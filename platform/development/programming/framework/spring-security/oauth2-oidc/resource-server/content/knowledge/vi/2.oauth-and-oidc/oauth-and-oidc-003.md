# Đối tượng nhận và mục đích sử dụng của từng loại token trong OAuth 2.0 và OpenID Connect

Trong hệ thống dùng **OAuth 2.0**, token giúp một ứng dụng được cấp quyền truy cập tài nguyên. Khi bổ sung **OpenID Connect (OIDC)**, ứng dụng còn có thể xác thực người dùng và nhận thông tin về phiên đăng nhập. Các token có thể cùng được trả về từ một Authorization Server, nhưng **không cùng đối tượng nhận, không cùng mục đích và không thể thay thế cho nhau**.

Ba loại cần phân biệt trước tiên:

- **Access token**: dành cho **Resource Server/API**, để quyết định có chấp nhận một yêu cầu truy cập tài nguyên hay không.
- **ID token**: dành cho **OIDC Client/Relying Party (RP)**, để xác nhận kết quả xác thực người dùng.
- **Refresh token**: dành cho **Authorization Server**, để client xin access token mới theo chính sách đã được cấp.

Điểm dễ nhầm: cả ba thường được **phát cho client** trong giao thức, nhưng **hệ thống sẽ nhận và xử lý chúng** là ba nơi khác nhau. “Ai cầm token?” và “Token dành cho ai?” là hai câu hỏi riêng.

## 1. Đặt token vào đúng vai trò của OAuth 2.0/OIDC

| Vai trò | Trách nhiệm | Quan hệ với token |
|---|---|---|
| **Resource Owner / End User** | Chủ thể sở hữu dữ liệu hoặc người dùng đăng nhập | Có thể là chủ thể (`sub`) của token, nhưng không mặc nhiên là người nhận token |
| **Client** | Web app, mobile app, backend hoặc service yêu cầu quyền truy cập | Nhận token từ Authorization Server và sử dụng chúng đúng mục đích |
| **Authorization Server (AS)** | Xác thực khi cần, cấp quyền và phát hành token | Phát hành access/refresh token; nhận refresh token tại token endpoint |
| **OpenID Provider (OP)** | Authorization Server hỗ trợ OIDC | Phát hành thêm ID token; cung cấp cơ chế nhận diện người dùng |
| **Resource Server (RS)** | API lưu trữ hoặc cung cấp tài nguyên được bảo vệ | Nhận, kiểm tra **access token** và áp dụng chính sách quyền |
| **Relying Party (RP)** | OIDC Client dựa vào kết quả xác thực từ OP | Nhận, kiểm tra **ID token** để thiết lập hoặc cập nhật phiên đăng nhập |

Một ứng dụng có thể đóng nhiều vai trò: backend vừa là **OIDC Client** khi xử lý đăng nhập, vừa là **Resource Server** khi cung cấp API. Phải phân biệt vai trò **theo từng request**; không suy luận rằng cùng một backend thì có thể dùng lẫn token.

### “Người nhận” có thể mang ba nghĩa

1. **Bên được cấp token**: thường là client đã xin token; client giữ và gửi token khi cần.
2. **Bên sử dụng token làm bằng chứng**: Resource Server dùng access token; RP dùng ID token; AS nhận refresh token.
3. **Đối tượng mà token mô tả**: thường là người dùng trong claim `sub`, hoặc một client/service trong một số luồng máy với máy.

Với JWT, claim `aud` (*audience*) thường giúp xác định bên mà token được phát hành để phục vụ. Claim `sub` (*subject*) nói token liên quan tới **ai**, không phải token phải được gửi **đến đâu**. Claim `iss` (*issuer*) nhận diện bên phát hành.

## 2. Bảng đối chiếu nhanh ba loại token

| Tiêu chí | Access token | ID token | Refresh token |
|---|---|---|---|
| Thuộc chuẩn | OAuth 2.0 | OIDC mở rộng OAuth 2.0 | OAuth 2.0 |
| Được phát cho | Client | OIDC Client / RP | Client được phép sử dụng refresh token |
| **Bên nhận để sử dụng** | **Resource Server/API** | **OIDC Client / RP** | **AS tại token endpoint** |
| Mục đích | Cấp quyền truy cập tài nguyên/API | Xác nhận kết quả xác thực và danh tính của người dùng với RP | Xin access token mới mà không cần thực hiện lại toàn bộ bước cấp quyền tương tác |
| Vị trí sử dụng thông thường | `Authorization: Bearer ...` khi gọi API | RP xử lý kết quả OIDC và thiết lập phiên đăng nhập | `grant_type=refresh_token` tại token endpoint |
| Định dạng | Có thể là JWT, opaque hoặc định dạng khác | **JWT** theo OIDC | Thường opaque, nhưng định dạng không bắt buộc |
| Nội dung cần chú ý | `aud`, quyền/phạm vi `scope`, hiệu lực, issuer, ràng buộc token | `iss`, `aud=client_id`, `sub`, `exp`, `iat`, `nonce` khi áp dụng | Ràng buộc với client/grant, hiệu lực, trạng thái thu hồi hoặc rotation theo AS |
| Thời hạn | Thường ngắn | Thường ngắn | Có thể dài hơn, có thể bị rotation hoặc thu hồi |
| Có gửi trực tiếp đến API nghiệp vụ? | **Có**, nếu API là đối tượng nhận phù hợp | **Không** | **Không** |
| Spring Security Resource Server xử lý? | **Có**: JWT validation hoặc opaque-token introspection | **Không dùng thay access token** | **Không** |

Thời hạn thực tế, định dạng và việc có phát hành refresh token hay không là **chính sách của nhà cung cấp danh tính**. Không nên suy luận từ tên token rằng nó luôn là JWT, luôn gắn với người dùng, hoặc chắc chắn được cấp trong mọi flow.

## 3. Access token: cấp quyền truy cập tài nguyên

### Ai nhận và dùng access token?

Authorization Server **cấp access token cho client**. Khi cần gọi API được bảo vệ, client đưa token vào request; **Resource Server** là bên nhận, xác minh token và xác định request có đủ quyền hay không.

Ví dụ ứng dụng `web-client` muốn đọc đơn hàng:

```http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer ACCESS_TOKEN
```

API `orders-api` cần xác nhận ít nhất:

- Token do **issuer đáng tin cậy** cấp và còn hiệu lực.
- Token **dành cho API này** (ví dụ `aud` chứa `orders-api`), khi hệ thống dùng audience.
- Token có **quyền thích hợp**, chẳng hạn `orders.read` để đọc đơn hàng.
- Nếu có ràng buộc người gửi (ví dụ DPoP hoặc mTLS), request đáp ứng đúng ràng buộc đó.
- Quy tắc nghiệp vụ vẫn cho phép truy cập **đơn hàng cụ thể**: có `orders.read` chưa có nghĩa là được đọc đơn hàng của mọi người dùng.

Access token mang ý nghĩa **ủy quyền truy cập**. Nó không tự chứng minh người dùng vừa đăng nhập tương tác. Trong flow `client_credentials`, token có thể đại diện cho một ứng dụng hoặc service mà **không có người dùng cuối**.

### Access token biểu diễn quyền gì?

Các trường thường xuất hiện, tùy Authorization Server và token profile:

| Trường | Ý nghĩa |
|---|---|
| `iss` | Ai phát hành token |
| `aud` | API/tài nguyên mà token dành cho |
| `sub` | Chủ thể liên quan; có thể là user hoặc client/service |
| `exp`, `nbf`, `iat` | Hết hạn, chưa có hiệu lực trước thời điểm, thời điểm phát hành |
| `scope` hoặc `scp` | Những phạm vi quyền được cấp |
| `client_id` hoặc claim tương đương | Client đã được cấp token, nếu profile/provider cung cấp |
| `jti` | Mã định danh token, khi được cung cấp |

**Scope không thay thế kiểm tra quyền trên từng tài nguyên.** Token có `orders.read` thường chỉ cho biết hành động được phép ở cấp API; ứng dụng vẫn phải kiểm tra người gọi có được xem `orderId=123` hay không.

### JWT access token và opaque access token

- **JWT access token**: Resource Server thường có thể kiểm tra chữ ký và các claim cục bộ bằng khóa công khai/JWKS của issuer. JWT gồm các phần được mã hóa Base64URL, **không mặc nhiên được mã hóa bí mật**. Không đưa dữ liệu nhạy cảm vào JWT chỉ vì có chữ ký.
- **Opaque access token**: Chuỗi token không thể được API giải nghĩa bằng cách tự decode. Resource Server thường hỏi Authorization Server qua **token introspection endpoint** hoặc cơ chế kiểm tra được triển khai riêng.
- **JWT là định dạng, access token là công dụng**. Một access token có thể là JWT hoặc opaque; nhìn thấy chuỗi ba phần giống JWT không đủ để quyết định mục đích của token.

Với bearer token, **ai chiếm được token còn hiệu lực có thể dùng token**, trong giới hạn quyền của nó. Vì vậy cần HTTPS, thời hạn phù hợp, hạn chế ghi log token và kiểm soát nơi lưu trữ. Cơ chế sender-constrained như DPoP/mTLS thay đổi điều kiện sử dụng token, nhưng phải được hỗ trợ đồng bộ bởi issuer, client và API.

## 4. ID token: xác nhận kết quả đăng nhập cho OIDC Client

### Ai nhận và dùng ID token?

ID token được **OpenID Provider phát hành cho OIDC Client/RP** khi thực hiện luồng OIDC phù hợp. RP kiểm tra token để biết OP đã xác thực chủ thể nào và những thông tin xác thực nào được khẳng định.

Ví dụ ứng dụng `web-client` đăng nhập qua OP:

1. Client khởi tạo yêu cầu OIDC, thông thường có scope `openid`.
2. OP xác thực người dùng và hoàn thành flow.
3. Client nhận ID token theo flow đã sử dụng và **tự kiểm tra ID token**.
4. Client tạo phiên đăng nhập của ứng dụng, có thể cần lấy thêm thông tin qua UserInfo endpoint.
5. Khi client gọi API nghiệp vụ, nó sử dụng **access token có audience phù hợp**, không lấy ID token để thay thế.

Một ID token ở dạng JWT có thể mang các claim:

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": "web-client",
  "exp": 1910000000,
  "iat": 1909996400,
  "nonce": "client-generated-nonce"
}
```

Ví dụ này chỉ minh họa cấu trúc, không phải token thật. Giá trị `aud` là `web-client` vì **ID token dành cho client đó**. Nó không phải một lời cấp quyền cho `orders-api`.

### RP phải kiểm tra gì?

Tùy OIDC flow và cách nhận token, RP cần áp dụng các kiểm tra của OIDC Core, gồm:

- Chữ ký/thuật toán phù hợp cấu hình OP và khóa tin cậy; các claim `iss`, `aud`, `exp`, `iat`.
- `aud` chứa **client_id** của RP; xử lý `azp` khi được yêu cầu bởi trường hợp nhiều audience.
- `nonce` khớp giá trị đã gửi khi yêu cầu OIDC có sử dụng nonce.
- Các claim bổ sung liên quan tới flow như `auth_time`, `at_hash`, `c_hash`, nếu điều kiện của flow yêu cầu.

`sub` giúp RP định danh chủ thể một cách ổn định **trong phạm vi issuer**, nhưng không nên dùng riêng `sub` thiếu `iss` làm khóa nhận diện liên nhà cung cấp. `name`, `email`, `picture` và những claim hồ sơ khác **không được bảo đảm luôn có** trong ID token.

### Vì sao ID token không được dùng để gọi API?

- **Sai đối tượng nhận:** ID token thường có `aud=client_id`, trong khi access token dành cho `aud` của API.
- **Sai mục đích:** ID token khẳng định xác thực, không mang hợp đồng ủy quyền truy cập API như access token.
- **Mở lỗ hổng confused deputy/token substitution:** API chấp nhận bất kỳ JWT hợp lệ của cùng issuer, mà không kiểm tra audience và loại token, có thể nhận nhầm ID token thành access token.

**Đăng nhập thành công** không đồng nghĩa **được quyền đọc/sửa mọi tài nguyên**. Nếu API cần biết người dùng là ai, Resource Server lấy danh tính từ **access token đã được xác thực** hoặc từ cơ chế tin cậy phù hợp, đồng thời tiếp tục kiểm tra quyền truy cập.

### ID token và UserInfo khác nhau thế nào?

Trong OIDC, UserInfo endpoint là tài nguyên được bảo vệ; client gọi nó bằng **access token thích hợp** để lấy các claim về người dùng theo scope và chính sách OP. ID token là bằng chứng xác thực được phát hành cho RP. Không mặc định ID token chứa đủ hồ sơ người dùng; cũng không mặc định access token luôn chứa các claim hồ sơ cần cho UI.

## 5. Refresh token: xin cấp lại access token

### Ai nhận và dùng refresh token?

Authorization Server **cấp refresh token cho client** nếu chính sách và flow cho phép. Khi access token hết hạn hoặc gần hết hạn, client gửi refresh token **trở lại token endpoint của Authorization Server**:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN
```

Endpoint và cách client xác thực phụ thuộc Authorization Server. Confidential client thường phải **xác thực client** theo phương thức đã đăng ký; public client không được dựa vào một client secret nhúng trong ứng dụng để coi là bí mật.

AS kiểm tra tính hợp lệ, client binding, trạng thái grant và chính sách trước khi phát hành access token mới. Phản hồi **có thể** chứa refresh token mới; nếu có **refresh-token rotation**, client phải thay token cũ bằng token mới và tuân theo quy tắc reuse detection của nhà cung cấp.

### Refresh token được dùng để làm gì, và không được dùng để làm gì?

- Dùng để **duy trì khả năng xin token truy cập mới** mà không yêu cầu người dùng lặp lại bước cấp quyền tương tác mỗi khi access token ngắn hạn hết hạn.
- **Không gửi refresh token đến Resource Server** và không đặt nó vào `Authorization: Bearer` khi gọi API nghiệp vụ.
- **Không dùng refresh token làm bằng chứng đăng nhập ở RP** và không coi nó là “access token sống lâu”.
- **Không phải flow nào cũng cấp refresh token**. Ví dụ `client_credentials` thường chỉ cần xin access token bằng thông tin xác thực client. Trong OIDC, `offline_access` liên quan tới yêu cầu truy cập khi người dùng không còn hiện diện, nhưng việc cấp refresh token vẫn phụ thuộc điều kiện và chính sách OP.

Vì refresh token có thể tạo ra nhiều access token, khả năng bị lộ thường có tác động lớn. Nên áp dụng lưu trữ an toàn theo loại client, bảo vệ phiên, rotation/revocation hoặc sender constraint khi phù hợp; không ghi token vào log hoặc URL. Với browser-based app, kiến trúc BFF/session cookie an toàn là một phương án giảm việc lộ token trong JavaScript; nếu public client trực tiếp giữ refresh token thì cần tuân theo yêu cầu bảo mật của AS và cơ chế rotation/binding được hỗ trợ.

## 6. Theo dõi toàn bộ luồng đăng nhập và gọi API

Ví dụ: người dùng đăng nhập vào `web-client`, sau đó client đọc đơn hàng từ `orders-api`. Luồng thông dụng là **Authorization Code + PKCE**:

```mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OIDC Client / RP
    participant AS as Authorization Server / OP
    participant API as Resource Server: orders-api

    U->>C: Yêu cầu đăng nhập
    C->>AS: Authorization request (openid, orders.read, PKCE)
    AS->>U: Xác thực và xin chấp thuận khi cần
    AS-->>C: Authorization code qua redirect
    C->>AS: Đổi code + code_verifier tại token endpoint
    AS-->>C: access_token + id_token (+ refresh_token nếu cấp)
    Note over C: Kiểm tra ID token; thiết lập phiên đăng nhập
    C->>API: GET /api/orders/123 với access_token
    Note over API: Kiểm tra token, audience và quyền truy cập
    API-->>C: Dữ liệu đơn hàng hoặc lỗi 401/403
    Note over C,AS: Khi cần, client gửi refresh_token tới AS
    C->>AS: grant_type=refresh_token
    AS-->>C: Access token mới (có thể có refresh token mới)
```

**Authorization code không phải access token.** Code là giá trị ngắn hạn để client đổi tại token endpoint; PKCE dùng `code_verifier` bảo vệ bước đổi code. Code không được đưa vào header `Authorization` để gọi API.

### Hai ví dụ JWT minh họa sự khác biệt `aud`

Access token (JWT nếu AS chọn định dạng JWT):

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1909996400,
  "exp": 1910000000
}
```

ID token, được cấp trong cùng luồng OIDC:

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1909996400,
  "exp": 1910000000,
  "nonce": "client-generated-nonce"
}
```

Cả hai cùng có thể chứa `iss`, `sub` và `exp`, nhưng **audience và chức năng khác hẳn nhau**. Các JSON trên là *payload minh họa*, không phải token đã ký và không dùng để thực hiện request thật. Refresh token, nếu được cấp, có thể chỉ là một chuỗi opaque không thể đọc claim.

### Không phải flow nào cũng có đủ ba token

| Tình huống | Token thường gặp | Điều cần hiểu |
|---|---|---|
| OAuth 2.0 truy cập API, không dùng OIDC | Access token; đôi khi refresh token | Không có yêu cầu bắt buộc phải phát hành ID token |
| Đăng nhập OIDC bằng Authorization Code + PKCE | Access token, ID token; refresh token tùy chính sách | RP dùng ID token cho đăng nhập; API nhận access token |
| Giao tiếp service-to-service với `client_credentials` | Access token | Không cần ID token xác nhận người dùng; thường không có refresh token |
| Client cần cấp lại quyền truy cập | Refresh token gửi tới AS, nhận access token mới | API vẫn chỉ nhận access token mới |

## 7. Áp dụng với Spring Security OAuth 2.0 Resource Server

Trong Spring Security, **Resource Server** là thành phần bảo vệ API và tiếp nhận **access token** từ request. Nó không thay thế chức năng của `oauth2Login()`/OIDC Client trong việc đăng nhập người dùng, cũng không dùng refresh token để tự gia hạn trên mỗi request đến API.

### Trường hợp A: API nhận JWT access token

Với Spring Boot và Spring Security hiện đại, thêm dependency `spring-boot-starter-oauth2-resource-server`. Ví dụ cấu hình issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/demo
```

Thiết lập `issuer-uri` cho phép Spring Security khám phá metadata/JWKS của issuer và xác thực JWT theo cấu hình. **Chỉ xác thực chữ ký, issuer và thời hạn chưa đủ để quyết định token đúng API**: cần bảo đảm audience mong đợi (hoặc cơ chế ràng buộc tài nguyên tương đương), sau đó kiểm tra quyền ứng dụng.

Ví dụ Java dưới đây minh họa kiểm tra cụ thể `aud=orders-api` và `scope=orders.read`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    private static final String ISSUER =
            "https://id.example.com/realms/demo";

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> defaultChecks =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> correctAudience = jwt ->
                jwt.getAudience().contains("orders-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Access token is not intended for orders-api",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaultChecks, correctAudience));
        return decoder;
    }
}
```

Ý nghĩa chính:

- `JwtDecoder` kiểm tra JWT đã ký và các điều kiện issuer/thời hạn thông qua validator được gắn vào decoder.
- Validator `correctAudience` từ chối JWT có `aud` không chứa `orders-api`; nhờ đó ID token có `aud=web-client` trong ví dụ không qua được cổng API.
- Spring Security thông thường ánh xạ scope từ claim `scope`/`scp` thành authority có tiền tố `SCOPE_`; `hasAuthority("SCOPE_orders.read")` kiểm tra quyền đọc ở tầng endpoint.
- Code trên minh họa **bảo vệ một HTTP endpoint**. Ứng dụng vẫn cần authorization ở tầng nghiệp vụ (ví dụ kiểm tra đơn hàng có thuộc người gọi không), và phải cấu hình những phương thức HTTP khác theo yêu cầu thực tế.

Các hệ thống khác nhau có thể dùng claim hoặc token profile riêng (ví dụ `typ=at+jwt`, `token_use=access`), nhưng **không giả định** những claim này luôn hiện diện ở mọi nhà cung cấp. Nếu nhà cung cấp chuẩn hóa dấu hiệu loại token, hãy kiểm tra thêm theo hợp đồng của họ.

> **Lưu ý vận hành:** Nếu ứng dụng đã khai báo bean `JwtDecoder` riêng, bean đó sẽ tham gia cấu hình thay cho mặc định của Spring Boot. Cần giữ đầy đủ các validator liên quan đến issuer, thời hạn và audience; không thay toàn bộ bằng một validator chỉ kiểm tra scope.

### Trường hợp B: API nhận opaque access token

Khi Authorization Server cấp token opaque, cấu hình Resource Server để introspect token theo giao thức và thông số của nhà cung cấp:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: YOUR_SECRET_FROM_SECURE_CONFIGURATION
```

API gửi token đến introspection endpoint bằng thông tin xác thực đã cấu hình. Authorization Server trả về trạng thái và metadata theo chính sách, điển hình có `active`. Resource Server dùng kết quả đó để quyết định tính hợp lệ và quyền; vẫn phải bảo đảm token **dành cho API này**, kiểm tra scope và kiểm tra quyền nghiệp vụ. Không gửi ID token hoặc refresh token qua đường gọi API chỉ vì introspection endpoint có thể trả lời về chúng.

### Phân biệt các vai trò Spring Security trong một ứng dụng

| Thành phần | Nó xử lý gì? | Token liên quan |
|---|---|---|
| `oauth2Login()` / OIDC Client | Đăng nhập qua OP và thiết lập authentication cho ứng dụng | **ID token** và cơ chế OIDC |
| OAuth2 Client support | Gọi API ở vai trò client, quản lý authorized client theo cấu hình | **Access token**, có thể dùng **refresh token** để lấy mới |
| `oauth2ResourceServer().jwt()` | Bảo vệ API nhận bearer JWT | **JWT access token** |
| `oauth2ResourceServer().opaqueToken()` | Bảo vệ API nhận opaque bearer token qua introspection | **Opaque access token** |

Một backend làm cả OIDC Client và Resource Server vẫn phải cấu hình ranh giới này đúng. Đừng gửi ID token được tạo cho giao diện web sang endpoint của API rồi coi như access token.

## 8. Các nhầm lẫn thường gây lỗi hoặc lỗ hổng

| Nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| “JWT nào ký đúng đều gọi được API” | ID token bị chấp nhận nhầm làm access token | Kiểm tra issuer, hiệu lực, **audience**, quyền và token profile khi áp dụng |
| “`sub` là người nhận token” | Không phân biệt user với API/client | `sub` là chủ thể; `aud` là đối tượng nhận dự kiến |
| “ID token có email/role nên dùng luôn để authorize API” | Dùng bằng chứng đăng nhập thay hợp đồng cấp quyền | API nhận **access token**, kiểm tra scope/role phù hợp và quyền nghiệp vụ |
| “Có access token là chứng minh user vừa đăng nhập” | Nhầm ủy quyền với xác thực tương tác | Phân biệt OAuth 2.0 với OIDC; xét flow và claims thực tế |
| “Refresh token gửi cùng mỗi request API cho tiện” | Tăng nguy cơ lộ thông tin có thể cấp token mới | Chỉ gửi refresh token đến **AS token endpoint** |
| “Access token luôn là JWT” | API cố decode opaque token, hoặc tin payload chưa xác minh | Cấu hình JWT validation hoặc introspection theo hợp đồng AS |
| “Có scope là thấy được mọi bản ghi” | Lộ dữ liệu của người dùng khác | Kết hợp kiểm tra scope với ownership, role, tenant và object-level authorization |
| “Đã có HTTPS thì có thể log token” | Token lọt vào log, telemetry hoặc hệ thống hỗ trợ | Không log nguyên token; hạn chế thu thập, lưu trữ và truyền token |

Đối với yêu cầu API, lỗi **401 Unauthorized** thường thể hiện thiếu/không hợp lệ thông tin xác thực, còn **403 Forbidden** thường thể hiện đã xác thực nhưng không đủ quyền. Phân loại thực tế phụ thuộc security chain và policy, nhưng cả hai đều không được “sửa” bằng cách đổi access token thành ID token.

## 9. Cách chọn token theo mục đích

Khi thiết kế endpoint hoặc đọc trace, có thể tự hỏi theo thứ tự:

1. **Đang gọi API để lấy/sửa tài nguyên?** Dùng **access token** được cấp cho API đó. Resource Server xác minh hiệu lực, audience, scope và quyền trên tài nguyên.
2. **Client đang xử lý đăng nhập OIDC?** Nhận và xác thực **ID token** được cấp cho chính `client_id` của nó; dùng kết quả để quản lý phiên đăng nhập.
3. **Client đang cần access token mới?** Dùng **refresh token** (nếu có) tại token endpoint của AS, kèm xác thực/ràng buộc client phù hợp.
4. **Đang nhận authorization code, DPoP proof, client assertion hay logout token?** Đây là những hiện vật giao thức có nhiệm vụ khác; không thay thế một trong ba token cốt lõi chỉ vì chúng cũng là chuỗi hoặc JWT.

Sơ đồ ghi nhớ:

```text
                Authorization Server / OpenID Provider
                    |          |             |
           access token    ID token     refresh token
                    |          |             |
             Client gửi   OIDC Client    Client gửi lại
                    |      xác thực      khi cần cấp mới
                    v          v             v
             Resource      Relying       Authorization
             Server/API     Party          Server
             (quyền)     (đăng nhập)     (token endpoint)
```

**Nguyên tắc cốt lõi:** token phải được đưa đến **đúng bên nhận** và được kiểm tra theo **đúng mục đích phát hành**. Trong Spring Security Resource Server, dữ liệu bảo vệ bằng bearer token chỉ nên được mở khi **access token dành cho API** vượt qua cả xác thực token lẫn chính sách phân quyền.

### Tài liệu chuẩn để tra cứu sâu hơn

- **RFC 6749 — OAuth 2.0 Authorization Framework**: access token, refresh token và các grant.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage**: cách trình bày bearer access token khi gọi tài nguyên.
- **OpenID Connect Core 1.0**: ID token, xác thực OIDC, claim, audience và quy tắc kiểm tra.
- **RFC 7662 — OAuth 2.0 Token Introspection**: cách kiểm tra metadata/trạng thái token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens**: profile access token dạng JWT khi hệ thống chọn áp dụng.
- **Tài liệu Spring Security — OAuth 2.0 Resource Server**: cơ chế bảo vệ API bằng JWT hoặc opaque token.
