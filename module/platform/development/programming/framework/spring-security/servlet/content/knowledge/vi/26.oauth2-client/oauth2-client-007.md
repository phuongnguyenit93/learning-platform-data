# `OAuth2AuthorizedClient`, kho lưu và vòng đời access token, refresh token

## 1. Vì sao cần quản lý authorized client?

Trong **Spring Security Servlet**, một ứng dụng có thể là **OAuth2 Client**: nó xin access token để gọi Resource Server thay mặt người dùng (authorization code), hoặc để giao tiếp giữa dịch vụ (client credentials). Sau khi nhận token, ứng dụng phải liên hệ token với đúng đăng ký OAuth2 client, đúng principal, lưu token ở nơi thích hợp, nhận biết hết hạn, làm mới khi được phép và xóa khi quyền đã chấm dứt.

`OAuth2AuthorizedClient` là mô hình của **một client đã được cấp phép**. Nó gồm `ClientRegistration`, tên principal, `OAuth2AccessToken` và `OAuth2RefreshToken` nếu có. Nó **không** phải `Authentication` của Spring Security, không phải registration configuration thuần túy, cũng không phải ID token của OpenID Connect.

Các thành phần phối hợp:

| Thành phần | Vai trò | Câu hỏi |
| --- | --- | --- |
| `ClientRegistration` | Metadata OAuth2: registration ID, client ID, grant type, authorization/token URI, scopes | Ứng dụng đăng ký với provider nào? |
| `OAuth2AuthorizedClient` | Kết quả authorization gắn registration, principal và token | Ai được cấp quyền cho client nào? |
| `OAuth2AuthorizedClientService` | Lưu/tải/xóa theo `(clientRegistrationId, principalName)` | Token nằm ở đâu qua nhiều request? |
| `OAuth2AuthorizedClientRepository` | Truy cập authorized client trong ngữ cảnh `HttpServletRequest`, `HttpServletResponse`, `Authentication` | Servlet request lấy token từ đâu? |
| `OAuth2AuthorizedClientManager` | Điều phối tải, authorize/reauthorize, lưu, xử lý thất bại | Khi gọi API, token có cần cấp/làm mới không? |
| `OAuth2AuthorizedClientProvider` | Cơ chế cho từng grant (`authorization_code`, `refresh_token`, `client_credentials`...) | Cách nào được phép lấy token mới? |

**Nguyên tắc:** service/repository **lưu trạng thái**; manager/provider **điều phối token**. Chỉ `loadAuthorizedClient()` không có tác dụng tự refresh access token.

## 2. Dữ liệu bên trong `OAuth2AuthorizedClient`

Dạng logic:

```text
OAuth2AuthorizedClient
├── ClientRegistration
│   ├── registrationId = "partner"
│   ├── clientId       = "portal-client"
│   └── authorizationGrantType = authorization_code
├── principalName      = "alice"
├── OAuth2AccessToken
│   ├── tokenValue     = <bí mật>
│   ├── issuedAt
│   ├── expiresAt
│   └── scopes
└── OAuth2RefreshToken? (có thể null)
    ├── tokenValue     = <bí mật>
    └── issuedAt / expiresAt (nếu có)
```

Một số API accessor quan trọng trong Spring Security 6.x:

```java
// Giả định client là một OAuth2AuthorizedClient được tải sẵn.
ClientRegistration registration = client.getClientRegistration();
String principal = client.getPrincipalName();
OAuth2AccessToken access = client.getAccessToken();
OAuth2RefreshToken refresh = client.getRefreshToken(); // nullable
Instant expiresAt = access.getExpiresAt();
Set<String> scopes = access.getScopes();
```

Đây chỉ là đoạn mã đặt trong scope có biến `client` và import phù hợp (`org.springframework.security.oauth2.client`, `org.springframework.security.oauth2.core`, `java.time`, `java.util`), **không** phải file Java độc lập. `getTokenValue()` trả credential nhạy cảm: không đưa vào log, JSON trả frontend, stack trace hay metrics label.

Khóa logic của authorized client gồm **registration ID + principal name**. Cùng một `ClientRegistration("partner")` có thể có authorized client của `alice`, `bob` và một service principal độc lập. Không cache token vào biến static toàn ứng dụng rồi dùng chung cho mọi user.

## 3. Access token, refresh token, ID token và session

- **Access token:** credential gửi đến API được cấp quyền, thường qua header `Authorization: Bearer ...`. Nó có scope, thời hạn sử dụng, có thể bị thu hồi trước `expiresAt`. Không phải mật khẩu đăng nhập của user.
- **Refresh token:** credential dùng gọi authorization server để xin access token mới mà không lặp lại toàn bộ tương tác đăng nhập. Refresh token có thể không được cấp, bị hết hạn, thu hồi hoặc được luân chuyển (*rotation*).
- **ID token:** thành phần xác thực danh tính trong OpenID Connect; không tự động là token mà một Resource Server chấp nhận.
- **Session/`SecurityContext`:** ứng dụng đang nhận diện user nào ở request hiện tại. Login thành công không đồng nghĩa user đã cấp mọi scope cho mọi API bên ngoài.

Với grant **authorization code**, provider có thể cấp refresh token theo policy/scope/consent. Với **client credentials**, thông thường client dùng client authentication để xin lại access token và **không cần refresh token**. Vì vậy phải code cho trường hợp `getRefreshToken() == null`.

Một ứng dụng có thể vừa là OAuth2 Client (gọi API ngoài), vừa là Resource Server (kiểm tra bearer token nhận vào). Hai vai trò xử lý hai bộ token và cơ chế Security khác nhau; không trộn token của request đến với token dùng gọi provider bên ngoài.

## 4. Chu trình OAuth2 authorization code trong Servlet

```text
Browser -> /oauth2/authorization/partner
              |
              v
  OAuth2AuthorizationRequestRedirectFilter
              |
              v
    Authorization Server / login / consent
              |
              | callback: authorization code
              v
      OAuth2LoginAuthenticationFilter
              |
              | đổi code lấy access token, có thể có refresh token
              v
      OAuth2AuthorizedClient tạo ra
              |
              v
    AuthorizedClientRepository / Service lưu
              |
              v
User gọi endpoint cần truy cập API partner
              |
              v
    OAuth2AuthorizedClientManager
              | đọc authorized client của principal + registration
              | dùng token hiện tại hoặc giao provider làm mới
              | lưu bản mới khi thành công
              v
  Outbound HTTP client gửi Bearer token đến API partner
```

Framework xử lý state/redirect/callback/token exchange theo cấu hình. Sơ đồ lược bớt session, CSRF, PKCE, security context và lỗi thất bại để nhấn mạnh vòng đời authorized client. Callback phải trỏ đúng public scheme/host sau reverse proxy; khi sai `redirect-uri`, token chưa kịp được lưu đã có thể thất bại.

Dữ liệu đăng ký OAuth2 client được cấu hình **trước**; chỉ sau khi provider cấp quyền mới có authorized client cho principal tương ứng. Nếu user đăng nhập với một registration mà controller tìm authorized client theo registration khác, `load` có thể trả `null`.

## 5. `OAuth2AuthorizedClientRepository` khác `OAuth2AuthorizedClientService` thế nào?

### Repository: theo request Servlet

Repository nhận `Authentication`, `HttpServletRequest` và `HttpServletResponse`. Các operation logic là:

```java
// Mô tả API, lược bỏ đầy đủ generic/import và thân implementation:
loadAuthorizedClient(registrationId, authentication, request);
saveAuthorizedClient(client, authentication, request, response);
removeAuthorizedClient(registrationId, authentication, request, response);
```

`AuthenticatedPrincipalOAuth2AuthorizedClientRepository` có thể dùng `OAuth2AuthorizedClientService` khi user đã xác thực và dùng HTTP session repository cho principal chưa xác thực. Chính xác backend nào được dùng phụ thuộc bean và cấu hình; không được giả định mọi token luôn nằm trong HTTP session.

### Service: theo registration ID và principal name

Ba operation quan trọng:

```java
service.loadAuthorizedClient("partner", "alice");
service.saveAuthorizedClient(authorizedClient);
service.removeAuthorizedClient("partner", "alice");
```

`load` trả `null` nếu chưa tìm thấy. Nó không tự xin token từ provider. Dùng service để cất trạng thái của authorized client, đặc biệt trong background job hoặc khi muốn persistence chung.

| Kho lưu | Tính chất | Rủi ro/vận hành |
| --- | --- | --- |
| `InMemoryOAuth2AuthorizedClientService` | Lưu theo process, mất khi restart | Node khác không thấy token; không dành cho HA nếu cần dữ liệu bền vững |
| `HttpSessionOAuth2AuthorizedClientRepository` | Gắn với Servlet HTTP session | Độ bền/phân tán tùy cấu hình session store; phụ thuộc cookie/session |
| `JdbcOAuth2AuthorizedClientService` | Dùng SQL qua `JdbcOperations` và schema phù hợp | Phải quản lý table, backup, secret-at-rest, quyền DB |
| Custom service/repository | Có thể dùng encrypted store hoặc DB theo tenant | Phải tự xử lý key, concurrency, revoke và audit |

Không đánh đồng in-memory service với session. Session có thể tồn tại ở nơi lưu phân tán qua Spring Session; service in-memory là dữ liệu thuộc JVM hiện tại.

## 6. Chương trình Java 17+ chạy độc lập: lưu, tải và xóa token giả

Ví dụ này không gọi provider, **không sử dụng secret thật** và luôn cho cùng output. Nó cho thấy `OAuth2AuthorizedClientService` chỉ làm nhiệm vụ lưu trữ. Dùng Spring Security OAuth2 Client phiên bản được quản lý bởi Spring Boot 3.3.5.

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.security:spring-security-oauth2-client'
}

application {
    mainClass = 'demo.tokens.AuthorizedClientStoreDemo'
}
```

Tạo `src/main/java/demo/tokens/AuthorizedClientStoreDemo.java`:

```java
package demo.tokens;

import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

public final class AuthorizedClientStoreDemo {
    public static void main(String[] args) {
        ClientRegistration registration =
                ClientRegistration.withRegistrationId("partner")
                        .clientId("demo-client")
                        .clientSecret("only-for-local-demo")
                        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                        .authorizationUri("https://identity.example.invalid/authorize")
                        .tokenUri("https://identity.example.invalid/token")
                        .scope("profile.read")
                        .build();

        OAuth2AuthorizedClientService service =
                new InMemoryOAuth2AuthorizedClientService(
                        new InMemoryClientRegistrationRepository(registration));

        Instant issuedAt = Instant.parse("2026-01-01T00:00:00Z");
        OAuth2AccessToken access = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "test-access-value",
                issuedAt,
                issuedAt.plusSeconds(3600),
                Set.of("profile.read"));
        OAuth2RefreshToken refresh = new OAuth2RefreshToken(
                "test-refresh-value", issuedAt);

        OAuth2AuthorizedClient authorizedClient =
                new OAuth2AuthorizedClient(registration, "alice", access, refresh);
        service.saveAuthorizedClient(authorizedClient);

        OAuth2AuthorizedClient loaded =
                service.loadAuthorizedClient("partner", "alice");
        System.out.println("loaded=" + (loaded != null));
        System.out.println("principal=" + loaded.getPrincipalName());
        System.out.println("has_refresh=" + (loaded.getRefreshToken() != null));
        System.out.println("expired_at_fixed_time=" +
                !loaded.getAccessToken().getExpiresAt()
                        .isAfter(issuedAt.plusSeconds(3700)));

        service.removeAuthorizedClient("partner", "alice");
        System.out.println("removed=" +
                (service.loadAuthorizedClient("partner", "alice") == null));
    }
}
```

Chạy bằng Gradle wrapper của dự án:

```bash
./gradlew run
```

Trên Windows:

```powershell
.\gradlew.bat run
```

Stdout của **chương trình Java** (loại trừ thông báo của Gradle):

```text
loaded=true
principal=alice
has_refresh=true
expired_at_fixed_time=true
removed=true
```

Tất cả thời điểm cố định nên kết quả không phụ thuộc đồng hồ hiện tại. Mặc dù access token đã quá hạn tại thời điểm giả định, service vẫn tải được object: **chỉ tải dữ liệu không phải refresh**. `removeAuthorizedClient` xóa bản ghi nội bộ, **không** gửi yêu cầu thu hồi token cho authorization server. Host `.invalid` cố ý không tồn tại và không được truy cập trong ví dụ này; Gradle chỉ cần tải dependencies nếu chưa có cache.

## 7. Cấu hình OAuth2 Client trong Spring Boot Servlet thực tế

Với ứng dụng web dùng OAuth2 Login + OAuth2 Client, khai báo dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Dùng registration/provider thật (ví dụ dưới dùng hostname minh họa, cần thay bằng dịch vụ OAuth2 có thật và lưu secret bên ngoài source):

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner-provider
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read
        provider:
          partner-provider:
            authorization-uri: https://identity.partner.example/authorize
            token-uri: https://identity.partner.example/token
            user-info-uri: https://identity.partner.example/userinfo
            user-name-attribute: sub
```

Một `SecurityFilterChain` riêng cho OAuth2 login:

```java
package demo.partner;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
```

Các URI `identity.partner.example` chỉ minh họa, **không thể đăng nhập thật** nếu chưa có provider tương ứng. Cấu hình này là class độc lập trong một **Spring Boot application** có main class `@SpringBootApplication`, DataSource và các endpoint phù hợp nếu cần; không phải thành phần của chương trình CLI ở phần 6.

Sau khi user được cấp quyền với registration `"partner"`, controller có thể nhận authorized client:

```java
package demo.partner;

import java.util.Map;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ClientStatusController {
    @GetMapping("/partner/status")
    public Map<String, Object> status(
            @RegisteredOAuth2AuthorizedClient("partner")
            OAuth2AuthorizedClient authorizedClient) {
        return Map.of(
                "connected", true,
                "registration",
                authorizedClient.getClientRegistration().getRegistrationId());
    }
}
```

`@RegisteredOAuth2AuthorizedClient` làm việc với cơ chế resolve/authorize của OAuth2 Client. Nếu token chưa có hoặc cần user đồng ý, ứng dụng có thể cần tiếp tục authorization flow hoặc xử lý lỗi, tùy config. Ví dụ cố ý **không** phản hồi token value về browser. Đừng dùng `.permitAll()` cho endpoint chứa dữ liệu của user; phải kiểm tra quyền phù hợp.

## 8. `OAuth2AuthorizedClientManager` điều phối token như thế nào?

Một `OAuth2AuthorizedClientManager` có thể tìm authorized client hiện có, chuyển cho provider phù hợp và ghi kết quả cập nhật. Với request Servlet có HTTP request/response, `DefaultOAuth2AuthorizedClientManager` sử dụng repository.

Cấu hình minh họa **thay thế hoặc bổ sung cho bean manager mặc định** trong ứng dụng đã có cấu hình OAuth2 Client:

```java
package demo.partner;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientManagerConfig {
    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {
        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .build();
        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Khi `authorize(...)` được gọi ở thời điểm thích hợp, provider `refreshToken()` có thể đổi refresh token lấy access token mới nếu refresh token hiện hữu và access token cần được làm mới (kể cả khoảng lệch đồng hồ mà provider áp dụng). Success handler có thể lưu authorized client mới. Failure handler có thể xóa trạng thái không còn hợp lệ, ví dụ trong một số luồng `invalid_grant`, theo config đang chạy.

**Không có bộ đếm nền tự refresh tất cả token chỉ vì khai báo `.refreshToken()`.** Manager cần được sử dụng, chẳng hạn thông qua OAuth2-aware HTTP client/argument resolver. Không tự tin rằng token luôn mới khi ứng dụng chỉ gọi `service.loadAuthorizedClient()` rồi đưa raw token vào request.

Nếu gọi API bằng HTTP client, nên tích hợp với các facility của Spring Security OAuth2 Client (ví dụ `ServletOAuth2AuthorizedClientExchangeFilterFunction` và `WebClient`) để chọn token đúng registration/principal và lưu token đã refresh. Tách quyền theo audience/scope; không phát token của user A sang request của user B, và không forward Bearer token đến hostname không được tin cậy.

## 9. Manager cho tác vụ nền và client credentials

`DefaultOAuth2AuthorizedClientManager` phù hợp trong **Servlet request**. Với scheduled job hoặc service-to-service không có request/session, dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` dựa trên service:

```java
// Đoạn method trong @Configuration, cần import các loại được dùng.
@Bean
OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService service) {
    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, service);
    manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build());
    return manager;
}
```

`client_credentials` thường lấy access token mới bằng client secret/private key khi cần; không nên trông đợi refresh token. Có thể gọi:

```java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId("batch-partner")
                .principal("billing-worker")
                .build();

OAuth2AuthorizedClient client = manager.authorize(request);
if (client == null) {
    throw new IllegalStateException("No authorized client for batch-partner");
}
```

Đây là đoạn đặt trong class có biến `manager` và import `OAuth2AuthorizeRequest`, `OAuth2AuthorizedClient`; registration `batch-partner` phải được cấu hình thật. Principal `"billing-worker"` là **khóa lưu token của workload**, không phải user đã đăng nhập. Đặt principal ổn định và phân tách workload/tenant khi mức quyền khác nhau.

## 10. Vòng đời access token

```text
Chưa có authorized client
    |
    v
Provider thực hiện grant thích hợp -> access token A1
    |
    v
Manager lưu authorized client
    |
    v
Outbound call đến Resource Server dùng A1
    |
    +--> A1 vẫn hiệu lực -> tiếp tục dùng
    |
    +--> A1 gần hết/hết hạn -> provider phù hợp
             |--> refresh grant khi có refresh token
             |--> client credentials xin token mới
             |--> authorization code cần user authorize lại
    |
    v
Lưu authorized client cập nhật hoặc xử lý thất bại
```

`OAuth2AccessToken#getExpiresAt()` là metadata về hạn token. Token có thể bị revoked **trước** thời điểm này, nên `expiresAt` không cam kết API sẽ chấp nhận token. Ngược lại, HTTP `401` từ Resource Server chưa chắc do hết hạn: có thể sai audience, sai scope, revoked, signature hoặc provider policy. Cần response handling/authorization failure handler hợp lý.

Một client có thể retry khi lỗi mạng, nhưng không nên tự làm vòng lặp vô hạn `401 -> refresh -> retry -> 401`. Request có side effect (POST/PATCH) cần idempotency contract trước khi retry tự động. Không dùng access token cũ sau khi đã nhận token mới chỉ vì một cache lỡ giữ lại object stale.

## 11. Vòng đời refresh token và rotation

Refresh token là credential nhạy cảm cho phép cấp access token mới. Khi refresh thành công, authorization server có thể cấp cặp mới:

```text
Trước:  access=A1 (expired), refresh=R1
Sau:    access=A2,           refresh=R2 (nếu bật rotation)
```

Manager/service cần lưu **bản authorized client đã cập nhật**. Nếu provider không trả refresh token mới, việc giữ/cập nhật token dựa vào contract của client implementation và provider; tránh tự ghép token thiếu kiểm soát.

Khi refresh thất bại, phải phân loại:

| Tình huống | Hành vi phù hợp |
| --- | --- |
| `invalid_grant` do refresh token hết hạn/revoked/reused | Ngừng retry bằng R1, cân nhắc xóa trạng thái không hợp lệ, yêu cầu user authorize lại |
| `invalid_client` hoặc client secret hết hạn | Sửa đăng ký client/credential, alert vận hành, không liên tục yêu cầu user login lại |
| Timeout/5xx từ authorization server | Retry giới hạn với backoff và đo lường; không xóa token ngay chỉ vì một lỗi mạng |
| Access token vẫn còn hạn nhưng refresh token đã hết hạn | Có thể tiếp tục sử dụng access token theo policy; lần gia hạn tiếp cần reauthorize |
| Refresh token được rotation nhưng một instance ghi đè token mới | Cần xử lý đồng bộ/locking hoặc CAS theo `(registrationId, principalName)` |

Một race nguy hiểm: hai request đọc R1, cùng refresh. Request thứ nhất nhận R2; request thứ hai dùng lại R1 nhận `invalid_grant`. Nếu request thứ hai xóa hàng vừa được thứ nhất cập nhật, user bị mất quyền không cần thiết. Với nhiều node và refresh token rotation, nên cân nhắc lock phân tán, optimistic locking hoặc điều phối refresh theo một điểm tập trung. Default service không nên bị xem là đã giải quyết mọi bài toán race giữa replicas.

## 12. Lưu JDBC khi cần persistence

Với nhiều instance hoặc yêu cầu khôi phục qua restart, có thể cấu hình `JdbcOAuth2AuthorizedClientService`.

Các dependency ví dụ cho Spring Boot Servlet dùng PostgreSQL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Trong class `@Configuration` đã có DataSource:

```java
@Bean
OAuth2AuthorizedClientService authorizedClientService(
        JdbcOperations jdbcOperations,
        ClientRegistrationRepository registrations) {
    return new JdbcOAuth2AuthorizedClientService(
            jdbcOperations, registrations);
}
```

Các import của đoạn method:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
```

Bean **không tự tạo bảng**. Spring Security có schema SQL tham khảo cho JDBC authorized clients, nhưng bạn phải đưa schema tương thích vào migration (Flyway/Liquibase hoặc tương đương), sửa kiểu dữ liệu theo database và kiểm thử đọc/ghi/xóa thực.

Dữ liệu có **access token và refresh token** nên quyền đọc DB, backup, log SQL, encryption at rest, audit và retention phải được bảo vệ như credential. Không sao chép token raw từ production sang staging. Khi cần nhiều tenant, xác định mô hình scoping thật: `registrationId + principalName` phải tránh va chạm giữa các tenant có quyền khác nhau.

## 13. Logout, ngắt kết nối và revocation khác nhau

| Hành động | Điều thực sự xảy ra |
| --- | --- |
| Logout phiên Spring Security | Chấm dứt trạng thái login/session theo config; không chắc token ở authorization server bị thu hồi |
| `removeAuthorizedClient(...)` | Xóa bản ghi token từ repository/service local; không tự gửi yêu cầu revocation |
| Token revocation endpoint của provider | Yêu cầu authorization server hủy token theo hỗ trợ và chính sách của provider |
| Xóa tenant/user khỏi business DB | Thay đổi quyền ở sản phẩm; không đương nhiên xóa mọi authorized client trong cache/backup |

“Disconnect integration” nên được thiết kế như một nghiệp vụ riêng: tìm đúng principal/registration, revoke ở provider khi được hỗ trợ và cần, xóa local store, kiểm tra token cache, dừng background work và ghi audit **không chứa token value**. Việc user logout browser không nhất thiết là yêu cầu revoke mọi tích hợp, nhưng khi họ chủ động disconnect thì không được tiếp tục dùng token đã được cấp.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| OAuth2 login thành công nhưng không có authorized client | Nhầm registration/principal, session/repository khác nhau | Kiểm tra callback, key, bean service/repository và auth hiện tại |
| Restart mất token | In-memory service | Đánh giá JDBC/shared store |
| Node A hoạt động, node B thất bại | Dữ liệu chỉ ở memory/session không chia sẻ | Kiểm tra session persistence và service backend |
| Access token hết hạn vẫn được gửi đi | Gọi `loadAuthorizedClient` rồi sử dụng trực tiếp, không qua manager | Cấu hình provider và dùng manager |
| Refresh token là `null` | Provider không cấp, scope/policy/grant không phù hợp | Đọc hợp đồng provider; xử lý reauthorize |
| Refresh thất bại `invalid_grant` liên tục | Revoked/expired/rotated refresh token | Loại bỏ retry vô hạn, xử lý token invalid và login lại |
| Sau refresh vẫn dùng token cũ | Cache stale hoặc ghi đè đồng thời | Kiểm tra repository, success handler, lock/transaction |
| Job nền báo thiếu request Servlet | Dùng manager dành cho Servlet | Dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| User A gọi API bằng token của user B | Key principal/caching sai | Scope token theo principal, tenant và registration |
| Xóa local store mà token vẫn có hiệu lực | Không gọi revocation endpoint | Thiết kế disconnect/revocation riêng |
| Gọi API trả 401 dù chưa đến `expiresAt` | Audience, revocation, policy hoặc lỗi token khác | Phân tích Resource Server response; không chỉ nhìn thời gian |
| Token xuất hiện trong log/response | In raw object, SQL bind hoặc HTTP debug | Redact token, hạn chế log và quyền truy cập |

Một lỗi thiết kế có tính hệ thống là lưu duy nhất `"partner"` vào cache key mà không phân biệt `"alice"` và `"bob"`. Nếu token gắn quyền người dùng, cache như vậy có thể gây truy cập nhầm danh tính. Thiết kế key phải phản ánh đúng principal và môi trường/tenant khi có nhiều vùng bảo mật.

## 15. Test phù hợp với từng tầng

**Test local storage** như chương trình Java ở mục 6 chứng minh save/load/remove, key và token có thể tồn tại dù expired. Nó không chứng minh refresh grant hoặc callback OAuth2 hoạt động.

**Test refresh:** dùng authorization server stub hoặc test OAuth2 provider để trả `access_token`, `expires_in`, `refresh_token` mới, rồi mô phỏng `invalid_grant`, timeout và rotation. Gọi qua `OAuth2AuthorizedClientManager`; khẳng định token mới được lưu, token invalid bị xử lý theo handler đã chọn, không retry vô hạn.

**Test Servlet end-to-end:** chạy flow authorization-code qua provider thử nghiệm, kiểm tra HTTP session, redirect URI, repository, `@RegisteredOAuth2AuthorizedClient`, outbound API call và credential scoping. Với nhiều replica, tạo tình huống refresh đồng thời để xác minh atomicity.

**Test an ninh:** không response/log raw token; token của user/tenant này không dùng cho user/tenant khác; khi disconnect không còn bản ghi; backup/log/database không làm lộ credential.

## 16. Checklist production

Trước khi triển khai OAuth2 Client, hãy xác nhận:

1. Grant là authorization code/OIDC hay client credentials? Có refresh token thực sự không?
2. Registration ID và principal name được xác định, tách tenant/service account đúng cách?
3. Token nằm trong session, process memory hay shared store? Restart/scale ảnh hưởng thế nào?
4. Mọi luồng lấy token cho outgoing request đều đi qua manager/provider phù hợp?
5. Access token expired, refresh token rotated/revoked và `invalid_grant` được xử lý ra sao?
6. Có backoff, giới hạn retry và kiểm soát race giữa nhiều node?
7. Secret của client và refresh token được mã hóa/lưu trữ/backup/log bảo vệ?
8. Logout khác disconnect, và provider revocation được thiết kế rõ?
9. HTTP client chỉ gửi token cho API có audience/host phù hợp, dùng HTTPS?
10. Có test success/failure cùng metric không chứa raw token?

## Ghi nhớ

`OAuth2AuthorizedClient` kết nối **registration + principal + access/refresh tokens**. `OAuth2AuthorizedClientService`/`Repository` chỉ **lưu và tìm lại**, còn `OAuth2AuthorizedClientManager` và provider **điều phối lấy/làm mới token**. Kho lưu không tự refresh, xóa local không tự revoke ở provider. Hiểu ranh giới đó, dùng đúng manager cho Servlet hoặc batch job, và kiểm soát refresh-token rotation sẽ tránh đa số lỗi lifecycle cũng như rò rỉ quyền truy cập.