# Repository hoặc service lưu authorized client trong Spring Security

Trong ứng dụng OAuth2 Client, đăng nhập thành công hoặc lấy được access token mới chỉ là một phần của bài toán. Ứng dụng còn cần biết **token thuộc client registration nào**, **được cấp thay mặt principal nào**, **có còn được lưu để dùng cho request sau không** và **được xóa hoặc cập nhật khi nào**. Spring Security dùng `OAuth2AuthorizedClient` để biểu diễn thông tin này; các interface `OAuth2AuthorizedClientRepository` và `OAuth2AuthorizedClientService` cung cấp những cách truy cập, lưu và xóa authorized client.

Trong module **SPRING_SECURITY_TESTING**, chủ đề này gắn trực tiếp với việc kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test`. Người học cần biết lúc nào nên kiểm tra kho lưu thật, lúc nào nên dùng `oauth2Client()` hoặc `mockOAuth2Client()` để tạo tình huống có token, và vì sao kiểm thử `@WithMockUser`, `oauth2Login()` hay JWT giả lập chưa đủ để khẳng định token đã được lưu chính xác.

## 1. Authorized client là gì?

`ClientRegistration` mô tả ứng dụng khách đã đăng ký với authorization server, chẳng hạn `registrationId=reports`, `clientId`, các endpoint authorization/token và grant type. Sau khi client được cấp token, `OAuth2AuthorizedClient` chứa thông tin gắn với lần ủy quyền đó:

| Thành phần | Vai trò |
| --- | --- |
| `ClientRegistration` | Xác định OAuth2 client và cấu hình provider mà token thuộc về |
| `principalName` | Danh tính gắn với authorized client, ví dụ `alice` |
| `OAuth2AccessToken` | Token dùng để ứng dụng gọi API bên ngoài; có giá trị, loại token, thời gian hiệu lực và scope |
| `OAuth2RefreshToken` (có thể không có) | Token dùng xin access token mới khi grant/provider hỗ trợ |

Ví dụ, một ứng dụng báo cáo cho phép người dùng Alice kết nối đến API kế toán:

~~~text
registrationId = reports
principalName  = alice
accessToken    = access-alice-test
refreshToken   = refresh-alice-test

registrationId = reports
principalName  = bob
accessToken    = access-bob-test
refreshToken   = refresh-bob-test
~~~

Hai authorized client cùng `registrationId` nhưng thuộc **hai principal khác nhau**, nên không được vô tình trả access token của Alice khi Bob đang thực hiện request. Trong các hệ thống đa người dùng, đây là ranh giới cần kiểm thử rõ.

**Authorized client khác SecurityContext.** `SecurityContext` chứa `Authentication` hiện tại của người dùng hoặc lời gọi. `OAuth2AuthorizedClient` chứa thông tin ủy quyền của *ứng dụng khách* để có thể gọi một tài nguyên OAuth2 khác. Một principal đã đăng nhập không bảo đảm rằng mọi client registration đều có authorized client đã lưu.

**Authorized client cũng khác ClientRegistration.** Một bản ghi `ClientRegistration` có thể tồn tại ngay khi ứng dụng khởi động; chỉ khi một phiên ủy quyền đã cấp token thành công mới có `OAuth2AuthorizedClient` tương ứng để lưu.

## 2. Phân biệt Repository và Service

Trên **Servlet stack**, hai interface có chủ đích khác nhau:

| Tiêu chí | `OAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClientService` |
| --- | --- | --- |
| Ngữ cảnh | Luồng web có `HttpServletRequest` và `HttpServletResponse` | Truy xuất theo thông tin ứng dụng, không cần request |
| Khóa tra cứu | `clientRegistrationId`, `Authentication` và request | `clientRegistrationId`, `principalName` |
| Phương thức | `loadAuthorizedClient`, `saveAuthorizedClient`, `removeAuthorizedClient` | Cùng ba nhóm thao tác load/save/remove, nhưng không nhận request |
| Nơi dữ liệu có thể được lưu | Session hoặc cơ chế được ủy nhiệm | Bộ nhớ, cơ sở dữ liệu hoặc implementation khác |
| Phù hợp với | Controller và request liên quan đến OAuth2 client | Service/application logic, worker hoặc thao tác độc lập HTTP |

Chữ “repository” không có nghĩa luôn dùng database. Chẳng hạn `HttpSessionOAuth2AuthorizedClientRepository` lưu thông tin trong HTTP session. Ngược lại, `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` có thể **ủy nhiệm cho `OAuth2AuthorizedClientService`** khi principal đã xác thực, và sử dụng cơ chế lưu theo session khi principal chưa xác thực. Vì vậy cùng một ứng dụng có thể sử dụng cả repository lẫn service.

Các implementation thường gặp:

- `HttpSessionOAuth2AuthorizedClientRepository`: lưu authorized client theo session HTTP; cần giữ cùng session khi kiểm thử các request liên tiếp.
- `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`: dùng service đối với principal đã xác thực và cơ chế lưu trong session cho tình huống không có principal đã xác thực.
- `InMemoryOAuth2AuthorizedClientService`: lưu theo principal và client registration trong bộ nhớ process; thuận tiện cho demo/test và mất dữ liệu khi process kết thúc.
- `JdbcOAuth2AuthorizedClientService`: lưu qua JDBC; thích hợp khi ứng dụng cần tầng lưu trữ bền vững và đã thiết lập schema, quyền và chính sách bảo vệ token phù hợp.

Lựa chọn phụ thuộc vào cách ứng dụng sử dụng OAuth2 client. Với request người dùng trong ứng dụng Servlet, repository thuận tiện vì có thông tin request/session. Với xử lý chạy theo lịch hoặc bên ngoài HTTP request, service có thể phù hợp hơn.

### Hợp đồng phương thức cần hiểu

~~~java
// Repository: cần ngữ cảnh HTTP.
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response);

void removeAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response);

// Service: định danh bản lưu bằng registrationId và principalName.
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId, String principalName);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal);

void removeAuthorizedClient(
    String clientRegistrationId, String principalName);
~~~

Các chữ ký trên được rút gọn theo mục đích giải thích; trong API thực, hàm `loadAuthorizedClient` sử dụng generic trả về kiểu con của `OAuth2AuthorizedClient`. Kết quả `null` từ service/repository Servlet có thể biểu thị chưa có authorized client được lưu với cặp định danh đó.

## 3. Repository/Service nằm ở đâu trong luồng OAuth2 Client?

~~~mermaid
flowchart TD
    A["HTTP request hoặc tác vụ ứng dụng"] --> B["OAuth2AuthorizedClientManager"]
    B --> C{"Đã có authorized client phù hợp?"}
    C -->|Có| D["Đọc từ Repository/Service"]
    C -->|Chưa có| E["OAuth2AuthorizedClientProvider xử lý grant"]
    D --> F{"Token cần được cấp mới / làm mới?"}
    F -->|Có| E
    F -->|Không| G["Dùng access token gọi API"]
    E --> H{"Authorization thành công?"}
    H -->|Có| I["Lưu authorized client mới hoặc cập nhật"]
    H -->|Không| J["Phản ánh lỗi / xử lý xóa theo policy"]
    I --> G
~~~

`OAuth2AuthorizedClientManager` quản lý việc lấy, cấp mới hoặc làm mới authorized client tùy grant và cấu hình `OAuth2AuthorizedClientProvider`. Repository/service **chỉ là tầng lưu trữ**: bản thân lời gọi `loadAuthorizedClient` không tự thực hiện HTTP request tới token endpoint hoặc làm mới access token.

Hai manager quan trọng trên Servlet:

1. `DefaultOAuth2AuthorizedClientManager`: thường dùng trong ngữ cảnh `HttpServletRequest`, kết hợp `ClientRegistrationRepository` và `OAuth2AuthorizedClientRepository`.
2. `AuthorizedClientServiceOAuth2AuthorizedClientManager`: dùng `OAuth2AuthorizedClientService`, phù hợp với tác vụ chạy ngoài Servlet request khi được cấu hình authorized client provider phù hợp.

Ví dụ mô hình xử lý:

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports")
        .principal(authentication)
        .build();

OAuth2AuthorizedClient authorizedClient =
    authorizedClientManager.authorize(request);

if (authorizedClient == null) {
    // Không tìm thấy hoặc không thể cấp authorized client
    // theo tình huống mà provider/manager hỗ trợ.
    throw new IllegalStateException("Client authorization unavailable");
}
~~~

Không dùng kết quả `null` để kết luận chắc chắn token bị từ chối: một số grant, provider hoặc trạng thái không được hỗ trợ cũng có thể khiến `authorize(...)` không trả authorized client. Các lỗi cụ thể thường được biểu diễn bằng ngoại lệ và handler; kiểm thử nên dựa trên hợp đồng của manager đã cấu hình.

### Servlet và Reactive tương ứng

| Servlet | Reactive (WebFlux) |
| --- | --- |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `HttpSessionOAuth2AuthorizedClientRepository` | `WebSessionServerOAuth2AuthorizedClientRepository` |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository` |
| `InMemoryOAuth2AuthorizedClientService` | `InMemoryReactiveOAuth2AuthorizedClientService` |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |

Reactive API sử dụng `Mono` thay cho kết quả đồng bộ và sử dụng `ServerWebExchange` thay cho Servlet request/response. Không mang `HttpServletRequest` vào WebFlux hoặc chặn luồng Reactive bằng `block()` trong logic request.

## 4. Tạo dữ liệu authorized client kiểm thử

Để kiểm tra tầng lưu trữ, không cần IdP thật. Test có thể tạo `ClientRegistration`, access token và refresh token với giá trị giả lập. Ví dụ một fixture chung cho các test Java:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

final class AuthorizedClientFixtures {
    private AuthorizedClientFixtures() {}

    static ClientRegistration reports() {
        return ClientRegistration.withRegistrationId("reports")
            .clientId("reports-test-client")
            .clientSecret("test-only-secret")
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .authorizationUri("https://idp.example.test/oauth2/authorize")
            .tokenUri("https://idp.example.test/oauth2/token")
            .scope("reports.read")
            .clientName("Reports API")
            .build();
    }

    static Authentication principal(String name) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name, "not-a-real-password",
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    static OAuth2AuthorizedClient authorizedClient(
            ClientRegistration registration, String name) {
        Instant now = Instant.now();

        OAuth2AccessToken accessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "access-token-for-" + name,
            now.minusSeconds(30),
            now.plusSeconds(600),
            Set.of("reports.read"));

        OAuth2RefreshToken refreshToken = new OAuth2RefreshToken(
            "refresh-token-for-" + name, now.minusSeconds(30));

        return new OAuth2AuthorizedClient(
            registration, name, accessToken, refreshToken);
    }
}
~~~

Các giá trị `idp.example.test`, `access-token-for-alice` và `refresh-token-for-alice` chỉ dành cho test. Tạo một `OAuth2AuthorizedClient` trực tiếp **không phát sinh** một lần ủy quyền thật và không chứng minh token có hiệu lực với API của nhà cung cấp.

## 5. Kiểm thử OAuth2AuthorizedClientService trên Servlet

Service có hợp đồng lưu theo `clientRegistrationId` và `principalName`. Đặc biệt cần kiểm tra tính độc lập giữa Alice và Bob, việc cập nhật cùng một cặp khóa và thao tác xóa.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;

import static org.assertj.core.api.Assertions.assertThat;

class AuthorizedClientServiceTest {
    private ClientRegistration reports;
    private OAuth2AuthorizedClientService service;

    @BeforeEach
    void setup() {
        reports = AuthorizedClientFixtures.reports();
        service = new InMemoryOAuth2AuthorizedClientService(
            new InMemoryClientRegistrationRepository(reports));
    }

    @Test
    void saveAndLoadForSamePrincipalAndRegistration() {
        Authentication alice = AuthorizedClientFixtures.principal("alice");
        OAuth2AuthorizedClient client =
            AuthorizedClientFixtures.authorizedClient(reports, "alice");

        service.saveAuthorizedClient(client, alice);

        OAuth2AuthorizedClient loaded =
            service.loadAuthorizedClient("reports", "alice");
        assertThat(loaded).isNotNull();
        assertThat(loaded.getPrincipalName()).isEqualTo("alice");
        assertThat(loaded.getClientRegistration().getRegistrationId())
            .isEqualTo("reports");
        assertThat(loaded.getAccessToken().getTokenValue())
            .isEqualTo("access-token-for-alice");
        assertThat(loaded.getRefreshToken()).isNotNull();
    }

    @Test
    void oneUsersAuthorizedClientIsNotAnotherUsersClient() {
        service.saveAuthorizedClient(
            AuthorizedClientFixtures.authorizedClient(reports, "alice"),
            AuthorizedClientFixtures.principal("alice"));

        assertThat(service.loadAuthorizedClient("reports", "bob")).isNull();

        service.saveAuthorizedClient(
            AuthorizedClientFixtures.authorizedClient(reports, "bob"),
            AuthorizedClientFixtures.principal("bob"));

        assertThat(service.loadAuthorizedClient("reports", "alice")
            .getAccessToken().getTokenValue()).isEqualTo("access-token-for-alice");
        assertThat(service.loadAuthorizedClient("reports", "bob")
            .getAccessToken().getTokenValue()).isEqualTo("access-token-for-bob");
    }

    @Test
    void removingOnePrincipalDoesNotRemoveTheOther() {
        service.saveAuthorizedClient(
            AuthorizedClientFixtures.authorizedClient(reports, "alice"),
            AuthorizedClientFixtures.principal("alice"));
        service.saveAuthorizedClient(
            AuthorizedClientFixtures.authorizedClient(reports, "bob"),
            AuthorizedClientFixtures.principal("bob"));

        service.removeAuthorizedClient("reports", "alice");

        assertThat(service.loadAuthorizedClient("reports", "alice")).isNull();
        assertThat(service.loadAuthorizedClient("reports", "bob")).isNotNull();
    }
}
~~~

Mỗi `@BeforeEach` tạo một service mới để các test độc lập. Kiểm tra **giá trị token cố định chỉ trong môi trường test** là hợp lệ; với ứng dụng chạy thật, tránh ghi token hoặc refresh token vào log/report kiểm thử.

### Điều gì chưa được test ở đây?

Những phép thử service chỉ chứng minh khả năng lưu, đọc và xóa theo định danh. Chúng **không chạy** OAuth2 authorization code exchange, không gọi token endpoint, không kiểm tra refresh token còn dùng được và không xác nhận access token đang được API bên ngoài chấp nhận. Các khả năng đó thuộc kiểm thử manager/provider và luồng HTTP với authorization server được mô phỏng.

Khi thay `InMemoryOAuth2AuthorizedClientService` bằng `JdbcOAuth2AuthorizedClientService`, cần bổ sung integration test dùng database/schema kiểm thử để kiểm tra lưu/đọc/xóa thật, transaction và các điều kiện cô lập dữ liệu phù hợp. Test đơn thuần với in-memory service không chứng minh cấu hình JDBC đã chính xác.

## 6. Kiểm thử OAuth2AuthorizedClientRepository qua hai Servlet request

Với principal đã xác thực, `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` có thể ủy nhiệm việc lưu/đọc cho service. Bài test sau gửi các đối tượng request khác nhau để xác nhận authorized client vẫn truy xuất được bằng cùng `Authentication`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

import static org.assertj.core.api.Assertions.assertThat;

class AuthorizedClientRepositoryTest {

    @Test
    void authenticatedPrincipalLoadsClientAcrossRequests() {
        ClientRegistration reports = AuthorizedClientFixtures.reports();
        var service = new InMemoryOAuth2AuthorizedClientService(
            new InMemoryClientRegistrationRepository(reports));
        OAuth2AuthorizedClientRepository repository =
            new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(service);

        Authentication alice = AuthorizedClientFixtures.principal("alice");
        OAuth2AuthorizedClient client =
            AuthorizedClientFixtures.authorizedClient(reports, "alice");

        repository.saveAuthorizedClient(
            client, alice,
            new MockHttpServletRequest(), new MockHttpServletResponse());

        OAuth2AuthorizedClient loaded = repository.loadAuthorizedClient(
            "reports", alice, new MockHttpServletRequest());

        assertThat(loaded).isNotNull();
        assertThat(loaded.getPrincipalName()).isEqualTo("alice");
        assertThat(service.loadAuthorizedClient("reports", "alice"))
            .isNotNull();

        Authentication bob = AuthorizedClientFixtures.principal("bob");
        assertThat(repository.loadAuthorizedClient(
            "reports", bob, new MockHttpServletRequest())).isNull();

        repository.removeAuthorizedClient(
            "reports", alice,
            new MockHttpServletRequest(), new MockHttpServletResponse());

        assertThat(service.loadAuthorizedClient("reports", "alice")).isNull();
    }
}
~~~

Đây là **test hợp đồng của repository**, chưa đi qua `SecurityFilterChain` hoặc endpoint MVC. Việc hai `MockHttpServletRequest` khác nhau vẫn đọc được client minh họa đặc điểm của `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` khi nó ủy nhiệm cho service đối với authenticated principal. Với `HttpSessionOAuth2AuthorizedClientRepository`, hãy dùng **cùng một `MockHttpSession`** cho các request tiếp theo; tạo session mới có thể khiến dữ liệu không còn truy xuất được.

Nếu ứng dụng lựa chọn repository tùy biến, cần kiểm tra việc ánh xạ `principalName`, session key, namespace hoặc tenant. Đừng giả định mọi implementation đều có hành vi lưu giống nhau.

## 7. MockMvc: cách tạo authorized client trong một HTTP test

Giả sử controller yêu cầu authorized client của registration `reports`:

~~~java
@RestController
class ReportsController {

    @GetMapping("/api/reports/connected")
    Map<String, String> connected(
            @RegisteredOAuth2AuthorizedClient("reports")
            OAuth2AuthorizedClient authorizedClient) {
        return Map.of(
            "registrationId",
            authorizedClient.getClientRegistration().getRegistrationId());
    }
}
~~~

Trong test tích hợp MVC có Spring Security filter chain, có thể dùng `oauth2Client("reports")` của `SecurityMockMvcRequestPostProcessors` để tạo authorized client mẫu:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Client;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ReportsControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void controllerCanReceiveAnAuthorizedClientFixture() throws Exception {
        mvc.perform(get("/api/reports/connected")
                .with(user("alice"))
                .with(oauth2Client("reports")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.registrationId").value("reports"));
    }
}
~~~

Khi test dùng `oauth2Client()`, Spring Security Test chuẩn bị authorized client giả lập cho request. Test phù hợp để kiểm tra controller nhận đúng registration, logic downstream và quyền HTTP khi có principal. **Nó chưa kiểm tra một OAuth2 Client thực sự đã thực hiện authorization code grant, đã lưu authorized client vào service lâu dài hoặc đã refresh token thành công.** Để kiểm tra việc lưu bền giữa các request, hãy sử dụng repository/service thực của ứng dụng và readback trong một test riêng.

`oauth2Login()` cũng là một tiện ích test quan trọng, nhưng mục đích chủ yếu là đặt một `OAuth2AuthenticationToken` và principal đăng nhập OAuth2 vào ngữ cảnh kiểm thử. Một người dùng đăng nhập OAuth2 **không mặc nhiên chứng minh** authorized client cho mọi registration đã tồn tại trong kho lưu. Vì vậy tránh kết luận “token đã được lưu” chỉ từ:

~~~java
mockMvc.perform(get("/some-secured-page").with(oauth2Login()))
    .andExpect(status().isOk());
~~~

Tương tự, `@WithMockUser` chỉ tạo `Authentication` giả lập, còn `jwt()` kiểm thử Resource Server ở phía **nhận Bearer token**. Chúng không thay thế test kho lưu OAuth2 Client ở phía **lấy token để gọi API khác**.

### Nếu muốn kiểm thử toàn bộ OAuth2 login và lưu authorized client

Một bài kiểm thử end-to-end hoặc integration test nên mô phỏng authorization server và thực hiện chuỗi:

1. Truy cập `/oauth2/authorization/reports` để khởi tạo authorization request, giữ session và giá trị `state`.
2. Mô phỏng authorization server chuyển hướng về callback với `code` và `state` đúng.
3. Cấu hình token endpoint giả lập trả access/refresh token; nếu login cần UserInfo hoặc OIDC, mô phỏng cả endpoint/ID token đúng với cấu hình.
4. Quan sát request callback được xử lý thành công và kiểm tra authorized client đã lưu bằng repository/service của ứng dụng, đúng registration và principal.
5. Gửi request sau với cùng session/principal, xác nhận authorized client còn tải được; khi đăng xuất/xóa liên kết, kiểm tra chính sách xóa tương ứng.

Đây là bài test rộng hơn `oauth2Client()`. Hãy giữ IdP trong test dưới dạng HTTP server giả lập hoặc môi trường tích hợp riêng, không đưa client secret hay token sản xuất vào source.

## 8. ReactiveOAuth2AuthorizedClientService: lưu và đọc bằng Mono

Trên WebFlux, service cung cấp cùng ý nghĩa lưu/đọc/xóa nhưng phương thức trả về `Mono`. Có thể kiểm tra bằng `StepVerifier`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ReactiveAuthorizedClientServiceTest {

    @Test
    void saveLoadAndRemoveReactively() {
        ClientRegistration reports = AuthorizedClientFixtures.reports();
        ReactiveOAuth2AuthorizedClientService service =
            new InMemoryReactiveOAuth2AuthorizedClientService(
                new InMemoryReactiveClientRegistrationRepository(reports));

        Authentication alice = AuthorizedClientFixtures.principal("alice");
        OAuth2AuthorizedClient client =
            AuthorizedClientFixtures.authorizedClient(reports, "alice");

        StepVerifier.create(service.saveAuthorizedClient(client, alice))
            .verifyComplete();

        StepVerifier.create(service.loadAuthorizedClient("reports", "alice"))
            .assertNext(loaded -> {
                assertThat(loaded.getPrincipalName()).isEqualTo("alice");
                assertThat(loaded.getAccessToken().getTokenValue())
                    .isEqualTo("access-token-for-alice");
            })
            .verifyComplete();

        StepVerifier.create(service.loadAuthorizedClient("reports", "bob"))
            .verifyComplete(); // Mono.empty: Bob không có authorized client.

        StepVerifier.create(service.removeAuthorizedClient("reports", "alice"))
            .verifyComplete();

        StepVerifier.create(service.loadAuthorizedClient("reports", "alice"))
            .verifyComplete();
    }
}
~~~

Đoạn Reactive cần các thư viện Spring Security OAuth2 Client và `reactor-test` trong test dependencies. `Mono.empty()` ở thao tác load tương ứng trường hợp chưa có authorized client; `StepVerifier.verifyComplete()` giúp xác nhận publisher kết thúc mà không phát phần tử.

### Khi repository gắn với WebSession

`ServerOAuth2AuthorizedClientRepository` nhận thêm `ServerWebExchange` để có thể truy cập ngữ cảnh HTTP. Chẳng hạn, `WebSessionServerOAuth2AuthorizedClientRepository` lưu authorized client trong WebSession; khi kiểm thử nhiều request bằng `WebTestClient`, phải bảo toàn cookie/session của cùng client nếu muốn kiểm tra persistence qua WebSession.

`AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository` có thể sử dụng `ReactiveOAuth2AuthorizedClientService` cho principal đã xác thực, tương tự Servlet. Cần kiểm thử đúng implementation ứng dụng chọn. Một test chỉ gọi reactive service chưa chứng minh cookie, session và `SecurityWebFilterChain` đang phối hợp chính xác.

Spring Security Test trên WebFlux còn cung cấp tiện ích `mockOAuth2Client("reports")` khi `WebTestClient` được cấu hình với Spring Security:

~~~java
client.mutateWith(mockOAuth2Client("reports"))
    .get()
    .uri("/api/reports/connected")
    .exchange()
    .expectStatus().isOk();
~~~

Sử dụng tiện ích này để thử logic endpoint khi đã có authorized client giả lập. Nó không đi qua authorization/token endpoint và không thay việc kiểm tra WebSession hoặc reactive service lưu được dữ liệu giữa các request. Khi cần xác nhận thực tế request WebFlux có session, hãy dùng client và repository thật của test cùng cấu hình Spring Security thay vì dựa hoàn toàn vào mock.

## 9. Token hết hạn, refresh và việc xóa authorized client

Tầng lưu trữ chỉ phản ánh trạng thái được ghi; nó không có nghĩa vụ làm mới access token trước khi `loadAuthorizedClient` trả về. Thông thường một `OAuth2AuthorizedClientManager` cùng `OAuth2AuthorizedClientProvider` sẽ quyết định có cần refresh token hay grant mới dựa trên cấu hình và trạng thái token.

Các kịch bản cần tách rõ:

| Kịch bản | Thành phần cần kiểm thử | Kết quả cần quan sát |
| --- | --- | --- |
| Lưu access token lần đầu | Repository/service | `load` trả đúng registration và principal |
| Lấy token của người dùng khác | Repository/service | Không trả nhầm authorized client |
| Access token hết hạn, có refresh token | Manager/provider + token endpoint giả lập | Có refresh nếu được cấu hình và lưu token mới |
| Refresh token bị từ chối | Manager failure handler và kho lưu | Xử lý lỗi, và có thể xóa client theo chính sách |
| Logout | Session/security/logout handler + repository | Hành vi xóa authorized client đúng chính sách thực tế |
| Thu hồi kết nối OAuth2 | Logic ứng dụng + repository/service | Client bị xóa cho đúng principal và registration |
| Ứng dụng khởi động lại | Kho lưu bền vững (nếu có) | Client tồn tại hoặc mất đi theo thiết kế lưu trữ |

**Không mặc định logout luôn xóa mọi authorized client.** Xóa session, xóa `SecurityContext`, xóa authorized client trong database và thu hồi token ở authorization server là các thao tác khác nhau. Nếu nghiệp vụ yêu cầu xóa cả quyền đã cấp, cần triển khai và kiểm thử riêng.

**Không mặc định refresh luôn hoạt động.** Authorization grant có thể không có refresh token; cấu hình provider/manager và phản hồi token endpoint quyết định quá trình làm mới. Test service chỉ kiểm tra một access token hết hạn *đang được lưu* không chứng minh manager sẽ gọi refresh đúng.

Trong ví dụ ứng dụng thật, token access/refresh phải được bảo vệ theo chính sách bảo mật dữ liệu: giới hạn quyền truy cập nơi lưu, tránh xuất ra log, cân nhắc mã hóa khi lưu lâu dài, thiết lập TTL/xóa theo chính sách, và không để access token của principal này lọt sang principal khác.

## 10. Các lỗi thường gặp khi kiểm thử

**Nhầm client registration với authorized client.** Việc tìm thấy `ClientRegistration("reports")` chỉ chứng minh ứng dụng có cấu hình OAuth2 client, không chứng minh đã có token được cấp cho Alice.

**Chỉ kiểm tra SecurityContext.** `@WithMockUser("alice")` đủ cho nhiều test quyền HTTP nhưng không tự thêm `OAuth2AuthorizedClient` vào repository hoặc service. Phải kiểm tra đúng bản lưu.

**Giả sử mọi repository lưu vào database.** `HttpSessionOAuth2AuthorizedClientRepository` lưu vào session; `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` có thể ủy nhiệm vào service. Mỗi cơ chế cần test với ngữ cảnh phù hợp.

**Không kiểm tra tenant/principal.** Chỉ assert “load không null” dễ bỏ qua lỗi trả token của người dùng khác. Luôn thêm ca negative với principal khác và registration khác khi có nhiều client.

**Dùng `oauth2Client()` để khẳng định có lưu token thật.** Tiện ích này dựng authorized client phục vụ request test; nó không chứng minh quy trình authorization code, token exchange hay persistence độc lập test.

**Cho rằng repository tự refresh token.** Refresh là trách nhiệm của manager/provider được cấu hình. Tách test lưu trữ và test làm mới token để biết lỗi xuất hiện ở đâu.

**Kết luận toàn bộ token đã bị thu hồi khi xóa một bản lưu.** Xóa client local không nhất thiết vô hiệu hóa access token tại authorization server hoặc nơi tiếp nhận token.

**Để test nhiều request tạo session mới.** Nếu ứng dụng lưu theo session, phải tái sử dụng đúng `MockHttpSession` hoặc cookie WebSession. Session mới đồng nghĩa ngữ cảnh lưu khác.

**Gắn test Servlet với API Reactive.** `OAuth2AuthorizedClientRepository` và `ServerOAuth2AuthorizedClientRepository` dùng các kiểu request khác nhau; đừng cố dùng `HttpServletRequest` trong WebFlux.

**Log token để debug.** Có thể assert token giả trong fixture, nhưng không đưa access token thật, refresh token hoặc client secret thật vào báo cáo hoặc log thường trực.

## 11. Bài tập thực hành

1. Tạo `ClientRegistration("reports")` và authorized client cho Alice. Lưu vào `InMemoryOAuth2AuthorizedClientService`, đọc lại và kiểm tra registration, principal, access token cùng refresh token.
2. Lưu thêm client cho Bob với cùng registration. Chứng minh `loadAuthorizedClient("reports", "bob")` không bao giờ trả token của Alice; xóa Alice và xác minh Bob vẫn còn.
3. Tạo `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` sử dụng cùng service. Lưu bằng `MockHttpServletRequest` thứ nhất, đọc bằng request thứ hai với principal Alice; sau đó thử principal Bob.
4. Thay bằng `HttpSessionOAuth2AuthorizedClientRepository`. So sánh kết quả khi hai request dùng cùng `MockHttpSession` và khi dùng session khác.
5. Viết endpoint nhận `@RegisteredOAuth2AuthorizedClient("reports")` và test bằng `MockMvc` với `oauth2Client("reports")`. Giải thích vì sao thành công không chứng minh token đã được cấp qua authorization server.
6. Dùng `InMemoryReactiveOAuth2AuthorizedClientService` và `StepVerifier` để lưu/đọc/xóa authorized client. Kiểm tra trường hợp không có bản lưu hoàn thành bằng `Mono.empty()`.
7. Mô phỏng access token hết hạn rồi cấu hình `OAuth2AuthorizedClientManager` và token endpoint giả lập để kiểm tra refresh; assert token mới đã được ghi lại vào kho theo policy của ứng dụng.
8. Viết integration test logout/unlink account và kiểm tra repository/service sau thao tác. Phân biệt việc xóa bản lưu local với thu hồi token tại authorization server.

Khi kết thúc, người học cần trả lời được ba câu hỏi khác nhau: **đang dùng client registration nào**, **authorized client được lưu cho principal nào và ở đâu**, và **lúc nào manager mới lấy/làm mới token**. Phân biệt những phần này giúp viết các ca kiểm thử chính xác từ mức lưu trữ cho tới HTTP trên cả Servlet và Reactive.
