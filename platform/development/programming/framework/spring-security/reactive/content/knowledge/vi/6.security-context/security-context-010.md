# Ngăn rò rỉ danh tính giữa các yêu cầu chạy đồng thời

**Module:** Spring Security – Reactive · **Phần:** Ngữ cảnh bảo mật.

Trong Spring WebFlux, nhiều yêu cầu HTTP của các người dùng khác nhau có thể được xử lý xen kẽ trên một số ít event-loop thread; một pipeline cũng có thể tiếp tục trên thread khác sau `delay`, `publishOn` hoặc một lời gọi I/O bất đồng bộ. Nếu lưu danh tính người dùng trong trường của singleton, biến `static`, `ThreadLocal` tự quản lý hoặc một Publisher được chia sẻ sai cách, yêu cầu của **Alice** có thể đọc nhầm thông tin của **Bob**. Đây là lỗi **rò rỉ danh tính giữa các request** (*cross-request identity leak*), có thể dẫn tới lộ dữ liệu hoặc cấp quyền sai.

Giải pháp cốt lõi là để Spring Security gắn `SecurityContext` với **Reactor Context của subscription tương ứng**, đọc danh tính bằng `ReactiveSecurityContextHolder` trong chuỗi reactive, và không biến thông tin đó thành trạng thái dùng chung không được phân vùng theo người dùng.

Bài này giải thích cơ chế, chỉ ra các mẫu code sai/đúng, cung cấp một ứng dụng Java 17+ chạy được và một bộ kiểm thử `WebTestClient` tạo nhiều yêu cầu đồng thời để phát hiện việc trộn danh tính.

## 1. Phát biểu đúng vấn đề

Giả sử hai client gửi gần như đồng thời:

```text
Client A (Authorization: Basic alice:...)       Client B (Authorization: Basic bob:...)
                  |                                                |
                  v                                                v
           Request A /api/delayed                         Request B /api/delayed
                  |                                                |
          authenticated = Alice                          authenticated = Bob
                  |                                                |
                 [chờ bất đồng bộ, nhiều tín hiệu được xen kẽ trên event-loop]
                  |                                                |
                  v                                                v
            response "Alice"                               response "Bob"
```

**Bất biến cần giữ:** Mọi bước dùng danh tính trong request A phải tham chiếu **Authentication hợp lệ của A**; mọi bước của request B phải tham chiếu **Authentication của B**, bất kể thứ tự chạy, thread nào thực thi, độ trễ, số lượng request hoặc số lần subscribe. Không bao giờ được thấy A trả kết quả của B, và ngược lại.

Cần tách ba câu hỏi:

1. **Ai xác thực?** Spring Security xác thực từng request bằng HTTP Basic, Bearer token, session hoặc cơ chế được cấu hình; thành công tạo ra một `Authentication`.
2. **Danh tính được giữ ở đâu?** Trong lập trình reactive, ngữ cảnh bảo mật được cung cấp thông qua `ReactiveSecurityContextHolder` và Reactor `Context` gắn với subscriber; request không có một thread riêng cố định.
3. **Mã nghiệp vụ lấy danh tính lúc nào?** Nó phải lấy trong **pipeline của request đang được subscribe**, sau khi security filter chuẩn bị context, thay vì lấy một giá trị từng được ghi vào bộ nhớ dùng chung trước đó.

Rò rỉ có thể xuất hiện dù ứng dụng trả `200` bình thường: request của Alice nhận dữ liệu Bob là một sai phạm nghiêm trọng hơn việc trả status lỗi. Do đó, chỉ test `200/401/403` là **chưa đủ**; cần assert **đúng principal, đúng tài nguyên và đúng tenant**.

## 2. Vì sao ThreadLocal không là nguồn danh tính tin cậy trong WebFlux?

Ở ứng dụng Servlet truyền thống, một request thường chiếm một thread trong lúc xử lý. Spring Security Servlet có thể dùng `SecurityContextHolder` với chiến lược `ThreadLocal`. Nhưng trong WebFlux:

- Một event-loop thread phục vụ nhiều request ở các thời điểm xen kẽ.
- `Mono.delay` hoặc nhiều operator chuyển lịch chạy sang scheduler khác.
- `flatMap` có thể đan xen nhiều inner Publisher; thứ tự và thread không nhất thiết như luồng Java tuần tự.
- Tác vụ async, retry, cancellation và scheduling có thể khiến thread đang chạy không trùng thread khi request đi vào.

`ThreadLocal` gắn dữ liệu với **thread**, còn bảo mật cần gắn với **request/subscription**. Một `ThreadLocal` chưa được dọn sạch có thể làm lộ thông tin của request trước cho tác vụ sau chạy cùng thread; một ThreadLocal thiếu cơ chế propagation có thể trả `null` khi đổi thread. Việc đổi sang `InheritableThreadLocal` không xử lý đúng thread pool hoặc hàng loạt task bất đồng bộ.

Đối với Spring Security Reactive, dùng:

```java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

Đây là **fragment** (cần import và Spring Security Reactive context) trả `Mono<String>`; nó **không** đọc một biến toàn cục lúc tạo Publisher. Khi được subscribe trong pipeline phù hợp, nó nhận context của subscriber tương ứng. Đừng thay bằng `SecurityContextHolder.getContext().getAuthentication()` kiểu Servlet để quyết định quyền trong WebFlux.

**Phân biệt:** Một số phiên bản/cấu hình Reactor có hỗ trợ chuyển đổi Reactor Context ↔ `ThreadLocal` cho hệ thống tracing/MDC thông qua Micrometer Context Propagation; điều đó không có nghĩa biến `ThreadLocal` tùy tiện sẽ trở thành nguồn danh tính bảo mật an toàn. Nếu tích hợp thư viện legacy dùng ThreadLocal, cần thiết lập accessor, phạm vi restore/cleanup rõ ràng, kiểm thử và đánh giá tác động riêng.

## 3. Reactor Context cách ly theo subscriber như thế nào?

Reactor `Context` là tập key/value **bất biến** theo góc nhìn người dùng: `put` sinh ra context mới, không sửa trực tiếp object cũ. Mỗi `Subscriber` có context riêng; tín hiệu subscription đi từ downstream lên upstream để các operator đọc context cần thiết.

- `contextWrite(...)` gắn/điều chỉnh context cho các **operator ở phía upstream** của nó, trong subscription hiện tại.
- `Mono.deferContextual(ctx -> ...)` đọc `ContextView` khi subscription diễn ra, không lấy dữ liệu ngay ở bước assembly.
- `ReactiveSecurityContextHolder.getContext()` đọc `SecurityContext` từ Reactor Context mà Spring Security Reactive cung cấp.
- `ReactiveSecurityContextHolder.withAuthentication(authentication)` tạo context chứa `Authentication`, hữu ích cho **test hoặc pipeline đã được tin cậy**. Không dùng nó để cho client tự chọn người dùng theo một header tự khai.

Ví dụ thuần Reactor để hiểu tính riêng biệt (fragment):

```java
Mono<String> message = Mono.deferContextual(ctx ->
    Mono.just("user=" + ctx.get("user")));

Mono<String> alice = message.contextWrite(ctx -> ctx.put("user", "alice"));
Mono<String> bob   = message.contextWrite(ctx -> ctx.put("user", "bob"));
```

Nếu subscribe vào `alice`, nó phát `user=alice`; subscribe vào `bob`, nó phát `user=bob`. Việc cả hai bắt nguồn từ **cùng một đối tượng `message`** không làm trộn context, vì mỗi subscription có context riêng. Ngược lại, nếu `message` được `cache()` sau khi gắn dữ liệu người dùng rồi chia sẻ cho mọi người, kết quả được cache có thể mất tính cách ly.

### 3.1. Vị trí contextWrite rất quan trọng

```java
// Đọc được "alice": contextWrite ở downstream của đoạn đọc.
Mono<String> good = Mono.deferContextual(ctx ->
    Mono.just(ctx.<String>get("user")))
    .contextWrite(ctx -> ctx.put("user", "alice"));

// Fragment sai vị trí: flatMap bên dưới không nhìn thấy key mới.
Mono<String> misplaced = Mono.just(1)
    .contextWrite(ctx -> ctx.put("user", "alice"))
    .flatMap(i -> Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("user", "missing"))));
```

`good` phát `alice`; `misplaced` phát `missing` khi subscribe (giả sử không có key `user` trước đó). Context đi theo đường **subscription**, không phải là biến global truyền theo mọi tín hiệu `onNext`. Các operator tạo inner Publisher có quy tắc ngữ cảnh riêng; khi cần đưa context vào một luồng tách biệt, phải thiết kế đường nối rõ ràng.

## 4. Các anti-pattern làm rò rỉ danh tính

### 4.1. Trường mutable trong singleton Spring bean

**Sai:**

```java
@Service
class UnsafeGreetingService {
    private volatile String lastUser;

    Mono<String> greet() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .doOnNext(name -> lastUser = name)
            .then(Mono.delay(Duration.ofMillis(40)))
            .map(ignored -> "hello " + lastUser);
    }
}
```

Đây là **mảnh minh họa cố ý không an toàn**; cần import các kiểu Spring/Reactor nếu thử riêng. `@Service` mặc định là singleton. Request Alice gán `lastUser="alice"`, sau đó chờ; request Bob gán `lastUser="bob"`; khi Alice tiếp tục, Alice có thể trả `hello bob`. `volatile` chỉ giúp nhìn thấy bản ghi giữa các thread, **không** phân biệt người dùng. `synchronized` hoặc biến `static` cũng không phải mô hình lưu principal của request.

**Đúng: giữ tên của mỗi subscription trong luồng dữ liệu cục bộ.**

```java
@Service
class SafeGreetingService {
    Mono<String> greet() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .flatMap(name -> Mono.delay(Duration.ofMillis(40))
                .map(ignored -> "hello " + name));
    }
}
```

Mỗi subscriber có biến `name` riêng trong lambda của nó. Sau khi đọc context, `flatMap` giữ giá trị tương ứng cho nhánh async. Không ghi vào trường bean, biến static hay đối tượng mutable dùng chung. Hai đoạn trên là **ví dụ đối chiếu**, không phải hai class bắt buộc của ứng dụng chạy được ở phần 5.

### 4.2. Cache Publisher chứa principal hoặc dữ liệu riêng của user

**Sai:**

```java
@Service
class UnsafeIdentityCache {
    private final Mono<String> cachedUser =
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .cache();

    Mono<String> currentUser() {
        return cachedUser;
    }
}
```

`cache()` lưu tín hiệu của lần đăng ký đầu tiên rồi phát lại cho những subscriber về sau. Nếu singleton lưu `cachedUser`, Alice có thể làm đầy cache trước, sau đó Bob đọc được tên Alice. Bảo vệ endpoint bằng `authenticated()` không tự giải quyết việc **trộn nội dung sau khi đã qua xác thực**.

**Đúng với dữ liệu danh tính:** tạo nguồn đọc context theo subscription, không dùng cache chung:

```java
Mono<String> currentUser() {
    return Mono.defer(() -> ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName));
}
```

Các đoạn ở đây minh họa trong bean đã có import. Nếu cache thông tin nghiệp vụ, thiết kế key theo danh tính được xác thực **và phạm vi dữ liệu/quyền/tenant tương ứng**, có quy tắc TTL và invalidation; không cache `Authentication` nhạy cảm trên toàn ứng dụng chỉ vì tối ưu hiệu năng. Cẩn thận với `share()`, `publish().refCount()`, hot `Sinks.Many` và publisher tạo ở scope singleton: chúng có thể phát dữ liệu cho nhiều subscriber khác nhau.

### 4.3. Tự subscribe() tạo luồng tách khỏi request

**Sai:**

```java
@GetMapping("/notify")
Mono<String> notifyUser() {
    service.notifyCurrentUser().subscribe(); // tách khỏi request
    return Mono.just("accepted");
}
```

Đây là fragment cố ý sai (ứng dụng phải tự định nghĩa `service`). Lần `subscribe()` thủ công tạo subscription mới, có thể mất security context của HTTP request; exception/cancellation không còn đi cùng response. Nếu bên trong job đọc ThreadLocal, nó có thể lấy nhầm danh tính, hoặc `ReactiveSecurityContextHolder.getContext()` trả rỗng.

**Đúng:** đưa tác vụ vào một chuỗi trả về cho WebFlux:

```java
@GetMapping("/notify")
Mono<String> notifyUser() {
    return service.notifyCurrentUser()
        .thenReturn("accepted");
}
```

Đây cũng là fragment; kết quả trên chỉ hợp lý nếu API cần **chờ tác vụ hoàn tất** trước khi trả response. Nếu thực sự cần background job, hãy mô hình hóa job/queue, truyền **định danh đã xác minh và thông tin ủy quyền tối thiểu** một cách rõ ràng, kiểm tra quyền tại điểm xử lý job và có idempotency/giám sát. Không dựa vào một Reactor Context của request đã kết thúc để cấp quyền mãi về sau.

### 4.4. Lấy username từ header do client tự gửi

`X-User: alice`, `X-Role: ADMIN` hoặc query parameter `?user=alice` không chứng minh người gọi là Alice. Chỉ reverse proxy/API gateway **đã được tin cậy, xác minh và cấu hình** mới có thể chuyển tiếp danh tính có bảo đảm; tại biên ứng dụng phải ngăn giả mạo header từ client. Trong ứng dụng WebFlux thông thường, dùng `Authentication` do Spring Security xây dựng từ credential hợp lệ.

### 4.5. Dùng dữ liệu yêu cầu A để ủy quyền yêu cầu B

Tránh ghi `SecurityContext` hoặc `Authentication` của Alice vào singleton/map không có vòng đời rõ; tránh lưu một `ServerWebExchange` hoặc mutable request object cho công việc chia sẻ với request khác. Đừng giữ reference đến bearer token, password hay cookies trong cache/service field để tái sử dụng.

## 5. Ứng dụng Java 17+ có thể chạy để quan sát cách ly danh tính

Ví dụ tạo ứng dụng Spring Boot WebFlux với hai user thử nghiệm `alice` và `bob`. Hai endpoint đều yêu cầu Basic auth:

- `GET /api/identity` trả `now:alice` hoặc `now:bob` từ security context hiện tại.
- `GET /api/delayed` dùng `Mono.delay` để đổi lịch chạy rồi mới đọc context, trả `later:alice` hoặc `later:bob`. Nhiều client gọi đồng thời vẫn phải nhận đúng người của chính mình.

Dùng Spring Boot `3.5.16` trong ví dụ và JDK 17+. Phiên bản là mốc biên dịch cụ thể; khi triển khai production, chọn phiên bản còn hỗ trợ và các bản vá bảo mật mới nhất theo quy định dự án.

### 5.1. Cấu trúc dự án

```text
reactive-context-isolation/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/isolation/
    │   │   ├── IsolationApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── IdentityService.java
    │   │   └── IdentityController.java
    │   └── resources/application.properties
    └── test/java/demo/isolation/
        └── IdentityIsolationTests.java
```

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-context-isolation</artifactId>
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

Chỉ dùng WebFlux starter, không cần `spring-boot-starter-web` (Spring MVC). `reactor-test` dùng để kiểm tra context mỗi subscriber bằng `StepVerifier`. Không cần database.

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-context-isolation
server.port=8080
```

### 5.2. Entry point

`src/main/java/demo/isolation/IsolationApplication.java`:

```java
package demo.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }
}
```

### 5.3. Hai tài khoản và một security chain

`src/main/java/demo/isolation/SecurityConfig.java`:

```java
package demo.isolation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}alice123")
            .roles("USER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password("{noop}bob123")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/identity", "/api/delayed")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }
}
```

- Hai user có cùng role `USER` để loại bỏ khác biệt role khỏi phép thử: thứ cần kiểm là **danh tính chính xác** trong response.
- HTTP Basic khiến mỗi test client có thể gửi credential riêng và quan sát trực tiếp. `{noop}` là mật khẩu rõ, **chỉ sử dụng trong bài thực hành trên localhost**; production phải dùng password hash/secret storage, HTTPS và cấu hình authentication phù hợp.
- `authenticated()` ngăn request chưa đăng nhập; `anyExchange().denyAll()` không vô tình mở endpoint khác. Đừng cho client tự chọn identity bằng header tự khai.
- `.formLogin(login -> login.disable())` tránh redirect trang đăng nhập khi test HTTP Basic. Nếu dự án thật dùng session/login form, cần kiểm tra cách lưu security context của session và cookie độc lập từng client.

### 5.4. Service không lưu trạng thái người dùng

`src/main/java/demo/isolation/IdentityService.java`:

```java
package demo.isolation;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class IdentityService {

    public Mono<String> current(String stage) {
        return Mono.defer(() ->
            ReactiveSecurityContextHolder.getContext()
                .switchIfEmpty(Mono.error(
                    new IllegalStateException("Missing reactive security context")))
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .map(name -> stage + ":" + name)
        );
    }
}
```

`@Service` là singleton, nhưng **không có field mutable chứa principal**. Mỗi lần subscribe vào `current(...)`, `Mono.defer` yêu cầu đọc `SecurityContext` từ context hiện có của subscription. Nếu thiếu context, mẫu chủ động phát lỗi thay vì âm thầm lấy danh tính mặc định hoặc chuyển sang user trước đó. Lớp service không tự cache `Mono` chứa tên người dùng.

### 5.5. Controller chuyển lịch chạy nhưng vẫn giữ đúng danh tính

`src/main/java/demo/isolation/IdentityController.java`:

```java
package demo.isolation;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class IdentityController {

    private final IdentityService identities;

    public IdentityController(IdentityService identities) {
        this.identities = identities;
    }

    @GetMapping(value = "/identity", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> identity() {
        return identities.current("now");
    }

    @GetMapping(value = "/delayed", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> delayed() {
        return Mono.delay(Duration.ofMillis(40))
            .then(identities.current("later"));
    }
}
```

`Mono.delay` dùng scheduler của Reactor để phát tín hiệu sau khoảng thời gian chờ. `then(...)` tiếp tục trong **cùng cây reactive subscription**, nên việc đọc `ReactiveSecurityContextHolder.getContext()` vẫn thấy đúng security context. Không cần biết hay cố định tên thread; tính đúng đắn dựa trên context của subscriber, không dựa trên “thread Alice”.

Cũng có thể dùng `publishOn(Schedulers.parallel())` hoặc một repository reactive trả `Mono` để minh họa đổi thread. Chúng không tự làm mất Reactor Context khi được ghép bình thường trong cùng pipeline. Tuy nhiên, nhảy ra hệ thống ngoài Reactor bằng `CompletableFuture.supplyAsync(...)` hoặc tự tạo task trong ExecutorService rồi đọc ThreadLocal là **một ranh giới khác**, cần truyền dữ liệu xác minh hoặc cơ chế propagation thích hợp.

## 6. Chạy thử bằng curl để kiểm chứng từng người

Cần JDK 17+, Maven và cổng 8080 trống. Từ thư mục dự án:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Mở terminal khác:

```bash
curl -i http://localhost:8080/api/identity
curl -i --user alice:alice123 http://localhost:8080/api/identity
curl -i --user bob:bob123 http://localhost:8080/api/identity
curl -i --user alice:alice123 http://localhost:8080/api/delayed
curl -i --user bob:bob123 http://localhost:8080/api/delayed
curl -i --user alice:wrong http://localhost:8080/api/identity
```

Theo cấu hình ví dụ, các status/body tương ứng:

| Request | Dự kiến |
| --- | --- |
| Anonymous `/api/identity` | `401 Unauthorized` (Basic challenge) |
| Alice `/api/identity` | `200`, body chính xác `now:alice` |
| Bob `/api/identity` | `200`, body chính xác `now:bob` |
| Alice `/api/delayed` | `200`, body chính xác `later:alice` |
| Bob `/api/delayed` | `200`, body chính xác `later:bob` |
| Sai password | `401 Unauthorized` |

Lưu ý khác nhau giữa **xác thực** và **không rò rỉ**: cả Alice lẫn Bob đều có thể qua `authenticated()` và nhận `200`. Phải so sánh body với principal đã xác thực để nhận ra lỗi “Alice nhận tên Bob”. Trên PowerShell cũ, có thể phải dùng `curl.exe` để gọi đúng chương trình curl.

Thử giả mạo header, nhưng vẫn dùng Basic của Alice:

```bash
curl -i --user alice:alice123 \
  -H "X-Authenticated-User: bob" \
  http://localhost:8080/api/delayed
```

Kết quả phải là `later:alice`, vì controller lấy danh tính từ Spring Security, không từ header không được tin cậy. Không đưa password/token thật lên shell history hoặc log; ngoài localhost phải dùng HTTPS vì Basic không mã hóa bản thân credential.

## 7. WebTestClient kiểm tra đồng thời, sai credential và per-subscriber Context

Đây là phần quan trọng nhất để biến “không rò rỉ” thành yêu cầu đo được. Dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot chạy WebFlux server thật trên cổng ngẫu nhiên; `WebTestClient` gửi HTTP request có Basic auth đến server đó. Không cần khởi chạy `mvn spring-boot:run` riêng trước khi chạy test.

`src/test/java/demo/isolation/IdentityIsolationTests.java`:

```java
package demo.isolation;

import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.IntStream;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class IdentityIsolationTests {

    @Autowired
    WebTestClient client;

    private void expectIdentity(
        String username, String password, String path, String prefix
    ) {
        client.get()
            .uri(path)
            .headers(headers -> headers.setBasicAuth(username, password))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo(prefix + ":" + username);
    }

    @Test
    void rejectsAnonymous() {
        client.get().uri("/api/identity")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void rejectsWrongPassword() {
        client.get().uri("/api/identity")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void keepsEachUserInSequentialRequests() {
        expectIdentity("alice", "alice123", "/api/identity", "now");
        expectIdentity("bob", "bob123", "/api/identity", "now");
        expectIdentity("alice", "alice123", "/api/identity", "now");
    }

    @Test
    void retainsIdentityAfterAsyncDelay() {
        expectIdentity("alice", "alice123", "/api/delayed", "later");
        expectIdentity("bob", "bob123", "/api/delayed", "later");
    }

    @Test
    void ignoresSpoofedIdentityHeader() {
        client.get().uri("/api/delayed")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .header("X-Authenticated-User", "bob")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("later:alice");
    }

    @Test
    void parallelRequestsDoNotExchangeIdentity() {
        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            List<CompletableFuture<Void>> tasks =
                IntStream.range(0, 40)
                    .mapToObj(index -> CompletableFuture.runAsync(() -> {
                        boolean even = index % 2 == 0;
                        String username = even ? "alice" : "bob";
                        String password = even ? "alice123" : "bob123";
                        expectIdentity(
                            username, password, "/api/delayed", "later");
                    }, pool))
                    .toList();

            CompletableFuture.allOf(
                tasks.toArray(new CompletableFuture[0])
            ).join();
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void onePublisherSupportsDifferentSubscriberContexts() {
        Mono<String> current = ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);

        Authentication alice = new TestingAuthenticationToken(
            "alice", "unused", "ROLE_USER");
        Authentication bob = new TestingAuthenticationToken(
            "bob", "unused", "ROLE_USER");

        StepVerifier.create(current.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(current.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(bob)))
            .expectNext("bob")
            .verifyComplete();
    }
}
```

Chạy:

```bash
mvn test
```

Nếu dự án chỉ chứa test class này, kết quả kỳ vọng là **7 test pass**; thời gian chạy, thứ tự test và log Maven phụ thuộc máy. Khi test thất bại, xem assertion expected/actual cùng security filter và request header, đừng đoán theo các dòng log Reactor không có thứ tự cố định.

### 7.1. Những điều test chứng minh

- `rejectsAnonymous` và `rejectsWrongPassword`: endpoint bảo vệ đang dùng đúng credential; tránh ngộ nhận principal đến từ request header tùy ý.
- `keepsEachUserInSequentialRequests`: cùng một `WebTestClient` đổi credential Alice → Bob → Alice, response vẫn nhận đúng từng request.
- `retainsIdentityAfterAsyncDelay`: đổi lịch chạy của Reactor không khiến danh tính biến mất hoặc nhảy sang user khác.
- `ignoresSpoofedIdentityHeader`: header `X-Authenticated-User` giả mạo không thay đổi `Authentication`.
- `parallelRequestsDoNotExchangeIdentity`: 40 request từ 8 thread client với credential xen kẽ, mỗi assertion kiểm tra **cả 200 lẫn body đúng tên user**. `CompletableFuture.allOf(...).join()` chuyển thất bại assertion trong worker thread thành test thất bại, không “nuốt” lỗi.
- `onePublisherSupportsDifferentSubscriberContexts`: cùng đối tượng `Mono<String>` có thể đọc hai context riêng khi subscribe ở hai nhánh độc lập. `withAuthentication(...)` chỉ dùng **trong test do ta kiểm soát**, không phải cho HTTP client quyền tự chỉ định identity.

**Giới hạn thực tế của concurrency test:** 40 request không thể chứng minh không bao giờ có race condition dưới mọi lịch thực thi; test là kiểm tra hồi quy có giá trị, nên tăng biến thể delay/số request phù hợp CI, quan sát lỗi lặp lại và kết hợp review những nơi dùng mutable shared state. Không lạm dụng sleep để “buộc” bug xảy ra. Với HTTP client/server, request có thể xử lý đồng thời dù từng assertion bên trong là đồng bộ trên thread client riêng.

### 7.2. Vì sao StepVerifier không thay thế được HTTP integration test?

`StepVerifier` kiểm tra chính xác semantics của Reactor Context cho Publisher độc lập; nó không chứng minh Spring Security đã xác thực HTTP request, nạp đúng security filter hay mapping endpoint. `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` kiểm tra đường đi HTTP thực. Dùng cả hai cho hai tầng bằng chứng khác nhau.

Nếu dùng `WebTestClient.bindToController(...)` trực tiếp, security filter có thể không được cài vào test. Nếu dùng `@WebFluxTest`, kiểm tra security configuration/bean có được import đúng không. Tránh test mà mọi request đều truyền sẵn một `Authentication` được mock ở ngoài network nhưng sau đó kết luận HTTP authentication thực tế an toàn. Với `RANDOM_PORT`, gửi credential qua HTTP như code trên.

## 8. Bảo toàn identity qua các điểm bất đồng bộ và thread switch

| Trường hợp | Có thể làm gì | Điều phải tránh |
| --- | --- | --- |
| `map`, `flatMap`, `then`, `delay` trong cùng Reactor chain | Đọc `ReactiveSecurityContextHolder` hoặc mang tên user làm giá trị của nhánh | Ghi user vào singleton field rồi đọc sau delay |
| `publishOn`, `subscribeOn` với Reactor operator chuẩn | Reactor Context của subscriber vẫn đi theo chuỗi | Dựa vào tên thread để quyết định người dùng |
| `retry`, `repeat` | Kiểm tra danh tính/quyền theo subscription và thiết kế idempotency | Giả định chỉ có một lần thực thi hay một lần đọc context |
| `Flux.share()` / `Mono.cache()` / `Sinks.Many` | Chỉ chia sẻ dữ liệu không phụ thuộc danh tính hoặc phân vùng đúng | Cache/shared result mang principal của người đầu tiên |
| `CompletableFuture` / `ExecutorService` ngoài chuỗi | Truyền identity/tenant đã xác minh một cách tường minh, nếu cần | Mong `ReactiveSecurityContextHolder` hoặc ThreadLocal tự có mặt trong thread mới |
| HTTP client gọi dịch vụ khác (`WebClient`) | Chọn cách chuyển token/claims được tin cậy, có giới hạn phạm vi | Dùng lại Authorization header của request trước hoặc một global mutable token |
| Log correlation ID / tracing | Sử dụng Reactor Context và integration đúng cho MDC nếu cần | Lưu token/PII vào ThreadLocal rồi không cleanup |

Ví dụ **đúng về dữ liệu** khi gọi một dịch vụ bất đồng bộ không tự hỗ trợ Reactor Context:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .flatMap(username -> otherClient.fetchForUser(username));
```

Fragment này giả định `otherClient.fetchForUser(String)` là API **đã được thiết kế an toàn** và server bên kia không tin vào một username client tùy ý. Trong hệ thống thực, đừng coi username truyền đi là bằng chứng xác thực. Dịch vụ đích phải xác minh token có chữ ký/ủy quyền (hoặc dùng kênh nội bộ được bảo đảm), và phải kiểm tra quyền tài nguyên; tránh cơ chế “client tự khai mình là admin”.

### 8.1. ThreadLocal và MDC cho logging

Nhiều thư viện logging dùng MDC, vốn dựa trên `ThreadLocal`. Nếu log trước/sau `publishOn` mà thiếu cơ chế context propagation thích hợp, correlation ID có thể mất hoặc lọt sang tín hiệu khác. Có thể dùng tích hợp Micrometer Context Propagation và operator `tap`/`handle` hoặc automatic propagation theo phiên bản Reactor đang chạy; phải kiểm thử cấu hình cụ thể và làm sạch ThreadLocal đúng scope. Nhưng **MDC chỉ phục vụ quan sát**, không phải authority để truy cập dữ liệu. Tránh đưa password, token, đầy đủ PII hoặc raw `SecurityContext` vào log.

### 8.2. Cần phân biệt security context của request với tác vụ tồn tại lâu hơn

Khi request trả response hoặc bị cancel, không thể dựa vào context của request đó cho một background job kéo dài vô hạn. Một job có danh tính chủ thể “Alice đã tạo” không có nghĩa Alice vẫn còn quyền lúc job thực thi. Hãy truyền identity ID đã được xác thực, request ID và metadata tối thiểu; tại lúc job chạy, thực hiện authorization mới theo chính sách phù hợp và tránh dùng token hết hạn/chia sẻ token giữa jobs.

## 9. Đừng nhầm danh tính đúng với phân quyền dữ liệu đúng

Một service có thể đọc `alice` chính xác nhưng vẫn trả tài nguyên của Bob nếu truy vấn không lọc theo chủ sở hữu. Vì vậy bảo vệ chống rò rỉ có hai lớp:

1. **Bảo toàn principal:** mỗi subscription đọc đúng `Authentication` của request.
2. **Cưỡng chế quyền trên tài nguyên:** truy vấn/tầng nghiệp vụ dùng principal và tenant để giới hạn tài nguyên, không chỉ dựa vào endpoint `authenticated()`.

Ví dụ fragment trong service đã có repository được thiết kế cho truy cập theo owner:

```java
Mono<Report> myReport(String reportId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(username ->
            repository.findByIdAndOwnerUsername(reportId, username))
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND)));
}
```

Cần import `Report`, `repository`, `HttpStatus` và `ResponseStatusException` trong ứng dụng cụ thể; đây không phải file Java tự chạy. Phương thức giả định repository lọc owner **tại nguồn dữ liệu**. Nếu có multi-tenancy, áp thêm tenant ID và quyền quản trị đúng ngữ cảnh; đừng chỉ tìm `findById(reportId)` rồi tin rằng endpoint đã xác thực là đủ. Có thể dùng `@EnableReactiveMethodSecurity`/`@PreAuthorize` như lớp phụ trợ khi gọi qua Spring proxy, nhưng phương pháp đó không tự thay thế kiểm tra quyền cấp bản ghi.

### 9.1. Tránh đặt cả SecurityContext vào cache

`Authentication` có thể chứa authorities, credentials và details. Lưu trữ hoặc logging toàn bộ object làm tăng nguy cơ lộ dữ liệu; auth state cũng có thể thay đổi khi quyền bị thu hồi. Dữ liệu cache nên có key rõ ràng, TTL, invalidation và chủ sở hữu; chỉ giữ các trường thật sự cần. Không dùng một `Mono<Authentication>` global để “tối ưu đọc principal”.

### 9.2. Session/cookie và token trên client

Hai tab trình duyệt cùng một session cookie hợp lệ có thể **cùng là một người** theo thiết kế; đây không phải bằng chứng Spring đã trộn Reactor Context. Ngược lại, một test dùng chung cookie session giữa hai tài khoản có thể gây false positive. Khi đo cách ly, tạo client/session độc lập hoặc dùng HTTP Basic/token riêng cho mỗi request; ghi rõ authentication scheme và lifetime của credentials.

Đối với tài khoản dùng chung (service account), khác biệt principal có thể không phản ánh identity của người cuối. Cần định nghĩa rõ danh tính cần bảo vệ: user, tenant, service principal, delegated authorization hay cả chuỗi delegation. Không chấp nhận một `X-User` tùy ý làm chứng cứ.

## 10. Dấu hiệu nhận biết và quy trình tìm lỗi

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Alice nhận body có tên Bob, cả hai đều `200` | Mutable field, `static`, cached Publisher, context bridge sai | Thêm test đồng thời theo từng principal; tìm nơi lưu `Authentication`/username trong singleton |
| Khi đổi thread, principal là `null` | Dựa vào `ThreadLocal` thay vì Reactor Context | Đọc bằng `ReactiveSecurityContextHolder` trong pipeline; xem điểm tách async |
| Chỉ hỏng khi request chạy song song | Race condition trong state dùng chung | Lặp lại test Alice/Bob, tạo độ trễ có kiểm soát; kiểm tra bean scope và cache |
| Sau user A, user B luôn thấy A | `Mono.cache()` hoặc cache key thiếu user/tenant | Kiểm tra lifetime của cached Publisher và partition dữ liệu |
| Request có header `X-User` điều khiển dữ liệu | Tin header do client gửi | Bỏ trust header hoặc ràng buộc với gateway xác thực, kiểm chứng token |
| API trả `401` khi pipeline async | Subscription tách không có context hoặc credential sai | Xem security filter, kết nối Reactor chain, request credential và lỗi thực |
| Đúng username nhưng truy cập sai bản ghi | Truy vấn thiếu điều kiện owner/tenant | Test truy cập chéo tài nguyên, thêm kiểm tra owner tại repository |
| Trace/MDC đôi lúc hiện username của request khác | Context propagation/cleanup ThreadLocal sai | Không dùng MDC làm quyền; kiểm tra accessor, phạm vi cleanup, log redaction |

Các bước điều tra hiệu quả:

1. Tái hiện bằng **hai danh tính riêng** và một endpoint trả về identity được Spring Security cung cấp; bắt đầu với request tuần tự.
2. Thêm delay hoặc scheduler switch trong chính Reactor pipeline, chạy các request xen kẽ. Ghi **request ID** độc lập (không phải token) để nối log theo request.
3. Mở rộng test thành concurrency test với assertion chính xác cả principal và dữ liệu. Dùng `WebTestClient` qua security filter, không gọi trực tiếp method của controller.
4. Rà soát singleton fields, `static`, ThreadLocal, `Mono.cache`, shared/hot Publisher, async callback, event sink, request/session scope và interceptor đọc identity.
5. Truy đường đi auth: credential → Spring Security authentication → Reactor Context → controller/service → truy vấn dữ liệu → response. Kiểm tra chốt cấp quyền ở từng boundary.
6. Nếu cần truyền identity sang API/queue khác, định nghĩa hợp đồng tin cậy và authorization mới; không truyền nguyên mutable `SecurityContext` một cách tùy tiện.
7. Đảm bảo test âm luôn tồn tại: anonymous không vào protected resource, sai credential bị từ chối, user A không nhận response/dữ liệu của B, header giả mạo không đổi principal.

## 11. Những nhầm lẫn phổ biến

**“Mỗi request trong WebFlux có thread riêng.”** Không. Event-loop thread được dùng chung và tín hiệu có thể được xử lý xen kẽ.

**“Dùng volatile String currentUser là đủ thread-safe.”** Không. `volatile` không cung cấp isolation theo request.

**“Reactor Context là một HashMap toàn cục.”** Không. Context bất biến và gắn với subscriber; `contextWrite` tác động lên phạm vi operator upstream của subscription đó.

**“Chỉ cần @PreAuthorize là không thể lộ dữ liệu người khác.”** Không. Method security còn tùy đường gọi qua proxy và policy. Truy vấn dữ liệu cần bảo vệ ở cấp owner/tenant; một biến username sai hoặc cache chung vẫn nguy hiểm.

**“Đổi scheduler thì chắc chắn mất security context.”** Không với operator Reactor chuẩn trong cùng chain. Nguy cơ lớn hơn là **tách khỏi chain**, đọc ThreadLocal hoặc dùng thư viện cần context bridge mà chưa cấu hình.

**“WebTestClient trả 200 nghĩa là không rò rỉ.”** Không. Phải đối chiếu body với danh tính/tenant thực của **từng request**.

**“Cache kết quả của Mono.getContext() sẽ giúp tối ưu.”** Rất nguy hiểm nếu cache dùng chung: subscriber đầu tiên có thể quyết định giá trị phát lại cho tất cả subscriber sau.

**“Hai tab browser hiển thị cùng user là bug concurrency.”** Có thể chỉ là hai tab dùng cùng cookie/session hoặc cache credentials. Xác định danh tính được trình duyệt gửi thực tế trước khi kết luận.

**“Có thể cho request chọn Authentication bằng contextWrite(withAuthentication(...)).”** Không. API này chỉ thích hợp ở nơi server/test đã **tin cậy** identity. Chấp nhận principal do client tự khai là lỗ hổng giả mạo danh tính.

## 12. Câu hỏi tự kiểm tra

**Câu 1:** Alice và Bob gửi request đồng thời trên cùng event-loop thread. Đặt tên user trong `ThreadLocal` có đảm bảo cách ly không?  
**Không.** Một thread có thể phục vụ hai request; dùng Reactor Context của subscriber và tránh lưu state dùng chung.

**Câu 2:** Vì sao `Mono.delay(...).then(identityService.current("later"))` trong ví dụ vẫn đọc đúng principal?  
Vì các operator nằm trong cùng subscription và `ReactiveSecurityContextHolder` đọc context tương ứng; `Mono.defer` cho phép việc đọc diễn ra lúc subscribe.

**Câu 3:** Trong ví dụ singleton có `Mono<String> cached = getContext().map(...).cache()`, vì sao Bob có thể thấy Alice?  
Vì `cache` phát lại kết quả của lần subscribe đầu cho subscriber sau, không phân vùng theo principal.

**Câu 4:** Bộ test nhiều request song song chỉ xác nhận `isOk()` có đủ không?  
**Không.** Cần xác nhận body/tài nguyên tương ứng với credential của **từng** request, đồng thời test trường hợp sai quyền.

**Câu 5:** Nếu user A đọc đúng Authentication nhưng vẫn xem được report của B, lỗi nằm ở đâu?  
Có thể ở policy/logic truy vấn quyền trên tài nguyên, ví dụ repository thiếu lọc theo owner/tenant; cần bảo vệ cấp dữ liệu ngoài cách ly security context.

**Câu 6:** Một background job cần ghi nhận người khởi tạo. Có nên giữ mãi `ReactiveSecurityContextHolder` của request?  
**Không.** Truyền danh tính đã xác minh và metadata tối thiểu trong hợp đồng job, kiểm tra ủy quyền tại thời điểm thực thi theo chính sách phù hợp.

### Tài liệu tham khảo chính thức

- Spring Security, *Reactive Method Security* (Reactor Context và `ReactiveSecurityContextHolder`): https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Reactor, *Adding a Context to a Reactive Sequence*: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor, *Context-Propagation Support*: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Spring Framework, *Testing with WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Boot, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Điều quan trọng nhất:** Giữ `SecurityContext` ở **Reactor Context của subscription**, đọc bằng `ReactiveSecurityContextHolder` trong đúng pipeline, không lưu principal trong state dùng chung, không chia sẻ cache chứa dữ liệu theo người dùng, và kiểm thử đồng thời bằng nhiều danh tính với assertion trên **chính dữ liệu được trả về**. Như vậy, sự xen kẽ của thread không tự biến thành rò rỉ danh tính giữa các request.