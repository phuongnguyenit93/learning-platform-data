# Cấu hình ký AuthnRequest và lựa chọn thuật toán chữ ký trong Spring Security SAML 2.0

## 1. Mục tiêu bài học

Khi một ứng dụng Spring Boot đóng vai **Service Provider (SP / Relying Party)** trong SAML 2.0 federation, nó có thể gửi `<samlp:AuthnRequest>` đến **Identity Provider (IdP / Asserting Party)** để bắt đầu đăng nhập. Nhiều IdP yêu cầu SP **ký số AuthnRequest** nhằm xác minh yêu cầu thực sự đến từ SP đã đăng ký và chưa bị thay đổi.

Bài học thuộc nhóm **Tùy chỉnh AuthnRequest** và tập trung vào hai quyết định gắn với nhau:

1. **Khi nào và bằng khóa nào SP phải ký AuthnRequest?**
2. **SP và IdP thỏa thuận thuật toán chữ ký nào, áp dụng chữ ký ở vị trí nào theo binding?**

Sau bài này, người học cần có khả năng phân biệt private key của SP với certificate công khai của IdP, cấu hình signing credential trong Spring Boot, hiểu `WantAuthnRequestsSigned` và `AuthnRequestsSigned`, chọn RSA-SHA256 hoặc thuật toán khác có cơ sở, kiểm tra chữ ký Redirect/POST và xử lý sự cố ký số an toàn.

**Nguyên tắc nền tảng:** chữ ký AuthnRequest **chứng minh bên gửi sở hữu private key của SP** tương ứng với certificate/khóa mà IdP đã tin cậy. Nó **không tự xác thực người dùng**, không tự bảo đảm SAML Response trả về là hợp lệ và không thay thế các bước chống replay, kiểm tra audience, issuer, recipient hay phân quyền nghiệp vụ.

## 2. Luồng đăng nhập và chỗ xuất hiện chữ ký

Trong SP-initiated Single Sign-On:

```text
Người dùng / trình duyệt       SP: ứng dụng Spring          IdP
          |                          |                       |
          | Mở trang bảo vệ          |                       |
          |------------------------->|                       |
          |                          | Tạo AuthnRequest      |
          |                          | chọn registration      |
          |                          | ký bằng private key SP |
          |                          |---------------------->|
          |                          |  Redirect hoặc POST   |
          |                          |                       | kiểm tra ký số
          |                          |                       | IdP xác thực user
          |        SAMLResponse/Assertion từ IdP              |
          |<--------------------------------------------------|
          | POST tới ACS              |                       |
          |------------------------->|                       |
          |                          | xác minh Response/     |
          |                          | Assertion, tạo phiên   |
          |<-------------------------|                       |
```

Trong HTTP-Redirect binding, trình duyệt được chuyển hướng đến IdP với các query parameter như `SAMLRequest`, `RelayState`, `SigAlg`, `Signature`. Trong HTTP-POST binding thông thường, AuthnRequest nằm trong form field `SAMLRequest` và chữ ký có thể nằm **bên trong XML** dưới dạng `<ds:Signature>`.

Việc chọn Redirect hay POST quyết định **cách tạo và kiểm tra chữ ký**. Cùng là “ký AuthnRequest”, nhưng hai cách này **không có cùng signed bytes** và không thể lấy một cách rồi dùng nguyên cho cách kia.

### 2.1. Chữ ký giúp giảm rủi ro nào?

Một AuthnRequest có thể chứa:

- `ID`: mã yêu cầu để gắn với SAML Response.
- `Issuer`: **SP Entity ID**.
- `Destination`: URL SSO của IdP.
- `AssertionConsumerServiceURL`: địa chỉ mà SP muốn nhận Response.
- `ProtocolBinding`, `NameIDPolicy`, `RequestedAuthnContext`, `ForceAuthn` và các tùy chọn khác tùy tích hợp.
- `IssueInstant`: thời điểm phát yêu cầu.

Nếu IdP chấp nhận request không được xác thực, attacker có thể thử thay các trường liên quan địa chỉ nhận response, SP identity hoặc chính sách. Chữ ký có thể bảo vệ nội dung đã ký trước sự sửa đổi. **IdP vẫn phải kiểm tra request đúng SP được đăng ký, ACS nằm trong allowlist, thời gian và các chính sách riêng**; ký số không biến một ACS bất kỳ thành địa chỉ an toàn.

Nếu các tham số được gửi qua trình duyệt, cần đặc biệt bảo vệ `RelayState` và tránh biến nó thành open redirect sau khi đăng nhập. Với Redirect binding, `RelayState` nằm trong dữ liệu được ký nếu có. Khi nhận response, SP còn cần **liên hệ request/response với phiên khởi tạo**, không chỉ dựa trên một RelayState do trình duyệt khai.

## 3. Ba loại khóa/certificate dễ nhầm lẫn

| Loại credential | Ai giữ private key? | Ai dùng public key/certificate? | Mục đích |
| --- | --- | --- | --- |
| **SP signing credential** | SP hoặc dịch vụ ký/HSM được SP ủy quyền | **IdP** | SP ký `AuthnRequest` và một số thông điệp khác theo cấu hình |
| **IdP verification credential** | IdP | **SP** | SP xác minh chữ ký `SAMLResponse`/`Assertion` |
| **Metadata signing credential** | Nhà phát hành metadata / federation operator | Đối tác nhận metadata | Xác minh toàn vẹn/xuất xứ của **tài liệu metadata** |

Tất cả có thể chứa X.509 certificate, nhưng mục đích và chủ sở hữu private key khác nhau:

- Khi **SP ký AuthnRequest**, SP cần **private key SP** và certificate tương ứng. **IdP phải biết và tin public certificate SP** từ SP metadata hoặc cấu hình onboarding đã được phê duyệt.
- Khi **SP xác minh Response**, SP dùng **public certificate IdP**, không dùng private key SP để “kiểm tra chữ ký IdP”.
- Khi nhập **metadata có chữ ký**, trust signer metadata phải được thiết lập bằng quy trình riêng; không coi certificate mới xuất hiện trong metadata chưa xác minh là đủ để tạo trust.

Một certificate có thể được dùng cho nhiều mục đích trong một số hệ thống, nhưng đó phải là lựa chọn rõ ràng. Về vận hành, tách khóa **signing** và **decryption** của SP thường giảm phạm vi rủi ro và cho phép xoay khóa độc lập khi đối tác hỗ trợ.

**Không bao giờ chuyển private key của SP cho IdP.** IdP chỉ cần certificate/public key và thông tin định danh SP. Không lưu private key SP trong git, Wiki, tài liệu chia sẻ, log hoặc ví dụ cấu hình công khai.

## 4. Ai yêu cầu AuthnRequest được ký?

Có hai thuộc tính metadata liên quan:

1. Phía **IdP** có thể công bố `WantAuthnRequestsSigned="true"` trên `<md:IDPSSODescriptor>`: IdP muốn/đòi SP gửi AuthnRequest có chữ ký theo quan hệ tin cậy.
2. Phía **SP** có thể công bố `AuthnRequestsSigned="true"` trên `<md:SPSSODescriptor>`: SP tuyên bố các AuthnRequest của mình được ký.

Ví dụ metadata **rút gọn**:

```xml
<!-- IdP metadata fragment -->
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
    WantAuthnRequestsSigned="true">
    <!-- SSO endpoints và các phần tử khác -->
</md:IDPSSODescriptor>
```

```xml
<!-- SP metadata fragment -->
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
    AuthnRequestsSigned="true">
    <!-- KeyDescriptor, ACS, ... -->
</md:SPSSODescriptor>
```

Các đoạn này minh họa **vị trí thuộc tính**, không phải XML metadata đầy đủ. Khi kiểm tra tích hợp thật, hãy lấy SP/IdP metadata thực tế, đúng entityID và certificate.

### 4.1. Hai cờ không phải chính chữ ký

`WantAuthnRequestsSigned` và `AuthnRequestsSigned` chỉ là **chính sách/tuyên bố**. Không có private key hợp lệ hoặc không thực hiện ký theo đúng binding thì request vẫn không có chữ ký hợp lệ, dù metadata có cờ `true`.

Trong Spring Security hiện đại, việc quyết định ký còn liên quan tới:

- **`RelyingPartyRegistration.isAuthnRequestsSigned()`**: SP chủ động chọn ký (API tùy phiên bản).
- **`AssertingPartyMetadata.getWantAuthnRequestsSigned()`**: chính sách/preference của IdP.
- **`RelyingPartyRegistration.signingX509Credentials`**: khóa và certificate mà SP có thể dùng để ký.

Ở các phiên bản có cả hai cờ, Spring Security có thể ký khi **SP yêu cầu ký hoặc IdP yêu cầu ký**. Vì thế đặt `WantAuthnRequestsSigned=false` **không nên được hiểu là lệnh cấm mọi chữ ký**: nếu SP tự đặt chính sách ký thì nó vẫn có thể ký. Khi IdP yêu cầu signed request, phải có signing credentials hợp lệ và xác minh chúng phù hợp.

Tài liệu Spring Security mô tả **mặc định hướng ký AuthnRequest với HTTP-Redirect và RSA-SHA256**, đồng thời cho phép khai rằng IdP không yêu cầu ký. Hành vi thực tế phụ thuộc phiên bản, registration metadata và bộ signing credentials đã cấu hình; nên **kiểm tra request phát ra**, thay vì chỉ đoán từ cờ YAML.

### 4.2. Khi nào có thể dùng request không ký?

Một số IdP không yêu cầu signed AuthnRequest và cấu hình federation cho phép request không ký. Khi đó SP có thể cấu hình tương ứng; nhưng cần:

- Xác nhận đây là quyết định **IdP/chính sách liên kết đã duyệt**, không phải cách “chữa lỗi tạm” vì thiếu khóa.
- IdP vẫn phải giới hạn SP Entity ID, ACS allowlist và profile SSO.
- SP vẫn phải xác minh chữ ký, issuer, audience, subject confirmation, thời gian và các điều kiện khác của **Response/Assertion**.
- Có test chống login CSRF, replay và chấp nhận response unsolicited ngoài chính sách.

Nếu đối tác yêu cầu signed AuthnRequest, **không tắt yêu cầu ký chỉ để đăng nhập chạy được**. Hãy sửa signing key, binding, certificate, thuật toán hoặc metadata đang lệch.

## 5. HTTP-Redirect binding: ký trên query string

Đây là cách SP-initiated SSO phổ biến. Spring Security mặc định sử dụng hướng Redirect trong nhiều cấu hình SAML.

Với HTTP-Redirect DEFLATE encoding, quy trình khái niệm:

1. Tạo AuthnRequest XML đúng cấu trúc, có `Issuer=SP Entity ID` và `Destination=IdP SSO URL`.
2. **Không** giữ chữ ký XML `<ds:Signature>` trên chính SAML protocol message trước khi áp dụng DEFLATE encoding (SAML bindings yêu cầu loại bỏ chữ ký cấp message trong bước encoding này).
3. Nén XML theo **raw DEFLATE**, Base64, rồi URL-encode thành query parameter `SAMLRequest`.
4. Nếu có `RelayState`, URL-encode nó thành parameter riêng.
5. URL-encode URI thuật toán chữ ký thành `SigAlg`.
6. Tạo **chuỗi bytes chính xác** theo thứ tự quy định và ký bằng private key SP.
7. Base64 chữ ký, URL-encode thành parameter `Signature`; chuyển hướng trình duyệt đến IdP SSO endpoint.

**Chuỗi dùng làm đầu vào ký** có dạng:

```text
SAMLRequest=<URL-encoded-value>&RelayState=<URL-encoded-value>&SigAlg=<URL-encoded-value>
```

Nếu **không có RelayState**, bỏ **toàn bộ** phần `&RelayState=...`:

```text
SAMLRequest=<URL-encoded-value>&SigAlg=<URL-encoded-value>
```

Với AuthnRequest, tên field là `SAMLRequest`; không đảo với `SAMLResponse`. Các trường khác trong query string **không tự nằm trong input ký**. Param `Signature` được thêm **sau**, không nằm trong input ký ban đầu.

Ví dụ cấu trúc Redirect URL:

```text
https://idp.example.test/saml/sso
  ?SAMLRequest=<deflated-base64-url-encoded>
  &RelayState=<opaque-state-url-encoded>
  &SigAlg=http%3A%2F%2Fwww.w3.org%2F2001%2F04%2Fxmldsig-more%23rsa-sha256
  &Signature=<base64-signature-url-encoded>
```

Các giá trị trong dấu `<...>` là **mô tả cấu trúc**, không phải URL request có thể gửi. Trong URL thực tế các tham số nằm trên **một dòng**.

### 5.1. Ba chi tiết rất dễ làm sai

**(1) Signed bytes sử dụng giá trị URL-encoded ban đầu.** IdP phải xác minh trên **các giá trị được URL-encode y nguyên như nhận**, theo thứ tự ký quy định. Giải mã rồi URL-encode lại bằng thư viện khác có thể tạo bytes khác dù nội dung logic giống nhau. Ví dụ `+` và `%20` đều có thể được diễn giải là khoảng trắng trong những trường hợp nhất định nhưng không đồng nghĩa về bytes chữ ký.

**(2) Thứ tự kiểm tra chữ ký không phải thứ tự xuất hiện của query trên URL.** OASIS quy định thứ tự xây input: `SAMLRequest`, `RelayState` nếu có, `SigAlg`. Trên URL, thứ tự tham số có thể khác; verifier phải dựng dữ liệu ký theo đúng quy tắc và **giữ nguyên encoded value** đã nhận.

**(3) Đừng tự ký nội dung XML rồi nhét `<ds:Signature>` vào Redirect** như với POST. HTTP-Redirect DEFLATE binding ký phần query-encoded `SAMLRequest/RelayState/SigAlg`; vị trí chữ ký là tham số **`Signature` trên URL**.

Với `RelayState`, SAML HTTP-Redirect binding truyền thống giới hạn kích thước và yêu cầu giữ nguyên giá trị khi IdP trả lại. Nên dùng **mã trạng thái ngắn, opaque**, được lưu/mapping phía server; không đưa URL tùy ý chưa xác thực vào RelayState rồi redirect trực tiếp sau đăng nhập.

## 6. HTTP-POST binding: XML Digital Signature nằm trong request XML

Một số IdP yêu cầu AuthnRequest được gửi bằng **HTTP-POST**. Trong SAML HTTP-POST binding thông thường:

1. SP tạo AuthnRequest XML.
2. SP có thể dùng **XML Digital Signature (XMLDSig)** để ký phần tử AuthnRequest.
3. XML đã ký được Base64 và đưa vào form field `SAMLRequest`.
4. Trình duyệt POST form đến IdP SSO endpoint.
5. IdP giải mã XML và kiểm tra `<ds:Signature>` bằng certificate SP đã đăng ký, theo chính sách binding.

Minh họa cấu trúc AuthnRequest ký theo XMLDSig:

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_req_001"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:00Z"
    Destination="https://idp.example.test/saml/sso">
    <saml:Issuer>urn:example:portal:sp</saml:Issuer>
    <ds:Signature>
      <!-- SignedInfo, Reference, SignatureValue, KeyInfo theo XMLDSig -->
    </ds:Signature>
</samlp:AuthnRequest>
```

Ví dụ là **XML minh họa**, không phải một chữ ký hợp lệ: các phần tử thực tế của XMLDSig, digest, canonicalization và chữ ký được thư viện chuyên dụng xây dựng. Không copy thẳng để gửi đến IdP.

Các điểm cần kiểm tra:

- `Reference` trỏ đúng `ID` AuthnRequest cần bảo vệ; không chấp nhận một signature trên phần tử khác (XML Signature Wrapping).
- Dùng thuật toán `SignatureMethod`, `DigestMethod`, `CanonicalizationMethod` được phép, các transform phù hợp (thường có enveloped signature transform).
- IdP xác minh bằng certificate **của SP đã đăng ký**, không “tin luôn” certificate xuất hiện trong `KeyInfo` mà request tự gửi.
- HTTP-POST thông thường **không dùng** query `SigAlg` và `Signature` của Redirect binding. Các profile/extension như POST-SimpleSign là trường hợp riêng cần thỏa thuận và hỗ trợ cụ thể, không mặc định giống SAML HTTP-POST + XMLDSig.

**Nếu IdP báo “request unsigned” dù XML có `<ds:Signature>`**, hãy kiểm tra trước tiên **binding mà IdP đã đăng ký và mong đợi**. Một chữ ký đúng cho POST không thỏa mãn yêu cầu Redirect query-signature, và ngược lại.

## 7. Thuật toán: phân biệt tên Java và Algorithm URI của SAML/XMLDSig

Trong Java Cryptography Architecture (JCA), thuật toán được gọi bằng tên như `SHA256withRSA`. Trong SAML/XML Signature, thuật toán thường được chỉ ra bằng một **URI**.

Ví dụ:

| Lựa chọn | Tên JCA phổ biến | URI XML Signature (SigAlg / SignatureMethod) | Lưu ý |
| --- | --- | --- | --- |
| RSA-SHA256 | `SHA256withRSA` | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha256` | Lựa chọn mặc định thường gặp trong Spring Security |
| RSA-SHA384 | `SHA384withRSA` | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha384` | Dùng khi IdP/hệ mật mã hỗ trợ |
| RSA-SHA512 | `SHA512withRSA` | `http://www.w3.org/2001/04/xmldsig-more#rsa-sha512` | Dùng khi hai bên thỏa thuận; không “tự an toàn hơn” nếu triển khai sai |
| ECDSA-SHA256 | `SHA256withECDSA` | `http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256` | Chỉ chọn nếu IdP, khóa EC và OpenSAML/provider thực sự tương thích |
| RSA-SHA1 | `SHA1withRSA` | `http://www.w3.org/2000/09/xmldsig#rsa-sha1` | Thuật toán cũ, nên tránh cho tích hợp mới |
| RSA-MD5 | `MD5withRSA` | URI tương ứng | Không dùng cho chữ ký SAML hiện đại |

**Không đưa trực tiếp chuỗi `SHA256withRSA` vào `SigAlg` nếu giao thức đòi URI.** Ngược lại, khi chạy `Signature.getInstance(...)` của JCA, dùng tên thuật toán được provider hỗ trợ, không đưa URI XMLDSig vào API này.

### 7.1. Vì sao không tự chọn RSA-SHA512 cho mọi đối tác?

Độ mạnh tổng thể còn phụ thuộc:

- Thuật toán và kích thước khóa (ví dụ RSA 2048+; nhiều tổ chức chọn RSA 3072 cho vòng đời dài tùy chính sách).
- Provider Java/OpenSAML thực tế có hỗ trợ thuật toán và dạng chữ ký đó không.
- IdP có chấp nhận **Algorithm URI chính xác** không.
- IdP có certificate/public key đúng kiểu RSA hoặc EC không.
- Signing/digest policy có còn thuật toán yếu bị bật không.
- Dữ liệu được ký có đúng theo binding/canonicalization không.

Nếu IdP chỉ công nhận RSA-SHA256, việc ép RSA-SHA512 có thể khiến request bị từ chối dù chữ ký mật mã đúng. Nếu IdP quảng bá danh sách `SigningMethod` trong metadata, cần chọn từ **giao điểm** của danh sách đã tin, chính sách cục bộ và khả năng ký thật sự.

**Khuyến nghị:** dùng **RSA-SHA256** làm baseline khi được hai bên hỗ trợ và chính sách cho phép. Dùng RSA-SHA384/512, ECDSA hoặc thuật toán khác khi đã kiểm tra metadata, IdP docs, key type và kết quả interoperability test. Không fallback âm thầm xuống RSA-SHA1/DSA-SHA1/MD5 vì đối tác cấu hình sai; giải quyết bằng migration/hợp đồng kỹ thuật được duyệt.

### 7.2. SignatureMethod và DigestMethod không phải một

Với **XMLDSig trong POST**, `SignatureMethod` mô tả thuật toán ký `SignedInfo`, ví dụ RSA-SHA256; `DigestMethod` mô tả thuật toán hash của từng tham chiếu, ví dụ SHA-256. Chúng là hai trường riêng cần đặt theo profile/chính sách.

Với **Redirect query signature**, `SigAlg` xác định thuật toán ký lên chuỗi query bytes; không có cấu trúc `SignedInfo/Reference/DigestMethod` trong query ký của binding này. Không nên áp dụng hướng dẫn XMLDSig canonicalization của POST để “sửa” signature bytes của Redirect.

### 7.3. Phối hợp thuật toán với metadata IdP

IdP có thể quảng bá `md:Extensions` chứa phần mở rộng `SigningMethod` với URI thuật toán được ưu tiên. Spring Security có thể đọc/chọn thuật toán dựa trên IdP metadata thông qua `RelyingPartyRegistrations`, hoặc cho phép cấu hình thủ công `AssertingPartyMetadata.signingAlgorithms`.

Danh sách này cần dựa trên **metadata tin cậy**. Không chấp nhận người dùng/HTTP request tự khai thuật toán; không cấp quyền cho token hay query string tự bật lại SHA-1. Nếu metadata thay đổi thuật toán, phải có kiểm tra tương thích và khả năng rollback theo chính sách.

## 8. Cấu hình Spring Boot: private key/certificate để ký

Ví dụ cho **Spring Boot 3.x / Spring Security 6.x** (các property có thể thay đổi theo phiên bản; kiểm tra configuration metadata của bản đang dùng). Spring Boot làm SP và IdP đã được đăng ký chính xác.

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:portal:prod:sp"
            signing:
              credentials:
                - private-key-location: "file:/etc/secrets/saml/sp-signing-key.pem"
                  certificate-location: "file:/etc/secrets/saml/sp-signing-cert.pem"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "classpath:corp-idp-metadata.xml"
              singlesignon:
                sign-request: true
```

**Giải thích:**

- `corp` là `registrationId` của Spring Security; không phải SP Entity ID.
- `entity-id` là **SP Entity ID**, IdP phải công nhận chính xác giá trị đó và certificate SP tương ứng.
- `signing.credentials` nạp **private key SP** và certificate X.509 khớp cặp khóa để SP ký AuthnRequest; đây là hai file riêng do vận hành cấp. **Đường dẫn trong ví dụ chỉ là cấu trúc minh họa**, file/cert cần được cung cấp hợp lệ.
- `assertingparty.metadata-uri` là nguồn IdP metadata. IdP entityID, SSO endpoint, certificate xác minh Response và các tín hiệu thuật toán xuất phát từ metadata được tin cậy; tải được XML không tự chứng minh metadata đã được kiểm tra chữ ký.
- `assertingparty.singlesignon.sign-request: true` biểu thị IdP muốn nhận signed AuthnRequest theo cấu hình Spring Boot. SP phải có signing credential để đáp ứng.
- `acs.location` là điểm nhận **SAML Response**, khác với IdP SSO endpoint nhận **AuthnRequest**. `{baseUrl}` và `{registrationId}` được mở rộng trong ngữ cảnh triển khai; cần xem URL được xuất ở SP metadata thực tế.

Đây là **mẫu cấu hình để tích hợp**, không thể đăng nhập một mình nếu thiếu IdP thật, file key/certificate, trust policy và ứng dụng Spring Boot đã build.

### 8.1. Chọn chỗ lưu khóa

Private key SP cần được bảo vệ tương ứng với vai trò chứng thực SP:

1. Tạo cặp khóa đúng thuật toán/kích thước theo chính sách bảo mật và năng lực IdP.
2. Gắn certificate công khai tương ứng; kiểm tra private/public key khớp trước khi deploy.
3. Lưu private key trong secret manager, key store, volume bảo mật hoặc HSM tùy thiết kế; chỉ cấp quyền đọc cho process cần ký.
4. Không đóng private key sản xuất trong `src/main/resources`, container image công khai hoặc source control.
5. Đưa **public certificate SP** đến IdP qua kênh quản trị/metadata đã xác minh; không gửi private key.
6. Thiết kế việc cập nhật certificate, overlap và thu hồi sau sự cố từ đầu.

Nếu dùng HSM/remote signer mà private key không thể xuất thành file, cần tích hợp credential/provider tương thích để Spring Security/OpenSAML ký theo API được hỗ trợ. **Không giả định property `private-key-location` có thể gọi trực tiếp mọi HSM**.

### 8.2. Định dạng khóa và lỗi thường gặp

- Certificate thường ở PEM `-----BEGIN CERTIFICATE-----`, định dạng X.509.
- Private key PEM thường cần dạng **PKCS#8** `-----BEGIN PRIVATE KEY-----` với provider/converter thích hợp; một `RSA PRIVATE KEY` kiểu PKCS#1 hoặc khóa đã mã hóa có thể cần chuyển đổi/cơ chế đọc khác.
- Khóa và certificate phải là **cùng cặp**. Nếu không, quá trình ký/xác minh sẽ thất bại.
- Không nhầm `assertingparty.verification.credentials` (public certificate **IdP** để SP kiểm tra response) với `registration.corp.signing.credentials` (private key và cert **SP** để ký request).
- Không dùng certificate đã hết hạn hoặc bị thu hồi theo chính sách của IdP. Certificate tự ký cũng có thể được các IdP chấp nhận trong mô hình pin certificate theo quan hệ federation, nhưng phải được đăng ký/trust rõ ràng.

## 9. Java Spring Security: chọn thuật toán theo AssertingPartyMetadata

Mặc định Spring Security ký bằng **RSA-SHA256** trong cấu hình hỗ trợ và có signing credential. Nếu IdP yêu cầu **RSA-SHA512**, Spring Security có API `AssertingPartyMetadata.signingAlgorithms` để điều chỉnh danh sách thuật toán ưu tiên.

Đoạn Java sau **thuộc về một ứng dụng Spring đã có dependency** `spring-security-saml2-service-provider`, registration và các nguồn khóa an toàn. Nó là trích đoạn xây repository, không phải chương trình chạy riêng bằng `javac`:

```java
import org.opensaml.xmlsec.signature.support.SignatureConstants;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

import java.security.PrivateKey;
import java.security.cert.X509Certificate;

// Đặt trong một method @Bean của lớp @Configuration.
// privateKey và certificate là cặp SP signing đã tải an toàn.
Saml2X509Credential spSigner =
    Saml2X509Credential.signing(privateKey, certificate);

RelyingPartyRegistration rp = RelyingPartyRegistrations
    .fromMetadataLocation("classpath:corp-idp-metadata.xml")
    .registrationId("corp")
    .entityId("urn:example:portal:prod:sp")
    .signingX509Credentials(credentials -> credentials.add(spSigner))
    .assertingPartyMetadata(party -> party
        .wantAuthnRequestsSigned(true)
        .signingAlgorithms(algorithms -> {
            algorithms.clear();
            algorithms.add(
                SignatureConstants.ALGO_ID_SIGNATURE_RSA_SHA512);
        })
    )
    .build();

RelyingPartyRegistrationRepository repository =
    new InMemoryRelyingPartyRegistrationRepository(rp);
```

**Cách hiểu chính xác:**

- `Saml2X509Credential.signing(privateKey, certificate)` đặt khóa **SP** vào mục đích signing.
- `signingX509Credentials` là phía **RP/SP**, không phải certificate của IdP.
- `wantAuthnRequestsSigned(true)` đặt preference/yêu cầu của **IdP** trong registration; nó không sinh private key.
- `signingAlgorithms` mô tả thuật toán phù hợp với IdP; trong ví dụ `clear()` rồi thêm RSA-SHA512 để **ưu tiên duy nhất** thuật toán đã thỏa thuận. Chỉ nên làm vậy khi IdP thực sự hỗ trợ, private key là RSA phù hợp, provider hỗ trợ và test ký thành công. Nếu metadata IdP đã chứa danh sách thuật toán đúng, **ưu tiên dùng danh sách đã kiểm chứng** để tránh hard-code không cần thiết.
- `SignatureConstants.ALGO_ID_SIGNATURE_RSA_SHA512` là một **Algorithm URI** do OpenSAML cung cấp, không phải `"SHA512withRSA"` của JCA.
- Đoạn `fromMetadataLocation(...)` là cách nạp metadata nhưng **không tự bảo đảm metadata có chữ ký đáng tin**; riêng bài toán metadata verification phải cấu hình trust chain/metadata repository phù hợp.

Khi dùng Spring Boot auto-configuration YAML, thường không cần tạo repository bằng tay chỉ để nạp signing credentials. Chọn **một nguồn cấu hình có thể kiểm soát được** để tránh có hai repository khác nhau làm lệch registration thực sự được filter sử dụng.

### 9.1. Tùy chỉnh AuthnRequest khác với tùy chỉnh thuật toán

Spring Security có `OpenSaml5AuthenticationRequestResolver` và `setAuthnRequestCustomizer` để sửa các trường như `ForceAuthn`, `NameIDPolicy` hoặc `RequestedAuthnContext`. Ví dụ:

```java
RelyingPartyRegistrationResolver registrationResolver =
    new DefaultRelyingPartyRegistrationResolver(registrations);
OpenSaml5AuthenticationRequestResolver resolver =
    new OpenSaml5AuthenticationRequestResolver(registrationResolver);

resolver.setAuthnRequestCustomizer(context ->
    context.getAuthnRequest().setForceAuthn(true));
```

Đây là **trích đoạn cấu hình** với biến `registrations` và imports Spring Security tương ứng, không phải một file Java độc lập. Việc thay `ForceAuthn` là sửa **nội dung yêu cầu xác thực**; việc chọn signing credential/algorithm/binding nằm trong registration và xử lý SAML của framework. Hãy để Spring Security/OpenSAML **ký sau khi toàn bộ dữ liệu cần ký đã được xác định**. Không ký trước rồi thay Issuer/ACS/ForceAuthn, vì chữ ký có thể mất hiệu lực.

Nếu dùng Spring Security khác phiên bản có `OpenSaml5AuthenticationRequestResolver`, đối chiếu Javadoc và API tương ứng. Không copy code của Spring Security SAML Extension cũ vào SAML2 Service Provider hiện đại mà chưa chuyển đổi.

## 10. SecurityFilterChain cho trang web dùng SAML 2.0

Ví dụ tối thiểu về trách nhiệm của Spring Security Servlet:

Tệp `src/main/java/com/example/portal/SecurityConfig.java`:

```java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
```

`saml2Login()` cho Spring Security tạo/nhận SAML Web SSO; `saml2Metadata()` công bố metadata SP nếu ứng dụng muốn đăng ký với IdP qua metadata. Class này cần dự án Spring Boot, dependency SAML2 và registration thực tế; **không phải code standalone**.

Với `registrationId=corp`, endpoint tạo request phổ biến là:

```text
GET /saml2/authenticate/corp
```

IdP thường nhận AuthnRequest ở `SingleSignOnService` đã cấu hình. URL xác thực gửi đi, binding và chữ ký phụ thuộc registration thực sự của `corp`; không suy `SigAlg` chỉ từ đường dẫn này.

### 10.1. Xem SP metadata trước khi kiểm thử

Nếu đã bật `saml2Metadata()`, các endpoint thường dùng gồm:

```text
/saml2/metadata
/saml2/metadata/{registrationId}
/saml2/service-provider-metadata/{registrationId}
```

Kiểm tra SP metadata xuất ra để xác nhận:

- `EntityDescriptor/@entityID` đúng **SP Entity ID**.
- `SPSSODescriptor/@AuthnRequestsSigned` phù hợp chính sách đã chọn.
- `KeyDescriptor use="signing"` (nếu được phát hành) chứa **public certificate SP** mà IdP phải tin.
- `AssertionConsumerService/@Location` đúng HTTPS public URL, không phải `localhost` hay hostname nội bộ từ reverse proxy.
- Nếu IdP đã nhập metadata trước đó, certificate và entityId phía IdP phải được cập nhật khi thay đổi.

**Không gửi private key trong metadata.** Certificate công khai/chain và URL là dữ liệu dùng để hai bên cấu hình trust; khi phân phối metadata cũng cần xác minh nguồn tin cậy của tài liệu.

## 11. Ví dụ Java 17 chạy độc lập: tạo và kiểm tra chữ ký Redirect

Để học rõ **bytes được ký** trong HTTP-Redirect binding, ví dụ sau:

- Tạo AuthnRequest XML minh họa.
- Nén raw DEFLATE, Base64 và URL-encode thành `SAMLRequest`.
- Ghép `SAMLRequest`, `RelayState`, `SigAlg` theo thứ tự ký chuẩn.
- Dùng `SHA256withRSA` của Java 17 ký chuỗi bytes đó.
- Xác minh bằng public key đúng, sau đó thử sửa RelayState, sửa SAMLRequest hoặc dùng public key khác.

Đây là **chương trình giáo dục độc lập**, đã được thiết kế để biên dịch bằng JDK 17+. Nó **không** tạo AuthnRequest có chữ ký cho IdP production: cặp khóa được tạo ngẫu nhiên trong lúc chạy, chưa có X.509 certificate được đăng ký với IdP; XML dùng giá trị ví dụ; chưa quản lý request correlation/session, metadata, thời hạn và phản hồi. Trong ứng dụng thật, **dùng Spring Security/OpenSAML**, không copy bộ ký giản lược để thay SAML library.

Tệp `SamlRedirectSigningDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Base64;
import java.util.zip.Deflater;

public class SamlRedirectSigningDemo {
    private static final String SIG_ALG =
        "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256";

    static String encodedRequest(String xml) {
        byte[] input = xml.getBytes(StandardCharsets.UTF_8);
        Deflater deflater = new Deflater(Deflater.DEFAULT_COMPRESSION, true);
        deflater.setInput(input);
        deflater.finish();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[1024];
        while (!deflater.finished()) {
            int n = deflater.deflate(buffer);
            output.write(buffer, 0, n);
        }
        deflater.end();
        return URLEncoder.encode(
            Base64.getEncoder().encodeToString(output.toByteArray()),
            StandardCharsets.UTF_8
        );
    }

    static String toSign(String encodedRequest, String relayState) {
        return "SAMLRequest=" + encodedRequest
            + "&RelayState=" + URLEncoder.encode(
                relayState, StandardCharsets.UTF_8)
            + "&SigAlg=" + URLEncoder.encode(
                SIG_ALG, StandardCharsets.UTF_8);
    }

    static String sign(String query, PrivateKey key) throws Exception {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(query.getBytes(StandardCharsets.UTF_8));
        return Base64.getEncoder().encodeToString(signer.sign());
    }

    static boolean verify(String query, String signature, PublicKey key)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(query.getBytes(StandardCharsets.UTF_8));
        return verifier.verify(Base64.getDecoder().decode(signature));
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair sp = generator.generateKeyPair();
        KeyPair another = generator.generateKeyPair();
        String xml = "<samlp:AuthnRequest "
            + "xmlns:samlp='urn:oasis:names:tc:SAML:2.0:protocol' "
            + "xmlns:saml='urn:oasis:names:tc:SAML:2.0:assertion' "
            + "ID='_req1' Version='2.0' "
            + "IssueInstant='2026-01-01T10:00:00Z' "
            + "Destination='https://idp.example.test/sso'>"
            + "<saml:Issuer>urn:example:portal:sp</saml:Issuer>"
            + "</samlp:AuthnRequest>";
        String signedInput = toSign(encodedRequest(xml), "state-42");
        String signature = sign(signedInput, sp.getPrivate());
        System.out.println("signedCorrectly="
            + verify(signedInput, signature, sp.getPublic()));
        System.out.println("modifiedRelayState="
            + verify(signedInput.replace("RelayState=state-42",
                "RelayState=other"), signature, sp.getPublic()));
        System.out.println("modifiedSamlRequest="
            + verify(signedInput.replace("SAMLRequest=",
                "SAMLRequest=X"), signature, sp.getPublic()));
        System.out.println("untrustedPublicKey="
            + verify(signedInput, signature, another.getPublic()));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 SamlRedirectSigningDemo.java
java SamlRedirectSigningDemo
```

**Stdout chính xác** (nội dung chữ ký và cặp khóa được tạo ngẫu nhiên nhưng các kết quả Boolean giữ như sau):

```text
signedCorrectly=true
modifiedRelayState=false
modifiedSamlRequest=false
untrustedPublicKey=false
```

**Giải thích kết quả:**

- `signedCorrectly=true`: public key tương ứng với private key SP xác minh được cùng các bytes đã ký.
- `modifiedRelayState=false`: đổi RelayState làm thay đổi input chữ ký.
- `modifiedSamlRequest=false`: đổi dữ liệu SAMLRequest đã URL-encode làm thay đổi input chữ ký.
- `untrustedPublicKey=false`: một public key khác không xác minh được chữ ký của SP.

`URLEncoder` tạo chuỗi URL-encoded từ giá trị đang có; trong ví dụ tất cả giá trị cần ký được tạo và dùng nhất quán. Bộ tích hợp production phải tuân thủ chính xác quy tắc encoding, kiểm tra input gốc từ HTTP, các giới hạn của SAML binding và policy thuật toán. Với chữ ký thật, sau khi tạo `signature` có thể thêm query parameter `&Signature=` cộng **Base64 signature đã URL-encode** vào URL Redirect; chương trình này **không thực hiện HTTP redirect**.

Việc dùng hai cặp RSA trong demo là để chứng minh khóa xác minh phải đúng. Trong thực tế, IdP không “tự chọn” một public key tình cờ từ AuthnRequest mà phải tìm **SP certificate đã được đăng ký và tin cậy** theo đúng SP Entity ID/registration.

## 12. Hướng dẫn kiểm chứng signing trong môi trường tích hợp

Một cấu hình chỉ được xem là xong khi **request thật gửi tới IdP** qua đúng binding và IdP xác minh được chữ ký.

### Bước A — Chốt hợp đồng SP–IdP

Thu thập/ghi lại:

1. SP Entity ID và IdP Entity ID chính xác.
2. IdP SSO URL và HTTP binding (Redirect hay POST) được cho phép.
3. IdP có yêu cầu signed AuthnRequest không; SP có đặt `AuthnRequestsSigned` không.
4. Danh sách thuật toán được IdP chấp nhận, thứ tự ưu tiên và chính sách loại thuật toán yếu.
5. Public certificate SP và fingerprint SHA-256 IdP đã import.
6. ACS URL và SP metadata được IdP đăng ký.
7. Phương án rotation certificate, điều kiện từ chối unsigned request và môi trường dev/prod riêng.

### Bước B — Đọc cấu hình ứng dụng

Kiểm tra `RelyingPartyRegistration` thực tế (không chỉ nhìn file YAML):

- `registrationId` đã chọn có đúng IdP không?
- `entityId` của SP có khớp bản ghi tại IdP?
- `signingX509Credentials` có signing credential chứa private key hợp lệ?
- `getWantAuthnRequestsSigned()` và chính sách signed của SP phù hợp với đối tác?
- `getSigningAlgorithms()` có thuật toán được hai bên hỗ trợ?
- Binding SSO thực tế là `REDIRECT` hay `POST`?

Nếu dùng nhiều IdP, mỗi registration có thể có yêu cầu ký, certificate và algorithm riêng. Không tự áp một thuật toán/cert cho mọi registration nếu hợp đồng khác nhau.

### Bước C — Gửi AuthnRequest thật

Mở điểm vào đăng nhập `/saml2/authenticate/{registrationId}` trong môi trường thử nghiệm và dùng công cụ kiểm tra network/SAML trong điều kiện bảo mật.

Với **Redirect**:

- Xem URL IdP có `SAMLRequest`, `SigAlg`, `Signature`; `RelayState` có thể có hoặc không.
- Kiểm tra `SigAlg` sau URL-decode là URI thuật toán được thỏa thuận (ví dụ RSA-SHA256).
- IdP xác minh signature bằng **public certificate SP**. Khi tái kiểm tra thủ công, dùng đúng encoded bytes của query; **không** decode rồi encode lại tùy ý.
- Không suy “có Signature param = chữ ký hợp lệ”; phải kiểm tra bằng khóa tin cậy.

Với **POST**:

- Form chứa `SAMLRequest` Base64; giải mã để xem `<ds:Signature>` trên AuthnRequest.
- Kiểm tra signed reference và XMLDSig `SignatureMethod`/digest, certificate SP, schema và điều kiện binding.
- Không yêu cầu tham số `Signature` theo kiểu Redirect nếu đang dùng POST XMLDSig chuẩn.

### Bước D — Xác minh Response độc lập

Khi IdP đã chấp nhận AuthnRequest, SP **vẫn cần** kiểm tra Response/Assertion: chữ ký IdP, issuer, audience, `Recipient`/`Destination`, `InResponseTo` và thời gian. Không cho rằng “request đã ký nên mọi Response trả về đều đáng tin”.

Spring Security thường lưu AuthnRequest chờ đối chiếu với Response; nếu thay cơ chế lưu request hoặc dùng distributed cache, cần giữ tính chất chống login CSRF/replay và liên hệ với phiên người dùng, không chỉ nhìn một `RelayState` dễ đoán.

## 13. Các lỗi thực tế và hướng điều tra

| Triệu chứng | Nguyên nhân điển hình | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| IdP báo “unsigned AuthnRequest” | SP chưa cấu hình signing credential, hoặc binding ký không đúng | Kiểm tra SP key/cert, cờ signed, Redirect `Signature` hay POST `ds:Signature` |
| IdP báo signature invalid | IdP dùng cert SP cũ/sai, private key không khớp cert hoặc query bị đổi bytes | Đối chiếu fingerprint public cert, keypair, signed query raw |
| `SigAlg` là RSA-SHA1 nhưng policy từ chối | Thuật toán cũ còn trong cấu hình | Chọn RSA-SHA256+ được IdP hỗ trợ, loại fallback yếu |
| IdP chỉ hỗ trợ RSA-SHA256 nhưng SP gửi RSA-SHA512 | Danh sách signingAlgorithms ép sai | Khôi phục giao điểm được hỗ trợ; test với IdP |
| Lỗi `InvalidKeyException` / key mismatch | Certificate/kiểu private key không phù hợp thuật toán | Xác minh RSA/EC keypair, định dạng PKCS#8, provider |
| Không đọc được private key | Sai location/quyền file, key PEM không đúng format hoặc encrypted key chưa hỗ trợ | Kiểm tra mount/permission, converter/keystore được hỗ trợ |
| Đã set `sign-request:false` nhưng request vẫn ký | SP tự yêu cầu ký, hoặc policy có cờ signed khác | Kiểm tra cả `AuthnRequestsSigned` và `WantAuthnRequestsSigned`, metadata thực tế |
| Ký xong mới đổi `Destination` hoặc `ForceAuthn` | Dữ liệu ký bị thay sau ký | Thực hiện customization **trước** khi framework ký |
| Redirect URL bị hệ thống trung gian sửa | Proxy/gateway/URL normalizer đổi encoded query | Giữ nguyên query bytes; kiểm tra log an toàn và tuyến chuyển hướng |
| POST đã có XML Signature nhưng IdP chỉ nhận Redirect signature | Mismatch binding | Thống nhất Redirect/POST và cách ký với IdP |
| IdP chấp nhận request nhưng Response tới ACS sai | Sai public base URL/ACS đăng ký | Kiểm tra reverse proxy/forwarded headers và SP metadata |
| Đăng nhập “chỉ lỗi prod” | Cert/algorithm/Entity ID khác môi trường | Tách trust và credentials theo môi trường, kiểm tra actual registration |
| Ký đúng nhưng IdP vẫn từ chối request | Issuer, ACS, NameIDPolicy, AuthnContext hoặc clock skew không hợp lệ | Xem đúng loại lỗi IdP, không tắt chữ ký |
| Xoay certificate SP rồi SSO lỗi | IdP vẫn giữ khóa cũ hoặc chuyển quá sớm | Phối hợp overlap/metadata update, cutover có kế hoạch |
| Không có response hoặc Response không qua validation | Request sign thành công chỉ là bước đầu | Kiểm tra SAML Response signature/issuer/audience/time/subject confirmation |

**Chẩn đoán tách lớp:** “không ký được” là lỗi khóa/config phía SP; “IdP không xác minh được” là lỗi certificate/binding/algorithm/bytes; “SP không nhận response” là lỗi xác minh IdP hoặc ACS/session. Không khắc phục một lớp bằng cách tắt bảo vệ của lớp khác.

## 14. Chiến lược luân chuyển khóa ký AuthnRequest

Việc xoay khóa SP signing phải được phối hợp **trước khi private key mới được đưa vào hoạt động**:

1. Kiểm kê SP Entity ID, các IdP liên quan, certificate hiện tại, hạn dùng và thuật toán.
2. Tạo cặp khóa/certificate mới theo chính sách; kiểm tra tương thích IdP.
3. Cấp **public certificate mới** cho IdP qua kênh onboarding/metadata được xác minh. Nếu IdP hỗ trợ nhiều certificate, đăng ký cả cũ và mới trong khoảng chuyển tiếp.
4. Đảm bảo IdP đã tin certificate mới **trước** khi SP bắt đầu ký bằng private key mới.
5. Thử luồng từng IdP và cả Redirect/POST đang áp dụng; đo lường tỷ lệ lỗi.
6. Chuyển sang key mới có kiểm soát, lưu lịch sử thay đổi/fingerprint phục vụ điều tra.
7. Hết thời gian chuyển tiếp, gỡ certificate cũ khỏi IdP và thu hồi/loại key cũ khỏi nơi lưu.
8. Có phương án khôi phục nếu đối tác không kịp đồng bộ; không mặc định khôi phục bằng việc gửi request unsigned.

**Phân biệt:** certificate ký AuthnRequest của SP và certificate ký SAML Response của IdP có thể xoay độc lập. Không dùng thay đổi certificate IdP làm lý do để xoay private key SP nếu không liên quan.

Nếu private key SP nghi bị lộ, không chỉ “đổi password file key”: phải thay cặp khóa, thu hồi trust của certificate cũ tại IdP, rà soát AuthnRequest có thể đã bị giả và điều tra sự kiện liên quan.

## 15. Kiểm thử chức năng và bảo mật

| Test case | Cấu hình/đầu vào | Kỳ vọng |
| --- | --- | --- |
| Signed Redirect chuẩn | SP ký query bằng RSA-SHA256, IdP có cert SP đúng | IdP xác minh chữ ký và xử lý request theo chính sách |
| Signed POST chuẩn | SP XML ký AuthnRequest, IdP hỗ trợ POST | IdP xác minh XML signature |
| Sai certificate SP | Request ký đúng bằng key khác cert IdP tin | IdP từ chối |
| Sai thuật toán | SP dùng RSA-SHA512, IdP chỉ chấp nhận RSA-SHA256 | IdP từ chối với lỗi rõ |
| Sửa `SAMLRequest` sau ký | Thay encoded request | Signature invalid |
| Sửa `RelayState` sau ký | Thay encoded relay | Redirect signature invalid |
| Sửa `SigAlg` | URI thuật toán không còn khớp signature | Từ chối |
| Thiếu `Signature` | IdP yêu cầu signed AuthnRequest | Từ chối |
| Không có private key | Cờ ký bật, signing credentials thiếu | Fail sớm/có lỗi rõ; không gửi unsigned khi policy cấm |
| Rollover key | Cả cert cũ và mới được IdP tin trong thời gian chuyển tiếp | Chuyển key thành công, hết kỳ thu hồi cert cũ |
| Thay `ForceAuthn` trước khi ký | Customizer chạy trước signing | Signature vẫn hợp lệ |
| Thay XML sau khi ký | `Issuer`, `Destination` hoặc `NameIDPolicy` bị đổi | Signature invalid |
| Re-encode Redirect URL | Percent-encoding biến đổi | Verifier từ chối nếu signed bytes thay |
| IdP khác | Request `registrationId=partner` nhưng ký cert của `corp` | Từ chối theo trust của partner |
| Same SP, nhiều IdP | Từng registration có signing policy riêng | Không rò/nhầm cert, algorithm, endpoint |
| Reverse proxy | `{baseUrl}` giải ra HTTP host nội bộ | Metadata/ACS test thất bại; sửa trusted proxy/public URL |
| Response giả | AuthnRequest đã ký nhưng Response không có chữ ký IdP hợp lệ | SP từ chối |
| Replay response | Response cũ đã dùng lại | SP từ chối theo correlation/replay policy |
| Xử lý lỗi khóa | File private key bị đọc sai quyền | Fail an toàn, không log private key hay tiếp tục unsigned |
| Thuật toán yếu | IdP metadata yêu cầu RSA-SHA1 | Không tự bật thuật toán yếu; cần kế hoạch tương thích/migration |

Ngoài unit test chữ ký, cần **integration test với IdP hoặc bộ SAML test harness** vì nhiều lỗi chỉ xuất hiện qua giao thức HTTP thực: URL encoding, binding, certificate đã import và chính sách ACS. Ghi nhận evidence hữu ích là thuật toán URI, fingerprint certificate, request ID, registrationId, thời gian và loại lỗi; tránh log full SAML assertion hoặc secret.

## 16. Checklist triển khai

- [ ] Biết IdP có thật sự yêu cầu signed AuthnRequest, qua metadata `WantAuthnRequestsSigned` và hợp đồng kỹ thuật.
- [ ] Biết SP có tuyên bố `AuthnRequestsSigned` và có chính sách sign riêng không.
- [ ] Đã cấu hình **SP private key + X.509 certificate** đúng cặp trong `signing.credentials`/`signingX509Credentials`.
- [ ] IdP đã đăng ký **public certificate SP** cho đúng SP Entity ID và môi trường.
- [ ] Không nhầm certificate SP signing với IdP response verification hay metadata signing credentials.
- [ ] Đã xác định **HTTP-Redirect** hay **HTTP-POST**, vị trí chữ ký theo binding tương ứng.
- [ ] Với Redirect, xác nhận `SAMLRequest`, `RelayState` nếu có, `SigAlg`, `Signature` và thứ tự signed bytes.
- [ ] Với POST, xác nhận XMLDSig `SignedInfo`, `Reference`, `SignatureMethod` và `DigestMethod` có kiểm tra đầy đủ.
- [ ] Thuật toán ký có **Algorithm URI chính xác**, tương thích loại khóa, IdP, OpenSAML và policy.
- [ ] RSA-SHA1/DSA-SHA1/MD5 không được bật lại tùy tiện; không có downgrade âm thầm.
- [ ] Key SP được bảo vệ trong secret manager/keystore/HSM phù hợp; không lưu private key trên repository hoặc log.
- [ ] SP metadata, ACS, IdP SSO endpoint, proxy URL và certificate công khai đã được đối chiếu.
- [ ] Nếu dùng `OpenSaml5AuthenticationRequestResolver`, mọi thay đổi AuthnRequest được thực hiện **trước khi ký**.
- [ ] Ký AuthnRequest không làm mất việc **xác minh SAML Response/Assertion** đầy đủ ở phía SP.
- [ ] Có kiểm thử negative cases: sai key, sai SigAlg, sửa query, sai binding, unsigned, sai registration, replay.
- [ ] Có kế hoạch key rollover, test khi IdP lưu cert cũ và phương án ứng cứu khi khóa SP bị lộ.

## 17. Câu hỏi tự kiểm tra

**1. Ai ký AuthnRequest và ai xác minh chữ ký?**

SP ký bằng **private key của SP**; IdP xác minh bằng **public key/certificate SP** đã được cấp và tin cậy trong cấu hình đối tác.

**2. Cấu hình `sign-request:true` tự tạo private key để ký được không?**

Không. Cờ biểu diễn yêu cầu/preference ký; SP vẫn cần signing credential hợp lệ, certificate đã được IdP đăng ký và binding/algorithm phù hợp.

**3. Với HTTP-Redirect, chữ ký nằm trong XML `<ds:Signature>`?**

Không theo SAML HTTP-Redirect DEFLATE binding chuẩn. Chữ ký được tính trên query bytes đã URL-encode, qua `SAMLRequest`, `RelayState` nếu có và `SigAlg`, rồi thêm `Signature` vào URL.

**4. Nếu không có RelayState, có ký `RelayState=` rỗng không?**

Không. Bỏ hẳn parameter RelayState khỏi input ký theo quy tắc của binding.

**5. Vì sao Java `Signature.getInstance("SHA256withRSA")` khác `SigAlg` URI?**

JCA dùng **tên thuật toán của provider Java**; SAML/XMLDSig dùng **URI quy ước giao thức**. Bộ tích hợp phải ánh xạ đúng hai dạng.

**6. Spring Security dùng thuật toán ký nào phổ biến mặc định?**

Tài liệu Spring Security mô tả **RSA-SHA256** khi ký AuthnRequest, và cho phép dùng `signingAlgorithms` để chọn thuật toán phù hợp IdP. Kết quả thực tế cần kiểm tra trên request đã phát.

**7. Có nên nâng tự động lên RSA-SHA512 cho mọi IdP?**

Không. Cần tương thích IdP, loại khóa và provider; không tự gây lỗi interoperability và không cho phép downgrade xuống thuật toán yếu.

**8. Đổi `ForceAuthn` sau khi request đã ký có được không?**

Không nên: thay đổi nội dung đã ký sẽ làm chữ ký mất hiệu lực. Thực hiện customization trước bước signing của framework.

**9. Một AuthnRequest có chữ ký hợp lệ đã đủ để chấp nhận SAML Response chưa?**

Chưa. SP phải xác minh chữ ký IdP, issuer, audience, destination/recipient, request correlation, thời hạn, subject confirmation và chống replay.

**10. Vì sao IdP thấy chữ ký RSA-SHA256 nhưng vẫn từ chối?**

Có thể certificate SP không khớp, ký trên bytes sai, dùng sai binding, request issuer/ACS chưa được đăng ký, hoặc policy IdP không chấp nhận cấu hình hiện tại. Cần phân loại lỗi trước khi chỉnh thuật toán.

## 18. Tài liệu chuẩn để đối chiếu

- Spring Security, **Producing AuthnRequests** — yêu cầu ký, `wantAuthnRequestsSigned`, `signingAlgorithms`, Redirect/POST và customizer: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security, **SAML 2.0 Login Overview** — credentials và `RelyingPartyRegistration`: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Boot 3.5, **SAML 2.0 Relying Party Properties** — `signing.credentials[*].private-key-location`, `certificate-location`: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Security Javadoc, **Saml2X509Credential** — `signing(privateKey, certificate)`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html
- Spring Security Javadoc, **AssertingPartyMetadata** — `getWantAuthnRequestsSigned`, `getSigningAlgorithms`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/registration/AssertingPartyMetadata.html
- OASIS, **Bindings for SAML V2.0**, mục HTTP-Redirect/HTTP-POST: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OASIS, **SAML V2.0 Metadata**, các cờ `AuthnRequestsSigned` / `WantAuthnRequestsSigned`: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OWASP, **SAML Security Cheat Sheet** — validation, trust và XML Signature Wrapping: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Ghi nhớ:** để ký AuthnRequest an toàn, phải phối hợp đúng **chính sách yêu cầu ký của IdP/SP + private key/certificate SP + thuật toán được hỗ trợ + SAML HTTP binding**. HTTP-Redirect ký **URL-encoded query**, HTTP-POST chuẩn ký **XML**. Trong Spring Security, cấu hình signing credentials và signing algorithms phải dựa trên hợp đồng federation; chữ ký của yêu cầu không bao giờ thay thế xác minh đầy đủ Response/Assertion và phân quyền phía ứng dụng.