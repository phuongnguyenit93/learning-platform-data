# Xác thực JWT bằng ReactiveJwtDecoder

RSocket có thể mang bearer token trong metadata của SETUP frame hoặc trong metadata của từng request. Spring Security cung cấp tích hợp JWT cho RSocket: lớp bảo mật đọc bearer authentication metadata, gọi authentication manager và dùng **ReactiveJwtDecoder** để xác minh token. Sau khi xác thực thành công, ứng dụng có thể dùng Principal cùng các authority được ánh xạ từ claims để phân quyền theo route.

ReactiveJwtDecoder là thành phần giải mã và xác minh JWT theo mô hình reactive. Nó kiểm tra chữ ký bằng khóa tin cậy, kiểm tra các claim thời gian và issuer theo validator đã cấu hình, rồi trả về một Mono chứa Jwt đã được xác minh. Spring Security kết nối decoder này với RSocket thông qua cấu hình RSocketSecurity và phần JWT authentication.

Bài học trình bày cách cấu hình decoder từ issuer hoặc JWK Set URI, gửi bearer token từ RSocketRequester, bảo vệ SETUP và request, phân quyền theo scope, bổ sung audience validation và kiểm thử các trường hợp token hợp lệ hoặc không hợp lệ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của ReactiveJwtDecoder trong xác thực JWT cho RSocket.
- Phân biệt giải mã token với xác minh chữ ký và xác thực danh tính.
- Tạo ReactiveJwtDecoder từ issuer URI hoặc JWK Set URI.
- Cấu hình Spring Security RSocket với JWT authentication.
- Gửi bearer token trong SETUP metadata hoặc metadata của từng request.
- Phân quyền theo route và authority được ánh xạ từ scope.
- Bổ sung kiểm tra audience và giới hạn thuật toán chữ ký.
- Xử lý token hết hạn, sai issuer, sai chữ ký và credential không hợp lệ.
- Kiểm thử decoder và RSocket security theo hướng reactive.

## 1. JWT trong RSocket

JWT (JSON Web Token) là một token có cấu trúc gồm header, payload và signature. Header mô tả loại token cùng thuật toán ký; payload chứa claims như issuer, subject, audience, thời hạn và scope; signature giúp bên nhận xác minh token được phát hành bởi khóa đáng tin cậy.

JWT thường được truyền dưới dạng chuỗi compact:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Payload JWT có thể đọc được nếu token chỉ được ký theo JWS. Chữ ký bảo vệ tính toàn vẹn và nguồn phát hành; nó không mã hóa nội dung. Không đặt mật khẩu, secret hoặc dữ liệu riêng tư không cần thiết trong claims.

RSocket dùng metadata extension để mang bearer token. Metadata này có thể xuất hiện trong:

- **SETUP frame**: xác thực connection ngay khi session được tạo.
- **Request payload**: xác thực theo từng interaction.

Spring Security hỗ trợ cả hai cách. Phía nhận sử dụng JWT authentication để kiểm tra token và tạo Authentication. Các quy tắc authorization sau đó quyết định request có được phép thực hiện hay không.

### 1.1. Các thành phần tham gia

| Thành phần | Trách nhiệm |
|---|---|
| Authorization Server / Identity Provider | Phát hành JWT và công bố khóa công khai qua JWK Set |
| RSocketRequester | Gửi bearer token trong metadata |
| Bearer authentication metadata | Đóng gói token theo RSocket authentication extension |
| RSocketSecurity | Cấu hình authentication và authorization cho RSocket |
| ReactiveJwtDecoder | Xác minh token và chuyển thành Jwt |
| ReactiveAuthenticationManager | Tạo Authentication từ credential đã xác minh |
| PayloadSocketAcceptorInterceptor | Kết nối Spring Security với RSocket protocol |
| Authorization rules | Kiểm tra authority, scope và route |

~~~mermaid
sequenceDiagram
    participant C as RSocket client
    participant S as RSocket server
    participant I as Spring Security
    participant D as ReactiveJwtDecoder
    participant A as Authorization Server
    C->>S: SETUP hoặc REQUEST + bearer metadata
    S->>I: AuthenticationPayloadInterceptor
    I->>D: decode(token)
    D->>A: Lấy JWK nếu chưa có khóa phù hợp
    A-->>D: JWK Set / public key
    D-->>I: Mono<Jwt> đã xác minh
    I->>I: Tạo Authentication và kiểm tra quyền
    I-->>S: Cho phép hoặc từ chối payload
    S-->>C: Xử lý interaction hoặc trả lỗi
~~~

## 2. ReactiveJwtDecoder làm gì?

ReactiveJwtDecoder nhận chuỗi JWT và trả về một publisher chứa Jwt:

~~~java
Mono<Jwt> decoded = jwtDecoder.decode(compactToken);
~~~

Việc decode không chỉ là tách ba phần của chuỗi token. Decoder còn xác minh chữ ký và áp dụng các validator đã cấu hình. Một token có cú pháp đúng nhưng chữ ký sai, hết hạn hoặc sai issuer vẫn phải bị từ chối.

Các bước thường có:

1. Đọc header và xác định thuật toán ký.
2. Tìm khóa phù hợp trong JWK Set hoặc khóa được cấu hình.
3. Xác minh signature.
4. Kiểm tra claim thời gian như exp và nbf.
5. Kiểm tra issuer (iss) theo validator.
6. Chạy các validator tùy chỉnh, ví dụ audience (aud).
7. Trả về Jwt đã xác minh hoặc phát lỗi xác thực.

ReactiveJwtDecoder trả về Mono nên có thể tham gia pipeline reactive mà không cần chặn thread bằng block(). Spring Security RSocket gọi decoder thông qua authentication manager; thông thường ứng dụng không cần tự gọi decode() trong từng handler.

### 2.1. ReactiveJwtDecoder và JwtDecoder

| API | Kết quả | Cách sử dụng |
|---|---|---|
| JwtDecoder | Jwt trực tiếp hoặc lỗi đồng bộ | Ứng dụng đồng bộ |
| ReactiveJwtDecoder | Mono<Jwt> | Ứng dụng reactive như WebFlux và RSocket |

RSocket server trong bài học sử dụng reactive pipeline. Dùng ReactiveJwtDecoder giúp việc lấy khóa, xác minh token và xử lý lỗi kết hợp được với Reactor mà không phải gọi API đồng bộ trên event loop.

### 2.2. Decoder không tự cấp quyền nghiệp vụ

Decoder trả về claims đã xác minh. Nó không tự quyết định người dùng được đọc thiết bị nào hoặc gọi route nào. Spring Security ánh xạ JWT thành Authentication và authority; authorization rules hoặc service nghiệp vụ mới kiểm tra quyền truy cập cụ thể.

Ví dụ:

- JWT hợp lệ có subject là user-42.
- Token có scope devices:read.
- User được xác thực thành công.
- Request đến route devices.status được phép nếu route yêu cầu SCOPE_devices:read.
- User vẫn cần được kiểm tra quyền truy cập thiết bị cụ thể theo tenant hoặc ownership trong service.

## 3. Chuẩn bị dependency

Với Gradle và Spring Boot dependency management:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-rsocket")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-security-oauth2-resource-server")
    implementation("org.springframework.security:spring-security-rsocket")
}
~~~

Các dependency có vai trò:

| Dependency | Vai trò |
|---|---|
| spring-boot-starter-rsocket | RSocket server/client và Spring Messaging integration |
| spring-boot-starter-security | Hạ tầng Spring Security |
| spring-boot-starter-security-oauth2-resource-server | JWT resource-server support và JOSE decoder trong Spring Boot 4 |
| spring-security-rsocket | Authentication và authorization cho RSocket payload |

Dùng Spring Boot BOM hoặc dependency management để đồng bộ version Spring Security, Spring Framework, Reactor và RSocket. Không ghim một version Spring Security khác với version mà Spring Boot quản lý nếu chưa kiểm tra tính tương thích.

Với Spring Boot 3, starter có tên spring-boot-starter-oauth2-resource-server. Từ Spring Boot 4, dùng tên mới spring-boot-starter-security-oauth2-resource-server; starter cũ được giữ lại trong giai đoạn chuyển tiếp nhưng đã deprecated.

## 4. Cấu hình ReactiveJwtDecoder từ issuer

Authorization Server công bố issuer URI trong claim iss của token và cung cấp metadata discovery endpoint để client tìm JWK Set URI. Spring Security có thể tạo decoder từ issuer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;

@Configuration
public class JwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return ReactiveJwtDecoders.fromIssuerLocation(
                "https://idp.example.com/issuer");
    }
}
~~~

ReactiveJwtDecoders.fromIssuerLocation thực hiện discovery để tìm JWK Set URI và tạo decoder với validator mặc định cho issuer. Khi token được xác minh, Spring Security cũng kiểm tra các claim thời gian như exp và nbf.

Issuer URI phải khớp với claim iss do Authorization Server phát hành. URL discovery phải được hỗ trợ bởi nhà cung cấp identity. Nếu issuer không chính xác hoặc metadata endpoint không truy cập được, việc lấy khóa và xác minh token sẽ thất bại.

### 4.1. Cấu hình qua application.yaml

Spring Boot có thể tự cấu hình ReactiveJwtDecoder từ issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
~~~

Khi có dependency phù hợp và chưa khai báo decoder riêng, Spring Boot có thể tạo ReactiveJwtDecoder mặc định. Khai báo bean riêng khi cần tùy chỉnh validator, JWK lookup hoặc thuật toán tin cậy.

### 4.2. Cấu hình bằng JWK Set URI

Nếu Authorization Server không cung cấp discovery endpoint hoặc ứng dụng cần chỉ định JWK Set URI trực tiếp, có thể tạo decoder bằng NimbusReactiveJwtDecoder:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.com/issuer";
    String jwkSetUri =
            "https://idp.example.com/.well-known/jwks.json";

    NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                    .withJwkSetUri(jwkSetUri)
                    .build();

    decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer));

    return decoder;
}
~~~

JWK Set URI cho decoder biết nơi lấy khóa công khai. Khi tự tạo decoder theo cách này, vẫn cần validator để kiểm tra issuer và các claim thời gian. Chỉ biết nơi lấy public key không có nghĩa token được phát hành bởi đúng issuer mà ứng dụng tin cậy.

## 5. Bổ sung audience validation

Claim aud xác định resource server hoặc nhóm resource mà token được phát hành cho. Một token có chữ ký hợp lệ và issuer đúng vẫn có thể không dành cho RSocket service hiện tại.

Spring Security không mặc định yêu cầu mọi ứng dụng phải có một audience cụ thể. Nếu kiến trúc cần giới hạn token cho API này, hãy thêm OAuth2TokenValidator:

~~~java
public final class AudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;
    private final OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Token không có audience dành cho RSocket API",
            null);

    public AudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

Kết hợp validator audience với validator mặc định:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.com/issuer";

    NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                    .withIssuerLocation(issuer)
                    .build();

    OAuth2TokenValidator<Jwt> validator =
            new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(issuer),
                    new AudienceValidator("rsocket-api"));

    decoder.setJwtValidator(validator);
    return decoder;
}
~~~

Trong ví dụ này, token phải vượt qua cả kiểm tra mặc định và audience validator. Nếu issuer phát hành token với nhiều audience, chỉ cần một giá trị trong danh sách khớp audience mà service yêu cầu.

Đây là cấu hình thay thế cho bean jwtDecoder đơn giản ở phần trước. Trong một ứng dụng, chỉ đăng ký một bean ReactiveJwtDecoder; không khai báo đồng thời nhiều bean cùng tên hoặc nhiều chính sách xác minh mâu thuẫn.

## 6. Cấu hình RSocket Security với JWT

RSocket Security sử dụng PayloadSocketAcceptorInterceptor để nối các interceptor bảo mật vào RSocket protocol. Với Spring Security, bật RSocket security và cấu hình JWT authentication:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;

@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                .setup().authenticated()
                .route("devices.status")
                    .hasAuthority("SCOPE_devices:read")
                .route("devices.events")
                    .hasAuthority("SCOPE_devices:read")
                .route("devices.command")
                    .hasAuthority("SCOPE_devices:write")
                .anyRequest().authenticated()
                .anyExchange().permitAll()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }
}
~~~

Phương thức jwt(Customizer.withDefaults()) cấu hình JWT authentication cho RSocket và sử dụng ReactiveJwtDecoder bean đã đăng ký. Khi nhận bearer authentication metadata, Spring Security giải mã token, xác thực token và tạo Authentication.

Các quy tắc authorization được xét theo thứ tự:

- setup().authenticated() yêu cầu xác thực khi thiết lập connection.
- route("devices.status") yêu cầu authority đọc thiết bị.
- route("devices.events") cũng yêu cầu authority đọc thiết bị.
- route("devices.command") yêu cầu authority ghi thiết bị.
- anyRequest().authenticated() yêu cầu xác thực cho request có metadata chưa được quy tắc trước đó khớp.
- anyExchange().permitAll() áp dụng cho payload tiếp theo không có metadata theo mô hình authorization của RSocket.

Nếu không muốn cho phép exchange không có metadata, hãy chọn quy tắc phù hợp với protocol và interaction của ứng dụng. Đừng sao chép anyExchange().permitAll() mà không hiểu nó áp dụng cho loại payload nào.

### 6.1. Khi chỉ xác thực theo từng request

Nếu connection được chia sẻ và client chỉ gửi token theo từng request, không bắt buộc setup phải được xác thực bằng JWT của người dùng. Có thể bỏ quy tắc setup().authenticated() và yêu cầu authentication ở các route:

~~~java
rsocket
    .authorizePayload(authorize -> authorize
        .route("devices.status")
            .hasAuthority("SCOPE_devices:read")
        .route("devices.command")
            .hasAuthority("SCOPE_devices:write")
        .anyRequest().authenticated()
        .anyExchange().permitAll()
    )
    .jwt(Customizer.withDefaults());
~~~

Khi đó, request nghiệp vụ phải mang bearer authentication metadata. Nếu muốn xác thực cả ứng dụng tại SETUP lẫn user cuối ở từng request, giữ setup().authenticated() và gửi credential ứng dụng trong SETUP, sau đó gửi JWT của user trong request. Hai lớp credential phục vụ hai danh tính khác nhau.

### 6.2. Spring Boot tự đăng ký security interceptor

Khi dùng Spring Boot cùng các dependency RSocket Security phù hợp, auto-configuration có thể đăng ký SecuritySocketAcceptorInterceptor vào RSocket server. Trong trường hợp này, bean PayloadSocketAcceptorInterceptor được cấu hình bởi RSocketSecurity sẽ được nối vào hạ tầng RSocket.

Nếu tự tạo RSocketServer ngoài Spring Boot auto-configuration, cần gắn SecuritySocketAcceptorInterceptor vào server bằng RSocketServer interceptor registry. Không chỉ tạo bean security rồi giả định raw RSocketServer tự sử dụng bean đó.

### 6.3. Phân biệt RSocket Security và WebFlux HTTP Security

SecurityWebFilterChain bảo vệ HTTP exchange của WebFlux. Nó không tự động thay thế PayloadSocketAcceptorInterceptor để bảo vệ RSocket payload. Một ứng dụng vừa có REST API vừa có RSocket endpoint có thể cần cả hai cấu hình:

| Lớp | Cơ chế |
|---|---|
| HTTP/REST | SecurityWebFilterChain và ServerHttpSecurity |
| RSocket | RSocketSecurity và PayloadSocketAcceptorInterceptor |

Có thể dùng chung issuer, JWK Set và ReactiveJwtDecoder nếu các endpoint có cùng chính sách xác minh token, nhưng authorization rules của HTTP và RSocket vẫn được cấu hình ở đúng lớp.

## 7. Gửi bearer token từ RSocketRequester

RSocket định nghĩa Bearer Token Authentication Metadata Extension. Spring Security dùng MIME type của authentication metadata extension để nhận token.

Ví dụ gửi token trong SETUP:

~~~java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

MimeType authenticationMimeType =
        MimeTypeUtils.parseMimeType(
                WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION
                        .getString());

BearerTokenMetadata token =
        new BearerTokenMetadata(accessToken);

Mono<RSocketRequester> requester =
        RSocketRequester.builder()
                .setupMetadata(token, authenticationMimeType)
                .connectTcp("localhost", 7000);
~~~

Token được gửi trong SETUP metadata. Sau khi connection được xác thực, các request trên connection có thể dùng Authentication gắn với session theo chính sách security.

Không dùng hằng BEARER_AUTHENTICATION_MIME_TYPE cũ của BearerTokenMetadata nếu nó đã deprecated trong version đang dùng. Hãy sử dụng MIME type chuẩn MESSAGE_RSOCKET_AUTHENTICATION và BearerTokenMetadata theo hướng dẫn của Spring Security.

### 7.1. Gửi token theo từng request

Nếu một connection được nhiều user chia sẻ, xác thực ở SETUP có thể chỉ xác định danh tính của ứng dụng hoặc gateway. Token người dùng cuối có thể được gửi trong từng request:

~~~java
public Mono<DeviceStatus> getStatus(
        RSocketRequester requester,
        String deviceId,
        String accessToken) {

    MimeType authenticationMimeType =
            MimeTypeUtils.parseMimeType(
                    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION
                            .getString());

    BearerTokenMetadata token =
            new BearerTokenMetadata(accessToken);

    return requester.route("devices.status")
            .metadata(token, authenticationMimeType)
            .data(new DeviceQuery(deviceId))
            .retrieveMono(DeviceStatus.class);
}
~~~

Spring Security xác thực token của request và áp dụng authorization dựa trên Authentication tương ứng. Đây là mô hình phù hợp khi connection thuộc một service trung gian nhưng request đại diện cho nhiều người dùng.

### 7.2. Chọn SETUP hay request-time authentication

| Tình huống | Cách phù hợp |
|---|---|
| Một người dùng sở hữu connection riêng | Token tại SETUP thường phù hợp |
| Một gateway dùng connection chung cho nhiều user | Token theo từng request |
| Cần xác thực ứng dụng ở SETUP và user ở request | Kết hợp cả hai |
| Token cần thay đổi thường xuyên | Cân nhắc request-time auth hoặc tái tạo connection |

Token tại SETUP không tự được thay thế khi access token được refresh ở client. Nếu connection sống lâu hơn token, hãy thiết kế thời gian sống connection, reconnect hoặc xác thực từng request phù hợp.

## 8. Scope và authority trong JWT

JWT từ OAuth 2.0 Authorization Server thường có claim scope hoặc scp. Spring Security ánh xạ scope thành GrantedAuthority với tiền tố SCOPE_.

Ví dụ payload JWT:

~~~json
{
  "iss": "https://idp.example.com/issuer",
  "sub": "user-42",
  "aud": ["rsocket-api"],
  "scope": "devices:read devices:write",
  "iat": 1790000000,
  "exp": 1790003600
}
~~~

Authorities tương ứng:

~~~text
SCOPE_devices:read
SCOPE_devices:write
~~~

Do đó, rule:

~~~java
.route("devices.status")
    .hasAuthority("SCOPE_devices:read")
~~~

sẽ yêu cầu token có scope devices:read. Nếu Authorization Server dùng claim roles hoặc permissions riêng, cần cấu hình converter để ánh xạ claim đó thành GrantedAuthority; không giả định mọi claim đều tự động trở thành authority.

### 8.1. Authentication không thay thế kiểm tra quyền dữ liệu

Route authorization xác định người dùng có được gọi chức năng hay không. Nó không nhất thiết chứng minh người dùng có quyền trên từng resource ID.

Ví dụ, scope devices:read cho phép gọi chức năng đọc thiết bị, nhưng service vẫn cần kiểm tra thiết bị có thuộc tenant hoặc phạm vi được cấp cho Principal hay không:

~~~java
@MessageMapping("devices.status")
public Mono<DeviceStatus> status(
        DeviceQuery query,
        Principal principal) {

    return deviceService.findVisibleTo(
            principal.getName(),
            query.deviceId());
}
~~~

Không lấy tenant ID do client tự khai trong payload làm điều kiện duy nhất để truy vấn dữ liệu. Dùng Principal đã xác thực và chính sách phân quyền ở service.

## 9. Các bước xác minh JWT

Một JWT hợp lệ cần thỏa các điều kiện phù hợp với chính sách của resource server:

| Thành phần | Kiểm tra |
|---|---|
| Signature | Chữ ký khớp với public key đáng tin cậy |
| Algorithm | Thuộc danh sách thuật toán được chấp nhận |
| Issuer (iss) | Đúng Authorization Server đã cấu hình |
| Expiration (exp) | Token chưa hết hạn |
| Not Before (nbf) | Token đã đến thời điểm được phép sử dụng |
| Audience (aud) | Token được phát hành cho RSocket API nếu chính sách yêu cầu |
| Claims | Các claim bắt buộc có kiểu và giá trị hợp lệ |

ReactiveJwtDecoders.fromIssuerLocation tạo decoder với các validator mặc định cho issuer và timestamp. Nếu cần audience hoặc quy tắc riêng, thêm OAuth2TokenValidator. Đừng chỉ decode payload Base64 rồi tin claims mà không xác minh chữ ký.

### 9.1. Thuật toán ký

NimbusReactiveJwtDecoder mặc định tin cậy RS256. Nếu Identity Provider dùng thuật toán khác, cấu hình rõ thuật toán được phép:

~~~java
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
                .withIssuerLocation(issuer)
                .jwsAlgorithm(SignatureAlgorithm.RS512)
                .build();

decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer));
~~~

Chỉ thêm thuật toán đã được thống nhất với Authorization Server. Không chọn thuật toán dựa trên giá trị không đáng tin cậy do token tự khai mà không có allowlist.

### 9.2. Clock skew

Các máy có thể lệch đồng hồ một khoảng nhỏ. Timestamp validator có thể được cấu hình clock skew phù hợp với hạ tầng. Khi thay validator mặc định, hãy kết hợp lại timestamp validator với issuer validator:

~~~java
OAuth2TokenValidator<Jwt> validator =
        new DelegatingOAuth2TokenValidator<>(
                new JwtTimestampValidator(Duration.ofSeconds(60)),
                new JwtIssuerValidator(issuer));

decoder.setJwtValidator(validator);
~~~

Đoạn mã này giả định decoder là NimbusReactiveJwtDecoder và biến issuer đã được cấu hình. Không vô tình bỏ kiểm tra exp, nbf hoặc iss khi thêm validator tùy chỉnh.

## 10. Xử lý lỗi xác thực

Một số lỗi phổ biến:

| Lỗi | Nguyên nhân thường gặp | Kết quả |
|---|---|---|
| Invalid signature | Token ký bằng khóa không được tin cậy hoặc bị sửa | Authentication thất bại |
| Expired token | exp đã qua | Token bị từ chối |
| Not yet valid | nbf nằm trong tương lai | Token bị từ chối |
| Invalid issuer | iss không khớp cấu hình | Token bị từ chối |
| Invalid audience | aud không chứa resource server yêu cầu | Token bị từ chối nếu có validator |
| Unsupported algorithm | Thuật toán không thuộc allowlist | Token bị từ chối |
| JWK unavailable | Không lấy được khóa từ JWK endpoint | Xác minh có thể thất bại |
| Missing bearer metadata | Request cần auth nhưng không có credential | Authorization thất bại |

Nếu xác thực tại SETUP thất bại, connection mới có thể bị từ chối trước khi ứng dụng gửi request nghiệp vụ. Nếu xác thực theo request thất bại, interaction đó bị từ chối; cách xử lý connection tiếp tục hay kết thúc phụ thuộc loại lỗi và chính sách của server.

Không trả token, chữ ký hoặc chi tiết nội bộ của decoder cho client. Log mã lỗi an toàn, route và correlation ID; không log toàn bộ bearer metadata.

## 11. Quản lý JWK và vòng đời token

JWK Set thường chứa nhiều public key với kid (key ID) để hỗ trợ xoay vòng khóa. Decoder chọn khóa tương ứng với header JWT và có thể tải lại JWK Set khi Authorization Server thay đổi khóa.

Các nguyên tắc vận hành:

- Dùng HTTPS cho issuer metadata và JWK Set URI.
- Giữ issuer URI chính xác và ổn định.
- Cho phép key rotation theo cơ chế JWK.
- Theo dõi lỗi truy cập JWK endpoint.
- Không cache JWK vô thời hạn nếu thư viện cung cấp chính sách cache có thể cấu hình.
- Cấu hình timeout và network egress để decoder có thể truy cập identity provider.

JWT thường là token tự chứa. Nếu token bị thu hồi trước exp, resource server không nhất thiết biết ngay trừ khi có cơ chế revocation/introspection hoặc trạng thái bổ sung. Có thể dùng token lifetime ngắn, xác thực lại theo request hoặc đóng các connection đã xác thực bằng token bị thu hồi.

## 12. Bảo vệ transport và credential

Bearer token là credential dạng bearer: bất kỳ bên nào có token đều có thể thử sử dụng nó trong phạm vi token cho phép. Vì vậy:

1. Dùng TLS cho RSocket TCP hoặc WSS cho WebSocket trên mạng không tin cậy.
2. Không đưa token vào URL, route hoặc log.
3. Không gửi token qua connection plaintext.
4. Giới hạn audience và scope theo service.
5. Đặt thời hạn token phù hợp và refresh theo chính sách.
6. Không lưu access token trong log, metric label hoặc exception message.
7. Giới hạn quyền của service account và token machine-to-machine.

TLS bảo vệ token trên đường truyền. JWT signature bảo vệ tính toàn vẹn và nguồn phát hành. Hai cơ chế giải quyết hai lớp rủi ro khác nhau và nên được dùng cùng nhau.

## 13. Kiểm thử ReactiveJwtDecoder

Có thể kiểm thử decoder độc lập bằng StepVerifier:

~~~java
StepVerifier.create(jwtDecoder.decode(validToken))
        .assertNext(jwt -> {
            assertThat(jwt.getSubject()).isEqualTo("user-42");
            assertThat(jwt.getAudience()).contains("rsocket-api");
        })
        .verifyComplete();
~~~

Với token không hợp lệ:

~~~java
StepVerifier.create(jwtDecoder.decode(expiredToken))
        .expectError()
        .verify();
~~~

Trong unit test, dùng khóa test và JWK endpoint giả lập hoặc decoder được cấu hình bằng public key test. Không phụ thuộc Authorization Server production trong mỗi lần chạy test.

### 13.1. Kiểm thử RSocket security end-to-end

Một integration test nên:

1. Khởi động RSocket server cùng RSocketSecurityConfiguration.
2. Cấu hình ReactiveJwtDecoder dùng khóa test.
3. Tạo RSocketRequester gửi bearer metadata trong SETUP.
4. Gọi route được phép với scope tương ứng.
5. Gọi route cần scope khác và xác minh bị từ chối.
6. Gửi token hết hạn hoặc chữ ký sai và xác minh authentication thất bại.
7. Kiểm tra request-time authentication nếu server dùng connection chung.
8. Xác minh token không xuất hiện trong log.

Ví dụ client setup:

~~~java
Mono<RSocketRequester> requester =
        RSocketRequester.builder()
                .setupMetadata(
                        new BearerTokenMetadata(validToken),
                        authenticationMimeType)
                .connectTcp("localhost", 7000);
~~~

Sau khi kết nối, gửi request:

~~~java
requester.flatMap(req ->
        req.route("devices.status")
                .data(new DeviceQuery("sensor-17"))
                .retrieveMono(DeviceStatus.class));
~~~

Nếu token được gửi ở SETUP, request sau đó dùng Authentication của connection theo cấu hình. Nếu token được gửi theo từng request, thêm metadata authentication vào request builder tương ứng.

## 14. Những lỗi thường gặp

### Chỉ parse JWT mà không xác minh chữ ký

Base64 decode payload không chứng minh token đáng tin cậy. Dùng ReactiveJwtDecoder và JWK/public key được cấu hình.

### Dùng JwtDecoder đồng bộ trong reactive flow

Việc block để xác minh token có thể chặn event loop. Dùng ReactiveJwtDecoder và để Spring Security quản lý pipeline.

### Cấu hình issuer không khớp claim iss

Issuer URI phải khớp giá trị token và metadata của Authorization Server. Sai issuer làm mọi token bị từ chối.

### Chỉ cấu hình JWK Set URI mà quên issuer validator

JWK Set URI cung cấp khóa. Khi tự tạo decoder, vẫn phải cấu hình validator issuer và timestamp.

### Không kiểm tra audience

Token có thể hợp lệ nhưng được phát hành cho API khác. Thêm audience validator nếu service cần ràng buộc aud.

### Dùng scope sai tiền tố

Spring ánh xạ scope thành authority có tiền tố SCOPE_. Rule cần dùng đúng tên authority, ví dụ SCOPE_devices:read.

### Chỉ cấu hình SecurityWebFilterChain

HTTP security không tự bảo vệ RSocket payload. Cần bật RSocket Security và gắn PayloadSocketAcceptorInterceptor.

### Gửi token trong SETUP nhưng kỳ vọng token tự refresh

SETUP chỉ được gửi khi session bắt đầu. Khi token thay đổi, cần reconnect hoặc xác thực theo request tùy kiến trúc.

### Tin claims để truy cập mọi resource

JWT xác minh danh tính và claims. Service vẫn phải kiểm tra ownership, tenant và quyền trên resource cụ thể.

## 15. Checklist triển khai

Trước khi đưa JWT authentication vào RSocket production, hãy xác nhận:

1. Có dependency RSocket, Spring Security và OAuth2 Resource Server/JOSE phù hợp.
2. ReactiveJwtDecoder được tạo từ issuer hoặc JWK Set URI tin cậy.
3. Issuer validator và timestamp validator được giữ đầy đủ.
4. Audience được kiểm tra nếu service yêu cầu.
5. Danh sách thuật toán ký được giới hạn rõ ràng.
6. RSocketSecurity bật JWT authentication bằng .jwt(...).
7. PayloadSocketAcceptorInterceptor được gắn vào RSocket server.
8. SETUP hoặc request metadata gửi bearer token theo đúng mô hình.
9. Authorization rules kiểm tra scope/authority theo route.
10. Service kiểm tra quyền truy cập resource và tenant cụ thể.
11. Token được bảo vệ bằng TLS/WSS và không xuất hiện trong log.
12. Token expiry, refresh, revocation và JWK rotation có chính sách rõ ràng.
13. Kiểm thử token hợp lệ, hết hạn, sai issuer, sai signature và sai audience.
14. Kiểm thử cả authentication ở SETUP và request-time nếu ứng dụng hỗ trợ hai cách.

## 16. Tổng kết

ReactiveJwtDecoder là thành phần reactive dùng để xác minh JWT và chuyển token thành Jwt đã được kiểm tra. Trong RSocket, Spring Security kết nối decoder với bearer authentication metadata thông qua RSocketSecurity và PayloadSocketAcceptorInterceptor. Token có thể được gửi trong SETUP để xác thực connection hoặc trong từng request khi một connection được nhiều người dùng chia sẻ.

Một cấu hình đáng tin cậy cần xác minh chữ ký bằng khóa JWK phù hợp, kiểm tra issuer và thời hạn, bổ sung audience validator khi cần, giới hạn thuật toán ký và ánh xạ scope thành authority. Sau authentication, authorization rules bảo vệ route còn service kiểm tra quyền trên từng resource. Kết hợp decoder reactive, bearer metadata, TLS và kiểm thử end-to-end giúp RSocket xác thực JWT mà vẫn giữ pipeline bất đồng bộ.

## Tài liệu tham khảo

- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [ReactiveJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
