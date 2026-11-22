# Algorithm confusion giữa HMAC và RSA

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Tấn công JWT  
> **Phạm vi:** Phân tích tấn công algorithm confusion trong JWS/JWT, đặc biệt là nhầm lẫn giữa RS256 và HS256; tập trung vào mô hình khóa, lỗi xác minh và biện pháp phòng vệ ở mức giao thức, không phụ thuộc Java, Spring hay framework cụ thể.

Algorithm confusion là lỗi xảy ra khi verifier để thuật toán do token tự khai báo làm thay đổi cách diễn giải khóa hoặc cơ chế xác minh ngoài chính sách tin cậy. Trường hợp kinh điển là **RS256 → HS256**: hệ thống dự kiến xác minh chữ ký RSA bằng public key, nhưng lại chấp nhận HS256 và dùng chính dữ liệu public key RSA như một HMAC secret.

Public key RSA vốn được công bố để mọi verifier có thể kiểm tra chữ ký. Nếu verifier dùng các byte public key đó làm bí mật HMAC, attacker biết public key cũng có thể tự tính MAC cho token giả. Chữ ký RSA không bị phá; lỗi nằm ở nhánh xác minh của ứng dụng.

Quy tắc phòng vệ quan trọng nhất: **verifier phải chọn thuật toán từ cấu hình tin cậy gắn với issuer, endpoint và token profile; đồng thời ràng buộc thuật toán với đúng loại khóa.** Giá trị alg trong protected header là dữ liệu do người gửi kiểm soát và chưa đáng tin trước khi xác minh.

## 1. RS256 và HS256 khác nhau ở đâu?

### 1.1. RS256: private key ký, public key xác minh

RS256 là JWS sử dụng RSASSA-PKCS1-v1_5 với SHA-256:

- Issuer giữ RSA private key và dùng nó để ký.
- Resource server giữ RSA public key và dùng nó để xác minh.
- Public key có thể được phân phối qua JWKS.
- Người chỉ có public key không thể tạo chữ ký RSA hợp lệ nếu thuật toán và khóa được sử dụng đúng.

Ví dụ header của token được issuer ký bằng RS256:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-signing-2026-01",
  "typ": "JWT"
}
~~~

### 1.2. HS256: cùng một secret để ký và xác minh

HS256 là HMAC với SHA-256:

- Issuer và verifier cùng giữ một secret.
- Issuer dùng secret để tạo MAC.
- Verifier dùng cùng secret để tính lại MAC và so sánh.
- Bất kỳ bên nào giữ secret đều có thể tạo token có MAC hợp lệ.

Ví dụ header:

~~~json
{
  "alg": "HS256",
  "typ": "JWT"
}
~~~

Theo RFC 7518, khóa HMAC dùng HS256 phải có ít nhất 256 bit. Secret phải được sinh ngẫu nhiên mật mã; một chuỗi dài nhưng dễ đoán không trở thành secret mạnh.

### 1.3. So sánh loại khóa

| Thuộc tính | RS256 | HS256 |
|---|---|---|
| Cơ chế | Chữ ký bất đối xứng | MAC đối xứng |
| Khóa tạo chữ ký/MAC | RSA private key | HMAC secret |
| Khóa xác minh | RSA public key | Chính HMAC secret |
| Public key có thể công khai? | Có | Không áp dụng; secret phải giữ kín |
| Verifier chỉ có khóa xác minh có thể tự phát hành token? | Không | Có, vì verifier phải giữ secret |
| JWK kty tương ứng | RSA | oct |

Hai thuật toán đều là JWS algorithms nhưng không thể dùng cùng một loại key material. RSA public key không phải HMAC secret.

## 2. Algorithm confusion là gì?

### 2.1. Verifier mong đợi một thuật toán nhưng lại tin header

Một triển khai dễ mắc lỗi có thể làm theo trình tự:

1. Đọc header JWT.
2. Lấy giá trị alg từ header.
3. Chọn thuật toán theo giá trị đó.
4. Truyền cùng một biến key vào hàm xác minh tổng quát.
5. Không kiểm tra loại khóa có phù hợp với thuật toán hay không.

Nếu hệ thống dự kiến dùng RSA nhưng đồng thời bật HMAC trên cùng đường xác minh, header có thể khiến verifier chuyển sang nhánh HMAC. Nếu key được truyền vào nhánh này dưới dạng byte string của RSA public key, public key có thể bị diễn giải thành HMAC secret.

### 2.2. Điều kiện cần để khai thác

Tấn công RS256 → HS256 thường cần kết hợp nhiều điều kiện:

- Verifier chấp nhận HS256 ở endpoint vốn dành cho token RS256.
- Thuật toán được chọn theo header do attacker kiểm soát, hoặc header có thể làm thay đổi lựa chọn thuật toán.
- Key được truyền vào thư viện/API xác minh ở dạng có thể bị diễn giải như HMAC secret.
- Attacker biết hoặc lấy được đúng biểu diễn byte của public key mà verifier dùng làm đầu vào HMAC.
- Verifier không ràng buộc loại khóa và thuật toán trước khi xác minh.

Không phải mọi thư viện JWT đều dễ bị khai thác. Một thư viện có kiểu khóa rõ ràng, validator gắn thuật toán cố định và kiểm tra tương thích key/alg có thể từ chối tổ hợp sai. Khả năng khai thác phụ thuộc API, phiên bản thư viện, cách nạp khóa và cấu hình ứng dụng.

### 2.3. Public key không cần bị đánh cắp

Public key RSA thường được công bố qua JWKS hoặc tài liệu cấu hình. Attacker có thể lấy public key từ nguồn công khai hoặc từ chính hệ thống cung cấp khóa.

Nếu verifier dùng đúng byte public key đó làm HMAC secret, tính công khai của public key khiến attacker có đủ dữ liệu để tính MAC. Đây không phải là việc đoán private key RSA.

## 3. Chuỗi tấn công RS256 → HS256

### 3.1. Trạng thái bình thường

Giả sử hệ thống có:

- Authorization server ký access token bằng RS256.
- JWKS công bố RSA public key tương ứng.
- Orders API dùng public key để xác minh chữ ký.
- Payload chứa issuer, audience, subject, thời hạn và scope.

Luồng đúng:

~~~mermaid
flowchart LR
    A[Issuer giữ RSA private key] -->|Ký RS256| B[JWT hợp lệ]
    B --> C[Orders API]
    D[JWKS tin cậy chứa RSA public key] --> C
    C --> E[Xác minh RS256]
    E --> F[Kiểm tra claims và quyền]
~~~

### 3.2. Tạo token giả theo nhánh HMAC

Trong cấu hình dễ bị tấn công:

1. Attacker lấy một token mẫu hoặc tạo header/payload theo cấu trúc endpoint chấp nhận.
2. Attacker thay alg trong protected header từ RS256 thành HS256.
3. Attacker tạo lại signing input từ header và payload đã thay đổi.
4. Attacker tính HMAC-SHA-256 bằng byte biểu diễn RSA public key mà verifier dùng nhầm làm secret.
5. Attacker gửi JWT mới tới API.
6. Verifier đọc HS256, chọn nhánh HMAC và sử dụng cùng byte public key làm secret.
7. Nếu các điều kiện khác cũng đạt, verifier có thể chấp nhận MAC giả.

Khi thay header, attacker phải tính lại MAC trên signing input mới. Không thể chỉ sửa chuỗi alg rồi giữ nguyên chữ ký RS256 cũ.

### 3.3. Sơ đồ nhầm lẫn

~~~mermaid
flowchart TD
    A[Verifier được thiết kế dùng RS256] --> B[Đọc RSA public key từ nguồn tin cậy]
    C[Attacker biết RSA public key] --> D[Tạo JWT giả, khai alg = HS256]
    D --> E[Tính HMAC bằng byte RSA public key]
    E --> F[Gửi JWT giả]
    B --> G{Verifier có ràng buộc alg với key type?}
    F --> G
    G -->|Không| H[Diễn giải RSA public key như HMAC secret]
    H --> I[MAC có thể được xác minh]
    G -->|Có| J[Từ chối HS256 hoặc key type mismatch]
~~~

Đây là mô hình lỗi khái niệm. Cách biểu diễn public key mà attacker phải dùng phải trùng với dữ liệu verifier truyền vào HMAC. Một thư viện có thể parse PEM thành key object, chuẩn hóa DER hoặc áp dụng type checking; vì vậy không được giả định mọi cách lưu public key đều tạo ra cùng kết quả khai thác.

### 3.4. Những claim nào có thể bị giả mạo?

Nếu attacker tạo được MAC hợp lệ trong nhánh xác minh sai, attacker có thể tự chọn payload, ví dụ:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "administrator",
  "aud": "https://api.orders.example.com",
  "iat": 1794800000,
  "exp": 1794803600,
  "scope": "orders:read orders:write"
}
~~~

Đây chỉ là payload minh họa, không phải token thật. Việc token giả được chấp nhận còn phụ thuộc verifier kiểm tra issuer, audience, thời hạn, token type, scope và các điều kiện khác ra sao. Nếu các kiểm tra claim được thực hiện đúng, chúng có thể giới hạn một số request nhưng không sửa được lỗi xác minh chữ ký/MAC.

## 4. Vì sao đây không phải là phá RSA?

### 4.1. Khóa RSA vẫn an toàn

Attacker không:

- Tính được RSA private key từ public key.
- Phá thuật toán RSASSA-PKCS1-v1_5.
- Tìm va chạm SHA-256 để giả chữ ký RS256.
- Tạo chữ ký RSA hợp lệ theo thuật toán RS256.

Thay vào đó, attacker khai thác việc verifier tự chuyển sang một thuật toán khác và diễn giải public key như secret HMAC. HMAC được tính đúng theo thuật toán HS256; sai lầm là hệ thống đã dùng một giá trị công khai làm secret.

### 4.2. Chữ ký và MAC có semantics khác nhau

Với chữ ký RSA, chỉ private key holder mới có quyền ký; public key holder chỉ xác minh. Với HMAC, mọi bên có secret đều có quyền tạo MAC.

Khi verifier nhầm hai mô hình, nó vô tình trao quyền phát hành token cho bất kỳ ai biết public key. Đây là sự thay đổi ranh giới tin cậy nghiêm trọng.

### 4.3. Phân biệt algorithm confusion và algorithm downgrade

| Khái niệm | Bản chất |
|---|---|
| Algorithm confusion | Một key hoặc key representation bị diễn giải theo thuật toán/loại khóa khác, ví dụ RSA public key bị dùng như HMAC secret |
| Algorithm downgrade | Verifier bị khiến chấp nhận thuật toán yếu hơn hoặc không còn được phép, trái với policy |
| Unsecured JWT acceptance | Verifier chấp nhận token không có chữ ký/MAC, thường liên quan alg none |

Các lỗi có thể xuất hiện cùng nhau, nhưng cần phân biệt để thiết kế test và biện pháp phòng vệ đúng.

## 5. Các biến thể và điều kiện cấu hình dễ mắc lỗi

### 5.1. Cho phép cả HS256 và RS256 trên cùng validator

Nếu một endpoint không có lý do rõ ràng để nhận cả HMAC và RSA, allowlist hỗn hợp làm tăng nguy cơ nhầm lẫn. Một cấu hình tổng quát cho mọi token có thể vô tình chấp nhận thuật toán không thuộc profile của endpoint.

### 5.2. Truyền key dạng chuỗi hoặc byte tổng quát

Một API xác minh có thể nhận một tham số key dạng chuỗi/byte và quyết định cách dùng dựa trên alg. Nếu ứng dụng truyền PEM public key vào API mà không kiểm tra loại khóa, cùng một dữ liệu có thể bị diễn giải theo nhánh HMAC.

Nên dùng key object có loại rõ ràng và API xác minh gắn với thuật toán đã cấu hình. Tuy vậy, chỉ dùng key object không đủ nếu validator vẫn cho phép thuật toán sai hoặc thư viện có hành vi không an toàn.

### 5.3. Lấy thuật toán từ token thay vì contract

Header alg được bảo vệ bởi chữ ký sau khi xác minh, nhưng trước khi xác minh nó là dữ liệu do attacker kiểm soát. Không thể dùng chữ ký chưa được xác minh làm căn cứ tin thuật toán được khai báo.

Verifier phải biết trước endpoint đang nhận profile nào, issuer nào và thuật toán nào được phép. Header chỉ được dùng như một giá trị để đối chiếu với policy.

### 5.4. Dùng một key set cho nhiều issuer hoặc nhiều profile

Không tra cứu khóa chỉ theo kid trên một kho khóa toàn cục. Hai issuer có thể trùng kid. Một endpoint cũng không nên dùng cùng key set/validator cho ID token, access token và token nghiệp vụ nếu profile có semantics khác nhau.

### 5.5. Fallback khi xác minh thất bại

Một số logic sai thử lần lượt nhiều thuật toán hoặc loại khóa cho tới khi một cách xác minh thành công. Đây là hành vi nguy hiểm:

- Không thử HMAC sau khi RSA thất bại.
- Không thử RSA sau khi HMAC thất bại.
- Không chuyển sang alg khác chỉ vì key resolver trả lỗi.
- Không chấp nhận token không chữ ký như phương án dự phòng.

Một token không khớp contract phải bị từ chối.

## 6. Phòng vệ ở verifier

### 6.1. Cấu hình allowlist cố định

Nếu contract dùng RS256, verifier chỉ cho phép RS256 cho contract đó. Nếu dùng PS256, chỉ cho phép PS256. Không chấp nhận HS256 chỉ vì thư viện hỗ trợ HMAC.

Ví dụ cấu hình khái niệm:

~~~yaml
contract:
  id: orders-access-v1
  issuer: "https://id.example.com"
  audience: "https://api.orders.example.com"
  token_profile: oauth2-jwt-access
  allowed_jws_algorithms:
    - RS256
  key_source:
    type: trusted_jwks
    issuer_bound: true
  expected_key:
    kty: RSA
    use: sig
    operation: verify
~~~

Đây là cấu hình minh họa, không phải schema chuẩn. Giá trị thuật toán phải khớp profile và chính sách mật mã của hệ thống.

### 6.2. Ràng buộc loại khóa với thuật toán

| Thuật toán | JWK kty mong đợi | Vai trò khóa xác minh |
|---|---|---|
| HS256 | oct | Secret đối xứng |
| RS256 | RSA | RSA public key |
| PS256 | RSA | RSA public key |
| ES256 | EC | EC public key trên curve tương ứng |
| EdDSA | OKP | Public key/curve được JWA hỗ trợ |

Với contract RS256:

- Từ chối khóa JWK có kty là oct.
- Từ chối token khai HS256.
- Không chuyển RSA public key thành byte secret.
- Chỉ dùng public key từ JWKS của issuer đã cấu hình.

Với HMAC, secret phải được quản lý riêng và không công bố trong JWKS công khai. Không dùng public key làm nguồn sinh secret.

### 6.3. Ràng buộc metadata JWK

Khi nguồn khóa là JWKS, kiểm tra:

- **kty:** đúng họ khóa.
- **alg:** nếu có, phải tương thích với allowlist và contract.
- **use:** phải là sig cho khóa xác minh chữ ký.
- **key_ops:** phải cho phép verify theo mục đích sử dụng.
- **kid:** chỉ dùng chọn khóa trong JWKS đã gắn với issuer.
- **crv:** phải khớp thuật toán nếu dùng EC/OKP.
- Các tham số khóa phải hợp lệ và đáp ứng yêu cầu chất lượng.

Trường alg trong JWK có thể không xuất hiện; sự vắng mặt không cho phép verifier tự suy ra rằng khóa dùng được với mọi thuật toán. Chính sách tin cậy vẫn đến từ contract.

### 6.4. Chọn issuer và nguồn khóa từ cấu hình tin cậy

Quy trình an toàn:

1. Endpoint xác định contract được phép nhận.
2. Contract xác định issuer chính xác và JWKS URI đã tin cậy.
3. Parse header chưa tin cậy và đối chiếu alg với allowlist.
4. Dùng kid để tìm ứng viên trong đúng JWKS của issuer.
5. Kiểm tra key type, algorithm binding và key purpose.
6. Xác minh bằng đúng thuật toán đã cấu hình.
7. Sau khi chữ ký hợp lệ mới tin claims và tiếp tục kiểm tra issuer, audience, type, thời gian và quyền.

Không tải khóa từ jku/x5u do token tự cung cấp nếu contract không có cơ chế trust rõ ràng. Không dùng kid để chọn issuer hoặc URL tải khóa.

### 6.5. Tách validator theo profile

Nếu hệ thống nhận nhiều loại JWT:

- Dùng validator riêng cho access token, ID token và token nghiệp vụ.
- Mỗi validator có issuer, audience, typ, thuật toán và claims bắt buộc riêng.
- Không cho ID token được dùng thay access token.
- Không cho một token profile kế thừa allowlist thuật toán quá rộng từ profile khác.
- Dùng token type và audience để chống cross-JWT confusion.

Tách profile giúp giảm khả năng một token hợp lệ trong ngữ cảnh này bị sử dụng ở ngữ cảnh khác.

## 7. Pseudocode xác minh an toàn

### 7.1. Cách làm không an toàn

~~~text
header = decodeHeaderWithoutVerification(token)
algorithm = header.alg
key = loadGenericKey()

verify(token, key, algorithm)
~~~

Vấn đề:

- Algorithm do token quyết định.
- Key không gắn với issuer/profile/algorithm.
- Hàm verify có thể diễn giải cùng key theo nhiều cơ chế.
- Không có kiểm tra key type và purpose.

### 7.2. Cách làm an toàn

~~~text
verifyAccessToken(endpoint, token):
    contract = trustedContracts.forEndpoint(endpoint)
    reject nếu contract không tồn tại

    header = parseProtectedHeaderAsUntrusted(token)
    reject nếu header.alg không nằm trong contract.allowedAlgorithms
    reject nếu header.typ/profile không phù hợp

    key = trustedJwks(contract.issuer).findCandidate(header.kid)
    reject nếu key không tồn tại
    reject nếu key.kty không phù hợp với contract algorithm
    reject nếu key.use/key_ops/curve/parameters không hợp lệ

    verifyUsingExactly(contract.algorithm, key)
    reject nếu chữ ký không hợp lệ

    claims = parseVerifiedClaims(token)
    validateExactIssuer(claims.iss, contract.issuer)
    validateAudience(claims.aud, contract.audience)
    validateTokenType(claims, header, contract)
    validateTimeAndRequiredClaims(claims, contract)
    authorizeScopeAndResource(claims, endpoint)
    ACCEPT
~~~

Pseudocode mô tả thứ tự và ranh giới tin cậy, không phải API của thư viện cụ thể. Thực tế cần dùng thư viện JOSE/JWT được duy trì và cấu hình kiểm tra thuật toán rõ ràng.

## 8. Ví dụ kiểm thử trong môi trường cô lập

Mục tiêu của kiểm thử là chứng minh validator từ chối token khai báo HS256 khi contract chỉ chấp nhận RS256, kể cả khi test harness có public key RSA hợp lệ.

### 8.1. Chuẩn bị test fixture

Tạo một key pair RSA giả lập riêng cho test:

- Private key chỉ dùng để tạo token RS256 hợp lệ.
- Public key được dùng trong cấu hình verifier test.
- Không dùng khóa production hoặc secret thật.
- Dùng issuer, audience, subject và scope giả lập.

### 8.2. Ca kiểm thử dương tính

1. Issuer test ký JWT bằng RSA private key và alg RS256.
2. Verifier được cấu hình chỉ chấp nhận RS256.
3. Public key RSA tương ứng được nạp từ JWKS test tin cậy.
4. Token có issuer, audience, thời hạn và scope đúng.
5. Kết quả mong đợi: xác minh chữ ký thành công, sau đó tiếp tục authorization.

### 8.3. Ca kiểm thử âm tính RS256 → HS256

1. Lấy public key test đã công bố.
2. Tạo một token test mới có header khai HS256.
3. Tạo MAC test trên signing input đã thay đổi bằng một giá trị public-key representation để mô phỏng nhánh nhầm lẫn.
4. Gửi token tới verifier chỉ cho phép RS256.
5. Kết quả bắt buộc: từ chối ngay vì HS256 ngoài allowlist; không được diễn giải RSA public key như HMAC secret.

Chỉ chạy trong môi trường kiểm thử do tổ chức kiểm soát. Mục tiêu là xác nhận validator không có nhánh xác minh sai, không thử trên hệ thống bên thứ ba.

### 8.4. Kiểm thử không chỉ dựa trên response cuối

Ngoài kết quả HTTP, quan sát:

- Validator đã từ chối ở bước allowlist hay chưa.
- Có nhánh HMAC nào được gọi khi contract là RS256 không.
- Key resolver có trả key object loại RSA hay byte string tổng quát.
- Có fallback algorithm nào chạy sau lỗi không.
- Log có ghi token, signature hoặc private key hay không.

Một test chỉ nhận HTTP 401 chưa chứng minh lỗi đã được sửa đúng nếu code vẫn chạy nhánh HMAC rồi tình cờ từ chối ở bước khác.

## 9. Ma trận kiểm thử chống algorithm confusion

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| J01 | RS256 đúng issuer, RSA public key và audience | Chấp nhận sau các kiểm tra khác |
| J02 | HS256 gửi tới endpoint chỉ cho RS256 | Từ chối tại algorithm allowlist |
| J03 | HS256 dùng byte public key RSA làm secret | Từ chối; không có nhánh diễn giải khóa sai |
| J04 | Token khai PS256 trong contract chỉ cho RS256 | Từ chối |
| J05 | Token dùng alg none | Từ chối |
| J06 | RSA key được đưa vào validator HMAC | Từ chối do sai loại khóa |
| J07 | JWK kty=oct trong contract RSA | Từ chối |
| J08 | JWK kty=RSA trong contract HMAC | Từ chối |
| J09 | JWK alg không khớp contract | Từ chối |
| J10 | JWK use=enc được dùng xác minh chữ ký | Từ chối |
| J11 | key_ops không cho verify | Từ chối |
| J12 | kid trùng giữa hai issuer | Chỉ tìm trong JWKS của issuer đã cấu hình |
| J13 | kid không tồn tại | Từ chối sau refresh JWKS có giới hạn |
| J14 | Token khai jku/x5u trỏ tới nguồn khóa tùy ý | Không tải hoặc tin nguồn ngoài contract |
| J15 | Chữ ký thất bại | Từ chối; không fallback sang thuật toán khác |
| J16 | ID token gửi tới resource API | Từ chối do sai token profile/audience |
| J17 | Token có chữ ký hợp lệ nhưng sai issuer | Từ chối |
| J18 | Token có chữ ký hợp lệ nhưng sai audience | Từ chối |

## 10. Phát hiện và ứng phó khi có dấu hiệu bị khai thác

### 10.1. Dấu hiệu cần điều tra

- Token có alg khác với thuật toán contract dự kiến.
- Một endpoint RS256 đột nhiên nhận nhiều token HS256.
- Lỗi key type mismatch hoặc thuật toán không nằm trong allowlist tăng bất thường.
- Token có claim quyền cao bất thường nhưng không có issuance record tương ứng.
- Cùng issuer/key có token với profile, audience hoặc subject không phù hợp.
- Verifier có dấu hiệu xác minh bằng một key representation không đúng loại.

Các dấu hiệu này chưa tự chứng minh đã khai thác thành công; cần đối chiếu log issuer, verifier, key resolver và request đã được chấp nhận.

### 10.2. Ứng phó

Nếu xác nhận hoặc nghi ngờ attacker đã tạo token giả bằng lỗi confusion:

1. Tắt ngay thuật toán ngoài allowlist ở verifier và triển khai cấu hình cố định.
2. Cô lập hoặc nâng cấp thư viện/API xác minh có hành vi diễn giải khóa không an toàn.
3. Xác định issuer, endpoint, key set và profile có dùng validator lỗi.
4. Tìm token/request bất thường và hành động đã được chấp nhận.
5. Nếu có khả năng attacker truy cập private key hoặc secret thật, xử lý thêm như sự cố compromise khóa.
6. Thu hồi session/grant/token và thay khóa khi bằng chứng cho thấy cần thiết.
7. Kiểm thử lại toàn bộ ma trận âm tính trước khi mở lưu lượng.

Trong tấn công RS256 → HS256 cổ điển, attacker có thể chỉ cần public key. Điều đó không tự động có nghĩa RSA private key bị lộ; không thay khóa chỉ dựa trên giả định sai này. Tuy nhiên, nếu issuer signing service hoặc private key có dấu hiệu bị truy cập, phải kích hoạt quy trình ứng phó compromise khóa riêng.

## 11. Những sai lầm phòng vệ thường gặp

| Sai lầm | Vì sao chưa đủ | Cách đúng |
|---|---|---|
| Chỉ kiểm tra chữ ký có hợp lệ | Nhánh HMAC sai vẫn có thể trả về hợp lệ | Cố định thuật toán và key type trước verify |
| Chỉ tin alg trong header | Header do attacker kiểm soát trước xác minh | Đối chiếu với allowlist của contract |
| Cho phép HS256 và RS256 trên cùng validator “cho tiện” | Mở nhánh diễn giải khóa không cần thiết | Tách validator/profile và key set |
| Dùng RSA public key làm HMAC secret | Public key không phải bí mật | Dùng đúng loại key và thuật toán |
| Chỉ kiểm tra kty từ token header | JWS header không phải JWK trust source | Kiểm tra key từ JWKS tin cậy và contract |
| Tin alg trong JWK nếu có | Metadata không thay thế trust policy | Contract vẫn quyết định allowlist |
| Chỉ từ chối none | Không ngăn nhầm lẫn HS256/RS256 | Ràng buộc đầy đủ algorithm/key |
| Thử thuật toán khác khi verify lỗi | Tạo fallback attack surface | Chỉ dùng một thuật toán đã cấu hình |
| Chỉ dựa vào HTTP 401 trong test | Không biết validator đã đi qua nhánh sai nào | Kiểm tra decision path và instrumentation |
| Cho mọi profile dùng chung một key resolver | Dễ lẫn issuer, audience và token purpose | Namespace theo issuer/profile/endpoint |

## 12. Checklist phòng chống Algorithm Confusion

**Chính sách thuật toán**

- [ ] Mỗi endpoint/profile có allowlist thuật toán rõ ràng.
- [ ] RS256 contract không chấp nhận HS256.
- [ ] Không chấp nhận none hoặc thuật toán ngoài allowlist.
- [ ] Không chọn thuật toán chỉ từ header chưa xác minh.
- [ ] Không fallback giữa các họ thuật toán.

**Khóa và nguồn khóa**

- [ ] RS256 dùng RSA public key; HS256 dùng secret đối xứng đủ mạnh.
- [ ] Không dùng RSA public key làm HMAC secret.
- [ ] JWK kty, alg, use, key_ops và curve/parameters phù hợp.
- [ ] kid chỉ tra cứu trong JWKS của issuer đã cấu hình.
- [ ] Không tin jku/x5u tùy ý trong token.
- [ ] Private key và HMAC secret được quản lý theo đúng mục đích.

**Validator và profile**

- [ ] Dùng thư viện JOSE/JWT được duy trì và API xác minh có ràng buộc thuật toán.
- [ ] Tách validator cho access token, ID token và token nghiệp vụ.
- [ ] Kiểm tra issuer, audience, typ, thời hạn và claims sau xác minh mật mã.
- [ ] Không dùng dữ liệu claims chưa xác minh để chọn trust domain.

**Kiểm thử và vận hành**

- [ ] Có test RS256 hợp lệ và HS256 giả mạo bằng public-key bytes.
- [ ] Có test sai kty, alg, use, key_ops, kid và issuer.
- [ ] Có test xác minh thất bại không fallback thuật toán.
- [ ] Có log mã lỗi/decision path mà không ghi raw token hoặc secret.
- [ ] Có playbook khi phát hiện token giả đã được chấp nhận.

**Điều cần nhớ:** Algorithm confusion giữa HMAC và RSA xảy ra khi verifier để token thay đổi thuật toán xác minh và dùng một key representation sai mục đích. Với lỗi RS256 → HS256, public RSA key có thể bị dùng nhầm như HMAC secret nếu validator chấp nhận cả hai thuật toán và không kiểm tra loại khóa. Cách phòng vệ là cố định thuật toán theo contract, ràng buộc chặt thuật toán với key type, chọn khóa từ issuer tin cậy và từ chối mọi fallback.

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): Signing input, protected header và JWS algorithms.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK parameters như kty, alg, use, key_ops và kid.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): HS256 và RS256; yêu cầu khóa và thuật toán.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Algorithm verification, issuer/audience validation và chống cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Ví dụ profile access token và yêu cầu xác minh.
- [PortSwigger Web Security Academy — JWT attacks](https://portswigger.net/web-security/jwt): Tổng quan các lớp tấn công JWT, gồm algorithm confusion.
