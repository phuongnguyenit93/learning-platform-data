# Kiểm thử token, scope và hết hạn mà không đưa thông tin nhạy cảm vào ví dụ

Với OAuth2 và OpenID Connect (OIDC), kiểm thử API không chỉ là gửi một bearer token rồi xác nhận HTTP 200. Cần kiểm tra token có đúng loại, đúng issuer và audience, còn hiệu lực, có scope cần thiết và được xử lý an toàn khi hết hạn hoặc bị từ chối. Đồng thời, tài liệu springdoc-openapi phải mô tả đúng cơ chế xác thực mà server thực thi.

Các ví dụ trong tài liệu, test source và log phải dùng dữ liệu giả. Không đưa access token, refresh token, ID token, client secret, API key thật hoặc nội dung token lấy từ production vào Markdown, @ExampleObject, fixture, snapshot hay ảnh chụp Swagger UI.

## 1. Phân biệt các loại token trước khi kiểm thử

OAuth2 và OIDC có thể sử dụng nhiều loại token, nhưng chúng có mục đích khác nhau:

| Loại | Mục đích | Nơi thường được sử dụng |
| --- | --- | --- |
| Access token | Cấp quyền truy cập resource server theo audience và scope/authority | Header Authorization: Bearer ... khi gọi API |
| Refresh token | Xin access token mới mà không yêu cầu người dùng đăng nhập lại | Gửi tới token endpoint của authorization server |
| ID token | Xác nhận kết quả xác thực người dùng trong OIDC | Client OIDC kiểm tra sau đăng nhập |

Không dùng ID token thay cho access token khi gọi resource API. ID token có audience dành cho OIDC client; access token có audience và quyền dành cho resource server. Hai loại có thể đều là JWT nhưng không có cùng mục đích hoặc quy tắc kiểm tra.

Refresh token cũng không được gửi tới API nghiệp vụ như bearer access token. Nó là credential có khả năng cấp access token mới, vì vậy cần được bảo vệ nghiêm ngặt và chỉ gửi tới authorization server theo flow đã cấu hình.

## 2. Các lớp kiểm tra của access token

Một resource server thường cần kiểm tra nhiều điều kiện:

| Điều kiện | Ý nghĩa | Ví dụ tình huống lỗi |
| --- | --- | --- |
| Chữ ký | Token được ký bởi khóa tin cậy và thuật toán được chấp nhận | Chữ ký sai hoặc khóa không được tin cậy |
| Issuer (iss) | Token do authorization server dự kiến phát hành | Token đến từ issuer khác |
| Audience (aud) | Token được phát hành cho API hiện tại | Token dành cho ứng dụng khác |
| Thời hạn (exp) | Token chưa hết hạn | Token đã hết hạn |
| Thời điểm hiệu lực (nbf) | Token đã tới thời điểm được phép sử dụng | Token chưa có hiệu lực |
| Scope/authority | Token có quyền thực hiện thao tác | Thiếu orders.read |
| Loại token | Token đúng mục đích và loại được API chấp nhận | Dùng ID token thay access token |

iat (issued at) ghi nhận thời điểm token được phát hành. Claim này hữu ích cho audit và một số chính sách riêng, nhưng không nên mặc định rằng mọi resource server đều tự kiểm tra iat như điều kiện hết hạn. exp xác định thời điểm hết hạn; nbf xác định thời điểm sớm nhất token có hiệu lực.

## 3. Phân biệt 401 và 403 trong kiểm thử

Hai status code này giúp xác định lỗi nằm ở xác thực hay phân quyền:

| Tình huống | Kết quả HTTP thường mong đợi |
| --- | --- |
| Không gửi access token tới endpoint yêu cầu xác thực | 401 Unauthorized |
| Token sai định dạng, chữ ký không hợp lệ hoặc đã hết hạn | 401 Unauthorized |
| Token chưa tới thời điểm nbf | 401 Unauthorized |
| Token hợp lệ nhưng thiếu scope cần thiết | 403 Forbidden |
| Token hợp lệ và có scope cần thiết | 2xx theo endpoint |

Quy tắc cụ thể còn phụ thuộc exception handler và cấu hình Spring Security. Không trả chi tiết nội bộ về chữ ký, khóa, token hoặc issuer trong response lỗi cho client; có thể ghi mã lỗi an toàn để hỗ trợ xử lý.

## 4. Dùng token giả trong tài liệu và ví dụ

Ví dụ HTTP trong tài liệu chỉ nên dùng placeholder:

~~~http
GET /api/orders
Authorization: Bearer <TEST_ACCESS_TOKEN>
~~~

<TEST_ACCESS_TOKEN> là ký hiệu thay thế, không phải token có thể gửi trực tiếp. Không chèn token JWT thật vào @ExampleObject, file Markdown hoặc OpenAPI JSON.

Nếu cần minh họa cấu trúc claim, dùng payload giả không chứa dữ liệu cá nhân hoặc bí mật:

~~~json
{
  "iss": "https://issuer.test.example",
  "sub": "test-user-001",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600
}
~~~

Đây chỉ là JSON minh họa claim, không phải JWT đã ký. Không ghép payload này với một chữ ký giả rồi mô tả như token có thể xác thực. Khi cần token kiểm thử có chữ ký, hãy tạo token trong test bằng khóa riêng chỉ dùng cho test và không đưa khóa đó vào tài liệu công khai.

## 5. Kiểm thử scope với Spring Security và MockMvc

Với resource server JWT, Spring Security thường ánh xạ claim scope hoặc scp thành authority có tiền tố SCOPE_. Ví dụ scope orders.read trở thành authority SCOPE_orders.read.

Có thể bảo vệ method bằng:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasAuthority('SCOPE_orders.read')")
@GetMapping("/api/orders")
List<OrderResponse> listOrders() {
    return orderService.findAll();
}
~~~

Để dùng @PreAuthorize, ứng dụng phải bật method security, thường bằng @EnableMethodSecurity trong cấu hình Spring Security. Nếu dự án chỉ dùng request matcher ở filter chain, hãy kiểm thử đúng cơ chế authorization đang được triển khai.

Trong test, dùng jwt() request post-processor để tạo một JwtAuthenticationToken giả lập:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderScopeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsReadScope() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void rejectsTokenWithoutReadScope() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Ví dụ trên kiểm tra phân quyền theo authority. Nó không xác minh chữ ký JWT, issuer, audience, thời hạn hoặc quá trình tải khóa từ JWKS, vì jwt() tạo principal đã được xác thực cho test và bỏ qua bước decode bearer token thực.

Nếu ứng dụng dùng JwtAuthenticationConverter tùy chỉnh, hãy kiểm tra converter ánh xạ claim đúng như cấu hình production. Có thể kiểm thử riêng converter bằng JWT model giả có claim scope hoặc scp, rồi xác nhận danh sách authority được tạo ra.

## 6. Kiểm tra cả trường hợp không có token và token không hợp lệ

Các test dùng jwt() không thay thế kiểm thử filter chain nhận header bearer thật. Nên có test tích hợp riêng cho:

- Không có header Authorization.
- Header không theo định dạng Bearer.
- Token sai cấu trúc hoặc không thể decode.
- Token có chữ ký không hợp lệ.
- Token hợp lệ nhưng thiếu scope.

Ví dụ không gửi token:

~~~java
mockMvc.perform(get("/api/orders"))
    .andExpect(status().isUnauthorized());
~~~

Ví dụ gửi chuỗi token giả không phải credential hợp lệ:

~~~java
mockMvc.perform(get("/api/orders")
        .header("Authorization", "Bearer not-a-jwt"))
    .andExpect(status().isUnauthorized());
~~~

Chuỗi not-a-jwt cố ý sai định dạng, không phải token production. Không ghi giá trị header này vào log. Nếu exception handler tùy biến response, assertion nên kiểm tra status và mã lỗi công khai thay vì nội dung lỗi nội bộ của decoder.

## 7. Kiểm thử exp, nbf và clock skew

JWT có thể chứa các claim thời gian:

- exp: token không còn được chấp nhận sau thời điểm hết hạn, có xét clock skew theo validator.
- nbf: token không được chấp nhận trước thời điểm bắt đầu hiệu lực, có xét clock skew.
- iat: thời điểm phát hành; nếu ứng dụng có chính sách riêng về token phát hành trong tương lai hoặc token quá cũ, cần kiểm tra chính sách đó tường minh.

Các máy trong hệ thống có thể lệch đồng hồ vài giây. Validator thường cho phép một khoảng clock skew nhỏ để tránh từ chối token hợp lệ chỉ vì sai khác thời gian. Khoảng này phải được cấu hình có chủ đích; không tăng quá lớn để che giấu đồng hồ hệ thống sai.

Spring Security có JwtTimestampValidator để kiểm tra các claim thời gian. Có thể cấu hình clock skew và clock cố định trong unit test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

class JwtTimestampValidatorTest {

    private final Instant now = Instant.parse("2030-01-01T12:00:00Z");

    private JwtTimestampValidator validator() {
        JwtTimestampValidator validator = new JwtTimestampValidator();
        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));
        validator.setClockSkew(Duration.ofSeconds(30));
        return validator;
    }

    @Test
    void rejectsExpiredTokenOutsideClockSkew() {
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .subject("test-user")
            .issuedAt(now.minusSeconds(600))
            .expiresAt(now.minusSeconds(60))
            .build();

        OAuth2TokenValidatorResult result = validator().validate(jwt);

        assertThat(result.hasErrors()).isTrue();
    }

    @Test
    void rejectsTokenBeforeNotBeforeTimeOutsideClockSkew() {
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .subject("test-user")
            .issuedAt(now)
            .notBefore(now.plusSeconds(60))
            .expiresAt(now.plusSeconds(600))
            .build();

        OAuth2TokenValidatorResult result = validator().validate(jwt);

        assertThat(result.hasErrors()).isTrue();
    }
}
~~~

Các test trên kiểm tra riêng timestamp validator bằng Jwt model được dựng trong bộ nhớ; chúng không xác minh chữ ký. Dùng Clock.fixed giúp test có kết quả ổn định, không phải chờ thời gian thực trôi qua. Nếu dự án dùng phiên bản Spring Security có API khác, điều chỉnh constructor hoặc setter theo Javadoc của dependency đang cài.

Hãy thêm test cho token vừa hết hạn nhưng còn trong khoảng clock skew, token hết hạn vượt quá khoảng đó, token có nbf vừa nằm trong vùng cho phép và token có nbf vượt quá vùng cho phép. Mục tiêu là xác nhận chính xác ranh giới mà hệ thống đang cấu hình.

## 8. Phân biệt mock JWT với kiểm thử chữ ký thật

Test dùng jwt() hoặc dựng Jwt trực tiếp rất hữu ích để kiểm tra authorization và validator riêng. Nhưng chúng không đủ để chứng minh toàn bộ resource server xác minh token đúng.

Nên chia thành hai lớp:

| Loại test | Thành phần được kiểm tra | Điều không được chứng minh |
| --- | --- | --- |
| Mock JWT/authority | Controller, method security và quy tắc scope | Chữ ký, JWKS, issuer, audience và decode header bearer |
| Unit test validator | Quy tắc timestamp, issuer hoặc audience riêng lẻ | Filter chain và giao tiếp với JWKS thật |
| Integration test với khóa test | Decode, chữ ký, issuer, audience và timestamp qua resource server | Khả năng tương thích với mọi cấu hình production nếu test dùng issuer giả |
| End-to-end với authorization server test | Flow cấp token, resource server và quyền | Không chứng minh production secret hoặc khóa production |

Để kiểm tra chữ ký, tạo cặp khóa RSA/EC chỉ dùng trong test hoặc chạy test authorization server/JWKS giả lập. Ký token bằng private key test, cấu hình decoder tin public key tương ứng, rồi gửi bearer token qua MockMvc hoặc HTTP client. Không dùng private key production, secret thật hoặc token của người dùng trong test.

Kiểm tra ít nhất:

1. Chữ ký hợp lệ và khóa tin cậy.
2. Chữ ký bị sửa hoặc dùng khóa khác.
3. iss đúng và sai.
4. aud chứa resource server và không chứa resource server.
5. exp hợp lệ, hết hạn.
6. nbf đã tới và chưa tới.
7. Khóa kid không tồn tại hoặc JWKS không khả dụng nếu hệ thống cần xử lý tình huống đó.

## 9. Kiểm tra issuer và audience

Khi cấu hình resource server bằng issuer URI, Spring Security có thể dùng metadata của authorization server để tìm JWKS và xác minh issuer. Nếu API yêu cầu audience cụ thể, cần cấu hình validator audience; không giả định mọi cấu hình mặc định đều tự kiểm tra audience theo tên service của bạn.

Ví dụ cấu hình validator audience:

~~~java
import java.util.List;

import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

final class AudienceValidator implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    AudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        List<String> audiences = jwt.getAudience();
        if (audiences != null && audiences.contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Token không dành cho API này.",
            null
        );
        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

Khi ghép validator audience với validator mặc định, cần giữ cả kiểm tra issuer và timestamp:

~~~java
OAuth2TokenValidator<Jwt> issuerAndTimestamp =
    JwtValidators.createDefaultWithIssuer("https://issuer.test.example");

OAuth2TokenValidator<Jwt> audience =
    new AudienceValidator("orders-api");

NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri("https://issuer.test.example/jwks")
    .build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(issuerAndTimestamp, audience)
);
~~~

Đoạn cấu hình minh họa cách ghép validator; cần tạo JwtDecoder theo JWKS URI hoặc public key test phù hợp. Dùng issuer giả trong test, không thay issuer production bằng giá trị test khi triển khai.

## 10. Kiểm tra OIDC: ID token và access token

OIDC bổ sung lớp xác thực danh tính trên OAuth2. Trong luồng đăng nhập OIDC, client kiểm tra ID token và các claim liên quan; resource server kiểm tra access token dành cho API.

| Claim/đặc tính | Kiểm tra trong OIDC |
| --- | --- |
| iss | Khớp issuer đã cấu hình |
| sub | Định danh người dùng tại issuer |
| aud | Chứa client ID của OIDC client |
| exp | ID token chưa hết hạn |
| iat | Thời điểm phát hành hợp lý theo chính sách |
| nonce | Khớp nonce của phiên đăng nhập để chống replay |
| azp | Authorized party khi có nhiều audience và cần xác minh client được ủy quyền |

Access token phải được kiểm tra theo resource server, đặc biệt audience và scope dành cho API. Không suy ra access token hợp lệ chỉ vì ID token của cùng phiên đăng nhập hợp lệ.

Với Spring Security test support, có thể dùng oidcLogin() để kiểm thử controller phụ thuộc OidcUser mà không gọi identity provider thật:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

mockMvc.perform(get("/profile")
        .with(oidcLogin().idToken(token ->
            token.claim("sub", "test-user-001")
                .claim("email", "user@example.test"))))
    .andExpect(status().isOk());
~~~

Test này giả lập principal OIDC để kiểm tra ứng dụng xử lý thông tin người dùng. Nó không xác minh chữ ký ID token, nonce hoặc trao đổi authorization code với identity provider. Các bước protocol cần integration test riêng với issuer test.

## 11. Kiểm thử refresh token an toàn

Refresh token thuộc luồng cấp token của authorization server, không thuộc bước gọi API nghiệp vụ. Nếu ứng dụng hoặc authorization server quản lý refresh token, cần kiểm tra:

- Refresh token hợp lệ cấp access token mới.
- Refresh token hết hạn hoặc bị revoke bị từ chối.
- Token rotation phát hành refresh token mới theo chính sách.
- Refresh token cũ không được tái sử dụng sau rotation nếu server hỗ trợ phát hiện reuse.
- Refresh token gắn đúng client, user/session và phạm vi cấp quyền.
- Logout hoặc thu hồi session xử lý refresh token theo chính sách.

Không đưa refresh token vào Authorization header của API nghiệp vụ. Không ghi refresh token vào log hoặc lưu trong fixture dùng chung. Khi test rotation, giữ giá trị token trong bộ nhớ test, dùng token giả do issuer test phát hành và xóa dữ liệu test sau khi chạy.

Nếu hệ thống dùng refresh token rotation, kiểm tra trường hợp hai request refresh đồng thời. Chính sách có thể cho phép một request thành công và request còn lại bị từ chối hoặc kích hoạt thu hồi token family khi phát hiện reuse. Kết quả phải khớp tài liệu của authorization server đang sử dụng.

## 12. Kiểm tra scope được công bố trong OpenAPI

Khi mô tả OAuth2 bằng springdoc, khai báo flow và scopes trong security scheme:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://issuer.test.example/oauth/token",
            scopes = {
                @OAuthScope(
                    name = "orders.read",
                    description = "Đọc đơn hàng"
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Tạo hoặc cập nhật đơn hàng"
                )
            }
        )
    )
)
~~~

Operation có thể yêu cầu scope:

~~~java
@Operation(
    summary = "Đọc đơn hàng",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"orders.read"}
    )
)
~~~

Kiểm tra tài liệu JSON sinh ra có components.securitySchemes.oauth2.flows.clientCredentials.scopes và requirement của operation có đúng orders.read. Scope trong OpenAPI chỉ mô tả hợp đồng; Spring Security vẫn phải ánh xạ claim và thực thi authority tương ứng.

Không đưa access token hoặc refresh token vào @ExampleObject. Nếu cần ví dụ request, dùng placeholder:

~~~http
GET /api/orders
Authorization: Bearer <TEST_ACCESS_TOKEN>
~~~

## 13. Ma trận test token và scope

Một ma trận cơ bản cho resource server:

| Token | Scope | Thời hạn | Kết quả mong đợi |
| --- | --- | --- | --- |
| Không gửi | — | — | 401 |
| Sai định dạng/chữ ký | Đủ hoặc không rõ | — | 401 |
| Token hợp lệ | Thiếu orders.read | Còn hạn | 403 |
| Token hợp lệ | Có orders.read | Còn hạn | 2xx |
| Token hợp lệ | Có orders.read | Hết hạn | 401 |
| Token hợp lệ | Có orders.read | nbf ở tương lai | 401 |
| Token hợp lệ từ issuer khác | Có scope | Còn hạn | 401 |
| Token hợp lệ cho audience khác | Có scope | Còn hạn | 401 |
| ID token được gửi như access token | Có thể có claim scope giả | Còn hạn | Từ chối theo validation token type/audience |

Với OIDC client, thêm test cho ID token sai issuer, sai audience, nonce không khớp và token hết hạn. Với authorization server, thêm test refresh token hết hạn, bị revoke và reuse sau rotation.

## 14. Không để token xuất hiện trong log, trace hoặc báo cáo lỗi

Credential có thể bị lộ qua nhiều vị trí ngoài mã nguồn:

| Nơi có thể lộ | Biện pháp |
| --- | --- |
| HTTP access log | Không ghi toàn bộ Authorization/Cookie header |
| Application log | Không log token, request header hoặc object chứa credential |
| Exception message | Không nối token hoặc raw JWT vào thông báo lỗi |
| Distributed tracing | Xóa/redact Authorization, Cookie và token-related attributes |
| Test report/snapshot | Dùng token giả, không ghi credential thật |
| Swagger UI screenshot | Xóa authorization trước khi chụp; dùng môi trường test |
| CI variables/output | Không echo secret; dùng secret store và masking |
| OpenAPI examples | Chỉ dùng placeholder hoặc dữ liệu giả |

Các tên field cần được xem là nhạy cảm gồm Authorization, Cookie, Set-Cookie, access_token, refresh_token, id_token, client_secret và API key. Redaction cần được áp dụng ở logger, gateway, tracing exporter và công cụ quan sát; chỉ che token ở một lớp là chưa đủ.

Không bật logging mức DEBUG/TRACE cho thành phần security trong production nếu chưa kiểm tra nội dung có thể bị ghi. Khi cần chẩn đoán, ghi correlation ID, issuer alias, kết quả validation hoặc mã lỗi an toàn thay vì raw token.

## 15. Dùng khóa và credential chỉ dành cho test

Khi cần xác minh chữ ký thật, tạo khóa test ngắn hạn trong test fixture hoặc dùng bộ khóa cố định chỉ dành cho test repository. Private key test không được dùng ở production và không được sao chép từ secret manager production.

Nguyên tắc:

1. Dùng issuer test riêng như https://issuer.test.example.
2. Dùng audience giả như orders-api.
3. Dùng subject tổng hợp, không phải email hoặc ID người thật.
4. Dùng cặp khóa test, không dùng private key production.
5. Token có thời hạn ngắn và chỉ dùng trong tiến trình test.
6. Không lưu token đã ký trong fixture lâu dài nếu có thể tạo lại khi test chạy.
7. Không log token hoặc nội dung Authorization khi test thất bại.
8. Thu hồi/xóa khóa và dữ liệu test nếu môi trường kiểm thử có state lâu dài.

Nếu test dùng WireMock hoặc mock JWKS endpoint, chỉ phục vụ public key test. Không trả private key qua JWKS và không cho phép môi trường production tin cậy issuer test.

## 16. Kiểm thử response lỗi mà không làm lộ chi tiết bảo mật

API nên trả thông tin đủ để client biết cần đăng nhập, cấp scope hoặc lấy token mới, nhưng không tiết lộ chi tiết nội bộ.

Ví dụ response an toàn:

~~~json
{
  "code": "INSUFFICIENT_SCOPE",
  "message": "Token không có quyền đọc đơn hàng.",
  "requiredScope": "orders.read"
}
~~~

Không trả:

- Raw token hoặc decoded payload đầy đủ.
- Nội dung chữ ký hoặc private key.
- Chi tiết cấu hình JWKS nội bộ.
- Client secret hoặc refresh token.
- Stack trace hoặc tên class decoder trong response công khai.

Với 401, có thể dùng WWW-Authenticate: Bearer và error code phù hợp. Tránh trả thông tin giúp kẻ tấn công phân biệt quá chi tiết giữa token không tồn tại, token bị thu hồi, chữ ký sai hoặc issuer không hợp lệ nếu chính sách bảo mật không cho phép.

## 17. Kiểm tra OpenAPI và Swagger UI

Sau khi khai báo OAuth2/OIDC security scheme, lấy tài liệu:

~~~bash
curl -sS http://localhost:8080/v3/api-docs
~~~

Kiểm tra:

1. Security scheme có đúng loại OAuth2 hoặc OpenID Connect không?
2. Token URL/authorization URL có phải endpoint công khai đúng môi trường không?
3. Các scope được khai báo có đúng tên và mô tả không?
4. Operation có yêu cầu đúng scope không?
5. Không có token thật trong example, examples, description hoặc extension?
6. Không có issuer nội bộ hoặc URL staging bị công bố nhầm trong tài liệu public?
7. Security requirement có khớp với Spring Security runtime không?

Swagger UI có thể hỗ trợ thao tác Authorize và thử request, nhưng không nên nhập token production vào giao diện chia sẻ hoặc máy dùng chung. Nếu bật persistence, xem lại chính sách lưu trạng thái authorization ở browser; ưu tiên token test ngắn hạn và profile trình duyệt riêng.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| MockMvc test scope đạt nhưng token thật vẫn bị từ chối | jwt() bỏ qua signature/issuer/audience/timestamp decoder | Thêm integration test gửi bearer token qua decoder thật với khóa test |
| Token hợp lệ nhưng nhận 403 | Authority converter không ánh xạ claim thành SCOPE_... như policy yêu cầu | Kiểm tra claim scope/scp và JwtAuthenticationConverter |
| Token hết hạn vẫn được chấp nhận trong một khoảng | Clock skew cho phép sai lệch thời gian | Kiểm tra cấu hình clock skew và đồng bộ clock |
| Token chưa tới nbf bị từ chối/được chấp nhận sai | Validator hoặc clock skew không đúng dự kiến | Test biên nbf với Clock cố định |
| ID token gọi được API | Resource server chỉ kiểm tra chữ ký mà chưa kiểm tra audience/type phù hợp | Ràng buộc audience và chính sách loại token |
| Scope trong tài liệu đúng nhưng runtime không chặn | OpenAPI chỉ mô tả, chưa cấu hình authorization | Test Spring Security authority/method security |
| Token xuất hiện trong CI log | Header hoặc exception bị log nguyên văn | Redact Authorization và token fields tại mọi lớp |
| Test token hết hạn thất thường | Phụ thuộc đồng hồ thật hoặc token có thời hạn ngắn | Dùng Clock cố định và thời điểm xác định |
| Test refresh token dùng lại token cũ thành công | Chưa kiểm tra rotation/reuse policy | Bổ sung test theo hành vi authorization server |

## 19. Quy trình kiểm thử an toàn

Khi xây dựng test cho OAuth2/OIDC:

1. Xác định vai trò đang kiểm thử: authorization server, OAuth2 client hay resource server.
2. Chọn đúng loại token: access token cho API, ID token cho đăng nhập OIDC, refresh token cho token endpoint.
3. Dùng token giả và subject tổng hợp; không lấy credential production.
4. Test scope/authority bằng MockMvc jwt() để kiểm tra authorization logic.
5. Test exp, nbf, issuer và audience bằng validator/unit test có Clock cố định.
6. Test chữ ký, JWKS và bearer filter chain bằng khóa/issuer test riêng.
7. Test OIDC nonce/audience/issuer ở client flow; test refresh rotation tại authorization server.
8. Kiểm tra OpenAPI scheme, scopes và requirement được sinh đúng.
9. Redact token ở log, trace, CI report, fixture và ví dụ tài liệu.
10. Phân biệt kết quả test mock với kết quả xác minh token thực.

Một bộ test tốt phải xác nhận cả quyền được cấp lẫn quyền bị từ chối, thời điểm token có hiệu lực và việc server chỉ tin token dành cho chính nó. Khi dùng dữ liệu giả, khóa test và redaction nhất quán, nhóm phát triển có thể kiểm tra OAuth2/OIDC sâu mà không đưa thông tin nhạy cảm vào tài liệu hoặc pipeline.

## Tài liệu tham khảo

- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [OpenID Connect Core – ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [RFC 7519 – JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6749 – OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
