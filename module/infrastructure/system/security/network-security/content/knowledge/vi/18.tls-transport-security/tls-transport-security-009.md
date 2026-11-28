# Perfect forward secrecy trong TLS: bảo vệ phiên quá khứ trước lộ khóa dài hạn

## 1. Perfect forward secrecy là gì?

**Perfect forward secrecy (PFS)**, thường được gọi ngắn hơn là **forward secrecy (FS)**, là một tính chất của cơ chế thiết lập khóa phiên: **nếu khóa xác thực dài hạn của một bên bị lộ về sau, kẻ tấn công đã ghi lại lưu lượng trước đó cũng không thể chỉ nhờ khóa dài hạn ấy mà tính được các khóa phiên cũ**, với điều kiện các giả định mật mã được thỏa mãn và bí mật phiên tạm thời đã được quản lý đúng cách.

Ví dụ, người nghe lén ghi lại các kết nối HTTPS của một hệ thống trong tháng 1. Đến tháng 6, họ lấy được **private key của chứng chỉ TLS server**. Nếu các kết nối tháng 1 đã sử dụng **ephemeral (EC)Diffie–Hellman** đúng cách, việc có private key chứng chỉ tháng 6 **không đủ** để giải mã các bản ghi tháng 1 đã lưu. Ngược lại, ở cơ chế **TLS 1.2 RSA key transport** cũ, private key RSA dùng để giải mã premaster secret có thể giúp giải mã các phiên cũ đã bị ghi lại.

**PFS không có nghĩa dữ liệu không bao giờ bị giải mã.** Nó không bảo vệ trước máy chủ bị xâm nhập **ngay khi phiên đang chạy**, khóa phiên bị rò rỉ, lỗi ứng dụng, người dùng đăng nhập sai trang, hay endpoint chủ động lưu bản rõ và chuyển cho kẻ tấn công.

Trong module **SECURITY_NETWORK_SECURITY**, PFS là một phần quan trọng khi xây dựng **kênh truyền an toàn** cùng TLS, VPN, xác thực, firewall, phân đoạn, DNS security và giám sát. Bài học tập trung vào **bí mật của những phiên TLS đã hoàn tất trước sự kiện lộ khóa dài hạn**, đồng thời nêu rõ tác động của TLS termination, session resumption, 0-RTT và quản trị khóa trong thực tế.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mô hình **ghi lại hôm nay, giải mã sau** (*harvest now, decrypt later*) và giới hạn của PFS.
2. Phân biệt **khóa xác thực dài hạn**, **bí mật Diffie–Hellman tạm thời**, **traffic keys** và **resumption PSK/ticket keys**.
3. So sánh **TLS 1.2 RSA key transport**, **TLS 1.2 ECDHE/DHE** và **TLS 1.3**.
4. Phân tích vì sao **TLS 1.3 PSK-only** và **0-RTT** không mang cùng bảo đảm FS như một handshake mới dùng (EC)DHE.
5. Kiểm tra đúng **protocol, negotiated key exchange, resumption mode và TLS termination point**, thay vì suy từ certificate/cipher name đơn lẻ.
6. Xây dựng chính sách, ca kiểm thử và kế hoạch ứng phó khi private key, ticket key hoặc session secret bị lộ.

## 2. Vấn đề: “ghi lại hôm nay, giải mã sau”

Một kẻ nghe lén trên Wi-Fi, ISP, mạng trung gian hoặc đường mirror có thể **lưu các bản ghi TLS được mã hóa**. Họ chưa đọc được payload tại thời điểm đó, nhưng có thể chờ một bí mật về sau bị lộ.

~~~mermaid
flowchart LR
    C["Client"] -->|"TLS session tháng 1"| S["Server"]
    C -. "Encrypted packets" .-> E["Đối tượng nghe lén: lưu traffic"]
    S -. "Tháng 6: private key bị lộ" .-> K["Kẻ tấn công có khóa dài hạn"]
    E --> Q{"Có thể giải mã dữ liệu tháng 1?"}
    K --> Q
    Q -- "TLS 1.2 RSA key transport" --> X["Có thể, nếu ghi đủ handshake và có các điều kiện cần"]
    Q -- "Fresh (EC)DHE + không lộ session secrets" --> N["Không chỉ nhờ private key chứng chỉ"]
~~~

Mô hình này đặt ra một câu hỏi rất cụ thể: **lộ khóa X sau khi phiên kết thúc có làm lộ bí mật trao đổi trong phiên cũ không?** Câu trả lời phụ thuộc **cách sinh bí mật khóa phiên**, không chỉ phụ thuộc việc dữ liệu được mã hóa bằng AES hay ChaCha20.

### 2.1. Bốn loại bí mật cần tách biệt

| Bí mật / khóa | Mục đích | Nếu bị lộ, điều gì đáng lo? |
| --- | --- | --- |
| **Private key chứng chỉ server** | Chứng minh danh tính server trong handshake có xác thực chứng chỉ | Giả mạo danh tính/tấn công phiên tương lai; đối với TLS 1.2 RSA key transport có thể lộ dữ liệu phiên cũ đã ghi |
| **Ephemeral DH/ECDH private value** | Tham gia trao đổi bí mật dùng cho một handshake | Nếu lộ cùng các dữ kiện cần thiết, có thể ảnh hưởng khóa phiên liên quan |
| **Handshake/application traffic secrets** | Sinh khóa mã hóa/xác thực TLS records của phiên | Có thể giải mã hoặc giả mạo traffic trong phạm vi secret/cipher state liên quan |
| **Resumption PSK/ticket-encryption key** | Cho phép tiếp tục phiên hoặc khôi phục thông tin resumption | Ảnh hưởng phụ thuộc TLS version, PSK mode, thời gian tồn tại và cơ chế lưu/sinh vé |

**PFS chủ yếu nói về lộ khóa dài hạn ở một thời điểm sau phiên**, không bao trùm trường hợp một đối tượng đã lấy được **ephemeral secret, key log hoặc traffic secret** của phiên cũ từ bộ nhớ, log, crash dump hay backup. Vì vậy, **xóa và giới hạn lưu giữ bí mật tạm thời** là điều kiện thực hành quan trọng.

## 3. Nhắc lại: TLS handshake làm những việc gì?

TLS tạo một kênh truyền được bảo vệ trên nền transport, thường là TCP cho HTTPS truyền thống; **QUIC** sử dụng TLS 1.3 để thiết lập khóa bảo vệ các gói QUIC trên UDP. Handshake TLS thực hiện ba nhóm chức năng:

1. **Thỏa thuận phiên bản và thuật toán** được hỗ trợ.
2. **Xác thực peer** theo mô hình, thường là server certificate; có thể có client authentication.
3. **Thiết lập traffic secrets** để mã hóa và xác thực dữ liệu ứng dụng.

Ba nhóm chức năng liên quan nhưng không giống nhau. **Chứng chỉ xác thực server**, còn bí mật phiên trong một handshake FS thường được tạo bằng **fresh ephemeral Diffie–Hellman** và key derivation. Việc trình duyệt hiển thị “ổ khóa HTTPS” chỉ cho biết một số điều kiện kết nối được thỏa mãn; nó **không đủ để chứng minh mọi request/resumption/0-RTT đã có cùng bảo đảm FS**.

### 3.1. Vai trò của public-key cryptography và symmetric cryptography

| Giai đoạn | Ví dụ cơ chế | Điều quan trọng |
| --- | --- | --- |
| Nhận diện server | X.509 certificate và chữ ký số trong handshake | Client xác minh tên, CA chain, hiệu lực và chính sách trust |
| Sinh bí mật chung | Ephemeral (EC)DHE hoặc cơ chế khác tùy phiên bản/mode | Quyết định phần lớn tính chất forward secrecy |
| Dẫn xuất khóa | KDF/HKDF, transcript binding theo phiên bản TLS | Phân tách secrets cho từng mục đích/hướng |
| Bảo vệ dữ liệu | AEAD như AES-GCM hoặc ChaCha20-Poly1305 | Confidentiality và integrity của records/packets theo khóa |

**Không nhầm AEAD với PFS.** AES-GCM bảo vệ dữ liệu bằng một khóa đối xứng; PFS giải thích vì sao **lộ khóa xác thực dài hạn** không tự cho phép tính lại **khóa đối xứng của những phiên trước**.

## 4. Diffie–Hellman và ý nghĩa của “ephemeral”

**Diffie–Hellman (DH)** là cơ chế thỏa thuận bí mật chung mà hai bên có thể dùng các giá trị công khai trao đổi qua mạng để tính cùng một bí mật mà người chỉ nhìn thấy các giá trị công khai khó tính được, dựa trên giả định toán học của nhóm được chọn.

Với mô hình DH truyền thống minh họa:

- Hai bên biết công khai \(p\) và \(g\).
- Client chọn bí mật \(a\), gửi \(A=g^a\bmod p\).
- Server chọn bí mật \(b\), gửi \(B=g^b\bmod p\).
- Client tính \(K=B^a\bmod p\); server tính \(K=A^b\bmod p\).
- Hai giá trị bằng nhau: \(g^{ab}\bmod p\).

**Không dùng số nhỏ trong ví dụ toán học để tạo khóa thật.** Hệ thống thực dùng nhóm/đường cong, thuật toán, tham số và xác thực handshake được lựa chọn theo chuẩn cùng thư viện mật mã có kiểm chứng.

### 4.1. Ephemeral khác static key agreement thế nào?

**Ephemeral** ở đây nghĩa là bí mật đóng góp cho handshake được **tạo mới và có tuổi thọ giới hạn**, không dùng một khóa DH cố định lâu dài để dẫn xuất tất cả các phiên. Chữ **E** trong **DHE** hoặc **ECDHE** nhấn mạnh tính tạm thời này.

~~~mermaid
sequenceDiagram
    participant C as TLS Client
    participant S as TLS Server
    Note over C: Sinh ephemeral private a
    Note over S: Sinh ephemeral private b
    C->>S: Public share A
    S->>C: Public share B + chữ ký/xác thực phù hợp
    C->>C: DH(a, B) -> shared secret
    S->>S: DH(b, A) -> shared secret
    Note over C,S: Dẫn xuất traffic secrets theo transcript/key schedule
    Note over C,S: Không lưu ephemeral private values lâu hơn cần thiết
~~~

Trong **ECDHE**, phép toán được thực hiện trên **nhóm elliptic-curve** hoặc nhóm khóa trao đổi tương ứng, không dùng biểu thức lũy thừa modulo như DHE cổ điển. **X25519** và **secp256r1** là những lựa chọn thường thấy theo hỗ trợ giao thức và thư viện; không giả định tất cả client/server dùng cùng nhóm.

### 4.2. Vì sao private key của chứng chỉ không giải mã được bí mật DH?

Trong handshake **ECDHE được xác thực bằng chứng chỉ**, private key chứng chỉ thường được dùng để **ký hoặc chứng minh danh tính trong handshake**, chứ **không dùng để giải mã trực tiếp một premaster secret đã được client gửi dưới dạng RSA-encrypted** như cơ chế RSA key transport cũ.

Người nghe lén có thể lưu **public key share của client/server, chữ ký, certificate chain** và encrypted TLS records. Sau này có private key chứng chỉ không tự tiết lộ **a** hoặc **b** từng dùng trong trao đổi DH, với giả định thuật toán an toàn và các bí mật tạm đã bị loại bỏ đúng.

**Giới hạn:** Nếu đối tượng đánh cắp được **ephemeral private value** hoặc session/traffic secret bằng cách xâm nhập endpoint khi phiên chạy, bảo đảm nêu trên không còn áp dụng cho secret đã lộ. Nếu private key chứng chỉ bị lộ **trước handshake**, kẻ tấn công còn có thể tìm cách **mạo danh server** trong các phiên mà client chấp nhận danh tính đó.

### 4.3. Freshness và việc tái sử dụng khóa tạm

Một thiết kế chỉ có chữ “ECDHE” trong tên nhưng **tái sử dụng bí mật ephemeral quá rộng**, lưu bí mật lâu dài hoặc dùng thư viện yếu có thể không đáp ứng kỳ vọng giảm thiệt hại khi lộ bí mật. Cần dùng thư viện TLS hiện đại, RNG thích hợp, quản lý lifecycle và các chính sách được hỗ trợ; không tự viết cơ chế sinh/xóa khóa tại tầng ứng dụng.

## 5. TLS 1.2: RSA key transport so với DHE/ECDHE

TLS 1.2 có nhiều kiểu **key exchange**, với tính chất forward secrecy khác nhau. Chỉ xem giao thức ghi “TLSv1.2” là không đủ.

### 5.1. RSA key transport (không có PFS theo mô hình lộ server RSA key)

~~~text
TLS 1.2 RSA key transport — sơ đồ khái niệm:

Client chọn premaster secret.
Client mã hóa premaster secret bằng RSA public key server.
Client gửi dữ liệu RSA-encrypted trong handshake.
Server dùng RSA private key tương ứng để giải mã.
Hai bên dẫn xuất master secret và record keys.

Nếu ai đó lưu handshake cũ và sau này lấy được RSA private key,
họ có thể giải mã premaster secret đã lưu rồi dẫn xuất record keys,
trong điều kiện transcript và dữ liệu cần thiết đều có sẵn.
~~~

Ví dụ tên cipher suite TLS 1.2 thường gặp trong tài liệu cũ:

~~~text
TLS_RSA_WITH_AES_128_GCM_SHA256
~~~

Ở đây **RSA sau tiền tố TLS_** biểu thị kiểu key exchange/authentication liên quan RSA key transport, chứ không chỉ là chứng chỉ dùng RSA. Cần xem **negotiated cipher suite và handshake thực tế**.

### 5.2. ECDHE/DHE key exchange (hỗ trợ FS theo giả định đúng)

~~~text
TLS 1.2 ephemeral key exchange:

Server gửi tham số/key share tạm và dữ liệu xác thực/chữ ký.
Client gửi key share tạm của mình.
Hai bên tính shared secret từ ephemeral private/public values.
Từ đó dẫn xuất master secret và record keys.

Lộ server certificate private key sau khi phiên kết thúc:
  Không tự suy ra ephemeral shared secret từng sử dụng.
~~~

Ví dụ:

~~~text
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256
TLS_DHE_RSA_WITH_AES_128_GCM_SHA256
~~~

Trong hai tên **ECDHE_RSA** và **ECDHE_ECDSA**, phần đầu **ECDHE** là kiểu trao đổi khóa tạm; **RSA/ECDSA** nói về cơ chế xác thực. **Chứng chỉ RSA vẫn có thể được dùng trong kết nối có PFS**, miễn key exchange thực sự là ECDHE/DHE, không phải TLS_RSA.

### 5.3. So sánh TLS 1.2

| Đặc điểm | TLS 1.2 RSA key transport | TLS 1.2 ECDHE/DHE |
| --- | --- | --- |
| Trao bí mật chung | Client gửi premaster secret đã mã hóa bằng RSA public key của server | Hai bên tính bí mật từ các private shares tạm |
| Private key chứng chỉ | Có thể giải mã premaster secret đã ghi trong handshake | Dùng cho xác thực/chữ ký, không trực tiếp giải DH secret |
| FS khi sau này lộ khóa chứng chỉ | **Không**, với các phiên đã được ghi đầy đủ | **Có**, dưới giả định thuật toán và ephemeral secrecy phù hợp |
| Chứng chỉ RSA có dùng được? | Có | **Có** với ECDHE_RSA/DHE_RSA |
| Mức phù hợp hiện nay | Không nên chọn cho thiết kế TLS mới | Là lựa chọn có FS khi còn phải hỗ trợ TLS 1.2 |

**Quan trọng:** TLS 1.2 session resumption, session ticket và cách lưu master secret có các điều kiện riêng; không được suy từ cipher suite **của phiên gốc** rằng mọi **phiên resumed** có bảo đảm độc lập tương đương một handshake ECDHE mới. Phần sau phân tích riêng vấn đề này.

## 6. TLS 1.3: handshake mới dựa trên (EC)DHE và PSK

TLS 1.3 bỏ các cơ chế legacy như **RSA key transport** và nhiều tùy chọn cipher/protocol cũ. Trong handshake có **(EC)DHE key exchange**, các bên trao đổi key shares tạm và dẫn xuất secrets bằng **HKDF-based key schedule** với ràng buộc transcript.

Tuy nhiên, **không nên phát biểu “mọi kiểu bắt tay TLS 1.3 đều có PFS như nhau”**. TLS 1.3 cho phép **PSK key exchange** và **PSK+(EC)DHE**, còn **0-RTT early data** có tính chất riêng.

### 6.1. Full handshake với (EC)DHE

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: ClientHello + supported_versions + key_share
    S->>C: ServerHello + selected key_share
    Note over C,S: Ephemeral (EC)DHE shared secret và HKDF key schedule
    S->>C: EncryptedExtensions + Certificate + CertificateVerify + Finished
    C->>S: Finished
    Note over C,S: Application traffic bảo vệ bởi traffic secrets
    C->>S: 1-RTT encrypted request
    S->>C: 1-RTT encrypted response
~~~

Trong TLS 1.3, phần lớn handshake sau **ServerHello** đã được mã hóa; sự hiện diện của **certificate authentication** và các thông điệp cụ thể phụ thuộc kiểu handshake (PSK-only có khác biệt). Sơ đồ cho **full certificate-authenticated handshake** theo hướng đơn giản hóa.

### 6.2. Cipher suite TLS 1.3 không tự cho biết group trao đổi khóa

Ví dụ TLS 1.3 có cipher suite:

~~~text
TLS_AES_128_GCM_SHA256
TLS_AES_256_GCM_SHA384
TLS_CHACHA20_POLY1305_SHA256
~~~

Các tên trên tập trung vào **AEAD và hash trong key schedule**. Chúng **không ghi ECDHE_RSA hoặc X25519 trong tên** như nhiều cipher suite TLS 1.2. Để xác minh FS của kết nối TLS 1.3, cần biết **loại handshake/key exchange thực sự**: có ephemeral key_share? Có PSK-only? Có 0-RTT?

### 6.3. Ba trường hợp cần phân biệt

| Trường hợp | Bí mật dùng tạo keys | Bảo đảm FS quan trọng |
| --- | --- | --- |
| **Full (EC)DHE handshake** | Fresh ephemeral DH và key schedule TLS 1.3 | Lộ certificate private key sau này không tự làm lộ phiên cũ |
| **PSK + (EC)DHE** | Kết hợp resumption PSK với fresh ephemeral DH | 1-RTT traffic có FS theo các điều kiện của handshake và DH |
| **PSK-only / psk_ke** | Phụ thuộc PSK, không có fresh DH contribution | **Không có cùng FS** khi PSK liên quan bị lộ về sau |

Với **0-RTT data**, ngay cả một resumed connection có fresh (EC)DHE cho 1-RTT sau đó, **0-RTT early data không nhận được forward secrecy từ ephemeral DH chưa diễn ra**. Không nhập chung hai loại dữ liệu dưới một nhãn “TLS 1.3 secure”.

## 7. Session resumption, PSK và 0-RTT: điểm dễ hiểu sai

Tối ưu bắt tay giúp giảm độ trễ và tải máy chủ, nhưng có thể thay đổi mô hình ảnh hưởng khi bí mật bị lộ.

### 7.1. Session resumption là gì?

Trong TLS, **session resumption** cho phép client/server thiết lập một kết nối mới dựa trên thông tin được lưu từ phiên trước, tránh lặp lại toàn bộ các bước tốn chi phí. TLS 1.2 có session IDs và session tickets theo các cơ chế tương ứng; TLS 1.3 dùng **resumption PSKs** (thường được phân phối thông qua NewSessionTicket).

**Resumption secret không phải private key của chứng chỉ**. Một hệ thống có thể bảo vệ tốt certificate key nhưng để **ticket keys/PSKs tồn tại quá lâu hoặc chia sẻ rộng** trong cluster, làm tăng phạm vi ảnh hưởng nếu bị lộ.

### 7.2. TLS 1.2 session ticket và tính chất khóa

Trong một số cơ chế TLS 1.2 session ticket, thông tin phiên gồm **master secret** được server bảo vệ trong ticket bằng một **ticket-encryption key**. Nếu key này và ticket/resumption transcript tương ứng bị lộ về sau, kẻ tấn công có thể khôi phục dữ liệu khóa cần thiết cho những phiên bị ảnh hưởng, tùy thiết kế/cách triển khai.

Vì vậy, **ECDHE ở handshake ban đầu không bảo đảm mọi resumption liên quan có FS độc lập**, đặc biệt nếu **master secret hoặc ticket-encryption key** bị lưu lâu, trích xuất được hay bị dùng chung trên nhiều máy chủ.

**Không gộp mọi cơ chế session ticket làm một cấu trúc cố định**: TLS 1.2 và TLS 1.3 có **key schedule và ticket semantics khác nhau**, các nhà cung cấp có thể dùng thiết kế lưu state/key rotation khác nhau. Cần xác minh phiên bản/protocol và hành vi của TLS stack cụ thể.

### 7.3. TLS 1.3 psk_dhe_ke so với psk_ke

~~~mermaid
flowchart TD
    A["TLS 1.3 resumption"] --> B{"Có fresh (EC)DHE contribution?"}
    B -- "Có: psk_dhe_ke" --> C["1-RTT traffic: FS theo ephemeral DH"]
    B -- "Không: psk_ke" --> D["1-RTT traffic dựa trên PSK: không có FS từ DH mới"]
    A --> E{"Có 0-RTT early data?"}
    E -- "Có" --> F["Early data: không FS; có replay risk"]
    E -- "Không" --> G["Không phát sinh early data"]
~~~

Với **psk_dhe_ke**, quá trình resumption tạo key shares tạm mới để kết hợp PSK và DH secret. **Với psk_ke**, traffic secrets không được củng cố bằng một fresh ephemeral DH của handshake mới.

### 7.4. 0-RTT early data: thêm rủi ro replay

**0-RTT** cho phép client gửi một số dữ liệu ứng dụng sớm dựa trên PSK đã có, **trước khi hoàn tất fresh handshake**. Early data có thể được mã hóa nhưng **không có forward secrecy** theo mô hình này và có thể bị **replay** trong các điều kiện nhất định.

Các hệ thống bật 0-RTT cần:

- Chỉ cho phép những request/operation **replay-safe** theo thiết kế; không tự coi mọi HTTP GET là vô hại nếu phía sau có side effect.
- Có kiểm soát replay ở server/edge theo năng lực triển khai và phạm vi cụm.
- Ghi rõ endpoint nào được chấp nhận early data, thời hạn/ticket và lý do nghiệp vụ.
- Không cho phép thanh toán, chuyển tiền, thay mật khẩu hoặc nghiệp vụ không idempotent qua 0-RTT nếu không có cơ chế chống replay chặt chẽ và được thiết kế đúng.
- Test được cả **resumed 1-RTT** và **early data**; không nhầm mã hóa với bảo vệ replay/FS.

### 7.5. Bảng tổng hợp theo tình huống lộ bí mật

| Phiên / dữ liệu | Lộ **certificate private key** sau phiên | Lộ **PSK/ticket/traffic secret** liên quan |
| --- | --- | --- |
| TLS 1.2 RSA key transport | Có thể giải mã phiên ghi lại nếu đủ dữ liệu | Có nguy cơ tùy secret bị lộ |
| TLS 1.2 ECDHE full handshake | Không tự giải mã được chỉ từ cert key | Traffic/master secret hoặc resumption state bị lộ có thể phá bảo vệ |
| TLS 1.3 full (EC)DHE | Không tự giải mã được chỉ từ cert key | Nếu traffic/ephemeral secret thực tế bị lộ, có thể ảnh hưởng phiên |
| TLS 1.3 resumption **psk_dhe_ke**, 1-RTT | Không tự giải mã được chỉ từ cert key | Fresh DH bổ sung FS cho 1-RTT trước trường hợp lộ PSK về sau, theo mô hình bảo mật |
| TLS 1.3 resumption **psk_ke**, 1-RTT | Không tự giải mã được chỉ từ cert key | Lộ PSK có thể ảnh hưởng 1-RTT đã được ghi |
| TLS 1.3 **0-RTT early data** | Không tự giải mã được chỉ từ cert key | Lộ PSK liên quan có thể ảnh hưởng early data; còn có replay risk |

**Điều cần nhớ:** “Certificate private key bị lộ” và “resumption PSK/ticket key hoặc traffic secret bị lộ” là **những sự kiện khác nhau**. PFS phải luôn được đánh giá cùng câu hỏi **bí mật nào lộ, lúc nào, phiên nào, và attacker đã ghi được những gì**.

## 8. Forward secrecy khác key rotation và post-compromise security

**Key rotation** thay khóa theo chu kỳ, làm giảm tuổi thọ của bí mật. **PFS** là tính chất rằng **lộ khóa dài hạn về sau không làm lộ session keys cũ theo cơ chế thiết lập khóa**. Hai điều này bổ trợ nhau nhưng **không đồng nhất**.

**Post-compromise security (PCS)** là khái niệm khác: sau khi một attacker từng biết một số bí mật tại thời điểm t, giao thức có thể **phục hồi bảo mật cho những phiên/đoạn về sau** khi có trao đổi khóa mới và attacker không còn kiểm soát các đầu. Không tự suy PCS từ một kết nối được mô tả là PFS.

### 8.1. Thay chứng chỉ không thay bí mật phiên cũ

Một certificate được thay mới không làm thay đổi khóa đối xứng đã dùng mã hóa bản ghi của những phiên đã kết thúc. Nếu handshake cũ thiếu FS, **chỉ rotate certificate hôm nay không làm traffic tháng trước an toàn trở lại** khi private key tương ứng đã bị lộ và bản ghi đã được lưu.

### 8.2. TLS 1.3 KeyUpdate không tạo thêm Diffie–Hellman mới

TLS 1.3 có thông điệp **KeyUpdate** để dẫn xuất traffic keys tiếp theo từ secret trước đó. **KeyUpdate không tự trao đổi một fresh ephemeral DH secret**. Vì vậy, nếu attacker đã có traffic secret cần thiết để tính chuỗi cập nhật, một KeyUpdate đơn thuần **không tạo ra bảo đảm PCS tương đương một authenticated fresh handshake**.

### 8.3. Đặt câu hỏi đúng

~~~text
Sai:  "Đã rotate certificate nên mọi bản ghi TLS cũ đều an toàn."
Đúng: "Handshake cũ dùng cơ chế gì, có PFS không,
       và những session/ticket/traffic secrets nào đã từng bị lộ?"

Sai:  "TLS 1.3 luôn PFS, kể cả 0-RTT."
Đúng: "Kiểm tra full/PSK-DHE/PSK-only và early-data mode."

Sai:  "Một KeyUpdate khôi phục an toàn sau khi lộ traffic secret."
Đúng: "KeyUpdate không tự có fresh DH; phải đánh giá threat model."
~~~

## 9. Giới hạn của PFS và các tình huống không cứu được dữ liệu

| Tình huống | PFS giúp gì? | Điều còn phải giải quyết |
| --- | --- | --- |
| Kẻ nghe lén lưu TLS cũ, sau này lấy **private key chứng chỉ server** | Bảo vệ bí mật phiên cũ khi dùng fresh ephemeral DH đúng cách | Thu hồi credential, xác minh hoạt động giả mạo và các phiên tương lai |
| Máy chủ bị nhiễm mã độc **ngay trong phiên** | Không che được plaintext/traffic secret khỏi endpoint đã bị chiếm | Hardening, EDR, giảm quyền, cô lập, điều tra |
| Khóa phiên bị ghi trong debug log hoặc crash dump | Không ngăn attacker dùng chính session secret đã lưu | Không lưu secrets, bảo vệ dump/log, chính sách retention |
| Browser/client bị chiếm quyền | Không ngăn attacker đọc dữ liệu trước/sau TLS tại client | Endpoint security, identity, ứng dụng |
| TLS 1.3 0-RTT request bị replay | Không giải quyết replay risk | Chỉ nhận operations replay-safe, anti-replay controls |
| CA/chứng chỉ bị dùng để mạo danh server trong phiên **tương lai** | Không ngăn một peer giả mạo được client tin cậy | Certificate validation, revocation, trust lifecycle |
| Khóa ticket/PSK hoặc cache resumption lộ | Không thể giả định mọi phiên resumed vẫn có FS | PSK-DHE, ticket rotation, scope và expiry |
| Kẻ tấn công có khả năng phá giả định toán học của DH | Bảo đảm FS cổ điển có thể bị đe dọa | Thuật toán/nhóm được đánh giá, chuyển đổi mật mã khi cần |
| TLS được kết thúc tại reverse proxy rồi backend dùng HTTP | Chỉ bảo vệ đoạn TLS đã thiết lập | TLS/mTLS cho chặng backend, segmentation, IAM |

**PFS không phải mã hóa đầu-cuối (end-to-end encryption)** theo nghĩa người dùng duy nhất đọc được. CDN/WAF/load balancer đã **kết thúc TLS hợp lệ** vẫn có thể thấy plaintext để cache, kiểm tra hoặc định tuyến; PFS bảo vệ các phiên TLS trên những đoạn được thiết lập, không tự ngăn sự truy cập có chủ đích tại điểm giải mã.

## 10. PFS tại reverse proxy, CDN, WAF và service mesh

Trong doanh nghiệp, TLS có thể được **kết thúc, kiểm tra và thiết lập lại nhiều lần**. Mỗi chặng TLS là một phiên/nhóm phiên có thuật toán, keys, ticket state và chính sách riêng.

~~~mermaid
flowchart LR
    U["Browser / Mobile app"] ==>|"TLS 1: Client ↔ CDN"| C["CDN / WAF edge"]
    C ==>|"TLS 2: CDN ↔ Reverse proxy"| R["Reverse proxy"]
    R ==>|"TLS 3 / mTLS: Proxy ↔ Service"| A["Application"]
    A --> D[("Database")]
~~~

**Chỉ cần một chặng quan trọng không dùng TLS hoặc không đáp ứng FS là bảo đảm toàn tuyến không còn đồng đều.** Ví dụ:

~~~text
Client -> CDN:         TLS 1.3 ECDHE, certificate validation đúng
CDN -> Reverse proxy:  TLS 1.2 RSA key transport (legacy)
Proxy -> Application:  HTTP plaintext

Nhận định:
  Client -> CDN có FS theo handshake phù hợp.
  CDN -> Proxy thiếu FS trong RSA key transport.
  Proxy -> App không có bảo vệ TLS ở lớp vận chuyển này.

Không thể mô tả toàn bộ chuỗi là "PFS end-to-end".
~~~

### 10.1. Mỗi điểm kết thúc TLS là một ranh giới tin cậy

| Vị trí | Có thể quan sát gì? | Kiểm soát bổ sung |
| --- | --- | --- |
| Browser/client | Payload trước khi TLS mã hóa và sau khi giải mã | Endpoint security, certificate validation, browser policy |
| CDN/WAF tại TLS termination | HTTP URI, headers, body theo quyền và cấu hình | Quyền truy cập logs, retention, mã hóa dữ liệu, WAF policy |
| Reverse proxy/ingress | Request sau khi giải mã tại proxy | mTLS tới backend, least privilege, log sanitization |
| Service mesh sidecar | Lưu lượng sau khi mTLS được chấm dứt tại proxy/sidecar | Workload identity, sidecar hardening, network policy |
| Application process | Dữ liệu ứng dụng được xử lý | Authorization, secrets handling, input validation |
| NIDS trên đoạn TLS mã hóa | IP/port, timing, record/handshake metadata còn quan sát được | Kết hợp proxy/app/endpoint logs, không suy đoán plaintext |

**TLS 1.3 handshake metadata:** Một phần handshake và nhiều thông tin sau ServerHello đã được mã hóa; trong một số trường hợp **SNI** còn có thể quan sát, nhưng **Encrypted ClientHello (ECH)** khi thực sự được hỗ trợ/triển khai có thể giảm thông tin lộ. Không dựa vào việc sensor thấy certificate của TLS 1.3 trên dây như một giả định mặc định.

### 10.2. mTLS và PFS là hai mục tiêu khác nhau

**Mutual TLS (mTLS)** xác thực cả client và server theo credential thích hợp. **Forward secrecy** phụ thuộc cách tạo traffic secrets. Một kết nối có **mTLS nhưng dùng cơ chế key exchange không cung cấp FS** (chẳng hạn TLS 1.2 legacy) vẫn có rủi ro khi lộ khóa dài hạn; một kết nối TLS có PFS nhưng **không có client certificate** vẫn có thể hợp lệ nếu ứng dụng dùng cơ chế xác thực client khác.

**Không coi PFS là biện pháp thay cho mTLS, OAuth, API authorization hoặc segmentation.**

## 11. TLS 1.3 và QUIC / HTTP/3

**QUIC** tích hợp cơ chế handshake **TLS 1.3** để dẫn xuất keys bảo vệ packet/streams của QUIC. HTTP/3 chạy trên QUIC; nó không phải HTTP/2 trong một TCP/TLS record layer truyền thống.

Các đặc điểm cần phân biệt:

- **QUIC 1-RTT** được bảo vệ bằng keys dẫn xuất từ handshake TLS 1.3 và hưởng tính chất của key exchange đã sử dụng.
- **QUIC 0-RTT** có những hạn chế tương tự TLS 1.3 early data về **FS và replay**, nên ứng dụng vẫn phải có chính sách cho phép thao tác an toàn trước khi handshake hoàn tất.
- QUIC có các **packet-number spaces và cơ chế key update riêng theo đặc tả QUIC**; không bê nguyên thông điệp TLS KeyUpdate của TLS over TCP để giải thích mọi packet QUIC.
- **TLS 1.3 cipher suite name** một mình vẫn không nói đầy đủ đã dùng PSK-only hay PSK+(EC)DHE và early-data state.
- NIDS ở biên thấy UDP/QUIC metadata và các trường còn lộ theo phiên bản, không mặc nhiên thấy HTTP/3 headers hay body sau bảo vệ.

Trong kiến trúc đa giao thức, một website có thể phục vụ **HTTPS over TCP/TLS** và **HTTP/3 over QUIC**. Cần kiểm chứng **cả hai entrypoints** khi tuyên bố chính sách FS cho public API.

## 12. IPsec VPN PFS khác PFS của TLS như thế nào?

Khái niệm forward secrecy cũng xuất hiện ở **IPsec/IKE**, nhưng **thuật ngữ trên giao diện cấu hình và vòng đời SA** có thể khác TLS.

| Khía cạnh | TLS | IPsec / IKEv2 |
| --- | --- | --- |
| Kênh được bảo vệ | TLS records hoặc QUIC protected packets | ESP data plane theo CHILD_SA |
| Xác thực | Thường server certificate, có thể mTLS/PSK | Certificate, PSK và phương thức được IKE hỗ trợ |
| Trao đổi khóa tạm | (EC)DHE trong handshake thích hợp | DH/ECDH khi thương lượng IKE_SA và có thể khi tạo/rekey CHILD_SA theo chính sách |
| Đơn vị khóa | Handshake/application traffic secrets, resumption state | IKE_SA/CHILD_SA, khóa ESP hai chiều |
| Rekey | Handshake mới, traffic key updates và resumption theo protocol | IKE_SA/CHILD_SA rekey theo protocol và chính sách |
| Câu hỏi FS | Lộ server authentication key về sau có lộ phiên TLS cũ? | Lộ khóa dài hạn hoặc SA/key material tương ứng có ảnh hưởng traffic đã ghi ở CHILD_SA nào? |

Không diễn giải nút bật “PFS group” trên firewall IPsec thành bằng chứng mọi kết nối **HTTPS chạy bên trong VPN** có FS. Hai lớp **TLS và IPsec** có key exchange độc lập.

**Phòng vệ nhiều lớp:** IPsec site-to-site có thể bảo vệ kết nối giữa gateway, còn HTTPS/mTLS bảo vệ ứng dụng xuyên qua nhiều hop. Nếu gateway IPsec hoặc TLS proxy bị chiếm quyền, dữ liệu tại điểm giải mã vẫn cần được bảo vệ bằng **authorization, endpoint controls và logging**.

## 13. Cách xác minh PFS trên TLS 1.2 và TLS 1.3

Không nên khẳng định “máy chủ hỗ trợ TLS 1.3” đồng nghĩa “mọi client đang dùng TLS 1.3 (EC)DHE”. Một kết nối thực tế phụ thuộc **client capabilities, server policy, load balancer/CDN, SNI, ALPN, resumption mode, từng region và rollout version**.

### 13.1. Thu những bằng chứng nào?

| Bằng chứng | Giúp trả lời | Không tự chứng minh |
| --- | --- | --- |
| **Negotiated protocol version** | Kết nối dùng TLS 1.2 hay 1.3 | Kiểu key exchange chi tiết của resumption |
| **TLS 1.2 cipher suite** | Có RSA key transport hay ECDHE/DHE ở full handshake? | Secret có bị log/lộ hoặc session resumption bảo vệ ra sao |
| **TLS 1.3 key_share/group và PSK mode** | Có fresh (EC)DHE contribution hay PSK-only? | Early data đã bị replay hay chưa |
| **Resumption/early-data state** | Có resume, psk_dhe_ke/psk_ke, 0-RTT? | Mọi ticket key/PSK được lưu an toàn |
| **TLS termination mapping** | Những hop nào độc lập chạy TLS? | Backend plaintext đã được bảo vệ bằng một lớp khác |
| **Server policy/configuration** | Những protocol/algorithm/mode nào được phép | Mọi node đã deploy config giống nhau |
| **Handshake/client telemetry** | Phân bố protocol/mode theo client/region | Không có phiên bị bỏ sót do sampling |
| **Certificate lifecycle** | Chứng chỉ/identity có hợp lệ và được bảo vệ? | Có FS chỉ vì certificate dùng RSA/ECDSA/EdDSA |

### 13.2. Ví dụ lệnh kiểm tra trong lab được ủy quyền

Trên **máy lab do bạn quản lý**, có thể tham khảo cách đọc kết quả handshake bằng công cụ TLS của hệ điều hành. Các lệnh dưới đây **thực hiện kết nối mạng tới dịch vụ** và chỉ nên chạy trong môi trường được cấp phép. Không có yêu cầu chạy các lệnh này trong bài.

~~~sh
# TLS 1.2: đọc negotiated cipher suite và xác nhận certificate.
# Thay lab.example.org bằng hostname LAB thực sự thuộc quyền quản lý.
openssl s_client -connect lab.example.org:443 \
  -servername lab.example.org -tls1_2 -brief

# TLS 1.3: đọc version, cipher, chứng chỉ/verification.
openssl s_client -connect lab.example.org:443 \
  -servername lab.example.org -tls1_3 -brief
~~~

**Không coi tùy chọn -brief là báo cáo đầy đủ về PFS.** Tên cipher TLS 1.3 không nêu key exchange group; kết quả kết nối ban đầu không đại diện cho **resumption/0-RTT**. Ngoài ra, các tùy chọn và cách trình bày output phụ thuộc **OpenSSL version**. Cần xem logs/telemetry hoặc phép kiểm thích hợp của TLS stack để biết PSK mode và early-data handling thực tế.

**Certificate verification:** Khi dùng s_client trong lab, cần xem kết quả kiểm tra trust/hostname theo cấu hình và phiên bản; một lệnh handshake có thể hoàn thành dù certificate không đáng tin nếu công cụ chưa được cấu hình từ chối lỗi. Đừng dùng **“handshake success”** làm bằng chứng danh tính peer đã xác thực đúng.

### 13.3. Đọc tên cipher suite TLS 1.2 đúng cách

~~~text
TLS_RSA_WITH_AES_128_GCM_SHA256
    ^^^            = RSA key transport (không FS khi RSA cert key lộ)

TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
    ^^^^^ ^^^      = ECDHE key exchange, RSA authentication

TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256
    ^^^^^ ^^^^^    = ECDHE key exchange, ECDSA authentication

TLS_AES_128_GCM_SHA256
    (TLS 1.3)      = AEAD/hash; key exchange mode phải xem riêng
~~~

Không kết luận dựa trên chuỗi **RSA** ở mọi vị trí: **ECDHE_RSA có forward secrecy** theo key exchange, còn **TLS_RSA** key transport không có tính chất đó trong threat model nói trên.

### 13.4. Những điểm dễ bỏ sót trong kiểm tra

1. Trang công khai chạy TLS 1.3 nhưng một **legacy API subdomain** vẫn chấp nhận TLS 1.2 RSA key transport.
2. CDN edge hỗ trợ FS nhưng chặng **CDN → origin** dùng TLS cũ hoặc HTTP plaintext.
3. API ở **một region** được nâng cấp nhưng các region/đường DR khác chưa cập nhật.
4. **IPv6** trỏ đến load balancer khác với IPv4 hoặc có chính sách TLS khác.
5. **HTTP/3/QUIC** dùng 0-RTT dù bản kiểm tra chỉ tập trung HTTPS/TCP.
6. TLS 1.3 dùng **PSK-only** trên một profile đặc biệt dù full handshake mặc định có (EC)DHE.
7. **Ticket key** dùng chung cho nhiều nodes tồn tại lâu ngoài ý định, làm tăng phạm vi ảnh hưởng nếu lộ.
8. Các bản **session key logs, heap dumps và backups** vẫn chứa secrets của phiên cũ.

## 14. Thiết kế chính sách TLS khuyến khích forward secrecy

Một chính sách hợp lý không phải chỉ “bật PFS”. Cần phối hợp **protocol versions, handshake modes, algorithms, session resumption, certificate controls, termination architecture và client compatibility**.

### 14.1. Nguyên tắc cấu hình

- Ưu tiên **TLS 1.3 với (EC)DHE hoặc PSK+(EC)DHE** trong những trường hợp phù hợp.
- Khi phải hỗ trợ **TLS 1.2**, chỉ cho phép các **ECDHE/DHE cipher suites** được phê duyệt; không chấp nhận RSA key transport chỉ vì client rất cũ mà không qua đánh giá rủi ro.
- Chọn **nhóm trao đổi khóa hiện đại**, thư viện TLS cập nhật và entropy/RNG được cung cấp bởi nền tảng đáng tin.
- Duy trì **certificate validation** đúng tên miền, trust chain và thời hạn; không tắt xác thực peer để “có PFS”.
- Với TLS 1.3 resumption, ưu tiên **psk_dhe_ke** nếu cần duy trì FS cho dữ liệu 1-RTT; xác định ticket lifetime/rotation theo chính sách.
- Chỉ bật **0-RTT** cho trường hợp nghiệp vụ đã phân tích **replay** và rủi ro early-data secrecy.
- Bảo vệ **private keys, resumption state, traffic secrets và logs**; không xuất key material vào hệ thống quan sát.
- Áp dụng chính sách cho **toàn bộ termination points**, kể cả CDN, WAF, reverse proxy, ingress, sidecar, DR region và IPv6.

### 14.2. Mẫu chính sách khai báo, không phải cấu hình production

~~~yaml
# MẪU MỤC TIÊU BẢO MẬT - không phải schema của một TLS server cụ thể.
policy_id: tls-fs-prod
scope:
  - edge-public-api
  - reverse-proxy-to-origin
  - internal-service-mtls
tls:
  preferred_protocol: TLS1.3
  legacy_tls12:
    allowed_when_justified: true
    permitted_key_exchange: [ECDHE, DHE]
    reject_static_rsa_key_transport: true
  tls13:
    require_fresh_dh_for_1rtt: true
    permitted_psk_resumption_mode: psk_dhe_ke
    zero_rtt_enabled: false
  certificate_validation: required
  strong_key_groups: required
secrets:
  certificate_keys_protected: true
  resumption_keys_lifetime_reviewed: true
  session_key_logging: prohibited_in_production
verification:
  inspect_all_tls_termination_hops: true
  test_ipv4_ipv6_quic_dr_regions: true
  review_resumption_early_data: true
~~~

**Đây là chính sách mục tiêu**, không phải thông số mà mọi server đều hỗ trợ đặt bằng các tên trên. Khả năng ép **psk_dhe_ke**, vô hiệu hóa **psk_ke**, chỉnh ticket policy hoặc phân biệt 0-RTT phụ thuộc TLS stack/framework/provider. Hãy **kiểm tra hành vi thương lượng thực tế** thay vì giả định phần mềm thực thi đầy đủ một bảng YAML.

### 14.3. Cân nhắc backward compatibility

Loại bỏ RSA key transport hoặc TLS versions cũ có thể khiến **client legacy không kết nối**. Điều này cần xử lý bằng **inventory client, kế hoạch nâng cấp, deprecation window, canary, thông báo đối tác và rollback có giới hạn**, chứ không bật lại mọi cipher yếu hoặc tắt certificate validation không thời hạn.

Nếu phải giữ một endpoint legacy, có thể cân nhắc **tách biệt hostname/zone, giới hạn identity/nguồn, tăng logging và kế hoạch loại bỏ**, theo phê duyệt rủi ro. Đừng để exception cho một đối tác khiến toàn bộ public edge chấp nhận RSA key transport.

## 15. Cipher suite, certificate và key exchange: tình huống gây nhầm

### 15.1. Server dùng chứng chỉ RSA có PFS được không?

**Có.** Với TLS 1.2 **ECDHE_RSA**, RSA chứng thực key exchange tạm; với TLS 1.3 certificate RSA có thể xác thực handshake với fresh (EC)DHE. **Thuật toán ký trong chứng chỉ** và **cách tạo traffic secret** là hai vấn đề khác.

### 15.2. Server dùng chứng chỉ ECDSA có chắc PFS?

**Không thể kết luận chỉ từ certificate.** Phải xem giao thức/handshake và những dữ liệu/secret liên quan. ECDSA là thuật toán chữ ký, không tự quyết định mọi resumption/PSK-only/early-data cases.

### 15.3. AES-256 có PFS hơn AES-128 không?

AES key length ảnh hưởng **mức an toàn mật mã của symmetric encryption**, nhưng không tự quyết định forward secrecy khi lộ **certificate private key**. **TLS 1.2 RSA_WITH_AES_256** có thể vẫn thiếu FS, trong khi **ECDHE_WITH_AES_128** có FS theo mô hình khóa tạm.

### 15.4. Đã đổi tên thuật toán cipher suite, có nghĩa đã đổi key exchange?

**Không nhất thiết**. Trong TLS 1.3, cipher suite chủ yếu biểu diễn AEAD/hash; group và PSK mode thương lượng riêng. Với TLS 1.2, nhiều cipher names bao hàm key exchange. Cần đọc theo **đúng phiên bản**.

### 15.5. Server đã khóa TLS1.3-only có thể bỏ qua review resumption không?

**Không.** 0-RTT và psk_ke có tính chất khác với full fresh (EC)DHE. Cần xem resumption policy, lifetime, ticket key protection và sổ audit của các điểm kết thúc TLS.

## 16. Quan hệ giữa PFS và quản trị vòng đời khóa

Một chương trình quản lý khóa đầy đủ cần xét cả **identity keys** và **session/PSK secrets**, chứ không chỉ gia hạn chứng chỉ trước ngày hết hạn.

### 16.1. Danh mục bí mật và chủ sở hữu

| Loại | Owner thường gặp | Vòng đời cần quản lý |
| --- | --- | --- |
| Certificate private key ở CDN/edge | PKI/Platform/Security cùng nhà cung cấp | Tạo, lưu trong KMS/HSM nếu phù hợp, quyền truy cập, renew/revoke |
| Internal mTLS workload keys | Platform/Service Mesh/Security | Xác thực workload, rotation tự động, hạn chế export |
| Ephemeral (EC)DHE values | TLS stack/runtime | Sinh mới đúng cách, không lưu ngoài nhu cầu handshake |
| Application traffic secrets | TLS implementation/process memory | Giới hạn truy cập RAM/dump, debug logging, lifetime |
| TLS session tickets/PSKs | Edge/Ingress/TLS platform | Scope, expiry, key rotation, phân phối cluster, revoke/disable |
| Backup/crash/core dumps | SRE/Security | Encryption, access control, retention, secure deletion |
| TLS configuration/policy | Network/Platform/Security | Version control, approval, test compatibility, deployment audit |

### 16.2. Dùng HSM/KMS có tự tạo PFS không?

**Không.** HSM/KMS có thể bảo vệ private key chứng chỉ, hạn chế export, hỗ trợ audit và giảm khả năng bị đánh cắp credential. Nhưng nếu kết nối TLS 1.2 vẫn dùng **RSA key transport**, sau khi private key tương ứng bị lộ qua một con đường nào đó thì phiên cũ đã ghi vẫn có thể giải mã. **PFS là tính chất của quá trình thiết lập traffic secrets**, không phải nhãn của nơi lưu certificate key.

Ngược lại, dùng ECDHE nhưng để traffic secrets trong **core dump không kiểm soát** vẫn có thể làm lộ phiên. Cần đồng thời có **FS và bảo vệ key material**.

### 16.3. Ticket key rotation: làm đúng nhưng đừng hứa quá mức

Giảm lifetime và phạm vi ticket keys có thể giảm hậu quả của sự cố lộ key, nhưng **không tạo FS cho những phiên PSK-only hoặc early data đã ghi** nếu secret của chúng đã bị lấy và attacker có transcript liên quan. Rotation là phòng vệ giảm phạm vi/tuổi thọ, không phải phép hoàn nguyên bảo mật cho bản ghi quá khứ.

## 17. Forward secrecy, bảo vệ DNS và phân tích lưu lượng mã hóa

PFS ảnh hưởng khả năng **giải mã dữ liệu cũ bằng private key bị lộ**; nó không làm metadata mạng biến mất. Dù TLS có FS:

- Firewall/flow logs vẫn thường thấy **source/destination IP, port, hướng, thời lượng, bps/pps**.
- DNS query có thể quan sát được ngoài TLS nếu client vẫn dùng DNS thông thường; **DoT/DoH** có lớp mã hóa khác cần đánh giá.
- **SNI/ALPN/handshake metadata** có phạm vi hiển thị tùy TLS version, ECH, QUIC và vị trí sensor.
- NIDS có thể phát hiện một số **dấu hiệu mạng hoặc handshake**, nhưng không tự đọc được HTTP payload mã hóa nếu không có quyền/điểm giải mã.
- Logs sau điểm TLS termination có thể chứa payload hoặc dữ liệu cá nhân; **không dựa vào PFS để bỏ qua log redaction và data minimization**.

### 17.1. Vì sao không nên thu key logs để “cải thiện IDS” ở Production?

Một số TLS stacks hỗ trợ **session-key logging** phục vụ debug. Khi session traffic secrets bị ghi ra file, **người có file và packet capture tương ứng có thể giải mã traffic**, làm mất phần bảo đảm bí mật bạn kỳ vọng đối với những phiên đó.

Nếu cần debug sâu trong **lab được cấp quyền**, dùng dữ liệu tổng hợp và quản lý keylog nghiêm ngặt, không chứa PII/credential thật. Trong Production, ưu tiên **WAF/proxy/application telemetry tại điểm termination được phép**, và chỉ thu dữ liệu cần thiết theo chính sách tổ chức.

### 17.2. Giám sát an ninh kênh truyền

| Nguồn | Có thể cung cấp | Không suy diễn |
| --- | --- | --- |
| Edge TLS telemetry | Version, negotiated cipher, resumption/early-data theo hỗ trợ | Mọi phiên có FS nếu chỉ biết TLS 1.3 |
| Reverse proxy logs | TLS termination và request metadata theo cấu hình | Inner backend hop được bảo vệ nếu không xác minh |
| Packet capture trên WAN | Traffic mã hóa, metadata handshake còn hiển thị | Có thể đọc được payload vì lấy được public certificate |
| PKI/KMS audit | Ai truy cập certificate key, vòng đời certificate | Không có session secret leaked |
| SIEM/EDR | Dấu hiệu lộ file, dump, process compromise | Có thể giải mã TLS quá khứ chỉ từ alert |
| DNS/security logs | Query/hostname theo khả năng quan sát | Dữ liệu DNS đã được PFS che tự động |

## 18. PFS và “harvest now, decrypt later” trước khả năng lượng tử

Đây là một khác biệt cần hiểu rõ: **PFS cổ điển không đồng nghĩa chống được một kẻ có máy tính lượng tử đủ mạnh trong tương lai**.

Với **ECDHE/DHE truyền thống**, các **public key shares** nằm trong transcript ghi lại. Một đối thủ trong tương lai có khả năng chạy **thuật toán lượng tử phá bài toán discrete logarithm** ở mức đủ lớn có thể suy ra bí mật trao đổi từ các public values đã ghi; do đó **chỉ triển khai ECDHE cổ điển không bảo vệ chắc chắn trước kiểu “thu hoạch traffic ngày nay để giải mã khi có công nghệ lượng tử”**.

| Mô hình kẻ tấn công | PFS ECDHE cổ điển bảo vệ tới đâu? |
| --- | --- |
| Nghe lén hôm nay, **sau này trộm server certificate private key** | Chống lộ session secrets cũ chỉ do certificate key bị lấy, nếu các giả định đúng |
| Nghe lén hôm nay, **sau này trộm ephemeral/traffic secret đã được lưu** | Không bảo vệ phần secret cụ thể đã bị lộ |
| Nghe lén hôm nay, **sau này có năng lực lượng tử phá DH/ECDH cổ điển** | Không bảo đảm chống được chỉ bằng ECDHE cổ điển |
| Dùng **key establishment có tính chất hậu lượng tử** theo profile được chuẩn hóa và hỗ trợ | Có thể giảm rủi ro tương ứng, nhưng cần đánh giá cả thành phần thuật toán, authentication, downgrade, implementation |

Các hướng **post-quantum key establishment** và **hybrid key exchange** nhằm giảm rủi ro này, nhưng **không được nhầm thuật toán, nhóm và trạng thái chuẩn hóa/triển khai**. Một hybrid mechanism được đánh giá đúng có mục tiêu giữ an toàn nếu ít nhất một thành phần key establishment đáp ứng giả định của nó; kết luận thực tế phải theo **protocol specification, version, implementation và chính sách** của nền tảng.

**Điểm cần nhớ:** PFS đáp lại câu hỏi **“lộ identity private key về sau có giải mã được phiên cũ không?”**. Bảo vệ chống giải mã tương lai bằng công nghệ lượng tử còn đòi hỏi **giả định mật mã và cơ chế trao đổi khóa phù hợp**, không chỉ một checkbox “forward secrecy”.

## 19. Thực hành Python offline: phân loại bằng chứng forward secrecy

Bài lab này **không thiết lập kết nối TLS, không kết nối Internet, không sinh hay giải mã khóa**, và chỉ xử lý một số bản ghi **mô phỏng đã gắn nhãn handshake**. Mục tiêu là học cách **đặt câu hỏi có điều kiện** thay vì suy PFS từ một trường đơn giản.

### 19.1. Bài toán

Cho một inventory về các kiểu handshake, quyết định liệu kiểu đó **có forward secrecy trước tình huống lộ server authentication key sau phiên** hay không. Phải báo rõ khi không đủ bằng chứng hoặc với 0-RTT.

~~~python
from dataclasses import dataclass
from typing import Literal


Version = Literal["TLS1.2", "TLS1.3"]
Exchange = Literal[
    "rsa_key_transport", "ecdhe_full", "dhe_full",
    "tls12_resumption", "psk_dhe_ke", "psk_ke"
]


@dataclass(frozen=True)
class Handshake:
    name: str
    version: Version
    exchange: Exchange
    early_data: bool = False


def classify(handshake: Handshake) -> dict:
    """Chỉ phân loại ngữ nghĩa đã khai báo; không xác minh một kết nối thật."""
    exchange = handshake.exchange
    if handshake.version == "TLS1.2":
        if exchange == "rsa_key_transport":
            one_rtt = "NO_FS_CERT_KEY_EXPOSURE"
        elif exchange in ("ecdhe_full", "dhe_full"):
            one_rtt = "FS_IF_EPHEMERAL_SECRETS_ERASED"
        elif exchange == "tls12_resumption":
            one_rtt = "REVIEW_MASTER_SECRET_AND_TICKET_KEYS"
        else:
            one_rtt = "INVALID_COMBINATION"
    else:
        if exchange in ("ecdhe_full", "dhe_full", "psk_dhe_ke"):
            one_rtt = "FS_IF_EPHEMERAL_SECRETS_ERASED"
        elif exchange == "psk_ke":
            one_rtt = "NO_FRESH_DH_FS_IF_PSK_COMPROMISED"
        else:
            one_rtt = "INVALID_COMBINATION"

    if handshake.early_data:
        if handshake.version == "TLS1.3" and exchange in (
            "psk_dhe_ke", "psk_ke"
        ):
            early = "NO_FS_AND_REPLAY_RISK"
        else:
            early = "INVALID_OR_UNSUPPORTED_0RTT_CASE"
    else:
        early = "NOT_APPLICABLE"

    return {
        "name": handshake.name,
        "one_rtt_assessment": one_rtt,
        "early_data_assessment": early,
    }


samples = [
    Handshake("old-rsa", "TLS1.2", "rsa_key_transport"),
    Handshake("tls12-ecdhe", "TLS1.2", "ecdhe_full"),
    Handshake("tls12-resume", "TLS1.2", "tls12_resumption"),
    Handshake("tls13-full", "TLS1.3", "ecdhe_full"),
    Handshake("tls13-psk-dhe", "TLS1.3", "psk_dhe_ke", True),
    Handshake("tls13-psk-only", "TLS1.3", "psk_ke"),
]

for case in samples:
    result = classify(case)
    print(
        result["name"],
        result["one_rtt_assessment"],
        result["early_data_assessment"],
    )

assert classify(samples[0])["one_rtt_assessment"] == "NO_FS_CERT_KEY_EXPOSURE"
assert classify(samples[1])["one_rtt_assessment"] == (
    "FS_IF_EPHEMERAL_SECRETS_ERASED"
)
assert classify(samples[4])["early_data_assessment"] == (
    "NO_FS_AND_REPLAY_RISK"
)
~~~

Kết quả dự kiến, rút gọn:

~~~text
old-rsa NO_FS_CERT_KEY_EXPOSURE NOT_APPLICABLE
tls12-ecdhe FS_IF_EPHEMERAL_SECRETS_ERASED NOT_APPLICABLE
tls12-resume REVIEW_MASTER_SECRET_AND_TICKET_KEYS NOT_APPLICABLE
tls13-full FS_IF_EPHEMERAL_SECRETS_ERASED NOT_APPLICABLE
tls13-psk-dhe FS_IF_EPHEMERAL_SECRETS_ERASED NO_FS_AND_REPLAY_RISK
tls13-psk-only NO_FRESH_DH_FS_IF_PSK_COMPROMISED NOT_APPLICABLE
~~~

### 19.2. Cách giải thích các nhãn

| Nhãn | Diễn giải |
| --- | --- |
| NO_FS_CERT_KEY_EXPOSURE | Phiên TLS 1.2 RSA key transport có nguy cơ giải mã khi server RSA key về sau bị lộ và có đủ transcript |
| FS_IF_EPHEMERAL_SECRETS_ERASED | Có FS theo mô hình phù hợp khi ephemeral secret không lộ và thuật toán an toàn |
| REVIEW_MASTER_SECRET_AND_TICKET_KEYS | Không đủ dữ kiện về session resumption để kết luận FS độc lập |
| NO_FRESH_DH_FS_IF_PSK_COMPROMISED | PSK-only không có fresh DH; nếu PSK bị lộ về sau, traffic bị ảnh hưởng có thể không có FS |
| NO_FS_AND_REPLAY_RISK | 0-RTT early data không có FS và có replay considerations |
| INVALID_COMBINATION | Ví dụ dữ liệu gắn nhãn không phù hợp các trường hợp mà mô hình hỗ trợ |

**Cảnh báo quan trọng:** Hàm không làm kiểm toán TLS thật. Nó không chứng minh thư viện sinh DH keys đúng, không kiểm tra certificate validation, không đánh giá khả năng chống tấn công lượng tử, không kiểm tra ticket key lifecycle và không nhận biết endpoint bị chiếm quyền. Đặc biệt **TLS 1.3 PSK-only vẫn có thể không bị giải mã chỉ từ certificate key**, nhưng **không có fresh DH FS trước PSK compromise**: phải xác định **bí mật bị lộ là gì**.

### 19.3. Bài tập mở rộng

1. Thêm trường **secret_compromised** với các giá trị certificate/private key, resumption PSK, traffic secret, ephemeral private value.
2. Tách kết quả thành **FS against certificate-key compromise** và **FS against PSK compromise**, không dùng một boolean duy nhất.
3. Mô hình thêm từng **TLS termination hop** (CDN/ingress/service mesh) và tính một bảng coverage theo hop.
4. Thêm cờ **key_log_present** để giải thích vì sao PFS không ngăn việc giải mã khi đã có traffic secrets.
5. Tạo bản ghi TLS 1.3 resumed với **PSK-DHE và 0-RTT**; kết luận riêng **early data** và **1-RTT data**.
6. Thêm trường **quantum_adversary** và ghi kết quả “KHÔNG ĐỦ BẢO ĐẢM CHỈ VỚI ECDHE CỔ ĐIỂN”, không suy đó là tấn công đang xảy ra.

## 20. Case study 1: lộ certificate private key sau khi traffic đã bị ghi

**Tình huống giả định:** Một công ty có website HTTPS, truy cập khách hàng trong quý I bị một bên chưa rõ danh tính ghi lại trên đường WAN. Quý II, có dấu hiệu private key TLS server đã bị sao chép trái phép khỏi một máy chủ. Đội an ninh cần đánh giá **dữ liệu quá khứ có thể bị giải mã hay không**.

### 20.1. Phân tích theo từng ứng dụng

| Dịch vụ | Quan sát từ cấu hình/lưu vết hợp lệ | Đánh giá ban đầu |
| --- | --- | --- |
| **API A** | TLS 1.2, full handshake ECDHE_RSA, session resumption được kiểm soát riêng | Không thể chỉ dựa vào việc mất RSA cert key mà suy giải mã được các full ECDHE handshakes cũ |
| **API B legacy** | TLS 1.2 RSA key transport còn cho phép | Có nguy cơ bản ghi cũ bị giải mã khi private key tương ứng bị lộ |
| **Public Web C** | TLS 1.3 full (EC)DHE, có resumption; 0-RTT chưa bật | Các full handshakes có FS theo giả định; vẫn phải review PSK/ticket lifecycle |
| **Ingress nội bộ** | TLS từ edge tới origin nhưng cấu hình chưa được kiểm kê | **Chưa đủ dữ kiện** để kết luận mức độ lộ |

**Không thể kết luận từ tên chứng chỉ hoặc thuật toán AES**. Để đánh giá cần biết **vùng traffic đã ghi, private key nào lộ, TLS version/cipher/handshake modes thực tế, ticket/PSK scope, thời gian hiệu lực và các key logs/dumps**.

### 20.2. Các hành động phù hợp

1. **Khoanh incident:** Xác định private key bị ảnh hưởng, nơi lưu, thời gian truy cập trái quyền và dịch vụ sử dụng.
2. **Ngăn lạm dụng tiếp diễn:** Thu hồi/rotate chứng chỉ và khóa, điều tra identity, cấu hình TLS và quyền truy cập secrets theo quy trình.
3. **Phân loại dữ liệu quá khứ:** Tách những phiên **RSA key transport** với những phiên **ephemeral DH full handshake**, và resumption/early data thành các nhóm riêng.
4. **Xem bí mật khác có bị lộ không:** Ticket-encryption keys, resumption state, TLS key logs, core dumps, memory snapshots có thể thay đổi nghiêm trọng đánh giá.
5. **Rà soát client/proxy trust:** Sự kiện lộ key có thể gây **mạo danh server về sau** nếu attacker có thể đưa client đến điểm giả.
6. **Thông báo rủi ro có chứng cứ:** Không hứa “mọi bản ghi quá khứ vẫn bí mật” nếu chưa xác minh đầy đủ tất cả TLS hops/PSK modes.
7. **Cải tiến kiến trúc:** Thu hẹp RSA key transport, thực thi FS trên các chặng, bảo vệ key/ticket logs, áp dụng quan sát/audit phù hợp.

**Điểm quan trọng:** Việc đổi chứng chỉ là cần thiết để giảm nguy cơ **mạo danh trong tương lai**, nhưng **không đảo ngược việc ghi và giải mã đã có thể xảy ra** ở các phiên thiếu PFS.

## 21. Case study 2: TLS 1.3, resumption và 0-RTT trên API

**Tình huống giả định:** Một API thanh toán qua CDN dùng TLS 1.3 và cho phép 0-RTT trên một số endpoints để giảm độ trễ. Bộ phận vận hành ghi trong báo cáo rằng “đã có PFS vì toàn bộ edge chạy TLS 1.3”. Một tháng sau, đội phát triển phát hiện một endpoint tạo đơn hàng đã chấp nhận early data.

### 21.1. Câu hỏi đánh giá

- **Full handshake** có fresh (EC)DHE và certificate validation đúng không?
- **Resumption 1-RTT** có chọn **psk_dhe_ke** hay **psk_ke**?
- Endpoint tạo đơn hàng có xử lý **0-RTT early data** không?
- Một thao tác tạo đơn có được thiết kế idempotent/replay-safe trên tất cả các lớp CDN, API gateway, queue và database không?
- **Ticket lifetime và chống replay** hoạt động ra sao khi request đến nhiều region/edge nodes?
- Logs có phân biệt early data với requests sau full/resumed 1-RTT không?

### 21.2. Kế hoạch cải tiến

1. Không gọi “toàn bộ TLS 1.3 có PFS” mà **ghi chính xác resumption mode và early-data policy**.
2. **Không cho phép 0-RTT** ở những endpoints có side effects nếu chưa có thiết kế chống replay phù hợp; ưu tiên xác nhận server đã hoàn thành handshake trước khi xử lý giao dịch nhạy cảm.
3. Kiểm chứng **PSK-DHE cho 1-RTT** theo khả năng TLS stack.
4. Áp dụng **ticket management, authentication, rate limiting và observability** với quyền truy cập tối thiểu.
5. Kiểm thử cả **retry, replay simulation trong lab được phép, cross-region và cache behavior** mà không gửi yêu cầu gây hại tới dịch vụ công cộng.
6. Sửa tài liệu báo cáo để phân biệt **forward secrecy** với **replay safety**, vốn là hai thuộc tính khác nhau.

**Bài học:** Cải thiện latency bằng session resumption/0-RTT có giá trị, nhưng đánh giá bảo mật phải ghi rõ **loại dữ liệu, bí mật nào bảo vệ nó và những tác động nếu request bị gửi lại**.

## 22. Runbook xử lý sự cố lộ khóa và đánh giá dữ liệu quá khứ

### 22.1. Các pha incident response

~~~mermaid
flowchart TD
    A["Phát hiện lộ khóa/chứng chỉ hoặc session secret"] --> B["Xác định chính xác loại secret và phạm vi"]
    B --> C["Cô lập nguồn rò, bảo toàn bằng chứng, luân chuyển credential"]
    C --> D["Xây timeline: lúc bị lộ, phiên TLS, ticket/PSK"]
    D --> E{"Key exchange của traffic cũ?"}
    E -- "RSA key transport / PSK-only bị lộ" --> F["Đánh giá nguy cơ giải mã bản ghi cũ"]
    E -- "Fresh ephemeral (EC)DHE" --> G["Xác minh ephemeral/traffic secrets không bị lộ"]
    E -- "Thiếu telemetry" --> H["Ghi trạng thái chưa kết luận, bổ sung evidence"]
    F --> I["Ứng phó, thông báo, giảm thiểu và hậu kiểm"]
    G --> I
    H --> I
~~~

### 22.2. Thu bằng chứng mà không làm rò thêm bí mật

| Nhóm | Dữ liệu cần có | Nguyên tắc bảo vệ |
| --- | --- | --- |
| Certificate/PKI | Key ID, certificate fingerprint, serial, issuer, thời gian, hệ thống dùng | Không xuất private key để đối chiếu |
| TLS configurations | Protocol, allowed key exchange, ticket/0-RTT policies | Tránh công khai endpoint nội bộ nhạy cảm ngoài phạm vi |
| Handshake telemetry | TLS 1.2 cipher, TLS 1.3 PSK/DHE mode, early-data state | Chỉ thu trường cần thiết, giảm dữ liệu cá nhân |
| Key lifecycle | KMS/HSM access audit, backup/restore, key log/core dump traces | Hạn chế người xem, ngăn lan truyền khóa trong ticket |
| Network topology | CDN/edge/origin/mTLS termination chain | Phân quyền theo environment/zone |
| Incident timeline | Trước/sau lộ, thời điểm traffic đã ghi có thể tồn tại | Đánh dấu độ tin cậy, không khẳng định khi thiếu evidence |
| Business impact | Loại dữ liệu nhạy cảm, hành trình người dùng | Phối hợp pháp lý/bảo mật theo nghĩa vụ tổ chức |

### 22.3. Ma trận ra quyết định minh họa

| Bí mật lộ | Loại handshake | Mối quan tâm chính | Hướng xử lý |
| --- | --- | --- | --- |
| Server certificate private key | TLS 1.2 RSA key transport | Bản ghi cũ có thể giải mã; giả mạo peer | Rotate/revoke, đánh giá dữ liệu và khách hàng bị ảnh hưởng |
| Server certificate private key | Full TLS 1.2 ECDHE / TLS 1.3 (EC)DHE | Giả mạo phiên tương lai, cần xác minh không có secret khác lộ | Rotate/revoke, kiểm tra ephemeral/session logs |
| Resumption PSK/ticket state | TLS 1.3 psk_ke hoặc 0-RTT | Traffic cũ/early data và replay trong phạm vi secret | Revoke/rotate PSK, chặn 0-RTT nhạy cảm, đánh giá affected sessions |
| Session traffic secret | Một phiên đang hoặc đã chạy | Records thuộc phạm vi key bị lộ | Cô lập nguồn rò, giảm lưu key logs, rotate/reconnect theo playbook |
| Ephemeral DH private value | Phiên trao đổi DH liên quan | Mất FS của phiên bị ảnh hưởng nếu kết hợp dữ liệu cần thiết | Điều tra endpoint memory/dumps, thay secrets/cấu hình bảo vệ |
| Chỉ public certificate bị lấy | Bất kỳ | Public cert vốn công khai | Không coi đây là lộ private key; xác minh dữ kiện |

**Không tự công bố mức độ lộ dữ liệu trên cơ sở một rule tự động**. Incident commander, PKI/Platform, SOC, người sở hữu dữ liệu và bộ phận chuyên trách nghĩa vụ thông báo phải đưa ra kết luận theo bằng chứng và chính sách của tổ chức.

### 22.4. Tiêu chí hoàn tất ứng phó

- Key/credential bị lộ đã được **cô lập, thay thế hoặc thu hồi** theo hướng dẫn PKI và ảnh hưởng đã được xem xét.
- Đã xác định **những TLS endpoints/regions** dùng key đó và các nhánh còn thiếu thông tin.
- Đã phân biệt **TLS 1.2 RSA, full ECDHE, resumption/PSK/0-RTT**.
- Session key logging/core dumps/ticket keys có owner, xử lý bảo mật và retention rõ.
- Client/partner không bị gián đoạn ngoài dự kiến khi rotate certificate; xác thực peer không bị nới lỏng.
- Regression tests cho **TLS handshake, resumption, backend TLS và authorization** đạt yêu cầu.
- Có postmortem, action owners và thời hạn xử lý các biện pháp còn thiếu.

## 23. Ma trận kiểm thử TLS forward secrecy trước khi triển khai

Ma trận này dành cho **các endpoint lab, staging hoặc hệ thống được phép kiểm thử**. Những phép thử kết nối chủ động, thay đổi TLS policy, thay key hoặc giả lập sự cố phải có **approval, scope, canary và rollback**; không bật debug chứa secrets lên Production để xác minh PFS.

| Test ID | Tình huống | Kỳ vọng và bằng chứng |
| --- | --- | --- |
| FS-01 | Full TLS 1.2 với ECDHE_RSA | Negotiated key exchange ECDHE; certificate validation đúng |
| FS-02 | Full TLS 1.2 với ECDHE_ECDSA | ECDHE bảo vệ phiên; ECDSA là xác thực, không bị nhầm với key exchange |
| FS-03 | Client đề nghị TLS 1.2 RSA key transport đã bị cấm | Server không thương lượng RSA key transport trái policy |
| FS-04 | Full TLS 1.3 với key_share hợp lệ | Có fresh (EC)DHE, certificate/identity được kiểm tra |
| FS-05 | TLS 1.3 dùng AES-GCM | Không tự kết luận FS chỉ từ cipher name; đọc mode/group |
| FS-06 | TLS 1.3 resumed với psk_dhe_ke | Có fresh DH contribution cho 1-RTT traffic |
| FS-07 | TLS 1.3 resumed với psk_ke | Cảnh báo không có fresh-DH FS theo PSK-compromise model |
| FS-08 | TLS 1.3 0-RTT được bật trên lab | Early data được phân loại riêng, kiểm soát replay và route |
| FS-09 | 0-RTT đến endpoint tạo đơn/ghi dữ liệu | Không xử lý sớm ngoài chính sách replay-safe |
| FS-10 | TLS 1.2 resumed session ID/ticket | Review master secret, ticket key scope và tuổi thọ, không suy từ full ECDHE |
| FS-11 | Certificate server dùng RSA cùng ECDHE | Báo FS đúng; không coi chứng chỉ RSA là thiếu FS |
| FS-12 | Certificate server dùng ECDSA nhưng handshake không rõ | Không kết luận PFS chỉ từ thuật toán ký |
| FS-13 | Client kết nối qua IPv4 và IPv6 | Cùng policy TLS theo mục tiêu, không lệch cipher/termination |
| FS-14 | CDN edge dùng TLS 1.3, origin legacy TLS 1.2 | Báo thiếu FS ở hop origin nếu dùng RSA key transport |
| FS-15 | Backend service mesh dùng mTLS | Xác minh identity và key exchange ở chặng backend độc lập |
| FS-16 | Website cung cấp HTTPS/TCP và HTTP/3/QUIC | Kiểm tra cả hai, đặc biệt early data và resumption |
| FS-17 | Load balancer failover tới region dự phòng | Policy, certificate/key lifecycle và PSK mode không drift |
| FS-18 | Certificate private key bị rotate trong lab | Kết nối mới hợp lệ, không nới certificate validation |
| FS-19 | Ticket key rotation/expiry trong lab | Resumption hoạt động hoặc fallback theo policy, không mở lại 0-RTT ngoài chủ đích |
| FS-20 | TLS keylog vô tình bật trong cấu hình mô phỏng | Policy validation cảnh báo/prohibit với Production |
| FS-21 | Một client legacy không hỗ trợ policy mới | Có danh sách ảnh hưởng/giải pháp nâng cấp, không tự mở TLS yếu đại trà |
| FS-22 | NIDS không thấy plaintext HTTPS | Không dùng thiếu HTTP signature để kết luận mã hóa hoặc PFS lỗi |
| FS-23 | Session key material bị lộ trong kịch bản tabletop | Nhận diện PFS không bảo vệ nếu traffic secret trực tiếp lộ |
| FS-24 | Post-quantum threat model | Ghi rõ classical ECDHE không bảo đảm chống giải mã lượng tử trong tương lai |
| FS-25 | Một API không được cấp quyền sau TLS termination | **DENY** vẫn áp dụng dù handshake có FS và certificate hợp lệ |
| FS-26 | Rollback TLS policy sau regression lỗi | Chỉ hoàn nguyên theo approval, không làm lộ key/giảm trust validation |

### 23.1. Mẫu bằng chứng của từng test

~~~text
TEST ID / CHANGE ID:
Endpoint / environment / region / IP family:
Network protocol: TLS-over-TCP or QUIC
TLS version:
Full handshake or resumed:
Key exchange: RSA transport / (EC)DHE / PSK-DHE / PSK-only
Early data: enabled / rejected / not applicable
Cipher suite / group:
Certificate identity validation:
TLS termination hop:
Ticket/PSK policy reference (no secrets):
Expected FS assessment:
Observed logs / handshake evidence:
Application ALLOW/DENY result:
Owner / reviewer / timestamp:
Rollback / follow-up:
~~~

**Hai lớp kiểm chứng khác nhau:** (1) **Cơ chế TLS và key schedule có thuộc tính FS mong muốn**. (2) **Ứng dụng bảo vệ đúng dữ liệu và quyền truy cập**. Một kết nối có FS vẫn có thể tới API thiếu authorization, hoặc một origin đã giải mã TLS vẫn có thể phát plaintext vào mạng không tin cậy.

## 24. Các nhầm lẫn thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “PFS nghĩa là khóa TLS không bao giờ bị lộ.” | FS giới hạn hậu quả của việc lộ **một số khóa dài hạn về sau**; session secrets vẫn có thể bị lộ. |
| “Có AES-256 là có PFS.” | AES là thuật toán symmetric encryption, FS phụ thuộc key establishment. |
| “Server dùng certificate RSA thì không thể có PFS.” | ECDHE_RSA/TLS 1.3 dùng chứng chỉ RSA vẫn có thể có FS. |
| “Certificate ECDSA bảo đảm FS.” | Thuật toán chữ ký không tự quyết định key exchange/resumption. |
| “TLS 1.2 luôn không có FS.” | TLS 1.2 ECDHE/DHE full handshakes có FS theo giả định phù hợp. |
| “TLS 1.3 cipher name cho biết key-exchange group.” | TLS 1.3 tách AEAD/hash khỏi group và PSK mode. |
| “TLS 1.3 có FS cho mọi PSK-only/0-RTT data.” | PSK-only thiếu fresh DH; 0-RTT không có FS và có replay risk. |
| “Resumption luôn an toàn tương đương full ECDHE handshake mới.” | Cần phân biệt TLS 1.2 tickets và TLS 1.3 psk_dhe_ke/psk_ke/0-RTT. |
| “Rotate certificate xong là phiên RSA cũ không thể giải mã.” | Nếu RSA key cũ đã bị lộ và transcript đã ghi, đổi cert không đảo ngược rủi ro. |
| “KeyUpdate khôi phục bảo mật sau compromise.” | TLS 1.3 KeyUpdate không tự tạo fresh DH. |
| “HSM giúp mọi kết nối có PFS.” | HSM bảo vệ khóa, nhưng FS là thuộc tính của trao đổi khóa phiên. |
| “PFS cũng bảo vệ trước compromised endpoint.” | Endpoint có thể thấy plaintext và session secret ngay khi hoạt động. |
| “Có PFS tại CDN nghĩa là có PFS trên mọi chặng backend.” | Mỗi TLS termination hop phải được xác minh riêng. |
| “HTTPS có PFS thì NIDS sẽ nhìn thấy HTTP để quét signature.” | TLS che payload khỏi sensor không có quyền giải mã tại đúng điểm. |
| “PFS bảo vệ cả source IP, traffic timing và metadata.” | Những dữ liệu ngoài vùng TLS mã hóa có thể vẫn quan sát được. |
| “PFS cổ điển giải quyết hoàn toàn vấn đề lượng tử.” | ECDHE/DHE cổ điển không tự bảo vệ trước thuật toán lượng tử đủ mạnh về sau. |
| “Mã hóa 0-RTT bảo vệ khỏi replay.” | Early data được mã hóa nhưng có replay concern riêng. |
| “TLS/mTLS có PFS đồng nghĩa user được phép truy cập DB.” | Identity/authorization/segmentation phải được kiểm tra độc lập. |

## 25. Câu hỏi tự kiểm tra và bài tập kiến trúc

1. **PFS bảo vệ trước sự kiện lộ khóa nào?** Trong mô hình điển hình, lộ private key xác thực dài hạn của server sau khi phiên kết thúc không tự lộ các session keys cũ đã thiết lập bằng fresh ephemeral (EC)DHE.
2. **Vì sao TLS 1.2 RSA key transport thiếu tính chất đó?** Premaster secret được mã hóa bằng RSA public key của server; private key RSA bị lộ sau này có thể giải mã premaster secret trong handshake đã ghi.
3. **ECDHE_RSA có PFS không?** Có theo giả định key exchange, dù certificate dùng RSA để xác thực.
4. **AES-GCM có phải cơ chế sinh PFS không?** Không; nó là AEAD dùng các symmetric traffic keys được dẫn xuất từ key schedule.
5. **ECDHE khác ECDSA?** ECDHE trao đổi bí mật khóa tạm; ECDSA là chữ ký số dùng xác thực.
6. **TLS 1.3 có cơ chế RSA key transport không?** Không như TLS 1.2; nhưng PSK-only và 0-RTT vẫn cần đánh giá riêng về FS.
7. **PSK-DHE khác PSK-only ở đâu?** PSK-DHE có đóng góp fresh ephemeral DH cho 1-RTT, còn PSK-only không.
8. **0-RTT early data có PFS như 1-RTT sau PSK-DHE không?** Không. Early data phát trước fresh DH hoàn tất, cũng có replay concerns.
9. **TLS 1.2 resumption có luôn kế thừa FS độc lập từ full ECDHE không?** Không; phải xét master secret, session tickets và khóa bảo vệ chúng.
10. **Lộ traffic secret khác lộ certificate private key thế nào?** Có traffic secret liên quan có thể ảnh hưởng trực tiếp bản ghi của phiên; FS không che được secret đã lộ.
11. **Tại sao rotate key không sửa được bản ghi RSA cũ?** Dữ liệu đã ghi vẫn có thể giải mã với private key cũ đã bị lộ.
12. **PFS có chống được kẻ nghe lén tương lai sử dụng máy tính lượng tử đủ mạnh không?** PFS dựa trên DH/ECDH cổ điển không bảo đảm trước nguy cơ đó.
13. **Khi TLS kết thúc ở CDN, PFS bảo vệ đến đâu?** Tới CDN trên chặng tương ứng; chặng CDN → origin phải kiểm tra và bảo vệ riêng.
14. **Tại sao HTTPS/TCP tốt không đủ để kết luận HTTP/3?** QUIC có handshake và 0-RTT/resumption riêng; phải kiểm thử entrypoint QUIC.
15. **mTLS và FS có thể tồn tại độc lập không?** Có: mTLS là xác thực hai phía, FS là tính chất thiết lập session secrets.
16. **Nếu chỉ có TLS version và AES cipher name, có đủ kết luận FS không?** Không, nhất là TLS 1.3; phải biết key exchange mode và resumption.
17. **KeyUpdate trong TLS 1.3 có phải một lần (EC)DHE mới không?** Không. Nó dẫn xuất keys tiếp theo từ secrets trước.
18. **Làm sao bảo đảm lưu lượng Dev không vào Prod DB dù đã có PFS?** Bằng authentication/authorization, firewall, segmentation, identity-aware policy và kiểm thử DENY.

### Bài tập tổng hợp

Một công ty triển khai public API qua CDN, reverse proxy ở cloud, nhiều microservices mTLS, ứng dụng mobile và đối tác TLS 1.2. CDN hỗ trợ TLS 1.3, có session resumption; chặng origin đang là TLS 1.2 và một số đối tác cũ chỉ kết nối được bằng RSA key transport.

Hãy xây dựng một tài liệu thiết kế gồm:

1. **Sơ đồ các TLS termination hops** và điểm thực sự có plaintext.
2. **Ma trận TLS 1.2/TLS 1.3 key exchange** cho từng endpoint; phân biệt RSA authentication với RSA key transport.
3. **Resumption design** xác định PSK-DHE, PSK-only, ticket lifetime, ticket-key access và 0-RTT replay.
4. **Kế hoạch nâng cấp legacy clients**, canary, thông báo đối tác và chính sách ngoại lệ giới hạn.
5. **Threat model** cho người nghe lén WAN, lộ certificate key sau này, keylog leaks, compromised proxy, future quantum capability.
6. **Kế hoạch xác minh** gồm TLS-over-TCP/QUIC, IPv4/IPv6, origin/mTLS và DR region.
7. **Ít nhất tám test ALLOW/DENY và FS** có bằng chứng version, handshake mode, resumption mode, owner và rollback.
8. **Kịch bản tabletop** khi certificate key bị lộ, phân loại mức ảnh hưởng giữa full ECDHE và legacy RSA handshake.

**Tiêu chí đánh giá:** Không chỉ nói “bật TLS 1.3” mà phải chỉ ra **mỗi kết nối tạo traffic secret bằng cách nào, bí mật nào có thể bị lộ, lớp nào thực thi authorization và giới hạn của bằng chứng thu được**.

## 26. Checklist bảo đảm forward secrecy trong TLS

- [ ] Đã xác định **threat model**: khóa nào lộ, lúc nào, attacker ghi được loại traffic nào?
- [ ] Đã vẽ đủ các điểm **TLS termination** từ client/edge tới backend/service mesh?
- [ ] Đã kiểm kê **protocol version và negotiated key exchange** của kết nối thực tế?
- [ ] Những kết nối TLS 1.2 cần FS đã loại **RSA key transport** theo chính sách?
- [ ] Các kết nối TLS 1.2 còn dùng thuật toán/nhóm **ECDHE/DHE** được phê duyệt?
- [ ] TLS 1.3 handshake mới có fresh **(EC)DHE** khi mục tiêu là FS?
- [ ] TLS 1.3 resumed 1-RTT đã phân biệt **psk_dhe_ke** và **psk_ke**?
- [ ] Chính sách **0-RTT** được định nghĩa, các thao tác có side effects không được chấp nhận tùy tiện?
- [ ] Đã kiểm tra **certificate validation**, peer identity và trust chain?
- [ ] Certificate private keys, resumption state, ticket keys và traffic secrets có owner/retention rõ?
- [ ] Không ghi **TLS keylog/secret values** trong Production logs, core dumps hoặc ticket trái chính sách?
- [ ] Có xem xét độ mạnh nhóm DH/curve, TLS library, random number generation và bảo trì phần mềm?
- [ ] Có bảo vệ hoặc mTLS phù hợp cho các chặng **CDN → origin → backend**, không chỉ browser → CDN?
- [ ] Chính sách TLS đồng bộ trên **IPv4, IPv6, QUIC/HTTP/3, DR region và load balancer**?
- [ ] IDS/IPS/SIEM có nguồn telemetry hợp pháp ở đúng điểm nhìn thấy dữ liệu cần phân tích?
- [ ] Đã phân biệt **PFS**, **key rotation**, **post-compromise security** và **post-quantum confidentiality**?
- [ ] Các kết nối remote-access/VPN và HTTPS nội bộ được đánh giá **tách biệt từng key exchange**?
- [ ] Đã chạy ma trận kiểm thử **full handshake, resumption, early data và certificate rotation** trong môi trường được phép?
- [ ] Đã đánh giá tác động với client legacy, có migration plan và ngoại lệ có ngày kết thúc?
- [ ] Có quy trình điều tra khi **certificate private key, ticket key hoặc traffic secret** bị lộ?
- [ ] Authorization, firewall và segmentation vẫn được xác minh **sau TLS termination**?
- [ ] Có change record, approval, canary/rollback và người phụ trách cập nhật chính sách?

**Kết luận:** **Perfect forward secrecy** giúp bảo vệ **bí mật của những phiên đã kết thúc** trước trường hợp **khóa xác thực dài hạn bị lộ về sau**, nhờ sử dụng **bí mật trao đổi khóa tạm thời** và cách quản lý chúng đúng. Trong TLS 1.2 cần phân biệt **RSA key transport** với **ECDHE/DHE**; trong TLS 1.3 phải xét **full handshake, PSK-DHE, PSK-only và 0-RTT**, không đánh đồng tất cả với một mức FS. PFS không thay thế **bảo mật endpoint, xác thực, phân quyền, bảo vệ ticket/session secrets, kiểm soát TLS termination hoặc kế hoạch hậu lượng tử**. Một kiến trúc mạng an toàn cần chứng minh **từng chặng kết nối được bảo vệ đúng cơ chế, dữ liệu cần giữ bí mật không bị lộ và những truy cập trái quyền vẫn bị chặn**.
