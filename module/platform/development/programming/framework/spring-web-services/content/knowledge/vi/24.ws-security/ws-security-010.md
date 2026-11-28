# Mã hóa, giải mã, thứ tự ký và mã hóa giữa hai phía

Trong một tích hợp SOAP doanh nghiệp, **mã hóa (encryption)** và **chữ ký số (digital signature)** trả lời hai câu hỏi khác nhau: *ai được phép đọc dữ liệu?* và *ai đã ký dữ liệu, dữ liệu có bị sửa không?*. Khi kết hợp chúng trên một SOAP message, thứ tự **ký rồi mã hóa** hoặc **mã hóa rồi ký** quyết định chính xác nội dung được ký, phần nào hiện ra trên đường truyền và bên nhận phải xử lý theo chính sách nào. Một cấu hình sai có thể khiến server giải mã được XML nhưng không xác minh chữ ký, hoặc chữ ký hợp lệ về mặt thuật toán nhưng không bao phủ phần XML mà endpoint sử dụng.

Bài học thuộc chương **WS-Security** của module `SPRING_WEB_SERVICES`. Theo hướng **contract-first**, XSD/WSDL xác định SOAP Body, request/response, endpoint và SOAP Fault; JAXB/OXM ánh xạ dữ liệu; `WebServiceTemplate` và `@Endpoint` tạo hai phía gửi/nhận; `Wss4jSecurityInterceptor` đảm nhiệm lớp bảo vệ thông điệp bằng **XML Signature, XML Encryption, X.509 và WS-Security**. TLS/mTLS, quyền truy cập tài nguyên, WS-Addressing, chứng chỉ và kiểm thử tương thích là các lớp liên quan nhưng **không tự thay thế** kiểm tra message security.

Các ví dụ hướng tới **Spring Web Services 4.1.x**, Apache WSS4J 2.x, Java 17+ và Jakarta JAXB. Chuẩn tham chiếu gồm OASIS Web Services Security, WSS X.509 Token Profile, WS-SecurityPolicy, W3C XML Signature/XML Encryption. **Không có một thứ tự chung luôn đúng cho mọi đối tác**: `SignBeforeEncrypting` và `EncryptBeforeSigning` là các lựa chọn policy; các bên phải thỏa thuận cụ thể và kiểm thử trên XML thực tế. Mẫu thuật toán, aliases và URI ở đây là minh họa; tuyệt đối không dùng mật khẩu/keystore mẫu trong production.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **integrity, authentication, confidentiality và authorization** trong SOAP message security.
2. Giải thích vai trò khóa **private signing key**, **public verification certificate**, **recipient public encryption key**, **recipient private decryption key** và trust anchors.
3. Mô tả `ds:Signature`, `ds:Reference`, `wsu:Id`, `xenc:EncryptedData`, `xenc:EncryptedKey` và `wsse:SecurityTokenReference` trong Envelope.
4. Vẽ đúng luồng **sign → encrypt** và **encrypt → sign**, cũng như cách bên nhận giải mã/xác minh theo policy.
5. Đọc ý nghĩa `securementActions` và `validationActions` của `Wss4jSecurityInterceptor`; không nhầm action tokens với các lệnh nghiệp vụ.
6. Cấu hình riêng SOAP **client** và **server** để request và response được ký/mã hóa bằng **khóa đúng hướng**.
7. Xác định **phần XML cần ký/mã hóa**, kiểm tra coverage và ngăn XML signature wrapping, thay đổi Header hoặc gửi nhầm dữ liệu.
8. Thiết kế truststore/keystore, AES/RSA-OAEP, certificate rotation, replay window, Timestamp và SOAP Fault an toàn.
9. Viết test tampering, sai key, sai thứ tự policy, thiếu chữ ký, lỗi giải mã, SOAP versions và tương thích Java/.NET.
10. Giải thích MTOM/attachments, SOAP intermediaries và WS-Addressing có thể ảnh hưởng thế nào tới phạm vi chữ ký/mã hóa.

## 1. Tình huống: hệ thống A gọi OrderService của hệ thống B

Giả sử bên **A** là SOAP client gửi `SubmitOrderRequest` chứa dữ liệu nhạy cảm cho bên **B** là Spring-WS server; B trả `SubmitOrderResponse` có thông tin đơn hàng. Contract-first định nghĩa:

~~~text
Namespace: urn:example:orders:v1

{urn:example:orders:v1}SubmitOrderRequest
{urn:example:orders:v1}SubmitOrderResponse
{urn:example:orders:v1}OrderFault

WSDL 1.1 operation: SubmitOrder
SOAP binding: 1.1 hoặc 1.2 theo hợp đồng
WS-SecurityPolicy: ký Body, mã hóa Body; Timestamp;
                   yêu cầu nhận diện signer và protection order
~~~

Ví dụ Body chưa bảo vệ:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:requestId>REQ-2030-015</ord:requestId>
  <ord:buyerId>BUYER-42</ord:buyerId>
  <ord:amount>1250000</ord:amount>
  <ord:currency>VND</ord:currency>
</ord:SubmitOrderRequest>
~~~

**Không** đưa nguyên `buyerId` và `amount` vào SOAP Fault hoặc logs nếu policy hạn chế. Khi A ký, chỉ A hoặc bên có khóa ký hợp lệ mới tạo được signature tương ứng; khi A mã hóa bằng public key của B, chỉ người nắm private decryption key tương ứng ở B mới có thể giải mã (theo mô hình thuật toán và quản lý khóa hợp lệ).

### 1.1. Những gì mỗi cơ chế cam kết

| Cơ chế | Cung cấp | Không tự cung cấp |
| --- | --- | --- |
| TLS | Bảo mật kênh giữa các điểm kết thúc TLS, xác minh server qua cert | Toàn vẹn message qua các proxy chấm dứt TLS hoặc lưu/truyền tiếp |
| mTLS | Xác thực client ở lớp TLS theo chứng chỉ | Tự ký từng SOAP element hay ký thay cho caller khác |
| XML Signature | Integrity của những `ds:Reference` được ký, nhận diện key signer | Confidentiality cho dữ liệu, ký tất cả các Header mặc định |
| XML Encryption | Bảo mật nội dung những phần được mã hóa, theo recipient keys | Bằng chứng sender đã ký hoặc được ủy quyền |
| WS-Security UsernameToken | Cơ chế mang/kiểm credential theo profile | Tự mã hóa Body; không thay SOAP signature policy |
| Timestamp + replay cache | Hạn chế replay trong cửa sổ thời gian khi cấu hình đúng | Exactly-once của một lệnh kinh doanh |
| Application authorization | Caller có quyền thực hiện operation trên `buyerId`? | Không thay kiểm tra signature/encryption |
| Idempotency key trong Body | Giảm rủi ro tạo đơn trùng với cùng intent khi server enforce | Không thay MessageID, Timestamp hoặc signature |

Một SOAP Body có XML đúng XSD **không chứng minh** caller tin cậy. Ngược lại, một signature hợp lệ **không chứng minh** amount nằm trong hạn mức nghiệp vụ hay caller có quyền tạo đơn.

### 1.2. Hai chiều trao đổi là hai lần bảo vệ riêng

~~~mermaid
sequenceDiagram
    autonumber
    participant A as SOAP Client A
    participant B as Spring-WS Server B
    A->>A: Ký bằng A private key
    A->>A: Mã hóa cho B public key
    A->>B: Secured SubmitOrderRequest
    B->>B: Giải mã bằng B private key
    B->>B: Xác minh chữ ký A + trust/coverage
    B->>B: XSD / authorization / application service
    B->>B: Ký response bằng B private key
    B->>B: Mã hóa response cho A public key
    B-->>A: Secured SubmitOrderResponse
    A->>A: Giải mã bằng A private key
    A->>A: Xác minh chữ ký B + trust/coverage
~~~

Mũi tên này mô tả **profile ký rồi mã hóa**. Nếu đối tác chọn mã hóa rồi ký thì thứ tự và đối tượng được ký thay đổi. Không thể dùng cùng `securementEncryptionUser` ở cả hai đầu: **request được mã hóa cho B**, còn **response được mã hóa cho A**.

## 2. Bốn loại khóa và vai trò trong hai chiều

### 2.1. Request A → B

| Việc | Key/certificate được dùng | Thực hiện bởi |
| --- | --- | --- |
| **Ký request** | A **private signing key** | A |
| **Xác minh request** | A **public cert/trust chain** | B |
| **Mã hóa request** | B **public encryption cert** | A |
| **Giải mã request** | B **private decryption key** | B |

### 2.2. Response B → A

| Việc | Key/certificate được dùng | Thực hiện bởi |
| --- | --- | --- |
| **Ký response** | B **private signing key** | B |
| **Xác minh response** | B **public cert/trust chain** | A |
| **Mã hóa response** | A **public encryption cert** | B |
| **Giải mã response** | A **private decryption key** | A |

Không nhầm “encrypt bằng private key” với chữ ký số: XML Signature sử dụng chữ ký bất đối xứng theo thuật toán đã thỏa thuận; XML Encryption thường dùng **session key đối xứng** để mã hóa data, rồi **public key của bên nhận** để bọc (transport/wrap) session key. `xenc:EncryptedKey` và `xenc:EncryptedData` liên quan nhau qua tham chiếu KeyInfo/reference. A không cần private encryption key của B để gửi request.

### 2.3. Keystore, truststore và Crypto

| Kho | Chứa gì | Dùng cho |
| --- | --- | --- |
| A signing keystore/HSM | A private signing key + certificate/chain | Tạo `ds:Signature` |
| B signature truststore/crypto | A trusted certificate/CA chain | Xác minh signer request |
| A encryption-recipient crypto | B public encryption cert/chain | Chọn recipient B |
| B decryption keystore/HSM | B private decryption key | Giải `EncryptedKey` |
| B signing keystore/HSM | B private signing key | Ký response |
| A signature truststore/crypto | B trusted signer cert/CA chain | Xác minh response |
| B encryption-recipient crypto | A public encryption cert | Mã hóa response cho A |
| A decryption keystore/HSM | A private decryption key | Giải mã response |

Một physical keystore có thể chứa nhiều entry hoặc cùng cặp key phục vụ hai vai trò nếu chính sách cho phép, nhưng **đừng gộp vai trò logic** trong thiết kế. Hãy giữ tên bean/alias rõ mục đích và bảo đảm certificate được phép dùng theo key usage/EKU/trust policy.

## 3. WS-Security dùng XML Signature và XML Encryption như thế nào?

SOAP security metadata thường nằm trong `<wsse:Security>` của **SOAP Header**, còn nội dung Body nhạy cảm có thể được thay bằng `<xenc:EncryptedData>` khi mã hóa.

### 3.1. Cấu trúc signature

Một **fragment mang tính sơ đồ**, không phải chữ ký có thể verify vì values đã bị lược:

~~~xml
<wsse:Security
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <wsu:Timestamp wsu:Id="TS-1">
    <wsu:Created>2030-01-01T01:00:00Z</wsu:Created>
    <wsu:Expires>2030-01-01T01:05:00Z</wsu:Expires>
  </wsu:Timestamp>

  <ds:Signature>
    <ds:SignedInfo>
      <ds:CanonicalizationMethod Algorithm="..."/>
      <ds:SignatureMethod Algorithm="..."/>
      <ds:Reference URI="#Body-1">
        <ds:Transforms>...</ds:Transforms>
        <ds:DigestMethod Algorithm="..."/>
        <ds:DigestValue>...</ds:DigestValue>
      </ds:Reference>
      <ds:Reference URI="#TS-1">
        <ds:Transforms>...</ds:Transforms>
        <ds:DigestMethod Algorithm="..."/>
        <ds:DigestValue>...</ds:DigestValue>
      </ds:Reference>
    </ds:SignedInfo>
    <ds:SignatureValue>...</ds:SignatureValue>
    <ds:KeyInfo>
      <wsse:SecurityTokenReference>...</wsse:SecurityTokenReference>
    </ds:KeyInfo>
  </ds:Signature>
</wsse:Security>
~~~

- `ds:Reference URI="#Body-1"` trỏ tới **node có ID đã được resolver nhận diện**, thường `wsu:Id` trên SOAP Body.
- `ds:DigestValue` kiểm content của reference sau transforms/canonicalization.
- `ds:SignatureValue` xác thực `SignedInfo` bằng khóa ký.
- `KeyInfo/SecurityTokenReference` chỉ ra cách tìm certificate/key (ví dụ BinarySecurityToken), **không có nghĩa certificate được tin cậy**.
- Một chữ ký hợp lệ chỉ bảo vệ những **reference thực sự được ký**; thêm một Header quan trọng mà chưa ký có thể tạo rủi ro đổi đích/operation.

Đừng tạo `ds:Signature` bằng cách nối chuỗi XML hoặc tự cài canonicalization. WSS4J/Santuario chịu trách nhiệm XML Signature; ứng dụng kiểm tra **phạm vi được ký, trust và node tiêu thụ** theo policy.

### 3.2. Cấu trúc encryption

Sơ đồ XML Encryption (giá trị giả):

~~~xml
<soap:Body
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:xenc="http://www.w3.org/2001/04/xmlenc#"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
    wsu:Id="Body-1">
  <xenc:EncryptedData Id="ED-1" Type="http://www.w3.org/2001/04/xmlenc#Content">
    <xenc:EncryptionMethod Algorithm="...AES-GCM..."/>
    <xenc:CipherData>
      <xenc:CipherValue>...base64-ciphertext...</xenc:CipherValue>
    </xenc:CipherData>
  </xenc:EncryptedData>
</soap:Body>
~~~

Ở một Header phần security, `xenc:EncryptedKey` có thể mang session key đã mã hóa bằng **recipient public key**:

~~~xml
<xenc:EncryptedKey xmlns:xenc="http://www.w3.org/2001/04/xmlenc#">
  <xenc:EncryptionMethod Algorithm="...RSA-OAEP..."/>
  <xenc:CipherData>
    <xenc:CipherValue>...wrapped-key...</xenc:CipherValue>
  </xenc:CipherData>
  <xenc:ReferenceList>
    <xenc:DataReference URI="#ED-1"/>
  </xenc:ReferenceList>
</xenc:EncryptedKey>
~~~

Đây là **fragment để hiểu cấu trúc**, không phải SOAP message đủ KeyInfo/WS-Security headers/algorithms để đem chạy. Khi mã hóa **Body content**, phần tử `soap:Body` còn tồn tại, các con được thay bằng `xenc:EncryptedData`; khi mã hóa **element**, cấu trúc thay thế khác. Mã hóa `content` và `element` có tác động khác nhau đến QName và khả năng định tuyến/validation, cần thống nhất với đối tác.

### 3.3. Một chữ ký và một ciphertext không đủ để tin message

Cần hỏi thêm:

- Chữ ký phủ **Body nào** và các Header `To`, `Action`, `MessageID`, `Timestamp` theo policy không?
- Bên nhận đang xác minh **chứng chỉ của ai**, chain trust và quyền sử dụng của signer?
- Recipient key có khớp private decryption key và đúng đối tác?
- Thuật toán có bị downgrade về RSA v1.5/SHA-1/3DES theo một cấu hình không an toàn không?
- SOAP Body mà JAXB xử lý có thực sự là **cùng node** được decrypt/verify không?
- WS-Security replay/cache và time window có được enforce?
- Message có MIME attachments nằm ngoài `ds:Reference`/`xenc:DataReference` không?

## 4. Ký trước rồi mã hóa: SignBeforeEncrypting

**`SignBeforeEncrypting`** là thứ tự mặc định trong **WS-SecurityPolicy 1.3 Protection Order** nếu policy áp dụng và không khai báo thứ tự khác. Về mặt ý nghĩa:

1. Tạo SOAP Body/Headers ở dạng **plaintext**.
2. Tính digest/canonicalization và tạo `ds:Signature` trên các phần cần ký.
3. Mã hóa Body/parts cần confidentiality bằng key/session key thích hợp.
4. Tùy policy, **mã hóa cả chữ ký** (signature protection), không chỉ Body.
5. Gửi SOAP security envelope đã bảo vệ.

~~~mermaid
flowchart LR
    A["Plain SOAP Body + signed Headers"] --> B["XML Signature bằng private key A"]
    B --> C["Encrypt Body/parts cho public key B"]
    C --> D["Nếu policy: Encrypt Signature"]
    D --> E["Wire SOAP message"]
~~~

### 4.1. Dữ liệu nào được ký?

Với sign-then-encrypt, **chữ ký được tính trên plaintext** của những nodes được chọn. Sau đó encryption có thể che plaintext. Bên nhận phải có khả năng giải mã phần được mã hóa để **khôi phục dữ liệu đã ký** và kiểm tra signature theo đúng references/transforms.

Không kết luận rằng chữ ký không tồn tại chỉ vì capture packet cho thấy Body là `EncryptedData`. Chữ ký có thể nằm trong `wsse:Security` và thậm chí chính chữ ký được mã hóa theo policy `EncryptSignature`.

### 4.2. Vì sao nhiều hệ thống chọn SignBeforeEncrypting?

- Signature có thể diễn tả integrity của **business payload sau khi giải mã**, gần với cách endpoint tiêu thụ XML.
- Hỗ trợ một số policy về **signature protection**, không công bố trực tiếp signature metadata nếu cần.
- Là default của WS-SecurityPolicy 1.3 khi dùng protection order property.
- Phù hợp khi hai phía có profile/policy được thống nhất và thử nghiệm.

Đổi lại, một trung gian không có decryption key có thể **không tự xác minh đầy đủ** signature bảo vệ plaintext; không thiết kế gateway “verify trước khi decrypt” theo cảm tính nếu profile sign-before-encrypt có encryption bao quanh signed contents.

### 4.3. Trường hợp dễ gây lỗi

Nếu A ký `<ord:SubmitOrderRequest>` nhưng B sau giải mã dùng một **node khác không nằm trong references**, chữ ký có thể được báo hợp lệ cho node gốc mà nghiệp vụ chạy trên node giả mạo — một dạng XML Signature Wrapping. Cần kiểm chính xác signed part coverage, ID uniqueness và tham chiếu tới node được endpoint map vào JAXB.

Một header `wsa:To` không được ký vẫn có thể bị sửa bởi intermediary; nếu server route theo To, hãy ký nó hoặc bảo vệ theo trust/transport policy đã review. Đừng tin “Body đã ký là mọi metadata đều an toàn”.

## 5. Mã hóa trước rồi ký: EncryptBeforeSigning

Với **`EncryptBeforeSigning`**, bảo vệ theo chiều khác:

1. Tạo plaintext SOAP Body/parts.
2. Mã hóa phần được chọn thành **ciphertext/EncryptedData** bằng public key của B.
3. Tính `ds:Signature` trên **ciphertext XML hiện có** hoặc các phần theo WS-SecurityPolicy.
4. Gửi message chứa encrypted parts và signature tương ứng.

~~~mermaid
flowchart LR
    A["Plain SOAP Body + headers"] --> B["Encrypt Body/parts cho public key B"]
    B --> C["Signature trên ciphertext bằng private key A"]
    C --> D["Wire SOAP message"]
~~~

### 5.1. Điểm khác so với sign-then-encrypt

| Thuộc tính | SignBeforeEncrypting | EncryptBeforeSigning |
| --- | --- | --- |
| Chữ ký tính trên | Plaintext của selected parts | Ciphertext của selected parts |
| Thứ tự tạo message | Sign → Encrypt | Encrypt → Sign |
| Bên nhận cần dữ liệu gì để verify? | Thường cần decrypt trước để truy cập signed plaintext | Có thể verify ciphertext trước decrypt khi references và policy phù hợp |
| Ai đọc plaintext? | Chỉ authorized recipient sau decrypt | Tương tự; signature trên ciphertext không làm lộ plaintext |
| Chữ ký có bị mã hóa không? | Có thể, tùy `EncryptSignature` policy | Chữ ký ngoài ciphertext thường còn hiển thị; policy khác có thể thêm bảo vệ |
| Lợi ích nổi bật | Ký nội dung nghiệp vụ dạng rõ trước khi mã hóa | Một verifier có thể kiểm integrity ciphertext không cần đọc plaintext |
| Cẩn trọng | Signatures/references sau decrypt | Verification đúng ciphertext và binding tới plaintext được xử lý |

Đây là khác biệt **khái niệm**, không phải sự bảo đảm rằng bất kỳ proxy nào cũng được verify khi không có recipient key. Khả năng verify trước decrypt phụ thuộc signature references, visibility của security tokens, thuật toán, policy và có bị mã hóa thêm hay không.

### 5.2. Không có thứ tự nào tự làm message “an toàn tuyệt đối”

- Sign-before-encrypt mà ký nhầm node vẫn không bảo vệ được dữ liệu JAXB thật.
- Encrypt-before-sign mà không verify đúng signer/trust vẫn không xác thực bên gửi.
- Chỉ encrypt một field nhạy cảm để lại Header chứa token/PII dạng rõ.
- Chữ ký trên ciphertext không bảo vệ Header không được tham chiếu.
- Không có replay protection thì một message đúng chữ ký vẫn có thể được phát lại.
- Không có TLS/hostname validation thì metadata/endpoint routing có thể rủi ro dù Body được mã hóa.

**Chọn thứ tự theo WSDL/WS-SecurityPolicy của đối tác và threat model**, không tự đổi vì một biến cấu hình có vẻ nhanh hơn.

### 5.3. Policy là hợp đồng, không phải đề xuất

WS-SecurityPolicy có các assertions điển hình:

~~~xml
<!-- Fragment minh họa; KHÔNG phải WS-Policy đầy đủ. -->
<sp:AsymmetricBinding
    xmlns:sp="http://docs.oasis-open.org/ws-sx/ws-securitypolicy/200702">
  <wsp:Policy xmlns:wsp="http://www.w3.org/ns/ws-policy">
    <sp:InitiatorToken>...</sp:InitiatorToken>
    <sp:RecipientToken>...</sp:RecipientToken>
    <sp:AlgorithmSuite>...</sp:AlgorithmSuite>
    <sp:Layout>...</sp:Layout>
    <sp:IncludeTimestamp/>
    <sp:SignBeforeEncrypting/>
    <sp:EncryptSignature/>
  </wsp:Policy>
</sp:AsymmetricBinding>
~~~

Những `...` chỉ là placeholder; fragment không thể dùng để parse/validate như policy thật. Tùy thiết kế, policy có thể dùng `sp:EncryptBeforeSigning` thay cho `sp:SignBeforeEncrypting`, quy định `SignedParts`/`EncryptedParts`, token inclusion, algorithm suite và protection của signature. Hãy kiểm phiên bản namespace WS-Policy/SecurityPolicy của đối tác trước khi áp dụng.


## 6. Bên nhận giải mã và xác minh theo thứ tự nào?

**Thứ tự tạo chữ ký/mã hóa** và **thứ tự cần xử lý để khôi phục/kiểm tra message** không phải cùng khái niệm. Phân tích mật mã:

| Policy phía gửi | Chuỗi tạo message | Chuỗi xử lý logic ở bên nhận | Điều kiện quan trọng |
| --- | --- | --- | --- |
| `SignBeforeEncrypting` | Ký plaintext → mã hóa signed parts | Giải mã phần liên quan → kiểm chữ ký của plaintext | Chỉ đưa plaintext cho nghiệp vụ **sau khi verify** |
| `EncryptBeforeSigning` | Mã hóa plaintext → ký ciphertext | Kiểm chữ ký trên ciphertext → giải mã | Verify đúng ciphertext/node mà sẽ được giải mã |
| Chỉ `Signature` | Ký selected parts | Verify signature/trust/coverage | Confidentiality không được cung cấp |
| Chỉ `Encrypt` | Encrypt selected parts | Decrypt với private key | Không có bằng chứng chữ ký nguồn gửi |
| `Timestamp Signature Encrypt` | Tạo Timestamp rồi ký/mã hóa theo profile | Kiểm timestamp/replay, decrypt/verify theo profile | Chữ ký cần phủ Timestamp nếu hợp đồng yêu cầu |

Trong Spring-WS/WSS4J, **không triển khai logic bằng cách tự gọi hàm `decrypt()` rồi `verify()` trong `@Endpoint`**. WSS4J phân tích `wsse:Security`, XML Encryption references, chữ ký và các security actions; phía server phải cấu hình `validationActions` và Crypto/callback đúng. Bảng mô tả *phụ thuộc logic giữa các phép bảo vệ*, không khẳng định thứ tự `validationActions` luôn là **đảo ngược** chuỗi `securementActions`.

### 6.1. Vì sao không đảo chuỗi action một cách máy móc?

Ví dụ bên A cấu hình:

~~~text
securementActions = "Timestamp Signature Encrypt"
~~~

Một cách suy luận dễ sai:

~~~text
Server validationActions = "Encrypt Signature Timestamp"
~~~

**Không nên** copy chuỗi đảo chiều đó như công thức. Spring-WS nói rõ thứ tự action phía gửi được kiểm tra với `validationActions` phía nhận theo các security results mà WSS4J tạo. Thứ tự trong cấu hình **phải phản ánh profile và WSS4J receiver behavior**; engine nội bộ có thể decrypt để kiểm tra chữ ký nhưng kết quả actions được đối chiếu theo chính sách, không nhất thiết theo thứ tự phép biến đổi mật mã thủ công. Vì vậy cần:

1. Thỏa thuận outbound protection order và signed/encrypted parts.
2. Cấu hình `validationActions` theo **action sequence mong đợi từ sender** và behavior phiên bản WSS4J.
3. Test thông điệp ký/mã hóa thật với certificate/algorithms của hai phía.
4. Đọc lỗi WSS4J/signed references để sửa order/policy, không “sửa bằng cách tắt check”.
5. Kiểm thêm **coverage**: việc có action `Signature` không đủ nếu signature ký node sai.

Ở ví dụ cấu hình các mục tiếp theo, ta chọn hai chiều có profile `Timestamp Signature Encrypt`; **phải kiểm thử** với WSS4J/provider và đối tác thực tế theo WSDL/WS-SecurityPolicy.

### 6.2. Đừng xử lý nghiệp vụ trên dữ liệu chưa verify

~~~mermaid
flowchart TD
    A["Inbound SOAP over TLS"] --> B["MIME / XML parser an toàn"]
    B --> C["WSS4J: xử lý XML Encryption / Signature"]
    C --> D{"Keys, algorithms, signature, trust hợp lệ?"}
    D -- "Không" --> E["Reject / SOAP security fault an toàn"]
    D -- "Có" --> F{"Timestamp, replay và signed coverage đúng?"}
    F -- "Không" --> E
    F -- "Có" --> G["XSD validation + JAXB mapping"]
    G --> H{"Authorization/business rules đúng?"}
    H -- "Không" --> I["Business/authorization SOAP fault"]
    H -- "Có" --> J["@Endpoint → application service"]
~~~

Một SOAP Fault có thể phát sinh **trước khi endpoint mapping tìm ra method**, hoặc từ security interceptor trước application layer; không ép mọi lỗi về một exception resolver nghiệp vụ duy nhất.

## 7. Spring-WS: securementActions và validationActions

### 7.1. `Wss4jSecurityInterceptor` làm hai nhiệm vụ

`org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor` thực hiện hai nhóm:

| Cấu hình | Sử dụng khi | Vai trò |
| --- | --- | --- |
| `setSecurementActions(...)` | **Outgoing**: client request hoặc server response | Chuỗi `Timestamp Signature Encrypt` |
| `setValidationActions(...)` | **Incoming**: server request hoặc client response | Kiểm security action chain |
| `setSecurementSignatureCrypto(...)` | Signing outbound | Crypto có private signing key của local sender |
| `setSecurementSignatureUser(...)` | Signing outbound | Keystore alias của signer |
| `setSecurementPassword(...)` | Signing/key securement | Passphrase private key từ secret manager |
| `setSecurementEncryptionCrypto(...)` | Encrypt outbound | Crypto với **recipient public certificate** |
| `setSecurementEncryptionUser(...)` | Encrypt outbound | Public cert alias của recipient |
| `setValidationSignatureCrypto(...)` | Verify incoming | Peer signer trust/cert crypto |
| `setValidationDecryptionCrypto(...)` | Decrypt incoming | Local private decryption key |
| `setValidationCallbackHandler(...)` | Decrypt incoming | Truy xuất private key passphrase |
| `setSecurementSignatureParts(...)` | Sign outgoing | QName Body, Timestamp, Header theo policy |
| `setSecurementEncryptionParts(...)` | Encrypt outgoing | QName Content/Element được bảo vệ |
| `setValidationReplayCache(...)` | Validate incoming | Cache nonce/timestamp/replay theo WSS4J |

Cả **client** lẫn **server** đều có outgoing và incoming. **Đừng** chỉ đặt `securementActions` trên server rồi mong client request tự được ký. Đăng ký bean vào `WebServiceTemplate.setInterceptors(...)` cho client và vào endpoint interceptor chain cho server là những bước **khác nhau**.

### 7.2. Validation action `Encrypt` nghĩa là decrypt

~~~text
Outgoing setSecurementActions("Signature Encrypt")
  Signature  → ký outgoing message
  Encrypt    → mã hóa outgoing message

Incoming setValidationActions("Signature Encrypt")
  Signature  → xác minh chữ ký từ peer
  Encrypt    → giải mã incoming message
~~~

`Encrypt` trong `validationActions` **không khiến receiver mã hóa incoming request lần nữa**. Nó mô tả một action phải xử lý khi incoming message đã được mã hóa. Tương tự `Signature` trong validation **không ký lại** message mà verify signature.

### 7.3. Action names, order và strict checking

- Spring-WS nhận **chuỗi actions cách nhau bằng khoảng trắng**; ví dụ `"Timestamp Signature Encrypt"`.
- WSS4J kiểm message có những security actions yêu cầu theo **thứ tự chính sách**; sai order có thể bị reject.
- Spring-WS **4.1.4** có `setStrictActionChecking(boolean)`; mặc định kiểm action nghiêm ngặt; có thể cho extra actions khi tắt, **không đồng nghĩa cho thiếu chữ ký**. Không tắt chỉ để vượt lỗi cấu hình.
- `setBspCompliant(boolean)` mặc định **true**; tắt có thể làm giảm tính tuân thủ WS-I Basic Security Profile.
- `setAllowRSA15KeyTransportAlgorithm(boolean)` mặc định **false** theo Spring-WS 4.1.x; không bật RSA PKCS#1 v1.5 chỉ để bỏ qua khả năng dùng RSA-OAEP.
- Nếu peer chuyển algorithm suite, kiểm cả signing, digest, encryption, key transport và trust; không chỉ sửa chuỗi action.

### 7.4. Bốn hướng action trong request-response

~~~text
A → B request:
  A outgoing securementActions
  B incoming validationActions

B → A response:
  B outgoing securementActions
  A incoming validationActions
~~~

Một SOAP Fault response từ B có thể cũng phải được bảo vệ theo **fault policy**. Tuy nhiên, lỗi security rất sớm (khi recipient chưa xác minh peer hoặc không thể mã hóa theo key của client) có thể có fallback/fault transport đặc thù; không hứa mọi Fault đều được ký/mã hóa giống success response.

## 8. Spring-WS client: ký request và mã hóa cho server

Một bean cấu hình **phía A** minh họa API Spring-WS 4.1.x. `Crypto` là `org.apache.wss4j.common.crypto.Crypto`, có thể lấy từ `CryptoFactoryBean` hoặc nhà cung cấp khóa phù hợp. `OrderKeySecrets` là interface ứng dụng **giả định**, kết nối secret manager thay vì hardcode password.

~~~java
import javax.security.auth.callback.CallbackHandler;
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration(proxyBeanMethods = false)
public class OrdersClientSecurityConfig {

    @Bean
    Wss4jSecurityInterceptor ordersClientWss4j(
            @Qualifier("clientSigningCrypto") Crypto ownSigning,
            @Qualifier("serverEncryptionCrypto") Crypto serverPublic,
            @Qualifier("serverSignatureTrustCrypto") Crypto serverTrust,
            @Qualifier("clientDecryptionCrypto") Crypto ownDecrypt,
            @Qualifier("clientKeyCallback") CallbackHandler decryptHandler,
            OrderKeySecrets secrets) {

        var security = new Wss4jSecurityInterceptor();

        // Bảo vệ request A -> B: timestamp, sign, encrypt.
        security.setSecurementActions("Timestamp Signature Encrypt");
        security.setSecurementSignatureUser("client-signing");
        security.setSecurementSignatureCrypto(ownSigning);
        security.setSecurementPassword(
            secrets.clientSigningKeyPassword());

        // Public cert B: A không cần private key B.
        security.setSecurementEncryptionUser("server-encryption");
        security.setSecurementEncryptionCrypto(serverPublic);

        // Kiểm response B -> A.
        security.setValidationActions("Timestamp Signature Encrypt");
        security.setValidationDecryptionCrypto(ownDecrypt);
        security.setValidationSignatureCrypto(serverTrust);
        security.setValidationCallbackHandler(decryptHandler);

        // Nếu muốn ký Timestamp và WS-A Headers,
        // phải khai báo explicit signed parts (mục 10).
        return security;
    }
}
~~~

**Giới hạn ví dụ:** mặc định WSS4J ký/mã hóa SOAP Body nếu không chỉ định parts; một `Timestamp` action xuất hiện trong message nhưng **chưa chắc đã được ký**. `OrderKeySecrets` là dependency cần viết trong ứng dụng; password không được commit vào source/log. `clientSigningCrypto` có private signing key A; `serverEncryptionCrypto` có public certificate B; `serverSignatureTrustCrypto` xác minh signature B; `clientDecryptionCrypto` có private decryption key A; `clientKeyCallback` cung cấp passphrase cho private decryption key theo policy.

Bean này **chưa tự** được đăng ký trên template. Ví dụ:

~~~java
@Bean
WebServiceTemplate ordersClientTemplate(
        Jaxb2Marshaller marshaller,
        @Qualifier("ordersClientWss4j")
        Wss4jSecurityInterceptor security) {

    WebServiceTemplate template =
        new WebServiceTemplate(marshaller);
    template.setDefaultUri(
        "https://orders.partner.example.test/soap");
    template.setInterceptors(
        new ClientInterceptor[] { security });
    return template;
}
~~~

Cần import `org.springframework.ws.client.core.WebServiceTemplate`, `org.springframework.ws.client.support.interceptor.ClientInterceptor` và `org.springframework.oxm.jaxb.Jaxb2Marshaller`. Các bean cần được cấu hình **trước khi sử dụng**; không đổi `securementEncryptionUser` hoặc keystore khi có concurrent requests. Nếu có nhiều security profiles/tenants, hãy tách template/interceptor/sender hoặc dùng cơ chế per-invocation đã được xác minh an toàn luồng.

### 8.1. CryptoFactoryBean và decryption callback

Theo Spring-WS API, `CryptoFactoryBean` có thể tạo Crypto từ keystore. Fragment XML minh họa:

~~~xml
<!-- Fragment Spring XML: EXTERNAL_SECRET không phải mật khẩu thật. -->
<bean id="clientSigningCrypto"
      class="org.springframework.ws.soap.security.wss4j2.support.CryptoFactoryBean">
  <property name="keyStoreLocation"
            value="file:/secure/keystores/client-signing.p12"/>
  <property name="keyStorePassword" value="EXTERNAL_SECRET"/>
  <property name="keyStoreType" value="PKCS12"/>
</bean>
~~~

Đường dẫn/alias/type/certificate trust constraints cần được provision và kiểm chứng; fragment không tự kết nối secret manager hay tổ chức key rotation. `org.springframework.ws.soap.security.wss4j2.callback.KeyStoreCallbackHandler` có `setPrivateKeyPassword(...)` giúp WSS4J mở private decryption key; theo security requirements có thể thay bằng handler/HSM phù hợp.

### 8.2. Chọn thuật toán an toàn theo profile

~~~java
security.setSecurementEncryptionKeyTransportAlgorithm(
    "http://www.w3.org/2001/04/xmlenc#rsa-oaep-mgf1p");
~~~

URI trên đại diện **key transport RSA-OAEP**, **không phải AES content encryption**. `setSecurementEncryptionSymAlgorithm(...)`, `setSecurementSignatureAlgorithm(...)` và `setSecurementSignatureDigestAlgorithm(...)` là những cấu hình **riêng**, phải dùng algorithm suite mà peer hỗ trợ. Ưu tiên các lựa chọn hiện đại như SHA-256+, AES thích hợp (AEAD như AES-GCM khi profile được hỗ trợ), RSA-OAEP và key lengths đủ mạnh. Không quay lại SHA-1/3DES/RSA1.5 chỉ vì môi trường test cũ dễ chạy.

### 8.3. Decrypt được không chứng minh người gửi

A có private key để decrypt response gửi cho mình, nhưng **không chứng minh B đã gửi response**. A phải xác minh signature của B, trust chain/identity, đúng các parts đã ký và time window/replay theo policy. Tương tự, B decrypt request của A không có nghĩa A được phép đặt hàng.


## 9. Spring-WS server: giải mã request và ký response

Phía **B** phải thực hiện bốn việc **theo đúng vai trò khóa**:

- Inbound request A → B: dùng **B private decryption key** và xác minh chữ ký bằng **A trusted signer certificate**.
- Outbound response B → A: ký bằng **B private signing key** và mã hóa bằng **A public encryption certificate**.

Một Spring bean phía server:

~~~java
import javax.security.auth.callback.CallbackHandler;
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration(proxyBeanMethods = false)
public class OrdersServerSecurityConfig {

    @Bean
    Wss4jSecurityInterceptor ordersServerWss4j(
            @Qualifier("clientSignatureTrustCrypto") Crypto clientTrust,
            @Qualifier("serverDecryptionCrypto") Crypto ownDecrypt,
            @Qualifier("serverKeyCallback") CallbackHandler decryptHandler,
            @Qualifier("serverSigningCrypto") Crypto ownSigning,
            @Qualifier("clientEncryptionCrypto") Crypto clientPublic,
            OrderKeySecrets secrets) {

        var security = new Wss4jSecurityInterceptor();

        security.setValidationActions("Timestamp Signature Encrypt");
        security.setValidationSignatureCrypto(clientTrust);
        security.setValidationDecryptionCrypto(ownDecrypt);
        security.setValidationCallbackHandler(decryptHandler);

        security.setSecurementActions("Timestamp Signature Encrypt");
        security.setSecurementSignatureUser("server-signing");
        security.setSecurementSignatureCrypto(ownSigning);
        security.setSecurementPassword(
            secrets.serverSigningKeyPassword());

        security.setSecurementEncryptionUser("client-encryption");
        security.setSecurementEncryptionCrypto(clientPublic);
        return security;
    }
}
~~~

Code chỉ **khai báo bean**, chưa tự đăng ký vào endpoint interceptor chain. Với `@EnableWs`/Spring configuration, có thể thêm interceptor qua `WsConfigurer.addInterceptors(List<EndpointInterceptor>)` hoặc cấu hình endpoint mappings phù hợp. Phải kiểm thứ tự hoạt động với XML validation, security, business authorization và logging. Không để `@Endpoint` truy cập plaintext chưa được xác thực.

### 9.1. Đối chiếu các bean Crypto

| Phía A | Phía B | Tác dụng |
| --- | --- | --- |
| `clientSigningCrypto` | `clientSignatureTrustCrypto` | B kiểm chữ ký request A |
| `serverEncryptionCrypto` | `serverDecryptionCrypto` | A encrypt cho B, B decrypt |
| `serverSignatureTrustCrypto` | `serverSigningCrypto` | A kiểm chữ ký response B |
| `clientDecryptionCrypto` | `clientEncryptionCrypto` | B encrypt cho A, A decrypt |

Mỗi bean name là **vai trò logic**, không có nghĩa phải có 8 tệp keystore riêng. Cặp signing key và encryption key có thể cùng hoặc khác nhau theo chính sách, nhưng private keys chỉ nằm ở owner phù hợp; certificate công khai có thể phân phối cho peer qua kênh xác thực.

### 9.2. Request và response có thể yêu cầu profile khác nhau

~~~text
Request A -> B:
  Signed + encrypted Body, signed Timestamp và WS-Addressing

Response B -> A:
  Signed Body + Timestamp, có thể mã hóa nếu chứa PII
~~~

Đây chỉ là **ví dụ về sự khác biệt profile**; không áp dụng nếu WS-SecurityPolicy yêu cầu encrypt response. Với SOAP Fault, có thể phải ký/mã hóa để giữ confidentiality của fault detail. Nhưng lỗi trước khi xác minh danh tính/recipient cert có thể chỉ cho phép thông báo từ chối tối thiểu hoặc transport error.

### 9.3. Đăng ký security ở hai nơi khác nhau

- Client A: `Wss4jSecurityInterceptor` phải nằm trong `WebServiceTemplate.setInterceptors(...)`; outgoing request securement và incoming response validation.
- Server B: interceptor nằm ở tầng `EndpointInterceptor` của Spring-WS; incoming request validation và outgoing response securement.
- Nếu cùng một process vừa nhận vừa gọi SOAP (gateway), tách bean và alias theo security profile; không thay `securementUsername`, private key, encryption recipient trong singleton bean giữa nhiều requests.
- `CallbackHandler` và secret provider tùy biến cũng phải thread-safe, không để currentTenant/currentPassword là mutable field.

## 10. Phạm vi ký/mã hóa: Body, Timestamp và WS-Addressing

WSS4J có thể báo **signature valid** với một `ds:Reference` hợp lệ nhưng **không phải phần XML ứng dụng đang xử lý**. Vì thế phải thiết kế **signed/encrypted parts** cùng với thứ tự actions.

### 10.1. Cú pháp cấu hình parts

`setSecurementSignatureParts(String)` và `setSecurementEncryptionParts(String)` dùng danh sách phần tử cách nhau bằng dấu `;`:

~~~text
{mode}{namespaceURI}LocalName
~~~

- Với encryption, `{Content}` mã hóa **nội dung** và `{Element}` mã hóa **cả phần tử**; mặc định mode là Content nếu không ghi.
- Với signature, phần `{}` đầu thường trống, rồi namespace URI và local name: `{}{namespaceURI}LocalName`.
- `namespaceURI` là URI mở rộng, **không phải prefix** XML như `soap:` hoặc `wsu:`.
- Các phần tử và namespace phân biệt hoa/thường.
- SOAP 1.1 và 1.2 có namespace khác; phải lựa chọn dựa trên binding.

### 10.2. SOAP 1.1: ký Body và Timestamp

~~~java
String SOAP11 = "http://schemas.xmlsoap.org/soap/envelope/";
String WSU =
    "http://docs.oasis-open.org/wss/2004/01/"
  + "oasis-200401-wss-wssecurity-utility-1.0.xsd";

security.setSecurementSignatureParts(
    "{}{" + SOAP11 + "}Body;"
  + "{}{" + WSU + "}Timestamp");

security.setSecurementEncryptionParts(
    "{Content}{" + SOAP11 + "}Body");
~~~

Nếu policy yêu cầu **SignedTimestamp**, phải bảo đảm `Timestamp` thực sự nằm trong signature references. Chỉ thêm `"Timestamp"` vào `securementActions` **không đồng nghĩa timestamp được ký**. Bên nhận không chỉ kiểm có timestamp mà còn phải enforce required coverage theo policy.

### 10.3. SOAP 1.2 và các header ảnh hưởng routing

Với SOAP 1.2:

~~~java
String SOAP12 = "http://www.w3.org/2003/05/soap-envelope";
~~~

Nếu dùng **WS-Addressing 1.0**, có thể cần ký `Action`, `To` và `MessageID` ngoài Body/Timestamp:

~~~java
String WSA = "http://www.w3.org/2005/08/addressing";

security.setSecurementSignatureParts(
    "{}{" + SOAP12 + "}Body;"
  + "{}{" + WSU + "}Timestamp;"
  + "{}{" + WSA + "}Action;"
  + "{}{" + WSA + "}To;"
  + "{}{" + WSA + "}MessageID");
~~~

Tùy contract, cần ký thêm `ReplyTo`, `FaultTo`, `RelatesTo` hoặc các headers phân quyền quan trọng. **Chỉ định đúng part tên mà sender biết** là chưa đủ: receiver phải validate references, uniqueness, coverage và ứng dụng phải tiêu thụ **đúng các nodes đã được ký**.

Lưu ý thứ tự interceptor: nếu WSS4J đã ký `wsa:To` rồi một callback/gateway thay `To` sau đó, signature verification sẽ lỗi. Nếu security chạy trước khi WS-Addressing Header được tạo, Header có thể bị bỏ khỏi signature. Chạy wire tests để xác nhận.

### 10.4. Content và Element encryption khác nhau

| Mode | Cái bị thay | Điều cần để ý |
| --- | --- | --- |
| `{Content}` | Nội dung bên trong element | Parent/attributes có thể vẫn thấy |
| `{Element}` | Cả element | QName không còn hiển thị trước decrypt |
| Chỉ ký Body | Dữ liệu vẫn ở dạng rõ | Không đáp ứng confidentiality |
| Chỉ mã hóa Body | Sender chưa được authenticated bởi chữ ký | Không đáp ứng yêu cầu signer identity |

SOAP Body Content encryption thường giữ node `soap:Body` và thay nội dung con bằng `xenc:EncryptedData`. Nếu mã hóa cả root element nghiệp vụ hoặc headers, kiểm mapping/decryption pipeline: những thành phần dispatch/validator chạy **trước khi decrypt** có thể không đọc được PayloadRoot và gây lỗi không tìm thấy endpoint.

### 10.5. Chống XML Signature Wrapping

Một lỗi tinh vi xảy ra khi attacker chèn **node đã được ký** vào vị trí khác, đồng thời đặt một **payload không ký** vào đúng nơi endpoint tìm kiếm. Verifier có thể báo chữ ký hợp lệ của node thứ nhất, nhưng JAXB nhận node thứ hai.

~~~xml
<!-- Sơ đồ tấn công, không phải SOAP Envelope hoàn chỉnh. -->
<soap:Header>
  <ord:SubmitOrderRequest wsu:Id="SignedPayload-1">
    <!-- Nội dung có chữ ký hợp lệ -->
  </ord:SubmitOrderRequest>
</soap:Header>
<soap:Body>
  <ord:SubmitOrderRequest>
    <!-- Nội dung khác, KHÔNG nằm trong signature -->
  </ord:SubmitOrderRequest>
</soap:Body>
~~~

Phòng vệ bắt buộc:

1. Reject duplicate/ambiguous `wsu:Id` và unexpected Body/Header elements.
2. Resolve signature references bằng namespace-aware secure XML parser, không dùng XPath chỉ theo `local-name()`.
3. Enforce coverage của Body/Headers đúng policy, không chỉ `Signature` action tồn tại.
4. Bảo đảm node JAXB/endpoint đọc **chính là node đã được xác minh**.
5. Kiểm signer trust và authorization trên đúng operation/tenant.
6. Test chủ động với SOAP message có signed decoy + unsigned business payload.

### 10.6. Attachment/MTOM không được ký tự động trong mọi profile

Nếu Body dùng `xop:Include href="cid:..."` hoặc SOAP with Attachments, XML Body signature có thể không bảo vệ bytes MIME theo mong đợi. WSS4J hỗ trợ ký/mã hóa attachments qua callback và đúng SwA profile (có selector `cid:Attachments` cho tất cả attachments trong WSS4J); Spring-WS 4.1.x có `setAttachmentCallbackHandler(...)`. **Không** kết luận chỉ ký Body là đủ để bảo vệ tài liệu nhị phân, Content-ID, MIME headers và nội dung attachment.

Nội dung/chính sách phải được xác minh bằng tamper tests với binary MIME part. Nếu đối tác Java/.NET dùng MTOM kèm WS-Security, phải thử đúng phiên bản WSS4J/provider, vì serialization và reference transforms có thể khác.


## 11. Chứng chỉ, trust và vòng đời khóa

### 11.1. Chứng chỉ trong WS-Security Header không tự đáng tin

Một `wsse:BinarySecurityToken` có thể mang X.509 certificate để verifier tìm public key. Nhưng **certificate xuất hiện trong SOAP không tự biến nó thành trusted signer**. Bên nhận phải kiểm:

- Certificate chain tới CA/pinned certificate theo chính sách.
- `NotBefore`/`NotAfter`, kích thước và thuật toán khóa, key usage/EKU.
- Signer identity/subject/issuer/serial/SKI có thuộc **đúng partner/tenant** không.
- Revocation (CRL/OCSP) khi policy yêu cầu.
- Đối tác ký hợp lệ **có quyền** thực hiện operation với `buyerId` này không.
- Rotation: chấp nhận cert cũ/mới có giới hạn khi thay đổi.

Một truststore chứa CA chung có thể tin nhiều certificates; vẫn cần ánh xạ signer identity tới role/resource authorization riêng. `validationSignatureCrypto` không thay toàn bộ authorization policy.

### 11.2. mTLS và WS-Security X.509 bảo vệ khác nhau

| Tiêu chí | TLS/mTLS | XML Signature/XML Encryption |
| --- | --- | --- |
| Phạm vi | Kênh giữa các điểm kết thúc TLS | Những SOAP XML parts được chọn |
| Identity | Server cert, tùy cấu hình có client cert | Signer/recipient cert theo WS-Security |
| Proxy chấm dứt TLS | Kênh cũ đã kết thúc | Message signature có thể đi qua mà vẫn verify |
| Confidentiality | Kênh TLS | EncryptedData cho những phần nhạy cảm |
| Kiểm quyền nghiệp vụ | Không tự có | Không tự có |
| Chống replay nghiệp vụ | Không tự có | Timestamp/replay cache vẫn khác idempotency |

Ngay cả khi TLS và WS-Security dùng **cùng certificate**, việc xác minh chain, identity và purpose ở từng lớp vẫn khác nhau.

### 11.3. Private key và secret management

- Private signing key chỉ nằm phía signer; private decryption key chỉ ở recipient/HSM/KMS được ủy quyền.
- Không commit `keyStorePassword`/`securementPassword` hoặc private keys vào repository/YAML/logs/SOAP Fault.
- Hạn chế ACL của keystore, container volume, user account và HSM access.
- Dùng aliases rõ như `client-signing`, `server-decryption`; không dùng cert cùng alias một cách tùy tiện.
- Callback handler phải thread-safe; không chứa `currentTenantPassword` mutable dùng chung.
- Rotation phải được thực hiện qua cấu hình/profile mới và drain requests cũ, không sửa singleton interceptor giữa concurrent requests.

### 11.4. Thuật toán bảo vệ

| Nhóm | Lựa chọn có thể phù hợp | Lưu ý |
| --- | --- | --- |
| XML Signature | RSA-SHA256 hoặc thuật toán hiện đại do peer hỗ trợ | Tránh SHA-1/MD5 nếu không có exception được đánh giá |
| Digest | SHA-256+ | Kiểm `ds:DigestMethod` thực tế |
| XML Encryption content | AES theo algorithm suite; AES-GCM khi support | CBC cần integrity/anti-oracle controls |
| Key transport | RSA-OAEP | Tránh RSA v1.5; `allowRSA15` default false |
| TLS | TLS 1.2+/1.3 theo đối tác | Không thay XML message protection |
| X.509 | Cert chain, revocation, key usage/identity | Certificate hợp lệ ≠ authorized |

`setSecurementEncryptionKeyTransportAlgorithm(...)` cấu hình cách bảo vệ **session key**, không phải thuật toán nội dung. `setSecurementEncryptionSymAlgorithm(...)` cấu hình data encryption. `setSecurementSignatureAlgorithm(...)` và `setSecurementSignatureDigestAlgorithm(...)` quyết định chữ ký và digest; phải so các Algorithm URIs trên wire với policy, không chỉ nhìn setter.

### 11.5. Rotation phía gửi và nhận

~~~mermaid
flowchart TD
    A["Partner công bố cert mới"] --> B["Xác minh fingerprint/chain qua kênh tin cậy"]
    B --> C["Provision trusted signer + encryption public cert"]
    C --> D["Test old/new keys trong staging"]
    D --> E["Chuyển profile và drain phiên cũ"]
    E --> F["Theo dõi signature/decrypt failures"]
    F --> G["Thu hồi cert cũ theo lịch"]
~~~

Nếu B đổi private encryption key mà A vẫn encrypt bằng public cert cũ, B có thể không decrypt được request. Nếu B đổi signing cert mà A chưa trust, A có thể decrypt response nhưng **verification fail**. Hai sự cố có triệu chứng khác nhau.

## 12. Timestamp, replay protection và ranh giới tin cậy

### 12.1. Timestamp phải được xác minh và ký khi policy yêu cầu

`wsu:Timestamp` thường có `Created`/`Expires`; Spring-WS/WSS4J hỗ trợ `setTimestampStrict(true)`, validation TTL và future time skew theo phiên bản API. Một message đúng chữ ký nhưng hết hạn vẫn phải bị từ chối theo time policy. Nếu Timestamp không được ký, attacker có thể thử thay đổi `Created`/`Expires` — do đó khi contract yêu cầu signed Timestamp phải bảo vệ **đúng `wsu:Timestamp` reference**.

Cần quản lý clock skew/NTP và cửa sổ chấp nhận; không nới TTL vô hạn chỉ để đối tác không đồng bộ đồng hồ.

### 12.2. Replay cache không phải business idempotency

`Wss4jSecurityInterceptor.setValidationReplayCache(ReplayCache)` có thể cung cấp replay state cho nonce/timestamp và một số one-time-use checks theo Spring-WS 4.1.4. Nhưng:

- Nó không lưu transaction result của `SubmitOrder`.
- Nó không thay unique business `requestId` và durable idempotency store.
- Nếu có nhiều server instances, replay cache cần consistency, TTL và capacity theo triển khai.
- Một client có thể gửi lại cùng ý định nghiệp vụ với MessageID/Timestamp mới, khi đó idempotency layer vẫn cần chặn duplicate effect.

~~~text
Security replay attack:
  Signature/Timestamp/Nonce/ReplayCache theo threat model

Valid retry sau network timeout:
  Business requestId + trạng thái bền vững + GetStatus
~~~

### 12.3. Không cho endpoint xử lý dữ liệu chưa verify

~~~mermaid
flowchart TD
    A["TLS + safe bounded parser"] --> B["WSS4J decrypt/verify/trust"]
    B --> C{"Signature, algorithm, signed coverage hợp lệ?"}
    C -- "Không" --> D["Reject / safe fault"]
    C -- "Có" --> E{"Timestamp và replay hợp lệ?"}
    E -- "Không" --> D
    E -- "Có" --> F["XSD/JAXB + authorization"]
    F --> G["Application service / DB"]
~~~

**Order thực tế của Spring-WS endpoint mapping/interceptors cần được kiểm chứng.** Nếu `PayloadRoot` mapping phụ thuộc việc đọc plaintext Body nhưng Body còn ciphertext trước decryption, có thể không tìm được endpoint; cần thiết kế mapping tương thích (SOAPAction/WS-Addressing) hoặc xử lý security sớm theo stack, không tắt validation để lách lỗi mapping.


## 13. SOAP Fault và các lỗi trong pipeline security

### 13.1. Failure modes theo từng lớp

| Trường hợp | Tầng lỗi | Hành vi có thể quan sát |
| --- | --- | --- |
| TLS certificate/hostname sai | Transport handshake | Connection failure, **không có SOAP Fault** |
| Recipient không có private decryption key | WSS4J + keystore | Decryption error, security fault hoặc transport failure |
| EncryptedKey alias/cert mismatch | XML Encryption | Không giải mã được session key |
| Ciphertext/authentication tag bị sửa | XML Encryption | Fail integrity/decryption |
| Signer certificate không trusted | XML Signature/trust | Validation exception/Fault |
| Signature bytes/namespace/canonicalization khác | XML Signature | Digest/signature mismatch |
| Outbound action order không khớp policy | WS-Security actions | Reject security message |
| Chữ ký hợp lệ nhưng đúng Body không được ký | Signed-part coverage | **Phải reject**, không chạy nghiệp vụ |
| Timestamp hết hạn hoặc replay | WSS4J replay/time checks | Security rejection |
| `wsa:To` hoặc `ReplyTo` bị thay | Header integrity/routing | Reject nếu policy bảo vệ |
| XSD sai sau khi decrypt | Payload validation | SOAP Client/Sender Fault |
| Request hợp schema nhưng trái quyền | Authorization | Business/security Fault theo contract |
| Backend commit nhưng response bị mất | Transport sau application | Timeout, trạng thái chưa rõ |
| Đổi cert lệch giữa 2 phía | Crypto/keystore | Verify/decrypt failures |

### 13.2. Error detail không được trở thành cryptographic oracle

Một thông báo kiểu:

~~~text
Keystore /etc/private/server-key.p12: wrong key password
RSA decrypt of key transport failed near WSS4J ...
~~~

**Không bao giờ** gửi nguyên văn cho đối tác. Public Fault có thể ghi “Yêu cầu không đáp ứng chính sách bảo mật” cùng correlation ID vô hại, còn nội bộ log loại lỗi được chuẩn hóa (`DECRYPT_FAILURE`, `SIGNATURE_TRUST_FAILURE`) theo quyền và chính sách redaction.

Không để public reason/detail chứa private path, SQL, key alias nhạy cảm, token, stack trace, full plaintext SOAP hoặc phần tử chứa secret. Một số security faults như `FailedCheck`/`InvalidSecurityToken` thuộc WS-Security profile, nhưng mức độ chi tiết công khai phải được đánh giá threat model: phân biệt “wrong padding” và “wrong certificate” quá cụ thể có thể hỗ trợ oracle/brute-force.

### 13.3. Không phải mọi Fault chạy qua application resolver

Một SOAP message có thể bị từ chối **trước khi endpoint mapping hoặc JAXB unmarshalling**. Vì vậy `SoapFaultMappingExceptionResolver` và `@SoapFault` ở business exception **không** nhất thiết xử lý mọi TLS, parser, XML Encryption hoặc WSS4J error.

Khi tạo Fault reply, hãy theo **fault protection policy**: có thể cần ký/mã hóa hoặc giảm detail tối đa nếu chưa xác định được peer/trust recipient. Không mặc định một security failure sẽ sinh một SOAP Fault được ký giống normal response; nếu TLS/HTTP đã fail, client chỉ thấy transport exception.

### 13.4. Lỗi sau commit không có nghĩa rollback

Một request có thể đã qua WS-Security, gọi service và commit DB, nhưng lỗi khi ký/mã hóa response hoặc khi transport gửi khiến client thấy `Receiver/Server` Fault hay timeout. Với command có side effect, client phải dùng **cùng business idempotency key**, tra cứu trạng thái theo WSDL hoặc cơ chế recovery đã thống nhất; không sinh key mới và thực thi lại vô điều kiện.

## 14. Tương thích SOAP 1.1/1.2, WS-Addressing và attachments

### 14.1. Phiên bản SOAP đổi QName của Body

| Yếu tố | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Fault loại client/server | `Client`/`Server` | `Sender`/`Receiver` |
| QName cần ký Body | SOAP 1.1 Body | SOAP 1.2 Body |
| HTTP binding action | `SOAPAction` header | Content-Type `action` theo binding |
| WS-Security header | OASIS WSSE namespace/profile | Tương tự, nhưng SOAP role/mustUnderstand khác |

Đừng dùng cấu hình `setSecurementSignatureParts("{}{SOAP11_NS}Body")` cho SOAP 1.2 rồi mong signer chọn đúng element. Kiểm QName mở rộng, transform/canonicalization, `wsu:Id` và signature references ở wire, không so prefix do serializer tự chọn.

### 14.2. WS-Addressing headers ảnh hưởng quyền và routing

Với `wsa:Action`, `wsa:To`, `wsa:MessageID`, `wsa:ReplyTo`, `wsa:FaultTo` và `wsa:RelatesTo`, một attacker sửa Header chưa ký có thể làm lệch operation, đích gọi hoặc nơi nhận response/Fault. Hãy chỉ định **những headers được ký** theo policy và bảo đảm gateway không rewrite sau signature mà không có trust/reauthorization.

WS-Security Timestamp, WS-Addressing MessageID và business requestId có mục đích khác nhau:

| Trường | Mục tiêu |
| --- | --- |
| `wsu:Timestamp` | Giới hạn thời gian sử dụng thông điệp theo security profile |
| `wsa:MessageID` | Định danh/correlation thông điệp |
| `wsa:RelatesTo` | Liên kết reply/Fault tới request |
| Body `requestId` | Idempotency cho cùng ý định nghiệp vụ khi server enforce |

Không sử dụng MessageID như password hay làm bằng chứng caller đã được xác thực.

### 14.3. MTOM/XOP và SwA: Body signature chưa đủ

Nếu SOAP có `xop:Include`/`cid:...` và binary MIME attachments, chỉ ký XML Body **có thể không bao phủ attachment bytes**. WSS4J có cơ chế `AttachmentCallbackHandler` và selectors/profiles ký/mã hóa attachments, Spring-WS 4.1.x cung cấp `setAttachmentCallbackHandler(...)`.

Phải test:

- Chỉnh một byte trong MIME attachment nhưng giữ XML Body không đổi.
- Chỉnh `Content-ID`, duplicate MIME parts, header metadata theo profile.
- Byte stream được verify có đúng stream ứng dụng scan/lưu không.
- Bộ nhớ/tệp tạm với XML Signature/Encryption + MTOM khi có nhiều attachments.
- Java/.NET interoperability, đặc biệt signed/encrypted attachment transforms và SOAP 1.1/1.2.

### 14.4. WS-SecurityPolicy là nguồn ràng buộc liên nền tảng

Hợp đồng giữa A và B nên định nghĩa rõ:

1. `SignBeforeEncrypting` hay `EncryptBeforeSigning`.
2. Body/Headers/attachments nào thuộc `SignedParts`/`EncryptedParts`.
3. Thuật toán XML Signature, Digest, AES, RSA key transport.
4. Token/certificate profile, KeyIdentifier/IssuerSerial/DirectReference.
5. Timestamp TTL, yêu cầu signed Timestamp, replay cache.
6. Signature protection: có mã hóa chữ ký hay không.
7. SOAP version, WS-Addressing, binding/fault protection.
8. Mutual trust, cách rotation cert và identity-to-tenant mapping.
9. Mức độ công bố SOAP Fault khi validation/decrypt thất bại.
10. Test vectors: XML do A tạo và B nhận, XML do B tạo và A nhận.

`@Endpoint` hoặc `WebServiceTemplate` biên dịch thành công **không chứng minh** WS-SecurityPolicy đã được áp dụng; Spring-WS interceptor cần cấu hình/kiểm thử riêng và WSDL/WS-Policy của đối tác phải phản ánh các yêu cầu đó.


## 15. Kiểm thử mã hóa, giải mã và thứ tự hành động

### 15.1. Ma trận kiểm thử hai chiều

| Ca | A → B request | B → A response | Kỳ vọng |
| --- | --- | --- | --- |
| SignBeforeEncrypting hợp policy | B decrypt, verify A | A decrypt, verify B | Pass và Body đúng schema |
| EncryptBeforeSigning hợp policy riêng | B verify ciphertext/decrypt | A verify ciphertext/decrypt | Pass khi hai phía cùng hỗ trợ |
| A dùng SignBeforeEncrypting, B đòi EncryptBeforeSigning | Order mismatch | Không tới business | Reject, không tự downgrade |
| Chỉ ký nhưng policy đòi encryption | Body có plaintext | — | Reject dù signature valid |
| Chỉ mã hóa nhưng policy đòi signature | Body ciphertext | — | Reject vì thiếu identity/integrity |
| Chữ ký có nhưng chỉ phủ Header phụ | B thấy unsigned Body | — | Reject theo coverage |
| B decrypt được nhưng signer A không trusted | Decryption pass, signature trust fail | — | Không gọi use case |
| A ký với private key sai | Verify signature fail | — | Safe security fault |
| A encrypt bằng cert cũ của B | B không mở EncryptedKey | — | Reject/decrypt error |
| B ký response bằng cert mới A chưa trust | Request pass | A signature trust fail | Client không chấp nhận response |
| B encrypt response cho sai recipient | Request pass | A decrypt fail | Client báo lỗi bảo mật |
| Body bị sửa sau khi ký | Digest mismatch | — | Reject |
| XML Signature Wrapping | Signed decoy + unsigned Body | — | Reject; endpoint không dùng unsigned Body |
| WS-Addressing To bị sửa sau ký | Signed Header mismatch | — | Reject |
| Timestamp hết hạn | Replay/time fail | — | Không vào endpoint |
| Lặp nonce/message trong replay window | Cache detect nếu profile bật | — | Reject theo policy |
| Duplicate wsu:Id | Signature reference ambiguity | — | Reject |
| Chọn SOAP 1.2 với Body QName SOAP 1.1 trong signing config | Signature thiếu Body | — | Reject/không sinh message hợp lệ |
| Payload XSD sai nhưng crypto hợp lệ | Signature/decrypt pass, XSD fail | — | Client/Sender Fault |
| Attachment bị thay bytes | WSS4J attachment signature fail nếu profile bảo vệ | — | Không lưu document |
| TLS handshake fail | Không tạo SOAP exchange | — | Transport error, không mặc định SOAP Fault |
| Server commit rồi response encryption fail | Request pass | Không có response hợp lệ | Client query status/idempotent retry |
| Concurrent calls đa tenant | Các keys/profiles tách biệt | Response đúng tenant | Không rò credential |
| Rotation overlap window | Old/new accepted theo policy | Mutual trust đúng | Không mất tương thích |

Mỗi kết quả cần được xác nhận bằng **wire XML và behavior**, không chỉ nhìn Java method trả về đúng exception. Đối với action order, test cả message XML có Signature→Encryption và Encryption→Signature để bảo đảm receiver **không silently accept** profile khác.

### 15.2. Các bước triển khai test thực tế

1. **Key fixtures:** tạo certificate/key pairs A/B chỉ dành riêng cho test, có trust chain và aliases tách biệt; không dùng private key production.
2. **Client outgoing:** tạo SOAP request thật qua `WebServiceTemplate` với `Wss4jSecurityInterceptor`; chụp message sau security nhưng trước transport bằng harness được phép.
3. **Wire assertions:** xác minh `wsse:Security`, `ds:Signature`, `xenc:EncryptedData`, `xenc:EncryptedKey`, `Timestamp` và các Algorithm URI đúng policy.
4. **Server inbound:** gửi message đến Spring-WS dispatcher/server có security interceptor thật; assert crypto verification xảy ra trước business use case.
5. **Server outgoing:** nhận `SubmitOrderResponse`/fault theo profile rồi cho client A decrypt/verify.
6. **Tampering:** sửa Body/ciphertext, headers, signature references, Timestamp và attachment; mỗi sửa đổi phải bị từ chối hoặc xử lý đúng lớp.
7. **Negative trust:** thay signer cert, recipient cert, expired certificate, key password và rotation.
8. **Fault protection:** kiểm public fault không rò keystore path/token/plaintext; kiểm transport failures riêng.
9. **Interoperability:** cùng vector chạy Java Spring-WS/WSS4J và ít nhất một client khác stack như .NET/WCF nếu là đối tác thực.
10. **Load:** thử nhiều calls đồng thời, message lớn/MTOM, xem heap, latency, thread pool, replay cache và file descriptors.

### 15.3. Test API của Spring-WS

`MockWebServiceClient` hỗ trợ server-side endpoint tests. `MockWebServiceServer` hỗ trợ client-side `WebServiceTemplate` tests. Chúng hữu ích để kiểm request/response/Fault thông dụng, **nhưng** một unit test chỉ mock `Wss4jSecurityInterceptor.validateMessage` hoặc bypass Crypto **không chứng minh** XML Signature/Encryption hoạt động.

Với security, nên có **integration test dùng message factory, WSS4J và Crypto thật**, kết hợp wire-level assertions theo namespace/QName. Một sơ đồ test:

~~~text
Test client A Wss4jSecurityInterceptor
        |
        | actual signed + encrypted SOAP request
        v
HTTP test server B / Spring-WS
  ├── reject before useCase if trust/coverage invalid
  ├── decrypt + signature verify + replay checks
  ├── business response builder
  └── sign + encrypt response
        |
        v
Test client A decrypt/verify
  └── JAXB response hoặc expected SOAP Fault
~~~

Nếu test môi trường không chạy HTTP thật, phải chứng minh message factory/serializer và security interceptors vẫn được kích hoạt. Mock transport có thể bỏ qua một phần HTTP/TLS behavior; bổ sung riêng TLS/mTLS tests khi đó là yêu cầu.

### 15.4. Assertion theo QName và chứng chỉ, không theo prefix

Một `ds:Reference` dùng `URI="#id-123"` phải được resolve về đúng node `wsu:Id=id-123`. Khi validator hoặc assertion đọc XML:

- Dùng XML parser an toàn, namespace-aware, reject duplicate IDs.
- So **namespace URI + local name**, không so raw text `<wsse:Security>` vì prefix có thể thay.
- Kiểm đúng `ds:Reference` cho Body và các Headers required, không chỉ số lượng references.
- Kiểm Algorithm URI đúng thuật toán/cipher suite được phê duyệt.
- Kiểm signer fingerprint/trust/identity theo partner, không chỉ signature mathematically valid.
- Kiểm plaintext sau decrypt đúng JAXB/XSD object và không chứa một node unsigned bị business xử lý.
- Không xuất key/private bytes hoặc toàn bộ SOAP Header/Body trong test logs/reports.

### 15.5. Thử response encryption fail sau khi nghiệp vụ commit

Đây là một lỗi ít thấy khi test “happy path”:

~~~mermaid
flowchart TD
    A["Request được decrypt/verify"] --> B["SubmitOrder commit DB"]
    B --> C["Response được marshal"]
    C --> D{"Ký / mã hóa response thành công?"}
    D -- "Không" --> E["Client có thể thấy Fault/timeout"]
    D -- "Có" --> F["Transport gửi response"]
    F --> G{"Client nhận?"}
    G -- "Không" --> E
    G -- "Có" --> H["Client xử lý success"]
    E --> I["Cùng business requestId / GetOrderStatus"]
~~~

Dù client chưa thấy result, transaction có thể đã commit. Sử dụng business idempotency key và status query thay vì retry bằng key mới. Security stack phải không tạo phản hồi success giả khi ký/mã hóa thất bại.

## 16. Những anti-pattern cần tránh

| Sai lầm | Nguy cơ | Thiết kế đúng |
| --- | --- | --- |
| “Encrypt thì đã authentication” | Ai cũng có thể encrypt bằng public cert B | Bắt buộc signature/trust khi policy yêu cầu |
| “Signature thì đã confidentiality” | Plaintext lộ trên wire/relay | Mã hóa selected parts |
| Đảo `validationActions` một cách máy móc | Policy/action mismatch | Theo WSS4J observed actions + wire tests |
| Coi `Timestamp` action tự được ký | Header có thể bị sửa | Explicit signed Timestamp part |
| Chỉ ký một Header phụ, không ký Body | Endpoint đọc dữ liệu không bảo vệ | Enforce signed Body coverage |
| Ký Body nhưng không ký `ReplyTo/FaultTo` quan trọng | Callback hijack | Ký Header theo threat model |
| Coi cert trong `BinarySecurityToken` là trusted | Attacker tự gửi cert | Chain trust + identity mapping |
| Encrypt request bằng public cert của chính client | Server B không decrypt được | Encrypt cho recipient B |
| Encrypt response bằng public cert của server B | Client A không decrypt được | Encrypt cho recipient A |
| Dùng `setSecurementEncryptionUser` để thay private signing alias | Sai chức năng key | Separate signing/encryption identities |
| Tắt `strictActionChecking` để chấp nhận thiếu signature | Security downgrade | Sửa partner profile/order đúng |
| Bật RSA 1.5 transport vì dễ interop | Rủi ro legacy crypto | RSA-OAEP nếu peer hỗ trợ |
| Hash/digest SHA-1 không có ngoại lệ | Thuật toán yếu | SHA-256+ theo policy |
| Tưởng SOAP Fault luôn được bảo vệ như success | Có thể lộ security diagnostic | Fault protection + safe fallback |
| Dùng XML parser `local-name()` để chọn payload | XML Signature Wrapping | QName + đúng signed node |
| Reuse mutable secret/cert profile trong singleton giữa calls | Cross-tenant leakage | Tách profile/bean/sender |
| Chỉ kiểm signature hợp lệ, bỏ authorization | Signer trái phép vẫn có thể gọi | Identity-to-resource policy |
| Chỉ ký XML Body nhưng tin binary attachment cũng đã ký | MIME part có thể không được bảo vệ | Attachment signing/profile tests |
| Log toàn SOAP có UsernameToken/private metadata | Lộ secret/PII | Redaction + access control |
| Tự tạo một `ds:Signature` bằng string concatenation | XML canonicalization/reference lỗi | WSS4J/Santuario |
| Retry SOAP command bằng requestId mới sau timeout | Tạo trùng side effect | Idempotent retry/status query |
| Chỉ test trên Java cùng version | Không thấy lỗi C14N/interop | Java/.NET test vectors |

## 17. Checklist review và bài tập

~~~mermaid
flowchart TD
    A["Xác định SOAP binding + WSDL/XSD"] --> B["Thỏa WS-SecurityPolicy giữa A/B"]
    B --> C["Chọn protection order và protected parts"]
    C --> D["Provision signing/decryption keys, peer certs"]
    D --> E["Cấu hình client securement + response validation"]
    E --> F["Cấu hình server request validation + response securement"]
    F --> G["Enforce signed coverage + identity + replay"]
    G --> H["Tamper tests và Java/.NET interoperability"]
    H --> I["Fault policy, rotation, monitoring và idempotency"]
~~~

### Checklist production

1. **WSDL/SOAP:** contract-first Request/Response/Fault, SOAP 1.1/1.2 và namespace đúng?
2. **Protection order:** `SignBeforeEncrypting` hay `EncryptBeforeSigning` được hai phía xác nhận bằng policy và wire test?
3. **Keys request:** A private signing; B public encryption; B private decryption; A signer trusted tại B?
4. **Keys response:** B private signing; A public encryption; A private decryption; B signer trusted tại A?
5. **Securement/validation:** actions được cấu hình đúng vị trí client/server và đúng order được WSS4J chấp nhận?
6. **Protected parts:** Body, Timestamp, WS-A routing headers và attachments đã được ký/mã hóa đúng phạm vi?
7. **XML safety:** parser chống XXE, duplicate ID, wrapping, namespace confusion và limits?
8. **Algorithms:** signature, digest, AES, RSA-OAEP/recipient key đáp ứng algorithm suite và không downgrade?
9. **Trust:** chain, validity, identity mapping, revocation/rotation và authorization được kiểm tra?
10. **Replay:** Timestamp signed, TTL/skew, cache nonce/timestamp và business idempotency tách biệt?
11. **Fault:** lỗi TLS/security/validation/business được phân biệt và không tiết lộ diagnostic nhạy cảm?
12. **Response:** server ký/mã hóa cả success/fault khi policy yêu cầu; client verify/decrypt mọi response thích hợp?
13. **Interoperability:** Java/.NET test cả hai protection orders, SOAP versions, signed parts và MTOM?
14. **Operations:** secret management, certificate rotation, metrics và retry sau post-commit failure đã thiết kế?

### Bài tập tự kiểm tra

**Bài 1.** A ký và mã hóa request cho B. Điền đúng private/public keys của A và B ở bốn bước ký, encrypt, decrypt, verify.

**Bài 2.** B đã decrypt request thành công nhưng verify chữ ký thất bại. Có được chạy `SubmitOrder` vì Body vẫn hợp XSD không? Vì sao?

**Bài 3.** Vẽ chuỗi SignBeforeEncrypting và EncryptBeforeSigning. Ở mỗi chuỗi, chữ ký ký trên plaintext hay ciphertext?

**Bài 4.** Vì sao không đơn thuần đặt `validationActions` theo đảo chiều của `securementActions`? Phải test điều gì?

**Bài 5.** Một `wsu:Timestamp` có mặt nhưng không nằm trong `ds:Reference`. Nếu hợp đồng yêu cầu signed Timestamp, request đạt policy không?

**Bài 6.** Một message ký `soap:Body` nhưng không ký `wsa:FaultTo` và server gửi Fault ngoài kênh. Có nguy cơ nào? Cách bảo vệ?

**Bài 7.** `securementEncryptionUser` và `securementSignatureUser` biểu thị hai certificate/aliases phục vụ mục đích gì?

**Bài 8.** B đổi encryption certificate nhưng A chưa cập nhật; lỗi xảy ra khi decrypt key hay verify signature? Nếu B đổi signing certificate thì sao?

**Bài 9.** Vì sao cert được gửi trong `wsse:BinarySecurityToken` không tự chứng minh người gửi được trust/authorized?

**Bài 10.** Một attacker thêm signed decoy Body vào Header và unsigned business Body. Cần những kiểm tra nào để ngăn XML Signature Wrapping?

**Bài 11.** Với SOAP 1.1 và 1.2, cấu hình `signatureParts` cho Body khác nhau ở phần nào?

**Bài 12.** Body SOAP có `xop:Include` trỏ MIME part. Vì sao ký Body chưa chắc bảo vệ toàn bộ bytes của attachment?

**Bài 13.** Sau khi order commit, server lỗi khi encrypt response và client timeout. Client retry bằng key mới có an toàn không?

**Bài 14.** WS-Security Timestamp replay cache và application `requestId` giải quyết những vấn đề gì khác nhau?

**Bài 15.** Thiết kế bộ test tối thiểu cho cả hai hướng request/response, bao gồm sửa 1 byte ciphertext, thay cert, bỏ Signature và sai protection order.

## Tài liệu tham khảo

- [Spring Web Services Reference 4.1.4 — Securing Your Web Services](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) — `Wss4jSecurityInterceptor`, encryption/decryption, signatures, certificates, timestamps.
- [Spring-WS 4.1.4 API — Wss4jSecurityInterceptor](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/security/wss4j2/Wss4jSecurityInterceptor.html) — `securementActions`, `validationActions`, crypto/parts, replay cache, strict action checking.
- [Spring-WS 4.1.4 API — CryptoFactoryBean](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/security/wss4j2/support/CryptoFactoryBean.html) — keystore/truststore cho `Crypto`.
- [Apache WSS4J — User Guide](https://ws.apache.org/wss4j/user_guide.html) — action-based security, sign/encrypt attachments và profiles.
- [Apache WSS4J — Configuration](https://ws.apache.org/wss4j/config.html) — action names, algorithms và configuration constants.
- [OASIS — WS-SecurityPolicy 1.3](https://docs.oasis-open.org/ws-sx/ws-securitypolicy/v1.3/ws-securitypolicy.pdf) — `SignBeforeEncrypting`, `EncryptBeforeSigning`, `EncryptSignature` và signed/encrypted parts.
- [W3C — XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core1/) — `SignedInfo`, `Reference`, `DigestMethod` và canonicalization.
- [W3C — XML Encryption Syntax and Processing 1.1](https://www.w3.org/TR/xmlenc-core1/) — `EncryptedData`, `EncryptedKey` và XML encryption methods.

**Ghi nhớ:** **Chữ ký chứng minh toàn vẹn/nguồn ký của những phần được tham chiếu, mã hóa che nội dung cho recipient được chọn; cả hai không tự thay authorization, replay protection hay business idempotency.** Với Spring-WS, phải thỏa thuận thứ tự bảo vệ giữa A và B, cấu hình đúng keys/`Crypto` cho request **và** response, kiểm `validationActions` theo WSS4J policy, xác minh **đúng Body và Header/attachment được ký**, xử lý SOAP Fault an toàn và thử các tình huống sửa nội dung/chứng chỉ/thuật toán trên cả hai phía.
