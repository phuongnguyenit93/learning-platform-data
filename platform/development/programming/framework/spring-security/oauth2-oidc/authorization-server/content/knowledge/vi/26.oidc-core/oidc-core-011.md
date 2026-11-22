# Phân biệt khả năng OIDC có sẵn với extension phải tự triển khai

## Mục tiêu bài học

Trong chương **OIDC Core và ID Token** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này giúp bạn xác định một ứng dụng dùng **Spring Security**, **Spring Authorization Server** và **Spring Boot** thực sự hỗ trợ những phần nào của OpenID Connect (OIDC), phần nào chỉ cần bật/cấu hình, phần nào cần mở rộng nghiệp vụ và phần nào thuộc các đặc tả OIDC riêng.

OIDC là lớp định danh trên OAuth 2.0. Một hệ thống có thể phát JWT access token và chạy Authorization Code Flow nhưng chưa chắc đã là một OpenID Provider tương thích OIDC. OIDC còn quy định Discovery, ID Token, UserInfo, Authentication Request, claims, logout và nhiều tùy chọn mở rộng.

Việc framework có một endpoint hoặc một configurer cũng không đồng nghĩa mọi yêu cầu của đặc tả đã được triển khai đầy đủ. Ví dụ:

- Spring Authorization Server 1.5.8 có OIDC Provider Configuration, UserInfo và RP-Initiated Logout tích hợp khi bật OIDC.
- OIDC Dynamic Client Registration cũng có implementation nhưng endpoint **tắt mặc định** và cần bearer access token với scope phù hợp.
- ID Token có thể được framework phát hành trong OIDC Authorization Code Flow; nhưng policy **max_age**, **auth_time**, ACR/MFA, pairwise subject, claim release động hoặc account linking vẫn có thể cần logic ứng dụng.
- RP-Initiated Logout không đồng nghĩa đã có Session Management, Front-Channel Logout hoặc Back-Channel Logout.
- Request Object, claims request, prompt, locale và các tham số OIDC tùy chọn phải được đánh giá theo behavior thực tế của phiên bản và cấu hình.

### Kết quả mong đợi

Sau bài học, bạn có thể:

1. Phân biệt OAuth 2.0 Authorization Server, OpenID Provider (OP), Relying Party (RP) và OAuth2 Resource Server.
2. Phân loại tính năng thành **built-in**, **built-in nhưng phải bật**, **cần cấu hình**, **cần custom implementation**, **đặc tả riêng** hoặc **chưa kiểm chứng**.
3. Liệt kê các OIDC endpoints có trong Spring Authorization Server 1.5.8 và biết endpoint nào mặc định tắt.
4. Hiểu ranh giới giữa Provider Configuration/Discovery, ID Token, UserInfo, RP-Initiated Logout và Dynamic Client Registration.
5. Dùng extension points của Spring Authorization Server mà vẫn giữ validation, authentication provider và response handler chuẩn.
6. Nhận diện các khả năng không tự xuất hiện như max_age enforcement, auth_time, ACR/MFA policy, pairwise subject, claim policy, front/back-channel logout và federation.
7. Thiết kế capability matrix, metadata chính xác và integration/conformance tests theo đúng phiên bản triển khai.
8. Tránh quảng cáo hoặc công bố một tính năng OIDC chỉ vì framework nhận được tham số hoặc có tên API tương tự.

> **Tình huống xuyên suốt:** Công ty triển khai **auth.example.com** bằng Spring Authorization Server. Nhóm sản phẩm muốn công bố đây là OpenID Provider cho **employee-portal**, **mobile-app** và đối tác. Trước khi phát hành, nhóm cần trả lời: Discovery có hoạt động không? ID Token có đúng contract không? UserInfo có lọc scope không? Logout có thông báo tới các RP không? Dynamic Client Registration có mở cho ai? Các yêu cầu MFA và pairwise subject được thực thi ở đâu?

## 1. Phân biệt các lớp tiêu chuẩn

### 1.1. OAuth 2.0 và OpenID Connect giải quyết hai bài toán khác nhau

| Thành phần | Vai trò | Kết quả chính |
|---|---|---|
| OAuth 2.0 Authorization Server | Cấp access token cho client theo grant và authorization policy. | Access token và các token liên quan. |
| OpenID Provider (OP) | Thực hiện xác thực End-User và cung cấp lớp identity theo OIDC. | ID Token, UserInfo và OIDC Provider Metadata. |
| Relying Party (RP) / OIDC Client | Gửi Authentication Request, xác minh ID Token và sử dụng danh tính. | Phiên đăng nhập của ứng dụng. |
| OAuth2 Resource Server | Bảo vệ API bằng access token. | Quyết định request API có được phép không. |

Một JWT có claim **sub** không tự biến nó thành ID Token. ID Token phải đáp ứng các yêu cầu OIDC về issuer, audience, thời gian, chữ ký, nonce khi áp dụng và các claim bắt buộc theo flow.

Tương tự, access token có thể là JWT nhưng không nên được client dùng như bằng chứng đăng nhập OIDC. Client phải xác minh ID Token theo OIDC Core.

### 1.2. OIDC không phải một endpoint đơn lẻ

OIDC gồm các đặc tả liên quan:

| Đặc tả | Phạm vi |
|---|---|
| **OpenID Connect Core 1.0** | Authentication Request, ID Token, UserInfo, claims và các flow xác thực. |
| **OpenID Connect Discovery 1.0** | Cách RP tìm metadata của OP. |
| **OpenID Connect Dynamic Client Registration 1.0** | Đăng ký và đọc cấu hình client động. |
| **OpenID Connect RP-Initiated Logout 1.0** | RP yêu cầu OP đăng xuất End-User. |
| **OpenID Connect Session Management 1.0** | Theo dõi/truy vấn trạng thái phiên OIDC giữa RP và OP. |
| **OpenID Connect Front-Channel Logout 1.0** | OP thông báo logout tới RP thông qua User Agent/browser. |
| **OpenID Connect Back-Channel Logout 1.0** | OP gửi logout notification trực tiếp tới RP qua back-channel. |
| **OpenID Connect Federation** | Thiết lập trust và metadata giữa các OP/RP theo mô hình federation. |

Spring Authorization Server có thể hỗ trợ một số endpoint trong các đặc tả này, nhưng không nên suy rộng từ một đặc tả sang tất cả. Đặc biệt, RP-Initiated Logout độc lập với ba cơ chế Session Management, Front-Channel và Back-Channel Logout.

### 1.3. Bốn lớp phải kiểm tra khi nói “đã hỗ trợ OIDC”

1. **Protocol surface:** endpoint, method, request/response và metadata có tồn tại.
2. **Protocol semantics:** server có thực hiện đúng ý nghĩa của parameter, claim, error và state transition.
3. **Security policy:** authentication, consent, subject binding, token validation, session và privacy có đúng policy.
4. **Interoperability:** RP thật có thể Discovery, login, validate ID Token, gọi UserInfo, logout và xử lý lỗi thành công.

Chỉ kiểm tra HTTP 200 hoặc endpoint trả JSON không đủ chứng minh một feature đã tương thích.

## 2. Ma trận OIDC tích hợp trong Spring Authorization Server 1.5.8

Spring Authorization Server 1.5.8 cung cấp các endpoint OIDC sau khi bật OIDC:

| Tính năng | Trạng thái trong SAS 1.5.8 | Điều kiện / giới hạn chính |
|---|---|---|
| OIDC Provider Configuration | Built-in, được bật cùng OIDC. | Metadata phải phản ánh issuer, endpoints và capabilities thực tế. |
| ID Token cho OIDC Authorization Code Flow | Built-in. | Client phải yêu cầu **openid**; cần cấu hình signing/JWK và client đúng. |
| OIDC UserInfo | Built-in, được bật cùng OIDC. | Access token Bearer; cần **JwtDecoder** bean; default mapper lấy standard claims từ ID Token theo scope. |
| RP-Initiated Logout | Built-in, được bật cùng OIDC. | Sử dụng **SessionRegistry**; cần kiểm session lifecycle và redirect validation. |
| OIDC Dynamic Client Registration / Client Read | Có implementation, **disabled by default**. | Phải bật endpoint; bearer token cần scope **client.create** hoặc **client.read**; cần **JwtDecoder**. |
| JWK Set Endpoint | Built-in khi có **JWKSource<SecurityContext>** bean. | Phải quản lý key lifecycle, kid, rotation và public JWKS. |
| OAuth2 Authorization Server Metadata | Built-in. | Khác với OIDC Provider Configuration; không nhầm hai metadata documents. |
| OIDC claims tùy chỉnh trong ID Token | Có extension point. | **OAuth2TokenCustomizer<JwtEncodingContext>** chỉ thêm/sửa claims; không tự thi hành authentication policy. |
| Custom UserInfo claims | Có extension point. | Mapper thay thế phải tự giữ scope filtering, sub, consent và privacy. |
| Custom logout validation/behavior | Có extension point. | Phải giữ redirect URI validation và session security. |

**Phạm vi phiên bản của bài:** các nhận định về API và endpoint ở phần Spring tập trung vào **Spring Authorization Server 1.5.8**. Nếu dùng Spring Authorization Server 1.4.x, Spring Security 7.x Authorization Server hoặc một phiên bản khác, hãy kiểm tra API và integration tests của đúng dependency đang chạy.

### 2.1. Bật OIDC trong SecurityFilterChain

Ví dụ cấu hình khung:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(Customizer.withDefaults())
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là cấu hình OIDC baseline. Ứng dụng hoàn chỉnh còn cần các bean như **RegisteredClientRepository**, **OAuth2AuthorizationService**, **AuthorizationServerSettings**, **JWKSource<SecurityContext>**, **JwtDecoder**, login **SecurityFilterChain**, session management và persistence.

Khi bật OIDC theo cách trên, SAS 1.5.8 cấu hình các endpoint Provider Configuration, Logout và UserInfo. Client Registration endpoint vẫn tắt mặc định.

### 2.2. Các endpoint và đường dẫn mặc định

| Endpoint | Đường dẫn thường dùng trong SAS 1.5.8 | Trạng thái |
|---|---|---|
| OIDC Provider Configuration | `/.well-known/openid-configuration` | Được bật khi bật OIDC. |
| JWK Set | `/oauth2/jwks` | Được cấu hình khi có JWKSource bean. |
| UserInfo | `/userinfo` | Được bật khi bật OIDC; cần JwtDecoder. |
| RP-Initiated Logout | `/connect/logout` | Được bật khi bật OIDC. |
| OIDC Client Registration / Read | `/connect/register` | Có implementation nhưng disabled by default; cần JwtDecoder và bearer scopes. |

Các đường dẫn có thể được thay bằng **AuthorizationServerSettings**. Builder có các setting tương ứng như **oidcUserInfoEndpoint(...)**, **oidcLogoutEndpoint(...)** và **oidcClientRegistrationEndpoint(...)**. Nếu đổi path, Discovery metadata phải phản ánh đường dẫn mới.

### 2.3. JWKSource và JwtDecoder

JWK Set endpoint được cấu hình khi ứng dụng đăng ký **JWKSource<SecurityContext>**. UserInfo và OIDC Client Registration endpoint yêu cầu **JwtDecoder** bean trong cấu hình SAS 1.5.8.

Ví dụ:

~~~java
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Đây là helper của Spring Authorization Server để tạo decoder theo JWK source. Trong production, cần kiểm tra issuer, key source, thuật toán, key rotation và trust boundary. Không dùng JWK set tự chọn từ một URL do request gửi lên.

### 2.4. Phân biệt OIDC Provider Configuration và OAuth2 Authorization Server Metadata

Hai metadata endpoints có mục đích gần nhau nhưng là hai protocol documents khác nhau:

| Document | Tiêu chuẩn | Nội dung |
|---|---|---|
| Authorization Server Metadata | RFC 8414 | OAuth2 endpoints và capabilities như authorization endpoint, token endpoint, scopes, grant types. |
| OpenID Provider Configuration | OpenID Connect Discovery 1.0 | OIDC issuer, authorization/token/JWKS/UserInfo endpoints, supported subject types, signing algorithms, claims và OIDC capabilities. |

Một OP có thể phục vụ cả hai. RP OIDC cần lấy OIDC Provider Configuration theo Discovery, sau đó xác minh issuer và các endpoint metadata. Không dùng metadata OAuth2 thay thế OIDC Discovery chỉ vì JSON có nhiều field giống nhau.

## 3. Discovery: endpoint có sẵn, metadata vẫn cần chính xác

### 3.1. Provider Configuration endpoint

OIDC Discovery cung cấp Provider Configuration document, thường tại:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: auth.example.com
Accept: application/json
~~~

Metadata có các field như:

- **issuer**
- **authorization_endpoint**
- **token_endpoint**
- **jwks_uri**
- **userinfo_endpoint**
- **end_session_endpoint** khi có logout endpoint
- **response_types_supported**
- **subject_types_supported**
- **id_token_signing_alg_values_supported**
- **scopes_supported**
- **claims_supported**
- **grant_types_supported**
- Các capability flags như **claims_parameter_supported** hoặc **request_parameter_supported** nếu được OP hỗ trợ.

Tên và tính bắt buộc của field được quy định trong OIDC Discovery. Không tự thêm một flag chỉ để client hiển thị nút/tính năng.

### 3.2. Tùy chỉnh metadata bằng configurer

SAS cung cấp **providerConfigurationEndpoint(...)** và **providerConfigurationCustomizer(...)** để tùy chỉnh Provider Configuration response.

Ví dụ vị trí cấu hình:

~~~java
.oidc(oidc -> oidc
    .providerConfigurationEndpoint(providerConfiguration ->
        providerConfiguration.providerConfigurationCustomizer(
            providerConfigurationCustomizer
        )
    )
)
~~~

**providerConfigurationCustomizer** là component do ứng dụng cung cấp. Có thể dùng nó để bổ sung hoặc điều chỉnh metadata khi protocol implementation thực sự đáp ứng capability tương ứng.

Không quảng cáo:

- **claims_parameter_supported=true** nếu server chưa xử lý claims request.
- **request_parameter_supported=true** nếu Request Object chưa được xác minh và xử lý.
- Một ACR/AMR hoặc signing algorithm chưa được thực thi.
- Front-channel/back-channel logout URI khi chưa triển khai protocol tương ứng.
- Scope hoặc grant type không thể được cấp trong Token Endpoint.

Metadata là contract công khai của OP. Khi thay đổi endpoint hoặc capability, hãy kiểm tra lại Discovery document và chạy client interoperability tests.

### 3.3. Issuer phải ổn định

Cấu hình issuer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

Issuer cần ổn định giữa Discovery, ID Token, access token và JWKS. Không để một request tùy ý quyết định issuer khi hệ thống có nhiều hostname hoặc reverse proxy chưa được trust đúng cách.

Client phải so sánh **iss** trong ID Token với issuer đã discovery. Nếu issuer thay đổi, đây là thay đổi trust domain và cần migration rõ ràng.

## 4. ID Token: framework phát hành, ứng dụng chịu trách nhiệm về policy

### 4.1. ID Token không phải JWT tùy ý

OIDC ID Token là một JWT có contract riêng. Các claim cốt lõi thường gồm:

| Claim | Ý nghĩa |
|---|---|
| **iss** | Issuer của OP. |
| **sub** | Subject identifier của End-User. |
| **aud** | Client ID hoặc audience được phép nhận ID Token. |
| **exp** | Thời điểm ID Token hết hạn. |
| **iat** | Thời điểm ID Token được phát hành. |
| **auth_time** | Thời điểm End-User được xác thực, khi được yêu cầu/áp dụng. |
| **nonce** | Giá trị ràng buộc Authentication Request với ID Token nếu request gửi nonce. |
| **azp** | Authorized party khi áp dụng, đặc biệt trong trường hợp nhiều audience. |
| **acr**, **amr** | Authentication Context Class Reference / Authentication Methods References khi OP hỗ trợ. |

SAS có thể phát ID Token trong OIDC Authorization Code Flow. RP vẫn phải xác minh chữ ký, issuer, audience, thời gian, nonce và các yêu cầu OIDC liên quan. Không coi token đã decode được là token đã được xác minh.

### 4.2. Thêm custom claims bằng OAuth2TokenCustomizer

SAS có extension point **OAuth2TokenCustomizer<JwtEncodingContext>** để tùy chỉnh JWT được tạo. Nếu thêm claim vào ID Token, phải giới hạn theo token type:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.oidc.endpoint.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> oidcTokenCustomizer() {
    return context -> {
        if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {

            // Chỉ lấy dữ liệu từ nguồn đã xác thực và được phép tiết lộ.
            context.getClaims().claim("employee_tier", "standard");
        }
    };
}
~~~

Ví dụ chỉ minh họa cách gắn claim; **employee_tier** phải có nguồn dữ liệu, consent/privacy policy và contract với RP. Không đưa dữ liệu nhạy cảm hoặc claim không ổn định vào ID Token chỉ vì customizer cho phép.

### 4.3. Customizer không tự thi hành OIDC semantics

| Yêu cầu | Customizer có tự giải quyết không? | Phần cần làm |
|---|---|---|
| Thêm claim department | Có thể thêm giá trị. | Xác minh nguồn, quyền tiết lộ và schema. |
| max_age | Không. | Đo tuổi lần xác thực thực tế, reauthenticate khi quá hạn. |
| auth_time | Chỉ có thể thêm claim. | Phải lưu timestamp của authentication thật, không dùng iat/now. |
| acr | Không tự chứng minh assurance. | Thực thi authentication policy và chỉ phát ACR đã đạt. |
| amr | Không tự biết phương thức đăng nhập. | Lưu bằng chứng method đã thực hiện và phát đúng giá trị. |
| Pairwise sub | Không tự tạo sector identifier mapping. | Xây subject mapping bền vững, không thể đảo ngược và ổn định theo client sector. |
| nonce | Không chỉ là custom claim tùy ý. | Giữ liên kết request/authorization/token theo flow chuẩn. |
| Essential claims từ claims parameter | Không. | Parse, validate, đáp ứng hoặc từ chối request theo OIDC semantics. |

**Nguyên tắc:** claim là dữ liệu kết quả của policy. Không tạo một claim để giả lập rằng policy đã được thực thi.

## 5. UserInfo: có sẵn, nhưng nguồn claim có thể cần mở rộng

### 5.1. Default UserInfo mapper

SAS 1.5.8 có **OidcUserInfoEndpointFilter** và **OidcUserInfoAuthenticationProvider**. Default mapper trích xuất standard claims từ ID Token theo các scopes được yêu cầu trong authorization flow.

UserInfo endpoint là OAuth2 protected resource:
- Client gửi access token dạng Bearer.
- Endpoint xác minh access token.
- SAS 1.5.8 yêu cầu **JwtDecoder** bean.
- Response trả claims theo mapper.

### 5.2. Khi nào cần custom mapper?

Cần custom mapper khi:
- Profile phải lấy từ database/LDAP mới nhất.
- Có claim domain-specific.
- Cần claim visibility theo tenant, privacy setting hoặc consent.
- Cần mapping giữa internal user ID và stable OIDC subject.
- Cần chính sách không trả profile của user đã bị disable/deprovisioned.
- Cần kiểm soát claims theo scope hoặc policy bổ sung.

**OidcUserInfoEndpointConfigurer.userInfoMapper(...)** nhận **OidcUserInfoAuthenticationContext** và trả **OidcUserInfo**. Khi thay default mapper, ứng dụng phải tự giữ scope filtering, **sub** bắt buộc, claim omission và privacy.

### 5.3. Client phải xác minh subject binding

Theo OIDC Core, UserInfo Response phải có **sub**. RP phải so sánh chính xác **sub** này với **sub** của ID Token; nếu không khớp thì không được sử dụng response.

Việc mapper trả **sub** đúng là chưa đủ. RP phải kiểm tra. Đây là bảo vệ chống trộn access token và ID Token từ hai session/người dùng khác nhau.

## 6. RP-Initiated Logout: tích hợp không đồng nghĩa logout toàn hệ sinh thái

### 6.1. Endpoint có sẵn

SAS 1.5.8 có OIDC RP-Initiated Logout endpoint, mặc định thường là:

~~~http
GET /connect/logout?id_token_hint=...&post_logout_redirect_uri=... HTTP/1.1
Host: auth.example.com
~~~

Client cũng có thể dùng Spring Security OAuth2 Client **OidcClientInitiatedLogoutSuccessHandler** để điều hướng người dùng tới OP logout endpoint.

SAS **OidcLogoutAuthenticationProvider** dùng **SessionRegistry** để tìm **SessionInformation** liên quan tới End-User và thực hiện logout. Nếu dùng **SessionRegistryImpl**, tài liệu khuyến nghị đăng ký **HttpSessionEventPublisher** để session lifecycle events được cập nhật.

### 6.2. Những gì RP-Initiated Logout không tự giải quyết

RP-Initiated Logout định nghĩa cách RP yêu cầu OP logout. Nó không tự động đồng nghĩa với:

- Thông báo logout đến mọi RP đang đăng nhập.
- Front-Channel Logout qua browser.
- Back-Channel Logout qua HTTP request từ OP đến RP.
- OIDC Session Management iframe/session state.
- Revoke mọi access token/refresh token đã phát.
- Logout khỏi upstream Identity Provider hoặc hệ thống federation.
- Xóa application session ở tất cả thiết bị/replica nếu không có session strategy tương ứng.

Các tính năng Session Management, Front-Channel Logout và Back-Channel Logout là các đặc tả riêng. Nếu yêu cầu “logout mọi ứng dụng”, cần triển khai cơ chế thông báo tới RP, quản lý session và token revocation tương ứng.

### 6.3. Cấu hình SessionRegistry

Ví dụ khi dùng session registry mặc định của Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

Đây là phần cấu hình session tracking; không tự tạo front/back-channel logout. Trong hệ thống cluster, phải chọn session registry/distributed session strategy phù hợp để logout lookup không phụ thuộc trạng thái local của một node.

## 7. Dynamic Client Registration: có implementation nhưng mặc định tắt

### 7.1. OIDC Client Registration endpoint trong SAS 1.5.8

SAS 1.5.8 có **OidcClientRegistrationEndpointConfigurer**, hỗ trợ:
- Client Registration request.
- Client Read request.
- Custom converter/provider.
- Custom response/error handler.

Endpoint **disabled by default**. Đây là chủ đích: nhiều deployment không muốn bất kỳ client registrar nào có thể tạo client mới.

Endpoint là OAuth2 protected resource:
- Registration request cần access token có scope **client.create**.
- Client Read request cần access token có scope **client.read**.
- **JwtDecoder** bean được yêu cầu cho endpoint.
- Default endpoint path thường là **/connect/register**.

### 7.2. Bật endpoint

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer configurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(configurer.getEndpointsMatcher())
        .with(configurer, authorizationServer ->
            authorizationServer.oidc(oidc ->
                oidc.clientRegistrationEndpoint(Customizer.withDefaults())
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đoạn code chỉ bật endpoint. Nó không phải chính sách đăng ký công khai an toàn hoàn chỉnh.

### 7.3. Registrar client và scope

Một registrar client hiện có có thể dùng Client Credentials để lấy initial access token có scope **client.create**. Nếu registrar cần đọc registration sau khi tạo, có thể được cấp thêm **client.read** theo policy.

~~~java
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient registrar = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("client-registrar")
        .clientSecret(passwordEncoder.encode(registrarSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();
~~~

Đây là ví dụ cấu hình registrar; secret phải được quản lý an toàn và **RegisteredClientRepository** production phải lưu bền vững. Không cấp **client.create** cho mọi ứng dụng chỉ vì cần đăng nhập.

Để lấy initial access token, registrar dùng grant **client_credentials** với scope **client.create**. Request đăng ký gửi bearer token này tới Client Registration endpoint. Khi đọc một registration, dùng access token được cấp quyền **client.read**. Các scope này là quyền đặc biệt của registrar; không đưa chúng vào scope của end-user client.

Ví dụ request lấy initial access token:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_REGISTRAR_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
~~~

Registrar phải được đăng ký grant **client_credentials** và chỉ được cấp scope quản trị cần thiết. Không dùng access token của end-user làm initial access token cho endpoint này.

### 7.4. Dynamic Registration vẫn cần policy riêng

Trước khi mở endpoint, hãy quyết định:
- Ai được phép tạo client?
- Client có được tự chọn grant type, redirect URI, authentication method và scope không?
- Có redirect URI allowlist, domain verification và review không?
- Ai được đọc hoặc cập nhật registration?
- Client registration access token được lưu và rotate ra sao?
- Có quota, rate limit, audit, tenant boundary và abuse detection không?
- Client public/confidential được phân biệt thế nào?
- Registration metadata nào được phép ghi?
- Khi client bị compromise, ai disable/rotate/revoke?

Không bật Dynamic Client Registration trên production chỉ để “có OIDC endpoint”. Endpoint này thay đổi trust boundary và có thể cho phép attacker tạo OAuth client độc hại nếu registrar policy yếu.

## 8. Các tính năng OIDC Core tùy chọn cần đánh giá riêng

OIDC Core định nghĩa nhiều tham số OPTIONAL. OPTIONAL nghĩa là OP có thể không hỗ trợ; nếu công bố hỗ trợ thì phải thi hành semantics đúng. Không nên nhầm việc parameter được parse vào additional parameters với việc protocol đã được hỗ trợ.

| Tính năng | Ý nghĩa tiêu chuẩn | Cách đánh giá trong SAS 1.5.8 |
|---|---|---|
| prompt | Điều khiển login, consent, account selection hoặc silent request. | Kiểm tra behavior của Authorization Endpoint, login entry point, consent và error redirect theo đúng version. |
| max_age / auth_time | Re-auth khi authentication quá cũ; ID Token có auth_time. | Cần trusted authentication timestamp và policy reauthentication; customizer chỉ thêm claim. |
| login_hint | Gợi ý danh tính. | Có thể cần login UI integration; tuyệt đối không dùng làm credential. |
| id_token_hint | Gợi ý session/subject bằng ID Token đã phát. | Phải kiểm trust, client/session binding và behavior thực tế. |
| acr_values | Yêu cầu authentication context. | Cần ACR mapping và step-up authentication thật. |
| claims request parameter | Yêu cầu claims cụ thể trong ID Token/UserInfo. | Cần parser, essential-claim handling, consent và claim policy; không mặc định có đủ chỉ vì mapper hỗ trợ custom claims. |
| request / Request Object | JWT chứa authorization parameters. | Cần kiểm hỗ trợ JAR, signature, encryption, client trust và parameter precedence. |
| request_uri | Tham chiếu Request Object. | Phải phân biệt OIDC Request URI với PAR URI; kiểm SSRF và trust. |
| ui_locales | Gợi ý ngôn ngữ UI. | Cần login/consent UI thực sự dùng locale. |
| display | Gợi ý cách trình bày UI. | Không làm yếu browser security để hỗ trợ popup/touch. |
| Pairwise subject | sub khác nhau theo sector/client grouping. | Cần subject mapping bền vững, sector identifier và privacy policy; không suy ra từ custom claim đơn giản. |

### 8.1. Prompt và max_age

OIDC Core yêu cầu semantics của **prompt=none**, **prompt=login**, **prompt=consent** và **prompt=select_account**. Ví dụ **prompt=none** không được hiển thị UI; nếu cần login/consent/selection thì trả OIDC error.

**max_age** yêu cầu OP reauthenticate nếu lần xác thực thực tế đã quá cũ; khi dùng, ID Token phải có **auth_time**. Không dùng thời điểm phát ID Token làm auth_time nếu người dùng chưa xác thực lại.

Spring Authorization Server có extension points ở Authorization Endpoint, nhưng không vì vậy mà toàn bộ interaction semantics tự được triển khai. Cần kiểm tra login filter chain, SSO cookie, consent UI, account selection, session state và error callback.

### 8.2. Claims parameter và UserInfo mapper

**claims** request parameter có thể yêu cầu claim trong ID Token hoặc UserInfo, có thuộc tính **essential**, **value** và **values**. Đây là request có ảnh hưởng đến privacy và consent.

Một custom **userInfoMapper** có thể trả claim, nhưng chưa đủ để triển khai đầy đủ **claims** parameter:
- Parse JSON và kiểm cấu trúc.
- Kiểm client có quyền yêu cầu claim không.
- Kiểm essential claim có thể đáp ứng không.
- Áp consent/privacy.
- Trả error hoặc response theo OIDC semantics.
- Cập nhật metadata **claims_parameter_supported** đúng capability.

### 8.3. Pairwise subject

OIDC hỗ trợ public và pairwise subject identifiers. Pairwise subject có thể hạn chế các RP liên kết hoạt động của cùng một người dùng.

Để triển khai pairwise, OP cần mapping subject ổn định theo sector identifier/client grouping, xử lý sector identifier URI và quản lý lifecycle khi redirect/client grouping thay đổi. Không hash email mỗi lần phát ID Token vì email có thể đổi và hash không có secret có thể bị dò ngược.

Nếu SAS application dùng custom subject mapper, phải bảo đảm ID Token, UserInfo, authorization storage, logout session và các API profile dùng cùng subject mapping.

## 9. Các đặc tả riêng không nên mặc định là built-in

### 9.1. Session Management và Front/Back-Channel Logout

RP-Initiated Logout đã có endpoint trong SAS, nhưng Session Management, Front-Channel Logout và Back-Channel Logout là các specifications riêng.

| Cơ chế | Kênh | Trách nhiệm bổ sung |
|---|---|---|
| RP-Initiated Logout | RP → OP | OP kết thúc session tương ứng. |
| Session Management | Browser/iframe và OP | Session state/check session protocol. |
| Front-Channel Logout | OP → RP qua User Agent | RP xử lý logout request trong browser context. |
| Back-Channel Logout | OP → RP trực tiếp | RP xác minh Logout Token và kết thúc session server-side. |

Nếu cần logout tất cả RP, phải triển khai thông báo và correlation session theo các specification tương ứng. Đừng suy ra điều đó từ **OidcLogoutEndpointConfigurer**.

### 9.2. Federation

OIDC Federation định nghĩa trust chain, entity statement, metadata policy và trust anchor. Đây là một lớp trust federation khác với việc dùng một upstream OIDC provider để login.

Spring Security OAuth2 Client có thể tích hợp một upstream OP; điều đó không tự biến Authorization Server thành OIDC Federation entity. Nếu cần federation chuẩn, cần triển khai hoặc dùng federation component riêng và kiểm trust chain/policy.

### 9.3. CIBA, FAPI và các profile chuyên biệt

- **CIBA (Client Initiated Backchannel Authentication):** flow xác thực back-channel theo đặc tả riêng; không suy ra từ Device Authorization Grant.
- **FAPI:** các security profiles bổ sung yêu cầu về PAR/JAR, sender-constrained tokens, signing, encryption, request validation và security controls.
- **OpenID Connect Native SSO / các profile ngành:** có yêu cầu riêng về client, device và session.
- **Pairwise subject:** cần mapping/policy riêng như phần trước.

Một hệ thống hỗ trợ OAuth2 Device Authorization Grant hoặc PAR không tự động có CIBA hoặc FAPI conformance. Các profile này cần kiểm thử và đánh giá theo specification cụ thể.

## 10. Extension points của Spring Authorization Server

SAS thiết kế endpoint configurers theo các giai đoạn:
1. **Pre-processing:** AuthenticationConverter đọc HTTP request.
2. **Main processing:** AuthenticationProvider kiểm tra và thực hiện protocol.
3. **Post-processing:** success/error handler tạo response.
4. **Policy/customization:** validator, mapper, token customizer hoặc service ứng dụng.

| Endpoint / component | Extension point tiêu biểu | Dùng cho |
|---|---|---|
| Authorization Endpoint | authorizationRequestConverter, authenticationProviders, setAuthenticationValidator, consentPage, error handler | Request validation, interaction policy, consent. |
| Provider Configuration | providerConfigurationCustomizer | Discovery metadata. |
| UserInfo | userInfoMapper, provider, response/error handler | Claims động, scope/privacy filtering. |
| RP-Initiated Logout | Logout validator, provider, response/error handler | Redirect validation và session/logout policy. |
| Client Registration | Registration converter/provider/response handler | Registration policy và client metadata. |
| ID Token | OAuth2TokenCustomizer<JwtEncodingContext> | Claims được phép phát hành. |
| Session | SessionRegistry, session strategy | Theo dõi và kết thúc OP session. |

### 10.1. Không thay thế default validation một cách vô tình

SAS Authorization Code Request validator mặc định kiểm tra **redirect_uri** và **scope**. Nếu ứng dụng gọi **setAuthenticationValidator(...)**, hãy giữ các validator mặc định cần thiết hoặc kết hợp chúng với custom validator.

Ví dụ cấu trúc:

~~~java
Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> validator =
        customBusinessValidator
            .andThen(OAuth2AuthorizationCodeRequestAuthenticationValidator
                .DEFAULT_SCOPE_VALIDATOR);
~~~

Đoạn minh họa cho thấy cách kết hợp một custom validator với default scope validator. Thứ tự và các validator cần giữ phải dựa vào version/API thực tế. Không bỏ redirect URI validation, PKCE hoặc client validation để đơn giản hóa extension.

### 10.2. Custom provider cần delegate hoặc giữ behavior chuẩn

Khi thay provider mặc định, cần hiểu đầy đủ contract mà provider đang xử lý. Một provider custom không chỉ cần nhận request; nó còn phải giữ các kiểm tra:
- RegisteredClient và client authentication.
- Redirect URI, response type, scope và grant.
- Consent, authorization state và PKCE.
- Token generation, authorization persistence.
- Error mapping và protocol response.

Nếu chỉ cần thêm một policy, ưu tiên decorator/wrapper hoặc validator hook để giữ provider chuẩn, thay vì viết lại toàn bộ flow.

### 10.3. Tùy chỉnh không đồng nghĩa hỗ trợ mọi extension

Các extension point là công cụ để ứng dụng tự triển khai semantics. Chúng không tự cung cấp:
- Request Object JWT verification.
- Pairwise subject calculation.
- ACR/MFA assurance engine.
- Dynamic claim authorization.
- Front/Back-Channel Logout.
- Federation trust chain.
- Conformance certification.

Mỗi extension cần design, implementation, security review và tests riêng.

## 11. Xây dựng capability matrix cho deployment

Một capability matrix phải gắn với **artifact/version/configuration đang chạy**, không chỉ tài liệu kiến trúc.

Ví dụ:

| Capability | SAS 1.5.8 baseline | Deployment hiện tại | Evidence |
|---|---|---|---|
| OIDC Discovery | Built-in khi bật OIDC | Supported | Discovery response + issuer tests |
| Authorization Code + ID Token | Built-in | Supported | RP integration test |
| UserInfo | Built-in; cần JwtDecoder | Supported | Bearer + scope + sub test |
| RP-Initiated Logout | Built-in; dùng SessionRegistry | Supported with limitations | Browser session/logout test |
| Dynamic Client Registration | Có implementation, default disabled | Disabled | Configuration review |
| prompt=none | Cần kiểm behavior theo version/filter chain | Not yet verified | Browser E2E |
| max_age / auth_time | Cần custom policy/state | Custom implementation | Authentication timestamp test |
| ACR/MFA | Cần assurance policy | Not implemented | Step-up conformance test |
| Pairwise sub | Cần subject mapping | Not implemented | Multi-client subject tests |
| Claims request parameter | Cần kiểm support/extension | Not verified | Claim request tests |
| Front-Channel Logout | Đặc tả riêng | Not implemented | RP logout tests |
| Back-Channel Logout | Đặc tả riêng | Not implemented | Logout Token verification tests |
| OIDC Federation | Thành phần riêng | Not implemented | Trust-chain tests |

Trạng thái đề xuất:

- **SUPPORTED:** đã triển khai và có integration/conformance evidence.
- **CUSTOM_IMPLEMENTED:** ứng dụng tự mở rộng và có test.
- **DISABLED:** framework có nhưng endpoint/feature đang tắt.
- **NOT_SUPPORTED:** deployment không cung cấp feature.
- **NOT_VERIFIED:** chưa có evidence; không được công bố như supported.

Không dùng từ **OIDC-compliant** chỉ vì có một vài endpoint. Cần xác định profile, phiên bản specification, test suite và các optional features đã công bố.

## 12. Kiểm thử interoperability và conformance

### 12.1. Discovery tests

- [ ] Discovery URL truy cập qua public issuer.
- [ ] issuer khớp tuyệt đối với issuer trong ID Token.
- [ ] authorization_endpoint, token_endpoint, jwks_uri, userinfo_endpoint đúng.
- [ ] Metadata không quảng cáo endpoint đang disabled.
- [ ] Supported signing algorithms khớp với key/JWT encoder thực tế.
- [ ] claims_supported, subject_types_supported, grant_types_supported không phóng đại capability.
- [ ] Reverse proxy/ingress không làm sai scheme, host hoặc path.

### 12.2. ID Token tests

- [ ] openid scope được yêu cầu và xử lý đúng.
- [ ] ID Token signature verify bằng JWKS của issuer.
- [ ] iss, sub, aud, exp, iat đúng.
- [ ] nonce được kiểm khi request có nonce.
- [ ] auth_time có khi max_age được yêu cầu và phản ánh authentication thật.
- [ ] acr/amr chỉ phản ánh phương thức/assurance đã thực hiện.
- [ ] RP từ chối token sai issuer/audience/nonce/signature.
- [ ] Custom claims không vượt consent/privacy và không lộ dữ liệu nội bộ.

### 12.3. UserInfo tests

- [ ] Access token Bearer hợp lệ.
- [ ] Token hết hạn/revoke bị từ chối.
- [ ] Scope mapping đúng.
- [ ] sub luôn có và khớp ID Token.
- [ ] Optional claims bị omit khi không có hoặc không được phép.
- [ ] Custom mapper không bỏ qua authorization state.

### 12.4. Logout tests

- [ ] RP có thể gửi logout request tới OP.
- [ ] post_logout_redirect_uri được xác thực theo client registration.
- [ ] OP session thực sự bị kết thúc.
- [ ] SessionRegistry được cập nhật khi session destroy/timeout.
- [ ] Test nhiều tab, nhiều thiết bị, nhiều node.
- [ ] Nếu công bố front/back-channel logout, chạy test riêng cho từng protocol.
- [ ] Kiểm tra access/refresh token còn sống và revoke behavior riêng; logout session không tự chứng minh token đã bị revoke.

### 12.5. Dynamic Client Registration tests

Nếu bật DCR:

- [ ] Registrar có bearer token với scope client.create.
- [ ] Client Read cần scope client.read.
- [ ] Registration access token không được public hoặc chia sẻ không kiểm soát.
- [ ] Redirect URI, grant types, scopes và client auth method được policy kiểm tra.
- [ ] Registration metadata không tạo open redirect hoặc client impersonation.
- [ ] RegisteredClient persistence hoạt động sau restart/multi-instance.
- [ ] Có audit, quota, rate limit và disable/rotation workflow.
- [ ] Endpoint không cho phép registrar đọc hoặc sửa registration ngoài phạm vi quyền.

## 13. Bảo mật khi công bố OIDC capabilities

### 13.1. Metadata phải trung thực

Metadata sai gây lỗi tương tác và có thể mở rộng trust boundary. Ví dụ:
- Advertise claims_parameter_supported=true nhưng bỏ qua essential claims.
- Advertise end_session_endpoint nhưng endpoint logout không kết thúc session.
- Advertise signing algorithm mà key source không có.
- Advertise subject_types_supported là pairwise nhưng mọi client nhận cùng public subject.
- Bật Dynamic Client Registration nhưng không có registrar governance.

### 13.2. Không nhầm authentication với authorization

OIDC xác thực người dùng, OAuth2 cấp quyền truy cập resource. ID Token nói client đã xác thực ai; access token cho phép gọi API theo audience/scope/policy.

Không dùng ID Token để gọi API. Không dùng access token như bằng chứng đăng nhập thay ID Token. Không đưa scope vào ID Token rồi cho rằng Resource Server đã kiểm quyền.

### 13.3. Claims và privacy

- Chỉ phát claims cần thiết.
- Scope không phải giấy phép vô hạn để phát mọi PII.
- UserInfo response phải lọc theo scope, consent và policy.
- Không log raw ID Token, access token, authorization code, nonce hoặc request object chứa PII.
- sub phải ổn định và không được tái sử dụng cho người khác.
- Pairwise subject cần mapping riêng và không nên suy ra từ email.

### 13.4. Session và token lifecycle

- Logout OP session không tự revoke mọi access token.
- Revocation token không tự logout mọi RP session.
- Front/back-channel logout cần xác minh logout message/token và chống replay.
- Refresh token rotation, revocation và session invalidation cần có policy riêng.
- Nhiều Authorization Server instance cần shared session/authorization state và key configuration nhất quán.

## 14. Bài tập thực hành

**Bối cảnh:** **auth.example.com** dùng Spring Authorization Server 1.5.8 và muốn cung cấp OIDC cho **employee-portal**, **mobile-app**, **partner-console**.

### Yêu cầu

1. Bật OIDC và xác minh Provider Configuration endpoint.
2. Cấu hình issuer và JWK source; phát ID Token cho Authorization Code Flow.
3. Xác minh JwtDecoder bean cho UserInfo.
4. Chạy UserInfo với default mapper, sau đó thêm custom mapper cho profile động và scope filtering.
5. Cấu hình RP-Initiated Logout và SessionRegistry; xác định rõ logout session có/không revoke access token.
6. Để Dynamic Client Registration tắt ban đầu; nếu cần, bật endpoint và chỉ cấp client.create/client.read cho registrar service.
7. Viết capability matrix cho prompt, max_age, auth_time, acr_values, claims, request, pairwise sub.
8. Implement max_age và auth_time bằng trusted authentication timestamp.
9. Định nghĩa ACR/AMR policy cho MFA/step-up; không copy acr_values vào ID Token.
10. Nếu cần pairwise subject, thiết kế sector mapping và migration.
11. Nếu yêu cầu logout toàn hệ sinh thái, đánh giá Session Management, Front-Channel và Back-Channel Logout như các project riêng.
12. Chạy browser E2E và OIDC conformance tests, ghi rõ unsupported/disabled features.

**Tiêu chí hoàn thành:** tài liệu metadata khớp implementation; ID Token/UserInfo được RP xác minh; logout semantics được mô tả chính xác; DCR có registrar authorization; mọi optional extension được đánh dấu trạng thái và có evidence.

## 15. Checklist trước khi bàn giao

- [ ] Đã khóa phiên bản Spring Authorization Server/Spring Security dùng làm baseline.
- [ ] Phân biệt OAuth2 Authorization Server, OP, RP và Resource Server.
- [ ] OIDC được bật tường minh và endpoint Discovery kiểm thử.
- [ ] issuer ổn định và khớp metadata/ID Token.
- [ ] JWKSource và JwtDecoder được cấu hình đúng.
- [ ] ID Token claims/signature/nonce được kiểm tra theo OIDC Core.
- [ ] UserInfo yêu cầu Bearer access token và lọc claims theo scope.
- [ ] RP xác minh UserInfo sub khớp ID Token sub.
- [ ] RP-Initiated Logout được kiểm thử với SessionRegistry.
- [ ] Không tuyên bố front/back-channel logout hoặc session management nếu chưa triển khai.
- [ ] Dynamic Client Registration vẫn disabled nếu chưa có registrar governance.
- [ ] Nếu bật DCR, client.create/client.read được cấp theo least privilege.
- [ ] max_age/auth_time có nguồn authentication timestamp đáng tin.
- [ ] ACR/AMR phản ánh assurance/method thật.
- [ ] claims, Request Object, login_hint, prompt, acr_values được test theo version.
- [ ] Pairwise subject có mapping bền vững nếu metadata công bố hỗ trợ.
- [ ] Discovery metadata không quảng cáo feature chưa triển khai.
- [ ] Default validators/providers được giữ khi mở rộng.
- [ ] Có capability matrix với trạng thái và evidence.
- [ ] Có integration, browser E2E và conformance tests phù hợp.
- [ ] Không log token, nonce, code, PII hoặc request object nhạy cảm.
- [ ] Có owner và runbook cho key rotation, session logout, client registration và deprovisioning.

## Tổng kết

Spring Authorization Server 1.5.8 cung cấp nền tảng OIDC thực dụng: Provider Configuration, ID Token cho OIDC Authorization Code Flow, UserInfo và RP-Initiated Logout. Dynamic Client Registration cũng có implementation nhưng endpoint mặc định tắt, cần bearer token với scope client.create/client.read và phải được bảo vệ bằng registrar policy. UserInfo và Client Registration endpoint cần JwtDecoder; JWK Set endpoint cần JWKSource.

Các API customizer, mapper, provider, validator và session registry cho phép mở rộng framework, nhưng chúng không tự triển khai mọi semantics OIDC. max_age, auth_time, ACR/MFA, claims request, Request Object, pairwise subject, session management, front/back-channel logout và federation cần được đánh giá riêng. Một capability chỉ nên được công bố là supported khi metadata, runtime behavior và integration/conformance tests cùng chứng minh điều đó.

## Tài liệu tham khảo

1. [Spring Authorization Server 1.5.8 — Overview](https://docs.spring.io/spring-authorization-server/reference/overview.html): protocol endpoints và danh sách specification được triển khai.
2. [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): bật OIDC, Provider Configuration, Logout, UserInfo và endpoint Client Registration.
3. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): configurers, defaults, UserInfo, Logout và Dynamic Client Registration.
4. [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, Authorization, SessionRegistry và các components.
5. [Spring Authorization Server — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): default mapper và custom UserInfo claims.
6. [Spring Authorization Server — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): enable DCR, registrar client, initial access token và scopes.
7. [OpenID Connect Core 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-core-1_0.html): Authentication Request, ID Token, UserInfo, claims và protocol semantics.
8. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration metadata và capability advertisement.
9. [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): Client Registration và Client Read protocol.
10. [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): RP yêu cầu OP logout.
11. [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0-final.html): session state và RP/OP session management.
12. [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): logout notification qua User Agent.
13. [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html): logout notification trực tiếp từ OP tới RP.
14. [OpenID Connect Conformance Testing](https://openid.net/certification/): test profiles và conformance evidence cho OpenID implementations.

