# 16.11. Chẩn đoán SSLHandshakeException, lỗi chứng thư và lỗi không có cấu hình chung

**`SSLHandshakeException` không phải một lỗi duy nhất.** Đây là một lớp exception Java thường gặp khi hai phía không thể hoàn tất SSL/TLS handshake. Nguyên nhân có thể là **không tin certificate**, **certificate hết hạn hoặc sai hostname**, **không có phiên bản TLS dùng chung**, **không có cipher suite được phép ở cả hai phía**, **server không có certificate/key phù hợp**, **mTLS client thiếu chứng thư**, hoặc **bất đồng signature schemes, named groups, SNI/ALPN và chính sách bảo mật**.

Đọc mỗi dòng `javax.net.ssl.SSLHandshakeException: handshake_failure` rồi kết luận “server bị lỗi SSL” là thiếu căn cứ. Ngược lại, thấy `PKIX path building failed` rồi “sửa” bằng một `TrustManager` chấp nhận mọi chứng thư là một lỗi an ninh nghiêm trọng: ứng dụng có thể kết nối được, nhưng mất khả năng xác thực đúng đối tác và dễ bị người đứng giữa (MITM).

**Quy tắc của bài:** luôn chẩn đoán theo thứ tự **đúng endpoint → đúng giai đoạn handshake → đúng chuỗi nguyên nhân (cause chain) → đúng cấu hình hai bên → đúng trust/identity → mới quyết định cách sửa**. Chẩn đoán không đồng nghĩa với việc nới lỏng security policy. Tên exception/alert có thể khác tùy Java version, TLS version, provider, proxy và phía phát hiện lỗi; dùng nhiều dấu hiệu kết hợp, không đoán chỉ từ một message.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài này, bạn có thể:

- Phân biệt lỗi **network/DNS/TCP**, lỗi **TLS handshake**, lỗi **certificate path/hostname** và lỗi **HTTP/application sau handshake**.
- Hiểu vị trí của `SSLHandshakeException` trong JSSE và cách lần theo `Throwable.getCause()`, `CertificateException`, `CertPathValidatorException`, `CertificateExpiredException` và các loại lỗi liên quan.
- Nhận diện lỗi “no common configuration” ở **TLS protocol versions, cipher suites, signature algorithms, supported groups/key shares, certificate/key types, ALPN, SNI và client authentication**.
- Bật tracing JSSE vừa đủ bằng `-Djavax.net.debug=ssl,handshake,trustmanager,keymanager` và cert-path tracing bằng `-Djava.security.debug=certpath`; hiểu giới hạn và nguy cơ dữ liệu nhạy cảm trong log.
- Dùng `keytool` và Java API đọc **cấu hình keystore/truststore, certificate chains, SAN, validity, KeyUsage, EKU** mà không biến certificate không tin cậy thành trusted root.
- Dùng `SSLContext`, `SSLEngine`, `SSLParameters` để kiểm tra capability và cấu hình trước handshake, nhưng không nhầm **supported** với **enabled** và **được negotiated**.
- Chạy chương trình Java 17+ có output xác minh được, phân loại một nguyên nhân certificate lỗi trong ví dụ tổng hợp và nhận diện hai cấu hình không có phần giao.
- Lập runbook bảo mật cho client/server/mTLS, reverse proxy, CA nội bộ, rotation và môi trường dev/staging/production.

## 2. Đọc đúng từ phía nào, ở tầng nào?

Trước khi chỉnh sửa TLS, hãy xác định **người phát hiện lỗi** và **kênh truyền cụ thể**.

```text
Java client            Reverse proxy / API gateway             Java backend
-----------            ---------------------------             ------------
DNS / TCP connect -->
                      TLS connection #1 may terminate here
                      HTTPS request -->
                               TCP/TLS connection #2 -------->
                                                  JSSE handshake may occur here
                                                  Application logic / HTTP
```

Một lỗi từ Java client tới gateway có thể xảy ra trước khi backend nhận request. Một lỗi mTLS giữa gateway và service khác có thể không xuất hiện trong Java client log. Nếu HTTP đã trả `401`/`403`/`500` qua một TLS connection hợp lệ thì thường **không phải** chứng cứ TLS handshake giữa hai phía đó thất bại.

Bảng định vị nhanh:

| Dấu hiệu | Tầng thường liên quan | Câu hỏi tiếp theo |
| --- | --- | --- |
| `UnknownHostException` | DNS/name resolution | Tên host có đúng? DNS/proxy/container khác môi trường? |
| `ConnectException: Connection refused` | TCP connect | Port/server listener/firewall có chạy? |
| `SocketTimeoutException` lúc connect/read | Network hoặc handshake/read bị treo | Timeout ở giai đoạn nào? Có nhận ServerHello không? |
| `SSLHandshakeException` | TLS handshake/authentication | Cause chain? Alert đến từ peer hay do local JSSE tạo? |
| `SSLProtocolException` | TLS protocol/framing | Alert/version/record nào? Có non-TLS data trên port? |
| `SSLPeerUnverifiedException` | Xác thực peer ở ngữ cảnh TLS | Chứng thư/peer identity có hiện diện/được verify không? |
| `CertificateException` / `CertPathValidatorException` trong cause | Certificate trust/validity/policy | Thiếu CA, lỗi thời gian, sai chain hay revocation? |
| HTTP `401/403` | Application auth/authz | TLS đã pass nhưng token/role/tenant không hợp lệ? |
| HTTP `502/503` từ proxy | Proxy/upstream health | Proxy có gặp TLS failure khi kết nối backend không? |

Đừng mặc định mọi `SSLException` xảy ra ở bước bắt tay: một connection có thể đã bắt tay xong rồi mới gặp lỗi record/EOF/alert, session resumption hoặc I/O. Ngay cả handshake cũng có thể khởi tạo khi lần đầu đọc/ghi, tùy API; muốn biết chính xác giai đoạn phải quan sát JSSE log hoặc đặt instrumentation tại `SSLSocket.startHandshake()`/`SSLEngine`.

### 2.1. Exception và TLS alert có nguồn khác nhau

Ví dụ:

```text
javax.net.ssl.SSLHandshakeException: Received fatal alert: handshake_failure
```

thường nói Java **nhận một alert từ peer**, nhưng peer phát alert vì nguyên nhân gì cần xem **log phía peer** hoặc capture handshake để biết. Không đủ căn cứ kết luận lỗi certificate hay cipher suite từ message chung này.

Ngược lại:

```text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed: ...
Caused by: sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
```

thường cho thấy phía Java **không xây được đường tin cậy** tới anchor phù hợp. Đây là ví dụ dạng thông báo, **không phải một contract chuẩn hóa**; lớp nội bộ `sun.security...` có thể thay đổi, không import hay phụ thuộc vào nó trong code.

**Luôn ghi nhận:** host/port thực sự, TLS termination point, Java/JDK version, provider, đường truststore/keystore theo cấu hình, expected hostname, thời điểm, full/resumed handshake và message **đầu tiên** chỉ nguyên nhân thay vì chỉ xem hàng trăm dòng cascade phía sau.

## 3. Các giai đoạn TLS handshake giúp khoanh vùng lỗi

Một certificate-based TLS 1.3 handshake thông thường:

```text
Client                                                  Server
------                                                  ------
ClientHello (supported_versions, suites, SNI,
             key_share/groups, sig_algs, ALPN) -------->
                                        <--------------- ServerHello
                                        <--------------- EncryptedExtensions
                                        <--------------- Certificate
                                        <--------------- CertificateVerify
                                        <--------------- Finished
Client validates certificate path, hostname and
handshake authentication; key schedule finishes
Finished ---------------------------------------------->
              <====== encrypted application data ======>
```

**Sơ đồ khái niệm:** handshake có thể khác khi dùng PSK resumption, mutual TLS, HelloRetryRequest hoặc policy khác. Không phải mọi TLS 1.3 connection đều có đầy đủ `Certificate`/`CertificateVerify`, và nhiều handshake messages sau `ServerHello` đã được mã hóa.

Từ đó suy luận:

- **Không thấy ServerHello:** kiểm tra ClientHello có ra khỏi client không, server/port có nói TLS không, gateway/firewall có chặn không, protocol/version/suite/key-share có giao được không. Có thể server abort sớm vì SNI hoặc cipher policy.
- **Đến Certificate rồi fail:** ưu tiên certificate chain, trust anchor, thời hạn, SAN/hostname, algorithm constraints, key usage, revocation và mTLS nếu liên quan.
- **CertificateVerify/Finished fail:** có thể liên quan chữ ký handshake, private key, transcript/parameters hoặc implementation/proxy; cần provider logs ở đúng phía.
- **TLS Finished xong rồi HTTP trả lỗi:** không sửa truststore để chữa lỗi token/route/authorization.
- **Client nhận fatal alert sau khi gửi client certificate:** kiểm tra phía server mTLS trust/certificate policy, không chỉ truststore của client.

### 3.1. Lỗi ở bên nhận hay bên gửi?

Nếu client ghi `Received fatal alert: certificate_unknown`, có thể **server** đã từ chối certificate client của mTLS; nếu server ghi tương tự, có thể **client** đã từ chối certificate server. Cần biết phía nào phát alert và handshake stage nào.

`handshake_failure`, `bad_certificate`, `certificate_unknown`, `unknown_ca`, `protocol_version`, `no_application_protocol` là các alert/concept hữu ích, nhưng **không có ánh xạ một-một tuyệt đối từ alert sang một root cause**. Một implementation có thể dùng alert chung cho nhiều lỗi cục bộ.

## 4. Cách đọc nguyên nhân `SSLHandshakeException` có hệ thống

Không dùng một `contains("PKIX")` đơn lẻ làm cơ sở sửa môi trường. Hãy tách:

1. **Top-level exception:** tên class Java và message giới hạn.
2. **Cause chain:** từ `getCause()` tới nguyên nhân sâu nhất, kể cả `CertificateException`/`CertPathValidatorException`.
3. **TLS debug sequence:** ClientHello, ServerHello, certificate, trust validation, alert/handshake failure.
4. **Peer-side log:** server có certificate/key nào, có yêu cầu client certificate không, có từ chối suite/group/ALPN không?
5. **Config provenance:** cờ JVM, biến môi trường, truststore/keystore thực tế, framework overrides, reverse proxy.
6. **Security policy:** liệu sửa có giữ nguyên peer identity và thuật toán được phép không?

Một cấu trúc để ghi nhận sự cố mà không ghi secret:

```text
incidentId: 6ef4f9c2          # mã ví dụ không nhạy cảm
direction: Java client -> api.example.com:443
TLS termination: gateway-1
JDK runtime: Java 17 / provider SunJSSE
expected service identity: api.example.com
TLS configured: versions [TLSv1.3, TLSv1.2]
stage: received Certificate, path validation failed
top exception: SSLHandshakeException
cause category: CERT_PATH_UNTRUSTED
observed result: fail closed
last known good: deployment/config revision X
```

Đừng đưa `Authorization`, cookies, passwords, private keys, session tickets, application payload hoặc full TLS secrets vào ticket/log để “đủ dữ liệu”. Chẩn đoán mạnh nhất thường dùng **metadata, policy, certificate public fields và cause classes**, không cần xuất secrets.

### 4.1. Phân biệt root cause với triệu chứng cascade

Một dòng debug `Fatal (CERTIFICATE_UNKNOWN)` sau khi JSSE đã ghi `PKIX path building failed` thường là **hậu quả của thất bại trust validation**. Đừng chỉ tìm dòng `Fatal` cuối cùng. Tương tự, `Broken pipe` ở server sau khi client đã reject certificate không phải chứng cứ server có cấu hình cipher sai.

Một flow hiệu quả:
- Ghi lại **fatal đầu tiên** và **exception gây ra nó**.
- Đối chiếu thời điểm/log của **cả hai bên** bằng correlation ID hoặc timestamp.
- Xác minh error có lặp lại cho nhiều endpoints hay chỉ một host/SNI.
- So sánh với phiên bản cấu hình đang hoạt động tốt trước đó, không sao chép file keystore/truststore tùy tiện.
- Chỉ thay một nhóm cấu hình tại một thời điểm, chạy lại negative tests.

## 5. Nhóm 1 — Lỗi certificate và đường tin cậy

### 5.1. `PKIX path building failed`

Dạng thường gặp:

```text
SSLHandshakeException: PKIX path building failed
  ...
  unable to find valid certification path to requested target
```

Nguyên nhân khả dĩ:
- Client **không tin** CA root hoặc intermediate cần thiết cho server certificate.
- Server không gửi đủ intermediate certificates, client không xây được path.
- Java runtime/container dùng truststore khác OS/browser; CA mà trình duyệt tin chưa chắc JDK trust.
- App chỉ đến file truststore sai hoặc truststore bị rỗng/không đọc được.
- TLS inspection proxy/corporate gateway phát certificate từ một CA nội bộ chưa được app tin theo chính sách.
- Chain có issuer mismatch, signature mismatch, policy constraints hoặc algorithm không được phép.
- JDK cũ/CA set chưa phù hợp hệ PKI mới, hoặc khác nhau giữa staging/production.

**Bước sửa đúng:** xác định **CA issuer/chain thực tế**, xác minh nguồn public CA/enterprise CA bằng kênh quản trị đáng tin, sửa chain phía server hoặc cập nhật truststore **có kiểm soát**. Không tự “import certificate vừa nhận từ server vào truststore” mà chưa xác minh; điều đó có thể biến certificate attacker thành trusted root.

### 5.2. `trustAnchors parameter must be non-empty`

Tình huống này thường cho thấy **tập trust anchors dùng cho PKIX rỗng** hoặc configuration tạo validator không có CA tin cậy. Cần kiểm tra:
- File truststore có tồn tại/được đọc không?
- Kiểu store: PKCS12/JKS/PKCS11 theo policy và provider?
- Password/cấu hình truststore có phù hợp không?
- File có chứa certificate entries đã được phê duyệt hay không?
- Code có khởi tạo `TrustManagerFactory` với một `KeyStore` mới rỗng rồi vô tình dùng cho mọi HTTPS connection?
- Container có mount chính xác truststore vào runtime không?

**Không** sửa bằng cách thêm root không rõ nguồn hoặc tạo `TrustManager` bỏ qua kiểm tra.

### 5.3. Certificate hết hạn hoặc chưa có hiệu lực

```text
java.security.cert.CertificateExpiredException
java.security.cert.CertificateNotYetValidException
```

Chứng thư hoặc thành phần chain có khoảng `notBefore/notAfter` không phù hợp thời điểm kiểm tra. Hãy đối chiếu:
- UTC/clock của JVM/host/container và NTP.
- Thời gian của leaf và intermediate.
- Dịch vụ có vẫn gửi certificate cũ sau rotation không?
- Load balancer nhiều node có cert khác nhau không?
- Certificate policy có yêu cầu revocation/short-lived credentials không?

**Không sửa bằng cách đặt lại system clock sai hoặc bỏ `checkValidity()` trong production.** Đồng bộ thời gian và renew/rollout certificate chính xác.

### 5.4. Sai SAN hoặc hostname

Ví dụ:

```text
No subject alternative DNS name matching api.example.com found
No name matching api.example.com found
No subject alternative names present
```

Dạng message tùy provider. Nếu app gọi `api.example.com` nhưng cert chỉ có `db.example.com` hoặc CN/SAN không hợp lệ, phải **từ chối** dù chain CA trusted.

Cách kiểm tra:
1. Xác định expected hostname từ URL/service discovery đã tin.
2. Đọc `SubjectAlternativeName` loại DNS/IP tương ứng.
3. Kiểm tra SNI mà client gửi có đúng, server virtual host có chọn cert đúng không.
4. Với IP literal, xem `iPAddress` SAN và policy matching; không giả định DNS SAN đủ.
5. Sửa certificate/SNI/routing theo thực tế; không tắt hostname verification.

Nếu app gọi qua IP nội bộ nhưng certificate chỉ có public DNS, giải pháp là **kết nối tới tên được chứng nhận** với DNS/routing phù hợp hoặc cấp certificate hợp lệ cho identity mong muốn, không tự đặt HostnameVerifier luôn true.

### 5.5. Certificate chain đúng chữ ký nhưng sai chính sách

Các trường hợp:
- `BasicConstraints: CA=false` ở certificate dùng làm intermediate CA.
- CA thiếu `keyCertSign` khi policy/KeyUsage yêu cầu.
- Leaf certificate sai `ExtendedKeyUsage`, ví dụ chỉ được dùng `clientAuth` nhưng đem làm `serverAuth`.
- Certificate có critical extension không được hiểu/đáp ứng.
- `NameConstraints` giới hạn tên không phù hợp.
- Thuật toán ký/khóa quá yếu theo `jdk.certpath.disabledAlgorithms` và algorithm constraints của runtime.
- Không vượt qua policy revocation (CRL/OCSP) khi được yêu cầu.

Gọi `cert.verify(issuerPublicKey)` chỉ kiểm tra **chữ ký trên certificate**; nó không phải một hệ thống PKIX trust validation hoàn chỉnh. Đừng dùng kết quả verify đơn lẻ để đánh dấu trusted.

### 5.6. Revocation/OCSP/CRL

Chứng thư có thể **còn hạn** và chữ ký đúng nhưng **đã bị thu hồi**. Kiểm tra policy của PKIX/trust manager/OCSP, khả năng truy cập responder, thời hạn CRL, stapling, timeout và fail-closed/soft-fail theo quy định của hệ thống. Không mặc định “gặp lỗi OCSP thì tắt revocation là xong”. Một số deployment dùng chứng thư sống ngắn và cơ chế rotation thay thế hoặc bổ sung kiểm tra revocation; mọi lựa chọn cần threat model.

## 6. Truststore và keystore: hai vai trò khác nhau

| Kho/cấu hình | Giữ gì? | Dùng để làm gì? | Nếu cấu hình sai |
| --- | --- | --- | --- |
| **Truststore** | CA/anchors hoặc chứng thư được tin theo policy | **Xác minh certificate của bên kia** | `PKIX path building failed`, unknown CA, trust anchors rỗng |
| **Keystore / key entry** | Private key của chính bên này + certificate chain tương ứng | **Chứng minh danh tính của mình** khi handshake yêu cầu | No available authentication scheme, missing client cert, server cannot present cert |
| **JDK security policy** | Protocol/algorithm constraints | Loại bỏ thuật toán hoặc khóa yếu | No common config dù có suite trên danh sách supported |
| **SSLContext/JSSE config** | KeyManagers, TrustManagers, SecureRandom, protocol state | Tạo TLS engine/sockets | Dùng nhầm store, override mặc định, không có key |
| **SNI/endpoint config** | Service identity cần kết nối | Chọn virtual host/certificate, xác minh hostname | Wrong cert, hostname failure |

### 6.1. Client kết nối HTTPS thường chỉ cần truststore

Nếu Java là **HTTPS client**, nó cần tin certificate server; thông thường không cần certificate của chính client trừ khi server yêu cầu **mutual TLS (mTLS)**.

- Client truststore: CA kiểm tra certificate server.
- Client keystore: private key/cert của client **nếu** mTLS.
- Server keystore: private key/cert của server.
- Server truststore: CA kiểm tra client certificate **nếu** mTLS.

Câu “Tôi đã import CA vào keystore mà client vẫn báo PKIX” có thể do **import vào kho sai vai trò** hoặc app không sử dụng chính file đó.

### 6.2. Default truststore và custom truststore

Trong SunJSSE/JDK, trust material mặc định thường đến từ JSSE truststore configuration, ví dụ `javax.net.ssl.trustStore` nếu được khai báo, hoặc các location mặc định của runtime như `jssecacerts`/`cacerts` tùy provider và cấu hình. **Đừng giả định JVM chắc chắn đọc OS certificate store** hoặc file của một JDK khác.

Một file `-Djavax.net.ssl.trustStore=/app/config/truststore.p12` sai đường dẫn có thể dẫn tới trust không như kỳ vọng; cần xác minh trực tiếp file tồn tại, nội dung, quyền đọc và runtime nào đang chạy.

Nếu dùng custom `SSLContext`:
- `TrustManagerFactory.init(customTrustStore)` thay đổi nguồn anchors của context đó; nó không tự “merge” mọi CA của hệ điều hành/JDK.
- `KeyManagerFactory.init(keyStore, ...)` cấp khả năng trình certificate/key của chính bên này.
- `SSLContext.init(keyManagers, trustManagers, secureRandom)` kết hợp những quyết định trên.
- Một framework có thể tạo `SSLContext` riêng và bỏ qua JVM-wide properties; hãy kiểm tra thực tế context của từng HTTP client.
- Khi cần kết hợp CA nội bộ với CA công khai, hãy quản lý trust policy tường minh, không thêm CA không tin cậy tùy tiện.

### 6.3. Phân biệt key password và store password

`KeyStore.load(...)` dùng store password, còn private key entry có thể có key password/PKCS12 settings khác theo provider. Sửa “không đọc được private key” bằng cách dùng password truststore thay key password mà không hiểu cấu trúc có thể vẫn fail.

Không truyền password production trong command-line flags dễ bị ghi vào process-list, shell history, CI log. Dùng secret manager và API/cơ chế triển khai được phê duyệt; kiểm soát file permissions và audit.

## 7. Nhóm 2 — Không có cấu hình TLS chung (no common configuration)

Ngay cả khi certificates đều có thể tin, hai bên vẫn phải **thương lượng được** phiên bản TLS, thuật toán trao đổi khóa, chữ ký và cipher suite phù hợp.

### 7.1. Không có chung protocol version

Client chỉ bật `TLSv1.3`, server chỉ bật `TLSv1.2`:

```text
Client enabled protocols: [TLSv1.3]
Server enabled protocols: [TLSv1.2]
Intersection: EMPTY
Result: handshake cannot select common TLS version
```

Có thể thấy `protocol_version`, `handshake_failure`, `No appropriate protocol` hoặc thông báo khác. Không khẳng định một thông báo duy nhất sẽ xuất hiện ở mọi provider.

Điểm phân biệt:
- **Supported**: provider có khả năng hỗ trợ nếu chính sách cho phép.
- **Enabled**: danh sách cấu hình cho instance, ví dụ `SSLEngine.getEnabledProtocols()`.
- **Negotiated**: phiên bản được chọn **sau handshake**, có thể xem từ `SSLSession.getProtocol()`.
- **Disabled by security policy**: phiên bản tồn tại trong provider nhưng bị cấm qua cấu hình như `jdk.tls.disabledAlgorithms`.

Nếu server chỉ còn TLS 1.0/1.1, không nên bật những protocol yếu đó trong client production để “nối được”. Cần nâng cấp server/gateway và tuân thủ policy hiện hành.

### 7.2. Không có chung cipher suite

```text
Client enabled suites: [TLS_AES_128_GCM_SHA256]
Server enabled suites: [TLS_CHACHA20_POLY1305_SHA256]
Intersection: EMPTY
```

Đây là một ví dụ cấu hình **cố ý không giao nhau**. Chưa xét suite có được provider cụ thể hỗ trợ hay được security policy cho phép không; nếu hai bên chỉ cấu hình như trên, không có suite chung để chọn.

Trường hợp thực tế:
- Client/server không có suite được phép trùng nhau.
- Có suite chung trên giấy nhưng policy `jdk.tls.disabledAlgorithms` hoặc provider không cho dùng.
- TLS 1.2 suite yêu cầu một loại certificate/key exchange không có trong server keystore.
- Security gateway bỏ suite/curve theo policy, service runtime vẫn dùng cấu hình cũ.

### 7.3. Đặc điểm TLS 1.3: suite không kể hết handshake

TLS 1.3 cipher suite như `TLS_AES_128_GCM_SHA256` hoặc `TLS_AES_256_GCM_SHA384` mô tả chủ yếu thuật toán AEAD và HKDF hash. Nó **không tự chỉ định** server dùng RSA certificate, ECDSA certificate, Ed25519 signature hay nhóm ECDHE nào.

Vì vậy, sau khi xác nhận có cipher suite chung, vẫn cần xét:
- **Signature schemes:** `signature_algorithms` từ client và những thuật toán signer/server certificate hỗ trợ.
- **Supported groups/named groups:** nhóm X25519, P-256, P-384... theo policy.
- **Key shares:** có thể có `HelloRetryRequest` khi cần nhóm khác; nếu không có nhóm dùng chung, handshake fail.
- **Certificate/key algorithm:** server có private key và certificate chain phù hợp lựa chọn.
- **ALPN:** giao thức ứng dụng `h2`/`http/1.1` hoặc profile khác có được hai bên cho phép không.
- **SNI:** tên máy chủ dùng để chọn đúng certificate/vhost/backend.

Không giải thích toàn bộ lỗi TLS 1.3 bằng câu “cipher suite không chung” khi nguyên nhân có thể là **chữ ký hoặc key share**.

### 7.4. `No available authentication scheme`

JSSE/peer có thể báo lỗi kiểu:

```text
No available authentication scheme
No available certificate corresponding to the SSL cipher suites...
```

Đừng vội kết luận CA không tin. Ở **server side**, nó thường gợi ý không có certificate/private key phù hợp các thuật toán/schemes mà peer chấp nhận, hoặc key manager không chọn được alias đúng.

Kiểm tra:
1. `KeyManagerFactory` đã nạp đúng keystore?
2. Keystore có **PrivateKeyEntry** chứ chỉ là **trustedCertEntry**?
3. Certificate chain và private key có đi cùng nhau?
4. Key type RSA/EC/EdDSA, signature schemes, KeyUsage/EKU có được JSSE hỗ trợ và policy cho phép?
5. SNI đang yêu cầu virtual host nào, key manager chọn alias ra sao?
6. Java provider có hỗ trợ thuật toán key và signature phù hợp không?
7. Client có đang yêu cầu cấu hình chỉ hỗ trợ một scheme server không có không?

Với **mTLS client side**, cũng có thể không có client certificate phù hợp yêu cầu `CertificateRequest` của server. Hãy xem `keymanager` trace của client và trust policy của server.

### 7.5. `Handshake failure` vẫn có thể là ALPN/SNI issue

- Server dùng SNI để chọn certificate hoặc routing; nếu client không gửi tên host phù hợp, server có thể trả default certificate **không khớp SAN** hoặc từ chối.
- ALPN cho phép chọn protocol ứng dụng như `h2` hoặc `http/1.1`. Nếu policy yêu cầu một protocol mà không có phần giao, server có thể gửi alert như `no_application_protocol`.
- Một HTTP server có thể chấp nhận TLS handshake nhưng application protocol sau đó bị hiểu sai; đừng trộn lỗi HTTP 2 framing với PKIX.
- Proxy có thể terminate TLS, gửi request lên upstream với SNI/ALPN khác endpoint gốc; cần kiểm tra cấu hình ở đúng hop.

## 8. Nhóm 3 — mTLS: lỗi chứng thư phía client

Khi server yêu cầu client certificate:
- Server gửi tín hiệu yêu cầu certificate theo handshake TLS đang dùng.
- Client `KeyManager` phải tìm được cert/private key phù hợp với issuer/signature schemes/policy.
- Client trình certificate và thực hiện handshake proof tương ứng.
- Server `TrustManager` kiểm tra certificate chain/clientAuth constraints.
- Ứng dụng còn phải map certificate identity sang principal/tenant/role và làm authorization.

### 8.1. Những tình huống thường gặp

| Triệu chứng | Bên cần quan sát | Nguyên nhân khả dĩ |
| --- | --- | --- |
| Server báo `certificate_required` | Client và server | Client không gửi certificate khi server yêu cầu |
| Server báo `unknown_ca` hoặc cert-path error | Server trust config | CA phát client cert chưa được server tin |
| Client log `Received fatal alert: bad_certificate` | Server quyết định | Client certificate/usage/chain không đạt server policy |
| Client keymanager không chọn alias | Client | Không có PrivateKeyEntry/issuer/key type phù hợp |
| Handshake pass nhưng API 403 | Application server | Certificate identity không có quyền, không phải PKIX error |
| Một số nodes mTLS pass, một số fail | Gateway/backend fleet | Truststore, CA rollout hoặc cert rotation chưa đồng bộ |

**Truststore của Java client dùng xác minh server** khác **truststore của server dùng xác minh client**. Import CA client vào truststore của chính client thường không giúp server tin client certificate.

### 8.2. Client có cert không có nghĩa server chấp nhận

Phải xem:
- Certificate chain đầy đủ và issuer mà server chấp nhận.
- Private key matching certificate.
- EKU `clientAuth`, KeyUsage và validity.
- Certificate DN/SAN mapping tới workload identity được phép.
- CA/root và revocation policy phía server.
- TLS signature algorithms/grouplist/certificate request context.

Đừng bật mTLS bằng cách tắt server validation để client kết nối được; nó đổi từ authenticated client/server thành một kết nối dễ bị MITM.

## 9. JSSE debugging: bật đúng công tắc, đọc đúng giai đoạn

Đây là công cụ chính để chẩn đoán Java TLS trong môi trường kiểm thử được kiểm soát.

### 9.1. JSSE debug flags

Ví dụ command-line (dùng tên class ứng dụng của bạn):

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager,keymanager MyTlsApp
```

Các nhóm debug phổ biến:
- `ssl`: SSL/TLS debug chung.
- `handshake`: các handshake messages và quá trình thương lượng.
- `trustmanager`: dấu vết trust manager và certificate validation theo implementation.
- `keymanager`: chọn key/certificate của chính endpoint.
- `session` hoặc `sessioncache`: hỗ trợ tìm hiểu resumption/cache khi cần.
- `record`: thông tin TLS records; cân nhắc dữ liệu được log.

Để xem các lựa chọn được **JDK đang chạy** hỗ trợ, có thể dùng:

```bash
java -Djavax.net.debug=help MyTlsApp
```

Tùy provider, chế độ này có thể hiển thị help và dừng ứng dụng. Không giả định log format là một API ổn định: Oracle lưu ý các diagnostic options có thể thay đổi và provider khác SunJSSE có thể không hỗ trợ cùng cách.

**Cảnh báo:** không bật mặc định `all`, `plaintext`, `packet` hoặc các chế độ dump bytes cho hệ thống production có dữ liệu thật. Traces có thể lộ certificate metadata, session identifiers, handshake content, hostname/tenant và thông tin nhạy cảm khác; cần access controls, retention và redaction.

### 9.2. CertPath debug flags

Khi gặp `PKIX path building failed` hoặc algorithm/chain constraints:

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager -Djava.security.debug=certpath MyTlsApp
```

`java.security.debug=certpath` cung cấp dấu vết liên quan PKIX path building/validation trong Sun security provider khi tương ứng. Các bản JDK có thể khác format và lượng thông tin. Không cần bật certpath cho mọi lỗi như TCP refused hoặc ALPN mismatch.

### 9.3. Cách đọc JSSE trace hữu ích

Một trình tự đọc:

1. **ClientHello**: TLS versions được đề xuất, cipher suites, `signature_algorithms`, `supported_groups`, `key_share`, SNI và ALPN.
2. **ServerHello** nếu có: version/suite được chọn, key share/PSK hoặc HelloRetryRequest.
3. **Certificate/CertificateRequest** (nếu có): chain server, mTLS yêu cầu client cert.
4. **Trust/key manager log**: CA anchors đã load, alias/certificate được chọn; path failure/hostname mismatch.
5. **Fatal alert trước nhất**: tên alert, phía gửi/nhận và cause.
6. **Application data**: nếu đã tới đây, TLS ban đầu có thể đã thành công, kiểm tra lỗi ở tầng khác.
7. **Đối chiếu server-side trace**: đặc biệt khi client chỉ thấy `Received fatal alert: handshake_failure`.

Không sao chép toàn bộ debug log vào email/ticket công khai. Chỉ trích những trường đủ khoanh vùng lỗi, loại bỏ token/cookie, thông tin cá nhân, secret, key share/debug bytes không cần thiết.

### 9.4. Trước khi tăng debug level

Kiểm tra những thứ đơn giản ít xâm phạm:
- `java -version` và JDK thực sự đang chạy trong container.
- URL/hostname/port, TLS termination point, proxy, gateway route.
- Cờ startup liên quan `javax.net.ssl.trustStore`/`keyStore`/`https.protocols`/`jdk.tls.client.protocols`, nhưng cẩn trọng flag nào áp cho API/provider nào.
- Security properties như `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms`.
- File truststore/keystore thực sự đọc được, permissions, cert chain, alias.
- Time synchronization, certificate expiration, SAN, certificate rotation status.
- Server version/certificate policy, mTLS requirements và SNI/ALPN selection.

Một số thuộc tính nằm trong file `java.security` của JDK hoặc được override qua cơ chế JVM; đừng suy từ một máy dev rằng production container có security policy giống hệt.

## 10. `keytool`: kiểm tra chứng thư và stores mà không làm mất trust model

Các lệnh sau để **đọc/kiểm tra**, không tự thêm CA hoặc làm yếu TLS.

### 10.1. Quan sát certificate server

```bash
keytool -printcert -sslserver api.example.com:443 -rfc
```

Lệnh có thể hiển thị certificate được server trình trên kết nối tới host/port, tùy network và tool. **Certificate được in ra không đồng nghĩa certificate đã được tin cậy**; cần kiểm tra chain/trust anchor/expected hostname bằng TLS client chuẩn. Với vhost phức tạp, kiểm tra SNI/tooling tương thích để chắc chắn đã thấy đúng certificate.

### 10.2. Đọc certificate file

```bash
keytool -printcert -file server-certificate.pem
```

Xem:
- Subject/Issuer.
- Validity Not Before/Not After.
- Subject Alternative Name (DNS/IP names).
- KeyUsage, ExtendedKeyUsage.
- BasicConstraints/CA flag.
- SHA-256 fingerprint **sau khi xác minh nguồn đáng tin**.

Fingerprint chỉ giúp so sánh nếu có reference value từ kênh xác thực khác. Nếu attacker đưa certificate cùng fingerprint tính từ chính certificate ấy qua một kênh không tin cậy, phép so sánh không chứng minh ownership.

### 10.3. Kiểm tra truststore (ví dụ PKCS12)

```bash
keytool -list -v -keystore truststore.p12 -storetype PKCS12
```

Lệnh có thể yêu cầu password tương tác. Kiểm tra certificate entries/issuers và có đúng CA được cấp phép chưa. **Không** vội nhập password vào dòng lệnh hoặc CI log; đường dẫn ở đây chỉ là ví dụ.

### 10.4. Kiểm tra keystore chứa identity

```bash
keytool -list -v -keystore identity.p12 -storetype PKCS12
```

Điểm cần tìm:
- Alias mong muốn có loại `PrivateKeyEntry`, không chỉ `trustedCertEntry`.
- Certificate chain đi kèm private key.
- Thuật toán/độ dài key, chữ ký, EKU/KeyUsage, SAN và validity.
- Với mTLS, issuer/key type có phù hợp server `CertificateRequest` không.
- Service có đang đọc đúng keystore đó, đúng alias và mật khẩu key không.

**Không** in/export private key ra log/ticket để kiểm tra “key có đúng không”. Nếu cần kiểm tra key matching, dùng API/provider có kiểm soát, certificate public key và bước thử ký an toàn trong môi trường được cấp phép.

## 11. Java 17+: chương trình offline phân biệt capability và cấu hình không chung

Ví dụ đầu tiên **không mở socket, không gửi TLS ClientHello thật và không yêu cầu server**. Nó được thiết kế để kiểm tra được những điều dễ nhầm:

1. `SSLContext`/`SSLEngine` có danh sách **supported protocols** từ provider.
2. `SSLParameters` đặt `EndpointIdentificationAlgorithm("HTTPS")` ở client mode. Đây là **yêu cầu thực thi hostname verification khi có TLS handshake tương ứng**, không chứng minh đã xác minh một host trong demo offline.
3. Hai bộ cấu hình TLS protocol được mô phỏng **không có phần giao**, khác với một cặp có thể giao nhau.
4. Hai bộ cipher-suite names được mô phỏng **không có phần giao**. Đây mới là **điều kiện cần**, không đủ để bảo đảm handshake thật thành công.
5. Một `SSLHandshakeException` tổng hợp bọc `CertificateExpiredException` được phân loại theo **cause class**, thay vì đoán chỉ từ chuỗi message.
6. Không tuyên bố “đã sửa TLS” vì chưa có remote server hoặc full handshake.

Tạo file **`JsseHandshakePreflightDemo.java`**:

```java
import java.security.SecureRandom;
import java.security.cert.CertificateException;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.CertPathValidatorException;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;

public class JsseHandshakePreflightDemo {
    static boolean overlap(String[] first, String[] second) {
        for (String a : first) {
            for (String b : second) {
                if (a.equals(b)) {
                    return true;
                }
            }
        }
        return false;
    }

    static String safeCauseCategory(Throwable problem) {
        for (Throwable current = problem;
                current != null;
                current = current.getCause()) {
            if (current instanceof CertificateExpiredException) {
                return "CERTIFICATE_EXPIRED";
            }
            if (current instanceof CertificateNotYetValidException) {
                return "CERTIFICATE_NOT_YET_VALID";
            }
            if (current instanceof CertPathValidatorException) {
                return "CERT_PATH_INVALID";
            }
            if (current instanceof CertificateException) {
                return "CERTIFICATE_ERROR";
            }
        }
        return "OTHER_HANDSHAKE_ERROR";
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, new SecureRandom());

        SSLEngine engine = context.createSSLEngine(
                "api.example.invalid", 443
        );
        engine.setUseClientMode(true);

        SSLParameters parameters = engine.getSSLParameters();
        parameters.setEndpointIdentificationAlgorithm("HTTPS");
        engine.setSSLParameters(parameters);

        System.out.println("Supports TLSv1.2: "
                + Arrays.asList(engine.getSupportedProtocols())
                        .contains("TLSv1.2"));
        System.out.println("Supports TLSv1.3: "
                + Arrays.asList(engine.getSupportedProtocols())
                        .contains("TLSv1.3"));
        System.out.println("Client mode: " + engine.getUseClientMode());
        System.out.println("Endpoint identification: "
                + engine.getSSLParameters()
                        .getEndpointIdentificationAlgorithm());

        System.out.println("Disjoint example protocols overlap: "
                + overlap(
                    new String[]{"TLSv1.3"},
                    new String[]{"TLSv1.2"}
                ));

        System.out.println("Compatible example protocols overlap: "
                + overlap(
                    new String[]{"TLSv1.3", "TLSv1.2"},
                    new String[]{"TLSv1.2"}
                ));

        System.out.println("Disjoint example suites overlap: "
                + overlap(
                    new String[]{"TLS_AES_128_GCM_SHA256"},
                    new String[]{"TLS_CHACHA20_POLY1305_SHA256"}
                ));

        SSLHandshakeException sample =
                new SSLHandshakeException("redacted");
        sample.initCause(
                new CertificateExpiredException("test fixture")
        );
        System.out.println("Synthetic failure category: "
                + safeCauseCategory(sample));

        System.out.println("Real handshakes performed: 0");
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac JsseHandshakePreflightDemo.java
java JsseHandshakePreflightDemo
```

Stdout đã kiểm chứng bằng JDK SunJSSE cung cấp TLSv1.2 và TLSv1.3 (kết quả hỗ trợ protocol có thể thay đổi nếu bạn dùng một provider đặc biệt):

```text
Supports TLSv1.2: true
Supports TLSv1.3: true
Client mode: true
Endpoint identification: HTTPS
Disjoint example protocols overlap: false
Compatible example protocols overlap: true
Disjoint example suites overlap: false
Synthetic failure category: CERTIFICATE_EXPIRED
Real handshakes performed: 0
```

### 11.1. Tại sao test này đáng tin và có giới hạn?

- `engine.getSupportedProtocols()` trả những version mà provider hỗ trợ; **không khẳng định** chúng đều enabled hoặc được phép sau security policy. Có thể dùng `getEnabledProtocols()` để xem cấu hình cụ thể của engine.
- `setEndpointIdentificationAlgorithm("HTTPS")` chỉ đặt policy cho một engine. Vì không có handshake, chương trình chưa kiểm tra một certificate hoặc hostname thật.
- `overlap(...)` làm việc với **các string đã cho**, chưa xét certificate, nhóm X25519/P-256, signature scheme, trust anchors và thuật toán bị disabled. **Có phần giao là điều kiện cần, không đủ**.
- `SSLHandshakeException sample` được tạo **có chủ đích từ test fixture**, không phải lỗi SSL thực tế. Phân loại `CERTIFICATE_EXPIRED` nhằm minh họa đọc cause chain; trong production, lỗi certificate còn cần kiểm tra cert/chain/peer logs.
- Việc debug thực tế có thể cần xem `SSLProtocolException`, `SSLException`, `CertPathBuilderException`, provider-specific classes và peer alert; `safeCauseCategory` không phải bộ phân loại tất cả nguyên nhân.
- Không in các bytes của session secrets, private key, certificate chain thô hay thông tin người dùng; các string về config đều công khai giả lập.

### 11.2. Vì sao không tự động sửa suite khi `overlap=false`?

Giả sử client chỉ cho phép TLS 1.3 và server chỉ còn TLS 1.2. Bước đúng là hỏi:
1. Vì sao phía server không hỗ trợ TLS 1.3? Có thể nâng cấp runtime/gateway được không?
2. Nếu policy tổ chức vẫn cho phép TLS 1.2, cả hai phía có ít nhất một suite/nhóm/chữ ký an toàn không?
3. Nếu server chỉ có protocol/suite đã bị cấm, **không mở lại cấu hình yếu** chỉ để kết nối.
4. Khi thay đổi protocol, chạy lại certificate validation, mTLS, ALPN/HTTP version và negative tests.

Tương tự, thấy `overlap=true` không phải lý do bỏ bước kiểm tra truststore/hostname; chỉ có cơ hội thương lượng một version, chưa chắc có authenticated TLS.

## 12. Java 17+: chương trình kết nối thật khi cần quan sát handshake

Ví dụ thứ hai **cần mạng và một HTTPS endpoint mà bạn được quyền kiểm tra**. Nó cho thấy cách:
- Kết nối TCP với connect timeout.
- Bọc socket thành `SSLSocket` dùng JSSE.
- Đặt **HTTPS endpoint identification** theo host bạn yêu cầu trước khi handshake.
- Gọi `startHandshake()` rõ ràng.
- Phân biệt `SSLHandshakeException` và những `IOException` khác, không bypass trust.
- Trả ra **chỉ metadata đã kiểm soát**, không ghi raw certificates/secrets.

Tệp **`JsseLiveProbe.java`**:

```java
import java.net.InetSocketAddress;
import java.net.Socket;
import java.io.IOException;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;

public class JsseLiveProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: java JsseLiveProbe <hostname> <port>");
            return;
        }

        String host = args[0]; // Intended DNS identity from trusted configuration.
        int port = Integer.parseInt(args[1]);

        SSLContext context = SSLContext.getDefault();
        try (Socket tcp = new Socket()) {
            tcp.connect(new InetSocketAddress(host, port), 5000);
            tcp.setSoTimeout(5000);

            try (SSLSocket tls = (SSLSocket) context.getSocketFactory()
                    .createSocket(tcp, host, port, true)) {
                tls.setUseClientMode(true);
                tls.setSoTimeout(5000);

                SSLParameters parameters = tls.getSSLParameters();
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
                tls.setSSLParameters(parameters);

                tls.startHandshake();
                System.out.println("Handshake: OK");
                System.out.println("Protocol: " + tls.getSession().getProtocol());
                System.out.println("Cipher suite: "
                        + tls.getSession().getCipherSuite());
            }
        } catch (SSLHandshakeException failure) {
            System.err.println("Handshake: FAILED (see controlled JSSE trace)");
            System.err.println("Exception type: "
                    + failure.getClass().getSimpleName());
            throw failure; // In a lab; production API should map to safe error.
        } catch (IOException networkOrTls) {
            System.err.println("Connection/I-O failure: "
                    + networkOrTls.getClass().getSimpleName());
            throw networkOrTls;
        }
    }
}
```

Lệnh ví dụ trong lab:

```bash
javac JsseLiveProbe.java
java -Djavax.net.debug=ssl,handshake,trustmanager -Djava.security.debug=certpath JsseLiveProbe api.example.com 443
```

**Không có stdout cố định**: certificate, TLS protocol, cipher suite, DNS/network/proxy và truststore phụ thuộc endpoint/môi trường. `api.example.com` chỉ là tên minh họa, phải thay bằng hostname thực sự được phép kiểm tra. Không chạy chương trình trên endpoint không được quản trị/cho phép hoặc dùng tool để quét mạng ngoài phạm vi.

**Giới hạn:** đây là HTTPS TLS probe mức cơ bản; nó chưa gửi HTTP request, không thiết kế cho proxy authentication, SNI override, mTLS credentials riêng, ALPN/HTTP2 hoặc truststore tùy biến. Thư viện HTTPS client production như `java.net.http.HttpClient` thường phù hợp hơn, và có thể tự thực hiện endpoint identification/trust policy theo cấu hình. Nếu phải dùng custom `SSLSocket`, đừng quên explicitly bật hostname verification như trên.

### 12.1. Khi không thấy certificate error

Nếu `startHandshake()` thành công, đây là bằng chứng một TLS connection được tạo theo trust/identity policy của context đang dùng; **không** tự kết luận application principal được phép truy cập resource. HTTP 401/403 là tầng xác thực/phân quyền sau đó.

Nếu `startHandshake()` thất bại ngay trước certificate, không có nghĩa certificate “đúng” hoặc “sai” — có thể chưa tới bước ấy do protocol/suite/SNI mismatch.

## 13. Thực hành phân loại lỗi theo dấu hiệu

| Thông báo/nhóm lỗi | Giả thuyết ưu tiên | Kiểm tra để xác nhận | Không nên làm |
| --- | --- | --- | --- |
| `PKIX path building failed` | Thiếu CA/path, sai truststore, thiếu intermediate | JSSE trustmanager + certpath, actual truststore, chain | Trust-all/auto-import root từ peer |
| `trustAnchors must be non-empty` | Truststore rỗng/sai file | File path, store type, entries, custom SSLContext | Chấp nhận bất kỳ certificate |
| `CertificateExpiredException` | Leaf/intermediate expired, clock skew | Time NTP, validity toàn chain, cert rollout | Đặt giờ sai, bỏ validity |
| `CertificateNotYetValidException` | Certificate future/notBefore, đồng hồ lệch | Clock/timezone & cert validity | Bỏ thời gian kiểm tra |
| `No subject alternative ...` | Sai endpoint identity | Requested host, SAN, SNI, vhost | HostnameVerifier always true |
| `Received fatal alert: unknown_ca` | Một peer không tin CA của phía còn lại | Đọc logs cả hai bên, mTLS direction | Chỉ sửa client truststore vô căn cứ |
| `bad_certificate` | Certificate bị peer từ chối | Key usage, chain, EKU, thời gian, trust policy | Tắt client auth để “pass” |
| `certificate_required` | Thiếu client certificate khi mTLS | Server CertificateRequest, client keymanager alias | Thêm CA sai phía |
| `No available authentication scheme` | Không có private key/cert/signer phù hợp | Keymanager, PrivateKeyEntry, sig schemes, SNI | Bật tất cả cipher yếu |
| `No cipher suites in common` | Suite intersection rỗng hoặc bị constraint | Config cả hai phía, TLS version, JDK policy | Enable RC4/3DES/NULL |
| `No appropriate protocol` | Không có TLS version hợp lệ chung | Enabled protocols, disabled algorithms | Bật SSLv3/TLS1.0 |
| `Received fatal alert: protocol_version` | Peer không chấp nhận version | ClientHello/ServerHello và server TLS policy | Downgrade tùy tiện |
| `no_application_protocol` | ALPN mismatch | `h2`/`http/1.1`, gateway/app policy | Đổi certificate vô căn cứ |
| `handshake_failure` chung | Nhiều khả năng, kể cả SNI/keys/algorithms | JSSE+peer trace theo handshake stage | Kết luận chỉ từ một dòng |
| `Socket closed`/EOF sau ClientHello | Peer/network chặn, non-TLS listener, TLS policy | TCP path, load balancer logs, server listener | Đổi truststore không kiểm chứng |
| TLS success rồi HTTP `403` | Authorization của app | Access token, roles, tenant/resource | Xóa TLS session hoặc disable validation |

Bảng trên là **heuristic chẩn đoán**, không phải quy tắc message→cause chắc chắn cho mọi JDK, provider và phiên bản TLS.

## 14. Một ví dụ điều tra theo từng bước

### 14.1. Ca A: Java client fail nhưng browser truy cập được

Tình huống:
- Java `HttpClient` gọi `https://api.example.com`, ném `SSLHandshakeException` với `PKIX path building failed`.
- Trình duyệt trên laptop mở được URL.

Các bước:
1. Java có chạy trong container với truststore/JDK khác browser không?
2. Browser có đang dùng trust store OS, CA enterprise hoặc HTTP proxy/TLS inspection mà JVM không dùng?
3. Server có gửi đủ chain, đặc biệt intermediate certificates, cho đúng SNI?
4. Java runtime đang dùng `cacerts` nào, có properties override hoặc custom `SSLContext` không?
5. CA chain của server đã được xác minh từ kênh tin cậy chưa?
6. Nếu server thiếu intermediate, sửa cấu hình server/gateway để gửi đúng chain.
7. Nếu ứng dụng cần tin CA enterprise/internal, thêm **đúng CA đã kiểm chứng** theo chính sách, không trust certificate ngẫu nhiên từ network.
8. Chạy lại Java TLS handshake với expected hostname và bật test wrong-CA/wrong-hostname để chứng minh vẫn fail closed.

**Điểm học:** browser success không chứng minh CA đã có trong JDK; JVM trust là cấu hình cụ thể.

### 14.2. Ca B: mTLS fail sau deploy

Tình huống:
- Service A dùng client certificate gọi Service B qua mTLS.
- Sau rotation CA, client thấy `Received fatal alert: bad_certificate`.

Các bước:
1. Ghi nhận TLS termination point của Service B (gateway hay backend).
2. Ở client A, xem `keymanager` trace có chọn PrivateKeyEntry đúng key/certificate chain không.
3. Ở server B, xem `trustmanager` trace/PKIX có tin issuer CA mới không; certificate client có còn hạn/EKU clientAuth đúng không.
4. Kiểm tra B có nhiều nodes và rollout CA/truststore có đồng bộ không.
5. Xác minh service identity SAN và policy mapping của A.
6. Nếu server B đã từ chối CA mới, cập nhật truststore của B theo rotation plan (có giai đoạn overlap), không chỉnh truststore client A thay thế.
7. Sau handshake success, xác minh authorization service principal tới API vẫn đúng.

**Điểm học:** “lỗi certificate trên client” không đồng nghĩa **client** là bên thực hiện trust validation. Client có thể chỉ nhận alert từ server.

### 14.3. Ca C: TLS versions không giao nhau

Tình huống:
- Client chỉ bật TLS 1.3.
- Legacy gateway chỉ bật TLS 1.2.
- Java client thấy `protocol_version` hoặc `handshake_failure`.

Các bước:
1. Thu cấu hình enabled protocols hai bên.
2. So phần giao, xác nhận rỗng.
3. Đánh giá nâng cấp gateway, TLS termination hoặc chọn cấu hình TLS 1.2 **chỉ nếu chính sách cho phép**.
4. Sau thay đổi, kiểm tra suites, signature algorithms, named groups, certificate và hostname.
5. Giữ negative tests từ chối phiên bản yếu, không tắt `jdk.tls.disabledAlgorithms`.

**Điểm học:** đây là negotiation mismatch, không nhất thiết do certificate/truststore.

### 14.4. Ca D: có chung cipher suite nhưng vẫn `handshake_failure`

Tình huống:
- Hai bên cùng liệt kê `TLS_AES_128_GCM_SHA256`.
- Server chỉ có một certificate/key không được client chấp nhận hoặc signer/group không phù hợp.

Cần kiểm tra:
- TLS 1.3 `signature_algorithms`, `supported_groups`, `key_share`, certificate public key.
- Server keymanager có PrivateKeyEntry phù hợp không?
- CA/cert chain có áp policy đúng không?
- SNI đã chọn vhost/certificate đúng chưa?
- Security properties loại bỏ thuật toán/độ dài key nào?
- Có `CertificateRequest` và client cert requirements không?

**Điểm học:** TLS 1.3 suite intersection không bảo đảm có authentication/key-share configuration dùng chung.

### 14.5. Ca E: chỉ một hostname trên cùng server fail

Tình huống:
- `api.internal.example` pass, `billing.internal.example` fail.
- Cả hai DNS trỏ cùng gateway IP.

Khả năng:
- SNI route trả certificate/default backend sai.
- Billing cert thiếu SAN/expired; API cert đúng.
- Một virtual host chỉ cho phép ALPN/TLS policy khác.
- Load balancer một node có certificate cũ.
- App gọi IP literal nhưng kỳ vọng certificate DNS.

Đừng dùng `-Dcom.sun.net.ssl.checkRevocation=false` hay tắt hostname verification để chữa. Thu đúng certificate trên mỗi SNI và sửa virtual-host/certificate chain.

## 15. Runbook một lần theo thứ tự ít rủi ro

### Bước 1 — Chuẩn bị chứng cứ tối thiểu

Ghi:
- JDK runtime/provider cụ thể.
- Client→host:port và expected hostname (không thay bằng IP tùy ý).
- TLS termination point và có proxy/mTLS không.
- Thời điểm lỗi, deploy/CA rotation gần nhất.
- Loại exception/cause chain **đã sanitize**, handshake stage cuối đã xác định.

### Bước 2 — Tách network khỏi TLS

Xác nhận DNS, port, listener, firewall, proxy và upstream route. Nếu không tới được port TLS, không cần đào sâu PKIX. Nếu tới một HTTP-only port mà client nói TLS, sẽ có lỗi record/protocol mà import CA không sửa được.

### Bước 3 — Bật debug vừa đủ ở môi trường được phép

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager,keymanager MyTlsApp
```

Nếu certificate trust path:
```bash
java -Djavax.net.debug=ssl,handshake,trustmanager -Djava.security.debug=certpath MyTlsApp
```

Giới hạn log retention, không upload traces thô chứa dữ liệu nhạy cảm vào kênh công khai.

### Bước 4 — So cấu hình hai phía

- Enabled TLS versions, cipher suites và algorithm constraints.
- TLS 1.3 supported groups/key shares/signature schemes.
- Server certificate/private key, mTLS client cert và CA.
- SNI expected host, ALPN application protocols.
- Resumption/full handshake và server node nếu failure chỉ theo traffic.

### Bước 5 — Xác minh PKIX/hostname

- Certificate chain leaf→intermediates→trust anchor.
- Truststore thực sự của từng endpoint, không chỉ file tên gần giống.
- Validity, SAN, issuer, BasicConstraints, EKU/KeyUsage, algorithm constraints, revocation policy.
- Expected hostname đúng từ client/service config.
- Chứng minh private key/handshake policy qua TLS stack, không chỉ `X509Certificate.verify(...)`.

### Bước 6 — Chọn cách sửa an toàn và kiểm thử âm

Ví dụ:
- Server thiếu intermediate: sửa server chain.
- CA enterprise chưa được JVM tin: cập nhật truststore **sau khi kiểm chứng CA**.
- Sai hostname: cấp cert đúng SAN, sửa SNI/route hoặc dùng expected host đúng.
- mTLS CA rollout lệch: sửa server trust anchors và kế hoạch rotation.
- No shared TLS version: nâng cấp server hoặc bật duy nhất version/suites được policy cho phép.
- Missing key entry: cấp/cấu hình PrivateKeyEntry phù hợp và bảo vệ private key.
- ALPN mismatch: cấu hình protocol ứng dụng được cả hai hỗ trợ.

Sau đó **đảm bảo các trường hợp sai CA, sai host, hết hạn, cipher yếu và thiếu cert mTLS vẫn bị từ chối**.

### Bước 7 — Ghi nhận nguyên nhân và phòng tái phát

- Phân loại lỗi đúng nhóm, tránh `SSLHandshakeException` chung chung.
- Health checks với certificate expiry/chain/hostname.
- CA/certificate rotation alert trước hạn, staged rollout và rollback plan.
- Kiểm tra truststore/key entry ngay khi khởi động (không in secrets).
- Kiểm thử contract TLS/mTLS giữa teams và gateways trong CI staging.
- Theo dõi handshake failures theo TLS termination point, JDK/provider, route, SNI và policy version.
- Duy trì runbook kiểm tra cả **peer log** khi client chỉ nhận fatal alert chung.

## 16. Những điều tuyệt đối không dùng làm “fix”

| Biện pháp sai | Vì sao nguy hiểm | Hướng thay thế |
| --- | --- | --- |
| TrustManager chấp nhận tất cả certificates | Bỏ chain/path validation, mở MITM | Dùng truststore chứa CA đã xác minh |
| HostnameVerifier luôn true | Certificate của host khác cũng được chấp nhận | Sửa SAN/SNI/expected hostname |
| Cài đặt một root lấy từ peer vào truststore | Tin nguồn CA có thể do attacker kiểm soát | Xác minh root qua kênh quản trị |
| Bật SSLv3/TLS 1.0/1.1 hoặc NULL/anonymous suites | Làm yếu protocol, có thể bị downgrade | Nâng cấp peer và giữ algorithm policy |
| Xóa `jdk.tls.disabledAlgorithms` để ép kết nối | Mở lại thuật toán/khóa đã bị cấm | Thay certificate/key/server config |
| Bỏ `CertificateException` rồi tiếp tục | Xác thực peer không còn đáng tin | Fail closed, sửa certificate/trust |
| Log private key, TLS session secrets, token | Rò rỉ lâu dài qua diagnostics | Chỉ log metadata và cause category |
| Đoán nguyên nhân chỉ từ `handshake_failure` | Alert generic, peer thường biết rõ hơn | JSSE+peer logs theo stage |
| Bắt `SSLHandshakeException` rồi retry vô hạn | Có thể DoS, che cấu hình sai, làm chậm recovery | Retry có kiểm soát khi lỗi tạm thời |
| Dùng HTTP plaintext để “tạm chạy” | Mất confidentiality/integrity/peer authentication | Sửa TLS hoặc chặn giao dịch |
| Bỏ kiểm tra mTLS clientAuth vì CA chưa đồng bộ | Mất client authentication và principal binding | Cập nhật CA theo rotation có kiểm soát |
| Chỉ test happy path sau “fix” | Security bypass có thể khiến test pass | Test wrong-CA, wrong-host, expired, mTLS rejection |

## 17. Checklist QA và regression

### Certificate trust và identity

- [ ] Valid chain tới approved CA + SAN đúng → handshake thành công.
- [ ] Self-signed untrusted → bị từ chối.
- [ ] CA không nằm trong truststore → bị từ chối.
- [ ] Leaf/intermediate expired/notYetValid → bị từ chối theo policy.
- [ ] Valid chain nhưng wrong SAN/hostname → bị từ chối.
- [ ] Issuer/chain bị sửa hoặc thiếu intermediate → được xử lý đúng (fail hoặc builder path hợp lệ).
- [ ] EKU/KeyUsage/BasicConstraints không phù hợp → bị từ chối.
- [ ] Revocation/OCSP/CRL theo policy được kiểm tra.

### Negotiation

- [ ] Client/server chỉ có protocol sets không giao nhau → handshake fail, không downgrade.
- [ ] Có protocol nhưng không có cipher suite chung → handshake fail theo policy.
- [ ] TLS 1.3 suite chung nhưng signature schemes không giao → fail thích hợp.
- [ ] Named groups/key shares không có điểm chung → fail/HelloRetryRequest theo protocol.
- [ ] ALPN bắt buộc không giao → fail/handled theo app profile.
- [ ] SNI sai → cert/route được chọn đúng policy, wrong host không pass.
- [ ] Security disabled algorithms không bị bỏ qua khi sửa.

### mTLS

- [ ] Client không có certificate khi server yêu cầu → bị từ chối.
- [ ] Client certificate do CA ngoài danh sách tin cậy cấp → bị từ chối.
- [ ] Client cert không matching private key/alias hoặc sai EKU → bị từ chối.
- [ ] Sau handshake, principal mapping và authorization đúng tenant/resource.
- [ ] CA/cert rotation của client và server có giai đoạn chuyển đổi an toàn.

### Observability và vận hành

- [ ] Có phân loại lỗi network/TLS/PKIX/identity/app.
- [ ] JSSE debug flags chỉ bật trong môi trường được phép và có retention/redaction.
- [ ] Server/peer-side log có thể truy vết theo correlation ID.
- [ ] Container/runtime truststore/keystore được kiểm chứng tại đúng JDK.
- [ ] Không hardcode password trong JVM args hoặc log/CI secrets.
- [ ] Runbook có rollback và negative tests để phát hiện bypass.

## 18. Câu hỏi tự kiểm tra

**1. `SSLHandshakeException` có luôn là lỗi certificate không?**  
Không. Nó bao gồm nhiều lỗi handshake: protocol/cipher/group/signature mismatch, mTLS, PKIX, endpoint identity và những vấn đề khác.

**2. `Received fatal alert: handshake_failure` có đủ để kết luận client thiếu CA không?**  
Không. Đây là alert chung từ peer; cần xem peer logs và handshake stage/cause.

**3. Khi Java báo `PKIX path building failed`, nên import certificate từ server ngay vào truststore không?**  
Không. Phải xác minh chain/CA qua nguồn tin cậy rồi sửa truststore hoặc chain có kiểm soát; không tự tin dữ liệu mạng chưa xác thực.

**4. Truststore và keystore khác nhau thế nào trong HTTPS client bình thường?**  
Truststore cung cấp CA để xác minh **server**. Keystore cung cấp private key/certificate của **client** nếu dùng mTLS.

**5. Nếu client chỉ TLS 1.3 và server chỉ TLS 1.2, certificate hợp lệ có giúp handshake không?**  
Không. Không có protocol version chung; phải sửa config/upgrade theo policy trước khi tới certificate authentication.

**6. Vì sao TLS 1.3 có chung suite `TLS_AES_128_GCM_SHA256` mà vẫn fail?**  
Vì authentication/signature schemes, supported groups/key shares, certificate/key type, SNI/ALPN và policy là những yêu cầu riêng.

**7. Một Java client log `Received fatal alert: bad_certificate` trong mTLS thì phía nào nên kiểm tra?**  
Cả hai, ưu tiên server/gateway nơi phát alert vì có thể server từ chối client certificate; xem client keymanager và server trustmanager.

**8. `SSLSession.getProtocol()` trả TLSv1.3 có chứng minh `CertificateVerify` đã thành công trong mọi resumed handshake không?**  
Không. TLS 1.3 có PSK resumption và không phải handshake nào cũng lặp certificate authentication; phải hiểu session/handshake mode. Đây cũng không chứng minh application authorization.

**9. Chạy `keytool -printcert -sslserver ...` ra certificate có nghĩa đã tin root chưa?**  
Không. Tool hiển thị certificate; trust validation/hostname matching là bước bảo mật khác.

**10. Nên bật debug `javax.net.debug` đến mức nào?**  
Bắt đầu `ssl,handshake,trustmanager,keymanager` theo lỗi; `java.security.debug=certpath` khi cần. Không bật data/plaintext/packet dump bừa bãi trên production.

**11. `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` dùng làm gì?**  
Yêu cầu endpoint identity/hostname checking khi JSSE handshake trong context phù hợp, không thay certificate path validation hoặc một network handshake hoàn chỉnh.

**12. Vì sao một truststore khác nhau giữa browser và Java container gây kết quả khác nhau?**  
Vì browser và JVM có thể dùng CA stores, proxy/TLS interception và security policy khác; browser success không tự chứng minh Java trust anchor đúng.

**13. Sau khi “fix” bằng cách bỏ HostnameVerifier, mọi request pass. Có hoàn thành nhiệm vụ không?**  
Không. Đây là security regression: client có thể chấp nhận cert của endpoint sai. Phải sửa SAN/SNI/trust configuration và kiểm thử âm.

**14. Nếu Java đã hoàn tất TLS rồi server trả HTTP 403, sửa `SSLHandshakeException` có đúng hướng không?**  
Không. HTTP 403 là application authorization/identity policy, phải debug ở layer đó.

**15. Khi client không có client certificate nhưng server yêu cầu mTLS, sửa bên nào?**  
Client cần PrivateKeyEntry/certificate chain phù hợp; server cần trust client issuer theo policy. Không thay bằng trust-all hoặc tắt mTLS.

**16. Vì sao cần biết TLS termination point?**  
Vì handshake/certificate được kiểm tra tại đúng hop (client↔gateway hay gateway↔backend); sửa keystore ở backend không giúp client↔gateway nếu TLS terminate ở gateway.

## 19. Sơ đồ quyết định cuối bài

```text
Connection failed
      |
      v
DNS/TCP success?
  |             |
 NO             YES
  |              |
Network/route   TLS handshake begins
                 |
                 v
          ClientHello/ServerHello overlap?
             |                 |
            NO                 YES
             |                  |
       version/cipher/          certificate/auth phase
       group/signature                 |
       ALPN/SNI policy                 v
                              PKIX certificate path valid?
                               |                 |
                              NO                 YES
                               |                  |
                           CA/chain/              expected hostname valid?
                           validity/               |                |
                           revocation/            NO                YES
                           algorithm               |                 |
                                                SAN/SNI/          mTLS + Finished?
                                                identity          |          |
                                                                 NO          YES
                                                                  |           |
                                                             keymanager/     HTTP/application
                                                             trustmanager    authorization

  At every failure:
  - Read cause chain and first meaningful fatal event
  - Check BOTH endpoints' logs + actual TLS termination hop
  - Preserve strong trust, hostname verification, algorithm constraints
  - Make a scoped fix and re-run negative tests
```

**Kết luận:** Chẩn đoán `SSLHandshakeException` phải phân biệt **certificate validation**, **đúng hostname/peer identity**, **mTLS client authentication**, và **khả năng thương lượng chung** về protocol, cipher suites, signature schemes, groups và ALPN. JSSE debug, certpath trace, `keytool` và `SSLParameters` giúp tìm gốc lỗi, nhưng chỉ có ý nghĩa khi xác định **đúng runtime và đúng TLS termination point**. Hãy sửa certificate/CA/config cho phù hợp chính sách thay vì vô hiệu trust hoặc downgrade. Một “fix” chỉ hoàn thành khi **handshake hợp lệ thành công và handshake sai vẫn bị từ chối**.

### Tài liệu tham khảo

- Oracle Java SE 17 — *Java Secure Socket Extension (JSSE) Reference Guide*, mục troubleshooting, certificate exceptions và debugging: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
- Java SE 17 `SSLHandshakeException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLHandshakeException.html
- Java SE 17 `SSLEngine`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html
- Java SE 17 `SSLParameters`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html
- Java SE 17 `SSLContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html
- Java SE 17 `SSLSocket`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html
- Java SE 17 `X509TrustManager`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509TrustManager.html
- Java SE 17 `CertPathValidatorException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidatorException.html
- Java SE 17 `KeyStore`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html
- Oracle Java 17 — *keytool* command reference: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- RFC 5280 — X.509 certificate path validation: https://www.rfc-editor.org/rfc/rfc5280
- RFC 9846 — TLS 1.3 specification current in 2026: https://www.rfc-editor.org/rfc/rfc9846
