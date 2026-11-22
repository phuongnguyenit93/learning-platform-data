# x5t và dấu vân tay chứng thư khi hồ sơ ứng dụng có sử dụng

## 1. x5t là gì?

JOSE Header Parameter **x5t** là dấu vân tay (thumbprint) của một chứng thư X.509. Giá trị này được tạo bằng cách tính SHA-1 trên dữ liệu DER của chứng thư, sau đó mã hóa digest bằng Base64URL. Nó cho phép bên nhận đối chiếu chứng thư được dùng trong một đối tượng JWS hoặc JWE với một giá trị định danh ngắn trong header.

JOSE còn định nghĩa **x5t#S256**, dùng SHA-256 thay cho SHA-1. Hai tham số đều định danh chứng thư bằng fingerprint, nhưng sử dụng hàm băm khác nhau.

Ví dụ protected header:

~~~json
{
  "alg": "PS256",
  "x5t#S256": "<base64url-sha256-certificate-thumbprint>"
}
~~~

Các giá trị minh họa không phải thumbprint thực tế.

Điểm quan trọng: x5t và x5t#S256 là **định danh chứng thư**, không phải chữ ký, không phải public key và không phải bằng chứng độc lập rằng chứng thư đáng tin. Bên nhận vẫn phải xác minh chứng thư theo chính sách tin cậy của mình.

Bài học này áp dụng cho bảo mật JOSE/JWT tổng quát, không phụ thuộc Java, Spring Security hay nền tảng triển khai.

## 2. Cách tạo certificate thumbprint

Đầu vào để tính x5t/x5t#S256 là **toàn bộ chứng thư X.509 được mã hóa DER**:

1. Lấy chứng thư X.509 tương ứng với khóa đang được tham chiếu.
2. Chuyển chứng thư về dữ liệu DER chuẩn.
3. Tính SHA-1 để tạo x5t hoặc SHA-256 để tạo x5t#S256.
4. Mã hóa các byte digest bằng Base64URL theo JOSE, không thêm dấu padding '='.

Biểu thức khái niệm:

~~~text
x5t       = BASE64URL(SHA-1(DER(certificate)))
x5t#S256  = BASE64URL(SHA-256(DER(certificate)))
~~~

Đây không phải phép băm trên:

- Nội dung PEM nguyên văn, bao gồm dòng BEGIN/END CERTIFICATE và ký tự xuống dòng.
- Chỉ riêng public key hoặc SubjectPublicKeyInfo (SPKI).
- JSON JWK hoặc JWKS.
- Toàn bộ chuỗi chứng thư ghép thành một file, trừ khi một profile riêng định nghĩa cách làm khác.

Nếu nguồn chứng thư là PEM, cần parse PEM và lấy chứng thư DER tương ứng trước khi băm. Việc tính trực tiếp trên văn bản PEM có thể tạo thumbprint khác với giá trị mà JOSE quy định.

### Ví dụ mã giả

~~~text
function certificateThumbprint(certificate, hashAlgorithm):
    derBytes = encodeCertificateAsDer(certificate)
    digest = hash(hashAlgorithm, derBytes)
    return base64urlEncodeWithoutPadding(digest)

sha1Thumbprint = certificateThumbprint(cert, "SHA-1")
sha256Thumbprint = certificateThumbprint(cert, "SHA-256")
~~~

Đây là mô tả thuật toán, không phải API của một thư viện cụ thể. Hàm Base64URL phải dùng đúng quy tắc JOSE; không thay bằng Base64 thông thường có dấu '+'/'/' và padding.

## 3. Phân biệt x5t và x5t#S256

| Tham số | Hàm băm | Đầu vào | Kết quả |
| --- | --- | --- | --- |
| x5t | SHA-1 | DER của một chứng thư X.509 | Base64URL của digest SHA-1 |
| x5t#S256 | SHA-256 | DER của một chứng thư X.509 | Base64URL của digest SHA-256 |

### Vì sao có cả hai?

x5t được định nghĩa trong các RFC JOSE ban đầu nhằm hỗ trợ nhận diện chứng thư. SHA-1 hiện không còn phù hợp cho các mục đích cần khả năng chống va chạm mạnh. Để thiết kế mới, nên ưu tiên x5t#S256 khi các bên tham gia hỗ trợ.

x5t vẫn có thể xuất hiện vì tương thích với hệ thống hoặc profile cũ. Nếu cần hỗ trợ nó, hãy giới hạn phạm vi sử dụng và không xem nó là bằng chứng mật mã đủ mạnh để thiết lập niềm tin hoặc cấp quyền.

Không được nhầm việc dùng SHA-1 để tạo certificate thumbprint với việc dùng SHA-1 làm thuật toán chữ ký số. Hai thao tác có mục đích khác nhau, nhưng rủi ro va chạm của SHA-1 vẫn khiến x5t không phù hợp làm căn cứ bảo mật duy nhất trong hệ thống mới.

## 4. x5t xác định chứng thư, không xác định riêng public key

Đây là khác biệt rất quan trọng giữa certificate thumbprint và JWK thumbprint:

| Giá trị | Đối tượng được định danh | Cách tính |
| --- | --- | --- |
| x5t | Một chứng thư X.509 cụ thể | SHA-1 trên DER certificate |
| x5t#S256 | Một chứng thư X.509 cụ thể | SHA-256 trên DER certificate |
| JWK Thumbprint | Các thành phần khóa bắt buộc của JWK | Chuẩn hóa tập thành viên JWK theo RFC 7638 rồi băm |
| SPKI fingerprint | Biểu diễn SubjectPublicKeyInfo của public key | Băm dữ liệu DER SPKI theo quy ước của hệ thống |

Một public key có thể được cấp trong nhiều chứng thư khác nhau. Chẳng hạn, issuer tái cấp chứng thư với serial number, thời hạn, issuer CA hoặc extension khác, nhưng giữ nguyên public key. Vì x5t băm toàn bộ DER certificate, thumbprint sẽ thay đổi dù public key không đổi.

Ngược lại, cùng một chứng thư DER sẽ luôn cho cùng thumbprint khi dùng cùng hàm băm. Vì vậy:

- Dùng x5t/x5t#S256 để nhận diện **đúng chứng thư**.
- Dùng JWK thumbprint hoặc SPKI fingerprint khi mục tiêu là nhận diện vật liệu public key theo định dạng tương ứng.
- Không thay thế các loại fingerprint cho nhau nếu profile không định nghĩa rõ.

## 5. Vai trò của x5t trong JWS

Trong JWS, x5t hoặc x5t#S256 có thể giúp bên nhận nhận diện chứng thư chứa public key tương ứng với private key đã ký JWS.

Ví dụ:

~~~json
{
  "alg": "PS256",
  "kid": "issuer-signing-2026-02",
  "x5t#S256": "<certificate-thumbprint>",
  "typ": "JWT"
}
~~~

Bên xác minh có thể dùng thumbprint để tìm chứng thư trong một kho chứng thư đã được cấu hình, hoặc đối chiếu với chứng thư được cung cấp qua x5c/x5u. Sau khi tìm thấy, nó phải tiếp tục xác minh:

1. Thumbprint khớp chính xác chứng thư DER đã parse.
2. Chứng thư nằm trong chuỗi PKIX dẫn tới trust anchor được cấu hình.
3. Danh tính chứng thư được phép ký token cho issuer đang xử lý.
4. Key Usage, Extended Key Usage, thời hạn, trạng thái thu hồi và thuật toán phù hợp.
5. Chữ ký JWS thực sự hợp lệ bằng public key trong chứng thư.
6. Các claim JWT như iss, aud, exp, nbf và typ đáp ứng profile.

Một thumbprint khớp chỉ xác nhận rằng bên nhận đã tìm đúng chứng thư theo fingerprint. Nó không chứng minh chứng thư được CA tin cậy phát hành hoặc chủ thể có quyền ký token cho issuer.

## 6. Vai trò của x5t trong JWE

Trong JWE, x5t/x5t#S256 liên quan tới chứng thư chứa public key được dùng trong thao tác quản lý khóa, thường là chứng thư của recipient. Nó có thể giúp recipient xác định chứng thư hoặc khóa tương ứng với đối tượng JWE.

Ví dụ:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "x5t#S256": "<recipient-certificate-thumbprint>"
}
~~~

Recipient có thể dùng thumbprint để tìm chứng thư và xác định private key phù hợp trong kho khóa được quản trị. Tuy nhiên:

- Không chọn private key chỉ vì token đưa ra một thumbprint bất kỳ.
- Phải đối chiếu với danh sách khóa recipient được phép và đúng ngữ cảnh/tenant.
- Kiểm tra loại khóa, thuật toán quản lý khóa, mục đích sử dụng và trạng thái khóa.
- Xác thực tag và giải mã JWE thành công vẫn không tự chứng minh danh tính người gửi.

Nếu plaintext cần bằng chứng về issuer, giao thức phải dùng chữ ký JWS lồng trong JWE hoặc cơ chế xác thực nguồn gốc khác.

## 7. Kết hợp x5t với x5c, x5u và kid

Các tham số JOSE có thể bổ trợ cho nhau:

| Tham số | Vai trò |
| --- | --- |
| x5c | Mang trực tiếp chuỗi chứng thư X.509 dạng Base64 DER |
| x5u | Tham chiếu URI tới tài nguyên chuỗi chứng thư dạng PEM |
| x5t | Fingerprint SHA-1 của một chứng thư DER |
| x5t#S256 | Fingerprint SHA-256 của một chứng thư DER |
| kid | Định danh khóa theo quy ước của tập khóa |

Ví dụ một header có thể chứa cả x5c và x5t#S256:

~~~json
{
  "alg": "PS256",
  "x5c": [
    "<base64-DER-leaf-certificate>",
    "<base64-DER-intermediate-certificate>"
  ],
  "x5t#S256": "<sha256-thumbprint-of-leaf-certificate>"
}
~~~

Trong ví dụ này, thumbprint phải được tính trên DER của chứng thư leaf đứng đầu mảng x5c, là chứng thư chứa public key tương ứng với khóa ký JWS.

Nếu một profile cho phép nhiều nguồn chứng thư cùng xuất hiện, nó phải quy định rõ cách đối chiếu. Một cách xử lý an toàn là tính thumbprint trên chứng thư lấy từ x5c/x5u rồi so với x5t/x5t#S256; nếu không khớp thì từ chối. Không tự động ưu tiên một nguồn để bỏ qua mâu thuẫn ở nguồn còn lại.

### x5t không thay thế kid

x5t là fingerprint của chứng thư, trong khi kid là định danh do hệ thống phát hành quy ước. Một issuer có thể dùng kid để quản lý khóa qua các lần xoay vòng và dùng x5t#S256 để xác nhận chính xác chứng thư tương ứng. Không giả định kid luôn chứa thumbprint hoặc được tính từ chứng thư.

## 8. x5t không phải trust anchor

Một giá trị thumbprint có thể được tính từ chứng thư tự ký hoặc chứng thư do kẻ tấn công tạo. Nếu ứng dụng chỉ kiểm tra rằng thumbprint khớp với chứng thư trong token rồi chấp nhận token, kẻ tấn công vẫn có thể tạo chứng thư và chữ ký của riêng họ.

Để x5t trở thành một phần của quyết định tin cậy, giá trị mong đợi phải đến từ một nguồn tin cậy độc lập, ví dụ:

- Cấu hình pin certificate thumbprint đã được quản trị.
- Metadata issuer đã được xác minh, liên kết với chứng thư cụ thể.
- Kho chứng thư/JWKS đã được gắn với issuer và phân phối qua kênh tin cậy.
- Quy trình đăng ký chứng thư ngoài băng đã xác thực danh tính chủ thể.

Ngay cả khi thumbprint đã được pin, vẫn cần kiểm tra các điều kiện profile như thời hạn chứng thư, mục đích sử dụng, thu hồi và thuật toán. Pinning không tự thay thế toàn bộ quy trình xác minh chứng thư.

## 9. SHA-1 và rủi ro va chạm của x5t

SHA-1 có các tấn công va chạm đã biết. Với hai đầu vào khác nhau được tạo có chủ đích, kẻ tấn công có thể tìm cách làm cho digest giống nhau. Vì x5t dùng SHA-1 trên DER certificate, không nên dùng x5t làm căn cứ duy nhất để quyết định một chứng thư mới có tương đương với chứng thư đã tin cậy hay không.

Các nguyên tắc:

1. Ưu tiên x5t#S256 cho profile mới.
2. Nếu phải hỗ trợ x5t vì tương thích, kết hợp với xác minh PKIX và mapping danh tính; không dùng SHA-1 thumbprint làm trust anchor duy nhất.
3. Không cho phép token tự khai x5t rồi tự cung cấp chứng thư tương ứng để xác lập niềm tin.
4. Khi profile hỗ trợ cả x5t và x5t#S256, quy định rõ tham số nào được ưu tiên và cách xử lý khi cả hai cùng xuất hiện nhưng không khớp.
5. Không hạ cấp từ x5t#S256 sang x5t chỉ vì giá trị SHA-256 bị thiếu hoặc không khớp.

SHA-256 hiện được dùng rộng rãi cho fingerprint certificate. Tuy nhiên, ngay cả x5t#S256 cũng chỉ là fingerprint; một giá trị do người gửi tự khai không tự chứng minh quyền sở hữu hay danh tính.

## 10. Bảo vệ thumbprint trong JOSE Header

x5t và x5t#S256 là thông tin nhận diện khóa/chứng thư. Nếu ứng dụng dùng chúng để chọn chứng thư, khóa hoặc quyết định tin cậy, cần bảo đảm header parameter được integrity-protected theo quy tắc JOSE.

- Trong JWS Compact, protected header là một phần của signing input.
- Trong JWE Compact, protected header được xác thực như một phần của AAD.
- Trong JSON Serialization, phải xét rõ protected và unprotected header. Không dùng giá trị thumbprint ở unprotected header để thay đổi quyết định tin cậy nếu giá trị đó không được bảo vệ theo profile.

Integrity protection chỉ ngăn sửa đổi sau khi token được tạo. Nó không chứng minh người tạo token có danh tính đáng tin. Một attacker vẫn có thể tự tạo header, thumbprint và chữ ký bằng khóa của họ.

## 11. Xoay vòng chứng thư và thumbprint

Khi issuer cấp lại chứng thư, x5t và x5t#S256 sẽ thay đổi nếu DER certificate thay đổi, kể cả khi public key vẫn giống nhau. Vì thế, quy trình rollover cần phân biệt thay khóa và cấp lại chứng thư.

Ví dụ:

~~~mermaid
flowchart TD
    A["Issuer đang dùng certificate-old / thumbprint-old"] --> B["Cấp certificate-new"]
    B --> C["Tính thumbprint mới trên DER certificate"]
    C --> D["Đăng ký/công bố certificate-new và thumbprint-new qua kênh tin cậy"]
    D --> E["Bên xác minh cập nhật trust mapping/cache"]
    E --> F["Issuer bắt đầu dùng certificate-new"]
    F --> G["Giữ certificate-old trong thời gian token cũ còn hiệu lực"]
    G --> H["Hết thời hạn token cũ và khoảng đệm"]
    H --> I["Gỡ certificate-old theo chính sách"]
~~~

Quy trình nên bao gồm:

1. Tạo hoặc cấp chứng thư mới và xác minh chain/danh tính trước khi sử dụng.
2. Tính x5t#S256 từ DER certificate mới.
3. Cập nhật metadata, pinset hoặc trust mapping qua kênh quản trị đáng tin cậy.
4. Cho bên xác minh thời gian cập nhật cache trước khi issuer phát hành token mới bằng chứng thư đó.
5. Duy trì chứng thư cũ trong thời gian cần xác minh token còn hiệu lực, trừ khi có sự cố thu hồi khẩn cấp.
6. Gỡ pin/chứng thư cũ khi token cũ hết hạn và các khoảng đệm vận hành đã kết thúc.

Nếu chứng thư mới giữ nguyên public key, JWK thumbprint hoặc SPKI fingerprint có thể không đổi, nhưng certificate thumbprint vẫn thay đổi. Nếu thay cả khóa lẫn chứng thư, cần cập nhật cả ánh xạ khóa và thumbprint.

## 12. Quy trình kiểm tra x5t/x5t#S256

Giả sử API nhận JWS và profile quy định x5t#S256 phải khớp chứng thư leaf đã được pin cho issuer:

1. Chọn issuer/profile từ cấu hình tin cậy, không từ thumbprint do token tự khai.
2. Parse JOSE Header nghiêm ngặt và kiểm tra thuật toán thuộc allowlist.
3. Lấy chứng thư từ kho đã cấu hình hoặc x5c/x5u được profile cho phép.
4. Parse chứng thư và lấy DER bytes của leaf certificate.
5. Tính SHA-256 trên DER bytes, mã hóa digest bằng Base64URL không padding.
6. So sánh với x5t#S256 trong protected header và giá trị pin/trust mapping đã cấu hình.
7. Xác minh PKIX chain, danh tính issuer, validity, revocation, Key Usage/EKU và thuật toán khóa.
8. Xác minh chữ ký JWS bằng public key của leaf certificate.
9. Kiểm tra iss, aud, exp, nbf, typ và các claim theo profile.
10. Chỉ chấp nhận token khi mọi điều kiện đều đạt.

~~~mermaid
flowchart TD
    A["Nhận JWS"] --> B["Chọn issuer/profile tin cậy"]
    B --> C["Parse protected header"]
    C --> D["Lấy chứng thư từ nguồn được phép"]
    D --> E["Parse certificate và lấy DER"]
    E --> F["Tính SHA-256 và Base64URL"]
    F --> G{"Khớp x5t#S256 và pin đã cấu hình?"}
    G -- Không --> X["Từ chối"]
    G -- Có --> H["Xác minh PKIX, danh tính và key usage"]
    H --> I{"Chứng thư hợp lệ?"}
    I -- Không --> X
    I -- Có --> J["Xác minh chữ ký JWS"]
    J --> K{"Chữ ký hợp lệ?"}
    K -- Không --> X
    K -- Có --> L["Kiểm tra claims và token profile"]
    L --> M{"Claims hợp lệ?"}
    M -- Không --> X
    M -- Có --> N["Chấp nhận"]
~~~

Mã giả:

~~~text
function verifyCertificateBoundJws(token, policy):
    jws = parseJwsStrictlyWithLimits(token)
    header = jws.protectedHeader

    require header.alg in policy.allowedAlgorithms
    require header.x5tS256 exists

    certificate = selectCertificateFromTrustedSource(header, policy)
    der = encodeCertificateAsDer(certificate)
    calculated = base64urlEncodeWithoutPadding(SHA256(der))

    require safeEquality(calculated, header.x5tS256)
    require safeEquality(calculated, policy.pinnedThumbprint)
    require validatePkixAndCertificateIdentity(certificate, policy)
    require keyUsageAllows(certificate, "digitalSignature")

    claims = verifyJwsSignature(jws, certificate.publicKey, [policy.allowedAlgorithm])
    require signatureVerificationSucceeded
    require claims.iss == policy.expectedIssuer
    require policy.expectedAudience in claims.aud
    require timeClaimsAreValid(claims)
    return claims
~~~

Đây là mã giả cho một profile yêu cầu x5t#S256. Profile khác có thể không yêu cầu thumbprint hoặc có thể sử dụng x5t vì tương thích; chính sách phải nêu rõ thuật toán fingerprint và nguồn chứng thư được tin cậy.

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tính thumbprint trên văn bản PEM | Giá trị khác với thumbprint JOSE | Parse PEM và băm DER certificate |
| Tính trên public key/JWK thay vì certificate | Nhầm certificate thumbprint với key thumbprint | Dùng đúng đầu vào DER của chứng thư |
| Chỉ so x5t rồi tin chứng thư | Chứng thư tự ký hoặc không thuộc issuer vẫn có thể được chấp nhận | Xác minh trust anchor, danh tính và mục đích |
| Dùng SHA-1 x5t làm trust anchor duy nhất | Rủi ro va chạm SHA-1 ảnh hưởng quyết định tin cậy | Ưu tiên x5t#S256 và xác minh chứng thư độc lập |
| Coi x5t#S256 là bằng chứng issuer | Fingerprint không xác thực chủ thể hoặc quyền ký | Liên kết chứng thư với issuer qua trust configuration |
| Không phân biệt x5t với JWK thumbprint | So sánh sai dữ liệu hoặc dùng sai thuật toán | Xác định rõ đối tượng được định danh |
| Không cập nhật pin khi cấp lại chứng thư | Token hợp lệ dùng chứng thư mới bị từ chối | Có quy trình certificate rollover |
| Tái sử dụng pin cũ sau khi chứng thư bị thu hồi | Chứng thư không còn được phép có thể tiếp tục được tin | Cập nhật thu hồi/pinset và cache khẩn cấp |
| Dùng thumbprint unprotected để chọn khóa | Giá trị có thể bị thay đổi ngoài cơ chế bảo vệ | Yêu cầu integrity protection theo profile |
| Chấp nhận khi x5c và x5t mâu thuẫn | Header chỉ tới chứng thư khác với chứng thư được cung cấp | So khớp fingerprint với chứng thư thực tế; từ chối nếu khác |

## 14. Bộ ca kiểm thử

Giả sử API chỉ chấp nhận JWS PS256 từ issuer đã cấu hình và profile yêu cầu x5t#S256 khớp chứng thư leaf đã pin.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| x5t#S256 được tính đúng trên DER leaf, chứng thư được tin cậy, chữ ký và claims hợp lệ | **Chấp nhận** |
| x5t#S256 tính trên PEM text thay vì DER | **Từ chối** |
| x5t#S256 tính trên JWK/SPKI thay vì certificate | **Từ chối** |
| Thumbprint không khớp chứng thư trong x5c | **Từ chối** |
| Thumbprint khớp chứng thư nhưng certificate chain không tới trust anchor | **Từ chối** |
| Thumbprint khớp nhưng SAN/identity không thuộc issuer dự kiến | **Từ chối** |
| Chứng thư hết hạn hoặc bị thu hồi theo policy | **Từ chối** |
| Chứng thư không cho phép digitalSignature theo profile | **Từ chối** |
| x5t#S256 đúng nhưng chữ ký JWS sai | **Từ chối** |
| x5t SHA-1 đúng nhưng profile chỉ cho phép x5t#S256 | **Từ chối** |
| x5t#S256 sai nhưng x5t SHA-1 khớp | **Từ chối**, không downgrade |
| x5c và x5t#S256 chỉ tới hai chứng thư khác nhau | **Từ chối** |
| Chứng thư mới cùng public key nhưng DER thay đổi và pin chưa được cập nhật | **Từ chối** cho đến khi rollover được quản trị |
| Chứng thư mới đã được pin qua kênh tin cậy, chain/claims/chữ ký hợp lệ | **Chấp nhận** |
| JWE thumbprint chỉ đúng certificate recipient nhưng ứng dụng cần xác thực sender | Không coi là bằng chứng sender; yêu cầu cơ chế xác thực nguồn gốc |

## 15. Ghi nhớ

- x5t là Base64URL(SHA-1(DER certificate)); x5t#S256 là Base64URL(SHA-256(DER certificate)).
- Đầu vào là toàn bộ chứng thư DER, không phải PEM text, JWK JSON, SPKI hay toàn bộ chain.
- x5t/x5t#S256 định danh một chứng thư cụ thể; cấp lại chứng thư có thể làm thumbprint đổi dù public key giữ nguyên.
- x5t#S256 nên được ưu tiên cho profile mới; x5t chỉ nên duy trì khi cần tương thích và không dùng làm căn cứ tin cậy duy nhất.
- Thumbprint khớp không thay thế PKIX path validation, issuer identity binding, Key Usage/EKU, revocation hay xác minh chữ ký.
- Trong JWS, thumbprint liên quan chứng thư chứa public key ký; trong JWE, nó thường liên quan chứng thư public key recipient.
- Nếu profile dùng thumbprint để chọn khóa hoặc quyết định tin cậy, phải bảo vệ header parameter theo quy tắc JOSE.
- Quản lý rollover phải cập nhật pin/trust mapping trước khi phát hành token bằng chứng thư mới và giữ chứng thư cũ theo vòng đời token.

### Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS), mục 4.1.7 và 4.1.8](https://www.rfc-editor.org/rfc/rfc7515): x5t và x5t#S256 trong JWS.
- [RFC 7516 — JSON Web Encryption (JWE), mục 4.1.9 và 4.1.10](https://www.rfc-editor.org/rfc/rfc7516): x5t và x5t#S256 trong JWE.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và metadata khóa.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): phân biệt fingerprint JWK với certificate thumbprint.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): chứng thư X.509 và xác minh chuỗi PKIX.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT theo issuer, thuật toán, khóa và ngữ cảnh.
