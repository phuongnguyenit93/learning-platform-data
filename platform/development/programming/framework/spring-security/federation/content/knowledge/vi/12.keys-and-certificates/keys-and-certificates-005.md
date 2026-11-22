# Lựa chọn thuật toán chữ ký, hàm băm và chính sách từ chối thuật toán yếu trong SAML 2.0

> **Bối cảnh:** Spring Security – federation → **Khóa và chứng thư**. Bài học dành cho ứng dụng Java/Spring Security đóng vai trò SAML Service Provider (SP) và đội quản trị Identity Provider (IdP). Nội dung phân biệt **thuật toán chữ ký số**, **hàm băm (digest)**, **thuật toán ký chứng thư X.509**, lựa chọn khóa, policy cho phép/từ chối, cách vận dụng vào SAML HTTP-Redirect/XML Signature, cùng các điểm cần xác minh khi Spring Security/OpenSAML tích hợp với nhiều IdP. Ví dụ độc lập sử dụng Java 17+; đoạn Spring yêu cầu dependency/configuration thật.

## 1. Tại sao chỉ “chữ ký hợp lệ” là chưa đủ?

Trong SAML 2.0, browser có thể gửi `SAMLResponse` chứa assertion cho SP. Một chữ ký số có thể xác minh thành công theo phép toán **nhưng vẫn không được chấp nhận** vì:

- Thông điệp chỉ định `rsa-sha1`, `hmac-sha1` hoặc digest `sha1`, trái chính sách không dùng thuật toán yếu.
- Chữ ký dùng khóa của một IdP không được đăng ký, hoặc tin nhầm certificate do chính `KeyInfo` của XML chưa tin cậy cung cấp.
- Một Assertion không nằm trong phần được chữ ký bảo vệ vẫn được code đọc để tạo principal (XML Signature Wrapping).
- Khóa RSA quá ngắn hoặc certificate/key không hợp lệ theo chính sách.
- Chữ ký bảo vệ đúng một phần XML nhưng `Audience`, `Recipient`, `Destination`, `InResponseTo` hoặc điều kiện thời gian sai.
- SP nhầm **thuật toán ký trên chứng thư X.509** với **SignatureMethod của XML SAML** rồi vô tình cho phép phương pháp XML yếu.

Do đó **kết quả authentication chỉ thành công khi đồng thời** có thuật toán được cho phép, khóa tin cậy và đủ mạnh, chữ ký đúng với dữ liệu thật được sử dụng, cùng đầy đủ các kiểm tra giao thức SAML. Việc XML parse được hoặc một thư viện trả `signature.verify=true` đơn lẻ chưa đủ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc đúng `ds:SignatureMethod`, `ds:DigestMethod`, `ds:CanonicalizationMethod`, `ds:Reference` và `ds:SignatureValue`.
2. Phân biệt **JCA name** như `SHA256withRSA` với **XMLDSig URI** như `http://www.w3.org/2001/04/xmldsig-more#rsa-sha256`.
3. Chọn một **allowlist** thuật toán có lý do, thường lấy RSA-SHA256 và SHA-256 làm baseline tương thích; đánh giá RSA-SHA384/512, ECDSA hoặc RSA-PSS khi hai bên hỗ trợ.
4. Từ chối SHA-1/MD5 và các lựa chọn không được chấp thuận mà không tự động downgrade, kể cả khi phép verify kỹ thuật có thể thành công.
5. Áp dụng khác nhau cho **SP ký AuthnRequest** và **SP xác minh IdP ký Response/Assertion**.
6. Hiểu giới hạn của cấu hình Spring Security: tùy chọn **signingAlgorithms** cho **AuthnRequest gửi đi** không tự trở thành whitelist **chữ ký SAMLResponse nhận về**.
7. Đặt acceptance policy theo IdP/tenant, thực hiện key rotation, kiểm thử âm tính và ghi log an toàn.

## 2. Ba lớp thuật toán phải phân biệt

| Lớp | Vị trí/thông tin | Nó bảo vệ gì? | Ví dụ |
| --- | --- | --- | --- |
| **XML SignatureMethod / HTTP-Redirect SigAlg** | `<ds:SignatureMethod Algorithm="...">` hoặc query `SigAlg` | Tạo/xác minh chữ ký trên dữ liệu đã chuẩn bị theo binding | RSA-SHA256 |
| **XML DigestMethod** | `<ds:DigestMethod Algorithm="...">` trong `ds:Reference` | Băm nội dung tham chiếu sau các transforms trước khi đưa vào cấu trúc chữ ký | SHA-256 |
| **X.509 certificate signature algorithm** | Trường signatureAlgorithm trong chứng thư | Thuật toán CA hoặc self-signer dùng ký **chứng thư**, không phải XML message | sha256WithRSAEncryption |
| **TLS cipher suite/certificate** | HTTPS giữa browser – IdP/SP | Bảo vệ kết nối vận chuyển, không thay SAML message signature | TLS 1.3 |
| **XML Encryption** | `EncryptedAssertion` / `EncryptedAttribute` | Bảo mật nội dung; khác việc xác thực tính toàn vẹn và issuer | AES-GCM theo profile/khả năng hỗ trợ |

Ví dụ một IdP có certificate tự ký bằng `sha256WithRSAEncryption` nhưng một SAML Assertion vẫn dùng `rsa-sha1` trong `ds:SignatureMethod`. Chứng thư được ký bằng SHA-256 **không làm chữ ký SAML thành SHA-256**. SP phải xem **cả certificate và XML Signature** theo đúng chính sách.

Ngược lại, một XML Signature `rsa-sha256` không bảo đảm khóa RSA đủ dài: khóa RSA 1024 bit không tương đương 2048/3072 bit về sức mạnh. Vì vậy policy phải áp dụng **thuật toán + digest + key strength + trust + signature coverage**.

## 3. Vai trò chữ ký theo chiều SP/IdP

```text
SP                         Browser                         IdP
 |-- AuthnRequest ------------>|------------------------------>|
 |   SP private signing key   |                               |
 |   IdP verify bằng SP public certificate                    |
 |                             |                               |
 |<----------------------------|<---- SAMLResponse/Assertion --|
 |                                  IdP private signing key   |
 |   SP verify bằng IdP public signing certificate tin cậy    |
```

**AuthnRequest:** do SP phát. Khi IdP yêu cầu `WantAuthnRequestsSigned=true` hoặc SP có policy ký, SP phải dùng private signing key của **chính SP**. Kênh HTTP-Redirect dùng `SigAlg` và `Signature` ở query; HTTP-POST thường dùng XML Signature trong AuthnRequest.

**SAMLResponse/Assertion:** do IdP phát. SP phải verify bằng public certificate/key **đã đăng ký cho IdP ấy** trước khi nhận danh tính. Tùy SAML profile và chính sách, chữ ký có thể ở `Response` hoặc `Assertion`; quan trọng là **assertion thực sự được dùng để đăng nhập phải nằm trong vùng đã ký và được xác minh**. Nếu hệ thống yêu cầu mỗi Assertion được ký riêng, không chấp nhận chỉ Response đã ký để thỏa yêu cầu riêng đó.

**Không hoán đổi:** `signing.credentials` của SP không dùng làm verification credentials cho IdP; IdP verification certificate không có private key để SP ký request.

## 4. Giải phẫu XML Digital Signature trong Assertion

Ví dụ dưới đây là **mảnh XML minh họa thuật toán**, không phải assertion hợp lệ hoặc chữ ký có thể xác minh. Các chuỗi `BASE64_SAMPLE_NOT_VALID` chỉ là dữ liệu giả:

```xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <ds:CanonicalizationMethod
      Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
    <ds:SignatureMethod
      Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
    <ds:Reference URI="#_assertion_001">
      <ds:Transforms>
        <ds:Transform
          Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
        <ds:Transform
          Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
      </ds:Transforms>
      <ds:DigestMethod
        Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
      <ds:DigestValue>BASE64_SAMPLE_NOT_VALID</ds:DigestValue>
    </ds:Reference>
  </ds:SignedInfo>
  <ds:SignatureValue>BASE64_SAMPLE_NOT_VALID</ds:SignatureValue>
</ds:Signature>
```

Đọc thứ tự:

1. `Reference URI="#_assertion_001"` chỉ element SAML có ID tương ứng. Đây là **đối tượng có nội dung được digest**, không phải tên tệp hoặc URL tùy ý để truy cập mạng.
2. `Transforms` định nghĩa phép biến đổi áp dụng lên nội dung được tham chiếu trước khi băm. `enveloped-signature` loại bỏ signature nhúng ra khỏi đối tượng băm trong kiểu cấu trúc tương ứng; exclusive canonicalization chuẩn hóa biểu diễn XML.
3. `DigestMethod` chỉ hàm băm, ví dụ SHA-256. `DigestValue` là giá trị digest của dữ liệu sau transforms.
4. `SignedInfo` gồm các digest references và metadata thuật toán. `CanonicalizationMethod` quy định canonicalization của `SignedInfo` trước khi ký.
5. `SignatureMethod` chỉ cách ký/verify `SignedInfo`, ví dụ RSA với SHA-256. `SignatureValue` chứa chữ ký đã encode.
6. `KeyInfo` (nếu có) có thể gợi ý khóa nhưng **không phải nguồn tin cậy tự thân**. SP phải đối chiếu signing key với certificate/IdP registration được chấp thuận.
7. SP phải xác nhận **signed element chính là Response/Assertion dùng để tạo Authentication**, tránh đọc một Assertion khác trong cùng XML chưa được ký.

**Hai kiểm tra khác nhau:** digest của reference phải khớp nội dung sau transforms, và signature trên `SignedInfo` phải hợp lệ với trusted key. Nếu chỉ kiểm tra một bước, hoặc xác minh một element nhưng đọc claims từ element khác, ứng dụng vẫn dễ bị giả mạo.

### 4.1. Canonicalization không phải thuật toán băm

XML có nhiều biểu diễn text nhưng vẫn có ý nghĩa cấu trúc tương đương: namespace prefixes, thứ tự attributes, cách xuống dòng hoặc encoding. Canonicalization (`C14N`) xác định bytes chuẩn để ký/verify; `SHA-256` sau đó băm bytes. `C14N` **không** thay SHA-256 và không tự tạo chữ ký.

Các lựa chọn `CanonicalizationMethod`/`Transform` cũng phải được giới hạn theo SAML/XMLSig profile và threat model. Một XML Signature chứa nhiều transforms, XSLT hoặc external references có thể gây parsing abuse/SSRF/đổi dữ liệu được kiểm tra. Với thư viện XML Security, bật secure validation và hạn chế reference URI, transform chain, số references. Không tự viết DOM/XPath parser bỏ qua schema/ID uniqueness.

### 4.2. Reference URI, ID uniqueness và XML Signature Wrapping

Giả sử phần chữ ký hợp lệ chỉ phủ `Assertion ID="_signed_a"`, còn XML có thêm `Assertion ID="_unsigned_b"` chứa quyền admin. Nếu code chọn “assertion đầu tiên” hoặc `getElementsByTagName("Assertion")` tùy tiện, một kết quả verify đúng không giúp dữ liệu chưa ký trở thành đáng tin.

Yêu cầu: document được parse an toàn, ID uniqueness/namespace đúng, reference URI trỏ tới **đúng** object, signature coverage của object dùng authentication được xác nhận; reject signed/unsigned ambiguity. OWASP khuyến nghị harden XML validation và không lựa chọn security element qua XPath lỏng.

## 5. Bảng URI thuật toán SAML/XMLDSig

| Thuật toán / cơ chế | URI ví dụ | Vai trò | Policy điển hình |
| --- | --- | --- | --- |
| RSA-SHA256 | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha256` | XML SignatureMethod / Redirect SigAlg | **Allow** khi key đủ mạnh, IdP/SP hỗ trợ |
| RSA-SHA384 | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha384` | SignatureMethod / SigAlg | Allow khi thực sự hỗ trợ và được duyệt |
| RSA-SHA512 | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha512` | SignatureMethod / SigAlg | Allow khi tương thích |
| ECDSA-SHA256 | `http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256` | XML SignatureMethod | Allow khi cert EC/IdP/SP/ thư viện cùng hỗ trợ |
| SHA-256 | `http://www.w3.org/2001/04/xmlenc#sha256` | XML DigestMethod | **Allow** |
| SHA-384 | `http://www.w3.org/2001/04/xmldsig-more#sha384` | XML DigestMethod | Allow nếu thư viện và hợp đồng hỗ trợ |
| SHA-512 | `http://www.w3.org/2001/04/xmlenc#sha512` | XML DigestMethod | Allow nếu hỗ trợ |
| RSA-SHA1 | `http://www.w3.org/2000/09/xmldsig#rsa-sha1` | Chữ ký kiểu cũ | **Reject** theo policy hiện đại |
| HMAC-SHA1 | `http://www.w3.org/2000/09/xmldsig#hmac-sha1` | MAC dạng cũ; không thay được trust IdP X.509 | **Reject** trong profile IdP/SP yêu cầu asymmetric signing |
| SHA-1 digest | `http://www.w3.org/2000/09/xmldsig#sha1` | XML DigestMethod yếu | **Reject** |
| RSA-MD5 / MD5 digest | Các URI XML Signature/Encryption tương ứng | Lỗi thời, collision resistance kém | **Reject** |
| `null`/rỗng/URI không nhận diện | Không hợp lệ/không có | Không có định danh algorithm tin cậy | **Reject** |

**Cần phân biệt URI và JCA name.** SAML/XMLDSig dùng URI; Java JCA thường dùng `SHA256withRSA`, `SHA384withRSA`, `SHA512withRSA`, `SHA256withECDSA`. Chúng không phải chuỗi thay thế trực tiếp: phải dùng mapping thư viện đã duy trì. Không tự sửa `SignatureMethod Algorithm` sang URI mạnh hơn sau khi đã ký; thay nội dung `SignedInfo` sẽ làm chữ ký không khớp.

### 5.1. SHA-256 là baseline, không phải trần hiệu năng/bảo mật

RSA 2048 bit + SHA-256 là lựa chọn tương thích rộng và hiện vẫn được OWASP nêu làm baseline; khi hai bên hỗ trợ, RSA 3072 bit hoặc thuật toán hiện đại mạnh hơn có thể phù hợp chính sách tuổi thọ khóa và compliance. Dùng SHA-512 với khóa RSA yếu không cứu được key weakness; dùng ECDSA P-256/SHA-256 có thể hiệu quả nhưng một số IdP chưa hỗ trợ key type tương ứng.

**RSA-PSS** có ưu điểm mật mã riêng và có thể được tiêu chuẩn XMLDSig mới hỗ trợ, nhưng không nên giả định mọi IdP/SAML binding xử lý RSA-PSS được. Chọn thuật toán dựa trên **giao của khả năng hai bên** và policy được phê duyệt, không chọn chỉ theo mức “số bit băm càng lớn càng tốt”.

### 5.2. “Có trong thư viện” khác “được chính sách cho phép”

Một thư viện JCA/OpenSAML có thể parse hoặc verify chữ ký RSA-SHA1 vì mục tiêu tương thích lịch sử. Điều đó không có nghĩa ứng dụng sản xuất phải chấp nhận. Một allowlist ở application security boundary phải từ chối **trước khi tạo principal**, ngay cả khi phép verify đối với thuật toán legacy trả true.

Ngược lại, không để attacker chọn “phương án fallback” bằng `SigAlg` hoặc `DigestMethod` trong message. Các trường ấy là input để **kiểm tra so với policy**, không được điều khiển policy.

## 6. Chính sách chấp nhận chữ ký: explicit allowlist và fail closed

### 6.1. Bộ quy tắc nên định nghĩa

Một policy minh họa cho các SP/IdP dùng RSA:

```yaml
# Đây là tài liệu chính sách minh họa, KHÔNG phải Spring Boot properties.
samlSignaturePolicy:
  outboundAuthnRequest:
    approvedSignatureMethods:
      - "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
    approvedKeyTypes:
      - "RSA"
    minRsaBits: 2048
  inboundSamlResponse:
    approvedSignatureMethods:
      - "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
      - "http://www.w3.org/2001/04/xmldsig-more#rsa-sha384"
      - "http://www.w3.org/2001/04/xmldsig-more#rsa-sha512"
    approvedDigestMethods:
      - "http://www.w3.org/2001/04/xmlenc#sha256"
      - "http://www.w3.org/2001/04/xmldsig-more#sha384"
      - "http://www.w3.org/2001/04/xmlenc#sha512"
    minRsaBits: 2048
    rejectUnknownAlgorithms: true
    rejectSha1AndMd5: true
    requireTrustedIssuerAndCertificate: true
    requireSignedAuthenticationContent: true
    verifyReferenceCoverage: true
```

**Đọc policy:** ví dụ dùng allowlist inbound có RSA-SHA256/384/512, digest SHA-2 và RSA key đủ mạnh. Một IdP khác có thể được phê duyệt dùng ECDSA P-256/SHA-256. Các trường trên **không tự cấu hình framework**; phải triển khai được trong OpenSAML/XML Security policy/validation integration của phiên bản thực tế và kiểm thử bằng fixture ký thật.

Một hệ thống không nên xem flag `rejectSha1AndMd5=true` trong YAML tự đặt là “đã bảo vệ” nếu chưa có code/framework thực thi. Chứng minh bằng integration test: một SAMLResponse được ký toán học hợp lệ bằng RSA-SHA1 **vẫn bị reject**.

### 6.2. Cấp chính sách theo IdP/registration

Với nhiều IdP, nên có approved suite theo **registration được quản trị** thay vì một danh sách toàn cục quá rộng:

| Registration | Certificate tin cậy | Inbound allowed suite | Outbound request suite |
| --- | --- | --- | --- |
| `corp` | IdP corp signing certs đã duyệt | RSA-SHA256 + SHA-256 | RSA-SHA256 |
| `partners` | IdP partner signing certs đã duyệt | RSA-SHA384 + SHA-384 khi tương thích | RSA-SHA256 theo IdP |
| `legacy-test` | Test signing cert riêng | Legacy fixture chỉ cho test **âm tính** | Không đưa production |

**Không chấp nhận chữ ký của IdP A cho issuer B** chỉ vì hai registration cùng dùng thuật toán RSA-SHA256. Thuật toán không xác minh danh tính signer; public key/trust binding với IdP cụ thể mới làm điều đó.

### 6.3. Chính sách reject cần kiểm tra theo thứ tự hợp lý

1. Giới hạn HTTP payload, Base64 decode và XML parser với hardening: không truy cập external entities hoặc remote references.
2. Xác định registration từ **ngữ cảnh tin cậy**; không tự tải IdP metadata URL hay verification key từ browser input.
3. Xác định signatures và vùng dữ liệu security-critical cần validate; yêu cầu signing coverage theo SAML profile/policy.
4. Kiểm tra `SignatureMethod`, tất cả `DigestMethod`/references được dùng và canonicalization/transforms theo allowlist/profile; reject unknown/weak algorithms.
5. Kiểm tra kiểu/độ dài key, certificate/trust binding và nội dung signed references; thực hiện signature/digest verification bằng OpenSAML/XMLSec.
6. Xác minh `Issuer`/`Audience`/`Destination`/`Recipient`/`InResponseTo`, thời gian, subject confirmation và chống replay.
7. Chỉ sau thành công mới xây dựng principal/authorities và session.

Đây là **thứ tự kiểm soát logic**, không phải mô tả chính xác từng dòng bên trong mọi bản Spring Security/OpenSAML. Crypto verification và kiểm tra algorithm có thể được thư viện phối hợp theo thứ tự riêng; điều bắt buộc là **không có đường chấp nhận** bỏ qua policy.

### 6.4. Reject thay vì downgrade

Nếu IdP đề xuất chỉ hỗ trợ `rsa-sha1`, SP không nên tự động cho phép SHA-1 để đạt “SSO success”. Quy trình hợp lý:

- Đối chiếu IdP metadata/tài liệu và kiểm thử thuật toán thực phát.
- Yêu cầu IdP bật RSA-SHA256 hoặc suite đã duyệt, cập nhật metadata/cert tương ứng.
- Nếu không có overlap được phép, **không triển khai luồng đó**; ghi blocker về interoperability thay vì vô hiệu policy.
- Với ngoại lệ legacy thực sự bắt buộc, cần quy trình quản trị rủi ro: phê duyệt, phạm vi hẹp, thời hạn và kế hoạch loại bỏ; không đưa SHA-1 vào allowlist toàn cục hay tuyên bố an toàn tương đương.
- Không sửa `SignatureMethod` của XML hoặc `SigAlg` trong query để “đổi sang SHA-256” sau khi ký: chữ ký sẽ sai. Bên **signer** phải thực sự ký lại bằng thuật toán đã thống nhất.

**Thông báo lỗi bên ngoài:** “Không thể hoàn tất đăng nhập SSO.” Nội bộ có thể có reason code `WEAK_SIGNATURE_ALGORITHM` hoặc `UNSUPPORTED_DIGEST_ALGORITHM`, không cần echo XML/KeyInfo/private key.

## 7. Chọn khóa và chứng thư tương ứng thuật toán

### 7.1. RSA hay EC?

| Tiêu chí | RSA | Elliptic Curve / ECDSA |
| --- | --- | --- |
| Mức tương thích SAML phổ biến | Rộng; nhiều IdP/SP có sẵn | Phụ thuộc IdP, XML Security stack và certificate |
| Kích cỡ tối thiểu nên xét | **RSA ≥ 2048 bit** theo baseline, cân nhắc 3072 cho tuổi thọ lâu hơn | **P-256** hoặc curve đã duyệt |
| Thuật toán ký thường gặp | RSA-SHA256/384/512 | ECDSA-SHA256/384 khi tương thích curve |
| Khóa riêng ở đâu? | HSM/keystore/secret store với quyền tối thiểu | Tương tự |
| Lỗi thường gặp | Key RSA 1024, certificate/key mismatch | Dùng EC key nhưng IdP chỉ hỗ trợ RSA |

**Không** tự đổi SP signing key sang EC trong khi IdP đăng ký RSA certificate; thuật toán phải tương thích **key type thực tế**. RSA-SHA256 trên EC certificate sẽ không verify đúng. Lưu ý RSA-PSS cần các parameters/URI cụ thể, không được coi cùng một thuật toán với RSA PKCS#1 v1.5 chỉ vì cả hai “có SHA-256”.

### 7.2. Kiểm tra certificate

- Xác minh certificate/key là của **IdP được phép tin** cho đúng registration. `KeyInfo` trong XML là dữ liệu đầu vào, không phải trust anchor.
- Theo policy, kiểm tra hạn `notBefore/notAfter`, key usage/digitalSignature, thuật toán ký certificate, loại key và rotation. Trong một số SAML integration, certificate có thể self-signed nhưng được pin trong metadata tin cậy; **PKIX trust store cho HTTPS không tự xác minh SAML trust**.
- Certificate signing algorithm có thể là SHA-256, nhưng XML `SignatureMethod` vẫn phải được kiểm tra **riêng**.
- Certificate rollover nên cho phép key cũ + mới trong cửa sổ chuyển tiếp có giám sát; **không** cho phép một certificate bất kỳ chỉ vì “new cert” được gửi kèm SAMLResponse.
- Private signing/decryption key không log, không trả về exception, không để trong source Git. Nếu lộ private signing key, xử lý là incident và rotate trust theo quy trình.

### 7.3. Key rotation và thuật toán là hai migration độc lập

Một IdP có thể đổi certificate nhưng tiếp tục ký XML bằng RSA-SHA256; hoặc giữ RSA key mới hợp lệ nhưng bắt đầu phát RSA-SHA384. Cần test **cả hai chiều**:

```text
Credential trust migration: old trusted cert → new trusted cert
Algorithm policy migration:  RSA-SHA256 → RSA-SHA384 (khi được duyệt)

Không suy ra một migration đã hoàn tất chỉ vì migration kia thành công.
```

Theo dõi signature verification failures, unknown signing key, thuật toán không hỗ trợ, request/response compatibility và các certificate nearing expiry. Kế hoạch rollback không được mở lại SHA-1 hoặc thêm trust certificate không rõ nguồn.

## 8. Cấu hình Spring Security cho AuthnRequest được ký

### 8.1. Spring Security làm gì theo mặc định?

Theo tài liệu Spring Security về “Producing AuthnRequests”, Spring Security thường tạo chữ ký AuthnRequest bằng **rsa-sha256** khi yêu cầu ký; asserting party metadata có thể mô tả các signing algorithms được hỗ trợ và ảnh hưởng cách chọn algorithm. Để **thực sự ký**, SP phải có **private signing credential**. Flag trong metadata **không tự tạo chữ ký** nếu key/cert không có.

Khi IdP yêu cầu `WantAuthnRequestsSigned=true`, cấu hình SP tương ứng; khi IdP không yêu cầu, vẫn có thể có policy SP chủ động ký. Cần xác minh **dữ liệu trên wire** theo binding thay vì chỉ nhìn YAML/metadata.

### 8.2. Spring Boot 3.x – YAML minh họa

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "{baseUrl}/saml/sp/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
              binding: POST
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/config/sp-signing.crt"
            assertingparty:
              entity-id: "https://login.example.org/idp"
              verification:
                credentials:
                  - certificate-location: "file:/run/config/idp-signing.crt"
              singlesignon:
                url: "https://login.example.org/saml/sso"
                binding: REDIRECT
                sign-request: true
```

Đây là **cấu hình giả lập**, cần IdP registration/certificates/key hợp lệ, dependency Spring Security SAML2 SP và binding/metadata đúng. `{baseUrl}`/`{registrationId}` là **URI template placeholders của Spring Security**, không phải lệnh cần copy thay thủ công.

Phân biệt:

- `signing.credentials`: SP private key + public certificate để **ký AuthnRequest**.
- `assertingparty.verification.credentials`: IdP **public signing certificate** để **xác minh Response/Assertion**.
- `acs.binding=POST`: IdP chuyển response về SP theo POST; **không quyết định request đi Redirect hay POST**.
- `assertingparty.singlesignon.binding=REDIRECT`: browser chuyển AuthnRequest đến IdP SSO bằng Redirect.
- `sign-request=true`: yêu cầu ký outbound request; phải xác nhận key/cert/algorithm thực tế và tương thích metadata IdP.

### 8.3. SecurityFilterChain tối thiểu

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSignatureSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là **class cấu hình Spring Security**, không phải chương trình chạy bằng `java SamlSignatureSecurityConfiguration` độc lập. Nó bật SAML login và dùng RelyingPartyRegistration được cấu hình. **Nó không tự áp dụng một inbound SHA-1 deny policy** nếu XML signature validator đang cho phép algorithm đó. Cần kiểm tra version và cấu hình thuật toán ở OpenSAML/XML Security layer.

### 8.4. “signingAlgorithms” dùng cho chiều nào?

Tài liệu Spring Security hiện hành đưa ra cách **khai báo những signing algorithms mà asserting party hỗ trợ** để Spring Security chọn thuật toán ký **AuthnRequest gửi đi**; ví dụ Java **fragment phụ thuộc version**:

```java
import org.opensaml.xmlsec.signature.support.SignatureConstants;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

// Fragment nằm trong cấu hình registration, không phải class standalone.
// IdP metadata đã được administrator xác minh trước khi nạp.
RelyingPartyRegistration rp =
        RelyingPartyRegistrations
            .fromMetadataLocation("classpath:corp-idp-metadata.xml")
            .registrationId("corp")
            .assertingPartyMetadata(party -> party
                .signingAlgorithms(algorithms -> algorithms.add(
                    SignatureConstants.ALGO_ID_SIGNATURE_RSA_SHA512)))
            .build();
```

**Không hiểu nhầm đoạn code này:**

1. Nó cập nhật thông tin **algorithm support của IdP cho AuthnRequest SP gửi tới IdP**; **không** cấu hình Spring Security từ chối `rsa-sha1` trong chữ ký **SAMLResponse IdP gửi về**.
2. Việc `add(RSA_SHA512)` chỉ có ý nghĩa nếu IdP thật sự hỗ trợ algorithm này và SP có key/cấu hình thích hợp; không dùng để “ép” một IdP chỉ nhận SHA-256.
3. Cần cung cấp SP signing credentials riêng và SP entityID/ACS, IdP verification credentials qua metadata/cấu hình thực tế.
4. Cú pháp `assertingPartyMetadata(...)`, `SignatureConstants` và lựa chọn OpenSAML thay đổi qua các phiên bản; code mang tính **fragment tham khảo theo reference hiện hành**, hãy đối chiếu Spring Security release của dự án trước khi dùng.
5. Thêm một algorithm vào danh sách hỗ trợ **không phải** là cơ chế định nghĩa “chỉ cho phép một algorithm”; không tự suy ra thứ tự ưu tiên/chữ ký thực tế. Kiểm tra `SigAlg`/`SignatureMethod` của AuthnRequest được phát.

Nếu policy của SP yêu cầu RSA-SHA256 nhưng IdP chỉ quảng cáo RSA-SHA1, cách đúng là **báo interoperability blocker và nâng cấp IdP**, không thêm RSA-SHA1 vào cấu hình để “chạy tạm”.

## 9. HTTP-Redirect signature và XML signature khác nhau ở đâu?

### 9.1. Ký AuthnRequest với HTTP-Redirect binding

Luồng:

```text
AuthnRequest XML
  → raw DEFLATE
  → Base64
  → URL encode thành SAMLRequest
  → thêm RelayState (nếu có)
  → SigAlg URI + Signature (ký chuỗi tham số đã định)
  → HTTP 302 đến IdP SingleSignOnService
```

Nếu có RelayState, dữ liệu ký theo binding là:

```text
SAMLRequest=<URL-encoded>&RelayState=<URL-encoded>&SigAlg=<URL-encoded>
```

Khi RelayState vắng, bỏ thành phần đó. `Signature` không phải thành phần của chuỗi được ký. Thuật toán ghi trong `SigAlg` phải nằm trong allowlist của IdP; ký bằng RSA-SHA256 không đồng nghĩa XML bên trong phải có `<ds:Signature>`.

Một URL được gửi có `SigAlg=rsa-sha1` dù SP định dùng SHA-256 là dấu hiệu **policy mismatch/unsupported downgrade**, không được “sửa” bằng cách thay query parameter mà giữ signature cũ. IdP phải reject algorithm không được duyệt, kể cả khi byte signature có thể verify theo SHA-1.

### 9.2. Với HTTP-POST binding

AuthnRequest thường được ký bằng XML Digital Signature trong XML rồi Base64 encode thành form `SAMLRequest`. `SignatureMethod` và `DigestMethod` được khai báo trong `ds:SignedInfo`/`ds:Reference`. IdP phải kiểm tra chữ ký XML và thuật toán theo policy IdP; không lấy `SigAlg` query làm điều kiện duy nhất cho POST.

SAMLResponse qua ACS cũng thường là HTTP-POST chứa XML đã ký ở Response hoặc Assertion; SP cần kiểm tra XML signature coverage và digest. Signature Redirect query và XML Signature POST là **hai kiểu bảo vệ thông điệp theo binding**, không được trộn logic.

## 10. Chính sách kiểm tra SAMLResponse nhận về bằng Spring Security/OpenSAML

### 10.1. Provider mặc định làm gì và khoảng trống policy

Spring Security dùng `Saml2WebSsoAuthenticationFilter`, authentication token converter và OpenSAML authentication provider để verify SAMLResponse/Assertion. Provider kiểm tra chữ ký, issuer, destination, các điều kiện assertion và các ràng buộc giao thức theo phiên bản. Các bản Spring Security hiện hành có thể dựa trên OpenSAML 5; bản Spring Security 6.x có cấu hình OpenSAML 4 hoặc 5 tùy release/dependency.

**Bắt buộc kiểm chứng riêng:** provider và XML Security library ở phiên bản ứng dụng có **thực sự từ chối SHA-1-based `SignatureMethod` và `DigestMethod` không**. Không giả định mặc định của JVM/JCA, flag `sign-request` hay outbound `signingAlgorithms` tự tạo inbound denylist.

Nếu framework/library chưa áp dụng chính sách cần thiết, lựa chọn là cấu hình **supported algorithm policy/secure-validation của OpenSAML/XML Security** hoặc extension validation **nằm trong authentication boundary, trước khi chấp nhận principal**, và giữ toàn bộ kiểm tra mặc định. Implementation cụ thể phải theo API release; không nên đưa một filter tự parse raw SAMLResponse để “xem thuật toán” rồi cho qua verify.

### 10.2. Pseudocode thuật toán an toàn

```text
Input: HTTP POST ACS, SAMLResponse từ browser (UNTRUSTED)
  -> enforce input size, parse XML securely and validate structure
  -> select TRUSTED RelyingPartyRegistration
  -> identify every signature/reference protecting authentication content
  -> reject disallowed SignatureMethod / DigestMethod / dangerous transforms
  -> reject weak/incorrect signing key; trust only registered IdP key(s)
  -> cryptographically verify signature and digest of signed XML objects
  -> reject missing/ambiguous coverage and XML signature wrapping
  -> verify issuer, audience, recipient, destination, time, InResponseTo,
     subject confirmation and replay controls
  -> only then create Authentication and map authorized roles
If any step fails:
  -> no SAML principal/session authentication
  -> generic browser error; internal allowlisted reason code
```

Đây là **thiết kế policy/validation**, không phải Java code trực tiếp của `OpenSaml5AuthenticationProvider`. Không được hoán đổi kiểm tra giữa các bước theo cách khiến một giá trị chưa được tin biến thành key/issuer/role của user.

### 10.3. Kiểm tra cả SignatureMethod và DigestMethod

Một attacker có thể gửi XML với:

- `SignatureMethod=rsa-sha256` nhưng `DigestMethod=sha1`.
- `SignatureMethod=rsa-sha1` và `DigestMethod=sha256`.
- Chữ ký ở `Response` dùng RSA-SHA256, nhưng có thêm một `Assertion` chưa được bảo vệ.
- Nhiều `ds:Reference` với một reference yếu hoặc URI trỏ ngoài document.

Policy phải kiểm tra **mọi signature/reference có liên quan đến authentication data**, không chỉ phép so chuỗi `SignatureMethod.contains("sha256")`. Không tin prefix, suffix hoặc viết hoa/thường tùy tiện; so với **URI exact đã duyệt** và sử dụng parser/schema.

### 10.4. Secure validation không thay toàn bộ SAML policy

Apache Santuario (XML Security cho Java) hỗ trợ **secure validation** với giới hạn transforms, reference resolution và thuật toán cấm như MD5. Tuy nhiên các hạn chế cụ thể và mặc định bật/tắt có thể khác theo version/call path. Bật chế độ bảo vệ ở thư viện XML Security nếu framework hỗ trợ và đảm bảo dependency được cập nhật, **rồi vẫn tự kiểm thử yêu cầu reject SHA-1**.

Đặc biệt, XML Signature secure validation tự nó **không biết** issuer nào SP tin, ACS nào hợp lệ hoặc assertion nào được app dùng làm principal. Cần kiểm tra SAML profile, reference coverage, SAML trust và audience/destination **bên cạnh** XML signature security.

### 10.5. Không sửa verifier bằng cách bỏ validation mặc định

Đoạn sau là **anti-pattern**:

```java
// Sai: dùng getter thô từ XML chưa verify để cấp quyền.
// String issuer = xml.getElementsByTagName("Issuer").item(0).getTextContent();
// if (issuer.contains("trusted")) return createAuthenticatedAdmin();
```

Không triển khai “kiểm tra algorithm” bằng regex trước khi cấp role. Với XML canonicalization, namespaces, signed references và signature wrapping, cách đó bỏ qua những điều kiện cốt lõi. Nếu cần tùy biến OpenSAML provider, hãy dùng extension hooks/documentation đúng phiên bản và **ủy quyền kiểm tra chữ ký/trust/conditions cho provider chuẩn**.

## 11. Chuyển đổi từ thuật toán yếu sang mạnh

### 11.1. Kiểm kê theo từng tích hợp IdP

Tạo bảng để quản trị migration:

| Trường | Ví dụ cần ghi | Lý do |
| --- | --- | --- |
| Registration | `corp` | Phân biệt key/policy per IdP |
| XML signature algorithm IdP đang phát | RSA-SHA1 hoặc RSA-SHA256 | Xác định thay đổi bắt buộc |
| XML digest algorithm | SHA-1 hoặc SHA-256 | Không quên một reference yếu |
| IdP signing certificate key type/size | RSA-2048 | Đánh giá sức mạnh key |
| SP AuthnRequest binding/signing | Redirect + RSA-SHA256 | Kiểm tra chiều SP→IdP riêng |
| IdP supported algorithms từ metadata/docs | RSA-SHA256, RSA-SHA384 | Biết khả năng interoperability |
| Rollover plan | New cert trusted trước thời điểm đổi | Tránh downtime |
| Deadline/owner/test result | Ngày, người phụ trách, test harness | Theo dõi và loại bỏ ngoại lệ |

Dữ liệu này nên được quản lý tại kho cấu hình/secret governance được phân quyền; không public danh sách key aliases hoặc mật khẩu keystore.

### 11.2. Các bước migration có thể kiểm chứng

1. **Inventory:** đo thuật toán thực tế trên test environment bằng verifier/thông tin audit không chứa raw assertion.
2. **Agree:** chốt với IdP/SP thuật toán signature/digest, key type/size, nơi đặt signature và binding.
3. **Prepare:** cấu hình certificate/keys mới nếu cần; đăng ký SP public signing cert cho IdP và IdP public signing cert cho SP.
4. **Deploy support:** đảm bảo verifier hỗ trợ **mạnh**, không cần mở rộng sang yếu. Cấu hình outbound request theo IdP agreement.
5. **Test:** SAML signed fixtures có RSA-SHA256/SHA-256 phải thành công; fixtures SHA-1, MD5, mismatch/downgrade, weak keys phải bị từ chối.
6. **Cutover:** IdP bắt đầu phát thuật toán mạnh và rollover keys theo lịch; SP theo dõi tỷ lệ login fail.
7. **Enforce:** khi các tích hợp đã tương thích, chốt allowlist, xóa legacy exceptions và cảnh báo phát hiện thuật toán yếu.
8. **Document:** ghi rõ kết quả test, version OpenSAML/Spring, thời hạn chứng thư và quy trình tiếp theo.

Cần phân biệt failure do **algorithm** với failure do **certificate rollover**. Việc chỉ thay certificate không tự đổi XML SignatureMethod; ngược lại đổi RSA-SHA256 sang RSA-SHA512 không tự thay key/certificate.

### 11.3. Nếu nhà cung cấp vẫn phát SHA-1

Không âm thầm fail-open hay “tạm cho login” bằng cách tắt signature verification. Nếu policy nội bộ cấm SHA-1, **bị chặn là kết quả đúng**. Việc xử lý là nâng cấp IdP, chuyển nhà cung cấp, giới hạn tích hợp trong môi trường không sản xuất, hoặc xin ngoại lệ rủi ro theo quy trình chính thức và có thời hạn (nếu tổ chức cho phép). Một ngoại lệ không được lan sang IdP khác.

Không khuyên giả mạo signer hoặc edit `SigAlg`/`DigestMethod` ở giữa đường: phải **sign lại ở bên phát message** với private key đúng, và verify theo hợp đồng.

## 12. Java 17+: kiểm tra allowlist trước khi verify chữ ký

Ví dụ sau sử dụng **Java SE 17 thuần**, không cần thư viện SAML. Nó minh họa rằng một policy sẽ:

- Chỉ chấp nhận cặp **RSA-SHA256** và **SHA-256 digest URI** đã cho phép.
- Kiểm tra RSA public key ít nhất 2048 bit.
- Xác minh chữ ký trên một chuỗi bytes giả bằng JCA `Signature`.
- Từ chối payload bị sửa và từ chối `rsa-sha1` hoặc `sha1` **ngay cả khi object chứa một signature bất kỳ**.

**Đây KHÔNG phải SAML/XMLDSig verifier**: không canonicalize XML, không resolve signed references, không xác minh SAML Issuer/Certificate, không kiểm tra Conditions/`InResponseTo`. Trong SAML thật, việc băm reference, canonicalization, signature coverage và trust phải do OpenSAML/XML Security provider xử lý.

Lưu file `SamlAlgorithmPolicyDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.security.interfaces.RSAPublicKey;

public class SamlAlgorithmPolicyDemo {

    private static final String SIG_RSA_SHA256 =
        "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256";
    private static final String SIG_RSA_SHA1 =
        "http://www.w3.org/2000/09/xmldsig#rsa-sha1";
    private static final String DIGEST_SHA256 =
        "http://www.w3.org/2001/04/xmlenc#sha256";
    private static final String DIGEST_SHA1 =
        "http://www.w3.org/2000/09/xmldsig#sha1";

    static String inspect(String signatureUri, String digestUri,
                          PublicKey trustedKey, byte[] data, byte[] signed) 
            throws Exception {

        if (!SIG_RSA_SHA256.equals(signatureUri)
                || !DIGEST_SHA256.equals(digestUri)) {
            return "REJECT_ALGORITHM";
        }
        if (!(trustedKey instanceof RSAPublicKey rsaKey)
                || rsaKey.getModulus().bitLength() < 2048) {
            return "REJECT_KEY";
        }

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(trustedKey);
        verifier.update(data);
        return verifier.verify(signed)
                ? "ACCEPT"
                : "REJECT_SIGNATURE";
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair keys = generator.generateKeyPair();

        byte[] original = "test-payload".getBytes(StandardCharsets.UTF_8);
        byte[] altered = "test-payload-changed"
                .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(keys.getPrivate());
        signer.update(original);
        byte[] signature = signer.sign();

        System.out.println("strong: "
                + inspect(SIG_RSA_SHA256, DIGEST_SHA256,
                          keys.getPublic(), original, signature));
        System.out.println("tampered: "
                + inspect(SIG_RSA_SHA256, DIGEST_SHA256,
                          keys.getPublic(), altered, signature));
        System.out.println("sha1 signature URI: "
                + inspect(SIG_RSA_SHA1, DIGEST_SHA256,
                          keys.getPublic(), original, signature));
        System.out.println("sha1 digest URI: "
                + inspect(SIG_RSA_SHA256, DIGEST_SHA1,
                          keys.getPublic(), original, signature));
        System.out.println("unknown signature URI: "
                + inspect("urn:example:unknown", DIGEST_SHA256,
                          keys.getPublic(), original, signature));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac SamlAlgorithmPolicyDemo.java
java SamlAlgorithmPolicyDemo
```

Stdout **chính xác** (chữ ký sinh từ khóa ngẫu nhiên nhưng boolean kết quả cố định):

```text
strong: ACCEPT
tampered: REJECT_SIGNATURE
sha1 signature URI: REJECT_ALGORITHM
sha1 digest URI: REJECT_ALGORITHM
unknown signature URI: REJECT_ALGORITHM
```

Giải thích:

- `strong: ACCEPT`: signature được tạo và verify với cùng RSA key; thuật toán/digest URI nằm trong policy **mô phỏng**.
- `tampered: REJECT_SIGNATURE`: bytes khác original làm JCA verify thất bại.
- `sha1 signature URI` và `sha1 digest URI` bị **từ chối trước khi gọi verify** nhờ whitelist, dù các bytes chữ ký JCA ban đầu còn nguyên.
- `unknown signature URI` bị từ chối vì không thuộc danh sách.
- `REJECT_KEY` là đường lỗi có thể được kích hoạt khi đưa public key RSA dưới ngưỡng hoặc key khác RSA; main chỉ demo các trường hợp algorithm/tampering.

**Quan trọng:** Trong demo, `DIGEST_SHA256` chỉ là **metadata policy input**, vì JCA `SHA256withRSA` tự băm payload bytes và không thực hiện XML `ds:Reference` digest. **Không suy diễn đoạn code đã validate `DigestValue` của XML**. Đừng thay OpenSAML bằng phép verify trên chuỗi XML raw do browser cung cấp; chữ ký XML đòi canonicalization, transforms, ID reference, trusted certificate và SAML protocol validation.

## 13. Ma trận kiểm thử âm tính

| Fixture / tình huống | Kỳ vọng |
| --- | --- |
| Response/Assertion RSA-SHA256 + SHA-256, key IdP trusted, đủ các điều kiện | PASS |
| Response RSA-SHA384 + SHA-384, allowed suite của IdP cụ thể | PASS theo policy/hỗ trợ |
| Response RSA-SHA1 + SHA-1, chữ ký toán học hợp lệ | **REJECT_WEAK_ALGORITHM** |
| RSA-SHA256 nhưng `DigestMethod=sha1` | **REJECT_WEAK_DIGEST** |
| `SignatureMethod` không xác định hoặc null | Reject |
| `DigestMethod` không xác định ở một reference | Reject |
| DSA-SHA1/HMAC-SHA1 trong profile yêu cầu trusted X.509 asymmetric key | Reject |
| RSA key 1024 bit, signature RSA-SHA256 verify được | Reject key strength |
| ECDSA-SHA256 trên IdP chỉ cho phép RSA | Reject unsupported key/algorithm |
| RSA-SHA512 với public cert thực tế là EC | Reject key mismatch |
| Certificate của IdP B ký assertion có issuer của IdP A | Reject trust/issuer mismatch |
| XML chứa `KeyInfo` tự sinh của attacker | Không tự tin certificate từ KeyInfo; reject |
| Chữ ký ở Response hợp lệ nhưng app đọc assertion chưa được ký/không trong coverage | Reject |
| Reference URI trỏ sai ID hoặc duplicate ID | Reject; chống signature wrapping |
| XML có XSLT/remote reference không được phép | Reject transform/reference |
| Một `ds:Reference` SHA-256, một `ds:Reference` SHA-1 | Reject theo policy trên tất cả references liên quan |
| `SigAlg=RSA-SHA1` trong signed Redirect AuthnRequest | IdP test reject nếu policy cấm SHA-1 |
| `SigAlg=RSA-SHA256` nhưng signature byte sai | IdP reject |
| Chỉ thay `SigAlg` từ SHA-1 thành SHA-256 sau khi ký | IdP reject vì signature không khớp |
| Response có signature RSA-SHA256 nhưng `Audience` sai | Reject SAML validation |
| Response có signature hợp lệ nhưng hết hạn | Reject |
| Response có signature hợp lệ nhưng `InResponseTo` sai/replay | Reject |
| Cả old/new signing certificate hợp lệ trong rotation window | PASS chỉ với keys được IdP registration tin, đúng issuer và policy |
| Metadata bị attacker đổi certificate | Reject thay đổi chưa được quản trị phê duyệt |
| Exception/log chứa raw SAMLResponse hoặc private key khi reject | **FAIL security QA**; không chỉ kiểm tra auth rejection |

### 13.1. Hai hướng kiểm thử bắt buộc

**Chiều SP → IdP (outbound):** bắt request theo Redirect/POST, kiểm tra signature placement, `SigAlg`/`SignatureMethod`, binding, cert SP và chấp nhận tại IdP test. Sử dụng IdP test có policy từ chối SHA-1 để tránh xác nhận chỉ bằng “request gửi đi được”.

**Chiều IdP → SP (inbound):** phát fixtures SAMLResponse/Assertion được **ký bằng các khóa test** với SHA-256 và SHA-1 riêng. Một fixture RSA-SHA1 hợp lệ về toán học phải bị từ chối bởi policy nếu SHA-1 cấm. Đồng thời thử digest SHA1 với SignatureMethod RSA-SHA256, key yếu, wrong issuer, duplicated IDs và unsigned assertion.

Chỉ đổi một string trong XML fixture sau khi ký sẽ làm chữ ký sai, **không chứng minh policy thuật toán đã reject một chữ ký SHA-1 hợp lệ**. Muốn test algorithm restriction thật phải có fixture được ký theo thuật toán yếu trong môi trường kiểm thử có kiểm soát, không dùng assertion production.

### 13.2. Kiểm tra cấu hình/runtime

- Kiểm tra Spring Security/OpenSAML/XML Security version, secure-validation behavior và supported algorithm policy **trên đúng build đang chạy**.
- Ghi rõ approved signature/digest URIs và key strength trong security contract, lưu trong quản lý cấu hình được phân quyền.
- Với multi-node, tất cả pod phải dùng cùng algorithm allowlist/trusted IdP certificates. Một pod còn cho phép SHA-1 có thể trở thành điểm chấp nhận yếu.
- Key rotation thử cả old/new trust đúng khoảng thời gian, không fail-open khi key thiếu hoặc metadata stale.
- Không dùng raw payload/PEM private key trong CI logs; chỉ dùng test fixture public và khóa test được kiểm soát.

## 14. Logging, vận hành và ứng phó

### 14.1. Từ chối có lý do nội bộ, không lộ thông điệp

Khi policy reject, browser chỉ nên thấy thông báo chung như:

```text
Không thể hoàn tất đăng nhập SSO.
Vui lòng thử lại hoặc liên hệ hỗ trợ với mã sự kiện.
```

Audit nội bộ có thể có:

```json
{
  "event": "saml_auth_rejected",
  "event_id": "3c98b4af-52d3-4326-926f-a8d16be946c8",
  "registration": "corp",
  "reason_code": "WEAK_SIGNATURE_ALGORITHM",
  "result": "DENIED"
}
```

Mẫu trên là dữ liệu giả. Không log raw `SAMLResponse`, `SAMLRequest`, XML `SignedInfo`, `SignatureValue`, private keys, `RelayState` bí mật, session cookie hoặc `exception.getMessage()` có thể chứa dữ liệu SAML. Cũng không đưa thuật toán/key alias/issuer chưa xác minh vào client error body.

### 14.2. Metrics hữu ích

- `saml_signature_algorithm_rejected_total{registration,reason}` với labels lấy từ allowlist đã kiểm soát.
- Tỉ lệ login success/failure theo IdP registration trong thời gian cert rollover.
- Số lỗi unsupported algorithm, invalid signature, untrusted key, XML reference coverage, time mismatch.
- Certificate/key expiry/rotation alerts và các instance bị configuration drift.

Tránh label `NameID`, email hoặc chuỗi `SignatureMethod` không được allowlist bởi attacker để khỏi rò dữ liệu hoặc gây metric cardinality explosion. Error detail được hạn chế trong kênh vận hành có phân quyền.

### 14.3. Nếu phát hiện đang chấp nhận SHA-1

1. Xác nhận bằng test fixture có chữ ký SHA-1 **thực sự hợp lệ** và kiểm tra đó là incoming Response/Assertion hay outbound request.
2. Xác định phiên bản OpenSAML/XML Security, IdP registration và code/custom validation đã khiến thuật toán được chấp nhận.
3. Áp dụng restriction ở đúng authentication/signature verification boundary, không chỉ thêm điều kiện sau khi session đã được tạo.
4. Phối hợp IdP nâng cấp sang SHA-256+, certificate/key strength và rotation nếu cần.
5. Kiểm tra logs, telemetry, existing sessions và dấu hiệu lạm dụng; nếu có sự cố nghiêm trọng, kích hoạt incident response.
6. Bổ sung regression test yếu/mạnh và giám sát rollout để tránh một pod hoặc IdP khác tiếp tục hỗ trợ thuật toán cũ.

Không tin một thay đổi `JDK disabledAlgorithms` hoặc thuộc tính `SignatureMethod` của AuthnRequest gửi đi là đủ bảo vệ XML Signature inbound: **test end-to-end trên phiên bản thực**.

## 15. Checklist review trước khi triển khai

- [ ] Đã phân biệt XML `SignatureMethod`, `DigestMethod`, certificate signature algorithm và TLS.
- [ ] Approved signature/digest URIs được **allowlist** theo registration/IdP và threat model, không fallback về SHA-1/MD5.
- [ ] RSA key ít nhất 2048 bit hoặc EC curve/key strength được phê duyệt; không dùng key yếu chỉ vì chữ ký verify được.
- [ ] SP private signing key và IdP public verification cert đúng chiều, được quản lý/rotate an toàn.
- [ ] SAML Response/Assertion verify bằng registered trusted IdP key, không trust tùy ý `ds:KeyInfo`.
- [ ] Tất cả signatures/references bảo vệ data authentication đều được kiểm tra, có phòng vệ XML Signature Wrapping.
- [ ] XML parser/schema/transform/reference security được bật và giới hạn; không tải external resources từ XML chưa tin.
- [ ] Algorithm policy được thực thi **trước khi tạo Authentication**, giữ các kiểm tra issuer/audience/recipient/time/`InResponseTo`/replay.
- [ ] Outbound AuthnRequest algorithm theo capability IdP; `signingAlgorithms`/`SigAlg` không bị nhầm inbound verification whitelist.
- [ ] Callback XML Signature và Redirect signature được kiểm tra theo **binding khác nhau**.
- [ ] Tất cả các instance/nodes có cùng policy và trust config; metadata/cert rotation có test.
- [ ] Test fixture RSA-SHA1 có chữ ký hợp lệ về toán học vẫn bị từ chối; thử DigestMethod SHA1 với SignatureMethod RSA-SHA256.
- [ ] Test expired assertion, wrong audience, wrong issuer, duplicate ID, reference mismatch và replay đều bị từ chối.
- [ ] Error response/log/APM/WAF không tiết lộ assertion, `SignatureValue`, private key hoặc exception dump.
- [ ] Có kế hoạch loại bỏ IdP chỉ hỗ trợ thuật toán yếu và quy trình ngoại lệ rủi ro (nếu được phép) rõ phạm vi/thời hạn.

## 16. Câu hỏi ôn tập

**1. Certificate của IdP dùng `sha256WithRSAEncryption`, nhưng SAML `SignatureMethod` là `rsa-sha1`. Có hợp lệ với policy cấm SHA-1 không?**  
Không. Thuật toán ký chứng thư và thuật toán ký XML là hai việc khác nhau. Chữ ký SAML đang dùng RSA-SHA1 nên phải bị từ chối.

**2. `SignatureMethod=rsa-sha256` có đủ để kết luận signed XML an toàn không?**  
Không. Cần kiểm tra cả `DigestMethod`, trusted key/key size, reference coverage, transforms, issuer/audience/recipient/time và replay.

**3. Một XML có chữ ký hợp lệ nhưng assertion dùng làm principal nằm ngoài vùng ký. Điều gì xảy ra?**  
Phải reject. Đây là tình huống liên quan XML Signature Wrapping; không được dùng claims không được chữ ký bảo vệ.

**4. `RSA-SHA512` luôn an toàn hơn `RSA-SHA256` với mọi IdP?**  
Không theo nghĩa triển khai. Cả hai có thể là lựa chọn hợp lệ khi key đủ mạnh, nhưng IdP/SP phải hỗ trợ. Chuyển thuật toán không làm key 1024 bit trở nên an toàn.

**5. Có thể dùng `assertingPartyMetadata(...).signingAlgorithms(...)` để SP tự động từ chối chữ ký SAMLResponse SHA-1 không?**  
Không được mặc định như vậy. Tùy chọn trong tài liệu Spring Security liên quan thuật toán **SP dùng ký AuthnRequest gửi tới IdP**; inbound verification policy cần kiểm tra/cấu hình riêng.

**6. Trong Redirect binding, tại sao không thấy `<ds:Signature>` mà request vẫn có thể được ký?**  
Vì chữ ký của HTTP-Redirect binding thường nằm trong query `SigAlg` và `Signature`, không nhất thiết trong XML AuthnRequest.

**7. Nếu IdP chỉ phát RSA-SHA1 thì làm gì?**  
Yêu cầu IdP nâng cấp/đổi tích hợp hoặc quy trình ngoại lệ chính thức có kiểm soát nếu tổ chức cho phép. Không silently downgrade hay tắt verify chữ ký.

**8. Tại sao phải test một SAMLResponse RSA-SHA1 được ký thật?**  
Nếu chỉ đổi URI của một response RSA-SHA256 đã ký, signature cũng sẽ hỏng, nên không chứng minh restriction SHA-1 hoạt động. Test đúng phải chứng minh **chữ ký SHA-1 đúng về toán học vẫn bị từ chối theo policy**.

**9. Public certificate trong `KeyInfo` có đủ để tin nguồn không?**  
Không. Certificate phải được ràng buộc với IdP/registration tin cậy thông qua cấu hình/metadata đã được quản trị, không phải tự lấy từ XML browser gửi.

**10. Có thể xem log raw `SAMLResponse` trên production khi debug algorithm?**  
Không nên. Dùng event code, test fixture, protected telemetry và key/certificate metadata đã được kiểm soát; raw assertions có thể chứa thông tin cá nhân hoặc bằng chứng đăng nhập có thể replay.

## 17. Tài liệu tham khảo

- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): chữ ký, trust key, lựa chọn RSA-2048/SHA-256, khuyến nghị reject RSA-SHA1/HMAC-SHA1/SHA1 Digest và kiểm tra signed reference coverage.
- [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): cấu hình ký request, `signingX509Credentials`, RSA-SHA256 mặc định và thuật toán được IdP hỗ trợ.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): provider xác minh Response/Assertion, customization và validation.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): phân biệt request/response filters và trust boundary.
- [Apache Santuario – Java FAQ / Secure Validation](https://cwiki.apache.org/confluence/spaces/SANTUARIO/pages/24838162/java_faq): giới hạn XML Signature transforms, remote references, MD5 và secure validation.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): cấu trúc `AuthnRequest`, `Response`, `Assertion`, XML Signature và điều kiện.
- [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-Redirect/POST và chữ ký theo binding.
- [W3C XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core1/): `SignedInfo`, `SignatureMethod`, `DigestMethod`, references/transforms/canonicalization.
- [NIST SP 800-131A Rev. 2](https://csrc.nist.gov/pubs/sp/800/131/a/r2/final): chuyển đổi thuật toán và kích thước khóa theo chính sách an toàn mật mã.

**Ghi nhớ:** Để bảo vệ SAML federation, SP/IdP phải chọn **suite ký được duyệt** (thuật toán chữ ký + digest + loại/kích cỡ khóa), không chấp nhận SHA-1/MD5 chỉ vì thư viện còn hỗ trợ, và luôn xác minh **đúng signed Response/Assertion bằng certificate của IdP đã tin**. Cấu hình ký AuthnRequest gửi đi và policy từ chối chữ ký yếu nhận về **là hai nhiệm vụ khác nhau**; cả hai cần integration tests và vận hành khóa/chứng thư đúng quy trình.