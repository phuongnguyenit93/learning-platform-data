# Kiểm tra TLS và certificate endpoint: Xác minh danh tính, chuỗi tin cậy và cấu hình đường truyền

## 1. Vì sao một endpoint dùng HTTPS vẫn có thể không an toàn?

Một giao diện quản trị có biểu tượng ổ khóa chưa chắc đã đáp ứng yêu cầu bảo mật mạng. Certificate có thể **hết hạn**, được cấp cho **hostname khác**, thiếu intermediate CA, dùng **khóa/thuật toán không đạt chính sách**, hoặc được trình ra từ **proxy/CDN không đúng route**. Một server có thể đàm phán TLS 1.3 thành công ở IPv4 nhưng trả certificate sai trên IPv6; frontend bảo mật đúng trong khi backend hoặc đường quản trị nội bộ chấp nhận cấu hình yếu.

Trong chương **Kiểm thử và xác minh bảo mật mạng** thuộc module **SECURITY_NETWORK_SECURITY**, kiểm tra TLS/certificate không dừng ở thao tác xem ngày hết hạn. Đây là phép kiểm tra có hệ thống để trả lời:

1. **Đúng đích không?** Client thực sự kết nối đến endpoint/network path được phép, đúng DNS/IP, port và SNI?
2. **Đúng danh tính không?** Certificate server có khớp tên dịch vụ mong đợi theo quy tắc SAN?
3. **Đáng tin không?** Chuỗi chứng chỉ có dẫn tới trust anchor hợp lệ với ứng dụng, theo ràng buộc CA và policy?
4. **Còn hiệu lực không?** Thời hạn, ký số, key usages và revocation status theo chính sách có đạt?
5. **Kênh bảo vệ đúng không?** TLS version, negotiated cipher, authentication, ALPN và khả năng chống downgrade có phù hợp?
6. **Có nhìn đủ các lớp không?** CDN, load balancer, WAF, ingress, service mesh, API gateway, VPN hoặc mTLS có tạo các TLS segments riêng?
7. **Kiểm thử có gây hại không?** Chỉ thực hiện handshake/request giới hạn với tài sản thuộc quyền, không quét Internet hoặc làm quá tải production.

Trong thực tiễn, **TLS kiểm soát bảo mật kênh truyền** còn authorization, session management, data classification và endpoint hardening vẫn phải triển khai độc lập. Certificate đúng không chứng minh ứng dụng không có lỗ hổng, không chứng minh dữ liệu không bị lộ ở phía máy đã giải mã.

### Mục tiêu học tập

Sau khi học, người học có thể:

- Phân biệt HTTPS, TLS, X.509 certificate, certificate chain, CA/root trust, public/private key và TLS session keys.
- Kiểm chứng **subjectAltName (SAN), DNS name/IP address matching, SNI và hostname verification**.
- Kiểm tra **NotBefore/NotAfter, key usage, Extended Key Usage (EKU), Basic Constraints, signature algorithm**, path building và certificate policy.
- Phân tích handshake TLS 1.2/1.3, certificate authentication, ephemeral key exchange, cipher suite, ALPN, resumption và mTLS.
- Dùng **OpenSSL, curl, Java keytool, Wireshark/tshark** theo cách có kiểm soát và nhận diện giới hạn công cụ.
- Đánh giá **OCSP/CRL, OCSP stapling, Certificate Transparency (CT), certificate rotation** mà không nhầm có/không có dữ liệu với kết quả chắc chắn.
- Thiết kế **positive tests, negative tests, IPv4/IPv6, multi-SNI, backend/mTLS, failover và expiry monitoring**.
- Ghi evidence có nguồn, thời gian UTC, certificate fingerprint, chain và client trust context; viết report có thể kiểm chứng.

> **Quy tắc an toàn:** mọi tên như `api.lab.example.test`, `admin.lab.example.test`, `192.0.2.10` và `2001:db8::10` chỉ để minh họa. Những lệnh thiết lập kết nối thật bên dưới **chỉ chạy sau khi thay bằng endpoint thuộc quyền quản lý hoặc đã được phê duyệt**, với tần suất và cửa sổ kiểm thử được cho phép. Không bỏ TLS verification bằng `curl -k`, `--insecure` hoặc `verify=false` để biến bài test thành PASS. Không thu private keys, passwords, client tokens hoặc packet payload của người khác.

## 2. Mô hình kiểm thử: certificate validation không đồng nghĩa TCP port mở

Một phép thử `TCP connect` thành công chỉ cho biết có listener hoặc thành phần trung gian đã chấp nhận kết nối. Để xác minh HTTPS an toàn, client còn cần:

~~~mermaid
flowchart LR
    A["Client và trust store"] --> B["DNS / IP / route"]
    B --> C["TCP hoặc QUIC connect"]
    C --> D["TLS handshake và SNI"]
    D --> E["Certificate chain + hostname + policy"]
    E --> F["Authenticated encrypted channel"]
    F --> G["HTTP request và application authorization"]
    G --> H["Business outcome"]
~~~

| Kiểm tra | Kết luận có thể đưa ra | Không chứng minh |
|---|---|---|
| DNS A/AAAA | Tên được resolver trả về địa chỉ theo context | IP đó là endpoint hợp lệ hoặc TLS đúng |
| TCP/443 connect | Có kết nối transport tới host/port qua đường test | TLS handshake hoặc certificate validation đúng |
| TLS handshake | Client/server đã đàm phán protocol/keys theo flow đó | Hostname và CA trust đã được client xác minh, nếu công cụ chưa bật validation |
| Certificate hostname + chain | Peer certificate phù hợp với trust policy và tên đích | User có quyền ứng dụng hoặc backend sau proxy an toàn |
| ALPN `h2` / `http/1.1` | Application protocol được đàm phán trên phiên tương ứng | Request xử lý đúng hoặc HTTP/3 hoạt động |
| HTTPS request with verification | Client xác minh peer và nhận HTTP response | Business data đúng, không có bug trong application |
| Synthetic business transaction | Một chức năng thực sự hoàn thành từ vantage point được chọn | Mọi users/regions/protocols đều đạt |

**Mọi kết luận phải đi kèm “từ đâu, tới đâu, bằng client/trust store nào, khi nào”.** Browser trên Windows có thể tin root CA doanh nghiệp đã cài, nhưng container Java dùng truststore khác có thể báo `PKIX path building failed`. Không có một trust store “chung cho cả thế giới”.

## 3. Những thành phần của TLS endpoint

### 3.1. TLS khác HTTPS thế nào?

**TLS** là giao thức bảo vệ kênh truyền, xác thực peer khi chính sách và credential được kiểm tra đúng. **HTTPS** thông thường là HTTP chạy trên TLS; HTTP/3 chạy trên QUIC sử dụng TLS 1.3 với cơ chế packet protection riêng. Một dịch vụ có thể dùng TLS cho SMTP, LDAP, database, MQTT, gRPC hoặc protocol khác chứ không chỉ HTTP.

**Không suy `port=443` chắc chắn là HTTPS**: dịch vụ có thể dùng TCP/443/UDP/443 cho giao thức khác; một số HTTPS chạy trên port tùy chọn. Phải nhận diện protocol và **TLS termination point**.

### 3.2. Các khái niệm cốt lõi

| Thuật ngữ | Vai trò trong kiểm thử |
|---|---|
| **Leaf/end-entity certificate** | Xác nhận danh tính server/client cụ thể |
| **Subject Alternative Name (SAN)** | Chứa DNS names hoặc IP addresses dùng để match service identity |
| **Issuer / CA certificate** | CA ký certificate con trong chain; có thể là intermediate hoặc root |
| **Trust anchor/root CA** | Nguồn tin cậy do client/application quản lý; có thể không nằm trong handshake |
| **Public key** | Khóa công khai gắn với certificate; peer chứng minh quyền kiểm soát private key tương ứng |
| **Private key** | Bí mật server/client dùng cho xác thực/chữ ký; không được xuất vào report |
| **Traffic/session secrets** | Khóa bảo vệ TLS records cho phiên; khác private key chứng chỉ |
| **SNI** | Hostname client gửi để server chọn virtual host/certificate; không thay hostname verification |
| **ALPN** | Extension đàm phán application protocol như `h2`, `http/1.1` |
| **mTLS** | Hai phía xác thực certificate theo chính sách; còn cần authorization theo identity |
| **OCSP/CRL** | Cơ chế kiểm tra trạng thái thu hồi certificate theo hệ thống tin cậy |
| **CT** | Public certificate transparency logs và các chính sách chứng minh/giám sát issuance |

### 3.3. Một certificate không tương đương một TLS session key

Certificate chứa **public key, names, issuer, usages, validity và extensions**. TLS 1.3 sử dụng ephemeral key agreement và key schedule tạo traffic secrets, do đó **private key của server certificate không tự giải mã được PCAP TLS 1.3 đã thu**. Trong TLS 1.2 ECDHE cũng có forward secrecy.

Điều này là **bảo vệ chủ động**, không phải lỗi. Không đổi server về TLS/RSA key exchange cũ hay thuật toán yếu chỉ để dễ packet inspection. Nếu cần quan sát nội dung cho điều tra có thẩm quyền, hãy thiết kế **application logs, proxy logs hoặc session key logging trong lab được kiểm soát**.

## 4. Handshake TLS 1.2 và TLS 1.3

### 4.1. Luồng TLS 1.3 đơn giản

~~~mermaid
sequenceDiagram
    participant C as TLS Client
    participant S as TLS Server
    C->>S: ClientHello + SNI + offered ALPN + key share
    S->>C: ServerHello + selected key share
    Note over C,S: Traffic secrets được thiết lập
    S-->>C: EncryptedExtensions + Certificate + CertificateVerify + Finished
    C-->>S: Finished (+ client certificate nếu mTLS yêu cầu)
    C->>S: Encrypted application data
    S->>C: Encrypted application data
~~~

Server chứng minh việc kiểm soát khóa riêng qua **CertificateVerify** trong TLS 1.3 certificate-based authentication; client dùng certificate chain, SAN, usages và trust policy để xác nhận đó là **đúng server**. Với TLS 1.2, quy trình khác ở các cipher suite/handshake messages; không mặc định mọi certificate đều hiển thị plaintext trong TLS 1.3 PCAP.

### 4.2. TLS 1.2, 1.3 và các phiên bản cũ

- **TLS 1.3**: giao thức hiện đại với key schedule, AEAD suites và cải tiến handshake; đòi hỏi endpoint/server/client hỗ trợ phù hợp.
- **TLS 1.2**: có thể chấp nhận trong một số môi trường khi dùng cấu hình mạnh và chính sách tương thích; phải kiểm tra **cipher suite/key exchange thực**, tránh suy mọi TLS 1.2 đều yếu.
- **TLS 1.0/1.1 và SSLv2/SSLv3**: đã lỗi thời/không nên được kích hoạt trong cấu hình Internet hiện đại; nếu môi trường legacy cần ngoại lệ, phải có phê duyệt, cô lập, kế hoạch thay thế và kiểm soát bù trừ.

**Không chỉ xem server quảng cáo hỗ trợ TLS 1.3:** phải kiểm tra **client thật đã đàm phán** phiên bản nào và có thể nối với endpoint hợp lệ hay không. Middlebox/proxy có thể tạo một TLS session khác giữa proxy và backend.

### 4.3. Key exchange, cipher và xác thực certificate

| Thành phần | Ví dụ cần xem | Chú ý |
|---|---|---|
| TLS version | 1.2/1.3 negotiated | Một phiên chỉ có một phiên bản được chọn |
| Cipher suite | AEAD algorithms như AES-GCM/ChaCha20-Poly1305 | TLS 1.3 suite names **không mã hóa thông tin key exchange** như nhiều tên TLS 1.2 |
| Key exchange group | X25519, P-256 hoặc nhóm được phê duyệt | Policy cần phù hợp khả năng của clients |
| Certificate public key | RSA/ECDSA/EdDSA tùy support và policy | Không đồng nghĩa TLS traffic encryption key |
| Signature algorithm | SHA-256/384-based hoặc algorithm hiện đại tương ứng | Xem yếu tố deprecated/legacy theo baseline |
| ALPN | `h2`, `http/1.1`, protocol khác | Chỉ là đàm phán application protocol, không thay HTTP test |

Không dùng “một cipher tên mạnh” để bỏ qua **hostname mismatch, untrusted root, expired certificate**. Ngược lại certificate hợp lệ không bù được khi service chỉ cho phép cấu hình transport yếu hoặc client không tuân thủ authorization.

## 5. X.509 certificate: đọc những trường nào?

### 5.1. Một certificate được mô tả qua gì?

~~~text
Version, serial number
Issuer Distinguished Name
Validity: Not Before / Not After
Subject Distinguished Name
SubjectPublicKeyInfo: algorithm, key size/curve
Extensions:
  subjectAltName (DNS / IP)
  basicConstraints
  keyUsage
  extendedKeyUsage
  subjectKeyIdentifier / authorityKeyIdentifier
  authorityInfoAccess (OCSP / CA issuers)
  cRLDistributionPoints
  certificatePolicies / nameConstraints (nếu áp dụng)
SignatureAlgorithm and SignatureValue
~~~

Certificate có thể là leaf, intermediate CA hoặc root; **vai trò quyết định cách đánh giá extensions**. Ví dụ CA có `basicConstraints CA:TRUE` và keyCertSign theo profile; leaf server thông thường không được cấp quyền ký certificate khác.

### 5.2. NotBefore và NotAfter

Certificate chỉ được xem là hợp lệ về thời gian trong **khoảng hiệu lực** theo clock của verifier:

\[
t_{\mathrm{NotBefore}} \leq t_{\mathrm{verification}} \leq t_{\mathrm{NotAfter}}
\]

Với cách diễn giải thực tế, expiry checks nên tính **giây UTC còn lại** và tạo cảnh báo trước hạn, xét timezone/clock skew và **kế hoạch triển khai certificate mới**. Chỉ thay certificate trên disk nhưng không reload/restart dịch vụ đúng cách có thể khiến server vẫn trình **certificate cũ**.

### 5.3. Leaf khác intermediate và root

Một server thường gửi **leaf + các intermediate certificates cần thiết**. Root CA thường đã nằm trong trust store của client và **không nhất thiết server phải gửi root**. Một số client có thể tự lấy intermediate từ AIA hoặc cache, trong khi client khác không có cơ chế đó; vì vậy **server gửi chain thiếu** có thể làm ứng dụng thất bại ngay cả khi một browser trên máy kỹ sư vẫn vào được.

### 5.4. Fingerprint, serial và issuer

**SHA-256 fingerprint** của certificate giúp định danh **đúng bytes của certificate** đang được trình bày. Nó hữu ích khi so endpoints/rollout và evidence. Tuy nhiên:

- Certificate được gia hạn sẽ có fingerprint khác dù dùng cùng private key hoặc SAN.
- Subject/issuer name không nhất thiết duy nhất, serial number có ngữ nghĩa theo issuer.
- **Không xác định trust chỉ bằng fingerprint** nếu client validation cần path, constraints và policy.
- Khi ghi report, giữ fingerprint/issuer/serial/NotAfter như metadata; **không thu server private key** để “xác minh”.

## 6. Hostname verification: SAN, wildcard, IP và IDN

### 6.1. Vì sao chỉ có chứng chỉ được ký bởi CA là chưa đủ?

Một CA có thể ký chứng chỉ cho `files.example.test`, nhưng client đang cần kết nối tới `api.example.test`. Nếu bỏ **hostname verification**, client có thể chấp nhận certificate hợp lệ của **dịch vụ khác**. Đây là một lỗi bảo mật nghiêm trọng, đặc biệt khi proxy/DNS bị cấu hình sai hoặc có tác nhân can thiệp trên mạng.

Xác minh TLS server identity phải so sánh **reference identity** (hostname mà ứng dụng định kết nối, sau chuẩn hóa thích hợp) với **presented identity** trong certificate, thường là SAN `dNSName`, theo quy tắc phù hợp như RFC 9525. Không lấy tên reverse DNS của IP, `Common Name (CN)` hoặc SNI nhìn thấy làm bằng chứng thay thế nếu SAN verification chưa đạt.

### 6.2. Ma trận SAN matching

| Certificate SAN | Client reference identity | Kỳ vọng |
|---|---|---|
| `DNS:api.example.test` | `api.example.test` | **MATCH** |
| `DNS:files.example.test` | `api.example.test` | **MISMATCH** |
| `DNS:*.example.test` | `api.example.test` | Thường **MATCH** trong phạm vi wildcard được phép |
| `DNS:*.example.test` | `a.b.example.test` | **MISMATCH**: wildcard không phủ nhiều nhãn |
| `DNS:*.example.test` | `example.test` | **MISMATCH**: không phủ apex |
| `DNS:api.example.test` | `api.other.test` | **MISMATCH** |
| `IP:192.0.2.10` | URL `https://192.0.2.10/` | **MATCH** nếu IP address SAN đúng và policy hỗ trợ |
| `DNS:192.0.2.10` | URL bằng IP literal `192.0.2.10` | Không thay thế `iPAddress` SAN theo chính sách modern client |
| `DNS:api.example.test` | URL bằng IP literal `192.0.2.10` | **MISMATCH** nếu không có IP SAN tương ứng |
| `DNS:api.example.test` | `API.EXAMPLE.TEST` | DNS name matching nhìn chung không phân biệt hoa/thường sau chuẩn hóa phù hợp |

`*.example.test` minh họa wildcard ở **nhãn trái nhất và chỉ một nhãn**; implementation/policy có thể hạn chế wildcard thêm nữa. Với internationalized domain names, client và certificate cần tuân thủ quy tắc **IDNA/A-label/Punycode** phù hợp; không tự so byte Unicode theo cách giản đơn. Các trường hợp public suffix hoặc ký tự quốc tế có thể chịu policy CA/browser đặc biệt.

### 6.3. IP SAN và IPv6

Khi client thực sự kết nối qua IP literal, reference identity là IP, không phải DNS name được đoán từ PTR. Trong X.509, IP SAN dùng loại `iPAddress`. Một service có cả IPv4 và IPv6 có thể tới **các địa chỉ, load balancers hoặc backends khác nhau**. Cần kiểm tra cả hai đường với **cùng hostname và SNI/validation intent**, thay vì gọi `https://IP` rồi tự kết luận hostname certificate sai.

### 6.4. CN fallback không nên là tiêu chuẩn thiết kế mới

Các hướng dẫn hostname validation hiện đại sử dụng **SAN** làm nguồn định danh. Không cấp certificate chỉ có `CN=api.example.test` rồi kỳ vọng mọi client hiện đại chấp nhận. Một số legacy runtime có hành vi khác; khi phát hiện, ghi **client/runtime version** và nâng chuẩn thay vì dựa vào fallback khó kiểm soát.

### 6.5. SNI khác hostname verification

**SNI** được client gửi trong ClientHello để server chọn virtual host/certificate; nó không chứng minh client đã xác minh cert. Ví dụ có thể có tình huống:

~~~text
TCP destination:    192.0.2.10:443
SNI supplied:       api.example.test
Certificate SAN:    DNS:wrong.example.test
Expected identity:  api.example.test
Result:             hostname validation FAIL
~~~

Ngay cả khi TLS handshake hoàn thành với công cụ không bắt lỗi, ứng dụng có **strict validation** phải từ chối certificate sai tên. Với TLS 1.3 có ECH, phần tên SNI bên trong có thể được bảo vệ; chỉ xem passive PCAP không thay cho validation từ client được phép.

## 7. Certificate chain: path building và trust anchor

### 7.1. Mô hình chuỗi

~~~mermaid
flowchart TD
    L["Leaf: api.example.test"] --> I["Intermediate CA"]
    I --> R["Root / trusted anchor trong client trust store"]
    L -. "Hostname, validity, EKU, keyUsage" .-> CHECK["Client path and identity validation"]
    I -. "CA:TRUE, path length, policy" .-> CHECK
    R -. "Explicit local trust decision" .-> CHECK
~~~

Kiểm tra chain không chỉ là so chuỗi `Issuer == Subject`. Path validation còn phải xác minh **digital signatures, CA basicConstraints, keyUsage, allowed algorithms, path length, name constraints, critical extensions và trust anchor** theo policy/client implementation.

### 7.2. Thiếu intermediate

Giả sử server gửi đúng leaf nhưng **không gửi intermediate**. Một browser có thể truy cập nhờ intermediate cache hoặc AIA retrieval, trong khi container Alpine/Java app hoặc embedded client báo lỗi. Lúc này:

1. Ghi leaf **fingerprint/SAN/issuer** từ kết nối.
2. Ghi danh sách certificates **server thực sự gửi**, không chỉ chuỗi do local store tự xây.
3. Xác định intermediate cần thiết có trong server handshake hay được client lấy từ nguồn khác.
4. Kiểm tra khả năng của **nhiều client trust stores** theo thiết kế.
5. Sửa **full chain bundle tại đúng TLS termination point** theo change control; không cài root CA tùy tiện lên client chỉ để làm lỗi biến mất.

### 7.3. Root CA tin cậy là quyết định của client

Với public HTTPS, browser/OS thường sử dụng public trust programs; với private PKI/mTLS, tổ chức có **custom trust anchors** và policy riêng. Một certificate private CA có thể **hoàn toàn hợp lệ trong mạng nội bộ** nhưng không được public browser tin. Ngược lại, một public CA chain được tin bởi browser không có nghĩa một Java truststore cũ chắc chắn chứa root liên quan.

**Đừng đưa một root tự ký lạ vào global trust store** để làm kiểm thử “PASS”; việc đó có thể mở rộng khả năng giả mạo nhiều host. Trong lab, cung cấp CA bundle rõ ràng cho **riêng phiên kiểm thử** hoặc ứng dụng được phê duyệt.

### 7.4. Cross-signing và alternate paths

Cùng một intermediate/public key có thể xuất hiện dưới nhiều đường chain/cross-sign khác nhau. Client khác version có thể xây **alternate certification paths**, dẫn đến kết quả khác nhau khi root bị ngừng tin, hết hạn hoặc policy thay đổi.

Ghi **chain mà server gửi** và **đường trust chain mà client sử dụng**, nếu công cụ hỗ trợ. Không suy từ một `Issuer` duy nhất rằng mọi thiết bị đều có cùng kết quả.

### 7.5. Name constraints và policy

Private CA có thể áp `nameConstraints` giới hạn DNS namespaces/IP ranges hoặc **certificatePolicies** cho mục đích chuyên biệt. Một chain có signatures đúng vẫn có thể bị client từ chối nếu vi phạm **critical name constraints**, path length hoặc application policy. Cần kiểm tra theo trust profile thực tế, không coi “self-signed” là lỗi duy nhất đáng quan tâm.

## 8. KeyUsage, ExtendedKeyUsage, BasicConstraints và thuật toán

### 8.1. Server certificate dùng để làm gì?

| Extension/thuộc tính | Ý nghĩa cần kiểm |
|---|---|
| `basicConstraints` | Leaf không có khả năng CA; intermediate CA hợp lệ có `CA:TRUE` khi cần |
| `keyUsage` | Các thao tác với public key được phép, ví dụ `digitalSignature` phù hợp TLS hiện đại |
| `extendedKeyUsage` | Certificate dùng cho TLS server theo profile, thường `serverAuth` |
| `subjectAltName` | DNS/IP identity so với client reference identity |
| `signatureAlgorithm` | CA certificate signature algorithm đáp ứng security policy |
| `SubjectPublicKeyInfo` | Thuật toán/kích cỡ/curve của public key đáp ứng baseline |
| `nameConstraints` | Chỉ các subtrees/identities phù hợp được CA cấp |
| `authorityInfoAccess` | URL chỉ CA issuers/OCSP theo chứng chỉ; không phải bằng chứng revocation đã được kiểm |

Các quy tắc cụ thể phải theo **RFC 5280, TLS version, client policy và trust program**. Ví dụ TLS 1.3 certificate authentication phụ thuộc khả năng **chữ ký số**; một leaf có usages chỉ dành cho key encipherment không thể được xem là hợp lệ cho mọi handshake.

### 8.2. Chữ ký certificate khác cipher suite của TLS

`sha256WithRSAEncryption` là kiểu ký certificate; `TLS_AES_128_GCM_SHA256` là TLS 1.3 cipher suite cho record protection. **Không lấy một field thay cho field kia** khi báo cáo “encryption strength”.

Một server có **RSA 3072-bit certificate**, nhưng đàm phán TLS 1.3 với một ephemeral key exchange group được hỗ trợ. Key dài hạn dùng xác thực, còn traffic secrets được thương lượng theo TLS protocol. Với ECDSA/EdDSA certificates, compatibility của clients và signature schemes cũng cần xem.

### 8.3. Không đặt cứng một ngưỡng cho mọi hệ thống

Security baseline phải dựa chuẩn/tài sản/rủi ro được phê duyệt: RSA minimum size, EC curves, SHA-1 deprecation, disallowed algorithms, legacy client requirements, FIPS profiles và crypto agility. Các thuật toán/cấu hình có thể thay đổi theo chuẩn và phiên bản. Trong báo cáo, ghi **algorithm, key size/curve, signature, client verification result và policy revision**, thay vì nói chung “mã hóa mạnh”.

### 8.4. Public key và private key phải đi đúng cặp

Nếu operator gắn **certificate mới** nhưng private key cũ không khớp, TLS server có thể không reload, handshake fail hoặc tiếp tục phục vụ old certificate. Kiểm tra qua **post-deployment handshake với hostname thật**, không yêu cầu người vận hành tải private key lên ticket. Bất kỳ kiểm tra key-pair tại server phải do chủ sở hữu hệ thống thực hiện trong quy trình được phép, tránh xuất secret ra bên ngoài.

## 9. Revocation: OCSP, CRL và stapling

### 9.1. Certificate còn hạn vẫn có thể bị thu hồi

Certificate có thể bị thu hồi trước `NotAfter` vì key compromise, issuance sai hoặc lý do quản trị. Trong X.509, **CRL** và **OCSP** là hai cách tra trạng thái thu hồi theo hệ PKI; cơ chế được client dùng và hành vi khi responder không sẵn sàng **khác nhau theo sản phẩm/policy**.

| Cơ chế | Vai trò | Giới hạn |
|---|---|---|
| **CRL** | CA công bố danh sách serial bị thu hồi | Cache/size/nextUpdate; không chắc client đã tải/kiểm tra |
| **OCSP** | Responder trả trạng thái certificate | Network/privacy/freshness/availability, có thể bị soft-fail |
| **OCSP stapling** | Server kèm OCSP response trong TLS handshake khi hỗ trợ | Không phải mọi server/client đều yêu cầu hoặc xử lý giống nhau |
| **Browser-specific revocation mechanisms** | Một số browser dùng CRLite/CRLSets hoặc chính sách riêng | Khác với phép thử bằng `openssl s_client -status` |
| **Short-lived certificates** | Giảm thời gian phơi nhiễm khi key bị lộ | Không thay thế key custody, rotation và client trust policy |

### 9.2. `No OCSP response sent` có nghĩa gì?

Khi dùng `openssl s_client -status`, output có thể báo **không được gửi stapled OCSP response**. Đó là quan sát về **stapling trong phiên thử**, không tự kết luận certificate bị thu hồi hoặc mọi browser phải thất bại. Phải xem client/browser policy, CA infrastructure và yêu cầu sản phẩm.

### 9.3. OCSP status tốt chưa chứng minh mọi thứ

Một OCSP response `good` (nếu đã kiểm tra chữ ký/timestamps đúng) chỉ hỗ trợ **không bị liệt kê revoked** theo responder ở thời điểm/semantics tương ứng; không chứng minh hostname đúng, chain đáng tin hoặc endpoint không bị xâm nhập.

Không tự tải hàng loạt CRL/OCSP endpoints khi không có thẩm quyền/tần suất phù hợp. Trong một số trường hợp, **OCSP responder không truy cập được** gây `unknown`/soft fail chứ không phải `revoked`. Báo cáo riêng trạng thái và client behavior.

## 10. Certificate Transparency và issuance monitoring

### 10.1. CT giải quyết câu hỏi nào?

**Certificate Transparency (CT)** tạo logs có thể kiểm toán việc phát hành public TLS certificates. Nó giúp phát hiện **certificate được cấp ngoài ý muốn** cho domain thuộc tổ chức hoặc hỗ trợ điều tra issuance anomalies. Các public browser/trust programs có thể có **yêu cầu SCT/CT** riêng.

CT **không thay thế** hostname/path verification hay revocation. Một certificate có mặt trong CT log không đồng nghĩa được cấp đúng quyền, không chứng minh client đang kết nối đúng endpoint; và private PKI thường không thuộc cùng nghĩa vụ công bố.

### 10.2. Issuance inventory và deployment inventory khác nhau

| Inventory | Mục đích |
|---|---|
| **Issued certificate inventory** | Có những cert nào được CA cấp cho domain, key/owner/expiry/CT status? |
| **Deployed certificate inventory** | Những cert thực sự được **serve** ở LB/CDN/ingress/API/region nào? |
| **Trusted CA inventory** | Những trust anchors nào có trên browser, OS, Java, container và IoT? |
| **Revoked/retired inventory** | Cert/key nào đã revoke, rollback hoặc ngừng dùng? |

Một wildcard cert được CA gia hạn nhưng load balancer vùng DR chưa cập nhật là một **deployment drift**, không phải lỗi issuance. Vì vậy cần **thử handshake từ mỗi vantage/route quan trọng** và đối chiếu fingerprint với desired state.

### 10.3. DNS CAA và ownership

DNS **CAA** có thể giới hạn CA được phép cấp certificate cho domain theo semantics và validation process của CA. Nó là **kiểm soát issuance policy**, không phải bước client thực thi khi TLS handshake. **DNSSEC, CAA, CT và certificate path validation** giải quyết các vấn đề khác nhau; không dùng một thứ thay cho thứ còn lại.

## 11. Chuẩn bị kiểm thử có kiểm soát

### 11.1. Scope và quyền

Trước khi thực hiện bất kỳ TLS probe nào, cần biết:

~~~yaml
# MẪU KẾ HOẠCH; chỉ dùng tên và IP lab/reserved.
assessment_id: TLS-LAB-008
owner: network-security-team
authorized_assets:
  - api.lab.example.test
  - admin.lab.example.test
allowed_ports: [443]
allowed_vantage_points:
  - managed-test-workstation
  - authorized-private-network-probe
expected_identity:
  hostname: api.lab.example.test
  certificate_trust: approved-test-ca
  tls_versions: [TLSv1.2, TLSv1.3]
rate_limit: one-controlled-check-per-test-case
evidence_destination: restricted-evidence-repository
credential_handling: never-export-private-keys-or-client-tokens
change_approval: pending-if-production
status: planned-not-executed
~~~

**Đây là ví dụ ý định, không phải cấu hình hay kết quả đã được áp dụng.** Không tự quét dải IP/cổng, thử hàng loạt tên ảo, bắn nhiều handshakes/s để “đo TLS load” trên production. Certificate transparency hoặc passive inventory có thể hỗ trợ xác định scope nhưng **không tự cấp quyền active scanning**.

### 11.2. Chọn client đáng tin và ghi version

Ghi:

- OS/architecture, version của **OpenSSL, curl, Java/JDK, browser hoặc platform TLS stack**.
- Trust store đang được sử dụng: system roots, application bundle, `cacerts` hay explicit `CAfile`.
- Thời điểm UTC, client clock/NTP và nơi xuất phát (Internet, VPN, VPC, Pod).
- DNS resolver/path và kết quả A/AAAA/route.
- SNI/reference hostname, IP/port thực tế, proxy settings, ALPN và network family.
- Các security policies: root trust, mTLS expected, TLS1.2 allowed, revocation hard/soft fail.

Không suy rằng hai công cụ có hành vi giống nhau: curl có thể dùng OpenSSL, Schannel, Secure Transport hoặc thư viện khác tùy bản build; Java JSSE có provider và truststore riêng.

### 11.3. Thứ tự test hạn chế rủi ro

~~~mermaid
flowchart TD
    A["Approved endpoint and client vantage"] --> B["DNS + routing + TCP/UDP connectivity"]
    B --> C["TLS with explicit SNI and strict validation"]
    C --> D["SAN, CA chain, expiry and key usages"]
    D --> E["Negotiated protocol, cipher and ALPN"]
    E --> F["HTTP/application verification"]
    F --> G["Negative cases, alternate routes and monitoring"]
    G --> H["Evidence/report and approved remediation"]
~~~

Nếu endpoint là hệ thống điều khiển/OT hoặc legacy appliance nhạy cảm với handshake, ưu tiên **config review, owner phối hợp và điều kiện vendor đã cho phép**; một lệnh tưởng chỉ đọc vẫn tạo kết nối thật.

## 12. OpenSSL: kiểm tra một TLS endpoint với xác minh nghiêm ngặt

### 12.1. Kiểm tra version công cụ

~~~bash
# Chạy trên máy lab/managed test workstation.
openssl version -a
~~~

Các tùy chọn `s_client`, `verify` và tên thuật toán có thể khác giữa OpenSSL 1.1.1, 3.x và các TLS libraries khác. **Không sao chép output của một máy thành bằng chứng cho mọi client**.

### 12.2. TLS handshake, SNI và hostname verification

~~~bash
# CHỈ chạy sau khi thay hostname bằng endpoint lab được phép.
# Một TCP/TLS connection thật; không sửa server configuration.
openssl s_client \
  -connect api.lab.example.test:443 \
  -servername api.lab.example.test \
  -verify_hostname api.lab.example.test \
  -verify_return_error \
  -showcerts \
  < /dev/null
~~~

Giải thích:

- `-connect` chọn TCP destination host/port.
- `-servername` gửi hostname SNI để chọn certificate đúng virtual host.
- `-verify_hostname` yêu cầu xác minh tên server theo reference identity.
- `-verify_return_error` làm kiểm thử dừng khi gặp lỗi certificate verification; không nhầm handshake thành công với PKI thành công.
- `-showcerts` in certificate chain **server đã gửi**, không bảo đảm là chain client đã dùng để xây trust path.
- Chuyển input từ `/dev/null` giúp tránh nhập dữ liệu tương tác vô ý; bản thân command vẫn **tạo kết nối**.

**Chỉ thấy `Verify return code: 0 (ok)` khi không cấu hình hostname verification không đủ chứng minh hostname match.** Phải ghi chính xác command/options, trust anchor/CAfile, thời điểm và output verification. Certificate validation có thể sử dụng OpenSSL default trust store khác browser/Java.

### 12.3. Yêu cầu TLS 1.3

~~~bash
# Chỉ một handshake tới endpoint lab.
openssl s_client \
  -connect api.lab.example.test:443 \
  -servername api.lab.example.test \
  -verify_hostname api.lab.example.test \
  -verify_return_error \
  -tls1_3 \
  -brief \
  < /dev/null
~~~

`-tls1_3` **giới hạn phép thử** vào TLS 1.3. Nếu thất bại, nguyên nhân có thể là server không hỗ trợ, policy, middlebox, thiếu cipher/signature compatibility hoặc lỗi CA/hostname; cần xem loại lỗi thay vì suy ngay “TLS 1.3 bị tắt”.

### 12.4. Đánh giá TLS 1.2 theo policy

~~~bash
openssl s_client \
  -connect api.lab.example.test:443 \
  -servername api.lab.example.test \
  -verify_hostname api.lab.example.test \
  -verify_return_error \
  -tls1_2 \
  -brief \
  < /dev/null
~~~

Nếu baseline chấp nhận TLS 1.2 với cấu hình đúng, handshake PASS có thể phù hợp. Nếu baseline yêu cầu TLS 1.3-only, **TLS 1.2 handshake thành công là sai chính sách** dù bản thân certificate đúng. Không ép bật SSLv3/TLS1.0 trên server để test; đánh giá protocol legacy có thể dùng **config read-only/inventory** hoặc controlled negative test do owner phê duyệt, không tạo nhiều probes.

### 12.5. ALPN và HTTP/2

~~~bash
openssl s_client \
  -connect api.lab.example.test:443 \
  -servername api.lab.example.test \
  -verify_hostname api.lab.example.test \
  -verify_return_error \
  -alpn "h2,http/1.1" \
  -brief \
  < /dev/null
~~~

ALPN output cho biết protocol được chọn cho phiên TLS/TCP. **HTTP/3 qua QUIC không được kiểm thử bằng cách chỉ đặt `-alpn h3` cho một kết nối TCP.** Cần client có QUIC/HTTP3 support, UDP path và test protocol phù hợp.

### 12.6. OCSP stapling

~~~bash
openssl s_client \
  -connect api.lab.example.test:443 \
  -servername api.lab.example.test \
  -verify_hostname api.lab.example.test \
  -verify_return_error \
  -status \
  < /dev/null
~~~

`-status` yêu cầu xem stapled OCSP response **nếu server cung cấp**. Không thấy staple là tình huống cần đánh giá theo policy, **không tự kết luận revoked**. Khi có response, cần đánh giá chữ ký/issuer/freshness và hành vi revocation checking của client thực.

## 13. OpenSSL: kiểm tra certificate file và CA chain ngoại tuyến

### 13.1. Đọc leaf certificate không dùng private key

Giả sử đội vận hành đã cung cấp file **public leaf certificate** `leaf-lab.pem` được phép sử dụng:

~~~bash
# Không cần network access, không ghi đè file.
openssl x509 -in leaf-lab.pem -noout -subject -issuer -serial -dates
openssl x509 -in leaf-lab.pem -noout -fingerprint -sha256
openssl x509 -in leaf-lab.pem -noout -ext subjectAltName
openssl x509 -in leaf-lab.pem -noout -text
~~~

`-text` hỗ trợ xem key usages, EKU, basic constraints, AIA, CRL distribution points và public key/signature algorithm. `openssl x509` là **parser của một certificate file**, không tự chứng minh file đó chính là certificate endpoint đang phục vụ hôm nay. Đối chiếu SHA-256 fingerprint với certificate **thu từ endpoint** trong cùng kiểm thử.

### 13.2. Kiểm tra hạn còn lại

~~~bash
# 2592000 giây = 30 ngày; exit 0 nếu còn hợp lệ vượt ngưỡng.
openssl x509 -in leaf-lab.pem -noout -checkend 2592000
~~~

Kết quả `Certificate will expire` hoặc exit code không đạt là dấu hiệu thời hạn còn lại **không vượt ngưỡng test**. Nó không có nghĩa certificate đã hết hạn ngay tại thời điểm đó. Ghi `NotAfter`, timestamp UTC và cả **certificate rotation plan**.

### 13.3. Xác minh với CA bundle được phê duyệt

~~~bash
# File roots/intermediates do chủ hệ thống lab cung cấp.
# Không nhập private key vào các lệnh này.
openssl verify \
  -purpose sslserver \
  -verify_hostname api.lab.example.test \
  -CAfile trusted-root-lab.pem \
  -untrusted intermediates-lab.pem \
  leaf-lab.pem
~~~

`-CAfile` cung cấp trust anchors được lựa chọn cho phép thử; `-untrusted` cung cấp intermediate certificates để **xây path**, không tự biến chúng thành trusted roots. `-purpose sslserver` yêu cầu mục đích TLS server theo semantics của OpenSSL. Với private PKI, **không cài trust anchor globally để che lỗi**; cung cấp chính xác root CA theo test profile.

### 13.4. Certificate file và server đang trình có thể khác nhau

Một deploy pipeline có thể đặt `leaf-new.pem` trên disk nhưng proxy process chưa reload, secret volume chưa update, hoặc một vùng load balancer còn dùng cert cũ. Vì vậy cần:

1. Xem cert file tại source of truth với fingerprint/hash.
2. Xem cert đang được **serve** bằng SNI từ từng endpoint/vantage.
3. So fingerprint, NotAfter, SAN, issuer và chain; ghi UTC.
4. Xác nhận LB/CDN/ingress secret mapping và rollout revision.
5. Test **failover/DR/alternate hostnames** chứ không chỉ một instance.

## 14. curl: xác minh TLS và kết quả HTTPS từ góc nhìn client

### 14.1. Client request có hostname validation

~~~bash
# CHỈ chạy trên endpoint HTTPS lab được phê duyệt.
# Một HTTP GET, có giới hạn connect/total timeout, xác minh TLS mặc định.
curl --silent --show-error \
  --output /dev/null \
  --connect-timeout 5 \
  --max-time 12 \
  --write-out 'http=%{http_code} verify=%{ssl_verify_result} remote=%{remote_ip} tls_total=%{time_appconnect}s total=%{time_total}s\n' \
  https://api.lab.example.test/health
~~~

Mặc định curl thường **xác minh certificate chain và hostname**, nhưng trust backend/bundle còn phụ thuộc bản build/cấu hình. `ssl_verify_result=0` cần được diễn giải cùng **curl exit status, backend, SNI/hostname, HTTP response và test source**; không coi mã `0` độc lập là bằng chứng mọi bước đều đúng.

`time_appconnect` là mốc elapsed time tới khi hoàn thành handshake theo libcurl, **không nhất thiết là thời gian TLS riêng lẻ**; khi có proxy/connection reuse/protocol khác, cần đọc đúng measurement semantics.

### 14.2. Private CA cho đúng một phép thử

~~~bash
# Root CA public certificate của lab được phép, không phải private key.
curl --silent --show-error \
  --cacert trusted-root-lab.pem \
  --connect-timeout 5 \
  --max-time 12 \
  --output /dev/null \
  https://api.lab.example.test/health
~~~

Việc dùng `--cacert` để chỉ định **CA đúng của môi trường riêng** khác căn bản với `-k/--insecure`. Đừng lấy một `trusted-root-lab.pem` không rõ nguồn rồi tin tất cả server ký bởi nó; phải quản lý certificate/trust anchor origin theo policy.

### 14.3. Kiểm tra đúng IP nhưng vẫn giữ hostname/SNI

~~~bash
# Chỉ dùng IP lab đã phê duyệt: giữ URL hostname cho TLS verification.
curl --silent --show-error \
  --resolve api.lab.example.test:443:192.0.2.10 \
  --connect-timeout 5 \
  --max-time 12 \
  --output /dev/null \
  https://api.lab.example.test/health
~~~

`--resolve` gán kết quả name resolution cho một host:port **cụ thể của phép thử**, hữu ích khi kiểm tra ingress/LB cụ thể trong rollout. TLS SNI và reference hostname vẫn dựa trên tên trong URL. Nếu dùng `https://192.0.2.10/` thay vì hostname, client có thể đòi **IP SAN**, đây là **test khác**.

Trong môi trường dùng HTTP proxy, VPN, DNS override hay connection reuse, `--resolve` có thể không kiểm soát được đoạn đến server cuối như người đọc tưởng; cần xác định **route thực tế** và client proxy settings.

### 14.4. IPv4 và IPv6

~~~bash
# Chỉ chạy nếu lab có cả A/AAAA và IPv4/IPv6 connectivity được phép.
curl -4 --silent --show-error --max-time 12 \
  --output /dev/null https://api.lab.example.test/health

curl -6 --silent --show-error --max-time 12 \
  --output /dev/null https://api.lab.example.test/health
~~~

Một phép thử IPv6 fail có thể vì client không có IPv6 route, DNS thiếu AAAA, firewall chặn, server không listen hoặc certificate sai; phải tìm **failure stage**. Nếu service được thiết kế IPv4-only, IPv6 failure không tự là lỗi security SLO, nhưng vẫn cần xác nhận IPv6 không có **đường quản trị ngoài policy**.

### 14.5. Không dùng `-k` để sửa kết quả

Các ví dụ sau **không được dùng làm tiêu chí PASS bảo mật**:

~~~text
curl -k https://api.lab.example.test/
curl --insecure https://api.lab.example.test/
Application option: verify_tls = false
~~~

Những tùy chọn này bỏ qua một hoặc nhiều bước TLS certificate verification và **có thể làm request thành công qua server giả/misconfigured**. Nếu muốn nghiên cứu nguyên nhân trong lab, có thể phân tích certificate/error bằng các công cụ đã duyệt, nhưng kết quả **strict client validation** mới là chuẩn đo.

## 15. Java/JSSE: vì sao browser PASS còn ứng dụng Java FAIL?

### 15.1. Truststore và runtime khác nhau

Ứng dụng Java dùng JSSE/provider và trust material theo cấu hình. Trust có thể đến từ `cacerts`, một custom `javax.net.ssl.trustStore`, container image hoặc provider đặc biệt. Browser chạy trên hệ điều hành khác có thể sử dụng trust anchors khác, tự lấy intermediate, hoặc áp certificate policy khác.

**“Mở được bằng Chrome” không đủ chứng minh client Java sản xuất vào được.** Cần xác minh **đúng JDK/vendor/version, truststore, URL hostname, SNI và proxy** giống ứng dụng thật.

### 15.2. Xem certificate server bằng keytool

~~~bash
# Chỉ kết nối tới host lab được cấp phép; không tải private key.
keytool -printcert \
  -sslserver api.lab.example.test:443 \
  -rfc
~~~

`keytool -printcert -sslserver` hữu ích để **in certificate được endpoint trình bày** theo công cụ/JDK, nhưng **không thay thế end-to-end JSSE application handshake với hostname/path validation**. Nên đối chiếu với `openssl s_client` và một request thật bằng runtime/application.

### 15.3. Các lỗi Java thường gặp

| Lỗi/thông điệp | Giả thuyết cần kiểm |
|---|---|
| `PKIX path building failed` | Trust anchor/intermediate không tìm được, policy/path validation fail |
| `unable to find valid certification path` | Root CA không được tin, chain thiếu hoặc policy mismatch |
| `No subject alternative DNS name matching ... found` | SAN hostname mismatch |
| `CertificateExpiredException` | NotAfter đã qua theo clock client |
| `CertificateNotYetValidException` | Clock sai hoặc NotBefore ở tương lai |
| `handshake_failure` | TLS protocol/cipher/signature/client cert/SNI incompatibility |
| `bad_certificate` / `certificate_required` | mTLS client auth failure hoặc certificate không hợp lệ |
| `Received fatal alert: protocol_version` | Không có TLS version tương thích theo policy |

Tên lỗi chỉ là **gợi ý lớp vấn đề**, không chứng minh nguyên nhân cuối cùng. Xem complete exception chain, server/client audit và trust policy trước khi sửa. Đặc biệt, `handshake_failure` không đồng nghĩa certificate hết hạn.

### 15.4. Debug đúng mức

Java có TLS/JSSE debug options (chẳng hạn `javax.net.debug`) nhưng **có thể sinh log rất chi tiết về handshake, names, certs và security-sensitive context**. Chỉ bật ở lab/canary với retention/permissions được phê duyệt; không đưa toàn bộ debug output vào public ticket. Trong production, ưu tiên **structured error codes, certificate fingerprints, truststore revision và correlation IDs**.

### 15.5. Cách sửa có trách nhiệm

- Sửa server **full chain** trước khi tùy tiện thay truststore trên hàng nghìn clients.
- Nếu dùng private CA thật, triển khai **root/intermediate trust material được phê duyệt** theo lifecycle.
- Sửa SAN/hostname/URL chính xác; không tắt endpoint identification trong `HttpsURLConnection`, OkHttp hoặc custom TrustManager.
- Kiểm tra JDK crypto policy/provider không reject signature/cipher đã lỗi thời.
- Test lại bằng **runtime thật** sau thay đổi và so với negative certificate cases.

## 16. Mutual TLS: kiểm tra cả server và client certificate

### 16.1. Server-auth TLS và mTLS

Trong TLS server authentication thông thường, **client xác minh server certificate**; user/application authentication có thể diễn ra sau TLS qua OAuth, cookies hoặc cơ chế khác. Với **mutual TLS (mTLS)**, server cũng yêu cầu/xác minh **client certificate**, tạo ranh giới xác thực hai chiều. mTLS phổ biến trong API-to-API, service mesh, device fleets và network management.

~~~mermaid
sequenceDiagram
    participant C as Managed Client
    participant S as Protected Server
    C->>S: ClientHello (SNI/ALPN)
    S-->>C: Server certificate
    S-->>C: CertificateRequest (nếu yêu cầu client auth)
    C->>S: Client certificate + proof of private key
    Note over C,S: Mỗi bên xác thực peer theo chính sách riêng
    C->>S: Encrypted application request
    S->>C: Response / authorization decision
~~~

**mTLS chỉ xác minh danh tính cryptographic của client theo trust policy.** Nó không tự quyết định “service A được sửa IAM hay đọc database B”; cần **authorization** theo certificate identity/SPIFFE ID/role/resource/action và kiểm toán.

### 16.2. Những kiểm tra cần có ở mTLS

| Phía client kiểm tra server | Phía server kiểm tra client |
|---|---|
| Đúng hostname/SAN server, trust CA và hạn | Certificate client có chain dẫn tới CA cho phép |
| Server key usages/EKU phù hợp | Client certificate usage/EKU phù hợp, thường clientAuth |
| TLS protocol/cipher được phép | Client thực sự chứng minh sở hữu private key |
| Revocation/policy theo trust profile | Identity mapping/authorization/expiry/revocation theo policy |
| Server certificate rotation mượt | Client certificate rotation/revocation và session behavior |

**Không đánh đồng cùng một CA với cùng quyền**: nhiều client certificates được CA cấp có thể thuộc những principals khác nhau; authorize theo **service identity** chứ không chỉ “chain signed by org CA”.

### 16.3. Lab request có client certificate

~~~bash
# Chỉ trong lab được ủy quyền, với client cert/key do lab sở hữu.
# Không sao chép private key vào chat, ticket hoặc repo.
curl --silent --show-error \
  --cacert trusted-server-ca-lab.pem \
  --cert client-lab.pem \
  --key client-lab.key \
  --connect-timeout 5 \
  --max-time 12 \
  --output /dev/null \
  https://mtls.lab.example.test/health
~~~

Nếu client cert/key không hợp lệ hoặc không có quyền, server có thể từ chối ở TLS handshake hoặc trả **HTTP 401/403** sau khi handshake, tùy kiến trúc. Ghi rõ điểm thất bại. Không kết luận “mTLS bật” chỉ vì server có option `client_auth` trong file cấu hình; cần test **client có/không có certificate** tại đúng listener.

### 16.4. Negative tests cho mTLS

Trong môi trường lab:

1. **Không có client certificate:** request bị deny theo design nếu listener yêu cầu mTLS.
2. **Client certificate từ CA không tin:** bị từ chối đúng lớp.
3. **Client certificate hết hạn/not yet valid:** bị reject theo policy.
4. **Certificate đúng CA nhưng không được cấp role:** TLS có thể PASS, application authorization phải DENY.
5. **Client certificate hợp lệ đúng identity:** request hợp lệ ALLOW với logs gắn certificate identity.
6. **Revoked client credential:** behavior phù hợp revocation/session policy, cả **phiên đang mở** khi yêu cầu.

Không tạo/chia sẻ forged certificates cho production identities để thử lừa hệ thống. Có thể dùng **test CA và test identities** được tổ chức sở hữu; certificate rotation/CRL/OCSP behavior cần xem policy runtime.

### 16.5. Service mesh mTLS

Trong Kubernetes service mesh, sidecar/ambient proxy có thể xác thực **workload identity** cho Pod-to-Pod traffic. Một Pod có thể gửi HTTP plaintext tới local sidecar, sidecar dùng mTLS đến sidecar khác, rồi target service nhận plaintext hoặc tiếp tục TLS khác tùy kiến trúc.

Kiểm thử nên nêu:

- **Strict/permissive mTLS** mode và có fallback plaintext không?
- Identity được cấp bởi trust domain/CA nào, thời hạn/certificate rotation?
- Policy authorization có restrict đúng **source identity → destination/port/action**?
- CNI NetworkPolicy, gateway ingress/egress và hostNetwork có đi vòng mesh không?
- Metrics/audit có chứng minh **thực tế lưu lượng đi qua mTLS** hay chỉ nói policy được khai báo?

Một service mesh report “mTLS enabled” không chứng minh browser client tới public ingress có certificate đúng; đó là **TLS segment khác**.

## 17. Nhiều TLS segments: CDN, WAF, reverse proxy, ingress và backend

### 17.1. Mô hình thực tế

~~~mermaid
flowchart LR
    U["Browser / external client"] -->|"TLS A"| CDN["CDN / WAF"]
    CDN -->|"TLS B"| LB["Cloud load balancer"]
    LB -->|"TLS C"| ING["Ingress / API gateway"]
    ING -->|"mTLS D"| APP["Backend service"]
    U -. "Client validates CDN cert" .-> CDN
    CDN -. "CDN validates origin cert per policy" .-> LB
    ING -. "Mesh identity and policy" .-> APP
~~~

Với mỗi segment, cần xác định:

| Segment | Client làm validation | Reference identity | Trust policy |
|---|---|---|---|
| A: Browser → CDN | Browser/OS | Public hostname | Browser/public CA program |
| B: CDN → origin/LB | CDN provider/origin connector | Origin hostname/SNI theo cấu hình | Public CA/private origin CA/pinning theo sản phẩm |
| C: LB → ingress | LB client stack | Internal service hostname | Managed CA/private trust bundle |
| D: Mesh → service | Workload proxy | Service/workload identity, có thể URI SAN | Mesh trust domain, identity & authorization policy |

**Một lần chạy OpenSSL từ laptop chỉ đánh giá segment A**, trừ khi bạn có đường truy cập đã được phê duyệt vào từng segment khác. Không khẳng định “end-to-end TLS” nếu giữa các segments tồn tại plaintext hop.

### 17.2. Origin không được validate là lỗ hổng ẩn

Một CDN có thể trình certificate public hoàn hảo cho browser nhưng kết nối origin bằng cơ chế không kiểm tra tên/trust đúng, hoặc dùng HTTP plaintext do cấu hình. Khi điều tra, kiểm tra **origin TLS mode, hostname verification, CA pinning/approved trust profile, fallback behavior và logs**.

Không bật `ignore certificate errors` ở edge-to-origin chỉ vì origin dùng private CA; hãy triển khai **origin CA/certificate phù hợp** và strict verification theo hướng dẫn nhà cung cấp.

### 17.3. SNI và multi-tenant load balancer

Cùng một IP/port có thể serve nhiều certificates theo SNI. Nếu `openssl s_client` không đặt SNI chính xác, tool có thể thấy default certificate và báo lỗi không đại diện cho service thật. Ngược lại, test chỉ tên `api.example.test` có thể bỏ sót `admin.example.test` trên cùng LB nhưng dùng cert khác.

Cần ma trận **hostname × endpoint/IP × region × protocol × trust profile**, được giới hạn về scope và tần suất. Với hệ multi-tenant, không thử các tên của tenant khác nếu không có quyền.

### 17.4. IPv4, IPv6 và failover drift

Một FQDN có nhiều A/AAAA records và traffic load-balanced. Một lần resolve có thể vào node A; lần sau sang node B. Trong giai đoạn certificate rotation:

- Node A trình certificate mới.
- Node B trình certificate cũ nhưng vẫn hợp lệ.
- DR site trình certificate đã hết hạn.
- IPv6 frontend dùng secret bị thiếu intermediate.

Dashboard toàn dịch vụ có thể “xanh” nếu probe chỉ trúng node A. Chọn **điểm đo phù hợp cho từng route/vantage**, có inventory và report per-endpoint fingerprint/expiry.

### 17.5. Private endpoints và VPN

VPN tunnel `UP` không chứng minh ứng dụng bên trong TLS đúng. Một endpoint dùng DNS split-horizon có thể trả IP private ở văn phòng và IP public ngoài Internet. Kiểm thử từ **mỗi context được hỗ trợ** với đúng hostname, SNI, trust store và firewall authorization. Nếu private endpoint chỉ được truy cập qua ZTNA, **không mở public port chỉ để TLS scan**.

## 18. STARTTLS và các dịch vụ không phải HTTPS

### 18.1. Explicit TLS upgrade

SMTP, IMAP, POP3, LDAP và một số protocol có thể bắt đầu kết nối ở dạng application protocol rồi **nâng lên TLS** thông qua STARTTLS hoặc cơ chế tương ứng. Phép thử kết nối TLS trực tiếp như `s_client -connect host:25` có thể thất bại vì **server chưa nhận ClientHello ở đầu phiên**; điều đó không tự nghĩa server không hỗ trợ TLS.

### 18.2. Ví dụ SMTP STARTTLS có quyền

~~~bash
# Chỉ với SMTP relay lab do tổ chức kiểm soát, không gửi email.
openssl s_client \
  -connect mail.lab.example.test:587 \
  -starttls smtp \
  -servername mail.lab.example.test \
  -verify_hostname mail.lab.example.test \
  -verify_return_error \
  < /dev/null
~~~

Ở SMTP, **opportunistic STARTTLS** có thể cho phép fallback sang plaintext tùy policy. Một TLS handshake thành công **không chứng minh** ứng dụng bắt buộc encryption hoặc có chống downgrade. Với email, các chính sách bổ sung như MTA-STS/DANE (khi được triển khai đúng) có thể ảnh hưởng khả năng thực thi, nên cần test **policy/negative path** chứ không chỉ “STARTTLS advertised”.

### 18.3. Protocol-aware checks

- **LDAP StartTLS:** phân biệt `ldap://` + StartTLS với `ldaps://` implicit TLS, và kiểm tra hostname/cert đúng server.
- **IMAP/POP3:** xác nhận implicit TLS hoặc STARTTLS được yêu cầu theo client policy.
- **Databases:** PostgreSQL/MySQL/SQL Server có SSL/TLS modes, hostname verification và driver config riêng.
- **MQTT/gRPC:** xác minh TLS identity, client authentication, ALPN và application authorization.
- **Service mesh:** certificate identity có thể là `URI SAN`/SPIFFE ID, không phải DNS server hostname truyền thống; cần đúng verifier.

Không lấy một lệnh OpenSSL HTTPS áp nguyên sang protocol khác rồi diễn giải mọi lỗi handshake thành “cấu hình server yếu”.

## 19. HTTP/3, QUIC và certificate validation

HTTP/3 sử dụng **QUIC trên UDP** và TLS 1.3 handshake integration. Có thể cùng một FQDN nhưng hai listeners TCP/443 và UDP/443 đi qua khác LB/firewall/CDN paths.

### 19.1. Điều gì cần kiểm tra?

| Câu hỏi | Phương pháp |
|---|---|
| HTTP/3 có được client hỗ trợ và dùng thật? | Client build/runtime supporting HTTP3, protocol negotiation/response info |
| UDP/443 có reachable? | Approved QUIC client request và network policy logs |
| Certificate identity có hợp lệ? | TLS 1.3 identity verification của QUIC client với hostname |
| HTTP/3 path có khác HTTP/2? | So kết quả từ cùng client vantage và FQDN |
| Có fallback không? | Client behavior khi UDP bị chặn, không chủ động thay firewall production |
| ECH/HTTPS DNS records ảnh hưởng gì? | Client DNS/HTTPS record policy, visible vs protected names |

### 19.2. Ví dụ client có hỗ trợ HTTP/3

~~~bash
# Chỉ khi curl build có HTTP/3 support và endpoint test được duyệt.
# Nếu curl không có feature, không suy server không hỗ trợ HTTP3.
curl --http3-only \
  --silent --show-error \
  --connect-timeout 5 \
  --max-time 12 \
  --output /dev/null \
  https://api.lab.example.test/health
~~~

`curl --http3-only` yêu cầu HTTP/3 (nếu hỗ trợ), không thay cho strict certificate verification. `openssl s_client` trên TCP không tự kiểm thử QUIC/HTTP3 certificate path, vì transport/protocol khác. Một phép thử HTTP/3 thất bại còn có thể là **UDP firewall/NAT/MTU issue**, không chỉ certificate.

### 19.3. Không đồng nhất transport upgrade và identity

HTTP/3 nâng hiệu năng ở một số tình huống nhưng không thay đổi nguyên tắc: **client vẫn phải xác thực đúng server identity**. QUIC Connection ID không phải chứng chỉ, không là user ID và không thay SAN/trust validation.

## 20. Lỗi phổ biến và cách khoanh vùng theo lớp

| Triệu chứng | Khả năng cần kiểm | Dấu hiệu/bằng chứng |
|---|---|---|
| TCP connect timeout | DNS/route/ACL/VPN/LB/network issue | Route/firewall, client vantage, destination IP |
| TCP connection refused | Không có listener, policy reject, node sai | Host listener/LB health, network logs |
| TLS handshake thành công nhưng hostname FAIL | SAN không chứa reference name, SNI sai | Leaf SAN, chosen hostname, SNI, client validator |
| `unable to get local issuer certificate` | Chain thiếu hoặc truststore không đủ | `-showcerts`, root/intermediate mapping |
| `self-signed certificate` | Private CA không tin hoặc self-signed leaf ngoài policy | Trust anchor, PKI ownership |
| `certificate has expired` | `NotAfter` qua thời điểm client | UTC clock, served cert fingerprint |
| `certificate is not yet valid` | `NotBefore` ở tương lai hoặc client clock lệch | Cert validity và time sync |
| `hostname mismatch` | Wrong SAN, URL hostname, proxy certificate | SAN `dNSName`/`iPAddress`, reference identity |
| `unsupported protocol` / `protocol_version` | TLS version policy/client compatibility | Negotiated/forced version, middleboxes |
| `no shared cipher` / `handshake_failure` | Cipher/signature/group mismatch, client cert, SNI | Client/server TLS debug theo quyền |
| `certificate_required` | mTLS bắt buộc client certificate | Listener policy, cert issuer/identity |
| mTLS handshake PASS nhưng HTTP 403 | Authentication succeeded, authorization deny | Service policy/RBAC, identity mapping |
| TLS1.3 PASS, TLS1.2 FAIL | Server 1.3-only hoặc policy/stack khác | Actual config và expected baseline |
| IPv4 PASS, IPv6 cert FAIL | LB v6 khác cert/chain/route | Per-address/region test, served fingerprint |
| Browser PASS, Java PKIX FAIL | Truststores, AIA, runtime policies khác nhau | Java JDK/truststore/chain, actual JSSE test |
| Node A PASS, Node B FAIL | Rotation/config drift | Fingerprints per node, deployment version |
| Cert trên disk đúng, endpoint vẫn cũ | Reload/secret mount/ingress sync thiếu | Served cert fingerprint, reload logs |
| OCSP stapling missing | Server không staple, option/policy khác | `-status`, client revocation policy |
| TLS OK nhưng HTTP 502/503 | Gateway/backend outage | HTTP status, LB/ingress upstream logs |
| HSTS warning/browser block | Security policy/history, certificate failure | Browser behavior, HSTS config |
| QUIC fail, TCP HTTPS OK | UDP block, QUIC stack/MTU/policy | UDP path, HTTP3 feature, server logs |
| TLS alert unknown_ca | CA không tin ở phía đang validate | mTLS direction, CA bundle |
| Generic reset in TLS | Middlebox/IDS/IPS, server reject, app close | Network captures/firewall and TLS logs |
| Certificate mới nhưng pinning FAIL | Client pin còn khóa/cert cũ, rotation kế hoạch sai | Pin policy, app release, approved rollout |

### 20.1. Chẩn đoán theo thứ tự, không mở quyền bừa bãi

1. Xác định **client, hostname, port, IP/protocol, UTC time và lỗi đúng lúc nào**.
2. Kiểm tra DNS/routing/transport trước khi quy lỗi CA.
3. Kiểm tra **SNI và hostname verification**.
4. Ghi leaf fingerprint, SAN, issuer, validity và served chain.
5. Xác minh trust anchor/truststore **của client bị lỗi**, không chỉ máy của analyst.
6. Đọc TLS handshake version/cipher/signature/ALPN/mTLS requirements.
7. Xác định có TLS termination/re-encryption, IPv6/DR/alternate node khác không.
8. Kiểm tra revocation/CT/policy chỉ khi thuộc bài toán.
9. Nếu TLS thành công nhưng app fail, chuyển sang HTTP/application/authorization.
10. Thực hiện sửa cấu hình có review/rollback, test lại **cả ALLOW và DENY**.

**Không sửa bằng cách tắt certificate verification hoặc nới TLS xuống giao thức cũ**. Những cách này có thể làm lỗi biến mất nhưng đồng thời phá ranh giới bảo vệ.

## 21. Tư duy đánh giá bảo mật: TLS là một ranh giới, không phải toàn bộ kiến trúc

### 21.1. Threat modeling cho endpoint certificate

~~~mermaid
flowchart TD
    C["Authorized client"] --> DNS["Resolver / network"]
    DNS --> EDGE["TLS frontend: CDN/LB/ingress"]
    EDGE --> BACK["TLS/mTLS backend"]
    ATT["Misrouting / MITM / compromised trust"] -. "Có thể thay đổi peer" .-> DNS
    ROT["Certificate rotation drift"] -. "Expired / wrong certificate" .-> EDGE
    CA["CA / key custody / policy"] -. "Trust and issuance" .-> EDGE
    AUTH["Application authorization"] -. "Role/identity enforcement" .-> BACK
    OBS["Telemetry and verification"] -. "Detect path + trust deviations" .-> EDGE
~~~

| Rủi ro | Kết quả đáng ngại | Kiểm soát cần đánh giá |
|---|---|---|
| Hostname verification bị tắt | Client có thể chấp nhận certificate cho host khác | Strict SAN/reference identity validation |
| Root CA lạ được thêm globally | Phạm vi CA trust bị mở rộng ngoài ý định | Truststore governance, least privilege, root inventory |
| Private key server bị lộ | Attacker có thể giả server khi các điều kiện phù hợp | HSM/KMS/key custody, rotation/revocation, incident response |
| Certificate thiếu intermediate | Một số clients/regions không kết nối được | Full-chain deployment, real-client testing |
| Certificate hết hạn | Outage/TLS warning hoặc client fail closed | Monitoring, automation, rotation rehearsals |
| TLS1.0/legacy cipher còn mở | Downgrade/legacy crypto risk theo policy | Protocol/cipher baseline và client compatibility |
| SNI default certificate sai | Virtual host hoặc failover nhận sai danh tính | Per-SNI route/region verification |
| CDN→origin không xác minh CA/SAN | Frontend hợp lệ nhưng upstream có trust gap | Strict origin validation và private CA profile |
| mTLS chỉ kiểm CA, không kiểm role | Client bất kỳ có cert trong CA được vượt quyền | Service identity authorization per action |
| IPv6 hoặc DR cert drift | Một số users mất kết nối/nhận sai cert | Coverage IPv4/IPv6/DR, dynamic inventory |
| CT issuance bất thường | Certificate ngoài ý muốn được cấp | Issuance monitoring và CA response |
| OCSP unavailable/misinterpreted | False fail hoặc revocation blind spot | Client policy, cached response handling, HA |
| Session re-use/long-lived connections | Rollout chưa tác động phiên cũ | Client reconnection/restart/TTL testing |
| Malware ở endpoint | TLS vẫn được dùng để gửi dữ liệu trái phép | EDR, egress controls, app authorization, DLP theo scope |

**Không kết luận “có certificate hợp lệ nên chống được mọi MITM”.** Một attacker có quyền thay truststore, nắm private key, điều khiển endpoint hoặc thông qua proxy được client tin có thể làm thay đổi threat model. TLS bảo vệ mạnh khi **danh tính và trust decision được thực thi đúng**.

### 21.2. Bảo vệ lớp mạng hỗ trợ TLS

- **Segmentation/firewall:** hạn chế ai được kết nối tới service và protocol/port nào; không thay TLS identity validation.
- **VPN/ZTNA:** cung cấp network access policy; đường đi được cho phép vẫn cần TLS verify và app authorization.
- **IDS/IPS/WAF:** có thể quan sát handshake/metadata hoặc plaintext tại termination được ủy quyền; không suy từ passive sensor rằng đã đọc được HTTPS body.
- **DNS security:** giảm nguy cơ chuyển hướng DNS, nhưng client vẫn cần xác minh hostname của certificate.
- **Cloud security groups/ingress policies:** hạn chế direct-to-origin bypass, cả IPv4 và IPv6.
- **Endpoint hardening:** giữ truststore an toàn, ngăn malware thay CA/policy hoặc đọc private keys.

### 21.3. Xác minh chính sách không lấn sang khai thác

Kiểm tra TLS nên ưu tiên **hợp đồng bảo mật có thể xác minh và negative test trong lab**. Không brute-force ciphers/cert keys, không quét hàng loạt host công khai, không dùng kỹ thuật ép downgrade hay TLS renegotiation stress lên production. Những bài kiểm tra cần lưu lượng bất thường phải có **môi trường tách biệt và approval cụ thể**.

## 22. Giám sát chứng chỉ, thay mới và chống regression

### 22.1. Theo dõi từ phía client thay vì chỉ file trên disk

Một hệ thống có thể tự gia hạn certificate qua ACME/CA nhưng vẫn phục vụ certificate cũ do chưa reload proxy. Vì vậy giám sát cần **active TLS probe** từ đúng user/network vantage tới những hostname/LB paths quan trọng.

### 22.2. Bộ metrics/alerts thiết yếu

| Nhóm | Tín hiệu | Điều kiện đáng xem |
|---|---|---|
| **Expiry** | Served leaf `NotAfter` / số giây còn hạn | Dưới warning/critical thresholds theo rotation SLO |
| **Hostname** | SAN match đúng FQDN/IP | Bất kỳ mismatch trên endpoint production |
| **Chain** | Trusted path theo client profile | Bất kỳ failure đối với supported clients |
| **Fingerprint** | Served leaf fingerprint per route | Thay đổi ngoài change window, hoặc node drift |
| **TLS config** | Negotiated TLS version/cipher/ALPN | Version trái baseline, client compatibility fail |
| **mTLS** | Client certificate handshake/authorization errors | Unexpected denies, expired workloads, wrong trust domain |
| **Revocation** | OCSP/CRL data/freshness khi policy yêu cầu | Stale/missing/unknown theo chính sách, không suy revoked |
| **Availability** | Strict HTTPS synthetic success/latency | User-visible failures hoặc handshake error surge |
| **Coverage** | Expected probes/actual probes, zones/IP stacks | Mất telemetry/route chưa được kiểm |

**Probe không chạy không đồng nghĩa TLS healthy.** Hiển thị `UNKNOWN/NO DATA` và đo availability của monitoring system riêng, không chuyển absence thành PASS.

### 22.3. Rotation lifecycle

~~~mermaid
flowchart TD
    I["Inventory and ownership"] --> C["Issue valid new certificate"]
    C --> V["Validate SAN/chain/EKU/key/expiry"]
    V --> ST["Stage to canary endpoint"]
    ST --> P{"Strict client validation succeeds?"}
    P -- "Không" --> FIX["Fix chain/name/trust/config"]
    FIX --> ST
    P -- "Có" --> DEP["Deploy to all TLS termination points"]
    DEP --> POST["Verify served fingerprint per region/SNI/IP"]
    POST --> N{"Drift or failure?"}
    N -- "Có" --> R["Rollback within security policy and investigate"]
    N -- "Không" --> MON["Monitor expiry and retire old credential"]
~~~

Lưu ý:

1. Certificate mới phải có **reference names/SANs** đủ cho những endpoints thực sự được hỗ trợ.
2. Intermediate/CA chains phải đúng theo các **client trust stores** quan trọng.
3. Backend mTLS client certificates và root rotation có thể cần **overlap trust window** để tránh outage.
4. Key rotation/private key storage cần HSM/KMS/ACL theo rủi ro; không in private key trong logs.
5. Thử **canary + negative tests** trước rollout; không chỉ kiểm tra một endpoint từ máy deployer.
6. Có khả năng phục hồi nếu failover node/DR route trả old certificate.
7. Khi certificate/key bị compromise, xem **revoke, rotate và incident escalation** theo policy, không đợi expiry.

### 22.4. Cảnh báo theo thời hạn còn lại

Ví dụ tổ chức đặt warning khi còn **30 ngày** và critical khi còn **7 ngày**, song đây **không phải ngưỡng bắt buộc cho mọi hệ thống**. Với short-lived certificates, phải đặt alert phù hợp chu kỳ tự động phát hành/renew; một cert chỉ còn vài ngày có thể **bình thường** nếu tự thay vài giờ một lần. Đánh giá **khả năng renew thành công, served cert transition và time to expiry** cùng nhau.

### 22.5. Recheck sau đổi CA và truststore

Thay CA root hoặc deprecate root cũ có thể làm browser PASS còn Java/embedded clients FAIL. Có thể cần staged rollout:

~~~text
Before:
  Test known client versions/truststores
  Confirm issuer path and expiry
  Stage new server certificate and intermediate chain

During:
  Observe client verification errors and mTLS failures
  Compare served leaf and path per endpoint
  Maintain approved overlap trust only as necessary

After:
  Remove retired trust anchors when safe
  Confirm only intended identities/CA paths accepted
  Preserve validation and change evidence
~~~

**Giữ một root đã ngừng tin mãi mãi để tránh lỗi client không phải phương án bền vững.** Cần theo dõi các runtime chưa được nâng cấp và có kế hoạch thay thế.

## 23. Ma trận 45 trường hợp kiểm thử TLS/certificate endpoint

Ma trận này định nghĩa **phép thử cần làm** và **tiêu chí có thể kiểm chứng**, không khẳng định chúng đã chạy. Những negative tests về certificate sai/CA không tin/expired hoặc client mTLS giả định dùng **lab test CA/test certificates**; không gây lỗi lên production hay thử giả mạo người dùng/tenant khác.

| ID | Kịch bản / mục tiêu | Cách xác minh trong phạm vi cho phép | PASS khi |
|---|---|---|---|
| **ID-01** | Đúng hostname/port/asset inventory | So requested FQDN, IP, owner và TLS listener | Endpoint thuộc scope, target xác định |
| **ID-02** | Client, truststore và thời gian rõ ràng | Lưu tool/runtime version, UTC, CA source | Có thể tái lập kết quả |
| **ID-03** | DNS A/AAAA có mapping đúng | Resolver/route/approved endpoint records | Không gắn nhầm DNS result với certificate identity |
| **ID-04** | SNI được gửi đúng | Explicit `-servername`, served leaf | Virtual host phù hợp reference name |
| **ID-05** | Không dùng bypass verification | Review commands/client config | Không có `-k`, trust-all hoặc disabled verifier |
| **SAN-01** | SAN DNS match đúng hostname | Strict client/`verify_hostname` | Valid name được chấp nhận |
| **SAN-02** | SAN DNS sai tên | Controlled wrong-cert lab endpoint | Strict client DENY |
| **SAN-03** | Wildcard một nhãn | `*.example.test` với `api.example.test` lab | Đúng policy match behavior |
| **SAN-04** | Wildcard không phủ apex/nhiều nhãn | Test apex/sub-subdomain trong lab | Mismatch bị từ chối |
| **SAN-05** | URL IP literal dùng IP SAN | Test certificate có `iPAddress` SAN | Đúng IP match policy |
| **SAN-06** | DNS SAN không thay IP SAN | URL IP literal, certificate chỉ DNS SAN | DENY khi không có IP identity hợp lệ |
| **SAN-07** | CN-only certificate | Test client hiện đại có strict SAN checking | Không dựa vào CN fallback ngoài policy |
| **SAN-08** | IPv4/IPv6 có name match cùng FQDN | Dual-stack vantage, strict client | Mỗi route trả certificate hợp lệ |
| **PKI-01** | Chuỗi server gửi đủ intermediates | `-showcerts`, chain inventory | Các client hỗ trợ xác minh được |
| **PKI-02** | Root CA/trust anchor đúng | Public/private trust profile | Không tin root ngoài chính sách |
| **PKI-03** | Leaf/intermediate constraints đúng | `openssl verify` + extensions review | CA/leaf roles và path constraints hợp lệ |
| **PKI-04** | EKU/keyUsage phù hợp | Certificate parse + client TLS validation | ServerAuth/clientAuth theo vị trí và policy |
| **PKI-05** | Certificate chưa hết hạn | UTC, `NotBefore/NotAfter`, strict client | Trong khoảng hiệu lực |
| **PKI-06** | Cert hết hạn/not yet valid bị từ chối | Test-only certificate/time context | DENY đúng lớp, không đổi production clock |
| **PKI-07** | Thuật toán/key length đạt baseline | Leaf/chain signature/public key inspection | Đáp ứng approved crypto policy |
| **PKI-08** | Revocation/OCSP/CRL được diễn giải đúng | Stapling/policy/response validity | Không nhầm missing với revoked hoặc GOOD với toàn bộ trust |
| **TLS-01** | TLS 1.3 handshake và validation | `s_client -tls1_3` với strict verification | Negotiated TLS1.3 theo baseline |
| **TLS-02** | TLS 1.2 compatibility khi được phép | `s_client -tls1_2` với strict verification | Accept/reject theo approved policy |
| **TLS-03** | TLS1.0/1.1/SSL bị giới hạn | Read-only config review/lab negative test | Deprecated versions không được mở trái policy |
| **TLS-04** | Negotiated cipher/signature/group | Handshake details, policy review | Không có crypto bị cấm |
| **TLS-05** | ALPN phù hợp ứng dụng | TLS negotiation + HTTP client check | `h2`/`http/1.1` theo design |
| **TLS-06** | HTTP/3/QUIC kiểm thử đúng transport | Client có H3 support, UDP path | Cert trust và user request đạt theo design |
| **TLS-07** | TLS1.3 PFS được hiểu đúng | Protocol/key agreement review | Không dùng server RSA key như universal decrypt |
| **TLS-08** | TLS thành công nhưng app authorization riêng | HTTPS request và app response | Không gộp TLS PASS với business PASS |
| **MTLS-01** | Có client certificate hợp lệ | Lab client cert và đúng server trust | Mutual authentication theo policy |
| **MTLS-02** | Không có client cert | Controlled lab client không cấp cert | DENY nếu listener bắt buộc mTLS |
| **MTLS-03** | Client cert từ CA không tin | Lab untrusted client cert | DENY theo server trust policy |
| **MTLS-04** | Cert đúng CA nhưng role không đủ | Authorized lab identity với scope hẹp | TLS có thể PASS, app access DENY |
| **MTLS-05** | Client cert rotation/revocation | Test-only cert lifecycle | Behavior và session handling đúng chính sách |
| **EDGE-01** | Public edge certificate hợp lệ | Browser-like strict client from Internet vantage | SAN/chain/TLS đầy đủ |
| **EDGE-02** | CDN→origin có strict verification | Origin connector config/log + controlled test | Không bỏ origin CA/hostname check |
| **EDGE-03** | Ingress→backend mTLS đúng identity | Service mesh/proxy TLS + authz audit | Không cho unapproved workload |
| **EDGE-04** | Mỗi SNI virtual host đúng cert | Approved host matrix, đúng SNI | Không serve default/wrong cert |
| **EDGE-05** | Multi-region/DR rotation nhất quán | Fingerprint/expiry per region/route | Không node nào trả cert lỗi/trái policy |
| **EDGE-06** | STARTTLS/implicit TLS được phân biệt | Lab SMTP/LDAP/client tests | Bắt buộc encryption theo protocol contract |
| **OBS-01** | Served cert so với desired inventory | Fingerprint + deployment metadata | File/config và cert served khớp |
| **OBS-02** | Expiry monitor báo trước hạn | Synthetic check, alert window | Cảnh báo theo rotation SLA/SLO |
| **OBS-03** | No-data được phát hiện | Simulate missed probes ở lab | UNKNOWN/monitoring alert, không false PASS |
| **OBS-04** | Audit không lộ private key | Evidence/report review | Chỉ public cert metadata và approved logs |
| **OBS-05** | Remediation/rollback có regression test | Canary, negative/positive clients, DR | Sửa lỗi nhưng không nới trust/TLS sai policy |

### 23.1. PASS, FAIL, INCONCLUSIVE

- **PASS** khi có đủ bằng chứng cho điều kiện test, gồm **đúng endpoint + đúng truststore/client + đúng kết quả**. Negative test PASS nghĩa strict client **từ chối đúng certificate/client identity trái phép**.
- **FAIL** khi một đường được phép không kết nối do certificate sai/chain thiếu, client chấp nhận cert trái policy, mTLS cho identity không được phép qua hoặc TLS configuration lệch baseline.
- **INCONCLUSIVE** khi DNS sai, backend down, firewall chặn trước TLS, TLS client không hỗ trợ protocol đang test, OCSP/stapling data thiếu mà chưa biết policy, certificate được quan sát từ IP/route khác hoặc không đủ logs/coverage.

**Không coi timeout từ IP không được phép là TLS validation PASS**: nếu handshake chưa diễn ra, không có certificate nào được client kiểm tra. Muốn xác minh hostname deny phải dùng **endpoint lab khỏe** và chứng minh request bị từ chối tại **certificate verification**.

### 23.2. Mẫu evidence cho một test

~~~yaml
test_id: SAN-02
environment: isolated-authorized-tls-lab
time_utc: pending
source:
  client_runtime: openssl-or-application-runtime
  runtime_version: pending
  truststore_profile: approved-test-ca
target:
  hostname: api.lab.example.test
  port: 443
  address_family: IPv4
  resolved_ip: pending
  sni: api.lab.example.test
certificate:
  observed_leaf_fingerprint_sha256: pending
  observed_san: pending
  observed_chain_fingerprints: pending
expected:
  wrong_certificate_hostname: reject
  matching_certificate_hostname: accept
evidence:
  - strict-client-command-and-exit-status
  - certificate-chain-and-name
  - server-side-lab-configuration
  - timestamp-and-authorization
result: pending-execution
~~~

Không dùng `result: PASS` trong hồ sơ khi chưa chạy và phân tích kết quả. Không chụp hoặc lưu **server/client private key** vào ticket.

## 24. Case study 1 — Browser truy cập được, Java service lỗi PKIX sau rotation

### 24.1. Bối cảnh giả định

Một đội Platform thay certificate cho `api.lab.example.test` thông qua public CA. Họ mở browser từ máy làm việc và thấy HTTPS hoạt động, nên kết luận triển khai thành công. Tuy nhiên microservice Java chạy trong một container bắt đầu báo:

~~~text
SSLHandshakeException
  PKIX path building failed
  unable to find valid certification path to requested target
~~~

Đồng thời:

~~~text
Browser on managed workstation: HTTPS PASS
Java service in container A: handshake FAIL
Java service in container B: handshake PASS
Leaf SAN: DNS:api.lab.example.test
Leaf NotAfter: future, not expired
CDN/WAF status: healthy
Server-sent intermediates: one expected intermediate missing
~~~

Đây là **tình huống giả định dùng để đào tạo**, không phải kết quả của một hệ thống thật.

### 24.2. Vì sao chỉ xem cert leaf chưa đủ?

~~~mermaid
flowchart LR
    B["Browser workstation"] --> LB["TLS endpoint: leaf only"]
    J1["Java container A"] --> LB
    J2["Java container B"] --> LB
    B -. "Intermediate cached/fetched" .-> PASS["PKI path success"]
    J1 -. "No cached intermediate" .-> FAIL["PKIX path failure"]
    J2 -. "Different trust/cache state" .-> PASS
~~~

Browser có thể **đã có intermediate trong cache** hoặc có khả năng tự lấy AIA, trong khi một Java runtime không có chain đầy đủ. Việc Java B PASS cũng không chứng minh server bundle đúng; có thể do truststore khác hoặc startup/connection cache.

### 24.3. Quy trình điều tra

1. Ghi **exact UTC window**, Java JDK vendor/version và container image revision.
2. Chạy strict TLS test từ **cùng network/trust context** với client bị lỗi.
3. Thu leaf/chain server trình bằng `s_client -servername ... -showcerts` trên endpoint được phép.
4. Kiểm tra SAN, issuer, AKI/SKI và intermediate CA bundle từ source of truth.
5. So **root CA trong Java truststore** và chain/path building behavior.
6. Thử `openssl verify -CAfile ... -untrusted ...` với public certs được kiểm soát, ghi rõ đây là kiểm tra ngoại tuyến.
7. Sửa **full-chain deployment trên đúng frontend**, reload/redeploy theo change control.
8. Test **Java application thật** và browser/synthetic từ các vùng khác; giữ hostname verification.
9. Đối chiếu fingerprints, NotAfter, OCSP/expiry monitoring; tạo regression rule cho chain coverage.

### 24.4. Trước và sau

| Điều kiện | Trước giả định | Mục tiêu sau sửa |
|---|---|---|
| Browser strict HTTPS | PASS | PASS |
| Java container A | FAIL | PASS |
| Java container B | PASS | PASS |
| Server sends required intermediate | Missing | Present |
| Public/private trust anchor | Không thay bừa bãi | Được giữ đúng profile |
| Java trust-all disable | Không dùng | Không dùng |
| Rotation inventory | Không biết node nào được cập nhật | Served fingerprint được so từng node |

**Bài học:** certificate chain là một phần của **client compatibility/security**. Sửa đúng ở endpoint thay vì biến Java thành trust-all client.

## 25. Case study 2 — SNI và IPv6 DR endpoint trả certificate sai

### 25.1. Bối cảnh giả định

Một ứng dụng public sử dụng `api.lab.example.test` qua IPv4 và IPv6. Certificate được thay ở load balancer IPv4 primary, nhưng IPv6 frontend của disaster recovery site vẫn dùng secret cũ, có **SAN cho hostname khác**. Giám sát chỉ chạy từ probe IPv4 và báo “TLS green”.

~~~text
Client A / IPv4 / primary route:
  SAN api.lab.example.test: MATCH
  Chain: trusted
  TLS1.3: OK
  HTTP: 200

Client B / IPv6 / DR route:
  SAN old-api.lab.example.test: MISMATCH
  Chain: trusted
  TLS1.3 handshake may complete before hostname rejection
  Strict HTTPS client: FAIL
~~~

Việc chain trusted **không cứu được** SAN sai. Kết quả handshake với OpenSSL thiếu `-verify_hostname` có thể trông như thành công dù client thực vẫn chặn.

### 25.2. Thiết kế kiểm thử

~~~mermaid
flowchart TD
    DNS["FQDN api.lab.example.test"] --> A["A records IPv4"]
    DNS --> AAAA["AAAA records IPv6"]
    A --> P["Primary LB: new cert"]
    AAAA --> DR["DR LB: old cert"]
    P --> V1["Strict TLS: PASS"]
    DR --> V2["Strict TLS: SAN mismatch"]
    MON["IPv4-only health monitor"] -. "Misses IPv6" .-> V2
~~~

Quy trình kiểm:

1. Inventory A/AAAA, regions, ports, SNI routes và proxy termination points.
2. So client `curl -4` / `curl -6` từ điểm có IPv6 thật (không suy từ lỗi không có IPv6 connectivity).
3. Dùng `curl --resolve` để gọi **đúng frontend IP** mà vẫn giữ hostname/reference identity.
4. Thu served leaf fingerprint, SAN, chain, notAfter, TLS protocol và response cho từng route.
5. Xác định config/secret sync hoặc stale deployment ở DR LB.
6. Triển khai corrected certificate/chain, tránh lộ private key qua ticket.
7. Test lại IPv4/IPv6, SNI mặc định và chính hostname có quyền.
8. Bổ sung monitoring **per region + IP family + relevant SNI** và dữ liệu `NO DATA`.

### 25.3. Mục tiêu kiểm thử

| Trường hợp | Kỳ vọng |
|---|---|
| IPv4 primary, correct hostname | ALLOW / strict TLS PASS |
| IPv6 DR, correct hostname | ALLOW / strict TLS PASS |
| Hostname không nằm trong SAN | DENY bởi validator |
| CA không nằm trong trust profile | DENY |
| Backend không được phép truy cập trực tiếp | DENY ở network boundary |
| Expiry/fingerprint monitor của DR | Thu được dữ liệu đúng và cảnh báo drift |

**Bài học:** **“TLS xanh” chỉ có ý nghĩa theo đúng vantage và route được đo**. Một FQDN có nhiều địa chỉ/termination points cần mức coverage tương xứng với thiết kế sản xuất.

## 26. Case study 3 — mTLS đã xác thực nhưng service vẫn cấp quyền quá rộng

### 26.1. Bối cảnh giả định

Một công ty dùng mTLS giữa hai microservices: `inventory` và `billing`. Hai workloads đều được cấp certificates bởi một internal CA. Chính sách gateway chỉ yêu cầu **certificate được ký bởi CA nội bộ**, nhưng lại không xác định **dịch vụ nào được gọi endpoint quản trị `/admin/reconcile`**.

Một workload `inventory` hợp lệ nhưng không có quyền nghiệp vụ quản trị có thể hoàn thành mTLS handshake tới `billing`, sau đó request được xử lý vì application thiếu authorization.

> Đây là kịch bản đánh giá thiết kế, không phải hướng dẫn chiếm quyền. Các test chỉ áp dụng với test identities/services được cấp phép.

### 26.2. Ranh giới mTLS và authorization

~~~mermaid
flowchart LR
    INV["Workload: inventory"] --> TLS["mTLS gateway"]
    TLS --> AUTH["Application authorization"]
    AUTH --> ADMIN["Sensitive API"]
    CA["Internal CA"] -. "Verifies certificate trust" .-> TLS
    POL["Role / identity policy"] -. "Should enforce resource/action" .-> AUTH
~~~

**Câu hỏi thứ nhất:** certificate của `inventory` có đúng trust profile và clientAuth EKU không? **Câu hỏi thứ hai:** `inventory` có quyền nghiệp vụ `admin:reconcile` không? Nếu chỉ kiểm câu thứ nhất thì policy vẫn thiếu.

### 26.3. Ma trận đánh giá

| Client/test identity | mTLS expectation | App authorization expectation |
|---|---|---|
| `billing-admin-lab` hợp lệ | PASS | ALLOW task được cấp quyền |
| `inventory-lab` hợp lệ nhưng không có admin role | PASS | DENY sensitive action |
| Không có client certificate | DENY ở TLS nếu listener strict mTLS | Không đến application |
| Client cert từ untrusted CA | DENY ở TLS | Không đến application |
| Expired client cert | DENY theo trust validation | Không đến application |
| Client cert hợp lệ nhưng credential bị revoke | DENY/session handling theo policy | Không còn quyền ngoài ý định |

### 26.4. Sửa lỗi theo defense-in-depth

1. Inventory **service identities**, CA trust domains, certificate SAN URI/DNS và rotation.
2. Cấu hình strict mTLS ở listener đúng phạm vi, đóng plaintext fallback không được phê duyệt.
3. Kiểm tra `serverAuth`/`clientAuth` EKU/usages của cert theo profile.
4. Áp authorization **source identity → destination/resource/action**, không chỉ CA trust.
5. Giới hạn network path với CNI/NetworkPolicy/firewall và kiểm tra đường bypass.
6. Audit request decisions với workload identity và policy revision.
7. Negative tests bảo đảm `inventory-lab` không vào admin API trong khi `billing-admin-lab` vẫn hoạt động.
8. Kiểm thử trust/key rotation, session expiry và response khi revoked credentials theo yêu cầu.

### 26.5. Bài học

**mTLS cung cấp cơ chế xác thực workload** và mã hóa transport, nhưng **không mặc nhiên cấp quyền mọi request**. Kiểm thử đúng phải xác minh đồng thời identity, transport và authorization tại service.

## 27. Runbook kiểm thử và xác minh TLS/certificate endpoint

Runbook này là một **quy trình kiểm thử có phê duyệt**, không thay tài liệu vận hành sản phẩm hoặc quy trình phát hành certificate của tổ chức. Chỉ dùng trên dịch vụ nằm trong scope, giới hạn số requests và tránh sửa production để tạo lỗi giả.

### Bước 1 — Xác định mục tiêu và hợp đồng bảo mật

Ghi:

~~~yaml
# Policy-as-intent mẫu, không phải file cấu hình có thể áp dụng.
service: api.lab.example.test
environment: isolated-authorized-lab
owner: platform-security
allowed_endpoint:
  scheme: https
  hostname: api.lab.example.test
  port: 443
supported_clients:
  - managed-browser
  - approved-java-runtime
identity_verification:
  dns_san_required: true
  trust_profile: approved-test-ca
  private_key_export_forbidden: true
transport:
  tls_1_3: required
  tls_1_2: allowed_if_meets-approved-policy
  disabled_versions: older-than-tls1.2
  alpn: [h2, http/1.1]
authorization:
  public_health_check: allowed
  admin_actions: authenticated-and-authorized
coverage:
  - IPv4-primary
  - IPv6-if-supported
  - disaster-recovery
  - edge-and-origin
evidence:
  store: restricted-security-test-repository
  time_basis: UTC
  do_not_collect: [private-keys, client-secrets, bearer-tokens]
execution_status: not-yet-run
~~~

Lưu ý `tls_1_2: allowed_if_meets-approved-policy` trong YAML chỉ mô tả **chính sách kỳ vọng**, không phải boolean/syntax của một API cụ thể. Chính sách thực tế do owner xác nhận.

### Bước 2 — Lập inventory TLS termination points

Đối với mỗi FQDN/service:

| Thuộc tính | Cần ghi |
|---|---|
| Service/owner | Hostname, criticality, port, application owner |
| Name resolution | A/AAAA, split DNS, CDN/LB, VPN/private endpoint |
| TLS termination | CDN, WAF, L4/L7 LB, ingress, proxy, sidecar, backend |
| Expected certificate | SAN names, issuer/CA profile, fingerprint desired state, NotAfter |
| Expected trust | Browser/OS, Java, container, custom private CA/mTLS |
| Network path | IPv4/IPv6, region/AZ, failover, VPN, direct-origin access |
| Change policy | Rotation owner, on-call, rollback/canary, exception expiry |

Không test các SNI/tenants ngoài phạm vi. Chỉ phân tích đường proxy/backend khi **có quyền network/application** đến segment đó.

### Bước 3 — Chọn vantage và công cụ

1. **Browser/user vantage:** strict HTTPS từ region/mạng người dùng.
2. **Application runtime vantage:** Java/Go/.NET client, truststore/config như thực tế.
3. **Inside-VPC/cluster vantage:** kiểm tra origin/backend/mTLS theo quyền.
4. **IPv4/IPv6 vantage:** xác định client có route hợp lệ và dùng đúng hostname.
5. **DR/failover vantage:** check những frontends có thể nhận traffic khi chuyển vùng.

Khi một đường private không mở cho máy test, **không mở firewall tạm để quét**; dùng công cụ/agent đã được phê duyệt trong private network hoặc read-only config/audit.

### Bước 4 — Thực hiện strict client baseline

~~~text
For each approved hostname and vantage:
  Resolve/record actual destination IP(s)
  Attempt bounded TCP/QUIC connect
  Send correct SNI/reference hostname
  Validate certificate hostname and chain
  Record TLS version, negotiated cipher and ALPN
  Perform one benign application request if approved
  Record exit status and whether response met contract
~~~

Trước khi xét performance, phải chứng minh **identity/trust PASS**. Một TLS handshake fail trước khi server trả certificate có thể do **route/protocol mismatch**; không gán vào SAN mismatch khi chưa thấy cert.

### Bước 5 — Kiểm tra certificate properties và chain

- Thu served leaf fingerprint, SAN, validity, issuer/serial và key/cert signature algorithms.
- Xác định **server-sent chain**, phân biệt root trusted của client.
- Kiểm tra EKU/keyUsage/basic constraints/name constraints theo certificate role.
- Xác nhận revocation behavior theo client policy, ghi `OCSP stapled / absent / unknown` đúng nghĩa.
- So certificate deployed với PKI/ACME desired inventory; xác minh mọi region/node quan trọng.
- Kiểm tra **NotAfter** và cảnh báo trước khi certificate thành stale.

### Bước 6 — Kiểm tra transport và protocol

- TLS 1.3/1.2 theo baseline, cipher suite/signature/key agreement group đúng policy.
- ALPN của HTTP/2/1.1, HTTP/3/QUIC bằng **client riêng có support**.
- Không có fallback TLS phiên bản deprecated ngoài exception được ký duyệt.
- STARTTLS/implicit TLS cho mail/LDAP/database được kiểm tra **theo protocol**.
- Với mTLS, tách **TLS server authentication, client certificate authentication và application authorization**.

### Bước 7 — Positive và negative cases

~~~text
Positive examples:
  Correct hostname + trusted chain + valid time -> strict TLS success
  Supported Java client + approved truststore -> service request success
  Approved mTLS identity -> authorized operation success
  IPv4 and IPv6 documented routes -> equivalent identity validation

Negative examples (isolated lab):
  Wrong SAN -> strict TLS client rejection
  Untrusted root -> rejection
  Expired/test invalid certificate -> rejection
  Missing mTLS client certificate -> TLS denial where required
  Valid cert but insufficient application role -> HTTP authorization DENY
  Legacy TLS version -> rejected if baseline forbids
~~~

Ghi **tại lớp nào** request bị từ chối: DNS, connect, TLS protocol, certificate path, hostname, mTLS hoặc application role. Không coi server/port đang down là một negative SAN test đã PASS.

### Bước 8 — Khắc phục và triển khai theo canary

~~~mermaid
flowchart TD
    R["Find verified certificate/TLS defect"] --> D["Review owner, scope, impact and rollback"]
    D --> S["Stage corrected cert/chain/config"]
    S --> T["Run strict positive and negative lab tests"]
    T --> G{"Expected verification results?"}
    G -- "Không" --> FIX["Fix candidate, do not disable validation"]
    FIX --> T
    G -- "Có" --> C["Canary by route/client/region"]
    C --> O["Observe served fingerprints and handshake errors"]
    O --> P{"Regression or trust drift?"}
    P -- "Có" --> RB["Rollback through approved process"]
    P -- "Không" --> F["Full rollout and monitor"]
~~~

Một rollback về certificate cũ **chỉ hợp lệ nếu certificate và private key cũ vẫn đáp ứng security policy**. Nếu certificate cũ bị revoked/compromised, không rollback về trạng thái không an toàn; dùng phương án phát hành/đổi route được duyệt.

### Bước 9 — Kiểm tra sau triển khai

1. So certificate served fingerprint/expiry/chain với expected state **từng endpoint**.
2. Kiểm tra strict Browser/Java/SDK clients theo phạm vi hỗ trợ.
3. Test IPv4/IPv6, public/private, primary/DR, từng SNI thuộc scope.
4. Với mTLS, đảm bảo authorized client hoạt động và unauthorized client bị deny.
5. Xác nhận upstream origin/backend strict verification vẫn bật.
6. Theo dõi TLS handshake failures, client errors, certificate expiry và telemetry coverage.
7. Đóng exception tạm, ghi change ID, responsible owner và next review date.

### Bước 10 — Handoff và vận hành liên tục

~~~yaml
assessment_id: TLS-LAB-008
status: pending-execution
time_utc: pending
service: api.lab.example.test
vantage: test-client-01
client_runtime: pending
tls_termination_point: pending
dns_resolution: pending
sni: api.lab.example.test
reference_identity: api.lab.example.test
truststore_profile: approved-test-ca
certificate:
  leaf_sha256: pending
  san: pending
  issuer: pending
  not_after_utc: pending
  chain_validation: pending
protocol:
  tls_version: pending
  cipher_suite: pending
  alpn: pending
http_outcome: pending
negative_tests: pending
evidence:
  command_and_exit_status: pending
  tls_handshake_log_reference: pending
  change_and_rollback_reference: pending
result: INCONCLUSIVE_UNTIL_EXECUTED
~~~

**Mẫu không phải kết quả thật.** Không điền fingerprint, TLS version hoặc `PASS` từ suy đoán, không lưu private key, session cookies hoặc bearer token trong báo cáo.

## 28. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài 1 — TCP 443 và TLS

Một phép thử TCP/443 thành công nhưng `curl` báo certificate verify failed. Có thể nói endpoint TLS “đạt” vì cổng mở không?

*Đáp án:* không. TCP connect chỉ xác nhận transport; TLS chain/hostname validation là điều kiện độc lập.

### Bài 2 — SAN so với CN

Certificate có `CN=api.lab.example.test` nhưng không có DNS SAN phù hợp. Có nên chấp nhận vì CN trông đúng?

*Gợi ý:* không dựa CN fallback cho cấu hình mới. Cấp certificate có SAN hợp lệ, kiểm tra với client strict.

### Bài 3 — Wildcard

Certificate có `DNS:*.lab.example.test`. Nó có tự khớp `lab.example.test` và `a.b.lab.example.test` không?

*Đáp án:* không. Wildcard thông thường không phủ apex hoặc hai nhãn bên dưới.

### Bài 4 — IP address

Ứng dụng gọi `https://192.0.2.10/` và certificate chỉ có `DNS:api.lab.example.test`. Nên sửa bằng `verify=false` không?

*Đáp án:* không. Dùng hostname đúng và DNS/route hợp lệ hoặc cấp IP SAN phù hợp nếu dịch vụ thực sự cần IP reference identity.

### Bài 5 — SNI

Cùng một LB IP serve hai services theo SNI. Vì sao một lần dùng `s_client -connect IP:443` chưa đủ kiểm thử service A?

*Gợi ý:* có thể nhận default certificate. Phải gửi SNI đúng và kiểm hostname reference identity của service A.

### Bài 6 — Thiếu intermediate

Browser kết nối được nhưng Java service báo PKIX. Nêu ba nguồn chứng cứ đầu tiên cần thu.

*Gợi ý:* server-sent chain với SNI, Java JDK/truststore profile, certificate leaf/issuer/SAN và client exception chain.

### Bài 7 — Root tự ký

Một private CA root được công ty phê duyệt ký server cert trong VPN. Public browser không tin root. Có phải server certificate chắc chắn giả?

*Đáp án:* không. Đó có thể là private PKI hợp lệ; phải đánh giá theo approved trust policy và client có quyền. Không thêm root lạ tùy ý cho mọi user.

### Bài 8 — Expiry threshold

Certificate hết hạn sau 20 ngày, monitoring warning threshold là 30 ngày. Có thể nói certificate đã hết hạn chưa?

*Đáp án:* chưa. Nó **còn hiệu lực theo thời gian** nhưng cần cảnh báo/rotation trước khi hết hạn.

### Bài 9 — EKU

Leaf certificate chỉ có usage phù hợp client authentication, không có serverAuth theo profile bắt buộc. Có thể dùng làm TLS server cert vì CA đã ký không?

*Gợi ý:* không. Client/server certificate usages và EKU phải phù hợp protocol và policy.

### Bài 10 — Cipher và signature

Một server dùng RSA certificate nhưng phiên TLS 1.3 báo `TLS_AES_128_GCM_SHA256`. Có thể suy RSA mã hóa trực tiếp mọi packet không?

*Đáp án:* không. Certificate public key phục vụ peer authentication, TLS record traffic dùng negotiated session secrets/AEAD.

### Bài 11 — Forward secrecy

Biết server certificate private key có đủ giải mã một PCAP TLS 1.3 từ trước không?

*Đáp án:* không. TLS 1.3 full handshake có key agreement/key schedule, không tự suy traffic secrets từ private key certificate.

### Bài 12 — OCSP staple

`openssl s_client -status` trả `no response sent`. Có thể kết luận certificate revoked không?

*Đáp án:* không. Chỉ biết trong phiên thử không thấy OCSP staple; cần xem trust/revocation policy và các nguồn thích hợp.

### Bài 13 — Certificate Transparency

Certificate xuất hiện trong CT log có tự động là certificate đang dùng ở production và luôn đáng tin không?

*Đáp án:* không. CT hỗ trợ công bố/kiểm toán issuance; không thay kiểm tra deployment, trust chain, SAN hoặc endpoint identity.

### Bài 14 — DNS CAA

Trong HTTPS handshake, browser có cần DNS CAA record để quyết định certificate issuer được chấp nhận không?

*Gợi ý:* CAA chủ yếu kiểm soát quyền cấp certificate ở CA issuance workflow; không phải phép path/hostname validation tiêu chuẩn của browser trong TLS handshake.

### Bài 15 — TLS1.2 chính sách

Một TLS1.2 connection với strong suite đáp ứng baseline được phê duyệt. Có thể báo FAIL chỉ vì không phải TLS1.3 không?

*Gợi ý:* không mặc định. Kiểm tra **approved policy**, tương thích, chosen cipher/key exchange và nhu cầu dịch vụ.

### Bài 16 — ALPN

Một server đàm phán `h2` qua TCP/TLS; điều đó tự chứng minh HTTP/3 đã hoạt động không?

*Đáp án:* không. HTTP/3 chạy qua QUIC/UDP, cần phép thử riêng.

### Bài 17 — mTLS và authorization

Workload A có client cert hợp lệ từ internal CA nhưng không có quyền gọi `/admin`. Nếu TLS handshake PASS, ứng dụng có nên trả kết quả admin không?

*Đáp án:* không. mTLS authentication và application authorization là hai lớp độc lập.

### Bài 18 — mTLS không có client cert

Một listener yêu cầu mTLS nghiêm ngặt nhưng client không gửi cert và vẫn vào được chức năng nhạy cảm. Đây là FAIL ở đâu?

*Gợi ý:* kiểm tra listener/gateway có thực sự bắt client cert hay không, alternate route/plaintext fallback và native authorization; xác định chính xác điểm sai.

### Bài 19 — CDN→origin

Browser thấy cert CDN hợp lệ; origin kết nối HTTP không mã hóa qua Internet. Có thể gọi toàn đường “TLS end-to-end” không?

*Đáp án:* không. Cần đánh giá segment giữa CDN và origin, chặn direct-origin bypass và xác minh upstream TLS/trust.

### Bài 20 — Java truststore

Developer thêm một root CA không rõ nguồn vào global Java truststore để sửa PKIX. Vì sao đây là rủi ro?

*Gợi ý:* trust expansion có thể cho CA đó xác nhận nhiều host ngoài ý định. Phải tìm nguyên nhân chain/CA policy và phân phối đúng approved trust material.

### Bài 21 — Dual stack

IPv4 strict HTTPS PASS, IPv6 timeout. Có đủ để khẳng định certificate IPv6 bị sai SAN không?

*Đáp án:* chưa. TLS handshake chưa xảy ra; cần phân biệt IPv6 route/DNS/listener/firewall với certificate validation.

### Bài 22 — Monitoring no-data

Probe certificate hết hạn ngừng chạy trong 24 giờ, dashboard hiện “0 certificate errors”. Đó có phải security PASS không?

*Đáp án:* không. Thiếu quan sát phải hiển thị UNKNOWN và có probe coverage alert.

### Bài 23 — STARTTLS

SMTP relay hỗ trợ STARTTLS nhưng client tự động fallback plaintext khi server không quảng cáo extension. Một phép handshake thành công có đủ chứng minh mail được bảo vệ đúng policy không?

*Gợi ý:* không. Phải kiểm **client/domain transport policy** có yêu cầu TLS và ngăn downgrade khi cần.

### Bài 24 — Negative test đúng điều kiện

Một test sai SAN dùng host không chạy HTTPS, kết quả timeout, rồi ghi PASS vì client không chấp nhận cert. Sai ở đâu?

*Đáp án:* không có cert được trình; failure thuộc network/listener. Cần test lab endpoint khỏe trình cert sai tên để strict validator thực sự reject.

### Bài 25 — Thiết kế tổng hợp

Thiết kế kế hoạch TLS testing cho **public CDN, internal API Java, Kubernetes service mesh mTLS và VPN-only admin portal**. Đề xuất:

- Bốn phép thử **ALLOW**, sáu phép thử **DENY**.
- Những vantage points bắt buộc (IPv4/IPv6/DR/private network).
- Trường chứng cứ cần ghi (SNI, SAN, chain, fingerprint, truststore, TLS version, HTTP outcome).
- Phương án rotation/rollback và chỉ số giám sát.

*Gợi ý:* ALLOW đúng hostname/browser, Java truststore hợp lệ, workload mTLS được phép, VPN admin có quyền; DENY sai SAN, untrusted root, expired test cert, client không có mTLS, mTLS identity sai role, TLS deprecated nếu policy cấm. Với network private, **không mở public endpoint để test**; dùng test client đã được phê duyệt trong đúng trust zone.

## 29. Checklist kiểm tra TLS và certificate endpoint

### 29.1. Quyền kiểm thử và phạm vi

- [ ] Có **asset owner, authorized hostnames/IP/ports, time window và approval** trước active probes.
- [ ] Chỉ thực hiện handshake/benign requests có giới hạn; không quét dải IP, tenants hoặc hosts ngoài scope.
- [ ] Xác định **client runtime, OS, truststore, proxy/VPN route và UTC time** để có thể tái lập.
- [ ] Phân biệt public frontend, private origin, service mesh mTLS và management-plane TLS.
- [ ] Có inventory các **TLS termination points**, SNI virtual hosts, IPv4/IPv6/regions/DR.
- [ ] Negative tests certificate sai/expired/untrusted thực hiện trên **lab CA/test endpoints**, không làm hỏng production.
- [ ] Không đưa private keys, client cert secrets, authorization headers hoặc session tokens vào report.

### 29.2. Identity, SAN và chuỗi tin cậy

- [ ] Strict **hostname verification** bật và được kiểm tra với reference identity thực.
- [ ] Certificate leaf có `subjectAltName` đúng cho **FQDN hoặc IP literal** theo cách client kết nối.
- [ ] Wildcard không được dùng để hợp thức hóa apex/nested subdomains ngoài phạm vi.
- [ ] Không dựa vào CN-only fallback hoặc reverse DNS thay thế SAN verification.
- [ ] SNI gửi đúng hostname và test default-SNI route nếu nằm trong scope.
- [ ] Server gửi **đủ intermediate chain**, path validation và trust anchor đúng profile.
- [ ] Không thêm unknown CA vào global truststore chỉ để giải quyết test failure.
- [ ] Ghi certificate fingerprint SHA-256, issuer, serial, SAN, `NotBefore`, `NotAfter` và chain nguồn.
- [ ] Kiểm tra CA `basicConstraints`, `keyUsage`, `pathLen`, name constraints khi áp dụng.
- [ ] Leaf usages/EKU và public key/signature algorithms đáp ứng TLS client/PKI policy.
- [ ] Client clock/time sync và expiry monitoring đáng tin; có rotation plan trước hạn.

### 29.3. TLS transport và protocol

- [ ] Kết quả **TLS handshake được tách** khỏi TCP connect và HTTP/application success.
- [ ] Negotiated TLS version phù hợp approved baseline, không chỉ version được advertise.
- [ ] TLS 1.2 nếu được phép có cipher suite/key exchange không thuộc tập cấm; TLS1.3 được đánh giá riêng.
- [ ] Các phiên bản/ciphers deprecated bị từ chối hoặc có documented exception/retirement plan.
- [ ] Certificate signature algorithms, public-key strength và key agreement groups được đánh giá theo baseline.
- [ ] Không coi RSA certificate private key là universal decryption key cho TLS1.3/(EC)DHE.
- [ ] ALPN phù hợp HTTP/1.1/2; HTTP/3/QUIC test bằng UDP/QUIC-aware client khi hỗ trợ.
- [ ] STARTTLS được test theo protocol; có policy ngăn plaintext downgrade nếu business yêu cầu.
- [ ] HTTP/application authorization được kiểm thử **sau TLS** bằng identity hợp lệ.
- [ ] Với mTLS: đúng serverAuth/clientAuth, CA profile, client identity, role và denied paths.
- [ ] Với service mesh, xác minh **traffic thực tế qua proxy**, không chỉ cấu hình mTLS ở YAML.

### 29.4. Revocation, CT, trust lifecycle

- [ ] Revocation checking theo **client/trust program policy**, không nhầm `no staple` với `revoked`.
- [ ] OCSP/CRL signatures, freshness, unknown và offline behavior được đánh giá khi policy yêu cầu.
- [ ] Certificate issuance monitoring/CT có owner và phản hồi bất thường, không thay client trust test.
- [ ] DNS CAA được hiểu là issuance policy, không dùng làm browser validation proof.
- [ ] Client truststore/root/intermediate changes có canary và plan cho các runtime cũ.
- [ ] Certificate rotation có kiểm tra **served cert**, không chỉ new cert on disk/config.
- [ ] Certificate/key compromise có incident response, revocation/rotation và audit nếu cần.
- [ ] Mọi exceptions/legacy TLS paths có owner, TTL/expiry và kế hoạch loại bỏ.

### 29.5. Nhiều điểm kết thúc và đường mạng

- [ ] Public CDN/WAF/LB certificate hợp lệ từ external client vantage.
- [ ] CDN→origin/ingress/backend certificate verification **đúng hostname/CA**, không tắt silently.
- [ ] Internal service/mesh identity và trust domains được xác minh riêng, không suy từ edge cert.
- [ ] FQDN nhiều A/AAAA được kiểm thử theo **IPv4/IPv6 route hỗ trợ**.
- [ ] Failover/DR regions/alternate LB instances có served certificate fingerprint/expiry đúng.
- [ ] Split-DNS/VPN/ZTNA/private endpoint được test từ **authorized network identity**, không mở public path.
- [ ] CNI/NetworkPolicy/firewall chặn direct-to-origin hoặc management bypass ngoài policy.
- [ ] Proxy/client CA interception có policy, thông báo, key custody và privacy controls phù hợp.

### 29.6. Test evidence, cảnh báo và hồi quy

- [ ] Mỗi phép thử lưu command/tool version/exit code, SNI/reference identity, truststore profile, UTC và endpoint thực.
- [ ] Có **positive test** với cert đúng và **negative tests** sai SAN, untrusted CA, expired test cert, mTLS unauthorized.
- [ ] PASS/FAIL/INCONCLUSIVE được phân loại theo đúng lớp (network, TLS, trust, authz, application).
- [ ] Không coi timeout/network block là bằng chứng certificate verifier đã reject.
- [ ] Monitoring lấy **served leaf**, expiry, fingerprint, chain/trust result và TLS handshake health.
- [ ] Có cảnh báo **no-data/probe coverage** thay vì mặc định hiển thị 0 lỗi khi collector down.
- [ ] Sau rollback/rotation, strict Browser/Java/SDK clients và IPv4/IPv6/DR được test lại.
- [ ] Nếu cert/key cũ đã revoked/compromised, rollback không đưa hệ thống về trạng thái nguy hiểm.
- [ ] Những dữ liệu trong log/capture được minimization, access controlled và có retention phù hợp.
- [ ] Report cuối cùng nêu **giới hạn test, source of truth, chủ trách nhiệm remediation và lần đánh giá tiếp theo**.

**Kết luận:** một endpoint TLS chỉ đạt yêu cầu khi **client kết nối đúng dịch vụ, xác minh được danh tính trong SAN, xây được chain đến CA đáng tin theo policy, certificate còn hiệu lực và phiên TLS dùng cấu hình được phép**. Trong môi trường hiện đại, kết quả còn phụ thuộc **SNI, IPv4/IPv6, CDN–origin, Java truststores, mTLS và rotation giữa nhiều vùng**. Kiểm tra tốt phải đo **đường ALLOW hợp lệ lẫn đường DENY trái chính sách**, bảo vệ private keys và tránh biến “handshake thành công” hoặc “browser có ổ khóa” thành bằng chứng duy nhất.

## 30. Tài liệu chuẩn và đọc thêm

Các tài liệu sau dùng để tra cứu sâu về giao thức, certificate validation và kiểm thử. Chọn **phiên bản tài liệu phù hợp với client/toolchain đang sử dụng**, đồng thời đối chiếu chính sách bảo mật nội bộ.

### 30.1. Chuẩn TLS, X.509, certificate identity

- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake, certificate authentication, traffic secrets và record protection.
- [RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246): mô hình handshake/cipher suites của TLS 1.2.
- [RFC 9325 — Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325): hướng dẫn thiết kế TLS/DTLS bảo mật hiện đại.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): path validation, constraints, usages, validity và revocation.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): xác minh hostname/service identities bằng certificate.
- [RFC 6066 — Transport Layer Security Extensions](https://www.rfc-editor.org/rfc/rfc6066): SNI và một số TLS extensions.
- [RFC 7301 — TLS Application-Layer Protocol Negotiation Extension](https://www.rfc-editor.org/rfc/rfc7301): ALPN.
- [RFC 6960 — X.509 Internet Public Key Infrastructure Online Certificate Status Protocol](https://www.rfc-editor.org/rfc/rfc6960): OCSP.
- [RFC 6962 — Certificate Transparency](https://www.rfc-editor.org/rfc/rfc6962): nền tảng CT logs và các khái niệm kiểm toán issuance.
- [RFC 8659 — DNS Certification Authority Authorization (CAA) Resource Record](https://www.rfc-editor.org/rfc/rfc8659): DNS CAA trong kiểm soát cấp certificate.
- [RFC 9001 — Using TLS to Secure QUIC](https://www.rfc-editor.org/rfc/rfc9001): QUIC TLS 1.3 handshake/key protection.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114): HTTP semantics trên QUIC.

### 30.2. Công cụ và hướng dẫn vận hành

- [OpenSSL — s_client manual](https://docs.openssl.org/master/man1/openssl-s_client/): SNI, hostname verification, CA, protocol, OCSP, ALPN.
- [OpenSSL — verify manual](https://docs.openssl.org/master/man1/openssl-verify/): certificate path validation, CAfile, untrusted intermediate và policy.
- [OpenSSL — x509 manual](https://docs.openssl.org/master/man1/openssl-x509/): certificate fields, SAN, fingerprint, validity và extensions.
- [curl — SSL Certificates](https://curl.se/docs/sslcerts.html): CA trust backend, client-side certificate verification và `--cacert`.
- [curl — Command line options](https://curl.se/docs/manpage.html): `--resolve`, `--http3-only`, client cert/key, TLS verification và timing.
- [Oracle Java — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): Java secure socket, TLS trust/key managers, providers và debugging.
- [Wireshark User's Guide](https://www.wireshark.org/docs/wsug_html_chunked/): TLS packet analysis, handshake visibility và protocol dissection.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): kết hợp phân đoạn mạng với mTLS/service policy.

### 30.3. Hướng dẫn bảo mật và quản lý vòng đời

- [NIST SP 800-52 Rev. 2 — Guidelines for the Selection, Configuration, and Use of TLS Implementations](https://csrc.nist.gov/pubs/sp/800/52/r2/final): lựa chọn/cấu hình TLS theo yêu cầu NIST, cần so chuẩn hiện hành và phạm vi sử dụng.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS configuration, certificate và application security considerations.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): private key lifecycle, storage và quyền truy cập.
- [CISA — Zero Trust Maturity Model](https://www.cisa.gov/zero-trust-maturity-model): identity/device/workload controls bổ trợ TLS.
- [NIST SP 800-61 Rev. 3 — Incident Response Recommendations](https://csrc.nist.gov/pubs/sp/800/61/r3/final): điều tra và xử lý key/certificate compromise trong incident response.
