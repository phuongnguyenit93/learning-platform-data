# x5c, x5u và quan hệ giữa chứng thư với quyết định tin cậy

## 1. Vai trò của x5c và x5u trong JOSE

JSON Web Signature (JWS) và JSON Web Encryption (JWE) có thể mang thông tin chứng thư X.509 trong JOSE Header để giúp bên nhận xác định khóa công khai liên quan đến một thao tác mật mã.

Hai tham số thường gặp là:

- **x5c**: nhúng một chuỗi chứng thư X.509 ngay trong JOSE Header. Mỗi chứng thư được biểu diễn bằng Base64 của dữ liệu DER.
- **x5u**: cung cấp URI trỏ tới tài nguyên chứa chứng thư X.509 hoặc chuỗi chứng thư. Tài nguyên được tham chiếu dùng biểu diễn PEM.

Các tham số này có thể giúp bên nhận lấy hoặc nhận diện khóa, nhưng **sự hiện diện của một chứng thư không tự động làm cho chứng thư hoặc người sở hữu nó trở nên đáng tin**. Bên nhận phải xác minh chuỗi chứng thư, danh tính, mục đích sử dụng khóa và mối liên hệ giữa chứng thư với issuer/recipient đang được mong đợi.

Bài học này thuộc phạm vi bảo mật JOSE/JWT tổng quát, không phụ thuộc Java, Spring Security hay nền tảng triển khai.

## 2. x5c: nhúng chuỗi chứng thư X.509

Theo RFC 7515, tham số x5c trong JWS có giá trị là một mảng các chuỗi Base64, mỗi chuỗi biểu diễn một chứng thư X.509 ở dạng DER. RFC 7516 định nghĩa cách dùng tương tự trong JWE.

Ví dụ protected header của JWS:

~~~json
{
  "alg": "PS256",
  "x5c": [
    "<base64-DER-leaf-certificate>",
    "<base64-DER-intermediate-certificate>"
  ]
}
~~~

Quy tắc thứ tự:

1. Phần tử đầu tiên phải là chứng thư chứa public key tương ứng với khóa đã dùng để ký JWS.
2. Các phần tử tiếp theo có thể là chứng thư dùng để chứng thực cho chứng thư đứng ngay trước nó.
3. Root CA không nhất thiết phải được gửi trong mảng; bên nhận thường có trust anchor riêng trong trust store.

Với JWE, chứng thư đầu tiên tương ứng với public key được dùng trong thao tác quản lý khóa để bảo vệ CEK, ví dụ khóa công khai của recipient dùng cho RSA-OAEP. Recipient có thể dùng thông tin này để tìm khóa riêng tương ứng, nhưng phải đối chiếu với khóa recipient mà nó thực sự quản lý.

### DER và Base64 không phải PEM

Trong x5c, mỗi phần tử là Base64 của chứng thư DER. Đây không phải chuỗi PEM có các dòng:

~~~text
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
~~~

Khi xử lý x5c, bên nhận phải Base64-decode từng phần tử rồi parse dữ liệu DER theo định dạng X.509. Không coi một chuỗi PEM nguyên văn là giá trị x5c hợp lệ nếu chưa chuyển đổi đúng định dạng.

## 3. x5u: tham chiếu tới tài nguyên chứng thư từ xa

Tham số x5u là URI tham chiếu tới tài nguyên chứa chứng thư X.509 hoặc chuỗi chứng thư tương ứng với khóa dùng trong JWS/JWE.

Ví dụ:

~~~json
{
  "alg": "PS256",
  "x5u": "https://identity.example/certificates/signing-chain.pem"
}
~~~

Theo đặc tả JOSE, tài nguyên được tham chiếu cung cấp biểu diễn PEM của chứng thư hoặc chuỗi chứng thư. Khi lấy tài nguyên, giao thức truyền tải phải bảo vệ tính toàn vẹn; TLS được khuyến nghị và danh tính máy chủ phải được xác minh theo quy tắc xác thực tên máy chủ TLS.

Với x5u, có hai đối tượng chứng thư khác nhau cần phân biệt:

| Chứng thư | Vai trò | Cách xác minh |
| --- | --- | --- |
| Chứng thư TLS của máy chủ x5u | Xác thực máy chủ đang cung cấp tài nguyên PEM và bảo vệ kết nối | Kiểm tra TLS chain, hostname/service identity, thời hạn và chính sách TLS |
| Chứng thư X.509 được tải từ x5u | Mang public key liên quan đến chữ ký JWS hoặc thao tác khóa của JWE | Kiểm tra chuỗi PKIX, trust anchor, danh tính và mục đích sử dụng khóa |

TLS hợp lệ chỉ chứng minh kết nối tới đúng máy chủ của URI đang truy cập. Nó **không chứng minh URI đó thuộc issuer được ứng dụng tin cậy**. Một domain do kẻ tấn công sở hữu vẫn có thể có chứng thư TLS hợp lệ cho chính domain đó.

### Khi x5c và x5u cùng xuất hiện

Một JOSE Header có thể mang nhiều tham số nhận diện chứng thư. Nếu profile cho phép cả x5c và x5u cùng xuất hiện, bên nhận cần quy định rõ cách xử lý. Thực hành an toàn là xác minh rằng chuỗi chứng thư lấy từ hai nguồn biểu diễn cùng leaf certificate/public key; nếu không khớp, từ chối. Không âm thầm chọn nguồn nào thuận tiện hơn hoặc dùng nguồn này để ghi đè nguồn kia. Một profile đơn giản hơn có thể chỉ cho phép một trong hai tham số.

## 4. Chứng thư có mặt không đồng nghĩa với chứng thư đáng tin

Một chứng thư X.509 chứa public key và thông tin được CA hoặc chủ thể tự ký xác nhận. Nhưng một chứng thư có thể:

- Được tạo bởi bất kỳ ai, kể cả kẻ tấn công.
- Được ký bởi CA không nằm trong trust store của ứng dụng.
- Đã hết hạn hoặc chưa đến thời điểm có hiệu lực.
- Đã bị thu hồi.
- Có tên chủ thể không liên quan tới issuer đang được mong đợi.
- Có Key Usage hoặc Extended Key Usage không phù hợp với thao tác JOSE.
- Chứa khóa yếu, thuật toán/chữ ký chứng thư không được chính sách cho phép.

Vì vậy, không được chấp nhận JWS chỉ vì x5c có chứng thư parse được, hoặc vì x5u trả về một file PEM hợp lệ.

Một quyết định tin cậy thường cần trả lời đủ các câu hỏi:

1. Chuỗi chứng thư có thể xây dựng và xác minh tới một trust anchor được cấu hình hay không?
2. Chứng thư cuối (leaf/end-entity) có còn hiệu lực và không bị thu hồi theo chính sách hay không?
3. Danh tính được chứng thư xác nhận có đúng issuer, tenant hoặc thực thể được phép phát hành token hay không?
4. Public key trong chứng thư có đúng loại và phù hợp với thuật toán JOSE hay không?
5. Key Usage, Extended Key Usage và các ràng buộc profile có cho phép thao tác đang thực hiện hay không?
6. Sau khi chọn khóa, chữ ký JWS hoặc thao tác JWE có hợp lệ không?
7. Claims của JWT có đúng issuer, audience, thời hạn và mục đích sử dụng không?

## 5. Xác minh chuỗi chứng thư theo PKIX

Chuỗi chứng thư thường có cấu trúc:

~~~text
End-entity certificate (leaf)
    được ký bởi Intermediate CA
        được ký bởi Root CA / trust anchor
~~~

Việc xác minh chuỗi không chỉ là kiểm tra chữ ký của leaf certificate. Bên nhận cần thực hiện path validation theo RFC 5280 với trust anchor lấy từ cấu hình đáng tin cậy.

Các kiểm tra quan trọng gồm:

- **Chữ ký và đường dẫn:** xác minh chữ ký của từng chứng thư theo đường dẫn tới trust anchor phù hợp.
- **Basic Constraints:** xác nhận CA certificate có quyền phát hành chứng thư con; leaf không được tự coi là CA nếu không được cho phép.
- **Path Length Constraint:** giới hạn số tầng CA trung gian theo chứng thư.
- **Validity:** kiểm tra Not Before và Not After theo thời gian hiện tại, có xử lý clock skew theo chính sách.
- **Name Constraints:** áp dụng giới hạn namespace/domain/IP nếu chuỗi chứng thư có quy định.
- **Certificate Policies:** kiểm tra policy OID nếu ứng dụng/profile yêu cầu.
- **Key Usage:** kiểm tra thao tác khóa được chứng thư cho phép.
- **Extended Key Usage:** kiểm tra mục đích chuyên biệt nếu profile hoặc chính sách triển khai yêu cầu.
- **Revocation:** kiểm tra trạng thái thu hồi qua CRL, OCSP hoặc cơ chế được tổ chức quy định; xác định rõ hành vi khi không truy cập được dịch vụ kiểm tra thu hồi.
- **Thuật toán và kích thước khóa:** từ chối chữ ký chứng thư, loại khóa hoặc kích thước khóa không còn được chính sách chấp nhận.

Trust anchor phải đến từ cấu hình hoặc kênh quản trị tin cậy. Không lấy root certificate trong x5c rồi tự động thêm nó vào trust store. Nếu làm vậy, người gửi token có thể tự tạo CA, ký leaf certificate của họ và tự biến CA đó thành gốc tin cậy.

### Intermediate và root certificate

Intermediate certificate thường được gửi kèm để bên nhận có thể xây dựng đường dẫn. Root certificate có thể bị bỏ qua trong x5c vì bên nhận đã có trust anchor riêng. Nếu root xuất hiện trong mảng, nó vẫn không tự trở thành trust anchor chỉ vì được gửi cùng token.

Một chuỗi có đủ chứng thư về mặt hình thức vẫn có thể không hợp lệ nếu:

- Intermediate không phải CA được phép ký chứng thư con.
- Chữ ký của một chứng thư không hợp lệ.
- Đường dẫn không kết thúc tại trust anchor được phép.
- Name constraints, path length hoặc policy bị vi phạm.
- Leaf đã hết hạn hoặc bị thu hồi.

## 6. Liên kết danh tính chứng thư với issuer của JWT

Path validation trả lời rằng chứng thư được phát hành theo một chuỗi CA được tin cậy. Nó chưa nhất thiết trả lời rằng chủ thể trong chứng thư có quyền phát hành JWT cho issuer cụ thể.

Ví dụ, trust store của một tổ chức có thể tin nhiều CA phục vụ website, email, thiết bị và người dùng. Một chứng thư hợp lệ từ một CA trong trust store không tự động có quyền ký access token cho issuer identity.

Ứng dụng cần một quy tắc liên kết danh tính, chẳng hạn:

- Chứng thư hoặc public key đã được pin cho issuer.
- Subject Alternative Name (SAN) chứa URI/DNS name được profile quy định và khớp với issuer đã cấu hình.
- Một certificate policy hoặc Extended Key Usage riêng được profile chấp nhận.
- Metadata issuer đã xác thực liên kết issuer với certificate/key cụ thể.
- Quy trình đăng ký khóa ngoài băng xác minh danh tính chủ thể trước khi cấp quyền ký.

Không nên chỉ so sánh Common Name (CN) hoặc một chuỗi Subject DN chung chung nếu profile yêu cầu danh tính cụ thể. Ưu tiên định danh SAN và quy tắc mapping được đặc tả rõ ràng. Không suy luận rằng chứng thư TLS serverAuth có thể dùng để ký JWT chỉ vì nó có tên miền của issuer.

Ví dụ cấu hình khái niệm:

~~~yaml
trustedTokenIssuers:
  - issuer: "https://identity.example"
    allowedCertificateIdentities:
      - "URI:spiffe://example.org/identity/issuer"
    trustAnchors:
      - "managed-identity-ca"
    allowedAlgorithms:
      - "PS256"
    requiredKeyUsage:
      - "digitalSignature"
~~~

Đây là cấu hình minh họa, không phải schema chuẩn của JOSE hoặc X.509. Cách biểu diễn identity và policy OID phải do profile/giao thức của hệ thống xác định.

## 7. Key Usage và Extended Key Usage

Chứng thư có thể hợp lệ về PKIX nhưng vẫn không phù hợp cho thao tác mật mã hiện tại. Key Usage và Extended Key Usage giúp giới hạn mục đích của public key.

| Thao tác | Key Usage thường cần xem xét | Ghi chú |
| --- | --- | --- |
| Xác minh chữ ký JWS | digitalSignature | Leaf certificate phải cho phép mục đích chữ ký theo profile |
| Mã hóa CEK cho recipient bằng RSA key transport | keyEncipherment | Kiểm tra thuật toán quản lý khóa JWE và chính sách chứng thư |
| Thỏa thuận khóa recipient bằng ECDH-ES | keyAgreement | Kiểm tra loại khóa/đường cong và thuật toán tương ứng |

Extended Key Usage có thể giới hạn chứng thư cho một số vai trò. Tuy nhiên, không có một EKU chung tự động áp dụng cho mọi JWT. Ví dụ, EKU serverAuth dùng cho xác thực máy chủ TLS không đồng nghĩa với quyền ký token. Nếu một hệ thống dùng EKU tùy chỉnh cho token signing, OID và cách kiểm tra phải được đặc tả, phân phối và quản trị nhất quán.

Nếu Key Usage hiện diện và không cho phép thao tác yêu cầu, từ chối chứng thư. Nếu trường không hiện diện, cách xử lý phụ thuộc profile và quy tắc PKIX/ứng dụng; không tự suy diễn một quyền mà profile không quy định.

### Bảo vệ thông tin nhận diện khóa trong JOSE Header

JWS/JWE JSON Serialization có thể chứa protected header và unprotected header. Nếu x5c, x5u hoặc metadata chứng thư được dùng để chọn khóa hay quyết định tin cậy, thông tin đó phải được integrity-protected theo quy tắc của JOSE. Với JWS JSON Serialization, RFC 7515 mục 6 nêu rõ yêu cầu bảo vệ thông tin nhận diện khóa khi thông tin đó tham gia quyết định tin cậy.

Không dựa vào một giá trị x5u/x5c ở unprotected header để thay đổi issuer, danh tính chứng thư hoặc quyền được cấp. Khi profile yêu cầu thông tin này, đặt nó trong protected header; sau đó vẫn phải xác minh PKIX path và liên kết danh tính độc lập. Chữ ký hoặc authentication tag bảo vệ header khỏi sửa đổi, nhưng không tự biến chứng thư do người gửi cung cấp thành chứng thư đáng tin.

## 8. Khác biệt khi dùng x5c/x5u trong JWS và JWE

| Khía cạnh | JWS | JWE |
| --- | --- | --- |
| Khóa được chứng thư mô tả | Public key tương ứng với private key dùng ký JWS | Public key dùng trong thao tác quản lý khóa để bảo vệ CEK, thường là public key của recipient |
| Mục tiêu | Xác minh chữ ký và có thể xác lập danh tính bên ký | Hỗ trợ xác định recipient/key dùng để giải mã |
| Điều cần kiểm tra | PKIX path, issuer identity, signing usage, thuật toán và chữ ký | Recipient/key mapping, PKIX/identity policy nếu áp dụng, key management algorithm và kết quả giải mã |
| Điều không tự chứng minh | Chứng thư được nhúng không tự chứng minh issuer nếu chưa xác minh trust | Giải mã thành công không tự chứng minh danh tính bên gửi |

Với JWS, chữ ký hợp lệ bằng private key tương ứng chứng minh bên tạo chữ ký kiểm soát khóa đó. Muốn gắn chữ ký với issuer, phải xác minh certificate/key được cấp cho issuer đó.

Với JWE, người gửi thường mã hóa cho public key của recipient. Bất kỳ ai có public key này đều có thể tạo ciphertext gửi cho recipient. Do đó, chứng thư recipient không phải bằng chứng về danh tính issuer của plaintext. Nếu nội dung cần xác thực người phát hành, dùng JWS lồng trong JWE hoặc cơ chế xác thực nguồn gốc khác theo profile.

## 9. Rủi ro khi tải x5u từ URL do token cung cấp

x5u là URI trong header. Nếu bộ xác minh tự động tải URI bất kỳ do token gửi tới, nó có thể trở thành SSRF giống trường hợp jku.

Các mục tiêu bị truy cập ngoài ý muốn có thể gồm:

- Loopback hoặc dịch vụ quản trị trên máy chủ xác minh.
- Địa chỉ private trong mạng nội bộ.
- Cloud metadata endpoint.
- Dịch vụ debug, metrics hoặc API nội bộ.
- Host bên ngoài được dùng để quét cổng, gây tải hoặc quan sát request.

HTTPS không loại bỏ rủi ro này. Kẻ tấn công có thể sở hữu domain và chứng thư TLS hợp lệ cho domain của họ. TLS xác thực máy chủ của URI, không xác lập rằng URI thuộc issuer được tin cậy.

### Kiểm soát khi lấy x5u

Ưu tiên dùng chứng thư nhúng x5c hoặc nguồn chứng thư đã cấu hình sẵn. Nếu profile cho phép tải x5u:

1. Chỉ dùng URI được cấu hình cho issuer/profile hoặc kiểm tra khớp allowlist chính xác.
2. Chỉ cho phép HTTPS và xác minh đầy đủ TLS certificate cùng hostname/service identity.
3. Tắt redirect tự động; nếu cần redirect, xác thực lại scheme, host, port, DNS và IP tại từng bước.
4. Từ chối loopback, private, link-local, multicast, unspecified và các dải IP đặc biệt; kiểm tra cả IPv4 và IPv6.
5. Ngăn DNS rebinding bằng cách gắn địa chỉ IP đã kiểm tra với kết nối thực tế; áp dụng egress firewall/network policy.
6. Từ chối URI có userinfo, scheme lạ, port không được phép hoặc cấu trúc không hợp lệ.
7. Đặt timeout, giới hạn kích thước response, số chứng thư, số lần redirect và số request đồng thời.
8. Không gửi cookie, bearer token hoặc thông tin xác thực nội bộ tới máy chủ x5u.
9. Parse PEM nghiêm ngặt, từ chối response HTML hoặc nội dung không phải chứng thư.
10. Sau khi tải, vẫn xác minh PKIX path và danh tính chứng thư; không tin chỉ vì TLS fetch thành công.

### Hai bước xác minh TLS khác nhau

Khi tải x5u qua HTTPS, phải xác minh chứng thư TLS của máy chủ x5u để bảo vệ kết nối. Sau khi tải xong, phải xác minh chuỗi chứng thư X.509 được tài nguyên cung cấp để xác lập public key của JWS/JWE. Hai chuỗi chứng thư này có thể hoàn toàn khác nhau và phục vụ hai mục đích khác nhau.

## 10. Quy trình xác minh JWS có x5c/x5u

Giả sử API chỉ nhận access token do issuer đã cấu hình phát hành:

1. Chọn issuer và profile từ cấu hình tin cậy của endpoint.
2. Parse JOSE Header theo giới hạn kích thước và quy tắc JSON nghiêm ngặt.
3. Kiểm tra thuật toán chữ ký nằm trong allowlist.
4. Nếu có x5c, decode Base64 DER theo đúng thứ tự; nếu có x5u, chỉ tải URI được profile cho phép qua HTTPS an toàn.
5. Xây dựng và xác minh certificate path tới trust anchor đã cấu hình; không thêm root lấy từ token làm trust anchor.
6. Kiểm tra validity, revocation theo policy, name constraints, Key Usage, EKU và thuật toán/chất lượng khóa.
7. Liên kết danh tính chứng thư với issuer dự kiến bằng mapping được cấu hình.
8. Lấy public key từ leaf certificate và xác minh nó tương thích với thuật toán JOSE.
9. Xác minh chữ ký JWS.
10. Sau khi chữ ký hợp lệ, kiểm tra iss, aud, exp, nbf, typ và các claim/quyền theo profile.
11. Chỉ chấp nhận token khi mọi điều kiện đều đạt.

~~~mermaid
flowchart TD
    A["Nhận JWS chưa tin cậy"] --> B["Chọn issuer/profile từ cấu hình"]
    B --> C["Parse header và kiểm tra alg"]
    C --> D{"Có x5c hay x5u?"}
    D -- x5c --> E["Decode chuỗi chứng thư DER"]
    D -- x5u --> F["Tải PEM từ URI được cho phép qua HTTPS"]
    F --> G["Xác minh TLS host và kiểm soát SSRF"]
    G --> H["Parse chuỗi chứng thư"]
    E --> H
    H --> I["PKIX path validation tới trust anchor cấu hình"]
    I --> J{"Chuỗi và danh tính hợp lệ?"}
    J -- Không --> X["Từ chối"]
    J -- Có --> K["Kiểm tra Key Usage, EKU và key algorithm"]
    K --> L["Xác minh chữ ký bằng public key của leaf"]
    L --> M{"Chữ ký hợp lệ?"}
    M -- Không --> X
    M -- Có --> N["Kiểm tra iss, aud, thời hạn và profile"]
    N --> O{"Claims hợp lệ?"}
    O -- Không --> X
    O -- Có --> P["Chấp nhận token"]
~~~

Mã giả:

~~~text
function verifySignedToken(token, endpoint):
    policy = trustedPolicyFor(endpoint)
    jws = parseJwsStrictlyWithLimits(token)
    header = jws.protectedHeader

    require header.alg in policy.allowedAlgorithms

    if header.x5c exists:
        certificates = decodeBase64DerCertificateArray(header.x5c)
    else if header.x5u exists:
        require policy.allowsConfiguredX5u(header.x5u)
        pem = fetchCertificateResourceSafely(header.x5u, policy.networkRules)
        certificates = parsePemCertificateChain(pem)
    else:
        reject("No certificate reference permitted by this profile")

    leaf = certificates[0]
    path = buildAndValidatePkixPath(
        leaf,
        certificates[1..],
        trustAnchors = policy.trustAnchors,
        revocationPolicy = policy.revocationPolicy
    )
    require path.validationSucceeded
    require certificateIdentityMatchesIssuer(leaf, policy.expectedIssuer)
    require keyUsageAllows(leaf, "digitalSignature")
    require publicKeyMatchesAlgorithm(leaf.publicKey, header.alg)

    claims = verifyJwsSignature(jws, leaf.publicKey, [policy.allowedAlgorithm])
    require signatureVerificationSucceeded
    require claims.iss == policy.expectedIssuer
    require policy.expectedAudience in claims.aud
    require timeClaimsAreValid(claims)
    return claims
~~~

Đây là mã giả minh họa cho profile JWS dùng chứng thư ký. Profile JWE cần quy trình recipient/key management riêng; không dùng nguyên quy trình này để kết luận danh tính issuer của JWE.

## 11. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tin x5c vì chứng thư parse thành công | Kẻ tấn công tự tạo chứng thư và token | Xác minh PKIX chain tới trust anchor đã cấu hình |
| Lấy root CA trong x5c làm trust anchor | Người gửi tự thêm CA của họ vào miền tin cậy | Trust anchor chỉ đến từ cấu hình/quản trị tin cậy |
| Chỉ kiểm tra TLS của x5u | Domain do kẻ tấn công sở hữu vẫn có TLS hợp lệ | Gắn URI với issuer và xác minh chứng thư được tải |
| Tải x5u bất kỳ từ token | SSRF, truy cập mạng nội bộ hoặc metadata endpoint | Allowlist URI, HTTPS, DNS/IP controls và egress filtering |
| Cho phép redirect tự động | URI hợp lệ chuyển sang host không được phép | Tắt redirect hoặc kiểm tra lại mọi bước |
| Nhầm TLS server certificate với token signing certificate | Chấp nhận sai danh tính hoặc mục đích khóa | Xác minh hai vai trò chứng thư độc lập |
| Không kiểm tra danh tính leaf certificate | CA hợp lệ nhưng chứng thư không thuộc issuer dự kiến | Mapping SAN/identity với issuer theo profile |
| Bỏ qua Key Usage/EKU | Dùng khóa cho mục đích chứng thư không cho phép | Kiểm tra usage theo thao tác JOSE và profile |
| Dùng chứng thư hết hạn hoặc bị thu hồi | Chấp nhận khóa không còn hợp lệ | Kiểm tra validity và revocation theo policy |
| Giả định JWE được giải mã là đã xác thực người gửi | Nhầm bí mật với xác thực nguồn | Dùng JWS hoặc cơ chế xác thực nguồn gốc riêng |
| Không giới hạn chuỗi hoặc response | Parser DoS, tiêu hao bộ nhớ/CPU | Giới hạn kích thước, số cert, timeout và độ sâu |

## 12. Bộ ca kiểm thử

Giả sử API chỉ chấp nhận JWS ký bằng chứng thư của issuer đã cấu hình, trust anchor là CA nội bộ được quản trị và thuật toán được phép là PS256.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| x5c có leaf và intermediate hợp lệ, chain tới trust anchor, danh tính issuer đúng, chữ ký đúng | **Chấp nhận** |
| x5c chứa chứng thư tự ký không nằm trong trust store | **Từ chối** |
| x5c có chain tới CA được tin nhưng SAN/identity không khớp issuer | **Từ chối** |
| Leaf certificate hết hạn hoặc chưa có hiệu lực | **Từ chối** |
| Leaf certificate bị thu hồi theo chính sách | **Từ chối** |
| Intermediate không có Basic Constraints CA hoặc path length bị vi phạm | **Từ chối** |
| Key Usage không cho phép digitalSignature | **Từ chối** |
| Chứng thư có EKU không phù hợp với profile yêu cầu | **Từ chối** |
| Public key trong leaf không tương thích PS256 | **Từ chối** |
| Chữ ký sai dù chain hợp lệ | **Từ chối** |
| x5c dùng PEM nguyên văn thay vì Base64 DER | **Từ chối** theo định dạng |
| x5u khớp URI cấu hình, HTTPS/TLS hợp lệ, PEM hợp lệ, chain và issuer đúng | **Chấp nhận** nếu chữ ký/claims hợp lệ |
| x5u trỏ tới domain ngoài allowlist dù domain có TLS hợp lệ | **Từ chối**, không tải |
| x5u trỏ tới loopback/private IP hoặc metadata service | **Từ chối**, không tạo request |
| x5u redirect sang host khác hoặc địa chỉ nội bộ | **Từ chối** hoặc không theo redirect |
| TLS hostname mismatch hoặc certificate TLS không hợp lệ | **Từ chối** |
| PEM response quá lớn hoặc chứa quá nhiều certificate | **Từ chối** |
| JWE có x5c của recipient hợp lệ nhưng ứng dụng cần xác thực sender | Không coi x5c là bằng chứng sender; yêu cầu chữ ký/cơ chế xác thực nguồn |

Kiểm thử x5u cần xác nhận không có request nào tới địa chỉ cấm, không chỉ kiểm tra kết quả trả về. Kiểm thử x5c cần xác nhận trust anchor đến từ cấu hình, không được tự thêm root certificate trong token vào trust store.

## 13. Ghi nhớ

- x5c nhúng chuỗi chứng thư X.509 dưới dạng Base64 DER; x5u tham chiếu tài nguyên chứng thư/chuỗi chứng thư dạng PEM.
- Trong x5c, leaf certificate đứng đầu; các certificate tiếp theo có thể chứng thực cho certificate đứng trước.
- Chứng thư parse thành công hoặc TLS fetch thành công không đồng nghĩa khóa đáng tin.
- Xác minh chuỗi PKIX tới trust anchor được cấu hình; không tin root certificate chỉ vì nó được gửi trong x5c.
- Liên kết danh tính leaf certificate với issuer/recipient và kiểm tra Key Usage, EKU, validity, revocation cùng thuật toán.
- Với x5u, kiểm soát URI, HTTPS/TLS, hostname, DNS/IP, redirect, timeout, response size và egress để phòng SSRF.
- Chứng thư TLS của máy chủ x5u và chứng thư được tải từ x5u là hai đối tượng có mục đích khác nhau.
- Trong JWS, chứng thư có thể giúp xác định public key ký; trong JWE, chứng thư thường liên quan tới public key recipient. Giải mã JWE không tự xác thực sender.

### Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS), mục 4.1.5, 4.1.6 và 6](https://www.rfc-editor.org/rfc/rfc7515): x5u, x5c và bảo vệ thông tin nhận diện khóa.
- [RFC 7516 — JSON Web Encryption (JWE), mục 4.1.7 và 4.1.8](https://www.rfc-editor.org/rfc/rfc7516): x5u và x5c trong JWE.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): định dạng chứng thư, certificate path validation, Key Usage và CRL.
- [RFC 6125 — Representation and Verification of Domain-Based Application Service Identity within Internet Public Key Infrastructure Using X.509](https://www.rfc-editor.org/rfc/rfc6125): xác minh danh tính máy chủ TLS theo tên miền; khi triển khai mới cần xem hướng dẫn cập nhật hiện hành về service identity.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): hướng dẫn hiện hành về xác minh danh tính dịch vụ TLS, cập nhật RFC 6125.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): ràng buộc issuer, khóa và ngữ cảnh xác minh JWT.
