# Lỗi OIDC UserInfo, thiếu JwtDecoder và subject không nhất quán

OIDC UserInfo là endpoint trả về các claim của người dùng đã đăng nhập, chẳng hạn tên và email. Trong Spring Authorization Server, endpoint này chỉ hoạt động đúng khi OIDC được bật, access token được xác thực, các scope được cấp phù hợp và claim `sub` nhất quán với ID Token.

Ba lỗi thường gặp có liên quan chặt chẽ với nhau:

- Client gọi UserInfo nhưng nhận `401`, `403` hoặc `404`.
- Ứng dụng khởi động thất bại với lỗi không tìm thấy bean `JwtDecoder`.
- UserInfo trả về claim `sub` khác với claim `sub` trong ID Token, khiến OIDC client từ chối kết quả.

Bài học này hướng dẫn lần theo request từ discovery đến UserInfo, cấu hình Spring Security để xác thực access token, kiểm tra scope và thiết kế subject identifier dùng chung cho ID Token lẫn UserInfo.

## 1. Hiểu đúng luồng OIDC UserInfo

UserInfo là một OAuth 2.0 protected resource được OIDC định nghĩa. Client dùng **access token** nhận được từ token endpoint để gọi UserInfo. ID Token là bằng chứng xác thực dành cho client; nó không phải bearer token để gọi UserInfo.

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant C as OIDC Client
    participant AS as Authorization Server
    participant U as UserInfo Endpoint

    C->>AS: Authorization Request (scope=openid profile email)
    AS->>AS: Xác thực người dùng và lấy consent
    AS-->>C: Authorization Code
    C->>AS: Token Request (authorization_code + PKCE)
    AS-->>C: ID Token + Access Token
    Note over C: Lưu ID Token và đọc claim sub
    C->>U: GET UserInfo với Bearer Access Token
    U->>U: Xác thực chữ ký, exp, issuer và scope
    U-->>C: JSON claims có sub
    Note over C: So sánh UserInfo.sub với ID Token.sub
~~~

Các nguyên tắc quan trọng:

1. Authorization Request phải có scope `openid` để trở thành một yêu cầu OIDC.
2. Client dùng access token trong header `Authorization: Bearer` khi gọi UserInfo.
3. Access token phải còn hiệu lực và được cấp cho mục đích phù hợp.
4. UserInfo chỉ trả những claim mà client được phép nhận theo scope, consent và chính sách của ứng dụng.
5. Claim `sub` trong UserInfo phải khớp chính xác với claim `sub` trong ID Token của cùng một End-User và cùng phiên xác thực.

Ví dụ request đúng:

~~~http
GET /userinfo HTTP/1.1
Host: auth.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
~~~

Không gửi ID Token trong header này. Nếu client gửi ID Token thay cho access token, server có thể từ chối do token không đúng loại, sai audience hoặc không được chấp nhận tại resource endpoint.

## 2. Nhận diện lỗi qua triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Nơi cần kiểm tra |
|---|---|---|
| Không tìm thấy `userinfo_endpoint` trong discovery | OIDC chưa được bật hoặc metadata không được công bố đúng | Cấu hình OIDC và `/.well-known/openid-configuration` |
| Gọi UserInfo nhận `404` | Sai đường dẫn, endpoint bị proxy rewrite hoặc OIDC UserInfo chưa được bật | `userinfo_endpoint` trong discovery và `AuthorizationServerSettings` |
| Nhận `401` khi gọi UserInfo | Thiếu bearer token, token hết hạn, sai chữ ký, issuer hoặc token không được chấp nhận | Header Authorization, access token và JwtDecoder |
| Nhận `403` hoặc lỗi scope | Access token không có scope cần thiết hoặc chính sách claim từ chối | Scope trong token và consent |
| Ứng dụng không khởi động vì thiếu `JwtDecoder` | Resource Server JWT đã được bật nhưng chưa có decoder để xác thực bearer token | SecurityFilterChain và bean JwtDecoder |
| `JwtDecoder` báo không lấy được khóa hoặc xác minh chữ ký thất bại | JWKSource/JWKS sai, khóa ký không đồng bộ hoặc `kid` không tồn tại | JWKSource, JWKS và quá trình xoay khóa |
| Client báo UserInfo `sub` không khớp ID Token | ID Token và access token/UserInfo dùng cách tạo subject khác nhau | Token customizer, principal mapping và UserInfo mapper |
| UserInfo thiếu `name` hoặc `email` | Thiếu scope, consent hoặc mapper không đưa claim vào response | Scope `profile`, `email` và UserInfo mapper |

Không bắt đầu bằng cách thay đổi nhiều cấu hình cùng lúc. Hãy xác định lỗi xảy ra ở discovery, xác thực access token, phân quyền theo scope hay đối chiếu subject.

## 3. Kiểm tra OIDC Discovery trước khi sửa code

Discovery document cho biết Authorization Server công bố những endpoint nào và client cần dùng issuer nào.

~~~bash
curl -i https://auth.example.com/.well-known/openid-configuration
~~~

Kiểm tra các trường:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "userinfo_endpoint": "https://auth.example.com/userinfo",
  "jwks_uri": "https://auth.example.com/oauth2/jwks"
}
~~~

Đây là JSON minh họa rút gọn. Giá trị thực tế phải lấy từ response của server.

- `issuer` phải là định danh công khai ổn định của Authorization Server.
- `userinfo_endpoint` phải trỏ đến đúng endpoint đang được triển khai.
- `jwks_uri` phải công bố public key dùng để xác minh JWT.
- Client cần dùng chính issuer đã cấu hình để xác minh ID Token.

Nếu `userinfo_endpoint` không xuất hiện, kiểm tra OIDC đã được bật trong Authorization Server configurer chưa. Nếu endpoint được công bố nhưng gọi vào lại nhận `404`, kiểm tra reverse proxy, ingress, context path và endpoint setting. Không tự suy ra đường dẫn từ ví dụ; dùng discovery document làm nguồn chuẩn cho client.

Với Spring Authorization Server, OIDC phải được bật rõ ràng:

~~~java
http.getConfigurer(OAuth2AuthorizationServerConfigurer.class)
        .oidc(Customizer.withDefaults());
~~~

Nếu ứng dụng dùng API configurer mới, đặt cấu hình `oidc(...)` trên chính `OAuth2AuthorizationServerConfigurer` đang gắn với Authorization Server SecurityFilterChain. Không bật OIDC trong một chain khác không xử lý các endpoint của Authorization Server.

## 4. Khắc phục lỗi thiếu JwtDecoder

### 4.1. Vì sao UserInfo cần JwtDecoder?

UserInfo nhận access token qua bearer authentication. Với cấu hình access token dạng JWT self-contained, Spring Security phải xác minh chữ ký và các claim bảo mật trước khi cho request đi vào xử lý UserInfo.

Khi cấu hình:

~~~java
http.oauth2ResourceServer(resourceServer ->
        resourceServer.jwt(Customizer.withDefaults()));
~~~

Spring Security bật cơ chế xác thực bearer JWT. Cơ chế này cần một `JwtDecoder` để giải mã và xác minh token. Nếu không tìm được decoder phù hợp, ứng dụng có thể lỗi ngay lúc khởi tạo SecurityFilterChain hoặc lúc khởi động context.

### 4.2. Dùng JWKSource của chính Authorization Server

Trong Spring Authorization Server, cách thông dụng khi access token được ký bằng khóa do Authorization Server quản lý là tạo decoder từ cùng `JWKSource` đang được dùng để ký token và cung cấp JWKS.

~~~java
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Bean này giả định ứng dụng đã có `JWKSource<SecurityContext>` hợp lệ. Hãy dùng cùng nguồn khóa với Authorization Server để:

- JWT access token được ký bằng private key tương ứng.
- Decoder có thể lấy public key tương ứng để xác minh chữ ký.
- JWKS endpoint công bố public key có `kid` phù hợp với token.
- Các replica có cùng cấu hình khóa và cùng khả năng xác minh token.

Không tạo một cặp khóa ngẫu nhiên riêng chỉ cho decoder. Nếu decoder dùng bộ khóa khác với token generator, request UserInfo sẽ bị từ chối dù access token được phát hành thành công.

### 4.3. Bật Resource Server JWT trong đúng SecurityFilterChain

Ví dụ dưới đây thể hiện cấu hình theo API `applyDefaultSecurity` thường gặp ở các phiên bản Spring Authorization Server trước đây. Nếu dự án đang dùng API configurer mới, giữ nguyên nguyên tắc: OIDC UserInfo và Resource Server JWT phải nằm trong chain xử lý endpoint của Authorization Server.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfiguration.applyDefaultSecurity(http);

    http.getConfigurer(OAuth2AuthorizationServerConfigurer.class)
            .oidc(Customizer.withDefaults());

    http.oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

Nếu chain hiện tại đã có cấu hình OIDC, chỉ bổ sung cấu hình Resource Server JWT vào đúng chain đó và kiểm tra bean decoder. Không tạo thêm một chain trùng matcher để xử lý cùng endpoint; thứ tự chain có thể khiến request UserInfo đi vào nhầm cấu hình.

Với API configurer mới, cấu trúc thường có dạng:

~~~java
OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults()))
        .oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(Customizer.withDefaults()));
~~~

Đoạn này chỉ minh họa phần gắn configurer và Resource Server; giữ nguyên các quy tắc authorization, exception handling và các cấu hình khác mà ứng dụng đang cần.

### 4.4. Phân biệt decoder cục bộ và decoder gọi JWKS qua HTTP

Có hai cách phổ biến để một Resource Server xác minh JWT:

- Dùng `JWKSource` cục bộ của Authorization Server để tạo `JwtDecoder`. Cách này phù hợp khi UserInfo nằm ngay trong Authorization Server và dùng chung kho khóa.
- Dùng `issuer-uri` hoặc `jwk-set-uri` để cấu hình một Resource Server độc lập xác minh token qua metadata/JWKS endpoint.

Ví dụ cấu hình cho một Resource Server độc lập:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://auth.example.com
~~~

Hoặc cấu hình trực tiếp địa chỉ JWKS:

~~~properties
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://auth.example.com/oauth2/jwks
~~~

Không cấu hình decoder gọi ngược qua public ingress của chính Authorization Server nếu không cần thiết. Việc đó thêm phụ thuộc DNS, TLS, proxy và network vào quá trình xác thực request. Trong cùng một ứng dụng, dùng JWKSource cục bộ thường đơn giản và ít điểm lỗi hơn.

Nếu ứng dụng dùng access token dạng opaque/reference, `JwtDecoder` không thể giải mã token đó. Cần dùng cơ chế introspection phù hợp với kiến trúc Resource Server và xác minh phiên bản Spring Authorization Server đang dùng hỗ trợ loại token đó cho UserInfo như thế nào. Không biến token opaque thành JWT bằng cách tự parse chuỗi token.

## 5. Xác minh access token trước khi gọi UserInfo

Sau khi có decoder, vẫn cần xác nhận access token đáp ứng yêu cầu của endpoint.

### 5.1. Gửi đúng loại token

Client phải gửi access token nhận từ token endpoint:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  https://auth.example.com/userinfo
~~~

Không dùng:

- Authorization code.
- ID Token.
- Refresh token.
- Client secret.
- Một JWT bất kỳ được ký bởi cùng một private key nhưng không được cấp làm access token.

Không ghi access token đầy đủ vào log, ticket hoặc ảnh chụp màn hình. Khi cần đối chiếu, chỉ ghi metadata không nhạy cảm như `kid`, issuer, thời hạn và một định danh request.

### 5.2. Kiểm tra các claim bảo mật

Khi access token là JWT, kiểm tra tối thiểu:

| Claim hoặc thuộc tính | Điều cần xác minh |
|---|---|
| Chữ ký | Chữ ký hợp lệ với public key tương ứng |
| `iss` | Khớp issuer được tin cậy |
| `exp` | Token chưa hết hạn |
| `nbf` | Token đã đến thời điểm có hiệu lực |
| `aud` | Audience phù hợp với chính sách của resource |
| `sub` | Xác định đúng End-User trong luồng người dùng |
| `scope` | Có các quyền cần thiết để trả claim |
| `kid` | Tồn tại trong JWKS mà decoder đang sử dụng |

Không phải mọi access token đều có cùng tập claim. Hãy kiểm tra token thực tế và chính sách phát hành của ứng dụng. Client credentials token không đại diện cho End-User; không dùng nó để truy vấn thông tin cá nhân qua OIDC UserInfo.

### 5.3. Kiểm tra scope và consent

Các scope OIDC thường liên quan đến UserInfo:

| Scope | Nhóm claim thường được phép trả |
|---|---|
| `openid` | Kích hoạt luồng OIDC |
| `profile` | Tên, tên hiển thị, ảnh đại diện, locale và các claim hồ sơ khác |
| `email` | Email và trạng thái xác minh email |
| `address` | Địa chỉ |
| `phone` | Số điện thoại và trạng thái xác minh số điện thoại |

Scope được yêu cầu trong authorization request chưa chắc đã được cấp đầy đủ. Cần kiểm tra scope đã được người dùng consent, được client cho phép và có trong authorization/access token hay chưa.

Ví dụ authorization request có thể chứa:

~~~text
scope=openid%20profile%20email
~~~

Nếu chỉ có `openid`, client không nên kỳ vọng UserInfo trả về email hoặc toàn bộ profile. Không giải quyết lỗi thiếu claim bằng cách trả mọi thuộc tính người dùng cho mọi client.

## 6. Khắc phục subject không nhất quán

### 6.1. Quy tắc bắt buộc của OIDC

`sub` là định danh của End-User tại issuer. Với cùng một End-User trong cùng một phiên xác thực, giá trị `sub` ở UserInfo phải giống chính xác giá trị `sub` trong ID Token.

Ví dụ hợp lệ:

~~~json
{
  "id_token": {
    "iss": "https://auth.example.com",
    "sub": "usr_7d91a2",
    "aud": "mobile-client"
  },
  "userinfo": {
    "sub": "usr_7d91a2",
    "name": "Nguyen Van A",
    "email": "user@example.com"
  }
}
~~~

Ví dụ không hợp lệ:

~~~json
{
  "id_token": {
    "sub": "usr_7d91a2"
  },
  "userinfo": {
    "sub": "user@example.com"
  }
}
~~~

Trong ví dụ sai, ID Token dùng mã người dùng nội bộ còn UserInfo dùng email. Email có thể thay đổi và không phải định danh OIDC phù hợp để thay thế subject. Client có quyền từ chối response vì hai giá trị không khớp.

### 6.2. Những nguyên nhân thường làm sub bị lệch

- ID Token dùng `Authentication.getName()`, còn UserInfo mapper dùng email hoặc username.
- Token customizer chỉ sửa `sub` của ID Token mà không sửa subject trong JWT access token.
- Một nơi dùng ID database, nơi khác dùng external identity ID.
- UserInfo truy vấn người dùng qua email đã thay đổi hoặc username có thể được đổi tên.
- Các replica chạy phiên bản khác nhau của subject mapping.
- Ứng dụng chuyển từ public subject sang pairwise subject nhưng chỉ cập nhật một luồng token.
- Client hoặc user profile được di chuyển dữ liệu nhưng không giữ mapping subject cũ.

Hãy chọn một nguồn định danh ổn định và một quy tắc tạo subject duy nhất. Không dùng tên hiển thị, số điện thoại hoặc email làm subject nếu các thuộc tính đó có thể thay đổi.

### 6.3. Lấy sub từ access token khi tạo UserInfo

Khi access token JWT đã mang subject đúng, UserInfo mapper có thể dùng chính subject của token đó làm claim `sub`. Ví dụ:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

import org.springframework.security.oauth2.core.oidc.IdTokenClaimNames;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

authorizationServerConfigurer.oidc(oidc -> oidc
    .userInfoEndpoint(userInfo -> userInfo
        .userInfoMapper(context -> {
            JwtAuthenticationToken jwtPrincipal =
                    (JwtAuthenticationToken) context.getPrincipal();

            String subject = jwtPrincipal.getToken().getSubject();
            Set<String> scopes = context.getAuthorization().getAuthorizedScopes();

            UserProfile profile = userProfileService.findBySubject(subject);

            Map<String, Object> claims = new HashMap<>();
            claims.put(IdTokenClaimNames.SUB, subject);

            if (scopes.contains(OidcScopes.PROFILE)) {
                claims.put("name", profile.getDisplayName());
            }

            if (scopes.contains(OidcScopes.EMAIL)) {
                claims.put("email", profile.getEmail());
                claims.put("email_verified", profile.isEmailVerified());
            }

            return new OidcUserInfo(claims);
        })
    )
);
~~~

`UserProfile` và `userProfileService` là thành phần thuộc ứng dụng. Hãy tra cứu profile bằng định danh ổn định tương ứng với subject, sau đó chỉ đưa claim được scope và consent cho phép vào response.

Đoạn mapper giả định endpoint đang xác thực JWT và principal là `JwtAuthenticationToken`. Nếu ứng dụng dùng một loại principal khác, hãy điều chỉnh mapper theo authentication type thực tế; không ép kiểu tùy tiện rồi bỏ qua lỗi xác thực.

### 6.4. Dùng cùng một subject resolver cho ID Token và access token

Nếu ứng dụng có quy tắc subject riêng, hãy gom quy tắc đó vào một service dùng chung. Khi customizer thay đổi `sub` của ID Token, cần bảo đảm JWT access token được dùng để gọi UserInfo cũng có cùng subject.

Ví dụ về cấu trúc customizer:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.oidc.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> subjectCustomizer(
        SubjectIdentifierService subjectIdentifierService) {

    return context -> {
        String tokenType = context.getTokenType().getValue();

        boolean userToken =
                OAuth2TokenType.ACCESS_TOKEN.getValue().equals(tokenType)
                || OidcParameterNames.ID_TOKEN.equals(tokenType);

        if (userToken
                && !AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
                        context.getAuthorizationGrantType())) {
            String subject = subjectIdentifierService.resolve(
                    context.getPrincipal(),
                    context.getRegisteredClient());

            context.getClaims().subject(subject);
        }
    };
}
~~~

`SubjectIdentifierService` là service do ứng dụng triển khai. Service này cần xác định cùng một End-User và cùng một client/sector theo một quy tắc ổn định. Nếu ứng dụng không cần subject tùy chỉnh, không cần thêm customizer chỉ để thay đổi `sub`; subject mặc định nhất quán có thể đã đáp ứng yêu cầu.

Với pairwise subject, subject có thể khác giữa các sector theo thiết kế OIDC. Tuy nhiên, ID Token và UserInfo của cùng client và cùng phiên xác thực vẫn phải dùng cùng một giá trị. Không tự tính pairwise subject riêng trong UserInfo mapper.

### 6.5. Tránh trả claim vượt quá consent

Mapper không nên serialize toàn bộ entity người dùng. Hãy tạo allowlist claim theo scope:

- `profile`: chỉ các thuộc tính profile đã được cho phép.
- `email`: email và `email_verified`.
- `address`: địa chỉ theo cấu trúc OIDC.
- `phone`: số điện thoại và `phone_number_verified`.

Không coi việc client yêu cầu scope là bằng chứng duy nhất rằng người dùng đã đồng ý. Cần áp dụng chính sách consent và client registration của Authorization Server.

## 7. Kiểm tra cấu hình endpoint và bảo mật

### 7.1. Kiểm tra đường dẫn UserInfo

Đường dẫn mặc định thường là `/userinfo`, nhưng ứng dụng có thể thay đổi endpoint setting hoặc đặt sau context path/proxy. Client phải lấy đường dẫn từ discovery document thay vì hardcode.

Khi gặp `404`, lần lượt kiểm tra:

1. OIDC đã được bật trên Authorization Server configurer chưa?
2. Discovery document có trường `userinfo_endpoint` không?
3. Request có đi qua đúng ingress, reverse proxy và application context path không?
4. `AuthorizationServerSettings` có thay đổi UserInfo endpoint không?
5. SecurityFilterChain có matcher bao phủ endpoint đó không?

### 7.2. Kiểm tra SecurityFilterChain

Authorization Server thường có một chain riêng với thứ tự ưu tiên cao hơn chain ứng dụng. Nếu chain khác bắt request UserInfo trước, bearer token có thể không được xử lý theo cấu hình Resource Server mong muốn.

Kiểm tra:

- Chain xử lý đúng endpoint matcher của Authorization Server.
- OIDC UserInfo được bật trong chain đó.
- `oauth2ResourceServer(...).jwt(...)` được cấu hình trong chain xử lý UserInfo.
- `JwtDecoder` được Spring tìm thấy trong application context.
- Không có rule yêu cầu form login hoặc session cho một request UserInfo vốn phải xác thực bằng bearer token.

Không mở endpoint UserInfo cho anonymous. UserInfo phải yêu cầu access token hợp lệ.

### 7.3. Kiểm tra issuer và public URL sau reverse proxy

Nếu ứng dụng chạy sau ingress, issuer phải là URL công khai. Cấu hình forwarded headers và proxy phải nhất quán để discovery, token và UserInfo cùng dùng đúng host/scheme.

Các lỗi như token có `iss=http://authorization-server:8080` trong khi discovery công bố `https://auth.example.com` có thể làm decoder hoặc client từ chối token. Kiểm tra cả:

- `AuthorizationServerSettings.issuer`.
- Trường `issuer` trong discovery.
- Claim `iss` trong ID Token và access token.
- URL công khai trong `userinfo_endpoint` và `jwks_uri`.

Không dùng hostname của pod hoặc địa chỉ service nội bộ làm issuer công khai.

## 8. Quy trình chẩn đoán theo thứ tự

Thực hiện theo chuỗi sau để khoanh vùng lỗi nhanh:

1. **Discovery:** lấy `/.well-known/openid-configuration`; xác nhận issuer và `userinfo_endpoint`.
2. **OIDC config:** xác nhận `oidc(Customizer.withDefaults())` hoặc cấu hình OIDC tương đương đã được bật.
3. **Decoder:** xác nhận có bean `JwtDecoder` và Resource Server JWT được cấu hình trên đúng SecurityFilterChain.
4. **Token:** lấy access token mới từ token endpoint; không tái sử dụng token cũ sau khi đổi cấu hình khóa hoặc issuer.
5. **JWT:** kiểm tra chữ ký, `kid`, `iss`, `exp`, `nbf`, `aud` và `sub`.
6. **Scope:** xác nhận access token có `openid` và các scope claim mà client cần.
7. **Request:** gọi UserInfo với access token trong bearer header.
8. **Response:** xác nhận JSON có `sub`, rồi so sánh với `sub` của ID Token.
9. **Mapper:** nếu thiếu claim, kiểm tra authorized scopes, consent và allowlist của UserInfo mapper.
10. **Replica:** nếu lỗi chỉ xảy ra ngẫu nhiên, so sánh issuer, JWK set, subject mapping và phiên bản cấu hình giữa các replica.

Lấy token mới sau khi thay đổi signing key hoặc decoder giúp loại bỏ trường hợp đang kiểm tra một token được ký bởi khóa cũ.

## 9. Kiểm thử hồi quy cho UserInfo

Một kiểm thử tích hợp nên lấy token qua luồng OAuth/OIDC thật hoặc fixture JWT được ký bằng khóa kiểm thử. Sau đó xác minh response của UserInfo.

Ví dụ với MockMvc khi đã có access token hợp lệ:

~~~java
mvc.perform(get(userInfoEndpoint)
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.sub").value(expectedSubject));
~~~

Các ca kiểm thử nên bao gồm:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Access token hợp lệ, có scope `openid profile` | UserInfo trả `sub` và claim profile được cho phép |
| Access token có `openid email` | UserInfo trả `sub`, email và trạng thái xác minh nếu chính sách cho phép |
| Thiếu bearer token | Request bị từ chối |
| Token hết hạn hoặc chữ ký sai | Request bị từ chối trong bước xác thực |
| Token không có scope cần thiết | Claim tương ứng không được trả hoặc request bị từ chối theo chính sách |
| Gửi ID Token thay access token | Request không được chấp nhận như một bearer access token hợp lệ |
| ID Token và UserInfo có subject khác nhau | Kiểm thử phát hiện lỗi; client không được coi response là hợp lệ |
| Pairwise subject | ID Token và UserInfo của cùng client/sector có cùng subject |
| Xoay khóa | Token hợp lệ được ký bằng khóa đang hoạt động vẫn được decoder xác minh; public key cần thiết vẫn có trong JWKS |

Một kiểm thử quan trọng là so sánh trực tiếp:

~~~java
assertThat(userInfo.getSubject()).isEqualTo(idToken.getSubject());
~~~

Đây là điều kiện cốt lõi để client tin rằng UserInfo đang mô tả đúng End-User được xác thực trong ID Token.

## 10. Bảng xử lý nhanh

| Lỗi | Hướng xử lý |
|---|---|
| Không có `userinfo_endpoint` | Bật OIDC trên Authorization Server configurer và kiểm tra discovery |
| `404` tại UserInfo | Dùng URL từ discovery; kiểm tra proxy, context path và endpoint setting |
| Không có bean `JwtDecoder` | Khai báo decoder từ JWKSource hoặc cấu hình decoder phù hợp với nguồn token |
| `401 invalid_token` | Gửi access token; kiểm tra chữ ký, issuer, thời hạn, audience và JWKS |
| `403 insufficient_scope` | Kiểm tra scope được cấp, consent và chính sách mapper |
| Thiếu `sub` trong response | Bắt buộc đưa subject vào UserInfo response |
| `sub` khác ID Token | Dùng một subject resolver cho ID Token và access token/UserInfo |
| Email/profile không xuất hiện | Yêu cầu scope tương ứng, kiểm tra consent và mapper |
| Chỉ một số replica lỗi | Đồng bộ JWKSource, issuer, subject resolver và cấu hình giữa replica |

## 11. Checklist trước khi phát hành

- [ ] OIDC được bật trên Authorization Server SecurityFilterChain.
- [ ] Discovery công bố đúng `issuer`, `userinfo_endpoint` và `jwks_uri`.
- [ ] Resource Server JWT được cấu hình trên chain xử lý UserInfo.
- [ ] Có `JwtDecoder` phù hợp với định dạng access token.
- [ ] Decoder xác minh bằng nguồn public key đúng với khóa ký của Authorization Server.
- [ ] Client gửi access token trong bearer header, không gửi ID Token hoặc refresh token.
- [ ] Scope và consent quyết định đúng nhóm claim được trả.
- [ ] UserInfo luôn trả claim `sub`.
- [ ] `sub` trong UserInfo khớp chính xác với `sub` trong ID Token.
- [ ] Subject được tạo từ định danh ổn định; không phụ thuộc email hoặc tên hiển thị có thể thay đổi.
- [ ] Nếu dùng pairwise subject, cùng một resolver được áp dụng cho ID Token và access token.
- [ ] Các replica dùng chung issuer, khóa ký/JWKS và subject mapping.
- [ ] Có kiểm thử cho token sai, token hết hạn, thiếu scope, subject mismatch và xoay khóa.
- [ ] Log không ghi bearer token, ID Token hoặc dữ liệu cá nhân đầy đủ.

Khi chẩn đoán OIDC UserInfo, hãy xác định request đang thất bại ở bước nào: discovery, xác thực bearer token, kiểm tra scope hay đối chiếu subject. Cấu hình đúng `JwtDecoder` giúp server xác thực access token; một subject resolver dùng chung bảo đảm UserInfo mô tả đúng End-User mà ID Token đã xác nhận.
