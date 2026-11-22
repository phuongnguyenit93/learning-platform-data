# 14.6. HttpSessionOAuth2AuthorizedClientRepository và dữ liệu theo phiên

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 Client**, đối tượng `OAuth2AuthorizedClient` đại diện cho một client đã được cấp quyền, chứa **access token** và có thể có **refresh token**. Ứng dụng cần lưu trạng thái đó để dùng token ở các request sau khi người dùng hoàn tất OAuth 2.0 hoặc OpenID Connect (OIDC) Login.

`HttpSessionOAuth2AuthorizedClientRepository` là implementation của `OAuth2AuthorizedClientRepository` lưu authorized client trong **`HttpSession` của ứng dụng Servlet**. Cách lưu này giúp gắn token với phiên trình duyệt, nhưng không tự động bảo đảm mọi token được cách ly theo principal khi một phiên bị tái sử dụng để đổi tài khoản.

Sau bài học, bạn có thể:

- Giải thích vai trò của `HttpSessionOAuth2AuthorizedClientRepository` và các contract `loadAuthorizedClient`, `saveAuthorizedClient`, `removeAuthorizedClient`.
- Phân biệt nơi lưu `OAuth2AuthorizedClient`, `SecurityContext` và `OAuth2AuthorizationRequest` đang chờ callback.
- Hiểu sự khác nhau giữa lưu **theo phiên** và lưu **theo principal**, cũng như vai trò của `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`.
- Cấu hình Spring Security OAuth2 Login/Client và đọc authorized client trong controller.
- Phân biệt **access token**, **refresh token** và **ID token** trong một phiên OIDC.
- Nhận diện rủi ro đổi tài khoản, nhiều tab, hết session, nhiều instance và refresh token đồng thời.
- Thiết kế cleanup, logout, token refresh và bảo vệ session store phù hợp.

## 1. Bối cảnh: sau OIDC Login, access token ở đâu?

Giả sử có **Customer Portal** viết bằng Spring Boot. Portal cho khách hàng đăng nhập với một OpenID Provider (OP) của doanh nghiệp và gọi **Orders API** để lấy đơn hàng.

Luồng tổng quát:

1. Browser truy cập `/orders` nhưng chưa đăng nhập.
2. Spring Security khởi tạo OIDC Authorization Code flow.
3. OP xác thực người dùng và chuyển browser về callback.
4. Portal đổi authorization code lấy token.
5. Portal xác minh ID token, tạo `OidcUser` và `Authentication`.
6. Portal lưu kết quả đăng nhập và trạng thái authorized client theo repository/service được cấu hình.
7. Request tiếp theo đến `/orders` có thể dùng access token đã cấp để gọi Orders API.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant P as Spring Boot Portal
    participant OP as OpenID Provider
    participant API as Orders API
    U->>B: Mở /orders
    B->>P: HTTP request
    P-->>B: Redirect tới OP
    B->>OP: OIDC Authorization Request
    OP->>U: Xác thực/consent khi cần
    OP-->>B: Redirect authorization code
    B->>P: Callback code và state
    P->>OP: Đổi code lấy token
    OP-->>P: ID token + access token
    Note over P: Xác minh OIDC, lưu Authentication và authorized client
    P-->>B: Session cookie / redirect
    B->>P: Request /orders tiếp theo
    Note over P: Tải Authentication và authorized client
    P->>API: Bearer ACCESS_TOKEN
    API-->>P: Các đơn hàng được phép đọc
    P-->>B: Nội dung trang
~~~

Kết quả login gồm **hai loại trạng thái riêng**:

- **Authentication/SecurityContext**: ai đang đăng nhập tại Portal?
- **OAuth2AuthorizedClient**: client đã được cấp token nào để gọi API?

Chúng có thể đều liên quan đến session, nhưng không phải cùng một đối tượng.

## 2. Các thành phần chính

| Thành phần | Vai trò | Chứa gì? |
|---|---|---|
| `ClientRegistration` | Cấu hình client và provider | Client ID, grant type, redirect URI, scopes, token endpoint |
| `OAuth2AuthorizedClient` | Kết quả một client được cấp quyền | Registration, principal name, access token, refresh token nếu có |
| `OAuth2AuthorizedClientRepository` | Lưu/đọc/xóa authorized client trong ngữ cảnh request Servlet | Phụ thuộc implementation |
| `OAuth2AuthorizedClientService` | Lưu/đọc/xóa authorized client theo registration ID và tên principal | Kho memory, database hoặc custom |
| `OAuth2AuthorizedClientManager` | Điều phối việc authorize/reauthorize, dùng lại/refresh token | Phối hợp registration, authorized client, provider |
| `SecurityContextRepository` | Lưu/khôi phục Authentication | `SecurityContext` và principal |
| `OAuth2AuthorizationRequestRepository` | Lưu dữ liệu authorization request chờ callback | `state`, redirect URI, nonce/PKCE khi áp dụng |

### 2.1. `ClientRegistration` không chứa token của người dùng

Ví dụ một registration:

~~~text
registrationId: corporate
clientId: portal-web
authorizationGrantType: authorization_code
scope: openid profile orders.read
provider: company-oidc
~~~

Đối tượng này có trước khi Alice hay Bob đăng nhập. Nó chỉ mô tả client.

Một authorized client được cấp cho Alice có cấu trúc khái niệm:

~~~text
OAuth2AuthorizedClient
├── clientRegistration: corporate
├── principalName: Alice
├── accessToken: ...
└── refreshToken: ... (nếu OP cấp)
~~~

Cùng một registration có thể được sử dụng bởi nhiều principal, mỗi người có token/ủy quyền khác nhau. Việc lưu trữ phải duy trì đúng sự cách ly đó.

### 2.2. `OAuth2AuthorizedClient` không phải `OidcUser`

`OidcUser` là principal sau OIDC Login, thường có ID token, UserInfo và claims. `OAuth2AuthorizedClient` chứa access token phục vụ API và có thể refresh token.

**Không dùng `OidcUser.getIdToken().getTokenValue()` làm bearer token gọi Resource Server.** API cần access token được cấp cho audience/scope phù hợp.

### 2.3. Tên principal có ý nghĩa thế nào?

`OAuth2AuthorizedClient.getPrincipalName()` mô tả principal liên quan tới lần ủy quyền.

Tuy nhiên, một field tên principal trong object **không có nghĩa mọi repository dùng nó làm khóa lưu**. Repository theo session và service theo principal có hành vi định vị khác nhau, được giải thích ở các phần sau.

## 3. `HttpSessionOAuth2AuthorizedClientRepository` là gì?

Lớp nằm trong package:

~~~java
org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizedClientRepository
~~~

Nó triển khai:

~~~java
org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository
~~~

Chức năng là giữ `OAuth2AuthorizedClient` trong `HttpSession` của request web Servlet.

### 3.1. Browser không cầm toàn bộ authorized client

Trong mô hình Servlet session-based:

~~~text
Browser
  Cookie: JSESSIONID=SESSION_A
                  |
                  v
          Session store của Portal
          HttpSession SESSION_A
          ├── SecurityContext nếu có
          ├── Authorization Request chờ callback nếu có
          └── Authorized clients nếu dùng session repository
              ├── corporate -> OAuth2AuthorizedClient
              └── partner   -> OAuth2AuthorizedClient
~~~

Đây là sơ đồ khái niệm, không phải các tên attribute chính xác của Spring Security.

Thông thường browser chỉ giữ **session identifier** bằng cookie. Access token/refresh token nằm phía server khi repository sử dụng HttpSession. Tuy vậy, **session cookie vẫn là credential nhạy cảm**: nếu bị chiếm, bên khác có thể cố chiếm phiên và hưởng quyền được gắn với phiên.

### 3.2. Phạm vi session khác phạm vi principal

`HttpSessionOAuth2AuthorizedClientRepository` tập trung vào **dữ liệu theo HttpSession**. Trong implementation thông dụng, các authorized client được lưu/tra theo **registration ID trong session**, không phải một kho token toàn cục có khóa bắt buộc là issuer + subject.

Hệ quả:

- Hai browser có hai session độc lập có thể giữ authorized client khác nhau.
- Hai tab cùng browser thường chia sẻ session và authorized client.
- Cùng session có thể giữ token cho nhiều registration ID.
- Nếu user A và user B đăng nhập luân phiên trong **cùng session chưa được dọn đúng**, token cũ có thể bị tái sử dụng sai.

**Không xem session scope là sự bảo đảm tuyệt đối về principal ownership.** Khi chuyển tài khoản hoặc có nhiều tenant, ứng dụng vẫn cần kiểm tra ràng buộc danh tính và dọn trạng thái không còn hợp lệ.

### 3.3. Không đọc trực tiếp attribute nội bộ của session

Tránh cách này:

~~~java
Object tokenStore = session.getAttribute("SPRING_SOME_INTERNAL_KEY");
~~~

Tên attribute và cấu trúc lưu có thể thay đổi theo phiên bản/implementation. Sử dụng `OAuth2AuthorizedClientRepository`, `OAuth2AuthorizedClientService` hoặc các integration Spring Security đã cung cấp thay vì phụ thuộc vào session internals.

## 4. Contract của `OAuth2AuthorizedClientRepository`

Interface có ba thao tác chính:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

// Các phương thức chính trong OAuth2AuthorizedClientRepository:

<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
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
~~~

*Đây là tập chữ ký để giải thích API; không phải một class Java hoàn chỉnh.*

### 4.1. `loadAuthorizedClient`

Ví dụ:

~~~java
OAuth2AuthorizedClient authorizedClient =
        repository.loadAuthorizedClient(
                "corporate",
                authentication,
                request);
~~~

Nếu không có authorized client phù hợp, kết quả có thể là `null`.

Nguyên nhân:

- Chưa hoàn thành authorization cho registration đó.
- Session không tồn tại hoặc hết hạn.
- Repository đang dùng để đọc khác với repository đã lưu.
- Registration ID khác nhau giữa login và gọi API.
- Client đã bị xóa theo chính sách.
- Service principal-aware không tìm được bản ghi của principal hiện tại.

Không tự lấy ID token làm token dự phòng khi repository trả `null`.

### 4.2. `saveAuthorizedClient`

Ví dụ:

~~~java
repository.saveAuthorizedClient(
        authorizedClient,
        authentication,
        request,
        response);
~~~

Với `HttpSessionOAuth2AuthorizedClientRepository`, trạng thái authorized client được lưu trong HttpSession.

Token có thể chứa bí mật có giá trị lâu dài như refresh token, nên:

- Chỉ lưu authorized client đã được framework/AS xác lập hợp lệ.
- Không chấp nhận một object token do browser tự khai báo làm authorized client hợp lệ.
- Không dump toàn bộ authorized client vào log.
- Xác định rõ repository có thể tạo session khi cần và dữ liệu nào nằm trong đó.
- Bảo vệ kho session như một nơi lưu credential.

### 4.3. `removeAuthorizedClient`

Ví dụ:

~~~java
repository.removeAuthorizedClient(
        "corporate",
        authentication,
        request,
        response);
~~~

Thao tác này xóa authorized client **ở kho lưu cục bộ** theo implementation đang dùng.

Nó **không đồng nghĩa**:

- Thu hồi token tại Authorization Server.
- Hủy `SecurityContext` hoặc logout Portal.
- Chấm dứt phiên SSO của OP.
- Làm mất hiệu lực access token đã cấp và đang được Resource Server chấp nhận.

Đây là những trách nhiệm tách biệt và có cơ chế riêng.

## 5. Ba loại repository cùng có thể liên quan tới HttpSession

Tên các lớp giống nhau dễ gây nhầm:

| Lớp/abstraction | Dữ liệu | Thời điểm |
|---|---|---|
| `HttpSessionOAuth2AuthorizationRequestRepository` | Authorization Request gốc, `state`, nonce/PKCE khi dùng | **Trước** callback |
| `HttpSessionSecurityContextRepository` | `SecurityContext`, `Authentication` | **Sau** khi xác thực hoặc khi cần khôi phục session |
| `HttpSessionOAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClient` chứa access/refresh token | **Sau** khi được cấp quyền |

### 5.1. Authorization Request chưa phải authorized client

Khi browser bắt đầu login, Spring Security tạo Authorization Request. Dữ liệu đó giúp so khớp callback:

~~~text
Pending Authorization Request:
  state=STATE_A
  clientRegistration=corporate
  redirectUri=...
  nonce=... (khi dùng)
  code_verifier=... (khi dùng PKCE)
~~~

Lúc này chưa có token được cấp. Sau callback và token exchange thành công, `OAuth2AuthorizedClient` mới có thể được lưu.

Hai class rất dễ nhầm:

~~~text
HttpSessionOAuth2AuthorizationRequestRepository
HttpSessionOAuth2AuthorizedClientRepository
~~~

Tên thứ nhất có **AuthorizationRequest**, tên thứ hai có **AuthorizedClient**. Chúng không thay thế nhau.

### 5.2. SecurityContext cho biết ai đăng nhập

Sau OIDC Login:

~~~text
SecurityContext
└── OAuth2AuthenticationToken
    ├── principal: OidcUser
    ├── authorities: [...]
    └── authenticated: true
~~~

Đây là thông tin authentication của Portal. Nó không nhất thiết chứa access token dành cho Orders API trong cùng một object.

### 5.3. Có session không chứng minh có token

Một đoạn code:

~~~java
HttpSession session = request.getSession(false);
boolean hasSession = session != null;
~~~

chỉ cho biết session tồn tại. Session có thể đã được tạo trước login để lưu `state`, request cache hoặc CSRF token.

Không suy luận:

~~~text
HttpSession có
  => User đã đăng nhập
  => OAuth2AuthorizedClient có
  => Access token chưa hết hạn
  => API cho phép mọi thao tác
~~~

Mỗi điều kiện cần cơ chế xác minh riêng.

## 6. Vai trò của `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`

Một class rất quan trọng khác là:

~~~java
org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository
~~~

Nó cho phép phối hợp:

1. Với **principal được xem là authenticated**, sử dụng `OAuth2AuthorizedClientService`.
2. Với ngữ cảnh **anonymous/chưa authenticated**, ủy quyền cho một `OAuth2AuthorizedClientRepository` phụ, thường mặc định là `HttpSessionOAuth2AuthorizedClientRepository`.

~~~mermaid
flowchart TD
    A["Authorized client load/save/remove"] --> B{"Principal authenticated?"}
    B -->|Có| C["OAuth2AuthorizedClientService"]
    C --> D["registrationId + principalName"]
    B -->|Không| E["Anonymous authorized client repository"]
    E --> F["HttpSessionOAuth2AuthorizedClientRepository thường dùng"]
~~~

Đây là lý do session repository có thể xuất hiện như một phần của cấu hình mặc định hoặc cấu hình kết hợp mà ứng dụng không trực tiếp tạo một bean session repository.

### 6.1. Vì sao dùng service theo principal?

`OAuth2AuthorizedClientService` dùng khóa registration ID + tên principal.

Điều đó có ích khi:

- Token cần được quản lý theo người dùng đã xác thực.
- Ứng dụng muốn truy xuất authorized client không phụ thuộc hoàn toàn vào một browser session.
- Cần lưu token ở memory hoặc database với lifecycle riêng.
- Có nhiều request/instance cần truy cập theo một identity đã được xác định.

Nhưng **principal name phải được thiết kế đúng**. Với nhiều OIDC issuer, không nên dùng mỗi email hoặc mỗi `sub` như khóa toàn cục nếu có thể trùng nhau. Nên xác định cách liên kết issuer + subject hoặc internal user ID đáng tin cậy.

### 6.2. Vì sao anonymous có thể dùng session?

Trong một số flow client authorization, ứng dụng có thể chưa có principal được xác thực theo mô hình web. Session giúp liên kết trạng thái authorized client với browser/ngữ cảnh request mà không có khóa principal rõ ràng.

Nhưng điều đó không có nghĩa mọi flow OAuth đều cần HttpSession.

Ví dụ **`client_credentials` cho background job** không có browser/HttpServletRequest thông thường nên sử dụng một manager/service và principal đại diện cho client/service theo cấu hình, thay vì phụ thuộc một session của user bất kỳ.

### 6.3. Không mặc định một repository cho mọi phiên bản/cấu hình

Trong Spring Boot/Spring Security, auto-configuration có thể tạo repository và service khi các điều kiện bean thỏa mãn. Nếu ứng dụng tự cung cấp bean hoặc custom config, lựa chọn thực tế có thể thay đổi.

Bởi vậy khi nghiên cứu một dự án, điều quan trọng là **repository nào thực sự được sử dụng khi login/save và khi API lookup**, không chỉ là sự tồn tại của một class trên classpath.

## 7. Cấu hình OIDC Client cho Servlet application

### 7.1. Dependency

Với Spring Boot Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

### 7.2. Client registration

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

Ở đây:

- `corporate` là registration ID của Spring.
- `client-id` và secret là thông tin đã được OP cấp.
- `authorization_code` sử dụng browser redirect và callback.
- `openid` yêu cầu OIDC Login.
- `orders.read` chỉ là scope API minh họa; AS và Orders API phải hỗ trợ.
- `issuer-uri` là issuer tin cậy cho provider metadata.

Giá trị secret đến từ biến môi trường/secret manager; không commit secret thật.

### 7.3. Security filter chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

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

`oauth2Login()` xử lý OAuth2/OIDC Login, còn `oauth2Client()` bật hỗ trợ sử dụng authorized client trong request ra bên ngoài theo cấu hình.

Thông thường không cần tự khai báo `HttpSessionOAuth2AuthorizedClientRepository` nếu wiring mặc định của Spring Security đã đáp ứng nhu cầu.

## 8. Chủ động cấu hình repository theo session

Nếu ứng dụng muốn toàn bộ authorized client trong Servlet flow dùng một session repository, có thể tạo bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class SessionAuthorizedClientConfiguration {

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository() {
        return new HttpSessionOAuth2AuthorizedClientRepository();
    }
}
~~~

Khi cần dùng rõ repository này trong các extension point của security configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ExplicitRepositorySecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2AuthorizedClientRepository repository)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(login -> login
                        .authorizedClientRepository(repository))
                .oauth2Client(client -> client
                        .authorizedClientRepository(repository))
                .build();
    }
}
~~~

Hai ví dụ được ghép trong một dự án minh họa; không cần tạo hai `SecurityFilterChain` khác nhau.

**Cẩn trọng:** cách này gắn token với HttpSession. Nếu cùng session dùng để đổi từ Alice sang Bob, cần bảo đảm xóa token cũ, ràng buộc principal hoặc lựa chọn repository theo principal thích hợp. Đừng chọn session repository chỉ vì tên class có chữ HttpSession.

## 9. Cấu hình repository kết hợp authenticated principal + anonymous

Một cách khác là dùng `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class PrincipalAwareClientConfig {

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository(
            OAuth2AuthorizedClientService service) {

        return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
                service);
    }
}
~~~

Với authenticated principal, repository này dùng `OAuth2AuthorizedClientService`. Với anonymous, nó có repository phụ theo cơ chế mặc định.

Cách kết hợp giúp mô hình lưu token theo principal rõ hơn cho người dùng đã đăng nhập. Tuy nhiên, nó có những hệ quả cần cân nhắc:

- Token có thể tồn tại ngoài vòng đời của một HttpSession nếu service lưu độc lập.
- Logout cục bộ không tự động xóa mọi record ở service.
- Cần thiết kế revocation và cleanup theo principal khi muốn ngắt kết nối provider.
- Nếu principal key không đủ phân biệt issuer/tenant, có nguy cơ trộn tài khoản.

Không tự khai báo bean này nếu dự án đã được auto-configure theo đúng yêu cầu, vì override bean có thể thay đổi hành vi lưu trữ.

## 10. Đọc authorized client trong controller

### 10.1. Dùng `@RegisteredOAuth2AuthorizedClient`

Spring Security có annotation:

~~~java
org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient
~~~

Ví dụ:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ClientStatusController {

    @GetMapping("/client-status")
    ClientStatus status(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        if (client == null) {
            return new ClientStatus("corporate", false, null);
        }

        return new ClientStatus(
                client.getClientRegistration().getRegistrationId(),
                client.getAccessToken() != null,
                client.getAccessToken() != null
                        ? client.getAccessToken().getExpiresAt()
                        : null);
    }

    record ClientStatus(
            String registrationId,
            boolean accessTokenPresent,
            Instant accessTokenExpiry) {}
}
~~~

Đoạn code chỉ trả metadata đơn giản; **không trả token thô**.

Trong hệ thống thật, cần kiểm tra authorized client đã được cấp theo registration/principal phù hợp và dùng manager/provider khi cần refresh. Việc annotation trả client phụ thuộc vào cấu hình authorized client resolution của dự án.

### 10.2. Dùng repository trực tiếp

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.stereotype.Service;

@Service
public class AuthorizedClientLookup {

    private final OAuth2AuthorizedClientRepository repository;

    public AuthorizedClientLookup(
            OAuth2AuthorizedClientRepository repository) {
        this.repository = repository;
    }

    public OAuth2AuthorizedClient find(
            String registrationId,
            Authentication authentication,
            HttpServletRequest request) {

        return repository.loadAuthorizedClient(
                registrationId,
                authentication,
                request);
    }
}
~~~

Cách này cho phép truy vấn repository trong một HTTP request cụ thể.

Không đưa toàn bộ `OAuth2AuthorizedClient` vào JSON response hoặc log, vì nó chứa access token và có thể refresh token.

## 11. Gọi Resource Server bằng access token

Sau OIDC Login:

- `OidcUser.getIdToken()` cung cấp ID token dành cho RP.
- `OAuth2AuthorizedClient.getAccessToken()` cung cấp access token dành cho API theo quyền được cấp.

Ví dụ dùng Spring Framework 6.1+ `RestClient`:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersController {

    private final RestClient ordersApi =
            RestClient.create("https://orders-api.example.com");

    @GetMapping("/orders")
    String orders(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        if (client == null || client.getAccessToken() == null) {
            throw new IllegalStateException("No access token available");
        }

        String token = client.getAccessToken().getTokenValue();

        return ordersApi.get()
                .uri("/api/orders")
                .headers(headers -> headers.setBearerAuth(token))
                .retrieve()
                .body(String.class);
    }
}
~~~

Mục đích của ví dụ là chỉ ra **token phải được lấy từ authorized client**, không phải từ ID token.

Đây chưa phải mẫu hoàn chỉnh cho production: cần kiểm tra token còn hiệu lực, scope/audience, reauthorization/refresh, retry policy và lỗi từ API.

Trong thực tế, nên cân nhắc tích hợp OAuth2 với HTTP client hoặc `OAuth2AuthorizedClientManager` để tập trung quản lý token. Resource Server phải tự xác minh token và quyền.

### 11.1. Session có token không đảm bảo API sẽ chấp nhận

Một access token tồn tại trong session có thể:

- Đã hết hạn.
- Đã bị thu hồi.
- Có audience dành cho API khác.
- Không có scope `orders.read`.
- Thuộc một tenant khác.
- Không còn phù hợp với account hiện tại sau khi đổi user.

Không gửi token chỉ vì registration ID trùng; phải áp chính sách xác thực và phân quyền ở cả client và Resource Server.

## 12. Session timeout, access token và refresh token

### 12.1. Ba vòng đời khác nhau

Ví dụ:

~~~text
HttpSession idle timeout:    30 phút
Access token expires in:    10 phút
Refresh token expires in:   2 giờ, nếu được cấp
OP SSO session:              theo chính sách OP
~~~

Những mốc trên chỉ để minh họa.

Các kết luận đúng:

- **Session còn sống** không có nghĩa access token chưa hết hạn.
- **Access token còn sống** không có nghĩa session Portal vẫn còn.
- **ID token hết hạn** không tự làm HttpSession biến mất trong mọi cấu hình.
- **OP SSO còn sống** không có nghĩa Portal còn Authentication cục bộ.
- **Refresh token tồn tại** không bảo đảm việc refresh luôn thành công.

### 12.2. Repository không tự refresh token

`HttpSessionOAuth2AuthorizedClientRepository` chỉ làm nhiệm vụ **save/load/remove**.

Việc xin token mới thuộc cơ chế như `OAuth2AuthorizedClientManager` phối hợp các `OAuth2AuthorizedClientProvider`.

~~~mermaid
flowchart TD
    A["Ứng dụng cần gọi API"] --> B["AuthorizedClientManager"]
    B --> C["Tìm authorized client trong repository"]
    C --> D{"Token còn đủ điều kiện sử dụng?"}
    D -->|Có| E["Gọi API bằng access token"]
    D -->|Không| F{"Có thể reauthorize/refresh?"}
    F -->|Có| G["Xin token mới từ AS"]
    G --> H["Lưu authorized client đã cập nhật"]
    H --> E
    F -->|Không| I["Yêu cầu flow mới hoặc báo lỗi"]
~~~

Sơ đồ mô tả vai trò khái niệm; cách refresh thực tế còn phụ thuộc grant, token policy và manager configuration.

### 12.3. Refresh token là dữ liệu đặc biệt nhạy cảm

Nếu authorized client chứa refresh token, lưu object trong HttpSession cũng đồng nghĩa session store có credential có thể được dùng xin thêm access token.

Cần bảo vệ:

- Session store và backup của nó.
- Kết nối ứng dụng với kho lưu session.
- Quyền truy cập vận hành.
- TTL, cleanup và encryption phù hợp.
- Log/tracing/debug dump để tránh lộ token.

Không coi token lưu server-side là tự động an toàn nếu kho session cho phép nhiều dịch vụ hoặc người vận hành đọc dữ liệu thô không cần thiết.

### 12.4. Concurrent refresh token

Khi hai HTTP request cùng thấy access token sắp hết hạn, cả hai có thể thử refresh. Nếu AS sử dụng refresh token rotation, có thể có race:

~~~text
Request A thấy refresh token R1
Request B thấy refresh token R1
A dùng R1 -> nhận R2
B dùng R1 -> bị từ chối hoặc kích hoạt policy reuse
~~~

Repository theo session không tự cung cấp cơ chế điều phối refresh token an toàn trên mọi node.

Nếu ứng dụng yêu cầu mức đồng thời cao, cần thiết kế refresh coordination/update policy theo manager, kho token và quy tắc của Authorization Server.

## 13. Đổi tài khoản trong cùng session: tình huống cần cẩn trọng

### 13.1. Ví dụ nhầm token

Giả sử Portal cho phép dùng nút “Đổi tài khoản” nhưng không tạo session mới hoặc không dọn token.

~~~text
Trước:
HttpSession S
  SecurityContext -> Alice
  corporate authorized client -> access token Alice

Sau khi Bob đăng nhập cùng session S:
HttpSession S
  SecurityContext -> Bob
  corporate authorized client -> token Alice vẫn còn
~~~

Nếu ứng dụng dùng `HttpSessionOAuth2AuthorizedClientRepository` và chỉ lấy authorized client theo registration ID `corporate`, có nguy cơ request của Bob gọi API bằng token Alice.

Đây là một hệ quả quan trọng của **session scope không tự đồng nghĩa principal scope**.

### 13.2. Cách tránh

Khi có chuyển account, cần:

1. Định danh user mới theo issuer + subject trong ID token đã kiểm tra.
2. Đảm bảo session/authentication được thay thế nhất quán.
3. Loại bỏ authorized client không thuộc principal mới.
4. Không dùng cache/DTO nghiệp vụ còn từ user cũ.
5. Nếu dùng service, bảo đảm principal key thực sự duy nhất và phân biệt tenant/issuer.
6. Áp authorization tại API theo tài khoản và tài nguyên cụ thể.

Không coi `login_hint` hoặc email do browser gửi là bằng chứng user mới.

### 13.3. Không sửa bằng cách dùng token mới nhất toàn cục

Một biến như:

~~~java
public static String lastAccessToken;
~~~

là sai cho ứng dụng nhiều người dùng: tất cả request có thể dùng token của người cập nhật gần nhất.

Dùng repository/service được thiết kế phù hợp, không lưu credential của user trong singleton mutable field.

## 14. Nhiều registration và nhiều tab

### 14.1. Nhiều registration trong một phiên

Một application có thể có:

~~~text
corporate: đăng nhập OIDC doanh nghiệp
partner: gọi API đối tác
billing: dùng một provider khác
~~~

Một HttpSession repository có thể giữ các authorized client tương ứng theo registration ID trong phiên.

Việc một user có token cho `corporate` không đồng nghĩa token đó phù hợp với `billing` hoặc `partner`. Mỗi token có issuer/audience/scope riêng.

### 14.2. Hai tab dùng cùng phiên

Hai tab trong cùng browser profile thường gửi cùng session cookie. Do đó chúng có thể cùng sử dụng authorized client đã lưu trong HttpSession.

Nếu tab A refresh token, tab B có thể đang dùng một object cũ tại thời điểm xử lý. Đây là vấn đề concurrency/lifecycle, không phải mỗi tab có kho token riêng.

Khi cần nhiều OAuth login song song, còn phải phân biệt **pending Authorization Requests** với authorized clients đã được cấp. Pending state/callback thuộc `HttpSessionOAuth2AuthorizationRequestRepository`, không phải kho authorized client.

### 14.3. Tab A đang dùng Alice, tab B đổi Bob

Nếu sản phẩm cho đổi tài khoản ở một tab, tab còn lại có thể tiếp tục hiển thị dữ liệu cũ trong UI nhưng browser đang dùng chung session server.

Không chỉ dựa vào dữ liệu hiển thị ở tab để biết user hiện tại. Mọi request nhạy cảm phải được xác thực và phân quyền theo principal/session hiện thời ở backend.

## 15. Logout và cleanup dữ liệu token

### 15.1. Logout Portal không đồng nghĩa token revocation

Khi logout trong ứng dụng Servlet, Spring Security thường hủy phiên cục bộ và xóa Authentication/SecurityContext theo cấu hình.

Nếu authorized client nằm trong HttpSession bị hủy, dữ liệu token cục bộ cũng biến mất cùng session.

Tuy nhiên:

- Access token đã cấp có thể vẫn được AS/Resource Server chấp nhận tới khi hết hạn hoặc bị thu hồi.
- Refresh token có thể vẫn còn hợp lệ ở AS nếu chưa bị revoke.
- OP có thể vẫn giữ phiên SSO.
- Nếu token lưu ở `OAuth2AuthorizedClientService` ngoài session, record có thể tiếp tục tồn tại.

### 15.2. `removeAuthorizedClient` không tự gọi revocation

Xóa token khỏi local repository chỉ thay đổi kho lưu của Portal.

Muốn thu hồi access/refresh token tại AS phải dùng cơ chế token revocation được provider hỗ trợ, cùng authentication và policy tương ứng. Cần thiết kế riêng quy trình này.

### 15.3. Các sự kiện cần dọn authorized client

Tùy nghiệp vụ có thể cần cleanup khi:

- User logout.
- User đổi account hoặc tenant.
- Client bị ngắt liên kết với provider.
- Token refresh bị từ chối.
- Tài khoản bị khóa hoặc giảm quyền.
- Registration/client secret bị thay đổi.
- Session hết hạn.
- User yêu cầu revoke quyền.

**Đảm bảo cleanup đi đúng kho thực sự được dùng.** Xóa một session attribute không giải quyết record đang lưu bằng service/database, và ngược lại.

## 16. Bảo mật của session chứa token

### 16.1. Cấu hình cookie và timeout

Ví dụ:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Giải thích:

- `timeout` là thời hạn bất hoạt của session, không phải TTL của access token.
- `HttpOnly` hạn chế JavaScript thông thường đọc session cookie.
- `Secure` yêu cầu HTTPS.
- `SameSite` giúp kiểm soát gửi cookie trong ngữ cảnh cross-site; cần đánh giá theo OIDC redirect flow cụ thể.

Ở môi trường local HTTP, cookie `Secure` có thể không được gửi theo kỳ vọng. Hãy cấu hình theo môi trường mà không hạ yêu cầu production.

### 16.2. Session fixation

Sau khi xác thực thành công, ứng dụng nên thay session identifier hoặc áp biện pháp session fixation protection phù hợp. Spring Security Servlet cung cấp cơ chế session fixation protection.

Điều này bảo vệ session ID nhưng không thay thế việc dọn token khi một session bị tái sử dụng để đổi principal.

### 16.3. CSRF

Browser tự gửi session cookie có thể khiến các request thay đổi trạng thái bị CSRF nếu không được bảo vệ.

`state` trong OAuth Authorization Request bảo vệ correlation của callback, không bảo vệ mọi endpoint `POST /orders`, `POST /account`.

Không tắt CSRF toàn bộ chỉ vì ứng dụng sử dụng OAuth2/OIDC Login.

### 16.4. Kho session phân tán là nơi lưu credential

Với Spring Session hoặc hệ thống lưu session phân tán, serialized session data có thể chứa authorized client cùng refresh token.

Các kiểm soát cần xem xét:

- Quyền truy cập và network isolation của session store.
- TLS/mã hóa khi truyền và encryption at rest khi phù hợp.
- TTL, backup/replication, rotation và xóa dữ liệu.
- Đánh giá lưu session trong log/metrics/backup.
- Hạn chế service khác truy cập raw session objects.
- Theo dõi khả năng serialization và tương thích giữa các version deploy.

**Không dùng dump toàn bộ HttpSession** làm phương pháp chẩn đoán ở production.

## 17. Nhiều instance và load balancer

Sơ đồ:

~~~text
Browser
  |
Load Balancer
  |---- Portal A
  |---- Portal B
~~~

Nếu Portal A lưu authorized client trong session memory cục bộ nhưng request kế tiếp đến Portal B, B có thể không thấy token đã lưu.

Hệ quả là triệu chứng “đăng nhập được nhưng gọi API không thấy authorized client”.

Các hướng giải quyết:

1. **Session affinity** để cùng browser thường vào cùng node, hiểu giới hạn khi node lỗi/scale.
2. **Kho session chia sẻ** qua Spring Session hoặc một session manager phân tán.
3. **Principal-based authorized client service** với backing store phù hợp nếu muốn persist ngoài session.

Dù chọn cách nào vẫn cần thiết kế token isolation, concurrent refresh và cleanup. Session chia sẻ không tự giải quyết atomic update trong mọi trường hợp.

### 17.1. Đọc từ instance khác và cookie không nhất quán

Cũng cần xem:

- Cookie domain/path.
- HTTPS và `Secure` flag.
- Session ID rotation sau login.
- Forwarded headers từ reverse proxy.
- Timeout ở session store.
- Vấn đề phiên bị xóa khi deployment.

Không bỏ kiểm tra authentication hoặc chuyển token sang biến toàn cục chỉ để làm cho multi-node hoạt động.

## 18. Khi nào nên chọn repository nào?

| Nhu cầu | Session repository | Principal-aware repository/service |
|---|---|---|
| Token chỉ cần gắn với một browser session | Phù hợp | Có thể cần ràng buộc session riêng |
| Anonymous flow cần ngữ cảnh browser | Có thể phù hợp | Thường cần repository fallback |
| User muốn token qua nhiều browser session | Không tự đáp ứng | Có thể phù hợp nếu chính sách cho phép |
| Background job không có Servlet request | Không thuận tiện | Service/manager theo service principal hợp lý hơn |
| Logout cần xóa token theo session | Có thể đi theo session invalidation | Cần cleanup record bên ngoài session |
| Đổi account trong cùng phiên | Cần bảo vệ và xóa token cũ | Có khóa principal nhưng vẫn cần identity đúng |
| Nhiều node không chia sẻ session | Dễ thiếu dữ liệu | Backing store theo service có thể hỗ trợ |
| Concurrent refresh token | Vẫn cần xử lý riêng | Vẫn cần xử lý riêng |

Trong ứng dụng OIDC web Servlet thông thường, nên **hiểu các bean và repository hiện có trước khi override**. Lựa chọn repository dựa trên mô hình token ownership, phiên, logout và khả năng vận hành, không dựa riêng vào tên class.

## 19. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra |
|---|---|---|
| Sau login không có authorized client | Repository/service khác nhau ở save và load; session/cookie mất | Wiring repository, registration, session |
| `loadAuthorizedClient` trả null | Chưa được cấp token, đã xóa hoặc sai registration | Flow, principal, repository |
| Session còn nhưng API trả 401 | Token hết hạn, sai audience/scope, bị revoke | Token manager và Resource Server |
| Logout xong token vẫn dùng được | Local logout không tự revoke token | AS/RS token policy |
| Bob dùng nhầm token Alice | Tái sử dụng session hoặc key không cách ly principal | Account switching/cleanup |
| Tab A và B có trạng thái token khác | Hai request đồng thời, refresh/repository update | Concurrency và token lifecycle |
| Nhiều node lúc có token lúc không | Session store không chia sẻ/routing không ổn định | Spring Session, load balancer |
| Refresh token bị từ chối | Token rotation, token hết hạn hoặc concurrency | AS policy, refresh coordination |
| Background job thiếu token | Không có Servlet request/session | Service principal/manager |
| Đọc token bằng attribute session nội bộ bị lỗi | Phụ thuộc implementation details | Sử dụng repository API |
| API nhận ID token rồi báo 401 | Dùng sai loại token/audience | Gửi access token đúng resource |

### 19.1. Chẩn đoán an toàn

Có thể quan sát:

- Registration ID.
- Loại Authentication và trạng thái đã xác thực.
- Session có tồn tại không (không log ID).
- Repository nào được wiring.
- Authorized client có tìm thấy không.
- Token expiry time nếu được phép.
- Lỗi token endpoint ở mức mã lỗi chung.
- Instance và correlation ID của request.

Không log:

~~~text
access token
refresh token
ID token
authorization code
code_verifier
client secret
JSESSIONID / session cookie
serialized HttpSession
~~~

## 20. Ví dụ thiết kế tổng hợp

Một Customer Portal yêu cầu:

- Đăng nhập OIDC bằng `corporate`.
- Dùng access token gọi Orders API.
- Không trộn token Alice và Bob.
- Có nhiều server instance.
- Cho phép logout và ngắt kết nối provider.

Thiết kế cần quyết định:

1. Authorized client có phải gắn với mỗi browser session hay theo principal?
2. Nếu đăng nhập từ nhiều thiết bị, có cho dùng chung một token không?
3. Khi đổi tài khoản trong cùng browser, session/token nào phải bị xóa?
4. Khi token hết hạn, component nào refresh?
5. Có cần xử lý refresh rotation đồng thời?
6. Token nằm trong HttpSession hoặc service/database nào?
7. Khi logout, token local có bị xóa và có cần revoke token tại AS không?
8. API kiểm tra audience, scope, issuer, quyền trên đơn hàng ra sao?

Một mô hình tốt không chỉ “lưu token cho request tiếp theo” mà còn xác định **ai được phép dùng token, lưu bao lâu và xóa khi nào**.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** `HttpSessionOAuth2AuthorizedClientRepository` dùng để lưu gì?

**Trả lời:** `OAuth2AuthorizedClient` với access token và có thể refresh token theo ngữ cảnh HttpSession của ứng dụng Servlet.

**Câu 2.** Nó có lưu authorization request đang chờ callback không?

**Trả lời:** Không phải nhiệm vụ của nó. Authorization Request và state được quản lý bằng `OAuth2AuthorizationRequestRepository`, thường có implementation session tương ứng.

**Câu 3.** Có HttpSession đồng nghĩa user đã login và có token?

**Trả lời:** Không. Session có thể tồn tại trước login. Phải kiểm tra SecurityContext/Authentication và authorized client riêng.

**Câu 4.** `OAuth2AuthorizedClientRepository` khác `OAuth2AuthorizedClientService` ở đâu?

**Trả lời:** Repository nhận Servlet request/response cùng Authentication; service lưu/tra cứu theo registration ID và principal name mà không cần Servlet request.

**Câu 5.** Khi authenticated principal, `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` thường dùng kho nào?

**Trả lời:** `OAuth2AuthorizedClientService`. Với anonymous, nó dùng repository phụ, mặc định thường là session repository.

**Câu 6.** Rủi ro khi đổi Alice sang Bob trong cùng HttpSession là gì?

**Trả lời:** Nếu chưa xóa token cũ và không ràng buộc principal đúng, có thể lấy token Alice cho request của Bob.

**Câu 7.** Session còn 20 phút nhưng access token đã hết hạn, repository có tự refresh không?

**Trả lời:** Không. Repository chỉ lưu/tải/xóa; manager/provider và chính sách AS điều phối reauthorization/refresh.

**Câu 8.** Logout Portal có làm access token đã phát hành mất hiệu lực ở Orders API ngay không?

**Trả lời:** Không mặc định. Local session cleanup khác token revocation tại AS.

**Câu 9.** Tại sao multi-node có thể mất authorized client?

**Trả lời:** Nếu session lưu cục bộ ở node A, node B có thể không đọc được. Cần kho session chia sẻ hoặc cách lưu theo principal phù hợp.

**Câu 10.** Có thể dùng ID token của `OidcUser` thay access token khi gọi API không?

**Trả lời:** Không theo mô hình OAuth Resource Server thông thường. Cần access token dành cho audience/scope của API.

**Câu 11.** Dùng session repository có bảo đảm mỗi tab lưu token riêng?

**Trả lời:** Không. Các tab cùng browser thường chia sẻ session cookie và do đó có thể chia sẻ authorized client.

**Câu 12.** Nếu ứng dụng chạy background job không có HttpServletRequest thì nên dùng gì?

**Trả lời:** Cân nhắc authorized client manager/service theo principal đại diện cho service hoặc cơ chế phù hợp, thay vì phụ thuộc một HttpSession của browser.

## Ghi nhớ

- **`HttpSessionOAuth2AuthorizedClientRepository` lưu trạng thái authorized client/token trong phiên Servlet**.
- **`ClientRegistration` chỉ là cấu hình**, còn `OAuth2AuthorizedClient` chứa access token và có thể refresh token.
- **Authorization Request**, **SecurityContext** và **Authorized Client** được quản lý bằng những abstraction khác nhau, dù có thể cùng liên quan đến HttpSession.
- **Session scope không tự động là principal scope**: đặc biệt phải bảo vệ khi đổi tài khoản và khi có nhiều tenant.
- **`AuthenticatedPrincipalOAuth2AuthorizedClientRepository`** có thể dùng service cho authenticated principal và session repository cho anonymous.
- **Repository không tự refresh hoặc revoke token**. Dùng cơ chế authorized client manager và cleanup/logout/revocation phù hợp.
- **Session store chứa token là nơi lưu credential nhạy cảm**; cần bảo vệ cookie, HTTPS, CSRF, session fixation, TTL, concurrency và triển khai phân tán.
- **Khi gọi API, dùng access token đúng audience/scope, không dùng ID token thay thế.**
