# Không coi client giả lập là bằng chứng token endpoint đã được gọi đúng

## 1. Tình huống và mục tiêu học tập

Giả sử một dịch vụ Spring Boot cần gọi API báo cáo của hệ thống khác. Dịch vụ được cấu hình như **OAuth2 Client** với registration `reports-client` và sử dụng grant `client_credentials` để lấy access token từ authorization server trước khi gọi API downstream.

Khi viết test, chúng ta có thể giả lập `OAuth2AuthorizedClient` bằng Spring Security Test rồi thấy controller trả `200 OK`. Test đó **có ích để kiểm chứng cách ứng dụng sử dụng client đã được ủy quyền**, nhưng không chứng minh ứng dụng đã gửi yêu cầu hợp lệ tới **token endpoint**, không chứng minh authorization server đã nhận `grant_type` hay client authentication đúng, và cũng không chứng minh access token được cấp thật.

Trong phạm vi module `SPRING_SECURITY_TESTING`, bài này tập trung vào kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế với `spring-security-test` trên cả Servlet và Reactive. Mục tiêu cụ thể:

1. Phân biệt `ClientRegistration`, `OAuth2AuthorizedClient`, token endpoint và `OAuth2AuthorizedClientManager`.
2. Hiểu giá trị cũng như giới hạn của `oauth2Client()`, `oauth2Login()` và `mockOAuth2Client()`.
3. Dựng một token endpoint thử nghiệm, **ghi nhận HTTP request thật** để xác nhận method, URL, client authentication, `Content-Type`, `grant_type` và `scope`.
4. Viết ca thành công và ca lỗi khi lấy access token, phân biệt với ca chỉ dùng fake client.
5. Biết lúc nào cần kiểm thử bổ sung cho `authorization_code`, PKCE, refresh token, OIDC và WebClient.

Điểm trọng tâm là **bằng chứng phải tương ứng với hành vi cần kiểm tra**. Một đối tượng Java giả được đặt sẵn trong test không tự cho biết mạng đã nhận request nào.

## 2. Các đối tượng trong OAuth2 Client

| Thành phần | Trách nhiệm | Câu hỏi kiểm thử |
| --- | --- | --- |
| `ClientRegistration` | Cấu hình client: `registrationId`, `clientId`, `clientSecret`, grant type, scopes và token URI | Ứng dụng chọn đúng cấu hình chưa? |
| `OAuth2AuthorizedClient` | Đại diện client đã được ủy quyền cho một principal; giữ `OAuth2AccessToken` và có thể `OAuth2RefreshToken` | Ứng dụng đọc/dùng access token đã có đúng chưa? |
| `OAuth2AuthorizedClientManager` | Điều phối cấp mới, tái sử dụng hoặc cấp lại authorized client qua các provider phù hợp | Khi cần token, ứng dụng thực sự kích hoạt quy trình xin token chưa? |
| `OAuth2AccessTokenResponseClient` | Thực hiện token grant cụ thể, gửi request và giải mã response của token endpoint | HTTP request/response đến token endpoint có đúng hợp đồng không? |
| Authorization server / token endpoint | Nhận `POST` token request, xác thực client, xử lý grant và cấp hoặc từ chối token | Request thực có `grant_type`, credentials, scope, code/verifier đúng không? |
| Resource server | Xác minh bearer access token và cho phép/từ chối API | Access token có được gửi tới API đúng cách và có đủ quyền không? |

~~~mermaid
flowchart TD
    A["Ứng dụng cần gọi API"] --> B["OAuth2AuthorizedClientManager"]
    B --> C{"Có authorized client còn hợp lệ?"}
    C -- "Có, tái sử dụng" --> D["OAuth2AuthorizedClient"]
    C -- "Không / cần cấp mới" --> E["Token response client"]
    E --> F["POST token endpoint qua HTTP"]
    F --> G{"Server cấp token?"}
    G -- "Không" --> H["Lỗi OAuth2"]
    G -- "Có" --> D
    D --> I["Gửi Bearer access token tới API downstream"]
    J["spring-security-test oauth2Client()"] -. "Tạo authorized client giả sẵn" .-> D
~~~

Điểm đặc biệt của `oauth2Client()` là nó giúp đặt authorized client giả vào bối cảnh request kiểm thử; nhánh request đến token endpoint **không được chứng minh chỉ bởi helper này**. Dĩ nhiên, code ứng dụng có thể gọi token endpoint vì một lý do khác trong cùng request; khi đó phải có bằng chứng độc lập như HTTP request được ghi nhận hoặc kiểm tra đúng client implementation.

### 2.1. Đừng nhầm authentication của người dùng với client được ủy quyền

- `OAuth2AuthenticationToken` là authentication của một người dùng đã login qua OAuth2/OIDC, có principal, authorities và registration ID.
- `OAuth2AuthorizedClient` chứa thông tin cấp quyền của client, bao gồm access token; một principal có thể sở hữu nhiều authorized clients.
- `JwtAuthenticationToken` thường xuất hiện khi một **resource server** nhận Bearer JWT, không biểu diễn việc một OAuth2 Client đã gọi token endpoint để xin token.
- `OAuth2AuthorizedClientManager.authorize(...)` có thể trả về authorized client hiện có mà **không gọi token endpoint**, nếu token còn hợp lệ theo chính sách cấp phát và lưu trữ.

Vì thế, có `OAuth2AuthorizedClient` hoặc một request trả `200` chưa đủ để khẳng định đã chạy giao thức token grant trong lần kiểm thử ấy.

## 3. Token endpoint phải nhận những gì?

Với OAuth2 `client_credentials` và client authentication kiểu `client_secret_basic`, một request điển hình là:

~~~http
POST /oauth2/token HTTP/1.1
Host: authorization-server.example.test
Authorization: Basic <base64-encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=reports.read
~~~

Khi thành công, authorization server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "access_token": "example-token-from-authorization-server",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "reports.read"
}
~~~

Tùy grant và chính sách server, `scope` trong request có thể được lược bỏ hoặc được chuẩn hóa; response cũng có thể trả ít/nhiều scopes hơn đề nghị. Không giả định refresh token luôn có mặt trong grant `client_credentials`.

Khi xác thực client thất bại, token endpoint có thể trả lỗi OAuth2:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "error": "invalid_client"
}
~~~

Để một test chứng minh HTTP token request đúng, cần quan sát **yêu cầu thực sự tới token URI**. Các khẳng định nên bao gồm đích nhận, HTTP method, hình thức client authentication được cấu hình, request body có `grant_type` đúng, và response được client parse hoặc xử lý lỗi đúng. Nếu còn yêu cầu gọi API downstream, phải quan sát thêm Bearer header gửi tới API đó.

**Lưu ý về credentials:** Khi dùng `client_secret_basic`, `client_id` và `client_secret` được mã hóa theo quy tắc xác thực client trong OAuth2 rồi đặt trong HTTP Basic header. Đừng đưa secret thật vào test fixture, log, snapshot hoặc thông báo assertion thất bại. Các chuỗi minh họa bên dưới là dữ liệu giả.

## 4. Test dùng `oauth2Client()` thực sự chứng minh điều gì?

Spring Security Test có request post-processor `oauth2Client("registration-id")` dành cho Servlet/MockMvc. Nó tạo `OAuth2AuthorizedClient` thử nghiệm để application code có thể truy cập thông qua cơ chế OAuth2 Client. Có thể cấu hình trước access token:

~~~java
import java.time.Instant;
import java.util.Set;

import org.springframework.security.oauth2.core.OAuth2AccessToken;

OAuth2AccessToken sampleToken = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "fake-access-token-for-tests",
        Instant.now().minusSeconds(10),
        Instant.now().plusSeconds(600),
        Set.of("reports.read"));
~~~

Một endpoint chỉ dùng trong môi trường test có thể đọc authorized client đã có:

~~~java
import java.util.Map;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class TestClientInfoController {

    @GetMapping("/test-only/client-info")
    Map<String, String> clientInfo(
            @RegisteredOAuth2AuthorizedClient("reports-client")
            OAuth2AuthorizedClient authorizedClient) {

        return Map.of(
                "registrationId",
                authorizedClient.getClientRegistration().getRegistrationId(),
                "tokenType",
                authorizedClient.getAccessToken().getTokenType().getValue());
    }
}
~~~

Ví dụ kiểm thử MockMvc với security filter chain và OAuth2 Client argument resolver đã được cấu hình trong test context:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oauth2Client;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@Test
void mockAuthorizedClientCanBeReadByController() throws Exception {
    mockMvc.perform(get("/test-only/client-info")
                .with(oauth2Client("reports-client")
                        .accessToken(sampleToken)))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.registrationId")
                   .value("reports-client"))
           .andExpect(jsonPath("$.tokenType").value("Bearer"));
}
~~~

Test trên có thể xác nhận:

- Spring MVC nhận diện một authorized client phù hợp registration `reports-client`.
- Controller đọc đúng registration ID và token type.
- Quy tắc bảo vệ HTTP được áp dụng nếu test setup thực sự bật Spring Security filters.

Nó **chưa kiểm chứng** `grant_type=client_credentials`, HTTP Basic chứa client secret đúng, token URI đúng, authorization server đã cấp token hay response lỗi đã được xử lý. Đó là vì `sampleToken` được test **tạo trước**, không phải kết quả được lấy từ token endpoint.

`oauth2Login()`/`oidcLogin()` cũng tạo authentication giả sau login, không tự chạy OAuth2 authorization-code flow. Đừng coi `oauth2Login()` tạo ra một `OAuth2AuthenticationToken` là bằng chứng callback đã đổi authorization code lấy token thành công.

### 4.1. Tình huống test vẫn xanh khi token endpoint cấu hình sai

Giả sử `ClientRegistration.tokenUri` đang trỏ nhầm đến `https://invalid.example.test/oauth/token`. Một test chỉ đưa `OAuth2AuthorizedClient` và access token giả vào controller vẫn có thể nhận `200 OK`, bởi code xử lý request không cần tự liên hệ token endpoint để nhận token. Sửa sai token URI trong hệ thống lúc này **không nhất thiết làm test đó thất bại**.

Đây là dấu hiệu rõ ràng cho thấy test đang kiểm tra việc **dùng token đã có**, không phải kiểm tra việc **xin token**. Để phát hiện token URI sai, cần test có grant thật và quan sát HTTP request tới token server thử nghiệm.

## 5. Chuẩn bị một token endpoint thử nghiệm có thể quan sát

Ta dùng `MockWebServer` của OkHttp làm HTTP server cục bộ trong test. Server này không phát hành token thật cho sản phẩm, nhưng có thể **nhận và ghi lại request thật từ OAuth2 Client**. Sau đó test kiểm tra method, path, headers, body và hành vi xử lý response.

Dependencies minh họa cho Spring Boot Servlet và `spring-security-test`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}
~~~

Nếu dùng một version library khác, phải chọn version tương thích với Java và các dependencies hiện tại. Các ví dụ `RestClient...TokenResponseClient` bên dưới hướng đến API Spring Security hỗ trợ Spring `RestClient` (dòng Spring Security 6.4+); với version cũ cần dùng token response client phù hợp version đó.

Định nghĩa `ClientRegistration` cho grant `client_credentials`, trỏ đúng token URI do server cục bộ cung cấp:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

static ClientRegistration reportsRegistration(String tokenUri) {
    return ClientRegistration.withRegistrationId("reports-client")
            .clientId("local-demo-client")
            .clientSecret("local-demo-secret")
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
            .tokenUri(tokenUri)
            .scope("reports.read")
            .build();
}
~~~

`registrationId` là tên local của client trong ứng dụng. Nó khác `clientId`, tức danh tính client được đăng ký tại authorization server. `tokenUri` quyết định HTTP endpoint mà token response client phải thực sự gọi.

## 6. Integration test: token endpoint nhận request đúng

Test sau trực tiếp kiểm chứng thành phần thực hiện `client_credentials` grant. Nó không sử dụng `oauth2Client()` hay dựng sẵn `OAuth2AuthorizedClient`.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.endpoint
        .OAuth2ClientCredentialsGrantRequest;
import org.springframework.security.oauth2.client.endpoint
        .RestClientClientCredentialsTokenResponseClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

import static org.junit.jupiter.api.Assertions.*;

class ClientCredentialsTokenEndpointTests {

    // Đặt reportsRegistration(String tokenUri) từ mục 5 ở đây.

    @Test
    void clientCredentialsGrantSendsExpectedHttpRequest() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "application/json")
                    .setBody("""
                        {
                          "access_token": "issued-by-local-server",
                          "token_type": "Bearer",
                          "expires_in": 3600,
                          "scope": "reports.read"
                        }
                        """));
            server.start();

            ClientRegistration registration = reportsRegistration(
                    server.url("/oauth2/token").toString());

            var grant = new OAuth2ClientCredentialsGrantRequest(registration);
            var tokenClient =
                    new RestClientClientCredentialsTokenResponseClient();

            OAuth2AccessTokenResponse response =
                    tokenClient.getTokenResponse(grant);

            assertEquals("issued-by-local-server",
                    response.getAccessToken().getTokenValue());
            assertEquals("Bearer",
                    response.getAccessToken().getTokenType().getValue());

            RecordedRequest request =
                    server.takeRequest(3, TimeUnit.SECONDS);
            assertNotNull(request, "Token endpoint không nhận request");
            assertEquals("POST", request.getMethod());
            assertEquals("/oauth2/token", request.getPath());

            String contentType = request.getHeader("Content-Type");
            assertNotNull(contentType);
            assertTrue(contentType.startsWith(
                    "application/x-www-form-urlencoded"));

            String expectedBasic = "Basic " + Base64.getEncoder()
                    .encodeToString(
                        "local-demo-client:local-demo-secret"
                            .getBytes(StandardCharsets.UTF_8));
            assertEquals(expectedBasic,
                    request.getHeader("Authorization"));

            String body = request.getBody().readUtf8();
            assertTrue(body.contains("grant_type=client_credentials"),
                    "Thiếu hoặc sai grant_type");
            assertTrue(body.contains("scope=reports.read"),
                    "Thiếu scope đã cấu hình");
            assertEquals(1, server.getRequestCount());
        }
    }
}
~~~

Các assertion trực tiếp kiểm chứng:

1. **Có HTTP request thực tới token endpoint**: `RecordedRequest` khác `null` trong thời gian chờ giới hạn.
2. **Đúng method và path**: `POST /oauth2/token`.
3. **Đúng định dạng truyền tham số**: `Content-Type: application/x-www-form-urlencoded` và body có `grant_type=client_credentials`.
4. **Đúng kiểu xác thực client**: header HTTP Basic chứa client ID và secret của fixture kiểm thử.
5. **Đọc được token response**: client giải mã JSON và lấy access token theo hợp đồng.
6. **Không gọi endpoint nhiều lần ngoài dự kiến** trong ca này: bộ đếm request bằng `1`.

Với client ID hoặc secret có ký tự đặc biệt, giá trị HTTP Basic của OAuth2 cần tuân theo quy tắc encoding dành cho client credentials. Ví dụ dùng chuỗi ASCII đơn giản để test có thể kiểm tra trực tiếp Base64 của `client-id:client-secret`; nếu muốn kiểm tra encoding nâng cao, hãy thêm test riêng cho ký tự đặc biệt.

`server.takeRequest(3, TimeUnit.SECONDS)` có timeout để tránh test treo vô hạn khi HTTP request không diễn ra. Giá trị `3 giây` là giới hạn quan sát trong test, không phải bằng chứng về SLA của authorization server sản xuất.

### 6.1. Điều test đã và chưa chứng minh

Đây là **integration test ở ranh giới HTTP giữa client và token endpoint mô phỏng**. Nó chứng minh OAuth2 token response client của ứng dụng có thể tạo và gửi request đúng tới endpoint được cấu hình, rồi parse response chuẩn.

Nó **không chứng minh** Identity Provider sản xuất đã chấp nhận client ID/secret thật, endpoint ngoài internet luôn sẵn sàng, kết nối TLS/certificate hợp lệ trong môi trường triển khai, hay token được server sản xuất ký chính xác. Các vấn đề đó cần thêm contract test hoặc integration test với môi trường Identity Provider do tổ chức kiểm soát.

## 7. Ca lỗi: token endpoint từ chối client

Test thành công cần được ghép với ca lỗi. Nếu token endpoint trả OAuth2 error, ứng dụng phải phát hiện thay vì tự tạo access token từ request bị từ chối.

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;

@Test
void invalidClientResponseFailsTokenAcquisition() throws Exception {
    try (MockWebServer server = new MockWebServer()) {
        server.enqueue(new MockResponse()
                .setResponseCode(401)
                .addHeader("Content-Type", "application/json")
                .setBody("""
                    {
                      "error": "invalid_client",
                      "error_description": "Client authentication failed"
                    }
                    """));
        server.start();

        ClientRegistration registration =
                reportsRegistration(server.url("/oauth2/token").toString());
        var tokenClient =
                new RestClientClientCredentialsTokenResponseClient();

        assertThrows(OAuth2AuthorizationException.class,
                () -> tokenClient.getTokenResponse(
                        new OAuth2ClientCredentialsGrantRequest(
                                registration)));

        RecordedRequest request =
                server.takeRequest(3, TimeUnit.SECONDS);
        assertNotNull(request);
        assertEquals("POST", request.getMethod());
        assertEquals("/oauth2/token", request.getPath());
    }
}
~~~

Authorization server có thể trả `400` hoặc `401` tùy loại lỗi và cơ chế xác thực client. Nên kiểm tra **mã lỗi OAuth2** như `invalid_client`, `invalid_grant` hoặc `invalid_scope` nếu chúng thuộc hợp đồng mong đợi, thay vì mặc định mọi request token thất bại đều là `401`.

Các ca cần xem xét thêm:

| Tình huống | Phản hồi mô phỏng | Kỳ vọng kiểm thử |
| --- | --- | --- |
| Sai client secret | OAuth2 error `invalid_client` | Không có access token, ứng dụng báo lỗi phù hợp |
| Scope không được phép | OAuth2 error `invalid_scope` | Không được coi token đã cấp đúng quyền |
| Token endpoint trả JSON hỏng | Response không parse được | Không được tự coi là token hợp lệ |
| Server trả `5xx` | Lỗi hạ tầng | Ứng dụng xử lý lỗi/giám sát theo chính sách |
| Timeout | Server không trả đúng hạn | Client timeout đúng cấu hình, không treo test |
| Response có token type bất thường | `token_type` sai kỳ vọng | Không sử dụng bừa làm Bearer token |
| Response thành công với scope bị giảm | Token có tập scopes khác đề nghị | Ứng dụng kiểm tra quyền yêu cầu trước khi dùng |

Không nên log nguyên client secret hoặc access token trong exception assertion, ảnh chụp lỗi kiểm thử hay test report.

## 8. Khi cần kiểm chứng `OAuth2AuthorizedClientManager`

Token response client test ở mục 6 tập trung vào **giao thức HTTP của một grant**. Nếu muốn chứng minh ứng dụng thực sự kích hoạt grant khi chưa có authorized client, hãy kiểm thử chính `OAuth2AuthorizedClientManager` hoặc thành phần ứng dụng đang sử dụng nó.

Ví dụ cho công việc nền theo grant `client_credentials`:

~~~java
import org.springframework.security.oauth2.client
        .OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client
        .OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client
        .InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client
        .AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
        .OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client
        .OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
        .OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration
        .ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration
        .InMemoryClientRegistrationRepository;

// registration.tokenUri trỏ tới MockWebServer trong test.
ClientRegistrationRepository registrations =
        new InMemoryClientRegistrationRepository(registration);
OAuth2AuthorizedClientService store =
        new InMemoryOAuth2AuthorizedClientService(registrations);

var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        registrations, store);

OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();
manager.setAuthorizedClientProvider(provider);

OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest.withClientRegistrationId("reports-client")
                .principal("scheduled-report-job")
                .build();

OAuth2AuthorizedClient authorizedClient =
        manager.authorize(authorizeRequest);

assertNotNull(authorizedClient);
assertEquals("reports-client",
        authorizedClient.getClientRegistration().getRegistrationId());
~~~

Nếu fixture bắt đầu với **store rỗng**, cần enqueue token response vào `MockWebServer` trước khi gọi `manager.authorize(...)` rồi kiểm tra `RecordedRequest` như mục 6. Như vậy test mới có bằng chứng manager đã xin token.

Ngược lại, nếu store đã có authorized client chưa hết hạn, manager có thể **tái sử dụng token mà không gọi token endpoint**. Đó là hành vi hợp lệ và nên có test riêng. Không dùng assertion “mỗi API request phải gọi token endpoint một lần”; nó có thể sai với thiết kế caching/refresh chuẩn.

Với client credentials, thường không có refresh token; khi access token hết hiệu lực, authorized client manager có thể cần yêu cầu access token mới. Khi kiểm thử điều này, cần kiểm soát thời gian hết hạn và khoảng lệch an toàn của provider để tránh test lúc chạy đậu lúc chạy rớt.

### 8.1. Chứng minh token đã được gửi tới API downstream

Một token endpoint test chứng minh **đã lấy token**. Nó chưa tự chứng minh code gọi API báo cáo đã thêm đúng header Bearer.

Để kiểm tra đủ đường đi, dùng thêm HTTP server cục bộ (hoặc endpoint khác của cùng `MockWebServer`) đại diện resource server:

1. Enqueue response cấp access token cho `/oauth2/token`.
2. Enqueue response của API `/api/reports`.
3. Cho **thành phần ứng dụng đang được sử dụng thật** gọi API bằng `OAuth2AuthorizedClientManager` hoặc filter/interceptor OAuth2.
4. Đọc request đầu và xác nhận `POST /oauth2/token`, body `grant_type=client_credentials`, header client authentication.
5. Đọc request kế tiếp và xác nhận `GET /api/reports` có `Authorization: Bearer issued-by-local-server`.

Nếu test chỉ lấy access token rồi **tự gắn thủ công** Bearer header bằng code khác với client HTTP của ứng dụng, nó chỉ xác nhận đoạn code test tự viết header; chưa bảo đảm interceptor hoặc filter OAuth2 trong ứng dụng làm đúng. Cần dùng chính thành phần gửi request của ứng dụng để chứng minh end-to-end.

Với ứng dụng Servlet, các thành phần thường gặp gồm `OAuth2AuthorizedClientManager` cùng `ServletOAuth2AuthorizedClientExchangeFilterFunction` cho `WebClient` hoặc interceptor OAuth2 cho `RestClient` (tùy phiên bản Spring Security). Hãy chọn đường đi phù hợp với code thực tế, tránh test bằng client khác rồi suy ra kết luận.

## 9. OAuth2 Authorization Code: các bằng chứng khác cần kiểm tra

Grant `authorization_code` không giống `client_credentials`. Trước token request thường có authorization redirect, state được lưu và callback nhận authorization code. Đối với client công khai hoặc cấu hình yêu cầu PKCE, request token phải kèm `code_verifier` tương ứng.

Ví dụ token request cho authorization-code flow có thể chứa:

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials-if-applicable>

grant_type=authorization_code&code=<authorization-code>&redirect_uri=<callback-uri>&code_verifier=<pkce-verifier-if-applicable>
~~~

Các thông tin cần kiểm tra cho flow này:

| Bước | Bằng chứng cần có |
| --- | --- |
| Bắt đầu login | Redirect đến đúng authorization endpoint, `client_id`, scopes, `redirect_uri` và `state` đúng |
| Callback | Giá trị `state` khớp với authorization request đang lưu và code được tiếp nhận an toàn |
| Token exchange | **Có HTTP POST thật** đến token URI; `grant_type=authorization_code`, `code`, `redirect_uri` và client authentication đúng |
| PKCE | `code_verifier` tương ứng code challenge của bước authorization |
| Response | Token response được parse và lưu thành authorized client phù hợp |
| OIDC | ID token được kiểm tra chữ ký, issuer, audience, hạn, nonce theo cấu hình |
| Truy cập API | Access token được gửi đúng resource server khi cần |

`oauth2Login()` hoặc `oidcLogin()` của Spring Security Test giúp tạo một người dùng **đã đăng nhập giả** để kiểm tra controller/authorization. Chúng không tự chứng minh các bước redirect, callback, exchange code, PKCE, xác minh ID token hoặc token endpoint đã được gọi. Muốn chứng minh flow, hãy chạy integration test cho các filter/authorization client thực tế, dùng IdP thử nghiệm có khả năng ghi nhận request hoặc môi trường xác thực được kiểm soát.

**Lưu ý:** authorization code và PKCE verifier là dữ liệu nhạy cảm trong thời gian ngắn. Không ghi chúng nguyên văn vào report/log ở môi trường thực chỉ để hỗ trợ assertion.

## 10. Reactive `WebTestClient` cũng có giới hạn tương tự

Với WebFlux, Spring Security Test cung cấp mutator như `mockOAuth2Client("reports-client")` để tạo ngữ cảnh OAuth2 Client giả cho test bằng `WebTestClient`. Ví dụ:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Client;

webTestClient
        .mutateWith(mockOAuth2Client("reports-client"))
        .get()
        .uri("/test-only/client-info")
        .exchange()
        .expectStatus().isOk();
~~~

Đoạn này chỉ hợp lệ khi test context WebFlux có route và OAuth2 Client/security support tương ứng. Nếu endpoint yêu cầu user authentication, cũng phải cung cấp authentication test phù hợp với ngữ cảnh đó. Cũng như Servlet `oauth2Client()`, mutator không phải bằng chứng rằng `ReactiveOAuth2AuthorizedClientManager` đã gửi POST đến token endpoint.

Trong Reactive, các thành phần trao đổi token thường dùng `ReactiveOAuth2AuthorizedClientManager` và token response client dựa trên `WebClient`. Để kiểm chứng giao thức:

- Cấu hình `ClientRegistration` hoặc service client của test trỏ tới token endpoint HTTP cục bộ.
- Dùng đúng manager/provider và HTTP client mà ứng dụng đang sử dụng.
- Thực hiện hành động kích hoạt grant khi chưa có authorized client hợp lệ.
- Đọc HTTP request từ server thử nghiệm; kiểm tra method, path, body, authentication, response và trường hợp lỗi.
- Kiểm tra thêm Bearer header trên request downstream nếu mục tiêu bao gồm gọi API.

| Khía cạnh | Servlet | Reactive |
| --- | --- | --- |
| Test helper giả lập | `oauth2Client()` | `mockOAuth2Client()` |
| Manager điển hình | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| Test HTTP security | `MockMvc` | `WebTestClient` |
| Cách chứng minh token endpoint được gọi | Ghi nhận request thật từ token response client/manager | Ghi nhận request thật từ reactive token response client/manager |
| Điều fake client không tự chứng minh | Token POST, client credentials, grant, response | Tương tự |

## 11. Những lỗi thường gặp

| Lỗi kiểm thử | Vì sao kết luận không hợp lệ | Cách sửa |
| --- | --- | --- |
| `with(oauth2Client(...))` rồi kết luận token endpoint đã nhận request | Helper tạo sẵn authorized client | Gửi grant thật và kiểm tra `RecordedRequest` |
| `with(oauth2Login())` rồi kết luận authorization code đã được đổi token | Login post-processor bỏ qua giao thức HTTP ngoài | Test OAuth2 callback và token exchange thực |
| Chỉ assert access token khác rỗng | Token có thể do test tự đặt | Dùng response của HTTP token endpoint thử nghiệm |
| Chỉ mock `OAuth2AccessTokenResponseClient` trả token | Không có HTTP POST để xác minh | Dùng implementation thật với mock HTTP server |
| Token response thành công nhưng không kiểm tra request | Client có thể dùng sai grant hoặc sai path | Assert method, URI, headers và body |
| Chỉ kiểm tra `200` từ token server | Có thể chưa kiểm tra client auth/scope | Assert client authentication và grant params |
| Gắn Bearer header thủ công trong test rồi kết luận interceptor đúng | Test không chạy qua interceptor thật | Dùng HTTP client/service production trong integration test |
| Luôn kỳ vọng POST token mỗi request | Authorized client có thể được cache | Tách ca chưa có token, token còn hạn, token hết hạn |
| Bỏ qua lỗi `invalid_client`, `invalid_scope` | Test chỉ có đường thành công | Mô phỏng OAuth2 error và timeout |
| Dùng token endpoint HTTP cục bộ để kết luận IdP production đã tin cậy credentials | Test không giao tiếp môi trường IdP thật | Bổ sung contract/integration test có kiểm soát |
| Log client secret hoặc access token để so sánh | Có nguy cơ lộ bí mật trong báo cáo | Chỉ dùng fixture giả và tránh log giá trị nhạy cảm |

## 12. Ma trận kiểm thử gợi ý

| Test | Thiết lập | Khẳng định quan trọng |
| --- | --- | --- |
| Đọc authorized client giả | `oauth2Client("reports-client")` | Controller đọc đúng registration/token type |
| Cấp token mới | Store rỗng, manager thật, HTTP token server giả | Có `POST`, `grant_type=client_credentials`, client auth và token response đúng |
| Sai credentials | Token server trả `invalid_client` | Grant thất bại, không dùng token giả |
| Sai scope | Token server trả `invalid_scope` hoặc giảm scopes | Ứng dụng xử lý đúng ràng buộc quyền |
| Tái sử dụng token | Store đã có token còn hạn | Dùng authorized client hiện có theo chính sách, không bắt buộc gọi token endpoint |
| Token hết hạn | Store có token hết hạn, manager/provider phù hợp | Xin lại token/ xử lý expiry theo chính sách |
| API downstream | Token endpoint và API server đều ghi nhận request | Bearer header chứa token được cấp bởi test token server |
| Authorization-code callback | Authorization request + callback và IdP thử nghiệm | `state`, `code`, `redirect_uri`, client auth và PKCE được xử lý đúng |
| OIDC | OIDC Provider thử nghiệm với ID token | Chữ ký, `iss`, `aud`, `nonce` và hạn token đúng |

### Bài tập áp dụng

**Bài tập 1.** Viết test sử dụng `oauth2Client("reports-client")` và token giả `abc`; giải thích vì sao `200 OK` không chứng minh `/oauth2/token` đã nhận POST.

**Bài tập 2.** Dùng `MockWebServer`, đổi `tokenUri` từ `/oauth2/token` sang `/wrong-token`. Kiểm tra test ở mục 6 sẽ thất bại ở assertion path như thế nào. Đây là minh họa trực tiếp điều mà test dùng fake client không phát hiện.

**Bài tập 3.** Giữ nguyên grant `client_credentials` nhưng đổi client authentication method từ `client_secret_basic` sang `client_secret_post`. Điều chỉnh assertion để kiểm tra credentials trong form body theo hợp đồng, thay vì cố đòi `Authorization: Basic`.

**Bài tập 4.** Dùng manager và store để xây dựng hai ca: lần đầu xin token và lần sau tái sử dụng token còn hạn. Assert số request token endpoint theo đúng cơ chế cache, không lấy số request của HTTP API downstream làm số request xin token.

**Bài tập 5.** Giả sử người học dùng `mockOAuth2Client()` trong Reactive WebTestClient và nhìn thấy `200` từ controller. Hãy chỉ ra cần bổ sung thành phần nào để chứng minh `ReactiveOAuth2AuthorizedClientManager` đã thực sự nhận được một access token response qua HTTP.

## 13. Tài liệu tham khảo

- [Spring Security — Testing OAuth 2.0 Client with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oauth2Client()` và các helper OAuth2/OIDC.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): client registration, authorized client và manager.
- [Spring Security — OAuth2AuthorizedClientManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html): hợp đồng cấp authorized client.
- [Spring Security — RestClientClientCredentialsTokenResponseClient API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/endpoint/RestClientClientCredentialsTokenResponseClient.html): token response client cho `client_credentials`.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): cơ chế OAuth2 Client trên WebFlux.
- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 4.4](https://www.rfc-editor.org/rfc/rfc6749#section-4.4): client credentials grant và token request.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): cơ chế PKCE trong authorization-code flow.
