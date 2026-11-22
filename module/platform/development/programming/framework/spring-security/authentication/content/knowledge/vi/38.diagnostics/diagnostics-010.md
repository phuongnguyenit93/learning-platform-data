# Mất Reactor Context hoặc ThreadLocal không phù hợp mô hình thực thi trong Spring Security authentication

## 1. Dấu hiệu và câu hỏi chẩn đoán đầu tiên

Một lỗi thường gặp khi ứng dụng Java chuyển từ Spring MVC/Servlet sang Spring WebFlux/Reactor là: request đã xác thực thành công, nhưng ở service hoặc callback bất đồng bộ, code gọi `SecurityContextHolder.getContext().getAuthentication()` lại trả `null`, ra anonymous hoặc hiếm hơn là nhìn thấy danh tính không mong đợi. Đôi khi lỗi chỉ xuất hiện ở production dưới tải, sau `publishOn`/`subscribeOn`, khi chạy `CompletableFuture`, hoặc trong logic `subscribe()` tự phát.

**Đề bài “Mất Reactor Context hoặc ThreadLocal không phù hợp mô hình thực thi”** không chỉ là lỗi không thấy username. Nó có thể tạo ba dạng hậu quả:

- **Sai từ chối:** user đã login nhưng service tưởng anonymous, trả 401/403 hoặc bỏ qua tác vụ.
- **Sai truy cập:** logic tự viết dùng fallback/admin/default tenant hoặc tin một `ThreadLocal` cũ từ thread pool, khiến quyền gắn sai user.
- **Sai quan sát:** request trace ID, tenant hoặc MDC mất khi đổi thread; logs chỉ hiển thị một phần flow và gây kết luận sai rằng authorization không chạy.

**Quy tắc nền tảng:**

- Với **Spring Security Servlet/MVC**, `SecurityContextHolder` mặc định dùng `ThreadLocal`: security context bám theo **thread hiện tại** trong phạm vi request, được Spring Security filter quản lý dọn dẹp.
- Với **Spring Security Reactive/WebFlux**, security context được đặt trong **Reactor `Context` của từng `Subscriber`**. Cách đọc đúng là `ReactiveSecurityContextHolder.getContext()`, trả `Mono<SecurityContext>`. Context không được lưu ở global variable và không được đảm bảo nằm trong `ThreadLocal` của thread đang chạy callback.
- **Reactor Context** và **ThreadLocal** là hai cơ chế khác nhau; không nên “khắc phục” bằng `SecurityContextHolder.MODE_GLOBAL` hoặc `MODE_INHERITABLETHREADLOCAL` trong server reactive.
- Khi code giao việc sang **ExecutorService, CompletableFuture, native callback hoặc hệ thống khác không dùng Reactor**, context không nhất thiết tự đi theo; phải thiết kế ranh giới truyền dữ liệu hoặc bridging được hỗ trợ.
- **Một Context có principal không tự cấp quyền cho tác vụ mới:** authority/tenant/object ownership vẫn phải được kiểm theo policy và identity đáng tin; không ghép thông tin giữa các request.

Bài dùng **Java 17+, Spring Boot 3.x, Spring Security 6.5 Servlet/WebFlux và Reactor 3.x** làm khung tham chiếu. Tên API cụ thể theo dòng thư viện, cần kiểm tra BOM thực chạy khi nâng sang Spring Boot 4/Spring Security 7.

## 2. So sánh ThreadLocal, Reactor Context và SecurityContext

| Khía cạnh | Servlet SecurityContextHolder (mặc định) | ReactiveSecurityContextHolder trong WebFlux |
| --- | --- | --- |
| Vị trí logic | `ThreadLocal<SecurityContext>` của thread | `Mono<SecurityContext>` gắn trong Reactor `Context` của subscriber |
| Cách đọc | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` |
| Scope điển hình | Thread đang phục vụ HTTP request | Luồng Publisher/Subscriber và subscription được bảo vệ |
| Khi chuyển thread | ThreadLocal **không** tự truyền qua thread pool | Reactor Context **được truyền trong các Reactor operators đúng hợp đồng** |
| Khi dùng `CompletableFuture.supplyAsync` độc lập | Thường không có context; cần propagation có chủ ý | Không tự đi qua callback ngoài Reactor |
| Khi dùng `Mono/Flux` thông thường | Không phải nơi nên đọc auth | Context đi với subscription, kể cả `publishOn`/`subscribeOn` chuẩn |
| Khi dùng `subscribe()` lồng bên trong | Không nên để lẫn lifecycle | Có thể tạo subscription tách, mất context và error handling |
| Cleanup | Security filter dọn context trên request thread | Subscriber lifecycle và Context scope; bridge ThreadLocal cần cleanup |
| Cách test | `MockMvc` + Spring Security Test | `WebTestClient` + Reactor `StepVerifier` |

**SecurityContext** chứa `Authentication`, trong đó có principal, authorities, trạng thái đã xác thực và metadata. Đây không phải nơi tin cậy để lưu raw password/access token tùy tiện; auth mechanism thường xóa credentials hoặc chỉ giữ dữ liệu cần thiết. **Reactor Context** cũng không phải secret vault hay database; nó là cơ chế truyền contextual metadata trong pipeline, không tự encrypt hay persist qua network.

### Mẫu nhầm lẫn thường thấy

```java
// Sai trong một reactive pipeline: lấy auth từ ThreadLocal
// thay vì subscriber's Reactor Context.
Mono<String> unsafe() {
    return Mono.just("ready")
            .publishOn(Schedulers.parallel())
            .map(x -> SecurityContextHolder.getContext()
                    .getAuthentication().getName());
}
```

Đây là **đoạn minh họa lỗi** (cần import Spring Security/Reactor), không phải API controller nên copy vào production. Trong WebFlux, `getAuthentication()` có thể là `null`; nếu trước đó vô tình có ThreadLocal cũ, code còn có nguy cơ lấy **sai principal**. Việc chạy đôi lúc thành công trên một thread **không chứng minh** đúng trong môi trường nhiều subscriber.

Cách đúng sẽ đọc `ReactiveSecurityContextHolder.getContext()` trong reactive chain và áp role/ownership bằng Spring Security authorization.

## 3. Reactor Context vận hành theo **subscription**, không phải theo thread

Reactor Core mô tả `Context` là cấu trúc key/value **immutable**, gắn với subscriber. Nó được truy cập theo luồng **subscription từ downstream về upstream**. Để thêm dữ liệu, dùng `contextWrite(...)`; để đọc trong logic xảy ra tại lúc subscribe, dùng `Mono.deferContextual(...)` hay `Flux.deferContextual(...)`.

### 3.1. Ví dụ Context thường (không phải security authentication)

```java
Mono<String> currentRequestId = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")));

Mono<String> first = currentRequestId
        .contextWrite(ctx -> ctx.put("requestId", "req-A"));

Mono<String> second = currentRequestId
        .contextWrite(ctx -> ctx.put("requestId", "req-B"));

// Hai subscriptions riêng:
String a = first.block();   // "req-A" trong CLI/unit test
String b = second.block();  // "req-B" trong CLI/unit test
```

Đây là **snippet minh họa Reactor** dùng `reactor.core.publisher.Mono`; `block()` chỉ nên dùng trong CLI/test, **không** đặt trong handler WebFlux trên event loop. Một Publisher nguồn `currentRequestId` được tái dùng mà mỗi subscription nhận Context riêng; không có biến global “requestId hiện tại”.

### 3.2. `contextWrite` ảnh hưởng upstream, không sửa thread state

```java
Mono<String> flow =
        Mono.deferContextual(ctx -> Mono.just(ctx.get("label")))
            .contextWrite(ctx -> ctx.put("label", "inner"))
            .flatMap(v -> Mono.deferContextual(ctx ->
                    Mono.just(v + "+" + ctx.get("label"))))
            .contextWrite(ctx -> ctx.put("label", "outer"));

// Khi subscribe: "inner+outer"
```

Ở đoạn trên, `deferContextual` **upstream** nhìn thấy giá trị `inner`; `flatMap` ở downstream nhìn thấy `outer`. Từ “Context có key này ở một chỗ” không suy ra mọi operator/inner Publisher trong graph nhìn thấy cùng giá trị. Context propagation tuân scope, thứ tự `contextWrite` và subscriber lineage.

**Trong Spring Security**, đặt `ReactiveSecurityContextHolder.withAuthentication(...)` sai chỗ có thể làm upstream nhìn thấy context nhưng downstream/inner subscription khác thì không. Ưu tiên để framework security filters thiết lập context tại HTTP boundary; tránh tự chèn principal giả vào production chain.

### 3.3. `publishOn` và `subscribeOn`

- `publishOn(Schedulers.parallel())` thay đổi thread chạy **các downstream operators** sau vị trí đó; các operators vẫn nằm trong Reactor chain và có thể truy cập Context phù hợp qua `deferContextual`.
- `subscribeOn(Schedulers.boundedElastic())` tác động cách subscription/source được schedule; không biến Context thành ThreadLocal.
- Các Reactor operators chuẩn giữ propagation đúng khi chain/subscription không bị cắt ra. Lỗi thường đến từ **đọc ThreadLocal** hoặc **tạo một subscription mới**, không phải cứ `publishOn` là Reactor Context bị mất.
- `Schedulers.boundedElastic()` phù hợp để offload một API **blocking** được đóng gói đúng; `Schedulers.parallel()` dành cho CPU-bound tasks, không nên block I/O trên nó hoặc Reactor Netty event loop.

### 3.4. Tại sao `Mono.just(...)` và `Mono.defer(...)` có thể đánh lừa?

`Mono.just(value)` nhận `value` được **tính ngay lúc assembly**. Nếu bạn viết `Mono.just(SecurityContextHolder.getContext().getAuthentication())`, việc đọc auth xảy ra **trước subscription** và có thể là null/sai user. Chuyển sang `Mono.defer(() -> Mono.just(SecurityContextHolder...))` làm việc tính toán xảy ra muộn hơn nhưng **vẫn đọc sai nguồn ThreadLocal** trong WebFlux. Khi cần Context, dùng `ReactiveSecurityContextHolder.getContext()` hoặc `deferContextual` của Reactor.

**Đừng chữa lỗi ngữ cảnh bằng cách thêm `Thread.sleep(...)` hoặc “làm mọi thứ trên một thread”**; đó có thể che bug trong local và làm nghẽn event loop khi chạy thật.

## 4. ReactiveSecurityContextHolder, WebFlux filter chain và phạm vi của Authentication

Trong Spring Security WebFlux, security filters tạo/khôi phục `SecurityContext` từ authentication scheme/repository rồi gắn context vào Reactor subscription. Tài liệu Spring Security về reactive method security nhấn mạnh dùng:

```java
Mono<String> currentName =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
```

Đoạn này cần imports:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
```

**Nếu không có reactive SecurityContext**, `getContext()` có thể phát `Mono.empty()`. `map(SecurityContext::getAuthentication)` không nên coi auth luôn có; trong một pipeline ở resource đã bảo vệ bằng `authenticated()` và authentication mechanism hợp lệ thì kỳ vọng có, nhưng custom contexts và public endpoints có thể không có. Dùng `switchIfEmpty` cho public endpoint và fail closed/giữ 401/403 đúng với protected operation.

### 4.1. Chỉ đưa auth vào Context trong test/custom boundary đã xác minh

```java
Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice", "N/A", List.of(
                        new SimpleGrantedAuthority("ROLE_USER")));

Mono<String> result =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(alice));
```

Import `UsernamePasswordAuthenticationToken` từ `org.springframework.security.authentication` và `SimpleGrantedAuthority` từ `org.springframework.security.core.authority`. `withAuthentication(...)` tạo Reactor Context chứa SecurityContext cho **subscription đó**, không ghi vào HttpSession/WebSession và không tự xác minh password/token. Ở production, đừng lấy username từ request parameter rồi tạo “authenticated token” bằng tay như trên: đó là **bypass authentication**.

### 4.2. Lifecycle được cấu hình ở đúng stack

| Tình huống | Cơ chế |
| --- | --- |
| Spring MVC `HttpSecurity`, `SecurityFilterChain` | Servlet authentication filters, `SecurityContextHolder` và `SecurityContextRepository` |
| Spring WebFlux `ServerHttpSecurity`, `SecurityWebFilterChain` | Reactive WebFilter chain, `ReactiveSecurityContextHolder` và `ServerSecurityContextRepository`/Reactor Context |
| HTTP Basic trong WebFlux | `http.httpBasic(...)` tạo reactive authentication flow, bảo vệ exchange |
| Spring Security reactive method rules | `@EnableReactiveMethodSecurity` trên publisher-returning methods, dùng Reactor Context |
| Unit test reactive | `StepVerifier` và `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` |
| HTTP WebFlux tests | `WebTestClient`, Spring Security Test `springSecurity()`/`mockUser()` hoặc Basic/JWT thật |

**Không trộn stack:** `SecurityWebFilterChain` không nhận `HttpSecurity`; `SecurityFilterChain` Servlet không phải cấu hình cho `ServerHttpSecurity`. Nếu một project kéo cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot có thể chọn Servlet web application type; cần kiểm actual runtime web stack thay vì chỉ nhìn thấy dependency `reactor-core` và kết luận đang ở WebFlux.

## 5. Bảng lỗi thường gặp theo vị trí đứt luồng

| Triệu chứng | Nguyên nhân | Cách test để phân biệt |
| --- | --- | --- |
| `SecurityContextHolder.getContext().getAuthentication() == null` trong WebFlux | Đọc Servlet ThreadLocal thay vì Reactor Context | Đọc `ReactiveSecurityContextHolder.getContext()` trong pipeline |
| Auth có ở controller nhưng mất trong `CompletableFuture.supplyAsync` | Task vào Executor/thread pool ngoài Reactor subscription | Truyền immutable validated identity có chủ đích hoặc bridge được quản lý |
| `MDC.get("traceId")` trống sau `publishOn` | MDC dùng ThreadLocal và không có Micrometer context bridge | So sánh Reactor Context `deferContextual`, kiểm registered accessor/hook |
| Không thấy auth sau `service.doWork().subscribe()` | Tạo detached subscriber, mất parent context/error lifecycle | Trả `Mono`, nối bằng `flatMap` |
| User A thỉnh thoảng thấy tenant của B | Mutable singleton/global variable hay ThreadLocal không cleanup trong pool | So A/B concurrent; reset/remove context sau task |
| Test `@WithMockUser` pass nhưng HTTP Basic thực fail | Test bơm principal trực tiếp, không qua provider | Tạo WebTestClient request với Basic/password thật |
| HTTP request qua WebFlux vẫn unauthorized | `SecurityWebFilterChain` matcher sai, authentication fail, principal không tồn tại | Kiểm HTTP 401/403, filters, credentials và logs đã mask |
| Test `ReactiveSecurityContextHolder.getContext()` empty | Test subscriber không có context hoặc `contextWrite` đặt sai scope | Unit test withAuthentication đúng vị trí, StepVerifier |
| Async job chạy sau khi request đã kết thúc | Request context không còn và job thiếu service identity | Truyền actor ID/audit metadata, re-authorize quyền hiện tại trước side effect |
| `block()` báo UnsupportedOperationException/IllegalStateException về blocking | Block trên reactor-http-nio hoặc parallel scheduler | Giữ end-to-end reactive, offload blocking đúng scheduler |
| Đã bật automatic propagation mà vẫn mất auth | Chưa có accessor/binding tương ứng; context bị tách; phụ thuộc version | Test thật theo version, không coi hook là auth mechanism |
| Login thành công mà request sau mất user | Repository/session/cookie/entry point sai, không phải Reactor Context | Kiểm `ServerSecurityContextRepository` và WebSession/cookie lifecycle |
| Thêm `MODE_INHERITABLETHREADLOCAL` nhưng lỗi trộn user | Child-thread semantics không phù hợp reused executor | Hoàn nguyên; dùng reactive context/delegating wrappers đúng stack |
| WebClient không tự gửi Bearer tới downstream | Reactor Context chứa Authentication không đồng nghĩa token relay | Cấu hình OAuth client/token relay theo policy, kiểm audience/scope |
| `Mono.empty()` bị coi là anonymous rồi cấp public default role | Fail-open trong custom fallback | Fail closed ở endpoint bảo vệ, không tự cấp quyền |

**Một kết luận quan trọng:** nếu thấy 403, đừng vội nói “mất context”. Có thể user đã authenticated nhưng thiếu role/tenant, CSRF bị chặn, WebFilterChain matcher sai hoặc downstream 403. Phải kiểm **authentication có được thiết lập không**, **authorization policy**, và **điểm phát status**.

## 6. Ví dụ ứng dụng Spring Boot 3 + WebFlux + Spring Security 6.5

Ví dụ minh họa cơ chế đúng từ request đến ReactiveSecurityContextHolder, có thể dùng làm bài lab trong project **Java 17+, Spring Boot 3.x tương thích Spring Security 6.5**. Không dùng Servlet/MVC starter trong project này.

### 6.1. build.gradle

Trong một Gradle project có Spring Boot plugin và Java toolchain đã được thiết lập:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

`spring-boot-starter-test` mang JUnit Jupiter/AssertJ/Mockito theo BOM. `reactor-test` chứa `StepVerifier`. Chỉ dùng một Reactor version do Boot BOM kiểm soát, không chèn `reactor-core` version khác vô căn cứ vì nó có thể đổi semantics context propagation.

### 6.2. ReactiveContextApplication.java

```java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }
}
```

### 6.3. ReactiveSecurityConfig.java

```java
package com.example.reactiveauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/public/**").permitAll()
                    .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(alice, admin);
    }
}
```

- `@EnableReactiveMethodSecurity` bật method security dựa trên Reactor Context. Method được bảo vệ nên trả về `Publisher` (ví dụ `Mono`) để interceptor reactive hoạt động đúng. Không tự dựng method security trên method `void`/`String` đồng bộ rồi giả định reactive context có sẵn.
- `httpBasic()` trong ví dụ nhận credential test; server tạo authentication từ `MapReactiveUserDetailsService` và BCrypt. Password chỉ là **fixture local**; không dùng InMemory user store/password test trong production.
- `.anyExchange().authenticated()` bảo vệ các route khác. Ở HTTP GET thuần, không cần tắt CSRF; nếu có POST web dùng cookie, hãy test CSRF đúng scheme. Basic credential có thể được browser tự gửi lại, nên không khẳng định Basic luôn miễn CSRF.
- Nếu Spring Boot thực sự khởi động **Servlet** do dependency khác, config `ServerHttpSecurity` sẽ không bảo vệ MVC như bạn dự kiến. Kiểm runtime logs và dependencies.

### 6.4. IdentityService.java: ví dụ method security đúng

```java
package com.example.reactiveauth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class IdentityService {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminView() {
        return currentName().map(name -> "admin=" + name);
    }
}
```

Phần khó: `currentName()` trả **Mono trì hoãn** thay vì đọc ThreadLocal ngay lúc service được gọi. `adminView()` là method public trên Spring bean nên interceptor có thể áp `@PreAuthorize`; chính sách admin cần cả HTTP authentication và role. Khi method được gọi từ **cùng class qua this.adminView()** (self-invocation), Spring proxy method security có thể bị bỏ qua; test cả gọi từ controller/bean khác, không chỉ unit direct new IdentityService().

### 6.5. IdentityController.java: đọc Context sau khi chuyển Scheduler

```java
package com.example.reactiveauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class IdentityController {

    private final IdentityService service;

    public IdentityController(IdentityService service) {
        this.service = service;
    }

    @GetMapping("/api/whoami")
    public Mono<String> whoami() {
        return service.currentName().map(name -> "user=" + name);
    }

    @GetMapping("/api/whoami-hop")
    public Mono<String> whoamiAfterSchedulerSwitch() {
        return Mono.just("start")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> service.currentName())
                .map(name -> "user=" + name);
    }

    @GetMapping("/api/public/context")
    public Mono<String> publicContext() {
        return service.currentName()
                .map(name -> "user=" + name)
                .defaultIfEmpty("anonymous");
    }

    @GetMapping("/api/admin/report")
    public Mono<String> adminReport() {
        return service.adminView();
    }
}
```

**Vì sao đây là ví dụ chẩn đoán hữu ích?**

- `/api/whoami` và `/api/whoami-hop` đều truy cập `ReactiveSecurityContextHolder`. Ở route thứ hai, việc đọc xảy ra **trong flatMap sau `publishOn`**; nếu code dùng ThreadLocal thay thế, có thể mất auth. Với Reactor Context đúng, cùng một authenticated subscriber vẫn nhìn thấy Alice.
- `/api/public/context` chỉ trả `anonymous` khi context **thật sự không có authentication**; nó là route public demo, không đại diện cho rule nhạy cảm. Không dùng `defaultIfEmpty("admin")` hoặc một principal có quyền làm fallback.
- `/api/admin/report` gọi method bean khác với `@PreAuthorize("hasRole('ADMIN')")`; Alice không được vào dù identity context vẫn tồn tại. **Mất context** khác **thiếu quyền**.
- Không có `.block()`, `.subscribe()` hoặc global ThreadLocal trong controller/service. Spring WebFlux quản lý subscription và response lifecycle.

### 6.6. Chạy local

Giả sử project có Gradle wrapper:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Thử qua terminal development, **không dùng password thật với HTTP**:

```bash
curl -i http://localhost:8080/api/public/context
curl -i -u alice:alice-pass http://localhost:8080/api/whoami
curl -i -u alice:alice-pass http://localhost:8080/api/whoami-hop
curl -i -u alice:alice-pass http://localhost:8080/api/admin/report
curl -i -u admin:admin-pass http://localhost:8080/api/admin/report
```

Kỳ vọng:

| Request | Kết quả |
| --- | --- |
| GET `/api/public/context` không credential | 200, body `anonymous` |
| GET `/api/whoami` không credential | 401 với HTTP Basic challenge |
| Alice GET `/api/whoami` | 200, body `user=alice` |
| Alice GET `/api/whoami-hop` | 200, body `user=alice` dù scheduler đã đổi |
| Alice GET `/api/admin/report` | 403 do thiếu role, **không phải mất Reactor Context** |
| Admin GET `/api/admin/report` | 200, body `admin=admin` |

Đây là hành vi **dự kiến cho demo**. Test mã 401/403 qua SecurityWebFilterChain thật, không suy rằng mỗi custom error handler hay proxy sẽ giữ chính xác response body/header.

## 7. Kiểm thử WebTestClient: đủ ba trạng thái anonymous, user và admin

Trong project Boot WebFlux ở trên, dùng `spring-security-test` và Spring Boot Test:

File `src/test/java/com/example/reactiveauth/ReactiveIdentityHttpTest.java`:

```java
package com.example.reactiveauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveIdentityHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousCannotReadProtectedIdentity() {
        client.get().uri("/api/whoami")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void anonymousPublicEndpointHasNoIdentity() {
        client.get().uri("/api/public/context")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("anonymous");
    }

    @Test
    void aliceIdentitySurvivesReactorSchedulerHop() {
        client.get().uri("/api/whoami-hop")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user=alice");
    }

    @Test
    void aliceLacksAdminAuthority() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminIsAuthorizedInReactiveMethod() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin=admin");
    }

    @Test
    void badPasswordIsAuthenticationFailure() {
        client.get().uri("/api/whoami")
                .headers(h -> h.setBasicAuth("alice", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

**Tại sao dùng Basic thật?** `@WithMockUser` và `mockUser()` chủ động chèn một principal test, hữu ích để kiểm authorization và Context flow nhưng **không chứng minh HTTP Basic password/ReactiveAuthenticationManager thật chạy**. Bộ test trên dùng request headers Basic đến app thật trên random port.

**Không nhập password production vào test fixture hoặc logs.** Khi chẩn đoán sau `publishOn`, test càng phải dùng nhiều account khác nhau để phát hiện lẫn identity chứ không chỉ “có một username”.

## 8. StepVerifier: xác minh Context độc lập giữa hai subscribers

Test ở cấp Reactor cho biết một `Mono` có lấy đúng security context tại subscription time và không dính context của request trước hay không.

File `src/test/java/com/example/reactiveauth/ReactivePrincipalTest.java`:

```java
package com.example.reactiveauth;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactivePrincipalTest {

    private Authentication principal(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username, "N/A",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void samePublisherUsesDifferentContextForEachSubscriber() {
        Mono<String> username = ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .defaultIfEmpty("missing");

        StepVerifier.create(username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        principal("alice"))))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        principal("bob"))))
            .expectNext("bob")
            .verifyComplete();

        StepVerifier.create(username)
            .expectNext("missing")
            .verifyComplete();
    }

    @Test
    void threadSwitchDoesNotLoseReactivePrincipal() {
        Mono<String> username = Mono.just("start")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> ReactiveSecurityContextHolder.getContext())
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);

        StepVerifier.create(username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        principal("alice"))))
            .expectNext("alice")
            .verifyComplete();
    }
}
```

**Đây là unit test có mock Authentication**, không kiểm database/password hashing; nó kiểm đúng **Context propagation semantics** của Reactor/Spring. Các imports đều thuộc stack WebFlux/Security/Reactor; `StepVerifier` trong `reactor-test`. Khi thiếu Context, expected là `missing`; khi có Context “bob”, expected không được là “alice”.

**Kiểm concurrency thực:** chạy hàng trăm requests Alice/Bob với token/session riêng qua WebTestClient trên scheduler/Netty thật. Assert response name, tenant, role và business side effects không bị trộn, thay vì chỉ assert rằng `Thread.currentThread().getName()` đã đổi.

## 9. Detach subscription: lỗi `subscribe()` ngay trong service

### 9.1. Phản ví dụ

```java
// Không nên áp dụng trong handler:
// Đây là một detached subscription, không thuộc vòng đời response.
public Mono<String> wrongFireAndForget() {
    doSensitiveWork().subscribe(); // side effect xảy ra độc lập
    return Mono.just("accepted");
}
```

Tình huống có thể xảy ra:

- Subscription được tạo ngay khi method được gọi, trong khi downstream request subscription/context chưa có.
- Security context của HTTP request **không tự được chuyển** vào detached subscription.
- Kết quả/exception/cancellation không còn gắn với HTTP response; endpoint có thể trả 200 dù hành động thực sự fail.
- Một task bắt đầu sau khi user logout hoặc account bị thu hồi có thể có snapshot auth cũ nếu bạn copy bằng tay mà không re-check.

**Cách đúng:** composition trong cùng graph:

```java
public Mono<String> correctComposition() {
    return doSensitiveWork()
            .thenReturn("accepted");
}

// Khi cần truyền đầu ra hoặc quyết định theo principal:
public Mono<String> identityBoundWork() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(authentication ->
                performAuthorizedAction(authentication.getName()))
            .thenReturn("accepted");
}
```

Đây là **fragment trong một service** có `doSensitiveWork()`/`performAuthorizedAction(...)` được định nghĩa, cần kiểm authorization domain. `thenReturn("accepted")` chỉ được phát sau khi Publisher nguồn hoàn tất; errors/cancellation vẫn thuộc pipeline. Với HTTP 202/queue xử lý bất đồng bộ lâu dài, hãy thiết kế **durable job** có account ID/audit và **service credentials + policy check khi worker chạy**, không giả vờ request Context sống sau response.

### 9.2. Context không tự truyền qua WebClient/OAuth service

Dù `ReactiveSecurityContextHolder` chứa Authentication của user ở request inbound, nó không đồng nghĩa `WebClient` tự gửi `Authorization: Bearer ...` tới downstream. Nếu cần token relay, dùng cơ chế OAuth2 client/delegation đúng quyền, audience và scope; không chuyển raw inbound token cho service khác một cách mù quáng. Lỗi 401 của downstream không chứng minh Reactor Context local đã mất.

## 10. CompletableFuture, @Async, ExecutorService và thread pool

**Không phải mọi async là Reactor.** Bất kỳ đoạn nào vượt sang `CompletableFuture.supplyAsync`, `ExecutorService.submit`, custom callback, scheduled job hay message listener đều có lifecycle khác.

### 10.1. Vì sao ThreadLocal không tự đi theo?

```java
ThreadLocal<String> currentUser = new ThreadLocal<>();
currentUser.set("alice");

CompletableFuture<String> result =
        CompletableFuture.supplyAsync(currentUser::get);

// Một task trên commonPool thường không nhìn thấy "alice".
// result có thể là null. Không dùng làm auth mechanism.
```

Đây là **phản ví dụ Java** trong một context thích hợp với import `CompletableFuture`, không phải code test deterministic vì executor/default thread behavior có thể thay đổi. Mặc định `ThreadLocal` ở thread cha không phải biến global, nên thread khác không có giá trị. `InheritableThreadLocal` có thể sao chép khi thread **được tạo**, nhưng reused thread pools làm semantics không phù hợp, dễ trộn identity/tenant; không bật nó để “sửa nhanh” WebFlux.

### 10.2. Truyền dữ liệu đã xác minh dưới dạng argument

Một cách an toàn hơn cho nghiệp vụ dài hạn là capture **immutable actor ID/tenant ID/correlation ID** ở ranh giới đã được authenticate, sau đó kiểm lại quyền tại lúc thực thi:

```java
record AuditActor(String accountId, String tenantId) {}

// Fragment bên trong reactive service:
Mono<String> work() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(auth -> {
            // stable ID/tenant ở đây phải xuất phát từ trusted principal,
            // không lấy accountId từ query parameter rồi tin ngay.
            AuditActor actor = resolveTrustedActor(auth);
            return Mono.fromCallable(() -> blockingBusinessAction(actor))
                .subscribeOn(Schedulers.boundedElastic());
        });
}
```

**Snippet cần implement `resolveTrustedActor` và `blockingBusinessAction`**, không phải class runnable. Việc đưa actor ID sang boundedElastic là input nghiệp vụ rõ ràng, nhưng vẫn phải enforce authorization/ownership trong `blockingBusinessAction` nếu nó truy cập tài nguyên nhạy cảm. Đừng đem raw password/Bearer token vào log hoặc queue.

Nếu bạn có **Servlet/MVC** `@Async` và thật sự cần SecurityContextHolder của request đã xác thực, Spring Security cung cấp các wrapper như `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` và cơ chế riêng. Đó là giải pháp có kiểm soát cho **Servlet ThreadLocal**; không phải thay thế trực tiếp `ReactiveSecurityContextHolder` của WebFlux. Wrapper phải tránh reuse context không còn hợp lệ, dọn dẹp đúng và không giữ quyền sau khi user bị revoke.

## 11. Micrometer Context Propagation, MDC và automatic mode: dùng đúng mức

Reactor 3.5+ tích hợp với hệ sinh thái **Micrometer Context Propagation** để truyền một số giá trị từ/đến `ThreadLocal` theo các `ThreadLocalAccessor` đã đăng ký. Có hai khái niệm riêng:

- **Reactor Context** là nguồn dữ liệu ngữ cảnh trong reactive graph.
- **ThreadLocal restoration/capture** là cầu nối nhằm hỗ trợ library cũ dùng `ThreadLocal`, như logging MDC, observability và một số integration đặc biệt.

Ở Reactor có các API `contextCapture()` và `Hooks.enableAutomaticContextPropagation()`:

```java
// Khái niệm: bật ở bootstrap trước khi tạo subscriptions,
// chỉ nếu dependencies/accessors và hiệu năng phù hợp.
Hooks.enableAutomaticContextPropagation();
```

Import `reactor.core.publisher.Hooks`. **Đừng bật hook rồi kết luận bảo mật đã đúng**. Reactor documentation lưu ý automatic mode tác động đến **new subscriptions**, cần registered `ThreadLocalAccessor`, có chi phí performance và phải cleanup ThreadLocal khi context thiếu giá trị để tránh leak sang người dùng khác. Cơ chế này có thể hữu ích cho MDC/tracing; nó **không xác thực token, không tạo Authentication mới và không tự mang login từ WebFlux request sang một HTTP request khác**.

**Không áp dụng một nhận định tuyệt đối “ThreadLocal luôn null sau publishOn”**: với automatic mode, đúng accessor và subscription context, một số ThreadLocal có thể được restore. Vấn đề là **phụ thuộc vào bridge/config và scope**, không phải semantics đáng tin cho mọi custom authentication code. Trong WebFlux, code business nên dùng `ReactiveSecurityContextHolder` và context-aware APIs để tránh phụ thuộc workaround.

### 11.1. MDC và log correlation

Trường log `traceId`, `requestId` có thể biến mất sau scheduler switch vì MDC mặc định bám ThreadLocal. Cách làm:

1. Dùng Micrometer Observation/Tracing trong Spring Boot theo version và cấu hình được hỗ trợ.
2. Xác nhận `ThreadLocalAccessor`/context-propagation dependencies đang có và hook/config có hiệu lực.
3. Test log field qua scheduler switch, async boundaries và nhiều concurrent requests.
4. Không log raw Authorization, session cookie hoặc JWT khi debug context; chỉ log correlation ID và user ID đã được giảm nhạy cảm theo policy.
5. Giới hạn cardinality, thu thập traces có quyền truy cập và retention chính xác.

**Tránh đọc MDC “user=alice” làm căn cứ authorization.** MDC chỉ phục vụ quan sát; SecurityContext và authoritative policy mới quyết định quyền. Nếu MDC sai mà auth đúng, cần sửa observability; nếu auth sai mà MDC đúng, vẫn là lỗi bảo mật.

## 12. Java 17 độc lập: nhìn thấy ThreadLocal mất và rò ở worker thread

Để phân biệt hai nguy cơ — **mất context khi đổi thread** và **context cũ rò trong thread pool nếu không dọn** — dùng chương trình Java thuần, không phụ thuộc Spring/Reactor.

Lưu thành `ThreadLocalBoundaryLab.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class ThreadLocalBoundaryLab {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    record TrustedActor(String name) {}

    private static String visibleOnCurrentThread() {
        String name = CURRENT.get();
        return name == null ? "missing" : name;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService single = Executors.newSingleThreadExecutor();
        try {
            // Tình huống request thread sau khi đã xác thực thật.
            CURRENT.set("alice");
            System.out.println("requestThread=" +
                    visibleOnCurrentThread());

            // Worker thread mới không tự nhận ThreadLocal từ request.
            String absent = single.submit(
                    ThreadLocalBoundaryLab::visibleOnCurrentThread).get();
            System.out.println("workerWithoutCapture=" + absent);

            // Input rõ ràng, không đọc global ThreadLocal trên worker.
            TrustedActor actor = new TrustedActor(CURRENT.get());
            String explicit = single.submit(actor::name).get();
            System.out.println("workerWithExplicitActor=" + explicit);

            // Ví dụ lỗi vận hành: task đặt ThreadLocal rồi quên remove.
            single.submit(() -> {
                CURRENT.set("bob");
                return null;
            }).get();
            String stale = single.submit(
                    ThreadLocalBoundaryLab::visibleOnCurrentThread).get();
            System.out.println("staleWorkerValue=" + stale);

            // Code dùng ThreadLocal đúng cách phải dọn trong finally.
            single.submit(() -> {
                try {
                    CURRENT.set("carol");
                    return visibleOnCurrentThread();
                } finally {
                    CURRENT.remove();
                }
            }).get();
            String cleaned = single.submit(
                    ThreadLocalBoundaryLab::visibleOnCurrentThread).get();
            System.out.println("workerAfterCleanup=" + cleaned);
        } finally {
            CURRENT.remove();
            single.shutdown();
            single.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Biên dịch và chạy Java 17+:

```bash
javac ThreadLocalBoundaryLab.java
java ThreadLocalBoundaryLab
```

Stdout **dự kiến xác định**: `newSingleThreadExecutor()` sử dụng một worker thread được tái sử dụng giữa các task, và ThreadLocal không kế thừa theo mặc định.

```text
requestThread=alice
workerWithoutCapture=missing
workerWithExplicitActor=alice
staleWorkerValue=bob
workerAfterCleanup=missing
```

Ý nghĩa từng dòng:

- `requestThread=alice` cho thấy ThreadLocal chỉ có giá trị trong thread nơi đã set.
- `workerWithoutCapture=missing` là lý do async code thường “mất người dùng” nếu đọc ThreadLocal của thread pool.
- `workerWithExplicitActor=alice` minh họa truyền một **giá trị rõ ràng**, không phụ thuộc worker thread state. Trong production, actor cần được xác minh và quyền cần được kiểm lại nếu công việc chạy muộn.
- `staleWorkerValue=bob` minh họa thread pool **giữ giá trị cũ** khi một task quên `remove()`, có thể tạo cross-request tenant/principal leakage nếu dùng làm authorization.
- `workerAfterCleanup=missing` chứng minh dọn qua `finally`. Spring Security framework quản lý cleanup trong các flow tích hợp; tự tạo ThreadLocal cho authenticated identity vẫn là việc nên tránh.

**Tính chất lab:** ví dụ cố tình đặt giá trị “bob” và không xóa ở một task để chỉ ra lỗi; **không áp dụng đoạn đó vào production**. Nó không chứng minh Reactor Context mất vì Reactor Context khác ThreadLocal. Ví dụ Reactor/Spring ở các mục trước là nơi kiểm chính xác reactive context.

## 13. Ma trận kiểm thử lỗi context trong ứng dụng thực

| ID | Tình huống | Hành động | Kỳ vọng |
| --- | --- | --- | --- |
| C01 | WebFlux anonymous request | GET route chỉ authenticated | 401/redirect tùy entry point, không vào logic protected |
| C02 | Alice Basic credential hợp lệ | GET `/api/whoami` | 200 `user=alice` |
| C03 | Alice + `publishOn(Schedulers.parallel())` | GET `/api/whoami-hop` | 200 `user=alice` |
| C04 | Admin + `publishOn` | GET same route | 200 `user=admin` |
| C05 | Alice thiếu ROLE_ADMIN | GET `/api/admin/report` | 403 do authorization, không phải context lost |
| C06 | Admin đủ role | GET admin route | 200 và đúng identity |
| C07 | Same Mono được subscribe 2 lần | Context Alice rồi Bob | Alice và Bob riêng biệt, không rò |
| C08 | Subscribe thiếu context | `ReactiveSecurityContextHolder.getContext()` | Mono empty hoặc fallback an toàn |
| C09 | ContextWrite áp sai vị trí | Unit test scope của operator | Fail rõ; sửa vị trí `contextWrite` |
| C10 | Nested inner Publisher trong flatMap | Truyền context sang inner chain | Đúng subscriber semantics |
| C11 | Service dùng `SecurityContextHolder` sai stack | Test chuyển scheduler | Null/sai auth được phát hiện, không cho access |
| C12 | Detached `subscribe()` trong service | Trigger side effect protected | Test không báo success giả, được thiết kế lại thành `flatMap` |
| C13 | `CompletableFuture.supplyAsync` | Đọc ThreadLocal ở worker | Không kỳ vọng auto propagation |
| C14 | Context từ request A | Gửi async job request B sau đó | Không bị dính principal A |
| C15 | Thread pool reuse task Bob → Alice | Log/request B | Không lấy tenant Bob từ ThreadLocal stale |
| C16 | Reactor context + MDC bridge | `publishOn`, log traceId | MDC giữ trace ID theo cấu hình thực; không leak |
| C17 | Không có bridge | Reactor Context vẫn có requestId | Ưu tiên đọc qua deferContextual |
| C18 | Token relay WebClient | Call downstream OAuth API | Token/scope đúng theo policy, không auto gửi Bearer |
| C19 | Authentication invalid/expired | Call protected | 401, không tự ghép context giả để vượt |
| C20 | Account disabled sau khi queue job | Worker xử lý sau | Re-check quyền/epoch theo policy, không tin snapshot vô hạn |
| C21 | Login qua WebSession | Request tiếp theo cùng session | Repository lưu đúng reactive authentication |
| C22 | Cùng account trên hai tenant | Concurrent requests | Trusted tenant ID không bị lẫn |
| C23 | Dùng `block()` trên Netty event loop | Exercise handler | Không được block; sửa API/đưa I/O blocking vào boundedElastic |
| C24 | HTTP request POST thiếu CSRF | CSRF filter chặn | Không đổ lỗi “mất React Context” khi auth chưa tới service |
| C25 | Spring MVC app nhầm thành WebFlux | Kiểm runtime và dependency | Chọn SecurityFilterChain đúng stack |
| C26 | Method security reactive | Gọi qua Spring bean proxy | `@PreAuthorize` áp đúng với Mono/Flux |

**Một test pass trong cùng thread chưa đủ.** Đặt tải song song nhiều account/tenant, dùng scheduler switch và kiểm giá trị business authorization; lỗi cross-principal có thể chỉ xuất hiện khi thread reuse. Ở những test HTTP, xác minh 401/403 đến đúng filter/handler thay vì chỉ nhìn status.

## 14. Chẩn đoán từng bước khi production báo mất danh tính

### Bước 1 — Xác nhận runtime thật

- Ứng dụng đang chạy Servlet hay Reactive? Kiểm Boot web application type, dependencies, logs. `WebFlux + Spring MVC starters` có thể khiến app chọn Servlet, dù service có `Mono`.
- Request đã qua **HTTP authentication** thật? Kiểm 401/403/302 và filter chain tương ứng. Chỉ có header Authorization không bảo đảm token hợp lệ.
- Spring Security version bao nhiêu? `SecurityWebFilterChain`/`ReactiveSecurityContextHolder` API trong 6.x khác đời Servlet hoặc 7.x ở vài điểm.

### Bước 2 — So sánh identity ở 3 vị trí

1. Sau authentication WebFilterChain/handler đầu tiên, dùng cách đọc reactive context.
2. Trong service `flatMap`/sau `publishOn`/`subscribeOn`; ở đây phải vẫn thấy cùng account nếu chain đúng.
3. Ở callback ngoài Reactor hoặc bên trong job queue. Nếu identity chỉ mất ở bước 3, xem ranh giới Executor/CompletableFuture; không sửa Spring Security WebFilterChain bừa bãi.

Log **hashed/pseudonymous account ID** và correlation ID nếu policy cho phép, không log raw password/Token. Không dùng value của `Thread.currentThread()` làm danh tính.

### Bước 3 — Soi operator graph

- Có `subscribe()` thủ công, `block()`, `toFuture()`, `CompletableFuture`, nested new `Mono` rồi subscribe riêng không?
- `contextWrite` đặt **sau những operator cần thấy giá trị** theo subscription direction chưa? Có inner `flatMap` bị context scope override không?
- `Mono.just(...)` đọc SecurityContextHolder ở assembly time không?
- Custom reactive filter có tạo publisher mới mà không nối response chain hoặc tự đổi SecurityContext không?
- Có context propagation bridge hoạt động không, và nó chỉ bổ trợ ThreadLocal nào?

### Bước 4 — Kiểm security invariants

- Không bao giờ dùng “nếu auth null thì account=admin” hoặc trust `X-User-ID` tự do từ client.
- Không tái sử dụng một mutable `Authentication` singleton cho nhiều requests.
- Không dùng global/inheritable ThreadLocal để “share currentUser” giữa pool threads.
- Khi công việc chạy sau request, dùng service principal đúng và audit request actor, reauthorize theo policy; không giữ một bearer token tồn tại vô hạn.
- Bất kỳ publisher không có SecurityContext ở route protected phải được xử lý fail closed, không âm thầm bỏ check ownership.
- Kiểm `@PreAuthorize`, security matchers, domain roles/tenant độc lập với propagation.

### Bước 5 — Viết test tái hiện nhỏ nhất

- Test Reactor với hai `StepVerifier` subscriptions Alice/Bob và không context.
- Test `WebTestClient` Basic thật qua WebFlux security chain và method security.
- Đặt `publishOn(Schedulers.parallel())` giữa request và nơi đọc context.
- Test task trên thread pool một thread để bắt stale ThreadLocal (như lab).
- So sánh chạy có/không automatic context bridge; không giả định kết quả mặc định.
- Cuối cùng mới chạy load test nhiều subscribers/threads, kiểm cross-tenant và authorization side effects.

## 15. Những sửa lỗi sai thường khiến hệ thống kém an toàn hơn

| Cách sửa tạm | Tại sao không nên | Hướng sửa |
| --- | --- | --- |
| `SecurityContextHolder.setStrategyName(MODE_GLOBAL)` | Global context giữa request/users, cực nguy hiểm | ReactiveSecurityContextHolder trong WebFlux |
| `MODE_INHERITABLETHREADLOCAL` trên web server | Thread pool reuse, propagation lúc tạo thread không phù hợp | Context-aware execution, không share TL |
| `SecurityContextHolder.getContext().setAuthentication(...)` với username từ query | Caller tự chọn principal, bypass authentication | Dùng trusted AuthenticationManager/WebFilter |
| `onErrorResume(e -> Mono.just("admin"))` khi không có context | Fail-open | Fail closed, 401/403 phù hợp |
| `Mono.just(SecurityContextHolder.getContext()...)` | Đọc identity ngay khi assembly | Dùng ReactiveSecurityContextHolder/deferContextual |
| `doWork().subscribe()` trong controller | Detached subscription, mất lifecycle/context | Trả Mono/Flux được compose |
| `Thread.sleep`/`block()` để ép đồng bộ | Block event loop, che race, giảm throughput | Reactive end-to-end hoặc boundedElastic |
| Bật automatic context hook là xong | Không tạo auth, accessor/version/config có thể thiếu | Test đúng bridge, business auth qua Reactor Context |
| Copy whole SecurityContext sang queue | Principal stale, token leak, quyền cũ tồn tại lâu | Immutable audit identity + reauthorize tại worker |
| Dùng MDC principal để xét quyền | MDC để log, có thể stale/forged | Authentication + authorization chính thức |
| Forward bearer token cho mọi WebClient call | Lộ token sang service không đúng audience | OAuth token relay theo scope/audience |
| Chỉ test `@WithMockUser` | Không chứng minh password/token provider chạy | HTTP Basic/OAuth integration tests |
| Cắt bỏ WebFlux security vì HTTP 403 | Tắt bảo vệ để che lỗi | Chẩn đoán EntryPoint/AccessDenied/CSRF |
| Dùng `subscribeOn(boundedElastic())` cho cả app | Chuyển tất cả sang thread pool không giải quyết scope | Offload chính blocking boundary có chủ đích |

**Lưu ý performance:** Context propagation có chi phí runtime; đo latency/throughput dưới tải và kiểm thread pool exhaustion. Nhưng tuyệt đối không tối ưu bằng cách bỏ security validation hoặc giữ account ID vào static mutable variable.

## 16. Checklist hoàn thành

- [ ] Xác định chính xác ứng dụng chạy Servlet hay WebFlux và security chain được kích hoạt.
- [ ] Trong WebFlux, auth được đọc qua `ReactiveSecurityContextHolder.getContext()` **trong Publisher chain**, không qua `SecurityContextHolder` ThreadLocal.
- [ ] Các `contextWrite` liên quan được đặt đúng subscription scope; `deferContextual` đọc ra giá trị tại thời điểm subscribe.
- [ ] Không có `subscribe()` detached trong controller/service khi logic phải chịu HTTP security lifecycle.
- [ ] Không `block()` Netty event-loop; I/O blocking được offload bằng `boundedElastic` hoặc thay reactive driver.
- [ ] Các ranh giới `CompletableFuture`/Executor/queue chuyển dữ liệu actor đã xác minh một cách tường minh, re-authorize khi chạy muộn.
- [ ] Không dùng `MODE_GLOBAL`, `InheritableThreadLocal` hay ThreadLocal stale để quyết định quyền trong request nhiều người dùng.
- [ ] Micrometer/MDC bridge chỉ được dùng khi dependency/accessor/hook đúng và có cleanup; log không phải nguồn quyết định authorization.
- [ ] WebTestClient test HTTP Basic thật: Alice thấy Alice sau scheduler hop; Admin được phép, Alice thiếu role bị 403; anonymous 401.
- [ ] StepVerifier test cùng publisher nhưng hai subscriber thấy hai principal khác nhau, subscription không auth không thừa hưởng account cũ.
- [ ] Context không tự relay Bearer token sang downstream; OAuth token relay được cấu hình/giới hạn riêng.
- [ ] Có test nhiều tenant/users đồng thời, biết chính xác nơi phát 401/403 và không có side effects khi fail.
- [ ] Dữ liệu nhạy cảm không xuất hiện trong log, static fields, queue payloads hoặc test snapshots.
- [ ] Với custom login/session, ServerSecurityContextRepository và reactive authentication filters lưu/khôi phục đúng context qua request.
- [ ] Sau fix, load test xác nhận không rò danh tính qua reused worker thread và không gây throughput regression.

**Tóm tắt:** Reactor Context **theo Subscriber và subscription**, không phải **theo Thread**. Trong Spring WebFlux, dùng `ReactiveSecurityContextHolder`; việc đổi Scheduler trong Reactor chain đúng không mặc nhiên làm mất danh tính, nhưng đọc `SecurityContextHolder` hoặc dùng detached subscription/Executor ngoài Reactor có thể làm mất hoặc làm rò ThreadLocal. Cần kiểm đúng ranh giới, dùng composition và truyền actor đã xác minh khi đi qua external executor, rồi tiếp tục enforce authorization tại điểm thực thi.

### Tài liệu chính thức và tham khảo

- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — Reactive WebTestClient Authentication Tests](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Security 6.5 — Servlet SecurityContextHolder / ThreadLocal](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
