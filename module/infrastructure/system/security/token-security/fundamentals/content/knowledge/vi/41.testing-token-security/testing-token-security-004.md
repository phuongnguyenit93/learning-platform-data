# Test audience mismatch

## Mục tiêu

Một access token có chữ ký hợp lệ vẫn có thể bị dùng sai dịch vụ nếu resource server không kiểm tra audience. Bài học này hướng dẫn xây dựng kiểm thử để chứng minh API chỉ chấp nhận token được phát hành cho chính API đó.

Sau bài này, bạn có thể:

- Giải thích vì sao kiểm tra chữ ký và issuer chưa đủ nếu thiếu kiểm tra `aud`.
- Xây dựng test case cho audience đúng, sai, thiếu, nhiều giá trị và sai định dạng.
- Phân biệt lỗi audience với lỗi chữ ký, issuer, thời hạn, token type và scope.
- Kiểm thử cả JWT access token và opaque access token qua introspection.
- Xác minh token sai audience bị từ chối trước khi controller, service hoặc database thực hiện tác vụ.
- Kiểm tra cấu hình audience thực tế của từng resource server trong môi trường triển khai.

## 1. Vì sao phải kiểm thử audience mismatch?

Claim `aud` (audience) chỉ ra bên nhận mà token được phát hành cho. Với OAuth 2.0, resource server phải xác minh access token được gửi đến nó là token dành cho tài nguyên đó theo hợp đồng phát hành token.

Ví dụ một hệ thống có hai API:

| Resource server | Audience được chấp nhận |
| --- | --- |
| `orders-api` | `orders-api` |
| `billing-api` | `billing-api` |

Authorization server phát hành hai access token cùng một issuer:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "billing-api",
  "scope": "billing:read",
  "exp": 1893459600
}
~~~

Token trên có thể được ký đúng, chưa hết hạn và được phát hành bởi issuer tin cậy. Tuy nhiên, khi gửi đến `orders-api`, nó phải bị từ chối vì `billing-api` không phải audience được API này chấp nhận.

Nếu `orders-api` chỉ kiểm tra chữ ký và `iss`, token dành cho dịch vụ khác có thể được dùng nhầm tại đây. Đây là dạng **token substitution** và có thể dẫn đến **confused deputy**: API dùng quyền của chính nó để xử lý một token không dành cho nó.

Kiểm thử audience vì vậy phải chứng minh đồng thời hai điều:

1. Token hợp lệ về mật mã và danh tính issuer vẫn bị từ chối khi audience không đúng.
2. Việc từ chối xảy ra trước khi API thực hiện hành động nghiệp vụ hoặc truy cập dữ liệu.

### Chữ ký, issuer, audience và scope trả lời các câu hỏi khác nhau

| Kiểm tra | Câu hỏi | Khi thất bại |
| --- | --- | --- |
| Chữ ký | Token có được ký bằng khóa được tin cậy của issuer không? | Token không hợp lệ |
| `iss` | Token có đến từ đúng nhà phát hành không? | Token không hợp lệ |
| `aud` | Token có được phát hành cho resource server hiện tại không? | Token không hợp lệ tại API này |
| `exp` / `nbf` | Token có nằm trong khoảng thời gian hiệu lực không? | Token không hợp lệ |
| Token type/profile | Đây có phải loại token API chấp nhận không? | Token không hợp lệ |
| `scope` / role | Chủ thể có quyền thực hiện thao tác này không? | Đã xác thực nhưng thiếu quyền |

Không được dùng test scope để thay thế test audience. Một token có `orders:read` nhưng audience là `billing-api` vẫn phải bị từ chối tại `orders-api`.

## 2. Xác định hợp đồng audience trước khi viết test

Test chỉ có ý nghĩa khi expected audience lấy từ hợp đồng cấu hình của resource server. Ví dụ:

~~~text
RESOURCE_SERVER = orders-api
TRUSTED_ISSUER = https://identity.example.test
ACCEPTED_AUDIENCES = ["orders-api"]
REQUIRED_TOKEN_PROFILE = OAuth 2.0 access token
~~~

Các nguyên tắc cần cố định:

- **Expected audience thuộc cấu hình server.** Không lấy giá trị mong đợi từ header `X-Audience`, query parameter, hostname tùy ý hoặc claim do request cung cấp.
- **So khớp chính xác.** Không dùng substring, prefix, case-insensitive comparison hoặc tự chuẩn hóa URI nếu hợp đồng không quy định.
- **Xử lý cả hai dạng chuẩn của JWT:** `aud` có thể là một chuỗi hoặc một mảng chuỗi. Khi API chấp nhận nhiều audience, đối chiếu theo tập giá trị.
- **Không mặc định mọi audience đều là tenant.** Audience thường xác định resource server; tenant là một quyết định chính sách khác.
- **Quy định rõ chính sách nhiều audience.** Theo ngữ nghĩa JWT, một token có thể có nhiều bên nhận. Nếu API chấp nhận token khi tập `aud` chứa `orders-api`, một phần tử hợp lệ trong mảng là đủ. Chỉ từ chối mảng có thêm audience khi hệ thống có chính sách riêng yêu cầu một audience duy nhất.
- **Phân biệt API và OAuth client.** `client_id` hoặc `azp` không tự động thay thế `aud` của resource server.

Trong JWT Access Token Profile của OAuth 2.0 (RFC 9068), claim `aud` là bắt buộc. Với profile hoặc nhà phát hành khác, kiểm tra tính bắt buộc và định dạng theo hợp đồng token cụ thể. Resource server vẫn phải có chính sách audience rõ ràng.

## 3. Ma trận kiểm thử audience

Giả định API đang kiểm thử là `orders-api`. Các test âm nên dùng token có chữ ký hợp lệ, issuer đúng, thời hạn hợp lệ và đúng token profile; **chỉ thay audience** để cô lập nguyên nhân thất bại.

| ID | Giá trị `aud` trong token | Kết quả tại orders-api | Mục đích |
| --- | --- | --- | --- |
| A01 | `"orders-api"` | Chấp nhận qua bước audience | Dạng chuỗi đúng |
| A02 | `["orders-api"]` | Chấp nhận qua bước audience | Mảng một phần tử |
| A03 | `["profile-api", "orders-api"]` | Chấp nhận nếu chính sách cho phép nhiều audience | API nằm trong mảng |
| A04 | `"billing-api"` | 401 | Audience thuộc API khác |
| A05 | `["billing-api", "profile-api"]` | 401 | Mảng không chứa API hiện tại |
| A06 | Không có `aud` | 401 nếu audience là bắt buộc | Thiếu claim |
| A07 | `[]` hoặc giá trị rỗng | 401 | Không có bên nhận hợp lệ |
| A08 | `"Orders-API"` | 401 nếu hợp đồng phân biệt hoa/thường | Sai khác ký tự |
| A09 | `"orders-api.example"` | 401 | Chuỗi gần giống nhưng không khớp |
| A10 | `"api"` khi expected là `"orders-api"` | 401 | Không được so khớp substring |
| A11 | `"https://api.example.test/orders"` | Theo đúng định danh cấu hình | Không tự bỏ slash hoặc đổi URL |
| A12 | `["orders-api", "billing-api"]` | Theo chính sách nhiều audience đã công bố | Xác minh hành vi rõ ràng, tránh vô tình thay đổi |
| A13 | Audience là client ID của ứng dụng web | 401 tại API nếu không phải audience API | Ngăn nhầm ID token/client token |
| A14 | Audience đúng nhưng token hết hạn | 401 | Test thời hạn riêng |
| A15 | Audience đúng nhưng chữ ký sai | 401 | Test chữ ký riêng |

Với A03 và A12, không nên viết kỳ vọng dựa trên thứ tự phần tử. `aud` là một tập người nhận về mặt ý nghĩa; API phải tìm audience được chấp nhận theo chính sách, không chỉ đọc phần tử đầu tiên.

### Tách test audience khỏi các lỗi xác thực khác

Để test A04 thực sự chứng minh audience validator hoạt động:

- Dùng issuer nằm trong allowlist.
- Ký token bằng private key tương ứng với public key mà test resource server tin cậy.
- Đặt `iat`, `nbf` (nếu có) và `exp` hợp lệ theo đồng hồ test.
- Dùng đúng token type/profile mà API yêu cầu.
- Cấp scope phù hợp để loại bỏ lỗi authorization không liên quan.
- Chỉ thay `aud` từ `orders-api` thành `billing-api`.

Nếu token đồng thời sai chữ ký và sai audience, test chỉ chứng minh token bị từ chối; nó không chứng minh audience check đã chạy.

## 4. Unit test cho audience validator

Ở tầng unit, kiểm tra logic đối chiếu claim mà không cần gọi mạng hoặc tạo khóa thật. Ví dụ dưới đây dùng Spring Security Resource Server. Validator được gọi sau khi decoder đã xác minh JWT; nó chỉ chịu trách nhiệm kiểm tra audience.

### Validator

~~~java
import java.util.List;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

final class AudienceValidator implements OAuth2TokenValidator<Jwt> {

    private final String expectedAudience;

    AudienceValidator(String expectedAudience) {
        if (expectedAudience == null || expectedAudience.isBlank()) {
            throw new IllegalArgumentException("Expected audience is required");
        }
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        List<String> audiences = jwt.getAudience();

        if (audiences != null && audiences.contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            OAuth2ErrorCodes.INVALID_TOKEN,
            "Required audience is missing",
            null
        );
        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

Validator này dùng so sánh chuỗi chính xác qua `contains`. Không kiểm tra chữ ký ở đây vì nhiệm vụ đó thuộc `JwtDecoder`. Không ghi giá trị token vào thông báo lỗi.

### Unit test

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

class AudienceValidatorTest {

    private final AudienceValidator validator =
        new AudienceValidator("orders-api");

    private Jwt tokenWithAudience(List<String> audiences) {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");

        return Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .issuer("https://identity.example.test")
            .subject("user-42")
            .audience(audiences)
            .issuedAt(now.minusSeconds(30))
            .expiresAt(now.plusSeconds(300))
            .claim("scope", "orders:read")
            .build();
    }

    @Test
    void acceptsExpectedAudience() {
        var result = validator.validate(
            tokenWithAudience(List.of("orders-api"))
        );

        assertThat(result.hasErrors()).isFalse();
    }

    @Test
    void acceptsExpectedAudienceInArray() {
        var result = validator.validate(
            tokenWithAudience(List.of("profile-api", "orders-api"))
        );

        assertThat(result.hasErrors()).isFalse();
    }

    @Test
    void rejectsDifferentAudience() {
        var result = validator.validate(
            tokenWithAudience(List.of("billing-api"))
        );

        assertThat(result.hasErrors()).isTrue();
    }

    @Test
    void rejectsAudienceWithSimilarButDifferentText() {
        var result = validator.validate(
            tokenWithAudience(List.of("orders-api.example"))
        );

        assertThat(result.hasErrors()).isTrue();
    }

    @Test
    void rejectsEmptyAudience() {
        var result = validator.validate(tokenWithAudience(List.of()));

        assertThat(result.hasErrors()).isTrue();
    }
}
~~~

Các test trên kiểm tra validator với một đối tượng `Jwt` đã được tạo sẵn. Chúng **không** chứng minh chữ ký, issuer, thời gian hoặc cấu hình decoder hoạt động. Những phần đó cần integration test riêng.

### Kết hợp validator với decoder

Ví dụ cấu hình Spring Security:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(trustedIssuer);

    OAuth2TokenValidator<Jwt> audience =
        new AudienceValidator("orders-api");

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTime,
            audience
        )
    );

    return decoder;
}
~~~

Cấu hình thực tế cần lấy `trustedIssuer`, JWKS URI và audience từ cấu hình được quản trị. Không lấy các giá trị này từ request hoặc token. Nếu hệ thống đã có validator riêng cho access token profile, giữ chúng trong chuỗi validator và bảo đảm audience validator cũng được gọi.

## 5. Integration test: chứng minh resource server từ chối token sai audience

Unit test không đủ để chứng minh API đang chạy thực sự sử dụng audience validator. Integration test cần đi qua luồng xác thực thật:

~~~mermaid
flowchart TD
    A["Test tạo access token có chữ ký"] --> B["Gửi request Bearer đến API"]
    B --> C["JwtDecoder xác minh chữ ký và issuer"]
    C --> D["Kiểm tra thời gian và token profile"]
    D --> E["Audience validator"]
    E --> F{"aud chứa orders-api?"}
    F -- "Không" --> G["401 invalid_token"]
    F -- "Có" --> H["Tạo Authentication"]
    H --> I["Kiểm tra scope/role"]
    I --> J["Controller và service"]
~~~

Test phải dùng cấu hình xác thực gần với production nhất có thể:

1. Tạo cặp khóa test riêng; ký JWT bằng private key và cung cấp public key qua JWKS test endpoint hoặc cấu hình decoder test.
2. Giữ issuer, thời hạn, token type và chữ ký giống nhau giữa hai token.
3. Tạo token thứ nhất có `aud=orders-api` và token thứ hai có `aud=billing-api`.
4. Gửi cả hai token đến cùng endpoint của `orders-api`.
5. Xác minh token đúng audience đi qua bước xác thực; token sai audience nhận 401.
6. Xác minh controller/service không chạy với token sai audience.

Ví dụ kiểm thử endpoint (phần tạo JWT được trừu tượng hóa trong fixture):

~~~java
@Test
void rejectsTokenIssuedForBillingApi() throws Exception {
    String token = tokenFixture.validAccessToken()
        .withAudience("billing-api")
        .signWithTrustedTestKey();

    mockMvc.perform(get("/api/orders")
            .header("Authorization", "Bearer " + token))
        .andExpect(status().isUnauthorized());

    verify(orderService, never()).listOrders(any());
}

@Test
void acceptsTokenIssuedForOrdersApi() throws Exception {
    String token = tokenFixture.validAccessToken()
        .withAudience("orders-api")
        .withScope("orders:read")
        .signWithTrustedTestKey();

    mockMvc.perform(get("/api/orders")
            .header("Authorization", "Bearer " + token))
        .andExpect(status().isOk());

    verify(orderService).listOrders(any());
}
~~~

Các phương thức `tokenFixture` ở đây là helper giả định của bộ test; cần triển khai bằng thư viện JWT đang dùng và khóa test. Không đưa private key production hoặc access token thật vào test fixture.

### Kiểm tra response và side effect

Với bearer token không hợp lệ, API thường trả 401 và có thể phát header `WWW-Authenticate: Bearer error="invalid_token"` theo RFC 6750. Không phụ thuộc vào thông báo lỗi chi tiết do thư viện tạo ra; nội dung phản hồi nên tránh tiết lộ issuer, key ID hoặc token.

Ngoài status code, cần kiểm tra:

- Controller không được gọi.
- Service nghiệp vụ không được gọi.
- Không có bản ghi được tạo/cập nhật/xóa.
- Không phát event hoặc message chứa tác vụ nghiệp vụ.
- Không ghi token nguyên văn vào log.
- Không tạo cache entry hoặc session gắn với danh tính từ token bị từ chối.

Một API trả 401 sau khi đã ghi dữ liệu vẫn là lỗi bảo mật. Vì vậy, test phải quan sát side effect chứ không chỉ so sánh HTTP status.

## 6. Phân biệt 401 audience mismatch và 403 thiếu quyền

Hai tình huống sau phải có kỳ vọng khác nhau:

| Token | Audience | Scope | Kết quả |
| --- | --- | --- | --- |
| Token A | `billing-api` | `orders:read` | 401: token không dành cho orders-api |
| Token B | `orders-api` | `orders:read` | Có thể cho phép đọc |
| Token C | `orders-api` | Chỉ `orders:read`, gọi thao tác ghi | 403: thiếu quyền ghi |
| Token D | `orders-api` | Đủ scope nhưng hết hạn | 401: token hết hiệu lực |

Test authorization chỉ có ý nghĩa sau khi token đã qua xác thực. Đừng sửa audience sai thành 403 chỉ để tránh lộ thông tin; hãy tuân theo hợp đồng bearer token của API. Có thể dùng response 404 cho một số tài nguyên để tránh tiết lộ sự tồn tại, nhưng đó là chính sách truy cập tài nguyên sau xác thực.

## 7. Kiểm thử audience của opaque access token

Opaque token không có payload JWT để resource server tự đọc. API thường gọi introspection endpoint đã cấu hình của authorization server và nhận JSON mô tả token.

Ví dụ response introspection:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test",
  "aud": ["billing-api"],
  "sub": "user-42",
  "scope": "orders:read"
}
~~~

Dù `active=true` và scope có vẻ phù hợp, token này vẫn phải bị từ chối tại `orders-api` vì audience không khớp. `active` chỉ cho biết token đang hoạt động theo authorization server; nó không tự chứng minh token dành cho API hiện tại.

Kiểm thử opaque token cần stub introspection server và bao phủ:

| Response introspection | Kết quả mong đợi |
| --- | --- |
| `active=true`, `aud` chứa `orders-api` | Qua audience check; tiếp tục kiểm tra scope |
| `active=true`, `aud=["billing-api"]` | 401 |
| `active=false` | 401 |
| `active=true` nhưng thiếu `aud` trong khi policy yêu cầu | 401 |
| `active=true`, audience đúng, thiếu scope | 403 |
| Introspection timeout hoặc lỗi server | Fail closed theo chính sách; không chấp nhận token vì không kiểm tra được |

RFC 7662 định nghĩa trường `aud` tùy chọn trong response introspection. Vì vậy, resource server phải thỏa thuận rõ với authorization server cách cung cấp audience. Nếu response không có trường cần thiết, không tự suy ra audience từ `client_id` hay scope.

Test phải bảo đảm API chỉ gọi đúng introspection endpoint đã cấu hình, xác thực kết nối theo yêu cầu và không gửi token đến URL do request chỉ định. Nếu introspection lỗi, tuyệt đối không chuyển sang chế độ bỏ qua kiểm tra audience.

## 8. Kiểm thử nhầm lẫn ID token và access token

OIDC ID token xác nhận thông tin đăng nhập cho client; access token cấp quyền truy cập resource server. Hai loại token có thể cùng là JWT và cùng chứa `iss`, `sub`, `aud`, nhưng ý nghĩa và bên nhận khác nhau.

Tạo một ID token hợp lệ có:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "web-client",
  "exp": 1893459600
}
~~~

Khi gửi token này đến `orders-api`, API phải từ chối vì audience là client ứng dụng và token không đúng access token profile mà resource server yêu cầu. Chỉ kiểm tra chữ ký và issuer không đủ để phân biệt.

Các test nên có:

- ID token hợp lệ cho web client được gửi đến API → 401.
- Access token hợp lệ cho orders-api → qua xác thực.
- Access token hợp lệ cho billing-api → 401 tại orders-api.
- Token có header/claim type không phù hợp profile đã cấu hình → 401.
- Token có claim `azp` hoặc `client_id` đúng nhưng `aud` sai → vẫn 401.

Không suy luận token type chỉ từ một claim tùy chọn nếu profile không quy định claim đó. Hãy thực hiện kiểm tra theo profile access token mà authorization server và resource server đã thống nhất.

## 9. Audience trong hệ thống nhiều API và multi-tenant

Trong kiến trúc có gateway và nhiều microservice, mỗi resource server cần xác định audience của chính nó. Ví dụ:

~~~text
Browser → API Gateway → Orders API → Inventory API
             gateway-api   orders-api   inventory-api
~~~

Một token có audience `gateway-api` không tự động phù hợp với `orders-api` hoặc `inventory-api`. Nếu service phía sau cần danh tính người dùng, hệ thống nên dùng cơ chế ủy quyền/token exchange hoặc token dành cho resource server đích theo kiến trúc OAuth đã chọn. Không chuyển tiếp bearer token đến mọi dịch vụ chỉ vì gateway đã xác thực thành công.

Đối với multi-tenant, kiểm thử thêm các cặp issuer/audience:

| Issuer đã xác thực | Audience | Tenant policy | Kết quả |
| --- | --- | --- | --- |
| Issuer Acme | `orders-api` | Ánh xạ Acme + orders-api | Chấp nhận nếu quyền hợp lệ |
| Issuer Acme | `billing-api` | Đang gọi orders-api | 401 |
| Issuer Beta | `orders-api` | Ánh xạ Beta + orders-api | Tiếp tục kiểm tra tenant và quyền |
| Issuer Acme | `orders-api-beta` | Không có cặp hợp lệ | 401 |
| Issuer chung | `orders-api` | Không có claim/quan hệ phân biệt tenant | Không được tự chọn tenant |

Test audience và test tenant phải tách lớp nhưng phối hợp trong integration suite. Audience xác nhận resource server được phép nhận token; tenant policy xác định vùng dữ liệu và quyền của chủ thể. Không dùng một kết quả đúng audience để bỏ qua tenant membership hoặc resource authorization.

## 10. Kiểm thử cấu hình và vận hành

Nhiều lỗi audience xuất phát từ cấu hình môi trường:

- Production cấu hình `orders-api` nhưng staging vô tình dùng `billing-api`.
- Gateway chuyển token đến service khác với audience ban đầu.
- Authorization server đổi audience khi thay client/resource registration.
- Một service chấp nhận audience mặc định quá rộng như `api`.
- Biến môi trường audience rỗng khiến validator bị bỏ qua hoặc cấu hình fallback không an toàn.

Bổ sung các kiểm tra sau vào pipeline và deployment:

1. **Fail fast khi cấu hình thiếu:** Khởi động ứng dụng phải thất bại nếu expected audience rỗng, thiếu hoặc không hợp lệ.
2. **Kiểm tra cấu hình theo môi trường:** Xác minh mỗi deployment có audience đúng với resource server tương ứng.
3. **Contract test với issuer:** Dùng token test được phát hành theo cấu hình tích hợp để xác minh giá trị `aud` thực tế.
4. **Test sau thay đổi IdP:** Khi thay client, resource indicator, API identifier hoặc scope, chạy lại ma trận audience.
5. **Kiểm tra JWKS rotation:** Xác minh token được ký bằng khóa mới vẫn qua chữ ký và audience; token sai audience vẫn bị từ chối. Không nới audience để khắc phục lỗi khóa.
6. **Kiểm tra cache:** Nếu có cache kết quả introspection hoặc authentication, bảo đảm cache key và TTL không khiến kết quả hợp lệ của API này được tái sử dụng cho API khác.
7. **Kiểm tra log/metric:** Ghi nhận lý do từ chối như `invalid_audience` cùng service và correlation ID; không log raw token hoặc claims nhạy cảm.

Không cần ghi toàn bộ giá trị audience của token vào log nếu điều đó làm lộ thông tin nội bộ. Có thể ghi expected resource identifier và mã lỗi đã chuẩn hóa.

## 11. Checklist hoàn tất bộ test

- [ ] Có expected audience cố định từ cấu hình resource server.
- [ ] Có test audience đúng ở cả dạng chuỗi và mảng.
- [ ] Có test audience sai, thiếu, rỗng và chuỗi gần giống.
- [ ] Có test nhiều audience theo đúng chính sách được công bố.
- [ ] Test negative dùng chữ ký, issuer, thời gian và token profile hợp lệ; chỉ thay audience.
- [ ] Có test tích hợp đi qua decoder/validator thật.
- [ ] Có test token dành cho API khác và ID token gửi đến API.
- [ ] Có test opaque token qua introspection nếu hệ thống hỗ trợ.
- [ ] Token sai audience nhận kết quả từ chối phù hợp và không tạo side effect.
- [ ] Token đúng audience nhưng thiếu scope được phân loại là lỗi authorization.
- [ ] Mỗi microservice kiểm tra audience của chính nó.
- [ ] Cấu hình thiếu hoặc sai audience khiến deployment/test thất bại rõ ràng.
- [ ] Log không chứa bearer token hoặc refresh token nguyên văn.

## Ghi nhớ

- Chữ ký hợp lệ và issuer đúng **không thay thế** kiểm tra audience.
- Audience mismatch là lỗi token tại resource server hiện tại; thông thường trả 401 với bearer error `invalid_token`.
- Unit test kiểm tra logic validator; integration test chứng minh decoder và endpoint thực sự áp dụng validator.
- Token sai audience phải bị chặn trước controller, service, database và các side effect.
- Với opaque token, kiểm tra audience từ introspection response theo hợp đồng đã cấu hình; `active=true` không đủ.
- Mỗi API và mỗi tenant policy cần ràng buộc audience rõ ràng để ngăn token substitution và truy cập nhầm tài nguyên.

### Tiêu chuẩn tham khảo

- **RFC 7519 — JSON Web Token:** định nghĩa claim `aud` và dạng biểu diễn audience.
- **RFC 8725 — JSON Web Token Best Current Practices:** các biện pháp tránh nhầm lẫn token, issuer và audience.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách resource server phản hồi lỗi bearer token, bao gồm `invalid_token`.
- **RFC 7662 — OAuth 2.0 Token Introspection:** response introspection và trường `aud`.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile JWT access token và yêu cầu audience.
- **OpenID Connect Core:** vai trò của ID token và audience của client.
