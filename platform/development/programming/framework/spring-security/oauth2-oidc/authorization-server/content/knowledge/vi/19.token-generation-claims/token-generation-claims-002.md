# JwtGenerator, OAuth2AccessTokenGenerator và OAuth2RefreshTokenGenerator

## Mục tiêu bài học

Trong chương **Token và claims** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này giải thích ba implementation quan trọng của Spring Authorization Server dùng để tạo token: **JwtGenerator**, **OAuth2AccessTokenGenerator** và **OAuth2RefreshTokenGenerator**. Chúng nhận ngữ cảnh **OAuth2TokenContext** và được phối hợp qua **DelegatingOAuth2TokenGenerator** trong ứng dụng **Spring Boot** dùng **Spring Security**.

Ba generator không phải ba cách viết khác nhau của cùng một token. Mỗi implementation đảm nhiệm một loại hoặc định dạng token cụ thể: JWT tự chứa, access token opaque/reference và refresh token. Việc chọn generator ảnh hưởng đến cách Resource Server xác minh token, cách claims được lưu, khả năng thu hồi và cách vận hành khóa.

Sau bài học, bạn có thể:

- Giải thích vai trò của **OAuth2TokenGenerator**, **OAuth2TokenContext** và **DelegatingOAuth2TokenGenerator**.
- Phân biệt **JwtGenerator** với **OAuth2AccessTokenGenerator** theo **OAuth2TokenFormat.SELF_CONTAINED** và **OAuth2TokenFormat.REFERENCE**.
- Hiểu vì sao **OAuth2RefreshTokenGenerator** tạo refresh token riêng và không phụ thuộc định dạng access token.
- Đăng ký generator theo cách mặc định hoặc cấu hình tường minh trong **OAuth2AuthorizationServerConfigurer**.
- Dùng **OAuth2TokenCustomizer<JwtEncodingContext>** để tùy chỉnh header/claims của JWT.
- Dùng **OAuth2TokenCustomizer<OAuth2TokenClaimsContext>** để tùy chỉnh claims của opaque access token.
- Cấu hình TTL, refresh token reuse/rotation và lưu authorization nhất quán.
- Kiểm thử token theo từng định dạng, grant, client, Resource Server và vòng đời thu hồi.

> **Tình huống xuyên suốt:** Authorization Server cấp token cho **inventory-worker** và **employee-portal**. API nội bộ cần JWT để tự xác minh chữ ký, còn một hệ thống đối tác muốn opaque token để tra trạng thái qua introspection. Cả hai đều phải dùng đúng scope, issuer, audience và thời hạn; ứng dụng OIDC còn cần ID Token riêng.

## 1. Tổng quan về token generation

Sau khi client được xác thực và grant được kiểm tra, Authorization Server cần tạo token theo yêu cầu. Spring Authorization Server cung cấp interface **OAuth2TokenGenerator<T extends OAuth2Token>**. Phương thức chính:

~~~java
T generate(OAuth2TokenContext context);
~~~

Generator nhận **OAuth2TokenContext** chứa thông tin grant và trả token phù hợp với **context.getTokenType()**. Nếu implementation không hỗ trợ loại token đó, nó trả **null** để generator khác có cơ hội xử lý.

Các thành phần liên quan:

| Thành phần | Trách nhiệm |
|---|---|
| **OAuth2TokenContext** | Mang thông tin client, principal, authorization, grant type, scope, token type và môi trường Authorization Server. |
| **OAuth2TokenGenerator** | Tạo một loại OAuth2Token từ context. |
| **JwtGenerator** | Tạo JWT dùng làm access token tự chứa hoặc OIDC ID Token. |
| **OAuth2AccessTokenGenerator** | Tạo access token dạng opaque/reference. |
| **OAuth2RefreshTokenGenerator** | Tạo refresh token. |
| **DelegatingOAuth2TokenGenerator** | Gọi lần lượt các generator con cho đến khi một generator trả token khác null. |
| **OAuth2TokenCustomizer** | Tùy chỉnh header/claims trong lúc generator xây token. |
| **OAuth2AuthorizationService** | Lưu authorization và các token/metadata liên quan sau khi grant provider xử lý. |

**Ranh giới quan trọng:** Generator chịu trách nhiệm **tạo giá trị token**. Nó không thay thế việc xác thực client, kiểm tra authorization grant, quyết định scope được cấp, lưu authorization, xác minh token ở Resource Server hay thu hồi token. Những việc đó thuộc các thành phần khác của Authorization Server và Resource Server.

### 1.1. Token generation diễn ra ở đâu trong grant flow?

~~~mermaid
flowchart TD
    A[HTTP request tới Token Endpoint hoặc Authorization flow] --> B[AuthenticationConverter]
    B --> C[AuthenticationProvider]
    C --> D[Xác thực client, grant, scope và trạng thái]
    D --> E[OAuth2TokenContext.Builder]
    E --> F[OAuth2TokenGenerator.generate]
    F --> G{Token type / format}
    G -->|SELF_CONTAINED access token hoặc ID Token| H[JwtGenerator]
    G -->|REFERENCE access token| I[OAuth2AccessTokenGenerator]
    G -->|refresh_token| J[OAuth2RefreshTokenGenerator]
    H --> K[OAuth2Authorization lưu token]
    I --> K
    J --> K
    K --> L[Token response hoặc authorization response]
~~~

Sơ đồ là mô hình khái niệm. Mỗi grant provider tạo context và yêu cầu những token cần thiết. Ví dụ Client Credentials thường chỉ cần access token; Authorization Code có thể tạo access token, ID Token khi OIDC được dùng và refresh token nếu policy cho phép.

### 1.2. Token type khác token format

- **Token type** mô tả mục đích token được tạo, ví dụ **access_token**, **refresh_token** hoặc **id_token**.
- **Token format** mô tả biểu diễn access token, ví dụ JWT tự chứa hoặc opaque/reference.

Không nhầm **OAuth2TokenType.ACCESS_TOKEN** với **OAuth2TokenFormat.SELF_CONTAINED**. Một access token có token type là access token, nhưng format có thể là JWT hoặc opaque theo cấu hình RegisteredClient.

## 2. OAuth2TokenContext: dữ liệu đầu vào của generator

**OAuth2TokenContext** là context chung cho token generation và token customization. Những thông tin quan trọng gồm:

| Accessor | Ý nghĩa |
|---|---|
| **getRegisteredClient()** | RegisteredClient đang thực hiện grant. |
| **getPrincipal()** | Authentication của resource owner hoặc client tùy grant. |
| **getAuthorizationServerContext()** | Issuer và ngữ cảnh runtime của Authorization Server. |
| **getAuthorization()** | Authorization hiện tại nếu đã có. |
| **getAuthorizedScopes()** | Các scope đã được cấp cho grant. |
| **getTokenType()** | Loại token đang cần tạo. |
| **getAuthorizationGrantType()** | Grant type đang được xử lý. |
| **getAuthorizationGrant()** | Authentication đại diện authorization grant đầu vào. |

Context này giúp customizer chỉ thêm claims trong đúng trường hợp. Ví dụ, claim **service_class** có thể áp dụng cho access token của **inventory-worker** nhưng không nên tự động xuất hiện trong ID Token của nhân viên.

### 2.1. Ví dụ kiểm tra context

~~~java
if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
        && AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
                context.getAuthorizationGrantType())
        && "inventory-worker".equals(
                context.getRegisteredClient().getClientId())) {
    // Chính sách chỉ dành cho access token M2M của inventory-worker.
}
~~~

Đây là điều kiện minh họa dùng trong customizer. Không kiểm tra client ID từ một request parameter tùy ý sau khi đã có context; sử dụng **RegisteredClient** đã được xác thực. Với nhiều tenant, phải xác định nguồn tenant tin cậy và ràng buộc nó với client/principal.

## 3. JwtGenerator: tạo JWT tự chứa

**JwtGenerator** triển khai **OAuth2TokenGenerator<Jwt>** và dùng **JwtEncoder** để ký/mã hóa JWT. Trong Spring Authorization Server, generator này được dùng để tạo:

- **Access token JWT** khi RegisteredClient dùng **OAuth2TokenFormat.SELF_CONTAINED**.
- **OIDC ID Token** khi luồng OIDC cần **id_token**.

Một JWT thường có ba phần Base64URL:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Header thường chứa **alg** và **kid**; payload chứa claims như **iss**, **sub**, **aud**, **exp**, **iat**, **jti** và các claim theo policy. Resource Server có thể xác minh chữ ký bằng public key/JWKS mà không cần gọi introspection cho mỗi request, nếu token profile và kiến trúc cho phép.

### 3.1. Tạo JwtGenerator

~~~java
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.server.authorization.token.JwtGenerator;

JwtGenerator jwtGenerator = new JwtGenerator(jwtEncoder);
~~~

**jwtEncoder** phải được cấu hình bằng khóa ký phù hợp. Trong triển khai phổ biến dùng **NimbusJwtEncoder** với **JWKSource<SecurityContext>**. Không tạo khóa mới mỗi lần request; khóa phải được quản lý, công bố qua JWKS và có quy trình rotation.

Ví dụ cấu hình JWKSource/JwtEncoder là một phần của hạ tầng ký token. Nếu đã có bean **JwtEncoder** hoặc **JWKSource<SecurityContext>**, không cần tự tạo encoder khác chỉ để thêm claims; có thể dùng generator mặc định và customizer đúng loại.

### 3.2. Tùy chỉnh header và claims của JWT

**JwtGenerator** cung cấp:

~~~java
jwtGenerator.setJwtCustomizer(
        OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer);
~~~

**JwtEncodingContext** cho phép đọc token context, thêm header JWS và chỉnh claims trước khi **JwtEncoder** ký JWT.

Ví dụ:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
                        context.getAuthorizationGrantType())
                && "inventory-worker".equals(
                        context.getRegisteredClient().getClientId())) {

            context.getClaims().claim("service_class", "inventory");
            context.getClaims().claim("policy_version", "v2");
        }
    };
}
~~~

Các claims ở đây minh họa dữ liệu **không nhạy cảm** dành riêng cho access token của một client. Không áp dụng cùng logic cho ID Token nếu không có yêu cầu OIDC rõ ràng. Không thêm secret, private key, mật khẩu, refresh token hoặc dữ liệu cá nhân không cần thiết.

Nếu cần header tùy chỉnh, context có **getJwsHeader()**:

~~~java
context.getJwsHeader().keyId("active-signing-key");
~~~

Thông thường **kid** và thuật toán nên được **JwtEncoder/JWK configuration** quản lý. Chỉ thay header khi đã có lý do tương thích và quy trình rotation rõ ràng; không tự đặt thuật toán yếu hoặc thuật toán do client yêu cầu.

### 3.3. Không ghi đè claims tiêu chuẩn tùy tiện

Các claims như **iss**, **sub**, **aud**, **exp**, **iat**, **jti** và **scope** có ý nghĩa giao thức/bảo mật. Nếu customizer thay đổi chúng sai cách:

- Resource Server có thể từ chối token do issuer/audience không đúng.
- Token có thể sống lâu hơn TTL đã cấu hình.
- Scope trong token có thể không khớp **OAuth2Authorization.authorizedScopes**.
- ID Token có thể không còn hợp lệ theo OIDC Core.
- Audit và introspection có thể diễn giải sai chủ thể/đối tượng.

Chỉ bổ sung claim khi có owner, ý nghĩa, nguồn dữ liệu tin cậy và validator ở Resource Server. Nếu cần thay đổi audience, hãy cấu hình audience theo API thực sự nhận token, không lấy giá trị từ tham số không được kiểm chứng.

## 4. OAuth2AccessTokenGenerator: tạo opaque/reference access token

**OAuth2AccessTokenGenerator** tạo access token dạng **reference/opaque**. Token gửi cho client là một chuỗi không tự mô tả claims như JWT. Authorization Server lưu trạng thái token trong **OAuth2AuthorizationService**; Resource Server thường kiểm tra bằng **Token Introspection** hoặc cơ chế tra cứu được triển khai.

### 4.1. Khi nào generator này được dùng?

Spring Authorization Server chọn định dạng access token dựa trên **TokenSettings.getAccessTokenFormat()** của RegisteredClient:

| Access token format | Generator | Token client nhận |
|---|---|---|
| **OAuth2TokenFormat.SELF_CONTAINED** (mặc định) | **JwtGenerator** | JWT tự chứa, có thể xác minh bằng chữ ký/JWKS. |
| **OAuth2TokenFormat.REFERENCE** | **OAuth2AccessTokenGenerator** | Opaque token; trạng thái/claims được lưu ở Authorization Server. |

Ví dụ client dùng opaque access token:

~~~java
RegisteredClient partnerApi = RegisteredClient
        .withId("partner-api-v1")
        .clientId("partner-api")
        .clientSecret(passwordEncoder.encode(partnerSecret))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .tokenSettings(TokenSettings.builder()
                .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .build())
        .build();
~~~

Đây là phần đăng ký client minh họa; cần có **PasswordEncoder**, nguồn secret, repository và các Bean khác. Với opaque token, client vẫn nhận access token để gửi Bearer header; chỉ Resource Server mới cần biết cách tra trạng thái token.

### 4.2. Tùy chỉnh claims của opaque access token

**OAuth2AccessTokenGenerator** có method:

~~~java
accessTokenGenerator.setAccessTokenCustomizer(
        OAuth2TokenCustomizer<OAuth2TokenClaimsContext> accessTokenCustomizer);
~~~

**OAuth2TokenClaimsContext** cung cấp **getClaims()** để thêm, thay hoặc xóa claims của opaque access token. Ví dụ:

~~~java
@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueAccessTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && "partner-api".equals(
                        context.getRegisteredClient().getClientId())) {
            context.getClaims().claim("integration_tier", "partner");
        }
    };
}
~~~

Các claims không được nhúng rõ trong chuỗi opaque token; chúng được gắn với authorization/token record để Authorization Server có thể trả thông tin tương ứng trong introspection khi được phép. Không giả định Resource Server có thể tự decode opaque token bằng Base64.

### 4.3. Lợi ích và chi phí vận hành

| Đặc điểm | Opaque/reference |
|---|---|
| Hiển thị claims | Không thể đọc trực tiếp từ chuỗi token. |
| Kiểm tra trạng thái | Thường cần introspection hoặc lookup tin cậy. |
| Thu hồi | Authorization Server có thể đánh dấu token không active trong storage; hiệu lực phụ thuộc cache/introspection policy. |
| Phụ thuộc mạng | Resource Server có thể cần gọi AS, nên cần timeout, cache và xử lý AS unavailable. |
| Lộ metadata | Chuỗi token không phơi claims trực tiếp như JWT, nhưng bản thân token vẫn là Bearer credential cần giữ kín. |
| Khả năng mở rộng | Cần DB/storage và introspection capacity phù hợp với lưu lượng API. |

Opaque token không tự động an toàn hơn JWT trong mọi tình huống. Quyết định phụ thuộc yêu cầu thu hồi, latency, HA, độ nhạy cảm của claims và khả năng vận hành introspection.

## 5. OAuth2RefreshTokenGenerator: tạo refresh token

**OAuth2RefreshTokenGenerator** tạo **OAuth2RefreshToken** dùng để đổi access token mới trong những grant/client được phép sử dụng refresh token. Đây là token có vòng đời và chính sách riêng, không phải access token thứ hai.

Một số đặc điểm:

- Generator được gọi khi **OAuth2TokenContext.getTokenType()** là **refresh_token**.
- Token thường là giá trị opaque ngẫu nhiên; không phải JWT access token.
- Thời hạn được quản lý qua **TokenSettings.refreshTokenTimeToLive(...)**.
- Việc grant provider có yêu cầu refresh token hay không phụ thuộc grant, client registration và policy.
- **OAuth2RefreshTokenGenerator** không có **OAuth2TokenCustomizer** công khai giống **JwtGenerator** hoặc **OAuth2AccessTokenGenerator** trong API chuẩn.
- Refresh token phải được bảo vệ nghiêm ngặt, vì ai sở hữu nó có thể yêu cầu access token mới trong điều kiện hợp lệ.

### 5.1. Cấu hình TTL và rotation

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(14))
        .reuseRefreshTokens(false)
        .build();
~~~

- **accessTokenTimeToLive**: thời gian sống của access token.
- **refreshTokenTimeToLive**: thời gian sống của refresh token.
- **reuseRefreshTokens(true)**: cấu hình tái sử dụng refresh token theo hành vi mặc định được tài liệu mô tả.
- **reuseRefreshTokens(false)**: yêu cầu phát refresh token mới khi refresh thành công; cần kiểm tra token cũ bị vô hiệu hóa/không thể dùng lại trong flow của framework.

**Refresh token rotation không chỉ là thay chuỗi trong response.** Authorization Server phải lưu trạng thái refresh token mới, đánh dấu trạng thái cũ theo policy, bảo vệ chống replay và xử lý request đồng thời. Nếu custom generator tự tạo token nhưng không gắn vào **OAuth2Authorization**, lần refresh tiếp theo sẽ không tìm được token hợp lệ hoặc có thể tạo lỗ hổng replay.

### 5.2. Refresh token không có ở mọi grant

| Grant | Refresh token |
|---|---|
| Authorization Code | Có thể được cấp nếu client/grant/policy cho phép. |
| OIDC Authorization Code | Có thể được cấp theo policy tương tự; ID Token không thay refresh token. |
| Client Credentials | RFC 6749 mục 4.4.3 khuyến nghị **SHOULD NOT** cấp. |
| Device Authorization | Có thể được cấp theo cấu hình/policy của grant và client. |
| Refresh Token Grant | Dùng refresh token hiện có; có thể trả token mới khi rotation được bật. |

Không bật **refresh_token** cho client chỉ vì muốn kéo dài session. Với Client Credentials, client nên xin access token mới bằng chính credential client khi token hết hạn, theo khuyến nghị của RFC 6749.

### 5.3. Có nên tùy chỉnh refresh token thành JWT?

Không nên làm chỉ vì muốn “đồng nhất format”. Refresh token là credential dài hạn và cần khả năng kiểm tra trạng thái/rotation/revocation. JWT tự chứa có thể khó thu hồi tức thời nếu Resource Server/Authorization Server không tra trạng thái tập trung.

Nếu có yêu cầu định dạng refresh token riêng, cần triển khai **OAuth2TokenGenerator<OAuth2RefreshToken>** có kiểm soát và bảo đảm:

- Entropy đủ mạnh, chống đoán và collision.
- TTL, client association và principal/grant association chính xác.
- Persistence và invalidation/replay protection.
- Rotation nguyên tử khi nhiều request đồng thời.
- Không đưa claims nhạy cảm vào giá trị token hoặc logs.

Với đa số hệ thống, giữ **OAuth2RefreshTokenGenerator** mặc định và dùng **TokenSettings** để quản lý TTL/reuse là lựa chọn đơn giản, dễ kiểm chứng hơn.

## 6. DelegatingOAuth2TokenGenerator phối hợp các generator

**DelegatingOAuth2TokenGenerator** nhận một danh sách **OAuth2TokenGenerator**. Nó lần lượt gọi **generate(context)**; **token khác null đầu tiên được trả về**. Nếu tất cả đều trả **null**, kết quả là không có generator nào hỗ trợ context đó.

~~~java
OAuth2TokenGenerator<OAuth2Token> tokenGenerator =
        new DelegatingOAuth2TokenGenerator(
                jwtGenerator,
                accessTokenGenerator,
                refreshTokenGenerator);
~~~

Với cấu hình chuẩn, mỗi generator kiểm tra token type/format và chỉ xử lý loại mình hỗ trợ. Ví dụ:

| Context | JwtGenerator | OAuth2AccessTokenGenerator | OAuth2RefreshTokenGenerator |
|---|---|---|---|
| Access token SELF_CONTAINED | Tạo JWT | Không xử lý | Không xử lý |
| Access token REFERENCE | Không xử lý | Tạo opaque access token | Không xử lý |
| Refresh token | Không xử lý | Không xử lý | Tạo refresh token |
| OIDC ID Token | Tạo JWT ID Token | Không xử lý | Không xử lý |

Thứ tự đặc biệt quan trọng khi có custom generator có thể cùng xử lý một token type với generator khác. Generator custom cần trả **null** khi không hỗ trợ context và chỉ trả token khi đã đáp ứng đầy đủ policy. Đừng đặt generator bắt mọi token type lên đầu danh sách rồi trả một giá trị mặc định.

### 6.1. Cấu hình generator tường minh

Ví dụ dưới đây theo API Spring Authorization Server **1.5.x**. Giả định ứng dụng đã có **JWKSource<SecurityContext>** và các Bean persistence/security cần thiết.

~~~java
package com.example.authserver.config;

import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.DelegatingOAuth2TokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.JwtGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2AccessTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2RefreshTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenClaimsContext;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenGenerator;

@Configuration(proxyBeanMethods = false)
class TokenGeneratorConfiguration {

    @Bean
    OAuth2TokenGenerator<?> tokenGenerator(
            JWKSource<SecurityContext> jwkSource,
            OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer,
            OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueCustomizer) {

        JwtGenerator jwtGenerator =
                new JwtGenerator(new NimbusJwtEncoder(jwkSource));
        jwtGenerator.setJwtCustomizer(jwtCustomizer);

        OAuth2AccessTokenGenerator accessTokenGenerator =
                new OAuth2AccessTokenGenerator();
        accessTokenGenerator.setAccessTokenCustomizer(opaqueCustomizer);

        OAuth2RefreshTokenGenerator refreshTokenGenerator =
                new OAuth2RefreshTokenGenerator();

        return new DelegatingOAuth2TokenGenerator(
                jwtGenerator,
                accessTokenGenerator,
                refreshTokenGenerator);
    }
}
~~~

Cấu hình này tạo:
- JWT generator cho access token self-contained và OIDC ID Token.
- Opaque access token generator cho client có **REFERENCE** format.
- Refresh token generator cho grant/provider yêu cầu refresh token.

### 6.2. Gắn generator vào Authorization Server

Trong SecurityFilterChain của Authorization Server, cấu hình token generator:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        OAuth2TokenGenerator<?> tokenGenerator) throws Exception {

    var authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, configurer ->
                configurer.tokenGenerator(tokenGenerator))
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là khung cấu hình; ứng dụng hoàn chỉnh còn cần **AuthorizationServerSettings**, **RegisteredClientRepository**, **OAuth2AuthorizationService**, signing/JWK setup, login chain và các endpoint/feature thực tế. Nếu dùng API mới hơn thuộc dòng Spring Security tích hợp Authorization Server, kiểm tra lại cách tạo configurer và package theo dependency của dự án.

**Lưu ý về cấu hình mặc định:** **OAuth2TokenGenerator** là thành phần tùy chọn. Spring Authorization Server có thể tự cấu hình **DelegatingOAuth2TokenGenerator** gồm **OAuth2AccessTokenGenerator** và **OAuth2RefreshTokenGenerator**; khi có **JwtEncoder** hoặc **JWKSource<SecurityContext>**, **JwtGenerator** được thêm vào. Nếu đã khai báo custom generator bean hoặc gọi **tokenGenerator(...)** trên configurer, bạn chịu trách nhiệm bảo đảm đủ implementation cho mọi token type/format mà ứng dụng hỗ trợ.

## 7. Hai loại access-token customizer

### 7.1. JWT claims: OAuth2TokenCustomizer<JwtEncodingContext>

Dùng cho JWT được tạo bởi **JwtGenerator**. Context cho phép chỉnh **JwsHeader.Builder** và **JwtClaimsSet.Builder**. Nên giới hạn theo token type, grant và client:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtAccessTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && "inventory-worker".equals(
                        context.getRegisteredClient().getClientId())) {
            context.getClaims().claim("service_class", "inventory");
        }
    };
}
~~~

Nếu cùng customizer được dùng cho ID Token, điều kiện **ACCESS_TOKEN** giúp tránh thêm claim chỉ dành cho API vào ID Token của người dùng. Nếu cần tùy chỉnh ID Token, hãy kiểm tra token type OIDC tương ứng và yêu cầu OIDC Core riêng.

### 7.2. Opaque claims: OAuth2TokenCustomizer<OAuth2TokenClaimsContext>

Dùng cho **OAuth2AccessTokenGenerator**. Ví dụ:

~~~java
@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && "partner-api".equals(
                        context.getRegisteredClient().getClientId())) {
            context.getClaims().claim("integration_tier", "partner");
        }
    };
}
~~~

Các claims được lưu cùng token/authorization để introspection có thể cung cấp cho Resource Server theo chính sách. Client vẫn chỉ nhìn thấy opaque token; không thể decode để đọc **integration_tier**.

### 7.3. Không dùng nhầm customizer

| Nhu cầu | Dùng thành phần |
|---|---|
| Thêm claim/header vào JWT access token | **JwtGenerator.setJwtCustomizer(...)** |
| Thêm claim vào JWT ID Token | **JwtGenerator** + customizer kiểm tra ID Token context và OIDC rules. |
| Thêm claim vào opaque access token | **OAuth2AccessTokenGenerator.setAccessTokenCustomizer(...)** |
| Tạo refresh token mặc định | **OAuth2RefreshTokenGenerator**; quản lý TTL/reuse qua **TokenSettings**. |
| Đổi thời hạn access token | **TokenSettings.accessTokenTimeToLive(...)**. |
| Đổi thời hạn refresh token | **TokenSettings.refreshTokenTimeToLive(...)**. |
| Thay định dạng access token | **TokenSettings.accessTokenFormat(...)**. |
| Thay hoàn toàn format/thuật toán token | Custom **OAuth2TokenGenerator** có contract/persistence tương ứng. |

**OAuth2RefreshTokenGenerator** không có setter customizer claims tương đương hai access-token generator. Không cố dùng **JwtEncodingContext** để thêm claims vào refresh token opaque mặc định.

## 8. TokenSettings quyết định format và vòng đời

**TokenSettings** thuộc **RegisteredClient**, cho phép policy khác nhau theo client. Ví dụ:

~~~java
TokenSettings settings = TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(14))
        .reuseRefreshTokens(false)
        .build();

RegisteredClient client = RegisteredClient.withId("employee-portal-v1")
        .clientId("employee-portal")
        // Thêm client authentication, grant, redirect URI, scope...
        .tokenSettings(settings)
        .build();
~~~

Ý nghĩa:

- **SELF_CONTAINED**: access token là JWT; Resource Server xác minh chữ ký và claims.
- **REFERENCE**: access token opaque; Resource Server thường introspect.
- **accessTokenTimeToLive**: thời gian sống access token.
- **refreshTokenTimeToLive**: thời gian sống refresh token.
- **reuseRefreshTokens**: chọn tái sử dụng hoặc cấp refresh token mới khi refresh grant thành công.

Không dùng chung một TTL dài cho mọi client nếu mức độ rủi ro khác nhau. M2M, browser-facing client, đối tác và ứng dụng quản trị có thể cần token lifetime, format, audience và refresh policy khác nhau.

### 8.1. Access token và refresh token có vòng đời độc lập

Một access token có thể sống 5 phút trong khi refresh token sống 14 ngày. Khi access token hết hạn, client có thể dùng refresh token nếu grant và policy cho phép. Nếu refresh token bị thu hồi/hết hạn, client phải khởi tạo authorization lại theo grant thích hợp.

**Không nhầm thời hạn refresh token với thời gian sống của authorization** hoặc phiên đăng nhập người dùng. Việc refresh thành công cũng không nhất thiết kéo dài consent, session hoặc các quyền nghiệp vụ đã bị thu hồi.

## 9. Lưu trữ authorization và claims

Sau khi generator tạo token, grant provider đưa token vào **OAuth2Authorization** và lưu qua **OAuth2AuthorizationService**. Model authorization liên kết:

- Registered client ID nội bộ.
- Principal name (resource owner hoặc client).
- Grant type.
- Authorized scopes.
- Các token tương ứng và metadata, ví dụ issued/expiry/invalidated.
- Attributes liên quan grant, ví dụ authorization request hoặc principal.

Nếu token triển khai **ClaimAccessor** và có claims, chúng có thể được truy cập qua **OAuth2Authorization.Token.getClaims()**. Điều này hữu ích với opaque token/introspection và hỗ trợ audit/diagnostic có kiểm soát.

### 9.1. Vì sao không tự tạo token ngoài provider?

Nếu tự gọi **new OAuth2AccessToken(...)** trong controller rồi trả cho client:

- Token có thể không được lưu trong **OAuth2AuthorizationService**.
- Introspection/revocation không nhận diện token.
- Authorized scopes và principal có thể không khớp.
- Refresh token rotation không có trạng thái cũ/mới.
- JWT có thể không được ký bằng khóa/JWS algorithm đúng.
- Token response có thể trả token không tương thích với provider/Resource Server.

Luôn để grant provider gọi generator phù hợp và lưu authorization qua service. Nếu cần custom format, implement generator nhưng vẫn tích hợp với provider/persistence lifecycle chuẩn.

## 10. Bảo mật khi tùy chỉnh token generator

### 10.1. Claim hygiene và quyền tối thiểu

- Chỉ đưa vào token dữ liệu Resource Server thực sự cần.
- Không nhúng mật khẩu, secret, private key, refresh token, thông tin phiên hoặc PII không cần thiết.
- Tránh tên claim tùy ý trùng claim tiêu chuẩn hoặc claim do OIDC/JWT profile định nghĩa.
- Không để client tự cung cấp role/tenant claim mà chưa có nguồn dữ liệu được xác thực.
- Scope trong token phải phản ánh quyền thực tế được cấp; không nâng scope trong customizer.
- Phân biệt access token và ID Token; không đưa quyền API vào ID Token chỉ vì cùng được JwtGenerator tạo.

### 10.2. Ký JWT và quản lý khóa

- Dùng thuật toán JWS được hỗ trợ và policy rõ ràng.
- Quản lý private signing keys trong KMS/HSM/keystore khi phù hợp; giới hạn quyền đọc và audit.
- Công bố public keys qua JWKS và giữ khóa cũ trong thời gian token còn hiệu lực khi rotation.
- Resource Server xác minh signature, **iss**, **aud**, **exp** và claims theo profile.
- Không tin JWT chỉ vì decode được payload hoặc header ghi thuật toán mong muốn.

### 10.3. Opaque token và introspection

- Endpoint introspection phải yêu cầu client/resource server có quyền gọi.
- Bảo vệ token trong cache và không log request body chứa token.
- Cache **active** response theo TTL phù hợp với yêu cầu thu hồi; cache quá lâu có thể giữ quyền sau khi token đã bị revoke.
- Nếu Authorization Server không sẵn sàng, Resource Server cần fail-closed hoặc policy đã được phê duyệt; không mặc định coi token là active.
- Giữ nhất quán dữ liệu authorization khi chạy nhiều instance.

### 10.4. Refresh token rotation và replay

Khi **reuseRefreshTokens(false)**, phải kiểm thử:

- Refresh token cũ không tiếp tục dùng được sau khi đã rotate theo policy.
- Hai request đồng thời không cùng đổi một refresh token thành hai authorization state hợp lệ.
- Token mới gắn đúng client, principal, scope và authorization.
- Logout/revoke/disable client có tác động theo chính sách.
- Logs không chứa raw refresh token.

Không tự chế refresh token tuần tự hoặc lấy UUID không được bảo vệ làm token. Refresh token là credential dài hạn; cần entropy, storage và kiểm soát replay phù hợp.

## 11. Kiểm thử ba generator và Delegating

### 11.1. Ma trận token type/format

| Test | Kỳ vọng |
|---|---|
| Access token SELF_CONTAINED | **JwtGenerator** trả JWT có signature/claims hợp lệ. |
| Access token REFERENCE | **OAuth2AccessTokenGenerator** tạo opaque token; không thể đọc claims từ chuỗi token. |
| OIDC ID Token | **JwtGenerator** tạo ID Token đúng OIDC context. |
| Refresh token được grant cho phép | **OAuth2RefreshTokenGenerator** tạo refresh token có TTL theo policy. |
| Context không được generator hỗ trợ | Generator trả **null** để delegate tiếp tục. |
| Custom generator trả token | **DelegatingOAuth2TokenGenerator** dừng ở kết quả non-null đầu tiên. |
| Customizer JWT | Claim chỉ xuất hiện đúng client/grant/token type. |
| Customizer opaque | Claim lưu trong authorization và xuất hiện đúng trong introspection nếu policy cho phép. |
| Client Credentials | Không phát refresh token theo policy chuẩn của grant. |
| Refresh token rotation | Token mới được lưu, token cũ không được tái sử dụng theo policy. |

### 11.2. Kiểm thử format self-contained

Với JWT access token:

1. Lấy token từ Token Endpoint trong test environment.
2. Dùng **JwtDecoder** hoặc Resource Server test để xác minh signature.
3. Kiểm tra **iss**, **aud**, **exp**, **scope** và claim custom.
4. Thử sửa payload hoặc signature; token phải bị từ chối.
5. Thử token đúng chữ ký nhưng sai audience; Resource Server phải từ chối.

Không chỉ dùng Base64 decoder rồi so sánh JSON; đó không phải xác minh chữ ký.

### 11.3. Kiểm thử opaque token

Với **REFERENCE**:

1. Đăng ký client có **TokenSettings.accessTokenFormat(OAuth2TokenFormat.REFERENCE)**.
2. Xin token bằng grant hợp lệ.
3. Gửi token tới introspection endpoint bằng client được phép.
4. Xác nhận **active**, client, scope và claims phù hợp.
5. Revoke token/authorization, gọi introspection lại theo cache policy.
6. Xác nhận token không thể dùng sau khi server đánh dấu inactive (tính đến độ trễ cache được chấp nhận).

### 11.4. Kiểm thử refresh token

- Authorization Code/OIDC client được phép refresh nhận token theo policy.
- Client Credentials không được phát refresh token theo chính sách tiêu chuẩn.
- Token hết hạn hoặc bị revoke không được refresh.
- Với rotation, refresh token cũ không được dùng lại.
- Sai client authentication hoặc client ID không khớp bị từ chối.
- Scope sau refresh không được tự tăng vượt quyền đã được cấp.
- Lưu trữ authorization sau refresh phản ánh token mới và trạng thái cũ chính xác.

### 11.5. Ví dụ test nhỏ cho generator delegation

Đoạn dưới minh họa nguyên tắc first non-null, không thay thế test tích hợp framework:

~~~java
OAuth2TokenGenerator<OAuth2Token> delegate =
        new DelegatingOAuth2TokenGenerator(
                context -> null,
                context -> expectedToken);

OAuth2Token actual = delegate.generate(tokenContext);

assertThat(actual).isSameAs(expectedToken);
~~~

Trong test thực tế cần tạo **OAuth2TokenContext** và token fixture hợp lệ; ví dụ này chỉ kiểm chứng semantics của delegation. Các generator chuẩn phải được kiểm tra thêm theo token type, token format và grant.

## 12. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Client mong JWT nhưng nhận opaque | RegisteredClient dùng **REFERENCE** hoặc không có JwtGenerator trong delegate. | Kiểm **TokenSettings**, **JwtEncoder/JWK** và token generator config. |
| Client nhận JWT nhưng API không xác minh được | Sai key/JWKS, issuer, audience hoặc thuật toán. | Kiểm signing key, JWKS, validator và clock. |
| Custom claims không xuất hiện trong JWT | Chưa gắn **jwtCustomizer** vào JwtGenerator hoặc điều kiện token type/client không khớp. | Kiểm customizer bean và context. |
| Custom claims không xuất hiện trong opaque introspection | Customizer sai loại hoặc authorization không lưu claims. | Dùng **OAuth2TokenClaimsContext** và kiểm storage/introspection mapping. |
| OIDC ID Token mất claim | Customizer chỉ xử lý access token hoặc cấu hình generator thiếu JWT. | Kiểm OIDC context và **JwtGenerator**. |
| Refresh token không được cấp | Grant/client/provider không yêu cầu hoặc policy không cho phép. | Kiểm grant, client settings và loại authorization flow. |
| Refresh token cũ vẫn hoạt động sau rotation | Reuse policy, persistence hoặc invalidation không đúng. | Kiểm **reuseRefreshTokens** và trạng thái authorization. |
| Không có generator hỗ trợ context | Delegate thiếu generator cho format/type đó. | Bổ sung generator tương ứng, giữ đúng thứ tự và test null. |
| Custom generator làm hỏng grant khác | Generator bắt mọi context hoặc trả token sai type. | Trả null khi không hỗ trợ, giới hạn theo context. |
| Token bị Resource Server từ chối sau customizer | Claim tiêu chuẩn bị ghi đè hoặc audience/issuer không hợp lệ. | Chỉ thêm claim cần thiết, giữ claim protocol. |
| Token revoke nhưng API vẫn nhận | JWT validation offline hoặc introspection cache lâu. | TTL ngắn, introspection/cache policy hoặc revocation mechanism. |
| Claims nhạy cảm xuất hiện trong logs | Log toàn bộ context/token/authorization. | Redact, chỉ log metadata được duyệt và không log raw token. |

## 13. Bài tập thực hành

**Bối cảnh:** Authorization Server cấp token cho ba client:

- **inventory-worker** dùng Client Credentials, access token JWT, scope **inventory.read**.
- **partner-api** dùng Client Credentials, access token opaque, scope **orders.read**.
- **employee-portal** dùng Authorization Code + OIDC, cần ID Token và refresh token theo policy.

Yêu cầu:

1. Cấu hình **TokenSettings** cho từng RegisteredClient với access token format/TTL phù hợp.
2. Tạo **JwtGenerator** bằng **NimbusJwtEncoder** và JWK source đã quản lý.
3. Tạo **OAuth2AccessTokenGenerator** và **OAuth2RefreshTokenGenerator**.
4. Ghép chúng bằng **DelegatingOAuth2TokenGenerator**, đăng ký với **OAuth2AuthorizationServerConfigurer**.
5. Tạo **OAuth2TokenCustomizer<JwtEncodingContext>** chỉ thêm claim cho access token của **inventory-worker**.
6. Tạo **OAuth2TokenCustomizer<OAuth2TokenClaimsContext>** cho opaque access token của **partner-api**.
7. Xác nhận **JwtGenerator** vẫn tạo OIDC ID Token cho **employee-portal**.
8. Cấu hình **refreshTokenTimeToLive** và **reuseRefreshTokens(false)** cho client được phép refresh.
9. Kiểm thử introspection, JWT signature/audience, refresh rotation, revoke và request sai.
10. Kiểm tra logs/tracing không chứa token, secret, claims nhạy cảm hoặc private key.

**Tiêu chí hoàn thành:** Mỗi client nhận đúng định dạng token theo registration; JWT và opaque claims được tùy chỉnh ở đúng context; ID Token không bị ảnh hưởng; refresh token chỉ được cấp khi grant cho phép; authorization persistence, introspection và rotation hoạt động nhất quán.

## 14. Checklist trước khi triển khai

- [ ] Đã phân biệt token type với token format.
- [ ] **JwtGenerator** dùng **JwtEncoder**/JWK và tạo JWT cho đúng context.
- [ ] **OAuth2AccessTokenGenerator** chỉ được dùng cho access token reference/opaque.
- [ ] **OAuth2RefreshTokenGenerator** tạo refresh token theo grant/provider policy.
- [ ] **DelegatingOAuth2TokenGenerator** có đủ generator và thứ tự được kiểm thử.
- [ ] Customizer JWT và opaque dùng đúng context type.
- [ ] Claims được giới hạn theo client, grant, token type và nguồn dữ liệu tin cậy.
- [ ] Không ghi đè **iss**, **sub**, **aud**, **exp**, **iat**, **jti** hoặc scope trái policy.
- [ ] TokenSettings format/TTL/reuse phù hợp từng RegisteredClient.
- [ ] AuthorizationService lưu token/claims và trạng thái invalidation bền vững.
- [ ] Resource Server xác minh signature/issuer/audience hoặc introspection đúng policy.
- [ ] Refresh rotation có replay protection và concurrency test.
- [ ] Key rotation/JWKS, cache, revocation và multi-replica đã được xem xét.
- [ ] Logs/traces không chứa raw access token, refresh token, client secret hoặc private key.
- [ ] Đã kiểm thử JWT, opaque, OIDC ID Token, refresh token và các grant được hỗ trợ.

## Tổng kết

**JwtGenerator**, **OAuth2AccessTokenGenerator** và **OAuth2RefreshTokenGenerator** là ba implementation phục vụ các nhu cầu tạo token khác nhau trong Spring Authorization Server. **JwtGenerator** tạo JWT tự chứa cho access token/ID Token; **OAuth2AccessTokenGenerator** tạo opaque/reference access token; **OAuth2RefreshTokenGenerator** tạo refresh token. **DelegatingOAuth2TokenGenerator** phối hợp chúng bằng cách chọn generator đầu tiên trả kết quả khác null.

Chọn generator đúng phải đi cùng **TokenSettings**, customizer đúng loại context, **OAuth2AuthorizationService** và policy Resource Server. Không dùng customizer để nâng quyền, không tạo token ngoài grant provider và không coi việc ký JWT là thay thế introspection/thu hồi khi hệ thống cần trạng thái tập trung.

## Tài liệu tham khảo

1. [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): OAuth2TokenContext, OAuth2TokenGenerator, mặc định generator, token customizer và token claims.
2. [Spring Authorization Server 1.5.3 — JwtGenerator API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/token/JwtGenerator.html): tạo JWT access token/ID Token và setJwtCustomizer.
3. [Spring Authorization Server 1.5.3 — OAuth2AccessTokenGenerator API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/token/OAuth2AccessTokenGenerator.html): opaque access token và setAccessTokenCustomizer.
4. [Spring Authorization Server 1.5.3 — OAuth2RefreshTokenGenerator API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/token/OAuth2RefreshTokenGenerator.html): refresh token generation.
5. [Spring Authorization Server 1.5.8 — DelegatingOAuth2TokenGenerator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/DelegatingOAuth2TokenGenerator.html): delegation theo kết quả non-null đầu tiên.
6. [Spring Authorization Server 1.5.3 — OAuth2TokenGenerator API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenGenerator.html): interface tạo token từ context.
7. [Spring Authorization Server 1.5.3 — TokenSettings API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): access format, access/refresh TTL và refresh token reuse.
8. [Spring Authorization Server — Custom JWT Claims](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): ví dụ customizer JWT.
9. [Spring Authorization Server — Extension Authorization Grant](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): tích hợp token generator với grant provider tùy chỉnh.
10. [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims tiêu chuẩn.
11. [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile và validation JWT access token.
12. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): tra trạng thái opaque/reference token.
13. [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi access token và refresh token.

