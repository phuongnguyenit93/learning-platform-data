# Keystore, truststore, khóa riêng và chứng chỉ công khai

## 1. Tại sao SOAP integration cần hiểu chứng chỉ và khóa?

Một ứng dụng Java dùng **Spring Web Services (Spring-WS)** gửi `SubmitOrderRequest` đến hệ thống đối tác qua HTTPS. Hai bên đồng ý XSD/WSDL theo hướng **contract-first**, đã sinh JAXB classes, cấu hình `WebServiceTemplate`, SOAP endpoint, SOAP Fault và interceptors. Đến môi trường tích hợp, một trong các lỗi sau xuất hiện:

- Client kết nối HTTPS thất bại: `PKIX path building failed`.
- Đối tác yêu cầu mutual TLS (mTLS), nhưng client không gửi được client certificate.
- Request SOAP có `wsse:Security` nhưng server trả Fault vì không xác minh được XML Signature.
- Server mã hóa SOAP response bằng certificate cũ khiến client không giải mã được.
- Một thành viên đề xuất gửi file `client.p12` chứa **private key** cho đối tác để “có thể xác minh chữ ký”.

Tình huống cuối rất nghiêm trọng: **đối tác cần public certificate, không cần private key của chúng ta**. Những lỗi còn lại thường xuất phát từ sự nhầm lẫn giữa **danh tính của mình**, **danh tính mình tin**, **TLS transport** và **WS-Security message-level**.

Bài này thuộc chương **Chứng chỉ và khóa** của module `SPRING_WEB_SERVICES`. Mục tiêu là dùng kiến thức PKI, Java keystore/truststore và X.509 để cấu hình an toàn kết nối SOAP và XML security trong hệ thống doanh nghiệp ổn định. Chủ đề tập trung vào **khóa riêng, khóa công khai, chứng chỉ, keystore, truststore và mối quan hệ giữa chúng**; các ví dụ triển khai Spring-WS chỉ nhằm giúp kết nối kiến thức với dự án thực tế.

### Sau bài này, bạn có thể

1. Giải thích private key, public key và X.509 certificate có vai trò khác nhau ra sao.
2. Phân biệt **keystore chứa danh tính của mình** với **truststore xác định danh tính/chứng chỉ mình chấp nhận**.
3. Phân biệt certificate, certificate chain, CA/root trust anchor và việc kiểm tra danh tính hostname.
4. Đọc và tạo ví dụ PKCS#12/JKS an toàn bằng `keytool`; xem public certificate bằng `openssl` mà không xuất private key.
5. Hiểu luồng HTTPS một chiều, mTLS hai chiều, WS-Security Signature và XML Encryption.
6. Dùng Java `KeyStore`, `KeyManagerFactory`, `TrustManagerFactory` và `SSLContext` để biểu diễn identity/trust tách biệt.
7. Chẩn đoán lỗi alias, password, chain, trust, certificate validity, hostname, Extended Key Usage và thuật toán.
8. Lập kế hoạch phát hành, phân phối public certificate, thay mới/thu hồi, kiểm thử và bảo vệ private key trong sản phẩm Spring-WS.

## 2. Bốn khái niệm nền tảng: private key, public key, certificate, trust

### 2.1. Cặp khóa bất đối xứng

Một **key pair** gồm:

- **Private key (khóa riêng)**: bí mật, được chủ sở hữu bảo vệ; có thể dùng để tạo digital signature hoặc giải mã một khóa phiên được bọc cho người nhận, tùy thuật toán và mục đích.
- **Public key (khóa công khai)**: có thể chia sẻ; dùng để xác minh chữ ký do private key tương ứng tạo, hoặc hỗ trợ mã hóa/thiết lập khóa cho người giữ private key, tùy thuật toán.

```mermaid
flowchart LR
    A["Private key: chỉ chủ sở hữu giữ"] -->|"Ký dữ liệu"| S["Digital signature"]
    P["Public key tương ứng"] -->|"Xác minh"| V["Verify signature"]
    S --> V
    E["Public key người nhận"] -->|"Mã hóa/bọc khóa phù hợp"| C["Ciphertext / wrapped key"]
    C -->|"Giải mã bằng private key người nhận"| D["Dữ liệu/khóa được khôi phục"]
```

**Lưu ý quan trọng:** không phải thuật toán bất đối xứng nào cũng hỗ trợ cả ký và mã hóa. Ví dụ ECDSA dùng để **ký/xác minh**, không dùng trực tiếp làm RSA-style public-key encryption. Trong XML Encryption, thông thường nội dung được mã hóa bằng **symmetric content key**, rồi content key được bảo vệ/bọc bằng cơ chế thích hợp cho certificate người nhận.

### 2.2. Chứng chỉ X.509 không phải private key

**X.509 certificate** là cấu trúc dữ liệu có chữ ký số từ issuer, liên kết public key với một subject/identity và những ràng buộc sử dụng nhất định.

```text
X.509 Certificate
  Subject / SAN (danh tính được chứng nhận)
  Issuer (ai cấp)
  Serial Number
  Validity (notBefore, notAfter)
  Subject Public Key Info (public key + thuật toán)
  Key Usage / Extended Key Usage
  Basic Constraints / SKI / AKI ...
  Signature Algorithm
  Issuer's digital signature

Không chứa private key của subject.
```

Một file `.cer`/`.crt`/`.pem` chỉ chứa certificate có thể được gửi cho đối tác theo quy trình. Ngược lại, một file `.p12`/`.pfx` có thể chứa cả **private key** và certificate chain; không được chia sẻ bừa với đối tác.

### 2.3. Sự khác nhau giữa biết public key và tin public key

Ai cũng có thể tạo một cặp khóa và chứng chỉ self-signed:

```text
Attacker tự tạo key pair
  -> tạo certificate Subject=CN=partner.example.org
  -> gửi certificate này cho client
```

Certificate mang đúng tên **không đủ** chứng minh nó là certificate của đối tác. Client phải xác thực chain/trust anchor, certificate validity, key usages, danh tính endpoint (ví dụ SAN khớp hostname) và policy liên quan.

**Một certificate tự mô tả danh tính; một trust decision mới quyết định certificate đó có được chấp nhận cho vai trò cụ thể hay không.**

### 2.4. Hai thao tác không được nhầm

| Thao tác | Khóa được dùng để thực hiện | Khóa được dùng để kiểm tra/đọc |
| --- | --- | --- |
| Tạo chữ ký số | **Private key của người ký** | Public key của người ký để **xác minh** |
| Mã hóa dữ liệu cho đối tác | Public key/cơ chế key agreement của **người nhận** | Private key của người nhận để giải mã/khôi phục khóa |
| TLS server authentication | Server chứng minh nắm private key theo handshake | Client dùng public certificate + trust/hostname checks |
| mTLS client authentication | Client chứng minh nắm private key theo handshake | Server xác minh client certificate/chain theo policy |
| WS-Security SOAP signature | Sender private key | Recipient có public certificate/trust phù hợp |
| WS-Security SOAP encryption | Sender dùng recipient public certificate để bảo vệ content key | Recipient private key để giải mã |

**Không gửi private key để đối tác “verify” chữ ký.** Chỉ cần public certificate hoặc public key theo contract kèm trust validation.

## 3. Keystore là gì? Truststore là gì?

Trong Java, `java.security.KeyStore` là **API và định dạng trừu tượng** để giữ keys và certificates. Từ “keystore” và “truststore” thường mô tả **vai trò sử dụng**, không phải hai loại file mang tính phép thuật.

### 3.1. Keystore: danh tính mà hệ thống sở hữu

Một **identity keystore** dùng cho SOAP client hoặc server có thể chứa:

```text
orders-client.p12     (PKCS12)
└── alias: orders-client
    ├── PrivateKeyEntry
    │   └── private key (bí mật, được bảo vệ)
    └── certificate chain
        ├── client leaf certificate
        └── intermediate CA certificates
```

Ứng dụng tải private key bằng một **key manager** hoặc crypto provider khi cần:

- Chứng minh danh tính client trong mTLS.
- Ký SOAP request bằng WS-Security XML Signature.
- Giải mã SOAP message đã được mã hóa cho client.

Server cũng có keystore của riêng mình để phục vụ HTTPS/mTLS hoặc ký SOAP response. Không được nhầm danh tính **client** và **server** chỉ vì cả hai đều dùng PKCS12.

### 3.2. Truststore: tập chứng chỉ/CA được chấp nhận

Ví dụ:

```text
partner-trust.p12     (PKCS12)
├── alias: partner-root-ca
│   └── trustedCertEntry: root CA certificate
└── alias: partner-intermediate-or-pin
    └── trustedCertEntry (khi policy cho phép)
```

Truststore thường chứa **CA certificates làm trust anchors** hoặc certificate cụ thể mà hệ thống được cấu hình tin. Nó phục vụ:

- Client xác minh chứng chỉ HTTPS server của đối tác.
- Server xác minh client certificates trong mTLS.
- WS-Security verifier tìm trust anchors/known recipient-signer certificates theo cấu hình.

**Truststore không dùng để “chứa private key của đối tác”.** Phía verifier chỉ cần public certificate/CA và trust policy; private key phải ở bên giữ danh tính.

### 3.3. So sánh trực tiếp

| Câu hỏi | Identity keystore | Truststore |
| --- | --- | --- |
| Mục đích | Tôi là ai, tôi có private key nào? | Tôi tin CA/certificate nào? |
| Nội dung thường gặp | `PrivateKeyEntry` + certificate chain | `trustedCertEntry` của CA/certificate |
| Thành phần tiêu thụ | `KeyManagerFactory`; WS-Security signer/decryptor | `TrustManagerFactory`; signature verifier/trust provider |
| Có cần private key không? | Có nếu ký, mTLS client/server hoặc giải mã | Không |
| Bên nào sở hữu? | Chủ thể của danh tính | Bên ra quyết định tin cậy |
| Có thể cùng format PKCS12? | Có | Có |
| Dùng alias để làm gì? | Chọn danh tính/key entry | Đặt tên một certificate/trust anchor |
| Sai cấu hình thường gặp | No suitable client certificate; cannot recover key | PKIX path building failed; untrusted issuer |

### 3.4. Keystore/truststore chỉ là vai trò, không phải ranh giới vật lý bắt buộc

Một file PKCS12 có thể chứa nhiều entry types và về mặt kỹ thuật có thể được dùng cho cả identity/trust. Nhưng đối với ứng dụng doanh nghiệp, nên **tách hai vai trò** để:

- Có quyền đọc/ghi và quy trình rotation riêng.
- Giảm rủi ro dùng nhầm private key hoặc trust không mong muốn.
- Chỉ cấp certificate cần thiết theo nguyên tắc tối thiểu.
- Tách các bí mật của từng integration/tenant/environment.

Không dựa vào phần mở rộng `.jks`/`.p12` để kết luận file có hay không có private key; hãy kiểm tra entry type.

### 3.5. Đừng đánh đồng password với trust

Store password có thể bảo vệ integrity của store và/hoặc key material theo format/provider. Key password có thể bảo vệ private-key entry. Nhưng **biết password không có nghĩa chứng chỉ bên trong đáng tin**, và **một certificate hợp lệ không làm private key an toàn nếu file bị rò rỉ**.

## 4. Trong HTTPS, mTLS và WS-Security, ai giữ gì?

### 4.1. HTTPS thông thường (server authentication)

```mermaid
sequenceDiagram
    participant C as SOAP client
    participant S as HTTPS SOAP server
    C->>S: TLS ClientHello
    S-->>C: Certificate chain + TLS handshake proof
    Note over C: Truststore/TrustManager xác minh chain + identity
    C->>S: TLS handshake hoàn tất
    C->>S: HTTP POST SOAP Envelope (kênh TLS)
    S-->>C: SOAP response/Fault (kênh TLS)
```

Server sử dụng **private key + server certificate chain** để chứng minh danh tính TLS. Client cần **trust anchors và hostname verification** để xác minh phía server. Trong HTTPS một chiều, client không nhất thiết phải có client-certificate keystore.

### 4.2. Mutual TLS (hai phía có danh tính)

```mermaid
sequenceDiagram
    participant C as SOAP client
    participant S as HTTPS SOAP server
    C->>S: TLS ClientHello
    S-->>C: Server certificate chain
    Note over C: Validate server chain + hostname
    S-->>C: Client certificate request
    C-->>S: Client certificate chain + proof of private key
    Note over S: Validate client chain + policy
    C->>S: SOAP request qua kênh TLS đã xác thực
    S-->>C: SOAP response/Fault
```

Lúc này:

- SOAP **client** có identity keystore chứa private key và client certificate.
- SOAP **client** có truststore để xác minh server certificate.
- SOAP **server** có server keystore chứa private key và server certificate.
- SOAP **server** có truststore/validation policy để xác minh client certificate.

**mTLS không tự phân quyền** một identity được phép gọi `CancelOrder` trên tài nguyên cụ thể. Server cần ánh xạ certificate identity sang principal và áp dụng authorization độc lập.

### 4.3. WS-Security SOAP Signature

Ở tầng thông điệp, sender có thể ký XML (thường SOAP Body, Timestamp và những headers theo policy). Ví dụ:

```text
Sender's private key
  -> tạo XML Signature trên những phần được chỉ định
  -> SOAP Header <wsse:Security>...
  -> gửi SOAP qua HTTP(S)

Recipient:
  -> lấy signer public certificate / key identifier
  -> xác minh cryptographic signature
  -> xác minh trust + identity + signed parts + timestamps/replay policy
  -> mới cho vào business endpoint
```

Chữ ký hợp lệ về toán học chỉ chứng minh message khớp với private key tương ứng; **trust, authorization, signed-parts coverage và chống replay vẫn cần được kiểm tra**.

### 4.4. WS-Security SOAP Encryption

Sender dùng **public certificate của recipient** để mã hóa/bọc symmetric content key theo profile. Recipient dùng **private key của mình** để giải mã. Chứng chỉ của signer và chứng chỉ của encryption recipient có thể khác nhau; không giả định luôn là một certificate.

### 4.5. Các lớp không thay thế nhau

| Cơ chế | Bảo vệ chính | Không tự bảo đảm |
| --- | --- | --- |
| TLS | Kênh vận chuyển, danh tính endpoint theo trust | SOAP Body không bị thay sau TLS termination, WS-A signed parts |
| mTLS | Hai peer chứng minh danh tính ở TLS | Authorization nghiệp vụ hoặc SOAP XML Signature |
| WS-Security Signature | Integrity/authenticity của các XML parts được ký | HTTPS hostname, toàn bộ Header nếu không ký |
| WS-Security Encryption | Bí mật của những XML parts được mã hóa | Xác thực người gửi chỉ từ encrypted content |
| XSD validation | Hợp đồng XML hợp lệ | Chữ ký/trust/certificate validity |
| Keystore/truststore | Key material và anchors cho các cơ chế trên | Chính sách ứng dụng tự động an toàn |

Không “đưa private key vào truststore đối tác để tiện tích hợp”; và không coi có HTTPS là đã thực thi WS-Security policy nếu đối tác yêu cầu message signing/encryption.

## 5. X.509 certificate: những trường phải đọc trước khi trust

Chứng chỉ public X.509 không đơn thuần là một file chứa public key. Các trường quan trọng quyết định **danh tính, quyền sử dụng khóa, thời hạn và chain**.

| Thuộc tính | Ý nghĩa | Kiểm tra thường gặp |
| --- | --- | --- |
| `Subject` | Danh tính được chứng nhận | Đúng thực thể theo policy, không chỉ nhìn CN |
| `Subject Alternative Name (SAN)` | Các DNS names/IP addresses/URIs được ràng buộc | HTTPS hostname khớp SAN theo quy tắc xác minh |
| `Issuer` | CA/issuer đã ký certificate | Có chain tới trust anchor đã được tin? |
| `Not Before / Not After` | Khoảng thời gian hiệu lực | Đồng hồ máy, expired/not-yet-valid |
| `Serial Number` | Định danh certificate trong phạm vi issuer | Tìm sự kiện thu hồi, quản lý rotation |
| `Public Key / Algorithm` | Thuật toán và public key | Được policy/TLS/WS-Security profile hỗ trợ? |
| `Key Usage (KU)` | Mục đích cryptographic | Ví dụ digitalSignature phù hợp signing |
| `Extended Key Usage (EKU)` | Vai trò ứng dụng | `serverAuth`, `clientAuth` theo profile |
| `Basic Constraints` | CA hay end-entity, path length | Không dùng leaf thông thường làm CA |
| `Subject Key Identifier (SKI)` | Hỗ trợ liên kết key/issuer | Hữu ích khi dựng chain và key identifiers |
| `Authority Key Identifier (AKI)` | Tham chiếu tới issuer key | Hỗ trợ chain building |
| Signature Algorithm | Cách issuer ký certificate | Không dùng thuật toán bị policy cấm |
| SHA-256 fingerprint | Dấu vân tay bytes certificate | Đối chiếu **ngoài băng** khi trao đổi chứng chỉ |

### 5.1. SAN quan trọng hơn tên hiển thị CN khi xác minh HTTPS

Giả sử SOAP client kết nối tới:

```text
https://soap.partner.example.org/integration/orders
```

Server trình certificate:

```text
Subject: CN=old-host.partner.example.org
Subject Alternative Name:
  DNS:api.partner.example.org
```

Certificate **không tự trở nên hợp lệ cho `soap.partner.example.org`** chỉ vì do cùng công ty cấp hoặc CA đã tin. HTTPS hostname verification kiểm tra danh tính endpoint theo SAN/policy; cần certificate có danh tính phù hợp hoặc sửa URI sang endpoint đã được phê duyệt.

Không “sửa nhanh” bằng một `HostnameVerifier` luôn trả `true`. Cách đó bỏ qua xác minh danh tính server và mở đường cho man-in-the-middle.

### 5.2. Certificate time validity và clock skew

Một certificate có `Not Before` vào ngày mai chưa hợp lệ ở hiện tại, dù chain đúng. Một certificate hết hạn hôm qua cũng không được trust theo validation mặc định. Kiểm tra UTC/time synchronization trên client, proxy và server; không sửa bằng cách tắt certificate expiration checks.

### 5.3. Key Usage và Extended Key Usage

Một CA có thể phát hành các certificates cho mục đích khác nhau:

- TLS server: thường liên quan `serverAuth`.
- TLS client authentication: thường liên quan `clientAuth`.
- XML Signature: cần key algorithm/usage phù hợp (ví dụ `digitalSignature`) cùng policy WS-Security/WSS4J.
- XML Encryption: cần certificate/key algorithm phù hợp với key transport/agreement đã thỏa thuận.

Không suy rằng một certificate có `clientAuth` tự động được đối tác chấp nhận làm SOAP message-signing identity hoặc ngược lại. **Mục đích được chấp nhận phụ thuộc profile và validator**.

### 5.4. Serial, fingerprint và alias khác nhau

```text
alias       = orders-client           (tên entry trong KeyStore)
subject     = CN=orders-client.dev... (identity trong certificate)
serial      = 49A03...               (issuer-scoped identifier)
fingerprint = SHA-256 của certificate bytes
messageId   = WS-Addressing ID của từng SOAP message
```

Các giá trị này **không thay thế nhau**:

- Alias không đi lên wire như danh tính TLS.
- Fingerprint thay đổi khi certificate được phát hành mới, kể cả cùng private/public key trong một số quy trình.
- WS-Addressing MessageID không phải certificate identity.
- Subject/SAN không chứng minh certificate được tin nếu chưa validate chain.

## 6. Certificate chain: leaf, intermediate CA và trust anchor

Một PKI chain đơn giản:

```mermaid
flowchart TD
    R["Root CA certificate\nTrust anchor trong truststore"] --> I["Intermediate CA certificate"]
    I --> L["Leaf certificate\nSOAP server / client / SOAP signer"]
    L --> K["Public key của leaf"]
    L -.->|"Private key tương ứng được giữ riêng bởi subject"| P["Identity keystore / HSM"]
```

Thực chất, mỗi certificate được issuer ký. Verifier xây và xác minh một **certification path** từ leaf qua intermediate(s) đến một **trust anchor** đã được cấu hình.

### 6.1. Server thường gửi certificate chain nào?

Trong TLS, server thường gửi **leaf certificate** và những intermediate certificates cần để client dựng chain. Root CA certificate thường đã nằm trong truststore phía client nên **không bắt buộc** phải gửi trong handshake.

Một vấn đề phổ biến:

```text
Client truststore:
  Root CA: có

Server gửi:
  Leaf certificate: có
  Intermediate CA: thiếu

Kết quả:
  PKIX path building failed
```

Không nên xử lý bằng cách trust-all certificates. Hãy sửa chain phía server hoặc cung cấp intermediate từ một nguồn hợp lệ đã được xác minh theo chính sách.

### 6.2. Tin root CA có nghĩa gì?

Trust root CA có thể khiến validator chấp nhận nhiều certificates hợp lệ do root và các subordinate CAs phù hợp phát hành, **không chỉ một certificate của một đối tác**. Vì vậy:

- Với public WebPKI, nhiều hệ thống dùng truststore tiêu chuẩn của runtime/platform.
- Với private PKI, nên thêm **chính xác CA** mà tổ chức đã phê duyệt.
- Với một partner-specific truststore, cân nhắc phạm vi CA và việc giới hạn peer identity bổ sung.
- Không import một root/intermediate không rõ nguồn chỉ để làm mất lỗi PKIX.

### 6.3. Trust leaf trực tiếp và certificate pinning

Một truststore có thể đặt leaf certificate cụ thể làm trust anchor hoặc ứng dụng có pinning policy riêng. Điều này **hạn chế phạm vi tin cậy hơn trong một số trường hợp**, nhưng làm rotation nhạy cảm:

```text
Partner leaf certificate cũ -> trust trực tiếp
Partner renew leaf mới       -> fingerprint/public key đổi
Client không trust mới       -> kết nối thất bại
```

Nếu dùng pinning, cần kế hoạch **backup pin và overlapping rotation**. Việc import leaf vào truststore không đồng nghĩa đã thực hiện pinning đầy đủ theo threat model, vì cách trust manager xây path và xác minh peer identity vẫn quan trọng.

### 6.4. Certificate revocation: CRL và OCSP

Certificate chưa hết hạn vẫn có thể bị thu hồi vì key compromise hoặc thay đổi trạng thái. Tùy policy:

- CRL: danh sách certificates đã bị thu hồi.
- OCSP: hỏi trạng thái của certificate.
- Stapling/caching/soft-fail/hard-fail: phụ thuộc TLS implementation và môi trường.

**Không mặc định Java TLS hoặc WS-Security luôn kiểm tra revocation đúng chính sách chỉ vì đã có truststore.** Cần cấu hình và kiểm thử revocation behavior theo JDK, trust manager và WSS4J/Crypto provider đang sử dụng.

### 6.5. Certificate chain và truststore không phải danh sách quyền nghiệp vụ

Một client cert được cấp bởi CA tin cậy chỉ chứng minh identity theo PKI. Nó không tự cho phép:

```text
CN=partner-A -> CancelOrder trên mọi tenant
```

Ứng dụng vẫn cần ánh xạ certificate identity tới principal, tenant, vai trò và quyền theo business policy. **Authentication và authorization là hai bước độc lập.**

## 7. Các định dạng thường gặp: PKCS12, JKS, PEM, DER, PKCS11

| Định dạng/cơ chế | Thường chứa | Đặc điểm |
| --- | --- | --- |
| **PKCS#12** (`.p12`, `.pfx`) | Private key + certificate chain, đôi khi trusted certificates | Container phổ biến cho identity material; Java hiện đại dùng rộng rãi |
| **JKS** (`.jks`) | Java keystore entries | Format truyền thống, nhiều hệ thống legacy |
| **PEM** (`.pem`, `.crt`, `.key`) | Certificate, CSR, hoặc private key tùy `BEGIN...` label | Encoding text Base64 với header/footer |
| **DER** (`.der`, `.cer`) | Binary-encoded X.509 certificate hoặc key structure | File nhị phân; phải xem nội dung thực |
| **PKCS#8** | Private key structure | Có thể chứa private key mã hóa hoặc không |
| **PKCS#10 CSR** | Certificate Signing Request, public key + identity request và chữ ký chứng minh sở hữu key | Gửi CA để xin certificate, không chứa private key |
| **PKCS#11** | Interface/token provider đến HSM, smart card | Key có thể không xuất ra file và thao tác ký nằm trong HSM |

### 7.1. Phần mở rộng không quyết định bí mật

Một PEM có thể là certificate public:

```text
-----BEGIN CERTIFICATE-----
... Base64 ...
-----END CERTIFICATE-----
```

Nhưng cũng có thể là private key:

```text
PEM header label: BEGIN PRIVATE KEY
... phần nội dung là private key material bí mật ...
PEM footer label: END PRIVATE KEY
```

Hoặc private key đã mã hóa:

```text
PEM header label: BEGIN ENCRYPTED PRIVATE KEY
... private key material đã được mã hóa; vẫn là bí mật ...
PEM footer label: END ENCRYPTED PRIVATE KEY
```

**Không** dựa vào tên `partner.pem` để quyết định có thể gửi qua email hay lưu trong Git. Kiểm tra nội dung file, phân loại và xử lý theo chính sách.

### 7.2. PKCS12 là lựa chọn thực dụng cho nhiều ứng dụng Java

Từ các JDK hiện đại, `PKCS12` được dùng rộng rãi làm default keystore type. Nó có thể giữ private key và chain, hỗ trợ import/export thuận tiện giữa Java và các công cụ tiêu chuẩn.

Tuy vậy:

- Không phải mọi PKCS12 do các công cụ cũ tạo đều dùng thuật toán bảo vệ tương thích mọi JDK.
- Một số legacy systems dùng JKS và cần chuyển đổi có kế hoạch.
- Một file password-protected vẫn cần file permissions, secret management và kiểm soát backup.
- Không nên để identity store và truststore của nhiều môi trường có thể bị nhầm lẫn.

### 7.3. HSM/KMS khác một file keystore thông thường

Trong hệ thống có yêu cầu bảo mật cao, private key có thể nằm trong **Hardware Security Module** hoặc managed key service; Java kết nối qua PKCS#11 hoặc provider thích hợp. Mục tiêu là **ký/giải mã mà private key không rời vùng bảo vệ**, tùy hệ thống.

Không đưa ra giả định “mọi PKCS11 keystore đều có private key exportable”. Trong nhiều triển khai, **private key cố ý không được export**. Việc rotate, backup và cấp quyền sử dụng key phụ thuộc HSM/KMS.

### 7.4. Password của keystore và password của key entry

Một keystore có thể dùng store password và private-key password riêng, nhưng mức hỗ trợ khác nhau theo định dạng/provider. Đừng mặc định:

```text
store password = key password
```

trong mọi file. Khi `KeyManagerFactory.init(keyStore, keyPassword)` thất bại với `UnrecoverableKeyException`, cần xác minh loại store, alias, key entry password và provider, **không tự động tắt password protection**.

## 8. Tạo key pair và certificate cho môi trường học bằng `keytool`

Các lệnh ở đây **chỉ phục vụ lab/sandbox**, không thay thế quy trình phát hành certificate production qua CA được tổ chức/đối tác phê duyệt.

### 8.1. Tạo PKCS12 identity store bằng keytool

Ví dụ tạo một RSA key pair trong `orders-client-dev.p12`:

```bash
keytool -genkeypair \
  -alias orders-client-dev \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 90 \
  -storetype PKCS12 \
  -keystore ./orders-client-dev.p12 \
  -dname "CN=orders-client.dev.example, OU=Integration, O=Example, C=VN" \
  -ext "SAN=dns:orders-client.dev.example" \
  -ext "EKU=clientAuth"
```

Lệnh dùng cú pháp **Bash**. Trên PowerShell/Windows, chạy `keytool.exe` và dùng cách xuống dòng/quote tương ứng. `keytool` sẽ hỏi password nếu không truyền ở command line.

Kết quả chính:

```text
orders-client-dev.p12
  alias orders-client-dev
  PrivateKeyEntry
    private key
    self-signed demo certificate
```

Certificate tự ký từ `-genkeypair` là **bước đầu của lab**, không phải mặc nhiên được đối tác production trust. Đừng gửi private key/store file cho đối tác; với production phải làm việc với approved CA và key provisioning policy.

**Giá trị RSA 3072 chỉ là ví dụ.** Thuật toán/key size/curve, Key Usage/EKU và thời hạn phải theo security standard + tương thích SOAP partner và WS-Security algorithms. Có thể dùng ECC nếu stack và profile hỗ trợ; không chọn thuật toán chỉ vì một ví dụ code.

### 8.2. Tạo CSR (Certificate Signing Request)

Khi cần CA phát hành certificate từ public key của key entry:

```bash
keytool -certreq \
  -alias orders-client-dev \
  -keystore ./orders-client-dev.p12 \
  -storetype PKCS12 \
  -file ./orders-client-dev.csr \
  -ext "SAN=dns:orders-client.dev.example" \
  -ext "EKU=clientAuth"
```

File CSR có public key/subject/đề nghị extensions và được ký bằng private key tương ứng để chứng minh sở hữu. **Không chứa private key**. CA có thể bỏ qua/thay đổi extensions; phải kiểm tra certificate thật sau khi CA cấp.

### 8.3. Nhận certificate đã được CA ký

Quy trình tổng quát:

1. CA xác minh identity theo quy trình.
2. CA phát hành leaf certificate với subject/public key đã yêu cầu.
3. Nhận leaf certificate và intermediate CA certificates.
4. Xác minh fingerprint/issuer/SAN/EKU/validity qua kênh tin cậy.
5. Import certificate chain vào **đúng key-pair alias** trong PKCS12.
6. Kiểm tra entry vẫn là `PrivateKeyEntry`, chứa certificate chain phù hợp.

Ví dụ (giả sử `client-issued-chain.pem` chứa chain đúng format/đúng thứ tự được công cụ hỗ trợ):

```bash
keytool -importcert \
  -alias orders-client-dev \
  -file ./client-issued-chain.pem \
  -keystore ./orders-client-dev.p12 \
  -storetype PKCS12
```

**Nếu keytool không xây được chain** do thiếu trust của CA cần thiết, hãy import/thiết lập certificates CA đã được xác minh bằng quy trình thích hợp rồi thử lại. Không dùng `-noprompt` hoặc import ngẫu nhiên một CA tải từ Internet để “có dấu thành công”.

### 8.4. Xác minh identity store

```bash
keytool -list -v \
  -keystore ./orders-client-dev.p12 \
  -storetype PKCS12 \
  -alias orders-client-dev
```

Những điều cần thấy:

- Entry type là `PrivateKeyEntry`.
- Certificate chain dài như policy yêu cầu; leaf đứng đúng vị trí.
- Public certificate subject/SAN/issuer phù hợp.
- Certificate validity, fingerprint, KU/EKU đúng.
- Thuật toán/key size tương thích với partner.

Không in/export `PrivateKey` ra stdout hoặc gửi screenshot có secret prompts.

### 8.5. Xuất **chỉ public certificate** để trao đổi với đối tác

```bash
keytool -exportcert -rfc \
  -alias orders-client-dev \
  -keystore ./orders-client-dev.p12 \
  -storetype PKCS12 \
  -file ./orders-client-public.pem
```

Lệnh `-exportcert` xuất certificate public tại alias, **không xuất private key**. Nếu đối tác cần cả certificate chain, cung cấp chain public được chuẩn bị theo policy, không gửi `.p12` chứa PrivateKeyEntry.

Một file public certificate không phải bí mật như private key, nhưng **tính xác thực** của certificate được trao đổi vẫn phải kiểm tra (fingerprint/out-of-band, CA validation, trust policy).

## 9. Tạo truststore để xác minh chứng chỉ của đối tác

Giả sử đối tác HTTPS sử dụng private PKI và đội PKI cung cấp certificate của root CA `partner-root-ca.pem`. Client Java cần **tin CA này theo policy**.

### 9.1. Xác minh CA certificate trước khi import

Trước khi đưa certificate vào truststore, đối chiếu:

- Nguồn nhận certificate có đáng tin và được phê duyệt không?
- SHA-256 fingerprint có khớp với giá trị nhận qua **kênh độc lập** không?
- Certificate `Basic Constraints` cho phép CA, key usage đúng?
- Subject/issuer/validity có phù hợp mục đích không?
- Có thực sự cần tin **root này** hay chỉ được phép tin một partner identity cụ thể?

Không mở rộng trust chỉ vì import certificate làm lỗi kết nối biến mất. Quyết định trust là một thay đổi bảo mật có tác động đến mọi certificate được chain tới anchor đó.

### 9.2. Import CA vào truststore riêng

```bash
keytool -importcert \
  -alias partner-root-ca \
  -file ./partner-root-ca.pem \
  -keystore ./partner-trust.p12 \
  -storetype PKCS12
```

`keytool` có thể hỏi xác nhận trust và password. Không dùng `-noprompt` trong quy trình thủ công khi chưa xác minh fingerprint; trong automation, chỉ import **certificate đã được kiểm định và versioned** với quy trình approval thích hợp.

Kết quả mong đợi:

```text
partner-trust.p12
  alias: partner-root-ca
  entry type: trustedCertEntry
  public CA certificate
```

**Không nên có private key của đối tác trong truststore này.**

### 9.3. Kiểm tra truststore

```bash
keytool -list -v \
  -keystore ./partner-trust.p12 \
  -storetype PKCS12
```

Xác minh `trustedCertEntry`, subject/issuer, fingerprint, validity, basic constraints và phạm vi CA. Alias `partner-root-ca` chỉ là tên entry do người vận hành đặt, **không phải danh tính TLS tự động gửi lên server**.

### 9.4. Một truststore quá rộng hoặc quá hẹp đều có vấn đề

**Quá rộng:** import mọi CA từ nhiều file không rõ nguồn để không còn `PKIX path building failed`. Điều này mở rộng tập certificates có thể được tin quá mức cần thiết.

**Quá hẹp:** chỉ tin chính một leaf certificate, không có kế hoạch rotation. Khi leaf gia hạn/thay key, integration bị ngắt dù CA/đối tác vẫn hợp lệ.

Chọn chiến lược:

- Trust CA theo quy định tổ chức + luôn xác minh hostname/identity.
- Trust CA riêng của đối tác nếu đây là private PKI.
- Leaf/public-key pinning nếu threat model bắt buộc và có kế hoạch rotation.
- Truststore riêng theo đối tác/môi trường khi cần giảm blast radius.

**Không có một lựa chọn duy nhất cho mọi hệ thống.** Hãy đánh đổi phạm vi tin cậy, chi phí vận hành và yêu cầu partner.

### 9.5. JDK default truststore và custom truststore

Java TLS thường dựa trên trust material do runtime/platform và JSSE cấu hình. Nhiều ứng dụng có thể kết nối các public HTTPS endpoints nhờ trust anchors sẵn có.

Khi thay bằng một **custom truststore**, không tự giả định Java sẽ tự merge cả default public CA store. Tùy cấu hình, bạn có thể **vô tình mất** khả năng gọi các public services khác. Với ứng dụng nhiều đối tác:

1. Xác định rõ trust set cần thiết cho từng connection.
2. Cấu hình trust manager theo sender/client thay vì một global override không kiểm soát.
3. Nếu cần kết hợp default CA với private CA, thiết kế **composite trust policy** có chủ đích và kiểm thử; không trust-all.
4. Tránh đưa CA của môi trường test vào production.

### 9.6. Truststore password không phải danh tính client

Password của truststore không phải client certificate, không được gửi trong TLS certificate handshake và không thay thế mTLS. Khi server đòi **client authentication**, bạn phải cung cấp identity keystore/key manager, không phải chỉ tạo thêm truststore.

## 10. Kiểm tra public certificate bằng `openssl`

`openssl` hữu ích để đọc public certificates/chain và điều tra TLS. Không cần export private keys để làm các bước này.

### 10.1. Xem subject, issuer, validity và fingerprint

```bash
openssl x509 \
  -in ./partner-root-ca.pem \
  -noout \
  -subject \
  -issuer \
  -dates \
  -fingerprint \
  -sha256
```

Kết quả được dùng để **đối chiếu**, không phải bằng chứng tự động đã trust:

```text
subject=...
issuer=...
notBefore=...
notAfter=...
sha256 Fingerprint=...
```

Chỉ đọc fingerprint từ một file nhận được qua chính kênh email đã bị giả mạo **không làm file trở nên đáng tin**; fingerprint cần được xác minh qua nguồn/kênh độc lập.

### 10.2. Xem SAN và EKU

```bash
openssl x509 \
  -in ./partner-server.pem \
  -noout \
  -text
```

Trong output, xem `X509v3 Subject Alternative Name`, `Key Usage`, `Extended Key Usage`, `Basic Constraints` và `Signature Algorithm`. Tránh in toàn bộ output vào logs sản xuất; metadata certificate có thể chứa tên hạ tầng nội bộ.

### 10.3. Kiểm tra TLS server trong sandbox được ủy quyền

```bash
openssl s_client \
  -connect soap.partner.example.org:443 \
  -servername soap.partner.example.org \
  -showcerts \
  -verify_return_error
```

Đây là **địa chỉ ví dụ**, chỉ dùng với endpoint bạn được phép kiểm tra. `-servername` đặt SNI để server chọn certificate phù hợp trong môi trường nhiều virtual hosts.

Thông tin cần xem:

- Certificate chain server thực sự gửi.
- TLS protocol/cipher đã thương lượng.
- Verify return code và lỗi dựng path trong trust context của OpenSSL.
- Leaf SAN/issuer/expiration.

**Cảnh báo:** OpenSSL và Java `TrustManager` có thể dùng **trust anchors khác nhau**. `openssl s_client` thành công **không chứng minh** Java SOAP client dùng đúng truststore, và ngược lại. Cần kiểm tra bằng **ứng dụng Java thật**.

### 10.4. Không xuất private key khi chỉ cần xem certificate

Tránh những thao tác như trích toàn bộ private-key contents từ PKCS12 ra PEM không mã hóa chỉ để debug. Nếu chỉ cần xem certificate của key entry, dùng:

```bash
keytool -exportcert -rfc \
  -keystore ./orders-client-dev.p12 \
  -storetype PKCS12 \
  -alias orders-client-dev \
  -file ./client-public-only.pem
```

Với PKCS12 từ nguồn khác, có thể kiểm tra phần certificate **không xuất key** bằng những tùy chọn OpenSSL phù hợp; tuy nhiên thao tác chuyển định dạng cần quy trình vận hành riêng nếu có nguy cơ làm lộ private key.

## 11. Java `KeyStore`: kiểm tra alias và entry mà không rút private key ra

Java API `KeyStore` cho phép mở store theo type, đọc metadata và cấp material cho các provider.

### 11.1. Đọc PKCS12 và liệt kê entries

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.Enumeration;

public final class StoreInspector {

    public static void inspect(Path path, char[] password)
            throws Exception {

        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(path)) {
            store.load(input, password);
        }

        Enumeration<String> aliases = store.aliases();
        while (aliases.hasMoreElements()) {
            String alias = aliases.nextElement();

            String type = store.isKeyEntry(alias)
                ? "KeyEntry"
                : store.isCertificateEntry(alias)
                    ? "TrustedCertificateEntry"
                    : "Other";

            Certificate certificate = store.getCertificate(alias);
            System.out.println("Alias: " + alias);
            System.out.println("Entry type: " + type);

            if (certificate instanceof X509Certificate x509) {
                System.out.println("Subject: " +
                    x509.getSubjectX500Principal());
                System.out.println("Issuer: " +
                    x509.getIssuerX500Principal());
                System.out.println("Not after: " +
                    x509.getNotAfter());
            }

            Certificate[] chain = store.getCertificateChain(alias);
            if (chain != null) {
                System.out.println("Chain length: " + chain.length);
            }
        }
    }
}
```

Code sử dụng Java hỗ trợ `instanceof` pattern matching, và `password` phải đến từ một **secret source** có kiểm soát. Không hard-code password hoặc ghi ra logs. `getCertificate()` và `getCertificateChain()` chỉ lấy public certificate objects; code không xuất private key.

**Lưu ý:** `isKeyEntry(alias)` có thể bao gồm `SecretKeyEntry`, không luôn là `PrivateKeyEntry`. Khi cần kiểm tra chính xác kiểu entry, dùng `entryInstanceOf(alias, KeyStore.PrivateKeyEntry.class)` với policy/format phù hợp.

### 11.2. Chọn alias là trách nhiệm của cấu hình ứng dụng

Một identity store có thể chứa:

```text
orders-client-2026    PrivateKeyEntry
orders-client-2027    PrivateKeyEntry
test-signing          PrivateKeyEntry
```

Key managers/crypto providers có thể chọn identity dựa trên key type, issuer constraints, alias configuration và handshake. Nếu ứng dụng phải dùng **một certificate cụ thể**, cần explicit selection policy (ví dụ alias ở WS-Security, hoặc custom `X509KeyManager` cho TLS nếu provider không chọn đúng).

Đừng mặc định “store có certificate đúng” là **certificate đó sẽ được gửi/ký**. Hãy kiểm tra peer certificate trong mTLS handshake và signer key identifier trong WS-Security response/request thực tế.

### 11.3. Store password và key password

Khi đọc store:

```java
store.load(input, storePassword);
```

Khi key manager dùng private key:

```java
keyManagerFactory.init(store, keyPassword);
```

Hai passwords có thể khác nhau, nhưng phải được cung cấp đúng theo provider/format. Không chuyển chúng thành `String` chỉ để logging. Hãy dùng `char[]` khi API hỗ trợ, làm sạch memory copies theo chính sách và dùng secret manager/container secret mount thay vì hard-code.

## 12. Tạo `SSLContext` với identity và trust tách biệt

Với HTTPS/mTLS, Java JSSE có hai factory chính:

- `KeyManagerFactory` lấy **own identity private key + certificate chain** để TLS trình chứng chỉ và chứng minh sở hữu key.
- `TrustManagerFactory` lấy **trusted certificate anchors** để xác minh chứng chỉ peer.

Sau đó `SSLContext` kết hợp key managers, trust managers và secure random source cho TLS connections.

### 12.1. Code Java minh họa một SSLContext riêng

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class PartnerTlsContextFactory {

    private PartnerTlsContextFactory() {}

    public static SSLContext build(
            Path identityStorePath,
            char[] identityStorePassword,
            char[] keyPassword,
            Path trustStorePath,
            char[] trustStorePassword) throws Exception {

        // Danh tính của client: PrivateKeyEntry + chain.
        KeyStore identity = KeyStore.getInstance("PKCS12");
        try (InputStream in =
                 Files.newInputStream(identityStorePath)) {
            identity.load(in, identityStorePassword);
        }

        KeyManagerFactory keyManagers =
            KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm()
            );
        keyManagers.init(identity, keyPassword);

        // Ai được client tin làm TLS peer.
        KeyStore trust = KeyStore.getInstance("PKCS12");
        try (InputStream in =
                 Files.newInputStream(trustStorePath)) {
            trust.load(in, trustStorePassword);
        }

        TrustManagerFactory trustManagers =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        trustManagers.init(trust);

        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(
            keyManagers.getKeyManagers(),
            trustManagers.getTrustManagers(),
            new SecureRandom()
        );
        return ssl;
    }
}
```

Đây là **factory tạo context**, chưa gắn vào một HTTP sender. Để thật sự sử dụng, phải cấu hình đúng `WebServiceMessageSender`/HTTP client dùng `SSLContext` này, đồng thời giữ **hostname verification** ở lớp HTTPS client.

**Không gọi `SSLContext.setDefault(...)`** cho toàn JVM chỉ vì một đối tác cần private truststore; việc này có thể thay đổi trust/identity của các outbound integrations khác một cách không mong muốn.

### 12.2. Nếu chỉ dùng HTTPS một chiều

Client không cần private-key identity trong TLS khi server không yêu cầu client certificate. Một context cho HTTPS một chiều có thể khởi tạo `ssl.init(null, trustManagers.getTrustManagers(), random)`, hoặc dùng default trusted JSSE context khi policy cho phép.

Ngược lại, **mTLS client cần key managers** có certificate chain/PrivateKeyEntry phù hợp, và vẫn cần **trust managers** để xác minh server.

### 12.3. Không cấu hình TrustManager “accept all”

Anti-pattern:

```java
// Anti-pattern: KHÔNG triển khai trong production.
// X509TrustManager.checkServerTrusted(...) để trống
// hoặc HostnameVerifier luôn trả true.
```

Nếu dùng trust-all và tắt hostname verification, bất kỳ peer giả mạo phù hợp điều kiện network có thể được client chấp nhận, làm lộ SOAP payload, WS-Security tokens hoặc thông tin đăng nhập ở tầng transport.

Giải pháp đúng là sửa certificate chain, trust anchor, SAN/hostname, SNI, mTLS identity và policy.

### 12.4. SSLContext không tự xác minh hostname

`SSLContext`/`TrustManagerFactory` thiết lập TLS trust path và cryptographic context. **HTTPS hostname verification** thường được HTTP client/`SSLSocket` endpoint identification algorithm thực hiện; phải bảo đảm tính năng này được bật trong **message sender thực tế**. Một custom raw TLS socket dùng SSLContext mà không cấu hình endpoint identification có thể không kiểm tra hostname như HTTPS client.

### 12.5. Cấp phát/cached contexts và rotation

Nhiều HTTP clients và SSLContexts được cấu hình **một lần** khi khởi động. Khi file `.p12` được thay trên disk, context đang hoạt động không nhất thiết tự reload.

Khi rotation:

1. Cập nhật secrets/material bằng quy trình đã phê duyệt.
2. Reload/rebuild key managers/trust managers/SSLContext hoặc restart/redeploy phù hợp.
3. Kiểm tra existing pooled TLS connections có thể còn dùng identity/session cũ.
4. Xác minh handshake mới đã dùng certificate mới.
5. Ghi nhận rollback/overlap strategy.

## 13. Spring-WS SOAP server: TLS certificate nằm ở đâu?

SOAP endpoint trong Spring Boot có thể nhận HTTPS trực tiếp hoặc thông qua **reverse proxy/API gateway/load balancer/service mesh**. Điểm kết thúc TLS quyết định **thành phần nào giữ server private key** và **thành phần nào xác minh client certificate**.

### 13.1. Khi Spring Boot trực tiếp nhận HTTPS

Ví dụ cấu hình `application.yml` (giả định server/JDK/Spring Boot hỗ trợ các properties này):

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: "file:/run/secrets/orders-server.p12"
    key-store-type: PKCS12
    key-store-password: "${SERVER_KEYSTORE_PASSWORD}"
    key-alias: orders-server
```

`${SERVER_KEYSTORE_PASSWORD}` là **Spring property placeholder** lấy giá trị từ môi trường/secret source, không phải password viết cứng. Đường dẫn và alias chỉ minh họa. Một số phiên bản Spring Boot có TLS bundles và cách cấu hình khác; kiểm tra runtime và secret mounting thực tế.

Server giữ **private key + certificate chain**. SOAP client xác minh server certificate chain **và hostname** theo trust policy; `WSDL GET` chạy được không tự chứng minh bảo mật chính xác.

### 13.2. Bật client certificate authentication tại server

Khi dùng mTLS, server còn cần trust material để xác minh client certificate:

```yaml
server:
  ssl:
    client-auth: need
    trust-store: "file:/run/secrets/approved-client-ca.p12"
    trust-store-type: PKCS12
    trust-store-password: "${SERVER_TRUSTSTORE_PASSWORD}"
```

Đây là **mảnh YAML bổ sung**, không phải thay thế toàn bộ cấu hình `server.ssl` ở trên. `client-auth=need` minh họa yêu cầu client certificate trong TLS.

Sau TLS authentication, ứng dụng vẫn cần ánh xạ certificate identity tới principal/tenant và kiểm tra **authorization** ở cấp SOAP operation/tài nguyên. Không tự cho rằng CA đã tin thì mọi certificate của CA đều được gọi `CancelOrder`.

### 13.3. Khi TLS kết thúc ở gateway

```mermaid
flowchart LR
    C["External SOAP client"] -->|"HTTPS/mTLS"| G["Gateway\nTLS private key + trust validation"]
    G -->|"Private trusted channel / mTLS theo policy"| S["Spring-WS @Endpoint"]
    S --> G
    G --> C
```

Gateway có thể giữ public TLS server key, Spring-WS app không trực tiếp giữ nó. Nhưng phải bảo vệ đường gateway → app và **không tin các header giả mạo certificate/identity** nếu external client có thể truy cập app trực tiếp.

### 13.4. TLS và SOAP message security có thể dùng certificates khác nhau

```text
api-server-tls.p12    -> HTTPS server private key/certificate
api-soap-signer.p12   -> WS-Security SOAP signing key/certificate
api-soap-recipient.p12 -> WS-Security decryption private key
```

Tách identities theo mục đích là lựa chọn theo policy, không bắt buộc mọi hệ thống dùng ba certificates. Khi dùng một key cho nhiều mục đích, cần kiểm tra KU/EKU, thuật toán và các yêu cầu của đối tác.

## 14. Spring-WS SOAP client: keystore/truststore nằm ở thành phần nào?

`WebServiceTemplate` tạo/điều phối SOAP message và JAXB; **`WebServiceMessageSender`/HTTP client** thực hiện kết nối HTTPS/mTLS. `Wss4jSecurityInterceptor` hoặc crypto provider tương ứng xử lý **message-level WS-Security**.

```text
JAXB request
  -> WebServiceTemplate
     -> SOAP MessageFactory + ClientInterceptor
     -> WS-Security Signature/Encryption (nếu có)
     -> HTTPS MessageSender
        -> SSLContext
           -> KeyManagers (client mTLS identity)
           -> TrustManagers (HTTPS server trust)
  -> SOAP response / Fault
```

### 14.1. Bảng vật liệu khóa từng thành phần

| Thành phần client | Identity/trust material | Khi nào cần |
| --- | --- | --- |
| HTTPS KeyManager | Client TLS private key + certificate chain | Server đòi mTLS |
| HTTPS TrustManager | Trusted server CA/cert + identity validation | HTTPS server authentication |
| WSS4J securement signer | Client SOAP signing private key + signer certificate | SOAP request XML Signature |
| WSS4J encryption | SOAP server **recipient public certificate** | Client mã hóa SOAP request |
| WSS4J signature validator | Trusted server signer public cert/CA | Server ký SOAP response/Fault |
| WSS4J decryption | Client recipient private key | Server mã hóa SOAP response cho client |
| JAXB marshaller | XSD-generated classes | Java ↔ SOAP Body XML |

### 14.2. Gắn `SSLContext` vào đúng HTTP sender

`PartnerTlsContextFactory.build(...)` ở mục 12 tạo một context. Ứng dụng phải **gắn context này vào HTTP client và WebServiceMessageSender thật**:

```text
PartnerTlsContextFactory.build(...)
  -> SSLContext
  -> HTTP client's TLS socket factory / TLS strategy
  -> Spring-WS WebServiceMessageSender
  -> WebServiceTemplate.setMessageSender(...)
```

Code cụ thể khác nhau giữa URLConnection sender, Apache HttpClient 4, HttpClient 5 và các Spring-WS versions. Không sao chép `HttpComponentsMessageSender` của phiên bản cũ vào một stack mới mà không xem API sender/TLS connection manager thực tế.

Khi kiểm thử:

- Phải thấy đúng **client leaf certificate** được chọn trong mTLS handshake.
- Phải xác minh server hostname/SAN (không dùng trust-all).
- Phải kiểm tra truststore có CA phù hợp, chain không thiếu intermediate.
- Phải kiểm tra connect/read timeouts và connection pool không làm giữ identity cũ khi rotate.

### 14.3. JSSE global system properties

```text
javax.net.ssl.keyStore
javax.net.ssl.keyStoreType
javax.net.ssl.keyStorePassword

javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
```

Chúng có thể ảnh hưởng **default JSSE context**, nhưng không tự áp dụng cho HTTP client đã được cấp custom context. Dùng global properties trong JVM gọi nhiều đối tác dễ thay đổi identity/trust của những integrations khác.

Ưu tiên per-partner TLS configuration, hoặc Spring Boot TLS bundles và sender-specific adapters nếu stack hỗ trợ. Không set global SSLContext chỉ vì một đối tác dùng private CA.

### 14.4. Chỉ có truststore chưa đủ cho mTLS

Client có thể tin server CA nên TLS xác minh server thành công, nhưng server vẫn từ chối vì **client không trình certificate**. Khi đó cần cấu hình **identity KeyStore + KeyManager** trên sender, kiểm tra alias, clientAuth EKU, certificate chain, issuer constraints và trust policy phía server.

**Không gửi file PKCS12 chứa private key cho đối tác** để “cài mTLS”. Đối tác cần public certificate/CA theo onboarding policy. Private key phải tiếp tục được giữ ở client/HSM.

## 15. WS-Security và WSS4J: certificate ở cấp SOAP message

Spring-WS có tích hợp **WSS4J**, ví dụ các cấu hình dùng `Wss4jSecurityInterceptor` trong những phiên bản hỗ trợ WSS4J 2.x. Cơ chế này phục vụ các yêu cầu như SOAP XML Signature, XML Encryption, Timestamp hoặc token theo profile. **Không đồng nhất WS-Security với HTTPS/mTLS.**

### 15.1. SOAP request được ký

```mermaid
sequenceDiagram
    participant C as SOAP client
    participant S as SOAP server
    Note over C: Signer private key nằm trong client keystore/HSM
    C->>C: Canonicalize + sign Body/headers theo policy
    C->>S: SOAP Envelope + wsse:Security/ds:Signature
    Note over S: Trust signer public certificate/CA
    S->>S: Verify signature, signed-parts, trust, timestamp/replay
    S-->>C: SOAP response hoặc security Fault
```

Một `wsse:BinarySecurityToken` có thể mang signer public certificate, nhưng **có certificate được gửi trong Header không có nghĩa certificate đó được trust**. Server phải xác minh chữ ký, trust path/identity, scope of signed elements và policy. Một kẻ tấn công có thể gửi certificate tự tạo và ký bằng private key của chính họ; toán học đúng nhưng identity chưa được tin.

### 15.2. SOAP request được mã hóa

```text
Client:
  có public encryption certificate của SOAP server
  tạo content key đối xứng
  mã hóa những phần SOAP XML theo profile
  bảo vệ/bọc content key cho server recipient
  gửi XML Encryption metadata + ciphertext

Server:
  giữ recipient private key
  giải mã/unwrap content key
  giải mã SOAP XML
  kiểm tra security/contract/authorization
```

Không dùng **private key của client signer** để “mã hóa cho server”. **Recipient public certificate** và **sender signing private key** phục vụ hai mục đích khác nhau.

### 15.3. Ma trận request và response

| Thông điệp | Ai ký? | Ai xác minh? | Public certificate dùng để mã hóa cho ai? |
| --- | --- | --- | --- |
| SOAP request C → S | Client private signing key | Server trust client signer cert/CA | **Server recipient public cert** |
| SOAP response S → C | Server private signing key | Client trust server signer cert/CA | **Client recipient public cert** |
| SOAP Fault S → C | Theo fault signing policy | Client verify nếu policy yêu cầu | Theo fault encryption policy |

Nếu một SOAP response được ký bằng certificate khác TLS server certificate, verifier cần trust **đúng SOAP signer** theo WS-Security policy. Không tự lấy chain đã validate ở TLS rồi coi mọi SOAP signature đều hợp lệ.

### 15.4. Các thông số phải thống nhất với đối tác

1. WS-Security actions (Signature, Encryption, Timestamp, UsernameToken...), chiều request và response.
2. Thuật toán ký/hash, key transport/agreement và symmetric encryption cho phép.
3. Signer certificate identities và **trust chain** mỗi chiều.
4. Encryption recipient certificate, key usage, key identifier, certificate rollover.
5. SOAP Body/Header parts nào được ký, đặc biệt WS-Addressing `Action`/`To`/`MessageID` nếu ảnh hưởng routing.
6. Thứ tự sign/encrypt theo profile và policy xác minh sau decrypt.
7. Timestamp/replay window, duplicate XML IDs, XPath/reference transforms.
8. SOAP Fault có cần được ký/mã hóa không và client sẽ xử lý thế nào.
9. Certificate rotation, overlap, multiple aliases, key compromise response.

### 15.5. Phác thảo cấu hình WSS4J

Một cấu hình client-side thường có các trách nhiệm:

```text
Wss4jSecurityInterceptor
  outbound securement:
    Signature (nếu contract yêu cầu)
    signer Crypto -> client signing keystore / HSM
    signer alias -> client private key entry
    private-key password -> secure CallbackHandler
    Encrypt (nếu contract yêu cầu)
    recipient public certificate -> server encryption identity

  inbound validation:
    Signature/TimeStamp/Encrypt theo partner policy
    trusted signer certificates/CA
    client private key khi cần decrypt response
    verify signed parts + identity + replay/timestamp
```

Đây là **sơ đồ vai trò**, không phải một bean hoàn chỉnh. Tên setter, loại `Crypto`, callback handler và security actions thay đổi theo **Spring-WS/WSS4J version**; phải đọc API đúng stack và làm test interoperability với đối tác.

Chỉ cấu hình `Signature` mà không cung cấp signer crypto/alias/password hoặc chỉ nhận một public certificate trong XML **không đủ** để ký/xác minh an toàn.

### 15.6. Bảo vệ XML processing ở cả message layer

WS-Security signature verification có thể xử lý canonicalization, XML References/XPath và certificate parsing — tất cả đều tiêu tốn tài nguyên. Bên cạnh key/trust:

- Giới hạn XML byte size, depth, element count, entity expansion và external resources (XXE).
- Giới hạn số signature references/transforms theo provider policy.
- Phát hiện ID duplication và XML Signature wrapping.
- Chỉ chấp nhận thuật toán/security profiles đã được duyệt.
- Xác minh đúng parts mà business code thực sự sử dụng.

Một chữ ký hợp lệ về toán học **không chứng minh mọi SOAP Header/Body đều đã được ký**, và TLS/mTLS **không thay thế** các yêu cầu này.

## 16. Alias, certificate chain và chọn đúng khóa khi có nhiều identities

Một identity keystore có nhiều entries:

```text
partner-integration.p12
  orders-mtls-2026       -> PrivateKeyEntry / clientAuth
  orders-soap-sign-2026  -> PrivateKeyEntry / XML Signature
  orders-decrypt-2026    -> PrivateKeyEntry / XML Encryption
  orders-mtls-2027       -> PrivateKeyEntry / chuẩn bị rotation
```

### 16.1. Alias không phải Subject/CN/SAN

`orders-mtls-2026` là **tên entry nội bộ**. Đối tác xác minh certificate identity/trust theo TLS/WS-Security policy; alias không được tự gửi làm danh tính certificate trong handshake.

Đừng đặt authorization rule dựa trên alias trong local client key store; phía server không đáng tin alias đó và trong TLS không có trường “Java KeyStore alias”.

### 16.2. TLS key manager có thể tự chọn certificate khác ý muốn

Nếu một `KeyManagerFactory` được khởi tạo từ store có nhiều `PrivateKeyEntry`, key manager sẽ lựa chọn theo key type, issuer hints, TLS algorithm constraints và implementation behavior.

Ví dụ:

```text
Partner A yêu cầu client certificate do CA-A phát hành
Partner B yêu cầu client certificate do CA-B phát hành

Client có cả cert A và B trong một store.
```

Việc “store chứa cert A” chưa chứng minh **cert A được trình cho Partner A**. Cần:

- Per-partner identity store/context nếu phù hợp.
- Hoặc custom `X509KeyManager` alias-selection policy được kiểm thử.
- Quan sát mTLS handshake thực tế và kiểm tra peer identity phía server.
- Không ép alias bằng private hack làm bỏ qua key type/issuer policy.

### 16.3. WS-Security signer alias phải được chọn có chủ đích

Một SOAP signer có thể cấu hình alias/key identifier riêng. Nếu alias chỉ tới certificate encryption recipient thay vì signing key, server có thể không verify được XML Signature hoặc key usage không đúng.

Kiểm tra:

1. Alias tồn tại và là `PrivateKeyEntry`.
2. Private key algorithm tương thích signature algorithm/policy.
3. Certificate chain của alias đúng signer identity.
4. Password handler trả password đúng entry, không log ra.
5. Server trust certificate/CA của signer.
6. Signed parts cover Body và những headers bắt buộc.

### 16.4. Hai certificates có thể cùng subject nhưng khác key/serial

Trong rotation, certificate cũ và mới có thể cùng `Subject`/SAN nhưng khác public key hoặc serial. Client không nên dùng Subject string như khóa lookup duy nhất. Cần quản lý issuer, serial, fingerprint, validity, purpose và version trong inventory.

### 16.5. Một cert hợp lệ về TLS chưa chắc hợp lệ cho SOAP signing

Certificate có `serverAuth` và server SAN đúng HTTPS hostname có thể được trust cho TLS, nhưng SOAP signer policy có thể yêu cầu **client SOAP signing certificate** với key usage/identity và trust riêng. Không gộp trust decisions chỉ vì cả hai dùng X.509.

## 17. Bảo vệ private key và mật khẩu trong production

### 17.1. Quy tắc tối thiểu

- **Không commit** `.p12`/`.pfx` chứa private key, `.key`, PEM private keys, store passwords hoặc secret snapshots vào source control.
- Không gửi private key qua email/chat/ticket cho đối tác hoặc đồng nghiệp chỉ cần verify public certificate.
- Dùng secret manager, protected mounts, restricted file permissions và identity-based access.
- Không ghi passwords/private key bytes trong stack traces, CI logs, debugging dumps hoặc screenshots.
- Không để container image bao gồm production key material.
- Không dùng cùng certificate/key cho dev, staging, production nếu security policy yêu cầu tách môi trường.
- Kiểm tra backups và artifact retention: file bị xóa khỏi working directory chưa chắc biến mất khỏi backups/build caches.

### 17.2. Mức độ nhạy cảm khác nhau

| Vật liệu | Có thể chia sẻ với đối tác? | Yêu cầu bảo vệ |
| --- | --- | --- |
| Public leaf certificate `.crt/.pem` | Có, qua kênh được xác minh | Authenticity/integrity, inventory |
| Public CA certificate | Có, khi được phê duyệt | Kiểm chứng fingerprint/trust policy |
| CSR `.csr` | Có, gửi CA/issuer | Không chứa private key nhưng chứa identity/public metadata |
| Private key `.key` | **Không** | Bí mật nghiêm ngặt, HSM/secret manager |
| PKCS12 chứa `PrivateKeyEntry` | **Không** | File + password + access control |
| Store/key password | **Không** | Secret manager/rotation |
| Certificate fingerprint | Có trong ngữ cảnh kiểm chứng | Nên đối chiếu qua kênh độc lập |
| SOAP message signature | Được gửi trên wire theo contract | Không tiết lộ private key |

### 17.3. Password protection không thay thế access control

Một PKCS12 có password nhưng được đăng công khai vẫn có rủi ro lớn (brute-force, offline analysis, tái sử dụng password). Chỉ file permissions không đủ nếu private key đã bị copy vào CI artifact.

Dùng **defense in depth**: permission, encryption, secret distribution, workload identity, backup policy, audit logs và kế hoạch phản ứng sự cố.

### 17.4. Không tạo String không cần thiết từ password

Java `KeyStore.load(...)` nhận `char[]`. Không in password, và nên xóa temporary arrays khi không cần:

```java
char[] password = secretSupplier.getPassword();
try {
    // Chỉ dùng password để mở keystore / key manager.
    // Không log hoặc đưa vào exception text.
} finally {
    java.util.Arrays.fill(password, '\0');
}
```

`secretSupplier` là abstraction giả định. Việc xóa `char[]` là biện pháp giảm lifetime của bản sao memory, **không đảm bảo JVM/provider xóa mọi bản sao nội bộ**. Không coi nó thay thế HSM/secret manager.

### 17.5. Private key có thể không được export

Khi dùng HSM/PKCS11, crypto operations có thể được thực hiện trong thiết bị/service bảo vệ khóa. Việc “không thể tải `PrivateKey.getEncoded()`” có thể là hành vi bảo mật mong muốn, không phải lỗi. Ứng dụng nên dùng provider API thay vì cố export key rồi đưa vào file PEM.

## 18. Vòng đời certificate: phát hành, gia hạn, thay khóa và thu hồi

Một SOAP integration chạy được hôm nay vẫn có thể ngừng hoạt động khi certificate hết hạn hoặc bị thay đổi. Certificate management phải là **quy trình vận hành liên tục**, không chỉ thao tác `keytool` khi triển khai lần đầu.

### 18.1. Những loại thay đổi khác nhau

| Thay đổi | Public key đổi? | Truststore thường phải đổi? | Ảnh hưởng |
| --- | --- | --- | --- |
| Renew leaf, giữ cùng key, cùng CA | Không | Thường không nếu tin CA và identity không đổi | Leaf serial/validity/fingerprint mới; pinning theo cert có thể phải đổi |
| Re-key leaf, cùng CA | Có | Thường không nếu trust CA | WS-Security recipient/signer cert có thể phải cập nhật |
| Đổi intermediate CA | Có thể | Tùy chain/trust anchors | Peer cần gửi đúng chain mới |
| Đổi root CA/trust anchor | Không nhất thiết | **Có thể cần** cập nhật | Phải overlap old/new trust với kế hoạch |
| Đổi TLS hostname | Không nhất thiết | Chưa đủ nếu chỉ sửa trust | Cần certificate SAN và endpoint URL tương ứng |
| Đổi signer identity WS-Security | Có thể | Có thể cần trust/cert registration | Partner phải tin signer mới theo policy |
| Đổi encryption recipient certificate | Có thể | Sender cần public cert mới | In-flight messages có thể còn cần old private key |
| Private key bị lộ | Có, phải thay key | Cần revoke/distrust theo policy | Incident response, invalidate credentials/certs |

### 18.2. Rotation không gián đoạn với overlapping window

Một kế hoạch điển hình:

```mermaid
flowchart TD
    A["1. Inventory cert/key/aliases/consumers"] --> B["2. Tạo key pair mới trong vùng bảo vệ"]
    B --> C["3. CA cấp certificate + chain"]
    C --> D["4. Phân phối public certificate/CA cho verifier"]
    D --> E["5. Verifier trust cả old/new theo policy"]
    E --> F["6. Chuyển signer/TLS identity sang cert mới"]
    F --> G["7. Test handshake + SOAP signed/encrypted messages"]
    G --> H["8. Hết overlap: revoke/remove old material"]
```

Với **server TLS certificate** do cùng CA phát hành, nhiều client chỉ cần chain mới mà không phải import leaf mới, nếu vẫn dùng CA trust và SAN hợp lệ. Với **WS-Security** có pinning hoặc cấu hình encryption recipient by certificate, đối tác thường phải cập nhật certificate public trước khi chuyển traffic.

### 18.3. Ký response trong giai đoạn rotation

Giả sử SOAP server chuyển từ signer `server-sign-2026` sang `server-sign-2027`. Nếu client chỉ trust public signer cũ, nó có thể từ chối chữ ký mới dù HTTPS vẫn hoàn toàn hợp lệ.

Quy trình:

1. Phân phối **public certificate signer mới** và các required chain/cert identifiers.
2. Client cho phép xác minh old/new signer trong thời gian overlap, theo policy.
3. Server đổi signer alias một cách được kiểm soát.
4. Client test SOAP normal response **và Fault response**.
5. Giảm/phế bỏ trust cho certificate cũ khi hết kỳ overlap.

### 18.4. Giải mã message còn đang xử lý

Nếu client/server thay **encryption private key**, những SOAP messages đã mã hóa bằng **public certificate cũ** có thể vẫn cần old private key để decrypt trong một thời gian. Do đó **không xóa old decryption key ngay** nếu còn in-flight/enqueued encrypted messages hợp lệ.

Thời hạn giữ old decryption capability phải dựa trên queue retention, replay controls, transaction SLAs và policy bảo mật. Khi key compromise, ưu tiên an ninh có thể buộc loại bỏ/quarantine messages theo incident procedure thay vì tiếp tục decrypt tất cả.

### 18.5. Giám sát hết hạn

Một inventory cần lưu:

```text
partner / environment / operation
certificate purpose: tls-server / tls-client / soap-sign / soap-encrypt
alias / store reference (không lưu password)
issuer / subject / SAN / serial / fingerprint
notBefore / notAfter
key algorithm / KU / EKU
CA chain / trust anchor source
owner / renewal contact / rotation procedure
current + next certificate status
```

Đặt cảnh báo trước hạn hết hiệu lực theo SLA của tổ chức (ví dụ 30/14/7 ngày là **minh họa**, không phải quy tắc bắt buộc). Nếu dùng certificate cấp ngắn ngày/automation, threshold phải phù hợp chu kỳ và hệ thống monitoring.

### 18.6. Khi private key bị lộ

Một private key compromise không thể được khắc phục chỉ bằng đổi store password. Kẻ có bản sao key có thể vẫn giả mạo danh tính khi certificate còn được trust.

Các bước cần xem xét:

- Kích hoạt security incident response, điều tra phạm vi lộ.
- Ngừng sử dụng key cũ, tạo **key pair mới** trong môi trường sạch.
- Thu hồi certificate khi hệ sinh thái/policy hỗ trợ; cập nhật CRL/OCSP hoặc explicit deny list.
- Phân phối trust/certificate mới và chuyển traffic có kiểm soát.
- Rà soát logs về chữ ký/giao dịch đáng ngờ, credentials liên quan.
- Loại bỏ key cũ khỏi runtime, backups, CI artifacts và storage theo quy trình khả thi.

**Không chỉ renew certificate với cùng private key đã bị lộ.**

## 19. Chẩn đoán lỗi certificate, keystore và truststore

### 19.1. Các tình huống phổ biến

| Dấu hiệu/log | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `PKIX path building failed` | Client không xây được chain tới trusted anchor | Server certificate chain, intermediate CA, client truststore |
| `unable to find valid certification path` | CA không được tin/chain không đầy đủ | Trust anchor source, certificate chain |
| `No subject alternative names matching ...` | Hostname/SAN sai | URI gọi thật, SNI, SAN và proxy |
| `CertificateExpiredException` | Leaf/CA certificate hết hạn | Validity, current time, rotation |
| `CertificateNotYetValidException` | Certificate chưa đến `Not Before` hoặc clock sai | Time sync, certificate validity |
| `UnrecoverableKeyException` | Key password sai hoặc provider/entry mismatch | Store password vs key password, alias, store type |
| `Keystore was tampered with, or password was incorrect` | Store không mở được | File đúng? Store format/password/provider? |
| `No such algorithm` / `algorithm constraints` | Thuật toán/key size không được hỗ trợ hoặc bị policy chặn | JDK/provider, TLS/WS-Security profiles |
| `handshake_failure` | Client/server không tìm được giao thức/cipher/cert phù hợp | TLS versions, client cert, issuer constraints, auth policy |
| `bad_certificate` | Peer không chấp nhận certificate | Chain, KU/EKU, identity, revocation, policy |
| `certificate_unknown` | Peer không tin certificate hoặc không phù hợp | Logs phía peer, issuer/truststore, hostname/policy |
| `No available authentication scheme` | Client không thể trình cert phù hợp trong TLS handshake | KeyManager, aliases, EKU, algorithm, issuer request |
| mTLS thất bại dù `partner-trust.p12` đúng | Client chưa có identity KeyManager | Client PrivateKeyEntry + sender SSLContext |
| HTTPS thành công nhưng SOAP Signature invalid | WS-Security là lớp độc lập | Signer crypto, alias, signed parts, trust, canonicalization |
| SOAP Decryption failure | Recipient private key/cipher profile sai | Encryption cert ID, private key alias, algorithms, old/new key |
| `Cannot find key for alias ...` | Alias không tồn tại hoặc sai store | `keytool -list`, runtime config, key entry type |
| SOAP Fault `FailedCheck` (profile-dependent) | Chữ ký/trust/security policy lỗi | WSS4J validation config, trusted signer, timestamps |
| Chỉ một đối tác lỗi sau đổi truststore | Global JSSE trust bị thay | Per-partner SSLContexts, default roots đã bị loại |
| Rotated PKCS12 trên disk nhưng vẫn gửi cert cũ | Context/pool chưa reload | Recreate/reload HTTP sender, TLS sessions, restart policy |
| WSDL tải được nhưng SOAP POST báo lỗi TLS | Metadata endpoint/transport khác | Endpoint HTTPS URI, redirect, SNI, client cert |

Các exception/error texts phụ thuộc JDK, HTTP sender, OS, reverse proxy và WSS4J version; **không chẩn đoán chỉ dựa vào một substring**. Đọc nested causes, TLS handshake direction, HTTP response nếu có và SOAP Fault nếu đã vào SOAP layer.

### 19.2. Quy trình chẩn đoán theo lớp

```text
1. Có TCP/HTTPS connection tới đúng host/port không?
     no  -> DNS / firewall / connect timeout
     yes
2. TLS handshake có hoàn thành không?
     no  -> server chain / trust / hostname / client cert /
            algorithm / revocation / SNI
     yes
3. HTTP request tới đúng SOAP endpoint/path không?
     no  -> proxy/URL/context path/HTTP auth
     yes
4. SOAP Envelope, WS-Security Header có đúng contract không?
     no  -> JAXB/WSDL/WS-Security format
     yes
5. XML Signature/decryption/trust có thành công không?
     no  -> signer/recipient key, alias, certificate trust,
            signed parts, algorithms, timestamps
     yes
6. XSD/endpoint/business xử lý thế nào?
     -> SOAP response hoặc business Fault
```

### 19.3. Khi nào dùng debug TLS?

Trong sandbox hoặc phiên điều tra được phê duyệt, Java JSSE có các tùy chọn:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
```

Hãy bật có kiểm soát, tắt sau khi điều tra và bảo vệ logs: debug có thể chứa metadata phiên TLS/certificate, endpoints và chi tiết cấu hình. Không bật verbose SSL debugging thường trực trong production hoặc gửi raw logs công khai.

### 19.4. Dùng `openssl s_client` không thay thế kiểm thử Java

`openssl s_client` có thể cho thấy chain/SNI ở endpoint, nhưng Java `TrustManager` và HTTP sender có truststore, TLS policy và certificate selection riêng. Nếu OpenSSL thành công nhưng Java thất bại, kiểm tra **đúng runtime keystore/truststore**, không vội kết luận “do Java bug”.

### 19.5. Phân biệt TLS handshake error với SOAP Fault

Nếu TLS thất bại, server SOAP application có thể chưa đọc được request. Client sẽ nhận I/O/handshake error, **không phải `SoapFaultClientException`**.

Nếu HTTPS hoàn thành, server nhận SOAP nhưng WSS4J từ chối chữ ký, phía client có thể nhận **SOAP security Fault** theo profile — hai lỗi cần remediation khác nhau.

## 20. Kiểm thử certificate và key configuration

### 20.1. Những điều có thể unit-test

Một unit test có thể mở PKCS12 test fixture (chỉ gồm key/cert được tạo cho test) và assert:

- Alias tồn tại.
- Entry đúng `PrivateKeyEntry` hoặc `trustedCertEntry`.
- Certificate validity/issuer/SAN/EKU phù hợp test profile.
- Chain length và key algorithm đúng.
- Không lẫn test alias/prod alias.

Ví dụ JUnit 5 test metadata:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.X509Certificate;
import org.junit.jupiter.api.Test;

class IdentityStoreTest {

    @Test
    void hasExpectedClientIdentity() throws Exception {
        // Sử dụng fixture riêng trong sandbox, KHÔNG phải prod store.
        Path path = Path.of("test-data/orders-client-test.p12");
        char[] password = TestSecrets.clientStorePassword();

        try {
            KeyStore store = KeyStore.getInstance("PKCS12");
            try (InputStream in = Files.newInputStream(path)) {
                store.load(in, password);
            }

            String alias = "orders-client-test";
            assertTrue(
                store.entryInstanceOf(
                    alias, KeyStore.PrivateKeyEntry.class
                )
            );

            X509Certificate leaf =
                (X509Certificate) store.getCertificate(alias);
            assertNotNull(leaf);
            leaf.checkValidity();

            assertTrue(
                store.getCertificateChain(alias).length >= 1
            );
        } finally {
            java.util.Arrays.fill(password, '\0');
        }
    }
}
```

`TestSecrets` và `test-data/orders-client-test.p12` là **test fixtures cần tự tạo** bằng key material giả lập. Đoạn này không kiểm tra toàn bộ PKIX trust path/hostname/EKU; cần integration test riêng. Không copy production private key vào test repository.

### 20.2. HTTPS/mTLS integration test bắt buộc

Một test server/sandbox được cấu hình:

1. Server có key/cert chain được CA test cấp.
2. Client trust đúng test CA, với hostname đúng SAN.
3. Server yêu cầu mTLS; client có test PrivateKeyEntry.
4. Gửi SOAP request thật qua `WebServiceTemplate`/HTTP sender thực.
5. Kiểm tra server nhìn thấy **đúng client cert identity**.
6. Kiểm tra SOAP response bình thường và SOAP Fault.

### 20.3. Negative tests chứng minh policy không bị bỏ qua

| Mã test | Tình huống | Mong đợi |
| --- | --- | --- |
| TLS-01 | Server chain + SAN hợp lệ | HTTPS thành công |
| TLS-02 | Server certificate do CA không tin | Handshake thất bại |
| TLS-03 | Server SAN không khớp URL | HTTPS bị từ chối |
| TLS-04 | Leaf hết hạn/chưa hiệu lực | Từ chối theo validity policy |
| TLS-05 | Thiếu intermediate chain | Fail hoặc không build chain nếu không có alternate trusted path |
| TLS-06 | Client cert không cấu hình, server đòi mTLS | Authentication thất bại |
| TLS-07 | Client cert do CA không được server trust | Authentication thất bại |
| TLS-08 | Client alias sai/private-key entry không có | Không thể trình cert đúng |
| TLS-09 | Store/key password sai | Config hoặc key-loading failure |
| TLS-10 | Cert đúng nhưng caller không có quyền `CancelOrder` | TLS pass, business authorization deny |
| SOAP-01 | TLS pass, signer WS-Security không tin | SOAP security validation fail |
| SOAP-02 | TLS pass, SOAP Body bị sửa sau ký | Signature validation fail |
| SOAP-03 | SOAP response encrypted cho public cert cũ | Chỉ decrypt nếu matching old private key vẫn được phép |
| SOAP-04 | SOAP Signature thiếu Body trong signed parts | Reject theo security policy |
| ROT-01 | Old/new signer overlap | Cả hai verify trong overlap window nếu policy cho phép |
| ROT-02 | Remove old trust khi hết overlap | Old signer không còn được chấp nhận |

### 20.4. `MockWebServiceServer` không kiểm tra TLS handshake

Spring-WS `MockWebServiceServer` hữu ích cho JAXB, callback, SOAP Fault và interceptor behavior, nhưng nó **không mở network socket TLS thật**. Tương tự `MockWebServiceClient` không thay thế HTTPS web-server configuration test.

Để xác nhận mTLS, phải có **HTTP/TLS integration test** đi qua sender/server/proxy thật hoặc sandbox tương đương. Để xác nhận SOAP XML Signature, cần test **WSS4J signer/verifier và chính xác XML parts được ký**, không chỉ assert header `wsse:Security` tồn tại.

### 20.5. Đo kết quả, không chỉ nhìn logs

Một bài test đúng phải chứng minh:

- Client **từ chối** untrusted server thay vì trust-all.
- Server **từ chối** unknown client certificate khi mTLS bắt buộc.
- SOAP signed message **không** được xử lý nghiệp vụ khi signature/trust/signed parts fail.
- Response encryption cần đúng recipient private key.
- Không có side effects khi authentication/authorization bị từ chối.
- Khi rotation, những kết nối **mới** sử dụng material đúng version.

## 21. Case study: tích hợp đơn hàng yêu cầu mTLS và SOAP message signing

### 21.1. Bối cảnh

Công ty A xây SOAP client bằng Spring-WS gọi `https://soap.partner-b.example.org/orders`. B yêu cầu:

1. HTTPS server certificate của B phải được client A xác minh.
2. A phải chứng minh danh tính bằng **mTLS client certificate**.
3. A phải **ký SOAP Body** bằng certificate đã đăng ký với B.
4. B ký SOAP response; A phải xác minh signer theo trust policy.
5. B có thể gửi SOAP Fault khi signature sai; SOAP client cần phân biệt security Fault và TLS handshake error.

Hệ thống đồng thời sử dụng XSD/WSDL để sinh JAXB `SubmitOrderRequest`/`SubmitOrderResponse`, có `WebServiceTemplate` và `Wss4jSecurityInterceptor`.

### 21.2. Inventory khóa và certificates

| Material | Chủ sở hữu | Nằm ở đâu? | Dùng để làm gì? |
| --- | --- | --- | --- |
| A client TLS private key | A | A mTLS identity store/HSM | A chứng minh danh tính trong mTLS |
| A client TLS public certificate/chain | A phát hành/CA | A store + B trust/policy | B xác minh mTLS client identity |
| B server TLS private key | B | B server identity store/HSM | B chứng minh HTTPS server identity |
| B server TLS public certificate/chain | B | B TLS handshake + A trust anchors | A xác minh server chain/hostname |
| A SOAP signing private key | A | A WS-Security signer store/HSM | A ký SOAP request |
| A SOAP signing public certificate | A | B WS-Security trusted signer config | B xác minh request signature |
| B SOAP signing private key | B | B WS-Security signer store/HSM | B ký SOAP response/Fault |
| B SOAP signer public certificate | B | A WS-Security validation config | A xác minh SOAP signature |

Trong một triển khai, A TLS client identity và A SOAP signer có thể cùng một certificate **nếu hai bên đồng ý và policy cho phép**. Bảng tách mục đích để người học không nhầm trách nhiệm.

### 21.3. Luồng end-to-end

```mermaid
sequenceDiagram
    participant A as A / Spring-WS Client
    participant B as B / TLS + SOAP Server
    Note over A: Trust B TLS CA + hostname
    Note over B: Trust A TLS client CA
    A->>B: TLS handshake
    B-->>A: B TLS server certificate chain
    A-->>B: A TLS client certificate + proof of private key
    Note over A: A private SOAP signing key
    A->>A: JAXB marshal + sign SOAP Body
    A->>B: HTTP POST SOAP + wsse:Security
    Note over B: Trust A SOAP signer certificate
    B->>B: Verify SOAP XML Signature + authorization + XSD
    B->>B: Xử lý nghiệp vụ
    Note over B: B private SOAP signing key
    B-->>A: SOAP response + B XML Signature
    Note over A: Trust B SOAP signer certificate
    A->>A: Verify signature + JAXB unmarshal
```

**Có hai bước xác minh khác nhau** tại A:

- Ở TLS handshake: A tin B HTTPS server certificate/CA và hostname.
- Ở SOAP response: A tin **B SOAP signer** và XML Signature có signed-parts policy đúng.

Tương tự, B xác minh A ở mTLS **và** xác minh A SOAP signing identity. Thành công ở một bước không thể thay thế bước còn lại.

### 21.4. Các cấu hình ứng dụng phải chuẩn bị

Phía client A:

```text
orders-tls-client.p12
  PrivateKeyEntry: a-orders-mtls

partner-b-tls-trust.p12
  trustedCertEntry: b-tls-approved-ca

orders-soap-signer.p12
  PrivateKeyEntry: a-orders-soap-signer

partner-b-soap-trust.p12
  trustedCertEntry(s): b-soap-approved-signer/CA
```

Đây là một **cách tách store theo mục đích**, không phải format bắt buộc của mọi triển khai. Server B phải có bộ material tương ứng của mình. Passwords lưu trong secret manager, không nằm trong WSDL hoặc source code.

### 21.5. Ba lỗi và cách chẩn đoán

**Lỗi A — TLS chưa hoàn thành:**

```text
SSLHandshakeException: PKIX path building failed
```

Kiểm tra A **truststore cho HTTPS server B** và chain/SAN/issuer; chưa có bằng chứng SOAP request đã tới `@Endpoint`.

**Lỗi B — TLS pass nhưng SOAP Fault security:**

```text
SOAP Fault: message signature verification failed
```

Kiểm tra A SOAP signer private key alias, certificate chain/trust tại B, signed parts, timestamp/canonicalization và profile WSS4J. Không sửa TLS truststore chỉ vì Fault nói đến “certificate”.

**Lỗi C — SOAP response không unmarshal được:**

```text
JAXB unexpected element {urn:example:orders:v2}SubmitOrderResponse
```

TLS và WS-Security có thể đều đã pass; lỗi nằm ở **contract/XSD/JAXB version**. Không import thêm CA để sửa root QName.

### 21.6. Tiêu chí nghiệm thu

Một test thành công cần chứng minh:

- A từ chối TLS server certificate giả/không tin hoặc SAN sai.
- B từ chối A khi thiếu client certificate, sai CA hoặc sai authorization.
- B từ chối SOAP Body bị sửa sau khi ký, dù mTLS đã pass.
- A từ chối SOAP response có signer không được tin, dù HTTPS đã pass.
- A và B dùng đúng aliases/chains trong log metadata an toàn.
- Cả successful SOAP response và SOAP Fault đi qua đúng security policy.
- Không có private key/password trong file chia sẻ, CI logs hoặc request XML.

## 22. Bài thực hành có đáp án

### Bài 1. Private key có được gửi cho đối tác không?

Đối tác muốn kiểm tra chữ ký SOAP của client A và yêu cầu “gửi file `orders-client.p12` cùng password”.

**Đáp án:** Không gửi file có PrivateKeyEntry/password. Đối tác cần **public signer certificate/CA và trust policy** để verify SOAP Signature. Nếu họ yêu cầu keystore chứa private key, phải làm rõ và sửa quy trình chia sẻ.

### Bài 2. Certificate có phải là private key không?

Bạn có một file:

```text
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
```

**Đáp án:** Đây là một PEM-encoded certificate, có public key và X.509 metadata, **không chứa private key**. Tuy nhiên cần xác minh fingerprint/issuer/trust trước khi dùng; “public” không đồng nghĩa “đáng tin”.

### Bài 3. `.pem` có luôn được phép công bố không?

Một PEM khác bắt đầu bằng `-----BEGIN PRIVATE KEY-----`.

**Đáp án:** Không. PEM chỉ là encoding/container văn bản; file này chứa **private key bí mật**. Không chia sẻ, đưa vào Git hoặc log. Kiểm tra `BEGIN...` label và mục đích trước khi xử lý.

### Bài 4. Keystore và truststore khác nhau ở đâu?

Client A gọi HTTPS B. A có `a-identity.p12` với PrivateKeyEntry và `b-trust.p12` có trustedCertEntry.

**Đáp án:** `a-identity.p12` cung cấp danh tính/private key mà **A sở hữu** (cần cho mTLS hoặc các mục đích được cấu hình). `b-trust.p12` chứa certificate/CA mà **A chấp nhận** để xác minh B. Hai store có thể cùng PKCS12 format nhưng chức năng khác.

### Bài 5. HTTPS một chiều có cần client private key không?

Server B chỉ yêu cầu HTTPS server authentication, không có mTLS.

**Đáp án:** Không nhất thiết. A cần verify B certificate chain/hostname; mTLS client key không bắt buộc. Tuy nhiên A có thể vẫn cần SOAP signing key riêng nếu WS-Security yêu cầu ký message.

### Bài 6. Đã trust B CA nhưng mTLS vẫn bị từ chối

Client A chỉ cấu hình `TrustManagerFactory`, chưa có `KeyManagerFactory`.

**Đáp án:** A có thể xác minh B server nhưng không trình được **client certificate/private key** cho mTLS. Cần A identity keystore với `PrivateKeyEntry`, key manager, alias/certificate phù hợp và server B trust CA phát hành certificate A.

### Bài 7. SAN và hostname

Client kết nối `https://soap.partner.example.org`, server cert có SAN `DNS:api.partner.example.org` nhưng không có SAN tương ứng `soap.partner.example.org`.

**Đáp án:** HTTPS hostname verification phải từ chối nếu không có matching SAN theo policy. Sửa URL/endpoint certificate một cách được phê duyệt; không tắt hostname verification.

### Bài 8. Vì sao biết CA chưa đủ để authorization?

Một client cert được CA tin cậy cấp, nhưng chủ sở hữu không được phép hủy đơn của tenant khác.

**Đáp án:** CA trust chứng minh identity theo PKI, không tự cấp quyền trên business resources. Server phải ánh xạ certificate identity tới principal/tenant và kiểm tra quyền operation/resource.

### Bài 9. Root CA và intermediate CA

Client A tin root CA của B, nhưng B chỉ gửi leaf certificate và thiếu intermediate cần thiết.

**Đáp án:** Có thể không dựng được PKIX chain. B nên trình đầy đủ leaf + intermediate certificates hoặc client dùng nguồn intermediates được cho phép, không import bừa CA hoặc trust-all.

### Bài 10. `PKIX path building failed` có phải SOAP Fault không?

Client nhận `SSLHandshakeException` trước HTTP POST.

**Đáp án:** Không. Đây là lỗi TLS certificate validation/transport, thường xảy ra **trước SOAP processing**. Không có lý do suy rằng `@Endpoint` đã ném SOAP Fault. Kiểm tra truststore, issuer/chain/hostname và TLS logs.

### Bài 11. Import root CA của đối tác vào identity store có đủ không?

Client import root CA vào `client-identity.p12` nhưng chưa cấu hình trust manager.

**Đáp án:** Không tự bảo đảm TLS server verification dùng certificate đó. Cần đưa approved CA vào trust material **thực sự được TrustManager/HTTPS sender sử dụng**; identity store là vai trò cho own keys, không thay thế đúng trust configuration.

### Bài 12. Alias có được gửi trên TLS wire không?

Client có alias `orders-mtls-2027`.

**Đáp án:** Alias là tên entry trong Java KeyStore. Peer thấy certificate chain và bằng chứng sở hữu private key, không phải tên alias. Peer authorization phải dựa vào validated certificate identity, không dựa vào alias local của client.

### Bài 13. Store password và key password

`KeyStore.load(...)` thành công nhưng `KeyManagerFactory.init(...)` ném `UnrecoverableKeyException`.

**Đáp án:** Có thể store password đúng nhưng **private-key entry password sai**, entry/provider không phù hợp hoặc thuật toán bảo vệ key không tương thích. Kiểm tra alias, type, provider và key password được nạp từ secret manager. Không tắt password hoặc tạo trust-all để khắc phục.

### Bài 14. Certificate signer khác TLS server certificate

SOAP response qua HTTPS hợp lệ nhưng WSS4J báo signer certificate không được tin.

**Đáp án:** HTTPS TLS trust và WS-Security signer trust là **hai validation decisions độc lập**. Kiểm tra certificate signer trong `wsse:Security`, XML Signature, WSS4J validation crypto/truststore, key identifier và partner policy. Không suy TLS pass thì SOAP signature pass.

### Bài 15. Ký SOAP request bằng khóa nào?

Client muốn ký `SubmitOrderRequest` để đối tác verify.

**Đáp án:** Client dùng **private signing key của chính mình** để tạo XML Signature; đối tác dùng client signer **public certificate** và trust policy để xác minh. Không dùng private key của server, không đưa private key vào SOAP message.

### Bài 16. Mã hóa SOAP request bằng khóa nào?

Client muốn mã hóa `SubmitOrderRequest` để chỉ server B đọc được.

**Đáp án:** Client dùng **public encryption certificate của B** để bảo vệ content key theo WS-Security XML Encryption profile. B dùng **private key của B** để decrypt. Private signing key của client không phải recipient decryption key.

### Bài 17. Có certificate trong BinarySecurityToken thì đã trust chưa?

Server nhận `wsse:BinarySecurityToken` chứa certificate tự ký của client và chữ ký toán học đúng.

**Đáp án:** Chưa. Server cần kiểm tra **trust/identity của signer** theo policy, chain, signed-parts, timestamps/replay và authorization. Client có thể tự tạo key/certificate; chữ ký hợp lệ chỉ chứng minh sử dụng matching private key.

### Bài 18. MockWebServiceServer có kiểm tra mTLS không?

Test sử dụng `MockWebServiceServer` và assert SOAP response đúng JAXB.

**Đáp án:** Không. Mock server Spring-WS không thực hiện TLS handshake thực; cần test HTTP/mTLS integration với key manager/trust manager/server/sender thật. Mock test vẫn hữu ích cho SOAP Fault và message processing.

### Bài 19. Gia hạn leaf cùng CA

Server B renew certificate, subject/SAN không đổi, CA chain vẫn được tin.

**Đáp án:** Client **tin CA** thường không cần import leaf mới nếu chain/hostname/validity/policy đúng. Nếu client **pin certificate fingerprint hoặc trust leaf trực tiếp**, phải có kế hoạch cập nhật/overlap và regression test.

### Bài 20. Root CA rollover

Đối tác B chuyển từ root CA cũ sang root CA mới nhưng A chỉ trust CA cũ.

**Đáp án:** A có thể không build chain cho certificate mới. Cần xác minh CA mới qua quy trình độc lập, import/phê duyệt trust trước khi B cutover, cho phép overlap có kiểm soát rồi loại bỏ trust CA cũ theo kế hoạch.

### Bài 21. Certificate hết hạn nhưng ứng dụng vẫn dùng context cũ

Đội vận hành thay `orders-client.p12` trên disk nhưng client vẫn trình old certificate.

**Đáp án:** `SSLContext`/key manager/HTTP pool đã được khởi tạo từ material cũ có thể không tự reload. Phải reload/rebuild context/sender hoặc restart, kiểm tra new connections và TLS session/pooling behavior.

### Bài 22. Private key bị lộ, chỉ thay password đã đủ?

File `client.p12` bị đưa vào public CI artifact. Đội dự án đổi password keystore nhưng giữ key pair và certificate cũ.

**Đáp án:** Chưa đủ. Người khác có thể đã copy private key trước đó. Cần incident response, **re-key**, revoke/distrust certificate cũ theo policy, phát hành mới, cập nhật các bên tin cậy, kiểm tra logs và bảo vệ artifacts/backups.

### Bài 23. Gọi nhiều đối tác bằng một global truststore

Ứng dụng đổi `javax.net.ssl.trustStore` thành truststore riêng của Partner A; sau đó kết nối HTTPS với Partner B thất bại.

**Đáp án:** Global trust configuration có thể đã thay thế các trust anchors trước đó. Nên kiểm tra sender/JSSE config và ưu tiên **per-partner SSLContext/trust policy**. Nếu phải kết hợp trust sources, thực hiện composite policy được review/test, không trust-all.

### Bài 24. HSM không cho export private key

Để tích hợp SOAP signing, lập trình viên định lấy `PrivateKey.getEncoded()` từ HSM rồi xuất PEM.

**Đáp án:** Với HSM/PKCS11, private key có thể cố ý **non-exportable**. Ứng dụng phải dùng provider ký bằng key trong HSM hoặc Crypto abstraction tương ứng; không biến private key thành file plaintext chỉ để tương thích API.

## 23. Checklist triển khai production

| Nhóm | Câu hỏi phải xác nhận |
| --- | --- |
| Sở hữu | Ai sở hữu mỗi private key? Có được phép export không? |
| Vai trò | Key dùng TLS server, TLS client, SOAP signer hay SOAP decryption? |
| Format | File là PKCS12/JKS/PEM/DER hay HSM/PKCS11? Entry types đúng? |
| Alias | Đúng PrivateKeyEntry alias và key type? Có nhiều aliases/rotation keys không? |
| Password | Store/key passwords nạp từ secret manager? Không log/commit? |
| Public cert | Có chia sẻ **chỉ public certificate/CSR/CA** đúng đối tác không? |
| Authenticity | Fingerprint/issuer/chain được xác minh ngoài băng khi tiếp nhận certificate? |
| X.509 | SAN, validity, KU/EKU, Basic Constraints, algorithm và key size đúng policy? |
| Trust chain | CA trust anchor đúng và intermediate chain đầy đủ? |
| Scope trust | Có tránh tin root CA không cần thiết, trust-all hoặc leaf pin không có rotation? |
| Revocation | CRL/OCSP/deny-list policy được xác định và test theo runtime? |
| HTTPS | Hostname verification bật, SNI/URI đúng, TLS config đáp ứng tiêu chuẩn? |
| mTLS client | HTTP sender thật có KeyManager/PrivateKeyEntry và trình cert đúng? |
| mTLS server | Gateway/web server có trust CA client và ánh xạ identity an toàn? |
| TLS termination | Biết private key ở gateway hay embedded server? Kênh backend được bảo vệ? |
| SOAP signer | WSS4J sử dụng đúng private key alias và signer public cert/CA? |
| SOAP encrypt | Đúng recipient public cert; recipient có matching private key? |
| SOAP reply/Fault | Có signer validation/encryption policy cho response và Fault? |
| Signed parts | Signature bao phủ Body/headers/WS-A fields theo contract? |
| Replay/XXE | Có timestamp/replay checks, XML parser limits và chống signature wrapping? |
| Authorization | TLS/WS-Security identity được map tới quyền nghiệp vụ, không chỉ CA trust? |
| Isolation | Có tách dev/staging/prod, tenant/partner và minimal access? |
| Rotation | Có cert inventory, expiry alerts, overlapping windows, rollback/reload plan? |
| Compromise | Có quy trình re-key/revoke/distrust và incident response? |
| Tests | Unit alias/chain + real TLS/mTLS + WS-Security interoperability + negative tests? |
| Logs | Không có private key, password, raw SOAP security headers, PII/credentials? |
| Dependencies | Đã test đúng JDK, Spring-WS, WSS4J, JAXB, HTTP sender, gateway? |

### 23.1. Một mẫu hồ sơ cho mỗi certificate

```text
Integration: Partner B / Orders SOAP
Environment: production
Purpose: TLS client authentication
Owner: Integration Operations
Keystore reference: secrets://orders/partner-b/tls-client
Store type: PKCS12 (hoặc PKCS11/HSM theo triển khai)
Alias: orders-partner-b-tls
Private key export allowed: no/according to policy
Certificate subject/SAN: [approved identity]
Issuer / serial / SHA-256 fingerprint: [record]
NotBefore / NotAfter: [record]
KU / EKU / algorithms: [record]
Partner trust relationship: [CA/pinning policy]
Rotation owner / expected date: [record]
Overlap / rollback plan: [record]
Monitoring and expiry alerts: [record]
```

Hồ sơ không chứa private key/password. `secrets://...` chỉ là cách biểu diễn một secret reference, không phải URI truy cập thật.

### 23.2. Thứ tự triển khai một kết nối mới

1. **Đọc WSDL và security profile:** SOAP 1.1/1.2, TLS/mTLS, WS-Security actions, cert roles, key algorithms.
2. **Chốt identity:** ai giữ private key cho TLS và SOAP signer/decryption.
3. **Cấp key/certificate:** dùng CA hoặc HSM được phê duyệt; tách môi trường.
4. **Trao đổi public material:** CSR, public leaf/chain, CA/fingerprint qua kênh xác thực.
5. **Tạo truststores:** chỉ chứa approved anchors/signer certificates theo policy.
6. **Cấu hình HTTP sender:** SSLContext riêng, trust+key managers, hostname verification.
7. **Cấu hình WSS4J:** signer/decryptor keys và verifier trust đúng chiều, signed parts/algorithms.
8. **Kiểm thử tầng TLS:** server cert validity, SAN, trust chain, client certificate khi mTLS.
9. **Kiểm thử tầng SOAP:** JAXB, SOAP Fault, signature/encryption, tampering, wrong signer.
10. **Bổ sung quan sát và vận hành:** expiry alerts, cert inventory, rotation overlap, safe logs.

### 23.3. Bảng câu hỏi nhanh khi đối tác gửi “cần chứng chỉ”

Một yêu cầu không rõ “hãy gửi certificate để tích hợp” cần được làm rõ theo **mục đích**, không chỉ hỏi file extension:

| Đối tác cần làm gì? | Public material nên trao đổi | Material phải ở lại bên sở hữu |
| --- | --- | --- |
| Xác minh SOAP request do A ký | A signer public certificate/chain | A signer private key |
| Xác minh A qua mTLS | A TLS client public cert/CA theo policy | A TLS client private key |
| A xác minh HTTPS server B | B server chain/CA từ nguồn xác thực | B TLS server private key |
| A mã hóa SOAP cho B | B recipient encryption public cert | B recipient decryption private key |
| B mã hóa SOAP response cho A | A recipient encryption public cert | A recipient decryption private key |
| CA cấp certificate cho A | CSR của A | A private key |

Nếu bên nhận đề nghị **private key/password**, dừng và xác minh quy trình với đội bảo mật trước khi chia sẻ bất kỳ artifact nào.

## 24. Tổng kết

**Keystore, truststore, private key và public certificate giải quyết bốn câu hỏi khác nhau**:

- **Private key:** Tôi giữ bí mật nào để ký/chứng minh sở hữu/giải mã?
- **Public certificate:** Public key đó gắn với danh tính và thuộc tính sử dụng nào, được ai chứng nhận?
- **Identity keystore:** Những private keys và certificate chains nào thuộc về hệ thống này?
- **Truststore/policy:** Tôi chấp nhận và xác minh certificates/issuers của ai cho vai trò gì?

### 24.1. Mô hình luồng kiểm chứng

```text
SOAP Client A                             SOAP Server B
-------------                             -------------
A identity keystore                      B identity keystore
  A private key                             B private key
  A public cert chain                       B public cert chain

A truststore                              B truststore
  CA/cert để tin B                          CA/cert để tin A

HTTPS:
  A xác minh B chain + hostname
  B xác minh A cert khi mTLS

SOAP WS-Security:
  A ký request bằng A private signer key
  B verify bằng A public signer cert + trust/policy
  B ký response bằng B private signer key
  A verify bằng B public signer cert + trust/policy

SOAP Encryption:
  A mã hóa cho B bằng B recipient public cert
  B giải mã bằng B private recipient key
  B mã hóa cho A bằng A recipient public cert
  A giải mã bằng A private recipient key
```

### 24.2. Những nguyên tắc cần nhớ lâu dài

1. **Không bao giờ trao private key cho đối tác chỉ để họ xác minh chữ ký hoặc certificate.**
2. **Certificate công khai không tự được tin**: cần CA chain/trust anchor, identity, validity, key usage và policy.
3. **Alias không phải certificate identity**, và PKCS12 có thể chứa private key nên phải phân loại trước khi chia sẻ.
4. **HTTPS/mTLS khác WS-Security**; có thể dùng certificates/truststores khác nhau.
5. **TLS/WS-Security authentication khác authorization**, không tự cấp quyền nghiệp vụ.
6. **Trust-all và tắt hostname verification là sai hướng** khi gặp PKIX/handshake errors.
7. **Rotation cần overlap và kế hoạch reload**; khi key compromise, thay password không đủ.
8. **Mock SOAP tests không thay TLS/mTLS integration tests**; phải chứng minh correct key/cert được trình trên wire.

Với Spring-WS, hãy tiếp tục áp dụng đúng XSD/WSDL, JAXB root QName, SOAP Fault, interceptor, XML processing limits và WS-Security signed-parts policy. **Certificate/key material chỉ an toàn khi cả cấu hình trust, cách sử dụng và vòng đời vận hành đều được kiểm soát.**

### Tài liệu tham khảo

- [Oracle — Java KeyStore API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html).
- [Oracle — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html).
- [Oracle — keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html).
- [Spring Boot — SSL/TLS configuration](https://docs.spring.io/spring-boot/reference/features/ssl.html).
- [Spring Web Services — Reference Documentation](https://docs.spring.io/spring-ws/docs/current/reference/html/).
- [Spring Web Services — API Documentation](https://docs.spring.io/spring-ws/docs/current/api/).
- [OpenSSL — x509 command](https://docs.openssl.org/3.5/man1/openssl-x509/).
- [OpenSSL — s_client command](https://docs.openssl.org/3.5/man1/openssl-s_client/).
- [IETF RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280).
- [OASIS — Web Services Security](https://www.oasis-open.org/committees/tc_home.php?wg_abbrev=wss).
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).
