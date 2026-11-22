# 14.1. OAuth2AuthorizedClient và liên kết registration, principal, token

## 1. Vì sao cần OAuth2AuthorizedClient?

Trong Spring Security OAuth 2.0/OIDC Client, biết **ứng dụng đã đăng ký với Authorization Server nào** chưa đủ để gọi một API được bảo vệ. Ứng dụng còn cần biết **ai đã cấp quyền**, **token nào đã được cấp** và token đó gắn với cấu hình OAuth2 Client nào.

Ví dụ một cổng doanh nghiệp có hai người dùng An và Bình:

- Ứng dụng có cấu hình ClientRegistration tên <code>company</code> để đăng nhập qua OpenID Provider.
- An đăng nhập và nhận access token dành cho An.
- Bình đăng nhập qua chính provider đó và nhận access token dành cho Bình.
- An cũng có thể ủy quyền cho một provider khác, chẳng hạn <code>partner</code>.

Nếu ứng dụng chỉ giữ một biến toàn cục chứa “access token mới nhất”, request của An có thể vô tình sử dụng token của Bình. Nếu chỉ lưu token theo tên provider, người dùng cùng provider có thể ghi đè token của nhau.

**<code>OAuth2AuthorizedClient</code>** là đối tượng Spring Security sử dụng để diễn tả mối liên hệ:

> **Một ClientRegistration + một principalName + một access token + một refresh token tùy chọn.**

Trong Authorization Code Flow, đối tượng này thường được tạo khi Client đã trao đổi authorization code thành công để nhận token. Trong Client Credentials Flow, authorized client cũng có thể được tạo dù không có End-User tương tác.

### Mục tiêu sau bài học

Người học có thể giải thích rõ:

1. <code>ClientRegistration</code> và <code>OAuth2AuthorizedClient</code> khác nhau thế nào.
2. <code>principalName</code> được dùng ra sao khi gắn token với người dùng hoặc service.
3. Vì sao access token/refresh token là dữ liệu khác với ID Token.
4. Cách Spring Security lưu, tra cứu và làm mới authorized client.
5. Cách sử dụng authorized client an toàn với Servlet OAuth2 Login và các job server-side.
6. Các lỗi phổ biến khi nhiều người dùng, provider hoặc tenant cùng sử dụng một ứng dụng.

## 2. Mô hình dữ liệu của OAuth2AuthorizedClient

~~~mermaid
flowchart TD
    R["ClientRegistration: company"] --> AC["OAuth2AuthorizedClient"]
    P["principalName: user-123"] --> AC
    AC --> AT["OAuth2AccessToken"]
    AC --> RT["OAuth2RefreshToken nếu được cấp"]
    AT --> ATD["tokenValue, tokenType, issuedAt, expiresAt, scopes"]
    RT --> RTD["tokenValue, issuedAt, expiresAt nếu có"]
    S["OAuth2AuthorizedClientService / Repository"] --> AC
~~~

Các phương thức truy cập chính:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

OAuth2AuthorizedClient client = /* do Spring Security cung cấp */;

ClientRegistration registration = client.getClientRegistration();
String principalName = client.getPrincipalName();
OAuth2AccessToken accessToken = client.getAccessToken();
OAuth2RefreshToken refreshToken = client.getRefreshToken(); // có thể null
~~~

| Thành phần | Ý nghĩa | Điều không nên nhầm |
|---|---|---|
| <code>clientRegistration</code> | Thông tin Client đã đăng ký với provider, grant type, endpoint, scope | Không phải token của người dùng |
| <code>principalName</code> | Tên định danh dùng ràng buộc authorized client với một principal | Không luôn là email hoặc ID Token subject |
| <code>accessToken</code> | Credential dùng gọi API trong phạm vi được cấp | Không dùng làm ID Token |
| <code>refreshToken</code> | Credential để xin token mới nếu provider/flow hỗ trợ | Có thể vắng mặt |

Lớp <code>OAuth2AuthorizedClient</code> nằm trong package <code>org.springframework.security.oauth2.client</code>. Đây là **đối tượng mô hình**, không phải một repository hay manager. Tự tạo đối tượng không tạo quyền truy cập thực tế tại Authorization Server.

### 2.1. ClientRegistration đại diện cho ứng dụng

<code>ClientRegistration</code> mô tả một OAuth 2.0 Client:

~~~text
registrationId: company
clientId:       rental-web
grantType:      authorization_code
issuer:         https://idp.example.org/realms/company
redirectUri:    {baseUrl}/login/oauth2/code/{registrationId}
scope:          openid, profile, api.read
~~~

Các thông tin trong ví dụ là placeholder; provider thật phải cung cấp Client ID, endpoint, credential và policy phù hợp.

Thông tin ClientRegistration có thể được nhiều người dùng của cùng ứng dụng dùng chung. **Access token không được dùng chung theo cách đó** khi token đại diện cho ủy quyền của từng người dùng.

<code>registrationId</code> là tên nội bộ do ứng dụng đặt; <code>clientId</code> do Authorization Server cấp. Hai giá trị không nhất thiết trùng nhau.

### 2.2. principalName đại diện cho ngữ cảnh của authorized client

Với OAuth2 Login trên Servlet, <code>principalName</code> thường được lấy từ <code>Authentication.getName()</code>. Với OIDC User mặc định, nó thường dựa trên claim <code>sub</code>, nhưng có thể thay đổi nếu ứng dụng tùy biến tên principal.

Những điều cần chú ý:

- Không mặc định <code>principalName</code> là địa chỉ email.
- Không dùng tên hiển thị người dùng làm khóa token nếu nó có thể trùng hoặc thay đổi.
- Không cho browser gửi tùy ý một <code>principalName</code> để backend tra cứu token của người khác.
- Khi thiết kế multi-tenant, phải tránh va chạm principal name giữa hai issuer/tenant.
- Với client credentials, principal name có thể là một chuỗi đại diện **service**, không phải End-User.

Ví dụ một hệ thống OIDC có thể sử dụng cặp <code>(iss, sub)</code> làm danh tính ngoài. Nếu chỉ biến <code>sub</code> thành principal name và các issuer có cùng subject, có thể xuất hiện rủi ro va chạm tại storage dùng chung. Cần thiết kế định danh nội bộ nhất quán với giới hạn tin cậy của hệ thống.

### 2.3. Access token chứa gì?

<code>OAuth2AccessToken</code> có các thông tin:

~~~java
OAuth2AccessToken token = client.getAccessToken();
OAuth2AccessToken.TokenType type = token.getTokenType();
String tokenValue = token.getTokenValue(); // nhạy cảm
Instant issuedAt = token.getIssuedAt();
Instant expiresAt = token.getExpiresAt();
Set<String> scopes = token.getScopes();
~~~

Access token có thể là JWT hoặc chuỗi opaque. **Không suy ra nó luôn là JWT** hoặc luôn có thể giải mã để đọc claim. Resource Server chịu trách nhiệm kiểm tra token bằng cơ chế phù hợp (JWT validation hoặc introspection), cùng audience, scope, expiry và authorization nghiệp vụ.

Không ghi <code>getTokenValue()</code> vào log hoặc trả về browser chỉ để debug.

### 2.4. Refresh token là tùy chọn

<code>OAuth2RefreshToken</code> có thể chứa giá trị token, thời điểm cấp và thời điểm hết hạn nếu được cung cấp:

~~~java
OAuth2RefreshToken refresh = client.getRefreshToken();

if (refresh != null) {
    // Chỉ sử dụng qua thành phần OAuth2 Client thích hợp.
}
~~~

Không phải Authorization Server nào cũng cấp refresh token cho mọi grant. Ví dụ client credentials thường xin access token mới bằng chính grant đó, không cần refresh token.

Không giả định <code>getRefreshToken()</code> luôn khác null, hoặc token còn tồn tại trong storage thì chắc chắn refresh được.

## 3. Cặp khóa (registrationId, principalName)

Một cách hiểu rất hữu ích là các authorized client được quản lý trong ngữ cảnh hai chiều:

~~~text
(clientRegistrationId, principalName)
~~~

Bảng minh họa:

| registrationId | principalName | Access token | Refresh token |
|---|---|---|---|
| <code>company</code> | <code>an</code> | <code>AT-COMPANY-AN</code> | <code>RT-COMPANY-AN</code> |
| <code>company</code> | <code>binh</code> | <code>AT-COMPANY-BINH</code> | Không có |
| <code>partner</code> | <code>an</code> | <code>AT-PARTNER-AN</code> | <code>RT-PARTNER-AN</code> |

Các chuỗi token trong bảng chỉ là nhãn minh họa, không phải credential thực.

**Cùng registration, khác principal:** An và Bình sử dụng token riêng.

**Cùng principal, khác registration:** An có thể có token riêng cho từng Client/provider.

**Một authorized client không tự chứng minh quyền hiện tại:** Resource Server vẫn quyết định liệu token đủ audience, scope và entitlement hay không. Người dùng có thể bị thu hồi quyền nội bộ trong khi token vẫn còn hạn.

### 3.1. Vì sao không lưu token chỉ theo registration?

Mô hình nguy hiểm:

~~~java
Map<String, String> accessTokenByProvider = new HashMap<>();
accessTokenByProvider.put("company", tokenValue);
~~~

Nếu một singleton hoặc static map dùng chung cho mọi phiên, token của Bình có thể ghi đè token của An. Sau đó một request của An có nguy cơ gọi API dưới danh nghĩa Bình.

Spring Security cung cấp authorized-client storage để giải quyết phần lớn nhu cầu gắn token với principal. Ứng dụng phải dùng nó đúng cách và đảm bảo principal key không va chạm.

### 3.2. Một user có thể có nhiều authorized client

Ví dụ An được phép dùng hai provider:

~~~text
An + company = OAuth2AuthorizedClient A
An + partner = OAuth2AuthorizedClient B
~~~

Hai authorized client có thể có endpoint, client ID, issuer, scopes, audience và token lifetime khác nhau. Không chuyển token của provider A sang API của provider B chỉ vì cùng <code>principalName</code>.

### 3.3. principalName không nhất thiết là danh tính duy nhất trên Internet

<code>OAuth2AuthorizedClient.principalName</code> là giá trị dùng lưu/truy cập authorized client trong ứng dụng. Nó không phải một thay thế tự động cho quy tắc OIDC <code>(iss, sub)</code>.

Khi người dùng đến từ nhiều issuer, ứng dụng nên dùng một tên principal đã được chuẩn hóa, không trùng và có ràng buộc danh tính rõ ràng. Cùng một tên <code>user123</code> tại hai tenant không mặc nhiên là cùng một người.

## 4. Tạo OAuth2AuthorizedClient minh họa bằng Java

Constructor nhận cấu hình Client, principal name và access token; refresh token được cung cấp nếu có.

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Set;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

ClientRegistration registration = /* cấu hình đã tạo ở nơi khác */;

Instant now = Instant.now();
OAuth2AccessToken access = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "demo-access-token",
    now,
    now.plus(30, ChronoUnit.MINUTES),
    Set.of("profile.read"));

OAuth2RefreshToken refresh = new OAuth2RefreshToken(
    "demo-refresh-token",
    now);

OAuth2AuthorizedClient authorizedClient = new OAuth2AuthorizedClient(
    registration,
    "user-123",
    access,
    refresh);
~~~

Đoạn code minh họa **cấu trúc object**, không phải hướng dẫn phát token giả để sử dụng production. Trong thực tế, các token đến từ Token Endpoint sau một grant hợp lệ và phải được xử lý bằng OAuth2 Client components. Chuỗi token tự đặt ở trên không có giá trị đối với Authorization Server.

Nếu không có refresh token, ứng dụng vẫn có thể tạo authorized client với refresh token null hoặc dùng constructor phù hợp với phiên bản API. Chỉ đưa dữ liệu token thực vào storage được bảo vệ.

### 4.1. Access token thay đổi khi refresh

Một authorized client đang được lưu có thể chứa access token đã hết hạn. Khi manager refresh thành công, token mới cần được lưu lại như một authorized client cập nhật.

Đừng giữ một tham chiếu <code>OAuth2AuthorizedClient</code> trong singleton suốt nhiều giờ rồi kỳ vọng object cũ tự đổi token khi instance khác refresh. Nên truy vấn lại trạng thái thích hợp hoặc dùng <code>OAuth2AuthorizedClientManager</code>.

## 5. Vòng đời khi đăng nhập bằng OIDC Authorization Code

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Browser
    participant C as Spring Security Client
    participant OP as OpenID Provider
    participant S as Authorized Client Storage
    participant API as Resource Server
    U->>C: GET /oauth2/authorization/company
    C-->>U: 302 tới OP với state và PKCE khi áp dụng
    U->>OP: Người dùng đăng nhập
    OP-->>U: Callback với authorization code và state
    U->>C: GET /login/oauth2/code/company
    C->>C: Tìm authorization request và kiểm tra state
    C->>OP: POST /token
    OP-->>C: Access token, refresh token nếu có, ID Token nếu OIDC
    C->>C: Xác minh ID Token và dựng Authentication
    C->>S: Lưu OAuth2AuthorizedClient
    C-->>U: Login success / session
    U->>C: GET /my/data
    C->>S: Tra cứu đúng registration và principal
    S-->>C: OAuth2AuthorizedClient
    C->>API: Bearer access token đúng audience và scope
    API-->>C: Resource response
    C-->>U: Kết quả ứng dụng
~~~

Ba thời điểm cần phân biệt:

**Trước callback:** Spring Security có <code>OAuth2AuthorizationRequest</code> chứa state, redirect URI và dữ liệu PKCE. Nó thường được lưu bằng <code>HttpSessionOAuth2AuthorizationRequestRepository</code>. Đây **chưa** phải authorized client.

**Khi token exchange thành công:** Client đã nhận access token và có thể refresh token. Spring Security tạo ra <code>OAuth2AuthorizedClient</code> gắn registration với principal.

**Trong những request sau:** Spring Security truy xuất authorized client, sử dụng access token hiện hành (hoặc refresh theo cấu hình) để gọi API.

### 5.1. OAuth2AuthorizedClient khác OidcUser

Sau OIDC Login:

~~~text
Authentication / SecurityContext
  └── principal: OidcUser
        ├── ID Token đã được xác minh
        ├── UserInfo nếu có
        └── GrantedAuthorities

OAuth2AuthorizedClient
  ├── ClientRegistration
  ├── principalName
  ├── OAuth2AccessToken
  └── OAuth2RefreshToken nếu có
~~~

<code>OidcUser</code> giúp ứng dụng biết **người dùng đã được xác thực là ai**. <code>OAuth2AuthorizedClient</code> giúp Client biết **token nào đã được cấp trong ngữ cảnh principal đó**.

Đừng tìm ID Token qua <code>OAuth2AuthorizedClient.getAccessToken()</code>. ID Token và access token có mục đích khác nhau.

### 5.2. Bảng so sánh các loại token

| Token | Mục đích | Sử dụng ở đâu? |
|---|---|---|
| ID Token | Chứng minh authentication cho OIDC Client | Spring Security xác minh ID Token và dựng <code>OidcUser</code> |
| Access token | Cho phép truy cập Resource Server trong phạm vi được cấp | Client gửi tới API đích |
| Refresh token | Xin access token mới nếu Authorization Server hỗ trợ | Client gửi tới Token Endpoint |

Không chuyển ID Token thành bearer token cho API tùy ý; cũng không gửi refresh token trong request API.

## 6. OAuth2AuthorizedClientService: lưu theo registration và principal

Interface <code>OAuth2AuthorizedClientService</code> có các API chính:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    String principalName);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName);
~~~

Service phù hợp với các use case không nhất thiết cần <code>HttpServletRequest</code> để đọc dữ liệu token.

Ví dụ tra cứu token cho người dùng đã xác thực:

~~~java
package example.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.stereotype.Service;

@Service
public class AuthorizedClientLookup {

    private final OAuth2AuthorizedClientService service;

    public AuthorizedClientLookup(OAuth2AuthorizedClientService service) {
        this.service = service;
    }

    public OAuth2AuthorizedClient findForCurrentUser(
            Authentication authentication) {

        if (authentication == null || !authentication.isAuthenticated()) {
            throw new IllegalArgumentException("Authentication required");
        }

        return service.loadAuthorizedClient(
            "company",
            authentication.getName());
    }
}
~~~

Khi không có authorized client phù hợp, <code>loadAuthorizedClient</code> có thể trả <code>null</code>. Không nên tự tạo access token hoặc fallback sang token của người dùng khác để “chữa lỗi”.

**Quan trọng:** Không cho browser chọn <code>principalName</code> bất kỳ qua query parameter để gọi API load. Với token gắn End-User, phải lấy principal từ <code>Authentication</code> tin cậy và áp dụng authorization.

### 6.1. InMemoryOAuth2AuthorizedClientService

Spring Security cung cấp implementation trong bộ nhớ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientService authorizedClientService(
        ClientRegistrationRepository registrations) {
    return new InMemoryOAuth2AuthorizedClientService(registrations);
}
~~~

Đoạn bean chỉ minh họa cách cấu hình tường minh. Nếu Spring Boot đã cung cấp service theo auto-configuration thì không khai báo thêm bean trùng tùy tiện.

Đặc điểm:

- Dễ sử dụng cho ứng dụng thử nghiệm hoặc single instance.
- Dữ liệu token trong memory sẽ mất sau restart.
- Các instance khác không tự thấy token được lưu bởi instance hiện tại.
- Không tự bảo đảm refresh token hoặc session lifetime.

**<code>InMemoryOAuth2AuthorizedClientService</code> khác <code>InMemoryClientRegistrationRepository</code>**. Một lớp chứa token đã được cấp; lớp còn lại chỉ chứa cấu hình đăng ký Client.

### 6.2. Lưu trữ bằng JDBC

Spring Security cũng hỗ trợ <code>JdbcOAuth2AuthorizedClientService</code> cho những trường hợp cần persistent storage. Trong production phải tính tới:

1. Bảo vệ access/refresh token bằng phân quyền database, encryption-at-rest và/hoặc mã hóa ở ứng dụng tùy mô hình đe dọa.
2. Giới hạn ai được đọc dữ liệu token, tránh cấp quyền database quá rộng.
3. Có chính sách cleanup khi user logout, unlink provider, bị khóa hoặc không còn cần ủy quyền.
4. Xử lý refresh concurrency khi nhiều node có thể cập nhật cùng authorized client.
5. Không để token value lộ ra log, backup không được bảo vệ hoặc hệ thống hỗ trợ.

Chuyển sang JDBC giúp có dữ liệu qua restart nhưng không tự đồng nghĩa bảo mật hơn hoặc token luôn có giá trị.

## 7. OAuth2AuthorizedClientRepository: lưu trong ngữ cảnh Servlet

Đối với Servlet web request, Spring Security có interface:

~~~java
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
~~~

Các class <code>HttpServletRequest</code>/<code>HttpServletResponse</code> thuộc <code>jakarta.servlet.http</code> trong Spring Boot 3/Spring Security 6.

Repository nhận request/response và Authentication nên có thể chọn cơ chế lưu phù hợp với session hoặc người dùng.

Spring Security có những implementation như:

- <code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code>: có thể dùng service để lưu authorized client cho principal đã xác thực.
- <code>HttpSessionOAuth2AuthorizedClientRepository</code>: lưu authorized clients trong HTTP session.

Sự lựa chọn cụ thể phụ thuộc cấu hình và version Spring Security/Spring Boot, không nên mặc định tất cả token chỉ được lưu vào HttpSession.

### 7.1. So sánh Service và Repository

| Đặc điểm | OAuth2AuthorizedClientService | OAuth2AuthorizedClientRepository |
|---|---|---|
| Tra cứu bằng | registration ID + principalName | registration ID + Authentication + HTTP request |
| Phụ thuộc Servlet request | Không | Có |
| Thường dùng | Service layer, background process, storage | OAuth2 Login, Servlet request |
| Ví dụ implementation | InMemory, JDBC | HTTP session hoặc delegate sang service |
| Có tự refresh token không? | Không | Không |

**Storage không phải token manager.** Cả hai interface chủ yếu quản lý việc lưu/đọc/xóa authorized client; logic refresh hoặc authorize mới thuộc các provider/manager thích hợp.

### 7.2. Đừng nhầm ba repository

| Thành phần | Chứa gì? | Giai đoạn |
|---|---|---|
| <code>ClientRegistrationRepository</code> | Client ID, grant type, endpoint, scopes, issuer | Cấu hình trước/giữa các flow |
| <code>HttpSessionOAuth2AuthorizationRequestRepository</code> | Authorization request đang chờ callback, state, PKCE attributes | Trước và khi callback |
| <code>OAuth2AuthorizedClientRepository</code> | Authorized client chứa access/refresh token | Sau token exchange |

Đặc biệt, **AuthorizationRequestRepository không lưu refresh token sau khi login**; nó giữ dữ liệu để correlation authorization response.

## 8. Cấu hình OIDC Login và truy cập authorized client

Ví dụ với Spring Boot 3/Spring Security 6 Servlet.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 8.2. Đăng ký Client

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: rental-web
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - api.read
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Các giá trị ở đây chỉ là ví dụ. <code>api.read</code> phải là scope thật sự được Authorization Server chấp nhận và cấp cho API; client secret lấy từ môi trường/secret manager, không commit vào source.

### 8.3. Kích hoạt Login/Client

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

<code>oauth2Login()</code> hỗ trợ đăng nhập Servlet; <code>oauth2Client()</code> cung cấp các thành phần hỗ trợ khi ứng dụng đóng vai OAuth2 Client và cần dùng token để gọi API. Nếu ứng dụng chỉ thực hiện login, không phải lúc nào cũng cần cả hai.

### 8.4. Nhận authorized client ở controller

Annotation <code>@RegisteredOAuth2AuthorizedClient</code> cho phép controller yêu cầu authorized client đúng registration trong ngữ cảnh người dùng hiện tại:

~~~java
package example.web;

import java.util.Map;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthorizedClientInfoController {

    @GetMapping("/my/authorized-client")
    public Map<String, Object> info(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient) {

        return Map.of(
            "registrationId",
            authorizedClient.getClientRegistration().getRegistrationId(),
            "hasRefreshToken",
            authorizedClient.getRefreshToken() != null,
            "hasKnownExpiry",
            authorizedClient.getAccessToken().getExpiresAt() != null
        );
    }
}
~~~

Controller chỉ trả **metadata**, không trả token value hoặc refresh token. Nếu không có authorized client và resolver không thể authorize theo cấu hình, yêu cầu có thể thất bại; ứng dụng cần xử lý phù hợp thay vì giả định mọi registration đều có token.

Annotation không có nghĩa server sẽ lấy token của một người bất kỳ cùng registration: việc resolve dựa vào ngữ cảnh principal/request đã xác thực.

### 8.5. Dùng access token gọi API

Giả sử API <code>https://api.example.org/v1/me</code> được cấu hình **chấp nhận access token có audience/scope phù hợp** từ provider:

~~~java
package example.web;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class DownstreamProfileController {

    private final RestClient api;

    public DownstreamProfileController(RestClient.Builder builder) {
        this.api = builder.baseUrl("https://api.example.org").build();
    }

    @GetMapping("/my/remote-profile")
    public String remoteProfile(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient) {

        String token = authorizedClient.getAccessToken().getTokenValue();

        return api.get()
            .uri("/v1/me")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(String.class);
    }
}
~~~

Đoạn code dùng <code>RestClient</code> (Spring Framework 6.1+/Spring Boot 3.2+) và chỉ minh họa backend gọi API. Trong production, cần DTO, timeouts, xử lý lỗi, kiểm soát response size và chính sách dữ liệu phù hợp.

Nếu access token chỉ dành cho UserInfo Endpoint, **không gửi nó sang API nghiệp vụ khác**. Có access token không có nghĩa token đúng audience/scope cho mọi Resource Server.

## 9. OAuth2AuthorizedClientManager và vòng đời token

<code>OAuth2AuthorizedClientManager</code> là abstraction cao hơn, phối hợp registration, storage và provider để **authorize** hoặc **refresh** khi grant được cấu hình cho phép.

~~~java
OAuth2AuthorizedClient authorize(
    OAuth2AuthorizeRequest authorizeRequest);
~~~

Các vai trò:

1. Tìm ClientRegistration theo registration ID.
2. Tìm authorized client hiện hành trong ngữ cảnh principal.
3. Chọn <code>OAuth2AuthorizedClientProvider</code> phù hợp.
4. Cấp token hoặc refresh nếu điều kiện cho phép.
5. Lưu trạng thái authorized client mới khi thành công.
6. Xử lý lỗi theo policy của manager/handler.

Các provider thường gặp có authorization code, refresh token và client credentials; không phải grant nào cũng được kích hoạt mặc định trong mọi manager.

### 9.1. Web manager và service manager

| Lớp | Ngữ cảnh |
|---|---|
| <code>DefaultOAuth2AuthorizedClientManager</code> | Servlet HTTP request, sử dụng OAuth2AuthorizedClientRepository |
| <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> | Service/background, không cần Servlet request, dùng OAuth2AuthorizedClientService |

Đừng dùng manager phụ thuộc HTTP request trong background job không có request/response. Với client credentials chạy định kỳ, dùng service manager.

### 9.2. Ví dụ client credentials không có End-User

Cấu hình registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          billing-service:
            provider: company
            client-id: billing-worker
            client-secret: ${BILLING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [billing.read]
        provider:
          company:
            token-uri: https://idp.example.org/oauth2/token
~~~

Bean manager:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class WorkerClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager workerAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);

        var provider = OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Code lấy token:

~~~java
package example.jobs;

import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class BillingAccessTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    public BillingAccessTokenProvider(
            OAuth2AuthorizedClientManager workerAuthorizedClientManager) {
        this.manager = workerAuthorizedClientManager;
    }

    public String accessToken() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest.withClientRegistrationId("billing-service")
                .principal("billing-worker-runtime")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null) {
            throw new IllegalStateException("Client cannot be authorized");
        }
        return client.getAccessToken().getTokenValue();
    }
}
~~~

<code>billing-worker-runtime</code> là **principal tổng hợp** để phân vùng storage. Token do client credentials cấp đại diện cho **Client/service**, không có nghĩa đang hành động thay một End-User đã đăng nhập.

Nếu hệ thống có nhiều tenant/workload, không mặc định dùng chung một principal tổng hợp và token cho tất cả khi policy yêu cầu tách biệt; cần thiết kế namespace theo tenant, registration và quyền được cấp.

## 10. Access token hết hạn, refresh và trạng thái lưu trữ

### 10.1. Authorized client có thể tồn tại sau khi token hết hạn

Ví dụ:

~~~text
registrationId=company
principalName=an
accessToken.expiresAt=10:00
now=10:05
refreshToken=available
~~~

Authorized client vẫn có thể nằm trong storage, nhưng access token đã hết hạn. Nếu manager có refresh-token provider và refresh token được OP chấp nhận, manager có thể xin access token mới và lưu authorized client cập nhật.

Nếu refresh token không có hoặc hết hạn/bị thu hồi, user có thể cần đăng nhập/ủy quyền lại. Không tự phát token mới từ dữ liệu local.

### 10.2. Refresh token không luôn được cấp

- Với OAuth2 authorization code, việc cấp refresh token phụ thuộc chính sách OP và registration.
- Một số OP yêu cầu scope như <code>offline_access</code> để cấp quyền truy cập khi user offline, nhưng không phải mọi provider giống nhau.
- Với client credentials, thông thường có thể xin token mới bằng client credentials grant, không cần refresh token.

Code gọi <code>getRefreshToken()</code> phải chấp nhận giá trị <code>null</code>.

### 10.3. Refresh token rotation và cạnh tranh đồng thời

Nhiều request có thể cùng đọc một authorized client gần hết hạn, rồi cố refresh. Nếu provider dùng **refresh token rotation**, request đầu tiên có thể làm token refresh cũ mất hiệu lực; request thứ hai dùng cùng refresh token có thể gặp <code>invalid_grant</code>.

Với multi-node, cần có chiến lược đồng bộ/locking/optimistic concurrency phù hợp, hoặc xử lý failure an toàn. Lock trong một JVM không bảo vệ toàn bộ cluster.

Các manager/handler có thể xóa authorized client khỏi storage khi gặp những lỗi refresh nhất định, ví dụ <code>invalid_grant</code>. Vì vậy không được mặc định bản cũ luôn còn sau lỗi.

### 10.4. Expiry không bảo đảm quyền API

Access token còn hạn chưa chắc Resource Server chấp nhận: token có thể bị thu hồi, sai audience, thiếu scope hoặc user bị khóa. Ứng dụng phải xử lý 401/403 từ API đích, không tiếp tục mù với token không phù hợp.

## 11. Logout, xóa authorized client và token revocation

Logout HTTP session, xóa authorized client local và thu hồi token tại Authorization Server là ba hành động **khác nhau**.

~~~text
09:00 User đăng nhập → token được lưu trong JDBC
09:20 User logout → session kết thúc
09:21 Token trong JDBC có thể vẫn còn nếu không có cleanup riêng
~~~

Không giả định logout mặc định xóa mọi authorized client persistent hoặc thu hồi tất cả access/refresh token ở provider.

Ví dụ xóa dữ liệu local đúng principal:

~~~java
authorizedClientService.removeAuthorizedClient(
    "company",
    authentication.getName());
~~~

Lệnh này **chỉ xóa local storage** của service được gọi. Muốn thu hồi token tại Authorization Server cần cơ chế revocation riêng khi provider hỗ trợ (theo RFC 7009 hoặc tài liệu provider).

Với người dùng bị khóa hoặc vai trò bị thu hồi, có thể cần invalidation của session, authorized-client cleanup, token revocation và kiểm tra entitlement tại Resource Server. Một <code>OAuth2AuthorizedClient</code> còn lưu không đồng nghĩa user vẫn được phép truy cập.

## 12. An toàn khi nhiều người dùng, issuer, provider và tenant

### 12.1. Không đặt token trong static field

Sai về mặt phân vùng quyền:

~~~java
public class GlobalTokenHolder {
    public static String accessToken;
}
~~~

Token của người dùng sau sẽ ghi đè của người dùng trước. Dùng authorized-client storage gắn đúng registration và principal.

### 12.2. Không chuyển access token sang Resource Server sai audience

Một authorized client có token cho API A không có nghĩa dùng được token đó ở API B. Mỗi token phải được cấp cho Resource Server phù hợp, có scope và audience đúng; API đích phải tự xác minh token.

### 12.3. Không để browser chọn principal tùy ý

Mẫu endpoint không an toàn:

~~~text
GET /internal/token?principal=another-user
~~~

Nếu backend chuyển query này trực tiếp thành <code>loadAuthorizedClient(registrationId, principalName)</code>, nó có thể cho phép đọc credential của người khác. Truy vấn token gắn End-User phải bắt nguồn từ <code>Authentication</code> đã xác thực và authorization nội bộ.

### 12.4. Principal name có thể trùng giữa issuer

Nếu issuer A và B cùng dùng subject <code>12345</code>, việc chỉ dùng principalName <code>12345</code> trong storage chung có thể tạo va chạm khi registration ID được tái dùng hoặc quy tắc mapping thiếu namespace.

Để phòng tránh:

- Kiểm tra issuer và subject của OIDC identity.
- Dùng principal key ổn định, không trùng, có gắn phạm vi tenant/issuer theo kiến trúc.
- Không tự liên kết hai tài khoản chỉ dựa vào email.
- Đảm bảo service, repository và manager thống nhất khóa principal khi save/load.

### 12.5. Không nhầm quyền đăng nhập và quyền nghiệp vụ

Access token, OIDC principal và internal roles phục vụ các mục đích khác nhau. Một user có OIDC Login hợp lệ có thể không có quyền quản trị. Resource Server hoặc domain service phải kiểm tra authorization, không chỉ kiểm tra sự tồn tại của OAuth2AuthorizedClient.

## 13. Lưu token an toàn trong production

Authorized client lưu access token và có thể cả refresh token, nên storage phải được đối xử như kho credential.

| Rủi ro | Biện pháp phù hợp |
|---|---|
| Token bị lộ qua log | Không log <code>getTokenValue()</code>, raw token response, Authorization header |
| Token bị đọc từ database | Giới hạn quyền, encryption-at-rest, audit, bảo vệ backup |
| Token bị gửi về browser | Chỉ trả kết quả nghiệp vụ; backend giữ token nếu là confidential server-side Client |
| Token bị dùng sai API | Kiểm soát audience/scope, Resource Server validation |
| Token tồn tại quá lâu | Cleanup, TTL, revocation và retention policy |
| Token trộn giữa user/tenant | Storage key/namespace đúng và kiểm soát Authentication |
| Refresh đồng thời | Thiết kế concurrency phù hợp với refresh token rotation |

Telemetry an toàn hơn có thể bao gồm:

~~~text
registrationId=company
authorizedClientFound=true
hasRefreshToken=true
accessTokenExpiresSoon=true
refreshResult=success
~~~

Không log client secret, access token, refresh token, authorization code, PKCE verifier, callback query chứa code/state hoặc toàn bộ object authorized client.

## 14. Sự cố thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| <code>loadAuthorizedClient</code> trả null | Sai registration/principal, chưa authorize hoặc token đã bị xóa | Đối chiếu khóa và lifecycle |
| Login thành công nhưng service không tìm thấy token | Repository dùng storage khác hoặc principal name không khớp | Kiểm tra wiring và <code>Authentication.getName()</code> |
| Token user A bị dùng cho user B | Cache chỉ keyed by provider hoặc principal tự khai | Dùng storage và principal đã xác thực |
| API trả 401 | Token hết hạn, sai issuer/audience hoặc đã bị revoke | Kiểm tra token và cấu hình Resource Server |
| API trả 403 | Không đủ scope/quyền | Kiểm tra authorization, không chỉ thời hạn token |
| <code>getRefreshToken()</code> null | Provider không cấp refresh token | Thiết kế flow không phụ thuộc refresh |
| Refresh thất bại <code>invalid_grant</code> | Refresh token hết hạn, dùng lại hoặc bị thu hồi | Xóa state lỗi, authorize lại nếu phù hợp |
| Mất token sau restart | In-memory service | Dùng persistent service nếu có yêu cầu |
| Chỉ một node đọc được token | Token nằm trong memory của node khác | Dùng storage chia sẻ hoặc thiết kế session/routing |
| Job chạy ngoài web request bị lỗi | Dùng web manager khi không có Servlet request | Dùng service manager |
| Logout rồi token vẫn tồn tại trong DB | Chưa có cleanup/revocation policy | Xóa authorized client và thu hồi token nếu cần |
| Cùng principal nhưng token của tenant khác | Key không phân biệt issuer/tenant | Thiết kế namespace và identity mapping |
| Code vẫn dùng token cũ sau refresh | Giữ reference quá lâu | Lấy token hiện hành qua manager/storage |

### 14.1. Quy trình chẩn đoán

~~~text
ClientRegistration có tồn tại?
  └── registrationId đúng?
       └── principalName có đúng Authentication?
            └── Service/Repository đang dùng storage nào?
                 └── Có OAuth2AuthorizedClient?
                      └── Access token còn hợp lệ?
                           ├── Có → kiểm tra audience/scope/Resource Server
                           └── Không → refresh/authorize có được hỗ trợ?
                                         └── storage có được cập nhật?
~~~

Đừng in token value khi điều tra. Dùng registration ID, loại lỗi, trạng thái có token, expiry và correlation ID an toàn.

## 15. Bài tập thực hành

### Bài 1 — Xác định số authorized clients

Hệ thống có:

~~~text
(company, an)
(company, binh)
(partner, an)
~~~

**Hỏi:** Cần ít nhất bao nhiêu mối liên kết authorized client độc lập?

**Giải thích:** Ba. Cùng provider nhưng khác principal phải có token riêng; cùng principal nhưng khác provider cũng là authorized client khác.

### Bài 2 — OAuth2AuthorizedClient có chứa ID Token không?

Một controller cần hiển thị subject, issuer và tên người dùng đã đăng nhập. Một service cần access token để gọi API.

**Giải thích:** Lấy OIDC identity từ <code>OidcUser</code>/<code>OidcIdToken</code> đã được xác minh; access token lấy từ <code>OAuth2AuthorizedClient</code> đúng registration/principal. Không dùng access token như ID Token.

### Bài 3 — Refresh token null

Authorized client đã có access token nhưng <code>getRefreshToken() == null</code>. Access token sắp hết hạn.

**Giải thích:** Đây có thể là trạng thái hợp lệ. Không cố gọi <code>getRefreshToken().getTokenValue()</code>. Dùng manager với provider/grant hỗ trợ hoặc yêu cầu người dùng authorize lại tùy luồng.

### Bài 4 — Background job

Một job dùng client credentials để lấy báo cáo hằng ngày; không có user session và HttpServletRequest.

**Giải thích:** <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> với provider <code>clientCredentials()</code> và principal tổng hợp ổn định phù hợp hơn một web manager đòi HTTP request. Principal tổng hợp không biến token service thành token user.

### Bài 5 — Token vẫn còn sau logout

Token được lưu JDBC. User logout khỏi web.

**Giải thích:** Không thể kết luận token đã bị thu hồi ở OP hoặc xóa ở database. Logout session, cleanup local và token revocation là các thao tác riêng.

### Bài 6 — Token sai audience

Client lấy access token được cấp cho API A rồi dùng gọi API B.

**Giải thích:** Không nên. API B có thể từ chối vì audience/scope/issuer khác. Phải lấy token có quyền hợp lệ dành cho API B và để Resource Server xác minh.

### Bài 7 — Thực hành trên ứng dụng thử

1. Tạo OIDC ClientRegistration với issuer, Client ID, secret và scopes hợp lệ.
2. Bật <code>oauth2Login()</code> và đăng nhập với người dùng thử.
3. Inject <code>OAuth2AuthorizedClientService</code> hoặc dùng <code>@RegisteredOAuth2AuthorizedClient</code> ở controller.
4. Quan sát registration ID, principalName, thời hạn access token và trạng thái có refresh token, **không in token value**.
5. Đăng nhập bằng user khác; đối chiếu kết quả tra cứu theo principal.
6. Thử khởi động lại khi dùng in-memory storage và so sánh với chính sách persistent storage nếu có.
7. Quan sát refresh/authorize behavior thông qua manager theo grant đã cấu hình.

## 16. Ghi nhớ

- <code>OAuth2AuthorizedClient</code> gắn **ClientRegistration**, **principalName**, **OAuth2AccessToken** và **OAuth2RefreshToken tùy chọn**.
- <code>ClientRegistration</code> lưu **cấu hình đăng ký Client**, không phải token của từng người dùng.
- Cặp <code>(registrationId, principalName)</code> là nền tảng phân biệt authorized clients trong các service mặc định. Principal key phải nhất quán, không lấy từ browser tùy ý và không va chạm giữa tenant.
- <code>OAuth2AuthorizedClientService</code> quản lý authorized clients theo registration/principal; <code>OAuth2AuthorizedClientRepository</code> phục vụ ngữ cảnh Servlet request.
- <code>OAuth2AuthorizedClientManager</code> phối hợp provider và storage để authorize hoặc refresh khi điều kiện/grant cho phép. Chỉ đọc token từ service không tự làm mới token.
- ID Token của OIDC chủ yếu thuộc <code>OidcUser</code>; authorized client chứa access/refresh token để gọi Resource Server đúng audience/scope.
- In-memory storage không tự tồn tại qua restart hoặc chia sẻ giữa nhiều instance; persistent storage cần bảo vệ credential và quản lý vòng đời.
- Logout, xóa local authorized client và token revocation là các cơ chế riêng. Không log hoặc trả giá trị token về browser.

### Tài liệu tham khảo

- **Spring Security Reference — OAuth2 Client:** OAuth2AuthorizedClient, ClientRegistration, Authorized Client Service/Repository và Authorized Client Manager.
- **Spring Security Reference — OAuth2 Login (Servlet):** Authorization Code Flow, callback và authorized-client persistence.
- **Spring Security Java API:** <code>OAuth2AuthorizedClient</code>, <code>OAuth2AuthorizedClientService</code>, <code>OAuth2AuthorizedClientRepository</code>, <code>OAuth2AuthorizedClientManager</code>, <code>OAuth2AuthorizeRequest</code>.
- **Spring Security Java API:** <code>InMemoryOAuth2AuthorizedClientService</code>, <code>JdbcOAuth2AuthorizedClientService</code>, <code>DefaultOAuth2AuthorizedClientManager</code>, <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Client, Access Token, Refresh Token, Authorization Code và Client Credentials Grants.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token tại Authorization Server.
- **OpenID Connect Core 1.0:** ID Token, Authorization Code Flow và quan hệ OIDC với OAuth2 Token Response.
