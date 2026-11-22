# Tiêu chí chọn thư viện JOSE được duy trì và có kiểm thử bảo mật

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Tích hợp thư viện  
> **Phạm vi:** Đánh giá và lựa chọn thư viện JOSE/JWT cho hệ thống thực tế dựa trên tiêu chí mật mã, API, kiểm thử, bảo trì và chuỗi cung ứng; không phụ thuộc Java, Spring hay framework cụ thể.

JWT và JOSE liên quan trực tiếp tới ranh giới xác thực và ủy quyền. Một lỗi trong cách parse header, chọn thuật toán, nạp khóa hoặc xác minh claims có thể khiến hệ thống chấp nhận token giả, nhầm token giữa các issuer hoặc bỏ qua một ràng buộc bảo mật. Vì vậy, chọn thư viện JOSE không nên chỉ dựa vào số lượng thuật toán hỗ trợ, mức độ phổ biến hay hiệu năng benchmark.

Một thư viện phù hợp cần có **API an toàn theo mặc định, hành vi tuân thủ chuẩn có thể kiểm chứng, khả năng xử lý khóa đúng mục đích, bộ kiểm thử bảo mật và quy trình bảo trì đáng tin cậy**. Ứng dụng vẫn phải xây dựng policy xác minh riêng cho issuer, audience, token profile và quyền truy cập; thư viện không thể tự biết toàn bộ hợp đồng nghiệp vụ.

## 1. Xác định đúng phạm vi cần thư viện

### 1.1. JOSE không chỉ là JWT

JOSE (JSON Object Signing and Encryption) là tập chuẩn mô tả cách biểu diễn và bảo vệ nội dung JSON bằng chữ ký, MAC, mã hóa và khóa. Các thành phần thường gặp:

| Thành phần | Vai trò | Chuẩn chính |
|---|---|---|
| JWS | Chữ ký số hoặc MAC trên nội dung | RFC 7515 |
| JWE | Mã hóa nội dung và bảo vệ tính toàn vẹn theo cấu trúc JWE | RFC 7516 |
| JWK/JWKS | Biểu diễn một khóa hoặc tập khóa | RFC 7517 |
| JWA | Đăng ký thuật toán và tham số JOSE | RFC 7518 |
| JWT | Định dạng claims thường được mang trong JWS/JWE | RFC 7519 |
| JWK Thumbprint | Tạo định danh fingerprint từ các thành phần JWK chuẩn hóa | RFC 7638 |
| Unencoded Payload Option | JWS với payload không Base64url encode theo profile cụ thể | RFC 7797 |

Một thư viện có thể hỗ trợ JWT nhưng không hỗ trợ đầy đủ JWE, JWK hoặc các dạng serialization cần thiết. Ngược lại, thư viện JOSE cấp thấp có thể xử lý JWS/JWE nhưng không cung cấp policy xác minh JWT theo profile ứng dụng.

### 1.2. Liệt kê use case trước khi so sánh thư viện

Hãy xác định hệ thống cần:

- Phát hành JWT có chữ ký hay MAC.
- Xác minh access token từ một hay nhiều issuer.
- Xử lý JWE hoặc nested JWT.
- Đọc và cập nhật JWKS, xoay vòng khóa.
- Hỗ trợ DPoP, certificate-bound token hoặc JWK thumbprint.
- Xử lý detached payload, critical header hoặc serialization đặc biệt.
- Tạo token cho OAuth/OIDC hay token nghiệp vụ nội bộ.
- Chạy trong môi trường có yêu cầu FIPS, HSM/KMS hoặc phần cứng bảo vệ khóa.

Không bật một tính năng chỉ vì thư viện có hỗ trợ. Mỗi định dạng và thuật toán được bật đều làm tăng bề mặt cần cấu hình, kiểm thử và vận hành.

### 1.3. Phân biệt ba lớp trách nhiệm

| Lớp | Trách nhiệm | Ví dụ |
|---|---|---|
| JOSE/crypto library | Parse/serialize JOSE, thực hiện chữ ký, MAC, mã hóa và xử lý JWK | Xác minh JWS bằng RSA public key |
| Token validation policy | Ràng buộc thuật toán, issuer, audience, typ, thời gian và claims bắt buộc | Chỉ nhận access token từ issuer đã cấu hình |
| Application authorization | Quyết định principal được phép làm gì trên resource cụ thể | Subject có quyền sửa đơn hàng này không? |

Một thư viện có thể cung cấp helper ở nhiều lớp, nhưng cần biết chính xác helper nào chỉ kiểm tra chữ ký và helper nào thực hiện đầy đủ validation. Không suy ra “verify thành công” đồng nghĩa token đã được xác thực và được phép dùng.

## 2. Tiêu chí an toàn theo mặc định của API

### 2.1. Thuật toán phải được ứng dụng ghim rõ ràng

API xác minh cần cho phép ứng dụng truyền allowlist thuật toán từ cấu hình tin cậy. Không nên có hành vi mặc định chấp nhận mọi thuật toán thư viện hỗ trợ hoặc tự chọn thuật toán chỉ dựa trên giá trị **alg** trong header chưa xác minh.

Ví dụ yêu cầu:

- Endpoint dùng RS256 chỉ chấp nhận RS256 theo contract.
- Không tự chuyển sang HS256 khi xác minh RSA thất bại.
- Không chấp nhận **alg: none** trừ một use case đặc biệt được chuẩn/profile cho phép và có thiết kế trust riêng; với access token thông thường phải từ chối.
- Không có fallback giữa các họ RSA, EC, HMAC hoặc EdDSA.
- Khi thuật toán bị tắt hoặc deprecated, API không tự quay về thuật toán cũ.

Thư viện tốt cần làm cho việc ghim thuật toán rõ ràng, dễ review và khó vô tình bỏ sót.

### 2.2. Ràng buộc thuật toán với loại khóa

Thư viện phải phân biệt key type và thuật toán:

| Thuật toán | Loại khóa mong đợi | Lưu ý |
|---|---|---|
| HS256/384/512 | Secret đối xứng (oct) | Secret phải đủ mạnh và giữ kín ở mọi bên có quyền tạo MAC |
| RS256/384/512 | RSA | Private key ký, public key xác minh |
| PS256/384/512 | RSA | Tham số PSS phải theo JWA |
| ES256/384/512 | EC | Curve và định dạng chữ ký phải đúng thuật toán |
| EdDSA | OKP | Chỉ dùng curve/thuật toán được JOSE profile hỗ trợ |

API không được âm thầm chuyển public key RSA thành HMAC secret hoặc cho phép một key object dùng với thuật toán không tương thích. Cần kiểm tra cả metadata **kty**, **alg**, **use**, **key_ops**, curve và tham số khóa khi có.

### 2.3. Không có default yếu hoặc mơ hồ

Kiểm tra hành vi khi ứng dụng không truyền:

- Danh sách thuật toán.
- Issuer/audience.
- Nguồn khóa.
- Token type/profile.
- Giới hạn kích thước và độ sâu parse.
- Chính sách critical header.

Nếu thiếu cấu hình bắt buộc, thư viện hoặc wrapper nên yêu cầu ứng dụng khai báo thay vì tự mở rộng mức chấp nhận. Một API “tiện dụng” nhưng tự suy đoán thuật toán/issuer có thể che giấu lỗi cấu hình.

### 2.4. API tách parse, verify và validate rõ ràng

Tên hàm và kiểu kết quả phải giúp người tích hợp phân biệt:

- Decode/parse token nhưng chưa xác minh.
- Xác minh chữ ký hoặc MAC.
- Xác minh toàn bộ token theo profile.
- Giải mã JWE.
- Kiểm tra claims và authorization.

Payload sau khi decode nhưng trước khi xác minh phải được xem là dữ liệu không tin cậy. API nên biểu diễn trạng thái này rõ, tránh trả về cùng một kiểu “VerifiedToken” cho cả token chưa xác minh và đã xác minh.

### 2.5. Lỗi phải fail closed

Khi chữ ký sai, key không tìm thấy, thuật toán không được phép, claim bắt buộc thiếu hoặc cấu trúc không hợp lệ, thư viện phải báo lỗi rõ và không trả payload như thể đã xác thực.

Không chấp nhận:

- Trả về claims đã decode sau khi verify thất bại mà caller dễ nhầm là thành công.
- Tự thử thuật toán khác sau lỗi.
- Bỏ qua chữ ký vì JWKS endpoint tạm thời lỗi.
- Tự bỏ qua claim không hiểu nhưng profile yêu cầu phải xử lý.
- Trả về giá trị mặc định cho trường bảo mật bị thiếu.

## 3. Độ bao phủ chuẩn JOSE/JWT

### 3.1. Kiểm tra đúng phiên bản và profile

Không chỉ hỏi thư viện “có hỗ trợ JWT không”. Hãy lập danh sách chuẩn/profile thực tế:

- JWS Compact Serialization.
- JWS JSON Serialization nếu use case cần.
- JWE Compact/JSON Serialization nếu dùng mã hóa.
- JWK/JWKS parsing và serialization.
- JWT claims và NumericDate.
- Nested JWT nếu profile yêu cầu.
- OAuth JWT Access Token Profile (RFC 9068) nếu phát hành/xác minh access token theo profile này.
- OpenID Connect ID Token nếu hệ thống có OIDC.

Một thư viện hỗ trợ một phần chuẩn vẫn có thể phù hợp, miễn là giới hạn được hiểu rõ và không cần tự viết phần mật mã/serialization còn thiếu.

### 3.2. Hành vi header JOSE

Thư viện cần xử lý đúng các trường:

| Header | Điều cần đánh giá |
|---|---|
| alg | Không được quyết định policy ngoài allowlist |
| kid | Chỉ là key selector trong trust domain đã chọn |
| typ | Hỗ trợ profile/token type validation theo ứng dụng |
| cty | Xử lý content type/nested JWT theo profile |
| crit | Từ chối critical parameter không được hỗ trợ hoặc không được ứng dụng xử lý |
| b64 | Chỉ hỗ trợ unencoded payload khi cần và tuân thủ RFC 7797 |
| jku, x5u | Không tự tải khóa/chứng thư từ URL chưa được tin cậy |
| x5c | Không tự coi certificate chain trong token là trust anchor |

Đặc biệt, **crit** không được âm thầm bỏ qua. Nếu token đánh dấu một header parameter là critical mà thư viện/ứng dụng không hiểu hoặc không xử lý, token phải bị từ chối.

### 3.3. Hành vi claims JWT

Thư viện có thể parse registered claims, nhưng ứng dụng phải kiểm tra profile yêu cầu. Xác minh:

- **iss**: issuer chính xác.
- **aud**: audience có chứa resource server hiện tại theo policy.
- **exp**: token chưa hết hạn.
- **nbf**: token đã đến thời điểm có hiệu lực.
- **iat**: thời điểm phát hành hợp lý theo policy.
- **jti**: định danh token nếu cần audit/revocation/replay protection.
- **sub**: subject đúng kiểu và semantics.
- **typ** hoặc token profile: access token, ID token hay token nghiệp vụ.

Đánh giá cách thư viện xử lý NumericDate, kiểu dữ liệu sai, claim trùng, leeway, clock skew và trường hợp claim thiếu. Không giả định mọi thư viện tự kiểm tra đầy đủ claims chỉ vì hàm tên là **verify**.

### 3.4. JWE và quản lý thuật toán mã hóa

Nếu hệ thống dùng JWE, cần đánh giá riêng:

- Key management algorithm (alg) và content encryption algorithm (enc).
- Kiểm tra authentication tag trước khi trả plaintext.
- Xử lý lỗi giải mã mà không làm lộ thông tin nhạy cảm.
- Giới hạn kích thước ciphertext và plaintext.
- Hành vi với compression (zip) và nguy cơ decompression bomb.
- Key wrapping, direct encryption, ECDH-ES hoặc các phương thức đang dùng.
- Tách biệt khóa ký và khóa mã hóa.

Không dùng JWE chỉ để “che payload” rồi bỏ qua authorization. Mã hóa không tự xác thực issuer theo mọi profile và không ngăn replay bearer token.

## 4. Chất lượng triển khai mật mã

### 4.1. Dựa trên crypto backend đáng tin cậy

JOSE library thường dựa vào một hoặc nhiều crypto provider/backend. Cần biết:

- Backend nào thực hiện RSA, ECDSA, HMAC, AES-GCM, ChaCha20-Poly1305 hoặc thuật toán liên quan.
- Phiên bản backend có còn được hỗ trợ và vá lỗi không.
- Có sử dụng implementation tự viết cho primitive mật mã không.
- Có tận dụng OS/hardware crypto hoặc HSM/KMS theo nhu cầu không.
- Có thể cấu hình provider một cách rõ ràng và kiểm tra được không.

Ưu tiên implementation dựa trên crypto primitive đã được sử dụng rộng rãi, kiểm thử và duy trì. Tự viết thuật toán mật mã trong ứng dụng hoặc thư viện JOSE là tín hiệu cần xem xét rất nghiêm túc.

### 4.2. Hành vi so sánh và xử lý bí mật

Đối với MAC, kiểm tra thư viện dùng phép so sánh an toàn theo thời gian (constant-time) ở nơi cần thiết. Với private key, secret và plaintext nhạy cảm:

- Không đưa dữ liệu vào exception message.
- Không log key material hoặc token.
- Hạn chế bản sao không cần thiết trong memory.
- Dùng cơ chế xóa/giải phóng phù hợp với runtime và backend khi có thể.
- Không hứa hẹn xóa sạch memory nếu runtime/garbage collector không bảo đảm điều đó.

### 4.3. Thuật toán và tham số khóa phù hợp chuẩn

Đánh giá:

- RSA key size tối thiểu theo JWA và policy mật mã hiện hành.
- HMAC secret có entropy và độ dài tối thiểu theo thuật toán.
- EC curve khớp chính xác với ES256/ES384/ES512.
- ECDSA signature encoding theo JWS (R || S), không nhầm với ASN.1 DER.
- RSA-PSS parameters theo JWA, không tự suy đoán salt length.
- EdDSA key type/curve theo RFC 8037.
- Không dùng thuật toán đã bị cấm hoặc deprecated trong policy triển khai.

Thư viện phải từ chối key material sai cấu trúc hoặc không đủ chất lượng, không âm thầm hạ cấp.

### 4.4. Randomness và key generation

Nếu thư viện có API sinh khóa hoặc secret:

- Dùng CSPRNG phù hợp của nền tảng.
- Không dùng PRNG thông thường hoặc seed cố định.
- Có thể tích hợp KMS/HSM khi private key không được export.
- Phân biệt key generation với key import.
- Ghi rõ format, encoding và cách bảo vệ key material.

Nếu thư viện chỉ tiêu thụ key do hệ thống khác tạo, vẫn cần đánh giá cách import và validate key.

## 5. Quản lý khóa và tích hợp JWKS

### 5.1. Key object có kiểu rõ ràng

Ưu tiên API nhận key object có kiểu cụ thể (RSA public/private, EC public/private, symmetric secret, certificate) thay vì chỉ nhận một chuỗi/byte tổng quát rồi suy đoán.

Thư viện cần:

- Kiểm tra key type tương thích với thuật toán.
- Phân biệt public/private/symmetric material.
- Tôn trọng **use** và **key_ops** khi được cung cấp.
- Không để private parameters xuất hiện khi serialize public JWKS.
- Có API import/export rõ format và lỗi.

### 5.2. JWKS resolver

Nếu có JWKS client/resolver, đánh giá:

- JWKS URI được cấu hình từ trust metadata đã xác minh, không lấy tùy ý từ token.
- Key được namespace theo issuer/trust domain; không tìm toàn cục chỉ theo kid.
- Hỗ trợ nhiều khóa trong giai đoạn rotation.
- Có cache TTL, refresh và xử lý key-not-found hợp lý.
- Có timeout, retry, backoff và giới hạn kích thước response.
- Chống SSRF qua URL/redirect và chặn scheme/host không được phép.
- Không dùng stale key đã bị emergency-block.
- Xử lý kid trùng, thiếu kid và JWKS chứa key không tương thích.

Nếu thư viện không có resolver, ứng dụng có thể tự quản lý JWKS. Điều quan trọng là ranh giới trust và cache behavior phải được thiết kế, không phải bắt buộc mọi JOSE library phải tải JWKS.

### 5.3. Rotation và thu hồi khóa

Thư viện hoặc integration layer cần hỗ trợ:

- Chọn key theo kid trong đúng issuer.
- Nạp public key mới trước khi issuer bắt đầu ký bằng private key mới.
- Giữ key cũ trong overlap chỉ khi rotation bình thường và policy cho phép.
- Gỡ key cũ sau giai đoạn chuyển tiếp.
- Chặn key bị compromise ngay cả khi còn trong cache.
- Purge cache và làm mới key set theo lệnh vận hành.

Không xem việc xóa public key khỏi JWKS là cơ chế thu hồi tức thời ở mọi verifier; cache và key object đang hoạt động có thể vẫn giữ khóa cũ.

### 5.4. Không tự động tải khóa theo header

Các trường **jku**, **x5u** hoặc thông tin URL trong token có thể bị attacker lợi dụng để khiến verifier truy cập host không tin cậy hoặc lấy khóa do attacker kiểm soát.

Thư viện cần cho phép tắt remote key fetching theo mặc định hoặc giới hạn bằng policy rõ ràng. Ứng dụng phải chọn issuer và nguồn JWKS từ cấu hình/metadata đã tin cậy; header chỉ có thể giúp chọn key trong nguồn đó.

## 6. Parser hardening và xử lý dữ liệu không tin cậy

### 6.1. Giới hạn tài nguyên parse

Token đến từ request là dữ liệu không tin cậy. Thư viện cần có cách giới hạn:

- Kích thước tổng token.
- Kích thước từng segment.
- Độ sâu JSON và số lượng member.
- Kích thước header/payload/JWK.
- Số lượng khóa trong JWKS.
- Kích thước ciphertext/plaintext và decompression.
- Thời gian parse/verify.

Không nên để một JWT quá lớn hoặc JSON lồng sâu làm tiêu thụ CPU/memory không giới hạn.

### 6.2. JSON ambiguity và duplicate member

Đánh giá cách parser xử lý JSON có member trùng tên, ví dụ hai trường **alg**, **iss** hoặc **aud**. Các parser khác nhau có thể chọn giá trị đầu, cuối hoặc báo lỗi; điều này tạo nguy cơ parser differential giữa issuer, gateway và resource server.

Ưu tiên từ chối JSON có member trùng ở vị trí nhạy cảm hoặc dùng parser có semantics rõ, nhất quán với profile và các bên liên quan. Không để một lớp parse nhìn thấy **alg** khác lớp thực hiện xác minh.

### 6.3. Encoding và cấu trúc

Kiểm tra:

- Base64url decode đúng chuẩn, không nhầm Base64 thường.
- Padding và ký tự không hợp lệ được xử lý theo chuẩn.
- UTF-8 và JSON syntax được xác minh nghiêm ngặt.
- Compact serialization có đúng số segment.
- JWS/JWE JSON serialization có cấu trúc và trường bắt buộc hợp lệ.
- NumericDate có kiểu dữ liệu hợp lệ.
- Không chấp nhận trailing data hoặc parser ambiguity ngoài profile.

### 6.4. Header parameters chưa biết

Thư viện cần:

- Từ chối critical header chưa được hỗ trợ.
- Không tự bỏ qua **crit**.
- Có API cho ứng dụng đăng ký handler nếu thực sự cần extension.
- Không xử lý extension trước khi policy trust được xác định.
- Không để header không quan trọng làm thay đổi trust source hoặc thuật toán.

## 7. Khả năng kiểm thử và bằng chứng bảo mật

### 7.1. Test vector từ chuẩn

Một thư viện tốt nên có test dựa trên:

- Ví dụ JWS trong RFC 7515.
- Ví dụ JWE trong RFC 7516.
- JWK/JWKS và thuật toán trong RFC 7517/7518.
- JOSE Cookbook (RFC 7520).
- Các profile liên quan như RFC 9068 hoặc RFC 9449 nếu thư viện tuyên bố hỗ trợ.

Test vector chứng minh một số hành vi chuẩn; nó không thay thế negative tests và kiểm thử tích hợp.

### 7.2. Positive tests

Kiểm tra token hợp lệ cho từng thuật toán/profile được bật:

- Chữ ký đúng và payload nguyên vẹn.
- JWK/JWKS đúng định dạng.
- Key rotation trong giai đoạn overlap.
- JWE giải mã và authentication tag hợp lệ.
- Claims đúng kiểu và nằm trong thời gian cho phép.
- Interoperability với implementation độc lập.

### 7.3. Negative tests bắt buộc

| Nhóm | Ca kiểm thử |
|---|---|
| Algorithm | none, thuật toán ngoài allowlist, RS256/HS256 confusion, downgrade/fallback |
| Key | Sai kty, key quá yếu, sai curve, private/public mismatch, key_ops/use không phù hợp |
| Signature/MAC | Chữ ký sai, MAC sai, signing input bị sửa, encoding sai |
| Claims | Sai issuer/audience/type, exp/nbf không hợp lệ, claim bắt buộc thiếu |
| Header | crit không hỗ trợ, kid lạ, jku/x5u tùy ý, duplicate member |
| Serialization | Sai số segment, Base64url lỗi, JSON hỏng, segment quá lớn |
| JWE | Sai tag, sai key management, ciphertext hỏng, zip/decompression abuse |
| JWKS | Key trùng kid, endpoint timeout, redirect, response quá lớn, cache stale |

Thư viện phải từ chối token lỗi một cách nhất quán và không để payload chưa xác minh được dùng như dữ liệu đã tin cậy.

### 7.4. Fuzzing và property-based testing

Fuzz parser/serializer với:

- Header và payload JSON bất thường.
- Segment rỗng, dài, sai encoding.
- JSON member trùng và Unicode edge cases.
- JWK tham số thiếu/thừa/sai kiểu.
- JWE ciphertext/tag ngẫu nhiên.
- Nested hoặc detached payload theo profile hỗ trợ.

Property-based tests có thể kiểm tra round-trip serialize/parse, tính nhất quán giữa các implementation và invariants như “verify thất bại thì không trả claims ở trạng thái trusted”.

### 7.5. Differential và interoperability testing

Đối chiếu với ít nhất một implementation độc lập và test vector chuẩn. Không chỉ kiểm tra hai phiên bản của cùng một codebase vì chúng có thể chia sẻ cùng lỗi.

Các khác biệt cần kiểm tra:

- ECDSA signature encoding.
- Base64url handling.
- JSON duplicate members.
- NumericDate và leeway.
- JWK thumbprint.
- Critical header.
- JWE key management/content encryption.

## 8. Mức độ bảo trì và phản ứng với lỗ hổng

### 8.1. Dấu hiệu dự án còn được duy trì

Đánh giá bằng chứng thực tế:

- Có release ổn định và changelog.
- Có hoạt động sửa lỗi, review và cập nhật dependency.
- Có maintainer hoặc tổ chức chịu trách nhiệm rõ.
- Có chính sách hỗ trợ phiên bản và thời gian end-of-life.
- Có quy trình nhận báo cáo bảo mật riêng.
- Có security advisory hoặc lịch sử phản ứng lỗ hổng có thể kiểm chứng.
- Có tài liệu migration khi API hoặc hành vi bảo mật thay đổi.

Số lượt tải, số star hoặc vị trí trong bảng xếp hạng không đủ chứng minh khả năng bảo trì.

### 8.2. Quy trình xử lý vulnerability

Thư viện nên công bố:

- Kênh báo cáo lỗ hổng bảo mật.
- Chính sách phối hợp công bố (coordinated disclosure).
- Security advisory với phạm vi ảnh hưởng và phiên bản bị ảnh hưởng.
- Bản vá và hướng nâng cấp rõ.
- Thông tin workaround nếu chưa có bản vá.
- Chính sách hỗ trợ phiên bản cũ.

Không yêu cầu dự án phải “không có CVE”. Một dự án có lịch sử lỗ hổng nhưng phát hiện, công bố và vá nhanh có thể đáng tin hơn dự án không có advisory vì không có quy trình tiếp nhận.

### 8.3. Bus factor và quyền sở hữu

Kiểm tra liệu dự án phụ thuộc hoàn toàn vào một maintainer không có người thay thế, có tổ chức bảo trợ hay có cộng đồng review độc lập. Bus factor thấp không tự động loại thư viện, nhưng cần có kế hoạch:

- Pin phiên bản và quản lý dependency.
- Theo dõi advisory.
- Có khả năng fork/patch nội bộ khi cần.
- Có lộ trình thay thế nếu dự án ngừng duy trì.

### 8.4. Phiên bản và compatibility

Không chọn thư viện chỉ vì phiên bản mới nhất. Xác minh:

- Phiên bản hỗ trợ runtime/nền tảng của hệ thống.
- Crypto backend và provider tương thích.
- Hỗ trợ các thuật toán còn được policy cho phép.
- Lịch vá lỗi và thời hạn hỗ trợ.
- Breaking changes trong API hoặc default behavior.
- Khả năng nâng cấp có kiểm soát và rollback.

Không giữ phiên bản cũ vô thời hạn chỉ để tránh migration; cần đánh giá rủi ro của cả nâng cấp và không nâng cấp.

## 9. Chuỗi cung ứng và độ tin cậy của gói

### 9.1. Nguồn phát hành

Kiểm tra:

- Gói được phát hành từ registry/repository chính thức.
- Namespace và tên package có bị nhầm với package tương tự/typosquatting không.
- Release artifact có chữ ký/provenance khi hệ sinh thái hỗ trợ.
- Checksum hoặc signature có thể xác minh độc lập.
- Quyền publish được bảo vệ và không phụ thuộc một tài khoản dễ bị chiếm.
- Repository, release tag và artifact có liên kết nguồn gốc rõ.

### 9.2. Dependency tree

Đánh giá cả dependency gián tiếp:

- Có dependency không cần thiết hoặc đã ngừng duy trì không?
- Có thư viện crypto backend cũ không?
- Có package có quyền chạy script/build-time không cần thiết không?
- Có vulnerability đã biết trong dependency không?
- Có thể tạo SBOM và theo dõi advisory không?
- Có thể cập nhật một dependency mà không thay đổi semantics JOSE không?

Một JOSE library tốt nhưng phụ thuộc vào crypto backend lỗi thời vẫn tạo rủi ro cho ứng dụng.

### 9.3. Quy trình tích hợp an toàn

- Pin version hoặc dùng cơ chế dependency lock phù hợp.
- Theo dõi security advisory của package và dependency.
- Quét dependency trong CI/CD.
- Xác minh checksum/signature/provenance khi có.
- Hạn chế quyền publish và quyền thay đổi dependency.
- Kiểm thử lại positive/negative vectors sau mỗi lần nâng cấp.
- Lưu lại phiên bản thư viện và crypto backend đang chạy để phục vụ điều tra.

## 10. Khả năng tích hợp và vận hành

### 10.1. Tích hợp key management

Nếu hệ thống cần HSM/KMS, thư viện phải có một trong các khả năng:

- Hỗ trợ provider/adapter chính thức.
- Nhận key handle hoặc interface ký/giải mã bên ngoài.
- Cho phép ứng dụng cung cấp signer/verifier abstraction.
- Không bắt buộc export private key ra file hoặc memory của ứng dụng.

Nếu thư viện không hỗ trợ trực tiếp KMS, cần đánh giá chi phí viết adapter và liệu API có cho phép ký/verify mà không lộ private key.

### 10.2. JWKS và cache

Đánh giá:

- Timeout, retry, backoff và circuit breaker ở resolver.
- Cache key theo issuer và JWKS URI đã tin cậy.
- Cache TTL có thể cấu hình.
- Refresh khi kid chưa biết nhưng có rate limit.
- Không refresh vô hạn theo mỗi token có kid ngẫu nhiên.
- Emergency key block có thể thắng cache.
- Có metrics về cache hit/miss, refresh error và key rotation.

### 10.3. Quan sát mà không lộ credential

Thư viện nên cung cấp lỗi và telemetry hữu ích:

- Mã lỗi phân biệt malformed token, invalid signature, unsupported algorithm, key not found và claim validation.
- Không ghi raw JWT, private key, HMAC secret hoặc plaintext nhạy cảm.
- Có thể gắn request ID/contract ID/key ID đã được chuẩn hóa.
- Không đưa token vào exception message hoặc debug dump mặc định.

### 10.4. Hiệu năng và khả năng mở rộng

Benchmark nên đo trên thuật toán, kích thước khóa, payload và tải thực tế:

- Verify/sign throughput và latency.
- Memory allocation theo request.
- Chi phí JWKS refresh/cache.
- JWE encryption/decryption.
- Hành vi khi concurrency cao.
- Độ trễ khi crypto backend dùng HSM/KMS từ xa.

Hiệu năng là tiêu chí sau khi các điều kiện bảo mật và tương thích đã đạt. Không chấp nhận cấu hình xác minh yếu chỉ để tăng throughput.

## 11. Những câu hỏi cần đặt khi đánh giá một thư viện

| Chủ đề | Câu hỏi cần có bằng chứng |
|---|---|
| Thuật toán | Có thể ghim allowlist và từ chối header alg ngoài policy không? |
| Key type | Có ngăn RSA public key bị dùng như HMAC secret không? |
| Claims | Verify có kiểm tra issuer/audience/exp/type hay chỉ chữ ký? |
| Parser | Có giới hạn kích thước, duplicate JSON và malformed encoding không? |
| Header | Unknown crit và URL key reference được xử lý thế nào? |
| JWK/JWKS | Có kiểm tra kty/use/key_ops và namespace issuer không? |
| JWE | Có xác minh authentication tag và giới hạn decompression không? |
| Crypto backend | Backend nào thực hiện primitive, phiên bản nào? |
| Testing | Có RFC test vectors, negative tests, fuzzing và interop tests không? |
| Maintenance | Release, advisory, support policy và maintainer ownership ra sao? |
| Supply chain | Artifact, dependency tree, provenance và SBOM có kiểm soát không? |
| Operations | Rotation, cache purge, error handling và key compromise được hỗ trợ thế nào? |

## 12. Scorecard lựa chọn thư viện

Có thể dùng bảng điểm dưới đây để so sánh các ứng viên. Điểm số chỉ hỗ trợ quyết định; các điều kiện bắt buộc không được bù bằng điểm cao ở mục khác.

| Tiêu chí | Trọng số gợi ý | Bằng chứng |
|---|---:|---|
| API an toàn theo mặc định | 20% | Algorithm pinning, key type enforcement, fail-closed |
| Tuân thủ chuẩn và tương thích | 15% | RFC vectors, profile support, interop |
| Key/JWKS management | 15% | Typed keys, issuer namespace, rotation/cache |
| Parser hardening | 10% | Size limits, duplicate member behavior, malformed input tests |
| Security testing | 15% | Negative tests, fuzzing, regression suite |
| Maintenance/vulnerability response | 10% | Release cadence, advisories, maintainers |
| Supply chain | 5% | Provenance, dependency health, SBOM |
| Operations/integration | 5% | KMS/HSM, telemetry, diagnostics |
| Performance | 5% | Benchmark trên workload thật |

### 12.1. Điều kiện loại trực tiếp

Không chọn thư viện nếu không thể khắc phục một trong các vấn đề:

- Không ghim được thuật toán theo contract.
- Có algorithm fallback không kiểm soát.
- Có thể nhầm key type giữa HMAC và chữ ký bất đối xứng.
- Bỏ qua unknown critical header.
- Không xác minh authentication tag khi dùng JWE.
- Không có cách xử lý lỗ hổng hoặc không xác định được nguồn phát hành.
- Có lỗi bảo mật nghiêm trọng chưa được vá mà không có biện pháp giảm thiểu khả thi.

### 12.2. Bằng chứng cần lưu trong quyết định lựa chọn

Ghi lại:

- Tên package, publisher, repository và phiên bản chính xác.
- Crypto backend và phiên bản.
- Các RFC/profile được sử dụng.
- Cấu hình thuật toán/key type đã kiểm thử.
- Test vector và negative test results.
- Advisory/CVE đã rà soát và trạng thái xử lý.
- Dependency/SBOM và provenance nếu có.
- Các giới hạn đã biết, workaround và kế hoạch nâng cấp.
- Người chịu trách nhiệm theo dõi thư viện sau khi tích hợp.

Không ghi secret, private key hoặc token thật vào hồ sơ đánh giá.

## 13. Quy trình Proof of Concept trước khi chọn

Một POC nhỏ nên kiểm tra hành vi thực tế, không chỉ chứng minh “ký được và verify được”.

1. Parse JWS/JWE hợp lệ từ test vector chuẩn.
2. Ký và xác minh bằng thuật toán/key type mà hệ thống dự định dùng.
3. Gửi token có alg ngoài allowlist và xác nhận bị từ chối.
4. Thử RS256/HS256 confusion bằng fixture test và xác nhận không có nhánh HMAC ngoài policy.
5. Kiểm tra issuer, audience, typ, exp, nbf và claims bắt buộc.
6. Kiểm tra kid lạ, trùng kid giữa issuer, JWKS timeout và rotation.
7. Kiểm tra crit không hỗ trợ, duplicate JSON member và token quá lớn.
8. Nếu dùng JWE, kiểm tra sai tag, sai key và giới hạn giải nén.
9. Chạy interoperability test với implementation độc lập.
10. Kiểm tra logging, exception và telemetry không làm lộ token/key.
11. Đánh giá dependency tree, release provenance và quy trình advisory.
12. Chạy benchmark trên workload thật sau khi các kiểm tra bảo mật đạt.

### 13.1. Pseudocode tích hợp có ranh giới tin cậy

~~~text
validateIncomingToken(endpoint, compactToken):
    contract = trustedContracts.forEndpoint(endpoint)
    reject nếu contract không tồn tại

    parsedHeader = joseLibrary.parseHeader(compactToken)
    treat parsedHeader as untrusted

    reject nếu parsedHeader.alg không thuộc contract.allowedAlgorithms
    reject nếu header có critical parameter không được hỗ trợ

    key = trustedKeyResolver.forIssuer(contract.issuer)
                         .find(parsedHeader.kid)
    reject nếu key không tồn tại hoặc key type/purpose không khớp

    verified = joseLibrary.verifyUsingExactly(
        compactToken,
        contract.algorithm,
        key
    )
    reject nếu chữ ký/MAC không hợp lệ

    validate issuer, audience, token type, time và required claims
    validate central status nếu contract yêu cầu
    authorize principal against requested resource/action
    ACCEPT
~~~

Đây là pseudocode khái niệm. Hàm parse header chỉ cung cấp dữ liệu chưa tin cậy; không được dùng kết quả parse đó để cấp quyền hoặc chọn trust source tùy ý.

## 14. Ma trận kiểm thử chấp nhận thư viện

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| LIB01 | JWS hợp lệ theo RFC vector | Parse và verify đúng |
| LIB02 | JWE hợp lệ theo RFC vector | Decrypt và xác minh tag đúng |
| LIB03 | Thuật toán ngoài allowlist | Từ chối trước khi xác minh |
| LIB04 | RS256 token đổi sang HS256 với public-key bytes làm secret | Từ chối; không có key-type confusion |
| LIB05 | alg none | Từ chối theo profile |
| LIB06 | RSA key được dùng cho HMAC hoặc ngược lại | Từ chối |
| LIB07 | JWK sai kty/use/key_ops/curve | Từ chối |
| LIB08 | Unknown critical header | Từ chối |
| LIB09 | jku/x5u trỏ tới URL ngoài trust configuration | Không tải khóa tùy ý |
| LIB10 | Duplicate alg/iss/aud trong JSON | Hành vi rõ ràng, ưu tiên từ chối ambiguity |
| LIB11 | Token vượt giới hạn kích thước | Từ chối có kiểm soát |
| LIB12 | Base64url/UTF-8/JSON malformed | Từ chối |
| LIB13 | Issuer hoặc audience sai | Từ chối |
| LIB14 | exp/nbf sai hoặc claim bắt buộc thiếu | Từ chối theo policy |
| LIB15 | kid trùng giữa hai issuer | Resolver không chọn nhầm issuer/key |
| LIB16 | JWKS timeout hoặc redirect bất thường | Không fallback sang nguồn không tin cậy |
| LIB17 | Key rotation bình thường | Token mới và cũ được xử lý theo overlap policy |
| LIB18 | Emergency key block | Cache không làm sống lại key bị chặn |
| LIB19 | JWE authentication tag sai | Không trả plaintext |
| LIB20 | JWE compression payload quá lớn | Bị giới hạn tài nguyên |
| LIB21 | ECDSA signature DER thay cho JOSE R||S | Xử lý đúng định dạng profile; không chấp nhận encoding sai |
| LIB22 | Verify thất bại | Không trả claims ở trạng thái trusted |
| LIB23 | Log/exception khi token sai | Không lộ raw token hoặc key material |
| LIB24 | Interop với implementation độc lập | Kết quả phù hợp chuẩn/test vector |
| LIB25 | Dependency có advisory nghiêm trọng | Có quy trình đánh giá và bản vá/mitigation |

## 15. Checklist quyết định cuối cùng

**Phù hợp use case**

- [ ] Đã liệt kê đúng JWS/JWE/JWK/JWT và profile cần hỗ trợ.
- [ ] Không bật thuật toán hoặc serialization không cần thiết.
- [ ] Xác định rõ phần nào do thư viện làm và phần nào do ứng dụng kiểm tra.

**An toàn mật mã và API**

- [ ] Thuật toán được ghim theo contract; không tin alg chưa xác minh.
- [ ] Key type, key purpose và thuật toán được ràng buộc.
- [ ] Không có fallback hoặc algorithm confusion.
- [ ] Critical header, key URL và token parsing được xử lý an toàn.
- [ ] JWE kiểm tra authentication tag và giới hạn tài nguyên.
- [ ] API phân biệt parse, verify, validate và authorize.

**Kiểm thử**

- [ ] Có RFC test vectors và negative tests.
- [ ] Có fuzzing/property tests hoặc bằng chứng kiểm thử parser tương đương.
- [ ] Có interoperability test độc lập.
- [ ] Có regression tests cho các lỗi bảo mật đã biết.
- [ ] POC kiểm tra cả JWKS rotation, cache và failure behavior.

**Bảo trì và chuỗi cung ứng**

- [ ] Có maintainer/tổ chức chịu trách nhiệm.
- [ ] Có release, changelog và support policy.
- [ ] Có security contact và quy trình advisory.
- [ ] Crypto backend/dependencies được duy trì.
- [ ] Nguồn package và artifact được xác minh.
- [ ] Có kế hoạch theo dõi, nâng cấp và thay thế thư viện.

**Vận hành**

- [ ] Tích hợp key store/KMS/HSM theo nhu cầu.
- [ ] Có cache/refresh/emergency key block phù hợp.
- [ ] Log và telemetry không lộ token hoặc key.
- [ ] Có người chịu trách nhiệm theo dõi advisory và nâng cấp.

**Điều cần nhớ:** Chọn JOSE library là quyết định về ranh giới tin cậy và khả năng bảo trì lâu dài. Hãy yêu cầu bằng chứng về API an toàn theo mặc định, algorithm/key binding, parser hardening, test âm tính, interoperability, xử lý lỗ hổng và nguồn gốc package. Sau khi chọn, ứng dụng vẫn phải ghim policy theo issuer/profile, kiểm tra claims và quyền tài nguyên; không giao toàn bộ quyết định bảo mật cho một hàm “verify JWT”.

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): Cấu trúc JWS và xử lý chữ ký/MAC.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): Cấu trúc JWE và mã hóa.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và key metadata.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): Thuật toán JOSE và yêu cầu khóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT và registered claims.
- [RFC 7520 — Examples of Protecting Content Using JSON Object Signing and Encryption (JOSE)](https://www.rfc-editor.org/rfc/rfc7520): Bộ ví dụ JOSE hữu ích cho interoperability testing.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): JWK thumbprint.
- [RFC 7797 — JSON Web Signature (JWS) Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797): Header b64 và unencoded payload.
- [RFC 8037 — CFRG Elliptic Curve Algorithms for JOSE](https://www.rfc-editor.org/rfc/rfc8037): EdDSA trong JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Các yêu cầu thực hành an toàn khi xử lý JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Profile JWT access token.
- [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/): Yêu cầu xác minh bảo mật ứng dụng.
- [OpenSSF Scorecard](https://scorecard.dev/): Tín hiệu đánh giá một số thực hành bảo mật chuỗi cung ứng phần mềm.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): Quản lý vòng đời khóa mật mã.
