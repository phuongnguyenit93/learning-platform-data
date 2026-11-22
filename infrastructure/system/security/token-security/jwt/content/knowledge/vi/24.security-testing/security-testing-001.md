# Vector chuẩn và kiểm tra liên thông với bộ triển khai độc lập

Một thư viện JWT có thể tạo và xác minh token thành công trong chính môi trường của nó nhưng vẫn không tương thích với thư viện khác. Khác biệt có thể nằm ở cách mã hóa Base64url, tạo signing input, biểu diễn chữ ký ECDSA, xử lý JWK, diễn giải header, kiểm tra claims hoặc áp dụng policy cho thuật toán. **Standard test vector** cung cấp đầu vào và kết quả tham chiếu có thể tái lập; **interoperability testing** xác nhận các bộ triển khai độc lập hiểu và xử lý cùng một token theo cách nhất quán.

Bài này thuộc chương **Kiểm thử bảo mật** của module **Security - JSON Web Token (JWT)**. Nội dung tập trung vào kiểm thử chuẩn JOSE/JWT và khả năng liên thông giữa các triển khai độc lập, áp dụng cho hệ thống bảo mật nói chung, không phụ thuộc ngôn ngữ lập trình hay framework.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc có thể:

1. Phân biệt test vector của thuật toán mật mã, JOSE và token profile.
2. Tổ chức bộ known-answer, positive, negative và interoperability vectors.
3. Kiểm tra JWS, JWE, JWK/JWKS, JWT claims và các profile liên quan.
4. Xây dựng test harness dùng các implementation độc lập làm producer và consumer.
5. Phát hiện khác biệt trong serialization, encoding, parser, algorithm policy và key selection.
6. Thiết kế mutation test, differential test và regression suite.
7. Báo cáo rõ một lỗi thuộc primitive, JOSE, profile, policy hay cấu hình môi trường.

Phạm vi bao gồm JWS/JWE compact serialization, JWK/JWKS, registered claims và một số profile phổ biến như OAuth JWT Access Token và DPoP. Mỗi hệ thống chỉ cần kiểm thử các thuật toán và profile mà nó tuyên bố hỗ trợ; không phải mọi implementation đều phải hỗ trợ mọi JOSE algorithm.

## 2. Các loại test vector

Một bộ kiểm thử tốt cần nhiều loại vector vì mỗi loại trả lời một câu hỏi khác nhau.

| Loại | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Known-answer test (KAT) | Key, message, parameters và vector chuẩn cố định | Output phải khớp chính xác giá trị tham chiếu |
| Positive vector | Token hợp lệ theo một profile | Được chấp nhận và trả về claims/kết quả đúng |
| Negative vector | Token sai chữ ký, claim, header hoặc key | Bị từ chối theo đúng reason/policy |
| Interoperability vector | Token do implementation A tạo, implementation B xử lý | B xác minh/giải mã đúng nếu cả hai hỗ trợ cùng profile |
| Mutation vector | Một trường của vector hợp lệ bị thay đổi | Chỉ biến thể bị ảnh hưởng phải thất bại |
| Regression vector | Input từng gây lỗi | Lỗi cũ không xuất hiện lại |
| Fuzz/property vector | Input được sinh hoặc biến đổi có kiểm soát | Không crash, treo, vượt giới hạn hoặc chấp nhận sai |

KAT xác minh thuật toán hoặc thao tác chuẩn có đúng với ví dụ tham chiếu hay không. Interoperability test xác minh hai bộ triển khai thực sự giao tiếp được. Một implementation có thể pass KAT nhưng vẫn fail interop vì profile, parser hoặc cấu hình khác nhau.

## 3. Phân tầng kiểm thử

Không nên gom mọi thất bại thành “JWT invalid”. Tách test theo lớp giúp tìm đúng nguyên nhân:

1. **Cryptographic primitive:** HMAC, RSA, ECDSA, EdDSA, AES-GCM, AES-CBC-HMAC và phép hash.
2. **JOSE serialization:** protected header, Base64url, signing input, compact/general serialization và AAD.
3. **Key representation:** JWK, key type, curve, key operations, thumbprint và JWKS selection.
4. **JWT semantics:** `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti` và token type.
5. **Token profile:** OAuth access token, OIDC ID Token, DPoP hoặc profile riêng.
6. **Application policy:** authorization, tenant boundary, revocation, clock skew và error handling.
7. **Deployment path:** reverse proxy, TLS termination, cache, key rotation và nhiều instance.

Một test crypto thành công không chứng minh issuer/audience validation đúng. Một token có chữ ký hợp lệ cũng không chứng minh token phù hợp với API hoặc profile đang xử lý.

## 4. Nguồn test vector chuẩn

Ưu tiên lấy vector trực tiếp từ tài liệu chuẩn hoặc bộ conformance test được duy trì chính thức. Các nguồn quan trọng:

| Tài liệu | Nội dung vector hoặc quy tắc cần kiểm thử |
| --- | --- |
| RFC 7515 — JWS | Ví dụ chữ ký, signing input và JWS serialization trong Appendix A |
| RFC 7516 — JWE | Ví dụ mã hóa, protected header, encrypted key, IV, ciphertext và authentication tag trong Appendix A |
| RFC 7517 — JWK | Cấu trúc JWK/JWKS và key metadata |
| RFC 7518 — JWA | Thuật toán HMAC, RSA, ECDSA, AES Key Wrap, AES-GCM và AES-CBC-HMAC |
| RFC 7519 — JWT | Compact token, registered claims và cách diễn giải claims |
| RFC 7638 — JWK Thumbprint | Vector tính thumbprint JWK |
| RFC 7797 — JWS Unencoded Payload | `b64`, `crit` và detached/unencoded payload khi được hỗ trợ |
| RFC 8037 — CFRG Elliptic Curve Signatures | EdDSA trong JOSE |
| RFC 8725 — JWT Best Current Practices | Negative cases, algorithm policy và token confusion |
| RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens | Access-token profile và type validation |
| RFC 9449 — DPoP | Proof JWT, request binding, nonce và access-token hash |

Vector trong RFC có thể là ví dụ minh họa chuẩn chứ không phải toàn bộ compliance suite. Cần đọc đúng algorithm/profile section, giữ nguyên key và byte sequence, đồng thời ghi rõ phiên bản tài liệu hoặc test corpus đã dùng.

Không tự chép lại vector bằng tay nếu có thể lấy bản gốc. Một ký tự bị đổi trong key, Base64url hoặc payload sẽ làm kết quả không còn là vector chuẩn.

## 5. Thiết kế test fixture có thể tái lập

Mỗi vector nên có metadata đủ để một implementation độc lập tái chạy:

~~~yaml
id: jws-rs256-valid-001
category: jws
source:
  standard: RFC 7515
  section: Appendix A
profile: internal-access-token-v1
algorithm: RS256
input:
  compact_token: "..."
  public_jwk: {}
expected:
  signature_valid: true
  claims_valid: true
  outcome: accept
notes:
  - "Fixed public test key; never use production credentials."
~~~

Đây là schema minh họa, không phải định dạng bắt buộc. Một fixture thực tế nên ghi:

- ID duy nhất và mô tả mục tiêu.
- Nguồn chuẩn, phiên bản, section hoặc hash của corpus.
- Token profile và algorithm policy.
- Key material test, key type, curve hoặc certificate.
- Input byte chính xác; không chỉ lưu JSON đã parse.
- Thời gian tham chiếu cố định cho `exp`, `nbf` và `iat`.
- Kết quả mong đợi: accept, reject hoặc expected output cụ thể.
- Lý do test và lớp đang được kiểm tra.
- Implementation/version đã chạy và kết quả.

Không dùng production private key, refresh token, access token hoặc dữ liệu cá nhân thật trong fixture. Test key phải tách biệt và có thể công khai.

## 6. Kiểm thử primitive mật mã

Trước khi kiểm thử JWT end-to-end, xác minh primitive và provider crypto bằng vector phù hợp. Nếu primitive sai, lỗi có thể lan sang mọi token.

### 6.1. HMAC

Với HS256, HS384 và HS512:

- Kiểm tra key bytes, message bytes, hash function và output đúng độ dài.
- Xác nhận signer và verifier dùng cùng secret theo profile.
- Thay đổi một bit của message hoặc signature phải làm verification thất bại.
- Key quá yếu hoặc không đáp ứng policy phải bị từ chối khi cấp/cấu hình.
- So sánh MAC theo constant-time primitive phù hợp; không tự viết phép so sánh dễ lộ timing.

Không nhầm chuỗi secret được encode Base64 với chính byte của secret. Fixture phải nói rõ key là raw bytes, Base64url text hay một dạng import khác.

### 6.2. RSA và RSA-PSS

Kiểm tra:

- RS256/RS384/RS512 dùng đúng hash và RSA signature scheme.
- PS256/PS384/PS512 dùng RSA-PSS với salt length bằng độ dài output của hash tương ứng và parameters theo JWA.
- Public/private key import/export nhất quán.
- Key size đáp ứng policy và key type đúng với `alg`.
- Signature bị sửa, cắt ngắn hoặc dùng key khác phải thất bại.

RSA-PSS có randomness nên hai lần ký cùng message có thể tạo signature khác nhau. Interop test nên xác minh chữ ký, không mặc định so sánh chuỗi signature byte-for-byte với một signer khác, trừ khi vector cố định parameters và output tham chiếu cụ thể.

### 6.3. ECDSA

JWS biểu diễn chữ ký ECDSA bằng phép nối hai số nguyên cố định độ dài `R || S`, không phải ASN.1 DER sequence thường thấy trong một số API crypto.

Kiểm tra:

- Curve tương ứng với thuật toán JOSE, ví dụ P-256 cho ES256.
- Độ dài chữ ký đúng hai phần R và S.
- Chuyển đổi DER ↔ JOSE raw signature nếu crypto provider yêu cầu.
- Reject signature sai độ dài, giá trị R/S ngoài miền hoặc signature bị sửa.
- Không nhầm ES256 với thuật toán ECDSA dùng curve/hash khác.

ECDSA signer có thể tạo signature khác nhau cho cùng message do nonce ký. Test liên thông nên kiểm tra xác minh hai chiều thay vì yêu cầu hai implementation sinh ra cùng chuỗi signature.

### 6.4. EdDSA

Nếu hỗ trợ EdDSA, kiểm tra đúng curve/key type và thuật toán theo RFC 8037, định dạng public/private JWK, signature length và negative vectors. Không suy luận rằng một implementation hỗ trợ Ed25519 chỉ vì nó hỗ trợ một thuật toán có tên chung là EdDSA.

## 7. JWS known-answer và interoperability

JWS compact serialization gồm ba phần:

~~~text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Signing input được xác định từ ASCII bytes của:

~~~text
BASE64URL(protected-header) + "." + BASE64URL(payload)
~~~

Verifier phải xác minh đúng byte sequence đã được ký. Không parse JSON rồi serialize lại header/payload trước khi xác minh, vì thứ tự member, whitespace, escape hoặc encoding có thể làm byte sequence thay đổi.

### 7.1. Positive vectors

- Vector JWS chuẩn từ RFC 7515 với key và payload cố định.
- Token do signer A tạo được verifier B chấp nhận.
- Token do signer B tạo được verifier A chấp nhận.
- Token có protected header và claims đúng profile.
- JWS có payload rỗng hoặc payload chứa Unicode nếu profile cho phép.
- General/flattened serialization nếu hệ thống tuyên bố hỗ trợ.

### 7.2. Negative vectors

- Thay một byte của protected header, payload hoặc signature.
- Dùng public key khác hoặc secret khác.
- Signature sai encoding hoặc sai độ dài.
- `alg` không nằm trong allowlist.
- Header có `crit` không được hỗ trợ.
- `kid` không tồn tại hoặc mơ hồ trong JWKS.
- Duplicate JOSE header parameter hoặc claim name theo policy parser.
- Token sai số segment hoặc có Base64url malformed.

### 7.3. Base64url

Compact JOSE dùng Base64url encoding theo quy tắc chuẩn, không dùng alphabet Base64 thông thường và không thêm padding `=` trong serialized segments. Test parser với:

- Ký tự `+` và `/` thay cho `-` và `_`.
- Padding thừa hoặc thiếu theo strictness policy.
- Ký tự ngoài alphabet.
- Segment rỗng ở vị trí không hợp lệ.
- Encoding không canonical hoặc dữ liệu decode bị cắt.

Định nghĩa rõ parser có chấp nhận biến thể tương thích nào. Không để các implementation trong cùng hệ thống diễn giải một chuỗi theo các byte khác nhau.

## 8. JWS header và JSON parser edge cases

Protected header là JSON, nhưng parser có thể khác nhau ở các trường hợp bất thường.

Kiểm thử:

- Header thiếu `alg`.
- `alg` là null, number, array hoặc object thay vì string.
- `kid` sai kiểu hoặc quá dài.
- Duplicate `alg`, `kid`, `crit` hoặc member khác.
- JSON malformed, trailing data hoặc nesting quá sâu.
- Unicode escape và tên member có cách biểu diễn khác nhau.
- Header chứa `jku`, `x5u`, `b64` hoặc `crit` không được profile hỗ trợ.

RFC JWT cho phép parser xử lý duplicate claim name theo một trong các cách: từ chối token hoặc dùng member xuất hiện cuối cùng theo thứ tự từ vựng. Để tránh parser differential giữa các implementation, profile bảo mật nên chọn chính sách rõ ràng; từ chối duplicate member là lựa chọn nghiêm ngặt, dễ kiểm thử.

Không chấp nhận duplicate header/claim theo cách implementation A dùng giá trị đầu còn implementation B dùng giá trị cuối. Đây là nguồn tạo ra xác minh khác nhau giữa gateway và backend.

## 9. JWE known-answer và interoperability

JWE compact serialization có năm phần:

~~~text
protected-header
.
encrypted-key
.
initialization-vector
.
ciphertext
.
authentication-tag
~~~

Protected header được Base64url encode. Với compact JWE, Additional Authenticated Data (AAD) là ASCII bytes của encoded protected header. Thay đổi header có thể làm authentication tag không còn hợp lệ.

### 9.1. Positive vectors

- Vector JWE chuẩn từ RFC 7516 Appendix A.
- Key management algorithm và content encryption algorithm đúng cặp.
- Giải mã bằng implementation khác với cùng recipient key.
- Direct encryption, key wrapping hoặc key agreement nếu profile hỗ trợ.
- JWE lồng trong JWT/JWE nested structure nếu hệ thống tuyên bố hỗ trợ.

### 9.2. Negative vectors

- Sai recipient key hoặc encrypted key.
- Thay protected header hoặc AAD.
- Thay IV, ciphertext hoặc authentication tag.
- Authentication tag bị cắt hoặc sai độ dài.
- Content encryption algorithm không được phép.
- Key management algorithm không tương thích với key type.
- JWE sai số segment hoặc có encoding malformed.

JWE có authenticated encryption phải xác minh authentication tag trước khi trả plaintext cho caller. Không để plaintext chưa xác thực đi vào parser hoặc business logic.

### 9.3. CBC-HMAC và GCM

Với AES-CBC-HMAC, kiểm thử đúng thứ tự encrypt-then-MAC, cách chia key material, MAC input và tag truncation theo JWA. Với AES-GCM, kiểm tra nonce/IV, AAD, ciphertext và tag.

Không tái sử dụng IV/nonce trong production theo cách vi phạm yêu cầu của thuật toán. Vector cố định có thể dùng IV cố định để tái lập kết quả trong môi trường test, nhưng không được sao chép cấu hình đó thành production key/nonce policy.

## 10. JWK và JWKS interoperability

JWK mô tả key material và metadata; JWKS là tập hợp JWK. Cùng một key có thể được biểu diễn hoặc import theo nhiều định dạng ở các crypto provider khác nhau.

Kiểm thử:

- JWK RSA public parameters và EC/OKP public parameters.
- `kty`, `crv`, `alg`, `use`, `key_ops`, `kid`.
- Private member không được xuất hiện trong public JWKS.
- JWK thumbprint theo RFC 7638.
- JWK import/export giữa hai implementation.
- JWKS có nhiều key trong thời gian rotation.
- Unknown hoặc duplicate `kid`.
- Key type, curve, use và key_ops không phù hợp với thuật toán.

Verifier không được chọn key chỉ vì `kid` khớp. Phải kiểm tra issuer trust context, thuật toán allowlist, key type và metadata phù hợp. Nếu có nhiều candidate tương thích hoặc không có candidate, từ chối theo policy thay vì chọn phần tử đầu tiên.

### 10.1. JWK thumbprint

RFC 7638 định nghĩa cách tạo thumbprint từ tập member JWK được chọn theo `kty`. Test vector cần giữ nguyên:

- JWK public parameters.
- Canonical member set và thứ tự serialization được quy định.
- Hash function.
- Base64url encoding.

Không hash JSON JWK tùy ý theo thứ tự property mà runtime trả về. Cách serialize thông thường có thể khác giữa implementation và tạo thumbprint không tương thích.

## 11. JWT claims và token profile

Chữ ký hợp lệ chỉ chứng minh token không bị sửa bởi bên không có signing key. Resource server vẫn phải kiểm tra claims và profile.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| `iss` khớp chính xác issuer được cấu hình | Tiếp tục |
| `iss` sai hoặc không được tin cậy | Reject |
| `aud` là string hoặc array có chứa đúng audience của resource server | Tiếp tục |
| `aud` không chứa resource server hiện tại | Reject |
| `exp` đã đến hoặc vượt thời điểm hết hạn theo policy | Reject |
| `nbf` nằm trong tương lai ngoài leeway | Reject |
| `iat` vượt maximum token age hoặc nằm tương lai bất hợp lý | Reject theo profile |
| Thiếu claim bắt buộc của token profile | Reject |
| `typ` sai hoặc token thuộc profile khác | Reject |
| Token có scope hợp lệ nhưng thiếu quyền nghiệp vụ | Authentication có thể hợp lệ; authorization phải từ chối |

Test thời gian phải dùng clock cố định hoặc injectable clock. Không dựa vào giờ máy thật để tạo vector ổn định.

### 11.1. Token substitution và cross-JWT confusion

Tạo vector trong đó một token có chữ ký hợp lệ nhưng thuộc mục đích khác:

- ID Token được gửi đến API thay access token.
- Access token được dùng ở endpoint yêu cầu token profile khác.
- Token từ issuer A được gửi đến verifier của issuer B.
- Token có audience cho service A được gửi đến service B.
- Token có `typ` hoặc claim profile không đúng.

Verifier phải phân biệt token theo issuer, audience, type và profile; không chỉ kiểm tra “signature valid”.

### 11.2. OAuth JWT Access Token

Nếu hệ thống hỗ trợ RFC 9068, kiểm thử access-token profile theo các claim và header yêu cầu của profile, bao gồm `typ` là `at+jwt` theo cách đặc tả quy định, issuer/audience, client/subject context và các claim bắt buộc tương ứng. Không áp dụng profile này cho mọi JWT chung nếu hệ thống không tuyên bố dùng nó.

## 12. Kiểm thử thời gian và clock skew

Tạo vector tại các mốc biên:

- Thời điểm ngay trước `exp`.
- Chính xác tại `exp`.
- Ngay sau `exp`.
- Ngay trước `nbf` phải bị từ chối; tại hoặc sau `nbf` có thể được chấp nhận nếu các kiểm tra khác đạt.
- `iat` trong tương lai.
- Token age đúng ngưỡng maximum age và vượt ngưỡng một đơn vị thời gian.
- Clock skew âm/dương ở các verifier khác nhau.

Ghi rõ leeway trong test metadata. Hai implementation có thể mặc định leeway khác nhau; interoperability yêu cầu cấu hình cùng policy, không chỉ cùng token.

Không để leeway lớn che lỗi đồng bộ thời gian. Nếu một verifier chấp nhận token lâu hơn verifier khác, đo đúng khoảng chênh lệch và đánh giá tác động bảo mật.

## 13. Negative test cho thuật toán và key confusion

Các vector cần có:

- `alg: none` khi profile yêu cầu chữ ký.
- Thuật toán không nằm trong allowlist.
- HMAC token được gửi đến endpoint chỉ cho phép RSA/ECDSA hoặc ngược lại.
- Dùng RSA public key bytes làm HMAC secret.
- RSA-PSS token với parameters không đúng JWA.
- Key type/curve không khớp `alg`.
- Key có `use=enc` được dùng để xác minh chữ ký.
- `key_ops` không cho phép verify.
- `kid` trỏ đến key của issuer/tenant khác.
- JWKS thay đổi giữa các lần fetch hoặc cache chứa key cũ.

Kết quả mong đợi là từ chối rõ ràng, không thử thuật toán khác, không dùng default key và không fallback sang bearer token.

## 14. `crit`, `b64` và extension handling

JOSE cho phép extension qua protected header parameters. Parameter trong `crit` đánh dấu các extension mà recipient phải hiểu và xử lý.

Kiểm thử:

- `crit` thiếu parameter được liệt kê.
- `crit` chứa extension không được hỗ trợ.
- Extension được khai báo nhưng không nằm trong protected header theo yêu cầu.
- `b64=false` theo RFC 7797 khi implementation hỗ trợ unencoded payload.
- `b64=false` nhưng thiếu `b64` trong `crit`.
- Producer và consumer hiểu khác nhau về detached payload.

Nếu profile không hỗ trợ extension, verifier phải từ chối token có critical extension không hiểu. Không bỏ qua `crit` rồi tiếp tục xác minh như thể extension không tồn tại.

Không bật unencoded payload chỉ để tăng tương thích nếu hệ thống không cần. Khi hỗ trợ, test signing input chính xác và detached payload handling theo RFC 7797.

## 15. Nested JWT và phân biệt JWS/JWE

Nested JWT có thể được ký rồi mã hóa hoặc mã hóa rồi ký theo cấu trúc được profile cho phép. Header `cty` và `typ` giúp mô tả nội dung, nhưng verifier vẫn phải áp dụng đúng quy tắc nesting.

Test:

- JWS bên trong JWE theo đúng thứ tự được profile hỗ trợ.
- JWE chứa plaintext không phải JWT.
- JWS hợp lệ nhưng không được phép ở vị trí nested.
- Sai `cty`, `typ` hoặc token profile.
- Token chỉ được ký khi endpoint yêu cầu mã hóa, hoặc ngược lại.
- Thay đổi một lớp phải làm xác minh lớp đó thất bại.

Không tự động parse bất kỳ plaintext giải mã nào thành JWT. Xác minh outer layer, kiểm tra content type, rồi mới xử lý inner token theo profile đã định.

## 16. Interoperability matrix giữa các implementation

Tạo ma trận producer/consumer để không chỉ kiểm thử từng thư viện riêng:

| Producer | Consumer | JWS | JWE | JWK/JWKS | Claims/profile |
| --- | --- | --- | --- | --- | --- |
| Implementation A | Implementation B | Pass/Fail | Pass/Fail | Pass/Fail | Pass/Fail |
| Implementation B | Implementation A | Pass/Fail | Pass/Fail | Pass/Fail | Pass/Fail |
| Implementation A | Implementation C | Pass/Fail | Pass/Fail | Pass/Fail | Pass/Fail |
| Implementation C | Implementation A | Pass/Fail | Pass/Fail | Pass/Fail | Pass/Fail |

Ít nhất hai implementation phải độc lập ở mức thư viện hoặc crypto backend. Nếu signer và verifier cùng gọi một thư viện lõi hoặc cùng một adapter có bug, kết quả pass không đủ chứng minh interoperability.

### 16.1. Kiểm thử hai chiều

Với mỗi profile/algorithm:

1. A ký, B xác minh.
2. B ký, A xác minh.
3. A mã hóa, B giải mã.
4. B mã hóa, A giải mã.
5. A xuất JWK/JWKS, B import và dùng.
6. B xuất JWK/JWKS, A import và dùng.

Không phải mọi profile đều hỗ trợ mọi hướng hoặc thuật toán. Đánh dấu rõ unsupported theo capability matrix thay vì ghi nhầm thành pass.

### 16.2. Không so sánh token string một cách máy móc

Một số thuật toán ký có randomness, chẳng hạn ECDSA hoặc RSA-PSS. Hai signer có thể tạo token string khác nhau nhưng cả hai đều hợp lệ. Với các trường hợp đó:

- So sánh header/payload theo byte sequence hoặc semantics được profile quy định.
- Xác minh chữ ký của từng token ở consumer độc lập.
- Không yêu cầu signature bytes bằng nhau nếu thuật toán không deterministic.
- Với vector KAT cố định, so sánh output đúng theo vector tham chiếu.

## 17. Differential testing

Differential testing đưa cùng một input vào nhiều implementation và so sánh kết quả. Mục tiêu là tìm ra parser hoặc verifier diễn giải khác nhau.

Input nên bao gồm:

- Token hợp lệ và token chỉ sai một chi tiết.
- Header/claims có member trùng.
- JSON whitespace, thứ tự member và escape khác nhau.
- Base64url padding/character edge cases.
- NumericDate ở ranh giới.
- JWK có metadata thiếu, thừa hoặc xung đột.
- JWKS có duplicate/ambiguous `kid`.
- Header extension và critical parameters.

Khi kết quả khác nhau:

1. Xác định hành vi nào được RFC/profile yêu cầu.
2. Xác định khác biệt do parser, crypto backend, configuration hay policy.
3. Không mặc định đa số implementation là đúng.
4. Lưu input tối giản tái lập được.
5. Tạo regression vector sau khi xác định cách xử lý chuẩn.

## 18. Mutation và property-based testing

Từ một vector hợp lệ, tạo các biến thể có kiểm soát bằng cách thay đổi từng phần:

- Một byte của signature.
- Một ký tự Base64url.
- Một claim hoặc JOSE header parameter.
- Một byte của key, IV, ciphertext hoặc tag.
- Một giá trị `iss`, `aud`, `exp`, `nbf` hoặc `typ`.
- Một JWK member như `kty`, `crv`, `use`, `key_ops` hoặc `kid`.

Property mong đợi:

- Thay payload sau khi ký phải làm JWS verification thất bại.
- Thay protected header làm signing input thay đổi và chữ ký cũ không còn hợp lệ.
- Thay JWE AAD, IV, ciphertext hoặc tag phải làm authenticated decryption thất bại.
- Key không tương thích không được chọn chỉ vì `kid` khớp.
- Parser không được crash, treo hoặc cấp phát bộ nhớ không giới hạn với input malformed.
- Một token bị từ chối không được gây side effect nghiệp vụ.

Fuzzing cần giới hạn kích thước, thời gian và tài nguyên. Khi phát hiện crash, lưu seed/input tối giản và phiên bản implementation để tái lập.

## 19. Kiểm thử key rotation, JWKS cache và nhiều instance

Một bộ test chỉ dùng một key cố định chưa đủ cho production.

Mô phỏng:

1. JWKS ban đầu có key K1; token T1 được ký bằng K1.
2. Issuer công bố K2 với `kid` mới trong thời gian overlap.
3. Token T2 được ký bằng K2.
4. Consumer nhận T2 khi cache vẫn chỉ có K1.
5. Consumer refresh JWKS đúng issuer và xác minh T2.
6. Sau thời gian overlap, issuer bỏ K1.
7. Consumer cập nhật cache và từ chối token K1 theo policy hết hạn/retirement.

Kiểm tra thêm:

- Nhiều instance refresh cùng lúc có single-flight hoặc cooldown phù hợp.
- Unknown `kid` không gây fetch storm.
- Cache key có issuer/profile scope.
- JWKS endpoint timeout, lỗi TLS, redirect hoặc trả JSON sai được xử lý fail closed.
- Một instance có cache mới và instance khác có cache cũ không tạo ra hành vi nguy hiểm.
- Không dùng key cũ vô thời hạn khi JWKS không thể refresh.

## 20. Kiểm thử profile DPoP và sender-constrained token

Nếu hệ thống hỗ trợ DPoP hoặc mTLS-bound token, thêm test chuyên biệt:

**DPoP**

- `cnf.jkt` khớp public JWK thumbprint trong proof.
- Proof signature hợp lệ và dùng key bất đối xứng được phép.
- `htm`, `htu`, `iat`, `jti`, `ath` và nonce đúng.
- Proof cũ hoặc `jti` đã dùng bị từ chối theo replay policy.
- Proof từ key khác không thể dùng với access token hiện tại.
- Thiếu proof không được fallback thành bearer nếu profile yêu cầu DPoP.

**mTLS**

- Client certificate đúng thumbprint với `cnf.x5t#S256`.
- Certificate sai, hết hạn hoặc bị revoke bị từ chối theo policy.
- TLS termination proxy chỉ chuyển metadata đã xác minh.
- Header certificate do client tự khai không được tin.

Nếu không hỗ trợ các profile này, đánh dấu capability là unsupported; không tạo test pass giả bằng cách bỏ qua sender-constraining.

## 21. Test harness và quy trình chạy

Một harness liên thông nên có các thành phần:

- **Vector store:** lưu input, key test, metadata, nguồn chuẩn và expected result.
- **Producer adapters:** gọi implementation tạo JWS/JWE/JWK.
- **Consumer adapters:** gọi implementation độc lập xác minh/giải mã/import.
- **Clock control:** cung cấp thời gian cố định cho claims.
- **Key fixtures:** public/private test keys và certificate test.
- **Result normalizer:** chuẩn hóa pass, reject, unsupported và lỗi môi trường.
- **Evidence collector:** ghi phiên bản, cấu hình, reason code và thời gian chạy.

Quy trình:

1. Xác định token profile và capability matrix.
2. Nạp RFC vectors nguyên bản và kiểm tra integrity của fixture.
3. Chạy KAT cho primitive/JOSE.
4. Chạy positive và negative profile tests.
5. Chạy producer-consumer interoperability hai chiều.
6. Chạy mutation, differential và fuzz tests có giới hạn.
7. Chạy rotation/cache/deployment tests.
8. Phân loại failure và lưu regression vector.
9. Tạo báo cáo theo implementation version và cấu hình.

Không thay đổi nhiều biến cùng lúc trong một test case. Khi một vector thất bại, hãy tạo biến thể chỉ thay một yếu tố để khoanh vùng nguyên nhân.

## 22. Phân loại kết quả và báo cáo

Mỗi kết quả nên thuộc một trạng thái rõ:

| Trạng thái | Ý nghĩa |
| --- | --- |
| PASS | Hành vi đúng với vector và policy |
| FAIL | Hành vi sai hoặc chấp nhận token không hợp lệ |
| REJECT_EXPECTED | Token âm bị từ chối đúng |
| UNSUPPORTED | Implementation không tuyên bố hỗ trợ capability/profile này |
| ENVIRONMENT_ERROR | Test không chạy được do key store, network, clock hoặc dependency |
| INCONCLUSIVE | Không đủ bằng chứng để kết luận |

Báo cáo nên có:

- Implementation, version, crypto provider và cấu hình algorithm.
- Vector ID, nguồn chuẩn, profile và expected outcome.
- Producer/consumer direction.
- Kết quả thực tế và reason code.
- Input đã được redacted nếu có dữ liệu nhạy cảm.
- Bước tái lập ngắn gọn.
- Mức độ ảnh hưởng và regression test liên quan.

Không ghi production token, private key, client secret hoặc dữ liệu cá nhân vào artifact kiểm thử. Log test cũng cần được bảo vệ nếu chứa test credential có thể truy cập môi trường thật.

## 23. Lỗi kiểm thử thường gặp

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ test signer và verifier cùng một thư viện | Bug chung không bị phát hiện | Dùng implementation độc lập |
| Chỉ test token do chính hệ thống tạo | Không phát hiện khác biệt encoding/parser | Import vector chuẩn và token từ producer khác |
| So sánh mọi token string byte-for-byte | Báo lỗi giả với thuật toán randomized | Xác minh chữ ký và semantics; chỉ so output chính xác cho KAT |
| Dùng giờ máy thật | Test thời gian flaky | Fixed/injectable clock |
| Chỉ có positive tests | Token sai có thể vẫn được chấp nhận | Negative, mutation và profile-confusion vectors |
| Dùng cùng parser cho gateway và backend | Parser differential không được phát hiện | Test bằng parser/implementation độc lập |
| Không ghi phiên bản thư viện | Không tái lập được kết quả | Ghi version và crypto provider |
| Tự sửa vector RFC | Mất giá trị tham chiếu | Lưu nguyên bản và kiểm tra hash |
| Dùng production key trong fixture | Rò rỉ credential | Chỉ dùng test key công khai |
| Bỏ qua test vì capability unsupported nhưng vẫn báo pass | Báo cáo sai mức tương thích | Phân loại UNSUPPORTED |
| Chỉ test một instance/cache mới | Bỏ sót rotation và cache inconsistency | Test nhiều instance và cache state khác nhau |
| Bỏ qua negative test side effect | Token bị từ chối sau khi nghiệp vụ đã chạy | Xác nhận reject xảy ra trước side effect |

## 24. Checklist kiểm thử chuẩn và liên thông

**Vector và fixture**

- [ ] Có nguồn RFC/profile rõ ràng và vector được giữ nguyên.
- [ ] Fixture có ID, key, algorithm, clock, expected result và version.
- [ ] Không dùng production key/token hoặc dữ liệu cá nhân thật.
- [ ] Có KAT, positive, negative, mutation và regression vectors.

**JWS/JWE/JWK**

- [ ] JWS signing input và Base64url được kiểm thử theo byte chính xác.
- [ ] HMAC, RSA, RSA-PSS, ECDSA và EdDSA được kiểm tra nếu hỗ trợ.
- [ ] ECDSA raw signature encoding được kiểm tra.
- [ ] JWE AAD, IV, ciphertext và authentication tag được kiểm tra.
- [ ] JWK/JWKS import, metadata, thumbprint và key selection được kiểm tra.
- [ ] Unknown/duplicate `kid`, `crit` và malformed JSON được kiểm thử.

**JWT semantics và profile**

- [ ] `iss`, `aud`, `exp`, `nbf`, `iat`, `typ` và maximum age được kiểm tra.
- [ ] Có test token substitution và cross-JWT confusion.
- [ ] Profile-specific claims và headers được kiểm tra.
- [ ] Không dùng chữ ký hợp lệ làm điều kiện chấp nhận duy nhất.

**Interoperability**

- [ ] Có ít nhất hai implementation độc lập.
- [ ] Có producer-consumer test hai chiều.
- [ ] Không yêu cầu signature byte equality với thuật toán randomized.
- [ ] Có differential test và mutation/fuzz test.
- [ ] Có capability matrix và trạng thái UNSUPPORTED rõ ràng.

**Vận hành**

- [ ] Có test key rotation, JWKS refresh, cache và nhiều instance.
- [ ] Có test clock skew, outage và timeout.
- [ ] Token bị từ chối không gây side effect.
- [ ] Báo cáo ghi implementation version, vector ID và evidence.
- [ ] Regression suite chạy lại khi nâng thư viện hoặc crypto provider.

## 25. Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS compact serialization và ví dụ trong Appendix A.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE compact serialization, AAD và ví dụ trong Appendix A.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và key metadata.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán và parameters JOSE.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims và JWT processing.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): canonical JWK thumbprint.
- [RFC 7797 — JWS Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797): `b64`, `crit` và unencoded payload.
- [RFC 8037 — CFRG Elliptic Curve Signatures](https://www.rfc-editor.org/rfc/rfc8037): EdDSA trong JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh JWT an toàn.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token profile.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof và replay protection.

**Ghi nhớ:** vector chuẩn xác nhận hành vi ở một lớp; interoperability test xác nhận các implementation độc lập có thể trao đổi token theo cùng profile. Hãy kiểm thử cả hai chiều, giữ nguyên byte sequence và nguồn vector, bao phủ positive lẫn negative cases, kiểm soát clock/key/cache, rồi phân loại rõ PASS, FAIL, UNSUPPORTED và lỗi môi trường.
