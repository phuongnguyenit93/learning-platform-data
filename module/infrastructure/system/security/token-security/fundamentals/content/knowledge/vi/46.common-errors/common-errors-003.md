# Bỏ qua issuer hoặc audience

> **Chương:** Lỗi thường gặp  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS  
> **Bối cảnh:** Mô hình tin cậy và vòng đời token bảo mật; phân biệt JWT, opaque token, access token, refresh token và OAuth 2.0/OIDC; kiểm tra claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của **issuer (iss)** và **audience (aud)** trong việc xác định nguồn phát hành và nơi được phép nhận token.
2. Phân tích rủi ro khi API chỉ kiểm tra chữ ký hoặc thời hạn mà bỏ qua issuer/audience.
3. Phân biệt audience của access token với audience của OIDC ID token và client ID.
4. Xây dựng kiểm tra issuer/audience cho JWT và opaque token theo cấu hình tin cậy.
5. Thiết kế trust allowlist khi một resource server nhận token từ nhiều Authorization Server.
6. Kiểm thử token sai issuer, sai audience, nhiều audience, token exchange, key rotation và lỗi cấu hình ở API gateway/Spring Security.

## 1. Vì sao không được bỏ qua issuer hoặc audience?

Trong OAuth 2.0/OIDC, token là bằng chứng được phát hành trong một **ranh giới tin cậy** và cho một **ngữ cảnh sử dụng**. Hai claim quan trọng giúp resource server xác định ranh giới đó:

- **Issuer (iss):** ai đã phát hành token.
- **Audience (aud):** token được dự định gửi tới resource server hoặc đối tượng nhận nào.

Một API có thể xác minh chữ ký JWT thành công nhưng vẫn chấp nhận nhầm token được phát hành bởi một issuer khác hoặc token vốn dành cho một API khác. Khi bỏ qua issuer hoặc audience, chữ ký hợp lệ không còn đủ để chứng minh token phù hợp với API đang xử lý request.

Ví dụ:

- Orders API tin cậy token do Authorization Server của doanh nghiệp phát hành và chỉ nhận token có audience là orders-api.
- Inventory API cũng nằm trong cùng mạng nội bộ nhưng có audience riêng là inventory-api.
- Một token hợp lệ dành cho Inventory API bị gửi sang Orders API.
- Nếu Orders API chỉ kiểm tra chữ ký và exp, nó có thể chấp nhận token không được cấp cho mình.

~~~mermaid
flowchart TD
    T["JWT có chữ ký hợp lệ"] --> I{"Issuer có nằm trong trust allowlist?"}
    I -->|Không| D1["Từ chối"]
    I -->|Có| A{"Audience có chứa API hiện tại?"}
    A -->|Không| D2["Từ chối"]
    A -->|Có| X["Kiểm tra exp, nbf, scope,<br/>token profile và authorization"]
    X -->|Hợp lệ| P["Cho phép tiếp tục"]
    X -->|Không hợp lệ| D3["Từ chối"]
~~~

**Chữ ký hợp lệ chỉ chứng minh token được ký bằng một khóa tương ứng.** Resource server vẫn phải xác minh issuer và audience để xác định khóa đó thuộc đúng nguồn tin cậy và token được phát hành cho đúng API.

## 2. Issuer (iss) xác định nguồn tin cậy

Issuer là định danh của bên phát hành token, thường là Authorization Server hoặc OpenID Provider. Ví dụ:

~~~json
{
  "iss": "https://identity.example.com/realms/workforce"
}
~~~

Resource server cần biết chính xác issuer nào được phép phát hành token cho nó. Cấu hình issuer thường liên kết với metadata discovery hoặc cấu hình Authorization Server, JWKS URI, introspection endpoint, quy tắc mapping claim và chính sách token.

### So sánh issuer chính xác

Giá trị issuer là định danh có semantics chính xác theo token profile. Không tùy tiện biến đổi chuỗi trước khi so sánh. Ví dụ các giá trị sau phải được xem là khác nhau nếu cấu hình issuer không xác nhận chúng tương đương:

- https://identity.example.com
- https://identity.example.com/
- https://identity.example.com/realms/workforce
- https://identity.example.com/realms/partners

Không tự bỏ dấu slash, đổi chữ hoa/thường, bỏ path hoặc chuẩn hóa URL theo ý muốn. JWT StringOrURI values được so sánh theo semantics phân biệt chữ hoa/thường; hãy dùng issuer identifier chính xác đã cấu hình.

### Không tin issuer chưa xác minh để tìm khóa tùy ý

Một lỗi nguy hiểm là đọc claim iss từ JWT chưa xác minh rồi tự động tải discovery metadata hoặc JWKS từ URL đó. Attacker có thể tạo token giả với iss trỏ đến server do họ kiểm soát, sau đó cung cấp key để ký token giả.

Quy tắc an toàn:

1. Có danh sách issuer được phép từ cấu hình tin cậy.
2. Ánh xạ issuer đã cấu hình tới metadata/JWKS hoặc introspection endpoint tương ứng.
3. Chỉ dùng token iss như một giá trị cần so khớp với issuer đã chọn.
4. Không theo jku, x5u hoặc URL do token tự khai để tải khóa nếu không có policy tin cậy rõ ràng.
5. Nếu hỗ trợ nhiều issuer, mỗi issuer phải có trust configuration và validation policy riêng.

Issuer không phải tên hiển thị. Nó là một phần của ranh giới bảo mật.

## 3. Audience (aud) xác định nơi được phép nhận token

Audience cho biết token được dự định sử dụng bởi resource server hoặc đối tượng nhận nào. Ví dụ access token dành cho Orders API:

~~~json
{
  "iss": "https://identity.example.com/realms/workforce",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Orders API cần xác minh audience có chứa identifier được cấu hình cho chính nó. Inventory API không được chấp nhận token này chỉ vì cùng tin issuer đó.

### Audience có thể là chuỗi hoặc mảng

Theo JWT, aud có thể là một StringOrURI hoặc một mảng các giá trị StringOrURI. Ví dụ:

~~~json
{
  "aud": "orders-api"
}
~~~

Hoặc:

~~~json
{
  "aud": ["orders-api", "reporting-api"]
}
~~~

Resource server cần kiểm tra identifier của mình có nằm trong tập audience được phép hay không. Nếu token có nhiều audience, việc chấp nhận phải phù hợp với policy và token profile; không tự suy ra rằng mọi API trong hệ thống đều được phép nhận token đó.

### Audience không đồng nghĩa client_id

- **client_id** định danh OAuth client đang yêu cầu token hoặc đã được xác thực.
- **aud** định danh resource server hoặc recipient được token hướng tới.
- **sub** định danh subject mà token đại diện.
- **azp** trong một số OIDC ID token biểu diễn authorized party.

Ví dụ token do orders-service yêu cầu có thể có client_id là orders-service nhưng audience là inventory-api. API đích phải kiểm tra audience của chính nó, không so sánh aud với client_id một cách máy móc.

## 4. Hậu quả khi bỏ qua issuer

Nếu API không kiểm tra issuer, các tình huống sau có thể xảy ra:

1. **Token từ issuer ngoài trust boundary:** API chấp nhận token do Authorization Server không được tổ chức tin cậy phát hành.
2. **Issuer confusion:** hai hệ thống có cấu trúc claim giống nhau nhưng cấp quyền theo policy khác nhau.
3. **Subject collision:** cùng chuỗi sub ở hai issuer có thể đại diện cho hai danh tính khác nhau; bỏ iss khiến hệ thống nhầm hai chủ thể.
4. **Key confusion:** verifier chọn nhầm key hoặc cấu hình issuer không đúng với token.
5. **Tenant/realm confusion:** token từ realm hoặc tenant identity khác được chấp nhận như token của realm hiện tại.
6. **Federation bypass:** token từ một identity provider không được phê duyệt có thể đi vào API chỉ vì chữ ký hợp lệ.

### Ví dụ subject collision

Issuer A và issuer B đều phát hành token có sub=alice. Nhưng Alice ở issuer A là nhân viên nội bộ, còn Alice ở issuer B là người dùng đối tác. Nếu hệ thống chỉ dùng sub để tìm tài khoản, hai danh tính có thể bị nhập nhằng.

Một định danh subject thường phải được hiểu trong ngữ cảnh issuer. Khi lưu liên kết danh tính hoặc audit, dùng cặp issuer + subject, hoặc một internal principal ID đã được ánh xạ an toàn.

## 5. Hậu quả khi bỏ qua audience

Nếu API không kiểm tra audience, token dành cho một resource có thể bị sử dụng ở resource khác:

- Token dành cho Inventory API được gửi sang Orders API.
- Token dành cho API staging được gửi sang production API nếu issuer/key dùng chung và verifier không phân biệt audience.
- Token có scope rộng ở một API được dùng làm bearer token ở API không nằm trong intended recipient.
- Một token được cấp cho client frontend hoặc OIDC client bị nhầm là access token dành cho backend API.

Điều này tạo điều kiện cho **cross-service token replay**, confused deputy và mở rộng phạm vi ảnh hưởng khi bearer token bị đánh cắp.

### Scope không thay thế audience

Scope mô tả quyền được cấp, còn audience xác định nơi token được dự định sử dụng. Một token có scope orders.read vẫn không nên được chấp nhận ở API không nằm trong audience, dù tên scope có vẻ liên quan.

Tương tự, audience đúng không chứng minh caller có đủ quyền. Sau khi kiểm tra issuer và audience, API vẫn phải kiểm tra scope, role, subject, actor, tenant và quyền trên tài nguyên.

~~~mermaid
flowchart LR
    A["Issuer đúng"] --> B["Audience đúng"]
    B --> C["Token còn hiệu lực"]
    C --> D["Scope/authority đủ"]
    D --> E["Object-level authorization"]
    E --> F["Thực thi nghiệp vụ"]
~~~

Các bước này bổ sung cho nhau. Không bỏ qua một bước chỉ vì bước khác đã thành công.

## 6. Phân biệt access token và OIDC ID token

Một lỗi phổ biến là gửi **ID token** đến API như thể đó là access token.

ID token được OpenID Connect phát hành cho OIDC client để cung cấp thông tin xác thực đăng nhập. Audience của ID token thường là client_id của ứng dụng đăng nhập. Access token được cấp để gọi resource server; audience của nó cần phù hợp API đích theo token profile.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "alice",
  "aud": "web-portal-client",
  "nonce": "login-nonce",
  "exp": 1893456000
}
~~~

Nếu Orders API nhận ID token có aud=web-portal-client, API phải từ chối vì token không được cấp cho orders-api. Việc ID token có chữ ký hợp lệ và sub hợp lệ không biến nó thành access token.

### Kiểm tra token type/profile

- API chỉ chấp nhận access token theo profile được cấu hình.
- Không chấp nhận ID token chỉ vì JWT decode thành công.
- Nếu dùng JWT access token profile, tuân thủ profile đó, bao gồm các claim/headers bắt buộc và quy tắc validation.
- Với opaque access token, xác minh qua introspection theo resource server context.
- Không chỉ dựa vào typ header nếu token profile còn yêu cầu các kiểm tra khác.

RFC 9068 định nghĩa JWT Profile for OAuth 2.0 Access Tokens. OpenID Connect Core định nghĩa ID token. Hai loại token phục vụ mục đích khác nhau và không thể thay thế nhau tùy tiện.

## 7. Những kiểm tra cần thực hiện cho JWT access token

Một resource server nên thực hiện tối thiểu các bước sau, theo token profile và chính sách của tổ chức:

1. Nhận token từ vị trí giao thức hợp lệ, thường là Authorization: Bearer.
2. Xác định issuer từ tập cấu hình tin cậy, không tải key từ nguồn tùy ý.
3. Xác minh chữ ký bằng public key thuộc issuer đã chọn.
4. Chỉ cho phép thuật toán ký đã cấu hình.
5. So khớp iss với issuer mong đợi.
6. Xác minh aud có chứa resource identifier của API hiện tại.
7. Kiểm tra exp, nbf và các yêu cầu thời gian khác.
8. Xác minh token đúng loại/profile access token.
9. Kiểm tra scope/authority, tenant, actor và các claim cần cho authorization.
10. Áp dụng quyền trên resource cụ thể và ghi audit event an toàn.

### JWT validation không phải chỉ decode

JWT thường có dạng header.payload.signature. Base64URL decode header/payload chỉ giúp đọc dữ liệu; nó không xác minh tính toàn vẹn hay nguồn phát hành. Không dùng thư viện decode-only để quyết định authorization.

### Kiểm tra thuật toán và key ID

Không chấp nhận thuật toán do token tự chọn nếu không nằm trong allowlist. Cấu hình thuật toán phải phù hợp key type và token issuer. Không cho phép fallback sang none hoặc thuật toán yếu chỉ để token validation không báo lỗi.

kid giúp chọn key trong JWKS đã tin cậy của issuer. kid không chứng minh issuer, không chứng minh audience và không cho phép verifier tải key từ URL tùy ý. Nếu kid không tìm thấy, có thể refresh JWKS theo cơ chế an toàn rồi từ chối nếu vẫn không có key phù hợp.

## 8. JWT có nhiều issuer: chọn đúng trust configuration

Một resource server có thể nhận token từ nhiều Authorization Server, ví dụ identity provider nội bộ, identity provider đối tác, authorization server riêng cho workload hoặc realm riêng cho từng nhóm người dùng.

Không nên tạo một validator quá rộng chấp nhận mọi issuer cùng một bộ claim. Mỗi issuer có thể có JWKS URI, key rotation, audience/resource, subject mapping, scope naming, token profile và quy trình revoke khác nhau.

### Quy trình multi-issuer an toàn

~~~mermaid
flowchart TD
    T["Incoming token"] --> R["Resolve candidate issuer<br/>from configured allowlist"]
    R --> A{"Issuer đã đăng ký?"}
    A -->|Không| D["Reject"]
    A -->|Có| K["Load only that issuer's<br/>trusted metadata and keys"]
    K --> V["Verify signature + exact iss"]
    V --> U["Validate audience and token profile"]
    U --> P["Apply issuer-specific<br/>scope and authorization policy"]
~~~

Trong triển khai multi-issuer, issuer resolution có thể cần đọc claim iss trước khi xác minh để chọn candidate configuration. Giá trị đó chỉ được dùng để tra trong **allowlist tĩnh hoặc registry tin cậy**; sau đó verifier phải xác minh chữ ký và kiểm tra iss khớp chính xác với issuer của configuration đã chọn. Không dùng untrusted iss để tạo trust mới hoặc tải metadata từ host bất kỳ.

Nếu hai issuer cùng phát hành sub=12345, không coi đó là cùng một principal trừ khi identity mapping có chủ đích. Khóa định danh có thể là issuer + subject hoặc internal user ID đã được xác minh.

## 9. Kiểm tra issuer và audience với Spring Security Resource Server

Khi cấu hình Spring Security bằng issuer-uri, framework có thể discovery metadata và thiết lập JWT decoder. Tuy nhiên, **không nên giả định việc cấu hình issuer-uri tự động kiểm tra audience của API**. Resource server cần thêm validator cho audience mong đợi.

Ví dụ cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/workforce
~~~

Đây là cấu hình issuer đã biết trước. Trong production, issuer URI phải đến từ cấu hình được quản lý và tin cậy, không lấy từ query/header hoặc URL trong JWT chưa xác minh.

### Audience validator

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class RequiredAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public RequiredAudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        );
        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

Validator trên kiểm tra audience chính xác đã cấu hình. Nó không tự xác minh chữ ký hoặc issuer; các việc đó do decoder và validator khác đảm nhiệm.

### Kết hợp issuer, thời gian và audience

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtSecurityConfiguration {

    private static final String ISSUER =
        "https://identity.example.com/realms/workforce";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience =
            new RequiredAudienceValidator(AUDIENCE);

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audience
            )
        );

        return decoder;
    }
}
~~~

Ví dụ này dùng issuer cố định đã cấu hình và kết hợp validator mặc định với audience validator. Tùy phiên bản Spring Security, cách khởi tạo decoder và các validator có thể khác; hãy kiểm tra API của phiên bản đang dùng.

### Các điểm cần xác minh trong cấu hình thật

- Issuer chính xác, bao gồm path và trailing slash theo metadata đã đăng ký.
- JWKS URI chỉ đến nguồn thuộc issuer đã tin cậy.
- Audience là identifier của resource server hiện tại.
- Decoder không bỏ qua validator mặc định về thời gian.
- Thuật toán được giới hạn theo policy.
- Resource server không chấp nhận ID token.
- Test xác nhận token sai issuer và sai audience đều bị từ chối.

## 10. Kiểm tra issuer/audience với opaque access token

Opaque token không thể tự decode để đọc claims. Resource server thường dùng **introspection endpoint** theo RFC 7662 để hỏi Authorization Server về trạng thái và metadata.

Một introspection response có thể chứa các trường như:

~~~json
{
  "active": true,
  "iss": "https://identity.example.com/realms/workforce",
  "sub": "alice",
  "client_id": "orders-service",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Các claim cụ thể được trả về phụ thuộc Authorization Server và profile triển khai. Resource server cần bảo đảm introspection endpoint trả metadata đủ để xác minh issuer/audience theo yêu cầu. Nếu profile không trả issuer hoặc audience, phải có ràng buộc tương đương được xác nhận trong cấu hình/resource registration; không tự suy đoán.

### Quy trình introspection

1. Resource server gửi token tới introspection endpoint qua TLS.
2. Resource server xác thực với endpoint bằng client authentication đã đăng ký.
3. Authorization Server trả metadata.
4. Resource server yêu cầu active=true.
5. Resource server xác minh issuer và audience theo contract.
6. Resource server kiểm tra scope, subject, client và authorization policy.
7. Resource server áp dụng cache theo TTL phù hợp và xử lý revoke propagation.

Nếu active=false, introspection timeout hoặc metadata cần thiết không thể xác minh, API phải từ chối theo policy. Không fallback sang chấp nhận token chỉ vì trước đây token từng hợp lệ.

### Spring opaque token

Cấu hình cơ bản có thể khai báo:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Client secret phải được inject từ secret manager hoặc cơ chế bảo mật phù hợp. Không commit secret vào repository hoặc ghi vào log. Nếu cần kiểm tra issuer/audience bổ sung, có thể bọc OpaqueTokenIntrospector để xác minh các attribute được Authorization Server trả về; cần fail closed nếu attribute bắt buộc bị thiếu.

## 11. Audience trong token exchange và service-to-service

Trong chuỗi microservices, token được cấp cho service A không tự động dùng được ở service B.

~~~mermaid
sequenceDiagram
    participant O as Orders Service
    participant AS as Authorization Server
    participant I as Inventory API

    O->>AS: Token exchange<br/>subject token + audience=inventory-api<br/>scope=inventory.read
    AS->>AS: Validate issuer, subject, actor<br/>and exchange policy
    AS-->>O: Token mới aud=inventory-api
    O->>I: Request + exchanged access token
    I->>I: Verify iss + aud + exp + scope
    I-->>O: Inventory response
~~~

Orders Service không nên chuyển nguyên token có audience orders-api sang Inventory API. Khi cần giữ ngữ cảnh người dùng, có thể dùng OAuth 2.0 Token Exchange (RFC 8693) để xin token mới với audience/resource và scope phù hợp.

Token exchange không bỏ qua validation ở downstream:

- Authorization Server phải xác minh subject token và client/actor.
- Token mới phải được giới hạn resource/audience và scope.
- Inventory API vẫn phải kiểm tra issuer, audience, thời gian, token type và authorization.
- Không tin header X-User-Id hoặc X-Tenant-Id do caller tự khai thay cho token đã xác minh.
- Cache token exchange phải phân biệt subject, actor, audience, scope và tenant context.

## 12. Gateway không được thay thế kiểm tra issuer/audience của API

API gateway có thể xác minh token trước khi chuyển request tới backend. Nhưng nếu backend có thể được gọi trực tiếp, backend vẫn cần kiểm tra token hoặc chỉ tin một identity assertion được bảo vệ bằng ranh giới kết nối đáng tin.

Các lỗi thường gặp:

- Gateway chỉ xác minh chữ ký nhưng không kiểm tra iss/aud.
- Gateway xác minh audience của chính gateway, sau đó chuyển token gốc sang backend có audience khác.
- Backend bỏ validation vì cho rằng mọi request đều đi qua gateway.
- Header danh tính do client gửi không bị xóa trước khi gateway ghi header nội bộ.
- Đường mạng bypass gateway vẫn truy cập được backend.

Nếu gateway terminate token validation và chuyển identity assertion, phải bảo vệ gateway-to-backend hop, xác thực gateway, loại header inbound giả mạo và giới hạn backend chỉ nhận assertion từ nguồn tin cậy. Contract giữa gateway và backend cần quy định audience/service identity rõ ràng.

## 13. Các lỗi cấu hình thường gặp

| Lỗi | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Chỉ xác minh chữ ký JWT | Token có thể đến từ issuer khác | Kiểm tra iss với issuer allowlist |
| Không kiểm tra aud | Token API A bị dùng ở API B | Kiểm tra audience của resource server hiện tại |
| So sánh aud với client_id | Hai định danh có mục đích khác nhau | Cấu hình resource identifier riêng |
| Tin iss chưa xác minh để tải JWKS | Có thể bị SSRF/key injection hoặc trust injection | Chỉ tra issuer trong allowlist |
| Chấp nhận mọi issuer dùng chung một key | Không giữ được ranh giới giữa issuer | Trust config và validator theo từng issuer |
| Bỏ qua trailing slash/path của issuer | Có thể gộp hoặc nhầm issuer | So khớp chính xác theo cấu hình |
| Chấp nhận ID token tại API | Token dành cho OIDC client, không phải API | Chỉ nhận access token đúng profile |
| Chỉ kiểm tra scope | Scope không xác định resource recipient | Kiểm tra cả audience |
| Chỉ kiểm tra audience | Token vẫn có thể hết hạn hoặc thiếu quyền | Kiểm tra exp/nbf, scope và authorization |
| Tin introspection active=true mà không xét resource | Token active nhưng không dành cho API này | Kiểm tra audience/resource metadata |
| Gateway xác minh, backend bỏ qua mọi trust boundary | Có thể bypass gateway hoặc giả header | Bảo vệ hop và backend validation |
| Cache kết quả validation quá lâu | Revoke/key/metadata thay đổi nhưng cache stale | TTL và invalidation phù hợp |

## 14. Kiểm thử issuer và audience

Cần có test âm tính cho từng điều kiện độc lập. Nếu chỉ test token hợp lệ, một validator bị thiếu vẫn có thể làm test xanh.

### Ma trận kiểm thử cơ bản

| Issuer | Audience | Token còn hạn | Kết quả mong đợi |
|---|---|---|---|
| Trusted issuer | orders-api | Có | Tiếp tục kiểm tra scope/authorization |
| Untrusted issuer | orders-api | Có | Từ chối |
| Trusted issuer | inventory-api | Có | Từ chối tại Orders API |
| Trusted issuer | Không có aud | Có | Từ chối nếu profile/API yêu cầu aud |
| Trusted issuer | orders-api + reporting-api | Có | Chấp nhận nếu policy cho phép nhiều audience |
| Trusted issuer | orders-api | Hết hạn | Từ chối |
| Trusted issuer | orders-api | Chưa tới nbf | Từ chối |
| Issuer sai path/realm | orders-api | Có | Từ chối |
| Trusted issuer | audience của web client | Có | Từ chối tại resource API |
| Untrusted issuer | audience của API | Hết hạn | Từ chối |

### Những test nâng cao

- JWT chữ ký hợp lệ từ issuer A nhưng gửi đến API chỉ tin issuer B.
- Hai issuer dùng cùng sub để xác nhận không nhầm principal.
- Token có nhiều audience và policy chỉ cho phép một số tập hợp nhất định.
- Token có aud kiểu sai định dạng hoặc giá trị rỗng.
- kid hợp lệ ở JWKS issuer A nhưng token khai issuer B.
- JWT header chứa jku/x5u trỏ tới host không tin cậy.
- ID token có aud là client_id bị gửi đến API.
- Token exchange tạo token sai audience.
- Opaque token active=true nhưng introspection audience không khớp.
- Opaque introspection thiếu metadata bắt buộc.
- Introspection timeout hoặc trả active=false.
- JWKS rotation khiến key mới chưa được phân phối.
- Gateway bỏ validation nhưng backend vẫn được gọi trực tiếp.

## 15. Kiểm thử validator trong Java

Có thể kiểm tra RequiredAudienceValidator trực tiếp bằng unit test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

class RequiredAudienceValidatorTest {

    private final RequiredAudienceValidator validator =
        new RequiredAudienceValidator("orders-api");

    private Jwt tokenWithAudience(List<String> audiences) {
        Instant now = Instant.now();

        return Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .issuer(URI.create(
                "https://identity.example.com/realms/workforce"
            ))
            .subject("alice")
            .audience(audiences)
            .issuedAt(now)
            .expiresAt(now.plusSeconds(300))
            .build();
    }

    @Test
    void acceptsExpectedAudience() {
        var result = validator.validate(
            tokenWithAudience(List.of("orders-api"))
        );

        assertTrue(result.getErrors().isEmpty());
    }

    @Test
    void rejectsDifferentAudience() {
        var result = validator.validate(
            tokenWithAudience(List.of("inventory-api"))
        );

        assertEquals(
            "invalid_token",
            result.getErrors().iterator().next().getErrorCode()
        );
    }

    @Test
    void acceptsExpectedAudienceInArrayWhenPolicyAllows() {
        var result = validator.validate(
            tokenWithAudience(
                List.of("orders-api", "reporting-api")
            )
        );

        assertTrue(result.getErrors().isEmpty());
    }
}
~~~

Unit test này chỉ kiểm tra audience validator. Nó không chứng minh chữ ký, issuer, thuật toán hoặc token profile được xác minh. Cần test riêng cho issuer/time validator và integration test đi qua decoder/filter chain.

### Kiểm tra issuer validator

Có thể dùng validator do Spring Security cung cấp:

~~~java
OAuth2TokenValidator<Jwt> issuerValidator =
    JwtValidators.createDefaultWithIssuer(
        "https://identity.example.com/realms/workforce"
    );
~~~

Sau đó test token có issuer đúng, issuer sai, token hết hạn và token chưa tới nbf. Trong integration test, sử dụng JWT ký bằng key test và decoder cấu hình JWKS/issuer phù hợp; không dùng postprocessor giả Authentication để kết luận chữ ký đã được kiểm tra.

## 16. Test qua MockMvc: hiểu đúng phạm vi

Spring Security Test có request postprocessor jwt() để tạo JWT Authentication giả cho request. Nó hữu ích khi kiểm tra authorization/controller/method security, nhưng thường bỏ qua quá trình decoder xác minh chữ ký và các validator issuer/audience.

Ví dụ:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt()
            .jwt(token -> token
                .issuer(URI.create(
                    "https://identity.example.com/realms/workforce"
                ))
                .audience(List.of("orders-api"))
                .subject("alice"))))
    .andExpect(status().isOk());
~~~

Đây là test authorization với JWT Authentication được dựng sẵn. Để kiểm tra issuer/audience validation thực tế, cần gửi token ký thật qua filter chain và dùng JwtDecoder thật hoặc test decoder riêng.

Không viết test chỉ với jwt() rồi kết luận API đã xác minh chữ ký và issuer. Hãy ghi rõ test đang kiểm tra lớp nào.

## 17. Xử lý lỗi và phản hồi HTTP

Khi bearer token không hợp lệ, resource server thường trả 401 Unauthorized và có thể dùng challenge theo RFC 6750 với error invalid_token. Nếu token hợp lệ nhưng thiếu scope/quyền, API thường trả 403 Forbidden.

Phân biệt:

- **401:** token thiếu, chữ ký sai, issuer không tin cậy, audience sai, hết hạn hoặc token không đúng profile.
- **403:** token đã được xác thực và phù hợp resource nhưng caller không có scope/role/quyền nghiệp vụ.
- **404:** một số API có thể dùng để tránh tiết lộ sự tồn tại của resource; đây là lựa chọn object-level policy, không thay cho token validation.

Không trả thông tin chi tiết như danh sách issuer nội bộ, JWKS URI, subject của người khác hoặc cấu hình realm trong error body công khai. Log nội bộ có thể ghi reason code chuẩn hóa như untrusted_issuer, audience_mismatch, expired hoặc insufficient_scope, không ghi raw token.

## 18. Quan sát và audit khi issuer/audience không hợp lệ

Các sự kiện hữu ích:

- Token validation failure theo reason code.
- Issuer alias đã cấu hình và service nhận request.
- Audience alias dự kiến của resource server.
- Token format và validation stage.
- Client alias đã xác minh nếu có.
- Trace ID và request ID.
- Số lần unknown issuer, audience mismatch hoặc invalid signature tăng bất thường.

Không log raw JWT, Authorization header, refresh token hoặc toàn bộ claims. Với issuer chưa xác minh, không ghi nó như trusted issuer. Nếu cần phân tích nguồn lạ, lưu một giá trị đã giới hạn/escape trong security event riêng theo policy.

Metrics nên dùng label có cardinality thấp như issuer alias đã allowlist, service, token format, outcome và reason code. Không đưa subject, raw client ID hoặc token ID vào metric labels.

### Cảnh báo gợi ý

- Tăng đột biến audience_mismatch trên một API.
- Token từ untrusted issuer xuất hiện lặp lại.
- Một client liên tục gửi token của resource khác.
- Unknown kid tăng sau key rotation.
- Tỷ lệ token validation failure thay đổi ngay sau khi sửa issuer/JWKS config.
- Backend nhận request trực tiếp không qua gateway theo thiết kế.

## 19. Tình huống thực tế và cách xử lý

### Tình huống A — Token từ realm khác được chấp nhận

Một công ty có hai realm workforce và partners. Orders API chỉ dành cho workforce nhưng decoder không kiểm tra issuer. Token partners có cùng claim scope và sub nên vẫn được chấp nhận.

**Phân tích:** Phải cấu hình issuer workforce chính xác, kiểm tra chữ ký bằng key tương ứng và so khớp iss. Nếu hỗ trợ cả hai realm, phải có policy riêng cho từng issuer và chỉ cho phép issuer phù hợp với API/client.

### Tình huống B — Token Inventory được gửi tới Orders

Inventory API phát hành token có audience inventory-api. Một service gửi token đó tới Orders API. Orders API chỉ kiểm tra chữ ký và exp nên request đi tiếp.

**Phân tích:** Thêm audience validator yêu cầu orders-api. Kiểm tra cả JWT và opaque token path; đảm bảo gateway và backend cùng hiểu resource identifier.

### Tình huống C — ID token được dùng thay access token

Frontend gửi ID token có aud=web-portal-client tới Orders API. API chỉ xác minh issuer và chữ ký, sau đó đọc sub.

**Phân tích:** API đang thiếu audience và token type/profile validation. Phải từ chối ID token; frontend cần gửi access token được cấp cho Orders API.

### Tình huống D — Multi-issuer discovery bị lợi dụng

Resource server đọc iss chưa xác minh rồi tải metadata từ URL trong token. Attacker tạo issuer trỏ tới host của họ và cung cấp JWKS để ký token giả.

**Phân tích:** Dùng allowlist issuer được cấu hình trước. Chỉ tra metadata/key theo issuer đã đăng ký; không biến claim untrusted thành nguồn trust mới.

### Tình huống E — Token đúng issuer/audience nhưng thiếu quyền

Token có issuer workforce và audience orders-api, nhưng chỉ có scope profile.read. Orders API trả 403 khi gọi chức năng đọc đơn hàng.

**Phân tích:** Đây là hành vi đúng. Issuer/audience chỉ xác nhận nguồn và recipient; scope/authorization vẫn phải được kiểm tra riêng.

## 20. Checklist trước production

- Issuer được cấu hình chính xác và nằm trong trust allowlist?
- Token được xác minh chữ ký bằng key thuộc issuer đã tin cậy?
- Không dùng iss chưa xác minh để tải metadata/JWKS từ URL tùy ý?
- Audience được kiểm tra với resource identifier của đúng API?
- Có phân biệt client_id, sub, azp và aud?
- Có từ chối ID token khi API yêu cầu access token?
- Có kiểm tra exp, nbf, thuật toán và token profile?
- Multi-issuer có validator, key set và policy riêng?
- Opaque token introspection xác minh active, issuer/audience metadata hoặc ràng buộc tương đương?
- Token exchange giữ audience/resource và scope phù hợp?
- Gateway/backend có trust boundary rõ và không cho bypass?
- Có test sai issuer, sai audience, nhiều audience, thiếu aud, ID token và opaque token?
- Metrics/logs có reason code mà không lưu raw token?
- Thay đổi issuer/JWKS/audience config có review và regression test?

## 21. Tổng kết

Bỏ qua **issuer** hoặc **audience** là lỗi validation nghiêm trọng. Issuer xác định Authorization Server mà resource server tin cậy; audience xác định token được dự định gửi tới API hoặc resource nào. Chữ ký hợp lệ không thay thế hai kiểm tra này.

Với JWT, resource server phải xác minh chữ ký, issuer chính xác, audience, thời gian, token profile và các quyền cần thiết. Với opaque token, phải dùng introspection hoặc cơ chế trạng thái đáng tin cậy và xác minh metadata phù hợp với resource server. Khi nhận nhiều issuer, dùng allowlist và cấu hình riêng; không tải khóa từ issuer chưa xác minh. Không nhầm ID token với access token hoặc client_id với aud.

Sau khi issuer và audience hợp lệ, API vẫn phải kiểm tra scope, tenant, actor và quyền trên tài nguyên. **Một token chỉ được chấp nhận khi vừa đến từ nguồn tin cậy, vừa được cấp cho đúng API, còn hiệu lực và đáp ứng chính sách authorization của request hiện tại.**
