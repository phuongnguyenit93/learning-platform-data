# Verification key: khóa xác minh chữ ký số và cách thiết lập niềm tin

## 1. Vì sao cần verification key?

Giả sử một dịch vụ Java nhận **thông báo thanh toán** có chữ ký số. Dịch vụ gọi hàm xác minh chữ ký và nhận kết quả **true**. Điều đó có đủ để kết luận thông báo do đúng nhà cung cấp thanh toán gửi hay không?

**Chưa đủ.** Phép kiểm tra chữ ký chỉ trả lời rằng **chữ ký phù hợp với thông điệp và khóa xác minh được cung cấp**. Nếu kẻ tấn công có thể đưa chính **verification key giả** của mình vào hệ thống rồi ký một thông báo bằng private key tương ứng, phép xác minh cũng có thể trả true. Thuật toán không bị phá; lỗi nằm ở **nguồn gốc và quyền được tin cậy của khóa xác minh**.

**Verification key (khóa xác minh)** là khóa được sử dụng để **kiểm tra chữ ký số**. Trong các hệ thống chữ ký số bất đối xứng như **Ed25519, ECDSA hoặc RSA-PSS**, verification key thường là **public key** tương ứng với **private signing key** của bên ký. Public key có thể chia sẻ, nhưng hệ thống phải chứng minh nó thực sự thuộc **đúng danh tính và đúng mục đích**.

~~~text
Bên phát hành:
    Message + private signing key ──Sign──> Signature

Bên nhận:
    Message + signature + trusted verification key
              └──────── Verify ────────> true / false

Nếu dùng verification key do kẻ tấn công thay thế:
    Verify có thể true, nhưng danh tính bên ký không đáng tin.
~~~

Bài học nằm trong chương **Chữ ký số** của module quản lý khóa. Nó kết nối thuật toán chữ ký với **PKI/chứng chỉ, JWKS, KMS/HSM, phân quyền, rotation, thu hồi, kiểm toán và ứng phó sự cố**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt verification key, signing key, public key, private key, certificate và HMAC key.
2. Giải thích **Verify = true** chứng minh điều gì và không chứng minh điều gì.
3. Chọn và xác thực verification key qua trust store, chứng chỉ số, cấu hình tin cậy hoặc JWKS.
4. Kiểm tra **thuật toán, key usage, danh tính issuer, phiên bản, phạm vi cho phép** trước khi tin chữ ký.
5. Thiết kế vòng đời verification key: đăng ký, phân phối, sử dụng, rotation, thu hồi, lưu giữ lịch sử và hủy.
6. Dùng API chữ ký của Java 17 để xác minh Ed25519 với public key đúng định dạng.
7. Nhận biết rủi ro giả mạo khóa, algorithm confusion, cache khóa cũ, replay và lạm dụng quyền ký trong KMS/HSM.

## 2. Verification key là gì? Phân biệt các vai trò khóa

### 2.1. Signing key và verification key

Trong chữ ký số bất đối xứng, **signing key** thường là **private key**; **verification key** là **public key tương ứng**.

| Tiêu chí | Signing key | Verification key |
| --- | --- | --- |
| Vai trò | Tạo chữ ký trên thông điệp | Kiểm tra chữ ký trên thông điệp |
| Bí mật? | **Có**, phải bảo vệ | Thông thường **không**, có thể phân phối |
| Người được phép sử dụng | Chỉ workload/người có quyền ký cụ thể | Các bên được phép xác minh |
| Rủi ro chính | Lộ hoặc bị lạm dụng để ký thông điệp giả | Bị tráo, gắn sai danh tính, cấp quyền tin cậy quá rộng hoặc không thu hồi |
| Nơi lưu thường gặp | KMS/HSM, kho khóa riêng được bảo vệ | Trust store, chứng chỉ X.509, JWKS, cấu hình public key |
| Vòng đời | Sinh, cấp quyền ký, rotation, vô hiệu hóa, hủy | Đăng ký danh tính, công bố, cập nhật, thu hồi niềm tin, giữ lịch sử |

Một cặp khóa có quan hệ toán học: chữ ký tạo bằng private key được kiểm tra bởi public key tương ứng. Trong thuật toán hiện đại được triển khai đúng, từ public key không thể thực tế suy ra private key bằng các kỹ thuật thông thường.

**Đặc biệt:** việc public key không bí mật **không có nghĩa nội dung của trust store được phép sửa tự do**. Nếu kẻ tấn công thay public key mà ứng dụng dùng để xác minh, hắn có thể thay đổi bên mà ứng dụng coi là “đã ký hợp lệ”.

### 2.2. Verification key có luôn là public key?

Trong phạm vi **digital signature bất đối xứng**, có. Nhưng khái niệm “khóa dùng để verify” đôi khi được dùng rộng cho các cơ chế khác:

- **HMAC/MAC:** người kiểm tra phải có **khóa bí mật đối xứng** giống bên tạo MAC, trừ khi một dịch vụ quản lý khóa cung cấp API VerifyMac tách quyền mà không tiết lộ vật liệu khóa. Đây là **MAC verification**, không phải public-key digital signature.
- **Ed25519, ECDSA, RSA-PSS:** người kiểm tra dùng **public verification key**, có thể công bố; người tạo chữ ký dùng private signing key.
- **Hash thường (SHA-256):** không có khóa xác minh. Người kiểm tra chỉ đối chiếu digest, phải có **digest tham chiếu đáng tin** nếu muốn chống sửa đổi có chủ đích.
- **AES-GCM:** dùng cùng khóa đối xứng bí mật để mã hóa và giải mã, kiểm tra authentication tag theo AEAD; không phải chữ ký số.

Vì thế, khi nghe “verification key”, cần hỏi ngay: **xác minh chữ ký số bất đối xứng, MAC hay authentication tag?** Bài này tập trung vào **verification key của chữ ký số**.

### 2.3. Public key, certificate và key ID không đồng nghĩa

| Khái niệm | Bản chất | Giới hạn |
| --- | --- | --- |
| **Verification key** | Public key dùng với thuật toán Verify được cho phép | Không tự chứng minh khóa thuộc ai |
| **X.509 certificate** | Chứa public key và metadata được bên phát hành ký | Phải kiểm tra chain, danh tính, thời hạn, key usage, chính sách |
| **Trust anchor** | Điểm tin cậy gốc được cấu hình trước | Phải được phân phối và thay đổi qua quy trình an toàn |
| **Key ID / kid** | Định danh để tìm khóa trong tập đã biết | Không phải bằng chứng quyền sở hữu hay chữ ký |
| **Key fingerprint** | Digest của public key/cấu trúc khóa theo định dạng xác định | Chỉ hữu ích nếu fingerprint tham chiếu lấy từ nguồn đáng tin |
| **JWKS** | Tập public keys theo định dạng JSON Web Key Set | URL, nội dung, cache và issuer phải được xác thực theo chính sách |

Một **verification key là dữ liệu toán học**. Chứng chỉ, trust store và quy trình đăng ký khóa mới cung cấp **bối cảnh để quyết định có tin khóa đó hay không**.

## 3. Verify thực sự kiểm tra điều gì?

Một hàm Verify có thể được mô tả khái niệm:

~~~text
Verify(verificationKey, messageBytes, signatureBytes) -> true | false
~~~

Các tham số có ý nghĩa rất cụ thể:

- **verificationKey:** đúng public key của thuật toán chữ ký được cấu hình.
- **messageBytes:** chính xác những byte bên ký đã ký, hoặc đầu vào theo lược đồ ký được đặc tả.
- **signatureBytes:** chữ ký được tạo bằng thuật toán tương ứng.
- **Thuật toán và tham số:** Ed25519, ECDSA, RSA-PSS, định dạng signature, hash và các tham số liên quan nếu có.

Kết quả **true** chứng minh tính phù hợp mật mã giữa **message, signature và key** trong giả định thuật toán an toàn và triển khai đúng. Để kết luận “nhà phát hành A đã ký”, hệ thống còn cần xác thực **khóa đó được ủy quyền cho nhà phát hành A**.

### 3.1. Những điều Verify không tự chứng minh

1. **Không chứng minh danh tính nếu khóa chưa được xác thực.** Bất kỳ ai cũng có thể tự sinh một cặp khóa và tạo chữ ký hợp lệ theo cặp đó.
2. **Không chứng minh thông điệp còn mới.** Bản tin và chữ ký cũ có thể được phát lại nguyên vẹn.
3. **Không chứng minh người ký có quyền với hành động nghiệp vụ.** Một service có signing key có thể ký nhầm nội dung không được phê duyệt.
4. **Không bảo đảm bí mật nội dung.** Người nhận và bên thứ ba vẫn đọc được thông điệp nếu không có mã hóa riêng.
5. **Không chứng minh một con người cụ thể đã chủ động đồng ý.** Private key có thể được dùng tự động, bị lộ hoặc bị lạm dụng bởi workload có quyền ký.
6. **Không tự chứng minh chữ ký hợp lệ tại thời điểm lịch sử.** Cần quy tắc thời gian, tình trạng thu hồi và bằng chứng thời điểm ký phù hợp.
7. **Không ngăn thay đổi ngữ cảnh ngoài thông điệp đã ký.** Nếu tenant ID hoặc mục đích xử lý nằm trong header không được ký, chữ ký body vẫn có thể hợp lệ khi header bị đổi.

Trong các quy trình có giá trị pháp lý, **giá trị chứng cứ của chữ ký số** còn phụ thuộc chính sách định danh, trách nhiệm giữ khóa, quy trình phê duyệt, timestamp và quy định áp dụng. Không suy luận “Verify = true” đồng nghĩa với non-repudiation về mặt pháp lý.

### 3.2. Đúng byte là điều bắt buộc

Nếu bên gửi ký:

~~~text
{"invoice":"154","amount":250}
~~~

thì bên nhận tự sắp xếp lại thành:

~~~text
{ "amount": 250, "invoice": "154" }
~~~

hai JSON có thể tương đương về mặt dữ liệu, nhưng **khác byte**. Phép kiểm tra chữ ký thông thường sẽ thất bại nếu dùng byte khác với byte đã được ký.

Các nguyên nhân phổ biến:

- Đổi UTF-8 thành encoding khác.
- Chuyển LF thành CRLF.
- Thêm/bỏ khoảng trắng, đổi thứ tự trường JSON.
- Thay đổi cách escape Unicode hoặc định dạng số.
- Đọc và dựng lại HTTP body thay vì kiểm tra raw bytes theo đặc tả.
- Ký một tập header nhưng verifier bỏ qua hoặc sắp xếp header khác quy định.

**Giải pháp:** thỏa thuận một **serialization/canonicalization** xác định rõ, hoặc xác minh trực tiếp trên **byte nguyên gốc được giao thức quy định**. Không tự đặt quy tắc chuẩn hóa trong mỗi service.

## 4. Thuật toán nào sử dụng verification key?

### 4.1. Các lược đồ chữ ký thường gặp

| Thuật toán | Verification key | Lưu ý |
| --- | --- | --- |
| **Ed25519** | Public key Ed25519 | Chữ ký EdDSA, hỗ trợ trong JDK hiện đại; không dùng như khóa mã hóa hay X25519 |
| **ECDSA** (ví dụ P-256 với SHA-256) | Public key trên đường cong tương ứng | Phải dùng đúng curve/hash/định dạng chữ ký; bên ký phải xử lý nonce ký đúng cách |
| **RSA-PSS** | RSA public key | Nên cấu hình tham số hash, MGF1, salt length nhất quán; không dùng RSA thô |
| **RSA PKCS#1 v1.5 signature** | RSA public key | Có thể gặp vì tương thích; dùng theo chính sách/giao thức, tránh tự trộn với PSS |
| **Các thuật toán khác được chuẩn hóa** | Public key theo thuật toán tương ứng | Cần xác minh mức hỗ trợ, chính sách, định dạng và cách phân phối trust |

**Tên thuật toán không chỉ là metadata trang trí.** Nó quyết định cách diễn giải public key, signature và message. Một public key RSA không phải tự động được chấp nhận cho bất kỳ cách ký nào.

### 4.2. Algorithm confusion và downgrade

Nếu ứng dụng tin vào chuỗi **alg** do client tự gửi mà không so khớp với policy, kẻ tấn công có thể tìm cách ép verifier dùng thuật toán khác hoặc nhầm lẫn khóa.

Ví dụ trong hệ sinh thái JWT/JOSE, việc cho phép thuật toán **none** khi lẽ ra yêu cầu chữ ký, hoặc lẫn lộn giữa khóa bất đối xứng và khóa HMAC, có thể dẫn tới lỗi nghiêm trọng ở các hệ thống cấu hình sai. Thư viện hiện đại thường có biện pháp bảo vệ, nhưng **ứng dụng vẫn phải cố định danh sách thuật toán được phép** và ràng buộc thuật toán với loại khóa, issuer, audience và use case.

**Không suy luận từ một token không tin cậy rằng hệ thống cần chấp nhận một loại khóa mới.** Header chỉ có thể đưa ra gợi ý chọn khóa nằm **trong tập đã cấu hình tin cậy**.

### 4.3. Signature encoding cũng phải khớp

Chữ ký ECDSA có thể có nhiều biểu diễn theo từng giao thức, chẳng hạn **ASN.1 DER** hoặc dạng nối hai giá trị số nguyên có độ dài cố định theo JOSE. Nếu bên gửi và bên nhận không thống nhất encoding, phép kiểm tra có thể thất bại dù khóa và dữ liệu đúng.

Với **Ed25519**, chữ ký có định dạng cố định theo thuật toán. Khi dùng JCA **Signature.getInstance("Ed25519")**, nên giao cho provider chuẩn xử lý chi tiết chữ ký thay vì tự tách hoặc chuyển đổi byte chữ ký.

**Không tự băm message rồi gọi một API ký/verifier bất kỳ** nếu không biết API đó đã hash bên trong hay yêu cầu prehash. Ed25519 thông thường và Ed25519ph có quy tắc khác nhau; RSA-PSS cũng có tham số riêng.

## 5. Làm sao xác thực verification key?

Một hệ thống an toàn cần thiết lập ràng buộc:

~~~text
(Verification key, algorithm, usage)
              +
(Owner/issuer, authorized purpose, trust policy)
              +
(Valid lifecycle state, version, constraints)
              =
Khóa được phép dùng để xác minh thông điệp cụ thể
~~~

### 5.1. Trust store và cấu hình tin cậy

Đối với dịch vụ biết trước nhà cung cấp, một phương án là **cấu hình public key hoặc certificate** của nhà cung cấp vào trust store thông qua quy trình được duyệt. Khi verifier khởi động, nó chỉ dùng khóa từ cấu hình đáng tin đó.

Điều cần kiểm soát:

- Ai có quyền **thêm, thay, xóa** verification key trong trust store?
- Thay đổi có phê duyệt và audit không?
- Khóa gắn với issuer, tenant, purpose và môi trường nào?
- Có cho phép một khóa dev/staging dùng để xác minh thông điệp production không?
- Có version và cơ chế cập nhật khi bên ký rotation hoặc thu hồi không?

**Trust store không nhất thiết phải bí mật; nó phải được bảo vệ khỏi sửa đổi trái phép.**

### 5.2. Chứng chỉ X.509 và PKI

Chứng chỉ X.509 gắn public key với thông tin chủ thể và có chữ ký của bên phát hành. Một verifier dựa trên PKI cần kiểm tra các yếu tố thích hợp với ngữ cảnh:

1. Chuỗi chứng chỉ từ chứng chỉ chủ thể tới **trust anchor** đã biết.
2. Chữ ký trên các chứng chỉ trong đường dẫn.
3. Danh tính yêu cầu: hostname, tổ chức/định danh hoặc ràng buộc chuyên biệt của ứng dụng.
4. Thời gian hiệu lực và các ràng buộc **Basic Constraints, Key Usage, Extended Key Usage** khi áp dụng.
5. Trạng thái thu hồi qua **CRL/OCSP hoặc cơ chế chính sách tương ứng**, cùng cách xử lý khi thông tin trạng thái không truy cập được.
6. Khóa có được phép dùng cho **mục đích xác minh chữ ký này** không.

**Không đủ** nếu chỉ đọc public key từ một chứng chỉ bất kỳ do request đính kèm rồi gọi Verify. Kẻ tấn công có thể tự tạo chứng chỉ hoặc cặp khóa của mình. Phải xác minh chứng chỉ trong **mô hình trust cụ thể**, không chỉ tính đúng chữ ký của chứng chỉ.

Trong TLS, trust policy gắn với chứng chỉ máy chủ và tên miền. Trong hệ thống phát hành phần mềm, trust policy có thể gắn với **nhà phát hành hoặc vai trò ký release**. Hai chính sách này không tự hoán đổi cho nhau.

### 5.3. JWKS và trường kid

Nhiều hệ thống OAuth/OIDC/JWT dùng **JSON Web Key Set (JWKS)** để công bố các public keys hiện tại của một issuer. Bên xác minh có thể chọn khóa dựa vào **kid** (key ID) trong header token.

Ví dụ định dạng minh họa của một JWK Ed25519:

~~~json
{
  "kty": "OKP",
  "crv": "Ed25519",
  "kid": "issuer-signing-2026-v2",
  "use": "sig",
  "alg": "EdDSA",
  "x": "<base64url public-key bytes>"
}
~~~

Đây **không phải khóa sử dụng được**; trường x cần public key thực theo định dạng JWK. Trong hệ thống thật, một JWKS chứa trường **keys** với danh sách các JWK; không được gán giá trị private key vào JWK công khai.

Quy tắc bảo vệ:

- **Cấu hình trước issuer và JWKS endpoint được tin cậy**, thường qua HTTPS với xác minh chứng chỉ và domain.
- Không tải khóa từ URL **jku/x5u** hay URL khác do token không tin cậy chỉ định nếu chưa có chính sách whitelist/validate phù hợp.
- **kid chỉ là selector** để tìm trong tập khóa tin cậy; không phải chữ ký hay bằng chứng danh tính.
- Ràng buộc khóa được chọn với **issuer, algorithm, key type, key use và policy**; không chỉ tìm một kid có cùng chuỗi trong mọi issuer.
- Quản lý **cache TTL**, refresh khi rotation và xử lý khi endpoint lỗi mà không tự tin vào nguồn thay thế chưa xác thực.
- Không cho attacker dùng kid để tạo đường dẫn tệp, câu truy vấn hoặc tên tài nguyên không được kiểm soát.

Đối với JWT, **chữ ký hợp lệ chưa đủ**. Bên xác minh còn phải kiểm tra issuer, audience, thời hạn (exp, nbf khi có), loại token và quyền nghiệp vụ theo đặc tả. Token hợp lệ cho ứng dụng A không mặc nhiên hợp lệ cho ứng dụng B.

### 5.4. Fingerprint và pinning

**Fingerprint** thường là digest SHA-256 của một biểu diễn khóa được quy định (ví dụ **SubjectPublicKeyInfo DER**). Bên nhận có thể so khớp fingerprint với giá trị được cung cấp qua **một kênh độc lập đã xác thực**.

Nếu cả public key và fingerprint đều do cùng website bị chiếm cung cấp, việc so sánh chỉ xác minh sự nhất quán của hai giá trị giả. Fingerprint không tự tạo trust.

**Pinning** cố định khóa hoặc fingerprint vào ứng dụng giúp thu hẹp tập khóa được chấp nhận trong một số mô hình; tuy nhiên phải có kế hoạch **backup pin, rotation và khôi phục khẩn cấp**, nếu không thay khóa hợp lệ có thể làm dịch vụ dừng hoạt động.

## 6. Verification key trong một quy trình xác minh hoàn chỉnh

Ví dụ: dịch vụ **InvoiceVerifier** nhận hóa đơn có chữ ký từ **BillingIssuer**.

~~~mermaid
sequenceDiagram
    participant I as BillingIssuer
    participant V as InvoiceVerifier
    participant T as Trust store / JWKS tin cậy
    I->>I: Chọn message bytes theo giao thức
    I->>I: Sign bằng private key được bảo vệ
    I-->>V: message + signature + key ID
    V->>V: Xác định issuer và nghiệp vụ được mong đợi
    V->>T: Lấy verification key thuộc issuer được phép
    T-->>V: Public key + algorithm/use/version/trust metadata
    V->>V: Kiểm tra key policy, trạng thái, algorithm
    V->>V: Verify(signature, exact message bytes, public key)
    V->>V: Kiểm tra timestamp/nonce/event ID chống replay
    V->>V: Kiểm tra tenant, invoice ID và quyền nghiệp vụ
    V-->>I: Chấp nhận hoặc từ chối theo chính sách
~~~

Ở đây, **thông điệp không đáng tin không được phép tự quyết định khóa nào sẽ được tin**. Key ID chỉ hỗ trợ chọn đúng khóa từ nguồn đã xác thực.

### 6.1. Ký đúng những trường mang ý nghĩa an ninh

Nếu thông báo gồm:

~~~json
{
  "issuer": "billing-partner",
  "tenantId": "tenant-42",
  "invoiceId": "inv-1001",
  "amount": 250000,
  "currency": "VND",
  "issuedAt": "2026-11-28T02:00:00Z",
  "eventId": "evt-1001"
}
~~~

thì giao thức cần định nghĩa **chính xác byte được ký**. Nếu tenant, amount, issuer hoặc event ID được sử dụng để ra quyết định nhưng lại nằm **ngoài phần được ký/xác thực**, attacker có thể sửa chúng mà chữ ký trên phần còn lại vẫn khớp.

Cũng cần xác nhận rằng chính **BillingIssuer** được phép ký cho tenant, tài khoản và loại giao dịch này. Verification key của issuer khác không được dùng thay chỉ vì chữ ký tương thích với khóa do request cung cấp.

### 6.2. Thứ tự xử lý sai có thể gây hại

**Cách sai:** nhận message, đọc kid trong header, tải khóa từ địa chỉ bất kỳ trong header, thấy Verify = true rồi cập nhật số dư.

**Cách đúng:** xác định issuer được phép từ cấu hình/trust policy, chọn khóa của issuer trong tập đã xác thực, kiểm tra thuật toán/trạng thái, xác minh đúng bytes, sau đó mới kiểm tra **freshness, replay và quyền nghiệp vụ** trước hành động có tác động.

Không nên sử dụng thông điệp chưa xác minh để gây tác động nghiệp vụ hay ghi dữ liệu quan trọng. Có thể cần đọc một lượng metadata **không tin cậy** để định tuyến quá trình verify, nhưng phải coi chúng là gợi ý, áp dụng hạn mức kích thước, parsing an toàn và policy cố định.

## 7. Ví dụ Java 17: xác minh Ed25519 với verification key

Đoạn mã sau minh họa một trường hợp có **trusted public key** từ nguồn cấu hình đã được xác thực. Trong ví dụ chạy độc lập, chương trình tạo cặp khóa ở phần demo để có dữ liệu kiểm tra; trong production, private key phải ở bên ký, còn verifier chỉ nạp **public key đã được duyệt**, không tự lấy public key từ yêu cầu đang kiểm tra.

Các API được sử dụng:

- **KeyPairGenerator("Ed25519")**: sinh cặp khóa cho demo.
- **Signature("Ed25519")**: ký bằng private key hoặc xác minh bằng public key.
- **KeyFactory("Ed25519") + X509EncodedKeySpec**: tái tạo public key từ biểu diễn **X.509 SubjectPublicKeyInfo DER**. Đây **không phải một chứng chỉ X.509 đầy đủ**.
- **Base64**: mã hóa public key DER sang chuỗi để minh họa cách cấu hình/trao đổi; nó không cung cấp xác thực hoặc bí mật.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Base64;
import java.security.spec.X509EncodedKeySpec;

public final class VerificationKeyDemo {

    // Production: lấy base64 SPKI DER từ trust configuration đã xác thực.
    // Không gọi phương thức này với khóa do request chưa tin cậy đưa vào.
    public static PublicKey loadTrustedEd25519Key(String base64Spki)
            throws Exception {
        byte[] encoded = Base64.getDecoder().decode(base64Spki);
        KeyFactory factory = KeyFactory.getInstance("Ed25519");
        return factory.generatePublic(new X509EncodedKeySpec(encoded));
    }

    public static boolean verifyEd25519(
            PublicKey trustedKey, byte[] exactMessage, byte[] signatureBytes)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedKey);
        verifier.update(exactMessage);
        return verifier.verify(signatureBytes);
    }

    public static void main(String[] args) throws Exception {
        // Demo giả lập publisher tạo cặp khóa.
        // Production: private key được giữ ở dịch vụ ký / KMS/HSM.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair publisher = generator.generateKeyPair();

        byte[] message = "issuer=billing;invoice=154;amount=250000"
                .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(publisher.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        // Giả lập bước đăng ký public key qua kênh quản trị tin cậy.
        // Base64 không chứng minh danh tính; trust ở đây là GIẢ ĐỊNH demo.
        String trustedSpki = Base64.getEncoder().encodeToString(
                publisher.getPublic().getEncoded());
        PublicKey trustedKey = loadTrustedEd25519Key(trustedSpki);

        System.out.println("Valid signature: " +
                verifyEd25519(trustedKey, message, signature));

        byte[] changed = "issuer=billing;invoice=154;amount=999999"
                .getBytes(StandardCharsets.UTF_8);
        System.out.println("Modified message: " +
                verifyEd25519(trustedKey, changed, signature));

        // Kẻ khác tự tạo cặp khóa và ký cùng thông điệp.
        KeyPair impostor = generator.generateKeyPair();
        signer.initSign(impostor.getPrivate());
        signer.update(message);
        byte[] fakeSignature = signer.sign();

        // Verifier vẫn giữ public key tin cậy của publisher.
        System.out.println("Wrong signer key: " +
                verifyEd25519(trustedKey, message, fakeSignature));
    }
}
~~~

Kết quả dự kiến:

~~~text
Valid signature: true
Modified message: false
Wrong signer key: false
~~~

### 7.1. Vì sao ví dụ đúng và vẫn chưa đủ cho production?

- **Đúng phép toán:** chữ ký được tạo bằng private key của publisher; public key tương ứng xác minh thành công.
- **Phát hiện thay nội dung:** thay một phần message khiến chữ ký cũ không còn hợp lệ.
- **Phát hiện sai khóa:** chữ ký tạo bằng private key của impostor không khớp với public key đã tin.
- **Giới hạn niềm tin:** chính demo tạo và đăng ký khóa trong một tiến trình; ngoài đời verifier phải xác thực **quy trình đăng ký public key** qua trust store/certificate/JWKS policy.
- **Giới hạn nghiệp vụ:** chưa có issuer whitelist, timestamp, nonce, event ID, chống replay, kiểm soát tenant, ràng buộc loại thông điệp hoặc quyền nghiệp vụ.
- **Giới hạn vận hành:** chưa có key ID, rotation, thu hồi, audit, versioning và quản lý thời hạn chứng chỉ.

### 7.2. Những lưu ý khi nạp khóa trong Java

**SPKI không phải certificate.** Trường **X509EncodedKeySpec** là một cấu trúc chứa public key được mã hóa theo SubjectPublicKeyInfo. Để xác minh một chứng chỉ X.509 hoặc chuỗi chứng chỉ, phải dùng các API và cơ chế kiểm tra chứng chỉ tương ứng, ví dụ **CertificateFactory** và **CertPathValidator/PKIXParameters** với trust anchors/chính sách phù hợp; chỉ parse public key từ certificate không tự làm certificate trở nên đáng tin.

Nếu public key được lưu dạng PEM:

~~~text
-----BEGIN PUBLIC KEY-----
<base64 SubjectPublicKeyInfo DER>
-----END PUBLIC KEY-----
~~~

cần phân tích đúng định dạng PEM rồi decode phần base64. **Không** dùng nhãn PRIVATE KEY cho verification key, không đổi byte của JWK Ed25519 thành SPKI bằng cách coi hai định dạng giống nhau. Nếu dùng JWKS, hãy dùng bộ xử lý JWK/JOSE được kiểm chứng và cấu hình issuer/alg policy rõ ràng.

**Không tự chọn public key bằng câu lệnh “lấy khóa đầu tiên”** khi có nhiều phiên bản hợp lệ. Phải chọn theo nguồn tin cậy, key ID và policy, đồng thời có xử lý khi khóa không tìm thấy hoặc nhiều bản ghi mâu thuẫn.

## 8. Vòng đời verification key

Verification key không cần bí mật như private signing key nhưng **độ tin cậy của nó phải có vòng đời**. Một khóa còn nguyên byte có thể không còn được phép xác minh thông điệp mới vì đã rotation, bị thu hồi hoặc đổi quyền chủ thể.

| Giai đoạn | Verification key | Signing key và cơ chế liên quan |
| --- | --- | --- |
| **Tạo cặp khóa** | Public key được tạo cùng private key, có thuật toán, ID, purpose | Private key được sinh và bảo vệ bằng cơ chế đủ mạnh |
| **Đăng ký** | Xác minh chủ thể sở hữu/quyền sử dụng, kiểm soát quy trình thêm khóa vào trust | Cấp quyền ký cho đúng workload và nội dung được phép |
| **Cấp phát/phân phối** | Xuất bản public key/certificate qua kênh đã được xác thực | Không công bố private key; không cấp quyền Sign quá rộng |
| **Sử dụng** | Verify với đúng issuer, algorithm, key usage, message bytes | Kiểm tra nghiệp vụ trước khi ký, audit từng thao tác Sign nhạy cảm |
| **Rotation** | Công bố khóa mới trước, dùng key ID/version, giữ chồng lấp có giới hạn | Chuyển signer sang private key mới, dừng ký bằng khóa cũ |
| **Thu hồi/vô hiệu** | Loại khỏi tập khóa được phép, cập nhật trust store/cert status/cache | Disable hoặc revoke quyền dùng private key có nguy cơ |
| **Lưu giữ lịch sử** | Có thể giữ public key, certificate, chain, revocation/timestamp evidence để xác minh lịch sử | Ngừng ký mới; quyết định giữ/hủy private key theo chính sách |
| **Hủy** | Xóa cấu hình không cần thiết hoặc ngừng tin; có thể lưu public key để phục vụ hồ sơ cũ | Hủy private key và bản sao sau khi kiểm kê phụ thuộc |

### 8.1. Rotation có hai phía cần phối hợp

Giả sử **PaymentSigner** đã ký sự kiện bằng private key **K1**. Bên nhận **PaymentVerifier** đang tin public key K1. Nhà cung cấp muốn chuyển sang K2.

~~~mermaid
sequenceDiagram
    participant S as PaymentSigner
    participant T as Trusted key distribution
    participant V as PaymentVerifier
    S->>T: Đăng ký public K2 đã được phê duyệt
    T-->>V: Công bố K2 bên cạnh K1 với key ID/version
    V->>V: Xác minh nguồn khóa; cập nhật trusted key set
    S->>S: Chuyển signing sang private K2
    S-->>V: Message + signature K2 + kid=K2
    V->>V: Chọn K2 trong trusted set, Verify + kiểm tra nghiệp vụ
    Note over S,V: Trong cửa sổ hợp lệ, K1 có thể dùng cho thông điệp cũ đang chờ
    S->>S: Dừng ký mới bằng K1
    T-->>V: Thu hẹp rồi loại K1 khỏi chính sách cho thông điệp mới
~~~

Một quy trình có kiểm soát:

1. **Sinh/đăng ký K2:** xác thực chủ thể, thuật toán, mục đích và quyền quản trị.
2. **Công bố trước K2:** bên xác minh được cập nhật qua nguồn tin cậy trước khi signer bắt đầu dùng K2.
3. **Chuyển signing:** message mới dùng private K2, kèm key ID được quy định bởi giao thức.
4. **Giai đoạn chồng lấp ngắn:** verifier có thể kiểm tra K1 và K2 theo policy, nhưng vẫn kiểm tra timestamp, event ID và thời hạn được phép.
5. **Loại K1 khỏi xác minh thông điệp mới:** hết cửa sổ chuyển đổi; xử lý riêng bản ghi lịch sử nếu nghiệp vụ yêu cầu.
6. **Kiểm tra cache và hệ thống phụ thuộc:** giám sát tỷ lệ signature verify thất bại và danh sách verifier chưa cập nhật.

**Không giả định** mọi verifier nhận khóa mới ngay sau khi JWKS hoặc trust store đổi. Cache TTL, khả năng truy cập endpoint, thứ tự deploy và đồng bộ đồng hồ có thể gây lỗi xác minh hàng loạt.

### 8.2. Thu hồi khẩn cấp khi private signing key bị lộ

Nếu private K1 bị đánh cắp, người tấn công có thể tạo **chữ ký hợp lệ bằng K1**. Đây không phải vấn đề không khớp public key: mọi verifier còn tin K1 có thể chấp nhận chữ ký giả.

Cần:

- Chặn **quyền Sign** hoặc vô hiệu hóa private key theo khả năng KMS/HSM, điều tra nguồn lộ.
- Ngừng tin **verification key K1 cho thông điệp mới** theo cơ chế tin cậy đang áp dụng, thu hồi certificate nếu có.
- Chủ động cập nhật trust store/JWKS, xử lý các client có cache cũ, phiên đang chạy và hệ thống offline.
- Phân tích **cửa sổ bị lộ** và các chữ ký/sự kiện có khả năng giả mạo.
- Tạo/đăng ký khóa thay thế, kiểm thử khả năng Verify trước khi chuyển luồng nghiệp vụ.
- Đánh giá **chữ ký lịch sử** riêng, với thời gian ký, timestamp được tin cậy và bằng chứng trạng thái khóa lúc ký nếu cần.

**Chỉ xóa key K1 khỏi JWKS không xóa những token/chữ ký giả đã được kẻ tấn công tạo**, đặc biệt nếu các bên xác minh còn cache khóa cũ hoặc dữ liệu đã được xử lý. Cần phối hợp thu hồi, hạn sử dụng, replay protections và xử lý giao dịch ảnh hưởng.

### 8.3. Hết hạn chứng chỉ khác thu hồi khóa

- **Certificate expiry** nói thời hạn hiệu lực được ghi đã kết thúc. Nó không tự chứng minh private key bị lộ.
- **Revocation** là tín hiệu khóa/chứng chỉ không còn được tin theo chính sách trong một giai đoạn.
- **Historical signature validation** có thể đòi hỏi bằng chứng rằng chữ ký đã có mặt và khóa/chứng chỉ được phép tại một thời điểm trước, không thể suy ra chỉ bằng cách Verify với public key còn lưu.

Vì thế, nếu phải giữ bằng chứng ký tài liệu nhiều năm, cần thiết kế **trusted timestamp, chain validation, revocation evidence và chính sách lưu hồ sơ** phù hợp. Một file chữ ký còn hợp lệ về mặt toán học không tự giải quyết toàn bộ yêu cầu chứng minh thời điểm và thẩm quyền ký.

## 9. KMS/HSM và việc bảo vệ signing key ảnh hưởng đến verifier thế nào?

**KMS (Key Management Service)** và **HSM (Hardware Security Module)** thường giúp bảo vệ **private signing key**; verification key ở phía nhận có thể được công bố rộng hơn. Hai phía có vai trò khác nhau nhưng phải cùng tuân thủ policy.

~~~mermaid
flowchart LR
    A["Ứng dụng cần ký thông điệp"] --> B["Kiểm tra quyền nghiệp vụ"]
    B --> K["KMS/HSM: Sign bằng private key"]
    K --> S["Signature + key ID"]
    M["Message đã canonicalize"] --> S
    S --> V["Verifier"]
    T["Trusted public verification key + policy"] --> V
    V --> R{"Verify + authorization + freshness?"}
    R -->|Đạt| OK["Chấp nhận thông điệp"]
    R -->|Không đạt| NO["Từ chối / ghi sự kiện"]
~~~

**HSM giữ private key không xuất được** giảm nguy cơ rò rỉ vật liệu khóa, nhưng **không bảo đảm mọi chữ ký được tạo đều hợp lệ về mặt nghiệp vụ**. Một workload có quyền gọi Sign quá rộng có thể dùng private key đúng để ký nội dung trái phép. Vì thế:

- **Signing workload:** chỉ có quyền Sign với khóa và mục đích cần thiết; kiểm tra nội dung được phép ký.
- **Key administrator:** quản lý policy/rotation, không mặc nhiên được quyền ký mọi nội dung hoặc đọc dữ liệu.
- **Verifier:** chỉ cần public key được tin cậy; không cần quyền đọc private key hoặc quyền Sign.
- **Auditor:** theo dõi sự kiện tạo/chuyển/thu hồi khóa và thao tác Sign; không cần vật liệu private key.

Một KMS/HSM cũng có thể có API Verify, nhưng việc API trả kết quả đúng **không thay thế xác minh danh tính/ủy quyền của khóa**. Không tự coi mọi khóa tồn tại trong KMS là được phép ký thay mọi issuer.

### 9.1. Verification key và envelope encryption là hai vai trò khác nhau

Trong **envelope encryption**, hệ thống dùng **DEK** mã hóa dữ liệu và **KEK** bảo vệ DEK, có thể qua KMS/HSM. Verification key của chữ ký số **không trực tiếp giải mã dữ liệu hoặc bọc DEK**.

Ví dụ:

- Một dịch vụ lưu hồ sơ dùng **AES-GCM DEK** để mã hóa nội dung và **KEK KMS** để bọc DEK.
- Khi xuất một bản manifest kèm danh sách digest hồ sơ, dịch vụ dùng **private signing key** để ký manifest.
- Đối tác dùng **public verification key được xác thực** để Verify manifest; chỉ khi được cấp quyền thích hợp mới dùng cơ chế giải mã hồ sơ.

Như vậy, **confidentiality**, **integrity/authenticity** và **access authorization** là những lớp độc lập có thể phối hợp:

| Mục tiêu | Công cụ phù hợp |
| --- | --- |
| Bí mật nội dung | AES-GCM với DEK hoặc cơ chế mã hóa phù hợp |
| Bảo vệ DEK | KEK và key wrapping trong KMS/HSM |
| Xác minh nguồn manifest/thông điệp | Chữ ký số + trusted verification key |
| Cho phép tài khoản đọc hồ sơ | IAM và phân quyền nghiệp vụ |
| Truy vết ký/giải mã | Audit log, key ID/version và cảnh báo |

**Không dùng Ed25519 verification key như một KEK để bọc dữ liệu.** Ed25519 là thuật toán chữ ký, không phải thuật toán mã hóa hoặc thỏa thuận khóa.

## 10. Thiết kế key ID, metadata và nguồn tin cậy

Một tổ chức có thể quản lý nhiều phiên bản verification key cho một issuer hoặc nhiều issuer khác nhau. Nếu thiếu metadata, verifier có thể chọn nhầm khóa.

### 10.1. Registry verification key minh họa

~~~json
{
  "issuer": "billing-partner",
  "keyId": "billing-signing-v4",
  "algorithm": "Ed25519",
  "keyUse": "verify-invoice-event",
  "environment": "production",
  "trustSource": "approved-partner-onboarding",
  "verificationKeyRef": "trust-store:billing-signing-v4",
  "state": "ACTIVE",
  "effectiveFrom": "2026-11-15T00:00:00Z"
}
~~~

Đây là **mô hình metadata giả định**, không phải chuẩn bắt buộc của JWKS/X.509. Phần public key có thể được lưu qua SPKI PEM, JWK hoặc certificate với định dạng tương ứng.

Mỗi bản ghi cần có:

- **Owner/issuer:** bên được ủy quyền phát hành chữ ký.
- **Algorithm/key type:** khóa thuộc thuật toán gì, kiểm tra bằng lược đồ nào.
- **Usage/purpose:** chữ ký trên artifact, webhook, invoice hay một loại thông điệp khác.
- **Environment/tenant:** khóa chỉ được tin ở đâu.
- **Key ID/version:** hỗ trợ rotation, cache, audit, tìm khóa lịch sử.
- **Trust origin:** ai đã xác minh danh tính và phê duyệt khóa.
- **State/time policy:** chưa kích hoạt, đang hoạt động, bị đình chỉ, bị thu hồi hoặc chỉ giữ cho việc xác minh lịch sử.

**Không để các trường security policy này bị thay trực tiếp qua input từ người đang yêu cầu Verify.**

### 10.2. Khóa tin cậy phải được quản lý như cấu hình bảo mật

Một số hành động đáng coi là thay đổi bảo mật nhạy cảm:

1. Thêm verification key mới cho issuer production.
2. Đổi địa chỉ JWKS được tin cậy.
3. Đổi key usage hoặc thuật toán được phép.
4. Cho phép một issuer ký thay tenant hoặc service khác.
5. Khôi phục key đã bị thu hồi.
6. Bỏ kiểm tra certificate revocation/hostname/policy hoặc chuyển chế độ thất bại thành “bỏ qua lỗi”.

Mỗi thay đổi nên có **ủy quyền, phê duyệt, dấu vết kiểm toán và phương án rollback**. Cấu hình public key không cần giữ bí mật nhưng phải được bảo vệ về **tính toàn vẹn và quyền sửa đổi**.

## 11. Kịch bản thực tế: xác minh webhook thanh toán

Giả sử **PaymentGateway** gửi webhook cho dịch vụ **OrderService**:

~~~text
POST /payments/webhook
Headers:
  X-Key-Id: gateway-signing-v3
  X-Signature: <base64 signature>
  X-Timestamp: <issued timestamp>

Body:
  {"orderId":"O-1001","status":"PAID","amount":250000}
~~~

Đây là ví dụ minh họa, không mô tả giao thức của nhà cung cấp cụ thể. **Chính tài liệu của giao thức** phải định nghĩa thuật toán ký, phần byte được ký, encoding chữ ký và cách kiểm tra freshness. Không tự giả định rằng chữ ký chỉ bao phủ body.

### Quy trình xử lý an toàn

1. **Định tuyến issuer:** endpoint/webhook configuration xác định nhà cung cấp PaymentGateway đã được cấp quyền, không lấy issuer tùy ý rồi tin ngay.
2. **Giới hạn input:** kiểm tra kích thước header/body, định dạng key ID/chữ ký, giới hạn tần suất.
3. **Chọn verification key:** lấy public key tương ứng từ **trusted key registry hoặc JWKS endpoint đã cấu hình**, chỉ trong tập của PaymentGateway.
4. **Kiểm tra policy:** đúng thuật toán, trạng thái ACTIVE, purpose “payment-webhook”, thời điểm/phiên bản hợp lệ; kid không phải nguồn tin cậy.
5. **Xây đúng signed bytes:** theo quy ước giao thức, gồm timestamp, body và các trường khác phải bảo vệ nếu giao thức yêu cầu.
6. **Verify chữ ký:** thất bại thì từ chối; không thử bỏ chữ ký, đổi thuật toán hoặc tải một khóa khác từ URL do request đưa vào.
7. **Kiểm tra chống replay:** timestamp trong cửa sổ, event ID/idempotency key chưa xử lý; không coi chữ ký hợp lệ là bằng chứng mới.
8. **Kiểm tra nghiệp vụ:** order ID có tồn tại, amount/currency có khớp, trạng thái chuyển đổi có hợp lệ, gateway có được phép xác nhận đơn hàng này không.
9. **Ghi log:** key ID, issuer, request ID, lý do từ chối được chuẩn hóa; không ghi secret hay toàn bộ dữ liệu nhạy cảm.
10. **Xử lý rotation:** hỗ trợ khóa gateway mới khi được xác thực, không giữ khóa cũ vô hạn.

### Điều gì xảy ra nếu thiếu bước 3?

Kẻ tấn công tự tạo cặp Ed25519, đặt public key trong một trường tùy ý kèm request, ký body “PAID”. Nếu OrderService dùng chính public key đó để Verify rồi cập nhật đơn hàng, mọi phép toán đều có thể trả **true**. Lỗi nằm ở **quyết định tin public key giả**, không phải lỗi thuật toán Ed25519.

### Điều gì xảy ra nếu thiếu bước 8?

Gateway thật ký thông báo hợp lệ về mặt mật mã, nhưng thông báo đề cập **order ID không thuộc khách hàng đang xử lý**. Nếu OrderService bỏ kiểm tra quyền và trạng thái nghiệp vụ, nó vẫn có thể cập nhật sai đơn hàng. Verification key chỉ là một lớp xác thực nguồn thông điệp.

## 12. Threat model và những lỗi thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Tin public key đính kèm request mà không xác thực | Attacker tự ký rồi tự đưa khóa Verify | Registry/trust store/certificate/JWKS có issuer cố định |
| Tin kid như bằng chứng danh tính | Chọn nhầm khóa giữa issuer hoặc tenant | kid chỉ chọn trong **tập khóa tin cậy đúng issuer**, thêm policy checks |
| Cho token chỉ định jku/x5u tùy ý | Có thể tải khóa từ nguồn attacker hoặc gây SSRF | Endpoint được cấu hình/whitelist, xác thực HTTPS và nguồn |
| Cho client chọn algorithm không bị ràng buộc | Algorithm confusion hoặc downgrade | Danh sách thuật toán cố định, kiểm tra key type/use |
| Chỉ Verify chữ ký rồi bỏ qua issuer/audience | Token hợp lệ cho hệ thống khác cũng được chấp nhận | Kiểm tra claims, purpose, audience và authorization |
| Ký body nhưng xử lý header không được bảo vệ | Header/tenant/purpose bị sửa mà chữ ký vẫn khớp | Đặc tả signed bytes đầy đủ, canonicalization nhất quán |
| Xác minh lại từ JSON đã serialize khác byte | Chữ ký hợp lệ bị từ chối hoặc chọn sai dữ liệu | Verify đúng byte theo giao thức, canonical format |
| Thiếu freshness/idempotency | Replay thông điệp đã ký hợp lệ | Timestamp, nonce/event ID, state và hạn sử dụng |
| Cache JWKS quá lâu | Verifier tiếp tục tin khóa cũ đã thu hồi | TTL, push/update khẩn cấp, chính sách khi endpoint lỗi |
| Xóa khóa cũ quá sớm khi rotation | Thông điệp còn chờ/hồ sơ cũ bị từ chối | Overlap có giới hạn, versioning, chính sách historical verify |
| Private signing key không xuất được nhưng Sign quá rộng | Kẻ chiếm workload vẫn ký nội dung giả | IAM least privilege, phê duyệt nghiệp vụ, audit |
| Dùng verification key thay khóa mã hóa dữ liệu | Sai mục đích mật mã | Tách Sign/Verify khỏi DEK/KEK và Encrypt/Decrypt |
| Để mọi admin sửa trust store không có audit | Tráo khóa mà không để lại dấu vết | Bảo vệ integrity cấu hình, tách nhiệm vụ, approval |

### 12.1. Key substitution

**Key substitution** xảy ra khi kẻ tấn công thay verification key được dùng cho một danh tính. Họ không cần tìm private key thật; chỉ cần khiến verifier tin private/public key pair do họ kiểm soát.

Biện pháp trọng tâm là **xác thực và quản lý nguồn public key**: trust anchors, issuer chính xác, key registry, quy trình đăng ký, bảo vệ quyền sửa cấu hình và kiểm toán.

### 12.2. Replay và chữ ký hết hạn

Một chữ ký hợp lệ hôm qua có thể vẫn hợp lệ về mặt toán học hôm nay. Nếu thông điệp “chuyển tiền” được xử lý lại không có kiểm soát trạng thái, chữ ký chỉ ngăn sửa dữ liệu chứ không ngăn thực hiện lại.

Bổ sung **timestamp, nonce, event ID, sequence hoặc token expiry** theo giao thức, và bảo đảm các giá trị an ninh liên quan được nằm trong phần ký/xác thực. Kiểm tra thời gian phải xử lý sai lệch đồng hồ và chính sách cửa sổ rõ ràng.

### 12.3. Dữ liệu được ký nhưng private key bị lạm dụng

Ngay cả khi verification key đúng nguồn, nội dung vẫn có thể bị ký trái phép nếu service ký bị chiếm quyền. Hệ thống cần kiểm tra quyền và ý nghĩa nghiệp vụ **trước bước Sign**, giới hạn KMS/HSM API, giám sát sự kiện ký bất thường và sẵn sàng thu hồi khóa.

## 13. Kiểm toán và ứng phó sự cố verification key

**Những sự kiện nên được ghi nhận:**

- Đăng ký hoặc thay public verification key cho một issuer/tenant.
- Thay trusted JWKS URL, trust anchor, algorithm allowlist hoặc key usage.
- Phát hành/gia hạn/thu hồi certificate; thêm hoặc loại key version.
- Thao tác **Sign** bằng private key trong KMS/HSM: principal, key ID, mục đích, kết quả; không log private key.
- Tỷ lệ chữ ký không hợp lệ, kid không tồn tại, issuer không khớp, algorithm bị cấm và request replay.
- Bên xác minh còn dùng khóa đã hết hạn/thu hồi sau khi policy cập nhật.

Nhật ký có thể có **timestamp, principal, key ID/version, issuer, request ID, policy version, kết quả Verify, nguyên nhân từ chối**. Không log private signing key, HMAC secret, DEK/KEK rõ, token truy cập hoặc payload nhạy cảm chỉ để debug.

### Kịch bản sự cố: khóa xác minh production bị thay

1. **Cô lập thay đổi trust:** ngăn cập nhật tiếp, khôi phục nguồn khóa đáng tin sau khi xác minh và bảo vệ bằng chứng.
2. **Kiểm tra phạm vi:** ứng dụng nào đã nhận verification key giả, từ lúc nào và đã xác minh những message/token nào.
3. **Ngăn xử lý mới:** vô hiệu hóa key/issuer bị ảnh hưởng trong hệ thống xác minh, xử lý các cache và phiên làm việc có rủi ro.
4. **Đánh giá giao dịch:** xác định những sự kiện đã được chấp nhận dựa trên khóa giả; áp dụng quy trình xử lý nghiệp vụ và thông báo theo chính sách.
5. **Điều tra quyền sửa:** tài khoản, CI/CD, secret/config management, thay đổi JWKS endpoint và log quản trị.
6. **Phục hồi an toàn:** tái đăng ký khóa đúng, kiểm thử end-to-end, điều chỉnh approval/quyền và giám sát lần thay tiếp theo.

Nếu sự cố là **lộ private signing key thật**, phải đồng thời thu hồi quyền ký, đánh giá cửa sổ có thể tạo chữ ký giả, thay private/public key pair và thông báo các verifier liên quan.

## 14. Checklist thiết kế và vận hành verification key

1. **Mục tiêu:** đang Verify chữ ký số, hay HMAC/AEAD tag? Thuật toán và khóa có đúng vai trò?
2. **Danh tính:** public key thuộc issuer/chủ thể nào, được xác minh qua nguồn tin cậy nào?
3. **Phân phối:** trust store, certificate, JWKS hay pinning được cấu hình và cập nhật an toàn không?
4. **Policy:** khóa có đúng purpose, environment, tenant, algorithm, key usage và trạng thái không?
5. **Key selector:** kid chỉ chọn khóa trong tập đã tin hay client có thể chỉ định khóa/URL tùy ý?
6. **Certificate:** nếu dùng PKI, có kiểm tra chain, identity, validity, usage và revocation phù hợp không?
7. **Dữ liệu:** bên ký và bên Verify có cùng chính xác message bytes hoặc chuẩn canonicalization không?
8. **Signature encoding:** format chữ ký và tham số thuật toán có thống nhất không?
9. **Freshness:** có timestamp/nonce/event ID chống replay và rollback khi nghiệp vụ yêu cầu?
10. **Business authorization:** chữ ký hợp lệ có được kiểm tra cùng issuer, audience và quyền với tài nguyên không?
11. **Rotation:** đã công bố khóa mới trước, kiểm soát overlap, cache TTL và thời điểm rút khóa cũ chưa?
12. **Compromise:** có thủ tục revoke khẩn cấp, xử lý cache và xác định thông điệp giả đã chấp nhận không?
13. **Historical verification:** dữ liệu lâu năm có cần giữ public key/certificate và bằng chứng timestamp/revocation không?
14. **Signing key:** private key có được bảo vệ trong KMS/HSM, IAM least privilege và kiểm toán Sign không?
15. **Audit:** ai thêm/thay khóa tin cậy, lỗi Verify và sự kiện nghi vấn có được theo dõi mà không lộ secret không?
16. **Thử nghiệm:** có kiểm tra trường hợp đúng khóa/sai khóa, message bị sửa, kid lạ, alg cấm, cert hết hạn, replay và rotation không?

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một chữ ký Ed25519 Verify = true với public key được gửi ngay trong request. Đã xác thực bên gửi chưa?

**Đáp án:** Chưa. Chữ ký khớp với khóa đó về mặt toán học, nhưng hệ thống chưa biết khóa thuộc danh tính được phép gửi. Phải lấy/đối chiếu khóa trong nguồn tin cậy gắn với issuer.

**Câu 2.** Tại sao verification key là public key mà vẫn phải bảo vệ trust store?

**Đáp án:** Public key không cần bí mật, nhưng trust store quyết định khóa nào được tin. Nếu attacker có thể thay khóa, hắn có thể đưa khóa của mình vào danh sách được chấp nhận rồi tạo chữ ký giả.

**Câu 3.** kid trong JWT/JWKS có chứng minh token được issuer chính thức ký không?

**Đáp án:** Không. kid chỉ là định danh chọn khóa. Phải chọn khóa trong tập đáng tin của đúng issuer, xác minh chữ ký và kiểm tra claims, algorithm, key usage và quyền.

**Câu 4.** Có thể dùng public key Ed25519 để mã hóa DEK như dùng RSA-OAEP không?

**Đáp án:** Không. Ed25519 là thuật toán chữ ký số. Bọc DEK cần cơ chế key wrapping/public-key encryption/KEM phù hợp; không đổi thuật toán chỉ vì đều dùng public/private key.

**Câu 5.** Vì sao chữ ký hợp lệ không tự ngăn webhook bị xử lý hai lần?

**Đáp án:** Một thông điệp cũ cùng chữ ký có thể được phát lại nguyên vẹn. Hệ thống cần timestamp/nonce/event ID, trạng thái idempotency hoặc sequence theo giao thức.

**Câu 6.** Đổi private signing key K1 sang K2 ngay mà không báo phía Verify sẽ xảy ra điều gì?

**Đáp án:** Verifier chưa tin public K2 có thể từ chối mọi chữ ký mới. Cần công bố K2 qua kênh đã xác thực trước khi chuyển signer, sau đó quản lý khoảng chồng lấp và thu hồi K1.

**Câu 7.** Private K1 bị lộ nhưng chứng chỉ K1 chưa hết hạn. Có thể tiếp tục chấp nhận chữ ký K1 đến hết hạn không?

**Đáp án:** Không nên. Kẻ có private K1 có thể ký thông điệp giả. Phải thực hiện thu hồi/vô hiệu hóa theo chính sách, cập nhật verifier, phân tích thông điệp bị ảnh hưởng và thay khóa.

**Câu 8.** HSM giữ private signing key không cho xuất. Hệ thống đã hoàn toàn tránh được chữ ký trái phép chưa?

**Đáp án:** Chưa. Một service có quyền Sign có thể bị lạm dụng để yêu cầu HSM ký nội dung sai. Phải bảo vệ quyền gọi API, kiểm tra nghiệp vụ trước ký và ghi audit.

**Câu 9.** Vì sao một chứng chỉ X.509 chứa public key đúng vẫn có thể không được tin?

**Đáp án:** Chứng chỉ có thể do CA không tin cậy phát hành, hết hạn, sai danh tính, sai key usage hoặc bị thu hồi. Phải kiểm tra chứng chỉ theo trust policy của ứng dụng.

**Câu 10.** Sau khi chứng chỉ ký tài liệu hết hạn, mọi chữ ký tài liệu cũ có tự động trở thành giả không?

**Đáp án:** Không. Cần chính sách kiểm tra chữ ký lịch sử với bằng chứng thời gian ký, trạng thái chứng chỉ/thu hồi khi ký và hồ sơ liên quan; Verify toán học và trust theo thời điểm là hai lớp khác nhau.

## Kết luận

**Verification key là public key được sử dụng để kiểm tra chữ ký số, nhưng bản thân phép Verify không quyết định khóa thuộc về ai hoặc ai được quyền ký thông điệp.** Bảo đảm nguồn gốc đòi hỏi kết hợp **chữ ký hợp lệ + khóa xác minh đã được xác thực + chính sách issuer/algorithm/key usage + kiểm tra nghiệp vụ và freshness**.

Trong hệ thống quản lý khóa an toàn, verification key cần được đăng ký và phân phối qua **trust store, PKI hoặc JWKS đáng tin**, có **key ID, version, rotation, revocation và audit**. Private signing key tương ứng phải được bảo vệ trong **KMS/HSM** hoặc ranh giới tương đương, với quyền Sign giới hạn. **Một thuật toán chữ ký mạnh không đủ nếu hệ thống tin sai verification key; an toàn bắt đầu từ quyết định đúng về khóa được phép tin.**
