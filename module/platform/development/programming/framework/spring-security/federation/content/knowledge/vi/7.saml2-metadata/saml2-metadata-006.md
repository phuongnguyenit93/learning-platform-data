# Chứng thư ký, chứng thư mã hóa và thông tin KeyDescriptor trong SAML 2.0

> **Bối cảnh:** Spring Security – federation / Metadata SAML2. Bài học tập trung vào cách `<md:KeyDescriptor>` công bố khóa dùng cho ký và mã hóa; cách phân biệt public certificate với private key; cách SP và IdP trao đổi metadata, triển khai Spring Security, kiểm tra chữ ký/giải mã, xoay khóa và xử lý sự cố. Các ví dụ dùng Java 17+ và Spring Boot 3.5.x/Spring Security 6.x trên Servlet stack.

## 1. Mục tiêu và kiến thức đầu vào

Sau khi học xong, bạn có thể:

1. Đọc `KeyDescriptor` trong `IDPSSODescriptor` và `SPSSODescriptor`, hiểu chính xác `use="signing"`, `use="encryption"` và trường hợp thiếu `use`.
2. Chỉ ra cấu trúc `ds:KeyInfo`, `ds:X509Data/ds:X509Certificate`, `ds:KeyValue` và `md:EncryptionMethod`, biết metadata chỉ công bố **thông tin khóa công khai**, không gửi private key.
3. Giải thích bốn hướng sử dụng: IdP **ký** → SP **kiểm chứng**; SP **ký** → IdP **kiểm chứng**; IdP **mã hóa cho SP** → SP **giải mã**; SP **mã hóa cho IdP** → IdP **giải mã** khi giao thức/tích hợp yêu cầu.
4. Phân biệt **chứng thư SAML**, **chứng thư HTTPS/TLS**, **chữ ký trên metadata** và **chữ ký trên SAML Response/Assertion/AuthnRequest**.
5. Thiết lập trust anchor đúng cách bằng metadata/registration đã phê duyệt, hiểu giới hạn của việc kiểm tra CA, hạn chứng thư và fingerprint.
6. Cấu hình `signing`, `decryption`, `assertingparty.verification` trong Spring Boot hoặc `Saml2X509Credential` trong Spring Security đúng vai trò.
7. Lập quy trình xoay signing/decryption certificate với thời gian overlap, cache/metadata refresh và kiểm thử âm, không gây lỗi đăng nhập hàng loạt.
8. Chẩn đoán sai chứng thư, sai mục đích khóa, mismatch entity ID/ACS, signature/decryption failure và lỗi do proxy.

**Nên biết trước:** SAML Web Browser SSO, `EntityDescriptor`, SP entity ID, IdP entity ID, `SingleSignOnService`, ACS, XML namespace, chữ ký số khóa công khai, Java/Spring Security cơ bản. Nếu chưa phân biệt khóa công khai và khóa riêng, hãy làm rõ điểm đó trước: **bên phát hành chữ ký giữ khóa riêng; bên nhận dùng khóa công khai đáng tin để xác minh**.

## 2. Metadata thiết lập bối cảnh, KeyDescriptor công bố khóa

SAML metadata là XML mô tả các **SAML entity** và vai trò của chúng. Một entity có thể là IdP, SP hoặc đồng thời nhiều vai trò. Trong metadata, `<md:EntityDescriptor entityID="...">` nhận diện entity, `<md:IDPSSODescriptor>` mô tả vai trò IdP, và `<md:SPSSODescriptor>` mô tả vai trò SP.

`<md:KeyDescriptor>` là phần tử mô tả khóa của **entity/role sở hữu metadata** và mục đích sử dụng khóa đó. Nó thường nằm dưới role descriptor, bên cạnh endpoint SSO/ACS, thông tin logout, NameIDFormat và các thuộc tính khác. Một IdP có thể công bố nhiều signing keys; một SP cũng có thể công bố riêng signing key và encryption key.

~~~text
EntityDescriptor (entityID = https://idp.example.org/metadata)
  └─ IDPSSODescriptor
       ├─ KeyDescriptor use="signing"
       │    └─ ds:KeyInfo → public signing key/certificate của IdP
       ├─ KeyDescriptor use="encryption" (khi cần)
       │    └─ ds:KeyInfo → public encryption key/certificate của IdP
       ├─ SingleSignOnService
       └─ SingleLogoutService (nếu có)

EntityDescriptor (entityID = https://portal.example.org/sp)
  └─ SPSSODescriptor
       ├─ KeyDescriptor use="signing" (khi SP ký request/logout)
       │    └─ ds:KeyInfo → public signing key/certificate của SP
       ├─ KeyDescriptor use="encryption" (khi SP nhận dữ liệu mã hóa)
       │    └─ ds:KeyInfo → public encryption key/certificate của SP
       └─ AssertionConsumerService (ACS)
~~~

**Điểm mấu chốt:** Nếu thấy **IdP metadata + signing certificate**, đó thường là public key mà **SP** cần để xác minh thông điệp ký bởi IdP. Nếu thấy **SP metadata + encryption certificate**, đó thường là public key mà **IdP** dùng để mã hóa Assertion/NameID/Attribute gửi cho SP. Bên cung cấp certificate không gửi private key của mình cho bên kia.

Metadata có thể được phân phối qua URL HTTPS hoặc tệp XML, nhưng **chỉ có metadata chưa đủ để tin**: SP phải biết nguồn đó thuộc IdP được phê duyệt, entity ID nào được chấp nhận và metadata được xác thực/phân phối theo chính sách nào. Một certificate tự được chèn vào tài liệu XML chưa tin không tự cấp quyền ký SAML thay cho IdP.

## 3. Cấu trúc chuẩn của `KeyDescriptorType`

Mô hình phần tử theo SAML 2.0 Metadata:

~~~text
md:KeyDescriptor
  @use = "signing" | "encryption" | [không khai báo]
  ds:KeyInfo                         (bắt buộc theo schema)
    ds:KeyValue hoặc ds:X509Data/ds:X509Certificate ...
  md:EncryptionMethod                (tùy chọn, 0 hoặc nhiều)
~~~

| Thành phần | Vai trò | Cảnh báo |
| --- | --- | --- |
| `md:KeyDescriptor` | Mô tả khóa ứng với role SP/IdP trong metadata | Không chứa private key |
| `use="signing"` | Khóa được dùng cho xác minh chữ ký hoặc xác thực đối tác theo role/profile | Không đồng nghĩa khóa dùng được để giải mã |
| `use="encryption"` | Khóa công khai có thể dùng để mã hóa dữ liệu gửi tới entity này | Không đồng nghĩa bên gửi có private key |
| Không có `use` | Theo đặc tả, khóa có thể áp dụng cho **cả signing và encryption** | Vẫn phải phù hợp chính sách/khả năng giao thức và thuật toán |
| `ds:KeyInfo` | Container biểu diễn khóa công khai/định danh khóa theo XML Signature | Có thể chứa nhiều loại thông tin; không phải “dấu tin cậy” độc lập |
| `ds:X509Data/ds:X509Certificate` | Chứa chứng thư X.509 đã mã hóa Base64 từ DER | Nội dung là **chứng thư công khai**, không có PEM headers |
| `ds:KeyValue` | Biểu diễn trực tiếp public key bằng XML | Không phải mọi thư viện/tích hợp đều hỗ trợ các kiểu khóa giống nhau |
| `ds:KeyName` | Gợi ý tên/nhãn để nhận diện khóa | Không có đủ key material nếu chỉ có tên; không được tự tin vì tên giống |
| `md:EncryptionMethod` | Mô tả thuật toán mã hóa có thể hỗ trợ, khi metadata khai báo | Phải kiểm tra tương thích thực tế và chính sách mật mã |

`KeyDescriptor` có thể xuất hiện **nhiều lần** dưới cùng `RoleDescriptor` để phục vụ rollover hoặc các cách dùng khác nhau. Không phải mọi message SAML đều ký bằng một khóa cố định, và không phải mọi Assertion đều được mã hóa. Điều cần biết là **những khóa nào được phép sử dụng** cho **đối tác nào** và **mục đích nào** trong thời điểm message được xử lý.

### 3.1. XML mẫu về mục đích `use`

Đây là trích đoạn XML minh họa **hình thức khai báo KeyDescriptor và KeyName**; riêng `KeyName` không chứa public key nên **không đủ để tích hợp hoặc xác minh chữ ký**. Metadata production cần `KeyInfo` có public key/certificate thực, được đưa vào từ nguồn đáng tin.

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://idp.example.org/metadata">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:KeyName>idp-signing-2026</ds:KeyName>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:KeyDescriptor use="encryption">
      <ds:KeyInfo>
        <ds:KeyName>idp-encryption-2026</ds:KeyName>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Cấu trúc production thường gặp** thay cho hoặc cùng `ds:KeyName` là:

~~~text
md:KeyDescriptor use="signing"
  ds:KeyInfo
    ds:X509Data
      ds:X509Certificate
        [Base64 của DER-encoded X.509 certificate do IdP công bố]
~~~

Dấu ngoặc vuông ở trên chỉ để mô tả vị trí **dữ liệu chứng thư thực** trong cây XML, không phải chuỗi hợp lệ để đưa vào metadata. Certificate thường được lưu riêng dưới dạng PEM:

~~~text
-----BEGIN CERTIFICATE-----
... dữ liệu Base64 của DER ...
-----END CERTIFICATE-----
~~~

Trong `ds:X509Certificate`, nội dung là Base64 của DER; **không đưa dòng** `-----BEGIN CERTIFICATE-----` / `-----END CERTIFICATE-----` vào trong phần tử XML. Nếu copy certificate sang cấu hình/secret file PEM, định dạng PEM thường có headers.

### 3.2. Bảng quyết định khi `use` không có hoặc metadata có nhiều keys

| Metadata của một role | Cách diễn giải theo đặc tả | Cách vận hành an toàn |
| --- | --- | --- |
| Một `KeyDescriptor use="signing"` | Public key cho mục đích ký/xác minh chữ ký | Chỉ dùng theo policy xác minh của role đó |
| Một `KeyDescriptor use="encryption"` | Public key cho mã hóa gửi tới role đó | Không dùng làm signing key chỉ vì key là RSA |
| Một `KeyDescriptor` không có `use` | Khóa có thể áp dụng cho cả signing và encryption | Vẫn tôn trọng allowed algorithms/profile và chính sách tổ chức |
| Hai `KeyDescriptor use="signing"` | Hai public keys có thể hợp lệ, thường gặp lúc đổi khóa | Hỗ trợ overlap; không chọn “cert đầu tiên” một cách cứng nhắc |
| Hai encryption certs | Hai public keys có thể được công bố để chuyển giao | Thống nhất với bên gửi key nào dùng để mã hóa và giữ private key nhận còn hiệu lực |
| Metadata công bố signing key mới mà app chỉ tin key cũ | Chữ ký mới có thể bị từ chối | Đồng bộ metadata/registration trước khi IdP chuyển signer |
| Certificate có `KeyName` khác tên trong SAML Response | Tên chỉ là hint, không thay trust decision | Xác minh bằng public keys đáng tin và đúng issuer |

**Giới hạn:** Không suy ra việc ứng dụng **bắt buộc** dùng cả ký và mã hóa chỉ vì `use` bị lược bỏ. Metadata cho phép mô tả khả năng; profile SSO, hợp đồng liên kết, crypto policy và implementation vẫn quyết định điều gì sẽ diễn ra.

## 4. Bốn đường đi của khóa: ký/xác minh và mã hóa/giải mã

| Hành động | Ai giữ **private key**? | Ai nhận **public key/certificate** từ metadata? | Ví dụ thông điệp |
| --- | --- | --- | --- |
| IdP ký kết quả đăng nhập | **IdP** | **SP** dùng signing cert IdP để verify | `SAML Response` hoặc `Assertion` |
| SP ký request/logout | **SP** | **IdP** dùng signing cert SP để verify | `AuthnRequest`, `LogoutRequest` / `LogoutResponse` nếu yêu cầu |
| IdP mã hóa dữ liệu cho SP | **SP** giữ decryption private key | **IdP** dùng encryption cert SP | `EncryptedAssertion`, `EncryptedID`, `EncryptedAttribute` |
| SP mã hóa dữ liệu cho IdP | **IdP** giữ decryption private key | **SP** dùng encryption cert IdP | Message/element gửi đến IdP nếu profile/hệ thống hỗ trợ |

### 4.1. Luồng IdP ký, SP kiểm chứng

~~~text
IdP                                               SP
   signing PRIVATE key
          |
          +-- ký Response hoặc Assertion ------------>
                                  |
                       SP lấy verifying PUBLIC key
                       trong IdP metadata đã tin
                                  |
                       kiểm chứng XML Signature
                       + Issuer/entity ID
                       + Destination/Recipient
                       + AudienceRestriction
                       + thời gian / correlation
                       + replay protections
                                  |
                       mới tạo Authentication
~~~

Không tự bỏ bước xác minh vì HTTPS đã mã hóa đường truyền. Browser là thành phần mang message, có thể bị chỉnh sửa. Việc chữ ký RSA/ECDSA khớp với **một** public key chưa đủ: public key phải thuộc đúng **IdP entity ID/registration** mà SP được phép tin.

Chữ ký có thể nằm trên `Response`, `Assertion` hoặc cả hai tùy profile/IdP. Validation phải kiểm tra đúng phần tử được ký và mối quan hệ với dữ liệu được sử dụng sau đó, tránh XML Signature Wrapping. Hãy để Spring Security/OpenSAML xác minh thay vì tự dùng XPath và một lệnh kiểm tra chữ ký tách rời.

### 4.2. Luồng SP ký, IdP kiểm chứng

~~~text
SP                                              IdP
   signing PRIVATE key
          |
          +-- ký AuthnRequest/Logout message ------->
                                   |
                       IdP lấy verifying PUBLIC key
                       trong SP metadata đã đăng ký
                                   |
                       IdP kiểm tra chữ ký, issuer,
                       SP entity ID, ACS, policy
~~~

Tùy binding, cách ký có thể khác: **HTTP-Redirect** thường mang chữ ký trong query parameters (`SigAlg`, `Signature`), trong khi **HTTP-POST** có thể mang XML Digital Signature. Cả hai đều liên hệ với signaling signing credential của SP, nhưng cách canonicalize/message signing phải do thư viện giao thức chuẩn thực hiện.

Trong metadata, `IDPSSODescriptor/@WantAuthnRequestsSigned` thể hiện IdP muốn AuthnRequest ký; `SPSSODescriptor/@AuthnRequestsSigned` thể hiện SP phát AuthnRequest ký. Quy tắc này phải tương ứng với thực tế. Không tự thêm signing cert SP rồi nghĩ mọi request mặc định ký đúng theo mọi phiên bản và mọi IdP: cần kiểm tra request network/IdP logs.

### 4.3. Luồng IdP mã hóa cho SP

~~~text
IdP                                                SP
        public ENCRYPTION cert của SP
          |
          +-- mã hóa dữ liệu với khóa đối xứng ------>
          |   và bảo vệ khóa đối xứng theo
          |   public key/transport agreement
          |
                                     SP dùng
                                     DECRYPTION private key
                                     tương ứng để giải mã
                                     |
                                     rồi kiểm tra đủ
                                     policy SAML
~~~

Trong SAML/XML Encryption, IdP có thể mã hóa toàn Assertion, NameID hoặc Attribute; cấu trúc thường là `EncryptedAssertion`, `EncryptedID`, `EncryptedAttribute` và XML Encryption elements như `EncryptedData`/`EncryptedKey`. Bên nhận cần **khóa riêng** tương ứng với public certificate mà bên gửi đã dùng, cùng thuật toán XML Encryption được hỗ trợ.

**Mã hóa không phải chữ ký:** Kẻ khác có public encryption key cũng có thể mã hóa dữ liệu gửi cho SP; chỉ giải mã thành công không chứng minh message do IdP đã tin phát hành. Vẫn phải kiểm chứng chữ ký và mọi điều kiện SAML trước khi cho đăng nhập. Nếu message vừa ký vừa mã hóa, thứ tự giải mã/xác minh có thể phụ thuộc thứ tự bảo vệ các XML elements; để thư viện chuẩn xử lý đúng context.

### 4.4. Khi IdP công bố encryption certificate

Một `KeyDescriptor use="encryption"` trong **IdP metadata** diễn đạt khóa công khai để bên khác mã hóa thông điệp **gửi đến IdP** khi profile hỗ trợ. Nó **không phải** khóa mà SP dùng để giải mã Assertion nhận được. Nếu SP phải giải mã một encrypted assertion thì decryption private key phải nằm **ở SP** và public certificate tương ứng nằm trong **SP metadata/registration** mà IdP sử dụng.

## 5. Phân biệt certificate SAML và certificate HTTPS/TLS

Cùng là X.509 certificate nhưng ngữ nghĩa vận hành khác nhau.

| Khía cạnh | SAML signing/encryption certificate | HTTPS/TLS server certificate |
| --- | --- | --- |
| Công dụng | Cung cấp public key để verify XML Signature hoặc encrypt dữ liệu | Xác thực máy chủ TLS và bảo vệ HTTP transport |
| Nơi tham chiếu | `md:KeyDescriptor/ds:KeyInfo` hoặc registration | TLS endpoint/reverse proxy, Web PKI/trust store |
| Tiêu chí tin cậy | Metadata/partner relationship đã được phê duyệt và profile/cấu hình | Xác minh tên miền, chuỗi CA/trust anchor, thời gian và TLS policy |
| Chứng thư tự ký | Có thể được dùng làm public key container trong SAML metadata nếu đã được tin đúng cách | Thường không được browser tin trừ khi cài trust root riêng |
| Bí mật cần bảo vệ | Private key bên ký hoặc bên giải mã | TLS private key của server |
| Khi xoay | Cần cập nhật metadata, verifying/decryption credentials và overlap | Cần cập nhật TLS endpoint/CA chain và client trust |

Trong nhiều SAML deployment, certificate X.509 trong metadata chỉ là **vật chứa public key** và trust đến từ **metadata đã được xác thực**. Không thể suy diễn rằng Spring Security sẽ tự áp dụng CA chain, OCSP, CRL hoặc thời hạn `NotAfter` giống trình duyệt HTTPS. Các triển khai và profile liên thông có thể dùng chính sách certificate khác nhau, nên phải xác định rõ policy thực tế.

**Không nên rút gọn thành “chứng thư hết hạn thì mọi chữ ký SAML luôn không hợp lệ”:** Trong profile SAML metadata interop, việc chấp nhận public key trong metadata có thể độc lập với thời hạn PKI truyền thống; song vận hành an toàn vẫn cần giám sát certificate dates, policy nội bộ và lịch rotation. Việc thư viện có tự kiểm tra hạn certificate hay không phải được thử nghiệm/đọc cấu hình cụ thể. Khi chứng thư bị lộ private key, cần thu hồi trust nhanh theo incident policy, không đợi ngày `NotAfter`.

### Fingerprint dùng để đối chiếu, không tự tạo trust

Một fingerprint SHA-256 của DER certificate hữu ích khi xác minh rằng tệp cert nhận được trùng với tệp đối tác đã gửi qua **kênh quản trị độc lập đã xác thực**. Fingerprint không chứng minh ownership nếu người gửi metadata và fingerprint là cùng nguồn chưa được xác thực. Đặc biệt, một XML tự chứa cert và một email chứa fingerprint cùng do kẻ tấn công gửi không tạo quan hệ tin cậy.

## 6. Chữ ký metadata khác chữ ký message

Một tài liệu `EntityDescriptor` / `EntitiesDescriptor` có thể được **ký ở cấp metadata**. Chữ ký này giúp xác thực tính toàn vẹn và nguồn phân phối metadata khi consumer có **metadata-signing trust anchor** được cung cấp độc lập. Nó khác với:

- **IdP signing certificate** trong `KeyDescriptor` dùng verify `Assertion`/`Response`.
- **SP signing certificate** trong `KeyDescriptor` dùng IdP verify `AuthnRequest`/logout.
- **TLS certificate** của URL phân phối metadata.
- **Encryption certificate** dùng bảo vệ tính bí mật của một message gửi đến bên nhận.

Khi nhận metadata:

1. Xác định chính xác **nguồn** (URL do đối tác đã đăng ký, tệp được phê duyệt, signed metadata feed) và **entityID** mong muốn.
2. Nếu policy yêu cầu metadata signature, verify bằng trust anchor dành cho **metadata signing**, không tin ngay certificate có trong XML tải về.
3. Kiểm tra metadata `validUntil` / `cacheDuration` theo chính sách nguồn, endpoint SSO/ACS, entityID, scope partner và bộ public keys; quản lý thay đổi với phê duyệt.
4. Chỉ sau khi đã chấp thuận metadata mới đưa signing cert vào trust config của SP hoặc public encryption cert vào hệ thống gửi.
5. Không tự động tải mọi metadata URI hoặc cert URL do một `SAMLResponse` hay request web đề xuất; tránh SSRF và tự động mở rộng danh sách IdP được tin.

Một metadata có chữ ký hợp lệ từ federation operator vẫn cần kiểm tra **đối tác cụ thể có được ứng dụng chấp thuận không**. Trust vào người ký tài liệu không mặc định đồng nghĩa mọi entity trong tài liệu đều được phép xác thực mọi tenant.

## 7. Bắt đầu bằng hồ sơ đối tác rõ ràng

Trước khi chỉnh Spring Security, thống nhất các thông số:

| Thuộc tính | IdP cung cấp/định nghĩa | SP cung cấp/định nghĩa |
| --- | --- | --- |
| Entity ID | IdP entity ID trong IdP metadata | SP entity ID trong SP metadata |
| Endpoint | `SingleSignOnService`, có thể `SingleLogoutService` | `AssertionConsumerService` (ACS), có thể `SingleLogoutService` |
| Signing cert | Public certificate/key trong **IdP metadata** | Public certificate/key trong **SP metadata** nếu SP ký request |
| Encryption cert | IdP public encryption cert nếu nhận ciphertext | SP public encryption cert nếu IdP mã hóa cho SP |
| Private keys | IdP giữ signing/decryption private keys của chính mình | SP giữ signing/decryption private keys của chính mình |
| Policy chữ ký | IdP yêu cầu AuthnRequest ký? thuật toán/binding? | SP yêu cầu Response/Assertion ký? thuật toán? |
| Policy mã hóa | IdP có mã hóa Assertion/Attribute/NameID? | SP có private key, thuật toán và quy trình rotation tương thích? |
| Vận hành | URL/chu kỳ metadata update, thời gian đổi khóa | Reload config, session/cache, log bảo mật và rollback |

**Ví dụ hợp đồng kỹ thuật hợp lý:** IdP A công bố hai signing certificates để chuẩn bị rollover; SP “portal” dùng cả hai public keys để verify IdP signatures, đồng thời công bố một encryption certificate cho IdP A. IdP mã hóa Assertion bằng public key của SP; SP giải mã bằng private key tương ứng. Nếu SP không ký AuthnRequest theo policy, signing certificate của SP không phải là điều kiện tiên quyết cho việc đọc Assertion từ IdP. Các chính sách thực tế phải đối chiếu profile và IdP cụ thể.

## 8. Spring Security: Credential có mục đích khác nhau

Spring Security định nghĩa `Saml2X509Credential` biểu diễn X.509 certificate và tùy mục đích có private key; một `RelyingPartyRegistration` liên kết cấu hình SP với một asserting party/IdP. Các credential quan trọng:

| API/khái niệm | Bên sở hữu | Thực hiện gì |
| --- | --- | --- |
| `Saml2X509Credential.verification(X509Certificate)` | Public signing cert **IdP** trong cấu hình asserting party | SP xác minh chữ ký message từ IdP |
| `Saml2X509Credential.signing(privateKey, certificate)` | Khóa riêng + certificate **SP** | SP ký request/logout khi cấu hình yêu cầu |
| `Saml2X509Credential.decryption(privateKey, certificate)` | Khóa riêng + certificate **SP** | SP giải mã encrypted Assertion/NameID/Attribute gửi cho SP |
| `Saml2X509Credential.encryption(certificate)` | Public encryption cert **đối tác nhận** | Dùng mã hóa dữ liệu gửi cho bên nhận trong flow có hỗ trợ |
| `RelyingPartyRegistration` | Một cặp IdP/SP có `registrationId` | Gắn entity IDs, SSO/ACS, binding, verifying/signing/decryption credentials |

**Không tự tráo role:** `assertingparty.verification` phải chứa verifying cert của **IdP**; `registration.signing`/`registration.decryption` chứa private key và certificate của **SP**. Đưa private key IdP vào SP là sai mô hình bảo mật. Đưa public encryption cert của SP vào trường verification IdP cũng không hợp lý.

### 8.1. Ví dụ Spring Boot 3.5.x cấu hình từ metadata

Ví dụ này là một **SP Servlet** có một đối tác `corporate`, dùng Spring Security để thực hiện SAML login. Giá trị URL và đường dẫn secret là hình minh họa; chỉ đăng nhập được khi metadata IdP có thật, khóa/cert hợp lệ, SP entity ID/ACS đã được IdP đăng ký và tương thích thuật toán. Private key để ở file được quản trị bởi secret manager, không commit vào Git.

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>saml-keys</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots><enabled>false</enabled></snapshots>
    </repository>
  </repositories>
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
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**`src/main/resources/application.yml`:**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/sp-signing.key
                  certificate-location: file:/run/secrets/sp-signing.crt
            decryption:
              credentials:
                - private-key-location: file:/run/secrets/sp-decryption.key
                  certificate-location: file:/run/secrets/sp-decryption.crt
~~~

**Giải thích cấu hình:**

- `metadata-uri` đọc metadata của **IdP đã phê duyệt**. Khi metadata chứa đúng signing `KeyDescriptor`, Spring có thông tin verification keys IdP phù hợp. Không lấy URL từ request người dùng.
- `signing.credentials` là khóa riêng của SP và public cert tương ứng, dùng khi SP cần ký AuthnRequest/logout. Tài liệu cấu hình này **không đưa signing cert của IdP vào đây**.
- `decryption.credentials` là private key SP và certificate tương ứng, dùng khi IdP mã hóa nội dung gửi đến SP. Public certificate của SP cần được **công bố trong SP metadata/registration** để IdP chọn đúng encryption key.
- Tệp `file:/run/secrets/...` được container/service cấp bởi secret manager; để chạy trên Windows hoặc môi trường khác phải đổi thành đường dẫn Resource hợp lệ, phân quyền file và bảo vệ backup. Nếu thiếu/mismatch private key và cert, ứng dụng có thể không khởi động hoặc decrypt fail.
- Nếu IdP **không yêu cầu** SP ký request hoặc **không mã hóa** Assertion, không bắt buộc cấu hình đủ cả hai nhóm credentials. Ví dụ đưa đủ để minh họa rõ từng mục đích; chỉ bật theo hợp đồng thực tế.
- Cấu hình SAML còn phải đáp ứng SP `entity-id` và ACS, default của thư viện hoặc override phù hợp. Đừng đoán URL production khi ứng dụng chạy sau reverse proxy.

**`src/main/java/demo/SamlKeysApplication.java`:**

~~~java
package demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SamlKeysApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlKeysApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoEndpoints {
        @GetMapping("/")
        String home() {
            return "SAML 2.0 signing and encryption demo";
        }

        @GetMapping("/me")
        Map<String, String> me(
                @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
            return Map.of(
                    "registrationId", principal.getRelyingPartyRegistrationId(),
                    "authenticated", "true");
        }
    }
}
~~~

Trong thư mục dự án, chạy `mvn spring-boot:run`. Nếu đã có IdP metadata hợp lệ, cert/key và registration đúng, mở `http://localhost:8080/` trả chính xác chuỗi **SAML 2.0 signing and encryption demo**. Mở `/me` bắt đầu SAML login và, sau khi hoàn thành, trả JSON với `registrationId` phụ thuộc cấu hình (ở đây thường là `corporate`) và `authenticated=true`. Đường khởi tạo thủ công mặc định thường là `/saml2/authenticate/corporate`.

Ứng dụng demo này **không thực hiện mã hóa hoặc ký message theo code Java thủ công**: Spring Security/OpenSAML xử lý theo `RelyingPartyRegistration`, profile và metadata. Demo chỉ phản ánh một registration; để thử đầy đủ bốn đường đi khóa cần IdP có thể phát response ký, mã hóa, và kiểm chứng AuthnRequest ký theo cấu hình. Không dùng endpoint `/me` như bằng chứng duy nhất cho việc validation đúng; phải kiểm tra negative tests.

### 8.2. Khi không dùng URL metadata

Nếu tổ chức không cho tải metadata tại runtime, có thể cấu hình IdP entity ID, SSO URL và verification certificate từ tệp đã được phê duyệt. Mẫu dưới đây là **lựa chọn thay thế** cho `assertingparty.metadata-uri`, không phải đoạn cần ghép thêm vào ví dụ trên:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              entity-id: https://idp.example.org/saml
              sso-url: https://idp.example.org/sso
              verification:
                credentials:
                  - certificate-location: file:/run/secrets/idp-signing-2026.crt
~~~

Cấu hình này chỉ nêu **IdP-side verification**. Với các endpoint, logout bindings, SP signing/decryption, entity ID và ACS khác, phải cấu hình đầy đủ tương thích metadata và hợp đồng. Đừng tùy tiện vừa cấu hình metadata-uri từ nguồn khác vừa thêm cert thủ công mà không xác định chính xác bộ verifying keys nào được chọn.

### 8.3. `Saml2X509Credential` và cấu hình Java

Khi cần cấu hình động, những factory methods có ý nghĩa rõ:

~~~java
// Đoạn minh họa API, đặt trong mã cấu hình đã đọc cert/key hợp lệ.
Saml2X509Credential verifyIdp =
        Saml2X509Credential.verification(idpSigningCertificate);
Saml2X509Credential signAsSp =
        Saml2X509Credential.signing(spSigningPrivateKey, spSigningCertificate);
Saml2X509Credential decryptAsSp =
        Saml2X509Credential.decryption(spDecryptionPrivateKey, spDecryptionCertificate);
~~~

Các biến đầu vào được hệ thống secret/certificate loader của ứng dụng cung cấp; **đây là trích đoạn Java, không phải tệp độc lập có thể chạy**. Với API builder của version phù hợp, SP signing credentials thuộc `RelyingPartyRegistration#signingX509Credentials`, SP decryption thuộc `decryptionX509Credentials`, và IdP verification thuộc phần asserting-party metadata/registration. Khi dùng Spring Boot properties ở trên, không cần viết lại conversion này thủ công.

## 9. Java 17: kiểm kê KeyDescriptor và fingerprint X.509 an toàn

Công cụ nhỏ sau đọc **một file metadata có root `EntityDescriptor`**, liệt kê các `KeyDescriptor` của `IDPSSODescriptor` hoặc `SPSSODescriptor` và in mục đích `use`, fingerprint SHA-256, subject và hạn certificate. Nó chỉ dùng Java 17 standard library, không cần Spring.

**Đây là công cụ kiểm kê, KHÔNG phải SAML metadata signature validator và KHÔNG được dùng để quyết định tin cậy**. Nó không thay thế kiểm chứng metadata signature, certificate source, issuer/entityID hay runtime XML Signature. Chương trình từ chối DTD/external entities để giảm rủi ro XXE khi đọc file.

**Tệp `InspectSamlKeys.java`:**

~~~java
import java.io.ByteArrayInputStream;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Base64;
import java.util.HexFormat;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

public class InspectSamlKeys {
    private static final String MD =
            "urn:oasis:names:tc:SAML:2.0:metadata";
    private static final String DS =
            "http://www.w3.org/2000/09/xmldsig#";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java InspectSamlKeys <metadata.xml>");
            System.exit(2);
        }

        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
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

        Document document = factory.newDocumentBuilder()
                .parse(Path.of(args[0]).toFile());
        Element root = document.getDocumentElement();
        if (!MD.equals(root.getNamespaceURI())
                || !"EntityDescriptor".equals(root.getLocalName())) {
            throw new IllegalArgumentException(
                    "Expected a single SAML EntityDescriptor");
        }

        System.out.println("entityID=" + root.getAttribute("entityID"));
        CertificateFactory certFactory =
                CertificateFactory.getInstance("X.509");
        for (String role : new String[] {
                "IDPSSODescriptor", "SPSSODescriptor"
        }) {
            NodeList roles = root.getElementsByTagNameNS(MD, role);
            for (int i = 0; i < roles.getLength(); i++) {
                Element roleElement = (Element) roles.item(i);
                NodeList keys = roleElement.getElementsByTagNameNS(
                        MD, "KeyDescriptor");
                for (int j = 0; j < keys.getLength(); j++) {
                    Element key = (Element) keys.item(j);
                    String use = key.getAttribute("use");
                    if (use.isBlank()) {
                        use = "both (use omitted)";
                    }
                    NodeList certificates = key.getElementsByTagNameNS(
                            DS, "X509Certificate");
                    if (certificates.getLength() == 0) {
                        System.out.println(
                                role + " use=" + use
                                + " certificate=not-present");
                    }
                    for (int k = 0; k < certificates.getLength(); k++) {
                        String base64 = certificates.item(k).getTextContent();
                        byte[] der = Base64.getMimeDecoder().decode(base64);
                        X509Certificate cert = (X509Certificate)
                                certFactory.generateCertificate(
                                    new ByteArrayInputStream(der));
                        byte[] sha256 = MessageDigest.getInstance("SHA-256")
                                .digest(cert.getEncoded());
                        System.out.println(role + " use=" + use);
                        System.out.println(
                                "SHA256=" + HexFormat.of().formatHex(sha256));
                        System.out.println(
                                "subject=" + cert.getSubjectX500Principal());
                        System.out.println(
                                "notAfter=" + cert.getNotAfter());
                    }
                }
            }
        }
    }
}
~~~

Biên dịch/chạy trên Java 17+:

~~~bash
javac InspectSamlKeys.java
java InspectSamlKeys idp-metadata.xml
~~~

**Output phụ thuộc metadata thật**: chương trình in `entityID`, role, `use`, fingerprint SHA256, subject và `notAfter` của mỗi certificate (nếu có). Vì file và certificate không được cung cấp trong bài, không có stdout cố định hợp lệ. Nếu `KeyInfo` chỉ có `KeyValue` hoặc `KeyName`, chương trình sẽ báo `certificate=not-present`; điều đó **không chứng minh metadata vô hiệu**, chỉ phản ánh phạm vi công cụ. Nếu file là `EntitiesDescriptor` tổng hợp, chương trình báo lỗi vì chỉ xử lý single-entity metadata.

**Giới hạn an toàn:** `getElementsByTagNameNS` chỉ giúp truy xuất nội dung XML, không verify chữ ký metadata, không kiểm tra chain CA hoặc issuer đáng tin. Đừng dùng fingerprint vừa in ra làm lý do tự tin dữ liệu; so sánh với fingerprint mà đối tác xác nhận qua kênh độc lập. Với trường hợp khai báo nhiều role/entity hoặc KeyInfo không chứa X509Certificate, mở rộng bộ kiểm kê có test riêng, không âm thầm bỏ qua khóa khi triển khai runtime.

### Lệnh kiểm tra chứng thư riêng

Nếu đối tác cung cấp certificate file có định dạng X.509, JDK có thể hiển thị thông tin:

~~~bash
keytool -printcert -file idp-signing.crt
~~~

Kết quả bao gồm issuer/subject, serial, validity và fingerprint tùy chứng thư. Trước khi áp dụng, so sánh certificate với metadata đã được xác thực, không chỉ so sánh tên file. `keytool` đọc certificate không cần private key; tuyệt đối tránh gửi private key qua email hoặc dán vào công cụ online.

## 10. Quản lý vòng đời: rollover signing và encryption keys

Key rotation là yêu cầu vận hành quan trọng, khác nhau giữa **khóa ký** và **khóa giải mã**. Trong signing, bên phát hành message phải giữ khả năng ký bằng private key mới trong khi bên nhận có public key phù hợp. Trong encryption, bên **nhận** phải giữ private key giải mã cho mọi ciphertext vẫn có thể đến hoặc đang tồn tại.

### 10.1. Xoay khóa ký của IdP

1. IdP tạo signing keypair mới, bảo vệ private key trong HSM/KMS/secret store và xác lập thời gian chuyển ký.
2. IdP công bố **public signing certificate mới** trong metadata cùng certificate cũ, với `KeyDescriptor use="signing"` phù hợp.
3. SP cập nhật hoặc refresh metadata/`RelyingPartyRegistration`, xác nhận đã tin cả hai khóa. Nếu registration được tạo tĩnh khi startup, cần biết liệu phải restart/redeploy để nhận thay đổi.
4. IdP chuyển signer sang private key mới theo lịch; SP verify bằng public key tương ứng.
5. Quan sát lỗi signature, tỷ lệ login, các SP/tenant và instance; giữ overlap phù hợp để xử lý thông điệp còn hiệu lực và cache.
6. Sau khi tất cả bên nhận đã cập nhật, token/assertion cũ hết hiệu lực và không còn cần khóa cũ, IdP gỡ key/cert cũ khỏi metadata theo change control.

**Không thay một signing cert cũ bằng cert mới ngay lập tức mà không phối hợp.** Khi SP cache metadata cũ, message ký bằng private key mới sẽ fail. Ngược lại, nếu SP bỏ khóa cũ quá sớm, message hợp lệ còn trong thời hạn có thể fail. Lịch overlap phải dựa trên Assertion lifetime, metadata cache/refresh, độ trễ và policy của từng đối tác.

### 10.2. Xoay khóa giải mã của SP

1. SP tạo encryption/decryption keypair mới, có public cert mới và private key mới trong secret store.
2. SP công bố encryption certificate mới trong **SP metadata** để IdP chuẩn bị dùng; xác nhận IdP đã nhận metadata.
3. SP nạp **cả old và new decryption private keys** nếu implementation hỗ trợ, đồng thời tiếp tục giữ old key trong thời gian chuyển tiếp.
4. IdP chuyển sang encrypt cho public key mới khi xác nhận SP đã có khả năng giải mã.
5. Kiểm thử hai ciphertext: encrypted bằng public key cũ và bằng key mới đều decrypt thành công trong overlap. Quan sát `DecryptionException`, unknown key và các endpoint lỗi.
6. Sau khi bên gửi không còn dùng cert cũ, các message cũ không cần xử lý và dữ liệu lưu trữ đã được migrate theo chính sách, SP gỡ old private key và metadata cũ.

**Điểm thường bị bỏ quên:** Metadata có thể chứa nhiều encryption certs nhưng IdP chỉ chọn một cert. Cách chọn không đồng nhất giữa các sản phẩm; phải thống nhất với đối tác cert nào đang active. Nếu SP đã xoay private key mà IdP vẫn encrypt bằng public key cũ, ứng dụng sẽ không decrypt được nếu đã xóa key cũ.

### 10.3. Xử lý khóa bị lộ

Nếu signing private key bị lộ, kẻ tấn công có thể phát message mang chữ ký tương ứng trong phạm vi nào đó; không tiếp tục overlap bình thường chỉ để tránh downtime. Cần ngừng tin compromised key, phát hành replacement, đánh giá session/user impacts, phối hợp IdP/SP, cập nhật metadata và log điều tra theo incident response. Nếu SP decryption private key bị lộ, dữ liệu đã mã hóa bằng public key đó có thể bị ảnh hưởng về tính bí mật; thay khóa và đánh giá dữ liệu đã lưu truyền/lưu trữ theo threat model.

## 11. Các lớp kiểm chứng ngoài `KeyDescriptor`

**KeyDescriptor đúng vẫn chưa đủ để chấp nhận một SAMLResponse.** Bên nhận cần:

- Chọn chính xác `RelyingPartyRegistration` từ context đã tin và kiểm tra `Issuer`/IdP entity ID.
- Xác minh chữ ký phù hợp trên Response hoặc Assertion bằng các signing verification credentials đáng tin.
- Kiểm tra `AudienceRestriction` nhắm đúng SP entity ID, `Destination` và `Recipient` khớp ACS.
- Kiểm tra `NotBefore`, `NotOnOrAfter`, `InResponseTo` khi SP khởi tạo request và chính sách chống replay.
- Nếu có mã hóa, giải mã bằng **decryption key SP đúng**, rồi áp dụng validation theo cấu trúc message/protection thực tế; không cho dữ liệu giải mã được tự trở thành principal.
- Chỉ sau đó ánh xạ NameID/attributes sang user và policy quyền nội bộ.
- Theo dõi metadata `validUntil`, `cacheDuration`, nguồn trust, key rotation, clock skew, cert dates và TLS proxy.

Tránh lỗi **XML Signature Wrapping**: không tự gọi “verify một element ký bất kỳ” rồi lấy NameID từ một element XML khác chưa được bảo vệ. Đừng viết XML parser/signature verifier tự chế để thay Spring Security/OpenSAML; tuân theo khả năng của thư viện đã cập nhật.

## 12. Ma trận kiểm thử trước khi bật production

| Trường hợp | Hành vi đúng | Thành phần được kiểm tra |
| --- | --- | --- |
| Response/Assertion IdP A ký bằng key đã đăng ký | SP chấp nhận khi tất cả conditions hợp lệ | `IdP signing KeyDescriptor` và validator |
| Message ký bằng key IdP B nhưng tự khai Issuer A | Từ chối | Ràng buộc signer ↔ issuer ↔ registration |
| Message của IdP A ký bằng key chưa công bố/được duyệt | Từ chối | Trust anchor |
| Message sửa nội dung sau khi ký | Từ chối | XML Digital Signature |
| Response có chứng thư đính kèm tự nhận là IdP A | Không tự thêm khóa vào trust store | Không tin key từ message |
| SP công bố public signing cert mới, IdP vẫn cache cert cũ | AuthnRequest ký mới có thể fail cho đến khi đồng bộ | Rotation SP signing |
| IdP công bố cả signing cert cũ và mới, đổi signer | SP tiếp tục xác minh nếu đã cập nhật đúng | Multi-key verification |
| SP public encryption cert mới, IdP vẫn encrypt bằng cert cũ | SP vẫn giải mã được trong thời gian overlap đã thiết kế | Multi-key decryption |
| IdP encrypt bằng public key không khớp private key SP | Fail decryption; không bỏ mã hóa để thông login | Certificate/key pairing |
| Đọc `KeyDescriptor use="encryption"` làm verification cert | Không dùng để verify chữ ký trái policy | Credential usage |
| `KeyDescriptor` không có `use` | Diễn giải đúng nghĩa cả hai theo đặc tả và local policy | Metadata parsing |
| Metadata từ URL lạ có cert mới | Không tự accept entity/keys nếu chưa được phê duyệt | Trust bootstrap |
| Metadata signature invalid khi policy bắt buộc | Từ chối cập nhật trust | Metadata signature validation |
| SAML Signature hợp lệ nhưng audience sai | Từ chối | SAML assertion conditions |
| SAML Signature hợp lệ nhưng hết hạn/replay | Từ chối | Time/correlation/replay |
| HTTPS certificate của metadata endpoint đổi | Xử lý theo TLS trust, không thay signer IdP vô cớ | Phân biệt TLS/SAML certificates |
| IdP metadata hết `validUntil` hoặc không được refresh | Cảnh báo/không sử dụng theo policy | Metadata lifecycle |
| SP không có decryption private key khi nhận EncryptedAssertion | Không đăng nhập được; xác định đúng nguyên nhân | Decryption credentials |
| User đăng nhập được nhưng thiếu role | Bị từ chối tài nguyên 403 | Authorization tách biệt authentication |

**Kiểm thử trong môi trường test** với IdP/SP giả lập, không can thiệp luồng SSO sản xuất. Không log toàn bộ `SAMLResponse`, `EncryptedKey`, assertion, secret, NameID hoặc session cookie. Với lỗi cần chẩn đoán sâu, dùng logging có chọn lọc và kiểm soát quyền truy cập.

## 13. Triệu chứng và cách sửa đúng nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra / hướng xử lý |
| --- | --- | --- |
| `InvalidSignature` khi IdP vừa rotate | SP cache metadata cũ, thiếu signing cert mới | So sánh fingerprint ở metadata được duyệt và key set đang active, refresh/redeploy đúng cách |
| `Signature validation failed` dù có certificate | Sai IdP entity ID/registration, signed element mismatch, alg không hỗ trợ | Kiểm tra Issuer, trust configuration, XML signature placement và signing algorithm policy |
| `DecryptionException` / cannot decrypt | IdP dùng public encryption cert khác private key SP | So sánh cert public trong SP metadata với decryption private key được cài; kiểm tra rollover |
| IdP từ chối AuthnRequest ký | SP signing cert chưa đăng ký, binding khác, signature không đúng | Đối chiếu SP metadata và `WantAuthnRequestsSigned`, SigAlg/Signature hoặc XML Signature |
| IdP đòi request ký nhưng SP không ký | SP thiếu signing credentials / cấu hình | Thiết lập SP signing private key + public cert, xác minh request thực |
| SAMLResponse hợp lệ nhưng Audience sai | SP entity ID hoặc IdP registration sai | Đồng bộ SP entity ID, không bỏ qua audience |
| ACS mismatch sau proxy | Server nhìn HTTP hoặc hostname nội bộ | Cấu hình forwarded headers từ proxy đáng tin, HTTPS public URL và IdP ACS |
| Certificate trong metadata có `NotAfter` đã qua | Có thể thiếu rotation hoặc policy không đồng bộ | Xem profile/chính sách certificate, lên kế hoạch thay và thử nghiệm, không suy đoán mọi thư viện auto-fail |
| Metadata signed nhưng không tin key | Metadata signing trust anchor chưa được cấu hình/chấp nhận | Xác minh nguồn trust qua kênh độc lập |
| Không thấy `X509Certificate` trong KeyDescriptor | Metadata chỉ có `KeyValue` hoặc `KeyName` | Kiểm tra cấu trúc KeyInfo và khả năng parser; KeyName đơn lẻ không đủ key material |
| Login lỗi chỉ ở một instance | Cache/credentials không đồng nhất giữa node | So sánh version metadata, secret mount và deployment rollout |
| New key hoạt động rồi old key vẫn được tin mãi | Rollover chưa cleanup | Hoàn tất plan xoay khóa, gỡ compromised/retired key đúng thời điểm |
| Logout yêu cầu chữ ký bị từ chối | SLO keys/policy khác login hoặc SP cert chưa đồng bộ | Kiểm tra request/response signing và cấu hình SLO riêng |

**Nguyên tắc xử lý:** Không tắt signature verification, không bỏ audience/recipient/time check, không cho phép cert từ response tùy ý và không hạ yêu cầu mã hóa chỉ để có “login thành công”. Tìm chính xác **cặp entity + vai trò + key purpose + thời điểm + message** bị sai.

## 14. Checklist triển khai một đối tác SAML mới

- [ ] Đã xác minh IdP/SP entity ID và nguồn metadata qua kênh quản trị được phê duyệt.
- [ ] Đã phân biệt metadata signing trust anchor với IdP signing certificate dùng xác minh Assertion.
- [ ] Đã kiểm tra mọi `KeyDescriptor`, `use`, `KeyInfo`, certificate và mục đích tương ứng.
- [ ] Đã xác nhận public/private key ownership; **không chia sẻ private key** qua bên đối tác.
- [ ] Đã thống nhất IdP ký Response hay Assertion, SP ký AuthnRequest/logout hay không.
- [ ] Đã thống nhất có encrypt Assertion/NameID/Attribute không, thuật toán hỗ trợ và SP decryption private key.
- [ ] Đã đối chiếu SP entity ID, ACS, binding, HTTPS/proxy và các URL công bố trong metadata.
- [ ] Đã cấu hình Spring Security `RelyingPartyRegistration`, verifying/signing/decryption credentials đúng role.
- [ ] Đã kiểm thử unsigned/wrong-key/wrong-issuer/wrong-audience/expired/replay/decryption mismatch.
- [ ] Đã thực hiện kế hoạch rotate với old/new public keys và old/new private decryption keys khi cần.
- [ ] Đã thiết lập alert/login failure monitoring, metadata refresh, certificate dates và kiểm soát secret.
- [ ] Đã ghi người sở hữu đối tác, lịch thay khóa, change approval, fallback và quy trình offboarding.

## 15. Bài tập củng cố

**Bài 1 – nhận diện bốn hướng.** Cho IdP A, SP B và một metadata có hai `KeyDescriptor use="signing"`, `use="encryption"`. Hãy vẽ mũi tên chỉ rõ bên nào giữ private key, bên nào dùng public key khi (i) IdP ký Response, (ii) SP ký AuthnRequest, (iii) IdP encrypt Assertion cho SP, (iv) SP encrypt message gửi IdP. Đối chiếu với bảng ở mục 4.

**Bài 2 – đọc metadata.** Chọn metadata **thử nghiệm** có `IDPSSODescriptor` và ít nhất một `ds:X509Certificate`. Xác định entity ID, KeyDescriptor count, từng `use`, fingerprint. Chạy `InspectSamlKeys.java`; đối chiếu fingerprint qua kênh quản trị đã xác thực. Giải thích tại sao việc xem fingerprint **không thay thế** metadata trust.

**Bài 3 – rollover IdP signing.** IdP đang ký bằng A, muốn chuyển sang B. Xây lịch công bố A+B, xác nhận tất cả SP đã nhận B, chuyển signer, quan sát login, thu hồi A. Đề xuất lỗi có thể gặp nếu một SP còn cache A.

**Bài 4 – rollover SP decryption.** IdP vẫn encrypt bằng public cert cũ khi SP đã đổi private key. Giải thích triệu chứng, cách thử decrypt bằng cả hai keys và vì sao SP không được gỡ khóa cũ quá sớm trong overlap.

**Bài 5 – Spring Security.** Tạo ứng dụng từ mục 8 với IdP SAML test, lưu signing/decryption keys trong secret files và đăng ký SP metadata với IdP. Thử một Response ký hợp lệ; thay verification certificate trong staging sang key khác, xác nhận login bị từ chối; khôi phục key đúng, thử encrypted assertion và quan sát trường hợp private key không khớp.

**Bài 6 – phân loại lỗi.** Một SP có Response được ký hợp lệ nhưng sai `AudienceRestriction`; một SP khác giải mã EncryptedAssertion được nhưng chữ ký không hợp lệ. Hai trường hợp nào được phép đăng nhập? **Không trường hợp nào.** Nêu bước kiểm chứng còn thiếu và vì sao encrypt/decrypt không thay signature/trust validation.

**Đạt bài khi** có thể giải thích KeyDescriptor/use/KeyInfo, phân biệt bốn luồng khóa, đọc đúng metadata của IdP và SP, chạy công cụ Java 17, cấu hình được Spring SAML2 bằng certificate đúng role, trình bày được signing/decryption rotation và ít nhất năm tình huống fail-closed.

## 16. Tài liệu chuẩn để đối chiếu

- OASIS SAML 2.0 Metadata, `2.4.1.1 KeyDescriptor: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML 2.0 Core (Assertions, XML Encryption, Authentication): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML Metadata Interoperability Profile (trust management/rollover): https://docs.oasis-open.org/security/saml/Post2.0/sstc-metadata-iop-cd-01.html
- Spring Security – SAML 2.0 Login Overview / Credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – Producing AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security – SAML Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.x – Spring Security / SAML2 Relying Party: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
