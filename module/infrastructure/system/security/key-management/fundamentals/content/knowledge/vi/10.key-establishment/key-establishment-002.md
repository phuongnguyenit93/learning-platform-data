# Key agreement trong key establishment: thiết lập bí mật chung và khóa phiên an toàn

## 1. Vì sao một hệ thống cần key agreement?

Giả sử hai dịch vụ Java, **OrderService** và **PaymentService**, lần đầu thiết lập kết nối qua mạng không đáng tin cậy. Chúng muốn dùng **AES-GCM** để bảo vệ dữ liệu giao dịch nhưng chưa chia sẻ một khóa AES nào. Chuyển khóa AES ở dạng rõ qua mạng không an toàn: người nghe lén có thể sao chép khóa, sau đó giải mã hoặc giả mạo dữ liệu.

**Key establishment** là quá trình thiết lập vật liệu khóa bí mật mà những bên được phép sẽ sử dụng. Trong đó, **key agreement (thỏa thuận khóa)** là một nhóm cơ chế để các bên tạo ra **bí mật chung** từ những đóng góp mật mã của mình, thay vì một bên chỉ đơn giản gửi khóa sử dụng thực tế ở dạng rõ.

Một ví dụ phổ biến là **Elliptic-Curve Diffie–Hellman (ECDH)**. Mỗi bên giữ một private key, trao đổi public key và tính một shared secret. Sau đó hệ thống dùng **Key Derivation Function (KDF)** để dẫn xuất khóa có mục đích cụ thể, chẳng hạn khóa mã hóa cho từng chiều truyền.

~~~text
                 Kênh mạng công khai
Client                                        Server
------                                        ------
privateC (bí mật)                            privateS (bí mật)
publicC  ------------------------------->    nhận publicC
nhận publicS <------------------------------- publicS

ECDH(privateC, publicS)                      ECDH(privateS, publicC)
         |                                             |
         +-------------- shared secret ----------------+
                               |
            KDF + transcript + nhãn vai trò/mục đích
                               |
              khóa bảo vệ lưu lượng cho từng hướng
~~~

**Điều đặc biệt quan trọng:** nếu không xác thực public key và handshake, kẻ tấn công có thể chen vào giữa rồi thực hiện **hai key agreement riêng biệt**. Khi đó công thức toán học vẫn đúng, nhưng các bên không chia sẻ bí mật với người mà họ tưởng đang giao tiếp.

Bởi vậy, trong key establishment an toàn, **key agreement là một thành phần**, không phải toàn bộ giao thức. Cần kết hợp:

- Tạo và kiểm tra key material đúng thuật toán.
- Xác thực danh tính hoặc nguồn gốc public key.
- Ràng buộc **transcript**, thuật toán và vai trò vào key schedule.
- Dẫn xuất các khóa riêng cho từng mục đích.
- Kiểm tra bên kia sở hữu khóa khi giao thức yêu cầu (**key confirmation**).
- Sử dụng **AEAD**, nonce/IV đúng quy tắc, có chống replay phù hợp.
- Quản lý toàn bộ vòng đời khóa, phân quyền và kiểm toán.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Định vị **key agreement** trong toàn bộ quy trình **key establishment**.
2. Phân biệt key agreement, key transport, KEM, key exchange, key derivation và key confirmation.
3. Giải thích DH/ECDH/X25519, shared secret, vai trò ephemeral/static key và giới hạn toán học của một bước DH.
4. Thiết kế khái niệm **authenticated key establishment** với danh tính, transcript binding và domain separation.
5. Phân tích **MITM, UKS, downgrade, replay, lộ private key, key compromise và forward secrecy**.
6. Đọc ví dụ Java 17 dùng **X25519 + HKDF-SHA256** để tạo các khóa traffic độc lập; biết vì sao demo không phải giao thức production.
7. Kết hợp key establishment với **TLS 1.3, KMS/HSM, DEK/KEK, envelope encryption, IAM và audit**.

## 2. Bản đồ khái niệm của key establishment

Các thuật ngữ dưới đây có liên hệ nhưng không đồng nghĩa.

| Khái niệm | Giải thích | Sự khác biệt cần nhớ |
| --- | --- | --- |
| **Key establishment** | Quy trình để những bên được phép có vật liệu khóa sử dụng chung hoặc thích hợp với từng vai trò | Bao gồm key agreement và những cơ chế thiết lập khóa khác |
| **Key agreement** | Các bên đóng góp vật liệu khóa để tính bí mật chung theo một giao thức | Ví dụ Diffie–Hellman; cần xử lý xác thực và KDF |
| **Key transport** | Một bên tạo/chọn khóa rồi chuyển cho bên khác bằng phương tiện bảo vệ thích hợp | Không giống hai bên cùng tính một secret từ đóng góp riêng |
| **KEM** | Cơ chế encapsulation/decapsulation tạo shared secret và encapsulated ciphertext | Giao diện khác DH; có thể là thành phần của key establishment hiện đại |
| **Key exchange** | Thuật ngữ rộng, đôi khi được dùng thay key establishment hoặc cho một pha trao đổi | Phải đọc đặc tả cụ thể, không coi mọi exchange là ECDH |
| **Key derivation** | Biến key material thành một hay nhiều khóa có nhãn/mục đích | Thường xảy ra sau DH/KEM, không tự xác thực đối tác |
| **Key confirmation** | Chứng minh cho đối tác rằng bên gửi có khả năng sử dụng khóa được dẫn xuất theo giao thức | Không tự chứng minh danh tính nếu ban đầu trao đổi với kẻ giả mạo |
| **Key distribution** | Phân phối/đăng ký khóa hay thông tin khóa đến chủ thể phù hợp | Công khai public key không có nghĩa public key đã được xác thực |

### 2.1. Agreement khác transport ở đâu?

Với **key transport**, một bên có thể sinh DEK ngẫu nhiên rồi mã hóa/bọc DEK cho người nhận. Bên nhận có private key hoặc KEK phù hợp để khôi phục DEK.

~~~text
Key transport (khái niệm):
Sender sinh DEK  ── bảo vệ dưới khóa người nhận ──> Receiver lấy DEK
~~~

Với **Diffie–Hellman key agreement**, mỗi bên giữ private key riêng và dùng public key đối tác để tính ra cùng một shared secret.

~~~text
Key agreement (khái niệm):
Client private + Server public → shared secret
Server private + Client public → shared secret
~~~

Cả hai phương án đều có thể hợp lệ, nhưng lựa chọn phải xét **ai đóng góp bí mật, ai được quyền tạo/nhận key, yêu cầu xác thực, giới hạn thuật toán và khả năng forward secrecy**.

### 2.2. KEM khác ECDH thế nào?

Một **Key Encapsulation Mechanism (KEM)** thường có ba thao tác theo giao diện:

~~~text
KeyGen()                  -> (publicKey, privateKey)
Encaps(publicKey)         -> (encapsulatedCiphertext, sharedSecret)
Decaps(privateKey, ciphertext) -> sharedSecret
~~~

Trong KEM, phía encapsulate dùng public key của bên nhận, còn bên nhận decapsulate bằng private key. Đây không phải đúng giao diện **KeyAgreement(privateSelf, publicPeer)** của DH/ECDH, mặc dù cả hai đều có thể cung cấp shared secret cho KDF.

Một số giao thức hiện đại có thể kết hợp nhiều nguồn secret (ví dụ ECDHE và một KEM) trong thiết kế **hybrid** theo quy chuẩn. Không tự nối các kết quả shared secret lại rồi coi như đã có giao thức an toàn; cách tổ hợp, xác thực, key schedule và chính sách phải được định nghĩa và phân tích.

### 2.3. Key agreement không giống signing

**Ed25519** là thuật toán chữ ký số; **X25519** dùng cho thỏa thuận khóa. Private signing key có thể được dùng để **ký lên handshake** nhằm chứng minh danh tính, nhưng không nên tự biến một cặp khóa Ed25519 thành khóa X25519 bằng cách đổi tên API hoặc chuyển byte tùy tiện.

**Public key có thể được công bố**, nhưng không phải public key bất kỳ cũng được tin. Một public key hợp lệ về mặt toán học chỉ là thông tin đầu vào mật mã; ứng dụng phải xác định nó thuộc đúng **peer và key usage**.

## 3. Nguyên lý Diffie–Hellman: bí mật chung mà không gửi trực tiếp

Để hiểu trực giác, xét Diffie–Hellman trên nhóm số học đơn giản. Đây là **ví dụ học tập**, không phải tham số an toàn cho hệ thống thật.

Hai bên biết công khai số nguyên tố \(p\) và phần tử cơ sở \(g\). Alice chọn số bí mật \(a\), Bob chọn \(b\):

\[
A = g^a \bmod p,\quad B = g^b \bmod p
\]

Alice gửi \(A\), Bob gửi \(B\). Sau đó:

\[
S_A = B^a \bmod p = g^{ab} \bmod p
\]

\[
S_B = A^b \bmod p = g^{ab} \bmod p
\]

Vì \(S_A = S_B\), hai bên thu được giá trị giống nhau. Một người chỉ quan sát \(p,g,A,B\) không dễ tính secret khi nhóm và tham số đủ mạnh, theo giả định mật mã áp dụng.

**Không dùng những phép toán này để tự triển khai DH trong production.** Các chuẩn còn quy định nhóm, tham số, public-key validation, thứ tự byte, xử lý lỗi, cách dẫn xuất khóa, xác thực và giới hạn sử dụng. Dùng nhóm nhỏ hoặc tham số tự chế có thể khiến secret bị khôi phục dễ dàng.

### 3.1. Private key và public key đóng vai trò khác nhau

- **Private key:** phải được giữ bí mật, có chất lượng ngẫu nhiên đúng thuật toán, chỉ được dùng trong phạm vi được cấp quyền.
- **Public key:** có thể trao đổi công khai nhưng cần được **xác thực ràng buộc danh tính** nếu muốn biết đang thỏa thuận với ai.
- **Shared secret:** là kết quả mật mã do bên tham gia tính cục bộ. Không được in ra log hoặc gửi qua mạng ở dạng rõ.
- **Derived/session keys:** được tạo từ shared secret qua KDF/key schedule rồi dùng cho mã hóa hoặc xác thực.

Việc shared secret có dạng byte dài 32 không đồng nghĩa có thể lấy trực tiếp làm AES-256 key trong mọi giao thức. Cần tuân thủ **đặc tả KDF và ngữ cảnh**.

### 3.2. DH không cung cấp tính xác thực sẵn có

Kẻ tấn công không nhất thiết phải giải bài toán logarithm rời rạc. Họ có thể thay public key trên đường truyền và tạo shared secret riêng với từng bên. Vì vậy muốn chống MITM, phải bảo vệ **danh tính và transcript**, không chỉ chọn phép toán DH mạnh.

## 4. ECDH, X25519 và lựa chọn thuật toán

### 4.1. ECDH

**Elliptic-Curve Diffie–Hellman (ECDH)** áp dụng nguyên lý agreement trên các nhóm điểm của đường cong elliptic. Trong JCA/JCE, những triển khai ECDH thường cần một **EC private key** và **EC public key** hợp lệ trên cùng nhóm/đường cong.

Một số lựa chọn có thể gặp:

| Cơ chế | Đặc điểm | Yêu cầu triển khai |
| --- | --- | --- |
| **ECDH trên P-256** | Dùng đường cong elliptic chuẩn hóa | Thống nhất curve và kiểm tra public point đúng cách; hỗ trợ tùy Java provider/HSM |
| **X25519** | Thỏa thuận khóa dựa trên Curve25519 theo giao diện X25519 | Sử dụng implementation đã kiểm chứng; xử lý đầu ra all-zero theo quy tắc |
| **FFDHE chuẩn hóa** | Finite-field Diffie–Hellman với nhóm đã chuẩn hóa | Không chấp nhận nhóm quá yếu hoặc tham số tùy ý; kiểm tra giá trị bên nhận |
| **Giao thức dùng KEM** | Có thể tạo secret từ encapsulation/decapsulation | Tuân thủ lược đồ và key schedule của giao thức được chọn |

Không có một bộ kiểm tra public key chung cho tất cả thuật toán. Ví dụ, điều kiện **all-zero shared secret** trong X25519 không thể thay thế mọi quy tắc kiểm tra tham số của ECDH trên các nhóm khác.

### 4.2. X25519 trong Java

Java 17 có thể cung cấp API **KeyPairGenerator** và **KeyAgreement** cho **X25519** khi security provider hỗ trợ. Cặp khóa cần được tạo bởi thư viện phù hợp; không tự dùng số ngẫu nhiên bất kỳ rồi gọi đó là private key của mọi loại đường cong.

Khi nhận public key từ mạng, cần phân tích theo **định dạng đã quy định** (chẳng hạn cấu trúc khóa của protocol), kiểm tra thuật toán/độ dài và mọi điều kiện xử lý input cần thiết. Không được giả định byte encoding của X25519, Ed25519, X.509 SubjectPublicKeyInfo và JWK là giống nhau.

### 4.3. Khóa static và ephemeral

- **Static key pair** được giữ qua nhiều phiên. Nó có thể phục vụ một vai trò lâu dài, nhưng việc lộ private key có thể ảnh hưởng rộng.
- **Ephemeral key pair** được tạo cho một phiên/giai đoạn ngắn, rồi hủy khi không cần nữa.
- **Ephemeral–ephemeral agreement** có thể giúp giao thức có **forward secrecy** nếu được xác thực và quản lý bí mật đúng.
- **Static–ephemeral agreement** không tự chứng minh có hoặc không có forward secrecy; phải phân tích key schedule và mô hình lộ khóa của chính giao thức.

Thực hành tốt thường tách **khóa xác thực danh tính dài hạn** (có thể dùng cho chữ ký) khỏi **khóa ECDH tạm thời**, nhưng cấu trúc thực tế phụ thuộc đặc tả.

## 5. Một quy trình authenticated key establishment đầy đủ

Key agreement là bước toán học nằm giữa quá trình thiết lập ngữ cảnh an toàn và sử dụng khóa.

### 5.1. Các bước tổng quát

1. **Xác định policy và danh tính:** hai bên biết mình cần xác thực peer nào, cho phép giao thức/nhóm nào, có yêu cầu mTLS/PSK/chứng chỉ hay không.
2. **Tạo vật liệu phiên:** mỗi bên sinh ephemeral key pair và các giá trị ngẫu nhiên được giao thức yêu cầu.
3. **Đàm phán thuật toán:** trao đổi phiên bản, nhóm agreement và lựa chọn AEAD theo danh sách đã được phép.
4. **Trao đổi public key:** gửi public ephemeral key và các trường handshake khác theo định dạng chuẩn.
5. **Kiểm tra đầu vào:** xác nhận public key/nhóm hợp lệ theo thuật toán; từ chối kết quả bất thường.
6. **Tính shared secret:** dùng private key của mình và public key đối tác để thực hiện key agreement.
7. **Xác thực handshake:** sử dụng chứng chỉ/chữ ký/PSK hoặc cơ chế chuẩn khác để gắn **peer identity, thuật toán và transcript** vào trao đổi.
8. **Dẫn xuất key schedule:** biến shared secret (và các secret khác nếu giao thức quy định) thành các khóa có purpose/role riêng.
9. **Key confirmation / Finished:** xác nhận theo giao thức rằng phía kia có cùng key schedule và đã nhận đúng handshake.
10. **Bảo vệ lưu lượng:** chỉ xử lý dữ liệu ứng dụng khi điều kiện xác thực/hoàn tất phù hợp đã đạt; dùng AEAD và nonce theo chuẩn.
11. **Giới hạn phiên và hủy:** áp dụng session expiry, traffic key update/rekey, xóa secret tạm thời, audit và xử lý lỗi.

Các bước trên là **mô hình chức năng**, không phải thứ tự gói tin bắt buộc của mọi giao thức. TLS 1.3 có key schedule và thông điệp Finished cụ thể; không nên tự xây một protocol mới bằng cách sao chép danh sách này.

~~~mermaid
sequenceDiagram
    participant C as Java Client
    participant S as Service
    C->>C: Sinh ephemeral (cPriv, cPub)
    S->>S: Sinh ephemeral (sPriv, sPub)
    C->>S: Phiên bản, nhóm, cPub, client random
    S-->>C: Nhóm, sPub, server random, bằng chứng xác thực
    Note over C,S: Kiểm tra chính sách, public key và transcript
    C->>C: Agreement(cPriv, sPub) → shared secret
    S->>S: Agreement(sPriv, cPub) → shared secret
    Note over C,S: Key schedule: KDF(secret, context, transcript)
    C->>C: Client write key + server write key
    S->>S: Client write key + server write key
    C->>S: Bằng chứng key confirmation theo giao thức
    S-->>C: Bằng chứng key confirmation theo giao thức
    Note over C,S: AEAD truyền dữ liệu; IAM kiểm tra quyền nghiệp vụ
~~~

### 5.2. “Cùng một secret” khác “cùng một đối tác hợp lệ”

Hai bên có thể tính đúng cùng shared secret và nhận key confirmation hợp lệ nhưng vẫn chưa xác thực đúng danh tính. Nếu attacker đã thay các public key và dựng hai phiên, key confirmation ở mỗi phiên có thể vẫn thành công.

Một thiết kế an toàn cần trả lời đồng thời:

- **Ai** đang tham gia? Danh tính này được xác thực bằng cách nào?
- **Đang dùng thuật toán nào?** Đã chấp nhận theo chính sách chưa?
- **Transcript nào** đã được các bên nhìn thấy và xác thực?
- **Secret nào** được tạo ra và dùng để dẫn xuất khóa gì?
- **Bên nào** được quyền gửi/nhận thông điệp hoặc truy cập tài nguyên nào?

## 6. Xác thực public key: bài toán MITM và tin cậy

### 6.1. Man-in-the-middle

Không xác thực public key, một kẻ tấn công có thể:

~~~mermaid
flowchart LR
    A["Client Alice"] <-->|"Agreement với Mallory"| M["Mallory"]
    M <-->|"Agreement khác"| B["Server Bob"]
~~~

Alice tưởng đã có shared secret với Bob; Bob tưởng đã có shared secret với Alice. Trên thực tế:

- Alice có một khóa chung với Mallory.
- Bob có một khóa chung khác với Mallory.
- Mallory có thể giải mã, thay dữ liệu, mã hóa lại và chuyển tiếp nếu hệ thống tin hai phiên là một.

Tăng kích thước key hoặc thay ECDH bằng thuật toán mạnh hơn **không tự giải quyết** lỗi xác thực danh tính.

### 6.2. Các cơ chế xác thực phổ biến

| Cơ chế | Định nghĩa niềm tin | Những điều bắt buộc |
| --- | --- | --- |
| **Chứng chỉ X.509 và chữ ký** | Trust anchor/CA và chính sách ràng buộc danh tính | Kiểm tra chain, hostname/identity, thời hạn, key usage, revocation phù hợp |
| **Pinned public verification key** | Public key/fingerprint được đăng ký trước qua kênh đáng tin | Bảo vệ cấu hình, rotation, recovery và chống tráo khóa |
| **Mutual TLS (mTLS)** | Hai phía xác thực chứng chỉ trong handshake TLS | Chính sách certificate mapping, trust, IAM cho service identity |
| **Pre-shared key (PSK)** | Các bên có cùng bí mật đã cấp phát an toàn | Bảo vệ PSK, identity binding, rotation, chống replay theo giao thức |
| **Authenticated key exchange chuẩn** | Giao thức quy định cách xác thực và ràng buộc handshake | Dùng implementation đúng chuẩn, cấu hình thuật toán an toàn |

**Chữ ký số và key agreement giải quyết hai mục tiêu khác nhau.** Một private signing key giúp ký bằng chứng xác thực; ephemeral ECDH dùng để tạo shared secret. Không mặc định cùng một khóa có thể dùng cho cả hai vai trò.

### 6.3. Transcript binding

**Transcript** là biểu diễn có thứ tự của những thông điệp bắt tay mà giao thức cần xác thực/ràng buộc. Ví dụ, nó có thể chứa:

~~~text
protocolVersion
supportedAlgorithms / selectedAlgorithm
clientRandom, serverRandom
clientEphemeralPublicKey, serverEphemeralPublicKey
serverIdentity / clientIdentity / role
authenticationMessages
other handshake fields required by the protocol
~~~

Trong giao thức được thiết kế an toàn, các trường liên quan phải được bao phủ bởi các bằng chứng xác thực hoặc key schedule theo đúng quy tắc. Nếu chỉ ký một public key mà không bảo vệ **đàm phán thuật toán**, attacker có thể gây nhầm lẫn/ngăn chặn một số cơ chế chống downgrade tùy protocol.

Bản transcript cần có **byte encoding xác định**. Sửa thứ tự trường, cắt phần dữ liệu hoặc tự chuẩn hóa khác nhau có thể khiến hai phía tính hash khác nhau và thất bại.

### 6.4. Unknown key-share và identity binding

**Unknown key-share (UKS)** xảy ra khi các bên dùng khóa theo cách mà một bên nhận diện **sai người còn lại**. Hai phía có thể có cùng key material nhưng hiểu khác về danh tính đang chia sẻ khóa.

Do đó, chỉ thấy **key confirmation thành công** vẫn chưa đủ. Giao thức cần ràng buộc đúng **peer identity, role, public key, transcript và mục đích sử dụng** trong cơ chế xác thực/key schedule phù hợp.

### 6.5. Phân biệt xác thực kết nối và phân quyền ứng dụng

Một PaymentService có thể xác thực đúng chứng chỉ của OrderService và thiết lập khóa TLS thành công. Điều đó **không đồng nghĩa** OrderService được đọc dữ liệu của mọi tenant.

Sau khi có kênh bảo mật, ứng dụng vẫn cần:

- Xác thực danh tính người dùng/workload ở tầng phù hợp.
- Kiểm tra principal/role có được gọi thao tác nghiệp vụ hay không.
- Xác minh quyền trên tenant, invoice ID và dữ liệu đang truy cập.
- Ghi audit hành động nhạy cảm mà không tiết lộ session key hoặc plaintext không cần thiết.

## 7. KDF và key schedule: từ shared secret tới các khóa sử dụng

Shared secret là đầu vào; khóa dùng thực tế nên được tạo theo **key schedule** của giao thức.

### 7.1. Vai trò của HKDF

**HKDF (RFC 5869)** là KDF dựa trên HMAC với hai giai đoạn:

~~~text
Extract:
  PRK = HKDF-Extract(salt, IKM)

Expand:
  trafficKey = HKDF-Expand(PRK, info, outputLength)
~~~

Với **HKDF-SHA256**:

~~~text
PRK = HMAC-SHA256(salt, IKM)

T(0) = empty
T(1) = HMAC-SHA256(PRK, T(0) || info || 0x01)
T(2) = HMAC-SHA256(PRK, T(1) || info || 0x02)
...
OKM = first L bytes of T(1) || T(2) || ...
~~~

Trong đó IKM có thể là shared secret ECDH được xử lý theo protocol, info chứa nhãn mục đích/ngữ cảnh, và outputLength là số byte cần tạo. Với SHA-256, giới hạn output HKDF-Expand là **255 × 32 = 8160 byte**.

**Không dùng HKDF thay cho password-based KDF** khi input là mật khẩu dễ đoán. HKDF nhanh, không được thiết kế để chống offline password guessing. Với password cần cân nhắc **Argon2id/scrypt/PBKDF2** theo use case và chính sách.

### 7.2. Domain separation

Nếu dùng cùng một khóa AES-GCM cho cả hai chiều truyền và cả hai phía bắt đầu nonce từ 0, rất dễ dẫn đến **nonce reuse dưới cùng khóa**. Tách khóa theo role và direction là một phần quan trọng của thiết kế:

~~~text
shared secret
   |
   +-- HKDF(... info="app/v1|client-to-server|aead") --> clientWriteKey
   |
   +-- HKDF(... info="app/v1|server-to-client|aead") --> serverWriteKey
   |
   +-- HKDF(... info="app/v1|client-finished")       --> confirmationKey
~~~

Các nhãn trên **chỉ minh họa ý tưởng**, không phải các nhãn của TLS 1.3. Giao thức sản xuất phải định nghĩa chính xác việc tạo info, byte order, độ dài, transcript hash và các bước xác thực.

**Không tạo khóa MAC, encryption key và KEK từ một shared secret bằng cách cắt/ghép tùy tiện**. Nếu giao thức muốn chia một output, quy tắc phải được thiết kế rõ ràng. Dùng **nhãn purpose riêng** là cách giảm nhầm lẫn.

### 7.3. Những giá trị thường bị nhầm

| Giá trị | Vai trò | Cần lưu ý |
| --- | --- | --- |
| **ECDH private key** | Secret riêng dùng trong agreement | Phải bảo vệ và hủy khi hết cryptoperiod |
| **ECDH public key** | Được trao đổi công khai | Cần kiểm tra hợp lệ và xác thực danh tính |
| **Shared secret** | Vật liệu bí mật tính từ agreement | Không gửi rõ hoặc log; xử lý bằng KDF |
| **HKDF salt** | Đầu vào Extract | Thường không bí mật; không thay nguồn entropy |
| **HKDF info** | Nhãn purpose/context | Đảm bảo encoding không nhập nhằng và nhất quán |
| **Transcript hash** | Cam kết các message handshake theo quy tắc | Chỉ có ý nghĩa xác thực khi được gắn vào bằng chứng xác thực/key schedule đúng |
| **Traffic key** | Dùng với AEAD cho một hướng/giai đoạn | Giới hạn sử dụng, cryptoperiod, rekey |
| **AEAD nonce/IV** | Giá trị cho mỗi bản tin mã hóa | Không lặp theo điều kiện thuật toán |
| **Authentication tag** | Kiểm tra toàn vẹn/xác thực bản mã và AAD | Không dùng plaintext trước khi xác thực thành công |

### 7.4. Key confirmation là gì?

Một bên có thể gửi một bản tin **Finished/confirmation** được xác thực bằng khóa dẫn xuất theo giao thức. Phía kia xác minh nó để có bằng chứng đối tác có cùng vật liệu khóa và transcript được bảo vệ như mong đợi.

Tuy nhiên:

- Confirmation không thay thế **peer authentication**.
- Confirmation không tự chống **replay** nếu protocol không có freshness/sequence phù hợp.
- Phải phân tách khóa/nhãn và vai trò gửi–nhận để tránh reflection/role confusion.
- Không dùng một giá trị HMAC trên transcript do tự chọn rồi khẳng định đó là giao thức TLS.

## 8. Ví dụ Java 17: X25519 và HKDF-SHA256

Đây là ví dụ **kỹ thuật học tập** về hai phía tính cùng shared secret và dẫn xuất hai khóa cho hai hướng. Nó không xây dựng giao thức truyền tin production. Cả hai bên chạy **trong cùng một tiến trình**, chưa có chứng chỉ, chữ ký, peer authentication, các bản tin Finished hoặc giao thức chống downgrade.

**Mục tiêu của code:** thấy rõ quan hệ giữa **ephemeral key pair → shared secret → HKDF → traffic keys**. Khi xây dịch vụ mạng thật, nên sử dụng **TLS 1.3/JSSE** hoặc một giao thức được chuẩn hóa, không sao chép đoạn demo thành handshake tự thiết kế.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class KeyEstablishmentDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String HMAC = "HmacSHA256";
    private static final int HASH_LEN = 32;

    private static byte[] agree(PrivateKey own, PublicKey other)
            throws GeneralSecurityException {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(own);
        agreement.doPhase(other, true);

        byte[] secret = agreement.generateSecret();

        // Với X25519, từ chối shared secret toàn zero.
        int accumulator = 0;
        for (byte b : secret) {
            accumulator |= b & 0xff;
        }
        if (accumulator == 0) {
            Arrays.fill(secret, (byte) 0);
            throw new GeneralSecurityException("Invalid shared secret");
        }
        return secret;
    }

    private static byte[] digestTranscript(byte[]... fields)
            throws GeneralSecurityException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        for (byte[] field : fields) {
            // Length-prefix giúp phân biệt các cặp field khác nhau.
            byte[] length = ByteBuffer.allocate(4)
                .putInt(field.length).array();
            digest.update(length);
            digest.update(field);
        }
        return digest.digest();
    }

    private static byte[] extract(byte[] salt, byte[] ikm)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance(HMAC);
        mac.init(new SecretKeySpec(salt, HMAC));
        return mac.doFinal(ikm);
    }

    private static byte[] info(String direction, byte[] transcriptHash) {
        byte[] label = ("key-establishment-demo/v1|" + direction)
            .getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(8 + label.length + transcriptHash.length)
            .putInt(label.length).put(label)
            .putInt(transcriptHash.length).put(transcriptHash)
            .array();
    }

    // RFC 5869 HKDF-Expand cho SHA-256.
    private static byte[] expand(byte[] prk, byte[] context, int length)
            throws GeneralSecurityException {
        if (length < 1 || length > 255 * HASH_LEN) {
            throw new IllegalArgumentException("Invalid HKDF length");
        }

        Mac mac = Mac.getInstance(HMAC);
        mac.init(new SecretKeySpec(prk, HMAC));

        byte[] result = new byte[length];
        byte[] previous = new byte[0];
        int offset = 0;
        try {
            for (int counter = 1; offset < length; counter++) {
                mac.reset();
                mac.update(previous);
                mac.update(context);
                mac.update((byte) counter);
                byte[] next = mac.doFinal();
                Arrays.fill(previous, (byte) 0);
                previous = next;

                int amount = Math.min(next.length, length - offset);
                System.arraycopy(next, 0, result, offset, amount);
                offset += amount;
            }
            return result;
        } finally {
            Arrays.fill(previous, (byte) 0);
        }
    }

    private static byte[] derive(
            byte[] sharedSecret,
            byte[] transcriptHash,
            String purpose) throws GeneralSecurityException {
        byte[] prk = extract(transcriptHash, sharedSecret);
        try {
            return expand(prk, info(purpose, transcriptHash), 32);
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("X25519");
        KeyPair client = generator.generateKeyPair();
        KeyPair server = generator.generateKeyPair();

        byte[] clientRandom = new byte[32];
        byte[] serverRandom = new byte[32];
        RNG.nextBytes(clientRandom);
        RNG.nextBytes(serverRandom);

        // Trong một giao thức thật, transcript và identity phải
        // được xác thực trước khi tin rằng đây là đúng đối tác.
        byte[] transcriptHash = digestTranscript(
            "key-establishment-demo/v1".getBytes(StandardCharsets.UTF_8),
            clientRandom, serverRandom,
            client.getPublic().getEncoded(),
            server.getPublic().getEncoded());

        byte[] clientSecret = null;
        byte[] serverSecret = null;
        byte[] c2sAtClient = null;
        byte[] c2sAtServer = null;
        byte[] s2cAtClient = null;
        byte[] s2cAtServer = null;

        try {
            clientSecret = agree(client.getPrivate(), server.getPublic());
            serverSecret = agree(server.getPrivate(), client.getPublic());

            c2sAtClient = derive(
                clientSecret, transcriptHash, "client-to-server");
            c2sAtServer = derive(
                serverSecret, transcriptHash, "client-to-server");

            s2cAtClient = derive(
                clientSecret, transcriptHash, "server-to-client");
            s2cAtServer = derive(
                serverSecret, transcriptHash, "server-to-client");

            System.out.println("Same shared secret: " +
                MessageDigest.isEqual(clientSecret, serverSecret));
            System.out.println("C->S keys match: " +
                MessageDigest.isEqual(c2sAtClient, c2sAtServer));
            System.out.println("S->C keys match: " +
                MessageDigest.isEqual(s2cAtClient, s2cAtServer));
            System.out.println("Directions separated: " +
                !Arrays.equals(c2sAtClient, s2cAtClient));
            System.out.println("Traffic key length: " +
                c2sAtClient.length);
        } finally {
            if (clientSecret != null)
                Arrays.fill(clientSecret, (byte) 0);
            if (serverSecret != null)
                Arrays.fill(serverSecret, (byte) 0);
            if (c2sAtClient != null)
                Arrays.fill(c2sAtClient, (byte) 0);
            if (c2sAtServer != null)
                Arrays.fill(c2sAtServer, (byte) 0);
            if (s2cAtClient != null)
                Arrays.fill(s2cAtClient, (byte) 0);
            if (s2cAtServer != null)
                Arrays.fill(s2cAtServer, (byte) 0);
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
Same shared secret: true
C->S keys match: true
S->C keys match: true
Directions separated: true
Traffic key length: 32
~~~

### 8.1. Code minh họa điều gì?

1. **Hai cặp X25519 được tạo độc lập**, private key không được truyền đi.
2. Kết quả KeyAgreement từ hai hướng trùng nhau khi sử dụng đúng public/private key đối ứng.
3. **Transcript hash** trong ví dụ chứa phiên bản, client/server random và public keys theo thứ tự cố định; nó được dùng như salt/context cho HKDF.
4. **HKDF-Extract** nhận shared secret; **HKDF-Expand** dùng nhãn mục đích để tạo **hai khóa 32 byte khác nhau** cho hai hướng.
5. Output 32 byte có thể là vật liệu phù hợp cho AES-256 trong một thiết kế chuẩn, nhưng ví dụ **chưa mã hóa dữ liệu** và chưa quản lý nonce AEAD.
6. Việc xóa mảng bằng Arrays.fill là **best effort**. JVM, JCA provider, object key và memory dump có thể vẫn chứa bản sao vật liệu bí mật.
7. Kết quả **true** chỉ chứng minh tính nhất quán mật mã của các thao tác trong demo, **không chứng minh đã xác thực danh tính người đối diện**.

### 8.2. Những điều còn thiếu so với key establishment production

Để bảo vệ một kênh thực tế, giao thức cần nhiều thành phần không có trong code demo: chứng chỉ/chữ ký hoặc PSK, xác thực peer và transcript, kiểm soát key usage, xử lý lỗi công khai một cách an toàn, chống downgrade, record framing, Finished/key confirmation đúng chuẩn, chống replay, cryptoperiod, nonce AEAD, cập nhật khóa, chính sách phiên và audit.

**Không sử dụng lớp KeyEstablishmentDemo làm giao thức ứng dụng riêng.** Các primitive riêng lẻ có thể đúng nhưng ghép sai sẽ tạo lỗ hổng khó phát hiện.

## 9. Java trong production: để TLS 1.3 thực hiện key establishment

Khi **OrderService** gọi **PaymentService** qua HTTPS, cách triển khai phù hợp là dùng **TLS 1.3** và thư viện TLS/JSSE chuẩn, không tự viết X25519 handshake.

Ví dụ mã Java 17 sau chỉ minh họa **client HTTPS sử dụng TLS 1.3** và trust configuration mặc định của runtime; endpoint là ví dụ, không yêu cầu chạy mã trong bài học.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import javax.net.ssl.SSLParameters;

public final class SecurePaymentClientExample {
    public static void main(String[] args) throws Exception {
        SSLParameters tls = new SSLParameters();
        tls.setProtocols(new String[] { "TLSv1.3" });

        // Mặc định: sử dụng cấu hình SSL/TLS và trust store của JVM.
        // Không cài TrustManager "tin mọi certificate".
        HttpClient client = HttpClient.newBuilder()
            .sslParameters(tls)
            .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://payment.example.org/health"))
            .GET()
            .build();

        HttpResponse<Void> response = client.send(
            request, HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP status: " + response.statusCode());
    }
}
~~~

Code này không cần tự gọi HKDF hay KeyAgreement: **TLS stack** thực hiện các bước cần thiết theo giao thức được thương lượng. Khi dùng môi trường doanh nghiệp, phải cấu hình **trust anchors, hostname validation, certificate lifecycle và mTLS** nếu chính sách yêu cầu. Thư viện HTTP thông thường chỉ xác thực danh tính **server**; nó không tự cấp quyền truy cập API cho client.

Đừng tắt kiểm tra chứng chỉ bằng một TrustManager trả true mọi lúc hoặc HostnameVerifier luôn chấp nhận chỉ để “chạy thử”. Làm như vậy có thể vô hiệu hóa phần xác thực mà key establishment cần để chống MITM.

### 9.1. TLS và key schedule

Trong TLS 1.3, key agreement là một phần của handshake; giao thức còn có:

- Đàm phán group/cipher suite theo policy.
- Xác thực server, có thể xác thực client theo cấu hình.
- Key schedule và transcript hash được đặc tả chính xác.
- Traffic secrets/keys khác nhau theo hướng.
- Bản tin xác nhận kết thúc handshake.
- AEAD bảo vệ record và quản lý nonce/sequence theo chuẩn.
- Khả năng KeyUpdate và các cơ chế đặc thù của phiên.

**Không thay các nhãn HKDF của TLS bằng nhãn từ ví dụ tự viết.** Ngay cả một công thức HKDF đúng về mặt toán học vẫn có thể sai ngữ cảnh, thứ tự và mục đích so với giao thức.

### 9.2. PSK và forward secrecy trong giao thức

Một giao thức có thể sử dụng **PSK** như một phần key schedule và xác thực, nhưng việc chỉ có PSK lâu dài không tự đem lại forward secrecy. Tùy chế độ, giao thức có thể kết hợp PSK với ephemeral agreement để có bảo đảm mạnh hơn.

Khi một PSK được chia sẻ giữa nhiều dịch vụ, mọi principal có PSK đều có thể là một điểm rủi ro. Cần kiểm soát phân phối, phạm vi, rotation, thu hồi, định danh và tránh dùng cùng một PSK cho nhiều mục đích ngoài thiết kế.

## 10. Forward secrecy, key update và vòng đời session key

### 10.1. Forward secrecy

**Forward secrecy (FS)** là tính chất giúp các session keys đã kết thúc **không tự bị khôi phục** chỉ vì một khóa dài hạn bị lộ về sau, theo mô hình bảo mật của giao thức.

Ví dụ, một hệ thống dùng ECDHE tạm thời và chữ ký/chứng chỉ để xác thực. Nếu private signing key bị lộ sau đó, attacker có thể tìm cách giả mạo các kết nối tương lai, nhưng các phiên ECDHE cũ **có thể vẫn an toàn** nếu ephemeral secrets và traffic keys đã được hủy và không bị lộ.

FS không có nghĩa:

- Người kiểm soát máy chủ lúc đang xử lý dữ liệu không thể đọc plaintext.
- Có thể lưu lại toàn bộ ephemeral private key để debug mà vẫn giữ đầy đủ bảo đảm FS.
- Đổi certificate signing key sẽ hồi phục các traffic keys đã bị đánh cắp.
- Dẫn xuất nhiều khóa bằng HKDF từ một **root dài hạn duy nhất** tự tạo FS.
- Mọi kết nối ECDH đều có FS, bất kể dùng static key hay không.

### 10.2. Session rekey và traffic key update

Một khóa traffic nên có **cryptoperiod** và giới hạn số lần mã hóa/khối lượng dữ liệu theo thuật toán/giao thức. Key update hoặc rekey giúp giảm lượng dữ liệu phụ thuộc vào một khóa, nhưng phải tuân thủ cách cập nhật của protocol.

| Loại thay đổi | Đối tượng bị ảnh hưởng | Không tự làm được điều gì? |
| --- | --- | --- |
| Tạo ephemeral key pair mới | Phiên/bắt tay mới | Không thay private signing key dài hạn |
| Traffic key update | Khóa bảo vệ lưu lượng của phiên | Không rotation DEK/KEK database |
| Thay server certificate/signing key | Xác thực danh tính phiên tương lai | Không thay session keys đã bị đánh cắp |
| Rotate PSK | Các kết nối phụ thuộc PSK | Không bảo đảm mọi phiên cũ đã được re-encrypt |
| Rotate KMS KEK | Khóa bảo vệ DEK ở tầng lưu trữ | Không ảnh hưởng tự động key agreement của TLS |
| Re-encrypt dữ liệu với DEK mới | Bản mã dữ liệu lưu dài hạn | Không thay thông số handshake của client/server |

### 10.3. Key compromise: phạm vi và xử lý

Phải xác định **loại khóa** bị lộ:

- **Ephemeral private key của một phiên:** có thể làm lộ shared secret/session keys của phiên đó tùy thiết kế.
- **Traffic key:** kẻ có khóa có thể đọc/giả mạo dữ liệu trong phạm vi nonce/key usage liên quan.
- **Private signing key dài hạn:** có thể cho phép giả mạo danh tính trong các handshake mới nếu chưa bị chặn, nhưng FS có thể bảo vệ phiên cũ.
- **Static DH private key:** phạm vi ảnh hưởng phụ thuộc cách giao thức sử dụng static/ephemeral key.
- **PSK:** các kết nối phụ thuộc PSK có thể bị ảnh hưởng; cần xét cách trộn secret của key schedule.
- **KMS KEK/DEK:** ảnh hưởng tới dữ liệu được bọc/mã hóa, là một mặt sự cố riêng với session key mạng.

Hành động ứng phó có thể gồm disable quyền ký hoặc DeriveKey, thay credential/certificate, kết thúc phiên đang chạy, áp dụng key update/rekey nếu giao thức hỗ trợ, điều tra dữ liệu đã bị truy cập và ghi nhận bằng chứng theo chính sách. **Rotation không làm attacker quên bí mật đã sao chép**.

## 11. Key agreement và quản lý khóa với KMS/HSM

Trong hạ tầng doanh nghiệp, **KMS** và **HSM** có thể bảo vệ private keys, cấp quyền thao tác mật mã và ghi audit. Nhưng các tính năng hỗ trợ thuật toán phụ thuộc nhà cung cấp, key type và cấu hình.

### 11.1. Tách private signing key và ephemeral agreement key

Một cấu hình thông dụng:

- Private signing key dài hạn được bảo vệ trong **KMS/HSM** hoặc kho khóa an toàn; ứng dụng được cấp quyền **Sign** có giới hạn.
- **Ephemeral agreement keys** do TLS stack sinh và quản lý theo phiên.
- Public signing verification key hoặc chứng chỉ được phát hành theo **PKI/trust**.
- Session keys được giữ trong phạm vi TLS provider; ứng dụng không tự log hoặc xuất vật liệu khóa.

Không mặc định một HSM hỗ trợ tất cả phép **X25519, ECDH P-256, KEM, Sign/Verify, DeriveKey** dưới cùng một API. Cần kiểm tra điều kiện provider và thiết kế key non-exportable phù hợp.

### 11.2. Quyền gọi API vẫn là một bí mật vận hành

Một private key nằm trong HSM và **không xuất được** không có nghĩa kẻ tấn công chiếm workload có quyền thao tác không thể lạm dụng nó. Nếu service được phép gọi Sign hoặc DeriveKey không hạn chế, attacker có thể tạo bằng chứng/secret cho mục đích trái phép mà không bao giờ xuất private key.

Các biện pháp:

- **Least privilege:** giới hạn key ID, key usage, principal và môi trường.
- **Separation of duties:** tách người quản trị key policy, người vận hành dịch vụ và người audit.
- **Identity binding:** service account đã xác thực và có quyền trên đúng khóa/mục đích.
- **Audit:** ghi thao tác Sign/Derive/Unwrap/Disable/Rotate và thay policy; không ghi secret.
- **Blast-radius control:** tách khóa theo môi trường/tenant khi cần, không dùng chung một root cho mọi workload.
- **Incident response:** theo dõi hoạt động bất thường, khả năng revoke nhanh và chuẩn bị hướng khôi phục.

### 11.3. KMS encryption context không tự xác thực peer trong DH

Một số KMS hỗ trợ **encryption context/AAD** để ràng buộc việc bọc hoặc giải bọc một data key. Đây là cơ chế thuộc **tầng mã hóa/lưu trữ**; nó không tự chứng minh public key ECDH đến từ server thật.

Ngược lại, TLS bảo vệ đường truyền không tự bảo đảm DEK của database được quản lý tốt. Phải thiết kế nhiều lớp theo đúng phạm vi.

## 12. Key establishment và envelope encryption: hai vòng đời khác nhau

Ví dụ một hệ thống có hai nhu cầu:

1. **Client kết nối tới PaymentAPI:** phải thiết lập kênh truyền an toàn qua mạng công khai.
2. **PaymentAPI lưu hóa đơn:** phải mã hóa dữ liệu có thể cần giải mã nhiều tháng sau.

Hai nhu cầu dùng những khóa có vai trò khác nhau.

~~~mermaid
flowchart LR
    C["OrderService"] -->|"TLS 1.3 key establishment + AEAD"| API["PaymentAPI"]
    API --> IAM["Xác thực và phân quyền tenant"]
    IAM --> ENC["Mã hóa bản ghi với DEK"]
    ENC --> DB["Database: ciphertext + wrapped DEK"]
    KMS["KMS/HSM giữ KEK"] <-->|"GenerateDataKey / Wrap / Unwrap"| ENC
~~~

| Lớp | Khóa chủ yếu | Vòng đời |
| --- | --- | --- |
| **Network session** | ECDHE ephemeral keys, shared secret, traffic keys | Ngắn; theo phiên và key schedule |
| **Authentication** | Signing key/certificate hoặc PSK | Dài hơn; rotation, revocation, kiểm soát danh tính |
| **Stored data** | DEK và KEK | Theo thời hạn lưu trữ; rewrap/re-encrypt có kế hoạch |
| **Authorization** | Identity/roles/policies; không nhất thiết là khóa mật mã riêng | Theo người dùng, workload, tenant và quyền tài nguyên |

**DEK** dùng AES-GCM hoặc thuật toán phù hợp để bảo vệ dữ liệu lưu trữ. **KEK** bọc DEK dưới KMS/HSM. Dùng ECDH để tạo traffic key cho kết nối không tự làm KEK có thể giải mã backup trong nhiều năm.

### 12.1. Khi key agreement phục vụ chia sẻ DEK

Một sản phẩm có thể cần gửi tệp mã hóa cho một đối tác chỉ có public key. Khi đó **authenticated key agreement/KEM + KDF + key wrapping** có thể tham gia thiết kế:

~~~text
Sender + public key người nhận đã xác thực
    |
    +--> thiết lập shared secret theo giao thức
    |
    +--> KDF với context/recipient identity/purpose
    |
    +--> key-encryption material / wrapping key
    |
    +--> wrapped DEK + ciphertext tài liệu + metadata

Receiver + private key tương ứng
    |
    +--> khôi phục shared secret
    |
    +--> cùng key schedule → unwrapping key
    |
    +--> unwrap DEK → decrypt tài liệu
~~~

Việc này phải dùng **giao thức/định dạng chuẩn** có phân tích bảo mật; không tự thay một kết quả X25519 bằng bytes của KEK AES rồi dùng không có xác thực. Nếu private key người nhận có vòng đời dài, cần kế hoạch mất/rotation khóa để vẫn mở được các DEK cũ theo chính sách.

**Key agreement không đồng nghĩa key wrapping.** Agreement tạo nguồn bí mật chung; wrapping bảo vệ DEK đã có. Một hệ thống có thể dùng cả hai ở những bước khác nhau.

## 13. Threat model cho key agreement

| Sai sót hoặc tấn công | Hậu quả | Cách giảm thiểu |
| --- | --- | --- |
| **MITM thay public key** | Hai phía tạo secret với attacker thay vì với nhau | Authenticated key establishment, PKI/PSK/trust đúng |
| **Không kiểm tra thuật toán/curve/public input** | Có thể nhận giá trị hoặc nhóm không hợp lệ, gặp lỗi mật mã tùy cơ chế | Thư viện chuẩn, kiểm tra public key và secret theo đặc tả |
| **Không xác thực transcript** | Downgrade, nhầm vai trò, ghép thông điệp | Transcript binding, Finished/confirmation theo protocol |
| **UKS/nhầm danh tính** | Có khóa hợp lệ nhưng một phía hiểu sai đối tác | Gắn identity và role vào xác thực/key schedule đúng chuẩn |
| **Dùng raw ECDH secret làm AES key** | Thiếu key schedule và tách miền | KDF được đặc tả, info/context rõ |
| **Dùng cùng traffic key cho hai hướng** | Rủi ro nonce collision và lẫn vai trò | Khóa riêng theo hướng, nonce theo protocol |
| **Nonce reuse trong AES-GCM** | Có thể mất confidentiality và integrity | Quản lý nonce duy nhất, giới hạn cryptoperiod/rekey |
| **Replay handshake/data** | Thông điệp hợp lệ cũ được phát lại | Freshness, sequence/counter, chống replay theo giao thức |
| **Algorithm downgrade** | Kết nối rơi xuống nhóm/cipher yếu không mong muốn | Allowlist thuật toán, bảo vệ negotiation |
| **Lộ ephemeral private key** | Mất bí mật trong các phiên bị ảnh hưởng | Không lưu log; hủy sớm; hạn chế memory dumps |
| **Lộ signing key** | Giả mạo peer trong các lần xác thực mới | KMS/HSM, thu hồi certificate, rotation và báo động |
| **Lộ static DH private key** | Ảnh hưởng rộng tùy key schedule | Giới hạn sử dụng, rotation và đánh giá FS |
| **PSK dùng chung mọi service** | Một service bị chiếm ảnh hưởng nhiều bên | Tách PSK, least privilege, lifecycle |
| **Chỉ dựa vào TLS mà bỏ IAM** | Có kênh an toàn nhưng đọc sai tài nguyên | Phân quyền ứng dụng độc lập |
| **Giữ key quá lâu** | Tăng lượng dữ liệu/phiên bị ảnh hưởng khi lộ | Session expiry, key update, rotation |
| **Log key/secret** | Phá hiệu quả mật mã dù thuật toán mạnh | Redaction, audit metadata, hạn chế quyền debug |

### 13.1. Replay không phải lỗi công thức DH

Một thông điệp bắt tay hoặc một sự kiện có thể được gửi lại nguyên vẹn. Việc hai bên tính ra shared secret đúng không tự chứng minh thông điệp **mới**. Một giao thức cần kiểm soát freshness qua nonce, random, sequence, session state, transcript và/hoặc biện pháp khác phù hợp.

Trong thiết kế ứng dụng, webhook thanh toán gửi qua TLS vẫn cần **event ID, idempotency và quyền nghiệp vụ** để tránh xử lý giao dịch hai lần.

### 13.2. Downgrade và sự nhất quán thuật toán

Giả sử client hỗ trợ nhóm mạnh nhưng attacker sửa thông điệp negotiation để server chọn một nhóm khác. Nếu protocol không có cơ chế phát hiện thay đổi ở transcript hoặc chính sách nhóm yếu vẫn được chấp nhận, hai bên có thể sử dụng cấu hình thấp hơn yêu cầu.

Không đủ nếu chỉ đặt “ưu tiên nhóm mạnh” mà vẫn cho phép mọi nhóm yếu hoặc bỏ kiểm tra transcript. Cần **danh sách cho phép** và sử dụng **giao thức xác thực negotiation** phù hợp.

### 13.3. Unknown key-share và role confusion

Một thiết kế có thể dùng cùng một shared secret nhưng các phía lại hiểu khác **issuer, peer, tenant hoặc role**. Đây là lỗi ở cách ràng buộc context, không nhất thiết là lỗi ECDH.

Ràng buộc **danh tính được xác thực, transcript, role và purpose** là điều kiện giúp key agreement trở thành một phần của authenticated key establishment có ý nghĩa.

## 14. Kiểm toán, vận hành và ứng phó sự cố

### 14.1. Những sự kiện nên theo dõi

- Thất bại certificate validation hoặc xác thực peer.
- Bất thường về protocol version, nhóm agreement hoặc thuật toán AEAD đã thương lượng.
- Tần suất handshake thất bại tăng hoặc các nguồn cố tình đề xuất nhóm bị cấm.
- Thay đổi trust anchors, trust store, signing key, certificate hoặc PSK.
- Thao tác KMS/HSM liên quan Sign, DeriveKey, key policy, grants và rotation.
- Session sử dụng key quá lâu hoặc không thực hiện key update theo chính sách.
- Lỗi phân quyền sau khi kết nối đã được xác thực.

Nhật ký có thể ghi **timestamp, workload, peer identity, certificate fingerprint/key ID, phiên bản TLS, nhóm đã thương lượng, request ID, loại lỗi và kết quả**, theo chính sách về dữ liệu nhạy cảm. **Không ghi** ECDH private key, shared secret, HKDF PRK, traffic keys, DEK/KEK rõ hoặc password.

### 14.2. Kịch bản: khóa ký máy chủ bị lộ

Giả sử private signing key của PaymentService bị lộ. Kẻ tấn công có thể giả mạo PaymentService khi có cơ hội và nếu verifier còn tin khóa/chứng chỉ đó. Quy trình phản ứng:

1. Cô lập key/signing principal hoặc workload bị nghi vấn.
2. Thu hồi/vô hiệu hóa certificate, key hoặc quyền theo khả năng hạ tầng.
3. Tạo/đăng ký signing key mới và cập nhật trust của các bên liên quan.
4. Xử lý các client cache trust và những phiên rủi ro.
5. Đánh giá hành vi giả mạo trong khoảng thời gian nghi ngờ.
6. Phân tích liệu **các phiên ECDHE trước** có được bảo vệ bởi forward secrecy trong thực tế hay secret phiên cũng đã bị lộ.
7. Kiểm tra audit và siết quyền KMS/HSM trước khi phục hồi toàn bộ lưu lượng.

**Đừng tự giả định** tất cả các phiên TLS 1.3 cũ đều đã bị giải mã chỉ vì signing key lộ; cũng đừng khẳng định mọi dữ liệu cũ đều an toàn nếu có dấu hiệu attacker chiếm endpoint hoặc ghi được session keys.

## 15. Tình huống thực tế: thiết kế OrderService ↔ PaymentService

### Bài toán

OrderService và PaymentService chạy trong hạ tầng khác nhau, giao tiếp qua Internet. Hệ thống yêu cầu:

- Chống nghe lén và giả mạo trên mạng.
- Xác thực đúng service, có phân quyền theo tenant.
- Có thể xoay vòng chứng chỉ mà không mất hóa đơn lưu trữ.
- Hỗ trợ audit, ứng phó sự cố và khôi phục backup.
- Không xuất private key dài hạn hoặc DEK rõ vào hệ thống không cần quyền.

### Thiết kế đề xuất

| Lớp | Cơ chế | Lý do |
| --- | --- | --- |
| **Transport** | HTTPS/TLS 1.3 qua thư viện chuẩn | Giải quyết authenticated key establishment và AEAD theo giao thức |
| **Peer identity** | Server certificate đã được kiểm tra; mTLS khi phù hợp | Chứng minh bên kết nối thuộc danh tính service dự kiến |
| **Authorization** | API identity, service role, tenant ACL | Key agreement không cấp quyền đọc hóa đơn |
| **Stored data** | DEK ngẫu nhiên + AES-GCM/AAD | Bảo vệ bí mật và tính toàn vẹn bản ghi |
| **Key protection** | KEK trong KMS/HSM, wrapped DEK | Tách key lifecycle lưu trữ khỏi TLS |
| **Key lifecycle** | Certificate rotation, session key update, KEK/DEK rotation riêng | Tránh thay sai loại khóa và gián đoạn |
| **Audit** | TLS validation, IAM/KMS, key ID/version, request ID | Có khả năng điều tra mà không lộ vật liệu khóa |

~~~mermaid
flowchart TD
    A["OrderService"] -->|"TLS 1.3: agreement + authentication + AEAD"| B["PaymentService"]
    B --> I["IAM: principal, tenant, resource policy"]
    I --> E["Mã hóa bản ghi bằng DEK"]
    E --> D["Database ciphertext + wrapped DEK"]
    K["KMS/HSM KEK"] <-->|"Wrap / Unwrap / key policy"| E
    B --> L["Audit: peer identity, key IDs, thao tác"]
    K --> L
~~~

### Sự cố giả định

Một certificate server đến ngày rotation. **Không cần re-encrypt toàn bộ hóa đơn** chỉ vì đổi signing certificate: những bản mã lưu trữ vẫn phụ thuộc DEK/KEK riêng. Điều phải làm là phân phối chứng chỉ mới có chain/trust hợp lệ, đảm bảo client xác thực được danh tính PaymentService, giữ dịch vụ không bị gián đoạn và cập nhật policy theo quy trình.

Ngược lại, nếu **KEK của database bị lộ**, thay certificate TLS không khắc phục được dữ liệu đã bị ảnh hưởng. Cần điều tra và xử lý key wrapping/re-encryption theo mô hình sự cố của dữ liệu lưu trữ.

## 16. Checklist thiết kế key agreement

1. **Bài toán:** đang cần thiết lập khóa phiên, vận chuyển DEK hay mã hóa dữ liệu lưu trữ?
2. **Giao thức:** có thể dùng TLS 1.3 hoặc một giao thức AKE chuẩn thay vì tự ghép primitive không?
3. **Thuật toán:** nhóm DH/ECDH/KEM và cipher suite có nằm trong policy, có phù hợp provider/HSM không?
4. **Sinh khóa:** ephemeral keys được tạo bằng nguồn ngẫu nhiên an toàn và đúng thuật toán chưa?
5. **Public input:** có kiểm tra định dạng/nhóm/public key và kết quả bất thường theo chuẩn không?
6. **Xác thực:** hai phía biết đúng peer identity bằng certificate/PSK/trust nào?
7. **Transcript:** negotiation, public keys, role, identity và thông điệp liên quan có được xác thực đúng không?
8. **KDF:** shared secret có đi qua key schedule đúng giao thức, có phân tách hướng/purpose không?
9. **Key confirmation:** có bằng chứng hoàn tất handshake theo đặc tả không, và có nhầm nó với identity validation không?
10. **AEAD:** nonce/sequence có được quản lý duy nhất theo khóa và giới hạn sử dụng không?
11. **Forward secrecy:** có ephemeral secret và cách hủy thích hợp; có tránh log/session key export không?
12. **Replay/downgrade:** negotiation và thông điệp có được bảo vệ theo đặc tả, có freshness không?
13. **Cryptoperiod:** session expiry, traffic key update, certificate/PSK rotation đã được định nghĩa chưa?
14. **KMS/HSM:** private signing/static agreement keys được bảo vệ, quyền Sign/DeriveKey được giới hạn chưa?
15. **IAM:** sau handshake có kiểm tra quyền ứng dụng theo tenant/đối tượng không?
16. **DEK/KEK:** khóa phiên mạng có được tách hoàn toàn khỏi khóa lưu trữ và chính sách backup không?
17. **Incident response:** nếu signing key/ephemeral key/traffic key/PSK bị lộ, có xác định phạm vi và hành động riêng cho từng loại không?
18. **Audit:** có đủ sự kiện điều tra mà không ghi shared secret hoặc derived key không?
19. **Khôi phục:** rotation hoặc mất chứng chỉ có gây mất khả năng mở dữ liệu database không? Nếu có, kiến trúc đã tách trách nhiệm hợp lý chưa?
20. **Kiểm thử:** có tình huống sai certificate/hostname, public key không hợp lệ, thuật toán bị cấm, role sai, replay, rotation và đóng phiên không?

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Hai phía tính được cùng ECDH shared secret. Điều đó chứng minh chúng đã xác thực đúng danh tính nhau chưa?

**Đáp án:** Chưa. Một kẻ MITM có thể thực hiện agreement riêng với mỗi phía. Muốn tin peer, phải xác thực public key, danh tính và handshake theo giao thức.

**Câu 2.** Key agreement và key transport khác nhau ở ý chính nào?

**Đáp án:** Với key agreement kiểu DH, các bên dùng các private/public key tương ứng để tính shared secret từ đóng góp của mình. Với key transport, một bên có thể tạo khóa rồi chuyển nó dưới cơ chế bảo vệ thích hợp. Cả hai đều có thể là phương án key establishment.

**Câu 3.** Vì sao không nên dùng raw X25519 shared secret làm AES-256 key cho mọi mục đích?

**Đáp án:** Giao thức cần KDF/key schedule có context, transcript và tách khóa cho từng mục đích/hướng. Việc lấy trực tiếp raw secret bỏ qua các yêu cầu về key separation và protocol binding.

**Câu 4.** Có phải key confirmation tự chứng minh phía đối diện chính là máy chủ thanh toán?

**Đáp án:** Không. Confirmation giúp chứng minh bên kia có khả năng sử dụng khóa đúng theo giao thức, nhưng vẫn cần xác thực identity. Một phiên với kẻ giả mạo cũng có thể có confirmation hợp lệ.

**Câu 5.** Vì sao session keys nên tách theo hướng client→server và server→client?

**Đáp án:** Tách khóa giảm nguy cơ dùng cùng khóa/nonce cho cả hai chiều, phân biệt vai trò và hỗ trợ key schedule rõ ràng. Nonce AEAD vẫn phải quản lý đúng riêng cho từng khóa.

**Câu 6.** Private signing key của server bị lộ sau khi một phiên ECDHE đã kết thúc. Có chắc giải mã được traffic cũ không?

**Đáp án:** Không. Nếu giao thức có forward secrecy và ephemeral/session secrets cũ đã được hủy an toàn, lộ signing key sau đó không tự làm lộ traffic cũ. Tuy vậy cần điều tra xem endpoint hoặc session keys cũng có bị lộ hay không.

**Câu 7.** Đổi KMS KEK của database có tự thay khóa phiên TLS giữa hai service không?

**Đáp án:** Không. KEK bảo vệ DEK lưu trữ; traffic key thuộc vòng đời của kết nối mạng. Chúng có vai trò, quyền và cơ chế rotation khác nhau.

**Câu 8.** Một service có mTLS thành công được quyền đọc mọi hóa đơn trong database?

**Đáp án:** Không. mTLS xác thực danh tính kết nối. Ứng dụng vẫn cần phân quyền theo principal, tenant, invoice ID và hành động.

**Câu 9.** KMS/HSM giữ private key non-exportable thì có thể cấp quyền DeriveKey cho mọi workload không?

**Đáp án:** Không. Workload bị chiếm có thể lạm dụng quyền thao tác khóa mà không cần xuất key. Cần least privilege, identity/purpose policy và audit.

**Câu 10.** Nếu một nhóm thuật toán yếu được chấp nhận trong negotiation nhưng hai bên đều “ưu tiên” nhóm mạnh, đã an toàn trước downgrade chưa?

**Đáp án:** Chưa đủ. Cần policy cấm nhóm không được phép và cơ chế transcript/negotiation authentication của giao thức để phát hiện sự sửa đổi hoặc hạ cấp.

## Kết luận

**Key agreement là một cơ chế thiết lập vật liệu khóa chung trong hệ thống key establishment**, thường dựa trên DH/ECDH/X25519 hoặc các thành phần khác theo giao thức. Kết quả toán học đúng **chưa đủ**: hệ thống phải xác thực đúng người tham gia, kiểm tra đầu vào, bảo vệ transcript, dẫn xuất khóa theo mục đích, kiểm tra hoàn tất handshake và quản lý khóa phiên an toàn.

Trong hệ thống Java thực tế, nên sử dụng **TLS 1.3 hoặc giao thức authenticated key establishment chuẩn** thay vì tự ghép các phép mật mã. **KMS/HSM, chữ ký số, IAM, envelope encryption và audit** bổ sung bảo vệ cho các loại khóa và dữ liệu khác nhau. Thiết kế tốt không chỉ khiến hai bên tính ra **cùng khóa**, mà còn bảo đảm **khóa được chia sẻ đúng đối tác, đúng mục đích, đúng quyền và đúng thời hạn**.
