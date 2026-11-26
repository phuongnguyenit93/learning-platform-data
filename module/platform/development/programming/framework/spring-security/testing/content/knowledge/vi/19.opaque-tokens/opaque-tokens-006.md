# Gửi bearer token thật để kiểm tra đường đi qua introspector

Trong ứng dụng dùng OAuth2 Resource Server, một kiểm thử với `opaqueToken()` có thể trả `200 OK` dù không có yêu cầu nào tới introspection endpoint. Lý do là `opaqueToken()` của `spring-security-test` đặt sẵn `BearerTokenAuthentication` vào ngữ cảnh bảo mật. Để kiểm chứng **đường xác thực của một bearer token**, cần gửi chuỗi token thật sự qua header HTTP rồi quan sát Spring Security gọi `OpaqueTokenIntrospector` (Servlet) hoặc `ReactiveOpaqueTokenIntrospector` (Reactive).

Bài học thuộc chương **Opaque token** của module **SPRING_SECURITY_TESTING**, tập trung vào kiểm thử xác thực và phân quyền HTTP bằng `MockMvc`, `WebTestClient` và `spring-security-test`. Giá trị token trong các ví dụ là chuỗi opaque tạo riêng cho test: không cần JWT hợp lệ, không lấy token sản xuất và không gọi nhà cung cấp danh tính thật.

## 1. Phân biệt giả lập danh tính với gửi bearer token

Hai request dưới đây trông giống nhau ở controller nhưng kiểm chứng hai hành vi khác nhau:

~~~java
// Đặt sẵn người dùng đã xác thực. Không gọi introspector.
mockMvc.perform(get("/api/profile")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read"))))
    .andExpect(status().isOk());

// Header Bearer đi qua security filter và introspector.
mockMvc.perform(get("/api/profile")
        .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-live-001"))
    .andExpect(status().isOk());
~~~

Ở ví dụ thứ nhất, `opaqueToken()` của `SecurityMockMvcRequestPostProcessors` trực tiếp thiết lập danh tính thích hợp để kiểm thử authorization. Kiểm thử ấy **không chứng minh** token từ client được trích xuất, xác minh hoặc kiểm tra trạng thái `active`.

Ở ví dụ thứ hai, `BearerTokenAuthenticationFilter` xử lý header `Authorization: Bearer opaque-live-001` rồi chuyển token cho cơ chế xác thực. Nếu Resource Server được cấu hình dùng opaque token, `OpaqueTokenAuthenticationProvider` gọi `OpaqueTokenIntrospector.introspect("opaque-live-001")`. Kết quả xác thực phụ thuộc thông tin introspector trả về.

Chữ **thật** trong “gửi bearer token thật” chỉ **cách gửi token qua HTTP và cho chạy đường xử lý bảo mật thật**. Không cần đưa secret, token đang có hiệu lực ở môi trường sản xuất hay truy cập mạng ngoài test.

~~~mermaid
sequenceDiagram
    participant Client as MockMvc/WebTestClient
    participant Filter as Security filter chain
    participant Intro as OpaqueTokenIntrospector
    participant IdP as Introspection endpoint
    participant API as Controller
    Client->>Filter: GET /api/profile + Authorization: Bearer opaque-live-001
    Filter->>Intro: introspect("opaque-live-001")
    Intro->>IdP: POST /introspect, token=opaque-live-001
    IdP-->>Intro: {"active":true,"sub":"alice","scope":"profile.read"}
    Intro-->>Filter: OAuth2AuthenticatedPrincipal
    Filter->>API: Authentication hợp lệ + đủ quyền
    API-->>Client: 200 OK
~~~

Resource Server thường gửi yêu cầu introspection bằng HTTP `POST`, body dạng `application/x-www-form-urlencoded` chứa trường `token`. Nó có thể dùng HTTP Basic với **client ID và client secret của Resource Server** khi gọi authorization server. Đây là thông tin xác thực *chiều đi* từ Resource Server tới IdP, khác với Bearer header *chiều vào* từ client.

## 2. Điều gì được xác nhận sau introspection?

Ví dụ authorization server trả JSON cho một token đang hoạt động:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "profile.read profile.write",
  "client_id": "web-client",
  "token_type": "Bearer"
}
~~~

Spring Security tạo `OAuth2AuthenticatedPrincipal` từ kết quả hợp lệ. Các scope thông dụng được ánh xạ thành authorities có tiền tố `SCOPE_`: `profile.read` tương ứng `SCOPE_profile.read`. Khi authentication thành công, controller Servlet có thể nhận `BearerTokenAuthentication`; WebFlux cũng có thể sử dụng principal tương ứng.

| Tình huống | Phản hồi HTTP điển hình khi dùng Bearer Resource Server |
| --- | --- |
| Không gửi Bearer trên endpoint cần đăng nhập | `401 Unauthorized`; introspector không được gọi |
| Token `active=true`, đủ scope | `200 OK`; introspector được gọi |
| Token `active=false` hoặc bị thu hồi | `401 Unauthorized` |
| Token `active=true` nhưng thiếu authority | `403 Forbidden` |
| Introspection endpoint timeout/HTTP 5xx | Xác thực không thể hoàn thành; mã HTTP cụ thể phụ thuộc xử lý lỗi, có thể là lỗi máy chủ |
| `opaqueToken()` tạo danh tính đủ quyền | Có thể `200` nhưng introspector không được gọi |

Phân biệt `401` (không xác thực được) với `403` (đã có danh tính hợp lệ nhưng không đủ quyền) là thiết yếu. Khi introspection lỗi, hệ thống không được tự động coi token là hợp lệ; tuy nhiên đừng viết test cứng `401` cho **mọi** lỗi mạng vì các ngoại lệ hạ tầng có thể được xử lý khác.

Introspection hỗ trợ cả những token có hình thức JWT nếu Resource Server được cấu hình xác minh bằng introspection. Giá trị token được chuyển cho introspector dưới dạng chuỗi; việc token có ba phần ngăn bởi dấu chấm không tự động khiến `JwtDecoder` được sử dụng.

## 3. Tạo ứng dụng Servlet cho bài kiểm thử

Với Spring Boot dùng Spring MVC, ví dụ dependency Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("org.wiremock:wiremock-standalone:3.13.2")
}
~~~

Cấu hình Java của ứng dụng minh họa:

~~~java
@Configuration
class OpaqueSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/profile")
                    .hasAuthority("SCOPE_profile.read")
                .requestMatchers("/api/admin")
                    .hasAuthority("SCOPE_admin")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}

@RestController
class ProfileController {
    @GetMapping("/api/profile")
    Map<String, String> profile(BearerTokenAuthentication authentication) {
        return Map.of("subject", authentication.getName());
    }

    @GetMapping("/api/admin")
    String admin() {
        return "ADMIN";
    }
}
~~~

Các lớp trên thuộc cùng ứng dụng Spring Boot và nằm trong phạm vi component scan. Những import chính gồm `HttpSecurity`, `SecurityFilterChain`, `Customizer`, `BearerTokenAuthentication`, `@Configuration`, `@Bean`, `@RestController` và `@GetMapping`.

Spring Boot có thể tự tạo introspector HTTP bằng cấu hình thuộc tính:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: resource-server
          client-secret: test-only-placeholder
~~~

Đây chỉ là cấu hình minh họa. Trong test, `@DynamicPropertySource` sẽ thay URI bằng HTTP server WireMock nội bộ và đặt thông tin client riêng cho test. Với ứng dụng thực, giữ client secret ngoài mã nguồn; một bean `OpaqueTokenIntrospector` tùy chỉnh có thể thay thế introspector tự cấu hình từ các thuộc tính trên.

## 4. MockMvc với WireMock: kiểm tra cả HTTP introspection

WireMock mô phỏng authorization server nhưng vẫn nhận **HTTP request thật từ introspector của Resource Server**. Test dưới đây dùng cấu hình và controller mục 3, tạo một server ở cổng ngẫu nhiên, rồi để Spring Boot dùng endpoint đó. Đặt class trong `src/test/java` của ứng dụng Spring Boot.

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OpaqueBearerMvcTest {

    private static final WireMockServer idp =
        new WireMockServer(wireMockConfig().dynamicPort());

    static {
        idp.start(); // Đã có cổng trước khi Boot đọc dynamic properties.
    }

    @DynamicPropertySource
    static void introspectionProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri",
            () -> idp.baseUrl() + "/oauth2/introspect");
        registry.add(
            "spring.security.oauth2.resourceserver.opaquetoken.client-id",
            () -> "resource-server");
        registry.add(
            "spring.security.oauth2.resourceserver.opaquetoken.client-secret",
            () -> "demo-secret");
    }

    @Autowired
    MockMvc mvc;

    @BeforeEach
    void resetServer() {
        idp.resetAll();
    }

    @AfterAll
    static void shutdown() {
        idp.stop();
    }

    private static void active(String token, String subject, String scopes) {
        idp.stubFor(post(urlEqualTo("/oauth2/introspect"))
            .withBasicAuth("resource-server", "demo-secret")
            .withFormParam("token", equalTo(token))
            .willReturn(okJson("""
                {
                  "active": true,
                  "sub": "%s",
                  "scope": "%s"
                }
                """.formatted(subject, scopes))));
    }

    private static void inactive(String token) {
        idp.stubFor(post(urlEqualTo("/oauth2/introspect"))
            .withBasicAuth("resource-server", "demo-secret")
            .withFormParam("token", equalTo(token))
            .willReturn(okJson("{\"active\":false}")));
    }

    @Test
    void bearerHeaderReallyCallsIntrospection() throws Exception {
        active("opaque-live-001", "alice", "profile.read");

        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-live-001"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("alice"));

        // Có bằng chứng HTTP POST đến introspection endpoint.
        idp.verify(1, postRequestedFor(urlEqualTo("/oauth2/introspect"))
            .withRequestBody(containing("token=opaque-live-001")));
    }

    @Test
    void inactiveTokenIsRejected() throws Exception {
        inactive("opaque-revoked-001");

        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer opaque-revoked-001"))
            .andExpect(status().isUnauthorized());

        idp.verify(1, postRequestedFor(urlEqualTo("/oauth2/introspect"))
            .withRequestBody(containing("token=opaque-revoked-001")));
    }

    @Test
    void activeTokenWithoutAdminScopeReturns403() throws Exception {
        active("opaque-read-only", "alice", "profile.read");

        mvc.perform(get("/api/admin")
                .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-read-only"))
            .andExpect(status().isForbidden());

        idp.verify(1, postRequestedFor(urlEqualTo("/oauth2/introspect")));
    }

    @Test
    void missingBearerDoesNotCallIntrospection() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());

        idp.verify(0, postRequestedFor(urlEqualTo("/oauth2/introspect")));
    }

    @Test
    void opaqueTokenMockBypassesIntrospection() throws Exception {
        mvc.perform(get("/api/profile")
                .with(opaqueToken()
                    .attributes(a -> a.put("sub", "mock-user"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("mock-user"));

        idp.verify(0, postRequestedFor(urlEqualTo("/oauth2/introspect")));
    }

    @Test
    void revokedBetweenRequestsIsRejectedOnSecondRequest()
            throws Exception {
        active("opaque-switch-001", "alice", "profile.read");

        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-switch-001"))
            .andExpect(status().isOk());

        idp.resetAll();
        inactive("opaque-switch-001");

        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-switch-001"))
            .andExpect(status().isUnauthorized());

        idp.verify(1, postRequestedFor(urlEqualTo("/oauth2/introspect")));
    }
}
~~~

Java 17+ hỗ trợ cú pháp text block ở ví dụ này. Khi đưa vào ứng dụng thật, bảo đảm context chỉ dùng introspector đích và Spring Security filter chain thật. Các phần mở rộng tùy chỉnh như cache, principal converter hoặc một filter chain khác có thể thay đổi đường xử lý; cần điều chỉnh test theo cấu hình ứng dụng.

Trong ca `bearerHeaderReallyCallsIntrospection`, phép kiểm tra `200` là chưa đủ: câu lệnh `idp.verify(...)` chứng minh introspector đã phát ra request mang **đúng giá trị token**. WireMock stub chỉ trả JSON `active=true` khi endpoint, Basic credentials và trường form `token` đúng. Điều đó kiểm tra thêm cả cấu hình client xác thực với authorization server.

Ca `activeTokenWithoutAdminScopeReturns403` cho thấy introspection đã thành công, nhưng `scope=profile.read` không cấp `SCOPE_admin`. Ca `opaqueTokenMockBypassesIntrospection` là đối chứng: có thể vẫn nhận `200`, nhưng HTTP introspection nhận **0 request**. Ca `revokedBetweenRequestsIsRejectedOnSecondRequest` minh họa việc token hết hiệu lực giữa hai yêu cầu; kết quả này giả định không có cache introspection tùy biến ở Resource Server.

## 5. Khi chỉ cần xác minh filter gọi introspector

Nếu bài kiểm thử chỉ cần chứng minh **chuỗi bearer được chuyển đúng vào interface introspector** mà chưa cần kiểm tra HTTP đến IdP, có thể thay introspector bằng một đối tượng ghi nhận lời gọi:

~~~java
final class RecordingIntrospector implements OpaqueTokenIntrospector {
    private final List<String> received = new CopyOnWriteArrayList<>();

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        received.add(token);
        if (!token.equals("opaque-known-001")) {
            throw new BadOpaqueTokenException("inactive");
        }
        return new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            Map.of("sub", "alice", "scope", "profile.read"),
            List.of(new SimpleGrantedAuthority("SCOPE_profile.read")));
    }

    List<String> receivedTokens() {
        return List.copyOf(received);
    }
}

@TestConfiguration
class RecordingIntrospectionConfig {
    @Bean
    RecordingIntrospector introspector() {
        return new RecordingIntrospector();
    }
}
~~~

Import cấu hình này vào **một lớp kiểm thử tích hợp riêng**, bảo đảm bean `RecordingIntrospector` được Resource Server sử dụng. Khi test gọi:

~~~java
mvc.perform(get("/api/profile")
        .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-known-001"))
    .andExpect(status().isOk());

assertThat(recordingIntrospector.receivedTokens())
    .containsExactly("opaque-known-001");
~~~

...thì test đã kiểm tra được Bearer header → filter → introspector. Tuy vậy, loại test này **chưa kiểm tra** body form, Basic credentials, thời gian chờ, lỗi HTTP và parsing JSON. Không trộn bean này với introspector HTTP của WireMock trong cùng test context khi không có cơ chế chọn bean rõ ràng.

`BadOpaqueTokenException` là ngoại lệ dành cho opaque token không hợp lệ trong tầng introspection. Việc dùng nó trong fake introspector giúp mô phỏng token bị từ chối mà không gọi authorization server.

## 6. WebFlux: dùng WebTestClient để đi qua Reactive introspector

Ứng dụng Reactive dùng `SecurityWebFilterChain` và `ReactiveOpaqueTokenIntrospector`:

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveOpaqueSecurity {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/profile")
                    .hasAuthority("SCOPE_profile.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}

@RestController
class ReactiveProfileController {
    @GetMapping("/api/profile")
    Mono<Map<String, String>> profile(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(Map.of("subject", principal.getName()));
    }
}
~~~

Tương tự Servlet, khi Spring Boot có các thuộc tính `spring.security.oauth2.resourceserver.opaquetoken.introspection-uri`, `client-id`, `client-secret`, một ứng dụng WebFlux có thể tự tạo introspector HTTP Reactive. Trong test có thể cho Reactive Resource Server sử dụng WireMock với `@DynamicPropertySource` như mục 4. Những lời gọi WebTestClient sau đó **không** dùng `mockOpaqueToken()`:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.main.web-application-type=reactive"
)
@AutoConfigureWebTestClient
class ReactiveOpaqueBearerTest {

    @Autowired
    WebTestClient client;

    // Trước test, cấu hình WireMock và DynamicPropertySource
    // như phần Servlet: opaque-reactive-live -> active=true,
    // sub=bob, scope=profile.read;
    // opaque-reactive-revoked -> active=false.

    @Test
    void activeBearerIsAcceptedThroughReactiveIntrospection() {
        client.get()
            .uri("/api/profile")
            .headers(h -> h.setBearerAuth("opaque-reactive-live"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("bob");

        // Kiểm tra WireMock đã nhận POST chứa token này.
    }

    @Test
    void inactiveBearerIsRejected() {
        client.get()
            .uri("/api/profile")
            .headers(h -> h.setBearerAuth("opaque-reactive-revoked"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Phần test Reactive minh họa request và assertion; để chạy độc lập, bổ sung fixture WireMock và dynamic properties tương tự mục 4, đồng thời sử dụng ứng dụng WebFlux có hai class `ReactiveOpaqueSecurity` và `ReactiveProfileController`. Trong ứng dụng chứa cả MVC lẫn WebFlux dependency, thuộc tính `spring.main.web-application-type=reactive` giúp tránh vô tình chạy test trên Servlet stack.

Khi chỉ muốn kiểm tra đường Bearer → introspector Reactive mà không tạo HTTP server, có thể dùng một bean test:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector reactiveIntrospector() {
    return token -> {
        if ("opaque-reactive-live".equals(token)) {
            return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                "bob",
                Map.of("sub", "bob"),
                List.of(new SimpleGrantedAuthority("SCOPE_profile.read"))));
        }
        return Mono.error(new BadOpaqueTokenException("inactive"));
    };
}
~~~

`ReactiveOpaqueTokenIntrospector.introspect(token)` trả `Mono<OAuth2AuthenticatedPrincipal>`. Có thể dùng `AtomicReference<String>` hoặc spy để xác nhận giá trị token mà WebTestClient đã gửi đi đến introspector. Đây là kiểm thử đường xác thực trong ứng dụng, chưa phải kiểm thử request HTTP từ introspector đến IdP.

Ngược lại, `mockOpaqueToken()` của Spring Security Test tạo trước authentication cho Reactive test. Nó hữu ích khi cần tập trung vào quyền và logic controller, nhưng không chứng minh bearer token đã qua introspection.

## 7. Bộ ca kiểm thử nên có

| Ca | Cách tạo input | Kỳ vọng / bằng chứng |
| --- | --- | --- |
| Không có bearer | GET endpoint bảo vệ không có `Authorization` | `401`; introspector 0 lần |
| Token active đủ scope | Bearer token; IdP trả `active=true` và đúng `scope` | `200`; introspection được gọi với đúng token |
| Token inactive/đã thu hồi | Bearer token; IdP trả `active=false` | `401`; introspection được gọi |
| Token active thiếu scope | Bearer token đủ xác thực nhưng thiếu authority | `403`; không nhầm với `401` |
| Giả lập authentication | `opaqueToken()` hoặc `mockOpaqueToken()` | Test phân quyền, không có introspection thật |
| Sai Bearer scheme | `Authorization: Basic ...` tới API chỉ nhận Bearer | Không xác thực bằng introspector opaque-token |
| Bearer header sai định dạng | Header trống, nhiều token xung đột | Bị từ chối theo bearer resolver; không phải mọi trường hợp đều tới introspector |
| IdP trả 503 / timeout | WireMock giả lập lỗi dịch vụ | Không cấp quyền khi chưa xác thực; ghi nhận HTTP status theo policy |
| Token đổi trạng thái | Cùng giá trị lần 1 `active=true`, lần 2 `active=false` | Thu hồi có hiệu lực theo chính sách cache/introspection |

Với ứng dụng có xác thực bằng nhiều phương thức (session, Basic, Bearer...), một yêu cầu vẫn có thể thành công qua phương thức khác nếu kiểm thử không cô lập đúng filter chain. Cần xác nhận API đang kiểm thử thực sự yêu cầu Bearer Resource Server và không nhận một identity được gắn sẵn bởi fixture.

Nếu viết test `POST`, `PUT` hoặc `DELETE` trên Servlet, hãy tính đến CSRF. Lỗi `403` có thể do thiếu CSRF token nếu cấu hình bật CSRF, và không chứng minh introspection đã thất bại. Những ví dụ ở đây dùng `GET` để tập trung vào bearer authentication và authorization.

Các thay đổi lớn trong ứng dụng như custom authority converter, cache introspection, bổ sung kiểm tra audience hoặc một introspector nhiều nguồn cũng cần test riêng. Một phản hồi `active=true` chưa tự động chứng minh token phù hợp với mọi API; endpoint vẫn phải thực thi quyền và policy liên quan.

## 8. Lỗi thường gặp khi viết test

**Chỉ assert HTTP `200`.** Một request có `@WithMockUser` hoặc `opaqueToken()` cũng có thể cho `200`. Nên kết hợp assertion HTTP với kiểm tra introspector đã nhận token hoặc WireMock đã nhận `POST`.

**Mock introspector rồi tuyên bố đã kiểm tra kết nối IdP.** Mockito hoặc recording fake chỉ kiểm tra đường gọi interface, không kiểm tra client credentials, HTTP body, timeout và phản hồi mạng. Muốn kiểm chứng mạng, dùng WireMock hoặc môi trường tích hợp kiểm soát được.

**Nhầm header client → API với API → IdP.** Client gửi `Authorization: Bearer <token>`. Khi introspect, Resource Server có thể gửi HTTP Basic bằng client ID/secret tới IdP và token trong form body. Hai authentication này phục vụ hai mục đích khác nhau.

**Gọi IdP thực trong mọi unit/integration test.** Điều đó gây phụ thuộc token sống, network, rate limit và dữ liệu ngoài. Dùng token opaque thử nghiệm và introspection server cục bộ để có kết quả xác định; dành kiểm thử IdP thật cho môi trường integration được quản lý riêng.

**Nhầm `active=false` với thiếu scope.** `active=false` là thất bại xác thực, thường trả `401`. `active=true` mà thiếu `SCOPE_admin` là thất bại authorization, thường trả `403`.

**Giả định tất cả token đều là JWT.** Chế độ opaque-token dùng introspection, không yêu cầu token có ba phần được ngăn bằng dấu chấm. Đừng dùng `jwt()` để chứng minh chuỗi opaque đã đi qua introspector.

**Bỏ qua cache và cơ chế thu hồi.** Một custom introspector hoặc gateway có thể cache kết quả. Khi cần kiểm tra revocation, hãy định nghĩa TTL và thời điểm cache bị làm mới; không mặc định mọi hệ thống đều hỏi IdP ở mỗi request.

**Quên kiểm tra lỗi hạ tầng.** Nếu IdP trả lỗi hoặc timeout, Resource Server phải chặn yêu cầu chưa xác thực. Mã HTTP quan sát được có thể khác theo cấu hình exception handler; nên ghi rõ kỳ vọng trước khi cố định assertion.

## 9. Thực hành

1. Dùng WireMock trả `active=true` với `sub=alice` và `scope=profile.read` cho token `opaque-live-001`. Gửi Bearer header bằng MockMvc, assert `200` và xác minh đúng giá trị token trong POST introspection.
2. Dùng `opaque-revoked-001` nhận `active=false`. Assert `401` và xác minh introspection đã được gọi đúng một lần.
3. Dùng token hợp lệ chỉ có scope `profile.read` gọi `/api/admin` yêu cầu `SCOPE_admin`. Assert `403` và giải thích khác biệt với ca token inactive.
4. Viết một test với `opaqueToken()` có cùng `sub` và scope, sau đó assert WireMock nhận **0 request**. Nêu phạm vi test này kiểm chứng được và chưa kiểm chứng được.
5. Thay introspection server bằng `RecordingIntrospector` để xác nhận đúng chuỗi Bearer đã đến interface. So sánh với test WireMock khi cần kiểm tra thêm HTTP Basic và form body.
6. Với WebFlux, gửi header qua `WebTestClient`, dùng `ReactiveOpaqueTokenIntrospector` hoặc WireMock để chứng minh token được introspect. Sau đó thử `mockOpaqueToken()` và nhận xét sự khác biệt.
7. Cấu hình WireMock đổi token từ `active=true` sang `active=false` giữa hai request. Quan sát hành vi khi không cache và khi có cache introspection.
8. Cho WireMock trả HTTP 503 hoặc body sai. Xác minh ứng dụng không cho truy cập khi chưa xác thực, đồng thời ghi nhận status/error contract của dự án.

Người học hoàn thành bài khi tự chứng minh được chuỗi **HTTP Bearer header → security filter → introspector → kết quả active/authorities → quyết định truy cập**. `opaqueToken()` và `mockOpaqueToken()` vẫn phù hợp cho kiểm thử authorization, còn request Bearer qua introspector mới kiểm tra đường xác thực token.

### Tài liệu tham khảo

- [Spring Security — Servlet Resource Server: Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — MockMvc Testing Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Reactive Resource Server: Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/)
