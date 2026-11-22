# UserInfo Endpoint và yêu cầu access token hợp lệ

## 1. Bối cảnh và mục tiêu

Trong chương **OIDC UserInfo** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này giải thích cách một OIDC Client lấy thông tin người dùng từ **UserInfo Endpoint**, điều kiện của Access Token được chấp nhận và cách Spring Authorization Server xác thực request rồi trả về claims phù hợp.

Nội dung gắn với mục tiêu của module: **học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot**.

Hãy hình dung người dùng đăng nhập vào ứng dụng Portal bằng Authorization Code Flow. Portal nhận được ID Token và Access Token. ID Token cung cấp claims nhận diện người dùng cho client; Access Token cho phép Portal gọi UserInfo Endpoint để lấy thêm thông tin profile đã được cấp quyền, ví dụ tên hiển thị hoặc email đã xác minh.

Một số lỗi thường gặp:

- Gửi ID Token tới UserInfo Endpoint thay vì Access Token.
- Access Token còn hạn nhưng không có scope openid.
- Dùng token của tenant hoặc issuer khác.
- UserInfo trả sub khác sub trong ID Token nhưng client vẫn sử dụng dữ liệu.
- Mapper trả email, số điện thoại hoặc địa chỉ dù user chưa cấp quyền.
- Endpoint chỉ kiểm tra chữ ký mà bỏ qua trạng thái thu hồi của token.

Sau bài này, bạn có thể:

1. Mô tả vai trò của UserInfo Endpoint trong OIDC Authorization Code Flow.
2. Phân biệt ID Token, Access Token và UserInfo Response.
3. Xác định điều kiện để Access Token được chấp nhận tại UserInfo Endpoint.
4. Hiểu vai trò của scope openid, profile, email, address và phone.
5. Cấu hình UserInfo Endpoint trong Spring Authorization Server.
6. Viết userInfoMapper chỉ trả các claims được phép và giữ đúng sub.
7. Kiểm thử token hợp lệ, token sai scope, token hết hạn, token bị revoke và lỗi subject mismatch.

## 2. UserInfo Endpoint nằm ở đâu trong OIDC?

OpenID Connect xây dựng trên OAuth 2.0. Sau khi người dùng xác thực và cấp quyền, client có thể nhận:

- **ID Token:** JWT chứa claims về authentication event và subject, được phát hành cho OIDC Client.
- **Access Token:** credential để gọi protected resource được cấp quyền, trong bài này là UserInfo Endpoint.
- **UserInfo Response:** tập claims về End User được trả qua UserInfo Endpoint sau khi Access Token được xác minh.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End User
    participant C as OIDC Client
    participant AS as OpenID Provider / Authorization Server
    U->>C: Bắt đầu đăng nhập
    C->>AS: Authorization Request (scope=openid profile email)
    AS->>U: Authentication + Consent
    U-->>AS: Xác thực và chấp thuận
    AS-->>C: Authorization Code
    C->>AS: Token Request + code_verifier
    AS-->>C: ID Token + Access Token
    C->>C: Xác minh ID Token
    C->>AS: GET /userinfo + Access Token
    AS->>AS: Kiểm tra token, scope và authorization
    AS-->>C: UserInfo JSON có sub và claims được phép
    C->>C: So sánh UserInfo sub với ID Token sub
~~~

UserInfo Endpoint là một **OAuth 2.0 protected resource** do OpenID Provider cung cấp. Client trình Access Token để lấy claims của End User. Nó không phải endpoint đăng nhập, không phải Token Endpoint và cũng không phải nơi client gửi password.

### 2.1. Phân biệt ba loại dữ liệu

| Thành phần | Được phát hành ở đâu? | Mục đích | Ai sử dụng? |
| --- | --- | --- | --- |
| ID Token | Token Endpoint | Xác nhận authentication và subject cho OIDC Client | OIDC Client |
| Access Token | Token Endpoint | Cấp quyền truy cập protected resources | UserInfo Endpoint và API được token cho phép |
| UserInfo Response | UserInfo Endpoint | Trả claims về End User theo quyền được cấp | OIDC Client |

**Không dùng ID Token để gọi UserInfo Endpoint.** ID Token chứng minh kết quả xác thực với client; Access Token mới là credential truy cập UserInfo.

### 2.2. UserInfo không phải lúc nào cũng cần gọi

ID Token có thể đã chứa đủ claims mà ứng dụng cần. Client chỉ nên gọi UserInfo khi cần thêm claims hoặc cần lấy dữ liệu profile theo quyền đã cấp. Gọi UserInfo không tự làm authentication mạnh hơn và không thay thế việc xác minh chữ ký, issuer, audience, nonce và thời hạn của ID Token.

## 3. Điều kiện cơ bản của Access Token

OIDC Core yêu cầu client gọi UserInfo Endpoint bằng Access Token được phát hành trong quá trình OIDC. Access Token phải được trình theo cơ chế token presentation mà endpoint hỗ trợ và phải được server xác minh.

Với Bearer Access Token thông thường, điều kiện khái quát:

1. Token được phát hành bởi đúng OpenID Provider/Authorization Server.
2. Token có giá trị hợp lệ, chưa hết hạn và chưa bị thu hồi theo trạng thái mà endpoint kiểm tra được.
3. Token được phát hành trong ngữ cảnh OIDC, có scope openid.
4. Token thuộc đúng authorization/client và đáp ứng policy truy cập UserInfo.
5. Các scope/consent trong token cho phép trả về claims được yêu cầu.
6. Token được gửi qua HTTPS theo đúng header scheme.

### 3.1. Scope openid là điều kiện nhận diện OIDC request

Một authorization request OIDC phải có scope openid. Ví dụ:

~~~text
scope=openid profile email
~~~

openid cho biết client đang thực hiện OpenID Connect. Các scope khác biểu thị nhóm thông tin người dùng mà client muốn nhận:

- profile: nhóm claims profile cơ bản.
- email: email và trạng thái xác minh email.
- address: địa chỉ.
- phone: số điện thoại và trạng thái xác minh.

Nếu Access Token chỉ có orders.read mà không có openid, token đó có thể hợp lệ để gọi Orders API nhưng không phải token phù hợp cho UserInfo Endpoint.

### 3.2. Token còn hạn chưa đủ

Một Access Token có exp ở tương lai vẫn có thể bị từ chối nếu:

- Sai issuer.
- Chữ ký không hợp lệ.
- Token không active hoặc đã bị invalidated.
- Không có scope openid.
- Không thuộc client/authorization được phép.
- Sai audience hoặc resource policy nếu triển khai có kiểm tra audience cho UserInfo.
- Token type hoặc sender constraint không được trình đúng cách.

Do đó, không dùng câu “token còn hạn nên UserInfo phải trả 200” làm tiêu chí kiểm thử.

### 3.3. Không gửi Refresh Token hoặc Authorization Code

Refresh Token chỉ dùng để xin Access Token mới tại Token Endpoint. Authorization Code chỉ dùng để đổi token một lần theo flow tương ứng. Cả hai không phải credential để gọi UserInfo.

## 4. Cách gửi Access Token tới UserInfo Endpoint

OIDC Core quy định UserInfo Endpoint hỗ trợ HTTP GET và POST. Với Bearer token, client gửi Access Token trong HTTP Authorization header:

~~~http
GET /userinfo HTTP/1.1
Host: login.example.com
Authorization: Bearer <access-token>
Accept: application/json
~~~

Hoặc POST:

~~~http
POST /userinfo HTTP/1.1
Host: login.example.com
Authorization: Bearer <access-token>
Accept: application/json
Content-Length: 0
~~~

Endpoint công khai chính xác được công bố qua OpenID Provider Configuration, field userinfo_endpoint. Không hard-code path nếu issuer có custom path hoặc hệ thống đặt sau reverse proxy.

### 4.1. Không truyền Access Token trong query string

Không dùng:

~~~http
GET /userinfo?access_token=<access-token>
~~~

Token trong URL dễ xuất hiện ở access log, proxy log, browser history, analytics, monitoring và Referer. Hãy sử dụng Authorization header qua TLS. Cũng không đặt token trong URL của link hoặc redirect.

### 4.2. Sender-constrained Access Token

Nếu Access Token được ràng buộc với DPoP key, client phải dùng scheme và DPoP Proof theo RFC 9449 thay vì coi nó như Bearer token thông thường. Nếu token được ràng buộc với mTLS certificate theo RFC 8705, client phải trình đúng certificate trên TLS connection. Các cơ chế này bổ sung điều kiện possession; chúng không thay thế issuer, scope, trạng thái token và sub consistency.

## 5. UserInfo Response và claim sub

UserInfo Endpoint trả về JSON object chứa claims về End User. **Claim sub là bắt buộc** và phải là subject identifier của người dùng tương ứng với Access Token.

Ví dụ response:

~~~json
{
  "sub": "user-8f2a91",
  "name": "Nguyen An",
  "given_name": "An",
  "family_name": "Nguyen",
  "preferred_username": "an.nguyen",
  "email": "an@example.com",
  "email_verified": true,
  "locale": "vi-VN"
}
~~~

Các claims trong ví dụ chỉ được trả khi chúng đã được cấp quyền và được policy cho phép. Không phải mọi UserInfo Response đều cần có tất cả trường này.

### 5.1. Vì sao sub quan trọng?

sub là định danh duy nhất của End User trong phạm vi issuer theo quy tắc OIDC. Client dùng sub để liên kết UserInfo Response với người dùng trong ID Token đã nhận.

OIDC Core quy định giá trị sub trong UserInfo Response **phải giống chính xác** giá trị sub trong ID Token. Nếu khác, client phải không sử dụng UserInfo Response.

Ví dụ:

~~~text
ID Token:
    iss = https://login.example.com
    sub = user-8f2a91

UserInfo:
    sub = user-8f2a91       -> hợp lệ về subject binding

UserInfo khác:
    sub = user-44b021       -> client phải loại bỏ response
~~~

Không so sánh bằng email, username hoặc display name. Những thuộc tính này có thể đổi hoặc trùng nhau.

### 5.2. Pairwise subject identifier

OIDC Provider có thể dùng pairwise subject identifier để hạn chế khả năng các client khác nhau liên kết cùng một người dùng. Khi dùng pairwise subject:

- Subject được tính theo sector/client policy.
- Cùng người dùng ở hai client khác nhau có thể có hai sub khác nhau.
- ID Token và UserInfo cho cùng một client/sector vẫn phải có sub giống nhau.
- Không tự tính lại sub ở mapper theo mỗi request hoặc theo email hiện tại.

Subject mapping phải ổn định, có versioning và được dùng nhất quán ở nơi phát hành ID Token lẫn UserInfo.

## 6. Scope và nhóm claims chuẩn

OIDC Core định nghĩa quan hệ giữa scope và các nhóm claims UserInfo:

| Scope | Claims tiêu biểu |
| --- | --- |
| profile | name, family_name, given_name, middle_name, nickname, preferred_username, profile, picture, website, gender, birthdate, zoneinfo, locale, updated_at |
| email | email, email_verified |
| address | address (object gồm formatted, street_address, locality, region, postal_code, country) |
| phone | phone_number, phone_number_verified |

openid là scope bắt buộc để thực hiện OIDC; nó không có nghĩa server được tự động trả mọi thông tin profile. Các scope profile/email/address/phone phải được yêu cầu và chấp thuận theo policy.

### 6.1. Requested scope khác authorized scope

| Tập scope | Ý nghĩa |
| --- | --- |
| Requested scopes | Client mong muốn được cấp |
| Registered client scopes | Giới hạn scope client được phép yêu cầu |
| Consented/authorized scopes | Scope được Authorization Server chấp thuận sau policy/consent |
| Access Token scopes | Quyền thực tế gắn với token |
| Claims trong UserInfo | Dữ liệu được trả theo authorized scopes và policy dữ liệu |

UserInfo mapper nên dựa trên **authorized scopes của authorization/token**, không lấy scope thô từ query hoặc header do client gửi. Việc một client yêu cầu email không có nghĩa user đã đồng ý hoặc email được phép tiết lộ.

### 6.2. Scope không phải field trong UserInfo Response

Scope thường không được lặp lại như một claim tên scope trong UserInfo Response. Nó là quyền gắn với Access Token. Client biết scope được cấp qua token response hoặc authorization state; server dùng scope để quyết định claims được trả.

### 6.3. Claims theo yêu cầu cụ thể

OIDC Core còn có cơ chế claims parameter trong Authorization Request để yêu cầu claims cụ thể. Nếu triển khai hỗ trợ, server phải xử lý theo chuẩn và consent/policy. Không nên tự tạo query parameter email=true hoặc includeSensitive=true ở UserInfo Endpoint rồi bỏ qua scope.

## 7. Luồng xác minh Access Token tại UserInfo Endpoint

Ở mức logic, UserInfo Endpoint cần:

1. Nhận Access Token theo scheme được hỗ trợ.
2. Xác minh token signature/issuer/time nếu là JWT, hoặc lookup trạng thái nếu opaque.
3. Tìm authorization/token tương ứng.
4. Kiểm tra token active và không bị invalidated.
5. Xác nhận scope openid và các quyền liên quan.
6. Xác định principal/subject đã được xác thực khi cấp authorization.
7. Tạo claims UserInfo theo authorized scopes, consent và data policy.
8. Bắt buộc đưa sub đúng subject của authorization.
9. Trả response theo định dạng đã cấu hình.

~~~mermaid
flowchart TD
    A["GET/POST UserInfo + Access Token"] --> B{"Authorization header hợp lệ?"}
    B -->|Không| X["401 invalid_token"]
    B -->|Có| C["Verify token / lookup authorization"]
    C --> D{"Token active, issuer/time hợp lệ?"}
    D -->|Không| X
    D -->|Có| E{"Scope openid được cấp?"}
    E -->|Không| Y["Từ chối theo OIDC/provider policy"]
    E -->|Có| F["Resolve principal + authorized scopes"]
    F --> G["Áp dụng consent và claim release policy"]
    G --> H["Tạo UserInfo, luôn có sub"]
    H --> I["Trả JSON response"]
~~~

Không lấy subject từ request parameter. Subject phải xuất phát từ authorization đã xác thực. Nếu mapper không tìm thấy user profile hoặc account đã bị xóa/khóa, cần policy rõ ràng: trả claims tối thiểu, từ chối token, hoặc xử lý theo trạng thái account; không thay subject bằng giá trị client gửi.

## 8. Cấu hình UserInfo Endpoint trong Spring Authorization Server

UserInfo Endpoint là tính năng OIDC. Trong Spring Authorization Server, cần bật OIDC trên OAuth2AuthorizationServerConfigurer.

Ví dụ cấu hình filter chain theo API Spring Authorization Server 1.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Đây là phần filter chain minh họa; ứng dụng hoàn chỉnh còn cần RegisteredClientRepository, OAuth2AuthorizationService, JWKSource, user authentication chain và các security rules khác. Nếu không bật OIDC, UserInfo Endpoint không được cấu hình như một OAuth endpoint thông thường.

### 8.1. Endpoint URL

UserInfo Endpoint mặc định thường là:

~~~text
GET /userinfo
POST /userinfo
~~~

Public URL thực tế cần được công bố trong OpenID Provider Configuration qua field userinfo_endpoint. Khi đặt sau reverse proxy, metadata phải dùng public scheme/host/path, ví dụ:

~~~json
{
  "issuer": "https://login.example.com",
  "userinfo_endpoint": "https://login.example.com/userinfo"
}
~~~

Nếu có context path hoặc proxy prefix, cần kiểm tra URL công bố và route thực tế nhất quán. Không chỉ kiểm tra /userinfo nội bộ bằng MockMvc rồi kết luận public endpoint hoạt động.

## 9. Tùy chỉnh claims bằng userInfoMapper

Trong Spring Authorization Server, OidcUserInfoEndpointConfigurer cung cấp điểm mở rộng userInfoMapper. Mapper nhận OidcUserInfoAuthenticationContext và trả về OidcUserInfo.

Mapper nên:

- Lấy authorization đã xác thực từ context.
- Lấy principal name/subject từ authorization.
- Lấy authorized scopes từ authorization.
- Truy xuất user profile từ service nội bộ.
- Chỉ trả claims được scope/consent/policy cho phép.
- Luôn trả sub đúng với ID Token đã phát hành cho client.

### 9.1. Ví dụ mapper có kiểm soát scope

Ví dụ sau dùng UserProfileService do ứng dụng định nghĩa:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;

@Configuration(proxyBeanMethods = false)
class UserInfoConfiguration {

    @Bean
    Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper(
            UserProfileService userProfileService) {

        return context -> {
            OAuth2Authorization authorization = context.getAuthorization();
            String subject = authorization.getPrincipalName();
            Set<String> scopes = authorization.getAuthorizedScopes();

            UserProfile profile = userProfileService.findBySubject(subject);
            Map<String, Object> claims = new HashMap<>();

            // OIDC Core yêu cầu sub trong UserInfo Response.
            claims.put("sub", subject);

            if (scopes.contains(OidcScopes.PROFILE)) {
                putIfPresent(claims, "name", profile.name());
                putIfPresent(claims, "given_name", profile.givenName());
                putIfPresent(claims, "family_name", profile.familyName());
                putIfPresent(claims, "preferred_username",
                        profile.preferredUsername());
                putIfPresent(claims, "locale", profile.locale());
            }

            if (scopes.contains(OidcScopes.EMAIL)
                    && profile.emailMayBeReleased()) {
                putIfPresent(claims, "email", profile.email());
                claims.put("email_verified", profile.emailVerified());
            }

            if (scopes.contains(OidcScopes.PHONE)
                    && profile.phoneMayBeReleased()) {
                putIfPresent(claims, "phone_number", profile.phoneNumber());
                claims.put("phone_number_verified",
                        profile.phoneNumberVerified());
            }

            if (scopes.contains(OidcScopes.ADDRESS)
                    && profile.addressMayBeReleased()
                    && profile.address() != null) {
                claims.put("address", profile.address());
            }

            return new OidcUserInfo(claims);
        };
    }

    private static void putIfPresent(
            Map<String, Object> claims, String name, String value) {
        if (value != null && !value.isBlank()) {
            claims.put(name, value);
        }
    }
}
~~~

UserProfileService, UserProfile và các phương thức emailMayBeReleased()/addressMayBeReleased() là **API nghiệp vụ minh họa do ứng dụng tự định nghĩa**, không phải class có sẵn của Spring. Đoạn mapper cần được tích hợp vào cấu hình OIDC:

~~~java
authorizationServerConfigurer.oidc(oidc ->
    oidc.userInfoEndpoint(userInfo ->
        userInfo.userInfoMapper(userInfoMapper)
    )
);
~~~

Các import package/API có thể thay đổi giữa các phiên bản Spring Authorization Server. Hãy kiểm tra Javadoc của dependency đang dùng; không copy một đoạn cấu hình phiên bản khác rồi giả định compile thành công.

### 9.2. Đăng ký mapper vào filter chain

Ví dụ cách ghép vào SecurityFilterChain:

~~~java
http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .with(authorizationServerConfigurer, authorizationServer ->
        authorizationServer.oidc(oidc ->
            oidc.userInfoEndpoint(userInfo ->
                userInfo.userInfoMapper(userInfoMapper)
            )
        )
    );
~~~

userInfoMapper ở đây là bean Function<OidcUserInfoAuthenticationContext, OidcUserInfo> được inject vào cấu hình. Chỉ đăng ký một mapper có chủ đích; nếu có nhiều customization, hợp nhất logic để tránh bean cấu hình ghi đè không rõ ràng.

### 9.3. Không trả tất cả profile claims chỉ vì đã đăng nhập

Một user đã authenticated không đồng nghĩa mọi dữ liệu của user được chia sẻ với client. Mapper phải xét authorized scopes, consent, tenant, data classification, account state và policy dữ liệu. Đặc biệt email, phone, address và birthdate có thể là dữ liệu cá nhân nhạy cảm.

## 10. Subject consistency giữa ID Token và UserInfo

Đây là điều kiện OIDC quan trọng nhất ở tầng client.

Giả sử ID Token được tạo với:

~~~json
{
  "iss": "https://login.example.com",
  "aud": "portal-client",
  "sub": "user-8f2a91"
}
~~~

UserInfo phải trả:

~~~json
{
  "sub": "user-8f2a91",
  "name": "Nguyen An"
}
~~~

Nếu mapper dùng email để tìm profile rồi tạo một sub khác, client phải loại bỏ response. Không ghép UserInfo vào account chỉ vì email trùng.

### 10.1. Subject mapping cần dùng chung

Trong hệ thống có pairwise subject:

1. Xác định sector identifier hoặc client policy khi phát hành ID Token.
2. Tạo sub ổn định theo user và sector.
3. Lưu hoặc tính lại cùng một mapping khi UserInfo được gọi.
4. Không thay đổi sub khi email/username đổi.
5. Khi client đổi sector identifier, phải có migration policy vì subject có thể thay đổi.

### 10.2. Principal name không luôn tự động là OIDC sub đúng

Ví dụ mapper dùng authorization.getPrincipalName() chỉ đúng khi ứng dụng đã thiết kế principal name làm subject identifier của ID Token. Nếu ID Token customizer tạo pairwise hoặc opaque subject khác, mapper phải dùng cùng subject mapping service thay vì trả principal name thô.

Nên có một component duy nhất như SubjectIdentifierService để tạo subject theo issuer/client/sector. Cả ID Token generator và UserInfo mapper cùng gọi component đó. Không sao chép thuật toán subject ở hai nơi.

## 11. Kiểm tra scope, consent và claims release

Một authorization request có thể yêu cầu:

~~~text
scope=openid profile email
~~~

Người dùng có thể chỉ chấp thuận:

~~~text
openid profile
~~~

Khi đó UserInfo chỉ được trả các claims theo openid profile và policy dữ liệu. Không được trả email chỉ vì client đã yêu cầu nó ban đầu.

### 11.1. Ma trận scope → claim

| Scope đã được cấp | Có thể trả | Không được suy diễn |
| --- | --- | --- |
| openid | sub | Không mặc nhiên trả toàn bộ profile |
| profile | Claims profile được policy cho phép | Không tự động trả email/phone/address nếu không có scope tương ứng |
| email | email, email_verified nếu có dữ liệu và được phép | Không khẳng định email_verified=true nếu chưa xác minh |
| phone | phone_number, phone_number_verified nếu có | Không tự xác nhận số điện thoại |
| address | address object theo dữ liệu được phép | Không trả địa chỉ nội bộ hoặc địa chỉ không còn hiệu lực |

### 11.2. Consent có thể thay đổi

Nếu user thu hồi consent sau khi Access Token đã được phát hành, hệ thống cần quyết định:

- Token cũ có bị revoke không?
- UserInfo mapper có đọc consent hiện tại ở mỗi request không?
- Claims có bị giảm ngay khi consent bị thu hồi không?
- Resource Server có nhận trạng thái thu hồi hay tiếp tục chấp nhận JWT offline?

Không giả định việc xóa consent tự động làm mọi Access Token hiện tại mất hiệu lực. Cần kết hợp revocation policy, authorization state và claim release policy.

### 11.3. Data minimization

Chỉ trả những claims client thực sự cần. Không trả password, credential, internal user ID không cần thiết, security answer, dữ liệu thanh toán, quyền quản trị nội bộ hoặc thuộc tính phục vụ phân tích rủi ro nếu không có cơ sở rõ ràng.

## 12. Access Token hợp lệ với JWT và opaque token

### 12.1. JWT Access Token

Nếu Access Token là JWT, các kiểm tra thông thường gồm:

- Chữ ký hợp lệ theo key đáng tin.
- iss đúng issuer.
- exp/nbf hợp lệ.
- Token type và profile phù hợp.
- Scope openid được cấp.
- Authorization/token state còn active theo policy của Authorization Server.

Không chỉ decode payload rồi tin claims. Decode không xác minh chữ ký. JWT cũng không tự cho biết record trong authorization store đã bị invalidated nếu endpoint không kiểm tra trạng thái đó.

### 12.2. Opaque Access Token

Opaque token không chứa claims để client đọc. UserInfo Endpoint lookup token trong authorization store hoặc cơ chế xác minh nội bộ. Server xác định authorization, principal, scopes và trạng thái token từ nguồn tin cậy.

| Đặc điểm | JWT | Opaque |
| --- | --- | --- |
| Token payload | Có thể decode nhưng cần verify signature | Không tự giải mã được |
| Lookup authorization | Có thể cần store để kiểm tra state | Thường lookup store/introspection |
| Revocation | Offline verifier có thể không thấy revoke | Có thể phản ánh qua store/active state |
| UserInfo claims | Lấy từ authorization và profile service | Lấy từ authorization và profile service |

UserInfo Endpoint không cần client decode Access Token. Client chỉ trình token; OpenID Provider chịu trách nhiệm xác minh token và xác định claims được trả.

### 12.3. Revocation và thời điểm kiểm tra

Nếu Access Token bị thu hồi, UserInfo Endpoint nên từ chối khi authorization store/validation layer biết token không còn active. Nhưng các API khác xác minh JWT offline có thể vẫn chấp nhận token tới exp. Cần hiểu rõ mỗi Resource Server có enforcement strategy riêng.

## 13. Lỗi UserInfo Endpoint và phản hồi HTTP

Các lỗi phổ biến:

| Tình huống | Phản hồi thường gặp | Ý nghĩa |
| --- | --- | --- |
| Thiếu Access Token | 401 Unauthorized | Không có credential |
| Token sai, hết hạn hoặc bị revoke | 401 Unauthorized, invalid_token | Token không hợp lệ |
| Token thiếu scope/permission cần thiết | 403 Forbidden hoặc lỗi scope theo policy | Token không đủ quyền |
| Token có sai scheme cho sender-constrained flow | Từ chối xác thực | Client trình token sai cách |
| UserInfo mapper gặp lỗi nội bộ | 5xx theo error handling | Server không xử lý được request |

Với Bearer token, response lỗi xác thực có thể dùng WWW-Authenticate: Bearer theo RFC 6750. Không trả stack trace, SQL error hoặc thông tin user nhạy cảm ra client.

### 13.1. Không biến UserInfo thành user lookup API công khai

Không cho phép gọi:

~~~http
GET /userinfo?userId=another-user
~~~

UserInfo trả dữ liệu của subject gắn với Access Token. Không lấy subject từ path, query, body hoặc custom header do client kiểm soát. Nếu một ứng dụng cần tìm user khác, đó là API nghiệp vụ riêng với authorization policy riêng, không phải UserInfo.

### 13.2. Client phải xử lý sub mismatch

Nếu UserInfo Response không có sub hoặc sub khác ID Token, client phải loại bỏ response. Không fallback sang email, username hoặc claim name. Đây là biện pháp ngăn việc gắn profile của một người dùng khác vào phiên đăng nhập hiện tại.

## 14. Bảo mật và quyền riêng tư

### 14.1. HTTPS là bắt buộc

UserInfo chứa claims người dùng, có thể gồm email, địa chỉ và số điện thoại. Endpoint phải được truy cập qua TLS. Không cho phép token đi qua HTTP cleartext hoặc redirect không an toàn.

### 14.2. Token và claims không được ghi log thô

Không log:

- Authorization header hoặc Access Token.
- Toàn bộ UserInfo Response.
- Email/phone/address nếu không có mục đích và quyền truy cập rõ.
- Client secret hoặc credential liên quan.

Log an toàn nên ghi correlation ID, client ID, issuer, endpoint, kết quả validation, scope category và error code; hạn chế ghi subject hoặc dùng pseudonymous identifier theo chính sách.

### 14.3. CORS và browser clients

Nếu SPA gọi UserInfo trực tiếp từ browser, cần cấu hình CORS cho origin cụ thể và method/header cần thiết. Không mở wildcard origin cùng credential hoặc bật CORS rộng cho mọi Authorization Server endpoint. CORS không phải cơ chế xác thực; Access Token vẫn phải được kiểm tra ở server.

### 14.4. Cache và response headers

UserInfo Response có dữ liệu cá nhân. Cấu hình cache policy phù hợp, thường tránh shared cache hoặc cache response theo một người dùng rồi trả cho người khác. Xem xét Cache-Control: no-store hoặc policy hạn chế tương đương cho dữ liệu nhạy cảm, và bảo đảm CDN/reverse proxy không cache nhầm.

### 14.5. Tenant isolation

Trong multi-tenant OIDC Provider:

- Subject được giải quyết trong tenant/issuer của Access Token.
- User profile lookup phải tenant-aware.
- Access Token Acme không được lấy profile Zen.
- Scope/consent của một tenant không được áp dụng cho tenant khác.
- sub phải nhất quán theo issuer và client/sector.

Không dùng email toàn cục làm khóa lookup duy nhất giữa tenants nếu email có thể trùng hoặc cùng người dùng có profile khác nhau theo tenant.

## 15. Kiểm thử UserInfo Endpoint

Kiểm thử cần đi qua Token Endpoint thật trong test fixture để có Access Token hợp lệ, sau đó gọi UserInfo Endpoint bằng token đó. Không chỉ mock mapper và assert nó trả Map.

### 15.1. Test response cho token có openid profile

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UserInfoEndpointIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsSubjectAndAuthorizedProfileClaims() throws Exception {
        String accessToken = obtainAccessToken("openid", "profile");

        mvc.perform(get("/userinfo")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sub").value("user-8f2a91"))
            .andExpect(jsonPath("$.name").value("Nguyen An"));
    }

    private String obtainAccessToken(String... scopes) {
        // Test fixture thực hiện Authorization Code + PKCE,
        // user login/consent và đổi code tại Token Endpoint.
        throw new UnsupportedOperationException("Provide the project's test flow");
    }
}
~~~

obtainAccessToken() là placeholder cho fixture của dự án, không phải implementation hoàn chỉnh. Test thực cần tạo RegisteredClient, user, consent, authorization service và signing key. Không hard-code Access Token production vào test.

### 15.2. Test email chỉ xuất hiện khi được cấp scope

~~~java
@Test
void doesNotReturnEmailWhenEmailScopeWasNotAuthorized() throws Exception {
    String accessToken = obtainAccessToken("openid", "profile");

    mvc.perform(get("/userinfo")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.sub").value("user-8f2a91"))
        .andExpect(jsonPath("$.email").doesNotExist());
}
~~~

Đây là method bổ sung vào test class ở trên. Fixture phải bảo đảm email không được authorized; chỉ kiểm tra scope trong request mà không kiểm tra consent/authorized scopes là chưa đủ.

### 15.3. Test token không hợp lệ

Các trường hợp tối thiểu:

- Không có Authorization header.
- Token sai chữ ký.
- Token hết hạn.
- Token bị invalidated/revoked.
- Token không có openid.
- Token thuộc issuer khác.
- Token được trình bằng sai scheme.
- DPoP-bound token không có proof hoặc proof sai key/ath.
- mTLS-bound token được trình qua certificate khác.

Kỳ vọng: endpoint từ chối, không trả UserInfo claims.

### 15.4. Test subject mismatch

Tạo fixture cố ý để ID Token có sub=user-A, còn UserInfo mapper trả sub=user-B. Client integration test phải loại bỏ response và không gắn claims của user-B vào session user-A.

Đây là kiểm thử phía **OIDC Client**, vì server không thể đảm bảo client sẽ thực hiện so sánh subject nếu client code bỏ qua quy tắc OIDC Core.

## 16. Ma trận kiểm thử đầy đủ

| # | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Access Token có openid và profile, token active | HTTP 200; có sub và claims profile được phép |
| 2 | Access Token chỉ có orders.read | UserInfo từ chối theo OIDC scope policy |
| 3 | Access Token không có openid | Không coi token là OIDC UserInfo credential |
| 4 | Không gửi token | 401 |
| 5 | Token sai chữ ký | 401 invalid_token |
| 6 | Token hết hạn | 401 invalid_token |
| 7 | Token bị revoke/invalidated và endpoint nhìn thấy trạng thái | 401 invalid_token |
| 8 | Token có email scope nhưng consent/policy không cho release | Không trả email |
| 9 | Token không có email scope | Không trả email/email_verified |
| 10 | Token có phone scope nhưng profile chưa xác minh số | Không khẳng định phone_number_verified=true |
| 11 | UserInfo không có sub | Response không đạt OIDC contract; test thất bại |
| 12 | UserInfo sub khác ID Token sub | OIDC Client loại bỏ response |
| 13 | Access Token thuộc issuer Acme gọi UserInfo Zen | Từ chối |
| 14 | Access Token tenant Acme lookup profile Zen | Không được xảy ra |
| 15 | Token trình bằng query parameter | Không hỗ trợ cách truyền token không an toàn |
| 16 | DPoP-bound token với proof hợp lệ | Chấp nhận theo DPoP policy |
| 17 | DPoP-bound token với proof sai key hoặc ath | Từ chối |
| 18 | mTLS-bound token với certificate sai | Từ chối |
| 19 | User profile service lỗi | Lỗi được xử lý an toàn, không trả stack trace |
| 20 | Metadata công bố sai userinfo_endpoint | Public integration test thất bại |
| 21 | UserInfo response bị cache giữa hai người dùng | Không xảy ra cross-user cache leak |
| 22 | CORS request từ origin không được phép | Browser không được phép đọc response |

### 16.1. Test contract giữa ID Token và UserInfo

Một test OIDC end-to-end nên:

1. Hoàn tất Authorization Code + PKCE.
2. Xác minh chữ ký ID Token, iss, aud, exp, iat, nonce theo flow.
3. Lưu sub từ ID Token.
4. Gọi UserInfo bằng Access Token.
5. Xác minh HTTP response và sub.
6. Assert userinfo.sub bằng chính xác id_token.sub.
7. Assert chỉ các claims đã được cấp và cho phép xuất hiện.

### 16.2. Test qua reverse proxy

Ngoài MockMvc, cần kiểm thử public URL từ bên ngoài ingress:

- userinfo_endpoint trong OIDC metadata truy cập được.
- HTTPS/SNI/TLS certificate đúng.
- Proxy không làm mất Authorization header.
- Proxy không log token.
- Path prefix được rewrite đúng.
- CORS và cache headers phù hợp.

## 17. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| /userinfo trả 404 | OIDC chưa bật hoặc route/path sai | Kiểm tra oidc(...), metadata và reverse proxy |
| 401 dù token chưa hết hạn | Sai chữ ký/issuer, token revoked, token lookup lỗi hoặc sai scheme | Kiểm tra authorization state và Authorization header |
| 403 hoặc scope error | Thiếu openid hoặc policy yêu cầu scope khác | Kiểm tra authorized scopes và consent |
| UserInfo chỉ trả sub | Mapper mặc định hoặc profile claims chưa được cấu hình | Cấu hình userInfoMapper theo policy |
| Email không xuất hiện | Thiếu email scope, consent hoặc profile data | Kiểm tra từng lớp; không tự bật trả email |
| UserInfo sub khác ID Token | Subject mapping không nhất quán | Dùng chung subject identifier service |
| UserInfo trả dữ liệu user khác | Mapper lookup theo request/email sai hoặc tenant context mất | Lookup theo subject đã xác thực và tenant-aware |
| Token Acme gọi được UserInfo Zen | Issuer/authorization isolation thiếu | Kiểm tra tenant routing, issuer và token lookup |
| Resource Server API từ chối nhưng UserInfo chấp nhận | Hai nơi có validation/revocation policy khác nhau | Đồng bộ trust, audience và token state strategy |
| Token trong query bị log | Client gửi sai cách | Chỉ dùng Authorization header qua HTTPS |
| UserInfo bị cache nhầm | CDN/shared cache cấu hình sai | Tắt shared cache hoặc cache theo identity an toàn |
| MockMvc pass nhưng public URL lỗi | Ingress TLS, forwarded headers hoặc prefix sai | Chạy end-to-end qua proxy |

## 18. Checklist triển khai production

1. **OIDC enabled:** UserInfo Endpoint chỉ được cấu hình khi OIDC support đã bật.
2. **Discovery:** userinfo_endpoint công bố đúng public HTTPS URL.
3. **Access Token:** client gửi Access Token, không gửi ID Token, Refresh Token hoặc Authorization Code.
4. **Scope:** token có openid; claims khác chỉ trả theo authorized scopes.
5. **Validation:** kiểm tra chữ ký/issuer/time/token state theo profile và policy.
6. **Subject:** sub luôn có và khớp chính xác với ID Token.
7. **Mapper:** lookup profile bằng subject đã xác thực; không lấy user ID từ request.
8. **Consent:** không suy ra consent từ requested scopes.
9. **Privacy:** chỉ trả claims tối thiểu; không log token hoặc UserInfo thô.
10. **Transport:** HTTPS; sender-constrained token dùng đúng DPoP/mTLS proof.
11. **Tenant:** issuer, principal, profile lookup và authorization đều tenant-aware.
12. **Caching:** không shared-cache response người dùng sai cách; headers được kiểm tra.
13. **Errors:** 401/403 phù hợp, không lộ thông tin nội bộ.
14. **Testing:** kiểm tra token sai scope, expired, revoked, subject mismatch và tenant mismatch.
15. **Operations:** monitor latency/error rates, profile lookup failures và bất thường truy cập claims.

## 19. Bài tập và câu hỏi tự đánh giá

**Bài tập A — Phân biệt token.** Một client nhận ID Token và Access Token. Hãy giải thích token nào dùng để xác minh đăng nhập, token nào dùng để gọi UserInfo và vì sao.

**Bài tập B — Scope.** Client yêu cầu openid profile email, nhưng user chỉ chấp thuận openid profile. Thiết kế response UserInfo phù hợp và giải thích vì sao email không được trả.

**Bài tập C — Subject mismatch.** ID Token có sub=user-A, UserInfo có sub=user-B. Client phải làm gì? Vì sao email trùng không thể thay thế kiểm tra sub?

**Bài tập D — Spring mapper.** Viết userInfoMapper chỉ trả name khi scope profile đã được cấp và email khi scope email đã được cấp. Thêm kiểm tra sub luôn có.

**Bài tập E — Revocation.** Access Token JWT bị đánh dấu invalidated trong Authorization Server nhưng Resource Server chỉ verify offline. Phân tích vì sao UserInfo có thể từ chối token trong khi API khác vẫn chấp nhận cho tới exp.

**Bài tập F — Multi tenant.** Cùng một email tồn tại ở tenant Acme và Zen. Thiết kế subject/profile lookup để Access Token Acme không thể lấy dữ liệu Zen.

**Bài tập G — End-to-end test.** Mô tả test Authorization Code + PKCE, lấy Access Token, gọi UserInfo và assert userinfo.sub == id_token.sub.

**Câu hỏi ôn tập:**

1. UserInfo Endpoint là protected resource hay Token Endpoint?
2. Vì sao phải dùng Access Token thay vì ID Token?
3. Scope openid có ý nghĩa gì?
4. Những scope nào tương ứng với profile, email, address và phone claims?
5. Claim nào bắt buộc trong UserInfo Response?
6. OIDC Client phải xử lý thế nào khi UserInfo sub khác ID Token sub?
7. Vì sao requested scopes không đủ để quyết định claims được trả?
8. userInfoMapper trong Spring Authorization Server có trách nhiệm gì?
9. Vì sao mapper không nên lookup user theo query parameter?
10. JWT còn hạn có chắc chắn active không?
11. DPoP/mTLS-bound Access Token cần được trình như thế nào?
12. Vì sao UserInfo Response không nên được shared-cache?
13. Xóa consent có tự động revoke Access Token đang hoạt động không?
14. Những test nào chứng minh UserInfo không lộ dữ liệu chéo tenant?

## 20. Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Section 5.3, UserInfo Endpoint](https://openid.net/specs/openid-connect-core-1_0.html#UserInfo)
- [OpenID Connect Core 1.0 — Section 5.3.2, UserInfo Response](https://openid.net/specs/openid-connect-core-1_0.html#UserInfoResponse)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)

**Ghi nhớ:** UserInfo Endpoint trả claims của End User dựa trên **Access Token hợp lệ**. Với OIDC, token phải gắn với authorization có scope openid; các claims khác chỉ được trả theo authorized scopes, consent và policy. sub luôn bắt buộc và phải khớp chính xác với sub trong ID Token. Spring Authorization Server cho phép tùy chỉnh bằng userInfoMapper, nhưng mapper phải lấy subject từ authorization đã xác thực, giới hạn claims và giữ cách ly issuer/tenant. Client cần loại bỏ UserInfo Response nếu subject không khớp.
