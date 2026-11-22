# Kiểm tra jwks, jwks_uri và thuật toán do client khai báo

## 1. Bối cảnh và mục tiêu

Trong hệ thống **OAuth 2.0/OpenID Connect Authorization Server** dùng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, Dynamic Client Registration (DCR) cho phép một ứng dụng đăng ký với OpenID Provider (OP) bằng request chứa metadata thay vì phải tạo từng client thủ công. Metadata có thể chứa redirect URI, grant type, cách xác thực client, địa chỉ JWK Set và các thuật toán JOSE mà client muốn sử dụng.

Một số metadata có ảnh hưởng trực tiếp đến ranh giới tin cậy:

- `jwks_uri` trỏ tới public JWK Set do client quản lý.
- `jwks` nhúng JWK Set trực tiếp vào registration request.
- `token_endpoint_auth_signing_alg` khai báo thuật toán client dùng để ký JWT xác thực tại Token Endpoint.
- `request_object_signing_alg` khai báo thuật toán client dùng để ký Request Object gửi tới OP.
- `id_token_signed_response_alg` yêu cầu OP ký ID Token cho client bằng thuật toán cụ thể.
- Các trường JWE khai báo cách mã hóa ID Token hoặc UserInfo response cho client.

Nếu OP chỉ kiểm tra JSON hợp lệ rồi lưu metadata, một client có thể đăng ký URL trỏ vào mạng nội bộ, đưa public key không tương thích thuật toán, khai báo thuật toán yếu hoặc tạo một cấu hình không thể vận hành. Đặc biệt, khi OP tải `jwks_uri` do client cung cấp để xác minh `private_key_jwt` hoặc Request Object, một URL không đáng tin có thể trở thành đường SSRF từ Authorization Server.

Ví dụ xuyên suốt: một đối tác đăng ký client `partner-service` và muốn dùng `private_key_jwt`. Đối tác khai báo `jwks_uri=https://partner.example.com/.well-known/jwks.json`, `token_endpoint_auth_signing_alg=PS256` và `request_object_signing_alg=ES256`. OP cần xác nhận endpoint công khai an toàn, JWK Set chỉ chứa public key phù hợp, có key tương thích PS256 và ES256, đồng thời không nhầm các thuật toán client ký với thuật toán OP dùng để ký ID Token.

Sau bài học, bạn có thể:

1. Phân biệt `jwks_uri` và `jwks` theo OIDC Dynamic Client Registration.
2. Xác định ai sử dụng từng key và thuật toán trong JWK Set của client.
3. Kiểm tra HTTPS, SSRF, DNS rebinding, redirect và giới hạn khi tải JWKS từ xa.
4. Kiểm tra public JWK, key type, curve, key use, key operations, `alg`, `kid` và certificate chain.
5. Phân biệt JWS signing algorithm với JWE key-management/content-encryption algorithm.
6. Kiểm tra thuật toán theo `token_endpoint_auth_method`, Request Object và ID Token response.
7. Cấu hình validator của Spring Authorization Server 1.5.x để giữ các kiểm tra mặc định và bổ sung allow-list.
8. Lưu metadata vào `RegisteredClient` và kiểm tra khả năng đọc lại cấu hình.
9. Kiểm thử rotation, key mismatch, endpoint lỗi và registration request không an toàn.

**Phạm vi phiên bản:** Ví dụ dùng Spring Authorization Server **1.5.8**, Spring Security **6.x** và Servlet stack. API DCR được minh họa bằng `OidcClientRegistrationAuthenticationProvider`, `OidcClientRegistrationAuthenticationValidator`, `OidcClientRegistration` và `RegisteredClient.ClientSettings`. DCR bị tắt mặc định; chỉ bật khi hệ thống có chính sách cấp quyền đăng ký phù hợp.

## 2. JWK Set của client dùng để làm gì?

### 2.1. Client có thể sở hữu nhiều cặp khóa

Một OIDC client có thể giữ private key trong HSM, keystore hoặc KMS. OP chỉ cần public key để xác minh chữ ký client hoặc mã hóa response gửi tới client. Client công bố public keys bằng JSON Web Key Set (JWKS).

Một JWKS có cấu trúc:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "PS256",
      "kid": "partner-auth-2026-01",
      "n": "base64url-rsa-modulus",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "use": "enc",
      "alg": "ECDH-ES+A256KW",
      "kid": "partner-encryption-2026-01",
      "crv": "P-256",
      "x": "base64url-x-coordinate",
      "y": "base64url-y-coordinate"
    }
  ]
}
~~~

Các giá trị khóa trong ví dụ là placeholder, không phải key material có thể sử dụng. Key RSA đầu tiên dùng để xác minh chữ ký client; key EC thứ hai dùng cho mục đích mã hóa response nếu OP hỗ trợ thuật toán tương ứng.

### 2.2. Hướng sử dụng key

| Nhu cầu | Ai ký/mã hóa? | OP dùng key nào? |
| --- | --- | --- |
| `private_key_jwt` tại Token Endpoint | Client ký JWT assertion bằng private key của client. | OP dùng public key trong JWKS của client để xác minh. |
| Signed Request Object | Client ký Request Object bằng private key của client. | OP dùng public signing key của client để xác minh. |
| Encrypted ID Token | OP mã hóa ID Token cho client. | OP dùng public encryption key trong JWKS của client. |
| Encrypted UserInfo response | OP mã hóa UserInfo response cho client. | OP dùng public encryption key trong JWKS của client. |
| ID Token JWS signature | OP ký ID Token bằng private key của OP. | Client lấy public key từ **JWKS của OP**, không phải JWKS của client. |

Phân biệt cuối bảng đặc biệt quan trọng: `jwks_uri` trong registration request là địa chỉ key của **client**. Nó không phải `jwks_uri` của Authorization Server trong OpenID Provider Discovery. Hai bên có thể đều công bố JWKS nhưng mỗi JWKS phục vụ một hướng tin cậy khác nhau.

### 2.3. Không phải client nào cũng cần JWKS

`jwks_uri` thường cần khi client sử dụng cơ chế ký bất đối xứng, chẳng hạn `private_key_jwt` hoặc Request Object có chữ ký. Một client chỉ dùng `client_secret_basic` không cần public signing key cho client authentication. `client_secret_jwt` dùng shared secret để ký MAC nên không lấy key từ JWKS.

Nếu client yêu cầu OP mã hóa ID Token/UserInfo bằng public key của client, OP cần có encryption key phù hợp, bất kể client dùng phương thức nào tại Token Endpoint.

Không yêu cầu mọi client phải gửi JWKS. Hãy kiểm tra metadata và tính năng client đã chọn để xác định key material thực sự cần thiết.

## 3. jwks_uri và jwks khác nhau thế nào?

### 3.1. jwks_uri — tham chiếu tới JWKS từ xa

Ví dụ registration metadata:

~~~json
{
  "client_name": "Partner Service",
  "redirect_uris": [
    "https://partner.example.com/oidc/callback"
  ],
  "token_endpoint_auth_method": "private_key_jwt",
  "token_endpoint_auth_signing_alg": "PS256",
  "jwks_uri": "https://partner.example.com/.well-known/jwks.json"
}
~~~

OP lưu URL và có thể tải JWKS khi cần xác minh JWT hoặc mã hóa response. Ưu điểm:

- Client có thể rotation key mà không cần đăng ký lại client chỉ để thay JWKS.
- OP có thể lấy key mới theo cache/revalidation policy.
- Registration request nhỏ, không phải truyền toàn bộ public key set.

OIDC Dynamic Client Registration quy định URL `jwks_uri` **MUST use the HTTPS scheme**. TLS phải xác minh đúng hostname và certificate chain; không chấp nhận HTTP thường cho public deployment.

### 3.2. jwks — truyền JWKS trực tiếp trong request

Ví dụ:

~~~json
{
  "client_name": "Native Partner",
  "redirect_uris": [
    "com.example.partner:/oauth2redirect"
  ],
  "token_endpoint_auth_method": "private_key_jwt",
  "token_endpoint_auth_signing_alg": "RS256",
  "jwks": {
    "keys": [
      {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "native-client-key-01",
        "n": "base64url-rsa-modulus",
        "e": "AQAB"
      }
    ]
  }
}
~~~

JWKS được gửi **by value** và được lưu như một phần metadata client. Cách này có thể hữu ích cho client không có nơi host một JWKS URL. Tuy nhiên:

- OP không tự nhận được key mới khi client rotation.
- Muốn thay key phải cập nhật registration qua Client Configuration Endpoint hoặc quy trình quản trị.
- Dữ liệu lớn hơn và cần giới hạn kích thước request.
- OP phải lưu trữ và version hóa key set theo client.

### 3.3. Hai trường loại trừ lẫn nhau

Theo OIDC Dynamic Client Registration 1.0:

- `jwks_uri` và `jwks` **MUST NOT** cùng xuất hiện trong một request/registration.
- Nếu client có thể sử dụng `jwks_uri`, client **MUST NOT** dùng `jwks`.
- JWKS không được chứa private key hoặc symmetric key values.

Không chọn ngẫu nhiên một trường khi cả hai cùng có. Hãy từ chối registration với lỗi metadata phù hợp và yêu cầu client gửi lại đúng một cơ chế.

### 3.4. Hỗ trợ của Spring Authorization Server 1.5.8

Trong API chuẩn của Spring Authorization Server 1.5.8:

- `OidcClientRegistration.Builder.jwkSetUrl(...)` đại diện cho metadata `jwks_uri`.
- `OidcClientMetadataClaimAccessor.getJwkSetUrl()` cung cấp URL JWKS.
- `RegisteredClient.ClientSettings.Builder.jwkSetUrl(...)` lưu URL trong client settings.
- Builder công khai không có method chuyên biệt `jwks(...)` để lưu một JWK Set inline.

Vì vậy, khi dùng mapping mặc định, hãy ưu tiên `jwks_uri`. Nếu sản phẩm bắt buộc hỗ trợ `jwks` inline, cần custom request converter/metadata converter và nơi lưu trữ có cấu trúc cho JWK Set; phải thiết kế cập nhật, rotation, read response và bảo vệ key riêng. Không giả định trường JSON lạ sẽ tự động được chuyển thành `ClientSettings.jwkSetUrl`.

## 4. Kiểm tra cấu trúc và nội dung JWK Set

### 4.1. Kiểm tra JSON envelope

JWKS phải là JSON object có thuộc tính `keys` là array các JWK. Kiểm tra:

- Body không rỗng và là JSON hợp lệ.
- `keys` tồn tại, đúng kiểu array và có số lượng nằm trong giới hạn.
- Mỗi phần tử là JSON object có `kty` hợp lệ.
- Không có key trùng lặp gây mơ hồ khi lựa chọn.
- Tổng kích thước response, số lượng key và kích thước từng trường nằm trong giới hạn.
- Không chấp nhận duplicate JSON members hoặc payload bị parser xử lý không nhất quán.

Ví dụ response sai:

~~~json
{
  "keys": "not-an-array"
}
~~~

Hoặc một JWK thiếu `kty`:

~~~json
{
  "keys": [
    {
      "kid": "key-01",
      "alg": "RS256"
    }
  ]
}
~~~

`kty` là thành phần REQUIRED của JWK theo RFC 7517. Không suy ra key type chỉ từ tên thuật toán.

### 4.2. Không nhận private hoặc symmetric key values

OIDC Dynamic Client Registration yêu cầu JWK Set của client không chứa private hoặc symmetric key values. Một số trường cần phát hiện:

| Key type | Trường private/sensitive cần loại |
| --- | --- |
| RSA | `d`, `p`, `q`, `dp`, `dq`, `qi`, `oth` |
| EC | `d` |
| OKP | `d` |
| oct | `k` (symmetric key material) |

Public RSA JWK thường có `n` và `e`; public EC JWK có `crv`, `x`, `y`; public OKP JWK có `crv` và `x`. Không đưa private parameter vào registration response, database log, exception hoặc audit event.

Nếu phát hiện private/symmetric key material, từ chối registration và xử lý như sự kiện dữ liệu nhạy cảm: không log nguyên request, giới hạn quyền truy cập log và thông báo client cần thay key.

### 4.3. Kiểm tra use và key_ops

`use` mô tả mục đích public key:

- `sig`: xác minh chữ ký.
- `enc`: mã hóa hoặc key agreement.

`key_ops` mô tả thao tác cụ thể, ví dụ `verify`, `encrypt` hoặc `wrapKey`. RFC 7517 khuyến nghị không dùng đồng thời `use` và `key_ops`; nếu có cả hai, chúng **MUST** nhất quán.

OIDC Registration quy định khi JWKS chứa cả signing key và encryption key, `use` phải được khai báo cho tất cả các key để chỉ rõ mục đích. Dùng key riêng cho signing và encryption được khuyến nghị; tái sử dụng cùng key cho hai mục đích không an toàn bằng việc tách biệt.

Không lọc bỏ mọi key có `use=enc` trước khi xử lý toàn bộ metadata. Hãy chọn key theo operation cụ thể:

- Xác minh client assertion: cần key có mục đích signature/verify.
- Xác minh signed Request Object: cần public signing key.
- Mã hóa ID Token/UserInfo: cần encryption key phù hợp JWE algorithm.

### 4.4. Kiểm tra alg và key type

`alg` trong JWK là metadata tùy chọn, nhưng nếu có phải khớp thuật toán thực sự dùng với key. Một vài quy tắc:

| JWS/JWE algorithm | Key type và điều kiện điển hình |
| --- | --- |
| `RS256`, `RS384`, `RS512` | RSA; modulus đủ mạnh. |
| `PS256`, `PS384`, `PS512` | RSA; crypto provider hỗ trợ RSA-PSS. |
| `ES256` | EC curve P-256. |
| `ES384` | EC curve P-384. |
| `ES512` | EC curve P-521. |
| `ECDH-ES`, `ECDH-ES+A256KW` | EC/OKP key agreement theo curve được JWA hỗ trợ; không dùng như JWS signing key. |
| `RSA-OAEP`, `RSA-OAEP-256` | RSA public encryption key phù hợp. |

Không chấp nhận JWK EC P-384 chỉ vì metadata khai báo ES256; không chấp nhận JWK RSA cho ES256; không dùng key encryption để verify chữ ký.

Nếu JWK không khai báo `alg`, OP vẫn phải xác định key có phù hợp theo `kty`, curve, use/key_ops và allow-list của chính thuật toán đang xử lý. Thiếu `alg` không có nghĩa cho phép mọi thuật toán.

### 4.5. kid và key selection

`kid` là key identifier giúp tìm đúng key trong JWKS. RFC 7517 không bắt buộc mọi JWK phải có `kid`, nhưng production policy nên yêu cầu `kid` duy nhất cho mỗi key được dùng để ký hoặc mã hóa, đặc biệt khi có rotation.

Khi xác minh JWT:

1. Đọc protected header và lấy `alg`, `kid` nếu có.
2. Áp dụng allow-list thuật toán của endpoint/client.
3. Lọc key theo `kid`, `kty`, curve, `use`/`key_ops` và `alg`.
4. Nếu không có key phù hợp, từ chối.
5. Nếu nhiều key cùng phù hợp mà không thể chọn duy nhất, từ chối thay vì thử mọi key không giới hạn.
6. Xác minh chữ ký và các claims JWT theo protocol.

Không lấy `alg` từ JWT header làm nguồn sự thật duy nhất. Thuật toán phải nằm trong policy server đã phê duyệt và tương thích với key được chọn.

### 4.6. x5c và chứng thư X.509

JWK có thể chứa `x5c` là chuỗi certificate. Nếu sử dụng:

- Public key trong certificate đầu tiên phải khớp các public key parameters của JWK.
- Giá trị `x5c` phải được parse và kiểm tra theo policy PKI.
- Không coi việc có certificate là tự động tin cậy client; cần trust anchor và quy tắc certificate validation riêng.
- Không bỏ các trường key parameters gốc chỉ vì có `x5c`.

Chứng thư X.509 trong JWK và mTLS client authentication là hai cơ chế có thể phối hợp nhưng không đồng nhất. `jwks_uri` không thay thế TLS client certificate verification.

JWK cũng có thể khai báo `x5u`, là URL tham chiếu tới certificate chain. Nếu thư viện JOSE tự tải URL này, nó tạo thêm một outbound request do metadata client điều khiển. Hãy áp dụng cùng SSRF, TLS, redirect và response-size policy như khi tải `jwks_uri`; nếu không có use case rõ ràng, ưu tiên `x5c` đã được kiểm tra hoặc từ chối `x5u`.

## 5. Kiểm tra jwks_uri và phòng chống SSRF

### 5.1. HTTPS chỉ là bước đầu

URL `jwks_uri` phải dùng HTTPS. Nhưng HTTPS **không tự ngăn SSRF**. Một URL HTTPS vẫn có thể trỏ tới:

- Địa chỉ loopback như `127.0.0.1` hoặc `::1`.
- Mạng private như RFC 1918 hoặc IPv6 unique-local.
- Cloud metadata service hoặc endpoint quản trị.
- Host nội bộ chỉ phân giải được trong DNS của Authorization Server.
- Domain công khai có thể đổi DNS để trỏ tới IP nội bộ.
- Redirect chain dẫn từ hostname public tới địa chỉ nội bộ.

OP là bên thực hiện outbound request, do đó quyền network của OP có thể bị lạm dụng nếu tải JWKS từ URL do người đăng ký không đáng tin kiểm soát.

### 5.2. Kiểm tra URL khi đăng ký

Policy URL nên kiểm tra:

- Scheme là `https`.
- Không có username/password trong authority.
- Không có fragment.
- Host hợp lệ và có thể canonicalize an toàn.
- Port nằm trong allow-list hoặc dùng port mặc định theo policy.
- Không cho phép localhost, literal IP, private/link-local/multicast/reserved address nếu use case không yêu cầu.
- Nếu cần, hostname phải thuộc danh sách domain đã phê duyệt.
- Chặn URL dạng IP-encoded, IPv4 shorthand, IPv6 zone identifier và các biến thể parser khác nhau.

Không chỉ gọi `URI.getHost()` rồi kết luận an toàn. URL parser, DNS resolver, HTTP client và proxy có thể diễn giải URL khác nhau. Cần kiểm tra ở lớp URL parser và ở lớp network egress.

### 5.3. DNS rebinding và redirect

Một domain có thể phân giải thành IP public lúc đăng ký nhưng trả IP private ở lần resolve tiếp theo. Vì vậy:

1. Kiểm tra hostname và DNS khi cần.
2. Khi kết nối, xác minh địa chỉ đích thực tế theo policy network.
3. Tránh để HTTP client tự theo redirect không giới hạn.
4. Nếu cho phép redirect, kiểm tra lại scheme, host, DNS và địa chỉ đích ở từng hop.
5. Chặn chuyển từ public hostname sang private/internal destination.
6. Bảo đảm TLS hostname verification vẫn bật sau mọi redirect.

Network egress policy/firewall là lớp phòng thủ quan trọng; không chỉ dựa vào validator Java.

### 5.4. Giới hạn HTTP client khi tải JWKS

HTTP client dùng để lấy JWKS cần có:

- Connect timeout và response/read timeout ngắn.
- Giới hạn số byte response.
- Giới hạn số lượng JWK và kích thước từng key.
- Redirect policy rõ ràng, tốt nhất tắt tự động redirect nếu không cần.
- TLS certificate/hostname verification.
- Giới hạn concurrency và rate để chống DoS.
- Cache có TTL và revalidation phù hợp.
- Không gửi cookie, bearer token hoặc client credential của OP tới host client cung cấp.
- Không ghi full URL chứa query secret vào log nếu URL có credential hoặc dữ liệu nhạy cảm.

Không dùng một HTTP client dùng chung có interceptor tự động gắn Authorization header nội bộ cho mọi outbound request.

### 5.5. Kiểm tra response JWKS

Sau khi fetch:

1. Kiểm tra HTTP status là thành công.
2. Kiểm tra response body có giới hạn và parse thành JWK Set hợp lệ.
3. Kiểm tra không có private/symmetric key material.
4. Kiểm tra key count, duplicate kid và algorithm/key compatibility.
5. Kiểm tra `use`/`key_ops` nếu được khai báo.
6. Không coi HTTP 200 hoặc JSON parse được là bằng chứng key đáng tin.

Nếu fetch thất bại, không thay thế bằng key không rõ nguồn hoặc fallback sang một thuật toán khác. Trả lỗi xác thực phù hợp và ghi metric/log an toàn.

## 6. Thuật toán client khai báo

Không phải mọi trường chứa từ `alg` đều điều khiển cùng một chữ ký. Cần phân biệt hướng ký, loại JWT và cơ chế mã hóa.

### 6.1. token_endpoint_auth_signing_alg

Trường này khai báo JWS algorithm client **MUST** dùng khi ký JWT xác thực tại Token Endpoint với:

- `private_key_jwt`: client ký bằng private asymmetric key; OP xác minh bằng public key của client trong JWKS.
- `client_secret_jwt`: client ký MAC bằng shared client secret; không lấy key từ JWKS.

Nếu client gửi JWT với thuật toán khác metadata đã đăng ký, Token Request phải bị từ chối. Giá trị `none` MUST NOT được sử dụng. Nếu trường không được khai báo, OIDC Registration cho phép thuật toán được cả OP và RP hỗ trợ; server SHOULD hỗ trợ RS256.

Policy OP nên dùng allow-list rõ ràng, ví dụ RS256/PS256/ES256 tùy hạ tầng, và ràng buộc thuật toán với phương thức xác thực:

| token_endpoint_auth_method | Key client | Algorithm policy |
| --- | --- | --- |
| `private_key_jwt` | Asymmetric private key ở client, public key trong JWKS | Chỉ cho phép asymmetric JWS đã hỗ trợ. |
| `client_secret_jwt` | Shared client secret | Chỉ cho phép HMAC JWS được policy cho phép. |
| `client_secret_basic` / `client_secret_post` | Client secret | `token_endpoint_auth_signing_alg` không phải cơ chế xác thực đang dùng. |
| `none` | Không có client secret | Không cho phép client assertion ký bằng shared secret; dùng public-client policy/PKCE. |

### 6.2. request_object_signing_alg

Trường này khai báo thuật toán client dùng để ký Request Object gửi tới OP bằng `request` hoặc `request_uri`. OP xác minh chữ ký bằng public signing key trong JWKS của client.

OIDC Registration quy định:

- Nếu trường có giá trị, mọi Request Object của client phải được ký bằng đúng thuật toán đó.
- OP SHOULD hỗ trợ RS256.
- `none` MAY được dùng theo chuẩn, nhưng production policy có thể yêu cầu signed Request Object và từ chối `none`.
- Nếu không khai báo, các thuật toán được cả OP và RP hỗ trợ có thể được dùng.

Nếu OP yêu cầu signed Request Object, phải kiểm tra có key phù hợp trong JWKS và không cho client dùng một key encryption để xác minh JWS.

### 6.3. id_token_signed_response_alg

Trường này yêu cầu **OP** dùng JWS algorithm để ký ID Token trả cho client. Nó không phải thuật toán client dùng để ký.

- Giá trị mặc định nếu không khai báo là RS256.
- `none` MUST NOT dùng, trừ trường hợp client chỉ dùng Response Type không trả ID Token tại Authorization Endpoint theo ngoại lệ của OIDC Registration.
- Public key để client xác minh ID Token nằm trong **JWKS của OP**.
- Client `jwks_uri` không phải nơi OP lấy private key để ký ID Token.

Nếu client chỉ định thuật toán mà OP không hỗ trợ, registration phải bị từ chối bằng lỗi metadata phù hợp; không âm thầm thay bằng thuật toán khác.

### 6.4. id_token_encrypted_response_alg và enc

Nếu client muốn OP mã hóa ID Token:

- `id_token_encrypted_response_alg` khai báo JWE key-management algorithm.
- `id_token_encrypted_response_enc` khai báo content-encryption algorithm.

Khi yêu cầu encryption, OP cần public encryption key phù hợp trong JWKS của client. Nếu `id_token_encrypted_response_alg` có mặt mà `enc` không có, OIDC Registration định nghĩa default `A128CBC-HS256`; nếu `enc` được gửi mà thiếu `alg` thì metadata không hợp lệ.

Khi cả ký và mã hóa được yêu cầu, ID Token được ký trước rồi mã hóa thành Nested JWT. Không nhầm JWE `alg` với JWS `alg`.

### 6.5. userinfo_signed_response_alg và UserInfo encryption

`userinfo_signed_response_alg` yêu cầu OP ký UserInfo response bằng JWS. `userinfo_encrypted_response_alg` và `userinfo_encrypted_response_enc` yêu cầu OP mã hóa UserInfo response bằng JWE.

Các thuật toán này cũng phải được kiểm tra theo khả năng OP và public key client. Chúng không tự thay đổi thuật toán ký ID Token.

### 6.6. Bảng tổng hợp

| Metadata | Hành động | Key phía client/OP |
| --- | --- | --- |
| `token_endpoint_auth_signing_alg` | Client ký client assertion | Client private key hoặc client secret; OP xác minh. |
| `request_object_signing_alg` | Client ký Request Object | Client private key; OP xác minh bằng JWKS client. |
| `id_token_signed_response_alg` | OP ký ID Token | OP private key; client xác minh bằng JWKS OP. |
| `id_token_encrypted_response_alg` | OP mã hóa ID Token | OP dùng public encryption key của client. |
| `id_token_encrypted_response_enc` | Mã hóa nội dung ID Token | Content-encryption algorithm của JWE. |
| `userinfo_signed_response_alg` | OP ký UserInfo response | OP private key. |
| `userinfo_encrypted_response_alg` | OP mã hóa UserInfo response | OP dùng public encryption key của client. |
| `userinfo_encrypted_response_enc` | Mã hóa nội dung UserInfo | Content-encryption algorithm của JWE. |

## 7. Quy tắc kiểm tra algorithm và key

### 7.1. Dùng allow-list theo từng mục đích

Không tạo một danh sách “mọi thuật toán JOSE được thư viện biết” rồi dùng cho tất cả metadata. Mỗi mục đích có một allow-list riêng:

- Client authentication JWS.
- Request Object JWS.
- ID Token JWS của OP.
- ID Token/UserInfo JWE key-management algorithm.
- ID Token/UserInfo JWE content-encryption algorithm.

Một thuật toán được hỗ trợ về mặt thư viện chưa chắc đã được phép trong security policy của hệ thống. Allow-list phải xét:

1. Khả năng của crypto provider/JWT library.
2. Loại và độ mạnh key đang có.
3. Hỗ trợ của client thực tế.
4. Quy định bảo mật của tổ chức.
5. Metadata OP đã công bố.
6. Khả năng rotation và vận hành key.

### 7.2. Không chấp nhận thuật toán none cho client authentication

`token_endpoint_auth_signing_alg=none` phải bị từ chối. Nếu server yêu cầu `private_key_jwt`, phải xác minh chữ ký bất đối xứng. Nếu yêu cầu `client_secret_jwt`, phải xác minh MAC bằng client secret và ràng buộc thuật toán được phép.

Đối với Request Object, chuẩn cho phép `none` trong một số trường hợp, nhưng nếu server dựa vào chữ ký Request Object để bảo vệ request integrity thì phải yêu cầu JWS có chữ ký.

Đối với ID Token, áp dụng đúng ngoại lệ Response Type của OIDC Registration; policy production có thể chặt hơn chuẩn nhưng không được quảng bá một thuật toán mà OP không thực thi.

### 7.3. Kiểm tra metadata thuật toán có quan hệ với key

Ví dụ:

| Metadata khai báo | JWKS thực tế | Kết quả |
| --- | --- | --- |
| `private_key_jwt` + `PS256` | Có RSA signing public key phù hợp | Có thể chấp nhận sau các kiểm tra khác. |
| `private_key_jwt` + `ES256` | Chỉ có RSA key | Từ chối hoặc không hoàn tất registration. |
| `private_key_jwt` + `RS256` | JWKS chỉ có EC key | Không tương thích. |
| Signed Request Object `ES256` | Có EC P-256 key với use phù hợp | Có thể xác minh. |
| Signed Request Object `ES256` | Chỉ có EC P-384 key | Không tương thích. |
| `id_token_signed_response_alg=ES256` | OP chỉ có RSA signing key | OP không thể đáp ứng metadata; từ chối. |
| Encrypted ID Token `RSA-OAEP-256` | Client JWKS chỉ có signing key EC | Không có encryption key tương thích. |
| `client_secret_jwt` + `HS256` | Client secret được cấp và policy cho phép HS256 | Có thể chấp nhận; không cần JWKS cho assertion. |

### 7.4. Không suy diễn key chỉ từ tên thuật toán

`RS256` gợi ý RSA nhưng vẫn phải kiểm tra modulus, public exponent và JWK metadata. `ES256` đòi hỏi P-256, không phải bất kỳ EC curve nào. `PS256` cần RSA-PSS support của crypto provider. Với JWE, cần phân biệt key-management algorithm (ví dụ RSA-OAEP-256 hoặc ECDH-ES) và content-encryption algorithm (ví dụ A256GCM).

Không chấp nhận key yếu, curve không được phép, thuật toán lỗi thời hoặc tổ hợp JWK/alg không nhất quán chỉ vì một thư viện có thể parse được.

## 8. Cấu hình DCR validator trong Spring Authorization Server

### 8.1. DCR bị tắt mặc định

Spring Authorization Server 1.5.8 tắt OpenID Connect Dynamic Client Registration Endpoint theo mặc định. Endpoint này là OAuth2 protected resource:

- Client Registration request cần Bearer access token có scope `client.create`.
- Client Read request cần scope `client.read`.
- Cần cấu hình `JwtDecoder` bean cho endpoint.

Không mở endpoint đăng ký cho anonymous caller chỉ vì muốn thử nghiệm metadata. Initial Access Token/registration access token, rate limit, tenant policy và quy trình phê duyệt phải được thiết kế trước.

### 8.2. Validator mặc định từ 1.5.7

`OidcClientRegistrationAuthenticationValidator` được thêm trong Spring Authorization Server 1.5.7. Trong 1.5.8, validator mặc định kiểm tra:

- `redirect_uris`.
- `post_logout_redirect_uris`.
- `jwks_uri`.
- `scope`.

Các field có hai nhóm validator:

| Validator | Ý nghĩa |
| --- | --- |
| `DEFAULT_JWK_SET_URI_VALIDATOR` | Từ chối `jwks_uri` không dùng HTTPS. |
| `SIMPLE_JWK_SET_URI_VALIDATOR` | Giữ behavior cũ, không kiểm tra URL. Có thể cho phép giá trị dẫn tới SSRF. |
| `DEFAULT_REDIRECT_URI_VALIDATOR` | Từ chối URI thiếu scheme, có fragment hoặc scheme nguy hiểm. |
| `DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR` | Áp dụng quy tắc an toàn tương tự cho post-logout URI. |
| `DEFAULT_SCOPE_VALIDATOR` | Từ chối request có scope không rỗng. |
| `SIMPLE_SCOPE_VALIDATOR` | Chấp nhận scope theo behavior cũ; cần policy scope riêng. |

Điểm quan trọng: `DEFAULT_JWK_SET_URI_VALIDATOR` chỉ kiểm tra **scheme HTTPS**. Nó không chứng minh hostname an toàn, không chặn DNS rebinding, không kiểm tra redirect chain và không xác minh JWK Set có public key hợp lệ. Đây là lớp validation đầu tiên, không phải toàn bộ SSRF defense.

### 8.3. Giữ validator mặc định và thêm thuật toán riêng

Spring Authorization Server cho phép tùy chỉnh validator bằng `OidcClientRegistrationAuthenticationProvider.setAuthenticationValidator(...)`. Ví dụ:

~~~java
private static Consumer<List<AuthenticationProvider>>
        registrationValidatorCustomizer() {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof OidcClientRegistrationAuthenticationProvider registrationProvider) {
            registrationProvider.setAuthenticationValidator(
                OidcClientRegistrationAuthenticationValidator
                    .DEFAULT_REDIRECT_URI_VALIDATOR
                    .andThen(
                        OidcClientRegistrationAuthenticationValidator
                            .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
                    .andThen(
                        OidcClientRegistrationAuthenticationValidator
                            .DEFAULT_JWK_SET_URI_VALIDATOR)
                    .andThen(customAlgorithmValidator())
                    .andThen(customScopeValidator()));
        }
    });
}
~~~

Đoạn code thể hiện thứ tự validator. Khi thay validator, phải chủ động chain lại các kiểm tra cần giữ. Không thay `DEFAULT_JWK_SET_URI_VALIDATOR` bằng `SIMPLE_JWK_SET_URI_VALIDATOR` chỉ để làm registration dễ hơn.

### 8.4. Đọc metadata từ authentication context

Validator nhận `OidcClientRegistrationAuthenticationContext`. Request metadata có thể lấy từ:

~~~java
private static Consumer<OidcClientRegistrationAuthenticationContext>
        customAlgorithmValidator() {

    return context -> {
        OidcClientRegistrationAuthenticationToken authentication =
            context.getAuthentication();
        OidcClientRegistration registration =
            authentication.getClientRegistration();

        String jwksUri = registration.getJwkSetUrl();
        String authMethod =
            registration.getTokenEndpointAuthenticationMethod();
        String authSigningAlg =
            registration.getTokenEndpointAuthenticationSigningAlgorithm();
        String idTokenAlg =
            registration.getIdTokenSignedResponseAlgorithm();
        String requestObjectAlg =
            registration.getClaimAsString("request_object_signing_alg");

        validateJwksUriPolicy(jwksUri);
        validateClientAuthenticationAlgorithm(
            authMethod, authSigningAlg, jwksUri);
        validateIdTokenResponseAlgorithm(idTokenAlg);
        validateRequestObjectAlgorithm(requestObjectAlg, jwksUri);
    };
}
~~~

Các hàm `validate...` là policy của ứng dụng. Chúng phải ném `OAuth2AuthenticationException` với `OAuth2Error` thích hợp khi metadata không hợp lệ. Không thực hiện network fetch không giới hạn ngay trong validator đồng bộ; nếu cần kiểm tra JWKS tại registration, hãy dùng fetcher được harden với timeout, egress policy và response-size limit.

### 8.5. Kiểm tra algorithm theo auth method

Ví dụ policy đơn giản:

~~~java
private static void validateClientAuthenticationAlgorithm(
        String authMethod, String alg, String jwksUri) {

    if ("private_key_jwt".equals(authMethod)) {
        if (jwksUri == null || jwksUri.isBlank()) {
            throw invalidClientMetadata(
                "private_key_jwt requires a client public key source");
        }
        if (alg != null && !Set.of("RS256", "PS256", "ES256").contains(alg)) {
            throw invalidClientMetadata(
                "Unsupported private_key_jwt signing algorithm");
        }
    }

    if ("client_secret_jwt".equals(authMethod)) {
        if (alg != null && !Set.of("HS256").contains(alg)) {
            throw invalidClientMetadata(
                "Unsupported client_secret_jwt signing algorithm");
        }
    }

    if ("none".equals(alg)) {
        throw invalidClientMetadata(
            "Unsigned client authentication assertion is not allowed");
    }
}

private static OAuth2AuthenticationException invalidClientMetadata(
        String description) {
    return new OAuth2AuthenticationException(
        new OAuth2Error(
            "invalid_client_metadata",
            description,
            null));
}
~~~

Đây là policy mẫu, không phải danh sách thuật toán bắt buộc của chuẩn. Nếu hỗ trợ `client_secret_jwt` với HS384/HS512, mở allow-list có chủ đích. Nếu client dùng `private_key_jwt` nhưng server hỗ trợ `jwks` inline, thay điều kiện yêu cầu `jwks_uri` bằng kiểm tra nguồn public key đã được lưu và xác minh. Ví dụ trên giả định deployment chỉ chấp nhận remote JWKS.

Không yêu cầu `jwks_uri` cho `client_secret_basic`. Không dùng `id_token_signed_response_alg` để suy ra client cần public key; đó là thuật toán OP ký ID Token.

### 8.6. Kiểm tra scope theo policy

Trong Spring Authorization Server 1.5.8, default scope validator từ chối mọi scope không rỗng. Nếu sản phẩm muốn nhận scope do client khai báo, hãy thay bằng một validator allow-list cụ thể, ví dụ:

~~~java
private static Consumer<OidcClientRegistrationAuthenticationContext>
        customScopeValidator() {

    Set<String> allowedScopes = Set.of(
        "openid",
        "profile",
        "orders.read");

    return context -> {
        List<String> requestedScopes =
            context.getAuthentication()
                .getClientRegistration()
                .getScopes();

        if (!allowedScopes.containsAll(requestedScopes)) {
            throw invalidClientMetadata("Unsupported client scope");
        }
    };
}
~~~

Nếu scope là phần metadata mà tổ chức không cho client tự chọn, dùng `DEFAULT_SCOPE_VALIDATOR` thay cho custom validator. Không dùng `SIMPLE_SCOPE_VALIDATOR` như một cách tắt validation chung.

### 8.7. Bật endpoint với validator

Ví dụ cấu hình:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .clientRegistrationEndpoint(registration ->
                    registration.authenticationProviders(
                        registrationValidatorCustomizer())))
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là phần cấu hình endpoint. Ứng dụng vẫn cần RegisteredClientRepository, OAuth2AuthorizationService, token generator, JwtDecoder, key management, bảo vệ scope `client.create`/`client.read` và persistence. Không bật DCR trong production nếu chưa có policy xác định ai được đăng ký client và metadata nào cần phê duyệt.

## 9. Lưu metadata vào RegisteredClient

### 9.1. jwks_uri được lưu trong ClientSettings

Spring Authorization Server 1.5.8 ánh xạ URL JWKS của client vào `ClientSettings`:

~~~java
ClientSettings clientSettings = ClientSettings.builder()
    .jwkSetUrl("https://partner.example.com/.well-known/jwks.json")
    .tokenEndpointAuthenticationSigningAlgorithm(
        SignatureAlgorithm.PS256)
    .build();

RegisteredClient registeredClient = RegisteredClient
    .withId("partner-service-record-001")
    .clientId("partner-service")
    .clientName("Partner Service")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.PRIVATE_KEY_JWT)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("orders.read")
    .clientSettings(clientSettings)
    .build();
~~~

Ví dụ dùng `SignatureAlgorithm.PS256` để minh họa JWS algorithm bất đối xứng; hãy xác minh class/enum và crypto provider trong dependency version của ứng dụng. `tokenEndpointAuthenticationSigningAlgorithm` nhận `JwsAlgorithm`, còn `jwkSetUrl` lưu URL JWKS. DCR converter mặc định của framework là nơi ánh xạ metadata registration sang RegisteredClient; nếu thêm policy riêng, giữ nguyên mọi field do converter mặc định xử lý.

### 9.2. Đọc lại client registration

Sau khi lưu, Client Configuration Endpoint trả metadata đã đăng ký. Hãy kiểm tra:

- `jwks_uri` phản ánh đúng URL đã phê duyệt.
- `token_endpoint_auth_method` đúng phương thức được cấp.
- `token_endpoint_auth_signing_alg` đúng thuật toán đã lưu.
- Không trả private key hoặc raw secret ngoài quy định.
- Các metadata custom được converter hai chiều xử lý nhất quán.

Nếu custom converter chỉ xử lý chiều request nhưng không xử lý chiều response, client read response có thể thiếu hoặc trả sai metadata. Spring Authorization Server cung cấp `setRegisteredClientConverter(...)` và `setClientRegistrationConverter(...)` để tùy chỉnh hai chiều.

### 9.3. Lưu inline jwks nếu thật sự cần

Vì `RegisteredClient.ClientSettings` mặc định có URL nhưng không có field chuyên biệt cho inline JWK Set, hỗ trợ `jwks` cần một thiết kế riêng:

1. Parse và validate JWKS ngay trong registration request.
2. Chỉ giữ public key đã được kiểm tra; loại private/symmetric material.
3. Serialize theo format chuẩn hoặc lưu key record trong bảng riêng gắn với RegisteredClient ID.
4. Đặt giới hạn dung lượng, số key, schema version và quyền đọc.
5. Khi xác minh JWT, tạo JWK source từ snapshot đã lưu.
6. Khi cập nhật registration, thay key set nguyên tử và audit phiên bản.
7. Khi trả Client Read Response, trả đúng metadata theo policy.

Không serialize một object Java tùy ý vào ClientSettings rồi giả định mọi JDBC mapper/upgrade sẽ giữ nguyên tương thích. Với key rotation thường xuyên, `jwks_uri` dễ vận hành hơn.

## 10. Thuật toán và JWK trong các luồng thực tế

### 10.1. private_key_jwt

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Partner Client
    participant JWKS as Client JWKS URI
    participant AS as Authorization Server
    C->>C: Tạo client_assertion JWT
    C->>C: Ký bằng private key PS256
    C->>AS: POST /oauth2/token + client_assertion
    AS->>JWKS: Tải public JWK nếu cache miss/refresh
    JWKS-->>AS: JWK Set của client
    AS->>AS: Chọn RSA public key theo kid/alg
    AS->>AS: Xác minh signature và assertion claims
    AS-->>C: Access Token hoặc lỗi invalid_client
~~~

OP phải kiểm tra `iss`, `sub`, `aud`, `exp`, `jti`, client ID và chống replay theo JWT client authentication profile. Chữ ký đúng nhưng `aud` sai hoặc assertion đã dùng lại vẫn phải bị từ chối.

### 10.2. Signed Request Object

Client ký Request Object bằng private key; OP lấy public key từ JWKS để xác minh trước khi sử dụng claims trong request. Các kiểm tra chữ ký và claim phải theo OIDC Core, gồm issuer/client, audience, thời gian và replay policy. Không dùng một request JWT đã ký hợp lệ nhưng sai `aud` như một authorization request hợp lệ.

### 10.3. OP mã hóa ID Token cho client

Khi client khai báo `id_token_encrypted_response_alg`, OP chọn public encryption key của client trong JWKS. Key phải phù hợp với JWE algorithm; signing key `use=sig` không được sử dụng làm encryption key chỉ vì nó nằm cùng JWKS.

Nếu client yêu cầu cả signing và encryption, OP có thể ký ID Token bằng private key OP rồi mã hóa bằng public key client. Client giải mã bằng private key của nó và xác minh chữ ký bằng public key OP.

## 11. Cache, rotation và tính sẵn sàng của JWKS

### 11.1. jwks_uri hỗ trợ rotation

Một client có thể công bố đồng thời public key hiện tại và key kế tiếp:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "partner-rsa-old",
      "n": "old-public-modulus",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "partner-rsa-new",
      "n": "new-public-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

Quy trình rotation:

1. Client công bố public key mới trước khi dùng private key mới.
2. Chờ OP có thể lấy key mới theo cache/revalidation policy.
3. Client chuyển ký bằng key mới và dùng `kid` mới.
4. Giữ public key cũ đủ lâu cho assertion/request in-flight và retry hợp lệ.
5. Gỡ key cũ khi không còn cần xác minh.

### 11.2. Cache phải có giới hạn

Cache JWKS giảm outbound request và latency, nhưng nếu key bị compromise hoặc bị thu hồi, cache quá lâu có thể tiếp tục tin public key cũ. Cần:

- TTL tối đa theo security policy.
- Hỗ trợ HTTP cache headers nếu thư viện cho phép.
- Refresh khi không tìm thấy `kid`, nhưng có rate limit để tránh forced refresh DoS.
- Single-flight/concurrent refresh để tránh hàng loạt request đồng thời.
- Giới hạn số lần refresh và không retry vô hạn.
- Invalidate cache khi registration/key version thay đổi theo kênh tin cậy.

Không chấp nhận JWKS stale vô thời hạn khi endpoint timeout. Nếu cache hết freshness và không thể tải key, quyết định xác minh phải fail closed.

### 11.3. Registration update và cache invalidation

Client Configuration Endpoint cho phép cập nhật metadata theo Registration Access Token. Khi `jwks_uri` thay đổi:

- Xác thực Registration Access Token và quyền sửa client.
- Chạy lại URL validation và policy algorithm/key.
- Ghi metadata mới nguyên tử.
- Invalidate JWKS cache cho client.
- Audit URL cũ/mới bằng fingerprint đã xử lý, không ghi key/private material.
- Kiểm thử assertion cũ/mới trong giai đoạn chuyển tiếp theo policy.

Không để một client thay `jwks_uri` ngay trước Token Request để chuyển OP tới host mới mà không chạy lại validator.

## 12. Lỗi thường gặp và cách xử lý

### Lỗi 1: Nhầm JWKS của client với JWKS của OP

**Triệu chứng:** OP cố dùng public key client để xác minh ID Token do chính OP ký.

**Nguyên nhân:** Không phân biệt hai hướng trust.

**Cách sửa:** Dùng client JWKS để xác minh chữ ký client/mã hóa response cho client; dùng OP JWKS cho client xác minh token OP ký.

### Lỗi 2: Cho phép jwks_uri dùng HTTP

**Triệu chứng:** Client key bị thay trên đường truyền hoặc attacker điều khiển nội dung JWKS.

**Nguyên nhân:** Bỏ qua yêu cầu HTTPS của OIDC Registration.

**Cách sửa:** Giữ `DEFAULT_JWK_SET_URI_VALIDATOR` và bắt buộc TLS hostname/certificate verification.

### Lỗi 3: Nghĩ HTTPS đã ngăn được SSRF

**Triệu chứng:** OP truy cập cloud metadata hoặc internal HTTPS service qua `jwks_uri`.

**Nguyên nhân:** Validator chỉ kiểm tra scheme.

**Cách sửa:** DNS/IP egress policy, block private/reserved destinations, kiểm soát redirect và hardened HTTP client.

### Lỗi 4: Dùng SIMPLE_JWK_SET_URI_VALIDATOR trong production

**Triệu chứng:** URL không an toàn được chấp nhận.

**Nguyên nhân:** Dùng validator tương thích ngược không kiểm tra URL.

**Cách sửa:** Dùng strict validator và bổ sung SSRF policy. Chỉ dùng SIMPLE khi có lý do tương thích đã được đánh giá và có lớp kiểm tra tương đương.

### Lỗi 5: Client gửi jwks_uri và jwks cùng lúc

**Triệu chứng:** Không rõ key source nào là nguồn sự thật.

**Nguyên nhân:** Không kiểm tra mutual exclusion.

**Cách sửa:** Từ chối registration; yêu cầu client chọn đúng một phương thức.

### Lỗi 6: JWKS chứa private key

**Triệu chứng:** Private key của client xuất hiện trong request, log hoặc database.

**Nguyên nhân:** Client upload toàn bộ keystore thay vì public key.

**Cách sửa:** Từ chối JWK có private/symmetric parameters; xóa raw request khỏi log và yêu cầu rotate key nếu đã lộ.

### Lỗi 7: Dùng một key cho cả signing và encryption

**Triệu chứng:** Key selection mơ hồ và key compromise ảnh hưởng nhiều mục đích.

**Nguyên nhân:** Tái sử dụng key hoặc không khai báo `use`.

**Cách sửa:** Tách key theo mục đích; nếu JWKS chứa cả signing và encryption, khai báo `use` cho từng key.

### Lỗi 8: Không kiểm tra alg với kty/curve

**Triệu chứng:** Client khai báo ES256 nhưng chỉ có RSA key.

**Nguyên nhân:** Chỉ kiểm tra thuật toán có nằm trong danh sách chuỗi cho phép.

**Cách sửa:** Validate cặp algorithm/key type/curve/use và thực hiện một phép xác minh thử trong test.

### Lỗi 9: Nhầm token_endpoint_auth_signing_alg với id_token_signed_response_alg

**Triệu chứng:** Client assertion dùng sai thuật toán hoặc OP ký ID Token theo policy không mong muốn.

**Nguyên nhân:** Gộp thuật toán client ký và OP ký.

**Cách sửa:** Lưu và kiểm tra từng metadata riêng, theo đúng chiều ký.

### Lỗi 10: Cho phép none cho client authentication

**Triệu chứng:** JWT assertion không có chữ ký nhưng vẫn được chấp nhận.

**Nguyên nhân:** Không áp dụng normative rule cho `token_endpoint_auth_signing_alg`.

**Cách sửa:** Từ chối `none`; yêu cầu JWS algorithm và key/secret phù hợp.

### Lỗi 11: Xóa key cũ ngay sau rotation

**Triệu chứng:** Assertion hợp lệ đang in-flight bị từ chối vì `kid` không còn trong JWKS.

**Nguyên nhân:** Rotation không có overlap.

**Cách sửa:** Pre-publish key mới, overlap, theo dõi cache và chỉ retire key cũ sau thời gian an toàn.

### Lỗi 12: Chỉ validate lúc đăng ký, không validate lúc cập nhật

**Triệu chứng:** Client thay JWKS URL sang địa chỉ không an toàn qua Client Configuration Endpoint.

**Nguyên nhân:** Chỉ gắn validator cho registration provider, bỏ qua configuration/update path.

**Cách sửa:** Áp dụng cùng policy cho cả registration và client configuration update, kiểm thử cả hai endpoint.

## 13. Ma trận kiểm thử

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| `jwks_uri` HTTPS hợp lệ | Qua strict scheme validator; tiếp tục kiểm tra policy host và JWKS. |
| `jwks_uri` dùng HTTP | Bị từ chối. |
| `jwks_uri` dùng localhost/private IP | Bị policy SSRF từ chối. |
| `jwks_uri` redirect tới private IP | Không follow hoặc redirect bị policy chặn. |
| DNS rebinding | Kết nối tới private/reserved address bị chặn. |
| TLS certificate sai hostname/expired | Không tải JWKS. |
| Response JWKS vượt kích thước | Dừng tải và từ chối. |
| JWKS không có `keys` array | Từ chối. |
| JWK thiếu `kty` | Từ chối. |
| JWKS có private RSA `d` | Từ chối; không log raw key. |
| JWKS có symmetric `oct` key | Từ chối theo OIDC Registration. |
| Có cả `jwks_uri` và `jwks` | Từ chối metadata. |
| Có signing và encryption key nhưng thiếu `use` | Từ chối theo policy OIDC. |
| `use` và `key_ops` mâu thuẫn | Từ chối. |
| `kid` trùng cho hai key khác nhau | Từ chối hoặc không thể chọn key duy nhất. |
| ES256 nhưng key không phải P-256 | Từ chối. |
| RS256 nhưng JWK là EC | Từ chối. |
| private_key_jwt không có public key source | Từ chối registration theo policy. |
| client_secret_jwt dùng HMAC được phép | Chấp nhận nếu secret và policy phù hợp. |
| token_endpoint_auth_signing_alg là none | Từ chối. |
| request_object_signing_alg ngoài allow-list | Từ chối. |
| id_token_signed_response_alg OP không hỗ trợ | Từ chối metadata. |
| id_token_encrypted_response_alg không có encryption key | Từ chối. |
| Registration scope ngoài allow-list | Từ chối. |
| JWKS rotation có key mới và cũ | Cả hai key được xác minh trong overlap window. |
| JWKS endpoint timeout sau cache expiry | Xác minh fail closed. |
| Client update đổi `jwks_uri` | Chạy lại validator và invalidate cache. |
| Client Read sau registration | Metadata được trả lại đúng và không lộ private key. |
| Registration endpoint không có client.create | Bị từ chối. |

## 14. Checklist production

| Hạng mục | Câu hỏi cần xác nhận |
| --- | --- |
| DCR access | Endpoint đã được bảo vệ bằng access token và scope `client.create`? |
| Registration read | Scope `client.read` được yêu cầu cho Client Read? |
| jwks_uri | Chỉ chấp nhận HTTPS và hostname/địa chỉ đích an toàn? |
| SSRF | Có egress firewall, DNS/IP validation và redirect policy? |
| HTTP client | Có timeout, response-size limit, concurrency limit và TLS verification? |
| JWKS schema | Có kiểm tra `keys`, `kty`, key count và duplicate key? |
| Private material | Không có private/symmetric JWK value? |
| Key use | `use`/`key_ops` đúng mục đích và nhất quán? |
| Algorithm | Allow-list riêng cho JWS/JWE và tương thích key? |
| Client auth | `token_endpoint_auth_method` tương thích signing algorithm và key source? |
| Request Object | Signed Request Object được xác minh theo client key policy? |
| ID Token | Không nhầm client JWKS với OP JWKS? |
| JWE | Có encryption key phù hợp cho ID Token/UserInfo response? |
| Registration update | Validator được áp dụng cả khi sửa metadata? |
| Persistence | RegisteredClient metadata được lưu bền vững và đọc lại đúng? |
| Rotation | Có pre-publish, overlap, cache refresh và key retirement? |
| Audit | Không log raw JWK private, client assertion hoặc secret? |
| Tests | Có SSRF, algorithm mismatch, malformed JWKS, rotation và negative tests? |

## 15. Bài tập thực hành

Một đối tác muốn đăng ký ba capability:

- `private_key_jwt` tại Token Endpoint bằng PS256.
- Signed Request Object bằng ES256.
- Nhận ID Token được mã hóa bằng RSA-OAEP-256 và A256GCM.

Đối tác gửi `jwks_uri=https://partner.example.com/.well-known/jwks.json`. JWKS chứa một RSA signing key, một EC P-256 signing key và một RSA encryption key. Endpoint chạy sau CDN có cache 5 phút.

1. Thiết kế metadata registration với các trường thuật toán phù hợp.
2. Chỉ ra public key nào dùng cho PS256, ES256 và RSA-OAEP-256.
3. Xác định `use` phải khai báo ra sao khi JWKS chứa signing và encryption keys.
4. Viết validator kiểm tra HTTPS, auth method, algorithm allow-list và key source.
5. Thiết kế SSRF defense cho `jwks_uri`, bao gồm DNS rebinding và redirect.
6. Xác định thời điểm OP fetch JWKS, TTL cache và cách refresh khi `kid` mới xuất hiện.
7. Thử registration chứa đồng thời `jwks_uri` và `jwks`; xác định lỗi phải trả.
8. Thử JWKS chứa private RSA `d` và symmetric `k`; xác định hành vi và log an toàn.
9. Rotation RSA signing key trong khi giữ EC key; chứng minh assertion cũ/mới vẫn được xác minh trong overlap.
10. Kiểm tra `id_token_signed_response_alg` là thuật toán OP ký ID Token, không phải một trong các thuật toán client ký.

**Tiêu chí đạt:** Mỗi thuật toán được gắn đúng mục đích và key phù hợp; OP không tải tài nguyên nội bộ từ `jwks_uri`; JWKS chỉ chứa public key; registration và update đều được kiểm tra; key rotation không tạo khoảng trống xác minh.

## 16. Tài liệu đối chiếu

- [OpenID Connect Dynamic Client Registration 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-registration-1_0.html): `jwks_uri`, `jwks`, client metadata, thuật toán và validation.
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591): client metadata `jwks_uri`/`jwks` và registration errors.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): `kty`, `use`, `key_ops`, `alg`, `kid` và JWK Set.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS protected header và signature verification.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE serialization, key management và content encryption.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JWS/JWE và key requirements.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): `private_key_jwt`/JWT client assertion.
- [Spring Authorization Server — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): bật DCR, validator và converter.
- [Spring Authorization Server 1.5.8 — OidcClientRegistrationAuthenticationValidator Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationValidator.html): strict/simple validators và kiểm tra `jwks_uri`.
- [Spring Authorization Server 1.5.8 — OidcClientRegistration.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcClientRegistration.Builder.html): `jwkSetUrl` và client metadata.
- [Spring Authorization Server 1.5.8 — OidcClientRegistrationAuthenticationProvider Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationProvider.html): authentication validator và converter.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Client Registration Endpoint, bearer access token và scope requirements.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient` và `ClientSettings.jwkSetUrl`.
