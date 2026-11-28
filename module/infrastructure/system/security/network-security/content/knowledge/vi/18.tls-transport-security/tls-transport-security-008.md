# Cipher suite và tiêu chí lựa chọn trong TLS: bảo mật kênh truyền theo đúng ngữ cảnh

**Cipher suite** là tập lựa chọn thuật toán mật mã được hai đầu kết nối TLS thương lượng để bảo vệ dữ liệu trong một phiên. Nhưng ý nghĩa của tên cipher suite **khác nhau rõ rệt giữa TLS 1.2 và TLS 1.3**: với TLS 1.2, tên suite thường biểu thị cả cơ chế trao đổi khóa, xác thực và bảo vệ bản ghi; với TLS 1.3, cipher suite chủ yếu xác định **thuật toán AEAD cho dữ liệu và hàm băm dùng trong HKDF**, còn trao đổi khóa và chữ ký được thương lượng bằng các phần mở rộng riêng.

Trong chương **TLS và bảo mật kênh truyền** của học phần **SECURITY_NETWORK_SECURITY**, chọn cipher suite là một phần của thiết kế phòng vệ nhiều lớp. Kênh mã hóa phục vụ HTTPS, API, VPN kiểu TLS, DNS over TLS/HTTPS, kết nối dịch vụ nội bộ và một số luồng quản trị. Nó phải phối hợp với **định danh endpoint, quản lý chứng chỉ, firewall, phân đoạn, IDS/IPS, chính sách truy cập, cloud load balancer và vận hành khóa**.

Bài này không xếp hạng một tên thuật toán như câu trả lời tuyệt đối. Thay vào đó, người học sẽ xây dựng **hồ sơ TLS (TLS policy/profile)** từ mô hình đe dọa, tính tương thích client, khả năng tăng tốc phần cứng, yêu cầu chuẩn hóa/tuân thủ, độ sẵn sàng và cách kiểm chứng thực tế. Các cấu hình và lệnh minh họa chỉ dùng cho môi trường được quản lý hoặc lab được cấp phép.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Đọc tên cipher suite TLS 1.2 và TLS 1.3 mà không đánh đồng cấu trúc.
2. Phân biệt **key exchange, server/client authentication, record encryption, integrity và key derivation**.
3. Giải thích AEAD, AES-GCM, ChaCha20-Poly1305, HKDF, nonce và authentication tag ở mức kiến trúc.
4. Hiểu vì sao **(EC)DHE** quan trọng đối với forward secrecy và tại sao cơ chế PSK/resumption cần xét riêng.
5. Phân tích vai trò RSA, ECDSA và những thuật toán chữ ký hỗ trợ trong xác thực TLS.
6. Lựa chọn profile hiện đại cho TLS 1.3 và cấu hình tương thích TLS 1.2 khi thực sự cần.
7. Đánh giá cipher suite theo client/OS, server library, CPU, hardware acceleration và quy định tổ chức.
8. Kiểm chứng negotiated protocol, cipher suite, certificate, supported groups, ALPN và hành vi từ chối cấu hình không được phép.
9. Nhận diện tình huống cấu hình sai tại reverse proxy, load balancer, VPN/TLS gateway hoặc đường service-to-service.
10. Viết ma trận thử nghiệm, tiêu chí triển khai, giám sát và rollback có bằng chứng.

## 2. TLS bảo vệ điều gì?

**Transport Layer Security (TLS)** thiết lập một kênh truyền có bảo vệ mật mã giữa các endpoint đã được xác thực theo profile và chính sách. TLS thường chạy trên transport đáng tin cậy như TCP; với QUIC, TLS 1.3 cung cấp cơ chế handshake và bí mật mật mã nhưng **QUIC có cơ chế bảo vệ packet riêng**, không đơn giản là các bản ghi TLS/TCP được chuyển qua UDP.

Trong một phiên HTTPS điển hình:

~~~mermaid
sequenceDiagram
    participant C as TLS client
    participant S as TLS server
    C->>S: ClientHello: versions, suites, key_share, groups
    S-->>C: ServerHello: version, suite, key_share
    Note over C,S: Tính toán khóa handshake
    S-->>C: EncryptedExtensions, Certificate, CertificateVerify, Finished
    C->>S: Finished sau khi xác minh theo chính sách
    Note over C,S: Hai đầu có traffic secrets
    C->>S: Application Data được bảo vệ
    S-->>C: Application Data được bảo vệ
~~~

Đây là trình tự **TLS 1.3 full handshake giản lược**, không mô tả mọi trường hợp PSK, HelloRetryRequest, mutual TLS hoặc 0-RTT. Với TLS 1.2, thứ tự và cách thương lượng khác.

### 2.1. Bốn câu hỏi bảo mật tách biệt

| Câu hỏi | Thành phần chính | Ví dụ |
|---|---|---|
| Đang nói chuyện với **đúng endpoint**? | Certificate/identity và signature verification | Browser kiểm tra tên và chuỗi tin cậy chứng chỉ máy chủ |
| Hai bên tạo **khóa phiên** như thế nào? | Key exchange, PSK và key schedule | ECDHE với X25519 hoặc P-256 khi được hỗ trợ |
| Nội dung record được **mã hóa và xác thực** thế nào? | AEAD cipher | AES-GCM, ChaCha20-Poly1305 |
| Khóa được **dẫn xuất và ràng buộc với handshake** ra sao? | KDF/hash, transcript, Finished | HKDF-SHA256 trong TLS 1.3 suite tương ứng |

**Cipher suite không trả lời mọi câu hỏi trên trong TLS 1.3.** Ngay cả khi tên suite nhìn “mạnh”, client có thể gặp sự cố do xác thực chứng chỉ không đúng, cấu hình key exchange yếu ở phiên bản cũ hoặc có đường HTTP không mã hóa ngoài TLS.

### 2.2. TLS không bảo đảm toàn bộ hệ thống an toàn

Một kết nối TLS có thể đúng về mật mã nhưng vẫn có rủi ro nếu:

- Máy chủ hoặc client bị chiếm quyền, nên nội dung sau giải mã bị đọc.
- Ứng dụng có lỗi authorization hoặc bị tấn công qua request hợp lệ về cú pháp.
- DNS/route trỏ tới endpoint không mong muốn và client bỏ qua kiểm tra identity.
- Traffic bị chặn, làm quá tải hoặc mất kết nối: **TLS không chống DoS hoàn toàn**.
- Reverse proxy giải mã rồi gửi plaintext qua một đoạn nội bộ ngoài thiết kế.
- Private key/certificate, session ticket key hoặc log chứa secret bị lộ.

Vì vậy, việc chọn cipher suite phải nằm trong **TLS security profile** gồm version, groups, signature, certificate, verify policy, session behavior, observability và access control.

## 3. Cipher suite là gì?

Một **cipher suite** là định danh chuẩn cho một tổ hợp thuật toán nhất định. Khi TLS handshake, client quảng bá các suite hỗ trợ và server chọn một suite phù hợp với protocol version, chính sách và năng lực của hai phía.

### 3.1. Ví dụ tên TLS 1.2

**TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256**

Có thể đọc thành:

| Thành phần | Ý nghĩa trong ví dụ TLS 1.2 |
|---|---|
| TLS_ | Tiền tố định danh suite |
| ECDHE | Trao đổi khóa Diffie–Hellman dạng elliptic curve tạm thời |
| RSA | Cơ chế xác thực trao đổi bằng chứng chỉ/chữ ký RSA trong loại suite này |
| WITH | Ngăn cách phần key exchange/authentication với record protection |
| AES_128_GCM | AES với khóa 128-bit ở chế độ GCM, AEAD |
| SHA256 | Hàm băm liên quan tới PRF/handshake theo định nghĩa TLS 1.2 suite |

Không nên suy ra “AES-128” là thuật toán trao đổi khóa, hoặc “RSA” nghĩa RSA mã hóa dữ liệu ứng dụng. Trong ví dụ này **ECDHE tạo bí mật khóa**, RSA phục vụ xác thực máy chủ, AES-GCM bảo vệ bản ghi.

### 3.2. Ví dụ tên TLS 1.3

**TLS_AES_128_GCM_SHA256**

Tên ngắn hơn, **không có ECDHE hoặc RSA**:

| Thành phần | Ý nghĩa trong TLS 1.3 |
|---|---|
| TLS_AES_128_GCM | AEAD bảo vệ record dùng AES-128-GCM |
| SHA256 | Hash dùng trong HKDF/key schedule của suite |
| ECDHE/X25519/P-256 | Được thương lượng ngoài tên cipher suite nếu sử dụng (EC)DHE |
| RSA-PSS/ECDSA/EdDSA | Thuật toán ký xác thực được thương lượng theo hỗ trợ và policy, không cố định bởi suite |

**Cùng một cipher suite TLS 1.3 có thể đi với những nhóm trao đổi khóa và loại chứng chỉ khác nhau**, khi những lựa chọn đó hợp lệ và hai phía đều hỗ trợ.

### 3.3. Tên suite không phải tiêu chuẩn đánh giá đơn độc

Để đánh giá đầy đủ một kết nối cần biết ít nhất:

- Phiên bản TLS được thương lượng.
- Cipher suite được chọn.
- Supported/key-exchange group, ví dụ X25519 hay P-256.
- Certificate chain, loại public key và signature algorithm.
- Client có thật sự xác minh tên máy chủ/trust chain không.
- Session dùng full handshake, resumption hoặc PSK profile nào.
- Các lựa chọn ALPN (HTTP/2, HTTP/1.1...) khi có.
- Có client authentication/mTLS khi chính sách yêu cầu không.
- Record được bảo vệ đến endpoint nào và đoạn phía sau còn TLS không.

## 4. Sự khác nhau giữa TLS 1.2 và TLS 1.3

TLS 1.3 không chỉ đổi số phiên bản. Nó tái cấu trúc việc thương lượng mật mã và loại bỏ nhiều lựa chọn cũ từng làm TLS khó cấu hình đúng.

| Nội dung | TLS 1.2 | TLS 1.3 |
|---|---|---|
| Cấu trúc cipher suite | Gồm các thành phần key exchange/authentication/record/KDF theo suite | Chủ yếu chọn AEAD + HKDF hash |
| Key exchange | Có nhiều kiểu, gồm cả RSA key transport trong các suite cũ | (EC)DHE hoặc PSK modes theo profile; key exchange tách khỏi suite |
| Record cipher | Có AEAD, CBC và các lựa chọn lịch sử | Chỉ các AEAD cipher được định nghĩa/hỗ trợ |
| Signature | Gắn phần nào với loại suite, song có extension hỗ trợ | Thương lượng độc lập qua signature_algorithms và profile |
| Forward secrecy | Chỉ có khi cơ chế exchange phù hợp, ví dụ ECDHE | Full (EC)DHE handshake hỗ trợ; **PSK-only không có tính chất tương đương** |
| Renegotiation kiểu TLS 1.2 | Có cơ chế renegotiation | Không sử dụng renegotiation kiểu TLS 1.2 |
| 0-RTT | Không theo cơ chế 0-RTT của TLS 1.3 | Có thể có trong PSK/resumption và phải quản lý replay |
| Độ phức tạp cấu hình suite | Nhiều tổ hợp cipher/auth/kex | Danh sách suite ngắn hơn; policy vẫn cần groups/signatures/PSK |

**Lưu ý quan trọng:** TLS 1.3 thường được ưu tiên cho triển khai hiện đại; **TLS 1.2 có thể vẫn cần** khi có client được quản trị chưa nâng cấp và được cấu hình với profile mạnh. TLS 1.0/1.1 và SSL phiên bản cũ không phải lựa chọn phù hợp cho endpoint bảo mật hiện đại.

### 4.1. Khi client và server không có suite chung

Ví dụ server chỉ cho TLS 1.3 + AEAD hiện đại, nhưng client quá cũ chỉ biết TLS 1.0/1.1 hoặc suite CBC/RC4. Handshake có thể bị từ chối; đây không phải lúc nào cũng là “lỗi mạng”.

**Không giải quyết bằng cách bật mọi cipher yếu để tương thích.** Nên nâng cấp client, tạo endpoint riêng được phân vùng chặt cho trường hợp ngoại lệ và có thời hạn loại bỏ, hoặc thay ứng dụng nếu không bảo đảm được mức bảo mật yêu cầu.

## 5. AEAD: mã hóa và xác thực dữ liệu trong một cơ chế

**AEAD (Authenticated Encryption with Associated Data)** bảo vệ cả **tính bí mật và tính toàn vẹn/xác thực** của bản ghi trong phạm vi khóa và cấu trúc giao thức. Những thuật toán AEAD quan trọng trong TLS hiện đại gồm **AES-GCM** và **ChaCha20-Poly1305**.

Ở mức khái niệm:

~~~text
Input:
  key
  nonce (duy nhất theo yêu cầu của cơ chế)
  plaintext
  associated_data (header/context được xác thực)

AEAD Encrypt -> ciphertext + authentication tag

AEAD Decrypt:
  kiểm tra authentication tag
  nếu không hợp lệ -> từ chối record
  nếu hợp lệ -> cung cấp plaintext
~~~

**Associated data (AAD)** là thông tin không nhất thiết được mã hóa nhưng được ràng buộc toàn vẹn. Trong TLS, cách record header, sequence number và nonce kết hợp phụ thuộc phiên bản và thuật toán.

### 5.1. Nonce và nguy cơ dùng lại

Nhiều AEAD mode có yêu cầu nghiêm ngặt về **không tái sử dụng nonce cùng một key**, đặc biệt với AES-GCM. Reuse có thể phá vỡ giả định bảo mật nghiêm trọng.

Trong TLS, **record protection tự quản lý nonce/sequence theo giao thức**. Người cấu hình server thường không tự viết nonce cho từng packet, nhưng phải đảm bảo implementation được cập nhật và không tự tạo một giao thức tùy ý bằng cách sao chép AES-GCM mà thiếu quản lý nonce.

### 5.2. Authentication tag không phải chữ ký của máy chủ

Tag AEAD chứng minh record không bị thay đổi theo khóa phiên trong mô hình mật mã tương ứng; nó **không thay thế xác thực danh tính endpoint ban đầu**. Chứng chỉ và handshake verification vẫn cần để client biết khóa phiên được thiết lập với đúng server.

### 5.3. Không đánh đồng AEAD với mọi dạng “AES”

AES là **block cipher**, có nhiều mode sử dụng. **AES-GCM** là AEAD; **AES-CBC** trong các TLS 1.2 cipher suite cũ có cách kết hợp mã hóa và MAC khác, cần xử lý padding và lỗi giải mã cẩn thận. Không thể đánh giá an toàn của một suite chỉ bằng việc thấy chữ “AES”.

## 6. Các cipher suite thường gặp trong TLS 1.3

| Suite | Record cipher | HKDF hash | Gợi ý sử dụng |
|---|---|---|---|
| **TLS_AES_128_GCM_SHA256** | AES-128-GCM | SHA-256 | Lựa chọn hiện đại phổ biến, thường hiệu quả với AES acceleration |
| **TLS_AES_256_GCM_SHA384** | AES-256-GCM | SHA-384 | Có thể phù hợp chính sách yêu cầu AES-256 và nền tảng hỗ trợ |
| **TLS_CHACHA20_POLY1305_SHA256** | ChaCha20-Poly1305 | SHA-256 | Lựa chọn hiện đại hữu ích khi AES hardware acceleration không có hoặc không tối ưu |
| **TLS_AES_128_CCM_SHA256** | AES-128-CCM | SHA-256 | Lựa chọn tiêu chuẩn ở những triển khai/profile có yêu cầu cụ thể |
| **TLS_AES_128_CCM_8_SHA256** | AES-128-CCM với tag rút ngắn | SHA-256 | Chỉ cân nhắc trong bối cảnh chuyên biệt; không là mặc định chung cho dịch vụ Internet |

Không phải mọi thư viện TLS hoặc client hỗ trợ toàn bộ năm suite. Hỗ trợ **CCM/CCM_8** thường không phổ biến như GCM và ChaCha20-Poly1305 trong nhiều stack web thông dụng.

### 6.1. AES-128-GCM có “yếu” vì chỉ 128-bit?

Không thể kết luận như vậy. **AES-128** là một độ dài khóa được sử dụng rộng rãi cho bảo mật hiện đại. Sự an toàn của kênh không chỉ do số bit khóa đối xứng: key exchange, private key protection, certificate verification, downgrade resistance và endpoint security cũng có vai trò lớn.

**AES-256-GCM** có khóa dài hơn và một số profile/đánh giá tuân thủ có thể ưu tiên. Tuy nhiên lựa chọn nó không tự làm mọi phần của TLS tương đương “256-bit security”; các thuật toán trao đổi khóa, chữ ký và hash có **mức bảo mật khác nhau**.

### 6.2. Vì sao ChaCha20-Poly1305 đáng cân nhắc?

ChaCha20-Poly1305 thường hiệu quả trên những nền tảng thiếu phần cứng tăng tốc AES hoặc có yêu cầu phần mềm nhất định. Nhưng ở server có AES-NI hoặc acceleration phù hợp, **AES-GCM có thể nhanh hơn**. Không áp đặt thứ tự tối ưu cho mọi CPU, điện thoại hay thiết bị IoT mà không đo workload thực tế.

### 6.3. CCM và tag ngắn

Một số suite AES-CCM được tiêu chuẩn hóa cho các trường hợp cụ thể. Với **CCM_8**, tag xác thực ngắn hơn, ảnh hưởng đến biên an toàn giả mạo theo mô hình sử dụng. **Không bật mặc định chỉ để có nhiều suite hơn**; hãy dùng profile/nền tảng có cơ sở và đánh giá riêng về giới hạn bảo mật, khả năng tương thích.

## 7. Các cipher suite TLS 1.2 nên hiểu và chọn thế nào?

Khi một endpoint buộc phải hỗ trợ TLS 1.2, ưu tiên thường là suite dùng **ECDHE + AEAD** cùng phương thức xác thực phù hợp với chứng chỉ và client.

| Cipher suite TLS 1.2 | Ý nghĩa chính | Đánh giá khái niệm |
|---|---|---|
| **TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256** | ECDHE, RSA auth, AES-128-GCM | Ứng viên mạnh khi cần TLS 1.2 và chứng chỉ RSA |
| **TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384** | ECDHE, RSA auth, AES-256-GCM | Ứng viên nếu profile và thiết bị hỗ trợ |
| **TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256** | ECDHE, ECDSA auth, AES-128-GCM | Ứng viên phù hợp chứng chỉ ECDSA và client tương thích |
| **TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384** | ECDHE, ECDSA auth, AES-256-GCM | Ứng viên TLS 1.2 với ECDSA và AES-256 |
| **TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256** | ECDHE, RSA auth, ChaCha20-Poly1305 | Khi thư viện/client hỗ trợ profile tương ứng |
| **TLS_RSA_WITH_AES_128_GCM_SHA256** | RSA key transport, AES-GCM | Có AEAD nhưng **không có forward secrecy kiểu ECDHE**; không là lựa chọn ưu tiên |

Đây là **tên định danh IANA** minh họa; OpenSSL/Nginx hoặc một sản phẩm khác có thể dùng **tên cấu hình alias** khác. Chẳng hạn một số triển khai OpenSSL dùng dạng **ECDHE-RSA-AES128-GCM-SHA256** thay cho tên TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256.

### 7.1. Vì sao tránh static RSA key transport?

Các suite TLS 1.2 bắt đầu bằng **TLS_RSA_WITH_...** dùng RSA key transport, khác với **TLS_ECDHE_RSA_WITH_...**. Với static RSA key transport, nếu một private key dài hạn bị lộ, điều đó có thể tạo nguy cơ cho những phiên đã được ghi lại theo mô hình trao đổi khóa và điều kiện tấn công tương ứng.

ECDHE sử dụng ephemeral key exchange để cung cấp **forward secrecy** cho những phiên được tạo đúng; việc lộ private key xác thực về sau không tự giải mã các session cũ đã được ghi lại. Dù vậy, nếu endpoint bị chiếm lúc phiên đang hoạt động hoặc traffic secrets bị đánh cắp, forward secrecy **không bảo vệ được những bí mật đó**.

### 7.2. Vì sao không ưu tiên CBC trong TLS 1.2?

TLS 1.2 CBC suites có cơ chế MAC/padding và phụ thuộc implementation xử lý lỗi theo cách an toàn. Lịch sử TLS có nhiều vấn đề liên quan CBC và cách xử lý timing/padding; AEAD giảm một số lớp rủi ro này và có profile rõ hơn cho cấu hình hiện đại.

Không tuyên bố **mọi triển khai CBC đều đang bị khai thác thành công**, nhưng đối với hệ thống mới, nên ưu tiên TLS 1.3 và TLS 1.2 ECDHE+AEAD thay vì mở rộng CBC vì mục tiêu tương thích không được xác minh.

## 8. Những thuật toán/cơ chế cũ cần tránh

| Nhóm | Vấn đề | Chính sách phòng thủ |
|---|---|---|
| SSL 2.0/3.0, TLS 1.0/1.1 | Phiên bản cũ với hạn chế bảo mật lịch sử | Không bật trên endpoint hiện đại |
| RC4 | Thiên lệch và điểm yếu mật mã đã được công bố | Không cho phép RC4 suites |
| 3DES / DES | Độ an toàn và kích thước block/tính năng không phù hợp nhu cầu hiện đại | Không dùng trong TLS profile mới |
| NULL / aNULL / EXPORT | Không mã hóa, thiếu xác thực hoặc độ an toàn cực thấp | Loại bỏ hoàn toàn |
| Static RSA key transport | Thiếu forward secrecy như ECDHE | Không ưu tiên; loại khỏi profile hiện đại |
| CBC suites lịch sử | Phức tạp về padding/MAC và có rủi ro thực thi | Tránh khi có TLS 1.2 AEAD hoặc TLS 1.3 |
| Anonymous key exchange | Không xác thực peer, nguy cơ man-in-the-middle | Không cho phép |
| Weak groups/short keys | Giảm mức an toàn trao đổi khóa hoặc chữ ký | Dùng nhóm/độ dài được policy chấp nhận |

Một số hệ thống cũ có thể chỉ hỗ trợ profile không đạt yêu cầu. Khi đó lựa chọn an toàn hơn thường là **nâng cấp/loại bỏ client**, hoặc cô lập bằng một gateway chuyển tiếp có kiểm soát và thời hạn chấm dứt, thay vì làm suy giảm TLS của mọi người dùng trên endpoint public.

### 8.1. Không chỉ là danh sách cipher

Ngay cả khi đã tắt suite yếu, nếu client bỏ xác minh chứng chỉ, server cho HTTP plaintext hoặc có thể bị downgrade vì cấu hình version sai, kênh vẫn thiếu bảo vệ. **Hardening là tập kiểm soát**, không phải một dòng danh sách cipher.

## 9. Key exchange, forward secrecy và supported groups

Các nhóm trao đổi khóa xác định cách hai bên tạo **shared secret** cho key schedule. Với TLS 1.3 dùng (EC)DHE, sự lựa chọn group được thương lượng **riêng** khỏi cipher suite.

### 9.1. ECDHE và các nhóm thường gặp

| Nhóm | Họ thuật toán | Ý nghĩa |
|---|---|---|
| **X25519** | Elliptic-curve Diffie–Hellman | Được hỗ trợ rộng rãi trong nhiều TLS stack hiện đại |
| **secp256r1 (P-256)** | ECDHE theo đường cong NIST | Có thể phù hợp nhiều profile, thư viện và yêu cầu tuân thủ |
| **secp384r1 (P-384)** | ECDHE theo đường cong NIST | Có thể cần trong một số profile hoặc chính sách cụ thể |
| **Finite-field DHE** | Diffie–Hellman trên nhóm hữu hạn | Có thể được hỗ trợ, nhưng cần nhóm an toàn phù hợp và cấu hình chuẩn |
| **Hybrid/post-quantum groups** | Kết hợp cơ chế trao đổi khóa theo chuẩn/hỗ trợ mới | Cần kiểm tra phiên bản, interoperability và policy, **không phải một cipher suite AEAD mới** |

Lựa chọn nhóm phụ thuộc **stack, chính sách, khả năng kết nối và mức bảo mật**. Không mặc định tất cả client đều biết X25519; cũng không mặc định một tổ chức bắt buộc dùng P-384 cho mọi ứng dụng.

### 9.2. Forward secrecy là gì?

**Forward secrecy** có nghĩa ở phạm vi thỏa thuận khóa phù hợp: việc lộ **khóa xác thực dài hạn về sau** không tự cho phép giải mã những session đã được ghi lại, vì session dùng bí mật tạm thời đã được xử lý/loại bỏ đúng.

~~~text
Chứng chỉ/khóa dài hạn của server
      |
      +--> xác thực handshake
              
Ephemeral secret C + Ephemeral secret S
      |
      +--> shared secret --> key schedule --> traffic secrets
                                         |
                                         +--> AEAD bảo vệ record
~~~

Trong thực tế, endpoint phải dùng PRNG phù hợp, xử lý khóa an toàn và không lưu traffic secrets dài hạn ngoài ý muốn. Nếu một attacker có quyền đọc bộ nhớ ở thời điểm phiên đang hoạt động, forward secrecy không tự ngăn họ lấy session keys.

### 9.3. TLS 1.3 và PSK resumption

TLS 1.3 hỗ trợ **PSK (pre-shared key)**, ví dụ trong session resumption. Có thể sử dụng **PSK kết hợp (EC)DHE** hoặc những mode theo tiêu chuẩn không bổ sung DHE. Vì vậy câu “mọi phiên TLS 1.3 đều forward-secret giống nhau” **không chính xác**.

Khi cần mức đảm bảo chặt, hãy xác định **PSK key-exchange mode, session ticket lifecycle, key rotation, resumption scope và cấu hình forward secrecy** của triển khai. Cipher suite TLS_AES_128_GCM_SHA256 một mình không nói mode nào đã được dùng.

## 10. Chứng chỉ TLS và signature algorithms

Trong HTTPS server authentication, client thường kiểm tra chứng chỉ máy chủ và xác minh handshake signature bằng những thuật toán được phép. Có thể dùng:

- **RSA signatures**, ví dụ những profile RSA-PSS phù hợp với TLS version.
- **ECDSA signatures** với đường cong và hash tương ứng.
- **EdDSA signatures** như Ed25519 trong những triển khai và policy hỗ trợ.
- Những profile mới khác nếu tiêu chuẩn, sản phẩm và tổ chức cho phép.

### 10.1. Public-key algorithm khác cipher suite AEAD

Trong TLS 1.3, một server có certificate ECDSA có thể thương lượng **TLS_AES_128_GCM_SHA256**; server dùng RSA certificate phù hợp cũng có thể thương lượng cùng suite nếu các signature algorithms được hỗ trợ.

Trong TLS 1.2, tên **TLS_ECDHE_RSA_...** hoặc **TLS_ECDHE_ECDSA_...** liên quan trực tiếp đến kiểu xác thực của suite, nên cert/key capabilities ảnh hưởng danh sách suite có thể chọn.

### 10.2. Kiểm tra certificate chain

Một client an toàn cần thực hiện những bước phù hợp với ứng dụng:

1. Kiểm tra chuỗi chứng chỉ tới trust anchor được chấp nhận.
2. Kiểm tra **tên máy chủ** theo SAN và quy tắc xác thực tương ứng.
3. Kiểm tra thời hạn, key usage và extended key usage khi áp dụng.
4. Kiểm tra thuật toán chữ ký, độ dài khóa và các ràng buộc certificate policy.
5. Xử lý trạng thái thu hồi theo cơ chế/sản phẩm/chính sách phù hợp.
6. Không tự động bỏ xác minh vì gặp lỗi chứng chỉ của lab/production.

**Có TLS handshake thành công không đủ chứng minh endpoint identity đã được kiểm tra đúng.** Công cụ kiểm thử như OpenSSL cần dùng các tùy chọn verify phù hợp hoặc kiểm tra riêng kết quả.

### 10.3. Mutual TLS (mTLS)

Với **mTLS**, server yêu cầu client chứng minh danh tính bằng chứng chỉ hoặc cơ chế xác thực tương ứng. Cipher suite vẫn bảo vệ record; **mTLS thêm kiểm tra client identity** chứ không tạo một lớp mã hóa AEAD khác.

Trong service mesh, VPN hoặc API B2B, mTLS giúp xác thực workload/device, nhưng **authorization** vẫn cần quy định danh tính đó được gọi endpoint nào. Một certificate hợp lệ không tự cấp quyền tới mọi dịch vụ.

## 11. SHA-256, SHA-384, HKDF và transcript hash

Tên TLS 1.3 như **TLS_AES_256_GCM_SHA384** có hậu tố SHA384, nhưng điều này **không có nghĩa SHA-384 được dùng để “mã hóa dữ liệu”**, cũng không đơn giản là một MAC rời cho payload.

Trong TLS 1.3:

- **HKDF** dẫn xuất secret/khóa từ shared secret/PSK và transcript theo key schedule.
- **Hash** phù hợp được suite lựa chọn, ví dụ SHA-256 hoặc SHA-384.
- **AEAD** thực hiện mã hóa và xác thực record, ví dụ AES-GCM.
- **Transcript hash** giúp ràng buộc handshake messages với các bước xác thực/Finished theo giao thức.

### 11.1. Tại sao cần transcript integrity?

Nếu attacker sửa một thông số handshake đang được bảo vệ/kiểm chứng, hai bên phải có cơ chế phát hiện bất nhất. Các bước Finished và certificate verification gắn với transcript giúp ngăn nhiều kiểu giả mạo/can thiệp trong phạm vi giả định của TLS.

**Không tự thiết kế lại tổ hợp hash/KDF/cipher** vì tên gọi nghe “mạnh”. Hãy dùng thư viện TLS chuẩn và profile được bảo trì.

### 11.2. Hash length không bằng security của toàn hệ thống

SHA-384 không biến chứng chỉ RSA yếu hay endpoint bị chiếm thành an toàn. Mức bảo mật hiệu dụng còn phụ thuộc độ dài khóa, elliptic curve, chế độ exchange, xác thực và khả năng giữ secret.

Một hồ sơ chọn AES-256-GCM/SHA-384 nhưng lại dùng client không kiểm tra chứng chỉ có thể **kém an toàn hơn nhiều** so với AES-128-GCM/SHA-256 với verification đúng.

## 12. Tiêu chí lựa chọn cipher suite theo threat model

Lựa chọn phải bắt đầu từ yêu cầu và bề mặt tấn công.

| Câu hỏi | Ý nghĩa với lựa chọn |
|---|---|
| Endpoint phục vụ Internet public hay private service? | Phạm vi client và khả năng bị downgrade/scan/DoS khác nhau |
| Có client quá cũ không? | Cần xác minh TLS 1.2 compatibility, không bật suite yếu mặc định |
| Dữ liệu cần bảo vệ lâu dài không? | Ưu tiên profile có forward secrecy và quản lý khóa tốt; đánh giá cập nhật chống rủi ro dài hạn |
| Có yêu cầu compliance/FIPS cụ thể không? | Chọn thuật toán và **implementation được phép**, không chỉ tên |
| Server có tăng tốc AES không? | Ảnh hưởng hiệu năng AES-GCM so với ChaCha20-Poly1305 |
| Client là mobile/IoT/embedded hay desktop? | Năng lực CPU, thư viện, battery và supported groups khác nhau |
| Có TLS termination tại CDN/WAF/LB không? | Phải đánh giá mỗi chặng TLS riêng, gồm re-encryption tới origin |
| Có mTLS hoặc private PKI không? | Certificate/signature và client auth có thể loại một số profile |
| Có nhiều vùng cloud/OS/library khác nhau không? | Cần policy nhất quán nhưng compatible với từng stack |
| Có QUIC/HTTP/3 không? | Phải đánh giá TLS 1.3 + QUIC transport và telemetry tương ứng |
| 0-RTT/resumption có được bật không? | Cần xử lý replay risk và session ticket governance |
| Có thiết bị IDS/IPS cần metadata không? | TLS giảm khả năng đọc payload ở điểm không giải mã |

### 12.1. Phân loại yêu cầu bắt buộc và tối ưu

**Yêu cầu bắt buộc** có thể gồm: TLS 1.2 trở lên theo profile được phê duyệt, certificate verification, AEAD, forward secrecy theo policy, chứng chỉ còn hạn, không dùng cipher yếu, log bảo mật và cập nhật thư viện.

**Yêu cầu tối ưu** có thể gồm: throughput, CPU, năng lượng, handshakes/second, lựa chọn AES-256 hay ChaCha20 và ưu tiên suite của server.

Không được dùng điểm hiệu năng cao để bù cho việc **không xác minh certificate** hoặc chấp nhận suite bị cấm bởi chính sách.

## 13. Hiệu năng: AES-GCM hay ChaCha20-Poly1305?

Một hệ thống TLS phục vụ nhiều kết nối, chẳng hạn API gateway hoặc reverse proxy, cần cân nhắc hiệu năng handshake và record processing.

### 13.1. AES-GCM và tăng tốc phần cứng

AES-GCM thường có lợi khi CPU/SoC hỗ trợ **AES acceleration và các phép toán cần cho GCM**. Tuy nhiên việc có tên AES-NI trong thông số CPU không tự chứng minh mọi tác vụ GCM đều được tăng tốc hiệu quả; cần kiểm tra kernel/library/hardware path.

### 13.2. ChaCha20-Poly1305 trên CPU không tăng tốc AES

ChaCha20-Poly1305 là thuật toán AEAD hiện đại, có thể rất cạnh tranh ở những nền tảng không có tăng tốc AES chuyên dụng. Một số client mobile hoặc thiết bị nhúng có thể hưởng lợi, tùy triển khai.

### 13.3. Những yếu tố gây sai lệch benchmark

- CPU/server không giống client thực.
- TLS termination chạy trên CDN hoặc phần cứng appliance thay vì server ứng dụng.
- Tốc độ handshake bị giới hạn bởi RSA/ECDSA verify, network RTT hoặc PKI.
- Record size và tỷ lệ kết nối ngắn/dài khác nhau.
- HTTP/2 multiplexing, HTTP/3 QUIC và session resumption làm thay đổi chi phí.
- mTLS có thêm client certificate verification.
- IPS/WAF logging và proxy transform tạo overhead ngoài crypto.
- CPU giới hạn nhiệt/điện hoặc autoscaling làm tăng chi phí cloud.
- Dữ liệu đo quá ít, không có p95/p99, error rate hoặc saturation.

**Không kết luận AES-256 luôn chậm đáng kể** hay ChaCha20 luôn nhanh hơn chỉ từ một benchmark. Cần test workload thật với thư viện TLS và platform đã chọn.

## 14. Tương thích và lựa chọn phiên bản

Trong nhiều triển khai, lựa chọn thực tế là:

1. **Ưu tiên TLS 1.3** cho các client/servers hỗ trợ.
2. **Cho TLS 1.2** trên những endpoint còn cần tương thích, giới hạn vào các ECDHE+AEAD suite được phê duyệt.
3. **Không bật TLS 1.0/1.1 và SSL cũ** cho profile bảo mật hiện đại.
4. Kiểm tra những client Java, Windows, thiết bị nhúng và thư viện cũ đang sử dụng version nào.
5. Phân loại exception có owner, kỳ hạn nâng cấp và giới hạn mạng.
6. Duy trì telemetry để biết client nào còn TLS 1.2 và do yêu cầu gì.

### 14.1. TLS client compatibility là kết quả kiểm thử, không phải dự đoán

Không nên suy ra một ứng dụng **Java** cụ thể chỉ từ phiên bản ngôn ngữ; còn phụ thuộc runtime, security provider, JVM flags, trust store, server policy và bản vá. Với Windows cũng phải xét SCHANNEL/OS policy. Với browser, phiên bản và chính sách enterprise ảnh hưởng supported suites/groups.

**ClientHello** cho biết những khả năng client quảng bá ở phiên cụ thể; handshake thành công cho biết tổ hợp thực tế được chọn. Không có một danh sách “mọi client Java” dùng chung.

### 14.2. Lỗi no shared cipher

Nếu client và server không có cipher suite hoặc nhóm/thuật toán chữ ký tương thích, handshake có thể thất bại. Các lỗi bên ngoài có thể được báo là **handshake_failure**, **protocol_version**, **no shared cipher**, hoặc lỗi khác tùy stack.

Để chẩn đoán, cần xét đồng thời:
- TLS version.
- Cipher suites.
- Supported groups/key shares.
- Signature algorithms/certificate type.
- Chứng chỉ/tên và trust.
- SNI/ALPN, reverse proxy route và mTLS.
- Policy cấm thuật toán ở OS/provider.
- Sự khác biệt giữa endpoint công khai và origin.

## 15. Lựa chọn theo compliance và môi trường quản trị

Một số tổ chức phải theo tiêu chuẩn hoặc yêu cầu của khách hàng, có thể đề cập đến **NIST, FIPS 140 validated cryptographic modules**, chuẩn ngành hay chính sách cấp tổ chức.

### 15.1. Thuật toán được chấp nhận khác module được chứng nhận

Câu “AES-256 là FIPS-compliant” theo cách diễn đạt chung chung là thiếu chính xác. FIPS có thể yêu cầu **một cryptographic module đã được xác nhận, ở chế độ và phiên bản được phép**, với tập thuật toán, cài đặt và môi trường vận hành phù hợp. Tên AES trong cipher suite **không tự chứng minh** hệ thống đang đáp ứng toàn bộ yêu cầu.

Cần hỏi:
- Tài liệu/chính sách nào áp dụng, phiên bản nào?
- Sản phẩm và crypto module có trạng thái xác nhận nào?
- Phiên bản OpenSSL/BoringSSL/OS crypto provider có nằm trong scope không?
- Có bật đúng compliance mode và kiểm soát theo chính sách không?
- Những nhóm ECDHE, hash, signature và PSK mode có được cho phép?
- Log và evidence kiểm toán có được lưu đủ?

### 15.2. ChaCha20-Poly1305 trong môi trường giới hạn

Một thuật toán có thể an toàn về mật mã trong TLS hiện đại nhưng **không nằm trong profile thuật toán được một tổ chức/hệ thống chứng nhận cụ thể chấp nhận**. Vì vậy việc chọn ChaCha20-Poly1305 hay AES-GCM cần xét **policy** riêng, không chỉ độ mạnh.

### 15.3. Tách endpoint khi có client legacy đặc biệt

Nếu một thiết bị không nâng cấp được, có thể cân nhắc kiến trúc:

~~~text
Client hiện đại ---> Public TLS 1.3/1.2 AEAD endpoint
Client legacy ----> Gateway riêng, network ACL chặt
                         |
                         v
                Backend qua TLS profile mạnh
~~~

Gateway ngoại lệ **không biến kết nối client legacy thành an toàn như TLS 1.3**; nó chỉ giới hạn phạm vi phơi bày và giúp kiểm soát quá trình chuyển đổi. Cần owner, thời hạn, giám sát rủi ro và kế hoạch loại bỏ.

## 16. Đề xuất hồ sơ TLS theo nhóm hệ thống

### 16.1. Hồ sơ A — Website/API hiện đại

- Cho phép TLS 1.3; hỗ trợ TLS 1.2 **chỉ khi còn nhu cầu tương thích hợp lý**.
- TLS 1.3 dùng các AEAD phổ biến như **TLS_AES_128_GCM_SHA256**, **TLS_AES_256_GCM_SHA384**, **TLS_CHACHA20_POLY1305_SHA256** theo policy và thư viện.
- TLS 1.2 nếu bật: **ECDHE + AES-GCM hoặc ChaCha20-Poly1305** cùng xác thực phù hợp.
- Certificate chain và hostname verification đúng; quản lý cấp/thay cert.
- Groups/signature algorithms hiện đại, không dùng anonymous/static RSA key transport.
- Không có HTTP plaintext vào vùng nhạy cảm ngoài ngoại lệ được kiểm soát; dùng HTTPS redirect/HSTS theo thiết kế.
- Có logging negotiated TLS version/cipher, lỗi handshake, mTLS status và certificate expiry.

### 16.2. Hồ sơ B — API nội bộ yêu cầu mTLS

- TLS 1.3 nếu client/service mesh hỗ trợ; tương thích TLS 1.2 theo chính sách nếu cần.
- Mutual authentication bằng certificate/workload identity được quản lý.
- Chọn AEAD phù hợp module và hiệu năng.
- Authorization theo service identity và path/operation, không chỉ “đã có chứng chỉ”.
- Certificate rotation/revocation hoặc workload identity lifecycle tự động hóa.
- Nguồn logs đủ để biết workload nào kết nối; tránh ghi secret.
- Kiểm tra service-to-service qua proxy và những đường bypass mesh.

### 16.3. Hồ sơ C — Thiết bị legacy trong vùng cô lập

- Chỉ chấp nhận client thực sự cần và có kế hoạch thay thế.
- Endpoint tách biệt, firewall allowlist chặt, không mở toàn Internet nếu không cần.
- Ưu tiên TLS 1.2 với AEAD nếu thiết bị hỗ trợ; không hạ xuống suite yếu ngoài policy.
- Có cảnh báo client lỗi thời, theo dõi phiên bản/suite, owner và deadline.
- Backend nối qua kênh bảo mật đạt profile hiện đại.
- Test cả positive/negative behavior và đường dữ liệu sau proxy.

### 16.4. Hồ sơ D — Cloud load balancer và CDN

- Xác định **TLS client → CDN/LB** và **TLS CDN/LB → origin** là hai phiên khác nhau.
- Mỗi hop có policy version/cipher/certificate/verification riêng.
- Ghi log negotiated TLS cho từng hop khi nhà cung cấp hỗ trợ.
- Kiểm tra origin có bị truy cập trực tiếp bỏ qua edge không.
- Không tin vào “Full (strict)” hoặc một nhãn sản phẩm nếu chưa xác định certificate validation, trust và đường kết nối.
- Xem giới hạn thuật toán do cloud provider quản lý; có thể chỉ chọn **predefined TLS security policy**, không cấu hình suite riêng.

## 17. Cấu hình mẫu và những điều không nên hiểu sai

Các ví dụ dưới đây là **mẫu minh họa**, không phải cấu hình khuyến nghị áp dụng nguyên vẹn cho mọi version. Trước khi triển khai cần đọc tài liệu của **đúng phần mềm, OpenSSL/crypto backend, OS và profile đã phê duyệt**.

### 17.1. Ví dụ cấu hình Nginx

~~~nginx
# Ví dụ cho môi trường thử nghiệm; cần kiểm chứng version và hỗ trợ
server {
    listen 443 ssl;
    server_name tls.lab.example;

    ssl_certificate     /etc/tls/lab/fullchain.pem;
    ssl_certificate_key /etc/tls/lab/private.key;

    ssl_protocols TLSv1.2 TLSv1.3;

    # ssl_ciphers chủ yếu áp dụng cho TLS <= 1.2 trên nhiều Nginx/OpenSSL.
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';

    # TLS 1.3 cipher suites có cơ chế cấu hình riêng, tùy Nginx/OpenSSL.
    # Không dùng ssl_ciphers để cho rằng đã kiểm soát TLS 1.3.
}
~~~

Giới hạn:

- Đây **không phải cấu hình hoàn chỉnh**: còn chứng chỉ thật, server block, quyền file, HSTS, OCSP theo chính sách, session, logging, reverse proxy và security headers.
- Tên **ECDHE-RSA-AES128-GCM-SHA256** là alias thường thấy ở OpenSSL/Nginx cho suite TLS 1.2 tương ứng.
- Có thể dùng cơ chế cấu hình TLS 1.3 riêng tùy build, chẳng hạn giao diện OpenSSL **Ciphersuites** được sản phẩm hỗ trợ; không giả định một directive hoạt động trên mọi bản Nginx.
- Cần xác minh cert type phù hợp, groups, signatures và negotiated suite thực tế sau triển khai.
- Server có thể chịu ảnh hưởng chính sách crypto toàn hệ điều hành và container image.

### 17.2. Trong Java/JSSE

Với hệ sinh thái Java, TLS sử dụng security provider và cấu hình runtime. Các yếu tố cần xem:

- Runtime/JDK version và nhà cung cấp TLS.
- **EnabledProtocols / enabled cipher suites** ở client/server cụ thể.
- Trust store, key store, endpoint identification và mTLS.
- Security properties loại bỏ thuật toán không chấp nhận.
- Supported groups, signature algorithms và client auth.
- Tác động từ framework như Spring, Tomcat, Netty hoặc reverse proxy đặt trước.

**Không kết luận JDK hỗ trợ TLS 1.3 nghĩa mọi ứng dụng Java tự dùng TLS 1.3.** Library/framework, endpoint và chính sách có thể giới hạn phiên bản hoặc loại suite.

### 17.3. Trong cloud managed services

Nhiều load balancer, CDN và API gateway có **TLS security policy/profile** do provider quản lý. Người vận hành có thể chọn profile nhưng không sửa từng suite. Hãy kiểm tra:

1. TLS versions được profile cho phép.
2. Danh sách suites thực tế và ưu tiên thương lượng.
3. Chứng chỉ RSA/ECDSA, SNI, ALPN và client auth nếu hỗ trợ.
4. Support cho HTTP/2 và HTTP/3/QUIC.
5. Chứng chỉ và TLS profile của **origin**.
6. Điều gì xảy ra khi profile/phiên bản thay đổi và cách rollback.

Một profile có tên “modern” không thay thế kiểm tra **thực tế negotiated version/cipher** và khả năng kết nối từ client đại diện.

## 18. Lệnh quan sát và kiểm chứng an toàn

Những lệnh sau chỉ chạy với **endpoint do bạn quản trị hoặc được phép kiểm tra**. Các tên **tls.lab.example** chỉ là placeholder; không đại diện một dịch vụ đã sẵn sàng. Những lệnh kiểm tra bên dưới tạo kết nối TLS đơn lẻ, không tạo tải cao.

### 18.1. Kiểm tra phiên bản OpenSSL

~~~bash
openssl version -a

# Liệt kê tên cipher theo library/config hiện hành
openssl ciphers -v
~~~

**openssl ciphers** cho biết khả năng/cấu hình của thư viện theo lệnh và profile được chọn, **không chứng minh server đích đã bật toàn bộ**. Các tùy chọn và output thay đổi theo version.

### 18.2. Quan sát handshake TLS 1.3

~~~bash
# Endpoint phải là tài sản lab của bạn, DNS và cert cần hợp lệ
openssl s_client \
  -connect tls.lab.example:443 \
  -servername tls.lab.example \
  -tls1_3 \
  -verify_return_error \
  -verify_hostname tls.lab.example \
  -brief
~~~

Đọc các trường:

- Negotiated protocol version.
- Negotiated cipher suite.
- Certificate verification outcome, hostname verification và trust.
- Peer certificate/key/signature khi output hỗ trợ.
- ALPN nếu client/server có cung cấp qua tùy chọn phù hợp.

**-servername** gửi SNI, không thay thế xác minh hostname. **-verify_hostname** và **-verify_return_error** cần OpenSSL version hỗ trợ và trust store phù hợp. Một lệnh s_client không mô phỏng toàn bộ policy của browser/Java client.

### 18.3. Thử một TLS 1.3 cipher suite cụ thể trong lab

~~~bash
openssl s_client \
  -connect tls.lab.example:443 \
  -servername tls.lab.example \
  -tls1_3 \
  -ciphersuites TLS_AES_128_GCM_SHA256 \
  -verify_return_error \
  -verify_hostname tls.lab.example \
  -brief
~~~

Nếu handshake thất bại, nguyên nhân có thể là suite bị tắt, version/group/signature không khớp, cert/mTLS hoặc policy khác. Không được kết luận ngay “AES-GCM không an toàn”.

**Phân biệt tùy chọn:** nhiều phiên bản OpenSSL dùng **-cipher** để điều chỉnh TLS 1.2 và **-ciphersuites** cho TLS 1.3. Tránh nghĩ một danh sách dùng chung có thể kiểm soát cả hai phiên bản.

### 18.4. Kiểm tra TLS 1.2 suite khi endpoint hỗ trợ

~~~bash
openssl s_client \
  -connect tls.lab.example:443 \
  -servername tls.lab.example \
  -tls1_2 \
  -cipher ECDHE-RSA-AES128-GCM-SHA256 \
  -verify_return_error \
  -verify_hostname tls.lab.example \
  -brief
~~~

Kết nối có thể thất bại nếu server chỉ dùng chứng chỉ ECDSA hoặc không hỗ trợ suite này, ngay cả khi endpoint có TLS 1.2 mạnh. Chọn suite kiểm tra **phù hợp loại chứng chỉ và profile**. Không giảm server security profile để chỉ làm câu lệnh demo chạy được.

### 18.5. Kiểm tra HTTPS bằng curl

~~~bash
# Kết nối HTTPS và xem thông tin vận hành/response
curl -Iv --tlsv1.3 --tls-max 1.3 https://tls.lab.example/
~~~

Tùy chọn **--tlsv1.3** yêu cầu tối thiểu TLS 1.3 trên những bản curl hỗ trợ; dùng **--tls-max 1.3** khi muốn giới hạn tối đa. Curl phụ thuộc TLS backend và certificate trust store; lỗi HTTP 403 hay 404 sau khi TLS thành công **không tự là lỗi cipher suite**.

### 18.6. Không đưa private key hoặc session secret vào log

Không dùng cờ debug làm lộ key material để “chứng minh cipher mạnh” trong hệ thống thật. Các dạng key log phục vụ giải mã packet capture, khi cần trong lab, phải được quản lý như **bí mật nhạy cảm**. Không đăng chúng vào ticket/chat/repo không được phép.

## 19. Cách đọc kết quả thử nghiệm

Giả sử một endpoint lab trả về:

~~~text
Protocol version: TLSv1.3
Ciphersuite: TLS_AES_128_GCM_SHA256
Peer certificate: verified for tls.lab.example
ALPN: h2
~~~

**Những điều có thể kết luận:**

- Kết nối thử đã thương lượng TLS 1.3.
- Suite bảo vệ record được báo là AES-128-GCM với SHA-256 theo TLS 1.3.
- Công cụ báo chứng chỉ được xác minh theo tùy chọn trust/name đã dùng.
- ALPN được chọn là h2 trong phiên giả định.

**Những điều chưa thể kết luận:**

- Tất cả client đều dùng TLS 1.3 hay cùng suite.
- Endpoint không hỗ trợ TLS 1.2/cipher yếu nếu chưa test negative.
- TLS giữa load balancer và backend cũng được bảo vệ tương đương.
- Client đã dùng (EC)DHE trong mọi resumption/PSK case.
- Ứng dụng đã xác thực/ủy quyền user thành công.
- Không có lỗi ứng dụng hoặc dữ liệu cá nhân bị rò ở endpoint.

### 19.1. Phân biệt lỗi TLS và lỗi ứng dụng

| Triệu chứng | Hướng xác minh |
|---|---|
| Protocol version alert | Client/server không có version chung hoặc policy chặn |
| No shared cipher | Xem version, cipher suites, cert, groups, signatures |
| Certificate verify failed | Trust, hostname, SAN, chain, thời gian, policy |
| Handshake timeout | Routing, firewall, proxy, MTU, TLS backend load |
| TLS thành công nhưng HTTP 401/403 | Authorization/app authentication, không phải cipher |
| HTTP 502/503 tại reverse proxy | Backend/TLS upstream/health/route, không chỉ cipher client |
| Một số client Java lỗi | JDK provider, truststore, disabled algorithms, SNI/ALPN |
| Chỉ HTTP/3 lỗi | QUIC/UDP path, LB/proxy support, TLS 1.3 handshake đặc thù |
| mTLS client lỗi | Client certificate, issuer, EKU, revocation, identity policy |

## 20. Phiên TLS tại proxy, CDN, WAF và VPN

Trong kiến trúc mạng, có thể tồn tại **nhiều phiên TLS riêng biệt**.

~~~mermaid
flowchart LR
    C[Client] -->|TLS A| EDGE[CDN / WAF]
    EDGE -->|TLS B hoặc policy riêng| LB[Load balancer]
    LB -->|TLS C hoặc mTLS| APP[Application]
    APP -->|TLS D| DB[(Database)]
    EDGE -.TLS logs.-> SIEM[SIEM]
    LB -.Upstream TLS logs.-> SIEM
    APP -.App/DB auth.-> SIEM
~~~

Một edge có thể cho client **TLS_AES_128_GCM_SHA256** nhưng phía origin dùng TLS 1.2 hoặc thậm chí plaintext nếu thiết kế sai. **Không suy từ TLS của trình duyệt ra toàn bộ đường truyền end-to-end**.

### 20.1. TLS termination và kiểm tra bảo mật

- **CDN/WAF:** có thể giải mã để áp policy HTTP, rồi tạo một phiên TLS khác tới origin.
- **Reverse proxy:** có certificate và cipher policy phía client, và trust policy riêng khi nối backend.
- **Service mesh:** mTLS giữa workload/proxy, certificate identity và authorization qua control plane.
- **VPN TLS:** phải phân biệt data channel của sản phẩm với HTTPS/TLS ứng dụng bên trong.
- **DoH/DoT:** bảo vệ kết nối client–resolver; phía resolver có thể tiếp tục tra cứu DNS theo đường khác.

Khi đánh giá crypto, ghi rõ **hop nào có policy nào** và liệu secret hoặc dữ liệu đã giải mã có đi qua nơi không được phê duyệt không.

### 20.2. IDS/IPS quan sát điều gì?

NIDS nằm trước TLS termination thường thấy IP, port, timing, kích thước và một số handshake metadata tùy giao thức. Nó **không đọc được HTTP payload** đã mã hóa chỉ từ packet capture thông thường.

Có thể lấy dữ liệu giải thích từ WAF, reverse proxy, app logs hoặc endpoint telemetry tại điểm hợp pháp sau giải mã. Không tắt TLS để IDS đọc payload khi chưa đánh giá yêu cầu bảo mật/quyền riêng tư.

## 21. TLS 1.3 session resumption, 0-RTT và replay

TLS 1.3 cho phép **session resumption** dựa trên PSK/ticket. Điều này có thể giảm chi phí handshake, hữu ích khi client kết nối lại hoặc hệ thống có nhiều phiên ngắn.

### 21.1. 0-RTT không đồng nghĩa an toàn với mọi nghiệp vụ

Khi **0-RTT early data** được dùng, dữ liệu có thể được gửi trước khi handshake hoàn tất. Theo mô hình TLS 1.3, **early data có nguy cơ replay** và không có đầy đủ thuộc tính như dữ liệu sau handshake theo mọi khía cạnh.

Vì vậy:
- Không mặc định bật 0-RTT cho các thao tác đổi trạng thái như **thanh toán, chuyển tiền, thay mật khẩu, tạo đơn**.
- Khi dùng 0-RTT cho request phù hợp, ứng dụng và edge cần cơ chế giới hạn replay/anti-replay theo thiết kế.
- Phân biệt nhận early data ở CDN với backend thực sự xử lý request.
- Cần có log và kịch bản test riêng cho early data.
- Không đánh đồng 0-RTT với lựa chọn **TLS_AES_128_GCM_SHA256**; đó là thuộc tính handshake/session, không phải AEAD suite.

### 21.2. Session ticket và quyền quản trị khóa

Session ticket/PSK có vòng đời và key material riêng. Một hệ thống có nhiều TLS terminators cần quản lý **ticket keys/rotation**, thời hạn, phạm vi chia sẻ và khả năng revoke. Không dùng key cố định quá lâu hoặc chia sẻ secret ngoài phạm vi thiết kế chỉ để tăng hit rate resumption.

## 22. Quy trình chọn và kiểm thử profile TLS

### Bước 1 — Định nghĩa endpoint

Xác định hostname, IP/LB, port, SNI, ALPN, loại client, nhóm người dùng và chặng TLS. Với mTLS, xác định CA/identity của client và quyền của service.

### Bước 2 — Chốt yêu cầu bắt buộc

Ghi phiên bản TLS tối thiểu, AEAD, forward secrecy, certificate policy, groups/signatures, compliance, logging và độ sẵn sàng. Phân biệt các ngoại lệ dành cho client cũ.

### Bước 3 — Kiểm tra hỗ trợ thực tế

Thu thông tin từ **server TLS library, OS, client runtimes, cloud provider profile và certificate type**. Không dùng danh sách cipher lấy từ một máy khác để kết luận về server thật.

### Bước 4 — Chọn candidate profiles

Ưu tiên profile TLS 1.3 đã bảo trì; nếu cần TLS 1.2, chỉ giữ **ECDHE+AEAD** phù hợp với cert/client. Không thêm cipher yếu chỉ để đạt “hỗ trợ càng nhiều càng tốt”.

### Bước 5 — Kiểm thử trong lab/staging

Thử client representative, certificate validation, TLS versions, cipher negotiation, supported groups, mTLS, resumption, HTTP/2/3, routing, firewall và negative cases. Ghi kết quả với timestamp, client/server version và evidence.

### Bước 6 — Triển khai có kiểm soát

Rollout theo canary/nhóm nhỏ, theo dõi handshake failures, app success rate, p95/p99 latency và CPU. Có cách rollback **về profile an toàn đã phê duyệt**, không rollback sang cấu hình yếu không kiểm soát.

### Bước 7 — Duy trì

Review định kỳ certificate expiry, library patches, cipher/profile drift, client legacy usage, 0-RTT/resumption, compliance và changes từ cloud provider. Cập nhật ma trận test khi có phiên bản mới hoặc endpoint thay đổi.

## 23. Ma trận kiểm thử TLS theo giao thức, cipher và chính sách

| Test | Điều kiện | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| T01 | Client TLS 1.3 hiện đại, certificate hợp lệ | Handshake thành công và cipher thuộc allowlist | Client log + server TLS metrics |
| T02 | TLS 1.3 AES-128-GCM được phép | Thương lượng khi cả hai hỗ trợ | Negotiated suite |
| T03 | TLS 1.3 ChaCha20 được phép | Có thể thương lượng trên client hỗ trợ | Negotiated suite và backend |
| T04 | TLS 1.2 ECDHE+AES-GCM được phê duyệt | Thành công nếu endpoint hỗ trợ TLS 1.2 | Protocol, cipher, certificate |
| T05 | Client chỉ hỗ trợ TLS 1.0/1.1 | Bị từ chối theo policy | Handshake failure có kiểm soát |
| T06 | Suite RC4/NULL/3DES hoặc static RSA bị cấm | Không thương lượng thành công | Server profile + negative test trong lab |
| T07 | Hostname không khớp certificate | Client xác minh đúng và từ chối | Verify error |
| T08 | Certificate hết hạn hoặc chain không tin cậy | Không vượt qua xác minh | Client validation log |
| T09 | Client chỉ hỗ trợ group không được phép | Bị từ chối hoặc xử lý theo profile | Handshake/alert và supported groups |
| T10 | Server dùng RSA và ECDSA cert tùy SNI | Chọn certificate/signature tương thích | SNI, cert và negotiated TLS |
| T11 | mTLS client không có chứng chỉ hợp lệ | Bị từ chối theo policy | Gateway auth + TLS logs |
| T12 | App yêu cầu ALPN h2 | Chọn đúng protocol/behavior được hỗ trợ | ALPN, HTTP transaction |
| T13 | TLS 1.3 resumption với PSK | Đúng key policy và app hoạt động | Resumption log, expiry |
| T14 | Endpoint nhận 0-RTT | Chỉ xử lý nghiệp vụ được phép và có anti-replay | Edge/app logs |
| T15 | CDN → origin | TLS profile/certificate đúng ở hop upstream | Origin handshake + CDN logs |
| T16 | Library/server được nâng cấp | Không tự bật lại cipher/protocol bị cấm | Configuration diff + scan có quyền |
| T17 | CPU/băng thông ở tải POC được duyệt | Không vượt SLO đã xác định | CPU, p95/p99, handshake rate |
| T18 | Client Java/Windows/mobile đại diện | Client có thể kết nối với cert và suite phù hợp | Real client logs |
| T19 | Session ticket key rotation | Client reconnect đúng, không lỗi lan rộng | TLS terminator logs |
| T20 | TLS endpoint hết chứng chỉ trong lab | Monitoring/renewal/rollback hoạt động | Expiry alert, test failure |
| T21 | Firewall/IDS tại trước termination | Chỉ nhìn metadata trong ciphertext | Packet/flow + app log |
| T22 | Endpoint khác SNI trên cùng LB | Không rơi vào default cert/profile sai | SNI-specific verification |

**Không ghi PASS nếu chưa chạy và có bằng chứng.** Một phép thử chỉ ép cipher trên công cụ CLI khác với kiểm thử app production đầy đủ. Trường hợp **NOT_RUN/BLOCKED/INCONCLUSIVE** cần được ghi rõ.

## 24. Tình huống thực hành có đáp án gợi ý

### Tình huống A — Server dùng TLS 1.3 và AES-128-GCM

Một báo cáo gọi **TLS_AES_128_GCM_SHA256** là “yếu vì không có RSA hoặc ECDHE trong tên”.

**Gợi ý:** nhận xét sai. Trong TLS 1.3, suite không chứa key exchange/signature trong tên; phải xem **supported group/key share và certificate signature** được thương lượng riêng. AES-128-GCM là AEAD hiện đại, không bị coi yếu chỉ vì khóa 128-bit.

### Tình huống B — Chuyển sang AES-256 nhưng client vẫn báo MITM

Endpoint dùng TLS_AES_256_GCM_SHA384, nhưng ứng dụng mobile bỏ kiểm tra hostname/certificate.

**Gợi ý:** cipher suite mạnh không thay thế xác thực server. Client có thể thiết lập kênh mã hóa tới endpoint sai. Ưu tiên sửa hostname/trust validation, sau đó đánh giá cipher/group/signature.

### Tình huống C — TLS 1.2 ECDHE_RSA và TLS_RSA cùng dùng AES-GCM

Hai suite đều kết thúc bằng **AES_128_GCM_SHA256**, nhưng tiền tố khác nhau.

**Gợi ý:** ECDHE_RSA trao đổi khóa ephemeral và dùng RSA authentication, hỗ trợ forward secrecy theo điều kiện; TLS_RSA là RSA key transport và không có thuộc tính FS tương đương. Record cipher giống nhau không làm hai suite có cùng security profile.

### Tình huống D — Thiết bị IoT chỉ biết TLS 1.0

Một bộ cảm biến không nâng cấp được, gây lỗi khi server tắt TLS 1.0.

**Gợi ý:** không bật TLS 1.0 trên toàn API public. Đánh giá thay thiết bị, gateway tách biệt, mạng cô lập, profile ngoại lệ được phê duyệt có thời hạn và logging. Ghi rõ rủi ro còn lại.

### Tình huống E — ChaCha20 được quảng bá nhanh hơn AES

Một kỹ sư đề xuất chỉ giữ ChaCha20-Poly1305 vì “luôn nhanh hơn AES-GCM”.

**Gợi ý:** hiệu năng tùy CPU, AES acceleration, thư viện, lưu lượng và client. Giữ tập AEAD được phép theo profile, đo thực tế trên server/client đại diện và không áp đặt chỉ số một nền tảng cho mọi thiết bị.

### Tình huống F — Cloud LB TLS 1.3 nhưng origin dùng plaintext

Người dùng thấy khóa HTTPS ở browser, công ty tuyên bố dữ liệu đã mã hóa end-to-end tới ứng dụng.

**Gợi ý:** trình duyệt chỉ kiểm chứng phiên client–LB. Nếu LB → origin là plaintext, kết luận end-to-end sai; cần kiểm tra TLS/mTLS upstream, certificate validation, private network, firewall và policy tại mỗi hop.

### Tình huống G — Nginx đã đặt ssl_ciphers nhưng TLS 1.3 không đổi

Admin thay danh sách ssl_ciphers và không thấy TLS 1.3 suite mới.

**Gợi ý:** trên nhiều Nginx/OpenSSL, ssl_ciphers áp cho TLS 1.2 và cũ hơn; TLS 1.3 ciphersuites có cơ chế cấu hình riêng hoặc do library/provider profile quản lý. Kiểm tra version, module và thử handshake đúng TLS 1.3.

### Tình huống H — TLS 1.3 resumption không dùng ECDHE

Một hệ thống bật PSK-only resumption và khẳng định “TLS 1.3 đương nhiên có forward secrecy trong mọi phiên”.

**Gợi ý:** không chính xác. Cần đánh giá **PSK key exchange mode**, có kết hợp (EC)DHE hay không, ticket lifetime và key security. AEAD cipher suite không tiết lộ tất cả thuộc tính key exchange.

### Tình huống I — HTTP/2 bị từ chối dù TLS thành công

Client thương lượng TLS 1.2 AEAD hợp lệ nhưng không đạt yêu cầu ứng dụng/protocol khi ALPN hoặc profile HTTP/2 không phù hợp.

**Gợi ý:** TLS handshake thành công không có nghĩa HTTP/2 được sử dụng. Kiểm tra ALPN, HTTP/2 cipher/version restrictions ở stack cụ thể, server config và response. Phân biệt lỗi giao thức ứng dụng với lỗi mật mã.

### Tình huống J — Cert ECDSA và client legacy

Một server chỉ dùng cert ECDSA/TLS 1.2, trong khi một client cũ chỉ hỗ trợ những suite TLS 1.2 xác thực RSA.

**Gợi ý:** không nhất thiết lỗi AES-GCM. Client và server không có tổ hợp certificate/signature/suite tương thích. Có thể dùng profile và certificate RSA hợp lệ song song khi sản phẩm hỗ trợ, hoặc nâng cấp client; không bật anonymous/static RSA key transport vì tương thích.

### Tình huống K — SOC không thấy nội dung HTTP sau bật TLS 1.3

NIDS ở firewall biên không còn đọc payload ứng dụng nhưng firewall flow log vẫn có metadata.

**Gợi ý:** TLS bảo vệ nội dung kênh; NIDS trước termination không giải mã HTTP body. Thu telemetry ở WAF/reverse proxy/application/endpoint theo quyền được cấp, không kết luận IDS bị tắt hoặc disable TLS để lấy payload.

### Tình huống L — Kiểm thử chỉ thấy một cipher

Một phép s_client kết nối thành công với TLS_AES_128_GCM_SHA256; báo cáo kết luận server không hỗ trợ cipher yếu nào khác.

**Gợi ý:** một negotiated suite chỉ chứng minh **một đường thương lượng thành công**. Cần kiểm tra allowed protocol/cipher profile, những negative tests ở lab và các hostname/SNI khác; không dùng một phép kết nối để suy ra đầy đủ server capabilities.

### Tình huống M — Chính sách yêu cầu FIPS

Ứng dụng bật AES-256-GCM và đánh dấu **FIPS compliant**, nhưng không biết crypto module, cấu hình hay phạm vi chứng nhận.

**Gợi ý:** phải xác định chính sách cụ thể, module/provider được phê duyệt, version và mode được phép. Tên cipher đơn lẻ không chứng minh tuân thủ. Nếu profile không cho ChaCha20, đó là yêu cầu compliance của môi trường, không đồng nghĩa nó yếu về mật mã.

### Tình huống N — API thay đổi state chấp nhận 0-RTT

Một CDN cho phép 0-RTT tới endpoint tạo đơn hàng, không có cơ chế chống replay ở ứng dụng.

**Gợi ý:** không nên coi 0-RTT như request sau handshake. Rà soát replay/idempotency và policy nhận early data; tắt 0-RTT cho thao tác thay đổi trạng thái nếu chưa có biện pháp phù hợp.

## 25. Những sai lầm thường gặp

1. **Đọc TLS 1.3 suite như TLS 1.2.** Tên TLS 1.3 không chỉ rõ ECDHE/RSA.
2. **Coi AES-256 tự động an toàn hơn mọi phương án.** Thiếu cert verification vẫn tạo rủi ro lớn.
3. **Đánh đồng SHA256 ở tên suite với mã hóa payload.** Trong TLS 1.3, hash phục vụ HKDF/key schedule.
4. **Coi TLS 1.3 mọi trường hợp đều forward-secret.** PSK-only/resumption cần phân tích riêng.
5. **Coi RSA trong ECDHE_RSA là thuật toán mã hóa nội dung.** Nó liên quan xác thực handshake.
6. **Coi TLS_RSA_WITH_AES_GCM ngang với ECDHE_RSA vì đều AES-GCM.** Khác forward secrecy.
7. **Bật RC4/3DES/CBC cũ chỉ để có nhiều cipher.** Mở rộng attack surface mà ít giá trị.
8. **Dùng NULL/anonymous/EXPORT suites để debug.** Làm mất thuộc tính mật mã quan trọng.
9. **Tin danh sách openssl ciphers là danh sách server bật.** Đó là library/local policy.
10. **Chỉ chạy một handshake rồi kết luận policy an toàn.** Thiếu negative tests và client coverage.
11. **Bỏ qua nhóm trao đổi khóa.** Suite TLS 1.3 không định nghĩa toàn bộ group/key share.
12. **Bỏ qua loại chứng chỉ.** TLS 1.2 ECDHE_ECDSA/RSA cần khả năng xác thực tương ứng.
13. **Bỏ kiểm tra hostname khi test.** SNI không thay certificate verification.
14. **Nhầm cert hợp lệ với authorization.** mTLS identity còn cần quyền ứng dụng.
15. **Không đánh giá TLS CDN–origin.** Browser TLS đúng không chứng minh đường nội bộ đã mã hóa.
16. **Không xét QUIC/HTTP/3.** Cấu hình TLS/TCP không đại diện hoàn toàn cho QUIC.
17. **Không xét 0-RTT replay.** Đặc biệt nguy hiểm với thao tác đổi trạng thái nếu thiếu bảo vệ.
18. **Cho rằng ChaCha20 luôn nhanh hơn AES-GCM.** CPU acceleration tạo khác biệt.
19. **Cho rằng AES-256 trong tên suite chứng minh FIPS compliance.** Cần module và mode hợp lệ.
20. **Không theo dõi certificate expiry/rotation.** Cipher tốt nhưng chứng chỉ hết hạn vẫn outage.
21. **Không lưu negotiated TLS version/cipher.** Khó xác minh rollout và tương thích.
22. **Mở lại TLS 1.0 cho một client legacy trên endpoint chung.** Làm giảm baseline cho mọi người.
23. **Không review disabledAlgorithms/provider policy.** Các cấu hình hệ điều hành/JDK có thể khác.
24. **Không thử failback/rollback.** Upgrade crypto có thể gây outage nếu chỉ thử một client.
25. **Bỏ qua firewall/IPS và dịch vụ phía sau.** TLS thành công không đồng nghĩa ứng dụng có quyền hay còn hoạt động.

## 26. Checklist lựa chọn và vận hành cipher suite TLS

- [ ] Xác định **mỗi chặng TLS** gồm client–edge, edge–origin, app–DB, VPN hoặc DoH/DoT.
- [ ] Có threat model và yêu cầu về bí mật, xác thực, toàn vẹn và availability.
- [ ] Ưu tiên TLS 1.3; TLS 1.2 chỉ khi cần và dùng AEAD+ECDHE theo profile.
- [ ] Không dùng SSL cũ, TLS 1.0/1.1, RC4, 3DES, NULL, anonymous hay EXPORT.
- [ ] Không dùng static RSA key transport trong profile hiện đại.
- [ ] Hiểu cipher suite TLS 1.3 tách khỏi key exchange group và signature.
- [ ] Chọn AEAD như AES-GCM hoặc ChaCha20-Poly1305 theo policy và hỗ trợ thực tế.
- [ ] Không bật CCM_8 chung nếu không có lý do/profile chuyên biệt.
- [ ] Xác minh key exchange groups, ephemeral secrets và PSK/resumption mode.
- [ ] Có chính sách certificate chain, hostname/SAN, key usage, trust và expiry.
- [ ] Đánh giá RSA/ECDSA/EdDSA theo hỗ trợ client và yêu cầu certificate.
- [ ] Nếu dùng mTLS, kiểm tra client cert **và** authorization sau handshake.
- [ ] Kiểm tra ALPN/HTTP2/HTTP3/QUIC trong môi trường có hỗ trợ.
- [ ] Nếu dùng 0-RTT, có chính sách replay và chỉ cho nghiệp vụ phù hợp.
- [ ] Gắn lựa chọn với OS/library/framework/cloud policy được xác minh.
- [ ] Kiểm tra khả năng tăng tốc AES, CPU, throughput, p95/p99, handshakes/second.
- [ ] Nếu có compliance, kiểm tra crypto module/validation/mode thay vì tên thuật toán.
- [ ] Có danh sách client đại diện và kịch bản negative tests.
- [ ] Dùng SNI/hostname verify trong công cụ kiểm thử, không bỏ TLS verification.
- [ ] Theo dõi handshake failures, negotiated version/suite, session resumption và cert renewal.
- [ ] Xem xét firewall/NAT/IDS/WAF và logging sau điểm TLS termination.
- [ ] Bảo vệ private key, session ticket key và secret khỏi logs/ticket/repo.
- [ ] Có rollout canary, rollback và người chịu trách nhiệm khi đổi TLS profile.
- [ ] Cô lập ngoại lệ legacy với owner và thời hạn loại bỏ rõ ràng.
- [ ] Review định kỳ theo cập nhật thư viện, chứng chỉ, client và chính sách doanh nghiệp.

## 27. Tổng kết

**Lựa chọn cipher suite** là quá trình lựa chọn một **hồ sơ mật mã và vận hành phù hợp**, không phải tìm tên thuật toán dài nhất. Với **TLS 1.3**, cipher suite chủ yếu biểu thị **AEAD + HKDF hash**, trong khi group trao đổi khóa, chữ ký, certificate và PSK/resumption có cơ chế thương lượng riêng. Với **TLS 1.2**, tên suite mang nhiều thành phần hơn; khi còn cần hỗ trợ, nên ưu tiên **ECDHE + AEAD** theo policy, thay vì bật những lựa chọn cũ không cần thiết.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, một kênh truyền an toàn phải được kiểm chứng từ **certificate identity, key exchange, cipher negotiation, endpoint policy, dữ liệu sau termination, firewall/IPS, DNS/VPN/cloud route, logging và thực tế ứng dụng**. Quyết định tốt được chứng minh bằng **client compatibility, positive/negative tests, performance, compliance và khả năng rollback**, đồng thời bảo vệ đúng người dùng, đúng dữ liệu và đúng ranh giới tin cậy của hệ thống.
