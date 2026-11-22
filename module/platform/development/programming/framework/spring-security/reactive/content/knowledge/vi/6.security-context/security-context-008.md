# Truyền ngữ cảnh bảo mật qua publishOn, subscribeOn và lời gọi bất đồng bộ

## 1. Mục tiêu học tập

Trong Spring Security Reactive, danh tính người dùng không được gắn vĩnh viễn vào một Java thread. Khi pipeline WebFlux dùng `publishOn`, `subscribeOn`, `flatMap`, timer, I/O reactive hoặc một lời gọi sang API bất đồng bộ khác, request có thể đi qua nhiều thread. Điểm cần giữ nguyên là **ngữ cảnh bảo mật thuộc cùng một Reactor subscription**, không phải tên thread đang chạy.

Sau bài này, bạn có thể:

1. Giải thích `Reactor Context`, `ContextView`, `contextWrite` và `ReactiveSecurityContextHolder`.
2. Phân biệt đổi scheduler bằng `publishOn`/`subscribeOn` với mất ngữ cảnh bảo mật.
3. Đọc `Authentication` trước/sau các ranh giới `flatMap`, `Mono.delay` và `Mono.fromCallable` đúng cách.
4. Tích hợp `CompletableFuture`, `@Async` hoặc callback bên ngoài Reactor mà không tưởng rằng `ThreadLocal` và Reactor Context sẽ tự động xuất hiện bên trong callback.
5. Nhận diện subscription bị tách do gọi `subscribe()`, cũng như lỗi đặt `contextWrite` sai vị trí.
6. Xây một ứng dụng Spring WebFlux Java 17+ và kiểm thử HTTP 401, tính nhất quán identity qua scheduler và tính cô lập giữa người dùng.

Phạm vi là **ngữ cảnh bảo mật của Spring Security trong WebFlux**. Ví dụ dùng Spring Boot 3.x, Spring Security 6.x, Project Reactor 3.x và Java 17+. Các cơ chế truyền tracing/MDC/ThreadLocal được phân biệt rõ với security context, vì chúng có vòng đời và mục đích khác nhau.

## 2. Vì sao ThreadLocal không còn là giả định đúng?

Ở ứng dụng Servlet truyền thống, Spring Security thường truy cập security context qua `SecurityContextHolder`; chiến lược mặc định của nó dựa vào `ThreadLocal`. Trong nhiều đoạn xử lý đồng bộ, thread phục vụ request giữ context ở thời điểm đoạn code chạy. Khi tự chuyển sang `Executor`, `@Async` hoặc thread khác, việc sao chép context không thể được giả định.

Trong Spring WebFlux, handler có thể bắt đầu trên một thread nhưng tiếp tục sau `publishOn`, `delayElement`, callback network hoặc scheduler khác. Một thread trong event loop phục vụ nhiều request theo thời gian, nên nếu lưu principal vào một biến `ThreadLocal` thủ công, có thể thấy `null` hoặc identity sai khi code đổi thread và có nguy cơ rò rỉ danh tính nếu quản lý vòng đời không đúng.

Spring Security Reactive dùng **`ReactiveSecurityContextHolder` và Reactor Context**:

```java
// Trích đoạn trong một bean WebFlux; không phải Java class độc lập.
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(authentication -> authentication.getName());
}
```

Import: `reactor.core.publisher.Mono` và `org.springframework.security.core.context.ReactiveSecurityContextHolder`. Khi không có context, publisher thường hoàn tất rỗng; ví dụ không tự quyết định user là ai. Trong một HTTP endpoint cần authentication, hãy để `SecurityWebFilterChain` xác thực và phân quyền trước khi controller dùng context.

**Nguyên tắc:** Reactor Context đi theo subscription và được các operator Reactor hỗ trợ truyền qua. Nó không đồng nhất với Java `ThreadLocal`; nó cũng không tự trở thành header truyền qua HTTP, sự kiện Kafka hay dữ liệu bên trong một `CompletableFuture` tùy ý.

## 3. Reactor Context thuộc subscriber, không phải Thread

`Context` là cấu trúc ánh xạ key/value bất biến theo cách sử dụng (mỗi `put` tạo một context mới). `ContextView` là giao diện đọc. Mỗi subscription có ngữ cảnh riêng và các operator Reactor có thể truy cập qua `Mono.deferContextual` hoặc `Flux.deferContextual`.

Ví dụ Reactor thuần:

```java
Mono<String> query = Mono.deferContextual(ctx ->
    Mono.just(ctx.getOrDefault("traceId", "missing"))
);

Mono<String> request = query
    .contextWrite(ctx -> ctx.put("traceId", "REQ-42"));

// Nếu block() ở bài demo chạy ngoài event-loop:
// request.block() trả "REQ-42".
```

Đây là mảnh code có import `reactor.core.publisher.Mono`, dùng `block()` **chỉ trong chương trình thử nghiệm hoặc kiểm thử**, không dùng trong WebFlux handler.

### 3.1. Hướng truyền của `contextWrite`

Reactor Context được gắn lúc subscribe và về mặt logic **truyền từ subscriber phía cuối chuỗi lên các operator phía trước**. Vì vậy vị trí `contextWrite` quan trọng:

```java
Mono<String> present = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("key", "missing")))
    .contextWrite(ctx -> ctx.put("key", "value"));
// present.block() -> "value"
```

So sánh với trường hợp đặt ngoài phạm vi operator muốn đọc:

```java
Mono<String> absent = Mono.just(1)
    .contextWrite(ctx -> ctx.put("key", "value"))
    .flatMap(n -> Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("key", "missing"))));
// absent.block() -> "missing"
```

Ở ví dụ `absent`, `contextWrite` chỉ thay context **về phía upstream của chính nó**; `flatMap` đặt phía sau không tự nhận entry `key`. Đừng hiểu ngữ cảnh là biến toàn cục được gán một lần cho toàn bộ ứng dụng.

### 3.2. Spring Security lưu context theo cơ chế nào?

Spring Security dùng key và cơ chế nội bộ thông qua `ReactiveSecurityContextHolder`. Ứng dụng không nên tự đoán key của security context hay thay bằng `Context.of("user", name)` rồi kỳ vọng authorization hiểu nó. Dùng API chính thức:

```java
Authentication authentication =
    UsernamePasswordAuthenticationToken.authenticated(
        "alice",
        "not-an-http-password",
        List.of(new SimpleGrantedAuthority("ROLE_USER"))
    );

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );
```

Import: `Authentication`, `UsernamePasswordAuthenticationToken`, `SimpleGrantedAuthority`, `List` và `Mono`. Đây là **mảnh code phục vụ unit test/mô phỏng nội bộ có identity đã được tin cậy**. Trong HTTP server thật, không tạo `Authentication` từ input/header tự khai rồi gọi `withAuthentication` để bỏ qua authentication; Spring Security WebFlux cần xác thực request và thiết lập context.

`ReactiveSecurityContextHolder.withAuthentication(authentication)` cung cấp một `Context` có authentication được bọc trong security context theo API Spring Security. `.contextWrite(...)` gắn nó cho phạm vi upstream của publisher, **không** sửa global static state hoặc mọi request về sau.

## 4. `publishOn`: chuyển nơi chạy downstream, không chuyển identity sang ThreadLocal

`publishOn(Scheduler)` ảnh hưởng luồng xử lý **tín hiệu downstream sau vị trí operator**, cho đến khi có một `publishOn` khác; nó thường đổi thread thực thi các callback phía sau. Nó không phải là API đăng nhập, không tự gắn security context vào ThreadLocal, cũng không cố định request vào một thread.

Ví dụ:

```java
Mono<String> display = username()
    .publishOn(Schedulers.parallel())
    .flatMap(before -> username()
        .map(after -> before + "|" + after));
```

Ở đây `username()` là method trả `ReactiveSecurityContextHolder.getContext().map(...)` nằm trong cùng reactive service, không phải API Java có sẵn; code đầy đủ ở mục 8.

Nếu security context tồn tại trong **subscription** của publisher, cả lần đọc trước và sau `publishOn` đều nhận cùng principal, dù hai đoạn code có thể chạy trên các thread khác nhau. Chúng có thể tình cờ cùng thread trong môi trường nhỏ; vì vậy **không dùng việc so sánh tên thread làm bằng chứng đúng/sai về context propagation**.

`Schedulers.parallel()` thích hợp cho tác vụ CPU ngắn, không dành cho JDBC blocking, file I/O đồng bộ kéo dài hoặc `Thread.sleep`. Reactor Context có thể vẫn đúng nhưng hệ thống vẫn bị nghẽn nếu chạy blocking code trên `parallel`/Netty event-loop.

## 5. `subscribeOn`: thay lịch subscription, không tạo context mới

`subscribeOn(Scheduler)` ảnh hưởng nơi công việc **subscribe/request tới nguồn** được lên lịch. Nó có ý nghĩa khác `publishOn`:

| Tiêu chí | `publishOn` | `subscribeOn` |
|---|---|---|
| Tác động chính | Chuyển cách phân phối tín hiệu từ vị trí đó về downstream | Lên lịch subscription/source request |
| Vị trí thường dùng | Trước các operator muốn chuyển thread xử lý | Gần nguồn blocking/nguồn cần schedule đặc thù |
| Ảnh hưởng security context | Bản thân nó không xóa Reactor Context | Bản thân nó không xóa Reactor Context |
| Có tạo identity mới không? | Không | Không |
| Có tự chuyển `ThreadLocal` thông thường không? | Không bảo đảm | Không bảo đảm |
| Có làm I/O blocking thành non-blocking không? | Không | Không; chỉ chuyển công việc sang scheduler khác |

Ví dụ một nguồn `Mono.fromCallable` mang công việc đồng bộ:

```java
Mono<Integer> value = Mono.fromCallable(() -> 7)
    .subscribeOn(Schedulers.boundedElastic());

Mono<String> result = value
    .flatMap(n -> username()
        .map(name -> name + ":" + n));
```

`boundedElastic` giới hạn số thread/queue theo thiết kế của Reactor và là một cách **cô lập một đoạn blocking legacy**. Nó vẫn tiêu thụ thread; không biến database driver đồng bộ thành reactive. Nếu có API non-blocking thật như `WebClient` hoặc R2DBC, ưu tiên compose publisher đó.

Cần phân biệt hai tầng: **Reactor Context được truyền qua publisher**, nhưng code Java đồng bộ chạy trong callable không được bảo đảm đọc thấy cùng identity qua `SecurityContextHolder`. Muốn callable cần username, lấy nó bằng `ReactiveSecurityContextHolder` **trước khi tạo callable**, rồi truyền vào bằng tham số/captured immutable value được phép:

```java
return username().flatMap(name ->
    Mono.fromCallable(() -> legacyService.loadFor(name))
        .subscribeOn(Schedulers.boundedElastic())
);
```

Đây là đoạn minh họa trong method trả `Mono<...>`, với `legacyService` được inject và có chính sách kiểm soát quyền phù hợp. Nếu `loadFor` xử lý dữ liệu nhạy cảm, chỉ truyền tên người dùng là chưa đủ để đảm bảo authorization; service và tầng dữ liệu vẫn phải kiểm tra đúng quyền đã xác minh.

### 5.1. Đặt nhiều `subscribeOn` có giúp truyền context tốt hơn?

Không. Vị trí và hiệu lực scheduling của nhiều `subscribeOn` có thể không trực quan; chỉ call gần nguồn cần điều phối để code dễ hiểu. Đừng thêm `subscribeOn(Schedulers.parallel())` khắp mọi nơi nhằm “giữ security context”. Context được giữ nhờ publisher trong cùng subscription; thay scheduler không tự giải quyết việc code ngoài Reactor không có context.

## 6. `flatMap`, timer và I/O reactive: điều gì được bảo toàn?

`flatMap` subscribe một publisher bên trong và Reactor truyền context của subscriber theo cơ chế operator. `Mono.delay` tạo tín hiệu bằng scheduler, và `WebClient`/reactive I/O có thể hoàn tất sau khi thread khác làm việc. Khi vẫn compose các publisher trong **một request pipeline** thì `ReactiveSecurityContextHolder.getContext()` có thể lấy identity ở các đoạn phù hợp.

Ví dụ:

```java
return username()
    .flatMap(before ->
        Mono.delay(Duration.ofMillis(10))
            .then(username())
            .map(after -> before + "|" + after)
    )
    .publishOn(Schedulers.parallel());
```

Mảnh code này dùng `java.time.Duration`, `reactor.core.scheduler.Schedulers` và một method `username()`; nó trả `Mono<String>`. Với principal đã xác thực là `alice` và ngữ cảnh không bị cắt, kết quả là `alice|alice`. Nên kiểm thử **giá trị danh tính** thay vì thread name hoặc trật tự log không ổn định.

**Lưu ý về kết nối sang service khác:** Nếu `WebClient` gửi HTTP tới downstream service, **Reactor Context không tự truyền qua network**. Service phía kia nhận request mới, có một security boundary mới; nó chỉ biết user nếu có credential/token hợp lệ và policy xác minh, hoặc một cơ chế trusted delegation được thiết kế. Đừng xem `contextWrite` trong caller là một cách “đăng nhập” tự động ở remote service.

## 7. Ranh giới ngoài Reactor: CompletableFuture, @Async, callback và subscribe tách biệt

Đây là phần dễ tạo lỗi tinh vi nhất. Reactor Context không phải dữ liệu tự động có trong mọi callback chạy ở executor ngoài Reactor.

### 7.1. `CompletableFuture.supplyAsync` không thừa hưởng context như một Reactor operator

Xem hai pha tách biệt:

```text
HTTP Request (đã xác thực)
    |
    v
Reactor pipeline: ReactiveSecurityContextHolder.getContext()
    | -> xác định user đã được Spring Security xác thực
    v
CompletableFuture.supplyAsync(() -> externalWork(user))
    | -> callback Java chạy trên executor riêng
    | -> KHÔNG giả định Reactor Context hay SecurityContextHolder ở đây
    v
Mono.fromFuture(...) nối completion vào pipeline
    |
    v
flatMap/ReactiveSecurityContextHolder.getContext()
    -> đọc context trên continuation thuộc subscription Reactor
```

Cách tích hợp an toàn cho trường hợp đơn giản:

```java
return username().flatMap(caller ->
    Mono.fromFuture(() ->
            CompletableFuture.supplyAsync(
                () -> "loaded-for-" + caller))
        .flatMap(result ->
            username().map(inContext ->
                result + "|" + inContext))
);
```

Đây là mảnh code trong service/controller, cần import `java.util.concurrent.CompletableFuture`. Cụm `"loaded-for-" + caller` chỉ đại diện phép tính non-blocking nhẹ để minh họa. `Mono.fromFuture(Supplier)` tạo future **lúc subscribe**, giúp tránh eager side effect ở thời điểm lắp publisher; mặc định việc cancel từ Mono có thể cancel future theo hợp đồng Reactor. Với tác vụ blocking thật, hãy dùng executor riêng có giới hạn/cơ chế backpressure hoặc adapter blocking phù hợp. `CompletableFuture.supplyAsync` không phải phương pháp mặc định tốt cho mọi I/O trong WebFlux.

Ở ví dụ trên, callback trong `supplyAsync` **nhận giá trị `caller` tường minh**, không cố lấy principal từ ThreadLocal. Sau `Mono.fromFuture(...)`, đoạn `flatMap` tiếp tục là operator Reactor nên `username()` có thể đọc lại context của subscription. Điều đó không có nghĩa code **bên trong** future cũng thấy context.

### 7.2. `@Async` và Executor

Một method Spring `@Async` hoặc một task gửi bằng `Executor.submit` thường chạy trong thread pool ngoài reactive subscription. Đừng viết:

```java
@Async
public CompletableFuture<String> load() {
    String user =
        SecurityContextHolder.getContext()
            .getAuthentication().getName(); // KHÔNG đáng tin trong WebFlux
    return CompletableFuture.completedFuture(user);
}
```

Đây là snippet lỗi minh họa, không nên sử dụng. Thay bằng API nhận identity đã xác minh như **dữ liệu đầu vào**:

```java
@Async
public CompletableFuture<String> load(String authenticatedUser) {
    return CompletableFuture.completedFuture(
        "loaded-for-" + authenticatedUser);
}
```

Đoạn này là method trong bean `@Async` phù hợp, không phải class Java độc lập. Bên gọi lấy identity từ `ReactiveSecurityContextHolder` trong pipeline, kiểm tra authorization và truyền tham số cần thiết. Nếu cần truyền nhiều quyền/metadata, thiết kế một object bất biến phù hợp và rõ ranh giới tin cậy; không lưu toàn bộ token/mật khẩu vào log hoặc truyền security context tùy ý tới worker chạy lâu hơn request.

### 7.3. Vì sao tự gọi `subscribe()` làm “mất context”?

Sai trong handler WebFlux:

```java
public Mono<String> broken() {
    username().subscribe(name -> audit(name));
    return Mono.just("queued");
}
```

*Đây là đoạn minh họa với `audit` đã có.* `subscribe()` này tạo một subscription riêng; nó không được framework WebFlux quản lý như chuỗi được return và **không bảo đảm nhận context của request subscription bên ngoài**. Nó còn tách lifecycle error/cancel, có thể để tác vụ chạy sau khi client đóng kết nối hoặc request kết thúc.

Đúng với công việc cần nằm trong request:

```java
public Mono<String> connected() {
    return username()
        .flatMap(name -> auditReactive(name).thenReturn("queued"));
}
```

Ở đây `auditReactive(String)` là service trả `Mono<Void>` (ví dụ audit non-blocking). Nếu audit phải chạy độc lập như một job bền vững, hãy đưa yêu cầu đã được kiểm chứng vào queue/job có identity và quyền rõ ràng, idempotency/expiry phù hợp và quyền được kiểm tra lại ở worker. Không hy vọng Reactor Context tự tồn tại suốt đời của job.

### 7.4. Không tự sửa Context để giả mạo xác thực

Trong unit test, có thể gọi `contextWrite(ReactiveSecurityContextHolder.withAuthentication(testAuthentication))`. Nhưng trong production, một giá trị username lấy từ `X-User`, query parameter hoặc JSON body **không** được tự biến thành một `Authentication` trusted rồi gắn vào Reactor Context. Security filter phải xác minh credential, chữ ký/issuer/audience token, session hoặc cơ chế được tin cậy, và authorization vẫn phải chạy. Propagation là **truyền danh tính đã xác minh**, không phải tạo quyền mới.

## 8. Bài thực hành Spring Boot WebFlux chạy được

Ta xây dựng ứng dụng WebFlux có HTTP Basic với hai user demo. Nó cung cấp `GET /chain`, dùng `publishOn`, `subscribeOn`, timer và `boundedElastic` rồi đọc lại username; `GET /future` minh họa lời gọi `CompletableFuture` và quay lại Reactor pipeline. Cả hai yêu cầu authentication.

### 8.1. Khởi tạo project và dependencies

Từ [Spring Initializr](https://start.spring.io/), tạo Gradle project Spring Boot 3.x với Java 17+ và dependencies **Spring Reactive Web**, **Spring Security**, **Spring Boot Starter Test**, **Spring Security Test**. Trong `build.gradle` do Initializr tạo, phần dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây là **mảnh dependencies**, cần giữ các plugin Spring Boot, dependency management, repositories, toolchain Java và Gradle wrapper do Initializr cung cấp. Không thêm `spring-boot-starter-web` vào demo nếu muốn inbound server là WebFlux; khi cả MVC và WebFlux starters có mặt, Spring Boot 3.x mặc định ưu tiên MVC.

Bố cục file:

```text
src/main/java/demo/contextpropagation/
  ContextPropagationApplication.java
  SecurityConfig.java
  ContextController.java
src/test/java/demo/contextpropagation/
  ContextControllerTests.java
  StandaloneContextTests.java
```

### 8.2. Entry point

Tạo `src/main/java/demo/contextpropagation/ContextPropagationApplication.java`:

```java
package demo.contextpropagation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextPropagationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextPropagationApplication.class, args);
    }
}
```

`@SpringBootApplication` quét bean trong package `demo.contextpropagation` và package con; ba class chính dùng cùng package.

### 8.3. Security filter chain và user store

Tạo `src/main/java/demo/contextpropagation/SecurityConfig.java`:

```java
package demo.contextpropagation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/chain", "/future").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }
}
```

Spring Security WebFlux xác thực HTTP Basic rồi đưa `SecurityContext` vào Reactor Context của request; controller **không tự tạo** một user bằng `contextWrite`. `alice-pass` và `bob-pass` là credential giả dành riêng cho bài học. Trong sản phẩm thật dùng HTTPS, nguồn identity thực và bảo mật credential; HTTP Basic chỉ Base64 hóa credential trong header, không mã hóa đường truyền.

### 8.4. Controller quan sát context sau scheduler và Future

Tạo `src/main/java/demo/contextpropagation/ContextController.java`:

```java
package demo.contextpropagation;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class ContextController {

    private Mono<String> username() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }

    @GetMapping("/chain")
    public Mono<String> chain() {
        return username()
            .publishOn(Schedulers.parallel())
            .flatMap(first ->
                Mono.delay(Duration.ofMillis(10))
                    .then(username())
                    .map(second -> first + "|" + second))
            .flatMap(prefix ->
                Mono.fromCallable(() -> 7)
                    .subscribeOn(Schedulers.boundedElastic())
                    .flatMap(value -> username()
                        .map(third -> prefix + "|" + third + "|" + value)))
            .subscribeOn(Schedulers.parallel());
    }

    @GetMapping("/future")
    public Mono<String> future() {
        return username()
            .flatMap(caller ->
                Mono.fromFuture(() -> CompletableFuture.supplyAsync(
                        () -> "loaded-for-" + caller))
                    .flatMap(result -> username()
                        .map(inContext -> result + "|" + inContext)));
    }
}
```

Đây là **class chạy được** trong project đã khai báo dependency ở trên. Giải thích từng chặng `/chain`:

1. `username()` đọc principal đã xác thực từ Reactor Context.
2. `publishOn(Schedulers.parallel())` chuyển các signal downstream qua scheduler `parallel`, không đổi user.
3. `Mono.delay(10ms)` tạo bước bất đồng bộ có scheduler. Sau `then(username())`, context vẫn được đọc trong cùng subscription.
4. `Mono.fromCallable(() -> 7).subscribeOn(Schedulers.boundedElastic())` đại diện cho một công việc đồng bộ nhỏ trên bounded elastic scheduler. Số 7 cố định giúp dễ kiểm tra, không chứng minh I/O blocking “biến thành” reactive.
5. `flatMap(value -> username()...)` đọc context lần nữa sau công việc đã được lên lịch.
6. `subscribeOn(Schedulers.parallel())` nằm ở pipeline ngoài, ảnh hưởng lịch subscription của source; nó không phải “bật” context propagation, vì context đã được Spring Security cung cấp.

Với HTTP Basic username `alice`, response `/chain` dự kiến chính xác:

```text
alice|alice|alice|7
```

Với `bob`:

```text
bob|bob|bob|7
```

Không khẳng định hai lần đọc chạy trên cùng một thread, cũng không yêu cầu log thread name giống nhau. Bằng chứng cần kiểm tra là **principal nhất quán** và **không lẫn giữa các request**.

Ở `/future`, `CompletableFuture.supplyAsync` tạo kết quả bằng cách nhận giá trị `caller` được lấy từ context trước đó. Code **bên trong future không truy cập security context**. Sau khi future hoàn thành và `Mono.fromFuture` phát giá trị, `flatMap` quay lại reactive publisher và có thể đọc context trong cùng subscription. Với Alice, response:

```text
loaded-for-alice|alice
```

Cấu trúc `Mono.fromFuture(() -> ...)` trì hoãn việc tạo future đến subscription. Nó phù hợp để minh họa bridge; với tác vụ production, phải cân nhắc executor có giới hạn, timeout, cancellation, idempotency và việc kiểm tra quyền trong backend thực hiện công việc. Không để future tự do sử dụng common pool cho I/O blocking quy mô lớn.

### 8.5. Chạy HTTP

Từ thư mục root project Gradle đã tạo:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Gửi request sau khi server lắng nghe ở `localhost:8080`:

```bash
curl -i http://localhost:8080/chain
curl -i -u alice:alice-pass http://localhost:8080/chain
curl -i -u bob:bob-pass http://localhost:8080/chain
curl -i -u alice:alice-pass http://localhost:8080/future
```

Trên Windows PowerShell, dùng `curl.exe` thay cho `curl` nếu shell ánh xạ alias khác. Bảng kiểm chứng:

| Yêu cầu | HTTP dự kiến | Body dự kiến khi thành công |
|---|---:|---|
| `GET /chain` không Authorization | `401` | Không cố định |
| `GET /chain` với Alice | `200` | `alice|alice|alice|7` |
| `GET /chain` với Bob | `200` | `bob|bob|bob|7` |
| `GET /future` với Alice | `200` | `loaded-for-alice|alice` |

Header `WWW-Authenticate`, body của response lỗi và log request thay đổi theo server/version. Kết quả bắt buộc về bảo mật là khách chưa xác thực không được truy cập endpoint và identity không biến thành người khác sau scheduler/future bridge.

## 9. Kiểm thử tự động không phụ thuộc thread name

### 9.1. HTTP integration tests với WebTestClient

Tạo `src/test/java/demo/contextpropagation/ContextControllerTests.java`:

```java
package demo.contextpropagation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ContextControllerTests {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousRequestIsRejected() {
        client.get().uri("/chain")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void aliceKeepsIdentityAcrossSchedulers() {
        client.get().uri("/chain")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("alice|alice|alice|7");
    }

    @Test
    void bobDoesNotInheritAliceIdentity() {
        client.get().uri("/chain")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("bob|bob|bob|7");
    }

    @Test
    void futureBridgeRejoinsReactorContext() {
        client.get().uri("/future")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("loaded-for-alice|alice");
    }
}
```

Đây là class JUnit 5 dùng server ngẫu nhiên để kiểm tra **HTTP thật qua Spring Security chain**. Username được xác thực bằng user store demo và trải qua chính controller đang dùng scheduler. Test không đoán thread name, nên ổn định hơn assert scheduler thread cụ thể.

### 9.2. Unit test độc lập với `contextWrite` và StepVerifier

Bản thân Spring Security cấp context trong WebFlux server. Khi cần test một **publisher/service độc lập**, bạn có thể gắn authentication **giả lập đã tin cậy** trong phạm vi subscription bằng `withAuthentication`.

Tạo `src/test/java/demo/contextpropagation/StandaloneContextTests.java`:

```java
package demo.contextpropagation;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class StandaloneContextTests {

    private Mono<String> username() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }

    @Test
    void testContextSurvivesSchedulerBoundaries() {
        Authentication alice =
            UsernamePasswordAuthenticationToken.authenticated(
                "alice", "unused",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));

        Mono<String> pipeline = username()
            .publishOn(Schedulers.parallel())
            .flatMap(first -> Mono.delay(Duration.ofMillis(5))
                .then(username())
                .map(second -> first + "|" + second))
            .subscribeOn(Schedulers.boundedElastic())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice));

        StepVerifier.create(pipeline)
            .expectNext("alice|alice")
            .verifyComplete();
    }

    @Test
    void withoutContextThereIsNoImplicitPrincipal() {
        StepVerifier.create(username())
            .verifyComplete();
    }
}
```

Ở test đầu, `withAuthentication(alice)` có hiệu lực với publisher **upstream** trong subscription. Test thứ hai không gắn context, nên `ReactiveSecurityContextHolder.getContext()` hoàn tất rỗng; identity từ test đầu không bị lưu ở biến global. Cả hai case không chứng minh framework tự kiểm tra mật khẩu; đó là việc của security chain trong HTTP tests.

Chạy trong project Gradle:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Kỳ vọng 6 test pass: 4 integration tests và 2 unit tests. Không giả định stdout Gradle/JUnit vì tên task, thời gian và cấu hình log có thể khác. Nếu kiểm thử không chạy, kiểm tra Java toolchain, Spring Boot plugin, dependency `reactor-test` và package/classpath đúng như code.

## 10. Context đi qua nhiều lớp service như thế nào?

Giả sử controller gọi `OrderService`, rồi `PermissionService`, rồi repository reactive:

```text
SecurityWebFilterChain xác thực request
  -> Reactor Context có Authentication
  -> Controller trả Mono
       -> OrderService.readOrders()
           -> flatMap(...)
           -> PermissionService.check()
               -> ReactiveSecurityContextHolder.getContext()
           -> R2DBC/WebClient (reactive publisher)
       -> Reactor pipeline hoàn thành
  -> WebFlux ghi HTTP response
```

Khi service **trả Publisher** để WebFlux/framework compose và subscribe, context tiếp tục nằm trong subscription nếu operator và adapter truyền đúng. Vì vậy API service reactive nên ưu tiên `Mono<T>`/`Flux<T>`, tránh `void` method tự subscribe, vì caller sẽ mất cách chờ kết quả, lỗi và cancellation.

Một method business có thể đọc Authentication:

```java
public Mono<String> readForCurrentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication())
        .flatMap(auth -> repository.findByOwner(auth.getName()))
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No permitted data")));
}
```

Đây là **mã thiết kế minh họa**, giả sử `repository.findByOwner` trả `Mono<String>` và chỉ được gọi sau HTTP authentication/authorization. Với yêu cầu dữ liệu thật, kiểm tra quyền truy cập resource ở service/repository thay vì tin rằng một `auth.getName()` bất kỳ cho phép xem mọi record. Việc `switchIfEmpty` trả exception chỉ minh họa luồng rỗng, không phải gợi ý dùng 500 cho mọi trường hợp không có dữ liệu. Trong production hãy tách “chưa xác thực”, “không được phép”, “không tìm thấy” bằng policy rõ.

### 10.1. Method security cũng dựa vào Reactor Context

Spring Security Reactive method security có thể dùng `@EnableReactiveMethodSecurity` và `@PreAuthorize` với method trả publisher:

```java
// Trích đoạn service; cần @EnableReactiveMethodSecurity ở configuration.
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<String> readReport() {
    return repository.findReport();
}
```

Không dùng `@EnableMethodSecurity` theo cách Servlet rồi giả định sẽ tự hoạt động tương đương cho WebFlux reactive method. `@EnableReactiveMethodSecurity` lấy security context từ Reactor Context để kiểm tra quyền trong quá trình subscription. Trong ví dụ test HTTP Basic ở mục 8 chỉ có role `ROLE_USER`, chưa có `SCOPE_orders.read`; muốn chạy snippet này phải cấu hình authorities thật phù hợp.

## 11. Phân biệt tracing/MDC với ngữ cảnh bảo mật

Có hai câu hỏi khác nhau:

- **Security context:** “Ai là người đã được xác thực, có authorities nào, và đang thuộc request/subscription nào?” Truy cập qua `ReactiveSecurityContextHolder` trong reactive pipeline.
- **Observability context:** “traceId/spanId/requestId nào cần thấy trong logs, metrics và tracing xuyên qua các thao tác?” Có thể tích hợp Reactor Context với Micrometer Context Propagation, OpenTelemetry hoặc MDC theo cấu hình.

Reactor hỗ trợ tích hợp `io.micrometer:context-propagation` và có chế độ **automatic context propagation** như `Hooks.enableAutomaticContextPropagation()`. Trong các phiên bản Reactor 3.x hỗ trợ nó, cơ chế này có thể khôi phục các `ThreadLocal` **đã đăng ký accessor tương ứng** từ Reactor Context ở những thời điểm thích hợp; cần dependency và cấu hình được kích hoạt trước các subscription muốn áp dụng. Điều đó **không** có nghĩa:

- Mọi `ThreadLocal` tùy ý đột nhiên truyền qua mọi thread và mọi `Executor`.
- Một `CompletableFuture.supplyAsync` độc lập có quyền đọc Reactive Security Context trong callback.
- Mọi lời gọi `subscribe()` tách rời đều mang context của HTTP request.
- Có thể bỏ xác thực/authorization khi gửi request sang service khác.
- Nên bật hook toàn cục chỉ để “sửa” một đoạn code đang đọc sai `SecurityContextHolder`.

Khi cần security context bên trong Reactor, cách chuẩn vẫn là `ReactiveSecurityContextHolder.getContext()`. Cầu nối ThreadLocal dùng cho framework hoặc thư viện legacy cần kiểm thử riêng với cấu hình cụ thể, bảo đảm cleanup và tránh rò rỉ identity giữa các request dùng chung pool.

## 12. Chẩn đoán mất context trong hệ thống thực tế

Khi gặp `ReactiveSecurityContextHolder.getContext()` trả rỗng hoặc principal không như kỳ vọng:

1. **Kiểm tra inbound stack và authentication.** Server thật là WebFlux hay MVC? Có `SecurityWebFilterChain` và `ReactorContextWebFilter` phù hợp không? Endpoint có yêu cầu authenticated hay đang permitAll? Nếu chưa có identity hợp lệ, không có context là kết quả hợp lý.
2. **Tìm `subscribe()` thủ công.** Một task fire-and-forget thường tạo subscription tách rời, không được WebFlux quản lý.
3. **Xem chỗ bắc cầu sang `CompletableFuture`/`@Async`/callback.** Có đang đọc `SecurityContextHolder` trong callback ngoài Reactor không? Nếu cần identity, lấy trong pipeline và truyền giá trị tường minh.
4. **Kiểm tra scope của `contextWrite`.** `Context` được cung cấp cho upstream; operator đọc ở downstream có thể không thấy entry vừa đặt.
5. **Kiểm tra custom publisher/adapters.** Nếu dùng thư viện không phải Reactor hoặc tạo publisher mới bằng cách không bảo toàn subscriber context, cần kiểm tra adapter và đảm bảo các cuộc gọi được compose.
6. **Kiểm tra thao tác chặn event-loop.** Ngữ cảnh đúng không bảo đảm hiệu năng; `block()` hoặc I/O đồng bộ không phù hợp có thể gây timeout rồi làm bạn tưởng “mất context”.
7. **Test hai user đồng thời hoặc xen kẽ.** Assertion identity Alice/Bob nên dựa trên principal của mỗi request, không phụ thuộc thread name. Tuyệt đối tránh lưu `Authentication` vào static field/cache dùng chung rồi lấy làm “current user”.
8. **Kiểm tra security policy sau khi có principal.** Có context không đồng nghĩa có quyền vào mọi endpoint; authentication và authorization là hai bước. Rule JWT scope/role vẫn phải được áp dụng và audit.
9. **Phân biệt context cục bộ với remote boundary.** Reactor Context không vượt qua TCP/HTTP/Kafka tự động. Nếu service downstream cần identity, thiết kế delegation token/trust và xác minh tại phía nhận.
10. **Quan sát cancel và error.** Nếu request đã bị hủy, một job nền không nên tiếp tục với context cũ vô thời hạn; thiết kế timeout/cancellation đúng và quyền xử lý độc lập cho background task.

### Các lỗi điển hình

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `username()` rỗng trong handler GET | Chưa có authentication hoặc publisher chạy ngoài request subscription | Kiểm tra security chain, cơ chế gọi và subscription |
| `SecurityContextHolder` trả `null` sau `publishOn` | Dùng ThreadLocal trong reactive pipeline | Dùng `ReactiveSecurityContextHolder` |
| `username()` đúng trước/sau `flatMap` nhưng rỗng trong Future callback | Future callback ngoài Reactor | Truyền identity đã xác minh như tham số |
| Test gắn `withAuthentication` pass nhưng endpoint thực trả 401 | Test chỉ giả lập context, không kiểm tra HTTP Basic/token | Viết WebTestClient integration test qua security chain |
| Hai request lẫn username | Lưu identity vào static/field mutable singleton hoặc ThreadLocal quản lý sai | Giữ dữ liệu theo subscription, không lưu vào global state |
| `contextWrite` không tác dụng tại `flatMap` sau nó | Entry chỉ áp dụng upstream | Đặt `contextWrite` đúng phạm vi và dùng `deferContextual` để test |
| Cần log traceId nhưng MDC trống | Không có bridge/accessor cho ThreadLocal | Kiểm tra Micrometer context propagation và lifecycle |
| Một task `@Async` vẫn dùng user của request cũ | Task chạy lâu, truyền identity tùy tiện hoặc có rò rỉ TL | Thiết kế job context/expiry/authorization riêng |
| `Mono.fromCallable` dùng `boundedElastic` nhưng thread vẫn chiếm lâu | Blocking adapter chưa thực sự non-blocking | Giới hạn concurrency, chuyển qua API reactive thật khi phù hợp |

## 13. Bài tập và đáp án

**Bài 1 — `publishOn` có làm mất người dùng không?** Một pipeline có `ReactiveSecurityContextHolder.getContext()` trước và sau `publishOn(Schedulers.parallel())`, mọi bước nằm trong subscription WebFlux đã xác thực. Có cần tự copy `SecurityContext` vào `ThreadLocal`?

**Đáp án:** Không. Trong cùng chuỗi Reactor được compose đúng, context đi theo subscriber qua scheduler. Nếu code sau `publishOn` đang dùng `SecurityContextHolder` ThreadLocal thì phải sửa cách đọc, không tự copy identity vô điều kiện.

**Bài 2 — `subscribeOn` có tạo authentication mới không?** Thêm `subscribeOn(Schedulers.boundedElastic())` vào một publisher không có context.

**Đáp án:** Không. `subscribeOn` chọn scheduler cho subscription/source; nó không tự đăng nhập hoặc sinh `Authentication`. Muốn có context, request phải được Spring Security xác thực hoặc test chủ động cung cấp context đáng tin cho đúng subscription.

**Bài 3 — Trong `CompletableFuture.supplyAsync` có thể gọi `ReactiveSecurityContextHolder.getContext().block()` để lấy user không?**

**Đáp án:** Không nên. Reactor Context của HTTP request không tự xuất hiện trong callback bên ngoài, và gọi `block()` không phục hồi điều đã thiếu. Đọc user trong pipeline Reactor trước khi tạo Future, truyền tham số được kiểm soát, rồi quay lại pipeline bằng `Mono.fromFuture`.

**Bài 4 — Vì sao một `contextWrite(ctx -> ctx.put("id", "R1"))` không luôn hiển thị ở operator phía sau?**

**Đáp án:** ContextWrite áp dụng cho upstream khi subscription đi ngược chuỗi; operator nằm downstream có thể không nằm trong phạm vi của thay đổi. Dùng `Mono.deferContextual` đúng vị trí để xác minh.

**Bài 5 — Một controller tự gọi `auditMono.subscribe()` rồi trả `Mono.just("ok")`. Rủi ro?**

**Đáp án:** Tạo subscription độc lập; lỗi, context, cancellation và vòng đời HTTP có thể không theo nhau. Compose bằng `flatMap`/`then`. Nếu cần job bền vững, đưa event đã được xác thực vào queue với quyền rõ ràng thay vì dựa vào request context.

**Bài 6 — Có nên bật `Hooks.enableAutomaticContextPropagation()` để sửa tất cả security bugs?**

**Đáp án:** Không. Đây là công cụ bridge Reactor Context với các ThreadLocal đã đăng ký qua context-propagation, chủ yếu phục vụ tích hợp thư viện; không thay đổi contract authentication, không tự truyền context vào mọi future/callback hay remote service. Dùng `ReactiveSecurityContextHolder` cho code Reactor Security là nền tảng đúng.

**Bài 7 — Vì sao test Alice và Bob có giá trị hơn test tên thread?**

**Đáp án:** Thread name/ID có thể khác khi scheduler sắp xếp công việc; điều cần bảo vệ là principal không mất và không rò rỉ giữa subscription của người dùng. Kiểm tra exact response tương ứng từng user cung cấp bằng chứng trực tiếp.

## 14. Tóm tắt kỹ thuật

```text
HTTP authentication (Spring Security WebFlux)
  -> SecurityContext trong Reactor Context của request subscription
       |
       +-- publishOn(scheduler) ----- context vẫn theo subscriber
       |
       +-- subscribeOn(scheduler) --- context vẫn theo subscriber
       |
       +-- flatMap / delay / WebClient (Reactor publisher)
       |      -> đọc qua ReactiveSecurityContextHolder
       |
       +-- fromCallable().subscribeOn(boundedElastic)
       |      -> operator Reactor giữ context
       |      -> Java callable không được giả định có ThreadLocal auth
       |
       +-- CompletableFuture / @Async / external Executor
       |      -> callback ngoài Reactor không tự có context
       |      -> truyền identity đã xác thực một cách tường minh
       |      -> Mono.fromFuture(...) để nối lại pipeline
       |
       +-- subscribe() mới, tách request
              -> subscription khác; không giả định kế thừa context

contextWrite(...) -> đặt Context cho upstream trong subscription
ReactiveSecurityContextHolder -> API đọc SecurityContext của WebFlux
SecurityContextHolder -> ThreadLocal mặc định, không thay thế cho Reactor Context
```

**Câu hỏi đúng khi debug:** “Đoạn code này thuộc cùng Reactor subscription và đang đọc qua API context phù hợp không?” thay vì “Nó chạy trên thread nào?”. Khi băng qua ranh giới sang công nghệ khác, hãy thiết kế truyền identity, xác thực và quyền rõ ràng, có thể kiểm thử.

## Nguồn tài liệu chính thức

- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Reactor Mono API — fromFuture](https://projectreactor.io/docs/core/3.6.1/api/reactor/core/publisher/Mono.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
