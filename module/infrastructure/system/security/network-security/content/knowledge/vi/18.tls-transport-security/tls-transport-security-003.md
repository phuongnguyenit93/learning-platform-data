# Mã hóa đối xứng và bất đối xứng trong TLS

Khi trình duyệt mở một dịch vụ qua HTTPS, nhiều người thường nói “TLS mã hóa bằng khóa công khai của máy chủ”. Cách nói này **không đúng cho TLS hiện đại nói chung**. Trong TLS 1.3, khóa công khai/bí mật có thể được dùng để **thỏa thuận bí mật chung** và **xác thực danh tính**, còn dữ liệu HTTP thực tế thường được bảo vệ bằng **mật mã đối xứng có xác thực (AEAD)**. Không hiểu sự phân công này dễ dẫn tới các nhận định sai như “có chứng chỉ là đủ an toàn”, “RSA dùng để mã hóa toàn bộ phiên” hoặc “lấy được private key của chứng chỉ thì giải mã được mọi bản ghi TLS đã thu trước đó”.

**Mã hóa đối xứng và bất đối xứng trong TLS** là cách các kỹ thuật mật mã phối hợp để bảo vệ kênh truyền: tạo khóa dùng chung, chứng minh danh tính của peer và bảo vệ tính bí mật/toàn vẹn của dữ liệu ứng dụng. Đây là bài thuộc chương **TLS và bảo mật kênh truyền**, module **SECURITY_NETWORK_SECURITY**. Kiến thức được dùng khi thiết kế firewall, VPN, IDS/IPS, DNS bảo mật, Wi-Fi Enterprise, WAF, load balancer, service mesh và hạ tầng cloud an toàn.

Mục tiêu của bài là hiểu **vai trò của từng thuật toán, dữ liệu đi qua các pha handshake, các ranh giới TLS có thể bảo vệ và cách kiểm chứng cấu hình** — không phải tự sáng chế thuật toán mã hóa hay triển khai một TLS stack mới.

## 1. Các thuộc tính an ninh mà TLS hướng tới

| Thuộc tính | Câu hỏi | Cơ chế liên quan |
|---|---|---|
| **Bí mật (confidentiality)** | Người quan sát mạng có đọc được payload ứng dụng không? | AEAD và khóa lưu lượng phiên |
| **Toàn vẹn (integrity)** | Kẻ trung gian có thể sửa nội dung mà client/server không phát hiện không? | AEAD authentication tag, bảo vệ transcript handshake |
| **Xác thực peer (authentication)** | Client có đang nói với máy chủ mà nó dự định kết nối không? | Certificate chain, hostname validation, chữ ký handshake |
| **Bí mật chuyển tiếp (forward secrecy)** | Lộ khóa xác thực dài hạn sau này có giải mã được các phiên đã ghi trước đó không? | (EC)DHE ephemeral và xóa bí mật phiên thích hợp |
| **Tách khóa (key separation)** | Hai chiều hoặc hai giai đoạn có dùng nhầm cùng khóa không? | TLS key schedule, HKDF và traffic secrets |
| **Khả năng chống phát lại** | Bản tin cũ có thể được dùng lại như yêu cầu mới không? | Bảo vệ transcript/record; riêng 0-RTT cần anti-replay ở mức thích hợp |

TLS **không** tự bảo đảm dữ liệu đầu cuối được phép truy cập, server không bị xâm nhập, hay ứng dụng không có lỗi logic. TLS cũng không mặc định che giấu địa chỉ IP, cổng, độ dài/timing traffic hoặc tất cả metadata của quá trình bắt tay.

### 1.1. Ba thuật ngữ phải phân biệt

1. **Encryption:** biến plaintext thành ciphertext bằng khóa và cơ chế thích hợp, phục vụ tính bí mật.
2. **Key agreement:** hai bên tính ra bí mật chung trên kênh công khai mà không phải gửi trực tiếp bí mật đó; ví dụ ECDHE.
3. **Digital signature:** bên sở hữu private key ký thông điệp, bên có public key kiểm tra chữ ký để xác thực và bảo vệ tính toàn vẹn trong ngữ cảnh phù hợp.

**ECDHE không phải một phép mã hóa payload**, còn **RSA/ECDSA signature không phải thuật toán mã hóa đối xứng**. TLS kết hợp các khối xây dựng này theo giao thức được chuẩn hóa.

## 2. Mã hóa đối xứng: lớp bảo vệ dữ liệu truyền đi

**Mật mã đối xứng** dùng bí mật khóa chung cho hai thao tác liên quan: mã hóa và giải mã. TLS tạo ra các khóa riêng cho từng chiều truyền và từng giai đoạn, nên không nên hình dung “client và server dùng đúng một khóa duy nhất cho cả phiên”.

Trong TLS hiện đại, các lựa chọn thường thấy là:

| AEAD cipher | Kích thước khóa | Ý nghĩa | Lưu ý |
|---|---:|---|---|
| **AES-128-GCM** | 128 bit | AES ở chế độ Galois/Counter Mode có mã xác thực | Thường hiệu quả trên CPU có hỗ trợ tăng tốc AES |
| **AES-256-GCM** | 256 bit | AES-GCM với khóa dài hơn | Cần đánh giá hiệu năng của hệ thống/thiết bị thật |
| **ChaCha20-Poly1305** | 256 bit | ChaCha20 mã hóa kết hợp Poly1305 xác thực | Có thể phù hợp thiết bị không có tăng tốc AES chuyên dụng |

Các thuật toán trong bảng là **AEAD (Authenticated Encryption with Associated Data)**: kết hợp **mã hóa và xác minh tính toàn vẹn** của dữ liệu được bảo vệ. Không đánh đồng AES-GCM với AES-CBC hoặc tự thiết kế “AES + một checksum” không có xác thực.

### 2.1. Một AEAD operation gồm những gì?

Khái niệm:

~~~text
Đầu vào:
  K     = traffic key bí mật
  N     = nonce duy nhất theo quy tắc của thuật toán/giao thức
  P     = plaintext
  AAD   = dữ liệu liên kết được xác thực nhưng không mã hóa

Encrypt(K, N, P, AAD) -> ciphertext C và authentication tag T

DecryptAndVerify(K, N, C, AAD, T):
  Nếu xác minh tag thành công -> trả lại P
  Nếu xác minh thất bại       -> báo lỗi, không chấp nhận plaintext
~~~

Đây là **mô hình học thuật**, không phải API của một thư viện. Trong TLS, các giá trị nonce, AAD, record header và sequence number được xây dựng theo **phiên bản giao thức**, không nên cho ứng dụng tự chọn tùy ý.

### 2.2. Vì sao nonce không được tái sử dụng?

Đối với các AEAD như AES-GCM và ChaCha20-Poly1305, tái sử dụng cùng cặp **(khóa, nonce)** trong những điều kiện bị cấm có thể phá vỡ nghiêm trọng bảo mật. TLS có quy tắc sinh nonce dựa trên trạng thái bản ghi và traffic secret, nhằm tránh việc các record thuộc cùng khóa lặp nonce.

Với TLS 1.3, nonce của mỗi record được tạo bằng cách kết hợp **static IV** của traffic key với **sequence number** (được đệm theo chiều dài phù hợp và XOR). Hai chiều sử dụng khóa/IV khác nhau. Khi cập nhật khóa, trạng thái nonce phải tuân thủ quy tắc của giao thức.

Không lấy cách tạo nonce này để tự áp sang giao thức hay thư viện mã hóa khác. Khi viết ứng dụng, hãy dùng **TLS library chuẩn**, không sao chép logic record cryptography.

### 2.3. Đối xứng mạnh không có nghĩa đã xác thực máy chủ

Một phiên có thể dùng AES-GCM rất mạnh nhưng vẫn bị tấn công man-in-the-middle nếu client **không kiểm tra danh tính peer** và chấp nhận khóa/thỏa thuận với sai máy chủ. Mã hóa kênh tới **đúng peer** phụ thuộc cả handshake và chứng chỉ, không chỉ thuật toán record layer.

## 3. Mật mã bất đối xứng: hai công việc khác nhau

**Mật mã khóa công khai (public-key cryptography)** dùng cặp khóa có quan hệ toán học:

- **Public key:** có thể công bố cho bên cần xác minh chữ ký hoặc tham gia cơ chế khóa công khai.
- **Private key:** phải giữ bí mật, dùng để ký hoặc tham gia cơ chế mật mã theo thuật toán.

Trong TLS, thường có **nhiều cặp khóa phục vụ nhiều mục đích**, đặc biệt:

1. Khóa chứng chỉ **dài hạn** của server để ký chứng minh danh tính trong handshake.
2. Khóa **ephemeral** dùng một lần/nhóm phiên thích hợp để thực hiện (EC)DHE và thiết lập bí mật chung.

Không được trộn khóa chứng chỉ dùng để ký với khóa trao đổi bí mật chỉ vì cả hai đều được gọi là “public/private key”.

### 3.1. ECDHE là cơ chế thỏa thuận khóa

**ECDHE (Elliptic-Curve Diffie–Hellman Ephemeral)** là dạng trao đổi/thỏa thuận khóa dựa trên đường cong elliptic và các khóa tạm thời. Ở mức trực quan:

~~~text
Client:
  Sinh private ephemeral a
  Tính public ephemeral A = a * G
  Gửi A

Server:
  Sinh private ephemeral b
  Tính public ephemeral B = b * G
  Gửi B

Client tính Z = a * B
Server tính Z = b * A

Hai bên đạt cùng Z về mặt toán học:
    a * (b * G) = b * (a * G)
~~~

`G` là điểm sinh của nhóm được chuẩn hóa; dấu `*` trong ví dụ biểu diễn phép **nhân vô hướng trên nhóm**, không phải phép nhân số nguyên thông thường. Đây là minh họa khái niệm, **không phải chỉ dẫn tự tính khóa ECDHE**.

Các nhóm được triển khai trong hệ sinh thái TLS có thể bao gồm **X25519** hoặc các đường cong được hỗ trợ khác. Tùy phiên bản và chính sách, còn có **DHE** trên nhóm hữu hạn. Client/server phải kiểm tra peer key share theo quy tắc nhóm và thư viện giao thức.

**Z không được đem trực tiếp dùng làm khóa AES**. TLS đưa shared secret và transcript context vào **key schedule** với HKDF để tạo các handshake/application traffic secrets và từ đó tạo keys/IV phù hợp.

### 3.2. Chữ ký số giúp xác thực handshake

Giả sử server có chứng chỉ chứa public key tương ứng một khóa ký. Server dùng private key để ký phần dữ liệu handshake đã được giao thức quy định; client kiểm tra chữ ký bằng public key từ chứng chỉ **sau khi đã đánh giá tin cậy của chứng chỉ và hostname**.

Các họ thuật toán chữ ký thường gặp:

| Thuật toán | Vai trò phổ biến trong TLS | Không nên hiểu là |
|---|---|---|
| **RSA-PSS / chữ ký RSA phù hợp** | Xác minh danh tính server khi certificate key là RSA và cơ chế được hỗ trợ | RSA đang mã hóa toàn bộ dữ liệu HTTP |
| **ECDSA** | Chữ ký từ khóa elliptic-curve signing | Cùng thuật toán với ECDHE key agreement |
| **Ed25519 / EdDSA khi được hỗ trợ** | Chữ ký số cho một số certificate/handshake profile | Một cipher suite đối xứng |

Sự tương thích giữa **certificate key type**, chữ ký trên chứng chỉ, signature algorithm trong handshake, phiên bản TLS và TLS library cần được kiểm tra riêng. Một certificate RSA vẫn có thể được dùng với **ECDHE để tạo khóa phiên**; không phải cứ RSA certificate là RSA key transport.

### 3.3. Chi phí tính toán và lý do không mã hóa dữ liệu lớn bằng bất đối xứng

Các phép thỏa thuận khóa/chữ ký bất đối xứng thường có chi phí và giới hạn khác so với mã hóa khối/stream cipher. TLS chỉ cần thực hiện những phép tương đối đắt này trong quá trình thiết lập/xác thực kênh hoặc những bước được giao thức quy định; sau đó dùng **AEAD đối xứng** để bảo vệ số lượng lớn application records.

Hãy nhớ mô hình:

~~~text
Mật mã bất đối xứng:
  - Chứng minh danh tính (chữ ký + chứng chỉ)
  - Tạo bí mật chung (ECDHE/DHE)

HKDF key schedule:
  - Trích xuất, ràng buộc và phân tách traffic secrets

Mật mã đối xứng (AEAD):
  - Mã hóa và xác minh dữ liệu trong từng record
~~~

## 4. TLS 1.3 handshake: các bước phối hợp khóa

TLS 1.3 là ví dụ trung tâm để hiểu cách phối hợp các cơ chế trên. Một phiên **full handshake xác thực server bằng chứng chỉ**, không dùng PSK/0-RTT trong ví dụ, có luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant C as TLS Client
    participant S as TLS Server
    C->>S: ClientHello + supported_versions + key_share A + algorithms
    S-->>C: ServerHello + selected key_share B + cipher suite
    Note over C,S: Hai bên tính ECDHE shared secret, HKDF -> handshake traffic keys
    S-->>C: EncryptedExtensions [được mã hóa]
    S-->>C: Certificate [được mã hóa]
    S-->>C: CertificateVerify [chữ ký, được mã hóa]
    S-->>C: Finished [xác thực transcript, được mã hóa]
    Note over C: Kiểm tra chain + SAN/hostname + chữ ký + Finished
    C->>S: Finished [được mã hóa]
    Note over C,S: Derive application traffic secrets, keys và IV
    C->>S: Application Data [AEAD]
    S-->>C: Application Data [AEAD]
~~~

Sơ đồ **rút gọn**: thứ tự và bí mật được chuyển đổi giữa các giai đoạn phải theo TLS 1.3 specification; client/server có thể gửi application data sau những mốc nhất định tùy luồng, và các tình huống như **HelloRetryRequest, client authentication, resumption, 0-RTT** được lược bỏ. Bắt tay QUIC dùng TLS 1.3 nhưng **không truyền application data qua TLS record layer theo cách TLS-over-TCP**.

### 4.1. ClientHello và ServerHello

**ClientHello** mang các khả năng mà client hỗ trợ: phiên bản TLS, nhóm trao đổi khóa, signature algorithms, cipher suites, và thường có key_share phục vụ thỏa thuận khóa. Có thể có hostname trong **SNI (Server Name Indication)** nếu cơ chế phù hợp được sử dụng.

**ServerHello** chọn các thông số được thỏa thuận và cung cấp key_share cần thiết. Từ ECDHE và key schedule, hai bên có thể tạo **handshake traffic keys**.

Các thông điệp `ClientHello` và `ServerHello` của TLS 1.3 thông thường **chưa được mã hóa bởi handshake traffic keys**. Nhiều thông tin sau đó, bao gồm **server Certificate**, được bảo vệ bằng khóa handshake. Vì vậy câu nói “chứng chỉ TLS luôn truyền plaintext” là **không đúng với TLS 1.3 thông thường**.

### 4.2. EncryptedExtensions, Certificate, CertificateVerify

- **EncryptedExtensions:** cung cấp các tham số mở rộng ở giai đoạn handshake được bảo vệ.
- **Certificate:** server gửi certificate chain cần thiết theo cấu hình; trust anchor thường nằm sẵn trong trust store của client, không được tin chỉ vì server tự gửi một certificate tự ký.
- **CertificateVerify:** server chứng minh sở hữu **private key tương ứng với certificate public key** qua chữ ký trên transcript/context phù hợp.
- **Finished:** sử dụng giá trị kiểm tra được dẫn xuất từ bí mật handshake để xác nhận toàn vẹn và tính ràng buộc của handshake transcript.

Client cần **đủ cả việc xác minh certificate và cryptographic handshake**, không chỉ kiểm tra “server gửi được một PEM certificate”. Các trường hợp peer xác thực bằng PSK hoặc mTLS có luồng khác, nhưng nguyên tắc ràng buộc danh tính và khóa vẫn giữ vai trò trung tâm.

### 4.3. Sau Finished: application traffic

Sau khi handshake thành công theo các điều kiện cần thiết, client/server sử dụng **application traffic keys riêng cho từng chiều** để bảo vệ HTTP, API request/response hay dữ liệu ứng dụng khác.

Đối với TLS 1.3, cipher suite chủ yếu chỉ định **AEAD và hash/HKDF hash**. Ví dụ:

| TLS 1.3 cipher suite | AEAD | Hash liên quan |
|---|---|---|
| `TLS_AES_128_GCM_SHA256` | AES-128-GCM | SHA-256 |
| `TLS_AES_256_GCM_SHA384` | AES-256-GCM | SHA-384 |
| `TLS_CHACHA20_POLY1305_SHA256` | ChaCha20-Poly1305 | SHA-256 |

**Tên TLS 1.3 cipher suite không mã hóa tên ECDHE group hoặc thuật toán chứng chỉ/chữ ký**. Chúng được thỏa thuận qua những phần khác của handshake. Đây là điểm khác quan trọng so với cách đặt tên nhiều cipher suite của TLS 1.2.

## 5. HKDF và TLS key schedule

**HKDF (HMAC-based Key Derivation Function)** là cơ chế dẫn xuất khóa dùng những chức năng `Extract` và `Expand`; TLS 1.3 còn có cơ chế `HKDF-Expand-Label` để ràng buộc tên secret/giai đoạn với context.

Đường đi khái niệm:

~~~mermaid
flowchart TD
    E["(EC)DHE shared secret + các input theo TLS 1.3 key schedule"] --> K["HKDF Extract / Expand-Label"]
    H["Handshake transcript hash"] --> K
    K --> HS["Handshake traffic secrets: client/server"]
    K --> MS["Master/application secrets theo key schedule"]
    HS --> HK["Handshake AEAD keys / IVs"]
    MS --> CA["Client application traffic key/IV"]
    MS --> SA["Server application traffic key/IV"]
    CA --> R1["Bảo vệ record client -> server"]
    SA --> R2["Bảo vệ record server -> client"]
~~~

Sơ đồ nhằm giải thích **tính phân tách**, không thể thay bản đặc tả chi tiết. Key schedule TLS 1.3 có nhiều trạng thái và nhãn (early secret, handshake secret, master secret, traffic secrets, exporter/resumption secrets); chính xác những đầu vào nào được dùng ở từng nhánh phụ thuộc full handshake/PSK và lựa chọn key exchange.

### 5.1. Tại sao mỗi chiều cần khóa riêng?

Không dùng chung key/IV cho cả client gửi và server gửi giúp giảm nguy cơ tái sử dụng nonce trong hai chiều và tạo phân tách mật mã rõ ràng. Mỗi chiều có sequence number và traffic secret riêng theo giao thức. Việc chuyển khóa ở các giai đoạn handshake/application cũng phải bảo đảm không áp sai key cho record.

### 5.2. Transcript binding ngăn điều gì?

Các thông số thỏa thuận (phiên bản, key shares, cipher suite và những dữ liệu handshake liên quan) được đưa vào transcript và được xác thực bằng cơ chế Finished/CertificateVerify. Điều này giúp chống việc kẻ trung gian **tùy ý thay đổi thông số bắt tay** mà không bị phát hiện, trong giả định các thuật toán và bước validation được triển khai đúng.

Không chỉ “dùng hash SHA-256 là an toàn”: **hash không tự xác thực người gửi**. An ninh đến từ cách transcript được ràng buộc với bí mật phiên và chữ ký/chứng chỉ, không phải từ giá trị hash công khai đơn lẻ.

### 5.3. KeyUpdate và vòng đời khóa

TLS 1.3 có thông điệp **KeyUpdate** cho phép cập nhật application traffic keys theo quy trình giao thức mà không phải thực hiện full handshake mới. Mỗi cập nhật phải được xử lý theo trạng thái và sequence numbers phù hợp. Sản phẩm có thể có các ngưỡng/chiến lược cập nhật khóa khác nhau.

Đừng nhầm **KeyUpdate** với việc cấp mới certificate, đổi ECDHE shared secret hoặc khởi tạo phiên TLS mới. Trong quản trị vận hành, cần phân biệt **certificate rotation**, **key material lifecycle của handshake**, **resumption session tickets** và **record key update**.

## 6. Forward secrecy và ý nghĩa của khóa ephemeral

**Forward secrecy** trong mô hình TLS dùng (EC)DHE ephemeral nghĩa là: nếu sau này **khóa ký chứng chỉ dài hạn của server** bị lộ, kẻ đã lưu bản ghi mạng từ những phiên cũ **không tự động** tính được bí mật ECDHE của các phiên đó và giải mã application data, nếu các bí mật ephemeral/session không bị lộ và giả định mật mã vẫn giữ.

Ví dụ:

~~~text
Ngày 1:
  Client/server thực hiện ECDHE mới.
  Server ký handshake bằng khóa chứng chỉ.
  Hai bên dùng AEAD keys dẫn xuất cho phiên.

Ngày 30:
  Khóa chứng chỉ của server bị đánh cắp.

Kết luận:
  Chỉ từ khóa ký dài hạn và PCAP đã ghi ngày 1,
  không suy ra đủ AEAD keys của phiên cũ có ECDHE an toàn.
~~~

**Những giới hạn của kết luận:**

- Nếu attacker đã lấy **traffic secrets, ephemeral private keys hoặc plaintext** từ endpoint trong lúc phiên diễn ra, forward secrecy không giúp bảo vệ những dữ liệu đó.
- Lộ khóa ký dài hạn hiện tại vẫn có thể gây **nguy cơ giả mạo máy chủ trong tương lai** cho tới khi chứng chỉ/khóa được thu hồi/thay thế và client kiểm tra đúng.
- Nếu dùng cơ chế **PSK-only** không có (EC)DHE cho một phiên, tính chất forward secrecy đối với việc lộ PSK khác với full (EC)DHE; cần xem đúng chế độ TLS 1.3.
- Nếu ghi lại và giải mã bằng **SSLKEYLOGFILE/traffic secrets trong lab**, đó là hành vi chủ động cung cấp khóa phiên để phân tích, không chứng minh giao thức thiếu bảo mật.
- Forward secrecy không đồng nghĩa **post-compromise security** trong mọi tình huống hay khả năng ngăn một endpoint đang bị kiểm soát đọc dữ liệu.

### 6.1. RSA key transport cũ không giống ECDHE

Trong một số chế độ **TLS 1.2 cũ**, client tạo premaster secret và mã hóa nó tới RSA public key của server; server dùng RSA private key để giải mã. Nếu attacker thu PCAP và sau này lấy được **RSA private key tương ứng**, có thể xuất hiện khả năng khôi phục bí mật của các phiên cũ theo chế độ này.

**TLS 1.3 đã loại bỏ RSA key transport**, không còn cơ chế dùng RSA certificate public key để vận chuyển premaster secret theo cách đó. **RSA signature** vẫn có thể tồn tại như cách xác thực server, khác hoàn toàn RSA key transport.

## 7. TLS 1.2 và TLS 1.3: bảng so sánh đúng vai trò

| Khía cạnh | TLS 1.2 (phụ thuộc cipher suite/chế độ) | TLS 1.3 |
|---|---|---|
| Thỏa thuận khóa | Có thể dùng RSA key transport cũ hoặc (EC)DHE | (EC)DHE và/hoặc PSK theo chế độ được phép; không có RSA key transport |
| Mã hóa record | Có các lựa chọn lịch sử gồm CBC và AEAD; cần chọn an toàn | Các AEAD cipher suites theo TLS 1.3 |
| Bảo vệ chứng chỉ server trong handshake | Chứng chỉ server trong full handshake thông thường truyền trước khi mã hóa record | Chứng chỉ server nằm trong các handshake message đã mã hóa sau ServerHello |
| Forward secrecy | Phụ thuộc key exchange; ECDHE/DHE cung cấp, RSA key transport cũ không | Full (EC)DHE hỗ trợ; cần xét PSK/0-RTT riêng |
| Tên cipher suite | Thường gồm key exchange/auth + cipher + hash | Chủ yếu AEAD + hash; key exchange/signature chọn riêng |
| Handshake complexity | Nhiều lựa chọn di sản và rủi ro cấu hình | Lược bỏ nhiều thuật toán/chế độ cũ |
| Resumption | Session IDs/tickets theo cơ chế TLS 1.2 | PSK-based resumption, có thể kết hợp (EC)DHE |
| 0-RTT | Không theo mô hình 0-RTT TLS 1.3 | Tùy chọn và có nguy cơ replay cần xử lý |

Ví dụ về tên TLS 1.2:

~~~text
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
  ECDHE: thỏa thuận bí mật phiên
  RSA:   xác thực server bằng chữ ký phù hợp
  AES_128_GCM: AEAD bảo vệ dữ liệu
  SHA256: thành phần hash/PRF theo bộ thuật toán

TLS_RSA_WITH_AES_128_GCM_SHA256   # Ví dụ key transport di sản
  RSA:   RSA key transport, không có forward secrecy kiểu ECDHE

TLS_AES_128_GCM_SHA256           # TLS 1.3
  Không ghi rõ ECDHE group hoặc certificate signature algorithm
~~~

Khi điều tra một máy chủ, không chỉ đọc `Cipher : AES256`. Cần ghi **phiên bản TLS, negotiated suite, key exchange group, signature algorithm, certificate validation và khả năng dùng session resumption** trong phạm vi công cụ có thể quan sát.

## 8. Chứng chỉ số và chuỗi tin cậy PKI

Một chứng chỉ X.509 thường chứa public key, danh tính/thuộc tính chủ thể và chữ ký của CA hoặc một bên cấp thích hợp. Khi client kết nối `api.corp.example.test`, việc xác minh cần đặt trong ngữ cảnh **tên đích mà người dùng/ứng dụng thực sự muốn kết nối**.

### 8.1. Các bước xác minh phía client

1. Xây dựng và kiểm tra **certificate chain** tới trust anchor được phép theo trust store của client.
2. Kiểm tra **thời hạn hiệu lực**, chữ ký, ràng buộc CA/basic constraints, chính sách và thuật toán được chấp nhận.
3. So khớp hostname/IP theo **Subject Alternative Name (SAN)** và quy tắc định danh tương ứng; không bỏ qua chỉ vì CN nhìn gần giống.
4. Kiểm tra **Extended Key Usage (EKU)**, key usage và các yêu cầu role nếu profile có áp dụng.
5. Áp chính sách revocation/OCSP/CRL hoặc cơ chế liên quan theo nền tảng/threat model, hiểu rõ các giới hạn online/offline.
6. Kiểm tra **CertificateVerify/Finished** và các bước của handshake để xác thực peer và khóa phiên.

Tùy nền tảng, một số chi tiết validation được hệ điều hành/trình duyệt/thư viện TLS xử lý. **Không dùng “verify=false” hoặc chấp nhận mọi chứng chỉ** như cách khắc phục lỗi lâu dài.

### 8.2. Hai chứng chỉ có thể cùng dùng AES-GCM nhưng không tương đương về tin cậy

Giả sử máy chủ A có certificate chain được trust và SAN khớp `api.corp.example.test`; máy chủ B dùng certificate tự ký không được client trust nhưng cũng đề xuất `TLS_AES_128_GCM_SHA256`.

- Khả năng **mã hóa AEAD** không giải quyết câu hỏi client đang nói với máy chủ nào.
- Nếu client **bỏ qua certificate validation**, nó có thể hoàn tất một phiên mã hóa an toàn về mặt thuật toán với **peer sai**.
- Trong mạng doanh nghiệp, private CA có thể là trust anchor hợp lệ **khi được cài và quản trị có chủ đích**, nhưng không có nghĩa mọi self-signed certificate đều nên chấp nhận.

### 8.3. Public-key pinning, CA rotation và mTLS

Trong một số hệ thống kiểm soát chặt endpoint, client có thể dùng ràng buộc bổ sung tới public key hoặc CA theo cơ chế được quản trị. **Pinning tùy tiện** có thể gây outage khi rotation, nên cần chiến lược backup/rotation rõ ràng.

Với **mutual TLS (mTLS)**, server ngoài việc cung cấp/chứng minh certificate của mình còn yêu cầu client chứng minh danh tính bằng certificate/private key phía client. mTLS hữu ích trong một số mạng nội bộ/service mesh/API giữa workload, nhưng:

- Client certificate identity phải được map tới **role/authorization** cụ thể.
- Mất thiết bị hoặc bị lộ private key cần cơ chế revoke, rotate và xử lý session.
- mTLS tại một proxy chỉ xác thực kết nối **giữa client và proxy**, không tự chứng minh backend đã trực tiếp xác thực client certificate.
- Application vẫn phải kiểm tra quyền truy cập tài nguyên và ranh giới tenant.

## 9. TLS record layer: điều gì thật sự được mã hóa?

Trong TLS-over-TCP điển hình, sau khi có traffic keys, application data được đưa vào các **TLS records** và bảo vệ bằng AEAD. TLS 1.3 còn mã hóa các thông điệp handshake thích hợp sau ServerHello. Những phần metadata phục vụ định tuyến/giao thức ngoài lớp TLS không tự được mã hóa.

~~~mermaid
flowchart LR
    P["HTTP request/response plaintext tại endpoint"] --> T["TLS record protection"]
    K["Application traffic key + IV, sequence number"] --> T
    T --> C["Ciphertext + authentication tag"]
    C --> N["TCP/IP packets đi qua mạng"]
    N --> V["TLS peer verify + decrypt"]
    V --> A["Ứng dụng nhận plaintext được xác thực"]
~~~

### 9.1. AEAD bảo vệ điều gì?

- **Dữ liệu được mã hóa:** application data và các thông điệp handshake nằm trong giai đoạn mã hóa theo TLS version.
- **Dữ liệu xác thực nhưng không mã hóa:** một số header/metadata record theo định nghĩa AAD và giao thức.
- **Không nằm trong TLS payload:** outer IP headers, TCP/UDP ports, một số metadata hostname/ALPN/ClientHello tùy phiên bản và ECH, độ dài và thời điểm truyền gói.

TLS không phải network VPN: nó thường bảo vệ một kênh ứng dụng/transport giữa **hai TLS endpoints**, không mã hóa mọi gói đi qua một máy. HTTPS cũng không tự che mọi truy vấn DNS được thực hiện trước khi thiết lập kết nối.

### 9.2. Sequence number và replay

Trong TLS 1.3-over-TCP, sequence number cho record giúp tạo nonce và kiểm soát tính hợp lệ của luồng record trong đúng trạng thái. AEAD tag phát hiện sửa ciphertext; giao thức/transport và trạng thái phiên còn xử lý việc chấp nhận những bản tin được gửi đúng thứ tự.

Đừng suy “TLS có AEAD nên mọi loại replay ở cấp ứng dụng bị loại”: một request HTTP nghiệp vụ được người dùng hoặc attacker gửi **lại trong một phiên hợp lệ** vẫn có thể được server xử lý nếu thiếu cơ chế idempotency/authorization thích hợp. Rủi ro **0-RTT** có đặc điểm riêng bên dưới.

### 9.3. TLS termination là một trust boundary

Khi browser truy cập một website qua CDN/WAF/reverse proxy:

~~~mermaid
flowchart LR
    B["Browser"] -->|"TLS phiên A"| E["CDN / WAF / LB: kết thúc TLS"]
    E -->|"TLS phiên B hoặc đường nội bộ theo policy"| O["Origin"]
    O -->|"Service mesh mTLS khi được thiết kế"| S["Backend service"]
    E -.->|"Plaintext tại điểm termination"| P["WAF/policy/logging"]
~~~

Khi TLS kết thúc tại edge, **plaintext có thể được xử lý tại edge**. Nếu edge mở một kết nối TLS khác tới origin, đó là **một phiên mới với khóa và chứng chỉ khác**; không phải kênh được mã hóa liên tục từ browser tới backend. Do đó:

- Đánh giá **ai sở hữu khóa chứng chỉ, nơi TLS được terminate, private-key permissions và audit**.
- Xác minh **edge → origin** có mã hóa/xác thực phù hợp, có kiểm tra certificate và identity peer, không chỉ “HTTPS được bật”.
- Giới hạn direct access/bypass vào origin; firewall/private link và authorization vẫn cần thiết.
- Cẩn thận với client IP, header như `X-Forwarded-For` hoặc identity assertions; chỉ tin từ proxy được xác thực/được phép.
- Giới hạn log chứa payload/token nhạy cảm tại nơi đã giải mã, vì TLS bảo vệ in-transit **không tự bảo vệ log lưu plaintext**.

## 10. TLS 1.3 session resumption và 0-RTT

### 10.1. Vì sao có PSK?

Để giảm chi phí handshake khi kết nối lại, TLS 1.3 hỗ trợ **pre-shared key (PSK)** dựa trên trạng thái/secret từ phiên trước hoặc được cấp ngoài băng theo mô hình thích hợp. Trong resumption, hai bên có thể dùng PSK để xác thực/khởi tạo key schedule theo quy tắc TLS.

Hai chế độ cần phân biệt:

- **PSK with (EC)DHE:** dùng cả PSK và thỏa thuận khóa ephemeral, có khả năng cung cấp forward secrecy cho handshake/application data tương ứng theo threat model.
- **PSK-only:** không có đóng góp (EC)DHE mới; khả năng bảo mật khi PSK bị lộ khác với chế độ có ephemeral key exchange.

Chứng chỉ máy chủ có thể **không được truyền lại trong mọi resumption handshake**. Vì thế chỉ nhìn một kết nối resumed mà không thấy certificate **không đồng nghĩa TLS đã bỏ xác thực**; cần xem cơ chế PSK/ticket và nguồn tin cậy được thiết lập trước đó.

### 10.2. 0-RTT early data và replay

TLS 1.3 có thể hỗ trợ **0-RTT early data** trên phiên resumption, cho client gửi application data sớm bằng khóa dẫn xuất từ thông tin PSK trước khi hoàn tất handshake mới. Điều này giảm độ trễ nhưng có **nguy cơ replay**; early data không hưởng forward secrecy từ một (EC)DHE mới.

Không cho các thao tác nhạy cảm, **không idempotent** (ví dụ tạo giao dịch thanh toán, chuyển tiền, thay mật khẩu, gửi email) đi 0-RTT mà không có phân tích và kiểm soát replay phù hợp ở server/edge. Cách an toàn thông dụng là **không chấp nhận 0-RTT cho các endpoint đó**, hoặc chỉ cho những thao tác có thiết kế chống replay/idempotency đúng.

Không nhầm 0-RTT TLS với một yêu cầu HTTP thông thường có retry: cả hai đều cần bảo vệ ứng dụng, nhưng đặc tính bảo mật và trạng thái handshake khác nhau.

### 10.3. Session ticket cũng là tài sản bảo mật

Ticket protection/encryption keys, PSK lifecycle, thời hạn session và chính sách thu hồi có tác động tới resumption. Đội vận hành phải kiểm soát quyền vào secret, rotation, backup và phân phối khóa trong cụm gateway. **Bảo vệ certificate private key nhưng để lộ session ticket key cũng tạo rủi ro khác** cần đánh giá.

## 11. TLS, VPN, DNS, IDS/IPS và Wi-Fi: cùng chủ đề nhưng khác lớp

| Lớp / công nghệ | Đường được bảo vệ | Quan hệ với symmetric/asymmetric TLS |
|---|---|---|
| **HTTPS / API TLS** | Client ↔ TLS endpoint (website/proxy/origin) | TLS thường dùng ECDHE/chữ ký để thiết lập/xác thực, AEAD bảo vệ record |
| **mTLS service mesh** | Proxy/workload ↔ proxy/workload khác | Certificate của cả hai phía và traffic keys riêng mỗi kết nối |
| **IPsec VPN** | Các IP packets qua tunnel tùy chính sách | Có mật mã/trao đổi khóa của riêng IPsec/IKE; không phải TLS record |
| **TLS-based remote-access VPN** | Đường VPN do sản phẩm xác định | Có thể dùng TLS làm một thành phần nhưng route/ACL được quản lý riêng |
| **WPA2/WPA3 Wi-Fi** | STA ↔ AP trên liên kết vô tuyến | Cơ chế WLAN security riêng; EAP-TLS có thể được dùng để xác thực Enterprise |
| **DNS over TLS (DoT)** | Client resolver ↔ DNS server qua TLS | Bảo vệ kênh DNS tới endpoint, không biến resolver thành nguồn dữ liệu DNS luôn đúng |
| **DNS over HTTPS (DoH)** | DNS qua HTTPS/TLS | Bảo vệ transport tới resolver, không tự ngăn DNS phishing hoặc resolver độc hại |
| **IDS/IPS** | Quan sát/chặn ở vị trí sensor | Có thể không thấy HTTP body khi traffic mã hóa và không có quyền giải mã |
| **WAF / CDN / LB** | TLS termination/proxy và bảo vệ HTTP | Có thể phân tích plaintext ở điểm được ủy quyền, tạo trust boundary mới |

### 11.1. Mã hóa khiến IDS/IPS “mù” ở đâu?

Nếu IDS ở trước TLS termination, sensor thường nhìn thấy **metadata kết nối, một phần handshake và ciphertext**, không tự đọc được URI, header và body của HTTP đã mã hóa. Để phát hiện tấn công L7 cần telemetry từ **WAF, reverse proxy, app hoặc endpoint**, hoặc kiến trúc giải mã được phép có quản lý khóa và quyền riêng tư rõ ràng.

Không kết luận “HTTPS có nghĩa lưu lượng vô hại”. Client xác thực với một endpoint độc hại cũng có thể truyền dữ liệu qua TLS mã hóa hợp lệ; mã hóa bảo vệ kênh với **peer được xác minh**, không bảo đảm peer đáng tin về mặt nghiệp vụ.

### 11.2. TLS 1.3 với QUIC/HTTP/3

QUIC dùng TLS 1.3 cho handshake và dẫn xuất khóa nhưng thực hiện **packet protection** trong QUIC, không truyền TLS record layer của TLS-over-TCP theo cách thông thường. Khi kiểm thử một website hỗ trợ HTTP/3, cần phân biệt TCP/TLS và UDP/QUIC; kết luận từ `openssl s_client` tới cổng TCP **không tự xác nhận cấu hình QUIC**.

## 12. Threat modeling cho TLS: các lỗi quan trọng

| ID | Rủi ro | Hiểu nhầm thường gặp | Biện pháp |
|---|---|---|---|
| T01 | **Không kiểm tra chứng chỉ** | Có AES-GCM là đã xác thực server | Bật chain/SAN/hostname validation và quản trị trust store |
| T02 | **Bị lộ certificate private key** | PFS làm lộ khóa không còn nguy hiểm | Rotate/revoke key, phân quyền private key, bảo vệ tương lai |
| T03 | **Dùng RSA key transport cũ** | RSA certificate đồng nghĩa forward secrecy | Không dùng key transport di sản; ưu tiên TLS 1.3/(EC)DHE |
| T04 | **Cho phép phiên bản/thuật toán lỗi thời** | “Hỗ trợ TLS” là đủ | Cấu hình phiên bản và cipher theo chính sách hiện hành, kiểm tra client tương thích |
| T05 | **Chấp nhận mọi CA hoặc hostname sai** | Certificate hết hạn thì bỏ validation tạm | Sửa certificate/PKI đúng, không dùng insecure bypass |
| T06 | **TLS kết thúc ở edge rồi dùng HTTP không kiểm soát** | HTTPS ngoài Internet có nghĩa backend cũng an toàn | Re-encryption/mTLS/private network, network ACL và audit |
| T07 | **Lộ key log / traffic secrets** | Đó chỉ là log debug vô hại | Cấm lưu/thu thập ngoài lab, bảo vệ dữ liệu phân tích |
| T08 | **Nonce hoặc record state sai** | Có thể tự triển khai AEAD mà không cần TLS library | Dùng thư viện TLS chuẩn, cập nhật bảo mật, kiểm thử vận hành |
| T09 | **0-RTT replay** | Early data đã được mã hóa nên mọi POST an toàn | Chặn 0-RTT với thao tác nhạy cảm hoặc thiết kế anti-replay |
| T10 | **PSK/ticket key bị lộ** | Chỉ certificate private key mới cần bảo vệ | Kiểm soát PSK/session ticket keys, vòng đời và HA |
| T11 | **Mất auth sau mTLS proxy** | Backend tự biết client certificate | Xác thực đường proxy-backend, identity binding và AuthZ |
| T12 | **TLS/QUIC config drift** | Kiểm tra TCP 443 nghĩa cả HTTP/3 giống nhau | Kiểm thử TCP/TLS và QUIC riêng |
| T13 | **Thông tin nhạy cảm trong logs sau giải mã** | TLS bảo vệ cả log tại WAF/proxy | Redaction, quyền truy cập, retention và audit |
| T14 | **Không mã hóa dữ liệu sau termination** | Các service cùng VPC đương nhiên tin cậy | Phân đoạn, mTLS khi phù hợp, kiểm tra peer identity |
| T15 | **Cơ chế kiểm tra revocation không rõ** | Một chứng chỉ còn hạn là không thể bị thu hồi | Quy định PKI revocation/rotation và xử lý lỗi validation |
| T16 | **Nhầm cipher suite với authentication** | `TLS_AES_256_GCM_SHA384` chứng minh đang dùng ECDSA | Ghi nhận cả key exchange, signature, chain/hostname và app AuthZ |

## 13. Quan sát an toàn bằng OpenSSL

Mục tiêu lab là **đọc trạng thái/chứng chỉ của một dịch vụ TLS do mình quản lý**, không thu thập khóa bí mật hoặc packet của hệ thống khác. Ví dụ dưới đây dùng `127.0.0.1:8443` làm dịch vụ giả định: máy cần có **TLS server lab thật đang chạy**, certificate có SAN `tls-lab.example.test` và trust chain hợp lệ theo CA lab.

### 13.1. Kiểm tra phiên bản OpenSSL và khả năng cục bộ

~~~bash
# Chỉ đọc phiên bản và thông tin build của công cụ.
openssl version -a

# Liệt kê TLS 1.3 cipher suites mà OpenSSL hiện tại hỗ trợ/cho phép.
# Tính tương thích của tùy chọn phụ thuộc phiên bản OpenSSL.
openssl ciphers -s -tls1_3
~~~

**Danh sách local ciphers không chứng minh server sẽ chọn cipher nào**. Nó mô tả năng lực của thư viện/cấu hình phía kiểm tra, không thay một TLS handshake tới đích.

### 13.2. Kiểm tra một server TLS lab có xác minh hostname

~~~bash
# Chỉ kết nối tới dịch vụ TLS do bạn sở hữu/được phép kiểm tra.
# /path/to/lab-root-ca.pem phải là trust anchor được chuẩn bị đúng.
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername tls-lab.example.test \
  -tls1_3 \
  -verify_hostname tls-lab.example.test \
  -verify_return_error \
  -CAfile /path/to/lab-root-ca.pem \
  -brief
~~~

Trên Windows/PowerShell, cú pháp xuống dòng shell khác với `\` của Bash; có thể đặt các tham số trên **một dòng**. Tham số `-servername` gửi SNI, `-verify_hostname` dùng để kiểm tra tên đích, còn `-verify_return_error` yêu cầu dừng khi validation thất bại. `-CAfile` ở đây chỉ dùng **CA lab tin cậy được chuẩn bị có chủ đích**; không lấy file bất kỳ từ server rồi coi đó là trust anchor.

Nếu OpenSSL báo certificate verify failed, không sửa bằng cách bỏ `-verify_return_error` để “PASS”. Hãy kiểm tra chain, SAN, thời hạn, CA đúng và ngày giờ hệ thống. Một số phiên bản/OpenSSL build không hỗ trợ đủ cờ như ví dụ; hãy kiểm tra `openssl s_client -help` và tài liệu của công cụ trong môi trường được phép.

### 13.3. Đọc thông tin công khai của certificate

~~~bash
# Chỉ đọc certificate đã có trong lab, không mở private key.
openssl x509 -in /path/to/server-certificate.pem -noout -text
~~~

Quan sát **Subject Alternative Name, Subject/Issuer, Validity, Public Key Algorithm, Signature Algorithm, Basic Constraints và Key Usage/EKU** nếu có. Một certificate in ra thuật toán RSA không chứng minh phiên TLS đang dùng RSA key transport; cần **thông tin handshake negotiated** để biết key exchange.

### 13.4. Diễn giải kết quả mà không suy quá mức

Ví dụ đầu ra **giả định**, không phải kết quả từ server thật:

~~~text
Protocol version: TLSv1.3
Ciphersuite: TLS_AES_128_GCM_SHA256
Peer certificate: CN = tls-lab.example.test
Hash used: SHA256
Signature type: RSA-PSS
Server Temp Key: X25519, 253 bits
Verification: OK
~~~

Hàm ý:

- `TLSv1.3`: phiên bản giao thức đã được negotiated.
- `TLS_AES_128_GCM_SHA256`: AEAD bảo vệ record là AES-128-GCM, hash liên quan SHA-256.
- `RSA-PSS` có thể là chữ ký server, **không phải RSA mã hóa HTTP data**.
- `X25519` là nhóm liên quan thỏa thuận khóa ephemeral, không phải thuật toán AEAD.
- `Verification: OK` có ý nghĩa trong **phạm vi chính sách trust/hostname được cấu hình cho công cụ**; không phải bằng chứng app đã phân quyền đúng.

Định dạng chính xác tùy phiên bản OpenSSL, server và các tùy chọn đầu ra; không kỳ vọng mọi dòng xuất hiện giống mẫu.

### 13.5. Điều gì không nên làm trong lab?

- Không tắt certificate verification chỉ để kết nối thành công.
- Không trích xuất/chia sẻ private key hoặc SSLKEYLOGFILE từ máy production.
- Không thử nghiệm các bộ mã cũ trên hệ thống người khác hoặc thay cấu hình production nếu chưa được phép.
- Không dùng Wireshark hoặc traffic capture chứa dữ liệu khách hàng trái quyền.
- Không dùng kết quả một kết nối TCP/TLS làm kết luận cho tất cả node, SNI hostnames, IPv6 và QUIC.

## 14. Ma trận kiểm thử TLS theo thuộc tính cần bảo vệ

| ID | Tình huống | Kết quả mong muốn | Bằng chứng |
|---|---|---|---|
| P01 | Server lab TLS 1.3 với cert hợp lệ | Handshake thành công, AEAD negotiated, validation OK | OpenSSL client logs/cert chain |
| N01 | Hostname truy cập không khớp SAN | Client từ chối | Verify error theo host |
| N02 | Certificate chain không tới trust anchor được phép | Client từ chối | Chain validation |
| N03 | Certificate hết hạn/chưa có hiệu lực | Client từ chối theo chính sách | Time validation |
| P02 | Server sử dụng certificate RSA signature và ECDHE | Phiên vẫn có ECDHE, AEAD bảo vệ data | Key exchange + signature + cipher fields |
| N04 | Server chỉ hỗ trợ cơ chế TLS cũ ngoài chính sách | Kết nối bị từ chối hoặc được đánh dấu không đạt | TLS version/cipher policy logs |
| P03 | Client/server gửi application data qua TLS 1.3 | Payload không hiển thị plaintext trên đường quan sát thụ động | Packet capture lab, thông tin record |
| N05 | Ciphertext/record được sửa trong lab được kiểm soát | Xác minh AEAD thất bại, không chấp nhận plaintext | TLS alert/connection termination theo engine |
| P04 | Resumption có (EC)DHE theo profile | Nhận diện đúng chế độ, không đồng nhất với full cert handshake | Handshake/PSK mode evidence |
| N06 | 0-RTT tới endpoint đổi trạng thái nhạy cảm | Không chấp nhận early data hoặc có anti-replay/idempotency được duyệt | Edge/server policy và app logs |
| P05 | mTLS client hợp lệ | Server xác thực client identity và app kiểm tra quyền | mTLS logs + application AuthZ |
| N07 | Client mTLS thiếu cert/không được phép | Không có quyền truy cập theo thiết kế | Handshake/app auth decision |
| P06 | Browser → WAF → origin có re-encryption | Hai TLS connections được xác thực theo chính sách | Edge/origin peer validation, network policy |
| N08 | Direct origin public bypass | Bị firewall/identity policy từ chối | Ingress rule/action, app logs |
| P07 | HTTP/3/QUIC khi được hỗ trợ | Có kiểm tra riêng QUIC/TLS 1.3 | QUIC-capable client/server telemetry |
| P08 | Certificate rotation theo change window | Client mới/đã mở phiên được xử lý đúng, không gây downtime ngoài dự kiến | PKI, SLO, handshake failure stats |
| N09 | Client cũ/cipher không được phép | Không tự downgrade trái policy | Config, TLS alerts và test results |

**Không thể xác minh an toàn của TLS bằng duy nhất một trường “encryption strength”**. Một bộ kiểm thử tốt bao gồm **đúng peer, đúng khóa, đúng chính sách, đúng điểm kết thúc TLS và đúng quyền ứng dụng**, cộng với khả năng vận hành.

## 15. Triển khai bảo mật kênh truyền trong doanh nghiệp

### Bước 1 — Xác định TLS endpoints và trust boundaries

Vẽ luồng **client → DNS → edge/CDN/WAF → load balancer → origin → service mesh/backend**. Tại mỗi hop ghi rõ nơi TLS bắt đầu/kết thúc, certificate identity, ai kiểm soát private key, kiểm tra phía client/server thế nào và dữ liệu plaintext xuất hiện ở đâu.

### Bước 2 — Chọn giao thức và thuật toán theo policy

Ưu tiên TLS 1.3 nơi có thể, xem xét TLS 1.2 với các cấu hình an toàn khi cần tương thích, hạn chế các phiên bản/chế độ di sản ngoài chính sách. Đảm bảo các thành phần hỗ trợ **(EC)DHE khi cần forward secrecy** và AEAD phù hợp, không thay cipher suite bằng cách suy đoán từ một tên thuật toán.

### Bước 3 — Thiết kế PKI và vòng đời chứng chỉ

Tạo trust anchors phù hợp với client, quản trị SAN/hostname, key usage, quyền private keys, thời hạn, rotation, revocation và rollback. Bảo vệ certificate private keys và session ticket keys, dùng quyền tối thiểu hoặc HSM/KMS khi phù hợp với kiến trúc.

### Bước 4 — Kiểm tra xác thực ở từng hop

Browser kiểm tra certificate của edge; edge kiểm tra certificate origin nếu được cấu hình làm TLS client; service mesh kiểm tra workload identity khi dùng mTLS. Không tin tưởng header identity do client tự gửi nếu không có upstream proxy được xác thực.

### Bước 5 — Kiểm thử canary và đường lỗi

Thử chain/SAN sai, chứng chỉ hết hạn, peer không tin cậy, ciphers/versions ngoài policy, thay certificate, QUIC khác TCP, dịch vụ sau termination, mất CA/OCSP/network và client cũ. Không thử phá handshake hoặc can thiệp dòng traffic production trái quy trình.

### Bước 6 — Giám sát và phản ứng sự cố

Theo dõi TLS version, cipher suite, handshake failure, validation errors, cert expiration, mTLS authorization failures, session resumption metrics và security logs. Nếu lộ private key, khởi động quy trình **thu hồi/thay thế khóa, điều tra ảnh hưởng và kiểm tra log**; không giả định PFS loại bỏ toàn bộ sự cố.

### Bước 7 — Rà soát khi kiến trúc thay đổi

CDN, service mesh, HTTP/3, IP/hostname mới, mở vùng cloud hoặc thay VPN có thể thêm điểm kết thúc TLS. Hệ thống tự động hóa certificate cần có chủ sở hữu, test và audit thay vì chỉ đặt “auto-renew=true” rồi không theo dõi lỗi.

## 16. Bài tập tình huống: certificate RSA nhưng TLS 1.3 dùng AES-GCM

**Bối cảnh giả định:** doanh nghiệp có API tại `api.corp.example.test` phía sau WAF. Kết quả kiểm tra một kết nối HTTPS đến edge:

~~~text
TLS version:           TLS 1.3
Cipher suite:          TLS_AES_128_GCM_SHA256
Server signature:      RSA-PSS
Ephemeral key share:   X25519
Peer certificate:      RSA public key, SAN contains api.corp.example.test
Certificate validation: OK (for the trust configuration used in this lab)
~~~

Kiến trúc:

~~~mermaid
flowchart LR
    C["API client"] -->|"TLS A: AES-128-GCM"| W["WAF edge"]
    W -->|"TLS B: policy chưa được xác minh"| O["Origin API"]
    O -->|"DB connection"| D[("Database")]
~~~

**Câu hỏi:**

1. RSA trong certificate có đang mã hóa toàn bộ nội dung JSON không? Vì sao?
2. X25519, RSA-PSS và AES-128-GCM thực hiện ba công việc nào khác nhau?
3. Nếu khóa ký certificate của edge bị lộ sau ba tháng, có thể kết luận giải mã được toàn bộ PCAP TLS 1.3 thu trước đó không?
4. Nếu WAF kết thúc TLS nhưng edge → origin là HTTP, ranh giới nào có thể lộ plaintext? Các biện pháp kiểm soát cần bổ sung?
5. Nếu origin chỉ dựa vào header `X-Forwarded-Client-Cert` do bất kỳ client nào cũng có thể đặt, rủi ro là gì?
6. Nếu muốn dùng mTLS cho đối tác API, làm thế nào kiểm tra client identity **và quyền truy cập tài nguyên**?
7. Vì sao không dùng `openssl s_client` tới TCP 443 để kết luận HTTP/3/QUIC cũng đã cấu hình như nhau?
8. Nếu edge cho phép TLS 1.3 0-RTT cho `POST /payments`, cần đánh giá điều gì trước khi bật?

**Gợi ý lời giải:**

- TLS 1.3 dùng RSA-PSS để xác minh **chữ ký chứng thực handshake**, còn X25519 thuộc cơ chế ECDHE tạo shared secret; AES-GCM bảo vệ các record. Cipher suite TLS 1.3 không cho biết trực tiếp signing key type hoặc group.
- Với phiên đã dùng ECDHE an toàn và không lộ ephemeral/session secrets, **chỉ** lộ khóa ký chứng chỉ sau này không đủ để giải mã phiên cũ. Nhưng phải rotate/revoke khóa để tránh giả mạo trong tương lai.
- WAF nhận plaintext tại điểm termination; cần bảo vệ quyền truy cập vào WAF/log, xác minh edge → origin có mã hóa và **origin certificate validation**, giới hạn direct-origin bypass.
- Header identity chỉ đáng tin khi được **proxy được xác thực tạo/ghi đè, đường vào bị giới hạn và backend kiểm tra nguồn**; mTLS identity cũng phải map tới permission/tenant cụ thể.
- HTTP/3 dùng QUIC/TLS 1.3 theo mô hình packet protection khác; cần test độc lập. 0-RTT có replay risk nên thao tác thanh toán có thay đổi trạng thái phải được loại trừ hoặc có thiết kế idempotency/anti-replay đúng.

## 17. Checklist mã hóa đối xứng và bất đối xứng trong TLS

- [ ] Phân biệt **mã hóa dữ liệu (AEAD)**, **thỏa thuận khóa ((EC)DHE)** và **xác thực (chữ ký/chứng chỉ)**.
- [ ] Hiểu TLS 1.3 không dùng RSA key transport, kể cả khi certificate của server chứa RSA public key.
- [ ] Đọc đúng tên TLS 1.3 cipher suite: AEAD + hash, không suy ra ECDHE group hay signing algorithm.
- [ ] Có giải thích vì sao traffic keys được dẫn xuất từ shared secret/HKDF, không dùng trực tiếp ECDHE output làm AES key.
- [ ] Biết client/server có traffic keys/IV/sequence state riêng và handshake/application stages khác nhau.
- [ ] Sử dụng TLS library chuẩn, không tự thiết kế nonce, AEAD composition hay certificate validation.
- [ ] Không tái sử dụng nonce với cùng key; không ghi lại/chia sẻ key log hoặc session secrets production.
- [ ] Client kiểm tra chain, SAN/hostname, validity, trust anchor và chính sách revocation/EKU khi cần.
- [ ] Hiểu forward secrecy của ephemeral (EC)DHE và các giới hạn với PSK-only, lộ session keys và compromise tương lai.
- [ ] 0-RTT early data được kiểm soát, không cho thao tác không idempotent nếu không có bảo vệ replay phù hợp.
- [ ] mTLS phải kết hợp client identity với application authorization, không chỉ “client có cert”.
- [ ] Xác định rõ mọi TLS termination tại CDN/WAF/LB, VPN gateway, service mesh và đường giữa các hop.
- [ ] Đánh giá mã hóa/xác thực lại từ proxy tới origin và giới hạn đường bypass vào backend.
- [ ] IDS/IPS/WAF dùng nguồn telemetry phù hợp khi traffic TLS không được giải mã tại sensor.
- [ ] DNS/SNI/IP/traffic timing và một số metadata vẫn có thể lộ; không coi HTTPS là ẩn danh toàn bộ.
- [ ] Kiểm thử TCP/TLS và HTTP/3/QUIC riêng, IPv4/IPv6 khi áp dụng.
- [ ] Có quy trình quản lý certificate private keys, ticket keys, rotation, expiration, revoke và incident response.
- [ ] Có positive/negative tests cho chứng chỉ sai, peer không tin cậy, phiên bản lỗi thời và policy drift.
- [ ] Logs/packet captures tuân thủ privacy, retention và chỉ thu khi được cấp quyền.

**Ghi nhớ:** **TLS không dùng một thuật toán mã hóa đơn lẻ để làm mọi việc.** Trong TLS 1.3, **(EC)DHE thiết lập bí mật phiên**, **chữ ký và PKI chứng minh danh tính**, **HKDF dẫn xuất và phân tách các khóa**, còn **AEAD đối xứng bảo vệ dữ liệu**. An ninh thực tế chỉ đạt được khi các bước này được triển khai chuẩn, **peer được xác minh đúng, TLS termination được kiểm soát và quyền truy cập ứng dụng không dựa vào việc kết nối đã mã hóa**.
