# 1.6. Các thành phần chính và vòng đời một authorized client

Trong **Spring Security OAuth 2.0 OIDC Client**, ứng dụng Spring Boot đóng vai trò **OAuth 2.0 Client**: thay mặt người dùng hoặc chính ứng dụng xin access token từ Authorization Server và sử dụng token đó để truy cập tài nguyên được bảo vệ. Khi có yêu cầu đăng nhập bằng OpenID Connect (OIDC), ứng dụng còn dùng thông tin định danh từ Identity Provider để xác thực người dùng.

Khái niệm trung tâm của bài là **`OAuth2AuthorizedClient`**. Đây là đối tượng biểu diễn **một client registration đã được cấp quyền**, gắn với một principal cụ thể và các token đã nhận. Hiểu đối tượng này cùng các thành phần tạo, lưu, nạp và gia hạn nó sẽ giúp bạn đọc đúng luồng xử lý của Spring Security.

## 1. Bức tranh tổng thể: ai làm gì?

Một hệ thống thường có bốn vai trò:

| Vai trò | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| **Resource Owner** | Chủ thể có quyền đối với dữ liệu, thường là người dùng | Người đăng nhập vào ứng dụng |
| **Client** | Ứng dụng yêu cầu quyền truy cập thay mặt người dùng hoặc nhân danh chính nó | Ứng dụng Spring Boot |
| **Authorization Server (AS)** | Xác thực, lấy sự đồng ý khi cần và cấp token | Keycloak, Okta, Spring Authorization Server |
| **Resource Server (RS)** | Bảo vệ API và kiểm tra access token | API hồ sơ, hóa đơn, tài liệu |

Khi Authorization Server hỗ trợ OIDC, nó còn đóng vai trò **OpenID Provider (OP)** và phát hành **ID token** để client xác thực danh tính người dùng.

```
flowchart LR
    U["Người dùng / trình duyệt"] --> C["Spring Boot<br/>OAuth2 / OIDC Client"]
    C <-->|"Authorization Code, token"| AS["Authorization Server<br/>/ OpenID Provider"]
    C -->|"Access token"| RS["Resource Server / API"]
    RS -.->|"Kiểm tra token theo cấu hình"| AS
```

**Phân biệt ba thứ dễ nhầm:**

- **`ClientRegistration`** là *cấu hình tĩnh* của một client đã đăng ký với Authorization Server: client ID, loại grant, scope, endpoint, redirect URI, v.v.
- **`OAuth2AuthorizedClient`** là *trạng thái được cấp quyền tại thời điểm chạy*: một registration cộng với principal và access token (có thể kèm refresh token).
- **`Authentication` / `OidcUser`** mô tả người dùng đã đăng nhập trong Spring Security. Đây là thông tin xác thực; nó không thay thế đối tượng lưu token truy cập API.

Một ứng dụng có thể có **nhiều client registration** (ví dụ `web-oidc` và `billing-service`), đồng thời có **nhiều authorized client** tương ứng các người dùng hoặc principal khác nhau.

## 2. Các thành phần chính trong Spring Security

### 2.1. `ClientRegistration` và `ClientRegistrationRepository`

**`ClientRegistration`** mô tả *cách* ứng dụng nói chuyện với Authorization Server. Những thuộc tính thường thấy:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `registrationId` | Tên định danh nội bộ, ví dụ `web-oidc`; dùng để tìm cấu hình |
| `clientId`, `clientSecret` | Danh tính và thông tin xác thực của client (nếu là confidential client) |
| `authorizationGrantType` | Cách nhận token, ví dụ `authorization_code` hoặc `client_credentials` |
| `redirectUri` | URL callback khi dùng Authorization Code |
| `scopes` | Quyền mà client yêu cầu, ví dụ `openid`, `profile`, `email` |
| `authorizationUri`, `tokenUri` | Endpoint điều hướng xin quyền và đổi mã lấy token |
| `issuerUri`, `jwkSetUri` | Thông tin issuer và khóa dùng xác thực token/ID token theo cấu hình |

**`ClientRegistrationRepository`** cho phép tra cứu `ClientRegistration` theo `registrationId`. Với Spring Boot, cấu hình `spring.security.oauth2.client.registration.*` thường được ánh xạ thành registration; một triển khai phổ biến là `InMemoryClientRegistrationRepository`.

Repository này lưu **cấu hình client**, không phải access token của từng người dùng.

### 2.2. `OAuth2AuthorizedClient`: dữ liệu sau khi cấp quyền

Một `OAuth2AuthorizedClient` về cơ bản nắm giữ:

```
OAuth2AuthorizedClient
├── clientRegistration : ClientRegistration
├── principalName       : String
├── accessToken         : OAuth2AccessToken
└── refreshToken        : OAuth2RefreshToken?  (có thể null)
```

- **`principalName`** xác định chủ thể mà token được cấp trong ngữ cảnh của ứng dụng. Với đăng nhập, đó thường là người dùng; với `client_credentials`, ứng dụng có thể dùng một tên principal kỹ thuật cố định.
- **Access token** được gửi đến Resource Server; nó có loại token (thường là Bearer), giá trị, scope, thời điểm cấp và hết hạn.
- **Refresh token** chỉ tồn tại nếu Authorization Server có cấp. Không được mặc định rằng mọi grant đều có refresh token.
- **ID token OIDC không phải thuộc tính trực tiếp của `OAuth2AuthorizedClient`**. Thông tin ID token thường nằm trong `OidcUser` hoặc ngữ cảnh xác thực OIDC.

Hãy hình dung registration là *thẻ thông tin đăng ký dịch vụ*; authorized client là *thẻ đó sau khi đã nhận quyền truy cập cho một principal cụ thể*.

### 2.3. Nơi lưu và nạp authorized client

Spring Security phân biệt hai abstraction:

| Thành phần | API điển hình | Phù hợp với |
| --- | --- | --- |
| **`OAuth2AuthorizedClientService`** | `loadAuthorizedClient(registrationId, principalName)`; `saveAuthorizedClient(...)`; `removeAuthorizedClient(...)` | Truy cập dữ liệu authorized client qua principal, không phụ thuộc HTTP request |
| **`OAuth2AuthorizedClientRepository`** | `loadAuthorizedClient(..., Authentication, HttpServletRequest)`; `saveAuthorizedClient(..., Authentication, HttpServletRequest, HttpServletResponse)` | Luồng Servlet/Web có request, response và session |

Ví dụ triển khai:

- `InMemoryOAuth2AuthorizedClientService`: lưu trong bộ nhớ; phù hợp minh họa hoặc trường hợp đơn giản.
- `JdbcOAuth2AuthorizedClientService`: có thể lưu vào cơ sở dữ liệu qua JDBC.
- `HttpSessionOAuth2AuthorizedClientRepository`: lưu theo HTTP session.
- `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`: dùng service đối với principal đã xác thực và có xử lý lưu phù hợp cho principal chưa xác thực.

**Điểm cốt lõi:** `ClientRegistrationRepository` trả lời câu hỏi *client được cấu hình ra sao?*; `OAuth2AuthorizedClientService/Repository` trả lời *principal này đã có token nào cho registration này?*

Tùy cách cấu hình lưu trữ, một authorized client có thể biến mất sau khi hết session, khởi động lại ứng dụng, hoặc được chia sẻ qua các instance khi dùng kho lưu trữ thích hợp. Không nên mặc định token tự được đồng bộ giữa các máy chủ.

### 2.4. `OAuth2AuthorizedClientManager` và `OAuth2AuthorizedClientProvider`

**`OAuth2AuthorizedClientManager`** là đầu mối điều phối khi ứng dụng cần một authorized client có thể sử dụng: tìm trạng thái hiện có, ủy quyền lần đầu, hoặc cấp lại quyền khi cần.

Một manager sử dụng **`OAuth2AuthorizedClientProvider`** để xử lý từng grant và trạng thái token. Các provider thường được ghép bằng `OAuth2AuthorizedClientProviderBuilder`:

| Provider | Khi nào cần |
| --- | --- |
| `authorizationCode()` | Luồng Authorization Code có tương tác người dùng qua trình duyệt |
| `refreshToken()` | Có refresh token hợp lệ và cần access token mới |
| `clientCredentials()` | Client tự xin access token để gọi API, không có người dùng trực tiếp |

Hai implementation manager thường gặp trong **Servlet application**:

- **`DefaultOAuth2AuthorizedClientManager`**: dùng cùng `OAuth2AuthorizedClientRepository`, thích hợp khi có `HttpServletRequest` / `HttpServletResponse`.
- **`AuthorizedClientServiceOAuth2AuthorizedClientManager`**: dùng cùng `OAuth2AuthorizedClientService`, thích hợp cho tác vụ nền hoặc service không có HTTP request.

Khi gọi `manager.authorize(OAuth2AuthorizeRequest)`, kết quả có thể là authorized client hiện có, authorized client đã được làm mới, hoặc `null` nếu provider không hỗ trợ/không thể hoàn tất authorization trong ngữ cảnh đó. Lỗi cấp quyền cũng có thể xuất hiện dưới dạng `OAuth2AuthorizationException`. Vì thế ứng dụng không nên coi mọi lời gọi `authorize()` đều chắc chắn trả về token mới.

### 2.5. Các thành phần hỗ trợ luồng trình duyệt và OIDC

Trong cấu hình Servlet với `oauth2Login()`, những thành phần sau tham gia vào quá trình đăng nhập:

- **`OAuth2AuthorizationRequestRedirectFilter`**: khởi động luồng chuyển hướng sang Authorization Server, mặc định thường bắt đầu tại `/oauth2/authorization/{registrationId}`.
- **`OAuth2AuthorizationRequestResolver`**: tạo authorization request với client ID, redirect URI, scope, `state` và tham số bổ sung phù hợp; có thể tùy biến.
- **`OAuth2LoginAuthenticationFilter`**: tiếp nhận callback chứa authorization code, mặc định tại `/login/oauth2/code/{registrationId}`, rồi xử lý đăng nhập.
- **`OidcUserService`** và các thành phần xác thực OIDC: thiết lập thông tin người dùng dựa trên ID token và UserInfo khi áp dụng.
- **`SecurityContext`**: giữ `Authentication` của người dùng đã đăng nhập; được lưu qua cơ chế security context/session theo cấu hình.

`oauth2Login()` giải quyết **đăng nhập người dùng**; `oauth2Client()` và cơ chế authorized client giải quyết **quản lý quyền/token để gọi tài nguyên**. Một ứng dụng web có thể dùng cả hai.

## 3. Vòng đời của authorized client với Authorization Code + OIDC

Giả sử người dùng mở trang cần đăng nhập trên ứng dụng Spring Boot, dùng registration `web-oidc`, và sau đó ứng dụng gọi một API khác.

```
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant C as Spring Boot Client
    participant AS as Authorization Server / OP
    participant API as Resource Server

    U->>B: Mở trang cần xác thực
    B->>C: GET /private
    C-->>B: Redirect sang authorization endpoint
    B->>AS: Yêu cầu authorize (scope, state, ...)
    AS->>U: Xác thực / xin consent nếu cần
    AS-->>B: Redirect với code và state
    B->>C: GET /login/oauth2/code/web-oidc?code=...&state=...
    C->>C: Kiểm tra state / request đã lưu
    C->>AS: Đổi authorization code lấy token
    AS-->>C: Access token, ID token, có thể refresh token
    C->>C: Kiểm tra OIDC; tạo Authentication
    C->>C: Lưu OAuth2AuthorizedClient
    C-->>B: Thiết lập phiên đăng nhập / trả trang
    C->>API: Gọi API với Bearer access token
    API-->>C: Dữ liệu được phép truy cập
```

### Giai đoạn A — Registration đã sẵn sàng, chưa có quyền

Sau khi cấu hình client được nạp, Spring Security biết endpoint, client ID, loại grant và scope. Nhưng **chưa có authorized client chỉ vì đã tồn tại registration**; hệ thống chưa có access token gắn với người dùng.

### Giai đoạn B — Điều hướng yêu cầu cấp quyền

Khi luồng đăng nhập bắt đầu, ứng dụng tạo authorization request và đưa trình duyệt đến Authorization Server. Thường có:

- `client_id`, `response_type=code`, `redirect_uri` và `scope`;
- `state` để liên kết callback với yêu cầu ban đầu và phòng chống giả mạo yêu cầu;
- `nonce` trong OIDC để ràng buộc ID token với phiên xác thực;
- **PKCE** (ví dụ `code_challenge` / `code_verifier`) khi được áp dụng để bảo vệ việc đổi authorization code.

Người dùng đăng nhập tại Authorization Server và cấp đồng ý nếu chính sách yêu cầu. Client không trực tiếp thu thập mật khẩu của người dùng trong flow redirect này.

### Giai đoạn C — Callback, đổi code và xác thực OIDC

Authorization Server chuyển trình duyệt về redirect URI với **authorization code** và `state`. Ứng dụng kiểm tra callback khớp yêu cầu đang chờ, sau đó **backend** gọi token endpoint để đổi code lấy token.

Nếu scope có `openid` và đây là OIDC, kết quả thường có **ID token**. Spring Security xác thực các điều kiện cần thiết của ID token, chẳng hạn chữ ký, issuer, audience, hiệu lực thời gian và nonce theo ngữ cảnh. Thông tin UserInfo có thể được truy vấn tùy scope và cấu hình nhà cung cấp.

Sau thành công:

1. Spring Security tạo `Authentication` (trong OIDC login thường là `OAuth2AuthenticationToken` với principal dạng `OidcUser`).
2. Nó lưu **`OAuth2AuthorizedClient`** chứa registration, principalName, access token và refresh token nếu được phát hành.
3. Ngữ cảnh xác thực và authorized client được lưu qua **hai cơ chế có liên quan nhưng khác nhau**: security context cho trạng thái đăng nhập; authorized-client repository/service cho token truy cập.

**Không gửi authorization code hoặc ID token như thể đó là access token đến Resource Server.** Authorization code chỉ dùng một lần để đổi token; ID token chứng minh danh tính với client; access token là bằng chứng cấp quyền dành cho API phù hợp.

### Giai đoạn D — Nạp lại và dùng access token

Khi người dùng thực hiện thao tác cần gọi API, ứng dụng tìm authorized client theo **`registrationId` và principal** trong ngữ cảnh tương ứng. Access token của nó thường được đính kèm vào header:

```
GET /api/profile HTTP/1.1
Host: api.example.org
Authorization: Bearer <access-token>
```

Resource Server phải tự kiểm tra token, audience/scope và chính sách ủy quyền của API. Việc Spring Boot client đã đăng nhập bằng OIDC **không tự động khiến mọi API chấp nhận token đó**; token cần được cấp cho tài nguyên thích hợp.

### Giai đoạn E — Hết hạn, gia hạn và cấp quyền lại

Access token có thời hạn sử dụng. Khi một component gọi **authorized-client manager** có provider phù hợp, vòng đời có thể diễn ra như sau:

```
flowchart TD
    A["Cần gọi API"] --> B["Tìm authorized client đã lưu"]
    B --> C{"Đã có client và access token<br/>còn dùng được?"}
    C -->|Có| D["Dùng access token hiện tại"]
    C -->|Không| E{"Có refresh token<br/>và refresh provider?"}
    E -->|Có| F["Xin access token mới"]
    F --> G["Lưu authorized client mới"]
    G --> D
    E -->|Không| H{"Grant / ngữ cảnh<br/>cho phép xin token mới?"}
    H -->|Có| I["Chạy cơ chế authorization phù hợp"]
    I --> G
    H -->|Không| J["Yêu cầu đăng nhập / cấp quyền lại hoặc báo lỗi"]
```

- **Refresh token**: nếu được phát hành và provider `refreshToken()` được cấu hình, manager có thể đổi refresh token lấy access token mới mà không cần chuyển hướng người dùng. Token/refresh token sau khi xoay vòng cần được lưu lại.
- **Authorization Code**: nếu không thể refresh, ứng dụng có thể cần người dùng thực hiện lại luồng authorization qua trình duyệt; manager không tự tạo được code nếu thiếu ngữ cảnh tương tác.
- **Client Credentials**: ứng dụng thường xin một access token mới bằng client credentials khi token cũ hết hạn. Đây không phải hành vi refresh-token flow.
- **Bị thu hồi / đăng xuất / thất bại authorization**: dữ liệu authorized client có thể bị xóa hoặc trở nên vô dụng. Việc logout có xóa token, revoke token từ xa hay kết thúc phiên tại OP hay không phụ thuộc cấu hình cụ thể; đừng mặc định mọi logout thực hiện cả ba.

**Lưu ý:** chỉ đọc `authorizedClient.getAccessToken()` từ một đối tượng đã nạp không bảo đảm token được làm mới. Cơ chế gia hạn nằm ở **manager/provider hoặc tích hợp HTTP client đã cấu hình**; nếu tự lấy token và tự gửi request, lập trình viên phải cân nhắc thời điểm xin lại token.

## 4. Vòng đời khác: `client_credentials` cho giao tiếp máy–máy

Một batch job cần gọi API thanh toán nhưng không có người dùng đang mở trình duyệt. Khi đó:

1. Ứng dụng tra cứu registration dùng grant `client_credentials`.
2. Nó gọi `AuthorizedClientServiceOAuth2AuthorizedClientManager` cùng một principal kỹ thuật, ví dụ `invoice-batch`.
3. Provider gửi client credentials đến token endpoint.
4. Authorization Server trả access token; manager lưu `OAuth2AuthorizedClient` dưới cặp `(registrationId, principalName)`.
5. Các lần gọi sau có thể dùng lại token còn hạn. Khi token hết hạn, provider có thể xin token mới.

Không có bước chuyển hướng trình duyệt, đăng nhập người dùng hay ID token OIDC trong luồng `client_credentials` thông thường. Tên principal ở đây giúp Spring Security định danh trạng thái token được lưu; nó **không có nghĩa một người dùng thật đã đăng nhập**.

| Tiêu chí | Authorization Code + OIDC | Client Credentials |
| --- | --- | --- |
| Chủ thể thực tế | Người dùng đăng nhập | Bản thân ứng dụng |
| Tương tác trình duyệt | Có, trong giai đoạn xin quyền | Không |
| Thành phần cần thiết | Login/filter, OIDC, lưu authorized client | Manager + provider + service |
| Token thông thường | Access token, ID token; có thể refresh token | Access token; thường không có refresh token |
| Khi hết hạn | Có thể refresh hoặc cần authorize lại | Xin access token mới bằng client credentials |
| Principal dùng làm khóa lưu | Người dùng đã xác thực | Tên kỹ thuật ổn định do ứng dụng chọn |

## 5. Ví dụ cấu hình và sử dụng trong Spring Boot (Servlet)

Ví dụ dưới dùng Spring Boot 3.x / Spring Security 6.x với cách viết DSL hiện đại. Tên endpoint và khả năng cấp refresh token phụ thuộc Authorization Server thực tế.

### 5.1. Khai báo hai registration

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          web-oidc:
            provider: corporate
            client-id: ${WEB_OIDC_CLIENT_ID}
            client-secret: ${WEB_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile, email

          billing-service:
            provider: corporate
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: billing.read

        provider:
          corporate:
            issuer-uri: https://id.example.org/realms/demo
```

`issuer-uri` cho phép Spring Security/Boot khám phá metadata của OIDC provider khi nhà cung cấp hỗ trợ discovery. Với nhà cung cấp không có metadata phù hợp, cần cấu hình rõ các endpoint cần thiết. Giá trị môi trường phải được cung cấp ở thời điểm chạy và **secret không nên commit vào mã nguồn**.

### 5.2. Bật đăng nhập OIDC và hỗ trợ OAuth2 client

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
```

Khi truy cập một trang cần xác thực, người dùng có thể được đưa tới trang đăng nhập OAuth2/OIDC. Muốn khởi động trực tiếp đăng nhập với registration `web-oidc`, ứng dụng có thể điều hướng trình duyệt tới `/oauth2/authorization/web-oidc`.

### 5.3. Lấy authorized client của người dùng trong controller

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AccountController {

    @GetMapping("/account/connection")
    String connection(
            @AuthenticationPrincipal OidcUser user,
            @RegisteredOAuth2AuthorizedClient("web-oidc")
                    OAuth2AuthorizedClient authorizedClient) {

        return "subject=" + user.getSubject()
                + ", registration="
                + authorizedClient.getClientRegistration().getRegistrationId()
                + ", accessTokenExpiresAt="
                + authorizedClient.getAccessToken().getExpiresAt();
    }
}
```

`@AuthenticationPrincipal` lấy thông tin người dùng từ SecurityContext. `@RegisteredOAuth2AuthorizedClient` lấy authorized client gắn với registration/principal. Đoạn code chỉ hiển thị metadata an toàn để minh họa, **không in giá trị token**.

### 5.4. Manager dành cho tác vụ nền

Với job không có HTTP request, dùng service-based manager:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.*;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class ServiceClientConfig {

    @Bean("serviceClientManager")
    OAuth2AuthorizedClientManager serviceClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Ứng dụng yêu cầu token qua manager mỗi khi cần thực hiện lời gọi; manager có cơ hội dùng lại hoặc xin token mới tùy trạng thái:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
class BillingTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    BillingTokenProvider(
            @Qualifier("serviceClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String currentAccessToken() {
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
            .withClientRegistrationId("billing-service")
            .principal("invoice-batch")
            .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null) {
            throw new IllegalStateException(
                "Cannot authorize billing-service");
        }
        return client.getAccessToken().getTokenValue();
    }
}
```

Trong ứng dụng thực tế, nên gắn manager vào `RestClient` hoặc `WebClient` thông qua integration OAuth2 thích hợp để quản lý header Bearer và vòng đời token thống nhất. Nếu viết thủ công HTTP request, mã gọi API phải xử lý lỗi 401/403 đúng cách; **không giả định cứ HTTP 401 là được refresh rồi retry vô hạn**.

## 6. Mốc trạng thái và việc lưu trữ

Để giải quyết một vấn đề “không tìm thấy token”, hãy lần theo bảng này:

| Mốc | Cấu hình registration | Authorized client | SecurityContext |
| --- | --- | --- | --- |
| Ứng dụng vừa khởi động | Đã có nếu cấu hình hợp lệ | Chưa chắc có | Chưa có đăng nhập của người dùng |
| Người dùng bắt đầu authorize | Đã có | Có thể chưa có | Đang ở bước xác thực |
| Authorization Code + OIDC thành công | Không đổi | Được tạo/lưu | Có Authentication của người dùng |
| Request kế tiếp cùng principal | Không đổi | Có thể được nạp lại | Được khôi phục theo cơ chế phiên |
| Access token hết hạn | Không đổi | Có thể tồn tại nhưng token đã hết hạn | Người dùng có thể vẫn đăng nhập |
| Refresh hoặc xin token mới thành công | Không đổi | Được cập nhật token mới | Có thể không thay đổi |
| Xóa authorized client / xóa session | Không đổi | Có thể không nạp lại được | Phụ thuộc thao tác logout/session |

Lưu ý hai quy tắc vận hành:

1. **Khóa nhận diện authorized client có ngữ cảnh principal.** Cùng một `registrationId` nhưng khác principal có thể là hai bản ghi token độc lập. Với tác vụ nền, chọn principal kỹ thuật nhất quán để tránh tạo nhiều bản ghi không cần thiết.
2. **Session và token có vòng đời riêng.** Một phiên đăng nhập có thể còn trong khi access token đã hết hạn. Ngược lại, một token lưu ở service bền vững có thể còn tồn tại dù phiên trình duyệt đã kết thúc; việc thu hồi và dọn dẹp phải theo chính sách ứng dụng.

## 7. Những nhầm lẫn phổ biến và cách chẩn đoán

| Hiện tượng | Cần kiểm tra |
| --- | --- |
| Có `ClientRegistration` nhưng không lấy được authorized client | Người dùng/client đã hoàn tất authorization chưa? Tên `registrationId` và principal dùng để nạp có đúng không? |
| Callback trả lỗi sau đăng nhập | `redirect_uri` có khớp đăng ký bên Authorization Server? `state`, phiên lưu request, PKCE và mã authorization có hợp lệ? |
| Login OIDC thất bại khi kiểm tra ID token | `issuer-uri`, chữ ký/JWKS, audience/client ID, hiệu lực thời gian và clock skew có đúng? |
| Lần đầu gọi API được, lần sau 401 | Access token hết hạn/bị thu hồi? Manager có provider phù hợp? Client đã gửi token mới chưa? Token có đúng audience không? |
| Không có refresh token | Server/grant/scope/chính sách có cấp refresh token không? Client không thể tự sinh refresh token. |
| Chạy batch nhưng báo thiếu request/response | Có đang dùng manager dành cho Servlet ngoài request không? Cân nhắc `AuthorizedClientServiceOAuth2AuthorizedClientManager`. |
| Chạy nhiều instance, token lúc có lúc mất | Authorized-client storage có chia sẻ giữa các instance không? Session routing/persistence có thống nhất không? |
| API trả 403 | Token có đúng scope/authority và quyền đối với tài nguyên không? 403 khác với lỗi chưa xác thực 401. |

### Những nguyên tắc bảo mật cần giữ

- Dùng HTTPS cho redirect, token endpoint và lời gọi API; đăng ký redirect URI chính xác.
- Bảo vệ client secret và refresh token bằng secret manager/kho lưu trữ thích hợp; không ghi chúng vào log hoặc response.
- Chỉ yêu cầu scope cần thiết. Với API khác nhau, xác minh token có audience và quyền phù hợp; không tái sử dụng tùy tiện.
- Giữ kiểm tra `state`, nonce OIDC và PKCE khi phù hợp; không bỏ xác thực ID token.
- Khi lưu token lâu dài, cân nhắc mã hóa, thời hạn lưu, khả năng thu hồi, quyền truy cập của ứng dụng và cơ chế làm sạch.
- Không gửi ID token thay access token; không coi JWT chỉ cần giải mã là đã được xác thực.

## 8. Tự kiểm tra hiểu bài

**Tình huống 1.** Ứng dụng có registration `web-oidc` và người dùng chưa từng đăng nhập. Có `OAuth2AuthorizedClient` của người dùng chưa?

> Chưa thể kết luận có. Registration chỉ là cấu hình; authorized client chỉ hình thành khi đã có trạng thái được cấp quyền/token phù hợp.

**Tình huống 2.** Người dùng đã đăng nhập OIDC nhưng API gọi bằng access token bị 401 do token hết hạn. Người dùng có bắt buộc đăng nhập lại?

> Không nhất thiết. Nếu có refresh token hợp lệ và manager/provider được cấu hình để refresh, ứng dụng có thể lấy token mới. Nếu không thể refresh, luồng cấp quyền lại có thể cần thiết.

**Tình huống 3.** Một job không có session cần gọi API bằng `client_credentials`. Nên chọn manager nào?

> `AuthorizedClientServiceOAuth2AuthorizedClientManager` cùng `clientCredentials()` provider và một principal kỹ thuật ổn định.

**Tình huống 4.** Vì sao không dùng ID token để gọi API?

> ID token dùng để client xác thực danh tính người dùng; Resource Server thông thường yêu cầu access token được phát hành với quyền và đối tượng nhận phù hợp.

---

**Ghi nhớ luồng chính:** `ClientRegistration` mô tả cấu hình → authorization/token endpoint phát hành token → `OAuth2AuthorizedClient` giữ trạng thái token theo principal → repository/service lưu và nạp → manager/provider điều phối dùng lại, gia hạn hoặc xin token mới → HTTP client gửi access token đến API.
