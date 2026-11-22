# 9.4 RSA PKCS#1 v1.5, RSASSA-PSS, ECDSA và EdDSA

Chữ ký số là cơ chế mật mã bất đối xứng giúp bên nhận kiểm tra một chuỗi byte có còn nguyên vẹn và có được ký bởi khóa riêng tương ứng với **khóa công khai được tin cậy** hay không. Trong ứng dụng Java, bốn lựa chọn quan trọng là **RSA PKCS#1 v1.5 signature**, **RSASSA-PSS**, **ECDSA** và **EdDSA**. Chúng đều dùng private key để ký và public key để xác minh, nhưng **không thay thế lẫn nhau**: thuật toán hash, tham số, kiểu khóa, định dạng chữ ký và quy tắc verify khác nhau.

Bài này giải thích đầy đủ điểm mạnh và giới hạn, cách chọn scheme, lập trình với **java.security.Signature** trên Java 17+, những vấn đề tương thích giữa Java và hệ thống khác, rồi thực hành bằng hai chương trình chạy độc lập. Đề bài thuộc phần **chữ ký số**; vì vậy “RSA PKCS#1 v1.5” ở đây chỉ **RSASSA-PKCS1-v1_5 để ký**, không phải sơ đồ **RSAES-PKCS1-v1_5 để mã hóa**.

## 1. Mô hình ký và xác minh

~~~text
                  BÊN KÝ                             BÊN NHẬN
message bytes M, private key SK                message bytes M', public key PK
            |                                              |
            v                                              v
  Signature.initSign(SK)                         Signature.initVerify(PK)
  Signature.update(M)                            Signature.update(M')
  Signature.sign() -> S                          Signature.verify(S)
            |                                              |
            +------------- gửi M và S --------------------->|
                                                           |
                                         true: hợp lệ theo key/profile
                                         false: không được chấp nhận
~~~

Một chữ ký hợp lệ chỉ có giá trị khi **public key được xác minh là thuộc đúng chủ thể**. Nếu người gửi tự cung cấp một public key chưa được xác thực cùng message và signature, verify true chỉ chứng minh chữ ký khớp **khóa người gửi tự chọn**. Cần xác thực key từ chứng chỉ hợp lệ, cấu hình tin cậy, JWKS đáng tin hoặc quy trình phân phối khóa được kiểm soát.

**Chữ ký số hỗ trợ:**

- **Integrity:** sửa byte của thông điệp thường khiến chữ ký cũ không còn hợp lệ.
- **Origin authentication:** có cơ sở tin thông điệp được ký bằng private key tương ứng với public key đã xác thực.
- **Bằng chứng kỹ thuật:** hữu ích để kiểm chứng gói phần mềm, thông báo, tài liệu; khả năng quy trách nhiệm/pháp lý còn phụ thuộc quản trị khóa, danh tính, thời gian và quy trình.

**Chữ ký không tự mang lại:** bí mật nội dung, phân quyền thao tác, bảo vệ khỏi replay hoặc bằng chứng chắc chắn về thời điểm ký. Phải kết hợp TLS, authorization, hạn hiệu lực, transaction ID và quy trình quản lý khóa tùy bài toán.

### 1.1. Phân biệt hash, MAC và signature

| Cơ chế | Khóa | Tính chất | Hạn chế |
| --- | --- | --- | --- |
| SHA-256 | Không | Fingerprint của dữ liệu | Kẻ sửa dữ liệu cũng tính lại được hash; không xác thực nguồn. |
| HMAC-SHA256 | Bí mật chung | Xác thực bên biết secret và phát hiện sửa message | Hai phía cùng giữ secret, không phân biệt ai thực sự tạo tag; không mã hóa. |
| RSA/ECDSA/EdDSA signature | Private key ký, public key verify | Integrity và quan hệ với private key đã xác thực danh tính | Không giữ bí mật message; không tự chặn replay. |
| AES-GCM | Khóa đối xứng | Bảo mật plaintext và xác thực ciphertext/AAD | Không phải chữ ký công khai. |

Với một lược đồ chữ ký có tính ngẫu nhiên, ký cùng message hai lần có thể tạo hai chữ ký **khác bytes nhưng cùng hợp lệ**. Vì thế phải dùng **Signature.verify**, không so sánh chữ ký nhận được với chữ ký mới tạo bằng Arrays.equals.

## 2. So sánh bốn scheme

| Scheme | Primitive / khóa | JCA Signature name | Đặc trưng |
| --- | --- | --- | --- |
| **RSASSA-PKCS1-v1_5** | RSA | **SHA256withRSA** | Hash + DigestInfo + EMSA-PKCS1-v1_5 padding. Signature deterministic theo message/key. Phổ biến ở hệ thống hiện hữu. |
| **RSASSA-PSS** | RSA | **RSASSA-PSS** | PSS padding dùng salt và MGF; hash/MGF/saltLength/trailer phải thống nhất. Thường được ưu tiên cho hệ thống RSA mới. |
| **ECDSA** | EC Weierstrass curve (ví dụ P-256) | **SHA256withECDSA** | Chữ ký là cặp số (r,s); nonce ký k phải được xử lý an toàn; có DER và P1363 encoding. |
| **EdDSA** | Edwards curves (Ed25519, Ed448) | **Ed25519**, **Ed448** | Pure EdDSA deterministic với key/message, output gọn; variant pure/prehash/context không được đánh đồng. |

Các kích thước thường được so sánh **RSA-3072, ECDSA P-256 và Ed25519** ở mức bảo mật cổ điển khoảng **128 bit**, nhưng chi phí CPU, kích thước key/signature và khả năng hỗ trợ phụ thuộc provider, giao thức và chính sách. Không suy từ độ dài output rằng một phần mềm hoặc một khóa production đã an toàn.

### 2.1. Điều gì phải khớp giữa hai phía?

Một bên Java ký và bên Go, Node.js, OpenSSL hoặc Java provider khác xác minh được khi cả hai có cùng hợp đồng:

1. Scheme **v1.5/PSS/ECDSA/EdDSA**; cùng hash và variant.
2. Public key/curve/key ID đúng chủ thể, private key tương ứng được bảo vệ.
3. Tham số đặc thù (PSS hash, MGF, saltLength, trailer; ECDSA curve; Ed25519/Ed448).
4. **Bytes đã ký**: UTF-8, canonical JSON, raw body, newline, thứ tự field và dấu phân cách chính xác.
5. Encoding chữ ký **DER, P1363, RSA raw bytes, Ed25519 raw bytes** phù hợp với giao thức.
6. Envelope/version và các kiểm tra bổ sung như timestamp, issuer, key usage, replay.

Cùng tên thuật toán **không đủ** nếu input bytes hoặc encoding khác.

## 3. RSASSA-PKCS1-v1_5: RSA signature với padding cổ điển

### 3.1. Cơ chế

Khi dùng **SHA256withRSA**, JCA thực hiện sơ đồ chữ ký RSASSA-PKCS1-v1_5:

1. Băm đúng bytes thông điệp bằng **SHA-256**.
2. Đưa hash và định danh thuật toán vào cấu trúc **DigestInfo** dạng ASN.1 DER.
3. Dùng **EMSA-PKCS1-v1_5** tạo encoded message có cấu trúc padding kiểm tra nghiêm ngặt.
4. Thực hiện phép toán ký RSA bằng **private key**; verify thực hiện quy tắc đối ứng bằng public key.

~~~text
M -> SHA-256(M) -> DigestInfo
                   |
                   v
           EMSA-PKCS1-v1_5 encoding
                   |
                   v
             RSA signature
~~~

Khi cùng key và input bytes, scheme tạo cùng chữ ký toán học; implementation có thể dùng RSA blinding khi tính toán mà không đổi kết quả cuối. Chữ ký RSA có kích thước bằng kích thước **modulus** làm tròn lên byte, ví dụ RSA-3072 tạo **384 byte**.

### 3.2. Tại sao không dùng Cipher với private key?

**RSAES-PKCS1-v1_5** và **RSASSA-PKCS1-v1_5** dùng các quy tắc padding khác nhau. Viết **Cipher.getInstance("RSA/ECB/PKCS1Padding")**, “mã hóa” hash bằng private key rồi tự đối chiếu không phải cách triển khai một sơ đồ chữ ký an toàn được chuẩn hóa. Dùng **Signature.getInstance("SHA256withRSA")** để provider xử lý cả hash identifier, padding, kiểm tra lỗi và phép toán ký/xác minh.

### 3.3. Nên dùng ở đâu?

- Hỗ trợ giao thức legacy có profile **RSASSA-PKCS1-v1_5** đã quy định rõ.
- Hệ thống hiện hữu có nhà cung cấp/khóa/cert chỉ hỗ trợ profile tương thích.
- Với thiết kế RSA mới, cân nhắc **RSASSA-PSS** nếu cả hai bên hỗ trợ. RFC 8017 yêu cầu PSS cho các ứng dụng RSA mới trong phạm vi đặc tả và giữ PKCS#1 v1.5 vì compatibility.

Dùng tên thuật toán hash cụ thể như **SHA256withRSA**; không chọn **SHA1withRSA** hay **MD5withRSA** cho scheme mới. Verifier phải kiểm tra nghiêm ngặt cả cấu trúc padding, không tự viết parser “tìm hash ở cuối block”.

## 4. RSASSA-PSS: RSA signature với salt và mask generation

RSA-PSS dùng **EMSA-PSS** để tạo encoded message từ hash thông điệp, salt và **mask generation function (MGF)**. Salt ở PSS là tham số cho từng phép ký, **khác với salt của password hashing**. Salt PSS không cần được lưu riêng cạnh chữ ký theo profile chuẩn; verifier kiểm tra trong cấu trúc encoded message.

~~~text
message M ----> Hash(M) --------+
                               |
salt ngẫu nhiên ----------------+--> EMSA-PSS-ENCODE
                                    (MGF1, saltLength, trailer)
                                                |
                                                v
                                      RSA private-key operation
                                                |
                                                v
                                           PSS signature
~~~

PSS thường tạo ra **chữ ký khác nhau** khi ký cùng message/key vì salt thay đổi; vẫn verify đúng với cùng profile tham số.

### 4.1. Các tham số cần chốt chính xác

| Tham số | Profile minh họa | Ý nghĩa |
| --- | --- | --- |
| Hash | **SHA-256** | Hash thông điệp dùng trong PSS. |
| MGF | **MGF1** | Mask generation function. |
| MGF digest | **SHA-256** | Hash của MGF1; phải khai báo riêng. |
| Salt length | **32 byte** | Thường bằng SHA-256 output trong profile này; không mặc định cho mọi profile. |
| Trailer field | **1** | Giá trị tham số JCA tương ứng trailer 0xBC. |
| RSA modulus | 3072 bit | Kích thước RSA đủ cho profile đã chọn. |

Ví dụ trong một method đã có rsaPrivateKey và messageBytes:

~~~java
PSSParameterSpec pss = new PSSParameterSpec(
        "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);

Signature signer = Signature.getInstance("RSASSA-PSS");
signer.setParameter(pss);
signer.initSign(rsaPrivateKey);
signer.update(messageBytes);
byte[] signature = signer.sign();
~~~

Đây là **mảnh minh họa**, không phải lớp Java độc lập; cần import java.security.* và java.security.spec.*. Code chạy hoàn chỉnh ở phần thực hành.

Trong Java, **PSSParameterSpec** có thứ tự **digestAlgorithm, mgfAlgorithm, mgfParameters, saltLen, trailerField**. **RSASSA-PSS** là tên algorithm, **không đủ** tự quy định SHA-256/MGF1-SHA256/salt 32/trailer 1. Cần cấu hình đầy đủ ở bên ký và verify, lưu profile theo version và key ID; không dựa vào default của provider.

### 4.2. Không tự fallback PSS params

Nếu chữ ký được tạo với saltLength=32 nhưng verifier mong saltLength=20, xác minh phải thất bại. Tùy provider, có thể nhận **verify(false)** hoặc lỗi tham số. Không tự thử giảm salt hoặc chuyển sang v1.5 cho đến khi kết quả khớp. Nếu buộc phải hỗ trợ nhiều profile legacy, server phải có **allowlist cố định theo key/version**, không cho message chưa xác thực quyết định mức bảo mật.

### 4.3. Dùng cùng một cặp khóa RSA cho PSS và v1.5?

Một RSA key có thể tương thích cả hai scheme nếu key usage/provider cho phép, nhưng **chữ ký không tương thích**. Thiết kế nên tách hoặc ràng buộc **key ID ↔ scheme/hash/params/purpose** để tránh algorithm confusion. HSM có thể chặn một số scheme/saltLength ngay cả khi khóa về mặt toán học là RSA.

## 5. ECDSA: chữ ký trên elliptic curve

### 5.1. Curve, hash và nonce ký

**ECDSA** dùng private scalar và public point trên một **elliptic curve Weierstrass**. Một profile phổ biến:

- Key algorithm: **EC**.
- Curve: **secp256r1** (NIST P-256).
- Hash: **SHA-256**.
- Signature algorithm: **SHA256withECDSA**.
- Chữ ký toán học: một cặp số nguyên **(r,s)**.

Khi tạo chữ ký, ECDSA cần một giá trị **nonce ký k**, bí mật và được tạo đúng theo yêu cầu của thuật toán. **Tái sử dụng k giữa các message khác nhau dưới cùng private key, hoặc k bị đoán/bias**, có thể dẫn tới lộ private key. Đừng tự triển khai nonce bằng timestamp, Random hoặc counter ứng dụng; dùng provider mật mã được kiểm chứng. Một số ECDSA implementation sử dụng nonce xác định theo RFC 6979, nhưng Java không bảo đảm mọi provider đều ký deterministic theo RFC 6979.

~~~text
message M + private key d + nonce k trên curve
              |
              v
       ECDSA signature (r,s)
              |
              v
   encode r,s thành DER hoặc P1363 bytes
~~~

**Không tự băm message trước** khi gọi **Signature.getInstance("SHA256withECDSA")**, vì tên đó đã gồm SHA-256. Nếu đưa SHA256(message) vào update, bạn đang ký một **message khác** và tạo ra hành vi double-hash không đúng profile thông thường.

Đoạn minh họa trong một method có biến messageBytes, import java.security.* và java.security.spec.*:

~~~java
KeyPairGenerator gen = KeyPairGenerator.getInstance("EC");
gen.initialize(new ECGenParameterSpec("secp256r1"));
KeyPair keys = gen.generateKeyPair();

Signature signer = Signature.getInstance("SHA256withECDSA");
signer.initSign(keys.getPrivate());
signer.update(messageBytes);
byte[] derSignature = signer.sign();
~~~

**Curve quan trọng:** một public key thuộc P-256 không tự nhiên tương thích với curve P-384 hoặc Ed25519. Không suy ra mọi khóa có tên “EC” đều dùng cho mọi curve/profile. Signature.verify cần public key đúng scheme/curve và bytes của message.

### 5.2. Hai encoding của chữ ký ECDSA: DER và IEEE P1363

Đây là nguồn lỗi liên hệ thống rất thường gặp. Cặp toán học (r,s) có thể được mã hóa thành:

| Encoding | Cấu trúc | P-256 | Java Signature name |
| --- | --- | --- | --- |
| **ASN.1 DER** | SEQUENCE chứa hai INTEGER DER là r và s | Độ dài thường quanh 70–72 byte, **có thể thay đổi** | **SHA256withECDSA** |
| **IEEE P1363** | Hai số nguyên big-endian fixed-width, nối **r\|\|s** | **32 byte r + 32 byte s = 64 byte** | **SHA256withECDSAinP1363Format** |

DER INTEGER sử dụng biểu diễn có dấu và có thể cần byte 0x00 ở đầu để không bị coi là âm; vì vậy **không thể chia đôi một chữ ký DER** để lấy r/s. DER còn có các trường length và SEQUENCE. Hãy dùng parser ASN.1 nghiêm ngặt nếu cần chuyển encoding, hoặc chọn đúng JCA algorithm name có **inP1363Format** khi cả phía triển khai hỗ trợ.

JWS **ES256** trong JOSE dùng ECDSA P-256 + SHA-256 nhưng chữ ký trên wire là **P1363 raw 64 byte**; Java **SHA256withECDSA** thường trả về DER. Nếu hai bên không quy định rõ định dạng, verify sẽ thất bại dù khóa, curve và message đúng.

### 5.3. Tính không duy nhất và quy tắc low-S

Trong một số profile ECDSA, cả (r,s) và (r,n−s) đều có thể là chữ ký toán học hợp lệ cho cùng một message (với n là order của nhóm). Một số giao thức yêu cầu **low-S canonicalization** để giới hạn biến thể chữ ký. Không giả định Signature.verify của mọi Java provider tự áp quy tắc này. Nếu giao thức cần low-S, phải kiểm tra theo **quy định cụ thể của giao thức** và có negative tests.

## 6. EdDSA: Ed25519 và Ed448

### 6.1. EdDSA khác ECDSA ở đâu?

**EdDSA** (RFC 8032) sử dụng Edwards curves. Hai profile nổi bật:

| Profile | Curve | Raw public key (thuật toán) | Signature | Ghi chú |
| --- | --- | --- | --- | --- |
| **Ed25519** | edwards25519 | 32 byte | 64 byte | Mức bảo mật cổ điển khoảng 128-bit theo profile. |
| **Ed448** | edwards448 | 57 byte | 114 byte | Mức bảo mật cổ điển cao hơn, khoảng 224-bit. |

Đây là kích thước **raw key theo RFC**; key khi lưu dạng **SubjectPublicKeyInfo/X.509** có thêm metadata ASN.1 nên byte file không cùng độ dài raw key. **Ed25519** không phải **X25519**: Ed25519 dùng cho signature, X25519 dùng cho key agreement. Tên cùng có “25519” không có nghĩa khóa và thuật toán có thể thay thế.

**Pure EdDSA deterministic:** ký cùng message bytes với cùng private key theo Ed25519 pure sẽ tạo cùng signature bytes. Thuộc tính này hạn chế một lớp lỗi nonce ngẫu nhiên kiểu ECDSA, nhưng vẫn cần **CSPRNG khi sinh khóa**, bảo vệ khóa riêng, an toàn implementation và xác thực nguồn public key.

### 6.2. Cách dùng Java 17+

Đoạn minh họa trong method có messageBytes và import java.security.*:

~~~java
KeyPairGenerator gen = KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = gen.generateKeyPair();

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(pair.getPrivate());
signer.update(messageBytes);
byte[] signature = signer.sign();

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(pair.getPublic());
verifier.update(messageBytes);
boolean valid = verifier.verify(signature);
~~~

Không cần khai báo **SHA256withEdDSA** hay **PSSParameterSpec**. Tên **Ed25519** đã mô tả scheme cụ thể. Có thể kiểm tra hỗ trợ **Ed448** theo tên Java chuẩn nếu provider và policy cho phép; không đổi từ Ed25519 sang Ed448 một cách im lặng trong giao thức.

### 6.3. Pure Ed25519, Ed25519ph và Ed25519ctx

RFC 8032 còn có:

- **Ed25519 (pure):** ký message theo profile chuẩn.
- **Ed25519ph:** prehash variant theo đúng domain separation/quy tắc RFC.
- **Ed25519ctx:** contextualized variant, có context string tham gia vào phép ký.

Chúng **không tự tương thích với nhau**. Đặc biệt, **SHA-512(message)** rồi gọi **Signature("Ed25519")** không biến phép ký thành Ed25519ph; đó chỉ là ký một chuỗi message khác bằng **pure Ed25519**. Nếu giao thức thực sự yêu cầu ph/ctx, cần implementation hỗ trợ variant đó chính xác.

**Ed25519 deterministic** không có nghĩa phải kiểm tra signature bằng cách ký lại. Nếu người nhận không giữ private key, họ vẫn dùng **Signature.verify** với public key. Chỉ bên giữ private key được phép gọi initSign.

## 7. Tham số, kích thước và format phải phù hợp

| Profile | Key generation | JCA signing | Dạng signature | Điều cần giữ |
| --- | --- | --- | --- | --- |
| **RSA-v1.5 + SHA-256** | RSA 3072-bit | SHA256withRSA | 384 byte với RSA-3072 | Scheme v1.5, digest, key ID. |
| **RSA-PSS + SHA-256** | RSA 3072-bit | RSASSA-PSS | 384 byte với RSA-3072 | SHA-256, MGF1/SHA-256, salt 32 byte, trailer 1. |
| **ECDSA P-256 DER** | EC / secp256r1 | SHA256withECDSA | ASN.1 DER, độ dài thay đổi | Curve P-256, SHA-256, DER. |
| **ECDSA P-256 P1363** | EC / secp256r1 | SHA256withECDSAinP1363Format | Raw r\|\|s = 64 byte | Curve P-256, SHA-256, P1363. |
| **Ed25519 pure** | Ed25519 | Ed25519 | 64 byte | Đúng variant Ed25519 pure, message bytes. |
| **Ed448 pure** | Ed448 | Ed448 | 114 byte | Đúng variant Ed448 pure, message bytes. |

Kích thước RSA được nói bằng **bit modulus**, vì vậy RSA-3072 sinh chữ ký 384 **byte**, không phải 3072 byte. Với ECDSA, format DER có thể dài khác nhau giữa các chữ ký; độ dài đó không phải tiêu chí phân biệt khóa mạnh/yếu.

### 7.1. Tên scheme không phải tên key algorithm

Trong Java:

- **KeyPairGenerator("RSA")** tạo khóa RSA; **Signature("SHA256withRSA")** hoặc **Signature("RSASSA-PSS")** dùng các scheme khác nhau trên khóa RSA phù hợp.
- **KeyPairGenerator("EC")** với **ECGenParameterSpec("secp256r1")** tạo EC key; **Signature("SHA256withECDSA")** ký.
- **KeyPairGenerator("Ed25519")** tạo Ed25519 key; **Signature("Ed25519")** ký.
- **X25519** thuộc KeyAgreement, không phải Signature.

Không dùng “RSA” hoặc “EC” đơn lẻ thay cho một hợp đồng thuật toán chữ ký đã đầy đủ.

## 8. Public key có đúng danh tính không?

**Signature.verify(true)** chỉ cho biết một kết quả **đúng theo public key được cung cấp**. Nếu client gửi public key tự tạo và server lập tức tin đó là ngân hàng hoặc dịch vụ thanh toán, việc verify không có giá trị xác thực danh tính.

Nguồn khóa tin cậy thường là:

1. X.509 certificate với đường chứng thực, key usage, thời hạn, danh tính và chính sách tin cậy được xác minh.
2. JWKS hoặc endpoint khóa từ issuer đã được cấu hình và truy cập qua kênh phù hợp, với quy tắc key ID/rotation.
3. Public key được pin theo đối tác trong cấu hình deployment, secret manager hoặc kho cấu hình đã phân quyền.
4. KMS/HSM quản lý private key ký, còn verifier nhận public key tương ứng qua kênh đáng tin.

**Định dạng khóa và định dạng signature khác nhau.**

| Loại dữ liệu | API hoặc encoding thường gặp | Điều cần nhớ |
| --- | --- | --- |
| Public key xuất/nhập | **X509EncodedKeySpec**, X.509 SubjectPublicKeyInfo | Chuỗi BEGIN PUBLIC KEY thường chứa SPKI Base64; không phải chứng chỉ đầy đủ. |
| Private key có thể xuất | **PKCS8EncodedKeySpec** | Private key cực nhạy cảm, có thể không xuất được từ HSM/KMS. |
| Chứng chỉ X.509 | **CertificateFactory**, X509Certificate | Cần xác minh chain/purpose/danh tính, không chỉ đọc public key. |
| Chữ ký ECDSA DER | **Signature("SHA256withECDSA")** | ASN.1 (r,s), không phải encoding của public key. |
| Chữ ký Ed25519 | **Signature("Ed25519")** | 64-byte raw signature; raw key có định dạng và chiều dài khác. |

**Key.getEncoded() có thể trả null** với khóa không xuất được từ hardware provider. Không giả định mọi khóa Java đều di chuyển được giữa các provider. Với khóa có thể xuất, nhập phải dùng đúng **KeyFactory**, định dạng, thuật toán và chính sách.

## 9. Bytes được ký quyết định kết quả verify

Java **Signature.update(byte[])** nhận byte sequence thực tế; Java object có cùng giá trị nghiệp vụ chưa chắc có cùng bytes.

~~~text
JSON A: {"order":42,"amount":250000}
JSON B: { "amount": 250000, "order": 42 }

Hai biểu diễn có thể mô tả cùng đối tượng,
nhưng byte sequence A và B khác nhau.
Chữ ký trên A không mặc nhiên xác minh được trên B.
~~~

Các lỗi tiêu biểu:

- Bên ký dùng **UTF-8**, bên xác minh chuyển String theo charset khác.
- Bên ký trên **raw HTTP body**, bên nhận parse JSON rồi serialize lại.
- Một phía giữ **newline cuối file**, phía kia loại bỏ.
- Một bên dùng Unicode normalization **NFC**, phía còn lại giữ dạng tổ hợp ký tự.
- Header timestamp, tenant, action hoặc key ID **không nằm trong bytes đã ký** nhưng server lại tin chúng.
- Bên nhận coi **Base64 signature text** như raw signature bytes thay vì decode đúng.
- Bên ký tự **SHA-256 message trước** dù Signature algorithm đã tự hash.

Hãy định nghĩa **canonicalization**, thứ tự trường, delimiter, format version, cách encode timestamp và byte sequence chính xác theo giao thức. Với webhook yêu cầu ký raw request body, phải giữ raw bytes. Không thử hàng loạt cách serialize đến khi tìm được cách verify true.

### 9.1. JWS/JWT và chữ ký Java

| JWS alg | Scheme | Ánh xạ Java |
| --- | --- | --- |
| **RS256** | RSA v1.5 + SHA-256 | **SHA256withRSA** |
| **PS256** | RSA-PSS + SHA-256 | **RSASSA-PSS** với profile SHA-256 / MGF1 SHA-256 / salt 32 byte |
| **ES256** | ECDSA P-256 + SHA-256 | **SHA256withECDSAinP1363Format** cho wire raw r\|\|s nếu provider hỗ trợ; DER thông thường phải chuyển đổi đúng |
| **EdDSA** với Ed25519 | Ed25519 | **Signature.getInstance("Ed25519")** |

JWS signature bảo vệ **bytes của signing input được chuẩn xác theo JWS**, thường gồm encoded header, dấu chấm và encoded payload. Không chỉ ký mỗi JSON payload rồi gọi đó là một chữ ký JWS. Khi triển khai JWT, nên dùng **JOSE/JWT library được duy trì** với allowlist algorithm, key ID, issuer, audience, expiry và chính sách token thay vì tự chế parser hoặc tin header **alg** từ nguồn không đáng tin.

Nếu đã chọn expected algorithm và public key theo policy server, **không để message chưa xác thực điều khiển algorithm fallback** (ví dụ từ PS256 xuống RS256 hay "none") hoặc điều khiển nguồn key một cách tùy ý.

## 10. Java 17+: thực hành ký và verify bốn scheme

Chương trình đầu tiên tạo ba cặp khóa dùng trong một lần chạy: **RSA-3072**, **EC P-256** và **Ed25519**. Nó ký đúng byte của **order=42;amount=250000** rồi thử verify trên message đã sửa thành **order=42;amount=250001**. Mỗi phép ký và verify dùng một **Signature instance riêng**, tránh trộn trạng thái.

Phần cuối còn kiểm tra pure **Ed25519 deterministic** và tình huống **RSA-PSS verify sai saltLength**. Để kết quả stdout không phụ thuộc bytes chữ ký có thể thay đổi, chương trình in boolean và nhãn profile.

Tạo file **SignatureSchemesDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.util.Arrays;

public class SignatureSchemesDemo {
    private static final byte[] MESSAGE =
            "order=42;amount=250000".getBytes(StandardCharsets.UTF_8);
    private static final byte[] ALTERED =
            "order=42;amount=250001".getBytes(StandardCharsets.UTF_8);
    private static final PSSParameterSpec PSS_SHA256 =
            new PSSParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);

    private static Signature engine(String algorithm, boolean pss)
            throws Exception {
        Signature signature = Signature.getInstance(algorithm);
        if (pss) {
            signature.setParameter(PSS_SHA256);
        }
        return signature;
    }

    private static byte[] sign(String algorithm, boolean pss,
            KeyPair keys, byte[] message) throws Exception {
        Signature signature = engine(algorithm, pss);
        signature.initSign(keys.getPrivate());
        signature.update(message);
        return signature.sign();
    }

    private static boolean verify(String algorithm, boolean pss,
            KeyPair keys, byte[] message, byte[] signed) throws Exception {
        Signature verifier = engine(algorithm, pss);
        verifier.initVerify(keys.getPublic());
        verifier.update(message);
        return verifier.verify(signed);
    }

    private static void check(String label, String algorithm, boolean pss,
            KeyPair keys) throws Exception {
        byte[] signed = sign(algorithm, pss, keys, MESSAGE);
        boolean ok = verify(algorithm, pss, keys, MESSAGE, signed);
        boolean changed = verify(algorithm, pss, keys, ALTERED, signed);
        System.out.println(label + ": hợp lệ=" + ok +
                ", sửa nội dung=" + changed);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator rsa = KeyPairGenerator.getInstance("RSA");
        rsa.initialize(3072);
        KeyPair rsaKeys = rsa.generateKeyPair();

        KeyPairGenerator ec = KeyPairGenerator.getInstance("EC");
        ec.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair ecKeys = ec.generateKeyPair();

        KeyPairGenerator ed = KeyPairGenerator.getInstance("Ed25519");
        KeyPair edKeys = ed.generateKeyPair();

        check("PKCS1-v1_5", "SHA256withRSA", false, rsaKeys);
        check("PSS", "RSASSA-PSS", true, rsaKeys);
        check("ECDSA", "SHA256withECDSA", false, ecKeys);
        check("Ed25519", "Ed25519", false, edKeys);

        byte[] signedEd = sign("Ed25519", false, edKeys, MESSAGE);
        byte[] signedAgain = sign("Ed25519", false, edKeys, MESSAGE);
        System.out.println("Ed25519 lặp lại cùng chữ ký: " +
                Arrays.equals(signedEd, signedAgain));

        Signature incompatiblePss = Signature.getInstance("RSASSA-PSS");
        incompatiblePss.setParameter(new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 20, 1));
        incompatiblePss.initVerify(rsaKeys.getPublic());
        incompatiblePss.update(MESSAGE);
        byte[] pssTag = sign("RSASSA-PSS", true, rsaKeys, MESSAGE);
        System.out.println("PSS sai salt length: " +
                incompatiblePss.verify(pssTag));
    }
}
~~~

Biên dịch với JDK có hỗ trợ các profile chuẩn của Java 17:

~~~bash
javac --release 17 -encoding UTF-8 SignatureSchemesDemo.java
java SignatureSchemesDemo
~~~

Stdout trên JDK/provider đã kiểm thử:

~~~text
PKCS1-v1_5: hợp lệ=true, sửa nội dung=false
PSS: hợp lệ=true, sửa nội dung=false
ECDSA: hợp lệ=true, sửa nội dung=false
Ed25519: hợp lệ=true, sửa nội dung=false
Ed25519 lặp lại cùng chữ ký: true
PSS sai salt length: false
~~~

### 10.1. Vì sao ví dụ có giá trị học tập?

1. **RSA-v1.5:** Signature("SHA256withRSA") kết hợp hash + scheme v1.5, dùng RSA key.
2. **RSA-PSS:** Signature("RSASSA-PSS") có **PSSParameterSpec** cụ thể; tham số này được đặt trước khi ký hoặc verify.
3. **ECDSA:** KeyPairGenerator("EC") được khởi tạo trên **secp256r1**, còn Signature dùng **SHA256withECDSA**.
4. **Ed25519:** KeyPairGenerator và Signature cùng profile **Ed25519**, không cần gửi PSS params.
5. **Tamper test:** byte message thay đổi khiến verify false với cùng chữ ký và public key.
6. **Deterministic test:** pure Ed25519 với cùng key/message cho chữ ký giống nhau; việc xác minh hợp lệ vẫn phải dùng Signature.verify.
7. **Wrong PSS params:** bên ký salt 32 byte, bên xác minh salt 20 byte. Trong provider đã chạy, verify false; provider khác có thể từ chối thông số hoặc khóa bằng exception. Không tự fallback.
8. **Private key test-only:** khóa sinh tạm trong bộ nhớ và không in/ghi ra; production cần KeyStore, KMS/HSM, key usage và public-key trust.

**Giới hạn:** không dùng một lần chạy để khẳng định provider nào cũng hỗ trợ. Các khóa mới được tạo ở mỗi lần chạy nên signatures cụ thể có thể khác; chương trình in **trạng thái kiểm tra**, không in signature bytes. Không dùng các khóa được sinh ngẫu nhiên trong demo để đại diện khóa identity production.

## 11. Java 17+: kiểm tra ECDSA DER và P1363

Chương trình thứ hai minh họa trực tiếp sự khác nhau giữa **SHA256withECDSA** (DER) và **SHA256withECDSAinP1363Format** (raw r||s) trên cùng EC P-256 key và cùng message. Mỗi chữ ký được verify bằng chính algorithm có encoding tương ứng. Không so sánh hai chữ ký với nhau vì nonce ECDSA có thể khác.

Tạo file **EcdsaFormatDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;

public class EcdsaFormatDemo {
    private static final byte[] MESSAGE =
            "payload-v1".getBytes(StandardCharsets.UTF_8);

    private static byte[] sign(String algorithm, KeyPair pair)
            throws Exception {
        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(pair.getPrivate());
        signer.update(MESSAGE);
        return signer.sign();
    }

    private static boolean verify(
            String algorithm, KeyPair pair, byte[] signed)
            throws Exception {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(pair.getPublic());
        verifier.update(MESSAGE);
        return verifier.verify(signed);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance("EC");
        gen.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair pair = gen.generateKeyPair();

        byte[] der = sign("SHA256withECDSA", pair);
        byte[] raw = sign("SHA256withECDSAinP1363Format", pair);

        System.out.println("DER ECDSA đúng: " +
                verify("SHA256withECDSA", pair, der));
        System.out.println("P1363 ECDSA đúng: " +
                verify("SHA256withECDSAinP1363Format", pair, raw));
        System.out.println("P1363 P-256 dài 64 byte: " +
                (raw.length == 64));
        System.out.println("DER bắt đầu ASN.1 SEQUENCE: " +
                ((der[0] & 0xff) == 0x30));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EcdsaFormatDemo.java
java EcdsaFormatDemo
~~~

Stdout:

~~~text
DER ECDSA đúng: true
P1363 ECDSA đúng: true
P1363 P-256 dài 64 byte: true
DER bắt đầu ASN.1 SEQUENCE: true
~~~

### 11.1. Cách hiểu đúng

- **SHA256withECDSA** tạo/chấp nhận signature theo **DER ASN.1** với r/s là INTEGER, do đó tổng độ dài có thể biến thiên.
- **SHA256withECDSAinP1363Format** tạo/chấp nhận **raw r||s**. Với P-256, mỗi số nguyên có kích thước 32 byte nên signature dài **64 byte**.
- Byte đầu DER dạng SEQUENCE là **0x30**, nhưng chỉ kiểm tra byte đầu **không phải bộ kiểm tra ASN.1** và không được dùng như security validation. Signature.verify của provider mới là bước xác minh.
- Khi tích hợp với hệ thống khác yêu cầu ES256 raw, không được tự cắt một DER signature thành hai nửa; dùng thư viện DER/P1363 conversion chuẩn hoặc chọn đúng API P1363.
- Không giả định hai lần ký ECDSA trên cùng message phải trả cùng signature bytes.

**Hai chương trình trên là ví dụ hoàn chỉnh có main** và được biên dịch với **javac --release 17**; chỉ những đoạn code nhỏ ở phần lý thuyết mới là mảnh minh họa nằm trong method.

## 12. JCA provider, quản lý khóa và khả năng tương thích

**JCA/JCE là lớp trừu tượng**: Signature, KeyPairGenerator và KeyFactory là engine API; provider thực thi thuật toán. Cùng tên thuật toán không bảo đảm mọi JVM, provider hoặc HSM hỗ trợ **cùng kiểu khóa, curve, PSS params, encoding và thông lượng**.

### 12.1. Những lỗi provider có thể trả

| Triệu chứng Java | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| **NoSuchAlgorithmException** | Provider/JDK không cung cấp tên Signature hoặc KeyPairGenerator | Xác nhận Java version, provider order, tên chuẩn và thuật toán được policy cho phép. |
| **InvalidAlgorithmParameterException** | Curve, saltLength, PSSParameterSpec hoặc tham số khác không được hỗ trợ | Đối chiếu profile chuẩn và khả năng provider/HSM. |
| **InvalidKeyException** | Key sai loại, yếu, từ provider khác hoặc key usage bị cấm | Kiểm tra key type, key size, alias, HSM permissions và chính sách. |
| **SignatureException** | Sai format/chữ ký chưa được khởi tạo/operation không hợp lệ | Kiểm tra DER/P1363, bytes, init mode, input length và provider. |
| **verify(false)** | Sai message, key, params hoặc signature hợp lệ về format nhưng không khớp | Tìm chính xác khác biệt của test vector; không mặc định do tấn công. |
| **Lỗi chỉ xảy ra dưới tải** | Chia sẻ Signature mutable, provider lock/session cạn, key bị rotate giữa request | Tách engine per operation, quản lý phiên HSM và key version nhất quán. |

Khi cần chẩn đoán trong môi trường tin cậy, **Signature.getProvider()** và **Signature.getAlgorithm()** cho biết implementation và tên đã được chọn; nhớ rằng một số engine/provider có thể chọn cài đặt theo khóa khi init. Ghi log tên thuật toán/key ID theo chính sách, tránh log private key, mật khẩu keystore, raw sensitive message và chữ ký chứa thông tin nhạy cảm từ giao thức.

### 12.2. Quy tắc quản lý khóa

1. **Sinh khóa** theo curve, kích thước và nguồn ngẫu nhiên phù hợp; RSA size và EC curve phải được phê duyệt.
2. **Lưu private key** trong cơ chế bảo vệ phù hợp (KeyStore được bảo vệ, HSM/KMS, secret manager) với quyền tối thiểu; không commit private key vào repository hoặc container image.
3. **Phân phối public key** qua kênh có xác thực và gắn đúng issuer/đối tác; không chấp nhận key tùy ý do request gửi đến.
4. **Ràng buộc key ID ↔ thuật toán/scheme/hash/curve/params**; nếu thay khóa, record/token cần xác định version để verify đúng.
5. **Tách mục đích dùng khóa** giữa signature, key agreement và encryption khi chính sách yêu cầu. Đừng dùng Ed25519 như X25519 hoặc dùng RSA private key cho bất kỳ operation nào client chỉ định.
6. **Luân chuyển và thu hồi** với hạn chấp nhận chữ ký cũ rõ ràng. Một chữ ký cũ có thể verify đúng về toán học nhưng vẫn bị từ chối theo thời hạn hoặc revoke.
7. **Bảo vệ key operation** bằng giới hạn tốc độ, giám sát bất thường và xử lý khi khóa bị lộ.

### 12.3. Vì sao cần kiểm tra public key khi dùng certificate?

Một certificate X.509 có public key và thông tin danh tính, nhưng chỉ trích xuất public key rồi gọi Signature.verify **không đồng nghĩa certificate đã đáng tin**. Cần kiểm tra certificate path theo trust anchor, thời gian, mục đích sử dụng, revocation theo chính sách, và danh tính dịch vụ/chủ thể được kỳ vọng. Với JWS/JWT, issuer/audience và trusted JWKS là một phần của quy trình riêng.

## 13. Signature là engine stateful: không dùng chung instance giữa thread

Một đối tượng **java.security.Signature** thay đổi trạng thái qua **initSign/initVerify → update → sign/verify**. Nếu đặt một Signature trong static field của web singleton rồi nhiều request cùng chạy, thao tác của A và B có thể xen lẫn:

~~~text
Không an toàn:
shared.initVerify(keyA)
shared.update(messageA)
                           shared.initVerify(keyB)
                           shared.update(messageB)
shared.verify(sigA)  -> trạng thái không còn thuộc messageA/keyA

Mẫu đơn giản:
request A -> Signature instance riêng -> initVerify A -> update A -> verify A
request B -> Signature instance riêng -> initVerify B -> update B -> verify B
~~~

Tạo **một Signature riêng cho từng lần ký hoặc verify** như hai ví dụ. Không suy diễn rằng vì SecureRandom thread-safe thì Signature cũng có thể chia sẻ. Dùng synchronized từng phương thức riêng lẻ **không bảo vệ cả chuỗi thao tác**; nếu tuần tự hóa toàn bộ chuỗi, lại làm mất lợi ích của concurrency.

Một public key object/key handle có thể được tái sử dụng nếu provider cho phép, nhưng khác hoàn toàn với chia sẻ **engine đang giữ message state**. Với HSM, còn cần session pool, timeout và backpressure; không nên “tối ưu” bằng cách tái sử dụng Signature mutable một cách không kiểm soát.

## 14. Kiểm tra message và signature trước khi xử lý nghiệp vụ

Một quy trình nhận webhook có chữ ký, gói phát hành hoặc token có thể gồm:

1. **Giới hạn kích thước request**, parse envelope/version, nhận signature bytes và key ID đúng định dạng.
2. Xác định **issuer/đối tác mong đợi và thuật toán được phép** từ cấu hình server. Không dùng alg từ dữ liệu chưa xác thực để tự mở rộng allowlist.
3. Lấy **trusted public key** theo key ID được phép; kiểm tra trạng thái và quyền sử dụng khóa.
4. Chuẩn bị **message bytes** theo giao thức đã quy định, giữ nguyên raw body hoặc canonical encoding; bảo vệ metadata ảnh hưởng nghiệp vụ.
5. Dùng **Signature.getInstance** đúng algorithm/params/encoding, initVerify, update bytes và verify.
6. Nếu verify false hoặc dữ liệu/format/algorithm không hợp lệ, **từ chối**; không thực hiện giao dịch hoặc phát quyền.
7. Nếu verify true, kiểm tra **thời hạn, issuer, audience, replay/idempotency, phân quyền và trạng thái nghiệp vụ** trước tác động.
8. Log request ID, key ID, profile và lý do kỹ thuật ở mức cho phép; phản hồi bên ngoài không làm lộ bí mật hoặc trạng thái nhạy cảm không cần thiết.

**Cảnh báo về replay:** kẻ tấn công có thể gửi lại nguyên payload và signature hợp lệ. Chữ ký sẽ tiếp tục verify đúng; ứng dụng phải có cơ chế freshness, nonce, thời gian, transaction ID và idempotency theo yêu cầu. Đặc biệt, timestamp hoặc nonce dùng chống replay cần được gắn với bytes đã ký hoặc ngữ cảnh tin cậy.

## 15. Quy tắc chọn scheme

| Bài toán | Lựa chọn thực tiễn | Tiêu chí quyết định |
| --- | --- | --- |
| Tích hợp hệ thống RSA legacy | **SHA256withRSA / RSASSA-PKCS1-v1_5** nếu policy cho phép | Hệ thống đối tác hỗ trợ profile v1.5 và có kế hoạch migration. |
| Thiết kế API signature RSA mới | **RSASSA-PSS** | Hai bên thống nhất đầy đủ SHA/MGF/saltLength/trailer, key size và provider. |
| Hệ sinh thái ECDSA P-256 | **SHA256withECDSA**, DER hoặc P1363 phù hợp | Curve, hash, encoding on-wire, quản lý nonce và provider. |
| API hoặc gói phần mềm hỗ trợ Ed25519 | **Signature("Ed25519")** | Pure Ed25519 đúng chuẩn, key distribution, provider/HSM compatibility. |
| Hệ thống có FIPS/PKI/HSM cụ thể | Scheme được policy/phần cứng cho phép | Chứng nhận, key usage, thuật toán, key size và latency triển khai. |

Không chọn theo một bảng xếp hạng “thuật toán mới luôn tốt hơn”; cần đối chiếu **giao thức bắt buộc, khuyến nghị chuẩn, yêu cầu an toàn và khả năng bảo vệ khóa**. RSA-PSS là lựa chọn mạnh cho ứng dụng RSA mới; Ed25519 gọn và tiện cho nhiều ứng dụng hiện đại nhưng không thể thay thế một profile RSA/ECDSA mà bên nhận đã cố định.

**Không tự chuyển sang NONEwithRSA, NONEwithECDSA, băm tay rồi ký raw, hoặc dùng Cipher để giả lập Signature** chỉ vì hai bên đang có lỗi tương thích.

## 16. Bộ kiểm thử cần có

| Ca kiểm thử | Input hoặc tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Đúng profile | Message, signature, public key, params khớp | **verify true**. |
| Message bị sửa | Thay một byte, giữ signature cũ | **verify false**. |
| Chữ ký bị sửa | Thay byte signature hoặc dùng signature của message khác | Từ chối hoặc lỗi format được xử lý an toàn. |
| Public key sai | Dùng key cùng scheme nhưng của issuer khác | Không chấp nhận. |
| PKCS1-v1_5 vs PSS | Ký SHA256withRSA, verify RSASSA-PSS hoặc ngược lại | Không chấp nhận. |
| PSS salt sai | Ký salt=32, verify salt=20 | Từ chối/false hoặc lỗi tham số. |
| PSS MGF sai | Một bên SHA-256 với MGF1-SHA256, bên kia dùng MGF1-SHA1 | Không chấp nhận. |
| ECDSA DER vs P1363 | DER gửi cho verifier expecting raw r\|\|s | Từ chối; cần conversion theo chuẩn. |
| ECDSA malformed | DER r/s không hợp lệ, wrong length | Từ chối với lỗi kiểm soát, không dùng parser lỏng lẻo. |
| Ed25519 deterministic | Ký pure Ed25519 hai lần trên cùng key/message | Cùng signature bytes. |
| Ed25519 variant sai | Message raw vs message đã prehash tùy tiện | Không tương thích. |
| Unicode/JSON | Khác whitespace, charset, normalization | Chữ ký raw bytes cũ không khớp nếu bytes thay đổi. |
| Provider matrix | Ký Java A, verify Go/OpenSSL/Java B với cùng vector | Phải cùng kết quả theo profile chuẩn. |
| Key rotation | Key ID cũ/mới, revoked key | Chấp nhận/từ chối theo version và policy. |
| Replay | Gửi lại message+signature đã hợp lệ | Signature có thể vẫn true; nghiệp vụ phải xử lý idempotent. |
| Concurrency | Nhiều requests song song với keys/messages khác nhau | Không trộn Signature state; throughput được kiểm soát. |
| Key permissions | Key handle không export hoặc bị chặn operation | Xử lý lỗi đúng, không dùng private key không được phép. |

**Test vector có giá trị** nên giữ message bytes gốc dưới dạng hex/file, algorithm, hash, curve/PSS params, public key test, signature bytes đúng encoding và expected result. Có thể tái chạy trên nhiều provider để tìm lỗi interoperability. Không đưa private key thật vào test repo.

### 16.1. Phân biệt lỗi đúng nghĩa

- **verify(false)**: message/key/params/signature không khớp trong phép kiểm tra đã thực hiện.
- **NoSuchAlgorithmException / InvalidKeyException**: thuật toán hoặc khóa không được provider chấp nhận; cần chẩn đoán kỹ thuật, không tự hạ thuật toán.
- **SignatureException**: có thể do trạng thái engine, input/encoding hoặc cài đặt; không suy luận chắc chắn có tấn công chỉ từ exception.
- **Certificate/replay/policy failure**: verify có thể true nhưng hệ thống vẫn phải từ chối vì danh tính hoặc quyền sử dụng không đáp ứng.

Với lỗi chữ ký, không log private key, raw token nhạy cảm, payload bí mật hoặc phản hồi chi tiết cho client khiến lộ trạng thái nội bộ.

## 17. Các sai lầm hay gặp

1. **Nhầm RSASSA-PKCS1-v1_5 với RSAES-PKCS1-v1_5.** Ký bằng Signature API, không dùng Cipher để tự làm RSA signature.
2. **Dùng SHA256withRSA để xác minh PSS.** Hai scheme khác nhau dù cùng RSA key.
3. **Không khai báo đầy đủ PSSParameterSpec.** Hash/MGF/salt/trailer có thể khác provider hoặc bên gửi.
4. **Tự động giảm PSS saltLength khi verify lỗi.** Đây là thay đổi chính sách an toàn ngoài giao thức.
5. **Chọn SHA1withRSA/MD5withRSA cho thiết kế mới.** Không dùng hash yếu khi đã có profile phù hợp hơn.
6. **Tự sinh nonce ECDSA bằng Random hoặc timestamp.** Lỗi nonce có thể làm mất private key.
7. **Cắt DER signature thành hai nửa rồi gọi P1363.** ASN.1 DER không phải raw r||s.
8. **Băm message trước SHA256withECDSA hoặc Ed25519.** Tạo input khác hoặc sai variant, thường dẫn đến mismatch.
9. **Nhầm Ed25519 với X25519.** Signature và key agreement có key type/operation riêng.
10. **Dùng public key tự gửi từ client như danh tính đáng tin.** Verify true chưa chứng minh thuộc đối tác cụ thể.
11. **Tin alg trong JWT vô điều kiện.** Không có allowlist scheme và key policy dẫn đến algorithm confusion.
12. **Không ký metadata nghiệp vụ.** Có thể thay tenant/action/timestamp bên ngoài phạm vi xác thực.
13. **So chữ ký bằng equals với chữ ký vừa tạo.** PSS/ECDSA có thể ngẫu nhiên; Signature.verify mới đúng.
14. **Chia sẻ Signature instance ở singleton.** init/update/verify có thể bị xen lẫn giữa nhiều thread.
15. **Lưu private key trong source, log hoặc file công khai.** Kẻ lấy được khóa có thể tạo chữ ký đúng.
16. **Không xử lý replay/authorization.** Chữ ký hợp lệ không chứng minh lệnh được phép hay chưa xử lý.
17. **Không lưu format version, key ID và params.** Khi đổi provider hoặc rotate khóa dễ không đọc/verify được dữ liệu cũ.

## 18. Tự kiểm tra kiến thức

**Câu 1.** Java **SHA256withRSA** dùng v1.5 hay PSS?  
**Trả lời:** RSASSA-PKCS1-v1_5 với SHA-256. PSS dùng **RSASSA-PSS** và PSSParameterSpec.

**Câu 2.** RSA-PSS SHA-256 ký với saltLength=32; verifier dùng saltLength=20 và đúng RSA public key. Có thể chấp nhận không?  
**Trả lời:** Không. **Tham số scheme khác nhau**; phải từ chối hoặc xử lý lỗi theo provider, không tự hạ tham số.

**Câu 3.** Vì sao hai chữ ký ECDSA trên cùng message có thể khác nhau?  
**Trả lời:** Do nonce ký k; nhiều implementation chọn k mới mỗi lần ký. Cả hai đều có thể hợp lệ và phải dùng Signature.verify.

**Câu 4.** Dịch vụ JWS ES256 đòi 64 bytes raw r||s nhưng Java tạo DER. Cần làm gì?  
**Trả lời:** Chọn **SHA256withECDSAinP1363Format** nếu hỗ trợ hoặc dùng converter DER/P1363 đúng chuẩn, đồng thời giữ cùng curve/hash/bytes.

**Câu 5.** Với pure Ed25519, vì sao không SHA-512(message) trước khi gọi Signature("Ed25519")?  
**Trả lời:** Vì Ed25519 đã có xử lý hash nội bộ. Prehash thủ công sẽ ký một message khác, không tự biến nó thành Ed25519ph.

**Câu 6.** Server nhận message, signature và public key do cùng client gửi, verify true; đã đủ để coi client là tổ chức X chưa?  
**Trả lời:** Chưa. Phải xác thực public key thực sự gắn với tổ chức X theo trust policy.

**Câu 7.** Chữ ký gói thanh toán đúng nhưng bị phát lại từ hôm qua; kiểm tra chữ ký có tự chặn không?  
**Trả lời:** Không. Thêm timestamp/nonce, transaction ID, freshness và idempotency được ràng buộc với thông điệp.

**Câu 8.** RSA-3072 có chữ ký dài khoảng bao nhiêu?  
**Trả lời:** **384 byte** với cả RSA v1.5 và PSS. 3072 là **bit modulus**.

**Câu 9.** Một Signature object có được dùng cho cả request A và B đồng thời không?  
**Trả lời:** Không nên: object có trạng thái init/update/sign/verify. Mỗi tác vụ sở hữu engine riêng.

**Câu 10.** Ed25519 và X25519 khác nhau ở đâu?  
**Trả lời:** Ed25519 là chữ ký số, X25519 là trao đổi khóa; không tự coi chúng là một key type hoặc một giao thức.

## 19. Kết luận và nguồn tham khảo

**PKCS#1 v1.5** giải quyết nhu cầu tương thích RSA signature với profile cổ điển; **RSA-PSS** cần bộ tham số chính xác và được ưu tiên cho ứng dụng RSA mới; **ECDSA** yêu cầu nonce ký an toàn, curve và **DER/P1363** đúng format; **EdDSA** có các profile **Ed25519/Ed448** khác ECDSA và có pure variant deterministic. Tất cả chỉ có giá trị khi **message bytes, algorithm/params, trust của public key, quản lý private key và xử lý replay/authorization** đều đúng.

Nguồn kỹ thuật:

- [RFC 8017 — PKCS #1 v2.2, RSASSA-PKCS1-v1_5 và RSASSA-PSS](https://www.rfc-editor.org/rfc/rfc8017.html)
- [RFC 8032 — EdDSA (Ed25519, Ed448)](https://www.rfc-editor.org/rfc/rfc8032.html)
- [NIST FIPS 186-5 — Digital Signature Standard](https://csrc.nist.gov/pubs/fips/186-5/final)
- [Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html)
- [Java SE 17 — Signature API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html)
- [Java SE 17 — PSSParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html)
- [Java SE 17 — ECGenParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/ECGenParameterSpec.html)
- [RFC 7518 — JWA, RS256/PS256/ES256](https://www.rfc-editor.org/rfc/rfc7518.html)
- [RFC 8037 — EdDSA in JOSE](https://www.rfc-editor.org/rfc/rfc8037.html)