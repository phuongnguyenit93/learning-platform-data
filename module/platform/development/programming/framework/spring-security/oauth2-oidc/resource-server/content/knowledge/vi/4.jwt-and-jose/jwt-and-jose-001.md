# JWT là tập claims được biểu diễn theo một định dạng token

Trong hệ sinh thái **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, JWT xuất hiện thường xuyên dưới dạng access token hoặc ID token. Tuy nhiên, trước khi cấu hình xác thực JWT, cần hiểu đúng khái niệm nền tảng: **JWT (JSON Web Token) là một cách biểu diễn tập hợp các phát biểu (claims) dưới dạng token có cấu trúc chuẩn**, để các hệ thống có thể trao đổi và xác minh những phát biểu đó theo quy tắc thống nhất.

Một JWT có thể nói rằng một chủ thể là `user-123`, do `https://identity.example.test` phát hành, được dành cho `orders-api`, có hiệu lực trong một khoảng thời gian và mang scope `orders.read`. Các phát biểu này là **dữ liệu**, còn việc dữ liệu ấy có đáng tin, token dành cho hệ thống nào và người dùng có được đọc đơn hàng cụ thể hay không là những vấn đề cần kiểm tra riêng.

> **Ý chính:** Claim là một phát biểu mang tên và giá trị; **JWT Claims Set** là tập các claim; **JWT** là cách đưa tập đó vào cấu trúc token dựa trên các chuẩn JOSE. Token có định dạng JWT không mặc nhiên hợp lệ, được mã hóa bí mật hoặc có quyền truy cập mọi API.

## 1. Từ claim đến JWT Claims Set

### 1.1. Claim là gì?

Trong ngữ cảnh JWT, một **claim** là một cặp **tên → giá trị** biểu diễn thông tin về một chủ thể hoặc về chính token.

Ví dụ:

| Tên claim | Giá trị minh họa | Phát biểu tương ứng |
| --- | --- | --- |
| `sub` | `"user-123"` | Chủ thể mà token nói tới có định danh `user-123`. |
| `iss` | `"https://identity.example.test"` | Bên tự nhận là nhà phát hành token. |
| `aud` | `"orders-api"` | Token được định hướng đến Orders API. |
| `scope` | `"orders.read"` | Token mang phạm vi quyền đọc đơn hàng theo hợp đồng hệ thống. |
| `exp` | `1893459600` | Token hết hiệu lực theo thời điểm Unix time tương ứng. |

Claim có thể mang giá trị chuỗi, số, boolean, mảng, object hoặc `null` theo quy tắc JSON và từng đặc tả claim. Không phải claim nào cũng được phép dùng mọi kiểu dữ liệu: chẳng hạn `exp` dùng **NumericDate**, còn `aud` có thể là chuỗi hoặc mảng chuỗi.

### 1.2. Claims Set là một JSON object

**JWT Claims Set** là một JSON object chứa các claim. Ví dụ:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "iat": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-7"
}
~~~

Ở đây:

- `iss`, `sub`, `aud`, `exp`, `iat` là những tên claim đã được chuẩn JWT định nghĩa.
- `scope` thường được dùng trong hệ OAuth 2.0, nhưng ý nghĩa cụ thể và cách biểu diễn cần tuân theo **profile access token / thỏa thuận với nhà phát hành**; nó không nằm trong bảy registered claim của RFC 7519.
- `tenant_id` là claim mở rộng theo hệ thống, chỉ đáng tin khi token đã qua xác minh và hợp đồng định nghĩa nguồn gốc, ý nghĩa của nó.

**JSON object ở trên chưa phải một chuỗi JWT hoàn chỉnh.** Đây là *nội dung* cần được biểu diễn dưới dạng token, ví dụ đặt vào payload của một **JWS** đã ký. Bên nhận không nên chỉ nhận một JSON Claims Set không có cơ chế bảo đảm tính toàn vẹn rồi coi là token hợp lệ.

### 1.3. “Tập claims” không có nghĩa “mọi thứ trong JSON đều đáng tin”

Một người dùng có thể tự tạo JSON có claim `"role": "admin"`. Điều đó chỉ cho thấy *họ đã viết ra một phát biểu*, không chứng minh tổ chức đã cấp quyền admin.

Để API tin claim, cần xác minh rằng:

1. Token được bảo vệ bằng cơ chế mật mã được hệ thống chấp nhận.
2. Token do đúng **issuer** phát hành và hướng tới đúng **audience**.
3. Token còn hiệu lực và đáp ứng những ràng buộc về loại token, Client, scope hoặc chính sách cần thiết.
4. Claim có ý nghĩa mà Resource Server và Authorization Server đã thống nhất.

Các bước đó thuộc quá trình **validation và authorization**, không phải tự động phát sinh chỉ vì có JSON.

## 2. Ba lớp cần tách riêng: Claims Set, JOSE và ngữ nghĩa ứng dụng

Để không nhầm JWT với một cơ chế xác thực hoàn chỉnh, có thể tách ba lớp:

| Lớp | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Claims Set (JWT, RFC 7519)** | Token tuyên bố những thông tin nào? | `iss`, `sub`, `aud`, `exp`, `scope` |
| **JOSE (JWS/JWE/JWK)** | Thông tin được đóng gói, ký, bảo vệ toàn vẹn hoặc mã hóa như thế nào? | JWS compact với chữ ký RS256; JWK/JWKS chứa khóa công khai |
| **OAuth 2.0 / OIDC / ứng dụng** | Token được dùng để làm gì và quyền nào được thực thi? | Access token dành cho Orders API; ID token dành cho Client; scope `orders.read` |

**JWT** không tự định nghĩa đầy đủ quy trình đăng nhập, cấp token, refresh token, revocation, role của công ty hoặc quyền sở hữu từng bản ghi. Nó là cách biểu diễn claim; các quy tắc còn lại đến từ profile, giao thức và chính sách hệ thống.

Các chuẩn nền tảng thường gặp:

- **RFC 7519 (JWT):** Cấu trúc/ý nghĩa JWT và các registered claim names.
- **RFC 7515 (JWS):** JSON Web Signature, cách bảo vệ tính toàn vẹn và xác thực nguồn phát hành dữ liệu bằng chữ ký số/MAC.
- **RFC 7516 (JWE):** JSON Web Encryption, cách mã hóa để bảo vệ tính bí mật của dữ liệu.
- **RFC 7517 (JWK):** JSON Web Key, cách biểu diễn khóa bằng JSON.
- **RFC 7518 (JWA):** JSON Web Algorithms, các mã định danh thuật toán.
- **RFC 8725 (JWT Best Current Practices):** Các lưu ý bảo mật khi tạo và xác minh JWT.

## 3. Một JWT thường trông như thế nào?

Kiểu JWT phổ biến ở các Resource Server là **JWT được ký bằng JWS Compact Serialization**, biểu diễn thành ba đoạn văn bản phân tách bằng dấu chấm:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Trong đó:

1. **JOSE protected header** cho biết các tham số mật mã/định dạng, như `alg`, `kid`, `typ`.
2. **Payload** chứa JWT Claims Set đã được mã hóa thành byte và Base64URL.
3. **Signature** bảo vệ tính toàn vẹn của phần header và payload; thuật toán ký/MAC và khóa phải được bên xác minh tin cậy.

~~~mermaid
flowchart TD
    JWT["JWT dạng JWS Compact"]
    Header["JOSE header\nalg, typ, kid"]
    Payload["Claims Set\niss, sub, aud, exp, scope..."]
    Signature["Chữ ký/MAC\nbảo vệ header + payload"]
    JWT --> Header
    JWT --> Payload
    JWT --> Signature
    Header --> EncHeader["Base64URL"]
    Payload --> EncPayload["Base64URL"]
    EncHeader --> Joined["header.payload.signature"]
    EncPayload --> Joined
    Signature --> Joined
~~~

Ví dụ header đã giải mã:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-01"
}
~~~

Ví dụ payload đã giải mã:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "iat": 1893456000,
  "scope": "orders.read"
}
~~~

Và chuỗi token khi gửi HTTP nhìn tương tự:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJhbGciOi...eyJpc3MiOi...HkQ8...
~~~

Chuỗi trên chỉ có tính minh họa, không phải một JWT hoàn chỉnh để sử dụng. **Dấu chấm và Base64URL là biểu diễn dữ liệu; độ tin cậy của token đến từ việc xác minh mật mã cùng với các điều kiện chấp nhận token.**

### 3.1. Header không phải Claims Set

Đây là phân biệt quan trọng:

| Thành phần | Chứa gì? | Lưu ý khi xác minh |
| --- | --- | --- |
| **JOSE header** | `alg`, `kid`, `typ`, có thể có `cty` | Giúp xác định cách xử lý cấu trúc token; các giá trị do token cung cấp phải nằm trong chính sách thuật toán/khóa cho phép. |
| **JWT Claims Set** | `iss`, `sub`, `aud`, `exp`, các claim ứng dụng | Chỉ sử dụng sau khi token được xác minh, kiểm tra issuer/audience/thời hạn và các điều kiện liên quan. |
| **JWS signature** | Kết quả ký/MAC trên input được đặc tả | Chứng minh payload/header không bị sửa bởi bên không có khóa hợp lệ; không tự cấp quyền truy cập dữ liệu. |

Ví dụ `alg = RS256` nằm ở **header**, không phải claim `scope` ở payload. `kid` giúp Resource Server chọn khóa từ tập JWKS tin cậy khi có nhiều khóa, nhưng **không cho phép token tự chỉ một nơi bất kỳ để tải khóa và mặc nhiên tin nơi đó**.

### 3.2. Base64URL là mã hóa biểu diễn, không phải mã hóa bí mật

Các đoạn header và payload của một JWS compact thường có thể **giải mã Base64URL mà không cần khóa**. Vì vậy:

~~~text
Base64URL ≠ Encryption
Signed JWT ≠ Secret payload
Decode JWT ≠ Verify JWT
~~~

Chữ ký số bảo vệ **tính toàn vẹn và tính xác thực bằng khóa tin cậy**, không che giấu nội dung. Không nên đưa mật khẩu, access key, số thẻ, bí mật hệ thống hoặc thông tin nhạy cảm không cần thiết vào payload JWT chỉ vì token đã được ký.

**HTTPS/TLS vẫn cần thiết**, kể cả khi dùng JWT ký hợp lệ: Bearer token bị lộ có thể bị người khác sử dụng trong thời gian token còn hiệu lực.

## 4. JWT có bắt buộc là JWS ba đoạn không?

Không. JWT có thể được biểu diễn bằng **JWS** (được ký/MAC để bảo vệ toàn vẹn), **JWE** (được mã hóa để bảo vệ nội dung), hoặc các cách kết hợp theo JOSE.

### 4.1. JWT được ký (JWS)

JWS Compact Serialization thông thường gồm **3 đoạn**:

~~~text
protectedHeader.payload.signature
~~~

Trong ứng dụng Spring Security Resource Server, cấu hình `oauth2ResourceServer().jwt()` thường xử lý loại **signed JWT** do Authorization Server cấp. Resource Server xác minh chữ ký bằng khóa tin cậy, ví dụ khóa công khai lấy từ JWKS được issuer công bố.

### 4.2. JWT được mã hóa (JWE)

JWE Compact Serialization gồm **5 đoạn**:

~~~text
protectedHeader.encryptedKey.iv.ciphertext.authenticationTag
~~~

Với JWE, claim không đọc trực tiếp được nếu không có khóa giải mã thích hợp. Token cũng có thể **lồng nhau** (nested JWT), ví dụ ký nội dung bằng JWS rồi mã hóa bằng JWE; khi đó bên nhận cần giải mã lớp ngoài và xác minh lớp trong theo chính sách. Trường hợp nested JWT có thể dùng tham số header `cty = "JWT"` để mô tả nội dung lồng bên trong.

**Không mặc định Spring Security JWT decoder cấu hình cho signed JWT sẽ tự giải mã mọi JWE**. Cơ chế JWE đòi hỏi hỗ trợ xử lý và quản lý khóa riêng, được thiết kế phù hợp với nhà phát hành/token profile.

### 4.3. “Unsecured JWT” và thuật toán `none`

Đặc tả JWT có mô tả dạng **Unsecured JWT** với header `"alg": "none"`, không có chữ ký bảo vệ. Đây không phải loại token được Resource Server thông thường tin dùng để xác thực yêu cầu API. Đối với Bearer access token, **chỉ chấp nhận thuật toán bảo vệ, khóa và kiểu token đã được cấu hình cho trường hợp sử dụng cụ thể**; không cho token tự quyết định tắt xác minh mật mã.

Nói cách khác, ba đoạn cách nhau bằng dấu chấm hoặc JSON hợp lệ **không bảo đảm token đã được ký và được xác minh đúng**.

## 5. Nhóm claim được chuẩn JWT định nghĩa

RFC 7519 đăng ký bảy tên claim thông dụng sau:

| Claim | Tên | Ý nghĩa | Kiểu / quy tắc đáng chú ý |
| --- | --- | --- | --- |
| `iss` | Issuer | Bên phát hành JWT | StringOrURI; Resource Server kiểm tra với issuer tin cậy |
| `sub` | Subject | Chủ thể được mô tả bởi JWT | StringOrURI; ý nghĩa cụ thể do profile và issuer quy định |
| `aud` | Audience | Những đối tượng mà JWT hướng đến | Chuỗi hoặc mảng chuỗi; phải chứa Resource Server nhận token |
| `exp` | Expiration Time | Thời điểm token không còn được chấp nhận | NumericDate; sau thời điểm này token hết hạn |
| `nbf` | Not Before | Thời điểm sớm nhất được chấp nhận | NumericDate |
| `iat` | Issued At | Thời điểm phát hành | NumericDate |
| `jti` | JWT ID | Định danh duy nhất của JWT nếu dùng | Chuỗi; giúp quản lý token/audit theo thiết kế |

Các claim này là **registered claim names**, không có nghĩa RFC 7519 bắt buộc mọi JWT phải có đủ cả bảy. Một **profile sử dụng JWT** (ví dụ JWT access token theo RFC 9068, ID token theo OIDC, hoặc hợp đồng nội bộ) có thể yêu cầu những claim nhất định. Resource Server phải áp dụng các yêu cầu của profile/thỏa thuận đang triển khai.

### 5.1. Các claim liên quan thời gian

`exp`, `nbf` và `iat` dùng **NumericDate**: số giây kể từ 1970-01-01T00:00:00Z, có thể có phần thập phân. Đây **không phải số mili-giây như `System.currentTimeMillis()` trong Java**.

Ví dụ:

~~~json
{
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600
}
~~~

Ý nghĩa:

- Token được phát hành tại `iat`.
- Token không nên được chấp nhận trước `nbf`.
- Token phải bị từ chối tại hoặc sau `exp` (có thể có dung sai lệch đồng hồ phù hợp khi xác minh).

Để xử lý lệch đồng hồ, hệ thống có thể dùng **clock skew** nhỏ, được quản trị theo chính sách. Không nên dùng sai đơn vị thời gian, bỏ qua `exp` hoặc đặt dung sai quá lớn để tránh lỗi tạm thời.

### 5.2. `iss`, `sub` và `aud` không thay thế nhau

Ví dụ một access token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read"
}
~~~

- **`iss`** trả lời **ai phát hành**.
- **`sub`** trả lời **token nói về chủ thể nào**.
- **`aud`** trả lời **token được gửi tới bên nào**.
- **`client_id`** (theo profile/nhà phát hành) cho biết Client nào liên quan tới việc cấp token.
- **`scope`** trả lời **phạm vi quyền đã được cấp**.

Nếu chỉ xác minh chữ ký mà không kiểm tra `aud`, Orders API có nguy cơ chấp nhận token do cùng issuer phát cho API khác. Nếu chỉ kiểm tra `sub` mà không kiểm tra scope và quyền dữ liệu, API có nguy cơ cho phép chủ thể thực hiện thao tác vượt quyền.

### 5.3. Subject không nhất thiết là một người dùng

Trong luồng **Authorization Code** có người dùng, `sub` thường liên quan tới người dùng được xác thực; trong luồng **client_credentials**, token đại diện cho Client/dịch vụ và có thể có quy ước subject khác. Không mặc định mọi `sub` trong access token đều tương ứng một tài khoản người dùng trong bảng `users`.

Khi gắn danh tính lâu dài vào dữ liệu ứng dụng, cặp **(`iss`, `sub`)** thường an toàn hơn chỉ dùng `sub` vì các issuer khác nhau có thể phát cùng một chuỗi subject. Claim `email` hoặc `preferred_username` không mặc định là định danh ổn định hay đủ để cấp quyền.

## 6. Registered, public và private claims

Một JWT không bị giới hạn ở các tên claim `iss`, `sub`, `aud`, v.v. Có ba nhóm tên claim cần phân biệt:

1. **Registered claim names:** Các tên đã đăng ký trong JWT, ví dụ `iss`, `sub`, `exp`. Chúng có ngữ nghĩa chuẩn.
2. **Public claim names:** Các tên công khai được định nghĩa/đăng ký theo cơ chế tránh xung đột tên, ví dụ tên có namespace/URI được kiểm soát.
3. **Private claim names:** Các tên do hai bên tự thỏa thuận, ví dụ `tenant_id` hoặc `department`. Chúng có thể va chạm tên hoặc khác nghĩa giữa nhà phát hành.

Ví dụ một hệ thống khai báo:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "https://claims.example.test/tenant_id": "tenant-7",
  "https://claims.example.test/permissions": ["order:read"]
}
~~~

Các URI trên **là tên claim**, không có nghĩa Resource Server phải truy cập Internet tới địa chỉ đó. Cách đặt tên giúp giảm xung đột giữa các namespace claim; giá trị và cách giải thích vẫn cần hợp đồng giữa các bên.

**Lưu ý:** Claim có tên giống nhau giữa hai hệ thống không chứng minh chúng có cùng nghĩa. `roles: ["admin"]` của một issuer không được hiểu là admin toàn hệ thống nếu API chưa thỏa thuận chính xác role nào, trong tenant nào và ai có quyền cấp.

## 7. JWT và OAuth 2.0/OIDC: định dạng khác với mục đích sử dụng

Phải phân biệt **token là định dạng gì** và **token dùng để làm gì**:

| Khái niệm | Định nghĩa ở mức mục đích | Có bắt buộc là JWT? |
| --- | --- | --- |
| **JWT** | Định dạng token để biểu diễn claims set trong JOSE | Đây chính là định dạng, không chỉ rõ token thuộc nghiệp vụ nào |
| **OAuth 2.0 access token** | Credential dùng để truy cập Resource Server theo quyền được cấp | **Không**; có thể opaque hoặc theo định dạng khác, JWT là lựa chọn phổ biến |
| **OIDC ID token** | Token mô tả kết quả xác thực người dùng cho OIDC Client | **Có** theo OIDC; dùng cấu trúc JWT theo các quy tắc của OIDC |
| **OAuth 2.0 refresh token** | Credential để Client xin access token mới khi được phép | **Không** có yêu cầu chung phải là JWT |

Một token không trở thành **access token hợp lệ** chỉ vì là JWT. Ngược lại, một access token có thể hoàn toàn hợp lệ trong OAuth 2.0 dù là opaque token không đọc được claim bằng cách tách dấu chấm.

### 7.1. ID token không phải access token của API

OIDC ID token thường có `aud` là **`client_id` của OIDC Client**. Ví dụ Client `shop-web` nhận ID token với audience `shop-web` để xác nhận người dùng đăng nhập.

Orders API lại mong access token với audience **`orders-api`** và scope như `orders.read`. Vì cả hai token có thể chứa `iss` và `sub`, ứng dụng rất dễ dùng nhầm ID token làm Bearer token gửi API.

API phải từ chối loại token sai mục đích, kể cả khi JWT đó được ký bởi cùng nhà phát hành. Tùy token profile, chính sách xác minh có thể kiểm tra `aud` và các chỉ báo loại token phù hợp (chẳng hạn `typ` cho profile access token). **Không dùng cùng khóa ký làm lý do để bỏ qua việc phân biệt hai loại token**.

### 7.2. JWT access token có profile riêng

**RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens** định nghĩa một profile chuẩn cho JWT access token. Profile này có các yêu cầu về header, claims và quá trình xác minh riêng, ví dụ `typ` có thể là `at+jwt`, khác với một JWT tùy ý có `typ: "JWT"`.

Vì vậy, trước khi viết validator, cần biết **Authorization Server phát hành theo profile nào**, định dạng scope ra sao, audience là giá trị gì và Resource Server được yêu cầu kiểm tra những thuộc tính nào. Không giả định mọi JWT access token của mọi sản phẩm Identity Provider có payload giống nhau.

## 8. Resource Server sử dụng Claims Set như thế nào?

Trong mô hình Spring Security OAuth 2.0, Resource Server thường nhận JWT qua:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Quá trình xử lý khái niệm:

~~~mermaid
flowchart TD
    Request["HTTP request + Bearer token"] --> Extract["Trích xuất token"]
    Extract --> Verify["Xác minh chữ ký, thuật toán và khóa tin cậy"]
    Verify --> Claims["Đọc claims sau khi token được xác minh"]
    Claims --> TokenRules["Kiểm tra iss, aud, exp, nbf, loại token"]
    TokenRules --> Authn["Tạo Authentication / principal / authorities"]
    Authn --> Scope["Kiểm tra scope tại endpoint"]
    Scope --> DataPolicy["Kiểm tra owner, tenant, chính sách nghiệp vụ"]
    DataPolicy --> Response["Trả tài nguyên hoặc từ chối"]
~~~

Trong thực tế, thư viện xác minh chữ ký và claims có thể thực hiện trong cùng một bước của `JwtDecoder`; sơ đồ chỉ diễn đạt **các điều kiện** mà token phải đáp ứng trước khi API trả dữ liệu.

### 8.1. Claims Set được ánh xạ thành đối tượng Java

Sau khi JWT đã được xác minh, Spring Security có thể cung cấp `Jwt` thông qua `Authentication` hoặc `@AuthenticationPrincipal`:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {

    @GetMapping("/api/whoami")
    UserInfo whoAmI(@AuthenticationPrincipal Jwt jwt) {
        return new UserInfo(
                jwt.getIssuer().toString(),
                jwt.getSubject(),
                jwt.getAudience());
    }

    record UserInfo(String issuer, String subject,
                    java.util.List<String> audience) {}
}
~~~

Ví dụ này cho thấy cách đọc claim **sau bước xác minh do security filter thực hiện**. Không dùng nó làm endpoint công khai khi chưa có cấu hình bảo vệ API. Trong ứng dụng thật, nên cân nhắc thông tin danh tính nào được phép trả cho Client và tránh tiết lộ các claim không cần thiết.

### 8.2. Cấu hình Resource Server nhận signed JWT

Dependency Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Khai báo issuer tin cậy:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
~~~

Với issuer được cấu hình đúng, Spring Security hỗ trợ khám phá metadata/khóa xác minh phù hợp và kiểm tra chữ ký, thời hạn và issuer theo cấu hình. **Kiểm tra audience riêng của Orders API là một điều khoản độc lập**: không nên cho rằng token do đúng issuer phát hành thì token luôn dành cho API này.

Ví dụ cấu hình validator kiểm tra `aud = orders-api` đồng thời với issuer và thời hạn:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwks-uri}") String jwksUri,
            @Value("${app.security.expected-audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> standardValidation =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidation = jwt ->
                jwt.getAudience().contains(audience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token",
                            "Unexpected audience", null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    standardValidation, audienceValidation));
        return decoder;
    }
}
~~~

Giả sử ứng dụng có cấu hình:

~~~yaml
app:
  security:
    issuer: https://identity.example.test
    jwks-uri: https://identity.example.test/.well-known/jwks.json
    expected-audience: orders-api
~~~

**Đường dẫn JWKS chỉ minh họa**; phải dùng URI được Authorization Server công bố cho hệ thống thực tế. Những ràng buộc về thuật toán, loại token và các claim bắt buộc khác nên được cấu hình theo profile token đã thỏa thuận. Nếu tự tạo `JwtDecoder`, phải bảo toàn các validator mặc định cần thiết thay vì vô tình thay thế chúng bằng một validator chỉ kiểm tra audience.

Để bảo vệ endpoint dựa trên scope:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Ở Spring Security, với các claim scope theo định dạng mặc định được hỗ trợ, ví dụ `scope: "orders.read"`, framework thường chuyển scope thành authority `SCOPE_orders.read`. Nếu nhà phát hành dùng claim `permissions`, `roles` hoặc định dạng `scp` đặc thù, cần thỏa thuận ánh xạ và cấu hình `JwtAuthenticationConverter` phù hợp.

Code trên mô tả cách bảo vệ Bearer token ở phần `/api/**`. Nếu ứng dụng cũng phục vụ trình duyệt bằng cookie/session, cần thiết kế CSRF và các filter chain tương ứng với mô hình xác thực thực tế.

### 8.3. Scope trong JWT không thay thế quyền trên từng bản ghi

Ngay cả khi token đã xác minh có:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Resource Server vẫn phải kiểm tra đơn hàng `42` có thuộc `user-123` hoặc tenant mà người dùng được phép xem hay không. Claim `scope` thể hiện phạm vi quyền được cấp; nó **không tự chứng minh ownership, quan hệ tenant, trạng thái đơn hàng hoặc chính sách phân quyền theo dữ liệu**.

Điều này giúp phân biệt rõ:

- **Authentication:** Xác nhận token/chủ thể có thể tin cậy trong ngữ cảnh request.
- **Authorization:** Quyết định request có được thực hiện thao tác và truy cập đối tượng cụ thể hay không.

## 9. Tại sao chỉ “decode JWT” là chưa đủ?

Đây là sai lầm phổ biến nhất khi mới học JWT. Một thư viện có thể thực hiện:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String payloadJson = new String(
        Base64.getUrlDecoder().decode(token.split("\\.")[1]),
        StandardCharsets.UTF_8);
~~~

Đoạn này chỉ **giải mã một phần văn bản** của chuỗi ba đoạn. Nó **không xác minh chữ ký, issuer, audience, hạn dùng, loại token hoặc quyền**. Không dùng kết quả này để xác thực caller, quyết định role hay truy cập dữ liệu.

Để thấy sự khác biệt:

| Thao tác | Kết luận được | Không kết luận được |
| --- | --- | --- |
| Tách dấu chấm và giải mã Base64URL | Có thể đọc header/payload của dạng JWS compact | Không chứng minh token chân thực |
| Parse JSON Claims Set | Có các trường tên và giá trị nào | Không chứng minh ai phát biểu chúng |
| Xác minh JWS bằng khóa tin cậy | Header/payload khớp chữ ký/MAC hợp lệ theo khóa được chấp nhận | Chưa chắc token đúng audience, thời hạn, loại token hoặc quyền |
| Xác minh issuer, audience, thời hạn, token profile | Token đáp ứng điều kiện nhận của API | Chưa chắc caller có quyền trên từng bản ghi |
| Kiểm tra scope và chính sách đối tượng | Quyết định cho phép thao tác cụ thể | Không thay thế quản trị vòng đời token và kiểm soát dữ liệu khác |

Trong code production, hãy để `JwtDecoder` và lớp bảo mật tiêu chuẩn thực hiện việc xác minh, rồi sử dụng những claim đã qua kiểm tra.

## 10. JWT không mặc nhiên làm được những việc gì?

### 10.1. JWT không mặc định được mã hóa bí mật

Payload của signed JWS thường có thể đọc được. Nếu cần bảo vệ tính bí mật của claim trước bên nhận không có quyền, phải thiết kế dữ liệu phát hành và/hoặc dùng JWE cùng cách phân phối khóa thích hợp. Đừng đưa claim nhạy cảm vào token chỉ vì “đã ký”.

### 10.2. JWT không tự hết hiệu lực ngay khi người dùng đăng xuất

Một signed JWT được xác minh cục bộ có thể tiếp tục hợp lệ cho tới `exp` nếu không có cơ chế bổ sung kiểm soát thu hồi/phiên. Đăng xuất khỏi website, thu hồi refresh token hoặc đổi mật khẩu **không đương nhiên** khiến mọi access token JWT đã phát hành mất hiệu lực ngay trên tất cả Resource Server.

Giải pháp tùy yêu cầu có thể là access token sống ngắn, tra cứu trạng thái token, danh sách thu hồi, introspection hoặc cơ chế quản lý phiên/phân quyền mới nhất.

### 10.3. JWT không bảo đảm bên nhận hiểu claim đúng nghĩa

Hai Authorization Server có thể dùng `roles` với hai kiểu dữ liệu hoặc định nghĩa role khác nhau. Một Client có thể xin `orders.read` nhưng issuer chỉ phát hành `orders.summary`. API phải kiểm tra **claim thực tế và profile được chấp nhận**, không dựa vào mong muốn của Client hoặc tự giả định giá trị.

### 10.4. JWT không loại bỏ nhu cầu bảo vệ Bearer token

Bearer token là credential: ai có token hợp lệ thường có thể trình token để gọi API theo quyền token mang. Cần truyền qua HTTPS, giữ token khỏi log, tránh lộ qua URL, thiết kế lưu trữ phù hợp với loại Client và giới hạn phạm vi/quyền/thời gian sống.

## 11. Những lưu ý bảo mật khi nhận JWT từ bên ngoài

Khi Resource Server tiếp nhận JWT, các điều kiện sau thường là một phần của hợp đồng:

| Điều kiện | Mục đích |
| --- | --- |
| Chỉ tin **issuer** cấu hình trước | Tránh nhận token từ bên không được ủy quyền |
| Chỉ tin **khóa** và **thuật toán** được cho phép | Tránh trường hợp token tự lựa chọn cơ chế xác minh không an toàn |
| Kiểm tra **`aud`** dành cho API | Tránh nhận token của API khác |
| Kiểm tra **`exp`**, `nbf` và thời gian | Tránh chấp nhận token quá hạn/chưa có hiệu lực |
| Phân biệt **access token với ID token** | Tránh nhầm ngữ cảnh xác thực người dùng với ủy quyền truy cập API |
| Kiểm tra **scope/authorities** đúng chính sách | Chỉ cho phép hành động được cấp |
| Kiểm tra **tenant/owner/role nghiệp vụ** | Ngăn truy cập dữ liệu không thuộc quyền |
| Giới hạn dữ liệu claim và log | Giảm rò rỉ thông tin nhạy cảm |
| Quay vòng khóa và quản trị token | Hỗ trợ vận hành an toàn theo thời gian |

Đặc biệt cần tránh **algorithm confusion**: không chọn cách xác minh chỉ dựa trên giá trị `alg` do token chưa xác thực đưa tới, không nhận `alg: none` cho các token yêu cầu bảo vệ mật mã, không nhầm khóa công khai với bí mật dùng cho thuật toán MAC và không nạp khóa từ URI tùy ý do token chỉ định. Thư viện JOSE/JWT đáng tin cậy cùng cấu hình danh sách thuật toán và khóa cố định theo issuer giúp giảm những rủi ro này.

Trong kiến trúc dùng nhiều issuer, phải gắn từng issuer với bộ khóa, audience, thuật toán và quy tắc claim tương ứng. Không gom các khóa từ nhiều nơi vào một kho rồi chỉ kiểm tra “chữ ký đúng bằng khóa bất kỳ”.

## 12. Ví dụ từ token tới quyết định API

Giả sử Authorization Server phát hành **JWT access token** đã ký với payload:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "iat": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-7"
}
~~~

Client gửi token tới Orders API để gọi `GET /api/orders/42`. Resource Server xử lý theo các ranh giới:

1. **Bảo vệ dữ liệu token:** Chữ ký và thuật toán được xác minh bằng khóa công khai tin cậy do issuer cung cấp.
2. **Kiểm tra claim về vòng đời và đối tượng nhận:** `iss` đúng, `aud` chứa `orders-api`, token chưa hết hạn, không vi phạm `nbf` và các điều kiện profile.
3. **Xác thực chủ thể:** `sub = user-123` và thông tin tenant/Client được đưa vào ngữ cảnh theo hợp đồng, không tự suy ra quyền admin.
4. **Kiểm tra phạm vi thao tác:** Scope `orders.read` đáp ứng endpoint GET đọc đơn hàng.
5. **Kiểm tra bản ghi:** Order 42 thực sự được phép hiển thị cho `user-123` trong `tenant-7` theo dữ liệu chính thức.
6. **Trả kết quả:** Nếu đáp ứng mọi điều kiện, trả dữ liệu; nếu không, trả lỗi phù hợp.

| Trường hợp | Kết quả điển hình |
| --- | --- |
| Không có token hoặc chữ ký/issuer/audience không hợp lệ | **401 Unauthorized** |
| Token hết hạn hoặc chưa có hiệu lực | **401 Unauthorized** |
| Token hợp lệ nhưng thiếu `orders.read` | **403 Forbidden** |
| Đủ scope nhưng Order 42 thuộc người dùng/tenant khác | **403 Forbidden** hoặc **404 Not Found** theo chính sách không tiết lộ tài nguyên |
| Token hợp lệ và đầy đủ quyền đối với Order 42 | **200 OK** nếu đơn tồn tại |

**Tính đúng đắn ở bước 1–2 chưa thay thế tính đúng đắn của bước 4–5.** Đây là lý do Spring Security có các tầng xác thực token, ánh xạ authorities và kiểm tra authorization theo endpoint/nghiệp vụ.

## 13. Ghi nhớ bằng ba ví dụ đối chiếu

**Ví dụ A — Claims Set chưa phải token được xác minh**

~~~json
{"sub": "user-123", "role": "admin"}
~~~

Đây chỉ là JSON với hai claim. Thiếu thông tin về nhà phát hành, tính toàn vẹn, thời hạn và đối tượng nhận; API không có căn cứ để tin người gửi là admin.

**Ví dụ B — JWT có chữ ký hợp lệ nhưng sai đối tượng nhận**

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["billing-api"],
  "scope": "billing.read"
}
~~~

Ngay cả khi chữ ký đúng, **Orders API** phải từ chối token vì `aud` không chứa `orders-api`.

**Ví dụ C — JWT đúng issuer/audience nhưng chưa đủ quyền**

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Nếu token còn hiệu lực và đã qua xác minh, nó có thể đáp ứng yêu cầu scope đọc đơn hàng. Tuy nhiên, request xem đơn của người khác vẫn phải bị từ chối nếu không có quyền theo chính sách dữ liệu.

Ba ví dụ nhắc lại sự khác nhau giữa **phát biểu (claim)**, **định dạng token có bảo vệ (JWT/JWS/JWE)** và **quyền truy cập thực tế (OAuth 2.0/Spring Security authorization)**.

## 14. Câu hỏi tự kiểm tra

**1. Nếu nhìn thấy dấu chấm phân tách ba đoạn và giải mã được payload, có thể kết luận token hợp lệ không?**

Không. Đó chỉ là dấu hiệu thường gặp của JWS compact. Cần xác minh chữ ký/MAC và các điều kiện tin cậy như issuer, audience, thời hạn, token profile và quyền.

**2. Claim `scope` có thuộc bảy registered claims của JWT không?**

Không. `scope` thường thuộc profile/token contract trong OAuth 2.0. Ý nghĩa và cách biểu diễn do nhà phát hành và API thống nhất.

**3. Một token có `aud = profile-api` nhưng có scope `orders.read`, Orders API có nên chấp nhận không?**

Không, trừ khi Orders API được liệt kê trong audience hợp lệ theo hợp đồng. Có scope nghe phù hợp không sửa được audience sai.

**4. Signed JWT có giúp giữ bí mật email hoặc số điện thoại trong payload không?**

Không. Payload JWS thường đọc được qua Base64URL; ký bảo vệ toàn vẹn chứ không mã hóa bí mật. Chỉ đưa dữ liệu cần thiết vào token, hoặc dùng cơ chế bảo vệ bí mật phù hợp.

**5. JWT là một khái niệm đồng nghĩa với OAuth 2.0 access token?**

Không. JWT là một cách biểu diễn claims set. Access token là credential trong OAuth 2.0, có thể là JWT hoặc opaque token; ID token của OIDC cũng dùng JWT nhưng có mục đích khác.

**6. Resource Server đã xác minh chữ ký và `exp`, có thể bỏ kiểm tra quyền nghiệp vụ không?**

Không. Token có thể hợp lệ nhưng chỉ có scope giới hạn, không dành cho API này hoặc không cho phép truy cập bản ghi cụ thể.

---

**Kết luận:** JWT nên được hiểu trước hết là **Claims Set được biểu diễn theo định dạng token chuẩn**, thường dưới dạng JWS có chữ ký hoặc JWE được mã hóa. Những claim như `iss`, `sub`, `aud` và `exp` có ngữ nghĩa chuẩn nhưng **không tự tạo ra sự tin cậy**. Trong Spring Security OAuth 2.0 Resource Server, chỉ đọc và dùng claim sau khi xác minh token theo khóa, issuer, audience, thời hạn và token profile phù hợp; việc cấp quyền thực tế còn phụ thuộc scope và chính sách truy cập tài nguyên của API.
