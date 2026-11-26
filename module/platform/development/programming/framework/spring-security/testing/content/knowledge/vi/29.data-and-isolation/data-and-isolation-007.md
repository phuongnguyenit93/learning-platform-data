# Không chia sẻ Authentication hoặc principal khả biến giữa các test

Trong một bộ kiểm thử Spring Security, việc tất cả các ca đều dùng tên `alice` không có gì sai. Điều nguy hiểm là các ca lại **dùng chung chính một đối tượng `Authentication`, `SecurityContext` hoặc principal có thể thay đổi**. Một test thêm quyền cho Alice, test khác đọc lại cùng object và vô tình thấy quyền mới; nếu test chạy song song, sự thay đổi còn có thể xảy ra ngay giữa lúc kiểm tra phân quyền. Kết quả là test xanh sai nguyên nhân, test đỏ tùy thứ tự chạy, hoặc một lỗ hổng leo thang quyền bị che khuất.

Trong chương **Dữ liệu và cô lập** của **SPRING_SECURITY_TESTING**, bài học giải thích cách tạo dữ liệu danh tính độc lập cho kiểm thử xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test`. Chúng ta sẽ làm việc với `SecurityContextHolder`, `@WithMockUser`, `MockMvc`, `WebTestClient`, `mockJwt()` và các trường hợp có OAuth2/OIDC principal; đồng thời kiểm tra những ca được phép và bị từ chối trên cả Servlet và Reactive.

Mục tiêu không phải thay mọi principal thành kiểu bất biến trong ứng dụng sản xuất. Mục tiêu kiểm thử là **mỗi ca có trạng thái bảo mật do chính nó tạo ra, không phụ thuộc việc một ca khác đã sửa gì hoặc đã chạy trước hay chưa**.

## 1. Nhận diện các đối tượng có thể bị chia sẻ

Spring Security phân biệt vài khái niệm:

| Thành phần | Ý nghĩa | Vì sao có nguy cơ rò trạng thái? |
| --- | --- | --- |
| `Authentication` | Principal, credentials, authorities và trạng thái xác thực của một lần xử lý | Một implementation có thể khả biến; nó còn tham chiếu tới principal hoặc details có thể thay đổi |
| `Authentication.getPrincipal()` | Đối tượng đại diện danh tính: `UserDetails`, JWT, OIDC user hoặc principal tùy biến | Một custom principal có thể có `List`, `Set`, `Map` khả biến hoặc setter sửa thông tin |
| `SecurityContext` | Chứa `Authentication` hiện tại | `setAuthentication(...)` có thể thay object đang giữ; nhiều context có thể trỏ tới cùng Authentication |
| `SecurityContextHolder` | Giữ context theo strategy, thường là ThreadLocal trong Servlet | Test để lại context trên thread sẽ ảnh hưởng thao tác chạy tiếp trên chính thread ấy |
| Fixture `static`, singleton bean hoặc cache | Dữ liệu được tái sử dụng giữa nhiều phương thức test | Tạo “kênh chia sẻ” dù mỗi test có test method riêng |
| Reactor Context | Cách Reactive chuyển security context theo subscription | Một publisher/context giữ tham chiếu tới authentication khả biến vẫn có nguy cơ bị sửa bên ngoài |

**Không phải mọi đối tượng đều khả biến giống nhau.** Ví dụ một số implementation của Spring Security không cho thay authorities sau khi khởi tạo. Nhưng điều đó **không bảo đảm** principal tùy biến, details, thuộc tính lồng nhau hoặc object được chia sẻ là bất biến. Đặc biệt, tạo hai token authentication cùng tham chiếu một principal không tạo ra hai bản sao principal.

Ví dụ:

~~~java
MutableAccountPrincipal shared = new MutableAccountPrincipal(
    "alice", new HashSet<>(Set.of("team-a")));

Authentication first = UsernamePasswordAuthenticationToken.authenticated(
    shared, "N/A",
    List.of(new SimpleGrantedAuthority("ROLE_USER")));

Authentication second = UsernamePasswordAuthenticationToken.authenticated(
    shared, "N/A",
    List.of(new SimpleGrantedAuthority("ROLE_USER")));

assertThat(first).isNotSameAs(second);
assertThat(first.getPrincipal()).isSameAs(second.getPrincipal());
~~~

Hai `Authentication` là hai object khác nhau, nhưng **principal giống hệt theo tham chiếu**. Nếu test A thêm `team-b` vào tập nhóm của principal, test B nhìn thấy sự thay đổi đó. Trong ví dụ này, danh sách `GrantedAuthority` đã tạo **không tự thay đổi** chỉ vì tập `teams` đổi; nguy cơ xuất hiện khi policy của ứng dụng đọc trực tiếp các nhóm/thuộc tính khả biến trên principal.

## 2. Ví dụ anti-pattern: một principal static cho cả suite

Một custom principal cho thấy rõ nguồn gốc lỗi:

~~~java
import java.security.Principal;
import java.util.HashSet;
import java.util.Set;

final class MutableAccountPrincipal implements Principal {
    private final String username;
    private final Set<String> teams;

    MutableAccountPrincipal(String username, Set<String> teams) {
        this.username = username;
        this.teams = teams;
    }

    @Override
    public String getName() {
        return username;
    }

    Set<String> teams() {
        return teams; // Trả thẳng collection khả biến.
    }
}
~~~

Và một bộ test **sai thiết kế**, cố tình dùng chung object:

~~~java
class SharedPrincipalAntiPatternTest {
    static final MutableAccountPrincipal ALICE =
        new MutableAccountPrincipal(
            "alice", new HashSet<>(Set.of("team-a")));

    @Test
    void temporarilyGrantTeamB() {
        // Tưởng rằng chỉ thay dữ liệu cho test này.
        ALICE.teams().add("team-b");
        assertThat(ALICE.teams()).contains("team-b");
    }

    @Test
    void aliceMustNotSeeTeamBByDefault() {
        // Có thể đỏ nếu test kia chạy trước.
        assertThat(ALICE.teams()).doesNotContain("team-b");
    }
}
~~~

Lỗi này không phụ thuộc Spring Security; chỉ cần shared mutable state đã đủ gây ô nhiễm. Nhưng khi object đó là principal được truyền vào `Authentication`, hậu quả liên quan trực tiếp đến bảo mật. Ví dụ một policy tự viết kiểu `principal.teams().contains(document.teamId())` có thể cấp quyền sai cho user trong test tiếp theo.

Các biến thể thường gặp:

- `static final Authentication TEST_AUTHENTICATION = ...` được tái sử dụng; `final` chỉ ngăn thay *tham chiếu*, không làm principal bên trong bất biến.
- `@TestInstance(PER_CLASS)` giữ một field principal khả biến cho mọi test method.
- `@BeforeAll` tạo một `SecurityContext` cho cả class, sau đó từng test thay `setAuthentication(...)`.
- Một singleton `@TestConfiguration` bean giữ `currentAuthentication`, `currentUser` hoặc một tập role có thể cập nhật.
- Một factory trả lại object đã cache thay vì tạo principal mới mỗi lần gọi.
- Một test dùng Mockito `when(authentication.getPrincipal())` với principal dùng chung rồi thay các thuộc tính ở test khác.

Không nên “chữa” các lỗi trên bằng `@TestMethodOrder`. Đổi thứ tự chỉ che hoặc tái hiện lỗi; một bộ test cô lập phải chạy đúng dù thứ tự và mức song song thay đổi.

## 3. Thiết kế fixture mới và principal bất biến cho mỗi ca

Cách đơn giản nhất là một **factory tạo object mới**. Với dữ liệu chỉ đọc, Java `record` và defensive copy giúp tránh thay đổi sau khi thiết lập:

~~~java
import java.security.Principal;
import java.util.Set;

record TestAccount(String id, Set<String> teams) implements Principal {
    TestAccount {
        // Copy ngay tại biên tạo object.
        teams = Set.copyOf(teams);
    }

    @Override
    public String getName() {
        return id;
    }
}
~~~

`Set.copyOf` giúp cả caller lẫn test không thêm/sửa/xóa nhóm qua `teams()`. Nếu principal chứa cấu trúc lồng nhau, chẳng hạn `Map<String, List<Permission>>` với `Permission` khả biến, phải copy các cấp tương ứng hoặc thiết kế các phần tử bất biến; **copy mỗi lớp Map ngoài cùng chưa phải deep copy**.

Factory tạo trọn bộ `Authentication` và `SecurityContext` mới:

~~~java
import java.util.Arrays;
import java.util.Set;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

final class SecurityFixtures {
    private SecurityFixtures() {}

    static Authentication authentication(
            String userId, Set<String> teams, String... authorities) {
        TestAccount principal = new TestAccount(userId, teams);
        var granted = Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toList();
        return UsernamePasswordAuthenticationToken.authenticated(
            principal, "N/A", granted);
    }

    static SecurityContext context(
            String userId, Set<String> teams, String... authorities) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            authentication(userId, teams, authorities));
        return context;
    }
}
~~~

Test xác minh tính độc lập thật sự, không chỉ so sánh tên:

~~~java
@Test
void twoFixturesWithSameUsernameHaveDifferentObjects() {
    SecurityContext first = SecurityFixtures.context(
        "alice", Set.of("team-a"), "ROLE_USER");
    SecurityContext second = SecurityFixtures.context(
        "alice", Set.of("team-a"), "ROLE_USER");

    assertThat(first).isNotSameAs(second);
    assertThat(first.getAuthentication())
        .isNotSameAs(second.getAuthentication());
    assertThat(first.getAuthentication().getPrincipal())
        .isNotSameAs(second.getAuthentication().getPrincipal());

    TestAccount account =
        (TestAccount) first.getAuthentication().getPrincipal();
    assertThat(account.teams()).containsExactly("team-a");
    assertThatThrownBy(() -> account.teams().add("team-b"))
        .isInstanceOf(UnsupportedOperationException.class);
}
~~~

Đây là kiểm thử khả năng cô lập fixture, **chưa phải** kiểm thử login hoặc JWT signature. Tên principal giống nhau vẫn hoàn toàn hợp lệ; trọng tâm là không cùng tham chiếu và không cùng state khả biến. Nếu dữ liệu thử nghiệm không cần custom principal, `@WithMockUser`/`mockUser()` thường gọn hơn việc tự dựng cả object.

## 4. Không chia sẻ SecurityContext chỉ vì đã tạo Authentication mới

Ngay cả khi hai authentication độc lập, một `SecurityContext` dùng chung vẫn có thể bị thay đổi bởi test khác:

~~~java
SecurityContext shared = SecurityContextHolder.createEmptyContext();
shared.setAuthentication(SecurityFixtures.authentication(
    "alice", Set.of("team-a"), "ROLE_USER"));

// Test khác thay authentication của cùng context object:
shared.setAuthentication(SecurityFixtures.authentication(
    "bob", Set.of("team-b"), "ROLE_ADMIN"));
~~~

`SecurityContextHolder.createEmptyContext()` là cách tạo context mới, không lấy lại context cũ rồi sửa. Nên tránh cấu trúc như `static final SecurityContext SHARED_CONTEXT` hoặc giữ một `SecurityContextImpl` trong singleton mutable test fixture.

Một helper quản lý phạm vi test imperative có thể thiết lập context tạm và **khôi phục context có trước**:

~~~java
static <T> T withContext(SecurityContext selected, Supplier<T> work) {
    SecurityContext previous = SecurityContextHolder.getContext();
    try {
        SecurityContextHolder.setContext(selected);
        return work.get();
    } finally {
        SecurityContextHolder.setContext(previous);
    }
}

@Test
void aliceContextDoesNotReplaceOuterContextForever() {
    SecurityContext outer = SecurityFixtures.context(
        "bob", Set.of("team-b"), "ROLE_USER");
    SecurityContextHolder.setContext(outer);
    try {
        String name = withContext(
            SecurityFixtures.context(
                "alice", Set.of("team-a"), "ROLE_USER"),
            () -> SecurityContextHolder.getContext()
                .getAuthentication().getName());
        assertThat(name).isEqualTo("alice");
        assertThat(SecurityContextHolder.getContext()).isSameAs(outer);
    } finally {
        SecurityContextHolder.clearContext();
    }
}
~~~

Helper trên minh họa scope tại **một thread**. `setContext(previous)` giữ nguyên context của caller nếu cần lồng các scope; ở ranh giới test độc lập, `clearContext()` trong `finally` bảo đảm thread test không còn authentication. Nó không thay thế giải pháp propagation khi chuyển sang executor khác.

### @BeforeEach và @AfterEach cần phối hợp với Spring Security Test

Khi tự đặt context bằng `SecurityContextHolder.setContext(...)`, dùng `try/finally` hoặc `@AfterEach` để tránh rò dữ liệu:

~~~java
@AfterEach
void clearManuallySetContext() {
    SecurityContextHolder.clearContext();
}
~~~

Với `@WithMockUser`, `WithSecurityContextTestExecutionListener` của Spring Security Test tạo và dọn test security context theo vòng đời do framework quản lý. Đừng vô tình gọi `clearContext()` ở `@BeforeEach` rồi tự xóa danh tính mà test listener vừa tạo; lịch thiết lập context có thể tùy `setupBefore`. Khi có callback custom hoặc tạo thread riêng, phải xem rõ ai chịu trách nhiệm setup/cleanup và không giả định test listener sẽ tự xóa context ở mọi thread pool do ứng dụng tạo.

## 5. Cô lập danh tính trong bài test Servlet bằng MockMvc

Trong các test HTTP của Spring MVC, `@WithMockUser` hoặc `user(...)` của Spring Security Test cung cấp principal phù hợp với từng request. Không cần tạo một `static Authentication` rồi chuyển qua các test:

~~~java
@RestController
@RequestMapping("/api")
class IdentityController {

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/admin")
    @PreAuthorize("hasRole('ADMIN')")
    Map<String, String> admin(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}
~~~

Controller mẫu cần `@EnableMethodSecurity` và Spring Security filter chain có yêu cầu xác thực cho `/api/**`. Một cấu hình Servlet tối thiểu có thể viết:

~~~java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
class IdentitySecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Các import gồm `@Configuration`, `@EnableWebSecurity`, `@EnableMethodSecurity`, `@Bean`, `HttpSecurity`, `SecurityFilterChain` và `Customizer`. Trong ứng dụng Spring Boot đã nạp controller và cấu hình trên, test minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityMvcTest {
    @Autowired MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceSeesOnlyHerOwnTestIdentity() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void bobCannotInheritAliceOrAdminRoles() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("bob"));
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    void requestPostProcessorCreatesTheIntendedIdentity()
            throws Exception {
        mvc.perform(get("/api/admin").with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("admin"));

        mvc.perform(get("/api/admin").with(user("guest").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
~~~

Các import của controller gồm `@RestController`, `@RequestMapping`, `@GetMapping`, `@PreAuthorize`, `Authentication` và `Map`. Các phép thử trên **xác nhận phân quyền với danh tính được giả lập**, không xác nhận mật khẩu thật, session login hoặc việc UserDetailsService đã được gọi.

Hai request `with(user(...))` trong cùng test tạo những danh tính tách biệt; test không sửa một principal dùng chung để đổi Alice thành Bob. Nếu ứng dụng có session hoặc singleton auth cache, cần bổ sung kiểm tra readback và session độc lập tương ứng, vì một request post processor không tự reset mọi state khác của ứng dụng.

## 6. WebFlux: mỗi WebTestClient request có authentication riêng

WebFlux không dựa vào ThreadLocal Servlet thông thường để truyền `SecurityContext` xuyên reactive chain; Spring Security dùng **Reactor Context**. Tuy nhiên, việc thay ThreadLocal bằng Reactor Context **không biến một principal khả biến được chia sẻ thành dữ liệu bất biến**. Nếu hai subscription tham chiếu cùng object rồi một nơi sửa thuộc tính, chúng vẫn có thể nhìn thấy cùng thay đổi.

Ví dụ controller Reactive đọc thông tin từ authenticated principal:

~~~java
@RestController
class ReactiveIdentityController {

    @GetMapping("/api/reactive/me")
    Mono<Map<String, String>> current(Mono<Principal> principal) {
        return principal.map(p -> Map.of("user", p.getName()));
    }
}
~~~

Trong test context WebFlux đã có `SecurityWebFilterChain` yêu cầu xác thực cho `/api/reactive/me`, chẳng hạn:

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveIdentitySecurityConfiguration {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/reactive/**").authenticated()
                .anyExchange().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình Reactive dùng các import `@Configuration`, `@Bean`, `@EnableWebFluxSecurity`, `ServerHttpSecurity`, `SecurityWebFilterChain` và `Customizer`. Trong ứng dụng đã nạp các bean này, hãy dùng mỗi lần một request identity:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "spring.main.web-application-type=reactive"
)
@AutoConfigureWebTestClient
class ReactiveIdentityIsolationTest {
    @Autowired WebTestClient client;

    @Test
    void aliceDoesNotBecomeBobAcrossRequests() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/api/reactive/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("alice");

        client.mutateWith(mockUser("bob").roles("USER"))
            .get().uri("/api/reactive/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("bob");
    }
}
~~~

Controller cần import `java.security.Principal`, `java.util.Map`, `reactor.core.publisher.Mono` và các annotation WebFlux. Mỗi `mockUser(...)` được tạo cho request cụ thể. Test này kiểm tra hai danh tính riêng biệt trong luồng HTTP giả lập, **không kiểm tra password của người dùng**.

Khi viết code không phụ thuộc HTTP, có thể đặt authentication theo từng Reactor subscription:

~~~java
Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Authentication alice = SecurityFixtures.authentication(
    "alice", Set.of("team-a"), "ROLE_USER");
Authentication bob = SecurityFixtures.authentication(
    "bob", Set.of("team-b"), "ROLE_USER");

StepVerifier.create(currentName.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();

StepVerifier.create(currentName.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob)))
    .expectNext("bob")
    .verifyComplete();
~~~

Ở đây test tự cung cấp **hai Authentication khác nhau**. `contextWrite(...)` thiết lập Reactor Context cho subscription tương ứng; nó không được phép ngầm đọc/ghi một `static currentAuthentication` mà các test khác chia sẻ. Khi triển khai phương thức Reactive có `@PreAuthorize`, nên dùng `StepVerifier` subscribe trên **Spring-managed bean**, thay vì tạo instance trực tiếp và vô tình bỏ qua method-security interceptor.

### Test chạy đồng thời hai subscription

Với Reactive, bài kiểm tra tăng cường có thể đưa Alice và Bob qua hai subscription độc lập:

~~~java
Mono<String> aliceName = currentName.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(
        SecurityFixtures.authentication(
            "alice", Set.of("team-a"), "ROLE_USER")));

Mono<String> bobName = currentName.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(
        SecurityFixtures.authentication(
            "bob", Set.of("team-b"), "ROLE_USER")));

StepVerifier.create(Mono.zip(aliceName, bobName))
    .assertNext(tuple -> {
        assertThat(tuple.getT1()).isEqualTo("alice");
        assertThat(tuple.getT2()).isEqualTo("bob");
    })
    .verifyComplete();
~~~

`Mono.zip(...)` chứng minh hai context không bị ghi đè bởi một trường lưu identity toàn cục, nhưng **chưa đủ để phát hiện mọi race condition**: cần thêm điều kiện đồng bộ hoặc chạy parallel thực sự nếu muốn gây ra một cửa sổ cạnh tranh cụ thể. Với dữ liệu principal khả biến, nên loại bỏ trạng thái chia sẻ trước khi tìm cách tăng độ ngẫu nhiên của lịch thực thi.

## 7. JWT, OAuth2 và OIDC: dữ liệu claims/attributes cũng phải độc lập

`spring-security-test` cho phép giả lập nhiều loại authentication:

| Cơ chế | Servlet test | Reactive test | Phạm vi kiểm chứng |
| --- | --- | --- | --- |
| User đơn giản | `@WithMockUser`, `user(...)` | `@WithMockUser` ở method test, `mockUser()` với WebTestClient | Identity và authorities giả lập |
| JWT Resource Server | `jwt()` | `mockJwt()` | Principal/claims/authorities giả lập, không xác minh chữ ký |
| OAuth2 Login | `oauth2Login()` | `mockOAuth2Login()` | Đăng nhập đã giả lập, không chạy OAuth2 redirect/code exchange |
| OIDC Login | `oidcLogin()` | `mockOidcLogin()` | OIDC principal giả lập, không xác minh ID token thật |
| Opaque token | `opaqueToken()` | `mockOpaqueToken()` | Principal introspection giả lập, không gọi authorization server |

Vấn đề chia sẻ không chỉ xuất hiện ở `UserDetails`. Một test có thể dùng `Map<String, Object>` claims hoặc `Map<String, Object>` user attributes làm fixture dùng chung, rồi thay `sub`, `groups` hoặc `tenant` cho test sau. Các object giả lập có thể tự copy một số trường trong quá trình xây dựng, nhưng **đừng dựa vào hành vi copy ngầm của builder để thay cho thiết kế fixture độc lập**.

Ví dụ với Servlet:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

@Test
void jwtForAliceUsesFreshClaims() throws Exception {
    mvc.perform(get("/api/me")
            .with(jwt().jwt(builder -> builder
                .subject("alice")
                .claim("tenant_id", "tenant-a"))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.user").value("alice"));
}

@Test
void jwtForBobDoesNotReuseAliceClaims() throws Exception {
    mvc.perform(get("/api/me")
            .with(jwt().jwt(builder -> builder
                .subject("bob")
                .claim("tenant_id", "tenant-b"))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.user").value("bob"));
}
~~~

Đây là các ca test áp dụng cho context đã hỗ trợ Spring Security Test JWT và controller nhận `Authentication` như mục 5. Các request này **không truyền JWT đã ký tới `JwtDecoder`**; chúng kiểm tra logic downstream khi identity và claims được thiết lập cho từng request. Để kiểm tra JWT sai chữ ký, issuer không khớp hoặc hết hạn, cần một suite riêng gửi Bearer token thực qua decoder.

Tương tự ở Reactive:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt()
        .jwt(builder -> builder.subject("alice")
            .claim("tenant_id", "tenant-a"))
        .authorities(new SimpleGrantedAuthority("SCOPE_profile.read")))
    .get().uri("/api/reactive/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.user").isEqualTo("alice");
~~~

Mỗi lần gọi `mockJwt()` tạo fixture theo request, thay vì sử dụng chung một `JwtAuthenticationToken` có claim details do test khác có thể thay đổi. Dù JWT ở nhiều API được mô hình hóa bằng object ít hoặc không có setter, các **tham chiếu tới data structure khả biến trong fixture** vẫn phải được xem xét, đặc biệt khi kết hợp custom authentication converter hoặc authorities theo attribute.

### Custom OIDC principal và nested attributes

Giả sử test OIDC tự xây user profile có dữ liệu:

~~~java
Map<String, Object> sharedClaims = new HashMap<>();
sharedClaims.put("sub", "alice");
sharedClaims.put("teams", new ArrayList<>(List.of("team-a")));
~~~

Nếu test B đổi danh sách `teams` thành thêm `team-b` rồi sử dụng lại `sharedClaims`, test A và B có thể không còn độc lập. `Map.copyOf(sharedClaims)` chỉ copy cấu trúc ngoài: nếu value vẫn là `ArrayList`, list đó vẫn khả biến. Hãy tạo các map/list mới theo từng test, ưu tiên `List.of(...)` và value bất biến, hoặc deep-copy đầy đủ theo cấu trúc được phép.

Với các bài test `oidcLogin()`, `mockOidcLogin()` hoặc principal implement `OidcUser` tùy biến, cần kiểm tra cả danh sách claim/attribute, tên principal, authorities và token giả lập. Một test đổi authority của user OIDC từ viewer sang admin phải tạo fixture mới, không sửa object đã được test khác sử dụng.

**Không cần** ghi access token/refresh token thật vào fixture hoặc log để kiểm thử này. Các giá trị minh họa chỉ dùng trong test, được tạo mới và có vòng đời rõ ràng.

## 8. Với @WithSecurityContext tùy biến: factory phải tạo context mới

Khi mặc định `@WithMockUser` không chứa đủ domain identity, dự án thường tạo một annotation riêng bằng `@WithSecurityContext`. Đây là chỗ dễ tạo shared mutable state nếu factory giữ một `SecurityContext` static và chỉ đổi principal.

Ví dụ một annotation đơn giản:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;
import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@WithSecurityContext(factory = WithTeamUserFactory.class)
public @interface WithTeamUser {
    String username() default "alice";
    String team() default "team-a";
}
~~~

Factory đúng là **không cache SecurityContext**:

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithTeamUserFactory
        implements WithSecurityContextFactory<WithTeamUser> {

    @Override
    public SecurityContext createSecurityContext(WithTeamUser annotation) {
        return SecurityFixtures.context(
            annotation.username(),
            Set.of(annotation.team()),
            "ROLE_USER");
    }
}
~~~

Spring Security Test gọi factory để tạo security context cho lần chạy có annotation; factory này tạo **principal, Authentication và SecurityContext mới**. Một method test có thể viết:

~~~java
@Test
@WithTeamUser(username = "alice", team = "team-a")
void aliceFromCustomAnnotationHasIndependentIdentity() {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
    TestAccount principal = (TestAccount) auth.getPrincipal();

    assertThat(principal.getName()).isEqualTo("alice");
    assertThat(principal.teams()).containsExactly("team-a");
}
~~~

Không tạo kiểu:

~~~java
// SAI: cùng một SecurityContext dùng lại cho mọi lần factory được gọi.
static final SecurityContext SHARED = SecurityContextHolder.createEmptyContext();
// createSecurityContext(...) { SHARED.setAuthentication(...); return SHARED; }
~~~

Với test chạy song song, mỗi lần ghi `SHARED.setAuthentication(...)` có thể thay Authentication mà một test khác đang dùng **ngay giữa request**. Sự cố này nghiêm trọng hơn việc test phụ thuộc thứ tự: nó gây race condition trên danh tính.

## 9. Test container và test context không đồng nghĩa dữ liệu độc lập

Spring Test thường cache `ApplicationContext` để giảm thời gian khởi động. Vì thế, ngay cả khi JUnit tạo một test class instance mới cho mỗi test method, **các singleton Spring bean trong context có thể vẫn là cùng object**.

| Nguồn state | Có được tạo mới tự động mỗi test không? | Điều cần làm |
| --- | --- | --- |
| Local variable trong test method | Có | Tạo fixture bên trong method hoặc factory |
| Field instance với lifecycle JUnit mặc định `PER_METHOD` | Mỗi method có instance mới | Tránh chia sẻ qua static hoặc singleton được tham chiếu |
| Field instance với `@TestInstance(PER_CLASS)` | Không | Reset dữ liệu hoặc không dùng mutable principal tại field |
| Field `static` | Không | Không đặt Authentication/principal mutable ở đây |
| Singleton `@Bean` trong Spring context cache | Không nhất thiết | Tránh lưu `currentUser` mutable trong bean; reset state test đúng cách |
| HTTP session/WebSession | Phụ thuộc session/cookie | Tách session/cookie theo test |
| Database hoặc Redis | Không | Dùng transaction/reset/schema/container/namespace phù hợp |
| Thread pool | Có thể tái sử dụng worker | Dùng wrapper propagation, cleanup và test chống rò `SecurityContext` |
| Reactor Context | Theo subscription khi được gắn đúng | Không truyền object Authentication mutable dùng chung |

`@DirtiesContext` có thể buộc Spring tạo context mới khi cần, nhưng không tự động làm sạch mọi `static` field, biến global của process, cache bên ngoài, dữ liệu database/Redis hay worker do ứng dụng tự tạo và không được đóng đúng. `@Transactional` trên test cũng không bảo đảm rollback mọi thay đổi đã commit từ request HTTP chạy ở transaction khác.

Vì thế, **cách khắc phục ưu tiên là thiết kế fixture độc lập**; chỉ dùng `@DirtiesContext` hoặc reset môi trường khi thực sự cần kiểm tra một bean/stateful integration. Dùng reset global hoặc xóa toàn bộ storage trong test chạy song song có thể phá hỏng dữ liệu của test khác.

## 10. Phát hiện lỗi chia sẻ bằng những phép kiểm tra có chủ đích

Một bộ test có thể chứa nhiều ca `200 OK`, nhưng vẫn chưa phát hiện được dữ liệu Alice rò sang Bob. Khi thử nghiệm tính cô lập, nên đo **trạng thái trước và sau** thay vì chỉ xem endpoint trả mã gì.

### Test A: đầu vào thay đổi không làm fixture thay đổi

~~~java
@Test
void changingCallerOwnedSetDoesNotChangePrincipal() {
    Set<String> source = new HashSet<>(Set.of("team-a"));
    TestAccount account = new TestAccount("alice", source);

    source.add("team-admin");

    assertThat(account.teams())
        .containsExactly("team-a")
        .doesNotContain("team-admin");
}
~~~

Phép thử này chứng minh factory đã làm defensive copy ngay cả khi caller tiếp tục sửa `source`. Nếu constructor chỉ gán `this.teams = source`, test thất bại và sẽ cảnh báo nguy cơ dùng chung state trong test cũng như ở production.

### Test B: cùng tên nhưng khác phiên dữ liệu không chia sẻ quyền

~~~java
@Test
void sameUsernameDoesNotImplySameFixtureInstance() {
    Authentication first = SecurityFixtures.authentication(
        "alice", Set.of("team-a"), "ROLE_USER");
    Authentication second = SecurityFixtures.authentication(
        "alice", Set.of("team-b"), "ROLE_USER");

    assertThat(first).isNotSameAs(second);
    assertThat(first.getPrincipal()).isNotSameAs(second.getPrincipal());

    TestAccount a = (TestAccount) first.getPrincipal();
    TestAccount b = (TestAccount) second.getPrincipal();

    assertThat(a.teams()).containsExactly("team-a");
    assertThat(b.teams()).containsExactly("team-b");
}
~~~

Không được dựa hoàn toàn vào `equals(...)` vì hai security object có thể được so sánh theo cùng tên hoặc giá trị nghiệp vụ. Đối với mục tiêu xác định **không dùng chung object**, `isNotSameAs(...)` trực tiếp diễn đạt điều kiện tham chiếu.

### Test C: chạy trên nhiều thread không dùng cùng context

Trong Servlet, `SecurityContextHolder` mặc định dùng ThreadLocal. Khi một tác vụ được chuyển sang executor, cần wrapper như `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable` hoặc `DelegatingSecurityContextExecutor`. Những wrapper này truyền **SecurityContext được lựa chọn**, không nhất thiết deep-copy principal.

~~~java
@Test
void twoTasksUseIndependentlyCreatedContexts()
        throws Exception {
    ExecutorService raw = Executors.newSingleThreadExecutor();
    try {
        SecurityContext aliceContext = SecurityFixtures.context(
            "alice", Set.of("team-a"), "ROLE_USER");
        SecurityContext bobContext = SecurityFixtures.context(
            "bob", Set.of("team-b"), "ROLE_USER");

        Callable<String> aliceTask = () ->
            SecurityContextHolder.getContext()
                .getAuthentication().getName();
        Callable<String> bobTask = () ->
            SecurityContextHolder.getContext()
                .getAuthentication().getName();

        Future<String> first = raw.submit(
            new DelegatingSecurityContextCallable<>(
                aliceTask, aliceContext));
        Future<String> second = raw.submit(
            new DelegatingSecurityContextCallable<>(
                bobTask, bobContext));

        assertThat(first.get(3, TimeUnit.SECONDS)).isEqualTo("alice");
        assertThat(second.get(3, TimeUnit.SECONDS)).isEqualTo("bob");

        Future<Authentication> after = raw.submit(() ->
            SecurityContextHolder.getContext().getAuthentication());
        assertThat(after.get(3, TimeUnit.SECONDS)).isNull();
    } finally {
        raw.shutdownNow();
        SecurityContextHolder.clearContext();
    }
}
~~~

Test dùng **một worker thread** để kiểm tra cả việc Alice/Bob được gắn đúng context và việc worker không giữ lại authentication sau hai task. Các import bổ sung gồm `java.util.concurrent.*`, `org.springframework.security.concurrent.DelegatingSecurityContextCallable` và JUnit/AssertJ. Nếu code dùng cùng một `SecurityContext` để chứa hai identity, sự cố sẽ dễ xảy ra hơn, nhất là khi task có thể chạy đồng thời.

Lưu ý: wrapper có thể khôi phục context trước đó của worker, nên trong môi trường executor đã bị ô nhiễm bởi code khác, `after` không nhất thiết `null`. Bài test sử dụng **executor mới không có Authentication ban đầu**, vì vậy kỳ vọng `null` là hợp lý. Ở môi trường thật, cần dọn nguyên nhân làm bẩn worker thay vì buộc wrapper che giấu nó.

### Test D: không dùng lại principal sau khi xóa credentials

Một số loại `Authentication` hỗ trợ `eraseCredentials()`, và một số đối tượng principal/credentials implement `CredentialsContainer` có thể bị xóa thông tin nhạy cảm. Nếu một test dùng cùng object với test khác, việc dọn credentials ở test A có thể làm fixture test B thay đổi ngoài ý muốn.

Ngay cả khi mục đích là bảo mật, một thao tác thay đổi state vẫn cần **ownership rõ ràng**. Với kiểm thử, hãy tạo authentication mới khi cần xác nhận `eraseCredentials()`, không đặt nó trên một singleton fixture để các test khác tiếp tục dùng.

## 11. Các ca authorization phải chứng minh không có quyền dư

Khi principal có dữ liệu doanh nghiệp, test nên đặt các câu hỏi trực tiếp về quyền:

| Tình huống | Fixture đúng | Kỳ vọng |
| --- | --- | --- |
| Alice chỉ có quyền đọc | Authentication mới có `SCOPE_documents.read` | `GET` thành công, `PUT` bị `403` |
| Bob có quyền sửa nhưng không sở hữu tài liệu Alice | Principal Bob mới, role/scope phù hợp | Từ chối truy cập tài liệu Alice theo owner policy |
| Alice có thêm quyền tạm trong một test | Chỉ fixture của test đó có `ROLE_ADMIN` | Test Alice bình thường khác không tự có ADMIN |
| JWT Alice và JWT Bob trong hai request | Tạo `jwt()`/`mockJwt()` mới theo request | Principal, tenant và scope không bị lẫn |
| OIDC user hai tenant | Claims/attributes mới cho mỗi principal | Không mang claim tenant của người này sang người kia |
| Test thành công chạy trước test âm tính | Không chia sẻ Authentication/principal | Test âm tính vẫn `403` theo policy |
| Hai test chạy cùng lúc | Không giữ principal trong field static/singleton mutable | Không xuất hiện danh tính hoặc authority của nhau |

Ví dụ một bài test quyền có ý nghĩa cần **cặp đối chứng**:

~~~java
@Test
void guestCannotInheritAdminAuthority() throws Exception {
    mvc.perform(get("/api/admin")
            .with(user("admin").roles("ADMIN")))
        .andExpect(status().isOk());

    mvc.perform(get("/api/admin")
            .with(user("guest").roles("USER")))
        .andExpect(status().isForbidden());
}
~~~

Trong test trên, hai request dùng **hai `Authentication` do request post processor tạo**, không thay principal của cùng một object để “giả làm” guest. Nếu hệ thống có cache authorization dựa vào principal ID hoặc resource ID, vẫn phải kiểm tra tính đúng đắn của cache bằng những test khác; chỉ thay request principal chưa chắc reset cache.

Một ca âm tính đơn lẻ trả `403` không đủ chứng minh hệ thống không bị rò quyền. Nó có thể bị từ chối bởi CSRF, không có filter chain phù hợp hoặc thiếu dữ liệu test. Luôn có đối chứng `200` cho đúng owner/quyền trên cùng endpoint, đồng thời kiểm tra nguyên nhân của các ca `403`.

## 12. Các nguyên tắc khi chạy test song song

Chạy song song giúp phát hiện race condition nhưng cũng làm lộ các anti-pattern về fixture:

1. **Không dùng `static Authentication` hay `static MutablePrincipal`** nếu có test sửa bất kỳ phần nào của object graph.
2. **Không đặt một `SecurityContext` dùng chung vào tất cả Reactor subscription hoặc request** rồi sửa authentication theo user hiện tại.
3. **Tránh `@TestInstance(PER_CLASS)` với field principal có setter hoặc collection mutable**, trừ khi mỗi test tự khởi tạo lại và có cơ chế ngăn thao tác song song phù hợp.
4. **Không dùng global `SecurityContextHolder.setStrategyName(...)` như một reset tiện lợi giữa test**: thay đổi strategy ảnh hưởng toàn JVM và các test chạy đồng thời.
5. **Dọn context trong `finally` hoặc callback đúng vòng đời** khi test tự đặt nó; đừng chỉ dọn khi assertion đi qua.
6. **Cô lập storage ngoài memory** nếu policy đọc dữ liệu user, role, tenant, session hoặc consent từ database/Redis.
7. **Không dùng test order để kiểm soát state**; một suite đáng tin cậy chạy được độc lập, lặp lại và với thứ tự thay đổi.

Ví dụ cấu hình JUnit 5 có thể bật chạy song song:

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
~~~

Đây chỉ là ví dụ cấu hình, **không phải yêu cầu áp dụng ngay cho mọi dự án**. Những integration test dùng chung database, cổng server hoặc singleton không thread-safe phải được thiết kế cô lập trước hoặc quản lý tài nguyên chạy song song một cách có chủ đích. Bật parallel trước khi sửa shared state có thể khiến CI không ổn định mà không tăng chất lượng test.

Với trường hợp cần tái hiện chính xác một race condition, dùng `CountDownLatch`/barrier để điều phối hai task tới điểm cạnh tranh, không dựa vào `Thread.sleep(...)` để “hy vọng” đúng lịch chạy. Sau khi tái hiện lỗi, sửa thiết kế bằng fixture riêng hoặc cấu trúc bất biến, rồi test lại.

## 13. Checklist chẩn đoán khi test thay đổi kết quả theo thứ tự

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Test Bob nhìn thấy role của Alice | Dùng chung Authentication/principal hoặc mutable authorities source | Tạo fixture mới, giữ authorities/attributes bất biến |
| Test pass riêng nhưng fail khi chạy cả suite | Static field, singleton bean, session hoặc database dùng chung | Tìm state vượt vòng đời test; reset hoặc tách phạm vi |
| Test pass khi chạy tuần tự, fail khi parallel | Race condition trên principal, context hoặc cache | Không chia sẻ mutable object, đồng bộ/kiểm soát external state |
| Context của test trước vẫn tồn tại | Tự `setContext(...)` không dọn đúng callback/finally | Dùng `clearContext()` ở biên phù hợp |
| Một test `@WithMockUser` không thấy user mong đợi | Custom `@BeforeEach` đã xóa context hoặc khác thời điểm listener setup | Kiểm tra `WithSecurityContextTestExecutionListener` và `setupBefore` |
| WebFlux subscription thấy sai principal | Dùng chung principal mutable, contextWrite sai vị trí hoặc subscription không gắn context | Đặt context cho từng subscription và tránh shared object |
| JWT/OIDC test nhận claim không mong đợi | Mutable claims map/list hoặc builder fixture dùng chung | Tạo map/list mới, copy nested values |
| Async worker nhận principal của request trước | Tự setContext không dọn hoặc executor wrapper dùng context cố định | Propagate theo lần submit và xác minh cleanup |
| `@DirtiesContext` vẫn không khắc phục | State nằm ở `static`, database, Redis, thread pool tự quản lý | Dọn đúng nguồn state, không chỉ tạo lại Spring context |
| Test âm tính `403` nhưng không kiểm tra được role | CSRF hoặc authentication thất bại trước khi tới policy | Thêm đối chứng dương và quan sát từng lớp security |

Một cách debug hiệu quả là ghi **tên test, identity giả được tạo, authority mong đợi và phép kiểm tra đang chạy** mà không log credentials hoặc access token nhạy cảm. Chỉ dùng các định danh giả như `alice-test`, `bob-test` và `tenant-test-a`; không in JWT thực hoặc refresh token vào log CI.

## 14. Bài tập thực hành

1. Tạo `MutableAccountPrincipal` với `Set<String> teams` rồi dùng chung instance giữa hai test. Quan sát test phụ thuộc thứ tự; thay bằng `TestAccount` bất biến và factory tạo mới để sửa lỗi.
2. Tạo hai `UsernamePasswordAuthenticationToken` khác nhau nhưng truyền cùng principal. Viết assertion `isSameAs(...)` phát hiện tham chiếu chia sẻ; sửa fixture để principal cũng độc lập.
3. Tạo hai `SecurityContext` mới cho Alice/Bob với `SecurityContextHolder.createEmptyContext()`. Viết test xác minh chúng chứa hai Authentication và principal khác nhau.
4. Dùng `@WithMockUser` trên hai test MockMvc: Alice USER và Bob ADMIN. Thêm test negative để chắc chắn Alice không thừa hưởng quyền ADMIN của Bob; không dùng static authentication.
5. Dùng `jwt()` hoặc `mockJwt()` để tạo hai request có `sub`, `tenant_id` và authorities khác nhau. Test response/policy thể hiện chính xác principal của từng request.
6. Tạo `@WithSecurityContext` factory dùng lại một `SecurityContext` static và quan sát vấn đề khi nhiều test cùng chạy; sau đó sửa factory để mỗi invocation trả context mới.
7. Trong WebFlux, sử dụng `Mono.zip(...)` với hai subscriber Alice/Bob và hai authentication riêng. Xác minh không bị lấy user từ một biến global.
8. Tạo executor một worker và hai `DelegatingSecurityContextCallable` độc lập. Kiểm tra Alice → Bob → task không context, bao gồm nhánh delegate ném exception.
9. Dùng `@TestInstance(PER_CLASS)` với một principal mutable field, xác định điểm gây phụ thuộc test order. Chuyển sang fixture tạo trong method hoặc factory rồi chạy lại theo thứ tự bất kỳ.
10. Thêm một singleton test bean có `Map<String, UserRecord>` lưu trạng thái quyền. Kiểm tra test A không thay dữ liệu test B; nếu bean được tái sử dụng qua cached `ApplicationContext`, thiết kế lại nguồn dữ liệu theo namespace/test hoặc reset an toàn.
11. Thực hiện test với user bị khóa hoặc có quyền được thu hồi. Đảm bảo test cấp quyền mới không dùng lại object của user ở trạng thái cũ; phân biệt dữ liệu fixture và sự kiện authentication thật.
12. Lập bảng liệt kê mọi fixture bảo mật trong dự án: nguồn tạo, vòng đời, khả năng mutable, có dùng static/singleton/cache hay không, và cơ chế dọn giữa các test.

### Kết quả cần đạt

Người học hoàn thành bài khi phân biệt được **cùng giá trị danh tính** với **cùng tham chiếu đối tượng**, hiểu tại sao `final`, `@WithMockUser`, Spring context cache hay Reactor Context không tự giải quyết mọi shared mutable state, và biết tạo **Authentication, principal và SecurityContext mới cho từng ca cần độc lập**. Một suite tốt phải kiểm tra cả hành vi được phép lẫn bị từ chối, chạy ổn định khi đổi thứ tự, và không làm rò quyền giữa user, request, test method hay worker thread.

### Tài liệu tham khảo

- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring Security — Test Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — SecurityContextHolder](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Reactive WebTestClient Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [JUnit 5 — Test Instance Lifecycle and Parallel Execution](https://junit.org/junit5/docs/current/user-guide/)
