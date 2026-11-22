# Lựa chọn thuật toán được chấp nhận trên JDK hiện đại cho chữ ký XML (Java 17+)

## 1. “Thuật toán được chấp nhận” nghĩa là gì?

Khi ứng dụng ký hoặc xác minh một tài liệu XML, vấn đề không chỉ là chọn `SHA-256` hay kiểm tra xem Java có class `SignatureMethod` hay không. Một bộ thuật toán phù hợp phải đồng thời thỏa:

1. **Độ an toàn mật mã:** thuật toán ký, digest, khóa và tham số đủ mạnh cho thời hạn bảo vệ dữ liệu.
2. **Khả năng của runtime:** JDK version và Java Cryptography Architecture (JCA) provider thực sự triển khai chúng.
3. **XML Signature specification:** thuật toán có **URI chuẩn** và được `XMLSignatureFactory` hỗ trợ cho `SignatureMethod`/`DigestMethod`/`CanonicalizationMethod`/`Transform`.
4. **Chính sách xác minh:** các thuật toán không bị `secureValidation` và `jdk.xml.dsig.secureValidationPolicy` hoặc cấu hình tổ chức chặn.
5. **Tương tác hệ thống:** đối tác, gateway, HSM, trust service và tài liệu profile chữ ký sử dụng đúng thuật toán, biến thể và cách biểu diễn.
6. **Độ tin cậy của khóa ký:** public key/certificate dùng xác minh được **tin cậy theo nguồn ngoài**; không lấy một khóa tùy ý do chính XML tự khai để làm bằng chứng danh tính.
7. **Đối tượng được bảo vệ:** chính dữ liệu nghiệp vụ mà ứng dụng xử lý nằm trong các `Reference` đã xác minh, tránh signature wrapping và chọn nhầm node.

Vì thế có ba câu hỏi khác nhau:

- **JDK có hằng số thuật toán?** Ví dụ `SignatureMethod.RSA_SHA256` là URI được API công bố.
- **Provider có dùng được?** `XMLSignatureFactory.newSignatureMethod(...)` có thể thành công, nhưng việc ký/xác minh còn cần key type, JCA provider và tham số thích hợp.
- **Ứng dụng có nên cho phép?** Chỉ những thuật toán trong **allowlist chính sách hiện hành** mới được ký/xác minh, kể cả khi provider còn hỗ trợ giải mã một thuật toán cũ.

**Mặc định khuyến nghị để bắt đầu với Java 17+:** một hệ thống XMLDSig mới có thể dùng **RSA-SHA256** với RSA ≥ 2048 bit (thường chọn RSA-3072 nếu phù hợp kế hoạch vòng đời khóa), **ECDSA-SHA256** với đường cong NIST P-256 (`secp256r1`), hoặc **RSA-PSS/SHA-256** khi các bên xác nhận khả năng tương tác. Digest của các `Reference` thường dùng **SHA-256**; mức mạnh hơn có thể dùng SHA-384/SHA-512 theo profile. Đối với JDK 21+, có thể cân nhắc **Ed25519** nếu mọi bên hỗ trợ XMLDSig EdDSA. Đây là lựa chọn kỹ thuật phổ biến, **không phải danh sách “được phép ở mọi cơ quan/quốc gia/chế độ FIPS”**.

**Không phát hành chữ ký XML mới bằng SHA-1 hoặc MD5.** Các thuật toán ấy không đáp ứng chính sách bảo mật hiện đại cho chữ ký mới; JDK secure-validation mode cũng có các hạn chế đối với XML signatures chứa SHA-1/MD5. `SignatureMethod.RSA_SHA1` tồn tại trong API vì lý do khả năng nhận diện tài liệu cũ, **không** có nghĩa đây là lựa chọn được khuyến nghị.

Bài này dùng `java.xml.crypto` và `java.xml` của Java 17+; không yêu cầu thư viện XML signature legacy. Khi tổ chức có policy riêng hoặc hệ thống ký số chuyên ngành, chính **policy đã được phê duyệt**, chứng thư, key usage và yêu cầu tuân thủ mới quyết định lựa chọn cuối cùng.

## 2. Bốn tầng thuật toán trong một XML Signature

Một XML digital signature có nhiều thành phần mật mã/XML xử lý, không phải “một thuật toán”:

```text
         XML document / signed objects
                    |
          Reference URI (chỉ dữ liệu nào)
                    |
         Transforms (enveloped, C14N...)
                    |
          DigestMethod: SHA-256
                    |
          DigestValue trong Reference
                    |
     SignedInfo chứa các Reference và metadata
                    |
 CanonicalizationMethod của SignedInfo: Exclusive C14N
                    |
 SignatureMethod: RSA-SHA256 / RSA-PSS / ECDSA-SHA256
                    |
             Private key ký
                    |
            SignatureValue
                    |
       Xác minh bằng public key đáng tin
```

| Phần tử XMLDSig | Java API | Nhiệm vụ | Chọn theo cái gì? |
| --- | --- | --- | --- |
| `Reference URI` | `XMLSignatureFactory.newReference` | Chỉ tài nguyên hoặc node-set nào được digest. | Cố định nội dung mục tiêu, same-document references, xác thực ID/URI. |
| `Transforms` | `Transform`, `TransformService` | Biến đổi tập dữ liệu trước khi digest. | Chỉ dùng các transforms cần thiết, theo allowlist. |
| `DigestMethod` | `DigestMethod.SHA256` | Hash **nội dung Reference sau transforms**. | SHA-256/384/512 theo yêu cầu. |
| `CanonicalizationMethod` | `CanonicalizationMethod.EXCLUSIVE` | Chuẩn hóa `SignedInfo` thành bytes để ký. | C14N tương thích hai bên và đúng namespace semantics. |
| `SignatureMethod` | `SignatureMethod.RSA_SHA256` | Ký bytes của SignedInfo đã canonicalize. | Thuật toán khóa công khai/HMAC, độ mạnh, provider và peer. |
| `KeyInfo` | `KeyInfoFactory`, `X509Data`, `KeyValue` | Chứa gợi ý nhận dạng/khóa để verify. | Không tự hình thành trust; xác minh qua truststore/PKI policy. |

**DigestMethod khác SignatureMethod:**
- `DigestMethod.SHA256` không cung cấp chữ ký số: bất cứ ai cũng tính SHA-256 của dữ liệu.
- `SignatureMethod.RSA_SHA256` xác thực `SignedInfo` bằng private RSA key và thuật toán ký phù hợp.
- Khi tài liệu bị sửa, digest của `Reference` không khớp; khi `SignedInfo` hoặc signature bị sửa, kiểm tra chữ ký không khớp.
- **Một `XMLSignature.validate(...)` trả true vẫn chưa chứng minh người ký được cấp phép hoặc dữ liệu nghiệp vụ chính xác đã được ký.** Cần thêm trust và signed-object selection.

**URI XMLDSig không đồng nhất với chuỗi JCA.** Ví dụ:
- XMLDSig: `SignatureMethod.RSA_SHA256` chứa URI kiểu `http://www.w3.org/2001/04/xmldsig-more#rsa-sha256`.
- JCA: `Signature.getInstance("SHA256withRSA")` dùng tên thuật toán JCA.
- XMLDSig provider ánh xạ URI sang JCA implementation phù hợp; code không lấy chuỗi `"SHA256withRSA"` làm `SignatureMethod` URI.

## 3. Các thuật toán ký nên cân nhắc trên JDK 17+

### 3.1. RSA-SHA256 — lựa chọn interoperable khi đối tác hỗ trợ

```java
SignatureMethod method = factory.newSignatureMethod(
        SignatureMethod.RSA_SHA256, null);
```

Đây là **snippet** trong method; cần `XMLSignatureFactory factory` và import `javax.xml.crypto.dsig.SignatureMethod`. Được hỗ trợ trong Java 17+ qua XMLDSig chuẩn. Đây là RSA signature với SHA-256 (PKCS#1 v1.5 signature encoding theo URI XMLDSig), **không phải RSA encryption** và không dùng `Cipher`.

Khuyến nghị:
- Khóa RSA **ít nhất 2048 bit** cho công việc mới; nhiều hệ thống chọn **3072 bit** nếu muốn biên an toàn dài hơn hoặc policy yêu cầu.
- Không dùng RSA-1024 dù một số JDK secure-validation default thresholds có thể chỉ từ chối khóa **nhỏ hơn 1024**. Ngưỡng của runtime không phải chuẩn thiết kế khóa mới.
- Public key dùng xác minh phải đến từ nguồn trust độc lập. Chỉ thấy `KeyValue`/`X509Data` trong XML không đủ.
- Đây là lựa chọn phổ biến nếu partner/enterprise PKI chưa hỗ trợ RSA-PSS hoặc EdDSA.

**Khi nào không nên chọn?** Nếu chính sách tổ chức yêu cầu RSA-PSS, curve-based signature, FIPS profile cụ thể hoặc giấy chứng nhận chuẩn chuyên ngành không chấp nhận PKCS#1 v1.5 cho chữ ký mới, phải theo policy đó. Không suy từ “được API hỗ trợ” thành “được chấp nhận theo mọi tiêu chuẩn”.

### 3.2. RSA-PSS / SHA-256 — khuyến nghị khi profile cho phép

Từ Java 17, XMLDSig JSR 105 có `SignatureMethod.RSA_PSS`. Javadoc quy định nếu tạo bằng `factory.newSignatureMethod(SignatureMethod.RSA_PSS, null)`, **tham số mặc định theo RFC 6931** gồm:
- Digest SHA-256.
- Mask Generation Function MGF1 với SHA-256.
- Salt length 32 bytes.
- Trailer field 1.

```java
SignatureMethod pssMethod =
        factory.newSignatureMethod(SignatureMethod.RSA_PSS, null);
```

**Điểm cần kiểm tra:** RSA-PSS có nhiều cách xác định tham số/URI trong các XMLDSig profiles; đừng giả định chỉ vì bên kia nói “RSA-PSS” thì họ sẽ hiểu chính xác XML `SignatureMethod` này. Cần thống nhất **URI, digest, MGF, saltLength, trailerField, key type và CanonicalizationMethod** với hệ thống nhận. Ví dụ hoàn chỉnh ở mục 8 đã ký/xác minh RSA-PSS/SHA-256 thành công trên JDK được thử nghiệm.

Một biến thể XMLDSig khác là `SignatureMethod.SHA256_RSA_MGF1` (đã tồn tại từ Java 11), mã hóa SHA-256/RSA-MGF1 ngay trong URI. Không tự thay thế hai URI lẫn nhau khi profile đối tác chỉ chấp nhận một loại. **Dùng đúng thuật toán được hợp đồng/profile chấp nhận**, dù cả hai có thể dùng cơ chế RSA-PSS ở tầng JCA.

### 3.3. ECDSA-SHA256 trên P-256 — ngắn gọn, hiệu quả

```java
SignatureMethod ecMethod = factory.newSignatureMethod(
        SignatureMethod.ECDSA_SHA256, null);
```

Khóa EC được tạo/tải với **`secp256r1`** (NIST P-256). Với tài liệu cần mức an toàn cao hơn và peer có hỗ trợ, có thể cân nhắc ECDSA-SHA384 + P-384 theo policy, nhưng luôn kiểm tra interop và key agreement với đối tác.

Lợi ích:
- Chữ ký và khóa công khai thường gọn hơn RSA cùng mục tiêu độ an toàn.
- Hợp với hạ tầng PKI/hardware hỗ trợ ECDSA.
- `SignatureMethod.ECDSA_SHA256` và `ECDSA_SHA384` đã có trên JDK 17.

Lưu ý:
- **ECDSA không dùng khóa RSA**; `InvalidKeyException` hoặc lỗi provider có thể phát sinh nếu truyền sai key type.
- Khi tự quản lý ECDSA keys ngoài JCA provider an toàn, chất lượng nonce/implementation có ý nghĩa bảo mật rất lớn. Không tự viết ECDSA hoặc dùng random generator tùy tiện; dựa trên JCA/HSM được đánh giá.
- ECDSA XMLDSig signature encoding phải phù hợp profile, không tự nối format ASN.1 DER và XMLDSig signature value bằng tay.

### 3.4. Ed25519 — chỉ bắt đầu từ API XMLDSig Java 21+

`SignatureMethod.ED25519` và `SignatureMethod.ED448` được bổ sung **từ Java 21** vào JDK XMLDSig API. Điều này khác với việc một bản JDK có JCA `KeyPairGenerator.getInstance("Ed25519")`.

- **Java 17:** không dùng `SignatureMethod.ED25519` trong code compile target 17 vì constant XMLDSig này chưa có.
- **Java 21/25+:** có thể dùng XMLDSig `SignatureMethod.ED25519` khi provider và hệ thống đối tác hỗ trợ đúng URI/verification.
- **Không xem Ed25519 là lựa chọn cho mọi bộ tiêu chuẩn:** chứng thư, PKI, profile XMLDSig và yêu cầu cơ quan/country có thể chưa chấp nhận.
- Ed25519 dùng cơ chế EdDSA riêng; không đặt `"SHA256withEd25519"` như thể đó là URI chuẩn. `Reference` vẫn có thể dùng `DigestMethod.SHA256` như phần riêng của XMLDSig.
- Mục 9 có chương trình biên dịch bằng `--release 21` và ký/xác minh bằng XMLDSig Ed25519 trên JDK thử nghiệm.

### 3.5. HMAC-SHA256 — phù hợp trust model dùng bí mật chung

`SignatureMethod.HMAC_SHA256` là một **MAC** trên `SignedInfo`. Có thể phù hợp khi hai thành phần backend có một symmetric secret được quản lý an toàn và cùng tin cậy nhau.

**Nhưng đây không phải chữ ký công khai độc lập:** cả hai bên biết shared secret có thể tạo MAC; không thể quy trách nhiệm cho một người ký riêng biệt như chữ ký bất đối xứng. Không dùng HMAC thay RSA/ECDSA/EdDSA trong hồ sơ đòi hỏi PKI, kiểm chứng bởi bên thứ ba hoặc non-repudiation. Secret phải có entropy phù hợp, quản lý bằng KMS/secret vault, xoay vòng và giới hạn phạm vi.

`HMAC_SHA1` tuy là hằng còn xuất hiện trong API **không phải lựa chọn mới**. Chỉ sử dụng HMAC-SHA256 hoặc các SHA-2 variants theo policy.

## 4. Bảng lựa chọn thực tế theo JDK và yêu cầu

| XMLDSig signature method | JDK XMLDSig | Dạng khóa | Phù hợp khi | Điều kiện |
| --- | --- | --- | --- | --- |
| `SignatureMethod.RSA_SHA256` | Java 17+ | RSA ≥2048 bit; thường 3072 trong chính sách mới. | Enterprise interop phổ biến. | Partner cho RSA PKCS#1 v1.5 signatures; trusted key. |
| `SignatureMethod.RSA_SHA384` / `RSA_SHA512` | Java 17+ | RSA đủ mạnh. | Profile yêu cầu SHA-384/512. | Không tự tăng hash thay cho key size; thống nhất profile. |
| `SignatureMethod.RSA_PSS` | Java 17+ | RSA phù hợp PSS. | Hệ thống đồng ý PSS parameters. | Đồng nhất digest, MGF1, salt, trailer, URI. |
| `SignatureMethod.SHA256_RSA_MGF1` | Java 17+ | RSA. | Profile yêu cầu URI SHA256-RSA-MGF1. | Kiểm tra provider/peer; URI khác `RSA_PSS`. |
| `SignatureMethod.ECDSA_SHA256` | Java 17+ | EC P-256. | Môi trường hỗ trợ EC/ECDSA. | Dùng curve phù hợp, certificate/key provenance. |
| `SignatureMethod.ECDSA_SHA384` | Java 17+ | EC P-384. | Policy cần profile mạnh hơn. | Peer/profile công bố hỗ trợ. |
| `SignatureMethod.ED25519` | Java **21+** | Ed25519. | Hạ tầng/đối tác hỗ trợ EdDSA XMLDSig. | Không dùng cho compile target Java 17. |
| `SignatureMethod.ED448` | Java **21+** | Ed448. | Profile hiện đại yêu cầu Ed448. | Test provider/interoperability thực. |
| `SignatureMethod.HMAC_SHA256` | Java 17+ | Symmetric secret. | Authenticated data giữa bên chia sẻ key. | Không tương đương PKI public signature. |

**Không nên chọn cho chữ ký mới:** `SignatureMethod.RSA_SHA1`, `DSA_SHA1`, `ECDSA_SHA1`, `HMAC_SHA1` hoặc thuật toán digest `SHA1`; các thuật toán MD5 và các cấu hình key quá yếu cũng không phù hợp. JDK giữ một số constant nhằm phục vụ nhận diện/khả năng tương thích với tài liệu cũ; bài học này **không hướng dẫn tạo chữ ký mới bằng các lựa chọn đó**.

### 4.1. SHA-3: có thể dùng, nhưng phân biệt JDK version

Hằng số SHA-3 trên `DigestMethod` đã có trong Java 17+, nhưng không phải mọi cặp `SignatureMethod` SHA-3 đều tồn tại từ Java 17:
- Các URI `SignatureMethod.SHA3_256_RSA_MGF1` và họ RSA-MGF1 SHA-3 được thêm vào API từ **Java 22**.
- Các `SignatureMethod.ECDSA_SHA3_256` và họ ECDSA-SHA3 được thêm vào API từ **Java 25**.
- JDK có một `MessageDigest` SHA3-256 không đồng nghĩa XMLDSig provider/counterparty biết URI SHA-3 tương ứng.
- Dùng SHA-2 phổ biến trước nếu không có profile SHA-3 rõ ràng; nếu có, test với đúng JDK/provider/peer.

Bảng ở mục 4 chỉ liệt kê những lựa chọn có thể cân nhắc; **không có bảo đảm một provider bất kỳ luôn thực hiện được mọi constant**. Một HSM/FIPS provider có thể chỉ cho phép một tập con.

### 4.2. Khóa mạnh và tuổi thọ bảo vệ

Độ mạnh không chỉ đến từ tên SHA:
- RSA key 3072 + SHA-256 có thể phù hợp nhiều ứng dụng; RSA key rất nhỏ + SHA-512 **vẫn yếu**.
- EC P-256 + SHA-256 là một cặp thường dùng; với P-384 có thể chọn SHA-384 theo profile.
- Ed25519 có profile cố định riêng; không tự trộn digest của `SignatureMethod`.
- Certificate validity, key usage, trust anchors, private key custody, revocation và rotation là một phần của chính sách.

Đặt **minimum key sizes** theo policy tổ chức, hướng dẫn cryptographic strength hiện hành và khả năng interop. **Đừng dùng mức tối thiểu trong secureValidation JDK như một khuyến nghị tạo key**; một số default restrictions chỉ chặn RSA/DSA dưới 1024 bit và EC dưới 224 bit, thấp hơn tiêu chuẩn thiết kế hiện đại nên ưu tiên.

## 5. DigestMethod: SHA-256/384/512 cho Reference

Trong XMLDSig, `DigestMethod` áp dụng lên **Reference** sau chuỗi transforms. Nó không trực tiếp tạo chữ ký bất đối xứng.

```java
DigestMethod digest = factory.newDigestMethod(
        DigestMethod.SHA256, null);
```

Đây là snippet, `factory` là `XMLSignatureFactory` đã có. Một `SignedInfo` có thể chứa nhiều `Reference` với các `DigestMethod` tương ứng; policy nên giới hạn số References, các URI và algorithms cho từng reference.

| Digest | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `DigestMethod.SHA256` | SHA-256 digest, phổ biến, tương tác tốt. | Mặc định hợp lý cho XMLDSig mới nếu profile cho phép. |
| `DigestMethod.SHA384` | SHA-384 digest. | Profile P-384/SHA-384 hoặc yêu cầu riêng. |
| `DigestMethod.SHA512` | SHA-512 digest. | Các profile cần SHA-512. |
| `DigestMethod.SHA3_256`… | SHA-3 digest algorithms. | Chỉ khi JDK/provider/peer và profile hỗ trợ. |
| `DigestMethod.SHA1` | SHA-1 digest. | **Không dùng cho thiết kế chữ ký mới**. |
| Các digest ít phổ biến | Có thể có constant/provider. | Chỉ dùng khi policy và interop đã duyệt; không mặc định. |

**Quan hệ với RSA-PSS:** `DigestMethod.SHA256` trong một Reference là **bước hash đối tượng XML**, còn SHA-256 trong RSA-PSS của `SignatureMethod.RSA_PSS` là **bước hash của quá trình ký SignedInfo**. Chúng có mục đích và vị trí khác nhau. Không dùng `SignatureMethod.RSA_SHA256` làm đối số cho `newDigestMethod`.

**Không chọn SHA-1 để “sửa lỗi verify”** khi tài liệu cũ bị từ chối. Thay đổi digest method trong XML sẽ làm thay đổi `SignedInfo` và phá chữ ký; không thể “nâng hash” trên chữ ký sẵn có chỉ bằng sửa URI. Cần ký lại với private key theo policy mới và giữ chain evidence theo nghiệp vụ.

## 6. Canonicalization và transforms phải được chọn riêng

### 6.1. Vì sao XML không được ký bằng raw String?

Hai serialization có thể cùng ngữ nghĩa XML nhưng khác:
- Thứ tự attributes.
- Namespace prefixes/declarations.
- Cách thể hiện whitespace trong những ngữ cảnh tương thích.
- Quote style, escaping và XML declaration.
- Cách serialize sau khi qua một DOM/transformer.

`CanonicalizationMethod` chuyển cấu trúc XML thành representation chuẩn để ký/xác minh nhất quán. Bản mẫu sử dụng **exclusive canonicalization**:

```java
CanonicalizationMethod c14n =
        factory.newCanonicalizationMethod(
                CanonicalizationMethod.EXCLUSIVE,
                (C14NMethodParameterSpec) null);
```

Đây là snippet, cần import `javax.xml.crypto.dsig.CanonicalizationMethod` và `javax.xml.crypto.dsig.spec.C14NMethodParameterSpec`. **Exclusive C14N không phải thuật toán hash**. Nó chuẩn hóa XML trước khi ký; không tạo bí mật hay authentication.

### 6.2. EXCLUSIVE, INCLUSIVE và comments

| Canonicalization | Đặc trưng | Lưu ý |
| --- | --- | --- |
| `CanonicalizationMethod.EXCLUSIVE` | Exclusive XML canonicalization, thường hữu ích khi ký phần XML ở một context namespace. | Phải khớp profile/peer; xử lý namespace thực tế phải được test. |
| `CanonicalizationMethod.INCLUSIVE` | Inclusive canonicalization. | Namespace context bên ngoài có thể ảnh hưởng kết quả trong một số cấu trúc. |
| `CanonicalizationMethod.INCLUSIVE_11` | Canonical XML 1.1. | Chỉ dùng khi được yêu cầu và hỗ trợ đúng. |
| `EXCLUSIVE_WITH_COMMENTS` / `INCLUSIVE_WITH_COMMENTS` | Biến thể gồm comments trong canonical form. | Comments bị thay đổi có thể ảnh hưởng chữ ký; chọn có chủ đích. |

**Đừng tự động đổi canonicalization để làm chữ ký cũ “pass”.** Verifier phải dùng thuật toán `SignedInfo.CanonicalizationMethod` đã khai trong chữ ký nếu nó nằm trong policy allowlist. Nếu thuật toán không được chấp nhận hoặc provider không hỗ trợ, từ chối; không thử ký lại bằng thuật toán khác với cùng `SignatureValue`.

### 6.3. Enveloped signature transform

Khi phần tử `Signature` được đặt **bên trong chính nội dung được ký**, cần loại bỏ nút Signature khỏi tập nodes đưa vào digest để tránh self-reference. Với chữ ký enveloped:

```java
Transform enveloped = factory.newTransform(
        Transform.ENVELOPED,
        (TransformParameterSpec) null);
```

Khi input của Reference là DOM document node-set, một transform C14N explicit thường giúp tránh phụ thuộc vào canonicalization mặc định của bước chuyển sang octets. Ví dụ chạy đầy đủ dùng:

```java
List.of(
    factory.newTransform(
            Transform.ENVELOPED,
            (TransformParameterSpec) null),
    factory.newTransform(
            CanonicalizationMethod.EXCLUSIVE,
            (TransformParameterSpec) null)
)
```

Các snippet này cần imports `Transform`, `TransformParameterSpec`, `CanonicalizationMethod` và `List`. Chọn transforms theo profile và **chỉ cho phép tập cần thiết**; không tùy tiện nhận một `Transforms` chain từ tài liệu chưa xác thực.

### 6.4. Những transforms nên hạn chế

JDK secure-validation mode có chính sách **cấm XSLT transforms** theo mặc định, giới hạn số transforms/reference và cấm các URI external phổ biến. Trong app, nên:
- Cho phép **enveloped + canonicalization** nếu đó là XMLDSig profile sử dụng.
- Từ chối XSLT/XPath transforms không được duyệt, vì có thể thay đổi **phần dữ liệu thực sự được digest** hoặc có hệ quả tài nguyên.
- Không cho `Reference URI` truy cập `http:`, `https:`, `file:` khi tài liệu do bên ngoài cung cấp, trừ khi ứng dụng có protocol đặc biệt, resolver allowlist và threat model riêng.
- Giới hạn total References, transforms, XML depth và resource usage.
- Luôn kiểm tra **node nào được ký** và **node nào được dùng trong nghiệp vụ** có phải cùng object.

**Cảnh báo:** một XML Signature có cryptographic validity true nhưng app lại lấy một `<payment>` chưa được ký để chuyển tiền vẫn có thể bị tấn công. Đây là lỗi **signature wrapping / unsigned data consumption**, không sửa được chỉ bằng SHA-512.

## 7. secureValidation và chính sách cho phép thuật toán

### 7.1. Secure validation mode mặc định trong JDK hiện đại

Oracle Java Security Guide mô tả **XML Signature secure validation mode được bật mặc định** trên JDK hiện đại. Nó hạn chế một số cấu trúc XMLDSig nguy hiểm, ví dụ:
- Cấm XSLT transforms.
- Giới hạn số `Reference` trong `SignedInfo`/`Manifest` (mặc định 30).
- Giới hạn số transforms trên mỗi Reference (mặc định 5).
- Hạn chế thuật toán ký/MAC dùng SHA-1/MD5 theo security policy hiện hành.
- Ngăn duplicated Reference IDs theo các điều kiện cụ thể.
- Cấm các Reference URI ngoài như `http`, `https`, `file`.
- Không cho `RetrievalMethod` tham chiếu một `RetrievalMethod` khác.
- Kiểm tra mức độ dài khóa tối thiểu (ví dụ RSA/DSA dưới 1024, EC dưới 224 bits bị chặn theo guide).

**Đây là lớp bảo vệ của runtime**, không phải chứng chỉ tuân thủ toàn diện. Default list và policy có thể thay đổi theo bản cập nhật JDK, security file và vendor. **Ứng dụng vẫn cần allowlist chặt hơn**, kiểm tra key size theo policy hiện đại, trust/PKI và signed-object identity.

Khi tạo validation context, đặt explicit:

```java
DOMValidateContext context =
        new DOMValidateContext(trustedPublicKey, signatureElement);
context.setProperty(
        "org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
```

Đây là snippet; `trustedPublicKey` là `PublicKey` đã được xác minh nguồn trust, `signatureElement` là DOM node đúng chữ ký và đã parse XML an toàn. Không dùng `Boolean.FALSE` để vượt qua lỗi “algorithm forbidden”; nếu chữ ký bị policy chặn, xử lý tương thích/nghiệp vụ ở hệ thống có thẩm quyền và không âm thầm downgrade.

**Nếu có system property tương ứng, nó có thể ưu tiên hơn API property** theo JDK guide. Vận hành phải kiểm tra cấu hình JDK và security properties của môi trường thực, không chỉ tin một dòng `setProperty` khi quyền kiểm soát system-level thuộc platform.

### 7.2. jdk.xml.dsig.secureValidationPolicy

`jdk.xml.dsig.secureValidationPolicy` là **Java Security Property**, cho phép cấu hình chi tiết hạn chế XMLDSig; được quản lý qua security properties của runtime (không phải tự ý thêm một system property bất kỳ rồi hy vọng có hiệu lực).

Không hard-code bản copy hoàn chỉnh của policy file JDK vào ứng dụng:
- Nội dung có thể thay đổi theo JDK release/vendor/security updates.
- Override thiếu hiểu biết có thể làm yếu bảo vệ của cả quá trình verify.
- Nếu tổ chức cần thắt chặt, test với deployment/image thực tế và quản lý change control.
- Trong policy ứng dụng còn cần **algorithm allowlist, key sizes và reference/transform allowlist** độc lập.

**Một thuật toán được provider hỗ trợ nhưng bị policy chặn là kết quả hợp lệ của hệ thống bảo mật**. Không tự giải quyết bằng cách đặt `secureValidation=false` hoặc làm lỏng `jdk.xml.dsig.secureValidationPolicy`.

### 7.3. Vì sao allowlist ứng dụng vẫn cần thiết?

Nếu code chỉ gọi:

```java
XMLSignature signature =
        factory.unmarshalXMLSignature(context);
boolean valid = signature.validate(context);
```

thì việc cryptographic validation thành công không chứng minh mọi quy định nghiệp vụ về thuật toán đều thỏa. Hãy kiểm tra explicit:
- `signature.getSignedInfo().getSignatureMethod().getAlgorithm()` thuộc allowlist.
- `getCanonicalizationMethod().getAlgorithm()` thuộc allowlist.
- Mọi `Reference` dùng `DigestMethod` được cho phép và URI hợp lệ.
- Mọi `Transform` thuộc allowlist và số lượng phù hợp profile.
- Key type và size đạt mức yêu cầu; certificate chain/trust/usage còn hợp lệ.
- Signed target IDs/root/path không bị wrapping/duplication/đổi node.

Mục 8 minh họa **allowlist cho một profile giáo dục rất hẹp**, nhưng vẫn chưa là verification gateway production.

## 8. Chương trình Java 17+ hoàn chỉnh: ký, verify, tamper test và allowlist

Ví dụ dưới đây **không cần JDBC, key store, file chứng thư hay dependency ngoài JDK**. Nó minh họa:
1. Tạo RSA-3072 và EC P-256 key pairs **tạm thời** chỉ để test.
2. Tạo XML nhỏ `<invoice><id>INV-7</id><amount>19.75</amount></invoice>`.
3. Ký **enveloped** bằng RSA-SHA256, RSA-PSS/SHA-256 hoặc ECDSA-SHA256.
4. Chọn `DigestMethod.SHA256` cho `Reference URI=""`; dùng enveloped transform và exclusive C14N.
5. Serialize rồi **parse XML an toàn** để verify như trường hợp nhận tài liệu.
6. Dùng `DOMValidateContext` với **public key được cung cấp từ phía tin cậy**, không lấy khóa tùy ý từ `KeyInfo`.
7. Bật explicit `secureValidation` và kiểm tra cấu trúc thuật toán/URI/transforms trước `validate()`.
8. Thử sửa số tiền và thay trusted public key: chữ ký bị từ chối.
9. Kiểm tra `RSA_SHA1` **không** thuộc allowlist, không tạo chữ ký SHA-1.

### 8.1. File XmlSignatureAlgorithmsDemo.java

Lưu toàn bộ nội dung sau vào **`XmlSignatureAlgorithmsDemo.java`** bằng UTF-8:

```java
import java.io.StringReader;
import java.io.StringWriter;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.spec.ECGenParameterSpec;
import java.util.List;
import java.util.Set;
import javax.xml.XMLConstants;
import javax.xml.crypto.dsig.CanonicalizationMethod;
import javax.xml.crypto.dsig.DigestMethod;
import javax.xml.crypto.dsig.Reference;
import javax.xml.crypto.dsig.SignatureMethod;
import javax.xml.crypto.dsig.SignedInfo;
import javax.xml.crypto.dsig.Transform;
import javax.xml.crypto.dsig.XMLSignature;
import javax.xml.crypto.dsig.XMLSignatureFactory;
import javax.xml.crypto.dsig.dom.DOMSignContext;
import javax.xml.crypto.dsig.dom.DOMValidateContext;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.xml.sax.InputSource;

public final class XmlSignatureAlgorithmsDemo {
    private static final XMLSignatureFactory FACTORY =
            XMLSignatureFactory.getInstance("DOM");

    private static final Set<String> ALLOWED = Set.of(
            SignatureMethod.RSA_SHA256,
            SignatureMethod.RSA_PSS,
            SignatureMethod.ECDSA_SHA256);

    private static DocumentBuilderFactory safeDomFactory()
            throws Exception {
        DocumentBuilderFactory f =
                DocumentBuilderFactory.newInstance();
        f.setNamespaceAware(true);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        f.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
        f.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
        f.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return f;
    }

    private static Document buildInvoice() throws Exception {
        Document d = safeDomFactory()
                .newDocumentBuilder().newDocument();
        Element root = d.createElement("invoice");
        d.appendChild(root);

        Element id = d.createElement("id");
        id.setTextContent("INV-7");
        root.appendChild(id);

        Element amount = d.createElement("amount");
        amount.setTextContent("19.75");
        root.appendChild(amount);

        return d;
    }

    private static String write(Document d) throws Exception {
        TransformerFactory f = TransformerFactory.newInstance();
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

        Transformer t = f.newTransformer();
        t.setOutputProperty(
                OutputKeys.OMIT_XML_DECLARATION, "yes");

        StringWriter out = new StringWriter();
        t.transform(new DOMSource(d), new StreamResult(out));
        return out.toString();
    }

    private static Document read(String xml) throws Exception {
        return safeDomFactory().newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));
    }

    private static void sign(
            Document d, KeyPair pair, String algorithm)
            throws Exception {
        Reference reference = FACTORY.newReference(
                "",
                FACTORY.newDigestMethod(
                        DigestMethod.SHA256, null),
                List.of(
                    FACTORY.newTransform(
                            Transform.ENVELOPED,
                            (javax.xml.crypto.dsig.spec
                             .TransformParameterSpec) null),
                    FACTORY.newTransform(
                            CanonicalizationMethod.EXCLUSIVE,
                            (javax.xml.crypto.dsig.spec
                             .TransformParameterSpec) null)),
                null, null);

        SignedInfo signedInfo = FACTORY.newSignedInfo(
                FACTORY.newCanonicalizationMethod(
                        CanonicalizationMethod.EXCLUSIVE,
                        (javax.xml.crypto.dsig.spec
                         .C14NMethodParameterSpec) null),
                FACTORY.newSignatureMethod(algorithm, null),
                List.of(reference));

        XMLSignature sig =
                FACTORY.newXMLSignature(signedInfo, null);

        DOMSignContext context =
                new DOMSignContext(
                        pair.getPrivate(), d.getDocumentElement());
        context.setDefaultNamespacePrefix("ds");
        sig.sign(context);
    }

    private static boolean allowedStructure(XMLSignature sig) {
        SignedInfo signedInfo = sig.getSignedInfo();

        if (!ALLOWED.contains(
                signedInfo.getSignatureMethod().getAlgorithm())) {
            return false;
        }

        if (!CanonicalizationMethod.EXCLUSIVE.equals(
                signedInfo.getCanonicalizationMethod()
                          .getAlgorithm())) {
            return false;
        }

        if (signedInfo.getReferences().size() != 1) {
            return false;
        }

        Reference reference =
                (Reference) signedInfo.getReferences().get(0);

        if (!"".equals(reference.getURI())
                || !DigestMethod.SHA256.equals(
                    reference.getDigestMethod().getAlgorithm())) {
            return false;
        }

        if (reference.getTransforms().size() != 2) {
            return false;
        }

        Transform first =
                (Transform) reference.getTransforms().get(0);
        Transform second =
                (Transform) reference.getTransforms().get(1);

        return Transform.ENVELOPED.equals(
                    first.getAlgorithm())
                && CanonicalizationMethod.EXCLUSIVE.equals(
                    second.getAlgorithm());
    }

    private static boolean verify(
            Document d, PublicKey trustedKey) throws Exception {

        Node node = d.getElementsByTagNameNS(
                XMLSignature.XMLNS, "Signature").item(0);

        if (!(node instanceof Element)) {
            return false;
        }

        DOMValidateContext context =
                new DOMValidateContext(trustedKey, node);
        context.setProperty(
                "org.jcp.xml.dsig.secureValidation", Boolean.TRUE);

        XMLSignature signature =
                FACTORY.unmarshalXMLSignature(context);

        if (!allowedStructure(signature)) {
            return false;
        }

        return signature.validate(context);
    }

    private static KeyPair rsaPair() throws Exception {
        KeyPairGenerator g =
                KeyPairGenerator.getInstance("RSA");
        g.initialize(3072);
        return g.generateKeyPair();
    }

    private static KeyPair ecPair() throws Exception {
        KeyPairGenerator g =
                KeyPairGenerator.getInstance("EC");
        g.initialize(
                new ECGenParameterSpec("secp256r1"));
        return g.generateKeyPair();
    }

    private static void roundTrip(
            String label, String algorithm, KeyPair keys)
            throws Exception {
        Document invoice = buildInvoice();
        sign(invoice, keys, algorithm);

        Document received = read(write(invoice));
        boolean valid = verify(
                received, keys.getPublic());

        System.out.println(label + "=" + valid);
        if (!valid) {
            throw new AssertionError(
                    "Valid signature rejected");
        }

        if ("rsaSha256".equals(label)) {
            received.getElementsByTagName("amount")
                    .item(0).setTextContent("999.99");

            System.out.println("tamperedAccepted="
                    + verify(received, keys.getPublic()));

            System.out.println("untrustedKeyAccepted="
                    + verify(
                        read(write(invoice)),
                        rsaPair().getPublic()));
        }
    }

    public static void main(String[] args) throws Exception {
        roundTrip(
                "rsaSha256",
                SignatureMethod.RSA_SHA256,
                rsaPair());

        roundTrip(
                "rsaPssSha256",
                SignatureMethod.RSA_PSS,
                rsaPair());

        roundTrip(
                "ecdsaSha256",
                SignatureMethod.ECDSA_SHA256,
                ecPair());

        System.out.println("sha1Allowed="
                + ALLOWED.contains(
                        SignatureMethod.RSA_SHA1));
    }
}
```

**Ghi chú về cách trình bày imports/casts:** trong Java code block, qualified names của `TransformParameterSpec` và `C14NMethodParameterSpec` được xuống dòng sau dấu chấm chỉ để vừa chiều ngang, là whitespace Java hợp lệ. Nếu IDE định dạng lại, code tiếp tục có cùng ngữ nghĩa. Toàn bộ chương trình đã được biên dịch và chạy kiểm chứng trên OpenJDK 24 với `javac --release 17`.

### 8.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 XmlSignatureAlgorithmsDemo.java
java XmlSignatureAlgorithmsDemo
```

Code sử dụng API đã có ở Java 17. **Không cần `--enable-preview`, dependency ngoài, private key file hay internet**. Nó tạo keys tạm trong RAM, chỉ để học. Thời gian tạo RSA keys có thể khác nhau, nhưng các dòng kết quả boolean bên dưới là những kiểm tra đã được thực thi.

**Stdout chính xác từ lần chạy kiểm chứng trên OpenJDK 24:**

```text
rsaSha256=true
tamperedAccepted=false
untrustedKeyAccepted=false
rsaPssSha256=true
ecdsaSha256=true
sha1Allowed=false
```

Giải thích:
- `rsaSha256=true`: signed XML sau serialize/parse an toàn vẫn xác minh đúng bằng trusted RSA public key.
- `tamperedAccepted=false`: sửa `<amount>19.75</amount>` thành `999.99` làm digest của Reference không khớp.
- `untrustedKeyAccepted=false`: cùng tài liệu ký bằng private key A, xác minh bằng public key khác B thất bại. Đây là **kiểm tra đúng khóa**, không phải một chương trình PKI certificate trust.
- `rsaPssSha256=true`: JDK đã thử nghiệm chấp nhận RSA-PSS với tham số mặc định SHA-256/MGF1/Salt32/Trailer1.
- `ecdsaSha256=true`: EC P-256 + ECDSA-SHA256 ký/xác minh thành công.
- `sha1Allowed=false`: phép kiểm tra `Set` ứng dụng **không** cho RSA-SHA1. Chương trình **không tạo chữ ký SHA-1**.

### 8.3. Giới hạn bảo mật của demo

Ví dụ cố ý có cấu trúc nhỏ và chính xác:
- `Reference URI=""` cùng enveloped transform ký **toàn bộ XML document** theo XMLDSig rules. Trong tài liệu có cấu trúc phức tạp, cần profile chặt hơn để kiểm tra signed node identities.
- Không dùng `KeyInfo`; verifier nhận public key tin cậy từ code, tránh chứng minh trust bằng một khóa kẻ tấn công đính kèm.
- Không có X.509 certificate chain validation, certificate revocation, timestamp, CRL/OCSP hoặc chính sách ký số pháp lý.
- `getElementsByTagNameNS(...).item(0)` chỉ phù hợp ví dụ **do chính mình tạo**, chưa xác minh **đúng một chữ ký, đúng vị trí và đúng signed object** khi nhận tài liệu lạ. Production phải xử lý signature wrapping, duplicate IDs và business element selection.
- `allowedStructure` chỉ là allowlist một profile học tập (một Reference root + hai transforms), không phải verifier cho mọi XMLDSig profile hợp lệ.
- Đã harden DOM parsing/Transformer cho các API JDK mặc định dùng trong demo; nếu thay XML provider ngoài JDK, cần kiểm thử các features/properties được hỗ trợ.
- Không log hoặc serialize private key. Production nên lấy private key từ HSM/KMS/keystore quản lý theo policy.

**Không dùng `XMLSignature.validate()` làm bước duy nhất quyết định trả tiền/đổi tài khoản/thực thi giao dịch.** Cần xác minh cả signer identity, certificate trust và dữ liệu nghiệp vụ nằm trong nút đã được ký.

## 9. Ví dụ Java 21+: XML Signature Ed25519

Từ Java 21, có thể tạo XMLDSig `SignatureMethod.ED25519`. Ví dụ sau là **chương trình riêng**; không biên dịch bằng `--release 17` do API constant chưa có. Nó ký một DOM document nhỏ bằng key Ed25519, sau đó xác minh chữ ký trên cùng DOM với `DOMValidateContext`.

### 9.1. File Ed25519XmlSignatureDemo.java

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.List;
import javax.xml.crypto.dsig.CanonicalizationMethod;
import javax.xml.crypto.dsig.DigestMethod;
import javax.xml.crypto.dsig.Reference;
import javax.xml.crypto.dsig.SignatureMethod;
import javax.xml.crypto.dsig.SignedInfo;
import javax.xml.crypto.dsig.Transform;
import javax.xml.crypto.dsig.XMLSignature;
import javax.xml.crypto.dsig.XMLSignatureFactory;
import javax.xml.crypto.dsig.dom.DOMSignContext;
import javax.xml.crypto.dsig.dom.DOMValidateContext;
import javax.xml.crypto.dsig.spec.C14NMethodParameterSpec;
import javax.xml.crypto.dsig.spec.TransformParameterSpec;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

public final class Ed25519XmlSignatureDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator keyGen =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair keys = keyGen.generateKeyPair();

        DocumentBuilderFactory dom =
                DocumentBuilderFactory.newInstance();
        dom.setNamespaceAware(true);
        Document doc = dom.newDocumentBuilder().newDocument();

        Element root = doc.createElement("message");
        root.setTextContent("Xin chào 🌏");
        doc.appendChild(root);

        XMLSignatureFactory factory =
                XMLSignatureFactory.getInstance("DOM");

        Reference reference = factory.newReference(
                "",
                factory.newDigestMethod(
                        DigestMethod.SHA256, null),
                List.of(factory.newTransform(
                        Transform.ENVELOPED,
                        (TransformParameterSpec) null)),
                null, null);

        SignedInfo signedInfo = factory.newSignedInfo(
                factory.newCanonicalizationMethod(
                        CanonicalizationMethod.EXCLUSIVE,
                        (C14NMethodParameterSpec) null),
                factory.newSignatureMethod(
                        SignatureMethod.ED25519, null),
                List.of(reference));

        XMLSignature signature =
                factory.newXMLSignature(signedInfo, null);
        DOMSignContext signContext =
                new DOMSignContext(keys.getPrivate(), root);
        signature.sign(signContext);

        Element signatureElement = (Element)
                root.getElementsByTagNameNS(
                    XMLSignature.XMLNS, "Signature").item(0);

        DOMValidateContext validation =
                new DOMValidateContext(
                        keys.getPublic(), signatureElement);
        validation.setProperty(
                "org.jcp.xml.dsig.secureValidation", Boolean.TRUE);

        XMLSignature decoded =
                factory.unmarshalXMLSignature(validation);

        System.out.println("ed25519Valid="
                + decoded.validate(validation));
    }
}
```

**Chạy trên JDK 21+:**

```bash
javac --release 21 -encoding UTF-8 Ed25519XmlSignatureDemo.java
java Ed25519XmlSignatureDemo
```

**Stdout đã biên dịch/chạy kiểm chứng trên OpenJDK 24:**

```text
ed25519Valid=true
```

Ví dụ này tạo **DOM của chính chương trình**, không parse XML nhận từ bên ngoài và không kiểm tra truststore. Khi kiểm tra chữ ký Ed25519 từ file/XML đối tác, phải bổ sung **DOM parser hardening, algorithm allowlist, signed-node checks và trust verification** như các mục khác. `DigestMethod.SHA256` ở đây là digest Reference; nó không biến Ed25519 thành thuật toán “Ed25519-SHA256”.

## 10. Hỗ trợ API khác hỗ trợ JCA provider

Đôi khi code compile nhưng tới runtime ném `NoSuchAlgorithmException`, `InvalidAlgorithmParameterException`, `XMLSignatureException` hoặc lỗi provider. Lý do:
- JDK compile target có constant `SignatureMethod` nhưng runtime thực không có hoặc có provider khác.
- XMLDSig provider biết URI nhưng JCA provider/HSM không cung cấp engine ký tương ứng.
- Key thuộc loại sai, thiếu algorithm parameters, size quá nhỏ hoặc certificate hạn chế key usage.
- XMLDSig security policy chặn thuật toán/key.
- Partner dùng URI/format khác cho RSA-PSS/ECDSA/EdDSA.
- Một provider chỉ hỗ trợ verify, hoặc chỉ hỗ trợ sign trong phạm vi token/HSM.
- HSM không cho xuất private key; `PrivateKey` là handle tới token và phải dùng provider đúng.

### 10.1. Đừng thử “fallback sang SHA1”

**Anti-pattern:**

```java
// SAI: chỉ để minh họa điều không được thực hiện.
try {
    return signWithStrongProfile(document);
} catch (Exception ignored) {
    return signWithLegacyWeakProfile(document);
}
```

Đây là pseudocode sai, không phải chương trình Java độc lập. Khi chính sách thuật toán hiện đại không được provider hỗ trợ, phải **fail closed** và báo lỗi cấu hình/interop. Không downgrade sang RSA-SHA1/HMAC-SHA1/MD5 hoặc tắt secureValidation chỉ để có chữ ký “hợp lệ”.

### 10.2. Thuật toán không thể tự đoán từ khóa

Một `PrivateKey` báo algorithm `RSA` không xác định nên chọn RSA-SHA256, RSA-PSS hay URI profile nào. Khóa `EC` không cho biết curve và policy nào được phép chỉ qua `getAlgorithm()`. Metadata certificate/PKI/contract phải được kiểm tra trước quyết định.

Với RSA-PSS, còn phải thống nhất `PSSParameterSpec` hoặc `RSAPSSParameterSpec` theo API/XMLDSig. Không hard-code mặc định mà chưa đọc hợp đồng và peer documentation.

### 10.3. KeyInfo không phải trust anchor

`KeyInfo` có thể chứa `KeyValue` hoặc `X509Data`, nhưng kẻ tấn công cũng có thể tạo key pair, ký XML giả và đính kèm public key của chính họ. Khi đó phép toán kiểm tra chữ ký **có thể true** với key đính kèm, nhưng signer vẫn **không được tin cậy**.

Thiết kế đúng:
- Resolve signer identity qua trusted certificate chain hoặc pinned public key/key identifier.
- Kiểm tra certificate validity, EKU/key usage, trusted roots, revocation/time evidence theo quy định.
- So sánh principal/issuer với operation được phép ký.
- Không bỏ qua trust chỉ vì XMLDSig `validate()` trả true.

## 11. Kiểm tra signed object: tránh signature wrapping

**Signature wrapping** là một nhóm tấn công nơi XML có chữ ký mật mã hợp lệ trên node A nhưng ứng dụng lại sử dụng node B chưa được ký. Đây là lỗ hổng nghiệp vụ XML parsing, không phải SHA-256 bị bẻ khóa.

Ví dụ lược giản:

```xml
<Envelope>
  <Order Id="signed-1">
    <amount>19.75</amount>
  </Order>
  <Order Id="unsigned-2">
    <amount>999.99</amount>
  </Order>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <!-- Cấu trúc chữ ký minh họa, không phải XMLDSig hoàn chỉnh. -->
  </ds:Signature>
</Envelope>
```

Đây là **XML minh họa dạng partial**, không thể dùng để verify vì không có `SignedInfo`/`SignatureValue` thật. Nếu signature thực ký `#signed-1` nhưng app xử lý “Order cuối” hoặc XPath không ràng buộc, có thể xử lý `unsigned-2`. **Thay RSA-SHA256 bằng RSA-PSS không tự sửa lỗi này.**

### 11.1. Ràng buộc Reference và ID

Với same-document ID reference, ứng dụng cần:
1. Chỉ định/chấp nhận những IDs nằm ở cấu trúc tài liệu đã xác thực.
2. Đăng ký thuộc tính ID đúng (ví dụ `DOMValidateContext.setIdAttributeNS(...)` hoặc DOM `setIdAttributeNS(...)` theo parser/schema), không tự tin rằng attribute tên `Id` tự động được nhận diện hợp lệ.
3. Từ chối ID trùng lặp và node không mong đợi.
4. Kiểm tra `Reference URI` là giá trị theo profile, không có external dereference.
5. Sau khi `validate()`, chỉ dùng **đúng node đã được Reference bao phủ**, không thực hiện một DOM search mơ hồ lần thứ hai.
6. Kiểm tra root/namespace, schema và content semantics.
7. Nếu có nhiều chữ ký, có chính sách rõ số lượng/vị trí/signer nào hợp lệ.

**Ví dụ bài học dùng Reference URI="" ký toàn bộ document** và chỉ có một Signature; một ứng dụng ký riêng `<Order Id="...">` cần cơ chế ID và coverage chặt hơn.

### 11.2. Chặn Reference URI ngoài

Một XMLDSig có `Reference URI="https://example.test/foo"` có thể buộc verifier tải data ngoài nếu dereferencer cho phép. Secure validation mode đã chặn nhiều scheme phổ biến theo policy, nhưng app còn nên dùng allowlist `Reference.getURI()` và **`URIDereferencer` giới hạn** nếu có yêu cầu đặc biệt.

**Không dùng Internet/file dereference tự do** cho dữ liệu do người dùng gửi. Với một đối tượng tham chiếu nội bộ có ID rõ, dùng same-document URI và validate ID uniqueness. Với detached references, nếu business thật sự cần, resolve từ nguồn dữ liệu **được xác thực/kiểm soát** theo policy, không để XML tự quyết định URL.

### 11.3. Chữ ký hợp lệ không đồng nghĩa XML hợp lệ nghiệp vụ

`XMLSignature.validate()` kiểm tra cryptographic structure và digests trong phạm vi XMLDSig; nó không thay:
- XSD validation đã harden.
- Schema version/issuer verification.
- Amount/currency/signing rights kiểm tra theo nghiệp vụ.
- Authorization của request.
- Confirmation của certificate trust/revocation/timestamp.
- Anti-replay/nonce/transaction ID và logging/audit policy.

Luôn **xác minh chữ ký + ràng buộc node + xác thực người ký + kiểm tra nghiệp vụ** theo thứ tự thiết kế.

## 12. XML input parser hardening là điều kiện trước khi verify

XMLDSig nằm trong `java.xml.crypto`, nhưng DOM parsing được cung cấp từ `java.xml`. Nếu DOM parser cho external entities/DTD, ứng dụng có thể bị XXE **trước khi** `XMLSignatureFactory` bắt đầu verify.

Với XML không tin cậy:
- `DocumentBuilderFactory.setNamespaceAware(true)` để tìm `ds:Signature` theo URI.
- Bật `FEATURE_SECURE_PROCESSING` và vô hiệu DOCTYPE khi policy không cần.
- Tắt external-general/external-parameter entities, XInclude, hạn chế `ACCESS_EXTERNAL_DTD`/`ACCESS_EXTERNAL_SCHEMA`.
- **Fail closed** nếu parser/provider không hỗ trợ property/feature bảo mật bắt buộc.
- Giới hạn bytes/depth/attributes/text/timeouts trước và trong parse; không dùng DOM cho tài liệu quá lớn không có budget.
- Với `TransformerFactory`, khóa `ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_STYLESHEET` khi xử lý nguồn không tin cậy.
- Không cho XML signature transforms tái truy cập mạng/tệp tùy ý.
- Không log payload/certificate private material khi verify thất bại.

**Không coi `XMLSignatureFactory` là XML parser input gateway hoàn chỉnh.** JSR105 nhận DOM đã parse và xử lý Reference/transforms; các rủi ro ở tầng parser, schema, transformation và nghiệp vụ cần được phòng thủ riêng.

## 13. Lựa chọn thuật toán theo bối cảnh triển khai

### 13.1. Hệ thống nội bộ, Java 17 và đối tác hỗ trợ RSA

Khuyến nghị ban đầu:
- RSA key tối thiểu 2048, thường RSA-3072 nếu phù hợp.
- `SignatureMethod.RSA_SHA256`.
- `DigestMethod.SHA256`.
- `CanonicalizationMethod.EXCLUSIVE` nếu XML profile cho phép.
- `Reference` same-document với URI được kiểm tra, enveloped transform nếu chữ ký nằm trong document.
- `secureValidation` bật, allowlist và trusted public key/certificate chain.

Lợi thế là nhiều hệ XMLDSig/PKI hiểu RSA-SHA256. Nếu đối tác bắt buộc RSA-PSS, chọn RSA-PSS và test tham số/URI thay vì cố áp RSA-SHA256.

### 13.2. Hệ thống Java 17+ muốn RSA-PSS

Dùng `SignatureMethod.RSA_PSS` khi tất cả bên thống nhất. JDK 17 hỗ trợ constant này, với default PSS SHA-256/MGF1/Salt32/Trailer1. Khi ký bằng HSM, kiểm tra token/provider hỗ trợ PSS và parameter mapping. Test cả Java verifier và bên nhận thực để tránh “ký được nội bộ nhưng gateway từ chối”.

### 13.3. Hệ thống hỗ trợ EC

Dùng ECDSA-SHA256 với P-256 hoặc ECDSA-SHA384 với P-384 theo policy. Xác minh cách biểu diễn `SignatureValue`/certificate hỗ trợ đúng XMLDSig. Không tự chuyển ký bằng `java.security.Signature` rồi base64 raw DER signature vào XML mà chưa tuân XMLDSig encoding.

### 13.4. Java 21+ và đối tác hiện đại

Có thể cân nhắc Ed25519, nhưng phải xác nhận:
- Chữ ký XMLDSig EdDSA URI được peer công nhận.
- Chứng chỉ/CA, HSM và trust service chấp nhận Ed25519.
- JDK/client tối thiểu Java 21 cho `SignatureMethod.ED25519`.
- Compliance/FIPS mode hoặc chính sách quốc gia không yêu cầu thuật toán khác.
- Key rotation/certificate validity và audit evidence phù hợp.

**Không ép Ed25519 chỉ vì thuật toán “mới hơn”.** Lựa chọn hợp lý là lựa chọn đáp ứng cryptographic policy **và** interoperability.

### 13.5. Hệ thống dùng HMAC

Chỉ dùng `HMAC_SHA256` khi cả hai bên thực sự chia sẻ secret có bảo vệ và không cần bên thứ ba kiểm chứng độc lập. HMAC không dùng X.509 public-key trust theo cùng cách RSA/ECDSA. Không giả định HMAC XML Signature có giá trị chứng cứ pháp lý tương đương chữ ký bất đối xứng.

### 13.6. Môi trường có quy định chuyên ngành hoặc FIPS

Đừng viết rule “JDK hỗ trợ nên FIPS-approved”. Mức chấp thuận phụ thuộc:
- Nhà cung cấp cryptographic provider/FIPS module và trạng thái validated.
- Key generation/storage và bảo vệ private key.
- Chế độ chạy FIPS, thuật toán/curve/parameter được profile chấp nhận.
- Chứng thư/cấp phát/quy trình định danh và chính sách pháp lý hiện hành.
- Hướng dẫn của đơn vị tích hợp, chuẩn ngành và đối tác ký số.

Khi compliance có quyết định khác với bảng lựa chọn ở trên, **theo chính sách được phê duyệt** và ghi nhận exception/migration plan nếu phải đọc chữ ký cũ.

## 14. Ký tài liệu cũ và migration SHA-1

Nếu bạn duy trì dữ liệu có chữ ký cũ, cần tách **đọc tài liệu lịch sử** khỏi **phát hành chữ ký mới**.

Không:
- Tắt `secureValidation` toàn hệ thống để một file SHA-1 legacy pass.
- Bật lại SHA-1 trong allowlist cho mọi request mới.
- Thay `DigestMethod`/`SignatureMethod` trong XML cũ để “nâng cấp” chữ ký.
- Xóa thông tin chứng chỉ/time evidence mà không có cơ chế lưu trữ.
- Giấu việc verifier từ chối SHA-1 bằng cách coi là “file corrupted”.

Nên:
1. Kiểm kê legacy signatures và algorithm URIs, tuổi tài liệu, trust evidence.
2. Xác định policy xác minh dữ liệu lịch sử theo quy định pháp lý và hệ thống nghiệp vụ.
3. Với nội dung cần tiếp tục trao đổi, có thể ký lại bằng thuật toán mới và giữ record/audit chain cũ theo quy trình.
4. Cấu hình khác nhau giữa **sign-new** và **verify-archived** chỉ khi được phê duyệt bằng security review; không tự hạ policy runtime của production request path.
5. Ghi nhận thời gian, signer/certificate/trust status và provenance, không tuyên bố một chữ ký cũ trở thành chữ ký mới chỉ vì file được re-serialized.

Special Note yêu cầu kiến thức hiện hành: mục này chỉ giải thích **cách tránh dùng thuật toán lỗi thời** và lập kế hoạch chuyển đổi, **không hướng dẫn tạo chữ ký XML bằng SHA-1/MD5**.

## 15. Bộ kiểm thử chọn thuật toán và xác minh an toàn

**Test 1 — RSA-SHA256 positive control.** Ký bằng RSA ≥2048, xác minh với trusted public key, `validate()` trả true, đúng signed object.

**Test 2 — RSA-PSS positive control.** Dùng `SignatureMethod.RSA_PSS` và parameters đã thống nhất; test verify trên cả JDK provider và đối tác gateway.

**Test 3 — ECDSA-SHA256 positive control.** Dùng EC P-256, confirm đúng XMLDSig encoding và verifier hỗ trợ.

**Test 4 — Ed25519 Java 21+.** Test `SignatureMethod.ED25519` trên JDK21+ và partner thật; với Java17 compile target, tuyệt đối không tham chiếu constant này trong production source.

**Test 5 — Reference digest tampering.** Sửa một trường trong node đã ký; verifier phải trả false. Không chỉ sửa phần nằm ngoài Reference rồi mong chữ ký phát hiện.

**Test 6 — Wrong public key.** Xác minh bằng public key khác người ký; verifier phải trả false. Sau đó kiểm tra trust anchor/PKI logic riêng.

**Test 7 — SHA-1 disallow.** Nhận metadata chữ ký yêu cầu `RSA_SHA1` hoặc `DigestMethod.SHA1`; **application allowlist phải từ chối** mà không tắt secureValidation.

**Test 8 — Unexpected algorithms.** Thay SignatureMethod, DigestMethod, C14N method hoặc transforms ngoài allowlist; từ chối trước khi dùng kết quả nghiệp vụ.

**Test 9 — Weak key.** Dùng RSA-1024 hoặc EC curve ngoài policy trong môi trường test; không cho ký mới hoặc chấp nhận theo policy mới dù JDK có thể hỗ trợ kỹ thuật.

**Test 10 — External URI.** `Reference URI` trỏ `file://`/`http://`; không có file/network I/O, verify fail closed.

**Test 11 — XPath/XSLT transform.** Reject transforms không nằm trong profile, không thực hiện arbitrary stylesheet/expression từ XML.

**Test 12 — Signature wrapping.** Có hai business nodes tương tự, một signed một unsigned; dù cryptographic signature trên signed node valid, app phải chỉ xử lý đúng node đã ký.

**Test 13 — Duplicate IDs.** Hai DOM elements có cùng `Id` hoặc khác case/namespace mang ID giống nhau; policy phải reject, không phụ thuộc finder mơ hồ.

**Test 14 — C14N/namespace differences.** Serialize rồi parse lại tài liệu, đổi namespace prefixes trong các điều kiện tương thích; verify theo canonicalization/profile, không giả định mọi sửa XML đều bất biến.

**Test 15 — Comment handling.** Với/không có comments, dùng C14N variant đã khai; xác minh logic khi comments nằm trong phạm vi được ký.

**Test 16 — Parser XXE.** DOM từ XML hostile có DOCTYPE/external entity, parser phải chặn trước XMLDSig verification; không chỉ tin `secureValidation`.

**Test 17 — Certificate trust.** `SignatureValue` valid với key không nằm truststore: phải fail authentication/authorization layer.

**Test 18 — Revocation/time.** Khi profile yêu cầu, kiểm tra CRL/OCSP, validity/timestamp/time evidence; xác minh crypto đơn thuần chưa đủ.

**Test 19 — Runtime provider change.** Nâng JDK/HSM/XML provider: chạy lại algorithm URI support, PSS params, security policy, C14N/transforms và negative tests.

**Test 20 — Resource budgets.** XML lớn, nhiều References/transforms, data URI/out-of-band resource, quá sâu/rộng: enforce size/count/timeouts; không để verifier tải/buffer vô hạn.

**Test 21 — Key rotation.** Sau rotation, signer mới dùng key mới; verifier chọn trusted key theo issuer/key identifier đã xác thực, không tự “tin” KeyInfo mới.

**Test 22 — Multiple signatures.** Tài liệu chứa 2+ Signatures phải có rule signer được phép và reference coverage; không chọn `item(0)` rồi xác nhận toàn document.

**Test 23 — HMAC.** Nếu có HMAC_SHA256, kiểm tra symmetric secret scope/rotation/entropy, không coi đó là public signature có non-repudiation.

**Test 24 — Compliance profile.** Kiểm tra profile của đối tác/chứng thư/HSM và thuật toán được tổ chức chấp nhận; JDK “can sign” chưa phải chính sách cho phép.

### 15.1. Kiểm thử không được dừng ở verify=true

Một integration test chuẩn nên assert ít nhất:

```text
(1) Algorithm policy              PASS
(2) Reference + transforms policy PASS
(3) Cryptographic signature       PASS
(4) Trusted key/certificate       PASS
(5) Signed business node identity PASS
(6) Schema/business validation    PASS
=> mới chấp nhận operation
```

Nếu chỉ có `(3)`, việc nhận một XMLDSig có chữ ký hợp lệ của kẻ tấn công không có nghĩa ứng dụng được phép thực hiện giao dịch.

## 16. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| “SHA-256 là toàn bộ chữ ký XML.” | Nhầm digest với signature method. | Phân biệt DigestMethod, SignatureMethod, C14N, transforms và Reference. |
| Dùng `"SHA256withRSA"` làm XMLDSig URI. | Provider không hiểu hoặc sai profile. | Dùng `SignatureMethod.RSA_SHA256`. |
| Thấy `RSA_SHA1` constant nên tiếp tục ký mới. | Thuật toán legacy, bị policy chặn. | Không phát hành SHA-1/MD5, dùng allowlist mạnh. |
| Bật `secureValidation=false` để vượt lỗi. | Làm mất giới hạn bảo vệ XMLDSig. | Giữ secureValidation và sửa profile/đầu vào. |
| Key RSA 1024 + SHA-512 thì an toàn. | Khóa quá yếu bất kể hash mạnh. | RSA ≥2048, thường RSA-3072 theo policy. |
| Dùng ECDSA method với RSA key. | Wrong key type/provider error. | Ghép EC key/curve với ECDSA; RSA key với RSA variants. |
| Đưa Ed25519 vào code `--release 17`. | Constant XMLDSig không tồn tại ở JDK17. | Dùng từ Java21+ hoặc lựa chọn RSA/ECDSA cho Java17. |
| Coi Ed25519 luôn được đối tác chấp nhận. | Interop và compliance fail. | Kiểm tra partner/HSM/PKI/policy. |
| Coi HMAC_SHA256 là chữ ký công khai có non-repudiation. | Trust model sai. | Chỉ dùng cho shared-secret MAC use cases. |
| Trộn `RSA_PSS` với `SHA256_RSA_MGF1` bất kỳ. | URI/parameters không khớp. | Chọn theo XMLDSig profile thống nhất. |
| Thay CanonicalizationMethod sau khi ký. | SignedInfo bytes khác, verify fail. | Giữ C14N theo signed profile và allowlist. |
| Bỏ enveloped transform khi chữ ký nằm trong XML đã ký. | Reference digest có thể tự bao gồm Signature. | Dùng transform phù hợp, kiểm thử round-trip. |
| Cho phép XPath/XSLT transforms tùy ý. | Rủi ro security và ký nhầm dữ liệu. | Strict transform allowlist; cấm không cần thiết. |
| Tin public key bất kỳ trong KeyInfo. | Attacker tự ký và xác minh được. | Trust chain/pinning independent. |
| Verify=true rồi lấy business node bất kỳ. | Signature wrapping/unsigned data attack. | Ràng buộc đúng signed node identity/ID. |
| Cho external Reference URI tùy ý. | File/network access, SSRF, sai nội dung ký. | Same-document references hoặc controlled dereferencer. |
| Tin parser DOM mặc định an toàn. | XXE xảy ra trước XMLDSig verification. | Harden DocumentBuilderFactory và input budgets. |
| Không test partner thật. | Ký được local, verifier ngoài từ chối. | Interop tests cho URI, PSS, C14N, certificate chain. |
| “Provider hỗ trợ” nghĩa là “được FIPS-approved”. | Suy diễn tuân thủ sai. | Xác minh module/provider và chính sách được phê duyệt. |
| Verify tài liệu cũ bằng cách sửa XML algorithm URI. | Chữ ký bị phá, provenance mất. | Ký lại/archival validation qua quy trình riêng. |

## 17. Câu hỏi ôn tập

**Câu 1.** `DigestMethod.SHA256` và `SignatureMethod.RSA_SHA256` khác nhau thế nào?

**Đáp án:** DigestMethod hash dữ liệu của Reference sau transforms. SignatureMethod dùng khóa ký để xác thực SignedInfo đã canonicalize. Một cái không thay thế cái kia.

**Câu 2.** Một API constant có trên JDK có nghĩa thuật toán được phép trong ứng dụng không?

**Đáp án:** Không. Còn phụ thuộc JCA/XMLDSig provider, key/parameters, secureValidation, interop và chính sách tổ chức.

**Câu 3.** RSA-PSS/SHA-256 khác RSA-SHA256 như thế nào?

**Đáp án:** RSA-PSS dùng cơ chế padding chữ ký PSS với các tham số hash/MGF/salt/trailer; RSA-SHA256 XMLDSig mô tả RSA PKCS#1 v1.5 signature encoding. Cả hai có thể dùng SHA-256 nhưng URI/encoding và profile khác nhau.

**Câu 4.** `SignatureMethod.RSA_PSS` mặc định dùng những tham số nào trên JDK17+?

**Đáp án:** Theo Javadoc: SHA-256, MGF1(SHA-256), salt 32 bytes và trailer field 1 khi truyền `null` parameter spec.

**Câu 5.** Ed25519 trong XMLDSig API có từ Java nào?

**Đáp án:** `SignatureMethod.ED25519`/`ED448` từ Java 21. Đối với Java 17, dùng thuật toán XMLDSig đã có như RSA-SHA256/ECDSA-SHA256/RSA-PSS.

**Câu 6.** Vì sao RSA-1024 không nên được chọn dù một JDK có thể chỉ chặn khóa nhỏ hơn 1024?

**Đáp án:** Ngưỡng tối thiểu runtime không phải tiêu chuẩn thiết kế. Ứng dụng nên đặt chính sách khóa mới mạnh hơn, như RSA ≥2048 hoặc 3072 theo thời hạn.

**Câu 7.** `CanonicalizationMethod.EXCLUSIVE` có thay thế SHA-256 không?

**Đáp án:** Không. C14N chuẩn hóa biểu diễn XML; digest hash bytes đã chuẩn hóa; SignatureMethod ký SignedInfo.

**Câu 8.** Dùng `Reference URI=""` cùng enveloped transform là gì?

**Đáp án:** Ký document theo same-document reference, loại bỏ chính phần tử Signature khỏi digest để tránh self-reference. Phải kiểm tra profile/nội dung mục tiêu trong ứng dụng.

**Câu 9.** `secureValidation` có thay thế kiểm tra certificate trust không?

**Đáp án:** Không. Nó hạn chế algorithms/constructs nguy hiểm; một private key do attacker sở hữu vẫn có thể tạo chữ ký hợp lệ với public key tương ứng.

**Câu 10.** Có thể tin khóa public được nhúng trong `KeyInfo` không?

**Đáp án:** Không tự động. KeyInfo là dữ liệu có thể do attacker cung cấp; cần chứng minh trust qua PKI/pinning/source độc lập.

**Câu 11.** Một XMLSignature validate true có đảm bảo app đang đọc đúng `<Order>` đã ký không?

**Đáp án:** Không. Phải ràng buộc Reference, ID uniqueness, namespace/position và business object identity để chống signature wrapping.

**Câu 12.** Tại sao không nên bật XSLT transforms của XMLDSig với input không tin cậy?

**Đáp án:** Transform có thể thay nội dung được digest, tiêu tốn tài nguyên hoặc truy cập external resources; JDK secure validation cũng cấm XSLT transforms theo mặc định.

**Câu 13.** Có nên cho phép SHA-1 verify tài liệu cũ bằng cách tắt secureValidation toàn service?

**Đáp án:** Không. Xử lý archived signatures trong quy trình riêng được security/compliance phê duyệt, không hạ chính sách production path.

**Câu 14.** `DigestMethod.SHA3_256` có nghĩa Java17 hỗ trợ `SignatureMethod.ECDSA_SHA3_256` không?

**Đáp án:** Không. XMLDSig ECDSA-SHA3 constants được bổ sung từ Java 25; RSA-MGF1 SHA-3 từ Java 22. Digest và SignatureMethod có các lộ trình API khác nhau.

**Câu 15.** Tại sao demo tạo private/public keys trong RAM?

**Đáp án:** Để chạy độc lập và không yêu cầu secrets. Production phải quản lý key material theo policy HSM/KMS/keystore, rotation và audit.

**Câu 16.** Chọn HMAC-SHA256 có thể phục vụ hai bên không muốn chia sẻ private signing key không?

**Đáp án:** HMAC là shared-secret MAC: cả hai bên phải biết cùng secret và đều có khả năng tạo MAC. Nếu cần bằng chứng từ riêng một người ký, chọn asymmetric signature + trust phù hợp.

## 18. Checklist lựa chọn thuật toán trong dự án thật

1. Xác định JDK version tối thiểu: Java17 có RSA-SHA256/RSA-PSS/ECDSA-SHA256; Ed25519 XMLDSig cần Java21+.
2. Xác minh profile/chính sách và thuật toán mà đối tác/HSM/PKI thực tế chấp nhận.
3. Chọn `SignatureMethod` mạnh với đúng key type/size; RSA thường ≥2048, cân nhắc 3072; ECDSA P-256/P-384 đúng policy.
4. Chọn `DigestMethod.SHA256`/SHA-384/512 phù hợp; không phát hành SHA-1/MD5.
5. Chọn `CanonicalizationMethod` theo profile, kiểm tra namespaces/comments.
6. Chọn `Transforms` tối thiểu; với enveloped signature, tránh tự-reference.
7. Hạn chế `Reference URI` và chỉ cho phép signed objects đúng nghiệp vụ.
8. Bật `org.jcp.xml.dsig.secureValidation`/kiểm tra JDK security policy; không hạ policy chỉ vì verify lỗi.
9. Có **application allowlist** cho signature/digest/C14N/transforms và giới hạn số references.
10. Dùng DOM parser hardening, hạn chế XML bytes/depth/entities và external access ngay ở tầng input.
11. Không lấy public key trong `KeyInfo` làm trust root; xác minh certificate chain/usage/revocation/time theo profile.
12. Ràng buộc node nghiệp vụ với Reference đã verify; kiểm tra duplicate IDs và signature wrapping.
13. Test sign/verify trên **đúng JDK, provider, HSM, peer**; riêng RSA-PSS cần thống nhất URI/parameters.
14. Test tampering, wrong public key, unsupported/legacy algorithms, external URIs, unsafe transforms, weak keys.
15. Không tự retry bằng cách downgrade sang SHA-1 hoặc tắt secureValidation.
16. Không log private keys, credentials, signed XML có PII, certificate secrets hoặc raw parser diagnostics chưa scrub.
17. Có key rotation, signer identity và audit trail rõ; phân biệt chữ ký mới với archived legacy signatures.
18. Kiểm tra tương tác khi nâng JDK/provider/PKI profile; không tự suy từ `SignatureMethod` constant là được chấp nhận.
19. Phân biệt chữ ký bất đối xứng và HMAC: trust model, verification parties, giá trị chứng cứ khác nhau.
20. Chỉ chấp nhận operation khi **algorithm + reference + cryptographic signature + trusted signer + business data** cùng PASS.

## 19. Tài liệu chính thức và chuẩn liên quan

- [Java SE 17 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/17/security/java-xml-digital-signature-api-overview-and-tutorial.html): JSR 105, tạo/xác minh XMLDSig, secureValidation.
- [Java SE 25 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/25/security/java-xml-digital-signature-api-overview-and-tutorial.html): chính sách hiện hành, hạn chế transforms/algorithms/Reference URI.
- [Java SE 17 — SignatureMethod](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml.crypto/javax/xml/crypto/dsig/SignatureMethod.html): RSA_SHA256, ECDSA_SHA256, RSA_PSS và các URI XMLDSig Java17.
- [Java SE 25 — SignatureMethod](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/SignatureMethod.html): ED25519/ED448 từ Java21, SHA3 URI theo phiên bản.
- [Java SE 17 — DigestMethod](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml.crypto/javax/xml/crypto/dsig/DigestMethod.html): SHA-256/384/512 và digests.
- [Java SE 17 — XMLSignatureFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html): newSignatureMethod, newDigestMethod, newSignedInfo, newXMLSignature.
- [Java SE 17 — DOMValidateContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMValidateContext.html): trusted key, ID registration và validation context.
- [Java SE 17 — Reference](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml.crypto/javax/xml/crypto/dsig/Reference.html): URI, transforms, digest algorithm.
- [Java SE 17 — CanonicalizationMethod](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml.crypto/javax/xml/crypto/dsig/CanonicalizationMethod.html): XML C14N algorithm URIs.
- [Oracle JDK 25 — Security Properties File](https://docs.oracle.com/en/java/javase/25/security/security-properties-file.html): `jdk.xml.dsig.secureValidationPolicy` và cấu hình provider.
- [Oracle JDK 25 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): DOM/XSLT/XSD parser hardening và external resource controls.
- [W3C — XML Signature Syntax and Processing Version 1.1](https://www.w3.org/TR/xmldsig-core1/): XMLDSig Reference, SignedInfo, transforms, algorithms và validation.
- [OWASP — XML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_Security_Cheat_Sheet.html): xác minh dữ liệu XML an toàn, XML Signature và parser security.
