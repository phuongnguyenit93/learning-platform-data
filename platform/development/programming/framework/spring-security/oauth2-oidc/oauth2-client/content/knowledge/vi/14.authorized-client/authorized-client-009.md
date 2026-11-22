# 14.9. Lưu, tải, cập nhật và xóa một authorized client

## 1. Vì sao OAuth2 Client cần một nơi lưu authorized client?

Trong ứng dụng **Spring Security OAuth 2.0 OIDC Client**, việc người dùng đăng nhập thành công qua một nhà cung cấp không đồng nghĩa backend chỉ cần dùng token một lần. Ứng dụng có thể cần:

- Gọi UserInfo hoặc một API nghiệp vụ sau khi người dùng đã đăng nhập.
- Tải Access Token đã nhận để dùng trong các lần gọi API tiếp theo.
- Làm mới Access Token khi nó hết hạn và còn Refresh Token hợp lệ.
- Cập nhật thông tin token nếu Authorization Server cấp bộ token mới.
- Xóa kết nối với provider khi người dùng chọn “Ngắt kết nối”.
- Tồn tại qua nhiều HTTP requests, nhiều instance hoặc sau khi ứng dụng restart, tùy thiết kế.

Spring Security biểu diễn một client đã nhận quyền bằng **`OAuth2AuthorizedClient`**. Đối tượng này kết hợp *client registration*, *tên principal* và các token đã được cấp.

Ví dụ, người dùng đã đăng nhập portal bằng OIDC và cho phép portal gọi API lịch. Backend cần nhớ **Access Token của registration lịch** cho principal tương ứng, chứ không nên yêu cầu người dùng nhập lại authorization code mỗi khi mở trang “Lịch của tôi”.

**Authorized client không phải bản ghi người dùng (user account), cũng không phải một HTTP session.** Nó là trạng thái ủy quyền của một OAuth2 client đối với một principal/đối tượng thực thi trong phạm vi registration. Bài này tập trung vào cách Spring Security Servlet **lưu, tải, cập nhật và xóa** trạng thái ấy an toàn.

## 2. Phân biệt ClientRegistration và OAuth2AuthorizedClient

Trước tiên cần tách **cấu hình client** khỏi **kết quả ủy quyền**.

| Thành phần | Chứa gì? | Tính chất |
| --- | --- | --- |
| `ClientRegistration` | `registrationId`, client ID, grant type, redirect URI, scope, authorization/token/JWKS/UserInfo endpoints | Cấu hình OAuth2 client dùng chung cho các giao dịch |
| `OAuth2AuthorizedClient` | `ClientRegistration`, `principalName`, Access Token và Refresh Token nếu có | Kết quả ủy quyền dành cho một principal |
| `OAuth2AuthorizedClientService` | Cơ chế lưu/tải/xóa theo `registrationId + principalName` | Trừu tượng hóa việc lưu token không phụ thuộc Servlet request |
| `OAuth2AuthorizedClientRepository` | Cơ chế lưu/tải/xóa có ngữ cảnh `HttpServletRequest`, `HttpServletResponse` và `Authentication` | Thích hợp khi làm việc trong luồng Servlet |
| `OAuth2AuthorizedClientManager` | Tìm hoặc xin mới authorized client, có thể refresh token theo provider/grant đã cấu hình | Điều phối vòng đời cấp quyền, không chỉ CRUD |

Một `ClientRegistration` tên `calendar` có thể được nhiều người dùng sử dụng:

~~~text
ClientRegistration:
  registrationId = "calendar"
  clientId = "portal-calendar"
  authorizationGrantType = "authorization_code"

OAuth2AuthorizedClient #1:
  registrationId = "calendar"
  principalName = "alice"
  accessToken = "TOKEN_FOR_ALICE"

OAuth2AuthorizedClient #2:
  registrationId = "calendar"
  principalName = "bob"
  accessToken = "TOKEN_FOR_BOB"
~~~

**Không bao giờ chỉ lưu token theo `registrationId` khi token thuộc người dùng.** Nếu thiếu principal namespace, Access Token của người A có thể bị trả nhầm cho người B.

### 2.1. Các trường quan trọng của OAuth2AuthorizedClient

API chính:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

OAuth2AuthorizedClient client = /* được framework tải hoặc cấp quyền */;

ClientRegistration registration = client.getClientRegistration();
String registrationId = registration.getRegistrationId();
String principalName = client.getPrincipalName();
OAuth2AccessToken accessToken = client.getAccessToken();
OAuth2RefreshToken refreshToken = client.getRefreshToken(); // có thể null
~~~

| Giá trị | Ý nghĩa |
| --- | --- |
| `client.getClientRegistration()` | Cấu hình provider/client được dùng để lấy token |
| `client.getPrincipalName()` | Tên định danh mà dữ liệu authorized client được gắn vào |
| `client.getAccessToken()` | Access Token hiện có, bao gồm giá trị, token type, issued/expiry và scopes |
| `client.getRefreshToken()` | Refresh Token nếu provider đã cấp và framework lưu được |

**Đối tượng này không chứa `id_token` như một thuộc tính chuẩn**. Với OIDC Login, ID Token dùng xác thực người dùng và thường nằm trong `OidcUser`/authentication context; Access Token/Refresh Token của OAuth2 client nằm trong `OAuth2AuthorizedClient`.

### 2.2. Principal name là khóa lưu trữ, không phải email tùy ý

Đa số service lưu authorized client theo khóa logic:

~~~text
(clientRegistrationId, principalName)
~~~

Với OAuth2 Login, tên principal thường đến từ `Authentication.getName()`, phụ thuộc loại principal và user name attribute. Đối với OIDC, khóa danh tính ổn định là **`iss + sub`**; riêng `sub` có thể trùng giữa hai issuer. Vì thế, khi thiết kế nhiều provider và tenant, cần bảo đảm registration và principal namespace không tạo collision hoặc nhầm người dùng.

Đừng tự ý dùng email làm `principalName` để lưu token bởi email có thể đổi, có thể chưa xác minh và có thể trùng/được tái sử dụng.

## 3. Vòng đời một authorized client

Một lượt điển hình:

~~~mermaid
flowchart TD
    A["Ứng dụng cần gọi API bằng client registration"] --> B["OAuth2AuthorizedClientManager.authorize(...)"]
    B --> C{"Đã có authorized client hợp lệ?"}
    C -->|Có, token còn phù hợp| D["Trả authorized client đã lưu"]
    C -->|Chưa có| E["Grant phù hợp: authorization_code / client_credentials / ..."]
    C -->|Token hết hạn, có refresh token| F["refresh_token grant"]
    E --> G["Token Endpoint cấp token"]
    F --> G
    G --> H["Lưu/cập nhật OAuth2AuthorizedClient"]
    D --> I["Dùng Access Token gọi API đúng audience/scope"]
    H --> I
    I --> J{"Người dùng ngắt kết nối hoặc token không còn dùng?"}
    J -->|Có| K["removeAuthorizedClient(...) và revocation nếu provider hỗ trợ"]
    J -->|Không| A
~~~

Đây là mô hình logic. **`OAuth2AuthorizedClientRepository` hoặc `OAuth2AuthorizedClientService` tự chúng không gửi HTTP request để refresh token**. Việc cấp mới/làm mới token được điều phối bởi `OAuth2AuthorizedClientManager` với `OAuth2AuthorizedClientProvider` thích hợp.

Đặc biệt, khi Authorization Code Login thành công, Spring Security có thể tự lưu authorized client trong repository ở bước xử lý đăng nhập. Ứng dụng **không bắt buộc** phải tự gọi `saveAuthorizedClient` ngay sau mỗi login chuẩn.

## 4. Hai abstraction lưu trữ: Repository và Service

Spring Security cung cấp hai kiểu API liên quan chặt chẽ nhưng có phạm vi khác nhau.

### 4.1. OAuth2AuthorizedClientRepository — có Servlet context

Giao diện:

~~~java
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
~~~

Các phương thức:

~~~java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response
);

void removeAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response
);
~~~

Đây là chữ ký diễn giải; `Authentication` là `org.springframework.security.core.Authentication`, còn HTTP types ở Servlet stack hiện đại dùng `jakarta.servlet.http.*`.

Ba phương thức cho phép implementation sử dụng **HTTP session, cookie hoặc cơ chế lưu server-side có ngữ cảnh người dùng**. Cấu trúc lưu trữ thực tế không nhất thiết nằm trong request.

Ví dụ: controller cần xem một authorized client của người dùng đang đăng nhập, hoặc người dùng nhấn nút disconnect trong ứng dụng web.

### 4.2. OAuth2AuthorizedClientService — không cần Servlet request

Giao diện:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
~~~

Các phương thức:

~~~java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    String principalName
);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
~~~

Service không nhận `HttpServletRequest`/`HttpServletResponse`. Do đó, nó phù hợp khi token được lưu trong memory, JDBC hoặc được truy xuất từ một service chạy **ngoài HTTP request**, miễn là ứng dụng có quyền tra cứu dữ liệu đó.

| Đặc điểm | Repository | Service |
| --- | --- | --- |
| API cần HTTP request/response | Có | Không |
| API cần Authentication | Có | Không, dùng `principalName` |
| Có thể lưu trong session | Có, với implementation phù hợp | Không phải đặc điểm bắt buộc |
| Có thể lưu trong database | Có thể delegate | Có, ví dụ JDBC |
| Tự refresh Access Token | Không | Không |
| Phù hợp controller Servlet | Có | Có, nếu có principal name được xác định an toàn |
| Phù hợp scheduled job không có Servlet request | Thường không trực tiếp | Có |

### 4.3. Không nhầm với AuthorizationRequestRepository

| Repository | Lưu gì? | Giai đoạn |
| --- | --- | --- |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | `state`, redirect URI, PKCE và request ủy quyền đang chờ | **Trước callback**, khi browser được đưa đến IdP |
| `OAuth2AuthorizedClientRepository` | Access Token/Refresh Token đã được cấp | **Sau khi ủy quyền thành công** |

Nếu callback báo `authorization_request_not_found`, vấn đề nằm ở correlation/session của **authorization request ban đầu**, không nhất thiết do mất `OAuth2AuthorizedClient`. Ngược lại, login thành công nhưng API không có token lưu trữ là vấn đề của authorized client lifecycle.

## 5. Các implementation phổ biến

### 5.1. HttpSessionOAuth2AuthorizedClientRepository

`HttpSessionOAuth2AuthorizedClientRepository` lưu dữ liệu authorized client bằng **HTTP session**. Nó phù hợp với một số luồng Servlet đơn giản hoặc ngữ cảnh chưa xác thực được framework xử lý theo session.

~~~text
Browser
  Cookie JSESSIONID -> session S1
                         |
                         v
                 HTTP Session S1
                   authorized clients:
                     calendar -> Access Token / Refresh Token
~~~

Ưu điểm: đơn giản, gần với browser session. Hạn chế: dữ liệu thường mất khi session hết hạn/bị xóa; nếu chỉ dùng memory trên một node thì không tự tồn tại qua restart hoặc dùng chung cho nhiều node.

### 5.2. InMemoryOAuth2AuthorizedClientService

`InMemoryOAuth2AuthorizedClientService` giữ authorized clients **trong memory của tiến trình ứng dụng**, theo khóa registration và principal.

~~~java
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

OAuth2AuthorizedClientService service =
    new InMemoryOAuth2AuthorizedClientService(clientRegistrationRepository);
~~~

Trong ví dụ, `clientRegistrationRepository` được giả định đã được cung cấp bởi Spring Boot/Spring Security. Cách lưu memory phù hợp với demo hoặc môi trường không yêu cầu token sống qua restart; **không tự động chia sẻ dữ liệu giữa các instance**.

### 5.3. JdbcOAuth2AuthorizedClientService

`JdbcOAuth2AuthorizedClientService` dùng cơ sở dữ liệu thông qua Spring JDBC để lưu Access Token và Refresh Token. Đây là lựa chọn thường gặp khi cần dữ liệu tồn tại qua nhiều phiên HTTP hoặc nhiều instance.

~~~java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

OAuth2AuthorizedClientService jdbcService(
        DataSource dataSource,
        ClientRegistrationRepository registrations) {
    return new JdbcOAuth2AuthorizedClientService(
        new JdbcTemplate(dataSource), registrations);
}
~~~

Đoạn trên minh họa cách tạo đối tượng, chưa phải cấu hình database/schema/migration đầy đủ. Khi dùng JDBC service, cần **tạo bảng/schema tương ứng với phiên bản Spring Security** và bảo vệ các cột token vì đó là credential nhạy cảm. Không tự áp một schema từ version khác mà chưa đối chiếu hợp đồng của thư viện.

### 5.4. AuthenticatedPrincipalOAuth2AuthorizedClientRepository

`AuthenticatedPrincipalOAuth2AuthorizedClientRepository` là adapter quan trọng:

- Với **principal đã được xác thực**, nó delegate lưu/tải/xóa thông qua `OAuth2AuthorizedClientService`.
- Với **principal chưa xác thực/anonymous**, nó có thể dùng một repository khác, thường là `HttpSessionOAuth2AuthorizedClientRepository`.

~~~mermaid
flowchart TD
    A["OAuth2AuthorizedClientRepository"] --> B{"Principal đã authenticated?"}
    B -->|Có| C["OAuth2AuthorizedClientService"]
    B -->|Không/anonymous| D["Anonymous fallback repository"]
    C --> E["InMemory / JDBC / custom store"]
    D --> F["HttpSessionOAuth2AuthorizedClientRepository"]
~~~

Điều này giải thích vì sao **đăng ký JDBC service** và **HTTP session** không phải lúc nào cũng là hai phương án loại trừ nhau: một repository có thể dùng service cho người dùng đăng nhập và session fallback cho tình huống chưa xác thực.

**Không giả định chỉ vì thấy HTTP session cookie thì token chắc chắn nằm trong session.** Hãy xác định implementation của repository/service mà ứng dụng thực tế đang sử dụng.

## 6. Cấu hình một ứng dụng Spring Boot Servlet

### 6.1. Dependency

Ví dụ với Spring Boot 3.x và Servlet MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Khi dùng JDBC authorized client service:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Với Spring Boot 4.x, các starter được modular hóa và có thể mang tên `spring-boot-starter-webmvc`, `spring-boot-starter-security-oauth2-client`. Chọn đúng bộ dependency theo BOM của dự án; không trộn Spring Security versions chỉ để có một class JDBC.

### 6.2. Registration OAuth2/OIDC

Ví dụ `application.yml` cho provider OIDC có discovery:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-provider:
            issuer-uri: https://id.example.com/realms/company
~~~

Những URL và ID là ví dụ; thay bằng thông tin của provider thật. `company` là **registration ID**; `company-provider` là ID phần cấu hình provider.

### 6.3. SecurityFilterChain

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
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

`oauth2Login()` xử lý việc đăng nhập từ browser; `oauth2Client()` hỗ trợ cấu hình OAuth2 Client khi cần gọi API và quản lý authorized client. **Việc login OIDC thành công không tự chứng minh Access Token có scope phù hợp cho mọi API**; phải xin đúng quyền và chọn đúng resource server.

## 7. Lưu một authorized client

### 7.1. Lưu bằng OAuth2AuthorizedClientService

Khi ứng dụng **đã có một `OAuth2AuthorizedClient` hợp lệ từ một OAuth2 flow tin cậy**, có thể gọi:

~~~java
void save(
        OAuth2AuthorizedClientService service,
        OAuth2AuthorizedClient authorizedClient,
        String principalName) {
    service.saveAuthorizedClient(authorizedClient, principalName);
}
~~~

Hành vi lưu: khóa logic kết hợp `authorizedClient.getClientRegistration().getRegistrationId()` với `principalName` được cung cấp. Đừng lấy `principalName` từ query string tự do của browser để lưu token vào tài khoản người khác.

### 7.2. Lưu bằng OAuth2AuthorizedClientRepository

Trong Servlet request:

~~~java
void saveForCurrentRequest(
        OAuth2AuthorizedClientRepository repository,
        OAuth2AuthorizedClient authorizedClient,
        Authentication authentication,
        HttpServletRequest request,
        HttpServletResponse response) {

    repository.saveAuthorizedClient(
        authorizedClient,
        authentication,
        request,
        response);
}
~~~

Các import:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
~~~

**Không tự tạo `OAuth2AuthorizedClient` từ Access Token do browser gửi**, hoặc lấy một token bất kỳ rồi gắn vào principal khác. Token phải đến từ quy trình cấp quyền hợp lệ, đúng registration và đúng đối tượng được ủy quyền.

### 7.3. Có phải tự save sau OAuth2 Login không?

Thông thường **không**. `OAuth2LoginAuthenticationFilter` và các thành phần OAuth2 Login liên quan đã kết nối với authorized client repository để lưu kết quả cấp quyền khi login thành công.

Tự save thêm sau login có thể gây:

- Ghi token trùng lặp.
- Lưu dưới `principalName` khác cách framework đã chọn.
- Vô tình ghi token của một registration vào user khác nếu code tự map tên.
- Mất đồng bộ khi session/authentication thay đổi.

Chỉ chủ động gọi save khi thực sự đang quản lý một flow tùy chỉnh hoặc một authorized client được tạo/cập nhật hợp lệ ngoài cơ chế tự động.

## 8. Tải một authorized client

### 8.1. Tải từ Service

~~~java
OAuth2AuthorizedClient authorizedClient =
    authorizedClientService.loadAuthorizedClient(
        "company",
        authentication.getName());
~~~

Nếu không có bản ghi phù hợp, phương thức thường trả `null`. Code ứng dụng phải xử lý trường hợp chưa có quyền thay vì lập tức gọi `getAccessToken()` trên `null`.

Ví dụ:

~~~java
OAuth2AuthorizedClient client =
    service.loadAuthorizedClient("company", currentPrincipalName);

if (client == null) {
    // User chưa cấp quyền cho registration này,
    // hoặc bản ghi đã bị xóa / không tồn tại.
    return;
}

OAuth2AccessToken accessToken = client.getAccessToken();
// Không log hoặc trả token cho browser.
~~~

Phần này giả định biến `service` và `currentPrincipalName` đến từ cơ chế xác thực server-side hợp lệ.

### 8.2. Tải từ Repository trong controller

Ví dụ một endpoint chỉ báo **đã có authorized client được lưu hay chưa**, không làm lộ token:

~~~java
package com.example.web;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConnectionStatusController {

    private final OAuth2AuthorizedClientRepository repository;

    public ConnectionStatusController(
            OAuth2AuthorizedClientRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/integrations/company/status")
    public Map<String, Object> status(
            Authentication authentication,
            HttpServletRequest request) {

        OAuth2AuthorizedClient client =
            repository.loadAuthorizedClient(
                "company", authentication, request);

        return Map.of(
            "registrationId", "company",
            "stored", client != null,
            "accessTokenPresent", client != null
        );
    }
}
~~~

Endpoint này được bảo vệ bởi `anyRequest().authenticated()` trong `SecurityFilterChain` ở trên. Kết quả chỉ phản ánh **trạng thái lưu trữ**, không chứng minh token còn hiệu lực hoặc gọi được API.

Trong sản phẩm thật, có thể chỉ cần `stored`; không nên gửi chi tiết scopes, token expiry hay tên principal nếu không cần cho UI.

### 8.3. @RegisteredOAuth2AuthorizedClient

Spring Security Servlet cung cấp annotation:

~~~java
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
~~~

Một số ví dụ sử dụng phiên bản Spring Security cụ thể dùng tham số controller như:

~~~java
@GetMapping("/calendar")
String calendar(
    @RegisteredOAuth2AuthorizedClient("calendar")
    OAuth2AuthorizedClient authorizedClient) {

    // Sử dụng authorizedClient.getAccessToken() phía server.
    return "calendar";
}
~~~

**Lưu ý:** annotation/resolver không chỉ là “lấy raw record” trong mọi trường hợp; nó có thể phối hợp với `OAuth2AuthorizedClientManager` để tìm hoặc authorize/re-authorize theo cấu hình. Nếu cần **kiểm tra trạng thái lưu trữ mà không kích hoạt luồng cấp quyền**, dùng `loadAuthorizedClient(...)` trực tiếp với principal và registration rõ ràng.

Không đưa `authorizedClient.getAccessToken().getTokenValue()` vào model/template, URL hoặc HTTP response chỉ vì controller đã nhận được đối tượng.

## 9. Cập nhật authorized client: lưu lại hay refresh?

Từ “cập nhật” có ít nhất hai nghĩa:

1. **Thay bản ghi lưu trữ**: ghi một `OAuth2AuthorizedClient` mới vào cùng khóa `(registrationId, principalName)`.
2. **Lấy token mới**: thực hiện OAuth2 grant, thường là Refresh Token grant, rồi lưu kết quả mới.

**Repository/service chỉ làm nhiệm vụ lưu trữ.** Chúng không hiểu đầy đủ điều kiện refresh và không tự gọi token endpoint. Phần cấp/làm mới token phải do `OAuth2AuthorizedClientManager` và `OAuth2AuthorizedClientProvider` hoặc một flow đã được thiết kế xử lý.

### 9.1. Khi Access Token đã hết hạn

Một `OAuth2AccessToken` có các thời điểm:

~~~java
OAuth2AccessToken token = authorizedClient.getAccessToken();

Instant issuedAt = token.getIssuedAt();
Instant expiresAt = token.getExpiresAt();
~~~

Giá trị `expiresAt` mô tả thời điểm hết hạn nếu có. Không dùng logic kiểu “cứ thấy `OAuth2AuthorizedClient` khác null thì Access Token luôn còn hiệu lực”.

Khi phát hiện token không còn phù hợp:

- Nếu có Refresh Token hợp lệ và provider/grant cho phép, token manager có thể refresh.
- Nếu không có Refresh Token hoặc refresh bị từ chối, có thể cần bắt đầu lại Authorization Code flow hoặc yêu cầu người dùng cấp quyền.
- Với Client Credentials, token manager có thể xin token mới bằng client credentials; không có người dùng tương tác.
- Các provider có thể thu hồi token trước hạn; kiểm tra thời hạn ở client không thay thế phản hồi 401/403 từ API.

### 9.2. Token rotation và việc lưu lại

Một response refresh có thể trả:

~~~json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "NEW_REFRESH_TOKEN",
  "scope": "calendar.read"
}
~~~

Nếu Refresh Token được xoay vòng, bản ghi `OAuth2AuthorizedClient` cần phản ánh token mới. Không giữ mãi Refresh Token cũ và retry khi token endpoint đã thu hồi nó.

Tùy provider, refresh response **có thể không chứa Refresh Token mới**. Framework hoặc client logic phải áp dụng đúng quy tắc giữ/đổi Refresh Token theo grant và hợp đồng provider; không mặc định “thiếu trường nghĩa là xóa toàn bộ kết nối”.

### 9.3. Không cập nhật token bằng phép sửa chuỗi

`OAuth2AuthorizedClient` không phải một đối tượng mà ứng dụng nên “sửa” token bằng thao tác chuỗi:

~~~java
// PHẢN VÍ DỤ: không tự lấy chuỗi token từ browser rồi ghi đè.
String token = request.getParameter("access_token");
// repository.save... với token không được cấp hợp lệ là sai thiết kế.
~~~

Access Token phải được phát hành bởi Authorization Server tin cậy và đúng grant. Nếu cần lưu trạng thái mới, nhận kết quả từ OAuth2 client/provider rồi xây/lưu object theo contract của Spring Security.

## 10. OAuth2AuthorizedClientManager: điểm vào cho cấp mới và refresh

Hai manager thường gặp trong hệ sinh thái Servlet:

| Manager | Bối cảnh | Kho lưu liên quan |
| --- | --- | --- |
| `DefaultOAuth2AuthorizedClientManager` | Trong `HttpServletRequest` của Servlet web app | `OAuth2AuthorizedClientRepository` |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Ngoài Servlet request, ví dụ job/backend service | `OAuth2AuthorizedClientService` |

Manager có thể điều phối các provider cho grant như `authorization_code`, `refresh_token` và `client_credentials` tùy cấu hình. Mỗi grant có điều kiện riêng; một manager không thể làm mới token nếu provider không cấp Refresh Token hoặc client không có quyền sử dụng grant đó.

### 10.1. Ví dụ cấu hình manager cho request Servlet

~~~java
package com.example.security;

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

**Ví dụ này minh họa điểm cấu hình**, không phải yêu cầu mọi ứng dụng phải bật tất cả các grant. Với một portal chỉ có đăng nhập Authorization Code, không cần cho phép Client Credentials nếu nghiệp vụ không dùng. Ngược lại, worker service không có user/browser nên thường dùng Client Credentials và `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

### 10.2. Gọi authorize() để có client phù hợp

Khi đã có `Authentication` và đang ở Servlet request:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

OAuth2AuthorizeRequest authorizeRequest =
    OAuth2AuthorizeRequest.withClientRegistrationId("calendar")
        .principal(authentication)
        .build();

OAuth2AuthorizedClient client =
    authorizedClientManager.authorize(authorizeRequest);

if (client == null) {
    // Manager không thể cấp/khôi phục client trong bối cảnh hiện tại.
    // Không gọi API bằng một token chưa có.
}
~~~

Trong ví dụ, `authentication` và `authorizedClientManager` đã được injection/cung cấp bởi server. Với `DefaultOAuth2AuthorizedClientManager`, lời gọi cần có **Servlet request/response context** thích hợp hoặc các attributes được cấu hình để manager làm việc với repository.

Khi provider thành công, manager thường sử dụng success handler phù hợp để lưu authorized client mới hoặc mới refresh vào kho. Vì vậy **không cần thêm một lần `saveAuthorizedClient` thủ công nếu manager đã chịu trách nhiệm lưu**.

### 10.3. Service manager cho công việc ngoài HTTP request

~~~java
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
    new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientService);

manager.setAuthorizedClientProvider(
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build());
~~~

Đoạn trên giả định hai dependency đã được cấu hình. Với Client Credentials, không có OIDC end-user login: Access Token đại diện cho **client/service principal**, không có ID Token xác thực người dùng.

Trong background job, hãy chọn `principalName` nhất quán để lưu token service-level (ví dụ `system-calendar-sync`). Đừng dùng ngẫu nhiên một tên người dùng cuối để nhận token Client Credentials của cả hệ thống.

### 10.4. Khác nhau giữa load() và authorize()

| Cách gọi | Tác động có thể có |
| --- | --- |
| `service.loadAuthorizedClient(registrationId, principalName)` | Chỉ đọc bản ghi được lưu |
| `repository.loadAuthorizedClient(registrationId, auth, request)` | Chỉ đọc bản ghi theo context repository |
| `manager.authorize(authorizeRequest)` | Đọc trạng thái, có thể xin mới/refresh, có thể cập nhật/xóa theo policy và handler |

Khi chỉ hiển thị trạng thái kết nối, nên phân biệt **“đã có bản ghi”** và **“hiện có Access Token có thể sử dụng”**. Hai sự kiện không tương đương.

## 11. Xóa một authorized client

Người dùng có thể chọn “Ngắt kết nối lịch”, hoặc quản trị viên yêu cầu xóa quyền truy cập ứng dụng đã lưu. Trong Spring Security, xóa authorized client là thao tác **loại bỏ bản ghi token do client giữ**.

### 11.1. Xóa từ OAuth2AuthorizedClientService

~~~java
service.removeAuthorizedClient(
    "calendar",
    currentPrincipalName
);
~~~

Điều này xóa bản ghi cho đúng `registrationId` và `principalName`. Nếu trước đó user có nhiều authorized clients cho các registrations khác nhau, thao tác này không tự xóa tất cả.

### 11.2. Xóa từ OAuth2AuthorizedClientRepository

~~~java
repository.removeAuthorizedClient(
    "calendar",
    authentication,
    request,
    response
);
~~~

Trong Servlet app, request, response và Authentication quyết định ngữ cảnh cần xóa. Với một repository delegate xuống service, đây có thể là thao tác xóa bản ghi trong database; với session-based repository, nó có thể xóa attribute của session.

### 11.3. Controller POST ngắt kết nối

Một endpoint minh họa:

~~~java
package com.example.web;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DisconnectController {

    private final OAuth2AuthorizedClientRepository repository;

    public DisconnectController(
            OAuth2AuthorizedClientRepository repository) {
        this.repository = repository;
    }

    @PostMapping("/integrations/calendar/disconnect")
    public Map<String, String> disconnect(
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        repository.removeAuthorizedClient(
            "calendar", authentication, request, response);

        return Map.of("status", "local_record_removed");
    }
}
~~~

Ví dụ giả định URL được bảo vệ bởi `anyRequest().authenticated()` và Spring Security CSRF protection đang bật cho request POST. Với HTML form cần gửi CSRF token tương ứng; với SPA cần cấu hình CSRF/session theo kiến trúc thay vì vô hiệu hóa CSRF toàn cục.

**Phản hồi `local_record_removed` chỉ xác nhận việc xóa dữ liệu do ứng dụng lưu**. Nó **không khẳng định** Access Token đã bị Authorization Server thu hồi, user đã đăng xuất khỏi IdP hoặc toàn bộ quyền đã bị hủy ở provider.

### 11.4. Xóa bản ghi khác với revoke token

| Hành động | Thực sự làm gì? |
| --- | --- |
| `removeAuthorizedClient(...)` | Xóa bản ghi token trong kho của OAuth2 client |
| OAuth2 Token Revocation (nếu provider hỗ trợ) | Yêu cầu Authorization Server thu hồi token theo cơ chế chuẩn/extension |
| Local logout | Kết thúc SecurityContext/HTTP session theo logout policy |
| OIDC RP-Initiated Logout | Có thể yêu cầu OP kết thúc phiên đăng nhập IdP nếu được cấu hình và hỗ trợ |
| Xóa liên kết tài khoản nghiệp vụ | Thay đổi dữ liệu tích hợp của ứng dụng, có thể cần quy trình riêng |

Muốn disconnect đầy đủ, một số sản phẩm cần gọi **revocation endpoint** (RFC 7009) trước khi xóa token đã lưu, nếu provider hỗ trợ. Phải xử lý kết quả theo contract của provider, không log raw token. Nếu chỉ xóa local record, token cũ có thể vẫn còn hiệu lực tại Resource Server cho đến khi hết hạn/bị thu hồi.

Không yêu cầu gọi revocation endpoint nếu provider không có; khi đó phải thông báo đúng mức độ của thao tác và quản lý rủi ro vòng đời token.

## 12. Lưu vào database: từ demo đến nhiều instance

### 12.1. Khi nào cần JDBC?

Nếu chạy một instance và không cần authorized clients tồn tại qua restart, in-memory service có thể đủ cho ví dụ học tập. Nhưng nếu ứng dụng:

- Chạy nhiều pods/instances sau load balancer.
- Cần Access Token để thực hiện tác vụ sau khi user đã đóng browser.
- Muốn người dùng kết nối một lần và dùng trong nhiều HTTP sessions.
- Cần quản lý vòng đời token/Refresh Token theo chính sách lâu dài.

thì một kho chia sẻ, bền vững như JDBC có thể phù hợp hơn.

~~~text
Browser A ------> App Instance 1 ---+
                                    |
Browser B ------> App Instance 2 ---+---> Shared database
                                    |     oauth2_authorized_client
Background job --> Worker Instance -+     (encrypted/restricted tokens)
~~~

### 12.2. Ví dụ bean JDBC service

~~~java
package com.example.security;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class AuthorizedClientStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            DataSource dataSource,
            ClientRegistrationRepository registrations) {
        return new JdbcOAuth2AuthorizedClientService(
            new JdbcTemplate(dataSource),
            registrations);
    }
}
~~~

Để repository cho người đã xác thực thực sự delegate vào service này, cần sử dụng/khai báo `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` phù hợp. Ví dụ cấu hình tường minh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientRepositoryConfig {

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository(
            OAuth2AuthorizedClientService service) {
        return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
            service);
    }
}
~~~

Trong ứng dụng có Spring Boot auto-configuration, có thể đã tồn tại service/repository beans. Không đăng ký bean trùng hoặc làm thay đổi store đang được sử dụng khi chưa xác định cấu hình hiện tại. Những đoạn trên minh họa cách tạo **các thành phần cần phối hợp**, không phải yêu cầu dự án thật phải copy mọi bean.

### 12.3. Schema và dữ liệu bí mật

Spring Security có schema tham khảo cho JDBC authorized client service. Tên bảng thường là:

~~~text
oauth2_authorized_client
  client_registration_id
  principal_name
  access_token_type
  access_token_value
  access_token_issued_at
  access_token_expires_at
  access_token_scopes
  refresh_token_value
  refresh_token_issued_at
~~~

Đây là **danh sách cột minh họa** nhằm hiểu mô hình, không thay thế DDL chính thức của phiên bản Spring Security đang dùng. Trong production, dùng migration phù hợp database/schema/độ dài cột, có index/unique key cho cặp `client_registration_id + principal_name`, xử lý byte/token encoding nhất quán.

Các cột `access_token_value` và `refresh_token_value` chứa **credential**. Cần:

- Hạn chế quyền truy cập database theo least privilege.
- Mã hóa dữ liệu nhạy cảm khi lưu nếu chính sách yêu cầu; quản lý khóa riêng và vòng đời rotation.
- Bảo vệ bản sao lưu/backup và replication.
- Không đưa token vào SQL log, tracing hoặc dump hỗ trợ.
- Thiết lập retention/cleanup rõ ràng khi disconnect hoặc tài khoản bị xóa.
- Đánh giá giao thức refresh token rotation và trường hợp ghi đồng thời từ nhiều instance.

**Không dùng database persistence như lý do bỏ qua revocation hay kiểm tra audience/scope khi gọi API.**

## 13. Các vấn đề concurrency khi refresh và cập nhật token

### 13.1. Hai request cùng refresh một authorized client

Giả sử Access Token hết hạn và hai API requests đến cùng lúc:

~~~mermaid
sequenceDiagram
    autonumber
    participant R1 as Request A
    participant R2 as Request B
    participant DB as Authorized Client Store
    participant OP as Token Endpoint
    R1->>DB: Load old access/refresh token
    R2->>DB: Load cùng old token
    R1->>OP: Refresh bằng old refresh token
    R2->>OP: Refresh bằng old refresh token
    OP-->>R1: New access + rotated refresh token
    OP-->>R2: invalid_grant hoặc kết quả khác tùy policy
    R1->>DB: Save new authorized client
~~~

Khi provider **rotate Refresh Token một lần dùng**, request thứ hai có thể gặp `invalid_grant`. Tùy logic failure handler, một lỗi refresh cũ có thể gây xóa bản ghi đã được request A cập nhật nếu hệ thống không xử lý cạnh tranh đúng.

### 13.2. Chiến lược xử lý

Các phương án cần đánh giá theo quy mô:

1. **Để manager mặc định xử lý** và quan sát hành vi thực tế khi tải/refresh song song, trước khi tự xây cơ chế phức tạp.
2. Nếu concurrency gây lỗi thực, dùng **single-flight/lock theo khóa (registrationId, principalName)** khi refresh, với TTL và cơ chế giải phóng khi node lỗi.
3. Với database, cân nhắc optimistic locking/version hoặc compare-and-swap để tránh một response cũ ghi đè token mới.
4. Khi refresh thất bại do `invalid_grant`, kiểm tra liệu đã có bản ghi/token mới từ luồng khác trước khi quyết định xóa hoặc yêu cầu reauthorization.
5. Không retry Refresh Token cũ vô hạn.

**Không đặt một lock global cho toàn bộ người dùng**, vì sẽ làm mọi hoạt động refresh nối đuôi nhau. Nếu cần đồng bộ, khóa phải có scope phù hợp với authorized client và bảo đảm isolation.

## 14. Khóa lưu trữ và ranh giới đa tenant

### 14.1. Cặp khóa logical

Với Service:

~~~text
registrationId + principalName -> OAuth2AuthorizedClient
~~~

Ví dụ:

| registrationId | principalName | Ý nghĩa |
| --- | --- | --- |
| `company` | `employee-123` | User với company OIDC registration |
| `partner` | `employee-123` | User với partner registration, **không phải cùng kết nối** |
| `calendar` | `employee-123` | Quyền riêng để gọi calendar API |
| `service-reports` | `system-reports-job` | Client Credentials của service, không phải end-user login |

Hai provider có thể cấp cùng `sub` cho hai người khác nhau. Với OIDC, danh tính logic cần xét **`issuer + subject`**, và registration ID phải có ranh giới rõ ràng. Trong hệ thống nhiều tenant, một principal name không đủ namespace có thể dẫn đến token association sai.

### 14.2. Khi principalName thay đổi

Nếu ứng dụng thay cách chọn `Authentication.getName()` từ `sub` sang email, service có thể không tìm được authorized client đã lưu dưới tên cũ.

Đừng “sửa” bằng cách tra token theo email rộng hoặc bỏ kiểm tra principal. Cần một chiến lược migration có kiểm soát và ràng buộc danh tính đã xác minh.

### 14.3. Không tin registrationId do browser chọn tùy ý

Nếu một endpoint nhận `registrationId` từ query/path, phải kiểm soát:

- User có được phép sử dụng registration này không?
- Registration có thuộc tenant/feature hiện tại không?
- Token được lưu dưới principal đang xác thực hay một account được ủy quyền hợp lệ khác?
- Có thể lộ thông tin token/tenant nếu người dùng đoán registration ID không?

Một endpoint disconnect an toàn nên dùng danh sách registration được duyệt hoặc ánh xạ từ tích hợp nghiệp vụ; không tự xóa mọi client theo ID mà browser gửi.

## 15. Logout, disconnect, xóa user: các vòng đời riêng

Một người dùng có thể:

- Đăng xuất khỏi HTTP session của ứng dụng.
- Ngắt kết nối một OAuth2 integration.
- Bị khóa tài khoản tại IdP.
- Xóa tài khoản nội bộ.
- Yêu cầu thu hồi Refresh Token.

Các sự kiện này **không tự đồng nghĩa nhau**.

| Sự kiện | Tác động mà ứng dụng cần quyết định |
| --- | --- |
| HTTP logout | SecurityContext/session kết thúc, nhưng JDBC authorized client có thể vẫn được lưu |
| Disconnect một integration | Xóa authorized client của registration đó, có thể revoke token |
| Xóa user nội bộ | Xóa tất cả authorized clients liên quan theo chính sách dữ liệu và khóa user nội bộ |
| IdP logout/SSO logout | Có thể ảnh hưởng phiên OP; không đảm bảo authorized client records ở ứng dụng biến mất |
| Refresh Token bị thu hồi | Các lần refresh tiếp theo có thể thất bại; cần xử lý reauthorization/cleanup |
| Access Token bị API từ chối | Có thể do audience, scope hoặc expiration; không tự xóa toàn bộ user session |

Đối với một portal thuần đăng nhập OIDC, việc xóa authorized client khi user logout hay giữ nó để dùng cho tác vụ khác là **quyết định sản phẩm và bảo mật**. Nếu token cho phép truy cập API sau logout, cần thẩm định rõ có hợp pháp/đúng ý người dùng hay không.

**Đừng khẳng định `logout()` mặc định luôn xóa mọi record trong `JdbcOAuth2AuthorizedClientService`.** Muốn xóa phải có chính sách và thao tác xóa/revoke tương ứng.

## 16. Xử lý lỗi: load không có token, refresh thất bại, store không sẵn sàng

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `loadAuthorizedClient(...)` trả null sau login | Sai registration/principal name, khác repository hoặc flow chưa lưu | Kiểm tra store/Authentication/registration, không suy đoán token tồn tại |
| Login ổn trên một instance nhưng request ở instance khác mất token | Chỉ dùng in-memory hoặc session cục bộ | Shared JDBC/session, hoặc routing phù hợp |
| Restart làm mất authorized clients | Store là in-memory | Dùng persistence nếu nghiệp vụ cần sống qua restart |
| `getRefreshToken() == null` | Provider không cấp hoặc grant không hỗ trợ | Tùy flow, yêu cầu lại quyền hoặc cấp token mới |
| Access Token hết hạn | Chưa chạy refresh/re-authorize | Dùng `OAuth2AuthorizedClientManager` với provider đúng |
| Token endpoint trả `invalid_grant` | Refresh Token hết hạn/thu hồi/đã xoay, hoặc code/PKCE có vấn đề | Xác định grant, xử lý theo policy; không retry vô hạn |
| 401 từ API dù token chưa hết hạn theo client | Token bị thu hồi, audience/issuer không đúng | Kiểm tra API resource policy; có thể cần refresh/re-auth |
| 403 từ API | Thiếu scope/role/policy | Xin quyền đúng và kiểm tra Resource Server, không sửa token |
| Token lưu trong JDBC nhưng không đọc được | Schema/serialization/permissions/DB connection lỗi | Kiểm tra migration, datasource, quyền DB và định dạng dữ liệu |
| Refresh thành công nhưng token mới không được lưu | Manager success handler/repository khác nhau | Kiểm tra manager và kho sử dụng, tránh tự ghi đè token cũ |
| Một lần refresh xóa token mới do request khác ghi | Concurrent refresh/rotation | Cân nhắc đồng bộ per-client hoặc optimistic concurrency |
| Logout xong token vẫn ở DB | Logout không tự xóa persistent authorized client | Định nghĩa disconnect/cleanup/revocation theo chính sách |
| User A thấy dữ liệu API của user B | Sai namespace principal hoặc truy vấn store không đủ khóa | Đảm bảo isolation theo registration/principal/tenant, rà soát security boundary |

### 16.1. Debug từng lớp, không nhảy bước

~~~text
API gọi thất bại
  |
  +-- Đúng client registration được chọn chưa?
  |
  +-- Authentication/principalName có đúng user hiện tại?
  |
  +-- loadAuthorizedClient trả bản ghi hay null?
  |
  +-- Access Token có hết hạn / có scope đúng không?
  |
  +-- AuthorizedClientManager có refresh/re-authorize khi cần không?
  |
  +-- Token mới đã được lưu vào cùng repository/service chưa?
  |
  +-- API trả 401 hay 403?
  |
  +-- Token đúng issuer, audience và policy phía Resource Server?
~~~

**Không log giá trị `access_token` hoặc `refresh_token`** để “dễ debug”. Dùng registration ID, mã lỗi, has-refresh-token boolean, thời điểm hết hạn đã được làm tròn/phân loại và correlation ID độc lập với credential.

## 17. Vấn đề bảo mật cần giải quyết trước production

### 17.1. Credential protection

Access Token và đặc biệt Refresh Token là **bí mật có khả năng cấp quyền truy cập**. Khi lưu authorized client:

1. Bảo vệ kho token bằng least privilege; chỉ service phù hợp được đọc.
2. Mã hóa token at rest khi yêu cầu hoặc theo mức độ rủi ro và quản lý encryption key tách biệt.
3. Dùng TLS cho Token Endpoint, database network và downstream APIs.
4. Không đưa token vào browser URL, HTML, localStorage hoặc log nếu kiến trúc là confidential Servlet client.
5. Không ghi raw `OAuth2AuthorizedClient` vào application logs hoặc serialize vào response JSON.
6. Cài thời hạn lưu trữ, cleanup và xóa token khi không còn cần.
7. Theo dõi các thao tác đọc/sửa/xóa token bằng audit metadata an toàn, không ghi secret.

### 17.2. Quyền xóa và truy xuất token

Endpoint xem trạng thái/xóa một integration phải kiểm tra **chính user/tenant đang đăng nhập**. Không tạo API:

~~~http
DELETE /authorized-clients?principalName=someone-else&registrationId=calendar
~~~

rồi xóa token theo input mà không xác thực/ủy quyền. Nếu chức năng admin phải xóa kết nối thay người khác, cần quyền admin được kiểm soát và audit riêng.

### 17.3. Không nhầm ID Token với Access Token

Với OIDC Login:

- **ID Token:** dùng xác minh danh tính tại OIDC client, có issuer/subject/audience và các quy tắc validation.
- **Access Token:** dùng gọi UserInfo hoặc Resource Server được cấp quyền.
- **Refresh Token:** dùng xin token mới tại Token Endpoint, không gửi tới API nghiệp vụ.

Không lưu ID Token vào chỗ Access Token hoặc dùng ID Token làm Bearer cho API chỉ vì cả hai có thể là JWT. `OAuth2AuthorizedClient` là đối tượng lưu **OAuth2 access/refresh token**, không phải kho chung cho mọi chuỗi JWT.

### 17.4. Token còn hiệu lực không đồng nghĩa có toàn quyền

Mỗi Access Token có audience/scope/policy nhất định. Khi client gọi API khác với token được cấp cho UserInfo, API có thể trả 401/403. Không cố giải quyết bằng cách gán role tại portal hoặc bỏ kiểm tra Resource Server.

### 17.5. Không tin metadata không được xác thực

Nếu ứng dụng lưu thêm tenant hoặc user ID bên cạnh `OAuth2AuthorizedClient`, dữ liệu đó phải gắn với `Authentication` và issuer/subject đã xác minh, không lấy trực tiếp từ query parameter hoặc claim chưa được kiểm tra. Một lỗi namespace có thể nghiêm trọng hơn lỗi hết hạn token vì dẫn đến rò rỉ dữ liệu giữa người dùng.

## 18. Kiểm thử hành vi lưu, tải, cập nhật và xóa

Một bộ test nên tách **logic lưu trữ** khỏi **token endpoint exchange**.

### 18.1. Unit test Service với InMemory implementation

Ví dụ minh họa tạo authorized client **chỉ dùng token giả cho test**, không dùng ngoài môi trường test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

class AuthorizedClientStorageTest {

    @Test
    void saveLoadReplaceAndRemove() {
        ClientRegistration registration = ClientRegistration
            .withRegistrationId("calendar")
            .clientId("test-client")
            .clientSecret("test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .authorizationUri("https://id.example.com/authorize")
            .tokenUri("https://id.example.com/token")
            .userInfoUri("https://id.example.com/userinfo")
            .userNameAttributeName("sub")
            .build();

        var registrations =
            new InMemoryClientRegistrationRepository(registration);
        var service =
            new InMemoryOAuth2AuthorizedClientService(registrations);

        Instant now = Instant.now();
        OAuth2AccessToken token1 = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "TEST_TOKEN_1",
            now,
            now.plusSeconds(300),
            Set.of("calendar.read"));

        OAuth2AuthorizedClient first =
            new OAuth2AuthorizedClient(registration, "user-1", token1);
        service.saveAuthorizedClient(first, "user-1");

        OAuth2AuthorizedClient loaded =
            service.loadAuthorizedClient("calendar", "user-1");
        assertNotNull(loaded);
        assertEquals("TEST_TOKEN_1", loaded.getAccessToken().getTokenValue());
        assertNull(service.loadAuthorizedClient("calendar", "user-2"));

        OAuth2AccessToken token2 = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "TEST_TOKEN_2",
            now,
            now.plusSeconds(600),
            Set.of("calendar.read"));
        OAuth2AuthorizedClient updated =
            new OAuth2AuthorizedClient(registration, "user-1", token2);
        service.saveAuthorizedClient(updated, "user-1");

        assertEquals(
            "TEST_TOKEN_2",
            service.loadAuthorizedClient("calendar", "user-1")
                .getAccessToken().getTokenValue());

        service.removeAuthorizedClient("calendar", "user-1");
        assertNull(service.loadAuthorizedClient("calendar", "user-1"));
    }
}
~~~

Test này kiểm tra **hợp đồng lưu trữ trong memory**: save → load → thay bản ghi cùng khóa → remove. Nó **không thực hiện OAuth2 Authorization Code, không xác minh OIDC token và không chứng minh Token Endpoint refresh hoạt động**.

### 18.2. Test ở cấp tích hợp

| Tình huống | Mục tiêu |
| --- | --- |
| Login OAuth2/OIDC thành công | Authorized client được lưu bằng repository/service đang cấu hình |
| User A và B cùng dùng registration | Không trả token của A cho B |
| User có hai registrations | Xóa registration A không làm mất B |
| Restart một instance dùng JDBC | Bản ghi vẫn tồn tại nếu DB còn dữ liệu |
| Hai instances cùng dùng JDBC | Client đã lưu được tải từ instance khác |
| Access Token hết hạn, có Refresh Token hợp lệ | Manager refresh và cập nhật authorized client đúng khóa |
| Refresh Token bị thu hồi | Xử lý thất bại/re-authorize theo policy, không retry vô hạn |
| Refresh rotation đồng thời | Không để token cũ ghi đè token mới |
| Disconnect integration | Local record được xóa và revocation được xử lý đúng contract |
| Logout ứng dụng | Kiểm tra policy giữ/xóa authorized clients thực tế |
| HTTP POST disconnect thiếu CSRF token | Request bị từ chối theo chính sách CSRF |
| Người dùng đoán registration ID không được phép | Không thể thao tác unauthorized clients ngoài quyền của mình |

Không dùng mock `OAuth2AuthorizedClient` để kết luận ID Token validation hoặc grant refresh đã đúng; đó là những lớp test khác.

## 19. Các tình huống thực tế

### Tình huống A — Sau login muốn gọi API

Người dùng đăng nhập portal qua OIDC registration `company`. Ứng dụng cần gọi API hồ sơ được phép.

**Cách làm:** để Spring Security lưu authorized client sau login; tải bằng `OAuth2AuthorizedClientRepository` hoặc dùng manager để có token phù hợp; chỉ dùng Access Token để gọi endpoint cho phép. Không đọc ID Token rồi dùng làm Access Token.

### Tình huống B — Không thấy token sau khi reload trang

`loadAuthorizedClient("company", authentication, request)` trả `null` sau khi browser reload.

**Cách tìm:** kiểm tra người dùng/Authentication có đổi không, registration ID có đúng không, repository/service có giống lúc login không, session có bị mất hay không. Không tự tạo token mới từ tham số browser.

### Tình huống C — Token còn trong DB nhưng không gọi được API

JDBC service tìm thấy Access Token, nhưng API trả 401.

**Cách làm:** kiểm tra token expiry, revocation, audience/resource và scope. Nếu cần refresh, sử dụng manager đã cấu hình; đừng cho rằng “đã lưu” đồng nghĩa “còn hiệu lực”.

### Tình huống D — User bấm “Ngắt kết nối”

Người dùng đã cấp quyền lịch, sau đó muốn dừng đồng bộ.

**Cách làm:** gọi revocation endpoint nếu được hỗ trợ và phù hợp, xóa authorized client đúng `registrationId + principalName`, đánh dấu integration chưa kết nối. Không tự coi việc xóa local record là IdP logout.

### Tình huống E — Một scheduled job cần token service-level

Backend job gọi API báo cáo bằng Client Credentials, không có browser session.

**Cách làm:** dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` cùng `OAuth2AuthorizedClientService`. Gắn token với principal key có namespace rõ ràng cho service, không dùng repository yêu cầu Servlet request.

### Tình huống F — User đổi email

Ứng dụng trước đây lưu token theo email. Khi user đổi email, bản ghi cũ không còn truy xuất được.

**Cách làm:** thiết kế khóa principal ổn định theo nguồn định danh tin cậy, với OIDC chú ý `iss + sub`; nếu cần migration phải đối chiếu account thật, không scan token theo email gần giống.

### Tình huống G — User bị gỡ quyền API ở provider

Access Token vẫn còn trong JDBC nhưng provider/Resource Server đã thu hồi quyền, API trả 403 hoặc token bị từ chối.

**Cách làm:** không cấp thêm scope/role tại ứng dụng để bypass; xử lý thiếu quyền, yêu cầu authorization lại khi thích hợp, hoặc xóa liên kết theo policy.

### Tình huống H — Hai request refresh cùng lúc

Provider xoay Refresh Token. Request A refresh thành công, request B dùng Refresh Token cũ nên gặp `invalid_grant`.

**Cách làm:** tránh refresh cạnh tranh bằng cơ chế có scope per-client khi cần, bảo vệ ghi token mới và xử lý lỗi không xóa nhầm bản ghi mới.

### Tình huống I — Logout portal nhưng token integration vẫn tồn tại

Ứng dụng lưu authorized client trong JDBC và người dùng bấm logout. Sau login mới, integration có thể vẫn hiện “Đã kết nối”.

**Cách làm:** đây có thể là hành vi chủ đích của tính năng kết nối lâu dài hoặc là rủi ro quyền riêng tư. Sản phẩm phải quyết định có giữ token qua logout hay không, hỗ trợ disconnect/revoke và công bố hành vi phù hợp.

## 20. Tài liệu tham khảo

- Spring Security — Servlet OAuth 2.0 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Core Interfaces and Classes, Authorized Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — OAuth2AuthorizedClient Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html
- Spring Security — OAuth2AuthorizedClientService Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html
- Spring Security — OAuth2AuthorizedClientRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizedClientRepository.html
- Spring Security — OAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — JdbcOAuth2AuthorizedClientService Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/JdbcOAuth2AuthorizedClientService.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Token Revocation (RFC 7009): https://www.rfc-editor.org/rfc/rfc7009
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700

## 21. Ghi nhớ: CRUD và quản lý token là hai tầng khác nhau

~~~text
OAuth2/OIDC Authorization thành công
  -> OAuth2AuthorizedClient
       ClientRegistration
       principalName
       accessToken
       refreshToken (nếu có)
  |
  +-- LƯU
  |     OAuth2AuthorizedClientRepository.saveAuthorizedClient(...)
  |     OAuth2AuthorizedClientService.saveAuthorizedClient(...)
  |
  +-- TẢI
  |     repository.loadAuthorizedClient(registrationId, auth, request)
  |     service.loadAuthorizedClient(registrationId, principalName)
  |
  +-- CẬP NHẬT
  |     Manager dùng grant phù hợp để xin/refresh token
  |     -> lưu authorized client mới vào đúng khóa
  |
  +-- XÓA
        repository.removeAuthorizedClient(...)
        service.removeAuthorizedClient(...)
        -> token có thể cần revoke riêng tại provider

Lưu trữ != refresh token
Xóa local record != revoke token tại provider
Logout browser != tự động xóa mọi persistent authorized client
Có token trong store != token hợp lệ cho mọi Resource Server
~~~

**Bốn thao tác cần nắm vững:** **save** bảo toàn kết quả ủy quyền cho đúng principal, **load** tìm lại token theo registration/principal, **update** lưu bộ token mới sau grant hợp lệ, và **remove** xóa dữ liệu client khi ngắt kết nối. Spring Security hỗ trợ các abstraction để thực hiện từng trách nhiệm; chọn **repository cho ngữ cảnh Servlet**, **service cho kho bền vững/ngoài HTTP request**, và **authorized client manager cho logic cấp mới/refresh**. Luôn bảo vệ credential, phân biệt danh tính người dùng với client, và thiết kế rõ ràng việc thu hồi quyền cũng như vòng đời token.
