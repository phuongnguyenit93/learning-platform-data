# Reactor Context khác với cơ chế kế thừa ThreadLocal

Một lỗi kiểm thử khó nhận ra trong ứng dụng bất đồng bộ là request ban đầu đã đăng nhập, nhưng khi công việc chuyển sang một luồng thực thi khác thì code đọc `SecurityContext` lại nhận `null`, anonymous user hoặc thậm chí danh tính của request trước. Lỗi càng dễ bị che khuất khi bài test chỉ chạy đồng bộ trên một thread.

Trong chương **Bất đồng bộ và ngữ cảnh** của module `SPRING_SECURITY_TESTING`, ta cần phân biệt hai mô hình **lưu và truyền ngữ cảnh bảo mật**:

- Trong **Servlet/imperative**, `SecurityContextHolder` mặc định sử dụng `ThreadLocal`. Khi công việc chạy ở thread khác, ngữ cảnh không tự xuất hiện trừ khi có cơ chế truyền thích hợp. `InheritableThreadLocal` là một lựa chọn dựa trên **quan hệ tạo thread**, không phải một lời giải tổng quát cho thread pool.
- Trong **WebFlux/Reactive**, `ReactiveSecurityContextHolder` sử dụng **Reactor Context gắn với subscriber/subscription**. Nó đi theo chuỗi reactive qua các operator phù hợp, thay vì phụ thuộc một Java thread cố định. `contextWrite(...)` và thời điểm subscribe quyết định ngữ cảnh mà các operator upstream có thể thấy.

Hai mô hình này có cùng mục đích — làm cho danh tính đã xác thực có sẵn ở nơi cần ra quyết định bảo mật — nhưng **không tương đương**, không thể thay thế lẫn nhau chỉ bằng cách đổi thread hoặc thêm annotation test.

Bài này dùng Java, Spring Security Test, `MockMvc`, `WebTestClient`, `StepVerifier` và ví dụ với executor để chứng minh sự khác biệt. Không cần hệ thống OAuth2/OIDC thật: phần trọng tâm là cách **authentication đã có** được truyền và quan sát trong mã bất đồng bộ.

## 1. Một tình huống thực tế: đúng danh tính ở controller, sai danh tính ở service

Giả sử một API `GET /api/whoami` trả tên người dùng hiện tại. Trong phương thức xử lý request, Spring Security đã xác thực Alice.

Ở Servlet:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String name = authentication.getName(); // "alice"
```

Nếu service tự chạy một công việc khác:

```java
CompletableFuture.supplyAsync(() -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

    return current == null ? "missing" : current.getName();
});
```

Khi không chủ động truyền ngữ cảnh, code bên trong task thường thấy **không có authentication** vì task chạy trên thread khác. Không được suy ra ngữ cảnh sẽ theo task chỉ vì request ban đầu đã đăng nhập.

Trong WebFlux, cố dùng cách đọc `SecurityContextHolder.getContext()` như đoạn Servlet ở trên cũng không phải lựa chọn đúng. Chuỗi `Mono`/`Flux` có thể được thực thi trên các thread khác nhau, trong khi Spring Security Reactive tổ chức ngữ cảnh qua `Reactor Context`:

```java
Mono<String> name = ReactiveSecurityContextHolder
    .getContext()
    .flatMap(ctx ->
        Mono.justOrEmpty(ctx.getAuthentication()))
    .map(Authentication::getName);
```

Cách đọc thứ hai chỉ được thực thi khi một subscriber subscribe vào publisher, trong ngữ cảnh reactive tương ứng.

### Mục tiêu của bài học

Sau bài này, bạn có thể:

1. Giải thích vì sao `ThreadLocal`, `InheritableThreadLocal` và `Reactor Context` có vòng đời khác nhau.
2. Viết test chứng minh một `Mono` được subscribe bởi hai ngữ cảnh khác nhau không tự chia sẻ danh tính.
3. Dùng `ReactiveSecurityContextHolder.withAuthentication(...)` và `StepVerifier` để kiểm tra service Reactive.
4. Dùng `WebTestClient` với `mockUser()` để kiểm tra WebFlux controller và filter chain nhận đúng authentication, đồng thời hiểu giới hạn của helper.
5. Biết khi nào cần `DelegatingSecurityContextExecutor` cho Servlet/imperative async và vì sao không nên dùng `MODE_INHERITABLETHREADLOCAL` để sửa mọi lỗi bất đồng bộ.
6. Thiết kế test chống rò rỉ ngữ cảnh giữa các request/subscriptions và phân biệt lỗi ngữ cảnh với lỗi phân quyền.

## 2. ThreadLocal của SecurityContextHolder hoạt động thế nào?

Trong mô hình imperative, `SecurityContextHolder` cung cấp API tĩnh:

```java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
```

Chiến lược mặc định phổ biến của `SecurityContextHolder` là `MODE_THREADLOCAL`. Một thread có thể giữ `SecurityContext` riêng trong suốt đoạn xử lý request. Spring Security Servlet thiết lập/ngăn rò rỉ context qua các filter và quản lý lifecycle của nó theo cấu hình.

Mô hình này dễ hình dung:

```text
Thread A (đang xử lý Alice)
    ThreadLocal[A] -> SecurityContext(Alice)

Thread B (đang xử lý Bob)
    ThreadLocal[B] -> SecurityContext(Bob)

Thread C (task async)
    ThreadLocal[C] -> thường không có Authentication
```

Dù A gọi một method tạo task ở C, `ThreadLocal[A]` **không tự động được sao chép** sang `ThreadLocal[C]`.

### 2.1. InheritableThreadLocal kế thừa lúc tạo thread

Java cung cấp `InheritableThreadLocal`. Khi một **thread con được tạo**, thread con có thể nhận giá trị ban đầu từ thread cha. Spring Security có chế độ `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL`.

Nhưng cơ chế này có giới hạn quan trọng:

- Giá trị được kế thừa theo **sự kiện tạo thread**, không phải theo từng job được gửi vào một pool.
- Thread pool thường tạo hoặc tái sử dụng thread trước khi request của Alice/Bob bắt đầu; các task trên thread pool không có quan hệ “thread con mới của request” như trực giác ban đầu.
- Nếu một thread sống lâu và nhận context không đúng thời điểm, nó có thể giữ ngữ cảnh sai cho những nhiệm vụ về sau nếu lifecycle không được xử lý chặt chẽ.
- Thay đổi chiến lược `SecurityContextHolder` là thay đổi **toàn cục trong JVM**; làm vậy trong bài test song song hoặc application khác có thể gây tác động khó kiểm soát.

Vì thế, **không nên dùng `MODE_INHERITABLETHREADLOCAL` như bản vá mặc định** cho `@Async`, `ExecutorService`, `CompletableFuture` hoặc thread pool.

Ví dụ Java thuần để thấy tính chất “kế thừa khi tạo thread”:

```java
import java.util.concurrent.atomic.AtomicReference;

InheritableThreadLocal<String> inherited =
    new InheritableThreadLocal<>();

inherited.set("alice");
AtomicReference<String> childSaw = new AtomicReference<>();

Thread child = new Thread(
    () -> childSaw.set(inherited.get())
);
child.start();
child.join();

assertThat(childSaw.get()).isEqualTo("alice");
inherited.remove();
```

Kết quả này chỉ chứng minh Java đã truyền một giá trị **khi tạo thread con**. Nó **không** chứng minh `ThreadLocal` thường hoạt động như vậy, và không có gì đảm bảo cùng kết quả khi gửi nhiều request đến một executor dùng chung các thread tồn tại từ trước.

### 2.2. Tại sao thread pool dễ gây hiểu nhầm?

Một thread pool có thể chạy lần lượt:

```text
Request Alice -> submit(task A) ─┐
                                 ├-> Worker-1 (tồn tại lâu)
Request Bob   -> submit(task B) ─┘

Task A cần Alice, task B cần Bob.
```

Ở đây, Worker-1 không tự trở thành thread con mới của từng request. Nếu task A để lại ngữ cảnh Alice trong thread dùng chung, task B có nguy cơ đọc nhầm Alice. Ngược lại, nếu thread pool không có context, cả hai task đều thấy thiếu authentication.

Đây là bài toán **truyền và dọn ngữ cảnh theo từng nhiệm vụ**, không phải chỉ bật “kế thừa ThreadLocal”.

## 3. Reactor Context: ngữ cảnh thuộc subscription, không thuộc thread

Reactor cung cấp `reactor.util.context.Context` và `ContextView`. Thay vì “giữ biến toàn cục theo thread”, Reactor truyền dữ liệu bối cảnh qua quá trình **subscriber subscribe** vào `Mono` hoặc `Flux`.

Một số tính chất thiết yếu:

- `Context` hoạt động như một cấu trúc key–value bất biến theo cách sử dụng: thao tác `put(...)` tạo ra ngữ cảnh mới, không sửa chung một map thay đổi được.
- Context đi từ phía **downstream subscriber lên các operator upstream** khi subscription được xây dựng; `contextWrite(...)` sửa context mà các operator **upstream** có thể thấy.
- Những operator như `publishOn(...)` hoặc `subscribeOn(...)` có thể đổi thread thực thi, nhưng bản thân việc đổi thread không đồng nghĩa mất Reactor Context.
- Một publisher có thể được subscribe nhiều lần. Mỗi subscription có thể có context **khác nhau**.
- Reactor Context không tự chảy vào một `Runnable` được đẩy sang executor ngoài pipeline hoặc một lần `subscribe()` tách rời mà bạn không truyền context.

### 3.1. Một ví dụ không liên quan Security để hiểu Context

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

Mono<String> requestId = Mono.deferContextual(context ->
    Mono.just(context.getOrDefault("traceId", "unknown"))
);

StepVerifier.create(
        requestId
            .publishOn(Schedulers.parallel())
            .contextWrite(Context.of("traceId", "trace-42"))
    )
    .expectNext("trace-42")
    .verifyComplete();
```

`Mono.deferContextual(...)` đọc `ContextView` khi subscription diễn ra. `contextWrite(...)` gắn giá trị `traceId` cho các operator upstream. Dù có `publishOn(Schedulers.parallel())`, test không phụ thuộc vào việc thread hiện tại có một `ThreadLocal<String>` tương ứng.

Đây chỉ là dữ liệu bối cảnh thông thường, **không phải authentication**. Đừng dùng một khóa tùy ý như `"user"` rồi tự coi nó là `SecurityContext` đáng tin cậy; Spring Security có API chuyên dụng để đưa kết quả xác thực vào Reactor Context.

### 3.2. Vì sao nói contextWrite tác động lên upstream?

Xét biểu thức:

```java
Mono<String> seen = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("key", "missing")))
    .contextWrite(ctx -> ctx.put("key", "inner"))
    .contextWrite(ctx -> ctx.put("key", "outer"));

StepVerifier.create(seen)
    .expectNext("inner")
    .verifyComplete();
```

Operator đọc context ở đầu pipeline nhìn thấy thay đổi từ `contextWrite` gần nó hơn về phía upstream, nên nhận `"inner"`. Bên dưới, mỗi subscription dựng chain context của riêng nó. Việc `contextWrite` xuất hiện gần cuối dòng code không có nghĩa nó “chạy sau” về mặt dữ liệu.

**Hệ quả khi test Security:** Đặt `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` lên đúng publisher/chuỗi mà bạn muốn kiểm tra; nếu tách sang một publisher được subscribe độc lập, không có gì đảm bảo hai subscription dùng cùng context.

## 4. ReactiveSecurityContextHolder lưu authentication như thế nào?

Spring Security Reactive cung cấp `ReactiveSecurityContextHolder`, với các API thường dùng:

| API | Vai trò |
| --- | --- |
| `ReactiveSecurityContextHolder.getContext()` | Trả `Mono<SecurityContext>` từ Reactor Context khi subscribe |
| `ReactiveSecurityContextHolder.withAuthentication(authentication)` | Tạo một Reactor `Context` mang authentication đã cung cấp |
| `ReactiveSecurityContextHolder.withSecurityContext(Mono<SecurityContext>)` | Tạo context từ một `Mono<SecurityContext>` |
| `ReactiveSecurityContextHolder.clearContext()` | Tạo hàm chỉnh context để xóa security context trong một nhánh phù hợp |

Trong luồng WebFlux thật, một security web filter sẽ lấy thông tin xác thực từ request/repository, áp dụng cơ chế xác thực được cấu hình và tạo ngữ cảnh dùng cho reactive chain. Các operator đọc bằng `ReactiveSecurityContextHolder.getContext()` sẽ quan sát context của subscription hiện tại.

`ReactiveSecurityContextHolder.getContext()` **không phải** lời gọi đồng bộ tương đương `SecurityContextHolder.getContext()`. Nó trả `Mono`: dữ liệu chỉ được đọc trong quá trình subscription.

### 4.1. Service lấy tên người dùng theo đúng kiểu Reactive

```java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class CurrentUserService {

    Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                Mono.justOrEmpty(ctx.getAuthentication()))
            .filter(authentication ->
                authentication.isAuthenticated()
                && !(authentication
                    instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .defaultIfEmpty("anonymous");
    }
}
```

Hai lưu ý quan trọng:

1. `Authentication.isAuthenticated()` không đủ để loại trừ mọi loại anonymous token, vì `AnonymousAuthenticationToken` có thể trả `true` cho cờ này. Vì vậy ví dụ kiểm tra thêm loại token; policy authorization thực tế của Spring Security dùng các cơ chế voter/authorization manager riêng để phân biệt anonymous.
2. `defaultIfEmpty("anonymous")` chỉ là lựa chọn biểu diễn dữ liệu cho bài demo. Nó không cho phép anonymous truy cập các endpoint đang bị `authenticated()` bảo vệ, vì filter authorization có thể chặn request **trước khi gọi controller**.

Nếu method service bắt buộc có authentication, có thể để pipeline rỗng hoặc trả lỗi nghiệp vụ tương ứng thay vì tạo chuỗi `"anonymous"`. Lựa chọn phải dựa vào contract của ứng dụng.

## 5. Unit test ReactiveSecurityContextHolder bằng StepVerifier

Đây là nơi rõ nhất để kiểm chứng một publisher nhận authentication theo subscriber context. Không cần WebTestClient hoặc HTTP server nếu mục tiêu chỉ là service.

Sử dụng JUnit Jupiter, Spring Security và `reactor-test`. Với Spring Boot project, `spring-boot-starter-test` thường cung cấp những thành phần test cần thiết; hãy kiểm tra dependency thực tế khi tách test độc lập.

### 5.1. Tạo Authentication đã được xác thực trong fixture

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.test.StepVerifier;

class CurrentUserServiceTest {

    private final CurrentUserService service =
        new CurrentUserService();

    private static Authentication user(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
            username,
            "not-a-real-password",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    @Test
    void userIsReadFromReactorContext() {
        StepVerifier.create(
                service.currentName()
                    .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                            user("alice")
                        )
                    )
            )
            .expectNext("alice")
            .verifyComplete();
    }
}
```

`UsernamePasswordAuthenticationToken.authenticated(...)` trong test là cách tạo sẵn một authentication **đã được đánh dấu xác thực**. Test này xác minh service đọc context đúng; **không chứng minh mật khẩu Alice đã được HTTP filter hoặc authentication provider kiểm tra**. Khi cần test password verification, phải đi qua cơ chế xác thực thật với request và credentials phù hợp.

### 5.2. Hai subscription phải thấy hai người dùng khác nhau

Có thể subscribe vào cùng **một publisher logic** với hai context:

```java
@Test
void onePublisherCanBeSubscribedWithDifferentIdentities() {
    Mono<String> source = service.currentName();

    StepVerifier.create(source.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(
                user("alice")
            )
        ))
        .expectNext("alice")
        .verifyComplete();

    StepVerifier.create(source.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(
                user("bob")
            )
        ))
        .expectNext("bob")
        .verifyComplete();

    StepVerifier.create(source)
        .expectNext("anonymous")
        .verifyComplete();
}
```

Bổ sung import `reactor.core.publisher.Mono`. Test này thể hiện một đặc tính quan trọng: **publisher không có “người dùng cuối cùng” nằm trong một ThreadLocal dùng chung**. Mỗi subscription đọc dữ liệu mà subscriber của nó cung cấp.

Việc subscribe lần ba mà không có authentication rồi nhận `anonymous` còn là một kiểm tra cơ bản chống rò rỉ danh tính giữa các lần kiểm thử.

### 5.3. Hai subscriber hoạt động đồng thời

Một cách kiểm tra độc lập khác là ghép hai publisher đã có context riêng:

```java
@Test
void separateSubscribersDoNotShareAuthentication() {
    Mono<String> alice = service.currentName()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(
                user("alice")
            )
        );

    Mono<String> bob = service.currentName()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(
                user("bob")
            )
        );

    StepVerifier.create(Mono.zip(alice, bob))
        .expectNextMatches(names ->
            names.getT1().equals("alice")
            && names.getT2().equals("bob"))
        .verifyComplete();
}
```

Nếu code vô tình đọc một giá trị tĩnh được chia sẻ giữa các request, bài test có thể phát hiện kết quả sai. Dù vậy, một test zip đơn giản không thay thế stress test hoặc kiểm tra tải khi ứng dụng thật có cơ chế caching và thread scheduling phức tạp.

## 6. Đổi Scheduler không đồng nghĩa mất Reactor Context

Một hiểu nhầm phổ biến: “Chạy trên thread khác thì Reactor Security Context chắc chắn mất”. Trong một **reactive chain được compose đúng**, điều đó không đúng. Reactor Context đi theo subscription và có thể hiện diện khi những operator upstream được thực thi trên scheduler khác.

Ví dụ:

```java
import reactor.core.scheduler.Schedulers;

@Test
void authenticationSurvivesSchedulerSwitchInSameChain() {
    Mono<String> pipeline = Mono.defer(
            () -> service.currentName())
        .subscribeOn(Schedulers.boundedElastic())
        .publishOn(Schedulers.parallel());

    StepVerifier.create(
            pipeline.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("alice")
                )
            )
        )
        .expectNext("alice")
        .verifyComplete();
}
```

Ở đây, `subscribeOn(...)` và `publishOn(...)` có thể tác động đến thread dùng để thực thi, nhưng service vẫn được subscribe trong context chứa Alice. Điểm quyết định là **chain còn liên tục và subscriber context được truyền đúng**.

Không nên tạo một ThreadLocal của riêng mình và suy luận nó có tính chất đó. Cũng không nên ép tất cả logic bất đồng bộ vào `Schedulers.boundedElastic()` để “sửa” lỗi security; điều đó có thể che đi chỗ mất context thật sự.

### 6.1. Điều gì có thể làm context không đi tới công việc mới?

Một số ranh giới nguy hiểm:

- Gọi `publisher.subscribe()` thủ công bên trong controller/service, tạo một subscription độc lập rồi trả một publisher khác. Context của request có thể không được truyền như mong đợi.
- Gọi `CompletableFuture.supplyAsync(...)` hoặc `executor.execute(...)` và đọc `SecurityContextHolder` trong task, trong khi danh tính ban đầu chỉ có ở Reactor Context.
- Chuyển dữ liệu vào callback của thư viện không dựa trên Reactor mà không có cơ chế context propagation thích hợp.
- Dùng `block()` giữa reactive chain để đọc kết quả rồi tiếp tục xử lý như imperative, nhất là trên event-loop.
- Tự lưu `Authentication` vào static field hoặc singleton, khiến các request có thể chia sẻ/ghi đè dữ liệu bảo mật.

Không có nghĩa **mọi** call sang API bên ngoài đều làm mất Reactor Context: một thư viện có thể hỗ trợ tích hợp context propagation. Nhưng việc có một `ThreadLocal` đang chứa dữ liệu ở một thời điểm không đủ để chứng minh subscription khác sẽ tự mang ngữ cảnh đúng.

### 6.2. Tại sao không gọi subscribe() bên trong service?

Anti-pattern:

```java
void startWork() {
    service.currentName()
        .subscribe(name -> sendAudit(name));
}
```

Phương thức trả ngay và tạo một subscription tách rời. Caller không thể dễ dàng kiểm soát hoàn tất, lỗi, hủy hoặc context của công việc. Thay vì vậy, trả publisher và để caller compose:

```java
Mono<Void> auditCurrentUser() {
    return service.currentName()
        .flatMap(name -> sendAuditReactive(name));
}
```

Nếu `sendAuditReactive(name)` trả `Mono<Void>`, caller có thể gọi:

```java
return auditCurrentUser()
    .then(responsePublisher);
```

Cách compose giữ công việc trong một chuỗi reactive có lifecycle và ngữ cảnh rõ ràng hơn. Nếu thật sự cần fire-and-forget, hãy định nghĩa ranh giới context, error handling và ownership của background job một cách tường minh, không dựa vào request context tồn tại mãi.

## 7. Kiểm thử HTTP WebFlux bằng WebTestClient

Unit test với `StepVerifier` chứng minh service hiểu Reactor Context. Nhưng nó chưa chứng minh WebFlux web filters và controller đặt/đọc context đúng khi một HTTP request được xử lý.

Để kiểm tra toàn tuyến **WebFlux request → SecurityWebFilterChain → handler → ReactiveSecurityContextHolder**, ta dùng `WebTestClient.bindToApplicationContext(...)` kết hợp `SecurityMockServerConfigurers.springSecurity()`.

### 7.1. SecurityWebFilterChain và người dùng test

Đối với ví dụ tự chứa, tạo một ứng dụng Spring Boot WebFlux với dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Cấu hình mẫu:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class WebFluxContextSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("correct-test-password"))
                .roles("USER")
                .build()
        );
    }
}
```

Trong production, danh sách user/credentials phải đến từ nguồn phù hợp và được quản trị an toàn. Những giá trị cố định ở trên chỉ là fixture minh họa. Nếu ứng dụng có nhiều `SecurityWebFilterChain`, bài test phải dùng endpoint khớp chain mong muốn.

### 7.2. Handler sử dụng Reactor Context

```java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ContextDemoController {

    private final CurrentUserService service;

    ContextDemoController(CurrentUserService service) {
        this.service = service;
    }

    @GetMapping("/api/whoami")
    Mono<Map<String, String>> whoami() {
        return service.currentName()
            .map(name -> Map.of("name", name));
    }

    @GetMapping("/public/context")
    Mono<String> publicContext() {
        return service.currentName();
    }
}
```

Endpoint `/api/whoami` yêu cầu authenticated user; `/public/context` cho phép thử nhánh không có authentication, và service sẽ trả `anonymous` nếu không tìm thấy principal thực.

### 7.3. Test với mockUser() để kiểm tra security context của request

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class WebFluxSecurityContextTest {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void mockAuthenticatedRequestSeesAliceInReactorContext() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get()
            .uri("/api/whoami")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("alice");
    }

    @Test
    void unauthenticatedRequestCannotReachProtectedHandler() {
        client.get()
            .uri("/api/whoami")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void publicHandlerWithoutLoginSeesAnonymous() {
        client.get()
            .uri("/public/context")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("anonymous");
    }
}
```

Ý nghĩa của từng test:

- `mockAuthenticatedRequestSeesAliceInReactorContext` cho thấy `mockUser()` cung cấp authentication cho request kiểm thử, WebFlux chuyển request qua security filters và service đọc được Alice từ `ReactiveSecurityContextHolder`.
- `unauthenticatedRequestCannotReachProtectedHandler` cho thấy quyền truy cập thật ở `/api/**` đang được bảo vệ; cấu hình Basic + form login disabled trả 401 khi request chưa xác thực.
- `publicHandlerWithoutLoginSeesAnonymous` kiểm tra service xử lý trường hợp không có người dùng đã xác thực, không tự dùng lại Alice từ test trước.

**Giới hạn:** `mockUser()` không gửi mật khẩu Alice qua HTTP và không gọi `ReactiveAuthenticationManager` để xác minh mật khẩu. Test này kiểm tra **truyền và quan sát authentication đã có** trong Reactor Context. Muốn kiểm tra xác thực HTTP Basic, cần một request mang header Basic.

### 7.4. So sánh với request gửi Basic credentials thật vào WebFlux filters

Trong cùng class:

```java
@Test
void httpBasicCredentialsReachReactiveAuthenticationMechanism() {
    client.get()
        .uri("/api/whoami")
        .headers(headers -> headers.setBasicAuth(
            "alice", "correct-test-password"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.name").isEqualTo("alice");
}
```

Request này đi qua `AuthenticationWebFilter` cho HTTP Basic trong WebFlux test server, sử dụng user details service/password encoder đã cấu hình. Nó chứng minh **xác thực qua HTTP header trong WebFlux filter chain**, nhưng vì `bindToApplicationContext(...)` chạy trong bộ nhớ, **không chứng minh socket TCP/TLS đã được sử dụng**. Nếu cần kiểm tra HTTP qua mạng, khởi động Spring Boot trên `RANDOM_PORT` và dùng `WebTestClient.bindToServer()`.

So sánh quan trọng:

| Test | Danh tính được tạo ở đâu? | Kiểm tra credentials? | Kiểm tra Reactor Context? |
| --- | --- | --- | --- |
| `StepVerifier + withAuthentication(alice)` | Test trực tiếp | Không | Có, ở service |
| `WebTestClient + mockUser("alice")` | Spring Security test configurer | Không | Có, qua WebFlux request |
| `WebTestClient + Basic header` | Reactive authentication filter/provider | Có, theo cấu hình test | Có, qua WebFlux request |
| `WebTestClient.bindToServer() + Basic header` | Server thật | Có | Có, và kết nối HTTP qua mạng |

Kết quả 200 có thể giống nhau, nhưng tầng bảo vệ được kiểm chứng khác nhau. Khi phát hiện bug ngữ cảnh, hãy chọn test giúp phân biệt “credentials chưa được xác thực” với “authentication đã xác thực nhưng không được truyền đến nơi cần dùng”.

## 8. Servlet async: cần truyền SecurityContext sang Executor một cách chủ động

Ở Servlet, `SecurityContextHolder` mặc định vẫn là ThreadLocal. Đối với một job chạy trên thread pool, Spring Security có các wrapper như `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor` và `DelegatingSecurityContextAsyncTaskExecutor` để thiết lập/khôi phục context quanh công việc.

Không nên tự sửa chiến lược toàn cục từ `MODE_THREADLOCAL` sang `MODE_INHERITABLETHREADLOCAL` chỉ để test một `CompletableFuture`.

### 8.1. Ví dụ truyền context tường minh tới executor

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

class ServletSecurityContextExecutorTest {

    @Test
    void explicitlyDelegatedContextIsVisibleInWorkerTask()
            throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Authentication alice =
                UsernamePasswordAuthenticationToken.authenticated(
                    "alice",
                    "not-a-real-password",
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
                );

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(alice);

            // Đặt context tường minh vào wrapper cho fixture này.
            var securedExecutor =
                new DelegatingSecurityContextExecutor(pool, context);

            CompletableFuture<String> result =
                new CompletableFuture<>();

            securedExecutor.execute(() -> {
                try {
                    Authentication current =
                        SecurityContextHolder.getContext()
                            .getAuthentication();

                    result.complete(current.getName());
                } catch (Throwable error) {
                    result.completeExceptionally(error);
                }
            });

            assertThat(result.get(3, TimeUnit.SECONDS))
                .isEqualTo("alice");
        } finally {
            pool.shutdownNow();
            SecurityContextHolder.clearContext();
        }
    }
}
```

Trong test này, `DelegatingSecurityContextExecutor` bọc task để worker có thể thấy SecurityContext được chỉ định; wrapper có trách nhiệm khôi phục/dọn bối cảnh thực thi theo contract của nó. Khi truyền context tường minh trong constructor, wrapper dùng **context đã chọn** cho những task nó xử lý. Đừng tái sử dụng cùng wrapper với danh tính Alice để chạy task của Bob.

Nếu muốn wrapper **lấy SecurityContext tại thời điểm submit task**, có thể dùng overload của wrapper được thiết kế để lấy context hiện tại. Khi đó vẫn cần đảm bảo request/thread gọi `execute(...)` đang có context chính xác và vòng đời của executor được quản lý phù hợp.

### 8.2. @Async cần executor bảo mật phù hợp

Một method Spring:

```java
@Async
public CompletableFuture<String> generateReport() {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

    return CompletableFuture.completedFuture(
        authentication.getName());
}
```

không tự có authentication trong thread `@Async` nếu executor không truyền context. Với Spring `@EnableAsync`, có thể cấu hình một `AsyncTaskExecutor` được bọc bằng `DelegatingSecurityContextAsyncTaskExecutor`, sau đó đảm bảo `@Async` dùng executor đó.

Ví dụ ý tưởng:

```java
@Bean(name = "securityAsyncExecutor")
AsyncTaskExecutor securityAsyncExecutor() {
    ThreadPoolTaskExecutor delegate =
        new ThreadPoolTaskExecutor();
    delegate.setCorePoolSize(2);
    delegate.setMaxPoolSize(4);
    delegate.initialize();

    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}
```

Khi dùng `@Async("securityAsyncExecutor")`, wrapper có thể mang context của caller đến task. Trong ứng dụng thật, quản lý shutdown executor, exception handling và chính sách context propagation khi một task phục vụ nhiều người dùng. Test nên assert **Alice ở task của Alice, Bob ở task của Bob, và không có rò rỉ giữa hai lần thực thi**. Không chỉ kiểm tra task hoàn thành thành công.

**Quan trọng:** Đây là cơ chế cho **imperative Spring Security context**. Nó không biến Reactor Context thành ThreadLocal một cách tự động, và không thay thế `ReactiveSecurityContextHolder` khi API đã dùng WebFlux/Reactor.

## 9. Spring MVC async Callable không giống một executor tự tạo

Spring MVC có cơ chế bất đồng bộ dựa trên `Callable` và `DeferredResult`. Spring Security Servlet tích hợp với một số điểm vòng đời MVC async, ví dụ thông qua `WebAsyncManagerIntegrationFilter` để hỗ trợ SecurityContext trên `Callable` được Spring MVC điều phối.

Vì vậy, cần phân biệt:

- **Spring MVC quản lý Callable:** có cơ chế tích hợp hỗ trợ context trên đường async được framework nhận diện. Nó không có nghĩa mọi `CompletableFuture` hoặc thread tự tạo đều được bảo vệ tương tự.
- **Một CompletableFuture/Executor tùy ý:** có thể chạy ngoài cơ chế MVC; cần wrapper hoặc context propagation rõ ràng.
- **DeferredResult do một callback ngoài hoàn tất:** cần xem callback chạy ở đâu và có tự cần SecurityContext không; không suy từ tên loại return value rằng mọi thread liên quan đều có context.

Ví dụ handler Servlet:

```java
@GetMapping("/api/async-user")
Callable<String> asyncUser() {
    return () -> SecurityContextHolder.getContext()
        .getAuthentication()
        .getName();
}
```

Khi test bằng `MockMvc`, nếu controller trả một `Callable`, cần kiểm tra request chuyển sang async và sau đó thực hiện `asyncDispatch(...)`:

```java
MvcResult first = mockMvc.perform(
        get("/api/async-user")
            .with(user("alice")))
    .andExpect(request().asyncStarted())
    .andReturn();

mockMvc.perform(asyncDispatch(first))
    .andExpect(status().isOk())
    .andExpect(content().string("alice"));
```

Các static imports trong test tương ứng `SecurityMockMvcRequestPostProcessors.user`, `MockMvcRequestBuilders.get/asyncDispatch`, `MockMvcResultMatchers.request/status/content`. Bộ test cần Spring Security được tích hợp vào `MockMvc` (ví dụ `@SpringBootTest + @AutoConfigureMockMvc` hoặc `.apply(springSecurity())` khi tự cấu hình).

Bài test này chứng minh luồng `Callable` MVC đã được tích hợp đúng trong cấu hình cụ thể. Nó **không** chứng minh mọi thread mới trong ứng dụng đều được kế thừa ThreadLocal.

## 10. Các ranh giới tích hợp phải kiểm tra riêng

Không nên đặt toàn bộ “ngữ cảnh bất đồng bộ” vào một câu trả lời duy nhất. Hãy xác định chính xác đoạn nào tạo ra công việc mới.

| Ranh giới | Nguồn ngữ cảnh mong muốn | Rủi ro | Phương án test |
| --- | --- | --- | --- |
| Spring MVC request cùng thread | `SecurityContextHolder` | Filter/setup sai | MockMvc request có/không auth |
| `ExecutorService` dưới Servlet | ThreadLocal do wrapper cung cấp | Mất context hoặc rò rỉ giữa task | Test Alice/Bob với wrapper |
| `@Async` | Context từ caller qua executor | Executor không được bọc/khác bean | Test task với executor thật và cleanup |
| Spring MVC `Callable` | MVC/Security async integration | Thiếu filters/asyncDispatch | MockMvc asyncStarted/asyncDispatch |
| WebFlux controller | Reactor Context của request | Không được compose đúng | WebTestClient + mockUser/header thật |
| `publishOn/subscribeOn` trong cùng chain | Reactor Context | Dùng nhầm ThreadLocal | StepVerifier kiểm tra sau scheduler switch |
| `subscribe()` tách rời | Context của subscriber mới | Mất context/lifecycle | Refactor composition, test độc lập |
| Callback/CompletableFuture ngoài Reactor | Cần adapter truyền context nếu thật sự cần | Không có bridge, dữ liệu sai | Test boundary và context propagation tường minh |
| HTTP request mới tới dịch vụ khác | Credentials truyền qua HTTP | Không tự có user ở server đích | Kiểm tra header/token bằng HTTP stub |

Có thể có tích hợp **Micrometer Context Propagation** hoặc Reactor hooks hỗ trợ kết nối một số ThreadLocal với Reactor Context. Các tính năng đó phụ thuộc phiên bản, cấu hình và những `ThreadLocalAccessor` được đăng ký. Chúng **không làm hai mô hình trở thành một**, cũng không nên được giả định là luôn bật trong mọi ứng dụng.

Nếu dự án bật automatic context propagation, hãy viết test riêng chứng minh chính xác giá trị cần thiết được truyền ở ranh giới mong muốn. Đừng mặc định mọi ThreadLocal, đặc biệt là dữ liệu bảo mật, đều được phép hoặc sẽ được copy một cách an toàn.

## 11. Test chống rò rỉ ngữ cảnh giữa người dùng

Một yêu cầu quan trọng của kiểm thử bảo mật là **không chỉ chứng minh Alice nhìn thấy Alice**, mà còn chứng minh Bob không nhìn thấy Alice trong một request/subscription khác.

### 11.1. Reactor: dùng Context riêng cho từng subscription

Một cách test tối thiểu:

```java
Mono<String> source = service.currentName();

Mono<String> forAlice = source.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(user("alice"))
);

Mono<String> forBob = source.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(user("bob"))
);

StepVerifier.create(Mono.zip(forAlice, forBob))
    .expectNextMatches(tuple ->
        tuple.getT1().equals("alice")
        && tuple.getT2().equals("bob"))
    .verifyComplete();

StepVerifier.create(source)
    .expectNext("anonymous")
    .verifyComplete();
```

Mục tiêu không phải kiểm tra tốc độ scheduler mà là ngăn một singleton/static cache hoặc ThreadLocal sai làm nhiễm danh tính giữa các subscribers.

### 11.2. Servlet/Executor: bảo đảm cleanup sau task

Nếu ứng dụng dùng wrapper để đặt SecurityContext lên worker thread, hãy thử submit lần lượt hai task với hai context khác nhau, rồi thử một task không mang context. Test phải kiểm tra kết quả của từng task không lẫn nhau.

Đừng gắn `SecurityContext` vào static field để “chia sẻ cho mọi thread”, và đừng bỏ qua `finally` khi tự thao tác `SecurityContextHolder.setContext(...)`. Wrapper chuyên dụng của Spring Security giúp giảm rủi ro quên restore/clear, nhưng test vẫn nên có những ca kiểm tra ngữ cảnh không bị rò rỉ trong cấu hình executor thật.

### 11.3. Không lẫn authentication với authorization

Người dùng có authentication không đồng nghĩa có quyền vào mọi endpoint. Với WebFlux:

- `mockUser("alice").roles("USER")` có thể đọc `/api/whoami` khi endpoint yêu cầu authenticated.
- Nếu `/api/admin` yêu cầu `ROLE_ADMIN`, cùng Alice phải nhận **403** dù service đọc được Alice từ Reactor Context.
- Request không có credentials tới endpoint bảo vệ có thể trả **401** hoặc redirect tùy entry point; trong ví dụ Basic-only ở trên, ta kỳ vọng 401.

Một test không đạt authorization không tự chứng minh Reactor Context bị mất. Cần so sánh principal quan sát được và policy bảo vệ URL để xác định đúng nguyên nhân.

## 12. Những sai lầm thường thấy trong bài kiểm thử

### 12.1. Dùng SecurityContextHolder.getContext() trong code WebFlux rồi chờ luôn có Alice

`SecurityContextHolder` mặc định dùng ThreadLocal ở mô hình imperative; `ReactiveSecurityContextHolder` mới là API chuẩn để đọc SecurityContext trong Reactor chain. Đọc ThreadLocal trong reactive callback có thể trả context rỗng, phụ thuộc thread hoặc bị ảnh hưởng bởi tích hợp propagation riêng của dự án. Đừng dựa vào việc test tình cờ chạy trên cùng một thread.

### 12.2. Cho rằng InheritableThreadLocal hoạt động với mọi thread pool

Giá trị được kế thừa lúc thread được tạo, không tự cập nhật theo job. Một pool tái sử dụng thread có thể không thấy context hiện tại hoặc thấy context không mong muốn. Truyền context theo từng task bằng wrapper phù hợp và kiểm tra cleanup.

### 12.3. Gắn contextWrite vào publisher không được subscribe

Nếu test tạo một publisher có context rồi **subscribe vào một publisher khác**, context sẽ không tự chảy sang publisher độc lập kia. Hãy xây một chain rõ ràng và xác định chỗ subscribe duy nhất do caller/framework quản lý.

### 12.4. Tự gọi subscribe() trong controller để chạy ngầm

Điều này tạo subscription mới, khó theo dõi lỗi, lifecycle và identity. Để test service/handler bảo đảm ngữ cảnh, nên trả `Mono`/`Flux` và compose. Nếu cần background job, truyền identity tối thiểu theo contract đã xác định, không giữ toàn bộ request context vô hạn.

### 12.5. Dùng block() để “giữ nguyên thread”

`block()` không phải cơ chế truyền SecurityContext. Nó phá nhịp non-blocking khi gọi trên event-loop và có thể gây deadlock hoặc lỗi runtime ở những scheduler không hỗ trợ blocking. Khi tích hợp thư viện blocking, hãy cô lập I/O và quản lý context phù hợp; không mặc định `block()` giải quyết vấn đề.

### 12.6. Coi StepVerifier withAuthentication là test password/JWT verification

`withAuthentication(authentication)` chèn sẵn authentication do test tạo. Nó kiểm tra việc **đọc ngữ cảnh**, không kiểm tra mật khẩu, chữ ký JWT hay introspection opaque token. Với JWT/OAuth2/OIDC, helper như `mockJwt()`, `mockOAuth2Login()` và `mockOidcLogin()` cũng chủ yếu phục vụ testing sau khi xác thực; không nên coi kết quả 200 là bằng chứng protocol/cryptographic validation thật đã chạy.

### 12.7. Quên negative case và chạy test song song không kiểm soát

Nếu chỉ một ca Alice thành công, có thể không phát hiện context leak. Thêm test Bob và unauthenticated, kiểm tra cả request kế tiếp. Khi dùng global `SecurityContextHolder.setStrategyName(...)` trong test, một test có thể ảnh hưởng test khác; tốt hơn tránh thay đổi chiến lược toàn cục hoặc phải hoàn nguyên có kiểm soát ngoài khu vực test chạy song song.

### 12.8. Trả authentication/credentials vào logs và error response

Thực hành test cần assert tên/authorities tối thiểu chứ không xuất toàn bộ `SecurityContext` hay Bearer token vào JSON và CI logs. Reactor Context có thể mang dữ liệu nhạy cảm; không log toàn bộ context view để tìm lỗi. Khi dùng fixture JWT/OIDC, cũng tránh log nguyên token hoặc client secrets.

## 13. Ma trận kiểm thử đề xuất

| Ca | Loại code | Công cụ | Assertion chính |
| --- | --- | --- | --- |
| Service thấy Alice khi context có Alice | Reactive service | StepVerifier + `withAuthentication` | `alice` |
| Không có context | Reactive service | StepVerifier | `anonymous` hoặc contract đã thiết kế |
| Hai subscription độc lập | Reactive service | `Mono.zip` + context riêng | Alice/Bob không lẫn |
| Đổi scheduler trong chain | Reactive service | `subscribeOn/publishOn` | Vẫn thấy identity của subscriber |
| WebFlux handler đọc Reactor Context | Reactive HTTP mock server | WebTestClient + `mockUser` | 200, tên Alice |
| WebFlux chặn request không auth | Reactive HTTP | WebTestClient | 401/redirect theo policy |
| WebFlux xác thực HTTP Basic | Reactive HTTP | WebTestClient + Basic header | Provider tạo Alice, 200 |
| Servlet cùng thread | MVC HTTP mock | MockMvc + `@WithMockUser`/`user()` | Principal đúng |
| Servlet Callable async | MVC async | MockMvc + `asyncDispatch` | Principal đúng khi Spring Security tích hợp |
| Executor task có identity | Imperative async | DelegatingSecurityContextExecutor | Alice trong task Alice |
| Executor task không rò rỉ | Imperative async | Test Alice/Bob/no context | Không thấy identity cũ |
| JWT/OIDC helper | Reactive security test | `mockJwt/mockOidcLogin` | Authorization/claims giả lập, không kết luận decoder |
| HTTP qua mạng | WebFlux/Servlet live server | WebTestClient `bindToServer` | Auth header/cookie tới server thật |

## 14. Bài thực hành tổng hợp

Xây một endpoint `GET /api/whoami` trả tên người dùng lấy từ `ReactiveSecurityContextHolder` và thực hiện các bước:

1. **Unit test Reactor:** Tạo một `Mono<String>` từ service, subscribe dưới context Alice/Bob bằng `StepVerifier`. Mỗi subscription phải trả đúng tên; subscription không có context phải trả `anonymous` hoặc kết quả fallback đã thống nhất.
2. **Async scheduler:** Thêm `publishOn(Schedulers.parallel())` hoặc `subscribeOn(Schedulers.boundedElastic())` trong cùng chain, giữ các assertion Alice/Bob đúng. Giải thích vì sao đây không phải tính chất của ThreadLocal thông thường.
3. **WebFlux integration:** Cấu hình `SecurityWebFilterChain` bảo vệ `/api/**`, dùng `WebTestClient.bindToApplicationContext(...).apply(springSecurity())`. Với `mockUser("alice")`, endpoint trả Alice; không có user, endpoint bị chặn; với Basic header đúng, provider thực tạo authentication.
4. **Imperative contrast:** Dùng `ExecutorService` và `DelegatingSecurityContextExecutor` trong một unit test. Khi có context tường minh Alice, task thấy Alice; phân tích vì sao bật `InheritableThreadLocal` không phải giải pháp an toàn cho pool dùng chung.
5. **Negative cases:** Thử context của Alice không được xuất hiện trong subscription Bob và request anonymous. Thử endpoint có yêu cầu role cao hơn rồi kiểm tra 403 để phân biệt lỗi authorization với lỗi mất security context.

**Tiêu chí hoàn thành:** Người học giải thích và chứng minh được rằng **Reactor Context đi theo subscriber/subscription**, trong khi **ThreadLocal đi theo Java thread** và **InheritableThreadLocal chỉ kế thừa vào lúc tạo thread con**. Các test phải chỉ rõ ranh giới giữa danh tính giả lập được đưa vào test, authentication được tạo từ credentials HTTP và việc truyền ngữ cảnh tới công việc bất đồng bộ; đồng thời phát hiện được nguy cơ mất/rò rỉ authentication khi chuyển luồng thực thi.

