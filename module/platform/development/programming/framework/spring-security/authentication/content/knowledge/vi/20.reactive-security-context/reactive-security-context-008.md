# Kiểm thử chuyển Scheduler, hủy subscription và cách ly danh tính giữa các request

## 1. Mục tiêu và phạm vi

Trong Spring Security WebFlux, câu hỏi cần kiểm chứng là: **một request có còn nhìn thấy đúng `Authentication` của nó sau khi luồng xử lý chuyển `Scheduler`, sau khi một subscription bị hủy, và khi nhiều request dùng chung các thread hay không?**

Sau bài này, bạn có thể:

1. Giải thích vì sao `ReactiveSecurityContextHolder` dựa trên **Reactor `Context` theo từng subscription**, thay vì giả định danh tính gắn vĩnh viễn với một thread.
2. Viết test chứng minh `publishOn` và `subscribeOn` không làm mất `SecurityContext` trong một chuỗi Reactor được kết nối đúng.
3. Dùng `StepVerifier.thenCancel()` và `doFinally(CANCEL)` để kiểm tra hủy subscription, sau đó xác nhận subscription mới không nhận nhầm danh tính.
4. Tạo nhiều subscription xen kẽ trên cùng `Scheduler` và xác nhận mỗi subscription nhận đúng người dùng.
5. Kiểm tra cách ly tại ranh giới HTTP bằng `WebTestClient` với các request Alice, Bob và không xác thực.

**Phạm vi:** ngữ cảnh xác thực trong luồng reactive của Spring Security. Những test này không thay thế test xác minh mật khẩu, phân quyền, session, token, cookie hoặc bảo mật tại gateway.

## 2. Mô hình cần hiểu trước khi kiểm thử

`ReactiveSecurityContextHolder.getContext()` đọc `Mono<SecurityContext>` từ Reactor `Context` của subscriber hiện tại. Trong WebFlux, bộ lọc bảo mật (đặc biệt `ReactorContextWebFilter` khi áp dụng) đưa ngữ cảnh bảo mật vào pipeline; trong unit test, ta có thể chủ động gắn ngữ cảnh bằng `contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))`.

```text
Request A ── Subscription A [Reactor Context: alice]
                  │
              subscribeOn(S1)
                  │
               publishOn(S2)
                  │
              đọc danh tính: alice

Request B ── Subscription B [Reactor Context: bob]
                  │
               publishOn(S2)  ← có thể dùng lại cùng thread
                  │
              đọc danh tính: bob
```

**Thread được tái sử dụng; subscriber và `Context` vẫn khác nhau.** `publishOn` đổi thread cho các toán tử phía sau; `subscribeOn` tác động đến việc đăng ký và phía nguồn. Chúng không tự làm biến mất Reactor `Context`. Ngược lại, `ThreadLocal` chứa thông tin người dùng có thể cho kết quả sai khi thread đổi hoặc được dùng lại.

`contextWrite(...)` cung cấp ngữ cảnh cho các toán tử **ở phía upstream** của chính vị trí đó trong chuỗi, theo chiều lan truyền ngữ cảnh lúc subscription. Khi `flatMap` tạo inner publisher thông thường, subscriber context được truyền vào inner publisher. Một `contextWrite` nằm riêng trong inner publisher không tự sửa ngữ cảnh của các nhánh bên ngoài.

| Trường hợp | Điều phải khẳng định | Không được suy diễn |
| --- | --- | --- |
| Đổi `Scheduler` | Đọc danh tính trước/sau chuyển thread đều đúng | Cần cố định tên thread hay số lượng thread |
| Nhiều subscription | Alice chỉ thấy Alice, Bob chỉ thấy Bob dù xử lý xen kẽ | Cứ dùng cùng thread là cùng người dùng |
| Hủy subscription | Nhận tín hiệu `CANCEL`; subscription sau không thấy ngữ cảnh cũ | `CANCEL` tự xóa session/token đã lưu |
| Request độc lập | Request Alice, Bob, ẩn danh cho kết quả riêng | Test `mockUser` xác minh được đăng nhập thật |

## 3. Chuẩn bị test

Ví dụ dùng **Java 17+**, JUnit Jupiter, Reactor Core/`reactor-test` và Spring Security reactive. Nếu dự án dùng Spring Boot và BOM quản lý phiên bản, khai báo các dependency cần thiết trong `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Đặt lớp test sau ở `src/test/java/example/ReactiveContextIsolationTest.java`. File này tự chứa bốn unit test; dự án cần có các dependency tương ứng và dùng phiên bản Spring Security/Reactor tương thích với BOM của mình. Không cần chạy HTTP server để thực thi bốn test này.

## 4. Unit test: scheduler hop, concurrent subscription, cancellation và phạm vi ngữ cảnh

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveContextIsolationTest {

    private static Authentication user(String name) {
        return new TestingAuthenticationToken(name, "unused", "ROLE_USER");
    }

    private static Mono<String> nameOrAnonymous() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .defaultIfEmpty("anonymous");
    }

    // Việc đọc danh tính diễn ra sau publishOn, trên Scheduler được chỉ định.
    private static Mono<String> readOn(Scheduler scheduler) {
        return Mono.just(1)
                .publishOn(scheduler)
                .flatMap(ignored -> nameOrAnonymous());
    }

    @Test
    void securityContextSurvivesSubscribeOnAndPublishOn() {
        Scheduler subscription = Schedulers.newSingle("subscription");
        Scheduler processing = Schedulers.newSingle("processing");
        try {
            Mono<String> pipeline = Mono.defer(
                        ReactiveContextIsolationTest::nameOrAnonymous)
                    .subscribeOn(subscription)
                    .publishOn(processing)
                    .flatMap(before -> nameOrAnonymous()
                            .map(after -> before + " -> " + after))
                    .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                            user("alice")));

            StepVerifier.create(pipeline)
                    .expectNext("alice -> alice")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        } finally {
            subscription.dispose();
            processing.dispose();
        }
    }

    @Test
    void concurrentSubscriptionsDoNotMixIdentities() {
        Scheduler shared = Schedulers.newSingle("shared");
        try {
            // 100 subscription riêng, xử lý xen kẽ trên cùng một worker thread.
            Flux<Boolean> checks = Flux.range(0, 100)
                    .flatMap(index -> {
                        String expected =
                                index % 2 == 0 ? "alice" : "bob";
                        return readOn(shared)
                                .map(expected::equals)
                                .contextWrite(
                                    ReactiveSecurityContextHolder
                                        .withAuthentication(user(expected)));
                    }, 16);

            StepVerifier.create(checks.collectList())
                    .assertNext(results -> {
                        assertEquals(100, results.size());
                        assertTrue(results.stream()
                                .allMatch(Boolean::booleanValue));
                    })
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            // Một subscription mới, không gắn Authentication.
            StepVerifier.create(readOn(shared))
                    .expectNext("anonymous")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        } finally {
            shared.dispose();
        }
    }

    @Test
    void cancellationDoesNotLeakIntoNextSubscription() {
        Scheduler shared = Schedulers.newSingle("cancel-worker");
        AtomicReference<SignalType> termination = new AtomicReference<>();
        try {
            Flux<String> aliceStream =
                    Flux.interval(Duration.ofMillis(10), shared)
                        .concatMap(tick -> nameOrAnonymous())
                        .doFinally(termination::set)
                        .contextWrite(
                            ReactiveSecurityContextHolder
                                .withAuthentication(user("alice")));

            StepVerifier.create(aliceStream)
                    .expectNext("alice")
                    .thenCancel()
                    .verify(Duration.ofSeconds(5));

            assertEquals(SignalType.CANCEL, termination.get());

            // Cùng Scheduler, nhưng hai subscription mới có Context riêng.
            StepVerifier.create(readOn(shared)
                    .contextWrite(
                        ReactiveSecurityContextHolder
                            .withAuthentication(user("bob"))))
                    .expectNext("bob")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            StepVerifier.create(readOn(shared))
                    .expectNext("anonymous")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        } finally {
            shared.dispose();
        }
    }

    @Test
    void contextChangeInsideFlatMapStaysInsideThatBranch() {
        Mono<String> pipeline = Mono.just(1)
                .flatMap(i -> nameOrAnonymous()
                        .contextWrite(
                            ReactiveSecurityContextHolder
                                .withAuthentication(user("bob"))))
                .flatMap(innerName -> nameOrAnonymous()
                        .map(outerName -> innerName + "/" + outerName))
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice")));

        StepVerifier.create(pipeline)
                .expectNext("bob/alice")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }
}
```

Chạy trong module có test setup nói trên:

```bash
./gradlew test --tests 'example.ReactiveContextIsolationTest'
```

Trên Windows dùng `gradlew.bat test --tests "example.ReactiveContextIsolationTest"`. Bốn test hoàn tất mà không in dòng kết quả nghiệp vụ cố định ra stdout; Gradle/JUnit báo tình trạng pass/fail. Các chuỗi `alice -> alice`, `anonymous` và `bob/alice` trong code là **giá trị được assertion kiểm tra**, không phải log được in ra.

### Phân tích từng test

**Test 1 — Chuyển `Scheduler`:** `Mono.defer(...)` trì hoãn việc đọc danh tính đến subscription. `subscribeOn(subscription)` điều phối bước đăng ký/phía nguồn; `publishOn(processing)` chuyển phần xử lý tiếp theo sang scheduler khác. Lần đọc đầu và lần đọc trong `flatMap` đều phải là Alice. Assertion theo **giá trị danh tính** là ổn định hơn assertion theo tên thread.

**Test 2 — Nhiều subscription xen kẽ:** `Flux.range(0, 100)` tạo 100 nhánh; mỗi nhánh tự có `contextWrite(withAuthentication(...))`, cùng gọi `readOn(shared)`. `flatMap(..., 16)` cho phép tối đa 16 inner subscription cùng hoạt động. Kết quả của từng nhánh phải khớp người dùng đã gắn vào chính nhánh đó; nếu một nhánh vô tình đọc nhầm ngữ cảnh thì sẽ xuất hiện `false`. Kiểm tra thêm một subscription ẩn danh trên scheduler cũ để phát hiện việc sử dụng sai bộ nhớ dùng chung hoặc `ThreadLocal`.

**Test 3 — Hủy:** `Flux.interval` phát tín hiệu trong thời gian thực; sau giá trị Alice đầu tiên, `thenCancel()` chủ động hủy subscription. `doFinally` ghi `SignalType.CANCEL`. Tiếp đó, Bob và subscription không xác thực được xử lý trên cùng scheduler. Kiểm tra này chứng minh hành vi tại **ranh giới subscription**; nó không đo xem bộ nhớ có được GC thu hồi hay session lưu trên server đã bị xóa hay chưa.

**Test 4 — Giới hạn phạm vi của `contextWrite`:** nhánh `flatMap` đầu tiên ghi Bob cho riêng inner publisher, nên trả về `bob`. Nhánh tiếp theo vẫn đọc ngữ cảnh bên ngoài là Alice, do đó kết quả `bob/alice`. Nếu kết quả là `bob/bob` thì rất có thể mã ứng dụng đã tự lưu một trạng thái người dùng dùng chung ngoài phạm vi Reactor.

`Schedulers.newSingle(...)` được `dispose()` trong `finally` để test không giữ thread sống sau khi kết thúc. `verify(Duration.ofSeconds(5))` giới hạn thời gian chờ, giúp phát hiện test bị treo thay vì chờ vô hạn. Test dùng scheduler thực để kiểm chứng chuyển thread; nếu chỉ thử logic thời gian, có thể cân nhắc `StepVerifier.withVirtualTime(...)` nhưng cần tạo publisher bên trong supplier và phân biệt rõ scheduler ảo với scheduler thực.

## 5. Kiểm tra tại ranh giới HTTP bằng WebTestClient

Unit test ở trên chứng minh cách ly giữa **subscription**. Để kiểm chứng **request HTTP thực sự qua bộ lọc bảo mật**, tạo một endpoint thử nghiệm trả về danh tính đang nhìn thấy. Đoạn sau là mã tích hợp vào **một ứng dụng Spring Boot WebFlux đã có**, không phải chương trình Java độc lập; phải đặt controller/config trong package được component scan, và cho phép GET `/identity` đối với người dùng ẩn danh.

```java
// Ví dụ controller trong ứng dụng WebFlux (bổ sung import phù hợp).
@RestController
class IdentityProbeController {

    @GetMapping("/identity")
    Mono<String> identity() {
        return Mono.just(1)
                .publishOn(Schedulers.parallel())
                .flatMap(ignored ->
                    ReactiveSecurityContextHolder.getContext()
                        .map(SecurityContext::getAuthentication)
                        .filter(authentication ->
                            !(authentication
                                instanceof AnonymousAuthenticationToken))
                        .map(Authentication::getName)
                        .defaultIfEmpty("anonymous"));
    }
}
```

`AnonymousAuthenticationToken` được chuẩn hóa thành chuỗi `anonymous` ở endpoint kiểm thử để kết quả không phụ thuộc vào việc Spring Security dùng anonymous token hay không có `SecurityContext`. Trong ứng dụng thật, đừng dùng tên `anonymous` như bằng chứng xác thực.

Nếu không có chain khác xử lý route này, cấu hình tối thiểu phục vụ test có thể là:

```java
@Configuration
@EnableWebFluxSecurity
class IdentityProbeSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http.authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/identity").permitAll()
                    .anyExchange().authenticated())
                .build();
    }
}
```

Dùng test Spring để khởi tạo `ApplicationContext` và gắn cấu hình kiểm thử Spring Security vào `WebTestClient`. Các import quan trọng: `org.springframework.test.web.reactive.server.WebTestClient`, `org.springframework.context.ApplicationContext`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.boot.test.context.SpringBootTest`, `org.junit.jupiter.api.Test`, cùng hai static import được trình bày dưới đây.

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class IdentityProbeHttpTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void separateHttpRequestsDoNotShareIdentity() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();

        client.mutateWith(mockUser("alice"))
                .get().uri("/identity").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");

        client.mutateWith(mockUser("bob"))
                .get().uri("/identity").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("bob");

        client.get().uri("/identity").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("anonymous");
    }
}
```

**Lưu ý khi sao chép code:** Hai dòng `import static` ở ví dụ trên đã được xuống dòng vì mục đích trình bày; trong file Java, mỗi import phải viết liền một dòng, chẳng hạn:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

`mockUser("alice")` và `mockUser("bob")` chỉ áp dụng cho client được `mutateWith` trả về; client gốc được dùng ở request thứ ba vẫn không xác thực. `springSecurity()` thêm hỗ trợ test Spring Security khi client bind vào `ApplicationContext`. Test này kiểm tra bộ lọc và propagation trong môi trường mock server; **không** chứng minh Basic Auth/OAuth2/JWT thật, cũng không tương đương với HTTP test qua cổng mạng thực.

Nếu policy của ứng dụng bắt buộc xác thực cho `/identity`, request không có user phải trả `401 Unauthorized` (hoặc kết quả policy tương ứng) thay vì body `anonymous`; thay assertion cho phù hợp, không nới policy chỉ để làm test pass. Với hệ thống có session/cookie, phải chủ động kiểm thử hai trường hợp: request độc lập không chia sẻ cookie; và request cố ý dùng chung session có thể tiếp tục dùng danh tính đã đăng nhập. Đây là hai kỳ vọng khác nhau, không được gọi tính năng giữ session hợp lệ là rò rỉ ngữ cảnh.

## 6. Nâng cấp từ unit test sang kiểm thử tình huống khó

| Tình huống | Bố trí kiểm thử | Kết quả cần có |
| --- | --- | --- |
| Đổi thread liên tiếp | `subscribeOn` → `publishOn` → `flatMap` → `publishOn` → đọc lại | Cùng một `Authentication` trong một subscription |
| Xử lý đồng thời nhiều request | Gửi Alice/Bob với correlation ID riêng, tạo tải nhiều request | Mọi phản hồi đúng user của request tương ứng |
| Hủy khi stream đang chạy | SSE/stream dài; phía client đóng kết nối; phía server gắn `doFinally` | Quan sát `CANCEL` khi việc hủy thực sự lan tới publisher; request sau độc lập |
| Lỗi giữa chừng | Stream phát `onError` trước và sau scheduler hop | Request khác không bị đổi danh tính, tài nguyên được giải phóng |
| Không xác thực | Request mới không token/cookie hoặc mock context | Không kế thừa principal của request trước |
| Phân nhánh ngữ cảnh | Inner `flatMap` có `contextWrite` riêng | Ngữ cảnh chỉ thay đổi trong nhánh sở hữu nó |
| Có session/token repository | Kiểm tra token/cookie khác nhau, token hết hạn hoặc logout | Thực hiện đúng chính sách lưu/xóa xác thực |

Với test cancellation ở HTTP, `doFinally(CANCEL)` chỉ xảy ra nếu tín hiệu hủy được truyền đến publisher đang quan sát. Một publisher đã hoàn thành rất nhanh có thể báo `ON_COMPLETE` trước khi client kịp hủy; tránh viết assertion `CANCEL` cho luồng vốn đã hoàn tất. Có thể dùng một streaming endpoint có tín hiệu/đồng bộ rõ ràng thay vì dựa vào `Thread.sleep`.

Khi kiểm thử concurrency, nên gắn mỗi request một ID chỉ dành cho test và đối chiếu cặp `(requestId, expectedUsername, actualUsername)`. Không log access token, password, cookie session hoặc nguyên `SecurityContext` vào báo cáo test.

## 7. Các lỗi phổ biến và hướng sửa

**1. Dùng `SecurityContextHolder.getContext()` của kiểu imperative trong reactive flow.** Holder kiểu truyền thống thường dựa vào `ThreadLocal`; đổi scheduler có thể khiến kết quả rỗng hoặc vô tình đọc dữ liệu của công việc khác. Trong reactive pipeline, dùng `ReactiveSecurityContextHolder.getContext()` hoặc sử dụng principal/authentication qua API WebFlux phù hợp.

**2. Lưu `Authentication` vào biến `static`, singleton mutable field hoặc `ThreadLocal` tự quản.** Các request đồng thời có thể ghi đè hoặc đọc nhầm nhau. Chuyển dữ liệu theo Reactor `Context`, qua tham số rõ ràng hoặc qua cơ chế bảo mật có phạm vi request đã được framework hỗ trợ.

**3. Gọi `subscribe()` bên trong `map`/`doOnNext` rồi hy vọng ngữ cảnh tự chảy sang tác vụ mới.** Lệnh `subscribe()` độc lập tạo subscription mới có thể không kế thừa `Context`. Trả inner publisher vào `flatMap`/`concatMap` để framework giữ liên kết; nếu buộc tạo subscription ngoài luồng, phải quản lý rõ ràng ngữ cảnh và vòng đời, không giả định kế thừa.

```java
// Sai về cấu trúc: fire-and-forget tách khỏi subscription hiện tại.
Mono.just("event").doOnNext(value ->
    auditService.record(value).subscribe());

// Tốt hơn: cùng một pipeline, completion/error/cancellation được liên kết.
Mono.just("event").flatMap(value ->
    auditService.record(value).thenReturn(value));
```

Đoạn `auditService.record(...)` là mã minh họa giả định trả `Mono<Void>`; nó không phải ví dụ biên dịch độc lập. Cũng không nên xử lý audit bắt buộc bằng `subscribe()` tự phát trong request handler.

**4. Đặt `contextWrite` sai phía toán tử cần đọc.** Ngữ cảnh được cung cấp cho upstream, không tự lan sang những toán tử nằm downstream của điểm ghi. Dùng test về `bob/alice` để xác nhận phạm vi thay đổi thay vì suy đoán theo vị trí mã.

**5. Chỉ kiểm tra `Thread.currentThread().getName()`.** Tên thread chỉ phản ánh nơi thực thi, không chứng minh context đúng. Luôn assert `Authentication.getName()` (và authority/tenant nếu bài toán yêu cầu) tại điểm thực sự truy cập dữ liệu bảo vệ.

**6. Không hủy/đóng tài nguyên trong test.** Stream vô hạn mà chỉ chờ `verifyComplete()` có thể treo; scheduler do test tạo ra nhưng không `dispose()` có thể để lại thread. Dùng `thenCancel()`, timeout hữu hạn và `finally`.

**7. Đồng nhất hủy subscription với đăng xuất.** Cancellation kết thúc subscription và làm Reactor `Context` đó hết phạm vi sử dụng; nó không mặc nhiên thu hồi JWT, xóa server session, cookie hay dữ liệu tại `ServerSecurityContextRepository`. Cần test riêng chính sách logout/revoke.

**8. Test với `mockUser` rồi kết luận cơ chế xác thực ngoài thực tế an toàn.** `mockUser` bỏ qua bước kiểm chứng thông tin đăng nhập. Thêm integration test với cơ chế xác thực thật và credential/cookie của từng request nếu cần kiểm chứng login, token parsing hoặc session isolation.

**9. Hiểu sai context propagation của `ThreadLocal` và Reactor `Context`.** Cơ chế automatic context propagation hay thư viện chuyển MDC/`ThreadLocal` phục vụ tích hợp thread-local; không cần bật chúng chỉ để `ReactiveSecurityContextHolder` hoạt động qua các toán tử Reactor chuẩn.

**10. Kiểm thử chỉ tuần tự.** Một bài test Alice rồi Bob có thể bỏ sót race condition. Kết hợp test xen kẽ với `flatMap`, test đồng thời ở HTTP và test request ẩn danh để tìm trường hợp trạng thái bị dùng chung.

## 8. Tiêu chí hoàn thành và cách đọc kết quả

Đánh dấu bài kiểm thử là đạt khi các tiêu chí sau đều đúng:

- Test chuyển scheduler đọc đúng danh tính cả trước và sau `subscribeOn`/`publishOn`.
- Các subscription đồng thời trên một `Scheduler` luôn nhận đúng người dùng đã gắn cho chính mình; subscription không có context trả về `anonymous` ở unit test.
- Test cancellation phát `CANCEL`, sau đó Bob vẫn là Bob, luồng không xác thực vẫn không thấy Alice.
- `contextWrite` bên trong inner publisher không làm rò danh tính sang nhánh bên ngoài.
- HTTP test có cấu hình security phù hợp trả về Alice, Bob và anonymous/unauthorized đúng theo policy; không chia sẻ nhầm session/cookie.
- Không có `subscribe()` tách rời ngoài kiểm soát, trạng thái `Authentication` mutable toàn cục, test treo hoặc scheduler test chưa giải phóng.

**Giới hạn của bằng chứng:** test pass cho thấy các đường đi được kiểm thử giữ đúng ngữ cảnh, chứ không phải chứng minh tuyệt đối không thể có rò rỉ trên mọi nhánh, mọi thư viện ngoài Reactor, mọi loại authentication và mọi trạng thái session. Khi thay đổi code bảo mật, chạy lại test theo đúng security filter chain, token/session repository và tải đồng thời của hệ thống.

## 9. Tài liệu chính thống để tra cứu

- Spring Security — Reactive Method Security và `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — Cấu hình `WebTestClient`: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — `mockUser` cho reactive tests: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Project Reactor — `Context` gắn với subscriber và `contextWrite`: https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/context.html
- Reactor Test — `StepVerifier`, `thenCancel()` và `verify(Duration)`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
