# Không tự viết thuật toán mật mã hoặc bộ xác minh chữ ký

## 1. Vì sao không nên tự triển khai mật mã cho JWT?

JWT thường được dùng làm credential trong các hệ thống xác thực và phân quyền. Một lỗi nhỏ trong cách xác minh chữ ký, diễn giải header, xử lý khóa hoặc kiểm tra claims có thể khiến hệ thống chấp nhận token giả, token sai mục đích hoặc token đã hết hiệu lực.

Các thuật toán mật mã như RSA, ECDSA, HMAC, EdDSA và các chế độ mã hóa xác thực đã có đặc tả cùng những chi tiết triển khai rất dễ sai. JOSE còn bổ sung quy tắc biểu diễn dữ liệu, serialization, thuật toán, khóa, header và cách liên kết các thành phần. JWT lại bổ sung quy tắc về claims và profile sử dụng.

Vì vậy, không nên tự viết:

- Thuật toán hash, MAC, chữ ký số hoặc mã hóa.
- Phép xác minh RSA/ECDSA/EdDSA bằng thao tác số học tự triển khai.
- Hàm so sánh MAC/chữ ký theo cách có thể rò rỉ thời gian.
- Bộ parse và xác minh JOSE/JWS/JWE tùy biến cho production.
- Cơ chế tự diễn giải signing input hoặc chuyển đổi chữ ký.
- Bộ quản lý khóa, JWKS hoặc rotation tự chế nếu có thư viện/hạ tầng đã được kiểm chứng.

Hãy dùng thư viện mật mã và thư viện JOSE/JWT được duy trì, có kiểm thử, hỗ trợ đúng profile và được cấu hình theo policy của ứng dụng. Thư viện giảm rủi ro lỗi triển khai; nó không tự quyết định issuer nào được tin, audience nào được phép, thuật toán nào được chấp nhận hay quyền nào được cấp.

Nội dung thuộc module Security - JSON Web Token (JWT), chương Tích hợp thư viện. Phạm vi là bảo mật JWT/JOSE tổng quát, không phụ thuộc Java, Spring Security hoặc một ngôn ngữ lập trình cụ thể.

## 2. Phân biệt ba lớp cần dùng đúng công cụ

Một triển khai JWT an toàn thường có ít nhất ba lớp:

| Lớp | Trách nhiệm | Công cụ phù hợp |
| --- | --- | --- |
| Primitive mật mã | Hash, MAC, chữ ký, mã hóa xác thực, sinh số ngẫu nhiên | Thư viện mật mã hoặc crypto provider đã được kiểm chứng |
| JOSE/JWT | Serialization, Base64URL, JWS, JWE, JWK, header, signing input, thuật toán và quy tắc chuyển đổi | Thư viện JOSE/JWT được duy trì |
| Policy ứng dụng | Issuer, audience, token profile, thời gian, claims bắt buộc, revocation, authorization | Cấu hình và logic policy của ứng dụng, dựa trên kết quả thư viện |

Không nên nhầm thư viện primitive với thư viện JOSE. Một crypto API có thể cung cấp hàm SHA-256 hoặc RSA verify nhưng không nhất thiết hiểu cách JWT tạo signing input, cách ECDSA được biểu diễn trong JWS, cách xử lý protected header hoặc cách kiểm tra token profile.

Ngược lại, một thư viện JWT có thể gọi crypto provider bên dưới để thực hiện thuật toán. Ứng dụng nên sử dụng API cấp cao của thư viện JOSE/JWT để parse, verify hoặc decrypt token, thay vì tự ghép các primitive thành một validator riêng.

## 3. Những lỗi dễ xuất hiện khi tự viết bộ xác minh

### 3.1. Xác minh sai signing input

Với JWS Compact Serialization, chữ ký được tính trên signing input có dạng:

~~~text
BASE64URL(UTF8(protected-header))
.
BASE64URL(payload)
~~~

Đây là byte sequence cụ thể theo serialization. Không được parse JSON rồi serialize lại header hoặc payload theo cách riêng trước khi xác minh. Khoảng trắng, thứ tự thuộc tính, escape, encoding hoặc cách biểu diễn số có thể thay đổi byte sequence.

Một validator tự viết có thể xác minh trên chuỗi đã tái tạo thay vì signing input gốc, dẫn đến sai lệch giữa các implementation hoặc bỏ qua dữ liệu đã được ký.

### 3.2. Sai quy tắc biểu diễn chữ ký

Một số API mật mã và JOSE dùng cách biểu diễn chữ ký khác nhau. Ví dụ, ECDSA trong JWS sử dụng dạng nối cố định phần R và S theo độ dài curve; một số API mật mã truyền thống lại dùng ASN.1 DER sequence. Chuyển đổi sai độ dài, padding hoặc endian có thể khiến xác minh thất bại hoặc tạo lỗi bảo mật.

RSA-PSS còn có các tham số như hash, MGF1 và salt length phải khớp profile. Chỉ chọn “RSA verify” chung chung không đủ để xác minh mọi thuật toán RSA trong JOSE.

Thư viện JOSE phù hợp sẽ xử lý các quy tắc chuyển đổi và tham số theo thuật toán đã chọn.

### 3.3. Algorithm confusion

Header alg do token gửi lên là dữ liệu chưa tin cậy. Nếu validator cho phép token tự quyết định thuật toán hoặc tự chuyển đổi giữa HMAC và chữ ký bất đối xứng, attacker có thể khai thác cách hệ thống diễn giải khóa.

Ví dụ, public key dùng để xác minh RSA có thể bị dùng nhầm như HMAC secret nếu ứng dụng không ràng buộc key type với thuật toán. Một số cấu hình còn vô tình cho phép thuật toán không bảo vệ chữ ký hoặc thuật toán ngoài policy.

Phòng thủ:

- Chọn allowlist thuật toán từ cấu hình tin cậy của endpoint.
- Không lấy danh sách thuật toán từ token.
- Ràng buộc thuật toán với key type, key usage và issuer.
- Không dùng chung một khóa cho các mục đích không tương thích.
- Từ chối thuật toán không được cấu hình, kể cả khi thư viện có hỗ trợ.

### 3.4. Lỗi parse và diễn giải header/claims

Tự viết parser có thể xử lý sai:

- JSON member trùng lặp.
- Kiểu dữ liệu không đúng, ví dụ exp là chuỗi thay vì NumericDate.
- Base64URL lỗi hoặc padding không hợp lệ.
- Header crit không được hỗ trợ.
- Protected và unprotected header bị nhầm lẫn.
- Serialization lồng nhau hoặc nested JWT.
- Token quá lớn, quá sâu hoặc gây tiêu tốn CPU/bộ nhớ.

Các implementation khác nhau có thể diễn giải cùng một dữ liệu không giống nhau. Kẻ tấn công có thể lợi dụng sự không nhất quán giữa gateway, thư viện và service phía sau.

### 3.5. Timing và so sánh mật mã

So sánh MAC hoặc dữ liệu xác thực bằng phép so sánh chuỗi thông thường có thể làm lộ thông tin qua thời gian phản hồi nếu dừng ngay tại byte đầu tiên khác nhau. Các primitive mật mã và thư viện chuyên dụng thường có API so sánh constant-time cho trường hợp cần thiết.

Không tự viết hàm constant-time dựa trên suy đoán. Dùng API được tài liệu hóa của crypto library hoặc JOSE library; lưu ý compiler, runtime và môi trường thực thi có thể ảnh hưởng đến đặc tính thời gian.

## 4. Dùng thư viện ở đúng ranh giới

Một ứng dụng thường cần kết hợp:

1. Thư viện JOSE/JWT để parse và xác minh JWS, giải mã JWE, xử lý JWK và serialization.
2. Crypto provider hoặc KMS/HSM để thực hiện thao tác khóa khi phù hợp.
3. Policy validator để quyết định token có phù hợp endpoint và nghiệp vụ hay không.

~~~mermaid
flowchart TD
    A["Nhận JWT thô"] --> B["Endpoint chọn validation policy tin cậy"]
    B --> C["JOSE/JWT library: parse có giới hạn"]
    C --> D["Key resolver: lấy khóa từ trust configuration"]
    D --> E["JOSE/JWT library + crypto provider"]
    E --> F["Verify JWS hoặc authenticated decrypt JWE"]
    F --> G{"Bằng chứng mật mã hợp lệ?"}
    G -- "Không" --> X["Từ chối"]
    G -- "Có" --> H["Policy kiểm tra typ, iss, aud, thời gian và claims"]
    H --> I["Kiểm tra revocation, binding và replay nếu yêu cầu"]
    I --> J{"Tất cả kiểm tra đạt?"}
    J -- "Không" --> X
    J -- "Có" --> K["Tạo validated token context"]
    K --> L["Authorization theo hành động và tài nguyên"]
~~~

Thư viện chịu trách nhiệm xử lý JOSE và primitive đúng đặc tả. Ứng dụng chịu trách nhiệm chọn policy, nguồn khóa tin cậy, token profile, audience, claims bắt buộc, trạng thái và authorization.

Không được bỏ qua policy chỉ vì thư viện trả về kết quả “signature valid”. Xác minh chữ ký thành công chỉ là một bước trong pipeline.

## 5. Tiêu chí chọn thư viện JOSE/JWT

Không chọn thư viện chỉ vì có API parse JWT hoặc vì nó phổ biến trong một bài hướng dẫn. Cần đánh giá khả năng kỹ thuật, chất lượng bảo trì và độ phù hợp với profile.

| Tiêu chí | Cần kiểm tra |
| --- | --- |
| Chuẩn giao thức | Hỗ trợ đúng RFC 7515, 7516, 7517, 7518, 7519 và profile ứng dụng cần dùng |
| Thuật toán | Có allowlist, hỗ trợ thuật toán cần thiết và ràng buộc key type |
| Serialization | Xử lý đúng Compact/JSON Serialization mà hệ thống sử dụng |
| JWS/JWE | Verify, sign, decrypt và authenticated encryption theo profile |
| JWK/JWKS | Parse, lọc key, key use, key_ops, kid và rotation |
| Claims validation | Hỗ trợ hoặc cho phép kiểm tra iss, aud, exp, nbf, iat và claims tùy profile |
| Explicit typing | Có thể áp dụng typ/token profile và validation rules tách biệt |
| Nested JWT | Xử lý nested JWS/JWE nếu hệ thống thực sự yêu cầu |
| Error handling | Phân loại lỗi kỹ thuật mà không làm lộ token hoặc secret |
| Tài liệu | Có hướng dẫn cấu hình an toàn, ví dụ đầy đủ và mô tả giới hạn |
| Kiểm thử | Có test vectors, interoperability tests, negative tests và fuzzing phù hợp |
| Bảo trì | Có phiên bản phát hành, changelog, xử lý lỗ hổng và maintainer hoạt động |
| Phụ thuộc | Dependency tree, license, nguồn phát hành và quy trình cập nhật minh bạch |

### 5.1. Kiểm tra trạng thái bảo trì

Trước khi chọn, hãy kiểm tra:

- Phiên bản ổn định hiện tại và lịch phát hành.
- Lần cập nhật bảo mật gần nhất.
- Cách dự án công bố và xử lý CVE.
- Các thuật toán hoặc profile đã bị deprecated.
- Tương thích với phiên bản runtime và crypto provider mà hệ thống hỗ trợ.
- Vấn đề mở liên quan đến parsing, key resolution, JWE hoặc algorithm confusion.

Không thể kết luận một thư viện an toàn chỉ vì nó có nhiều lượt tải, nhiều sao hoặc được dùng trong một dự án lớn. Cũng không nên tự động coi thư viện cũ là có lỗ hổng; cần xem phiên bản, advisory và cách cấu hình cụ thể.

### 5.2. Ưu tiên thư viện có API policy rõ

API tốt nên cho phép ứng dụng cấu hình rõ:

- Thuật toán được phép.
- Issuer và audience mong đợi.
- Key source tin cậy.
- Token type/profile.
- Claims bắt buộc và quy tắc thời gian.
- Giới hạn kích thước và serialization.
- Cách xử lý key rotation và lỗi.

Tránh API có hành vi mặc định quá rộng, tự chấp nhận mọi thuật toán, tự tải khóa từ header hoặc tự suy ra issuer từ token mà không có trust configuration.

## 6. Cấu hình an toàn trước khi xác minh

Validation policy phải được lấy từ endpoint hoặc cấu hình tin cậy, không lấy từ token chưa xác minh.

Ví dụ cấu hình khái quát:

~~~yaml
jwtValidation:
  profile: oauth-access-token
  trustedIssuer: https://identity.example.org/
  expectedAudience: https://api.example.org/invoices
  allowedAlgorithms:
    - RS256
    - ES256
  requiredClaims:
    - iss
    - sub
    - aud
    - exp
  maxTokenBytes: 16384
  clockSkewSeconds: 60
  requireExplicitTokenType: true
  checkRevocation: true
~~~

Đây là cấu hình minh họa, không phải schema chuẩn. Thuật toán và clock skew phải được lựa chọn theo policy, threat model và profile; không sao chép nguyên xi vào production.

### 6.1. Allowlist thuật toán

Danh sách thuật toán được cấu hình riêng cho từng token profile. Ví dụ, một API chỉ cần xác minh Access Token ký bằng RS256 hoặc ES256 thì không nên tự động chấp nhận HS256, none hoặc các thuật toán khác chỉ vì thư viện hỗ trợ.

Không dùng một allowlist rộng cho mọi loại token. Client assertion, ID Token, Access Token và DPoP proof có thể có yêu cầu khác nhau.

### 6.2. Key type và key usage

Khóa phải tương thích với thuật toán và mục đích:

- HMAC dùng secret đối xứng; bên xác minh cũng có khả năng tạo MAC.
- RSA/EC/OKP thường dùng cặp khóa bất đối xứng theo thuật toán tương ứng.
- Public key chỉ được dùng trong vai trò được phép.
- JWK use/key_ops và thuật toán phải phù hợp policy.
- Không dùng encryption key làm signing key hoặc ngược lại nếu profile không cho phép.

### 6.3. Giới hạn đầu vào

Trước và trong khi parse token, đặt giới hạn:

- Kích thước token tối đa.
- Kích thước header và payload.
- Độ sâu nested serialization.
- Số lượng recipient hoặc key được thử.
- Thời gian tải JWKS và timeout mạng.
- Số lần refresh key khi gặp kid không tồn tại.

Giới hạn phải đủ cho token hợp lệ của hệ thống nhưng ngăn token bất thường gây cạn tài nguyên.

## 7. Key resolver và JWKS: không tin nguồn khóa do token tự khai

JOSE header có thể chứa kid để gợi ý khóa phù hợp. Tuy nhiên, kid không phải bằng chứng khóa thuộc issuer tin cậy. Key resolver cần được gắn với issuer và trust configuration đã biết.

Luồng phù hợp:

1. Endpoint chọn issuer được tin cậy từ policy.
2. Resolver lấy key set từ JWKS URI đã cấu hình hoặc nguồn khóa nội bộ đã xác thực.
3. Header kid chưa xác minh chỉ dùng để tìm candidate trong key set đó.
4. Resolver kiểm tra key type, use, key_ops, thuật toán và trạng thái.
5. JOSE library xác minh bằng khóa phù hợp.
6. Sau xác minh, ứng dụng kiểm tra iss khớp issuer policy.

Không tải khóa từ jku hoặc x5u tùy ý trong token chưa xác minh. Việc fetch URL do attacker kiểm soát có thể tạo SSRF, truy cập mạng nội bộ hoặc tin cậy một nguồn khóa giả.

### 7.1. Xử lý kid không tồn tại

Khi kid không tìm thấy:

- Có thể refresh JWKS một lần theo cache/refresh policy đã định.
- Dùng timeout và giới hạn số lần tải.
- Không tải URL do token chỉ định.
- Không thử mọi khóa từ mọi issuer trong hệ thống.
- Nếu vẫn không có khóa phù hợp, từ chối token.

Không để một request có kid ngẫu nhiên kích hoạt tải JWKS không giới hạn. Điều đó có thể bị lợi dụng để gây quá tải.

### 7.2. Rotation và cache

Issuer có thể phát hành token bằng khóa mới trong khi Resource Server vẫn đang cache JWKS cũ. Cần có quy trình:

- Công bố khóa mới trước khi dùng nếu giao thức/hạ tầng cho phép.
- Hỗ trợ overlap trong thời gian chuyển tiếp.
- Cache có TTL và refresh policy rõ.
- Xử lý kid mới một cách có giới hạn.
- Loại bỏ khóa cũ sau khi token ký bằng khóa đó không còn được chấp nhận.
- Có quy trình khẩn cấp khi khóa bị compromise.

Không giữ khóa cũ vô thời hạn chỉ để tương thích. Cũng không xóa khóa cũ quá sớm nếu token hợp lệ còn hạn cần được xác minh.

## 8. Xác minh JWS và giải mã JWE bằng thư viện

### 8.1. JWS

Với JWS, dùng API verify của thư viện JOSE/JWT. Truyền vào:

- Token nguyên gốc.
- Key resolver hoặc khóa thuộc trust configuration.
- Allowlist thuật toán.
- Quy tắc serialization và profile.

Sau khi thư viện báo chữ ký hợp lệ, tiếp tục kiểm tra issuer, audience, thời gian, token type và claims bắt buộc. Không tự parse payload riêng rồi bỏ qua kết quả parser/validator của thư viện.

### 8.2. JWE

Với JWE, dùng API decrypt/authenticated-decrypt của thư viện. Cấu hình allowlist alg và enc, recipient key, giới hạn kích thước và profile.

Chỉ sử dụng plaintext sau khi authentication tag được xác minh thành công. Nếu JWE chứa JWS lồng, tiếp tục xác minh JWS bên trong theo issuer và profile. Giải mã thành công không tự chứng minh issuer đã phát hành token nếu mô hình mã hóa không cung cấp xác thực nguồn gửi.

### 8.3. Nested JWT

Với cấu trúc ký bên trong, mã hóa bên ngoài:

1. Xác minh header và policy JWE.
2. Giải mã JWE bằng khóa recipient.
3. Chỉ sau authenticated decryption mới xử lý payload bên trong.
4. Xác minh JWS bằng khóa issuer tin cậy.
5. Kiểm tra claims và profile của JWT bên trong.

Không bỏ qua lớp ký bên trong chỉ vì lớp mã hóa ngoài hợp lệ. Cũng không chấp nhận nested structure sâu hoặc phức tạp ngoài profile đã định nghĩa.

## 9. Không để thư viện tự quyết định policy nghiệp vụ

Một thư viện có thể xác minh chữ ký và hỗ trợ kiểm tra claims, nhưng ứng dụng vẫn phải xác định:

- Issuer nào được tin cậy.
- Audience nào phù hợp endpoint.
- Token type/profile nào được chấp nhận.
- Claim nào bắt buộc và semantics của chúng.
- Clock skew và lifetime tối đa.
- Có cần kiểm tra revocation, jti, session hoặc sender binding không.
- Scope/permission nào được phép cho hành động cụ thể.

Ví dụ, một API có thể xác minh chữ ký thành công nhưng vẫn phải từ chối token vì:

- aud dành cho API khác.
- iss không nằm trong trust configuration.
- typ không phù hợp Access Token profile.
- exp đã qua hoặc nbf chưa tới.
- Token bị thu hồi.
- Tenant/client binding không khớp.
- Scope không đủ cho thao tác.

Không gom tất cả thành một boolean “valid” nếu downstream cần biết các điều kiện nào đã được kiểm tra. Tốt hơn là tạo validated token context chỉ sau khi mọi kiểm tra bắt buộc thành công.

## 10. Xử lý lỗi an toàn

Lỗi từ thư viện có thể gồm token sai cú pháp, thuật toán không hỗ trợ, chữ ký sai, khóa không tìm thấy, token hết hạn, issuer/audience mismatch, JWE authentication failure hoặc lỗi tải JWKS.

Ở ranh giới bên ngoài, phản hồi nên đủ tổng quát để không tiết lộ:

- Token có tồn tại trong hệ thống hay không.
- kid nào đang được tin cậy.
- Khóa nào đã được thử.
- Dữ liệu nào trong payload đúng/sai.
- Chi tiết nội bộ của crypto provider.
- Raw token, claims hoặc secret.

Trong log nội bộ, có thể ghi mã lỗi đã chuẩn hóa, request ID, issuer policy ID, endpoint, thời gian xử lý và loại lỗi. Không ghi Authorization header, raw JWT, private key hoặc plaintext claims nhạy cảm.

Không biến lỗi kỹ thuật thành thành công:

| Lỗi | Hành vi |
| --- | --- |
| Token parse thất bại | Từ chối |
| Thuật toán ngoài allowlist | Từ chối |
| Không tìm được khóa tin cậy | Từ chối |
| Chữ ký sai | Từ chối |
| JWE authentication tag sai | Từ chối |
| Issuer/audience/profile sai | Từ chối |
| JWKS hoặc revocation store bắt buộc không khả dụng | Áp dụng failure policy đã định; không giả định token hợp lệ |

## 11. Mã giả tích hợp thư viện theo policy

~~~text
function validateIncomingJwt(rawToken, endpoint):
    policy = trustedPolicyRegistry.forEndpoint(endpoint)
    require policy exists

    require byteLength(rawToken) <= policy.maxTokenBytes

    parsedHeader = joseLibrary.parseProtectedHeaderWithinLimits(rawToken)
    require parsedHeader.alg in policy.allowedAlgorithms

    key = trustedKeyResolver.resolve(
        issuer = policy.trustedIssuer,
        kid = parsedHeader.kid,
        algorithm = parsedHeader.alg
    )
    require key exists
    require key.type and key.usage are compatible with policy

    cryptographicResult = joseLibrary.verifyOrDecrypt(
        rawToken,
        key,
        allowedAlgorithms = policy.allowedAlgorithms,
        allowedEncryptionMethods = policy.allowedEncryptionMethods
    )
    require cryptographicResult is successful

    claims = cryptographicResult.verifiedClaims
    require validateTokenProfile(claims, parsedHeader, policy)
    require claims.iss exactly equals policy.trustedIssuer
    require validateAudience(claims.aud, policy.expectedAudience)
    require validateTimeClaims(claims, policy.clockPolicy)
    require validateRequiredClaimsAndTypes(claims, policy)

    if policy.checkRevocation:
        require revocationCheckIsAvailable
        require not isRevoked(claims, policy)

    if policy.requireSenderConstraint:
        require validateProofOfPossession(claims, endpoint.request)

    return createImmutableValidatedTokenContext(claims, policy)
~~~

Đây là pseudocode độc lập với ngôn ngữ. Tên hàm chỉ mô tả ranh giới trách nhiệm, không phải API của một thư viện cụ thể. Với JWE, verifyOrDecrypt phải chỉ trả plaintext sau authenticated decryption; với nested JWT, phải xác minh từng lớp theo policy.

## 12. Kiểm thử thư viện và tích hợp

Không nên chỉ kiểm thử một token hợp lệ. Bộ kiểm thử cần chứng minh validator từ chối đúng các trường hợp sai và các profile không bị nhầm lẫn.

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Positive vectors | Token hợp lệ theo từng thuật toán được cho phép | Xác minh thành công |
| Negative signature | Chỉnh payload hoặc signature | Từ chối |
| Algorithm | none, thuật toán ngoài allowlist, alg/key mismatch | Từ chối |
| Key type | HMAC secret bị dùng như public key hoặc ngược lại | Từ chối |
| ECDSA | Chữ ký sai encoding/độ dài | Từ chối an toàn |
| RSA-PSS | Sai hash/MGF1/salt parameter | Từ chối |
| Parsing | JSON duplicate member, Base64URL lỗi, sai kiểu claim | Từ chối theo parser/profile policy |
| Header | crit không hỗ trợ, kid lạ, jku/x5u ngoài trust | Từ chối; không fetch nguồn tùy ý |
| JWE | Ciphertext/tag bị sửa, alg/enc ngoài allowlist | Decrypt thất bại |
| Nested | JWE hợp lệ nhưng JWS bên trong sai | Từ chối toàn bộ |
| Claims | iss, aud, exp, nbf, typ hoặc required claim sai | Từ chối |
| Key rotation | Token dùng khóa mới/cũ trong overlap | Hành vi đúng theo rotation policy |
| JWKS outage | Timeout hoặc endpoint lỗi | Failure mode đúng, không bypass verify |
| Resource limits | Token quá lớn hoặc nested quá sâu | Từ chối trước khi tiêu tốn tài nguyên quá mức |
| Interoperability | Token tạo bởi implementation độc lập | Kết quả nhất quán theo RFC/profile |
| Regression | Cập nhật thư viện | Toàn bộ negative và positive tests tiếp tục đạt |

### 12.1. Dùng test vector và kiểm thử liên thông

Test vector chuẩn giúp xác nhận cách triển khai thuật toán và serialization. Interoperability test với một implementation độc lập giúp phát hiện giả định riêng của một thư viện.

Không chỉ test token do chính ứng dụng tạo ra rồi xác minh lại bằng chính thư viện đó. Hai phía có thể cùng mắc một lỗi giống nhau và vẫn pass.

### 12.2. Fuzzing và kiểm thử parser

Parser JOSE là bề mặt tấn công. Nếu thư viện hỗ trợ fuzzing hoặc có kết quả fuzzing công khai, hãy xem xét. Ở cấp tích hợp, có thể fuzz các đầu vào sai định dạng trong môi trường kiểm thử để xác nhận:

- Không crash hoặc treo.
- Không tiêu tốn CPU/bộ nhớ quá mức.
- Không truy cập URL tùy ý.
- Không tạo context xác thực một phần.
- Không làm lộ token hoặc secret trong lỗi.

Không chạy fuzzing trực tiếp trên production.

## 13. Quản lý dependency và cập nhật bảo mật

Thư viện mật mã và JOSE nằm trên đường đi xác thực của hệ thống. Một lỗ hổng parser hoặc thuật toán có thể ảnh hưởng trực tiếp tới mọi API sử dụng nó.

Quy trình quản lý:

1. Pin phiên bản dependency đã đánh giá.
2. Theo dõi security advisory và CVE của thư viện cùng crypto provider.
3. Cập nhật bản vá bảo mật theo SLA của tổ chức.
4. Đọc release notes để biết thay đổi về default algorithm, parser hoặc validation.
5. Chạy lại positive/negative/interoperability tests trước khi phát hành.
6. Có kế hoạch rollback an toàn nếu bản cập nhật gây lỗi liên thông.
7. Kiểm tra dependency transitive và nguồn phân phối package.

Không tự động cập nhật mọi phiên bản vào production mà không kiểm thử. Cũng không trì hoãn bản vá quan trọng vô thời hạn vì lo ngại thay đổi nhỏ. Cần quy trình đánh giá mức độ ảnh hưởng và thời gian xử lý rõ ràng.

### 13.1. Supply-chain security

Kiểm tra:

- Package có đúng publisher/repository chính thức không?
- Artifact có checksum hoặc chữ ký phát hành khi dự án cung cấp không?
- Dependency tree có package không cần thiết hoặc không còn bảo trì không?
- License có phù hợp không?
- Build có thể tái lập hoặc kiểm tra provenance ở mức tổ chức yêu cầu không?
- Có cơ chế phát hiện package giả mạo hoặc dependency confusion không?

Không tải thư viện từ mirror hoặc package name không xác định chỉ vì kết quả tìm kiếm đầu tiên.

## 14. Các lỗi tích hợp thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Tự viết RSA/ECDSA/HMAC | Lỗi thuật toán, encoding và timing | Dùng crypto library đã kiểm chứng |
| Dùng crypto primitive nhưng tự ghép JOSE | Sai signing input, serialization hoặc key handling | Dùng JOSE/JWT library cấp cao |
| Tin alg từ header | Algorithm confusion | Allowlist từ policy tin cậy |
| Dùng một key cho mọi thuật toán | Key confusion và mở rộng tác động | Ràng buộc key type/use/algorithm |
| Tự serialize JSON trước khi verify | Xác minh byte sequence khác | Verify signing input nguyên gốc qua thư viện |
| Chỉ kiểm tra signature | Token sai issuer/audience/profile vẫn được chấp nhận | Claims và profile validation riêng |
| Tin kid/jku/x5u tùy ý | Key substitution hoặc SSRF | Resolver gắn với trust configuration |
| Bỏ qua JWE authentication tag | Chấp nhận plaintext bị sửa | Dùng authenticated decrypt API |
| Log raw token khi debug | Rò rỉ bearer credential | Redact token và log mã lỗi |
| Dùng thư viện không được duy trì | Không nhận bản vá và lỗi tương thích | Đánh giá bảo trì và advisory |
| Dùng default quá rộng | Thuật toán hoặc token profile ngoài ý muốn được chấp nhận | Cấu hình explicit policy |
| Không test negative cases | Không phát hiện validator chấp nhận token sai | Test vectors và regression suite |

## 15. Checklist triển khai

1. [ ] Không tự viết primitive mật mã hoặc thuật toán chữ ký.
2. [ ] Dùng thư viện JOSE/JWT được duy trì cho serialization, parsing, verify và decrypt.
3. [ ] Phân biệt crypto provider, JOSE library và application validation policy.
4. [ ] Chọn thư viện theo RFC/profile cần hỗ trợ, bảo trì, tài liệu, test và advisory.
5. [ ] Policy được chọn từ endpoint/configuration tin cậy, không từ token chưa xác minh.
6. [ ] Allowlist thuật toán riêng cho từng token profile.
7. [ ] Ràng buộc key type, key usage, key_ops và thuật toán.
8. [ ] Giới hạn kích thước, độ sâu nested, thời gian xử lý và số lần tải JWKS.
9. [ ] Key resolver chỉ dùng trust store/JWKS URI đã cấu hình; không fetch jku/x5u tùy ý.
10. [ ] Xử lý kid, JWKS cache, rotation và emergency key revocation có giới hạn.
11. [ ] JWS được verify trên signing input gốc; JWE chỉ dùng plaintext sau authenticated decryption.
12. [ ] Nested JWT được xác minh đầy đủ từng lớp.
13. [ ] Kiểm tra issuer, audience, typ/profile, thời gian và claims bắt buộc sau xác minh mật mã.
14. [ ] Kiểm tra revocation, replay, binding và authorization theo policy.
15. [ ] Không log token, secret hoặc plaintext claims nhạy cảm.
16. [ ] Có positive, negative, test vector, interoperability và regression tests.
17. [ ] Theo dõi CVE/advisory, cập nhật dependency và kiểm tra supply chain.

## 16. Tài liệu tiêu chuẩn liên quan

- **RFC 7515 — JSON Web Signature (JWS):** signing input, protected header và xác minh chữ ký.
- **RFC 7516 — JSON Web Encryption (JWE):** mã hóa và authenticated decryption.
- **RFC 7517 — JSON Web Key (JWK):** biểu diễn khóa và JWKS.
- **RFC 7518 — JSON Web Algorithms (JWA):** thuật toán JOSE và quy tắc biểu diễn.
- **RFC 7519 — JSON Web Token (JWT):** cấu trúc JWT và claims.
- **RFC 8725 — JSON Web Token Best Current Practices:** algorithm verification, issuer/audience validation, explicit typing và phòng token confusion.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile Access Token và validation tại Resource Server.
- **RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE:** thuật toán OKP/EdDSA trong JOSE.

**Nguyên tắc ghi nhớ:** Dùng thư viện đã được kiểm chứng để thực hiện primitive và xử lý JOSE/JWT; không tự ghép các thao tác mật mã thành một validator. Sau khi thư viện xác minh chữ ký hoặc giải mã thành công, ứng dụng vẫn phải áp dụng policy tin cậy về issuer, audience, token profile, thời gian, trạng thái và quyền. Thư viện tốt giảm lỗi triển khai, còn cấu hình đúng mới quyết định token nào được chấp nhận.
