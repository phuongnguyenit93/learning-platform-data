# Đăng ký ứng dụng native với redirect URI và PKCE phù hợp

> **Chương: Tích hợp ứng dụng.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Bài tập trung vào đăng ký mobile/desktop native app như public client, chọn redirect URI phù hợp với nền tảng và bắt buộc Authorization Code Flow kết hợp PKCE.

## 1. Native app là public client

Native app là ứng dụng được cài trên thiết bị người dùng, ví dụ Android, iOS, macOS, Windows, Linux hoặc ứng dụng hybrid được đóng gói như app. Ứng dụng có thể gọi trực tiếp Authorization Server và Resource Server, nhưng mọi bí mật được đóng gói trong binary đều có thể bị trích xuất.

Vì vậy, native app thông thường là **public OAuth client**:

- Có `client_id` để Authorization Server nhận diện registration.
- Không có `client_secret` đáng tin cậy. Secret nhúng trong APK, IPA, desktop executable hoặc cấu hình client có thể bị người dùng/attacker lấy ra.
- Dùng Authorization Code Grant kết hợp Proof Key for Code Exchange (PKCE).
- Mở trang đăng nhập bằng external user-agent, thường là browser hệ thống hoặc browser tab bảo mật.
- Nhận authorization response qua redirect URI đã đăng ký.
- Lưu token theo cơ chế bảo mật của hệ điều hành.

`client_id` nhận diện ứng dụng, nhưng không chứng minh binary đang gọi request là bản chính thức. PKCE bảo vệ authorization code khỏi bị ứng dụng khác chặn và đổi token; nó không biến public client thành confidential client.

### 1.1. Các thành phần trong một lần đăng nhập

| Thành phần | Vai trò |
|---|---|
| Native app | Public OAuth2/OIDC client trên thiết bị |
| Authorization Server | Xác thực user, kiểm tra client/redirect/scope/PKCE và phát code/token |
| External user-agent | Browser hoặc browser tab bảo mật để user đăng nhập |
| Operating system URI dispatcher | Chuyển redirect response tới app đã đăng ký URI |
| Resource Server | Xác minh access token và thực thi API authorization |
| PKCE verifier | Bí mật ngẫu nhiên chỉ app giữ trong transaction hiện tại |
| Redirect URI | Địa chỉ nhận authorization response sau khi user hoàn tất đăng nhập |

## 2. Chọn redirect URI theo nền tảng

Redirect URI là phần quan trọng của client registration. Authorization Server chỉ được redirect authorization response tới URI mà client đã đăng ký và request đã vượt qua validation.

RFC 8252 mô tả ba loại redirect URI phù hợp cho native apps:

| Loại | Ví dụ | Nền tảng phù hợp | Khuyến nghị |
|---|---|---|---|
| Claimed HTTPS URI | `https://app.example.com/oauth2/callback` | Android App Links, iOS Universal Links | Ưu tiên khi nền tảng hỗ trợ xác minh app-domain association |
| Private-use URI scheme | `com.example.mobile:/oauth2redirect/issuer-a` | Android/iOS và desktop | Dùng scheme dựa trên domain do tổ chức sở hữu, viết theo thứ tự domain đảo ngược |
| Loopback IP URI | `http://127.0.0.1:51004/oauth2/callback` | Desktop app có thể mở local listener | Dùng IP literal loopback và port động; không dùng localhost |

### 2.1. Claimed HTTPS URI

Ví dụ:

~~~text
https://app.example.com/oauth2/callback
~~~

Hệ điều hành có thể xác minh ứng dụng được phép xử lý URL thuộc domain này:

- Android dùng Android App Links và file Digital Asset Links tại domain.
- Apple platforms dùng Universal Links và file apple-app-site-association, kết hợp Associated Domains entitlement.
- Domain phải thuộc quyền kiểm soát của tổ chức và cấu hình association phải trỏ đúng package/bundle identifier.

RFC 8252 khuyến nghị native app ưu tiên claimed HTTPS redirect khi có thể, vì hệ điều hành có thể ràng buộc domain với ứng dụng đã xác minh. Dù redirect URI là HTTPS, app vẫn là public client và vẫn phải dùng PKCE.

Không đăng ký HTTPS callback như một web client confidential chỉ vì URI có domain. Client type phải được lưu rõ trong registration và áp dụng chính sách public-client phù hợp.

### 2.2. Private-use URI scheme

Ví dụ:

~~~text
com.example.mobile:/oauth2redirect/authorization-server
~~~

Scheme nên được tạo từ domain do tổ chức sở hữu theo thứ tự đảo ngược. Nếu tổ chức sở hữu example.com, scheme com.example.mobile có cơ sở ownership rõ hơn scheme chung chung như myapp.

Lưu ý cú pháp: sau scheme chỉ có **một dấu /** trước path. Không tự đổi thành com.example.mobile://oauth2redirect/..., vì đó là URI có authority khác với dạng private-use URI scheme được RFC 8252 mô tả.

Nhiều ứng dụng trên cùng thiết bị có thể đăng ký cùng custom scheme. Một app giả mạo có thể cố nhận authorization code trước app thật. PKCE làm code bị chặn không thể đổi thành token nếu app giả không có verifier của transaction gốc. Tuy vậy, claimed HTTPS thường có ràng buộc app identity tốt hơn.

### 2.3. Loopback IP redirect cho desktop

Desktop app có thể mở HTTP listener chỉ trên loopback interface và xin hệ điều hành cấp một ephemeral port:

~~~text
http://127.0.0.1:51004/oauth2/callback
http://[::1]:61023/oauth2/callback
~~~

Quy tắc vận hành:

- Bind listener trên 127.0.0.1 hoặc ::1, không bind 0.0.0.0 hay địa chỉ mạng LAN.
- Mở listener trước khi khởi chạy browser authorization request.
- Dùng port được hệ điều hành cấp; không giả định một port cố định luôn rảnh.
- Authorization Server phải cho phép port thay đổi đối với loopback IP redirect URI, nhưng vẫn phải kiểm tra chính xác scheme, IP literal và path đã đăng ký.
- Đóng listener ngay sau khi nhận response hợp lệ hoặc transaction hết hạn.
- Ưu tiên hỗ trợ cả IPv4 và IPv6 khi nền tảng cho phép.

RFC 8252 không khuyến nghị http://localhost:.... Dùng IP literal tránh DNS resolution và tránh trường hợp listener vô tình nhận traffic từ interface khác.

## 3. Đăng ký native app trong Spring Authorization Server

Mỗi native app cần một RegisteredClient được cấu hình như public client. Ví dụ registration cho ứng dụng mobile:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

RegisteredClient nativeMobile = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("mobile-native")
        .clientName("Example Mobile App")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://app.example.com/oauth2/callback")
        .redirectUri("com.example.mobile:/oauth2redirect/authorization-server")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .build())
        .build();
~~~

Giải thích:

- ClientAuthenticationMethod.NONE xác định client không dùng shared secret tại token endpoint.
- Chỉ đăng ký AuthorizationGrantType.AUTHORIZATION_CODE cho interactive user sign-in.
- redirectUri(...) chỉ chứa callback cụ thể của app.
- OidcScopes.OPENID yêu cầu OIDC Authentication Request và ID Token.
- requireProofKey(true) buộc Authorization Code Flow phải có PKCE.
- requireAuthorizationConsent(true) yêu cầu consent theo client policy; có thể điều chỉnh theo mô hình tin cậy và UX của tổ chức.
- Access token TTL ngắn làm giảm khoảng thời gian token bị lạm dụng nếu thiết bị bị mất hoặc token bị lộ.

Đây là ví dụ registration dùng claimed HTTPS và private-use scheme. Với desktop loopback, đăng ký các base URI đã kiểm soát, ví dụ:

~~~java
.redirectUri("http://127.0.0.1/oauth2/callback")
.redirectUri("http://[::1]/oauth2/callback")
~~~

Sau đó cấu hình redirect validator cho loopback port như phần 5. Không thêm client secret vào registration native app và không nhúng secret vào app binary.

### 3.1. Một registration cho mỗi app/platform/environment

Có thể tạo registration riêng cho:

- Android production và Android staging.
- iOS production và iOS staging.
- Desktop app theo hệ điều hành hoặc theo release channel nếu callback/policy khác nhau.

Cách tách này giúp giới hạn redirect URI, scope, consent policy và lifecycle của từng app. Nếu dùng chung một client_id cho mọi nền tảng, hãy chắc chắn mọi redirect URI đều thực sự thuộc cùng một client product và có cùng security policy. Không thêm callback của app thử nghiệm vào registration production chỉ để tiện debug.

### 3.2. Lưu RegisteredClient bền vững

RegisteredClientRepository quản lý registration và được Authorization Server dùng trong client authentication, authorization grant processing và các protocol flow khác. InMemoryRegisteredClientRepository phù hợp development/testing; production nên dùng persistence như JdbcRegisteredClientRepository hoặc implementation phù hợp với hệ thống.

Registration native app là cấu hình bảo mật. Thay đổi redirect URI, scope hoặc client settings phải được kiểm soát quyền, audit và review; không mở Dynamic Client Registration công khai chỉ để app tự khai báo callback tùy ý.

## 4. Authorization Code Flow kết hợp PKCE

Native app phải dùng Authorization Code Flow kết hợp PKCE. Không dùng Implicit Grant để nhận access token trực tiếp trên redirect và không dùng Resource Owner Password Credentials để thu username/password của user trong app.

Luồng tổng thể:

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Native App
    participant OS as Browser / OS
    participant AS as Authorization Server
    participant API as Resource Server

    App->>App: Generate state, nonce and code_verifier
    App->>App: code_challenge = BASE64URL(SHA256(code_verifier))
    App->>OS: Open external browser with authorization request
    OS->>AS: /oauth2/authorize with redirect_uri and PKCE challenge
    AS->>OS: Login and consent UI
    OS-->>AS: User authenticates and approves
    AS-->>OS: Redirect with authorization code and state
    OS-->>App: OS dispatches callback URI to native app
    App->>App: Verify state and callback URI
    App->>AS: POST /oauth2/token with code_verifier
    AS->>AS: Verify code, client, redirect URI and PKCE
    AS-->>App: Access token and optional OIDC ID Token
    App->>API: API request with access token
    API-->>App: Protected resource response
~~~

### 4.1. Tạo code_verifier và code_challenge

Với mỗi authorization transaction, app tạo một code_verifier ngẫu nhiên, độc lập. Theo RFC 7636, verifier có từ 43 đến 128 ký tự thuộc tập unreserved; khuyến nghị tạo 32 byte ngẫu nhiên bằng cryptographic random generator rồi Base64 URL encode không padding.

Với phương thức S256:

~~~text
code_challenge =
    BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

Client gửi code_challenge và code_challenge_method=S256 ở authorization request. Client giữ code_verifier ở phía app và chỉ gửi nó ở token request sau khi nhận authorization code.

Không dùng plain nếu app hỗ trợ S256. Không tái sử dụng verifier cho nhiều transaction, không lưu verifier vào log, analytics, clipboard hoặc URL.

### 4.2. State và nonce

- state là giá trị ngẫu nhiên, khó đoán, gắn callback với authorization transaction đang chờ. App phải từ chối response thiếu state hoặc state không khớp.
- Với OIDC, nonce gắn ID Token với Authentication Request. App phải kiểm tra nonce trong ID Token nếu đã gửi nonce.
- Lưu state, nonce, code_verifier, redirect URI và issuer trong một transaction object có thời hạn. Xóa transaction sau khi hoàn tất hoặc thất bại.
- Khi app hỗ trợ nhiều Authorization Server, dùng redirect URI riêng cho từng issuer/provider và xác minh callback URI nhận được đúng URI đã gửi trong transaction.

Không lưu duy nhất một biến currentState hoặc currentVerifier dùng chung cho mọi login; nhiều login song song có thể ghi đè dữ liệu của nhau.

## 5. Spring Authorization Server: validation redirect URI

Spring Authorization Server 1.5.8 dùng OAuth2AuthorizationCodeRequestAuthenticationValidator mặc định để validate redirect_uri và scope. Việc so khớp redirect URI mặc định là exact string match.

Điều này phù hợp với claimed HTTPS và private-use scheme khi client gửi URI đã đăng ký chính xác. Tuy nhiên, desktop native app dùng loopback ephemeral port cần xử lý thêm: RFC 8252 yêu cầu Authorization Server cho phép port bất kỳ trên loopback IP URI, trong khi giữ nguyên các thành phần khác của URI.

**Không giải quyết bằng wildcard host/path.** Chỉ bỏ qua port trong trường hợp URI đã đăng ký và URI được yêu cầu đều là HTTP loopback IP literal; scheme, host, path và các thành phần khác vẫn phải khớp.

### 5.1. Cấu hình validator cho Authorization Code endpoint

Spring Authorization Server cho phép thay validator bằng OAuth2AuthorizationCodeRequestAuthenticationProvider.setAuthenticationValidator(). Ví dụ dưới đây giữ nguyên default scope validator và thay phần redirect validation bằng policy hỗ trợ loopback port động.

~~~java
import java.net.URI;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AuthorizationCodeRequestAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AuthorizationCodeRequestAuthenticationException;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AuthorizationCodeRequestAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AuthorizationCodeRequestAuthenticationValidator;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

private static Consumer<List<AuthenticationProvider>>
        configureNativeRedirectUriValidation() {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof OAuth2AuthorizationCodeRequestAuthenticationProvider codeProvider) {
            Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> validator =
                    new NativeRedirectUriValidator()
                            .andThen(OAuth2AuthorizationCodeRequestAuthenticationValidator.DEFAULT_SCOPE_VALIDATOR);

            codeProvider.setAuthenticationValidator(validator);
        }
    });
}

static final class NativeRedirectUriValidator
        implements Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> {

    @Override
    public void accept(
            OAuth2AuthorizationCodeRequestAuthenticationContext context) {

        RegisteredClient client = context.getRegisteredClient();
        String requested = context.getAuthentication().getRedirectUri();

        boolean exactMatch = client.getRedirectUris().contains(requested);
        boolean loopbackPortMatch = !exactMatch
                && client.getRedirectUris().stream()
                .anyMatch(registered -> matchesLoopbackExceptPort(registered, requested));

        if (!exactMatch && !loopbackPortMatch) {
            OAuth2Error error = new OAuth2Error(OAuth2ErrorCodes.INVALID_REQUEST);
            throw new OAuth2AuthorizationCodeRequestAuthenticationException(error, null);
        }
    }

    private static boolean matchesLoopbackExceptPort(
            String registeredValue,
            String requestedValue) {

        if (requestedValue == null) {
            return false;
        }

        try {
            URI registered = URI.create(registeredValue);
            URI requested = URI.create(requestedValue);

            return isLoopbackBase(registered)
                    && isLoopbackRequest(requested)
                    && registered.getPort() == -1
                    && requested.getPort() >= 1
                    && requested.getPort() <= 65535
                    && registered.getHost().equalsIgnoreCase(requested.getHost())
                    && Objects.equals(registered.getRawPath(), requested.getRawPath())
                    && registered.getRawUserInfo() == null
                    && requested.getRawUserInfo() == null
                    && registered.getRawQuery() == null
                    && requested.getRawQuery() == null
                    && registered.getRawFragment() == null
                    && requested.getRawFragment() == null;
        }
        catch (IllegalArgumentException ex) {
            return false;
        }
    }

    private static boolean isLoopbackBase(URI uri) {
        return "http".equalsIgnoreCase(uri.getScheme())
                && isLoopbackIpLiteral(uri.getHost())
                && uri.getPort() == -1
                && uri.getRawUserInfo() == null
                && uri.getRawQuery() == null
                && uri.getRawFragment() == null
                && uri.getRawPath() != null
                && !uri.getRawPath().isEmpty();
    }

    private static boolean isLoopbackRequest(URI uri) {
        return "http".equalsIgnoreCase(uri.getScheme())
                && isLoopbackIpLiteral(uri.getHost())
                && uri.getPort() >= 1
                && uri.getPort() <= 65535
                && uri.getRawUserInfo() == null
                && uri.getRawQuery() == null
                && uri.getRawFragment() == null
                && uri.getRawPath() != null
                && !uri.getRawPath().isEmpty();
    }

    private static boolean isLoopbackIpLiteral(String host) {
        return "127.0.0.1".equals(host)
                || "::1".equals(host)
                || "[::1]".equals(host);
    }
}
~~~

Validator này áp dụng policy cụ thể:

- URI đăng ký phải là HTTP loopback IP literal không có port, user-info, query hoặc fragment.
- URI request phải dùng đúng IP literal và path, chỉ khác port động hợp lệ.
- localhost, hostname bất kỳ, LAN IP, wildcard host, path khác hoặc query/fragment đều không được chấp nhận bởi nhánh dynamic-port.
- Exact match vẫn được chấp nhận cho redirect URI đã đăng ký đầy đủ.

`requireProofKey(true)` buộc request có PKCE challenge và token request có verifier. Native client phải dùng `code_challenge_method=S256`. Nếu policy của tổ chức yêu cầu Authorization Server từ chối cả `plain`, bổ sung kiểm tra `code_challenge_method` trong authentication validator và áp dụng cùng quy tắc cho PAR; đừng suy ra method chỉ từ độ dài hoặc nội dung của challenge.

Đây là ví dụ validator cho Authorization Code endpoint. Nếu deployment bật Pushed Authorization Requests (PAR), phải áp dụng cùng redirect URI policy cho OAuth2PushedAuthorizationRequestAuthenticationProvider; không để PAR và authorization endpoint có hai quy tắc khác nhau.

### 5.2. Gắn validator vào SecurityFilterChain

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

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server -> server
                    .oidc(Customizer.withDefaults())
                    .authorizationEndpoint(endpoint ->
                            endpoint.authenticationProviders(
                                    configureNativeRedirectUriValidation())))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Ví dụ tập trung vào điểm gắn validator; ứng dụng vẫn cần cấu hình user authentication filter chain, RegisteredClientRepository, authorization service, consent service, signing key và các thành phần bắt buộc khác của Authorization Server.

## 6. Authorization Request và Token Request

### 6.1. Authorization Request

Ví dụ OIDC Authorization Code Request từ native app:

~~~http
GET /oauth2/authorize?response_type=code&client_id=mobile-native&redirect_uri=com.example.mobile%3A%2Foauth2redirect%2Fauthorization-server&scope=openid%20profile%20orders.read&state=STATE_RANDOM&nonce=NONCE_RANDOM&code_challenge=PKCE_S256_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: login.example.vn
~~~

Authorization Server kiểm tra:

1. client_id tồn tại và registration là public client.
2. response_type=code và grant type được phép.
3. redirect_uri khớp registration theo redirect policy.
4. scope nằm trong tập scope client được phép yêu cầu.
5. PKCE challenge có mặt vì client yêu cầu proof key.
6. User authentication, consent và authorization policy hoàn tất trước khi phát code.

### 6.2. Authorization Response

Sau khi user xác thực và consent thành công:

~~~http
HTTP/1.1 302 Found
Location: com.example.mobile:/oauth2redirect/authorization-server?code=AUTH_CODE_REDACTED&state=STATE_RANDOM
~~~

Hệ điều hành chuyển URI tới native app. App phải kiểm tra:

- Callback URI đúng với URI đã lưu trong authorization transaction.
- state trùng với giá trị đang chờ.
- Response không chứa OAuth error; nếu có, xử lý như transaction thất bại.
- Transaction chưa hết hạn và chưa được xử lý trước đó.

Không đổi authorization code nếu state sai hoặc callback được nhận từ URI khác với URI đã khởi tạo.

### 6.3. Token Request

Native public client đổi code bằng token request, gửi client_id, redirect URI và code_verifier; không gửi client secret:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=mobile-native&code=AUTH_CODE_REDACTED&redirect_uri=com.example.mobile%3A%2Foauth2redirect%2Fauthorization-server&code_verifier=PKCE_VERIFIER_REDACTED
~~~

Authorization Server xác minh code còn hiệu lực, code thuộc đúng client/redirect URI, chưa được sử dụng và verifier tạo ra challenge đã lưu. Nếu verifier sai, token endpoint phải từ chối request.

Với public client, client_id nhận diện registration; nó không thay thế PKCE và không chứng minh app binary là confidential client.

## 7. Cấu hình callback trên Android, iOS và desktop

### 7.1. Android App Links

Với claimed HTTPS redirect, manifest có thể khai báo intent filter:

~~~xml
<intent-filter android:autoVerify="true">
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data
        android:scheme="https"
        android:host="app.example.com"
        android:path="/oauth2/callback" />
</intent-filter>
~~~

Domain cần publish Digital Asset Links để xác minh package name và signing certificate fingerprint của ứng dụng. Chỉ khai báo intent filter không đủ chứng minh domain ownership.

Nếu dùng private-use scheme, khai báo scheme riêng dựa trên reverse-domain name và kiểm tra callback URI trong AppAuth response handler. Không đăng ký scheme chung như myapp nếu có thể tránh.

### 7.2. iOS Universal Links

Với claimed HTTPS URI:

- Thêm Associated Domains entitlement, ví dụ applinks:app.example.com.
- Host file apple-app-site-association trên domain qua HTTPS.
- Khai báo đúng Team ID, Bundle ID và path callback được phép.
- Xử lý Universal Link trong app delegate hoặc scene delegate, sau đó chuyển URI cho authorization session tương ứng.

Nếu dùng custom scheme, khai báo URL Types trong Info.plist. Scheme vẫn có nguy cơ collision; PKCE và state vẫn bắt buộc.

### 7.3. Desktop loopback

Desktop app nên:

1. Bind HTTP listener trên loopback IP literal với port 0 để hệ điều hành cấp port trống.
2. Lấy port thực tế từ listener và tạo redirect URI tương ứng.
3. Tạo state, code_verifier, code_challenge và lưu transaction.
4. Mở system browser tới Authorization Server.
5. Nhận callback, kiểm tra path/state/transaction, đổi code và đóng listener.
6. Timeout và đóng listener nếu user hủy hoặc flow không hoàn tất.

Không expose callback listener ra mạng LAN. Không chạy listener lâu dài chỉ để chờ OAuth redirect.

## 8. OIDC validation và lưu token trên thiết bị

Nếu native app dùng OIDC bằng scope openid, app phải xử lý ID Token theo OIDC Core. Tối thiểu cần kiểm tra:

- Chữ ký bằng JWK Set của issuer đã discovery/trust.
- iss khớp chính xác issuer đã cấu hình.
- aud chứa client ID của native app; xử lý azp khi áp dụng.
- exp chưa hết hạn và thời gian phát hành hợp lý.
- nonce khớp transaction nếu Authorization Request đã gửi nonce.
- Các claim bổ sung như auth_time, acr, amr nếu ứng dụng có yêu cầu xác thực cụ thể.

Không chỉ Base64 decode ID Token rồi tin payload. ID Token là thông tin về authentication dành cho client; khi gọi API, app gửi access token theo audience/scope mà Resource Server chấp nhận.

### 8.1. Lưu token an toàn

- Ưu tiên giữ access token trong memory và chỉ lưu lâu hơn khi có nhu cầu.
- Nếu cần lưu credential qua lần khởi động, dùng Android Keystore hoặc Apple Keychain với access control phù hợp.
- Không lưu token trong SharedPreferences/UserDefaults dạng plaintext, file log, crash report hoặc analytics.
- Không ghi authorization code, verifier, ID Token hay refresh token vào log.
- Xóa credential khi logout, unlink account, user bị deprovision hoặc thiết bị bị thu hồi theo policy.
- Dùng TLS cho mọi endpoint ngoài loopback callback cục bộ.

### 8.2. Refresh token với public client trong Spring Authorization Server

Spring Authorization Server 1.5.8 hướng dẫn public client qua PKCE và nêu rõ server không phát refresh token cho public client. Vì vậy, không giả định native client registration mẫu ở trên sẽ nhận refresh token chỉ vì app là mobile/desktop.

Nếu sản phẩm cần phiên dài hạn, hãy xác định rõ session policy và khả năng re-authentication. Nếu cần một confidential component giữ refresh token, có thể cân nhắc Backend-for-Frontend (BFF) hoặc một kiến trúc server-side phù hợp. Không nhúng client secret vào native app để cố lấy refresh token.

## 9. Những lỗi đăng ký redirect URI thường gặp

| Lỗi | Rủi ro | Cách xử lý |
|---|---|---|
| Dùng wildcard redirect URI | Code có thể bị gửi tới callback ngoài dự kiến | Đăng ký URI cụ thể và exact match |
| Dùng custom scheme chung chung | App khác có thể chiếm callback | Dùng reverse-domain scheme và PKCE |
| Dùng localhost cho desktop loopback | DNS/interface resolution có thể không như dự kiến | Dùng 127.0.0.1 hoặc [::1] |
| Server chỉ exact-match port loopback | App không dùng được ephemeral port | Cài validator hẹp theo RFC 8252 |
| Validator bỏ qua cả host/path | Có thể mở open redirect hoặc code leakage | Chỉ bỏ qua port của loopback IP literal |
| Nhúng client secret vào binary | Secret có thể bị trích xuất | Đăng ký public client với none |
| Dùng WebView nhúng để login | App có thể đọc credential/cookie và sửa nội dung login | Mở external user-agent |
| Thiếu PKCE | Authorization code có thể bị app khác chặn và đổi | Bắt buộc PKCE S256 |
| Không kiểm tra state | Callback có thể bị gắn vào transaction khác | So khớp state ngẫu nhiên theo transaction |
| Dùng cùng redirect URI cho nhiều issuer | Tăng rủi ro authorization server mix-up | Dùng path khác nhau cho từng issuer |
| Không kiểm tra callback URI nhận được | Response có thể đến từ redirect khác transaction | Lưu và so khớp URI đã gửi |
| Dùng access token như ID Token | Token confusion và lỗi audience | Tách mục đích và validation từng token |

## 10. Kiểm thử native client registration và PKCE

| # | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | Native app đăng ký với ClientAuthenticationMethod.NONE | Registration được coi là public client |
| 2 | Native app gửi client secret giả | Server không coi secret nhúng là bằng chứng confidential client |
| 3 | Authorization Code request có PKCE S256 | Request được xử lý nếu các validation khác đạt |
| 4 | Client không gửi code_challenge | Từ chối vì client yêu cầu proof key |
| 5 | Client gửi verifier sai khi đổi code | Token endpoint từ chối |
| 6 | Client dùng code_challenge_method=plain | Từ chối nếu policy native app chỉ chấp nhận S256 |
| 7 | Verifier ngắn hơn 43 ký tự | Client test không tạo request; server test theo PKCE validation |
| 8 | Verifier dài hơn 128 ký tự | Client test không tạo request; server từ chối giá trị không hợp lệ |
| 9 | Authorization response thiếu state | Native app từ chối callback |
| 10 | State không khớp pending transaction | Native app từ chối callback |
| 11 | Callback URI khác URI đã gửi | Native app từ chối response |
| 12 | HTTPS claimed redirect đã đăng ký chính xác | Redirect tới app association hợp lệ |
| 13 | HTTPS redirect có path khác | Authorization Server từ chối |
| 14 | Private scheme reverse-domain hợp lệ | OS dispatch callback tới app |
| 15 | Private scheme không có dấu chấm | Registration policy từ chối |
| 16 | Custom scheme bị app khác đăng ký | PKCE ngăn app không có verifier đổi code |
| 17 | Loopback IPv4 dùng port ngẫu nhiên | Được chấp nhận nếu validator loopback port được cấu hình |
| 18 | Loopback IPv6 dùng port ngẫu nhiên | Được chấp nhận nếu validator hỗ trợ ::1 |
| 19 | Loopback request dùng localhost | Từ chối theo policy chỉ cho IP literal |
| 20 | Loopback request dùng LAN IP | Từ chối |
| 21 | Loopback request thay path | Từ chối |
| 22 | Loopback request thêm user-info/query/fragment | Từ chối theo validator minh họa |
| 23 | Loopback request dùng port 0 hoặc port ngoài range | Từ chối |
| 24 | URI có scheme khác HTTP trong loopback branch | Từ chối |
| 25 | Request dùng redirect URI không đăng ký | Từ chối với invalid_request |
| 26 | Client yêu cầu scope không được đăng ký | Từ chối với invalid_scope |
| 27 | OIDC request thiếu scope openid | Không được xử lý như OIDC Authentication Request |
| 28 | ID Token có issuer sai | Native OIDC client từ chối |
| 29 | ID Token có audience không chứa client ID | Native OIDC client từ chối |
| 30 | ID Token nonce không khớp | Native OIDC client từ chối |
| 31 | Dùng WebView nhúng để login | Security review phát hiện không phù hợp RFC 8252 |
| 32 | Callback listener bind 0.0.0.0 | Security test thất bại |
| 33 | Listener không đóng sau callback | Lifecycle test thất bại |
| 34 | Hai authorization transaction chạy song song | State/verifier không ghi đè lẫn nhau |
| 35 | Cùng app đăng nhập với hai issuer | Redirect URI và transaction được phân biệt theo issuer |
| 36 | App logout | Token/session local được xóa theo policy |
| 37 | App bị deprovision/revoke | API từ chối token theo revocation/expiry policy |
| 38 | Token/secret được ghi vào log | Secret scanning hoặc log assertion phát hiện |

### 10.1. Kiểm thử loopback validator riêng

Với custom validator, cần có unit test cho từng URI pair:

| URI đăng ký | URI request | Kết quả |
|---|---|---|
| `http://127.0.0.1/oauth2/callback` | `http://127.0.0.1:51004/oauth2/callback` | Accept |
| `http://[::1]/oauth2/callback` | `http://[::1]:61023/oauth2/callback` | Accept |
| `http://127.0.0.1/oauth2/callback` | `http://127.0.0.1:51004/other` | Reject |
| `http://127.0.0.1/oauth2/callback` | `http://localhost:51004/oauth2/callback` | Reject |
| `http://127.0.0.1/oauth2/callback` | `http://192.168.1.10:51004/oauth2/callback` | Reject |
| `http://127.0.0.1/oauth2/callback` | `https://127.0.0.1:51004/oauth2/callback` | Reject |
| `http://127.0.0.1/oauth2/callback` | `http://127.0.0.1:51004/oauth2/callback?next=evil` | Reject |
| `http://127.0.0.1/oauth2/callback` | `http://127.0.0.1:0/oauth2/callback` | Reject |

Ngoài unit test, cần integration test Authorization Endpoint và Token Endpoint để xác minh cùng một redirect URI được ràng buộc vào authorization code và token exchange.

## 11. Troubleshooting và checklist production

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| invalid_client | Client authentication method không khớp public registration | Dùng none, không gửi secret |
| invalid_request ở authorization endpoint | Redirect URI không khớp hoặc thiếu tham số bắt buộc | Kiểm tra registration, state, PKCE và URI |
| invalid_grant ở token endpoint | Code hết hạn/đã dùng, redirect URI hoặc verifier sai | Kiểm tra transaction và gửi đúng verifier |
| Loopback callback port động bị từ chối | SAS default exact match | Cấu hình validator chỉ bỏ qua port cho loopback IP literal |
| HTTPS callback mở website thay vì app | App association chưa đúng | Kiểm tra Digital Asset Links/Universal Links |
| Custom scheme mở nhầm app | Scheme collision | Dùng reverse-domain scheme, ưu tiên claimed HTTPS |
| Callback tới app nhưng không tìm được transaction | State/session store bị mất hoặc dùng một biến toàn cục | Dùng transaction store có TTL và hỗ trợ nhiều flow |
| ID Token validation fail | Issuer/JWK/audience/nonce sai | Kiểm tra OIDC Discovery và transaction |
| Server không cấp refresh token | Public client policy của SAS | Thiết kế re-authentication hoặc BFF; không nhúng secret |
| Token bị lộ qua log | Debug logging hoặc callback logging | Redact query/token và giảm log mức nhạy cảm |

### 11.1. Checklist production

- [ ] Native app được đăng ký là public client với client authentication method none.
- [ ] Không có client secret trong source code, binary, mobile resources hoặc app configuration.
- [ ] Authorization Code Grant được dùng cho interactive user login.
- [ ] PKCE được yêu cầu trong client registration.
- [ ] Native client tạo verifier có entropy cao và dùng S256.
- [ ] External user-agent được dùng để đăng nhập; không dùng embedded WebView.
- [ ] Redirect URI được chọn theo nền tảng: claimed HTTPS, reverse-domain private scheme hoặc loopback IP.
- [ ] Redirect URI có path cụ thể và được đăng ký đầy đủ.
- [ ] Loopback chỉ bind 127.0.0.1/::1, dùng port động và đóng listener sau flow.
- [ ] Nếu hỗ trợ loopback dynamic port, validator chỉ bỏ qua port và giữ nguyên các thành phần URI còn lại.
- [ ] Nếu dùng PAR, cùng redirect validation policy được áp dụng ở PAR endpoint.
- [ ] State, nonce, verifier, issuer và redirect URI được lưu theo từng transaction.
- [ ] Callback kiểm tra state, URI và lỗi trước khi đổi code.
- [ ] Token endpoint nhận đúng code_verifier; không gửi client secret.
- [ ] OIDC client validate chữ ký, issuer, audience, expiry và nonce.
- [ ] Access token được lưu trong memory hoặc OS secure storage theo nhu cầu.
- [ ] Token, code, verifier và secret không xuất hiện trong log/analytics/crash reports.
- [ ] Refresh token behavior của Authorization Server được xác minh thực tế; không giả định public client sẽ nhận refresh token.
- [ ] Có test cho callback collision, redirect mismatch, PKCE failure, multi-issuer và concurrent login.

**Câu hỏi tự đánh giá**

1. Vì sao native app được đăng ký là public client?
2. Tại sao client secret nhúng trong binary không chứng minh được client identity?
3. Authorization Code Flow kết hợp PKCE bảo vệ native app khỏi code interception như thế nào?
4. Ba loại redirect URI trong RFC 8252 là gì?
5. Vì sao claimed HTTPS URI được ưu tiên khi nền tảng hỗ trợ?
6. Vì sao private-use scheme nên dựa trên reverse-domain name và chỉ có một dấu slash sau scheme?
7. Vì sao desktop loopback dùng IP literal thay vì localhost?
8. Tại sao Authorization Server phải cho phép port bất kỳ đối với loopback IP redirect?
9. Vì sao Spring Authorization Server 1.5.8 cần custom redirect validator cho loopback ephemeral port?
10. Validator loopback phải giữ nguyên những URI components nào?
11. ClientAuthenticationMethod.NONE và requireProofKey(true) giải quyết hai vấn đề khác nhau như thế nào?
12. Vì sao không nên dùng Implicit Grant hoặc embedded WebView cho native login?
13. state, nonce và code_verifier có vai trò khác nhau như thế nào?
14. Native app phải xác minh gì trước khi gửi code tới token endpoint?
15. Vì sao access token và ID Token không thể thay thế nhau?
16. Vì sao Spring Authorization Server 1.5.8 public client không nên được giả định sẽ nhận refresh token?
17. Khi một app hỗ trợ nhiều issuer, cần làm gì để giảm rủi ro authorization server mix-up?

## Tài liệu tham khảo

- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252.html): external user-agent, claimed HTTPS/private-use/loopback redirects, public client registration và client authentication.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html): code verifier, S256 challenge và token exchange.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): PKCE, redirect URI và bảo vệ OAuth clients/authorization servers.
- [Spring Authorization Server 1.5.8 — How-to: Authenticate using a Single Page Application with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): public client, ClientAuthenticationMethod.NONE, requireProofKey và token flow; hướng dẫn cũng nêu giới hạn refresh token của public client.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization request validation, default redirect URI validation và setAuthenticationValidator().
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, redirect URI, client authentication method, scopes và ClientSettings.
- [Android Developers — Verify Android App Links](https://developer.android.com/training/app-links/verify-android-applinks): xác minh domain association cho HTTPS app links.
- [Apple Developer — Supporting Associated Domains](https://developer.apple.com/documentation/xcode/supporting-associated-domains): cấu hình Universal Links và domain association.
- [AppAuth for Android](https://github.com/openid/AppAuth-Android) và [AppAuth for iOS](https://github.com/openid/AppAuth-iOS): thư viện native hỗ trợ Authorization Code Flow, external user-agent và PKCE.
