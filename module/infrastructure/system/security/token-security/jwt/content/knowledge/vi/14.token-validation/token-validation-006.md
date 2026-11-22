# Xác minh chữ ký hoặc giải mã xác thực bằng thư viện phù hợp

## 1. Mục tiêu: kiểm tra bằng chứng mật mã đúng cách

JWT có thể được bảo vệ bằng **JSON Web Signature (JWS)** hoặc **JSON Web Encryption (JWE)**. Với JWS, bên nhận cần xác minh chữ ký hoặc MAC trên đúng dữ liệu đã được ký. Với JWE, bên nhận cần thực hiện quy trình quản lý khóa và giải mã nội dung, đồng thời xác minh tính toàn vẹn bằng authentication tag hoặc cơ chế xác thực được thuật toán quy định.

Đây là bước mật mã cốt lõi trong quá trình xác minh token. Những thao tác như Base64URL decode, parse JSON, đọc header, lấy claims hoặc tìm được khóa đều chưa chứng minh token hợp lệ. Kết quả chỉ đáng tin cậy khi thư viện JOSE thực hiện đúng phép xác minh/giải mã theo thuật toán đã được chính sách cho phép và dùng đúng khóa tin cậy.

Trong thực tế, nên dùng **thư viện JOSE/JWT được duy trì, triển khai đúng chuẩn và có API xác minh rõ ràng**. Không tự viết thuật toán chữ ký, MAC, mã hóa, padding, xử lý IV hoặc so sánh tag. Những chi tiết nhỏ như cách tạo signing input, tham số RSA-PSS, định dạng ECDSA signature, kiểm tra tag hay thứ tự xác thực đều có thể làm hỏng ranh giới bảo mật.

Nội dung này áp dụng cho Security - JSON Web Token (JWT) nói chung, không phụ thuộc Java, Spring Security hay một nền tảng cụ thể.

## 2. Phân biệt parse, verify và decrypt

Ba thao tác thường xuất hiện cạnh nhau nhưng có ý nghĩa khác nhau:

| Thao tác | Việc thực hiện | Điều có thể kết luận |
| --- | --- | --- |
| **Parse/decode** | Đọc Base64URL, JSON, JOSE header hoặc claims | Dữ liệu có thể được diễn giải theo một cấu trúc; chưa có bằng chứng tin cậy |
| **Verify JWS** | Kiểm tra chữ ký hoặc MAC trên signing input bằng khóa phù hợp | Nội dung JWS khớp với bằng chứng mật mã của khóa được dùng |
| **Decrypt JWE** | Quản lý/thiết lập khóa, giải mã ciphertext và xác minh authentication tag | Nội dung JWE được bảo vệ toàn vẹn theo cơ chế và khóa đã dùng |

Một thư viện có thể trả về payload ngay sau khi parse mà chưa xác minh. Không được nhầm API tên **decode**, **parse**, **read** hoặc **getClaims** với API đã thực hiện verify. Cần hiểu rõ hợp đồng của API trước khi dùng kết quả.

~~~text
raw JWT
  |
  +--> parse/decode ----------> header/claims chưa tin cậy
  |
  +--> verify JWS ------------> payload được bảo vệ bằng chữ ký/MAC
  |
  +--> decrypt JWE -----------> plaintext chỉ sau khi xác thực bảo vệ mã hóa
~~~

Ngay cả khi verify JWS hoặc decrypt JWE thành công, vẫn cần kiểm tra issuer, audience, thời gian, loại token và claims theo policy. Đặc biệt, một JWE được mã hóa bằng public key của người nhận có thể do bất kỳ bên nào biết public key tạo ra; giải mã thành công không tự động chứng minh nội dung đến từ issuer cụ thể.

## 3. Chọn thư viện JOSE phù hợp

Thư viện là một phần của ranh giới bảo mật. Trước khi tích hợp, cần đánh giá:

| Tiêu chí | Điều cần xác nhận |
| --- | --- |
| Tuân thủ chuẩn | Hỗ trợ đúng RFC 7515 (JWS), RFC 7516 (JWE), RFC 7517 (JWK), RFC 7518 (JWA) và profile JWT cần dùng |
| Bảo trì | Có phiên bản còn được hỗ trợ, lịch sử sửa lỗi bảo mật và quy trình cập nhật rõ ràng |
| API xác minh | Phân biệt rõ parse với verify/decrypt; không trả claims chưa xác minh như kết quả đã tin cậy |
| Allowlist thuật toán | Có thể cấu hình rõ thuật toán được phép; không tự chấp nhận mọi alg trong header |
| Quản lý khóa | Hỗ trợ khóa đúng loại, kiểm tra metadata và key resolver bị giới hạn trong nguồn tin cậy |
| Xử lý mật mã | Dùng primitive đã được kiểm chứng; xử lý đúng signing input, tag, padding, tham số và so sánh nhạy cảm |
| Xử lý lỗi | Phân biệt lỗi cú pháp, khóa, chữ ký, tag và thuật toán; không fallback sang chế độ yếu hơn |
| Giới hạn tài nguyên | Có hoặc cho phép đặt giới hạn token, header, payload, độ sâu, số khóa và thời gian xử lý |
| Kiểm thử | Có bộ kiểm thử tương thích JOSE, vector chuẩn và khả năng kiểm thử lỗi/đầu vào bất thường |

Không chọn thư viện chỉ vì API ngắn hoặc dễ dùng. Cần đọc tài liệu để biết:

- Hàm nào chỉ parse và hàm nào thực sự xác minh chữ ký.
- Thuật toán có được cấu hình từ ứng dụng hay được suy ra tự do từ header.
- Key resolver có thể truy cập mạng hoặc nguồn khóa nào.
- Claims có được trả về trước khi xác minh thành công không.
- JWE plaintext có bị lộ trước khi tag được kiểm tra không.
- Lỗi mật mã có thể bị bắt rồi biến thành kết quả thành công hay không.

Thư viện đúng chuẩn vẫn cần cấu hình đúng. Một API an toàn nếu được gọi với allowlist rộng, nguồn khóa sai hoặc policy mặc định không phù hợp vẫn có thể dẫn đến xác minh không an toàn.

## 4. Chuẩn bị đầu vào và policy trước khi gọi thư viện

Trước khi thực hiện phép mật mã, hệ thống cần:

1. Xác định endpoint và validation policy từ ngữ cảnh tin cậy.
2. Lấy issuer, audience, token profile và allowlist thuật toán từ policy.
3. Lấy nguồn khóa đã được gắn với issuer; không lấy JWKS URL tùy ý từ token.
4. Giới hạn kích thước token và từng thành phần trước khi parse.
5. Kiểm tra đúng loại serialization được endpoint chấp nhận.
6. Parse protected header nghiêm ngặt, từ chối JSON trùng trường hoặc kiểu dữ liệu sai.
7. Đối chiếu alg, typ và crit với policy.
8. Chọn ứng viên khóa tương thích với thuật toán và mục đích sử dụng.

Đối với JWS, khóa xác minh phải được tin cậy độc lập với token. Đối với JWE, khóa giải mã/thiết lập khóa phải thuộc về bên nhận hoặc được cấp theo hợp đồng đã xác thực. Không sử dụng **jku**, **x5u** hay khóa **jwk** nhúng trong header làm nguồn tin cậy tự động.

## 5. Xác minh chữ ký JWS

### 5.1. Signing input là dữ liệu chính xác phải được xác minh

Với JWS Compact thông thường, signing input được tạo từ hai thành phần đã mã hóa Base64URL:

~~~text
ASCII(
  BASE64URL(UTF8(protected-header))
  + "."
  + BASE64URL(payload)
)
~~~

Chữ ký được tạo trên chính signing input đó. Bên nhận phải xác minh **đúng các octet đã được ký**, không parse JSON rồi serialize lại theo định dạng khác để tạo chuỗi mới.

Ví dụ hai JSON object có thể mang cùng ý nghĩa nhưng khác thứ tự thuộc tính hoặc khoảng trắng:

~~~json
{"alg":"RS256","kid":"key-1"}
~~~

~~~json
{
  "kid": "key-1",
  "alg": "RS256"
}
~~~

Hai biểu diễn này không tạo ra cùng Base64URL segment và do đó không tạo ra cùng signing input. Nếu bên nhận tự parse rồi serialize lại, chữ ký có thể bị kiểm tra trên dữ liệu khác với thông điệp ban đầu. Hãy truyền chuỗi JWS gốc cho thư viện thực hiện verify theo chuẩn.

Các trường hợp detached payload hoặc JWS JSON Serialization cần được hỗ trợ theo profile cụ thể. Không tự suy đoán hoặc ghép payload rời vào token nếu hợp đồng không định nghĩa chính xác cách làm.

### 5.2. Quy trình verify

Một luồng JWS có chữ ký bất đối xứng thường gồm:

1. Chọn policy và allowlist thuật toán từ endpoint/issuer.
2. Parse JWS Compact trong giới hạn.
3. Đọc protected header để lấy alg và kid dưới dạng dữ liệu chưa tin cậy.
4. Chọn public key phù hợp trong JWKS/kho khóa đã gắn với issuer.
5. Kiểm tra loại khóa, metadata và mục đích verify.
6. Gọi thư viện để xác minh chữ ký trên signing input gốc.
7. Chỉ khi verify thành công mới sử dụng payload làm claims đầu vào cho bước kiểm tra tiếp theo.

Với HMAC, thư viện cần xác minh MAC bằng shared secret đủ mạnh. So sánh MAC phải được thực hiện theo cách chống rò rỉ thời gian (constant-time) phù hợp. Không tự viết phép so sánh byte thông thường cho chữ ký/MAC; dùng API của thư viện mật mã.

### 5.3. Chữ ký hợp lệ có phạm vi kết luận giới hạn

Chữ ký hợp lệ chứng minh dữ liệu được bảo vệ khớp với khóa xác minh tương ứng. Nó không tự chứng minh:

- Khóa đó thuộc issuer mà ứng dụng mong đợi, nếu nguồn khóa chưa được gắn với issuer.
- Token dành cho API hiện tại.
- Token còn hiệu lực hoặc chưa bị thu hồi.
- Chủ thể có quyền truy cập tài nguyên.
- Token là access token thay vì ID token hoặc loại JWT khác.

Do đó, verify JWS chỉ là một bước trong validation pipeline.

## 6. Các lỗi dễ gặp khi xác minh JWS

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chỉ decode payload rồi tin claims | Giả mạo subject, scope, role hoặc audience | Chỉ dùng claims sau verify thành công |
| Tự serialize lại header/payload trước verify | Xác minh trên signing input khác | Dùng token gốc và thư viện JOSE |
| Cho phép mọi alg | Algorithm confusion hoặc downgrade | Cấu hình allowlist rõ ràng |
| Chấp nhận alg none trong profile yêu cầu chữ ký | Bỏ qua bằng chứng chữ ký | Từ chối thuật toán không bảo vệ |
| Dùng RSA public key làm HMAC secret | Có thể tạo chữ ký giả theo cách diễn giải nhầm khóa | Ràng buộc thuật toán với key type |
| Thử nhiều khóa/thuật toán không giới hạn | Tốn CPU, tạo khác biệt lỗi và mở rộng bề mặt tấn công | Giới hạn ứng viên và thuật toán |
| So sánh MAC/chữ ký thủ công | Lỗi timing hoặc lỗi định dạng | Dùng verify API của thư viện |
| Bắt mọi lỗi rồi tiếp tục với payload | Fail-open | Mọi lỗi verify đều phải dẫn tới từ chối |

## 7. Giải mã xác thực JWE

JWE Compact có năm thành phần:

~~~text
BASE64URL(protected-header).
BASE64URL(encrypted-key).
BASE64URL(iv).
BASE64URL(ciphertext).
BASE64URL(authentication-tag)
~~~

JWE có thể sử dụng nhiều phương pháp quản lý khóa và thuật toán mã hóa nội dung. Bên nhận cần kiểm tra cặp **alg/enc** theo policy, chọn đúng khóa giải mã hoặc khóa quản lý khóa, rồi dùng thư viện thực hiện toàn bộ quy trình.

### 7.1. Các bước xử lý

1. Chọn policy JWE từ ngữ cảnh tin cậy.
2. Parse đúng JWE Compact hoặc serialization mà profile cho phép; giới hạn kích thước từng phần.
3. Đối chiếu alg và enc với allowlist; từ chối thuật toán không hỗ trợ hoặc không được phép.
4. Chọn khóa giải mã/quản lý khóa đúng loại và đúng mục đích.
5. Kiểm tra các tham số theo thuật toán như encrypted key, IV, authentication tag và protected header.
6. Gọi thư viện để quản lý khóa, giải mã ciphertext và xác minh authentication tag.
7. Chỉ sử dụng plaintext sau khi xác thực thành công hoàn toàn.
8. Nếu plaintext là nested JWT, tiếp tục xác minh lớp bên trong theo profile đã định nghĩa.

Không tự giải mã ciphertext rồi xử lý plaintext trước khi xác minh tag. Với mã hóa có xác thực, authentication tag là một phần thiết yếu của phép kiểm tra; dữ liệu plaintext chưa xác thực không được chuyển vào parser claims, logger, business logic hoặc bất kỳ thành phần nào khác.

### 7.2. Không để lộ plaintext khi tag sai

Khi authentication tag không hợp lệ, thư viện phải trả về lỗi xác thực và không cung cấp plaintext có thể sử dụng. Ứng dụng không được:

- Xử lý một phần plaintext trước khi kiểm tra tag.
- Ghi plaintext vào log để chẩn đoán khi giải mã thất bại.
- Phân biệt công khai quá chi tiết giữa lỗi padding, tag, khóa hoặc ciphertext nếu điều đó tạo oracle.
- Thử một thuật toán khác hoặc một khóa không thuộc policy chỉ vì lần giải mã đầu thất bại.

Với JWE dùng AES-GCM, xác minh tag là phần của authenticated decryption. Với các cấu hình JOSE khác, như tổ hợp CBC-HMAC, phải tuân thủ đúng thứ tự và quy tắc xác thực được chuẩn quy định; cách đơn giản và an toàn là để thư viện JOSE thực hiện trọn vẹn thuật toán đã chọn.

### 7.3. Giải mã thành công không luôn xác thực issuer

Trong mô hình mã hóa bằng public key của người nhận, bất kỳ ai biết public key đều có thể tạo một JWE gửi tới người nhận. Do đó, authentication tag hợp lệ chứng minh nội dung được bảo vệ trong phạm vi khóa/mô hình mã hóa, nhưng không tự chứng minh ai là bên phát hành JWT.

Nếu cần bằng chứng về issuer, có thể dùng nested JWT: issuer ký JWS bằng private key, sau đó nội dung được mã hóa thành JWE cho người nhận. Bên nhận giải mã lớp JWE rồi xác minh chữ ký JWS bên trong theo issuer/key policy. Trình tự và cấu trúc nested phải được xác định trước.

## 8. Nested JWT: xác minh đúng từng lớp

Một token có thể kết hợp chữ ký và mã hóa:

~~~mermaid
flowchart TD
    A["Nhận JWE bên ngoài"] --> B["Kiểm tra alg/enc và chọn khóa nhận"]
    B --> C["Authenticated decryption"]
    C --> D{"Tag hợp lệ?"}
    D -- "Không" --> X["Từ chối, không dùng plaintext"]
    D -- "Có" --> E["Nhận JWS bên trong"]
    E --> F["Chọn issuer policy và khóa verify"]
    F --> G["Xác minh chữ ký JWS"]
    G --> H{"Chữ ký hợp lệ?"}
    H -- "Không" --> X
    H -- "Có" --> I["Kiểm tra claims và token profile"]
    I --> J["Tạo kết quả đã xác minh"]
~~~

Thứ tự thực tế phụ thuộc cấu trúc nested và profile. Một JWT được ký rồi mã hóa (JWS nằm trong JWE) thường cần giải mã lớp ngoài trước, sau đó xác minh JWS bên trong. Trường **cty** có thể báo nội dung lồng nhưng vẫn là dữ liệu header cần đối chiếu với policy.

Mỗi lớp cần:

- Đúng serialization và loại token.
- Allowlist thuật toán riêng.
- Nguồn khóa đúng issuer/recipient.
- Kiểm tra chữ ký hoặc authenticated decryption.
- Giới hạn số lớp, kích thước và thời gian xử lý.
- Kiểm tra claims theo hợp đồng.

Không để nested token tự tạo thêm lớp không giới hạn hoặc thay đổi issuer policy của lớp bên trong.

## 9. Sử dụng API của thư viện một cách an toàn

Tên hàm giữa các thư viện khác nhau, nhưng quy tắc tích hợp có thể thống nhất:

| Yêu cầu | Hành vi mong đợi từ thư viện/API |
| --- | --- |
| Verify JWS | Nhận token gốc, thuật toán được cho phép và khóa phù hợp; trả kết quả xác minh rõ ràng |
| Parse header | Chỉ trả dữ liệu chưa tin cậy; không tự động tạo trust hoặc tải URL trong header |
| Key resolver | Chỉ tìm trong nguồn khóa đã cấu hình; giới hạn số ứng viên và thao tác mạng |
| Decrypt JWE | Chỉ trả plaintext sau khi authentication tag được xác minh thành công |
| Algorithm policy | Có thể khóa thuật toán được phép; không phụ thuộc hoàn toàn vào alg của token |
| Claims | Có cách lấy claims đã được xác minh hoặc phân biệt rõ kết quả chưa xác minh |
| Failure | Trả lỗi khi chữ ký/tag/khóa/thuật toán sai; không trả một kết quả “gần đúng” |

### 9.1. Mã giả xác minh JWS

~~~text
function validateSignedJwt(rawToken, trustedPolicy):
    require byteLength(rawToken) <= trustedPolicy.maxTokenBytes
    parsed = joseLibrary.parseJwsStrict(rawToken)

    header = parsed.protectedHeader
    require header.alg in trustedPolicy.allowedSignatureAlgorithms
    require header.crit contains only supported critical parameters

    key = trustedPolicy.trustedKeyResolver.resolve(
        issuer = trustedPolicy.issuer,
        kid = header.kid,
        algorithm = header.alg
    )
    require key is compatible with header.alg
    require key is permitted for signature verification

    verified = joseLibrary.verifyJws(
        originalCompactToken = rawToken,
        key = key,
        allowedAlgorithms = trustedPolicy.allowedSignatureAlgorithms
    )
    require verified.success

    claims = verified.payload
    require validateIssuerAudienceTimeAndProfile(claims, header, trustedPolicy)
    return ValidatedTokenContext(claims, trustedPolicy.id)
~~~

### 9.2. Mã giả giải mã xác thực JWE

~~~text
function validateEncryptedJwt(rawToken, trustedPolicy):
    require byteLength(rawToken) <= trustedPolicy.maxTokenBytes
    parsed = joseLibrary.parseJweStrict(rawToken)

    header = parsed.protectedHeader
    require header.alg in trustedPolicy.allowedKeyManagementAlgorithms
    require header.enc in trustedPolicy.allowedContentEncryptionAlgorithms
    require criticalHeadersAreSupported(header, trustedPolicy)

    key = trustedPolicy.decryptionKeyResolver.resolve(
        issuerOrRecipient = trustedPolicy.recipientContext,
        kid = header.kid,
        algorithm = header.alg
    )
    require key is compatible with header.alg and header.enc

    plaintext = joseLibrary.authenticatedDecryptJwe(
        originalCompactToken = rawToken,
        key = key,
        allowedKeyManagementAlgorithms = trustedPolicy.allowedKeyManagementAlgorithms,
        allowedContentEncryptionAlgorithms = trustedPolicy.allowedContentEncryptionAlgorithms
    )
    require plaintext.authenticationSucceeded
    require byteLength(plaintext.bytes) <= trustedPolicy.maxPlaintextBytes

    return validateInnerContentOrNestedJwt(plaintext.bytes, trustedPolicy)
~~~

Đây là pseudocode mô tả hợp đồng mong muốn, không phải API của một thư viện cụ thể. Nếu thư viện không cung cấp cách cấu hình allowlist hoặc không bảo đảm plaintext chỉ xuất hiện sau khi xác thực tag, cần chọn thư viện khác hoặc xây dựng lớp tích hợp có thể chứng minh các điều kiện đó.

## 10. Xử lý lỗi và fail closed

Mọi lỗi liên quan đến xác minh mật mã phải dẫn tới từ chối token. Một số nhóm lỗi thường gặp:

| Nhóm lỗi | Ví dụ | Kết quả |
| --- | --- | --- |
| Cú pháp | Sai số thành phần, Base64URL/JSON không hợp lệ | Từ chối |
| Policy | alg hoặc enc ngoài allowlist, typ không phù hợp | Từ chối |
| Khóa | Không tìm thấy kid, key type sai, khóa không đủ mạnh | Từ chối |
| JWS | Chữ ký/MAC không hợp lệ | Từ chối |
| JWE | Tag sai, ciphertext hỏng, giải mã thất bại | Từ chối và không dùng plaintext |
| Claims | Issuer, audience, exp, nbf hoặc profile không đạt | Từ chối |
| Hạ tầng | JWKS timeout, kho khóa lỗi, HSM không sẵn sàng | Từ chối theo chính sách; không bỏ verify |

Phản hồi bên ngoài nên đủ để client hiểu thông tin xác thực không hợp lệ, nhưng không tiết lộ chi tiết giúp dò khóa hoặc tạo oracle. Log nội bộ có thể ghi mã nguyên nhân đã chuẩn hóa, policy ID và request ID; không ghi token, secret, private key hoặc plaintext nhạy cảm.

Không viết logic kiểu:

~~~text
try:
    verify(token)
catch error:
    return decodedPayload
~~~

Đây là **fail open**: mọi lỗi xác minh đều bị biến thành thành công. Cách đúng là thất bại ở bất kỳ bước bắt buộc nào thì dừng và từ chối.

## 11. Kiểm thử thư viện và tích hợp mật mã

Không chỉ kiểm thử một token hợp lệ. Cần xác nhận thư viện và cấu hình từ chối đúng các đầu vào lỗi:

| Nhóm | Ca kiểm thử |
| --- | --- |
| JWS cơ bản | Chữ ký đúng, chữ ký sai, payload/header bị sửa, signing input khác một byte |
| Thuật toán | alg ngoài allowlist, none, HS/RS confusion, tham số RSA-PSS sai |
| Khóa | kid không có, khóa sai issuer, sai kty, EC curve sai, RSA quá nhỏ, HMAC secret quá ngắn |
| Biểu diễn | Base64URL lỗi, JSON duplicate member, token sai số phần, whitespace bất thường |
| JWE | Ciphertext bị sửa, IV/tag sai, khóa sai, alg/enc ngoài allowlist, plaintext quá lớn |
| Nested JWT | JWE hợp lệ nhưng JWS bên trong sai, lớp lồng quá sâu, sai token profile |
| Lỗi thư viện | Exception/timeout, provider lỗi, key resolver không sẵn sàng, HSM lỗi |
| Không rò rỉ | Tag sai không trả plaintext, log không có token/secret, phản hồi không tạo oracle |
| Tương thích | Test vector chuẩn JOSE, token từ issuer thực, rotation và nhiều phiên bản khóa |

Nên dùng test vector từ RFC và bộ kiểm thử tương thích của thư viện. Có thể fuzz parser và kiểm tra khác biệt giữa các phiên bản thư viện. Mỗi lần nâng cấp thư viện mật mã cần chạy lại các kiểm thử bảo mật trọng yếu và rà soát thay đổi mặc định về thuật toán.

## 12. Quan sát vận hành

Các chỉ số nên theo dõi:

- Tỷ lệ JWS verify thành công/thất bại theo policy và issuer.
- Tỷ lệ JWE decrypt thành công/thất bại, đặc biệt lỗi authentication tag.
- Số lỗi thuật toán ngoài allowlist, khóa không tìm thấy hoặc metadata không tương thích.
- Thời gian verify/decrypt, mức CPU và số thao tác mật mã.
- Số lần refresh JWKS, lỗi key resolver và trạng thái HSM/secret store.
- Số token nested và mức độ tiêu thụ tài nguyên theo số lớp.

Không ghi toàn bộ token, chữ ký, plaintext, HMAC secret hoặc private key. Hạn chế ghi cả payload/claims vì chúng có thể chứa dữ liệu cá nhân hoặc quyền truy cập. Dùng mã lỗi, policy ID và request ID để truy vết.

## 13. Checklist tích hợp thư viện

1. [ ] Thư viện JOSE/JWT được duy trì, có hỗ trợ chuẩn và cập nhật bảo mật.
2. [ ] Parse/decode được phân biệt rõ với verify/decrypt.
3. [ ] JWS được xác minh trên signing input gốc; không serialize lại JSON.
4. [ ] Allowlist thuật toán được cấu hình từ policy tin cậy; không tin alg trong token một cách độc lập.
5. [ ] Key resolver chỉ dùng nguồn khóa đã gắn với issuer/recipient và giới hạn ứng viên.
6. [ ] Verify dùng đúng key type, metadata và mục đích khóa.
7. [ ] HMAC/signature/tag được xử lý bằng API mật mã an toàn; không tự so sánh hoặc viết thuật toán.
8. [ ] JWE kiểm tra cặp alg/enc và không để lộ plaintext trước khi tag hợp lệ.
9. [ ] Nested JWT có thứ tự xác minh, profile và giới hạn lớp rõ ràng.
10. [ ] Lỗi mật mã, lỗi khóa và lỗi hạ tầng đều fail closed.
11. [ ] Claims chỉ được dùng sau khi verify/decrypt thành công và validation policy đạt.
12. [ ] Có test vector, negative tests, kiểm thử nâng cấp và log không lộ dữ liệu nhạy cảm.

## 14. Tài liệu tiêu chuẩn liên quan

- **RFC 7515 — JSON Web Signature (JWS):** signing input, chữ ký và quy trình xác minh JWS.
- **RFC 7516 — JSON Web Encryption (JWE):** quản lý khóa, mã hóa nội dung, authentication tag và giải mã.
- **RFC 7517 — JSON Web Key (JWK):** biểu diễn khóa và metadata khóa.
- **RFC 7518 — JSON Web Algorithms (JWA):** thuật toán và tham số mật mã JOSE.
- **RFC 7519 — JSON Web Token (JWT):** JWT Claims Set và cấu trúc token.
- **RFC 8725 — JSON Web Token Best Current Practices:** thực hành xác minh JWT, thuật toán, issuer, audience và token confusion.
- **RFC 7797 — JWS Unencoded Payload Option:** quy tắc đặc biệt về payload không mã hóa trong JWS.

**Nguyên tắc ghi nhớ:** Parse chỉ đọc dữ liệu; JWS verify kiểm tra chữ ký/MAC trên đúng signing input; JWE authenticated decrypt chỉ được cung cấp plaintext sau khi kiểm tra tag thành công. Hãy giao các thao tác mật mã cho thư viện JOSE phù hợp, cấu hình thuật toán và khóa theo policy tin cậy, rồi tiếp tục xác minh claims trước khi chấp nhận token.
