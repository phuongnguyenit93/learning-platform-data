# Gọi API bên ngoài bằng WebClient và OAuth2 Client Credentials

> **Học phần:** Spring Security - reactive → Thực hành tổng hợp. Bài thực hành xây dựng một dịch vụ Spring WebFlux dùng **WebClient** gọi API của đối tác được bảo vệ bằng OAuth2 **Client Credentials**, đồng thời giải thích cách cấp token, gắn Bearer token, tái sử dụng token, xử lý hết hạn/lỗi và kiểm thử đường đi đến token endpoint lẫn resource API.

## 1. Tình huống, mục tiêu và giới hạn

Giả sử dịch vụ **catalog-sync** cần gọi **GET /v1/status** của **partner-api**. Hai hệ thống giao tiếp ở phía server. **catalog-sync** được cấp **client_id/client_secret** và scope **partner.read** từ Authorization Server; người dùng không tham gia cấp quyền trên từng request. Dịch vụ phải lấy access token trước khi gọi API và gửi token trong header:

~~~http
GET /v1/status HTTP/1.1
Host: partner-api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Mục tiêu:

1. Hiểu đúng các bên trong OAuth2 Client Credentials: **client**, **authorization server** (AS), **resource server** (RS), và **access token**.
2. Cấu hình đăng ký OAuth2 client, token endpoint, scope và client authentication trong Spring Security.
3. Dùng **ReactiveOAuth2AuthorizedClientManager** dành cho tác vụ dịch vụ không phụ thuộc HTTP request từ người dùng.
4. Dùng WebClient gửi token đúng API, tránh gửi nhầm credential sang host khác.
5. Giải thích caching/renewal token, timeout, retry, lỗi 401/403/429/5xx và observability.
6. Chạy integration test với token endpoint/API giả lập để xác minh **grant_type=client_credentials**, Authorization header và việc tái sử dụng token.
7. Biết giới hạn của demo so với cấu hình TLS, secret manager, chính sách scope và IdP thật.

Bài dùng Java 17, Spring Boot 3.3.x/Spring Security 6.x và Reactor. Ví dụ demo **không** mô phỏng user delegation hoặc OAuth2 Authorization Code. Đối với API thay mặt từng người dùng, phải thiết kế luồng ủy quyền phù hợp thay vì dùng client credentials rồi tự nhận danh tính người dùng.

## 2. Luồng Client Credentials trong ứng dụng reactive

~~~text
catalog-sync (OAuth2 Client)              Authorization Server
         |                                          |
         |  POST /oauth/token                       |
         |  Authorization: Basic base64(id:secret)  |
         |  Content-Type: application/x-www-form-urlencoded
         |  grant_type=client_credentials           |
         |  scope=partner.read                      |
         |----------------------------------------->|
         |<-----------------------------------------|
         |  200 {"access_token":"...",              |
         |       "token_type":"Bearer",             |
         |       "expires_in":3600}                 |
         |                                          |
         |             Partner Resource Server      |
         |  GET /v1/status                          |
         |  Authorization: Bearer <access_token>    |
         |----------------------------------------->|
         |<-----------------------------------------|
         |  200 {"status":"ready"}                  |
~~~

**Authorization Server** xác thực ứng dụng client, đánh giá scope/audience được phép và phát hành token. **Resource Server** kiểm tra token theo hợp đồng của IdP (chữ ký JWT hoặc introspection opaque token), issuer, audience, thời hạn và scope trước khi cấp quyền. **WebClient** ở catalog-sync là **OAuth2 Client** gửi request đi; nó không tự biến catalog-sync thành Resource Server xác minh request đi vào.

Các thuộc tính quan trọng:

- Grant gửi **grant_type=client_credentials**. OAuth2 không yêu cầu luôn dùng HTTP Basic; kiểu **client_secret_basic**, **client_secret_post**, private_key_jwt hoặc mTLS tùy Authorization Server. Demo chọn **client_secret_basic**.
- Request thành công thường trả **access_token**, **token_type=Bearer**, **expires_in**, có thể có **scope**. RFC 6749 không yêu cầu cấp refresh token với grant Client Credentials; thông thường khi gần hết hạn, client xin access token mới.
- Token là quyền của **ứng dụng** theo scope và chính sách của AS; **sub/client_id** có thể biểu diễn client, không phải người dùng đang gọi vào catalog-sync.
- JWT và opaque access token đều có thể dùng với Client Credentials. OAuth2 Client không cần tự giải mã JWT để gửi token; Resource Server chịu trách nhiệm xác thực/ủy quyền.
- Đừng nhầm **client secret** với **access token**: client secret chỉ truyền theo token request đến AS; access token là credential ngắn hạn gửi tới RS được phép.

Với tải nhiều request, Spring Security có thể lưu **OAuth2AuthorizedClient** gắn với **ClientRegistration** và principal name ổn định, rồi dùng access token đang còn hạn. Mỗi request không nhất thiết phải gọi token endpoint. Chính sách cấp token có thể bị IdP giới hạn, vì vậy đo cả số token requests và số API requests.

## 3. Chọn đúng thành phần Spring Security reactive

| Thành phần | Vai trò |
| --- | --- |
| **ReactiveClientRegistrationRepository** | Lưu cấu hình registration: client ID/secret, token URI, grant và scope |
| **ReactiveOAuth2AuthorizedClientService** | Lưu/tra authorized client/token theo registration và principal |
| **ReactiveOAuth2AuthorizedClientProvider** | Cài đặt grant được cho phép, ở đây chỉ **clientCredentials()** |
| **AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager** | Cấp/lưu authorized client **ngoài ServerWebExchange**, phù hợp tác vụ nền và service-to-service |
| **DefaultReactiveOAuth2AuthorizedClientManager** | Dành cho trường hợp gắn với request **ServerWebExchange** |
| **ServerOAuth2AuthorizedClientExchangeFilterFunction** | Gắn access token vào WebClient request |
| **OAuth2AuthorizeRequest** | Yêu cầu authorize, chỉ rõ registration ID và principal |

**Vì sao không mặc định dùng ServerWebExchange?** Scheduled job, Kafka consumer hoặc một service không có HTTP request đầu vào vẫn cần danh tính ứng dụng. Trường hợp đó dùng **AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager**; khi authorize truyền một principal name cố định như **catalog-sync-service**. Đây là **khóa quản lý token**, không phải cách giả mạo user cho resource server.

Nhiều ví dụ trực tuyến dùng **OAuth2AuthorizedClientManager**, **ServletOAuth2AuthorizedClientExchangeFilterFunction** và **HttpSecurity**. Đó là stack servlet. WebFlux cần đúng các lớp **Reactive...**, **ServerOAuth2...**. Không tự gọi HTTP token endpoint rồi ghép JSON token nếu framework OAuth2 Client đã giải quyết expiry, caching và association.

Trong context có ServerWebExchange, cũng có thể dùng **ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId("partner")** với principal thích hợp. Với tác vụ nền, bài này gọi **manager.authorize()** tường minh để cấp authorized client cho một service principal, sau đó gắn **oauth2AuthorizedClient(...)** vào WebClient request. Hai cách không nên trộn tùy tiện.

## 4. Project Java 17 + Spring Boot 3.3: mã hoàn chỉnh

Demo dùng một Spring Boot application cung cấp **PartnerClient**. Integration test khởi động **MockWebServer** làm cả token endpoint và resource API. Khi chạy test không cần IdP, credential hoặc API ngoài thật.

~~~text
client-credentials-demo/
├─ settings.gradle
├─ build.gradle
├─ src/main/resources/application.yml
├─ src/main/java/example/oauth/ClientCredentialsApplication.java
└─ src/test/java/example/oauth/PartnerClientIntegrationTest.java
~~~

### 4.1 Gradle

**settings.gradle**

~~~groovy
rootProject.name = 'client-credentials-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không cần **spring-boot-starter-oauth2-resource-server** để catalog-sync **chỉ gọi API đi** bằng client credentials. Nếu ứng dụng đồng thời xác minh Bearer JWT ở request **đi vào**, cần thêm Resource Server và **SecurityWebFilterChain** theo hợp đồng inbound; đây là nhiệm vụ khác với việc lấy token outbound.

### 4.2 Cấu hình ClientRegistration và secret

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - partner.read
        provider:
          partner:
            token-uri: ${PARTNER_TOKEN_URI}

partner:
  api-base-url: ${PARTNER_API_BASE_URL}
~~~

- **partner** là registration ID do ứng dụng đặt, phải khớp với tham số ở **OAuth2AuthorizeRequest**.
- **token-uri** là endpoint của Authorization Server; **api-base-url** là host của Resource Server; thường là hai hệ thống/host khác nhau.
- **client-id/client-secret** được inject từ environment hoặc secret manager. Không hardcode secret thật trong source, log hoặc test output.
- **scope** là quyền client yêu cầu. Scope được cấp có thể hẹp hơn và Resource Server quyết định action thực tế.
- Với API/IdP production, dùng HTTPS xác thực certificate, không tắt certificate verification cho “dễ kết nối”.
- Test ở mục 5 dùng **@DynamicPropertySource** thay các giá trị cấu hình bằng endpoint local và credential thử, nên chạy test không cần secret thật.

Để chạy app độc lập, cung cấp các biến **PARTNER_CLIENT_ID**, **PARTNER_CLIENT_SECRET**, **PARTNER_TOKEN_URI**, **PARTNER_API_BASE_URL** hợp lệ. Demo không có scheduler/controller tự gọi đối tác; phương thức **PartnerClient.status()** được gọi từ integration test hoặc nghiệp vụ có chủ đích.

### 4.3 Ứng dụng, manager và WebClient

**src/main/java/example/oauth/ClientCredentialsApplication.java**

~~~java
package example.oauth;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@SpringBootApplication
public class ClientCredentialsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientCredentialsApplication.class, args);
    }
}

@Configuration
class PartnerOAuthConfiguration {
    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        // Demo: token trong bộ nhớ theo từng application instance.
        return new InMemoryReactiveOAuth2AuthorizedClientService(registrations);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService clients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, clients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("partnerWebClient")
    WebClient partnerWebClient(
            WebClient.Builder builder,
            ReactiveOAuth2AuthorizedClientManager manager,
            @Value("${partner.api-base-url}") String apiBaseUrl) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        // Client riêng cho đúng Resource Server: không bật gửi token
        // mặc định trên mọi WebClient của ứng dụng.
        return builder
                .baseUrl(apiBaseUrl)
                .filter(oauth2)
                .build();
    }
}

record PartnerStatus(String status) {}

@Service
class PartnerClient {
    private static final String REGISTRATION = "partner";
    private static final String SERVICE_PRINCIPAL = "catalog-sync-service";

    private final WebClient webClient;
    private final ReactiveOAuth2AuthorizedClientManager manager;

    PartnerClient(
            @Qualifier("partnerWebClient") WebClient webClient,
            ReactiveOAuth2AuthorizedClientManager manager) {
        this.webClient = webClient;
        this.manager = manager;
    }

    Mono<PartnerStatus> status() {
        OAuth2AuthorizeRequest authorizationRequest =
                OAuth2AuthorizeRequest.withClientRegistrationId(REGISTRATION)
                        .principal(SERVICE_PRINCIPAL)
                        .build();

        return manager.authorize(authorizationRequest)
                .switchIfEmpty(Mono.error(new IllegalStateException(
                        "Authorization Server did not authorize partner client")))
                .flatMap(authorizedClient ->
                        webClient.get()
                                .uri("/v1/status")
                                .attributes(oauth2AuthorizedClient(authorizedClient))
                                .retrieve()
                                .bodyToMono(PartnerStatus.class));
    }
}
~~~

**Giải thích đường gọi:**

1. **status()** tạo OAuth2AuthorizeRequest cho registration **partner** và principal cố định **catalog-sync-service**. Không dùng username từ incoming request.
2. **manager.authorize(...)** trả **Mono<OAuth2AuthorizedClient>**. Nếu chưa có token, provider **clientCredentials()** gọi token endpoint bằng HTTP client reactive. Nếu token còn hạn và đã lưu, manager có thể dùng lại.
3. **switchIfEmpty(...)** ngăn tình trạng không có authorized client bị hiểu nhầm thành request thiếu xác thực hợp lệ.
4. **oauth2AuthorizedClient(authorizedClient)** truyền client/token cho OAuth2 filter; filter gắn **Authorization: Bearer ...** vào request GET đúng API.
5. **retrieve().bodyToMono(PartnerStatus.class)** nhận JSON và phát lỗi reactive khi nhận HTTP lỗi.
6. Không có **block()** hay **subscribe()** thủ công trong service. Caller quản lý subscription, cancellation và timeout.

Principal ổn định cho phép **authorized-client service** tái sử dụng token thuộc cùng registration. Trong ứng dụng nhiều tenant có nhiều **client credentials khác nhau**, không chia sẻ principal/registration và token tùy tiện giữa tenant; phân vùng cấu hình/token theo chính sách IdP.

**Tại sao không gọi setDefaultOAuth2AuthorizedClient(true)?** Tùy chọn đó có thể gắn token vào request không chủ đích khi dùng WebClient chung. Demo đưa authorized client **tường minh** và chỉ tạo WebClient chuyên dùng cho API đối tác. Cũng không dùng token lấy từ header inbound nếu không có hợp đồng token relay/token exchange.

## 5. Integration test: token endpoint + API giả lập

MockWebServer trả access token thử và JSON giả lập. Test khởi động Spring context thật, đi qua **ReactiveOAuth2AuthorizedClientManager → token endpoint HTTP → WebClient filter → resource API HTTP**. Đây là kiểm thử client credentials ở mức giao thức HTTP, nhưng không thử xác thực chữ ký, introspection, TLS hay ủy quyền thực của partner Resource Server.

**src/test/java/example/oauth/PartnerClientIntegrationTest.java**

~~~java
package example.oauth;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class PartnerClientIntegrationTest {
    private static final MockWebServer SERVER = startServer();

    @Autowired
    PartnerClient partner;

    private static MockWebServer startServer() {
        try {
            MockWebServer server = new MockWebServer();
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry properties) {
        properties.add(
                "spring.security.oauth2.client.registration.partner.client-id",
                () -> "demo-client");
        properties.add(
                "spring.security.oauth2.client.registration.partner.client-secret",
                () -> "demo-secret");
        properties.add(
                "spring.security.oauth2.client.provider.partner.token-uri",
                () -> SERVER.url("/oauth/token").toString());
        properties.add(
                "partner.api-base-url",
                () -> SERVER.url("/").toString());
    }

    @AfterAll
    static void shutDown() throws IOException {
        SERVER.shutdown();
    }

    @Test
    void obtainsClientCredentialsTokenAndReusesItForApiCalls()
            throws InterruptedException {

        // Request 1: token endpoint.
        SERVER.enqueue(new MockResponse()
                .addHeader("Content-Type", "application/json")
                .setBody("""
                    {
                      "access_token": "demo-access-token",
                      "token_type": "Bearer",
                      "expires_in": 3600,
                      "scope": "partner.read"
                    }
                    """));

        // Requests 2 và 3: resource API.
        for (int i = 0; i < 2; i++) {
            SERVER.enqueue(new MockResponse()
                    .addHeader("Content-Type", "application/json")
                    .setBody("{\"status\":\"ready\"}"));
        }

        StepVerifier.create(partner.status())
                .assertNext(result -> assertEquals("ready", result.status()))
                .verifyComplete();

        StepVerifier.create(partner.status())
                .assertNext(result -> assertEquals("ready", result.status()))
                .verifyComplete();

        RecordedRequest token = SERVER.takeRequest(5, TimeUnit.SECONDS);
        RecordedRequest firstApi = SERVER.takeRequest(5, TimeUnit.SECONDS);
        RecordedRequest secondApi = SERVER.takeRequest(5, TimeUnit.SECONDS);

        assertNotNull(token, "Expected a token endpoint call");
        assertNotNull(firstApi, "Expected first resource call");
        assertNotNull(secondApi, "Expected second resource call");

        assertEquals("/oauth/token", token.getPath());
        assertEquals("POST", token.getMethod());
        assertTrue(token.getHeader("Authorization").startsWith("Basic "));
        assertTrue(token.getBody().readUtf8()
                .contains("grant_type=client_credentials"));

        assertEquals("/v1/status", firstApi.getPath());
        assertEquals("/v1/status", secondApi.getPath());
        assertEquals("Bearer demo-access-token",
                firstApi.getHeader("Authorization"));
        assertEquals("Bearer demo-access-token",
                secondApi.getHeader("Authorization"));

        // Một lần xin token, hai lần gọi API trong cùng token lifetime.
        assertEquals(3, SERVER.getRequestCount());
    }
}
~~~

**Chạy** ở thư mục có **build.gradle**:

~~~bash
gradle test --tests example.oauth.PartnerClientIntegrationTest
~~~

Hoặc nếu đã có Gradle Wrapper tương thích:

~~~bash
./gradlew test --tests example.oauth.PartnerClientIntegrationTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.oauth.PartnerClientIntegrationTest
~~~

**Đầu ra kỳ vọng:** build test thành công, bài test **obtainsClientCredentialsTokenAndReusesItForApiCalls** pass. Stdout Gradle thay đổi theo version/cache, nên không gán một log cố định là bằng chứng. Các assertion chính là hợp đồng: request đầu là **POST /oauth/token**, request sau là **GET /v1/status**, Bearer token đúng và chỉ một lần lấy token trong thời gian còn hạn.

**Độ tin cậy và giới hạn:** token giả **demo-access-token** được Resource Server mock chấp nhận nguyên trạng. Test kiểm client gửi credential, **không** xác nhận token thật được RS xác minh. Test dựa vào OAuth2AuthorizedClientService lưu token cùng application context; nếu thay storage, principal, registration hoặc process, cần kiểm caching riêng.

## 6. Token reuse, expiration và scope

### 6.1 Cache token

**InMemoryReactiveOAuth2AuthorizedClientService** lưu authorized client ở bộ nhớ mỗi instance. **manager.authorize()** với cùng registration ID + principal name có thể dùng lại token còn hạn; khi gần hết hạn, provider client_credentials xin token mới theo thời hạn và clock skew của framework. Đây thường là **cấp access token mới**, không phải refresh token flow.

Không dựa vào **expires_in=3600** mà giả định token hiệu lực đúng 3.600 giây tại mọi node: network latency, clock skew và chính sách IdP có thể ảnh hưởng. Đo lại trên runtime cụ thể.

### 6.2 Khi ứng dụng có nhiều replica

Mỗi replica với in-memory service giữ token **riêng**; 10 replica khởi động đồng thời có thể phát sinh 10 token requests. Điều này có thể hợp lệ nhưng cần tính rate limit/capacity IdP. Nếu dùng store phân tán hoặc cache tùy chỉnh, chú ý mã hóa credential, TTL, race khi hết hạn, cách ly tenant, eviction và thu hồi quyền. Không lưu Bearer token vĩnh viễn trong static field.

### 6.3 Scope, audience và resource

Scope **partner.read** là quyền client yêu cầu; quyền cuối cùng do AS cấp và RS kiểm. **Audience** của token (khi có theo token format/IdP) phải đúng API nhận token. Client không thể tạo audience đáng tin bằng cách sửa JWT payload. Client Credentials không thay thế **mTLS/HTTPS** nếu hợp đồng đối tác yêu cầu.

Khi API trả **403**, kiểm scope/role/policy; khi trả **401**, kiểm expired/revoked, issuer/audience và các lỗi token. Không tự động tăng quyền hoặc gửi token sang host khác để thử.

## 7. Bộ test cần bổ sung cho hệ thống thực

Với từng tình huống, stub AS/RS theo thứ tự thực phát sinh, kiểm request count, status/exception, latency và side effect:

| Tình huống | Stub/đầu vào | Kết quả cần assert |
| --- | --- | --- |
| Cấp token lần đầu | AS trả 200 + Bearer + expires_in | AS nhận POST client_credentials; API có Bearer |
| Reuse token | Gọi hai API khi token còn hạn | Không xin token lại vô ích với cùng client/principal |
| Sai client secret | AS trả **invalid_client** hoặc 401 | Không gọi API với Bearer giả; pipeline phát lỗi |
| Scope bị từ chối | AS trả **invalid_scope** | Không sửa scope để vượt quyền; báo lỗi rõ |
| JSON token response sai | Thiếu access_token/token_type | Không gọi resource giả thành công |
| Access token hết hạn | Token fixture hết hạn/clock kiểm soát | Cấp token mới, không dùng token cũ |
| Resource API trả 401 | Response có WWW-Authenticate thích hợp | Không “allow”; không retry vô hạn |
| Resource API trả 403 | Token được chấp nhận nhưng thiếu quyền | Không tự nâng scope/client ID |
| AS timeout/TLS lỗi | Token endpoint không truy cập được | Fail closed; chưa có token thì không gọi resource |
| API timeout/429/5xx | AS cấp token nhưng downstream lỗi | Bounded timeout, retry có chọn lọc |
| API host bị đổi | Redirect/config/URI tuyệt đối ngoài allowlist | Không tiết lộ Bearer token |
| Burst request | Nhiều request đồng thời | Đo token storm, queue, pool và reuse |
| Tracing/log | Bật wire logging trong môi trường test | Không log client_secret/access token |

**Không đếm số lần gọi AS bằng cách tự đọc cache trước test:** thao tác đó dễ thay đổi state. Quan sát RecordedRequest từ mock server là bằng chứng mạnh hơn.

### Ví dụ test lỗi qua StepVerifier

~~~java
// Snippet ghép vào một test với mock AS đã enqueue response lỗi.
// Test độc lập phải có fixture chưa cache access token.
StepVerifier.create(partner.status())
        .expectError()
        .verify();

// Kiểm thêm số request HTTP và không có GET /v1/status
// khi Authorization Server chưa cấp token.
~~~

Đây là snippet bổ sung, không phải chương trình độc lập. Khi token đã cache từ test khác, request có thể bỏ qua AS; cần test context/registration/principal tách biệt hoặc reset storage có chủ đích. Với từng lỗi, assert **kiểu exception cụ thể** nếu application contract đã định nghĩa.

### Retry không được vô hạn

- **invalid_client, invalid_scope, 401/403 do quyền:** retry lặp lại thường không sửa được cấu hình.
- **429/503/transient network:** retry **có giới hạn** với backoff, jitter và Retry-After, sau khi kiểm tổng timeout.
- **POST có side effect:** không tự retry sau timeout nếu thiếu idempotency key/hợp đồng chống lặp, vì request có thể đã xử lý xong dù response mất.
- **Token endpoint:** tránh mỗi downstream failure lại cấp token mới mãi. Invalidation/renew theo lỗi chính xác phải có giới hạn để tránh token storm.

## 8. Timeout, pool và quan sát vận hành

### 8.1 Hai kết nối HTTP phải được xem riêng

Có hai đường ra ngoài:

1. **Token endpoint** từ OAuth2 client framework.
2. **Resource API** do **partnerWebClient** gọi.

Tùy phiên bản Spring Security, HTTP client token endpoint được cấu hình qua **ReactiveOAuth2AccessTokenResponseClient**. Điều chỉnh Reactor Netty connector cho **partnerWebClient** **không mặc nhiên** đổi timeout, proxy, TLS hoặc pool của token client. Nếu triển khai qua mTLS/proxy, phải cấu hình và test cả hai đường. Với Spring Security 6.3+, tham khảo tùy biến token response client cho grant **client_credentials**.

Nên đo và giới hạn:

- Connect timeout: chờ TCP.
- Response timeout: chờ response.
- Pool acquire timeout: chờ connection.
- **Deadline tổng** từ nghiệp vụ: token acquisition + resource call + retry + queue.

Một **Mono.timeout(Duration.ofSeconds(...))** ở caller là lớp deadline tổng hữu ích nhưng không thay connect timeout hoặc giới hạn pool.

~~~java
// Caller đã inject PartnerClient; snippet không độc lập.
Mono<PartnerStatus> result =
        partner.status().timeout(java.time.Duration.ofSeconds(8));
~~~

Khi timeout/cancel, request HTTP phía server có thể đã nhận; không mặc định mutation đã rollback.

### 8.2 Metrics nên đo

| Nhóm | Cần quan sát | Mục tiêu |
| --- | --- | --- |
| AS/token | request p50/p95/p99, status 4xx/5xx, timeout | IdP chậm, credential sai, token storm |
| Token cache | token request count, reuse, expiry | Cache hoạt động và rotation |
| RS/API | RPS, p95/p99, 401/403/429/5xx, timeout | Phân biệt chính sách và downstream load |
| HTTP pool | active/pending connections, DNS/connect/TLS | Pool/network bottleneck |
| JVM/reactive | CPU, memory, event-loop blocking, scheduler queue | Tìm blocking hoặc saturation |
| Security | error code đã chuẩn hóa, registration ID | Debug mà không lộ token |

Không gắn **raw token, client secret, Authorization header, user-provided URL, response body chứa credential** vào metric label, span attribute hoặc log. Dùng tên registration/provider là tập hữu hạn. Nếu cần phân tích lỗi, log error code đã lọc bí mật.

**Quan sát concurrency:** khi nhiều request xảy ra cùng lúc token hết hạn, có thể có nhiều lệnh xin token tùy provider/scheduler/storage. Kiểm bằng tải thật/mock AS, không mặc định framework single-flight tuyệt đối.

## 9. Phân quyền inbound và outbound là hai trách nhiệm

~~~text
Incoming client ──JWT/session──> catalog-sync (WebFlux Resource Server)
                                    |
                                    | service principal + client_credentials
                                    v
                              Authorization Server
                                    |
                                    | access token của catalog-sync
                                    v
                              partner-api (Resource Server)
~~~

- **Incoming SecurityWebFilterChain** xác thực/ủy quyền caller vào catalog-sync.
- **Outgoing OAuth2 Client** lấy token với danh tính máy và scope dành cho partner-api.
- Không dùng token từ incoming client làm token outbound nếu chưa có hợp đồng token relay/token exchange.
- Nếu cần “gọi API thay mặt Alice”, Client Credentials **không mang consent/role của Alice**. Dùng Authorization Code, token exchange hoặc on-behalf-of flow được AS hỗ trợ.
- Không mở endpoint công khai để caller bất kỳ kích hoạt WebClient có quyền máy mạnh hơn nếu chưa có chính sách inbound.

**Ví dụ cấu hình inbound (chỉ minh họa, không thuộc project hoàn chỉnh mục 4):**

~~~java
@Bean
SecurityWebFilterChain inboundSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/health").permitAll()
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth ->
                    oauth.jwt(Customizer.withDefaults()))
            .build();
}
~~~

Snippet này cần imports **@Bean**, **SecurityWebFilterChain**, **ServerHttpSecurity**, **Customizer**, dependency **spring-boot-starter-oauth2-resource-server** và decoder/issuer/audience hợp lệ; không phải class độc lập. Bổ sung Resource Server inbound không thay cách authorize outbound trong mục 4.

## 10. Quyết định bảo mật và vận hành ở production

**Credential protection.** Dùng secret manager hoặc identity workload (mTLS/private_key_jwt nếu AS hỗ trợ), quyền đọc secret tối thiểu, rotation có quy trình. Không ghi secret plaintext vào repo, log hoặc query string. Token endpoint cấu hình sai có thể làm lộ Basic header, nên cần kiểm endpoint tin cậy ở deployment.

**Destination restriction.** WebClient chuyên biệt với base URL/host allowlist. Không nhận URI tuyệt đối từ query/body rồi gắn Bearer token đến host bất kỳ; kiểm redirect/proxy. Token cần được cấp đúng API theo resource/audience policy.

**Least privilege.** Mỗi đối tác/integration có registration và scope riêng; không cấp write khi chỉ cần read. Với multi-tenant, cách ly registration, store và credential, tránh cache key trùng.

**Fail closed.** Nếu AS không cấp token hoặc RS trả 401/403, không bypass OAuth2 hay dùng token đã hết hạn. Circuit breaker, timeout và throttling bảo vệ hệ thống nhưng không thay quyết định ủy quyền.

**Revocation.** Token có thể bị revoke trước thời điểm expires_in. RS có thể trả 401; xác định cách invalidate authorized client và cấp token mới theo lỗi phù hợp, giới hạn số lần. Không vòng lặp token storm.

**Safe diagnostics.** Redact Authorization header/token response/client credentials trong HTTP wire logging, exception, tracing và test artifacts. Không in nguyên request/response khi troubleshooting, kể cả staging.

**Idempotency.** Với GET an toàn có thể retry chọn lọc. Với POST/PUT/PATCH side effect cần idempotency key/correlation và cơ chế reconciliation; tránh xử lý giao dịch nhiều lần.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Xác minh/sửa |
| --- | --- | --- |
| Thiếu **ReactiveClientRegistrationRepository** | Chưa có OAuth2 client starter hoặc registration sai | Kiểm dependency/YAML/runtime |
| **Unsupported authorization grant** | Chưa bật clientCredentials() hoặc registration không hợp lệ | Kiểm provider/registration |
| manager.authorize() rỗng | Registration/principal/provider không phù hợp | Kiểm registration ID và grant |
| AS trả **invalid_client** | Sai ID/secret, kiểu client auth không đúng | Kiểm token endpoint và IdP, không in secret |
| AS trả **invalid_scope** | Scope yêu cầu vượt quyền | Rà policy, least privilege |
| 401 từ partner-api | Token expired/revoked, issuer/audience sai | Kiểm RS error contract, không chỉ kiểm có Bearer header |
| 403 từ partner-api | Thiếu scope hoặc rule của resource | So scope được cấp với policy |
| WebClient không có Bearer | Thiếu filter hoặc **oauth2AuthorizedClient(...)** | Assert request thực từ mock server |
| Token gửi sai API | Default token toàn cục, URI/redirect ngoài allowlist | Tách WebClient và kiểm host |
| Test context lỗi secret placeholder | Test chưa override YAML env vars | Dùng **@DynamicPropertySource** |
| HTTP timeout | AS hoặc RS chậm, pool cạn | Đo riêng hai đường, timeout/retry/pool |
| AS bị gọi mỗi request | Principal đổi, cache không dùng, token quá ngắn | Đếm request AS và xác minh expiry |
| Blocked event loop | RestTemplate, block(), HTTP sync trong handler | WebClient reactive, StepVerifier, profiling |
| Production lỗi TLS nhưng test xanh | MockWebServer HTTP không kiểm certificate/proxy | Thêm integration test HTTPS/mTLS |

Trong WebFlux tránh **.block()** và **.subscribe()** thủ công trong controller/service. Dùng **Mono<PartnerStatus>** trả về cho caller. Test CLI có thể chờ Mono để assert; demo dùng StepVerifier để thể hiện semantics reactive.

## 12. Bài tập mở rộng

1. **Expiry:** mock hai token khác nhau và thời hạn ngắn có kiểm soát; kiểm request sau khi token hết hạn dùng token mới, không dựa vào sleep dài.
2. **Scope:** AS trả scope thiếu partner.read hoặc RS trả 403; client không tự nâng quyền.
3. **AS timeout:** delay mock AS vượt timeout; kiểm không có resource request khi chưa cấp token.
4. **Unauthorized RS:** RS trả 401 kèm Bearer error; kiểm authorized-client invalidation/failure handler theo version thực.
5. **Concurrency:** Flux.range(...).flatMap(...) phát burst, đếm token vs API requests, đo pool và token storm.
6. **Hai registration:** partner-read và partner-write scope khác nhau; không dùng nhầm token.
7. **Multi-tenant:** credential và token tenant A không được sử dụng cho tenant B.
8. **Observability:** bật metrics/tracing đã redact, quan sát AS/RS errors và p95/p99.

Không bắt buộc mọi app phải có scheduler/controller. **PartnerClient.status()** tái sử dụng trong task queue, job định kỳ hoặc service handler WebFlux đã được bảo vệ bởi security inbound. Chọn điểm gọi theo nghiệp vụ, không expose quyền máy cho caller không đáng tin.

## 13. Checklist nghiệm thu

- Phân biệt OAuth2 **Client Credentials** với Authorization Code, JWT verification và token relay.
- Cấu hình **registration/provider**, **client_credentials**, scope, Basic client authentication, token URI và resource API base URL đúng.
- Dùng **AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager** cho service/background và một principal ổn định để reuse token.
- Gắn token bằng **ServerOAuth2AuthorizedClientExchangeFilterFunction** trên WebClient chuyên biệt, không leak Bearer sang host tùy ý.
- Không **block()/subscribe()** trong reactive request flow, không cache token vĩnh viễn bỏ qua expiry.
- Test được POST token endpoint, grant, Basic auth, hai GET với Bearer và một lần token acquisition bằng mock HTTP local.
- Có kế hoạch kiểm invalid_client, invalid_scope, 401/403, timeout, retry, rotation/revocation, pool và burst.
- Dùng HTTPS, secret rotation, least privilege, token redaction và inbound authorization riêng ở production.

**Tài liệu tham khảo:** [Spring Security – Reactive OAuth2 Client: Core Interfaces/Classes](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html), [RFC 6749 §4.4 – Client Credentials Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.4), [RFC 6750 – Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).

**Ghi nhớ:** đường an toàn trong service-to-service WebFlux là **ClientRegistration → ReactiveOAuth2AuthorizedClientManager → authorized client còn hạn → WebClient OAuth2 filter → API đối tác**. Chứng minh đúng qua test cấp token và đúng điểm đến, kể cả khi hết hạn, lỗi mạng hoặc tải đồng thời.