# 15.5 Khóa tạm thời, forward secrecy và quan hệ với khóa dài hạn của chứng thư

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Phân biệt **khóa định danh dài hạn gắn với chứng thư X.509**, **khóa riêng tạm thời (ephemeral)** dùng trong thỏa thuận khóa, **shared secret**, **traffic keys** và **session resumption PSK**.
2. Giải thích **forward secrecy (FS)** bảo vệ điều gì, trong mô hình kẻ tấn công nào và với điều kiện nào; không nhầm nó với bảo mật tuyệt đối hay xác thực danh tính.
3. So sánh **TLS 1.2 RSA key transport** với **TLS 1.2 (EC)DHE**, và hiểu tại sao **TLS 1.3 dùng trao đổi khóa tạm thời khi xác thực bằng chứng thư**, trong khi **PSK-only** và **0-RTT** là các trường hợp phải xem xét riêng.
4. Hiểu cách TLS ràng buộc phần trao đổi khóa tạm thời với **Certificate**, **CertificateVerify**, **Finished** và trust/hostname verification; giải thích vì sao **server có RSA certificate vẫn có thể có forward secrecy**.
5. Thực hành Java 17+ bằng **X25519 KeyAgreement** và **Ed25519 Signature** để minh họa shared secret tạm thời và chữ ký của khóa định danh, đồng thời nhận diện giới hạn: đây **không phải giao thức TLS tự xây**.
6. Kiểm tra TLS trong hệ thống Java/JSSE, tránh lựa chọn lỗi thời, quản lý vòng đời khóa và thiết kế phép thử khi khóa định danh bị lộ sau khi phiên kết thúc.

**Điểm then chốt:** **Chứng thư** giúp client xác minh **đối tác nào** đang tham gia (thông qua quyền sở hữu private key và chính sách tin cậy). **Khóa tạm thời** giúp tạo bí mật dùng cho **phiên/kết nối này** mà không cần suy ra từ private key dài hạn của chứng thư. Với một phiên (EC)DHE an toàn, khóa phiên đã được dẫn xuất và secret tạm thời đã được loại bỏ đúng cách, **kẻ đánh cắp private key định danh sau đó không thể chỉ dùng khóa ấy để giải mã bản ghi phiên cũ**.

Ngược lại, nếu hệ thống sử dụng kiểu trao đổi khóa không có forward secrecy, khóa dài hạn bị lộ có thể kéo theo nhiều bản ghi mạng được lưu từ trước. **Chữ ký số và thỏa thuận khóa là hai chức năng khác nhau; không thay thế nhau.**

## 1. Mô hình đe dọa: “hôm nay ghi lại, ngày mai lấy khóa”

Giả sử Alice dùng HTTPS truy cập máy chủ Bob.

- Ở thời điểm **T1**, Eve ghi lại một bản sao đầy đủ những packet TLS trên mạng nhưng chưa có quyền vào server.
- Tại **T2** (sau khi phiên TLS cũ đã kết thúc), Eve đánh cắp **private key dài hạn** của Bob, ví dụ file PKCS12, key backup hoặc quyền dùng một khóa định danh.
- Eve thử giải mã những packet đã ghi ở T1.

Câu hỏi của forward secrecy là:

> Khi Eve lấy được **bí mật dài hạn ở T2**, liệu cô ấy có thể giải mã **traffic của phiên trước ở T1** chỉ từ bản ghi mạng và khóa vừa đánh cắp hay không?

Trong một thiết kế có FS dựa trên **fresh (EC)DHE** và xóa keying material không còn dùng, câu trả lời kỳ vọng là **không** đối với riêng sự lộ **private key định danh dài hạn**. Traffic keys của phiên cũ được dẫn xuất qua một shared secret mà Eve không thể tính chỉ từ public shares đã quan sát và private key định danh lấy được sau này.

Sơ đồ thời gian:

~~~text
T1: Handshake dùng fresh ephemeral (EC)DHE
    Alice <---------------------------------> Bob
      |                                         |
   Ephemeral private a                     Ephemeral private b
      |                                         |
   Shared secret Z ---------------------- Shared secret Z
      |                                         |
   Derive traffic keys -> truyền dữ liệu mã hóa
      |
    Eve ghi lại ClientHello, ServerHello, certificate,
    key shares, handshake và application ciphertext.

T1 kết thúc:
    a, b và các secret không còn cần được xóa/giải phóng
    theo khả năng và chính sách của implementation.

T2: Eve có private key định danh dài hạn của Bob.
    Nếu chỉ có khóa này và bản ghi T1:
       không suy ra được Z hay traffic keys của T1
       trong mô hình (EC)DHE an toàn.
~~~

**FS không nói rằng dữ liệu luôn an toàn nếu Bob bị chiếm quyền từ T1.** Nếu Eve đã chiếm server khi phiên đang chạy, lấy được session secrets, plaintext trong RAM, key logs, hoặc kiểm soát ứng dụng, cô ấy có thể đọc dữ liệu dù handshake có (EC)DHE.

### 1.1 Điều được bảo vệ và không được bảo vệ

| Câu hỏi | Một phiên (EC)DHE có FS trả lời thế nào? |
| --- | --- |
| Sau phiên, private key định danh của server bị đánh cắp. Bản ghi traffic cũ có giải mã được bằng khóa đó không? | **Không chỉ từ khóa định danh**, nếu trao đổi khóa/thuật toán an toàn và ephemeral/session secrets không còn bị lộ |
| Client chưa xác thực certificate, liệu (EC)DHE có tự chống man-in-the-middle không? | **Không**; DH không xác thực có thể bị chèn khóa trung gian |
| Attacker lấy traffic key hoặc plaintext khi phiên đang sống? | **FS không cứu được dữ liệu đã bị lộ trong thời gian đó** |
| Attacker có private key định danh trước một handshake mới? | **Có thể giả mạo server trong tương lai**, trừ khi trust/thu hồi/khóa mới và các kiểm soát khác ngăn chặn |
| Server dùng lại khóa tạm thời rất lâu hoặc log keying material? | Bảo đảm FS có thể bị suy giảm hoặc mất |
| Ciphertext từ TLS cũ được lưu ở proxy/DB dưới dạng plaintext? | FS của kết nối mạng không bảo vệ các bản sao plaintext đó |
| Kết nối dùng PSK-only hoặc dữ liệu TLS 1.3 0-RTT? | **Không tự có bảo đảm FS giống full (EC)DHE**; cần xét PSK lifecycle và mode cụ thể |
| Một công nghệ tính toán mới phá (EC)DH hiện tại trong tương lai? | FS cổ điển **không tự bảo vệ** trước việc giải bài toán DH từ public shares bằng năng lực mới |

### 1.2 Forward secrecy và “Perfect Forward Secrecy” có khác không?

Trong tài liệu cũ và cấu hình hệ thống, thuật ngữ **Perfect Forward Secrecy (PFS)** thường được dùng cho bảo đảm này. Tài liệu tiêu chuẩn mới thường gọi là **forward secrecy**. Chữ “perfect” không nên bị diễn giải thành “không có ngoại lệ”. Bảo đảm mật mã luôn phụ thuộc giả định về thuật toán, cách sinh/xóa secret, mode handshake và mô hình kẻ tấn công.

**Định nghĩa thiết thực:** thỏa hiệp một số khóa dài hạn trong tương lai **không tiết lộ các phiên đã hoàn thành trước đó** dưới mô hình an toàn đã quy định.

## 2. Phân loại khóa trong TLS — đừng gọi tất cả là “SSL key”

| Thành phần | Vòng đời | Ai giữ? | Công việc chính |
| --- | --- | --- | --- |
| **Private key định danh dài hạn** (RSA/ECDSA/EdDSA tùy TLS/provider) | Nhiều phiên, gắn với certificate/identity và rotation | Server hoặc HSM; mTLS có thể cả client | Chứng minh quyền giữ khóa định danh, ký dữ liệu handshake phù hợp giao thức |
| **Public key trong X.509 certificate** | Công khai, có validity và chuỗi chứng nhận | Peer có thể đọc | Giúp xác minh chữ ký và ràng buộc identity sau kiểm tra PKI |
| **Ephemeral private key** của (EC)DHE | Tạo cho một handshake hoặc giới hạn thời gian theo giao thức/policy | Mỗi peer giữ riêng | Cùng public share đối tác tạo **shared secret** |
| **Ephemeral public share** | Truyền trong handshake; không bí mật | Hai peer và người nghe lén có thể thấy | Đầu vào công khai để tính shared secret bằng private share |
| **(EC)DHE shared secret** | Trung gian, ngắn hạn | Hai peer sau thỏa thuận | Đầu vào key schedule/KDF; không phải raw traffic key để dùng trực tiếp |
| **Handshake traffic secrets/keys** | Trong lúc hoàn thành handshake | Hai peer theo chiều gửi/nhận | Bảo vệ các handshake record cần mã hóa |
| **Application traffic secrets/keys** | Trong kết nối, có thể cập nhật | Hai peer theo chiều gửi/nhận | Mã hóa và xác thực application records |
| **PSK/resumption secret/session ticket keys** | Có thể tồn tại qua nhiều kết nối | Client/server/ticket infrastructure | Xác thực hoặc nối lại phiên; rủi ro FS phụ thuộc cách dùng/giữ/xóa |
| **CA signing private key** | Dài hạn ở CA, không nằm trong TLS handshake | CA/KMS/HSM | Ký chứng thư, **không** phải key tạo traffic của phiên |

**Cặp khóa của chứng thư** và **cặp khóa tạm thời** là **hai cặp khác nhau** về chức năng. Cùng được gọi “public/private key” nhưng vòng đời và mục đích rất khác.

### 2.1 Chứng thư không chứa private key

Một chứng thư X.509 chứa public key cùng subject, issuer, validity, SAN, KU/EKU, signature và các extension. **Private key không nằm trong certificate**. Private key có thể được cất trong PKCS12, HSM, OS keystore hoặc KMS. Khi nói “private key của chứng thư”, đó là cách gọi khóa riêng **tương ứng public key được chứng thư ràng buộc**, không phải một trường bí mật bên trong chứng thư.

### 2.2 Server certificate có thể là RSA, handshake vẫn có ECDHE

Điều này thường bị nhầm. Trong TLS 1.2 cipher suite **TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256**:

- **ECDHE**: phương pháp thỏa thuận khóa tạm thời.
- **RSA**: phương pháp xác thực/chữ ký bằng khóa định danh RSA của server.
- **AES_128_GCM**: cơ chế bảo vệ application records.
- **SHA256**: thành phần PRF/hash theo đặc tả của cipher suite.

Chữ **RSA trong tên ECDHE_RSA** không có nghĩa TLS đã mã hóa premaster secret bằng public key RSA của certificate. RSA được dùng cho **chữ ký xác thực**, còn shared secret đến từ **ECDHE**.

Tương tự, **TLS_ECDHE_ECDSA_...** dùng ECDHE để trao đổi khóa và ECDSA để xác thực. Một certificate có key type RSA hoặc ECDSA không tự quyết định FS; phải xem **handshake/key exchange đã đàm phán thực sự**.

## 3. Cơ chế (EC)DHE tạm thời tạo shared secret thế nào?

**Diffie-Hellman (DH)** cho phép hai phía tính được cùng một shared secret bằng private value của mình và public value của đối tác, mà không gửi shared secret trực tiếp qua mạng. “E” trong DHE/ECDHE là **ephemeral**, nghĩa là các giá trị riêng cho trao đổi khóa được tạo mới và có vòng đời ngắn.

Sơ đồ khái niệm:

~~~text
Client Alice                                     Server Bob

Tạo ephemeral private a                         Tạo ephemeral private b
Tạo public share A                              Tạo public share B
       |                                               |
       +---------------- A -------------------------->+
       +<--------------- B ---------------------------+
       |                                               |
Z = DH(a, B)                                     Z = DH(b, A)
       |                                               |
       +--------------- cùng Z ------------------------+
                             |
                 KDF/HKDF + handshake context
                             |
                 Traffic secrets, keys, IVs
                             |
             Bảo vệ dữ liệu qua AEAD record layer
~~~

**Không truyền a, b hoặc Z** trong handshake. Public shares A, B có thể bị ghi lại nhưng không đủ để tính Z theo giả định khó của (EC)DH cổ điển.

Với **ECDHE**, phép toán diễn ra trên elliptic curve. Ví dụ nhóm hiện đại có thể là **X25519** hoặc **secp256r1** khi hai phía và provider hỗ trợ. Với finite-field DHE, dùng các nhóm DH đã được tiêu chuẩn hóa và đủ mạnh; **không tự sinh tham số DH yếu hoặc chọn nhóm không được tin cậy**.

### 3.1 Tại sao phải gắn chữ “ephemeral”?

Nếu dùng một private DH value cố định qua nhiều phiên, rò rỉ value đó có thể ảnh hưởng nhiều session và làm tăng tác động của compromise. Với fresh ephemeral keypair cho từng handshake và xóa đúng lúc, một private share đã kết thúc không còn sẵn để attacker thu thập ở T2.

**Không nên hiểu “ephemeral” chỉ là đặt tên biến tempKey**: phải thực sự dùng key material được sinh an toàn theo policy, không tái sử dụng không cần thiết, không ghi vào log/key dump, không persist trái ý muốn và giải phóng khi đã kết thúc.

Các chi tiết cụ thể như khả năng pre-generate key shares, pool trong implementation, session resumption, KDF và thời điểm xóa phụ thuộc giao thức/runtime. Không tự viết một bộ thỏa thuận khóa qua socket rồi gọi nó là TLS chỉ vì có DH.

### 3.2 Shared secret không phải traffic key trực tiếp

Một **KeyAgreement.generateSecret()** có thể trả mảng byte shared secret. Trong TLS 1.3, secret này được đưa vào **key schedule sử dụng HKDF** và handshake transcript để dẫn xuất nhiều secret/khóa theo ngữ cảnh:

~~~text
(EC)DHE shared secret (+ PSK nếu handshake có PSK)
                         |
                   TLS 1.3 key schedule
              HKDF-Extract / HKDF-Expand-Label
                         |
      +------------------+------------------+
      |                                     |
Handshake traffic secrets           Application traffic secrets
      |                                     |
  handshake keys                      traffic keys + IVs
                                      theo chiều gửi/nhận
~~~

**Không dùng raw DH shared secret làm AES key ngay** hoặc tự tạo key/IV bằng cách cắt byte tùy ý. Key schedule xử lý phân tách miền, handshake context, hướng gửi/nhận, cập nhật và các bảo đảm khác; implementation TLS phải lo việc đó theo chuẩn.

### 3.3 Diffie-Hellman không xác thực thì gặp MITM

Nếu Alice chỉ chấp nhận bất kỳ public share B nào nhận từ mạng, Eve có thể thay nó bằng public share của Eve, thực hiện một trao đổi khóa riêng với Alice và một trao đổi khóa khác với Bob. Hai phía có khóa, nhưng thực ra **mỗi phía trao đổi với Eve**.

~~~text
Alice                 Eve (MITM)                 Bob
  |  public share A       |                       |
  +---------------------> |                       |
  |<------ public share E1|                       |
  |                       | --- public share E2 ->|
  |                       |<--- public share B ---|
  |                       |                       |
Shared secret Alice-Eve        Shared secret Eve-Bob
~~~

**Certificate + handshake authentication** là phần chống tấn công này: client phải kiểm tra chain/trust, hostname và bằng chứng server giữ private key định danh; chữ ký xác thực phải ràng buộc với **handshake transcript gồm phần trao đổi khóa**, không chỉ một public share tùy ý.

## 4. TLS 1.2: RSA key transport khác gì ECDHE_RSA?

### 4.1 TLS 1.2 với static RSA key exchange — không có FS

Trong kiểu **TLS_RSA_WITH_AES_...** trước đây, client tạo **premaster secret**, sau đó mã hóa nó bằng **public key RSA dài hạn trong server certificate** và gửi tới server. Server dùng private key RSA dài hạn để giải mã premaster secret và cùng client dẫn xuất session keys.

~~~text
TLS 1.2 static RSA key transport:

Client:
   Tạo premaster_secret
   RSA_encrypt(server_certificate_public_key, premaster_secret)
                      |
                 network packet
                      |
Server:
   RSA_decrypt(long_term_server_private_key, encrypted_premaster)
   -> premaster_secret -> traffic keys
~~~

Nếu Eve ghi lại encrypted premaster secret và bản ghi application traffic tại T1, sau đó đánh cắp RSA private key dài hạn tại T2, Eve **có thể giải mã premaster secret đã ghi và tính lại keying material phiên cũ** (trong điều kiện có đủ bản ghi và không có bảo vệ khác). Vì vậy cơ chế này **không có forward secrecy**.

Đó là vấn đề cấu trúc, không phải vì RSA “luôn kém an toàn”. RSA còn có thể đóng vai trò **chữ ký định danh** trong handshake ECDHE_RSA có FS.

**Lưu ý trạng thái tiêu chuẩn:** RFC 10015 (2026) đã **deprecated** cơ chế RSA key exchange và một số cơ chế lỗi thời trong (D)TLS 1.2. TLS 1.3 không có static RSA key transport. Tài liệu Java cũ vẫn có thể liệt kê một số cipher suite legacy vì lý do compatibility, nhưng việc nhận ra tên suite cũ không có nghĩa nên bật nó trong cấu hình hiện đại.

### 4.2 TLS 1.2 với ECDHE_RSA — có thể có FS

Trong **TLS_ECDHE_RSA_...**:

1. Client và server trao đổi ephemeral ECDHE shares.
2. Server chứng minh quyền giữ private key định danh RSA bằng chữ ký trên tham số handshake theo giao thức TLS 1.2 (điển hình **ServerKeyExchange**).
3. Client xác thực chuỗi chứng thư/hostname và chữ ký.
4. Cả hai dẫn xuất premaster/shared secret qua ECDHE, không cần giải mã ciphertext của premaster bằng khóa RSA dài hạn.
5. Khi ephemeral secrets biến mất và các giả định an toàn thỏa mãn, lấy RSA identity private key **sau phiên** không đủ để giải mã traffic cũ.

~~~text
TLS 1.2 ECDHE_RSA:

RSA certificate/private key dài hạn:
    xác thực/chữ ký thông điệp ECDHE trong handshake

Client ephemeral a, server ephemeral b:
    ECDHE(a, B) == ECDHE(b, A) -> premaster/master/traffic keys

Lộ RSA private key sau phiên:
    có thể giả mạo identity về sau,
    nhưng không tự cung cấp ephemeral shared secret đã dùng.
~~~

### 4.3 Bảng phân biệt TLS 1.2

| Cipher suite / cơ chế | Key exchange | Vai trò certificate/key dài hạn | FS trước việc lộ certificate private key sau phiên? |
| --- | --- | --- | --- |
| **TLS_RSA_WITH_AES_128_GCM_SHA256** | RSA key transport | RSA private key giải mã premaster secret | **Không** |
| **TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256** | ECDHE tạm thời | RSA ký/xác thực handshake | **Có, với điều kiện của ECDHE và vận hành đúng** |
| **TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256** | ECDHE tạm thời | ECDSA ký/xác thực handshake | **Có, với điều kiện tương ứng** |
| **DHE_RSA** (biến thể phù hợp) | Finite-field DHE tạm thời | RSA xác thực | **Có**, nếu dùng nhóm mạnh, ephemeral đúng |
| **DH/ECDH static** | Khóa DH dài hạn/tĩnh | Có thể liên quan identity/certificate | Không tự cung cấp FS như trao đổi ephemeral |

Tên suite quan trọng trong **TLS 1.2** vì nó chứa cơ chế key exchange/auth. Đừng áp dụng cùng cách đọc tên suite sang TLS 1.3.

## 5. TLS 1.3: trao đổi khóa tạm thời và xác thực theo chứng thư

Trong **TLS 1.3 full handshake dựa trên chứng thư**, trao đổi khóa và xác thực identity được thiết kế **tách chức năng rõ ràng**:

- **ClientHello / ServerHello, key_share:** trao đổi giá trị công khai của (EC)DHE.
- **Certificate:** server công bố chuỗi chứng thư xác thực identity.
- **CertificateVerify:** server chứng minh quyền giữ private key định danh bằng **chữ ký số ràng buộc với handshake transcript và ngữ cảnh TLS**.
- **Finished:** MAC xác nhận handshake transcript và quyền sở hữu handshake secret thích hợp; phát hiện sửa đổi handshake theo thiết kế.
- **HKDF key schedule:** dẫn xuất các secret/traffic keys từ (EC)DHE secret và ngữ cảnh handshake, tách theo giai đoạn/hướng.

Sơ đồ giản lược:

~~~text
Client                                             Server
  |                                                  |
  | ClientHello + supported_groups + key_share A    |
  +------------------------------------------------->|
  |                                                  |
  |       ServerHello + selected key_share B         |
  |<-------------------------------------------------+
  |                                                  |
  |      [Hai phía đã có Z = (EC)DHE(a,B)/(b,A)]     |
  |                                                  |
  |            EncryptedExtensions                   |
  |            Certificate (server identity)         |
  |            CertificateVerify (signature)        |
  |            Finished (handshake MAC)              |
  |<-------------------------------------------------+
  |                                                  |
  |     Validate certificate chain + hostname       |
  |     Verify CertificateVerify + Finished          |
  |                                                  |
  | Finished                                        |
  +------------------------------------------------->|
  |                                                  |
  |<======== encrypted application data ============>|
~~~

Đây là **sơ đồ mô tả**, không phải bản sao toàn bộ message-level TLS 1.3. Tùy handshake, có thể có CertificateRequest, client Certificate/CertificateVerify khi mTLS, HelloRetryRequest, resumption/PSK và các extension khác.

**Điều quan trọng:** Trong full certificate handshake, **private key của chứng thư dùng để xác thực**, không dùng làm bí mật tĩnh để giải mã shared secret (EC)DHE. Certificate không “chứa khóa phiên”, cũng không “gửi khóa phiên được mã hóa” theo cách RSA key transport TLS 1.2.

### 5.1 CertificateVerify ràng buộc điều gì?

Trong TLS 1.3, signature của CertificateVerify được tính theo định dạng có **context string** và **hash của handshake transcript** theo chuẩn, bằng thuật toán chữ ký đã thỏa thuận. Nó **không chỉ là ký chuỗi "hello"** hoặc ký mỗi key share đơn lẻ.

Việc ràng buộc transcript giúp client phát hiện kẻ giữa đường tráo các thành phần handshake, nếu signature và PKI validation được thực hiện đúng. Chữ ký xác thực rằng peer giữ private key định danh phù hợp với certificate đã được chấp nhận, còn (EC)DHE tạo secret tạm thời.

**Chữ ký không tự xác minh SAN/hostname, trust chain, thời hạn, EKU và policy.** Những kiểm tra này là trách nhiệm của certificate/path/endpoint identity validation trong TLS stack.

### 5.2 Finished là bước gì?

**Finished** xác nhận hai bên đã đi tới keying material phù hợp và ràng buộc **nội dung handshake** bằng MAC có khóa. Nếu handshake bị sửa mà không có secret đúng, Finished không xác minh thành công.

Không nên rút gọn “TLS an toàn vì có CertificateVerify”. An toàn handshake đến từ **nhiều phép kiểm tra liên kết**: version/cipher suite selection, key shares, transcript signatures, Finished, certificate validation và tính toàn vẹn record layer.

### 5.3 Certificate RSA không đồng nghĩa RSA key transport

Trong TLS 1.3, server có thể dùng RSA certificate để **ký handshake** với signature algorithm phù hợp; điều đó **không phục hồi static RSA key transport**. Một TLS 1.3 cipher suite như:

~~~text
TLS_AES_128_GCM_SHA256
~~~

nêu **AEAD cipher và hash** của bộ mã, **không mã hóa tên key exchange hoặc phương thức chữ ký** trong chính tên suite. Nhìn SSLSession.getCipherSuite() chỉ ra chuỗi trên không đủ để biết group X25519/secp256r1 hay chứng thư RSA/ECDSA mà peer đã dùng.

Với TLS 1.3, cần xem **protocol version, kiểu handshake (full/PSK), key_share/PSK mode, certificate/signature và JSSE handshake diagnostics** nếu muốn xác nhận chi tiết FS.

### 5.4 TLS 1.3 có luôn forward secrecy không?

Không được trả lời một từ “luôn” mà bỏ qua **PSK-only và 0-RTT**.

Theo **RFC 9846 (tháng 7/2026)**, tiêu chuẩn TLS 1.3 hiện hành thay thế RFC 8446, giữ các nguyên tắc quan trọng:

- Khi **public-key handshake dùng fresh (EC)DHE**, thiết kế cung cấp FS theo mô hình mật mã, nếu secret tạm thời/traffic secret được quản lý đúng.
- TLS 1.3 hỗ trợ **PSK-only (psk_ke)**; mode này **không mặc nhiên cung cấp FS trước việc lộ PSK được giữ lại**, vì không có fresh DH share đóng góp vào shared secret.
- TLS 1.3 hỗ trợ **PSK + (EC)DHE (psk_dhe_ke)**; fresh DH giúp FS cho traffic 1-RTT được dẫn xuất theo mode này.
- **0-RTT early data** dựa trên PSK và **không có bảo đảm forward secrecy đầy đủ như 1-RTT DHE**; đồng thời có vấn đề **replay giữa các kết nối**.
- Với một số cách quản lý PSK và session ticket **một lần rồi xóa mọi bản sao**, phạm vi compromise có thể hẹp hơn; đó là **thuộc tính vận hành phụ thuộc thời điểm xóa PSK**, không phải lời hứa “PSK-only luôn bằng DHE”.

Nguồn cập nhật: [RFC 9846 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc9846.html), đặc biệt §2.2–2.3 và Appendix F.

## 6. Resumption, PSK, 0-RTT và những ngoại lệ dễ bỏ sót

### 6.1 PSK là gì?

**Pre-Shared Key (PSK)** là bí mật mà hai phía đã có trước handshake (do cấp ngoài hoặc được dẫn xuất từ một kết nối trước). Trong TLS 1.3, session resumption có thể dùng resumption PSK và ticket để thiết lập kết nối mới nhanh hơn.

**PSK không phải private key X.509.** Một server có thể sử dụng certificate trong full handshake ban đầu, nhưng một resumption handshake theo PSK có thể không gửi lại certificate tương tự. Phải hiểu TLS state/session và chính sách trust của ứng dụng.

### 6.2 So sánh psk_ke và psk_dhe_ke

~~~text
TLS 1.3 psk_ke:
    PSK ----------------> key schedule -> traffic keys
    (Không có fresh key_share đóng góp)
    => Nếu PSK được giữ và lộ sau này, không có bảo đảm FS
       tương tự trao đổi fresh (EC)DHE.

TLS 1.3 psk_dhe_ke:
    PSK ------------------+
                          +--> key schedule -> traffic keys
    Fresh (EC)DHE Z ------+
    => FS của traffic 1-RTT khi bảo vệ/xóa ephemeral đúng,
       dưới các giả định của giao thức.
~~~

**Không được tự suy luận rằng tất cả các session HTTPS dùng PSK đều mất FS**: cần kiểm tra mode, thời điểm PSK bị lộ và lifecycle. Ngược lại, nhìn thấy “TLS 1.3” cũng không tự chứng minh handshake chọn fresh DHE trong mọi trường hợp.

### 6.3 0-RTT early data

Khi client có PSK từ lần kết nối trước, TLS 1.3 có thể cho phép gửi một số application data trong **first flight** của handshake mới. Điều này giảm độ trễ nhưng đánh đổi thuộc tính bảo mật:

- **Không có bảo đảm FS đầy đủ cho early data**; khóa early data được dẫn xuất từ PSK trước khi nhận fresh ServerHello key share.
- **Có nguy cơ replay** giữa nhiều kết nối; attacker có thể thử gửi lại early data đã ghi.
- Các thao tác có side effect, như **chuyển tiền, mua hàng, tạo đơn, thay đổi mật khẩu**, không nên mặc định cho phép trong 0-RTT; cần profile ứng dụng rõ ràng và biện pháp chống replay/idempotency phù hợp.
- **1-RTT application data sau handshake** có thể nhận tính bảo vệ khác khi dùng PSK+(EC)DHE; không nên gộp tất cả traffic TLS 1.3 thành một câu “forward secret” duy nhất.

RFC 9846 yêu cầu ứng dụng không bật 0-RTT nếu không có chủ đích, và không gửi early data không an toàn khi bị replay. Đối với Java/JSSE, hỗ trợ thực tế cho 0-RTT phụ thuộc bản JDK/provider/API; không giả định JSSE Java 17 phổ biến luôn bật 0-RTT.

### 6.4 Session ticket encryption key và vòng đời PSK

Một server có thể phát hành session ticket để resumption. Nếu ticket được mã hóa/xác thực bằng một **server ticket protection key** tồn tại lâu, hoặc resumption PSK được lưu trong cache/DB quá lâu, compromise hạ tầng ticket có thể ảnh hưởng các kết nối nối lại.

Kiểm soát cần có:

- Thời hạn session ticket/resumption PSK thích hợp.
- Rotation và hạn chế quyền truy cập ticket keys.
- Xóa key/PSK không còn cần; không log session secrets.
- Quy tắc single-use hoặc anti-replay nếu ứng dụng cho phép early data.
- Phân biệt full handshake, resumption psk_ke, resumption psk_dhe_ke.
- Không thiết kế “forward secrecy” chỉ dựa trên private key certificate mà quên nơi lưu PSK/session tickets.

## 7. Tấn công và giới hạn: hiểu đúng lời hứa của FS

### 7.1 Lộ private key chứng thư sau khi phiên cũ kết thúc

**Điều có thể xảy ra:**

- TLS 1.2 RSA key transport: attacker có thể giải mã premaster secret đã bị ghi trong handshake; rủi ro giải mã traffic cũ.
- TLS 1.2 ECDHE và TLS 1.3 full handshake (EC)DHE: khóa định danh không đủ để tính shared secret cũ; traffic cũ có thể được bảo vệ, miễn secret tạm thời không bị lộ.
- Trong các handshake mới, attacker đang giữ identity private key **có thể giả mạo server**, vì signature/authentication bị compromise. FS **không tự ngăn** việc giả mạo tương lai.

**Việc cần làm khi mất private key định danh:** thu hồi/rotation certificate và khóa, khóa quyền truy cập, điều tra sự cố, cập nhật trust/deployment và phạm vi ảnh hưởng. Bản ghi cũ có FS không phải lý do bỏ qua incident response.

### 7.2 Attacker có traffic secrets hoặc endpoint memory

FS **không** có khả năng xóa ảnh hưởng của dữ liệu từng được attacker đọc. Nếu attacker thu thập:

- Plaintext ở reverse proxy, application logs, traces, heap dump.
- Ephemeral private key trong lúc phiên đang hoạt động.
- (EC)DHE shared secret/handshake traffic secret.
- Application traffic keys hoặc key log export (ví dụ key log files dùng cho packet analysis).
- Một session ticket/PSK vẫn có giá trị dưới mode resumption phù hợp.

thì một số phiên hoặc dữ liệu có thể bị giải mã/giả mạo. Bảo vệ endpoint, memory dump, debug settings và secret storage vẫn quan trọng **ngay cả khi dùng TLS 1.3**.

### 7.3 KeyUpdate không phải phép trao đổi DH mới

TLS 1.3 có cơ chế **KeyUpdate** để dẫn xuất generation traffic keys mới từ secret hiện có. Điều này hữu ích cho giới hạn sử dụng khóa và bảo vệ một số thế hệ cũ nếu key cũ đã được xóa.

Nhưng **KeyUpdate không tự chạy lại (EC)DHE**. Nếu attacker đã nắm **traffic secret hiện tại**, việc chỉ dẫn xuất thế hệ mới từ secret đó **không tự tạo post-compromise security cho tương lai**. Đừng nhầm FS trước compromise với khả năng “tự hồi phục” sau khi attacker kiểm soát session secret.

Theo phân tích an toàn của RFC 9846, để giảm tác hại của một số loại compromise cho kết nối mới cần **trao đổi khóa bất đối xứng mới**, không chỉ đổi tên key.

### 7.4 Forward secrecy không phải post-quantum security

Một attacker có thể ghi lại public DH shares và ciphertext hôm nay. Nếu sau này có năng lực giải bài toán DH/ECDH hiện tại từ public shares (ví dụ năng lực lượng tử đủ mạnh theo mô hình Shor), việc private key định danh đã bị xóa **không còn là vấn đề quyết định**. Vì vậy **FS cổ điển** không đồng nghĩa an toàn trước “harvest now, decrypt later” trong mô hình lượng tử.

Giảm rủi ro HNDL trong tương lai cần đánh giá các giao thức/hybrid post-quantum key establishment đã được chuẩn hóa và triển khai phù hợp, không tự nối X25519 với một thuật toán bất kỳ trong code ứng dụng. **X25519 trong ví dụ Java của bài này là mô hình cổ điển**, không đại diện một bảo đảm post-quantum.

### 7.5 Ứng dụng lưu lại plaintext vẫn có thể làm mất ý nghĩa bảo vệ

Một TLS terminator/reverse proxy có thể giải mã traffic, sau đó chuyển plaintext vào service nội bộ hoặc lưu xuống log/database. FS chỉ có ý nghĩa cho **traffic TLS được mã hóa theo phiên**, không tự bảo vệ plaintext đã tồn tại ngoài kết nối đó.

Kiểm tra cả đường đi của dữ liệu: client → CDN/LB/proxy → app → DB/queue/log, và từng ranh giới trust. Một hệ thống nói “TLS có PFS” nhưng lưu access tokens/raw payload vào log công khai vẫn có vấn đề bảo mật nghiêm trọng.

## 8. Java 17+: mô phỏng hai vai trò, không tự xây TLS

Java có JCA/JCE cho phép học primitives bên dưới:

- **KeyPairGenerator.getInstance("X25519")** sinh một cặp khóa X25519 tạm thời.
- **KeyAgreement.getInstance("X25519")** cho hai phía tạo shared secret trùng nhau.
- **KeyPairGenerator.getInstance("Ed25519")** sinh một cặp khóa định danh mẫu.
- **Signature.getInstance("Ed25519")** ký/xác minh một transcript minh họa.

Trong ví dụ, server giữ một **khóa định danh dài hạn Ed25519**, client biết trước **public key định danh đã tin**. Hai phía sinh fresh X25519 cho từng handshake và tạo secret riêng. Server ký một transcript có chứa **cả hai public ephemeral shares**, client xác thực chữ ký bằng public key định danh đã biết.

**Ranh giới cực kỳ quan trọng:** Đây là **mô hình giáo dục**, **không phải TLS 1.3 implementation**. Trong TLS thật, CertificateVerify có định dạng ngữ cảnh và transcript do RFC quy định; cần certificate/path/hostname validation, Finished MAC, HKDF key schedule, cipher suite negotiation, AEAD record framing, replay/downgrade protections, error handling và nhiều kiểm soát khác. **Không gửi hai public shares + chữ ký dưới định dạng demo này lên mạng sản xuất**.

### 8.1 Chương trình Java 17+ hoàn chỉnh

Tạo file **EphemeralIdentityDemo.java** (UTF-8):

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.Arrays;
import javax.crypto.KeyAgreement;

public class EphemeralIdentityDemo {
    // Transcript mô phỏng có domain separation và độ dài từng trường.
    // Không phải Transcript/CertificateVerify format của TLS 1.3.
    private static byte[] transcript(PublicKey client, PublicKey server) {
        byte[] ctx = "educational-ephemeral-v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] c = client.getEncoded();
        byte[] s = server.getEncoded();

        return ByteBuffer.allocate(12 + ctx.length + c.length + s.length)
                .putInt(ctx.length).put(ctx)
                .putInt(c.length).put(c)
                .putInt(s.length).put(s)
                .array();
    }

    private static byte[] agree(KeyPair own, PublicKey peer)
            throws GeneralSecurityException {
        KeyAgreement a = KeyAgreement.getInstance("X25519");
        a.init(own.getPrivate());
        a.doPhase(peer, true);
        return a.generateSecret();
    }

    private static byte[] sign(PrivateKey key, byte[] message)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initSign(key);
        s.update(message);
        return s.sign();
    }

    private static boolean verify(PublicKey key, byte[] message, byte[] tag)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initVerify(key);
        s.update(message);
        return s.verify(tag);
    }

    public static void main(String[] args) throws Exception {
        // Mô phỏng identity dài hạn của server, ví dụ key của certificate.
        KeyPairGenerator idGen = KeyPairGenerator.getInstance("Ed25519");
        KeyPair longTermServerIdentity = idGen.generateKeyPair();

        // Mỗi handshake có hai cặp ephemeral X25519 riêng.
        KeyPairGenerator ephemeralGen =
                KeyPairGenerator.getInstance("X25519");
        KeyPair c = ephemeralGen.generateKeyPair();
        KeyPair s = ephemeralGen.generateKeyPair();

        byte[] secretC = agree(c, s.getPublic());
        byte[] secretS = agree(s, c.getPublic());

        // Server ký transcript dùng khóa định danh dài hạn.
        byte[] handshake = transcript(c.getPublic(), s.getPublic());
        byte[] signed = sign(
                longTermServerIdentity.getPrivate(), handshake);

        System.out.println("X25519 secrets agree: "
                + MessageDigest.isEqual(secretC, secretS));
        System.out.println("Shared secret bytes: " + secretC.length);
        System.out.println("Identity signature valid: "
                + verify(longTermServerIdentity.getPublic(),
                         handshake, signed));

        // Một attacker thay public share của server trong transcript.
        KeyPair fakeServerShare = ephemeralGen.generateKeyPair();
        byte[] tampered = transcript(
                c.getPublic(), fakeServerShare.getPublic());
        System.out.println("Modified share rejected: "
                + !verify(longTermServerIdentity.getPublic(),
                          tampered, signed));

        // Handshake độc lập khác dùng fresh ephemeral keypairs.
        KeyPair nextClient = ephemeralGen.generateKeyPair();
        KeyPair nextServer = ephemeralGen.generateKeyPair();
        byte[] nextSecret = agree(
                nextClient, nextServer.getPublic());
        System.out.println("Fresh exchange differs: "
                + !MessageDigest.isEqual(secretC, nextSecret));

        // Giảm vòng đời các byte[] secret do chương trình trực tiếp giữ.
        Arrays.fill(secretC, (byte) 0);
        Arrays.fill(secretS, (byte) 0);
        Arrays.fill(nextSecret, (byte) 0);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 EphemeralIdentityDemo.java
java EphemeralIdentityDemo
~~~

Stdout dự kiến với provider Java 17+ hỗ trợ **X25519** và **Ed25519**:

~~~text
X25519 secrets agree: true
Shared secret bytes: 32
Identity signature valid: true
Modified share rejected: true
Fresh exchange differs: true
~~~

**Giải thích từng dòng:**

1. **X25519 secrets agree: true** — client và server cùng tính một secret từ cặp private/public tạm thời tương ứng.
2. **Shared secret bytes: 32** — X25519 trả 32 byte shared secret.
3. **Identity signature valid: true** — transcript gốc được ký bằng private key Ed25519; public key **được giả định đã được client tin** xác minh đúng chữ ký.
4. **Modified share rejected: true** — khi server ephemeral share bị tráo trong transcript nhưng chữ ký cũ không đổi, việc xác minh **signature** thất bại.
5. **Fresh exchange differs: true** — trao đổi X25519 độc lập dùng fresh keypairs cho secret khác với xác suất áp đảo.

**Không in raw private keys/shared secrets** trong stdout; đây là dữ liệu mật mã nhạy cảm. Raw public keys có thể công khai, nhưng không được nhầm chúng với authenticated identity nếu chưa xác minh chữ ký/certificate.

**Giới hạn của Java demo:** Không có PKI, certificate chain, SAN/hostname, TLS HKDF, Finished, record layer hoặc mạng. Client tin thẳng longTermServerIdentity.getPublic() trong cùng tiến trình — điều này **chỉ minh họa chữ ký khi public key đã được tin**. Ở HTTPS thật, public key đến từ certificate phải được xác minh qua truststore và hostname policy. Mã demo cũng không phải bằng chứng hình thức rằng một giao thức mới do người học tự xây có FS hay chống MITM hoàn chỉnh.

Các array bị Arrays.fill() chỉ là buffer mà code trực tiếp sở hữu; **không bảo đảm mọi secret trong provider/JVM/native memory được xóa**. Demo vẫn tạo KeyPair chứa private key objects, Java runtime quyết định quản lý vòng đời object; đừng sao chép kỹ thuật xóa này rồi tuyên bố có bảo đảm xóa secret tuyệt đối.

### 8.2 Điều demo chứng minh và không chứng minh

| Điều quan sát | Kết luận hợp lệ |
| --- | --- |
| X25519 hai phía cho cùng 32 byte | Primitive KeyAgreement hoạt động đúng trong phép thử |
| Ed25519 xác minh transcript | Có thể ràng buộc public shares với một public key định danh đã tin |
| Đổi một public share làm chữ ký không hợp lệ | Signature bảo vệ nội dung đã được ký khỏi sửa đổi không có private signing key |
| Fresh pair cho secret mới | Dùng keypairs mới tạo secret phiên mới, với xác suất trùng cực nhỏ |
| Ghi lại transcript/public shares và về sau lộ signing key | Không có đường tính lại X25519 secret cũ **chỉ từ signing key** theo giả định X25519, nếu ephemeral private không bị lộ |
| Demo chạy mà không có TLS | **Không** đồng nghĩa tạo một kênh truyền có xác thực/an toàn production |

### 8.3 Vì sao không dùng chữ ký số thay cho ephemeral key?

Một chữ ký Ed25519 hoặc RSA có nhiệm vụ **chứng minh người ký sở hữu private signing key** tương ứng với public key được tin. Signature không trực tiếp tạo shared secret bí mật mà chỉ client/server biết. KeyAgreement lại tạo shared secret nhưng **không tự chứng minh danh tính server**.

Hai phép toán bổ trợ nhau:

~~~text
Signature của identity key:
   "Public share/handshake này thuộc phiên được server hợp lệ xác thực"
   (nếu PKI/public key trust và giao thức đều đúng)

Ephemeral KeyAgreement:
   "Hai bên cùng biết shared secret riêng phiên"
   (nhưng một mình nó chưa ngăn MITM)

TLS handshake:
   kết hợp authentication + authenticated key exchange +
   key schedule + Finished + AEAD traffic protection
~~~

Không thay KeyAgreement bằng RSA ký một random string, không gửi raw shared secret qua mạng, cũng không cố “cải tiến” TLS bằng cách tự nối vài primitive.

## 9. Quan sát TLS thật qua Java JSSE

Trong ứng dụng Java 17, **JSSE** và các API **SSLSocket, SSLEngine, SSLContext, SSLParameters, SSLSession, HttpsURLConnection/HttpClient** triển khai hoặc sử dụng TLS theo provider được cấu hình.

**Điều đầu tiên cần biết:** nhiều thuộc tính trong JVM là **khả năng được hỗ trợ** hoặc **khả năng được bật**, không phải handshake thực tế đã đàm phán. Ví dụ danh sách supported suites có thể chứa tên TLS 1.2 legacy; điều đó không chứng minh server chấp nhận chúng hay bất kỳ connection nào đã dùng chúng.

### 9.1 Xem TLS protocol và suite được hỗ trợ

Đoạn Java sau **độc lập** và không kết nối mạng; nó chỉ liệt kê **khả năng của JSSE provider đang chạy**.

Tệp **JsseCapabilitiesDemo.java**:

~~~java
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;

public class JsseCapabilitiesDemo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);
        SSLEngine engine = context.createSSLEngine();

        System.out.println("TLSv1.3 supported: "
                + Arrays.asList(engine.getSupportedProtocols())
                        .contains("TLSv1.3"));
        System.out.println("TLSv1.3 enabled: "
                + Arrays.asList(engine.getEnabledProtocols())
                        .contains("TLSv1.3"));

        SSLParameters params = context.getSupportedSSLParameters();
        System.out.println("Supported suites count: "
                + params.getCipherSuites().length);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 JsseCapabilitiesDemo.java
java JsseCapabilitiesDemo
~~~

**Output phụ thuộc JDK/provider/security properties thực tế**, nên không đưa một con số cụ thể cho Supported suites count. Trên một JDK 17 JSSE chuẩn hỗ trợ TLS 1.3, hai dòng đầu thường là true; cấu hình bị quản trị giới hạn có thể khác. Chương trình này **không thực hiện handshake**, vì vậy không có chứng minh runtime vừa dùng ECDHE, PKIX hay forward secrecy.

### 9.2 Với một handshake thực, kiểm tra những gì?

Khi có quyền quan sát một endpoint được cấp phép, hãy ghi nhận:

1. **Protocol version đã đàm phán**, không chỉ supported protocols. Ví dụ từ **SSLSession.getProtocol()** sau handshake.
2. **Cipher suite đã đàm phán**, ví dụ từ **SSLSession.getCipherSuite()**.
3. Với **TLS 1.2**, key exchange thường được thể hiện trong suite (ECDHE_RSA, DHE_RSA hay static RSA).
4. Với **TLS 1.3**, cipher suite **không chứa KEX/auth mode**; phải xem thêm handshake **key_share**, nhóm được chọn, PSK mode và tình trạng full vs resumption.
5. Đảm bảo **certificate chain/trust path, hostname, EKU/KU, thời gian và revocation policy** được kiểm tra theo ứng dụng.
6. Xác nhận **TLS 1.3 0-RTT** có được dùng không, nếu có thì chính sách anti-replay và idempotency là gì.
7. Nếu phía client dùng mTLS, kiểm tra client certificate/auth riêng, không gộp với xác thực server.
8. Kiểm tra **termination point**: TLS kết thúc ở reverse proxy hay trực tiếp tại app; có mTLS/TLS ở chặng nội bộ tiếp theo không.

**Đừng suy luận forward secrecy chỉ từ việc chứng thư là ECDSA hoặc RSA**, cũng không chỉ từ việc SSLSession trả TLS_AES_128_GCM_SHA256.

### 9.3 JSSE handshake debugging trong lab

Trong môi trường được phép, Java hỗ trợ logging phục vụ chẩn đoán JSSE, ví dụ system property:

~~~text
javax.net.debug=ssl,handshake
~~~

Nó có thể giúp quan sát version, cipher suites, key_share, handshake messages và certificate validation theo bản JDK. Đây **không phải kết quả xác nhận an toàn tự động**: cần đọc cấu hình và kết quả thật; debug có thể lộ metadata nhạy cảm trong log và gây tăng dung lượng. Không bật dài hạn trên production.

Nếu phải phân tích packet, dùng công cụ/sniffer được cấp phép trong phạm vi kiểm thử. **Không bật xuất TLS session keys** ra file rồi quên xóa: key logs có thể giúp giải mã traffic mà FS lẽ ra bảo vệ trước việc lộ identity key.

### 9.4 Nên cấu hình TLS thế nào trong ứng dụng Java 17?

Về nguyên tắc:

- **Ưu tiên TLS 1.3** trong những môi trường peer/provider hỗ trợ; khi cần TLS 1.2 để tương thích, chỉ cho phép **cipher suites có (EC)DHE và AEAD** theo policy hiện hành.
- Không bật **static RSA key transport** vì legacy compatibility mà không đánh giá rủi ro; RFC 10015 đã deprecated phương pháp này.
- Không bật SSLv3/TLS 1.0/1.1 hoặc các cipher yếu để “thử cho chạy được”.
- Đảm bảo TrustManager/KeyManager và chứng thư định danh có quyền/chain/hostname đúng.
- Không dùng **trust-all X509TrustManager** hay **HostnameVerifier luôn true**.
- Dùng provider/JDK được cập nhật bảo mật; không viết TLS 1.3 từ KeyAgreement + Signature của bài tập.
- Không hardcode một danh sách duy nhất các named groups hoặc signature algorithms cho mọi máy khi chưa đánh giá tính tương thích/chính sách. Cập nhật theo provider và crypto policy có thẩm quyền.
- Kiểm thử **1-RTT full handshake, resumption, mTLS nếu có**, không chỉ nhìn một phiên HTTPS thành công.

**Lưu ý về cipher suite naming:** Tên TLS 1.3 như TLS_AES_256_GCM_SHA384 chỉ diễn đạt AEAD/hash; **X25519, secp256r1, RSA-PSS hoặc ECDSA không xuất hiện trong tên**. Chúng là những phép chọn của handshake khác với TLS 1.2.

## 10. Vận hành để bảo đảm FS có ý nghĩa thực tế

### 10.1 Bảo vệ private key dài hạn của certificate

FS giảm hậu quả **giải mã hồi tố** sau khi lộ identity private key, nhưng không làm khóa đó kém quan trọng. Attacker có private key phù hợp certificate và có khả năng can thiệp mạng có thể **giả mạo peer trong các handshake tương lai** cho đến khi chính sách trust/thu hồi/key rotation chặn.

Do đó cần:

- Bảo vệ key bằng HSM, keystore/secret manager theo yêu cầu.
- Giới hạn quyền ký, quyền xuất khóa, phạm vi dùng và audit.
- Cấp lại certificate/key đúng chu kỳ và khi có sự cố.
- Kiểm tra certificate revocation/truststore và hostname chính xác.
- Không chia sẻ một signing key cho quá nhiều endpoint/tenant nếu không có chính sách rõ.
- Không gửi private key qua ticket/chat/log hoặc đưa vào source repository.

### 10.2 Không giữ ephemeral secret “cho tiện debug”

Khóa tạm thời, shared secret và session keys cần vòng đời ngắn nhất theo implementation và protocol. Nếu doanh nghiệp log raw session secrets, lưu memory dump mở rộng, bật TLS key logging hoặc backup session state quá dài, **bảo đảm FS trước việc chỉ mất identity key không còn diễn đạt đầy đủ rủi ro thực tế**.

Java app không nên tự lấy shared secret rồi ghi vào log “để so sánh” hoặc giữ private ephemeral key trong cache toàn cục. Dựa vào JSSE implementation chuẩn thay vì tự quản lý raw ephemeral keys trong ứng dụng.

### 10.3 Session resumption và PSK cần chính sách riêng

Làm rõ:

- Mode full handshake hay PSK resumption?
- PSK-only hay PSK+(EC)DHE?
- Có 0-RTT hay không?
- Ticket keys được lưu ở đâu, ai có quyền, thời hạn/rotation?
- Cách xóa ticket/PSK cũ và xử lý failover nhiều instance?
- Chống replay/idempotency cho 0-RTT ở tầng ứng dụng thế nào?

Bật TLS 1.3 nhưng quản trị session resumption không cẩn thận có thể tạo các đường tấn công khác với những bảo đảm của fresh (EC)DHE full handshake.

### 10.4 Không thay thế bảo mật ở các lớp khác

FS không sửa:

- SQL injection, XSS, command injection trong ứng dụng.
- Lộ JWT/API key qua log hoặc browser storage.
- Mã hóa dữ liệu lưu trữ thiếu chính sách khóa/rotation.
- Phân quyền sai giữa tenant.
- Endpoint chủ động trả plaintext cho attacker được cấp quyền nhầm.
- CA hoặc truststore bị cài root giả dẫn đến xác thực sai.
- Backup/monitoring chứa session secrets hoặc raw dữ liệu.

Vì vậy đánh giá TLS là **một** lớp của hệ thống an toàn, không phải “bật PFS là xong”.

## 11. Các hiểu nhầm phổ biến

1. **“Server certificate là RSA nên chắc chắn không có FS.”** Sai: RSA có thể chỉ dùng xác thực trong ECDHE_RSA/TLS 1.3, còn traffic key đến từ DHE.
2. **“Đã có ECDHE thì không cần chứng thư.”** Sai: DH không xác thực bị MITM; cần certificate/PSK trust và handshake authentication.
3. **“Certificate chứa ephemeral session key.”** Sai: cert chứa public key định danh, ephemeral key tạo trong handshake.
4. **“Private key định danh dùng để giải mã mọi session TLS.”** Sai với ECDHE/TLS 1.3 full certificate handshake; có thể đúng với static RSA key transport TLS 1.2 theo thiết kế legacy.
5. **“TLS 1.3 cipher suite name cho biết server dùng RSA hay ECDSA và nhóm X25519.”** Sai: TLS 1.3 suite không mang KEX/auth trong tên.
6. **“TLS 1.3 có FS tuyệt đối trong mọi kết nối, kể cả 0-RTT.”** Sai: phải phân biệt full (EC)DHE, PSK-only và early data.
7. **“0-RTT an toàn như các request thông thường.”** Sai: có replay risk và thiếu bảo đảm FS đầy đủ; phải chọn các thao tác replay-safe.
8. **“Ephemeral key phải được gửi cho đối tác để hai bên tính secret.”** Sai: chỉ **public share** được truyền; private share phải giữ bí mật.
9. **“DH shared secret dùng thẳng làm AES key.”** Sai: TLS key schedule dẫn xuất các key/IV/context riêng.
10. **“Nhìn thấy cùng shared secret trong hai phía là đã có kênh TLS an toàn.”** Sai: demo chưa có PKI, Finished, AEAD, replay, downgrade protections.
11. **“Lộ identity key sau phiên cũ thì FS còn bảo vệ mọi phiên trong tương lai.”** Sai: attacker có thể mạo danh khi bắt tay mới.
12. **“Lộ session traffic key không sao vì có FS.”** Sai: traffic/session keys bị lộ có thể mở dữ liệu được bảo vệ bởi chúng.
13. **“Dùng KeyUpdate chắc chắn hồi phục nếu key hiện tại đã bị chiếm.”** Sai: KeyUpdate không tự rerun ECDHE; hậu quả phụ thuộc loại key bị lộ.
14. **“Mỗi kết nối có secret khác nhau nghĩa là chắc chắn FS.”** Chưa đủ: nếu secret được dẫn xuất từ một bí mật dài hạn mà sau đó bị lộ, có thể tái lập các phiên.
15. **“Forward secrecy đồng nghĩa chống máy tính lượng tử tương lai.”** Không: ECDH cổ điển có thể bị phá khi giả định độ khó không còn đúng.
16. **“Chỉ test TLSv1.3 supported là chứng minh endpoint dùng TLS 1.3.”** Sai: phải quan sát **protocol negotiated** trên phiên thực.
17. **“TLS cipher suite ECDHE_RSA nghĩa là RSA encrypt premaster secret.”** Sai: RSA chứng thực chữ ký, ECDHE tạo secret.
18. **“Thời hạn cert ngắn tự tạo forward secrecy.”** Không: đổi certificate thường xuyên giới hạn hậu quả compromise, nhưng không thay thế ephemeral key exchange.
19. **“Nếu client không xác thực hostname, ECDHE vẫn chặn MITM.”** Sai: kẻ giữa đường có thể tự thực hiện key exchange với mỗi phía.
20. **“Có FS rồi có thể lưu TLS session secrets/heap dump thoải mái.”** Sai: rò secrets trực tiếp có thể làm mất bảo mật của phiên được ghi lại.

## 12. Tình huống phân tích

### Tình huống A — Máy chủ dùng RSA certificate, cần kiểm tra có FS không

Nhóm vận hành xem certificate type là RSA rồi kết luận không có FS. Cách đánh giá đúng:

- Xem **protocol phiên thật**.
- Nếu TLS 1.2, xác định suite có **ECDHE_RSA** hay **TLS_RSA_...**; hai loại có tính chất rất khác.
- Nếu TLS 1.3, xem full handshake/key share hoặc PSK mode; không suy ra từ certificate type và tên TLS_AES_... suite.
- Kiểm tra JDK/provider, security properties, cipher suites đang enabled thực tế.

**Kết luận:** Loại khóa chứng thư nói về **xác thực**, không tự quyết định key establishment và forward secrecy.

### Tình huống B — Private key của server bị lấy cắp sau sáu tháng

Attacker ghi packet TLS từ sáu tháng trước, nay có server RSA identity key.

- Phiên TLS 1.2 static RSA: có thể bị giải mã hồi tố.
- Phiên TLS 1.2 ECDHE/TLS 1.3 full DHE: không giải mã được chỉ từ RSA identity key, nếu ephemeral/session secrets cũ không bị lộ.
- Handshake mới: attacker có thể mạo danh server nếu không bị thu hồi/chặn.

**Hành động:** đánh giá exposure theo từng protocol/suite/mode và thời điểm lộ; luân chuyển key, chứng thư và xử lý incident, không khẳng định “vì TLS nên không vấn đề”.

### Tình huống C — Dịch vụ bật resumption và 0-RTT

Để giảm latency, đội hệ thống chấp nhận 0-RTT request gọi API tạo giao dịch. Attacker gửi lại một request early data đã ghi.

**Vấn đề:** 0-RTT có replay risk; FS của early data không tương đương 1-RTT fresh DHE. Kết quả có thể là thao tác bị lặp.

**Khắc phục:** không gửi thao tác có side effect trong 0-RTT nếu không có profile chống replay và idempotency thích hợp; hạn chế early data, theo dõi session tickets và thực thi anti-replay ở tầng hạ tầng/nghiệp vụ.

### Tình huống D — Lộ session key log trong quá trình debug

Một developer bật key logging để Wireshark giải mã HTTPS lab và vô tình tải key log lên artifact store dùng chung. Attacker có file logs và packet capture.

**Vấn đề:** FS trước việc lộ **long-term identity key** không bảo vệ khi **session traffic secrets đã bị xuất trực tiếp**. Cần coi file key log là secret, hạn chế truy cập, thu hồi/điều tra và không lưu qua pipeline production.

### Tình huống E — Endpoint bị chiếm khi một phiên đang sống

Attacker đọc bộ nhớ app hoặc TLS runtime, lấy session keys và plaintext. Sau đó tổ chức xoay certificate.

**Vấn đề:** rotation certificate không xóa được dữ liệu phiên đã bị thu thập, và FS không có nghĩa bảo vệ trước **đối thủ đang kiểm soát endpoint**. Cần incident response ở tầng host/app và xác định dữ liệu đã lộ.

### Tình huống F — TLS 1.3 KeyUpdate bị hiểu là “DH mới”

Một nhóm muốn phục hồi sau khi attacker lấy application traffic secret, nên chỉ yêu cầu KeyUpdate.

**Vấn đề:** KeyUpdate dẫn xuất từ traffic secret cũ, không trao đổi ephemeral DH mới; attacker có bí mật gốc có thể theo dõi các thế hệ khóa phù hợp. Cần thiết lập handshake mới với key establishment và xác thực được kiểm soát để phục hồi theo mô hình sự cố.

## 13. Test matrix và câu hỏi tự kiểm tra

### 13.1 Test matrix cho Java/TLS deployment

| Test | Cần quan sát | Kết luận |
| --- | --- | --- |
| Full TLS 1.3 certificate handshake | key_share + certificate authentication + Finished | Có cơ sở FS theo fresh (EC)DHE; vẫn cần endpoint/secret lifecycle |
| TLS 1.2 ECDHE_RSA | negotiated suite thực tế chứa ECDHE_RSA | RSA cert dùng xác thực, ECDHE tạo secret |
| TLS 1.2 TLS_RSA | negotiated suite thực tế static RSA key exchange | Không có FS, cần loại bỏ theo chính sách mới |
| TLS 1.3 PSK-only | mode psk_ke không có fresh key_share | Không mặc định có FS khi PSK còn tồn tại |
| TLS 1.3 PSK+(EC)DHE | psk_dhe_ke và fresh key share | FS của 1-RTT dưới điều kiện DHE/secret management |
| TLS 1.3 0-RTT | early_data, resumption PSK, anti-replay | Không mặc định FS hoặc replay safety |
| Sai certificate/hostname | handshake bị từ chối | Xác thực identity không bị bypass |
| Key logging/debug đang bật trên production | kiểm tra config, files, ACL, retention | Không để lộ session secrets |
| Lộ long-term identity key | kiểm kê protocol/handshake modes & lịch sử | Phân biệt traffic cũ với nguy cơ giả mạo tương lai |
| Chỉ gọi getSupportedProtocols() | có TLSv1.3 trong danh sách | **Không** đủ để xác nhận negotiated session |
| Thay certificate RSA bằng ECDSA | chỉ thay signature key algorithm | Không kết luận FS nếu key establishment chưa kiểm tra |
| TLS terminates ở reverse proxy | chặng mạng sau proxy và log/data storage | FS của TLS client-to-proxy không tự bảo vệ hop khác |

### 13.2 Câu hỏi và đáp án

**Câu 1.** Chứng thư X.509 chứa khóa tạm thời của mỗi phiên không?

**Trả lời:** Không. Chứng thư chứa public key định danh và thông tin xác thực. Ephemeral keypair được tạo cho key exchange của handshake.

**Câu 2.** RSA certificate có khiến TLS 1.3 không có forward secrecy không?

**Trả lời:** Không. RSA certificate có thể dùng xác thực bằng chữ ký; full TLS 1.3 certificate handshake có fresh (EC)DHE tạo shared secret.

**Câu 3.** TLS 1.2 TLS_RSA khác TLS_ECDHE_RSA ở điểm nào?

**Trả lời:** TLS_RSA mã hóa premaster secret bằng static RSA public key, làm mất FS nếu private key bị lộ về sau. TLS_ECDHE_RSA dùng ephemeral ECDHE để tạo premaster secret, RSA chỉ xác thực handshake.

**Câu 4.** Vì sao (EC)DHE một mình chưa chống MITM?

**Trả lời:** Vì ai cũng có thể thay public share; cần xác thực đúng peer và ràng buộc transcript bằng chữ ký/Finished theo giao thức.

**Câu 5.** Khi private key định danh của server bị lộ sau phiên cũ có FS, attacker có giải mã được packet cũ chỉ từ private key ấy không?

**Trả lời:** Không theo mô hình an toàn chuẩn, nếu fresh ephemeral key material và traffic secrets cũ không lộ, thuật toán an toàn. Nhưng attacker có thể giả mạo server trong handshake tương lai.

**Câu 6.** Session ticket/PSK ảnh hưởng FS thế nào?

**Trả lời:** PSK-only không tự bảo đảm FS trước việc PSK còn lưu và bị lộ; PSK+(EC)DHE thêm fresh DH có thể cung cấp FS cho 1-RTT. Thời gian sống/xóa PSK là yếu tố vận hành quan trọng.

**Câu 7.** 0-RTT early data có cùng FS và anti-replay như TLS 1.3 1-RTT DHE không?

**Trả lời:** Không. Early data phụ thuộc PSK và có rủi ro replay giữa kết nối; cần giới hạn những thao tác được phép và phòng ngừa tương ứng.

**Câu 8.** Vì sao CipherSuite TLS_AES_128_GCM_SHA256 không cho biết X25519 hay RSA?

**Trả lời:** TLS 1.3 tách lựa chọn key exchange và signature khỏi tên cipher suite; cần xem handshake negotiated key_share/PSK/certificate.

**Câu 9.** Demo X25519+Ed25519 của bài có thay thế JSSE không?

**Trả lời:** Không. Demo thiếu PKIX, TLS transcript format/Finished/HKDF/record layer/host validation và nhiều cơ chế an toàn bắt buộc.

**Câu 10.** KeyUpdate có đủ để phục hồi nếu attacker biết current application traffic secret không?

**Trả lời:** Không. KeyUpdate không rerun DH, chỉ dẫn xuất thế hệ mới từ secret hiện có.

**Câu 11.** Tại sao KeyAgreement.generateSecret() không được dùng thẳng làm AES key theo cảm tính?

**Trả lời:** TLS dùng key schedule HKDF để phân tách theo context, hướng traffic và giai đoạn, tránh tái sử dụng trực tiếp shared secret.

**Câu 12.** Có FS rồi thì cần bảo vệ log/proxy/database không?

**Trả lời:** Có. FS bảo vệ traffic cũ trước một loại compromise cụ thể, không tự bảo vệ các bản sao plaintext, session key logs và dữ liệu đã được endpoint giải mã.

## 14. Tài liệu tham khảo

- [RFC 9846 (July 2026) — TLS 1.3](https://www.rfc-editor.org/rfc/rfc9846.html): đặc tả TLS 1.3 hiện hành, **thay thế RFC 8446 (2018)**; §2.2–2.3 về PSK/0-RTT, §4 về handshake, §7 về key schedule, Appendix F về forward secrecy và key compromise.
- [RFC 8446 (2018) — TLS 1.3, lịch sử](https://www.rfc-editor.org/rfc/rfc8446.html): nguồn học tập cũ, hiện được RFC 9846 thay thế.
- [RFC 5246 — TLS 1.2, lịch sử](https://www.rfc-editor.org/rfc/rfc5246.html): cơ chế RSA key exchange và (EC)DHE trong TLS 1.2 (đã bị RFC 9846 thay thế ở vị trí chuẩn hiện hành).
- [RFC 10015 (2026) — Deprecating Obsolete Key Exchange Methods in TLS 1.2](https://www.rfc-editor.org/rfc/rfc10015.html): loại bỏ/khuyến cáo ngừng sử dụng RSA key transport và các phương pháp lỗi thời trong TLS 1.2.
- [Oracle Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): SSLContext, SSLSocket/SSLEngine, TLS 1.3, handshake, cipher suites, provider và debug.
- [Oracle Java SE 17 — KeyAgreement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html): API tạo shared secret cho X25519.
- [Oracle Java SE 17 — Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): API tạo/kiểm tra chữ ký định danh.
- [Oracle Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên thuật toán X25519/Ed25519/TLS và cipher suites.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525.html): hướng dẫn xác minh danh tính dịch vụ khi dùng TLS.

## Kết luận

**Khóa định danh dài hạn và khóa tạm thời giải quyết hai bài toán khác nhau.** Private key tương ứng certificate dùng **xác thực** đối tác và ràng buộc handshake; ephemeral (EC)DHE tạo một shared secret **không phụ thuộc vào khả năng giải mã premaster secret bằng static identity private key**. Với fresh (EC)DHE, xử lý KDF đúng và xóa secret tạm thời, việc đánh cắp private key định danh **sau phiên** không đủ để giải mã traffic cũ đã ghi lại: đó là ý nghĩa thực tế của forward secrecy.

Khi đánh giá một kết nối TLS, phải xét **protocol phiên thực, key exchange/resumption mode, 0-RTT, certificate validation và key lifecycle**, không kết luận từ loại certificate hoặc tên cipher suite một mình. **TLS 1.2 static RSA key transport không có FS; TLS 1.2 (EC)DHE và full TLS 1.3 certificate handshake dùng fresh (EC)DHE có FS trong mô hình thích hợp; TLS 1.3 PSK-only và 0-RTT là các ngoại lệ phải quản lý có chủ đích.** Trong Java 17+, hãy để **JSSE** thực hiện TLS, dùng JCA X25519/Ed25519 chỉ cho việc học primitive hoặc giao thức chuyên biệt đã được đánh giá chặt chẽ.
