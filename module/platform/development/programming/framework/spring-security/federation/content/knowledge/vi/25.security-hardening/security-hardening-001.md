# XML Signature Wrapping và nguyên tắc chỉ dùng assertion đã được xác minh

> **Chủ đề:** Spring Security – federation. **Nhóm:** Gia cố an toàn. Tài liệu Knowledge này giải thích tấn công XML Signature Wrapping (XSW) với SAML 2.0, tại sao một chữ ký kiểm thành công vẫn có thể dẫn đến đăng nhập sai danh tính, cách ràng buộc đúng phần tử XML được ký với phần tử ứng dụng sử dụng, và cách triển khai, kiểm thử, vận hành Spring Security SAML 2.0 Login an toàn. Các ví dụ Java 17 độc lập chỉ minh họa kiểm tra cấu trúc/chính sách, không phải thư viện xác minh chữ ký SAML.

## 1. Kết luận quan trọng nhất

Một câu định nghĩa:

**XML Signature Wrapping (XSW) xảy ra khi chữ ký hợp lệ bảo vệ XML object A nhưng ứng dụng lấy NameID, Attributes hoặc quyền từ XML object B không nằm trong phạm vi chữ ký tin cậy đó.**

Những điểm cần nhớ:
- `SignatureValue` hợp lệ **không tự** đồng nghĩa dữ liệu danh tính SP đang dùng đã được xác thực.
- `ds:Reference URI` trỏ tới **object được ký**. Phải kiểm Reference resolve tới duy nhất expected Response/Assertion.
- **Signed object** phải là **consumed object**, hoặc assertion được tiêu thụ phải được chứng minh nằm trong **verified signed Response subtree**.
- **ID duplicate, XML cấu trúc bất thường, XPath quá rộng, KeyInfo không tin cậy, transform ngoài policy** là các rủi ro phổ biến.
- Có thể ký **Response** hoặc **Assertion**, tùy SAML profile/IdP–SP contract; không nhất thiết mọi assertion cần chữ ký riêng khi Response đã được verify và bao phủ nó.
- Không được trộn NameID từ Assertion A và Attributes từ Assertion B rồi coi cả hai đều đã xác thực.
- Ngoài XML signature còn phải kiểm **Issuer, Audience, Destination, Recipient, InResponseTo, Conditions, SubjectConfirmationData, replay** và local account policy.
- Với Spring Security, ưu tiên `saml2Login` và OpenSAML provider mặc định; không tự parse raw SAMLResponse vào Spring SecurityContext.
- Vai trò business chỉ được sinh từ validated principal/attributes và một chính sách quyền rõ ràng.

**Hậu quả nếu thiếu ràng buộc signed/consumed:** Kẻ tấn công có thể lợi dụng parser và verifier chọn hai nodes khác nhau để tạo phiên local cho người dùng/quyền không được IdP ký.

## 2. Bối cảnh SAML Web Browser SSO

Các vai trò:
- **IdP:** Identity Provider xác thực người dùng và phát SAML Response/Assertion.
- **SP:** Service Provider, ví dụ ứng dụng Spring tại `https://portal.example.org`.
- **ACS:** Assertion Consumer Service, nơi browser POST SAMLResponse về SP.
- **RelyingPartyRegistration:** cấu hình Spring Security ràng buộc SP entityID, ACS URL, trusted IdP issuer, verification credentials và các setting giao thức.
- **Assertion:** bằng chứng SAML mô tả subject/authentication statement/conditions/attributes.
- **Response:** thông điệp protocol chứa Assertion hoặc EncryptedAssertion và các trường cấp Response.
- **ds:Signature:** XML Digital Signature có thể nằm trên Response hoặc Assertion.

Luồng chuẩn SP-initiated:

~~~text
Browser             Spring SP                  Trusted IdP
   | GET /private      |                            |
   +------------------>|                            |
   |<-- 302 AuthnRequest                           |
   +---------------------------------------------->|
   |                      IdP authenticates user    |
   |<-------------- Response via Browser -----------+
   |                                              |
   | POST SAMLResponse to SP ACS                 |
   +------------------>|                         |
   |                    Secure XML parsing       |
   |                    Select expected RP       |
   |                    Verify signature+key     |
   |                    Check signed coverage    |
   |                    Validate SAML conditions  |
   |                    Extract verified subject |
   |                    Load app account/roles    |
   |                    Create Authentication    |
   |<------ response ---+                         |
~~~

**Browser không phải trust anchor.** SAMLResponse đi qua browser, có thể bị sửa/thay/phát lại. Mọi chứng cứ phải được provider trên server xác minh trước khi ứng dụng tin NameID hay Attributes.

### 2.1. XML security và SAML protocol security là hai lớp

**XML layer:** chữ ký được ký trên dữ liệu nào, bằng khóa nào, ID/Reference nào, transform gì và parser chọn node nào.

**SAML layer:** thông điệp có đúng IdP, SP, ACS, đối tượng, thời gian, phiên đăng nhập, request correlation và replay policy không.

Một assertion signed đúng key nhưng sai Audience phải bị reject. Một Response có Audience đúng nhưng chữ ký chỉ bảo vệ node khác cũng phải bị reject.

## 3. Cấu trúc XML Signature cần hiểu

| Thành phần | Vai trò |
|---|---|
| `<ds:Signature>` | Container của XML signature |
| `<ds:SignedInfo>` | Danh sách References, canonicalization và SignatureMethod |
| `<ds:Reference URI="#id">` | Xác định tài nguyên/element được ký |
| `<ds:Transforms>` | Xử lý nội dung trước digest, có thể gồm enveloped-signature và C14N |
| `<ds:DigestMethod>` | Thuật toán băm của Reference |
| `<ds:DigestValue>` | Digest của referenced content sau transforms |
| `<ds:SignatureMethod>` | Thuật toán chữ ký |
| `<ds:SignatureValue>` | Chữ ký mật mã của SignedInfo |
| `<ds:KeyInfo>` | Thông tin gợi ý khóa; **không phải trust decision** |
| `ID="_A1"` | ID của SAML Response/Assertion, có thể là target của Reference |
| XML C14N | Quy tắc canonicalization dữ liệu XML để ký/verify |

Ví dụ **chỉ là sketch minh họa, không có chữ ký thật**:

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_A1"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <ds:Signature>
    <ds:SignedInfo>
      <ds:Reference URI="#_A1">
        <ds:Transforms>
          <ds:Transform Algorithm="urn:example:illustrative-transform"/>
        </ds:Transforms>
        <ds:DigestValue>ILLUSTRATION_ONLY</ds:DigestValue>
      </ds:Reference>
    </ds:SignedInfo>
    <ds:SignatureValue>ILLUSTRATION_ONLY</ds:SignatureValue>
  </ds:Signature>
  <saml:Subject>
    <saml:NameID>alice@EXAMPLE.ORG</saml:NameID>
  </saml:Subject>
</saml:Assertion>
~~~

Ví dụ cố ý lược bỏ các trường XMLDSig/SAML bắt buộc và dùng URI biến thể minh họa. **Không phải assertion có thể đưa vào production hoặc payload khai thác.** Nó chỉ cho thấy Reference hướng vào ID của chính assertion.

### 3.1. Chữ ký chỉ bảo vệ phạm vi Reference và transforms

Một chữ ký có thể ký:
- **Toàn bộ Response** khi Reference trỏ ID của Response.
- **Một Assertion** khi Reference trỏ ID của Assertion.
- Đối tượng XML khác theo chính sách XMLDSig, nhưng không thể mặc định là identity assertion của SAML Web SSO.

Nó không tự ký mọi sibling, mọi element tên Assertion, mọi URI HTTP và mọi DOM node trong document. Parser/verifier không được trả “signature valid” chung chung mà không gắn với **Reference target**.

### 3.2. Chữ ký hợp lệ có hai điều kiện khác nhau

1. **Cryptographic validity:** SignatureValue, SignedInfo, DigestValue và transforms kiểm đúng.
2. **Trust validity:** public key dùng verify thuộc trusted IdP signing credentials của đúng RelyingPartyRegistration.

Nếu attacker tự ký XML bằng private key của họ, cryptographic verification bằng attacker public key có thể trả true. Nhưng SP **không được tin** họ là IdP hợp lệ chỉ vì XML KeyInfo chứa certificate đó.

## 4. XSW xuất hiện từ hai cách chọn XML node không nhất quán

Một sai lầm concept:

~~~text
XML document supplied through browser
       |
       +-- Signature library:
       |      resolves Reference URI="#_SIGNED_A"
       |      verifies Assertion A -> true
       |
       +-- Application:
              searches raw XML for first Assertion
              picks Assertion B (different object)
              reads NameID/roles from B
              creates authenticated session
~~~

Đây là lỗi **signed-object vs consumed-object mismatch**. Không cần phá RSA hay biết IdP private key để tạo ra sai lệch nếu ứng dụng chấp nhận cấu trúc XML có nhiều lựa chọn node.

### 4.1. Vì sao gọi là XML Signature Wrapping?

Một biến thể di chuyển phần tử đã ký tới nhánh khác của XML document (nhưng giữ nguyên nội dung đã ký, tùy canonicalization/signature type), đồng thời đặt phần tử chưa ký vào nhánh mà ứng dụng ưu tiên đọc. Signature verifier vẫn có thể giải đúng ID của signed node, còn application parser tìm object khác.

Những kỹ thuật liên quan cần phòng vệ:
- Duplicate IDs.
- Signed node bị lồng trong wrapper bất thường.
- Multiple Assertions.
- XPath quá rộng hoặc chọn first/last.
- XML namespace/prefix confusion.
- Parser khác nhau giữa signature verifier và business code.
- Signed Reference trỏ một object khác với expected SAML Assertion.
- Untrusted KeyInfo hoặc transform dereference ngoài policy.
- Reparse dữ liệu sau verification nhưng không giữ binding tới verified object.

### 4.2. XSW không nhất thiết làm chữ ký sai

Trong một số XSW scenarios, chính signed element A vẫn nguyên và chữ ký A **vẫn xác minh đúng**. Lỗ hổng xảy ra vì ứng dụng dùng **object B** không nằm trong covered signed scope.

Tuy nhiên, nếu **toàn bộ Response được ký và chữ ký bảo vệ thực sự các Assertions con**, sửa nội dung các con trong protected subtree **thông thường sẽ làm signature/digest fail**. Không nên phát biểu sai rằng có thể chèn assertion vào bất kỳ signed Response nào mà signature vẫn hợp lệ; đó chỉ có thể là exploit khi có **scope, ID, XPath hoặc parser ambiguity**.

## 5. Bất biến an toàn: chỉ sử dụng assertion được chữ ký bảo vệ

Điều kiện chấp nhận nên được diễn đạt rõ:

~~~text
Accept a SAML subject/attribute as authenticated ONLY IF:

1. XML parsed under a secure SAML-aware parser/profile.
2. Expected XML Signature(s) verified cryptographically.
3. Signing credential is trusted for the selected IdP.
4. Reference URI uniquely resolves to an allowed signed object.
5. The consumed Assertion is EXACTLY the verified signed
   Assertion, or is demonstrably inside the verified
   signed Response's protected content.
6. No other unsigned/untrusted Assertion contributes to
   NameID, Attributes, Groups or application roles.
7. Issuer, Audience, Recipient, InResponseTo, time
   conditions, replay and local authorization checks pass.
~~~

**Một chữ ký hợp lệ của node A không được làm hộ chiếu cho node B.**

### 5.1. Những gì cần giữ nguyên giữa validation và business code

- **Object identity:** assertion dùng cho authentication là chính instance/validated security object của provider.
- **Document identity:** không parse lại một XML khác với parser khác để lấy NameID.
- **Provider identity:** signed key và issuer phải thuộc registration được tin.
- **SAML protocol context:** correlation và conditions áp cho chính assertion được dùng.
- **Attribute provenance:** không trộn attributes từ assertion chưa validated.
- **Local identity and role policy:** role mapping dựa verified subject và configured trust, không dựa raw XML.

Nếu framework trả một `Saml2AuthenticatedPrincipal`, controller dùng object đó thay vì cố chọn Assertion trực tiếp từ DOM.

## 6. Signed Assertion và Signed Response không phải một điều

### 6.1. Assertion-signed model

~~~text
Response ID=R1
  |
  +-- Assertion ID=A1
        |
        +-- ds:Signature
        |      ds:Reference URI="#A1"
        |
        +-- Issuer / Subject NameID
        +-- Conditions / Audience
        +-- SubjectConfirmationData
        +-- AttributeStatement
~~~

Khi chỉ Assertion A1 được ký, SP phải:
- Verify A1 signature bằng đúng trusted IdP key.
- Kiểm A1 là node được application tiêu thụ.
- Kiểm Response-level Issuer, Destination, Status, InResponseTo và các quy tắc SAML Web SSO liên quan.
- Kiểm Assertion Conditions, Audience, Recipient, time window và replay.
- Không đọc NameID từ một sibling unsigned Assertion A2.

### 6.2. Response-signed model

~~~text
Response ID=R1
  |
  +-- ds:Signature
  |      ds:Reference URI="#R1"
  |
  +-- Assertion ID=A1
        |
        +-- Subject, Conditions, Attributes
~~~

Nếu R1 thực sự được signed và verified bằng key IdP trusted, A1 nằm trong covered subtree của R1 và toàn bộ SAML protocol checks pass, thì A1 có thể được dùng **ngay cả khi A1 không có chữ ký riêng**. Không áp quy tắc “mọi Assertion bắt buộc ký riêng” cho tất cả SAML profiles.

### 6.3. Cả Response và Assertion đều được ký

Nhiều deployments ký cả hai:
- Duy trì toàn bộ kiểm tra theo IdP–SP contract.
- Chữ ký invalid không được âm thầm bỏ qua.
- Không chọn assertion khác sau khi verify một chữ ký.
- Kiểm giữa Response issuer và Assertion issuer theo policy.
- Multiple Assertions phải có policy rõ ràng.

Tài liệu Spring Security hiện hành mô tả provider OpenSAML kiểm signatures theo Response/Assertion, và về cơ bản **Response hoặc tất cả Assertions phải được bảo vệ bằng chữ ký**. Điều quan trọng là library chỉ map identity **sau** kiểm tra.

### 6.4. Signed Assertion vẫn có thể không dành cho SP này

Một assertion có chữ ký IdP hợp lệ vẫn phải bị reject khi:
- `AudienceRestriction` không có SP entityID đúng.
- `Recipient` không phải ACS của SP.
- `Destination` sai.
- `InResponseTo` không khớp AuthnRequest pending.
- `NotBefore` hoặc `NotOnOrAfter` không hợp lệ.
- `SubjectConfirmationData.NotOnOrAfter` hết hạn.
- `Issuer` không thuộc trusted IdP.
- Assertion ID đã được replay.
- User local bị khóa hoặc không có quyền vào tenant.

Chữ ký là một phần bắt buộc của verification, **không thay thế protocol checks**.

## 7. Các mẫu XSW nên có trong threat model

Các mô hình dưới đây là **XML cấu trúc minh họa để review**, không phải complete SAML messages hay signed exploit payloads.

### 7.1. Signed object chuyển vào nhánh khác

~~~xml
<p:Response xmlns:p="urn:oasis:names:tc:SAML:2.0:protocol"
            xmlns:a="urn:oasis:names:tc:SAML:2.0:assertion"
            ID="_R1">
  <a:Assertion ID="_UNSIGNED">
    <a:Subject>
      <a:NameID>untrusted-user@example.org</a:NameID>
    </a:Subject>
  </a:Assertion>
  <p:Extensions>
    <a:Assertion ID="_ORIGINAL_SIGNED">
      <a:Subject>
        <a:NameID>alice@example.org</a:NameID>
      </a:Subject>
    </a:Assertion>
  </p:Extensions>
</p:Response>
~~~

**Lưu ý:** Response này không phải SAML Schema-compliant XML, và không chứa real XML signature. Nó chỉ minh họa việc verifier có thể kiểm ID của object ở nhánh khác, trong khi application tìm direct Assertion. Strict schema/profile validation phải từ chối cấu trúc không hợp lệ.

### 7.2. Duplicate XML ID

~~~xml
<root xmlns:a="urn:oasis:names:tc:SAML:2.0:assertion">
  <a:Assertion ID="_same">...</a:Assertion>
  <a:Assertion ID="_same">...</a:Assertion>
</root>
~~~

Đây cũng **không** phải SAML Response hợp lệ. Nếu signature resolver và application khác cách chọn phần tử theo một ID trùng, có nguy cơ xác minh node này rồi dùng node khác. **Reject toàn bộ document** khi ID cần dùng không unique.

### 7.3. Signed/unsigned Assertions cùng tồn tại

~~~text
Response
  Assertion A1: signed and verified
  Assertion A2: unsigned; NameID differs
App:
  picks A2 merely because it appears first
~~~

Đó là lỗi. Khi profile không cho phép, reject multiple/mixed assertions. Nếu deployment hỗ trợ nhiều assertions hợp lệ, phải xác minh coverage của mỗi assertion được dùng và **không trộn claims** giữa các đối tượng.

### 7.4. Chữ ký ký node khác

Một signature valid có thể bảo vệ một XML element không phải login Assertion của SAML. Nếu app vẫn lấy username từ một Assertion ngoài signed scope, chưa có proof cho identity. Không chỉ kiểm “document chứa một ds:Signature và verify returns true”.

### 7.5. Prefix và XPath confusion

XML namespace prefixes không phải identity bất biến của element. Tránh:
- `getElementsByTagName("saml:Assertion")` trên raw XML.
- `getElementsByTagName("NameID").item(0)`.
- XPath theo wildcard/local-name thiếu expected namespace.
- Tự tìm `Attribute Name=role` ở bất kỳ descendant nào.

Phải parse namespace-aware, validate schema/profile và chỉ sử dụng SAML objects đã được provider xác minh.

## 8. XML Reference URI và ID resolution

### 8.1. Same-document ID reference

Một signature enveloped điển hình dùng:

~~~xml
<ds:Reference URI="#_A1"
              xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:Transforms>
    <ds:Transform Algorithm="urn:example:approved-transform"/>
  </ds:Transforms>
  <ds:DigestValue>ILLUSTRATION_ONLY</ds:DigestValue>
</ds:Reference>
~~~

Trong SAML verification, Reference nên trỏ đúng ID của expected Response/Assertion theo profile; external references không tự được cho phép.

### 8.2. Attribute ID không tự động thành typed XML ID

Tùy DOM/parser, một attribute tên `ID` không tự được nhận là XML ID nếu thiếu schema/ID registration. Nhưng việc tự gọi `setIdAttribute` cũng nguy hiểm nếu không kiểm:
- Node thuộc expected namespace và position?
- Có duplicate ID value nào trong toàn parsed document?
- Có resolver đang tìm node khác?
- Reference target chính xác là object cần ký?
- Các transforms có làm thay semantic của signed content không?

**Không “sửa” lỗi ID resolution bằng cách chọn element đầu tiên**. Reject ambiguous references.

### 8.3. Chỉ dùng transforms phù hợp

W3C XML Signature Best Practices khuyến nghị ứng dụng áp quy tắc nghiêm:
- Local ID references.
- Enveloped signature transform khi áp dụng.
- Canonicalization được phê duyệt.
- Hạn chế transform chain, không cho XSLT tùy ý.
- Check what is signed, không chỉ chữ ký tổng quát.

External Reference URI có thể lạm dụng SSRF/file read khi thư viện cho dereference file/network. Dùng secure validation của thư viện và rule allowlist.

### 8.4. Canonicalization không đồng nghĩa authenticated data selection

C14N giải quyết sự khác biệt biểu diễn XML khi ký/verify. Nó không quyết định:
- Node nào nên cho NameID.
- IdP nào được trust.
- Audience/Recipient có hợp lệ.
- Có ID duplicates.
- Business role mapping có an toàn.

Một signed canonicalized subtree đúng vẫn vô nghĩa nếu ứng dụng dùng data từ subtree khác.

## 9. Trusted IdP signing keys và KeyInfo

**Không lấy certificate trong incoming KeyInfo làm nguồn tin duy nhất.** Attacker có thể ký XML bằng private key của mình và tự chèn certificate trong KeyInfo. Chữ ký sẽ valid về toán học dưới public key đó, nhưng signer không phải IdP đã được SP phê duyệt.

Trust sources:
- Spring `RelyingPartyRegistration` đã cấu hình.
- IdP metadata đã được quản trị xác minh qua kênh tin cậy.
- Approved signing credentials/certificates cho IdP entityID.
- Metadata signature validation/certificate rollover theo tổ chức.
- Multi-tenant registration riêng biệt khi có các IdP khác nhau.

### 9.1. Certificate rollover

Trong giai đoạn IdP đổi khóa, SP có thể chấp nhận nhiều approved signing credentials. Nhưng:
1. Cập nhật approved metadata qua kênh tin cậy.
2. Không tự thêm KeyInfo của request.
3. Kiểm certificate/key association với IdP issuer.
4. Kiểm expiry và retirement theo agreed policy.
5. Không disable signature validation để “sửa lỗi login”.

### 9.2. Thuật toán chữ ký

Signature và digest phải nằm trong cryptographic algorithm allowlist theo chính sách, ví dụ RSA-SHA256 hoặc mức tương đương phù hợp profile. Reject SHA-1/MD5-based signatures hoặc transforms yếu khi security baseline cấm. **Không chỉ kiểm SignatureMethod mà bỏ DigestMethod/Transforms**.

## 10. Parse XML an toàn, schema validation và XXE

XSW cũng tận dụng những hành vi bất thường khi XML parser chấp nhận cấu trúc không đúng profile.

**Các bước phòng thủ:**
1. Giới hạn HTTP request size, Base64 decoded size, XML node count/depth.
2. Dùng XML parser namespace-aware.
3. Bật JAXP secure processing/DTD disable/external entity restrictions.
4. Không cho XXE hoặc external DTD/schema tự download.
5. Schema validation bằng bản SAML XSD **local, trusted và hardened** khi áp dụng.
6. Kiểm đúng root `samlp:Response` và cấu trúc con hợp SAML Web SSO.
7. Kiểm duplicate IDs.
8. Verify XMLDSig Reference, transforms, digest, signature.
9. Dùng đúng validated assertion object, không global DOM search.
10. Validate SAML protocol conditions và session security.

OWASP SAML Security Cheat Sheet khuyến nghị schema validation trước khi dùng XML cho security decisions, dùng local trusted schema và không tải schema từ URL lạ.

**XXE và XSW là hai lỗ hổng khác nhau:**
- XXE/DTD nhắm external entities, local files, SSRF, DoS.
- XSW nhắm signed-node/consumed-node mismatch.

Chặn XXE không thay kiểm signature coverage; kiểm signature cũng không cho phép bật XXE.

### 10.1. Schema không phải silver bullet

Schema validation rất hữu ích để từ chối signed assertions nằm sai vị trí, nested extensions và phần tử không được profile chấp nhận. Nhưng cần cả Reference target checks, key trust, unique IDs, parser consistency và protocol validation; đừng coi schema một mình đủ chống XSW.

## 11. Thứ tự validation hợp lý

Một high-level pipeline an toàn:

~~~text
1. Resolve trusted relying-party registration and ACS context
2. Decode POST body with size limits
3. Secure XML parse and schema/shape validation
4. Identify expected Response/Assertion signatures
5. Validate cryptographic signatures using approved IdP keys
6. Bind exact signed object(s) to selected Assertion(s)
7. Decrypt EncryptedAssertion/EncryptedAttribute in safe
   protocol-dependent order
8. Check Issuer, Destination, Status, Audience, Recipient,
   Conditions, SubjectConfirmation, InResponseTo
9. Reject replay and unsolicited flows outside policy
10. Map verified NameID and verified Attributes to local account
11. Load approved GrantedAuthority data and tenant membership
12. Create Spring Security Authentication
~~~

**Chú ý thứ tự decrypt:** Với signed Response, decryption của encrypted assertions có thể xảy ra sau khi Response signature đã được verified; với signed assertion và encrypted inner fields, decrypt trước signature verification có thể làm thay đổi signed subtree. Dùng thứ tự mặc định do OpenSAML/Spring provider quản lý, không xem checklist này là mã thay thế thuật toán cụ thể.

### 11.1. Chữ ký là của object nào?

Cần chứng minh:
- Reference URI = `#Response.ID` cho Response-signed profile hoặc `#Assertion.ID` cho Assertion-signed profile.
- Object resolved là duy nhất, thuộc current document và expected element.
- Signing key thuộc đúng IdP registration.
- Consumed NameID/Attributes nằm trong protected object.
- Không có unsigned alternate assertion cung cấp dữ liệu cho local authentication.

### 11.2. Không tái parse rồi tự chọn node sau verification

Nếu library verify DOM A nhưng application parse lại XML thành DOM B và dùng `getElementsByTagName`, rất khó chứng minh B dùng cùng verified node. Ưu tiên single SAML object graph trong trusted provider và chỉ đưa `Saml2AuthenticatedPrincipal` ra business layer.

## 12. Những trường SAML cần kiểm cùng signed assertion

| Trường | Điều kiện kiểm |
|---|---|
| Response `Issuer` | Trusted IdP entityID trong đúng RP registration |
| Assertion `Issuer` | Khớp trust context/profile |
| Response `Status` | Success, không biến error Response thành login |
| Response `Destination` | Đúng ACS URL public HTTPS |
| Response `InResponseTo` | Khớp pending AuthnRequest khi SP-initiated |
| Assertion `Conditions.NotBefore` | Không quá sớm ngoài clock skew |
| Assertion `Conditions.NotOnOrAfter` | Chưa hết hạn; boundary exclusive |
| `AudienceRestriction` | Có SP entityID được phép |
| `SubjectConfirmation.Method` | Bearer/approved method theo profile |
| `SubjectConfirmationData.Recipient` | Đúng ACS endpoint |
| `SubjectConfirmationData.InResponseTo` | Correlate AuthnRequest nếu cần |
| `SubjectConfirmationData.NotOnOrAfter` | Chưa hết hạn |
| `AuthnStatement` | Có/đúng profile và authentication context theo policy |
| Assertion ID | Chống replay theo trusted issuer và TTL |
| `RelayState` | State/correlation, safe return URL allowlist |
| NameID/AttributeStatement | Chỉ lấy trong validated protected assertion |

**Không trộn conditions của A, NameID của B, groups của C.** Mỗi business identity phải có proof gắn với chính assertion được tiêu thụ.

### 12.1. SP-initiated và IdP-initiated

**SP-initiated:** App đã gửi AuthnRequest, có ID pending; phải kiểm InResponseTo và subject confirmation correlation theo profile. Nếu IdP lỗi, không tắt correlation để “login dễ hơn”.

**IdP-initiated/unsolicited:** Có thể thiếu AuthnRequest/InResponseTo theo profile riêng. Chỉ chấp nhận nếu tổ chức thực sự bật/cho phép, với stricter issuer, signature, ACS, Audience, Recipient, replay, login-CSRF và landing policy. Nếu không cần, tắt unsolicited login.

### 12.2. Replay và time

Signature hợp lệ không có nghĩa assertion mới. Replay cache, TTL, duplicate IDs và session correlation vẫn cần. Nhiều replicas nên dùng shared replay state phù hợp. Clock skew chỉ nên nhỏ và có lý do, không kéo dài quá mức để qua test lỗi.

## 13. Spring Security SAML 2.0 Login và OpenSAML

Các thành phần trong Spring Security Servlet:
- `Saml2WebSsoAuthenticationFilter` nhận SAMLResponse tại ACS.
- `Saml2AuthenticationTokenConverter` tạo token và resolve registration.
- `OpenSaml5AuthenticationProvider` (theo dòng tài liệu Spring hiện hành) dùng OpenSAML để xử lý XML, signature, decryption, conditions.
- `RelyingPartyRegistrationRepository` giữ SP/IdP metadata.
- `Saml2Authentication` chứa authenticated principal/response theo API.
- `Saml2AuthenticatedPrincipal` cung cấp verified subject/attributes sau khi provider kiểm.
- `SecurityContextHolder` giữ Authentication đã thành công.
- HTTP authorization/method security áp local roles.

Theo Spring Security documentation, authentication provider:
1. Unmarshal Response.
2. Verify Response signature nếu có.
3. Decrypt EncryptedAssertion theo strategy.
4. Validate Response Issuer/Destination.
5. Verify Assertion signatures; bảo đảm Response hoặc Assertions được signed theo policy.
6. Decrypt inner encrypted IDs/attributes ở bước phù hợp.
7. Validate Conditions, Subject, Audience và các thuộc tính cần thiết.
8. Convert verified assertion thành Saml2AuthenticatedPrincipal/Authentication.

**Không copy logic “lấy assertion đầu tiên” ra ngoài provider trước verification.** Kể cả provider sau khi validate tất cả có thể chọn assertion đầu tiên làm principal, điều đó không bảo đảm một custom parser ngoài provider có thể làm tương tự.

### 13.1. Custom validators có thể làm mất kiểm soát

Spring Security cho cấu hình tùy biến ResponseValidator/AssertionValidator. Khi tùy biến:
- Ưu tiên **thêm** check vào defaults, không thay toàn bộ default validator list.
- Không bỏ Issuer, Destination, Audience hoặc BearerSubjectConfirmation.
- Không bỏ InResponseTo vì muốn hỗ trợ một test Response không đúng profile.
- Không dùng response token chưa verified để map NameID.
- Có negative tests cho XSW và expired/redirected assertions.

### 13.2. Multi-IdP configuration

Trong ứng dụng nhiều IdP/tenant:
- Registration phải được chọn từ trusted routing/session context.
- Signing keys gắn issuer tương ứng.
- Assertion Issuer và Response Issuer phải đúng trust configuration.
- Audience/Recipient và ACS đúng SP registration.
- Identity-linking tạo local user đúng tenant.
- Không chấp nhận “key hợp lệ của IdP A, attributes của IdP B”.

## 14. Spring Security Java 17: cấu hình an toàn tối thiểu

Tệp `src/main/java/com/example/security/SamlSecurityConfiguration.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Giải thích:** `saml2Login(Customizer.withDefaults())` dùng Spring Security SAML authentication path, thay vì tự parse XML lấy user. Đây là **Spring configuration class**, không phải Java standalone; cần Spring Boot app/project, RelyingPartyRegistration, IdP metadata/certificates, ACS URL, HTTPS và business authorization. Không dùng `javac SamlSecurityConfiguration.java` nếu thiếu dependencies.

### 14.1. Spring Boot properties fragment

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          portal:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
~~~

Giá trị là **mô phỏng endpoint IdP**. Production chỉ kết nối metadata đã được tổ chức approved/pinned với TLS/metadata signatures theo policy; không đọc metadata URI từ request user tùy ý. Kiểm chính xác property names theo Spring Boot release dùng trong dự án.

### 14.2. Maven dependencies fragment

Trong `pom.xml` đã có Spring Boot parent/BOM:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
~~~

Cần quản lý tương thích Spring Security/OpenSAML/Apache Santuario/XMLDSig/JDK. Không trộn jars đa phiên bản hoặc tắt secureValidation vì signature parsing lỗi. Fragment này không phải một POM standalone.

## 15. Đọc principal đúng cách sau Spring authentication

Tệp `src/main/java/com/example/web/MeController.java`:

~~~java
package com.example.web;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class MeController {

    public record CurrentUser(String verifiedName) {
    }

    @GetMapping("/me")
    public CurrentUser me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        if (principal == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        // Source: authenticated SAML principal created by provider.
        // NEVER re-read NameID from raw SAMLResponse XML.
        return new CurrentUser(principal.getName());
    }
}
~~~

Đây là **Spring MVC class** cần framework runtime, không phải standalone. Nó chỉ đọc user identity sau khi Spring Security SAML provider xác thực. Không đọc raw SAMLResponse từ request.

**Không phải mọi verified NameID là stable local user ID.** Có transient/persistent/email NameID profiles. Local account linking phải dựa trusted issuer + stable subject contract, unique local mapping, tenant và account lifecycle.

### 15.1. Attributes và quyền

Verified SAML AttributeStatement có thể chứa groups/department. Nhưng một claim `groups=Admin` không tự cấp `ROLE_ADMIN`. Chỉ mapped authorities qua allowlist trusted IdP/tenant và local policy. Một assertion ký đúng key có thể chứa claim không đủ để cho quyền business nếu IdP contract không authorize claim đó.

## 16. Java 17 độc lập: kiểm chính sách signed object = consumed object

Chương trình chạy được với JDK 17+. Nó **giả định** có một trusted signature verifier đã tạo `SignatureProof`. Đây là bài tập về **đúng object/coverage**, **không phải chương trình xác minh XML chữ ký thật**.

Tệp `SignedAssertionBoundaryDemo.java`:

~~~java
import java.util.List;
import java.util.Set;

public class SignedAssertionBoundaryDemo {

    enum Coverage { ASSERTION, RESPONSE }

    record Assertion(String id, String nameId) {
    }

    record SignatureProof(
            Coverage coverage,
            boolean cryptographicallyValid,
            boolean trustedKey,
            String signedObjectId,
            Set<String> coveredAssertions) {
    }

    static String consume(
            SignatureProof proof,
            List<Assertion> directAssertions,
            String selectedId) {

        if (!proof.cryptographicallyValid() || !proof.trustedKey()) {
            return "REJECT_SIGNATURE";
        }

        if (directAssertions.size() != 1) {
            return "REJECT_ASSERTION_SHAPE";
        }

        Assertion selected = directAssertions.get(0);
        if (!selected.id().equals(selectedId)) {
            return "REJECT_SELECTION";
        }

        boolean covered = switch (proof.coverage()) {
            case ASSERTION ->
                    selected.id().equals(proof.signedObjectId());
            case RESPONSE ->
                    proof.coveredAssertions().contains(selected.id());
        };

        if (!covered) {
            return "REJECT_NOT_COVERED";
        }

        return "AUTHENTICATED:" + selected.nameId();
    }

    public static void main(String[] args) {
        Assertion alice = new Assertion("a1", "alice");
        Assertion alternate = new Assertion("a2", "other");

        SignatureProof signedAssertion = new SignatureProof(
                Coverage.ASSERTION, true, true, "a1", Set.of());

        SignatureProof signedResponse = new SignatureProof(
                Coverage.RESPONSE, true, true, "r1", Set.of("a1"));

        SignatureProof untrusted = new SignatureProof(
                Coverage.ASSERTION, true, false, "a1", Set.of());

        System.out.println("verified=" +
                consume(signedAssertion, List.of(alice), "a1"));
        System.out.println("swapped=" +
                consume(signedAssertion, List.of(alternate), "a2"));
        System.out.println("multiple=" +
                consume(signedAssertion,
                        List.of(alice, alternate), "a1"));
        System.out.println("untrusted=" +
                consume(untrusted, List.of(alice), "a1"));
        System.out.println("response-signed=" +
                consume(signedResponse, List.of(alice), "a1"));
    }
}
~~~

Lệnh:

~~~bash
javac SignedAssertionBoundaryDemo.java
java SignedAssertionBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
verified=AUTHENTICATED:alice
swapped=REJECT_NOT_COVERED
multiple=REJECT_ASSERTION_SHAPE
untrusted=REJECT_SIGNATURE
response-signed=AUTHENTICATED:alice
~~~

**Giải thích:**
- `verified`: mô hình giả định signed Assertion A1 và consumed A1 khớp.
- `swapped`: ký A1 nhưng app chọn A2 → reject.
- `multiple`: mô hình chỉ hỗ trợ một direct Assertion → reject.
- `untrusted`: signature mathematically valid nhưng key không thuộc IdP trusted → reject.
- `response-signed`: mô phỏng A1 đã được trusted signed Response R1 bảo vệ.

**Giới hạn tuyệt đối:** các booleans và coveredAssertions trong demo không đến từ SAML/XMLDSig verifier thực. Nếu chúng do browser gửi, attacker có thể tùy ý đặt true. Không dùng class này làm authentication logic thực, không thay `OpenSaml5AuthenticationProvider`, không bỏ verification of issuer, signature, conditions, replay và local user policy.

## 17. Java 17 độc lập: parse XML an toàn và phát hiện duplicate ID

Bài này dùng JDK JAXP DOM để dạy một **preliminary XML shape guard**; không kiểm cryptography và không khẳng định XML được chấp nhận là full SAML Response hợp lệ.

Tệp `SamlXmlShapeDemo.java`:

~~~java
import java.io.StringReader;
import java.util.HashSet;
import java.util.Set;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.xml.sax.InputSource;

public class SamlXmlShapeDemo {

    static final String P =
            "urn:oasis:names:tc:SAML:2.0:protocol";
    static final String A =
            "urn:oasis:names:tc:SAML:2.0:assertion";

    static Document parse(String xml) throws Exception {
        DocumentBuilderFactory f =
                DocumentBuilderFactory.newInstance();

        f.setNamespaceAware(true);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        f.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
        f.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        return f.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));
    }

    static boolean uniqueIds(Element e, Set<String> ids) {
        if (e.hasAttribute("ID")
                && !ids.add(e.getAttribute("ID"))) {
            return false;
        }

        for (Node n = e.getFirstChild();
                n != null; n = n.getNextSibling()) {
            if (n instanceof Element child
                    && !uniqueIds(child, ids)) {
                return false;
            }
        }
        return true;
    }

    static String inspect(String xml) throws Exception {
        Element root = parse(xml).getDocumentElement();

        if (!P.equals(root.getNamespaceURI())
                || !"Response".equals(root.getLocalName())) {
            return "REJECT_ROOT";
        }

        if (!uniqueIds(root, new HashSet<>())) {
            return "REJECT_DUPLICATE_ID";
        }

        int count = 0;
        for (Node n = root.getFirstChild();
                n != null; n = n.getNextSibling()) {
            if (n instanceof Element child
                    && A.equals(child.getNamespaceURI())
                    && "Assertion".equals(child.getLocalName())) {
                count++;
            }
        }

        return count == 1
                ? "SHAPE_ONLY_NOT_AUTHENTICATED"
                : "REJECT_ASSERTION_SHAPE";
    }

    public static void main(String[] args) throws Exception {
        String start =
                "<p:Response " +
                "xmlns:p='" + P + "' " +
                "xmlns:a='" + A + "' ID='R1'>";

        String good = start
                + "<a:Assertion ID='A1'/>"
                + "</p:Response>";

        String duplicate = start
                + "<a:Assertion ID='R1'/>"
                + "</p:Response>";

        String nested = start
                + "<p:Extensions><a:Assertion ID='A1'/>"
                + "</p:Extensions></p:Response>";

        System.out.println("good=" + inspect(good));
        System.out.println("duplicate=" + inspect(duplicate));
        System.out.println("nested=" + inspect(nested));
    }
}
~~~

Chạy:

~~~bash
javac SamlXmlShapeDemo.java
java SamlXmlShapeDemo
~~~

**Stdout chính xác:**

~~~text
good=SHAPE_ONLY_NOT_AUTHENTICATED
duplicate=REJECT_DUPLICATE_ID
nested=REJECT_ASSERTION_SHAPE
~~~

**Giải thích ranh giới:**
- `good` chỉ đáp ứng shape guard demo; không có chữ ký, Issuer, SubjectConfirmation hay Conditions. **Không được login**.
- `duplicate` có cùng ID ở Response và Assertion → reject.
- `nested` không có direct Assertion mà có nested Assertion → reject theo demo policy.
- Demo chỉ kiểm attribute literal `ID`, không thay thế schema-aware XML ID resolution/unique checking của OpenSAML.
- Parser đã chặn DTD/external entities theo JAXP features trong môi trường JDK17 giả định. Production phải kiểm parser implementation, exceptions và limits cụ thể.
- Ví dụ XML không phải SAML-compliant Response hoàn chỉnh, nên không dùng nó làm integration test SAML authentication success.
- **Một shape check không chứng minh identity**. Chỉ SAML provider đầy đủ mới được tạo SecurityContext.

## 18. EncryptedAssertion và thứ tự verify/decrypt

SAML có thể dùng:
- `EncryptedAssertion`.
- `EncryptedID`.
- `EncryptedAttribute`.

**Encryption giải quyết confidentiality, không thay signature authenticity.**

Nếu một signed Assertion có encrypted elements bên trong, decrypt trước khi kiểm signature trên signed bytes/canonicalized structure có thể khiến signature bị invalid. Spring Security documentation phân biệt response-level decrypter và assertion-level decrypter để xử lý theo thứ tự an toàn.

Các kiểm tra bắt buộc:
1. Decryption key thuộc SP được cấp phép.
2. Chữ ký Response/Assertion được verify ở đúng layer.
3. Decrypted data vẫn nằm trong validated object graph.
4. Không trộn unsigned decrypted data với một signed assertion khác.
5. Kiểm Audience/Recipient/Conditions sau decryption theo SAML profile.
6. Có policy cho multiple EncryptedAssertions và mixed Assertions; reject unsupported forms.

**Không kết luận:** “Đã giải mã được thì chắc chắn do IdP gửi”. Một ciphertext có thể được mã hóa tới public key SP bởi bên không được tin nếu không có signature/protocol proof.

## 19. Apache Santuario secure validation

Apache Santuario hỗ trợ XMLDSig verification và cơ chế secure validation. Theo Santuario FAQ, secure validation trong các phiên bản hỗ trợ:
- Giới hạn số transforms và references.
- Cấm XSLT transforms.
- Cấm arbitrary filesystem/HTTP dereferencing.
- Chặn recursive RetrievalMethod patterns.
- Kiểm uniqueness của dereferenced IDs.
- Chặn DTD và thuật toán MD5.

JSR-105 context có thể hỗ trợ property:

~~~java
XMLValidateContext context =
        new DOMValidateContext(trustedKey, signatureElement);
context.setProperty(
        "org.apache.jcp.xml.dsig.secureValidation",
        Boolean.TRUE);
~~~

Đây là **code fragment**; cần imports, trustedKey và signatureElement được tạo trong đúng XML security pipeline. Nó không verify SAML/KeyInfo trust/subject selection chỉ vì một flag true. Hãy xác nhận default secureValidation và APIs theo đúng Santuario/JDK versions.

### 19.1. Signature/digest policy

- Allowed SignatureMethod và DigestMethod phải được liệt kê theo tổ chức.
- Không bật SHA-1-based signatures hoặc MD5 khi security baseline cấm.
- Không cho XSLT/external URI references ngoài policy.
- Không chấp nhận tất cả algorithms chỉ vì crypto library hỗ trợ.
- Audit sự thay đổi metadata keys/algorithms khi IdP rollover.

## 20. Identity linking và authorization sau assertion verification

Ngay cả protected assertion đã verify, SP vẫn phải:
1. Ràng buộc tới approved IdP issuer/registration.
2. Chọn stable identity key theo NameID format/qualifiers hoặc attribute được hợp đồng IdP–SP cho phép.
3. Link tới đúng localUserId, không tự gộp bằng email trùng.
4. Kiểm account status (active/disabled/locked) và tenant.
5. Load GrantedAuthorities theo approved group/role mapping.
6. Kiểm resource-level permission.

Ví dụ:
- Verified Assertion nói `NameID=alice@example.org`.
- App có local user Alice thuộc tenant A.
- Một tenant B cũng có email tương tự.
- **Không** tự cho local user của tenant B login từ cùng subject chỉ vì email giống.

Nếu IdP gửi attribute `groups=Admin`, app không tự cấp `ROLE_ADMIN`; đó là authorization policy riêng, phải có allowlist/identity authority contract.

### 20.1. Phiên đã xác thực vẫn có vòng đời

SAML signature verify lúc login không bảo đảm local session còn được phép mãi. User disable/group revoke cần xử lý session invalidation/role cache TTL và sensitive action recheck. SAML assertions có validity window riêng, HttpSession lifetime khác; không dùng lại raw SAMLResponse để tạo session mới.

## 21. Bộ kiểm thử tích cực

| Case | Tình huống | Kết quả mong đợi |
|---|---|---|
| P1 | Trusted IdP ký Response, một Assertion thuộc signed subtree | Accept nếu protocol conditions pass |
| P2 | Trusted IdP ký Assertion, đúng assertion được dùng | Accept nếu Response context hợp lệ |
| P3 | Cả Response và Assertion ký đúng | Verify theo configured policy |
| P4 | Reference URI local trỏ unique expected ID | Signature reference OK |
| P5 | Key rollover approved trust set | New cert accept theo policy |
| P6 | Audience và Recipient khớp SP | Protocol validation pass |
| P7 | InResponseTo khớp pending AuthnRequest | SP-initiated pass |
| P8 | Decrypt/verify EncryptedAssertion đúng order | Extract validated attributes |
| P9 | SAML valid nhưng local user disabled | Deny business access |
| P10 | Multi-tenant issuer/registration mapping đúng | Subject không bị nhầm tenant |
| P11 | Assertion đã xác minh và group allowlisted | GrantedAuthority đúng |
| P12 | Assertion ID/replay cache hợp lệ | Chấp nhận lần sử dụng được cho phép |

## 22. Bộ kiểm thử tiêu cực phòng XSW

| Case | Đầu vào lỗi | Kết quả |
|---|---|---|
| N1 | Ký Assertion A1, app đọc unsigned A2 | Reject |
| N2 | Ký A1 nhưng app chọn node first/last khác | Reject |
| N3 | Duplicate XML IDs | Reject |
| N4 | Reference URI trỏ node ngoài expected Response/Assertion | Reject |
| N5 | External HTTP/file Reference URI | Reject |
| N6 | XSLT/unknown transforms | Reject |
| N7 | Signature valid bằng attacker KeyInfo certificate | Reject |
| N8 | SHA-1/MD5 không đúng policy | Reject |
| N9 | Không có required trusted signature | Reject |
| N10 | Signature trên Response invalid | Reject |
| N11 | Multiple signed/unsigned Assertions trộn claims | Reject |
| N12 | Raw DOM getElementsByTagName chọn NameID | Security test fail |
| N13 | Audience không thuộc SP | Reject |
| N14 | Recipient không khớp ACS | Reject |
| N15 | Destination không đúng HTTPS/public host | Reject |
| N16 | InResponseTo không khớp | Reject SP-initiated |
| N17 | Assertion Conditions expired | Reject |
| N18 | SubjectConfirmationData expired | Reject |
| N19 | Assertion ID replay | Reject |
| N20 | Unknown issuer/key | Reject |
| N21 | Signed Response tenant A dùng cho tenant B | Reject |
| N22 | Parser reparse DOM B sau verify DOM A | Không cho identity từ B |
| N23 | XML DTD/XXE/external entity | Reject |
| N24 | XML bomb/too many nested elements | Reject |
| N25 | Empty/invalid Response Status | Reject |
| N26 | Unsigned AttributeStatement mang ROLE_ADMIN | Ignore/reject |
| N27 | Unexpected EncryptedAssertion mix | Reject |
| N28 | Custom validator bỏ Audience | Regression test fail |
| N29 | IdP-initiated khi unsolicited disabled | Reject |
| N30 | RelayState open redirect | Reject |
| N31 | NameID transient tự link vào local admin | Deny account link |
| N32 | Signed assertion valid nhưng local account disabled | Deny |

### 22.1. Regression phải chạy trên real SAML provider

Một unit test `assertTrue(signatureOk)` giả lập không chứng minh XSW đã được chặn. Integration suite cần:
1. Test IdP signing keys/metadata và SP registration.
2. Valid signed baseline SAMLResponse.
3. Real HTTP POST đến Spring ACS.
4. Trường hợp wrapped/multiple/duplicate ID trong XML.
5. Các reference/issuer/audience/correlation/timing failures.
6. Assert không tạo authenticated SecurityContext khi reject.
7. Assert final principal/authorities đến **chính signed assertion được chấp nhận**, không từ unsigned alternate.
8. Certificate rollover/multi-IdP tests.
9. Replay/CSRF/session handling.
10. Log redaction và privacy checks.

Không cần phơi bày payload thực cho user cuối. Test SAML messages và credentials nên nằm trong test harness có bảo vệ, không trong public logs/docs.

## 23. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm |
|---|---|---|
| Signature valid nhưng user sai | Signed object khác consumed object | Trace Reference và parsed object identity |
| Login được dù có unsigned Assertion | Custom converter/bypass | Restore defaults, negative tests |
| Multiple Assertions dẫn đến user khác | Policy/select node sai | Validate all required signatures/coverage |
| Duplicate ID lookup không nhất quán | ID registration/parser resolver | Reject duplicates, secure validation |
| KeyInfo chứa cert lạ | Trust selection sai | Only approved registration signing credentials |
| Response ký nhưng Audience sai | Assertion validators bị bỏ | Restore audience checks |
| Assertion ký nhưng Destination sai | Response protocol validators bị bỏ | Check issuer/destination |
| Unsolicited/Replay login | Correlation/replay thiếu | InResponseTo, assertion ID cache |
| Signature fail sau decrypt | Verification order sai | Use library default pipeline |
| XML DTD bị chặn và IdP lỗi | IdP gửi XML không đúng policy | Fix IdP, không bật XXE |
| Tenant khác nhận same user | Multi-IdP registration mix-up | Match issuer/key/tenant scope |
| Certificate rollover gây login fail | Metadata chưa approved | Update trusted keys theo change control |
| Role admin xuất hiện bất thường | Raw attrs/mapper sai | Only validated attrs and allowlist |
| One node accept, one node reject | Time, certs hoặc cache không đồng bộ | Sync deployments |
| RelayState redirect tới URL ngoài | Open redirect | Return URL allowlist |
| Người dùng đã disabled nhưng còn vào được | Local account/session policy | Revoke sessions/roles |
| Spring login fail sau tự viết validator | Default validations bị thay | Compare with OpenSAML defaults |

## 24. Giám sát, bảo vệ dữ liệu và incident response

Metrics/logs nên dùng:
- `saml_signature_validation_failed`.
- `saml_signature_untrusted_key`.
- `saml_reference_target_mismatch`.
- `saml_duplicate_id_rejected`.
- `saml_assertion_shape_rejected`.
- `saml_issuer_mismatch`.
- `saml_invalid_audience`.
- `saml_recipient_mismatch`.
- `saml_in_response_to_mismatch`.
- `saml_replay_rejected`.
- `saml_role_mapping_rejected`.

Có thể lưu correlation ID, RP registration ID, issuer category, latency, failure reason và hashed principal theo privacy policy. **Không log raw SAMLResponse, Base64 tokens, SignatureValue, PII attributes, private signing keys hay session cookies.**

Nếu nghi vấn XSW:
1. Khoanh vùng custom XML parser, SAML converter hoặc validator vừa thay đổi.
2. Xác định exact Spring Security/OpenSAML/Santuario versions và advisories.
3. Kiểm đối chiếu principal đã đăng nhập với subjects trong trusted signed assertions theo incident process.
4. Thu hồi suspicious sessions, audit elevated permissions.
5. Khôi phục strict signature/protocol validation và trusted keys.
6. Viết regression tests cho signed/consumed mismatch.
7. Bảo đảm replay cache và metadata/tenant policies hoạt động.
8. Ghi báo cáo/security review và theo dõi events liên quan.

## 25. Checklist secure code review

- [ ] SAML parsing dùng OpenSAML/framework hoặc parser được review kỹ.
- [ ] Namespace-aware và secure XML parsing; DTD/XXE disabled.
- [ ] Request/XML size/depth limits phù hợp.
- [ ] Schema/shape validation từ local trusted SAML schemas khi áp dụng.
- [ ] Không global DOM/XPath để lấy security NameID từ raw XML.
- [ ] Reference URI gắn đúng unique expected Response/Assertion ID.
- [ ] Reject duplicate IDs và ambiguous dereferencing.
- [ ] Transforms/digest/signature algorithms trong allowlist.
- [ ] Không external Reference URI/filesystem/HTTP dereferencing.
- [ ] Trusted signing keys thuộc đúng RelyingPartyRegistration.
- [ ] Không tin certificate do KeyInfo tự khai.
- [ ] Consumed assertion là signed assertion hoặc thuộc verified signed Response subtree.
- [ ] Không trộn Attributes/NameID của khác assertions.
- [ ] Validate Issuer, Destination, Status, Audience, Recipient và Conditions.
- [ ] SubjectConfirmationData và InResponseTo đúng profile.
- [ ] Có replay detection và clock skew phù hợp.
- [ ] Encrypted assertions xử lý đúng thứ tự verify/decrypt.
- [ ] Không bỏ validators mặc định khi customize Spring Security.
- [ ] Multi-IdP/tenant không trộn issuer/cert/registration.
- [ ] Identity linking và role mapping dùng trusted validated data.
- [ ] Account disabled và tenant/resource authorization được thực thi.
- [ ] Không log SAML XML/tokens/PII/private keys.
- [ ] Có test cases XSW/duplicate ID/unsigned claims/reference mismatch.
- [ ] Có checks metadata signing certificate rotation.
- [ ] Mọi authentication failure không tạo authenticated session.
- [ ] Dependency versions và security advisories được cập nhật.

## 26. Câu hỏi tự kiểm tra

1. **XSW là gì?** Chữ ký verify node A nhưng app sử dụng node B.
2. **Tại sao chữ ký hợp lệ không đủ?** Có thể key không trusted, signed target khác consumed object hoặc SAML conditions sai.
3. **Reference URI làm gì?** Xác định XML object mà chữ ký bảo vệ.
4. **Duplicate ID nguy hiểm thế nào?** Resolver và app có thể chọn hai objects khác nhau.
5. **KeyInfo tự là trust anchor?** Không.
6. **Response ký có thể bảo vệ Assertion không ký riêng?** Có nếu Assertion thuộc covered verified subtree và protocol pass.
7. **Assertion ký có yêu cầu Response luôn ký?** Không phải mọi profile, cần đúng SP/IdP contract.
8. **Có được lấy first Assertion trước verify?** Không.
9. **Có được đọc NameID bằng getElementsByTagName trên raw XML?** Không cho security decisions.
10. **XXE và XSW là một?** Không.
11. **Schema validation đủ chống XSW chưa?** Chưa, còn signed scope, references và key trust.
12. **C14N có tự map đúng principal?** Không.
13. **Multi Assertions phải xử lý thế nào?** Chỉ dùng validated protected assertions theo strict policy hoặc reject.
14. **Encryption có thay signature không?** Không.
15. **Spring provider hiện hành dùng gì?** OpenSAML/Spring SAML2 Login, ví dụ OpenSaml5AuthenticationProvider.
16. **Controller lấy verified identity ở đâu?** Saml2AuthenticatedPrincipal từ Spring SecurityContext.
17. **Vì sao không override validators toàn bộ?** Dễ bỏ Issuer, Audience, Destination, InResponseTo.
18. **Response signed nhưng Audience sai?** Reject.
19. **InResponseTo quan trọng khi nào?** SP-initiated authentication correlation.
20. **IdP-initiated mặc nhiên hợp lệ?** Không, cần unsolicited flow policy riêng.
21. **Replay cache dùng để làm gì?** Ngăn reuse assertions/response theo expiry/profile.
22. **RelayState cần kiểm gì?** State/correlation và redirect URL allowlist.
23. **Một nhóm Admin trong assertion tự tạo ROLE_ADMIN?** Không, cần app authorization mapping.
24. **Demo SignedAssertionBoundaryDemo có verify chữ ký thật?** Không, nó giả lập proof để học invariant.
25. **Demo SamlXmlShapeDemo trả SHAPE_ONLY nghĩa là đã login?** Không.
26. **Lỗi thiết kế nghiêm trọng nhất?** Verify node A rồi đọc identity từ node B.
27. **Nguyên tắc bao quát?** Chỉ tạo Authentication từ assertion được IdP trusted signature bảo vệ và đã qua toàn bộ SAML conditions.

## 27. Nguồn tham khảo chính thức

- OWASP SAML Security Cheat Sheet, XML Signature Wrapping: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- W3C XML Signature Best Practices — Check what is signed: https://www.w3.org/TR/xmldsig-bestpractices/
- W3C XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
- Apache Santuario Secure Validation FAQ: https://cwiki.apache.org/confluence/spaces/SANTUARIO/pages/24193195/faq
- Spring Security SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security SAML 2.0 Relying Party configuration: https://docs.spring.io/spring-security/reference/servlet/saml2/login/relying-party.html
- OASIS SAML 2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles, Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OWASP XML External Entity Prevention: https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

**Tổng kết:** XML Signature Wrapping khai thác **độ lệch giữa node được xác minh và node ứng dụng sử dụng**. Một signature valid chỉ đáng tin khi khóa đúng IdP, Reference URI trỏ đúng unique object, và NameID/Attributes thuộc chính signed Assertion hoặc subtree được trusted signed Response bảo vệ. Spring Security/OpenSAML phải kiểm thêm issuer, audience, recipient, destination, time, InResponseTo, subject confirmation và replay trước khi tạo Authentication. Không tự reparse raw SAMLResponse hoặc chọn assertion bằng XPath toàn cục; luôn dùng validated Saml2AuthenticatedPrincipal và tiếp tục kiểm local account, tenant và quyền nghiệp vụ.
