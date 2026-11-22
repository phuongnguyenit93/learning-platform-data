# Điều kiện kiểu trả về Publisher khi áp dụng bảo mật phương thức reactive

**Chủ đề:** Spring Security – reactive · **Phần:** Phân quyền phương thức  
**Trọng tâm:** Điều kiện return type `org.reactivestreams.Publisher` của phương thức Java được bảo vệ bằng `@PreAuthorize`, cách Spring Security dùng Reactor Context, và những sai lầm dù code có vẻ bất đồng bộ.

Khi bảo vệ một endpoint bằng `authorizeExchange`, Spring Security kiểm tra quyền lúc HTTP request đi qua chuỗi filter. Với một service có thể được gọi từ nhiều nơi, ta còn cần **bảo mật phương thức**: đặt điều kiện quyền ngay trên method được Spring quản lý. Ví dụ:

```java
@PreAuthorize("hasRole('READER')")
public Mono<String> read(String id) {
    return repository.findById(id).map(Document::content);
}
```

Đây là fragment, không phải file Java độc lập. Điểm quyết định: phương thức trả `Mono<String>`, mà `Mono` thực thi `org.reactivestreams.Publisher`. Spring Security Reactive dựa vào cơ chế Publisher và **Reactor Context gắn với subscription** để đọc `Authentication` và áp dụng `@PreAuthorize` đúng thời điểm.

**Quy tắc chính:** Với phương thức Java dùng reactive method security trong Spring WebFlux, khai báo kiểu trả về thuộc `Publisher<T>` — thường là `Mono<T>`, `Flux<T>` hoặc `Mono<Void>`. **Không** dựa vào một annotation `@PreAuthorize` gắn trên method trả `String`, `List<T>`, `void` hay `CompletableFuture<T>` rồi mặc định nó được intercept đúng cách. Các kiểu đó không tuân hợp đồng Publisher của reactive method security. Tùy phiên bản, lỗi có thể được phát ra khi gọi/subscribe; đừng xem việc chương trình vẫn chạy là bằng chứng an toàn.

Một ngoại lệ có chủ đích: cơ chế `AuthorizationManager` ở Spring Security mới có **hỗ trợ Kotlin coroutines/suspend functions** theo tài liệu. Đây là tích hợp coroutine riêng, không có nghĩa tất cả Java Future hoặc method đồng bộ tự động được chấp nhận.

## 1. Vì sao Publisher là điều kiện quan trọng?

Trong WebFlux, request A và B có thể được xử lý xen kẽ trên cùng event-loop thread; tín hiệu của một request cũng có thể chuyển scheduler sau một lời gọi I/O hoặc `Mono.delay`. Do đó Spring Security Reactive không thể dựa vào ý tưởng “mỗi request có một ThreadLocal user”.

`ReactiveSecurityContextHolder` đọc `SecurityContext` từ Reactor `Context` của **subscriber**:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

Đây là fragment. Method security cần kết nối kiểm tra authorization với **chuỗi Publisher** đang mang context đó. Khi method trả `Mono` hoặc `Flux`, interceptor có thể gắn quyết định truy cập vào pipeline. Với method Java trả thẳng `String` hoặc `void`, không có Publisher của method để phối hợp subscription theo cách mà tài liệu reactive method security yêu cầu.

```text
HTTP / service caller
        |
        v
Spring AOP proxy của @Service
        |
        v
method có @PreAuthorize(...)
        |
        v
Publisher được bao quanh bởi reactive authorization
        |
        v
subscriber + Reactor Context có Authentication
        |
        +--> thiếu quyền -> AccessDeniedException / onError
        |
        +--> đủ quyền  -> thực thi nguồn Mono/Flux
                            |
                            v
                       onNext/onComplete
```

Sơ đồ mô tả *ý nghĩa logic*, không cam kết một thứ tự Java call/bytecode cụ thể ở mọi phiên bản. Điểm cần giữ là **công việc nhạy cảm phải nằm trong pipeline và chỉ xảy ra sau khi được phép**, thay vì chạy eager trước khi pipeline có subscriber.

### 1.1. Bảng nhận diện return type

| Return type ở method Java được annotated | Có phải Publisher? | Hướng xử lý |
| --- | --- | --- |
| `Mono<User>` | Có | Phù hợp cho một kết quả async |
| `Flux<User>` | Có | Phù hợp cho nhiều kết quả hoặc stream |
| `Mono<Void>` | Có | Phù hợp thao tác chỉ báo completion/error |
| `Publisher<User>` | Có | Hợp đồng chung; trong ứng dụng Reactor nên chọn Mono/Flux cho rõ |
| `Mono<ResponseEntity<String>>` | Có | Khi method cần HTTP response wrapper bất đồng bộ |
| `ResponseEntity<String>` | Không | Không phải boundary Publisher |
| `String`, `User`, `List<User>` | Không | Kết quả đồng bộ; không dùng làm return type của reactive secured method |
| `void` | Không | Đổi sang `Mono<Void>` nếu method cần được bảo vệ reactive |
| `CompletableFuture<User>` | Không | Cần bridge trì hoãn thành `Mono<User>` tại boundary method |
| `CompletionStage<User>` | Không | Bất đồng bộ không đồng nghĩa Reactive Streams |
| Kotlin `suspend fun` | Trường hợp đặc biệt | Kiểm tra Spring Security version, integration coroutine và proxy |

**Phân biệt:** Một controller WebFlux **có thể** trả đối tượng Java thường và WebFlux xử lý HTTP thành công; yêu cầu Publisher trong bài này nói về **method Java được bảo vệ bằng reactive method security**. Không suy luận rằng mọi utility/private function trong một dự án WebFlux bắt buộc trả `Mono`.

### 1.2. Publisher không đồng nghĩa chạy thread riêng

`Mono.just("hello")` vẫn có thể chạy synchronous trên thread subscribe. `Flux` không tự tạo concurrency. `Mono.delay` và `publishOn` có thể đổi lịch chạy nhưng Reactor Context vẫn gắn với subscriber của pipeline thông thường. Bảo mật nằm ở đúng context, không phụ thuộc tên thread hay số thread.

## 2. Bật method security đúng API của WebFlux

Spring Boot starter Security **không tự bật** annotation-based method authorization chỉ bằng việc có dependency. Spring Security 6.x dùng cấu hình:

```java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfig {
    // @Bean SecurityWebFilterChain, user store...
}
```

Đoạn trên là fragment; phần 7 có project hoàn chỉnh. `@EnableReactiveMethodSecurity` ở Spring Security 6.x mặc định sử dụng cơ chế `AuthorizationManager`; với các bản 5.x cũ, tài liệu có thể nhắc `useAuthorizationManager=true`. Không copy tùy chọn legacy mà không kiểm version.

Phân biệt ba annotation:

- `@EnableWebFluxSecurity` bật filter bảo mật WebFlux/HTTP.
- `@EnableReactiveMethodSecurity` bật interceptor bảo mật **method reactive**.
- `@EnableMethodSecurity` là cấu hình method security thông dụng trong stack đồng bộ/Servlet; không thay thế tự động cấu hình reactive khi bạn cần Reactor Context.

Sau đó đặt `@PreAuthorize("hasRole('READER')")` trên **public method** của service được Spring quản lý. Spring AOP proxy phải là đường đi thực của caller. `@PreAuthorize` không phải quyền từ HTTP header tùy ý: expression sẽ đọc `Authentication` đáng tin đã được Spring Security thiết lập.

### 2.1. Tách HTTP policy khỏi method policy

Một thiết kế rõ ràng:

```java
// Ở SecurityWebFilterChain:
.authorizeExchange(ex -> ex
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll())

// Ở service:
@PreAuthorize("hasRole('ADMIN')")
public Flux<String> auditEvents() { ... }
```

Đây là hai fragment minh họa, không phải file Java biên dịch độc lập. HTTP policy nói **người gọi phải đăng nhập**; method policy nói **phải có ROLE_ADMIN**. Nếu service có thêm entry point ngoài HTTP, method rule vẫn có vai trò. Nếu chỉ test API trả 401 khi không có credential, ta chưa chứng minh `@PreAuthorize` có hoạt động — vì request có thể đã bị chặn ở HTTP layer.

## 3. Viết các kiểu Publisher đúng mục đích

### 3.1. Mono<T>: một kết quả

```java
@PreAuthorize("hasRole('READER')")
public Mono<Report> report(String id) {
    return reportRepository.findById(id);
}
```

Đây là fragment giả định có `Report` và `reportRepository`. `Mono` biểu thị không có/đúng một result. Cần bổ sung quyền theo owner/tenant; role READER không tự cho xem mọi report.

### 3.2. Flux<T>: nhiều phần tử

```java
@PreAuthorize("hasAuthority('audit:read')")
public Flux<AuditRecord> auditHistory() {
    return auditRepository.findRecent();
}
```

`Flux` là Publisher phát nhiều tín hiệu. Chỉ cho phép gọi method không tự lọc từng bản ghi theo owner. Nếu stream nhiều tenant, repository/policy dữ liệu phải kiểm soát nguồn dữ liệu chứ không dựa đơn thuần vào role.

### 3.3. Mono<Void>: thao tác không trả body

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Void> deleteRecord(String id) {
    return reactiveRepository.deleteById(id);
}
```

Đổi sang `void` rồi gọi `deleteById(id).subscribe()` **không** phải cách tương đương: nó tách tác vụ khỏi pipeline và quyền. `Mono<Void>` thể hiện completion/error; controller WebFlux có thể chờ để phản hồi đúng. Với tác vụ ghi phải bảo vệ owner/tenant, transaction, idempotency và chỉ ghi sau authorization.

### 3.4. Khi method cần HTTP status

Một phương thức được annotate có thể trả `Mono<ResponseEntity<DTO>>` nếu thực sự cần wrapper HTTP:

```java
@PreAuthorize("hasRole('READER')")
public Mono<ResponseEntity<String>> preview(String id) {
    return service.loadText(id).map(ResponseEntity::ok);
}
```

Đoạn trên là fragment. `Mono<ResponseEntity<String>>` là Publisher; `ResponseEntity<String>` thuần thì không. Thường nên đặt method security ở service nghiệp vụ và để controller xử lý mapping status, nhằm tái sử dụng service từ nhiều entry point.

## 4. Chọn thời điểm thực thi: assembly không phải subscription

Điểm có rủi ro nhất là **method trả Mono nhưng đã làm việc nhạy cảm trước khi trả**.

### 4.1. Sai: side effect eager

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Void> deleteNow(String id) {
    legacyDeleteBlocking(id);  // có thể chạy ngay khi method target bị gọi
    return Mono.empty();
}
```

Đây là *mẫu anti-pattern*. Dù return type là `Mono<Void>`, lời gọi `legacyDeleteBlocking` không phải một operator deferred của Publisher. Việc proxy có thể trì hoãn một số bước trong các phiên bản không phải lý do để dựa vào side effect xảy ra trước publisher subscription. Tránh side effect ngoài luồng đã được bảo vệ, và đặc biệt tránh blocking trên Netty event-loop.

### 4.2. Đúng: trì hoãn nguồn reactive

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Void> deleteAfterAuthorization(String id) {
    return Mono.defer(() -> reactiveRepository.deleteById(id));
}
```

`Mono.defer` chỉ tạo publisher con lúc subscribe. Nếu repository bản thân reactive/cold, có thể return trực tiếp `reactiveRepository.deleteById(id)`, nhưng `defer` làm ranh giới tạo nguồn rõ hơn khi có logic khởi tạo.

### 4.3. Blocking legacy là trường hợp cần cô lập

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Void> deleteLegacy(String id) {
    return Mono.fromRunnable(() -> legacyDeleteBlocking(id))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
}
```

Đây là fragment cần import/implementation của `Schedulers` và `legacyDeleteBlocking`; dùng như **cầu nối tạm thời** trong hệ thống legacy, không phải phương án tối ưu mãi mãi. Không dùng `Mono.just(blockingRepository.load(id))`: Java tính giá trị đối số **trước** khi `Mono.just` được tạo, do đó blocking I/O đã chạy ở assembly. Khi có thể, dùng R2DBC/reactive driver hoặc thư viện không chặn event-loop.

### 4.4. Future không tự trở thành Publisher

`CompletableFuture<T>` không implement `org.reactivestreams.Publisher`. Nếu có thư viện ngoài trả future, method được annotated nên chuyển ở **bên trong boundary reactive**:

```java
@PreAuthorize("hasRole('READER')")
public Mono<String> export(String id) {
    return Mono.fromFuture(() -> externalClient.exportAsync(id));
}
```

Đây là fragment của Reactor có overload nhận Supplier. Khác biệt với `Mono.fromFuture(alreadyStartedFuture)`: việc tạo future trong Supplier có thể được trì hoãn tới subscription. Phải kiểm soát cancellation, timeout, retry và idempotency; hủy future không bảo đảm tác vụ bên thứ ba được rollback.

**Các anti-pattern không đáp ứng hợp đồng Publisher:**

```java
@PreAuthorize("hasRole('ADMIN')")
public String exportNow() {
    return costlyExport();
}

@PreAuthorize("hasRole('ADMIN')")
public void clearCache() {
    clearSensitiveCache();
}

@PreAuthorize("hasRole('ADMIN')")
public CompletableFuture<String> exportAsync() {
    return CompletableFuture.supplyAsync(this::costlyExport);
}
```

Đây là **mẫu sai cần sửa**, không phải những function bạn nên đưa vào dự án chạy. Spring Security reactive method interceptors không hứa hỗ trợ trực tiếp các kiểu return này. Dùng `Mono<String>`, `Mono<Void>` và nguồn deferred tương ứng khi cần làm method security boundary.

## 5. Spring AOP proxy là điều kiện quan trọng thứ hai

Một return type đúng chỉ là điều kiện **cần**, chưa đủ. Bảo mật phương thức reactive của Spring dùng **AOP interception**. Các điều kiện thực tế:

1. **Bean Spring-managed:** lớp `@Service` được Spring tạo và inject. Nếu controller tự gọi `new DocumentService()`, không có proxy security.
2. **External invocation qua proxy:** lời gọi `documentService.read(...)` từ controller/bean khác đi qua proxy. `this.read(...)` bên trong chính class là *self-invocation*; với Spring AOP proxy thông dụng, nó không được advice lại.
3. **Khả năng proxy:** public method, không final, class/interface thích hợp. `private` và `final` có hạn chế theo proxy strategy.
4. **Đúng annotation và dependency:** phải có `@EnableReactiveMethodSecurity`, config thuộc WebFlux, không chỉ HTTP security.
5. **Không tách subscribe:** không gọi `subscribe()` thủ công trong controller rồi return một `Mono.just("accepted")` khác.
6. **Test đường vào thực:** ít nhất một negative test dùng Spring-injected bean hay HTTP thật và expect error/403 khi thiếu role.

Ví dụ self-invocation rủi ro:

```java
@Service
class IncorrectFacade {
    public Mono<String> callInternal(String id) {
        return guarded(id); // lời gọi nội bộ trên this
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> guarded(String id) {
        return Mono.just("secret:" + id);
    }
}
```

Đây là fragment cố ý sai kiến trúc. Khi caller gọi `callInternal` qua proxy, `guarded` bên trong **không tự động được proxy lại**. Sửa bằng cách đặt annotation ở `callInternal`, hoặc di chuyển `guarded` sang một bean thứ hai do Spring inject và gọi qua bean đó. Test riêng đường gọi gián tiếp.

## 6. Ví dụ Java 17+ Spring Boot WebFlux hoàn chỉnh

Bài thực hành sử dụng HTTP Basic để tránh trộn chủ đề với UI login. Chỉ mục tiêu method security:

- `GET /public/ping` là public → `200 pong`.
- Anonymous `GET /api/documents/R7` → `401` do HTTP `authenticated()`.
- User `reader`, role `ROLE_READER`, gọi `/api/documents/R7` → `200 document:R7:reader`.
- User `admin`, role `ROLE_ADMIN`, gọi **cùng URL** → `403` bởi `@PreAuthorize("hasRole('READER')")`.
- User `reader` gọi `/api/audit` → `403` bởi `@PreAuthorize("hasRole('ADMIN')")` trên một `Flux`.
- User `admin` gọi `/api/audit` → `200` và JSON array có hai phần tử.

Hai user chỉ có **một role riêng biệt**, giúp test role âm thực sự phát hiện method security chưa hoạt động.

### 6.1. Cấu trúc và pom.xml

```text
reactive-method-publisher/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/method/
    │   │   ├── MethodSecurityApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DocumentService.java
    │   │   └── DocumentController.java
    │   └── resources/application.properties
    └── test/java/demo/method/
        └── MethodSecurityTests.java
```

Ví dụ sử dụng JDK 17+ và Spring Boot **3.5.7** để minh họa một cấu hình nhất quán với Spring Security 6.5.x. Trong ứng dụng thật, cập nhật lên phiên bản còn được hỗ trợ với các bản vá theo chính sách dự án.

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
    <artifactId>reactive-method-publisher</artifactId>
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

Không thêm `spring-boot-starter-web` (Servlet MVC) cho bài WebFlux. Không cần database, Docker hay account bên ngoài. Các password chỉ phục vụ thử nghiệm trên localhost; không dùng lại trong sản phẩm thực.

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-method-publisher
server.port=8080
```

### 6.2. Application entry point

`src/main/java/demo/method/MethodSecurityApplication.java`:

```java
package demo.method;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityApplication.class, args);
    }
}
```

### 6.3. SecurityConfig: URL authentication, method authorization

`src/main/java/demo/method/SecurityConfig.java`:

```java
package demo.method;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
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
@EnableReactiveMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader123"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/**").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }
}
```

Giải thích:

- HTTP `/api/**` chỉ yêu cầu `authenticated()`; **không có rule role tại HTTP**. Nếu method security tắt, nhiều URL sẽ vẫn cho phép user đã login bất kỳ.
- `@EnableReactiveMethodSecurity` kích hoạt việc đọc annotation trên Spring beans.
- `PasswordEncoderFactories` băm password demo bằng encoder delegating với BCrypt; không lưu `{noop}` plaintext.
- `formLogin` tắt cho API minh họa để quan sát HTTP Basic 401/403; trong ứng dụng thật có thể dùng session/OAuth2 nhưng yêu cầu Publisher vẫn là trọng tâm.
- `anyExchange().denyAll()` không cho route mới tự mở.

### 6.4. Service: Mono và Flux thực sự được bảo vệ

`src/main/java/demo/method/DocumentService.java`:

```java
package demo.method;

import java.time.Duration;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    @PreAuthorize("hasRole('READER')")
    public Mono<String> read(String id) {
        return Mono.delay(Duration.ofMillis(10))
            .then(ReactiveSecurityContextHolder.getContext())
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "document:" + id + ":" + name);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Flux<String> audit() {
        return Flux.just("audit-open", "audit-close")
            .delayElements(Duration.ofMillis(5));
    }
}
```

`Mono.delay`/`delayElements` minh họa thời điểm phát tín hiệu khác lúc gọi Java method. `ReactiveSecurityContextHolder` vẫn đọc Context của subscriber. Cả hai method `public` thuộc bean `@Service` và được controller gọi qua dependency injection, tạo điều kiện để AOP proxy chạy.

### 6.5. Controller nối các Publisher vào HTTP

`src/main/java/demo/method/DocumentController.java`:

```java
package demo.method;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {
    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(value = "/api/documents/{id}",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> read(@PathVariable String id) {
        return documents.read(id);
    }

    @GetMapping(value = "/api/audit",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<String> audit() {
        return documents.audit();
    }
}
```

Không gọi `new DocumentService()`, `documents.read(id).block()` hay `documents.audit().subscribe()`. Controller trả Publisher để WebFlux quản lý subscription, Reactor Context và HTTP response. Nếu cần status 404, map `Mono.empty()`/domain error ở HTTP boundary thay vì biến service method annotated thành synchronous `ResponseEntity`.

## 7. Chạy và kiểm tra bằng curl

Tại thư mục project có `pom.xml`:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Mở terminal khác:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/R7
curl -i --user reader:reader123 http://localhost:8080/api/documents/R7
curl -i --user admin:admin123 http://localhost:8080/api/documents/R7
curl -i --user reader:reader123 http://localhost:8080/api/audit
curl -i --user admin:admin123 http://localhost:8080/api/audit
```

Kết quả kỳ vọng:

| Request | Status | Nội dung/ý nghĩa |
| --- | --- | --- |
| Public anonymous | 200 | `pong` |
| Anonymous document | 401 | Bị URL policy `authenticated()` từ chối |
| Reader document | 200 | `document:R7:reader` |
| Admin document | 403 | HTTP đã xác thực nhưng thiếu role READER ở method |
| Reader audit | 403 | Method trả Flux yêu cầu role ADMIN |
| Admin audit | 200 | JSON list chứa `audit-open` và `audit-close` |

Các body/message lỗi có thể phụ thuộc handler. Cặp test admin/document và reader/audit là **negative role tests** thiết yếu: nếu method security không được enable hoặc gọi lệch AOP proxy, chúng có thể nhận 200 dù HTTP authentication vẫn hoạt động.

Trên PowerShell, hãy dùng `curl.exe` nếu `curl` bị alias. Basic dùng Base64, không mã hóa đường truyền; ngoài localhost luôn cần HTTPS và không đưa credential thật vào log/shell history.

## 8. WebTestClient + StepVerifier: kiểm chứng Publisher và quyền

`@SpringBootTest(webEnvironment = RANDOM_PORT)` tạo server thật trên cổng ngẫu nhiên. `WebTestClient` đi qua HTTP filters, còn `StepVerifier` kiểm tra Publisher của **Spring-injected service bean** dưới một `Authentication` trong Reactor Context test.

`src/test/java/demo/method/MethodSecurityTests.java`:

```java
package demo.method;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MethodSecurityTests {

    @Autowired
    WebTestClient client;

    @Autowired
    DocumentService documents;

    @Test
    void publicPingWorksWithoutLogin() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousDocumentGets401() {
        client.get().uri("/api/documents/R7")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerReceivesAuthorizedMonoValue() {
        client.get().uri("/api/documents/R7")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("document:R7:reader");
    }

    @Test
    void adminWithoutReaderRoleGets403ForMono() {
        client.get().uri("/api/documents/R7")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void readerGets403ForAdminFlux() {
        client.get().uri("/api/audit")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminReceivesBothFluxValues() {
        client.get().uri("/api/audit")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(String.class)
            .hasSize(2)
            .contains("audit-open", "audit-close");
    }

    @Test
    void directServiceProxySeesReaderContextAtSubscription() {
        Authentication reader = new TestingAuthenticationToken(
            "reader", "unused", "ROLE_READER");

        StepVerifier.create(
                documents.read("R8")
                    .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(reader)))
            .expectNext("document:R8:reader")
            .verifyComplete();
    }

    @Test
    void directServiceProxyRejectsMissingReaderRole() {
        Authentication admin = new TestingAuthenticationToken(
            "admin", "unused", "ROLE_ADMIN");

        StepVerifier.create(
                documents.read("R8")
                    .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(admin)))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
```

Chạy:

```bash
mvn test
```

Nếu chỉ có class test trên, mục tiêu là **8 test pass** khi môi trường JDK/Maven/dependencies đúng. Đây là code mẫu để người học tự chạy; **không khẳng định đã thực thi test trong dự án của người đọc**. Nếu một version thay đổi exception subtype, đối chiếu actual exception: Spring Security có các loại thuộc họ `AccessDeniedException` và `AuthorizationDeniedException`; không đổi test sang chấp nhận mọi exception tùy tiện.

### 8.1. Ý nghĩa của từng nhóm test

- Test anonymous 401 chứng minh **HTTP layer** yêu cầu authentication, chưa chứng minh annotation hoạt động.
- Test reader Mono 200 chứng minh một Publisher được xử lý thành công và principal đúng.
- Test admin Mono 403/reader Flux 403 chứng minh **method-level role policy** thực sự có hiệu lực, vì HTTP chỉ yêu cầu authenticated.
- Test admin Flux 200 kiểm tra cả HTTP body JSON chứa đúng hai giá trị.
- Direct `StepVerifier` test gọi **Spring-injected proxy** và thêm `Authentication` bằng `contextWrite`. Nếu dùng `new DocumentService()`, sẽ không có AOP; nếu dùng context không gắn với subscription đúng, test sẽ sai.
- `withAuthentication` ở test là dữ liệu được harness tin cậy để tạo Reactor Context. Không cho HTTP client được tự gắn role bằng header `X-Role` trong production.

### 8.2. Kiểm tra side effect bị chặn

Nếu method của dự án ghi database hoặc gọi API bên ngoài, bổ sung test: khi người thiếu quyền subscribe vào method, Publisher phát access-denied signal **và database/side effect không thay đổi**. Chỉ kiểm tra 403 chưa đủ nếu code làm việc eager trước khi method trả Publisher. Với Flux theo user, thêm test kiểm tra không có record thuộc tenant khác, không chỉ status 200.

## 9. Bảo vệ dữ liệu khi Publisher hợp lệ

`@PreAuthorize("hasRole('READER')")` là chính sách vai trò, **không** tự lọc từng tài nguyên theo owner hoặc tenant. Ví dụ `findById(id)` có thể trả báo cáo của người khác dù caller đủ role. Cần đưa danh tính đã xác thực vào truy vấn:

```java
@PreAuthorize("hasRole('READER')")
public Mono<Report> readMine(String id) {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .flatMap(username ->
            reports.findByIdAndOwnerUsername(id, username));
}
```

Đây là fragment giả định có `Report` và repository `reports`, không phải file Java độc lập. Repository phải **thật sự lọc owner tại nguồn dữ liệu** và kiểm tra tenant ID nếu có multi-tenancy. Đừng tin ownerId do client gửi trừ khi policy đã đối chiếu với Authentication đáng tin.

### 9.1. Quyết định quyền bất đồng bộ bằng Mono<Boolean>

Spring Security với `AuthorizationManager` hỗ trợ custom method authorization expression/bean có thể trả `Boolean` hoặc `Mono<Boolean>` theo tài liệu 6.5. Đây là **return type của quyết định quyền**, khác với return type của method được bảo vệ.

```java
@Component("reportPolicy")
class ReportPolicy {
    public Mono<Boolean> canRead(String id) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .flatMap(user -> permissionRepository.isAllowed(user, id))
            .defaultIfEmpty(false);
    }
}

@Service
class ReportService {
    @PreAuthorize("@reportPolicy.canRead(#id)")
    public Mono<Report> read(String id) {
        return reportRepository.findById(id);
    }
}
```

Đây là **fragment** cần `permissionRepository`, `reportRepository`, kiểu `Report` và import/bean thích hợp. `isAllowed` phải trả `Mono<Boolean>` và không block. Nếu thiếu Authentication, policy mặc định false. Mẫu để expression chính là kết quả async; cách phối hợp với nhiều toán tử boolean SpEL khác cần kiểm chứng theo phiên bản.

### 9.2. PostAuthorize không thay thế chốt trước side effect

`@PreAuthorize` hữu ích khi cần chặn **trước hành động**. `@PostAuthorize` xem kết quả sau khi method được gọi/Publisher có kết quả, tùy cơ chế interceptor; nếu pipeline đã ghi dữ liệu hoặc thanh toán, việc deny sau đó **không tự rollback** side effect. Với tài nguyên nhạy cảm, ưu tiên điều kiện quyền ở trước hoặc trong truy vấn, còn post-check là lớp bảo vệ bổ sung có test cụ thể.

### 9.3. Cache/Hot Publisher cũng có thể làm rò rỉ

`Mono.cache()` có thể phát lại kết quả của subscription đầu cho các subscriber sau; `Flux.share()` hay hot `Sinks` có thể chia sẻ tín hiệu. Nếu kết quả mang principal, tài khoản hoặc dữ liệu tenant, một cache singleton không phân vùng sẽ làm lộ thông tin dù method có annotation role hợp lệ. Phân vùng cache theo principal/tenant/tài nguyên và kiểm tra quyền với mỗi request; hoặc không cache kết quả nhạy cảm.

### 9.4. Retry, subscribe lần hai và Reactor Context

Một cold Publisher có thể thực thi lại khi subscribe nhiều lần, `retry` hoặc `repeat`. Mỗi subscription cần Context đúng, và các thao tác ghi phải có idempotency/transaction nếu cần. `Mono.delay` hoặc `publishOn` trong một Reactor chain bình thường không làm mất Context; nhưng khi tự tạo `CompletableFuture.supplyAsync` rồi đọc `ThreadLocal`, danh tính có thể không được truyền đúng. Không dùng `ThreadLocal currentUser` làm nguồn phân quyền reactive.

## 10. Lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| Method có `@PreAuthorize` nhưng trả `String` hoặc `void` | Sai return type contract | Đổi thành `Mono<T>` / `Mono<Void>` |
| Method trả `CompletableFuture` | Future không là Publisher | Dùng `Mono.fromFuture(Supplier)` và nguồn deferred |
| Role sai vẫn nhận 200 | Chưa bật annotation, self-invocation, không qua Spring proxy | Bật `@EnableReactiveMethodSecurity`, inject bean, test 403 |
| Unauthorized vẫn ghi DB | Side effect eager trước Publisher | Di chuyển vào `Mono.defer`/repository reactive, test side effects |
| Đổi thread bị mất username | Dùng ThreadLocal / tách pipeline | `ReactiveSecurityContextHolder` và Reactor Context |
| Test trực tiếp với `new Service()` được phép | Không có AOP proxy | Inject bean từ Spring vào test |
| Reader nhận bản ghi Bob | Role-only policy, truy vấn thiếu owner/tenant | Lọc dữ liệu ở repository, test truy cập chéo |
| Flux vô tình phát chung dữ liệu | Hot/cached Publisher theo singleton | Tách stream/cache theo user hoặc bỏ shared state |
| API chậm khi query | `Mono.just(blockingCall())` hoặc `block()` | Dùng I/O reactive, cô lập blocking khi bắt buộc |
| Đã login nhưng 403 | Method role/scope không đúng | Kiểm tra authorities/SpEL/proxy, không xóa policy tùy tiện |
| Lỗi 403 bị chuyển thành 200 rỗng | `onErrorResume` nuốt access-denied | Xử lý lỗi quyền có chủ đích ở boundary |
| Có `@PostAuthorize` nhưng vẫn chuyển tiền | Post-check không hoàn tác side effect | Dùng pre-authorization và transaction đúng |

### 10.1. Đừng sửa 403 bằng cách bỏ annotation

Nếu admin không có READER và bị 403 ở `/api/documents`, đó là phép thử minh họa có chủ ý. Thay `@PreAuthorize("hasRole('READER')")` bằng `permitAll` chỉ để test xanh sẽ phá chính sách. Phân biệt lỗi cấu hình với yêu cầu quyền thực tế của sản phẩm.

### 10.2. Đừng dùng onErrorResume bừa bãi

`onErrorResume(Throwable.class, e -> Mono.empty())` có thể nuốt `AccessDeniedException`, khiến client tưởng không có dữ liệu thay vì bị từ chối. Cần quản lý mã 403, log metadata an toàn và phân biệt lỗi authorization với 404/not found, I/O failure hay input invalid.

### 10.3. Đừng coi annotation thay cho test

Một annotation có thể tồn tại trên code nhưng Spring AOP không intercept do self-invocation, method final, class không phải bean hoặc config chưa bật. Negative tests với role sai là phép kiểm tra bắt buộc để chứng minh rule đang được thực thi.

## 11. Các trường hợp đặc biệt và giới hạn

**Kotlin coroutines:** Spring Security mới với AuthorizationManager có hỗ trợ `suspend fun`; kiểm tra phiên bản Spring Security/Kotlin, WebFlux coroutine integration, class `open`/all-open plugin và test riêng. Không suy rộng từ yêu cầu Java Publisher thành “Kotlin suspend luôn bị cấm”.

**Reactive policy bean:** Có thể trả `Mono<Boolean>` từ logic cho phép/chặn theo user/resource; không được block thread để tra quyền. Nếu kết hợp nhiều expression, test semantics của SpEL/authorization manager.

**Publisher.empty():** `Mono.empty()` hoặc `Flux.empty()` vẫn là Publisher hợp lệ. “Không emit onNext” không có nghĩa được phép bypass method security; pipeline vẫn cần được subscribe và hoàn tất/error theo chính sách.

**Mono<Void>:** Không có giá trị trả, nhưng subscription/completion có thật. Đây là hình thức đúng để WebFlux biết khi tác vụ async đã hoàn thành, không dùng `void` + `subscribe()`.

**Lưu dữ liệu phân vùng:** Một Flux được phép gọi có thể chứa nhiều records; quyền xem từng record không tự do `@PreAuthorize("hasRole('USER')")` giải quyết. Đặt chốt ở service/repository.

**Method gọi từ scheduled/background job:** Lời gọi ngoài HTTP có thể không có Reactor SecurityContext. Phải có thiết kế identity/authorization cụ thể của job; không tự gắn quyền ADMIN cho mọi Publisher chỉ để tránh lỗi.

**Return type Publisher không chứng minh non-blocking:** `Mono.fromCallable(blockingOperation)` vẫn có thể block thread khi subscribe. Dùng `boundedElastic` bridge có kiểm soát, timeout, capacity và test hiệu năng nếu chưa chuyển được sang driver reactive.

## 12. Checklist triển khai

1. Xác định method được annotate và **kiểu trả về khai báo**. Với Java reactive, dùng `Mono<T>`, `Flux<T>` hoặc `Mono<Void>`.
2. Bật `@EnableReactiveMethodSecurity`; giữ `@EnableWebFluxSecurity`/`SecurityWebFilterChain` cho HTTP theo kiến trúc.
3. Đặt rule ở public Spring service bean gọi qua AOP proxy, tránh self-invocation/`new`/private/final restrictions.
4. Giữ side effects trong Publisher deferred, không tự `subscribe()`, không `block()` trên event-loop.
5. Lấy principal từ `ReactiveSecurityContextHolder` và không tin header tự khai hay biến singleton.
6. Test method với Spring-injected proxy bằng `StepVerifier` và Reactor Context; test HTTP bằng `WebTestClient`.
7. Có negative tests: anonymous 401, authenticated role sai 403, dữ liệu chéo owner/tenant không bị lộ.
8. Với method ghi, test rằng **không có side effect** khi role bị từ chối.
9. Với Flux/hot Publisher/cache/retry, test không có rò rỉ giữa các subscriber và việc ghi không bị chạy lại ngoài ý muốn.
10. Khi dùng Kotlin coroutine hoặc policy Mono<Boolean>, tra tài liệu theo version thực tế, không sao chép mù cấu hình từ Servlet.
11. Bổ sung authorization theo resource/tenant, không coi method role-only là đủ cho tất cả dữ liệu.
12. Nâng phiên bản framework đúng chính sách, chạy lại test khi thay đổi proxy/annotation/scheduler.

## 13. Câu hỏi tự đánh giá

**Câu 1.** `CompletableFuture<User>` có phải `Publisher<User>` không?  
**Không.** Java Future không implement Reactive Streams Publisher. Cần trả `Mono<User>` và trì hoãn nguồn khi tích hợp.

**Câu 2.** Tại sao `Mono.just(blockingSave())` nguy hiểm?  
Vì Java chạy `blockingSave()` trước khi `Mono.just(...)` được tạo. Đây là eager side effect/blocking, không đảm bảo đúng boundary subscription.

**Câu 3.** `Mono<Void>` có phải kiểu return hợp lệ để áp `@PreAuthorize` không?  
**Có.** Nó là Publisher hoàn thành hoặc phát lỗi và phù hợp thao tác async không có body.

**Câu 4.** Bật `@EnableWebFluxSecurity` có tự bật `@PreAuthorize` trên service không?  
**Không.** Cần `@EnableReactiveMethodSecurity`.

**Câu 5.** `@PreAuthorize` trên phương thức trả Mono nhưng controller gọi `new Service()` có an toàn không?  
**Không theo cơ chế Spring AOP proxy bình thường.** Service phải là bean do Spring quản lý và được gọi qua proxy.

**Câu 6.** Một user đã xác thực thiếu role gọi endpoint và nhận 403; điều này khác 401 ra sao?  
401 thường liên quan chưa có authentication hợp lệ, còn 403 với user đã login cho thấy authorization từ chối theo policy.

**Câu 7.** `Flux<Report>` được `@PreAuthorize("hasRole('READER')")` có tự lọc record theo tenant không?  
**Không.** Phải kiểm tra owner/tenant tại truy vấn hoặc policy domain.

**Câu 8.** Có phải method Java trả `String` được bảo vệ giống reactive `Mono<String>` không?  
**Không nên giả định như vậy.** Reactive method security cần hợp đồng Publisher để làm việc với Reactor Context.

**Câu 9.** `@PostAuthorize` bị deny có tự rollback email đã gửi hoặc thanh toán đã xử lý không?  
**Không.** Cần chốt quyền trước side effect và thiết kế transaction/idempotency.

**Câu 10.** Kotlin `suspend fun` có nhất thiết phải khai báo `Mono` ở source để được hỗ trợ không?  
**Không tuyệt đối.** Spring Security AuthorizationManager mode có hỗ trợ coroutine trên các phiên bản phù hợp; phải test integration đó riêng.

### Tài liệu chính thức

- Spring Security 6.5, *EnableReactiveMethodSecurity*: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security, `EnableReactiveMethodSecurity` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html
- Spring Security, `ReactiveSecurityContextHolder` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Project Reactor, *Adding a Context to a Reactive Sequence*: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor `Mono` API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring Framework, *AOP Proxying Mechanisms*: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework, *WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Boot 3.5, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Kết luận:** Với method security **reactive** cho Java, kiểu trả về `Publisher` là điều kiện để interceptor kết nối authorization với Reactor Context của subscription. Hãy ưu tiên `Mono`, `Flux`, `Mono<Void>`; nhưng return type đúng thôi chưa đủ — code phải được gọi qua Spring AOP proxy, không chạy side effect trước khi được cho phép, và có negative tests chứng minh user thiếu quyền thật sự bị chặn.