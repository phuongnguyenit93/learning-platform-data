# 17.7. Xử lý refresh token không được trả lại trong response

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, ứng dụng có thể giữ **refresh token** để xin access token mới khi access token hiện tại hết hạn hoặc sắp hết hạn. Một tình huống khiến nhiều hệ thống vô tình mất khả năng làm mới token là: **token endpoint trả response refresh thành công nhưng không có trường `refresh_token`**.

Điều này **không tự động là lỗi**. Theo OAuth 2.0, Authorization Server (AS) **có thể** cấp refresh token mới khi xử lý refresh token grant; nó không bắt buộc phải cấp token mới trong mọi response. Khi client đã có refresh token R1, một response refresh thành công chỉ cấp access token A2 thường có nghĩa client **giữ R1 đang có**. Nếu response cấp thêm refresh token R2, client phải **thay R1 bằng R2**.

Phải phân biệt rõ với **token response cấp lần đầu không có refresh token**. Khi chưa từng nhận được R1, client không thể tự làm mới access token qua refresh token grant và cũng không có token cũ để giữ.

Sau bài học, bạn có thể:

- Phân biệt response cấp token lần đầu với response của refresh token grant.
- Đọc phản hồi có/không có `refresh_token` và hiểu hệ quả về vòng đời token.
- Giải thích **giữ refresh token cũ khi không có token mới** và **thay token cũ khi AS cấp token mới**.
- Hiểu cách `OAuth2AccessTokenResponse`, `OAuth2AuthorizedClient`, `RefreshTokenOAuth2AuthorizedClientProvider` và manager phối hợp.
- Nhận biết lỗi custom code vô tình ghi `null` đè lên refresh token đang lưu.
- Xử lý `invalid_grant`, token rotation, response sai định dạng và nhiều request refresh đồng thời.
- Bảo vệ token trong repository, session, nhiều instance và khi logout.
- Phân biệt refresh access token với OIDC reauthentication, ID token và ủy quyền tại Resource Server.

## 1. Bối cảnh: refresh response thiếu token mới

Giả sử **Employee Portal** dùng Spring Boot, OIDC Authorization Code Login với OpenID Provider (OP) của doanh nghiệp. Sau login, Portal cần access token để gọi **Orders API**.

Token response sau Authorization Code có thể là:

~~~json
{
  "access_token": "ACCESS_A1",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "REFRESH_R1",
  "id_token": "ID_TOKEN_1",
  "scope": "openid profile orders.read"
}
~~~

Các chuỗi token chỉ là placeholder, không phải token thật. Spring Security xác minh kết quả OIDC, thiết lập principal và lưu `OAuth2AuthorizedClient` chứa access token A1 cùng refresh token R1.

Sau đó A1 hết hạn. Client gọi token endpoint bằng R1:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Authorization: Basic <CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_R1
~~~

Request minh họa phương thức xác thực confidential client bằng HTTP Basic; client thật phải dùng phương thức đã đăng ký với AS.

AS trả:

~~~json
{
  "access_token": "ACCESS_A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "openid profile orders.read"
}
~~~

**Không có `refresh_token`.** Một token response như vậy có thể hoàn toàn hợp lệ: AS cấp access token mới nhưng không cấp refresh token thay thế.

Trạng thái hợp lý:

~~~text
Trước khi refresh:
  accessToken  = A1
  refreshToken = R1

Response:
  accessToken  = A2
  refreshToken = không có trường này

Authorized client sau khi cập nhật:
  accessToken  = A2
  refreshToken = R1
~~~

Nếu custom code chỉ lấy `response.getRefreshToken()` và ghi thẳng vào authorized client, ứng dụng có thể vô tình lưu `refreshToken = null`, khiến lần refresh tiếp theo không có credential để sử dụng.

## 2. Câu hỏi quan trọng: có refresh token trước response không?

| Trường hợp | Refresh token trước đó | Response hiện tại | Trạng thái sau xử lý |
|---|---|---|---|
| Authorization Code cấp token lần đầu | Chưa có | A1, không có refresh token | A1, không có refresh token |
| Authorization Code cấp token lần đầu | Chưa có | A1 + R1 | A1 + R1 |
| Refresh token grant, không rotation ở lượt này | Đã có R1 | A2, không có refresh token mới | A2 + R1 |
| Refresh token grant có rotation | Đã có R1 | A2 + R2 | A2 + R2; bỏ R1 |
| Refresh grant thất bại | Có thể còn R1 | OAuth error như `invalid_grant` | Xử lý lỗi; không coi là refresh thành công |

Điểm khác biệt không nằm ở việc JSON có trường `refresh_token` hay không một cách đơn lẻ. Quan trọng hơn là **ngữ cảnh grant** và **trạng thái authorized client trước lúc thực hiện grant**.

### 2.1. Chưa từng được cấp refresh token

Token response ban đầu:

~~~json
{
  "access_token": "ACCESS_A1",
  "token_type": "Bearer",
  "expires_in": 600,
  "id_token": "ID_TOKEN_1"
}
~~~

Client có thể đăng nhập và gọi API bằng A1 nhưng không có R1. Khi A1 hết hạn, `refresh_token` provider không có refresh token để dùng. Ứng dụng có thể phải bắt đầu Authorization Code flow mới hoặc dùng grant khác được AS cho phép.

**Không tự tạo refresh token từ ID token, access token hoặc authorization code cũ.**

### 2.2. Đã có R1, response refresh không cấp R2

Nếu AS xử lý refresh token grant thành công và trả access token A2 nhưng không cấp refresh token mới, trong mô hình thông thường client tiếp tục giữ R1 để có thể sử dụng lần sau.

Điều này **không phải lời bảo đảm R1 còn hợp lệ mãi mãi**. AS vẫn có thể giới hạn thời gian sống, thu hồi, áp chính sách số lần sử dụng hoặc đổi quy tắc cấp token theo client.

### 2.3. Đã có R1, response refresh cấp R2

Nếu response chứa R2:

~~~json
{
  "access_token": "ACCESS_A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "REFRESH_R2"
}
~~~

Client phải lưu A2/R2 và **bỏ R1**. Giữ R1 làm token dự phòng có thể vi phạm rotation policy hoặc kích hoạt cơ chế phát hiện reuse khi dùng lại.

## 3. OAuth 2.0 quy định gì?

### 3.1. Refresh token mới không bắt buộc có trong mỗi refresh response

Trong OAuth 2.0, AS **có thể phát hành refresh token mới** khi client thực hiện refresh token grant. Khi phát hành token mới, client phải thay token cũ bằng token mới.

Vì thế:

- **Không có token mới trong response thành công:** không tự suy ra AS yêu cầu xóa token cũ.
- **Có token mới trong response thành công:** không tiếp tục sử dụng token cũ như credential còn hợp lệ.
- **AS trả OAuth error:** không tạo authorized client mới từ response lỗi.

Đây là logic quan trọng khi xây custom provider hoặc tích hợp token store.

### 3.2. Refresh token khác authorization code

Authorization code là giá trị ngắn hạn dùng **một lần** để đổi token. Không được suy ra rằng mọi refresh token cũng phải dùng một lần.

AS có thể triển khai:

- Refresh token được phép dùng nhiều lần cho đến khi hết hạn hoặc bị thu hồi.
- Refresh token rotation, mỗi lần thành công phát một token mới.
- Chính sách token family và phát hiện sử dụng lại token đã rotate.
- Ràng buộc refresh token với client và những điều kiện bảo mật khác.

Client phải tuân thủ đúng hợp đồng AS đang dùng.

### 3.3. Không đánh đồng token thiếu với token không hợp lệ

Ba tình huống khác nhau:

~~~json
{
  "access_token": "ACCESS_A2",
  "token_type": "Bearer",
  "expires_in": 600
}
~~~

~~~json
{
  "access_token": "ACCESS_A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": null
}
~~~

~~~json
{
  "access_token": "ACCESS_A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": ""
}
~~~

**Vắng mặt** `refresh_token` là tình huống khác với trả giá trị JSON `null` hoặc chuỗi rỗng. Hai giá trị sau không phải refresh token hợp lệ. Chúng có thể cho thấy provider trả dữ liệu sai schema hoặc một quy ước đặc thù mà client không nên âm thầm chấp nhận.

Đừng tự coi chuỗi rỗng là token mới. Hãy để token response client kiểm tra response theo hợp đồng thực tế.

### 3.4. Response thành công vẫn cần access token hợp lệ

Một response:

~~~json
{
  "token_type": "Bearer",
  "expires_in": 600
}
~~~

không trở thành response refresh hợp lệ chỉ vì HTTP status là 200. Token response thành công cần những trường bắt buộc theo OAuth, bao gồm access token và token type.

**Thiếu refresh token mới có thể hợp lệ; thiếu access token trong token response thành công là vấn đề khác.**

## 4. Dòng thời gian khi AS không rotate mỗi lượt

Giả sử AS cho phép dùng R1 nhiều lần:

~~~text
T0  Authorization Code thành công:
    cấp A1 + R1
    client lưu A1/R1

T1  A1 hết hạn:
    gửi refresh_token=R1
    AS trả A2, không có R2
    client lưu A2/R1

T2  A2 hết hạn:
    gửi refresh_token=R1
    AS trả A3, không có R3
    client lưu A3/R1

T3  R1 hết hạn hoặc bị thu hồi:
    AS trả invalid_grant
    client xử lý authorization mới nếu cần
~~~

Đây là một mô hình hợp lệ nếu AS cho phép tái sử dụng refresh token trong thời gian hiệu lực. Dù vậy, AS có thể từ chối ở bất cứ thời điểm nào theo policy; client không được xem R1 là credential vĩnh viễn.

## 5. Dòng thời gian khi AS dùng refresh token rotation

Mô hình rotation:

~~~text
T0  Lần đầu:
    A1 / R1

T1  Dùng R1:
    AS cấp A2 / R2
    client thay R1 bằng R2

T2  Dùng R2:
    AS cấp A3 / R3
    client thay R2 bằng R3

T3  Dùng lại R1:
    AS từ chối theo policy reuse
~~~

Điểm cần nhớ:

- Khi có refresh token mới, **lưu token mới**.
- Không dùng refresh token cũ làm fallback mặc định.
- Cần tránh request khác ghi đè cặp token mới bằng dữ liệu đã cũ.
- Một số AS có thể thu hồi token family khi thấy token đã rotate bị dùng lại.

**Quy tắc giữ R1 chỉ áp dụng khi response thành công không cấp token thay thế, không áp dụng khi response đã cấp R2.**

## 6. Spring Security biểu diễn kết quả refresh thế nào?

### 6.1. `OAuth2AccessTokenResponse`

Spring Security biểu diễn kết quả token endpoint bằng:

~~~java
org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse
~~~

Đối tượng này chứa `OAuth2AccessToken`, `OAuth2RefreshToken` nếu có, các scope và metadata liên quan.

Với response refresh không có `refresh_token`, lời gọi:

~~~java
OAuth2RefreshToken returnedRefreshToken =
        tokenResponse.getRefreshToken();
~~~

có thể trả `null`.

**`null` ở đây mô tả response hiện tại không có refresh token mới**, không tự chứng minh R1 trong authorized client cũ đã bị AS thu hồi.

### 6.2. `OAuth2AuthorizedClient`

Authorized client đã lưu chứa:

~~~java
OAuth2AccessToken currentAccessToken =
        authorizedClient.getAccessToken();

OAuth2RefreshToken storedRefreshToken =
        authorizedClient.getRefreshToken();
~~~

Khi tạo trạng thái mới sau refresh, phải xem **cả token response** và **authorized client đang tồn tại**.

### 6.3. `RefreshTokenOAuth2AuthorizedClientProvider`

Provider refresh token của Spring Security:

~~~java
org.springframework.security.oauth2.client.RefreshTokenOAuth2AuthorizedClientProvider
~~~

Trong luồng refresh thông thường, provider xử lý theo nguyên tắc:

~~~text
updatedAccessToken = response.accessToken

updatedRefreshToken =
    response.refreshToken != null
        ? response.refreshToken
        : existingAuthorizedClient.refreshToken
~~~

Khi response có R2, chọn R2. Khi response không có token mới, giữ R1 từ authorized client hiện có. **Đây là hành vi quan trọng giúp tránh làm mất refresh token khi dùng provider chuẩn.**

### 6.4. `OAuth2AuthorizedClientManager`

Manager điều phối:

~~~text
OAuth2AuthorizedClientManager
├── ClientRegistrationRepository
├── OAuth2AuthorizedClientRepository / Service
├── OAuth2AuthorizedClientProvider
│   └── RefreshTokenOAuth2AuthorizedClientProvider
└── Authorization success / failure handlers
~~~

Sau refresh thành công, manager có thể lưu authorized client cập nhật qua success handler. Đảm bảo nơi lưu và nơi đọc token nhất quán; nếu sử dụng hai repository/service khác nhau, request kế tiếp có thể thấy dữ liệu cũ.

## 7. Minh họa Java: không ghi `null` đè R1

### 7.1. Ghép response vào authorized client đã lưu

Ví dụ minh họa logic cập nhật:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

public final class RefreshResultMerger {

    private RefreshResultMerger() {}

    public static OAuth2AuthorizedClient merge(
            OAuth2AuthorizedClient existing,
            OAuth2AccessTokenResponse response) {

        OAuth2RefreshToken newRefreshToken =
                response.getRefreshToken();

        OAuth2RefreshToken effectiveRefreshToken =
                newRefreshToken != null
                        ? newRefreshToken
                        : existing.getRefreshToken();

        return new OAuth2AuthorizedClient(
                existing.getClientRegistration(),
                existing.getPrincipalName(),
                response.getAccessToken(),
                effectiveRefreshToken);
    }
}
~~~

Đây là **mã minh họa cơ chế**, không có nghĩa mọi dự án phải tự cài đặt refresh provider. Trong ứng dụng sử dụng Spring Security manager/provider chuẩn, logic giữ refresh token cũ đã được provider xử lý.

### 7.2. Kết quả cho ba trường hợp

| Authorized client trước | Response | Kết quả merge |
|---|---|---|
| A1/R1 | A2, không có R2 | A2/R1 |
| A1/R1 | A2/R2 | A2/R2 |
| A1, refresh token null | A2, không có refresh token | A2, refresh token null |

Hàm không tạo refresh token nếu AS chưa từng cấp.

### 7.3. Cách ghép sai làm mất token

~~~java
// Sai về logic: response thiếu refresh_token có thể làm mất R1.
OAuth2AuthorizedClient updated = new OAuth2AuthorizedClient(
        existing.getClientRegistration(),
        existing.getPrincipalName(),
        response.getAccessToken(),
        response.getRefreshToken());
~~~

Nếu response không có refresh token, giá trị cuối là `null`. Ứng dụng có thể mất khả năng refresh lần sau.

**Không nên sửa bằng cách thay đổi JSON response của AS để nhét R1 vào.** Hãy phân biệt dữ liệu AS thật sự phát hành với trạng thái mà client giữ trong authorized client.

## 8. Cấu hình Spring Boot OIDC Client

### 8.1. Dependency

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

### 8.2. Registration

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

- `corporate` là registration ID của Spring Security.
- `openid` cho biết client sử dụng OpenID Connect.
- `orders.read` là scope API minh họa, phải được AS và API cho phép.
- `issuer-uri` xác định OP đáng tin cậy.
- Client secret được lấy từ môi trường hoặc secret manager.

**Chỉ cấu hình OIDC Login không đảm bảo refresh token luôn được cấp.** Điều đó phụ thuộc AS, kiểu client, scope, consent và chính sách.

### 8.3. `offline_access` có bắt buộc không?

Trong OIDC, scope `offline_access` liên quan việc yêu cầu khả năng truy cập khi End-User không hiện diện. Một số provider dùng scope này hoặc cấu hình client riêng để quyết định phát refresh token.

Không nên khẳng định:

- Cứ có `openid` là luôn có refresh token.
- Cứ thêm `offline_access` là chắc chắn có refresh token.
- Mọi OP có cùng yêu cầu consent cho refresh token.
- Muốn token lâu dài thì không cần xét rủi ro bảo mật.

Khi **response cấp token đầu tiên không có R1**, hãy kiểm tra tài liệu/contract provider, client registration và chính sách cấp quyền; không tự phát minh token.

### 8.4. Servlet filter chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

`oauth2Login()` hỗ trợ luồng browser redirect/callback; `oauth2Client()` phục vụ việc sử dụng authorized client khi gọi API theo cấu hình.

## 9. Bật refresh provider trong `OAuth2AuthorizedClientManager`

Ví dụ manager cho Servlet:

~~~java
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
                new DefaultOAuth2AuthorizedClientManager(
                        registrations,
                        repository);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Với cấu hình này:

1. Manager tìm authorized client của registration/principal.
2. Nếu token còn đủ điều kiện dùng, manager có thể trả client đã lưu.
3. Nếu cần refresh và có refresh token, provider dùng refresh token grant.
4. Nếu AS cấp A2 mà không cấp R2, provider giữ R1 đang có.
5. Authorized client cập nhật được lưu theo success handler của manager.

Không mặc định mỗi lần gọi `authorize()` đều gửi request đến token endpoint.

### 9.1. Luồng refresh response không có R2

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Controller / HTTP Client
    participant Manager as OAuth2AuthorizedClientManager
    participant Repo as Authorized Client Repository
    participant Provider as Refresh Token Provider
    participant AS as Authorization Server
    App->>Manager: authorize(corporate, Alice)
    Manager->>Repo: load authorized client
    Repo-->>Manager: A1 / R1
    Manager->>Provider: reauthorize khi cần
    Provider->>AS: refresh_token=R1
    AS-->>Provider: access_token=A2, không cấp R2
    Note over Provider: Giữ R1 từ authorized client cũ
    Provider-->>Manager: A2 / R1
    Manager->>Repo: save A2 / R1
    Manager-->>App: authorized client cập nhật
~~~

Không cần thay đổi response raw của AS. Việc ghép trạng thái xảy ra trong client/provider.

## 10. Đọc trạng thái token mà không làm lộ credential

Trong Servlet controller có thể nhận authorized client:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthorizedClientStatusController {

    @GetMapping("/client-status")
    TokenStatus status(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        if (client == null) {
            return new TokenStatus(false, false, null);
        }

        return new TokenStatus(
                client.getAccessToken() != null,
                client.getRefreshToken() != null,
                client.getAccessToken() != null
                        ? client.getAccessToken().getExpiresAt()
                        : null);
    }

    record TokenStatus(
            boolean hasAccessToken,
            boolean hasRefreshToken,
            Instant accessTokenExpiry) {}
}
~~~

Ví dụ này không trả token raw. Trong production, endpoint trạng thái cũng cần policy authentication và chỉ trả dữ liệu thực sự cần.

### 10.1. Trả về refresh token cho frontend là sai mục đích

Không trả:

~~~json
{
  "refresh_token": "REFRESH_R1"
}
~~~

chỉ để frontend biết “token còn tồn tại”. Dùng một cờ `hasRefreshToken` nếu thật sự cần UI hiển thị trạng thái. Refresh token phải được giữ trong kho bảo mật phù hợp với kiến trúc.

### 10.2. ID token không phải access token

`OidcUser.getIdToken()` phục vụ xác thực End-User tại RP. Khi gọi Orders API, phải dùng access token dành cho API từ authorized client.

Không lấy ID token để gọi API khi refresh token không được trả lại.

## 11. Repository/service phải giữ trạng thái cập nhật

Các abstraction liên quan:

| Abstraction | Công việc |
|---|---|
| `OAuth2AuthorizedClientRepository` | Lưu/đọc/xóa authorized client theo Servlet request/response |
| `OAuth2AuthorizedClientService` | Lưu/đọc/xóa theo registration ID + principal |
| `HttpSessionOAuth2AuthorizedClientRepository` | Một implementation dựa trên HttpSession |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Có thể dùng service cho authenticated principal và session repository cho anonymous |
| `OAuth2AuthorizedClientManager` | Điều phối provider và success/failure handling |

Sau refresh thành công, dữ liệu phải được ghi vào **đúng kho mà request tiếp theo sử dụng**.

Ví dụ:

~~~text
Lần refresh ở Portal A:
  load A1/R1
  AS trả A2, không có R2
  save A2/R1

Request sau ở Portal B:
  phải thấy A2/R1 nếu dùng shared store
~~~

Nếu B dùng kho độc lập, nó có thể vẫn thấy A1/R1 hoặc không có authorized client. Đây là vấn đề lưu trữ, không nhất thiết do AS “không trả refresh token”.

### 11.1. `saveAuthorizedClient` với service

Một authorized client hợp lệ có thể được lưu:

~~~java
OAuth2AuthorizedClient updated = ...;  // Kết quả từ manager/provider
Authentication principal = ...;        // Principal đã xác thực

authorizedClientService.saveAuthorizedClient(updated, principal);
~~~

Đây chỉ là đoạn minh họa interface. Nếu success handler của manager đã lưu authorized client, không tự lưu lặp lại ở mọi controller.

### 11.2. Token phải thuộc đúng principal

Nếu Alice và Bob cùng dùng registration `corporate`, token của Alice không được tái sử dụng trong request của Bob.

Nếu custom persistence dùng một khóa toàn cục như `registrationId` mà không xét principal/session, có thể trộn token.

Với nhiều OIDC issuer hoặc tenant, identity key nên dựa trên một danh tính nội bộ tin cậy liên kết đúng cặp `iss` + `sub`, thay vì dùng email hoặc `sub` đơn lẻ mà không xét issuer.

## 12. Những trường hợp dễ làm mất R1 trong custom code

### 12.1. Ghi đè object theo response mới

Mẫu sai:

~~~text
existing authorized client = A1/R1
token response             = A2/no R2

custom object mapper:
  access_token  <- response.access_token
  refresh_token <- response.refresh_token (null)
~~~

Kết quả A2/null. Lần sau không còn R1.

Giải pháp: logic ghép trạng thái cần giữ R1 khi response **không cấp token mới**.

### 12.2. Mapper JSON gán default null

Nếu ứng dụng tự serialize `OAuth2AuthorizedClient` sang JSON/DB và update toàn bộ row từ response, một field không xuất hiện trong response có thể bị mapper biến thành `null` và ghi đè refresh token đang lưu.

Cần phân biệt **absent** với **explicit replacement** trong phương pháp update, và chỉ cho các thành phần đáng tin cậy thay đổi token.

### 12.3. Chỉ lưu access token mới

Một custom success handler có thể chỉ ghi access token A2 vào DB mà không giữ refresh token R1. Đó cũng là làm mất khả năng refresh.

Nên lưu/cập nhật authorized client nguyên trạng hợp lệ từ provider/manager, không xây bản ghi tối giản thiếu refresh token nếu ứng dụng còn cần refresh sau này.

### 12.4. Đọc và ghi ở hai kho khác nhau

Manager lưu A2/R1 qua `OAuth2AuthorizedClientService`, còn controller đọc từ `HttpSessionOAuth2AuthorizedClientRepository` cũ. Token có thể “biến mất” hoặc không đồng bộ.

Phải xác định repository/service nào là nguồn dữ liệu thực sự cho luồng cấp token và gọi API.

## 13. Lỗi `invalid_grant` sau khi giữ R1

Giả sử AS từng trả A2 nhưng không cấp R2. Client giữ R1. Đến lần refresh tiếp theo:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant"
}
~~~

Điều này có thể do:

- R1 hết hạn.
- R1 bị user/AS thu hồi.
- Client registration hoặc quyền đã thay đổi.
- Một request khác đã dùng R1 và AS áp rotation.
- AS có chính sách single-use hoặc token family khác kỳ vọng.
- R1 không phù hợp client đang gửi request.
- Token bị sử dụng ngoài ý muốn, AS áp reuse detection.

Không thể chỉ nhìn `invalid_grant` rồi kết luận chắc chắn “client đã giữ R1 sai”. Cần xem chính sách provider và dữ liệu vận hành giảm nhạy cảm.

### 13.1. Xử lý lỗi

1. Không thử lại vô hạn cùng refresh token cũ.
2. Xác định lỗi ở token endpoint, khác lỗi API 401/403.
3. Dùng failure handler/manager để xóa hoặc đánh dấu authorized client cũ khi chính sách yêu cầu.
4. Nếu cần và có user, bắt đầu Authorization Code flow mới.
5. Nếu là service không có user, sử dụng grant/service identity phù hợp.
6. Không dùng ID token hoặc authorization code cũ như refresh token.

**Xóa local authorized client không tự động revoke token tại AS.**

### 13.2. AS rotate mà không trả token mới?

Nếu hợp đồng provider nói R1 sẽ bị vô hiệu hóa ngay sau mỗi refresh nhưng response thành công lại không cấp R2, client không thể tự suy ra token thay thế.

Khi đó cần điều tra behavior của AS và khả năng lỗi tích hợp. Nếu R1 không thể dùng lại, client có thể phải xin authorization mới. **Không tạo token giả hoặc tiếp tục retry R1 vô hạn.**

## 14. Request đồng thời và refresh token rotation

### 14.1. Race điển hình

~~~text
Request A load A1/R1
Request B load A1/R1

A: refresh R1 -> A2/R2
B: refresh R1 -> invalid_grant (hoặc reuse policy)
~~~

Nếu request B ghi trạng thái cũ đè lên A2/R2, ứng dụng mất refresh token mới.

Cần xem xét:

- Lock/single-flight theo registration và principal.
- Ghi cập nhật có điều kiện hoặc transaction phù hợp.
- Kho token chia sẻ giữa các instance.
- Bảo toàn cặp A2/R2 khi AS rotate.
- Không lấy R1 từ snapshot cũ ghi đè sau khi đã có R2.
- Giới hạn retry và báo lỗi đúng ngữ cảnh.

Không mặc định session repository hoặc manager luôn cung cấp atomic refresh trên nhiều thread/nhiều node.

### 14.2. AS cho phép dùng lại R1

Nếu AS không rotate và hai request cùng refresh R1:

~~~text
A: R1 -> A2, không có R2
B: R1 -> A3, không có R3
~~~

Hai request có thể cùng thành công theo chính sách AS. Tuy vậy việc ghi access token A2/A3 vẫn có concurrency; cần tránh trạng thái bị ghi đè gây dùng token lỗi thời hoặc nhầm principal.

### 14.3. Response bị mất

Nếu AS đã cấp A2/R2 và vô hiệu hóa R1 nhưng network làm mất response, client có thể chỉ còn R1. Một lần retry R1 có thể bị AS từ chối.

Client không thể phục hồi R2 bằng suy đoán. Cần policy retry, khả năng grace của AS nếu có hoặc authorization flow mới. Đây là một failure mode của rotation cần dự liệu.

## 15. Refresh response và lỗi API là hai chuyện khác

| Response | Nguồn | Ý nghĩa |
|---|---|---|
| Token endpoint trả A2, không có R2 | Authorization Server | Refresh thành công, không cấp token thay thế |
| Token endpoint trả `invalid_grant` | Authorization Server | Refresh thất bại |
| Orders API trả 401 | Resource Server | Access token không được chấp nhận hoặc request chưa xác thực |
| Orders API trả 403 | Resource Server | Thiếu quyền truy cập |
| Orders API trả JSON đơn hàng | Resource Server | Không liên quan việc cấp refresh token |

Nếu API trả 401, cần phân biệt access token hết hạn, sai audience, bị thu hồi, sai issuer hoặc lỗi token profile. Một access token vừa refresh vẫn có thể bị API từ chối nếu audience/scope không phù hợp.

**Không coi mọi 401/403 là tín hiệu phải refresh R1**, và không coi việc JSON API không có `refresh_token` là lỗi.

## 16. Có cần ID token mới trong refresh response không?

Trong OIDC:

- ID token xác thực End-User cho Relying Party.
- Access token dùng truy cập Resource Server.
- Refresh token dùng xin token mới tại token endpoint theo quyền và chính sách AS.

Một refresh response có thể không có ID token mới tùy flow/provider. Điều này **khác** việc thiếu refresh token mới.

~~~text
Không có id_token mới
    !=
Không có refresh_token mới
    !=
Access token refresh thất bại
~~~

Refresh token grant thành công cũng **không tự chứng minh user vừa xác thực lại**. Nếu ứng dụng yêu cầu MFA mới hoặc authentication freshness, cần OIDC Authentication Request và kiểm tra `auth_time`, `acr` hoặc những claim phù hợp theo chính sách.

## 17. Bảo mật refresh token trong kho lưu

Refresh token là credential có thể cho phép nhận access token mới. Vì vậy nó cần được bảo vệ:

- HTTPS khi trao đổi với AS.
- Client authentication/PKCE theo flow và loại client.
- Access control cho kho authorized client.
- Mã hóa kết nối và dữ liệu lưu trữ khi phù hợp.
- TTL, cleanup và chính sách backup/replication.
- Không ghi token raw vào logs/tracing.
- Không trả refresh token ra frontend.
- Không chia sẻ token giữa principal hoặc tenant.
- Dọn token khi logout/ngắt kết nối provider theo policy.

### 17.1. HttpSession và refresh token

Nếu authorized client được lưu trong `HttpSession`, session store có thể chứa refresh token. Session cookie thường chỉ chứa định danh phiên chứ không chứa token raw, nhưng bị chiếm cookie có thể khiến attacker sử dụng quyền của phiên.

Bảo vệ `HttpOnly`, `Secure`, `SameSite` phù hợp, HTTPS, CSRF, session fixation và session store.

### 17.2. Logout và revoke

Logout Portal có thể xóa local session, nhưng không mặc định thu hồi refresh token tại AS. Nếu token lưu ở `OAuth2AuthorizedClientService` ngoài session, logout cũng không tự dọn record đó nếu không có chính sách.

`removeAuthorizedClient` xóa trạng thái cục bộ; token revocation tại AS là thao tác khác.

### 17.3. Không dùng refresh token làm token API

Refresh token chỉ dùng với token endpoint theo grant phù hợp. Nó **không** được gửi đến Orders API trong header `Authorization: Bearer`. Resource Server thông thường cần access token với audience/scope đúng.

## 18. Quan sát an toàn: biết AS có trả R2 không mà không log token

Các trường telemetry có thể hữu ích:

~~~text
registrationId: corporate
principalReference: internal-user-id
authorizedClientFound: true
refreshAttempted: true
refreshSucceeded: true
newRefreshTokenReturned: false
storedRefreshTokenPresent: true
accessTokenExpiry: timestamp
errorType: none
~~~

Không ghi:

~~~text
raw access token
raw refresh token
id_token
authorization code
code_verifier
client secret
JSESSIONID / session cookie
serialized OAuth2AuthorizedClient
~~~

Nếu cần nhận biết request trùng, dùng correlation ID riêng, không dùng token thô làm ID.

### 18.1. Quy trình điều tra lỗi “refresh lần đầu được, lần sau không”

1. Kiểm tra lần cấp token đầu có refresh token R1 hay không.
2. Kiểm tra lần refresh đầu có thực sự gọi token endpoint không.
3. Nếu response chỉ trả A2, xác nhận authorized client sau khi lưu còn R1.
4. Nếu response trả R2, xác nhận kho đã thay R1 bằng R2.
5. Nếu đã có R1/R2 nhưng lần sau lỗi, kiểm tra expiry, revocation, rotation hoặc race.
6. Nếu request ở nhiều instance đọc trạng thái khác nhau, xem backing store.
7. Nếu có custom provider/mapper/success handler, kiểm tra nơi cập nhật token.
8. Không thử lặp refresh token thật vô hạn ở production; AS có thể áp reuse detection.

## 19. Lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Refresh thành công rồi mất R1 | Ghi `null` từ response lên authorized client | Giữ R1 cũ nếu không có R2 |
| AS trả R2 nhưng lần sau vẫn dùng R1 | Không lưu token mới khi rotation | Lưu R2, loại bỏ R1 |
| Response đầu không có refresh token | AS không cấp R1 | Xem client policy/scope/consent |
| `invalid_grant` sau khi giữ R1 | R1 hết hạn, revoke, rotation/race | Điều tra policy và xử lý authorization mới |
| HTTP 200 nhưng không có access token | Response không hợp lệ | Báo lỗi parser/token response client |
| `refresh_token` là chuỗi rỗng/null | Dữ liệu không hợp lệ hoặc đặc thù provider | Không coi là token mới hợp lệ |
| Token mới chỉ thấy trong một request | Kho lưu/success handler sai | Đồng nhất repository/service |
| Nhiều node làm mất R2 | State cũ ghi đè hoặc token store không chia sẻ | Đồng bộ update |
| API 401 sau refresh | Access token sai audience/issuer/expiry | Xem Resource Server policy |
| API 403 sau refresh | Thiếu quyền nghiệp vụ/scope | Không coi refresh là tăng quyền |
| Logout xong token vẫn hợp lệ | Local cleanup khác revocation | Cân nhắc revoke tại AS |
| ID token dùng làm refresh token | Nhầm loại token | Sử dụng refresh token được AS cấp |

## 20. Bài tập tình huống

### Tình huống A — Chưa từng có R1

**Đầu vào:** Authorization Code response có A1 và ID token, không có refresh token.

**Kết quả:** Client không có refresh token để giữ. Khi A1 hết hạn, cần Authorization Code flow mới hoặc grant khác được AS hỗ trợ.

### Tình huống B — Có R1, response không có R2

**Đầu vào:** Stored authorized client A1/R1; AS trả A2, không có refresh token.

**Kết quả:** Thông thường lưu A2/R1. Không ghi `null` đè R1.

### Tình huống C — Có R1, response có R2

**Đầu vào:** A1/R1; AS trả A2/R2.

**Kết quả:** Lưu A2/R2 và bỏ R1; nếu dùng lại R1 có thể bị phát hiện reuse.

### Tình huống D — AS từ chối R1 lần sau

**Đầu vào:** A2/R1 được lưu, lần sau `invalid_grant`.

**Kết quả:** Không kết luận chỉ vì giữ R1 mà client sai. Cần xem AS expiry, revocation, race, rotation và hợp đồng provider; xử lý lỗi thay vì retry vô hạn.

### Tình huống E — Hai request đồng thời

**Đầu vào:** Hai request cùng dùng R1, một request nhận R2, request khác lỗi.

**Kết quả:** Kiểm soát concurrency và thứ tự ghi, tránh ghi R1 cũ đè R2.

### Tình huống F — AS trả success nhưng không có A2

**Đầu vào:** HTTP 200 chỉ có `expires_in`.

**Kết quả:** Đây không phải token response thành công hoàn chỉnh để cập nhật authorized client. Parser/client cần báo lỗi.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Refresh response thành công không có `refresh_token` mới có luôn là lỗi không?

**Trả lời:** Không. AS có thể cấp access token mới mà không cấp refresh token thay thế.

**Câu 2.** Client có A1/R1, response refresh chỉ có A2. Nên lưu gì?

**Trả lời:** Thông thường A2/R1; giữ token cũ khi không có token thay thế, theo hợp đồng AS.

**Câu 3.** Nếu response có A2/R2 thì có giữ R1 làm dự phòng được không?

**Trả lời:** Không. Phải thay R1 bằng R2 khi được AS cấp refresh token mới.

**Câu 4.** Response cấp token ban đầu không có refresh token, có R1 để giữ không?

**Trả lời:** Không. Client chưa từng được cấp refresh token.

**Câu 5.** `OAuth2AccessTokenResponse.getRefreshToken() == null` có chứng minh R1 đã bị revoke không?

**Trả lời:** Không. Nó có thể chỉ cho biết response hiện tại không cấp refresh token mới.

**Câu 6.** Spring Security refresh provider thường xử lý thế nào khi response không có R2?

**Trả lời:** Giữ refresh token từ authorized client cũ khi tạo authorized client cập nhật.

**Câu 7.** Nếu AS trả R2 mà client lưu R1, điều gì có thể xảy ra?

**Trả lời:** Refresh tiếp theo có thể gặp `invalid_grant` hoặc cơ chế reuse detection.

**Câu 8.** Việc giữ R1 có đảm bảo R1 còn hiệu lực mãi không?

**Trả lời:** Không. AS quyết định expiry, revocation và policy khác.

**Câu 9.** API trả 403 sau refresh có phải chắc chắn refresh token bị mất không?

**Trả lời:** Không. 403 thường liên quan authorization/scope/ownership.

**Câu 10.** ID token có thể thay refresh token không?

**Trả lời:** Không. Hai token có mục đích và quy tắc dùng khác nhau.

**Câu 11.** Vì sao request đồng thời có thể làm mất R2?

**Trả lời:** Request khác có thể lưu snapshot A1/R1 cũ sau khi một request đã lưu A2/R2.

**Câu 12.** Xóa local authorized client có đồng nghĩa revoke tại AS không?

**Trả lời:** Không. Local cleanup và token revocation tại AS khác nhau.

## Ghi nhớ

- **Response refresh thành công không có `refresh_token` không mặc định là lỗi.** AS có thể không cấp refresh token mới ở mỗi lượt.
- **Lần cấp token đầu không có refresh token** nghĩa là chưa có credential để dùng refresh token grant.
- **Đã có R1, refresh response cấp A2 nhưng không cấp R2:** thông thường giữ **A2/R1**.
- **Response cấp A2/R2:** phải lưu **A2/R2** và bỏ R1 theo rotation.
- **`RefreshTokenOAuth2AuthorizedClientProvider` của Spring Security** có logic giữ refresh token cũ khi response không cấp token mới; ưu tiên manager/provider chuẩn hơn custom ghép response tùy tiện.
- **Giữ R1 không bảo đảm R1 hợp lệ vĩnh viễn.** AS có thể áp expiry, revocation và reuse detection; xử lý `invalid_grant` có kiểm soát.
- **Lưu token đúng principal/registration và cập nhật nhất quán**, đặc biệt khi có rotation, nhiều request đồng thời hoặc nhiều node.
- **Refresh token là credential nhạy cảm**: không log, không gửi tới frontend/API tài nguyên, không dùng ID token thay thế và không nhầm local cleanup với AS revocation.
