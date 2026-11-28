# Khóa ký, khóa mã hóa và mối quan hệ giữa bên gửi với bên nhận

## 1. Vì sao ký số và mã hóa phải dùng đúng khóa của đúng bên?

Trong module **SPRING_WEB_SERVICES**, hệ thống SOAP được xây dựng theo hướng **contract-first**: XSD/WSDL xác định các thông điệp, JAXB/OXM ánh xạ XML–Java, Spring Web Services triển khai `@Endpoint` và `WebServiceTemplate`, còn SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và các phép thử tương thích giúp tích hợp doanh nghiệp ổn định.

Khi một SOAP client gửi dữ liệu đơn hàng cho đối tác, thường cần bảo đảm hai mục tiêu:

- **Toàn vẹn và xác thực nguồn gửi:** bên nhận xác minh nội dung ở những phần được ký không bị sửa và chứng thực người ký.
- **Bí mật nội dung:** chỉ bên nhận được chỉ định mới có khả năng giải mã các XML parts nhạy cảm.

Hai mục tiêu dẫn đến **hai hướng sử dụng khóa khác nhau**:

**Ký số:** bên **gửi** dùng **private signing key của mình** để ký; bên **nhận** dùng **public signing key/certificate của bên gửi** để kiểm chữ ký.

**Mã hóa:** bên **gửi** dùng **public encryption key/certificate của bên nhận** để mã hóa; bên **nhận** dùng **private decryption key của mình** để giải mã.

Nếu đảo nhầm các vai trò, hệ thống có thể không ký được, không giải mã được, kiểm sai certificate hoặc yêu cầu chia sẻ private key của một tổ chức cho tổ chức khác. Trong thiết kế đúng, **partner không cần được trao private key của mình chỉ để verify chữ ký hoặc mã hóa thông điệp cho mình**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt public key, private key, X.509 certificate, keystore, truststore và key alias.
2. Chỉ ra đúng khóa cho **ký, kiểm chữ ký, mã hóa, giải mã** ở từng bên.
3. Áp dụng quy tắc cho SOAP request **client → server** và SOAP response **server → client**.
4. Hiểu XML Encryption sử dụng mã hóa lai: symmetric key bảo vệ nội dung, asymmetric key bảo vệ symmetric key.
5. Phân biệt khóa **SOAP message-level** với chứng chỉ **HTTPS/TLS, mTLS**.
6. Giải thích các thuộc tính Crypto của `Wss4jSecurityInterceptor`.
7. Quản lý certificate trust, signer identity, authorization, key alias và vòng đời khóa.
8. Thiết kế signed/encrypted parts phù hợp SOAP Body, Timestamp và WS-Addressing Headers.
9. Giải thích điều gì thay đổi khi ký rồi mã hóa hoặc mã hóa rồi ký.
10. Viết positive/negative tests cho khóa sai, cert không trust và XML bị sửa.

## 2. Hai câu hỏi quyết định chiều sử dụng khóa

Trước khi gán bất kỳ `Crypto` hoặc `KeyStore` nào vào Spring-WS, hãy hỏi:

**Ai cần chứng minh đã gửi thông điệp?** Đó là **người giữ private signing key**. Bên nhận có public signing certificate và policy để kiểm chứng.

**Ai cần đọc nội dung đã được mã hóa?** Đó là **người giữ private decryption key**. Bên gửi cần public encryption certificate của người nhận để mã hóa đúng đích.

~~~mermaid
flowchart LR
    subgraph A["Bên gửi A"]
        A1["Private signing key A"] --> A4["Ký XML parts"]
        A2["Public encryption certificate B"] --> A5["Mã hóa XML parts"]
        A3["SOAP plaintext"] --> A4
        A4 --> A5
    end
    subgraph B["Bên nhận B"]
        B1["Private decryption key B"] --> B4["Giải mã"]
        B2["Trusted signing certificate A"] --> B5["Verify chữ ký"]
        B3["SOAP mã hóa và ký"] --> B4
        B4 --> B5
    end
    A5 -->|"SOAP trên dây"| B3
~~~

Sơ đồ minh họa một profile **ký trước, mã hóa sau**. Có thể có profile ngược lại; dù protection order nào, **sở hữu khóa vẫn không đổi**.

### 2.1. Bảng bốn thao tác

| Thao tác | Chủ thể | Khóa/certificate cần dùng | Mục đích |
|---|---|---|---|
| **Sign** | Sender | Private signing key **của sender** | Tạo chữ ký số cho XML parts |
| **Verify** | Receiver | Public signing certificate **của sender** và trust | Xác minh chữ ký/nguồn ký |
| **Encrypt** | Sender | Public encryption certificate **của receiver** | Mã hóa để receiver đọc |
| **Decrypt** | Receiver | Private decryption key **của receiver** | Khôi phục XML plaintext |

Chữ ký đúng về mặt toán học **chưa đủ**. Receiver còn phải xác minh signer certificate/trust, những XML parts đã ký và quyền của signer đối với operation.

### 2.2. Vì sao “mã hóa bằng private key để tạo chữ ký” là cách nói sai?

**Digital Signature** dùng thuật toán ký/kiểm chữ ký riêng; không phải phép “mã hóa private key” áp dụng cho một đoạn dữ liệu bất kỳ. Với RSA-PSS, ECDSA hoặc EdDSA, phép ký không tương đương encrypt plaintext bằng private key.

Ngược lại, **encryption để giữ bí mật** dùng public encryption key của người nhận (thường để wrap một symmetric content key), và người nhận giải mã bằng private decryption key của mình.

### 2.3. Public key không bí mật nhưng phải được xác thực

Một attacker có thể công bố public key của họ rồi giả mạo đó là public certificate của partner. Nếu client mã hóa nhầm cho public key này, dữ liệu có thể chỉ được attacker giải mã.

Do đó, lúc nhận public certificate của đối tác phải có **quy trình onboarding/trust**: kiểm fingerprint/chain/pin theo chính sách, nguồn phân phối đáng tin, partner identity và rotation.

## 3. Public key, private key và cặp khóa

Một **asymmetric key pair** gồm:

- **Private key**: chủ sở hữu hoặc dịch vụ được ủy quyền giữ bí mật; dùng để ký hoặc giải mã theo thuật toán/key usage.
- **Public key**: phân phối cho bên cần verify hoặc encrypt; thường đi kèm X.509 certificate.

~~~text
Partner A:
  privateSignA  <---->  publicSignA

Partner B:
  privateDecryptB  <---->  publicEncryptB

A ký request bằng privateSignA.
B verify bằng publicSignA.

A mã hóa request bằng publicEncryptB.
B giải mã bằng privateDecryptB.
~~~

Các tên này thể hiện **vai trò logic**. Một tổ chức có thể có một hoặc nhiều key pairs; nếu chính sách cho phép, một keypair có thể dùng cho nhiều tác vụ, nhưng thường nên cân nhắc **tách signing và encryption keys** vì key usage, rotation và phạm vi ảnh hưởng khi compromise.

### 3.1. Chữ ký bảo vệ điều gì?

Với WS-Security XML Signature được triển khai và xác minh chính xác:

- Nội dung các XML nodes nằm trong `ds:Reference` không bị sửa ngoài các phép biến đổi/canonicalization được cho phép.
- Receiver xác minh chữ ký bằng public signing key tương ứng.
- Nếu signer identity được trust và authorized, receiver có cơ sở chứng thực nguồn gửi.

Chữ ký **không tự giữ bí mật nội dung**. SOAP Body được ký vẫn có thể đọc được khi không được mã hóa hoặc bảo vệ kênh phù hợp.

### 3.2. Mã hóa không tự xác thực người gửi

Nếu server B giải mã được SOAP Body bằng private key B, điều đó chỉ chứng minh ciphertext được tạo để B có thể mở. Người khác cũng có thể dùng **public encryption certificate của B** tạo ciphertext gửi đến B. Do đó, muốn xác thực sender phải sử dụng chữ ký, mTLS identity hoặc cơ chế authentication theo policy.

### 3.3. Signing key và encryption key có nên dùng chung?

Có thể một triển khai legacy dùng một X.509 keypair cho cả signing và key transport, nếu thuật toán, certificate KeyUsage, policy và key management cho phép. Tuy nhiên, dùng cặp khóa riêng thường có lợi:

- Dễ thu hồi/rotate signing key mà không tác động dữ liệu cần decrypt.
- Tránh mở rộng mục đích sử dụng một private key.
- Phân quyền truy cập private keys chi tiết hơn.
- Rõ ràng audit logs: khóa nào để ký, khóa nào để giải mã.
- Giảm phạm vi ảnh hưởng nếu một keypair bị lộ.

Không khẳng định bắt buộc mọi SOAP integration phải có hai pairs; hãy kiểm tra profile và interoperability.

## 4. X.509 certificate và chuỗi tin cậy

Một chứng chỉ X.509 thường chứa:

- Public key.
- Subject, Subject Alternative Name hoặc metadata nhận diện.
- Issuer và serial number.
- Thời gian `notBefore` và `notAfter`.
- Signature algorithm và chữ ký của issuer.
- Key Usage, Extended Key Usage và Basic Constraints.
- Các extension cho policies/revocation, khi có.

**Certificate không chứa private key của chủ thể.** Một file `.cer`/`.crt` chỉ có public certificate không đủ để tạo chữ ký hoặc giải mã.

### 4.1. Certificate chain

~~~text
Root CA (trust anchor)
      |
      +-- Intermediate CA
               |
               +-- Partner B certificate
~~~

Receiver phải đánh giá chain/anchor phù hợp trust policy; không tin certificate chỉ vì Subject có chữ “Partner B”. Một hệ thống cũng có thể dùng certificate pinning/explicit partner trust theo thỏa thuận nhưng cần kế hoạch rotation.

### 4.2. Chữ ký đúng chưa chắc signer được tin

Các câu hỏi độc lập:

1. `ds:SignatureValue` có đúng toán học không?
2. Public key dùng verify có khớp private key đã ký không?
3. Certificate của signer có được trust không?
4. Certificate có đáp ứng thời gian hiệu lực, mục đích và policies không?
5. Signer có quyền thực hiện operation và truy cập tenant này không?
6. XML Body/Header quan trọng có thực sự nằm trong signed references không?

Không được “trust all certificates” chỉ để signature verification pass.

### 4.3. Certificate expiry và thời điểm ký

Certificate có thời hạn riêng; WS-Security Timestamp và message signature có chính sách thời gian khác. Với SOAP request–response thời gian thực, cần kiểm chứng validity/revocation theo chính sách. Không bỏ qua expiration chỉ vì chữ ký mathematically valid.

Các hệ thống lưu chữ ký dài hạn có thể có yêu cầu riêng về time-stamping, archival validation và audit; đó không phải mặc định của mọi SOAP service.

## 5. Keystore, truststore và key alias

Một KeyStore hoặc PKCS#12 store là **container** có thể giữ:

- Private key entry cùng certificate chain.
- Trusted certificate entry.
- Secret key entry nếu loại store và API hỗ trợ.
- Alias xác định entries.

**Keystore/truststore thường là tên theo vai trò sử dụng**, không nhất thiết là hai định dạng file khác nhau.

| Khái niệm | Ý nghĩa |
|---|---|
| `PKCS12` / `JKS` | Định dạng file/store |
| Keystore | Store thường chứa private keys và certificate chains của mình |
| Truststore | Store chứa certificate/CA trust anchors của đối tác |
| Alias | Tên logic của entry trong một store |
| Store password | Credential mở store |
| Key password | Credential mở private key entry khi cần |
| Certificate alias | Tên để tìm public certificate của partner |

### 5.1. Store của Client A

~~~text
client-a-identity.p12
    alias: client-a-signing
        - private signing key A
        - certificate chain A
    alias: client-a-decryption
        - private decryption key A
        - certificate chain A

client-a-trust.p12
    alias: partner-b-signing
        - trusted signing certificate/CA của B
    alias: partner-b-encryption
        - public encryption certificate của B
~~~

Có thể tách Crypto/stores cho public encryption certificates khỏi truststore nếu policy quy định. Điều quan trọng là certificate dùng **mã hóa cho B** được xác thực thuộc B.

### 5.2. Store của Server B

~~~text
server-b-identity.p12
    alias: server-b-signing
        - private signing key B
        - certificate chain B
    alias: server-b-decryption
        - private decryption key B
        - certificate chain B

server-b-trust.p12
    alias: client-a-signing
        - trusted signing certificate/CA của A
    alias: client-a-encryption
        - public encryption certificate của A
~~~

B không cần private signing key A để verify, A không cần private decryption key B để encrypt.

### 5.3. Alias không là định danh toàn cục

Hai stores có thể cùng chứa alias `signing` nhưng trỏ hai keys khác nhau. Trong WSS4J, alias phải được hiểu **cùng với Crypto instance/store**. Nếu `securementUsername` trỏ alias của store sai, chữ ký có thể fail hoặc đại diện nhầm identity.

### 5.4. File có tên “truststore” không tự đáng tin

Đánh giá đúng store entry types, permissions, nguồn certificate và identity mapping. File có tên `partner-trust.p12` vẫn có thể chứa dữ liệu bị import sai. Không dựa vào tên file hay sự tồn tại của alias để quyết định trust.

## 6. SOAP request A → B: mapping khóa chính xác

Giả sử A là SOAP client, B là SOAP server. Request `SubmitOrderRequest` phải được ký và mã hóa.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Server B
    Note over A: Own private signing key A
    Note over A: Trusted public encryption cert B
    A->>A: Marshal request, tạo Timestamp
    A->>A: Ký Body/headers bằng private signing key A
    A->>A: Mã hóa Body cho public cert B
    A->>B: SOAP request qua HTTPS
    Note over B: Own private decryption key B
    B->>B: Giải mã bằng private decryption key B
    B->>B: Verify bằng public signing cert A
    B->>B: Kiểm tra trust, XSD và quyền
~~~

### 6.1. Bảng request

| Tác vụ | Client A, gửi request | Server B, nhận request |
|---|---|---|
| Signature | Dùng `privateSignA` | Verify với `publicSignA` + trust |
| Encryption | Dùng `publicEncryptB` | Decrypt với `privateDecryptB` |
| Timestamp | Tạo Created/Expires | Kiểm tra TTL/skew/replay |
| SOAP payload | Marshal, ký/mã hóa các parts | Verify/decrypt, validate XSD, xử lý |
| Transport TLS | Verify TLS identity B | Cung cấp TLS certificate B; có thể mTLS |

### 6.2. Nhầm lẫn số 1: A dùng public cert A để mã hóa request

Nếu A mã hóa request bằng public cert A, server B không có private key tương ứng để decrypt. Sửa bằng cách dùng public encryption certificate **của B** đã được xác thực qua onboarding.

### 6.3. Nhầm lẫn số 2: B cần private key A để verify chữ ký

B chỉ cần public signing cert A và trust policy. Yêu cầu A chuyển private signing key cho B là sai nguyên tắc sở hữu và làm mất ý nghĩa của chữ ký.

### 6.4. Nhầm lẫn số 3: Signature hợp lệ đồng nghĩa có quyền SubmitOrder

Signer A có thể được trust nhưng không được phép đặt hàng cho một tenant cụ thể. Sau khi message security hợp lệ, authorization vẫn phải kiểm tra partner, operation và business resource.

## 7. SOAP response B → A: bên gửi và nhận đổi vai

Server B gửi `SubmitOrderResponse` về Client A:

~~~mermaid
sequenceDiagram
    participant B as Server B
    participant A as Client A
    Note over B: Own private signing key B
    Note over B: Public encryption cert A
    B->>B: Marshal response, tạo Timestamp
    B->>B: Ký bằng private signing key B
    B->>B: Mã hóa cho public encryption cert A
    B->>A: SOAP response
    Note over A: Own private decryption key A
    A->>A: Giải mã bằng private decryption key A
    A->>A: Verify bằng public signing cert B
    A->>A: Trust, policy, XSD và business mapping
~~~

### 7.1. Bảng response

| Tác vụ | Server B, gửi response | Client A, nhận response |
|---|---|---|
| Signature | `privateSignB` | Verify bằng `publicSignB` + trust |
| Encryption | Mã hóa với `publicEncryptA` | Giải mã với `privateDecryptA` |
| Timestamp | Tạo response timestamp | Kiểm tra TTL/skew |
| SOAP Fault | Áp policy Fault riêng nếu quy định | Nhận diện lỗi và xác minh theo policy |
| TLS | Dùng TLS server identity B | Verify TLS cert B |

### 7.2. Một vòng SOAP đủ bốn cặp nhiệm vụ

~~~text
REQUEST  A -> B:
  Sign:       privateSignA
  Verify:     publicSignA
  Encrypt:    publicEncryptB
  Decrypt:    privateDecryptB

RESPONSE B -> A:
  Sign:       privateSignB
  Verify:     publicSignB
  Encrypt:    publicEncryptA
  Decrypt:    privateDecryptA
~~~

Tên các keys thể hiện vai trò, không bắt buộc phải có tám keypairs. Public/private của một pair là cặp tương ứng; chính sách có thể cho phép dùng chung pair cho ký và mã hóa, nhưng cần xem key usage, algorithms và rotation.

### 7.3. One-way SOAP và HTTP 202

Một operation có thể không có SOAP business response thông thường. Khi đó không tự áp profile securement response nếu binding/policy chỉ có acknowledgment. Nếu server gửi callback khác kênh, callback trở thành **một SOAP message mới** mà bên gửi/bên nhận phải xác định lại theo quy tắc trên.

## 8. WS-Security XML Signature và XML Encryption trong SOAP Header

WS-Security thường đưa metadata vào SOAP Header `wsse:Security`. Các token có thể bao gồm `wsu:Timestamp`, `ds:Signature`, `xenc:EncryptedKey` và `wsse:BinarySecurityToken`. SOAP Body hoặc các phần tử bên trong có thể biến thành `xenc:EncryptedData`.

Khung XML minh họa:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    xmlns:xenc="http://www.w3.org/2001/04/xmlenc#">
    <soap:Header>
        <wsse:Security soap:mustUnderstand="1">
            <!-- Security tokens, signature, wrapped key... -->
            <ds:Signature>
                <!-- SignedInfo, SignatureValue, KeyInfo -->
            </ds:Signature>
            <xenc:EncryptedKey>
                <!-- Wrapped content key -->
            </xenc:EncryptedKey>
        </wsse:Security>
    </soap:Header>
    <soap:Body>
        <xenc:EncryptedData>
            <!-- Encrypted XML content -->
        </xenc:EncryptedData>
    </soap:Body>
</soap:Envelope>
~~~

Đây là **XML khái niệm, chưa phải một SOAP message bảo mật hợp lệ**; thư viện WSS4J phải tạo XML Signature References, digest, signature values, encryption algorithms và key transports theo profile.

### 8.1. BinarySecurityToken không phải private key

`wsse:BinarySecurityToken` có thể chứa certificate X.509 công khai của signer, không mang private key tương ứng. Receiver cần verify signature và certificate trust/identity, không tin certificate do sender đính kèm chỉ vì parse thành công.

### 8.2. EncryptedKey là khóa nội dung đã được bọc

`xenc:EncryptedKey` thường chứa symmetric **content-encryption key (CEK)** đã được bảo vệ bằng key transport/wrapping. Nó **không phải private decryption key** của recipient.

~~~text
xenc:EncryptedKey = wrapped CEK trong SOAP
privateDecryptB  = bí mật riêng của B trong keystore/HSM B
~~~

Recipient B sử dụng privateDecryptB giải bọc CEK và dùng CEK giải mã `xenc:EncryptedData`.

### 8.3. Có Signature trong Header chưa chắc SOAP Body được ký

Một chữ ký XML tham chiếu những nodes cụ thể qua `ds:Reference`. Có `ds:Signature` không có nghĩa toàn bộ SOAP Body, Timestamp, WS-Addressing Header hoặc attachments đều nằm trong chữ ký.

Phải kiểm tra signed references và `securementSignatureParts` phù hợp contract, tránh chỉ tìm tên thẻ `Signature`.

## 9. Mã hóa lai: recipient public key bảo vệ symmetric content key

Mã hóa trực tiếp SOAP Body lớn bằng RSA thường không phù hợp. Một XML Encryption flow phổ biến:

1. Tạo symmetric content key CEK ngẫu nhiên.
2. Mã hóa selected XML parts bằng CEK.
3. Dùng **public encryption certificate của receiver** để bảo vệ CEK theo key-transport algorithm.
4. Gửi `EncryptedData` và `EncryptedKey` trong SOAP.
5. Receiver dùng **private decryption key của mình** khôi phục CEK.
6. Receiver dùng CEK giải mã XML ciphertext.

~~~mermaid
flowchart TD
    A["Plaintext XML"] --> B["Symmetric encryption with CEK"]
    C["Random CEK"] --> B
    C --> D["Wrap CEK for recipient"]
    E["Recipient public key"] --> D
    B --> F["EncryptedData"]
    D --> G["EncryptedKey"]
    F --> H["SOAP message"]
    G --> H
    H --> I["Recipient receives"]
    I --> J["Recipient private key unwraps CEK"]
    J --> K["Decrypt XML"]
    K --> L["Plaintext XML"]
~~~

### 9.1. Public certificate không chứa sẵn CEK

Public certificate B mang public key B; nó không tự chứa AES key. CEK được tạo theo session/message profile, và B giải bọc bằng private key B.

### 9.2. Các nhóm thuật toán độc lập

| Quyết định | Ví dụ | Điều cần đánh giá |
|---|---|---|
| Content encryption | AES theo mode và key length được duyệt | Confidentiality, integrity/authentication của ciphertext theo profile |
| Key transport | RSA-OAEP theo profile phù hợp | Key type, OAEP digest/MGF, algorithm support |
| Key identification | Issuer/serial, SKI, direct reference | Receiver chọn được private key đúng |
| Encryption target | SOAP Body Content/Element | QName và WS-Policy |
| XML Encryption version | URI algorithms và cấu trúc key info | Interoperability |

Không bật thuật toán yếu chỉ vì một đối tác legacy yêu cầu mà không có quy trình exception/security review. Những WSS4J/Spring-WS versions có cơ chế từ chối RSA PKCS#1 v1.5 key transport theo baseline; phải kiểm tra version và test âm.

### 9.3. Profile symmetric key khác mô hình certificate-based

Một số WS-Security profiles dùng shared symmetric keys, derived keys hoặc security context token. Bài này tập trung vào mô hình X.509/asymmetric để giải thích chủ sở hữu khóa. Với shared secret, cả hai phía có thể giữ secret chung, nên các quy tắc certificate-based cần được điều chỉnh theo hợp đồng thực.

## 10. Ký trước mã hóa và mã hóa trước ký

Hai protection orders thông dụng:

**Sign-before-encrypt:**

~~~text
Plaintext XML
  -> tạo Timestamp/Headers
  -> ký selected XML parts
  -> mã hóa selected XML parts
  -> gửi SOAP
~~~

**Encrypt-before-sign:**

~~~text
Plaintext XML
  -> tạo Timestamp/Headers
  -> mã hóa XML parts
  -> ký ciphertext/selected representation
  -> gửi SOAP
~~~

Không có một thứ tự đúng cho mọi WSDL/WS-Policy. Thứ tự thay đổi signed references, encrypted targets, header layout và quy trình kiểm chứng inbound.

### 10.1. Quyền sở hữu khóa không đổi theo protection order

Dù order nào, sender vẫn ký với private signing key **của sender**, mã hóa với public encryption key **của receiver**. Receiver giải mã với private decryption key **của receiver** và verify bằng public signing cert **của sender**.

### 10.2. securementActions không phải toàn bộ security contract

~~~java
security.setSecurementActions(
    "Timestamp Signature Encrypt"
);
~~~

Chuỗi action không tự quyết định:

- SignatureParts/EncryptionParts.
- Sender signer identity và certificate trust.
- Recipient certificate/alias.
- Algorithms và XML canonicalization.
- Protection order receiver yêu cầu.
- Action results order tương thích với WSS4J version.

Không tự đảo ngược `validationActions` so với `securementActions` để “giải mã ngược” một cách máy móc; phải thử bằng WSS4J sender/receiver thật và profile chính thức.

## 11. Chứng chỉ TLS và chứng chỉ WS-Security là hai lớp khác nhau

| Lớp | Key/certificate | Mục tiêu |
|---|---|---|
| HTTPS/TLS | TLS server cert/private key, CA trust; optional TLS client cert | Xác thực network peers, bảo vệ kênh |
| WS-Security Signature | Sender private signing key, receiver trust sender public cert | Message-level integrity/authentication |
| WS-Security Encryption | Recipient public encryption cert, recipient private decrypt key | Confidentiality của XML parts |
| Domain authorization | Verified identity, tenant, operation permissions | Kiểm soát quyền truy cập |

Một certificate có thể được tái sử dụng nếu KeyUsage/EKU, algorithm, policy và vòng đời cho phép; nhưng nhiều tổ chức tách TLS và SOAP message keys.

### 11.1. TLS qua gateway

~~~text
Client A --HTTPS--> Gateway --HTTPS--> SOAP Server B
~~~

TLS có thể terminate ở gateway. Chữ ký WS-Security giúp các phần XML đã ký được kiểm chứng sau nhiều hops nếu không bị sửa. XML Encryption có thể giữ selected payload parts bí mật khỏi trung gian nếu chỉ final recipient có private key.

Tuy nhiên, WS-Security **không tự thay TLS**: transport identity, HTTP metadata và những phần chưa được bảo vệ vẫn cần kênh HTTPS được cấu hình đúng.

### 11.2. mTLS không tự sinh ds:Signature

Trong mTLS, TLS client certificate xác thực ở lớp transport. Một SOAP contract yêu cầu XML Signature vẫn cần riêng `Signature` action và các key materials liên quan.

### 11.3. TLS client identity khác SOAP signer identity

Nếu A dùng certificate A1 cho TLS và A2 cho SOAP Signature, phía B phải xác minh cả hai theo đúng policy và đối chiếu identity/authorization khi cần. Không tự động coi signer A2 là cùng chủ thể với TLS caller A1 nếu chưa có mapping được phép.

### 11.4. Key Usage/Extended Key Usage

Certificate X.509 có các ràng buộc sử dụng theo extensions. Certificate chỉ được cấp cho TLS server authentication không mặc nhiên phù hợp với XML Signature hoặc key transport. Đối chiếu đúng certificate purpose trước khi reuse.

## 12. Ma trận khóa chuẩn cho hai phía A và B

| Chiều | Tác vụ | Client A giữ/sử dụng | Server B giữ/sử dụng |
|---|---|---|---|
| A → B | A ký request | **Private signing key A** | **Public signing cert A** + trust |
| A → B | A mã hóa request | **Public encryption cert B** | **Private decrypt key B** |
| B → A | B ký response | **Public signing cert B** + trust | **Private signing key B** |
| B → A | B mã hóa response | **Private decrypt key A** | **Public encryption cert A** |

Hãy kiểm tra chiều trao đổi trước khi gán bất kỳ `Crypto` nào vào Spring-WS. Cùng một certificate A có thể tham gia hai vai trò logic khác nhau nếu key usage/policy cho phép, nhưng **private keys luôn nằm ở chủ sở hữu tương ứng**, không phát cho partner để “làm cho giao dịch chạy”.

### 12.1. Khi chỉ yêu cầu Signature

Một SOAP contract có thể yêu cầu:

~~~text
A -> B: Timestamp + Signature
B -> A: Timestamp + Signature
Transport: HTTPS
~~~

Lúc đó không bắt buộc đưa `Encrypt` vào hai chiều. Nhưng message confidentiality vẫn cần được bảo vệ bằng HTTPS và những biện pháp theo data classification.

### 12.2. Khi chỉ yêu cầu Encryption

Nếu chỉ có mã hóa, B giải mã được request không có nghĩa B biết chắc ai là sender. Public certificate B có thể được nhiều bên biết. Authentication phải đến từ signature, TLS/mTLS, UsernameToken hoặc identity mechanism được hợp đồng chấp nhận.

## 13. Spring-WS Wss4jSecurityInterceptor: ánh xạ Crypto properties

Spring-WS dùng WSS4J interceptor cho message-level security. Với dòng hỗ trợ WSS4J 2, import thường gặp:

~~~java
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;
~~~

Các tên API có thể khác theo Spring-WS release. Luôn đối chiếu package và properties với dependency hiện có.

| Property | Chiều tác động | Key material cần cấp |
|---|---|---|
| `securementActions` | Outbound | Actions cần tạo |
| `validationActions` | Inbound | Actions cần kiểm |
| `securementSignatureCrypto` | Outbound Signature | **Own private signing key** |
| `validationSignatureCrypto` | Inbound Signature | **Signer public certificate/trust** |
| `securementEncryptionCrypto` | Outbound Encrypt | **Recipient public encryption certificate** |
| `validationDecryptionCrypto` | Inbound Decrypt | **Own private decryption key** |
| `securementUsername` | Outbound Signature key selection | Own signing key alias |
| `securementEncryptionUser` | Outbound Encrypt recipient selection | Recipient encryption alias |
| `CallbackHandler` | Credential/key access | Secret provider hoặc key password |

### 13.1. Vì sao hai Signature Crypto khác nhau?

Client A có thể khai báo:

~~~text
ownSigningCrypto:
  client-a-identity.p12 / client-a-signing / privateSignA

partnerSigningTrustCrypto:
  partner-b-trust.p12 / partner-b-signing / publicSignB
~~~

Khi **gửi request**, A cần privateSignA. Khi **nhận response**, A cần publicSignB để verify. Không dùng một “crypto chung” tùy tiện nếu nó không phân tách trust/identity rõ ràng.

### 13.2. Vì sao hai Encryption Crypto khác nhau?

~~~text
recipientEncryptionCrypto:
  partner-b-encryption-public.p12 / publicEncryptB

ownDecryptionCrypto:
  client-a-identity.p12 / privateDecryptA
~~~

A dùng public B khi mã hóa request, private A khi giải mã response. Không có lý do để A nhận privateDecryptB.

### 13.3. Aliases thuộc về entries trong stores

~~~java
security.setSecurementUsername("client-a-signing");
security.setSecurementEncryptionUser("partner-b-encryption");
~~~

Hai chuỗi là selectors cho **hai mục tiêu khác nhau**. Alias chỉ có ý nghĩa cùng Crypto/store; một alias giống nhau có thể trỏ keys khác nhau ở những stores khác nhau.

## 14. SOAP Client A: secure request, validate response

Ví dụ hợp đồng A ↔ B yêu cầu cả request và response có Timestamp, Signature và Encryption. Client A có thể cấu hình:

~~~java
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

Wss4jSecurityInterceptor clientSecurity =
    new Wss4jSecurityInterceptor();

clientSecurity.setSecurementActions(
    "Timestamp Signature Encrypt"
);
clientSecurity.setValidationActions(
    "Timestamp Signature Encrypt"
);

// Outbound request A -> B:
clientSecurity.setSecurementSignatureCrypto(
    clientOwnSigningCrypto
);
clientSecurity.setSecurementUsername(
    "client-a-signing"
);
clientSecurity.setSecurementEncryptionCrypto(
    partnerBPublicEncryptionCrypto
);
clientSecurity.setSecurementEncryptionUser(
    "partner-b-encryption"
);

// Inbound response B -> A:
clientSecurity.setValidationSignatureCrypto(
    trustedPartnerBSigningCrypto
);
clientSecurity.setValidationDecryptionCrypto(
    clientOwnDecryptionCrypto
);

// Còn cần callback key passwords, signature/encryption parts,
// algorithms, trust, timestamp/replay và SOAP/TLS configuration.
~~~

Đây là **skeleton**: các Crypto variables cần được khai báo thành beans, có store/password callbacks và trusted certs. `Encrypt` là action được tài liệu Spring-WS mô tả ở một số phiên bản; WSS4J layer mới có thể dùng tên `Encryption`. Chỉ dùng token mà đúng adapter version nhận diện và kiểm thử được.

### 14.1. Đăng ký client interceptor

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;

WebServiceTemplate template = new WebServiceTemplate();

template.setInterceptors(new ClientInterceptor[] {
    clientSecurity
});

// Ngoài ra cần marshaller/unmarshaller, SOAP factory,
// HTTPS WebServiceMessageSender và WSDL/XSD đúng contract.
~~~

Một bean security không nằm trong `WebServiceTemplate` đang gọi partner sẽ không tự xử lý outbound request.

### 14.2. Request và response có thể có chính sách khác

Ví dụ:

~~~text
Request:
  UsernameToken Timestamp Signature Encrypt

Response:
  Timestamp Signature
~~~

Khi đó `securementActions` (outbound request) và `validationActions` (inbound response) cần **hai chuỗi khác nhau**. Không yêu cầu server encrypt response chỉ vì client encrypt request nếu contract không nói vậy.

### 14.3. Callback khác kênh

Nếu `wsa:ReplyTo` chỉ callback listener, server B có thể gửi response qua HTTP POST mới. B lúc này là **sender** và A là **receiver** như mọi message B → A. Callback listener của A cần inbound signature validation/decryption và correlation `RelatesTo`, không phải chờ `marshalSendAndReceive` trả business response sau khi initial HTTP 202 đã kết thúc.

## 15. SOAP Server B: validate request, secure response

Phía server B sử dụng cùng loại properties với chủ thể khóa đảo vai:

~~~java
Wss4jSecurityInterceptor serverSecurity =
    new Wss4jSecurityInterceptor();

serverSecurity.setValidationActions(
    "Timestamp Signature Encrypt"
);
serverSecurity.setSecurementActions(
    "Timestamp Signature Encrypt"
);

// Inbound request A -> B:
serverSecurity.setValidationSignatureCrypto(
    trustedClientASigningCrypto
);
serverSecurity.setValidationDecryptionCrypto(
    serverOwnDecryptionCrypto
);

// Outbound response B -> A:
serverSecurity.setSecurementSignatureCrypto(
    serverOwnSigningCrypto
);
serverSecurity.setSecurementUsername(
    "server-b-signing"
);
serverSecurity.setSecurementEncryptionCrypto(
    clientAPublicEncryptionCrypto
);
serverSecurity.setSecurementEncryptionUser(
    "client-a-encryption"
);

// Còn cần private-key callbacks, Crypto beans và policy.
~~~

### 15.1. So sánh hai phía cho cùng một request

| Request A → B | Client A | Server B |
|---|---|---|
| Signing | `securementSignatureCrypto` = private A | `validationSignatureCrypto` = public A + trust |
| Encryption | `securementEncryptionCrypto` = public B | `validationDecryptionCrypto` = private B |

Với response B → A thì ngược lại: B ký bằng private B, mã hóa cho public A; A verify với public B và giải mã bằng private A.

### 15.2. Register security vào endpoint interceptor chain

Với các Spring-WS versions cung cấp `WsConfigurer`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;

@Configuration
@EnableWs
public class SoapSecurityConfig implements WsConfigurer {

    private final Wss4jSecurityInterceptor serverSecurity;

    public SoapSecurityConfig(
            Wss4jSecurityInterceptor serverSecurity) {
        this.serverSecurity = serverSecurity;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(serverSecurity);
    }
}
~~~

Skeleton này cần được phối hợp với cấu hình SOAP servlet, endpoint mappings và provider đúng phiên bản. **Có bean nhưng quên register** có thể khiến request được xử lý mà không qua security validation.

### 15.3. Thiếu Signature không được chuyển thành success

Nếu B yêu cầu `validationActions="Timestamp Signature Encrypt"` mà A gửi chỉ Timestamp, B phải từ chối trước side effect nghiệp vụ. Không tắt `Signature` hoặc dùng `NoSecurity` chỉ để hết lỗi tích hợp.

## 16. CryptoFactoryBean và những nguồn key tin cậy

Spring-WS có những cơ chế xây WSS4J `Crypto` từ keystore/trust resources, ví dụ `CryptoFactoryBean` trong các bản hỗ trợ. Cần kiểm tra **chữ ký API và package thật** trước khi copy code, đặc biệt giữa Spring-WS 3.x, 4.x và WSS4J versions.

~~~text
Secret manager / HSM / KMS
     |
     +-- Own private signing key / callback
     +-- Own private decryption key / callback

Trusted certificate onboarding
     |
     +-- Partner public signing certificate / CA trust
     +-- Partner public encryption certificate

Spring Crypto beans
     |
     +-- Wss4jSecurityInterceptor
              |
              +-- WebServiceTemplate hoặc SOAP @Endpoint
~~~

### 16.1. Không hard-code key passwords

Không ghi keystore passwords, private keys, token credentials hay recovery secrets trong source code, README hoặc tài liệu bài học. Dùng secret manager/keystore permissions, hạn chế người/process truy cập và có rotation policy.

### 16.2. PKCS12, JKS và HSM

PKCS#12/JKS là storage formats, không tự bảo đảm trust. Private key có thể nằm trong PKCS#12 hoặc trong HSM/PKCS#11/KMS với non-exportable key handle. Một WSS4J Crypto provider cần có khả năng thực thi **ký** và/hoặc **giải mã** với key thực tế. Không tự kết luận hỗ trợ signing nghĩa là chắc chắn hỗ trợ mọi key-transport/decryption operation.

### 16.3. Hạn chế tài khoản được đọc private keys

Service A có quyền truy cập private key A của mình; service B có quyền truy cập private key B. Một shared filesystem volume chứa private keys của nhiều partners là thiết kế dễ dẫn đến cross-tenant exposure. Tách secrets theo service identity và audit key usage.

## 17. Signed parts và encrypted parts quan trọng ngang chọn đúng khóa

Ví dụ một response có:

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-2048</ord:orderId>
    <ord:bankAccount>masked-example</ord:bankAccount>
</ord:GetOrderResponse>
~~~

Nếu `bankAccount` nhạy cảm, encryption policy phải bảo vệ đúng vùng. Nếu `orderId` ảnh hưởng authorization hoặc idempotency, signature policy cũng phải bảo vệ đúng vùng. **Khóa đúng nhưng ký/mã hóa nhầm XML parts vẫn là thiết kế sai.**

### 17.1. SOAP version quyết định Body QName

~~~text
SOAP 1.1 Body:
  {http://schemas.xmlsoap.org/soap/envelope/}Body

SOAP 1.2 Body:
  {http://www.w3.org/2003/05/soap-envelope}Body
~~~

`securementSignatureParts` chọn Body QName của SOAP 1.1 không tự chọn được SOAP 1.2 Body. Khi nâng cấp binding, kiểm tra parts trước khi đổ lỗi cho certificate.

### 17.2. Timestamp và WS-Addressing headers

Một signature profile có thể yêu cầu ký:

- SOAP Body.
- `wsu:Timestamp`.
- `wsa:To`, `wsa:Action`, `wsa:MessageID`, `wsa:ReplyTo`.
- Business correlation/routing Headers.

Không suy từ chuỗi `securementActions="Timestamp Signature"` rằng Timestamp đã được ký. **Ký những XML parts nào** là một quyết định riêng.

### 17.3. Content encryption khác Element encryption

XML Encryption có thể mã hóa **Content** (nội dung bên trong element) hoặc **Element** (cả element). Chọn kiểu theo SOAP contract, QName và đối tác; kiểm thử JAXB unmarshalling sau decrypt. Không mặc định mọi đối tác đều chấp nhận cùng XML Encryption target.

## 18. Certificate onboarding: nhận đúng public key của đúng đối tác

Trước khi đưa certificate partner vào Spring-WS Crypto, một quy trình onboarding nên xác nhận:

1. Partner/service identity và phạm vi sử dụng.
2. Certificate dùng cho signing, encryption hay TLS/mTLS.
3. Certificate subject, issuer, serial, fingerprint và public key.
4. Trust chain/pinning theo kênh xác thực độc lập.
5. Validity window, key usage, algorithm và revocation policy.
6. Key alias, Crypto store và đích triển khai chính xác.
7. Test với message thật, partner thật hoặc test endpoint được phép.
8. Người phụ trách rotation và cách thông báo trước khi thay certificate.

**Không tin certificate được đính kèm trong `BinarySecurityToken` chỉ vì nó nằm trong SOAP Envelope.** Verify signature bằng một public key không được trust chưa chứng minh signer đáng tin.

### 18.1. Public encryption cert B dùng cho A phải được xác thực

Nếu A import một public certificate giả mạo rồi mã hóa request cho nó, A vẫn có thể tạo ciphertext thành công; lỗi có thể chỉ phát hiện tại phía B khi không decrypt được. Nếu certificate thuộc attacker, thông tin có thể bị mã hóa cho attacker.

Cần xác minh cert B từ nguồn onboarding đáng tin và chạy **encryption round-trip** để kiểm tra B giải mã được bằng privateDecryptB.

### 18.2. Public signing cert A dùng cho B cần có identity mapping

B có thể nhận public cert A qua `BinarySecurityToken` hoặc trust repository. B phải kiểm certificate chain/identity được phép và map signer đó với operations/tenants của A. Certificate do sender tự gửi không tự được thêm vào trust list.

### 18.3. CA trust khác pinning

- **CA-based trust:** certificate chain dẫn tới trust anchor được phê duyệt, kèm identity matching.
- **Certificate/public-key pinning:** chỉ chấp nhận cert/key cụ thể đã đăng ký.
- **Kết hợp:** dùng CA validation và pin/expected identity phù hợp.

Pinning dễ gây gián đoạn nếu quên cập nhật cert khi rotation. Chọn theo mô hình governance và kiểm thử transition window.

## 19. Private key management và giảm quyền

| Câu hỏi | Chính sách |
|---|---|
| Ai giữ private signing key A? | A hoặc HSM/KMS được A ủy quyền |
| Ai giữ private decrypt key B? | B hoặc HSM/KMS được B ủy quyền |
| Ai dùng được khóa? | Service identity có quyền tối thiểu |
| Khóa bị lộ xử lý ra sao? | Revoke, rotate, audit, đánh giá tác động |
| Khóa có được export không? | Theo HSM/key policy, tránh nếu có thể |
| Ai giám sát sử dụng? | Audit key operations, signer identity và certificate lifecycle |

### 19.1. Lộ private signing key khác lộ private decryption key

Nếu privateSignA bị lộ, attacker có thể giả mạo signature A trong phạm vi trust của đối tác. Cần thu hồi signer identity, thay signing keypair và rà soát messages/transactions có nguy cơ giả mạo.

Nếu privateDecryptB bị lộ, attacker có thể giải mã ciphertext được bảo vệ cho publicEncryptB tương ứng, tùy đã thu thập traffic và encryption scheme. Cần thay encryption keypair, phát public cert mới cho partners và đánh giá dữ liệu lịch sử có nguy cơ.

Đổi signing cert không tự khắc phục lộ decrypt key, và ngược lại.

### 19.2. HSM không thay thế certificate trust

HSM có thể giữ private keys non-exportable và thực hiện ký/giải mã, nhưng không tự quyết định signer public cert nào từ partner đáng tin. Trust và authorization vẫn do application/policy xử lý.

### 19.3. Tránh chia sẻ một keystore cho mọi partner

Một keystore chứa private keys của nhiều tenants và được mọi application instances dùng chung làm tăng phạm vi rủi ro. Tách quyền và key aliases theo service identity, môi trường, tenant và chức năng; audit key usage mà không log private material.

## 20. Rotation signing cert và encryption cert có quy trình khác nhau

### 20.1. Rotate signing key A

~~~mermaid
flowchart TD
    A["A tạo privateSignA-v2 và public cert A-v2"] --> B["B cập nhật signer trust chấp nhận v2"]
    B --> C["Hai phía test signature v2"]
    C --> D["A chuyển signing alias sang v2"]
    D --> E["Giám sát verification failures"]
    E --> F["Kết thúc thời gian chuyển tiếp"]
    F --> G["B loại bỏ trust cho signer v1"]
~~~

A không gửi privateSignA-v2 cho B; B chỉ cần public cert/trust A-v2.

### 20.2. Rotate encryption key B

~~~mermaid
flowchart TD
    A["B tạo privateDecryptB-v2 / publicEncryptB-v2"] --> B["B kích hoạt khả năng decrypt v2"]
    B --> C["A xác minh public cert B-v2"]
    C --> D["A chuyển encryption recipient sang B-v2"]
    D --> E["Kiểm tra decrypt messages trên đường truyền"]
    E --> F["Giữ private v1 qua transition nếu policy cho phép"]
    F --> G["Không còn ciphertext v1: retire v1 theo policy"]
~~~

Điểm đặc biệt: nếu B hủy privateDecryptB-v1 khi vẫn còn requests/queued messages mã hóa cho publicEncryptB-v1, B sẽ không decrypt được những messages ấy.

### 20.3. Gia hạn certificate không đồng nghĩa đổi key

Có thể renew một certificate với cùng keypair, hoặc cấp certificate mới và keypair mới. Security policy cần phân biệt certificate validity, key lifetime và rotation thực. Đừng chỉ dựa vào file name hoặc alias để kết luận keypair đã đổi.

### 20.4. Theo dõi hết hạn độc lập

TLS server cert, SOAP signing cert, SOAP encryption cert và mTLS client cert có thể hết hạn vào các ngày khác nhau. Giám sát `notAfter`/revocation/rotation theo từng vai trò và chuẩn bị rollback có kiểm soát.

## 21. Revocation, trust và authorization

Một certificate trong thời hạn hiệu lực vẫn có thể bị thu hồi hoặc không còn được phép đại diện cho partner.

### 21.1. Revocation checking cần được cấu hình và test

CRL/OCSP hoặc denylist/pinning policy có thể được dùng tùy WSS4J Crypto provider và vận hành. Không giả định `validationSignatureCrypto` mặc định thực hiện mọi CRL/OCSP checks. Cần xác định fallback khi revocation service không reachable, tránh silent fail-open ngoài policy.

### 21.2. Certificate chain có thể tin nhiều chủ thể

Nếu truststore tin một CA lớn, nhiều certificates có thể có chain hợp lệ. Vẫn cần map signer identity/subject/issuer hoặc pin key đến đúng partner account và allowed operations.

Ví dụ:

~~~text
Signer identity: partner-A
Allowed:
  GetOrder
  CancelOrder (partner-A tenant)
Denied:
  SubmitPayment (partner-B tenant)
~~~

### 21.3. Identity trong Body phải khớp signer

Một SOAP request có signer cert A nhưng Body chứa `partnerId=B` phải bị kiểm tra quyền, không tự tin dữ liệu chỉ vì chữ ký/ XSD hợp lệ. Bảo vệ routing/authorization fields bằng signed parts và kiểm business authorization.

## 22. Tình huống sai khóa và hậu quả

| Lỗi | Sender có thể tạo message? | Receiver quan sát gì? |
|---|---|---|
| A mã hóa request bằng public cert A | Có thể | B không có private A để decrypt |
| A mã hóa request bằng cert B-v1, B chỉ còn key v2 | Có thể | B không unwrap CEK được |
| A ký bằng alias không tồn tại | Thường fail ở sender | Không có request hợp lệ |
| A ký bằng key identity C | Có thể | B không trust signer A như mong đợi |
| B verify bằng public cert C | Có thể nhận XML | Signature/trust mismatch |
| A ký Body nhưng bỏ Timestamp khi policy yêu cầu | Có thể | Policy về signed parts fail |
| Certificate A hết hạn | Có thể gửi | B reject theo validity policy |
| Response của B bị sửa sau ký | Có response | A signature verification fail |
| A dùng public cert B cho encryption nhưng B chỉ có cert, thiếu private key | Có thể gửi | B không decrypt được |
| A dùng thuật toán key transport không được B hỗ trợ | Có thể | Decryption/interoperability error |

### 22.1. Phân biệt securement outbound và validation inbound

- **Securement outbound failure:** không tìm thấy private signing key, wrong alias, không có recipient encryption cert, callback password lỗi.
- **Validation inbound failure:** certificate không trust, signature sai, decrypt key không khớp, Timestamp hết hạn, message không đúng WS-Security policy.

Hai nhóm lỗi đòi những bên xử lý khác nhau. Không sửa `validationSignatureCrypto` khi nguyên nhân là không tìm thấy recipient encryption certificate ở phía gửi.

## 23. SOAP Fault và xử lý lỗi an toàn

Khi server không giải mã hoặc không kiểm được chữ ký của request, nó có thể chưa biết business sender hoặc payload. Lỗi cần được xử lý theo SOAP Fault/HTTP/security policy, không cho domain endpoint chạy.

- Signature invalid → reject.
- Untrusted certificate → reject.
- No suitable decrypt key → reject.
- Expired Timestamp → reject theo policy.
- SOAP Fault gửi về có thể cần protection riêng, không mặc định luôn có Signature/Encrypt như response thường.

Trong Spring-WS, lỗi security securement/validation và SOAP Fault/transport exceptions là những luồng khác nhau. Không convert một security exception thành successful JAXB response hoặc retry vô hạn.

### 23.1. Không tiết lộ key/keystore internals

SOAP Fault công khai không nên chứa private key password, store path, aliases, raw stack trace hoặc token secrets. Giữ cause để điều tra ở logs nội bộ an toàn, nhưng không log nguyên SOAP Header hoặc plaintext đã giải mã.

### 23.2. Trust failure khác chữ ký sai về mặt toán học

Một chữ ký có thể kiểm toán học thành công nhưng certificate signer không nằm trong trust policy. Cần phân loại lỗi rõ để tránh “chữa” bằng cách bật trust-all.

## 24. Khóa đúng nhưng XML processing vẫn cần bảo vệ

WS-Security Signature/Encryption không thay các lớp sau:

| Lớp | Mục tiêu |
|---|---|
| XSD validation | SOAP business payload đúng contract |
| XXE prevention | Không tải DTD/external entity từ XML không tin cậy |
| Signature Wrapping defense | Business dùng đúng XML nodes đã được xác minh |
| TLS/mTLS | Xác thực/bảo vệ network peer |
| Authorization | Signer được phép gọi operation/tenant |
| Resource limits | Giới hạn SOAP/XML size, nesting, CPU/memory |

### 24.1. XML Signature Wrapping

Nếu một Signature hợp lệ trên một SOAP element nhưng endpoint xử lý element khác cùng local name, receiver có thể bị lừa. Cần xác minh references/`wsu:Id`, enforce đúng SOAP structure và business QName, dùng WSS4J provider được cập nhật.

### 24.2. Đừng sửa XML đã ký

Một logging/tracing interceptor thay SOAP namespaces, IDs, Body hoặc headers sau bước ký có thể khiến signature verification fail. Đừng deserialize rồi serialize lại XML chỉ để đẹp khi đã ký.

### 24.3. Chỉ ký Body chưa chắc bảo vệ Addressing Headers

Nếu `wsa:To`/`wsa:Action`/`wsa:ReplyTo` ảnh hưởng định tuyến, policy có thể yêu cầu ký chúng. Phải đưa QName đúng version vào signature parts và test; không suy rằng chúng được ký chỉ vì ở cùng SOAP Envelope.

## 25. Tạo certificate thử nghiệm mà không chia sẻ private key

Để học luồng A → B có thể tạo test keypairs bằng `keytool` trong môi trường cô lập. Các lệnh dưới đây dành cho **test local**, không dùng key material này ở production, không commit files `.p12` hoặc password vào Git.

### 25.1. Client A tạo signing keypair

~~~bash
keytool -genkeypair \
  -alias client-a-signing \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 30 \
  -storetype PKCS12 \
  -keystore client-a-test-signing.p12 \
  -dname "CN=Client A Test, OU=Training, O=Example, C=VN"
~~~

Công cụ hỏi mật khẩu theo provider/JDK. Không đặt mật khẩu production trong command line hoặc ghi vào shell history.

### 25.2. Export public signing certificate A cho B

~~~bash
keytool -exportcert \
  -alias client-a-signing \
  -storetype PKCS12 \
  -keystore client-a-test-signing.p12 \
  -rfc \
  -file client-a-signing-public.pem
~~~

B nhận file certificate công khai, kiểm fingerprint/trust và dùng để verify signature A. B **không** cần file chứa private key A.

### 25.3. Server B tạo decryption keypair

~~~bash
keytool -genkeypair \
  -alias server-b-decryption \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 30 \
  -storetype PKCS12 \
  -keystore server-b-test-decryption.p12 \
  -dname "CN=Server B Test, OU=Training, O=Example, C=VN"
~~~

Một demo `keytool` tự ký chỉ nhằm học key direction. Trong sản phẩm thật, certificate cần KeyUsage/EKU/profile phù hợp mục đích encryption và quy trình cấp phát đã phê duyệt.

### 25.4. Export public encryption certificate B cho A

~~~bash
keytool -exportcert \
  -alias server-b-decryption \
  -storetype PKCS12 \
  -keystore server-b-test-decryption.p12 \
  -rfc \
  -file server-b-encryption-public.pem
~~~

A nhận public cert B sau onboarding, sử dụng để mã hóa request. B giữ privateDecryptB trong store/HSM của mình. Có thể kiểm thông tin certificate bằng:

~~~bash
keytool -list -v \
  -storetype PKCS12 \
  -keystore server-b-test-decryption.p12
~~~

Không xuất private key B cho A. Để test response B → A, cần thêm B signing keypair và A decryption keypair tương ứng.

## 26. Kiểm thử crypto thật bằng Spring-WS/WSS4J

`MockWebServiceClient` hỗ trợ kiểm thử phía SOAP server; `MockWebServiceServer` hỗ trợ kiểm thử phía `WebServiceTemplate` client. Tuy nhiên, **chỉ kiểm tra sự xuất hiện của `ds:Signature` hoặc `xenc:EncryptedKey` không đủ**: cần thực sự verify signature bằng public cert/trust và decrypt bằng private key đã cấp cho receiver.

### 26.1. Happy-path A → B

1. A marshal `SubmitOrderRequest` theo XSD global element.
2. A tạo Timestamp.
3. A ký Body/Timestamp với privateSignA-test.
4. A mã hóa Body cho publicEncryptB-test.
5. B decrypt bằng privateDecryptB-test.
6. B verify signature bằng publicSignA-test với trust policy.
7. B kiểm authorization A được phép SubmitOrder.
8. B validate XSD và chỉ sau đó xử lý business.

### 26.2. Happy-path B → A

1. B marshal `SubmitOrderResponse`.
2. B ký response bằng privateSignB-test.
3. B mã hóa response cho publicEncryptA-test.
4. A decrypt bằng privateDecryptA-test.
5. A verify bằng publicSignB-test và trust policy.
6. A validate response QName/XSD và xử lý kết quả.

### 26.3. Những negative tests bắt buộc

| Ca | Thay đổi so với hợp đồng | Kỳ vọng |
|---|---|---|
| N1 | A dùng publicEncryptA thay vì publicEncryptB | B không decrypt được |
| N2 | B dùng publicEncryptB thay vì publicEncryptA ở response | A không decrypt được |
| N3 | A ký bằng privateSignC | B từ chối signer C |
| N4 | B ký response bằng privateSignC | A từ chối signer C |
| N5 | Đổi `orderId` sau khi ký | Signature verification fail |
| N6 | B chỉ có privateDecryptB-v1, message dùng publicB-v2 | Decryption fail |
| N7 | Certificate signer hết hạn hoặc untrusted | Trust/validity fail |
| N8 | Message đúng Signature nhưng Body không nằm trong signed references | Reject theo policy |
| N9 | Header `wsa:Action` không được ký khi bắt buộc | Reject theo policy |
| N10 | Dùng key transport algorithm bị cấm | Reject |
| N11 | Sender signature alias không tồn tại | Securement fail trước khi gửi |
| N12 | Recipient private decrypt key không thể mở | Inbound decryption fail |
| N13 | Tamper SOAP Ciphertext | Decrypt/integrity validation fail |
| N14 | Request hợp chữ ký nhưng signer không có quyền | Domain authorization fail |
| N15 | XML có DOCTYPE/external entity | Parser reject, không external I/O |
| N16 | Duplicate signed SubmitOrder request | Replay/idempotency policy |
| N17 | Response SOAP 1.2 nhưng signature parts chọn Body SOAP 1.1 | Contract/security fail |

Không dùng một Crypto helper “trust all” chung cho hai phía rồi coi test pass là bằng chứng bảo mật. Cần test keypairs và truststores **độc lập**, bao gồm trường hợp signer không được trust.

### 26.4. Positive JAXB fixture không thay security fixture

JAXB marshal/unmarshal round-trip có thể pass ngay cả khi client chọn sai recipient encryption cert. Ngược lại, một SOAP message verify signature thành công vẫn có thể sai XSD. Dùng đồng thời:

~~~text
XSD/WSDL/JAXB contract tests
    +
WS-Security sign/verify/decrypt tests
    +
HTTPS/mTLS integration tests
    +
Partner interoperability tests
~~~

### 26.5. Test Fault và transport riêng

Khi chữ ký sai ở inbound, có thể xảy ra SOAP security Fault hoặc lỗi được xử lý trước endpoint. Khi HTTP/TLS handshake fail, chưa có SOAP message để verify. Test phải phân biệt security validation, SOAP Fault, XML parsing và HTTP transport, không gộp tất cả thành “JAXB error”.

## 27. Cách đọc lỗi mà không nhầm key direction

| Triệu chứng | Tầng nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| Cannot find signing key | Outbound sender own key/alias | `securementSignatureCrypto`, alias, callback |
| Cannot find encryption certificate | Outbound sender thiếu recipient public cert | `securementEncryptionCrypto`, alias |
| Cannot decrypt EncryptedKey | Inbound recipient key mismatch | `validationDecryptionCrypto`, private key, key ID |
| Signature invalid | Wrong signer cert, tampered XML, algorithms | `validationSignatureCrypto`, signed refs |
| Signature mathematically valid but untrusted | Trust/identity mapping | Truststore, expected partner |
| Response B → A decrypt fail | B mã hóa cho wrong recipient A | B recipient cert, A private decrypt key |
| Request A → B decrypt fail | A dùng wrong public cert B | A encryption Crypto, B own decrypt |
| Fails only after rotation | Public/private key versions lệch | Transition window, alias/fingerprint |
| TLS handshake failure | TLS/mTLS trust, không phải SOAP encryption | JSSE, TLS cert/hostname |
| Timestamp expiry | Message time policy | Clock skew, TTL, replay |
| XML signature changes after logging | XML bị sửa sau khi ký | Interceptor order, canonicalization |
| SOAP Body signed but business header unprotected | Signature parts thiếu | Signed references, WSDL policy |

### 27.1. Debug “B không giải mã được request A”

1. B thực sự nhận một SOAP message có `EncryptedData`/`EncryptedKey`?
2. A đã mã hóa bằng **public encryption certificate nào của B**?
3. Key identifier có trỏ đúng certificate/version không?
4. B có **private decryption key khớp public key đó** không?
5. `validationDecryptionCrypto` của B trỏ đúng store/alias không?
6. OAEP/key transport và symmetric cipher có hợp policy hai phía không?
7. Trong transition, B có còn private key cho ciphertext v1 không?
8. Có lỗi XML parser/MessageFactory trước bước decrypt không?
9. Test lại bằng benign fixture, không log plaintext hoặc private keys.
10. Tuyệt đối không “sửa” bằng cách gửi private key B sang A.

### 27.2. Debug “A không verify được response B”

1. B ký response bằng private signing key B nào?
2. A dùng public signing certificate B nào để verify?
3. Cert chain/trust và signer authorization có hợp lệ không?
4. SOAP Body/Timestamp/Headers có nằm trong signed parts không?
5. Có thay XML sau signing hoặc đổi SOAP version không?
6. Certificate đã rotate nhưng A chưa cập nhật trust chưa?
7. Có nhầm `validationSignatureCrypto` của A với own signing Crypto của A không?

## 28. Triển khai và giám sát production

Một kế hoạch triển khai:

1. Chốt WSDL/XSD và SOAP 1.1/1.2 binding.
2. Chốt WS-Security policy: actions, protection order, signed/encrypted parts và algorithms.
3. Lập **bảng ownership** cho signing/private, encryption/public, trust và decryption/private ở cả hai phía.
4. Onboard public certificates qua kênh xác thực.
5. Provision own private keys trong secrets manager/HSM/keystores có quyền tối thiểu.
6. Đăng ký đúng `Wss4jSecurityInterceptor` vào client/server chains.
7. Xác minh TLS/mTLS riêng với SOAP message-level keys.
8. Chạy crypto test fixtures thật, bao gồm negative tests.
9. Chạy interoperability với stack phía đối tác nếu được cung cấp.
10. Giám sát certificate expiry, rotation trạng thái và signature/decryption failure rate.
11. Rollout có kiểm soát, giữ rollback keys/trust theo transition window.
12. Sau chuyển đổi, retire keys/aliases và audit quyền theo policy.

### 28.1. Metrics an toàn

Có thể theo dõi:

~~~text
partner=orders-service
operation=SubmitOrder
direction=inbound
security_phase=decrypt
result=failure
key_version=v2
~~~

Không log private key content, passwords, raw SOAP security tokens hoặc decrypted business payload. Tránh dùng raw request MessageID/transaction IDs làm metric labels do high cardinality.

### 28.2. Giám sát rotation riêng cho bốn vai trò

- Client A signing cert A expiry.
- Client A decryption cert A expiry.
- Server B signing cert B expiry.
- Server B decryption cert B expiry.
- Public certs/trust của đối tác đã phát hành và đang được sử dụng.

Nếu một cặp key được dùng cho nhiều mục đích theo policy, vẫn cần ghi rõ tác động tới từng chức năng khi rotate.

## 29. Bài thực hành: hai chiều SOAP với bốn key roles

Một SOAP integration `GetOrder`/`SubmitOrder` chạy qua HTTPS, dùng XSD namespace `urn:example:orders:v1`.

Yêu cầu:

~~~text
Request A -> B:
  Timestamp + Signature + Encrypt
  Signed: SOAP Body + Timestamp
  Encrypted: SOAP Body content

Response B -> A:
  Timestamp + Signature + Encrypt
  Signed: SOAP Body + Timestamp
  Encrypted: SOAP Body content
~~~

Thực hiện:

1. Sinh JAXB classes từ XSD/WSDL, xác minh global element QNames.
2. Tạo A signing keypair và A decryption keypair độc lập.
3. Tạo B signing keypair và B decryption keypair độc lập.
4. Phân phối chỉ public certificates qua quy trình onboarding.
5. Cấu hình A `securementSignatureCrypto` từ A private signer.
6. Cấu hình A `securementEncryptionCrypto` từ B public encrypt cert.
7. Cấu hình A `validationSignatureCrypto` từ B public signer/trust.
8. Cấu hình A `validationDecryptionCrypto` từ A private decrypt key.
9. Cấu hình B mirror tương ứng: verify A, decrypt bằng B, ký bằng B, encrypt cho A.
10. Chọn signing alias và recipient encryption alias rõ ràng.
11. Bảo vệ đúng SOAP Body/WSU Timestamp trong signed references.
12. Kiểm protection order và algorithms theo WSDL/WS-Policy.
13. Test cả request và response bằng WSS4J crypto verifier thật.
14. Kiểm wrong recipient public cert ở mỗi chiều.
15. Kiểm untrusted signer, tampered Body và wrong decryption key.
16. Kiểm certificate expiry và rotation mismatch.
17. Kiểm authorization của signer khác với signature validity.
18. Kiểm SOAP Fault, TLS errors và XML parser policy riêng.
19. Viết bảng key ownership/trust/aliases và expiry để bàn giao vận hành.

**Tiêu chí đạt:** A chỉ ký bằng private A và decrypt bằng private A; B chỉ ký bằng private B và decrypt bằng private B; mỗi sender encrypt cho **public cert của recipient**; cả hai receivers verify đúng signer/trust và từ chối messages không hợp policy.

### 29.1. Tình huống tự giải

**Tình huống A:** A đặt `securementEncryptionCrypto` bằng public certificate của chính A rồi gửi request cho B. B báo không giải mã được. Giải thích nguyên nhân, không yêu cầu chuyển private key A cho B.

**Tình huống B:** B ký response bằng private B, A dùng `validationSignatureCrypto` chỉ chứa public certificate A. Tại sao A từ chối response dù B đã ký đúng?

**Tình huống C:** B rotate encryption cert sang v2 nhưng các clients A còn gửi ciphertext mã hóa cho v1. B có nên xóa privateDecryptB-v1 ngay? Trình bày thứ tự rotation không làm mất khả năng giải mã các messages đang chờ.

## 30. Checklist trước khi triển khai certificate-based WS-Security

- [ ] Phân biệt public key, private key, certificate, keystore, truststore và alias.
- [ ] **Sender ký bằng own private signing key; receiver verify bằng signer public certificate.**
- [ ] **Sender mã hóa bằng recipient public encryption certificate; recipient decrypt bằng own private key.**
- [ ] Bảng khóa của request A → B và response B → A được kiểm tra độc lập.
- [ ] Không chia sẻ private keys cho partner chỉ để verify/encrypt.
- [ ] Signing Crypto và encryption Crypto trỏ đúng aliases/stores.
- [ ] Validation Signature Crypto và own Decryption Crypto không bị đảo vai.
- [ ] Certificate onboarding có fingerprint, trust, identity và key usage phù hợp.
- [ ] CA/pinning/revocation và signer authorization được kiểm chứng.
- [ ] Private keys được quản lý trong keystore/HSM/KMS theo least privilege.
- [ ] Password callbacks không chứa literal secrets trong source hoặc logs.
- [ ] Signature parts bảo vệ Body, Timestamp và Headers bắt buộc.
- [ ] Encryption parts, algorithms và protection order đúng contract.
- [ ] SOAP 1.1/1.2 namespaces và JAXB/XSD compatibility đúng.
- [ ] TLS/mTLS certificate được quản trị riêng với SOAP message keys.
- [ ] Có kế hoạch signing rotation, encryption rotation, transition và rollback.
- [ ] Old decryption key không bị retire khi còn ciphertext hợp lệ cần xử lý.
- [ ] Có crypto-enabled positive/negative tests cả hai chiều.
- [ ] Có tests cert untrusted, signer unauthorized, wrong recipient và tamper.
- [ ] XML parser hardening/XXE, XSD validation, replay và business authorization không bị bỏ qua.
- [ ] SOAP Fault/logging không lộ keys, passwords hoặc raw SOAP dữ liệu nhạy cảm.
- [ ] Có monitoring cert expiry và failure codes theo phase.
- [ ] Đã kiểm interoperability với đối tác hoặc test fixtures được phê duyệt.

## 31. Tổng kết và câu hỏi tự kiểm tra

- **Signing:** người gửi dùng private signing key của mình; người nhận dùng signer public cert và trust để verify.
- **Encryption:** người gửi dùng recipient public encryption cert; người nhận dùng private decryption key của mình.
- **Request A → B:** A ký private A, encrypt public B; B verify public A, decrypt private B.
- **Response B → A:** B ký private B, encrypt public A; A verify public B, decrypt private A.
- **Không trao private keys cho partner chỉ để họ verify chữ ký hoặc mã hóa cho mình.**
- **XML Encryption thường dùng hybrid scheme:** CEK mã hóa XML, recipient public key bảo vệ CEK.
- **TLS/mTLS khác WS-Security message-level keys**, và certificate trust khác authorization.
- **Có khóa đúng vẫn cần đúng signed/encrypted parts, SOAP binding, certificate identity, thuật toán và protection order.**
- **Rotation signing và encryption có rủi ro khác nhau**, nhất là những ciphertext còn cần decrypt bằng private key cũ.
- **Kiểm thử thật phải verify cryptography** và chủ động từ chối wrong key/wrong cert/altered XML, không chỉ nhìn tên thẻ.

**Câu hỏi tự kiểm tra:** Client A ký request bằng privateSignA và mã hóa cho publicEncryptB. Server B giải mã bằng privateDecryptB, verify bằng publicSignA. Khi B trả response được ký và mã hóa cho A, A và B phải dùng các khóa nào? Hãy trình bày đủ bốn thao tác, giải thích vì sao B không cần privateSignA, và đề xuất ba negative tests cho sai recipient certificate, sai signer trust và mismatch giữa key versions khi rotation.





