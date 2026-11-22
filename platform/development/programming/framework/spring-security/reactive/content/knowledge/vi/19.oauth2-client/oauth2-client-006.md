# Cấp mới access token và xử lý refresh token khi hết hạn trong Spring Security Reactive OAuth2 Client

## 1. Mục tiêu và khái niệm

Một ứng dụng Spring WebFlux hoạt động như **OAuth2 Client**: trình duyệt đăng nhập qua Authorization Server, sau đó ứng dụng dùng WebClient gửi access token tới Resource Server. Access token có thời gian tồn tại giới hạn. Nếu cứ gửi token hết hạn, Resource Server thường trả HTTP 401. Nếu đã được Authorization Server cấp **refresh token hợp lệ**, client có thể xin access token mới mà chưa cần bắt người dùng đăng nhập lại.

**Authorization Server mới phát hành token.** OAuth2 Client không thể tự sửa JWT exp, ký lại token hay biến refresh token thành Bearer cho Resource Server.

Mục tiêu:

1. Phân biệt access token, refresh token, authorization code, ID token, session cookie.
2. Hiểu authorization_code và refresh_token grant, token endpoint và refresh rotation.
3. Hiểu expires_in, issuedAt, expiresAt và ngưỡng refresh theo clock skew 60 giây.
4. Dùng ReactiveOAuth2AuthorizedClientManager, RefreshTokenReactiveOAuth2AuthorizedClientProvider, ServerOAuth2AuthorizedClientExchangeFilterFunction và authorized client store.
5. Biết vì sao service/background task phải chọn manager khác HTTP request.
6. Xử lý invalid_grant, revoked token, missing refresh token, 401/403 và lỗi mạng đúng.
7. Chạy ví dụ Java 17+ Spring Boot WebFlux với OAuth2 Client và WebClient.
8. Kiểm thử provider, rotation, expiry, persistence bằng StepVerifier và fake Token Endpoint không cần IdP thật.
9. Tránh lộ refresh token, dùng token nhầm user, concurrent refresh và retry loop.

### 1.1. Các vai trò

~~~text
Browser người dùng
   | login/consent
   v
OAuth2 Client (Spring WebFlux)
   | authorization_code
   v
Authorization Server / IdP
   | access_token + optional refresh_token
   v
OAuth2AuthorizedClient lưu tại backend
   | Authorization: Bearer access_token
   v
Resource Server (API nhận Bearer)
   | dữ liệu được cấp quyền
   v
WebFlux ứng dụng
~~~

| Thành phần | Vai trò | Nơi sử dụng |
| --- | --- | --- |
| Authorization code | Mã ngắn hạn, one-time dùng ở Token Endpoint | Client đổi lấy token |
| Access token | Credential gọi resource có scope/audience cụ thể | Resource Server |
| Refresh token | Credential xin access token mới | Authorization Server Token Endpoint |
| ID token OIDC | Chứng nhận phiên đăng nhập của end user dành cho OIDC client | Không thay access token |
| WebSession cookie | Duy trì phiên của ứng dụng WebFlux | Trình duyệt với ứng dụng |
| Client secret | Xác thực confidential client với Authorization Server | Backend, không ra frontend |

Access token có thể là JWT hoặc opaque string. **OAuth2 Client không cần giả định luôn là JWT**. Thời hạn được biểu diễn bởi OAuth2AccessToken.getExpiresAt(). Refresh token có thể có tuổi thọ dài hơn nhưng vẫn có thể bị revoke/expire hoặc rotate.

### 1.2. Vòng đời khác nhau

- WebSession của app có thể còn sống khi access token của IdP hết hạn.
- Access token mới có thể được refresh trong khi user vẫn đang đăng nhập.
- Refresh token hết hạn hoặc revoke có thể khiến người dùng cần authorize lại.
- Một WebSession đã logout **không tự hồi sinh** chỉ vì backend còn cất refresh token.
- Refresh token không phải bằng chứng cho phép user của API WebFlux bỏ qua authorizeExchange.

## 2. Authorization code và refresh_token grant

Một lần login thường bắt đầu ở endpoint Spring Security:

~~~http
GET /oauth2/authorization/training HTTP/1.1
Host: app.example.org
~~~

Spring Security chuyển browser sang Authorization Endpoint của nhà cung cấp. Sau xác thực/consent và state verification, callback mặc định có thể là:

~~~http
GET /login/oauth2/code/training?code=<authorization-code>&state=<state> HTTP/1.1
~~~

Spring Security đổi code lấy access token và optional refresh token, rồi lưu OAuth2AuthorizedClient theo ClientRegistration và principal. OIDC có thể thêm ID token, nhưng ID token không thay thế access token khi gọi Resource Server.

### 2.1. Request refresh

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.org
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token-value>
~~~

Client authentication tùy nhà cung cấp: client_secret_basic, private_key_jwt, mTLS hoặc phương án khác. Tất cả phải dùng HTTPS. Không tự cho rằng secret luôn nằm trong form body hoặc giả định Token Endpoint chấp nhận mọi grant.

Response thành công ví dụ:

~~~json
{
  "access_token": "access-next",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "refresh-next",
  "scope": "profile api.read"
}
~~~

expires_in là **số giây**, không phải epoch. Scope được cấp có thể bị thu hẹp. Nếu nhà cung cấp rotate refresh token từ R1 sang R2, client **phải lưu R2**; R1 có thể bị vô hiệu hóa ngay. Một response refresh không nhất thiết có refresh_token mới, tùy provider và chính sách. Không tự ghi null vào refresh token đang có mà không hiểu implementation.

### 2.2. Khi không có refresh token

**RefreshTokenReactiveOAuth2AuthorizedClientProvider** không thể refresh nếu authorized client không có refresh token. Điều đó không mặc nhiên là bug: Authorization Server có thể từ chối cấp refresh token hoặc yêu cầu offline_access/consent. Với user authorization_code, cần authorize/login lại; với client_credentials của machine account, xin access token mới bằng client_credentials, **không cần refresh token user**.

### 2.3. Refresh grant không cho thêm quyền tự động

Refresh token không tự đổi user thành admin và không tự tăng scopes của access token. Resource Server vẫn cần kiểm tra audience, scopes, quyền đối tượng/tenant. Nếu API trả 403 insufficient_scope, refresh cùng grant thường không khắc phục được thiếu quyền.

## 3. Expiry, skew và refresh trước hạn

Spring Security OAuth2AccessToken lưu issuedAt và expiresAt. RefreshTokenReactiveOAuth2AuthorizedClientProvider có Clock/clockSkew để xác định access token đã đến ngưỡng làm mới. Spring Security 6.5 Javadoc nêu **clockSkew mặc định 60 giây**.

Điều kiện gần đúng là thời điểm hiện tại đã vượt mốc:

~~~text
expiresAt - clockSkew
~~~

Ví dụ token hết hạn 10:05:00:

| Request | Còn lại | Hành động với skew 60 giây |
| --- | --- | --- |
| 10:02:00 | 180 giây | Không refresh |
| 10:03:59 | 61 giây | Không refresh |
| 10:04:01 | 59 giây | Refresh nếu có refresh token |
| 10:05:01 | Token đã quá hạn | Refresh nếu có refresh token |

Clock skew giảm rủi ro lệch đồng hồ/latency nhưng không phải phép màu. Đặt skew quá lớn so với token TTL khiến mọi request liên tục gọi Token Endpoint. Đồng bộ NTP và test với Clock.fixed thay vì sleep sát ranh giới expiry.

~~~java
RefreshTokenReactiveOAuth2AuthorizedClientProvider provider =
        new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
provider.setClock(Clock.systemUTC());
provider.setClockSkew(Duration.ofSeconds(60));
~~~

Đây chỉ là snippet API; test Java đầy đủ ở mục 8.

## 4. Các abstraction reactive

### 4.1. ClientRegistration

Cấu hình danh tính của OAuth2 client với nhà cung cấp: registrationId, clientId, client authentication method, grant, redirectUri, authorizationUri, tokenUri, scopes, metadata issuer/JWK/userinfo. ClientRegistration không phải token.

### 4.2. OAuth2AuthorizedClient

Đại diện một client đã được cấp quyền **cho một principal cụ thể**:

~~~text
OAuth2AuthorizedClient
  ClientRegistration: training
  principalName: alice
  OAuth2AccessToken: access-current
  OAuth2RefreshToken: refresh-current hoặc null
~~~

Không có static access token dùng chung cho Alice và Bob. Sự liên kết đúng registrationId/principalName là ranh giới tránh lộ dữ liệu đa người dùng.

### 4.3. ReactiveOAuth2AuthorizedClientManager

Manager điều phối:

1. Load authorized client từ repository/service.
2. Dùng ReactiveOAuth2AuthorizedClientProvider phù hợp để authorize/re-authorize.
3. Với refresh thành công, success handler lưu authorized client mới.
4. Với một số OAuth2 errors như invalid_grant, failure handler có thể loại bản ghi không hợp lệ.
5. Trả Mono<OAuth2AuthorizedClient>, không block event loop.

| Manager | Dùng cho | Storage |
| --- | --- | --- |
| DefaultReactiveOAuth2AuthorizedClientManager | HTTP WebFlux có ServerWebExchange | ServerOAuth2AuthorizedClientRepository |
| AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager | Service, scheduled/background task không có HTTP request | ReactiveOAuth2AuthorizedClientService |

Không nhầm với các class Servlet DefaultOAuth2AuthorizedClientManager/HttpServletRequest/HttpSession.

### 4.4. ReactiveOAuth2AuthorizedClientProvider

~~~java
ReactiveOAuth2AuthorizedClientProvider providers =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();
~~~

Refresh token provider chỉ áp dụng khi đã có authorized client, refresh token và access token cần làm mới. Nếu không phù hợp, provider có thể trả Mono.empty, không gọi Token Endpoint. Có thể thêm clientCredentials riêng khi ứng dụng cần machine-to-machine calls.

### 4.5. ServerOAuth2AuthorizedClientExchangeFilterFunction

WebClient OAuth2 filter có thể giải quyết authorized client, refresh trước request và gắn **Authorization: Bearer** vào outbound request. Đừng bật default OAuth2AuthorizedClient cho toàn bộ outbound hosts nếu WebClient gọi URL tùy ý, vì có thể gửi Bearer token đến host không đáng tin.

**Hai loại 401 khác nhau:** Token Endpoint trả invalid_grant khi refresh thất bại; Resource Server có thể trả 401 invalid_token khi access token bị revoke dù local expiresAt còn hạn. Làm mới trước request và xử lý 401 sau request là hai luồng khác nhau.

## 5. Persistence và rotation concurrency

ReactiveOAuth2AuthorizedClientService có các phương thức:

~~~java
Mono<Void> saveAuthorizedClient(
        OAuth2AuthorizedClient client, Authentication principal);

Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
        String registrationId, String principalName);

Mono<Void> removeAuthorizedClient(
        String registrationId, String principalName);
~~~

Đây là minh họa chữ ký, không phải class Java độc lập. Mono phải được compose và subscribe đúng vòng đời; gọi save rồi bỏ Mono có thể không lưu gì. Manager thường tự điều phối việc lưu.

### 5.1. Refresh token rotation race

~~~text
T0: Kho lưu có access A1 + refresh R1 cho alice
T1: Request A đọc R1
T2: Request B cũng đọc R1
T3: A refresh thành công, AS trả A2/R2
T4: A lưu A2/R2
T5: B dùng R1 bị từ chối invalid_grant (R1 đã rotate)
T6: B xóa bản ghi theo key mà không kiểm tra version
    => A2/R2 của A có nguy cơ bị xóa
~~~

Trong một số IdP, tái sử dụng R1 còn có thể kích hoạt token family revocation. Spring Security không mặc nhiên tạo distributed lock cho mọi storage và topology.

**Các biện pháp:**

- Single-flight refresh theo registrationId/principal trong một process.
- Với multi-node, optimistic locking/CAS/version hoặc distributed coordination.
- Lưu access/refresh token mới nhất quán.
- Cleanup invalid_grant không xóa một version token mới hơn của request khác.
- Retry có giới hạn/backoff và hiểu token reuse policy; không retry R1 vô hạn sau timeout.
- Bảo vệ storage, logs và backup chứa secrets.

### 5.2. Token storage an toàn

- Refresh token nên ở server-side khi app có backend/BFF; không xuất nó ra JSON frontend.
- Hạn chế quyền DB/Redis, mã hóa at rest, kiểm soát TTL, backup và secret rotation.
- Không log access_token, refresh_token, Authorization header, cookies, authorization code, code verifier hoặc client_secret.
- Không dùng cùng token cho các principals/tenants khác nhau.
- Xóa/revoke đúng authorized client khi logout theo chính sách IdP.
- Tránh gửi Bearer token đến URL do user tự cung cấp; cần outbound allowlist để giảm SSRF/exfiltration.

## 6. Dự án Java 17+ / Spring Boot WebFlux

Ví dụ dùng Spring Boot 3.5.16, Java 17+, Gradle 8.x tương thích, Spring Security OAuth2 Client Reactive.

**Hai tầng kiểm tra khác nhau:** ứng dụng có cấu hình OAuth2 login và WebClient, nhưng cần IdP/Resource Server thực cho login end-to-end; các host example.org chỉ là tên tài liệu. Bộ test mục 7 chạy thật các class refresh/manager của Spring Security với fake Token Endpoint, **không gọi network**, nên có thể chạy gradle test không cần IdP.

### 6.1. Cấu trúc dự án

~~~text
webflux-refresh/
├── settings.gradle
├── build.gradle
├── src/main/resources/application.yml
├── src/main/java/example/refresh/TokensApplication.java
├── src/main/java/example/refresh/SecurityConfig.java
├── src/main/java/example/refresh/DownstreamClient.java
├── src/main/java/example/refresh/ApiController.java
└── src/test/java/example/refresh/RefreshFlowTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-refresh'
~~~

### 6.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không dùng Servlet OAuth2 client APIs cho WebFlux. Spring Boot BOM giúp các dependencies đồng bộ; dự án nhóm nên có Gradle Wrapper được pin.

### 6.4. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          training:
            provider: training-idp
            client-id: lesson-webflux-client
            client-secret: local-demo-not-production-secret
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - offline_access
        provider:
          training-idp:
            authorization-uri: https://login.example.org/oauth2/authorize
            token-uri: https://login.example.org/oauth2/token
            jwk-set-uri: https://login.example.org/oauth2/jwks
            user-info-uri: https://login.example.org/oauth2/userinfo
            user-name-attribute: sub

app:
  downstream:
    profile-url: https://resource.example.org/api/profile
~~~

**Chú ý:** example.org là host minh họa, không thể login end-to-end với nó. Khi dùng IdP thật, cấu hình ClientRegistration, client auth, redirect URI, scopes và URLs thật; secrets phải đến từ vault/Environment, không dùng giá trị demo cho production. Scope offline_access không bảo đảm IdP cấp refresh token, còn phụ thuộc consent/policy.

### 6.5. TokensApplication.java

~~~java
package example.refresh;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TokensApplication {
    public static void main(String[] args) {
        SpringApplication.run(TokensApplication.class, args);
    }
}
~~~

### 6.6. SecurityConfig.java

~~~java
package example.refresh;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository repository) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

OAuth2 login phục vụ interactive user; ReactiveOAuth2AuthorizedClientManager tìm authorized client theo principal và repository, gọi refresh provider khi access token tới hạn. Success handler mặc định lưu authorized client đã được refresh. Không tắt CSRF toàn ứng dụng chỉ vì dùng API; ví dụ này chỉ có GET.

### 6.7. DownstreamClient.java

~~~java
package example.refresh;

import java.util.Objects;

import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class DownstreamClient {

    private final WebClient webClient;
    private final String profileUrl;

    public DownstreamClient(
            ReactiveOAuth2AuthorizedClientManager manager,
            Environment env) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        manager);
        this.webClient = WebClient.builder()
                .filter(oauth)
                .build();
        this.profileUrl = Objects.requireNonNull(
                env.getProperty("app.downstream.profile-url"),
                "app.downstream.profile-url is required");
    }

    public Mono<String> profile(ServerWebExchange exchange) {
        return webClient.get()
                .uri(profileUrl)
                .attributes(
                        ServerOAuth2AuthorizedClientExchangeFilterFunction
                                .clientRegistrationId("training"))
                .attributes(
                        ServerOAuth2AuthorizedClientExchangeFilterFunction
                                .serverWebExchange(exchange))
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

WebClient nhận clientRegistrationId rõ ràng và ServerWebExchange đúng request. Nó lấy/refresh token và gửi Bearer đến **downstream trusted host**. Không để client gửi URL bất kỳ; không trả token values cho frontend. Constructor filter nhận manager không tự gắn failure handler dành cho Resource Server 401/403; phần xử lý này khác expiry refresh, xem mục 8.

### 6.8. ApiController.java

~~~java
package example.refresh;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    private final DownstreamClient downstream;

    public ApiController(DownstreamClient downstream) {
        this.downstream = downstream;
    }

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/profile")
    public Mono<String> profile(ServerWebExchange exchange) {
        return downstream.profile(exchange);
    }
}
~~~

### 6.9. Chạy local

~~~bash
gradle bootRun
curl -i http://localhost:8080/public/ping
~~~

Body kỳ vọng:

~~~json
{"status":"ok"}
~~~

Public ping không cần IdP. OAuth2 login thật ở /oauth2/authorization/training và /api/profile chỉ hoạt động sau khi thay demo endpoints bằng IdP/Resource Server thật, đăng ký callback và client secret phù hợp.

## 7. Test provider và manager không cần IdP thật

Tạo fake Token Endpoint bằng cách thay **ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>** trong RefreshTokenReactiveOAuth2AuthorizedClientProvider. Đây không phải mock chính bản thân provider: test gọi provider, OAuth2AuthorizedClient và manager thật của Spring Security. StepVerifier subscribe và xác minh publisher.

Tệp **src/test/java/example/refresh/RefreshFlowTest.java**:

~~~java
package example.refresh;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.RefreshTokenReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class RefreshFlowTest {

    private static ClientRegistration registration() {
        return ClientRegistration.withRegistrationId("training")
                .clientId("test-client")
                .clientSecret("test-secret")
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationUri(
                        "https://idp.example.org/oauth2/authorize")
                .tokenUri("https://idp.example.org/oauth2/token")
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("profile", "offline_access")
                .build();
    }

    private static Authentication principal() {
        return UsernamePasswordAuthenticationToken.authenticated(
                "alice", "unused-mock-password",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static OAuth2AuthorizedClient expiredClient() {
        Instant now = Instant.now();
        OAuth2AccessToken old = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "access-old",
                now.minusSeconds(600),
                now.minusSeconds(120),
                Set.of("profile"));
        return new OAuth2AuthorizedClient(
                registration(), "alice", old,
                new OAuth2RefreshToken(
                        "refresh-old", now.minusSeconds(600)));
    }

    private static OAuth2AccessTokenResponse rotated() {
        return OAuth2AccessTokenResponse
                .withToken("access-new")
                .tokenType(OAuth2AccessToken.TokenType.BEARER)
                .expiresIn(900)
                .refreshToken("refresh-new")
                .scopes(Set.of("profile"))
                .build();
    }

    @Test
    void expiredTokenRefreshesAndRotates() {
        AtomicInteger calls = new AtomicInteger();
        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();

        provider.setAccessTokenResponseClient(request -> {
            calls.incrementAndGet();
            assertEquals("refresh-old",
                    request.getRefreshToken().getTokenValue());
            return Mono.just(rotated());
        });

        StepVerifier.create(provider.authorize(
                OAuth2AuthorizationContext
                        .withAuthorizedClient(expiredClient())
                        .principal(principal()).build()))
                .assertNext(updated -> {
                    assertEquals("access-new",
                            updated.getAccessToken().getTokenValue());
                    assertNotNull(updated.getRefreshToken());
                    assertEquals("refresh-new",
                            updated.getRefreshToken().getTokenValue());
                })
                .verifyComplete();

        assertEquals(1, calls.get());
    }

    @Test
    void validAccessTokenDoesNotRefresh() {
        Instant now = Instant.now();
        OAuth2AccessToken access = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "access-still-valid",
                now.minusSeconds(10),
                now.plusSeconds(1200));
        OAuth2AuthorizedClient current = new OAuth2AuthorizedClient(
                registration(), "alice", access,
                new OAuth2RefreshToken(
                        "refresh-old", now.minusSeconds(10)));

        AtomicInteger calls = new AtomicInteger();
        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setAccessTokenResponseClient(request -> {
            calls.incrementAndGet();
            return Mono.just(rotated());
        });

        StepVerifier.create(provider.authorize(
                OAuth2AuthorizationContext
                        .withAuthorizedClient(current)
                        .principal(principal()).build()))
                .verifyComplete();

        assertEquals(0, calls.get());
    }

    @Test
    void clockSkewRefreshesBeforeActualExpiry() {
        Instant fixed = Instant.parse("2026-11-07T00:00:00Z");
        OAuth2AccessToken access = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "access-near",
                fixed.minusSeconds(600),
                fixed.plusSeconds(30));
        OAuth2AuthorizedClient current = new OAuth2AuthorizedClient(
                registration(), "alice", access,
                new OAuth2RefreshToken(
                        "refresh-old", fixed.minusSeconds(600)));

        AtomicInteger calls = new AtomicInteger();
        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setClock(Clock.fixed(fixed, ZoneOffset.UTC));
        provider.setClockSkew(Duration.ofSeconds(60));
        provider.setAccessTokenResponseClient(request -> {
            calls.incrementAndGet();
            return Mono.just(rotated());
        });

        StepVerifier.create(provider.authorize(
                OAuth2AuthorizationContext
                        .withAuthorizedClient(current)
                        .principal(principal()).build()))
                .assertNext(updated -> assertEquals("access-new",
                        updated.getAccessToken().getTokenValue()))
                .verifyComplete();
        assertEquals(1, calls.get());
    }

    @Test
    void missingRefreshTokenCannotRunRefreshGrant() {
        OAuth2AuthorizedClient old = expiredClient();
        OAuth2AuthorizedClient noRefresh = new OAuth2AuthorizedClient(
                old.getClientRegistration(),
                old.getPrincipalName(),
                old.getAccessToken());

        AtomicInteger calls = new AtomicInteger();
        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setAccessTokenResponseClient(request -> {
            calls.incrementAndGet();
            return Mono.just(rotated());
        });

        StepVerifier.create(provider.authorize(
                OAuth2AuthorizationContext
                        .withAuthorizedClient(noRefresh)
                        .principal(principal()).build()))
                .verifyComplete();
        assertEquals(0, calls.get());
    }

    @Test
    void managerPersistsNewAccessAndRotatedRefreshToken() {
        var registrations =
                new InMemoryReactiveClientRegistrationRepository(
                        registration());
        var store =
                new InMemoryReactiveOAuth2AuthorizedClientService(
                        registrations);

        AtomicInteger calls = new AtomicInteger();
        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setAccessTokenResponseClient(request -> {
            calls.incrementAndGet();
            return Mono.just(rotated());
        });

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, store);
        manager.setAuthorizedClientProvider(provider);

        Authentication alice = principal();
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                .withClientRegistrationId("training")
                .principal(alice).build();

        Mono<OAuth2AuthorizedClient> flow =
                store.saveAuthorizedClient(expiredClient(), alice)
                        .then(manager.authorize(request))
                        .flatMap(updated -> store.loadAuthorizedClient(
                                "training", "alice")
                                .map(saved -> {
                                    assertEquals("access-new",
                                            saved.getAccessToken()
                                                    .getTokenValue());
                                    assertNotNull(saved.getRefreshToken());
                                    assertEquals("refresh-new",
                                            saved.getRefreshToken()
                                                    .getTokenValue());
                                    return updated;
                                }));

        StepVerifier.create(flow)
                .assertNext(updated -> assertEquals("access-new",
                        updated.getAccessToken().getTokenValue()))
                .verifyComplete();

        assertEquals(1, calls.get());
    }

    @Test
    void invalidGrantRemovesSavedAuthorizedClient() {
        var registrations =
                new InMemoryReactiveClientRegistrationRepository(
                        registration());
        var store =
                new InMemoryReactiveOAuth2AuthorizedClientService(
                        registrations);

        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setAccessTokenResponseClient(request ->
                Mono.error(new OAuth2AuthorizationException(
                        new OAuth2Error("invalid_grant"))));

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, store);
        manager.setAuthorizedClientProvider(provider);

        Authentication alice = principal();
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                .withClientRegistrationId("training")
                .principal(alice).build();

        Mono<String> flow =
                store.saveAuthorizedClient(expiredClient(), alice)
                        .then(manager.authorize(request)
                                .onErrorResume(
                                        OAuth2AuthorizationException.class,
                                        error -> Mono.empty()))
                        .then(store.loadAuthorizedClient(
                                "training", "alice")
                                .map(ignored -> "STILL_SAVED")
                                .defaultIfEmpty("REMOVED"));

        StepVerifier.create(flow)
                .expectNext("REMOVED")
                .verifyComplete();
    }
}
~~~

### 7.1. Chạy và đánh giá test

~~~bash
gradle test
~~~

**Kỳ vọng:** 6 tests PASS và BUILD SUCCESSFUL khi dependencies/JDK tương thích. Đây là kết quả kỳ vọng từ code, không phải tuyên bố đã chạy build thực tế.

Bộ test chứng minh:

- Token đã hết hạn + refresh hợp lệ → fake Token Endpoint được gọi một lần và trả access mới, refresh đã rotate.
- Token còn hạn xa → provider trả Mono.empty, không refresh không cần thiết.
- Clock.fixed + skew 60 giây → token còn 30 giây đã cần refresh.
- Không có refresh token → refresh grant không hoạt động.
- Manager service-level lưu token mới theo đúng registrationId/principal và đọc lại được.
- invalid_grant được default failure handler loại authorized client cũ trong test.

**Giới hạn:** test không chạm HTTPS/IdP thật, không xác minh redirect/state/PKCE, client secret/issuer, revocation thực và resource server. Cần test end-to-end trong staging.

### 7.2. Vì sao không block?

Không làm trong WebFlux handler:

~~~java
// Không dùng trên reactive event loop:
OAuth2AuthorizedClient client = manager.authorize(request).block();
~~~

Dùng WebClient filter hoặc compose Mono bằng flatMap/then để framework quản lý subscription. Trong unit test dùng StepVerifier.

## 8. Resource Server 401/403, lỗi refresh và cách xử lý

### 8.1. Hai constructor WebClient filter

Nếu tạo:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager)
~~~

Javadoc Spring Security 6.5 ghi rõ filter **không tự cài failure handler** cho Resource Server 401/403. Khi muốn xóa cached authorized client không còn hợp lệ theo downstream Bearer invalid_token, cần cấu hình RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler phù hợp repository/service và test.

Nếu tạo:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        clientRegistrations, authorizedClientRepository)
~~~

constructor này có default failure handler cho một số OAuth2 error codes, nhưng dùng strategy quản lý riêng; không tự áp dụng các tùy chỉnh manager khác nếu chưa tích hợp. Không mặc định request bị 401 sẽ tự được replay.

### 8.2. Phân loại sự cố

| Tình huống | Cần làm |
| --- | --- |
| Access token còn hạn | Dùng token hiện tại |
| Token sắp hết và có refresh token | Refresh với AS, persist cặp mới |
| Không có refresh token | Reauthorize/login user hoặc grant khác |
| invalid_grant do refresh đã revoke | Xóa token lỗi theo policy, yêu cầu authorize lại |
| invalid_client | Kiểm tra client secret/certificate/config, cảnh báo vận hành |
| Token Endpoint timeout hoặc 5xx | Fail closed, retry giới hạn/backoff; không coi là user sai password |
| 429 từ AS | Tôn trọng Retry-After, jitter, hạn chế thundering herd |
| Resource Server 401 invalid_token | Xem token revocation/failure handler, reauthorize có kiểm soát |
| Resource Server 403 insufficient_scope | Cần quyền/consent, không tự refresh thành admin |
| Nhiều requests rotate cùng refresh token | Lock/CAS/version, tránh mất token mới |
| Logout, revoke consent | Cleanup đúng authorized client và session |

Không retry cùng refresh token cũ vô hạn khi bị invalid_grant hoặc timeout, vì token rotation có thể đã xảy ra phía AS. Không tự replay POST thay đổi trạng thái sau 401 nếu không có idempotency policy; request có thể đã tạo side effect.

### 8.3. Quan sát an toàn

Nên đo registrationId, grant type, token seconds-to-expiry, result category, latency, error code và correlationId. Không log raw Authorization header, token endpoint form/JSON response, code verifier, client secret hoặc refresh token. Metric labels không nên chứa raw principal/email.

## 9. Checklist production và tình huống nhiều node

1. Lấy client secret từ vault/secret store; không commit secret thật.
2. Đăng ký redirect URI chính xác, state và PKCE theo client type.
3. Dùng HTTPS/TLS có xác thực chứng chỉ ở browser, AS và Resource Server.
4. Lưu refresh token server-side trong kho mã hóa, giới hạn quyền truy cập.
5. Chọn shared store/TTL hợp lý khi nhiều replicas; in-memory store chỉ dùng demo.
6. Đồng bộ clock, đặt clockSkew theo TTL/latency thực.
7. Phân biệt request HTTP user với background job, chọn manager phù hợp.
8. Không gắn Bearer token vào host do user chọn, chống SSRF/exfiltration.
9. Giữ token theo principal/tenant; không dùng static global token.
10. Khi rotation one-time, single-flight và CAS/version để chống xóa R2 vì lỗi R1.
11. Logout/revoke cần xóa authorized client tương ứng và phối hợp IdP.
12. Xử lý invalid_grant khác invalid_client/429/5xx; retry có giới hạn.
13. Test expired, near expiry, no-refresh-token, rotation, persistence, revoked token.
14. Test 401/403 downstream độc lập với refresh trước expiry.
15. Không tự tắt CSRF cho browser cookie chỉ vì dùng OAuth2 Client.
16. Test HTTPS, issuer, redirect, consent, token scope và Resource Server trên IdP thật.

### 9.1. Quy trình end-to-end khi có IdP staging

1. Đăng ký client và callback chính xác với nhà cung cấp thật; dùng tài khoản thử.
2. Truy cập /oauth2/authorization/training, hoàn tất login/consent.
3. Gọi /api/profile bằng cùng browser session, xác nhận đúng danh tính downstream.
4. Cấu hình access token TTL ngắn để dễ chạm ngưỡng refresh.
5. Gọi lại API lúc token đến cửa sổ skew và kiểm tra AS nhận refresh_token grant.
6. Xác nhận cặp access/refresh mới được lưu, nếu rotation thì lần sau dùng R2.
7. Revoke token ở IdP test, xác nhận không refresh/login loop.
8. Gửi nhiều requests song song và qua nhiều node để kiểm tra consistency.
9. Soát logs/token redaction và HTTPS/public proxy behavior.
10. Đánh giá lỗ hổng replay, refresh token reuse detection và request retries.

## 10. Bài tập và tự đánh giá

1. OAuth2 Client có được tự phát access token mới không?
2. Access token và refresh token dùng ở hai endpoint nào?
3. expires_in = 900 biểu diễn giây hay timestamp?
4. Token hết hạn 10:05, skew 60 giây; request 10:04:20 có cần refresh không?
5. Khi không có refresh token, authorization_code user nên làm gì?
6. Client credentials thường xin token mới theo grant nào?
7. Vì sao phải lưu refresh token mới sau rotation?
8. Vì sao không dùng một static token cho tất cả users?
9. Một downstream 403 insufficient_scope có nên tạo vòng refresh vô hạn không?
10. Vì sao test Clock.fixed tốt hơn Thread.sleep?
11. Khi request B nhận invalid_grant vì A đã rotate R1 thành R2, cần tránh lỗi gì?
12. Vì sao 401 Resource Server khác invalid_grant Token Endpoint?
13. Nếu Token Endpoint trả 503, nên xử lý khác invalid_grant thế nào?
14. Khi user logout, authorized client cần được làm gì?
15. Vì sao fake response test không thay thế kiểm thử IdP thật?

**Đáp án:** (1) Không, chỉ AS; (2) access tới Resource Server, refresh tới Token Endpoint; (3) số giây; (4) có vì còn 40 giây nhỏ hơn skew; (5) xin authorize/login lại; (6) client_credentials; (7) R1 có thể đã bị revoke; (8) tránh lẫn token A/B; (9) không, thiếu scope cần quyền/consent; (10) deterministic; (11) không xóa R2 mới vì lỗi R1 cũ; (12) access bị từ chối ở resource khác refresh grant không hợp lệ; (13) lỗi tạm cần backoff/503, không xóa tùy tiện; (14) cleanup/revoke theo policy; (15) chưa test TLS, issuer, redirect, scopes và giao thức thật.

## 11. Tài liệu tham khảo

- Spring Security 6.5 — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html
- Spring Security 6.5 — Reactive Authorized Clients: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html
- Spring Security 6.5 — OAuth2 Authorization Grants: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html
- Spring Security 6.5 Javadoc — RefreshTokenReactiveOAuth2AuthorizedClientProvider: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/RefreshTokenReactiveOAuth2AuthorizedClientProvider.html
- Spring Security 6.5 Javadoc — DefaultReactiveOAuth2AuthorizedClientManager: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/DefaultReactiveOAuth2AuthorizedClientManager.html
- Spring Security 6.5 Javadoc — ServerOAuth2AuthorizedClientExchangeFilterFunction: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- RFC 6749 §6 — Refresh Access Token: https://www.rfc-editor.org/rfc/rfc6749.html#section-6
- RFC 6750 — Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700.html
- OWASP OAuth2 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html

**Kết luận:** ReactiveOAuth2AuthorizedClientManager phối hợp RefreshTokenReactiveOAuth2AuthorizedClientProvider để xin access token mới từ Authorization Server khi token sắp hết hạn và refresh token còn hợp lệ. Hãy lưu OAuth2AuthorizedClient đã được rotate, dùng WebClient filter gắn Bearer, không rò refresh token, xử lý invalid_grant đúng cách và bảo vệ concurrent refresh trong hệ multi-node.