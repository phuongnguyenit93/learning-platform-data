# Kiểm tra algorithm được cho phép

Một JWT có thể chứa header `"alg": "RS256"`, `"HS256"`, `"ES256"` hoặc thậm chí `"none"`. **Giá trị `alg` do bên gửi token cung cấp không được tự trở thành chính sách bảo mật của API.** Resource server phải có một **danh sách thuật toán được cho phép (*algorithm allowlist*)** xuất phát từ cấu hình tin cậy của issuer, loại token, khóa xác minh và hợp đồng OAuth 2.0/OpenID Connect (OIDC). Chỉ khi thuật toán nằm trong chính sách **và** chữ ký được kiểm tra bằng đúng loại khóa thì mới được dùng claims để xác thực và phân quyền.

Ví dụ: một API được cấu hình chỉ chấp nhận access token **RS256** từ `https://auth.example.com`. Một request mang token có header `alg=HS256` hoặc `alg=none` phải bị từ chối, **kể cả nếu payload có `sub`, `scope` và `aud` trông hợp lệ**. API cũng phải từ chối token RS256 có chữ ký sai, phát hành bởi issuer khác hoặc dành cho API khác.

Trong chương **Token validation** của module bảo mật token, chúng ta sẽ phân biệt JWS/JWE, thiết kế allowlist cho JWT và các loại khóa, giải thích lỗi *algorithm confusion*, triển khai với Java/Spring Security, xử lý JWKS rotation và xây bộ kiểm thử ngăn token giả mạo, bị đánh cắp hoặc sử dụng sai ngữ cảnh.

## 1. Algorithm trong JWT nằm ở đâu?

JWT thường xuất hiện dưới dạng **JWS Compact Serialization**, gồm ba đoạn Base64url:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Một protected header minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "signing-key-2026-11"
}
~~~

Các thành phần có ý nghĩa khác nhau:

| Thành phần | Chức năng | Điều API phải làm |
| --- | --- | --- |
| `alg` | Khai báo thuật toán JWS dùng tạo/xác minh chữ ký hoặc MAC | So với **allowlist đã cấu hình**, không để header tự quyết định chính sách |
| `kid` | Gợi ý ID khóa để tìm trong tập khóa tin cậy | Chỉ tra khóa **trong key set của issuer tin cậy**, kiểm tra kty/use/alg tương thích |
| `typ` | Gợi ý loại JWT, ví dụ `at+jwt` trong access-token profile | Áp dụng validation loại token theo profile, chống nhầm ID token với access token |
| `cty` | Gợi ý kiểu nội dung bên trong, thường gặp ở nested JWT | Xử lý theo profile đã cấu hình; không tự coi token đã xác thực |
| `crit` | Báo các protected-header parameter mở rộng cần hiểu | Từ chối nếu ứng dụng **không hiểu/xử lý được** extension bắt buộc |

Header có thể được đọc **trước khi** kiểm tra chữ ký để chọn candidate key, nhưng tại thời điểm đó **nội dung chưa được tin cậy**. Dù header được bao gồm trong dữ liệu ký của JWS, việc chọn phương thức xác minh dựa hoàn toàn vào header chưa xác minh vẫn có thể tạo lỗi thiết kế.

### 1.1. Đọc được JWT không có nghĩa JWT hợp lệ

Payload:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/payments",
  "scope": "payments.read",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

Đây chỉ là **JSON minh họa**, không phải JWT đã ký. Kẻ tấn công có thể tự tạo payload bất kỳ. Các claim `iss`, `aud`, `scope`, `roles` hoặc `tenant_id` chỉ có giá trị bảo mật sau khi token được xác minh theo **mô hình tin cậy** của resource server.

Chữ ký đúng cũng chưa đủ để cho phép request: API phải tiếp tục kiểm tra **issuer, audience, loại token, thời gian, scope và quyền đối với tài nguyên**.

## 2. Thuật toán nào thường được dùng để ký token?

Các thuật toán JWS có hai nhóm xác thực chữ ký chính:

| Thuật toán JWS | Họ thuật toán | Ai có khả năng tạo chữ ký/MAC? | Bên xác minh cần gì? | Lưu ý |
| --- | --- | --- | --- | --- |
| **HS256** | HMAC-SHA-256, đối xứng | Bất kỳ bên nào biết **shared secret** | Chính shared secret đó | Bên xác minh có secret cũng có thể tạo token giả nếu bị lộ |
| **RS256** | RSA + SHA-256, chữ ký PKCS#1 v1.5 | Bên giữ **RSA private key** | **RSA public key** | Phù hợp nhiều API xác minh, với key size và quản lý khóa đạt policy |
| **PS256** | RSA-PSS + SHA-256 | Bên giữ private key | RSA public key | Khác RS256; không mặc định chấp nhận chỉ vì cùng khóa RSA |
| **ES256** | ECDSA trên P-256 + SHA-256 | Bên giữ EC private key | EC public key P-256 | Cần thư viện triển khai ECDSA/JOSE đúng chuẩn |
| **EdDSA** | Edwards-curve signature, ví dụ Ed25519 | Bên giữ private key | Khóa công khai phù hợp | Chỉ chấp nhận khi profile, thư viện và chính sách hỗ trợ |
| **`none`** | Unsecured JWS | Không cần chữ ký | Không có xác minh chữ ký | **Không chấp nhận cho bearer access token/ID token cần xác thực nguồn** |

**Không có một thuật toán “tốt nhất” bất biến cho mọi hệ thống.** Lựa chọn phụ thuộc mô hình tin cậy, yêu cầu đối tác, khả năng bảo vệ khóa, quy định nội bộ và mức hỗ trợ của AS/RS. Nhưng **một API phải biết chính xác mình chấp nhận thuật toán nào**.

Ví dụ:

- Nếu AS dùng RSA private key còn API chỉ giữ public key, **RS256/PS256** cho phép API xác minh mà không có khả năng tự phát token.
- Nếu AS và API chia sẻ secret **HS256**, mỗi bên có secret đều có thể tạo MAC hợp lệ; rủi ro xâm nhập một API cần được xem xét kỹ.
- Nếu issuer chọn **ES256**, JWT có thể ngắn hơn RSA chữ ký 2048-bit, nhưng **không được đổi thuật toán chỉ nhằm giảm kích thước** rồi bỏ kiểm soát tương thích khóa và profile.

**Độ dài khóa, thuật toán và mục đích khóa là các thuộc tính độc lập nhưng phải khớp nhau.** Chẳng hạn HS256 cần secret entropy đủ cao (tối thiểu 256 bit theo yêu cầu JWA với HMAC SHA-256), không dùng một mật khẩu dễ đoán; RSA/EC cần khóa đáp ứng yêu cầu an toàn của profile và thư viện.

### 2.1. JWS khác JWE: đừng áp cùng cách hiểu cho `alg`

Trong **JWS**, `alg` chỉ thuật toán ký/MAC như `RS256`, `ES256` hoặc `HS256`.

Trong **JWE**, `alg` chỉ **thuật toán quản lý/trao đổi khóa mã hóa** (ví dụ `RSA-OAEP-256`), còn `enc` chỉ **thuật toán mã hóa nội dung** (ví dụ `A256GCM`). JWE compact có năm đoạn:

~~~text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
~~~

Ví dụ header JWE:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT"
}
~~~

**JWE không tự biến `alg=RSA-OAEP-256` thành chữ ký RS256.** Nếu ứng dụng yêu cầu JWT **vừa được ký bởi issuer vừa được mã hóa cho client**, nó phải xác minh **từng lớp** của nested JWT theo đúng chính sách. Việc giải mã thành công không mặc nhiên chứng minh bên gửi là issuer dự kiến khi mô hình khóa và profile không bảo đảm điều đó.

Bài học này tập trung vào **allowlist thuật toán ký/MAC của JWS** cho token xác thực/ủy quyền. Nếu triển khai JWE, cần **allowlist riêng cho cả `alg` và `enc`**.

## 3. Vì sao không được tin thuật toán do token tự chọn?

Resource server nhận token từ một nguồn có thể bị kẻ tấn công kiểm soát: HTTP header, cookie hoặc proxy. Nếu server suy luận “token nói `alg=X`, vậy hãy dùng thuật toán X” mà không đối chiếu policy, có thể xuất hiện:

1. **Unsecured token acceptance:** thư viện chấp nhận `alg=none` và bỏ qua chữ ký.
2. **Symmetric/asymmetric algorithm confusion:** cùng dữ liệu key bị dùng sai giữa HMAC và RSA/EC.
3. **Untrusted key selection:** token chỉ đến một khóa bên ngoài, không thuộc issuer được tin.
4. **Weak algorithm downgrade:** chấp nhận thuật toán cũ/yếu ngoài cam kết của authorization server.
5. **Token type/issuer confusion:** token từ issuer hoặc loại token khác được xác minh bằng chính sách chung quá rộng.

~~~mermaid
flowchart LR
    A["Bearer token do caller gửi"] --> B["Đọc protected header,\nchưa tin cậy"]
    B --> C{"alg trong allowlist\nđúng issuer/profile?"}
    C -->|Không| REJ["Từ chối token"]
    C -->|Có| D{"Chọn khóa từ\nissuer đã cấu hình;\nkhớp kty/use/alg?"}
    D -->|Không| REJ
    D -->|Có| E{"Xác minh JWS\nsignature/MAC"}
    E -->|Sai| REJ
    E -->|Đúng| F{"Validate iss, aud,\ntyp, exp, nbf,\nclaims & policy"}
    F -->|Sai| REJ
    F -->|Đúng| G["Xét scope và\nquyền tài nguyên"]
~~~

Điều kiện **`alg` thuộc allowlist** không có nghĩa token hợp lệ. Nó chỉ cho phép **bắt đầu kiểm tra chữ ký bằng phương thức đúng**. Chỉ sau khi chữ ký/MAC và claims đều được xác minh mới có căn cứ tin principal.

## 4. Lỗ hổng `alg=none`: bỏ qua bằng chứng mật mã

Một JWT JWS không bảo đảm chữ ký có thể dùng header:

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

Kẻ tấn công có thể sửa payload thành `"sub": "admin"`, `"scope": "payments.write"`, `"exp"` ở tương lai rồi gửi token không có chữ ký. Nếu một verifier được cấu hình sai và chấp nhận JWT unsecured, ứng dụng có thể tạo principal **từ dữ liệu tự khai**.

**Quy tắc phòng tránh cho OAuth access token và OIDC ID token cần xác thực nguồn:**

- **Không** đưa `none` vào allowlist.
- **Không** fallback sang parse unsigned JWT khi kiểm tra chữ ký thất bại.
- **Không** coi JWT chỉ có hai dấu chấm và payload đọc được là một credential hợp lệ.
- Sử dụng thư viện JOSE/OIDC đã được bảo trì, cấu hình chính xác issuer, thuật toán và khóa.

Chuẩn JOSE có mô tả JWT unsecured cho các **ngữ cảnh được thiết kế riêng**, nhưng điều đó **không cho phép** resource server mặc định tin `alg=none` trong các Bearer request bảo vệ API.

## 5. Algorithm confusion: nhầm HS256 với RS256

Đây là lỗi điển hình khi verifier cho phép quá nhiều thuật toán và dùng **cùng một biến key** theo cách phụ thuộc `alg` từ token.

### 5.1. Thiết kế đúng

AS:

~~~text
Authorization Server:
  signing algorithm = RS256
  signing key       = RSA PRIVATE key

Resource Server:
  accepted algorithm = RS256
  verification key   = RSA PUBLIC key của issuer tin cậy
~~~

API dùng public key để xác minh chữ ký RSA. Public key có thể được công bố ở JWKS mà **không làm lộ private key** của AS.

### 5.2. Thiết kế sai

Một verifier cấu hình giả định:

~~~text
accepted algorithms = [RS256, HS256]           (quá rộng)
verificationKey = sameKeyMaterialForEverything (sai thiết kế)

if token.header.alg == "RS256":
    verify_RSA(token, verificationKey)
else if token.header.alg == "HS256":
    verify_HMAC(token, verificationKey)
~~~

Nếu code cho phép dùng **public key RSA như một secret HMAC**, attacker có thể biết được dữ liệu public key và tạo MAC theo cách verifier sai đó; token giả có thể qua bước xác minh. **Đây là mô hình tấn công do triển khai sai**, không có nghĩa mọi thư viện hiện đại đều mắc lỗi.

Biện pháp:

1. Với issuer RS256, **chỉ chấp nhận RS256** hoặc tập thuật toán đã đàm phán/được phê duyệt rõ ràng.
2. Chỉ dùng **khóa RSA** cho các thuật toán RSA đã được chính sách cho phép; **không** tái sử dụng dữ liệu public key làm secret HMAC.
3. Ràng buộc một key với **một họ thuật toán và mục đích phù hợp**, kiểm tra kiểu khóa `kty`, `use`, `key_ops` và `alg` nếu có.
4. Nếu đổi thuật toán, thực hiện qua quy trình đổi cấu hình, kiểm thử và rollout, **không** dựa vào lựa chọn tùy ý của token.

**Đổi khóa không đồng nghĩa đổi thuật toán.** AS có thể rotate từ RSA key A sang RSA key B mà vẫn dùng RS256; `kid` thay đổi nhưng allowlist `RS256` không cần mở thêm `HS256`.

## 6. Chọn khóa từ JWKS phải ràng buộc issuer và algorithm

Resource server thường lấy public key từ **JWKS (*JSON Web Key Set*)** của issuer. JWKS có thể chứa nhiều khóa để hỗ trợ rotation.

Ví dụ JWKS giản lược (giá trị khóa chỉ là placeholder):

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "signing-key-2026-11",
      "alg": "RS256",
      "n": "<base64url-rsa-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Trong RSA JWK, `n` và `e` là các tham số public key; ví dụ **không đủ dữ liệu để xác minh chữ ký thật**. Cần JWKS được tải theo metadata/cấu hình **đúng issuer qua kênh HTTPS tin cậy**.

### 6.1. `kid` chỉ là gợi ý tìm khóa

Một JWS header có:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-11"
}
~~~

Quy trình đúng:

1. API biết trước **issuer tin cậy** và JWKS URI tương ứng từ cấu hình/discovery đã được kiểm soát.
2. Tìm candidate key với `kid` trong **JWKS của issuer đó**.
3. Kiểm tra key có kiểu, mục đích sử dụng và algorithm tương thích với chính sách.
4. Kiểm tra chữ ký RS256, sau đó kiểm tra `iss`, `aud`, `exp`, `typ` và các điều kiện còn lại.

**`kid` không phải credential, không phải một chứng chỉ tin cậy, và không được biến thành đường dẫn tùy ý để đọc file.** Nếu `kid` không tìm thấy hoặc có nhiều candidate mơ hồ, verifier phải xử lý an toàn; không chấp nhận token mà bỏ kiểm tra chữ ký.

### 6.2. Không tự động tin `jku` hoặc `x5u` từ token

Một header do attacker gửi có thể chứa URL trỏ tới JWKS/chứng chỉ do họ kiểm soát:

~~~json
{
  "alg": "RS256",
  "kid": "attacker-key",
  "jku": "https://attacker.example/jwks.json"
}
~~~

**Sai:** API tải khóa theo `jku` bất kỳ trong token, rồi kiểm tra chữ ký bằng khóa từ đó. Attacker có thể tự ký JWT và cung cấp public key tương ứng; ngoài giả mạo token, còn có nguy cơ **SSRF** nếu thư viện tự truy cập các URL nội bộ.

**Đúng:** lấy JWKS từ **địa chỉ của issuer đã được cấu hình trước**, không từ URL do caller kiểm soát. Nếu profile có cơ chế chọn khóa nâng cao, phải allowlist nguồn, kiểm soát redirect, TLS, caching và ranh giới tin cậy. Header `x5c` mang chuỗi chứng chỉ cũng không tự bảo đảm chứng chỉ đã được trust; cần kiểm tra theo policy PKI và gắn với issuer được phép.

### 6.3. Key rotation không nên buộc tắt kiểm tra algorithm

Khi AS thay khóa ký:

~~~text
Giai đoạn 1: JWKS có K1 (RS256); token mới dùng kid=K1
Giai đoạn 2: JWKS có K1 + K2 (đều RS256); token mới dùng kid=K2
Giai đoạn 3: token dùng K1 đã hết hạn; ngừng công bố K1 theo policy
~~~

API phải hỗ trợ JWKS refresh theo cache/TTL có kiểm soát và nhận khóa mới. **Đừng giải quyết “không thấy kid” bằng cách chấp nhận `alg=none`, bỏ chữ ký hoặc tải khóa tùy ý.**

Với nhiều issuer, dùng **mỗi issuer một trust configuration**. JWKS hoặc key ID trùng tên ở hai issuer khác nhau không làm chúng trở thành cùng một nguồn tin cậy.

## 7. Định nghĩa algorithm allowlist theo issuer, audience và loại token

Một hệ thống có thể chấp nhận nhiều JWT, nhưng không nên dùng một danh sách “mọi thuật toán thư viện hỗ trợ” cho tất cả request.

| Ngữ cảnh | Chính sách minh họa | Vì sao cần tách biệt? |
| --- | --- | --- |
| Access token cho Payments API từ AS nội bộ | `iss=https://auth.example.com`, `aud=payments-api`, JWS **RS256** | API chỉ tin đúng issuer và RSA signing keys được đăng ký |
| ID token OIDC cho web RP | `aud=web-client`, JWS **RS256** theo đăng ký client | RP xác minh login; API **không nhận ID token** |
| Access token từ IdP đối tác đã được phê duyệt | `iss=https://partner.example`, `aud=partner-api`, JWS **ES256** | Key type/algorithm của đối tác không mở rộng quyền cho AS nội bộ |
| Opaque access token | Không có JWS `alg` để client/API đọc | Kiểm tra qua introspection, TLS và metadata tin cậy |
| JWE cho dữ liệu cần bí mật | `alg`/ `enc` nằm trong allowlist JWE riêng | Mã hóa không đồng nhất với xác thực chữ ký |

**Đừng đoán issuer từ trường `iss` của JWT chưa được xác minh rồi mở kết nối tới issuer bất kỳ.** Với multi-issuer, chỉ định danh issuer **để chọn trong registry cố định các issuer đã tin**; sau đó xác minh chữ ký và so `iss` chính xác. Không thêm issuer mới động theo yêu cầu caller.

### 7.1. Token type confusion

ID token có thể do cùng issuer ký cùng thuật toán với access token. Nếu API chỉ kiểm tra “signature hợp lệ và `alg=RS256`” rồi chấp nhận, attacker có thể đưa **ID token** vào endpoint yêu cầu access token.

API cần:

- So **`aud`** đúng resource server, không phải `client_id` OIDC.
- Kiểm tra **token type/profile** phù hợp, ví dụ `typ=at+jwt` trong JWT access-token profile khi profile yêu cầu.
- So issuer, hạn, scope và claims hợp lệ; không ánh xạ email/role từ ID token thành access permission.

Tương tự, một **client assertion JWT** ký bằng RS256 để client authentication không tự là access token cho API, dù signature đúng. **Thuật toán hợp lệ chỉ là một trong nhiều điều kiện cần.**

## 8. Quy trình kiểm tra an toàn cho JWS

Quy trình tổng quát cho API nhận bearer JWT access token:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant API as Resource Server
    participant CFG as Trusted Issuer Config / JWKS
    participant DB as Authorization Policy / DB
    C->>API: GET /payments + Bearer JWT
    API->>API: Parse JOSE header, chưa tin payload
    API->>CFG: Lấy policy issuer/audience/profile đã cấu hình
    CFG-->>API: Allowed alg=RS256, trusted JWKS
    API->>API: Reject alg ngoài allowlist
    API->>API: Chọn RSA signing key tương thích (kid)
    API->>API: Verify JWS signature
    API->>API: Validate iss, aud, typ, exp, nbf, claims
    API->>DB: Check scope, tenant, ownership, resource policy
    DB-->>API: Allow / deny
    API-->>C: Data hoặc 401/403 theo policy
~~~

Thứ tự triển khai có thể thay đổi đôi chút tùy thư viện, nhưng phải giữ hai nguyên tắc:

1. **Không sinh principal/authority đáng tin từ token trước khi kiểm tra crypto và claims đầy đủ.**
2. **Không sử dụng header do caller cung cấp để mở rộng algorithm/key policy đã cấu hình.**

### 8.1. Các kiểm tra cần phối hợp

| Nhóm kiểm tra | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| **Algorithm policy** | `alg` có thuộc tập cho phép? | HS256 trong hệ thống chỉ nhận RS256 |
| **Key compatibility** | `kty`, key usage, key material đúng algorithm? | Dùng RSA public key như HMAC secret |
| **Signature/MAC** | Token có thực sự được tạo bằng khóa tin cậy? | Payload bị sửa nhưng vẫn được decode |
| **Issuer** | `iss` có đúng AS/OP đã cấu hình? | Token của môi trường staging dùng ở production |
| **Audience** | `aud` có chứa đúng API không? | Token của Profile API gửi sang Payments API |
| **Type/profile** | Đây là JWT access token hay ID token/client assertion? | ID token được dùng gọi resource API |
| **Time** | `nbf`, `exp`, `iat` hợp lệ theo profile? | Token quá hạn hoặc chưa đến lúc dùng |
| **Scope/authorization** | Có quyền thao tác trên tài nguyên này? | Có `payments.read` nhưng sửa payment |
| **Revocation** | Token/grant có còn hợp lệ theo thiết kế? | JWT còn hạn nhưng quyền đã bị thu hồi |

Không đổi bài toán “algorithm allowlist” thành việc tự viết thuật toán mật mã bằng tay. Nên dùng thư viện JOSE/JWT trưởng thành với cấu hình **explicit allowlist**, kiểm soát issuer/JWKS và những validator đặc thù của API.

## 9. Java/Spring Security: pin RS256 cho JWT resource server

Giả sử Payments API:

- Chỉ chấp nhận JWT access token của `https://auth.example.com`.
- Chỉ chấp nhận **RS256** tại JWS layer.
- Yêu cầu `aud` bao gồm `https://api.example.com/payments`.
- Sau khi xác thực token, endpoint kiểm tra `SCOPE_payments.read` hoặc `SCOPE_payments.write`.

Ví dụ Java với Spring Security Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class PaymentsJwtDecoderConfig {
    private static final String ISSUER = "https://auth.example.com";
    private static final String JWKS_URI =
        "https://auth.example.com/.well-known/jwks.json";
    private static final String AUDIENCE =
        "https://api.example.com/payments";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            // Cấu hình danh sách thuật toán tin cậy ngay tại verifier.
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience() != null &&
                    jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "Unexpected audience", null)
            );
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audienceValidator
        ));
        return decoder;
    }
}
~~~

**Điểm quan trọng:** `.jwsAlgorithm(SignatureAlgorithm.RS256)` là cấu hình verifier cho phép RS256 trong ví dụ. **Không** đọc `alg` từ JWT rồi truyền trực tiếp vào phương thức cấu hình decoder. JWKS URI cũng là cấu hình tin cậy, **không** lấy từ `jku` trong token.

Các yêu cầu chưa thể hiện hết trong snippet:

- Cần xác minh **token type/profile**, ví dụ JWT access token theo RFC 9068 với `typ=at+jwt` hoặc `application/at+jwt`, theo hành vi thư viện/phiên bản đang dùng.
- Cần quản lý được key rotation, thời hạn/thu hồi, claims bắt buộc, scope và tenant context nếu API sử dụng.
- Cần xác định rõ **thuật toán được thư viện cho phép mặc định** để tránh tạo thêm một đường xác minh ngoài policy; ví dụ dùng cấu hình RS256 tường minh thay vì tin “alg bất kỳ trong JWKS”.
- Nếu API chấp nhận nhiều issuer, cấu hình **decoder/validator riêng cho từng issuer đã đăng ký** và chọn đúng theo trust registry.

**Đoạn code định nghĩa bean `JwtDecoder` cụ thể.** Nếu dự án cũng cấu hình `issuer-uri` tự động, phải hiểu bean tự định nghĩa có thể thay thế cấu hình decoder mặc định của Spring Boot; luôn kiểm thử toàn bộ validators được kích hoạt.

### 9.1. SecurityFilterChain và quyền tại API

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PaymentsApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/payments/**")
                    .hasAuthority("SCOPE_payments.read")
                .requestMatchers(HttpMethod.POST, "/api/payments/**")
                    .hasAuthority("SCOPE_payments.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> {}))
            .build();
    }
}
~~~

Spring Security có thể ánh xạ scope JWT đáng tin sang `SCOPE_` authorities. **Đừng dùng `hasRole("payments.read")` để thay `hasAuthority("SCOPE_payments.read")`**: `hasRole` thường tìm tiền tố `ROLE_`, không phải `SCOPE_`. Với endpoint POST, cấu hình CSRF còn phụ thuộc kiến trúc: API thuần Bearer không dùng cookie được xét khác với web app có session/cookie. **Không tắt CSRF theo thói quen** mà phải đánh giá nguồn credential và đường request.

Ngay cả khi `SCOPE_payments.write` có mặt, service vẫn phải kiểm tra **quyền sở hữu payment, tenant, trạng thái giao dịch và policy nghiệp vụ**. Algorithm đúng không làm mọi record trở nên có thể sửa.

## 10. Nếu hệ thống dùng HS256 thì kiểm tra thế nào?

HMAC không tự xấu. Nhưng nếu dùng HS256, secret phải đủ entropy, lưu trữ an toàn, phạm vi chia sẻ rõ và **không được lẫn với khóa công khai RSA**. Ví dụ một hệ thống internal với một issuer và một verifier được cấu hình secret từ kho bảo mật:

~~~java
import javax.crypto.SecretKey;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public JwtDecoder hs256Decoder(SecretKey trustedSecretKey) {
    return NimbusJwtDecoder.withSecretKey(trustedSecretKey)
        .macAlgorithm(MacAlgorithm.HS256)
        .build();
}
~~~

Lưu ý:

- `trustedSecretKey` phải đến từ **secret manager hoặc cấu hình bảo mật**, không đọc từ JWT, query parameter hoặc người dùng.
- Cần thêm validator issuer, audience, thời gian và token type theo profile, tương tự JWT bất đối xứng; snippet chỉ minh họa pin thuật toán HMAC.
- Không nhúng shared secret vào SPA, app mobile hoặc ứng dụng được phát cho người dùng.
- Nếu nhiều API chia sẻ cùng HS256 secret, thỏa hiệp một API có thể ảnh hưởng quyền **phát token giả** cho API khác. Cân nhắc chữ ký bất đối xứng để giảm chia sẻ khả năng ký.

**Đừng cho cùng một decoder thử HS256 rồi tự động fallback RS256** chỉ vì token báo thuật toán. Nếu thật sự phải chuyển đổi thuật toán, dùng policy migration cụ thể, key binding rõ ràng và kiểm thử âm cho từng trạng thái.

## 11. Allowed algorithms khi có nhiều issuer và migration

### 11.1. Một issuer, nhiều thuật toán: khi nào được?

Đôi khi AS cần chuyển từ RS256 sang ES256 hoặc PS256. Để tránh gián đoạn, resource server có thể tạm chấp nhận **tập thuật toán được phê duyệt**, nhưng mỗi thuật toán phải đi với key type/keys tương ứng và có thời hạn chuyển đổi.

Một kế hoạch hợp lý:

1. **Đăng ký policy mới**: issuer, profile, audiences, key sets, thuật toán cũ/mới, thời gian hỗ trợ.
2. **Triển khai verifier có allowlist mới** qua cấu hình kiểm soát; không thay đổi trực tiếp theo JWT đến.
3. **Phát token mới với khóa/algorithm mới**, tiếp tục xác minh token cũ trong khoảng TTL được công bố.
4. **Giám sát các algorithm và `kid` đang được sử dụng**, không log token.
5. **Thu hẹp allowlist** khi token cũ đã hết hạn và các client/AS hoàn tất migration.

Việc chấp nhận hai thuật toán không tự là lỗ hổng nếu thực hiện đúng **algorithm–key binding**, nhưng làm tăng bề mặt cấu hình và phạm vi cần kiểm thử. Không kéo dài cửa sổ migration vô thời hạn.

### 11.2. Multi-tenant, issuer federation

Một SaaS có thể tin issuer Acme dùng RS256 và issuer Globex dùng ES256. Registry phải xác định rõ:

| Issuer tin cậy | Algorithm JWS | JWKS/key source | API audience |
| --- | --- | --- | --- |
| `https://login.acme.example` | `RS256` | JWKS đã cấu hình cho Acme | `invoice-api` |
| `https://login.globex.example` | `ES256` | JWKS đã cấu hình cho Globex | `invoice-api` |

API không được “thử mọi issuer cho đến khi có cái verify thành công” mà quên kiểm tra `iss` và tenant mapping. Cần bảo đảm external identity được ánh xạ sang đúng tenant nội bộ và quyền thực tế; `kid` giống nhau giữa hai issuer **không** tạo ra cùng một trust domain.

### 11.3. API gateway và microservice kiểm tra thuật toán

Một gateway có thể xác minh token và truyền thông tin danh tính xuống service. Tuy nhiên:

- Nếu service nhận Bearer token trực tiếp, nó phải kiểm tra token theo policy hoặc có trust boundary mạnh với gateway.
- Nếu gateway truyền user/role qua header như `X-User-Id`, service phải bảo đảm header đó không thể bị client ngoài giả mạo; cần cách ly mạng, loại bỏ header do client gửi, kênh tin cậy/mTLS và quyền truy cập phù hợp.
- Nếu service tự xác minh token, issuer/algorithm/audience policy phải đồng bộ qua cơ chế cấu hình an toàn.
- Không dùng “gateway đã kiểm tra `alg`” làm lý do bỏ object-level authorization trong service.

**Chữ ký hợp lệ ở gateway không tự cấp quyền trên mọi tài nguyên downstream.**

## 12. Thuật toán, kích thước token và vòng đời

Lựa chọn algorithm có ảnh hưởng đến kích thước chữ ký, CPU và quản trị khóa:

| JWS algorithm | Độ dài chữ ký điển hình ở dạng nhị phân | Hệ quả thực tế |
| --- | ---: | --- |
| HS256 | 32 byte | JWT ngắn, nhưng secret đối xứng phải được chia sẻ an toàn |
| ES256 | 64 byte theo JOSE signature format | JWT ngắn hơn RSA 2048-bit, cần triển khai EC đúng |
| RS256 với RSA 2048-bit | 256 byte | Public/private key tách biệt, chữ ký dài hơn |
| PS256 với RSA 2048-bit | 256 byte | RSA-PSS, khác RS256 dù có thể dùng cùng cỡ khóa |
| EdDSA Ed25519 | 64 byte | Yêu cầu key type và hỗ trợ thuật toán phù hợp |

**Không đánh đổi thuật toán an toàn để tiết kiệm vài trăm byte.** Nếu JWT quá dài, hãy giảm claims `groups`/`roles`/profile không cần thiết, dùng scope/audience phù hợp hoặc cân nhắc opaque token + introspection/BFF. Giới hạn HTTP header do CDN/gateway áp dụng vẫn có thể từ chối token hợp lệ.

### 12.1. Thu hồi khóa ký và token

Nếu private signing key bị lộ:

- Vô hiệu hóa/rotate khóa ở issuer và JWKS theo quy trình ứng phó sự cố.
- Bảo đảm resource server cập nhật trust store/cache kịp thời; có chiến lược từ chối token ký bởi khóa bị thu hồi.
- Cân nhắc thu hồi hoặc giảm giá trị token/grant đã phát nếu có rủi ro giả mạo; đánh giá hậu quả trên audience/scope.
- Giám sát bất thường theo `kid`, issuer và phương thức ký, **không** lưu JWT nguyên vẹn trong log.

**Rút một key khỏi JWKS không phải lúc nào cũng khiến mọi verifier ngừng tin ngay** vì có thể tồn tại cache. Cần quy trình rotation/revocation đáp ứng yêu cầu thời gian của hệ thống.

### 12.2. Algorithm allowlist không chống token bị đánh cắp

Một token RS256 hợp lệ có thể bị đánh cắp và được gửi lại như Bearer token trong thời hạn còn hiệu lực; chữ ký vẫn đúng. Algorithm allowlist giúp chống **token giả được tạo bằng phương thức trái phép**, nhưng không trực tiếp chống **replay credential đã phát thật**.

Cần thêm:

- HTTPS, không đưa token vào URL/log/analytics, giữ token ở kho phù hợp.
- Token hạn ngắn, scope/audience tối thiểu, thu hồi khi cần.
- Bảo vệ XSS/CSRF phù hợp với browser, cookie và mô hình BFF.
- Cân nhắc **sender-constrained token** qua DPoP hoặc mTLS khi phù hợp.
- Theo dõi hành vi bất thường và cấp lại credential khi bị lộ.

## 13. Phân biệt lỗi thuật toán với các lỗi token khác

| Tình huống | Kết quả | Phản hồi HTTP thường gặp |
| --- | --- | --- |
| `alg=none`, API chỉ chấp nhận RS256 | Không thuộc allowlist, từ chối | `401 Unauthorized`, `invalid_token` nếu dùng Bearer challenge |
| `alg=HS256`, policy RS256 | Không đúng thuật toán | `401` |
| `alg=RS256`, chữ ký không hợp lệ | Không xác minh được crypto | `401` |
| `alg=RS256`, `kid` không nằm trong JWKS tin cậy | Không có khóa phù hợp | `401` |
| Signature đúng nhưng sai `iss` | Sai issuer | `401` |
| Signature đúng nhưng `aud` là API khác | Sai audience | `401` |
| Signature đúng nhưng đã quá `exp` | Token hết hạn | `401` |
| Signature đúng nhưng thiếu scope | Thiếu quyền được cấp | Thường `403 Forbidden` / `insufficient_scope` |
| Signature đúng, scope đủ nhưng record thuộc user/tenant khác | Thiếu object-level authorization | `403` hoặc `404` theo policy |
| Opaque token được đưa vào JWT decoder | Sai cơ chế xử lý/định dạng | Từ chối; không tự decode |

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

**Không trả chi tiết nhạy cảm** như key ID nội bộ, raw token, JWKS cache state hoặc quy tắc xác minh quá chi tiết cho caller chưa được tin. Ở log server, ghi mã lỗi chuẩn hóa như `alg_not_allowed`, `unknown_kid`, `invalid_signature`, `wrong_audience` để chẩn đoán, nhưng không log JWT nguyên vẹn.

## 14. Bộ kiểm thử bắt buộc

Giả sử API chỉ cho phép RS256 từ issuer A, audience Payments API. Có thể tổ chức test:

| Test case | Kỳ vọng |
| --- | --- |
| JWT RS256 do issuer A ký bằng key tin cậy, claims đúng | Xác minh thành công, tiếp tục policy |
| JWT có `alg=none`, payload giả `sub=admin` | Từ chối |
| JWT có `alg=HS256` dùng dữ liệu public key RSA như secret | Từ chối từ allowlist/key binding |
| JWT có `alg=ES256` nhưng policy RS256 | Từ chối |
| JWT có `alg=PS256` dù RSA key giống issuer | Từ chối nếu PS256 không được cấu hình |
| JWT RS256 đã sửa payload mà không ký lại hợp lệ | Từ chối chữ ký |
| JWT RS256 ký bằng private key của attacker | Từ chối do key không thuộc issuer |
| JWT có `jku` trỏ domain của attacker | Không tải khóa từ URL tùy ý; từ chối |
| JWT có `kid` chứa chuỗi path, URL hoặc ký tự bất thường | Không đọc file/SSRF; không tạo key trust từ input |
| JWT có `kid` lạ sau rotation | Từ chối an toàn, JWKS refresh có giới hạn |
| JWT từ issuer B nhưng ký bằng thuật toán cũng là RS256 | Từ chối nếu issuer B không được trust cho API |
| ID token OIDC cùng issuer, cùng alg nhưng sai audience/type | Từ chối tại resource API |
| JWT access token hết hạn hoặc chưa đến `nbf` | Từ chối |
| JWT có `crit` yêu cầu extension không được hỗ trợ | Từ chối |
| Token malformed, nhiều/mất dấu chấm, header sai JSON | Từ chối an toàn, không gây crash |
| Access token opaque với introspection `active=false` | Từ chối; không cố đoán `alg` |
| Signature và claims đúng, nhưng thiếu scope | Không qua authorization |
| Scope đủ nhưng thiếu quyền trên tài nguyên tenant khác | Không trả dữ liệu |

### 14.1. Integration test quan trọng hơn chỉ mock authorities

Một test Spring Security dùng `jwt()` hoặc mock `Authentication` có thể **bỏ qua decoder và chữ ký thật**, chỉ kiểm tra `hasAuthority`. Điều đó **không chứng minh algorithm allowlist hoạt động**.

Nên kiểm thử hai tầng:

1. **Decoder integration tests:** tạo token test bằng khóa test riêng với các `alg`, `kid`, issuer/audience/time khác nhau; kiểm tra decoder từ chối những gì ngoài policy.
2. **API authorization tests:** với token đã được xác minh, kiểm tra scope, tenant, ownership, trạng thái đối tượng và quyền theo endpoint.

Ví dụ pseudocode của bộ test:

~~~java
// Pseudocode: dùng khóa thử nghiệm và JwtDecoder production-configured.
assertDoesNotThrow(() -> decoder.decode(validRs256AccessToken));

assertThrows(
    JwtException.class,
    () -> decoder.decode(unsignedAlgNoneToken)
);
assertThrows(
    JwtException.class,
    () -> decoder.decode(hs256TokenSignedWithAttackerMaterial)
);
assertThrows(
    JwtException.class,
    () -> decoder.decode(rs256TokenWithUntrustedKey)
);
assertThrows(
    JwtException.class,
    () -> decoder.decode(rs256TokenForOtherAudience)
);
~~~

`JwtException`, `decoder` và các token test ở đây mang tính minh họa; kiểm thử thực tế cần import/libraries, fixture và cấu hình JOSE key tương ứng. **Không đưa private key test vào môi trường production**.

### 14.2. Giám sát algorithm mismatch

Các metric/log gợi ý:

- Số request bị từ chối theo nhóm: algorithm không cho phép, signature sai, key không tìm thấy, issuer/audience không hợp lệ.
- Tỷ lệ xuất hiện `kid` cũ/mới khi rotation, nhưng không ghi nguyên credential.
- Mức độ tăng bất thường của `alg=none` hoặc token malformed có thể là tín hiệu quét lỗ hổng.
- Độ trễ và lỗi refresh JWKS, số lần request JWKS thất bại, nguy cơ rate/DoS.

Nên giới hạn kích thước JWT/header, kiểm soát JSON parser và caching để tránh tấn công tiêu tốn tài nguyên. Không refresh JWKS vô hạn mỗi lần gặp `kid` ngẫu nhiên do attacker tạo.

## 15. Các ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Header JWT nói RS256 thì đó là bằng chứng RSA.” | Header do caller gửi | Chỉ tin sau khi xác minh bằng key và allowlist |
| “Mọi thuật toán do thư viện hỗ trợ đều được phép.” | Khả năng thư viện không phải chính sách issuer/API | Pin thuật toán theo trust contract |
| “`alg=none` là JWT hợp lệ nên API phải nhận.” | JWT unsecured không chứng minh nguồn ký | Từ chối trong bearer authentication |
| “Cho cả RS256 và HS256 càng tương thích.” | Có thể tạo algorithm confusion nếu key handling sai | Chỉ cấp quyền cho thuật toán thật sự đăng ký và ràng buộc khóa |
| “`kid` giống nhau nghĩa là cùng khóa đáng tin.” | `kid` chỉ định danh trong key set | Gắn khóa với issuer, JWKS và algorithm |
| “`jku` ở header là nơi phải tải khóa.” | Attacker có thể điều khiển URL/SSRF | JWKS URI từ trusted configuration |
| “Đã verify signature thì khỏi kiểm tra `aud`.” | Token có thể dành cho API khác | Kiểm tra audience và token type |
| “ID token và access token cùng RS256 nên thay thế được.” | Mục đích và audience khác nhau | OIDC client xác minh ID token; API nhận access token |
| “Đổi từ RS256 sang ES256 chỉ cần để client tự chọn.” | Trust policy và key type phải thay đổi đồng bộ | Triển khai migration được kiểm soát |
| “Algorithm allowlist chống replay bearer token.” | Token thật bị đánh cắp vẫn có chữ ký hợp lệ | Kết hợp TTL, bảo vệ lưu trữ, sender constraint và revocation |
| “Opaque token không có `alg` nên khỏi validation.” | Opaque token vẫn là credential có nguy cơ giả/replay | Introspection/lookup, audience, scope và chính sách |

## 16. Checklist cho triển khai production

1. **Xác định trust contract:** issuer nào, token type nào, audience nào, algorithm nào được cấp phép.
2. **Chọn allowlist tối thiểu:** không cho `none`; không bật nhiều thuật toán chỉ để “thử cho chạy”.
3. **Ràng buộc algorithm–key:** HMAC chỉ dùng secret có entropy phù hợp, RSA/EC/OKP dùng đúng key type, key usage và profile.
4. **Cố định JWKS source:** lấy từ issuer tin cậy, bảo vệ TLS/cache/rotation; không tin `jku`, `x5u`, `kid` như nguồn quyền tự thân.
5. **Xác minh signature/MAC:** không fallback parse unsigned JWT hoặc tạo principal từ payload chưa verified.
6. **Chống token substitution:** issuer, audience, `typ`/profile, mục đích ID/access/client assertion phải phù hợp.
7. **Kiểm tra thời gian:** `exp`, `nbf`, `iat` theo profile và clock skew có giới hạn.
8. **Áp dụng authorization:** scope, tenant, principal type, membership và ownership; thuật toán đúng không tự cấp quyền.
9. **Quản lý credential:** key rotation, revoke khi lộ khóa, bảo vệ refresh/access token, hạn ngắn và logging an toàn.
10. **Kiểm thử âm:** `none`, HS/RS confusion, thuật toán khác không cho phép, key của attacker, `kid` lạ, `jku` ngoài trust, token sai aud/iss.
11. **Giám sát:** reject reasons, JWKS cache/refresh, số token malformed, thay đổi thuật toán bất thường.
12. **Kiểm tra cấu hình thực chạy:** xác minh decoder nào được inject, validator nào đang kích hoạt, gateway và service có cùng trust policy.

## 17. Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected headers, `alg`, `kid`, `crit` và xác minh chữ ký JWS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): định nghĩa HS256, RS256, PS256, ES256, các thuật toán JOSE và yêu cầu khóa.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWKS, `kty`, `use`, `key_ops`, `kid` và key parameters.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): token claims, xử lý JWT và unsecured JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): validate thuật toán, chống cross-JWT confusion, yêu cầu ràng buộc khóa với thuật toán và issuer.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token JWT, `typ`, issuer, audience và validation.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): `alg`/ `enc` cho mã hóa và nested JWT.
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037): EdDSA/OKP JOSE trong những hệ thống có hỗ trợ.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh opaque token qua AS.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): giới hạn quyền, bảo vệ bearer/refresh token và giảm nguy cơ OAuth.
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình decoder, trusted algorithms, validators và `JwtAuthenticationToken`.

**Ghi nhớ:** `alg` trong JOSE header là **dữ liệu cần đối chiếu**, không phải lệnh cho phép API đổi chính sách mật mã. **Chỉ cho phép thuật toán đã cấu hình cho đúng issuer/token profile, chỉ dùng khóa phù hợp từ nguồn tin cậy, rồi xác minh chữ ký và các claims trước khi cấp quyền.** Việc chặn `alg=none`, algorithm confusion và key injection là nền tảng; sau đó vẫn cần audience, scope, tenant, thời hạn, revocation và phòng chống replay cho vòng đời token hoàn chỉnh.
