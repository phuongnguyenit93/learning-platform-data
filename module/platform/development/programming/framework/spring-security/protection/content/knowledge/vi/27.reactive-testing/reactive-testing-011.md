# Giữ riêng cấu hình, dữ liệu và danh tính giữa các ca kiểm thử

> **Chương:** Kiểm thử Reactive  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Mục đích:** Bảo đảm các phép thử HTTP protection trong **Spring Security WebFlux** độc lập về cấu hình, dữ liệu, principal, cookie, session và Reactor Context. Từ đó, test CSRF/CORS/headers/CSP/HSTS, HTTP firewall, login/logout, authorization không cho kết quả ngẫu nhiên do ca trước để lại trạng thái.  
> **Dòng tham chiếu:** Java 17+, Spring Security 6.5/7.x, Spring Framework 6.2/7.x, Spring Boot 3.5/4.x, JUnit Jupiter, Reactor Test và `WebTestClient`. Mọi ví dụ về package/version phải kiểm tra lại theo BOM thực tế của ứng dụng.

## 1. Khi test xanh một mình nhưng đỏ khi chạy toàn bộ suite

Hãy tưởng tượng có ba ca kiểm thử:

```text
Test A: Alice đăng nhập, POST /private/orders, tạo order BOOK-01.
Test B: Bob gọi GET /private/orders, kỳ vọng không thấy order của Alice.
Test C: Anonymous gọi GET /private/whoami, kỳ vọng 401.

Chạy riêng:
  A PASS; B PASS; C PASS.

Chạy A → B → C:
  B thấy BOOK-01 do shared singleton repository không được reset.
  C nhận "alice" do WebTestClient bị mutate thành client đã auth.
```

Một bộ kiểm thử như vậy có thể bỏ sót lỗi **tenant isolation**, **authorization** hoặc **session fixation**. Nghiêm trọng hơn, một POST thiếu CSRF có thể vượt qua bài test vì client dùng chung đã bị gắn `csrf()` mutator, hoặc kiểm thử CORS origin lạ vẫn nhận header do configuration test trước làm thay đổi singleton.

**Isolation (cô lập ca kiểm thử)** không có nghĩa bắt buộc khởi động lại toàn bộ Spring context trước mọi `@Test`. Nó có nghĩa:

- Mỗi ca có **đầu vào, principal và dữ liệu kiểm thử có kiểm soát**.
- Tác động từ ca trước không thay đổi kết quả ca sau.
- Không phụ thuộc thứ tự chạy, trừ workflow kịch bản được mô tả **bên trong cùng một test**.
- Test vừa kiểm tra điều kiện hợp lệ, vừa xác minh **danh tính/dữ liệu không rò** qua đường biên request, session và tenant.
- Khi chạy song song, các ca không ghi/đọc trạng thái shared có thể làm kết quả sai.

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt scope của `ApplicationContext`, bean singleton, dữ liệu database/cache, `WebSession`, Reactor `Context` và `WebTestClient`.
2. Chọn `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, `@DirtiesContext` và bean override đúng mục đích.
3. Viết WebFlux security tests dùng `mockUser()`, `mockJwt()`, `@WithMockUser` hoặc HTTP credentials thật mà không làm principal rò sang request/test khác.
4. Dựng fixture WebTestClient mới ở mỗi test, có reset test data nhưng vẫn tận dụng Spring TestContext cache an toàn.
5. Phân tách dữ liệu theo user/tenant/test namespace, bảo vệ session cookie và CSRF token độc lập.
6. Test `ReactiveSecurityContextHolder` ở mức publisher bằng Reactor `contextWrite`/`StepVerifier`, không dựa vào `SecurityContextHolder` ThreadLocal của Servlet.
7. Nhận diện giới hạn của rollback `@Transactional` với R2DBC, server chạy cổng thật và hệ thống ngoài.
8. Tổ chức Testcontainers, Redis/Spring Session, time/clock và external side effects để test ổn định khi CI chạy song song.
9. Thiết kế ma trận âm/dương để bắt các hành vi sai về authentication, authorization, CSRF, CORS, headers và session.

## 2. Năm ranh giới phải giữ độc lập

| Ranh giới | Trạng thái có thể rò | Phương pháp cô lập | Dấu hiệu kiểm thử sai |
| --- | --- | --- | --- |
| **Cấu hình** | Active profile, SecurityWebFilterChain, CORS origin, HTTP headers, bean override | Test class/context config rõ, `@TestPropertySource`/`@ActiveProfiles`, test context cache hợp lý | Một test làm policy của test sau thay đổi |
| **Dữ liệu nghiệp vụ** | Singleton map, database rows, R2DBC repo, Redis key, Kafka event | Reset deterministic hoặc unique test namespace/tenant, cleanup có scope | Bob thấy dữ liệu của Alice từ ca khác |
| **Danh tính** | `Authentication`, role, JWT claims, mock principal | Request-scoped `mutateWith`, `@WithMockUser` có scope rõ, Reactor Context | Anonymous request bị nhận là Alice |
| **HTTP/browser state** | Cookie `SESSION`/`XSRF-TOKEN`, CSRF header, default Authorization header, request cache | Client/cookie jar riêng, bootstrap mới, không mutate client base dùng chung | POST không token vẫn pass |
| **Thời gian/hệ thống ngoài** | Redis TTL, message queue, scheduled task, cache, mock invocation, virtual clock | Fake clock, isolated container/topic/key prefix, await deterministic | Suite thỉnh thoảng fail do delayed event |

Không chỉ “reset một bean” rồi xem như đã cô lập tất cả. Ví dụ reset database nhưng vẫn dùng client có `Authorization: Bearer alice` mặc định thì test anonymous có thể sai. Ngược lại, xây mới WebTestClient mỗi test nhưng tất cả vẫn truy vấn cùng Redis database với prefix `orders:` cũng chưa độc lập về dữ liệu.

### 2.1. Sơ đồ đời sống một phép thử Reactive

```text
JUnit @Test instance
       |
       +-- Spring TestContext cache
       |    +-- ApplicationContext (có thể dùng lại giữa các tests)
       |    +-- singleton beans / WebFilters / SecurityWebFilterChain
       |
       +-- @BeforeEach
       |    +-- reset data test-only hoặc cấp namespace duy nhất
       |    +-- tạo baseline WebTestClient
       |
       +-- request #1
       |    +-- WebTestClient + mockUser("alice") dành riêng request
       |    +-- ServerWebExchange + Reactor Context + WebSession S1
       |
       +-- request #2
       |    +-- WebTestClient anonymous/bob (không mang state #1)
       |    +-- ServerWebExchange + Reactor Context/session riêng
       |
       +-- Assertions: status + principal + body + side effects
       |
       +-- Cleanup/AfterEach (đợi async work hoàn tất)
```

**Bất biến quan trọng:** tách biệt *test instance* không đồng nghĩa tách biệt *singleton beans* hoặc *database*. JUnit Jupiter thường tạo một test instance mới cho mỗi method, nhưng Spring có thể cache và tái sử dụng nguyên `ApplicationContext`/singleton bean.

### 2.2. Bài này và các bài CSRF/CORS/WebFlux trước khác nhau thế nào?

Một test `POST /orders` thiếu CSRF trả 403 là **hành vi bảo mật riêng của request**. Bài này hỏi thêm: nếu test trước đã POST với `mockUser("alice")` và `csrf()`, test tiếp theo có chắc đang bắt đầu từ **client và dữ liệu sạch** không? Nếu hai WebSessions S1/S2 dùng chung Redis, có thực sự không gửi nhầm `SESSION` cookie? Nếu config CORS thay giữa hai test classes, có đang dùng lại một `ApplicationContext` từ cache theo key cũ không?

Mục tiêu không phải lặp lại tất cả chi tiết về CSRF/CORS, mà là tạo **kỷ luật fixture và assertions** để các bài kiểm thử HTTP protection đáng tin cậy.

## 3. Ba cấp kiểm thử và giới hạn isolation

| Loại | Cấu hình được nạp | Danh tính test | Dữ liệu và trạng thái |
| --- | --- | --- | --- |
| Unit Reactor/Service | Có thể không có Spring context | `ReactiveSecurityContextHolder.withAuthentication(...)` | Dữ liệu object/test instance cục bộ |
| Mock WebFlux integration | `bindToApplicationContext(context).apply(springSecurity())` | `mockUser`/`mockJwt`, session mock | Spring singleton/context thường shared, request exchange riêng |
| Full HTTP `RANDOM_PORT` | Server thật và full Spring context | Basic/form/JWT/session **qua HTTP thật** | DB/Redis/container có thể shared giữa tests |

Không dùng `WebTestClient.bindToController` để suy toàn bộ Spring Security WebFilters đã chạy. Ngược lại, `@SpringBootTest` không đồng nghĩa mở cổng TCP; chỉ `webEnvironment=RANDOM_PORT`/`DEFINED_PORT` mới tạo HTTP server ở cấu hình phù hợp.

Một phương án test isolation tốt:

1. Unit tests cho pure mappers, token parsers và Reactor Context.
2. Mock WebFlux integration cho rule authorization, CSRF, CORS và header writers — nhanh, độc lập principal theo request.
3. Live HTTP tests cho session cookie, auth/login/logout, issuer/JWT decoder và persistence.
4. Browser HTTPS smoke tests cho `SameSite`, CSP, HSTS, cross-origin và reverse proxy.

## 4. Phiên bản và dependencies của fixture

Ví dụ dùng **Java 17+** và BOM Spring Boot tương thích với Spring Security/Framework đã chọn:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu dự án dùng Maven:

```xml
<dependencies>
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
```

Boot 4 có test starters tổ chức theo stack và một số test annotation đổi package. Các ví dụ `@SpringJUnitConfig` thuần Spring không phụ thuộc Boot; khi dùng `@WebFluxTest` hoặc `@AutoConfigureWebTestClient`, chọn imports đúng dòng Boot và test starter:

```java
// Spring Boot 3.x:
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;

// Spring Boot 4.x:
// import org.springframework.boot.webflux.test.autoconfigure.WebFluxTest;
```

Không copy cả hai imports vào cùng lớp. `spring-security-test` phải cùng dòng phù hợp với `spring-security-web`/`spring-security-config`, tránh việc test helper tồn tại nhưng production API khác.

Để tự kiểm tra dependency của dự án:

```bash
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./mvnw dependency:tree -Dincludes=org.springframework.security
```

Trên Windows dùng wrapper `gradlew.bat` hoặc `mvnw.cmd`. Các đoạn lệnh là bài thực hành, không phải kết quả build đã được chạy tại STEP 4.

## 5. Dựng fixture WebFlux có dữ liệu theo principal

Để thấy một request có thể đúng authentication nhưng vẫn đọc nhầm dữ liệu, ta xây controller lấy principal của **chính request**, lưu đơn hàng theo tên user và kiểm tra không có side effect khi request bị từ chối.

### 5.1. In-memory store dùng chung để cố ý bộc lộ nguy cơ

```java
package com.example.reactiveisolation;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

public final class InMemoryOrders {
    private final ConcurrentHashMap<String, CopyOnWriteArrayList<String>>
        byOwner = new ConcurrentHashMap<>();

    public void add(String owner, String sku) {
        byOwner.computeIfAbsent(
            owner, ignored -> new CopyOnWriteArrayList<>()
        ).add(sku);
    }

    public List<String> list(String owner) {
        List<String> rows = byOwner.get(owner);
        return rows == null ? List.of() : List.copyOf(rows);
    }

    public int totalCount() {
        return byOwner.values().stream()
            .mapToInt(List::size).sum();
    }

    public void clearForTests() {
        byOwner.clear();
    }
}
```

Store này **là singleton bean** khi được đăng ký trong Spring context, nghĩa là tồn tại qua nhiều `@Test` nếu context được cache. `ConcurrentHashMap` chỉ giúp các thao tác thread-safe ở mức cấu trúc; nó **không** tự reset data hoặc bảo đảm nghiệp vụ đa-tenant. Đừng dùng store này cho production persistence.

### 5.2. Controller thực sự lấy principal từ request

```java
package com.example.reactiveisolation;

import java.security.Principal;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IsolationController {

    public record CreateOrder(String sku) {}

    private final InMemoryOrders orders;

    public IsolationController(InMemoryOrders orders) {
        this.orders = orders;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/private/whoami")
    public Mono<String> whoami(Mono<Principal> principal) {
        return principal.map(Principal::getName);
    }

    @GetMapping("/private/orders")
    public Mono<List<String>> myOrders(Mono<Principal> principal) {
        return principal.map(p -> orders.list(p.getName()));
    }

    @PostMapping("/private/orders")
    public Mono<ResponseEntity<Void>> createOrder(
            Mono<Principal> principal,
            @RequestBody Mono<CreateOrder> request) {

        return Mono.zip(principal, request)
            .doOnNext(tuple ->
                orders.add(
                    tuple.getT1().getName(),
                    tuple.getT2().sku()
                )
            )
            .thenReturn(
                ResponseEntity.status(HttpStatus.CREATED)
                    .<Void>build()
            );
    }

    @GetMapping("/admin/count")
    public Mono<Integer> totalCount() {
        return Mono.fromSupplier(orders::totalCount);
    }
}
```

Ở đây principal là `Mono<Principal>` của **request đang xử lý**. Không lưu `Principal` hoặc `Authentication` vào trường static, singleton field hay `ThreadLocal` dùng lại; làm vậy có thể khiến Alice đọc dữ liệu của Bob khi Reactive chain đổi thread.

`Mono.zip(principal, request)` chỉ thêm đơn nếu cả principal và body được phát, rồi trả 201. Các tests dùng body JSON hợp lệ (ví dụ `{"sku":"BOOK-01"}`). Cần validate payload thật trong production; bài này tập trung vào isolation.

### 5.3. WebFlux infrastructure và Spring Security chain

```java
package com.example.reactiveisolation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class IsolationWebConfig {

    @Bean
    InMemoryOrders orders() {
        return new InMemoryOrders();
    }

    @Bean
    IsolationController controller(InMemoryOrders orders) {
        return new IsolationController(orders);
    }
}
```

```java
package com.example.reactiveisolation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class IsolationSecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .pathMatchers("/private/**").authenticated()
                .anyExchange().denyAll()
            )
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService testUsers() {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password("{noop}fixture-only")
                .roles("USER").build(),
            User.withUsername("bob")
                .password("{noop}fixture-only")
                .roles("USER").build(),
            User.withUsername("admin")
                .password("{noop}fixture-only")
                .roles("ADMIN").build()
        );
    }
}
```

Chuỗi rule bảo vệ:

- `/public/**` có thể gọi anonymous.
- `/private/**` phải có authentication; POST cần **CSRF** theo mặc định.
- `/admin/**` cần `ROLE_ADMIN`, không chỉ authenticated.
- Các path khác bị `denyAll()`.

`{noop}` password chỉ dùng cho fixture, **không** dùng production. `@EnableWebFlux` thích hợp context thuần Spring Test; trong Spring Boot app đã auto-config WebFlux, không tùy ý thêm vì có thể thay đổi defaults.

## 6. Baseline `WebTestClient` mới cho từng test

### 6.1. Test class không sửa client base sau khi tạo

```java
package com.example.reactiveisolation;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringJUnitConfig(classes = {
    IsolationWebConfig.class,
    IsolationSecurityConfig.class
})
class IsolatedRequestsTest {

    @Autowired ApplicationContext applicationContext;
    @Autowired InMemoryOrders orders;

    private WebTestClient base;

    @BeforeEach
    void setUp() {
        // An toàn khi test class chạy tuần tự và chỉ fixture này dùng store.
        orders.clearForTests();

        // Một client baseline không auth, không default cookies/headers.
        base = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    // Đặt các @Test thuộc mục 7–9 bên dưới ở class này.
}
```

`@BeforeEach` chạy trước mỗi method, nhưng **`ApplicationContext` có thể vẫn được tái sử dụng** từ cache. `orders.clearForTests()` là lựa chọn **chỉ phù hợp** vì fixture singleton được sở hữu bởi test class và suite chạy tuần tự. Nếu hai tests chạy song song hoặc class khác cũng dùng store, lệnh clear giữa chừng có thể xóa dữ liệu của một request còn đang xử lý.

### 6.2. Không ghi đè biến `base` bằng client có principal

Mẫu sai:

```java
@Test
void leakingAuthClientBetweenRequestsIsAnAntiPattern() {
    // Không khuyến nghị:
    base = base.mutateWith(mockUser("alice").roles("USER"));
    // Từ đây base không còn là baseline anonymous.
}
```

Mẫu trên không nhất thiết rò qua **một test method khác** nếu `@BeforeEach` luôn dựng lại `base`; nhưng nó rò sang **các requests tiếp theo trong chính test** và có thể rò giữa tests nếu `base` là static/shared hoặc setup bị bỏ qua. Chọn:

```java
WebTestClient alice = base.mutateWith(
    mockUser("alice").roles("USER")
);
WebTestClient bob = base.mutateWith(
    mockUser("bob").roles("USER")
);

// base vẫn anonymous; alice/bob được dùng cục bộ.
```

Không đẩy `alice`/`bob` vào singleton holder hoặc static field. Các client này chỉ dành cho **mock HTTP testing**; `mockUser` không tạo phiên đăng nhập thật.

### 6.3. Khi nào cần cleanup trong `@AfterEach`?

`@BeforeEach` reset để test bắt đầu từ baseline; `@AfterEach` hữu ích để xác nhận không còn tasks/in-flight events và xóa dữ liệu test-owned trước class khác chạy. Nếu cleanup lỗi, suite nên fail rõ thay vì nuốt exception. Với external services:

- Chỉ xóa keys/rows có **test namespace** hoặc tenant prefix của ca đó.
- Không `FLUSHALL` Redis shared dev/staging.
- Không truncate database không thuộc test container.
- Không cleanup bằng background `subscribe()` fire-and-forget rồi lập tức kết thúc test.

## 7. Mỗi HTTP request có một principal rõ ràng

### 7.1. Anonymous không được hưởng quyền của test trước

```java
@Test
void anonymousRequestIsNotAliceEvenAfterAliceRequest() {
    base.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/private/whoami")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("alice");

    // Cùng test nhưng dùng baseline chưa mutate.
    base.get().uri("/private/whoami")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

Đây là **negative control** cực kỳ quan trọng. Chỉ assert Alice trả 200 không chứng minh identity isolation; ca anonymous chạy ngay sau Alice mới phát hiện client/default header/session bị dùng lại.

### 7.2. Alice và Bob không đọc lẫn principal

```java
@Test
void aliceAndBobSeeDifferentNamesWithoutClientLeakage() {
    WebTestClient alice = base.mutateWith(
        mockUser("alice").roles("USER"));
    WebTestClient bob = base.mutateWith(
        mockUser("bob").roles("USER"));

    alice.get().uri("/private/whoami")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("alice");

    bob.get().uri("/private/whoami")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("bob");
}
```

Với application khác sử dụng custom principal type hoặc OAuth2 claim `sub`, không thay bằng username đơn giản rồi nghĩ rằng đã test toàn bộ tenant policy. Nhưng cơ chế **request-scoped identity** vẫn giống nhau.

### 7.3. Quyền ADMIN không rò sang USER/anonymous

```java
@Test
void roleForOneRequestDoesNotElevateAnother() {
    base.mutateWith(mockUser("admin").roles("ADMIN"))
        .get().uri("/admin/count")
        .exchange()
        .expectStatus().isOk();

    base.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/admin/count")
        .exchange()
        .expectStatus().isForbidden();

    base.get().uri("/admin/count")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

Với fixture HTTP Basic-only ở mục 5, mặc định anonymous protected request trả 401; khi dùng form login có thể trả 302. **Dùng status theo authentication entry point đã cấu hình**, không assert 401 cho mọi ứng dụng.

### 7.4. Không dùng `@WithMockUser` lớp-level mặc định nếu cần tests anonymous

Một lớp test có:

```java
@WithMockUser(username = "alice")
class AllAuthenticatedTests { /* ... */ }
```

sẽ đưa authentication mặc định vào **mọi test** nếu listeners áp dụng. Điều này làm test “anonymous” trong lớp có thể âm thầm được coi là Alice. Đối với các suites bảo mật cần nhiều danh tính, ưu tiên annotation **theo method** hoặc request-specific `mutateWith`.

Nếu cần class-level default thật sự, `@WithAnonymousUser` trên method có thể override theo Spring Security Test. Với Reactive method-security publisher, listeners phải tích hợp `ReactorContextTestExecutionListener` theo Spring Test support; không suy annotation chạy qua live HTTP network.

## 8. Dữ liệu theo user: kiểm thử cả kho dữ liệu lẫn quyền truy cập

### 8.1. Alice tạo dữ liệu, Bob không thấy dữ liệu của Alice

```java
import org.springframework.http.MediaType;

@Test
void ordersAreScopedToAuthenticatedOwner() {
    WebTestClient alice = base.mutateWith(
        mockUser("alice").roles("USER"));
    WebTestClient bob = base.mutateWith(
        mockUser("bob").roles("USER"));

    alice.mutateWith(csrf())
        .post().uri("/private/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new IsolationController.CreateOrder("BOOK-01"))
        .exchange()
        .expectStatus().isCreated();

    alice.get().uri("/private/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(String.class)
        .contains("BOOK-01");

    bob.get().uri("/private/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(String.class)
        .hasSize(0);

    assertEquals(1, orders.totalCount());
}
```

Nhận xét: Bob không thấy `BOOK-01` chứng minh controller lấy dữ liệu theo principal, **không** chứng minh mọi IDOR đã bị chặn. Trong production, còn phải test endpoint dạng `GET /orders/{id}`/`DELETE /orders/{id}` không cho Bob thao tác lên ID của Alice.

### 8.2. POST thiếu CSRF không được tạo dữ liệu

```java
@Test
void forbiddenPostDoesNotPolluteNextTestData() {
    base.mutateWith(mockUser("alice"))
        .post().uri("/private/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new IsolationController.CreateOrder("BAD"))
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, orders.totalCount());
}
```

Test riêng POST hợp lệ không đủ. Cần kiểm tra **side effect count bằng 0** khi CSRF/authorization từ chối; nếu repository/queue vẫn có dữ liệu thì filter order hoặc business transaction boundary có vấn đề.

### 8.3. Dữ liệu còn lại từ test trước là false positive/false negative

Nếu bỏ `orders.clearForTests()`, một test trước tạo `BOOK-01` có thể khiến:

```java
assertEquals(1, orders.totalCount());
```

“xanh” ngay cả khi handler của test hiện tại **không hề tạo order**. Ngược lại, test kỳ vọng store rỗng có thể đỏ do một test không liên quan. Vì thế điều kiện chuẩn là **baseline rõ ràng**, không chỉ “một giá trị cuối trông hợp lý”.

### 8.4. Tốt hơn reset global: dữ liệu có namespace theo ca

Khi tests cần chạy song song, tránh mọi ca dùng cùng key `alice` trong cùng singleton store. Hướng cải tiến:

```text
test-run=run-21, test-case=case-A, tenant=tenant-A
key: test:run-21:case-A:orders:tenant-A:alice

test-run=run-21, test-case=case-B, tenant=tenant-B
key: test:run-21:case-B:orders:tenant-B:alice
```

Tạo namespace từ `UUID.randomUUID()` hoặc một tên ổn định duy nhất cho mỗi method/test run. **Không chỉ đổi mock username** nếu application authorization vẫn dùng tenant từ JWT claim/header khác; namespace phải đi qua query/persistence boundary thật.

## 9. `WebTestClient` không phải cookie jar hay session tự động an toàn

### 9.1. Đừng mutate baseline bằng `defaultHeader` hoặc `defaultCookie`

Một lỗi khó phát hiện:

```java
@Test
void unsafeClientMutationExample() {
    WebTestClient alice = base.mutate()
        .defaultHeader("Authorization", "Bearer alice-test-token")
        .defaultCookie("SESSION", "alice-session")
        .build();

    // alice dùng riêng cho test có chủ đích.
    // KHÔNG ghi "base = alice" hoặc lưu client vào biến static.
}
```

Trong Java, `mutate()` tạo builder cho client mới, nhưng **nếu bạn thay biến `base` hoặc dùng cùng client đã cấu hình default headers** thì request tiếp theo sẽ tự mang Authorization/cookie ngoài ý muốn.

Mẫu tốt:

```java
WebTestClient authenticated = base.mutate()
    .defaultHeader("Authorization", "Bearer scoped-fixture-token")
    .build();

// anonymous vẫn dùng base:
base.get().uri("/private/whoami") /* ... */;
```

Đoạn trên chỉ minh họa **cách giới hạn scope cấu hình client**, chưa khẳng định Bearer token giả sẽ authenticate. Fixture ở mục 5 dùng HTTP Basic, nên một Bearer header tự đặt không làm user authenticated; dùng `mockUser()` cho mock request hoặc credentials thật qua HTTP khi phù hợp.

### 9.2. Các yếu tố có thể ở “default” mà test không để ý

| Nơi cấu hình | Giá trị nguy hiểm nếu dùng lại | Cách an toàn |
| --- | --- | --- |
| `WebTestClient.defaultHeader(...)` | `Authorization`, `Origin`, `X-CSRF-TOKEN` | Tạo local client riêng cho một scenario |
| `WebTestClient.defaultCookie(...)` | `SESSION`, `XSRF-TOKEN` | Session fixture/cookie jar riêng |
| Client filters | Tự thêm Basic/Bearer credentials | Không gắn vào baseline anonymous |
| `mutateWith(mockUser())` | Principal hoặc roles test | Gọi trên `base` và giữ local returned client |
| `mutateWith(csrf())` | Request được giả lập là có CSRF hợp lệ | Chỉ áp vào positive control tương ứng |
| `mutateWith(mockJwt())` | JWT claims/scopes giả lập | Không dùng để test chữ ký/expiry JWT |
| Shared cookie store/custom client | Session trước được tự gửi | Reset/đổi client, tạo browser contexts riêng |

Không nên xem việc tạo WebTestClient mới **tự động xóa state server-side**. Nó chỉ giảm khả năng rò default config/cookie phía client; dữ liệu trong Redis/DB/WebSession store vẫn tồn tại nếu không cleanup/invalidate đúng.

### 9.3. Auth principal không tự biến thành WebSession authentication thật

`SecurityMockServerConfigurers.mockUser(...)` gắn authentication vào **mock ServerWebExchange**. Nó không chạy:

- HTTP Basic password verification qua provider,
- Form login success handler/session fixation,
- JWT signature/issuer/audience decoder,
- OAuth2 authorization-code grant,
- Browser cookie acceptance.

Vì vậy test identity isolation bằng `mockUser` rất phù hợp cho **authorization behavior**, nhưng test login/logout session lifecycle cần HTTP requests và session cookie thật.

## 10. CSRF token và session cookie giữa hai ca không được trộn

### 10.1. Mỗi bootstrap là cặp session/token gắn nhau

Ở WebFlux, `WebSessionServerCsrfTokenRepository` là lựa chọn mặc định phổ biến. Một endpoint GET đọc `Mono<CsrfToken>` từ `ServerWebExchange` và thực sự consume publisher có thể cấp expected token trong WebSession:

```java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public record CsrfEnvelope(String headerName, String token) {}

@GetMapping("/public/csrf")
public Mono<ResponseEntity<CsrfEnvelope>> csrf(
        ServerWebExchange exchange) {
    Mono<CsrfToken> source =
        exchange.getAttribute(CsrfToken.class.getName());
    if (source == null) {
        return Mono.error(new IllegalStateException(
            "CSRF filter not active for this request"));
    }
    return source.map(t -> ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(new CsrfEnvelope(t.getHeaderName(), t.getToken())));
}
```

**Đoạn này là phần thêm vào một `@RestController` phù hợp**, không phải method top-level Java. Để test round-trip, thêm endpoint vào fixture trong một test variant. Trong context WebSession repository mặc định, cookie session thường có tên `SESSION`, nhưng Spring Session/custom resolver có thể đổi.

### 10.2. Request #1: bootstrap S1/token1, request #2: bootstrap S2/token2

```java
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;

record BrowserSession(
    String cookieName, String cookieValue,
    String headerName, String csrfToken
) {}

BrowserSession freshSession(WebTestClient anonymousClient) {
    EntityExchangeResult<CsrfEnvelope> result =
        anonymousClient.get().uri("/public/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectBody(CsrfEnvelope.class)
            .returnResult();

    CsrfEnvelope t = result.getResponseBody();
    org.junit.jupiter.api.Assertions.assertNotNull(t);

    ResponseCookie cookie =
        result.getResponseCookies().getFirst("SESSION");
    org.junit.jupiter.api.Assertions.assertNotNull(cookie);

    return new BrowserSession(
        cookie.getName(), cookie.getValue(),
        t.headerName(), t.token());
}
```

Với **mock WebTestClient baseline không có default cookies**, mỗi `freshSession(base)` không truyền cookie của lần trước nên tạo session độc lập nếu token lần đó được generate/save. Nếu dùng HTTP client có cookie jar tự động, phải tạo jar/context riêng hoặc xóa cookie store trước bootstrap thứ hai.

### 10.3. S1/T1 không được dùng để xác thực request CSRF của S2

```java
@Test
void csrfTokensMustNotCrossWebSessions() {
    BrowserSession a = freshSession(base);
    BrowserSession b = freshSession(base);

    org.junit.jupiter.api.Assertions.assertNotEquals(
        a.cookieValue(), b.cookieValue());

    WebTestClient alice = base.mutateWith(
        mockUser("alice").roles("USER"));

    // Không dùng csrf() helper: kiểm repo/handler thật.
    alice.post().uri("/private/orders")
        .cookie(b.cookieName(), b.cookieValue())
        .header(a.headerName(), a.csrfToken())
        .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
        .bodyValue(new IsolationController.CreateOrder("CROSS"))
        .exchange()
        .expectStatus().isForbidden();

    assertEquals(0, orders.totalCount());
}
```

Đây là test của **WebSession repository**. Nếu app dùng `CookieServerCsrfTokenRepository`, expected token được đọc từ CSRF cookie và **không mặc nhiên ràng buộc với server-side WebSession** giống WebSession repo; đừng áp invariant sai cho repository khác.

### 10.4. Positive control cùng session

```java
@Test
void matchingCookieAndCsrfTokenAreAccepted() {
    BrowserSession browser = freshSession(base);

    base.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/private/orders")
        .cookie(browser.cookieName(), browser.cookieValue())
        .header(browser.headerName(), browser.csrfToken())
        .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
        .bodyValue(new IsolationController.CreateOrder("OK"))
        .exchange()
        .expectStatus().isCreated();

    assertEquals(1, orders.totalCount());
}
```

Giữ **cùng hostname/scheme/path policy** trong app thực; ở mock request có thể truyền cookie dù browser sẽ không gửi nó vì `Secure/SameSite/Domain/Path`. Do đó vẫn cần HTTPS browser tests.

### 10.5. Token của hai GET có thể khác vì XOR/BREACH masking

Spring Security 6.x/7.x WebFlux mặc định có thể dùng `XorServerCsrfTokenRequestAttributeHandler`, khiến token exposed có randomness ngay cả khi expected raw token trong cùng WebSession không đổi. **Không** assert hai giá trị exposed token “phải bằng nhau” để chứng minh session isolation.

Kiểm tra đúng:

- S1 và S2 là hai session IDs khác nhau trong fixture.
- Token S1 dùng với cookie S2 bị chặn.
- Token S2 dùng với cookie S2 được đi tiếp.
- Không có order bị ghi ở ca negative.

Khi dùng cookie-based SPA token, kiểm tra raw cookie và masked/header handler riêng. Không tắt CSRF để làm các tests qua.

## 11. `ApplicationContext` được cache — nguồn rò cấu hình âm thầm

Spring TestContext Framework **cache `ApplicationContext` giữa các tests và classes có context configuration key tương đương**. Cache là một static cache trong cùng JVM/test suite; nó giúp giảm thời gian nạp WebFlux/Security beans nhưng cũng giữ các **singleton state** chưa được reset.

### 11.1. Những thành phần của context cache key

Theo Spring Framework TestContext reference, khóa cache có thể dựa trên:

- `@ContextConfiguration` classes/locations, initializers, loader.
- `@ActiveProfiles`.
- `@TestPropertySource` properties/locations.
- `@DynamicPropertySource` và context customizers.
- Bean override như `@MockitoBean`/`@MockitoSpyBean`.
- Context hierarchy, parent và resource base path.

Do đó, **hai lớp cùng config** có thể chia sẻ context/singleton; **hai lớp có profiles/test properties khác** thường tạo context khác theo cache key. Không giả định “mỗi class có một context mới”, cũng không giả định “@DirtiesContext ở lớp A luôn chỉ ảnh hưởng A”.

### 11.2. Cache context ≠ cache HTTP request

`WebTestClient.bindToApplicationContext(context)` dựng request/response mock cho từng exchange; những exchange đó độc lập, nhưng context chứa:

```text
SecurityWebFilterChain / HandlerMapping
singleton InMemoryOrders
singleton CacheManager
ReactiveUserDetailsService fixture
ObjectMapper / validation / config beans
ConnectionFactory / WebSession manager
```

Nếu `InMemoryOrders` giữ dữ liệu test A, test B thấy dữ liệu đó dù exchange/client hoàn toàn mới. Đây là **rò dữ liệu qua bean singleton**, không phải principal leak.

### 11.3. Khi nào dùng `@DirtiesContext`?

`@DirtiesContext` đánh dấu context đã bị “dirty”; Spring đóng và loại nó khỏi cache, để test tiếp theo với cùng config load context mới:

```java
import org.springframework.test.annotation.DirtiesContext;

@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringJUnitConfig(classes = {
    IsolationWebConfig.class,
    IsolationSecurityConfig.class
})
class ContextMutatingTests {
    // Chỉ dùng cho case thật sự thay đổi global bean state/config.
}
```

Tuy nhiên đây thường là **phương án sau cùng**, vì reload context tốn thời gian và làm parallel tests phức tạp. Thay vì `@DirtiesContext` để xóa vài order rows, ưu tiên cleanup đúng scope hoặc cấp store/namespace riêng.

### 11.4. Không lạm dụng `@DirtiesContext`

| Điều muốn cô lập | Cách ưu tiên | Cần `@DirtiesContext`? |
| --- | --- | --- |
| Một list dữ liệu trong singleton fixture | `clearForTests()` ở suite tuần tự hoặc per-test namespace | Không thường xuyên |
| Data rows trong test DB | Cleanup có scope, schema/DB riêng | Không |
| Một HTTP session cookie | Browser/client mới, invalidate session test-owned | Không |
| Mock invocation history | Reset/clear mock theo supported lifecycle | Không |
| Thay đổi bean definition/critical singleton policy giữa tests | Test context khác hoặc reload context | Có thể |
| Mỗi test cần thật sự boot một config khác | `@TestPropertySource`/`@ActiveProfiles` theo class | Thường không |

Đừng dùng `@DirtiesContext` để “chữa” một flaky test do queue message đến chậm hoặc database chưa cleanup: context mới **không xóa** state trong external Kafka/Redis/Postgres.

### 11.5. Chẩn đoán context cache hit/miss

Có thể bật log Spring TestContext cache:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Hoặc cấu hình logger tương đương trong test. Mục tiêu: quan sát context hit/miss/reload, không in credentials/properties nhạy cảm. Cache mặc định có giới hạn, và khi vượt giới hạn có LRU eviction; context đang bị close trong test parallel có thể gây lỗi “context no longer active”.

Nếu suite khởi động lại context hàng trăm lần, kiểm tra có tạo `@TestPropertySource`/`@MockitoBean` khác nhau tùy từng method/class hay lạm dụng `@DirtiesContext` không.

## 12. Cô lập cấu hình qua profile và property sources

### 12.1. Đừng thay JVM system properties trong mỗi `@Test`

Mẫu nguy hiểm:

```java
@Test
void changingGlobalPropertyIsUnsafe() {
    System.setProperty(
        "app.cors.allowed-origin",
        "https://temporary.example"
    );
    // Context có thể đã được tạo; test khác cùng JVM thấy property.
}
```

`System.setProperty` là trạng thái **process-wide**. Một context đã được khởi tạo có thể không tự rebuild các beans đã bind config, trong khi code gọi `Environment.getProperty()` động lại thấy giá trị mới, dẫn đến các nguồn truth không nhất quán. Parallel tests càng dễ gặp race.

**Thay thế:** sử dụng properties theo **test class/context** bằng `@TestPropertySource` hoặc `@SpringBootTest(properties=...)`, không mutate một JVM-global value giữa các methods.

### 12.2. Hai test classes có policy khác nhau

Ví dụ hai test classes độc lập:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
    IsolationWebConfig.class,
    IsolationSecurityConfig.class
})
@TestPropertySource(properties = {
    "app.security.mode=strict",
    "app.cors.allowed-origin=https://app.example.test"
})
class StrictPolicyPropertiesTest {
    @Autowired Environment env;

    @Test
    void strictPolicyIsBoundInThisContext() {
        org.junit.jupiter.api.Assertions.assertEquals(
            "strict", env.getProperty("app.security.mode"));
    }
}
```

```java
@SpringJUnitConfig(classes = {
    IsolationWebConfig.class,
    IsolationSecurityConfig.class
})
@TestPropertySource(properties = {
    "app.security.mode=compatibility",
    "app.cors.allowed-origin=https://legacy.example.test"
})
class CompatibilityPolicyPropertiesTest {
    @Autowired Environment env;

    @Test
    void compatibilityPolicyHasOwnPropertySource() {
        org.junit.jupiter.api.Assertions.assertEquals(
            "compatibility", env.getProperty("app.security.mode"));
    }
}
```

Hai properties khác nhau tham gia **cache key**, nên được phép có hai contexts khác nhau. Nhưng **fixture `IsolationSecurityConfig` chưa dùng `app.security.mode` để đổi Security behavior**: những tests trên chứng minh property source isolation, không chứng minh rule CORS/CSRF đổi theo property.

Để test policy behavior, một bean như `CorsConfigurationSource`/`SecurityWebFilterChain` phải thực sự đọc property (ví dụ qua `@Value`, `@ConfigurationProperties`) và có requests âm/dương. Đừng dùng một assertion `Environment.getProperty()` rồi suy app đã áp dụng policy.

### 12.3. `@ActiveProfiles` tách môi trường nhưng không xóa DB

```java
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("security-test")
@SpringJUnitConfig(classes = {
    IsolationWebConfig.class,
    IsolationSecurityConfig.class
})
class SecurityTestProfileTests {
    // Dùng đúng test profile được khai báo cho context.
}
```

`@ActiveProfiles("security-test")` ảnh hưởng environment/bean selection/context cache key. Nó **không** tự tạo database mới, vô hiệu Redis cũ hay xóa static mocks. Nếu test profile vẫn trỏ tới Redis/database production hoặc shared staging thì isolation bị hỏng nghiêm trọng.

### 12.4. Kiểm thử default Security chain không bị bean profile khác thay thế

Khi có nhiều `SecurityWebFilterChain` dưới `@Profile` hoặc `@ConditionalOnProperty`, hãy test:

```text
Profile security-test:
  GET /private/whoami anonymous -> 401 (Basic fixture)
  GET /admin/count Alice USER    -> 403
  POST /private/orders no CSRF   -> 403

Profile browser:
  GET protected anonymous       -> 302 /login nếu form login
  POST state-changing no CSRF    -> 403

Profile api:
  GET /api/** without Bearer      -> 401 (không redirect login)
```

Chỉ test profile/env string chưa đủ: cần request-level assertions để phát hiện một chain test vô tình `permitAll()` hoặc `csrf.disable()`.

### 12.5. Không đặt secrets thật trong `@TestPropertySource`

Tránh đặt database password, OAuth2 client secret, JWT private key hoặc production credentials trực tiếp trong test code. Ưu tiên Testcontainers ephemeral credentials/test-only issuer, CI secret injection có scope giới hạn và redaction. **Test isolation không phải lý do để bỏ bảo vệ secrets**.

## 13. `@DynamicPropertySource`, container ports và context cache

### 13.1. Khi nào dùng dynamic properties?

Với PostgreSQL/Redis/Testcontainers, hostname và mapped port chỉ được biết khi container đã chạy. Spring Framework hỗ trợ `@DynamicPropertySource` static method đăng ký Suppliers để context lấy giá trị:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void configureDynamicProperties(
        DynamicPropertyRegistry registry) {
    registry.add("app.external.url", server::getBaseUrl);
}
```

`server` ở đây là một **test fixture object có lifecycle được quản lý**; không phải Spring class có sẵn. Method `@DynamicPropertySource` phải static và nhận đúng một `DynamicPropertyRegistry`. Không đổi giá trị external server đang chạy giữa test classes trong khi cache còn dùng cùng context.

### 13.2. Ví dụ PostgreSQLContainer + R2DBC

Khi dự án có dependencies Testcontainers, R2DBC PostgreSQL driver và Spring Data R2DBC:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class IsolatedR2dbcIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password_only");

    @DynamicPropertySource
    static void dbProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
            "r2dbc:postgresql://"
                + POSTGRES.getHost() + ":"
                + POSTGRES.getMappedPort(5432) + "/"
                + POSTGRES.getDatabaseName()
        );
        registry.add("spring.r2dbc.username",
            POSTGRES::getUsername);
        registry.add("spring.r2dbc.password",
            POSTGRES::getPassword);
    }

    @Test
    void runAgainstDedicatedTestDatabase() {
        // Bổ sung R2DBC repository integration tests + cleanup.
    }
}
```

Đây là **template** yêu cầu app có R2DBC schema migrations, config datasource và Testcontainers dependencies, không phải một standalone test tự đầy đủ khi copy vào dự án bất kỳ. Container DB chỉ dùng test, không connect dữ liệu thật. Testcontainers có thể start/stop static container ở phạm vi class; muốn shared reusable container trên nhiều classes, cần quản lý lifecycle tương ứng và context cache semantics kỹ càng.

### 13.3. Cạm bẫy: context cached nhưng container port đã thay

`@DynamicPropertySource` participates trong test context configuration, nhưng nếu hai subclasses kế thừa cùng method và **giá trị dynamic supplier thay đổi** giữa chúng, context cache có thể dùng lại beans chứa giá trị cũ. Spring reference khuyến nghị có thể cần `@DirtiesContext` trong **trường hợp đặc biệt** này để rebuild context với dynamic properties mới.

Giải pháp ưu tiên: quản lý container lifecycle **cùng hoặc dài hơn** lifecycle của context sử dụng nó; không đóng container rồi tiếp tục dùng context cached trỏ về mapped port không tồn tại.

### 13.4. Dynamic property precedence

Dynamic properties có precedence cao hơn `@TestPropertySource` trong Spring TestContext. Nếu `@TestPropertySource` ghi URL A nhưng `@DynamicPropertySource` ghi URL B, bean có thể lấy B. Khi debug “test trỏ nhầm DB”, kiểm tra:

1. Dynamic registry suppliers.
2. Active profiles.
3. Test property sources.
4. Context reuse và container lifecycle.
5. Spring Boot `@ServiceConnection`/connection details nếu đã dùng.

Không in password hoặc full connection string có credentials vào report/CI logs.

## 14. Bean overrides và mock invocation state

### 14.1. Mock bean cũng là một bean trong context

Spring Framework 6.2+ cung cấp `@MockitoBean`/`@MockitoSpyBean` dưới `org.springframework.test.context.bean.override.mockito`. Spring Boot 3.x có `@MockBean`/`@SpyBean` (dòng cũ; đã deprecated trong những bản mới). Dòng Boot 4 ưu tiên APIs Spring Framework phù hợp.

Ví dụ:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringJUnitConfig(classes = SomeServiceConfig.class)
class ServiceUsingMockTest {

    @MockitoBean
    ExternalAuditGateway auditGateway;

    @Test
    void auditCanBeStubbedPerTest() {
        // Stub/verify qua Mockito, không dùng shared static mock.
    }
}
```

`ExternalAuditGateway` và `SomeServiceConfig` ở đây là **interfaces/config do dự án định nghĩa**, không phải Spring APIs; ví dụ chỉ minh họa annotation scope. Tùy TestContext/Spring version, Mockito mock có lifecycle reset được quản lý theo mặc định hoặc cấu hình; hãy xác minh reset mode và đừng phụ thuộc vào mock invocation từ method trước.

### 14.2. Dữ liệu mock stubbing và invocation history là hai thứ

Nếu test A:

```java
when(gateway.check("alice")).thenReturn(true);
verify(gateway).check("alice");
```

test B có thể sai nếu một mock shared còn stubbing/invocations từ A. Với mock có framework-managed reset, dùng lifecycle mặc định/`MockReset` theo version; với plain Mockito mocks test-local, tạo lại mỗi test. Không gọi `reset(...)` bừa bãi trong production code hoặc giữa lúc một async call còn đang chạy.

### 14.3. Không biến mọi dependency thành mock

Một integration test CSRF/CORS/headers cần **Security WebFilters thật**; nếu mock `ServerSecurityContextRepository`, `ServerCsrfTokenRepository` hoặc `SecurityWebFilterChain` quá sâu, bài test có thể pass vì bạn đã bypass chính lớp cần đo. Mock outbound HTTP/notification gateway có thể phù hợp, nhưng auth/authorization/storage boundary cần xác định rõ đâu là đối tượng kiểm chứng.

### 14.4. Context cache key thay đổi khi bean override khác

Một class có `@MockitoBean ExternalAuditGateway` và class không override bean thường tạo context configuration khác, tránh dùng chung context quá mức. Tuy nhiên **cùng một override config** giữa hai classes có thể vẫn chia sẻ context/mock lifecycle được quản lý. Đừng dựa vào việc “test class mới” để mặc định mock là object mới nếu không kiểm chứng.

## 15. R2DBC, transactions và dọn dữ liệu đúng phạm vi

### 15.1. Không mặc định `@Transactional` sẽ rollback mọi WebFlux request

Spring TestContext test-managed `@Transactional` truyền thống dựa vào `PlatformTransactionManager` và thread-bound test transactions. Trong Reactive, R2DBC thường dùng `ReactiveTransactionManager`/`TransactionalOperator` cùng **Reactor Context**, và HTTP requests qua `RANDOM_PORT` chạy ở server threads/transaction boundaries khác.

Vì vậy:

```java
@Transactional
@Test
void naiveAssumption() {
    // Gọi live HTTP server POST /orders
    // Không được mặc định mọi R2DBC write trong server request
    // sẽ tự rollback khi JUnit method này kết thúc.
}
```

Test-managed JDBC rollback **không phải** cơ chế dọn tất cả dữ liệu ngoài HTTP request của server. Nếu app dùng R2DBC, Kafka, Redis hoặc background tasks, rollback của test thread cũng không xóa những side effects ấy.

### 15.2. Hai chiến lược cleanup phổ biến

| Chiến lược | Ưu điểm | Nguy cơ | Khi nào dùng |
| --- | --- | --- | --- |
| Dedicated test DB/schema + reset theo test | Dễ assert baseline bằng SQL | Không song song an toàn nếu reset toàn schema | Suite tuần tự, environment ephemeral |
| Unique test namespace/tenant/owner + cleanup có điều kiện | Song song tốt hơn, ít ảnh hưởng test khác | Cần thiết kế query scope và cleanup mạnh | Integration/parallel/CI |
| Container riêng mỗi test class | Infrastructure độc lập hơn | Chi phí tài nguyên/startup | Các bài test cần DB topology/config khác |
| TransactionalOperator cho một reactive publisher | Test business transaction logic | Không tự ôm HTTP server, Redis và queue | Unit/service reactive tests |

**Quan trọng:** không truncate bảng dữ liệu production/staging; mọi cleanup phải chạy trên database test chuyên dụng và xác minh database identity/URL trước khi xóa.

### 15.3. Ví dụ data namespace + cleanup R2DBC

Trong một test class **có table `orders(test_run, owner, sku)` và `DatabaseClient` được inject**:

```java
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.r2dbc.core.DatabaseClient;

class ScopedOrdersIntegrationTest {
    @Autowired DatabaseClient db;
    String testRun;

    @BeforeEach
    void allocateNamespace() {
        testRun = "it-" + UUID.randomUUID();
    }

    @AfterEach
    void removeOwnedRows() {
        // block() ở JUnit cleanup, KHÔNG ở WebFlux event loop.
        db.sql("DELETE FROM orders WHERE test_run = :run")
            .bind("run", testRun)
            .fetch()
            .rowsUpdated()
            .then()
            .block();
    }
}
```

Đây là **fragment** của integration test, không phải standalone class đầy đủ `@SpringBootTest`/schema. Mọi test data created phải mang cột `test_run` tương ứng và truy vấn phải lọc theo đó. Nếu server endpoint không nhận namespace nhưng test chỉ lưu UUID ở JUnit field, cleanup sẽ không tìm đúng rows; cần truyền metadata qua **test-authorized** API/payload/tenant context rồi đảm bảo không expose như bypass trong production.

Không cho người dùng production tự chọn tenant ID bất kỳ chỉ vì test cần namespace: tenant phải được ràng buộc với authenticated principal/claims ở server.

### 15.4. Thử thất bại giữa transaction

Một test reactive service có thể dùng `TransactionalOperator`:

```java
Mono<Void> operation = transactionalOperator
    .transactional(
        repository.save(order)
            .then(Mono.error(
                new IllegalStateException("simulated-failure")))
    )
    .then();

StepVerifier.create(operation)
    .expectError(IllegalStateException.class)
    .verify();
```

Ở đây `transactionalOperator` và `repository` là beans/fixtures **cần khai báo** trong test app. Với R2DBC driver/transaction manager hỗ trợ và cùng reactive transaction, có thể kiểm rằng order không được commit sau error. Nhưng event đã gửi tới Kafka trước error hoặc Redis key ghi ngoài transaction **không được rollback tự động**; cần outbox/idempotency/compensation và tests riêng.

### 15.5. Test không nên tự tạo “sự thật” bằng cleanup

Nếu handler sai vô tình ghi data dưới owner Bob, cleanup `DELETE WHERE test_run=:run` có thể xóa bằng chứng sau test. Vì vậy phải **assert trước khi cleanup**:

- Alice thấy dữ liệu của Alice.
- Bob không nhìn thấy/không sửa được dữ liệu Alice.
- Tổng row count/owner IDs đúng.
- Request bị 403/401 không sinh rows.
- Không có dữ liệu ngoài namespace test bị sửa.

Cleanup là cơ chế bảo vệ môi trường, **không** thay assertions security.

## 16. Redis, WebSession và CSRF token là state của server

### 16.1. Redis store khác với local cookie jar

Một browser test có thể tạo:

```text
Browser A:
  SESSION=sess-a
  XSRF-TOKEN=raw-token-a  (nếu cookie repository)

Browser B:
  SESSION=sess-b
  XSRF-TOKEN=raw-token-b

Redis:
  spring:session:sessions:<sess-a>
  spring:session:sessions:<sess-b>
```

Tạo hai WebTestClient chỉ cô lập **client-side cookies**; nó không tự xóa Redis session records hoặc đảm bảo A/B được sinh từ độc lập. Ngược lại, nếu dùng shared cookie jar, A/B có thể vô tình cùng `SESSION` dù mỗi object WebTestClient trông như một client khác.

### 16.2. WebSession repository và cookie CSRF repository có semantics khác

| CSRF repository | Expected token nằm ở đâu? | Isolation test cần gì? |
| --- | --- | --- |
| `WebSessionServerCsrfTokenRepository` | WebSession server-side | Session S1/T1 và S2/T2 riêng; POST T1/S2 bị từ chối |
| `CookieServerCsrfTokenRepository` | CSRF cookie trên request | Cookie/header phải match; không mặc định token mật mã gắn với WebSession |

Với session-authenticated SPA, **authentication cookie** phải giữ `HttpOnly/Secure/SameSite` phù hợp. Cookie `XSRF-TOKEN` chỉ đặt `HttpOnly=false` khi JavaScript thực sự cần đọc nó, không tắt `HttpOnly` của session auth cookie để test dễ hơn.

### 16.3. Session expiration không tương đương logout

`WebSession.invalidate()` làm mất session, còn idle timeout phụ thuộc `WebSessionStore`/Redis TTL. Logout handler có thể xóa `SecurityContext`, CSRF token và/hoặc invalidate WebSession theo config. Các tests cần tách:

- S1/T1 hợp lệ khi session còn sống.
- S1/T1 cũ bị từ chối sau explicit invalidation.
- S1/T1 cũ bị từ chối sau **expiration thật**.
- Session/authentication không được tái sử dụng sau logout nếu policy yêu cầu.

Không lấy một POST không gửi session cookie làm bằng chứng TTL đã hết. Cần store/time control hoặc staging timeout nhỏ có kiểm tra.

### 16.4. Không dùng Redis `FLUSHDB`/`FLUSHALL` trên store shared

Nếu mỗi test có key prefix `it:<runId>:<caseId>:`, có thể cleanup **chỉ những keys prefix được cấp** và chờ publisher hoàn thành. Tuy nhiên Redis Spring Session keys có thể gồm indexed/set/expiration indexes do framework quản lý; xóa một vài key thô theo prefix không tương đương invalidate session đúng API.

Ưu tiên **dedicated Redis container/database** cho integration suite, hoặc dùng `WebSession.invalidate()`/Spring Session repository APIs hợp lệ để xóa test-owned sessions. Không xóa toàn Redis instance có thể chứa dữ liệu của các test families/người dùng khác.

### 16.5. Đừng để scheduled cleanup chạy sau khi test kết thúc

Trong WebFlux:

```java
// Anti-pattern: fire-and-forget cleanup
redis.delete(key).subscribe();
// @AfterEach return ngay, test sau có thể vẫn thấy key.
```

Nên:

```java
// Test teardown được phép block ngoài event loop:
redis.delete(key).then().block();
```

`redis` là test-owned `ReactiveStringRedisTemplate`/reactive Redis API phù hợp (đoạn fragment). Nếu cleanup là một multi-key transactional operation hoặc có retry, phải await toàn bộ. Đừng gọi `block()` trong production WebFlux request handler; rule ở đây dành cho setup/teardown JUnit thread.

## 17. Reactor Context: danh tính thuộc **subscription**, không thuộc thread

### 17.1. Vì sao `SecurityContextHolder` ThreadLocal dễ sai ở Reactive?

Trong Servlet, một request thường gắn với một thread trong phần lớn vòng đời. Trong Reactor, publisher có thể chuyển scheduler/thread giữa các operators; reactive method security dùng `ReactiveSecurityContextHolder` và **Reactor Context**.

```text
subscribe request Alice
    |
    +-- Context{Authentication=Alice}
    +-- publishOn(boundedElastic) -> thread khác
    +-- Service đọc Reactor Context -> Alice

subscribe request Bob
    |
    +-- Context{Authentication=Bob}
    +-- filter/flatMap -> thread có thể tái sử dụng
    +-- Service đọc Reactor Context -> Bob
```

Không lưu request principal trong `static Authentication currentUser` hoặc lấy `SecurityContextHolder.getContext()` trong mọi Reactor operator rồi giả định sẽ là user hiện tại.

### 17.2. Test hai subscriptions dùng cùng publisher nhưng khác context

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void identityDoesNotLeakBetweenReactorSubscriptions() {
    Mono<String> whoami = ReactiveSecurityContextHolder
        .getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .defaultIfEmpty("anonymous");

    var alice = new TestingAuthenticationToken(
        "alice", "ignored", "ROLE_USER");
    var bob = new TestingAuthenticationToken(
        "bob", "ignored", "ROLE_USER");

    StepVerifier.create(whoami.contextWrite(
            ReactiveSecurityContextHolder
                .withAuthentication(alice)))
        .expectNext("alice")
        .verifyComplete();

    StepVerifier.create(whoami.contextWrite(
            ReactiveSecurityContextHolder
                .withAuthentication(bob)))
        .expectNext("bob")
        .verifyComplete();

    StepVerifier.create(whoami)
        .expectNext("anonymous")
        .verifyComplete();
}
```

`ReactiveSecurityContextHolder.withAuthentication(...)` tạo **Reactor Context** cho subscription, không thay một global user cho JVM. Đây là test rất phù hợp để phát hiện một service tự lưu `Authentication` vào biến static/instance cache.

### 17.3. Context propagation qua scheduler

```java
@Test
void authenticationSurvivesReactorSchedulerHop() {
    var auth = new TestingAuthenticationToken(
        "alice", "ignored", "ROLE_USER");

    Mono<String> work = ReactiveSecurityContextHolder
        .getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(reactor.core.scheduler.Schedulers.parallel())
        .map(name -> name + "-processed")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));

    StepVerifier.create(work)
        .expectNext("alice-processed")
        .verifyComplete();
}
```

Khi dùng operators Reactor chuẩn, context được truyền theo subscription. Nhưng tự khởi tạo một `CompletableFuture`/`new Thread`, subscribe lồng hoặc gọi blocking library ngoài pipeline có thể mất context nếu chưa thiết kế context propagation rõ ràng.

### 17.4. Đừng gọi `subscribe()` tay để “giữ danh tính”

```java
// Anti-pattern trong controller/service:
audit.logForCurrentUser().subscribe();
return Mono.just("ok");
```

Fire-and-forget tạo một subscription độc lập, có thể mất context/lifecycle/error handling và chạy sau test kết thúc. Hãy compose:

```java
return audit.logForCurrentUser()
    .thenReturn("ok");
```

Các code fragments giả định `audit` là reactive service đã được inject và trả `Mono<Void>`. Nếu cần gửi background event, đưa vào queue/outbox có contract và test side effects/identity rõ, không dựa vào context ngẫu nhiên của thread thực thi.

## 18. `@WithMockUser` với Reactive Method Security

### 18.1. Khác biệt giữa test HTTP WebFilter và test service method

`mockUser()` trên `WebTestClient` hợp với HTTP request tests. Với một service method `@PreAuthorize` trả `Mono`/`Flux`, Spring Security Test hỗ trợ `@WithMockUser` khi TestContext/listeners được cấu hình đúng cho Reactive.

Tài liệu `reactive/test/method` chính thức minh họa:

```java
package com.example.reactiveisolation;

import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

public class AdminReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> report() {
        return Mono.just("admin-only-report");
    }
}
```

```java
package com.example.reactiveisolation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodIsolationConfig {

    @Bean
    AdminReportService adminReportService() {
        return new AdminReportService();
    }
}
```

`@PreAuthorize` nằm trên Spring-managed bean có proxy method security, không phải object tự `new` trong test. Phương thức trả `Mono<String>` để framework dùng Reactor Context.

### 18.2. Ba identities trong ba test methods độc lập

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import reactor.test.StepVerifier;

@SpringJUnitConfig(classes = ReactiveMethodIsolationConfig.class)
class AdminReportServiceTests {

    @Autowired AdminReportService reports;

    @Test
    void anonymousCannotReadAdminReport() {
        StepVerifier.create(reports.report())
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void normalUserCannotReadAdminReport() {
        StepVerifier.create(reports.report())
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadReport() {
        StepVerifier.create(reports.report())
            .expectNext("admin-only-report")
            .verifyComplete();
    }
}
```

Spring Security TestContext support dùng test listeners để đưa authentication vào test method và Reactor Context cho reactive method security. Các tests độc lập về identity; **không tự ghi vào `SecurityContextHolder` static rồi giữ qua method khác**.

### 18.3. `@WithMockUser` không phải production identity lookup

Annotation không xác thực mật khẩu thật, kiểm JWT signature/issuer/audience, hay thực hiện OAuth2 grant. Nếu service đọc custom principal type, test bằng `@WithUserDetails`/`@WithSecurityContext` custom factory hoặc chính mock authentication mà service kỳ vọng. Chỉ test `@PreAuthorize("hasRole('ADMIN')")` không chứng minh toàn auth pipeline.

### 18.4. Tách từng test khi đổi role

Không làm:

```java
// Không khuyến nghị:
SecurityContextHolder.getContext()
    .setAuthentication(adminAuth);
// Sau đó test user/anonymous trong cùng thread mà không cleanup.
```

Trong Reactive code, điều này còn sai về mô hình Context. Với direct publisher tests, dùng `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))`; với HTTP tests, dùng `mutateWith(mockUser(...))`; với annotation tests, để TestContext listeners dọn context theo lifecycle.

## 19. JWT/OAuth2: mock principal riêng nhưng vẫn phải test token thật

### 19.1. `mockJwt()` tạo token giả cho authorization tests

Spring Security Test hỗ trợ `mockJwt()` trong WebFlux:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@Test
void aliceJwtScopeDoesNotGrantAdminAuthority() {
    client.mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .subject("alice")
                .claim("tenant_id", "tenant-A"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read")))
        .get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isForbidden();
}
```

**Đây là fragment dành cho một **API Resource Server chain** có JWT/security rules tương ứng**, không chạy trong fixture HTTP Basic của mục 5. Route `/api/admin/report` phải tồn tại và yêu cầu authority admin; JWT Resource Server dependencies/chain phải được khai báo trong test context. `mockJwt()` tự tạo `JwtAuthenticationToken`, không cần token thật có chữ ký hợp lệ.

### 19.2. Tách identities, claims và authorities

JWT test có thể có cùng `sub` nhưng khác `tenant_id` hoặc authorities. Ví dụ:

```text
JWT A: sub=alice, tenant_id=T1, authorities=[SCOPE_orders:read]
JWT B: sub=alice, tenant_id=T2, authorities=[SCOPE_orders:read]
JWT C: sub=bob,   tenant_id=T1, authorities=[SCOPE_orders:write]
```

Nếu service luôn tra cứu orders bằng username nhưng bỏ qua tenant claim, test A/B có thể lộ dữ liệu xuyên tenant dù principal không đổi. Viết **cross-tenant negative tests** theo domain model; đừng xem `mockJwt().authorities(...)` đơn lẻ là bằng chứng tenant isolation.

### 19.3. `mockJwt()` bypass signature/expiry validation

| Mục tiêu | Nên dùng |
| --- | --- |
| Rule `hasAuthority("SCOPE_orders:read")` | `mockJwt()` với authority phù hợp |
| Service mapping `sub`/`tenant_id` sang owner | `mockJwt()` và negative cross-tenant tests |
| JWT signature sai, `iss`/`aud` sai, `exp` hết hạn | HTTP request với signed token thật và `ReactiveJwtDecoder` được cấu hình |
| OAuth2/OIDC principal/claims trên method/controller | `mockOAuth2Login()`/`mockOidcLogin()` |
| Redirect/login/logout session lifecycle | Authentication thật qua HTTP, cookie jar/IdP test fixture |

`mockJwt()` có thể nhận các claim như `exp` “đã hết” nhưng vẫn được đưa vào SecurityContext vì test helper **không thực thi decoder validation**. Đây không phải lỗi Spring, mà là giới hạn có chủ đích của mock API.

### 19.4. `mockOAuth2Login()`, `mockOidcLogin()` không phải login flow thật

Các mutators OAuth2/OIDC đưa `OAuth2AuthenticationToken`/principal attributes vào mock exchange. Dùng để test controller đọc `@AuthenticationPrincipal` hoặc authorization theo authorities. Không dùng nó để kết luận:

- Authorization code + PKCE được kiểm đúng.
- Callback `state`/`nonce` được validate.
- Refresh token rotation xảy ra.
- Session fixation protection và logout thực thi.

Những assertions phải có integration/E2E với test authorization server và HTTP clients mang state riêng. Không chia sẻ OAuth2 authorized-client repository/token cache giữa test identities nếu mục tiêu là phát hiện tài khoản bị lẫn.

## 20. Chạy test song song không phải lúc nào cũng an toàn

### 20.1. Khi nào **không** bật parallel?

Tài liệu Spring TestContext về parallel execution cảnh báo không nên chạy song song khi tests:

- Dùng `@DirtiesContext`.
- Dùng `@MockitoBean`/`@MockitoSpyBean` hoặc Boot `@MockBean`/`@SpyBean` có shared lifecycle.
- Có `@TestMethodOrder` thiết kế phụ thuộc thứ tự.
- Sửa state shared: database, message broker, filesystem, Redis/cache.
- Có context cache eviction hoặc side effects khiến context khác bị đóng giữa chừng.

Không coi `ConcurrentHashMap`/`CopyOnWriteArrayList` là lý do đủ để parallel mọi test: một `clearForTests()` có thể xóa data của test khác ngay khi đang chạy.

### 20.2. Giới hạn test class về cùng một thread

```java
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@Execution(ExecutionMode.SAME_THREAD)
@SpringJUnitConfig(classes = {
    IsolationWebConfig.class,
    IsolationSecurityConfig.class
})
class SequentialIsolationTests {
    // Các methods trong class không thực thi song song.
}
```

`SAME_THREAD` không bảo đảm **các test classes khác** hoặc **JVM forks khác** không cùng dùng một Redis/DB/store. Đó là lựa chọn giảm race cục bộ, không phải giải pháp isolation toàn CI.

### 20.3. JUnit `@ResourceLock` trong cùng JVM

Nếu một nhóm tests bắt buộc dùng tài nguyên độc quyền:

```java
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock(
    value = "shared-test-redis",
    mode = ResourceAccessMode.READ_WRITE)
class RedisStatefulTests {
    // Các tests tương thích phải cùng dùng khóa resource này.
}
```

Resource lock giúp quản lý concurrency do JUnit Jupiter trong cùng execution engine, **không** khóa một Redis instance cho các Gradle/Maven workers, containers CI khác hoặc ứng dụng bên ngoài. Nếu suite tách nhiều JVM, dùng namespaces/db độc lập hoặc tổ chức một lock/lease có phạm vi thực tế.

### 20.4. Test order không được dùng để mang state

```text
Sai:
  test1_loginAlice
  test2_createOrderAlice
  test3_logoutAlice
  test4_expectAnonymous

Đúng:
  @Test oneCompleteLoginCreateLogoutScenario()
    - create isolated client/session
    - login + bootstrap token
    - POST create order
    - logout
    - assert old session rejected
```

Một **workflow integration** gồm nhiều requests trong **một test** là hợp lý; nhiều test methods dựa vào status/data của nhau là brittle. Khi JUnit reorder/retry/shard suite, mọi assumptions ngầm sẽ vỡ.

### 20.5. CI test retry không được che flaky security tests

Nếu test S1/T1 vs S2/T2 đôi lúc pass/đôi lúc fail, đừng chỉ thêm retry. Cần kiểm:

1. Cookie jar có dùng lại `SESSION` không?
2. Redis session keys shared giữa tests?
3. `@BeforeEach` clear data có trùng lúc request khác xử lý?
4. Reactor async side effect có hoàn thành trước assertion không?
5. Có mock `csrf()` hoặc principal default bị dùng chung?
6. Context có bị `@DirtiesContext` của test khác đóng?

Một test authorization “ngẫu nhiên pass” là dấu hiệu đáng điều tra, không đơn thuần là bất tiện CI.

## 21. Đồng hồ, scheduler, cache TTL và công việc bất đồng bộ

### 21.1. Thời gian thực cũng là state chia sẻ

Những tests về session expiration, HSTS max-age, JWT expiry, cache timeout, CSRF token lifecycle hoặc scheduled logout có thể fail vì **đồng hồ thật** thay đổi. Nếu test dùng `Thread.sleep(1000)` rồi mong token vừa hết hạn, nó phụ thuộc tải CPU, CI host và scheduler.

Mục tiêu là tách:

- **Thời gian ứng dụng:** injected `java.time.Clock` cho logic business/token expiry có thể kiểm soát.
- **Reactor timers:** `Mono.delay`/`Flux.interval` có thể dùng `StepVerifier.withVirtualTime`.
- **Thời gian hệ thống ngoài:** Redis TTL, DB TTL, OAuth2 provider expiry và browser HSTS có đồng hồ/lifecycle riêng; không tự bị thay bởi Reactor virtual time.

### 21.2. Inject `Clock` thay vì gọi `Instant.now()` khắp service

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class FixedClockTestConfig {
    @Bean
    Clock clock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC);
    }
}
```

Service nên nhận `Clock` qua constructor và dùng `Instant.now(clock)`. Không ghi đè một **static mutable clock toàn suite** để điều khiển thời gian cho các ca khác nhau; tạo clock per test/context hoặc thử logic thuần Java với một object local.

### 21.3. Reactor virtual time áp cho publisher timer

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void reactorDelayDoesNotNeedRealSleep() {
    StepVerifier.withVirtualTime(() ->
            Mono.delay(Duration.ofHours(1))
                .map(ignored -> "expired"))
        .expectSubscription()
        .thenAwait(Duration.ofHours(1))
        .expectNext("expired")
        .verifyComplete();
}
```

Phải **tạo publisher trong Supplier của `withVirtualTime`** khi cần scheduler ảo; nếu publisher/timer đã capture scheduler ngoài, test có thể vẫn dùng thời gian thực.

Đoạn test này **không** kiểm Redis TTL, Spring Session store expiration hoặc browser HSTS memory. Các hệ thống ấy cần fake clock/test store phù hợp hoặc time-controlled staging, không giả định virtual scheduler áp lên mọi external service.

### 21.4. Đợi mọi side effect hoàn thành trước khi teardown

Một reactive service:

```java
return repository.save(order)
    .then(auditGateway.publishEvent(event))
    .thenReturn(order.id());
```

cho phép test subscribe/await cả hai bước theo sequence. Ngược lại:

```java
repository.save(order).subscribe();
return Mono.just(order.id());
```

tạo fire-and-forget publisher; test có thể kết thúc, cleanup rows, rồi publisher bất đồng bộ vẫn ghi dữ liệu trở lại. Đây là nguyên nhân điển hình của test contamination. Không dùng `Thread.sleep` để che race; sửa composition/ownership của publisher.

## 22. Live HTTP: mock identities không đi qua TCP

### 22.1. `@SpringBootTest(RANDOM_PORT)` cần credentials thật

`@WithMockUser` trên thread chạy JUnit hay `WebTestClient.mutateWith(mockUser())` cho mock exchange **không gửi authentication qua TCP**. Để kiểm tra HTTP Basic chính xác, request phải có header Basic.

Ví dụ với Spring Boot test application đã chứa `IsolationController`/`IsolationSecurityConfig`/`IsolationWebConfig` (hoặc beans tương đương):

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LiveHttpIdentityIsolationTest {

    @Autowired WebTestClient http;

    @Test
    void credentialsBelongToThisRequestOnly() {
        http.get().uri("/private/whoami")
            .headers(h -> h.setBasicAuth(
                "alice", "fixture-only"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");

        http.get().uri("/private/whoami")
            .headers(h -> h.setBasicAuth(
                "bob", "fixture-only"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("bob");

        http.get().uri("/private/whoami")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

`@AutoConfigureWebTestClient` import trên dùng **Boot 3.5**; Boot 4 thay bằng `org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient`. Đừng dùng password fixture trong production hoặc đặt credentials thật vào CI log.

### 22.2. HTTP client có cookie jar cần cách ly theo “browser”

Đối với form login/sessions, mô hình đúng:

```text
Browser A client/context/cookie jar:
  GET /login -> POST login Alice -> SESSION=S1

Browser B client/context/cookie jar:
  GET /login -> POST login Bob   -> SESSION=S2

Anonymous C:
  Không có Authorization, không có SESSION cookie
```

Với một WebTestClient được tùy biến `defaultCookie("SESSION", S1)`, request của Bob hoặc anonymous có thể đang gửi **session của Alice** dù đang cố set mock principal khác. Vì vậy test HTTP live nên sử dụng client/browser contexts độc lập và kiểm tra:

1. Cookie SESSION của hai clients khác nhau khi login/session strategy yêu cầu.
2. A không đọc resource B dù biết resource ID.
3. B không logout session A ngoài ý muốn.
4. Old-cookie replay sau logout không authenticated theo policy.
5. CSRF token/cookie thuộc session phù hợp.

### 22.3. Signed JWT phải được kiểm riêng

Một live Resource Server test dùng Bearer token thật từ test issuer hoặc ký bằng test private key, gửi:

```java
http.get().uri("/api/orders")
    .headers(h -> h.setBearerAuth(signedTokenForAlice))
    .exchange()
    .expectStatus().isOk();
```

`signedTokenForAlice` là **test-generated JWT** với `iss`/`aud`/`exp` và signature phù hợp decoder của test app, không phải string bất kỳ. Negative cases gồm token Alice dùng sai tenant, signature bị sửa, issuer không tin, token hết hạn và scope thiếu.

Test `mockJwt()` không xác nhận những negative decoder cases; live tests mới đi qua logic xác thực của server.

### 22.4. Test cookies trong browser cần môi trường HTTPS thật

`WebTestClient` có thể gửi cookie `Secure` trong mock HTTP request nếu bạn cấu hình thủ công, trong khi browser thực có thể không gửi nó trên HTTP. Browser E2E kiểm:

- `HttpOnly` session cookie không đọc được bằng JavaScript.
- `Secure` yêu cầu HTTPS.
- `SameSite` phù hợp same-site/cross-site navigation và API fetch.
- Cookie `Path`/`Domain` match URL public sau proxy rewrite.
- CSP `connect-src` và CORS cho SPA fetch hoạt động, không bị chặn trước backend.
- HSTS/CSP trên đúng HTML/public HTTPS owner.

Không gộp browser cookie rules với việc `mockUser()` pass; đó là hai lớp kiểm chứng khác nhau.

## 23. Nhiều `SecurityWebFilterChain` không được gây rò chính sách

### 23.1. Một context có thể có nhiều chains theo path

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        // Chỉ miễn CSRF nếu API thực sự Bearer-only.
        .csrf(csrf -> csrf.disable())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain browser(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/public/**", "/login").permitAll()
            .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .csrf(Customizer.withDefaults())
        .build();
}
```

Đây là **biến thể thay thế** `IsolationSecurityConfig` một chain, không nạp song song trong cùng fixture không có chủ đích. Resource Server cần dependency/`ReactiveJwtDecoder` thực hoặc phù hợp test support.

### 23.2. Rule isolation cần test cả URL sát đường biên matcher

| Request | Chain dự kiến | Isolation assertion |
| --- | --- | --- |
| `GET /api/orders` anonymous | API Bearer | 401, không redirect HTML login |
| `GET /api/orders` signed JWT Alice | API Bearer | Dữ liệu đúng Alice/tenant |
| `GET /api/orders` JWT Bob | API Bearer | Không thấy dữ liệu Alice |
| `GET /private/whoami` anonymous | Browser | Redirect login nếu form login |
| `POST /private/orders` session auth, thiếu CSRF | Browser | 403, không side effect |
| `GET /api-v2/orders` | Không match `/api/**` | Phải review fallback, không cho bypass |
| `OPTIONS /api/orders` có preflight | Global/chain CORS | Không cần cookie auth cho preflight |

Nếu API matcher vô tình đổi thành `/**`, browser routes có thể bị đưa vào Bearer-only chain với CSRF disabled; test browser POST không token sẽ phát hiện regression. Nếu `/api-v2/**` lọt sang browser fallback, API có thể trả 302 `/login` thay 401, và frontend bị CORS/HTML redirect bất ngờ.

### 23.3. Profile configs phải gắn với đúng test class

Không dùng cùng static `SecurityWebFilterChain` và thay flags giữa tests. Với form login, Bearer-only hoặc CORS variants, khai báo **separate test classes/configuration keys** hoặc một application context có chains đúng matcher và chỉ sửa request inputs. Không gọi `http.build()` lại tùy tiện trên shared `ServerHttpSecurity` bean trong mỗi `@Test` để thay policy runtime.

### 23.4. CORS và security headers cũng là cấu hình dùng chung

Một `CorsConfigurationSource`/`HttpHeaderWriter` singleton mutable bị sửa trong test có thể khiến test sau thấy origin lạ được chấp nhận hoặc CSP bị nới:

```text
Test A: mutate allowedOrigins -> ["https://attacker.test"]
Test B: test CORS default -> bất ngờ attacker Origin được chấp nhận
```

Tốt hơn tạo chính sách immutable qua config riêng, test contexts khác nhau và request-level positive/negative controls. Đừng sửa danh sách live CORS config trong một test rồi trông chờ `@AfterEach` khôi phục an toàn dưới parallel execution.

## 24. Runbook: 22 lỗi isolation hay gặp trong Reactive tests

### Lỗi A — Một test pass riêng, fail khi chạy sau một test tạo order

**Nghi vấn:** singleton `InMemoryOrders`/repository dùng chung, DB rows chưa cleanup, hoặc Reactor publisher trước đó ghi muộn.

**Xác minh:** ghi assert baseline trước test; dùng per-test namespace; đợi mọi publisher hoàn tất; kiểm tra context cache reuse. Không sửa bằng `@TestMethodOrder` để ép test “đúng thứ tự”.

### Lỗi B — Anonymous request bất ngờ được xem là Alice

**Nghi vấn:** `WebTestClient` bị mutate thành client Alice và tái sử dụng, `defaultHeader Authorization` hoặc `defaultCookie SESSION` còn sót, class-level `@WithMockUser` đang áp mọi test, hoặc server-side cookie jar dùng chung.

**Xác minh:** chạy sequence Alice → anonymous trên **base client mới**; inspect default headers/cookies; dùng `@WithAnonymousUser` khi class-level annotation là chủ đích; test live HTTP không credentials phải 401/302 theo chain.

### Lỗi C — USER có quyền ADMIN sau test trước đó

**Nghi vấn:** static `Authentication`, mutable shared authentication object, mock principal default, hoặc test chỉ kiểm ADMIN positive.

**Xác minh:** cùng test có ADMIN 200, USER 403, anonymous 401/redirect. Đọc authentication từ Reactor Context/request thay vì static/ThreadLocal.

### Lỗi D — `@WithMockUser` không có tác dụng khi gọi server thật

**Giải thích:** annotation/mutator thiết lập mock context ở test client, không gửi credentials qua TCP tới thread/server. Với `RANDOM_PORT`, dùng HTTP Basic, Bearer thật hoặc form session cookie.

### Lỗi E — `mockJwt()` chấp nhận token hết hạn trong test

**Giải thích:** `mockJwt()` tạo `JwtAuthenticationToken` giả để test authorization, không chạy `ReactiveJwtDecoder` signature/expiry/issuer validation.

**Xác minh:** tách mock authorization tests khỏi HTTP decoder tests với signed/expired/tampered JWT thật trong test issuer.

### Lỗi F — Bob thấy đơn của Alice dù mock principal đúng

**Nghi vấn:** repository query lọc sai `owner`/`tenant_id`, controller dùng static currentUser hoặc cache key không chứa tenant, hay data có sẵn từ test trước.

**Xác minh:** tạo order Alice; query Bob phải rỗng; thử Bob truy cập ID trực tiếp và assert 403/404 theo policy; test cross-tenant cùng `sub` khác claim tenant.

### Lỗi G — POST thiếu CSRF vẫn thành công

**Nghi vấn:** test client dùng chung đã gắn `csrf()`, browser chain CSRF bị disable hoặc sai securityMatcher.

**Xác minh:** POST với principal nhưng **không** `csrf()` nhận 403 và không side effect; sau đó positive POST với `csrf()` hoặc actual token/cookie hợp lệ. Không dùng một mock helper để test repository lifecycle.

### Lỗi H — S1/T1 dùng với S2 vẫn pass trong test WebSession repo

**Nghi vấn:** hai bootstrap requests có cùng cookie jar/S1, test helper `csrf()` đã bypass, selected chain sai hoặc repository thực không phải WebSession.

**Xác minh:** S1/S2 session IDs khác; POST S2/T1 bị từ chối, POST S2/T2 pass; kiểm tra raw-vs-XOR handler và repo variant.

### Lỗi I — Reset store trong `@BeforeEach` nhưng vẫn flaky dưới parallel

**Nguyên nhân:** test A đang xử lý trong Reactor và test B gọi `clearForTests()` giữa chừng. Thread-safe map không bảo vệ tính độc lập của dữ liệu.

**Xử lý:** chạy tuần tự suite shared-state hoặc chuyển sang per-test namespace/containers. Không chỉ thay `HashMap` thành `ConcurrentHashMap` rồi kết luận đã hết race.

### Lỗi J — Test DB có row còn lại sau rollback

**Nguyên nhân:** test-managed JDBC `@Transactional` không bao trùm R2DBC request chạy trong server/transaction khác, hoặc event được ghi ngoài transaction.

**Xử lý:** dedicated test DB, namespace/cleanup đúng scope, test `TransactionalOperator` ở service boundary, xác minh commit/rollback và external side effects độc lập.

### Lỗi K — Đổi `System.setProperty` nhưng Security behavior không đổi

**Nguyên nhân:** `SecurityWebFilterChain`/`CorsConfiguration` đã được tạo khi context khởi động. Environment property mutable không nhất thiết rebind beans tự động.

**Xử lý:** dùng `@TestPropertySource`/`@ActiveProfiles` theo class/context, test request behavior; không mutate JVM global property giữa methods.

### Lỗi L — Container đã đổi port nhưng context vẫn kết nối port cũ

**Nguyên nhân:** cached Spring context chứa R2DBC/Redis connection settings từ `@DynamicPropertySource` trước đó, container bị stop/restart hoặc subclass dùng dynamic properties khác.

**Xử lý:** align container lifecycle với context, tránh đổi suppliers giữa subclasses; cân nhắc `@DirtiesContext` khi dynamic values khác bắt buộc theo Spring reference.

### Lỗi M — `@DirtiesContext` không xóa dữ liệu Redis/Kafka

**Giải thích:** annotation chỉ đóng/evict Spring `ApplicationContext`. External services vẫn giữ state.

**Xử lý:** cleanup theo test-owned resource, namespace/topic/schema riêng hoặc container riêng; không `FLUSHALL` trên shared Redis.

### Lỗi N — Test service mất principal sau `publishOn`

**Nguyên nhân:** service dùng `SecurityContextHolder` ThreadLocal hoặc tự tách publisher thành `subscribe()`/CompletableFuture mà không thiết kế context propagation.

**Xử lý:** `ReactiveSecurityContextHolder.getContext()` trong reactive pipeline; dùng `contextWrite(withAuthentication(...))` ở unit tests và verify qua scheduler hop.

### Lỗi O — Service log audit chạy sau khi test đã cleanup

**Nguyên nhân:** fire-and-forget `subscribe()`, test dùng sleep tùy ý hoặc mock/Redis teardown trước khi publisher hoàn thành.

**Xử lý:** compose `Mono`/`Flux` và await bằng `StepVerifier`/terminal operator trong JUnit; với external queues, đợi acknowledgment và cleanup theo namespace.

### Lỗi P — Tests mock dùng chung một `@MockitoBean` có invocation history bất ngờ

**Nguyên nhân:** mock lifecycle/reset mode không như test giả định, hoặc test song song cùng gọi một mock.

**Xử lý:** kiểm tra Spring Framework/Boot version và mock reset strategy; dùng local mocks/isolated context khi cần, tránh parallel tests shared mock.

### Lỗi Q — Timeout/session-expiration test xanh nhưng production không hết hạn

**Nguyên nhân:** `StepVerifier.withVirtualTime` chỉ kiểm soát Reactor schedulers phù hợp, không chi phối Redis TTL/DB expiry hoặc browser HSTS clock.

**Xử lý:** test logic với injected `Clock`, Redis/session expiration với test store/TTL thật, browser behavior với HTTPS staging.

### Lỗi R — TestContext báo “context no longer active” khi parallel

**Nguyên nhân:** context cache bị `@DirtiesContext`/LRU eviction trong luồng khác, hoặc quá nhiều cache keys khác nhau khiến context đóng bất ngờ.

**Xử lý:** xem `org.springframework.test.context.cache=DEBUG`; giảm `@DirtiesContext`/context variants; tắt parallel với các class không phù hợp theo Spring guidelines.

### Lỗi S — `@WebFluxTest` pass nhưng full app dùng chain khác

**Nguyên nhân:** slice chưa import custom `SecurityWebFilterChain`/CorsWebFilter/CSRF repository, hoặc bean override đã thay test wiring.

**Xử lý:** assert chain behavior trên mock context đầy đủ và `@SpringBootTest`; thêm test HTTP live cho auth/cookie flows; không mock mọi security filters.

### Lỗi T — Anonymous API trả 302 thay vì 401

**Nguyên nhân:** API path không match Bearer chain, rơi vào browser form-login fallback, hoặc test profile config sai.

**Xử lý:** test `/api/**`/`/api-v2/**` với request anonymous, xác nhận selected chain; Bearer-only API trả 401/`WWW-Authenticate`, browser route 302 khi đã cấu hình form-login.

### Lỗi U — CORS preflight đôi lúc 401 sau khi test khác sửa allowlist

**Nguyên nhân:** `CorsConfiguration` singleton mutable bị test khác chỉnh, filter order/profile khác, gateway sở hữu CORS trong một env nhưng không trong env khác.

**Xử lý:** policy immutable/per-context; OPTIONS + Origin + Access-Control-Request-Method positive/negative controls; không chia sẻ mutable CORS config. Preflight thường không mang auth cookie.

### Lỗi V — Browser E2E có cookie Alice trong context của Bob

**Nguyên nhân:** Playwright/Selenium tests dùng chung browser context/storage state hoặc cookie jar profile, hoặc frontend tự cache Authorization trong local storage shared.

**Xử lý:** mỗi identity dùng browser context/incognito profile/storage riêng, reset service worker/local/session storage theo test ownership và logout/invalidate sessions. Test UI và API phải xác minh data access chứ không chỉ hiển thị tên user.

## 25. Ma trận regression cho các ranh giới cô lập

| ID | Ca thử | Kỳ vọng |
| --- | --- | --- |
| I01 | Alice `GET /private/whoami` | 200, body Alice |
| I02 | Alice xong, anonymous cùng baseline | 401/redirect theo chain, không còn Alice |
| I03 | Bob `GET /private/whoami` | 200, body Bob |
| I04 | ADMIN `GET /admin/count` | 200 |
| I05 | USER `GET /admin/count` | 403 |
| I06 | Anonymous `GET /admin/count` | 401/redirect |
| I07 | Alice POST hợp lệ + mock CSRF | 201, owner Alice |
| I08 | Bob list sau I07 trong cùng test | Không thấy data Alice |
| I09 | Bob truy cập ID resource Alice | 403/404 theo domain policy |
| I10 | Alice POST thiếu CSRF | 403, zero side effect |
| I11 | Client có default Authorization Alice | Chỉ request của client ấy có auth |
| I12 | Baseline client sau mutated client | Không có default auth/cookie |
| I13 | WebSession S1/T1 positive | Được chấp nhận |
| I14 | WebSession S2/T1 negative | 403 |
| I15 | WebSession S2/T2 positive | Được chấp nhận |
| I16 | Old session/token sau invalidate/logout | Không được dùng trái policy |
| I17 | Cookie CSRF repo raw/header | Đúng theo configured request handler |
| I18 | Reactive Context Alice subscription | Alice |
| I19 | Cùng publisher với Bob subscription | Bob, không Alice |
| I20 | Không có Reactor auth context | Anonymous/default |
| I21 | `publishOn` với Reactor context | Vẫn đúng principal |
| I22 | `@WithMockUser(USER)` method security | 403/AccessDenied |
| I23 | `@WithMockUser(ADMIN)` method security | Pass |
| I24 | JWT mock với wrong scope | 403 |
| I25 | JWT mock với wrong tenant | Không đọc cross-tenant data |
| I26 | Live JWT signature/issuer/expiry invalid | 401 theo decoder |
| I27 | Profile strict vs compatibility | Cấu hình/response theo context riêng |
| I28 | `@TestPropertySource` khác nhau | Environment keys tách đúng |
| I29 | `@DynamicPropertySource` container port | URL đúng container còn sống |
| I30 | Cached context singleton data | Có reset/namespace trước mỗi test |
| I31 | Mock override stubbing/history | Không ảnh hưởng ca sau |
| I32 | R2DBC cleanup scoped by testRun | Không xóa dữ liệu test khác |
| I33 | Redis keys/sessions per test | Không lẫn keys hoặc cookie jars |
| I34 | Reactor virtual time | Timer test không ngủ thời gian thực |
| I35 | Redis TTL expiry thật | Không suy từ virtual time |
| I36 | Parallel tests với shared store | Không chạy song song hoặc có namespace |
| I37 | Context cache eviction/DirtiesContext | Không đóng context đang dùng |
| I38 | Browser contexts Alice/Bob | Cookies/storage tách biệt |
| I39 | Multi-chain API `/api/**` | Bearer policy, không form-login fallback |
| I40 | Multi-chain browser `/private/**` | Session/CSRF policy còn bảo vệ |
| I41 | CORS preflight không cookie | Policy quyết định trước authentication |
| I42 | CSP/HSTS ở public HTML/HTTPS owner | Headers đúng, không rò policy test |

### 25.1. Bộ assertions tối thiểu cho mỗi security-sensitive endpoint

Không chỉ test “người có quyền thành công”. Đối với một endpoint, nên có:

1. **Positive identity**: owner/user hợp lệ được quyền.
2. **Negative identity**: user khác không được đọc/ghi dữ liệu.
3. **Negative authority**: user thiếu role/scope bị từ chối.
4. **Anonymous**: không có auth thì 401/redirect theo chain.
5. **CSRF**: nếu cookie-backed browser state-changing request, thiếu token bị 403; có token đúng được tiếp tục.
6. **Data side effect**: request bị từ chối không tạo/sửa dữ liệu.
7. **Configuration**: policy/chain expected được nạp, không bị test profile khác nới lỏng.
8. **Repeatability**: chạy test một mình, toàn suite, đảo thứ tự/shard và parallel khi phù hợp cho cùng kết quả.

### 25.2. Tại sao không cần mọi hàng trong mọi test class?

Một unit Reactor Context không cần start Redis; một `@WebFluxTest` authorization không nên ép kiểm HSTS TLS public; một end-to-end browser test không kiểm tất cả JWT signature edge cases bằng mock token. **Chọn lớp test đúng threat model**, nhưng bao phủ đủ các ranh giới để tránh lỗ hổng do mỗi suite chỉ giả lập nơi khác đã kiểm.

## 26. Bài tập thực hành

### Bài 1 — Tái hiện test contamination từ singleton bean

Dựng fixture `IsolationWebConfig`/`IsolationSecurityConfig`/`IsolationController`. Tạo một test POST order Alice và một test kỳ vọng store rỗng. Bỏ `orders.clearForTests()`, chạy từng method riêng và cả suite, nhận diện kết quả phụ thuộc thứ tự. Khôi phục reset hoặc per-test namespace; giải thích vì sao test instance mới không tạo singleton bean mới khi context cached.

### Bài 2 — Principal tách biệt ở cùng một WebTestClient baseline

Viết một `@Test` gọi GET `/private/whoami` theo thứ tự Alice → anonymous → Bob → anonymous, sử dụng `base.mutateWith(mockUser(...))` chỉ với request cần auth. Kiểm response đúng từng principal. Sau đó cố tình đổi `base = base.mutateWith(mockUser("alice"))` và quan sát test anonymous bị ảnh hưởng như thế nào.

### Bài 3 — Role isolation

Gọi `GET /admin/count` bằng ADMIN, USER, anonymous. Assert tương ứng 200, 403, 401 (với HTTP Basic fixture), rồi thử đổi chain sang form login để hiểu vì sao anonymous có thể 302. Không sửa expected chỉ để xanh mà bỏ qua loại authentication entry point.

### Bài 4 — Tách dữ liệu Alice/Bob

Alice POST order `BOOK-01` với CSRF hợp lệ; Bob GET list phải rỗng. Thêm endpoint `GET /private/orders/{id}` chỉ chủ sở hữu được xem, thử Bob dùng trực tiếp ID của Alice và assert 403/404 theo policy. Vì sao lọc list theo principal chưa đủ chống IDOR?

### Bài 5 — Không để `csrf()` từ ca trước che mất lỗi

Trong một test, tạo local client `aliceWithCsrf` và baseline client `aliceNoCsrf`. POST cùng payload: một request 201, request còn lại 403; kiểm totalCount chỉ tăng một lần. Không mutate field `base` thành client đã có `csrf()`.

### Bài 6 — Hai WebSessions và actual token round-trip

Bổ sung `GET /public/csrf` vào controller variant, sử dụng WebSession repository. Bootstrap S1/T1 và S2/T2 bằng hai cookie jars độc lập, thử S2/T1 bị chặn, S2/T2 được phép. Sau khi logout/invalidate S1, replay token cũ không được xử lý. Không dùng `mutateWith(csrf())` trong actual-token suite.

### Bài 7 — Ranh giới raw cookie vs XOR

Thay WebSession repo bằng `CookieServerCsrfTokenRepository` trong test context riêng. Phân biệt raw `XSRF-TOKEN` cookie với exposed masked token và `ServerCsrfTokenRequestHandler`. Viết test thiếu header/sai header/đúng header, không gán sai contract server-side WebSession binding cho cookie repo.

### Bài 8 — Context cache với hai `@TestPropertySource`

Viết hai classes có `app.security.mode=strict` và `compatibility`, assert Environment mỗi class; bổ sung custom Security config thật sự đọc mode, rồi kiểm HTTP behavior khác nhau. Bật cache DEBUG để thấy context hit/miss. Không dùng `System.setProperty` giữa methods.

### Bài 9 — Dynamic container property và R2DBC

Khởi tạo một dedicated PostgreSQL Testcontainer, đăng ký `spring.r2dbc.url`/credentials bằng `@DynamicPropertySource`. Chạy tests với hai `testRun` UUID khác nhau, cleanup chỉ rows của run mình. Cố tình đóng container trước khi cached context hoàn thành và mô tả vì sao connection pool vẫn trỏ tới old port.

### Bài 10 — Reactive authentication trong hai subscriptions

Sử dụng cùng `Mono<String> whoami` đọc `ReactiveSecurityContextHolder.getContext()`. Một subscription dùng Alice, một dùng Bob, một anonymous; kiểm kết quả tương ứng. Thêm `publishOn(Schedulers.parallel())`. Vì sao một static `Authentication` field là sai ngay cả khi test chạy tuần tự?

### Bài 11 — Method security với `@WithMockUser`

Viết `AdminReportService` có `@PreAuthorize("hasRole('ADMIN')")` và `@EnableReactiveMethodSecurity`. Test anonymous/USER bị denied, ADMIN pass với `StepVerifier`. Thêm test với custom principal hoặc `@WithUserDetails` nếu service phụ thuộc loại principal riêng. Không dùng `@WithMockUser` để chứng minh JWT signature verification.

### Bài 12 — JWT scope, issuer và tenant

Dùng `mockJwt()` để test SCOPE reader vs writer và claim `tenant_id`. Sau đó dùng `RANDOM_PORT` và test issuer/decoder thật để gửi JWT đúng chữ ký, chữ ký sai, issuer sai và token hết hạn. Giải thích vì sao một mock JWT có claim `exp` cũ vẫn có thể pass mock test.

### Bài 13 — Parallel test race

Cho hai tests cùng sử dụng `InMemoryOrders` singleton và mỗi `@BeforeEach` gọi `clearForTests()`. Bật parallel JUnit trong **dedicated test branch** và tái hiện race (nếu có). Sửa bằng namespace/case-owned keys hoặc `@Execution(SAME_THREAD)` khi suite thực sự dùng resource độc quyền. Nêu rõ SAME_THREAD không khóa Redis cho JVM khác.

### Bài 14 — Virtual time không thay Redis TTL

Viết `StepVerifier.withVirtualTime` cho `Mono.delay(Duration.ofHours(1))`. Sau đó thử session Redis TTL thật trong một dedicated Redis test container và so sánh: virtual time của Reactor có làm Redis key expire ngay không? Thiết kế test session timeout phù hợp thay vì `Thread.sleep` tùy ý.

### Bài 15 — Browser contexts độc lập

Trong staging HTTPS, tạo hai browser contexts A/B với storage tách biệt. Login Alice/Bob bằng credentials test, POST với CSRF token đúng, thử GET order người khác theo direct resource ID, logout A rồi kiểm B không bị ảnh hưởng. Quan sát cookie `Secure/SameSite/HttpOnly`/CORS/CSP và redaction artifacts.

### Bài 16 — API chain và browser fallback

Tạo `/api/**` Bearer-only chain và browser form-login fallback. Kiểm anonymous API 401, browser 302, browser POST thiếu CSRF 403, request `/api-v2/**` không lọt sai chain. Đánh giá rủi ro nếu API matcher bị đổi thành `/**`.

### Bài 17 — CI sharding và trạng thái shared

Chạy cùng suite trên hai Gradle workers/JVM forks trỏ đến một Redis/container. Thiết kế `runId` + `testId` key prefix và cleanup scope, hoặc mỗi worker một Redis instance. Đo context cache hits và tài nguyên còn tồn sau suite; chứng minh không còn stale sessions/rows/queued events.

## 27. Checklist trước khi đưa bộ Reactive Security tests vào CI

- [ ] Mỗi test có **baseline rõ ràng**, không dựa vào kết quả/test data của method trước.
- [ ] Biết `ApplicationContext` có thể được cache và chia sẻ singleton beans giữa test classes.
- [ ] Có phương án cô lập dữ liệu của singleton fixture: reset **tuần tự** hoặc per-test namespace.
- [ ] Không giữ principal, CSRF token, session cookie hay client auth mặc định trong static fields.
- [ ] `WebTestClient` baseline không mang Authorization/cookie/CSRF test mutators.
- [ ] `mockUser()`/`mockJwt()` chỉ gắn vào test request/local client cần thiết.
- [ ] Anonymous negative control chạy sau authenticated requests và vẫn bị từ chối.
- [ ] Có tests ADMIN/USER/anonymous và role/scope khác nhau.
- [ ] Tenant/owner filtering được test cả list lẫn direct resource ID.
- [ ] Side effect count/rows/events bằng 0 khi CSRF hoặc authorization từ chối.
- [ ] Phân biệt mock `csrf()` success với actual WebSession/cookie/CSRF token round-trip.
- [ ] S1/T1 và S2/T2 thực sự dùng khác session IDs/cookie jars khi test WebSession repo.
- [ ] Không gán token session-binding invariant cho Cookie CSRF repository mặc định.
- [ ] Không đọc `Authentication` từ một static field hoặc ThreadLocal trong Reactive pipeline.
- [ ] Direct reactive publisher tests dùng `ReactiveSecurityContextHolder`/`contextWrite`/`StepVerifier`.
- [ ] Method security tests có `@EnableReactiveMethodSecurity` và test annotations/listeners phù hợp.
- [ ] `@WithMockUser` ở class-level không vô tình áp vào anonymous tests.
- [ ] `mockJwt()`/`mockOAuth2Login()` không được dùng để kết luận signature, expiry hay OAuth2 grant flow thật.
- [ ] HTTP server live tests gửi credentials/cookies/tokens qua request thực, không chỉ mock context.
- [ ] `@TestPropertySource`/`@ActiveProfiles` dùng theo test class/context, không mutate System properties theo method.
- [ ] Khi test config khác nhau, Security/CORS/Header beans **thực sự đọc** properties và được test behavior.
- [ ] `@DynamicPropertySource` suppliers khớp container lifecycle và giá trị test hiện hành.
- [ ] `@DirtiesContext` chỉ dùng khi context thật sự dirty; không dùng nó thay external data cleanup.
- [ ] Bean overrides (`@MockitoBean`/`@MockBean`) được quản lý reset/lifecycle đúng version.
- [ ] Không chạy parallel tests share state/`@DirtiesContext`/mock bean nếu không có bảo vệ phù hợp.
- [ ] JUnit resource lock được hiểu là **trong JVM/execution engine**, không áp CI forks khác.
- [ ] R2DBC external HTTP writes không bị mặc định coi là rollback bởi JUnit `@Transactional`.
- [ ] Data cleanup chỉ xóa test-owned DB rows/Redis keys; không đụng production/dev shared DB.
- [ ] Không dùng Redis `FLUSHALL` hoặc truncate toàn DB không được dành riêng cho suite.
- [ ] Mọi asynchronous publisher/cleanup đều được await trước khi test hoàn thành.
- [ ] Không fire-and-forget `subscribe()` trong handler chỉ để test qua.
- [ ] `Clock`/Reactor virtual time dùng đúng scope; không coi nó là Redis/browser/system clock.
- [ ] Browser contexts/cookie jars/storages Alice/Bob/anonymous tách biệt.
- [ ] CORS origin/method/header policy không bị mutate bởi một test khác.
- [ ] CSP/HSTS và Security headers được test trên đúng HTML/public HTTPS owner.
- [ ] Multi-chain path matcher có tests boundary API vs browser; CSRF browser không bị nới khi API đổi.
- [ ] Suite pass khi chạy từng test, chạy toàn bộ, lặp lại, đảo thứ tự/shard và parallel **nếu được thiết kế cho parallel**.
- [ ] Logs/CI artifacts không ghi raw session IDs, CSRF tokens, JWTs, passwords hoặc secrets.

## 28. Tài liệu tham khảo chính thức

1. [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — `bindToApplicationContext`, `apply(springSecurity())`, security mock configurers.
2. [Spring Security — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html) — `@WithMockUser`, `mockUser()`, authentication test scope.
3. [Spring Security — Reactive Testing OAuth2/JWT](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html) — `mockJwt`, OAuth2/OIDC test support và test authorization không verify JWT signature.
4. [Spring Security — Reactive Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — `csrf()` mock helper và phạm vi sử dụng.
5. [Spring Security — Reactive Method Security Tests](https://docs.spring.io/spring-security/reference/reactive/test/method.html) — `@WithMockUser`/`StepVerifier` cho `@PreAuthorize` reactive service.
6. [Spring Security — Enable Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html) — Reactor `Context` và `ReactiveSecurityContextHolder`.
7. [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html) — `getContext`, `withAuthentication`, `clearContext`.
8. [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html) — `mockUser`, `mockJwt`, `mockOAuth2Login`, `csrf`.
9. [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — WebSession vs cookie repository, token handler và session lifecycle.
10. [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, chain matchers, multi-chain.
11. [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html) — context cache key, LRU, `@DirtiesContext` và hit/miss logging.
12. [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html) — khi nào evict/rebuild context.
13. [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html) — `@TestPropertySource` và property precedence.
14. [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html) — `@DynamicPropertySource`, container properties và subclass caching.
15. [Spring Framework — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html) — shared state, `@DirtiesContext`, mock bean và concurrency cautions.
16. [Spring Framework — Transaction Management for Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html) — test-managed transactions và rollback boundaries.
17. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — mock/live clients, response assertions và test scope.
18. [Spring Framework — Mockito Bean Overrides](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html) — Spring 6.2+ bean overriding and lifecycle.
19. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@WebFluxTest`, `@SpringBootTest`, profiles/test infrastructure, version-specific annotations.
20. [Testcontainers — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/) — test containers lifecycle, `@Container` và resource isolation.
21. [Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — `StepVerifier`, virtual time và deterministic reactive tests.
22. [JUnit Jupiter — Parallel Execution](https://docs.junit.org/current/user-guide/#writing-tests-parallel-execution) — `@Execution`, `@ResourceLock` và lifecycle.
23. [OWASP — Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — CSRF token/session requirements.
24. [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — deny by default, object-level/tenant authorization, test negative paths.

**Câu hỏi tự đánh giá:** Vì sao JUnit tạo một object test mới nhưng một singleton Spring vẫn có data từ test trước? Khi nào nên `@DirtiesContext` thay vì reset store? Một `WebTestClient` gắn `mockUser("alice")` có ảnh hưởng baseline client hay không nếu bạn thay biến shared? Vì sao anonymous test cần chạy ngay sau authenticated request? `@WithMockUser` khác login/JWT signature validation thật thế nào? Vì sao `mockJwt()` không chứng minh issuer/expiry? Một `Mono` đọc `ReactiveSecurityContextHolder` nhận Alice ở subscription đầu nhưng Bob ở subscription tiếp theo cần bảo đảm điều gì? Tại sao `@Transactional` trên JUnit test không tự rollback R2DBC write của HTTP server riêng? `@DynamicPropertySource` và context cache có thể chỉ vào container port cũ khi nào? Vì sao virtual time không làm Redis TTL hết hạn? Và nếu một bài test security chỉ fail khi chạy song song, bạn sẽ xác định rò config, data, identity, cookie hay async side effects theo thứ tự nào?
