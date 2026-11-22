# 15.10. Phân biệt authorize lần đầu, tái sử dụng token và cấp lại token

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, một ứng dụng thường gọi `OAuth2AuthorizedClientManager.authorize(...)` trước khi gửi request đến API. Tên phương thức dễ gây hiểu nhầm: **gọi authorize không đồng nghĩa luôn xin một access token mới**, cũng không đồng nghĩa yêu cầu người dùng đăng nhập lại.

Tùy trạng thái của authorized client và những `OAuth2AuthorizedClientProvider` đã được cấu hình, manager có thể thực hiện một trong ba hướng:

1. **Authorize lần đầu:** chưa có authorized client cho registration/principal tương ứng; client cần được cấp quyền và nhận token qua grant thích hợp.
2. **Tái sử dụng token:** authorized client đã tồn tại và không cần reauthorize; manager có thể trả lại object hiện có mà không gọi token endpoint.
3. **Cấp lại token:** access token cũ không còn dùng được hoặc sắp hết hạn; manager thử cơ chế reauthorization được hỗ trợ, chẳng hạn refresh token hoặc client credentials.

Ba khả năng trên giống nhau ở API gọi từ phía ứng dụng, nhưng khác **điều kiện**, **grant**, **tương tác của người dùng**, **lưu trữ** và **cách xử lý lỗi**.

Sau bài học, bạn có thể:

- Giải thích `ClientRegistration`, `OAuth2AuthorizedClient`, `OAuth2AuthorizedClientProvider` và `OAuth2AuthorizedClientManager` phối hợp thế nào.
- Phân biệt authorize lần đầu bằng `authorization_code` và `client_credentials`.
- Hiểu lý do một request gọi `authorize(...)` có thể dùng lại access token đã lưu.
- Mô tả refresh token grant và xin token mới bằng client credentials.
- Phân biệt refresh/cấp access token với **OIDC Login**, reauthentication và step-up authentication.
- Cấu hình manager cho ứng dụng Servlet và cho công việc không có HTTP request.
- Đọc kết quả `authorize()`, xử lý `null`, exception, `invalid_grant` và các lỗi API.
- Nhận biết rủi ro token rotation, request đồng thời, sai principal, sai audience và kho lưu không nhất quán.

## 1. Một bài toán, ba nhánh xử lý

Giả sử **Employee Portal** là ứng dụng Spring Boot cho nhân viên đăng nhập OIDC qua OpenID Provider (OP) của công ty. Sau đăng nhập, Portal dùng access token để gọi **Orders API**.

Ở một thời điểm, Portal cần token cho request:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <ACCESS_TOKEN>
~~~

Để lấy token, ứng dụng gọi manager với client registration và principal hiện tại.

| Thời điểm minh họa | Trạng thái trong kho authorized client | Kết quả mong muốn |
|---|---|---|
| 09:00 | Chưa có token cho Alice | Authorization Code flow lần đầu và lưu token |
| 09:02 | Access token A1 còn dùng được | Tái sử dụng A1 |
| 09:05 | A1 vẫn phù hợp | Tiếp tục dùng A1 |
| 09:10 | A1 hết hạn/sắp hết hạn; có refresh token R1 | Xin A2 bằng refresh token |
| 09:12 | A2 đã được lưu | Dùng lại A2 |
| 10:00 | Refresh token đã bị thu hồi | Không refresh được; xử lý lỗi hoặc bắt đầu flow mới |

Ví dụ trên chỉ nhằm minh họa, không phải TTL mặc định của token.

**Cùng một lời gọi `authorize()` có thể dẫn đến những hành vi khác nhau ở từng thời điểm.** Nếu không nắm điều này, ứng dụng dễ tạo vòng lặp xin token hoặc hiểu sai lý do không có lần đăng nhập OIDC mới.

## 2. Sơ đồ tổng quát

~~~mermaid
flowchart TD
    A["Ứng dụng cần token"] --> B["OAuth2AuthorizedClientManager.authorize"]
    B --> C["Tải trạng thái authorized client"]
    C --> D{"Đã có authorized client?"}
    D -->|Chưa| E["Provider phù hợp với grant lần đầu?"]
    E -->|client_credentials| F["Xin access token từ AS"]
    E -->|authorization_code| G["Cần authorization flow tương tác"]
    E -->|Không thể| H["Không có authorized client"]
    D -->|Có| I{"Provider cần và có thể reauthorize?"}
    I -->|Không| J["Dùng lại authorized client đã lưu"]
    I -->|refresh_token| K["Refresh access token tại AS"]
    I -->|client_credentials| L["Xin token mới bằng client credentials"]
    K --> M{"AS chấp nhận?"}
    L --> M
    M -->|Có| N["Lưu authorized client cập nhật"]
    M -->|Không| O["Failure handling theo chính sách"]
    F --> P["Lưu authorized client lần đầu"]
    G --> P
    P --> Q["Dùng access token đúng API"]
    J --> Q
    N --> Q
~~~

Sơ đồ mô tả các nhánh khái niệm. **Authorization Code browser redirect/callback không diễn ra trọn vẹn bên trong một lời gọi manager đồng bộ.** Các bước tương tác được Spring Security web filters và authorization request repository hỗ trợ.

## 3. Từ cấu hình đến trạng thái được cấp quyền

### 3.1. `ClientRegistration`

`ClientRegistration` mô tả client đã đăng ký với Authorization Server (AS):

~~~text
registrationId: corporate
clientId: employee-portal
authorizationGrantType: authorization_code
redirectUri: https://portal.example.com/login/oauth2/code/corporate
scope: openid profile orders.read
provider: company-oidc
~~~

Nó biết grant, endpoint và thông tin client. **Nó không chứa access token của Alice.**

### 3.2. `OAuth2AuthorizedClient`

Sau authorization thành công, Spring Security có thể lưu:

~~~text
OAuth2AuthorizedClient
├── clientRegistration: corporate
├── principalName: Alice
├── accessToken: A1
│   ├── issuedAt: ...
│   └── expiresAt: ...
└── refreshToken: R1 (nếu được cấp)
~~~

Authorized client được định vị theo mô hình lưu trữ tương ứng với registration/principal hoặc phiên. Một registration có thể có nhiều authorized client cho các principal khác nhau.

### 3.3. `OAuth2AuthorizedClientRepository` và `Service`

Hai abstraction đều quản lý authorized client, nhưng khác ngữ cảnh:

| Abstraction | Ngữ cảnh truy cập | Ví dụ |
|---|---|---|
| `OAuth2AuthorizedClientRepository` | HTTP Servlet request/response và Authentication | `HttpSessionOAuth2AuthorizedClientRepository` |
| `OAuth2AuthorizedClientService` | Registration ID và tên principal, không cần Servlet request | `InMemoryOAuth2AuthorizedClientService` hoặc service backed by database |

Repository lưu Authorization Request đang chờ callback là **abstraction khác**:

~~~text
OAuth2AuthorizationRequestRepository
    -> state / nonce / PKCE / callback correlation

OAuth2AuthorizedClientRepository
    -> access token / refresh token sau cấp quyền
~~~

Không hoán đổi hai kho chỉ vì tên lớp gần giống nhau.

### 3.4. `OAuth2AuthorizedClientProvider`

Provider biết thực hiện grant khi điều kiện phù hợp. Spring Security cung cấp cơ chế cấu hình:

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();
~~~

Một `DelegatingOAuth2AuthorizedClientProvider` có thể thử các provider theo thứ tự. **Mỗi provider chỉ thực hiện phần việc phù hợp với registration và authorization context hiện tại.**

### 3.5. `OAuth2AuthorizedClientManager`

Manager chịu trách nhiệm điều phối:

1. Xác định registration và principal.
2. Tìm authorized client đã lưu.
3. Tạo `OAuth2AuthorizationContext`.
4. Cho provider chain thử authorize/reauthorize.
5. Sử dụng success/failure handlers để lưu/xóa khi cần.
6. Trả về authorized client tương ứng hoặc không có kết quả nếu không thể authorize.

Đây là lý do `authorize()` không chỉ mang nghĩa “gọi token endpoint”.

## 4. Tình huống A: authorize lần đầu

### 4.1. Điều kiện đầu vào

~~~text
Client registration: corporate
Principal: Alice
Authorized client: chưa có
~~~

Manager phải xác định provider nào có khả năng tạo authorization lần đầu. **Grant type** quyết định phương án.

### 4.2. Lần đầu với Authorization Code và OIDC Login

Luồng `authorization_code` thông thường gồm:

1. Browser truy cập trang Portal cần xác thực.
2. Spring Security tạo Authorization Request, `state` và dữ liệu PKCE/nonce khi áp dụng.
3. Browser được chuyển đến OP.
4. OP xác thực/consent theo chính sách.
5. Browser quay về callback chứa code và state.
6. Client kiểm tra correlation, đổi code lấy token.
7. Spring Security xác minh ID token nếu là OIDC Login.
8. `OAuth2AuthorizedClient` được tạo và lưu cho các lần dùng sau.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant RP as Spring Security Portal
    participant OP as OpenID Provider
    participant Repo as Authorized Client Repository
    U->>B: Mở /orders
    B->>RP: Request chưa đăng nhập
    RP-->>B: Redirect tới OP
    B->>OP: Authorization Request
    OP->>U: Login/consent nếu cần
    OP-->>B: Redirect code và state
    B->>RP: Callback
    RP->>OP: Token request
    OP-->>RP: ID token + access token
    Note over RP: Tạo Authentication/OidcUser
    RP->>Repo: Save OAuth2AuthorizedClient
    RP-->>B: Redirect về ứng dụng
~~~

**Điểm quan trọng:** không kỳ vọng một background job gọi `manager.authorize(...)` có thể tự mở browser và xử lý toàn bộ redirect/callback. Authorization Code là flow tương tác, cần những thành phần web tương ứng.

### 4.3. “Lần đầu authorize” không nhất thiết là “lần đầu đăng nhập OP”

Alice có thể đã có phiên Single Sign-On tại OP. Khi Portal lần đầu xin authorization, OP có thể trả code mà không bắt Alice nhập lại mật khẩu.

Phân biệt:

- Portal chưa từng có authorized client cho Alice.
- Browser đã có phiên SSO tại OP.
- Portal tạo một Authentication/session mới.
- OP yêu cầu xác thực lại do chính sách.

Bốn trạng thái không bắt buộc trùng nhau.

### 4.4. Lần đầu với Client Credentials

Một service dùng `client_credentials` không cần End-User:

~~~text
Client: reporting-service
Principal kỹ thuật: reporting-job
Authorized client: chưa có

Manager -> clientCredentials provider
Provider -> token endpoint
AS -> access token S1
Manager -> lưu authorized client S1
~~~

Grant này xác thực **client/service**, không chứng minh một người dùng OIDC đã đăng nhập.

### 4.5. Manager không có provider đúng grant

Ví dụ registration `corporate` dùng `authorization_code` nhưng manager chỉ cấu hình:

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();
~~~

Không được kỳ vọng provider này tự lấy token cho `corporate`. Tương tự, một chain chỉ có `refreshToken()` không thể tạo token lần đầu khi chưa có refresh token.

**Grant type và provider phải phù hợp; không thể lấy token bằng cách “thử grant nào cũng được”.**

## 5. Tình huống B: tái sử dụng token đã có

### 5.1. Authorized client tồn tại

Ví dụ:

~~~text
corporate / Alice:
  access token A1
  expiresAt 10:30
  refresh token R1
~~~

Lúc 10:05, một request khác muốn gọi Orders API. Provider chain có thể thấy **không có nhu cầu reauthorize**, manager trả authorized client hiện có.

~~~text
manager.authorize(request)
  -> repository.loadAuthorizedClient(...)
  -> tìm thấy A1/R1
  -> provider không thực hiện grant mới
  -> trả về authorized client hiện có
~~~

Không phải gọi token endpoint và không có OIDC callback mới.

### 5.2. Lợi ích của việc tái sử dụng

- Ít request đến AS hơn.
- Giảm độ trễ gọi API.
- Tránh liên tục redirect browser.
- Giảm số access token được cấp.
- Hạn chế các tình huống consent hoặc login không cần thiết.

### 5.3. Tái sử dụng không đồng nghĩa token được API chấp nhận chắc chắn

Access token còn hạn theo `expiresAt` vẫn có thể:

- Bị AS/RS thu hồi.
- Có audience dành cho API khác.
- Thiếu scope.
- Không thuộc đúng tenant/user.
- Có issuer hoặc token profile không được API chấp nhận.

**Manager chủ yếu quản lý trạng thái authorization của client.** Resource Server vẫn phải kiểm tra access token và quyền nghiệp vụ.

### 5.4. Clock skew

Các provider làm mới token thường sử dụng `expiresAt` và một khoảng lệch thời gian cho phép (clock skew). Token sắp hết hạn có thể được coi là cần cấp lại trước thời điểm `exp` thực tế để tránh token hết hạn khi API xử lý.

Không mặc định chỉ refresh đúng giây hết hạn. Khoảng skew và điều kiện phụ thuộc implementation/configuration.

### 5.5. Nếu API trả 401 dù token chưa hết hạn?

Manager không mặc định nhìn thấy mọi HTTP response của API. Một API 401 có thể do audience sai hoặc token đã bị revoke, không nhất thiết do token hết hạn.

Cần tích hợp HTTP client và authorization failure handling phù hợp, phân biệt lỗi có thể reauthorize với lỗi cấu hình/policy. **Không retry vô hạn cùng token vừa bị API từ chối.**

## 6. Tình huống C: cấp lại token

“Cấp lại” có thể có nhiều cơ chế. Không có một OAuth grant tên chung là “reauthorize”.

| Cơ chế | Điều kiện | Có cần browser? |
|---|---|---|
| `refresh_token` | Có refresh token được AS chấp nhận | Thường không |
| Xin token mới bằng `client_credentials` | Client được phép dùng grant | Không |
| Authorization Code flow mới | Cần authorization mới, client hỗ trợ tương tác | Có redirect/callback |
| Token exchange/delegation | AS hỗ trợ và client được phép exchange | Tùy cơ chế |

### 6.1. Refresh Token grant

Nếu access token A1 hết hạn/sắp hết hạn và có refresh token R1:

~~~text
Authorized client:
  accessToken = A1 (đã hết hạn)
  refreshToken = R1 (còn hợp lệ)
~~~

provider `refreshToken()` có thể gửi một token request:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=R1
~~~

Đây là request minh họa, chưa thể hiện client authentication thực tế. Confidential client có thể phải dùng `client_secret_basic`, `private_key_jwt`, mTLS hoặc phương thức khác theo đăng ký. Không in token thật trong log.

AS có thể trả:

~~~json
{
  "access_token": "ACCESS_TOKEN_A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "REFRESH_TOKEN_R2"
}
~~~

Token mới là giá trị giả. AS có thể phát refresh token mới khi rotation hoặc giữ refresh token cũ theo chính sách.

Sau thành công, manager/success handler lưu authorized client cập nhật để request sau dùng A2.

### 6.2. Refresh không phải đăng nhập lại OIDC

Refresh token grant **không tự chứng minh user vừa xác thực lại**. Access token A2 vừa phát hành không có nghĩa Alice vừa nhập mật khẩu hoặc thực hiện MFA.

Khi nghiệp vụ yêu cầu một authentication event mới, có thể cần Authorization Request OIDC mới với `max_age`, `prompt=login` hoặc `acr_values`, sau đó kiểm tra `auth_time`/`acr` trong ID token theo chính sách.

**Đừng dùng thời gian cấp access token để suy ra độ mới của xác thực người dùng.**

### 6.3. Refresh không tự tăng quyền

Giả sử token trước chỉ có scope `orders.read`. Một lần refresh không tự cho phép Portal nâng lên `orders.approve`.

Muốn quyền mới có thể cần client được cấp scope, consent/authorization mới hoặc token exchange theo cơ chế AS hỗ trợ. Không được tự sửa claim scope hoặc authority để tăng quyền.

### 6.4. Client Credentials cấp access token mới

Với background service:

~~~text
Access token S1 đã hết hạn
Refresh token: thường không được cấp
Grant: client_credentials

Manager -> clientCredentials provider
AS -> access token S2
Manager -> lưu S2
~~~

Đây là một token request `client_credentials` mới, **không phải refresh token grant**. Không liên quan đến người dùng OIDC.

### 6.5. Không có refresh token và không thể cấp lại tự động

Một client Authorization Code có thể không được cấp refresh token. Khi access token hết hạn:

- Không thể sử dụng provider refresh nếu thiếu refresh token.
- Có thể phải bắt đầu Authorization Code flow mới.
- OP có thể dùng phiên SSO còn hiệu lực để hoàn tất nhanh mà không hỏi mật khẩu.
- Nếu đang ở background job, không thể tự mở browser thay user.

Nếu chưa có cách reauthorize hợp lệ, manager không thể “tự sinh access token”. Không dùng ID token làm bearer token API để thay thế.

## 7. Kết quả trả về từ `authorize()`

### 7.1. Authorized client mới

Provider đã cấp token lần đầu hoặc reauthorize và tạo object mới/cập nhật. Manager có thể sử dụng success handler để lưu trạng thái.

### 7.2. Authorized client đã lưu

Provider không thực hiện grant mới và manager trả object cũ. Đây là hành vi tái sử dụng token, không phải lỗi.

### 7.3. Không có kết quả

Manager có thể trả `null` khi không có authorized client và provider không xử lý được ngữ cảnh. Ứng dụng cần xác định cần authorization tương tác, grant khác hoặc xử lý lỗi.

Không tiếp tục gọi API bằng token trống hoặc ID token thay thế.

### 7.4. Exception khi token endpoint thất bại

Các lỗi điển hình:

| Lỗi | Nguyên nhân có thể | Xử lý |
|---|---|---|
| `invalid_grant` | Refresh token đã hết hạn, bị revoke, reused hoặc không hợp lệ | Dừng retry cũ, cleanup/authorization mới |
| `invalid_client` | Secret/client authentication sai | Kiểm tra client registration |
| Timeout | Mạng hoặc AS không trả response | Retry có kiểm soát, đánh giá tính idempotent |
| Không có provider | Grant không được hỗ trợ bởi chain | Sửa cấu hình |
| API 401 | RS không chấp nhận token | Xem audience, issuer, revoke, expiry |
| API 403 | Thiếu scope/authority hoặc quyền | Không coi là yêu cầu refresh mặc định |

Lỗi token endpoint khác HTTP error từ Resource Server. Cần chẩn đoán ở đúng tầng.

## 8. Cấu hình Spring Boot: OIDC web và service client

### 8.1. Maven dependency

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

### 8.2. `application.yml`

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
          reporting-service:
            provider: company-auth
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
          company-auth:
            token-uri: https://id.example.com/oauth2/token
~~~

Ở đây:

- `corporate` là registration phục vụ OIDC Login người dùng.
- `reporting-service` là client dùng `client_credentials` cho tác vụ nền.
- Scope `orders.read` và `reports.read` chỉ là ví dụ, phải được AS và API hỗ trợ.
- Client secret được nạp từ môi trường/secret manager, không commit vào mã nguồn.

## 9. Manager cho Servlet request

### 9.1. `DefaultOAuth2AuthorizedClientManager`

Class:

~~~java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager
~~~

Nó dùng `ClientRegistrationRepository` và `OAuth2AuthorizedClientRepository`. Phù hợp với request Servlet vì repository có thể cần `HttpServletRequest` và `HttpServletResponse`.

Ví dụ cấu hình:

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
public class ServletAuthorizedClientConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Provider chain bao gồm khả năng phù hợp với các grant, nhưng **không biến authorization code thành một flow không cần browser**.

### 9.2. Security Filter Chain

~~~java
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
~~~

`oauth2Login()` cung cấp cơ chế browser login/callback; `oauth2Client()` hỗ trợ client authorization trong những request cần dùng token.

Nếu ứng dụng có bean repository/manager tự định nghĩa, phải bảo đảm nơi **lưu token ở login** và nơi **đọc token khi gọi API** nhất quán.

### 9.3. Gọi manager trong Servlet controller

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class TokenStatusController {

    private final OAuth2AuthorizedClientManager manager;

    TokenStatusController(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @GetMapping("/token-status")
    String status(
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        OAuth2AuthorizeRequest authorizeRequest =
                OAuth2AuthorizeRequest.withClientRegistrationId("corporate")
                        .principal(authentication)
                        .attribute(HttpServletRequest.class.getName(), request)
                        .attribute(HttpServletResponse.class.getName(), response)
                        .build();

        OAuth2AuthorizedClient client =
                manager.authorize(authorizeRequest);

        if (client == null || client.getAccessToken() == null) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED,
                    "No authorized client available");
        }

        return "registrationId="
                + client.getClientRegistration().getRegistrationId();
    }
}
~~~

Controller minh họa cách gắn Authentication và Servlet request/response vào authorize request. Nó chỉ trả registration ID, **không trả chuỗi access token**.

Ví dụ giả định user đã hoàn thành OIDC Login. Nếu chưa có authorized client của `corporate`, cần thực hiện flow tương tác, ví dụ bắt đầu tại:

~~~text
/oauth2/authorization/corporate
~~~

Không coi một lời gọi manager tùy ý là thay thế toàn bộ redirect/callback.

## 10. Manager cho background job

### 10.1. `AuthorizedClientServiceOAuth2AuthorizedClientManager`

Background job hoặc scheduled task thường không có Servlet request/session.

Lúc này Spring Security có:

~~~java
org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager
~~~

Nó sử dụng `ClientRegistrationRepository` và `OAuth2AuthorizedClientService`, phù hợp để lưu/đọc token theo service principal.

### 10.2. Cấu hình

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class BackgroundTokenConfig {

    @Bean("backgroundClientManager")
    OAuth2AuthorizedClientManager backgroundClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations, service);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

### 10.3. Dùng manager để lấy token

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class ReportingTokenService {

    private final OAuth2AuthorizedClientManager manager;

    ReportingTokenService(
            @Qualifier("backgroundClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String accessToken() {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("reporting-service")
                        .principal("reporting-job")
                        .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null || client.getAccessToken() == null) {
            throw new IllegalStateException(
                    "Could not authorize reporting-service");
        }

        return client.getAccessToken().getTokenValue();
    }
}
~~~

`reporting-job` là **tên principal kỹ thuật** để quản lý token của service, không phải End-User đăng nhập OIDC.

Trong ứng dụng thật, đừng log access token hoặc trả token qua endpoint frontend; nên dùng HTTP client đã được cấu hình đúng domain và scope.

## 11. Xác định manager phù hợp với môi trường

| Tiêu chí | `DefaultOAuth2AuthorizedClientManager` | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
|---|---|---|
| Ngữ cảnh chính | Servlet request | Background/service ngoài Servlet request |
| Nơi lưu | `OAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClientService` |
| Có thể cần HTTP request/response | Có | Không |
| Principal | Authentication trong ngữ cảnh request | Principal name được cung cấp |
| Thường dùng với browser OIDC Login | Có | Không tự xử lý browser login |
| Thường dùng với client credentials job | Có thể dùng trong request | Phù hợp hơn |
| Refresh token | Tùy provider/authorized client | Tùy provider/authorized client |
| Tự mở browser trong background | Không | Không |

Với **Reactive WebFlux**, Spring Security sử dụng những abstraction reactive tương ứng như `ReactiveOAuth2AuthorizedClientManager`; không nhầm Servlet manager với reactive service.

## 12. Token expiration và clock skew

### 12.1. Các thời điểm quan trọng

Access token có thể có:

~~~java
client.getAccessToken().getIssuedAt();
client.getAccessToken().getExpiresAt();
~~~

Một token có `expiresAt=10:30` nhưng API nhận request ở 10:30:01 có thể bị từ chối. Vì vậy provider có thể tính một khoảng lệch đồng hồ (clock skew) và coi token **sắp hết hạn** là cần refresh/cấp lại.

Không hard-code quy tắc “chỉ refresh khi `now >= exp`” mà bỏ qua policy của provider.

### 12.2. Token chưa hết hạn vẫn có thể không dùng được

Ngoài thời gian, API còn kiểm tra:

- Issuer đáng tin cậy.
- Audience/resource phù hợp.
- Token type/profile được chấp nhận.
- Scope/authority.
- Quyền trên tài nguyên cụ thể.
- Trạng thái token nếu có cơ chế revocation/introspection.

`authorize()` trả authorized client không có nghĩa API sẽ chấp nhận mọi request.

### 12.3. HttpSession và token có vòng đời khác nhau

Ví dụ:

~~~text
Portal HttpSession idle timeout: 30 phút
Access token TTL:              10 phút
Refresh token lifetime:        theo AS
OP SSO session lifetime:       theo OP
~~~

Session còn sống không đảm bảo token còn hạn. Token còn hạn không đảm bảo user vẫn có session Portal. OP SSO có thể vẫn tồn tại dù Portal đã logout.

## 13. Refresh token rotation và concurrent requests

### 13.1. Hai request cùng refresh

Giả sử authorized client hiện có A1/R1, và R1 sẽ được rotate khi dùng.

~~~text
Request A load A1/R1
Request B load A1/R1
Request A refresh R1 -> nhận A2/R2
Request B refresh R1 -> invalid_grant hoặc phát hiện reuse
~~~

Tùy AS, việc dùng lại R1 có thể chỉ bị từ chối hoặc kích hoạt chính sách thu hồi rộng hơn.

Không giả định `OAuth2AuthorizedClientManager` và repository luôn đảm bảo atomic refresh giữa nhiều thread/nhiều instance.

### 13.2. Cần quyết định đồng bộ

Khi tải cao, có thể cần:

- Key đồng bộ theo registration và principal/service.
- Single-flight hoặc lock phù hợp khi refresh.
- Ghi cập nhật token có điều kiện để tránh overwrite bản mới bằng bản cũ.
- Kho authorized client chia sẻ đúng giữa các instance.
- Failure handling phù hợp khi token bị rotate/thu hồi.
- Theo dõi lỗi, không log raw refresh token.

Đây là thiết kế token lifecycle, không phải việc chỉ bật một flag.

### 13.3. Cùng principal ở nhiều scheduled jobs

Hai job dùng `principal("reporting-job")` và cùng registration có thể chia sẻ token trong service store. Đây có thể là lựa chọn có chủ đích.

Nhưng nếu mỗi job cần audience/scope khác nhau, không nên tự dùng cùng registration/token cho mọi API. Tạo các registration/policy riêng khi cần.

## 14. Authorization success/failure handlers

### 14.1. Save sau khi cấp token

Khi provider trả authorized client mới/cập nhật, manager có thể gọi success handler để lưu kết quả vào repository/service.

Nếu tùy biến manager, phải đảm bảo nơi lưu **nhất quán** với nơi controller/HTTP client đọc. Nếu không, token mới có thể chỉ tồn tại trong request hiện tại còn request sau lại thấy token cũ.

### 14.2. `invalid_grant` khi refresh

Refresh token có thể hết hạn, bị thu hồi hoặc đã được rotate. Khi AS trả `invalid_grant`, ứng dụng không nên tiếp tục thử mãi cùng refresh token cũ.

Một số manager/handler thông dụng của Spring Security có cơ chế xóa authorized client khi lỗi OAuth phù hợp, chẳng hạn `invalid_grant`; hành vi thực tế phụ thuộc cách manager và handlers được cấu hình.

Về mặt thiết kế, cần xử lý:

1. Dừng dùng refresh token bị từ chối.
2. Xóa/cập nhật local authorized client theo đúng principal/registration.
3. Nếu cần, bắt đầu authorization mới cho user hoặc trả lỗi cho service.
4. Không để vòng lặp refresh vô hạn.

Xóa local authorized client **không tự thu hồi token ở AS**.

### 14.3. Lỗi mạng không giống lỗi bị từ chối grant

Nếu token endpoint timeout, không thể luôn kết luận credential không hợp lệ. Cần xử lý retry/backoff theo tính chất grant, tránh lặp yêu cầu vô hạn hoặc tạo trạng thái không nhất quán.

Nếu client secret sai, retry cùng secret không giải quyết được vấn đề. Cần sửa cấu hình client authentication.

### 14.4. API 401/403 không tự động là token refresh

Một API có thể trả:

| HTTP | Tình huống phổ biến | Ý nghĩa xử lý |
|---|---|---|
| 401 | Token không hợp lệ, sai issuer/audience, hết hạn, bị revoke | Điều tra authentication/token validity |
| 403 | Token hợp lệ nhưng thiếu quyền | Điều tra scope/authority/ownership |

Không mặc định “mọi 401/403 thì refresh ngay”. 403 do thiếu quyền không được sửa bằng cách xin một access token cùng scope.

## 15. OAuth2-aware HTTP client và lỗi API

Spring Security có tích hợp OAuth2 với các HTTP client như `RestClient` và `WebClient` theo phiên bản hỗ trợ. Thông thường, một integration có thể:

- Tra cứu authorized client theo registration và principal.
- Dùng manager để authorize/reauthorize khi cần.
- Gắn access token vào header Bearer.
- Kết hợp failure handler để xử lý một số lỗi ủy quyền.

Không nhất thiết phải gọi `authorize()` thủ công trong từng controller. Với hệ thống lớn, nên tập trung token management tại lớp HTTP client/service.

Khi HTTP client nhận 401, cần xác định token có thể được cấp lại hợp lệ không. Nếu nguyên nhân là sai audience hoặc API đang từ chối issuer, xin một token mới cùng cấu hình sai sẽ không sửa được.

Đặc biệt tránh retry request nghiệp vụ có side effect, như `POST /payments`, khi chưa có cơ chế idempotency tương ứng.

## 16. Reauthorize khác reauthentication và step-up

### 16.1. Access token mới không chứng minh user vừa xác thực

Refresh token grant có thể cấp A2 sau A1, nhưng không tự khiến OP xác thực lại Alice. Cần phân biệt:

~~~text
Cấp access token mới
    !=
Xác thực lại End-User
    !=
Mức xác thực mạnh hơn
~~~

### 16.2. Khi nghiệp vụ yêu cầu đăng nhập mới hơn

OIDC có những tham số:

- `prompt=login`: đề nghị OP xác thực lại.
- `max_age`: giới hạn độ cũ của lần xác thực, cần đánh giá `auth_time` trong ID token theo quy tắc OIDC.
- `acr_values`: nêu lớp xác thực mong muốn theo OP.

Các tham số này thuộc **Authentication Request**. Chúng không được tự thêm vào refresh token grant để biến một lần refresh thành sự kiện MFA.

### 16.3. Step-up authentication

Nếu nhân viên được xem Orders API nhưng phải xác thực mạnh khi phê duyệt khoản tiền lớn:

1. Backend kiểm tra Authentication và policy assurance hiện tại.
2. Nếu chưa đạt, bắt đầu OIDC Authentication Request mới.
3. OP xác thực theo chính sách và trả kết quả.
4. RP xác minh ID token, `acr` và `auth_time` nếu policy cần.
5. Backend kiểm tra đúng user và quyền trên giao dịch.
6. Chỉ sau đó mới thực hiện phê duyệt.

Đừng dùng thời gian phát hành access token mới như chứng cứ user vừa thực hiện MFA.

## 17. Token thuộc principal nào?

### 17.1. Không lưu token theo registration ID toàn cục

Một registration `corporate` có thể được Alice và Bob cùng dùng. Nếu token bị lưu vào biến static chỉ theo registration:

~~~java
public static String lastAccessToken;
~~~

Bob có thể vô tình dùng token Alice.

Sử dụng repository/service ràng buộc đúng principal/session và registration. Khi đổi tài khoản trong cùng HttpSession, cần cleanup token của user trước nếu mô hình lưu theo session.

### 17.2. Nhiều issuer và tenant

OIDC `sub` chỉ có ý nghĩa trong phạm vi issuer. Nếu hai OP đều phát hành `sub=12345`, không mặc định là cùng người.

Khi xây identity key phục vụ token store, thường cần liên kết với cặp **`iss` + `sub`** hoặc một internal user ID đã được ánh xạ và quản lý đúng.

### 17.3. Registration ID không phải audience API

`registrationId=corporate` là khóa nội bộ Spring Security, không bảo đảm token nhận được có `aud=orders-api`. API phải kiểm tra audience và quyền phù hợp.

Nếu dùng access token cho sai Resource Server, manager không tự sửa audience. Có thể cần scope/resource indicator hoặc cơ chế token exchange được AS hỗ trợ.

## 18. Tái sử dụng sau logout và thu hồi token

### 18.1. Logout Portal

Logout cục bộ thường xóa SecurityContext và có thể hủy HttpSession. Nếu authorized client nằm trong session, token local có thể mất cùng session.

Nhưng authorized client được lưu trong `OAuth2AuthorizedClientService` có thể tồn tại ngoài session nếu không có cleanup riêng.

### 18.2. Token revocation

Xóa token khỏi repository **khác** thu hồi token ở AS. Một access token đã cấp vẫn có thể còn được Resource Server chấp nhận cho tới khi hết hạn hoặc bị revoke theo cơ chế AS/RS.

### 18.3. Phiên SSO của OP

Portal logout không nhất thiết hủy phiên SSO ở OP. Khi user mở lại Portal, OIDC Authorization Code flow mới có thể diễn ra nhanh nhờ SSO, nhưng đó vẫn là **authorization flow mới**, không phải dùng lại code cũ.

## 19. Môi trường nhiều instance

Giả sử hai instance Portal cùng dùng authorized client service hoặc session store:

~~~text
Browser / Jobs
      |
Load balancer
  |------- Portal A
  |------- Portal B
~~~

Nếu A và B có kho token memory riêng, request đến B có thể không thấy authorized client mà A đã lưu. Điều này dễ khiến ứng dụng xin token lặp lại hoặc báo chưa được authorize.

Cần quyết định:

- Token lưu theo HttpSession hay service principal?
- Kho lưu có được chia sẻ giữa instance không?
- Refresh token rotation được phối hợp ra sao?
- Khi deploy lại có mất authorized client không?
- Khi đổi tài khoản/tenant có dọn token đúng không?
- Khi token bị thu hồi có cách thông báo hoặc cleanup không?

Đừng chuyển token sang một static global cache chỉ để “nhiều node dễ truy cập”.

## 20. Quy trình tư duy khi đọc một lời gọi `authorize()`

Khi gặp:

~~~java
OAuth2AuthorizedClient client = manager.authorize(request);
~~~

hãy trả lời theo thứ tự:

1. **Registration ID là gì?**
2. **Grant type là gì?** `authorization_code` hay `client_credentials`?
3. **Principal là ai?** User OIDC hay service principal?
4. **Manager thuộc Servlet hay service/background?**
5. **Repository/service nào đang lưu?**
6. **Có authorized client đã lưu không?**
7. **Access token có hết hạn/sắp hết hạn theo provider không?**
8. **Có refresh token còn hợp lệ không?**
9. **Provider chain có hỗ trợ grant tương ứng không?**
10. **Nếu provider không cấp token mới, manager sẽ trả gì?**
11. **Nếu token endpoint từ chối, failure handler xử lý thế nào?**
12. **API đích có chấp nhận issuer, audience, scope và quyền không?**

Chuỗi câu hỏi này giúp phân biệt **authorize lần đầu**, **tái sử dụng** và **cấp lại token** mà không suy đoán theo tên phương thức.

## 21. Tình huống minh họa

### Tình huống A — Đăng nhập lần đầu

Alice chưa có session và authorized client tại Portal. Browser bắt đầu OIDC Authorization Code flow. Sau callback hợp lệ, Spring Security tạo Authentication và lưu authorized client. Các request sau có thể dùng token đã cấp.

### Tình huống B — Mở trang đơn hàng liên tiếp

Alice đã có A1 chưa hết hạn. Hai lần truy cập `/orders` có thể dùng cùng A1. Manager không nhất thiết gọi token endpoint.

### Tình huống C — Access token hết hạn, có refresh token

A1 hết hạn, R1 còn hiệu lực. Provider `refreshToken()` có thể dùng R1 để xin A2, lưu authorized client cập nhật. Không cần browser redirect nếu refresh thành công.

### Tình huống D — Không có refresh token

A1 hết hạn, registration dùng `authorization_code` nhưng AS không cấp refresh token. Một luồng Authorization Code mới có thể cần được bắt đầu. OP có thể tận dụng SSO, nhưng manager không tự làm một background job thành browser.

### Tình huống E — Service token hết hạn

`reporting-service` dùng `client_credentials`; S1 hết hạn. Manager phù hợp xin S2 bằng grant mới, không có End-User hay ID token.

### Tình huống F — Refresh token bị từ chối

R1 bị rotate/thu hồi và token endpoint trả `invalid_grant`. Ứng dụng không retry vô hạn R1, cần xử lý cleanup/authorization mới.

### Tình huống G — API trả 403

Token còn hiệu lực nhưng thiếu quyền `orders.approve`. Không tự refresh với hy vọng quyền xuất hiện; cần quyền được AS/RS/ứng dụng cấp theo policy phù hợp.

### Tình huống H — Hai request cùng refresh

Hai request cùng thấy A1/R1 hết hạn. Một request nhận A2/R2, request khác gặp reuse. Cần xem concurrency và refresh token rotation, không đổ lỗi đơn giản cho Authorization Code flow.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Mỗi lần gọi `authorize()` có nhất thiết tạo access token mới?

**Trả lời:** Không. Manager có thể trả authorized client đang lưu khi provider không cần/có thể reauthorize.

**Câu 2.** Có thể dùng `refreshToken()` để xin token lần đầu khi chưa có refresh token?

**Trả lời:** Không. Refresh token grant cần refresh token đã được cấp từ một authorization trước đó.

**Câu 3.** `authorization_code` có thể hoàn thành hoàn toàn trong background job không có browser?

**Trả lời:** Không theo flow web tương tác thông thường. Nó cần Authorization Request, redirect/callback và cơ chế giao thức phù hợp.

**Câu 4.** `client_credentials` xin token mới sau expiry có phải refresh token grant?

**Trả lời:** Không. Client thực hiện grant `client_credentials` mới theo danh tính của chính client.

**Câu 5.** Access token vừa được refresh có chứng minh user vừa MFA?

**Trả lời:** Không. Độ mới/mức xác thực phải được đánh giá qua OIDC Authentication Request và các claim phù hợp.

**Câu 6.** API trả 401 nhưng access token chưa hết hạn, manager có tự sửa?

**Trả lời:** Không mặc định. Cần phân tích nguyên nhân và cấu hình HTTP client/failure handling nếu muốn reauthorize phù hợp.

**Câu 7.** API trả 403 vì thiếu scope, refresh có tự tăng scope không?

**Trả lời:** Không. Cần authorization và quyền được cấp theo AS/RS, không tự nâng quyền qua refresh.

**Câu 8.** Nên dùng manager nào cho scheduled job?

**Trả lời:** `AuthorizedClientServiceOAuth2AuthorizedClientManager` thường phù hợp hơn vì không phụ thuộc HTTP Servlet request.

**Câu 9.** Vì sao phải ràng buộc authorized client với principal?

**Trả lời:** Để tránh dùng token Alice cho Bob hoặc trộn token giữa issuer/tenant.

**Câu 10.** `invalid_grant` khi refresh nên được xử lý thế nào?

**Trả lời:** Không retry vô hạn cùng refresh token cũ; xem xét cleanup và flow cấp quyền mới theo policy.

**Câu 11.** Manager trả token có tự chứng minh token đúng audience của Orders API không?

**Trả lời:** Không. API cần xác minh token đúng audience, scope, issuer và quyền.

**Câu 12.** Xóa authorized client ở local store có thu hồi token tại AS không?

**Trả lời:** Không. Local cleanup và token revocation là hai cơ chế riêng.

## Ghi nhớ

- **`OAuth2AuthorizedClientManager.authorize(...)` là API điều phối**, không phải lệnh “luôn xin access token mới”.
- **Authorize lần đầu** phụ thuộc grant: `authorization_code` cần flow tương tác; `client_credentials` có thể thực hiện ở backend.
- **Tái sử dụng token** thường không gọi AS; token được lấy từ repository/service đã cấu hình.
- **Cấp lại token** có thể bằng refresh token, một request client credentials mới hoặc Authorization Code flow mới. Các cơ chế này không thay thế nhau.
- **Access token mới không đồng nghĩa user được xác thực lại**. Với step-up/freshness, cần OIDC flow và kiểm tra claim thích hợp.
- **Provider chain, manager và repository/service phải nhất quán** về grant, registration, principal và ngữ cảnh thực thi.
- **Refresh rotation, concurrent requests, API 401/403 và đổi tài khoản** cần chính sách riêng; không tự retry vô hạn hoặc dùng token của principal khác.
- **Resource Server phải kiểm tra token và quyền**, dù manager phía client đã tìm được authorized client.
