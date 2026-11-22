# Kiểu dữ liệu, giá trị rỗng, claims thiếu và token bị từ chối

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, việc xác minh chữ ký JWT mới chỉ chứng minh rằng payload không bị sửa trái phép bằng khóa ký đã được tin cậy. Để cho một request truy cập API, hệ thống còn phải quyết định **claims nào bắt buộc**, **kiểu dữ liệu và giá trị nào được chấp nhận**, và **token phải bị từ chối như thế nào khi claim bị thiếu, rỗng, sai kiểu hoặc sai ngữ nghĩa**.

Đây là một ranh giới bảo mật quan trọng: một JWT có **chữ ký hợp lệ** vẫn có thể gây lỗi hoặc tạo điều kiện vượt quyền nếu Resource Server đọc nhầm kiểu dữ liệu, chấp nhận giá trị mặc định thiếu an toàn, hoặc bỏ qua claim mà API thực sự cần.

Bài học trình bày nguyên tắc thiết kế schema cho JWT claims, phân biệt **missing / JSON null / empty / malformed**, cách dùng **JwtDecoder**, **OAuth2TokenValidator** và authorization trong Spring Security, cùng các kịch bản kiểm thử token bị từ chối. Ví dụ sử dụng **Spring Boot 3.x, Spring Security 6.x, Java 17+**, Resource Server Servlet, và một API **orders-api** chỉ tin JWT Access Token của issuer được cấu hình.

## 1. Chữ ký hợp lệ không có nghĩa claims hợp lệ

Giả sử Authorization Server phát hành JWT Access Token với payload:

~~~json
{
  "iss": "https://login.example.test/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "exp": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-42",
  "roles": ["ORDER_READER"]
}
~~~

Những câu hỏi Resource Server phải xử lý không chỉ là “chữ ký đúng không?”:

1. **Issuer** có đúng nhà phát hành đáng tin cậy không?
2. **Audience** có chỉ định **orders-api** không?
3. Token có được phát hành theo profile mà API nhận không, và có còn hiệu lực không?
4. **tenant_id** có phải chuỗi không rỗng, và có khớp tenant của tài nguyên không?
5. **roles** có đúng kiểu mảng chuỗi, chứa vai trò được cho phép không?
6. **scope** có đúng cách biểu diễn theo hợp đồng token không, và có quyền đọc đơn hàng không?

JWT được ký chỉ bảo vệ claims **do bên ký đưa vào token**. Nếu issuer và Resource Server không thống nhất schema, một giá trị được ký hợp lệ vẫn có thể sai về mặt nghiệp vụ. Ngay cả khi decoder chấp nhận JWT, bước **authorization** vẫn phải bảo đảm token không dùng để truy cập dữ liệu ngoài phạm vi.

~~~text
Authorization: Bearer <jwt>
             |
             v
    Xác minh chữ ký / thuật toán / khóa
             |
             v
    Kiểm tra registered claims
    iss, aud, exp, nbf, ...
             |
             v
    Kiểm tra hợp đồng custom claims
    tenant_id, roles, scope,...
             |
             v
    Authentication được chấp nhận
             |
             v
    Authorization theo scope, tenant và tài nguyên
             |
          Cho phép hoặc từ chối
~~~

Hai bước **token validation** và **authorization** có quan hệ nhưng không đồng nhất:

- Token thiếu một claim **bắt buộc để được chấp nhận** có thể bị từ chối ở **authentication**, thường là **401 Unauthorized**.
- Token hợp lệ nhưng không có **quyền** thực hiện thao tác thường bị từ chối ở **authorization**, thường là **403 Forbidden**.

Để phân biệt đúng, trước tiên phải định nghĩa **schema và chính sách** của từng claim.

## 2. JSON có những loại giá trị nào?

JWT Claims Set về cơ bản là một **JSON object** gồm các cặp tên–giá trị. JSON cho phép:

| Kiểu JSON | Ví dụ | Ý nghĩa trong JWT |
| --- | --- | --- |
| **string** | `"tenant-42"` | Định danh issuer, subject, tenant, scope text... tùy claim. |
| **number** | `1893456000` | Thời điểm NumericDate, bộ đếm hoặc giá trị số được profile định nghĩa. |
| **boolean** | `true` | Cờ trạng thái, ví dụ `email_verified` trong OIDC. |
| **array** | `["orders-api", "reports-api"]` | Nhiều audience, roles, permissions... |
| **object** | `{"region":"apac"}` | Cấu trúc lồng nhau theo một contract rõ ràng. |
| **null** | `null` | Giá trị null; không tương đương với một giá trị hợp lệ tự động. |

Ngoài **kiểu**, nhiều claim có quy định riêng:

- `iss` là **string** theo RFC 7519.
- `sub` là **string**, cần diễn giải trong ngữ cảnh issuer.
- `aud` có thể là **string** hoặc **array of strings** theo RFC 7519.
- `exp`, `nbf`, `iat` là **NumericDate**, biểu diễn bằng **JSON number** (giây tính từ Unix epoch), không phải string ngày tháng.
- `scope` thường là **chuỗi cách nhau bởi khoảng trắng** trong các JWT Access Token profile phù hợp; một số nhà cung cấp dùng `scp` với cách biểu diễn khác, cần hợp đồng riêng.
- `roles`, `tenant_id`, `permissions` là những tên custom thường gặp nhưng **không có một kiểu JSON duy nhất áp dụng cho mọi issuer**.

**Không được cho rằng tên claim “trông quen” thì kiểu dữ liệu tự động đúng.** Ví dụ một issuer dùng `roles: ["ORDER_READER"]`, issuer khác dùng `roles: "ORDER_READER"`. Nếu API chấp nhận cả hai mà không có hợp đồng rõ, việc cấp quyền có thể không nhất quán.

## 3. Phân biệt claim thiếu, JSON null, rỗng và sai kiểu

Những trường hợp sau khác nhau về bản chất:

| Tình huống | Ví dụ claim `tenant_id` | Cách hiểu |
| --- | --- | --- |
| **Missing** | Không có khóa `tenant_id` trong JSON. | Issuer không đưa claim vào token. |
| **JSON null** | `"tenant_id": null` | Khóa có mặt nhưng không có giá trị. |
| **Empty string** | `"tenant_id": ""` | Chuỗi dài 0 ký tự. |
| **Whitespace only** | `"tenant_id": "   "` | Chuỗi không có nội dung hữu ích sau khi xét khoảng trắng. |
| **Wrong type** | `"tenant_id": 42` | Số thay vì chuỗi. |
| **Wrong structure** | `"tenant_id": ["tenant-42"]` | Mảng thay vì một định danh tenant. |
| **Unexpected value** | `"tenant_id": "tenant-99"` | Đúng kiểu nhưng có thể không được phép với tài nguyên đang truy cập. |

Trường hợp **roles** cũng có nhiều biến thể:

~~~json
{"roles": ["ORDER_READER"]}
~~~

~~~json
{"roles": []}
~~~

~~~json
{"roles": [""]}
~~~

~~~json
{"roles": null}
~~~

~~~json
{"roles": "ORDER_READER"}
~~~

Nếu profile API yêu cầu **một danh sách role không rỗng và mọi phần tử là chuỗi hợp lệ**, chỉ cấu trúc đầu tiên đáp ứng ví dụ này. `[]` có thể là một giá trị hợp lệ ở **hợp đồng khác** với ý nghĩa “không có role”, nhưng không được mặc nhiên coi nó là quyền truy cập. Chính sách cho phép thiếu hoặc rỗng phải được quy định rõ theo từng trường.

### 3.1. Quy tắc fail-closed

**Fail-closed** nghĩa là khi hệ thống không thể chắc chắn một credential đáp ứng quy tắc bắt buộc, mặc định **không cấp quyền**.

Đối với một claim bắt buộc:

~~~text
Claim bắt buộc có mặt?
  | Không -> Từ chối token
  |
  Có
  v
Giá trị khác null và đúng kiểu?
  | Không -> Từ chối token
  |
  Có
  v
Đáp ứng ràng buộc không rỗng, miền giá trị?
  | Không -> Từ chối token
  |
  Có
  v
Đối chiếu policy / tài nguyên thực tế
  | Không -> Từ chối truy cập
  |
  Có -> Có thể cho phép theo các điều kiện còn lại
~~~

Một claim **tùy chọn** không nhất thiết làm token bị từ chối khi vắng mặt. Tuy nhiên, **vắng mặt không được tự biến thành quyền cao hơn**. Ví dụ thiếu `roles` có thể ánh xạ thành **không role** nếu contract cho phép, nhưng không được tự gán `ADMIN` hoặc bỏ qua kiểm tra tenant.

### 3.2. “Thiếu” và “null” khi đã vào Java

Khi JWT được giải mã thành `Map<String, Object>`, có thể kiểm tra sự tồn tại của key:

~~~java
Map<String, Object> claims = jwt.getClaims();
boolean present = claims.containsKey("tenant_id");
Object value = claims.get("tenant_id");
~~~

- Nếu `present == false`, tên claim không có trong map.
- Nếu `present == true` và `value == null`, map có một giá trị null.
- Tuy nhiên một số bước JSON parsing, claim conversion hoặc thư viện có thể **loại bỏ/chuẩn hóa null**, nên hai trạng thái có thể trở nên khó phân biệt sau giải mã.

Nếu contract thực sự phải phân biệt **JSON key không tồn tại** với **key có null** ở mức dữ liệu gốc, kiểm tra tại lớp parsing/claim conversion phù hợp và viết test dùng **JWT đã ký thật**. Với bảo mật, hai trường hợp thường cùng bị từ chối khi claim là bắt buộc.

## 4. Registered claims: không phải tất cả đều bắt buộc trong RFC 7519

RFC 7519 định nghĩa các **Registered Claim Names**: `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`. Tuy nhiên, **RFC 7519 không bắt buộc mọi JWT phải có tất cả bảy claim**. Quy tắc bắt buộc phụ thuộc **token profile** và chính sách của hệ thống nhận token.

Ví dụ **OIDC ID Token** có các yêu cầu riêng theo OIDC; **JWT Access Token profile (RFC 9068)** có yêu cầu khác dành cho Resource Server. Đừng sao chép logic kiểm tra ID Token để dùng cho Access Token mà không xét audience, typ và profile.

| Claim | JSON type và quy tắc cơ bản | Điều cần xét khi thiếu hoặc sai |
| --- | --- | --- |
| **iss** | String định danh issuer. | Resource Server có issuer tin cậy cần từ chối token không có/sai issuer. |
| **sub** | String định danh subject. | Có thể được profile yêu cầu; không suy ra người dùng từ email nếu sub thiếu. |
| **aud** | Một string hoặc array các string. | API có audience bắt buộc phải từ chối token không chứa audience của mình. |
| **exp** | NumericDate. | Nếu profile API yêu cầu exp, token thiếu exp phải bị từ chối. |
| **nbf** | NumericDate nếu có. | Token chưa đến thời điểm nbf phải bị từ chối, có thể xét clock skew nhỏ. |
| **iat** | NumericDate nếu có. | Nếu profile yêu cầu iat, phải bác claim thiếu/sai; iat không thay thế exp. |
| **jti** | String định danh token nếu có. | Không tự ngăn replay nếu không có cơ chế kiểm tra/lưu trạng thái bổ sung. |

### 4.1. `aud`: string và array đều có thể hợp lệ

Hai JWT Claims Set sau đều biểu diễn audience dành cho `orders-api` theo RFC 7519:

~~~json
{"aud": "orders-api"}
~~~

~~~json
{"aud": ["orders-api", "reports-api"]}
~~~

Các ví dụ khác không phù hợp với chính sách “audience phải chứa orders-api”:

~~~json
{"aud": []}
~~~

~~~json
{"aud": ["billing-api"]}
~~~

~~~json
{"aud": 123}
~~~

~~~json
{"aud": null}
~~~

**Đừng viết validator giả định `aud` luôn là một chuỗi** rồi dùng `equals` để so với `"orders-api"`; như vậy có thể từ chối nhầm array hợp lệ hoặc xử lý sai cấu trúc khác. Spring Security `Jwt.getAudience()` cung cấp danh sách audience theo dữ liệu đã được decoder chuyển đổi:

~~~java
if (!jwt.getAudience().contains("orders-api")) {
    // Không chấp nhận token dành cho resource khác.
}
~~~

Nếu yêu cầu phải kiểm tra **kiểu JSON gốc** rất nghiêm ngặt, cần chú ý decoder có thể **chuẩn hóa registered claims** trong lúc chuyển từ JSON sang `Jwt`. Phân tích kiểm thử qua decoder thật, không chỉ tạo `Jwt` giả với claims đã được chuẩn hóa.

### 4.2. `exp`: thiếu có thể là rủi ro dù token “chưa hết hạn”

Hai trường hợp khác nhau:

~~~json
{"exp": 1893456000}
~~~

~~~json
{"exp": null}
~~~

Và một token **không có `exp`** hoàn toàn. Nếu chính sách API yêu cầu Access Token **phải có thời hạn**, token thiếu hoặc null `exp` cần bị từ chối.

Một số validator timestamp được thiết kế để kiểm tra **`exp` khi nó tồn tại**, chứ không nhất thiết bắt buộc mọi JWT có claim này. Do đó:

> **Không coi kiểm tra “exp đã hết hạn chưa?” là tương đương với kiểm tra “exp có tồn tại và hợp lệ không?”**

Nếu contract yêu cầu `exp`, cần thêm điều kiện kiểm tra **presence** bên cạnh kiểm tra thời gian. Tương tự với `iat` nếu token profile bắt buộc phát hành thời điểm.

### 4.3. NumericDate: giây, không phải chuỗi ngày hoặc mili-giây

`exp`, `iat`, `nbf` sử dụng **NumericDate**: số giây kể từ 1970-01-01T00:00:00Z (theo ngữ nghĩa RFC 7519). Ví dụ:

~~~json
{
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000
}
~~~

Không đánh đồng với:

~~~json
{"exp": "2030-01-01T00:00:00Z"}
~~~

~~~json
{"exp": 1893456000000}
~~~

Ví dụ đầu là **chuỗi ISO-8601**, không phải JSON number NumericDate; ví dụ thứ hai trông giống **mili-giây**, có thể làm token tồn tại quá lâu nếu bị diễn giải thành giây. API không nên tự “đoán” đơn vị hoặc chuyển chuỗi bất kỳ thành thời hạn rồi chấp nhận token.

Khi Spring Security `NimbusJwtDecoder` tạo đối tượng `Jwt`, những claim thời gian tiêu chuẩn thường được chuyển thành **`Instant`**. Do đó kiểm tra trên `Jwt.getClaims().get("exp")` có thể thấy một kiểu Java đã chuẩn hóa, **không còn là JSON number gốc**. Đừng nhầm schema JSON với kiểu object Java sau khi thư viện chuyển đổi.

Nếu yêu cầu bảo mật phải bác **JSON type sai ngay từ dữ liệu gốc**, cần kiểm thử bằng JWT được ký thực sự, xem xét claim-set converter/decoder và chính sách profile; không chỉ kiểm tra object `Jwt` được dựng thủ công.

### 4.4. `iss`: có mặt nhưng sai giá trị vẫn phải từ chối

Ví dụ API chỉ tin:

~~~text
https://login.example.test/realms/demo
~~~

Các giá trị sau đều cần được xem xét không phù hợp với chính sách issuer đó:

~~~json
{"iss": ""}
~~~

~~~json
{"iss": "https://login.example.test/realms/other"}
~~~

~~~json
{"iss": "https://login.example.test/realms/demo/"}
~~~

String thứ ba khác issuer gốc bởi dấu **/** cuối URI. Không tự cắt path hoặc làm gần đúng rồi coi mọi issuer cùng hostname là đáng tin. Hãy dùng **issuer identifier do Authorization Server công bố** và validator được cấu hình rõ.

## 5. Custom claims: schema phải do hệ thống xác định

Giả sử **orders-api** có hợp đồng Access Token sau:

| Claim | Kiểu bắt buộc | Bắt buộc? | Quy tắc |
| --- | --- | --- | --- |
| **iss** | String/URI | Có | Đúng issuer được tin cậy. |
| **aud** | String hoặc array of strings | Có | Phải chứa `orders-api`. |
| **exp** | NumericDate | Có | Chưa hết hạn tại thời điểm request. |
| **iat** | NumericDate | Có | Phải tồn tại theo token profile này. |
| **scope** | String | Có | Không rỗng; quyền kiểm tra theo endpoint. |
| **tenant_id** | String | Có | Không rỗng; chỉ định tenant phát hành quyền. |
| **roles** | Array of strings | Có trong ví dụ này | Mảng không rỗng; từng phần tử là role hợp lệ. |

Đây là **contract ví dụ** cho một hệ thống cụ thể, không phải quy tắc JWT áp dụng toàn cầu. Một API khác có thể cho `roles` là tùy chọn hoặc dùng `scp` thay `scope`; khi đó cần định nghĩa lại contract và validator tương ứng.

### 5.1. Sai kiểu nguy hiểm hơn việc “không lấy được dữ liệu”

Những token có chữ ký hợp lệ nhưng claim custom khác schema có thể gồm:

~~~json
{"tenant_id": 42}
~~~

~~~json
{"tenant_id": ""}
~~~

~~~json
{"roles": "ORDER_READER"}
~~~

~~~json
{"roles": ["ORDER_READER", 99]}
~~~

~~~json
{"roles": ["ORDER_READER", null]}
~~~

Không nên ép kiểu tự động bằng `String.valueOf(claim)` rồi coi `42` là tenant ID hợp lệ, hoặc chuyển một object tùy ý thành role string. Quy tắc nhận dạng phải căn cứ schema đã thống nhất. Với mảng role, cần xác minh **mọi phần tử**, không chỉ phần tử đầu tiên.

### 5.2. Empty array không đồng nghĩa toàn quyền

Giả sử issuer phát hành:

~~~json
{
  "scope": "",
  "roles": []
}
~~~

Nếu `roles` là claim tùy chọn và một mảng rỗng có nghĩa **không có quyền**, Resource Server có thể giữ token ở trạng thái xác thực nhưng từ chối truy cập endpoint đặc quyền bằng **403**. Nếu profile yêu cầu role phải có ít nhất một phần tử thì token có thể bị từ chối ngay tại validator bằng **401**.

**Hai chính sách đều có thể hợp lệ trong những hệ thống khác nhau**, nhưng phải cố định theo contract. Không dùng quy tắc như “nếu roles rỗng thì bỏ qua kiểm tra role”.

### 5.3. Tránh nhầm `false`, `0`, `""` và `null`

Trong JSON, các giá trị sau hoàn toàn khác nhau:

~~~json
{
  "email_verified": false,
  "login_count": 0,
  "display_name": "",
  "approval": null
}
~~~

Đừng dùng logic JavaScript-like “truthy/falsy” để kiểm tra tất cả claims: **false** hoặc **0** có thể là giá trị hợp lệ có ý nghĩa; **null** hoặc thiếu claim mới là điều kiện khác. Spring Security nhận claims như các object Java có kiểu tương ứng, nên nên dùng **kiểm tra kiểu và giá trị tường minh**.

Ví dụ một thuộc tính nghiệp vụ `can_export` chỉ được coi là cho phép khi thực sự là boolean `true`; không coi string `"true"` hoặc số `1` là tương đương nếu contract định nghĩa kiểu boolean.

## 6. Đọc claims trong Spring Security mà không che giấu sai kiểu

Sau khi `JwtDecoder` thành công, Spring Security cung cấp đối tượng `Jwt`. Một số API thường dùng:

~~~java
String subject = jwt.getSubject();
String tenantId = jwt.getClaimAsString("tenant_id");
List<String> roles = jwt.getClaimAsStringList("roles");
Map<String, Object> claims = jwt.getClaims();
~~~

Các tiện ích `getClaimAsString`, `getClaimAsStringList` giúp truy cập thuận tiện, nhưng **không nên xem chúng là một bộ kiểm tra schema hoàn chỉnh**. Tùy kiểu dữ liệu đầu vào và quá trình claim conversion, giá trị có thể được chuyển đổi hoặc phát sinh lỗi khi không tương thích.

Khi bắt buộc **tenant_id là JSON string**, nên đọc và kiểm tra object gốc ở map sau decoder cho claim custom:

~~~java
Object rawTenant = jwt.getClaims().get("tenant_id");
if (!(rawTenant instanceof String tenantId)
        || tenantId.isBlank()) {
    // Claim không đúng contract; yêu cầu phải bị từ chối.
}
~~~

Với role array:

~~~java
Object rawRoles = jwt.getClaims().get("roles");

if (!(rawRoles instanceof List<?> roleList)
        || roleList.isEmpty()) {
    // Không đúng contract.
}
~~~

Nếu mảng có mặt, vẫn phải kiểm tra kiểu và nội dung **từng phần tử**. Đừng cast `(List<String>) rawRoles` rồi chỉ hy vọng phần tử đều là string: generic type bị xóa tại runtime, một mảng chứa number có thể qua phép cast ở mức danh sách và chỉ lỗi khi sử dụng phần tử.

**Giới hạn quan trọng:** `Jwt.getClaims()` là dữ liệu **sau bước chuyển đổi của decoder**. Với claim standard như `exp`, `aud`, thư viện có thể chuẩn hóa kiểu; với custom claim thường giữ cấu trúc tương ứng JSON nhưng vẫn phụ thuộc claim-set converter. Nếu cần kiểm tra chính xác JSON type gốc trước conversion, cấu hình chính sách tại ranh giới parse/decode và kiểm thử đầu vào ký thật.

## 7. Viết validator fail-closed cho claims bắt buộc

Trong Spring Security, interface **`OAuth2TokenValidator<Jwt>`** cho phép định nghĩa một quy tắc nhận/chặn JWT ở bước xác thực. Nếu trả về **`OAuth2TokenValidatorResult.failure(...)`**, `JwtDecoder` xem token không hợp lệ và Bearer request thường bị từ chối bằng **401**.

Giả sử contract ví dụ yêu cầu:

1. `exp` và `iat` phải tồn tại sau khi decoder tạo `Jwt`.
2. `aud` phải chứa `orders-api`.
3. `tenant_id` phải là string không blank.
4. `roles` phải là mảng **không rỗng**, mọi phần tử là string không blank.
5. `scope` phải là string không blank theo định dạng issuer đã thỏa thuận.

### 7.1. Custom validator

Ví dụ class **`RequiredApiClaimsValidator.java`**:

~~~java
import java.util.List;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class RequiredApiClaimsValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public RequiredApiClaimsValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {

        // presence khác với expiration check.
        if (jwt.getExpiresAt() == null) {
            return invalid("Required expiration time is missing");
        }
        if (jwt.getIssuedAt() == null) {
            return invalid("Required issued-at time is missing");
        }

        if (!jwt.getAudience().contains(requiredAudience)) {
            return invalid("Required audience is missing");
        }

        Object tenant = jwt.getClaims().get("tenant_id");
        if (!(tenant instanceof String tenantId)
                || tenantId.isBlank()) {
            return invalid("Invalid tenant claim");
        }

        Object roles = jwt.getClaims().get("roles");
        if (!(roles instanceof List<?> roleList)
                || roleList.isEmpty()) {
            return invalid("Invalid roles claim");
        }

        for (Object role : roleList) {
            if (!(role instanceof String roleName)
                    || roleName.isBlank()) {
                return invalid("Invalid roles claim");
            }
        }

        Object scope = jwt.getClaims().get("scope");
        if (!(scope instanceof String scopeValue)
                || scopeValue.isBlank()) {
            return invalid("Invalid scope claim");
        }

        return OAuth2TokenValidatorResult.success();
    }

    private static OAuth2TokenValidatorResult invalid(String message) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", message, null));
    }
}
~~~

Đoạn code có chủ ý kiểm tra **object** thay vì chỉ lấy string đã ép kiểu. Vì **roles** là claim custom nên kiểm tra `List<?>` cùng từng phần tử; vì **exp/iat** được decoder chuẩn hóa thành `Instant` nên kiểm tra bằng `jwt.getExpiresAt()` và `jwt.getIssuedAt()`.

Đây là **quy tắc cho token profile ví dụ**, không phải yêu cầu của mọi JWT. Nếu API không yêu cầu roles trên mọi request, có thể thiết kế claim đó tùy chọn và chỉ kiểm tra role khi authorization cần, nhưng **không được tạo quyền mặc định khi thiếu**.

Một hệ thống production có thể bổ sung:

- Kiểm tra `tenant_id` thuộc cú pháp/miền định danh đã quy ước.
- Kiểm tra tên role nằm trong một tập hợp vai trò có nghĩa với API.
- Kiểm tra những scope token mang theo thuộc danh sách scope ứng dụng hỗ trợ, nếu profile yêu cầu.
- Kiểm tra `iat` không ở quá xa tương lai hoặc tuổi token nằm trong giới hạn, khi đó là yêu cầu chính sách.
- Kiểm tra token type/profile khi hệ thống có nhiều loại JWT.

**Không trả nguyên claim gây lỗi** trong `OAuth2Error`, log hoặc HTTP body. Lỗi chỉ cần nêu loại trường không hợp lệ, tránh làm lộ thông tin cá nhân hoặc token. Thông điệp nội bộ cũng nên được xử lý thận trọng tại error handler.

### 7.2. Kết hợp validator của Spring Security với custom validator

Ví dụ cấu hình **`NimbusJwtDecoder`** tải public keys qua JWK Set:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";
    private static final String JWKS =
        "https://login.example.test/realms/demo/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS)
            .build();

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<Jwt>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                new RequiredApiClaimsValidator("orders-api")));

        return decoder;
    }
}
~~~

**`JwtValidators.createDefaultWithIssuer(ISSUER)`** áp dụng các validator mặc định, bao gồm issuer và thời hạn theo cấu hình framework; **`RequiredApiClaimsValidator`** thêm các điều kiện của API, đặc biệt **presence** cho `exp` và `iat`, audience và các claims custom.

Nếu gọi `decoder.setJwtValidator(...)`, bộ validator trước có thể bị thay bằng bộ mới. Vì vậy **không chỉ đặt custom validator và bỏ qua những kiểm tra mặc định**. Cũng cần hạn chế thuật toán ký và nguồn JWKS tin cậy theo hợp đồng với Authorization Server.

Khi tự định nghĩa bean `JwtDecoder`, Spring Boot thường không tự tạo decoder tương đương từ YAML. Không nên cho rằng thuộc tính `audiences` hoặc `issuer-uri` ở `application.yml` sẽ tự gắn các validator vào bean custom; hãy kiểm tra rõ decoder đang được Resource Server dùng.

### 7.3. Nếu dùng cấu hình Boot thay vì bean custom?

Cấu hình JWT Resource Server phổ biến:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Trên Spring Boot phiên bản hỗ trợ `audiences`, những thuộc tính này thiết lập xác thực JWT với issuer và audience dành cho API. Tuy nhiên, **các yêu cầu custom** như `tenant_id` là string không blank hoặc `roles` là list không rỗng **không tự phát sinh chỉ vì có cấu hình issuer**. Cần đưa chúng vào validator/authorization theo contract.

Nếu cần áp nhiều validators mà vẫn muốn tái sử dụng decoder Boot, chọn cách tích hợp phù hợp với phiên bản dự án và làm rõ nơi bộ validator được áp; không khai báo hai bean decoder xung đột nhau.

## 8. Phân biệt validation và authorization để trả 401/403 đúng

Một JWT có thể **hợp lệ về mặt xác thực** nhưng không có đủ scope để truy cập endpoint:

~~~json
{
  "iss": "https://login.example.test/realms/demo",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "orders.read",
  "tenant_id": "tenant-42",
  "roles": ["ORDER_READER"]
}
~~~

Nếu API kiểm tra endpoint `POST /api/orders` cần **`SCOPE_orders.write`**, JWT chỉ có `orders.read` phải nhận **403** sau khi đã xác thực.

### 8.1. SecurityFilterChain mẫu

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Ở ví dụ này:

- **Thiếu/sai Bearer JWT** hoặc thiếu một claim bắt buộc trong decoder → thường là **401**.
- JWT hợp lệ, nhưng thiếu scope cần cho method → **403**.
- JWT hợp lệ, có scope cần thiết → được đi tiếp đến controller, nơi có thể còn kiểm tra quyền theo tenant, owner và tài nguyên.

Spring Security thường ánh xạ `scope` hoặc `scp` thành authorities có tiền tố **`SCOPE_`**. Nếu profile của issuer dùng cấu trúc scope khác, cấu hình **`JwtAuthenticationConverter`** hoặc converter phù hợp. Không tự mặc định claim `roles` là authorities `ROLE_...` khi chưa định nghĩa mapping.

Tắt CSRF trong ví dụ chỉ dành cho API **thuần Bearer header** không dùng session cookie làm credential. Nếu cùng backend có OIDC Login qua cookie/session, cần áp chính sách CSRF riêng theo security chain.

### 8.2. Bảng quyết định lỗi

| Điều kiện | Bước thất bại | HTTP thường dùng |
| --- | --- | --- |
| Không có `Authorization: Bearer` cho endpoint yêu cầu token | Authentication | **401** |
| Token sai chữ ký hoặc ký bằng khóa không tin cậy | Authentication | **401** |
| Token sai issuer/audience hoặc đã hết hạn | Token validation | **401** |
| `tenant_id` là number trong profile bắt buộc string | Token validation | **401** |
| `exp` thiếu dù profile yêu cầu | Token validation | **401** |
| `roles` thiếu dù schema yêu cầu, trước khi xét quyền | Token validation | **401** |
| JWT hợp lệ, thiếu scope đọc/ghi cần thiết | Authorization | **403** |
| JWT hợp lệ, đúng scope nhưng khác tenant tài nguyên | Resource authorization | **403** (hoặc 404 khi chính sách che giấu tài nguyên áp dụng) |
| Token đáp ứng authentication và authorization | Cho phép xử lý | **200/201/...** tùy thao tác |

Không đánh tráo “thiếu một claim cấu trúc bắt buộc” thành “token hợp lệ nhưng thiếu quyền” trừ khi hệ thống **cố ý** định nghĩa claim đó là tùy chọn và điều kiện quyền được đánh giá ở authorization.

### 8.3. Thông báo lỗi không được tiết lộ token

Ví dụ phản hồi ngắn gọn:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json

{"code":"invalid_token","message":"Không thể xác thực yêu cầu."}
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Content-Type: application/json

{"code":"forbidden","message":"Không đủ quyền truy cập."}
~~~

Thông tin `WWW-Authenticate` thực tế phụ thuộc tình huống và handler của Spring Security; không phải lỗi 403 nào cũng cần giống hệt ví dụ. **Không phản chiếu JWT, claim nhạy cảm, exception thô hoặc stack trace** vào header/body. Với Resource Server Servlet, các lỗi tại filter chain có thể xảy ra **trước controller**, vì vậy chỉ dựa vào `@RestControllerAdvice` không đủ để kiểm soát mọi lỗi Bearer authentication.

## 9. Đọc claims an toàn trong controller và dịch vụ nghiệp vụ

Sau khi JWT đã được xác thực, controller có thể lấy principal:

~~~java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/tenants")
public class TenantOrdersController {

    @GetMapping("/{tenantId}/orders")
    Map<String, Object> listOrders(
            @PathVariable String tenantId,
            @AuthenticationPrincipal Jwt jwt) {

        String tokenTenant =
            jwt.getClaimAsString("tenant_id");

        if (tokenTenant == null || !tokenTenant.equals(tenantId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        // Minh họa: lớp nghiệp vụ còn phải kiểm tra
        // tài nguyên thuộc tenant này và scope/role phù hợp.
        return Map.of("tenantId", tenantId, "orders", "[]");
    }
}
~~~

Trong kiến trúc bài học, `RequiredApiClaimsValidator` đã kiểm tra `tenant_id` **đúng kiểu và không blank**. Controller kiểm tra **claim có khớp tài nguyên đang yêu cầu không**. Đó là hai trách nhiệm khác nhau.

Đoạn controller minh họa chỉ mô tả phép so sánh tenant; chưa phải API quản lý đơn hàng đầy đủ và cũng chưa kiểm tra quyền sở hữu bản ghi. Một ứng dụng thật nên thực hiện kiểm tra truy cập dữ liệu ở lớp service/repository theo chính sách nghiệp vụ, tránh lỗi **BOLA/IDOR**.

### 9.1. Tránh cấp quyền theo mặc định khi claim thiếu

Mẫu sau **không an toàn** nếu thiếu `tenant_id` đồng nghĩa được đọc tất cả tenant:

~~~java
// KHÔNG LÀM:
String tenant = jwt.getClaimAsString("tenant_id");
if (tenant == null) {
    return orderService.findAllOrders(); // Mở rộng quyền ngoài ý muốn!
}
~~~

Thay vào đó, nếu schema yêu cầu tenant thì token thiếu tenant phải bị bác ở validator; nếu vẫn có trường hợp cần xử lý tại service, phải **từ chối thao tác** thay vì chuyển sang truy vấn rộng hơn.

### 9.2. Đừng coi dữ liệu từ client là claim đã xác minh

Một request sau không thể tự cấp quyền:

~~~http
GET /api/tenants/tenant-99/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
X-Tenant-Id: tenant-99
X-User-Role: ADMIN
~~~

Header `X-Tenant-Id` và `X-User-Role` do client gửi là **input chưa đáng tin**. Nếu API cần tenant/role, hãy lấy từ JWT đã được xác thực hoặc nguồn authorization được quản lý, rồi đối chiếu với tài nguyên. Việc một JWT có chữ ký hợp lệ cũng không cho phép client tùy ý thay đổi tenant bằng header khác.

## 10. Lỗi claim type có thể xảy ra ở nhiều tầng

Khi một JWT có claims bất thường, hành vi phụ thuộc vào **tầng xảy ra lỗi**:

~~~text
Raw Bearer JWT
    |
    v
1. JOSE/JWT parsing
    |-- JSON sai cú pháp, cấu trúc token lỗi
    |-- Không thể đọc header/claims
    |     -> Authentication thất bại
    v
2. NimbusJwtDecoder / claim conversion
    |-- Không thể chuyển claims tiêu chuẩn
    |-- Kiểu dữ liệu không phù hợp
    |     -> Decode thất bại
    v
3. OAuth2TokenValidator<Jwt>
    |-- Thiếu exp, tenant_id, roles...
    |-- Issuer/audience/time không phù hợp
    |     -> Token validation thất bại
    v
4. JwtAuthenticationConverter
    |-- Chuyển scope/roles sang GrantedAuthority
    v
5. AuthorizationFilter / Method Security
    |-- Thiếu scope, sai tenant, sai quyền tài nguyên
    |     -> 403 / policy response
    v
Controller
~~~

**Không nên dựa vào việc “kiểu sai chắc chắn gây exception”** làm chính sách schema. Một decoder hoặc converter có thể chuyển đổi một số giá trị; phiên bản khác có thể từ chối. Vì thế, những field quan trọng cần **validator có quy tắc tường minh** và kiểm thử bằng JWT thực sự.

### 10.1. Chuẩn hóa claim và rủi ro kiểm tra sai tầng

Spring Security có cơ chế chuyển claims từ Nimbus sang kiểu Java quen thuộc; ví dụ:

- `exp` và `iat` thường được nhìn thấy dưới dạng **`Instant`** trong `Jwt`.
- `aud` thường được nhìn thấy dưới dạng **`List<String>`**.
- Các claim tùy biến như `tenant_id` hoặc `roles` thường giữ dữ liệu tương ứng JSON, trừ khi ứng dụng thay đổi claim conversion.

Nếu ứng dụng cần bác **JSON `exp` là string**, trong khi converter có thể chuyển string sang thời gian, chỉ kiểm tra `jwt.getExpiresAt() != null` **không chứng minh kiểu JSON gốc là number**. Cần áp quy tắc ở nơi còn thấy dữ liệu gốc, hoặc thiết lập converter/decoder có hành vi nghiêm ngặt và test những payload kiểu sai. Không dùng một quy tắc schema dựa trên giả định vô điều kiện về chuyển đổi của thư viện.

### 10.2. Không trộn claims giữa các token profile

Một **OIDC ID Token** có thể chứa `email`, `email_verified`, `nonce`, `auth_time`, nhưng nó dành cho **OIDC Client**, không phải mặc nhiên là Access Token của Resource Server.

Một **OAuth 2.0 JWT Access Token** có thể chứa `client_id`, `scope`, `aud` dành cho API và những claim riêng của issuer. Các yêu cầu về **presence** và **type** cần xuất phát từ **profile thực tế**, không phải một danh sách claims chung lấy từ ID Token.

Đặc biệt, một ID Token có issuer và chữ ký hợp lệ vẫn có thể sai audience và mục đích sử dụng. Resource Server cần từ chối token không dành cho mình.

## 11. Kiểm thử custom validator bằng Jwt giả lập

Để kiểm tra **quy tắc presence/type/value** độc lập với network và chữ ký, có thể tạo đối tượng `Jwt` trực tiếp rồi gọi validator. Đây là **unit test của validator**, không chứng minh RSA/JWKS hoặc đường Bearer filter.

Ví dụ JUnit 5 dùng class `RequiredApiClaimsValidator` ở mục 7:

~~~java
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RequiredApiClaimsValidatorTest {

    private static final Instant NOW =
        Instant.parse("2030-01-01T00:00:00Z");

    private final RequiredApiClaimsValidator validator =
        new RequiredApiClaimsValidator("orders-api");

    private Jwt jwt(
            Object tenant, boolean includeTenant,
            Object roles, boolean includeRoles,
            Object scope, boolean includeScope) {

        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("iss", "https://login.example.test/realms/demo");
        claims.put("sub", "user-123");
        claims.put("aud", List.of("orders-api"));
        claims.put("iat", NOW);
        claims.put("exp", NOW.plusSeconds(600));

        if (includeTenant) {
            claims.put("tenant_id", tenant);
        }
        if (includeRoles) {
            claims.put("roles", roles);
        }
        if (includeScope) {
            claims.put("scope", scope);
        }

        return new Jwt(
            "synthetic-token",
            NOW,
            NOW.plusSeconds(600),
            Map.of("alg", "RS256"),
            claims);
    }

    @Test
    void validCustomClaimsPass() {
        Jwt token = jwt(
            "tenant-42", true,
            List.of("ORDER_READER"), true,
            "orders.read", true);
        assertFalse(validator.validate(token).hasErrors());
    }

    @Test
    void missingTenantIsRejected() {
        Jwt token = jwt(
            null, false,
            List.of("ORDER_READER"), true,
            "orders.read", true);
        assertTrue(validator.validate(token).hasErrors());
    }

    @Test
    void nullTenantIsRejected() {
        Jwt token = jwt(
            null, true,
            List.of("ORDER_READER"), true,
            "orders.read", true);
        assertTrue(validator.validate(token).hasErrors());
    }

    @Test
    void blankTenantAndWrongTypeAreRejected() {
        Jwt blank = jwt(
            "   ", true,
            List.of("ORDER_READER"), true,
            "orders.read", true);
        Jwt number = jwt(
            42, true,
            List.of("ORDER_READER"), true,
            "orders.read", true);

        assertTrue(validator.validate(blank).hasErrors());
        assertTrue(validator.validate(number).hasErrors());
    }

    @Test
    void invalidRolesAreRejected() {
        Jwt missing = jwt(
            "tenant-42", true,
            null, false,
            "orders.read", true);
        Jwt empty = jwt(
            "tenant-42", true,
            List.of(), true,
            "orders.read", true);
        Jwt wrongType = jwt(
            "tenant-42", true,
            "ORDER_READER", true,
            "orders.read", true);
        Jwt wrongElement = jwt(
            "tenant-42", true,
            List.of("ORDER_READER", 12), true,
            "orders.read", true);

        assertTrue(validator.validate(missing).hasErrors());
        assertTrue(validator.validate(empty).hasErrors());
        assertTrue(validator.validate(wrongType).hasErrors());
        assertTrue(validator.validate(wrongElement).hasErrors());
    }

    @Test
    void missingOrEmptyScopeIsRejected() {
        Jwt missing = jwt(
            "tenant-42", true,
            List.of("ORDER_READER"), true,
            null, false);
        Jwt empty = jwt(
            "tenant-42", true,
            List.of("ORDER_READER"), true,
            "", true);

        assertTrue(validator.validate(missing).hasErrors());
        assertTrue(validator.validate(empty).hasErrors());
    }
}
~~~

Các test trên dùng **`Jwt` tự tạo** với `iat`/`exp` đã được thể hiện bằng **Instant** giống đối tượng sau decode. Chúng chứng minh **logic của validator cho dữ liệu đã được chuẩn hóa**, không chứng minh cách Nimbus xử lý raw JSON, nguồn khóa hoặc chữ ký.

Nếu cần test **`exp` và `iat` thiếu**, có thể dựng một `Jwt` test không có thông tin tương ứng hoặc, đáng tin cậy hơn cho ranh giới decode, dùng JWT ký thật thiếu claim đó để xác nhận chính sách end-to-end. Khi làm vậy, cần kiểm soát rằng `Jwt` test có thể được tạo theo invariant của phiên bản Spring Security đang sử dụng.

## 12. Kiểm thử bằng JWT ký thật để bắt lỗi claim gốc

Những trường hợp như `exp: "2030-01-01T00:00:00Z"`, `aud: 7` hoặc array chứa phần tử sai type cần được kiểm thử **qua chính JWT decoder đang dùng trong production**, vì converter có thể chuẩn hóa dữ liệu trước khi chạy custom validator.

Một mô hình test ổn định:

~~~text
JUnit test
   |
   +-- tạo RSA key pair chỉ dùng trong test
   +-- tạo JWT claims theo từng case
   +-- ký JWT bằng private key test
   |
   v
NimbusJwtDecoder dùng public key test
   |
   +-- kiểm tra JWS signature
   +-- chuyển raw JSON claims -> Jwt
   +-- chạy default validators + custom validator
   |
   v
decode thành công / JwtException
~~~

Một phần mã minh họa ký JWT bằng Nimbus JOSE + JWT:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.security.KeyPair;
import java.security.interfaces.RSAPrivateKey;
import java.util.Date;
import java.time.Instant;
import java.util.List;

public final class JwtTestTokens {

    private JwtTestTokens() {}

    public static String signWithMissingTenant(
            KeyPair testKeyPair) throws Exception {

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer("https://login.example.test/realms/demo")
            .subject("user-123")
            .audience("orders-api")
            .issueTime(Date.from(Instant.now()))
            .expirationTime(Date.from(
                Instant.now().plusSeconds(600)))
            .claim("scope", "orders.read")
            .claim("roles", List.of("ORDER_READER"))
            // Không đặt tenant_id để kiểm tra required claim.
            .build();

        SignedJWT jwt = new SignedJWT(
            new JWSHeader(JWSAlgorithm.RS256),
            claims);

        jwt.sign(new RSASSASigner(
            (RSAPrivateKey) testKeyPair.getPrivate()));

        return jwt.serialize();
    }
}
~~~

Trong test tương ứng, tạo decoder bằng `NimbusJwtDecoder.withPublicKey((RSAPublicKey) testKeyPair.getPublic()).build()` rồi **gắn cùng bộ validators** như production, sau đó kỳ vọng `JwtException` khi gọi `decode` với JWT thiếu tenant. Nếu muốn kiểm tra cả đường HTTP, gửi chuỗi JWT đã ký trong header `Authorization: Bearer` qua MockMvc hoặc test server có decoder thật.

**Không cần** dùng private key hoặc Access Token production để kiểm thử. JWT fixture với RSA key test và các claims giả là đủ để tái hiện hầu hết trường hợp missing/null/wrong type một cách có kiểm soát.

### 12.1. Ma trận token cần thử

| Token / claim | Kỳ vọng nếu dùng contract ví dụ |
| --- | --- |
| Chữ ký đúng, issuer/audience đúng, mọi claim bắt buộc đúng | Decode thành công. |
| Chữ ký sai | Bị từ chối trước khi tin claims. |
| `iss` thiếu hoặc là issuer khác | Token bị từ chối. |
| `aud` thiếu, sai resource hoặc sai JSON type | Token bị từ chối. |
| `exp` thiếu dù profile bắt buộc | Token bị từ chối bởi required-claim policy. |
| `exp` đã qua | Token bị từ chối bởi timestamp validation. |
| `nbf` trong tương lai | Token bị từ chối, có xét clock skew được phép. |
| `exp` là chuỗi/số mili-giây sai schema | Cần bị từ chối theo quy tắc profile/kiểm tra type gốc. |
| `iat` thiếu dù profile bắt buộc | Token bị từ chối. |
| `tenant_id` thiếu | Token bị từ chối. |
| `tenant_id: null` | Token bị từ chối. |
| `tenant_id: ""` hoặc chỉ whitespace | Token bị từ chối. |
| `tenant_id: 42` | Token bị từ chối vì sai type. |
| `roles: []` | Token bị từ chối theo hợp đồng bắt buộc non-empty của ví dụ. |
| `roles: ["ORDER_READER", 1]` | Token bị từ chối vì phần tử sai type. |
| `scope: ""` hoặc `scope` thiếu | Token bị từ chối theo contract ví dụ. |
| Token hợp lệ nhưng không có **orders.write** khi POST | Authentication được chấp nhận; authorization thường trả **403**. |
| Token hợp lệ và scope đúng nhưng khác tenant tài nguyên | Resource authorization từ chối truy cập. |

### 12.2. Test MockMvc với jwt() không phải test decoder

Spring Security Test hỗ trợ:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Đây là công cụ phù hợp để kiểm thử **authorization** với principal đã được xác thực. Nhưng `jwt()` **bỏ qua bước xác minh chữ ký và validators của JwtDecoder**. Bởi vậy, một test dùng `jwt()` với claim sai nhưng vẫn nhận 200 **không chứng minh decoder đang chấp nhận JWT sai**. Muốn kiểm thử token bị từ chối do thiếu/sai claim, phải dùng decoder thật hoặc gửi JWT ký thật qua filter.

## 13. Những trường hợp ranh giới cần thiết kế riêng

### 13.1. Claim đã được chuẩn hóa có thể che mất lỗi kiểu JSON gốc

Nếu một claim tiêu chuẩn được converter biến thành kiểu Java hợp lệ, validator phía sau có thể không còn biết dữ liệu gốc là JSON string, number hay array. Nếu token profile yêu cầu **strict JSON types**, cần cơ chế kiểm tra tại quá trình parsing/conversion và integration tests với JWT payload có kiểu không hợp lệ.

Đây là lý do không nên dùng duy nhất **`Jwt` dựng thủ công** để đánh giá việc decoder sẽ từ chối tất cả kiểu dữ liệu sai. Hãy phân biệt **kiểm thử validator** và **kiểm thử raw JWT decoding**.

### 13.2. Claim duplicate trong JSON

JSON object có thể bị tạo với tên trùng:

~~~json
{
  "scope": "orders.read",
  "scope": "orders.admin"
}
~~~

RFC 7519 yêu cầu tên claim trong JWT Claims Set là duy nhất; parser phải xử lý theo quy định, chẳng hạn từ chối duplicate hoặc sử dụng quy tắc đã được chuẩn cho phép. Một parser có thể chỉ giữ giá trị cuối, nên sau khi decode thành map, ứng dụng **có thể không phát hiện được** rằng payload gốc có tên trùng.

Đối với dữ liệu cấp quyền nhạy cảm, không tự ghép hoặc cộng quyền từ hai giá trị trùng. Cần tin cơ chế parsing phù hợp tiêu chuẩn, kiểm thử behavior thực tế của thư viện và tránh nhận các JWT không đáp ứng profile.

### 13.3. Chuỗi có khoảng trắng hoặc ký tự Unicode

Một định danh tenant như `"tenant-42"` khác `" tenant-42 "`. Nếu contract yêu cầu định danh theo pattern cố định, nên **kiểm tra pattern tường minh** thay vì tự `trim()` mọi giá trị và coi chúng tương đương. Với claims là tên/định danh từ nhiều hệ thống, việc chuẩn hóa Unicode có thể có ý nghĩa riêng và không nên làm âm thầm ở bước phân quyền.

### 13.4. Object lồng nhau và arrays lớn

Nếu issuer phát hành claims như:

~~~json
{
  "permissions": {
    "orders": ["read", "write"],
    "billing": ["read"]
  }
}
~~~

Resource Server phải biết `permissions` là object, mỗi key được phép là gì, mỗi value có phải array of strings không, có giới hạn kích thước và quyền hợp lệ không. Không cast vô điều kiện sang `Map<String, List<String>>` rồi tin dữ liệu.

Token bất thường có thể chứa claims quá lớn hoặc quá sâu, gây tăng CPU/bộ nhớ/HTTP header size. Bên cạnh schema validation, cần có giới hạn request/header và khả năng parser phù hợp; tránh đưa dữ liệu không cần thiết vào Access Token.

### 13.5. Nhiều issuer có contract khác nhau

Nếu Resource Server chấp nhận nhiều issuer, claim `roles` có thể có những nghĩa khác nhau. Một issuer dùng:

~~~json
{"roles": ["ORDER_READER"]}
~~~

Issuer khác có thể dùng:

~~~json
{"role": "ORDER_READER"}
~~~

Không nên xây fallback “đọc `roles`, nếu thiếu thì đọc `role`, nếu thiếu nữa cho phép mặc định” trên mọi issuer. Nếu thật sự hỗ trợ nhiều profile, hãy **chọn contract theo issuer/token profile đã được xác minh** và áp quyền tương ứng. Không để token của issuer chưa được cấp phép chỉ vì có một claim mang tên quen thuộc.

## 14. Khi nào từ chối token, khi nào chỉ từ chối một quyền?

Một câu hỏi thiết kế hữu ích là: **claim này thuộc điều kiện nhận token hay thuộc điều kiện thực hiện hành động?**

| Claim / điều kiện | Nếu vắng mặt hoặc không phù hợp | Gợi ý tầng xử lý |
| --- | --- | --- |
| Chữ ký, issuer, audience, thời hạn theo profile | Không thể tin credential. | **Decoder / validation → 401** |
| `tenant_id` bắt buộc cho mọi token API | Token không đáp ứng contract. | **Custom token validator → 401** |
| `roles` bắt buộc và kiểu sai | Token không đáp ứng contract. | **Custom token validator → 401** |
| `roles` tùy chọn theo profile, thiếu nghĩa là không có role | Token có thể hợp lệ nhưng không có quyền theo role. | **Authorization → 403** khi endpoint yêu cầu |
| `scope` rỗng được profile xem là không có scope | Token có thể được xác thực nhưng thiếu quyền. | **Authorization → 403** khi endpoint cần scope |
| `scope` bắt buộc không rỗng theo profile ví dụ | Token vi phạm schema bắt buộc. | **Custom token validator → 401** |
| `tenant_id` đúng kiểu nhưng không khớp tenant của đơn hàng | Credential có thể hợp lệ nhưng yêu cầu tài nguyên trái quyền. | **Resource authorization → 403/404 theo policy** |

Không có một câu trả lời chung cho mọi custom claim, vì chính sách phụ thuộc token contract. Tuy nhiên, một khi đã chọn contract, **mọi instance Resource Server phải xử lý thống nhất** để không tạo điểm yếu giữa các endpoint hoặc môi trường.

## 15. Những lỗi thường gặp khi viết claim validation

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Chỉ kiểm tra chữ ký, không kiểm tra audience. | Token của API khác có thể được dùng sai mục đích. | Audience validator đúng API. |
| Chỉ kiểm tra `exp` nếu có dù profile bắt buộc exp. | Token không có thời hạn có thể lọt qua chính sách. | Kiểm tra presence và timestamp. |
| Coi `null`, missing, empty string là tương đương với quyền mặc định. | Dễ cấp quyền vượt mong muốn. | Fail-closed hoặc ánh xạ về không quyền theo contract. |
| Dùng `String.valueOf` để chuyển mọi kiểu về string. | Wrong-type claims có thể được chấp nhận ngoài dự kiến. | Kiểm tra schema rõ ràng. |
| Cast `List<String>` mà không kiểm tra từng phần tử. | Lỗi runtime hoặc quyền sai khi phần tử là number/object. | Kiểm tra `List<?>` và từng item. |
| Tạo JwtDecoder custom nhưng quên default validators. | Mất issuer/timestamp validation. | Kết hợp `JwtValidators.createDefaultWithIssuer` và custom validator. |
| Dùng `@RestControllerAdvice` để bắt mọi JWT error. | Lỗi ở security filter có thể xảy ra trước controller. | Cấu hình xử lý lỗi phù hợp trong security chain. |
| Chỉ test `jwt()` rồi khẳng định decoder từ chối token sai. | Test không đi qua JWT verification. | Test decoder với JWT ký thật. |
| Dùng ID Token thay Access Token. | Nhầm loại token và audience. | Kiểm tra profile, issuer và audience API. |
| Log nguyên JWT/claims khi validation thất bại. | Rò rỉ Bearer credential và dữ liệu nhạy cảm. | Log mã lỗi/ID yêu cầu, không phản chiếu token. |

## 16. Quy trình triển khai schema validation vào Resource Server

1. **Thống nhất token contract** với Authorization Server: JWT Access Token profile, issuer, audience, scope và những claims bắt buộc.
2. **Định nghĩa schema cho từng claim**: tên, JSON type, required/optional, cách hiểu null, empty, whitespace, miền giá trị, phiên bản và nguồn cấp.
3. **Cấu hình JwtDecoder tin cậy**: chữ ký/JWK Set, thuật toán, issuer, timestamp, audience.
4. **Thêm validators theo contract**: presence, type và những ràng buộc giá trị bắt buộc; không vô tình bỏ validator mặc định.
5. **Ánh xạ authorities có chủ đích**: scope, roles, permissions từ claims đúng schema; không cấp quyền từ input client tự khai.
6. **Kiểm tra authorization theo tài nguyên**: tenant ID, chủ sở hữu bản ghi và hành động cụ thể sau khi token được xác thực.
7. **Kiểm thử thiếu/null/empty/wrong-type** với unit tests của validator và JWT ký thật đi qua decoder. Thử cả positive và negative cases.
8. **Bảo vệ xử lý lỗi và vận hành**: trả 401/403 có ý nghĩa, không log Bearer Token, không làm lộ claims nhạy cảm, theo dõi những lỗi schema bất thường.

**Ghi nhớ:** Với Spring Security Resource Server, điều kiện “JWT có chữ ký đúng” chỉ mở đầu quá trình xác thực. Một API an toàn cần **hợp đồng claims rõ ràng**, phân biệt **thiếu / null / rỗng / sai kiểu**, kiểm tra **issuer, audience, thời hạn và claims bắt buộc**, sau đó thực hiện **authorization theo quyền và tài nguyên**. Nếu không có đủ thông tin đáng tin cậy để cấp quyền, hệ thống phải từ chối theo chính sách thay vì tự diễn giải theo hướng rộng quyền hơn.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 4: JWT Claims](https://www.rfc-editor.org/rfc/rfc7519#section-4).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — JwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html).
- [Spring Security — OAuth2TokenValidator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2TokenValidator.html).
- [Spring Security — Jwt API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
