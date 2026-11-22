# 15.2. Luồng bắt tay, xác thực máy chủ và xác thực hai chiều mTLS

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả **TLS (Transport Layer Security)** bảo vệ một kết nối bằng cách thỏa thuận tham số mã hóa, tạo khóa phiên, xác thực danh tính và bảo vệ dữ liệu trao đổi khỏi đọc trộm/chỉnh sửa.
2. Đọc đúng thứ tự các thông điệp chính trong một **TLS 1.3 full handshake**, đặc biệt `ClientHello`, `ServerHello`, `EncryptedExtensions`, `Certificate`, `CertificateVerify`, `Finished` và `CertificateRequest` khi xác thực client.
3. Phân biệt **one-way TLS** (client xác thực server) với **mutual TLS/mTLS** (cả hai phía xác thực chứng thư của nhau), kể cả vai trò **keystore**, **truststore** và CA riêng ở mỗi phía.
4. Giải thích **xác minh chuỗi chứng thư X.509, hostname/SAN, KeyUsage/EKU, chứng minh sở hữu private key** và vì sao chỉ “kiểm chữ ký CA đúng” hoặc “có certificate” không đủ.
5. Hiểu mối liên hệ giữa **(EC)DHE key exchange, HKDF, handshake transcript, Finished, AEAD record protection, forward secrecy** và những khác biệt quan trọng giữa TLS 1.3, TLS 1.2, resumption và 0-RTT.
6. Dùng **Java 17+ JSSE** kết hợp `keytool` tạo lab CA/leaf certificates, chạy TLS server và client thực tế ở hai chế độ, **giữ hostname verification bật**, minh họa hành vi thiếu client certificate trong mTLS.
7. Nhận diện các sai lầm vận hành: `trust-all`, `HostnameVerifier` luôn true, nhầm mTLS với authorization, nhầm serverAuth/clientAuth, không kiểm certificate expiry/revocation, chứng thư đúng nhưng endpoint sai.

**Phạm vi:** Thuộc **Java Advance – security-cryptography / 15. Nền tảng TLS**. Bài tập trung vào **luồng bắt tay và hai hình thức xác thực**; các câu lệnh tạo CA/certificate và code socket dùng để học, không phải cấu hình PKI hay deployment production hoàn chỉnh.

---

## 1. TLS bảo vệ cái gì và tại sao phải “bắt tay”?

TCP cung cấp dòng byte hai chiều nhưng **không tự mã hóa dữ liệu, xác thực máy chủ hoặc chống thay đổi nội dung**. Một kẻ đứng giữa trên đường truyền có thể nghe, sửa hoặc giả mạo dữ liệu nếu ứng dụng không có lớp bảo vệ khác.

TLS đặt một giao thức mật mã lên transport phù hợp, phổ biến nhất là TCP cho HTTPS. **Handshake** tạo một bối cảnh bảo mật mà cả hai đầu thống nhất:

- **Phiên bản và tham số**: ví dụ TLS 1.3, bộ mã hóa AEAD/cipher suite và các thuật toán được phép.
- **Key agreement**: bí mật chung từ trao đổi khóa tạm thời, thường (EC)DHE, được dẫn xuất thành khóa handshake và application traffic qua key schedule; hoặc dùng PSK/resumption theo giao thức.
- **Server authentication**: client kiểm chain của chứng thư server đến trust anchor, đúng hostname/endpoint identity và thông điệp chứng minh private key hợp lệ.
- **Client authentication (tùy chọn)**: server có thể yêu cầu client certificate và xác minh nó; đây là **mTLS** khi client cũng xác thực server.
- **Handshake integrity**: những bản tóm lược handshake (transcript) được ràng buộc vào xác thực và `Finished`, phát hiện sửa đổi/giả mạo trao đổi.
- **Record protection**: application data sau handshake được mã hóa và xác thực bằng AEAD; mỗi chiều dùng traffic keys/nonce và sequence tương ứng do giao thức quản lý.

```text
Application: HTTP / gRPC / ứng dụng Java riêng
                   │
                   ▼
     TLS handshake → authenticated traffic keys
                   │
                   ▼
      TLS record protection (AEAD)
                   │
                   ▼
             TCP connection
```

**TLS không thay thế business authorization**: một client đã có TLS session hợp lệ không vì vậy được đọc mọi database record hoặc thực hiện mọi thao tác. TLS cũng **không đảm bảo dữ liệu an toàn sau khi đã giải mã trong ứng dụng**, không loại bỏ lỗi XSS/SQL injection và không che metadata như IP hoặc toàn bộ tính chất lưu lượng.

### 1.1. Các thuật ngữ dễ nhầm

| Thuật ngữ | Ý nghĩa | Không đồng nghĩa với |
| --- | --- | --- |
| **Handshake** | Trình tự thiết lập khóa, kiểm thông số, xác thực peer và hoàn tất kết nối bảo mật | HTTP request hoặc một lần mã hóa AES |
| **TLS record** | Đơn vị vận chuyển dữ liệu được mã hóa/xác thực dưới traffic keys | X.509 certificate |
| **Cipher suite (TLS 1.3)** | Định danh AEAD và hash dùng trong key schedule, ví dụ `TLS_AES_128_GCM_SHA256` | Gói đầy đủ key-exchange/authentication algorithms như cách đặt tên ở TLS 1.2 |
| **Key share** | Public value cho key agreement tạm thời, thường ECDHE | Private key nằm trong server certificate |
| **Certificate chain** | Leaf + intermediate(s) cần để xây đường đến trust anchor | Truststore đã tin sẵn mọi certificate do server gửi |
| **Keystore** | Kho chứa private key/certificate chain của chính bên này | Truststore dùng tin các CA của bên kia |
| **Truststore** | Cơ sở trust anchors/certificates được bên xác minh chấp thuận | Private key của server |
| **Server authentication** | Client xác minh server identity và proof-of-possession trong handshake | Server xác thực client |
| **Client authentication** | Server xác minh client identity và proof-of-possession | Quyền API của client |
| **mTLS** | Cả hai chiều thực hiện xác thực TLS phù hợp | Hai lớp TLS lồng nhau hoặc gửi username/password hai lần |
| **ALPN** | Thỏa thuận application protocol như `h2`/`http/1.1` | Bằng chứng danh tính của peer |
| **SNI** | Tên server client chỉ ra để hỗ trợ server chọn certificate/virtual host | Cơ chế kiểm chứng hostname thay client |
| **Session resumption** | Tái sử dụng trạng thái/PSK được TLS cho phép ở kết nối tiếp theo | Chắc chắn thực hiện lại đầy đủ certificate exchange như lần đầu |

---

## 2. One-way TLS: client xác thực server

Ở mô hình HTTPS thông thường, **server trình bày chứng thư**, còn client **không bắt buộc** trình bày client certificate. Đây là **server-authenticated TLS**, hay one-way TLS.

```text
CLIENT                                  SERVER
  |                                       |
  | ClientHello ------------------------->|
  |<------------------------- ServerHello |
  |<------------------ EncryptedExtensions|
  |<-------------------------- Certificate|
  |<-------------------- CertificateVerify|
  |<--------------------------------Finished|
  |                                       |
  | Validate server chain, SAN/hostname, |
  | certificate purpose, private-key    |
  | possession via handshake, transcript|
  |                                       |
  | Finished ---------------------------> |
  |                                       |
  |<======== protected app data =========>|
```

Sơ đồ rút gọn là **full TLS 1.3 certificate-based handshake**. Nó bỏ qua alert, optional messages, HelloRetryRequest và chi tiết record/key schedule. Các message sau `ServerHello` trong TLS 1.3 được bảo vệ bằng handshake traffic keys thích hợp (với ngoại lệ/phần nhìn thấy được theo cấu trúc bản ghi, protocol details). Không dùng sơ đồ này như một packet capture chính xác ở mọi phiên bản.

### 2.1. Bước 1 – `ClientHello`

Client gửi các khả năng hỗ trợ, ví dụ:

- Những phiên bản TLS được hỗ trợ qua extension `supported_versions`.
- Các TLS 1.3 cipher suites có thể sử dụng.
- `supported_groups` và `key_share` cho key agreement.
- `signature_algorithms` để các phía biết loại signature scheme chấp nhận.
- **SNI** cho tên server dự định và **ALPN** nếu ứng dụng cần thỏa thuận protocol.
- Có thể có thông tin PSK/session resumption, tùy kiểu handshake.

Client **không gửi raw secret key hoặc mật khẩu keystore** trong `ClientHello`. Một `key_share` chứa dữ liệu public của cơ chế thỏa thuận khóa; private ephemeral key vẫn được giữ cục bộ.

**SNI không phải “kiểm server đáng tin”:** SNI chủ yếu giúp server chọn virtual host/certificate phù hợp; client vẫn phải xác thực certificate và tên dự định kết nối.

### 2.2. Bước 2 – `ServerHello` và shared secret

Server chọn phiên bản TLS/cipher suite và key share thích hợp. Hai phía dùng private key ephemeral của mình kết hợp public key share phía kia để có shared secret tương ứng, rồi cùng chạy **key schedule** của TLS 1.3 dựa trên HKDF để dẫn xuất các traffic secrets.

```text
Client ephemeral secret + Server public key share ──┐
                                                    ├─ same key agreement secret
Server ephemeral secret + Client public key share ──┘
                                  │
                                  ▼
                  HKDF-based TLS 1.3 key schedule
                                  │
                handshake traffic keys / Finished keys
                                  │
                       application traffic keys
```

Đây là hình dung về key agreement; không phải phép nối byte/kDF mà ứng dụng nên tự lập trình. Trong TLS 1.3, RSA certificate có thể dùng **để ký xác thực**, không phải “RSA encrypt premaster secret” như một số handshake TLS 1.2 cũ. **(EC)DHE** tạo cơ sở cho **forward secrecy** khi ephemeral secrets được quản lý/xóa đúng: bị lộ server certificate private key về sau không tự cho phép giải mã các phiên TLS 1.3 đã ghi lại trước đó.

**Chú ý:** Forward secrecy không bảo vệ nếu attacker đã kiểm soát endpoint trong phiên, đọc traffic keys/endpoint plaintext, hoặc giả mạo được server lúc bắt tay. Resumption/PSK và các phương thức trao đổi khóa khác có tính chất riêng cần đánh giá đúng giao thức.

### 2.3. Bước 3 – Server gửi chứng thư và chứng minh key possession

Server gửi `Certificate` với leaf certificate (và thường intermediate certificates). Những thành phần quan trọng:

1. **SubjectAlternativeName** (SAN) phải bao phủ endpoint identity mà client dự định kết nối, như `DNS:api.example.com` hoặc SAN IP phù hợp khi kết nối bằng IP literal.
2. **Certificate chain** phải xây được path đến root/trust anchor được client chấp thuận, với ký số CA và những ràng buộc CA/BasicConstraints/name constraints, key usage và policy.
3. **Validity/revocation** được đánh giá theo thời điểm và chính sách; certificate chưa hết hạn vẫn có thể bị thu hồi.
4. **ExtendedKeyUsage** của server certificate thường cần `serverAuth` theo profile/policy; không coi clientAuth hoặc codeSigning là thay thế tùy tiện.
5. **`CertificateVerify`** chứa chữ ký do server thực hiện bằng private key tương ứng với leaf, trên transcript/cấu trúc có domain separation theo TLS 1.3. Điều này chứng minh server đang nắm private key hợp lệ cho handshake, chứ không chỉ sao chép một PEM công khai.

```text
CA trusted? ----yes----+
                       |
Chain valid? ---yes----+
                       |
Hostname SAN? --yes----+---> Có thể chấp nhận server identity
                       |     nếu các kiểm tra TLS/policy khác đều đạt
Key usage? ----yes-----+
                       |
CertificateVerify? yes-+
                       |
Finished? ----yes------+
```

**Một leaf certificate chứa public key không đủ:** bất kỳ ai cũng có thể gửi bản sao certificate của `api.example.com`. Điều làm attacker khó giả làm server là họ còn phải tạo được `CertificateVerify` hợp lệ bằng **server private key** và đáp ứng toàn bộ trao đổi khóa/handshake.

### 2.4. Bước 4 – `Finished` và application data

`Finished` bảo vệ ranh giới hoàn tất handshake bằng MAC/verify data ràng buộc với transcript và các handshake secrets phù hợp. Client chỉ coi session là bảo mật sau các phép kiểm TLS/identity cần thiết.

Sau khi handshake hoàn thành, **application data** (HTTP request/response hoặc bytes từ `SSLSocket`) được bảo vệ bằng record-layer AEAD. Mỗi chiều có traffic keys riêng theo key schedule và quản lý nonce/sequence nội bộ, **ứng dụng không tự lấy AES-GCM nonce cho TLS record**.

**Không nhầm:** server authenticated TLS cho client biết đang giao tiếp với server được phép; nó **không tự cung cấp danh tính client**. Trong one-way TLS, phía server thường cần thêm bearer token, session cookie, OAuth/OIDC hoặc xác thực ứng dụng riêng để biết requester là ai.

---

## 3. mTLS: server cũng xác thực client

**mTLS – mutual TLS** dùng cùng nền tảng TLS nhưng bổ sung bước **server yêu cầu client certificate** và xác minh danh tính phía client. Client vẫn phải xác thực server như one-way TLS; không có ngoại lệ “vì server tin client nên client có thể bỏ hostname verification”.

```text
CLIENT                                          SERVER
  |                                               |
  | ClientHello ---------------------------------> |
  |<---------------------------------- ServerHello |
  |<----------------------------- EncryptedExtensions
  |<-------------------------------- CertificateRequest
  |<-------------------------------------- Certificate
  |<-------------------------------- CertificateVerify
  |<----------------------------------------- Finished
  |                                               |
  | Verify SERVER chain + SAN/hostname + signature|
  |                                               |
  | Client Certificate --------------------------> |
  | Client CertificateVerify --------------------> |
  | Client Finished -----------------------------> |
  |                                               |
  |        SERVER verifies CLIENT certificate     |
  |        trust chain / purpose / possession     |
  |                                               |
  |<============== protected app data ===========> |
```

Đây là **luồng TLS 1.3 mTLS trong initial/full handshake**; thứ tự có thể thay theo phiên bản/kiểu handshake, và các trường hợp optional/resumption/post-handshake auth có quy tắc riêng. `CertificateRequest` là tín hiệu server yêu cầu client authentication; nếu không có certificate phù hợp client có thể gửi danh sách trống, nhưng server yêu cầu xác thực **bắt buộc** sẽ từ chối handshake.

### 3.1. Ai sở hữu khóa nào?

| Tài sản | Phía server | Phía client |
| --- | --- | --- |
| Server private key | **Giữ bí mật** trong server keystore/HSM | Không được cấp |
| Server leaf + chain | Trình bày trong handshake | Nhận để xác minh server |
| Server-trust CA/root | Không cần làm tin cậy cho chính mình | **Client truststore** chứa trust anchor được chấp thuận |
| Client private key | Không được cấp | **Giữ bí mật** trong client keystore/HSM |
| Client leaf + chain | Nhận khi server yêu cầu | Trình bày trong handshake |
| Client-trust CA/root | **Server truststore** chứa CA cấp cho clients được phép | Không mặc nhiên dùng làm server trust anchor |
| Application authorization | **Enforce** identity → role/tenant/action | Chỉ gửi yêu cầu trong quyền được cấp |

Trong lab, root CA dùng chung để giảm thao tác; trong production **có thể và thường nên phân biệt CA/profile phục vụ serverAuth với CA/profile cho clientAuth** để giảm phạm vi tin cậy. Việc server có `server.p12` chưa đồng nghĩa server đã tin `client.p12`: server phải được cấu hình riêng trust anchors và yêu cầu client authentication.

### 3.2. `CertificateRequest` và `CertificateVerify`

Khi server bật mTLS:

1. Trong TLS 1.3 full handshake, server gửi `CertificateRequest`; yêu cầu có thể mang danh sách CA chấp nhận, signature algorithms và extensions.
2. Client chọn một certificate chain/private key phù hợp; thuật toán lựa chọn phụ thuộc JSSE key manager, key type, CA hints và khả năng ký.
3. Client gửi `Certificate` và `CertificateVerify` để chứng minh sở hữu private key trên transcript phù hợp.
4. Server xác thực chain/client certificate theo trust anchors của **server**, kiểm mục đích `clientAuth` và những ràng buộc/identity policy.
5. `Finished` hoàn tất handshake integrity. Server chỉ cho client dùng kênh khi handshake authentication đáp ứng chính sách.

**Chỉ gửi một certificate công khai không đủ để xác thực mTLS.** Bất kỳ ai có bản PEM công khai đều có thể gửi nó, nhưng không thể hoàn thành proof-of-possession nếu không có private key tương ứng.

### 3.3. `needClientAuth` và `wantClientAuth`

Trong JSSE server:

- `SSLServerSocket.setNeedClientAuth(true)` hoặc `SSLEngine.setNeedClientAuth(true)`: client certificate là **bắt buộc**; nếu client không trình bày credential hợp lệ, handshake bị từ chối.
- `setWantClientAuth(true)`: server **đề nghị** client certificate nhưng có thể chấp nhận client không có certificate. Ứng dụng phải tự quyết định đường xử lý identity rỗng.
- Mặc định server thường không yêu cầu client certificate. Khi client không được yêu cầu, có sẵn `client.p12` cũng không có nghĩa client tự gửi cert.
- Khi bật need/want, phải có trust manager và CA policy dành cho client identities, không được chỉ bật một boolean rồi tin mọi client certificate.

Đối với Spring Boot, Netty, gRPC, proxy/ingress/service mesh, các tên cấu hình có thể khác nhưng ý nghĩa **require client auth** và **trusted client roots** vẫn cần rõ. Cần biết mTLS **kết thúc ở đâu** (edge proxy, sidecar hay ứng dụng JVM).

### 3.4. mTLS xác thực danh tính, không tự phân quyền

Ví dụ một client có certificate:

```text
Subject: CN=payments-worker, O=Example
SAN: URI:spiffe://company.example/ns/prod/sa/payments-worker
EKU: clientAuth
Issuer: Internal Workload CA
```

Khi handshake thành công, server có thể map identity được xác minh thành **service principal** như `payments-worker`, nhưng vẫn phải kiểm **service đó có được đọc tenant T hoặc gọi operation refund không**. Nếu mọi chứng thư được CA cấp đều được gán role admin, mTLS đã bị lạm dụng thành một chính sách authorization quá rộng.

Không lấy một Subject DN, hostname hoặc header `X-Client-Cert` chưa được proxy tin cậy bảo vệ rồi cấp quyền. Với proxy termination, cần bảo đảm header identity được **xóa/tạo lại** bởi proxy tin cậy, không cho client Internet tự khai.

---

## 4. TLS 1.3 và TLS 1.2 khác nhau ở chỗ nào?

| Khía cạnh | TLS 1.3 | TLS 1.2 |
| --- | --- | --- |
| Cơ chế key exchange | Thiết kế dùng cơ chế cho forward secrecy trong full handshake phổ biến như (EC)DHE, hoặc PSK/resumption theo chuẩn | Có thể dùng ECDHE; các suite cũ còn dùng static RSA key transport (nay không nên chọn) |
| Cipher suite naming | AEAD + hash, ví dụ `TLS_AES_128_GCM_SHA256`; key exchange/signature được thỏa thuận độc lập | Tên suite có thể gồm key exchange, authentication, symmetric cipher, MAC/hash |
| Sau `ServerHello` | Phần lớn handshake messages sau mốc này được bảo vệ bởi handshake traffic keys | Nhiều certificate/handshake messages truyền rõ theo quy trình TLS 1.2 cổ điển |
| Server certificate proof | `CertificateVerify` trong full certificate authentication | Có chữ ký trong ServerKeyExchange ở ECDHE suites; exact flow khác, không ép công thức TLS 1.3 |
| Server yêu cầu client certificate | `CertificateRequest` trong TLS 1.3 full handshake, thường sau EncryptedExtensions | `CertificateRequest` có vị trí/sequence theo TLS 1.2 |
| Key derivation | HKDF-based TLS 1.3 key schedule | TLS 1.2 PRF/key expansion theo RFC 5246 |
| 0-RTT | Có thể có early data trong PSK resumption với rủi ro replay, phụ thuộc hỗ trợ | Không phải tính năng handshake TLS 1.2 tiêu chuẩn tương tự |
| Chuẩn nên dùng | Thường **ưu tiên TLS 1.3** khi client/server tương thích | Chỉ giữ khi cần interoperability với cấu hình mạnh và policy cho phép |

**Không áp mô tả “ClientKeyExchange / ChangeCipherSpec làm khóa như TLS 1.2” cho TLS 1.3.** Trong TLS 1.3, có record `ChangeCipherSpec` tương thích giữa một số triển khai, nhưng không có vai trò chuyển khóa theo cách của TLS 1.2; keys được kích hoạt qua state của handshake/key schedule.

### 4.1. Session resumption có thể không gửi lại certificate

Một kết nối TLS 1.3 mới có thể **resume session** bằng PSK/ticket từ kết nối trước. Trong luồng resumption, không nhất thiết có `Certificate`/`CertificateVerify` mới như full certificate handshake. Vì vậy packet capture chỉ có thể giải thích đúng nếu bạn biết đây là full handshake, PSK-only, hay kết hợp PSK với fresh key exchange.

Đặc biệt với mTLS, nếu tổ chức đòi **kiểm danh tính client mới trên mọi request**, cần hiểu cách server, TLS stack, proxy và session resumption gắn identity vào session, và tác động của rotation/revocation. Không mặc nhiên “không thấy client Certificate trong capture = không có mTLS” hay “resumption luôn revalidate client certificate”.

### 4.2. 0-RTT không thay thế xác thực client

TLS 1.3 **0-RTT early data** là tùy chọn của resumption; early data có **rủi ro replay** ngay cả khi bản ghi được mã hóa. Không đặt những thao tác không idempotent hoặc chuyển tiền vào 0-RTT mà không có replay protections. Không nhầm 0-RTT với client-certificate authentication vừa được thực hiện đầy đủ trong cùng full handshake.

### 4.3. ALPN và SNI nằm ở tầng nào?

- **SNI**: gợi ý tên server mà client muốn kết nối để server/proxy chọn certificate/route. Cần tránh sai lệch giữa SNI, HTTP Host/:authority, certificate SAN và policy routing.
- **ALPN**: ví dụ thỏa thuận `h2` cho HTTP/2 hoặc `http/1.1`. ALPN không cấp client identity; nó là protocol negotiation.
- **SAN/hostname validation**: phép kiểm **riêng** mà client thực hiện cho danh tính endpoint mong muốn; không được bỏ chỉ vì SNI đã gửi.
- **HTTP Authorization**: diễn ra ở tầng ứng dụng sau TLS; thường vẫn cần ngay cả khi mTLS xác thực service identity.

---

## 5. Tại sao X.509, CA, keystore và truststore quan trọng cho handshake?

**Chứng thư X.509** là một cấu trúc có chữ ký CA liên kết public key với subject/SAN và các extensions theo chính sách. Trong TLS, chứng thư giúp client/server xác minh public key được trình bày thuộc danh tính được chấp nhận.

### 5.1. Server authentication cần những điều kiện nào?

Với `https://api.example.com`, client không chỉ làm một check:

1. Certificate có cấu trúc X.509 hợp lệ và thuật toán/key strength được chính sách chấp nhận.
2. Chain từ leaf qua intermediate(s) đến **trust anchor** mà client thực sự chấp thuận.
3. Thời hạn `notBefore/notAfter` và revocation/status theo policy phù hợp.
4. BasicConstraints/KeyUsage/EKU và path constraints, đặc biệt CA issuer phải có quyền `keyCertSign` phù hợp.
5. Định danh đích `api.example.com` khớp **DNS Subject Alternative Name** thích hợp; kết nối bằng IP literal cần SAN **iPAddress** phù hợp.
6. Chứng minh server đang sở hữu private key liên quan qua handshake signature/proof, không chỉ sở hữu bản sao leaf certificate.
7. Kiểm transcript/`Finished` và các tham số TLS không bị thay đổi.
8. Kiểm ứng dụng chọn đúng URL, trust configuration và các policy bảo mật liên quan.

`X509Certificate.verify(issuerPublicKey)` chỉ kiểm **chữ ký certificate với public key đã đưa vào**, không tự đảm bảo issuer trusted, hostname đúng hoặc peer đang sở hữu private key. Tương tự, `CertPathValidator("PKIX")` không tự biết hostname của URL nếu ứng dụng không kết hợp endpoint identity verification.

**Không dùng `CN` thay SAN một cách tùy tiện.** TLS identity hiện đại dựa trên các dạng SAN theo quy tắc service identity; JSSE/HTTPS phải làm endpoint identification đúng.

### 5.2. Khi dùng mTLS, client certificate phải có purpose phù hợp

Trong mô hình TLS server nhận client certificate:

- Server truststore có CA/trust anchors cho **client identities**, không chỉ CA dùng cấp server certificates.
- Client leaf có ExtendedKeyUsage phù hợp, thường `clientAuth` (OID `1.3.6.1.5.5.7.3.2`), KeyUsage phù hợp với signature mechanism.
- Server phải quyết định **có chấp nhận client identity này không**, không chỉ “bất kỳ chain dưới root đều được phép”.
- Các profile nội bộ có thể dùng SAN URI, DNS, email hoặc Subject DN theo policy; phải xác định identity source rõ và tránh coi CN tự do là quyền truy cập.
- Nếu certificate bị revoke, mất private key hoặc service không còn quyền, cần vòng đời key/trust/revocation và authorization cập nhật.

### 5.3. Keystore và truststore

```text
ONE-WAY TLS
===========
Server:
  server.p12 = server private key + server leaf + chain
Client:
  truststore.p12 = trusted server CA/root(s)
  (không cần client private key)

mTLS
====
Server:
  server.p12 = server private key + server leaf + chain
  truststore.p12 = trusted client CA/root(s)
Client:
  client.p12 = client private key + client leaf + chain
  truststore.p12 = trusted server CA/root(s)
```

**Truststore không phải nơi copy private key của đối tác.** Một chứng thư CA công khai không nhất thiết bí mật, nhưng **truststore integrity** là an ninh quan trọng: attacker thay trust anchors có thể khiến ứng dụng tin certificate giả.

**Keystore path đúng nhưng password sai** → JVM không load private key. **Truststore có cert riêng lẻ không được phép** → chain validation sai hoặc mở rộng trust quá rộng. **Certificate chain thiếu intermediate** → client có thể không xây được path đến root dù root đã trusted.

---

## 6. Java JSSE: API nào tương ứng với hoạt động nào?

**JSSE** (*Java Secure Socket Extension*) là nền tảng Java cho TLS. Một số API nền tảng trên Java 17:

| API | Trách nhiệm chính | Lưu ý |
| --- | --- | --- |
| `SSLContext` | Thiết lập các key managers, trust managers và TLS engine configuration | Cấu hình context sai có thể dẫn đến tin nhầm CA |
| `KeyStore` | Nạp file `PKCS12` hoặc provider store chứa certificate/private-key entries | Có file/alias không tự tạo trust |
| `KeyManagerFactory` / `X509KeyManager` | Chọn private key/certificate **của chính phía này** trình bày khi cần | mTLS client phải có client identity, server phải có server identity |
| `TrustManagerFactory` / `X509TrustManager` | Xác minh certificate chain của **peer** với trust anchors/policy | Tuyệt đối không dùng custom trust-all manager |
| `SSLSocketFactory` | Tạo client TLS sockets | Với raw `SSLSocket` phải cấu hình endpoint identification phù hợp |
| `SSLServerSocketFactory` | Tạo server TLS listen socket | Server quyết định `setNeedClientAuth`/`setWantClientAuth` |
| `SSLSocket` | TLS kết nối, `startHandshake`, ứng dụng đọc/ghi plaintext bytes | Dữ liệu trên wire được TLS record bảo vệ |
| `SSLEngine` | TLS nonblocking/transport-agnostic theo framework | Phải quản lý handshake state, buffers và task callbacks đúng |
| `SSLParameters` | Cấu hình endpoint identification, protocols, cipher suites, ALPN... | `setEndpointIdentificationAlgorithm("HTTPS")` giúp xác minh host ở raw client |
| `SSLSession` | Thông tin protocol, peer certificates/principal, cipher suite | Thông tin peer không đồng nghĩa authorization |
| `HttpsURLConnection` / `HttpClient` | HTTP(S) client trên TLS | Thường nên dùng stack HTTP chuẩn thay vì raw TLS socket |
| `SSLHandshakeException` | Lỗi trong handshake, có thể do chain/hostname/client cert/protocol | Không tắt authentication để “chạy được” |

### 6.1. `setNeedClientAuth(true)` không phải là “cài TLS cho cả hai phía”

Bật `needClientAuth` chỉ là yêu cầu **client trình bày và xác thực certificate**. Server vẫn phải có keystore chứa **server private key/cert**, phải có truststore đúng CA cấp client, và application authorization phải được enforce. Nếu server bật needClientAuth nhưng client không có cert hoặc cert không tin cậy, handshake không hoàn thành.

### 6.2. Raw `SSLSocket` cần endpoint identification rõ ràng

Ví dụ sử dụng JSSE cho client:

```java
SSLSocket socket = (SSLSocket) context.getSocketFactory()
        .createSocket("api.example.com", 443);
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
```

Đây là **đoạn minh họa không độc lập**: cần imports JSSE, `SSLContext context` đã init bằng truststore đúng, kiểm network/exception và giải phóng socket. Thuật toán `HTTPS` dùng quy tắc TLS endpoint identification của JSSE; không tự so hostname bằng `contains` hoặc disable hostname verification.

Raw `SSLSocket` **không nên được giả định tự kiểm hostname như một HTTPS client** nếu bạn chưa đặt cấu hình endpoint identification. Với Java `HttpClient`/`HttpsURLConnection`, hãy giữ xác minh TLS/hostname theo mặc định an toàn, tránh property/`HostnameVerifier` bypass.

### 6.3. mTLS ở reverse proxy hoặc service mesh

Nhiều hệ thống chấm dứt TLS tại ingress/load balancer/Envoy/service mesh. Tại đó mTLS có thể xác thực **workload ngang hàng với proxy**, trong khi Java app nhận kết nối nội bộ từ proxy. Vì vậy:

- Xác định rõ **TLS endpoint** nào kiểm client cert và truststore nằm ở đâu.
- Nếu proxy forward `X-Client-Cert`/principal headers, phải chặn client Internet tự đặt header; proxy tin cậy phải strip/rewrite và kết nối proxy→app cần được bảo vệ tương ứng.
- Không để Java app coi mọi HTTP request từ proxy là cùng identity rồi bỏ authorization theo tenant/action.
- Kiểm rotation/expiry/revocation của workload certificates trong control plane, log identity và policy giữa các hops.

---

## 7. Lab Java 17+: chuẩn bị root CA, server certificate và client certificate

Lab sau dùng **keytool có sẵn với JDK 17**. Mục tiêu là làm rõ mỗi bên sở hữu private key gì và tin CA nào. Ta dùng một **training root CA** ký trực tiếp cả server leaf và client leaf, với **ExtendedKeyUsage khác nhau**.

**Cảnh báo bảo mật:**

- Mật khẩu `changeit`, root CA và private keys tạo ở đây **chỉ dành cho môi trường học**. Không reuse trong production và không commit file `.p12` vào git.
- Các lệnh đưa store password vào command-line để thao tác dễ; trong hệ thống thật, password trên process list/shell history có thể lộ. Hãy dùng secret manager/interactive prompt/provider bảo mật theo policy.
- Chạy lệnh trong **thư mục lab trống** để không ghi đè keystore có sẵn. Không import CA demo vào `cacerts` toàn hệ thống.
- Nếu muốn chạy ví dụ song song hai mode, kết thúc server phiên trước rồi khởi động server mới trên port 8443; chương trình chỉ xử lý một kết nối mỗi lần.
- Dùng **`localhost`** làm hostname, vì chứng thư server sẽ có SAN `DNS:localhost`. Không thay bằng `127.0.0.1` mà giữ nguyên certificate, vì IP literal cần SAN dạng iPAddress.

### 7.1. Tạo training root CA

Lệnh sau sinh RSA CA key pair trong `root-ca.p12`, tự ký root certificate với `BasicConstraints CA:true` và `KeyUsage keyCertSign/cRLSign`:

```shell
keytool -genkeypair -alias lab-ca -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Training TLS Root CA, O=Learning, C=VN" -validity 3650 -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -keystore root-ca.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
```

Export **public** CA certificate:

```shell
keytool -exportcert -alias lab-ca -keystore root-ca.p12 -storepass changeit -file root-ca.pem -rfc
```

`root-ca.p12` chứa private key của CA và phải được bảo vệ. `root-ca.pem` là public certificate có thể dùng để thiết lập trust anchor. Self-signed root **không tự đáng tin**, cho đến khi relying party đưa nó vào truststore có chủ đích. `pathlen:0` phù hợp vì lab root ký leaf trực tiếp, không tạo intermediate CA.

### 7.2. Sinh server key pair và CSR

```shell
keytool -genkeypair -alias tls-server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost, O=Learning, C=VN" -validity 365 -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
keytool -certreq -alias tls-server -keystore server.p12 -storepass changeit -file server.csr -ext "SAN=dns:localhost"
```

CSR chứa server public key và đề nghị cấp SAN. CA phải kiểm đúng identity/policy; việc CSR đề nghị `SAN=dns:localhost` không có nghĩa CA thực luôn phải chấp nhận mọi DNS name tùy ý.

### 7.3. CA ký server leaf với `serverAuth`

```shell
keytool -gencert -alias lab-ca -keystore root-ca.p12 -storepass changeit -infile server.csr -outfile server.pem -rfc -validity 365 -ext "SAN=dns:localhost" -ext "KU:critical=digitalSignature" -ext "EKU=serverAuth" -ext "BC=ca:false"
```

Nạp CA certificate rồi certificate reply vào `server.p12`:

```shell
keytool -importcert -alias lab-ca -file root-ca.pem -keystore server.p12 -storepass changeit -noprompt
keytool -importcert -alias tls-server -file server.pem -keystore server.p12 -storepass changeit -noprompt
```

Alias `tls-server` là private-key entry cùng certificate chain để JSSE server xuất trình. `server.pem` chỉ là public certificate, không thay private key trong `server.p12`.

### 7.4. Sinh client key pair và CSR

```shell
keytool -genkeypair -alias tls-client -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=demo-client, O=Learning, C=VN" -validity 365 -keystore client.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
keytool -certreq -alias tls-client -keystore client.p12 -storepass changeit -file client.csr
```

Dưới đây CA ký một leaf **dành cho client TLS**, không phải server:

```shell
keytool -gencert -alias lab-ca -keystore root-ca.p12 -storepass changeit -infile client.csr -outfile client.pem -rfc -validity 365 -ext "KU:critical=digitalSignature" -ext "EKU=clientAuth" -ext "BC=ca:false"
```

Nhập root trước khi nhập certificate reply vào client keystore:

```shell
keytool -importcert -alias lab-ca -file root-ca.pem -keystore client.p12 -storepass changeit -noprompt
keytool -importcert -alias tls-client -file client.pem -keystore client.p12 -storepass changeit -noprompt
```

**So sánh:** `server.p12` chứa **server private key + server certificate (`serverAuth`)**. `client.p12` chứa **client private key + client certificate (`clientAuth`)**. Cả hai chain cùng về `lab-ca` chỉ để đơn giản lab, không có nghĩa production nên dùng một CA cấp mọi identity/purpose.

### 7.5. Tạo truststore riêng cho lab

```shell
keytool -importcert -alias lab-ca -file root-ca.pem -keystore truststore.p12 -storetype PKCS12 -storepass changeit -noprompt
```

Trong lab cả server và client đều được cấu hình tin root ở `truststore.p12`. Với one-way TLS, **client** dùng truststore này để kiểm server. Với mTLS, **server** cũng dùng để kiểm client. Truststore chứa **public root certificate**, không chứa private key của CA.

### 7.6. Kiểm nội dung chứng thư bằng keytool

```shell
keytool -printcert -file server.pem
keytool -printcert -file client.pem
keytool -list -v -keystore server.p12 -storetype PKCS12 -storepass changeit
keytool -list -v -keystore client.p12 -storetype PKCS12 -storepass changeit
keytool -list -v -keystore truststore.p12 -storetype PKCS12 -storepass changeit
```

Trong kết quả:

- Server certificate: `SAN DNSName: localhost` và `ExtendedKeyUsages serverAuth`.
- Client certificate: `ExtendedKeyUsages clientAuth`.
- KeyStore cho mỗi identity có `PrivateKeyEntry` dưới alias tương ứng.
- Truststore chứa `trustedCertEntry` cho `lab-ca`.
- Issuer của leaf tương ứng root đã ký; root có CA constraints phù hợp.

**Không có stdout cố định cho các lệnh keytool**, vì serial, fingerprints, public key, timestamps và dữ liệu ASN.1 thay đổi theo lần chạy. Hãy đối chiếu **thuộc tính có ý nghĩa** thay vì so nguyên văn output dài.

---

## 8. Java 17+ runnable: server-authenticated TLS và mTLS

Tạo file **`TlsHandshakeLab.java`** trong cùng thư mục với `server.p12`, `client.p12` và `truststore.p12`. Đây là **một Java class chạy ở hai process riêng**: process server lắng nghe cổng 8443, sau đó process client kết nối đến `localhost:8443`.

Hai mode:

- `oneway`: server trình bày server certificate; client xác thực chain và SAN hostname. **Không trình bày client certificate**.
- `mtls`: server bật `setNeedClientAuth(true)`; client nạp `client.p12` và trình bày client certificate khi được yêu cầu. Server kiểm client chain theo `truststore.p12`.
- Cả hai mode đều dùng **TLS 1.3** và cùng bộ ký tự thử `P`/`K`. Traffic keys/record encryption do JSSE thực hiện, không phải do demo tự viết AES.
- Code client raw `SSLSocket` **bật endpoint identification `"HTTPS"`** trước `startHandshake`, tránh một lỗi bảo mật rất phổ biến.

**Lưu ý:** `changeit` được hard-code trong code chỉ để chạy lab khớp lệnh `keytool`; production phải dùng phương thức secret injection/keystore access được bảo vệ. Đây là **minimal TLS learning app**, không phải server HTTP, không có certificate revocation service, IAM, ACL, audit, timeout hay rate limit production.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManager;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLPeerUnverifiedException;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class TlsHandshakeLab {
    private static final char[] PASSWORD =
            "changeit".toCharArray(); // ONLY FOR THE TRAINING LAB
    private static final String[] PROTOCOLS = {"TLSv1.3"};
    private static final int PORT = 8443;

    private static KeyStore loadStore(String path) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(path))) {
            store.load(in, PASSWORD);
        }
        return store;
    }

    // identityPath == null: this endpoint has no client identity.
    private static SSLContext context(String identityPath)
            throws Exception {
        KeyManager[] identities = null;

        if (identityPath != null) {
            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(loadStore(identityPath), PASSWORD);
            identities = kmf.getKeyManagers();
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(loadStore("truststore.p12"));

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(identities, tmf.getTrustManagers(),
                new SecureRandom());
        return context;
    }

    private static void runServer(boolean mutual) throws Exception {
        SSLContext context = context("server.p12");
        try (SSLServerSocket listener = (SSLServerSocket)
                context.getServerSocketFactory()
                        .createServerSocket(PORT)) {
            listener.setEnabledProtocols(PROTOCOLS);
            listener.setNeedClientAuth(mutual);

            // One connection, one request byte: minimal lab only.
            try (SSLSocket socket = (SSLSocket) listener.accept()) {
                socket.setEnabledProtocols(PROTOCOLS);
                socket.startHandshake();

                boolean clientCertificateSeen;
                try {
                    clientCertificateSeen =
                            socket.getSession()
                                    .getPeerCertificates().length > 0;
                } catch (SSLPeerUnverifiedException expected) {
                    clientCertificateSeen = false;
                }

                int request = socket.getInputStream().read();
                if (request != 'P') {
                    throw new IOException("Unexpected demo request");
                }
                socket.getOutputStream().write('K');
                socket.getOutputStream().flush();

                System.out.println("mode="
                        + (mutual ? "mtls" : "oneway"));
                System.out.println("serverHandshake=success");
                System.out.println("protocol="
                        + socket.getSession().getProtocol());
                System.out.println("clientCertificateSeen="
                        + clientCertificateSeen);
                System.out.println("received=P");
            }
        }
    }

    private static void runClient(boolean mutual) throws Exception {
        // One-way client has no private-key identity to present.
        SSLContext context = context(mutual ? "client.p12" : null);
        try (SSLSocket socket = (SSLSocket)
                context.getSocketFactory()
                        .createSocket("localhost", PORT)) {
            socket.setEnabledProtocols(PROTOCOLS);

            // Critical: raw SSLSocket must check intended server name.
            SSLParameters params = socket.getSSLParameters();
            params.setEndpointIdentificationAlgorithm("HTTPS");
            socket.setSSLParameters(params);
            socket.startHandshake();

            boolean serverCertificateSeen =
                    socket.getSession()
                            .getPeerCertificates().length > 0;
            socket.getOutputStream().write('P');
            socket.getOutputStream().flush();

            int reply = socket.getInputStream().read();
            if (reply != 'K') {
                throw new IOException("Unexpected demo response");
            }
            System.out.println("mode="
                    + (mutual ? "mtls" : "oneway"));
            System.out.println("clientHandshake=success");
            System.out.println("protocol="
                    + socket.getSession().getProtocol());
            System.out.println("serverCertificateSeen="
                    + serverCertificateSeen);
            System.out.println("reply=K");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2
                || !("server".equals(args[0])
                     || "client".equals(args[0]))
                || !("oneway".equals(args[1])
                     || "mtls".equals(args[1]))) {
            System.err.println(
                    "Usage: java TlsHandshakeLab server|client oneway|mtls");
            return;
        }

        boolean mutual = "mtls".equals(args[1]);
        if ("server".equals(args[0])) {
            runServer(mutual);
        } else {
            runClient(mutual);
        }
    }
}
```

**Biên dịch** một lần:

```shell
javac TlsHandshakeLab.java
```

### 8.1. Chạy one-way TLS

Mở **terminal 1** tại thư mục lab:

```shell
java TlsHandshakeLab server oneway
```

Mở **terminal 2** cùng thư mục, sau khi server đã bind/lắng nghe:

```shell
java TlsHandshakeLab client oneway
```

**Stdout kỳ vọng của terminal server:**

```text
mode=oneway
serverHandshake=success
protocol=TLSv1.3
clientCertificateSeen=false
received=P
```

**Stdout kỳ vọng của terminal client:**

```text
mode=oneway
clientHandshake=success
protocol=TLSv1.3
serverCertificateSeen=true
reply=K
```

**Diễn giải:** Client nhận server certificate, JSSE kiểm chain dựa trên root trong `truststore.p12` và endpoint hostname `localhost` nhờ `setEndpointIdentificationAlgorithm("HTTPS")`. Server **không yêu cầu** client certificate, và client không nạp private key; do đó `clientCertificateSeen=false`. Một kết nối one-way TLS vẫn mã hóa/xác thực traffic sau handshake, nhưng server **không có TLS-level client identity**.

### 8.2. Chạy mTLS

Đợi cả hai process ở lượt one-way kết thúc. Sau đó mở lại **terminal 1**:

```shell
java TlsHandshakeLab server mtls
```

Trong **terminal 2**:

```shell
java TlsHandshakeLab client mtls
```

**Stdout kỳ vọng của terminal server:**

```text
mode=mtls
serverHandshake=success
protocol=TLSv1.3
clientCertificateSeen=true
received=P
```

**Stdout kỳ vọng của terminal client:**

```text
mode=mtls
clientHandshake=success
protocol=TLSv1.3
serverCertificateSeen=true
reply=K
```

**Diễn giải:** Server bật `setNeedClientAuth(true)` nên JSSE gửi yêu cầu client certificate. Client chọn key/cert trong `client.p12`, server kiểm chain về root trong `truststore.p12` và mục đích client authentication theo JSSE/provider. Client vẫn kiểm server hostname và chain. Mỗi bên chứng minh possession qua handshake phù hợp với TLS 1.3. Hai bên cùng giao tiếp trên record layer được xác thực/mã hóa.

**Để không hiểu sai:** Dòng `clientCertificateSeen=true` chỉ là một cách **quan sát sau khi JSSE handshake thành công**; nó không phải business authorization. Production server cần lấy authenticated principal/certificate trong context được tin, map sang identity có cấu trúc và enforce ACL/IAM/tenant policy.

### 8.3. Thử các trường hợp thất bại quan trọng

**Thử 1 – Server bắt buộc mTLS nhưng client không có cert.**

Terminal server:

```shell
java TlsHandshakeLab server mtls
```

Terminal client:

```shell
java TlsHandshakeLab client oneway
```

Dự kiến: **không có cặp stdout success đầy đủ**. Server từ chối client thiếu chứng thư và ném exception handshake/protocol thích hợp; client cũng có thể thấy error trong handshake hoặc lần đọc/ghi sau đó. **Không cố định chuỗi exception** vì TLS 1.3 alert delivery, provider và thứ tự đóng kết nối có thể khác.

**Thử 2 – Client tin một CA khác.** Thay truststore bằng một truststore an toàn nhưng không chứa root `lab-ca` trong môi trường test. JSSE client không thể xây trust path cho server leaf nên handshake thất bại (thường thấy lỗi `PKIX path building failed` hoặc thông tin tương đương). Không nên giải quyết bằng `TrustManager` nhận mọi chứng thư.

**Thử 3 – Hostname sai.** Tạm thay `createSocket("localhost", PORT)` thành `createSocket("127.0.0.1", PORT)` nhưng giữ server cert chỉ có SAN `DNS:localhost`. Với endpoint identification bật, client phải từ chối vì không có SAN loại `iPAddress` thích hợp cho `127.0.0.1`. **Không** chữa bằng cách tắt hostname verification; cấp lại certificate có SAN đúng theo nhu cầu thực tế.

**Thử 4 – Client certificate `serverAuth` thay vì `clientAuth`.** Nếu server trust manager tuân theo purpose checks như JSSE chuẩn, chứng thư không phù hợp mục đích sẽ bị từ chối. Không dùng server certificate làm client identity chỉ để vượt lỗi config.

**Thử 5 – Certificate hết hạn/bị revoke.** Chứng thư hết hạn phải bị từ chối theo validity policy; kiểm trạng thái thu hồi phụ thuộc cấu hình OCSP/CRL/trust manager và cần thử riêng. Demo này **không kích hoạt kiểm revocation chính thức**. Một chứng thư chưa hết hạn không mặc nhiên được chấp nhận nếu có thông tin revoke đáng tin.

### 8.4. Demo cố ý không có những gì?

- Chưa có nhiều concurrent connections, timeouts, size limits, request parsing hoặc HTTP server.
- Không có KMS/HSM, secret manager, certificate enrollment/renewal, CA chain nhiều cấp, role-based authorization, audit logging hoặc policy revocation production.
- Password store dùng trong code chỉ hợp lệ để học; không hard-code bất kỳ password/key vào JAR triển khai.
- Client truststore và server truststore đang dùng chung root; production có thể tách trusted server CAs và trusted client CAs.
- `TlsHandshakeLab` không tự chống replay của **HTTP/business action**. TLS record layer có bảo vệ integrity/ordering trong session, nhưng một HTTP request hợp lệ có thể bị gửi lại như yêu cầu mới nếu nghiệp vụ không có transaction id/idempotency controls.
- Demo ép TLS 1.3 để luồng quan sát rõ. Với đối tác cũ phải có compatibility policy chứ không tắt bảo mật tùy tiện.

---

## 9. Từ handshake đến identity/authorization trong ứng dụng

### 9.1. Ví dụ mTLS giữa hai microservices

Giả sử service `billing-worker` gọi `payment-api`:

```text
billing-worker                      payment-api
(client)                            (server)

client truststore                   server keystore
  trusts payment CA                   private key + serverAuth cert
client keystore                     server truststore
  private key + clientAuth cert        trusts workload CA
        |                                    |
        +--- mTLS TLS 1.3 handshake --------+
        |                                    |
        | server authenticated              |
        | client authenticated              |
        |                                    |
        +--- POST /refund ------------------>|
                                              |
                                  map verified client principal
                                  check role=refund-writer
                                  check tenant and amount policy
                                              |
        |<--- authorized response ----------+
```

Nếu server chỉ kiểm certificate chain mà không check role hoặc tenant, **mọi service** được cấp cert dưới workload CA có thể bị nhầm thành trusted admin. Mục tiêu của mTLS là làm mạnh danh tính kết nối; policy nghiệp vụ vẫn do server quyết định.

### 9.2. Certificate identity có thể là gì?

Tùy PKI profile:

- **DNS SAN**: hợp với server/hostname theo service identity rules.
- **URI SAN**: dùng trong nhiều workload identity systems, ví dụ định danh SPIFFE; cần chuẩn xác thực URI và trust domain riêng.
- **Subject DN**: có thể dùng cho tổ chức/người, nhưng không nên dựa vào CN tự do nếu PKI không enforce uniqueness/identity policy.
- **OtherName/email/IP SAN**: có ngữ nghĩa theo loại; không được ép tất cả về một string `contains(...)`.
- **Certificate fingerprint/public key pinning**: có thể ràng buộc một key cụ thể cho một hệ thống, nhưng rotation phức tạp và không thay authorization.

Identity mà code đọc qua `SSLSession.getPeerPrincipal()` phải được map theo chuẩn PKI của tổ chức, không cho client tự chọn DN bất kỳ rồi được cấp quyền.

### 9.3. Tách các ranh giới bảo mật

Một request API có thể đi qua:

1. TLS termination ở public ingress (xác thực server).
2. mTLS giữa ingress và internal service.
3. mTLS giữa các sidecars trong mesh.
4. Authentication token cho người dùng cuối.
5. Authorization kiểm user/tenant/object/action.

Mỗi hop có identity/trust policies riêng. **mTLS giữa proxy và app không tự xác thực người dùng cuối**, và một bearer token hợp lệ không thay việc ứng dụng xác thực đúng server TLS khi gọi đối tác.

### 9.4. Rotation và revocation mTLS

Các chứng thư workload thường có hạn ngắn và được tự động cấp lại:

- CA có **issuance policy** xác minh workload identity trước khi cấp cert.
- Agent/proxy thay private key/cert có overlap hợp lý, reload SSLContext/keystore nếu framework cần.
- Peers cập nhật trust bundle/CA rotation có kiểm soát; không xóa CA cũ trước khi các cert phụ thuộc đã hết hiệu lực hoặc được chuyển.
- Kết nối TLS **đang tồn tại** có thể không lập tức bị kết thúc khi certificate bị revoke hoặc hết hạn sau handshake; server cần session lifecycle, reauthentication hoặc connection draining theo security policy.
- Revocation qua CRL/OCSP có tính thực tiễn khác nhau với chứng thư workload sống rất ngắn; thiết kế phải hiểu khả năng kiểm tra của đúng TLS stack.

**Rotate server certificate** không tự đóng mọi TLS sessions cũ; **rotate client certificate** không tự rút quyền của identity đã copy private key. Nếu private key bị lộ, đánh giá scope, thay identity/key material, trust policy, session invalidation và sự cố có thể đã xảy ra.

---

## 10. Bản đồ chẩn đoán lỗi TLS và mTLS trên Java

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm đúng |
| --- | --- | --- |
| `PKIX path building failed` / `unable to find valid certification path` | CA không trusted, thiếu intermediate, cấu hình truststore sai | Kiểm server chain, truststore client, CA phù hợp; không trust-all |
| `No subject alternative names matching IP address` | Kết nối IP literal nhưng chỉ có DNS SAN hoặc thiếu IP SAN | Cấp đúng iPAddress SAN hoặc dùng tên DNS được chứng nhận |
| `No name matching ... found` | Hostname endpoint không khớp SAN | Kiểm URL/SNI/host và SAN; không tắt hostname verification |
| `bad_certificate` / `certificate_unknown` | Certificate lỗi hoặc không được peer chấp nhận | Kiểm chain, alias, EKU/KU, time, CA policy |
| `certificate_required` | Server require client cert nhưng client không trình bày chứng thư phù hợp | Nạp client KeyManager và PKCS12 có private key+chain |
| `Empty client certificate chain` | Client chưa có matching credential/không có key entry | Kiểm `client.p12`, alias, CA hints và key manager |
| `handshake_failure` | Không có giao điểm TLS protocol/cipher/signature, cert/key không phù hợp hoặc lỗi auth | Kiểm `supported_versions`, schemes, provider, certificate policy |
| `protocol_version` | Một bên không hỗ trợ phiên bản mà bên kia yêu cầu | Kiểm JDK, enabled protocols và compatibility policy |
| `No appropriate protocol` | TLS 1.3 disabled hoặc policy/provider không hỗ trợ | Kiểm `jdk.tls.disabledAlgorithms` và cấu hình JSSE |
| `UnrecoverableKeyException` | Password private-key entry sai/keystore hỏng | Kiểm password bảo mật, alias/entry type/provider |
| `FileNotFoundException` khi load store | Path chạy Java khác thư mục tạo file | Kiểm cwd và tham chiếu file keystore |
| `BindException: Address already in use` | Port 8443 đang dùng/server lab cũ chưa dừng | Dừng process trước rồi chạy một server lab |
| `SSLPeerUnverifiedException` ở server one-way | Server không yêu cầu/chưa xác thực client cert | Đó là điều dự kiến với one-way; mTLS cần `needClientAuth` |
| Client handshake success nhưng API `403` | TLS identity hợp lệ nhưng không có quyền nghiệp vụ | Kiểm role/tenant/resource policy |
| TLS 1.3 resumption không thấy `Certificate` mới | PSK/session resumption thay full certificate handshake | Kiểm chế độ session, ticket/PSK và identity binding |
| Certificate valid nhưng kết nối vẫn bị chặn | Revocation, policy, hostname, algorithm, KU/EKU hoặc app authorization | Kiểm tất cả lớp thay vì chỉ validity |

### 10.1. Xem handshake debug logs

Java 17 có thể bật debug JSSE tại **môi trường lab**:

```shell
java -Djavax.net.debug=ssl,handshake TlsHandshakeLab client mtls
```

Kết quả là nhiều dòng debug phụ thuộc JDK/provider/config, **không có stdout cố định**. Có thể thấy TLS version, certificate request, selected signature algorithms, alerts và thông tin về certificate path. Tránh bật debug verbose trong production lâu dài vì logs có thể tiết lộ identity, endpoint, metadata và thông tin nhạy cảm khác.

**Làm đúng thứ tự khi debug:**

1. Xem client đang gọi **đúng hostname và port** không.
2. So chứng thư leaf/server SAN với hostname yêu cầu.
3. Kiểm trusted CA roots và chain intermediates ở **bên verify**.
4. Xem mục đích `serverAuth`/`clientAuth` và signature/key algorithms.
5. Xem server có thực sự yêu cầu mTLS (`CertificateRequest`, need vs want) không.
6. Kiểm client keystore có `PrivateKeyEntry` phù hợp và key manager chọn đúng alias.
7. Kiểm TLS version/cipher suites/trust manager, sau đó mới xem business authorization.

Không chẩn đoán bằng cách tắt hostname check, trust-all CA hoặc chấp nhận mọi client certificate chỉ để “thử cho chạy”.

### 10.2. Lỗi có thể xuất hiện không đối xứng

Khi server mTLS từ chối client thiếu cert, **server có thể nhận một TLS fatal alert và ném `SSLHandshakeException`**. Client, tùy lúc alert đến và cách TLS 1.3 buffering hoạt động, có thể quan sát lỗi khi `startHandshake`, khi ghi hoặc lúc đọc response. Do đó **không dựa vào một exception text cụ thể** để quyết định tính đúng của giao thức; log điều kiện an toàn và kiểm outcome thực tế của cả hai đầu.

### 10.3. TLS và dữ liệu application sau handshake

`startHandshake()` thành công chỉ nói rằng kênh TLS được thiết lập theo policy của JSSE. Tầng ứng dụng phải có:

- request size limits/timeouts, parser/schema validation;
- authentication/authorization ở mức user/service;
- replay controls/idempotency với thao tác có tác động;
- kiểm permission theo tenant/object;
- bảo vệ secret sau khi TLS decrypt và trước khi trả response;
- monitoring và xử lý certificate/key compromise.

---

## 11. Các mẫu cấu hình cần tránh

### 11.1. Trust-all certificate manager

**Không sử dụng đoạn mã kiểu sau trong production, kể cả “chỉ tạm thời”:**

```java
// ANTI-PATTERN: rejects nothing and destroys peer authentication.
TrustManager[] trustAll = new TrustManager[]{
    new X509TrustManager() {
        public void checkClientTrusted(
                X509Certificate[] chain, String authType) {}
        public void checkServerTrusted(
                X509Certificate[] chain, String authType) {}
        public X509Certificate[] getAcceptedIssuers() {
            return new X509Certificate[0];
        }
    }
};
```

Đây là **đoạn cố ý không độc lập để nhận diện anti-pattern**, không phải code nên dùng. Không kiểm chain nghĩa là attacker có thể dùng chứng thư của họ mà cũng được tin. Hãy sửa truststore hoặc certificate chain, không thay trust manager bằng một implementation chấp nhận mọi peer.

### 11.2. Hostname verifier luôn true

```java
// ANTI-PATTERN: do not use!
HostnameVerifier unsafe = (host, session) -> true;
```

Dùng lối tắt này sẽ bỏ xác minh host dự định, tạo cơ hội MITM ngay cả khi một CA nào đó đã ký certificate. Trong raw `SSLSocket` dùng `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`; trong HTTP client chuẩn giữ TLS/hostname verification bật.

### 11.3. Gắn `clientAuth` certificate nhưng không enforce client identity

Một server có thể `setWantClientAuth(true)` và sau đó tin bất kỳ request nào đi qua TLS. Điều này không tạo mTLS bắt buộc; các client không có cert vẫn có thể được chấp nhận. Hãy dùng `needClientAuth`/policy tương đương khi chứng thư client là yêu cầu bắt buộc, và phải **kiểm identity→permission**.

### 11.4. Dùng một root CA làm toàn bộ authorization

Một root được phép ký certificate cho nhiều service không có nghĩa mọi service được quyền gọi endpoint quản trị. Cần certificate profiles/purpose, trust-domain segmentation và authorization ở tầng ứng dụng. Ràng buộc một service identity ổn định, tránh chỉ dựa vào Subject CN có thể tự khai trong quy trình cấp phát yếu.

### 11.5. Kiểm đúng certificate nhưng kiểm sai đối tượng

Nếu proxy kết nối đến `api.example.com` nhưng client HTTP muốn `payments.example.com`, không được tùy tiện lấy identity đã xác minh của một host để biện minh cho host khác. SAN, SNI, HTTP :authority, routing và service policy phải thống nhất theo giao thức.

---

## 12. Câu hỏi tự kiểm tra có đáp án

**1. Trong one-way TLS, client có bắt buộc gửi certificate không?**  
Không. Mô hình thông thường là client xác thực server; client identity có thể được xác thực sau TLS bằng token/cookie. Server có thể không biết client TLS principal.

**2. Trong mTLS, client có được bỏ qua server certificate validation vì server đã yêu cầu client certificate không?**  
Không. mTLS đòi **cả hai** xác thực đúng peer. Client vẫn phải tin đúng server CA và kiểm SAN/hostname.

**3. `ClientHello` có chứng minh client identity không?**  
Không. `ClientHello` quảng bá capabilities/key shares/SNI...; client certificate authentication yêu cầu handshake messages thích hợp và proof-of-possession nếu server bật.

**4. Vai trò `CertificateVerify` của TLS 1.3 là gì?**  
Bên gửi dùng private key tương ứng certificate để ký cấu trúc transcript theo giao thức, chứng minh đang kiểm soát key hợp lệ cho handshake. Gửi certificate công khai một mình không đủ.

**5. Vai trò `Finished` là gì?**  
Ràng buộc và xác minh tính toàn vẹn transcript handshake với secrets/key schedule, phát hiện sửa đổi trái phép và hoàn tất xác thực handshake.

**6. mTLS có chứng minh client có quyền refund không?**  
Không. Nó giúp xác minh service identity; server phải map principal rồi kiểm ACL/IAM/tenant/amount.

**7. Trong Java, `KeyManagerFactory` và `TrustManagerFactory` khác nhau thế nào?**  
Key manager cung cấp private key/cert **của mình** khi cần; trust manager xác minh cert **của đối tác** theo trust anchors/policy.

**8. Server bật `setNeedClientAuth(true)` nhưng không có client truststore. Điều gì có thể xảy ra?**  
Server có thể không xác minh được chain client hoặc dùng trust configuration ngoài ý muốn; cần cấu hình đúng root CA cấp client và chính sách identity.

**9. Vì sao `SSLSocket` raw phải dùng `setEndpointIdentificationAlgorithm("HTTPS")`?**  
Để JSSE kiểm server certificate khớp tên đích theo quy tắc endpoint identification. Chain valid mà hostname sai vẫn không đủ an toàn.

**10. Nếu server cert có SAN `DNS:localhost`, client kết nối bằng IP literal `127.0.0.1` có hợp lệ không?**  
Không theo kiểm đúng IP identity nếu certificate thiếu SAN `iPAddress:127.0.0.1`. Đổi sang hostname đã được cấp hoặc cấp chứng thư đúng loại SAN.

**11. Tại sao TLS 1.3 có forward secrecy trong full ECDHE handshake?**  
Traffic secrets được dẫn xuất từ ephemeral key agreement; lộ private key ký certificate sau đó không tự tái tạo ephemeral shared secrets đã được xử lý/xóa thích hợp.

**12. `setWantClientAuth(true)` có giống `setNeedClientAuth(true)` không?**  
Không. `want` là optional request; `need` bắt buộc xác thực client certificate phù hợp.

**13. Một client không gửi client certificate trong session resumption có tự động nghĩa là không có mTLS không?**  
Không. Cần xem đó có phải resumption/PSK session đã liên kết identity từ phiên trước hay một full handshake. Kiểm chính sách reauthentication của stack.

**14. 0-RTT có an toàn cho mọi thao tác POST thay đổi tiền không?**  
Không. Early data có replay risk; cần chính sách chống phát lại/idempotency và kiểm chặt nghiệp vụ.

**15. Chỉ có certificate PEM trong thư mục server có làm server bắt tay thành công không?**  
Không. Server cần **private key tương ứng** và certificate chain/key manager phù hợp; client phải tin chain và identity của server.

**16. mTLS ở reverse proxy có tự làm Java app xác thực danh tính client cuối không?**  
Không. Cần đường truyền trusted principal từ proxy vào app và bảo vệ header/context; phân biệt mTLS workload identity với user identity.

## 13. Checklist triển khai TLS/mTLS an toàn trên Java

- [ ] **Protocol:** ưu tiên TLS 1.3 theo compatibility; loại bỏ các phiên bản/cipher suites yếu theo policy.
- [ ] **Server key/cert:** private key và leaf chain hợp lệ; SAN đúng host; EKU `serverAuth`, KU/policy đúng; rotation và quyền file/KMS được quản lý.
- [ ] **Client trust:** chỉ tin các CA/trust anchors được phép, giữ JSSE chain validation và HTTPS endpoint identity; không trust-all/hostname-bypass.
- [ ] **Client identity (mTLS):** client có private key + leaf/chain `clientAuth` được chọn đúng alias; server yêu cầu cert (need vs want) và tin đúng client CA.
- [ ] **Proof-of-possession:** xác thực handshake signature, `Finished` và traffic key derivation thông qua TLS stack chuẩn; không tự mô phỏng handshake bằng Java RSA/AES thủ công.
- [ ] **Authorization:** map verified client identity → principal/role/tenant; kiểm từng API/resource/action; không chỉ tin rằng client cert tồn tại.
- [ ] **Key lifecycle:** cấp phát, quản lý PKCS12/KMS/HSM, rotate, revoke, audit, quản lý client/server roots và reauthentication của các session hiện hành.
- [ ] **Network/architecture:** xác định nơi TLS terminate; proxy headers được xác thực; ingress/backend/mesh hops được bảo vệ phù hợp.
- [ ] **Session nuances:** hiểu full handshake vs resumption, chính sách client-auth khi resume và 0-RTT/replay.
- [ ] **Logging:** ghi protocol/cipher/version/identity/outcome có kiểm soát; không log private keys, passwords hoặc decrypted payload nhạy cảm.
- [ ] **Testing:** thành công one-way và mTLS; không có client cert, sai server hostname, CA không trusted, server/client EKU sai, hết hạn, revocation policy, giả identity và permission denied.
- [ ] **Recovery:** có đường làm mới key/certificate, rollback có kiểm soát, handling CA compromise, không tắt verification khi sự cố certificate xảy ra.

**Kết luận:** Trong **one-way TLS**, client xác thực máy chủ; trong **mTLS**, server còn xác thực chứng thư và sở hữu khóa riêng của client. Dù bắt tay thành công, **application authorization**, vòng đời khóa/chứng thư, hostname identity và sự an toàn của dữ liệu sau giải mã vẫn là những trách nhiệm riêng.

## 14. Tài liệu chính thống

- [RFC 8446 – The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): `ClientHello`/`ServerHello`, `CertificateRequest`, `CertificateVerify`, `Finished`, HKDF key schedule, record protection, resumption và early data.
- [RFC 5246 – The Transport Layer Security (TLS) Protocol Version 1.2](https://www.rfc-editor.org/rfc/rfc5246): cấu trúc handshake TLS 1.2 và khác biệt key exchange/record protection.
- [RFC 5280 – Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate path validation, CA constraints, SAN, KeyUsage, ExtendedKeyUsage và CRL.
- [RFC 9525 – Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): quy tắc nhận diện máy chủ theo tên/identity khi dùng TLS.
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): TLS/JSSE, `SSLContext`, key/trust managers, `SSLSocket`/`SSLEngine`, endpoint identification, debug.
- [Java SE 17 – SSLServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html), [SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html) và [SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): cấu hình bắt tay, clientAuth và hostname endpoint identification.
- [Java SE 17 – KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html), [TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html) và [KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): local TLS identity vs peer trust configuration.
- [JDK 17 keytool manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): lệnh tạo PKCS12 key pairs, CSR, certificate replies và trusted roots.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): cấu hình TLS, certificate verification và những anti-pattern vận hành.