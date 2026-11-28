# Phân biệt chứng chỉ dùng cho TLS với chứng chỉ bảo vệ thông điệp

## 1. Tình huống mở đầu: đã có HTTPS, vì sao đối tác vẫn yêu cầu chữ ký SOAP?

Một hệ thống Spring Web Services (**Spring-WS**) cung cấp operation `SubmitPayment`. Client gọi:

~~~text
https://api.example.test/ws/payments
~~~

Đường truyền sử dụng **HTTPS**, server có chứng chỉ TLS hợp lệ. Đối tác còn yêu cầu client ký SOAP Body bằng chứng chỉ X.509, kèm `wsu:Timestamp` và chữ ký trên các header quan trọng. Nhóm phát triển thắc mắc: *“HTTPS đã mã hóa kết nối rồi, dùng thêm chứng chỉ WS-Security có thừa không?”*

Câu trả lời phụ thuộc **ranh giới tin cậy và thuộc tính bảo mật cần đạt**. HTTPS và WS-Security không giải quyết cùng một bài toán:

- **TLS** bảo vệ **một kết nối truyền tải** giữa hai TLS peers, ví dụ client ↔ API gateway. Tùy cấu hình, nó xác thực server và cũng có thể xác thực client qua mTLS.
- **WS-Security** bảo vệ **những phần của SOAP message** bằng chữ ký và/hoặc mã hóa ở mức thông điệp. Tính toàn vẹn của các phần được ký có thể được kiểm tra sau khi message đi qua nhiều hop.
- **mTLS** chứng minh client đang giữ private key của chứng chỉ TLS tại điểm thiết lập kết nối. Nó không tự tạo một chữ ký XML gắn với nội dung `amount` hoặc `paymentRequestId`.
- **Chữ ký SOAP hợp lệ** không tự xác nhận HTTPS server đáng tin hoặc rằng HTTP connection đã được mã hóa.

Nếu gateway **kết thúc TLS** rồi chuyển SOAP qua một tầng khác, kết nối TLS ban đầu không còn kéo dài nguyên vẹn tới backend. Chữ ký SOAP có thể cho phép backend phát hiện message bị chỉnh sửa ở những phần đã được ký, **nếu chính sách xác minh và quản lý khóa đáng tin cậy được triển khai đúng**.

Bài này thuộc chương **Chứng chỉ và khóa** của module `SPRING_WEB_SERVICES`, trong bối cảnh phát triển SOAP contract-first bằng XSD/WSDL, JAXB, endpoint và SOAP client, gắn với SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tích hợp doanh nghiệp.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **transport certificate** với **message-signing/encryption certificate**, cùng các private key tương ứng.
2. Hiểu TLS server authentication, mTLS client authentication, và WS-Security X.509 token/signature/encryption.
3. Xác định đúng ai **sở hữu private key**, ai chỉ cần **public certificate/trust anchor**.
4. Phân biệt **keystore**, **truststore**, **certificate chain**, **certificate alias** và **key usage** theo từng cơ chế.
5. Cấu hình HTTPS/mTLS phía Spring Boot/JSSE và định hướng cấu hình Spring-WS/WSS4J mà không trộn lẫn hai tầng.
6. Thiết kế trust, rotation, logging, SOAP Fault và kiểm thử khi có gateway, nhiều đối tác hoặc nhiều môi trường.
7. Tránh suy rằng “chứng chỉ hợp lệ” tự động bảo đảm quyền thực hiện nghiệp vụ, chống replay hoặc idempotency.

## 2. Khái niệm nền: khóa, chứng chỉ và danh tính

**Khóa bất đối xứng** có hai thành phần:

- **Private key**: giữ bí mật; được dùng cho thao tác mật mã tùy thuật toán, ví dụ tạo chữ ký hoặc giải mã.
- **Public key**: có thể phân phối; dùng để xác minh chữ ký hoặc mã hóa/thiết lập cơ chế nhận khóa cho người sở hữu private key.

**Chứng chỉ X.509** là cấu trúc chứa public key và metadata như subject, issuer, thời hạn hiệu lực, serial number, key usage và chữ ký của CA phát hành. Một chứng chỉ **không chứa private key** theo định dạng chứng chỉ X.509 thông thường.

Một certificate chain thường gồm:

~~~text
Trust anchor (root CA) -- được truststore tin cậy
          |
          v
Intermediate CA -- ký chứng chỉ tiếp theo
          |
          v
Leaf certificate -- chứa public key của service/client
~~~

Việc một chứng chỉ được CA ký không tự làm nó đáng tin. Bên xác minh phải xây dựng đường chứng chỉ hợp lệ tới **trust anchor được chính sách tin cậy**, kiểm tra thời hạn, thuật toán, ràng buộc tên/mục đích, key usage và các điều kiện khác áp dụng cho cơ chế cụ thể.

### 2.1. Giữ riêng bốn câu hỏi

| Câu hỏi | Cần nhìn vào điều gì? |
| --- | --- |
| Ai sở hữu khóa bí mật? | Private key được lưu trong keystore, HSM hoặc key manager nào? |
| Public key thuộc về danh tính nào? | Chứng chỉ leaf, subject/SAN, chuỗi CA và quy trình cấp phát |
| Người xác minh tin danh tính đó theo điều kiện gì? | Truststore/CA, pinning, policy, revocation, allowlist và mapping principal |
| Khóa được phép dùng cho mục đích gì? | KeyUsage, ExtendedKeyUsage (EKU), thuật toán, ràng buộc policy/ứng dụng |

Chứng chỉ có thể được tạo từ một key pair, nhưng **không nên dùng từ “chứng chỉ” để chỉ luôn private key**. Khi vận hành, câu “cần gửi chứng chỉ cho đối tác” thường có nghĩa gửi **public certificate hoặc chain**, *không* gửi private key.

### 2.2. Keystore và truststore không phải hai định dạng bắt buộc khác nhau

**Keystore** trong cách gọi JSSE/Java thường lưu key material thuộc quyền sở hữu của ứng dụng, có thể bao gồm:

- Private key entry cùng chuỗi chứng chỉ.
- Secret-key entry tùy mục đích.
- Trusted certificate entry.

**Truststore** là kho các chứng chỉ/CA được tin để **xác minh peer**. Cả hai đều có thể dùng định dạng `PKCS12`, tùy Java/provider, chứ không có nghĩa truststore chỉ được lưu `.jks` và keystore chỉ là `.p12`.

| Cơ chế | Ví dụ phía server cần private key nào? | Ví dụ phía client cần trust gì? |
| --- | --- | --- |
| HTTPS server TLS | Khóa bí mật của chứng chỉ server TLS | Trust anchor xác minh server TLS và tên máy chủ |
| HTTPS mTLS | Server TLS private key; phía client cũng có client TLS private key | Client xác minh server; server xác minh client cert |
| WS-Security XML Signature từ client | Client dùng private signing key để ký SOAP | Server cần khả năng tin và xác minh signing certificate |
| WS-Security message encryption tới server | Server giữ private decryption key | Client cần public encryption cert của server và policy về recipient |

**Một kho chứa nhiều certificate không tự định nghĩa chúng được dùng cho TLS hay SOAP.** Vấn đề là key entry, mục đích, cách cấu hình provider và đường code thực sự dùng khóa.

## 3. Hai lớp bảo mật qua sơ đồ kiến trúc

~~~mermaid
flowchart LR
    C["SOAP client"] -->|"TLS connection A"| G["API gateway"]
    G -->|"TLS connection B hoặc internal transport"| S["Spring-WS server"]
    C -.->|"WS-Security Signature/Encryption trong SOAP message"| S
    G --> P["Policy: route, authentication, rate limits"]
    S --> V["WSS4J: verify signature / decrypt"]
    V --> E["@Endpoint + authorization"]
~~~

**TLS connection A** và **connection B** là hai security contexts độc lập. Nếu gateway chấm dứt TLS, ứng dụng backend có thể không nhìn thấy client TLS certificate gốc, trừ khi có một **cơ chế chuyển tiếp danh tính được xác thực và chống giả mạo**.

Ngược lại, SOAP message đi qua gateway có thể vẫn giữ nguyên các XML elements được ký. Backend xác minh chúng bằng WS-Security; nếu gateway chỉnh sửa một phần đã ký, signature validation phải thất bại.

### 3.1. Từng cơ chế bảo vệ chỗ nào?

| Tiêu chí | TLS / HTTPS | mTLS | WS-Security XML Signature | WS-Security XML Encryption |
| --- | --- | --- | --- | --- |
| Cấp bảo vệ | Kết nối transport | Kết nối transport | SOAP message / selected elements | SOAP message / selected elements |
| Xác thực server | Có khi client xác minh đúng server | Có | Không tự thay TLS server authentication | Không tự thay TLS server authentication |
| Xác thực client | Không nhất thiết | **Có tại TLS peer** | Chứng minh possession signing key theo trust/policy | Không tự chứng minh người gửi |
| Bảo mật dữ liệu khi truyền | Có trên từng TLS hop | Có trên từng TLS hop | Không tạo confidentiality | Có cho selected elements |
| Phát hiện sửa SOAP Body sau gateway | Không bảo vệ end-to-end qua TLS termination | Không tự bảo vệ qua TLS termination | Có nếu Body được ký đúng | Có thể bảo vệ nội dung mã hóa; integrity cần xem thuật toán/policy |
| Giữ bảo vệ khi SOAP message được lưu/chuyển tiếp | Chỉ trong phiên kết nối | Chỉ trong phiên kết nối | Chữ ký có thể tiếp tục được xác minh | Ciphertext có thể tiếp tục được bảo vệ |
| Chống message replay | Không thay chính sách replay ở ứng dụng | Không thay chính sách replay ở ứng dụng | Chữ ký riêng lẻ không chặn replay | Mã hóa riêng lẻ không chặn replay |
| Phân quyền nghiệp vụ | Không | Không | Không, cần authorization riêng | Không |

Một hệ thống có thể yêu cầu **cả HTTPS và SOAP Signature**, thậm chí thêm SOAP Encryption nếu message phải được giữ kín khỏi intermediary. Không nên chọn một cơ chế rồi tuyên bố những cơ chế khác “không cần” mà không đánh giá threat model.

### 3.2. Kịch bản không cần ký SOAP cũng có thể hợp lý

Một service nội bộ có kết nối mTLS end-to-end, không lưu/chuyển tiếp SOAP message qua bên thứ ba, threat model chấp nhận bảo vệ ở transport và không có yêu cầu interoperable message signature có thể chỉ dùng TLS/mTLS **theo policy của tổ chức**.

Điều đó không có nghĩa TLS luôn đủ: nếu hợp đồng đối tác quy định WS-Security, message đi qua nhiều trust domain, cần chữ ký end-to-end, hoặc có audit requirement ở mức message, hãy triển khai WS-Security đúng profile.

## 4. TLS server certificate: client đang kết nối với ai?

Khi client kết nối `https://api.example.test/ws/orders`, phần TLS handshake cho phép server chứng minh mình kiểm soát private key tương ứng với chứng chỉ được trình ra theo cơ chế TLS và thuật toán được thương lượng. Client xác minh chứng chỉ theo trust policy:

1. Chuỗi chứng chỉ đi đến một CA/trust anchor mà client chấp nhận.
2. Chứng chỉ còn trong thời hạn và phù hợp các ràng buộc path/algorithm.
3. Danh tính hostname `api.example.test` khớp Subject Alternative Name (**SAN**) phù hợp.
4. Key Usage/Extended Key Usage phù hợp cách dùng TLS server.
5. Quy tắc revocation/pinning hoặc tổ chức yêu cầu được áp dụng.

**SAN/hostname verification rất quan trọng**. Chỉ import một certificate vào truststore mà không xác minh đúng hostname có thể khiến client tin một endpoint không phải đích mong muốn.

### 4.1. Một HTTPS request minh họa

~~~text
Client:
  DNS -> api.example.test
  TLS handshake -> verify server TLS cert / SAN
  HTTP POST /ws/orders -> SOAP Envelope

Server:
  TLS endpoint -> private key cho TLS handshake
  HTTP/SOAP stack -> MessageDispatcherServlet
~~~

TLS certificate không nằm trong `soap:Header` dưới dạng XML Signature chỉ vì client gọi URL HTTPS. Nó thuộc **giao thức TLS bên ngoài SOAP**.

### 4.2. Chứng chỉ public và private key TLS

~~~text
Server TLS keystore:
  alias: api-server-tls
  private key: có, giữ bí mật
  leaf certificate + chain: có

Client TLS truststore:
  trusted CA / pinset thích hợp
  private key server: KHÔNG CÓ
~~~

Client thường không cần private key TLS của server. Nếu ai đó yêu cầu bạn gửi file keystore chứa private key server cho đối tác chỉ để họ xác minh HTTPS, cần xem xét lại yêu cầu: đối tác thường chỉ cần CA/public certificate phù hợp.

## 5. mTLS: chứng chỉ TLS phía client là một danh tính ở kết nối

**Mutual TLS (mTLS)** mở rộng HTTPS thông thường: ngoài việc client xác minh server, **server TLS peer** yêu cầu và xác minh chứng chỉ client.

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant G as TLS server / gateway
    participant S as Spring-WS backend
    C->>G: TLS ClientHello
    G-->>C: Server certificate + certificate request
    C->>G: Client certificate + proof of private-key possession
    Note over G: Verify chain, purpose, allowed client identity
    G-->>C: TLS channel established
    C->>G: HTTPS SOAP POST
    G->>S: Forward SOAP + trusted identity context theo policy
~~~

Trong topology có gateway terminate TLS:

- **Gateway** xác minh client certificate ở TLS layer.
- Backend `Spring-WS` không tự nhìn thấy TLS client certificate của client gốc trong kết nối mới.
- Nếu gateway chuyển principal qua header, phải dùng kênh backend được bảo vệ và **xóa/chặn header do client trực tiếp giả mạo**, đồng thời kiểm tra trust giữa gateway/backend.
- Nếu muốn **backend tự xác minh certificate client ở TLS layer**, kiến trúc TLS termination phải phù hợp (ví dụ TLS pass-through hoặc mTLS đến backend từ một identity đúng vai trò).

### 5.1. mTLS certificate không mặc nhiên là SOAP signing certificate

Một khách hàng có thể có:

~~~text
tls-client.p12:
  alias partner-client-tls
  purpose: client authentication at gateway

soap-signing.p12:
  alias partner-soap-signing
  purpose: sign SOAP Body and Timestamp
~~~

**Hai certificates có thể thuộc cùng một pháp nhân nhưng là hai khóa riêng**. Không dùng chứng chỉ client TLS để verify SOAP XML Signature trừ khi nó **thực sự** là signing certificate được dùng trong SOAP và phù hợp chính sách.

Ngược lại, XML Signature key có thể được giữ trong HSM/service riêng; việc sở hữu nó không chứng minh client đã hoàn tất mTLS handshake.

### 5.2. “mTLS đã xác thực” khác “được phép gọi operation”

Một client certificate hợp lệ cho `partner-A` không tự có quyền gọi `DeleteInvoice` hoặc thay đổi tài khoản của `partner-B`. Cần:

- Mapping chứng chỉ TLS tới principal được tổ chức tin cậy.
- Authorization theo operation, tenant, tài nguyên và điều kiện nghiệp vụ.
- Kiểm soát chứng chỉ thu hồi/hết hạn/được phép.
- Cơ chế audit liên hệ SOAP request với identity đã xác minh.

Chứng chỉ là **đầu vào của authentication**, không phải giấy phép tổng quát cho mọi thao tác.

## 6. WS-Security X.509: chữ ký bảo vệ nội dung thông điệp

Trong SOAP, XML Signature dùng private key phía người ký để ký các phần thông điệp được policy chỉ định. Phía nhận dùng public key/certificate được chấp nhận để xác minh chữ ký.

~~~mermaid
flowchart LR
    D["SOAP Body + Timestamp"] --> C["XML canonicalization/digest"]
    C --> P["Client private signing key"]
    P --> S["ds:Signature trong wsse:Security"]
    S --> R["Server nhận SOAP message"]
    R --> T["Trust signer + verify ds:Signature + references"]
    T --> V["Validate timestamp, replay, authorization"]
~~~

**Chỉ những XML elements được tham chiếu và ký đúng mới được bảo vệ bằng chữ ký đó.** Một chữ ký hợp lệ trên `wsu:Timestamp` không chứng minh nội dung `amount` nguyên vẹn nếu Body bị bỏ khỏi danh sách signed parts.

### 6.1. Chữ ký SOAP ký những gì?

Tùy WS-SecurityPolicy, hệ thống có thể yêu cầu ký:

- SOAP Body, đặc biệt `paymentRequestId` và `amount`.
- `wsu:Timestamp`, để attacker không thể sửa `Created/Expires` mà chữ ký vẫn đúng.
- WS-Addressing `Action`/`To` khi những header này quyết định routing và authorization.
- Các SOAP Header nghiệp vụ quan trọng.
- MIME attachments theo profile ký attachment nếu có, không mặc định chữ ký Body bao phủ toàn bộ MIME part.

Một hợp đồng có thể quy định **sign-before-encrypt hoặc encrypt-before-sign** tùy profile. Không tự thay đổi thứ tự bảo vệ mà không kiểm thử interoperable với đối tác.

### 6.2. SOAP Header chứa BinarySecurityToken và Signature

Một **fragment sơ đồ**, cố ý không có giá trị chữ ký hợp lệ:

~~~xml
<wsse:Security
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">

    <wsu:Timestamp wsu:Id="TS-1001">
        <wsu:Created>2026-11-27T02:00:00Z</wsu:Created>
        <wsu:Expires>2026-11-27T02:05:00Z</wsu:Expires>
    </wsu:Timestamp>

    <wsse:BinarySecurityToken
        wsu:Id="X509-1"
        ValueType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3"
        EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">BASE64_CERT_EXAMPLE</wsse:BinarySecurityToken>

    <ds:Signature>
        <!-- SignedInfo, SignatureValue và KeyInfo phải
             được WSS4J tạo theo profile; không tự chép từ ví dụ. -->
    </ds:Signature>
</wsse:Security>
~~~

**Không phải SOAP security header hoàn chỉnh để gửi thật**. `BASE64_CERT_EXAMPLE` là placeholder, và không có `ds:SignedInfo`/`SignatureValue` thực. Trong production, WSS4J/crypto provider chịu trách nhiệm tạo canonicalization, digest, XML signature references và security token.

**Quan trọng:** chứng chỉ xuất hiện trong `BinarySecurityToken` **không mặc nhiên đáng tin**. Một attacker cũng có thể gửi chứng chỉ tự ký của họ kèm một chữ ký được tạo bằng private key của họ. Server phải kiểm tra **trust/allowlist/chain và danh tính có quyền** chứ không chỉ tính toán “signature verifies with embedded public key”.

### 6.3. XML signature wrapping

Một lớp tấn công XML nguy hiểm là **signature wrapping**: request chứa một phần tử được ký hợp lệ nhưng endpoint lại xử lý một phần tử khác do cấu trúc XML, ID hoặc QName bị thao túng.

Phòng vệ:

1. Dùng WSS4J/XML security library đã được bảo trì, không tự xác minh chữ ký thủ công.
2. Kiểm tra các phần được ký **chính là** SOAP Body/Header mà nghiệp vụ sử dụng.
3. Từ chối duplicate ID, namespace lạ, tham chiếu đáng ngờ hoặc XML cấu trúc không hợp lệ.
4. Kết hợp schema validation và giới hạn XML resource.
5. Kiểm thử khi signer hợp lệ nhưng attacker chèn thêm Body/element cùng tên.

Chỉ việc có `ds:Signature` không bảo đảm các phần mà ứng dụng tiêu thụ đã được bảo vệ.

## 7. WS-Security XML Encryption: khóa của người nhận, không phải khóa người gửi

Nếu SOAP Body chứa dữ liệu phải được giữ kín ngay cả khi đi qua một gateway hoặc được lưu trong queue, có thể sử dụng **XML Encryption** theo WS-Security.

Mô hình đơn giản:

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant G as Gateway / intermediary
    participant S as Spring-WS backend
    C->>C: Lấy public encryption certificate của S
    C->>C: Mã hóa selected SOAP content
    C->>G: SOAP chứa xenc:EncryptedData
    G->>S: Forward SOAP message
    S->>S: Giải mã bằng private decryption key
    S->>S: Xác thực chữ ký / schema / quyền
~~~

Trong cơ chế mã hóa lai phổ biến:

1. Bên gửi tạo khóa phiên đối xứng cho dữ liệu.
2. Bên gửi dùng public key của **người nhận dự kiến** theo thuật toán trao khóa/wrapping được hỗ trợ để bảo vệ khóa phiên.
3. SOAP message chứa các cấu trúc XML Encryption liên quan.
4. Chỉ bên sở hữu private decryption key phù hợp mới giải mã được phần đã bảo vệ, trừ khi khóa bị lộ hoặc chính sách chia sẻ cho thêm recipients.

**Public encryption certificate có thể được trao cho client; private decryption key phải ở phía người nhận**. Đừng gửi private key của server cho client để họ mã hóa dữ liệu.

### 7.1. Ký và mã hóa khác nhau thế nào?

| Tác vụ | Khóa phía gửi | Khóa phía nhận | Mục tiêu |
| --- | --- | --- | --- |
| Client ký SOAP Body | **Client private signing key** | Client public signing cert để server verify | Toàn vẹn / xác thực signer |
| Client mã hóa SOAP Body gửi server | Server **public encryption cert** | **Server private decryption key** | Bí mật nội dung với đúng recipient |
| Server ký SOAP response | **Server private signing key** | Server public signing cert để client verify | Toàn vẹn / xác thực response |
| Server mã hóa SOAP response cho client | Client **public encryption cert** | **Client private decryption key** | Bí mật response với client |

Một thiết kế có thể dùng cùng một identity cho TLS và SOAP security, nhưng **không đồng nghĩa** cùng private key là lựa chọn tốt. Khuyến nghị quản trị thường là tách khóa theo mục đích, chủ sở hữu, quyền truy cập, vòng đời và policy.

### 7.2. Vì sao mã hóa SOAP không thay chữ ký?

Mã hóa giúp giữ bí mật những phần được mã hóa, nhưng không tự xác định mọi thông điệp có nguồn từ người gửi được tin, không tự chống replay và có thể không cung cấp toàn bộ thuộc tính integrity/authenticity mà hợp đồng yêu cầu. Sử dụng thuật toán mã hóa xác thực phù hợp và chữ ký/signed-parts theo **WS-SecurityPolicy**.

Khi bảo vệ SOAP:

- Xác định rõ **phần nào cần ký**, **phần nào cần mã hóa**, thứ tự và thuật toán.
- Xác định **certificate/key nào** dành cho encryption và certificate/key nào dành cho signing.
- Bảo vệ WS-Addressing `To`/`Action`, Timestamp hoặc header khác khi routing/security dựa vào chúng.
- Không tin rằng mã hóa `Body` làm các header bên ngoài mặc nhiên bí mật hoặc nguyên vẹn.
- Với attachment/MTOM, kiểm tra profile WS-Security attachment protection thay vì suy rằng mã hóa XML Body luôn mã hóa cả binary MIME parts.

### 7.3. Gateway có thể định tuyến khi Body được mã hóa?

Nếu gateway cần đọc nội dung nghiệp vụ trong Body để định tuyến, mã hóa Body end-to-end có thể ngăn nó thực hiện công việc. Cần thiết kế routing dựa trên:

- HTTP host/path.
- SOAP Action hoặc WS-Addressing Action/To theo policy.
- Metadata không nhạy cảm đã được bảo vệ tính toàn vẹn.
- Cơ chế nhận dạng operation phù hợp WSDL.

**Không giải mã ở gateway chỉ để định tuyến** rồi vẫn tuyên bố backend có confidentiality end-to-end, trừ khi gateway được đưa vào chính trust boundary có quyền đọc nội dung.

## 8. Ma trận sở hữu khóa: bốn vai trò rất dễ bị nhầm

Giả sử tổ chức **Acme** là client gọi server **Payments** qua gateway. Một kiến trúc tách khóa có thể như sau:

| Mục đích | Chủ sở hữu private key | Certificate bên nào cần biết? | Nơi được cấu hình |
| --- | --- | --- | --- |
| Gateway TLS server | Gateway operator | Acme client phải tin gateway certificate/CA | TLS listener và HTTP client trust |
| Acme mTLS client | Acme client | Gateway xác minh Acme certificate/CA | Client TLS key manager; gateway trust policy |
| Acme SOAP signing | Acme signer/HSM | Payments server xác minh Acme signing cert | WSS4J client sign; server signature validation |
| Payments SOAP decryption | Payments backend/HSM | Acme client có Payments public encryption cert | WSS4J client encrypt; backend decrypt |

Các dòng không nhất thiết tương ứng **bốn pháp nhân** hoặc bốn CA độc lập; chúng là **bốn vai trò mật mã**. Khi ký SOAP response hoặc mã hóa response, có thể cần các cặp khóa tương ứng theo chiều ngược lại.

### 8.1. Một sơ đồ quy trình trao khóa an toàn

~~~text
1. Payments cung cấp:
   - public server TLS certificate/CA thông qua PKI hợp lệ
   - public SOAP encryption certificate được xác minh fingerprint

2. Acme cung cấp:
   - public client TLS certificate hoặc CA thông qua quy trình onboarding
   - public SOAP signing certificate được Payments cho phép

3. Acme giữ:
   - private TLS client key
   - private SOAP signing key

4. Payments / gateway giữ:
   - private server TLS key tại TLS terminator
   - private SOAP decryption key tại backend được phép

5. Không bên nào chuyển private key sang đối tác chỉ để đối tác verify.
~~~

Trao **public certificate qua email không có xác minh nguồn** có thể làm đối tác tin nhầm public key của attacker. Với onboarding doanh nghiệp, kiểm tra certificate fingerprint, chain và chủ sở hữu qua một kênh tin cậy độc lập.

### 8.2. Nếu dùng cùng chứng chỉ cho nhiều mục đích thì sao?

Một certificate X.509 có thể có key usage/EKU và provider cho phép nhiều mục đích, nhưng việc **tái sử dụng khóa TLS cho SOAP signing/decryption** làm tăng phạm vi tác động nếu private key bị lộ và khiến rotation khó độc lập.

Trước khi quyết định reuse:

1. Xác minh certificate thật sự cho phép các thao tác mật mã tương ứng theo policy.
2. Kiểm tra CA đã cấp certificate cho mục đích nào.
3. Đánh giá nơi private key phải tồn tại: gateway, backend, client, HSM.
4. Đánh giá backup, audit, tách quyền sử dụng và thời điểm rotation.
5. Đảm bảo đối tác hỗ trợ certificate/key profile và thuật toán được chọn.

**Cùng một cặp khóa không phải điều kiện để TLS và WS-Security hoạt động cùng nhau.**

## 9. KeyUsage, ExtendedKeyUsage, SAN và thuật toán

X.509 certificate có các extensions để ràng buộc mục đích:

| Thuộc tính | Ví dụ | Ý nghĩa đối với hai tầng |
| --- | --- | --- |
| `keyUsage.digitalSignature` | Bit cho phép chữ ký số | Liên quan ký TLS handshake hoặc ký SOAP tùy profile |
| `keyUsage.keyEncipherment` | Liên quan thao tác encipherment ở một số cơ chế RSA | Không áp dụng máy móc cho mọi thuật toán TLS hiện đại |
| `keyUsage.keyAgreement` | Dùng cho cơ chế thỏa thuận khóa | Phụ thuộc thuật toán và profile |
| `extendedKeyUsage.serverAuth` | TLS Web Server Authentication | Thường cần cho TLS server cert |
| `extendedKeyUsage.clientAuth` | TLS Web Client Authentication | Thường cần cho mTLS client cert |
| `subjectAltName (SAN)` | `DNS:api.example.test` | Hostname verification TLS server |
| `basicConstraints` | CA=true với CA certificates | Phân biệt CA và end-entity certificates |
| `notBefore` / `notAfter` | Khoảng hiệu lực | Bị kiểm tra ở cả trust policies |
| Certificate policy OID | Theo PKI doanh nghiệp | Có thể ràng buộc loại danh tính/cấp phát |

**Không suy rằng một SOAP signing cert phải có `serverAuth` hoặc SAN trùng HTTP hostname.** SOAP signer có thể là một principal doanh nghiệp không phải web server; trust mapping của WS-Security phải được định nghĩa riêng.

Ngược lại, TLS server cert có `DNS:api.example.test` nhưng không được phép dùng để giải mã SOAP chỉ vì tên host đúng.

### 9.1. Hậu quả khi dùng sai EKU

Giả sử đối tác đưa cho bạn một certificate chỉ có `clientAuth` và nói “cứ dùng nó làm server TLS cert”. TLS client có thể từ chối vì mục đích chứng chỉ không phù hợp. Thay vì vô hiệu hóa kiểm tra, cần yêu cầu certificate được cấp đúng mục đích và chính sách.

Một SOAP signing validator có thể có quy tắc EKU/identity khác với JSSE TLS trust manager; **đừng cho rằng JSSE đã chấp nhận cert nên WSS4J sẽ chấp nhận, hoặc ngược lại**.

### 9.2. Thuật toán và crypto agility

Các profile có thể sử dụng RSA, ECDSA, RSA-PSS, SHA-256 hoặc thuật toán khác tùy Java, XML Signature và WSS4J stack. Không chọn thuật toán chỉ vì “keytool tạo được khóa”:

- TLS 1.2/1.3 có tập thuật toán/cipher suites riêng.
- XML Signature có algorithm identifiers và canonicalization riêng.
- XML Encryption có cơ chế mã hóa nội dung và khóa riêng.
- FIPS hoặc security baseline của tổ chức có thể hạn chế thuật toán.
- Đối tác Java/.NET có thể khác nhau về mức độ hỗ trợ.

Không dùng SHA-1/MD5 hoặc các thuật toán đã yếu cho chữ ký mới chỉ để dễ tương thích, trừ khi policy/exception được quản lý chặt; hãy nâng profile khi có thể. **Tương thích không được đạt bằng cách tắt xác minh chữ ký hoặc chấp nhận mọi certificate.**

## 10. Truststore: “được CA ký” chưa phải đã được phép giao dịch

Một TLS client có thể tin CA công khai để xác minh máy chủ `api.example.test`. Một SOAP receiver có thể chỉ được phép chấp nhận **một tập đối tác ký** theo hợp đồng.

### 10.1. Hai lớp trust policy

~~~text
TLS trust:
  - CA chain hợp lệ?
  - Hostname đúng SAN?
  - EKU và validity phù hợp?
  - Certificate revocation/pinning policy?

SOAP signing trust:
  - Signature verify đúng signed parts?
  - Certificate chain/trust anchor được chấp nhận?
  - Fingerprint/issuer/subject/partner mapping đúng policy?
  - Principal có quyền gọi operation/resource?
  - Timestamp và replay policy hợp lệ?
~~~

Đừng coi việc import một root CA chung vào WS-Security crypto truststore là đủ để cấp quyền **cho mọi certificate do CA đó cấp**. Tùy threat model, cần allowlist fingerprint, subject/issuer/serial, certificate policy hoặc một identity mapping đáng tin, **đồng thời** authorization ở business layer.

### 10.2. Chứng chỉ tự ký của đối tác

Trong một số tích hợp doanh nghiệp, đối tác sử dụng certificate tự ký và gửi public cert qua onboarding. Có thể thiết lập **explicit trust/pinning** trong phạm vi hợp đồng, nhưng phải:

- Xác minh fingerprint qua kênh độc lập.
- Theo dõi thời hạn và rotation.
- Không import vô điều kiện mọi certificate mà SOAP message tự gửi kèm.
- Đặt trust khác nhau giữa staging và production.
- Kiểm tra signer identity mapping và operation authorization.

Một certificate tự ký **không tự đáng tin** chỉ vì signature của chính nó hợp lệ.

### 10.3. Thu hồi chứng chỉ (revocation)

Certificate có thể bị thu hồi trước `notAfter` vì private key lộ, đối tác bị dừng hợp tác hoặc PKI thay đổi. Kiểm tra revocation qua CRL/OCSP hoặc cơ chế enterprise phù hợp là một phần policy; **không giả định mọi JSSE/WSS4J configuration bật kiểm tra thu hồi mặc định**.

Khi chọn fail-open hoặc fail-closed nếu OCSP/CRL không khả dụng, phải đánh giá tác động tới:

- Khả dụng của hệ thống.
- Khả năng chấp nhận certificate đã bị thu hồi.
- Latency/timeout và cache revocation responses.
- Audit/compliance và quy định của đối tác.

Không tự tạo “kiểm tra certificate còn hạn” rồi coi như đã hoàn tất trust validation.

## 11. TLS server với Spring Boot: keystore và HTTPS listener

Trong Spring Boot, khi server nhúng trực tiếp sở hữu HTTPS listener, có thể cấu hình TLS theo các properties như:

~~~properties
# application.properties - minh họa, không lưu secret thật trong source
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:tls/server-tls.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-alias=server-tls
server.ssl.key-store-password=INJECT_FROM_SECRET_MANAGER
~~~

**Đây là mẫu giải thích cấu hình**. Thay `INJECT_FROM_SECRET_MANAGER` bằng cơ chế secrets bên ngoài phù hợp; đừng commit mật khẩu vào Git. Trong môi trường container, file private key thường nên được mount từ secret volume hoặc cung cấp qua PKI/key manager được bảo vệ, thay vì đóng gói trong JAR.

Properties `server.ssl.*` cấu hình **transport server** khi Spring Boot sở hữu TLS listener. Chúng **không** có nghĩa `Wss4jSecurityInterceptor` tự lấy keystore này để ký hoặc giải mã SOAP messages.

### 11.1. mTLS phía Spring Boot server

Nếu chính application server yêu cầu client certificate:

~~~properties
server.ssl.client-auth=need
server.ssl.trust-store=classpath:tls/allowed-client-ca.p12
server.ssl.trust-store-type=PKCS12
server.ssl.trust-store-password=INJECT_FROM_SECRET_MANAGER
~~~

`client-auth=need` yêu cầu chứng chỉ client tại TLS handshake theo cấu hình servlet container/SSL stack. Nếu TLS termination xảy ra tại gateway thay vì Spring Boot, các properties này trên backend **không làm gateway tự yêu cầu client certificate**. Cần cấu hình mTLS tại đúng **TLS terminating peer**.

Đặt `client-auth=want` (yêu cầu tùy chọn) không tương đương `need` (bắt buộc) và không thay thế enforcement của application nếu endpoint chỉ dành cho client đã xác thực.

### 11.2. Tách khóa server TLS và SOAP server private key

~~~text
TLS:
  server.ssl.key-store -> tls/server-tls.p12
  alias -> server-tls

SOAP message security:
  WSS4J decryption/signature crypto -> wssec/server-message.p12
  alias -> soap-server-decryption / soap-server-signing
~~~

Hai file có thể cùng kiểu PKCS12 nhưng phục vụ hai **cơ chế độc lập**. Một số môi trường enterprise dùng HSM và không có file `.p12` local; nguyên tắc phân tách vai trò vẫn giữ nguyên.

## 12. TLS phía Spring-WS client: cần cấu hình message sender

Khi `WebServiceTemplate` gọi một endpoint HTTPS, chính **HTTP message sender** mở TLS connection. Không giả định properties `server.ssl.key-store` của Spring Boot server được tự động sử dụng cho mọi outbound SOAP client.

Các thành phần:

~~~text
WebServiceTemplate
   |
   +-- JAXB Marshaller / Unmarshaller
   |
   +-- ClientInterceptor(s)
   |      +-- WSS4J: ký / mã hóa / kiểm tra response
   |
   +-- WebServiceMessageSender
          +-- HTTP client / TLS provider
                +-- Trust managers: verify remote TLS server
                +-- Key managers: select mTLS client certificate
                +-- Hostname verification / timeouts
~~~

### 12.1. Ví dụ xây dựng `SSLContext` với JSSE

Đoạn Java minh họa vai trò khác nhau của hai kho:

~~~java
package example.integration.tls;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class ClientTlsContextFactory {

    public static SSLContext create(
            Path clientKeyStoreFile,
            char[] clientKeyStorePassword,
            Path serverTrustStoreFile,
            char[] serverTrustStorePassword)
            throws Exception {

        KeyStore clientKeys = KeyStore.getInstance("PKCS12");
        try (InputStream in =
                     Files.newInputStream(clientKeyStoreFile)) {
            clientKeys.load(in, clientKeyStorePassword);
        }

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(clientKeys, clientKeyStorePassword);

        KeyStore serverTrust = KeyStore.getInstance("PKCS12");
        try (InputStream in =
                     Files.newInputStream(serverTrustStoreFile)) {
            serverTrust.load(in, serverTrustStorePassword);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(serverTrust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
                kmf.getKeyManagers(),
                tmf.getTrustManagers(),
                new SecureRandom());
        return context;
    }
}
~~~

Đây là **hàm tạo SSLContext**, chưa phải cấu hình message sender hoàn chỉnh và **không tự gắn context vào `WebServiceTemplate`**. Các ngoại lệ/phần import được tối giản; password chars đến từ nguồn bí mật bên ngoài, không hard-code.

Để hoàn thiện phải:

1. Chọn HTTP client implementation tương thích phiên bản Spring-WS (ví dụ sender dựa trên HttpComponents hoặc JDK HTTP).
2. Cấu hình chính `SSLContext` đó cho **connection manager/SSL socket factory** của sender theo API/version của implementation.
3. Giữ **hostname verification bật**.
4. Đặt connect/read/request timeouts và redirect policy.
5. Gắn sender vào `WebServiceTemplate` bằng setter/auto-configuration thích hợp.
6. Test endpoint TLS thật với server certificate hợp lệ/sai SAN, client mTLS có/không có chứng chỉ.

**Không dùng `setDefaultSSLSocketFactory(...)` global hoặc trust-all manager làm giải pháp nhanh**: cấu hình toàn JVM có thể ảnh hưởng các HTTP clients khác và làm mất ranh giới tin cậy.

### 12.2. Khách hàng chỉ cần HTTPS, không dùng mTLS

Nếu server **không yêu cầu client certificate**, outbound client thường chỉ cần **trust managers** để xác minh server certificate. Không nhất thiết cung cấp `KeyManagerFactory` với private key.

Trong snippet ở trên, `clientKeys` chỉ cần khi **mTLS client authentication** hoặc một cơ chế TLS cần key manager. Nếu chỉ HTTPS server-auth, cấu hình phù hợp có thể truyền `null` cho key managers và chọn trust managers theo policy.

### 12.3. TLS client alias

Một keystore có thể chứa nhiều private-key entries:

~~~text
client-tls.p12
  alias: partner-a-mtls
  alias: partner-b-mtls
~~~

TLS provider có thể chọn certificate theo key type, CA hints và thuật toán. Nếu client phải dùng đúng alias tương ứng đối tác, cần cơ chế key manager/certificate selection phù hợp, không mặc định “first alias” luôn đúng. Test certificate **thực sự được gửi** trong TLS handshake.

## 13. Spring-WS/WSS4J: crypto cho SOAP message là cấu hình riêng

Đối với chữ ký và mã hóa thông điệp, Spring-WS thường tích hợp Apache WSS4J qua:

~~~java
org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor
~~~

**WSS4J Crypto** là abstraction truy cập key/certificate và trust material phục vụ WS-Security; nó **không** đồng nghĩa Java `SSLContext` hay HTTP TLS trust manager.

| WSS4J operation | Material cần | Mục tiêu |
| --- | --- | --- |
| `Signature` securement | Private signing key + certificate chain | Ký SOAP request/response |
| `Signature` validation | Tin cậy signer public certificate/chain | Verify signature và signer identity |
| `Encrypt` securement | Public encryption certificate của người nhận | Mã hóa selected SOAP elements |
| `Encrypt` validation/decryption | Private decryption key của người nhận | Giải mã message nhận |
| `Timestamp` validation | Thời gian và policy, không cần TLS cert | Kiểm tra freshness |
| `UsernameToken` validation | Shared secret/callback theo profile | Xác thực token, nonce/replay |

### 13.1. Ví dụ cấu hình WSS4J server kiểm tra chữ ký

Một Spring-WS application có thể tạo interceptor inbound:

~~~java
package example.payments.ws;

import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
public class InboundMessageSecurityConfig {

    @Bean("inboundSignatureValidator")
    public Wss4jSecurityInterceptor inboundSignatureValidator(
            Crypto approvedPartnerSigningTrust) {

        Wss4jSecurityInterceptor interceptor =
                new Wss4jSecurityInterceptor();

        interceptor.setValidationActions(
                "Signature Timestamp");
        interceptor.setValidationSignatureCrypto(
                approvedPartnerSigningTrust);

        return interceptor;
    }
}
~~~

**Ý nghĩa:** `Crypto approvedPartnerSigningTrust` là trust/crypto implementation được ứng dụng tạo và đưa vào Spring context, **không phải default TLS truststore**. Nó cần được cấu hình để xác minh signer certificate theo PKI/allowlist của đối tác.

Đoạn trên mới thể hiện hai action cần kiểm tra. Để vận hành, còn phải:

- Gắn interceptor vào **Spring-WS EndpointInterceptor chain**.
- Đặt signature parts, time limits và các yêu cầu WS-SecurityPolicy khác.
- Xác minh principal/certificate identity thực sự được phép với operation.
- Kiểm tra nonce/replay policy nếu profile có token/MessageID hoặc signature replay.
- Cấu hình WS-Security Fault response, logging và bảo vệ thông tin bí mật.
- Thử cả signed message hợp lệ và signed message dùng certificate không được trust.

**Quan trọng:** `setValidationActions("Signature Timestamp")` không có nghĩa mọi phần `Body`/`Timestamp` đều được ký đúng policy; cần xác minh **references/signed parts cụ thể**. API có thể thay đổi theo Spring-WS/WSS4J version, cần đối chiếu khi biên dịch.

### 13.2. Đăng ký interceptor đúng với SOAP server

~~~java
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
@EnableWs
public class SoapServerConfigurer implements WsConfigurer {

    private final Wss4jSecurityInterceptor security;

    public SoapServerConfigurer(
            @Qualifier("inboundSignatureValidator")
            Wss4jSecurityInterceptor security) {
        this.security = security;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(security);
    }
}
~~~

Một bean WSS4J được tạo nhưng **không nằm trong chain của endpoint mapping đang được sử dụng** thì không bảo vệ request đó. Nếu ứng dụng có nhiều `EndpointMapping`, SOAP servlet hoặc application context, cần test tất cả đường vào.

### 13.3. Phía SOAP client: ký request

Ví dụ **cấu hình khung**, giả định `Crypto ownSigningCrypto` truy cập private key và chain của client:

~~~java
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

Wss4jSecurityInterceptor outboundSigner =
        new Wss4jSecurityInterceptor();

outboundSigner.setSecurementActions(
        "Timestamp Signature");
outboundSigner.setSecurementUsername(
        "partner-soap-signing");
outboundSigner.setSecurementSignatureCrypto(
        ownSigningCrypto);

// Cần thêm password/key callback thích hợp cho private key,
// signature parts, algorithms và policies theo WSS4J version.
~~~

`setSecurementUsername` trong ngữ cảnh Signature có thể được dùng để **chọn key alias**, không phải một HTTP username hay `wsse:UsernameToken` nếu `UsernameToken` không thuộc securement actions.

Client phải cấu hình **private-key password callback** hoặc nguồn khóa phù hợp để WSS4J có thể sử dụng private key. Đừng nhét mật khẩu private key trực tiếp vào mã nguồn hoặc SOAP Header.

### 13.4. Phía SOAP client: mã hóa cho certificate của server

~~~java
// Phác thảo các property WS-Security, không phải mã hoàn chỉnh.
outboundSecurity.setSecurementActions(
        "Timestamp Signature Encrypt");
outboundSecurity.setSecurementSignatureCrypto(
        ownSigningCrypto);
outboundSecurity.setSecurementEncryptionCrypto(
        recipientPublicCrypto);
outboundSecurity.setSecurementEncryptionUser(
        "payments-soap-encryption");
~~~

`recipientPublicCrypto` cung cấp public encryption certificate của server; tên alias `payments-soap-encryption` được resolve trong key/cert store của WSS4J. Client không cần và không được có private decryption key của Payments chỉ để mã hóa gửi tới Payments.

Trong code sản xuất, `outboundSecurity` phải là interceptor có đầy đủ signing alias/password callback, XML parts, encryption algorithms, key transport method và policy phù hợp. Cấu hình thứ tự `Signature`/`Encrypt` **không được thay tùy ý**; một số profile yêu cầu thứ tự xác định và interoperable tests.

### 13.5. SOAP security outbound không tự áp dụng cho `WebServiceTemplate`

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;

WebServiceTemplate client = new WebServiceTemplate();
client.setMarshaller(jaxbMarshaller);
client.setUnmarshaller(jaxbMarshaller);
client.setInterceptors(new ClientInterceptor[] {
        outboundSigner
});
~~~

`jaxbMarshaller` và `outboundSigner` là các bean/biến đã cấu hình ở ứng dụng. **`WsConfigurer.addInterceptors(...)` trên server không tự đăng ký interceptor cho SOAP client**. Ngược lại, outbound WSS4J settings không làm thay đổi cấu hình HTTPS transport nếu message sender chưa có SSLContext thích hợp.

Khi dùng cả client request sign/encrypt và response validation/decryption, security client interceptor phải được cấu hình cho **cả chiều gửi và chiều nhận** theo WSDL/WS-SecurityPolicy.

## 14. WSS4J Merlin và các kho khóa: vai trò theo đường dẫn

Apache WSS4J cung cấp `Crypto` implementations như Merlin để truy cập certificate/key material qua Java keystore/truststore. Một file cấu hình Merlin có thể chứa dạng property:

~~~properties
# Định hướng cấu hình, KHÔNG chứa secret thật.
org.apache.wss4j.crypto.provider=org.apache.wss4j.common.crypto.Merlin
org.apache.wss4j.crypto.merlin.keystore.type=pkcs12
org.apache.wss4j.crypto.merlin.keystore.file=/run/secrets/soap-signing.p12
org.apache.wss4j.crypto.merlin.keystore.alias=partner-soap-signing
org.apache.wss4j.crypto.merlin.keystore.password=SECRET_INJECTED_AT_RUNTIME
~~~

Đây là **mẫu property theo họ WSS4J Merlin**, không phải lời khuyên commit password vào file. Khi triển khai cần chọn cách **runtime injection/KeyStore load/crypto provider** phù hợp phiên bản. Nếu dùng HSM/PKCS#11, provider và key access có thể hoàn toàn khác ví dụ file PKCS12.

Một trust configuration cho signer có thể dùng dedicated truststore:

~~~properties
org.apache.wss4j.crypto.provider=org.apache.wss4j.common.crypto.Merlin
org.apache.wss4j.crypto.merlin.truststore.type=pkcs12
org.apache.wss4j.crypto.merlin.truststore.file=/run/secrets/approved-soap-signers.p12
org.apache.wss4j.crypto.merlin.truststore.password=SECRET_INJECTED_AT_RUNTIME
~~~

**Keystore chứa private signing key** và **truststore chứa signer trust anchors/public certs** có thể là hai stores khác nhau, do hai bên có mục đích khác nhau.

### 14.1. “Có public cert trong SOAP Header” vẫn cần truststore riêng?

Có. Một signature verifier có thể nhận signer certificate trực tiếp trong `BinarySecurityToken`, nhưng vẫn phải xác định liệu certificate/chain đó **được tổ chức chấp nhận**. Nếu server chỉ verify toán học với public key gửi cùng message mà không kiểm tra trust/identity, attacker có thể tạo một key pair của chính mình và ký request giả.

Trust material có thể là CA, certificate pin, hoặc policy tin cậy tương ứng đối tác. **Đừng tin mọi public certificate chỉ vì nó được gửi đến.**

### 14.2. Một store cho nhiều private keys

~~~text
soap-keys.p12
  alias client-soap-sign
    private key + certificate chain
  alias client-soap-decrypt
    private key + certificate chain
  alias partner-soap-encrypt
    trusted public certificate only
~~~

Một store vật lý có thể chứa các entry này nhưng **không nên coi các alias có quyền sử dụng như nhau**. Code signing không được vô tình chọn khóa decryption; crypto/trust policy và quyền truy cập nên tách khi khả thi.

### 14.3. Khóa nằm trong HSM hoặc cloud KMS

Khi dùng HSM, private key có thể **không bao giờ xuất ra file**. WSS4J Crypto/Java provider cần được cấu hình để gọi thao tác ký/giải mã qua provider, còn public certificates vẫn có thể phân phối để verify/encrypt.

Không mặc định một cloud KMS bất kỳ cung cấp XML Signature/Encryption tương thích trực tiếp. Cần kiểm tra:

- Thuật toán ký, padding và hash được provider hỗ trợ.
- Khả năng sử dụng với JCA/JCE và WSS4J version.
- Latency, concurrency và key selection.
- Quota, audit, HA/failover và rotation.
- Hành vi khi HSM/KMS không khả dụng.

Nếu không xác minh các điểm đó, việc đổi `.p12` thành “HSM key” có thể làm hệ thống không tạo được SOAP Signature dù TLS vẫn chạy bình thường.

## 15. XSD, WSDL và WS-SecurityPolicy: hợp đồng nghiệp vụ không tự khai báo khóa

Trong kiến trúc **contract-first**:

1. **XSD** định nghĩa cấu trúc SOAP Body và các kiểu dữ liệu nghiệp vụ như `SubmitPaymentRequest`, `amount` và `currency`.
2. **WSDL** mô tả operations, messages, SOAP binding và transport endpoint (`soap:address`).
3. **WS-SecurityPolicy** hoặc tài liệu tích hợp bảo mật quy định yêu cầu signature/encryption, token type, algorithm suite, signed/encrypted parts, timestamp, certificate trust và những điều kiện khác.

Một XSD hợp lệ không tự yêu cầu client ký XML. Một WSDL công bố `soap:address location="https://..."` cũng không có nghĩa message phải có `wsse:Security`.

### 15.1. Ví dụ một SOAP Body contract-first

~~~xml
<p:SubmitPaymentRequest
    xmlns:p="urn:example:payments:v1">
    <p:paymentRequestId>PAY-1001</p:paymentRequestId>
    <p:amount>250000</p:amount>
    <p:currency>VND</p:currency>
</p:SubmitPaymentRequest>
~~~

Thành phần này chịu schema validation. Một SOAP Signature đúng phải bảo vệ chính **SOAP Body thực tế được ứng dụng xử lý**, chứ không phải một bản sao XML nào đó nằm ở Header.

### 15.2. Ví dụ policy bằng ngôn ngữ tích hợp

Một tài liệu hợp đồng có thể quy định:

~~~text
Transport:
  - HTTPS TLS theo baseline doanh nghiệp
  - mTLS tại gateway đối với các đối tác được đăng ký

SOAP request:
  - WS-Security X.509 Signature
  - Ký SOAP Body và wsu:Timestamp
  - Timestamp TTL = 300 giây, future skew được giới hạn
  - Chữ ký phải xác minh với allowed partner certificates/CA

SOAP response:
  - Server ký SOAP Body/Fault khi policy yêu cầu
  - Client xác minh response signing identity

Optional confidentiality:
  - Mã hóa selected SOAP Body bằng recipient encryption cert

Business:
  - paymentRequestId chống ghi giao dịch trùng
~~~

Đây là **một profile giả định** để thảo luận, không phải các giá trị mặc định Spring-WS. Các bên phải thống nhất **thuật toán, identity mapping, acceptance/failure behavior, rotation và môi trường** trước khi sản xuất.

### 15.3. Tại sao JAXB không quan tâm đến TLS private key?

JAXB marshaller chuyển object Java thành XML payload. Nó không kiểm soát TLS handshake, không quyết định truststore, không ký SOAP Signature và không bảo vệ certificate chain.

Một pipeline client:

~~~mermaid
flowchart LR
    O["JAXB object"] --> M["Jaxb2Marshaller -> XML Body"]
    M --> W["WSS4J -> Signature/Encryption"]
    W --> H["HTTP message sender"]
    H --> T["TLS / mTLS"]
    T --> R["Remote SOAP service"]
~~~

Đây là sơ đồ lớp trách nhiệm, không khẳng định serializer luôn thực hiện từng bước theo thời gian đúng thứ tự như hình trong mọi provider. **Marshaller, WS-Security interceptor và HTTP TLS sender là ba thành phần cấu hình riêng**.

## 16. Chứng chỉ nào được trình ra khi SOAP server trả response?

Nếu server ký response, nó cần **private SOAP signing key phía server**, và client phải xác minh public signing certificate theo trust policy.

Nếu response được mã hóa cho client, server cần **public SOAP encryption certificate phía client**; client giải mã bằng **private decryption key phía client**.

~~~text
Request client -> server:
  SIGN: client private signing key
  VERIFY: server tin client signing certificate

  ENCRYPT: server public encryption certificate
  DECRYPT: server private decryption key

Response server -> client:
  SIGN: server private signing key
  VERIFY: client tin server signing certificate

  ENCRYPT: client public encryption certificate
  DECRYPT: client private decryption key
~~~

**Không dùng `soap:address` hoặc server TLS certificate để suy ra response SOAP signing identity**. Có những ứng dụng TLS terminate ở gateway nhưng SOAP response được ký bởi backend với một chứng chỉ riêng.

### 16.1. SOAP Fault cũng có thể cần chữ ký

Nếu hợp đồng yêu cầu signed SOAP responses, đường **SOAP Fault** cũng cần được đánh giá:

- Fault có thể do backend tạo trước khi trả về qua gateway.
- Fault có thể do security interceptor tạo khi xác minh request thất bại.
- Fault có thể do HTTP gateway tạo ở ngoài SOAP stack.
- Không phải mọi lỗi HTTP có SOAP Envelope hợp lệ để ký.

Một client không được coi HTTP 500 là một signed SOAP Fault chỉ vì response có status 500. Phải parse SOAP Envelope, kiểm tra `wsse:Security` và xác minh chữ ký/Fault theo chính sách phù hợp.

### 16.2. Không tin rằng response signing cert trùng server TLS cert

Giả sử:

~~~text
HTTPS host = api.example.test
TLS server cert = gateway-tls.example.test
SOAP response signing cert = payments-soap-signer
~~~

Đây có thể là thiết kế hợp lệ. Client cần **hai phép kiểm tra riêng**:

1. TLS: endpoint URL, chain, SAN, EKU, trust policy.
2. WS-Security: SOAP signature valid, signer certificate/identity được phép, đúng signed parts và freshness/replay policy.

Không chỉ kiểm tra certificate subject name giống chuỗi `CN=...` rồi tin cả hai cơ chế.

## 17. Khi gateway chỉnh sửa SOAP, chữ ký có thể hỏng ở đâu?

Sau TLS termination, gateway có thể:

- Thêm hoặc xóa SOAP Header.
- Thay đổi `wsa:To` hoặc `wsa:Action` để phù hợp routing.
- Chuyển đổi prefix, canonicalization-related structures hoặc XML namespaces.
- Thêm correlation ID.
- Re-serialize XML qua một SOAP implementation khác.
- Nén/giải nén MIME/MTOM contents.

Một số thay đổi XML chỉ là biểu diễn khác nhau và vẫn có thể giữ signature hợp lệ sau canonicalization; một số khác **làm thay đổi phần đã ký** và khiến verify thất bại.

### 17.1. Cần phân biệt ba vùng

| Vùng | Ai sở hữu bảo vệ? | Rủi ro |
| --- | --- | --- |
| TLS framing/HTTP headers | TLS peer, gateway, HTTP stack | TLS termination kết thúc bảo vệ kênh ban đầu |
| SOAP Header/Body được ký | XML Signature và WS-Security validator | Thay đổi signed elements làm chữ ký sai |
| SOAP Header/Body **không** được ký | Chính sách application; có thể cần ký thêm | Bị sửa mà signature vẫn hợp lệ |

Không giải quyết lỗi chữ ký bằng cách **bỏ SOAP Body khỏi signed parts** để gateway sửa tùy ý. Cách phù hợp là thiết kế gateway xử lý nguyên vẹn những phần cần bảo vệ, hoặc điều chỉnh trust boundary và contract với đối tác.

### 17.2. Có nên terminate rồi ký lại ở gateway?

Trong một số kiến trúc, gateway được ủy quyền:

1. Xác minh inbound signature của client.
2. Áp policy, chuyển đổi message.
3. Tạo **chữ ký mới bằng danh tính của gateway** cho downstream.

Khi đó backend xác minh **gateway signing identity**, không còn xác minh trực tiếp chữ ký client trên message đã bị chuyển đổi, trừ khi có cơ chế bảo tồn bằng chứng nguồn gốc phù hợp.

Đây là thay đổi **trust model** rõ rệt. Phải audit, gắn identity được xác thực từ client vào downstream context một cách chống giả mạo và không gọi việc ký lại là “end-to-end signature nguyên vẹn”.

## 18. Quản lý vòng đời chứng chỉ và khóa

Chứng chỉ sẽ hết hạn; private key có thể bị lộ; thuật toán có thể bị loại khỏi baseline; đối tác có thể đổi certificate khi đổi CA hoặc tổ chức.

Nếu hệ thống gộp mọi vai trò vào một key pair duy nhất, **mỗi lần thay certificate** có thể gây gián đoạn cả TLS, SOAP signing và decryption.

### 18.1. Lập bảng inventory theo mục đích

| Thuộc tính cần quản lý | Ví dụ |
| --- | --- |
| Service/partner | `orders-soap-prod` / `partner-A` |
| Role | `tls-server`, `mtls-client`, `soap-sign`, `soap-decrypt` |
| Alias hoặc key ID | `soap-signing-2026-11` |
| Certificate fingerprint (SHA-256) | Chuỗi hash public certificate, không phải password |
| Issuer/subject/SAN | Phục vụ identity mapping và chẩn đoán |
| NotBefore / NotAfter | Theo dõi thời hạn |
| EKU/KeyUsage/algorithm | Kiểm tra phù hợp policy |
| Kho lưu private key | HSM, secret manager, keystore volume |
| Trust distribution | Đối tác/gateway/backend/client nào đã cập nhật? |
| Rotation owner/runbook | Ai thực hiện, rollback thế nào? |
| Revocation process | Quy trình ứng phó compromise |

Không ghi private key hoặc mật khẩu vào inventory. **Fingerprint của public certificate** là metadata tiện lợi để so khớp, nhưng vẫn cần kênh phân phối trust đáng tin.

### 18.2. Quy trình rotation hai pha

Ví dụ đổi SOAP signing certificate từ `sign-v1` sang `sign-v2`:

~~~mermaid
flowchart TD
    A["Phát hành key/cert v2"] --> B["Phân phối public cert v2 tới verifier"]
    B --> C["Cho phép xác minh v1 và v2 trong overlap"]
    C --> D["Chuyển signer sang private key v2"]
    D --> E["Theo dõi signature success/failure"]
    E --> F["Ngừng chấp nhận v1 sau thời hạn an toàn"]
    F --> G["Thu hồi/hủy key v1 theo policy"]
~~~

Với **SOAP encryption certificate**, bên gửi có thể đang mã hóa cho public cert v1 trong khi backend đã chuyển sang private key v2. Nếu mất private key v1 quá sớm, các message đang chờ trong queue hoặc retry từ đối tác có thể không giải mã được.

Vì vậy cần tính:

- Thời gian tồn tại của message đang ở queue.
- Khoảng retry của client.
- Thời điểm hai bên chuyển sang public encryption cert mới.
- Khả năng backend giữ **decryption key cũ** trong giai đoạn chuyển tiếp có kiểm soát.
- Quy tắc kết thúc, hủy và thu hồi key cũ.

**Rotation khóa ký** và **rotation khóa mã hóa** có yêu cầu chồng lấn khác nhau. Với signing verifier, có thể cần tin cả old/new cert một thời gian; với encryption receiver, phải giữ khả năng giải mã những message cũ được phép tồn tại.

### 18.3. TLS rotation và SOAP key rotation cần lịch riêng

Một tổ chức có thể thay TLS cert 60-90 ngày/lần, trong khi SOAP signing cert theo PKI doanh nghiệp có lịch riêng. **Không trói lịch hai lớp** chỉ vì cả hai đều là X.509.

Khi rotation:

1. Giám sát thời hạn từng certificate theo role.
2. Đánh giá truststore của bên xác minh và thời gian phân phối.
3. Test handshake TLS và verify/decrypt SOAP riêng biệt.
4. Xác minh aliases và quyền truy cập secrets sau rollout.
5. Chuẩn bị rollback không làm sống lại một khóa đã bị thu hồi do lộ.

### 18.4. Sự cố lộ private key

Nếu private SOAP signing key của client bị lộ:

- Attacker có thể tạo SOAP Signature với danh tính đó, tùy trust/authorization policy.
- Thay **TLS server certificate** không tự khắc phục compromised SOAP signing key.
- Cần thu hồi/vô hiệu hóa signer identity, cập nhật trust, điều tra log, rà soát transactions và phát hành key mới.

Nếu private TLS server key bị lộ:

- Ưu tiên thay TLS certificate/key, kiểm tra các dịch vụ cùng dùng key, thu hồi theo chính sách và điều tra nguy cơ impersonation.
- SOAP Signature key riêng có thể vẫn an toàn, nhưng cần đánh giá xem hệ thống đã bị compromise rộng hơn hay chưa.

**Tách khóa giúp thu hẹp blast radius**, nhưng không thay việc kiểm tra quyền HSM, backup, log và truy cập hạ tầng.

## 19. Tình huống hệ thống nhiều đối tác và môi trường

Một doanh nghiệp tích hợp ba ngân hàng bằng SOAP:

~~~text
bank-a-prod:
  tls-endpoint = https://a.bank.example/ws
  tls-CA = CA-A
  soap-signer = BANK-A-SIGN-2026

bank-b-prod:
  tls-endpoint = https://b.bank.example/ws
  tls-CA = CA-B
  soap-signer = BANK-B-SIGN-2026

bank-c-staging:
  tls-endpoint = https://test.c.bank.example/ws
  tls-CA = STAGING-CA-C
  soap-signer = C-STAGING-SIGN
~~~

Các ranh giới cần giữ:

- **Staging truststore** không nên vô tình được dùng cho production.
- WSS4J signer trust của bank A không được mặc nhiên cấp quyền thay bank B.
- Private keys của một đối tác không được lộ cho luồng gọi đối tác khác.
- HTTP client pool/SSLContext được chọn theo endpoint, không dùng global trust-all.
- Cert/alias/key rotations được version theo partner/environment.
- Metadata giám sát phải biết lỗi xảy ra tại TLS connection hay message-level security.

### 19.1. Trust không chỉ là certificate chain

Một signing cert của bank A có thể được CA chung của nhiều ngân hàng cấp. Server vẫn cần **đối chiếu signer identity với Bank A** và operation/tenant đã đăng ký. Không chỉ vì certificate có chain hợp lệ mà signer được phép gửi `SubmitPayment` thay tất cả tenants.

### 19.2. Có thể dùng cấu hình động theo đối tác?

Có thể, nhưng phải có cơ chế chọn crypto/trust policy **trước hoặc trong quá trình security validation được kiểm soát**. Tránh chọn truststore bằng một chuỗi `partnerId` chưa xác thực trong SOAP Body vì attacker có thể khai danh tính của đối tác khác.

Một design hợp lý:

- Xác định entrypoint hoặc context tin cậy theo transport/client identity, nếu có.
- Xác minh signer certificate theo một tập trust được cho phép.
- Ánh xạ certificate identity sang partner principal đã xác thực.
- So khớp partner principal với payload/operation và tenant.

Không dùng `issuer CN contains "Bank"` hoặc tên file keystore để làm authorization.

## 20. Phân loại lỗi TLS, WS-Security và nghiệp vụ

Một lỗi được mô tả là “certificate invalid” có thể xảy ra ở **ba tầng hoàn toàn khác nhau**:

1. **TLS handshake**: client không tin server TLS cert, server từ chối mTLS client cert, private key/certificate mismatch, hoặc thuật toán không được hỗ trợ.
2. **SOAP WS-Security validation**: chữ ký XML sai, signer certificate không được tin, recipient decryption key không phù hợp, signed parts thiếu hoặc timestamp không hợp lệ.
3. **Authorization/business logic**: certificate đúng và signature hợp lệ nhưng principal không được phép gọi operation hoặc thực hiện giao dịch.

### 20.1. Bảng lỗi và nơi xử lý

| Triệu chứng | Tầng bị ảnh hưởng | Có SOAP Fault từ endpoint không? | Bước kiểm tra |
| --- | --- | --- | --- |
| `PKIX path building failed` khi gọi HTTPS | TLS trust path của client | Thường **không** | Client truststore, server chain |
| `No subject alternative DNS name matching` | TLS server identity | Không | SAN của TLS cert, URL thật |
| `bad_certificate` / client cert rejected | TLS/mTLS handshake | Không | Gateway trust, EKU, client alias |
| Server không chọn được private key TLS | TLS listener/keystore | Không | KeyStore alias, password, private key entry |
| SOAP `wsse:FailedCheck` hoặc signature validation failure | WS-Security | Có thể là SOAP Fault do security layer | Signed parts, cert trust, algorithm |
| SOAP decryption failure | WS-Security | Có thể có SOAP Fault | Recipient cert/alias, private decryption key |
| SOAP signer cert hết hạn | WS-Security trust/certificate policy | Có thể có SOAP Fault | SOAP cert validity và policy |
| Timestamp expired | WS-Security freshness | Có thể có SOAP Fault | UTC/TTL/skew, signed Timestamp |
| SOAP request bị từ chối vì nonce lặp | Replay validation | Có thể có SOAP Fault | Replay cache, key, cluster |
| JAXB unmarshalling failure | XML/schema/data binding | Có thể tạo SOAP Fault tùy đường xử lý | Root QName, XSD, JAXB classes |
| Principal không được phép dùng orderId | Authorization/business | Có thể là Fault nghiệp vụ theo contract | Authenticated identity, domain rules |
| HTTP 502 + HTML từ gateway | HTTP transport/gateway | **Không** nhất thiết có SOAP Envelope | Gateway logs, upstream health |
| HTTP 404 trước SOAP servlet | HTTP routing | Không | URL, servlet mapping |

**Không catch mọi exception rồi ném “certificate invalid”**. Điều đó che lỗi JAXB, timeout và security misconfiguration, đồng thời có thể tạo những retry không cần thiết hoặc làm lộ chi tiết hạ tầng.

### 20.2. SOAP Fault bảo mật là khác handshake exception

Một SOAP 1.1 Fault **minh họa**:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Client</faultcode>
            <faultstring>Security validation failed</faultstring>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

Đây không phải output cố định của Spring-WS. WS-Security có các fault code/profile riêng; SOAP 1.2 dùng `Code/Reason/Detail` và HTTP binding khác. Một security interceptor có thể tạo Fault **trước khi endpoint chạy**, không đi qua `SoapFaultMappingExceptionResolver` dành cho exception nghiệp vụ.

Nếu TLS handshake thất bại, SOAP request có thể **chưa được server SOAP nhận và parse**, nên đừng mong ứng dụng trả một SOAP Fault giải thích SAN/EKU của client.

### 20.3. Lỗi gì có thể retry?

- Chứng chỉ TLS hết hạn, SAN sai hoặc truststore thiếu CA: **không** giải quyết bằng retry request y nguyên.
- SOAP signature invalid hoặc signer chưa được trust: **không** nên retry vô hạn; sửa certificate/policy/clock hoặc payload được ký.
- HTTP 503/timeout: có thể cần retry có giới hạn **sau khi đánh giá tính idempotent** của operation.
- Business rejection (không đủ số dư, không đúng quyền): thường không retry mù quáng.

Đối với thao tác thanh toán, **đừng dùng sự thành công của TLS/WS-Security để suy giao dịch đã commit**. Transport + message authentication là điều kiện cần, không phải xác nhận kết quả nghiệp vụ.

## 21. Chẩn đoán “TLS chạy nhưng SOAP Signature lỗi”

Đây là tình huống thường gặp trong tích hợp doanh nghiệp:

~~~text
HTTPS connection: success
HTTP status: 500
Response: SOAP Fault "Security validation failed"
~~~

Vì HTTPS đã thành công, một số kỹ sư kiểm tra mãi TLS keystore, dù nguyên nhân nằm ở **SOAP signing certificate/alias/signed parts**.

### 21.1. Quy trình chẩn đoán theo tầng

1. **HTTP transport:** endpoint URL là gì? TLS termination ở gateway hay backend?
2. **TLS server:** certificate chain, SAN, EKU và truststore client có đúng không?
3. **mTLS:** client cert nào đã được trình ra, gateway/backend có xác minh không?
4. **SOAP Envelope:** version SOAP 1.1 hay 1.2? Content-Type/Action/WSDL binding đúng?
5. **WS-Security Header:** có Signature, Timestamp, token/certificate như profile yêu cầu không?
6. **Signer cert:** leaf cert public trong token/KeyInfo có đúng partner, đúng hạn và chain/trust hợp lệ?
7. **Signature references:** các phần được ký có phải chính Body và Timestamp hiện được application xử lý?
8. **Canonicalization:** có intermediary hoặc interceptor sửa phần đã ký sau khi signing?
9. **Encryption recipient:** có dùng public cert của đúng backend, đúng alias, algorithm và key transport policy?
10. **Replay/timestamp:** message còn mới, nonce/MessageID có bị phát lại?
11. **Authorization:** signer đã được map thành đúng principal/partner, có quyền operation không?
12. **Response:** client đã kiểm tra SOAP Fault, signature response và lỗi transport theo contract chưa?

Nếu chỉ thay truststore TLS mà SOAP Signature vẫn lỗi, đó không phải bằng chứng WSS4J hỏng. Hãy đối chiếu **certificate roles** và kiểm tra đúng tầng.

### 21.2. Cặp cấu hình sai rất phổ biến

~~~text
Spring Boot:
  server.ssl.key-store=/keys/gateway-tls.p12

WSS4J inbound:
  validationSignatureCrypto=/keys/partner-soap-trust.p12

WSS4J outbound:
  securementSignatureCrypto=/keys/backend-soap-sign.p12
~~~

**Ba đường dẫn có thể hoàn toàn khác nhau** mà vẫn đúng. Nếu developer thay `validationSignatureCrypto` bằng `gateway-tls.p12` chỉ vì “đó là chứng chỉ server”, chữ ký đối tác có thể bị từ chối vì kho đó không tin signer.

### 21.3. Chứng chỉ đã import nhưng signature vẫn bị từ chối

Các nguyên nhân thường thấy:

- Import nhầm **TLS server certificate** thay vì SOAP signer certificate.
- Public cert đúng nhưng thiếu chain/CA hoặc trust mapping.
- Khóa ký riêng không khớp certificate được đưa vào SOAP token.
- Signer certificate đã rotation nhưng verifier chưa thêm bản mới.
- Signature dùng thuật toán không được phép hoặc provider không hỗ trợ.
- Một intermediary làm thay đổi Body/header được ký.
- Signed-part policy yêu cầu Timestamp/Body nhưng client ký nhầm một element khác.
- Certificate đúng nhưng principal không được phép thực hiện operation.
- WSS4J version/provider khác nhau về WS-Security profile.

## 22. Kiểm tra certificate/keystore an toàn bằng công cụ dòng lệnh

Các lệnh dưới đây **chỉ là ví dụ để kỹ sư thực hiện trong môi trường được phép**; bài học không chạy lệnh, không tạo/đọc private keys trong project. Không đưa file keystore/secret thật vào repository hoặc đính kèm trong ticket công khai.

### 22.1. Xem metadata certificate mà không xuất private key

~~~bash
openssl x509 -in public-cert.pem -noout -subject -issuer -dates -serial -fingerprint -sha256
~~~

Kiểm tra SAN/KeyUsage/EKU bằng:

~~~bash
openssl x509 -in public-cert.pem -noout -text
~~~

Khi xem `-text`, cần kiểm tra các extension thực tế chứ không chỉ subject `CN`.

### 22.2. Xem aliases trong PKCS12 bằng Java `keytool`

~~~bash
keytool -list -v \
  -keystore /run/secrets/soap-signing.p12 \
  -storetype PKCS12
~~~

Lệnh có thể yêu cầu mật khẩu tương tác. **Không thêm `-storepass actual-password` vào một command được ghi trong shell history hoặc CI logs**. Kết quả giúp kiểm tra:

- Alias được WSS4J/JSSE tham chiếu có tồn tại không.
- Entry là `PrivateKeyEntry` hay `trustedCertEntry`.
- Chuỗi chứng chỉ và fingerprint.
- Validity, Issuer, Subject và extensions.

### 22.3. Vì sao không cần export private key để đối soát?

Đối tác muốn kiểm tra server/client public certificate chỉ cần **public cert/chain** hoặc fingerprint qua kênh tin cậy. Không cần:

- Export private key không mã hóa.
- Chụp màn hình keystore password.
- Upload toàn bộ `.p12` chứa private key lên email/chat.
- Vô hiệu hóa `hostnameVerifier` hoặc `trustManager`.

Nếu private key phải được chuyển giữa các HSM/service trong một quy trình có kiểm soát, đó là một **quy trình key management riêng**, không phải bước debug thông thường của SOAP integration.

### 22.4. Kiểm tra TLS khác kiểm tra SOAP Signature

~~~bash
# Xem TLS server certificate chain của một endpoint, theo nhu cầu test:
openssl s_client -connect api.example.test:443 -servername api.example.test -showcerts
~~~

Lệnh này quan sát **TLS connection**, không kiểm tra `ds:Signature` trong SOAP Envelope. Nó cũng không tự xác minh toàn bộ policy PKIX của ứng dụng nếu thiếu trust/hostname options tương ứng.

Để kiểm tra SOAP Signature, cần gửi/nhận SOAP message với WSS4J đã cấu hình trust và signed-part policy, đồng thời chạy negative tests (ký sai, dùng cert không được phép, sửa phần đã ký).

## 23. Kiểm thử TLS và WS-Security: hai bộ test độc lập

### 23.1. Ma trận kiểm thử

| Ca kiểm thử | Kỳ vọng | Tầng được chứng minh |
| --- | --- | --- |
| TLS server cert chain hợp lệ, SAN đúng | Client kết nối HTTPS được | TLS server trust |
| TLS server cert do CA chưa được trust | Handshake bị từ chối | TLS truststore |
| TLS server cert SAN sai hostname | Handshake bị từ chối | Hostname verification |
| TLS server cert hết hạn | Handshake bị từ chối | TLS certificate validity |
| mTLS cần client cert nhưng client không cung cấp | Handshake bị từ chối | mTLS |
| mTLS client cert sai EKU/CA | Bị từ chối theo TLS policy | mTLS client trust |
| TLS hợp lệ, SOAP không có Signature bắt buộc | WS-Security từ chối | Message policy |
| TLS hợp lệ, SOAP ký bằng cert không được trust | WS-Security từ chối | SOAP signer trust |
| SOAP cert hợp lệ, Body đã bị sửa | XML Signature verify thất bại | Signed Body integrity |
| SOAP cert hợp lệ, Timestamp bị sửa | Signature/freshness thất bại theo policy | Signed Timestamp |
| SOAP Signature hợp lệ nhưng amount thiếu | XSD validation từ chối | Schema contract |
| SOAP Signature hợp lệ nhưng principal không có quyền | Authorization từ chối | Business access control |
| Request ký đúng, recipient encryption cert sai | Backend không giải mã được | Message encryption |
| Client cũ vẫn mã hóa tới cert v1 trong rotation | Backend hỗ trợ grace period nếu policy cho phép | Key rotation |
| TLS gateway cert được rotation | HTTPS tiếp tục kết nối qua trust được cập nhật | TLS rotation |
| SOAP signer cert được rotation | Verifier chấp nhận v2, không chấp nhận v1 sau cutoff | SOAP rotation |
| SOAP Body đúng, attachment chưa được ký | Test policy phát hiện thiếu coverage | Attachment security |
| SOAP request giống hệt được phát lại | Replay detector từ chối nếu profile yêu cầu | Freshness/replay |
| HTTP 502 + HTML | Client xử lý transport failure | HTTP/gateway |
| SOAP Fault từ backend có signature bắt buộc | Client verify được Fault theo policy | Response security |

### 23.2. Spring-WS mock và HTTP integration test

**`MockWebServiceClient`** giúp kiểm tra endpoint/WS-Security interceptor trong Spring application context; **`MockWebServiceServer`** giúp kiểm tra `WebServiceTemplate` client và SOAP message được tạo/nhận. Tuy nhiên:

- Mock không tự kiểm tra TLS handshake và SAN.
- Mock không chứng minh gateway chuyển tiếp mTLS identity an toàn.
- Một test XML Signature đơn lẻ không chứng minh key rotation hoặc multi-instance replay cache.
- Mock SOAP Fault không thay việc kiểm tra HTTP Content-Type/status.

Cần thêm **test HTTPS thật** (test container/gateway hoặc môi trường staging được quản trị) và **interop tests** với SOAP stack phía đối tác.

### 23.3. Test “đổi đúng một yếu tố”

Khi debug, dùng một request thành công làm baseline:

~~~text
Baseline:
  TLS handshake valid
  SOAP Body valid XSD
  Signature valid with approved cert
  Timestamp current
  Principal authorized
~~~

Sau đó lần lượt:

1. Thay **TLS server certificate** sai SAN; SOAP message giữ nguyên.
2. Phục hồi TLS, thay **SOAP signer certificate** không được trust.
3. Phục hồi cert, sửa **amount** trong SOAP Body sau khi ký.
4. Phục hồi Body, sửa **Timestamp** sau khi ký.
5. Phục hồi Signature, dùng valid signer nhưng không có quyền operation.
6. Phục hồi quyền, gửi lại request nguyên vẹn để kiểm tra replay.

Mỗi bước phải tạo một kết quả lỗi ở **tầng dự kiến**, không lấy thông báo ngoại lệ Java bất kỳ làm bằng chứng duy nhất.

## 24. Bài tập tình huống: giao dịch qua gateway và ngân hàng

Một doanh nghiệp gọi SOAP API của ngân hàng qua:

~~~text
HTTP destination:
  https://gateway.bank.example/payments

Gateway TLS certificate:
  tls-gateway-bank-2026

Mutual TLS client certificate:
  company-tls-client-2026

SOAP signer certificate của doanh nghiệp:
  company-soap-sign-2026

SOAP encryption certificate của ngân hàng:
  bank-soap-encrypt-2026
~~~

Client có **cấu hình SAI có chủ ý** sau (các certificate bị đặt nhầm vai trò):

~~~text
server SSL truststore   = company-soap-sign.p12
SOAP signature crypto   = company-tls-client.p12
SOAP encryption user    = tls-gateway-bank-2026
~~~

Sau triển khai, HTTPS kết nối thành công khi tắt SOAP security, nhưng khi bật ký/mã hóa thì ngân hàng trả SOAP Fault. Một lập trình viên đề xuất tắt kiểm tra signature vì “mTLS đã đủ”.

### 24.1. Câu hỏi

1. Client HTTPS phải tin certificate nào?
2. Client mTLS cần private key nào?
3. Client phải dùng private key nào để ký SOAP Body?
4. Client cần public cert nào để mã hóa message cho ngân hàng?
5. Server ngân hàng cần trust public cert nào để xác minh SOAP signer?
6. Server ngân hàng cần private key nào để giải mã Body?
7. Vì sao không thể chỉ thay TLS truststore để sửa SOAP Signature?
8. Nếu gateway terminate TLS, backend có tự nhìn thấy mTLS client cert không?
9. SOAP signer certificate hợp lệ có tự chứng minh doanh nghiệp được quyền thực hiện `SubmitPayment` không?
10. Khi ngân hàng xoay vòng SOAP encryption cert, cần chú ý điều gì với message đang chờ xử lý?
11. Một chữ ký đúng trên Timestamp nhưng không đúng trên Body có bảo vệ `amount` không?
12. Nên tắt Signature validation để hết lỗi hay sửa cấu hình?

### 24.2. Đáp án

1. Client TLS phải trust **TLS server certificate/CA của gateway** và xác minh SAN trùng `gateway.bank.example`.
2. Client cần **private mTLS client key** tương ứng `company-tls-client-2026`.
3. Client cần **private SOAP signing key** tương ứng `company-soap-sign-2026`.
4. Client cần **public SOAP encryption certificate của ngân hàng**, tức `bank-soap-encrypt-2026`.
5. Server cần trust **public SOAP signing certificate/chain của doanh nghiệp**, kiểm tra signer principal theo policy.
6. Backend ngân hàng cần **private SOAP decryption key** tương ứng public cert dùng để mã hóa.
7. TLS truststore dùng cho handshake; WSS4J SOAP signing crypto/trust **được cấu hình riêng**. Đổi một kho không tự sửa kho kia.
8. **Không mặc nhiên.** Gateway có thể chuyển tiếp identity qua kênh được bảo vệ, nhưng backend phải xác minh nguồn/ngữ nghĩa identity đó.
9. **Không.** Cần authentication mapping và authorization theo operation/tenant/payment account.
10. Bên gửi phải cập nhật public cert mới; bên nhận có thể cần tiếp tục giải mã thông điệp cũ bằng private key cũ trong overlap theo policy.
11. **Không.** `amount` chỉ được bảo vệ nếu Body hoặc phần thích hợp có trong signed references và validation xác minh đúng phần nghiệp vụ.
12. **Sửa cấu hình và trust model**. Tắt Signature phá điều kiện hợp đồng và có thể làm message bị chỉnh sửa mà backend không phát hiện.

### 24.3. Bài thực hành mở rộng

Thiết kế một Spring-WS `PaymentClient` và `PaymentEndpoint` với:

- XSD/WSDL định nghĩa `SubmitPaymentRequest` và `SubmitPaymentResponse`.
- Spring Boot HTTPS endpoint hoặc gateway test với server TLS certificate.
- TLS client truststore xác minh SAN đúng.
- mTLS client identity nếu hợp đồng yêu cầu.
- WSS4J client ký SOAP Body/Timestamp bằng SOAP signing key riêng.
- WSS4J server verify signer theo trust/allowlist riêng.
- WS-Security encryption đến recipient public encryption cert, backend decrypt bằng private key riêng khi có yêu cầu.
- Replay cache và business idempotency cho thao tác ghi.
- SOAP Fault an toàn và client phân biệt HTTP/TLS failure.
- Test các lỗi truststore, wrong alias, expired certificate, incorrect signed parts và key rotation.

**Tiêu chí đạt:** mỗi chứng chỉ/khóa được gắn đúng vai trò; test chứng minh TLS/mTLS và WS-Security **độc lập nhưng bổ trợ**, không có bypass signature, không rò rỉ private keys.

## 25. Checklist trước khi đưa dịch vụ Spring-WS vào production

### 25.1. Kiểm tra transport TLS/mTLS

1. **URL đúng:** client kết nối tới host/path được WSDL và hợp đồng công bố.
2. **TLS server cert:** có SAN phù hợp hostname public, chain/trust và EKU đúng.
3. **TLS client cert:** nếu mTLS cần, xác định peer nào yêu cầu và xác minh certificate.
4. **TLS private keys:** đặt ở đúng TLS terminator/client, không phân phối cho bên chỉ cần verify.
5. **SSLContext:** trust/key managers được gắn đúng HTTP message sender, không dùng trust-all.
6. **Timeout/pool:** cấu hình connect/read timeouts, connection reuse, redirects và resource limits.
7. **Gateway:** biết TLS terminate ở đâu; identity forwarding được xác thực, không chấp nhận spoofing.
8. **Revocation/rotation:** có quy trình cho expired/compromised cert và giám sát trước hạn.

### 25.2. Kiểm tra WS-Security message-level

9. **Signer private key:** ứng dụng ký SOAP dùng đúng alias/key, không nhầm với mTLS certificate.
10. **Signer trust:** verifier chỉ chấp nhận certificate/identity được policy cho phép.
11. **Signed parts:** SOAP Body, Timestamp, WS-Addressing headers quan trọng được ký theo yêu cầu.
12. **Encryption recipient:** public cert của đúng đối tác/recipient, private decryption key giữ ở bên nhận.
13. **Message crypto:** WSS4J `Crypto`/keystore/truststore được khai báo **độc lập** với JSSE TLS truststore.
14. **Security actions:** outbound `Signature`/`Encrypt` và inbound validation/decryption phù hợp SOAP binding/profile.
15. **Algorithms:** sử dụng thuật toán và provider được tổ chức chấp nhận, tương thích client đối tác.
16. **Freshness:** timestamp, clock skew, nonce/replay cache được cấu hình và kiểm thử.
17. **Replay/idempotency:** không đồng nhất signature hợp lệ với unique message hoặc transaction.
18. **Authorization:** signer principal được phép operation/tenant/resource cụ thể.
19. **SOAP Fault:** đường security failure không lộ secret, client phân biệt transport và SOAP Fault.
20. **MTOM/attachments:** nếu có, kiểm tra liệu MIME attachments có được bảo vệ theo profile hay không.

### 25.3. Kiểm tra vận hành và khả năng tương thích

21. **Key inventory:** từng key/cert có role, alias, owner, fingerprint, expiry, môi trường và runbook.
22. **Secret handling:** không commit keystore password/private key, không log bí mật, hạn chế quyền và dùng HSM/vault khi phù hợp.
23. **Rotation overlap:** public cert mới được phân phối trước khi signer chuyển; old decryption key chỉ giữ lâu theo policy.
24. **Fail-closed:** khi trust/certificate validation thất bại, không tự bypass để “hết lỗi”.
25. **Regression tests:** handshake TLS, mTLS, SOAP sign/verify/encrypt/decrypt, signed parts, Fault và key rotation.
26. **Interoperability:** xác minh Java/Spring-WS và SOAP client khác (ví dụ .NET) dùng cùng XSD/WSDL/WS-SecurityPolicy.
27. **Observability:** log kết quả TLS/message validation, identity đã xác minh và correlation ID, **không** log private key/digest/raw SOAP nhạy cảm.
28. **Disaster recovery:** biết cách thu hồi signer bị compromise và phục hồi khóa giải mã cần thiết cho message đang tồn tại.
29. **Environment isolation:** staging và production tách trust, secrets, tenant identities và endpoints.
30. **Change control:** mỗi lần nâng Spring Boot, Spring-WS, WSS4J, Java hoặc HTTP provider phải kiểm tra lại behavior thực tế.

## 26. Tổng kết

- **Chứng chỉ TLS** được dùng ở **transport layer**: server chứng minh danh tính HTTPS; với mTLS, client cũng trình chứng chỉ để TLS peer xác minh.
- **Chứng chỉ WS-Security** được dùng ở **message layer**: public certificate giúp xác minh XML Signature hoặc mã hóa cho recipient; private key tương ứng dùng để ký hoặc giải mã.
- **Private key của người ký ở phía người ký**, **private key giải mã ở phía người nhận**. Đối tác chỉ cần public certificates/chain phù hợp và policy trust để verify/encrypt.
- **TLS certificate, mTLS client certificate, SOAP signing certificate và SOAP encryption certificate là các vai trò khác nhau**. Chúng có thể thuộc cùng tổ chức nhưng không bắt buộc dùng chung key pair.
- **`server.ssl.*` của Spring Boot** không tự cấu hình WSS4J, và **`Wss4jSecurityInterceptor`** không tự cấu hình outbound HTTPS `SSLContext`/truststore của `WebServiceTemplate`.
- **Certificate chain hợp lệ không tự cấp quyền nghiệp vụ**. Phải kiểm tra trust, đúng signer identity, signed parts, principal authorization và XSD/WSDL contract.
- **Chữ ký SOAP chỉ bảo vệ những phần thực sự được ký**; gateway có thể terminate TLS mà không phá chữ ký message, nhưng cũng có thể làm signature thất bại nếu sửa nội dung được ký.
- **XML Encryption** dùng public encryption cert của người nhận, còn người nhận dùng private decryption key. Không gửi private key của server cho client.
- **Timestamp, nonce, replay cache và idempotency** bổ sung cho TLS/chữ ký; một signed request hợp lệ vẫn có thể bị gửi lại.
- **Rotation** của TLS, signer và decryption keys cần kế hoạch riêng, có thời gian chồng lấn, kiểm thử trust và quản lý messages đang chờ.
- **Kiểm thử tách tầng** TLS/mTLS, SOAP Signature/Encryption, SOAP Fault, JAXB/XSD, gateway và nghiệp vụ là cách chứng minh hệ thống Spring-WS tích hợp doanh nghiệp an toàn và ổn định.
