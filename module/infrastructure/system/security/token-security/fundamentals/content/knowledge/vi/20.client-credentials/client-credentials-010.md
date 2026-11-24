# Audience restriction

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **audience restriction** trong OAuth 2.0: access token chỉ nên được chấp nhận bởi **Resource Server (RS)** mà Authorization Server (AS) dự định cấp cho.
- Hiểu vì sao audience đặc biệt quan trọng trong **client_credentials grant**, nơi token thường đại diện cho **client/workload**, không mặc định đại diện cho một End-User.
- Phân biệt audience (aud), scope, issuer (iss), subject (sub), client_id, token type và permission nghiệp vụ.
- Thiết kế AS giới hạn **(client, resource, scope)** dựa trên client registration và policy; sử dụng **resource indicator theo RFC 8707** khi phù hợp.
- Kiểm audience ở RS đối với cả **JWT access token** và **opaque token dùng introspection**, không chỉ kiểm chữ ký hoặc trường active.
- Xử lý token cho nhiều API, cache theo audience, service-to-service delegation, **token exchange** và rủi ro **confused deputy**.
- Kết hợp audience restriction với TTL, lưu trữ token, sender-constraining, revocation và kiểm quyền trên tài nguyên/tenant.
- Đọc ví dụ HTTP, Java/Spring Security, sơ đồ Mermaid và tự kiểm thử các trường hợp sai audience.

## 1. Audience restriction là gì?

**Audience** là **bên nhận dự kiến của một token**. Trong hệ thống OAuth 2.0, **audience restriction** là nguyên tắc access token được phát cho **một Resource Server hoặc một tập Resource Server đã được cho phép**, và những API không nằm trong audience phải từ chối token.

Ví dụ:

~~~text
Authorization Server: https://identity.example.test
Client: reporting-worker
Resource Server: Orders API
Audience: https://orders.example.test/api
Scope: orders:read
~~~

Sau khi AS phát access token cho Orders API:

- **Orders API** có thể chấp nhận token nếu issuer, chữ ký/trạng thái, audience, thời hạn, scope và policy đều hợp lệ.
- **Payments API** phải từ chối chính token đó vì nó **không được cấp cho Payments API**, cho dù cả hai API tin cùng một AS.
- **Client** không được tự sửa claim aud trên token để biến token Orders thành token Payments.

~~~text
Token-Orders:
    aud = orders-api
    scope = orders:read

Token-Payments:
    aud = payments-api
    scope = payments:reconcile
~~~

**Audience trả lời “token dùng ở đâu?”, còn scope trả lời “token được dùng để làm những gì?”.** Một access token chỉ an toàn khi cả giới hạn **bên nhận** và **quyền thực hiện** đều được thực thi đúng.

### Audience restriction không phải mã hóa token

Một JWT có claim aud thường vẫn đọc được nếu được biểu diễn dưới dạng JWS. Chữ ký của AS bảo vệ tính toàn vẹn nhưng **không làm token không thể sao chép**. Audience restriction chỉ phát huy tác dụng khi **RS xác minh audience đã được AS phát hành**, thay vì chỉ kiểm chữ ký.

## 2. Vì sao cần đặc biệt quan tâm trong client_credentials?

**Client Credentials Grant** của OAuth 2.0 cho phép một **confidential client** xác thực với AS bằng credential của chính nó để xin access token theo quyền client được cấp.

Ví dụ:

~~~text
Machine client:
    nightly-report-worker

Grant type:
    client_credentials

Client authentication:
    private_key_jwt / mTLS / client_secret_basic theo đăng ký

Resource đích:
    Orders API

Scope yêu cầu:
    orders:read
~~~

Khác với Authorization Code có End-User tương tác, client_credentials **không cần một người dùng cuối đang đăng nhập trình duyệt** tại mỗi lần cấp token. AS xác định quyền theo **client registration, workload identity và policy**.

AS phải trả lời:

1. Client đã đăng ký và được phép dùng **client_credentials** chưa?
2. Credential hoặc client assertion được xác thực đúng phương thức đăng ký chưa?
3. Client có được nhận token dành cho **Orders API** không?
4. Client được cấp **orders:read**, hay chỉ một scope hẹp hơn?
5. Token có TTL, audience, loại token và sender binding phù hợp không?

**Một client được xác thực không đồng nghĩa được xin token cho mọi API.** Ví dụ reporting-worker được đọc Orders không tự được xin access token có aud=Payments và scope=payments:refund.

### Chủ thể của token thường là workload

Với client_credentials, token thường đại diện **service/client principal**, không phải hành động được một End-User ủy quyền trong phiên browser. Tùy token profile, claim sub có thể diễn đạt identity của client; không được tự ánh xạ service principal thành một user có role admin.

Audience restriction giúp giảm **blast radius** của workload credential và access token: token cho API A không nên được sử dụng ở API B.

## 3. Vai trò OAuth và trust boundary

| Bên | Trách nhiệm liên quan audience | Điều không được giả định |
| --- | --- | --- |
| **Client/workload** | Xác thực với AS, yêu cầu đúng resource/scope và sử dụng token ở RS được cấp. | Có client secret đúng là được gọi mọi RS. |
| **Authorization Server** | Kiểm client/grant, áp resource allowlist, quyết định audience/scope và phát token. | URI resource do client gửi luôn đáng tin. |
| **Resource Server** | Kiểm token do issuer đáng tin cấp **cho chính RS**, rồi kiểm scope/permission. | JWT ký đúng có thể dùng ở mọi API. |
| **Resource Owner** | Trong client_credentials, quyền của client được quản lý theo mô hình máy–máy. | Mọi access token đều gắn với End-User có quyền cá nhân. |

~~~mermaid
sequenceDiagram
    participant W as reporting-worker
    participant AS as Authorization Server
    participant O as Orders API
    participant P as Payments API

    W->>AS: HTTPS /token client_credentials resource=Orders
    AS->>AS: Xác thực client; kiểm resource và scope
    AS-->>W: Access token aud=Orders
    W->>O: Bearer token aud=Orders
    O->>O: Kiểm iss, signature/active, aud, exp, scope
    O-->>W: Dữ liệu được phép
    W->>P: Thử dùng chính token aud=Orders
    P->>P: Audience mismatch
    P-->>W: 401 invalid_token
~~~

Trust boundary quan trọng nhất ở đây là **Client → Resource Server**: RS không được chấp nhận token chỉ vì client đã nhận nó từ AS. RS phải kiểm chính xác **token có dành cho RS không**.

## 4. Audience khác gì scope, issuer, client_id và permission?

| Thuộc tính | Ý nghĩa | Ví dụ | Quyết định |
| --- | --- | --- | --- |
| **iss** | Ai phát hành token? | https://identity.example.test | RS chỉ tin issuer cấu hình. |
| **aud** | Bên nhận dự kiến là ai? | https://orders.example.test/api | RS kiểm token dành cho mình. |
| **scope** | Phạm vi hành động OAuth được cấp. | orders:read | RS kiểm quyền của endpoint. |
| **client_id** | Client nào nhận token theo profile. | reporting-worker | AS xác thực client; RS có thể áp policy theo client. |
| **sub** | Chủ thể token theo profile. | reporting-worker | RS phân biệt service và user. |
| **exp/nbf/iat** | Mốc thời gian token. | NumericDate | RS kiểm thời gian và clock skew có giới hạn. |
| **permission/role** | Quyền thực tế trên nghiệp vụ. | Được đọc đơn thuộc tenant-blue | RS/policy engine kiểm theo tài nguyên. |

Các nhầm lẫn thường gặp:

**Audience không phải issuer.** Cùng một issuer có thể cấp token cho nhiều RS. Hai API cùng tin chữ ký của AS vẫn phải có aud riêng.

**Audience không phải client_id.** Client là ứng dụng xin token; audience là API được phép nhận token.

**Audience không phải scope.** Scope **read** hoặc **orders:read** không chứng minh token được cấp cho Orders API; vẫn phải kiểm aud.

**Audience không phải tenant.** Token aud=orders-api vẫn có thể bị từ chối khi client không có quyền đọc đơn ở tenant được yêu cầu.

**Audience không nhất thiết bằng URL request đang gọi.** Nó là **resource identifier đã được AS và RS thống nhất**, có thể là URI hoặc logical identifier theo profile. Không tự lấy Host header người dùng gửi để xác định expected audience.

## 5. Vì sao chỉ kiểm chữ ký/issuer/expiry là không đủ?

Giả sử cả Orders API và Payments API tin cùng một Authorization Server.

~~~text
Token A:
    signature hợp lệ
    iss = identity.example.test
    exp = còn hạn
    aud = orders-api
    scope = read
~~~

Nếu Payments API chỉ kiểm:

~~~text
verifySignature(token)
verifyIssuer(token)
verifyExpiration(token)
verifyScope(token, "read")
~~~

thì một token hợp lệ **cho Orders** có thể bị dùng nhầm ở **Payments**, nhất là khi hai API dùng tên scope giống nhau.

Đây là một dạng **cross-resource token substitution**. Trong trường hợp token bị đánh cắp từ log hoặc bộ nhớ của client, kẻ tấn công có thể thử dùng nó ở nhiều API cùng issuer.

Cần kiểm thêm:

~~~text
verifyAudience(token, "payments-api")
~~~

Nếu aud=orders-api, Payments API **phải từ chối**, không kể chữ ký đúng.

### Vai trò của audience trong giảm thiệt hại

Audience restriction thu hẹp **nơi một bản sao token có thể dùng được**. Tuy nhiên, nó **không bảo vệ khỏi việc kẻ tấn công dùng token tại chính audience hợp lệ**. Vì vậy vẫn cần TTL, scope tối thiểu, sender-constraining, thu hồi và permission nghiệp vụ.

## 6. AS phải kiểm quyền theo bộ (client, resource, scope)

Không đủ nếu AS chỉ có:

~~~text
client.allowedGrants = ["client_credentials"]
client.allowedScopes = ["orders:read", "payments:reconcile"]
~~~

rồi phát token theo bất kỳ audience mà client yêu cầu. Scope hợp lệ cho **một resource** không tự hợp lệ ở **resource khác**.

Một policy phù hợp hơn:

| Client | Resource | Scope cho phép | Ví dụ yêu cầu | Kết quả |
| --- | --- | --- | --- | --- |
| reporting-worker | Orders API | orders:read | Orders + orders:read | Cho phép. |
| reporting-worker | Payments API | Không có quyền | Payments + payments:refund | Từ chối. |
| settlement-worker | Payments API | payments:reconcile | Payments + payments:reconcile | Cho phép. |
| settlement-worker | Orders API | Không có quyền | Orders + orders:write | Từ chối. |
| metrics-worker | Metrics API | metrics:read | Metrics + metrics:read | Cho phép theo policy. |

Các bước AS cần áp:

1. **Client registration:** client tồn tại, trạng thái hoạt động và được dùng client_credentials.
2. **Client authentication:** secret, private_key_jwt hoặc mTLS được kiểm đúng theo đăng ký.
3. **Resource resolution:** resource là một resource đã đăng ký và đáng tin.
4. **Resource authorization:** client được phép nhận token cho resource đó.
5. **Scope authorization:** những scope được cấp thuộc giao điểm của yêu cầu, grant và policy của resource.
6. **Token issuance:** aud, iss, TTL, type và binding được chọn theo profile.
7. **Audit:** ghi metadata cần thiết, không log plaintext credential/token.

**Client authentication xác minh ai đang xin token, còn resource/scope policy xác định client đó được xin cái gì.** Không gộp hai quyết định này.

## 7. RFC 8707 Resource Indicators

**RFC 8707 — Resource Indicators for OAuth 2.0** cho phép client chỉ rõ tài nguyên đích bằng tham số **resource**.

Trong token request client_credentials:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Authorization: Basic EXAMPLE_CLIENT_AUTH
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders%3Aread&resource=https%3A%2F%2Forders.example.test%2Fapi
~~~

Đây là request minh họa. Trong thực tế phải gửi qua **HTTPS**, client authentication đúng phương thức đã đăng ký và không đặt secret vào log. Base64 trong HTTP Basic **không phải mã hóa bảo mật**.

Ở đây resource là URI:

~~~text
https://orders.example.test/api
~~~

AS phải kiểm xem URI ấy có nằm trong resource registry và client có quyền xin token cho nó hay không.

### Tham số resource không tự là aud claim

**resource** là tham số của client gửi tới AS. **aud** là thông tin audience trong token hoặc metadata token mà RS sử dụng.

Một AS có thể ánh xạ:

~~~text
resource request:
    https://orders.example.test/api

aud in access token:
    https://orders.example.test/api
~~~

Một AS khác có thể dùng hợp đồng:

~~~text
resource request:
    https://orders.example.test/api

aud in access token:
    orders-service-prod
~~~

Điều bắt buộc là **AS và RS có hợp đồng định danh tin cậy, nhất quán**. Không tự suy mọi triển khai phải chép nguyên giá trị resource vào aud.

### Kiểm URI resource

Theo RFC 8707, resource parameter dùng **absolute URI**, không có fragment. Nhưng một URI đúng cú pháp chưa đủ để được cấp quyền.

AS cần:

- Parse URI nghiêm ngặt và áp profile.
- Từ chối resource không thuộc registry/allowlist.
- Kiểm policy **client → resource → scope**.
- Xử lý mapping/canonicalization theo quy tắc chính thức.
- Không dùng resource từ client làm URL để server tự gọi HTTP đến địa chỉ tùy ý.
- Không dùng kiểm tra prefix/substring để cho phép tên miền gần giống.
- Xác định cách xử lý nhiều resource indicators nếu AS hỗ trợ.

**Resource indicator là yêu cầu nhận token, không phải quyền tự đăng ký Resource Server mới.**

### Client không gửi resource

Nếu client không gửi resource, AS có thể áp **default resource đã cấu hình an toàn**. Nếu không xác định được audience phù hợp, nên từ chối hoặc yêu cầu chỉ rõ resource theo hợp đồng, **không cấp token dùng cho mọi API**.

## 8. Luồng HTTP hoàn chỉnh: một worker xin token Orders API

Giả sử:

~~~text
AS:
    https://identity.example.test

Confidential Client:
    nightly-report-worker

Target Resource:
    https://orders.example.test/api

Requested Scope:
    orders:read
~~~

### 8.1 Token request

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Authorization: Basic EXAMPLE_ENCODED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&resource=https%3A%2F%2Forders.example.test%2Fapi&scope=orders%3Aread
~~~

AS xác thực client, kiểm grant registration, resource allowlist và scope.

### 8.2 Token response

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_ORDERS_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

**expires_in=600** chỉ là giá trị minh họa, không phải default hoặc TTL bắt buộc cho client_credentials.

### 8.3 Client gọi Orders API

~~~http
GET /api/orders?status=OPEN HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_ORDERS_ACCESS_TOKEN
~~~

Orders API phải xác minh token, audience và quyền phù hợp trước khi trả dữ liệu.

### 8.4 Client thử gọi Payments bằng token Orders

~~~http
POST /api/refunds HTTP/1.1
Host: payments.example.test
Authorization: Bearer EXAMPLE_ORDERS_ACCESS_TOKEN
Content-Type: application/json

{"orderId":"order-123","reason":"EXAMPLE"}
~~~

Payments API **phải từ chối** vì token không dành cho Payments.

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Trường hợp **token đúng audience nhưng thiếu scope** có thể trả **403 Forbidden** với Bearer error **insufficient_scope** theo RFC 6750. Đừng nhầm aud sai với scope không đủ.

## 9. Audience của JWT access token

Trong JWT, **aud** là registered claim name biểu thị các bên nhận dự kiến. RFC 7519 cho phép aud là **một string hoặc một mảng string**. RFC 9068 xác định thêm profile cho **JWT access token OAuth 2.0**.

Ví dụ header minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "example-key-1"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "nightly-report-worker",
  "client_id": "nightly-report-worker",
  "aud": "https://orders.example.test/api",
  "scope": "orders:read",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000600,
  "jti": "example-token-123"
}
~~~

Đây **không phải JWT hoàn chỉnh**; không có chữ ký và các thời điểm chỉ là dữ liệu giả.

### Audience là mảng

Một JWT có thể chứa:

~~~json
{
  "aud": [
    "https://orders.example.test/api",
    "https://reports.example.test/api"
  ]
}
~~~

Cú pháp này có thể hợp lệ, nhưng **không có nghĩa AS nên cấp token đa audience mặc định**. Mỗi recipient thêm vào làm tăng phạm vi nơi một bản sao token có thể được chấp nhận.

### Sai lầm khi đọc JWT

RS không được chỉ decode Base64URL payload rồi tin aud. Phải **xác minh token** bằng khóa/issuer/thuật toán được cấu hình tin cậy; JWT header tự khai không được quyết định nguồn JWKS.

Ngược lại, JWT ký đúng nhưng **aud sai** vẫn không phải token hợp lệ cho RS đó. Chữ ký và audience là **hai phép kiểm độc lập**.

### Token type quan trọng

Với profile RFC 9068, access token JWT có quy định về **typ=at+jwt** (và dạng được cho phép tương ứng). RS phải nhận đúng **access-token profile** mà API được cấu hình để chấp nhận, không coi một ID token OIDC có chữ ký cùng issuer là Bearer AT hợp lệ.

## 10. Opaque token và introspection

Opaque access token là chuỗi mà Resource Server không cần tự decode như JWT. RS có thể gọi **introspection endpoint** của AS theo RFC 7662 hoặc dùng cơ chế xác minh đã thỏa thuận.

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic EXAMPLE_RS_AUTH
Content-Type: application/x-www-form-urlencoded

token=EXAMPLE_OPAQUE_ACCESS_TOKEN
~~~

Phản hồi minh họa:

~~~json
{
  "active": true,
  "client_id": "nightly-report-worker",
  "token_type": "Bearer",
  "scope": "orders:read",
  "aud": "https://orders.example.test/api",
  "iss": "https://identity.example.test",
  "exp": 1730000600
}
~~~

**active=true không đồng nghĩa được cho phép mọi request**. RS vẫn phải kiểm aud, token type, scope, subject/client, permission nghiệp vụ và trạng thái theo profile.

### Nếu introspection không trả aud

Nếu RS yêu cầu audience restriction mà response không cung cấp thông tin audience đáng tin, RS **không được tự chấp nhận token chỉ dựa vào active=true**. AS và RS phải có hợp đồng trả metadata cần thiết hoặc một cơ chế xác minh tương đương.

### Bảo vệ introspection endpoint

AS nên xác thực/ủy quyền bên introspect và giới hạn thông tin trả về. Không biến endpoint thành công cụ công khai để dò token hay lấy claims. TLS là yêu cầu nền tảng.

### Cache introspection

Kết quả active=true có thể được cache ngắn để giảm tải, nhưng cần **TTL và chính sách thu hồi**. AS đã revoke token mà RS còn giữ cache active có thể tạo ra cửa sổ tiếp tục chấp nhận token. RS phải kiểm đúng aud với **kết quả introspection của chính token**.

## 11. Resource Server kiểm audience ở đâu?

Một quy trình kiểm token tại Orders API:

~~~mermaid
flowchart TD
    A["Nhận Bearer access token"] --> B{"Có credential đúng transport?"}
    B -->|Không| X["401 Unauthorized"]
    B -->|Có| C["Xác minh JWT hoặc introspection đáng tin"]
    C --> D{"Issuer, type, signature/active, expiry hợp lệ?"}
    D -->|Không| X
    D -->|Có| E{"aud đúng Orders API?"}
    E -->|Không| X
    E -->|Có| F{"Đủ scope?"}
    F -->|Không| Y["403 Forbidden"]
    F -->|Có| G{"Đủ permission trên tenant/tài nguyên?"}
    G -->|Không| Y
    G -->|Có| H["Xử lý nghiệp vụ"]
~~~

Thứ tự trong framework có thể khác, nhưng mọi kiểm tra bắt buộc phải hoàn tất **trước khi thực hiện hành động được bảo vệ**.

### So khớp exact identifier

Ví dụ RS được cấu hình:

~~~text
EXPECTED_AUDIENCE = "https://orders.example.test/api"
~~~

Phép kiểm phù hợp:

~~~text
if EXPECTED_AUDIENCE not in verifiedToken.audiences:
    DENY
~~~

Những phép kiểm không đủ an toàn:

~~~text
token.aud contains "orders"         // substring, dễ nhầm
token.aud startsWith "https://orders"
token.aud endsWith ".example.test"
token.scope includes "orders:read"   // scope không thay aud
token.iss == trustedIssuer          // issuer không thay aud
request.Host == token.aud           // Host từ client không tạo trust config
~~~

**Expected audience phải đến từ cấu hình server đáng tin**, không phụ thuộc Host hoặc X-Forwarded-Host do Internet có thể kiểm soát.

### Aud thiếu, sai hoặc nhiều phần tử

- **Thiếu aud** khi token profile yêu cầu: từ chối.
- **Aud sai:** từ chối ngay cả khi chữ ký đúng.
- **Aud nhiều phần tử:** nếu profile/policy cho phép, RS có thể kiểm membership; nếu hệ thống yêu cầu single-audience token, RS phải từ chối token nhiều aud.
- **Identifier không đồng nhất:** cấu hình một dạng chính thức; không tự chấp nhận prefix, trailing slash hay tên miền gần giống.
- **Dữ liệu không đáng tin:** không coi một payload JWT chưa xác minh là thông tin phân quyền.

### TLS không tự giải quyết aud

TLS bảo vệ kết nối client–RS; nó không chứng minh access token được AS phát cho RS đó. Một client có thể gửi token audience sai qua một kết nối TLS hoàn toàn hợp lệ. RS vẫn phải kiểm aud.

## 12. Java/Spring Security: kiểm aud trong JWT Resource Server

Đoạn code minh họa cách thêm **audience validator** cho Orders API bằng các thành phần Spring Security. Nó tập trung vào **một audience chính xác** và dùng JWKS URI đã cấu hình từ issuer tin cậy.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersAudienceValidation {

    private static final String ISSUER =
            "https://identity.example.test";

    private static final String JWKS_URI =
            "https://identity.example.test/.well-known/jwks.json";

    private static final String EXPECTED_AUDIENCE =
            "https://orders.example.test/api";

    @Bean
    JwtDecoder jwtDecoder() {
        // Không lấy JWKS URI từ dữ liệu do JWT tự khai.
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(JWKS_URI)
                .build();

        OAuth2TokenValidator<Jwt> base =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            List<String> aud = jwt.getAudience();

            // Chính sách ví dụ: chỉ cho đúng một audience.
            boolean allowed = aud != null
                    && aud.size() == 1
                    && EXPECTED_AUDIENCE.equals(aud.get(0));

            if (allowed) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Audience is not Orders API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                base, audienceValidator
            )
        );
        return decoder;
    }
}
~~~

### Điều code minh họa chưa làm

- **SecurityFilterChain:** vẫn phải cấu hình route cần xác thực, tích hợp JWT Resource Server, kiểm scope/authority và authorization nghiệp vụ.
- **Token type/profile:** cần bảo đảm chỉ nhận access token JWT đúng profile (ví dụ RFC 9068), không nhận ID token có chữ ký hợp lệ.
- **Thuật toán và khóa ký:** chỉ dùng thuật toán được cho phép, quản lý JWKS/key rotation tin cậy.
- **Multi-audience:** ví dụ cố tình yêu cầu aud chỉ có **một giá trị**. Nếu AS cho phép nhiều audience, thay bằng policy được đánh giá riêng; không tự nới lỏng.
- **Client principal:** client_credentials token không được mặc nhiên diễn giải là token End-User.
- **Tenant permission:** aud đúng chỉ là bước đầu; vẫn cần kiểm quyền trên bản ghi/tenant.
- **Revocation và logs:** cân nhắc token state/TTL và không ghi JWT, client secret hay private key vào log.

**Cần chạy audience validation trên token đã được xác minh cryptographically hoặc introspection đáng tin**, không trên JSON decode tùy tiện.

## 13. Mã giả của Authorization Server

AS phải quyết định resource và audience **trước khi phát token**.

~~~text
function issueTokenForClientCredentials(request):
    requireHttps()
    requirePostAndValidFormEncoding(request)
    require request.grant_type == "client_credentials"

    client = authenticateConfidentialClient(
        request,
        registeredAuthMethod
    )

    if client not authenticated:
        return invalid_client

    if not client.grantAllowlist.contains("client_credentials"):
        return unauthorized_client

    resource = parseResourceIndicator(request.resource)

    if resource absent:
        resource = safeConfiguredDefaultResource(client)

    if resource absent:
        return resourcePolicyError

    target = resourceRegistry.resolve(resource)
    if target absent or not client.allowedResources.contains(target.id):
        return resourcePolicyError

    requestedScopes = parseScopes(request.scope)
    grantedScopes = authorizeScopesForResource(
        client,
        target,
        requestedScopes
    )

    if grantedScopes invalid under grant policy:
        return invalid_scope

    token = issueAccessToken(
        issuer = trustedConfiguredIssuer,
        subject = trustedClientPrincipal(client),
        clientId = client.id,
        audience = target.expectedAudience,
        scopes = grantedScopes,
        expiry = policyLifetime(client, target),
        senderBinding = configuredBinding(client, target)
    )

    return noStoreTokenResponse(token)
~~~

Đây là **mã giả về trách nhiệm bảo mật**, không phải triển khai AS production. Các mã lỗi OAuth cụ thể cho resource indicator phụ thuộc hồ sơ/tiêu chuẩn và triển khai; không tự trả thông tin nhạy cảm về resource registry.

### Vì sao không dùng nguyên request.resource làm aud?

Cách không an toàn:

~~~text
aud = request.resource
signJwt(aud, allRequestedScopes)
~~~

Nó trao quyền lựa chọn audience và scope cho client. AS phải tra **resource registry/allowlist**, kiểm client có quyền, và chỉ phát token theo policy đã được quản trị.

### Default audience

Nếu request không có resource, AS có thể có default resource riêng đã cấu hình cho client. Nhưng **không nên tự cấp aud=all-apis**. Nếu không thể xác định recipient an toàn, từ chối sẽ tốt hơn cấp một credential mơ hồ.

## 14. Một token nhiều audience hay nhiều token riêng?

**Single-audience token** là lựa chọn rõ ràng cho hệ thống nhiều RS độc lập:

~~~text
Orders Token:
    aud = orders-api
    scope = orders:read

Payments Token:
    aud = payments-api
    scope = payments:reconcile
~~~

Ưu điểm:

- Giảm nơi một bản sao token có thể sử dụng.
- Scope gắn với đúng resource.
- Dễ cache và kiểm thử việc gửi nhầm token.
- Có thể áp TTL/risk policy theo từng API.
- Giảm rủi ro token forwarding và confused deputy.

**Multi-audience token** có thể hợp lệ theo một số token profile, nhưng cần chính sách cụ thể. Nó tăng số RS có thể chấp nhận cùng credential và có thể làm permission/thu hồi phức tạp.

| Thiết kế | Lợi ích | Rủi ro/đánh đổi |
| --- | --- | --- |
| **Một token cho mỗi RS** | Least privilege rõ, cache và audit đơn giản. | Client quản lý nhiều token hơn. |
| **Một token đa audience** | Giảm số lần xin token trong vài mô hình. | Tăng nơi token có thể bị lạm dụng; scope/policy dễ nhầm. |
| **Một logical RS ở gateway** | Nhiều route có thể dùng một audience theo hợp đồng. | Phải định nghĩa gateway/backend là ranh giới tin cậy nào. |
| **Token exchange/downscoping** | Đổi token cho downstream theo policy. | Yêu cầu AS hỗ trợ và kiểm delegation chặt. |

**Không dùng aud=* hoặc aud=all-apis như giải pháp tránh phải quản lý resource**. Nếu một profile riêng cho phép nhiều recipient, AS/RS cần kiểm từng recipient theo hợp đồng, không diễn giải wildcard tùy tiện.

## 15. Downstream services và rủi ro token forwarding

Một luồng microservice:

~~~text
reporting-worker
     |
     | Token aud=orders-api
     v
Orders Service
     |
     | Cần gọi Payments Service
     v
Payments Service
~~~

**Orders Service không nên chuyển nguyên token aud=orders-api đến Payments Service.** Payments phải từ chối token sai audience.

### Phương án 1: Service tự xin token bằng client_credentials

Orders Service cũng có thể là một confidential client riêng:

~~~text
Orders Service -> AS:
    grant_type = client_credentials
    client_id = orders-service
    resource = payments-api
    scope = payments:status.read

AS -> Orders Service:
    AT aud=payments-api, scope=payments:status.read

Orders Service -> Payments:
    Bearer AT dành cho Payments
~~~

Đây là **quyền của chính service**, không mặc định mang sự ủy quyền của người dùng/request gốc. Orders Service phải kiểm policy của request trước khi dùng quyền mạnh của mình.

### Phương án 2: OAuth Token Exchange

Nếu kiến trúc cần gọi downstream **thay mặt principal hoặc client gốc**, có thể dùng **RFC 8693 OAuth 2.0 Token Exchange** khi AS hỗ trợ.

~~~text
Incoming token:
    aud = orders-api
    scope = orders:read

AS kiểm token, actor, subject và delegation policy.

Outgoing token:
    aud = payments-api
    scope = payments:status.read
    actor/subject context theo profile
~~~

Token exchange **không tự cho phép nâng quyền**. AS phải giới hạn scope/audience theo client, actor và grant. Payments API vẫn phải kiểm token đầu ra và permission của chính nó.

### Confused deputy

Một service có quyền thanh toán mạnh có thể bị một caller ít quyền dẫn dụ thực hiện refund nếu backend chỉ tin “request đã qua gateway” mà không kiểm caller/context.

**Audience giúp giới hạn nơi token được chấp nhận**, nhưng không thay business authorization, delegation policy hoặc kiểm principal ở từng hop.

## 16. Token cache phải phân biệt audience

Client_credentials thường dùng token cache để giảm request tới AS. Một cache key chỉ dựa vào client_id có thể gây nhầm:

~~~text
cache key = reporting-worker

1. Xin token aud=orders-api -> cache.
2. Cần gọi payments-api -> lấy lại cùng token.
3. Gửi token Orders tới Payments -> phải bị từ chối.
~~~

Lỗi nghiêm trọng xuất hiện khi Payments API còn **thiếu audience validation** và chấp nhận nhầm token.

### Những yếu tố cần cân nhắc trong cache key

~~~text
issuer
client registration / credential identity
resource hoặc expected audience
scope set
token profile
sender-binding key/certificate nếu áp dụng
tenant/environment context nếu policy cần
~~~

Không bắt buộc mọi cache đều có mọi field, nhưng **không được chia sẻ token qua hai đích/quyền khác nhau**.

### TTL và safety margin

- Không dùng access token sau **exp**.
- Thường có margin trước exp để tránh token hết hạn khi request đang truyền.
- Không nhầm NumericDate giây với milliseconds.
- Không coi cached token có giá trị vĩnh viễn nếu AS thay quyền.
- Hạn chế log token trong cache debugger, metrics và distributed traces.

### Concurrent requests

Có thể dùng **single-flight theo cache key** để nhiều request cùng audience chờ một lần xin token. Không dùng một lock toàn cục rồi trả token của resource A cho resource B.

Theo RFC 6749, AS **SHOULD NOT** cấp refresh token trong client_credentials. Worker thường xin access token mới bằng credential của chính client, không dựa vào RT cá nhân lưu lâu dài.

## 17. Audience và scope phải kiểm cùng nhau

Orders API:

~~~text
GET /orders              cần scope orders:read
POST /orders             cần scope orders:write
POST /orders/123/approve cần orders:approve và permission nghiệp vụ
~~~

Một token có **aud=orders-api** không tự được POST hay approve nếu scope không đủ.

Ngược lại, token **aud=payments-api** nhưng có chuỗi scope **orders:read** cũng không được GET Orders.

Một policy logic:

~~~text
ALLOW_REQUEST =
    valid_access_token
    AND trusted_issuer
    AND expected_audience_present
    AND token_not_expired_or_revoked_per_policy
    AND required_scope_present
    AND client_or_principal_has_permission
    AND resource_state_allows_action
~~~

### Tên scope trùng nhau

Hai API có thể cùng dùng scope **read**. Nếu một RS chỉ kiểm scope=read, token từ API khác có thể bị nhầm.

Audience là lớp bảo vệ độc lập, **không được thay bằng việc đặt tên scope thật dài**.

## 18. Audience không phải tenant authorization

Ví dụ client chỉ có quyền đọc dữ liệu tenant-blue:

~~~text
client_id = reporting-worker
aud = orders-api
scope = orders:read
allowed tenant = tenant-blue
~~~

Nó thử gọi:

~~~http
GET /api/tenants/tenant-green/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_ORDERS_AT
~~~

Token đúng audience **không có nghĩa worker được đọc tenant-green**.

RS phải kiểm tenant của tài nguyên từ nguồn tin cậy, client/service principal và permission hiện hành:

~~~text
ALLOW =
    token.valid
    AND token.aud == orders-api
    AND token.scope includes orders:read
    AND principal.active
    AND policy.allows(principal, actualResourceTenant, "orders:read")
~~~

**actualResourceTenant** không chỉ là giá trị X-Tenant-Id hoặc path tùy ý do client gửi. Đọc đúng tenant từ dữ liệu/quan hệ tài nguyên giúp giảm rủi ro **BOLA/IDOR**.

## 19. Revocation và quyền thay đổi sau phát hành

Audience restriction giới hạn **recipient**, nhưng không tự thu hồi token hay cập nhật permission.

### JWT access token xác minh offline

Nếu JWT còn hạn và RS chỉ kiểm JWT offline, việc AS vừa khóa client có thể chưa khiến RS từ chối token đó ngay. Cần chọn chính sách phù hợp:

- AT TTL ngắn.
- Denylist/session version hoặc trạng thái thu hồi khi nghiệp vụ cần.
- Introspection hoặc lookup permission hiện hành.
- Cache với TTL/invalidation theo SLA.
- Phản ứng sự cố khi client secret/private key bị lộ.

### Opaque token và introspection

AS có thể trả **active=false** nếu token đã bị revoke. Tuy nhiên, cache active=true ở RS có thể khiến thu hồi bị trễ. Audience cần được kiểm trong phản hồi introspection đáng tin, không bỏ qua khi dùng cache.

### Key rotation không tự thay aud

Xoay khóa ký/JWKS là quản lý mật mã; không biến token cấp cho Orders thành token Payments. Nếu signing key bị lộ, hệ thống có thể cần quy trình xử lý rộng hơn key rotation thông thường, nhưng vẫn phải duy trì audience checks.

## 20. Sender-constraining và audience restriction

Hai cơ chế trả lời hai câu hỏi:

| Cơ chế | Giới hạn điều gì? | Không tự giải quyết |
| --- | --- | --- |
| **audience restriction** | Token được phép dùng ở RS nào. | Bản sao token bị dùng tại đúng RS. |
| **scope/permission** | Hành động và tài nguyên được phép. | Token bị sao chép và phát lại. |
| **DPoP** | Proof-of-possession theo RFC 9449. | Phân quyền sai hoặc runtime client bị chiếm. |
| **mTLS-bound access token** | Token gắn với client certificate theo RFC 8705. | Sai aud/permission hoặc quản lý khóa yếu. |
| **TLS** | Bảo vệ dữ liệu trong kết nối. | Token lộ trong log/storage. |

Một token có thể có:

~~~text
aud = payments-api
scope = payments:reconcile
cnf = sender binding theo profile
exp = thời hạn ngắn
~~~

Payments API cần kiểm **aud** và **bằng chứng sender** nếu profile yêu cầu. Không tắt aud validation chỉ vì đã bật mTLS/DPoP.

**Bearer token có thể bị phát lại tại đúng audience** nếu bị lấy trộm và còn hạn. TTL, storage, sender binding, revocation và authorization theo resource vẫn cần thiết.

## 21. Gateway, service mesh và audience

Nhiều hệ thống dùng API Gateway:

~~~mermaid
flowchart LR
    C["Machine Client"] -->|"AT aud=orders-api"| G["API Gateway"]
    G -->|"Trusted context/hop"| O["Orders Service"]
    G -->|"Other route"| P["Payments Service"]
    G -.->|"JWKS / introspection tin cậy"| AS["Authorization Server"]
    O --> DB[("Orders DB")]
~~~

Hai phương án:

**A. Mỗi RS tự kiểm token.** Gateway định tuyến, rate limit; Orders/Payments kiểm issuer, aud, type, scope và permission độc lập.

**B. Gateway kiểm token và chuyển context đã xác minh.** Backend chỉ được dựa vào context đó nếu **gateway không thể bị bypass**, giao tiếp nội bộ được xác thực/bảo vệ và client bên ngoài không thể giả mạo header nội bộ.

Ví dụ header không thể tin từ Internet:

~~~http
X-Audience: orders-api
X-Authenticated-Client: trusted-worker
X-Authorized-Scope: orders:read
~~~

Gateway phải **xóa/ghi đè** header đáng tin cậy do client gửi, backend có trust contract rõ. **mTLS của hop gateway→service không thay audience check ở ingress**.

### Gateway là RS hay backend mới là RS?

Tùy kiến trúc, gateway có thể là **một logical RS** hoặc mỗi backend là **RS có audience riêng**. Không có quy tắc chung suy audience từ hostname gateway. Cần định nghĩa resource identifier và trách nhiệm kiểm ở từng boundary, không tự bỏ aud khi route thay đổi.

## 22. Những lỗi cấu hình phổ biến

| Lỗi | Hậu quả | Biện pháp |
| --- | --- | --- |
| AS phát access token **thiếu aud** khi profile yêu cầu. | RS không xác định recipient. | Chọn audience theo resource policy trước khi ký. |
| AS copy nguyên **resource tùy ý** vào aud. | Client tự xin token cho API không được phép. | Registry/allowlist và kiểm client-resource-scope. |
| RS chỉ kiểm **chữ ký + issuer + exp**. | Token cho API khác được chấp nhận. | Audience validation bắt buộc. |
| RS kiểm aud bằng **prefix/substring**. | Nhầm resource tên gần giống. | Exact identifier theo cấu hình. |
| RS lấy expected aud từ **Host header**. | Client có thể ảnh hưởng policy. | Expected audience từ server config. |
| RS chấp nhận **ID token** làm AT. | Token substitution. | Kiểm token type/profile và audience. |
| RS chấp nhận **RT** ở API. | Sai mục đích, làm lộ credential dài hạn. | Chỉ nhận access token phù hợp. |
| Client cache token **chỉ theo client_id**. | Gửi nhầm token giữa API. | Cache phân biệt resource/audience/scope. |
| Worker dùng **scope=read** thay kiểm aud. | Scope confusion xuyên API. | Kiểm aud và scope độc lập. |
| AS cấp **aud=all-apis**. | Mở rộng phạm vi lạm dụng. | Ưu tiên per-resource tokens. |
| Microservice **forward token sai aud**. | Downstream nhận sai credential. | Token riêng hoặc exchange theo policy. |
| AS tin authenticated client là **admin toàn hệ thống**. | Client auth bị nhầm thành authorization. | Grant/resource/scope policy riêng. |
| Introspection trả **active=true**, RS bỏ qua aud. | Opaque token cũng bị dùng nhầm API. | Kiểm aud trong metadata đáng tin. |
| Cache introspection quá lâu. | Chậm phản ánh revocation. | TTL/SLA phù hợp. |
| RS aud đúng nhưng **không kiểm tenant**. | BOLA/IDOR. | Policy nghiệp vụ theo dữ liệu hiện hành. |
| Middleware kiểm aud lỗi rồi **fail-open**. | Cho phép request không xác minh được. | Fail closed. |

## 23. Kịch bản sự cố: Orders token bị chấp nhận ở Payments

Một tổ chức phát hiện reporting-worker vốn chỉ có quyền đọc Orders nhưng có thể gọi endpoint Payments.

Cấu hình:

~~~text
Token:
    iss = identity.example.test
    aud = orders-api
    scope = read
    signature valid

Payments API:
    verify signature
    verify expiration
    verify scope == read
    // Không kiểm audience
~~~

**Nguyên nhân gốc:** Payments API bỏ qua audience restriction. AS có thể đã phát token đúng policy, nhưng RS chấp nhận sai recipient.

Quy trình khắc phục:

1. Bổ sung kiểm **expected aud=payments-api** trên token đã xác minh.
2. Rà soát các RS/gateway/middleware khác có bỏ kiểm aud không.
3. Kiểm token type, issuer, key/algorithm allowlist và scope policy.
4. Rà soát ma trận cấp token của AS theo client/resource/scope.
5. Điều tra token hoặc client credential có bị lộ hay bị lạm dụng; revoke/rotate theo phạm vi.
6. Sửa cache key để không trả nhầm token khác audience.
7. Thêm regression test token Orders → Payments phải bị từ chối.
8. Ghi audit **audience mismatch** bằng metadata an toàn, không log raw AT.

**Bài học:** AS phát đúng token vẫn không đủ nếu RS không từ chối token được phát cho bên khác.

## 24. Negative tests

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| **Client/resource/scope đúng** | reporting-worker xin Orders + orders:read. | AS cấp token theo policy. |
| **Resource ngoài allowlist** | reporting-worker xin Payments. | AS từ chối. |
| **Scope ngoài quyền** | reporting-worker xin orders:approve. | Không cấp scope vượt quyền. |
| **Resource URI sai** | URI không absolute hoặc chứa fragment theo RFC 8707. | AS từ chối theo profile. |
| **Host giống tên** | orders.example.test.attacker.test. | Không được coi là Orders API. |
| **Thiếu resource** | Không có default resource an toàn. | AS không cấp token đa API tùy tiện. |
| **Nhiều resource** | Xin Orders + Payments nhưng policy không cho. | Từ chối hoặc xử lý đúng hợp đồng. |
| **Client auth sai** | Wrong private key/secret/cert. | Không cấp token. |
| **Grant không được phép** | Client chưa đăng ký client_credentials. | Từ chối unauthorized_client. |
| **JWT aud đúng** | AT Orders hợp lệ gửi Orders. | Tiếp tục kiểm scope/permission. |
| **JWT aud sai** | AT Orders gửi Payments. | **401 invalid_token** theo Bearer profile. |
| **JWT thiếu aud** | Token profile yêu cầu aud. | Từ chối. |
| **aud prefix** | aud=orders-api-backup tại Orders. | Từ chối. |
| **aud khác canonical form** | URI khác identifier đã đăng ký. | Từ chối nếu không có mapping tin cậy. |
| **aud array nhưng single-aud policy** | Token chứa Orders và Payments. | RS từ chối theo policy. |
| **Multi-aud được cho phép** | Đúng RS trong aud và đúng scope. | Có thể tiếp tục các bước authz khác. |
| **Issuer sai** | Token đúng aud nhưng issuer lạ. | Từ chối. |
| **Chữ ký sai** | Sửa aud trong payload JWT. | Từ chối chữ ký. |
| **Token hết hạn** | exp qua rồi, aud vẫn đúng. | Từ chối. |
| **ID token thay AT** | ID token gửi như Bearer AT. | Từ chối token type/audience. |
| **Opaque active=true, aud sai** | Introspection trả Payments cho request Orders. | Orders từ chối. |
| **Opaque thiếu aud** | Profile yêu cầu nhưng không có audience metadata. | Không chấp nhận. |
| **Introspection lỗi** | AS unavailable hoặc caller không được phép. | Fail-safe, không mặc định active. |
| **Cache lẫn resource** | Worker gọi Orders rồi Payments. | Cache không trả token Orders cho Payments. |
| **Forwarding sai aud** | Orders chuyển token Orders sang Payments. | Payments từ chối. |
| **Service-user confusion** | Client_credentials token gọi endpoint chỉ dành End-User. | Từ chối theo principal type/policy. |
| **Cross-tenant** | AT aud/scope đúng, resource thuộc tenant khác. | RS từ chối theo resource policy. |
| **Sender proof sai** | Token DPoP/mTLS-bound gửi không đúng proof. | Từ chối theo profile. |
| **Client bị rút grant** | AS không còn cho client gọi Payments. | Không cấp token mới; RS theo SLA revoke. |
| **Header giả** | Client gửi X-Audience=orders-api. | Không thay đổi kết quả xác minh token. |

### Test chéo hai Resource Server

~~~text
TokenOrders:
    aud = orders-api
    scope = orders:read

TokenPayments:
    aud = payments-api
    scope = payments:reconcile

A. TokenOrders -> Orders API      => có thể tiếp tục authz
B. TokenOrders -> Payments API    => DENY
C. TokenPayments -> Payments API  => có thể tiếp tục authz
D. TokenPayments -> Orders API    => DENY
~~~

Các trường hợp ghi **có thể tiếp tục authz** không mặc định trả HTTP 200. RS còn kiểm scope/permission và dữ liệu thực tế.

## 25. Checklist review trước production

1. **Resource identifier:** Mỗi RS có audience identifier chính thức, thống nhất giữa AS và RS?
2. **Client registration:** Có grant allowlist, client auth method, resource allowlist và scope theo resource?
3. **Client authentication:** AS thật sự xác thực confidential client bằng phương thức đăng ký?
4. **Resource indicator:** Nếu dùng RFC 8707, AS parse resource, kiểm absolute URI/fragment và mapping đúng profile?
5. **Default audience:** Khi thiếu resource, AS có default cụ thể an toàn hoặc từ chối?
6. **Policy cấp phát:** Có kiểm **client + resource + scope**, không cho client tự chọn aud bất kỳ?
7. **Token format:** JWT hoặc opaque được chọn theo yêu cầu kiểm trạng thái/thu hồi?
8. **JWT validation:** Có issuer, chữ ký, thuật toán/khóa tin cậy, exp, type và audience?
9. **Opaque validation:** Introspection được bảo vệ, RS kiểm active và audience đúng?
10. **Type isolation:** ID token và refresh token không được dùng thay access token?
11. **Exact aud:** RS không dùng prefix, substring, scope hoặc Host thay expected audience?
12. **Single/multi aud:** Chính sách audience array rõ, không mặc định tin token đa API?
13. **Scope:** RS kiểm scope chính xác của endpoint sau kiểm audience?
14. **Service identity:** Client_credentials token không bị nhầm là End-User session?
15. **Tenant/resource permission:** RS kiểm quyền trên bản ghi thực tế, không chỉ aud/scope?
16. **Downstream:** Service không forward token sai audience; có token riêng/exchange theo policy?
17. **Cache:** Token cache phân biệt issuer/client/resource/scope và còn hạn?
18. **TTL/revocation:** Có giới hạn token lifetime, SLA rút quyền client và kế hoạch cache invalidation?
19. **Sender binding:** DPoP/mTLS nếu dùng được kiểm đúng và không thay audience validation?
20. **TLS:** Client–AS/RS và RS–introspection dùng HTTPS với xác minh certificate/hostname?
21. **Gateway:** Không bypass được audience validation bằng route/headers; hop nội bộ có trust contract?
22. **Observability:** Log lỗi aud mismatch và policy decision mà không log raw token/secret?
23. **Negative tests:** Test chéo Orders/Payments, sai aud, thiếu aud, sai scope, multi-aud, cache lẫn resource và cross-tenant?

## Kết luận

**Audience restriction buộc access token chỉ được sử dụng tại Resource Server mà Authorization Server dự định cấp cho.** Trong **client_credentials**, việc một workload xác thực thành công không đủ để được gọi mọi API: AS phải giới hạn **resource và scope theo client registration/policy**, còn RS phải kiểm audience **độc lập với chữ ký, issuer và scope**.

**RFC 8707 resource indicator** cho phép client chỉ rõ tài nguyên muốn gọi, nhưng đây là **yêu cầu cần được AS phê duyệt**, không phải quyền tự chọn recipient. Token cho Orders API phải bị Payments API từ chối. Khi service gọi downstream, dùng token đúng audience hoặc token exchange hợp lệ thay vì tắt kiểm audience.

Audience restriction là một lớp bảo vệ quan trọng nhưng không thay TLS, hạn token, bảo vệ credential, sender-constraining, revocation hay authorization theo tenant/tài nguyên. Trong buổi review, câu hỏi quan trọng nhất là: **“AS cấp token này cho API nào, và mỗi API có thực sự từ chối token dành cho nơi khác không?”**

### Tài liệu tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 4.4: Client Credentials](https://www.rfc-editor.org/rfc/rfc6749#section-4.4)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JSON Web Token Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
