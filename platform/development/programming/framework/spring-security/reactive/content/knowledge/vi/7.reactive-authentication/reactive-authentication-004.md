# Phân biệt không có thông tin, thông tin không được hỗ trợ và thông tin không hợp lệ trong xác thực reactive

## 1. Ba trạng thái khác nhau

Trong ứng dụng **Spring WebFlux + Spring Security reactive**, một HTTP request chưa được xác thực không nhất thiết có “mật khẩu sai”. Cần phân biệt:

- **Không có thông tin (absent):** request không chứa credentials mà một filter đang tìm, ví dụ không có header `Authorization`.
- **Thông tin hoặc cơ chế không được hỗ trợ (unsupported):** có dữ liệu nhưng không thuộc loại mà converter hoặc authentication manager hiện tại phụ trách, ví dụ Basic converter gặp Bearer header, hoặc manager chỉ xử lý `UsernamePasswordAuthenticationToken` lại nhận một token Java loại khác.
- **Thông tin không hợp lệ (invalid):** cơ chế đã được nhận diện, credentials đã được thử xác thực nhưng bị từ chối, chẳng hạn mật khẩu sai, JWT hết hạn, chữ ký token sai, account bị khóa.

**Hậu quả quan trọng:** ba trường hợp có thể cùng kết thúc bằng HTTP 401 ở một route yêu cầu đăng nhập, nhưng có ý nghĩa rất khác về luồng Reactor, bảo mật, ghi log và việc thử phương thức xác thực kế tiếp.

Mục tiêu bài học là giải thích chính xác `Mono.empty()`, `Mono.error(...)`, `Mono.just(authentication)` ở hai ranh giới của hệ thống, tạo ví dụ Java 17+ chạy được, sau đó áp dụng vào HTTP Basic, JWT/Bearer và các trường hợp nhiều authentication manager.

## 2. Nơi quyết định: converter và manager

~~~text
Client HTTP request
    |
    v
WebFlux SecurityWebFilterChain
    |
    v
AuthenticationWebFilter
    |
    +-- requiresAuthenticationMatcher không khớp
    |     -> không thử xác thực, tiếp tục WebFilterChain
    |
    v
ServerAuthenticationConverter.convert(exchange)
    |
    +-- Mono.empty()
    |     -> không tạo Authentication cho filter này
    |
    +-- Mono.error(...)
    |     -> lỗi phát hiện trong bước chuyển đổi credentials
    |
    +-- Mono.just(Authentication token chưa xác thực)
          |
          v
ReactiveAuthenticationManager.authenticate(token)
          |
          +-- Mono.empty()
          |     -> manager không có kết luận / không hỗ trợ loại token
          |
          +-- Mono.error(AuthenticationException)
          |     -> xác thực thất bại
          |
          +-- Mono.just(Authentication đã xác thực)
                -> thành công, cung cấp SecurityContext cho chuỗi Reactor
    |
    v
Authorization: permitAll, authenticated, hasRole, ...
~~~

Hai giao diện cốt lõi có chữ ký gần giống nhau:

~~~java
// Chữ ký rút gọn, chưa phải toàn bộ source:
Mono<Authentication> convert(ServerWebExchange exchange);
Mono<Authentication> authenticate(Authentication authentication);
~~~

Nhưng **empty ở converter** có nghĩa filter không có một authentication attempt để tiến hành; theo tài liệu `AuthenticationWebFilter`, filter bỏ qua xác thực và tiếp tục chain. **Empty ở manager** nghĩa là đã có Authentication object được đưa tới manager nhưng manager **không xác định được** kết quả. Nó hữu ích để một manager khác xử lý nếu cơ chế delegation được thiết kế.

Không có quy tắc “bất cứ `Mono.empty()` nào cũng là password sai”. Cũng không được coi empty là authenticated thành công. Phải xem publisher đến từ **tầng nào**.

## 3. Trường hợp A: không có thông tin xác thực

Ví dụ một HTTP request không có Authorization header:

~~~http
GET /private HTTP/1.1
Host: localhost:8080
Accept: text/plain
~~~

Nếu ứng dụng cấu hình HTTP Basic, `ServerHttpBasicAuthenticationConverter` không nhận được dữ liệu Basic để chuyển thành token. Với converter bỏ qua đầu vào thiếu, kết quả là `Mono.empty()` và `AuthenticationWebFilter` không gọi manager cho request đó.

**Request có bị chặn hay không còn do authorization.**

| Route | Security rule | Hành vi thông thường khi không có credentials |
| --- | --- | --- |
| `GET /public` | `permitAll()` | HTTP 200 nếu handler trả thành công |
| `GET /private` | `authenticated()` | HTTP 401 qua HTTP Basic entry point |
| `GET /admin` | `hasRole("ADMIN")` | Chưa xác thực; thường được yêu cầu đăng nhập |

Với form login, server có thể redirect tới trang login thay vì HTTP 401. Với Bearer resource server, response/challenge có thể khác. Một request không gửi credentials **không tự động là lỗi** nếu route công khai.

**Anonymous cũng không đồng nghĩa đăng nhập.** Spring Security có thể dùng `AnonymousAuthenticationToken` để biểu diễn request không có danh tính thật; đừng suy luận “đã authenticated” chỉ vì có Authentication object. `authenticated()` xử lý ngữ nghĩa tin cậy, không đơn thuần `authentication != null`.

Trong ứng dụng nhiều phương thức, thiếu Bearer token không có nghĩa thiếu session cookie hợp lệ. Do đó “không có thông tin” luôn là nhận định **đối với một filter/matcher cụ thể**.

Snippet nhận diện missing tại converter:

~~~java
ServerAuthenticationConverter converter = exchange -> {
    String header = exchange.getRequest()
            .getHeaders().getFirst("Authorization");
    if (header == null || header.isBlank()) {
        return Mono.empty(); // Filter này không thử xác thực
    }
    // Nhánh parse dành cho scheme được hỗ trợ...
    return Mono.empty();
};
~~~

Đây là **đoạn minh họa không độc lập**, có một nhánh cuối để biểu diễn flow, không phải converter production hoàn chỉnh. Cần import `ServerAuthenticationConverter` và `reactor.core.publisher.Mono`.

## 4. Trường hợp B: thông tin hoặc loại Authentication không được hỗ trợ

### 4.1. Không hỗ trợ scheme ở converter

Ví dụ:

~~~http
GET /private HTTP/1.1
Host: localhost:8080
Authorization: Bearer example-token
~~~

Nếu ứng dụng chỉ có HTTP Basic, Basic converter **không phụ trách Bearer scheme**. Nó có thể bỏ qua bằng `Mono.empty()`. Nếu không có Bearer filter khác và route cần authentication, client vẫn thường nhận HTTP 401.

**Không thể kết luận JWT sai chữ ký hay hết hạn từ tình huống này**, vì Bearer token chưa được decoder tương ứng kiểm tra. Trong ứng dụng hỗ trợ nhiều cơ chế, việc Basic filter bỏ qua Bearer là bình thường để filter Bearer có thể thử xác thực. Nếu API chỉ cho phép một scheme, bạn cũng có thể thiết kế chính sách từ chối scheme lạ, nhưng cần nhất quán giữa parser, matcher, filter và entry point.

### 4.2. Không hỗ trợ loại Authentication object ở manager

`ReactiveAuthenticationManager` nhận một **đối tượng Java** như `UsernamePasswordAuthenticationToken`, `BearerTokenAuthenticationToken` hoặc custom token. Một manager chỉ hỗ trợ username/password có thể gặp `TestingAuthenticationToken` và **không có kết luận**:

~~~java
ReactiveAuthenticationManager manager = request -> {
    if (!(request instanceof UsernamePasswordAuthenticationToken)) {
        return Mono.empty();
    }
    // Manager có trách nhiệm kiểm tra username/password bên dưới.
    return Mono.error(new BadCredentialsException("Invalid credentials"));
};
~~~

Snippet này **chưa phải manager hợp lệ cho ứng dụng thật**: nhánh cuối cố tình giả lập lỗi để chỉ cách tách loại token. Phân biệt rõ:

- `Authorization: Bearer ...` là dạng credentials trên HTTP.
- `UsernamePasswordAuthenticationToken` là class Java biểu diễn authentication request/result.
- Bộ **converter** lựa chọn cách đọc HTTP request.
- Bộ **manager** quyết định có hỗ trợ kiểu token đã chuyển đổi và kiểm tra credentials hay không.

### 4.3. Nhiều manager và fallback

`DelegatingReactiveAuthenticationManager` có thể chứa nhiều manager. Manager trả empty cho một token không hỗ trợ có thể để delegate phía sau tiếp tục. Tuy nhiên, manager trả `Mono.error(...)` khi đã kiểm tra credentials và thất bại **không giống empty**: mặc định delegating manager không tiếp tục sang delegate tiếp theo sau lỗi.

Một số version có `setContinueOnError(boolean)`, nhưng không nên bật “thử tiếp dù password sai” theo phản xạ. Cách đó có thể làm suy yếu kiểm soát lockout, rate limit hoặc cho phép dữ liệu đăng nhập bị gửi tới provider khác. Hãy **định tuyến theo scheme/token type**, không thử mọi backend một cách mù quáng.

Một dịch vụ xác thực bị mất kết nối, database timeout hoặc JWK endpoint ngừng hoạt động cũng không mặc nhiên là unsupported. Đây là lỗi hạ tầng cần xử lý và giám sát riêng.

## 5. Trường hợp C: đã hỗ trợ, nhưng credentials không hợp lệ

Khi converter đã nhận diện scheme và tạo token, manager có thể xác định thông tin là sai. Ví dụ:

- Mật khẩu không khớp dù HTTP Basic được parse thành công.
- JWT đúng cấu trúc nhưng sai signature, hết hạn, issuer/audience không được chấp nhận.
- Tài khoản bị disabled/locked nếu manager có dữ liệu trạng thái.
- OTP sai, hết hạn hoặc đã dùng trong hệ thống có OTP.

Tín hiệu trong manager thường là `Mono.error(AuthenticationException)`, có thể dùng subtype như `BadCredentialsException`, `LockedException`, `DisabledException` hoặc exception dành cho token. Ví dụ nhánh code:

~~~java
if (!validCredentials) {
    return Mono.error(new BadCredentialsException("Invalid credentials"));
}
~~~

`validCredentials` là biến minh họa; đây **không phải Java class độc lập**. Điều quan trọng là **không biến password sai thành `Mono.empty()`**: hành vi đó che giấu một authentication attempt đã bị từ chối.

### 5.1. Sai cấu trúc và sai giá trị

Header `Authorization: Basic ???` có thể không giải mã được Base64. Lỗi malformed này có thể xuất hiện tại converter và không đi tới manager. Header Basic parse được, nhưng user/password sai, thường bị manager từ chối.

Tương tự, không gom mọi lỗi Bearer vào một nguyên nhân: token rỗng, format sai, không verify được signature và issuer không phù hợp có thể phát sinh từ các bước khác nhau. Tất cả đều cần được kiểm soát an toàn; không bịa một loại exception bất biến cho mọi phiên bản hoặc mọi cấu hình.

**Giữ thông báo trả về đủ chung.** Tránh để response tiết lộ username tồn tại hay không, mật khẩu đúng hay sai. Log bảo mật chỉ ghi loại sự kiện/correlation ID, không log raw password, token, session cookie hoặc API key.

## 6. Bảng đối chiếu giá trị reactive và HTTP

| Tình huống | Điểm quyết định | Publisher thường dùng | Ý nghĩa |
| --- | --- | --- | --- |
| Không có Authorization header cho Basic | Converter | `Mono.empty()` | Không tạo authentication attempt |
| Header Bearer vào converter Basic | Converter | Thường `Mono.empty()` | Scheme ngoài phạm vi filter này |
| Manager username/password nhận loại Authentication khác | Manager | `Mono.empty()` | Không có kết luận / không hỗ trợ |
| Username/password sai | Manager | `Mono.error(BadCredentialsException)` | Authentication thất bại |
| Token đã được kiểm tra nhưng hết hạn/sai chữ ký | Decoder/manager | Error phù hợp | Credentials không hợp lệ |
| Username/password đúng | Manager | `Mono.just(authenticated)` | Xác thực thành công |

Có thể cả thiếu header, unsupported scheme và password sai đều được biểu diễn là HTTP 401 ở một private endpoint dùng HTTP Basic. **Status code không đủ phân biệt đường đi nội bộ**. HTTP 403 thường là chuyện khác: principal đã được xác thực nhưng **authorization từ chối quyền**.

## 7. Ví dụ Spring Boot WebFlux chạy được với Java 17+

Ví dụ có hai phần. HTTP API thể hiện `/public`, `/private` và kết quả của Basic authentication; một `CommandLineRunner` gọi manager trực tiếp một lần để thấy cụ thể **unsupported type → empty**, **wrong password → error**, **correct password → success**.

### 7.1. Cấu hình Maven

Tạo project trên [Spring Initializr](https://start.spring.io/) với Java 17+, Maven, group `com.example`, artifact `auth-states-demo`; thêm **Spring Reactive Web** và **Spring Security**. File `pom.xml` hoàn chỉnh tối giản dùng Boot 4.1.2:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>auth-states-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

Để BOM Spring Boot quản lý phiên bản Spring Framework, Security và Reactor; không khai báo version cho từng module con.

### 7.2. Một lớp Java hoàn chỉnh

Tạo `src/main/java/com/example/authstates/AuthStatesDemoApplication.java`:

~~~java
package com.example.authstates;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class AuthStatesDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthStatesDemoApplication.class, args);
    }

    @Bean
    ReactiveAuthenticationManager demoManager() {
        return input -> {
            if (!(input instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            boolean userOk = "learner".equals(input.getName());
            boolean passwordOk = "correct".equals(input.getCredentials());
            if (!userOk || !passwordOk) {
                return Mono.error(
                        new BadCredentialsException("Invalid credentials"));
            }

            Authentication result =
                    UsernamePasswordAuthenticationToken.authenticated(
                            "learner", null,
                            List.of(new SimpleGrantedAuthority("ROLE_USER")));
            return Mono.just(result);
        };
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {
        return http
                .authenticationManager(manager)
                .authorizeExchange(rules -> rules
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/private").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    CommandLineRunner showOutcomes(ReactiveAuthenticationManager manager) {
        return args -> {
            Authentication unsupported =
                    new TestingAuthenticationToken("learner", "correct");
            Authentication invalid =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "learner", "wrong");
            Authentication valid =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "learner", "correct");

            System.out.println("UNSUPPORTED_TYPE -> "
                    + observe(manager, unsupported));
            System.out.println("WRONG_PASSWORD -> "
                    + observe(manager, invalid));
            System.out.println("CORRECT_PASSWORD -> "
                    + observe(manager, valid));
        };
    }

    private static String observe(
            ReactiveAuthenticationManager manager, Authentication input) {
        return manager.authenticate(input)
                .map(auth -> "SUCCESS:" + auth.getName())
                .switchIfEmpty(Mono.just("EMPTY"))
                .onErrorResume(BadCredentialsException.class,
                        e -> Mono.just("ERROR:" + e.getClass().getSimpleName()))
                .block();
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("PUBLIC_OK");
        }

        @GetMapping("/private")
        Mono<String> privateEndpoint() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(Authentication::getName)
                    .map(name -> "PRIVATE_OK:" + name);
        }
    }
}
~~~

Code có đủ package, import và class. Nó chỉ minh họa tín hiệu; manager hard-code mật khẩu là **không phù hợp cho production**. Ứng dụng thật cần lưu mật khẩu đã hash bằng password encoder, dùng nguồn danh tính đáng tin, HTTPS, timeout và monitoring.

`http.authenticationManager(manager)` đưa manager demo vào chain, giúp xác định cơ chế nào xác thực HTTP Basic. `ReactiveSecurityContextHolder` cho controller đọc user từ Reactor Context.

**Tại sao có `.block()`?** Chỉ dùng trong `CommandLineRunner` chạy một lần lúc startup để biến kết quả của probe thành chuỗi in ra; **không dùng `block()` trong request handler, WebFilter hoặc manager trên event loop**.

### 7.3. Khởi động và stdout

Trong thư mục chứa `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `.\mvnw.cmd spring-boot:run`; nếu không có wrapper, dùng `mvn spring-boot:run`. Ba dòng do `showOutcomes` in ra là:

~~~text
UNSUPPORTED_TYPE -> EMPTY
WRONG_PASSWORD -> ERROR:BadCredentialsException
CORRECT_PASSWORD -> SUCCESS:learner
~~~

Log khởi động của Spring Boot có thể xuất hiện thêm trước/sau. Probe **không** mô phỏng HTTP request thiếu header vì ở tình huống đó converter không tạo Authentication và manager không được gọi.

### 7.4. Thử HTTP bằng curl

Mở terminal khác khi server chạy tại `http://localhost:8080`:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -H "Authorization: Bearer some-token" http://localhost:8080/private
curl -i -u learner:wrong http://localhost:8080/private
curl -i -u learner:correct http://localhost:8080/private
~~~

| Request | HTTP status thường nhận | Body khi thành công | Giải thích |
| --- | --- | --- | --- |
| Không header, `/public` | 200 | `PUBLIC_OK` | Route công khai |
| Không header, `/private` | 401 | — | Chưa có authentication |
| Bearer header, `/private` | 401 | — | Basic converter không phụ trách Bearer |
| Basic `learner:wrong` | 401 | — | Manager từ chối password |
| Basic `learner:correct` | 200 | `PRIVATE_OK:learner` | Xác thực thành công |

Header và body của 401 tùy cơ chế/phiên bản. Không thể suy từ response 401 rằng converter hay manager đã phát sinh lỗi.

## 8. Custom ServerAuthenticationConverter: phân loại trước khi kiểm tra

Một converter tùy chỉnh có thể cho các trạng thái rõ ràng:

~~~java
ServerAuthenticationConverter demoConverter = exchange -> {
    String header = exchange.getRequest()
            .getHeaders().getFirst("Authorization");

    if (header == null || header.isBlank()) {
        return Mono.empty(); // ABSENT
    }
    if (!header.startsWith("Demo ")) {
        return Mono.empty(); // UNSUPPORTED SCHEME cho converter này
    }

    String credential = header.substring("Demo ".length()).trim();
    if (credential.isEmpty()) {
        return Mono.error(new BadCredentialsException(
                "Malformed Demo credentials")); // INVALID FORMAT
    }

    return Mono.just(
            UsernamePasswordAuthenticationToken.unauthenticated(
                    "demo", credential));
};
~~~

Đây là **snippet minh họa**, chưa có manager, matcher, failure handler hoặc HTTP config nên không phải chương trình độc lập. Cần import `ServerAuthenticationConverter`, `UsernamePasswordAuthenticationToken`, `BadCredentialsException` và `Mono`. Scheme Demo và username hard-code chỉ nhằm giải thích ranh giới, không dùng như một cơ chế bảo mật thật.

Bốn nhánh:

1. Thiếu header → không thử xác thực.
2. Scheme lạ → converter này không hỗ trợ; cơ chế khác chỉ có thể xử lý nếu đã cấu hình.
3. Scheme đúng nhưng dữ liệu malformed → báo lỗi, không biến thành missing.
4. Scheme đúng và có data → tạo token để **manager kiểm tra đúng/sai**.

Nếu một endpoint được phép dùng nhiều scheme, converter riêng nên bỏ qua scheme không thuộc trách nhiệm. Nếu endpoint chỉ chấp nhận một scheme, có thể chọn chính sách reject scheme lạ, nhưng phải rõ ràng và có test.

## 9. Những lỗi operator Reactor cần tránh

### Nuốt BadCredentialsException thành empty

~~~java
// Sai trong trường hợp password/token thực sự không hợp lệ:
return verifyCredential(request)
        .onErrorResume(error -> Mono.empty());
~~~

`verifyCredential` là method giả định. Đoạn này đổi từ **FAILED** thành **UNDETERMINED**; có thể kích hoạt fallback ngoài ý muốn, làm sai số liệu và bỏ qua chính sách khóa tài khoản.

### Tự tạo authentication từ empty

~~~java
// Sai: authGuest là biến giả định đã được đánh dấu authenticated.
return manager.authenticate(request)
        .defaultIfEmpty(authGuest);
~~~

Không có kết luận của manager **không phải căn cứ cấp danh tính**. Nếu cần fail closed, dùng chính sách từ chối hoặc lỗi cấu hình ở ranh giới phù hợp; không dựng principal có quyền.

### Dùng switchIfEmpty đúng tình huống

Có thể dùng `switchIfEmpty(Mono.defer(() -> otherManager.authenticate(request)))` khi manager đầu không hỗ trợ loại token và delegate thứ hai mới có thẩm quyền. Nó chỉ xử lý **empty**, không xử lý **error**. Password sai ở manager thứ nhất không được âm thầm đổi thành thành công ở provider thứ hai.

### Tránh I/O blocking trên event loop

~~~java
// Sai: tìm user đồng bộ trước khi tạo Mono.
return Mono.just(blockingRepository.findUser(username));
~~~

`blockingRepository` và `username` là ví dụ giả định. Với database/HTTP auth, dùng API reactive phù hợp hoặc cô lập thư viện blocking trên scheduler có giới hạn; `Mono.just(...)` không tự biến lời gọi blocking thành non-blocking.

## 10. Kết quả authentication khác authorization

`AuthenticationWebFilter` thử xác thực khi matcher và converter có đầu vào. `ReactiveAuthenticationManager` trả kết quả/empty/error. `ExceptionTranslationWebFilter` và các handler bảo mật xử lý việc yêu cầu đăng nhập hoặc trả lỗi phân quyền ở downstream, tùy cấu hình.

- **ABSENT:** request anonymous vẫn có thể vào endpoint `permitAll`.
- **UNSUPPORTED:** bộ lọc hiện tại không chứng minh token đúng hay sai; phải có cơ chế khác thích hợp hoặc để authorization yêu cầu đăng nhập.
- **INVALID:** lỗi xác thực từ converter/manager cần được xử lý theo failure path; Basic thường trả 401.
- **SUCCESS:** SecurityContext chứa authenticated principal; authorization vẫn có thể trả 403 nếu thiếu role.

`permitAll` không nhất thiết làm request gửi credentials **sai** được qua: một filter authentication nhận credentials sai có thể từ chối trước khi kiểm tra URL authorization.

## 11. Test và debug

Nên kiểm thử các trường hợp:

1. Converter nhận request không có header ⇒ `Mono.empty()`.
2. Converter nhận scheme khác ⇒ empty hoặc error theo chính sách của ứng dụng.
3. Converter nhận scheme đúng nhưng malformed ⇒ error thích hợp.
4. Manager nhận Authentication token type không hỗ trợ ⇒ empty.
5. Manager nhận password sai ⇒ `BadCredentialsException`.
6. Manager nhận password đúng ⇒ Authentication đã xác thực, authority phù hợp.
7. HTTP route công khai anonymous ⇒ 200; private anonymous ⇒ 401 với Basic.
8. HTTP private với wrong password ⇒ 401; đúng password ⇒ 200.
9. Nếu có nhiều manager ⇒ bảo đảm error thật không bị biến thành fallback không an toàn.

Ở tầng publisher, dùng `reactor-test`/`StepVerifier` để kiểm tra empty/error/next signal; với API HTTP WebFlux, dùng `WebTestClient` và Spring Security test support.

Có thể bật log trong môi trường dev:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Nên phân loại log bằng mã sự kiện nội bộ như `credential_absent`, `unsupported_scheme`, `unsupported_authentication_type`, `authentication_failed`, `authentication_success`. Không ghi password, token, Basic header, cookie hoặc private key vào log. Dùng correlation ID để lần theo request qua các thành phần.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Basic converter trả empty do thiếu Authorization header, có phải user nhập password sai?

**Đáp án:** Không. Không có authentication attempt; bước authorization quyết định có cho anonymous vào route hay không.

**Câu 2.** Manager chỉ hỗ trợ username/password nhận token type khác và trả empty. Đây có phải login thành công?

**Đáp án:** Không. Manager không có kết luận; một delegate phù hợp có thể thử tiếp nếu được cấu hình, nhưng chưa ai xác thực thành công.

**Câu 3.** Username/password đã được parse và password sai, trả empty hay error?

**Đáp án:** `Mono.error(new BadCredentialsException(...))` để thể hiện authentication attempt thất bại.

**Câu 4.** Bearer header vào Basic-only API nhận 401. Có chứng minh JWT bị sai chữ ký không?

**Đáp án:** Không. Basic converter không kiểm tra chữ ký JWT; nếu không cấu hình Bearer authentication filter, token chưa được kiểm chứng.

**Câu 5.** Vì sao `/public` không header có thể trả 200 nhưng request gửi credentials sai đến cùng URL có thể bị 401?

**Đáp án:** Thiếu header khiến Basic converter bỏ qua; gửi credentials sai có thể kích hoạt authentication failure trước khi `permitAll` ở tầng authorization được xét.

**Câu 6.** Vì sao không dùng `onErrorResume(... -> Mono.empty())` cho mọi lỗi xác thực?

**Đáp án:** Nó xóa mất sự kiện credentials đã được kiểm tra và bị từ chối, có thể dẫn tới fallback không an toàn và che giấu lỗi hạ tầng.

## 13. Tài liệu chính thức

- [Spring Security — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security — ServerAuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html)
- [Spring Security — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security — DelegatingReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html)
- [Spring Security — Reactive HTTP Basic](https://docs.spring.io/spring-security/reference/reactive/authentication/basic.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — OAuth2 Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
