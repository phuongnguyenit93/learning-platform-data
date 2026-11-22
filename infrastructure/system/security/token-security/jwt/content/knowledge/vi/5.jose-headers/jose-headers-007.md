# JWK trong JOSE Header và rủi ro tin vào khóa nhúng do bên gửi cung cấp

## 1. JWK trong JOSE Header là gì?

JSON Web Key (JWK) là cấu trúc JSON biểu diễn một khóa mật mã cùng metadata liên quan như loại khóa, mục đích sử dụng và thuật toán. JOSE Header Parameter **jwk** cho phép nhúng trực tiếp một JWK vào header của JWS hoặc JWE.

Theo RFC 7515, **jwk trong JWS biểu diễn khóa công khai tương ứng với khóa đã dùng để ký JWS**. Theo RFC 7516, **jwk trong JWE biểu diễn khóa công khai của recipient mà JWE được mã hóa tới**, giúp recipient xác định khóa riêng cần dùng để giải mã.

Ví dụ JWS:

~~~json
{
  "alg": "ES256",
  "typ": "JWT",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<public-x-coordinate>",
    "y": "<public-y-coordinate>"
  }
}
~~~

Ví dụ JWE:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "jwk": {
    "kty": "RSA",
    "n": "<recipient-public-modulus>",
    "e": "AQAB"
  }
}
~~~

Các giá trị trong ví dụ là placeholder, không phải khóa có thể sử dụng.

JWK trong header là tham số tùy chọn. Nó giúp mang thông tin khóa cùng đối tượng JOSE, nhưng **không tự chứng minh khóa thuộc về một issuer, người dùng, tổ chức hay recipient cụ thể**. Đây là điểm quan trọng nhất khi xử lý khóa do chính bên gửi nhúng vào token.

## 2. Phân biệt JWK hợp lệ với khóa đáng tin cậy

Một JWK có thể chứa đầy đủ tham số toán học để thư viện import khóa và thực hiện thao tác mật mã. Điều đó chỉ trả lời câu hỏi:

> Khóa này có đúng cấu trúc và có thể dùng cho thuật toán được chỉ định hay không?

Nó chưa trả lời:

> Ai sở hữu khóa này, ai đã đăng ký nó, và vì sao ứng dụng phải tin dữ liệu được bảo vệ bằng khóa này?

Ví dụ, một public JWK RSA hợp lệ có thể chứa kty, n và e. Thư viện có thể import khóa đó và xác minh một chữ ký RSA thành công. Nhưng bất kỳ ai cũng có thể tự tạo một cặp khóa RSA, công bố phần public trong JWK và ký dữ liệu bằng phần private của họ.

Vì vậy, cần phân biệt:

| Khái niệm | Điều nó chứng minh |
| --- | --- |
| JWK hợp lệ về cú pháp | Dữ liệu khóa có cấu trúc phù hợp với định dạng JWK |
| Khóa phù hợp thuật toán | Loại khóa và tham số có thể dùng với thuật toán dự kiến |
| Chữ ký xác minh thành công bằng JWK nhúng | Người tạo chữ ký có quyền sử dụng private key tương ứng với public key được nhúng |
| Khóa thuộc issuer đáng tin | Cần cơ chế xác lập nguồn gốc và liên kết khóa với issuer độc lập với lời khai trong token |

Một chữ ký hợp lệ bằng khóa do token tự mang chỉ xác nhận **tính nhất quán mật mã giữa chữ ký và khóa đó**. Nó không tự xác nhận danh tính của bên phát hành. RFC 7515 mục 10.3 yêu cầu kỹ thuật quản lý khóa dùng để lấy public key phải xác thực nguồn gốc của khóa; nếu không, bên nhận không biết thực thể nào đã ký thông điệp.

## 3. Rủi ro tự cung cấp khóa trong JWS

Đây là tình huống nguy hiểm nhất khi ứng dụng sử dụng JWK trong header như nguồn khóa xác minh duy nhất.

Giả sử một API chỉ nên chấp nhận access token do issuer https://identity.example phát hành. Kẻ tấn công có thể:

1. Tạo cặp khóa riêng/công khai của chính họ.
2. Đưa public key vào JOSE Header dưới tham số jwk.
3. Tạo payload có các claim như iss, sub, aud và exp theo ý muốn.
4. Ký JWS bằng private key của họ.
5. Gửi token tới API.

Header và payload minh họa:

~~~json
{
  "alg": "ES256",
  "typ": "JWT",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<attacker-public-x>",
    "y": "<attacker-public-y>"
  }
}
~~~

~~~json
{
  "iss": "https://identity.example",
  "sub": "administrator",
  "aud": "orders-api",
  "exp": 1893456000
}
~~~

Nếu API lấy public key trực tiếp từ jwk, xác minh chữ ký bằng chính khóa đó rồi tin các claim mà không kiểm tra quan hệ giữa khóa và issuer, chữ ký sẽ hợp lệ. Kẻ tấn công đã tạo cả khóa lẫn chữ ký nên phép xác minh không phát hiện được việc khóa không thuộc issuer.

**Sai lầm cốt lõi:** dùng khóa mà token tự khai để chứng minh chính token đó đến từ một issuer đã được tin cậy.

### Chữ ký có bảo vệ jwk thì đã đủ chưa?

Trong JWS Compact Serialization, toàn bộ protected header được đưa vào signing input. Vì vậy, jwk trong protected header được bảo vệ cùng chữ ký. Điều đó ngăn người trung gian sửa khóa mà không làm chữ ký mất hiệu lực.

Tuy nhiên, kẻ tấn công tạo token từ đầu vẫn có thể đưa **khóa công khai của chính họ** vào protected header rồi ký toàn bộ header và payload bằng private key tương ứng. Chữ ký bảo vệ mối liên hệ giữa token và khóa được khai báo; nó không tạo ra một mối liên hệ đáng tin cậy giữa khóa đó và issuer.

Nói cách khác, tính toàn vẹn của header và nguồn gốc đáng tin cậy của khóa là hai vấn đề khác nhau.

## 4. Rủi ro và cách hiểu jwk trong JWE

Trong JWE, jwk có vai trò khác JWS. Theo RFC 7516, nó biểu diễn public key mà JWE được mã hóa tới và có thể giúp recipient xác định private key tương ứng để giải mã.

Ví dụ, bên gửi mã hóa CEK hoặc nội dung theo cơ chế sử dụng public key của recipient. Header có thể mang JWK của public key đó:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "jwk": {
    "kty": "RSA",
    "n": "<recipient-public-modulus>",
    "e": "AQAB"
  }
}
~~~

Recipient có thể dùng thông tin này để tìm private key tương ứng trong kho khóa của mình. Các giới hạn quan trọng:

- JWK nhúng phải được đối chiếu với khóa recipient đã được quản trị hoặc cấu hình tin cậy.
- Không import một khóa riêng tùy ý từ token để thay thế kho khóa recipient.
- Không để jwk quyết định tùy ý tenant, tài khoản, kho khóa hoặc phạm vi giải mã.
- Nếu public key không khớp với một khóa recipient được phép, từ chối JWE.

**Giải mã JWE thành công không tự chứng minh danh tính người gửi.** Với cơ chế mã hóa dùng public key recipient, bất kỳ ai có public key đó đều có thể tạo ciphertext gửi cho recipient. Authentication tag của JWE bảo vệ tính toàn vẹn của ciphertext/plaintext theo cơ chế mã hóa có xác thực; nó không tự tạo chữ ký định danh issuer. Nếu cần xác minh nguồn phát hành, phải có chữ ký JWS hoặc một cơ chế xác thực nguồn gốc khác theo profile.

Không nhầm jwk với epk trong các thuật toán ECDH-ES. epk biểu diễn ephemeral public key phục vụ phép thỏa thuận khóa; nó có vai trò và quy tắc riêng.

## 5. JWK cần một trust anchor độc lập

Để tin một public JWK, ứng dụng cần cơ chế độc lập liên kết khóa với danh tính hoặc vai trò được phép. Một số mô hình thường dùng:

| Cơ chế | Cách xác lập tin cậy |
| --- | --- |
| Khóa được cấu hình/pin trước | So sánh JWK hoặc thumbprint với khóa đã được quản trị và gắn với issuer |
| JWKS đã cấu hình cho issuer | Tìm khóa trong JWKS lấy từ nguồn tin cậy đã gắn với issuer; không lấy nguồn từ token |
| PKIX/X.509 | Xác minh certificate chain tới trust anchor, kiểm tra danh tính và xác nhận public key trong JWK khớp public key của certificate |
| Đăng ký khóa ngoài băng | Khóa được đăng ký qua quy trình xác thực danh tính và cấp quyền độc lập với token đang xác minh |
| Ràng buộc khóa trong một giao thức chuyên biệt | Kiểm tra thumbprint/confirmation claim hoặc bằng chứng sở hữu khóa theo đúng profile |

RFC 7517 mục 9.1 nhấn mạnh rằng mức độ tin cậy dành cho dữ liệu được bảo vệ bằng một khóa không thể cao hơn mức tin cậy dành cho cách lấy khóa và thực thể xác nhận mối liên hệ giữa danh tính với khóa.

### Dùng thumbprint để so khớp khóa

RFC 7638 định nghĩa JWK Thumbprint: một fingerprint được tính từ tập thành viên JWK bắt buộc đã chuẩn hóa cho loại khóa tương ứng. Thumbprint có thể được dùng để pin hoặc đối chiếu public key.

Ví dụ khái niệm:

~~~text
expected = configuredThumbprintForIssuer
received = jwkThumbprint(publicJwkFromHeader)

require safeEquality(expected, received)
~~~

Không tính fingerprint bằng cách hash nguyên văn JSON JWK tùy ý, vì thứ tự thuộc tính, khoảng trắng và metadata bổ sung có thể khác nhau. Hãy dùng đúng thuật toán chuẩn hóa và thành viên được RFC 7638 quy định. Thumbprint giúp nhận diện chính xác vật liệu khóa; bản thân thumbprint cũng phải đến từ cấu hình hoặc kênh tin cậy.

## 6. Kiểm tra JWK nhúng trước khi sử dụng

Ngay cả khi public JWK đến từ nguồn tin cậy, ứng dụng vẫn phải kiểm tra cấu trúc và sự phù hợp với chính sách.

### Kiểm tra loại khóa và tham số

- kty phải thuộc loại khóa mà profile cho phép, chẳng hạn RSA, EC hoặc OKP.
- Với EC, kiểm tra crv và các tọa độ public key hợp lệ trên đường cong được phép.
- Với RSA, kiểm tra modulus, public exponent và kích thước khóa theo yêu cầu an toàn hiện hành.
- Với OKP, kiểm tra đúng đường cong/biến thể và độ dài public key.
- Từ chối tham số bắt buộc bị thiếu, sai kiểu, ngoài miền hợp lệ hoặc có encoding không hợp lệ.
- Kiểm tra alg, use và key_ops nếu có; các giá trị này phải tương thích với thao tác dự kiến.
- Allowlist thuật toán phải do ứng dụng cấu hình; không để JWK hoặc JOSE Header tự mở rộng allowlist.

### Chỉ chấp nhận public key trong JOSE Header

Tham số jwk của JWS/JWE mô tả public key theo định nghĩa tương ứng. Không đưa private key hoặc symmetric secret vào một header có thể được truyền, ghi log, lưu trữ hoặc quan sát bởi bên không được phép.

Các thành viên JWK nhạy cảm có thể gồm:

| Loại khóa | Thành viên private/secret cần bảo vệ |
| --- | --- |
| RSA | d, p, q, dp, dq, qi, oth |
| EC | d |
| OKP | d |
| Octet sequence (khóa đối xứng) | k |

Nếu phát hiện private hoặc symmetric key material trong jwk công khai, không sử dụng khóa đó; cần coi đây là sự cố lộ bí mật, đánh giá nơi token đã được gửi/lưu và thực hiện xoay vòng hoặc thu hồi khóa tương ứng.

### Kiểm tra metadata và certificate

Nếu JWK chứa x5c, certificate đầu tiên phải chứa public key tương ứng với các thành viên khóa trong JWK. Nếu ứng dụng dùng certificate để xác lập danh tính, phải kiểm tra chuỗi certificate tới trust anchor, thời hạn, mục đích sử dụng và danh tính theo chính sách. Chỉ thấy x5c trong JWK không có nghĩa certificate đã được tin cậy.

Các metadata như kid, use, key_ops và alg hỗ trợ lựa chọn và giới hạn thao tác; chúng không thay thế trust anchor.

## 7. Bảo vệ và xử lý header trong các serialization

### JWS Compact

JWS Compact không có unprotected header riêng. JOSE Header nằm trong phần protected header và được đưa vào signing input. Tuy nhiên, như đã giải thích, chữ ký có thể được tạo bởi bất kỳ ai sở hữu private key tương ứng với JWK tự nhúng.

### JWS JSON Serialization

JWS JSON Serialization có thể có protected header và unprotected header. RFC 7515 mục 6 quy định các tham số dùng để nhận diện khóa phải được integrity-protected nếu thông tin mà chúng mang được sử dụng trong một quyết định tin cậy. RFC cũng nêu ngoại lệ: nếu thông tin duy nhất được dùng trong quyết định là bản thân khóa, thay đổi tham số khiến một khóa khác được chọn sẽ làm xác minh thất bại.

Trong thiết kế xác thực issuer, nên đặt jwk và mọi metadata nhận diện danh tính/nguồn khóa trong protected header, đồng thời xác minh mối liên hệ với trust anchor độc lập. Không dựa vào giá trị unprotected để quyết định issuer, role hoặc quyền.

### JWE

Trong JWE Compact, protected header được xác thực trong quá trình mã hóa có xác thực. Trong JWE JSON Serialization, có protected header chung, shared unprotected header và header theo recipient. Ứng dụng phải tuân theo đúng phạm vi bảo vệ của từng tham số; metadata dùng trong quyết định tin cậy phải được bảo vệ và ràng buộc với recipient/key policy.

## 8. Quy trình xác minh JWS có jwk an toàn

Giả sử một API chỉ chấp nhận access token do issuer đã cấu hình phát hành. API có thể xử lý như sau:

1. Chọn issuer và profile từ endpoint hoặc cấu hình tin cậy.
2. Parse JWS và protected header theo quy tắc nghiêm ngặt; từ chối JSON sai định dạng hoặc tham số trùng lặp.
3. Kiểm tra alg nằm trong allowlist của profile.
4. Nếu header có jwk, parse như public JWK; từ chối private/secret material và kiểm tra loại khóa/tham số.
5. So khớp JWK với khóa được pin, JWKS tin cậy hoặc cơ chế đăng ký đã xác thực. Nếu không có liên kết tin cậy, không chấp nhận JWK như căn cứ xác thực issuer.
6. Chọn đúng một khóa xác minh phù hợp; không fallback sang thuật toán khác khi kiểm tra thất bại.
7. Xác minh chữ ký JWS.
8. Sau khi chữ ký hợp lệ, kiểm tra iss, aud, exp, nbf, typ, scope/quyền và các claim theo profile.
9. Chỉ tạo ngữ cảnh xác thực và cấp quyền khi mọi điều kiện đều đạt.

~~~mermaid
flowchart TD
    A["Nhận JWS chưa tin cậy"] --> B["Chọn issuer/profile từ cấu hình endpoint"]
    B --> C["Parse protected header và kiểm tra alg"]
    C --> D{"Có jwk nhúng?"}
    D -- Không --> E["Chọn khóa từ nguồn tin cậy đã cấu hình"]
    D -- Có --> F["Parse public JWK và kiểm tra tham số"]
    F --> G{"Có private/secret material?"}
    G -- Có --> X["Từ chối và xử lý sự cố lộ khóa"]
    G -- Không --> H["So khớp thumbprint/khóa với trust anchor"]
    H --> I{"Khóa được tin cậy cho issuer?"}
    I -- Không --> X
    I -- Có --> E
    E --> J["Xác minh chữ ký bằng thuật toán được phép"]
    J --> K{"Chữ ký hợp lệ?"}
    K -- Không --> X
    K -- Có --> L["Kiểm tra iss, aud, thời hạn và profile"]
    L --> M{"Claims hợp lệ?"}
    M -- Không --> X
    M -- Có --> N["Chấp nhận token"]
~~~

Mã giả:

~~~text
function verifyAccessToken(token, endpoint):
    policy = trustedPolicyFor(endpoint)
    jws = parseJwsStrictlyWithLimits(token)
    header = jws.protectedHeader

    require header.alg in policy.allowedAlgorithms

    if header.jwk exists:
        candidate = parsePublicJwk(header.jwk)
        require candidate contains no private or symmetric secret members
        require keyParametersAreValid(candidate)
        require keyMatchesAlgorithmAndPurpose(candidate, header.alg, "verify")
        require thumbprint(candidate) in policy.trustedKeyThumbprints
        key = candidate
    else:
        key = selectTrustedIssuerKey(policy, header.kid, header.alg)

    require key is uniquely bound to policy.expectedIssuer
    claims = verifyJwsSignature(jws, key, [policy.allowedAlgorithm])
    require signatureVerificationSucceeded
    require claims.iss == policy.expectedIssuer
    require policy.expectedAudience in claims.aud
    require timeClaimsAreValid(claims)
    require tokenProfileAndAuthorizationRulesAreSatisfied(claims, header)
    return claims
~~~

Đây là mã giả minh họa. Một profile có thể cấm hoàn toàn jwk trong header và chỉ dùng JWKS đã cấu hình. Nếu profile cho phép JWK nhúng, nó vẫn phải định nghĩa rõ cách liên kết khóa với issuer hoặc danh tính đã đăng ký.

## 9. Trường hợp giao thức chủ động dùng JWK nhúng

Không phải mọi trường hợp nhúng JWK đều là lỗi. Một số giao thức cần public key ngay trong đối tượng để chứng minh quyền sở hữu khóa hoặc hỗ trợ trao đổi khóa. Điều kiện là giao thức phải có **quy tắc ràng buộc khóa với ngữ cảnh tin cậy**.

Ví dụ DPoP (Demonstrating Proof of Possession) dùng một public JWK trong protected header của proof JWT. Resource server không được xem JWK đó như issuer key để xác minh access token. Nó phải kiểm tra proof theo RFC 9449, bao gồm các claim yêu cầu như htm, htu, iat, jti, nonce khi được yêu cầu và ràng buộc thumbprint của public key với access token qua cnf.jkt khi áp dụng.

Đây là ví dụ về cách một giao thức có thể chấp nhận khóa do bên yêu cầu cung cấp nhưng vẫn ràng buộc khóa với quyền hoặc token đã được xác thực. Không được lấy riêng ví dụ DPoP để suy ra rằng mọi JWS có jwk đều đáng tin.

## 10. So sánh jwk, jku, kid và x5c

| Tham số | Dữ liệu mang theo | Vai trò | Điều kiện tin cậy |
| --- | --- | --- | --- |
| jwk | Một JWK trực tiếp trong header | Cung cấp public key tương ứng với chữ ký JWS hoặc public key recipient của JWE | So khớp với trust anchor/khóa đã đăng ký; không tin chỉ vì được nhúng |
| jku | URI tới JWKS | Cho biết nơi có thể lấy tập khóa | Nguồn URI phải được cấu hình/cho phép và truy cập an toàn |
| kid | Chuỗi định danh khóa | Gợi ý chọn khóa trong tập khóa | Chỉ tra cứu trong tập khóa gắn với issuer/ngữ cảnh tin cậy |
| x5c | Chuỗi certificate X.509 | Mang certificate chain chứa public key | Xác minh chain, trust anchor, danh tính và key usage |

Các tham số này có thể hỗ trợ tìm khóa, nhưng không tự tạo ra danh tính đáng tin. Chọn một tham số khác không loại bỏ yêu cầu xác thực nguồn gốc khóa.

## 11. Các lỗi bảo mật thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Xác minh chữ ký bằng bất kỳ JWK nào trong header rồi tin claim | Kẻ tấn công tự tạo khóa, chữ ký và token giả | Chỉ chấp nhận khóa đã được ràng buộc với issuer/danh tính qua trust anchor |
| Nghĩ protected header làm JWK trở nên đáng tin | Chỉ bảo vệ lời khai tự thân của người tạo token | Phân biệt integrity với key provenance |
| Tin iss vì JWK trong cùng token xác minh được chữ ký | Claim issuer và khóa cùng do kẻ tấn công kiểm soát | So khớp issuer với trust configuration độc lập |
| Dùng JWK của JWS để xác minh mọi loại token | Nhầm khóa/thuật toán hoặc mục đích giữa các profile | Ràng buộc khóa với issuer, token type, audience và thuật toán |
| Dùng jwk của JWE như bằng chứng người gửi | Nhầm xác thực recipient/encryption với xác thực nguồn phát hành | Dùng chữ ký hoặc cơ chế xác thực nguồn gốc riêng |
| Cho phép JWK chứa private/symmetric key material | Lộ khóa và có thể bị giả mạo/giải mã | Từ chối, xử lý như sự cố lộ bí mật và xoay vòng khóa |
| Bỏ qua kty, crv, kích thước hoặc tham số khóa | Khóa không an toàn hoặc không tương thích có thể được dùng | Kiểm tra cấu trúc và chính sách mật mã |
| Tin kid, use hoặc alg trong JWK như metadata đã xác thực | Metadata do bên gửi tự khai có thể gây chọn sai khóa | Đối chiếu với chính sách độc lập |
| Dùng x5c mà không xác minh certificate chain | Chấp nhận certificate do attacker tự tạo | Xác minh tới trust anchor và kiểm tra danh tính |
| Fallback sang khóa/thuật toán khác khi JWK không khớp | Mở rộng bề mặt algorithm confusion | Từ chối khi không có một khóa duy nhất phù hợp |

## 12. Bộ ca kiểm thử cho jwk

Giả sử API chỉ nhận access token JWS từ issuer https://identity.example, dùng thuật toán ES256 và có một public key đã đăng ký/pin.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Không có jwk, khóa lấy từ JWKS tin cậy, chữ ký và claims hợp lệ | **Chấp nhận** |
| jwk nhúng có thumbprint khớp khóa đã pin, public key hợp lệ, chữ ký và claims hợp lệ | **Chấp nhận** nếu profile cho phép jwk |
| jwk nhúng là khóa do attacker tạo, chữ ký đúng bằng khóa đó, iss khai issuer hợp lệ | **Từ chối** vì khóa không gắn với issuer tin cậy |
| JWK hợp lệ về cú pháp nhưng không có trong trust store/JWKS đã cấu hình | **Từ chối** |
| JWK có thumbprint khác khóa đã đăng ký | **Từ chối** |
| JWK dùng kty RSA trong khi profile chỉ cho ES256 | **Từ chối** |
| JWK EC dùng đường cong khác P-256 | **Từ chối** |
| JWK thiếu tọa độ public key hoặc có tham số ngoài miền hợp lệ | **Từ chối** |
| JWK chứa d hoặc thành viên private RSA | **Từ chối** và xử lý sự cố lộ khóa |
| JWK chứa k của khóa đối xứng | **Từ chối** và xử lý sự cố lộ secret |
| JWK khai use enc nhưng dùng để xác minh chữ ký | **Từ chối** |
| JWK có key_ops không cho phép verify | **Từ chối** |
| JWS JSON đặt metadata định danh issuer trong unprotected header | **Từ chối** theo profile yêu cầu bảo vệ metadata |
| JWE mang JWK recipient không khớp bất kỳ private key recipient được phép | **Từ chối** |
| JWE giải mã được nhưng ứng dụng yêu cầu xác thực issuer mà không có chữ ký/cơ chế xác thực nguồn | **Từ chối** |
| JWS có jwk đúng nhưng sai iss, aud hoặc hết hạn | **Từ chối** |

Các kiểm thử phải xác nhận rằng việc chữ ký thành công bằng một khóa tự cung cấp không tự tạo danh tính đã xác thực hoặc quyền truy cập. Không được phát hành authenticated context trước khi hoàn tất kiểm tra nguồn gốc khóa và claims.

## 13. Ghi nhớ

- jwk nhúng một JWK vào JOSE Header; trong JWS, nó là public key tương ứng với khóa ký; trong JWE, nó là public key recipient mà JWE được mã hóa tới.
- Public JWK có thể giúp xác minh chữ ký hoặc chọn khóa giải mã, nhưng **không tự xác nhận danh tính issuer/người gửi**.
- Kẻ tấn công có thể tự tạo cặp khóa, nhúng public key và ký token; chữ ký hợp lệ chỉ chứng minh quyền sử dụng private key tương ứng.
- Chỉ tin JWK khi khóa được liên kết với issuer/danh tính qua cấu hình, JWKS tin cậy, certificate chain hoặc cơ chế đăng ký/ràng buộc khóa phù hợp.
- Không đưa private key hoặc symmetric secret vào JOSE Header; phát hiện chúng là dấu hiệu lộ khóa cần xử lý.
- Kiểm tra kty, tham số khóa, alg, use, key_ops, thumbprint và profile trước khi sử dụng.
- Với JWE, giải mã thành công không thay thế xác thực nguồn phát hành.

### Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS), mục 4.1.3, 6 và 10.3](https://www.rfc-editor.org/rfc/rfc7515): jwk trong JWS, nhận diện khóa và xác thực nguồn gốc khóa.
- [RFC 7516 — JSON Web Encryption (JWE), mục 4.1.5 và 6](https://www.rfc-editor.org/rfc/rfc7516): jwk trong JWE và nhận diện public key recipient.
- [RFC 7517 — JSON Web Key (JWK), mục 4 và 9.1–9.2](https://www.rfc-editor.org/rfc/rfc7517): cấu trúc JWK, nguồn gốc/độ tin cậy của khóa và bảo vệ private key material.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): cách tính thumbprint chuẩn hóa cho JWK.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT theo issuer, loại token và ngữ cảnh tin cậy.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): public JWK trong DPoP proof và ràng buộc khóa proof với access token.
