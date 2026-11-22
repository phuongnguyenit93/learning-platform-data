# Fuzzing, kiểm thử lỗi và bảo đảm thất bại theo hướng từ chối

## 1. Mục tiêu của fuzzing và fail-closed testing

Một hệ thống xác minh JSON Web Token (JWT) nhận dữ liệu từ bên ngoài ở nhiều lớp: compact token, JOSE header, JSON claims, chữ ký, khóa công khai, metadata của issuer, trạng thái phiên và các bằng chứng sender-constrained như DPoP hoặc mTLS. Dữ liệu có thể sai định dạng, thiếu trường, quá lớn, mâu thuẫn hoặc được tạo có chủ đích để làm parser và verifier xử lý sai.

Kiểm thử thông thường thường dùng một số token hợp lệ và một số token lỗi đã biết. Cách đó cần thiết nhưng không bao phủ hết tổ hợp đầu vào. **Fuzzing** bổ sung bằng cách tạo nhiều biến thể đầu vào có cấu trúc hoặc ngẫu nhiên, rồi quan sát parser, verifier và hệ thống nghiệp vụ có giữ được các thuộc tính an toàn hay không.

**Fail-closed testing** kiểm tra cách hệ thống phản ứng khi không thể xác minh một điều kiện bảo mật. Khi chữ ký, issuer, audience, token profile, trạng thái thu hồi hoặc bằng chứng sở hữu không thể được xác nhận, hệ thống không được coi request là đã xác thực.

Ví dụ một tình huống lỗi:

~~~text
Resource server nhận JWT
       |
       v
JWKS cache không có kid mới
       |
       v
JWKS endpoint không truy cập được
       |
       v
Không thể xác minh chữ ký
       |
       v
Từ chối request
~~~

Hệ thống không được bỏ qua bước xác minh rồi sử dụng claims đã decode. Nếu có một khóa đã được tin cậy và cache còn nằm trong chính sách freshness/stale đã phê duyệt, hệ thống có thể dùng khóa đó theo policy. Nhưng khi không có đủ bằng chứng tin cậy để xác minh token, kết quả phải là từ chối.

Nguyên tắc cốt lõi:

> **Đầu vào bất thường, lỗi thư viện, lỗi mạng hoặc thiếu bằng chứng bảo mật không được biến thành một quyết định ALLOW. Fuzzing phải chứng minh điều đó bằng các thuộc tính có thể quan sát và lặp lại.**

Bài này thuộc phạm vi Security chung của JSON Web Token (JWT), JOSE, OAuth 2.0 và OpenID Connect. Các phương pháp áp dụng cho mọi thư viện, runtime và kiến trúc xác minh token, không phụ thuộc ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Phân biệt fuzzing, negative testing và fault injection

Ba kỹ thuật này bổ trợ cho nhau nhưng không giống nhau.

| Kỹ thuật | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Negative testing | Kiểm tra một trường hợp lỗi đã biết có bị từ chối không. | JWT hết hạn, sai audience hoặc chữ ký sai. |
| Fuzzing | Tạo nhiều đầu vào biến thể để tìm lỗi chưa được dự đoán. | JSON lồng sâu, Base64URL bất thường, claim sai kiểu, segment quá dài. |
| Fault injection | Chủ động làm một dependency hoặc thành phần vận hành thất bại. | JWKS timeout, replay store unavailable, clock lỗi, crypto provider không hoạt động. |

Có thể kết hợp cả ba:

1. Negative test xác nhận các quy tắc đã biết.
2. Fuzzing tìm parser bug, crash, khác biệt diễn giải và đường đi ngoài dự kiến.
3. Fault injection xác nhận hệ thống vẫn giữ quyết định an toàn khi dependency lỗi.

Một bài test chỉ xác nhận endpoint trả HTTP 401 chưa đủ. Cần kiểm tra principal, dữ liệu trả về, side effect, outbound request và trạng thái hệ thống sau khi xử lý đầu vào lỗi.

## 3. Fail-closed và fail-open trong xác minh token

### 3.1. Fail-closed

Fail-closed nghĩa là khi hệ thống không thể xác minh một điều kiện bắt buộc, nó không cấp quyền dựa trên giả định thuận lợi.

Ví dụ:

- Không xác minh được chữ ký: từ chối.
- Issuer không nằm trong trust registry: từ chối.
- Audience không khớp: từ chối.
- Thuật toán không nằm trong allowlist: từ chối.
- Claim bắt buộc thiếu hoặc sai kiểu: từ chối.
- DPoP proof sai hoặc replay: từ chối.
- Certificate binding không khớp: từ chối.
- Introspection bắt buộc nhưng endpoint không khả dụng: không chấp nhận token chỉ dựa trên giả định token còn active.

### 3.2. Fail-open

Fail-open xảy ra khi một lỗi kiểm tra làm hệ thống bỏ qua điều kiện bảo mật hoặc dùng một nguồn tin yếu hơn để tiếp tục.

Ví dụ:

~~~text
try:
    verifySignature(token)
catch error:
    decodePayload(token)
    continueAsAuthenticated()
~~~

Đây là lỗi nghiêm trọng: payload JWT có thể đọc được mà không cần chữ ký hợp lệ.

Các biến thể fail-open khác:

- JWKS không truy cập được nên chấp nhận token mà không xác minh chữ ký.
- Không tìm thấy kid nên dùng key đầu tiên trong cache.
- Clock service lỗi nên bỏ qua exp và nbf.
- Replay cache lỗi nên bỏ qua DPoP replay check.
- Không lấy được certificate nên chỉ kiểm tra bearer token.
- Introspection timeout nên coi token là active.
- Validator không hiểu typ hoặc crit nhưng vẫn tiếp tục.

### 3.3. Fail-closed không đồng nghĩa từ chối mọi request khi một dịch vụ ngoài lỗi

Chính sách cần phân biệt dependency nào là bắt buộc cho quyết định hiện tại và dữ liệu tin cậy nào đã có sẵn.

Ví dụ, nếu JWKS endpoint tạm thời lỗi nhưng resource server có public key đã xác minh trước đó, key vẫn còn trong thời gian cache/stale được policy cho phép và không có tín hiệu emergency revoke, verifier có thể dùng key đã cache để xác minh chữ ký offline. Đây là sử dụng bằng chứng tin cậy đã có, không phải bỏ qua xác minh.

Ngược lại, nếu token có kid chưa biết và server không thể tải JWKS mới, không có cơ sở để xác minh chữ ký; phải từ chối.

Quy tắc cần được ghi rõ:

- Chỉ dùng cache có nguồn gốc và issuer binding đã xác minh.
- Tôn trọng TTL và giới hạn stale được cấu hình.
- Emergency deny/revocation phải có khả năng vượt qua cache thông thường.
- Không chấp nhận key mới hoặc metadata mới khi chưa xác minh.
- Khi policy bắt buộc trạng thái online mà không thể truy vấn, không giả định trạng thái là hợp lệ.

## 4. Các bề mặt cần fuzz trong hệ thống JWT

Một chương trình fuzzing nên chia theo bề mặt để biết test đang tìm lỗi ở lớp nào.

| Bề mặt | Đầu vào cần fuzz | Lỗi cần phát hiện |
| --- | --- | --- |
| Compact serialization | Số segment, dấu chấm, Base64URL, độ dài | Parser crash, parse lệch segment, chấp nhận malformed token. |
| JOSE header | alg, kid, typ, crit, jku, x5u, jwk, cty | Algorithm confusion, key lookup sai, bỏ qua critical extension. |
| Payload claims | iss, sub, aud, exp, nbf, iat, jti, scope, tenant, roles | Sai kiểu, sai ngữ nghĩa, claim injection. |
| JSON parser | Duplicate members, nesting, Unicode, number range | Parser differential, memory/CPU exhaustion. |
| JWS | Protected header, payload, signature | Chấp nhận chữ ký sai hoặc ghép nhầm segment. |
| JWE | Encrypted key, IV, ciphertext, authentication tag | Giải mã không an toàn, bỏ qua authentication failure. |
| JWKS/metadata | JSON key set, URI, redirect, response size | SSRF, key confusion, parser failure. |
| Runtime dependencies | Network, clock, key store, crypto provider, cache | Fail-open khi dependency lỗi. |
| DPoP/mTLS | Proof, nonce, replay state, certificate chain | Replay, binding bypass, certificate spoofing. |
| Application boundary | Principal, authorization, database, event | Side effect trước khi xác thực hoàn tất. |

Không nên chỉ fuzz hàm parse token độc lập rồi coi toàn bộ hệ thống an toàn. Cần fuzz cả đường đi từ request đầu vào tới quyết định xác thực và hành động nghiệp vụ.

## 5. Chuẩn bị corpus và test environment

### 5.1. Corpus bắt đầu từ token hợp lệ

Một corpus hữu ích có các fixture hợp lệ cho từng profile:

- JWT access token theo profile đang dùng.
- OIDC ID Token nếu hệ thống có xử lý OIDC.
- JWT nội bộ nếu ứng dụng có profile riêng.
- DPoP proof nếu resource server hỗ trợ DPoP.
- JWE hoặc nested JWT nếu hệ thống hỗ trợ.
- Token được ký bằng key hiện tại và key cũ trong overlap rotation.

Mỗi fixture cần ghi metadata test ở ngoài token: profile, issuer dự kiến, audience, thuật toán, key ID, thời gian và kết quả mong đợi. Không ghi private key hoặc raw production token vào corpus.

### 5.2. Tách fixture hợp lệ và fixture lỗi

Nên có ba nhóm:

1. **Valid seeds:** token chuẩn được endpoint chấp nhận.
2. **Malformed seeds:** token sai cấu trúc, sai encoding hoặc sai kiểu.
3. **Signed-invalid seeds:** token có chữ ký hợp lệ nhưng vi phạm policy như issuer, audience, typ, scope hoặc required claims.

Nhóm thứ ba rất quan trọng. Nếu mọi seed lỗi đều có chữ ký sai, verifier có thể dừng ở signature check và các policy check phía sau không được kiểm tra.

### 5.3. Dùng khóa và dữ liệu riêng cho test

- Tạo test issuer và test signing key riêng.
- Không dùng private signing key production.
- Dùng subject, tenant, account và resource giả.
- Chạy fuzzing trong môi trường cô lập.
- Không gửi fuzz traffic tới Authorization Server hoặc API production.
- Không cho fuzz harness tự do truy cập mạng.
- Có giới hạn CPU, memory, thời gian và số request.

### 5.4. Kiểm soát thời gian

Token phụ thuộc exp, nbf, iat, nonce và cache TTL. Dùng clock có thể điều khiển hoặc fixture có thời hạn đủ rộng để kết quả không thay đổi ngẫu nhiên giữa các lần chạy.

Các test về clock skew, token expiration và stale cache nên đặt thời gian ở các biên rõ ràng, thay vì dựa vào sleep hoặc thời gian thực không kiểm soát.

## 6. Fuzzing compact serialization và Base64URL

JWS Compact Serialization thông thường có ba segment:

~~~text
protected-header.payload.signature
~~~

JWE Compact Serialization có năm segment:

~~~text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
~~~

### 6.1. Số segment và separator

Tạo các đầu vào:

- Chuỗi rỗng.
- Chỉ có một segment.
- Hai segment.
- Bốn segment cho JWS.
- Ba hoặc bốn segment cho JWE.
- Nhiều hơn số segment quy định.
- Dấu chấm ở đầu/cuối.
- Dấu chấm liên tiếp tạo segment rỗng.
- Token chứa newline, tab hoặc khoảng trắng ở vị trí không được phép.

Parser phải từ chối cấu trúc không đúng profile, không tự đoán token thuộc JWS hay JWE bằng cách bỏ qua segment.

### 6.2. Base64URL malformed

Fuzz từng segment với:

- Ký tự không thuộc alphabet Base64URL.
- Padding không phù hợp.
- Segment bị cắt giữa chừng.
- Encoding có byte không hợp lệ.
- Chuỗi quá dài.
- Segment rỗng ở vị trí bắt buộc.
- Nhiều cách biểu diễn không được parser hỗ trợ.

Parser cần có quy tắc nhất quán. Không để một thành phần giải mã theo cách permissive còn thành phần khác xác minh theo cách khác.

### 6.3. Kích thước segment

Kiểm tra:

- Header rất lớn.
- Payload rất lớn.
- Signature rất dài hoặc quá ngắn.
- Token tổng thể vượt giới hạn.
- Segment có độ dài làm phát sinh cấp phát bộ nhớ lớn.

Giới hạn kích thước phải được áp dụng trước khi giải mã toàn bộ nội dung nếu có thể.

### 6.4. Không crash hoặc treo parser

Các đầu vào malformed phải dẫn tới lỗi có kiểm soát. Không được:

- Crash tiến trình xác minh.
- Tạo vòng lặp vô hạn.
- Tăng bộ nhớ không giới hạn.
- Chiếm CPU kéo dài.
- Làm cạn connection pool hoặc thread pool.

Crash trong một worker xử lý token vẫn có thể ảnh hưởng toàn bộ dịch vụ nếu không có giới hạn tài nguyên và cô lập phù hợp.

## 7. Fuzzing JSON header và payload

### 7.1. JSON syntax

Tạo các trường hợp:

- Thiếu dấu ngoặc, dấu phẩy hoặc dấu nháy.
- String escape sai.
- UTF-8 không hợp lệ.
- Unicode escape bất thường.
- Object hoặc array lồng quá sâu.
- Number quá lớn hoặc vượt giới hạn parser.
- Giá trị NaN/Infinity nếu parser có thể gặp qua extension ngoài JSON chuẩn.
- Member có kiểu không đúng.

JSON malformed phải bị từ chối trước khi claims được dùng.

### 7.2. Duplicate member

Ví dụ:

~~~json
{
  "iss": "https://identity.test.example",
  "iss": "https://attacker.test.example",
  "aud": "https://api.test.example/billing"
}
~~~

Parser có thể xử lý member trùng theo quy tắc khác nhau. Theo JWT, parser cần từ chối member trùng hoặc dùng giá trị xuất hiện cuối cùng theo quy tắc của chuẩn. Với hệ thống bảo mật, chính sách từ chối duplicate member giúp giảm sự nhập nhằng giữa các thành phần.

Điều quan trọng là parser dùng trong xác minh và parser dùng trong nghiệp vụ phải có cùng cách diễn giải. Không để signature verifier nhìn thấy issuer này còn authorization layer nhìn thấy issuer khác.

### 7.3. Claim sai kiểu

Thử các biến thể:

~~~json
{
  "iss": 123,
  "sub": {},
  "aud": false,
  "exp": "tomorrow",
  "nbf": [],
  "iat": null,
  "scope": {"admin": true}
}
~~~

Nếu profile yêu cầu iss/sub là string, aud là StringOrURI hoặc array, NumericDate là số và scope có định dạng cụ thể, verifier phải từ chối kiểu không hợp lệ.

Không tự ép kiểu string, number, boolean hoặc object để cố tiếp tục xác minh.

### 7.4. NumericDate và số biên

Fuzz:

- Số âm.
- Số rất lớn.
- Số thập phân.
- Giá trị vượt giới hạn integer của runtime.
- Giá trị bằng đúng thời điểm hiện tại.
- Giá trị sát clock skew boundary.
- exp nhỏ hơn iat.
- nbf lớn hơn exp.

Profile và ứng dụng phải định nghĩa các quan hệ thời gian hợp lệ. Không để overflow hoặc ép kiểu làm token hết hạn được hiểu thành token còn hạn.

### 7.5. String và Unicode

Thử:

- String rỗng.
- Chuỗi rất dài.
- Ký tự điều khiển.
- Unicode normalization khác nhau.
- Ký tự nhìn giống nhau nhưng code point khác.
- Null byte hoặc ký tự escape.
- Whitespace đầu/cuối.

Issuer và audience cần được so khớp theo định danh chuẩn, không dùng so khớp mơ hồ sau khi tự ý trim hoặc normalize.

## 8. Fuzzing JOSE header và thuật toán

JOSE header ảnh hưởng đến thuật toán, khóa và cách diễn giải token. Header đến từ người gửi nên phải được coi là dữ liệu chưa tin cậy cho đến khi xác minh chữ ký.

### 8.1. alg

Fuzz các trường hợp:

- Thiếu alg.
- alg là null, number, array hoặc object.
- alg rỗng.
- alg = none.
- Thuật toán ngoài allowlist.
- Thuật toán đúng tên nhưng key type không tương thích.
- Thay đổi chữ hoa/thường.
- Giá trị gần giống tên thuật toán hợp lệ.

Verifier phải chỉ chấp nhận thuật toán nằm trong allowlist được cấu hình cho issuer và token profile. Không fallback sang thuật toán khác.

### 8.2. kid

Fuzz:

- kid thiếu hoặc rỗng.
- kid quá dài.
- kid chứa Unicode hoặc ký tự điều khiển.
- kid có giá trị trùng giữa issuer.
- kid không tồn tại.
- kid trỏ tới một key có use/alg không phù hợp.
- Nhiều JWK cùng kid tạo kết quả nhập nhằng.

Không dùng kid như URL và không tra cứu toàn cục ngoài issuer/JWKS đã tin cậy.

### 8.3. crit

Test:

- crit có extension không được hỗ trợ.
- crit không phải array theo yêu cầu.
- crit rỗng hoặc có phần tử trùng.
- crit tham chiếu header parameter không tồn tại.
- Header extension được khai báo nhưng parser bỏ qua.

Verifier phải từ chối critical extension mà nó không hiểu hoặc không xử lý. Không bỏ qua crit rồi tiếp tục như thể extension không quan trọng.

### 8.4. jku, x5u và jwk

Thử URL loopback, private IP, link-local, domain ngoài allowlist, redirect và scheme không an toàn. Xác minh:

- Verifier không tự fetch URL tùy ý từ token.
- Không có SSRF tới mạng nội bộ.
- JWK nhúng không tự trở thành trust anchor.
- Private key material trong JWK bị từ chối.
- Key selection vẫn gắn với issuer và profile đã cấu hình.

### 8.5. typ và cty

Thử typ sai, thiếu typ khi profile yêu cầu, typ có kiểu không hợp lệ và cty không phù hợp với nested JWT policy. Token type phải được xác minh theo profile; không chỉ tin header tự khai báo.

## 9. Fuzzing JWS, chữ ký và thuật toán

### 9.1. Sửa signing input

Với JWS, thay đổi protected header hoặc payload nhưng giữ signature cũ phải làm xác minh chữ ký thất bại.

Fuzz:

- Thay một byte ở header segment.
- Thay một byte ở payload segment.
- Thay thứ tự JSON member rồi encode lại.
- Thay whitespace.
- Thay Base64URL representation.
- Ghép header/payload từ token khác.

Không canonicalize token trước khi xác minh theo cách làm thay đổi signing input của JWS.

### 9.2. Sửa signature

Fuzz:

- Flip một bit.
- Thay signature bằng bytes ngẫu nhiên.
- Cắt ngắn signature.
- Làm rỗng signature.
- Dùng signature của token khác.
- Dùng signature từ key khác.
- Dùng signature có độ dài không hợp lệ với thuật toán.

Verifier phải thực hiện xác minh mật mã thực sự, không chỉ kiểm tra signature có định dạng hoặc độ dài trông hợp lệ.

### 9.3. Key/algorithm mismatch

Tạo signed-valid token với các tổ hợp:

- RSA key và thuật toán EC.
- EC key sai curve.
- HMAC secret không đúng.
- RSA key dưới kích thước tối thiểu của policy.
- JWK use = enc.
- key_ops không cho phép verify.
- Key bị disable hoặc emergency revoked.

Các tổ hợp không tương thích hoặc ngoài policy phải bị từ chối.

### 9.4. Không fuzz thuật toán mật mã bằng cách tự viết lại nó

Fuzzing nên tập trung vào parser, adapter, key selection, validation pipeline và cách ứng dụng xử lý kết quả của thư viện mật mã đã được kiểm chứng. Không tự viết thuật toán chữ ký hoặc mã hóa để tạo một verifier song song.

Dùng test vector chuẩn và các thư viện mật mã được duy trì. Nếu fuzzing trực tiếp một crypto provider, thực hiện theo quy trình riêng của nhà cung cấp và trong môi trường cô lập.

## 10. Fuzzing JWE và nested JWT

JWE có năm segment và dùng encryption/authentication. Không áp dụng quy tắc JWS ba segment cho JWE.

### 10.1. JWE mutation

Thử thay đổi:

- Protected header.
- Encrypted key.
- Initialization Vector (IV).
- Ciphertext.
- Authentication tag.
- Encoding hoặc số segment.

Với authenticated encryption, thay đổi dữ liệu được bảo vệ phải dẫn tới authentication/decryption failure. Không được trả plaintext cho tầng ứng dụng khi authentication tag không hợp lệ.

### 10.2. Sai thuật toán hoặc key management

Thử:

- alg hoặc enc ngoài allowlist.
- Key management algorithm không tương thích.
- Content encryption method không được hỗ trợ.
- Encrypted key rỗng hoặc sai độ dài.
- IV không đúng yêu cầu thuật toán.
- Authentication tag bị cắt hoặc thay đổi.

Verifier/decrypter phải từ chối trước khi sử dụng nội dung chưa được xác thực.

### 10.3. Nested JWT

Nếu JWE chứa JWS hoặc ngược lại, fuzz từng lớp:

1. Outer serialization.
2. Outer header và encryption/authentication.
3. Inner compact serialization.
4. Inner signature.
5. Token profile và claims.

Giải mã thành công lớp ngoài không có nghĩa chữ ký lớp trong hợp lệ. Xác minh lớp trong thất bại phải làm toàn bộ credential bị từ chối.

## 11. Fuzzing metadata và JWKS

Resource server có thể tải metadata/JWKS qua mạng. Đây là một bề mặt đầu vào riêng, không chỉ là một phần của token.

### 11.1. JWKS JSON

Fuzz:

- Không có member keys.
- keys không phải array.
- Phần tử không phải object.
- JWK thiếu kty hoặc tham số bắt buộc.
- RSA n/e sai định dạng.
- EC curve hoặc tọa độ không hợp lệ.
- kid trùng hoặc quá dài.
- JWK có private key material.
- JWKS quá lớn hoặc chứa quá nhiều key.
- JSON duplicate member hoặc malformed.

JWKS sai cấu trúc phải bị từ chối. Không dùng một phần key set hợp lệ nếu policy yêu cầu toàn bộ response phải hợp lệ mà không có quy tắc xử lý partial rõ ràng.

### 11.2. Metadata và jwks_uri

Fault/fuzz:

- Metadata thiếu issuer hoặc jwks_uri bắt buộc.
- Issuer metadata không khớp issuer dự kiến.
- jwks_uri dùng HTTP khi policy yêu cầu HTTPS.
- URI chứa userinfo, port hoặc scheme ngoài policy.
- URL trỏ tới loopback/private/link-local.
- DNS trả IP ngoài phạm vi cho phép.
- Redirect sang host không tin cậy.
- Response quá lớn hoặc sai content type.
- TLS certificate sai hostname hoặc hết hạn.

Không fetch issuer hoặc jwks_uri do token chưa xác minh tự cung cấp. Metadata và JWKS phải được gắn với trust bootstrap đã phê duyệt.

### 11.3. SSRF và egress

Xác minh server không truy cập:

- Loopback IPv4/IPv6.
- Private network.
- Link-local.
- Cloud metadata endpoint.
- Control plane hoặc database nội bộ.
- Domain attacker-controlled ngoài allowlist.

Kiểm tra cả redirect và DNS rebinding. Chỉ kiểm tra chuỗi hostname trước khi request là chưa đủ.

## 12. Resource exhaustion và DoS resistance

Fuzzing bảo mật phải xem xét cả tính sẵn sàng. Một token sai không nên có khả năng làm cạn CPU, memory, network hoặc worker pool.

### 12.1. Giới hạn đầu vào

Đặt giới hạn cho:

- Kích thước Authorization header.
- Kích thước compact JWT.
- Độ dài mỗi segment.
- Kích thước JSON header/payload.
- Độ sâu JSON nesting.
- Số lượng claims và phần tử array.
- Độ dài string và kid.
- Kích thước JWKS/metadata.
- Số lượng JWK trong một response.
- Kích thước certificate chain.

Giới hạn cần phù hợp với profile và token thực tế. Không dùng giới hạn quá lớn chỉ để tránh lỗi đầu vào.

### 12.2. Giới hạn tài nguyên tính toán

Kiểm tra:

- CPU time cho parse và verify.
- Memory allocation cho token lớn.
- Số lần refresh JWKS khi kid lạ.
- Số outbound request khi nhiều token lỗi cùng lúc.
- Số lần retry khi dependency timeout.
- Số request chờ replay store hoặc introspection.
- Số certificate path validation đồng thời.

Dùng timeout, concurrency limit, rate limit và circuit breaker phù hợp. Circuit breaker không được chuyển validation failure thành ALLOW.

### 12.3. Unknown kid storm

Attacker có thể gửi nhiều token với kid ngẫu nhiên để ép server refresh JWKS liên tục.

Kiểm thử:

- Gửi nhiều kid khác nhau trong thời gian ngắn.
- Gửi cùng kid lạ từ nhiều request đồng thời.
- Làm JWKS endpoint chậm hoặc lỗi.
- Quan sát outbound request count, cache contention và CPU.

Kết quả mong đợi:

- Refresh có rate limit/single-flight.
- Không có request không giới hạn cho mỗi kid.
- Token không tìm được key bị từ chối.
- Hệ thống vẫn phục vụ request hợp lệ trong giới hạn tài nguyên.

### 12.4. JSON nesting và pathological input

JSON lồng sâu, chuỗi lớn hoặc số cực trị có thể gây parser chậm hoặc tiêu thụ bộ nhớ. Fuzz harness phải có giới hạn riêng để không tự làm quá tải máy chạy test.

## 13. Fault injection cho JWKS, metadata và key store

### 13.1. JWKS endpoint timeout

Thiết lập JWKS endpoint chậm hơn timeout:

- Nếu key đã cache và vẫn nằm trong freshness policy, verifier có thể dùng key đã tin cậy.
- Nếu kid chưa biết và không tải được key mới, từ chối token.
- Không bỏ qua chữ ký.
- Không dùng key không liên quan để thử tiếp.
- Có metric/cảnh báo về refresh failure.

### 13.2. HTTP lỗi hoặc response malformed

Thử 404, 500, 429, body rỗng, JSON malformed, response bị cắt giữa chừng và content type sai.

Không ghi đè cache tốt bằng response lỗi. Không coi HTTP 200 là đủ để tin JWKS nếu JSON hoặc key validation thất bại.

### 13.3. TLS và DNS failure

Thử:

- Certificate không tin cậy.
- Hostname mismatch.
- Certificate hết hạn.
- DNS resolution failure.
- DNS trả private IP ngoài policy.
- Connection reset.
- Redirect loop.

Không hạ cấp sang HTTP hoặc tắt certificate verification để khôi phục request.

### 13.4. Cache corruption hoặc cache miss

Thử:

- Cache rỗng.
- Cache chứa JSON malformed.
- Cache bị ghi nhầm issuer.
- Cache key chỉ dựa vào kid.
- Cache chứa key đã emergency revoked.
- Cache vượt TTL hoặc stale limit.

Cache phải gắn với issuer và nguồn metadata đã xác minh. Nếu cache không thể được xác nhận là đáng tin, không dùng nó để chấp nhận token.

### 13.5. Key store hoặc HSM unavailable

Nếu issuer ký token bằng HSM hoặc key store, lỗi signing có thể làm token endpoint không cấp token mới. Không chuyển sang key yếu hoặc key test để tiếp tục.

Nếu resource server dùng crypto provider hoặc key store để verify và thành phần đó lỗi, request cần bị từ chối hoặc trả lỗi vận hành phù hợp. Không bỏ qua chữ ký.

## 14. Fault injection cho clock, revocation và trạng thái

### 14.1. Clock source không đáng tin

Kiểm thử:

- Clock đi lùi.
- Clock nhảy tiến.
- Clock drift giữa các instance.
- Clock source unavailable.
- Timestamp nằm đúng biên clock skew.

Nếu không thể xác định thời gian đáng tin để kiểm tra exp/nbf/iat theo profile, không chấp nhận token dựa trên việc bỏ qua time validation.

### 14.2. Introspection unavailable

Với opaque token hoặc policy yêu cầu kiểm tra trạng thái online:

- Introspection timeout.
- TLS failure.
- Response malformed.
- Response thiếu active.
- Response có active sai kiểu.
- Client authentication tới introspection endpoint thất bại.

Nếu trạng thái online là điều kiện bắt buộc, không coi lỗi truy vấn là active. Chỉ dùng cache introspection nếu có freshness policy rõ và được phép.

### 14.3. Revocation store unavailable

Nếu ứng dụng yêu cầu kiểm tra token/session revocation online, làm revocation store unavailable và xác minh hệ thống không tự bỏ qua bước này. Nếu thiết kế chấp nhận JWT offline tới exp, phải ghi rõ giới hạn thu hồi; không tuyên bố đã thu hồi tức thì khi resource server không có cách nhận tín hiệu.

### 14.4. Replay store unavailable

Với DPoP hoặc cơ chế one-time proof yêu cầu replay detection, nếu replay store không ghi được jti một cách atomic thì không chấp nhận proof như thể nó chưa từng được dùng.

Có thể trả lỗi tạm thời để client thử lại theo giao thức. Không fallback sang bỏ kiểm tra replay.

### 14.5. Nonce service unavailable

Nếu policy hoặc profile yêu cầu nonce:

- Không chấp nhận proof thiếu nonce.
- Không tự tạo nonce cố định hoặc dùng nonce mặc định.
- Không bỏ qua nonce validation khi service lỗi.
- Trả lỗi/challenge phù hợp và ghi nhận dependency failure.

## 15. Fault injection cho mTLS và sender binding

### 15.1. Client certificate thiếu hoặc không hợp lệ

Test:

- Không gửi client certificate.
- Certificate hết hạn.
- Chain không tin cậy.
- Key usage hoặc extended key usage không phù hợp.
- Certificate bị revoke theo policy.
- Certificate không khớp thumbprint trong cnf.x5t#S256.

Certificate-bound token phải bị từ chối khi không xác minh được đúng chứng thư đã gắn với token.

### 15.2. TLS termination và proxy failure

Nếu Gateway xác minh certificate rồi chuyển thông tin tới backend:

- Mất header certificate đã xác minh.
- Client tự gửi header giả.
- Proxy không xóa header đầu vào của client.
- Backend bị gọi trực tiếp.
- Kênh Gateway-backend không được xác thực.
- Proxy gửi certificate thumbprint khác với kết nối ban đầu.

Backend chỉ được tin thông tin certificate từ một proxy đã xác thực theo trust contract. Khi không chứng minh được nguồn của forwarded identity, từ chối.

### 15.3. DPoP proof failure

Fault/fuzz:

- Proof signature invalid.
- Public key thumbprint không khớp cnf.jkt.
- jti đã được dùng.
- htm/htu sai.
- ath không khớp access token.
- iat ngoài cửa sổ.
- Nonce thiếu hoặc sai khi được yêu cầu.
- Replay cache unavailable.

Không chấp nhận access token DPoP-bound chỉ vì access token riêng lẻ có chữ ký hợp lệ.

## 16. Fail-closed theo từng bước của validation pipeline

Một pipeline minh họa:

~~~mermaid
flowchart TD
    A["Nhận credential"] --> B{"Compact token hợp lệ?"}
    B -- Không --> X["REJECT"]
    B -- Có --> C{"Profile và header được hỗ trợ?"}
    C -- Không --> X
    C -- Có --> D{"Có key tin cậy phù hợp?"}
    D -- Không --> X
    D -- Có --> E{"Chữ ký hoặc authentication tag hợp lệ?"}
    E -- Không --> X
    E -- Có --> F{"Issuer, audience, time và claims hợp lệ?"}
    F -- Không --> X
    F -- Có --> G{"Revocation và sender proof đạt yêu cầu?"}
    G -- Không --> X
    G -- Có --> H["Tạo verified principal"]
    H --> I{"Authorization cho action/resource?"}
    I -- Không --> Y["DENY"]
    I -- Có --> Z["ALLOW"]
~~~

Mỗi bước phải có kết quả rõ ràng. Không dùng giá trị mặc định có lợi cho người gửi khi parser, key source hoặc dependency trả lỗi.

### 16.1. Không tạo principal sớm

Không tạo authenticated principal ngay sau khi decode payload hoặc sau khi chỉ xác minh chữ ký. Principal chỉ được tạo sau khi token vượt qua toàn bộ validation profile và các điều kiện bắt buộc.

### 16.2. Không fallback sang validator khác

Nếu access-token validator từ chối token vì sai typ, không thử ID Token validator hoặc validator JWT tổng quát. Nếu key lookup thất bại, không thử key từ jku hoặc một issuer khác.

### 16.3. Authorization cũng phải fail closed

Token hợp lệ không đủ để cho phép mọi hành động. Nếu policy engine, membership store hoặc object ownership check là điều kiện bắt buộc mà không thể truy vấn, API không được tự động cho phép thao tác được bảo vệ.

Có thể trả lỗi tạm thời thay vì kết luận user không có quyền, nhưng kết quả bảo mật vẫn phải là không thực hiện hành động.

## 17. Error handling và phân loại kết quả

Một hệ thống nên phân biệt lỗi credential với lỗi vận hành nội bộ.

| Nhóm | Ví dụ | Kết quả bảo mật |
| --- | --- | --- |
| MALFORMED_TOKEN | Compact token hoặc JSON sai cấu trúc | Reject. |
| UNSUPPORTED_PROFILE | typ, crit hoặc token profile không hỗ trợ | Reject. |
| UNSUPPORTED_ALGORITHM | alg ngoài allowlist | Reject. |
| KEY_NOT_FOUND | kid không có trong JWKS đã tin cậy | Reject sau refresh có giới hạn. |
| SIGNATURE_INVALID | Chữ ký sai | Reject. |
| INVALID_ISSUER/AUDIENCE | iss hoặc aud không khớp | Reject. |
| INVALID_CLAIMS | Claim thiếu, sai kiểu hoặc sai ngữ nghĩa | Reject. |
| EXPIRED/NOT_YET_VALID | Điều kiện thời gian không đạt | Reject. |
| REPLAY_DETECTED | DPoP jti/proof đã được sử dụng | Reject. |
| SENDER_BINDING_FAILED | Key/certificate không khớp token | Reject. |
| TRUST_SOURCE_UNAVAILABLE | Không có metadata/key đáng tin cậy để xác minh | Không authenticate; trả lỗi phù hợp. |
| REVOCATION_CHECK_UNAVAILABLE | Trạng thái online bắt buộc không kiểm tra được | Không authenticate theo policy. |
| INTERNAL_VALIDATOR_ERROR | Parser, crypto provider hoặc dependency lỗi | Không authenticate. |

### 17.1. Public error và internal reason code

Phản hồi công khai nên theo contract của giao thức, tránh lộ chi tiết nội bộ về key ID, issuer registry, parser stack trace hoặc cấu trúc hạ tầng.

Log nội bộ có thể ghi:

- Correlation ID.
- Endpoint/token profile.
- Nhóm lỗi.
- Validation stage.
- Dependency và timeout category.
- Kết quả fail-closed.

Không ghi raw JWT, refresh token, private key, toàn bộ Authorization header hoặc secret. Nếu cần liên kết sự kiện, dùng token ID/fingerprint đã được bảo vệ.

### 17.2. Không biến lỗi vận hành thành invalid user một cách sai lệch

Nếu JWKS service hoặc replay store đang lỗi, đó có thể là lỗi vận hành chứ không chứng minh user gửi credential giả. Public response vẫn có thể là lỗi xác thực hoặc lỗi tạm thời theo API contract, nhưng audit/metric cần phân biệt để đội vận hành xử lý đúng.

## 18. Property-based testing và security invariants

Property-based testing kiểm tra các thuộc tính phải đúng với nhiều đầu vào, thay vì chỉ một bộ ví dụ cố định.

### 18.1. Invariant về chữ ký

Với mọi JWS fixture hợp lệ:

~~~text
mutateProtectedHeader(token) -> reject
mutatePayload(token)         -> reject
mutateSignature(token)      -> reject
~~~

Giả định mutation thật sự thay đổi signing input hoặc signature và không tạo lại chữ ký hợp lệ.

### 18.2. Invariant về trust

~~~text
issuer not in trusted registry -> never authenticate
audience not accepted by endpoint -> never authenticate
algorithm not in allowlist -> never authenticate
key not bound to trusted issuer -> never authenticate
token profile mismatch -> never authenticate
~~~

### 18.3. Invariant về parser

~~~text
malformed compact serialization -> controlled rejection
unsupported critical header -> rejection
ambiguous claims representation -> deterministic rejection
oversized input -> bounded resource use
~~~

### 18.4. Invariant về side effect

~~~text
if authentication is not verified:
    authenticatedPrincipal == absent
    protectedDataReturned == false
    businessStateChange == false
    downstreamPrivilegedCall == false
~~~

### 18.5. Invariant về dependency failure

~~~text
if requiredTrustEvidenceUnavailable:
    decision != ALLOW

if requiredReplayCheckUnavailable:
    proof != ACCEPTED

if requiredRevocationCheckUnavailable:
    token != ASSUMED_ACTIVE
~~~

Các invariant cần được kiểm tra ở ranh giới hệ thống, không chỉ trong unit test của parser.

## 19. Differential testing giữa parser và verifier

Nếu cùng token được xử lý bởi nhiều thành phần, chúng phải hiểu token nhất quán.

Ví dụ:

- API Gateway và backend.
- Hai phiên bản thư viện JWT trong giai đoạn migration.
- Parser ở tầng authentication và parser ở tầng authorization.
- Các region có cấu hình khác nhau.
- JWT verifier và công cụ audit đọc claims.

Chạy cùng corpus và so sánh:

- Số segment và cách parse.
- Base64URL decoding.
- Duplicate JSON member behavior.
- Claim type interpretation.
- Issuer/audience matching.
- JOSE header/critical extension handling.
- Signature/JWE authentication result.
- Accept/reject outcome.

Nếu một thành phần chấp nhận trong khi thành phần khác từ chối, phải điều tra sự khác biệt. Không chọn hành vi permissive hơn chỉ để giảm lỗi tương thích.

## 20. Chaos testing và kiểm thử vận hành

Fuzzing tập trung vào đầu vào; chaos/fault testing tập trung vào sự cố hệ thống trong lúc xác minh token.

### 20.1. Dependency outage

Thử tắt hoặc làm chậm:

- Discovery metadata endpoint.
- JWKS endpoint.
- Introspection endpoint.
- Revocation store.
- Replay cache.
- Clock/time source.
- Certificate validation service nếu có.
- Key management/crypto provider.

Xác minh hệ thống không tự bỏ qua kiểm tra bắt buộc.

### 20.2. Network partition

Tạo tình huống một số instance truy cập được JWKS/replay store, một số instance không truy cập được. Kiểm tra:

- Không có instance nào tự fallback sang ALLOW.
- Cache có namespace theo issuer.
- Stale policy được áp dụng nhất quán.
- Emergency deny/revocation được truyền tới mọi instance.
- Retry không tạo request storm.

### 20.3. Rolling deployment

Khi hai phiên bản verifier chạy song song:

- Cùng allowlist thuật toán.
- Cùng issuer/audience/profile.
- Cùng quy tắc claim parsing.
- Cùng giới hạn stale và clock skew.
- Cùng hành vi fail-closed.

Nếu policy thay đổi, triển khai có version và có test tương thích rõ ràng.

### 20.4. Quan sát tác động vận hành

Đo:

- Tỷ lệ token malformed.
- Tỷ lệ signature failure.
- Tỷ lệ unknown kid.
- JWKS refresh count và latency.
- Replay detection count.
- Dependency timeout/error.
- Parser CPU/memory.
- Request rejected do resource limit.
- Số side effect được ngăn.

Không tạo metric label từ raw token hoặc claim không giới hạn vì có thể gây lộ dữ liệu và cardinality explosion.

## 21. Test matrix tổng hợp

| Nhóm | Fault/mutation | Kết quả mong đợi |
| --- | --- | --- |
| Serialization | Sai số segment, dấu chấm, Base64URL | Reject có kiểm soát. |
| JSON | Malformed, duplicate member, nesting sâu | Reject; không crash hoặc parse lệch. |
| Header | alg none/unknown, kid lạ, crit không hỗ trợ | Reject; không fallback. |
| Claims | iss/aud sai, required claim thiếu, sai kiểu | Reject. |
| JWS | Header/payload/signature bị sửa | Signature verification fail. |
| JWE | Authentication tag/ciphertext bị sửa | Decryption/authentication fail; không trả plaintext. |
| JWKS | JSON lỗi, key sai type, kid trùng | Không dùng key không hợp lệ. |
| Network | Timeout, TLS error, redirect ngoài policy | Không bỏ qua trust check. |
| Clock | Clock unavailable/drift | Không bỏ qua time validation. |
| Introspection | Timeout hoặc response malformed | Không giả định active nếu online check bắt buộc. |
| Replay | Replay store lỗi hoặc jti trùng | Không chấp nhận proof replay. |
| mTLS | Certificate thiếu/sai/revoked | Reject sender binding. |
| Authorization | Policy engine hoặc membership store lỗi | Không thực hiện hành động được bảo vệ. |
| Resource | Token/JWKS/JSON quá lớn | Bounded CPU/memory và reject. |
| Logging | Token lỗi và exception | Không ghi raw credential. |
| Multi-instance | Cache/policy không đồng bộ | Không có đường accept ngoài policy. |

## 22. Pseudocode: fuzz harness và kiểm tra invariant

Ví dụ ở mức khái niệm:

~~~text
function fuzzJwtVerifier(seedCorpus, verifier, protectedEndpoint):
    for each seed in seedCorpus:
        if seed.expectedValid:
            assert verifier.validate(seed.token) == ACCEPT

        mutations = generateStructuredMutations(
            seed.token,
            targets = [
                "compact_segments",
                "base64url",
                "json_header",
                "json_payload",
                "jose_parameters",
                "signature"
            ],
            bounded = true
        )

        for each candidate in mutations:
            result = verifier.validate(candidate)

            if result != ACCEPT:
                assert result.principal is absent

            response = protectedEndpoint.send(candidate)
            assert response.didNotExposeProtectedData
            assert response.didNotCauseBusinessSideEffect


function injectDependencyFailure(verifier, dependency):
    dependency.failMode = TIMEOUT

    result = verifier.validate(tokenRequiring(dependency))

    assert result != ACCEPT
    assert noDecodeOnlyFallbackOccurred()
    assert failureWasObservableWithoutLeakingSecrets()
~~~

Đây là pseudocode mô tả mục tiêu kiểm thử, không phải API của thư viện cụ thể. Harness phải có timeout và giới hạn tài nguyên riêng; nếu fuzzing làm cạn tài nguyên môi trường test, cần dừng và điều tra thay vì tự động tăng giới hạn.

## 23. Lỗi thường gặp khi triển khai fuzzing và fail-closed tests

| Sai lầm | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Chỉ fuzz parser độc lập | Bỏ sót đường đi tới principal và side effect. | Kiểm thử end-to-end qua endpoint được bảo vệ. |
| Chỉ dùng token chữ ký sai | Không chứng minh issuer/audience/type policy hoạt động. | Thêm signed-valid policy-invalid fixtures. |
| Không có positive control | Test có thể luôn fail vì cấu hình sai. | Xác nhận token hợp lệ trước mutation. |
| Chỉ kiểm tra status code | Side effect có thể đã xảy ra trước khi response lỗi. | Quan sát principal, dữ liệu, database và event. |
| Dùng production issuer/key | Có nguy cơ lộ secret và gây nhiễu hệ thống thật. | Test issuer/key riêng, môi trường cô lập. |
| Fuzz không giới hạn | Chính harness có thể gây DoS. | Giới hạn CPU, memory, input size và thời gian. |
| Bắt exception rồi tiếp tục | Biến lỗi verifier thành fail-open. | Ánh xạ lỗi thành reject hoặc unavailable theo policy. |
| JWKS lỗi thì dùng key bất kỳ | Chấp nhận chữ ký không có trust anchor. | Chỉ dùng key đã xác minh và cache trong policy. |
| Replay store lỗi thì bỏ check | DPoP proof có thể bị replay. | Không chấp nhận proof khi replay check bắt buộc không thực hiện được. |
| Introspection timeout thì coi active | Token revoked/invalid có thể được chấp nhận. | Fail closed khi online status là điều kiện bắt buộc. |
| Không kiểm tra multi-instance | Instance khác có thể có policy/cache yếu hơn. | Chạy corpus và fault injection trên mọi đường xác minh. |
| Ghi raw token vào log | Log trở thành nơi rò rỉ credential. | Log reason code và correlation ID, không log secret. |
| Chỉ chạy fuzz một lần | Lỗi hiếm hoặc phụ thuộc seed không được tái hiện. | Lưu seed, corpus version và regression case. |

## 24. Quy trình xử lý khi fuzz tìm thấy lỗi

Khi fuzzing phát hiện crash, timeout, accept bất thường hoặc khác biệt giữa verifier:

1. Lưu seed tối thiểu tái hiện lỗi.
2. Loại bỏ credential hoặc dữ liệu nhạy cảm khỏi artifact.
3. Ghi lại phiên bản parser, thư viện, cấu hình profile và môi trường.
4. Xác định validation stage nơi lỗi xuất hiện.
5. Kiểm tra có principal, dữ liệu hoặc side effect nào đã được tạo không.
6. Tạo regression test cố định.
7. Sửa nguyên nhân gốc, không chỉ thêm điều kiện cho đúng một payload.
8. Chạy lại regression corpus và các invariant liên quan.
9. Đánh giá các phiên bản/instance khác có cùng lỗi không.
10. Nếu lỗi có thể dẫn tới token acceptance trái phép hoặc lộ dữ liệu, xử lý theo quy trình incident response.

Không đưa nguyên raw token, private key hoặc dữ liệu người dùng vào bug report công khai.

## 25. Checklist bảo đảm fail-closed

Trước khi kết luận hệ thống xác minh JWT có hành vi fail-closed, hãy xác nhận:

1. **Input bounds:** token, header, payload, JWKS và certificate chain có giới hạn kích thước/depth không?
2. **Parser:** malformed JSON, Base64URL và compact serialization có bị từ chối có kiểm soát không?
3. **JOSE:** alg, kid, typ, crit, jku, x5u và key type có policy rõ không?
4. **Signature:** mọi mutation header/payload/signature đều không thể vượt qua xác minh?
5. **Profile:** issuer, audience, required claims và token type được kiểm tra riêng?
6. **Key source:** JWKS/metadata lỗi có làm verifier bỏ qua chữ ký hoặc tin key ngoài registry không?
7. **Cache:** chỉ dùng key đã xác minh trong TTL/stale policy; emergency revoke có vượt cache không?
8. **Clock:** time source lỗi có khiến exp/nbf bị bỏ qua không?
9. **Revocation:** introspection/revocation unavailable có bị giả định là active không?
10. **Replay:** replay store hoặc nonce service lỗi có làm proof được chấp nhận không?
11. **Sender binding:** DPoP/mTLS proof hoặc certificate thiếu/sai có bị từ chối không?
12. **Authorization:** policy engine, tenant hoặc membership store lỗi có làm thao tác được phép không?
13. **Principal boundary:** principal chỉ được tạo sau validation hoàn chỉnh?
14. **Side effects:** credential lỗi không trả dữ liệu, cập nhật trạng thái hoặc gọi downstream?
15. **Error handling:** exception không bị bỏ qua hoặc fallback sang decode-only?
16. **Observability:** có reason code, metric và correlation ID nhưng không lộ raw credential?
17. **Resource limits:** fuzz và unknown-kid storm không làm cạn tài nguyên không kiểm soát?
18. **Distributed behavior:** mọi instance/region áp dụng cùng trust và fail-closed policy?
19. **Regression:** mỗi lỗi fuzz tìm được có seed và regression test?
20. **Operations:** có quy trình ứng phó khi key, metadata, replay store hoặc verifier bị compromise/lỗi?

## 26. Ghi nhớ trọng tâm

- Fuzzing tìm lỗi parser và validation bằng đầu vào biến thể; fault injection kiểm tra dependency failure; negative testing kiểm tra các trường hợp sai đã biết.
- Fail-closed nghĩa là thiếu bằng chứng bắt buộc thì không ALLOW. Không đồng nghĩa phải bỏ qua mọi cache tin cậy đã được xác minh và còn nằm trong policy.
- Với JWS, thay protected header, payload hoặc signature phải làm token không còn xác minh được bằng chữ ký cũ.
- Fuzz cả compact serialization, JSON, JOSE header, claims, JWS/JWE, JWKS, metadata và sender proof.
- Signed-valid policy-invalid fixtures cần thiết để kiểm tra issuer, audience, typ, required claims và thuật toán độc lập với signature failure.
- Giới hạn kích thước, CPU, memory, timeout, retry và JWKS refresh để chống DoS.
- Khi JWKS, clock, introspection, revocation, replay store hoặc certificate validation không khả dụng, không bỏ qua điều kiện bảo mật bắt buộc.
- Principal chỉ được tạo sau validation hoàn chỉnh; token lỗi không được gây side effect hoặc trả dữ liệu được bảo vệ.
- Kiểm thử nhiều instance/region và các trust boundary, không chỉ parser hoặc API Gateway.
- Lưu seed và regression test cho mọi lỗi đã phát hiện; không ghi raw token hoặc secret vào log.

**Tài liệu tham khảo kỹ thuật:** RFC 7515 (JSON Web Signature); RFC 7516 (JSON Web Encryption); RFC 7517 (JSON Web Key); RFC 7518 (JSON Web Algorithms); RFC 7519 (JSON Web Token); RFC 8725 (JSON Web Token Best Current Practices); RFC 6750 (Bearer Token Usage); RFC 7662 (OAuth 2.0 Token Introspection); RFC 9449 (OAuth 2.0 Demonstrating Proof of Possession); RFC 8705 (OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens). Các chuẩn này định nghĩa token, JOSE và các cơ chế liên quan; fuzzing strategy, resource bounds, fault policy và fail-closed invariants cần được cụ thể hóa theo hệ thống triển khai.
