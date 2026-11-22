# Chữ ký XML: Phân biệt chữ ký hợp lệ với chứng chỉ đáng tin và nội dung đúng nghiệp vụ

## Mục tiêu học tập

Khi một hệ thống Java nhận hóa đơn, lệnh thanh toán, chứng từ hoặc thông điệp XML có **XML Digital Signature (XMLDSig)**, gọi **XMLSignature.validate(...)** trả về **true** là một kiểm tra quan trọng, nhưng **chưa đủ cơ sở để thực thi nghiệp vụ**.

Có ít nhất **ba câu hỏi độc lập** cần được trả lời:

1. **Chữ ký có hợp lệ về mặt mật mã và tham chiếu hay không?** Tức là XML Signature core validation thành công, bao gồm **Reference digest validation** và **SignatureValue validation**.
2. **Khóa công khai/chứng chỉ đại diện cho ai và có thực sự đáng tin theo chính sách của hệ thống không?** Một `KeyValue` hoặc `X509Data` nằm trong XML do người gửi tự cung cấp **không trở thành trust anchor chỉ vì chữ ký dùng được khóa đó**. Chứng chỉ X.509 cần được kiểm tra bằng chuỗi PKIX, trust anchors độc lập, mục đích sử dụng, danh tính, thời gian, revocation policy và các điều kiện liên quan.
3. **Thông tin XML được ký có phù hợp nghiệp vụ không?** Một số tiền âm, người nhận không được phép, `orderId` trùng, giao dịch quá hạn hoặc sai trạng thái vẫn có thể được ký bằng **khóa hợp lệ** và có **chữ ký mật mã đúng**.

Trong hệ thống thực tế nên có một câu hỏi thứ tư: **người sở hữu khóa/chứng chỉ đó có quyền thực hiện operation cụ thể này không?** Certificate chain hợp lệ **không tự cấp quyền duyệt khoản thanh toán, phát hành hóa đơn hay thay đổi trạng thái hợp đồng**.

~~~text
XML từ bên ngoài
      │
      ▼
[0] XML parsing an toàn, đúng cấu trúc dự kiến
      │
      ▼
[1] XMLDSig CORE VALIDATION
    - SignatureValue hợp lệ?
    - Mọi Reference digests hợp lệ?
    - Algorithms, URI/transforms, signed scope đúng profile?
      │
      ▼
[2] TRUST & SIGNER IDENTITY
    - Khóa từ đâu?
    - Chứng chỉ/chuỗi PKIX đến trust anchor được phép?
    - Time, usage, revocation, tên chủ thể đúng?
      │
      ▼
[3] AUTHORIZATION
    - Chủ thể này được phép thực hiện operation?
      │
      ▼
[4] BUSINESS VALIDATION
    - Số tiền, currency, recipient, trạng thái, idempotency, hạn?
    - Các trường được sử dụng chính là những trường đã được ký?
      │
      ▼
Chỉ khi tất cả điều kiện bắt buộc PASS → chấp nhận
~~~

Thứ tự triển khai có thể kiểm tra metadata và chính sách key trước khi thực hiện các transforms tốn kém để giảm rủi ro DoS; bản chất **các điều kiện đều phải đúng trước khi tin dùng dữ liệu**.

Bài học này giúp bạn:

- Phân biệt **XMLSignature.validate**, **SignatureValue.validate** và **Reference.validate**, tránh xác nhận thiếu một phần.
- Hiểu chữ ký xác thực **mối liên kết giữa khóa và dữ liệu tham chiếu**, không tự chứng minh khóa thuộc một người hoặc công ty được phép.
- Nhận biết nguy cơ **KeyInfo self-assertion**, X509Data không được kiểm chứng và CA/truststore cấu hình sai.
- Hiểu quy trình **PKIX CertPathValidator**, **TrustAnchor**, hạn chứng chỉ, KeyUsage/ExtendedKeyUsage, revocation và signer identity mapping.
- Phân biệt **valid certificate chain** với **authorized signer** và **valid business payload**.
- Nhận biết **XML Signature Wrapping (XSW)**, duplicate ID, external URI, transforms nguy hiểm và sự khác nhau giữa *what was signed* với *what the application consumes*.
- Cấu hình **secure validation mode** hiện hành và XML parser chống DTD/XXE.
- Chạy ví dụ **Java 17+ độc lập** tạo XMLDSig với **RSA-SHA256**, ký toàn bộ document, kiểm tra một khóa công khai được ghim độc lập và một số business rules.
- Quan sát bốn trường hợp: hợp lệ; khóa người ký không được tin; chữ ký đúng nhưng nghiệp vụ sai; nội dung bị sửa sau khi ký.
- Thiết kế error handling, audit, replay protection, test matrix và acceptance policy cho hệ thống production.

**Phiên bản hiện hành:** Java XML Digital Signature API nằm trong **module `java.xml.crypto`**, DOM/JAXP parser trong `java.xml`, cryptography/PKIX trong `java.base`. Ví dụ được kiểm thử bằng **OpenJDK 24.0.2**, biên dịch với **`javac --release 17`**, dùng API còn được hỗ trợ trong Java SE 17+ và Java SE 26. Không sử dụng kỹ thuật legacy bị loại bỏ.

---

## 1. XMLDSig bảo vệ điều gì?

XMLDSig là tiêu chuẩn W3C để biểu diễn chữ ký trên **một hoặc nhiều tài nguyên được tham chiếu**. Những tài nguyên đó có thể là XML trong cùng document, dữ liệu bên ngoài hoặc các đối tượng khác tùy profile.

Cấu trúc thường gặp:

~~~xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <ds:CanonicalizationMethod Algorithm="..."/>
    <ds:SignatureMethod Algorithm="..."/>
    <ds:Reference URI="">
      <ds:Transforms>...</ds:Transforms>
      <ds:DigestMethod Algorithm="..."/>
      <ds:DigestValue>...</ds:DigestValue>
    </ds:Reference>
  </ds:SignedInfo>
  <ds:SignatureValue>...</ds:SignatureValue>
  <ds:KeyInfo>...</ds:KeyInfo>
</ds:Signature>
~~~

**Đây là sơ đồ XML với dấu `...` minh họa, không phải một signature thực có thể xác minh.** Tên có prefix `ds` là quy ước phổ biến; XML namespace URI và cấu trúc mới là điều cần kiểm tra.

### 1.1. Reference digest validation

Mỗi **Reference** chỉ ra dữ liệu được bảo vệ, thường qua **URI** và **Transforms**. Phần mềm xác minh:

1. Tìm đúng data object mà Reference đề cập.
2. Thực thi đúng transforms đã được profile cho phép.
3. Tính hash bằng DigestMethod được phép, ví dụ SHA-256.
4. So sánh với DigestValue nằm trong SignedInfo.

Nếu nội dung đã ký bị thay đổi sau thời điểm ký, Reference validation thường thất bại. Nhưng **nếu ứng dụng lấy một node khác không nằm trong phạm vi Reference đã ký**, chữ ký vẫn có thể hợp lệ trong khi thông tin ứng dụng dùng là không được bảo vệ.

### 1.2. SignatureValue validation

**SignedInfo** được canonicalize theo CanonicalizationMethod, rồi xác minh SignatureValue bằng khóa công khai tương ứng với khóa bí mật đã ký.

Điều này trả lời: **chữ ký được tạo bằng khóa tương ứng với public key đang kiểm tra, cho SignedInfo cụ thể đó hay không?**

Nó **không** trả lời:

- Khóa này thuộc ai?
- Có được CA tin cậy chứng nhận không?
- Chứng chỉ có bị thu hồi hay hết hạn không?
- Người ký có quyền thực hiện giao dịch này không?
- Số tiền, bên nhận, trạng thái trong document có đúng quy định không?
- Bên nhận XML có thật sự sử dụng đúng nội dung đã ký không?

### 1.3. Hai phần phải cùng đúng

~~~text
core validation =
  SignatureValue validation PASS
  AND
  all required Reference digest validations PASS
~~~

Trong Java, dùng **`XMLSignature.validate(DOMValidateContext)`** để thực hiện **core validation** theo profile.

Một sai lầm:

~~~java
// Mảnh minh họa SAI nếu dùng riêng để quyết định chấp nhận.
boolean signatureOnly =
        signature.getSignatureValue().validate(validationContext);
if (signatureOnly) {
    // KHÔNG được lập tức trả tiền hoặc tin payload.
}
~~~

`SignatureValue.validate(...)` có thể đúng trong khi một Reference đã bị đổi dữ liệu. Với trường hợp đó, **core validity phải false**. Khi cần diagnostics, bạn có thể kiểm tra riêng SignatureValue và từng Reference, nhưng **không bỏ bước xác minh cả hai**.

### 1.4. KeyInfo không phải trust anchor

**KeyInfo** có thể chứa `KeyValue`, `X509Data`, `KeyName`, `RetrievalMethod` hoặc dạng metadata khóa khác. Nội dung này thường nằm trong XML nhận từ bên ngoài.

Nếu một bên tấn công tự tạo cặp khóa RSA, tự ký một tài liệu rồi nhúng **public key của chính họ** vào `KeyInfo`, chữ ký **vẫn có thể xác minh mật mã đúng bằng khóa vừa nhúng**. Đó chỉ chứng minh **self-consistency**, không chứng minh người ký là đối tác được ủy quyền.

**Không auto trust public key/certificate được lấy từ chính XML không đáng tin.** Xác minh với một khóa hoặc trust policy được thiết lập **độc lập với payload**.

---

## 2. Ba lớp kiểm tra và quyền của người ký

| Điều cần xác nhận | Câu hỏi | Công cụ/cơ chế | Nếu FAIL |
| --- | --- | --- | --- |
| **Core XMLDSig** | SignedInfo, SignatureValue, References có đúng? | XMLSignature.validate và profile allowlist | Không được tin nội dung |
| **Trust/key binding** | Khóa/chứng chỉ có thuộc nguồn đáng tin theo policy? | Trusted key pin, PKIX validation, trust anchors | Từ chối dù core đúng |
| **Signer identity/authorization** | Chủ thể này có được phép ký loại document/action này? | Contract registry, identity mapping, ACL/role | Từ chối dù cert hợp lệ |
| **Business semantics** | Payload có đúng schema và quy tắc nghiệp vụ không? | Validated domain model, amount/currency/recipient/idempotency | Từ chối dù crypto và PKIX đúng |

Đây là **bốn điều kiện kiểm tra**, trong đó **trust/certificate** và **authorization** nên tách riêng dù cùng liên quan “người ký”.

### 2.1. Ma trận quyết định

| Core signature | Khóa/chứng chỉ đáng tin | Signer có quyền | Nội dung đúng nghiệp vụ | Chấp nhận? |
| --- | --- | --- | --- | --- |
| FAIL | Bất kỳ | Bất kỳ | Bất kỳ | **Không** |
| PASS | FAIL | Bất kỳ | PASS | **Không** |
| PASS | PASS | FAIL | PASS | **Không** |
| PASS | PASS | PASS | FAIL | **Không** |
| PASS | PASS | PASS | PASS | **Có thể**, sau các kiểm tra trạng thái/replay cần thiết |

“Có thể” thay vì “chắc chắn” vì hệ thống còn có thể phải kiểm tra **request chưa bị dùng lại, giao dịch chưa hoàn tất, deadline, đối soát hoặc xác nhận người dùng** theo contract.

### 2.2. Một chữ ký đúng trên một lệnh sai

Ví dụ một đối tác có khóa được công nhận ký:

~~~xml
<order orderId="O-2026-001">
  <amount>-10</amount>
  <currency>VND</currency>
  <recipient>SHOP-APPROVED</recipient>
  <!-- Signature được tạo hợp lệ ở thời điểm ký -->
</order>
~~~

Ở đây **âm số tiền** có thể vi phạm business rule, nhưng **chữ ký vẫn đúng** vì người ký thực sự đã ký nguyên nội dung đó.

Chữ ký không thể tự biến dữ liệu sai thành dữ liệu đúng.

### 2.3. Một chứng chỉ đáng tin nhưng không đủ quyền

Giả sử chứng chỉ của phòng Kế toán có chuỗi CA hợp lệ, còn một quyết định chi tiền trên 100 triệu chỉ được ký bởi role APPROVER. Nếu chứng chỉ đó thuộc người không có role APPROVER, **PKIX validation thành công vẫn phải bị từ chối**.

Xác minh signer authority theo **danh tính được ánh xạ và policy do ứng dụng quản lý**, có thể kèm scope như tenant, phòng ban, loại giao dịch, giới hạn tiền và thời gian ủy quyền.

### 2.4. Một giao dịch được ký hợp lệ nhưng đã được xử lý

Ngay cả khi chữ ký, trust và business fields đều đúng, kẻ khác có thể **gửi lại cùng một XML cũ**. Mật mã không tự phát hiện “lệnh này đã từng được xử lý”.

Cần **operationId/nonce, idempotency key, issuedAt/expiry** hoặc transaction status theo contract, được ràng buộc vào phần dữ liệu có chữ ký. Lưu kết quả đã xử lý theo key để không tạo double payment/duplicate order. Một `createdAt` xuất hiện trong XML **không tự chứng minh thời gian đã được người thứ ba xác thực**.

---

## 3. Chứng chỉ X.509 đáng tin khác chữ ký XML hợp lệ

### 3.1. Chứng chỉ chứa public key và thông tin chủ thể

Một chứng chỉ X.509 có thể chứa:

- Public key.
- Subject và issuer names.
- Thời hạn có hiệu lực.
- Serial number.
- Signature của issuer.
- Basic Constraints, KeyUsage, ExtendedKeyUsage, certificate policies và các extensions khác.
- Subject Alternative Names hoặc identifiers theo profile.

Chứng chỉ **không phải cam kết rằng mọi thông điệp do chủ thể đó ký đều đúng nghiệp vụ**. Nó là một phần của hạ tầng định danh/PKI.

### 3.2. Chuỗi chứng chỉ và trust anchor

~~~text
End-entity certificate (người ký XML)
                │
                ▼
Intermediate CA certificate
                │
                ▼
Root CA / Trust Anchor
(được hệ thống cấu hình tin cậy từ trước)
~~~

**PKIX CertPathValidator** kiểm tra certification path theo quy tắc PKIX phù hợp. Điểm gốc là **TrustAnchor được cấu hình ngoài dữ liệu XML nhận**, không phải cứ gặp chứng chỉ “Root CA” trong KeyInfo thì tự tin nó.

Nếu tổ chức chỉ chấp nhận chứng chỉ từ một private CA riêng, không nên dùng mọi CA có sẵn trong truststore hệ điều hành/JDK mà không có lý do.

### 3.3. Những bước bổ sung bên cạnh chain validity

Một policy hợp lệ thường phải xác định:

1. **Trust anchors**: CA hoặc khóa công khai nào được hệ thống cho phép.
2. **Thời gian**: chứng chỉ hợp lệ tại thời điểm kiểm tra theo business contract; xác minh historical signing-time cần trusted timestamp/evidence phù hợp.
3. **KeyUsage**: khóa có thể được dùng để xác thực chữ ký số theo profile không?
4. **ExtendedKeyUsage/certificate policies**: đúng mục đích nghiệp vụ/chứng chỉ nếu profile yêu cầu?
5. **Revocation**: CRL/OCSP hoặc cơ chế xác minh thu hồi theo policy, có quy tắc rõ ràng khi network không sẵn sàng.
6. **Algorithm/key strength**: không chấp nhận thuật toán yếu hoặc key size ngoài policy.
7. **Signer identity binding**: ánh xạ certificate subject/SAN/identifier vào đối tác hoặc tài khoản đã được đăng ký.
8. **Authorized operation scope**: chủ thể được làm gì, cho tenant nào, hạn mức nào?
9. **Key rotation/incident handling**: khi certificate hoặc signer key bị thay thế/thu hồi, làm gì với các tài liệu cũ/mới?
10. **Evidence/audit**: giữ lại bằng chứng cần thiết để xử lý tranh chấp và tuân thủ theo retention policy.

**Không nên vô hiệu hóa revocation checking chỉ để PKIX path validation chạy nhanh.** Nếu hệ thống dùng offline validation, cần có chính sách dữ liệu CRL/OCSP cache, thời gian và soft-fail/hard-fail được phê duyệt.

### 3.4. Mảnh code PKIX chỉ minh họa cơ chế

~~~java
// MẢNH MINH HỌA, không phải file độc lập.
// certPath: X.509 CertPath đã được dựng đúng.
// trustAnchors: Set<TrustAnchor> lấy từ cấu hình độc lập, đáng tin.
// validationDate: thời điểm xác minh theo chính sách.
java.security.cert.PKIXParameters parameters =
        new java.security.cert.PKIXParameters(trustAnchors);
parameters.setDate(validationDate);
parameters.setRevocationEnabled(true);

java.security.cert.CertPathValidator validator =
        java.security.cert.CertPathValidator.getInstance("PKIX");
validator.validate(certPath, parameters);
~~~

**Đoạn này KHÔNG phải một trình xác minh chứng chỉ hoàn chỉnh.** Nó chưa chỉ ra cách dựng `CertPath`, cung cấp CRLs/OCSP, xử lý revocation network failures, kiểm tra signer identity/KeyUsage/EKU/business profile hay mapping certificate leaf public key vào XML signature. Các bước đó phải được triển khai và kiểm thử bằng PKI của hệ thống.

Khi dùng chứng chỉ chứa trong `X509Data`, `CertPathValidator` **không được XMLSignature.validate tự động gọi thay cho bạn chỉ vì có X509Data**. Cần chính sách `KeySelector`/validator chủ động kiểm chứng chứng chỉ.

### 3.5. Không nhầm fingerprint/public key pin với PKIX

Một hệ thống B2B có thể dùng **public-key pinning**: người quản trị cấu hình trước public key hợp lệ của đối tác thông qua kênh tin cậy. Nếu XML signature xác minh bằng đúng public key đó, ta có một trust binding theo **pinned key policy**.

Điều này **không phải** PKIX certification path validation. Pinning vẫn cần quản lý rotation, expiry của quyền, quyền người ký, thu hồi key và key compromise. Một key có thể đúng theo pin nhưng người giữ key không có quyền ký một payment cụ thể.

**Ví dụ runnable dưới đây chỉ mô phỏng trust bằng public-key pinning**, không sinh chứng chỉ X.509 và không tuyên bố đã xác minh PKIX.

---

## 4. XML Signature Wrapping: chữ ký hợp lệ trên sai node

Một rủi ro nổi bật trong XMLDSig là **XML Signature Wrapping (XSW)**. Kẻ tấn công có thể giữ nguyên một phần tử đã được ký hợp lệ nhưng chèn thêm một phần tử khác ở vị trí ứng dụng đọc trước.

Sơ đồ:

~~~xml
<Envelope>
  <Order>
    <amount>999999</amount>
    <!-- Phần tử bị ứng dụng lấy nhầm, không nằm trong Reference -->
  </Order>
  <Wrapper>
    <Order Id="signed-1">
      <amount>100</amount>
      <!-- Signature hợp lệ cho signed-1 -->
    </Order>
  </Wrapper>
</Envelope>
~~~

**Đây là ví dụ khái niệm, không phải một XMLDSig hợp lệ có chữ ký đầy đủ.** Nếu verifier kiểm tra Reference tới `signed-1` nhưng business code lại đọc `/Envelope/Order` đầu tiên, verifier có thể báo valid cho dữ liệu **100** trong khi ứng dụng xử lý **999999**. Sai lầm nằm ở **mismatch giữa signed node và consumed node**.

### 4.1. Các nguyên tắc phòng ngừa

- Xác định rõ **document profile**: chấp nhận chữ ký enveloped, enveloping hay detached? Reference URI nào?
- Xác minh **số lượng/vị trí `Signature`**; không chỉ lấy `getElementsByTagNameNS(...).item(0)` rồi bỏ qua mọi signature khác.
- Từ chối **duplicate ID** và registration không an toàn; khi dùng `#id`, xác định ID attribute theo schema và đảm bảo chỉ một target.
- Kiểm tra **Reference URI và transforms** theo allowlist.
- Không mặc định mọi XPath/XSLT/external Reference đều an toàn; không bật các thuật toán/transform không dùng.
- Đảm bảo **đúng node đã được cryptographically authenticated chính là node mà business parser sử dụng**.
- Không dùng một DOM tree cho verification rồi parse lại theo quy tắc khác khiến ứng dụng chọn node không tương ứng.
- Áp schema/profile validation độc lập để loại bỏ extra elements, nested payloads và namespace confusion.
- Không đọc business fields từ một vị trí XML tùy tiện (`getElementsByTagName(...).item(0)`) nếu có thể có duplicates/nesting.
- Không dùng XML `SignatureValue`/`KeyInfo` như bằng chứng rằng mọi dữ liệu trong cùng file đều được ký.

### 4.2. Vì sao bài demo chọn Reference URI rỗng?

Trong chương trình, `Reference URI=""` chỉ **toàn bộ XML document** theo XMLDSig same-document semantics. Signature là enveloped và được loại khỏi digest bằng **Transform.ENVELOPED**. Code cũng:

- Cho phép **đúng một `Signature` là con trực tiếp của root**.
- Cho phép **đúng một Reference**.
- Cho phép **chính xác hai transforms**: enveloped + exclusive canonicalization.
- Chỉ chấp nhận **SHA-256**, **RSA-SHA256**, canonicalization đã dự kiến.
- Đọc dữ liệu nghiệp vụ từ **chính DOM document đã xác minh**, trong các **direct children** của root.
- Kiểm tra số lượng phần tử con theo cấu trúc mong đợi.

Đó là một **profile nhỏ có kiểm soát**, phù hợp ví dụ. **Không phải một thư viện chống XSW tổng quát** cho SOAP/SAML/XAdES hoặc các chữ ký detached/multiple references. Những định dạng đó cần profile ID, namespace, schema, transform và trust semantics riêng.

### 4.3. Cẩn thận với namespace và canonicalization

Hai element nhìn giống nhau ở prefix có thể có **namespace URI khác nhau**; hai prefix khác nhau có thể cùng một expanded name. So sánh **namespace URI + localName** theo schema, không chỉ raw XML prefix.

Canonicalization giải quyết một số khác biệt biểu diễn XML nhưng **không tự xác nhận tài liệu có đúng nghiệp vụ**. Đừng nghĩ đổi whitespace/namespace miễn canonicalization vẫn pass thì app không cần validate schema.

---

## 5. Secure validation trong JDK hiện hành

Theo Oracle Java SE 26, **XML Signature secure validation mode bật mặc định** trong JDK XMLDSig implementation. Có thể đặt tường minh:

~~~java
DOMValidateContext context = new DOMValidateContext(keySelector, signatureNode);
context.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
~~~

Đây là mảnh minh họa; `keySelector` cần được thiết kế và `signatureNode` phải đúng vị trí XMLDSig. JDK còn hỗ trợ system property cùng tên, và **system property có thể ghi đè context property**, vì vậy môi trường triển khai phải được kiểm tra/khóa cấu hình.

### 5.1. Một số hạn chế mà secure validation áp dụng

Theo hướng dẫn JDK hiện hành, mặc định mode này có thể:

- Từ chối **XSLT transforms**.
- Giới hạn **số lượng References** và **transforms** để giảm DoS.
- Từ chối một số **thuật toán yếu** như MD5, SHA-1 trong XMLDSig policy hiện hành.
- Từ chối **external Reference URI schemes** như `http`, `https`, `file`.
- Từ chối duplicate Reference IDs theo policy.
- Ngăn một `RetrievalMethod` tham chiếu tiếp sang một RetrievalMethod khác.
- Đặt ngưỡng tối thiểu cho một số public-key sizes.
- Dùng security property **`jdk.xml.dsig.secureValidationPolicy`** để cấu hình các giới hạn do JDK triển khai.

**Không coi ngưỡng tối thiểu do runtime áp đặt là chính sách mật mã đủ mạnh cho sản phẩm.** Thiết lập business/organization algorithm allowlist và key-lifecycle riêng. Trong Java 26, security policy đối với một số XPath transforms cũng có thay đổi, vì thế phải kiểm thử chính xác JDK/runtime đang triển khai.

### 5.2. Secure validation không thay thế trust hoặc business rules

Ngay cả khi secure validation bật:

- `KeyInfo` tự khai vẫn có thể cung cấp một public key mà chữ ký xác minh đúng.
- `XMLSignature.validate()` không tự lấy trust anchors do ứng dụng thiết kế.
- Chữ ký đúng trên số tiền âm vẫn đúng.
- Reference chỉ một phần của document vẫn không bảo vệ phần ngoài scope.
- Replay của một XML cũ vẫn có thể có core signature hợp lệ.

**Secure validation là cơ chế hardening cho phần kiểm tra chữ ký**, không phải một hệ thống authorization/PKIX/domain validation hoàn chỉnh.

---

## 6. XML parser phải an toàn trước khi kiểm tra chữ ký

XMLDSig DOM provider cần một **DOM document đã được parse**. Nếu XML đến từ nguồn ngoài, việc parse phải an toàn **trước khi gọi XMLSignatureFactory**.

Một `DocumentBuilderFactory` hiện hành:

~~~java
// MẢNH MINH HỌA với imports javax.xml.parsers.DocumentBuilderFactory,
// javax.xml.XMLConstants.
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setNamespaceAware(true);
factory.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl", true);
factory.setFeature(
        "http://xml.org/sax/features/external-general-entities", false);
factory.setFeature(
        "http://xml.org/sax/features/external-parameter-entities", false);
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
~~~

Nếu một security property bắt buộc **không được provider hỗ trợ**, ứng dụng nhạy cảm phải **fail closed**, không im lặng tiếp tục với XML parser có thể mở file/URL từ external entities.

Cần thêm quotas về **input bytes, element depth, total nodes, attributes, text lengths, parse time và concurrency**, vì DOM xây cả cây vào heap; chặn DTD/XXE không tự giải quyết mọi XML bombs.

### 6.1. Parser và XMLDSig không phải cùng một bước

~~~text
Untrusted bytes
    │
    ├── XML parser có XXE / DTD?      → vấn đề có thể xảy ra TRƯỚC chữ ký
    │
    ▼
DOM (structure checked)
    │
    ▼
XMLSignature.validate(context)
    │
    ▼
Trust + signer authorization + business
~~~

Không để `ResourceResolver` hoặc Reference URI từ untrusted XML truy cập arbitrary network/file trước khi trust policy được áp dụng. Trong profile của ví dụ, **chỉ cho Reference URI=""** để tránh external reference dereferencing.

### 6.2. Không dùng raw XML/stacktrace làm public error

Một XML có thể chứa thông tin định danh khách hàng, số tài khoản, số tiền, certificate subject hoặc signed assertions. Với lỗi signature verification, public API nên trả **mã lỗi ổn định** và correlation ID. Diagnostic logs nội bộ có thể ghi bước nào fail (CORE, TRUST, AUTHORIZATION, BUSINESS), algorithm URI, reference URI đã sanitize, cert thumbprint hoặc issuer phù hợp với policy, **không dump toàn bộ XML**.

---

## 7. Ví dụ Java 17+ độc lập: chữ ký hợp lệ ≠ đáng tin ≠ hợp lệ nghiệp vụ

### 7.1. Thiết kế ví dụ

File **`XmlSignatureTrustLayersDemo.java`** sử dụng:

- **`KeyPairGenerator` RSA 2048** để tạo hai cặp khóa trong memory: một khóa được app **ghim** như người ký được phép, một khóa của người ngoài. **2048 bits chỉ là độ dài chọn cho demo**; hệ thống thực theo crypto profile/key rotation hiện hành.
- **`XMLSignatureFactory.getInstance("DOM")`**, SHA-256 digest, RSA-SHA256 signature, Exclusive Canonicalization và enveloped transform.
- **`KeyInfo` chứa `KeyValue`**; chứng minh attacker cũng có thể ký hợp lệ bằng public key tự nhúng.
- **`DOMValidateContext`** với `secureValidation=true` và `KeySelector` chỉ để lấy embedded public key rồi xác minh XMLDSig core.
- **Public-key pinning** so sánh với trusted public key có sẵn ngoài XML.
- **Business rule đơn giản**: orderId đúng expected, amount > 0 và <= 1.000.000, currency VND, recipient SHOP-APPROVED, cấu trúc root/direct children đúng.
- Ký và **serialize + parse lại XML** trước khi verify, để kiểm tra XMLDSig không chỉ đúng trên DOM nội bộ lúc ký.
- Một trường hợp bị sửa `amount` sau khi ký để cho thấy Reference digest fail.

**Giới hạn rất quan trọng:** Ví dụ **không tạo chứng chỉ X.509, không chạy PKIX, CRL hoặc OCSP**, và chưa có một authorization database thực. Cột `trust` có nghĩa là **khóa khớp pinned public key được ứng dụng cấu hình**; nó KHÔNG có nghĩa chứng chỉ đáng tin theo PKIX. Ví dụ chỉ mô phỏng acceptance gates, không dùng trực tiếp làm hệ thống hóa đơn/thanh toán production.

### 7.2. Source: XmlSignatureTrustLayersDemo.java

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.security.KeyException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.crypto.AlgorithmMethod;
import javax.xml.crypto.KeySelector;
import javax.xml.crypto.KeySelectorException;
import javax.xml.crypto.KeySelectorResult;
import javax.xml.crypto.XMLCryptoContext;
import javax.xml.crypto.XMLStructure;
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
import javax.xml.crypto.dsig.keyinfo.KeyInfo;
import javax.xml.crypto.dsig.keyinfo.KeyInfoFactory;
import javax.xml.crypto.dsig.keyinfo.KeyValue;
import javax.xml.crypto.dsig.spec.C14NMethodParameterSpec;
import javax.xml.crypto.dsig.spec.TransformParameterSpec;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

public final class XmlSignatureTrustLayersDemo {
    record Verdict(boolean core, boolean trusted, boolean business,
                   boolean accepted) {
        @Override public String toString() {
            return "core=" + core + " trust=" + trusted
                    + " business=" + business + " accept=" + accepted;
        }
    }

    static final class EmbeddedPublicKey extends KeySelector {
        PublicKey selected;

        @Override
        public KeySelectorResult select(KeyInfo info, Purpose purpose,
                AlgorithmMethod method, XMLCryptoContext context)
                throws KeySelectorException {
            if (info == null) {
                throw new KeySelectorException("Missing KeyInfo");
            }
            for (XMLStructure structure : info.getContent()) {
                if (structure instanceof KeyValue value) {
                    try {
                        PublicKey key = value.getPublicKey();
                        selected = key;
                        return () -> key;
                    } catch (KeyException e) {
                        throw new KeySelectorException(e);
                    }
                }
            }
            throw new KeySelectorException("No KeyValue found");
        }
    }

    static KeyPair newSigner() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    static DocumentBuilderFactory safeDocumentFactory() throws Exception {
        DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
        f.setNamespaceAware(true);
        f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        f.setFeature("http://xml.org/sax/features/external-general-entities", false);
        f.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return f;
    }

    static Document document(String amount, String recipient) throws Exception {
        Document doc = safeDocumentFactory().newDocumentBuilder().newDocument();
        Element root = doc.createElement("order");
        root.setAttribute("orderId", "O-2026-001");
        doc.appendChild(root);
        append(doc, root, "amount", amount);
        append(doc, root, "currency", "VND");
        append(doc, root, "recipient", recipient);
        return doc;
    }

    static void append(Document d, Element parent, String name, String value) {
        Element child = d.createElement(name);
        child.setTextContent(value);
        parent.appendChild(child);
    }

    static Document signAndReparse(String amount, String recipient,
            KeyPair signer) throws Exception {
        Document doc = document(amount, recipient);
        XMLSignatureFactory factory = XMLSignatureFactory.getInstance("DOM");
        Reference ref = factory.newReference(
                "",
                factory.newDigestMethod(DigestMethod.SHA256, null),
                List.of(
                        factory.newTransform(Transform.ENVELOPED,
                                (TransformParameterSpec) null),
                        factory.newTransform(CanonicalizationMethod.EXCLUSIVE,
                                (TransformParameterSpec) null)
                ), null, null);
        SignedInfo info = factory.newSignedInfo(
                factory.newCanonicalizationMethod(
                        CanonicalizationMethod.EXCLUSIVE,
                        (C14NMethodParameterSpec) null),
                factory.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
                List.of(ref));
        KeyInfoFactory keyFactory = factory.getKeyInfoFactory();
        KeyInfo keyInfo = keyFactory.newKeyInfo(
                List.of(keyFactory.newKeyValue(signer.getPublic())));
        DOMSignContext signContext =
                new DOMSignContext(signer.getPrivate(), doc.getDocumentElement());
        signContext.setDefaultNamespacePrefix("ds");
        factory.newXMLSignature(info, keyInfo).sign(signContext);

        TransformerFactory transforms = TransformerFactory.newInstance();
        transforms.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        transforms.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        transforms.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        Transformer transformer = transforms.newTransformer();
        ByteArrayOutputStream xml = new ByteArrayOutputStream();
        transformer.transform(new DOMSource(doc), new StreamResult(xml));
        return safeDocumentFactory().newDocumentBuilder()
                .parse(new ByteArrayInputStream(xml.toByteArray()));
    }

    static Element singleDirectChild(Element root, String name) {
        Element found = null;
        for (Node child = root.getFirstChild(); child != null;
                child = child.getNextSibling()) {
            if (child.getNodeType() != Node.ELEMENT_NODE) continue;
            Element element = (Element) child;
            if (!name.equals(element.getLocalName())
                    || element.getNamespaceURI() != null) continue;
            if (found != null) return null;
            found = element;
        }
        return found;
    }

    static boolean businessValid(Document doc) {
        Element root = doc.getDocumentElement();
        if (!"order".equals(root.getLocalName())
                || root.getNamespaceURI() != null
                || !"O-2026-001".equals(root.getAttribute("orderId"))) {
            return false;
        }
        Element amount = singleDirectChild(root, "amount");
        Element currency = singleDirectChild(root, "currency");
        Element recipient = singleDirectChild(root, "recipient");
        if (amount == null || currency == null || recipient == null) {
            return false;
        }
        int childCount = 0;
        for (Node node = root.getFirstChild(); node != null;
                node = node.getNextSibling()) {
            if (node.getNodeType() == Node.ELEMENT_NODE) childCount++;
        }
        if (childCount != 4) return false;
        if (amount.getChildNodes().getLength() != 1
                || currency.getChildNodes().getLength() != 1
                || recipient.getChildNodes().getLength() != 1) {
            return false;
        }
        if (!"VND".equals(currency.getTextContent())
                || !"SHOP-APPROVED".equals(recipient.getTextContent())) {
            return false;
        }
        try {
            int value = Integer.parseInt(amount.getTextContent());
            return value > 0 && value <= 1_000_000;
        } catch (NumberFormatException e) {
            return false;
        }
    }

    static boolean expectedReferencePolicy(XMLSignature signature) {
        SignedInfo info = signature.getSignedInfo();
        if (!SignatureMethod.RSA_SHA256.equals(
                info.getSignatureMethod().getAlgorithm())
                || !CanonicalizationMethod.EXCLUSIVE.equals(
                info.getCanonicalizationMethod().getAlgorithm())
                || info.getReferences().size() != 1) {
            return false;
        }
        Reference reference = (Reference) info.getReferences().get(0);
        List<?> transforms = reference.getTransforms();
        return "".equals(reference.getURI())
                && DigestMethod.SHA256.equals(
                        reference.getDigestMethod().getAlgorithm())
                && transforms.size() == 2
                && Transform.ENVELOPED.equals(
                        ((Transform) transforms.get(0)).getAlgorithm())
                && CanonicalizationMethod.EXCLUSIVE.equals(
                        ((Transform) transforms.get(1)).getAlgorithm());
    }

    static Verdict evaluate(Document doc, PublicKey allowedSigner)
            throws Exception {
        Element root = doc.getDocumentElement();
        NodeList signatures =
                doc.getElementsByTagNameNS(XMLSignature.XMLNS, "Signature");
        if (signatures.getLength() != 1
                || signatures.item(0).getParentNode() != root) {
            return new Verdict(false, false, false, false);
        }
        EmbeddedPublicKey embedded = new EmbeddedPublicKey();
        DOMValidateContext context =
                new DOMValidateContext(embedded, signatures.item(0));
        context.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
        XMLSignatureFactory factory = XMLSignatureFactory.getInstance("DOM");
        XMLSignature signature = factory.unmarshalXMLSignature(context);
        if (!expectedReferencePolicy(signature)) {
            return new Verdict(false, false, false, false);
        }
        boolean coreValid = signature.validate(context);
        boolean pinned = coreValid && embedded.selected != null
                && MessageDigest.isEqual(embedded.selected.getEncoded(),
                        allowedSigner.getEncoded());
        boolean rules = pinned && businessValid(doc);
        return new Verdict(coreValid, pinned, rules,
                coreValid && pinned && rules);
    }

    public static void main(String[] args) throws Exception {
        KeyPair trustedSigner = newSigner();
        KeyPair outsider = newSigner();

        Document good = signAndReparse("20000", "SHOP-APPROVED", trustedSigner);
        System.out.println("trustedValid=" +
                evaluate(good, trustedSigner.getPublic()));

        Document untrusted = signAndReparse("20000", "SHOP-APPROVED", outsider);
        System.out.println("unknownSigner=" +
                evaluate(untrusted, trustedSigner.getPublic()));

        Document badBusiness = signAndReparse("-10", "SHOP-APPROVED", trustedSigner);
        System.out.println("badBusiness=" +
                evaluate(badBusiness, trustedSigner.getPublic()));

        Document tampered = signAndReparse("20000", "SHOP-APPROVED", trustedSigner);
        singleDirectChild(tampered.getDocumentElement(), "amount")
                .setTextContent("90000");
        System.out.println("tampered=" +
                evaluate(tampered, trustedSigner.getPublic()));

        System.out.println("noCertificateChainValidation=true");
    }
}
~~~

### 7.3. Biên dịch và chạy

Lưu file thành **XmlSignatureTrustLayersDemo.java**, dùng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 --release 17 XmlSignatureTrustLayersDemo.java
java XmlSignatureTrustLayersDemo
~~~

Không cần database, mạng, Maven, Gradle, bên phát hành chứng chỉ hay thư viện ngoài JDK. Demo tạo cặp khóa mới cho mỗi lần chạy và không dùng/cất private key của người thật. **Không sử dụng cơ chế sinh khóa tạm bằng memory như vậy cho chữ ký production**; khóa production thường nằm trong hệ thống quản lý khóa/HSM hoặc một kho khóa có policy được phê duyệt.

### 7.4. Stdout chính xác đã kiểm chứng

~~~text
trustedValid=core=true trust=true business=true accept=true
unknownSigner=core=true trust=false business=false accept=false
badBusiness=core=true trust=true business=false accept=false
tampered=core=false trust=false business=false accept=false
noCertificateChainValidation=true
~~~

**Đã biên dịch và chạy thành công trên OpenJDK 24.0.2 với `--release 17`, kiểm tra đúng toàn bộ 5 dòng stdout**. Những kết quả này là demo Java/JDK trên dữ liệu tự tạo, không phải đầu ra từ một CA hay dịch vụ ký/chứng thực bên ngoài.

### 7.5. Cách diễn giải từng trường hợp

**1. trustedValid**

- `core=true`: XMLDSig SignatureValue và References hợp lệ.
- `trust=true`: public key dùng để verify **khớp public key được ghim độc lập**.
- `business=true`: document có cấu trúc hợp lệ, amount 20000, currency VND, recipient SHOP-APPROVED theo rule giả lập.
- `accept=true`: ba gates trong demo pass.

Điều này **không chứng minh một chứng chỉ X.509 đã được kiểm tra**. Demo chỉ dùng public-key pinning.

**2. unknownSigner**

- Người ngoài tự tạo cặp khóa khác, tự ký nội dung business hoàn toàn hợp lệ.
- `core=true`: chữ ký mật mã và Reference digest đúng với public key do họ tự nhúng vào KeyInfo.
- `trust=false`: public key không bằng key đã được application tin cậy.
- `business=false`: trong code mẫu đây là **gated evaluation**, nghĩa là **businessValid() không được gọi khi trust fail**; không có nghĩa amount/currency trong document này nhất thiết sai.
- `accept=false`: fail trust gate nên không được xử lý.

Đây chính là ví dụ cho thấy **“verify thành công bằng KeyValue trong XML” không đồng nghĩa “chứng chỉ hoặc người ký đáng tin”**.

**3. badBusiness**

- Người ký dùng đúng key đã ghim.
- Số tiền `-10` bị người ký ký nguyên như vậy, nên `core=true` và `trust=true`.
- `business=false`: amount không dương, vi phạm contract.
- `accept=false`: **chữ ký đúng không làm số tiền âm trở nên hợp lệ**.

**4. tampered**

- XML được ký hợp lệ với amount=20000.
- Sau khi ký, application giả lập kẻ tấn công sửa DOM thành amount=90000 mà **không tạo lại signature**.
- Core Reference validation thất bại, nên `core=false`.
- Các cờ `trust=false`, `business=false` trong code là **gated evaluation**: chương trình dừng các bước sau nếu core không đạt.
- `accept=false`: không xử lý nội dung đã bị sửa.

**5. noCertificateChainValidation**

Dòng này là nhãn rõ ràng để người học không suy sai demo đã kiểm tra CA chain. **Không hề có chứng chỉ X.509 hoặc CertPathValidator trong chương trình.** Để đánh giá chứng chỉ thật, phải bổ sung bước PKIX độc lập.

---

## 8. Phân tích code: nơi tạo ranh giới trust

### 8.1. Tại sao cần kiểm tra Reference policy trước validate?

Hàm `expectedReferencePolicy` chỉ chấp nhận:

~~~text
SignatureMethod = RSA-SHA256
DigestMethod    = SHA-256
CanonicalizationMethod = Exclusive C14N
References      = exactly 1
Reference URI   = "" (whole document)
Transforms      = Enveloped + Exclusive C14N
~~~

Nếu một XML được ký bằng **reference URI khác**, có thể nó chỉ bảo vệ một node con không phải nội dung mà business sẽ đọc. Nếu ký bằng thuật toán ngoài profile hoặc reference tới URL bên ngoài, ứng dụng này không có lý do chấp nhận.

**Không dùng policy của demo như whitelist bắt buộc cho mọi profile XMLDSig.** SAML, SOAP, e-invoice và detached signatures có rules khác, cần yêu cầu riêng. Điều quan trọng là **profile explicit, minimal và được test**, không auto accept mọi XMLDSig mà thư viện có thể xử lý.

### 8.2. Vì sao demo vẫn có `EmbeddedPublicKey`?

Vì mục tiêu bài học là **quan sát sự khác nhau giữa core validity và trust**. Đọc KeyValue do signer cung cấp cho phép ta thấy:

~~~text
KeyInfo của outsider
    │
    ├── core signature validate → true
    └── independently pinned public key compare → false
~~~

**Trong ứng dụng production, tốt hơn là xác minh trực tiếp bằng public key được chọn từ trusted registry hoặc từ X.509 certificate đã được validate**, thay vì lấy embedded KeyValue rồi chỉ phân loại trust sau. Nếu buộc dùng embedded key để xác minh, phải kết hợp chính sách allowlist/trust và ràng buộc danh tính chặt chẽ.

### 8.3. Vì sao so sánh khóa với `MessageDigest.isEqual`?

Code so sánh encoded public keys để mô phỏng một registry chỉ có **một key** được tin. Việc dùng `MessageDigest.isEqual` cho byte arrays là một kỹ thuật so sánh xác định; **đừng coi điều đó tạo ra PKIX trust**. Quản lý trust/rotation/revocation và chính sách liên quan vẫn phải tồn tại ngoài XML.

Với nhiều partners, một registry đáng tin có thể ánh xạ **keyId/certificate fingerprint → partner identity/tenant/permissions**, nhưng ID lấy từ XML chỉ là chỉ dẫn để tìm candidate. **Không auto-register unknown public keys**.

### 8.4. Tại sao phải lấy đúng node cùng DOM?

`businessValid` nhìn root và các direct child nodes của **Document đã được dùng trong core validation**. Nó không lấy một `Order` bất kỳ ở vị trí khác theo `getElementsByTagName(...).item(0)`, giảm nguy cơ “verify một node, xử lý node khác”.

Mã còn kiểm tra số direct element children và giá trị cụ thể, nhưng **không phải XML schema validator đa dụng**. Một ứng dụng XMLDSig thật cần namespace/schema profile, unique ID handling, content/transform scope và một cấu trúc domain model được validate kỹ hơn.

### 8.5. Không dùng dữ liệu trước khi xác minh

Trong `evaluate`, `businessValid` chỉ được chạy khi cả core và pinned key đều true. Các flags `business=false` của trường hợp earlier gate fail nên được hiểu là **not evaluated/denied**, không phải bằng chứng về bản thân payload.

Ở API production, có thể dùng kiểu kết quả giàu ngữ nghĩa:

~~~text
VerificationStatus:
  CORE_INVALID
  UNTRUSTED_KEY_OR_CERT
  SIGNER_NOT_AUTHORIZED
  BUSINESS_INVALID
  REPLAY_OR_EXPIRED
  ACCEPTED
~~~

Không đưa full XML message, certificate private fields hoặc raw exception stack trace vào response công khai. Phân loại lý do có thể được ghi chi tiết nội bộ theo audit policy và dùng error code chung với client nếu tránh lộ thông tin xác minh.

---

## 9. Đánh giá certificate trust với PKIX trong production

### 9.1. Quy trình khái quát

~~~text
Signature/KeyInfo X509Data
             │
             ▼
Tách và parse X509Certificate candidate
             │
             ▼
Tìm đúng certificate chain theo issuer identifiers
             │
             ▼
PKIX CertPathValidator + TrustAnchors do app quản lý
             │
             ▼
Thời gian, KeyUsage/EKU, revocation và policies
             │
             ▼
Ràng buộc signer identity ↔ trusted registry / authorized partner
             │
             ▼
Dùng leaf public key đúng với XML SignatureMethod
             │
             ▼
XMLDSig core + Reference scope + business validation
~~~

**Thứ tự kiểm tra các phần có thể thay đổi cho mục tiêu an ninh**, nhưng không bước nào được bỏ qua nếu thuộc security contract.

### 9.2. CertPathValidator và CertPathBuilder

- **`CertPathValidator.getInstance("PKIX")`** xác minh một `CertPath` đã có theo PKIX parameters.
- **`CertPathBuilder.getInstance("PKIX")`** có thể giúp xây đường dẫn chứng chỉ dựa trên constraints và certificate stores được cấp quyền.
- **`PKIXParameters`** mang trust anchors, thời gian và policy kiểm tra.
- **`PKIXRevocationChecker`** là cơ chế bổ sung kiểm soát revocation behavior theo implementation.
- **`X509Certificate.checkValidity(date)`** kiểm tra ngày nhưng **không thay thế full PKIX validation**.
- **`KeyStore`** là một nguồn có thể chứa trusted certificate entries; chỉ chứa một cert trong store không có nghĩa cert đó được ủy quyền cho mọi action.

Tùy hạ tầng, chain được gửi trong `X509Data` có thể không đầy đủ, hoặc chứa những certificate không đáng tin. Không tự coi certificate đầu tiên/ cuối cùng trong XML là trust anchor.

### 9.3. Revocation và thời điểm xác minh

Một certificate hôm nay đã hết hạn/thu hồi nhưng một document được ký từ nhiều năm trước có thể cần **long-term validation**. Xác minh historical validity không chỉ dựa vào XML field `signingTime`, vì người ký có thể tự khai thời gian.

Cần có **trusted timestamp**, revocation evidence và chính sách lưu trữ bằng chứng phù hợp chuẩn nghiệp vụ/pháp lý nếu muốn xác nhận chữ ký đã hợp lệ tại một thời điểm quá khứ.

Không tự “quay thời gian xác minh” về `SigningTime` lấy từ XML mà không có bằng chứng thời gian tin cậy.

### 9.4. Chứng chỉ tin cậy nhưng signer chưa được cấp quyền

Một CA public được tin cậy có thể cấp hàng triệu certificates. “Chain to trusted CA” không tự có nghĩa certificate đó thuộc **partner A** hoặc có quyền duyệt **invoice của tenant B**.

Sau khi xác minh chain, hệ thống cần kiểm tra **identity/authorization binding**, ví dụ:

~~~text
certificate identity → registered partner ID
registered partner   → allowed tenants
partner role         → allowed document types
role/contract        → amount threshold and time window
current policy       → not disabled/suspended
~~~

Các quy tắc này thuộc ứng dụng và có thể thay đổi theo hợp đồng; XMLDSig library không biết.

---

## 10. Replay, business state và quyền sử dụng dữ liệu đã ký

### 10.1. Trường được ký phải bao trùm decision

Nếu business xử lý **amount, currency, recipient, orderId, expiry**, các trường quyết định đó phải nằm trong phần được Reference bảo vệ hoặc được xác minh qua một mechanism tin cậy khác.

Một request có chữ ký bảo vệ amount nhưng không bảo vệ recipient có thể cho kẻ tấn công đổi người nhận, dù core signature vẫn pass cho phần đã ký. Điều này thường là lỗi **signature scope policy**, không phải bug trong thuật toán RSA.

### 10.2. Không coi signature pass là authorization của user hiện tại

Một document có chữ ký hợp lệ do đối tác phát hành có thể được chuyển tiếp qua một client khác. Client gửi tài liệu **không tự trở thành người ký**, và chữ ký cũng không thay thế session authentication của sender hiện tại. Nếu yêu cầu nghiệp vụ cần quyền của cả sender/requester, kiểm tra thêm authn/authz của API.

### 10.3. Idempotency/replay prevention

Ví dụ quy trình xử lý:

~~~text
1. Parse XML an toàn, giới hạn size/depth.
2. Kiểm tra XMLDSig scope + cryptographic validity.
3. Xác nhận signer identity/trust/authorization.
4. Kiểm tra domain fields và document profile.
5. Kiểm tra operationId/nonce/expiry và trạng thái hiện có.
6. Trong transaction phù hợp, ghi nhận operationId duy nhất.
7. Thực hiện business operation một lần.
8. Commit và trả kết quả xác định; retry sử dụng idempotency contract.
~~~

Một chữ ký có thể hợp lệ mãi về mặt mật mã nếu dữ liệu không bị sửa; điều đó không cho phép **thực hiện vô hạn một lệnh thanh toán**.

### 10.4. Không tự tạo “non-repudiation” tuyệt đối từ XMLDSig

Chữ ký số là bằng chứng mật mã quan trọng, nhưng việc suy diễn thành **ý chí pháp lý, quyền đại diện hoặc phủ nhận/không thể phủ nhận giao dịch** còn phụ thuộc chứng chỉ, quản lý private key, chứng cứ thời gian, quy trình ký, hợp đồng và pháp luật áp dụng.

Không viết log “chữ ký hợp lệ → người A chắc chắn đồng ý mọi điều kiện” nếu bạn chỉ kiểm tra core signature.

---

## 11. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Core validate true → accept | Không chứng minh trust/business | Separate gates |
| Chỉ gọi SignatureValue.validate | Có thể bỏ qua Reference digest failures | Dùng XMLSignature.validate |
| Tin `KeyInfo/KeyValue` do XML nhúng | Người gửi tự tạo key bất kỳ | Trusted pin/PKIX độc lập |
| X509Data chứa cert → cert trusted | Chưa xác minh chain/trust anchor | CertPathValidator/PKIX policy |
| CertPath hợp lệ → signer được duyệt tiền | CA trust không cấp business role | Identity mapping + authorization |
| CertPath hợp lệ → payload đúng | PKIX không biết business rules | Domain validation |
| Amount âm vẫn core true | Người ký có thể ký dữ liệu sai | Kiểm tra amount/currency/recipient |
| Coi XML cũ được ký là request mới | Replay/double processing | Idempotency/nonce/state |
| Dùng truststore tùy tiện | CA không thuộc partner policy vẫn được tin | Trust anchors theo đối tác |
| Tắt revocation checking để chạy nhanh | Có thể chấp nhận cert bị thu hồi | Revocation policy rõ và test |
| Dùng signingTime tự khai để chấp nhận cert cũ | Thời gian có thể không đáng tin | Trusted timestamp/evidence |
| Lấy `Signature` đầu tiên trong document | Có thể chọn signature sai | Đúng số lượng/vị trí |
| Verify signed node A, business đọc node B | XML signature wrapping | “See what is signed” |
| Chấp nhận duplicate ID | Resolver có thể chọn sai element | Unique ID enforcement |
| Reference tới file/http URL | Có thể SSRF/file access, scope sai | Strict URI allowlist |
| Cho XSLT transforms tùy ý | Tăng rủi ro DoS/complexity | Secure validation, allowlist |
| Dùng SHA-1/MD5 | Thuật toán yếu, có thể bị JDK cấm | Hiện đại SHA-256+ theo policy |
| Tắt secure validation | Mất hardening | Bật/kiểm chứng runtime policy |
| Cho DTD/XXE trong XML input | File/network leak trước verify | JAXP parser hardening |
| Parse XML nhiều lần khác schema | Dùng node khác node ký | Giữ cùng verified DOM/model |
| Log raw signed XML và private data | Lộ PII/identifiers | Redacted diagnostics |
| Không test tampering | Không biết Reference scope đủ chưa | Mutate từng business field |
| Test chỉ với self-generated valid sample | Không phát hiện wrapping/rogue signer | Negative/adversarial tests |

### 11.1. Tại sao một key/cert “đúng” nhưng verify fail?

Có thể do:

- Chữ ký hoặc tài liệu đã bị sửa.
- Reference URI/digest khác nội dung.
- Canonicalization hoặc namespace thay đổi không được profile cho phép.
- Thuật toán yếu/bị JDK secure validation từ chối.
- Dùng sai public key so với private key ký.
- Reference resolver thiếu ID registration.
- Input bị parser transform/normalize ngoài phạm vi đã ký.
- Chữ ký ở vị trí ngoài document profile hoặc có multiple signatures.
- Format XMLDSig không khớp yêu cầu protocol.

Thường kiểm tra **XMLSignature.validate** rồi, chỉ để diagnostics, tách **SignatureValue.validate** và **Reference.validate** trên cùng context. Không in raw XML chứa dữ liệu nhạy cảm ra public logs.

### 11.2. Tại sao một chữ ký hợp lệ nhưng hệ thống vẫn từ chối?

Vì hợp lệ ở một tầng nhưng fail tầng khác:

~~~text
CORE_VALID / UNTRUSTED_SIGNER
CORE_VALID / CERT_EXPIRED
CORE_VALID / CERT_REVOKED
CORE_VALID / SIGNER_UNAUTHORIZED
CORE_VALID / BUSINESS_INVALID
CORE_VALID / DUPLICATE_OPERATION
CORE_VALID / EXPIRED_REQUEST
~~~

Đó là **những kết quả có thể chính xác và cần thiết**, không có gì mâu thuẫn.

---

## 12. Kiểm thử theo các lớp bảo vệ

| Test case | Core | Trust | Business | Accept |
| --- | --- | --- | --- | --- |
| Trusted key, hợp lệ | PASS | PASS | PASS | Có thể PASS |
| Unknown key tự ký XML | PASS | FAIL | Không cần chạy | FAIL |
| Trusted key, amount âm | PASS | PASS | FAIL | FAIL |
| Trusted key, sửa amount sau ký | FAIL | Không cần chạy | Không cần chạy | FAIL |
| Tự sửa `SignatureValue` | FAIL | Không cần chạy | Không cần chạy | FAIL |
| Sửa phần được Reference bảo vệ | FAIL | Không cần chạy | Không cần chạy | FAIL |
| Chữ ký chỉ bảo vệ node phụ | Có thể PASS | PASS | Scope FAIL | FAIL |
| Duplicate XML ID / wrapping | Từ chối theo profile | — | — | FAIL |
| Multiple `Signature` sai profile | Từ chối | — | — | FAIL |
| XML có external Reference URI | Từ chối theo policy | — | — | FAIL |
| DTD/XXE input | Bị chặn trước verify | — | — | FAIL |
| Self-signed X.509 không được pin/trust | Có thể PASS | FAIL | — | FAIL |
| Chain đến CA không được phép | Có thể PASS | FAIL | — | FAIL |
| Expired certificate | Có thể PASS | FAIL theo policy | — | FAIL |
| Revoked certificate | Có thể PASS | FAIL theo policy | — | FAIL |
| Trusted cert nhưng sai identity | PASS | Signer binding FAIL | — | FAIL |
| Trusted cert nhưng thiếu role | PASS | Authorization FAIL | — | FAIL |
| Trusted cert, wrong recipient | PASS | PASS | FAIL | FAIL |
| Trusted cert, duplicate operationId | PASS | PASS | Replay FAIL | FAIL |
| Trusted cert, đã hết hạn yêu cầu | PASS | PASS | FAIL | FAIL |
| Chứng chỉ cũ có timestamp đáng tin | Theo signature policy | PKIX theo evidence | Theo contract | Có thể PASS |

**Bảng là test expectation theo policy mẫu**, không phải mọi trường hợp đều tạo được bằng code demo. Những case PKIX/revocation/wrapping cần integration tests với certificate chain, truststore và schema thực tế.

### 12.1. Unit test và integration test khác nhau

**Unit tests:** dùng cặp key tạm, signed DOM, mutate field, compare pin, kiểm tra business predicate; đây là các test demo đã thực hiện.

**Integration tests:** dùng certificate thật của test CA, certificates expired/revoked, CRL/OCSP trong môi trường test, KeyUsage/EKU, partner registry, signed SOAP/SAML/e-invoice envelope, duplicate ID, detached refs, data stream limits và replay state.

**Security/adversarial tests:** dữ liệu có XML Signature Wrapping, extra unsigned Order, nhiều Signature/Reference, attributes trùng lặp/namespace lẫn, external URI schemes, DTD và entity expansion. Chạy trong sandbox, không cho phép truy cập file/network production.

### 12.2. Một test quan trọng: sửa mọi trường nghiệp vụ

Với một document đã ký hợp lệ, lần lượt mutate từng trường:

- amount
- currency
- recipient
- operationId
- tenantId
- issuedAt/expiresAt

Nếu một trường quyết định business acceptance có thể đổi mà core signature vẫn PASS, có thể **trường đó không nằm trong scope được bảo vệ**, hoặc có lỗi resolver/DOM mapping. Không triển khai cho production cho đến khi xác nhận được coverage theo profile.

---

## 13. Bài tập tự luyện

1. Chạy `XmlSignatureTrustLayersDemo`, giải thích vì sao `unknownSigner` có `core=true` nhưng `trust=false`.
2. Đổi amount của `badBusiness` từ `-10` thành `500`, kiểm tra điều kiện business.
3. Đổi recipient từ SHOP-APPROVED thành SHOP-UNKNOWN khi ký bằng trusted key; giải thích core/trust/business.
4. Mutate currency sau khi ký; dự đoán kết quả Reference validation.
5. Chỉnh XML `SignatureValue` sau ký; giải thích khác biệt với mutate Reference data.
6. Thêm `Order` thứ hai ngoài Reference scope trong một profile khác, vẽ kịch bản XML Signature Wrapping.
7. Xây utility lấy **một direct child** với namespace URI/local name và từ chối duplicates.
8. So sánh `XMLSignature.validate` với `getSignatureValue().validate` và từng `Reference.validate` trên một XML bị sửa.
9. Thử tạo chữ ký bằng outsider key nhưng dùng public KeyValue chính họ trong KeyInfo; giải thích vì sao core vẫn pass.
10. Thử thay KeyInfo bằng key không khớp SignatureValue; giải thích crypto fail.
11. Tạo test certificate chain với một test Root CA được ghim trong truststore; không dùng certificate của production.
12. Tạo các certificates expired/revoked trong test PKI; xác nhận theo revocation policy.
13. Thêm signer authorization theo tenant/role/amount threshold, tách với certificate trust.
14. Tạo operationId cho mỗi XML; lưu unique idempotency record và reject replay.
15. Thêm issuer/subject identity mapping dựa trên thuộc tính chứng chỉ thực, không dùng raw XML `<signerName>` tự khai.
16. Thêm giới hạn số lượng Reference/Transform và URL scheme allowlist theo profile.
17. Thử đổi `Reference URI=""` thành `URI="#data"` trong một profile có ID hợp lệ; cập nhật code để kiểm tra scope đúng.
18. Thử XML có multiple `Signature` và từ chối thay vì lấy chữ ký đầu tiên.
19. Tạo XML namespace prefix khác nhưng cùng URI, kiểm tra parser/profile.
20. Thử XML có DOCTYPE và external entity chỉ vào URL/file giả; kiểm tra parser từ chối trước khi verify.
21. Soạn error response chỉ có public code/correlation ID, không dump XML/certificate details.
22. Viết ma trận test đủ 4 lớp: core, trust, authorization, business + replay.
23. Thiết kế policy kiểm chứng timestamp trước khi chấp nhận chứng chỉ đã hết hạn ở hiện tại.
24. So sánh trusted public key pinning với PKIX trust anchors và nêu trách nhiệm key rotation của mỗi cách.

## 14. Checklist trước production

- [ ] Có một profile XMLDSig rõ ràng: enveloped/enveloping/detached, References và transforms.
- [ ] Cấu hình JAXP parser chống DTD/XXE, namespace-aware, giới hạn input.
- [ ] Không cho external Reference URI ngoài allowlist.
- [ ] Secure validation mode của JDK được bật/kiểm tra.
- [ ] Thuật toán chữ ký/digest/canonicalization phù hợp allowlist hiện hành.
- [ ] Dùng XMLSignature.validate cho core validation, không chỉ SignatureValue.
- [ ] Mọi Reference quan trọng được xác minh; Manifest/extra objects có policy riêng.
- [ ] Đúng số lượng/vị trí Signature và Reference theo document profile.
- [ ] Không có duplicate ID, XML wrapping hay unsigned business-critical field.
- [ ] Business parser dùng **đúng node đã được ký/xác minh**, không node tương tự.
- [ ] Không auto trust KeyInfo/KeyValue/X509Data do bên ngoài gửi.
- [ ] Public key được chọn từ nguồn trusted độc lập, hoặc certificate chain được PKIX validate.
- [ ] TrustAnchor/truststore được kiểm soát và cập nhật theo organization policy.
- [ ] Certificate validity period, KeyUsage/EKU, algorithms và revocation được kiểm tra phù hợp.
- [ ] Không tin `SigningTime` tự khai để thay trusted timestamp/evidence.
- [ ] Signer identity được ánh xạ tới partner/tenant/account đã đăng ký.
- [ ] Signer authorization được kiểm tra theo document type, role và monetary scope.
- [ ] Business rules được áp sau crypto/trust checks và trên dữ liệu signed.
- [ ] Có operationId/idempotency/expiry/replay policy khi XML ra lệnh thay đổi trạng thái.
- [ ] Audit trail có status từng gate nhưng không dump secrets/raw XML ở public channels.
- [ ] Error handling fail closed với unknown algorithms/certs/reference scope.
- [ ] Có tests cho tampering, unknown keys, invalid business, expired/revoked cert và unauthorized signer.
- [ ] Có adversarial tests cho wrapping, duplicate IDs, external references và XXE.
- [ ] Có quy trình quản lý khóa, certificate rotation/revocation, truststore updates và incident response.
- [ ] Không dựa vào demo public-key pinning như chứng cứ đã làm PKIX certificate validation.
- [ ] Chỉ dùng API/thuật toán và JDK security policies còn được hỗ trợ ở runtime hiện hành.

## Kết luận

**Chữ ký XML hợp lệ, chứng chỉ đáng tin và dữ liệu đúng nghiệp vụ là những thuộc tính khác nhau.** `XMLSignature.validate(...)` chỉ xác nhận **core cryptographic validity** của SignatureValue và các Reference; nó không tự tin `KeyInfo` là một danh tính đáng tin, không tự kiểm chứng PKIX certificate path/thu hồi theo business policy, không tự biết signer có quyền hay không, và không tự biết số tiền hoặc người nhận có hợp lệ.

Vì vậy, acceptance của một XML có tác động nghiệp vụ cần **đủ các gates**: parse an toàn → validate signature và signed scope → xác minh key/certificate trust từ nguồn độc lập → ánh xạ danh tính và authorization → kiểm tra business/replay/idempotency. **Một chữ ký hợp lệ trên dữ liệu sai vẫn phải bị từ chối**; một chữ ký hợp lệ của người lạ cũng phải bị từ chối; một nội dung bị chỉnh sửa phải thất bại ở cryptographic core validation.

Ví dụ Java 17+ trên đã chứng minh bốn trường hợp bằng một signature profile nhỏ có kiểm soát, đồng thời minh bạch **chỉ dùng public-key pinning, không giả mạo PKIX validation**. Khi triển khai thật, luôn tuân thủ chuẩn ngành/profile XML, PKI và chính sách bảo mật của hệ thống.

**Tài liệu chính thức, còn áp dụng:**

- [W3C XML Signature Syntax and Processing Version 1.1](https://www.w3.org/TR/xmldsig-core/)
- [Oracle Java SE 26 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/26/security/java-xml-digital-signature-api-overview-and-tutorial.html)
- [XMLSignature — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignature.html)
- [DOMValidateContext — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMValidateContext.html)
- [XMLSignatureFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html)
- [KeyInfo và KeyValue — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/keyinfo/package-summary.html)
- [Oracle Java SE 26 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/26/security/java-pki-programmers-guide.html)
- [CertPathValidator — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertPathValidator.html)
- [PKIXParameters — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXParameters.html)
- [PKIXRevocationChecker — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html)
- [DocumentBuilderFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html)
- [JAXP Security Guide — Java SE 17](https://docs.oracle.com/en/java/javase/17/security/java-api-xml-processing-jaxp-security-guide.html)
- [Microsoft — XML Digital Signature Security Considerations](https://learn.microsoft.com/en-us/windows/win32/seccrypto/xml-digital-signature-security-considerations)