# Thiết lập audience và chứng minh API từ chối token dành cho nơi khác

## 1. Vì sao Resource Server phải kiểm tra audience?

Một JWT có thể có chữ ký hợp lệ, được phát hành bởi Authorization Server (AS) đáng tin cậy và vẫn không được phép dùng để gọi API hiện tại.

Giả sử một hệ thống có hai APIs:

- **orders-api** xử lý đơn hàng.
- **billing-api** xử lý thanh toán.

Cả hai APIs dùng cùng issuer và cùng bộ signing keys. AS phát hành token cho billing:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "orders.read billing.pay",
  "iat": 1794729600,
  "exp": 1794730500
}
~~~

Giả sử token có chữ ký hợp lệ và scope chứa orders.read. Nếu orders-api chỉ kiểm tra chữ ký, issuer, thời hạn và scope mà bỏ qua audience, nó có thể nhận token được phát hành cho billing-api.

Đây là lỗi **token substitution / cross-resource token acceptance**: credential được cấp cho resource server A bị dùng tại resource server B.

**Audience validation trả lời câu hỏi: access token này được phát hành cho resource server nào?**

Đối với orders-api, policy có thể yêu cầu:

~~~text
iss == https://auth.example.com/
AND aud contains orders-api
AND signature is valid
AND token is within its validity window
AND required scope is present
~~~

Các điều kiện này có vai trò khác nhau:
- **iss** xác định nhà phát hành.
- **aud** xác định recipient/resource được phép nhận token.
- **exp/nbf** giới hạn thời gian sử dụng.
- **scope/authorities** mô tả quyền được cấp.
- **signature** bảo vệ tính toàn vẹn và nguồn phát hành claims.

Không điều kiện nào thay thế điều kiện còn lại.

## 2. Audience trong JWT có nghĩa gì?

JWT Registered Claim **aud** xác định những recipient mà JWT được dự định gửi tới. Giá trị có thể là một string hoặc một array các strings.

Dạng một audience:

~~~json
{
  "aud": "orders-api"
}
~~~

Dạng nhiều audiences:

~~~json
{
  "aud": ["orders-api", "reporting-api"]
}
~~~

Theo JWT specification, recipient phải nhận diện chính nó trong audience claim khi claim này hiện diện. Với access token profile dành cho OAuth 2.0, API nên yêu cầu audience theo contract của access-token issuer; RFC 9068 định nghĩa profile JWT access token có audience.

Một Resource Server thường có một expected audience identifier:

~~~text
Expected audience for this API = orders-api
~~~

Nếu token có aud là billing-api, orders-api phải từ chối, kể cả khi token:
- Có chữ ký hợp lệ.
- Được ký bằng key của issuer mà orders-api tin.
- Chưa hết hạn.
- Có scope tên giống scope của orders-api.
- Có subject là một user hợp lệ.

### Audience identifier có thể là URI hoặc tên resource

Ví dụ:

~~~json
{
  "aud": ["https://api.example.com/orders"]
}
~~~

Hoặc:

~~~json
{
  "aud": ["urn:shop:orders-api"]
}
~~~

Giá trị cần thống nhất giữa AS và RS. Nếu issuer phát hành orders-api nhưng RS cấu hình https://api.example.com/orders, hai giá trị không tự tương đương.

Không tự chuẩn hóa bằng cách bỏ trailing slash, đổi chữ hoa/thường hoặc so sánh URL theo quy tắc tùy ý. Audience matching phải theo identifier contract mà AS và API đã thống nhất.

## 3. Audience khác issuer, client_id, azp và scope

Các claims sau thường bị nhầm:

| Claim | Ý nghĩa | Câu hỏi được trả lời |
|---|---|---|
| **iss** | Issuer | Ai phát hành token? |
| **aud** | Audience/recipient | Token dành cho resource server nào? |
| **sub** | Subject | Token đại diện subject nào? |
| **client_id** | OAuth client | Client nào yêu cầu/có liên quan tới token? |
| **azp** | Authorized party trong OIDC context | Client nào được phép sử dụng ID token trong ngữ cảnh đó? |
| **scope** | Granted permissions | Token được cấp quyền gì? |
| **exp** | Expiration | Token hết hạn khi nào? |

Một client web có thể gọi nhiều APIs:

~~~text
shop-web
   |
   +---- access token for orders-api
   |
   +---- access token for billing-api
   |
   +---- access token for inventory-api
~~~

Client ID giống nhau không có nghĩa các access tokens có cùng audience.

Ví dụ:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "client_id": "shop-web",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Token này dành cho orders-api. client_id=shop-web không làm nó trở thành token dùng được cho mọi API mà shop-web có thể gọi.

### Scope không thay audience

Giả sử token có:

~~~json
{
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Scope orders.read không biến billing token thành orders token. Audience vẫn sai nên orders-api phải từ chối trước khi xét authorization theo scope.

### azp không thay aud

Trong OIDC ID Token, azp có thể nhận diện authorized party. Resource Server không được dùng azp hoặc client_id thay cho aud khi kiểm tra recipient của access token.

## 4. Luồng kiểm tra audience ở Resource Server

~~~mermaid
flowchart TD
    A["HTTP request with Bearer JWT"] --> B["Parse JWT"]
    B --> C["Select trusted verification key"]
    C --> D{"Signature valid?"}
    D -->|No| X["Reject: 401 invalid_token"]
    D -->|Yes| E["Validate issuer"]
    E --> F{"Expected issuer?"}
    F -->|No| X
    F -->|Yes| G["Validate timestamps and token profile"]
    G --> H{"Audience contains this API?"}
    H -->|No| X
    H -->|Yes| I["Create authenticated principal"]
    I --> J["Check scope and domain permissions"]
    J --> K{"Authorized?"}
    K -->|No| Y["Reject: 403"]
    K -->|Yes| L["Invoke API"]
~~~

Audience validation là một phần của **authentication/token validation**. Token dành cho API khác không phải principal đã authenticated nhưng thiếu scope; nó không hợp lệ cho resource server hiện tại.

Một số implementation có thể chạy validators theo thứ tự khác nhau hoặc gom lỗi vào một kết quả chung. Điều quan trọng là tất cả required validations phải thành công trước khi Resource Server tạo Authentication.

## 5. Cấu hình audience tại Authorization Server

Resource Server chỉ có thể kiểm tra audience đúng nếu AS phát hành access token với audience contract rõ ràng.

Một token endpoint có thể cấp token cho orders-api:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_CREDENTIALS

grant_type=client_credentials&scope=orders.read&resource=orders-api
~~~

resource ở đây là ví dụ về cách client biểu thị resource theo AS hỗ trợ. OAuth 2.0 Resource Indicators được chuẩn hóa trong RFC 8707; không phải mọi AS đều hỗ trợ cùng một request parameter hoặc cùng cách map nó thành aud.

AS có thể:
- Xác định audience dựa trên resource indicator.
- Dùng client registration/resource mapping.
- Dùng audience mapper hoặc token customization.
- Phát hành token riêng cho từng API.
- Áp dụng policy theo grant, client, user và requested resource.

Điều quan trọng là client không được tự sửa claim aud sau khi token đã ký. Audience là claim do AS phát hành và được bảo vệ bởi chữ ký.

### Không mặc định client tự chọn được mọi audience

Nếu AS cho client gửi resource=orders-api, AS vẫn phải kiểm tra client/grant có được phép xin token cho resource đó hay không. Resource indicator là request input, không phải quyền tự cấp.

### Tránh phát một token dùng cho tất cả APIs

Một token có:

~~~json
{
  "aud": [
    "orders-api",
    "billing-api",
    "inventory-api",
    "admin-api"
  ]
}
~~~

có thể hợp lệ theo JWT semantics nếu các recipients được chủ ý chỉ định. Nhưng token dùng chung nhiều resource làm tăng phạm vi tác động khi token bị lộ và dễ tạo authorization coupling.

Nếu các APIs có trust boundaries, dữ liệu hoặc quyền khác nhau, ưu tiên token audience hẹp theo resource. Chỉ dùng multi-audience khi AS và toàn bộ recipients có policy rõ ràng.

## 6. Thiết kế audience identifier cho nhiều APIs

Một naming scheme có thể là:

| Resource Server | Audience identifier |
|---|---|
| Orders API | orders-api |
| Billing API | billing-api |
| Inventory API | inventory-api |
| Reporting API | reporting-api |
| Admin API | admin-api |

Hoặc dùng URI identifiers:

| Resource Server | Audience identifier |
|---|---|
| Orders API | https://api.example.com/orders |
| Billing API | https://api.example.com/billing |
| Inventory API | https://api.example.com/inventory |

Chọn một quy ước và giữ ổn định. Cần xác định:
- Audience có phân biệt environment dev/staging/prod không?
- Mỗi tenant có audience riêng hay tenant là một authorization dimension bên trong API?
- API version có làm thay audience không?
- Internal service có audience khác public API không?
- Gateway và downstream service cùng nhận token hay mỗi hop có token riêng?
- Token exchange có tạo audience mới không?
- Khi API được rename/domain migrate, overlap và migration policy ra sao?

### Audience không nhất thiết là URL public

Một audience identifier có thể là URI hoặc opaque string. Không yêu cầu endpoint phải public hoặc truy cập được tại URI đó. Điều cần thiết là issuer và recipient hiểu cùng identifier.

### Không dùng audience để encode mọi authorization detail

Không tạo audience riêng cho từng order ID hoặc mỗi hành động nhỏ. Audience xác định recipient/resource boundary; scope, role, tenant membership và object policy xử lý quyền chi tiết.

## 7. Cấu hình Spring Boot Resource Server với audiences

Với Spring Boot version hỗ trợ property audiences, có thể cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/
          audiences:
            - orders-api
~~~

Ý nghĩa:
- issuer-uri xác định trusted issuer và hỗ trợ discovery/JWK configuration.
- audiences liệt kê resource identifiers mà JWT phải được cấp cho.
- JWT sai issuer hoặc không có expected audience sẽ không được chấp nhận.
- Các timestamp/signature validations vẫn được áp dụng.

Kiểm tra Spring Boot/Spring Security version của project vì property binding và API có thể khác theo version. Nếu version hiện tại không hỗ trợ audiences property, có thể cấu hình JwtDecoder/ReactiveJwtDecoder với custom validator.

Không chỉ decode JWT trong controller để so sánh aud. Validation phải chạy trong Resource Server authentication pipeline để token sai audience bị từ chối trước khi vào application handler.

### SecurityWebFilterChain

Cấu hình filter chain vẫn cần khai báo Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OrdersApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Audience policy được thực thi bởi decoder/validators đã cấu hình. Filter chain ở trên không tự tạo audience validator nếu decoder được cấu hình thiếu.

## 8. Custom audience validator trong WebFlux

Khi cần kiểm soát rõ expected audience, có thể gắn validator vào NimbusReactiveJwtDecoder.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;

@Configuration
public class OrdersJwtDecoderConfiguration {

    private static final String ISSUER =
            "https://auth.example.com/";

    private static final String AUDIENCE =
            "orders-api";

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withIssuerLocation(ISSUER)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> issuerValidator =
                new JwtIssuerValidator(ISSUER);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            List<String> audiences = jwt.getAudience();

            if (audiences != null && audiences.contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Token is not intended for this resource server",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        new JwtTimestampValidator(),
                        issuerValidator,
                        audienceValidator));

        return decoder;
    }
}
~~~

Giải thích:
- withIssuerLocation cấu hình trusted issuer metadata/JWK discovery.
- jwsAlgorithm giới hạn thuật toán ký được chấp nhận theo policy.
- JwtIssuerValidator kiểm tra issuer.
- JwtTimestampValidator kiểm tra exp/nbf với clock skew mặc định của implementation.
- audienceValidator yêu cầu orders-api xuất hiện trong aud.
- DelegatingOAuth2TokenValidator yêu cầu mọi validators thành công.

**setJwtValidator thay bộ validator hiện có.** Khi tự cấu hình, phải giữ lại timestamp, issuer và các validators khác mà ứng dụng cần. Không chỉ đặt audience validator rồi vô tình bỏ kiểm tra exp/nbf.

Ví dụ trên dùng audience exact string matching. Nếu API sử dụng URI identifier, đặt AUDIENCE bằng đúng URI mà AS phát hành.

### Cần thêm required-claim policy khi profile yêu cầu

JWT generic không bắt buộc mọi registered claims đều hiện diện. Nếu API dùng OAuth JWT access token profile hoặc contract riêng yêu cầu aud/exp/iat, validator cần kiểm tra claim bắt buộc. Audience validator trên đã reject khi aud missing hoặc không chứa expected string; timestamp validator kiểm tra các timestamp có mặt, còn việc bắt buộc exp cần policy rõ theo profile/version.

## 9. Servlet Resource Server dùng JwtDecoder

Trong Servlet stack, ý tưởng tương tự nhưng decoder type là JwtDecoder:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;

@Configuration
public class ServletOrdersDecoderConfiguration {

    private static final String ISSUER =
            "https://auth.example.com/";

    private static final String AUDIENCE =
            "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            List<String> audiences = jwt.getAudience();

            if (audiences != null && audiences.contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Token is not intended for this resource server",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        new JwtTimestampValidator(),
                        new JwtIssuerValidator(ISSUER),
                        audienceValidator));

        return decoder;
    }
}
~~~

Đây là Servlet decoder configuration; nó không dùng ReactiveJwtDecoder. Cả hai stack đều cần giữ các validators bắt buộc.

## 10. Chọn audience theo API thay vì dùng một decoder chung quá rộng

Nếu một deployment phục vụ nhiều resource servers hoặc nhiều API zones, mỗi zone cần audience policy riêng.

~~~text
/orders/**
  expected aud = orders-api

/billing/**
  expected aud = billing-api

/inventory/**
  expected aud = inventory-api
~~~

Một decoder dùng expected audiences quá rộng:

~~~text
allowedAudiences = {
  orders-api,
  billing-api,
  inventory-api
}
~~~

có thể khiến orders endpoint nhận billing token nếu code chỉ kiểm tra aud thuộc tập chung. Điều này thường không phải ý định.

Cần chọn:
- Một Resource Server/decoder riêng cho mỗi trust boundary; hoặc
- Một resolver chọn AuthenticationManager/decoder theo route trước authentication; hoặc
- Một multi-audience policy có chủ đích cho API gateway thực sự đóng vai trò recipient chung.

Không dùng một validator toàn cục chấp nhận mọi audience chỉ vì ứng dụng có nhiều APIs.

### Route selection không thay token validation

Nếu path /orders chọn orders decoder, decoder vẫn phải kiểm tra signature theo trusted issuer, exact issuer, audience orders-api, exp/nbf, token type/profile và các claims bắt buộc khác.

Không dùng path do caller chọn để mở rộng trust source.

## 11. Audience dạng string và array

JWT audience có thể là string hoặc array theo RFC 7519. Spring Security Jwt.getAudience() cung cấp danh sách audience để application kiểm tra.

Ví dụ:

~~~json
{
  "aud": "orders-api"
}
~~~

và:

~~~json
{
  "aud": ["orders-api", "reporting-api"]
}
~~~

Cả hai đều có thể chứa orders-api theo policy membership check.

Một validator đúng theo policy recipient membership:

~~~java
boolean intendedForOrders =
        jwt.getAudience() != null
        && jwt.getAudience().contains("orders-api");
~~~

Không viết:

~~~java
jwt.getAudience().get(0).equals("orders-api")
~~~

vì thứ tự trong array không phải contract để xác định audience duy nhất. API có thể nằm ở phần tử thứ hai hoặc sau đó.

### Khi nào cần strict single audience?

Một tổ chức có thể yêu cầu token chỉ dành cho đúng một API:

~~~java
List<String> aud = jwt.getAudience();

boolean exactAudience =
        aud != null
        && aud.size() == 1
        && aud.contains("orders-api");
~~~

Đây là policy chặt hơn membership check thông thường. Chỉ áp dụng nếu AS contract yêu cầu single audience. Nếu issuer phát hành multi-audience token có chủ đích, strict-single policy sẽ từ chối token đó.

### Audience set policy

Một API có thể cho phép một tập audiences được kiểm soát:

~~~text
orders-api accepts:
  orders-api
  orders-api-v2 (during migration)
~~~

Điều này nên có migration window, owner và sunset plan. Không thêm mọi audience của hệ thống vào một global allow-list.

## 12. Audience validation phải chạy sau khi JWT được verify

Payload JWT thường chỉ là Base64URL-encoded JSON. Bất kỳ ai cũng có thể tạo một chuỗi payload tự khai:

~~~json
{
  "iss": "https://auth.example.com/",
  "aud": ["orders-api"],
  "sub": "admin"
}
~~~

Nếu chỉ decode payload rồi kiểm tra aud, attacker có thể tự khai orders-api.

Đúng flow:

~~~text
Receive compact JWT
  |
  v
Verify JWS signature using trusted key
  |
  v
Validate trusted issuer
  |
  v
Validate audience and time claims
  |
  v
Create Authentication
~~~

Audience claim chỉ trở thành trusted assertion sau khi token signature được verify bằng key của issuer tin cậy và các validation cần thiết thành công.

Không:
- Tạo JWKS URL từ iss chưa verify.
- Fetch jku/x5u tùy ý từ JOSE header.
- Dùng aud chưa verify để chọn quyền.
- Map tenant hoặc admin role từ payload trước signature verification.
- Cho token sai signature chuyển sang provider khác.

Có thể dùng một số claim làm routing hint trong resolver được thiết kế an toàn, nhưng kết quả cuối vẫn phải được verify bằng trust configuration có sẵn.

## 13. Audience validation và scope authorization chạy ở hai giai đoạn

Giả sử hai token:

Token A:

~~~json
{
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Token B:

~~~json
{
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Token A:
- Audience đúng.
- Có thể được authenticate nếu signature/issuer/time/profile hợp lệ.
- GET orders có thể được authorize.

Token B:
- Audience sai.
- Authentication phải thất bại tại orders-api.
- Không xét scope để cứu token.
- API trả 401 invalid_token theo Bearer error semantics.

Token C:

~~~json
{
  "aud": ["orders-api"],
  "scope": "billing.pay"
}
~~~

Token C:
- Audience đúng.
- Có thể authentication thành công.
- Nếu endpoint cần orders.read, authorization từ chối, thường 403.

| Token | Signature/issuer/time | Audience | Scope | Kết quả |
|---|---|---|---|---|
| A | Hợp lệ | orders-api | orders.read | Authentication pass; GET có thể được phép |
| B | Hợp lệ | billing-api | orders.read | 401 invalid_token |
| C | Hợp lệ | orders-api | billing.pay | Authentication pass; orders.read bị 403 |
| D | Sai signature | orders-api | orders.read | 401 invalid_token |
| E | Hợp lệ | orders-api | orders.write | Có thể pass nếu policy endpoint yêu cầu write |

**Wrong audience là authentication failure; missing scope là authorization failure.**

## 14. Audience với Opaque Token Introspection

Opaque access token không có payload để Resource Server tự đọc aud. Resource Server gửi token tới trusted introspection endpoint theo RFC 7662.

Response có thể chứa:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-web",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1794730500
}
~~~

Nếu introspection response chứa aud, Resource Server cần bảo đảm token dành cho resource hiện tại theo contract. Một AS có thể đã bind token với resource khi tạo token và chỉ trả active=true cho authorized resource; implementation cần hiểu rõ behavior đó.

Nếu RS tự làm thêm audience check, phải kiểm tra claims từ introspection response sau khi đã xác minh response đến từ trusted AS qua TLS và client authentication phù hợp.

### active=true không tự có nghĩa audience đúng

Một token có thể active tại AS nhưng dành cho billing-api. Nếu introspection endpoint chỉ trả trạng thái active chung, orders-api vẫn phải enforce resource binding theo contract.

### Không suy ra audience từ client_id

Opaque response có client_id=shop-web không có nghĩa token dành cho orders-api. Client và resource là hai đối tượng khác nhau.

## 15. Resource Indicators và audience issuance

RFC 8707 định nghĩa OAuth 2.0 Resource Indicators. Client có thể chỉ định resource mà nó muốn access token dùng tới, tùy AS hỗ trợ.

Ví dụ minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=...&
redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
resource=https%3A%2F%2Fapi.example.com%2Forders
~~~

AS cần xác định client/grant được phép xin token cho resource đó. AS có thể phát JWT với aud tương ứng.

Không phải mọi AS đều dùng đúng URL/resource indicator này hoặc map nó 1:1 vào aud. Kiểm tra vendor/documentation và token contract.

### Token exchange

Trong token exchange, subject token có thể dành cho service A, còn exchanged token được cấp cho service B với audience khác:

~~~text
User token for gateway
      |
      v
Trusted token exchange
      |
      v
Downstream token for orders-api
~~~

Downstream service nên nhận token được cấp đúng audience của nó. Không chuyển nguyên bearer token dành cho gateway sang mọi downstream APIs nếu contract không cho phép.

## 16. Audience và API gateway

Một gateway có thể là resource server ở edge và gọi downstream APIs. Cần quyết định token nào được dùng ở mỗi hop:

~~~text
Client
  |
  | token aud = gateway-api
  v
API Gateway
  |
  | token aud = orders-api
  v
Orders Service
~~~

Các lựa chọn:
- Client xin token riêng cho downstream resource và gửi qua gateway theo architecture đã định.
- Gateway dùng token exchange để lấy token audience orders-api.
- Gateway dùng service credential riêng để gọi backend, đồng thời truyền actor context đã được bảo vệ theo contract.
- Gateway là recipient duy nhất nếu backend chỉ nhận identity assertions từ gateway qua trusted channel.

Không mặc định token aud=gateway-api hợp lệ cho orders-api. Gateway có thể validate token của nó, nhưng downstream vẫn cần credential/identity trust contract phù hợp.

### Không nhầm audience với network destination

Gọi HTTP tới host orders.example.com không tự khiến token có aud=orders-api. Network route và token recipient là hai lớp khác nhau.

## 17. Multi-audience token: chấp nhận khi có chủ đích

JWT cho phép aud là array. Ví dụ:

~~~json
{
  "aud": [
    "orders-api",
    "reporting-api"
  ]
}
~~~

Nếu orders-api là một recipient được chỉ định, membership check có thể pass. Tuy nhiên, multi-audience token có trade-offs:
- Token có thể được dùng ở nhiều recipients.
- Một token leak có phạm vi tác động rộng hơn.
- Scope có thể bị hiểu khác nhau giữa APIs.
- Các APIs có thể có mức độ trust khác nhau.
- Revocation/incident response ảnh hưởng nhiều services.
- Khó phân biệt token được cấp cho một API hay một nhóm APIs nếu contract mơ hồ.

Nếu dùng multi-audience:
1. Liệt kê recipients cụ thể.
2. Mỗi API chỉ chấp nhận audience của chính nó.
3. Mỗi API vẫn enforce scope/tenant/object authorization riêng.
4. Không dùng chung một allow-list rộng cho tất cả APIs.
5. Audit và test từng resource.
6. Có policy thu hồi/migration cho audience cũ.

## 18. Audience migration khi đổi API identifier

Giả sử orders-api đổi audience từ orders-api sang urn:shop:orders:v2.

~~~text
Phase 1:
  AS emits old audience.
  RS accepts old audience.

Phase 2:
  AS can issue new audience for migrated clients.
  RS accepts old + new during explicit overlap.

Phase 3:
  Monitor old audience usage.
  Migrate remaining clients.

Phase 4:
  AS stops issuing old audience.
  RS removes old audience after token lifetime + skew/propagation window.
~~~

Trong overlap, validator có thể chấp nhận hai identifiers:

~~~java
Set<String> allowedDuringMigration =
        Set.of("orders-api", "urn:shop:orders:v2");

OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    boolean accepted = jwt.getAudience() != null
            && jwt.getAudience().stream()
                    .anyMatch(allowedDuringMigration::contains);

    return accepted
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Audience is not allowed",
                            null));
};
~~~

Đây là allow-list của một API trong migration, không phải allow-list mọi APIs. Có sunset date, metric và owner rõ ràng.

Không dùng audience wildcard, prefix matching tùy tiện, URL host substring matching hoặc mặc định chấp nhận token thiếu aud.

## 19. Kiểm thử validator độc lập

Có thể test audience validator bằng Jwt object:

~~~java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class AudienceValidatorTests {

    private final OAuth2TokenValidator<Jwt> validator =
            new OrdersAudienceValidator("orders-api");

    @Test
    void acceptsExpectedAudience() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "RS256")
                .claim("aud", List.of("orders-api"))
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(300))
                .build();

        assertThat(validator.validate(jwt).hasErrors()).isFalse();
    }

    @Test
    void rejectsTokenForAnotherApi() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "RS256")
                .claim("aud", List.of("billing-api"))
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(300))
                .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }

    @Test
    void rejectsMissingAudience() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "RS256")
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(300))
                .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }
}
~~~

Validator implementation:

~~~java
public final class OrdersAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String expectedAudience;

    public OrdersAudienceValidator(String expectedAudience) {
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        List<String> audiences = jwt.getAudience();

        if (audiences != null && audiences.contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "Token is not intended for this API",
                        null));
    }
}
~~~

Đây là unit test logic claim matching. Jwt được dựng trực tiếp nên không có chữ ký thật; test không chứng minh decoder verify signature, issuer hoặc JWK source.

## 20. Chứng minh API từ chối token dành cho nơi khác

Một test chỉ gọi audience validator hoặc dùng mockJwt() là chưa đủ để chứng minh toàn bộ Resource Server pipeline.

Một negative integration test cần:
1. JWT được ký bằng private key test.
2. Resource Server tin public key tương ứng.
3. JWT issuer hợp lệ.
4. JWT thời gian hợp lệ.
5. JWT có scope mà endpoint yêu cầu.
6. JWT audience là billing-api.
7. Request gửi token tới orders-api.
8. Decoder chạy validators thật.
9. Response bị từ chối trước controller.

Điều này loại bỏ khả năng test fail chỉ vì signature sai hoặc token hết hạn.

### Token test sai audience nhưng các yếu tố khác hợp lệ

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "iat": 1794729600,
  "nbf": 1794729600,
  "exp": 1794730500
}
~~~

Test control token đúng audience:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1794729600,
  "nbf": 1794729600,
  "exp": 1794730500
}
~~~

Hai tokens cần cùng issuer, signing key, algorithm, thời hạn và scope. Chỉ thay audience để test cô lập đúng biến cần kiểm chứng.

## 21. Tạo signed JWT trong integration test

Có thể dùng Nimbus JOSE + JWT để tạo compact JWS test. Ví dụ helper minh họa:

~~~java
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.security.interfaces.RSAPrivateKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;

public String signedAccessToken(
        RSAPrivateKey privateKey,
        String issuer,
        List<String> audience,
        String scope) throws JOSEException {

    Instant now = Instant.now();

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("user-42")
            .audience(audience)
            .issueTime(Date.from(now))
            .notBeforeTime(Date.from(now.minusSeconds(1)))
            .expirationTime(Date.from(now.plusSeconds(300)))
            .claim("scope", scope)
            .build();

    SignedJWT jwt = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                    .keyID("test-signing-key")
                    .build(),
            claims);

    jwt.sign(new RSASSASigner(privateKey));
    return jwt.serialize();
}
~~~

Test fixture cần tạo một RSA key pair riêng. Private key chỉ dùng trong test để ký token; Resource Server decoder chỉ được cấu hình public key/JWKS tương ứng.

Không dùng production private key trong test. Không commit private key thật hoặc access token thật vào repository.

## 22. WebTestClient integration test với decoder thật

Một test WebFlux có thể gọi protected route qua filter chain:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AudienceIntegrationTests {

    @Autowired
    WebTestClient client;

    @Autowired
    TestTokenFactory tokens;

    @Test
    void rejectsBillingTokenAtOrdersApi() throws Exception {
        String token = tokens.signedToken(
                List.of("billing-api"),
                "orders.read");

        client.get()
                .uri("/api/orders")
                .headers(headers -> headers.setBearerAuth(token))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                    .valueMatches(
                            "WWW-Authenticate",
                            ".*invalid_token.*");
    }

    @Test
    void acceptsOrdersTokenAtOrdersApi() throws Exception {
        String token = tokens.signedToken(
                List.of("orders-api"),
                "orders.read");

        client.get()
                .uri("/api/orders")
                .headers(headers -> headers.setBearerAuth(token))
                .exchange()
                .expectStatus().is2xxSuccessful();
    }
}
~~~

Test giả định:
- Test application có real SecurityWebFilterChain.
- ReactiveJwtDecoder dùng test public key hoặc test JWKS endpoint.
- Issuer validator được cấu hình.
- Audience validator yêu cầu orders-api.
- Token factory ký token bằng test private key tương ứng.
- Endpoint trả 2xx khi token đúng và scope đủ.

Test không nên dùng mockJwt() trong hai case này vì mockJwt dựng Authentication và có thể bỏ qua decoder/audience validator.

### Assert controller không được gọi

Có thể mock service/handler dependency và xác nhận nó không được gọi khi audience sai:

~~~java
verifyNoInteractions(ordersService);
~~~

Cần hoàn tất WebTestClient exchange trước khi verify. Điều này chứng minh request bị chặn trước business layer, không chỉ status cuối cùng tình cờ là 401.

## 23. Phân biệt audience failure với scope failure trong tests

Nên có ba tests độc lập:

| Test | Audience | Scope | Kết quả |
|---|---|---|---|
| Token đúng resource | orders-api | orders.read | GET được phép |
| Token dành cho API khác | billing-api | orders.read | 401 invalid_token |
| Token đúng resource nhưng thiếu scope | orders-api | billing.pay | 403 hoặc authorization denial |

Token sai audience cần có scope đúng để chứng minh API từ chối vì resource mismatch.

Token đúng audience nhưng thiếu scope cần có signature, issuer, time hợp lệ để chứng minh authentication pass và authorization fail.

Không viết một test token vừa sai audience vừa thiếu scope rồi kết luận 401 là do audience. Test đó không cô lập được nguyên nhân.

## 24. Dùng mockJwt() đúng mục đích

Spring Security Test hỗ trợ mockJwt() trong WebFlux để kiểm tra authorization rules.

Ví dụ:

~~~java
client.mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("aud", List.of("orders-api")))
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().is2xxSuccessful();
~~~

Đây là test authorization sau khi đã giả lập Authentication. Nó không chứng minh:
- Chữ ký JWT hợp lệ.
- Issuer đã được verify.
- Audience validator đã chạy.
- JWKS endpoint đã được gọi.
- Timestamp claims được kiểm tra.

Dùng mockJwt cho permission mapping/route access; dùng signed JWT qua decoder thật để chứng minh audience enforcement.

## 25. Kiểm tra token audience missing, malformed và multiple

Negative tests nên bao gồm:

| Token claim | Policy | Kết quả |
|---|---|---|
| aud = orders-api | Orders API | Pass audience |
| aud = [orders-api, reporting-api] | Membership policy | Pass nếu multi-audience được cho phép |
| aud = billing-api | Orders API | Reject |
| aud missing | API requires aud | Reject |
| aud = [] | API requires aud | Reject |
| aud = [""] | API requires orders-api | Reject |
| aud = ["orders-api-v2"] | Expected orders-api | Reject trừ khi migration allow-list |
| aud = ["ORDERS-API"] | Expected lowercase exact ID | Reject nếu identifier case-sensitive |
| aud = [billing-api, inventory-api] | Orders API | Reject |
| aud malformed type | JWT parser/claim validation | Reject |

JWT parser thường validate claim type theo library; nếu claim malformed, token không được chuyển thành principal hợp lệ.

### Duplicate audience values

JWT array có thể được phát hành với duplicate strings do lỗi issuer. Nếu contract yêu cầu unique audience values, thêm validator/policy hoặc sửa issuer. Không dựa vào index đầu tiên.

## 26. Kiểm tra multi-issuer và audience độc lập

Một API có thể tin nhiều issuers nhưng chỉ chấp nhận audience của chính nó:

~~~text
Trusted issuers:
  https://auth-a.example.com/
  https://auth-b.example.com/

Orders API audience:
  orders-api
~~~

Policy:

~~~text
(iss == auth-a AND aud contains orders-api)
OR
(iss == auth-b AND aud contains orders-api)
~~~

Token từ auth-a với aud=billing-api phải reject. Token từ auth-b với aud=orders-api có thể pass nếu issuer B được phép phát access token cho orders-api và các claims khác hợp lệ.

Không để issuer A chấp nhận audience billing-api chỉ vì issuer B có token orders-api. Issuer allow-list và audience allow-list là hai chiều kiểm soát độc lập.

### Namespace audience theo issuer

Nếu mỗi issuer có naming conventions riêng, cấu hình mapping rõ:

~~~text
issuer A:
  orders resource = urn:auth-a:orders

issuer B:
  orders resource = orders-api
~~~

Đừng tự suy ra audience từ issuer URL hoặc tenant name. Dùng trusted configuration.

## 27. Token dành cho frontend không phải token dành cho API

OIDC ID token thường có audience là client_id của relying party:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["shop-web"],
  "exp": 1794730500
}
~~~

ID token được client dùng để hiểu kết quả authentication của user. Resource Server API không được nhận nó như access token chỉ vì:
- Cùng issuer.
- Cùng signing key.
- Cùng sub.
- Có chữ ký hợp lệ.
- Có một claim tên scope do issuer thêm.

Access token dành cho orders-api phải có token purpose/profile và audience phù hợp. Nếu dùng RFC 9068, có thể kiểm tra typ=at+jwt theo profile; không coi ID token và access token là cùng một loại credential.

### Token type và audience là hai checks khác nhau

Một JWT có aud=orders-api nhưng typ/profile sai vẫn có thể bị từ chối. Ngược lại, typ=at+jwt không cứu token có aud=billing-api.

## 28. Audience trong service-to-service client credentials

Với client credentials, token đại diện client application chứ không phải user. AS có thể phát:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "inventory-worker",
  "client_id": "inventory-worker",
  "aud": ["orders-api"],
  "scope": "orders.sync"
}
~~~

Orders API cần:
- Xác minh issuer/signature/time.
- Yêu cầu audience orders-api.
- Xác định actor là machine client theo token profile.
- Kiểm tra scope orders.sync.
- Áp dụng resource/tenant policy cho client identity.

Không vì client_id được đăng ký trong AS mà chấp nhận token cho mọi APIs. Client credentials token vẫn cần audience/resource binding.

## 29. Audience và tenant trong multi-tenant APIs

Một SaaS API có thể dùng cùng audience orders-api cho mọi tenants:

~~~json
{
  "aud": ["orders-api"],
  "tenant_id": "blue",
  "scope": "orders.read"
}
~~~

Audience nói token dành cho Orders API. tenant_id/membership nói actor có thể hoạt động trong tenant nào. Object policy quyết định actor có được truy cập order cụ thể không.

Không dùng tenant ID làm audience mặc định cho mọi tenant nếu architecture không yêu cầu resource server riêng theo tenant. Ngược lại, nếu mỗi tenant có API endpoint/resource boundary độc lập, có thể có audience riêng theo contract.

Các lớp cần giữ độc lập:
- API recipient.
- Issuer.
- Actor identity.
- Tenant membership.
- Scope/authority.
- Object ownership/business policy.

## 30. HTTP response khi audience sai

Token sai audience không hợp lệ cho Resource Server. Với Bearer token, response thường là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/problem+json
~~~

Không trả 403 insufficient_scope vì principal chưa được authenticate hợp lệ cho API này.

Không cần tiết lộ:
- Audience token thực tế là billing-api.
- Danh sách audience được API tin.
- Issuer nội bộ.
- JWT claims.
- Signing key hoặc kid.
- Token string.

Một body generic:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "code": "invalid_token",
  "detail": "A valid access token for this resource is required"
}
~~~

WWW-Authenticate giữ Bearer protocol semantics; JSON body chỉ là representation cho client.

## 31. Logging và metrics cho audience mismatch

Log an toàn có thể ghi:

~~~text
requestId = req-421
resourceServer = orders-api
configuredIssuerId = shop-auth
authenticationOutcome = failure
failureCategory = audience_mismatch
httpStatus = 401
~~~

Không log raw token hoặc toàn bộ claims. Audience trong token chưa verify không nên được log như trusted resource identity; nếu cần chẩn đoán, ghi một category đã sanitize hoặc chỉ ghi expected resource ID.

Metrics có thể theo dõi:
- audience_validation_success_total.
- audience_validation_failure_total.
- missing_audience_total.
- issuer_validation_failure_total.
- invalid_signature_total.
- resource_server_id (configured, bounded label).
- issuer_id (configured identifier).

Không dùng raw audience strings tùy ý từ token làm metric labels vì có thể tạo high cardinality hoặc bị attacker kiểm soát.

### Alert theo tỷ lệ mismatch

Một đợt audience mismatch tăng đột biến có thể chỉ ra:
- Client đang dùng nhầm token endpoint/resource.
- API deployment đổi audience nhưng client chưa migrate.
- AS audience mapper bị lỗi.
- Gateway chuyển tiếp token dành cho chính nó tới downstream.
- Token substitution attempt.
- Environment config dev/staging/prod bị trộn.

Không tự động mở audience allow-list chỉ để giảm alert. Tìm đúng issuer/client/resource configuration.

## 32. Các anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách đúng |
|---|---|---|
| Chỉ kiểm tra signature và issuer | Token của API khác có thể được chấp nhận | Validate aud |
| Dùng client_id thay aud | Nhầm caller với recipient | Kiểm tra resource audience |
| Dùng azp thay aud | Nhầm OIDC authorized party với API recipient | Kiểm tra access-token audience |
| Scope đúng nên bỏ qua aud | Cross-resource token substitution | Cả aud và scope đều cần |
| Chỉ lấy aud[0] | Bỏ sót audience khác hoặc phụ thuộc thứ tự | Membership check |
| Chấp nhận mọi audience | Trust boundary quá rộng | Per-API allow-list |
| Chấp nhận aud missing | Token không bind resource | Reject nếu API contract yêu cầu |
| Decode payload trước signature rồi authorize | Attacker tự khai aud | Validate trong decoder pipeline |
| Dùng mockJwt để chứng minh audience validator | Test bypass decoder | Signed token + real decoder |
| Token sai aud trả 403 | Nhầm authentication với authorization | 401 invalid_token |
| Dùng audience wildcard/prefix | Chấp nhận resource ngoài dự kiến | Exact identifier matching |
| Dùng một decoder cho mọi APIs với allow-list union | Billing token có thể vào Orders API | Decoder/manager policy riêng |
| Xóa old audience ngay khi đổi identifier | Client đang migrate bị lỗi | Overlap có thời hạn |
| Không test audience multi-value | Lỗi khi aud là array | Test string/array contract |
| Gateway chuyển nguyên token sai aud xuống service | Downstream trust confusion | Token exchange/downstream audience |
| ID token gọi Resource Server | Cross-JWT confusion | Access token profile + aud |
| Log full token khi mismatch | Credential leakage | Sanitized logs |

## 33. Checklist trước khi triển khai

**Authorization Server**
1. AS phát access token có audience đúng resource chưa?
2. Client có được phép xin audience đó không?
3. Resource indicator/client registration mapping có rõ không?
4. Token cho APIs khác có audience khác không?
5. Có phát ID token và access token với purpose riêng không?
6. Multi-audience có thực sự cần thiết không?

**Resource Server**
1. Expected audience identifier chính xác là gì?
2. Decoder có validate issuer và audience cùng nhau không?
3. Timestamp và signature validators có còn được giữ khi custom validator được thêm không?
4. Audience missing có bị reject không?
5. Multi-audience policy là membership hay strict single?
6. Token type/profile có được kiểm tra khi contract yêu cầu không?
7. Opaque introspection có resource/audience binding không?
8. Mỗi API có policy riêng không?

**Testing**
1. Token đúng audience và đúng scope được nhận.
2. Token sai audience nhưng signature/issuer/time/scope đúng bị reject.
3. Token thiếu audience bị reject.
4. Token audience dạng array được xử lý đúng.
5. Token đúng audience nhưng thiếu scope bị 403.
6. Token sai signature bị reject.
7. Token issuer sai bị reject.
8. Controller/service không được gọi khi audience sai.
9. MockJwt không được dùng thay signed-token integration test.
10. Multi-issuer và gateway/downstream paths được kiểm tra riêng.

## 34. Tổng kết

~~~text
AS issues access token for billing-api
              |
              v
Client sends token to orders-api
              |
              v
Orders Resource Server
  verify signature
  validate trusted issuer
  validate timestamps/profile
  require aud contains orders-api
              |
       +------+------+
       |             |
       v             v
  aud matches     aud mismatch
       |             |
       v             v
 Authentication   401 invalid_token
       |
       v
 Check scope / tenant / object policy
       |
   +---+---+
   |       |
   v       v
 Allow   403 if authorization denied
~~~

Các nguyên tắc cần nhớ:

1. **Audience xác định resource server được dự định nhận token**.
2. **Issuer và audience là hai checks độc lập**: issuer đúng không có nghĩa recipient đúng.
3. **client_id, azp và scope không thay thế aud**.
4. Audience có thể là string hoặc array; kiểm tra membership theo contract, không phụ thuộc phần tử đầu.
5. Resource Server phải kiểm tra audience trong decoder/validation pipeline sau khi chữ ký được verify.
6. Token dành cho API khác phải bị từ chối ngay cả khi signature, issuer, time và scope đều hợp lệ.
7. Wrong audience là authentication failure, thường trả 401 invalid_token; token đúng audience nhưng thiếu scope thường trả 403.
8. Mỗi API cần expected audience riêng; không dùng global allow-list quá rộng.
9. Multi-audience chỉ nên dùng khi có chủ đích và policy rõ cho mọi recipients.
10. Gateway/downstream services cần token audience phù hợp từng hop hoặc một trusted identity contract riêng.
11. Dùng signed JWT qua decoder thật và WebTestClient để chứng minh API từ chối token sai audience.
12. mockJwt() phù hợp cho authorization tests nhưng không chứng minh signature/audience validation đã chạy.

**Kết luận:** Thiết lập audience là cách Resource Server xác nhận access token được cấp cho đúng API. Một token được issuer tin cậy ký vẫn phải bị từ chối nếu audience không bao gồm resource hiện tại. Để chứng minh điều đó, hãy tạo hai JWT test giống nhau về issuer, key, thời gian và scope, chỉ khác aud; gửi chúng qua SecurityWebFilterChain thật và xác nhận token đúng được chấp nhận còn token dành cho API khác nhận 401 trước khi business handler chạy.

## 35. Tài liệu tham khảo

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server JWT:** ReactiveJwtDecoder, issuer và audience validation. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server JWT:** JwtDecoder, issuer và audience validation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Boot Reference — OAuth2 Resource Server:** JWT issuer, JWK Set URI và audiences properties theo version. https://docs.spring.io/spring-boot/reference/security/oauth2.html
- **Spring Security API — Jwt:** audience claim accessor và JWT claim model. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html
- **Spring Security API — JwtValidators:** default issuer/timestamp validator composition. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html
- **Spring Security Reference — Reactive Testing:** WebTestClient và mock JWT. https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- **RFC 7519 — JSON Web Token:** aud claim, issuer và registered claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** JWT access-token profile and audience requirements. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 8707 — Resource Indicators for OAuth 2.0:** resource parameter and resource-specific tokens. https://www.rfc-editor.org/rfc/rfc8707
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** invalid_token and Bearer error response. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** issuer metadata and JWKS discovery. https://www.rfc-editor.org/rfc/rfc8414
- **OpenID Connect Core 1.0:** ID Token audience and authorized party semantics. https://openid.net/specs/openid-connect-core-1_0.html
- **Nimbus JOSE + JWT Documentation:** JWS signing and verification APIs for test fixtures. https://connect2id.com/products/nimbus-jose-jwt
