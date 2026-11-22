# 15.4 Cipher suite và khác biệt về thành phần thương lượng giữa các phiên bản TLS

Khi một ứng dụng Java kết nối HTTPS, gRPC hoặc một dịch vụ TCP sử dụng TLS, hai phía không chỉ “bật TLS” rồi trao đổi dữ liệu. Chúng phải thống nhất **phiên bản giao thức, thuật toán bảo vệ record, cách thiết lập khóa chung và phương thức xác thực**. Một phần của việc này được mô tả bởi **cipher suite**. Tuy nhiên, **TLS 1.2 và TLS 1.3 định nghĩa ý nghĩa cipher suite khác nhau một cách căn bản**.

Trong TLS 1.2, một tên cipher suite thường nêu cả **cơ chế trao đổi khóa / xác thực phía server**, thuật toán mã hóa record và thuật toán MAC hoặc PRF. Trong TLS 1.3, cipher suite chủ yếu chọn **AEAD cho record** và **hash dùng trong HKDF/key schedule**; **key exchange group** và **signature algorithm** được thương lượng riêng qua extension. Vì vậy, đọc tên TLS 1.3 như thể nó là tên TLS 1.2 dẫn đến cấu hình sai, phân tích log sai và đôi khi hiểu nhầm mức bảo mật.

Bài học giải thích chi tiết việc thương lượng TLS 1.2 và TLS 1.3, cách đọc tên, vai trò ClientHello/ServerHello, certificate, supported_groups/key_share/signature_algorithms, PFS, ALPN, tình huống không tương thích và cách quan sát trên Java 17+ JSSE. Hai ví dụ Java biên dịch và chạy được giúp phân biệt **supported**, **enabled** và **actually negotiated**.

## 1. TLS thương lượng những gì?

**TLS (Transport Layer Security)** bảo vệ kênh liên lạc giữa hai endpoint. Ở cấu hình thông dụng, TLS cần:

1. **Protocol version:** TLS 1.2 hay TLS 1.3, quyết định cấu trúc handshake, key schedule và record protection.
2. **Record-protection algorithm:** cách mã hóa, xác thực và phát hiện dữ liệu bị sửa, ví dụ AES-GCM hoặc ChaCha20-Poly1305.
3. **Key establishment:** cách hai phía tạo ra các traffic secrets, thường dùng ephemeral (EC)DHE; TLS 1.3 còn hỗ trợ PSK và PSK+(EC)DHE.
4. **Peer authentication:** cách bên nhận xác minh server (và tùy chọn client), thường qua chứng chỉ X.509 và chữ ký số; hoặc bằng PSK theo cấu hình.
5. **Key derivation / transcript integrity:** thuật toán dẫn xuất key, hash của transcript và Finished nhằm ràng buộc các bước handshake.
6. **Thông tin ở tầng ứng dụng:** SNI để tìm virtual host; ALPN để chọn HTTP/2, HTTP/1.1 hoặc giao thức ứng dụng khác. Chúng là extension/chính sách riêng, **không phải một phần của tên cipher suite**.

~~~text
Ứng dụng Java (HTTPS, gRPC, TCP/TLS)
                   |
             JSSE / SSLEngine
                   |
        +----------+----------------------------+
        |                                       |
   TLS handshake                            TLS records
        |                                       |
protocol + cipher suite                  traffic keys/nonce
key exchange + authentication            AEAD / record integrity
SNI + ALPN + transcript                  protected application data
        |
        v
  SSLSession: protocol và cipher suite ĐÃ chọn
~~~

**Cipher suite không đồng nghĩa với toàn bộ TLS security profile.** Một kết nối có thể ghi nhận TLS_AES_128_GCM_SHA256, nhưng log riêng còn cần xác định certificate/issuer, key exchange group, signature scheme, ALPN và chính sách TLS endpoint nếu muốn đánh giá đầy đủ.

### 1.1. Ba trạng thái thường bị nhầm

| Khái niệm | Ý nghĩa | API Java thường dùng |
| --- | --- | --- |
| **Supported** | Implementation/provider có thể hỗ trợ thuật toán hoặc phiên bản | SSLContext.getSupportedSSLParameters, SSLSocket.getSupportedCipherSuites / getSupportedProtocols. |
| **Enabled** | Những lựa chọn được bật trong cấu hình endpoint, có thể bị policy/provider giới hạn | SSLContext.getDefaultSSLParameters, SSLSocket.getEnabledCipherSuites / getEnabledProtocols. |
| **Negotiated** | **Một lựa chọn cụ thể đã được hai phía chọn sau handshake thành công** | SSLSocket.getSession().getCipherSuite(), getSession().getProtocol(). |

**Supported không chắc đã enabled; enabled không chắc đã negotiated.** Nếu peer không hỗ trợ, certificate không phù hợp, thiếu group/key share hoặc bị chính sách algorithm constraints loại bỏ, handshake có thể thất bại. Kết quả cuối còn chịu ảnh hưởng provider, JDK config, key material và policy của hai phía.

## 2. Cách đọc tên cipher suite trong TLS 1.2

Một cấu trúc phổ biến của các suite TLS 1.2:

~~~text
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
|    |     |         |   |   |   |
|    |     |         |   |   |   +--> PRF hash: SHA-256
|    |     |         |   |   +------> AES mode GCM (AEAD)
|    |     |         |   +----------> AES key 128-bit
|    |     |         +--------------> record encryption algorithm
|    |     +------------------------> RSA-based server authentication
|    +------------------------------> Ephemeral EC Diffie–Hellman key agreement
+-----------------------------------> TLS cipher suite name prefix
~~~

Đây là cách diễn giải tên cụ thể, không phải grammar áp dụng cho mọi cipher suite lịch sử: một số suite dùng RSA key transport, static DH, PSK, CBC/HMAC hoặc các biến thể khác.

**TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256** có nghĩa:

- **ECDHE:** hai phía thực hiện **ephemeral Elliptic Curve Diffie–Hellman**, tạo shared secret. Ephemeral key agreement giúp có **forward secrecy** khi triển khai đúng.
- **RSA:** server chứng minh quyền sở hữu **private key RSA** tương ứng certificate bằng phép ký handshake (authentication). **Không có nghĩa client lấy RSA public key để mã hóa premaster secret** trong suite ECDHE_RSA.
- **AES_128_GCM:** record protection dùng AES-128-GCM thuộc họ **AEAD**, bảo vệ cả confidentiality lẫn integrity.
- **SHA256 ở cuối:** theo RFC 5289, là **hash của TLS 1.2 PRF** cho suite GCM này. **Không phải HMAC-SHA256 được tính độc lập lên từng record**, bởi GCM đã có authentication tag riêng.

### 2.1. So sánh vài suite TLS 1.2

| Tên suite TLS 1.2 | Key establishment / authentication | Bảo vệ dữ liệu | Lưu ý |
| --- | --- | --- | --- |
| **TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256** | Ephemeral ECDH, server certificate RSA | AES-128-GCM AEAD | ECDHE cho PFS; SHA256 là PRF hash. |
| **TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256** | Ephemeral ECDH, server certificate ECDSA | AES-128-GCM AEAD | ECDHE là trao đổi khóa, ECDSA là ký/xác thực. |
| **TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384** | Ephemeral ECDH, RSA authentication | AES-256-GCM AEAD | SHA384 là PRF hash theo profile. |
| **TLS_RSA_WITH_AES_128_GCM_SHA256** | RSA key transport và RSA authentication | AES-128-GCM AEAD | **Không có PFS** theo cơ chế RSA key transport; không dùng cho thiết kế mới. |
| **TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA** | Ephemeral ECDH, RSA authentication | AES-CBC + HMAC-SHA1 | Legacy CBC/MAC; đòi hỏi xử lý padding/oracle đúng, tránh khi có AEAD tốt hơn. |

Các tên trong bảng **không đương nhiên enabled** trên mọi Java runtime. Một thuật toán được provider hỗ trợ có thể bị **jdk.tls.disabledAlgorithms**, certificate policy, khuyết thiếu key material hoặc cấu hình ứng dụng vô hiệu hóa.

### 2.2. Vì sao _SHA và _SHA256 không luôn cùng ý nghĩa?

Trong **TLS 1.2 CBC suites**, phần đuôi như **_SHA** có thể xác định HMAC-SHA1 dùng cho record MAC, còn PRF của TLS 1.2 theo quy định thích hợp (thường SHA-256). Trong **TLS 1.2 AEAD/GCM suites** như ECDHE_RSA_WITH_AES_128_GCM_SHA256, **GCM authentication tag** thay chức năng record HMAC; **SHA256** chỉ định PRF hash.

**Không nhìn thấy SHA256 rồi kết luận record dùng HMAC-SHA256**, và cũng không nhìn thấy _RSA rồi kết luận đang dùng RSA key exchange. Phải phân tích **toàn bộ scheme** theo đặc tả của suite.

## 3. TLS 1.2 thương lượng key exchange và authentication như thế nào?

Một TLS 1.2 full handshake dùng certificate và ECDHE có thể được hình dung:

~~~text
Client                                           Server
  |                                                |
  | ClientHello: version, suites, groups, extensions|
  |----------------------------------------------->|
  |                                                |
  |       ServerHello: version, chọn cipher suite   |
  |       Certificate (RSA/ECDSA theo suite)        |
  |       ServerKeyExchange: ephemeral params + ký  |
  |       ServerHelloDone                           |
  |<-----------------------------------------------|
  | ClientKeyExchange: ephemeral key share          |
  | ChangeCipherSpec + Finished                     |
  |----------------------------------------------->|
  |                  ChangeCipherSpec + Finished    |
  |<-----------------------------------------------|
  |            application data protected           |
~~~

Đây là **sơ đồ đơn giản hóa** cho handshake đầy đủ TLS 1.2 dùng ECDHE; các extension, certificate request/client authentication và resumed handshakes có thể thay đổi thông điệp. Dòng **ServerKeyExchange** quan trọng với ECDHE, vì server phải ràng buộc ephemeral parameters bằng chữ ký/cơ chế xác thực thích hợp.

- **ClientHello** công bố các cipher suite chấp nhận được, version và các extension tương ứng.
- **ServerHello** chọn một suite phù hợp trong danh sách client đưa ra và policy server.
- Các phần ECDHE và certificate phải **tương thích với key exchange/authentication đã được chọn trong suite**.
- Hai phía cùng tính key material, xác minh handshake transcript/Finished; nếu không khớp hoặc certificate không tin cậy, handshake thất bại.
- **ALPN** có thể được thương lượng qua extension độc lập; một kết nối TLS 1.2 có thể chạy HTTP/2 hoặc HTTP/1.1 tùy chính sách chấp nhận và cấu hình.

Nếu server chỉ có certificate ECDSA, nó không thể đơn giản chọn suite **ECDHE_RSA** mà không có RSA key/đặc tính xác thực phù hợp. Ngược lại, TLS 1.2 suite **ECDHE_ECDSA** yêu cầu certificate/cơ chế ký tương ứng.

### 3.1. RSA key transport khác ECDHE_RSA

| Cơ chế TLS 1.2 | Vai trò RSA | Forward secrecy khi private key certificate bị lộ sau này? |
| --- | --- | --- |
| **TLS_RSA_...** | Client mã hóa premaster secret bằng RSA public key của server | **Không**, vì bản ghi handshake có thể bị lưu để giải mã về sau bằng RSA private key bị lộ. |
| **TLS_ECDHE_RSA_...** | RSA private key ký/xác thực ephemeral ECDHE handshake | **Có thể có PFS** khi ephemeral secret được xử lý/xóa an toàn. |

Do đó, **“có RSA trong tên” không đủ biết có PFS hay không**. Phân biệt **TLS_RSA_** và **TLS_ECDHE_RSA_**.

## 4. TLS 1.3 định nghĩa cipher suite lại từ đầu

RFC 8446 thay đổi quan trọng: một **TLS 1.3 cipher suite** quy định **cặp (AEAD cho record protection, hash dùng cho HKDF)**, **không quy định key exchange/authentication trong tên suite**.

~~~text
TLS_AES_128_GCM_SHA256
|   |   |   |   |
|   |   |   |   +--> Hash SHA-256 cho HKDF và handshake transcript
|   |   |   +------> GCM mode
|   |   +----------> AES key 128 bit
|   +--------------> AEAD algorithm cho TLS record
+------------------> TLS cipher suite
~~~

**TLS_AES_128_GCM_SHA256** không cho biết server đang dùng RSA, ECDSA hay Ed25519 certificate, cũng không cho biết key exchange group là X25519 hay P-256. Những thành phần này được thương lượng **riêng**, nên **cùng một TLS 1.3 suite có thể đi cùng nhiều loại certificate và group** được cho phép.

### 4.1. Những suite được RFC 8446 định nghĩa

| TLS 1.3 cipher suite | AEAD / protection | Hash cho HKDF / transcript | Nhận xét |
| --- | --- | --- | --- |
| **TLS_AES_128_GCM_SHA256** | AES-128-GCM | SHA-256 | Phổ biến, có thể tận dụng tăng tốc AES. |
| **TLS_AES_256_GCM_SHA384** | AES-256-GCM | SHA-384 | Khóa AES 256 bit; cần support/policy tương ứng. |
| **TLS_CHACHA20_POLY1305_SHA256** | ChaCha20-Poly1305 | SHA-256 | Phù hợp môi trường không có tăng tốc AES tốt. |
| **TLS_AES_128_CCM_SHA256** | AES-128-CCM | SHA-256 | Được RFC xác định, support phụ thuộc implementation. |
| **TLS_AES_128_CCM_8_SHA256** | AES-128-CCM tag 8 byte | SHA-256 | Profile tag ngắn, cần kiểm tra policy và giới hạn ứng dụng. |

Đây là **danh sách suite TLS 1.3 được RFC 8446 định nghĩa ban đầu**, không phải bảo đảm rằng Java/provider hiện tại hỗ trợ hoặc bật tất cả. Các RFC khác có thể đăng ký cipher suite bổ sung; khi đánh giá thực tế phải dựa vào registry, chuẩn liên quan và policy triển khai.

### 4.2. SHA256 trong tên TLS 1.3 dùng cho việc gì?

TLS 1.3 dùng **HKDF** để dẫn xuất **handshake traffic secrets, application traffic secrets, key/IV** từ shared secret và transcript của handshake. Hash của cipher suite cũng được dùng cho **transcript hash/Finished key schedule**.

**Không dùng SHA-256 làm record MAC rời** khi chọn AES-GCM: record đã được **AEAD** xác thực bằng authentication tag. Vì vậy, từ tên TLS_AES_128_GCM_SHA256 ta có thể biết AES-GCM và HKDF-SHA256, **không thể suy ra public key algorithm hoặc phiên bản chứng chỉ**.

### 4.3. TLS 1.3 và TLS 1.2 suite không thể hoán đổi

Theo RFC 8446:

- **TLS 1.3 cipher suite** như TLS_AES_128_GCM_SHA256 **chỉ dùng trong TLS 1.3**.
- **TLS 1.2 suite** như TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256 **không được thương lượng làm TLS 1.3 suite**.
- Dù hai tên đều chứa **AES_128_GCM_SHA256**, chúng không chỉ là hai spelling của cùng một bộ tham số. Một tên chỉ định key exchange/authentication ở TLS 1.2; tên kia chỉ AEAD/HKDF hash ở TLS 1.3.

Đây là lý do **không cấu hình một tập tên suite TLS 1.2 rồi mong TLS 1.3 tự dùng nó**. JSSE có thể có chung API setEnabledCipherSuites cho cả hai phiên bản, nhưng người lập trình phải chọn các cipher suite **phù hợp từng TLS protocol**.

## 5. TLS 1.3 thương lượng thêm những thành phần nào?

Theo RFC 8446 §4.1.1, ở kết nối certificate-based (không chọn PSK), các nhóm lựa chọn gần như độc lập:

1. **cipher_suites:** cặp AEAD/HKDF hash.
2. **supported_groups + key_share:** nhóm (EC)DHE hỗ trợ và key share đang gửi để thiết lập shared secret.
3. **signature_algorithms** (và có thể signature_algorithms_cert): thuật toán ký mà bên nhận chấp nhận cho xác thực và certificate.
4. **supported_versions:** những phiên bản TLS mà client thực sự hỗ trợ.
5. Nếu dùng PSK: **pre_shared_key + psk_key_exchange_modes** bổ sung một con đường xác thực/thiết lập khóa; thay đổi những tập lựa chọn hợp lệ.

Ngoài ra **ALPN** có thể chọn giao thức ứng dụng, **server_name (SNI)** giúp định tuyến virtual host/certificate. Chúng **không được thể hiện trong cipher suite name**.

~~~text
ClientHello TLS 1.3
 |
 +-- supported_versions: [TLS 1.3, TLS 1.2]
 +-- cipher_suites: [TLS_AES_128_GCM_SHA256, TLS_CHACHA20_POLY1305_SHA256, ...]
 +-- supported_groups: [X25519, secp256r1, ...]
 +-- key_share: key-share cho một/vài group
 +-- signature_algorithms: [RSA-PSS, ECDSA, Ed25519, ...]
 +-- signature_algorithms_cert: optional
 +-- server_name / ALPN: ví dụ api.example và h2/http1.1
 +-- PSK extensions: khi dùng PSK/resumption
 |
 v
Server selects a compatible combination
 |
 +-- TLS version
 +-- one TLS 1.3 cipher suite (AEAD + hash)
 +-- group/key share (nếu dùng DHE)
 +-- cert + handshake signature scheme (nếu dùng certificate)
 +-- ALPN (nếu ứng dụng dùng)
 |
 v
Handshake transcript -> HKDF traffic keys -> AEAD records
~~~

**Quan hệ độc lập không có nghĩa mọi tổ hợp đều chạy được**. Server phải có certificate/key tương thích với thuật toán chữ ký client chấp nhận, group và key share được hỗ trợ, cipher suite có overlap và chính sách/provider cho phép. TLS 1.3 cần certificate key phù hợp để phát ra CertificateVerify; tên suite **không thể tự giải quyết một certificate không hợp lệ**.

### 5.1. supported_groups và key_share không giống nhau

**supported_groups** là tập những nhóm key exchange client hỗ trợ; **key_share** là các giá trị public share được client thực sự gửi cho một số group.

Ví dụ client hỗ trợ **X25519 và secp256r1** nhưng chỉ gửi key_share cho X25519. Nếu server muốn dùng secp256r1 và hai bên tương thích, server có thể gửi **HelloRetryRequest** yêu cầu client gửi một key_share phù hợp. HelloRetryRequest là một nhánh handshake có bảo vệ ràng buộc transcript; không phải mặc nhiên là lỗi hay một yêu cầu “cho phép downgrade”.

Nếu không có group phù hợp cho kết nối yêu cầu (EC)DHE, handshake thất bại. Tuy nhiên, **PSK-only** mode của TLS 1.3 có logic khác: nó có thể không sử dụng (EC)DHE nên không nhất thiết đòi overlap supported_groups. Không suy ra có PFS chỉ từ cipher suite.

### 5.2. signature_algorithms và certificate trong TLS 1.3

Một server có thể dùng:

- **RSA public key** với một profile **RSA-PSS** được hỗ trợ để ký CertificateVerify.
- **ECDSA P-256 public key** với signature scheme tương thích.
- **Ed25519** với signature scheme tương ứng, nếu cả hai JSSE/provider và policy tin cậy hỗ trợ.

Cùng với các profile này, kết nối vẫn có thể thương lượng **TLS_AES_128_GCM_SHA256** cho record. Đây là thay đổi đáng nhớ so với TLS 1.2 **ECDHE_RSA** vs **ECDHE_ECDSA** được phản ánh trong tên cipher suite.

**Lưu ý chi tiết:** signature scheme cho **CertificateVerify** và signature algorithm dùng để ký **chứng chỉ trong certificate chain** là hai câu chuyện có thể chịu extension/policy khác nhau. Trong TLS 1.3, tên cipher suite không quyết định cả hai; không kết luận “SHA256 trong tên suite nghĩa là certificate phải ký SHA-256”.

### 5.3. Các sơ đồ TLS 1.3 1-RTT với certificate

~~~text
Client                                            Server
  |                                                 |
  | ClientHello + supported_versions + suites       |
  | + supported_groups + key_share + signature_algs  |
  |------------------------------------------------>|
  |                                                 |
  |            ServerHello + selected suite/key_share|
  |            {EncryptedExtensions}                |
  |            {Certificate}                        |
  |            {CertificateVerify}                  |
  |            {Finished}                           |
  |<------------------------------------------------|
  | {Finished}                                      |
  |------------------------------------------------>|
  |        [Protected application data]             |
~~~

Trong sơ đồ RFC 8446, ngoặc **{ }** biểu thị các handshake message được bảo vệ bằng **handshake traffic keys**; **[ ]** biểu thị application data bảo vệ bằng **application traffic keys**. Hình trên giản lược tùy chọn client authentication, resumption/PSK, HelloRetryRequest và các trường khác.

TLS 1.3 đưa nhiều handshake message vào vùng mã hóa sớm hơn TLS 1.2, có **HKDF-based key schedule** và bảo vệ record bằng AEAD. **ChangeCipherSpec** có thể xuất hiện ở compatibility mode nhưng không được diễn giải giống transition state trong TLS 1.2.

### 5.4. 0-RTT/PSK là ngoại lệ bảo mật cần nhìn riêng

TLS 1.3 cho phép **PSK resumption**, có thể kết hợp DHE hoặc không:

- **psk_dhe_ke:** sử dụng PSK và (EC)DHE; có thể mang tính forward secrecy cho traffic phù hợp khi triển khai đúng.
- **psk_ke:** chỉ dùng PSK, **không có forward secrecy** do thiếu ephemeral DHE.
- **0-RTT early data:** gửi dữ liệu khi handshake chưa hoàn tất, bảo vệ dựa trên PSK; **không có bảo đảm anti-replay xuyên kết nối** như 1-RTT thông thường và early-data key không có full forward secrecy.

Do đó, câu nói **“TLS 1.3 luôn có PFS”** là quá đơn giản. Với các thiết kế API có thể thay đổi trạng thái như chuyển tiền, tạo đơn, phát mã giảm giá, **không xử lý 0-RTT như request mới chắc chắn không bị lặp**. Khi sử dụng 0-RTT phải có cơ chế chống replay/idempotency và tuân thủ policy ứng dụng.

## 6. Bảng so sánh TLS 1.2 và TLS 1.3 theo thành phần thương lượng

| Hạng mục | TLS 1.2 | TLS 1.3 |
| --- | --- | --- |
| **Ý nghĩa cipher suite** | Thường nêu key exchange/authentication, record cipher, MAC/PRF | Chọn **AEAD + HKDF hash**; không đưa key exchange/certificate signature vào tên. |
| **Ví dụ suite** | TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256 | TLS_AES_128_GCM_SHA256 |
| **Version negotiation** | Trường phiên bản/extension theo TLS 1.2; không dùng quy tắc supported_versions TLS 1.3 | **supported_versions** extension xác định TLS 1.3; legacy_version có giá trị tương thích. |
| **Key establishment** | RSA transport, (EC)DHE hoặc các phương thức cũ theo suite | (EC)DHE, PSK+(EC)DHE, PSK-only theo profile/mode. |
| **Certificate/signature** | Có quan hệ chặt với phần RSA/ECDSA trong tên suite; signature_algorithms extension vẫn có vai trò | **signature_algorithms**, có thể signature_algorithms_cert; certificate/key được chọn riêng. |
| **Groups/key shares** | Supported curves/groups theo extension và thông điệp key exchange | **supported_groups** + **key_share**, HelloRetryRequest nếu cần share khác. |
| **Record protection** | Có CBC/HMAC và AEAD tùy suite | Theo RFC 8446 ban đầu là các suite **AEAD**; các RFC bổ sung cần đánh giá riêng. |
| **Key schedule** | TLS 1.2 PRF, master secret, key expansion | **HKDF** kết hợp handshake transcript và secrets theo giai đoạn. |
| **Forward secrecy** | Có với ECDHE/DHE phù hợp, không có với static RSA key transport | Có thể có với (EC)DHE; **PSK-only và 0-RTT** không có cùng bảo đảm. |
| **Handshake flow** | ServerHello, Certificate, ServerKeyExchange, ChangeCipherSpec, Finished theo profile | ServerHello, EncryptedExtensions, CertificateVerify, Finished; các phần mã hóa sớm. |
| **Renegotiation** | Có các cơ chế và rủi ro lịch sử; ứng dụng nên hạn chế/kiểm soát | **Không hỗ trợ renegotiation kiểu TLS 1.2**; có KeyUpdate và post-handshake authentication trong điều kiện thích hợp. |
| **ALPN/SNI** | Extension riêng, không nằm trong cipher suite | Vẫn là extension riêng, không nằm trong cipher suite. |
| **Resumption** | Thường session ID/ticket theo TLS 1.2 | PSK/ticket theo TLS 1.3; có thể 0-RTT nếu được phép. |

**Lưu ý về ngoại lệ:** TLS 1.3 RFC 8446 ban đầu định nghĩa bộ suite AEAD và hash; một số phần mở rộng sau này, ví dụ RFC 9150, định nghĩa integrity-only TLS 1.3 suites. Khi nói “TLS 1.3 dùng AEAD” trong HTTPS phổ thông, hiểu đó là profile bảo mật có mã hóa thông dụng; không khẳng định mọi suite đăng ký về sau đều mã hóa nội dung.

### 6.1. Cùng tên hash nhưng mục đích khác nhau

**TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256** (TLS 1.2):
- **SHA256** dùng trong TLS 1.2 PRF theo RFC 5289.
- **RSA** là cách xác thực certificate/handshake.
- **ECDHE** xác định key establishment.
- **GCM** đã đảm nhận authentication tag của record.

**TLS_AES_128_GCM_SHA256** (TLS 1.3):
- **SHA256** dùng trong HKDF/key schedule và transcript theo RFC 8446.
- Không nói certificate dùng RSA hay ECDSA.
- Không nói nhóm X25519 hay P-256.
- Vẫn dùng AES-128-GCM để bảo vệ record.

Cả hai đều có AES-128-GCM nhưng **không có khả năng hoán đổi cipher suite giữa hai phiên bản**.

## 7. ALPN, SNI, certificate và hostname: ngoài tên cipher suite

### 7.1. ALPN

**Application-Layer Protocol Negotiation (ALPN)** cho phép chọn giao thức ứng dụng qua TLS: ví dụ client quảng bá h2 và http/1.1, server chọn protocol phù hợp.

- ALPN **không phải TLS protocol version**: h2 không nghĩa TLS 1.2, http/1.1 không nghĩa TLS 1.3.
- ALPN **không phải cipher suite**: cùng TLS_AES_128_GCM_SHA256 có thể phục vụ các protocol ứng dụng được phép.
- Cấu hình ALPN phải tương thích policy ứng dụng: HTTP/2 có ràng buộc về các phiên bản/cipher suite theo chuẩn liên quan.
- Trong Java, **SSLParameters.setApplicationProtocols** cấu hình danh sách; sau handshake **SSLSocket.getApplicationProtocol** cho biết protocol đã thương lượng, nếu implementation hỗ trợ.

### 7.2. SNI

**Server Name Indication (SNI)** giúp server nhiều virtual hosts chọn certificate và cấu hình phù hợp. Không tự coi SNI là chứng minh hostname: client vẫn phải kiểm tra **certificate chain + hostname** theo endpoint identification/trust policy, nhất là raw SSLSocket/SSLEngine.

- SNI có thể ảnh hưởng certificate server chọn, từ đó ảnh hưởng signature schemes.
- Không suy rằng TLS 1.3 suite có chữ RSA nên certificate phải RSA: tên suite 1.3 không chỉ định RSA.
- Java HTTPS libraries thường có hostname verification mặc định; khi dùng raw SSLSocket cần xem xét **SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")** và trust manager đúng, không dùng TrustManager chấp nhận mọi certificate.

### 7.3. mTLS (mutual TLS)

TLS thường xác thực **server**; **client certificate** là tùy chọn theo chính sách. Trong Java, server có thể yêu cầu bằng **SSLServerSocket.setNeedClientAuth(true)** hoặc SSLParameters. mTLS bổ sung nhận diện client, nhưng vẫn cần authorization ở tầng ứng dụng: certificate hợp lệ chưa đồng nghĩa được phép gọi mọi API.

## 8. Java JSSE: các API liên quan đến cipher suite

Các class quan trọng của **javax.net.ssl**:

| API | Việc thực hiện | Lưu ý |
| --- | --- | --- |
| **SSLContext** | Cấu hình key managers, trust managers và nguồn ngẫu nhiên; tạo socket/engine | SSLContext("TLS") không đồng nghĩa buộc một version. |
| **SSLSocketFactory / SSLServerSocketFactory** | Tạo TLS client/server socket | Mỗi socket còn có enabled settings. |
| **SSLSocket / SSLServerSocket** | Lấy supported/enabled versions và suites, set policy | setEnabledCipherSuites phải dùng tên provider hỗ trợ; không vượt được algorithm constraints. |
| **SSLParameters** | Truyền cipher suites/protocols, ALPN, endpoint identification, client auth... | Các trường ảnh hưởng handshake độc lập. |
| **SSLSession** | Ghi nhận protocol và suite trên kết nối **đã thiết lập** | getProtocol/getCipherSuite chỉ là kết quả handshake, không phải toàn bộ security profile. |
| **SSLEngine** | TLS state machine không phụ thuộc blocking socket, cho async frameworks | Cũng có handshake status, supported/enabled và SSLSession. |
| **KeyManagerFactory** | Cung cấp private keys/certificates | Key/certificate ảnh hưởng signature scheme có thể chọn. |
| **TrustManagerFactory** | Định cấu hình kiểm tra certificate peer | Không thay bằng trust-all trong production. |

**Supported ≠ enabled ≠ negotiated** là bất biến khi quan sát JSSE. **SSLContext.getSupportedSSLParameters** có thể liệt kê protocol/suite nhiều hơn default. **setEnabledProtocols** hoặc **setEnabledCipherSuites** giới hạn danh sách thử, nhưng **không bảo đảm handshake thành công** nếu peer không có overlap hoặc bị chính sách bảo mật loại bỏ.

### 8.1. SSLContext.getInstance("TLS") có dùng phiên bản nào?

**"TLS"** là tên ngữ cảnh chung cho JSSE provider, có thể hỗ trợ nhiều phiên bản. Phiên bản thực tế do **enabled protocols**, supported protocols, JDK policy và peer negotiation quyết định. Sau **startHandshake**, đọc **SSLSession.getProtocol()**; không in SSLContext.getProtocol rồi coi đó là protocol phiên kết nối.

### 8.2. Có nên pin một cipher suite?

- **Lợi ích:** đáp ứng security policy, tái hiện test, loại bỏ suites yếu và kiểm soát compatibility.
- **Rủi ro:** client/server không có overlap, certificate sai loại, provider không hỗ trợ hoặc policy thay đổi sau JDK update.
- **Thực hành:** cấu hình **tập suite hiện đại được phê duyệt**, ưu tiên TLS 1.3; giữ TLS 1.2 ECDHE+AEAD khi cần tương thích. Tránh cứng hóa một suite đơn lẻ nếu không có yêu cầu rõ và kiểm thử đầy đủ.

Trong test integration có thể pin một suite để **chứng minh hai handshake khác nhau**, nhưng production thường cần policy linh hoạt cho client hợp lệ và lộ trình nâng cấp.

## 9. Java 17+: kiểm kê supported và enabled

Ví dụ đầu tiên không mở kết nối mạng, chỉ hỏi **SSLContext** trên JDK đang chạy về protocol và cipher suite. Đây là quan sát cấu hình, **không phải bằng chứng một kết nối sẽ chọn suite đó**.

Tạo file **TlsSuitesInspectDemo.java**:

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

public class TlsSuitesInspectDemo {
    private static boolean contains(String[] values, String wanted) {
        return Arrays.asList(values).contains(wanted);
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, new SecureRandom());

        SSLParameters supported = context.getSupportedSSLParameters();
        SSLParameters enabled = context.getDefaultSSLParameters();
        System.out.println("Provider: " + context.getProvider().getName());
        System.out.println("TLSv1.3 được hỗ trợ: " +
                contains(supported.getProtocols(), "TLSv1.3"));
        System.out.println("TLSv1.2 được hỗ trợ: " +
                contains(supported.getProtocols(), "TLSv1.2"));
        System.out.println("TLS 1.3 AES-GCM được hỗ trợ: " +
                contains(supported.getCipherSuites(), "TLS_AES_128_GCM_SHA256"));
        System.out.println("TLS 1.2 ECDHE-RSA được hỗ trợ: " +
                contains(supported.getCipherSuites(),
                        "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"));
        System.out.println("TLSv1.3 đang bật mặc định: " +
                contains(enabled.getProtocols(), "TLSv1.3"));
        System.out.println("TLSv1.2 đang bật mặc định: " +
                contains(enabled.getProtocols(), "TLSv1.2"));
    }
}
~~~

Chạy bằng **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 TlsSuitesInspectDemo.java
java TlsSuitesInspectDemo
~~~

Kết quả **trên JDK SunJSSE đã thử** (runtime khác có thể báo provider hoặc boolean khác):

~~~text
Provider: SunJSSE
TLSv1.3 được hỗ trợ: true
TLSv1.2 được hỗ trợ: true
TLS 1.3 AES-GCM được hỗ trợ: true
TLS 1.2 ECDHE-RSA được hỗ trợ: true
TLSv1.3 đang bật mặc định: true
TLSv1.2 đang bật mặc định: true
~~~

### 9.1. Giải thích

- **SSLContext.getInstance("TLS")** chọn provider và context hỗ trợ các phiên bản TLS theo implementation; không mở TCP.
- **init(null,null,new SecureRandom())** dùng key/trust managers theo provider defaults; ở ví dụ này không phát sinh kết nối.
- **getSupportedSSLParameters** mô tả khả năng được công bố; **getDefaultSSLParameters** là tập mặc định.
- Tên suite TLS 1.2 và TLS 1.3 cùng xuất hiện trong một API Java, nhưng chúng **chỉ dùng đúng phiên bản phù hợp khi handshake**.
- Kết quả true không chứng minh key của server đã cấu hình, certificate tin cậy, group phù hợp hay ALPN được thương lượng.
- Cấu hình **jdk.tls.disabledAlgorithms**, provider và security policy có thể đổi enabled/default qua từng môi trường. Không sao chép stdout làm tiêu chuẩn chung.

Để chứng minh một kết nối thực sự đã chọn suite nào, cần thực hiện **handshake** và đọc **SSLSession**, như ví dụ tiếp theo.

## 10. Java 17+: hai handshake thật cho TLS 1.2 và TLS 1.3

Ví dụ thứ hai chạy một TLS server **chỉ trên địa chỉ loopback 127.0.0.1**, rồi dùng client JSSE tạo handshake thật. Chương trình kiểm tra **SSLSession.getProtocol()**, **getCipherSuite()** và **getApplicationProtocol()** ở cả hai phía để cho thấy TLS 1.2 và TLS 1.3 đã thương lượng **hai cipher suite khác nhau**.

Để tránh dùng một TrustManager “tin mọi certificate” (thói quen cực kỳ nguy hiểm), bài test dùng một certificate **self-signed chỉ tạo cho localhost bằng keytool**, nạp chính keystore test làm trust anchors trong client context và bật **HTTPS endpoint identification**. Đây chỉ là một minh họa **trust cục bộ được cấu hình rõ**; production phải dùng truststore/PKI của tổ chức hoặc cơ chế tin cậy thích hợp, không copy certificate test này.

### 10.1. Tạo tệp PKCS12 test bằng keytool

Tại một thư mục làm bài tập có quyền ghi, dùng **JDK 17+ keytool**:

~~~bash
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 -validity 1 -storetype PKCS12 -keystore loopback.p12 -storepass local-demo-pass -keypass local-demo-pass -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1" -noprompt
~~~

Câu lệnh tạo một khóa RSA **chỉ để test** và certificate self-signed có Subject Alternative Name cho localhost. **local-demo-pass chỉ là password công khai của bài tập**, không được dùng trong ứng dụng thật. Certificate có validity một ngày để giảm nguy cơ vô tình coi nó là tài sản lâu dài. Nếu file loopback.p12 đã tồn tại, làm việc trong một thư mục test mới thay vì ghi đè dữ liệu có giá trị.

### 10.2. Tạo file TlsNegotiationDemo.java

~~~java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class TlsNegotiationDemo {
    private static final String ALPN = "demo/1";

    private static SSLContext[] contexts(Path file, char[] password)
            throws Exception {
        KeyStore keys = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(file)) {
            keys.load(input, password);
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, password);
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(keys);

        SSLContext server = SSLContext.getInstance("TLS");
        server.init(kmf.getKeyManagers(), null, new SecureRandom());
        SSLContext client = SSLContext.getInstance("TLS");
        client.init(null, tmf.getTrustManagers(), new SecureRandom());
        return new SSLContext[] {server, client};
    }

    private static String runOne(SSLContext serverContext,
            SSLContext clientContext, String protocol, String suite)
            throws Exception {
        InetAddress host = InetAddress.getByName("127.0.0.1");
        try (SSLServerSocket server = (SSLServerSocket)
                serverContext.getServerSocketFactory()
                        .createServerSocket(0, 8, host)) {
            server.setEnabledProtocols(new String[] {protocol});
            server.setEnabledCipherSuites(new String[] {suite});
            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                Future<String> serverResult = pool.submit(() -> {
                    try (SSLSocket peer = (SSLSocket) server.accept()) {
                        peer.setEnabledProtocols(new String[] {protocol});
                        peer.setEnabledCipherSuites(new String[] {suite});
                        SSLParameters p = peer.getSSLParameters();
                        p.setApplicationProtocols(new String[] {ALPN});
                        peer.setSSLParameters(p);
                        peer.startHandshake();
                        SSLSession session = peer.getSession();
                        return session.getProtocol() + "|"
                                + session.getCipherSuite() + "|"
                                + peer.getApplicationProtocol();
                    }
                });

                try (Socket tcp = new Socket(host, server.getLocalPort());
                     SSLSocket client = (SSLSocket)
                             clientContext.getSocketFactory().createSocket(
                                     tcp, "localhost", server.getLocalPort(), true)) {
                    client.setEnabledProtocols(new String[] {protocol});
                    client.setEnabledCipherSuites(new String[] {suite});
                    SSLParameters p = client.getSSLParameters();
                    p.setEndpointIdentificationAlgorithm("HTTPS");
                    p.setApplicationProtocols(new String[] {ALPN});
                    client.setSSLParameters(p);
                    client.startHandshake();
                    SSLSession session = client.getSession();
                    String clientState = session.getProtocol() + "|"
                            + session.getCipherSuite() + "|"
                            + client.getApplicationProtocol();
                    if (!clientState.equals(serverResult.get())) {
                        throw new IllegalStateException("TLS peers disagree");
                    }
                    return session.getProtocol() + " / "
                            + session.getCipherSuite() + " / ALPN="
                            + client.getApplicationProtocol();
                }
            } finally {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: keystore.p12 password");
        }
        char[] password = args[1].toCharArray();
        try {
            SSLContext[] both = contexts(Path.of(args[0]), password);
            System.out.println(runOne(both[0], both[1], "TLSv1.3",
                    "TLS_AES_128_GCM_SHA256"));
            System.out.println(runOne(both[0], both[1], "TLSv1.2",
                    "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"));
        } finally {
            java.util.Arrays.fill(password, '\0');
        }
    }
}
~~~

### 10.3. Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 TlsNegotiationDemo.java
java TlsNegotiationDemo loopback.p12 local-demo-pass
~~~

Với SunJSSE trên JDK 17 đã kiểm thử, chương trình in:

~~~text
TLSv1.3 / TLS_AES_128_GCM_SHA256 / ALPN=demo/1
TLSv1.2 / TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256 / ALPN=demo/1
~~~

**Quan sát chính:** cả hai handshake dùng **cùng certificate test RSA**, cùng lựa chọn ALPN demo/1 và có thể cùng AES-128-GCM ở tầng record. Nhưng tên suite **khác vì semantics khác giữa TLS 1.2 và TLS 1.3**. Ở TLS 1.2 tên suite nói rõ **ECDHE_RSA**; ở TLS 1.3 tên **TLS_AES_128_GCM_SHA256** không nói certificate RSA hay key exchange group.

### 10.4. Giải thích lifecycle của demo

1. **KeyStore PKCS12** được tạo từ keytool, có private key/certificate dùng cho server và trust anchor test cho client.
2. **KeyManagerFactory** đưa certificate/private key cho server SSLContext. **TrustManagerFactory** tạo trust manager chỉ chấp nhận những anchor trong keystore test, không vô hiệu xác minh.
3. ServerSocket chỉ bind **127.0.0.1** với random free port, không mở service ra Internet.
4. Trong mỗi lần **runOne**, phía server/client cùng bật một protocol và một suite đúng loại; đây là **bài test deterministic về lựa chọn**, không phải một production policy có đầy đủ fallback.
5. **SSLSocket.startHandshake()** hoàn tất TLS handshake. Sau đó **SSLSession.getProtocol**, **getCipherSuite** và **getApplicationProtocol** cho biết kết quả thực tế.
6. **SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")** buộc client kiểm tra hostname localhost so với certificate được tin cậy; dùng Socket TLS bọc TCP đã kết nối để peer host phục vụ hostname check là localhost.
7. **serverResult.get()** so sánh quan sát cả hai phía sau handshake. Không dùng handshake thành công như bằng chứng certificate public CA hợp lệ; trust được giới hạn trong file test.
8. **ExecutorService** chạy server accept ở một thread, client trong thread khác để tạo handshake loopback; session socket được đóng bằng try-with-resources.
9. **char[] password** tạm được xóa trong finally; tuy nhiên password ban đầu truyền qua **String args[1]**, nên chương trình minh họa không đạt chuẩn secret-handling production.

**Đừng dùng password test làm mật khẩu kho thật**, đừng đưa password production lên command line (có thể lộ trong process listing), và xóa/kiểm soát file test sau bài thực hành. Lấy secret từ môi trường bảo mật phù hợp như secret manager/callback khi làm ứng dụng thật.

### 10.5. Nếu demo không chạy trên máy khác

Nếu JDK/provider không hỗ trợ một protocol/suite, certificate không đúng, disabled algorithm chặn RSA key size, truststore không khớp, keytool không có trên PATH hoặc policy local không cho bind socket thì có thể nhận **SSLHandshakeException**, **NoSuchAlgorithmException**, **IllegalArgumentException** hoặc lỗi I/O phù hợp. Không tự giảm xuống TLS 1.0/1.1 hay bỏ certificate verification để “cho chạy”.

Dùng chương trình phần 9 để kiểm tra supported/default, sau đó xem chính sách **jdk.tls.disabledAlgorithms**, cấu hình provider, key material và certificate SAN. Nếu muốn bắt thêm trường hợp thương lượng TLS 1.3 với certificate ECDSA, cần tạo certificate EC test và cấu hình trust tương ứng; **tên suite TLS 1.3 có thể vẫn là TLS_AES_128_GCM_SHA256** khi profile/keys phù hợp.

## 11. Chọn cipher suite theo yêu cầu bảo mật và tương thích

Việc chọn suite cần dựa trên **phiên bản TLS + key management + security policy + loại client/server được hỗ trợ**; không chỉ dựa trên con số AES 128/256.

### 11.1. Khuyến nghị kiến trúc thực tế

1. **Ưu tiên TLS 1.3** khi tất cả các bên triển khai và đã kiểm thử; bộ suites phổ biến như AES-GCM hoặc ChaCha20-Poly1305 nên do security policy/provider xác định.
2. **Giữ TLS 1.2 khi có nhu cầu tương thích** với client được hỗ trợ, ưu tiên **ECDHE + AEAD** như TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256 hoặc ECDHE_ECDSA tương ứng certificate.
3. **Không bật lại TLS 1.0/1.1** hoặc RC4, 3DES, anonymous cipher suites chỉ để kết nối một client không được hỗ trợ; nâng cấp peer hoặc đưa ra lộ trình migration.
4. **Không dùng RSA key transport** khi thiết kế mới. Trong TLS 1.2, chọn ECDHE_RSA không đồng nghĩa đang dùng TLS_RSA; ECDHE tạo forward secrecy phù hợp.
5. **Cấu hình certificate và signature algorithms** tương thích với thực tế: RSA/ECDSA/EdDSA, certificate chain và trust manager; TLS 1.3 suite name không chọn hộ certificate.
6. **Không bật 0-RTT mặc định cho API có side effects** nếu không có chính sách replay/idempotency và đánh giá rủi ro.
7. **Không lạm dụng cipher-suite pinning**: cấu hình một tập được phê duyệt và kiểm thử với peer matrix, vì tập supported của nhà cung cấp có thể đổi khi nâng cấp JDK.
8. **Coi kết quả negotiated session là bằng chứng vận hành**, kết hợp certificate validation và authorization, không chỉ xem config.

### 11.2. Tại sao AES-256 không tự động tốt hơn toàn hệ thống?

**TLS_AES_256_GCM_SHA384** dùng AES-256-GCM và HKDF-SHA384; **TLS_AES_128_GCM_SHA256** dùng AES-128-GCM/HKDF-SHA256. Cả hai có mức bảo vệ mạnh trong profile TLS hiện đại. Một kết nối có AES-256 nhưng thiếu certificate validation, dùng PSK yếu, bị replay ở tầng nghiệp vụ hoặc lưu private key công khai **vẫn có thể không an toàn**.

Bên cạnh mức an toàn, cần xét hardware acceleration, latency, hỗ trợ client, policy chính thức và giới hạn provider. **Không được xếp hạng độ an toàn chỉ từ chuỗi cipher suite.**

## 12. Những lỗi thương lượng và cách chẩn đoán

| Triệu chứng | Kiểm tra trước tiên | Bẫy cần tránh |
| --- | --- | --- |
| **No appropriate protocol** | enabled versions, jdk.tls.disabledAlgorithms, peer versions | Không ép TLS 1.0 chỉ để loại bỏ lỗi. |
| **No cipher suites in common** | Suite enabled của hai phía, protocol tương ứng, type của certificate/key | Không cho rằng tên có AES-GCM là dùng được cho cả TLS 1.2/1.3. |
| **No available authentication scheme** | RSA/ECDSA/Ed25519 certificate, signature_algorithms, key managers | TLS 1.3 suite không nói loại certificate nên phải xem extension/key material. |
| **No appropriate key exchange group/share** | supported_groups, key_share, provider/curve policy, HelloRetryRequest | Đừng mặc định lỗi do record cipher. |
| **CertificateUnknown / PKIX path building failed** | trust anchors, certificate chain, hostname, validity và revocation policy | Không dùng trust-all TrustManager để vượt lỗi. |
| **ALPN negotiation error** | protocol ứng dụng hai bên cho phép, server preference, HTTP/2 policy | ALPN không phải cipher suite. |
| **Handshake thành công nhưng ứng dụng bị lỗi** | TLS session vs HTTP/2 policy, service authorization và protocol framing | Cipher suite đúng không chứng minh logic nghiệp vụ đúng. |
| **TLS 1.2 hoạt động, TLS 1.3 thất bại** | supported_versions, TLS 1.3 signature schemes/groups/certificates, provider support | Không so trực tiếp suite tên TLS 1.2 sang TLS 1.3. |
| **0-RTT request bị lặp** | early-data policy, replay/idempotency, state mutation | Không trông chờ signature/cipher suite tự chống replay tầng app. |

Trong Java, **SSLHandshakeException** mô tả lỗi chung; nguyên nhân gốc có thể là certificate, algorithm constraints, key exchange, ALPN, version hoặc IO. Ở môi trường kiểm thử, JSSE hỗ trợ **javax.net.debug** để quan sát handshake, ví dụ:

~~~bash
java -Djavax.net.debug=ssl,handshake TlsNegotiationDemo loopback.p12 local-demo-pass
~~~

Dòng trên chỉ minh họa cách bật log trên bài test. **Không chạy bằng mật khẩu production trên command line**, và không bật verbose handshake logs vô điều kiện trong production: log có thể chứa certificate metadata, hostnames và dữ liệu chẩn đoán nhạy cảm; phải giới hạn thời gian/đối tượng và bảo vệ log.

**Khi đọc log:**
- Xác nhận **client đã offer** TLS 1.3/TLS 1.2 và những cipher suite nào.
- Xác nhận **ServerHello chọn** suite phiên bản tương ứng.
- Với TLS 1.3, xem **supported_groups/key_share**, signature_algorithms/cert, PSK policy và ALPN **riêng**.
- Kiểm tra trust, hostname và certificate chain; khác biệt cipher suite chỉ là một phần của câu chuyện.
- Nếu peer bị downgrade hoặc không hỗ trợ TLS 1.3, kiểm tra cấu hình và policy; không chủ động tắt protections để vượt lỗi.

### 12.1. Downgrade protection và version negotiation

TLS 1.3 có **supported_versions** và cơ chế chống downgrade được đặc tả ở RFC 8446. Trường **legacy_version** và đôi khi các thông điệp compatibility **không nên được diễn giải thành việc TLS 1.2 đã được chọn** nếu supported_versions chỉ định TLS 1.3. Trong TLS 1.2 còn có các cơ chế liên quan fallback/renegotiation, ví dụ TLS_FALLBACK_SCSV; không dựa vào tự động fallback xuống phiên bản thấp để kết nối bằng mọi giá.

Lập cấu hình server/client theo **minimum TLS version được policy cho phép**, nâng cấp peer cũ thay vì giảm xuống giao thức không còn đạt yêu cầu. Không dùng packet capture hoặc các bytes legacy đơn lẻ để suy diễn version thành công; kết luận từ **handshake đã hoàn tất và SSLSession.getProtocol()**.

## 13. Bộ kiểm thử tương thích nên có

| Ca kiểm thử | Cấu hình | Kết quả mong đợi |
| --- | --- | --- |
| **TLS 1.3 happy path** | Hai phía bật TLSv1.3 + TLS_AES_128_GCM_SHA256, cert/trust hợp lệ | Handshake thành công, SSLSession trả TLSv1.3 và suite tương ứng. |
| **TLS 1.2 happy path** | Hai phía bật TLSv1.2 + ECDHE_RSA_WITH_AES_128_GCM_SHA256 | Handshake thành công với TLSv1.2 và suite tương ứng. |
| **Version mismatch** | Client chỉ TLSv1.3, server chỉ TLSv1.2 | Handshake thất bại; không âm thầm downgrade. |
| **Suite mismatch** | Không có overlap suite hợp lệ cho cùng protocol | Handshake thất bại. |
| **Certificate mismatch** | TLS 1.2 ECDHE_RSA nhưng server chỉ có ECDSA key không thể dùng RSA | Không chọn được profile đó, xử lý lỗi phù hợp. |
| **Wrong trust anchor** | Certificate self-signed không nằm trong client truststore | Từ chối; không bật trust-all. |
| **Hostname mismatch** | Certificate không có SAN của hostname được truy cập | Endpoint identification từ chối. |
| **TLS 1.3 group mismatch** | Không cùng nhóm DHE hợp lệ và không có PSK-only mode được phép | Handshake thất bại. |
| **Key share khác nhóm server thích** | Client hỗ trợ group nhưng chưa gửi share | HelloRetryRequest trong profile thích hợp hoặc failure có kiểm soát. |
| **ALPN mismatch** | Không có application protocol cùng hỗ trợ theo policy | Chọn protocol phù hợp hoặc thất bại; không suy ra cipher suite yếu. |
| **PSK-only** | TLS 1.3 cho phép psk_ke | Kiểm tra yêu cầu PFS và policy PSK riêng; không tuyên bố PFS dựa vào suite. |
| **0-RTT replay** | Gửi lại early-data request có side effect | Application phải có replay defense/idempotency hoặc từ chối 0-RTT. |
| **Provider upgrade** | Đổi JDK/security provider/HSM | Re-run supported/default/handshake tests theo suite được duyệt. |
| **Load/concurrency** | Nhiều kết nối đồng thời và chứng chỉ/ALPN khác nhau | Không trộn SSLSession, certificate/key usage, không vượt HSM capacity. |

Một test trong cùng JVM chỉ chứng minh **môi trường test**, không bảo đảm trình duyệt, mobile client, reverse proxy/CDN hoặc HSM production có cùng tập suite/extension. Cần **matrix có phiên bản JDK/client/proxy và nguồn key thực tế**.

## 14. Những hiểu lầm cần tránh

1. **TLS 1.3 cipher suite chứa loại certificate/key exchange như TLS 1.2.** Không: suite TLS 1.3 mô tả AEAD/HKDF hash.
2. **Tên có RSA nghĩa RSA key transport.** ECDHE_RSA dùng ephemeral ECDH và RSA authentication; khác TLS_RSA_.
3. **SHA256 trong tên GCM nghĩa record có HMAC-SHA256 độc lập.** Không: GCM đã có authentication tag; suffix trong TLS 1.2 GCM thường là PRF hash.
4. **TLS_AES_128_GCM_SHA256 dùng được nguyên tên trên TLS 1.2.** Sai phiên bản định nghĩa cipher suite.
5. **TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256 dùng nguyên tên trên TLS 1.3.** Tên này thuộc profile TLS 1.2.
6. **Supported nghĩa enabled và negotiated.** Supported chỉ là khả năng; cần kiểm tra cấu hình và SSLSession.
7. **Cứ setEnabledCipherSuites là server buộc chấp nhận.** Peer, certificate, group, signature và policy còn phải phù hợp.
8. **TLS 1.3 luôn có PFS trong mọi trường hợp.** PSK-only và 0-RTT có các giới hạn quan trọng.
9. **ALPN/SNI là phần của suite.** Chúng là extensions với mục đích khác.
10. **TLS 1.3 suite nói hash certificate signature là SHA256.** Cipher-suite hash dùng cho HKDF/transcript; handshake/certificate signatures được quy định riêng.
11. **Chỉ kiểm tra certificate chain là đủ.** Client còn cần hostname/identity, thời hạn, key usage, revocation policy và ứng dụng còn cần authorization.
12. **Bật TrustManager tin mọi cert để sửa handshake.** Việc này loại bỏ xác thực peer và tạo điều kiện MITM.
13. **Thấy legacy_version 0x0303 là kết luận TLS 1.2.** Trong TLS 1.3 đó có thể là giá trị tương thích; xem supported_versions và kết quả handshake.
14. **Bật TLSv1.2 là bắt buộc bật CBC/3DES.** Có thể cấu hình TLS 1.2 ECDHE+AEAD hiện đại mà không bật các suite yếu.
15. **Bật AES-256 tự giải quyết mọi rủi ro.** Còn key/cert trust, PSK, replay, implementation và application auth.
16. **Dùng một SSLSession.getCipherSuite để suy ra group, certificate type và ALPN.** Phải quan sát các thành phần khác riêng.
17. **Cho phép 0-RTT với API chuyển tiền mà không chống replay.** TLS không đảm bảo 0-RTT có anti-replay xuyên kết nối.
18. **Coi TLS encryption đồng nghĩa toàn bộ hệ thống đã an toàn.** TLS bảo vệ kênh, không thay kiểm soát người dùng và nghiệp vụ.

## 15. Câu hỏi tự kiểm tra

**1. TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256 có dùng RSA key transport không?**  
Không. **ECDHE** tạo shared secret qua ephemeral EC Diffie–Hellman; **RSA** dùng cho xác thực server/handshake theo suite.

**2. TLS_AES_128_GCM_SHA256 có chứng minh server dùng RSA certificate không?**  
Không. TLS 1.3 suite chỉ định **AES-128-GCM + SHA-256 HKDF/transcript**. Certificate/signature được chọn riêng.

**3. SHA256 trong TLS 1.2 AES-GCM suite có nghĩa mỗi record có HMAC-SHA256 không?**  
Không. Với suite GCM RFC 5289, SHA256 chỉ định **TLS PRF hash**; authentication tag đến từ AES-GCM.

**4. Java báo TLS_AES_128_GCM_SHA256 trong supported suites. Kết nối TLSv1.3 chắc chắn thành công không?**  
Không. Cần protocol enabled, overlap với peer, certificate/trust, group/key share, signature và policy tương thích.

**5. Tại sao TLS 1.3 có supported_groups và key_share riêng?**  
supported_groups công bố khả năng về nhóm key agreement; key_share chứa public shares đã gửi. Nếu thiếu key_share cho nhóm server muốn dùng, có thể có HelloRetryRequest.

**6. TLS 1.3 kết nối qua psk_ke có cùng PFS như ECDHE không?**  
Không. PSK-only không có ephemeral (EC)DHE; cần đánh giá khả năng forward secrecy theo mode thực tế.

**7. TLS 1.3 0-RTT có được tự do dùng cho giao dịch thanh toán không?**  
Không nên nếu thiếu replay protection và idempotency. Early data có rủi ro replay và bảo đảm bảo mật yếu hơn 1-RTT.

**8. Vì sao cần đọc SSLSession sau handshake?**  
Để biết **protocol và suite thực sự đã chọn**, khác danh sách supported/enabled ban đầu.

**9. ALPN h2 có phải một cipher suite hay một TLS version không?**  
Không. ALPN chọn protocol tầng ứng dụng, không phải suite/phiên bản TLS.

**10. TLS 1.2 với ECDHE_RSA và TLS 1.3 với AES_128_GCM_SHA256 có thể cùng dùng RSA certificate không?**  
Có, nếu server certificate và scheme ký đáp ứng profile/policy của cả hai; TLS 1.3 suite không ghi RSA trong tên.

## 16. Ghi nhớ và tài liệu chuẩn

**TLS 1.2:** cipher suite name thường thể hiện **key establishment/authentication + record cipher + MAC/PRF**, ví dụ **TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256**.  
**TLS 1.3:** cipher suite name chủ yếu thể hiện **AEAD + HKDF hash**, ví dụ **TLS_AES_128_GCM_SHA256**. **Group/key share, signature scheme/certificate, PSK mode và ALPN** được xử lý riêng, nên không thể đọc TLS 1.3 bằng cùng quy tắc tên TLS 1.2.

Trong Java 17+, **SSLContext và SSLParameters** dùng để khai báo chính sách; **SSLSocket/SSLEngine + SSLSession** giúp kiểm tra **kết quả thương lượng thực tế**. Cấu hình tốt cần bảo vệ **certificate validation, hostname, phiên bản cho phép, suite hiện đại, key exchange, replay và chính sách ứng dụng** cùng lúc.

Nguồn đọc chính thức:

- [RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246)
- [RFC 5289 — ECC Cipher Suites for TLS 1.2](https://www.rfc-editor.org/rfc/rfc5289)
- [RFC 5288 — AES-GCM Cipher Suites for TLS](https://www.rfc-editor.org/rfc/rfc5288)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 7301 — Application-Layer Protocol Negotiation](https://www.rfc-editor.org/rfc/rfc7301)
- [RFC 9150 — TLS 1.3 integrity-only cipher suites (ngoại lệ mở rộng)](https://www.rfc-editor.org/rfc/rfc9150)
- [Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Java SE 17 — SSLContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [Java SE 17 — SSLParameters API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [Java SE 17 — SSLSession API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html)
- [Java SE 17 — SSLSocket API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html)