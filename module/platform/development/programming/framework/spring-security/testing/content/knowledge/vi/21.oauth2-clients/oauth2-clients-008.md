# Xác minh Authorization header trên yêu cầu gửi đi

Khi ứng dụng Spring Security đóng vai trò **OAuth2 Client**, nó có thể nhận một HTTP request từ người dùng rồi gọi tiếp một API khác với **access token**. Khi kiểm thử bằng `spring-security-test`, điều cần chứng minh không chỉ là controller trả `200 OK`: phải kiểm tra **HTTP request được gửi tới dịch vụ downstream có header `Authorization` đúng hay không**.

Đây là một ranh giới khác với kiểm thử xác thực của request **đi vào** ứng dụng. `@WithMockUser`, `oauth2Login()` hoặc `oidcLogin()` có thể tạo authentication giả cho caller, nhưng bản thân chúng **không chứng minh** OAuth2 Client lấy token, chọn đúng `ClientRegistration` và gắn `Authorization: Bearer ...` lên request **đi ra**.

Trong module **SPRING_SECURITY_TESTING**, bài học dùng `MockMvc` để khởi phát request Servlet, `OAuth2AuthorizedClientManager` và `WebClient` để thực hiện lời gọi OAuth2, rồi dùng WireMock kiểm chứng chính xác header mà HTTP server phía nhận quan sát được. Phần mở rộng giới thiệu kiểm thử cấp phát token `client_credentials`, lỗi token, cách hạn chế token rò rỉ và mối liên hệ với WebFlux.

## 1. Đầu vào và đầu ra là hai ranh giới bảo mật độc lập

Giả sử người dùng `alice` gọi một ứng dụng báo cáo:

```http
GET /proxy/reports HTTP/1.1
Host: frontend.example.test
Cookie: SESSION=...
```

Ứng dụng sau đó gọi API nội bộ:

```http
GET /internal/reports HTTP/1.1
Host: reports.example.test
Authorization: Bearer <outbound-access-token>
```

Header `Authorization` thứ hai được tạo trong **HTTP client của ứng dụng**. Token thường đến từ một `OAuth2AuthorizedClient` do `OAuth2AuthorizedClientManager` cung cấp. Tùy grant type, token có thể thuộc client ứng dụng (`client_credentials`) hoặc thay mặt người dùng đã ủy quyền (`authorization_code`). Nó **không mặc nhiên giống** credential của HTTP request đầu vào.

```mermaid
sequenceDiagram
    participant Caller as Người dùng / MockMvc
    participant App as Servlet controller
    participant OAuth as OAuth2AuthorizedClientManager
    participant IdP as Authorization Server
    participant Api as Downstream API / WireMock
    Caller->>App: GET /proxy/reports
    App->>OAuth: authorize(registrationId, principal)
    opt Chưa có authorized client hoặc cần token mới
        OAuth->>IdP: Lấy/refresh access token
        IdP-->>OAuth: Access token
    end
    OAuth-->>App: OAuth2AuthorizedClient
    App->>Api: GET /internal/reports + Authorization: Bearer token
    Api-->>App: Response
    App-->>Caller: HTTP response
    Note over Caller,Api: Test phải quan sát HTTP request đi ra
```

Một số khái niệm cần phân biệt:

| Thành phần | Vai trò | Điều cần kiểm tra |
| --- | --- | --- |
| `SecurityContext` / `@WithMockUser` | Danh tính của caller trong ứng dụng | Quyền gọi endpoint Servlet |
| `ClientRegistration` | Cấu hình OAuth2 client: grant, client id, token URI, scopes | Ứng dụng chọn đúng registration |
| `OAuth2AuthorizedClient` | Client registration và access token hiện có cho một principal | Token nào được chọn để dùng |
| `OAuth2AuthorizedClientManager` | Lấy mới, tái dùng hoặc gia hạn authorized client theo cấu hình | Có được gọi với registration/principal mong đợi |
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | Tích hợp authorized client với `WebClient` trong ứng dụng Servlet | Header Bearer được gắn lên outbound request |
| HTTP downstream / WireMock | Nơi thực sự nhận request của ứng dụng | Đúng URI, method và `Authorization` header |

**Kết luận về bằng chứng:** assertion `status().isOk()` trên `MockMvc` chỉ quan sát response của ứng dụng. Nếu mục tiêu là kiểm tra header gửi đi, cần assertion ngay tại request outbound, chẳng hạn `WireMock.verify(...withHeader(...))` hoặc `MockWebServer.takeRequest().getHeader(...)`.

## 2. Cấu hình mẫu cho một ứng dụng OAuth2 Client trên Servlet

Ví dụ bên dưới dựa trên Spring Boot 3.x, Java 17+, Spring Security OAuth2 Client, Spring MVC, `WebClient` và JUnit 5. Các đoạn Java lược bỏ `package`/`import`. Vì `WebClient` có API nonblocking nhưng ta dùng một controller Servlet đơn giản, ví dụ gọi `block()` để trình bày luồng đồng bộ; dự án thực có thể chọn `RestClient` hoặc thiết kế bất đồng bộ theo nhu cầu.

Dependency Gradle chính:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'

    // Chọn phiên bản WireMock 3 tương thích với môi trường build.
    testImplementation 'org.wiremock:wiremock:3.10.0'
}
```

Khi có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường chọn ứng dụng Servlet theo MVC, còn `WebClient` được dùng ở vai trò HTTP client.

Đăng ký OAuth2 client theo `client_credentials`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-client:
            provider: reports-provider
            client-id: reports-api
            client-secret: TEST_OR_ENV_SECRET
            authorization-grant-type: client_credentials
            scope: reports.read
        provider:
          reports-provider:
            token-uri: https://auth.example.test/oauth2/token

reports:
  base-url: https://reports.example.test
```

Các URL/credential ở đây là ví dụ, không phải endpoint hay secret hoạt động. Trong triển khai thật, đưa secret vào cấu hình bảo mật của môi trường thay vì lưu cố định. Với grant `client_credentials`, ứng dụng lấy token nhân danh chính OAuth2 client; nếu bạn muốn gọi API thay mặt người dùng, cần chọn luồng ủy quyền và quản lý authorized client tương ứng.

### 2.1. Khai báo AuthorizedClientManager

Trong ứng dụng Servlet, một `DefaultOAuth2AuthorizedClientManager` có thể quản lý OAuth2 authorized clients với `ClientRegistrationRepository` và `OAuth2AuthorizedClientRepository`:

```java
@Configuration
class OAuth2ClientConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        var manager = new DefaultOAuth2AuthorizedClientManager(
            registrations,
            authorizedClients
        );

        manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build()
        );

        return manager;
    }

    @Bean
    WebClient reportsWebClient(
            WebClient.Builder builder,
            OAuth2AuthorizedClientManager manager,
            @Value("${reports.base-url}") String baseUrl) {

        var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
            manager
        );

        return builder
            .baseUrl(baseUrl)
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
```

`ServletOAuth2AuthorizedClientExchangeFilterFunction` lấy `OAuth2AuthorizedClient` qua manager rồi thêm access token vào header Bearer của request do `WebClient` thực hiện. Manager ở đây là một bean rõ ràng để test có thể thay bằng mock **chỉ trong bài kiểm thử cấp adapter**; ở bài kiểm thử cấp phát token thật ta sẽ giữ manager thật.

### 2.2. Gọi downstream với registration ID cụ thể

Tạo gateway và controller:

```java
@Service
class ReportsGateway {

    private final WebClient reportsWebClient;

    ReportsGateway(@Qualifier("reportsWebClient") WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    String fetchCurrentReport() {
        return reportsWebClient.get()
            .uri("/internal/reports")
            .attributes(
                ServletOAuth2AuthorizedClientExchangeFilterFunction
                    .clientRegistrationId("reports-client")
            )
            .retrieve()
            .bodyToMono(String.class)
            .block();
    }
}

@RestController
class ReportsProxyController {

    private final ReportsGateway gateway;

    ReportsProxyController(ReportsGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/proxy/reports")
    String proxy() {
        return gateway.fetchCurrentReport();
    }
}
```

Gọi `clientRegistrationId("reports-client")` trên từng request làm rõ chính xác client nào được dùng. Đây là lựa chọn quan trọng khi ứng dụng có nhiều client registration: test có thể khẳng định việc chọn token đúng, không vô tình dùng một client mặc định.

Với ứng dụng Servlet bảo vệ HTTP, một filter chain tối thiểu:

```java
@Configuration
class HttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/proxy/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Trong bài kiểm thử, `@WithMockUser(username = "alice")` sẽ đưa người dùng đã xác thực vào `SecurityContext` để request đi đến controller. Nó chỉ mô phỏng **inbound authentication**; token outbound vẫn do manager và filter function quyết định.

## 3. Bài kiểm thử chính: dùng MockMvc và WireMock xác minh header gửi đi

Ta muốn chứng minh ba điều cùng lúc:

1. Request `MockMvc` vào `/proxy/reports` được ứng dụng xử lý.
2. `OAuth2AuthorizedClientManager` chọn authorized client cho registration `reports-client`.
3. WireMock thực sự nhận request outbound với header **chính xác** `Authorization: Bearer test-access-token`.

Để tách mục tiêu này khỏi việc gọi token endpoint, test **mock manager**, trả về `OAuth2AuthorizedClient` chứa access token kiểm thử. Phần `WebClient` và HTTP outbound vẫn chạy thật.

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportsOutgoingAuthorizationHeaderTest {

    private static final WireMockServer downstream =
        new WireMockServer(
            WireMockConfiguration.options().dynamicPort()
        );

    static {
        downstream.start();
    }

    @Autowired MockMvc mvc;

    @MockitoBean OAuth2AuthorizedClientManager manager;

    @DynamicPropertySource
    static void downstreamProperties(DynamicPropertyRegistry registry) {
        registry.add("reports.base-url", downstream::baseUrl);
    }

    @BeforeEach
    void resetDownstream() {
        downstream.resetAll();
    }

    @AfterAll
    static void stopDownstream() {
        downstream.stop();
    }

    private static OAuth2AuthorizedClient authorizedClient(String tokenValue) {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("reports-client")
                .clientId("test-client")
                .clientSecret("test-only-secret")
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS
                )
                .tokenUri("https://auth.example.test/oauth2/token")
                .build();

        Instant now = Instant.now();

        OAuth2AccessToken token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            tokenValue,
            now.minusSeconds(10),
            now.plusSeconds(300),
            Set.of("reports.read")
        );

        return new OAuth2AuthorizedClient(registration, "alice", token);
    }

    @Test
    @WithMockUser(username = "alice")
    void sendsBearerHeaderToDownstreamApi() throws Exception {
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
            .thenReturn(authorizedClient("test-access-token"));

        downstream.stubFor(get(urlEqualTo("/internal/reports"))
            .withHeader(
                HttpHeaders.AUTHORIZATION,
                equalTo("Bearer test-access-token")
            )
            .willReturn(okJson("""
                {"report":"available"}
                """))
        );

        mvc.perform(get("/proxy/reports"))
            .andExpect(status().isOk())
            .andExpect(content().json("""
                {"report":"available"}
                """));

        verify(manager).authorize(argThat(request ->
            request != null
                && "reports-client".equals(request.getClientRegistrationId())
        ));

        downstream.verify(1,
            getRequestedFor(urlEqualTo("/internal/reports"))
                .withHeader(
                    HttpHeaders.AUTHORIZATION,
                    equalTo("Bearer test-access-token")
                )
        );

        downstream.verify(1,
            getRequestedFor(urlEqualTo("/internal/reports"))
        );
    }

    @Test
    void anonymousCallerCannotTriggerOutboundCall() throws Exception {
        mvc.perform(get("/proxy/reports"))
            .andExpect(status().isUnauthorized());

        downstream.verify(0,
            getRequestedFor(urlEqualTo("/internal/reports"))
        );
        verifyNoInteractions(manager);
    }
}
```

Các static import quan trọng:

```java
import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

`@WithMockUser` được import từ `org.springframework.security.test.context.support.WithMockUser`. Các annotation/test utility còn lại sử dụng import Java, JUnit, Spring và WireMock tương ứng. Trong Spring Framework 6.2+ dùng `@MockitoBean`; với Spring Boot cũ hơn chưa hỗ trợ annotation này, thay bằng `@MockBean` của Spring Boot. Với `httpBasic()` trong cấu hình mẫu, request không xác thực nhận `401` và bị chặn trước khi có lời gọi outbound.

**Cách đọc kết quả:** nếu test trên PASS, ta biết `WebClient` của ứng dụng đã gửi HTTP request tới WireMock với header Bearer đúng. Dù manager là mock, filter function và HTTP client thật vẫn quyết định cách tạo header. Không có token endpoint nào được gọi trong test này.

### Vì sao cần kiểm tra cả số lượng request?

Nếu chỉ stub:

```java
downstream.stubFor(get(urlEqualTo("/internal/reports"))
    .willReturn(okJson("{}")));
```

và chỉ assert `200`, ứng dụng có thể vô tình gửi request **không có Authorization header** nhưng vẫn nhận response hợp lệ. Khi stub yêu cầu `withHeader(...)`, lời gọi thiếu header sẽ không khớp. Dùng `downstream.verify(1, getRequestedFor(...).withHeader(...))` còn khẳng định giá trị và vị trí header; kiểm tra tổng số request bảo đảm không có request thứ hai không được kiểm tra.

Khi test có nhiều HTTP call, hãy kiểm tra từng endpoint/host và token tương ứng. Header được xác minh ở **đích HTTP**, không chỉ ở object `OAuth2AuthorizedClient`.

## 4. Cần tách rõ “token được cấp” và “token được gắn vào request”

Test ở mục 3 **mock `OAuth2AuthorizedClientManager`** nên không chứng minh luồng `client_credentials` chạy thành công. Nó chứng minh tầng gắn access token vào outbound request.

Để kiểm chứng cả việc lấy token, hãy dùng **manager thật** và hai HTTP stub riêng trong cùng test server (hoặc hai WireMock server):

- `POST /oauth2/token` đóng vai Authorization Server thử nghiệm.
- `GET /internal/reports` đóng vai downstream Resource Server thử nghiệm.

Khi gọi proxy, application phải lấy access token rồi gửi sang API với Bearer header.

Ví dụ cấu hình test (đặt trên test class không có `@MockitoBean OAuth2AuthorizedClientManager`):

```java
@DynamicPropertySource
static void oauth2TestEndpoints(DynamicPropertyRegistry registry) {
    registry.add("reports.base-url", downstream::baseUrl);

    registry.add(
        "spring.security.oauth2.client.provider.reports-provider.token-uri",
        () -> downstream.baseUrl() + "/oauth2/token"
    );

    registry.add(
        "spring.security.oauth2.client.registration.reports-client.client-id",
        () -> "test-client"
    );

    registry.add(
        "spring.security.oauth2.client.registration.reports-client.client-secret",
        () -> "test-secret"
    );

    registry.add(
        "spring.security.oauth2.client.registration.reports-client.authorization-grant-type",
        () -> "client_credentials"
    );

    registry.add(
        "spring.security.oauth2.client.registration.reports-client.provider",
        () -> "reports-provider"
    );
}
```

Với `DefaultOAuth2AuthorizedClientManager` thật từ mục 2, test có thể stub token response như sau:

```java
downstream.stubFor(post(urlEqualTo("/oauth2/token"))
    .withBasicAuth("test-client", "test-secret")
    .withRequestBody(containing("grant_type=client_credentials"))
    .willReturn(okJson("""
        {
          "access_token": "token-from-test-idp",
          "token_type": "Bearer",
          "expires_in": 300,
          "scope": "reports.read"
        }
        """))
);

downstream.stubFor(get(urlEqualTo("/internal/reports"))
    .withHeader(
        "Authorization", equalTo("Bearer token-from-test-idp")
    )
    .willReturn(okJson("""
        {"report":"available"}
        """))
);

mvc.perform(get("/proxy/reports")
        .with(user("alice")))
    .andExpect(status().isOk());

downstream.verify(1, postRequestedFor(urlEqualTo("/oauth2/token")));
downstream.verify(1, getRequestedFor(urlEqualTo("/internal/reports"))
    .withHeader(
        "Authorization", equalTo("Bearer token-from-test-idp")
    )
);
```

Lưu ý: đây là **phần mở rộng trong một test class riêng**, có cấu hình token URI riêng, không ghép trực tiếp vào class đã mock manager ở mục 3. Test manager thật cần `ClientRegistrationRepository`, `OAuth2AuthorizedClientRepository` và filter chain cấu hình đúng; nếu đã có authorized client trong repository hoặc cache, hãy cô lập trạng thái để lần gọi được quan sát là lần lấy token đầu tiên.

**Phạm vi chứng minh:** token endpoint ở đây vẫn là WireMock. Test đã đi qua HTTP token request và HTTP downstream request, nhưng token là fixture do server kiểm thử cấp. Muốn xác minh tích hợp Authorization Server thật, cần thêm một integration test với môi trường thử nghiệm và credentials/token thật của môi trường đó.

## 5. Các tình huống test cần bổ sung

### 5.1. Thiếu authorization: không được tự động bỏ qua

Khi manager không lấy được authorized client, client có thể không gửi Bearer header, ném exception hoặc trả lỗi tùy cấu hình hiện hành. Hãy thiết kế test theo **hành vi mong muốn của ứng dụng**.

Ví dụ, một API nội bộ bắt buộc OAuth2 authentication không nên âm thầm trả báo cáo với request không có header. Nếu downstream yêu cầu:

```http
Authorization: Bearer test-access-token
```

thì test có thể stub mọi request **không có header** trả `401`, và xác minh handler phía ứng dụng xử lý lỗi đúng chính sách.

### 5.2. Sai token cho sai dịch vụ

Với nhiều client registration, hãy kiểm tra đúng mapping:

| Downstream | Client registration | Header mong đợi |
| --- | --- | --- |
| Reports API | `reports-client` | `Bearer reports-access-token` |
| Billing API | `billing-client` | `Bearer billing-access-token` |
| Endpoint công khai không yêu cầu OAuth2 | Không dùng authorized client | Không có `Authorization` của OAuth2 Client |

Một test chỉ xác nhận header bắt đầu bằng `Bearer ` không phát hiện việc ứng dụng gửi nhầm token của Billing sang Reports. Khi có thể, so sánh **exact token fixture** và URI đích.

Đừng dùng `setDefaultOAuth2AuthorizedClient(true)` một cách không kiểm soát trên HTTP client được dùng gọi nhiều host. Cơ chế dùng authorized client mặc định có thể gắn access token lên cả request không cần quyền đó. Ưu tiên cấu hình client rõ ràng cho từng downstream và bổ sung negative tests với endpoint khác.

### 5.3. Không làm rò rỉ inbound Authorization header

Một ứng dụng có thể nhận Bearer token của caller từ `Authorization` đầu vào, nhưng OAuth2 client outbound theo `client_credentials` nên dùng token của chính ứng dụng. **Không mặc nhiên relay token của caller** sang downstream.

Một test tốt có thể tạo:

- Inbound credential kiểm thử: `inbound-user-token` hoặc một `SecurityContext` giả.
- Manager trả token outbound: `outbound-service-token`.
- WireMock bắt buộc header `Authorization: Bearer outbound-service-token`.
- WireMock xác minh không gửi `Bearer inbound-user-token` tới API không được thiết kế để nhận token người dùng.

Token relay là một quyết định kiến trúc riêng. Nếu nghiệp vụ thực sự cần token của caller, phải kiểm tra audience, scopes, trust boundary và cơ chế relay/đổi token được hệ thống hỗ trợ, thay vì tự sao chép header từ inbound request.

### 5.4. Token hết hạn hoặc cấp lại

Một `OAuth2AuthorizedClientManager` thực có thể tái sử dụng token chưa hết hạn hoặc xin token mới khi cần. Nếu chỉ mock manager trả token còn hạn, test ở mục 3 **không chứng minh refresh token hoặc client_credentials renewal**.

Để kiểm thử vòng đời token, tạo một fake token endpoint có thể trả lần lượt `token-A` rồi `token-B`, sử dụng manager thật, cô lập repository/cache và điều khiển thời gian hết hạn phù hợp. Kiểm tra cả token request và Bearer header downstream tương ứng; không nên dùng `Thread.sleep` tùy tiện làm test chậm hoặc không ổn định.

### 5.5. Bị từ chối bởi downstream

Nếu downstream nhận header đúng nhưng trả `401 Unauthorized`, đó chưa phải bằng chứng OAuth2 Client không gắn token. Có thể token sai audience, hết hạn, bị thu hồi hoặc Resource Server không tin issuer.

Một test có thể stub downstream trả `401` và vẫn dùng WireMock khẳng định header đã được gửi đúng. Khi đó kiểm tra cách ứng dụng xử lý exception `WebClientResponseException.Unauthorized`, retry hoặc báo lỗi theo contract. Không biến toàn bộ lỗi downstream thành lỗi thiếu header.

### 5.6. Chỉ gửi token đến đích được phép

Bearer token là thông tin nhạy cảm: bên nhận được token có thể dùng nó theo quyền được cấp. Kiểm tra URI/host thực sự được gọi; tránh forward header đến host không tin cậy, không ghi token thực vào application logs, test reports hay console CI. Nếu HTTP client tự follow redirect, cần xem rõ policy giữ/bỏ `Authorization` khi redirect sang host khác.

## 6. Phân biệt các helper của spring-security-test

| Helper | Mô phỏng điều gì? | Tự chứng minh outbound Authorization header? |
| --- | --- | --- |
| `@WithMockUser` | `Authentication` dạng user trong `SecurityContext` | Không |
| `user("alice")` của MockMvc | Principal giả cho một HTTP request vào ứng dụng | Không |
| `oauth2Login()` | Người dùng đăng nhập qua OAuth2/OIDC client với `OAuth2AuthenticationToken` | Không |
| `oidcLogin()` | `OidcUser` và trạng thái login OIDC giả | Không |
| `oauth2Client()` | Authorized client giả gắn với context của MockMvc request | Không; phải kiểm tra HTTP outbound |
| `jwt()` / `opaqueToken()` | Authentication giả của Resource Server để kiểm tra inbound authorization | Không |
| Mock `OAuth2AuthorizedClientManager` | Authorized client/token do Mockito trả về | Chỉ khi HTTP client thực thi và test quan sát header outbound |
| WireMock / MockWebServer / MockRestServiceServer | Quan sát request gửi bởi HTTP client | Có, trong phạm vi HTTP client/test được chạy |

Ví dụ dễ hiểu: test sau chỉ cho thấy user giả có thể truy cập controller:

```java
@Test
@WithMockUser(username = "alice")
void controllerReturnsOk() throws Exception {
    mvc.perform(get("/proxy/reports"))
        .andExpect(status().isOk());
}
```

Nếu controller bị mock hoặc downstream stub luôn trả thành công, bài test có thể xanh dù `Authorization` outbound bị thiếu. Khi mục tiêu là **header gửi đi**, phải bổ sung assertion tại điểm nhận HTTP:

```java
downstream.verify(1,
    getRequestedFor(urlEqualTo("/internal/reports"))
        .withHeader(
            "Authorization",
            equalTo("Bearer test-access-token")
        )
);
```

## 7. WebClient, RestClient và WebTestClient: chọn đúng ranh giới

Ví dụ chính dùng `WebClient` trong Servlet app. Với Spring Security phiên bản hỗ trợ `OAuth2ClientHttpRequestInterceptor` (ví dụ Spring Security 6.4+), `RestClient` cũng có thể tự đính token. Cách tiếp cận tương tự: cấp manager, chỉ định registration, rồi dùng `MockRestServiceServer` hoặc WireMock để assert header thực tế.

Phác họa cấu hình `RestClient`:

```java
@Bean
RestClient reportsRestClient(
        RestClient.Builder builder,
        OAuth2AuthorizedClientManager manager,
        @Value("${reports.base-url}") String baseUrl) {

    var oauth2Interceptor =
        new OAuth2ClientHttpRequestInterceptor(manager);

    return builder
        .baseUrl(baseUrl)
        .requestInterceptor(oauth2Interceptor)
        .build();
}
```

Khi gọi bằng `RestClient`, sử dụng request attribute chỉ định client registration theo API phiên bản đang dùng (chẳng hạn `RequestAttributeClientRegistrationIdResolver.clientRegistrationId("reports-client")`). Không nên chỉ gọi trực tiếp `RestClient.create()` rồi giả định OAuth2 interceptor đã được đăng ký.

Đối với WebFlux, sử dụng `ServerOAuth2AuthorizedClientExchangeFilterFunction` cùng `ReactiveOAuth2AuthorizedClientManager` hoặc các thành phần reactive phù hợp; đây là một hệ thống khác với Servlet manager. `WebTestClient` kiểm thử request vào WebFlux, nhưng vẫn cần WireMock/MockWebServer để quan sát HTTP request đi ra từ reactive HTTP client.

**Lưu ý:** `WebTestClient` có thể được dùng để gọi một server thật hoặc bind vào application context. Điều đó không tự động biến nó thành công cụ quan sát outbound request; phải kiểm tra phía downstream hoặc ở connector của HTTP client.

## 8. Bài thực hành và ma trận kiểm tra

Hãy tạo một request `GET /proxy/reports` cho người dùng `alice`. Yêu cầu của ứng dụng là dùng OAuth2 client `reports-client` gọi `GET /internal/reports`.

1. **Khởi tạo** Spring Boot Servlet với `SecurityFilterChain`, `OAuth2AuthorizedClientManager`, `WebClient` và controller/gateway ở mục 2.
2. **Mock authorized client** trả token `test-access-token`. Stub WireMock nhận `GET /internal/reports` chỉ khi header chính xác `Authorization: Bearer test-access-token`. Dùng MockMvc phát request và khẳng định `200`.
3. **Đọc bằng chứng**: verify manager được gọi với registration `reports-client` và WireMock nhận đúng một request có header mong đợi. Thử thay token trong stub thành giá trị sai để thấy test báo lỗi.
4. **Kiểm tra phân quyền đầu vào**: gửi request không xác thực, khẳng định ứng dụng chặn theo entry point đang cấu hình và downstream không bị gọi.
5. **Giữ manager thật**: mock HTTP token endpoint `client_credentials` bằng WireMock, sau đó khẳng định cả HTTP token request và Bearer header gửi đến downstream.
6. **Kiểm tra âm tính**: thử client registration sai, token sai, downstream trả `401` và endpoint khác không cần token. Viết assertion ở đúng ranh giới cho mỗi ca.

Ma trận tiêu chí:

| Ca kiểm thử | Inbound HTTP | Manager | Outbound HTTP | Assertion chính |
| --- | --- | --- | --- | --- |
| User chưa đăng nhập | Bị từ chối | Không cần gọi | Không nên gọi | `401`/redirect tùy config, downstream = 0 |
| User hợp lệ, manager trả token | Cho phép | Trả authorized client giả | Bearer token đến WireMock | Exact `Authorization` và URI |
| Manager chọn sai registration | Cho phép | Nhận ID sai | Có nguy cơ dùng token sai | Verify `getClientRegistrationId()` |
| Token endpoint trả token mới | Cho phép | Manager thật | Bearer token mới | Verify token HTTP response → outbound header |
| Downstream trả `401` | Cho phép | Có token | Header vẫn được gửi | Header đúng và lỗi được xử lý |
| Endpoint không cần token | Cho phép | Không cần authorized client | Không có OAuth2 Bearer | Assert absence của header |
| WebFlux tương đương | WebTestClient | Reactive manager | Reactive WebClient | Verify trên downstream server |

## 9. Checklist chất lượng và giới hạn test

Trước khi kết luận “Authorization header được gửi đúng”, hãy kiểm tra:

- Test chạy qua **HTTP client thực có cấu hình OAuth2**, không mock toàn bộ gateway rồi chỉ assert status.
- Có assertion trên **outbound request**: header `Authorization` đúng dạng `Bearer <token>`, giá trị đúng, đúng URI và đúng số lần gọi.
- Có căn cứ về **nguồn token**: manager được mock để kiểm tra gắn header, hay manager thật để kiểm tra cấp phát/gia hạn token.
- Phân biệt rõ người dùng của request đầu vào, client registration của ứng dụng và principal gắn với authorized client.
- Có test thất bại khi thiếu token, sai scope/registration hoặc downstream yêu cầu bảo mật khác với cấu hình.
- Test không ghi access token hay client secret sản xuất ra log; chỉ dùng token fixture vô hại.

**Tiêu chí hoàn thành:** khi `MockMvc` nhận `200` và WireMock xác nhận đúng `Authorization: Bearer test-access-token` trên `GET /internal/reports`, bạn đã có bằng chứng thực tế rằng OAuth2 Client **đính đúng header vào request gửi đi** trong môi trường test. Muốn nói thêm rằng OAuth2 Client **đã lấy token thật từ Authorization Server**, hãy bổ sung bài kiểm thử manager thật và token endpoint phù hợp.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): `ClientRegistrationRepository`, `OAuth2AuthorizedClient` và `OAuth2AuthorizedClientManager`.
- [Spring Security — OAuth 2.0 Client Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): `OAuth2AuthorizedClientManager`, grant types và cách sử dụng HTTP client.
- [Spring Security — WebClient integration for Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): `ServletOAuth2AuthorizedClientExchangeFilterFunction` và client registration.
- [Spring Security — Testing OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oauth2Login()`, `oauth2Client()` trong `MockMvc`.
- [Spring Framework — MockRestServiceServer](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): xác minh outbound HTTP request cho `RestClient` và `RestTemplate`.
