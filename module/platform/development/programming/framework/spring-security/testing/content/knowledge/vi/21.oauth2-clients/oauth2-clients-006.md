# Mock OAuth2AuthorizedClientManager khi cần cô lập việc cấp token

## 1. Bài toán và kết quả cần đạt

Giả sử ứng dụng Spring Boot nhận yêu cầu đọc danh mục hàng hóa, sau đó gọi một API đối tác được bảo vệ bằng OAuth2. Ứng dụng sử dụng grant `client_credentials` để nhận access token, gắn token vào header `Authorization: Bearer ...` và gửi request đi. Trong môi trường production, việc cấp token có thể liên quan đến mạng, client secret, bộ nhớ lưu token, thời hạn hiệu lực và cấu hình của authorization server.

Khi kiểm thử logic của ứng dụng, không phải bài test nào cũng cần gọi authorization server. Ví dụ, muốn chứng minh rằng endpoint của ứng dụng gửi đúng bearer token đến API đối tác và xử lý phản hồi đúng, ta nên **mock `OAuth2AuthorizedClientManager` để cô lập việc cấp token**, sau đó kiểm tra HTTP outbound bằng một server giả hoặc request interceptor có kiểm soát.

Trong module **SPRING_SECURITY_TESTING**, mục tiêu lớn là kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên Servlet và Reactive. Bài này tập trung vào **OAuth2 Client gọi API outbound** và cách kết hợp Mockito, MockMvc hoặc WebTestClient để tránh nhầm nó với xác thực request inbound.

Sau khi học, bạn có thể:

1. Mô tả vai trò của `OAuth2AuthorizedClientManager`, `OAuth2AuthorizeRequest` và `OAuth2AuthorizedClient`.
2. Chọn đúng trường hợp cần mock manager và trường hợp cần kiểm thử cấp/refresh token thực sự.
3. Tạo fixture OAuth2 client với access token giả, ổn định, không cần IdP.
4. Dùng Mockito kiểm tra registration ID, principal, trạng thái thành công, `null` và exception.
5. Kiểm chứng bearer token xuất hiện trong request HTTP outbound bằng `MockRestServiceServer`; tách kiểm thử inbound HTTP khỏi outbound OAuth2.
6. Áp dụng nguyên tắc tương tự cho `ReactiveOAuth2AuthorizedClientManager` và `WebClient`.

## 2. OAuth2 Client Manager thực hiện công việc gì?

`OAuth2AuthorizedClientManager` là điểm điều phối authorization cho một ứng dụng **OAuth2 Client** chạy trên Servlet. Nó phối hợp `ClientRegistration`, principal, `OAuth2AuthorizedClientProvider` và kho lưu trữ để lấy lại authorized client đã có hoặc thực hiện authorization khi cần. Tùy grant và cấu hình, quá trình có thể sử dụng access token hiện có, cấp token mới hoặc refresh token.

Đầu vào và đầu ra cốt lõi:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("catalog")
        .principal("catalog-job")
        .build();

OAuth2AuthorizedClient authorizedClient = manager.authorize(request);
```

| Đối tượng | Vai trò | Dữ liệu quan trọng |
| --- | --- | --- |
| `ClientRegistration` | Cấu hình OAuth2 client | `registrationId`, `clientId`, grant type, token URI, scopes |
| `OAuth2AuthorizeRequest` | Yêu cầu cấp/tìm authorized client | Registration ID hoặc authorized client, principal, attributes |
| `OAuth2AuthorizedClientManager` | Thực hiện/điều phối authorization | `authorize(request)` |
| `OAuth2AuthorizedClient` | Kết quả authorization cho một client và principal | Client registration, principal name, access token, có thể có refresh token |
| `OAuth2AccessToken` | Credential dùng gọi resource server | Token type, value, thời gian cấp/hết hạn, scopes |
| `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` | Lưu/đọc authorized clients theo bối cảnh triển khai | Client registration ID và principal |

Hai trường hợp kết quả cần nhớ:

- `authorize(request)` **trả về một `OAuth2AuthorizedClient`** khi đã có thông tin authorization phù hợp.
- `authorize(request)` **có thể trả về `null`** khi không thể authorization theo provider/configuration, hoặc ném `OAuth2AuthorizationException` khi có lỗi OAuth2. Ứng dụng phải xử lý cả hai đường đi; đừng dereference `getAccessToken()` khi chưa kiểm tra kết quả.

### 2.1. Luồng phụ thuộc khi chạy thật và khi mock

```mermaid
flowchart TD
    A["Ứng dụng: cần gọi API đối tác"] --> B["OAuth2AuthorizeRequest"]
    B --> C["OAuth2AuthorizedClientManager"]
    C --> D{"Lấy token bằng cách nào?"}
    D --> E["Đọc token lưu trữ"]
    D --> F["Token endpoint / Refresh token"]
    E --> G["OAuth2AuthorizedClient"]
    F --> G
    G --> H["HTTP outbound: Bearer access token"]
    H --> I["Resource server đối tác"]
    M["Mockito stub"] -. "Trong unit test thay C–G" .-> G
```

Mock manager tạo ranh giới kiểm thử ở chỗ ứng dụng *nhận token*. Khi trả về một `OAuth2AuthorizedClient` đã dựng sẵn, test không gọi token endpoint, không kiểm tra client secret và không chạy thuật toán refresh token của manager thật. Nhờ đó lỗi HTTP downstream có thể được chẩn đoán độc lập với lỗi Identity Provider.

## 3. Khi nào nên mock, khi nào phải dùng manager thật?

| Mục tiêu kiểm thử | Mock manager? | Cách kiểm chứng |
| --- | --- | --- |
| Service chọn đúng `clientRegistrationId` | Có | `ArgumentCaptor<OAuth2AuthorizeRequest>` |
| Service chọn đúng principal và tenant | Có | Kiểm tra `getPrincipal().getName()` và attributes |
| Service gắn đúng bearer token vào HTTP outbound | Có | Mock manager + `MockRestServiceServer` hoặc mock `ExchangeFunction` |
| Service xử lý thiếu authorized client | Có | `authorize(...)` trả `null` |
| Service xử lý OAuth2 provider lỗi | Có | `authorize(...)` ném exception |
| Authorization server có trả token hợp lệ | Không | HTTP integration với authorization server giả/kiểm soát được |
| Token được cache hoặc refresh đúng thời điểm | Không | Manager/provider thật, token store và thời gian có kiểm soát |
| Sai client secret hoặc token URI | Không | Kiểm thử cấu hình cùng token endpoint giả |
| Scope trong response được ghi nhận đúng | Không chỉ dựa vào mock | Kiểm thử OAuth2 client provider xử lý token response thật |
| Endpoint inbound yêu cầu user/JWT hợp lệ | Tùy mục tiêu | `MockMvc`, `@WithMockUser`, `jwt()` hoặc WebTestClient |

**Nguyên tắc lựa chọn:** mock những phụ thuộc không thuộc hành vi đang kiểm tra. Nếu hành vi cần chứng minh chính là cơ chế **cấp token**, hãy chạy manager/provider thật với một token endpoint được kiểm soát. Nếu hành vi cần chứng minh là **ứng dụng sử dụng token**, mock manager là lựa chọn gọn và có tính quyết định.

## 4. Ví dụ service dùng OAuth2AuthorizedClientManager

Để các ví dụ có thể áp dụng thực tế, ta xây một client đơn giản gọi API danh mục bên ngoài. Phần code sử dụng `RestClient` của Spring Framework 6.1+ (Spring Boot 3.2+); ở dự án dùng phiên bản cũ hơn, có thể dùng `RestTemplate` hoặc `WebClient` với cùng ý tưởng.

```java
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.web.client.RestClient;

public final class CatalogGateway {
    private final OAuth2AuthorizedClientManager authorizedClients;
    private final RestClient http;

    public CatalogGateway(
            OAuth2AuthorizedClientManager authorizedClients,
            RestClient http) {
        this.authorizedClients = authorizedClients;
        this.http = http;
    }

    public String loadItems() {
        OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest.withClientRegistrationId("catalog")
                .principal("catalog-job")
                .build();

        OAuth2AuthorizedClient authorized =
            authorizedClients.authorize(authorizeRequest);

        if (authorized == null) {
            throw new IllegalStateException(
                "OAuth2 client 'catalog' was not authorized");
        }

        String accessToken = authorized.getAccessToken().getTokenValue();

        return http.get()
            .uri("/items")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
```

Trong ví dụ này, `principal("catalog-job")` là **tên principal kỹ thuật ổn định** dành cho luồng service-to-service sử dụng `client_credentials`. Nó góp phần xác định khóa lưu authorized client. Một ứng dụng thực hiện **delegated authorization** thay mặt người dùng phải truyền principal của người dùng phù hợp, không tái sử dụng máy móc `"catalog-job"` cho mọi request.

Ta cố ý inject `OAuth2AuthorizedClientManager` và `RestClient` qua constructor. Nhờ vậy, bài test có thể thay manager bằng Mockito, còn HTTP request được một mock server ghi nhận. Đây là cách kiểm tra kết quả thực tế ở biên HTTP mà vẫn không cần kết nối IdP hoặc API đối tác.

### 4.1. Cấu hình manager thực sự cho tác vụ nền

Khi chạy ngoài request Servlet, chẳng hạn scheduled job, bean thường dùng là `AuthorizedClientServiceOAuth2AuthorizedClientManager` cùng `OAuth2AuthorizedClientService`:

```java
@Bean
OAuth2AuthorizedClientManager catalogAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClientService) {

    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        registrations, authorizedClientService);

    manager.setAuthorizedClientProvider(
        OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build());

    return manager;
}
```

Đối với request Servlet có bối cảnh HTTP, `DefaultOAuth2AuthorizedClientManager` thường dùng `OAuth2AuthorizedClientRepository`. Đối với job phía server không có `HttpServletRequest`, service manager ở trên giúp tránh phụ thuộc vào request hiện hành. Mẫu này chỉ thiết lập grant `client_credentials`; muốn hỗ trợ grant khác phải cấu hình provider tương ứng với quy trình OAuth2 mà ứng dụng thực sự sử dụng.

## 5. Dựng OAuth2AuthorizedClient giả đúng kiểu

`OAuth2AuthorizedClientManager.authorize(...)` trả về **`OAuth2AuthorizedClient`**, vì vậy không thể thay bằng một chuỗi token thô hay `OAuth2AccessTokenResponse`. Fixture nên chứa `ClientRegistration`, tên principal và `OAuth2AccessToken` có thời hạn hợp lệ cho test.

```java
import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

public final class OAuth2Fixtures {
    private OAuth2Fixtures() {}

    public static OAuth2AuthorizedClient catalogClient() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("catalog")
                .clientId("catalog-client-test")
                .clientSecret("unused-secret-test")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://idp.example.test/oauth/token")
                .scope("catalog.read")
                .build();

        Instant issuedAt = Instant.parse("2030-01-01T00:00:00Z");
        Instant expiresAt = Instant.parse("2030-01-01T01:00:00Z");

        OAuth2AccessToken accessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "test-access-token-for-catalog",
            issuedAt,
            expiresAt,
            Set.of("catalog.read"));

        return new OAuth2AuthorizedClient(
            registration,
            "catalog-job",
            accessToken);
    }
}
```

Thời điểm trong fixture minh họa chỉ có tác dụng dựng đối tượng. Với một test phụ thuộc `expiresAt` theo thời gian thực, hãy dùng `Clock` kiểm soát được hoặc tạo `Instant.now().plusSeconds(...)`; không giả định một ngày cố định trong fixture luôn còn hạn tại thời điểm chạy test.

Tại đây không có yêu cầu token phải có chữ ký JWT. Với `client_credentials`, access token được trả về từ token endpoint có thể là **opaque token** hoặc JWT tùy IdP. OAuth2 Client chỉ cần truyền token phù hợp tới resource server; một unit test sử dụng bearer string giả là đủ để kiểm tra việc gắn header.

**Đừng đưa token thật, client secret thật hoặc thông tin người dùng thật vào fixture và log.** Giá trị `test-access-token-for-catalog` là dữ liệu giả hoàn toàn.

## 6. Unit test thành công: Mock manager, kiểm tra HTTP outbound

Test sau dùng:

- **Mockito** để stub `authorize(...)` và bắt `OAuth2AuthorizeRequest`.
- **`MockRestServiceServer`** để quan sát request từ `RestClient` mà không gửi dữ liệu ra mạng.
- **AssertJ** để kiểm tra kết quả business và các tham số authorization.

Ví dụ có thể đặt trong cùng test package với `CatalogGateway` và `OAuth2Fixtures` ở trên:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.mockito.ArgumentCaptor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.client.match
    .MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match
    .MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match
    .MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response
    .MockRestResponseCreators.withSuccess;

class CatalogGatewayTest {

    @Test
    void usesAuthorizedTokenInActualOutboundRequest() {
        OAuth2AuthorizedClientManager manager =
            mock(OAuth2AuthorizedClientManager.class);

        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://catalog.example.test");
        MockRestServiceServer remote =
            MockRestServiceServer.bindTo(builder).build();
        CatalogGateway gateway = new CatalogGateway(
            manager, builder.build());

        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
            .thenReturn(OAuth2Fixtures.catalogClient());

        remote.expect(requestTo("https://catalog.example.test/items"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(
                HttpHeaders.AUTHORIZATION,
                "Bearer test-access-token-for-catalog"))
            .andRespond(withSuccess(
                "[{\"id\":1}]",
                MediaType.APPLICATION_JSON));

        String result = gateway.loadItems();

        assertThat(result).isEqualTo("[{\"id\":1}]");
        remote.verify();

        ArgumentCaptor<OAuth2AuthorizeRequest> captured =
            ArgumentCaptor.forClass(OAuth2AuthorizeRequest.class);
        verify(manager).authorize(captured.capture());

        OAuth2AuthorizeRequest actual = captured.getValue();
        assertThat(actual.getClientRegistrationId())
            .isEqualTo("catalog");
        assertThat(actual.getPrincipal().getName())
            .isEqualTo("catalog-job");
    }
}
```

Test này kiểm chứng được **ba hợp đồng**:

1. `CatalogGateway` gọi đúng manager để lấy authorized client cho registration `catalog`.
2. Service truyền đúng principal `catalog-job`, tránh lấy token theo một danh tính không mong muốn.
3. HTTP outbound đến `/items` có header `Authorization: Bearer test-access-token-for-catalog` và xử lý response như mong đợi.

`MockRestServiceServer` kiểm tra request ở tầng HTTP client, **không cần token endpoint hoạt động**. Đây là bằng chứng mạnh hơn việc chỉ gọi `verify(manager).authorize(...)`, vì request cuối cùng có thể vô tình bỏ quên header hoặc gắn sai token dù manager đã trả về đúng dữ liệu.

Nếu ứng dụng dùng `WebClient` thay `RestClient`, có thể dùng một `ExchangeFunction` giả để quan sát `ClientRequest`. Nếu sử dụng `ServletOAuth2AuthorizedClientExchangeFilterFunction`, có thể inject manager giả trực tiếp vào filter function; vẫn cần test request HTTP outbound và các thuộc tính của `OAuth2AuthorizeRequest` trong bối cảnh servlet thích hợp.

## 7. Kiểm thử thất bại: manager trả null hoặc ném lỗi

Không được viết:

```java
String token = manager.authorize(request)
    .getAccessToken().getTokenValue(); // Có thể NullPointerException.
```

Ngược lại, service ở mục 4 từ chối tiếp tục nếu `authorize(...)` không trả về authorized client. Dưới đây là hai ca không cần tạo network expectation:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.OAuth2AuthorizationException;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CatalogGatewayFailureTest {

    @Test
    void noAuthorizedClientMustFailClosed() {
        var manager = mock(OAuth2AuthorizedClientManager.class);
        var gateway = new CatalogGateway(
            manager,
            RestClient.create("https://catalog.example.test"));

        when(manager.authorize(any())).thenReturn(null);

        assertThatThrownBy(gateway::loadItems)
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("not authorized");
        verify(manager).authorize(any());
    }

    @Test
    void tokenEndpointErrorIsNotConvertedToFakeSuccess() {
        var manager = mock(OAuth2AuthorizedClientManager.class);
        var gateway = new CatalogGateway(
            manager,
            RestClient.create("https://catalog.example.test"));

        when(manager.authorize(any()))
            .thenThrow(new OAuth2AuthorizationException(
                new OAuth2Error("invalid_client")));

        assertThatThrownBy(gateway::loadItems)
            .isInstanceOf(OAuth2AuthorizationException.class);
    }
}
```

Vì `CatalogGateway` lấy token **trước** khi gọi HTTP, hai test này không tạo request mạng. Khi hệ thống có mapping exception thành HTTP status tại controller, hãy viết thêm test MockMvc để kiểm tra response theo policy: ví dụ trả 502/503 cho lỗi phụ thuộc authorization server, hoặc một mã lỗi nội bộ đã chuẩn hóa. Không đẩy raw `client_secret`, `access_token` hay thông tin token endpoint vào response công khai.

Chú ý: `null` không đồng nghĩa duy nhất với “token hết hạn”. Với manager thật, giá trị đó có thể xuất hiện khi provider không thể thực hiện authorization theo grant/configuration. Test nên mô tả **hành vi ứng dụng trước kết quả null**, không tự suy ra nguyên nhân cụ thể mà test không thiết lập.

## 8. Captor chính xác hơn: registration ID, principal và attributes

`OAuth2AuthorizeRequest` không chỉ chứa registration ID. Một số flow truyền attributes bổ sung để phục vụ các authorized client providers hoặc custom context:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("catalog")
        .principal("catalog-job")
        .attribute("tenant", "tenant-a")
        .build();
```

Trong test, có thể dùng `ArgumentCaptor` như mục 6 để assert:

```java
OAuth2AuthorizeRequest actual = captured.getValue();

assertThat(actual.getClientRegistrationId()).isEqualTo("catalog");
assertThat(actual.getPrincipal().getName()).isEqualTo("catalog-job");
assertThat(actual.getAttributes()).containsEntry("tenant", "tenant-a");
```

Đây chỉ là ví dụ khi ứng dụng đã **thực sự xây request có tenant**. Trường `tenant` không phải thuộc tính chuẩn mà mọi manager tự hiểu; để ảnh hưởng việc chọn client/credentials, custom provider hoặc logic ứng dụng phải xử lý attribute đó. Một test chỉ thêm `.attribute("tenant", ...)` không chứng minh quyền truy cập đã được giới hạn theo tenant.

Với hệ thống đa client, nên có các ca:

| Ngữ cảnh | Registration/principal mong đợi | Điều cần bảo vệ |
| --- | --- | --- |
| Gọi catalog API | `catalog` + `catalog-job` | Không lấy token của client khác |
| Gọi billing API | `billing` + `billing-job` | Mỗi client dùng scopes và credentials riêng |
| Gọi thay mặt Alice | Registration hợp lệ + principal của Alice | Không tái sử dụng authorized client của Bob |
| Gọi thay mặt tenant A | Registration/principal/attributes theo hợp đồng của A | Không đọc nhầm token hoặc quyền của tenant B |

Một lỗi khó phát hiện là dùng `principal("anonymous")` hoặc cùng một tên principal cho các request thật sự cần token riêng theo người dùng. Khi sử dụng `OAuth2AuthorizedClientService` hoặc repository, principal name là một phần thông tin gắn với authorized client; test cần phản ánh chính xác danh tính mà hệ thống chọn.

## 9. Kết hợp với MockMvc khi có endpoint HTTP inbound

Giả sử ứng dụng cung cấp `GET /api/catalog` và controller gọi `CatalogGateway.loadItems()`. HTTP test có thể kiểm tra đồng thời rằng endpoint **inbound** chỉ cho người đã đăng nhập truy cập và gateway **outbound** nhận token từ mock manager.

Hai ranh giới xác thực cần phân biệt:

```mermaid
flowchart LR
    U["Browser/API caller"] --> A["Spring Security inbound"]
    A --> B["GET /api/catalog"]
    B --> C["CatalogGateway"]
    C --> D["OAuth2AuthorizedClientManager"]
    D --> E["Access token cho API đối tác"]
    E --> F["GET API đối tác"]
```

- `@WithMockUser`, `with(user(...))`, `with(jwt())` hoặc `oauth2Login()` cung cấp **SecurityContext của request đến ứng dụng**, phù hợp khi muốn kiểm tra authentication/authorization inbound.
- Mockito mock của `OAuth2AuthorizedClientManager` cung cấp **authorized client dùng cho request đi từ ứng dụng đến API đối tác**.
- Hai loại thông tin này độc lập. Không dùng `@WithMockUser` để kỳ vọng tự có access token outbound. Cũng không dùng manager mock để chứng minh SecurityFilterChain đã chặn request anonymous.

Với Spring Boot 3.4+ / Spring Framework 6.2+, có thể dùng `@MockitoBean` khi test chạy trong ApplicationContext:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CatalogControllerHttpTest {
    @Autowired MockMvc mvc;

    // Thay bean manager trong ApplicationContext bằng Mockito mock.
    @MockitoBean OAuth2AuthorizedClientManager authorizedClientManager;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void authorizedCallerCanEnterController() throws Exception {
        when(authorizedClientManager.authorize(any()))
            .thenReturn(OAuth2Fixtures.catalogClient());

        // Ứng dụng cần có GET /api/catalog -> CatalogGateway.loadItems().
        // Đồng thời phải stub HTTP đối tác bằng test HTTP transport phù hợp.
        // mvc.perform(get("/api/catalog"))
        //     .andExpect(status().isOk());
    }
}
```

Đoạn trên là **khung minh họa cách thay bean**, không phải một test hoàn chỉnh: nếu chạy request, bạn còn cần controller, security policy và stub HTTP outbound. Việc mock manager chỉ cô lập token issuance; nó không tự ngăn `RestClient` gửi request sang API thật. Với Spring Boot cũ hơn, `@MockBean` từng được dùng cho mục đích tương tự; hãy chọn annotation theo phiên bản Spring Boot/Spring Framework trong dự án.

Để kiểm tra đầy đủ, thực hiện các assertion sau trong bài test tích hợp:

1. Caller anonymous bị chặn bởi security policy đã cấu hình (có thể 401 hoặc redirect tùy entry point).
2. Caller đủ authority vào controller, manager được gọi đúng registration/principal.
3. Server HTTP giả nhận bearer token và trả nội dung fixture.
4. Request không đủ quyền bị 403 nếu đã đăng nhập nhưng thiếu authority; manager và HTTP outbound không bị gọi.
5. Khi manager trả null/throw, endpoint trả phản hồi lỗi có kiểm soát và không gửi request ra đối tác.

Kiểm thử này không yêu cầu liên hệ authorization server, nhưng vẫn chứng minh đường đi từ HTTP inbound qua business service tới HTTP outbound.

## 10. Mẫu tương tự cho WebClient trên Reactive/WebFlux

Ứng dụng Reactive dùng **`ReactiveOAuth2AuthorizedClientManager`** thay cho interface Servlet. Phương thức `authorize(...)` trả `Mono<OAuth2AuthorizedClient>`:

```java
import reactor.core.publisher.Mono;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.web.reactive.function.client.WebClient;

public final class ReactiveCatalogGateway {
    private final ReactiveOAuth2AuthorizedClientManager authorizedClients;
    private final WebClient webClient;

    public ReactiveCatalogGateway(
            ReactiveOAuth2AuthorizedClientManager authorizedClients,
            WebClient webClient) {
        this.authorizedClients = authorizedClients;
        this.webClient = webClient;
    }

    public Mono<String> loadItems() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest.withClientRegistrationId("catalog")
                .principal("catalog-job")
                .build();

        return authorizedClients.authorize(request)
            .switchIfEmpty(Mono.error(
                new IllegalStateException(
                    "OAuth2 client 'catalog' was not authorized")))
            .flatMap(client -> webClient.get()
                .uri("/items")
                .headers(headers -> headers.setBearerAuth(
                    client.getAccessToken().getTokenValue()))
                .retrieve()
                .bodyToMono(String.class));
    }
}
```

Trong Reactive, “không có authorized client” thường được biểu diễn bằng **`Mono.empty()`**, không phải `null`. Vì thế, nhánh xử lý phải dùng `switchIfEmpty(...)` thay vì kiểm tra `if (authorized == null)` sau khi gọi manager.

Một unit test có thể kiểm tra cả manager và HTTP request mà không mở socket:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ReactiveCatalogGatewayTest {

    @Test
    void managerStubProvidesBearerTokenToWebClient() {
        var manager =
            mock(ReactiveOAuth2AuthorizedClientManager.class);
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
            .thenReturn(Mono.just(OAuth2Fixtures.catalogClient()));

        ExchangeFunction remote = request -> {
            assertThat(request.url().toString())
                .isEqualTo("https://catalog.example.test/items");
            assertThat(request.headers()
                .getFirst(HttpHeaders.AUTHORIZATION))
                .isEqualTo("Bearer test-access-token-for-catalog");

            return Mono.just(ClientResponse.create(HttpStatus.OK)
                .header(HttpHeaders.CONTENT_TYPE,
                    MediaType.APPLICATION_JSON_VALUE)
                .body("[{\"id\":1}]")
                .build());
        };

        WebClient client = WebClient.builder()
            .baseUrl("https://catalog.example.test")
            .exchangeFunction(remote)
            .build();

        var gateway = new ReactiveCatalogGateway(manager, client);

        StepVerifier.create(gateway.loadItems())
            .expectNext("[{\"id\":1}]")
            .verifyComplete();

        verify(manager).authorize(any(OAuth2AuthorizeRequest.class));
    }

    @Test
    void emptyAuthorizedClientFailsBeforeHttpCall() {
        var manager =
            mock(ReactiveOAuth2AuthorizedClientManager.class);
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
            .thenReturn(Mono.empty());

        ExchangeFunction forbiddenRemote =
            request -> Mono.error(new AssertionError(
                "HTTP must not be called without an access token"));

        var gateway = new ReactiveCatalogGateway(
            manager,
            WebClient.builder()
                .exchangeFunction(forbiddenRemote)
                .build());

        StepVerifier.create(gateway.loadItems())
            .expectError(IllegalStateException.class)
            .verify();
    }
}
```

`StepVerifier` thuộc `reactor-test`. Nếu dự án chưa có, khai báo `testImplementation 'io.projectreactor:reactor-test'` với version được quản lý bởi BOM của Spring Boot. Fixture `OAuth2Fixtures.catalogClient()` ở mục 5 có thể dùng lại vì `OAuth2AuthorizedClient` là cùng kiểu dữ liệu trong hai API.

Nếu kiểm thử request **inbound** trong WebFlux, dùng `WebTestClient` và các mutator như `mockOAuth2Login()` hoặc `mockJwt()` của `spring-security-test`. Chúng tạo trạng thái bảo mật của caller; việc cấp token **outbound** vẫn thuộc `ReactiveOAuth2AuthorizedClientManager`.

Trong background job Reactive, cân nhắc `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`; khi làm việc trong server exchange, `DefaultReactiveOAuth2AuthorizedClientManager` dùng repository và exchange phù hợp.

## 11. Nếu đã dùng OAuth2 WebClient filter function

Nhiều ứng dụng không gọi manager trực tiếp trong service mà cấu hình filter của `WebClient` để tự lấy token và gắn header:

```java
ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        authorizedClientManager);

WebClient webClient = WebClient.builder()
    .apply(oauth2.oauth2Configuration())
    .build();
```

Với Servlet, filter tương ứng thường là `ServletOAuth2AuthorizedClientExchangeFilterFunction`. Với Reactive, lớp tương ứng là `ServerOAuth2AuthorizedClientExchangeFilterFunction` và dùng `ReactiveOAuth2AuthorizedClientManager`.

Một request sử dụng registration ID cụ thể có thể cung cấp thuộc tính bằng helper của filter:

```java
webClient.get()
    .uri("https://catalog.example.test/items")
    .attributes(
        ServletOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("catalog"))
    .retrieve()
    .bodyToMono(String.class);
```

Khi đó, test manager mock vẫn hữu ích, nhưng `authorize(...)` được gọi **bên trong filter**. Hãy kiểm tra request sau filter có bearer token, registration ID mà filter nhận, bối cảnh principal thích hợp và hành vi khi authorization không thành công. Nếu thiếu Servlet request context, cần cung cấp principal hoặc request attributes theo yêu cầu cụ thể của filter; đừng giả định filter luôn có thể lấy SecurityContext trong một scheduled job.

Không nên lạm dụng `setDefaultOAuth2AuthorizedClient(true)` hoặc một client mặc định cho **mọi** request HTTP. Việc tự động gắn token không đúng đích có thể làm lộ token đến host hoặc API không được dự định. Cấp registration ID tường minh cho những outbound requests có yêu cầu OAuth2 rõ ràng.

## 12. Các giới hạn phải ghi rõ trong báo cáo kiểm thử

**Một test có mock manager chứng minh ứng dụng xử lý kết quả authorization như thế nào.** Nó không chứng minh authorization server đã cấp token theo OAuth2 đúng chuẩn.

| Điều có thể khẳng định sau test mock | Điều chưa thể khẳng định |
| --- | --- |
| Service gọi đúng manager với ID/principal | Client secret, token URI đúng với IdP thật |
| Manager stub trả authorized client có token cụ thể | Grant `client_credentials` được IdP chấp nhận |
| Request outbound mang đúng bearer header | Token thực sự hợp lệ với resource server |
| Service xử lý `null` / lỗi OAuth2 | Cơ chế retry, refresh và cache của manager thật |
| Endpoint inbound áp dụng policy đúng khi kết hợp MockMvc | Toàn bộ authorization code/OIDC login flow hoạt động |
| Reactive pipeline xử lý `Mono.empty()` | Token store và scheduler trong môi trường production đúng |

### 12.1. Cần test gì khi kiểm chứng cấp hoặc làm mới token?

Khi chủ đề cần kiểm tra **thực sự cấp token**, dựng một integration test có:

1. `ClientRegistration` trỏ đến token endpoint giả bằng một HTTP stub server.
2. `OAuth2AuthorizedClientProvider` thực tế, ví dụ `clientCredentials()` hoặc `refreshToken()` theo flow.
3. Manager thật và authorized client service/repository test cách ly.
4. Response giả cho success, `invalid_client`, `invalid_grant`, timeout hoặc 5xx nếu hệ thống có cơ chế xử lý tương ứng.
5. Clock/TTL có kiểm soát khi cần chứng minh token hết hạn hoặc refresh.
6. Assertion cho số lần gọi token endpoint, thông tin token được lưu và hành vi các request tiếp theo.

Mock manager không thực thi `OAuth2AuthorizedClientProvider` nên không có cơ sở để kết luận token thực sự được refresh đúng lúc. Nếu ứng dụng có refresh token, có thể test lần lượt “token còn hạn”, “token sắp hết hạn” và “refresh token bị từ chối” ở tầng integration với provider thật và server mô phỏng.

### 12.2. Không dùng những giả lập sai mục đích

- `@WithMockUser`: thiết lập principal/authorities cho **HTTP inbound**, không tự cấp OAuth2AuthorizedClient cho outbound request.
- `jwt()` / `mockJwt()`: mô phỏng bearer JWT mà **resource server inbound** đã xác thực, không mô phỏng client xin access token.
- `oauth2Login()` / `mockOAuth2Login()`: mô phỏng người dùng đã đăng nhập OAuth2; hữu ích cho authorization inbound, nhưng không chứng minh token endpoint được gọi.
- `OAuth2AccessTokenResponse`: là dữ liệu phản hồi từ token endpoint; manager mock ở đây phải trả **`OAuth2AuthorizedClient`**.
- `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService`: lưu authorized client; nếu hành vi cần kiểm tra phụ thuộc vào token cache, mock trực tiếp manager có thể che khuất lỗi đó.

## 13. Những lỗi thường gặp và cách khắc phục

**Lỗi 1 — Mock manager trả một chuỗi token.** Phương thức trả `OAuth2AuthorizedClient`; hãy dựng đầy đủ `ClientRegistration` và `OAuth2AccessToken` như fixture ở mục 5.

**Lỗi 2 — `when(manager.authorize(request)).thenReturn(client)` không khớp request.** Production có thể tạo `OAuth2AuthorizeRequest` mới mỗi lần, nên Mockito không stub theo instance gốc. Dùng `any(OAuth2AuthorizeRequest.class)` và `ArgumentCaptor` để assert nội dung sau đó, hoặc `argThat` với tiêu chí hẹp.

**Lỗi 3 — Không test nhánh `null`.** Code có thể ném `NullPointerException` hoặc vô tình gửi request không được bảo vệ. Yêu cầu fail closed trước khi gọi downstream.

**Lỗi 4 — Manager bị mock nhưng HTTP client vẫn gọi API thật.** Mockito thay phần cấp token, không thay network transport. Hãy bổ sung `MockRestServiceServer`, mock `ExchangeFunction` hoặc HTTP stub server.

**Lỗi 5 — Kiểm tra mỗi lời gọi manager, không kiểm tra bearer header.** Application có thể lấy đúng token rồi gắn nhầm header, dùng token của client khác hoặc quên token. Assert request outbound thực sự được gửi.

**Lỗi 6 — Dùng token người dùng để gọi luồng `client_credentials`.** Client credentials đại diện cho ứng dụng, không phải mặc nhiên mang quyền của user. Nếu cần quyền delegated, phải dùng grant và principal đúng của người dùng.

**Lỗi 7 — Dùng cùng principal cho tất cả tenant.** Có thể làm chia sẻ authorized client/token không phù hợp. Chọn tên principal và strategy lưu token theo ranh giới security của sản phẩm.

**Lỗi 8 — Test timeout bằng `Thread.sleep` dài.** Dẫn tới test chậm và dễ flake. Nếu chỉ kiểm tra ứng dụng xử lý lỗi, stub manager throw exception; nếu cần kiểm tra mạng timeout thật, dùng HTTP stub server và timeout có kiểm soát.

**Lỗi 9 — Trong Reactive, kiểm tra `null` khi manager trả `Mono.empty()`.** Dùng `switchIfEmpty` hoặc operator phù hợp; verify không có HTTP downstream.

**Lỗi 10 — In bearer token vào assertion failure/log CI.** Fixture nên chỉ chứa token giả; token/secret production không được ghi ra log, telemetry hoặc test snapshot.

**Lỗi 11 — Kết luận mock chứng minh token refresh thành công.** Mock bỏ qua provider và token repository; bổ sung integration test riêng nếu refresh là yêu cầu.

## 14. Ma trận test tối thiểu và bài thực hành

### 14.1. Ma trận theo hành vi

| Ca | Stub manager | Input/HTTP | Kết quả cần kiểm tra |
| --- | --- | --- | --- |
| Thành công | Trả `OAuth2AuthorizedClient` có access token | GET API đối tác | Header `Bearer`, status/body đúng |
| Chọn client | Trả client fixture | `catalog` + principal kỹ thuật | Captor khớp registration/principal |
| Không cấp được token | Trả `null` | Chưa gọi HTTP đối tác | Service fail closed, không dùng null token |
| IdP lỗi | Ném `OAuth2AuthorizationException` | Chưa gọi HTTP đối tác | Xử lý exception theo policy |
| API đối tác trả 401/403 | Trả client fixture | HTTP stub trả 401/403 | Không coi token mock là bảo đảm quyền truy cập API |
| User inbound anonymous | Manager có stub nhưng SecurityFilterChain chặn | GET controller được bảo vệ | Không chạy service/manager |
| User inbound thiếu authority | Manager có stub nhưng policy chặn | GET endpoint cần role | Trả 403, không gọi outbound |
| Reactive không có client | `Mono.empty()` | Pipeline reactive | Lỗi có kiểm soát, không gửi HTTP |
| Reactive có client | `Mono.just(client)` | WebClient ExchangeFunction giả | Header bearer và body đúng |
| Refresh thật | **Không mock manager** | Token endpoint giả + token store | Số lần cấp/refresh và token mới đúng |

### 14.2. Bài tập

**Bài 1 — Cô lập token issuance.** Viết `CatalogGateway` dùng `OAuth2AuthorizedClientManager` như mục 4. Dùng Mockito trả `OAuth2AuthorizedClient` có token giả. Kiểm tra bằng `ArgumentCaptor` rằng service yêu cầu đúng `clientRegistrationId` và principal.

**Bài 2 — Xác minh request đi.** Kết hợp `MockRestServiceServer` với `RestClient`. Trả JSON từ API đối tác giả; assert method, URL, bearer header và response.

**Bài 3 — Fail closed.** Thêm hai ca manager trả `null` và ném `OAuth2AuthorizationException`. Chứng minh service không tiếp tục gửi HTTP outbound.

**Bài 4 — Phân biệt security inbound/outbound.** Tạo controller gọi gateway; bảo vệ endpoint bằng `SecurityFilterChain`. Dùng MockMvc để kiểm tra request anonymous, authenticated và thiếu authority. Manager mock chỉ nhận lời gọi sau khi inbound authorization thành công.

**Bài 5 — Reactive.** Chuyển gateway sang `ReactiveOAuth2AuthorizedClientManager` và `WebClient`. Dùng `Mono.just(client)` cho thành công, `Mono.empty()` cho lỗi; kiểm tra bearer token qua mock `ExchangeFunction`.

**Bài 6 — Integration theo grant thực.** Dùng token endpoint giả, manager/provider thật và kho authorized clients test. Kiểm tra token issuance/cache/refresh theo đúng grant thực tế của dự án; so sánh kết quả với unit test đã mock.

Một bài làm đạt yêu cầu cần có **assertion về request gửi đến manager**, **assertion về header HTTP outbound**, **kiểm thử đường lỗi an toàn** và nêu rõ lý do unit test với mock manager **không xác nhận tính đúng đắn của token endpoint hoặc refresh token**.

## 15. Tài liệu tham khảo

- [Spring Security — Core Interfaces and Classes for OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): `ClientRegistration`, `OAuth2AuthorizedClient`, manager và authorized client services.
- [Spring Security — Authorized Client Features](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): quản lý và sử dụng authorized client trên Servlet.
- [Spring Security — OAuth2 Client (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): reactive manager và WebClient.
- [Spring Framework — Testing Clients](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): nguyên tắc dùng `MockRestServiceServer` và kiểm thử HTTP client.
- [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): kiểm thử inbound SecurityFilterChain bằng MockMvc.
