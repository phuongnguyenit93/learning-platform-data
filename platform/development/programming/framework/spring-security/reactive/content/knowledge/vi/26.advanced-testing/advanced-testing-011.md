# Kiểm thử đồng thời để phát hiện mất ngữ cảnh hoặc rò rỉ danh tính trong Spring Security Reactive

## 1. Mục tiêu và phạm vi

Trong ứng dụng Spring WebFlux dùng Spring Security Reactive, hai request đến cùng thời điểm có thể cùng đi qua event loop, đổi scheduler, gọi các thao tác bất đồng bộ và hoàn tất theo thứ tự bất kỳ. Bài kiểm thử tốt phải trả lời được hai câu hỏi độc lập:

1. **Mất ngữ cảnh (context loss):** request của Alice đã được xác thực, nhưng sau một ranh giới bất đồng bộ, mã xử lý không còn tìm thấy `SecurityContext`/`Authentication` của Alice, hoặc nhận kết quả chưa xác thực.
2. **Rò rỉ danh tính (identity leakage):** request của Alice lại đọc được danh tính/quyền/dữ liệu của Bob (hoặc ngược lại) vì trạng thái bảo mật bị chia sẻ giữa các request.

Kết quả mong muốn: mọi subscription/request nhìn thấy đúng danh tính của **chính nó** xuyên suốt các bước bất đồng bộ; request vô danh không thừa hưởng phiên của request khác; phép kiểm tra quyền dựa trên principal đúng; số lượng kết quả không mất/nhân đôi. Chỉ kiểm tra HTTP 200 hoặc chỉ chạy tuần tự chưa đủ phát hiện rò rỉ.

Phạm vi là **Spring Security Reactive + Project Reactor + WebFlux**, không áp dụng thói quen dùng `SecurityContextHolder` kiểu `ThreadLocal` của ứng dụng Servlet để suy luận ngữ cảnh Reactive.

## 2. Cơ chế cần hiểu trước khi viết test

### 2.1. Reactor Context đi theo subscriber

`ReactiveSecurityContextHolder.getContext()` đọc `SecurityContext` từ **Reactor Context**, vốn gắn với luồng subscription. `ReactiveSecurityContextHolder.withAuthentication(authentication)` tạo một `Context` có authentication để gắn vào publisher bằng `contextWrite(...)`. `contextWrite` tác động lên phần **upstream** của chuỗi, theo cơ chế truyền ngữ cảnh lúc subscribe.

`publishOn(...)`, `subscribeOn(...)`, `delayElement(...)` và `flatMap(...)` trong một chuỗi Reactor chuẩn **không tự động làm mất Reactor Context** chỉ vì đổi thread. Lỗi thường xuất hiện khi lập trình viên phá vỡ chuỗi subscription hoặc dùng trạng thái ngoài Reactor: gọi `subscribe()` lồng nhau, chuyển sang `CompletableFuture`/callback thuần mà không chuyển ngữ cảnh phù hợp, lưu principal vào biến `static`/singleton, tự dùng `ThreadLocal` trên thread được tái sử dụng, hay dùng publisher/cache chia sẻ dữ liệu phụ thuộc danh tính.

Cần phân biệt **ngữ cảnh bảo mật** với các `ThreadLocal` phục vụ logging/MDC hoặc thư viện khác. Tính năng Micrometer/Reactor context propagation cho một số `ThreadLocal` có đăng ký accessor không đồng nghĩa với việc có thể đọc `SecurityContextHolder` kiểu Servlet trong mọi operator Reactive.

### 2.2. Bất biến bảo mật cần kiểm chứng

Giả sử có ba request đồng thời: `R-A` (Alice), `R-B` (Bob), `R-0` (anonymous).

| Request | Danh tính kỳ vọng | Điều kiện phải giữ |
| --- | --- | --- |
| `R-A` | `alice` | Mọi điểm đọc danh tính trong pipeline đều là `alice`; dữ liệu/quyền được lọc cho Alice |
| `R-B` | `bob` | Mọi điểm đọc danh tính đều là `bob`; không thấy dữ liệu chỉ dành cho Alice |
| `R-0` | Không có người dùng được xác thực | Bị từ chối ở tài nguyên yêu cầu đăng nhập (thường HTTP 401 với cấu hình HTTP Basic/Bearer); tuyệt đối không nhận principal của A/B |

Trên một endpoint trả tên người dùng, điều kiện đo được là `actualIdentity(request) == expectedIdentity(request)` cho **từng request**; không đủ nếu tập kết quả chỉ có cả hai tên nhưng bị hoán đổi giữa request. Với endpoint dữ liệu, kiểm thêm chủ sở hữu resource và HTTP 403 khi người dùng có đăng nhập nhưng thiếu quyền (mã cụ thể phụ thuộc chính sách của hệ thống).

## 3. Thiết kế kiểm thử nhiều lớp

- **Lớp 1 — publisher/service:** tạo từng `Authentication` khác nhau, gắn qua `contextWrite`, chạy nhiều `Mono` song song bằng `flatMap`/`merge`; dùng `StepVerifier` so sánh từng cặp expected/actual. Lớp này cô lập lỗi truyền `Reactor Context`.
- **Lớp 2 — WebFlux + security filter chain:** tạo `WebTestClient` gắn `springSecurity()`, áp `mockUser(...)` riêng cho **từng request**, chạy đồng thời và kiểm chứng status + response body. Lớp này bắt lỗi giữa filter, controller và service.
- **Lớp 3 — qua HTTP và cơ chế xác thực thật:** khi ứng dụng dùng JWT/session/OAuth2, gửi credential A/B khác nhau qua server đang chạy; kiểm chữ ký/issuer/audience/expiry, session và dữ liệu thật. `mockUser()`/`mockJwt()` giúp kiểm code authorization nhưng **không xác minh** bộ kiểm chữ ký token hoặc mạng thật.

Không dùng duy nhất `@WithMockUser` trên cả test để mô phỏng đồng thời hai danh tính: annotation đó phù hợp kiểm một security identity cho phương thức test, còn bài toán xen kẽ nhiều principal cần ngữ cảnh gắn từng publisher/request.

## 4. Ví dụ chạy được: kiểm thử ở tầng Reactor bằng JUnit 5

Ví dụ Java 17+ sau tạo **100 cặp Alice/Bob**, mỗi cặp dùng username riêng. `IdentityService` đọc danh tính **sau** `Mono.delay` và `publishOn` để kiểm tra ngữ cảnh sống qua ranh giới bất đồng bộ. Phép assert ghép `expected` với `observed` ngay trong publisher tương ứng nên phát hiện cả mất ngữ cảnh lẫn hoán đổi danh tính.

Tệp `src/test/java/example/security/ReactiveIdentityServiceTest.java`:

```java
package example.security;

import java.time.Duration;
import java.util.HashSet;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveIdentityServiceTest {

    static final class IdentityService {
        Mono<String> currentNameAfterAsyncBoundary() {
            return Mono.delay(Duration.ofMillis(2))
                    .publishOn(Schedulers.parallel())
                    .then(ReactiveSecurityContextHolder.getContext())
                    .switchIfEmpty(Mono.error(
                            new IllegalStateException("security context missing")))
                    .map(context -> context.getAuthentication().getName());
        }
    }

    record Observation(String expected, String observed) {}

    private final IdentityService service = new IdentityService();

    private Mono<Observation> requestAs(String username) {
        Authentication authentication = new UsernamePasswordAuthenticationToken(
                username, "ignored", AuthorityUtils.createAuthorityList("ROLE_USER"));

        return service.currentNameAfterAsyncBoundary()
                .map(actual -> new Observation(username, actual))
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(authentication));
    }

    @Test
    void concurrentSubscribersKeepTheirOwnIdentity() {
        int pairs = 100;

        Flux<Observation> requests = Flux.range(0, pairs)
                .flatMap(i -> Flux.merge(
                        requestAs("alice-" + i),
                        requestAs("bob-" + i)), 32);

        StepVerifier.create(requests.collectList())
                .assertNext(items -> {
                    assertEquals(pairs * 2, items.size());
                    Set<String> uniqueRequests = new HashSet<>();

                    for (Observation item : items) {
                        assertEquals(item.expected(), item.observed(),
                                "Cross-user identity or lost context");
                        assertTrue(uniqueRequests.add(item.expected()),
                                "Duplicated request: " + item.expected());
                    }
                })
                .verifyComplete();
    }

    @Test
    void missingContextDoesNotReuseLastUser() {
        StepVerifier.create(service.currentNameAfterAsyncBoundary())
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "security context missing".equals(error.getMessage()))
                .verify();
    }
}
```

**Vì sao test này có ý nghĩa?** `Mono.delay` tạo tín hiệu bất đồng bộ, `publishOn` buộc bước downstream chạy qua scheduler, `flatMap(..., 32)` cho nhiều inner publisher đang hoạt động đồng thời, và `contextWrite` gắn `Authentication` riêng ở thời điểm subscribe. `StepVerifier` không phụ thuộc thứ tự hoàn thành; nó bắt lỗi theo cặp request. Test âm tính xác nhận publisher thiếu security context báo lỗi đã quy định, thay vì vô tình thấy principal của lần chạy trước.

**Cách chạy:** thêm các dependency test trong mục 6, sau đó dùng Gradle với bộ kiểm thử JUnit Platform:

```bash
./gradlew test --tests 'example.security.ReactiveIdentityServiceTest'
```

Trên Windows, dùng `gradlew.bat` thay `./gradlew`. Hai phép thử phải hoàn thành thành công; test không cố định thứ tự kết quả và không in danh tính ra stdout.

## 5. Ví dụ tích hợp: nhiều WebTestClient request với principal riêng

Đây là một fixture test Spring Boot WebFlux độc lập với controller mẫu `GET /whoami`, security chain yêu cầu đăng nhập và test client kết nối với `ApplicationContext`. Trong sản phẩm thật, dùng controller/service đang có thay fixture test. **Lưu ý:** `mockUser(...)` hoạt động qua cấu hình Spring Security test của `WebTestClient` bind in-memory; không phải credential gửi qua HTTP đến một server độc lập.

Tệp `src/test/java/example/security/ConcurrentIdentityWebTest.java`:

```java
package example.security;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;
import java.util.stream.Stream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        classes = ConcurrentIdentityWebTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ConcurrentIdentityWebTest {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    record Attempt(String expected, String observed) {}

    @Test
    void concurrentUsersNeverReceiveAnotherUsersPrincipal() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            List<String> users = IntStream.range(0, 40)
                    .boxed()
                    .flatMap(i -> Stream.of("alice-" + i, "bob-" + i))
                    .toList();

            List<CompletableFuture<Attempt>> tasks = users.stream()
                    .map(user -> CompletableFuture.supplyAsync(() -> {
                        String response = client.mutateWith(mockUser(user))
                                .get().uri("/whoami")
                                .exchange()
                                .expectStatus().isOk()
                                .expectBody(String.class)
                                .returnResult().getResponseBody();
                        return new Attempt(user, response);
                    }, pool))
                    .toList();

            CompletableFuture.allOf(tasks.toArray(new CompletableFuture[0]))
                    .get(60, TimeUnit.SECONDS);

            for (CompletableFuture<Attempt> task : tasks) {
                Attempt attempt = task.join();
                assertEquals(attempt.expected(), attempt.observed(),
                        "The response belongs to a different principal");
            }

            client.get().uri("/whoami")
                    .exchange()
                    .expectStatus().isUnauthorized();
        } finally {
            pool.shutdownNow();
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({IdentityController.class, SecurityConfig.class})
    static class TestApplication {}

    @RestController
    static class IdentityController {
        @GetMapping("/whoami")
        Mono<String> whoami() {
            return Mono.delay(Duration.ofMillis(5))
                    .then(ReactiveSecurityContextHolder.getContext())
                    .map(context -> context.getAuthentication().getName());
        }
    }

    @Configuration
    @EnableWebFluxSecurity
    static class SecurityConfig {
        @Bean
        SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
            return http
                    .authorizeExchange(exchange ->
                            exchange.anyExchange().authenticated())
                    .httpBasic(Customizer.withDefaults())
                    .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                    .build();
        }
    }
}
```

**Các điểm tránh test giả:** mỗi lời gọi sử dụng `client.mutateWith(mockUser(user))` để có cấu hình riêng, không thay đổi một biến `currentUser` dùng chung; `ExecutorService` cho 8 request thực sự có thể cùng chạy, `Mono.delay` tạo khoảng chồng lấn trong controller, và phần kiểm tra so sánh body với username gốc của **đúng future**. `exchange()` là API đồng bộ trong test nên chạy trên pool của test; không nhét thao tác blocking này vào event loop của ứng dụng. Khối `finally` dừng pool cả khi assert/timeout lỗi.

Chạy fixture bằng:

```bash
./gradlew test --tests 'example.security.ConcurrentIdentityWebTest'
```

Nếu app thật có quy tắc quyền phức tạp, thay `/whoami` bằng endpoint yêu cầu tenant/owner cụ thể và kiểm thêm request Alice vào tài nguyên Bob phải bị từ chối theo chính sách; chỉ so sánh username là phép thử nền, chưa chứng minh toàn bộ authorization.

## 6. Dependency và môi trường chạy

Ví dụ Gradle Groovy cho dự án Spring Boot quản lý phiên bản dependency (đoạn cấu hình để ghép vào `build.gradle` hiện có, không phải tệp build độc lập):

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

Yêu cầu Java 17+ và Spring Boot/Spring Security/Reactor tương thích với nhau qua BOM của Spring Boot. Nếu module đã có các dependency này thì không khai báo trùng. Mục 4 kiểm service trực tiếp; mục 5 nạp ứng dụng WebFlux tối giản và filter chain trong test. Không cần server production, database, tài khoản thật hay token thật cho hai fixture.

## 7. Bộ test case tối thiểu khi chuyển sang ứng dụng thật

| Kịch bản | Cách kích thích | Assert bắt buộc |
| --- | --- | --- |
| Hai người dùng cùng role | Trộn 50–100 request A/B, thay username/subject mỗi lần | Principal, resource owner và tenant đúng từng request |
| Hai người dùng khác role | Xen kẽ USER/ADMIN tới endpoint có phân quyền | Các response 200/403 đúng cho đúng credential; B không hưởng quyền A |
| Anonymous xen giữa A/B | Trộn request không credential | 401 hoặc kết quả chính sách đã định; không lộ body người dùng trước |
| Đổi scheduler | `delay`, `publishOn`, bất đồng bộ I/O trong pipeline | Identity giữ nguyên; không có `Mono.empty()` bất ngờ |
| Lỗi / hủy / retry | Một request bị timeout/cancel/error khi request khác còn chạy | Không chuyển principal sang subscriber khác; cleanup hợp lệ |
| Dùng token/session thật | A/B sử dụng credential độc lập khi gọi server qua mạng | AuthN + AuthZ + tenant isolation đều đúng; kiểm expiry/invalid token |
| Tải lặp lại | Chạy nhiều vòng cùng seed/tham số và tăng mức song song có giới hạn | Không có mismatch nào; số request hoàn tất/timeout được ghi rõ |

Để kiểm JWT trong `WebTestClient` ở tầng mock, có thể dùng `mockJwt().jwt(jwt -> jwt.subject("alice"))` (với resource-server test setup phù hợp). Khi cần chứng minh xác thực thật, dùng hai JWT ký hợp lệ do hệ thống test phát hành và gửi header `Authorization: Bearer ...`; mock JWT không kiểm tra signature decoder.

## 8. Lỗi thường gặp, cách nhận diện và sửa

### 8.1. Mất `SecurityContext` vì tách subscription

Dấu hiệu: test Alice đơn lẻ thành công nhưng sau chuyển sang callback/`CompletableFuture` hoặc `subscribe()` thủ công thì `ReactiveSecurityContextHolder.getContext()` rỗng. Mỗi lần `subscribe()` tạo subscription mới; không được mặc định subscription mới kế thừa Context từ subscription cha.

- Sai hướng: trong service gọi `someMono.subscribe(...)` để tạo side effect rồi trả về `Mono.just(...)`; nhánh chạy riêng không còn nằm trong pipeline mà caller gắn `contextWrite`.
- Hướng sửa: trả về publisher và ghép bằng `flatMap`, `then`, `zipWhen` hoặc toán tử Reactor phù hợp; để framework/caller subscribe một lần ở biên hệ thống.
- Khi bắt buộc dùng API không Reactive, truyền identity/authorization data một cách tường minh đến callback, hoặc dùng cầu nối context propagation được thiết kế và kiểm thử cho thư viện đó. Không suy ra tự động có security context vì đang chạy trên cùng thread.

### 8.2. Rò rỉ vì trạng thái dùng chung

Ví dụ **cố ý sai** dưới đây có thể cho Alice nhận `bob` khi hai yêu cầu xen kẽ. `AtomicReference` chỉ giúp truy cập bộ nhớ an toàn giữa thread, không làm trạng thái trở thành riêng của request.

```java
// ANTI-PATTERN: trạng thái principal toàn cục
static final java.util.concurrent.atomic.AtomicReference<String> LAST_USER =
        new java.util.concurrent.atomic.AtomicReference<>();

static Mono<String> broken(String username) {
    return Mono.defer(() -> {
        LAST_USER.set(username);
        return Mono.delay(Duration.ofMillis(10))
                .map(ignored -> LAST_USER.get());
    });
}
```

Hướng sửa: không lưu `Authentication`/principal/tenant của request trong singleton, `static`, mutable field hoặc cache không khóa theo identity. Đọc từ `ReactiveSecurityContextHolder` đúng subscription, hoặc truyền chủ sở hữu tài nguyên như tham số bất biến khi nghiệp vụ cần. Nếu đặt object mutable vào `Context`, object đó vẫn có thể bị chia sẻ bằng tham chiếu; bản thân `Context` bất biến không làm các value bên trong trở thành bất biến.

### 8.3. Test cho kết quả xanh giả

- Chỉ assert `isOk()`: A có thể nhận dữ liệu B mà test vẫn PASS.
- Dùng chung một mock principal cho toàn bộ request: không tạo được tình huống giao thoa danh tính.
- Gọi tuần tự: ít cơ hội kích hoạt bug khi callback/scheduler xen kẽ.
- Phụ thuộc `Thread.sleep` để ép race: khó lặp lại và dễ flaky; ưu tiên latch/barrier hoặc phép thử với các pipeline chồng lấn có kiểm soát.
- Kiểm kết quả bằng thứ tự hoàn thành cố định: `flatMap` cho phép hoàn tất bất kỳ thứ tự nào; phải kiểm cặp expected/actual.
- Gán lỗi cho `publishOn` hoặc `delayElement` mà không xác định ranh giới tách subscription/chia sẻ state thực sự.
- Đọc `SecurityContextHolder` (Servlet/ThreadLocal) trong WebFlux rồi kết luận Reactor Context sai.

## 9. Tăng độ tin cậy, chẩn đoán khi FAIL

1. Dùng principal phân biệt rõ (`alice-0`, `bob-0`, ...), số vòng chạy và mức concurrency hữu hạn. Mỗi test case nên có `requestId`/`correlationId` độc lập và liên kết với expected principal.
2. Khi FAIL, ghi: requestId, expected principal/tenant/role, actual principal/tenant/role, operator/endpoint nơi phát hiện, số vòng và concurrency. **Không log raw JWT, password, cookie hay dữ liệu cá nhân nhạy cảm.**
3. Thu nhỏ bản tái hiện về 2 request/2 principal. Dùng `CountDownLatch` trong test hoặc barrier mô phỏng để tái tạo đúng thời điểm giao nhau nếu đã xác định race; không chặn event-loop production.
4. Kiểm cách tạo subscription, mọi lần `contextWrite`, `subscribe()` thủ công, `cache/share`, callback sang thư viện ngoài Reactor, và mutable state singleton. Đặt phép đọc identity ở **sau** ranh giới nghi ngờ để thấy lỗi đúng vị trí.
5. Sau khi sửa, chạy lại unit test, WebFlux test, test qua credential thật và test lặp. Kết quả PASS của fixture chỉ khẳng định các điều kiện nó assert trong cấu hình test; không tự chứng minh mọi luồng runtime đều an toàn.

## 10. Checklist hoàn thành bài

- [ ] Phân biệt được context loss với identity leakage, biết rò rỉ dữ liệu là rủi ro nghiêm trọng hơn một lỗi 401.
- [ ] Giải thích vì sao Reactor Context theo subscriber; không gắn quyền danh tính với thread.
- [ ] Test tạo ≥2 principal khác nhau, thực sự có các publisher/request chồng lấn.
- [ ] Mỗi response được gắn với expected identity ban đầu và kiểm đúng principal, role, owner/tenant khi áp dụng.
- [ ] Có test anonymous và nhánh deny; không đánh đồng mock authentication với credential thật.
- [ ] Có ranh giới bất đồng bộ (`delay`/scheduler/I/O) và không dùng `subscribe()` lồng nhau làm mất context.
- [ ] Test chạy lặp, lỗi có thông tin tái hiện, không phụ thuộc thứ tự trả về hay `sleep` may rủi.
- [ ] Không ghi/giữ nguyên principal request trong static/singleton/ThreadLocal không kiểm soát.

## Tài liệu đối chiếu

- Spring Security — [Testing Authentication trong Reactive WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html) và [thiết lập WebTestClient với springSecurity()](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html).
- Spring Security — [Reactive Method Security và Reactor Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html), [Testing OAuth2/JWT](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html).
- Project Reactor — [Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html) và [Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).
