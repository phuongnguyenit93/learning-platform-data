# Giải mã EncryptedAssertion và lựa chọn khóa giải mã phù hợp trong Spring Security SAML 2.0

## 1. Mục tiêu và bài toán

Trong SAML 2.0 federation, **Identity Provider (IdP / Asserting Party)** có thể gửi kết quả đăng nhập đến **Service Provider (SP / Relying Party)** dưới dạng **`<saml:EncryptedAssertion>`** thay vì để nguyên `<saml:Assertion>` ở dạng có thể đọc được.

Tính năng này bảo vệ **tính bí mật của assertion** trên hành trình qua trình duyệt và các hệ thống trung gian. Assertion có thể chứa NameID, thuộc tính người dùng, định danh tổ chức và dữ liệu riêng tư. TLS bảo vệ từng kết nối HTTP, còn mã hóa assertion bảo vệ nội dung đối với các thành phần **không sở hữu khóa giải mã của SP**.

Bài học thuộc nhóm **Kiểm chứng SAML2** và tập trung vào hai việc liên quan chặt chẽ:

1. **Giải mã đúng `EncryptedAssertion`** khi IdP thực sự gửi assertion đã mã hóa.
2. **Lựa chọn đúng private key của SP** theo registration, certificate mà IdP đã sử dụng, chính sách rotation và cấu trúc XML Encryption.

Sau bài này, bạn cần hiểu:

- Vì sao IdP mã hóa bằng **public key SP**, còn **SP giải mã bằng private key tương ứng**.
- Vai trò của `<xenc:EncryptedData>`, `<xenc:EncryptedKey>`, `<ds:KeyInfo>` và cách chọn một credential từ **tập khóa đã được quản trị tin cậy**.
- Cách khai báo `decryption.credentials` trong Spring Boot và `Saml2X509Credential.decryption(...)` trong Spring Security.
- Vì sao **giải mã thành công không đồng nghĩa xác thực thành công**; cần kiểm tra chữ ký, issuer, audience, recipient, thời gian và correlation phù hợp.
- Thứ tự giải mã/kiểm chữ ký khi assertion được ký rồi mã hóa, hoặc khi thuộc tính bên trong assertion được mã hóa.
- Cách xử lý nhiều IdP, nhiều khóa, key rollover, sai thuật toán, lỗi Java/OpenSAML và các bài kiểm thử bảo mật.

**Nguyên tắc nền:** hệ thống chỉ được dùng **private key SP đã được phê duyệt cho registration đó**. Một KeyName, certificate hoặc gợi ý khóa nằm trong SAMLResponse do trình duyệt chuyển đến **không thể tự cấp quyền truy cập vào khóa mới hoặc thay đổi trust policy**.

## 2. SAML Assertion, EncryptedAssertion và ranh giới bí mật

SAML Response bình thường có thể chứa `<saml:Assertion>` ở dạng XML trực tiếp:

```text
samlp:Response
  saml:Issuer
  saml:Assertion
    saml:Issuer
    saml:Subject / NameID
    saml:Conditions / AudienceRestriction
    saml:AuthnStatement
    saml:AttributeStatement
```

Khi IdP mã hóa toàn bộ assertion, vị trí assertion sẽ được thay bằng `<saml:EncryptedAssertion>`:

```text
samlp:Response
  saml:Issuer
  saml:EncryptedAssertion
    xenc:EncryptedData                  <- ciphertext của Assertion XML
      xenc:EncryptionMethod             <- AES, v.v.
      ds:KeyInfo                        <- có thể tham chiếu EncryptedKey
      xenc:CipherData
    xenc:EncryptedKey                   <- khóa nội dung AES đã được bọc
      xenc:EncryptionMethod             <- RSA-OAEP, v.v.
      ds:KeyInfo                        <- gợi ý recipient key
      xenc:CipherData
```

Đây là **sơ đồ cấu trúc**, không phải thứ tự XML duy nhất được mọi nhà cung cấp dùng. Theo SAML/XML Encryption và các errata, `EncryptedKey` có thể được liên kết qua `KeyInfo` hoặc cơ chế tham chiếu hợp lệ khác; không viết code tùy tiện yêu cầu nó luôn nằm tại **một XPath cố định**.

### 2.1. Ba lớp cần phân biệt

| Lớp | Bảo vệ điều gì? | Thành phần liên quan |
| --- | --- | --- |
| **Mã hóa assertion** | Nội dung bí mật của assertion | `EncryptedAssertion`, `EncryptedData`, `EncryptedKey`, private key SP |
| **Chữ ký XML** | Tính toàn vẹn/xuất xứ của message hoặc assertion | `ds:Signature`, certificate xác minh của IdP |
| **Điều kiện SAML** | Assertion có đúng SP, đúng phiên và còn hiệu lực không | `Issuer`, `AudienceRestriction`, `Recipient`, `Destination`, `InResponseTo`, thời gian |

Mã hóa **không tự chứng minh người phát hành**. Một attacker biết public certificate SP có thể tạo ciphertext mới gửi về SP; chỉ một SAML Response/Assertion **được xác minh đúng** mới được phép trở thành `Authentication`.

## 3. Cơ chế mã hóa lai (hybrid encryption)

Trong triển khai SAML/XML Encryption phổ biến, IdP **không dùng trực tiếp RSA để mã hóa toàn bộ XML assertion** vì giới hạn kích thước và hiệu suất. Thay vào đó, IdP sử dụng **mã hóa lai**:

1. IdP tạo **content-encryption key (CEK)** đối xứng ngẫu nhiên cho một lần mã hóa.
2. Dùng CEK và thuật toán đối xứng như **AES** để mã hóa XML assertion, lưu ciphertext dưới `<xenc:EncryptedData>`.
3. Dùng **public key SP** để **bọc (wrap/transport)** CEK theo thuật toán như **RSA-OAEP**, lưu dưới `<xenc:EncryptedKey>`.
4. Gửi SAML Response chứa EncryptedAssertion đến **ACS endpoint của SP** qua trình duyệt.
5. SP chọn **private key** tương ứng với public key mà IdP đã dùng và giải mã EncryptedKey để lấy CEK.
6. SP dùng CEK để giải mã EncryptedData, khôi phục Assertion XML và **tiếp tục xác minh SAML**.

```text
                IdP                                  SP
        (có public cert SP)                  (giữ private key SP)
                |                                   |
       Tạo AES content key                          |
                |                                   |
       AES Encrypt(Assertion)                       |
                |                                   |
       ciphertext -> EncryptedData                  |
                |                                   |
       RSA-OAEP(public SP, AES key)                 |
                |                                   |
       wrapped CEK -> EncryptedKey                  |
                |                                   |
             SAML Response ------------------------>|
                                                    | chọn private key
                                                    | unwrap CEK
                                                    | AES Decrypt
                                                    v
                                               Assertion XML
                                                    |
                                                    v
                                      Xác minh chữ ký / SAML policy
                                                    |
                                                    v
                                       Authentication nếu hợp lệ
```

**Public certificate của SP không phải bí mật.** IdP cần nhận nó qua metadata SP hoặc cấu hình tích hợp đáng tin. **Private key của SP phải ở lại SP**, keystore/secret manager/HSM được quản trị. Không gửi private key cho IdP để “họ cấu hình mã hóa” và không dùng private key IdP để giải mã assertion gửi đến SP.

### 3.1. Khi nào không có EncryptedKey?

Không phải mọi XML Encryption đều cần mang `<xenc:EncryptedKey>` trong thông điệp. Một số profile có thể sử dụng khóa đối xứng đã thiết lập từ trước hoặc cơ chế nhận biết khóa cục bộ. SAML errata mô tả cách liên kết EncryptedKey/EncryptedData khi khóa được mang trong XML.

Vì vậy:

- **Không mặc định** mọi `EncryptedAssertion` đều có chính xác một `EncryptedKey`.
- Không viết XPath theo thứ tự cố định hoặc chỉ nhận một cấu trúc mà IdP của bạn chưa cam kết.
- Nếu ứng dụng chỉ hỗ trợ dạng hybrid RSA-OAEP/AES với EncryptedKey, hãy **thỏa thuận profile rõ ràng và từ chối dạng không được hỗ trợ**, không suy đoán hoặc lén dùng một khóa toàn cục.

## 4. Các khóa và certificate có vai trò khác nhau

| Credential | Sở hữu private key | Công dụng | Chỗ cấu hình thường gặp |
| --- | --- | --- | --- |
| **SP decryption** | **SP** | Giải mã `EncryptedKey`/assertion dành cho SP | `RelyingPartyRegistration.decryptionX509Credentials` |
| **SP signing** | SP | Ký AuthnRequest/LogoutRequest theo hợp đồng | `signingX509Credentials` |
| **IdP verification** | IdP (private key) | SP dùng **public cert IdP** kiểm tra chữ ký Response/Assertion | `assertingPartyMetadata.verificationX509Credentials` |
| **Metadata signer** | IdP hoặc federation operator | Xác minh chữ ký tài liệu metadata, nếu mô hình yêu cầu | Trust anchor metadata được cấp riêng |

Một tổ chức có thể sử dụng **cùng cặp khóa SP** cho signing và decryption, và Spring Security cho phép chỉ định credential cho nhiều mục đích. Tuy vậy, dùng **khóa riêng cho từng nhiệm vụ** thường giúp quản trị/rotation/thu hồi chính xác hơn khi IdP hỗ trợ.

**Lỗi nghiêm trọng:** cấu hình certificate IdP ở phần `decryption.credentials` rồi hy vọng SP giải mã được. Certificate IdP là public key của **IdP**, không phải private key SP. Tương tự, chỉ nhập public certificate SP mà thiếu private key tương ứng cũng không thể giải mã.

### 4.1. SP metadata và chứng thư dùng để mã hóa

SP thường công bố certificate phục vụ **encryption** qua:

```xml
<md:KeyDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    use="encryption">
  <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:X509Data>
      <ds:X509Certificate>BASE64_CERTIFICATE_DATA</ds:X509Certificate>
    </ds:X509Data>
  </ds:KeyInfo>
</md:KeyDescriptor>
```

Đây là **trích đoạn minh họa**, `BASE64_CERTIFICATE_DATA` chỉ là ký hiệu để giải thích, không phải certificate thật. IdP cần import đúng **SP encryption certificate** vào ứng dụng SP đã đăng ký, rồi mã hóa cho public key ấy. Nếu IdP giữ bản certificate cũ, nó sẽ tạo EncryptedKey mà private key mới không giải được; phải duy trì khóa cũ tạm thời theo kế hoạch rotation hoặc đồng bộ cấu hình trước.

Trong metadata có thể có nhiều `KeyDescriptor` cùng mục đích để rollover. `use` có thể vắng mặt theo SAML metadata, khi ấy một khóa có thể được mô tả cho nhiều mục đích theo profile/chính sách; cần đối chiếu với IdP trước khi giả định rằng “khóa đầu tiên” là khóa mã hóa chính.

## 5. EncryptedData, EncryptedKey, KeyInfo: trường nào chọn khóa?

Một `EncryptedAssertion` thường chứa các khái niệm:

```xml
<saml:EncryptedAssertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:xenc="http://www.w3.org/2001/04/xmlenc#"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <xenc:EncryptedData
      Type="http://www.w3.org/2001/04/xmlenc#Element">
    <xenc:EncryptionMethod
        Algorithm="http://www.w3.org/2009/xmlenc11#aes128-gcm"/>
    <ds:KeyInfo>
      <!-- tham chiếu hoặc liên kết tới EncryptedKey theo profile -->
    </ds:KeyInfo>
    <xenc:CipherData>
      <xenc:CipherValue>BASE64_ENCRYPTED_ASSERTION</xenc:CipherValue>
    </xenc:CipherData>
  </xenc:EncryptedData>
  <xenc:EncryptedKey>
    <xenc:EncryptionMethod
        Algorithm="http://www.w3.org/2009/xmlenc11#rsa-oaep"/>
    <ds:KeyInfo>
      <!-- có thể có KeyName / X509Data gợi ý người nhận -->
    </ds:KeyInfo>
    <xenc:CipherData>
      <xenc:CipherValue>BASE64_WRAPPED_CONTENT_KEY</xenc:CipherValue>
    </xenc:CipherData>
  </xenc:EncryptedKey>
</saml:EncryptedAssertion>
```

Đoạn này **chỉ để học cấu trúc**, chưa phải XML Encryption hợp lệ có thể giải mã: ciphertext là ký hiệu, thiếu tham số/chỉ dẫn đầy đủ và có thể cần namespace/phần tử phù hợp profile. Tuyệt đối không dùng nó làm SAMLResponse test dương tính.

| Thành phần | Chức năng | Lưu ý lựa chọn khóa |
| --- | --- | --- |
| `EncryptedData/EncryptionMethod` | Thuật toán mã hóa **nội dung** (AES) | Không cho biết private key RSA nào |
| `EncryptedKey/EncryptionMethod` | Thuật toán **bọc CEK** (RSA-OAEP, v.v.) | Phải được hỗ trợ bởi private key/protocol |
| `EncryptedKey/CipherValue` | CEK đã mã hóa | Chỉ private key phù hợp mới unwrap đúng |
| `EncryptedData/CipherValue` | Assertion ciphertext | Dùng CEK sau khi unwrap để giải mã |
| `ds:KeyInfo` / `ds:KeyName` | Gợi ý khóa/cert/recipient | **Không phải nguồn cấp khóa tin cậy** |
| `xenc:EncryptedKey/@Recipient` nếu có | Gợi ý/định danh bên nhận | Đối chiếu với SP chính xác, không tin một mình |
| `ds:RetrievalMethod` / `ReferenceList` khi dùng | Liên kết EncryptedKey với EncryptedData | Chỉ theo các dạng được thư viện và policy cho phép |

**KeyInfo là một hint, không phải lệnh cấp quyền.** Nếu message ghi `KeyName=sp-2030`, ứng dụng chỉ được xem nó là gợi ý tìm **một khóa đã tồn tại trong tập credential được quản trị cho registration đúng**. Không đọc `KeyName` như đường dẫn file, ID secret manager do người gửi tự chọn, hoặc URL tải private key.

## 6. Chọn đúng private key: thuật toán, registration và key ring

### 6.1. Thứ tự lựa chọn an toàn

1. Xác định **`RelyingPartyRegistration`** đang xử lý SAML Response theo cấu hình Spring Security và ngữ cảnh request/correlation đã tin cậy.
2. Lấy **chỉ** các `Saml2X509Credential` có loại **DECRYPTION** của **Relying Party** trong registration đó.
3. Dựa trên `KeyInfo`/certificate identifier/recipient, có thể **lọc bớt** các credential ứng viên trong tập đã tin cậy.
4. Kiểm tra thuật toán `EncryptedKey` có tương thích loại khóa, kích thước và policy mật mã.
5. Thử unwrap CEK bằng private key phù hợp, trong giới hạn tài nguyên rõ ràng. Nếu chưa có gợi ý chắc chắn, thư viện có thể thử các candidate được cho phép theo thứ tự hợp lý, nhưng **không thử khóa của tenant/registration khác một cách vô hạn**.
6. Dùng CEK giải mã `EncryptedData` theo thuật toán/chế độ/IV/tag đúng.
7. Xác minh kết quả là assertion XML hợp lệ và thực hiện **toàn bộ kiểm chứng chữ ký + điều kiện SAML** trước khi tạo phiên đăng nhập.
8. Nếu không có khóa phù hợp hoặc thuật toán không được phép, **fail closed** với lỗi có thể vận hành, không chuyển sang “bỏ mã hóa” hay chấp nhận assertion tự khai.

### 6.2. Ví dụ lựa chọn key ring

Giả sử SP có hai khóa giải mã trong giai đoạn rotation:

| Key ID nội bộ | Trạng thái | Private key có ở SP? | SP certificate được IdP biết? |
| --- | --- | --- | --- |
| `sp-dec-2025` | Chỉ giữ để giải mã dữ liệu cũ | Có, còn được duyệt | IdP có thể còn mã hóa bằng cert cũ khi chuyển tiếp |
| `sp-dec-2026` | Khóa chính cho ciphertext mới | Có | IdP đã import cert mới |

Khi EncryptedKey được tạo bằng **public key 2026**, chỉ private key 2026 tương ứng có thể unwrap CEK theo phép mã hóa đã dùng. SP có thể thử 2025 trước và gặp lỗi, nhưng **không phải mọi lỗi đầu tiên đều là bằng chứng assertion bị giả**; nếu policy cho phép cả hai khóa, nó có thể chuyển qua 2026 theo cơ chế an toàn của thư viện. Ngược lại, sau khi 2025 đã bị thu hồi và loại khỏi key ring, **không được nạp nó lại** chỉ vì request có KeyName đề nghị.

Một thiết kế không an toàn:

```text
keyPath = "/secrets/" + userSuppliedKeyName
privateKey = load(keyPath)
decrypt(...)
```

Một thiết kế an toàn về nguyên tắc:

```text
registration = trustedRegistrationResolver(responseContext)
allowedKeys = registration.decryptionCredentials
hint = parseUntrustedKeyHint(samlResponse)
candidateKeys = selectWithin(allowedKeys, hint)
decryptWithBoundedCandidates(candidateKeys)
verifyAssertionAndPolicy(...)
```

Mã giả chỉ minh họa **phạm vi quyền chọn khóa**. Mọi thao tác parse XML, lookup và giải mã thực tế cần OpenSAML/Spring Security, không tự viết bộ XML Encryption.

### 6.3. Các mối quan hệ không được suy đoán

- `registrationId` là khóa cấu hình local Spring; **không phải** mã private key và không phải SAML subject.
- SP `entityId` là định danh hệ thống đích của assertion; **không phải** tên file private key.
- `IdP entityId` giúp xác định nhà phát hành **sau validation**, không phải khóa giải mã của SP.
- `KeyInfo` có thể chứa certificate/KeyName do IdP gửi và phải được đối chiếu với cấu hình, không được biến thành trust anchor động.
- `NameID` là danh tính người dùng bên trong assertion sau giải mã, **không dùng để chọn private key** (chưa thể biết NameID trước khi giải mã).
- `RelayState`/URL callback không nên quyết định một cách tùy ý đến key ring của tenant khác.
- Mật mã giải mã thành công không chứng minh issuer/audience hợp lệ; một public certificate SP có thể được bất kỳ bên nào dùng để mã hóa dữ liệu.

## 7. Thuật toán mã hóa: tính tương thích và chính sách

Để xử lý một EncryptedAssertion, hai bên phải thống nhất **hai lớp thuật toán**:

### 7.1. Content encryption

| Thuật toán / URI điển hình | Vai trò | Cân nhắc |
| --- | --- | --- |
| `http://www.w3.org/2009/xmlenc11#aes128-gcm` | AES-128-GCM cho nội dung | Có kiểm tra tag toàn vẹn ở lớp mật mã; ưu tiên khi IdP/OpenSAML và XML Encryption profile hỗ trợ |
| `http://www.w3.org/2009/xmlenc11#aes256-gcm` | AES-256-GCM cho nội dung | Yêu cầu provider/cấu hình tương thích |
| `http://www.w3.org/2001/04/xmlenc#aes128-cbc` | AES-128-CBC dạng legacy | Không có authentication tag riêng, cần xem xét rủi ro và cấu hình chống oracle |
| `http://www.w3.org/2001/04/xmlenc#aes256-cbc` | AES-256-CBC dạng legacy | Dùng khi có yêu cầu interoperability được đánh giá kỹ, không mặc nhiên an toàn hơn GCM |

**Lưu ý:** SAML 2.0 cũ và các sản phẩm IdP khác nhau có mức hỗ trợ XML Encryption 1.0/1.1 khác nhau. Không tự chuyển toàn bộ đối tác sang AES-GCM nếu stack thực tế chỉ hỗ trợ AES-CBC; cần kiểm tra khả năng hỗ trợ, phiên bản OpenSAML, metadata, IdP policy và negative tests trước khi thay đổi. Nhưng cũng **không nới policy** để bật thuật toán cũ nguy hiểm chỉ nhằm che giấu lỗi key.

### 7.2. Key transport/key wrapping

| Thuật toán / URI điển hình | Vai trò | Cân nhắc |
| --- | --- | --- |
| RSA-OAEP `http://www.w3.org/2001/04/xmlenc#rsa-oaep-mgf1p` | Bọc khóa với OAEP kiểu XML Encryption 1.0 | Tham số mặc định/digest cần khớp thông điệp và profile |
| RSA-OAEP `http://www.w3.org/2009/xmlenc11#rsa-oaep` | OAEP XML Encryption 1.1 | Hỗ trợ cấu hình DigestMethod/MGF phù hợp nếu có |
| RSA v1.5 `http://www.w3.org/2001/04/xmlenc#rsa-1_5` | Key transport legacy | Không khuyến nghị vì các rủi ro oracle; nên từ chối theo security policy hiện đại |

**Không đồng nhất RSA-OAEP với “OAEP luôn dùng SHA-256”.** XML Encryption có nhiều URI/đường biểu diễn digest và MGF. Bên giải mã phải tuân theo thuật toán/tham số được phép theo thông điệp/profile; sai `DigestMethod` hoặc MGF có thể khiến private key đúng vẫn unwrap thất bại.

### 7.3. Các biện pháp an toàn

- Cho phép **danh sách thuật toán cụ thể** phù hợp với chính sách và khả năng IdP/SP; loại trừ RSA v1.5, mã hóa yếu và downgrade không có phê duyệt.
- Giới hạn **kích thước XML/SAMLResponse**, số `EncryptedKey`, số candidate key, CPU và thời gian xử lý; tránh DoS.
- XML parser cần chặn **DTD, external entity (XXE), XInclude, external URI/transform** không được phép; sử dụng thư viện SAML/XMLSec được bảo trì.
- Không phản hồi lỗi chi tiết kiểu “padding đúng/sai”, “khóa A đúng”, “AES tag fail” cho bên ngoài vì có thể tạo **decryption oracle**. Ghi mã lỗi đủ để vận hành ở log nội bộ an toàn.
- Đối chiếu nội dung sau giải mã với schema và ràng buộc SAML; không dùng một chuỗi XML chưa kiểm chữ ký làm quyền truy cập.

## 8. Thứ tự giải mã và kiểm tra chữ ký: phần dễ sai nhất

SAML cho phép kết hợp **XML Encryption** và **XML Digital Signature** theo nhiều cách. Đặc biệt:

### 8.1. Assertion được ký rồi mã hóa

Quy trình IdP:

```text
Assertion XML
   -> ký Assertion (ds:Signature nằm trong Assertion)
   -> mã hóa cả Assertion
   -> EncryptedAssertion trong Response
```

Phía SP thực hiện **theo thứ tự ngược**:

```text
EncryptedAssertion
   -> giải mã với private key SP
   -> Assertion có ds:Signature
   -> xác minh chữ ký assertion bằng public cert IdP đã tin
   -> xác minh điều kiện SAML
```

Ở đây không thể kiểm chữ ký **bên trong assertion** trước khi giải mã vì chữ ký đang bị mã hóa cùng nội dung. Nếu Response ngoài cũng được ký, chữ ký Response (bảo vệ encrypted bytes) có quy trình xác minh riêng.

### 8.2. Attribute hoặc NameID bên trong Assertion được mã hóa

Quy trình IdP có thể là:

```text
Assertion
   -> mã hóa một hoặc nhiều Attribute / NameID
   -> ký Assertion bao gồm các phần tử encrypted
```

Phía SP cần **xác minh chữ ký assertion trước khi thay đổi cây XML đã ký**. Nếu giải mã một `EncryptedAttribute` trước khi kiểm chữ ký của assertion bao ngoài, cây XML bị thay và có thể khiến chữ ký không còn khớp.

Spring Security tài liệu hóa hai chiến lược:

- **Response elements decrypter**: giải mã phần tử ở cấp Response, ví dụ `EncryptedAssertion`.
- **Assertion elements decrypter**: giải mã `EncryptedAttribute` hoặc `EncryptedID` nằm bên trong Assertion.

Việc tách hai thời điểm giải mã chính là để tránh **giải mã quá sớm làm sai chữ ký của Assertion đã được ký**. <https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html>

### 8.3. Response ký, Assertion không ký?

Một số profile cho phép chữ ký ở **Response** thay vì từng Assertion, hoặc ký cả hai. SP phải thực hiện **chính sách signature coverage đã thỏa thuận**: nếu chỉ Response được ký thì cần xác minh đúng chữ ký bao phủ response chứa encrypted data theo cấu trúc; nếu assertion ký riêng cần xác minh chữ ký sau khi giải mã. Đừng coi “đã giải mã được” là chữ ký. Đừng tắt signature validation vì XML bên trong có `NameID` mong đợi.

**Điểm mấu chốt:** thứ tự thao tác phụ thuộc **cái gì đã được ký và cái gì được mã hóa**. Sử dụng lifecycle validation của Spring Security/OpenSAML thay vì tự parse/replace XML trong controller.

## 9. Cấu hình Spring Boot: decryption credentials của SP

Trong Spring Boot hỗ trợ SAML 2.0 Relying Party, các credentials phục vụ giải mã được đặt dưới **`decryption.credentials` của registration**. Ví dụ môi trường có hai khóa trong giai đoạn rollover:

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:portal:prod:sp"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-dec-2026.key"
                  certificate-location: "file:/etc/saml/sp-dec-2026.crt"
                - private-key-location: "file:/run/secrets/saml/sp-dec-2025.key"
                  certificate-location: "file:/etc/saml/sp-dec-2025.crt"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "file:/etc/saml/idp-metadata.xml"
```

**Đọc chính xác:**

- `corp` là **registrationId** local, để Spring Security tìm đúng cặp SP–IdP.
- `entity-id` là **SP Entity ID**, phải phù hợp với Audience trong assertion.
- Mỗi item `decryption.credentials` gồm **private key SP** và X.509 certificate **tương ứng**. File là ví dụ tên/đường dẫn; cần được provision bởi môi trường thật.
- `sp-dec-2026` là khóa mới, `sp-dec-2025` là khóa cũ còn được duyệt trong cửa sổ rollover. Trật tự liệt kê chỉ là một lựa chọn cấu hình; **không dựa vào “mục đầu tiên” như bảo đảm giao thức**.
- `assertingparty.metadata-uri` là nguồn IdP metadata, không phải private key SP và không tự chứng minh metadata đó được ký hợp lệ. Một nguồn file nội bộ vẫn cần quy trình nhập/cập nhật IdP metadata đáng tin.
- `acs.location` là nơi SP nhận SAMLResponse; không phải nơi đặt khóa giải mã.

Cấu hình có thể thay theo phiên bản Spring Boot, nhưng property `spring.security.saml2.relyingparty.registration.<registrationId>.decryption.credentials[*].private-key-location` và `certificate-location` được Spring Boot tài liệu hóa. Kiểm tra property metadata/Javadoc **của phiên bản đang triển khai**.

### 9.1. Đã có khóa giải mã thì còn cần gì?

Ít nhất vẫn phải có:

- `spring-security-saml2-service-provider` cùng dependency Servlet/Security của dự án.
- IdP metadata/verification credentials đáng tin để **xác minh chữ ký IdP**.
- SP Entity ID, ACS và registration chọn đúng theo request.
- IdP đã import **SP encryption certificate** mới, trỏ tới chính SP được đăng ký.
- Thuật toán encryption/transport được cả hai bên hỗ trợ.
- Cấu hình session, HTTPS, reverse proxy, key protection và quyền nghiệp vụ.

Không nên công bố secret private key của SP trong `application.yml` hoặc classpath của container image dùng chung; ở ví dụ chúng được tham chiếu từ file mount có quyền đọc hạn chế. Nếu dùng secret manager hoặc HSM, tích hợp qua API/provider phù hợp thay vì để key xuất vào log hoặc repository.

### 9.2. Thử phản hồi có EncryptedAssertion

Sau cấu hình, bật `saml2Login()` và thực hiện một đăng nhập SP-initiated trên môi trường kiểm thử. IdP phải **thực sự bật mã hóa assertion**; chỉ có decryption credentials ở SP không khiến IdP tự động mã hóa mọi Response nếu phía IdP chưa được cấu hình nhận SP certificate.

Kiểm tra SAMLResponse ở môi trường thử nghiệm có `EncryptedAssertion`, thuật toán `EncryptedData` và `EncryptedKey` đúng, sau đó xác nhận kết quả đăng nhập qua Spring Security. Không cần viết controller tự gọi AES hoặc RSA trong ứng dụng.

## 10. Cấu hình Java: Saml2X509Credential.decryption và RelyingPartyRegistration

Spring Security cung cấp `Saml2X509Credential` cho các mục đích SIGNING, DECRYPTION, VERIFICATION và ENCRYPTION. Với SP giải mã, cần một `Saml2X509Credential` có **private key của SP**.

Ví dụ **trích đoạn trong một dự án Spring Boot**, giả định `privateKey2026`, `privateKey2025` là `PrivateKey` và `certificate2026`, `certificate2025` là `X509Certificate`, đều đã được đọc an toàn và kiểm tra khớp:

```java
Saml2X509Credential decrypt2026 =
    Saml2X509Credential.decryption(
        privateKey2026, certificate2026);

Saml2X509Credential decrypt2025 =
    Saml2X509Credential.decryption(
        privateKey2025, certificate2025);

RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("file:/etc/saml/idp-metadata.xml")
        .registrationId("corp")
        .entityId("urn:example:portal:prod:sp")
        .decryptionX509Credentials(credentials -> {
            credentials.add(decrypt2026);
            credentials.add(decrypt2025);
        })
        .build();
```

Đoạn trên **không phải file Java độc lập**: cần imports, credentials thực tế, các Spring Security classes và `RelyingPartyRegistrationRepository` lưu registration. `fromMetadataLocation` cần IdP metadata tin cậy; nó không thay thế việc xác minh metadata theo chính sách. Builder API có thể có khác biệt giữa Spring Security 5/6/7, nên đối chiếu đúng version.

**`decryptionX509Credentials` thuộc SP/Relying Party**, còn `verificationX509Credentials` thường nằm dưới Asserting Party/IdP. Không tráo hai danh sách.

### 10.1. Nạp RSA private key và X.509 certificate

Theo tài liệu Spring Security, với trường hợp RSA thường gặp có thể dùng utility `RsaKeyConverters.pkcs8()` để chuyển private key PKCS#8 cùng certificate SP:

```java
Resource keyFile = new FileSystemResource(
    "/run/secrets/saml/sp-dec-2026.key");
Resource certificateFile = new FileSystemResource(
    "/etc/saml/sp-dec-2026.crt");

RSAPrivateKey key;
try (InputStream in = keyFile.getInputStream()) {
    key = RsaKeyConverters.pkcs8().convert(in);
}

X509Certificate certificate;
try (InputStream in = certificateFile.getInputStream()) {
    certificate = (X509Certificate)
        CertificateFactory.getInstance("X.509")
            .generateCertificate(in);
}

Saml2X509Credential credential =
    Saml2X509Credential.decryption(key, certificate);
```

**Chỉ là đoạn trong ứng dụng có imports/dependencies**, không phải tệp Java chạy độc lập. Lệnh nạp trên giả định key ở định dạng **PKCS#8 được converter hỗ trợ**. Key mã hóa bằng password, key PKCS#1 hoặc key lưu trong HSM/PKCS#11 có thể yêu cầu cách nạp/provider khác. Tài liệu Spring Security có ví dụ tương đương về `RsaKeyConverters`; Spring Boot có thể tự nạp khi dùng các property file được hỗ trợ.

Đừng coi việc nạp hai file thành công là đã chứng minh chúng **cùng cặp khóa**. Kiểm tra keypair trong provisioning/triển khai bằng phép thử mật mã an toàn hoặc công cụ certificate/keystore; nếu lệch, decrypt sẽ thất bại khi chạy thực tế.

## 11. Spring Security tự giải mã những gì?

Trong Spring Security SAML 2.0 hiện đại, **`OpenSaml5AuthenticationProvider`** chịu trách nhiệm xác thực SAMLResponse. Theo tài liệu chính thức, provider tự giải mã:

- `<saml:EncryptedAssertion>` ở cấp **Response**, thông qua response-elements decrypter.
- `<saml:EncryptedAttribute>` và `<saml:EncryptedID>` bên trong **Assertion**, thông qua assertion-elements decrypter.

Nó sử dụng các decryption `Saml2X509Credential` được đăng ký trong `RelyingPartyRegistration`, nếu các cấu trúc/thuật toán tương thích.

Điều này có nghĩa **trong trường hợp thông thường chỉ cần khai đúng decryption credentials**, không phải tự viết một `EncryptedAssertion` parser và RSA/AES decryptor.

### 11.1. Khi nào cần custom decrypter?

Có thể cần khi:

- Private key nằm trong **HSM/remote crypto service** và không thể xuất về JVM; phải tích hợp đường decrypt phù hợp với trust policy.
- Đối tác sử dụng một profile XML Encryption đặc thù được bộ giải mã mặc định không hỗ trợ, nhưng vẫn có phương án được kiểm chứng và bảo trì.
- Cần thay đổi chiến lược lấy khóa/thuật toán theo kiến trúc tổ chức mà không đánh mất thứ tự signature validation.

Tài liệu Spring Security có API cho phép thay strategy:

```java
OpenSaml5AuthenticationProvider provider =
    new OpenSaml5AuthenticationProvider();

// Trích đoạn: decryptionService do ứng dụng tự thiết kế.
// Đây là callback dành cho các phần tử ở cấp Response,
// bao gồm EncryptedAssertion.
provider.setResponseElementsDecrypter(responseToken ->
    decryptionService.decrypt(responseToken.getResponse()));
```

Đây là **trích đoạn tích hợp**, không chạy được độc lập. Cần import và cung cấp `decryptionService` thực hiện đúng giao thức, cấu hình provider vào `AuthenticationManager` được sử dụng bởi `saml2Login()`. **Chỉ khai provider bean mà không lắp vào filter chain chưa chắc làm Spring Security dùng nó.**

Nếu tùy chỉnh giải mã **EncryptedAttribute/EncryptedID**, Spring Security cung cấp `setAssertionElementsDecrypter(...)` riêng. Phải giữ **chữ ký assertion được kiểm tra trước khi thay đổi những phần tử nằm trong phạm vi chữ ký**.

**Cảnh báo:** đừng thay custom decrypter rồi bỏ qua mặc định về kiểm chữ ký, audience, SubjectConfirmation và Request correlation. Nếu custom service trả về XML do chính nó giải mã, Spring Security vẫn cần kiểm tra đầy đủ tính hợp lệ của assertion đó theo policy.

Nguồn kỹ thuật: <https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html>.

## 12. Java 17 độc lập: mô phỏng chọn khóa và phát hiện ciphertext bị sửa

Ví dụ chạy bằng JDK 17+ sau đây minh họa **mật mã lai** và quyết định lấy khóa theo một key ring đã phê duyệt:

- Tạo hai cặp RSA của SP: khóa cũ `sp-2025`, khóa mới `sp-2026`.
- IdP giả định dùng **public key mới** để bọc AES CEK bằng **RSA-OAEP (SHA-256 và MGF1-SHA256)**.
- AES-128-GCM dùng để bảo vệ một chuỗi **payload minh họa**, không phải SAML Assertion hợp lệ.
- Bên nhận chỉ lấy private key từ một `Map` được cung cấp trước.
- Kiểm tra khóa đúng, chỉ có khóa cũ, tên key đúng nhưng private key sai, ciphertext bị sửa.

**Giới hạn quan trọng:** chương trình không tạo hoặc parse `saml:EncryptedAssertion`, không triển khai XML Encryption serializer, không xử lý `EncryptedKey/KeyInfo` thật, không kiểm chữ ký XML/SAML và không tạo `Authentication`. Dùng nó để hiểu **quan hệ RSA-OAEP + AES-GCM + key ring**, còn SAML production phải dùng Spring Security/OpenSAML.

Tệp `SamlDecryptionKeySelectionDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.Key;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.spec.MGF1ParameterSpec;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

public class SamlDecryptionKeySelectionDemo {
    record Envelope(String keyHint, byte[] wrappedAesKey,
                    byte[] nonce, byte[] ciphertext) {}

    static KeyPair rsaKeyPair() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    static Cipher rsaOaep(int mode, Key key) throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
        OAEPParameterSpec params = new OAEPParameterSpec(
            "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
            PSource.PSpecified.DEFAULT
        );
        cipher.init(mode, key, params);
        return cipher;
    }

    static Envelope encrypt(String payload, String keyHint,
                            PublicKey spPublicKey)
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey contentKey = generator.generateKey();
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.ENCRYPT_MODE, contentKey,
                 new GCMParameterSpec(128, nonce));
        byte[] encryptedPayload = aes.doFinal(
            payload.getBytes(StandardCharsets.UTF_8));

        byte[] wrappedKey = rsaOaep(
            Cipher.ENCRYPT_MODE, spPublicKey).doFinal(
                contentKey.getEncoded());
        return new Envelope(keyHint, wrappedKey, nonce, encryptedPayload);
    }

    static String decrypt(Envelope envelope,
                          Map<String, PrivateKey> approvedKeys)
            throws GeneralSecurityException {
        PrivateKey key = approvedKeys.get(envelope.keyHint());
        if (key == null) {
            throw new GeneralSecurityException("No approved key");
        }
        byte[] contentKeyBytes = rsaOaep(
            Cipher.DECRYPT_MODE, key).doFinal(envelope.wrappedAesKey());
        SecretKeySpec contentKey =
            new SecretKeySpec(contentKeyBytes, "AES");
        Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
        aes.init(Cipher.DECRYPT_MODE, contentKey,
                 new GCMParameterSpec(128, envelope.nonce()));
        return new String(
            aes.doFinal(envelope.ciphertext()), StandardCharsets.UTF_8);
    }

    static boolean matches(Envelope envelope,
                           Map<String, PrivateKey> keys,
                           String expectedPayload) {
        try {
            return expectedPayload.equals(decrypt(envelope, keys));
        } catch (GeneralSecurityException ex) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPair oldKey = rsaKeyPair();
        KeyPair newKey = rsaKeyPair();
        String payload = "opaque-assertion-payload";
        Envelope envelope =
            encrypt(payload, "sp-2026", newKey.getPublic());

        Map<String, PrivateKey> active = Map.of(
            "sp-2025", oldKey.getPrivate(),
            "sp-2026", newKey.getPrivate());
        Map<String, PrivateKey> oldOnly = Map.of(
            "sp-2025", oldKey.getPrivate());
        Map<String, PrivateKey> wrong = Map.of(
            "sp-2026", oldKey.getPrivate());

        System.out.println("correctKey="
            + matches(envelope, active, payload));
        System.out.println("oldKeyOnly="
            + matches(envelope, oldOnly, payload));
        System.out.println("wrongPrivateKey="
            + matches(envelope, wrong, payload));

        byte[] tampered = envelope.ciphertext().clone();
        tampered[tampered.length - 1] ^= 1;
        Envelope changed = new Envelope(
            envelope.keyHint(), envelope.wrappedAesKey(),
            envelope.nonce(), tampered);
        System.out.println("tamperingRejected="
            + !matches(changed, active, payload));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 SamlDecryptionKeySelectionDemo.java
java SamlDecryptionKeySelectionDemo
```

**Stdout chính xác** (giá trị RSA/AES được tạo ngẫu nhiên nhưng các Boolean có kết quả dưới đây):

```text
correctKey=true
oldKeyOnly=false
wrongPrivateKey=false
tamperingRejected=true
```

**Giải thích:**

- `correctKey=true`: trong tập credential được cho phép có private key 2026 khớp public key dùng để mã hóa CEK.
- `oldKeyOnly=false`: key ring chỉ chứa khóa 2025, không có khóa mà ciphertext cần.
- `wrongPrivateKey=false`: một key hint có tên `sp-2026` **không biến khóa cũ thành đúng khóa mới**. Tên là chỉ dấu chọn, không phải bằng chứng mật mã.
- `tamperingRejected=true`: AES-GCM xác minh authentication tag và phát hiện ciphertext bị thay đổi. Nhưng kết quả này **không thay thế xác minh chữ ký SAML** vì nhiều bên có thể biết public key SP và tạo ciphertext mới hợp lệ của họ.

Ví dụ dùng map key hint để trình bày đơn giản; hệ thống thật phải chọn credential theo **registration + approved key ring + metadata/certificate policy**, với giới hạn thuật toán và số lần thử. Các thuật toán và cách encode ciphertext trong ví dụ **không tự tương thích XML Encryption 1.1 trên wire** nếu thiếu serialization, key info và nonce/tag format theo chuẩn.

## 13. Quản lý nhiều IdP, tenant và registration

Một ứng dụng có thể có:

```text
RelyingPartyRegistration employee
    IdP A
    SP entityID = urn:example:portal:prod:sp
    decryption keys = {sp-employee-2025, sp-employee-2026}

RelyingPartyRegistration partner
    IdP B
    SP entityID = urn:example:portal:prod:sp
    decryption keys = {sp-partner-2026}
```

Hai registration có thể cùng SP Entity ID trong trường hợp hợp đồng cho phép, nhưng **không vì vậy mà mọi private key nên được gộp**. Khả năng giải mã thuộc về **mối quan hệ trust/cấu hình kỹ thuật cụ thể**:

- Response của IdP A phải được xử lý bởi registration được chọn và sau đó **Issuer/Signature/Audience** được xác minh phù hợp. Không cho header/query do attacker tự chỉ định tenant rồi mở toàn bộ key ring.
- Key ring của `employee` có thể được tái sử dụng có chủ đích ở `partner` nếu cùng SP ownership và policy cho phép; việc tái sử dụng phải **được cấu hình rõ ràng**.
- `ds:KeyInfo` trong một response không được buộc hệ thống truy vấn private key của tenant khác. Cần cách ly và kiểm soát số candidate.
- Trước khi giải mã một assertion, chưa thể tin `NameID`, group hay email trong đó để xác định nên dùng khóa của tenant nào.
- Sau khi giải mã và xác thực, authorization vẫn dựa trên **local user**, membership, tenant và quyền nghiệp vụ, không dựa vào việc một private key đã mở được ciphertext.

Một identity broker là một trường hợp khác: SP tin khóa/issuer từ **broker** đã được cấu hình, còn broker giải quyết trust với upstream IdP. Không suy key của upstream IdP phải dùng trực tiếp để giải mã assertion được broker phát hành cho SP.

## 14. Rotation khóa giải mã mà không làm gián đoạn SSO

Đổi certificate mã hóa của SP là một hoạt động **hai phía**: SP giữ private keys; IdP chọn public cert để mã hóa.

Một kế hoạch an toàn:

1. **Kiểm kê trạng thái hiện tại**: registration, SP Entity ID, certificate SP đang dùng, key type/thuật toán, IdP đã import certificate nào, thời gian hết hạn.
2. **Tạo keypair mới** qua quy trình được phê duyệt, lưu private key trong secret manager/HSM/volume có quyền hạn hẹp. Cấp public certificate cho IdP hoặc xuất SP metadata đã xác thực.
3. **Bổ sung khóa mới tại SP trước khi IdP chuyển đổi**. Trong khoảng overlap, SP giữ cả private key cũ và mới làm decryption credentials, nếu policy cho phép.
4. **Đưa public certificate mới vào IdP**, để IdP mã hóa CEK bằng khóa mới theo lịch chuyển đổi. Nếu IdP không thể lưu hai certificate, phối hợp thời điểm cutover và rollback cụ thể.
5. Kiểm thử Response mã hóa bằng **cả hai certificate** khi giai đoạn overlap đang được duyệt. Theo dõi lỗi unwrap/decrypt, issuer và audience validation.
6. Xác nhận IdP **không còn gửi ciphertext mã hóa bằng key cũ** và các phiên/response đang bay đã hết cửa sổ hợp lý.
7. **Gỡ khóa cũ** khỏi registration/keystore, ngừng công bố cert cũ, thu hồi hoặc lưu trữ ngoại tuyến theo chính sách. Không để key cũ online vô thời hạn chỉ vì một số request lỗi.
8. Có kế hoạch ứng cứu khi private key bị lộ: thu hồi/đổi key, thông báo IdP, điều tra ciphertext có thể bị giải mã, đánh giá dữ liệu nhạy cảm đã truyền.

### 14.1. Vì sao không xóa private key cũ ngay?

IdP có thể vẫn đang mã hóa theo certificate cũ trong metadata cache hoặc trong một phiên bản cấu hình chưa được đồng bộ. Nếu SP xóa key cũ trước khi IdP chuyển đổi, EncryptedKey không thể unwrap.

### 14.2. Vì sao không chỉ giữ mỗi khóa cũ?

Sau khi SP đã công bố cert mới, IdP có thể bắt đầu mã hóa bằng khóa mới. Nếu SP chưa tải private key mới, chính hệ thống SP không thể giải mã dữ liệu dành cho public cert mới mà mình vừa công bố.

**Thứ tự thực tế thường an toàn:** provision private key mới tại SP → công bố/đăng ký public cert mới tại IdP → chuyển IdP sang cert mới → giám sát → loại key cũ. Phải kiểm thử theo hành vi cụ thể của IdP, không suy rằng nó hỗ trợ nhiều certificate chỉ vì XML metadata có nhiều `KeyDescriptor`.

## 15. Lỗi giải mã thường gặp và cách phân tích

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra có ích |
| --- | --- | --- |
| `EncryptedAssertion` xuất hiện nhưng SP báo không có decryption key | Thiếu `decryption.credentials` của registration đúng | Kiểm tra credentials RP, không lấy nhầm IdP verification cert |
| Không unwrap được EncryptedKey | IdP mã hóa bằng public cert khác private key SP đang có | So fingerprint cert tại IdP với cert SP, kiểm tra rotation |
| `BadPaddingException`/khóa sai | RSA private key không khớp hoặc OAEP parameters/algorithm khác | Kiểm tra keypair và `EncryptionMethod` XMLSec, không thử downgrade |
| Không giải mã được AES content | CEK unwrap không đúng, IV/tag/thuật toán/dạng XML ciphertext không tương thích | Kiểm tra AES mode URI và XML Encryption profile với IdP |
| Tệp private key đọc lỗi | Sai đường dẫn, quyền, định dạng PKCS#1/PKCS#8, key password chưa hỗ trợ | Kiểm tra secret mount, converter và keystore |
| IdP giữ cert cũ sau rollover | Cert mới đã cấu hình SP, IdP vẫn mã hóa cho khóa cũ | Giữ overlap có hạn, đồng bộ IdP trước khi gỡ key cũ |
| `KeyName` trông đúng nhưng decrypt vẫn sai | KeyName chỉ là hint, không chứng minh keypair đúng | Kiểm tra public/private key thực và approved key ring |
| Decrypt được nhưng login vẫn bị từ chối | Assertion signature/issuer/audience/time không hợp lệ | Điều tra **validation layer**, không tắt chữ ký |
| Ký Assertion rồi mã hóa, SP cố verify assertion trước decrypt | Assertion signature bị mã hóa bên trong | Dùng response decrypter rồi assertion validation đúng thứ tự |
| Mã hóa attribute rồi ký Assertion, custom service giải mã trước verify | Thay XML nằm trong signed scope | Xác minh chữ ký assertion trước assertion-elements decryption |
| Sai lựa chọn registration đa IdP | Decryptor lấy key ring IdP/tenant khác | Kiểm tra registration resolver và request correlation |
| SAML Response gửi sai ACS | Destination/Recipient/public URL không đúng | Kiểm tra proxy, ACS metadata, registration |
| `EncryptedKey` ở chỗ khác với code tự viết | XML Encryption hỗ trợ nhiều cách liên kết key/data | Dùng OpenSAML XMLSec và profile được thỏa thuận |
| Gặp RSA v1.5 hoặc AES-CBC cũ | IdP/profile quá cũ | Đánh giá nâng chuẩn/interop theo policy; không hạ bảo mật vô điều kiện |
| Request gây CPU cao | Quá nhiều encrypted keys, candidate keys hoặc XML quá lớn | Giới hạn input, thuật toán, số lượt thử, timeout và memory |
| Log lộ assertion đã giải mã | Debug ghi XML toàn bộ, NameID/attributes | Tắt logging nội dung nhạy cảm; chỉ log mã lỗi và metadata an toàn |
| App dùng HSM nhưng converter muốn private key file | API loader không tương thích key storage | Dùng provider/adapter hỗ trợ HSM, không xuất key trái chính sách |

### 15.1. Không biến lỗi giải mã thành oracle

Nếu ứng dụng trả cho client các thông báo khác nhau kiểu “key A đúng”, “OAEP padding sai”, “AES tag đúng nhưng XML invalid”, attacker có thể sử dụng sự khác biệt làm **tín hiệu phân tích mật mã**. Với endpoint ACS công khai, nên trả lỗi xác thực thống nhất và lưu **mã phân loại nội bộ** (không chứa plaintext/key material) cho đội vận hành.

### 15.2. Không sửa bằng cách tắt encryption

Khi IdP đã yêu cầu encrypted assertion, việc bật chấp nhận plain assertion để “đăng nhập tạm” có thể làm lộ thuộc tính trên các tuyến xử lý/log hoặc vi phạm hợp đồng. Nếu muốn thay profile, phải đánh giá bảo mật và phối hợp cả IdP lẫn SP; không thay đổi ngầm.

## 16. Ma trận kiểm thử quan trọng

| Ca kiểm thử | Tình huống | Kết quả đúng |
| --- | --- | --- |
| Ciphertext hợp lệ | IdP mã hóa bằng SP cert hiện tại, SP có private key tương ứng | Giải mã, sau đó xác minh SAML; chỉ xác thực nếu mọi điều kiện hợp lệ |
| Thiếu private key | SP chỉ có certificate công khai | Fail closed, không nhận assertion |
| Private key không khớp | SP key cũ, IdP dùng public cert mới | Không giải mã được |
| Hai khóa giai đoạn rollover | IdP mã hóa bằng cert cũ hoặc mới, SP còn tin cả hai | Giải mã được cả hai trong overlap được phê duyệt |
| Đã thu hồi khóa cũ | Request mã hóa bằng cert cũ sau cutoff | Từ chối, không tự nạp lại khóa |
| `KeyName` giả | Hint yêu cầu khóa ngoài tập credential | Không truy cập secret ngoài allowlist, từ chối/không chọn |
| EncryptedKey ở vị trí khác | Cấu trúc được XML Encryption/SAML profile cho phép | Parser thư viện hỗ trợ hoặc từ chối rõ vì không tương thích |
| AES mode không được phép | XML đưa thuật toán không nằm trong policy | Từ chối |
| RSA v1.5 bị policy cấm | IdP gửi EncryptedKey dùng RSA v1.5 | Từ chối, không fallback |
| OAEP digest/MGF không khớp | Key đúng nhưng tham số khác | Từ chối/chẩn đoán thuật toán, không tắt validation |
| Ciphertext bị sửa | AES-GCM tag không khớp | Không giải mã thành plaintext tin cậy |
| Assertion tự mã hóa bởi attacker | Dùng public cert SP để tạo ciphertext mới | Decrypt có thể thành công; **signature/issuer policy phải từ chối** |
| Assertion có chữ ký hợp lệ nhưng audience sai | Nội dung giải mã dành cho SP khác | Từ chối |
| Assertion hết hạn | `NotOnOrAfter` đã qua | Từ chối |
| Recipient sai | `SubjectConfirmationData/Recipient` không phải ACS hợp lệ | Từ chối |
| Correlation sai | `InResponseTo` không khớp request khi profile yêu cầu | Từ chối |
| Ký rồi mã hóa | EncryptedAssertion chứa signed Assertion | Decrypt trước rồi verify chữ ký assertion |
| Mã hóa thuộc tính rồi ký | Signed Assertion có EncryptedAttribute | Verify assertion trước khi thay thuộc tính |
| Nhiều IdP | Response đến từ IdP B nhưng chọn registration A | Không xác thực nhầm; áp đúng registration/trust |
| Multi-tenant | Tenant A gửi hint khóa tenant B | Không mở rộng quyền truy cập key ring |
| XML độc hại | DTD/XXE, external reference hoặc XML rất lớn | Chặn/giới hạn, không giải mã tùy tiện |
| HSM lỗi | Remote decryptor không sẵn sàng | Fail an toàn, có cảnh báo; không lưu private key ra log |
| Key rotation chưa đồng bộ | IdP vẫn encrypt bằng cert cũ khi SP đã xóa key | Test fail, yêu cầu phục hồi đồng bộ theo kế hoạch |

Nên có integration test với **SAML IdP thật hoặc IdP giả lập có thể phát EncryptedAssertion**, không chỉ dùng unit test AES/RSA. Unit test Java trong bài chứng minh quan hệ keypair và tag; nó không chứng minh Spring Security đã validate đúng SAML.

## 17. Quy trình debug có kiểm soát trong môi trường thử nghiệm

Một quy trình chẩn đoán tránh lộ dữ liệu:

1. Xác nhận request đang đến endpoint ACS của **registration dự kiến**, không chỉ tên hiển thị nhà cung cấp.
2. Kiểm tra metadata SP đã xuất có **encryption certificate** mà IdP đang dùng, với fingerprint được đối chiếu qua cấu hình quản trị.
3. Xác nhận SP có **private key khớp** với cert ấy trong `decryption.credentials`, không chỉ certificate.
4. Kiểm tra định dạng key/cert và quyền filesystem/HSM; không in private key vào log.
5. Dùng công cụ phân tích SAML trong môi trường kiểm thử để xem **cấu trúc** `EncryptedAssertion`, `EncryptedKey` và thuật toán; tránh gửi assertion thật lên dịch vụ công cộng.
6. So sánh `EncryptionMethod` giữa IdP và policy hỗ trợ của OpenSAML/JCE; xem OAEP digest/MGF và content cipher.
7. Chọn lỗi thuộc **decryption** hay **SAML validation**. Nếu decrypt thành công nhưng assertion sai issuer/audience, cần sửa đúng metadata/trust/IdP chứ không động vào key.
8. Với rotation, đối chiếu certificate cũ/mới mà IdP đang thật sự sử dụng; kiểm tra cache metadata và cửa sổ overlap.
9. Kiểm tra thứ tự signed/encrypted elements nếu ứng dụng có custom decrypter.
10. Ghi evidence an toàn: registrationId, SP/IdP entityId ở mức được phép, thuật toán URI, fingerprint cert công khai, mã lỗi và thời gian; **không ghi plaintext assertion, NameID/attributes nhạy cảm hoặc CEK/private key**.

Khi xử lý sự cố trên production, không thử dump toàn bộ `SAMLResponse` ra console vì nó có thể chứa dữ liệu cá nhân hoặc assertion chưa giải mã có khả năng bị khai thác trong bối cảnh khác.

## 18. Checklist triển khai

- [ ] IdP và SP thống nhất rằng assertion phải được mã hóa, không nhầm với yêu cầu ký AuthnRequest.
- [ ] SP đã tạo keypair và certificate dành cho **decryption**; private key được bảo vệ tại SP.
- [ ] IdP đã import đúng **SP encryption certificate** gắn với đúng SP entityId và môi trường.
- [ ] `RelyingPartyRegistration` có đúng `decryptionX509Credentials`; không trộn với IdP verification cert.
- [ ] Thuật toán CEK transport (ví dụ RSA-OAEP) và content encryption (ví dụ AES-GCM) được hai bên hỗ trợ thực tế.
- [ ] Bộ xử lý chỉ chọn private key trong **key ring của registration tin cậy**, không tải/giải mã bằng khóa do `KeyInfo` tự chỉ.
- [ ] Không dùng NameID/email hoặc giá trị chưa giải mã để chọn tenant/private key.
- [ ] XML Encryption parser chặn XXE, external reference, thuật toán yếu và giới hạn tài nguyên.
- [ ] Đã phân biệt `EncryptedAssertion` với `EncryptedAttribute`/`EncryptedID` khi tùy chỉnh decrypter.
- [ ] Có đúng thứ tự **ký rồi mã hóa ⇒ giải mã rồi verify signature** đối với signed Assertion được mã hóa.
- [ ] Với encrypted attribute nằm trong signed Assertion, chữ ký được kiểm tra **trước khi** thay signed XML bằng plaintext.
- [ ] Sau giải mã, Spring Security vẫn thực hiện signature, issuer, audience, recipient, time, subject confirmation và request correlation/replay checks.
- [ ] Chấp nhận plain assertion hay encrypted assertion theo policy rõ ràng, không hạ bảo mật âm thầm.
- [ ] Rotation khóa có overlap hợp lệ và kế hoạch ngừng khóa cũ/rollback; có test với cả hai certificate.
- [ ] Private key, CEK và plaintext assertion không lọt vào source control, log, traces hoặc báo lỗi cho người dùng.
- [ ] Đã có integration/negative tests: sai key, wrong recipient, sai algorithm, ciphertext sửa, issuer/audience sai, XML malicious, multi-IdP.
- [ ] Có kế hoạch ứng phó nếu private key SP bị lộ hoặc IdP đổi certificate trước lịch.

## 19. Câu hỏi tự kiểm tra

**1. IdP dùng khóa nào để mã hóa assertion cho SP?**

Thông thường IdP sử dụng **public certificate của SP** và content key AES ngẫu nhiên. SP dùng **private key tương ứng** để unwrap content key và giải mã.

**2. SP có thể giải mã với certificate công khai nhưng không có private key không?**

Không. Public certificate là để IdP mã hóa; phần giải mã bất đối xứng cần private key tương ứng.

**3. `ds:KeyInfo` chứa KeyName `sp-2026` có đủ chứng minh phải tải khóa `sp-2026` không?**

Không. Nó chỉ là gợi ý từ thông điệp. SP được phép chọn **trong danh sách decryption credentials đã được cấu hình cho registration**, không tải khóa do request tự chỉ.

**4. Vì sao thường có cả EncryptedData và EncryptedKey?**

EncryptedData chứa ciphertext của XML assertion được mã hóa bằng AES; EncryptedKey chứa CEK đã được bọc bằng public key SP. Đó là thiết kế hybrid encryption phổ biến.

**5. Giải mã thành công có nghĩa là người dùng đã được xác thực?**

Không. Public key SP là công khai nên người không tin cậy cũng có thể tạo ciphertext. SP phải xác minh chữ ký IdP và điều kiện SAML độc lập.

**6. Spring Security giải mã EncryptedAssertion ở thời điểm nào?**

Theo tài liệu `OpenSaml5AuthenticationProvider`, decrypter cấp **Response** dùng cho `EncryptedAssertion`; assertion-elements decrypter dùng cho encrypted Attribute/ID ở bên trong Assertion.

**7. Nếu Assertion được ký rồi mã hóa, xác minh chữ ký assertion lúc nào?**

Sau khi **giải mã toàn bộ assertion** rồi khôi phục phần tử assertion chứa chữ ký; sau đó verify bằng key IdP đã tin.

**8. Nếu một Attribute được mã hóa trước khi Assertion được ký thì sao?**

Cần kiểm tra chữ ký assertion **trước khi giải mã và sửa đổi** XML chứa EncryptedAttribute, để không phá signed scope.

**9. Khi IdP chuyển sang certificate SP mới, SP cần làm gì?**

Giữ private key mới **trước khi** IdP mã hóa bằng certificate mới; có overlap khóa cũ/mới trong cửa sổ được phê duyệt, rồi loại khóa cũ đúng kế hoạch.

**10. IdP báo RSA-OAEP decrypt fail dù SP có private key đúng thì khả năng gì?**

Có thể sai tham số OAEP digest/MGF, ciphertext bị sửa, cert được IdP dùng thực tế không phải cert tương ứng, key format/proxy/profile sai, hoặc algorithm không được thư viện hỗ trợ.

**11. Có nên tự fallback sang RSA v1.5 hoặc AES-CBC khi AES-GCM/OAEP không hoạt động?**

Không được tự hạ bảo mật. Cần đối chiếu chính sách và khả năng interoperability, đánh giá rủi ro và có phê duyệt rõ ràng nếu phải hỗ trợ thuật toán legacy.

**12. Kiểm thử Java AES-GCM thành công đã đủ chứng minh SAML federation an toàn chưa?**

Chưa. Cần kiểm tra XML Encryption serialization và toàn bộ chữ ký/SAML Response validation của Spring Security với IdP thật và các negative cases.

## 20. Tài liệu chuẩn để đối chiếu

- Spring Security, **SAML 2.0 Login Overview** — `decryptionX509Credentials`, `Saml2X509Credential.decryption`, private key SP: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **Authenticating SAML Responses — Customizing Decryption** — `OpenSaml5AuthenticationProvider`, response/ assertion decrypters và thứ tự signature: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **Saml2X509Credential API** — credential types và factory `decryption(privateKey, certificate)`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2X509Credential.html
- Spring Boot, **SAML 2.0 Relying Party** — `decryption.credentials[*].private-key-location` / `certificate-location`: https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html
- OASIS, **SAML 2.0 Core** — `EncryptedAssertion`, XML Encryption và kết hợp chữ ký/mã hóa: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS, **SAML 2.0 Errata 05**, mục E43 — tham chiếu `EncryptedKey`/`EncryptedData`: https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html
- W3C, **XML Encryption Syntax and Processing 1.1** — cấu trúc `EncryptedData`, `EncryptedKey`, thuật toán: https://www.w3.org/TR/xmlenc-core1/
- OWASP, **SAML Security Cheat Sheet** — signature validation, XML wrapping và bảo mật federation: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Ghi nhớ:** `EncryptedAssertion` bảo vệ **tính bí mật**, không thay thế **xác thực**. IdP mã hóa bằng **public certificate SP**, SP giải mã bằng **private key SP phù hợp**, được lựa chọn từ **decryption credentials của registration đúng**; mọi `KeyInfo` chỉ là hint. Sau giải mã, Spring Security/OpenSAML vẫn phải xác minh **chữ ký IdP, issuer, audience, thời gian, recipient và các điều kiện SAML** trước khi người dùng được đăng nhập.