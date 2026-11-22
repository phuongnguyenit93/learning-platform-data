# ReactorContextWebFilter và tích hợp ngữ cảnh bảo mật vào yêu cầu WebFlux

## 1. Mục tiêu và bối cảnh

Khi xử lý một HTTP request bằng Spring WebFlux, công việc không nhất thiết chạy từ đầu đến cuối trên một luồng (thread). Một chuỗi `Mono`/`Flux` có thể đổi thread khi gặp `publishOn`, `subscribeOn` hoặc khi I/O bất đồng bộ hoàn tất. Vì vậy, đọc danh tính người dùng bằng `SecurityContextHolder.getContext()` theo mô hình `ThreadLocal` của Servlet là không đáng tin cậy trong một reactive chain.

Bài này tập trung vào **`ReactorContextWebFilter`**: nó phối hợp `ServerSecurityContextRepository` với **Reactor Context** để cho phần xử lý phía sau đọc `SecurityContext` thông qua `ReactiveSecurityContextHolder`. Sau bài học, bạn có thể:

1. Phân biệt `ServerWebExchange`, Reactor `Context` và Spring Security `SecurityContext`.
2. Giải thích filter lấy ngữ cảnh bảo mật từ đâu, đưa vào reactive subscription khi nào, và vì sao không phụ thuộc thread.
3. Theo dõi ngữ cảnh qua xác thực HTTP Basic, phân quyền và handler WebFlux.
4. Đọc người dùng hiện tại đúng cách, cấu hình repository thích hợp và kiểm tra bằng request/test.
5. Nhận diện lỗi mất ngữ cảnh khi tự `subscribe()`, sử dụng `ThreadLocal` hoặc tạo tác vụ bên ngoài reactive chain.

## 2. Ba loại “context” có tên gần giống nhau

| Thành phần | Chứa gì? | Phạm vi và cách truy cập |
| --- | --- | --- |
| `ServerWebExchange` | Request, response, attributes, session và các tiện ích cho một lần trao đổi HTTP. | Đi qua `WebFilter` và WebFlux handler; truy cập qua tham số `exchange`. |
| Reactor `Context` | Dữ liệu có khóa/giá trị gắn với **subscription**, được truyền qua các toán tử reactive. | `Mono.deferContextual(...)` để đọc, `contextWrite(...)` để thêm/sửa. Nó không tự là HTTP session. |
| Spring Security `SecurityContext` | `Authentication`: principal, authorities và trạng thái xác thực. | Trong reactive flow, dùng `ReactiveSecurityContextHolder.getContext()`; API trả `Mono<SecurityContext>`. |

Cần hiểu thêm hai khái niệm:

- `ServerSecurityContextRepository` quyết định **cách tải/lưu** `SecurityContext` liên quan đến các request (chẳng hạn trong `WebSession`). Nó là nơi cung cấp context đã lưu; bản thân Reactor `Context` không tự lưu trạng thái qua các HTTP request.
- `ReactiveSecurityContextHolder` là API chuyên dụng để đọc/ghi security context vào **Reactor Context**, không phải một kho lưu trữ toàn cục. Các API đáng nhớ là `getContext()`, `withAuthentication(authentication)` và `withSecurityContext(Mono<SecurityContext>)`.

Hình dung một người dùng đã đăng nhập: repository có thể khôi phục `SecurityContext` của phiên HTTP; `ReactorContextWebFilter` gắn một publisher chứa context đó vào subscription đang xử lý request; controller hoặc bộ phân quyền có thể lấy ra danh tính từ cùng reactive chain.

## 3. ReactorContextWebFilter thực sự làm gì?

Tên lớp đầy đủ: `org.springframework.security.web.server.context.ReactorContextWebFilter`. Đây là một `WebFilter` thuộc **Spring Security WebFlux**, nhận `ServerSecurityContextRepository` qua constructor.

Theo mã nguồn, logic cốt lõi là:

1. Cho phần còn lại của `WebFilterChain` tiếp tục xử lý request.
2. Gắn thao tác `contextWrite(...)` vào publisher kết quả, để thiết lập Reactor Context cho subscription.
3. Nếu Reactor Context đã có khóa tương ứng `SecurityContext.class`, giữ nguyên context đang có. Nhờ vậy context do một phần khác trong chain cung cấp không bị ghi đè.
4. Nếu chưa có, lấy `Mono<SecurityContext>` từ `repository.load(exchange)` và đặt publisher ấy vào Reactor Context thông qua `ReactiveSecurityContextHolder.withSecurityContext(...)`.

Điểm tinh tế: filter gắn **`Mono<SecurityContext>`** vào Context. Điều đó không đồng nghĩa nó luôn phải xác thực người dùng ngay tại thời điểm WebFilter được gọi; việc subscribe và thực thi luồng tải context diễn ra theo cơ chế reactive. `load(exchange)` có thể trả `Mono.empty()` nếu không có context được lưu.

Luồng khái niệm:

```text
HTTP request
    |
    v
Spring Security WebFilter chain
    |
    +--> ReactorContextWebFilter
    |      \-- repository.load(exchange)
    |           \-- cung cấp Mono<SecurityContext> cho Reactor Context
    |
    +--> AuthenticationWebFilter (khi có cơ chế xác thực phù hợp)
    |      \-- nếu xác thực thành công: đưa Authentication mới vào context
    |
    +--> AuthorizationWebFilter / các bộ kiểm tra quyền
    |      \-- đọc Authentication trong reactive context
    |
    +--> WebFlux handler / service
           \-- ReactiveSecurityContextHolder.getContext()
```

**Đừng nhầm nhiệm vụ:** `ReactorContextWebFilter` không tự kiểm tra mật khẩu, không phát hành token và không tự gọi `save(...)` cho mọi request. Xác thực thông tin đăng nhập là nhiệm vụ của các bộ lọc/cơ chế authentication; việc lưu context phụ thuộc repository và cấu hình thành công xác thực. Filter này chủ yếu **đưa context có thể đọc được vào reactive subscription**.

## 4. Vị trí trong chuỗi bảo mật và sự tương tác với các filter khác

Spring Security định nghĩa `SecurityWebFiltersOrder.REACTOR_CONTEXT` cho vị trí của `ReactorContextWebFilter`. Nó đứng trước các vị trí HTTP Basic, form login, authentication và authorization để ngữ cảnh sẵn sàng cho những bước sau. Khi bật bảo mật WebFlux chuẩn qua `@EnableWebFluxSecurity` cùng `SecurityWebFilterChain`, framework lắp ráp các thành phần cần thiết; ứng dụng bình thường **không cần tự tạo và đăng ký thêm một `ReactorContextWebFilter`**.

Các vai trò liên quan:

- `AuthenticationWebFilter`: nếu request khớp matcher và có dữ liệu đăng nhập, chuyển request thành `Authentication`, gọi `ReactiveAuthenticationManager`, rồi đặt kết quả thành công vào `ReactiveSecurityContextHolder`. Tùy cấu hình, success handler lưu context qua repository.
- `ReactorContextWebFilter`: tạo đường truy cập tới `SecurityContext` **đã lưu từ repository** khi reactive context chưa có nó.
- `SecurityContextServerWebExchangeWebFilter`: làm cho `ServerWebExchange.getPrincipal()` tham chiếu danh tính được cung cấp bởi `ReactiveSecurityContextHolder`. Nó phục vụ hướng truy cập principal từ `exchange`, khác với nhiệm vụ nạp context của `ReactorContextWebFilter`.
- `AuthorizationWebFilter`: dùng thông tin xác thực để đánh giá quy tắc truy cập cấu hình trong `authorizeExchange`.

Ví dụ theo thời gian:

**Request A – vừa cung cấp thông tin đăng nhập:** context trong repository có thể chưa tồn tại; `AuthenticationWebFilter` xác thực credentials của chính request, đặt danh tính mới vào reactive chain và có thể lưu context nếu cơ chế đăng nhập được cấu hình như vậy.

**Request B – quay lại với HTTP session hợp lệ:** repository có thể tải context của lần đăng nhập trước; `ReactorContextWebFilter` đưa nó vào Reactor Context để thành phần phía sau dùng.

**Request C – stateless, mang token/Basic credentials mỗi lần:** không cần một session chứa context cũ; filter xác thực tương ứng phải xác thực thông tin của từng request. Không thể chỉ dựa vào `ReactorContextWebFilter` để suy ra danh tính khi repository không lưu gì.

## 5. Ví dụ WebFlux chạy được: lấy Authentication từ Reactor Context

Ví dụ dùng **Java 17+**, **Spring Boot 3.5.16**, Maven, WebFlux và Spring Security. Thông tin `demo/secret` và `{noop}` được dùng **chỉ cho bài thực hành cục bộ**; ứng dụng thật phải mã hóa mật khẩu và quản lý bí mật an toàn.

Cấu trúc dự án:

```text
reactor-context-demo/
├── pom.xml
├── src/main/java/demo/reactorcontext/DemoApplication.java
└── src/test/java/demo/reactorcontext/SecurityContextIntegrationTest.java
```

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactor-context-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

Tạo `src/main/java/demo/reactorcontext/DemoApplication.java`:

```java
package demo.reactorcontext;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(basic -> {})
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("demo")
            .password("{noop}secret")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/whoami")
    public Mono<String> whoami() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "Hello, " + auth.getName());
    }

    @GetMapping("/principal")
    public Mono<String> principal(ServerWebExchange exchange) {
        return exchange.getPrincipal().map(Principal::getName);
    }
}
```

`securityWebFilterChain` yêu cầu authenticated user ở `/whoami` và `/principal`. `httpBasic` xác thực HTTP Basic; `formLogin` bị tắt để request không có Basic credentials được xử lý theo HTTP API thay vì chuyển hướng tới form đăng nhập. `/whoami` đọc trực tiếp `SecurityContext` từ Reactor Context; `/principal` minh họa lớp cầu nối qua `ServerWebExchange.getPrincipal()`.

Chạy ứng dụng tại thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Ở terminal khác:

```bash
curl -s http://localhost:8080/public
curl -s -u demo:secret http://localhost:8080/whoami
curl -s -u demo:secret http://localhost:8080/principal
curl -i http://localhost:8080/whoami
```

Kết quả body của ba lệnh đầu, theo thứ tự:

```text
public
Hello, demo
demo
```

Lệnh cuối nhận **HTTP 401 Unauthorized** khi chưa cung cấp credentials hợp lệ; các header và body lỗi có thể tùy phiên bản/cấu hình. `curl -s` không thêm newline, nên khi chạy liên tiếp trong terminal, các body có thể dính trên cùng một dòng dù từng nội dung nêu trên là chính xác.

Vì sao không gọi thủ công `new ReactorContextWebFilter(...)`? `@EnableWebFluxSecurity` và `SecurityWebFilterChain` đã lắp ráp chuỗi bảo mật; tự đăng ký trùng filter có thể tạo đường thực thi khó theo dõi.

## 6. Kiểm chứng bằng WebTestClient

Tạo `src/test/java/demo/reactorcontext/SecurityContextIntegrationTest.java`:

```java
package demo.reactorcontext;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityContextIntegrationTest {
    @Autowired
    WebTestClient client;

    @Test
    void basicCredentialsAreAvailableFromReactorContext() {
        client.get().uri("/whoami")
            .headers(headers -> headers.setBasicAuth("demo", "secret"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("Hello, demo");
    }

    @Test
    void securityRulesApplyToTheRequest() {
        client.get().uri("/whoami")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }
}
```

Chạy `mvn test`. Bộ kiểm tra quan sát được cả hai mắt xích: yêu cầu HTTP đi qua filter chain và danh tính đã xác thực có thể được đọc tại WebFlux handler bằng `ReactiveSecurityContextHolder`. Kết quả mong đợi là hai bài test pass. Đây là kiểm tra tích hợp hành vi; không cần viết test cho mã nội bộ của `ReactorContextWebFilter`.

Bạn cũng có thể cô lập cơ chế Reactor Context mà không chạy HTTP server:

```java
Authentication auth =
    new TestingAuthenticationToken("alice", "unused", "ROLE_USER");

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

StepVerifier.create(name)
    .expectNext("alice")
    .verifyComplete();
```

Đoạn cuối là **trích đoạn trong một test**, không phải file Java độc lập. Cần import các type `Authentication`, `TestingAuthenticationToken`, `Mono`, `SecurityContext`, `ReactiveSecurityContextHolder`, `StepVerifier` và có dependency `reactor-test` ở test scope. Nó chứng minh `contextWrite` gắn một `Authentication` vào **subscription hiện tại**, để đoạn mã ở phía trước đọc được context; không gọi repository hay HTTP filter trong test này.

## 7. Cách đọc và truyền context đúng khi viết service

Ví dụ, cần lấy user hiện tại rồi gọi một service reactive:

```java
public Mono<String> currentGreeting(UserGreetingService service) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(auth -> auth.getName())
        .flatMap(service::greetingFor);
}
```

Đây là **phương thức minh họa**, với `UserGreetingService.greetingFor(String)` giả định trả `Mono<String>`. Hãy giữ pipeline do WebFlux subscribe; thông tin SecurityContext sẽ đi theo chuỗi các toán tử Reactor, kể cả khi cùng chain đổi thread bằng scheduler chuẩn của Reactor.

Để xử lý trường hợp không có người dùng:

```java
public Mono<String> optionalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(auth -> auth.getName())
        .defaultIfEmpty("anonymous");
}
```

Lưu ý: `defaultIfEmpty` chỉ áp dụng khi publisher không phát giá trị; nó không thay thế bước **kiểm tra quyền** ở endpoint. Quy tắc `authenticated()`, `hasRole(...)` hay method security vẫn là nơi quyết định ai được truy cập dữ liệu.

Một ví dụ quan trọng về hướng truyền Reactor Context:

```java
Mono<String> result = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
```

`contextWrite` ở cuối chuỗi thiết lập context cho các operator ở **phía trước (upstream)** trong cùng subscription. Reactor Context được truyền theo luồng subscribe từ downstream lên upstream. Vì thế không nên hiểu nó như một biến toàn cục tự động hiện diện cho mọi publisher trên toàn ứng dụng.

## 8. Session, stateless request và nơi lưu danh tính

**`WebSessionServerSecurityContextRepository`** lưu/đọc `SecurityContext` bằng WebFlux `WebSession`. Nó hữu ích khi ứng dụng duy trì đăng nhập qua session. Repository có hai phương thức chính:

- `load(ServerWebExchange) -> Mono<SecurityContext>`: tải context gắn với request; có thể trả `Mono.empty()`.
- `save(ServerWebExchange, SecurityContext) -> Mono<Void>`: lưu context theo chính sách của implementation.

**`NoOpServerSecurityContextRepository`** không giữ context giữa các request. Nó phù hợp với mô hình mỗi request tự xác thực thông qua Basic credentials, bearer token, v.v. Tuy nhiên **stateless hoàn chỉnh** yêu cầu kiểm tra cả cơ chế authentication, success handler, request cache và những thành phần có thể dùng session; chỉ đổi repository dùng để `load` không đủ để chứng minh toàn ứng dụng không tạo session.

Nếu muốn tùy biến repository, điểm cấu hình chính là:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        ServerSecurityContextRepository repository) {
    return http
        .securityContextRepository(repository)
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(basic -> {})
        .build();
}
```

Đây là **mẫu cấu hình minh họa thay thế bean ở phần 5**, không khai báo đồng thời hai `SecurityWebFilterChain` như nhau. Đối tượng `repository` cần do ứng dụng cung cấp; cách một bộ lọc authentication **lưu** context có thể cần cấu hình riêng tại bộ lọc ấy. `securityContextRepository(...)` của `ServerHttpSecurity` điều khiển nguồn context mà `ReactorContextWebFilter` sử dụng; không nên tự suy luận rằng nó đổi toàn bộ chính sách lưu của mọi loại authentication.

## 9. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra/sửa |
| --- | --- | --- |
| `SecurityContextHolder.getContext()` rỗng hoặc sai user trong WebFlux | Đọc context dựa trên `ThreadLocal` ở một chuỗi bất đồng bộ. | Dùng `ReactiveSecurityContextHolder.getContext()` trong `Mono`/`Flux`. |
| `ReactiveSecurityContextHolder.getContext()` rỗng | Không có session/token hợp lệ; chain không được bảo vệ; context chưa được tạo/đưa vào subscription; hoặc test tự dựng publisher ngoài môi trường HTTP. | Xem matcher/filter chain, auth filter, repository, và với unit test thì dùng `contextWrite(withAuthentication(...))`. |
| Có danh tính ở controller nhưng mất ở task khác | Tự `subscribe()`, tạo subscription mới không mang context, dùng `CompletableFuture`/executor tùy ý mà không truyền ngữ cảnh. | Giữ xử lý trong một reactive chain, compose bằng `flatMap`/`then` và trả publisher lên framework. |
| Tưởng đổi `publishOn` là mất context | Nhầm Reactor Context với `ThreadLocal`. | Với các operator Reactor thông thường, context thuộc subscription và không phụ thuộc tên thread; kiểm tra khi rời khỏi Reactor chain. |
| `exchange.getPrincipal()` khác kỳ vọng | Nhầm cầu nối principal với bước khôi phục `SecurityContext` hoặc request chưa xác thực. | Kiểm tra `SecurityContextServerWebExchangeWebFilter`, authentication và quyền của endpoint. |
| Request tiếp theo không còn login | Repository stateless, session/cookie thiếu hoặc filter authentication không lưu context theo cách mong đợi. | Kiểm tra `ServerSecurityContextRepository`, cookie/session và cấu hình lưu trong authentication flow. |
| Đọc được context nhưng không truy cập API downstream | Reactor Context không tự chuyển token qua HTTP khi gọi `WebClient`. | Cấu hình client outbound/OAuth2 token propagation thích hợp; không tự sao chép credentials một cách tùy tiện. |

Một cách chẩn đoán có thứ tự: xác định request có đi qua đúng `SecurityWebFilterChain` không; kiểm tra nơi credentials được chuyển thành `Authentication`; kiểm tra `repository.load(exchange)` có context hay không; cuối cùng theo dõi **cùng subscription** đi tới handler. Khi log, chỉ ghi những trường tối thiểu cần chẩn đoán; tránh log mật khẩu, bearer token, cookie phiên hoặc toàn bộ `SecurityContext`.

## 10. Câu hỏi tự kiểm tra

1. **Nếu `ServerSecurityContextRepository.load(exchange)` trả rỗng, `ReactorContextWebFilter` có tự tạo người dùng đã xác thực không?** Không. Nó chỉ cung cấp đường đọc context; xác thực hiện tại phải do cơ chế authentication khác thực hiện.
2. **Vì sao `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>` thay vì một object tức thì?** Vì giá trị phụ thuộc Reactor Context của subscription và nguồn security context có thể là một luồng bất đồng bộ.
3. **Có cần đăng ký thủ công `ReactorContextWebFilter` cho mọi `@RestController`?** Không, chuỗi Spring Security WebFlux chuẩn đã cấu hình filter tương ứng.
4. **`ReactorContextWebFilter` và `SecurityContextServerWebExchangeWebFilter` có giống nhau không?** Không. Một filter đưa context từ repository vào Reactor Context; filter kia tích hợp `getPrincipal()` trên `ServerWebExchange` với context reactive.
5. **`contextWrite` có lưu người dùng cho request HTTP ngày mai không?** Không. Nó tác động subscription hiện tại; trạng thái qua các request phải dựa vào session/token hoặc chiến lược lưu khác.
6. **Làm thế nào kiểm chứng integration thực tế?** Gửi request có credentials vào endpoint bảo vệ, kiểm tra handler đọc đúng danh tính, rồi gửi request không có credentials và xác nhận bị từ chối.

## 11. Tài liệu chính thức

- API `ReactorContextWebFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ReactorContextWebFilter.html
- API `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- API `ServerSecurityContextRepository`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html
- API `SecurityContextServerWebExchangeWebFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/SecurityContextServerWebExchangeWebFilter.html
- Hướng dẫn WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Mã nguồn `ReactorContextWebFilter`: https://github.com/spring-projects/spring-security/blob/main/web/src/main/java/org/springframework/security/web/server/context/ReactorContextWebFilter.java
