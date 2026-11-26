# registrationId, principalName và client registration

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Chương **Ứng dụng khách OAuth2** tập trung vào cách định danh một OAuth2 client trong Spring Security: `registrationId` xác định cấu hình client nào, `principalName` xác định authorized client gắn với chủ thể nào, và `ClientRegistration` chứa những thông tin gì để Spring thực hiện OAuth2 flow.

Sau bài học, bạn có thể:

1. Phân biệt `registrationId`, `clientId` và provider id.
2. Đọc một `ClientRegistration` từ cấu hình Spring Boot và từ Java builder.
3. Giải thích vì sao `OAuth2AuthorizedClient` cần cả registration và principal name.
4. Hiểu khóa tra cứu của `OAuth2AuthorizedClientService` và vai trò của `OAuth2AuthorizedClientRepository`.
5. Viết MockMvc test với registration id và principal name tường minh.
6. Phát hiện lỗi sai registration id, sai principal name và nhầm danh tính service với end user.

## 1. Ba tên định danh không có cùng ý nghĩa

Một cấu hình OAuth2 Client thường có ba tên dễ bị nhầm:

| Tên | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `registrationId` | `reports-client` | Khóa định danh cục bộ của cấu hình client trong ứng dụng Spring |
| `clientId` | `reporting-web-42` | Định danh client do authorization server cấp |
| Provider id | `company-idp` | Tên cấu hình provider dùng để tham chiếu endpoint và metadata của authorization server |

`registrationId` không phải một trường giao thức OAuth2 gửi tới authorization server. Nó là khóa nội bộ để ứng dụng tìm `ClientRegistration`. `clientId` mới là giá trị client identifier được gửi trong các bước protocol phù hợp, ví dụ authorization request hoặc token request.

Ví dụ cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-client:
            provider: company-idp
            client-id: reporting-web-42
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-idp:
            token-uri: https://identity.example.test/oauth2/token
~~~

Trong ví dụ:

- Registration id là `reports-client` vì nó là khóa dưới `registration`.
- Provider id là `company-idp` vì registration tham chiếu provider này.
- Client id là `reporting-web-42` vì đây là giá trị `client-id`.
- Token URI đến từ cấu hình provider, không phải registration id.

Trong Java, tìm registration bằng khóa cục bộ:

~~~java
ClientRegistration registration =
    clientRegistrationRepository.findByRegistrationId("reports-client");
~~~

Không truyền `reporting-web-42` vào `findByRegistrationId` chỉ vì đó là client id. Repository tìm theo registration id.

## 2. ClientRegistration mô tả cấu hình client

`ClientRegistration` là mô tả cấu hình của một OAuth2 client. Nó chứa thông tin cần để Spring Security tạo authorization request hoặc token request theo grant type được chọn.

Các nhóm thuộc tính chính:

| Thuộc tính | Mục đích |
| --- | --- |
| `registrationId` | Khóa nội bộ của registration |
| `clientId`, `clientSecret` | Credentials/định danh client do authorization server cấp |
| `clientAuthenticationMethod` | Cách client xác thực tại token endpoint |
| `authorizationGrantType` | Grant type, ví dụ `authorization_code` hoặc `client_credentials` |
| `redirectUri` | URI callback cho authorization code flow |
| `scopes` | Scope ứng dụng yêu cầu |
| `authorizationUri` | Authorization endpoint |
| `tokenUri` | Token endpoint |
| `userInfoUri` | UserInfo endpoint nếu dùng |
| `userNameAttributeName` | Tên thuộc tính định danh user từ UserInfo response |
| `jwkSetUri` / issuer metadata | Thông tin khóa/issuer phục vụ OIDC hoặc kiểm tra token tùy flow |
| `clientName` | Tên hiển thị của client |

Một registration không đồng nghĩa với một lần đăng nhập hay một access token. Cùng một registration có thể được dùng cho nhiều người dùng hoặc nhiều lần cấp token.

### 2.1. Tạo registration bằng Java

~~~java
ClientRegistration reportsClient =
    ClientRegistration.withRegistrationId("reports-client")
        .clientId("reporting-web-42")
        .clientSecret("test-secret")
        .clientName("Reports client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("reports.read")
        .tokenUri("https://identity.example.test/oauth2/token")
        .build();
~~~

Các import chính:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
~~~

`withRegistrationId("reports-client")` đặt khóa nội bộ. `clientId("reporting-web-42")` đặt client identifier mà authorization server cấp. Hai giá trị độc lập và không cần giống nhau.

### 2.2. Registration cho authorization code

Với một client dùng authorization code flow, cấu hình có thêm authorization endpoint, redirect URI và scope phù hợp:

~~~java
ClientRegistration webLogin =
    ClientRegistration.withRegistrationId("company-login")
        .clientId("web-portal-17")
        .clientSecret("test-secret")
        .clientName("Company login")
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid", "profile", "email")
        .authorizationUri("https://identity.example.test/oauth2/authorize")
        .tokenUri("https://identity.example.test/oauth2/token")
        .userInfoUri("https://identity.example.test/userinfo")
        .userNameAttributeName("sub")
        .jwkSetUri("https://identity.example.test/oauth2/jwks")
        .build();
~~~

Với OIDC, scope `openid` báo hiệu OpenID Connect; thông tin issuer và JWK Set thường được lấy từ provider metadata hoặc cấu hình tương ứng. Chỉ đặt các endpoint phù hợp với authorization server thực tế. Không dùng một registration client credentials để thay cho cấu hình authorization code login.

## 3. OAuth2AuthorizedClient gắn registration với principal

`OAuth2AuthorizedClient` biểu diễn một client đã được ủy quyền. Nó chứa:

- `ClientRegistration` mà token được cấp cho.
- `principalName` dùng để liên kết authorized client với principal trong ứng dụng.
- `OAuth2AccessToken`.
- `OAuth2RefreshToken` nếu có.

Mối quan hệ:

~~~mermaid
flowchart TB
    A["ClientRegistration<br/>registrationId = reports-client"] --> C["OAuth2AuthorizedClient"]
    B["Principal<br/>principalName = alice"] --> C
    D["OAuth2AccessToken<br/>scope = reports.read"] --> C
    E["OAuth2RefreshToken<br/>(nếu có)"] --> C
    C --> F["Repository / Service"]
~~~

Registration mô tả **ứng dụng client được cấu hình thế nào**. Authorized client biểu diễn **token nào đã được cấp cho registration đó và gắn với principal nào**.

`principalName` không phải `clientId` và cũng không nhất thiết là claim `sub` trong access token. Nó là tên principal mà Spring dùng để liên kết authorized client trong ứng dụng. Với user login, giá trị này thường khớp `Authentication.getName()`. Với client credentials, principal name có thể đại diện cho một service account hoặc danh tính ứng dụng do hệ thống chọn.

### 3.1. Cùng registration, nhiều principal

Một registration `reports-client` có thể có authorized client riêng cho `alice` và `bob`:

| registrationId | principalName | Ý nghĩa |
| --- | --- | --- |
| `reports-client` | `alice` | Token được lưu gắn với người dùng Alice |
| `reports-client` | `bob` | Token được lưu gắn với người dùng Bob |

Hai authorized client này có thể có access token, scope hoặc thời hạn khác nhau dù dùng cùng cấu hình registration.

### 3.2. Cùng principal, nhiều registration

Một principal `alice` có thể dùng nhiều OAuth2 client:

| registrationId | principalName | Ví dụ mục đích |
| --- | --- | --- |
| `reports-client` | `alice` | Gọi API báo cáo |
| `calendar-client` | `alice` | Gọi API lịch |
| `company-login` | `alice` | Client dùng cho đăng nhập OIDC |

Do đó, registration id và principal name cùng góp phần phân biệt authorized client. Chỉ biết tên user hoặc chỉ biết client id là chưa đủ để xác định một authorized client cụ thể.

## 4. principalName và khóa lưu trữ

`OAuth2AuthorizedClientService` cung cấp API tải và lưu authorized client theo hai giá trị:

~~~java
OAuth2AuthorizedClient authorizedClient =
    authorizedClientService.loadAuthorizedClient(
        "reports-client",
        "alice"
    );
~~~

Đối với service implementation theo hợp đồng Spring, cặp khóa tra cứu là:

~~~text
(clientRegistrationId, principalName)
~~~

`clientRegistrationId` chọn registration; `principalName` chọn chủ thể gắn với authorized client. Khi lưu client:

~~~java
authorizedClientService.saveAuthorizedClient(authorizedClient, authentication);
~~~

service dùng registration id của authorized client và danh tính trong tham số `Authentication` để xác định khóa lưu. Vì vậy, `authentication.getName()` nên nhất quán với `authorizedClient.getPrincipalName()`. Khi tải hoặc xóa, truyền đúng cặp registration id và principal name đã dùng lúc lưu.

`OAuth2AuthorizedClientRepository` có vai trò ở tầng web request: nó nhận request/response và `Authentication` để tải hoặc lưu authorized client cho request hiện tại. Repository mặc định có thể dùng session; repository được cấu hình khác có thể ủy quyền việc lưu trữ cho `OAuth2AuthorizedClientService`. Vì vậy, không nên giả định mọi repository đều dùng cùng một cơ chế vật lý hoặc cùng cấu trúc session.

Điều cần giữ nhất quán là:

1. Request đang mang principal nào?
2. Authorized client được lưu với principal name nào?
3. Registration id mà controller yêu cầu có đúng registration đã lưu không?

## 5. Registration id được dùng ở đâu?

Một registration id có thể xuất hiện ở nhiều điểm:

| Vị trí | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| YAML configuration | `registration.reports-client` | Khóa của registration trong cấu hình |
| `ClientRegistrationRepository` | `findByRegistrationId("reports-client")` | Tải cấu hình theo khóa |
| Controller argument | `@RegisteredOAuth2AuthorizedClient("reports-client")` | Yêu cầu authorized client của registration đó |
| MockMvc test | `oauth2Client("reports-client")` | Tạo authorized client giả lập cho request |
| Authorized client service | `loadAuthorizedClient("reports-client", "alice")` | Tải token đã lưu theo registration và principal |
| OAuth2 login URL | `/oauth2/authorization/company-login` | Registration id chọn client để bắt đầu login |

Registration id cần được thống nhất xuyên suốt. Đổi registration id trong cấu hình mà quên sửa annotation hoặc test sẽ khiến Spring tìm sai registration.

## 6. Kiểm thử registrationId và principalName với MockMvc

Ta tạo endpoint trả về metadata không nhạy cảm của authorized client để thấy hai giá trị được resolve chính xác. Trong ứng dụng thật, không trả access token hoặc client secret ra response.

### 6.1. Controller

~~~java
package example;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ClientInfoController {
    @GetMapping("/api/client-info")
    String clientInfo(
            @RegisteredOAuth2AuthorizedClient("reports-client")
            OAuth2AuthorizedClient client) {
        return client.getClientRegistration().getRegistrationId()
            + "|" + client.getClientRegistration().getClientId()
            + "|" + client.getPrincipalName();
    }
}
~~~

Để ví dụ dùng cùng cơ chế OAuth2 Client trong ứng dụng, security configuration cần bật OAuth2 Client support và yêu cầu Authentication:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ClientSecurityConfiguration {
    @Bean
    SecurityFilterChain clientSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Registration `reports-client` được tạo từ cấu hình OAuth2 Client ở mục 1. Khi chạy test trong application context, bảo đảm class cấu hình này và registration repository được nạp.

### 6.2. Test với registration và principal tường minh

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oauth2Client;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ClientRegistrationIdentityTest {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    ClientRegistrationRepository clientRegistrationRepository;

    @Test
    @WithMockUser(username = "alice")
    void authorizedClientBelongsToAlice() throws Exception {
        mockMvc.perform(get("/api/client-info")
                .with(oauth2Client("reports-client")
                    .clientRegistration(clientRegistrationRepository
                        .findByRegistrationId("reports-client"))
                    .principalName("alice")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "reports-client|reporting-web-42|alice"));
    }

    @Test
    @WithMockUser(username = "bob")
    void sameRegistrationCanBelongToBob() throws Exception {
        mockMvc.perform(get("/api/client-info")
                .with(oauth2Client("reports-client")
                    .clientRegistration(clientRegistrationRepository
                        .findByRegistrationId("reports-client"))
                    .principalName("bob")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "reports-client|reporting-web-42|bob"));
    }
}
~~~

Ví dụ giả định registration `reports-client` tồn tại với client id `reporting-web-42` và endpoint yêu cầu người dùng đã xác thực. `@WithMockUser` thiết lập Authentication; `oauth2Client(...)` cung cấp authorized client; `principalName(...)` xác định tên principal gắn với authorized client.

Đặt principal name tường minh giúp test thể hiện quan hệ cần kiểm tra. Với authorized client dành cho người dùng, thường nên khớp nó với `Authentication.getName()` để tránh tạo dữ liệu test mâu thuẫn với cách ứng dụng lưu và tải client.

## 7. Client credentials và principalName của service

Client credentials grant đại diện cho ứng dụng/service gọi API bằng quyền của chính client. Nó không có end user tham gia trực tiếp vào grant. Tuy vậy, `OAuth2AuthorizedClient` vẫn cần `principalName` để hệ thống lưu trữ và phân biệt authorized client.

Ví dụ:

~~~java
import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

OAuth2AccessToken accessToken = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "test-service-token",
    Instant.parse("2030-01-01T00:00:00Z"),
    Instant.parse("2030-01-01T00:05:00Z"),
    Set.of("reports.read")
);

OAuth2AuthorizedClient serviceClient =
    new OAuth2AuthorizedClient(
        reportsClient,
        "batch-report-worker",
        accessToken
    );
~~~

`batch-report-worker` là principal name do ứng dụng chọn để nhận diện workload. Nó không phải client id và cũng không phải subject do authorization server tự động suy ra từ token.

Nếu có hai worker dùng cùng registration:

| registrationId | principalName | Ý nghĩa |
| --- | --- | --- |
| `reports-client` | `nightly-report-worker` | Authorized client của job chạy ban đêm |
| `reports-client` | `reconciliation-worker` | Authorized client của job đối soát |

Hệ thống có thể lưu riêng trạng thái token cho từng workload. Trong triển khai client credentials, cần chọn principal name ổn định, dễ truy vết và phù hợp vòng đời của authorized client. Không tùy tiện dùng một tên chung nếu nhiều service identity cần được quản lý độc lập.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy registration | Dùng client id hoặc provider id thay cho registration id | Kiểm tra khóa dưới `registration` và dùng đúng giá trị |
| Controller không resolve được authorized client | Registration id trong annotation khác request | Đồng bộ `@RegisteredOAuth2AuthorizedClient` và `oauth2Client(...)` |
| Authorized client không được tìm thấy | Principal name khi lưu khác principal name khi tải | So sánh `Authentication.getName()` với `principalName` |
| Alice nhận token của workload khác | Dùng chung principal name cho nhiều loại client identity | Chọn principal name ổn định và phân biệt từng chủ thể |
| Registration có token nhưng không biết thuộc ai | Chỉ log registration id | Ghi nhận cả principal name theo chính sách log an toàn |
| Client credentials bị hiểu là user login | Nhầm service principal với OAuth2 end-user principal | Tách client authentication khỏi user authentication |
| Đổi client id làm test tìm registration thất bại | Nhầm `clientId` với `registrationId` trong repository lookup | Dùng `findByRegistrationId`, kiểm tra `getClientId()` riêng |
| Nhiều registration cùng gọi một provider | Cho rằng provider id là registration id | Mỗi client registration có id riêng dù cùng provider |

### Checklist khi debug

1. Khóa dưới `spring.security.oauth2.client.registration` là gì?
2. `ClientRegistration.getRegistrationId()` trả về giá trị nào?
3. `ClientRegistration.getClientId()` có đúng credentials của authorization server không?
4. Provider id đang tham chiếu endpoint nào?
5. Annotation và request post-processor có cùng registration id không?
6. Principal name của authorized client có khớp danh tính mà ứng dụng dùng để lưu/tải không?
7. Flow là authorization code hay client credentials; principal name đang đại diện user hay service?

## 9. Bài tập thực hành

**Bài 1 — Phân biệt ba id.** Tạo registration có id `billing-portal`, client id `billing-web-9` và provider id `corp-idp`. Viết test xác nhận mỗi API trả về đúng giá trị của nó.

**Bài 2 — Hai user, một registration.** Dùng cùng `billing-portal` nhưng principal name lần lượt `alice` và `bob`. Kiểm tra controller nhận đúng principal name trong từng request.

**Bài 3 — Sai registration id.** Đổi `oauth2Client("billing-portal")` thành client id `billing-web-9` trong test. Quan sát lỗi resolve, rồi sửa bằng registration id chính xác.

**Bài 4 — Client credentials.** Tạo authorized client với principal name `nightly-billing-worker`. Giải thích vì sao giá trị này đại diện workload và không phải client id hay end-user subject.

**Bài 5 — Lưu và tải.** Dùng `OAuth2AuthorizedClientService` để lưu client với registration `billing-portal` và principal `alice`; tải lại bằng cùng cặp khóa, sau đó thử thay một trong hai giá trị và quan sát kết quả.

## 10. Ghi nhớ

**`registrationId` chọn cấu hình OAuth2 Client trong ứng dụng; `clientId` định danh client tại authorization server; `principalName` cho biết authorized client được gắn với chủ thể nào.** Ba giá trị này có vai trò khác nhau và không thể thay thế cho nhau.

`ClientRegistration` mô tả cấu hình client. `OAuth2AuthorizedClient` kết hợp registration, principal name và token. Khi kiểm thử hoặc chẩn đoán, hãy dùng đúng registration id ở repository, annotation và MockMvc post-processor; đồng thời giữ principal name nhất quán với danh tính user hoặc service mà ứng dụng dùng để lưu/tải authorized client.
