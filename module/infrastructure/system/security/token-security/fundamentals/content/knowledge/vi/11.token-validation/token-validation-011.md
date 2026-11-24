# Không chỉ decode token rồi tin nội dung

Một API nhận access token trong header Authorization. Lập trình viên tách chuỗi JWT theo dấu chấm, giải mã phần payload bằng Base64url, thấy **sub=user-42** và **role=ADMIN**, rồi cho phép yêu cầu. Cách triển khai này mắc lỗi nghiêm trọng: **đọc được nội dung không đồng nghĩa nội dung đó đã được xác minh**. Kẻ tấn công có thể tự tạo một chuỗi trông giống JWT và điền những claims mà họ muốn.

**Decode** là chuyển dữ liệu từ một biểu diễn sang dữ liệu có thể đọc. **Validate/verify** là kiểm chứng nguồn, tính toàn vẹn, thời hạn, mục đích sử dụng và chính sách trước khi ra quyết định. Với token bảo mật, nhầm lẫn hai thao tác này có thể biến một chuỗi do người dùng tự khai thành bằng chứng xác thực và phân quyền.

Bài học thuộc chương **Token validation** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là mô hình tin cậy và vòng đời JWT, opaque access token, refresh token trong OAuth 2.0/OIDC: phát hành, xác minh claims, scope, audience, lưu trữ, thu hồi, và hạn chế token bị đánh cắp hoặc phát lại.

Sau bài học, bạn sẽ:

- Giải thích vì sao **Base64url decode không xác minh chữ ký**.
- Biết từng bước xác minh **JWT access token** trước khi dùng bất kỳ claim nào cho bảo mật.
- Phân biệt **signature validation**, **claims validation**, **token type validation**, **policy evaluation** và **revocation**.
- Hiểu vì sao **opaque token** phải được kiểm tra bằng nguồn tin cậy thay vì tự giải mã.
- Phát hiện các lỗi như tin **alg**, **kid**, **jku** do token khai báo, nhận sai **issuer/audience**, hoặc dùng **ID token** để gọi API.
- Thiết kế negative tests và cách xử lý lỗi **fail closed**.

## 1. Decode, parse, verify và authorize là các thao tác khác nhau

Một pipeline xử lý access token nên chia thành những bước có trách nhiệm rõ:

| Bước | Làm gì? | Có đủ để tin token chưa? |
|---|---|---|
| **Extract** | Lấy Bearer token từ request theo giao thức | Chưa. Request là dữ liệu đầu vào chưa đáng tin. |
| **Parse/Decode** | Tách cấu trúc, đọc header/payload hoặc metadata | Chưa. Giá trị vừa đọc có thể do kẻ tấn công đặt. |
| **Cryptographic verification** | Kiểm tra chữ ký/MAC đối với key được tin và thuật toán được cho phép | Chưa đủ. Có thể đúng chữ ký nhưng sai issuer, audience hoặc đã hết hạn. |
| **Token validation** | Kiểm tra issuer, audience, thời gian, profile, loại token, trạng thái thu hồi khi áp dụng | Có thể xác lập một **principal/credential hợp lệ cho API**, chưa tự cho phép mọi thao tác. |
| **Authorization policy evaluation** | Kiểm tra scope, vai trò, quan hệ với tài nguyên, tenant và quyền hiện hành | Chỉ Permit hành động cụ thể khi mọi điều kiện đạt. |

**Decode** là thao tác biểu diễn; **verify** là xác minh chứng cứ; **authorize** là ra quyết định quyền. Không bước nào được dùng để thay bước tiếp theo.

Giả sử có hai token:

- Token A chứa **sub=user-42**, **scope=orders:read**, chữ ký hợp lệ từ issuer tin cậy, audience đúng và còn hạn.
- Token B cũng chứa các chuỗi đó nhưng do kẻ tấn công tự tạo, chữ ký sai hoặc không có chữ ký phù hợp.

Sau Base64url decoding, payload của hai token **có thể giống hệt nhau**. Chỉ quá trình xác minh tin cậy mới phân biệt chúng. Nếu API chỉ nhìn các claims đã decode, API sẽ cho Token B quyền giống Token A.

## 2. Điều gì thực sự nằm trong một JWT?

Với **JWT dưới dạng JWS compact serialization** thường gặp, chuỗi có ba phần:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ phần header và payload **trước khi mã hóa Base64url**:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-01"
}
~~~

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1899999000,
  "exp": 1900000800,
  "jti": "sample-jti-701"
}
~~~

Đây là **dữ liệu giả minh họa**, không phải token đã được ký. **Bất kỳ người nào có JWT kiểu JWS không mã hóa đều có thể giải mã Base64url để đọc header và payload**, không cần biết private key. Đó là lý do không được nhúng mật khẩu, refresh token, API secret hoặc dữ liệu cá nhân không cần thiết vào JWT dễ đọc.

**Chữ ký JWS** bảo vệ tính toàn vẹn và cho phép xác minh nguồn ký với **khóa được tin**. Nó không che giấu nội dung payload. Nếu ai đó thay **role=USER** thành **role=ADMIN**, chữ ký cũ sẽ không còn hợp lệ **nếu verifier thực sự kiểm tra chữ ký**.

Một vài định dạng cần phân biệt:

| Dạng | Đặc điểm | Cách xác minh |
|---|---|---|
| **JWS/JWT ký** | Payload thường đọc được; có chữ ký/MAC | Xác minh thuật toán, key, chữ ký, sau đó kiểm claims/profile |
| **JWE** | Payload được mã hóa cho bên có khóa giải mã; compact JWE thường có năm phần | Giải mã và kiểm chứng mật mã theo profile, sau đó kiểm claims/loại token |
| **Opaque access token** | Bên nhận không có hợp đồng tự diễn giải chuỗi token | Introspection hoặc kho trạng thái tin cậy; vẫn kiểm audience/scope/policy |
| **Refresh token** | Credential xin access token mới tại Authorization Server | AS kiểm tra theo flow, client binding và trạng thái; không gửi đến API nghiệp vụ |

**Không phải chuỗi có ba phần ngăn bằng dấu chấm nào cũng là JWT access token hợp lệ**. Và **JWT hợp lệ về cấu trúc chưa chắc hợp lệ cho Resource Server** đang nhận nó.

## 3. Ví dụ lỗ hổng: chỉ giải mã và dùng claims

Đoạn Java dưới đây là **anti-pattern cố ý** để cho thấy lỗi thiết kế, tuyệt đối không dùng để xác thực:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class UnsafeJwtExample {
    public static String decodePayloadOnly(String compactJws) {
        String[] parts = compactJws.split("\\.", -1);
        if (parts.length != 3) {
            throw new IllegalArgumentException("Invalid compact JWS shape");
        }
        byte[] payloadBytes = Base64.getUrlDecoder().decode(parts[1]);
        return new String(payloadBytes, StandardCharsets.UTF_8);
    }
}
~~~

Hàm có tên **decodePayloadOnly** chỉ chuyển dữ liệu thành chuỗi JSON. Nó không kiểm:

1. Chữ ký có hợp lệ không, token có dùng thuật toán bị cấm không.
2. Public key có thực sự thuộc issuer mà API tin cậy không.
3. **iss** là issuer nào, **aud** có chứa API đang nhận hay không.
4. **exp** đã qua, **nbf** còn ở tương lai hay chưa.
5. Token đó là **access token**, **ID token**, hay một cấu trúc khác.
6. Subject/client có quyền với tài nguyên cụ thể hay không.

Ví dụ về quyết định **sai** tiếp theo:

~~~text
claims = JSON.parse(decodePayloadOnly(request.bearerToken))
if claims.role == "ADMIN":
    allowDeleteOrder()
~~~

Kẻ tấn công có thể tự tạo payload chứa **role=ADMIN**, đặt vào cấu trúc giống JWT và đưa cho API. Nếu code không xác minh nguồn và chữ ký, **giá trị role hoàn toàn là dữ liệu tự khai**.

**Không “chữa” bằng cách chỉ kiểm exp sau decode.** Kẻ tấn công cũng có thể tự đặt exp trong tương lai. **Không “chữa” bằng cách chỉ kiểm iss sau decode**: chuỗi issuer cũng do họ tự viết được. Phải kiểm **chữ ký với key được tin và toàn bộ profile/claims** trước khi đưa dữ liệu vào quyết định bảo mật.

## 4. Bắt đầu từ trust configuration, không từ claims chưa xác minh

Một verifier đúng không hỏi token: “Tôi nên tin issuer nào và tải key từ đâu?”. Verifier phải biết những điều đó từ **cấu hình được quản lý bởi phía server** hoặc quy trình chọn issuer đã được xác thực.

Trong một API Orders, hợp đồng có thể gồm:

| Thuộc tính | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| **Trusted issuer** | https://auth.example.org/realms/shop | Nguồn phát hành được phép |
| **Expected audience** | orders-api | Chỉ nhận token dành cho Orders API |
| **Accepted token profile** | OAuth 2.0 JWT access token | Không dùng ID token thay access token |
| **Allowed algorithms** | Tập thuật toán đã cấu hình theo khả năng và policy | Không tự nhận mọi alg do token công bố |
| **Trusted keys/JWKS** | Nguồn key được xác thực, gắn với issuer này | Không lấy key tùy ý từ JWT |
| **Endpoint scope** | orders:read, orders:write tùy route | Giới hạn quyền đã cấp |
| **Resource policy** | Membership/owner/tenant/role hiện hành | Chặn truy cập sai tài nguyên |

Khi API nhận một token tuyên bố **iss=https://attacker.example**, nó không được tự tải metadata hoặc JWKS của địa chỉ đó rồi coi là một issuer mới được phép. Nếu một hệ thống phải chấp nhận nhiều issuer, **allowlist issuer** cùng khóa và policy được quản lý từ trước; iss chưa xác minh chỉ có thể được dùng như **gợi ý chọn trong danh sách đã tin**, rồi phải được kiểm tra lại sau xác minh mật mã.

### Issuer và key phải được ràng buộc

Một public key trả lời “chữ ký có khớp khóa này không?”, còn **issuer** trả lời “nguồn nào được phép tạo bằng chứng cho API?”. Dùng key từ issuer khác có thể khiến verifier nhận sai nguồn token. Hai nhà phát hành có thể sử dụng cùng **kid**; kid chỉ là nhãn chọn key **trong tập key gắn với issuer**, không phải chứng cứ tin cậy toàn cục.

Với thuật toán đối xứng như HS256, bí mật dùng để xác minh cũng dùng để tạo MAC, nên việc chia sẻ bí mật cho nhiều Resource Server tăng phạm vi ảnh hưởng khi một bên bị lộ. Với chữ ký bất đối xứng, API thường chỉ giữ public key, trong khi private signing key được bảo vệ ở Authorization Server.

## 5. Header JOSE cũng là dữ liệu chưa đáng tin

Một JSON Web Signature có thể chứa các trường **alg**, **kid**, **typ**, đôi khi **jku**, **x5u** hoặc tham số khác. **Header có mặt trước bước verify không có nghĩa được tin**.

| Trường | Ý nghĩa | Quy tắc an toàn |
|---|---|---|
| **alg** | Thuật toán dự kiến | Chỉ chấp nhận thuật toán đã được server cho phép và phù hợp với key; không tự chấp nhận none hoặc chuyển loại key ngoài policy |
| **kid** | Key identifier | Chỉ chọn trong tập key của issuer đã tin cậy; kiểm tra key chưa bị thu hồi |
| **typ** | Loại đối tượng JWT/JWS theo profile | Kiểm tra để phân biệt access token với ID token khi profile quy định; không coi typ tự nó là bằng chứng hợp lệ |
| **jku** | URL đến JWK Set theo JOSE | Không tải và tin URL do token chưa xác minh đề xuất; chống SSRF/key substitution |
| **x5u** | URL đến chứng thư theo JOSE | Không biến nguồn chứng thư tùy ý do token chỉ định thành trust anchor |
| **crit** | Danh sách header parameters cần hiểu | Verifier phải xử lý đúng các tham số quan trọng hoặc từ chối; không bỏ qua một cách mù quáng |

### Lỗi algorithm confusion

Một số triển khai kém an toàn để header **alg** quyết định tự do thuật toán kiểm chữ ký. Điều này có thể dẫn đến chấp nhận **none** hoặc nhầm khóa bất đối xứng/đối xứng. Thay vì “cứ dùng thuật toán mà token yêu cầu”, server phải **cố định tập thuật toán được phép**, kiểm loại key phù hợp và dùng thư viện JOSE/JWT được duy trì.

Không nên tự triển khai các thuật toán mật mã bằng cách so chuỗi, dùng hàm băm thông thường thay chữ ký, hoặc bỏ qua ngoại lệ verify để tiếp tục xử lý. **Verification failure phải là Deny**, không phải lý do fallback sang decode-only.

### Lỗi nguồn khóa tự chọn

Anti-pattern:

~~~text
header = decodeJwtHeader(token)
keySet = httpGet(header.jku)          # URL chưa đáng tin
key = keySet.find(header.kid)
if signatureMatches(token, key):
    accept()
~~~

Nếu verifier tin bất kỳ key set nào do token chỉ ra, kẻ tấn công có thể dùng public key của chính họ để làm verifier chấp nhận token do họ ký. **Nguồn JWKS phải được gắn với issuer allowlist**, lấy theo cấu hình/metadata đã xác thực và bị ràng buộc bởi policy. Header chưa verify không được mở rộng danh sách nơi lấy khóa tin cậy.

## 6. Sau khi kiểm chữ ký vẫn phải kiểm claims và ngữ cảnh

Chữ ký hợp lệ không đồng nghĩa token được sử dụng ở đúng nơi, đúng thời điểm hay có đủ quyền.

| Claim/điều kiện | Cách kiểm tra | Nếu bỏ qua sẽ xảy ra gì? |
|---|---|---|
| **iss** | Khớp issuer đã cấu hình cho API/tenant | Token của issuer khác có thể được nhận nhầm |
| **aud** | Có đúng audience của Resource Server, theo kiểu string hoặc mảng string được phép | Token cho API khác có thể được tái sử dụng |
| **exp** | Chưa hết hạn theo NumericDate, với clock skew nhỏ theo policy | Token cũ vẫn được chấp nhận |
| **nbf** | Nếu có, chưa dùng token trước thời điểm hiệu lực | Token tương lai bị sử dụng sớm |
| **iat** | Nếu có/theo profile, đúng kiểu và hợp lý; có thể kiểm tuổi tối đa | Không phát hiện token có mốc thời gian bất thường |
| **sub** | Subject đúng kiểu, ngữ nghĩa theo issuer và flow | Gộp sai danh tính người dùng/dịch vụ |
| **client_id** | Theo profile và policy, xác định OAuth client được cấp token | Nhầm quyền client với quyền subject |
| **scope** | So khớp đúng tên scope yêu cầu của action | Token có scope khác vẫn được cho thao tác |
| **Loại token/profile** | Chấp nhận đúng access token cho API | ID token hoặc token sai ngữ cảnh bị dùng thay |
| **Revocation/trust state** | Token/key/issuer chưa bị vô hiệu hóa theo cơ chế triển khai | Tiếp tục tin một bằng chứng đã bị thu hồi |

Các giá trị thời gian JWT **exp**, **nbf**, **iat** dùng **NumericDate** (giây Unix epoch, không mặc định là mili giây). Một thư viện hoặc profile có thể chấp nhận một sai lệch đồng hồ nhỏ, nhưng không được mở rộng clock skew vô hạn để che cấu hình thời gian sai.

**Optional không có nghĩa là bỏ qua khi hiện diện.** Ví dụ JWT nền tảng (RFC 7519) định nghĩa nhiều registered claims mà không bắt tất cả JWT luôn chứa chúng. Nhưng **JWT access token theo RFC 9068** có các claims bắt buộc riêng: **iss, sub, aud, exp, iat, jti, client_id**. Nếu ứng dụng dùng profile này, phải tuân thủ cả profile, không chỉ RFC JWT nền tảng. Scope được kiểm theo chính sách cấp quyền và endpoint, không tự biến thành quyền mặc định khi thiếu.

### Đối chiếu audience phải chính xác

Audience **orders-api** không tự tương đương **orders-api-staging**, **my-orders-api** hay **ORDERS-API**. Dùng so khớp giá trị audience đúng kiểu và phân biệt hoa/thường theo profile, không dùng substring, suffix hoặc wildcard tùy tiện. Nếu hệ thống chỉ cho phép một audience, phải từ chối token nhiều audience theo policy; nếu cho phép nhiều, mọi API vẫn độc lập kiểm scope và quyền.

### Issuer không phải là URL trong token để truy cập tùy ý

Giá trị **iss** được xử lý như **danh tính**, đối chiếu theo quy tắc profile. Không tự bỏ dấu gạch chéo cuối, đổi path/realm hoặc dùng host của request để ép khớp issuer. Trong nhiều issuer/tenant, cặp **(iss, sub)** giúp phân biệt hai chủ thể có cùng sub thuộc các nguồn khác nhau.

## 7. Kiểm tra đúng loại token: access, ID và refresh không thể hoán đổi

Trong OAuth 2.0/OIDC, hai token cùng là JWT có thể có **mục đích và audience khác nhau**:

| Token | Bên nhận dự kiến | Điều phải kiểm tra |
|---|---|---|
| **OAuth access token** | Resource Server/API | Token dành cho API, đúng issuer, audience, thời hạn, scope, profile và quyền tài nguyên |
| **OIDC ID token** | Client/Relying Party | Bằng chứng xác thực danh tính; issuer và audience là client ID, cùng các điều kiện OIDC |
| **Refresh token** | Authorization Server/token endpoint | Client binding, hiệu lực, trạng thái thu hồi, rotation/replay; không gửi đến API nghiệp vụ |

Một ID token có **iss** và **sub** đúng, thậm chí chữ ký hợp lệ, **không phải access token**. Nếu API chấp nhận ID token chỉ vì cùng issuer, có thể xảy ra **token substitution**. Khi JWT access token tuân RFC 9068, header **typ** theo profile thường phân biệt access token (ví dụ **at+jwt**). Tuy nhiên API phải kiểm **cả profile và audience**, không chỉ nhìn typ.

Ví dụ payload ID token dành cho client:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "shop-web",
  "iat": 1899999000,
  "exp": 1900000800
}
~~~

Nếu Orders API kỳ vọng **aud=orders-api**, token trên **không đúng người nhận** dù ID token được client xác minh hợp lệ. Resource Server cần access token được cấp cho API của mình.

Ngược lại, client khi xác minh OIDC ID token cần áp dụng quy tắc OIDC của chính flow, gồm **nonce**, **auth_time**, **azp** và các điều kiện khác khi áp dụng. Không dùng một bộ validator access token đơn giản cho mọi ID token.

## 8. Với opaque token, decode cũng không phải cách xác minh

**Opaque access token** có thể là chuỗi ngẫu nhiên khó đoán. Resource Server không có hợp đồng để suy ra chủ thể, scope hay thời hạn từ cách nhìn chuỗi token. Thay vào đó, nó thường truy vấn **OAuth 2.0 Token Introspection (RFC 7662)** hoặc một nguồn trạng thái đáng tin.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Orders API
    participant AS as Authorization Server
    C->>RS: Bearer opaque access token
    RS->>AS: Introspection qua TLS + xác thực RS
    AS-->>RS: active, aud, scope, sub, exp...
    alt active=false hoặc điều kiện không đạt
        RS-->>C: Reject
    else active=true và đúng API
        RS->>RS: Kiểm scope và quyền trên đơn hàng
        RS-->>C: Permit hoặc deny theo policy
    end
~~~

Một phản hồi minh họa:

~~~json
{
  "active": true,
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1900000800
}
~~~

Trong RFC 7662, **active** là trường cốt lõi của phản hồi introspection. Những trường metadata khác có thể không được cung cấp trong mọi triển khai. Resource Server phải có **hợp đồng tin cậy** đủ để biết token dành cho API và loại token nào; không coi thiếu aud là cho phép mọi audience.

**HTTP 200 của introspection không có nghĩa token hợp lệ**. Response sau cũng thường là kết quả HTTP 200:

~~~json
{
  "active": false
}
~~~

Nếu **active=false**, API phải từ chối. Nếu endpoint không truy cập được, phản hồi sai định dạng hoặc không xác thực được nguồn introspection, API phải **fail closed** hoặc trả lỗi hệ thống phù hợp; **không mặc định active=true** chỉ vì không kiểm tra được.

Cache kết quả introspection giúp giảm tải nhưng tạo độ trễ thu hồi. Một token đã bị vô hiệu hóa ở Authorization Server có thể vẫn được nhận tại Resource Server cho đến khi cache hết hạn hoặc bị invalidated. Độ trễ này phải được thiết kế theo mức rủi ro, không được suy rằng opaque token luôn thu hồi tức thì.

## 9. Mô hình validate đầy đủ ở Resource Server

~~~mermaid
flowchart TD
    A["Nhận Bearer token"] --> B{"Token đúng định dạng/profile?"}
    B -->|Không| X["Reject"]
    B -->|Có| C{"JWT hay opaque theo cấu hình?"}
    C -->|JWT| D["Verifier tin cậy: issuer, key, alg, chữ ký"]
    C -->|Opaque| E["Introspection tin cậy: active, metadata"]
    D --> F{"Tính hợp lệ nguồn và bằng chứng đạt?"}
    E --> F
    F -->|Không| X
    F -->|Có| G{"aud, thời hạn, loại token, thu hồi đạt?"}
    G -->|Không| X
    G -->|Có| H{"scope và policy tài nguyên đạt?"}
    H -->|Không| Y["Deny authorization"]
    H -->|Có| I["Permit hành động cụ thể"]
~~~

Quy trình mẫu cho Orders API ở dạng pseudocode:

~~~text
authorizeOrderRead(request):
    token = requireBearerToken(request)
    if token missing:
        return 401

    # Những ràng buộc sau lấy từ cấu hình server, không từ token.
    expectedIssuer = "https://auth.example.org"
    expectedAudience = "orders-api"

    validation = trustedAccessTokenValidator.validate(
        token,
        issuer = expectedIssuer,
        audience = expectedAudience,
        allowedAlgorithms = configuredAllowlist,
        expectedProfile = configuredAccessTokenProfile
    )
    if validation invalid:
        return 401

    principal = validation.verifiedPrincipal
    if not principal.hasExactScope("orders:read"):
        return 403

    order = repository.findWithinTenant(
        request.orderId, validatedTenantContext(request)
    )
    if order missing:
        return 404
    if not currentPolicy.canRead(principal, order):
        return 403

    return 200 with allowedOrderFields(order)
~~~

**Pseudocode không phải thư viện bảo mật dùng trực tiếp.** Một thư viện OAuth/JWT được duy trì phải đảm nhiệm parse có giới hạn kích thước, xác minh mật mã, trust configuration và claims/profile. Cần cấu hình **expected issuer/audience** độc lập với claims do client cung cấp. Khi token sai định dạng, thiếu khóa, verifier lỗi hoặc dữ liệu quan trọng không xác minh được, phải **từ chối** thay vì chuyển sang nhánh decode-only.

### Nơi đặt kiểm tra

- **API Gateway** có thể xác minh chữ ký/issuer/audience và chặn yêu cầu sớm.
- **Resource Server** hoặc thành phần enforcement đáng tin phải đảm bảo kiểm soát tại **điểm truy cập dữ liệu**, kể cả các request nội bộ không đi qua gateway.
- **Policy Decision Point** có thể tập trung hoặc nội bộ, nhưng quyết định cần gắn với subject, action, tenant, resource và quyền hiện hành.
- Không chỉ bảo vệ **HTTP controller** rồi bỏ quên background job, message consumer hoặc đường gọi service-to-service.

Một token đã qua cryptographic verification vẫn có thể bị **Deny authorization** vì không có membership tenant, role đã bị thu hồi hoặc đơn hàng thuộc người khác.

## 10. Khác biệt giữa xác minh claims và phân quyền tài nguyên

Giả sử một access token hợp lệ có:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1900000800
}
~~~

Với token thật, Resource Server phải xác minh chữ ký và profile trước khi tin JSON như trên. Sau đó vẫn còn hai câu hỏi:

1. Token có **scope orders:read**, nhưng user-42 có được xem **order-900** của tenant **T17** không?
2. Membership hoặc role của user-42 có thể bị gỡ **sau khi token được phát hành** không?

Scope thường giới hạn phạm vi quyền được cấp cho token; nó **không chứng minh quyền trên mọi bản ghi**. API phải kiểm tenant, ownership, relationship, role, trạng thái nghiệp vụ và các điều kiện bổ sung của chính sách.

Đây cũng là lý do không nên đưa toàn bộ thông tin quyền vào JWT rồi coi nó luôn cập nhật. Các claims trong JWT được phát hành tại một thời điểm; **chữ ký hợp lệ không có nghĩa quyền vẫn mới**. Với thao tác nhạy cảm, cần tra cứu quyền hiện hành, kiểm version/epoch, trạng thái thu hồi hoặc chấp nhận rõ thời gian trễ của access token ngắn hạn.

### Ví dụ quyết định đúng

| Token đã xác minh | Quyền hiện hành | Hành động | Quyết định |
|---|---|---|---|
| Đúng issuer/audience, scope orders:read | User là thành viên T17 và được đọc order-900 | GET order-900 | Permit |
| Đúng issuer/audience, scope orders:read | User không thuộc tenant T17 | GET order-900 | Deny |
| Đúng issuer/audience, thiếu orders:write | User vẫn là chủ đơn hàng | UPDATE order-900 | Deny |
| Đúng issuer, nhưng aud=reports-api | User có role trong T17 | GET order-900 | Reject token trước phân quyền |
| Token có role ADMIN trong JSON chưa xác minh | Chưa xác minh nguồn | DELETE order-900 | Reject token |

**Không bao giờ cho phép dựa trên role/scope lấy từ payload chưa xác minh**, kể cả API có dùng HTTPS. HTTPS bảo vệ đường truyền; nó không chứng minh nội dung token được issuer đáng tin ký.

## 11. Ký đúng vẫn có thể không đáng tin khi key hoặc issuer bị xâm phạm

Cryptographic verification dựa trên một giả định quan trọng: **signing key và nguồn phát hành còn đáng tin**.

- **Chỉ một bearer token bị đánh cắp:** kẻ tấn công có thể phát lại chính token đó khi còn hiệu lực; họ không nhờ vậy mà có khả năng tự ký token mới.
- **Private signing key bị lộ:** kẻ tấn công có thể tạo nhiều JWT với chữ ký hợp lệ, tự đặt sub, scope và exp. Kiểm chữ ký với public key cũ có thể vẫn “pass” mặc dù token là giả.
- **Issuer hoặc JWKS bị kiểm soát:** cả quy trình phát hành key, metadata và claims có thể sai. Xoay key mà không khôi phục nền tảng tin cậy chưa đủ.

Khi một key bị xâm phạm, Resource Server cần **ngừng tin key đó trên mọi instance**, kể cả khi public key vẫn nằm trong cache JWKS. Khi toàn bộ issuer bị xâm phạm hoặc không thể khoanh vùng, có thể cần **tạm vô hiệu hóa issuer** cho đến khi khôi phục và kiểm chứng độc lập.

**Xóa key khỏi JWKS không lập tức xóa key khỏi cache của mọi verifier.** Cần chính sách chặn key/issuer có khả năng phân phối khẩn cấp và kiểm thử âm. Tương tự, **thu hồi refresh token không tự làm JWT access token cũ hết hiệu lực** nếu API không kiểm trạng thái thu hồi và chỉ dựa vào chữ ký/exp.

Trong thiết kế JWT self-contained, token ngắn hạn giảm cửa sổ rủi ro khi **một token** bị đánh cắp, nhưng không chặn **kẻ giữ private signing key** tiếp tục tự ký token mới chừng nào key ấy còn được tin.

## 12. Bảo vệ chính credential sau khi validate

Ngay cả khi token đã được cấp và xác minh đúng, vẫn có rủi ro **bearer token theft và replay**. Người giữ chuỗi token có thể gọi đúng API trong phạm vi token nếu không có cơ chế ràng buộc thêm.

Những biện pháp bổ trợ:

1. **HTTPS/TLS** cho cấp token, gọi Resource Server, introspection và revoke. Không gửi token trong query string hoặc qua kênh không bảo mật.
2. **Thời hạn access token phù hợp**, audience/scope tối thiểu và thu hồi khi phát hiện lộ.
3. **Bảo vệ nơi lưu**: tránh để token dài hạn lộ qua JavaScript không tin cậy, localStorage khi có rủi ro XSS; cân nhắc BFF và cookie HttpOnly/Secure/SameSite với CSRF protection khi phù hợp.
4. **Không ghi nguyên credential vào log, tracing, APM, crash report, ticket hỗ trợ hoặc công cụ decode công khai**.
5. **Refresh token rotation, phát hiện reuse hoặc sender-constraining** theo loại client và chính sách OAuth.
6. **DPoP hoặc mTLS sender-constrained access token** khi AS/RS/client hỗ trợ; Resource Server phải xác minh bằng chứng sở hữu đúng giao thức, không chỉ kiểm một claim tự khai.
7. **Giám sát bất thường**: tốc độ gọi API, phạm vi truy cập khác thường, revocation và sự kiện sử dụng lại token.

Opaque token không tự chống replay; JWE không tự chống replay; JWS có chữ ký hợp lệ cũng không tự chống replay. **Validation xác định credential có được chấp nhận**, còn chống phát lại đòi kiểm soát quyền sở hữu/phiên hoặc cơ chế đặc biệt.

## 13. HTTP response, xử lý ngoại lệ và logging an toàn

Một Resource Server nên có hành vi nhất quán:

| Trường hợp | Phản hồi thường gặp | Lý do |
|---|---|---|
| Thiếu access token | **401 Unauthorized** | Chưa có credential hợp lệ |
| JWT sai chữ ký, issuer, audience, thời hạn hoặc loại token | **401 Unauthorized** | Token không hợp lệ với API |
| Opaque introspection active=false | **401 Unauthorized** | Token không hoạt động |
| Token hợp lệ nhưng thiếu scope bắt buộc | **403 Forbidden** | Không đủ quyền được cấp |
| Token đủ scope nhưng bị từ chối theo tenant/ownership | **403 Forbidden** hoặc 404 theo chính sách che giấu | Không đủ quyền tài nguyên |
| JWKS hoặc introspection lỗi, không có cách xác minh an toàn | **Từ chối/fail closed**, có thể 5xx/503 | Không được biến lỗi hệ thống thành Permit |

Ví dụ challenge cho token không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Đối với Bearer token, cách dùng **WWW-Authenticate** và mã lỗi nên tuân thủ RFC 6750 theo trường hợp áp dụng. Không trả toàn bộ claims hoặc nguyên token trong thông báo lỗi; không nêu chi tiết nội bộ giúp người lạ dò policy.

Log phía server có thể ghi **request ID**, loại lỗi (INVALID_SIGNATURE, INVALID_ISSUER, INVALID_AUDIENCE, EXPIRED_TOKEN), tên policy và phiên bản cấu hình, nhưng **không ghi nguyên access token, refresh token, authorization code, client secret hoặc private key**. Nếu cần liên hệ sự kiện giữa nhiều yêu cầu, dùng định danh/safe fingerprint được thiết kế để không tái sử dụng làm credential.

### Fail closed không có nghĩa phải luôn trả 401

Nếu API không thể tải JWKS cần thiết hoặc introspection service đang lỗi, nó có thể trả lỗi **503** để báo phụ thuộc tạm thời không hoạt động, hoặc từ chối theo policy vận hành; nhưng không được cho phép request nhạy cảm chỉ vì bước validate thất bại. Phân biệt **token chắc chắn không hợp lệ** và **hệ thống tạm không xác minh được**, đồng thời tránh lộ nội dung bảo mật.

## 14. Kiểm thử: token decode được nhưng vẫn phải bị từ chối

Hãy xây dựng cả **positive tests** và **negative tests**. Mục tiêu không phải chỉ kiểm parser trả ra JSON, mà phải xác minh Resource Server **không trả dữ liệu hay tạo side effect** khi token không hợp lệ.

| Tình huống | Decoder có thể đọc JSON? | Kết quả đúng |
|---|---|---|
| JWT được ký hợp lệ, issuer/audience đúng, còn hạn, đủ scope/quyền | Có | Permit thao tác cụ thể |
| Payload tự tạo với role=ADMIN nhưng chữ ký sai | Có | Reject token |
| JWT có alg không nằm trong allowlist | Có thể | Reject token |
| JWT với header kid trỏ đến key của issuer khác | Có | Reject token |
| JWT gắn jku/x5u trỏ nguồn ngoài allowlist | Có thể | Không tải/tin nguồn tùy ý; reject nếu không xác minh được |
| JWT chữ ký hợp lệ nhưng iss thuộc staging | Có | Reject ở production |
| JWT đúng issuer nhưng aud=payments-api gửi Orders API | Có | Reject token |
| JWT đúng issuer/aud nhưng exp đã hết hạn | Có | Reject token |
| JWT có nbf ở tương lai | Có | Reject token |
| JWT thiếu claim bắt buộc theo profile áp dụng | Có | Reject token |
| JWT có exp sai kiểu, aud sai kiểu | Có thể | Reject token theo profile |
| ID token hợp lệ dành cho shop-web gửi vào Orders API | Có | Reject vì sai loại/audience |
| JWT hợp lệ, scope thiếu orders:read | Có | Deny authorization |
| JWT hợp lệ, đủ scope nhưng user không thuộc tenant | Có | Deny authorization |
| Opaque token introspection HTTP 200, active=false | Không cần decode | Reject token |
| Introspection timeout/không xác thực được | Không liên quan | Không fail open |
| Key đã bị thu hồi nhưng còn trong JWKS cache | Có | Reject ở mọi instance |
| Token đã bị đánh cắp, có chữ ký đúng và còn hạn | Có | Có thể bị replay nếu không có cơ chế chặn/ràng buộc; cần kiểm soát bổ sung |

### Một bài test mang tính minh họa

**Cho trước:** Orders API có trusted issuer **https://auth.example.org** và expected audience **orders-api**.

**Khi:** request mang một chuỗi JWS do test tạo với payload:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:write",
  "exp": 1900000800,
  "role": "ADMIN"
}
~~~

nhưng **chữ ký không hợp lệ**.

**Thì:** API phải từ chối trước khi thực hiện thao tác; không cập nhật đơn hàng, không trả dữ liệu bảo vệ. Nếu test chỉ khẳng định **decodePayloadOnly** trả JSON, nó **không chứng minh** hệ thống đang xác thực token đúng.

Chạy các negative tests bằng **token/khóa thử nghiệm trong môi trường được phép**. Tránh sao chép bearer token thực lên công cụ bên ngoài chỉ để xem payload.

## 15. Checklist triển khai validation an toàn

1. **Đúng ngữ cảnh:** API nhận access token, không nhầm ID token/refresh token?
2. **Trust anchor:** issuer, audience và nguồn key/introspection lấy từ cấu hình đáng tin, không từ token chưa verify?
3. **JOSE:** thuật toán, kiểu key, kid, typ và header quan trọng có được kiểm theo profile/allowlist?
4. **Signature:** JWT được xác minh bằng key đúng issuer, không fallback decode-only khi lỗi?
5. **Claims:** iss, aud, exp, nbf, iat và các claims bắt buộc có đúng kiểu/giá trị theo profile?
6. **Audience:** API có kiểm chính mình là audience, không dùng substring hoặc chấp nhận mọi audience?
7. **Token type:** đã phân biệt rõ OAuth access token và OIDC ID token?
8. **Opaque:** introspection có TLS, xác thực Resource Server, active=true, audience và metadata đủ để ra quyết định?
9. **Authorization:** scope chính xác, quyền theo tenant/owner/role và trạng thái hiện hành được kiểm tại nơi bảo vệ tài nguyên?
10. **Revocation:** có cách xử lý token, signing key hoặc issuer bị thu hồi, kể cả verifier có cache không?
11. **Storage/replay:** bearer token không lộ qua URL/log, và có chính sách TTL/sender-constraining/refresh rotation khi cần?
12. **Error behavior:** token không xác minh được không bao giờ mặc định Permit; lỗi trả ra không lộ secrets?
13. **Tests:** đã kiểm chữ ký sai, issuer/audience sai, token sai loại, hết hạn, scope thiếu, cache key cũ và policy tài nguyên?

## 16. Câu hỏi tự đánh giá

**1. Giải mã được payload JWT có chứng minh issuer cấp token không?** Không. Base64url chỉ là encoding. Chứng cứ nguồn phát hành đến từ xác minh mật mã với key đúng issuer và đối chiếu claims.

**2. Một JWT có chữ ký hợp lệ đã đủ để cho phép gọi mọi API chưa?** Chưa. Token còn phải đúng issuer, audience, thời hạn, loại token, trạng thái thu hồi và có đủ quyền cho hành động/tài nguyên.

**3. Vì sao không tự tải key từ jku của token?** Vì URL trong header chưa xác minh có thể do kẻ tấn công kiểm soát; dùng nó làm nguồn tin cậy mở đường cho key substitution hoặc truy cập URL ngoài ý muốn.

**4. ID token có sub hợp lệ có thể dùng thay access token không?** Không. ID token dành cho client theo OIDC và có audience/mục đích khác Resource Server.

**5. Introspection trả HTTP 200 có đủ để tin opaque token không?** Không. Cần kiểm active=true, nguồn introspection đáng tin và ràng buộc audience/scope/policy.

**6. Nếu role=ADMIN nằm trong JWT được ký hợp lệ nhưng role đã bị gỡ khỏi database, API có nhất thiết còn cho phép không?** Không. Nếu chính sách yêu cầu quyền hiện hành, API phải kiểm entitlement mới hoặc cơ chế thu hồi tương đương.

**7. Khi private signing key bị lộ, tại sao chữ ký có thể verify được token giả?** Vì kẻ tấn công giữ được key tạo chữ ký và Resource Server vẫn tin public key tương ứng. Cần chặn key/issuer bị ảnh hưởng.

**8. Opaque token và JWT có chữ ký có tự chống phát lại bearer token không?** Không. Cả hai có thể bị người nắm token sử dụng lại khi còn hiệu lực; cần biện pháp bảo vệ nơi lưu, thu hồi và sender-constraining khi phù hợp.

**Ghi nhớ:** **Decode để đọc; verify để xác lập nguồn và tính toàn vẹn; validate để chứng minh token phù hợp ngữ cảnh; authorize để quyết định quyền.** Không dùng bất kỳ claim nào từ token chưa xác minh để cấp quyền. Một Resource Server an toàn luôn bắt đầu từ **issuer/key/introspection được tin**, kiểm **chữ ký hoặc trạng thái, audience, thời hạn, loại token**, rồi mới đánh giá **scope và quyền trên tài nguyên**. Khi không có bằng chứng đủ tin cậy, quyết định an toàn là **từ chối**, không phải tin dữ liệu vừa giải mã.
