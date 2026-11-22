# KeyInfo, lựa chọn khóa và nguồn tin cậy trong chữ ký XML (Java)

## 1. Mục tiêu: chữ ký đúng chưa chắc người ký đáng tin

**XML Digital Signature (XMLDSig)** cho phép ký và kiểm tra tính toàn vẹn của những phần được tham chiếu trong XML. Trong Java, các API hiện hành thuộc module `java.xml.crypto`, đặc biệt `javax.xml.crypto.dsig`, `javax.xml.crypto.dsig.keyinfo` và `javax.xml.crypto.KeySelector`.

Một chữ ký có thể **hợp lệ về mật mã** nhưng **không đáng tin về danh tính người ký**. Ví dụ kẻ tấn công tự tạo cặp khóa RSA, ký XML bằng private key của chính họ, rồi đặt public key vào `<KeyInfo><KeyValue>...</KeyValue></KeyInfo>`. Nếu ứng dụng lấy khóa từ chính XML và gọi `XMLSignature.validate()`, phép kiểm tra mật mã có thể trả `true`: chữ ký đúng với khóa mà người gửi đã đưa vào. Nhưng điều đó **không chứng minh khóa thuộc đối tác hợp pháp**.

Bài **“KeyInfo, lựa chọn khóa và nguồn tin cậy”**, thuộc chủ đề **Chữ ký XML**, làm rõ ba lớp kiểm tra cần tách biệt:

1. **Cryptographic signature validation:** chữ ký và digest của các `Reference` có đúng với khóa được chọn không?
2. **Key trust/authorization:** khóa hoặc chứng thư có nằm trong tập được ứng dụng tin cậy **từ một nguồn độc lập** không, có đúng đối tác, mục đích và thời điểm không?
3. **Document semantics:** dữ liệu ứng dụng tiêu thụ có thực sự là **phần đã được ký**, đúng cấu trúc, đúng ID và đúng transaction/request không?

Chỉ sau khi cả ba lớp phù hợp với chính sách nghiệp vụ mới có thể chấp nhận một thông điệp XML.

Sau bài, bạn sẽ biết:
- Cấu trúc `Signature`, `SignedInfo`, `Reference`, `DigestValue`, `SignatureValue` và `KeyInfo`.
- Ý nghĩa và giới hạn của `KeyValue`, `KeyName`, `X509Data`, `RetrievalMethod`.
- Vai trò `KeySelector` và `DOMValidateContext`.
- Vì sao `KeyInfo` là *gợi ý tìm khóa*, không phải trust anchor.
- Cách lấy key từ cấu hình/trust store/PKI đã được tin cậy và chống giả mạo tên khóa.
- Sự khác nhau giữa **public-key pinning**, **PKIX certificate-path validation**, **signer identity policy** và **signature verification**.
- Cách bảo vệ `Reference URI`, tránh external URI, duplicate IDs và XML Signature Wrapping.
- Cách dùng `org.jcp.xml.dsig.secureValidation` đúng với JDK hiện hành.
- Cách thiết kế chính sách rotation, diagnostics và integration tests.

**Tính hiện hành:** Java SE 26 vẫn cung cấp XML Digital Signature API. Ví dụ đầy đủ dùng Java 17+, RSA-2048 với RSA-SHA256 và SHA-256, chạy hoàn toàn trên JDK, không cần thư viện bên ngoài. Đã biên dịch `javac --release 17` và chạy trên OpenJDK 24: **23/23 assertions PASS**.

## 2. Nhìn toàn bộ XML Signature trước khi nói về KeyInfo

Ví dụ cấu trúc minh họa của một chữ ký XML:

```xml
<Envelope>
  <Payload Id="payload">amount=100;to=partner</Payload>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:SignedInfo>
      <ds:CanonicalizationMethod Algorithm="..." />
      <ds:SignatureMethod Algorithm="..." />
      <ds:Reference URI="#payload">
        <ds:Transforms>...</ds:Transforms>
        <ds:DigestMethod Algorithm="..." />
        <ds:DigestValue>...</ds:DigestValue>
      </ds:Reference>
    </ds:SignedInfo>
    <ds:SignatureValue>...</ds:SignatureValue>
    <ds:KeyInfo>
      <ds:KeyValue>...</ds:KeyValue>
    </ds:KeyInfo>
  </ds:Signature>
</Envelope>
```

Các dấu `...` là chỗ lược bớt trong **sơ đồ minh họa**, không phải XML đầy đủ có thể dùng để xác minh. Chương trình ở phần 12 mới tạo XMLDSig thật.

Các thành phần:

| Thành phần | Vai trò | Điểm bảo mật |
| --- | --- | --- |
| `SignedInfo` | Chứa thuật toán và các `Reference` được ký | Chỉ chấp nhận tập thuật toán và references phù hợp policy |
| `Reference URI` | Cho biết node/nguồn dữ liệu được digest | Không tự ý lấy dữ liệu ở URI ngoài hoặc ID không mong muốn |
| `DigestValue` | Digest của nội dung đã transform | Kiểm tra integrity của nội dung reference |
| `SignatureValue` | Chữ ký trên `SignedInfo` canonicalized | Cần public key đúng mới kiểm tra được |
| `KeyInfo` | Thông tin giúp bên nhận **tìm** khóa | **Không tự chứng minh khóa đáng tin** |
| `KeyValue` | Public key được nhúng trong XML | Kẻ gửi XML cũng có thể tự tạo khóa |
| `KeyName` | Tên/alias gợi ý khóa | Tên được gửi có thể giả mạo |
| `X509Data` | Chứng thư/issuer/serial/subject/SKI... | Certificate nằm trong XML vẫn cần trust validation riêng |

Trong XMLDSig thường gặp, `KeyInfo` nằm ngoài `SignedInfo` và không tự động được bảo vệ bởi chữ ký, trừ khi có `Reference` riêng bảo vệ nó. Dù có được ký, thông tin khóa **vẫn không thể tự tạo niềm tin từ chính nó**; phải có nguồn trust độc lập.

### 2.1. Điều gì xảy ra khi verify?

```text
Nhận XML không đáng tin
        |
        v
Parse XML an toàn, có giới hạn
        |
        v
Xác định đúng Signature + Payload + Reference
        |
        v
Đọc KeyInfo (gợi ý, không phải authority)
        |
        v
KeySelector / trusted-key registry / PKIX
        |
        +-- Không tìm thấy khóa đáng tin -> REJECT
        |
        v
XMLSignature.validate(context)
        |
        +-- Digest / Signature invalid -> REJECT
        |
        v
Kiểm tra policy: đúng đối tác, tài liệu, quyền, thời gian
        |
        +-- Không phù hợp -> REJECT
        |
        v
Tiêu thụ CHÍNH node Payload đã xác minh
```

Không đảo lộn quy trình thành “tìm bất kỳ public key trong XML, thấy `validate==true`, tin mọi trường trong document”.

## 3. `KeyInfo` thực sự có nghĩa gì?

`javax.xml.crypto.dsig.keyinfo.KeyInfo` đại diện cho thẻ `<ds:KeyInfo>`. Nó là một `XMLStructure` chứa danh sách các cấu trúc hỗ trợ tìm key.

Các API cơ bản:

```java
KeyInfoFactory kif = xmlSignatureFactory.getKeyInfoFactory();
KeyInfo info = kif.newKeyInfo(
        List.of(kif.newKeyName("partner-prod")));
```

Đây là **snippet**, cần `xmlSignatureFactory` hợp lệ và imports từ `javax.xml.crypto.dsig.keyinfo` / `java.util`.

`KeyInfo.getContent()` trả danh sách không rỗng, không sửa được, có thể chứa nhiều loại `XMLStructure`. `KeyInfo.getId()` trả ID tùy chọn nếu có.

Theo Oracle Java SE 26 XML Digital Signature API tutorial, `KeySelector` tìm và **có thể xác thực** key dựa trên thông tin trong `KeyInfo`. Tài liệu cũng cảnh báo selector chỉ lấy `KeyValue` để xác minh là **ví dụ học thuật**, nó **không kiểm tra khóa có đáng tin không**.

### 3.1. KeyInfo không bắt buộc phải có

`KeyInfo` là tùy chọn trong XMLDSig. Khi ứng dụng **đã biết khóa trusted từ config**, có thể dùng:

```java
DOMValidateContext context =
        new DOMValidateContext(trustedPublicKey, signatureNode);
```

Đây là snippet; `trustedPublicKey` phải đến từ **nguồn cấu hình đáng tin**, `signatureNode` phải là đúng `ds:Signature`. Khi dùng constructor nhận `Key`, `DOMValidateContext` sẽ dùng singleton key selector tương ứng. **Không cần KeyInfo** mới có thể xác minh bằng một public key đã biết.

Đây thường là lựa chọn dễ kiểm soát cho tích hợp cố định chỉ với một đối tác/khóa.

## 4. Các kiểu nội dung KeyInfo và mức độ tin cậy

### 4.1. `KeyValue`: công khai key nhưng không chứng minh danh tính

XML có thể nhúng RSA/DSA/EC public-key material theo provider và chuẩn XMLDSig:

```xml
<ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:KeyValue>
    <!-- Nội dung public key theo chuẩn XMLDSig -->
  </ds:KeyValue>
</ds:KeyInfo>
```

Một selector ngây thơ:

```java
if (structure instanceof KeyValue keyValue) {
    return () -> keyValue.getPublicKey();
}
```

Đây chỉ là **ý tưởng minh họa**, không phải implementation đầy đủ của `KeySelector`. Nó chọn public key từ chính XML chưa tin cậy. Với một thông điệp do kẻ tấn công tự ký bằng khóa của họ, kết quả xác minh mật mã có thể vẫn là `true`.

Cách an toàn hơn khi hệ thống dùng pinning:
- Lấy **trusted public key** từ trust registry/keystore được quản trị độc lập.
- Nếu `KeyValue` được gửi, so khớp nó với khóa đã pin, hoặc bỏ qua và dùng khóa trusted.
- Chỉ trả trusted key cho verifier.
- Không tự “onboard” một key mới chỉ vì một XML có `KeyValue` chưa biết.

### 4.2. `KeyName`: alias, không phải định danh đã xác thực

`KeyName` chứa tên gợi ý, ví dụ `partner-prod`:

```xml
<ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:KeyName>partner-prod</ds:KeyName>
</ds:KeyInfo>
```

Giá trị này **do nguồn XML đưa vào**, có thể bị đặt thành bất kỳ tên nào. Nó chỉ hữu ích nếu ứng dụng có **mapping bên ngoài XML**:

```text
"partner-prod" -> public key đã được duyệt trong trusted registry
"partner-old"  -> key cũ còn hiệu lực trong rollover window
"unknown"      -> REJECT
```

Một attacker có thể ghi `partner-prod` vào KeyInfo, nhưng **không thể tạo chữ ký hợp lệ bằng private key của đối tác chỉ bằng cách đặt đúng tên**. Selector tìm ra key trusted, rồi `SignatureValue` vẫn phải được kiểm tra bằng key đó.

Không cho phép một `KeyName` mới tự tạo một entry trong trusted registry.

### 4.3. `X509Data`: thông tin chứng thư X.509

`X509Data` có thể chứa:
- `X509Certificate`;
- `X509IssuerSerial`;
- `X509SubjectName`;
- `X509SKI` (subject key identifier);
- `X509CRL`;
- hoặc các cấu trúc theo contract.

Nó giúp tìm certificate hoặc chuỗi certificate liên quan, nhưng **certificate được gửi trong XML chưa phải trust anchor**.

Để tin một chữ ký dựa trên X.509, ứng dụng thường phải:
1. Tìm candidate leaf certificate/public key.
2. Xây dựng và xác minh **certificate path** theo PKIX tới trust anchor **đã cấu hình bên ngoài XML**.
3. Kiểm tra thời hạn hiệu lực theo thời điểm xác minh có chính sách rõ ràng.
4. Kiểm tra key usage phù hợp, chính sách extended key usage nếu áp dụng.
5. Kiểm tra revocation (CRL/OCSP) theo policy, bao gồm fail-open/fail-closed được quy định rõ.
6. Gắn chứng thư đã xác thực với **đúng đối tác/tenant/role** mà hệ thống cho phép ký loại tài liệu này.
7. Dùng public key của leaf đã được chấp nhận để xác minh XMLDSig.
8. Chỉ tiêu thụ nội dung đã ký sau khi cấu trúc và business policy đạt yêu cầu.

**Đặc biệt:** Certificate chain hợp lệ tới một CA công khai **không tự động có quyền ký đơn hàng/tài liệu nội bộ của bạn**. Identity và authorization là bước riêng. Ngược lại, một dịch vụ chỉ cần tin một partner key đã pin thì không nhất thiết cần PKI nếu contract cho phép pinning.

### 4.4. `RetrievalMethod`: tham chiếu để tìm khóa

`RetrievalMethod` có thể chứa URI/tham chiếu đến nội dung khóa. Nếu một chương trình tự động tải external URL từ untrusted KeyInfo, nó có thể tạo rủi ro SSRF và sai trust boundary.

Chính sách mặc định an toàn:
- Không tự dereference external URL từ untrusted `RetrievalMethod`.
- Hạn chế remote resolution bằng `URIDereferencer` hoặc từ chối hoàn toàn.
- Nếu cần external key directory, endpoint phải đến từ **trusted configuration**, có identity/TLS, policy, caching, timeout và rotation riêng.
- Việc tải thành công certificate/public key **không chứng minh nó đáng tin**.

## 5. Phân tách bốn quyết định về “đáng tin”

| Quyết định | Câu hỏi cần trả lời | Nơi xử lý |
| --- | --- | --- |
| **Key discovery** | Lấy public key candidate từ đâu? | KeyInfo/KeyName/KeyValue/X509Data hoặc cấu hình |
| **Key trust** | Key có thuộc tập được chấp nhận không? | Pinning, trusted registry, certificate-path policy |
| **Crypto validation** | Chữ ký/digest có đúng với selected key không? | `XMLSignature.validate()` |
| **Authorization + payload binding** | Key này có quyền ký tài liệu/đối tác đó và đúng signed object không? | Business + XML structure policy |

Không thể gộp cả bốn thành một boolean chỉ bằng cách gọi `XMLSignature.validate()`.

### 5.1. Key material không đồng nghĩa trust anchor

Trusted sources có thể là:
- Public key/certificate đã được provision qua kênh quản trị bảo mật.
- Keystore local `PKCS12`/`JKS` được triển khai và cập nhật có kiểm soát.
- Trust anchors dùng cho PKIX và partner identity rules.
- Một key registry/KMS/HSM được xác thực và kiểm soát quyền.
- Key configuration versioned theo partner/tenant/environment.

Untrusted inputs gồm:
- `KeyValue` embedded trong XML.
- `KeyName` hoặc `X509SubjectName` do người gửi khai báo.
- Certificate chain do chính XML đính kèm nếu chưa được validated.
- `RetrievalMethod` URL do XML chỉ định.

### 5.2. Khi nào dùng pinning?

**Public-key pinning** hữu ích nếu tích hợp có số lượng đối tác ít và biết trước public key. Ứng dụng lấy key từ nguồn tin cậy, kiểm tra public key embedded trùng key trusted (nếu có), và verify. Quản trị phải có:
- Khóa mới được approved **out-of-band**.
- Trusted key sets theo partner và thuật toán.
- Rollover window có hạn sử dụng.
- Key revocation/emergency removal.
- Auditing cho mọi thay đổi trust configuration.

Không cập nhật pin tự động khi XML có KeyValue không khớp. Pinning làm giảm phụ thuộc CA nhưng chuyển trách nhiệm key lifecycle cho tổ chức.

### 5.3. Khi nào dùng PKIX?

**PKIX path validation** phù hợp khi policy dựa trên một hệ thống PKI: nhiều khóa/certificates, chain tới CA trusted và xác định identity dựa trên certificate attributes.

`CertPathValidator.getInstance("PKIX")`, `PKIXParameters`, `TrustAnchor` và `CertPathBuilder` là các Java Security APIs hiện hành. Tuy nhiên certificate chain/trust chỉ là một phần; ứng dụng còn phải map signer vào role/tenant và các signing profiles được phép.

### 5.4. Thời điểm kiểm tra

Chữ ký có thể được tạo trước khi certificate hết hạn nhưng đến lúc verify certificate đã hết hạn. Quyết định tin chữ ký lịch sử cần **trusted timestamp hoặc bằng chứng thời gian**, certificate status và chính sách lưu trữ/chứng cứ. Không đơn giản lấy một `SigningTime` do XML tự khai và coi nó là mốc thời gian đáng tin.

## 6. `KeySelector` và `DOMValidateContext`

`javax.xml.crypto.KeySelector` là abstract class với method:

```java
KeySelectorResult select(
        KeyInfo keyInfo,
        KeySelector.Purpose purpose,
        AlgorithmMethod method,
        XMLCryptoContext context)
        throws KeySelectorException;
```

Mỗi tham số:

- `keyInfo`: gợi ý tìm khóa, có thể `null` nếu không được đưa vào.
- `purpose`: mục đích sử dụng khóa, ví dụ `VERIFY`.
- `method`: thuật toán liên quan, như RSA-SHA256.
- `context`: context của phiên xử lý XML crypto; có thể chứa config của ứng dụng.
- `KeySelectorResult`: đối tượng trả về `Key` được chọn.

Một implementation thực tế nên:
- Nhận dạng đúng `purpose` và algorithm allowlist.
- Không tùy tiện tìm khóa từ untrusted URI.
- Tìm partner key chỉ trong nguồn tin cậy.
- Từ chối KeyInfo rỗng, unknown alias hoặc key không được phép.
- Giữ key/trust policy nhất quán với document type/tenant.

### 6.1. DOMValidateContext nhận trực tiếp một trusted key

```java
DOMValidateContext ctx =
        new DOMValidateContext(knownPartnerPublicKey, signatureElement);
ctx.setProperty(
        "org.jcp.xml.dsig.secureValidation",
        Boolean.TRUE);
```

Nếu chỉ có một partner key trusted, cách này có thể đơn giản hơn tự viết `KeySelector`. Nhưng application **vẫn** cần kiểm soát Reference URI, signed element, document structure và authorization.

### 6.2. Khi có nhiều keys: selector theo trusted registry

`KeyName` chỉ là alias. Registry do ứng dụng quản lý:

```java
Map<String, PublicKey> approved = Map.of(
        "partner-prod", trustedPartnerPublicKey
);
```

Selector có thể dùng alias để lấy đúng key **đã có trong approved**. Đừng viết code nếu alias không có thì tự lấy embedded `KeyValue` rồi coi là trusted; đó là **fallback fail-open**.

### 6.3. Các exception cần xử lý

`KeySelectorException` có thể xảy ra khi selector không tìm được khóa hợp lệ. Trong DOM XMLDSig validation, nó có thể được wrap thành `XMLSignatureException`. `MarshalException` xảy ra khi XMLDSig không hợp lệ hoặc không thể unmarshal.

Ứng dụng production nên:
- Từ chối validation thất bại.
- Ghi safe error categories, không log private key hay toàn bộ XML chứa dữ liệu bí mật.
- Không retry bằng cách **tắt secureValidation** hoặc dùng random `KeyValue`.
- Không trả chi tiết trusted-key registry ra public response.

## 7. `secureValidation`, thuật toán và giới hạn chính sách

JDK hiện hành hỗ trợ:

```java
context.setProperty(
        "org.jcp.xml.dsig.secureValidation",
        Boolean.TRUE);
```

Theo tài liệu Java SE 26, **secure validation mode được bật mặc định** trên JDK provider. Nó áp dụng các ràng buộc trong `jdk.xml.dsig.secureValidationPolicy`, chẳng hạn giới hạn transforms/references, cấm nhiều thuật toán yếu, hạn chế external URI schemes, duplicate IDs và một số kiểu reference/transform nguy hiểm. Chi tiết policy có thể thay đổi theo JDK update.

**Không tắt secure validation để giải quyết chữ ký thất bại**. Nếu một hệ thống cũ dùng MD5, SHA-1 hoặc transforms không còn phù hợp, hướng đi là cập nhật format/protocol của người gửi, không hạ bảo vệ cho untrusted XML.

**Quan trọng về override:** System property `org.jcp.xml.dsig.secureValidation` có thể **ghi đè** giá trị được đặt trong `DOMValidateContext`, theo JDK. Kiểm tra startup/runtime configuration; đừng tuyên bố chỉ mỗi lệnh `setProperty(..., TRUE)` bảo đảm bất biến nếu ứng dụng cho phép system property tắt mode.

### 7.1. Thuật toán trong ví dụ

Ví dụ dùng:
- `SignatureMethod.RSA_SHA256`.
- `DigestMethod.SHA256`.
- `CanonicalizationMethod.EXCLUSIVE`.
- Một `Reference URI="#payload"`.
- Một exclusive canonicalization transform cho reference.
- Cặp khóa RSA **2048-bit** chỉ để kiểm thử trong bộ nhớ.

Đây là lựa chọn còn áp dụng với Java 17+. Với production, thuật toán/độ dài khóa cần tuân thủ security policy của tổ chức, thời gian lưu trữ và profile tương tác đối tác; không suy rằng minimum do JDK secureValidation cho phép chính là khuyến nghị bảo mật của công ty.

Không dùng `SignatureMethod.RSA_SHA1` hoặc `DigestMethod.SHA1` làm lựa chọn mới khi đã có SHA-256. Không tự đặt algorithm URI lấy từ XML thành một thuật toán “được phép” mà không qua allowlist.

### 7.2. Canonicalization không có nghĩa mọi data đều được ký

Canonicalization chuẩn hóa cách byte hóa node được ký. Nó không biến **mọi sibling XML element** thành signed data. Nếu `Reference` chỉ trỏ tới `#payload`, các sibling ngoài `Payload` không được bảo vệ chỉ nhờ chúng ở chung `Envelope`.

## 8. XML Signature Wrapping và reference binding

XML wrapping là nhóm lỗi ứng dụng **xác minh một node nhưng sử dụng node khác**.

Ví dụ nguy hiểm:
- Chữ ký tham chiếu `#payload` hợp lệ.
- Kẻ tấn công thêm một `Payload` thứ hai có giá trị gian lận.
- Code nghiệp vụ lấy “Payload đầu tiên/ở vị trí tiện lợi” mà không chắc nó là node đã được verify.
- Hệ thống chấp nhận dữ liệu **không nằm trong tập được ký**.

Các kiểm tra cần có trước/sau validation:
1. Có đúng số lượng `Signature` theo protocol.
2. `Signature` nằm đúng vị trí cấu trúc mong đợi.
3. Có đúng `Payload` được phép, parent node đúng.
4. ID của phần tử mục tiêu là duy nhất trong scope đã kiểm soát.
5. `SignedInfo` có đúng số lượng `Reference` và URI được phép.
6. Không dereference `http:`, `https:`, `file:` hoặc URI bất ngờ.
7. Digest/signature/transform algorithms nằm trong allowlist.
8. Đưa **chính phần tử đã được tham chiếu và xác minh** cho business logic.
9. Nếu XML schema có phép chứa thêm nodes, chỉ tin các nodes đã ký theo contract.
10. Không chỉ dựa vào `getElementsByTagName("Amount").item(0)` trên toàn tài liệu nếu chưa xác minh cấu trúc.

### 8.1. ID attribute phải được đăng ký đúng

DOM thường không tự coi một attribute tên `Id` là XML ID. Dùng:

```java
validateContext.setIdAttributeNS(
        payloadElement, null, "Id");
```

Lệnh này đăng ký ID đã được xác định bởi ứng dụng để resolving `URI="#payload"`. Nó **không** thay việc kiểm tra duplicate IDs và đúng vị trí. Đừng để untrusted XML tự chọn một ID trùng rồi tin lookup luôn đúng node.

### 8.2. Custom URIDereferencer

Có thể giới hạn đúng URI được phép:

```java
URIDereferencer base = signatureFactory.getURIDereferencer();
validateContext.setURIDereferencer(
        (reference, cryptoContext) -> {
            if (!"#payload".equals(reference.getURI())) {
                throw new URIReferenceException(
                        "Only the expected local reference is allowed");
            }
            return base.dereference(reference, cryptoContext);
        });
```

Đây là snippet cần các biến `signatureFactory` và `validateContext`. Phương pháp này không bảo đảm toàn bộ policy nếu ứng dụng còn các chỗ dereference ở layer khác, nhưng chặn một đường reference không mong muốn tại điểm validate.

## 9. Các mô hình trust thường dùng

### 9.1. A — Đối tác duy nhất, public key đã biết

```text
Trusted deploy configuration:
  partner A -> PublicKey A
               |
               v
DOMValidateContext(PublicKey A, Signature)
               |
               v
XMLSignature.validate()
               |
               v
Business signature profile + payload binding
```

Không cần `KeyInfo`. Nếu bên gửi có KeyInfo, validator không nhất thiết phải dùng nó.

### 9.2. B — Nhiều đối tác, KeyName chỉ là hint

```text
<ds:KeyName>partner-prod</ds:KeyName>  [UNTRUSTED]
               |
               v
Map from approved config
               |
               v
PublicKey of approved "partner-prod"
               |
               v
Crypto + authorization validation
```

Chỉ mapping được key từ registry không đủ nếu XML của đối tác B lại yêu cầu quyền đối tác A. Cần gắn registry với **expected sender identity** do transport/tenant/business context cung cấp.

### 9.3. C — Certificate chain với X509Data

```text
<X509Data>certificate(s)</X509Data> [UNTRUSTED CANDIDATES]
                  |
                  v
Certificate path verification (PKIX)
             trusted anchor(s)
                  |
                  v
Validity/revocation/keyUsage/identity policy
                  |
                  v
Leaf public key -> XMLSignature.validate()
                  |
                  v
Signed payload + business authorization
```

Không tin root CA nằm trong XML như một root CA của chính mình. `TrustAnchor` phải đến từ **nguồn ngoài XML**. Tham chiếu `X509IssuerSerial` hoặc subject name chỉ giúp *lookup*, không bảo đảm identity.

## 10. `X509Data` và PKIX: phân biệt xác thực certificate với XMLDSig

Một mô tả ngắn cho Java certificate validation:

```java
CertificateFactory cf = CertificateFactory.getInstance("X.509");
CertPath path = cf.generateCertPath(
        List.of(leafCertificate, intermediateCertificate));

PKIXParameters params = new PKIXParameters(trustedTrustAnchors);
params.setRevocationEnabled(true);

CertPathValidator validator =
        CertPathValidator.getInstance("PKIX");
validator.validate(path, params);

PublicKey verifiedKey = leafCertificate.getPublicKey();
```

Đây là **snippet minh họa, không chạy độc lập**: `leafCertificate`, `intermediateCertificate` và `trustedTrustAnchors` phải được cấp từ PKI/cấu hình đã xác thực; chain trong `generateCertPath` được sắp từ leaf đến intermediates và thường không đặt trust anchor vào path. `setRevocationEnabled(true)` còn cần cơ chế CRL/OCSP/cert stores/network policy phù hợp với triển khai. Không coi việc bật flag đã bảo đảm kết quả revocation được truy vấn đúng.

Production cần bổ sung:
- `leafCertificate.checkValidity(...)` theo validation-time policy.
- Kiểm tra `KeyUsage` cho digital signature nếu profile bắt buộc.
- Kiểm tra `ExtendedKeyUsage` khi có yêu cầu cụ thể.
- Kiểm tra subject/SAN hoặc certificate policy theo expected partner identity.
- Kiểm tra revocation và rotation theo trust policy.
- Không chấp nhận unknown CA, self-signed certificate từ XML làm trust anchor.
- Không cho fallback sang “bất kỳ KeyValue nào trong KeyInfo” nếu PKIX fail.

Đối với dữ liệu đã ký lâu dài, dấu thời gian đáng tin và chứng cứ revocation lịch sử là một chủ đề riêng. Không suy ra một XML `SigningTime` chưa được bảo vệ là bằng chứng thời gian.

### 10.1. Keystore được provision ngoài XML

Một public key đã được phê duyệt có thể nằm trong keystore:

```java
KeyStore store = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(keystorePath)) {
    store.load(in, keystorePassword);
}

Certificate cert = store.getCertificate("partner-prod");
if (cert == null) {
    throw new GeneralSecurityException("Unknown trusted partner");
}
PublicKey approvedKey = cert.getPublicKey();
```

Đây là **snippet tích hợp**: cần `keystorePath`, `keystorePassword` do hệ thống secrets/config quản lý và imports `java.security.*`, `java.security.cert.Certificate`, `java.io.InputStream`, `java.nio.file.Files`. Nếu keystore chứa **trusted leaf certificate pinned**, khóa công khai đó có thể là trust source theo hợp đồng pinning. Nếu keystore chỉ chứa **CA roots**, vẫn cần PKIX path + signer identity validation, không tự gán mọi leaf signed by CA là đối tác được phép.

## 11. Thiết kế bộ kiểm thử: ký thật, xác minh thật và tách trust

Ví dụ Java 17+ sau không dùng mock XMLDSig. Nó dùng JDK DOM XML Digital Signature implementation để:
1. Tạo hai cặp RSA-2048 độc lập: **partner** và **attacker**.
2. Ký `Payload Id="payload"` bằng RSA-SHA256 và SHA-256.
3. Ghi `KeyInfo` ở dạng `KeyValue` hoặc `KeyName`.
4. Xác minh bằng **pinned public key**, **trusted alias registry** hoặc trực tiếp bằng public key đã biết.
5. Cho thấy **unsafe selector** lấy bất kỳ `KeyValue` nào sẽ chấp nhận chữ ký attacker về mặt mật mã.
6. Cho thấy pinned selector/direct trusted key **từ chối** cùng chữ ký attacker.
7. Chứng minh giả mạo `KeyName` không tạo ra private key của partner.
8. Phát hiện payload bị chỉnh sửa.
9. Xác minh XML có thể được ký **không cần KeyInfo** khi key được biết ngoài XML.
10. Từ chối duplicate ID, thêm Payload thứ hai, external Reference URI và nhiều Signature nodes.
11. Bật `secureValidation` và chỉ dereference `#payload`.
12. Restrict signature/digest/canonicalization/transform algorithms.

**Thiết kế bảo vệ:** Code chỉ chấp nhận **một `Envelope` có một `Payload` và một `Signature`**. Đây là profile XML giả định của bài, không phải profile chung của mọi XMLDSig implementations. Trên production, cần schema và rules theo đúng message format, không copy cứng tên `Envelope/Payload` vào các định dạng khác.

Bộ test đã chạy với `javac --release 17` và OpenJDK 24: **23/23 PASS**.

## 12. Chương trình Java 17+ hoàn chỉnh — `XmlSignatureTrustDemo.java`

Lưu **nguyên file** dưới đây. Không cần Maven, Gradle hay thư viện XMLDSig bên ngoài.

```java
import java.security.Key;
import java.security.KeyException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.util.List;
import java.util.Map;
import javax.xml.XMLConstants;
import javax.xml.crypto.AlgorithmMethod;
import javax.xml.crypto.KeySelector;
import javax.xml.crypto.KeySelectorException;
import javax.xml.crypto.KeySelectorResult;
import javax.xml.crypto.URIReferenceException;
import javax.xml.crypto.XMLCryptoContext;
import javax.xml.crypto.XMLStructure;
import javax.xml.crypto.dsig.CanonicalizationMethod;
import javax.xml.crypto.dsig.DigestMethod;
import javax.xml.crypto.dsig.Reference;
import javax.xml.crypto.dsig.SignatureMethod;
import javax.xml.crypto.dsig.SignedInfo;
import javax.xml.crypto.dsig.Transform;
import javax.xml.crypto.dsig.XMLSignature;
import javax.xml.crypto.dsig.XMLSignatureException;
import javax.xml.crypto.dsig.XMLSignatureFactory;
import javax.xml.crypto.dsig.dom.DOMSignContext;
import javax.xml.crypto.dsig.dom.DOMValidateContext;
import javax.xml.crypto.dsig.keyinfo.KeyInfo;
import javax.xml.crypto.dsig.keyinfo.KeyInfoFactory;
import javax.xml.crypto.dsig.keyinfo.KeyName;
import javax.xml.crypto.dsig.keyinfo.KeyValue;
import javax.xml.crypto.dsig.spec.C14NMethodParameterSpec;
import javax.xml.crypto.dsig.spec.TransformParameterSpec;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

public final class XmlSignatureTrustDemo {
    private static int passed;

    static void check(String label, boolean success) {
        if (!success) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    static KeyPair keyPair() throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048);
        return g.generateKeyPair();
    }

    static Document newDocument(String text) throws Exception {
        DocumentBuilderFactory b = DocumentBuilderFactory.newInstance();
        b.setNamespaceAware(true);
        b.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        b.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        b.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
        b.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
        b.setFeature(
                "http://apache.org/xml/features/nonvalidating/load-external-dtd",
                false);
        b.setXIncludeAware(false);
        b.setExpandEntityReferences(false);
        b.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        b.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        Document doc = b.newDocumentBuilder().newDocument();
        Element envelope = doc.createElement("Envelope");
        doc.appendChild(envelope);

        Element payload = doc.createElement("Payload");
        payload.setAttribute("Id", "payload");
        payload.setIdAttribute("Id", true);
        payload.setTextContent(text);
        envelope.appendChild(payload);
        return doc;
    }

    static Document sign(String text, KeyPair pair, String keyName,
                         boolean includeKeyInfo) throws Exception {
        Document doc = newDocument(text);
        Element root = doc.getDocumentElement();
        Element payload = (Element)
                root.getElementsByTagName("Payload").item(0);

        XMLSignatureFactory factory =
                XMLSignatureFactory.getInstance("DOM");

        Reference ref = factory.newReference(
                "#payload",
                factory.newDigestMethod(DigestMethod.SHA256, null),
                List.of(factory.newTransform(
                        CanonicalizationMethod.EXCLUSIVE,
                        (TransformParameterSpec) null)),
                null, null);

        SignedInfo signedInfo = factory.newSignedInfo(
                factory.newCanonicalizationMethod(
                        CanonicalizationMethod.EXCLUSIVE,
                        (C14NMethodParameterSpec) null),
                factory.newSignatureMethod(
                        SignatureMethod.RSA_SHA256, null),
                List.of(ref));

        KeyInfo info = null;
        if (includeKeyInfo) {
            KeyInfoFactory kif = factory.getKeyInfoFactory();
            XMLStructure entry = keyName == null
                    ? kif.newKeyValue(pair.getPublic())
                    : kif.newKeyName(keyName);
            info = kif.newKeyInfo(List.of(entry));
        }

        DOMSignContext context =
                new DOMSignContext(pair.getPrivate(), root);
        context.setIdAttributeNS(payload, null, "Id");

        XMLSignature signature =
                factory.newXMLSignature(signedInfo, info);
        signature.sign(context);
        return doc;
    }

    static final class PinnedKeyValue extends KeySelector {
        final PublicKey trusted;

        PinnedKeyValue(PublicKey trusted) {
            this.trusted = trusted;
        }

        @Override
        public KeySelectorResult select(
                KeyInfo info,
                Purpose purpose,
                AlgorithmMethod method,
                XMLCryptoContext context)
                throws KeySelectorException {

            if (!SignatureMethod.RSA_SHA256.equals(
                    method.getAlgorithm())) {
                throw new KeySelectorException(
                        "Signature algorithm not allowed");
            }
            if (info == null) {
                throw new KeySelectorException("KeyInfo missing");
            }

            for (XMLStructure structure : info.getContent()) {
                if (structure instanceof KeyValue kv) {
                    try {
                        PublicKey offered = kv.getPublicKey();
                        if (MessageDigest.isEqual(
                                trusted.getEncoded(),
                                offered.getEncoded())) {
                            return () -> trusted;
                        }
                    } catch (KeyException e) {
                        throw new KeySelectorException(e);
                    }
                }
            }
            throw new KeySelectorException(
                    "KeyValue not pinned");
        }
    }

    static final class AliasFromTrustedConfig
            extends KeySelector {
        final Map<String, PublicKey> trustedAliases;

        AliasFromTrustedConfig(
                Map<String, PublicKey> aliases) {
            trustedAliases = Map.copyOf(aliases);
        }

        @Override
        public KeySelectorResult select(
                KeyInfo info,
                Purpose purpose,
                AlgorithmMethod method,
                XMLCryptoContext context)
                throws KeySelectorException {

            if (!SignatureMethod.RSA_SHA256.equals(
                    method.getAlgorithm())) {
                throw new KeySelectorException(
                        "Signature algorithm not allowed");
            }
            if (info == null) {
                throw new KeySelectorException("KeyInfo missing");
            }

            for (XMLStructure item : info.getContent()) {
                if (item instanceof KeyName name) {
                    PublicKey trusted =
                            trustedAliases.get(name.getName());
                    if (trusted != null) return () -> trusted;
                }
            }
            throw new KeySelectorException(
                    "Unknown key alias");
        }
    }

    // ONLY for a security-negative demonstration, never for trust.
    static final class UnsafeKeyValue extends KeySelector {
        @Override
        public KeySelectorResult select(
                KeyInfo info,
                Purpose purpose,
                AlgorithmMethod method,
                XMLCryptoContext context)
                throws KeySelectorException {

            if (info == null) {
                throw new KeySelectorException("Missing KeyInfo");
            }

            for (XMLStructure item : info.getContent()) {
                if (item instanceof KeyValue kv) {
                    try {
                        Key key = kv.getPublicKey();
                        return () -> key;
                    } catch (KeyException ex) {
                        throw new KeySelectorException(ex);
                    }
                }
            }
            throw new KeySelectorException("No KeyValue");
        }
    }

    static boolean validate(Document doc, KeySelector selector)
            throws Exception {
        return validate(doc, selector, null);
    }

    static boolean validate(
            Document doc, KeySelector selector,
            PublicKey directKey) throws Exception {

        XMLSignatureFactory factory =
                XMLSignatureFactory.getInstance("DOM");

        Element root = doc.getDocumentElement();
        if (!"Envelope".equals(root.getTagName())) return false;

        NodeList payloads = root.getElementsByTagName("Payload");
        if (payloads.getLength() != 1) return false;

        Element payload = (Element) payloads.item(0);
        if (payload.getParentNode() != root) return false;
        if (!"payload".equals(payload.getAttribute("Id"))) {
            return false;
        }

        // Duplicate ID values are never permitted by this profile.
        NodeList all = doc.getElementsByTagName("*");
        int idCount = 0;
        for (int i = 0; i < all.getLength(); i++) {
            Element e = (Element) all.item(i);
            if (e.hasAttribute("Id")
                    && "payload".equals(e.getAttribute("Id"))) {
                idCount++;
            }
        }
        if (idCount != 1) return false;

        NodeList signatures = doc.getElementsByTagNameNS(
                XMLSignature.XMLNS, "Signature");
        if (signatures.getLength() != 1) return false;
        if (signatures.item(0).getParentNode() != root) {
            return false;
        }

        DOMValidateContext context = directKey != null
                ? new DOMValidateContext(
                        directKey, signatures.item(0))
                : new DOMValidateContext(
                        selector, signatures.item(0));

        context.setProperty(
                "org.jcp.xml.dsig.secureValidation",
                Boolean.TRUE);
        context.setIdAttributeNS(payload, null, "Id");

        var safeDereferencer =
                factory.getURIDereferencer();
        context.setURIDereferencer(
                (reference, cryptoContext) -> {
                    if (!"#payload".equals(reference.getURI())) {
                        throw new URIReferenceException(
                                "Only #payload is permitted");
                    }
                    return safeDereferencer.dereference(
                            reference, cryptoContext);
                });

        try {
            XMLSignature sig =
                    factory.unmarshalXMLSignature(context);
            SignedInfo signedInfo = sig.getSignedInfo();

            if (!SignatureMethod.RSA_SHA256.equals(
                    signedInfo.getSignatureMethod()
                            .getAlgorithm())) {
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

            Reference ref = (Reference)
                    signedInfo.getReferences().get(0);
            if (!"#payload".equals(ref.getURI())) return false;
            if (!DigestMethod.SHA256.equals(
                    ref.getDigestMethod().getAlgorithm())) {
                return false;
            }
            if (ref.getTransforms().size() != 1) {
                return false;
            }

            Transform transform = (Transform)
                    ref.getTransforms().get(0);
            if (!CanonicalizationMethod.EXCLUSIVE.equals(
                    transform.getAlgorithm())) {
                return false;
            }

            return sig.validate(context);

        } catch (XMLSignatureException
                 | javax.xml.crypto.MarshalException ex) {
            // Demo only. Production should record safe diagnostics.
            return false;
        }
    }

    static boolean verifyDirect(
            Document doc, PublicKey trusted)
            throws Exception {
        return validate(doc, null, trusted);
    }

    static void mutatePayload(Document doc, String text) {
        ((Element) doc.getElementsByTagName("Payload").item(0))
                .setTextContent(text);
    }

    static void addDuplicateId(Document doc) {
        Element extra = doc.createElement("AnotherNode");
        extra.setAttribute("Id", "payload");
        extra.setTextContent("Forged claim");
        doc.getDocumentElement().appendChild(extra);
    }

    static void replaceReferenceWithExternal(Document doc) {
        NodeList refs = doc.getElementsByTagNameNS(
                XMLSignature.XMLNS, "Reference");
        ((Element) refs.item(0)).setAttribute(
                "URI", "https://example.invalid/never-fetch");
    }

    public static void main(String[] args) throws Exception {
        KeyPair partner = keyPair();
        KeyPair attacker = keyPair();

        check("independent-rsa-keys",
                !MessageDigest.isEqual(
                        partner.getPublic().getEncoded(),
                        attacker.getPublic().getEncoded()));
        check("rsa-2048-demo-key",
                ((java.security.interfaces.RSAPublicKey)
                        partner.getPublic()).getModulus()
                        .bitLength() == 2048);

        Document good =
                sign("amount=100;to=partner", partner, null, true);

        check("keyvalue-present",
                good.getElementsByTagNameNS(
                        XMLSignature.XMLNS, "KeyValue")
                        .getLength() == 1);
        check("trusted-keyvalue-validated",
                validate(good,
                        new PinnedKeyValue(partner.getPublic())));
        check("trusted-direct-key-validated",
                verifyDirect(good, partner.getPublic()));
        check("wrong-pinned-key-rejected",
                !validate(good,
                        new PinnedKeyValue(attacker.getPublic())));

        Document selfSignedByAttacker =
                sign("amount=999999;to=attacker",
                        attacker, null, true);

        check("attacker-signature-cryptographically-valid",
                validate(selfSignedByAttacker,
                        new UnsafeKeyValue()));
        check("attacker-not-trusted-by-pinning",
                !validate(selfSignedByAttacker,
                        new PinnedKeyValue(partner.getPublic())));
        check("attacker-not-trusted-by-direct-key",
                !verifyDirect(selfSignedByAttacker,
                        partner.getPublic()));

        Document edited =
                sign("amount=100", partner, null, true);
        mutatePayload(edited, "amount=1000000");

        check("payload-tampering-detected",
                !validate(edited,
                        new PinnedKeyValue(partner.getPublic())));

        Document aliasDoc =
                sign("id=7;status=OK", partner,
                        "partner-prod", true);

        check("keyname-present",
                aliasDoc.getElementsByTagNameNS(
                        XMLSignature.XMLNS, "KeyName")
                        .getLength() == 1);

        KeySelector aliases = new AliasFromTrustedConfig(
                Map.of("partner-prod", partner.getPublic()));

        check("trusted-keyname-alias-resolves",
                validate(aliasDoc, aliases));
        check("trusted-keyname-validates-with-direct-key",
                verifyDirect(aliasDoc, partner.getPublic()));
        check("unknown-alias-rejected",
                !validate(aliasDoc,
                        new AliasFromTrustedConfig(
                                Map.of("other-partner",
                                        partner.getPublic()))));

        Document aliasImpersonation =
                sign("id=8;status=FORGED",
                        attacker, "partner-prod", true);
        check("spoofed-alias-cannot-forge-signature",
                !validate(aliasImpersonation, aliases));

        Document noKeyInfo =
                sign("id=9", partner, null, false);

        check("no-keyinfo-allowed-with-external-key",
                verifyDirect(noKeyInfo, partner.getPublic()));
        check("no-keyinfo-rejected-by-pinned-hint-selector",
                !validate(noKeyInfo,
                        new PinnedKeyValue(partner.getPublic())));

        Document duplicate =
                sign("id=10", partner, null, true);
        addDuplicateId(duplicate);
        check("duplicate-id-rejected",
                !validate(duplicate,
                        new PinnedKeyValue(partner.getPublic())));

        Document duplicatedPayload =
                sign("id=11", partner, null, true);
        Element second =
                duplicatedPayload.createElement("Payload");
        second.setAttribute("Id", "other");
        second.setTextContent("Untrusted copy");
        duplicatedPayload.getDocumentElement().appendChild(second);

        check("unexpected-payload-rejected",
                !validate(duplicatedPayload,
                        new PinnedKeyValue(partner.getPublic())));

        Document externalRef =
                sign("id=12", partner, null, true);
        replaceReferenceWithExternal(externalRef);

        check("external-reference-rejected-before-dereference",
                !validate(externalRef,
                        new PinnedKeyValue(partner.getPublic())));

        Document secondSignature =
                sign("id=13", partner, null, true);

        Element originalSig = (Element)
                secondSignature.getElementsByTagNameNS(
                        XMLSignature.XMLNS, "Signature").item(0);
        secondSignature.getDocumentElement().appendChild(
                originalSig.cloneNode(true));

        check("multiple-signatures-rejected",
                !validate(secondSignature,
                        new PinnedKeyValue(partner.getPublic())));

        Document goodAgain =
                sign("hello=world", partner,
                        "partner-prod", true);
        check("separate-validate-context-reusable-policy",
                validate(goodAgain, aliases));

        check("java-xml-crypto-factory-dom",
                XMLSignatureFactory.getInstance("DOM") != null);

        System.out.println("passed=" + passed);
    }
}
```

### 12.1. Biên dịch và chạy

Trong thư mục có file:

```bash
javac --release 17 -encoding UTF-8 XmlSignatureTrustDemo.java
java XmlSignatureTrustDemo
```

Chạy bằng JDK 17+ trên Linux/macOS hoặc Windows PowerShell nếu `java`/`javac` nằm trên PATH. Không cần database, thư viện Apache Santuario ngoài JDK, khóa private production hay certificate thật. Chương trình tạo hai cặp khóa **trong RAM** và mỗi lần chạy chữ ký có giá trị bytes khác nhau, nhưng tên assertions/output không đổi khi chạy thành công.

**Không đưa private key thật vào source code/test fixture.** Production nên dùng keystore/KMS/HSM hoặc secret management phù hợp; thông số crypto phải đáp ứng policy hiện hành.

### 12.2. Stdout đã kiểm chứng trên OpenJDK 24

```text
PASS independent-rsa-keys
PASS rsa-2048-demo-key
PASS keyvalue-present
PASS trusted-keyvalue-validated
PASS trusted-direct-key-validated
PASS wrong-pinned-key-rejected
PASS attacker-signature-cryptographically-valid
PASS attacker-not-trusted-by-pinning
PASS attacker-not-trusted-by-direct-key
PASS payload-tampering-detected
PASS keyname-present
PASS trusted-keyname-alias-resolves
PASS trusted-keyname-validates-with-direct-key
PASS unknown-alias-rejected
PASS spoofed-alias-cannot-forge-signature
PASS no-keyinfo-allowed-with-external-key
PASS no-keyinfo-rejected-by-pinned-hint-selector
PASS duplicate-id-rejected
PASS unexpected-payload-rejected
PASS external-reference-rejected-before-dereference
PASS multiple-signatures-rejected
PASS separate-validate-context-reusable-policy
PASS java-xml-crypto-factory-dom
passed=23
```

**Kết quả:** `javac --release 17` PASS, chạy trên OpenJDK 24 **23/23 assertions PASS**.

### 12.3. Tại sao đây là ví dụ bảo mật đáng nhớ?

Nhìn hai dòng:

```text
PASS attacker-signature-cryptographically-valid
PASS attacker-not-trusted-by-pinning
```

Chúng **không mâu thuẫn**. Chữ ký của attacker đúng về mật mã khi sử dụng public key do chính attacker nhúng; nhưng public key đó không thuộc tập trusted keys của đối tác, nên hệ thống đúng phải **từ chối**.

`UnsafeKeyValue` trong code là **một anti-pattern có chủ đích để làm negative demonstration**. **Không sử dụng class này trong production để xác thực danh tính hoặc phân quyền**. Oracle tutorial cũng mô tả KeyValueKeySelector đơn giản là ví dụ tìm key, không kiểm tra trust.

## 13. Phân tích các nhóm test

| Nhóm kiểm thử | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Hai cặp RSA độc lập | `independent-rsa-keys` | Attacker không có private key của partner |
| KeyValue | `keyvalue-present` | XML có thể mang public key |
| PinnedKeyValue | `trusted-keyvalue-validated` | Embedded key phải trùng trusted key |
| Direct key | `trusted-direct-key-validated` | Có thể bỏ qua KeyInfo khi key trusted đã biết |
| Wrong trust | `wrong-pinned-key-rejected` | Chữ ký thật của partner không hợp lệ với pin sai |
| Unsafe KeyValue | `attacker-signature-cryptographically-valid` | Chỉ verify bằng khóa tự khai không xác thực identity |
| Safe trust | `attacker-not-trusted-by-pinning` | Pinning chặn key lạ |
| Payload integrity | `payload-tampering-detected` | Sửa phần đã ký làm digest/signature fail |
| KeyName alias | `trusted-keyname-alias-resolves` | Tên chỉ chọn key trong registry |
| Spoofing | `spoofed-alias-cannot-forge-signature` | Chỉ đặt tên đúng không tạo chữ ký bằng private key trusted |
| No KeyInfo | `no-keyinfo-allowed-with-external-key` | KeyInfo optional khi trusted key được cung cấp riêng |
| Duplicate ID | `duplicate-id-rejected` | Giảm rủi ro ID reference confusion |
| Duplicate Payload | `unexpected-payload-rejected` | Tránh app đọc payload giả |
| External URI | `external-reference-rejected-before-dereference` | Không tải URI không mong muốn |
| Multiple Signatures | `multiple-signatures-rejected` | Profile đòi đúng một signature |
| Separate Context | `separate-validate-context-reusable-policy` | Mỗi validation dùng context mới |

**Giới hạn của fixture:** Nó tạo DOM XML từ đầu bằng `DocumentBuilder.newDocument()` chứ **không parse raw XML từ attacker**. Khi dùng XML nhận từ network/file, ứng dụng còn cần **DOM parser chống XXE**, byte/depth limits và validation structure đầy đủ. Nó chứng minh chính sách khóa và References đã test; không thay thế audit security hay integration testing cho một XML signing protocol cụ thể.

## 14. Xây bộ xác minh production theo nguyên tắc fail closed

### 14.1. Parse XML an toàn trước khi verify

Với untrusted XML, cấu hình DOM parser:
- `DocumentBuilderFactory.setNamespaceAware(true)`.
- Chặn DOCTYPE và external entities.
- `ACCESS_EXTERNAL_DTD=""`, `ACCESS_EXTERNAL_SCHEMA=""`.
- Chặn XInclude khi không dùng.
- Giới hạn input bytes, độ sâu, timeouts.
- Từ chối provider nếu không thực thi được security settings.
- Không parse lại XML bằng một parser yếu sau khi đã verify.

**Lưu ý:** XMLDSig DOM API và StAX là hai chủ đề khác nhau. Đừng nghĩ chỉ vì một pipeline dùng một StAX parser an toàn ở bước đầu, bước DOM parse nội bộ ở bước sau tự được bảo vệ.

### 14.2. Bắt đúng exception khi validate

```java
try {
    XMLSignature signature =
            xmlSignatureFactory.unmarshalXMLSignature(validateContext);
    boolean cryptographicallyValid =
            signature.validate(validateContext);
    if (!cryptographicallyValid) {
        throw new SecurityException("Signature invalid");
    }
} catch (javax.xml.crypto.MarshalException
         | javax.xml.crypto.dsig.XMLSignatureException ex) {
    throw new SecurityException(
            "XML signature rejected", ex);
}
```

Đây là **snippet trong method** cần `xmlSignatureFactory` và `validateContext` hợp lệ. Production còn có thể gặp lỗi cấu hình/algorithm/KeySelector cần log category an toàn. Không phản hồi raw private key, full XML hoặc secret values.

### 14.3. Xác thực nguồn tin cậy và chữ ký nên có kết quả riêng

Thay vì một boolean “valid” duy nhất, nên phân loại:
- `UNTRUSTED_KEY`: không tìm được key đã được duyệt.
- `BAD_SIGNATURE`: signature cryptographic verification fail.
- `BAD_REFERENCE`: Reference không đúng expected signed object.
- `BAD_ALGORITHM`: algorithm/transform bị cấm.
- `BAD_CERT_PATH`: X.509 certificate path không đạt policy.
- `UNAUTHORIZED_SIGNER`: key được tin ở cấp PKI nhưng không có quyền ký tài liệu này.
- `MALFORMED_XML`: XML parse/schema/structure không hợp lệ.
- `EXPIRED_OR_REVOKED`: ký dựa vào cert không còn hợp lệ theo policy.
- `POLICY_MISMATCH`: tenant/partner/document type sai.

Đây là **gợi ý error taxonomy của ứng dụng**, không phải các constants có sẵn trong JDK. Đừng trả quá chi tiết về trusted-key database cho người gửi chưa xác thực.

### 14.4. Tránh TOCTOU trên DOM

Javadoc `DOMValidateContext` ghi rõ: hành vi của một `XMLSignature` được unmarshal là **undefined nếu caller thay đổi underlying DOM tree sau đó**. Vì vậy:
- Không chia sẻ một mutable DOM giữa threads để người khác thay đổi trong lúc verify.
- Không thay payload sau khi verify nhưng trước khi business consume.
- Không reuse cùng `DOMValidateContext` với nhiều `XMLSignature` khác nhau.
- Tạo validation context mới cho mỗi document/signature.
- Sau khi verify, truyền trực tiếp immutable/trusted representation của **đúng signed node** vào business layer.

## 15. Key rotation, partner identity và môi trường

Một ứng dụng thật nên lưu trust policy như cấu hình có version:

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `partnerId` | `partner-A` | Identity từ trusted partner registry |
| `environment` | `production` | Không nhầm staging keys với production |
| `keyId` | `partner-A-2026` | Nhãn versioned, không tự là authority |
| `algorithm` | `RSA-SHA256` | Allowed signature algorithm |
| `publicKeyFingerprint` | SHA-256 của SPKI bytes | So khớp key pin; fingerprint lấy từ trusted config |
| `notBefore/notAfter` | Policy dates | Window chấp nhận key |
| `documentTypes` | invoice/payment | Quyền ký theo loại tài liệu |
| `status` | approved/retired/revoked | Lifecycle |
| `source` | PKCS12/KMS/config | Nguồn provision đáng tin |

Khi key rotation:
1. Tạo/nhận new public key qua authenticated out-of-band process.
2. Review và approve key mới trước khi sử dụng.
3. Cho phép overlap có hạn nếu protocol cần.
4. Gắn keyID và expected partner identity.
5. Thu hồi key cũ đúng lịch, có emergency revoke.
6. Log keyID đã match, không log private key hoặc toàn bộ certificate chain nếu không cần.
7. Không cho XML tự gia hạn trust khi KeyInfo đưa key lạ.

**Không suy rằng việc XML ghi `KeyName="partner-A"` chứng minh nó thuộc partner A**. Alias chỉ là lookup hint, còn chữ ký phải xác minh bằng approved key và business context phải cho phép partner đó.

## 16. KeyInfo có thể chứa nhiều gợi ý: phải làm gì?

`KeyInfo.getContent()` có thể chứa cả `KeyName`, `KeyValue` và `X509Data`.

Một chính sách có thể:
- **Ưu tiên trusted external key**, bỏ qua KeyInfo nếu không cần.
- Chỉ cho `KeyName` và ánh xạ tới registry allowlist.
- Cho `KeyValue` nếu nó trùng với approved pinned key.
- Cho `X509Data` nếu certificate path + signer identity policy đã đạt.
- **Từ chối ambiguity** nếu nhiều nội dung KeyInfo mâu thuẫn, không dùng fallback chọn key “đầu tiên verify thành công” rồi tự coi trusted.
- Không dereference `RetrievalMethod` ngoài whitelist.

Nếu có nhiều candidates trusted do rotation, verifier có thể thử một **tập khóa nhỏ đã được phê duyệt**, nhưng cần ràng buộc partner/tenant/document type và giới hạn số lần thử để tránh DoS. Không “brute force” mọi public key trong toàn hệ thống.

## 17. Kiểm thử tích hợp và mô hình đe dọa

Bộ 23 checks chỉ xác minh contract đã thiết kế trên JDK implementation. Khi tích hợp thực, nên test thêm:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Chữ ký đúng, trusted key đúng | Chấp nhận nếu policy/structure đúng |
| Chữ ký đúng, KeyValue mới do attacker tạo | Từ chối do untrusted key |
| Chữ ký đúng, X509 self-signed nằm trong XML | Không tự coi là trusted |
| KeyName giả mạo alias trusted | Crypto verify fail nếu private key không khớp |
| Unknown KeyName | Từ chối, không fallback vào arbitrary KeyValue |
| Certificate chain đến unknown root | Từ chối PKIX |
| Certificate trusted CA nhưng sai partner role | Từ chối authorization |
| Certificate expired/revoked | Theo chính sách validation time/revocation |
| SignedInfo dùng thuật toán bị cấm | Từ chối |
| Reference external URL/file | Từ chối trước dereference |
| Reference trỏ node khác payload dự kiến | Từ chối |
| Duplicate ID, extra Payload | Từ chối hoặc validate schema profile nghiêm |
| Multiple signatures | Xử lý theo protocol, không mặc định chọn cái đầu |
| Payload bị sửa sau ký | Digest/signature fail |
| XML wrapping | Từ chối hoặc không consume unsigned replacement |
| DOCTYPE, external entity | Parser từ chối trước XMLDSig |
| Reader input quá lớn | Dừng theo request resource budgets |
| Unsupported transform/provider | Fail closed |
| Key rotation overlap | Chỉ các approved keys trong allowed period |
| System property tắt secureValidation | Chặn bằng deployment policy/health check |
| KeyInfo absent nhưng trusted key đã biết | Có thể validate theo protocol |
| KeyInfo chứa RetrievalMethod lạ | Không tự fetch |
| Retry/partial failure | Không fallback sang insecure selector |

**Tài liệu XMLDSig ngoài thực tế** có thể dùng detached signatures, enveloped signatures hoặc nhiều References. Bài dùng profile chỉ một `#payload` để dạy trust boundary. Không áp nguyên xi profile này cho SAML, WS-Security, e-invoice, các chuẩn ký tài liệu chính thức nếu protocol của chúng có quy tắc khác. Với các protocol phức tạp, ưu tiên thư viện/validator được duy trì và harden theo profile thay vì tự chắp vá generic XMLDSig DOM logic.

## 18. Các lỗi phổ biến cần tránh

**1. Dùng `KeyValue` từ XML như trust anchor.**  
Nó chỉ là public key tự khai; attacker có thể ký bằng khóa của chính họ.

**2. Coi `XMLSignature.validate()==true` là xác thực danh tính.**  
Chỉ kết luận signature/digest đúng với key đã chọn, chưa có identity/authorization.

**3. Dùng `KeyName` như bằng chứng người ký.**  
KeyName có thể tự đặt; phải lookup trong trusted registry rồi verify.

**4. Tin X509Certificate đính kèm trong X509Data ngay lập tức.**  
Certificate chưa được PKIX/identity policy kiểm tra thì chưa trusted.

**5. Coi certificate chain hợp lệ đến một CA là đủ để cho ký mọi tài liệu.**  
Cần đúng partner, key usage, document type và role.

**6. Cho `RetrievalMethod` tự tải arbitrary URLs.**  
Có nguy cơ SSRF, remote key substitution và resource exhaustion.

**7. Không kiểm tra `KeyInfo==null`.**  
KeyInfo optional. Dùng external trusted key nếu protocol cho phép.

**8. Nếu không tìm thấy trusted key, fallback vào KeyValue.**  
Đó là fail-open; phải từ chối.

**9. Không giới hạn algorithms.**  
Đừng chấp nhận thuật toán yếu hoặc transforms không cần thiết.

**10. Tắt secureValidation để “chạy được chữ ký”.**  
Đây là hạ bảo vệ, đặc biệt với XML untrusted.

**11. Nghĩ gọi `ctx.setProperty(..., TRUE)` luôn thắng system property.**  
JDK system property có thể override; cần quản lý startup config.

**12. Bỏ qua external URI references.**  
Signature validation có thể kéo theo việc lấy tài nguyên không mong muốn nếu dereferencer cho phép.

**13. Tin mọi node trong Envelope đã được ký.**  
Chỉ các referenced/transformed data mới được bảo vệ.

**14. Dùng node khác với node đã verified.**  
Mở đường cho XML Signature Wrapping.

**15. Không kiểm tra duplicate Id.**  
Có thể làm ambiguous ID resolution và khác biệt giữa validator và business code.

**16. Chỉ dùng `getElementsByTagName("Payload").item(0)` mà không kiểm tra structure.**  
Có thể chọn payload giả.

**17. Có nhiều chữ ký nhưng chỉ chọn chữ ký đầu tiên không theo protocol.**  
Cần rõ loại chữ ký nào chứng thực đối tượng nào, cùng policy cho tất cả required signatures.

**18. Tái sử dụng mutable `DOMValidateContext` cho nhiều signatures.**  
Javadoc cảnh báo kết quả không dự đoán được; tạo context mới.

**19. Sửa DOM sau khi unmarshal/verify rồi vẫn tin kết quả.**  
Không an toàn; giữ DOM bất biến trong validation/use path.

**20. Dùng public key pin mới xuất hiện làm key trusted tự động.**  
Cần on-boarding out-of-band và audited approval.

**21. Không có key rotation/revocation policy.**  
Có thể chấp nhận key đã bị thu hồi hoặc không có khả năng chuyển key an toàn.

**22. Không phân biệt staging và production keys.**  
Dễ để khóa test ký message production.

**23. Bỏ qua certificate revocation/time policy.**  
PKIX signature verification khác business validity và revocation.

**24. Dùng `SigningTime` trong unsigned XML làm thời điểm ký đáng tin.**  
Dữ liệu tự khai không thay trusted timestamp.

**25. Log raw private key, full unsigned XML hoặc certificate details không cần thiết.**  
Gây rò rỉ. Ghi safe key IDs, category và correlation IDs.

**26. Cho URI dereferencer truy cập file/network dựa trên keyinfo/references do XML đưa vào.**  
Chặn bằng allowlist và isolation.

**27. Coi cryptographic demo JDK-only đủ cho production.**  
Cần protocol profile, trust store, revocation/identity, key lifecycle và integration tests.

**28. Dùng cùng một signer policy cho mọi tenant.**  
Trusted keys phải được scope bởi partner/tenant/document type để ngăn key confusion.

**29. Coi KeyInfo có thể chứa một public key là đồng nghĩa private key cũng nằm trong XML.**  
Không. XMLDSig KeyInfo thường đưa **public key/certificate/key locator**; không nên chứa private key.

**30. Không kiểm tra algorithm/key compatibility trong KeySelector.**  
Selector nên ràng buộc đúng thuật toán và loại key được phép.

## 19. Câu hỏi tự kiểm tra

**1. `KeyInfo` có tự xác thực người ký không?**  
Không. Nó chủ yếu giúp **tìm** key để validate XML Signature.

**2. Vì sao chữ ký attacker tự ký có thể `validate()==true`?**  
Nếu ứng dụng dùng chính `KeyValue` attacker đưa vào, chữ ký khớp với key đó, nhưng không có trust.

**3. Khác nhau giữa `KeyValue` và `KeyName`?**  
KeyValue chứa public-key material; KeyName chứa chuỗi alias để lookup.

**4. KeyName có chống giả mạo được không?**  
Không tự nó. Chỉ khi registry trả key trusted và signature verify thành công bằng private-key counterpart.

**5. Nếu KeyInfo không có thì sao?**  
Vẫn có thể xác minh nếu public key trusted đã biết ngoài XML và protocol cho phép.

**6. `X509Data` chứa certificate có đủ chứng minh trusted không?**  
Không. Cần PKIX/trust anchor độc lập, revocation/validity và signer authorization policy.

**7. `TrustAnchor` nên lấy từ đâu?**  
Từ trust store/config đã được quản trị **ngoài XML không tin cậy**.

**8. PKIX valid có tự cho phép cert ký mọi business action không?**  
Không. Cần partner identity/role/document-type authorization.

**9. `RetrievalMethod` có thể gây rủi ro gì?**  
SSRF, tải dữ liệu ngoài trust boundary và resource abuse nếu cho phép arbitrary URI.

**10. Vì sao không chỉ kiểm tra `SignatureValue`?**  
Cần kiểm tra `Reference` digest, transforms, signer trust và đúng signed payload.

**11. `DOMValidateContext` có thể tạo bằng key trực tiếp không?**  
Có. Constructor nhận `Key`/`PublicKey` và Signature Node.

**12. `KeySelector.select` trả gì?**  
`KeySelectorResult` chứa `Key` được chọn để verify/sign tùy purpose.

**13. Vì sao nên giới hạn Reference thành `#payload` trong ví dụ?**  
Để verifier chỉ xử lý signed object được protocol dự kiến và không dereference URI ngoài.

**14. Duplicate ID có tác hại gì?**  
Gây ambiguous ID selection, dễ dẫn đến khác biệt giữa node xác minh và node business sử dụng.

**15. Secure validation mặc định ở JDK hiện hành thế nào?**  
Bật mặc định theo Java SE 26 JDK implementation; vẫn cần kiểm tra system property và policy.

**16. Key rotation an toàn cần gì?**  
Approval out-of-band, versioned trusted keys, overlap có giới hạn và revocation policy.

**17. Vì sao KeyInfo không nên được xem là always signed?**  
Trong thông điệp thông dụng nó nằm ngoài SignedInfo; chỉ được bảo vệ nếu format tạo Reference liên quan. Dù có được ký, trust vẫn phải từ ngoài.

**18. Tại sao phải consume đúng node đã verify?**  
Để tránh XML Signature Wrapping và chấp nhận unsigned replacement data.

**19. 23/23 PASS chứng minh điều gì?**  
Demo kiểm tra chính sách pinning/alias, signature/digest và những cấu trúc nguy hiểm đã tạo; không chứng minh mọi XMLDSig protocol production đã an toàn.

**20. Khi KeyInfo có key lạ hoặc cert không trusted, hệ thống nên làm gì?**  
**Từ chối**, không tự thêm trusted key hoặc fallback vào embedded KeyValue.

## 20. Tài liệu chính thức và hiện hành

- [Oracle Java SE 26 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/26/security/java-xml-digital-signature-api-overview-and-tutorial.html): cách generate/validate, `KeySelector` và cảnh báo selector lấy key từ KeyValue **không kiểm tra trust**.
- [Oracle Java SE 26 — `KeyInfo`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/keyinfo/KeyInfo.html): các XMLStructure hỗ trợ tìm key, `getContent()` và optional ID.
- [Oracle Java SE 26 — `KeyName`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/keyinfo/KeyName.html): alias/key identifier do signer khai báo.
- [Oracle Java SE 26 — `KeyValue`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/keyinfo/KeyValue.html): public key material trong KeyInfo.
- [Oracle Java SE 26 — `X509Data`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/keyinfo/X509Data.html): certificates và X.509 metadata.
- [Oracle Java SE 26 — `KeySelector`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/KeySelector.html): cách chọn key, `KeySelectorResult` và purpose.
- [Oracle Java SE 26 — `DOMValidateContext`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMValidateContext.html): trusted key hoặc selector, ID registration, secure-validation implementation note và cảnh báo mutable DOM.
- [Oracle Java SE 26 — `XMLSignature`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignature.html): core validation, SignatureValue và References.
- [Oracle Java SE 26 — `XMLSignatureFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html): DOM factory, unmarshalling, creating signatures.
- [Oracle Java SE 26 — `URIDereferencer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/URIDereferencer.html): URI reference dereferencing.
- [Oracle Java SE 26 — `CertPathValidator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertPathValidator.html): PKIX certificate path validation.
- [Oracle Java SE 26 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors, revocation và certificate-path policy.
- [Oracle Java SE 26 — `KeyStore`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html): quản trị keys/certificates theo trust source.

**Ghi nhớ:** `KeyInfo` cho biết **có thể tìm khóa ở đâu**, không chứng minh **có quyền tin khóa đó**. `KeyValue`, `KeyName`, `X509Data` và `RetrievalMethod` từ XML chưa tin cậy phải được kiểm tra với nguồn trust độc lập. Chỉ chấp nhận khi chữ ký và References hợp lệ **với trusted key**, signer được ủy quyền và application sử dụng đúng signed payload. Đó mới là cách xác minh chữ ký XML có ý nghĩa bảo mật.
