# Tích hợp ứng dụng Spring OAuth2 Client qua issuer discovery

## 1. Bối cảnh và mục tiêu

Trong chương **Tích hợp ứng dụng** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này hướng dẫn kết nối một ứng dụng Spring Boot với OpenID Provider/Authorization Server bằng Spring Security OAuth2 Client thông qua **issuer discovery**.

Module này học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Khi một ứng dụng khác sử dụng Authorization Server, nhóm phát triển không nên phải tự ghép từng URL authorization, token, JWKS và UserInfo cho mọi môi trường. Issuer discovery giúp client lấy metadata từ một issuer identifier đã được tin cậy rồi khởi tạo cấu hình provider nhất quán.

Ví dụ, doanh nghiệp có Authorization Server tại issuer https://login.example.com và một ứng dụng Portal dùng Spring Boot. Portal cần đăng nhập người dùng bằng OpenID Connect, sau đó gọi Orders API bằng Access Token. Thay vì hard-code authorization-uri, token-uri, jwk-set-uri và user-info-uri, Portal khai báo issuer-uri. Spring Security truy vấn Provider Configuration hoặc Authorization Server Metadata, lấy endpoint và key location từ metadata rồi tạo ClientRegistration.

Sau bài này, bạn có thể:

1. Phân biệt issuer identifier, provider metadata và client registration.
2. Cấu hình issuer-uri trong Spring Boot.
3. Hiểu quy trình discovery của ClientRegistrations.fromIssuerLocation.
4. Đăng nhập bằng Authorization Code Flow và PKCE.
5. Xử lý callback, session, ID Token và UserInfo.
6. Dùng OAuth2AuthorizedClientManager và WebClient để gọi API bằng Access Token.
7. Thực hiện logout tại ứng dụng và khởi tạo RP-Initiated Logout khi OP hỗ trợ.
8. Kiểm thử discovery, login, token relay và các lỗi issuer/redirect/JWKS.

## 2. Các thành phần trong mô hình tích hợp

| Thành phần | Trách nhiệm |
| --- | --- |
| OpenID Provider / Authorization Server | Xác thực End User, cấp ID Token và Access Token, công bố metadata |
| Issuer Identifier | Định danh duy nhất của OpenID Provider/Authorization Server |
| Provider Metadata | Công bố authorization endpoint, token endpoint, JWKS URI, UserInfo và các capability |
| ClientRegistration | Cấu hình một client đã đăng ký với provider |
| ClientRegistrationRepository | Lưu và tra cứu ClientRegistration theo registration ID |
| OAuth2LoginAuthenticationFilter | Xử lý callback Authorization Code của browser login |
| OAuth2AuthorizedClientRepository | Lưu authorized client gắn với principal/session trong ứng dụng Servlet |
| OAuth2AuthorizedClientService | Lưu authorized client theo service, phù hợp use case cần persistence |
| OAuth2AuthorizedClientManager | Điều phối authorization, refresh và cấp token cho outbound call |
| WebClient OAuth2 filter | Gắn Access Token phù hợp vào request gọi protected API |

### 2.1. Issuer khác registration ID

Issuer là danh tính của Authorization Server, ví dụ https://login.example.com/tenant-a. Registration ID là tên nội bộ do ứng dụng Spring đặt, ví dụ corporate. Một ứng dụng có thể có nhiều registration ID trỏ tới nhiều issuer hoặc nhiều client registration của cùng một provider. Registration ID xuất hiện trong URL login như /oauth2/authorization/corporate; nó không phải issuer, client ID hay tenant ID.

### 2.2. Issuer khác client_id

Issuer định danh Authorization Server. client_id định danh Portal trong hệ thống của Authorization Server. Một issuer có thể đăng ký hàng trăm client; một ứng dụng Spring cũng có thể khai báo nhiều registration tới các issuer khác nhau.

## 3. Issuer discovery hoạt động như thế nào?

OpenID Connect Discovery công bố Provider Configuration tại một endpoint well-known. Với issuer gốc https://login.example.com, endpoint thường là:

~~~text
https://login.example.com/.well-known/openid-configuration
~~~

Với issuer có path https://login.example.com/tenant-a, OIDC Provider Configuration thường được đặt tại:

~~~text
https://login.example.com/tenant-a/.well-known/openid-configuration
~~~

Response là JSON metadata, ví dụ:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "jwks_uri": "https://login.example.com/oauth2/jwks",
  "userinfo_endpoint": "https://login.example.com/userinfo",
  "end_session_endpoint": "https://login.example.com/connect/logout",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Đây là ví dụ rút gọn. Metadata thực tế có thể có nhiều field khác và giá trị phụ thuộc cấu hình provider.

### 3.1. Những metadata client cần

- authorization_endpoint: nơi browser được chuyển tới để người dùng xác thực và cấp quyền.
- token_endpoint: nơi client đổi authorization code lấy token hoặc refresh token.
- jwks_uri: nơi lấy public keys để xác minh chữ ký ID Token.
- userinfo_endpoint: nơi lấy thêm claims về End User nếu flow cần.
- issuer: giá trị issuer phải khớp issuer đã cấu hình và claim iss trong ID Token.
- end_session_endpoint: nơi RP khởi tạo logout nếu provider công bố và hỗ trợ RP-Initiated Logout.

Metadata cũng có thể công bố capability như grant types, response types, signing algorithms, scopes, authentication methods và PKCE support.

### 3.2. Discovery không tự đăng ký client

Discovery chỉ giúp ứng dụng biết provider endpoint và capability. Nó không tạo client_id, không cấp client_secret, không đăng ký redirect URI và không tự cấp quyền cho Portal.

Client vẫn phải được đăng ký trước tại Authorization Server. Giá trị client ID, secret hoặc public-client configuration được cung cấp qua quy trình onboarding riêng.

## 4. ClientRegistrations.fromIssuerLocation

Spring Security cung cấp ClientRegistrations.fromIssuerLocation(issuer) để tạo ClientRegistration.Builder từ metadata của issuer.

Với issuer có host và path, API này thử tuần tự các discovery endpoint sau và dùng response thành công đầu tiên:

1. host/.well-known/openid-configuration/path theo compatibility notes của RFC 8414.
2. issuer/.well-known/openid-configuration theo OpenID Connect Discovery.
3. host/.well-known/oauth-authorization-server/path theo OAuth 2.0 Authorization Server Metadata.

Nếu một endpoint trả về HTTP 200, metadata response được dùng để khởi tạo builder. Các response lỗi khác 200 hoặc 4xx có thể khiến quá trình dừng theo quy tắc của API; vì vậy cần cấu hình endpoint discovery chính xác và kiểm tra log khi khởi tạo thất bại.

### 4.1. Chỉ truy vấn OIDC discovery

Nếu muốn chỉ dùng OpenID Provider Configuration endpoint, có thể dùng:

~~~java
ClientRegistration registration =
        ClientRegistrations.fromOidcIssuerLocation(
                "https://login.example.com")
            .registrationId("portal")
            .clientId("portal-client")
            .clientSecret(clientSecret)
            .build();
~~~

fromIssuerLocation linh hoạt hơn khi provider hỗ trợ OAuth Authorization Server Metadata; fromOidcIssuerLocation chỉ tập trung vào OIDC discovery.

### 4.2. Issuer trong metadata phải chính xác

Client cần xác minh field issuer trong metadata khớp chính xác issuer đã cấu hình. Không tự thay issuer bằng hostname khác, bỏ path hoặc chuẩn hóa tùy ý. Khi xác minh ID Token, claim iss cũng phải khớp issuer tương ứng.

Không lấy issuer URI từ query parameter hoặc input tùy ý của người dùng rồi gọi discovery. Nếu cho phép cấu hình nhiều provider, dùng danh sách issuer tin cậy đã được quản trị để tránh SSRF và việc kết nối tới máy chủ không đáng tin.

## 5. Cấu hình Spring Boot bằng issuer-uri

Đây là cách cấu hình phổ biến nhất khi ứng dụng dùng Spring Boot auto-configuration.

### 5.1. Dependency

Với ứng dụng Servlet MVC:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Nếu ứng dụng dùng Spring MVC và WebClient, thêm spring-boot-starter-webflux để dùng WebClient API; không cần chuyển toàn bộ ứng dụng MVC thành WebFlux.

### 5.2. application.yml

Ví dụ ứng dụng Portal:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: company-idp
            client-id: ${PORTAL_OIDC_CLIENT_ID}
            client-secret: ${PORTAL_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: Company Login
        provider:
          company-idp:
            issuer-uri: https://login.example.com
~~~

Các biến PORTAL_OIDC_CLIENT_ID và PORTAL_OIDC_CLIENT_SECRET được nạp từ environment/secret manager. Không commit secret thật vào Git hoặc file cấu hình chia sẻ.

### 5.3. Ý nghĩa các thuộc tính

| Thuộc tính | Ý nghĩa |
| --- | --- |
| registration.portal | Registration ID do Portal đặt |
| provider: company-idp | Liên kết registration với provider cấu hình bên dưới |
| client-id | Client ID do Authorization Server cấp |
| client-secret | Secret của confidential client |
| client-authentication-method | Cách client xác thực tại Token Endpoint |
| authorization-grant-type | Flow mà client sử dụng |
| redirect-uri | Callback mà Spring Security xử lý |
| scope | Quyền client yêu cầu |
| issuer-uri | Issuer dùng cho provider discovery |

### 5.4. Không nhầm registration ID với provider ID

portal là registration ID; company-idp là provider ID. Nhiều registration có thể cùng tham chiếu một provider nhưng dùng client ID, secret, redirect URI hoặc scope khác nhau.

## 6. Cấu hình public client và PKCE

SPA hoặc native app không thể giữ client secret một cách đáng tin cậy. Khi ứng dụng là public client, cấu hình authentication method là none:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          desktop:
            provider: company-idp
            client-id: desktop-public-client
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company-idp:
            issuer-uri: https://login.example.com
~~~

Public client không có secret để chứng minh danh tính ở Token Endpoint. Authorization Code Flow cần PKCE để ràng buộc authorization code với client instance đã khởi tạo request.

Spring Security tự động thêm PKCE khi client registration thỏa cả hai điều kiện: không cấu hình client-secret (hoặc secret rỗng) và client-authentication-method là none. Ngoài ra, có thể yêu cầu PKCE bằng ClientRegistration.clientSettings.requireProofKey=true cho Authorization Code Flow. Nếu cần thay đổi cách tạo Authorization Request, có thể tùy chỉnh OAuth2AuthorizationRequestResolver. Ở phía Authorization Server, phải yêu cầu PKCE cho public client và xác minh code_verifier khi đổi code.

Không đặt một secret giả vào SPA/native app với mục đích biến nó thành confidential client. Secret có thể bị trích xuất từ package, binary, browser storage hoặc thiết bị người dùng.

## 7. Cấu hình OAuth2 Login

Khi đã có ClientRegistrationRepository, bật OAuth2 Login trong SecurityFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class PortalSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Spring Boot tự cấu hình ClientRegistrationRepository từ các property spring.security.oauth2.client.registration.* và provider.*. Nếu cần cấu hình repository bằng Java, có thể tạo ClientRegistration thủ công bằng ClientRegistrations.fromIssuerLocation.

### 7.1. URL bắt đầu đăng nhập

Với registration ID portal, Spring Security mặc định cung cấp URL:

~~~text
/oauth2/authorization/portal
~~~

Khi người dùng mở URL này:

1. Spring Security tìm ClientRegistration có registration ID portal.
2. Tạo Authorization Request với client ID, redirect URI, scope, state và nonce khi dùng OIDC.
3. Chuyển browser tới authorization endpoint lấy từ discovery.

Không điều hướng người dùng trực tiếp tới token endpoint. Token Endpoint không phải endpoint đăng nhập của browser.

### 7.2. Callback URL

Mặc định Spring Security xử lý callback theo pattern:

~~~text
/login/oauth2/code/*
~~~

Với redirect URI {baseUrl}/login/oauth2/code/{registrationId} và registration ID portal, callback thực tế có dạng:

~~~text
https://portal.example.com/login/oauth2/code/portal
~~~

URI này phải được đăng ký chính xác tại Authorization Server. Nếu đổi callback path, phải cấu hình cả redirect-uri và OAuth2LoginAuthenticationFilter/redirection endpoint tương ứng.

### 7.3. State và nonce

- state liên kết authorization response với request mà Portal đã khởi tạo, giúp chống CSRF/login response injection.
- nonce trong OIDC ràng buộc ID Token với authentication request, giúp phát hiện ID Token bị phát lại trong flow.

Không tắt state hoặc nonce validation để xử lý lỗi callback. Kiểm tra session/cookie, proxy, callback URL và việc ứng dụng có nhiều node nhưng không chia sẻ session.

## 8. Authorization Code Flow qua discovery

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Browser / End User
    participant APP as Spring Boot Portal
    participant OP as OpenID Provider
    participant API as Orders API
    APP->>OP: Discovery từ issuer-uri
    OP-->>APP: Provider metadata + jwks_uri
    U->>APP: GET /oauth2/authorization/portal
    APP-->>U: Redirect tới authorization_endpoint
    U->>OP: Authorization Request (code, state, nonce, PKCE)
    OP->>U: Authentication + Consent
    U-->>OP: User xác thực và chấp thuận
    OP-->>U: Redirect callback?code=...&state=...
    U->>APP: GET /login/oauth2/code/portal
    APP->>OP: POST token_endpoint (code + verifier)
    OP-->>APP: ID Token + Access Token
    APP->>APP: Verify ID Token và tạo Authentication
    APP-->>U: Session đăng nhập Portal
    APP->>API: Request với Bearer Access Token
    API-->>APP: Protected resource
~~~

### 8.1. Đổi authorization code

Spring Security thực hiện token request ở backend. Client cần:

- Gửi đúng authorization code.
- Dùng redirect URI đã gắn với authorization request.
- Xác thực tại Token Endpoint theo authentication method đã đăng ký.
- Gửi code_verifier nếu request dùng PKCE.

Authorization Server kiểm tra code, redirect URI, client authentication và PKCE trước khi phát hành token.

### 8.2. Xác minh ID Token

Với OIDC Login, Spring Security dùng provider metadata/JWKS để xác minh ID Token, bao gồm các điều kiện quan trọng:

- Chữ ký hợp lệ theo thuật toán/key được tin cậy.
- iss khớp issuer đã cấu hình.
- aud chứa client ID của Portal.
- exp và các thời điểm liên quan còn hợp lệ.
- nonce khớp giá trị request nếu đã gửi.

Không chỉ decode JWT rồi tin các claim. Decode payload không xác minh chữ ký, issuer hoặc audience.

### 8.3. ID Token khác Access Token

| Token | Dùng cho | Không dùng cho |
| --- | --- | --- |
| ID Token | Xác nhận authentication và subject cho OIDC Client | Gọi Orders API |
| Access Token | Truy cập resource server theo scope/audience | Làm bằng chứng đăng nhập thay cho ID Token |
| Refresh Token | Xin Access Token mới khi được cấp và còn hiệu lực | Gửi tới UserInfo hoặc API nghiệp vụ |

Portal không nên gửi ID Token tới API chỉ vì nó là JWT. API phải nhận Access Token có audience/resource phù hợp.

## 9. Lấy thông tin người dùng qua OIDC UserInfo

Khi scope có openid, Spring Security xử lý OIDC Login. Nếu provider công bố userinfo_endpoint, OidcUserService có thể gọi endpoint này bằng Access Token để lấy thêm claims.

Ví dụ controller:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("issuer", user.getIssuer().toString());
        result.put("subject", user.getSubject());
        result.put("name", user.getFullName());
        result.put("email", user.getEmail());
        result.put("emailVerified", user.getEmailVerified());
        return result;
    }
}
~~~

### 9.1. Subject là khóa nhận diện ổn định

Nên dùng cặp (iss, sub) để định danh user trong hệ thống tích hợp. Không dùng email làm khóa duy nhất vì email có thể đổi, có thể trùng hoặc có thể được tái cấp cho người khác.

Nếu provider dùng pairwise subject identifier, cùng một người có thể nhận sub khác nhau ở hai client. Portal phải lưu mapping theo issuer/client context đã được thiết kế, không tự suy luận hai subject là cùng người chỉ vì email trùng.

### 9.2. Scope và claims

| Scope | Claims tiêu biểu |
| --- | --- |
| openid | sub và OIDC authentication context |
| profile | name, given_name, family_name, preferred_username, picture, locale |
| email | email, email_verified |
| address | address |
| phone | phone_number, phone_number_verified |

Client chỉ nhận claims đã được cấp theo scope, consent và policy của provider. Không giả định thêm scope vào cấu hình Portal sẽ tự động làm provider trả dữ liệu nhạy cảm.

### 9.3. UserInfo sub phải khớp ID Token sub

Theo OIDC Core, sub trong UserInfo Response phải giống chính xác sub trong ID Token. Nếu khác, client phải không sử dụng UserInfo Response. Không ghép account bằng email hoặc username để bỏ qua mismatch này.

## 10. Lưu và sử dụng OAuth2AuthorizedClient

OAuth2AuthorizedClient liên kết:

- ClientRegistration.
- Principal name.
- Access Token.
- Refresh Token nếu có.

Trong ứng dụng Servlet, OAuth2AuthorizedClientRepository thường lưu authorized client gắn với principal/session. OAuth2AuthorizedClientService cung cấp persistence theo service và phù hợp khi ứng dụng cần quản lý authorized client độc lập với một request cụ thể.

Không tự lưu raw Access Token vào session attribute, cookie, localStorage hoặc log. Dùng abstraction của Spring Security để token lifecycle, refresh và authorization được quản lý nhất quán.

### 10.1. Gọi API bằng WebClient

Ví dụ cấu hình OAuth2AuthorizedClientManager và WebClient:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class OAuth2ClientHttpConfiguration {

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

    @Bean
    WebClient oauth2WebClient(OAuth2AuthorizedClientManager authorizedClientManager) {
        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
                new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                        authorizedClientManager);

        return WebClient.builder()
                .apply(oauth2.oauth2Configuration())
                .build();
    }
}
~~~

Ví dụ trên dành cho Servlet application có request/session context. Nếu chạy tác vụ nền hoặc service không có HttpServletRequest, hãy dùng AuthorizedClientServiceOAuth2AuthorizedClientManager cùng OAuth2AuthorizedClientService thay cho manager gắn với request.

Lưu ý về lỗi từ Resource Server: khi khởi tạo ServletOAuth2AuthorizedClientExchangeFilterFunction bằng constructor nhận OAuth2AuthorizedClientManager như ví dụ trên, filter không tự cấu hình failure handler để xóa authorized client khi Resource Server trả 401/403. Hãy cấu hình OAuth2AuthorizationFailureHandler phù hợp nếu muốn loại bỏ authorized client đã bị từ chối. Một lựa chọn khác là dùng constructor nhận ClientRegistrationRepository và OAuth2AuthorizedClientRepository; constructor này tự cấu hình RemoveAuthorizedClientOAuth2AuthorizationFailureHandler. Cơ chế này xử lý token bị Resource Server từ chối; nó khác với việc manager xóa authorized client khi refresh token trả invalid_grant.

### 10.2. Gọi Orders API với authorized client của người dùng

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

class OrdersClient {

    private final OAuth2AuthorizedClientManager authorizedClientManager;
    private final WebClient webClient;

    OrdersClient(
            OAuth2AuthorizedClientManager authorizedClientManager,
            WebClient oauth2WebClient) {
        this.authorizedClientManager = authorizedClientManager;
        this.webClient = oauth2WebClient;
    }

    String getOrders(String principalName) {
        OAuth2AuthorizeRequest authorizeRequest =
                OAuth2AuthorizeRequest.withClientRegistrationId("portal")
                        .principal(principalName)
                        .build();

        OAuth2AuthorizedClient client =
                authorizedClientManager.authorize(authorizeRequest);
        if (client == null) {
            throw new IllegalStateException("Unable to authorize Orders API call");
        }

        return webClient.get()
                .uri("https://api.example.com/orders")
                .attributes(
                        ServletOAuth2AuthorizedClientExchangeFilterFunction
                                .oauth2AuthorizedClient(client))
                .retrieve()
                .bodyToMono(String.class)
                .block();
    }
}
~~~

Đây là ví dụ đồng bộ hóa để minh họa; trong ứng dụng reactive end-to-end, không dùng block(). Với request thread Servlet, cần bảo đảm principalName là người dùng đã authenticated hiện tại và authorized client thuộc đúng registration.

### 10.3. Client Credentials cho service-to-service

Với machine-to-machine client, dùng registration riêng có grant client_credentials, confidential client authentication và scope API phù hợp. Không dùng registration OIDC Login của người dùng làm service account nếu policy khác nhau.

Ví dụ lấy token bằng manager:

~~~java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId("orders-service")
                .principal("orders-integration")
                .build();

OAuth2AuthorizedClient authorizedClient =
        authorizedClientManager.authorize(request);
~~~

Registration orders-service phải khai báo authorization-grant-type: client_credentials và một phương thức xác thực client được Authorization Server hỗ trợ. Principal name ở đây là định danh local cho authorized client service flow; nó không phải End User.

## 11. Cấu hình thủ công khi không dùng Boot properties

Có thể tạo registration bằng Java nếu ứng dụng nạp cấu hình từ tenant catalog hoặc cần kiểm soát cách khởi tạo:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration(proxyBeanMethods = false)
class ClientRegistrationConfiguration {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            OidcClientProperties properties) {

        ClientRegistration registration =
                ClientRegistrations.fromIssuerLocation(properties.issuerUri())
                        .registrationId("portal")
                        .clientId(properties.clientId())
                        .clientSecret(properties.clientSecret())
                        .clientAuthenticationMethod(
                                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                        .authorizationGrantType(
                                AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                        .scope("openid", "profile", "email")
                        .clientName("Company Login")
                        .build();

        return new InMemoryClientRegistrationRepository(registration);
    }
}
~~~

OidcClientProperties là class cấu hình do ứng dụng tự định nghĩa, không phải class Spring có sẵn. Có thể dùng @ConfigurationProperties để bind issuer URI, client ID và secret từ externalized configuration.

InMemoryClientRegistrationRepository phù hợp khi registration được nạp lúc khởi động và không thay đổi trong runtime. Nếu ứng dụng cần quản lý registration động hoặc nhiều tenant, hãy dùng repository/registry phù hợp và kiểm soát nguồn issuer.

## 12. Nhiều issuer và multi-tenant client

Một ứng dụng Spring có thể khai báo nhiều provider:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          tenant-a:
            provider: tenant-a-provider
            client-id: ${TENANT_A_CLIENT_ID}
            client-secret: ${TENANT_A_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile
          tenant-b:
            provider: tenant-b-provider
            client-id: ${TENANT_B_CLIENT_ID}
            client-secret: ${TENANT_B_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile
        provider:
          tenant-a-provider:
            issuer-uri: https://login.example.com/tenant-a
          tenant-b-provider:
            issuer-uri: https://login.example.com/tenant-b
~~~

Các issuer phải là giá trị đã được quản trị. Không tạo registration bằng cách lấy tenant từ URL rồi ghép thành issuer tùy ý. Nếu hỗ trợ tenant động, dùng tenant catalog/allowlist, xác minh domain và issuer, giới hạn số registration, cache discovery có kiểm soát và có cơ chế thu hồi.

### 12.1. Không trộn authorized client giữa tenant

Access Token được cấp bởi Tenant A không được gửi tới API của Tenant B nếu audience/resource policy không cho phép. Cache key và authorized client association phải bao gồm registration/issuer context.

Nếu cùng principal name tồn tại ở hai tenant, không dùng principal name làm khóa duy nhất cho dữ liệu ứng dụng. Dùng định danh có namespace theo issuer, thường là (iss, sub).

## 13. Discovery và vận hành khi Authorization Server ở sau reverse proxy

Issuer và endpoint công bố phải là URL public mà browser/client truy cập được. Ví dụ ứng dụng chạy nội bộ tại http://authorization-server:9000, nhưng public URL là https://login.example.com.

Provider metadata phải công bố:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "jwks_uri": "https://login.example.com/oauth2/jwks"
}
~~~

Nếu metadata chứa URL nội bộ hoặc issuer khác public host, OAuth2 Client có thể redirect tới endpoint không truy cập được hoặc từ chối ID Token do iss mismatch.

### 13.1. Cấu hình issuer phía Authorization Server

Ví dụ cấu hình tường minh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://login.example.com")
            .build();
}
~~~

Khi triển khai nhiều issuer trên cùng host, cách phân giải issuer cần nhất quán với multi-issuer configuration và request routing. Không đặt issuer cố định nếu deployment yêu cầu issuer thay đổi theo request.

### 13.2. Bật OIDC Provider Configuration

Spring Authorization Server cần bật OIDC để công bố OpenID Provider Configuration, UserInfo và Logout endpoint. Ví dụ với SecurityFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Đây là phần cấu hình cho protocol endpoints; ứng dụng hoàn chỉnh còn cần RegisteredClientRepository, OAuth2AuthorizationService, JWKSource, user authentication chain và các policy tương ứng. OIDC Client Registration Endpoint vẫn bị tắt mặc định; không cần bật endpoint đó chỉ để Spring OAuth2 Client dùng issuer discovery.

### 13.3. Forwarded headers

Nếu reverse proxy kết thúc TLS, Authorization Server cần biết public scheme/host/port/prefix khi tạo metadata và redirect URI. Cấu hình forwarded headers ở proxy và Spring Boot theo đúng topology, ví dụ server.forward-headers-strategy=framework khi phù hợp.

Chỉ tin forwarded headers từ proxy tin cậy đã ghi đè giá trị do client gửi. Nếu ứng dụng trực tiếp tin X-Forwarded-Host từ Internet, attacker có thể làm sai issuer hoặc URL trong metadata.

### 13.4. Kiểm tra metadata từ góc nhìn client

- issuer đúng tuyệt đối với issuer được cấu hình ở OAuth2 Client.
- Authorization, token và JWKS endpoint truy cập được từ network của client.
- Endpoint dùng HTTPS trong production.
- Không có hostname nội bộ hoặc path prefix bị mất.
- Chứng thư TLS hợp lệ và DNS trỏ đúng môi trường.

## 14. Logout từ Spring OAuth2 Client

Local logout mặc định của Spring Security xóa session tại Portal. Nó không tự động kết thúc SSO session ở OpenID Provider. Nếu OP công bố end_session_endpoint, Portal có thể dùng OidcClientInitiatedLogoutSuccessHandler để khởi tạo RP-Initiated Logout:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration(proxyBeanMethods = false)
class OidcLogoutConfiguration {

    @Bean
    LogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {

        OidcClientInitiatedLogoutSuccessHandler handler =
                new OidcClientInitiatedLogoutSuccessHandler(registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}");
        return handler;
    }
}
~~~

Inject handler vào SecurityFilterChain:

~~~java
@Bean
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http,
        LogoutSuccessHandler oidcLogoutSuccessHandler) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .logout(logout ->
            logout.logoutSuccessHandler(oidcLogoutSuccessHandler)
        );

    return http.build();
}
~~~

OP phải công bố endpoint, chấp nhận ID Token hint và đăng ký post-logout redirect URI tương ứng. Redirect URI phải được kiểm tra theo cấu hình của OP. Nếu OP không hỗ trợ RP-Initiated Logout, handler không thể tự tạo global logout.

Logout session không tự revoke mọi Access Token đã phát hành. Nếu nghiệp vụ yêu cầu thu hồi token, cần triển khai token revocation hoặc policy khác riêng.

## 15. Bảo mật ứng dụng tích hợp

### 15.1. Bảo vệ client secret

- Nạp secret từ secret manager hoặc environment injection.
- Không commit secret vào Git.
- Không ghi Authorization header, code hoặc token vào log.
- Rotate secret theo chính sách.
- Chọn private_key_jwt hoặc mTLS nếu yêu cầu bảo mật và hạ tầng hỗ trợ.

### 15.2. Redirect URI

Redirect URI phải được đăng ký chính xác tại Authorization Server. Dùng HTTPS trong production; không wildcard domain/path. Khi ứng dụng có nhiều môi trường, đăng ký callback riêng cho dev/staging/production và tránh dùng chung credential không cần thiết.

### 15.3. Session và CSRF

OAuth2 Login browser thường dựa trên session để lưu authorization request và SecurityContext. Giữ CSRF protection cho ứng dụng browser. Không tắt CSRF toàn cục chỉ để một endpoint callback hoạt động; callback OAuth2 có cơ chế kiểm tra state riêng.

### 15.4. Token storage và token relay

- Không lưu Access Token vào browser localStorage nếu không có threat model phù hợp.
- Không truyền ID Token tới Resource Server thay Access Token.
- Không gửi Access Token tới host tùy ý do user cung cấp.
- Chỉ relay token tới resource server đã được cấu hình tin cậy.
- Kiểm tra audience, scope và resource trước khi gọi API.
- Dùng TLS giữa client và Resource Server.

### 15.5. Discovery endpoint là đầu vào tin cậy

Issuer discovery khiến ứng dụng thực hiện outbound HTTP request tới metadata/JWKS URI. Chỉ dùng issuer đã được tin cậy, tránh SSRF và DNS rebinding. Giới hạn egress network, timeout, response size và redirect theo threat model.

Không cho phép người dùng gửi URL issuer bất kỳ rồi ứng dụng gọi URL đó. Với tenant onboarding, chỉ resolve issuer đã được admin xác minh.

### 15.6. Clock skew và thời gian

ID Token và JWT phụ thuộc exp, iat, nbf và nonce/time window. Đồng bộ clock giữa Authorization Server, client và Resource Server bằng NTP. Chỉ cấu hình clock skew hợp lý; không nới rộng thời hạn token để che lỗi clock.

## 16. Kiểm thử tích hợp

### 16.1. Kiểm thử discovery

Dùng WireMock/MockWebServer hoặc test provider để trả metadata. Xác minh:

1. Client truy vấn discovery URL đúng theo issuer.
2. Metadata có issuer, authorization endpoint, token endpoint và JWKS URI hợp lệ.
3. Issuer response mismatch bị phát hiện.
4. Metadata thiếu endpoint bắt buộc làm registration khởi tạo thất bại.
5. TLS/network timeout được xử lý và log đủ thông tin mà không lộ secret.

### 16.2. Kiểm thử OAuth2 Login với MockMvc

Spring Security Test cung cấp oidcLogin() để mô phỏng một user đã đăng nhập bằng OIDC:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@SpringBootTest
@AutoConfigureMockMvc
class OidcLoginIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedOidcUserCanReadProfile() throws Exception {
        mvc.perform(get("/api/me").with(oidcLogin()
                        .idToken(token -> token
                                .claim("iss", "https://login.example.com")
                                .subject("user-123")
                                .claim("name", "Nguyen An")
                                .claim("email", "an@example.com"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject").value("user-123"))
                .andExpect(jsonPath("$.email").value("an@example.com"));
    }
}
~~~

oidcLogin() tạo Authentication test cho controller/security authorization. Nó không kiểm thử discovery, code exchange, chữ ký ID Token hoặc token endpoint; các phần đó cần integration test với provider thật hoặc test server mô phỏng.

### 16.3. Kiểm thử Authorization Code Flow end-to-end

Một end-to-end test cần:

1. Khởi chạy Portal và test OP.
2. Xác minh discovery hoàn tất.
3. Bắt đầu /oauth2/authorization/portal.
4. Theo redirect tới authorization endpoint.
5. Xác thực user và consent tại test OP.
6. Redirect về callback với code và state.
7. Xác nhận Portal đổi code thành token.
8. Xác minh ID Token và tạo session.
9. Gọi /api/me và protected API.
10. Kiểm tra refresh token, logout và session cleanup theo policy.

### 16.4. Ma trận kiểm thử

| # | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| 1 | issuer-uri hợp lệ, discovery trả 200 | ClientRegistration được khởi tạo |
| 2 | Metadata issuer khác issuer cấu hình | Registration/token validation thất bại |
| 3 | Discovery URL không truy cập được | Lỗi khởi tạo/connection rõ ràng |
| 4 | Metadata thiếu token_endpoint | Client không khởi tạo registration hợp lệ |
| 5 | JWKS URI không truy cập được | ID Token validation thất bại |
| 6 | client_id không đúng | Authorization/token request bị từ chối |
| 7 | client_secret sai | Token request bị từ chối |
| 8 | Redirect URI chưa đăng ký | Authorization request bị từ chối |
| 9 | Callback state mismatch | Login response bị từ chối |
| 10 | ID Token issuer mismatch | Authentication thất bại |
| 11 | ID Token audience mismatch | Authentication thất bại |
| 12 | ID Token hết hạn | Authentication thất bại |
| 13 | Nonce mismatch | Authentication thất bại |
| 14 | UserInfo sub khác ID Token sub | UserInfo response không được sử dụng |
| 15 | Access Token không có scope API cần thiết | Resource Server trả lỗi quyền |
| 16 | Dùng ID Token gọi Orders API | Resource Server từ chối |
| 17 | Access Token hết hạn và có Refresh Token hợp lệ | AuthorizedClientManager refresh theo policy |
| 18 | Refresh Token bị revoke | Refresh thất bại; yêu cầu xác thực lại |
| 19 | Gọi API với client registration sai | Không gửi token sai audience/resource |
| 20 | Tenant A token dùng ở tenant B | Bị từ chối theo issuer/audience policy |
| 21 | Logout local | Portal session bị xóa |
| 22 | OP có end_session_endpoint | Handler khởi tạo RP-Initiated Logout |
| 23 | OP không công bố logout endpoint | Không giả định global logout |
| 24 | Reverse proxy làm mất forwarded scheme | Discovery/redirect URL không đúng và test phát hiện |
| 25 | User nhập issuer URI tùy ý | Bị chặn bởi issuer allowlist |

## 17. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Application startup lỗi khi dùng issuer-uri | Discovery endpoint không truy cập được hoặc metadata sai | Kiểm tra issuer, DNS, TLS, metadata và outbound network |
| /oauth2/authorization/portal trả 404 | Registration ID sai hoặc OAuth2 Login chưa bật | Kiểm tra registration ID và SecurityFilterChain |
| Authorization Server trả invalid_redirect_uri | Callback chưa đăng ký hoặc không exact match | Đồng bộ redirect-uri giữa Portal và RegisteredClient |
| Callback báo state mismatch | Session/cookie không được giữ hoặc proxy/callback domain sai | Kiểm tra cookie, session affinity và forwarded headers |
| invalid_client tại token endpoint | Client ID/secret/authentication method không khớp | Kiểm tra RegisteredClient và cấu hình client |
| invalid_grant khi đổi code | Code hết hạn, đã dùng hoặc redirect/PKCE mismatch | Kiểm tra code lifecycle và PKCE verifier |
| ID Token signature invalid | JWKS URI/key rotation/algorithm không đúng | Kiểm tra metadata, key set và signing algorithm |
| issuer mismatch | Public issuer và issuer trong metadata/token khác nhau | Cấu hình AuthorizationServerSettings và proxy |
| UserInfo 401 | Access Token thiếu/sai hoặc bị revoke | Kiểm tra token, scope và endpoint policy |
| UserInfo trả ít claims | Scope/consent/provider mapper chưa cho phép | Kiểm tra authorized scopes và claims release |
| WebClient không gắn token | AuthorizedClientManager/repository chưa cấu hình hoặc registration ID sai | Kiểm tra manager, authorized client và filter |
| API trả 401 dù login thành công | Access Token không đúng audience/resource | Cấp token cho API đúng và kiểm tra resource server |
| Refresh không hoạt động | Provider không cấp refresh token hoặc client không có scope/offline policy | Kiểm tra grant, consent và refresh token policy |
| Logout chỉ thoát Portal | Chưa cấu hình OIDC logout handler hoặc OP không hỗ trợ | Kiểm tra end_session_endpoint và post logout URI |
| Metadata trả hostname nội bộ | Forwarded headers hoặc issuer cấu hình sai | Sửa proxy trust và public issuer |

## 18. Vận hành và quan sát

Theo dõi các chỉ số:

- Discovery success/failure và latency.
- Login success/failure theo registration ID.
- Authorization callback errors: state, code exchange, redirect.
- Token endpoint latency và error code.
- ID Token/JWKS validation failures.
- UserInfo latency và lỗi.
- Authorized client refresh success/failure.
- Protected API response 401/403.
- Logout success và session cleanup.

Log nên ghi correlation ID, registration ID, issuer, endpoint, error code và thời gian xử lý. Không log authorization code, state thô nếu không cần, ID Token, Access Token, Refresh Token, client secret hoặc session cookie.

### 18.1. Key rotation

Authorization Server có thể thay signing key và công bố nhiều public keys trong JWKS trong giai đoạn chuyển tiếp. OAuth2 Client phải dùng JWKS URI đã discovery và xử lý kid phù hợp. Không pin một public key tĩnh nếu kiến trúc yêu cầu rotation tự động.

### 18.2. Cache metadata

Discovery và JWKS là dữ liệu được lấy qua network. Cần có cache/refresh policy phù hợp để tránh gọi metadata quá thường xuyên, nhưng vẫn cập nhật key khi rotation. Không cache metadata vô thời hạn hoặc dùng một metadata response cho issuer khác.

## 19. Checklist triển khai production

1. **Issuer:** cấu hình issuer canonical, HTTPS và nhất quán với metadata/ID Token.
2. **Discovery:** dùng issuer URI tin cậy; xác minh metadata issuer và endpoint.
3. **Registration:** client đã được đăng ký, redirect URI exact match.
4. **Credentials:** secret được lấy từ secret manager; public client không có secret giả.
5. **Grant:** dùng Authorization Code Flow; PKCE cho public clients và theo policy cho confidential clients.
6. **Scopes:** chỉ yêu cầu scope cần thiết; consent được xử lý ở OP.
7. **Callback:** state, nonce, session và redirect URI được kiểm tra.
8. **Tokens:** phân biệt ID Token, Access Token và Refresh Token.
9. **UserInfo:** dùng Access Token, kiểm tra sub consistency và claims policy.
10. **API calls:** dùng OAuth2AuthorizedClientManager, không tự ghép Bearer header từ token tùy ý.
11. **Audience:** Access Token được cấp cho đúng resource server.
12. **Logout:** local logout và RP-Initiated Logout được phân biệt rõ.
13. **Proxy:** forwarded headers chỉ được tin từ proxy đã xác thực.
14. **Multi-tenant:** issuer allowlist, registration isolation và cache key theo issuer.
15. **Observability:** không log credential/token; theo dõi discovery/login/token errors.
16. **Resilience:** timeout, DNS, TLS, JWKS rotation và provider outage có runbook.
17. **Testing:** có end-to-end test cho login, token, API call, refresh và logout.

## 20. Bài tập và câu hỏi tự đánh giá

**Bài tập A — Cấu hình issuer discovery.** Tạo Spring Boot Portal dùng issuer-uri của Authorization Server. Khai báo registration ID, client ID, redirect URI và scope phù hợp.

**Bài tập B — Discovery path.** Với issuer https://login.example.com/tenant-a, liệt kê các discovery endpoint mà ClientRegistrations.fromIssuerLocation có thể thử và giải thích khác biệt với fromOidcIssuerLocation.

**Bài tập C — Authorization Code Flow.** Vẽ luồng từ /oauth2/authorization/portal tới callback, code exchange, ID Token validation và session creation.

**Bài tập D — Token usage.** Giải thích vì sao Portal dùng Access Token để gọi Orders API và không gửi ID Token thay thế.

**Bài tập E — UserInfo.** Viết controller nhận OidcUser, trả (iss, sub) và một số profile claims. Bổ sung xử lý khi UserInfo sub mismatch.

**Bài tập F — WebClient.** Cấu hình OAuth2AuthorizedClientManager hỗ trợ authorization_code, refresh_token và client_credentials; viết service gọi API.

**Bài tập G — Multi-tenant.** Portal hỗ trợ hai issuer. Thiết kế allowlist issuer, hai registration và cách ngăn authorized client của tenant A được dùng cho tenant B.

**Bài tập H — Reverse proxy.** Authorization Server chạy HTTP nội bộ nhưng public HTTPS. Phân tích ảnh hưởng forwarded headers lên issuer, metadata và callback URL.

**Câu hỏi ôn tập:**

1. Issuer Identifier khác client ID và registration ID như thế nào?
2. Provider metadata công bố những endpoint nào?
3. Discovery có tự đăng ký client không?
4. issuer-uri được khai báo ở nhánh property nào của Spring Boot?
5. fromIssuerLocation khác fromOidcIssuerLocation ở đâu?
6. Vì sao metadata issuer phải khớp issuer cấu hình?
7. /oauth2/authorization/{registrationId} có vai trò gì?
8. Callback mặc định của Spring Security là gì?
9. state và nonce bảo vệ phần nào của flow?
10. ID Token và Access Token khác nhau ở đâu?
11. Khi nào OidcUserService gọi UserInfo?
12. Vì sao dùng (iss, sub) thay email làm định danh?
13. OAuth2AuthorizedClientManager quản lý những thao tác nào?
14. Khi nào dùng DefaultOAuth2AuthorizedClientManager, khi nào dùng AuthorizedClientServiceOAuth2AuthorizedClientManager?
15. Vì sao local logout không đồng nghĩa OP logout hoặc token revocation?
16. Làm thế nào ngăn SSRF qua issuer discovery?

## 21. Tài liệu tham khảo

- [Spring Boot — OAuth2 Client](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [Spring Security — OAuth2 Client Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — OAuth2 Client Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security — ClientRegistrations API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/registration/ClientRegistrations.html)
- [Spring Security — OIDC Client-Initiated Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)

**Ghi nhớ:** Spring OAuth2 Client có thể khởi tạo ClientRegistration từ một issuer đã tin cậy bằng issuer-uri. Discovery cung cấp endpoint và key metadata; nó không thay thế bước đăng ký client. OAuth2 Login dùng Authorization Code Flow, xử lý state/nonce và xác minh ID Token. Khi gọi API, dùng Access Token được quản lý qua OAuth2AuthorizedClientManager; không dùng ID Token thay Access Token. Local logout, OP logout và token revocation là các hành động riêng. Với multi-tenant, quản lý issuer bằng allowlist và giữ registration, token, cache cùng identity trong đúng tenant boundary.
