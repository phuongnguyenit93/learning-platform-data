# Key agreement: thỏa thuận khóa trong mật mã bất đối xứng

## 1. Tại sao hai bên cần thỏa thuận khóa?

Một ứng dụng Java kết nối tới dịch vụ thanh toán qua mạng công cộng. Cả hai muốn mã hóa dữ liệu bằng **AES-GCM**, nhưng trước khi mã hóa phải có **khóa đối xứng chung**. Nếu gửi trực tiếp khóa AES ở dạng rõ qua mạng, người nghe lén có thể lấy khóa rồi giải mã toàn bộ dữ liệu.

**Key agreement (thỏa thuận khóa)** cho phép hai hoặc nhiều bên cùng thiết lập **vật liệu bí mật chung** thông qua một giao thức mật mã, ngay cả khi những thông điệp công khai của giao thức bị quan sát. Trong các giao thức dùng **Diffie–Hellman (DH)** hoặc **Elliptic-Curve Diffie–Hellman (ECDH)**, mỗi bên dùng private key của mình cùng public key của bên kia để tính ra một bí mật chung; từ đó dùng **KDF (Key Derivation Function)** để dẫn xuất khóa sử dụng thực tế.

~~~text
Client: private A + public B  ──► shared secret ──► KDF ──► session keys
Server: private B + public A  ──► shared secret ──► KDF ──► session keys
                  ▲                                      ▲
          Public keys trao đổi                    Khóa đối xứng
          trên kênh công khai                  dùng cho AEAD / MAC
~~~

**Điểm then chốt:** key agreement tạo ra bí mật chung, nhưng **không tự xác thực danh tính đối tác**. Nếu thiếu bước xác thực public key và bản ghi bắt tay, kẻ đứng giữa có thể thiết lập hai phiên riêng rồi đọc hoặc sửa thông điệp. Một giao thức bảo mật hoàn chỉnh cần phối hợp **thỏa thuận khóa + xác thực đối tác + KDF + mã hóa có xác thực + quản lý vòng đời khóa**.

Sau bài này, người học có thể:

1. Phân biệt key agreement, key exchange, key transport, KEM, mã hóa bất đối xứng và chữ ký số.
2. Giải thích DH/ECDH, vai trò public/private key và cách hai bên tạo cùng shared secret.
3. Hiểu vì sao shared secret cần qua KDF như HKDF trước khi dùng làm session key.
4. Nhận diện các rủi ro MITM, tráo public key, lỗi xác thực, replay, downgrade và key compromise.
5. Phân tích **forward secrecy**, rotation, thu hồi và hủy khóa phiên/khóa dài hạn.
6. Đọc ví dụ Java 17 dùng X25519 và HKDF-SHA256, đồng thời hiểu giới hạn của ví dụ.
7. Kết nối key agreement với chữ ký số, chứng chỉ, TLS, KMS/HSM, envelope encryption, IAM và audit.

## 2. Phân biệt các khái niệm dễ nhầm

Trong nhiều tài liệu, **key exchange** được dùng như thuật ngữ bao quát để chỉ các cách thiết lập khóa; **key agreement** có ý nghĩa cụ thể hơn là các bên đóng góp vào quá trình tạo bí mật chung. Không nên đồng nhất mọi giao thức trao đổi khóa với một phép ECDH đơn lẻ.

| Khái niệm | Cách hoạt động khái quát | Ví dụ và lưu ý |
| --- | --- | --- |
| **Key agreement** | Hai bên dùng vật liệu bí mật riêng cùng thông tin công khai của đối tác để tính vật liệu bí mật chung | ECDH, X25519; thường phải kết hợp KDF và xác thực |
| **Key transport** | Một bên tạo/chọn khóa rồi bảo vệ khóa đó khi chuyển cho bên nhận | Ví dụ dùng public-key encryption thích hợp để vận chuyển một khóa nhỏ |
| **KEM (Key Encapsulation Mechanism)** | Một bên encapsulate tạo ciphertext và shared secret, bên nhận decapsulate để thu cùng shared secret | Khác giao diện DH; không nên tự chuyển một phép DH thành KEM tùy ý |
| **Symmetric encryption** | Dùng khóa bí mật đã có để mã hóa/giải mã dữ liệu | AES-GCM bảo vệ dữ liệu, nhưng không tự giúp hai máy chưa chia sẻ bí mật tạo khóa chung |
| **Asymmetric encryption** | Mã hóa theo public key và giải mã theo private key | RSA-OAEP với giới hạn kích thước plaintext; có thể dùng trong giao thức vận chuyển khóa |
| **Digital signature** | Private key ký, public key xác minh chữ ký | RSA-PSS, ECDSA, Ed25519; thường giúp xác thực một handshake, không trực tiếp tạo khóa phiên |
| **KDF** | Dẫn xuất các khóa có mục đích rõ từ key material | HKDF-SHA256 nhận shared secret và context để tạo traffic keys |

Ví dụ: **Ed25519** là thuật toán **chữ ký số**, **X25519** là cơ chế **thỏa thuận khóa** dựa trên đường cong Montgomery. Dù tên gần giống nhau, không dùng key Ed25519 như một key X25519 bằng cách đổi tên thuật toán hoặc đổi byte tùy tiện.

**Key agreement không đồng nghĩa key management.** Key agreement là một thao tác/protocol trong vòng đời khóa; key management còn gồm sinh khóa, lưu trữ, phân quyền, sử dụng, xoay vòng, thu hồi, kiểm toán, backup và hủy.

## 3. Trực giác toán học của Diffie–Hellman

Để hiểu tại sao hai bên có thể tính cùng một bí mật mà không gửi bí mật đó qua mạng, xem một ví dụ số nhỏ **chỉ phục vụ học tập**.

Giả sử hai bên công khai số nguyên tố **p = 23** và một phần tử cơ sở **g = 5** trong nhóm thích hợp. Alice chọn số bí mật **a = 6**, Bob chọn **b = 15**.

- Alice tính giá trị công khai **A = g^a mod p = 8** rồi gửi A cho Bob.
- Bob tính giá trị công khai **B = g^b mod p = 19** rồi gửi B cho Alice.
- Alice tính **s = B^a mod p = 2**.
- Bob tính **s = A^b mod p = 2**.

Hai bên có cùng s do:

\[
(B)^a \bmod p = (g^b)^a \bmod p = g^{ab} \bmod p
\]

\[
(A)^b \bmod p = (g^a)^b \bmod p = g^{ab} \bmod p
\]

Kẻ nghe lén thấy p, g, A và B nhưng không thấy a hoặc b. Trong nhóm tham số đủ mạnh và được sử dụng đúng, việc tính bí mật chung chỉ từ các giá trị công khai được cho là khó về mặt tính toán theo giả định của DH.

**Không dùng các con số trong ví dụ để mã hóa thật.** Chúng quá nhỏ, có thể thử hết ngay lập tức. Mật mã DH thực tế phải sử dụng nhóm đã chuẩn hóa, tham số đủ mạnh, giá trị công khai hợp lệ và thư viện được kiểm chứng; không tự chọn p, g hoặc cài đặt phép toán nhóm để xây một giao thức production.

### 3.1. Vì sao hai bên không gửi private key?

Giá trị private key là dữ liệu bí mật của từng bên; nếu bị lộ, người khác có thể giả mạo việc tham gia thỏa thuận hoặc khôi phục shared secret của những phiên bị ảnh hưởng, tùy thiết kế. Giá trị public key có thể truyền đi, nhưng **tính xác thực của public key** phải được bảo đảm nếu cần xác thực đối tác.

Ngay cả khi công thức toán học tạo cùng s, **s chưa phải khóa AES-GCM dùng trực tiếp**. Giao thức cần dẫn xuất khóa qua KDF, ràng buộc vào context và phân tách theo từng mục đích/chiều truyền.

## 4. ECDH và X25519 trong hệ thống hiện đại

**Elliptic-Curve Diffie–Hellman (ECDH)** áp dụng nguyên lý thỏa thuận khóa trên nhóm điểm của đường cong elliptic. Cùng cấp độ an toàn cổ điển thông dụng, các giao thức dựa trên đường cong thường sử dụng public key nhỏ hơn DH nhóm hữu hạn truyền thống.

### 4.1. Vai trò của private và public key

Trong một phiên ECDH:

1. Alice tạo một cặp **private/public key** hợp lệ theo thuật toán.
2. Bob cũng tạo một cặp như vậy.
3. Hai bên trao đổi public key theo giao thức.
4. Alice tính shared secret bằng private key của mình và public key của Bob.
5. Bob tính shared secret bằng private key của mình và public key của Alice.
6. Giao thức xử lý shared secret bằng KDF và sử dụng khóa dẫn xuất theo chính sách.

Các thao tác trên **không phải chữ ký số** và **không tự kiểm tra đối tác có đúng là Bob/Alice hay không**.

### 4.2. X25519, ECDH trên P-256 và tính tương thích

| Lựa chọn | Đặc điểm | Lưu ý triển khai |
| --- | --- | --- |
| **X25519** | Chức năng thỏa thuận khóa dựa trên Curve25519 | Hỗ trợ rộng trong các stack hiện đại; dùng implementation chuẩn, kiểm tra lỗi và quy tắc đầu ra theo giao thức |
| **ECDH với P-256** | ECDH trên đường cong NIST P-256 | Thường có hỗ trợ trong JCA/JCE, TLS và HSM; phải dùng điểm, nhóm và thuật toán theo đúng chuẩn |
| **Finite-field DH / FFDHE** | DH trên nhóm hữu hạn với tham số đã được chuẩn hóa | Cần nhóm đủ mạnh, kiểm tra public value và tránh nhóm/tham số yếu |
| **KEM chuẩn hóa** | Giao diện encapsulate/decapsulate thay cho kiểu ECDH truyền thống | Lựa chọn theo giao thức, khả năng tương thích và mô hình đe dọa; có thể kết hợp với ECDH trong thiết kế hybrid |

Với **X25519**, cả hai bên phải tuân thủ yêu cầu xử lý public key và kiểm tra kết quả theo giao thức; một đầu ra **shared secret toàn byte 0** là trường hợp phải bị từ chối trong các giao thức yêu cầu kiểm tra đó. Dùng thư viện nền tảng và phương thức xác thực được thiết kế phù hợp; không thay phép kiểm tra giá trị đầu ra bằng tự sáng tạo phép kiểm tra điểm trên đường cong.

Với các họ ECDH khác, kiểm tra membership, điểm không hợp lệ, cofactor hoặc public key bất thường **phụ thuộc thuật toán và chuẩn**. Đừng áp dụng máy móc kiểm tra của X25519 cho mọi đường cong.

### 4.3. Public key công khai nhưng không thể tin mọi public key

Kẻ tấn công có thể tự tạo một cặp khóa hợp lệ và gửi public key của mình. Điều này không phá ECDH; nhưng nếu ứng dụng tin rằng đó là khóa của máy chủ thanh toán, ứng dụng có thể tạo shared secret với **kẻ tấn công**.

Vì vậy cần phân biệt:

- **Mathematically valid public key:** được thuật toán chấp nhận và có dạng hợp lệ.
- **Authenticated public key:** có bằng chứng gắn public key với đúng danh tính và quyền sử dụng theo giao thức.
- **Authorized peer:** danh tính đã xác thực **được phép** thực hiện hành động nghiệp vụ hiện tại.

Một public key có thể hợp lệ về toán học mà không thuộc về đối tác mong muốn; một đối tác được xác thực vẫn có thể không có quyền đọc dữ liệu cụ thể.

## 5. Luồng thỏa thuận khóa: từ bắt tay đến khóa phiên

Một giao thức client–server sử dụng ECDH tạm thời thường có các bước tổng quát sau:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>C: Sinh ephemeral key pair (cPriv, cPub)
    C->>S: cPub + đề xuất phiên bản/thuật toán
    S->>S: Sinh ephemeral key pair (sPriv, sPub)
    S-->>C: sPub + bằng chứng xác thực server
    C->>C: Kiểm tra danh tính, chứng chỉ/chữ ký và transcript
    Note over C,S: Hai bên tính shared secret với ECDH
    C->>C: ECDH(cPriv, sPub)
    S->>S: ECDH(sPriv, cPub)
    Note over C,S: KDF gắn vào transcript/role/context
    C->>C: Dẫn xuất traffic keys
    S->>S: Dẫn xuất traffic keys
    C->>S: Thông điệp xác thực/khẳng định khóa theo giao thức
    S-->>C: Thông điệp xác thực/khẳng định khóa theo giao thức
    Note over C,S: Chỉ truyền dữ liệu dưới AEAD theo chính sách
~~~

Sơ đồ là **mô hình học thuật**, không phải đặc tả hoàn chỉnh của TLS hoặc một giao thức sản xuất. Thứ tự và bằng chứng xác thực thực tế phụ thuộc giao thức. Ví dụ, TLS 1.3 dùng key schedule và xác thực bản ghi handshake theo quy tắc riêng, không nhất thiết trao đổi đúng những thông điệp được đặt tên trong sơ đồ.

### 5.1. Shared secret chưa phải khóa dùng trực tiếp

Một thiết kế chuẩn không nên lấy thẳng số/byte trả về từ ECDH và truyền vào AES hoặc HMAC. Đầu ra từ phép thỏa thuận khóa được đưa qua **KDF** để:

- Trích xuất vật liệu khóa có tính chất phù hợp theo giả định về secret đầu vào.
- Ràng buộc khóa với **phiên bản giao thức**, danh tính/role và transcript.
- Tách khóa cho các **mục đích** và **chiều truyền** khác nhau.
- Tránh dùng một khóa cho nhiều thuật toán trong khi thiết kế không có chứng minh bảo mật cho cách tái sử dụng đó.

**HKDF (RFC 5869)** là một KDF thông dụng cho key material có entropy mật mã đủ tốt; với HKDF-SHA256, ta có thể hình dung:

~~~text
PRK = HKDF-Extract(salt, ECDH_shared_secret)

clientWriteKey = HKDF-Expand(
    PRK, info="app/v1|client-to-server|aead|" + transcriptHash, 32)

serverWriteKey = HKDF-Expand(
    PRK, info="app/v1|server-to-client|aead|" + transcriptHash, 32)
~~~

Trong ví dụ này **32 byte** phù hợp cho khóa AES-256. Công thức chỉ mô tả cách phân tách ngữ cảnh; một giao thức sản xuất cần định nghĩa chính xác việc mã hóa info, thứ tự vai trò, độ dài, salt, transcript và key confirmation. **Không tự thế công thức này vào TLS 1.3**: TLS 1.3 có key schedule và nhãn HKDF riêng.

### 5.2. Salt, info, transcript và nonce không phải cùng một thứ

| Thành phần | Mục đích |
| --- | --- |
| **ECDH shared secret** | Vật liệu bí mật do phép key agreement tạo ra |
| **HKDF salt** | Đầu vào Extract; thường công khai và có thể giúp tách phiên/nguồn secret tùy giao thức |
| **HKDF info/label** | Gắn khóa dẫn xuất với mục đích, phiên bản, vai trò và hướng truyền |
| **Transcript hash** | Giá trị băm của các thông điệp bắt tay theo quy ước, giúp khóa/xác thực gắn với diễn tiến phiên |
| **AEAD nonce/IV** | Giá trị cho từng lần mã hóa bằng cùng session key, tuân thủ giới hạn thuật toán |
| **Authentication tag** | Bằng chứng xác thực mật mã ciphertext và associated data theo key/nonce |

**Không dùng lại salt của KDF như thể nó là nonce của AES-GCM.** Chúng có mục đích và yêu cầu quản lý khác nhau. Cũng không gửi shared secret ở dạng rõ qua mạng; hai bên đã có khả năng tính nó cục bộ.

### 5.3. Tách khóa theo hướng truyền

Nếu client và server dùng **cùng session key và cùng cơ chế tăng nonce** cho cả hai chiều, rất dễ tạo ra **nonce trùng dưới một khóa**, đặc biệt khi hai phía cùng bắt đầu từ số đếm 0. Một thiết kế rõ ràng dẫn xuất **client_write_key** và **server_write_key** khác nhau, quản lý nonce độc lập và ràng buộc chính xác role.

Việc tách miền (*domain separation*) cũng hữu ích khi dẫn xuất khóa để mã hóa dữ liệu, khóa MAC, khóa xuất giao thức hoặc khóa wrap. Không nên dùng cùng một derived key cho nhiều mục đích chỉ vì có cùng độ dài.

## 6. Vấn đề xác thực: ECDH tự nó không chống man-in-the-middle

Hãy xem một phiên ECDH không xác thực giữa Alice và Bob, có kẻ tấn công Mallory ở giữa.

1. Alice gửi public key cho Bob; Mallory chặn và thay bằng public key của Mallory.
2. Bob trả public key cho Alice; Mallory chặn và lại thay bằng public key của mình.
3. Alice tính **shared secret với Mallory**, trong khi tưởng là với Bob.
4. Bob cũng tính **một shared secret khác với Mallory**, trong khi tưởng là với Alice.
5. Mallory giải mã dữ liệu từ Alice rồi mã hóa lại gửi Bob, và làm điều ngược lại.

~~~mermaid
flowchart LR
    A["Alice"] <-->|"ECDH phiên 1"| M["Mallory"]
    M <-->|"ECDH phiên 2"| B["Bob"]
    N["Alice tin đây là Bob"] -.-> A
    O["Bob tin đây là Alice"] -.-> B
~~~

Ở đây các phép ECDH vẫn hoạt động đúng. Vấn đề nằm ở việc **không xác thực public key và danh tính peer**.

### 6.1. Những cách xác thực key agreement

| Cơ chế | Vai trò | Điều phải kiểm tra |
| --- | --- | --- |
| **Certificate + chữ ký số** | Bên có private signing key được xác thực ký lên phần handshake/transcript theo giao thức | Chuỗi tin cậy, hostname/identity, key usage, thời hạn, chính sách thu hồi và chữ ký |
| **Pre-shared key (PSK)** | Hai bên có trước bí mật chung để xác thực hoặc tham gia key schedule | Cấp phát và bảo vệ PSK, gắn vào đúng danh tính, chống replay theo giao thức |
| **Authenticated static public key** | Khóa public dài hạn được cấu hình an toàn, dùng theo giao thức phù hợp | Chống bị thay khóa, có quy trình rotation/revocation |
| **Authenticated key exchange chuẩn hóa** | Giao thức kết hợp key agreement, xác thực transcript và khẳng định khóa | Dùng implementation đúng chuẩn thay vì ghép tùy ý primitive |

**Chữ ký số thường xác thực handshake, không trực tiếp cung cấp tính bí mật của session key.** Việc dùng private key ký chỉ chứng minh quyền sử dụng signing key ở bước được thiết kế; ECDH và KDF vẫn đảm nhiệm phần tạo khóa phiên.

### 6.2. Transcript binding và key confirmation

**Transcript** là tập thông điệp bắt tay theo một quy ước có thứ tự, gồm lựa chọn thuật toán, public keys và các giá trị liên quan. Nếu giao thức không ràng buộc xác thực hoặc KDF với transcript, kẻ tấn công có thể có cơ hội **thay đổi thuật toán, thay vai trò hoặc ghép thông điệp từ phiên khác**.

**Key confirmation** là cơ chế giúp một bên có bằng chứng rằng bên kia thực sự có khóa phiên đúng, ví dụ thông qua bản tin xác thực bằng khóa vừa dẫn xuất. Nó **không thay thế xác thực danh tính**: hai bên đều có thể xác nhận đã chia sẻ khóa với Mallory nếu bước xác thực ban đầu thất bại.

**Unknown key-share (UKS)** là ví dụ lỗi giao thức khi hai phía có cùng khóa nhưng một phía hiểu sai danh tính người đồng sở hữu khóa. Việc đưa role, danh tính đã xác thực và transcript vào các phép kiểm tra phù hợp giúp ngăn những nhầm lẫn như vậy.

### 6.3. Tại sao TLS 1.3 đáng dùng hơn việc tự viết handshake?

Một ứng dụng Java thông thường nên sử dụng **TLS 1.3** qua các API TLS/HTTPS đã được kiểm chứng, thay vì tự xây giao thức từ X25519 + HKDF + AES-GCM.

TLS 1.3 phối hợp:

- Thỏa thuận khóa (thường là ECDHE hoặc lựa chọn nhóm do hai bên hỗ trợ).
- Xác thực máy chủ qua chứng chỉ và chữ ký handshake, hoặc phương thức xác thực được giao thức cho phép.
- Key schedule có ràng buộc bản ghi handshake.
- Khóa traffic khác nhau theo hướng và giai đoạn của phiên.
- Mã hóa có xác thực và quản lý nonce theo quy tắc.
- Cơ chế phát hiện lỗi, xác thực kết thúc handshake và thay khóa traffic.

**TLS 1.3 không dùng public RSA key của chứng chỉ để mã hóa toàn bộ dữ liệu phiên.** Chứng chỉ có thể được dùng để xác thực; session key thường được thiết lập từ thỏa thuận khóa và key schedule.

## 7. Static, ephemeral key agreement và forward secrecy

### 7.1. Khóa dài hạn và khóa tạm thời

- **Static (long-term) key pair:** cặp khóa có thể được giữ qua nhiều kết nối hoặc một giai đoạn vận hành. Nếu private key bị lộ, các phiên phụ thuộc có thể chịu rủi ro trong phạm vi thiết kế.
- **Ephemeral key pair:** cặp khóa được tạo cho một phiên hoặc phạm vi rất ngắn rồi hủy khi không còn cần. Các phiên khác sử dụng vật liệu khóa mới.
- **Static-ephemeral / ephemeral-static:** một bên dùng khóa dài hạn, bên kia dùng khóa tạm thời. Bảo đảm an toàn và forward secrecy **phụ thuộc giao thức**, không suy luận chỉ từ tên của hai loại khóa.
- **Ephemeral-ephemeral:** hai bên đều dùng khóa tạm thời; khi được xác thực đúng, thường là thành phần quan trọng của các giao thức muốn có forward secrecy.

### 7.2. Forward secrecy là gì?

**Forward secrecy (FS)** là thuộc tính mà việc lộ một số bí mật dài hạn ở thời điểm sau **không làm lộ các session keys của những phiên trước**, theo mô hình bảo mật của giao thức. Ví dụ, với phiên ECDHE có khóa tạm thời được hủy an toàn, việc lộ private signing key của máy chủ sau này **không tự cho phép giải mã những kết nối ECDHE đã ghi lại**, nếu bí mật tạm thời và session keys cũ không bị lộ.

Cần phân biệt:

- FS **không** có nghĩa người đang chiếm máy chủ ở thời điểm hiện tại không đọc được plaintext đang được xử lý.
- FS **không** bảo vệ phiên cũ nếu session keys hoặc ephemeral private keys cũ đã bị lưu và lộ.
- FS **không** bảo đảm tính bí mật của bản dữ liệu dài hạn đã được giải mã và lưu lại nơi khác.
- FS **không** xuất hiện chỉ vì dùng HKDF hoặc đổi khóa chứng chỉ.
- FS **không** tự khắc phục lỗi xác thực đối tác, replay hoặc downgrade.

Nếu hệ thống lưu toàn bộ ephemeral private keys để “debug”, thuộc tính forward secrecy kỳ vọng có thể không còn đúng với các phiên đó.

### 7.3. Rotation và rekey không giống nhau

| Hoạt động | Mục đích | Tác động |
| --- | --- | --- |
| **Ephemeral key generation** | Có vật liệu khóa mới cho phiên/bắt tay | Giảm sự phụ thuộc vào một khóa dài hạn khi giao thức hỗ trợ |
| **Traffic key update / rekey** | Dẫn xuất hoặc thiết lập khóa mới cho lưu lượng đang chạy | Giới hạn thời gian và dung lượng bảo vệ dưới một khóa |
| **Rotation signing certificate/key** | Thay khóa xác thực danh tính server/client | Cần cập nhật chứng chỉ, trust chain và chính sách tin cậy |
| **Rotation KEK trong KMS** | Thay khóa bọc DEK tại tầng dữ liệu | Không tự thay session keys của ECDH/TLS |
| **Re-encrypt dữ liệu lưu trữ** | Đổi DEK hoặc bản mã dữ liệu dài hạn | Không thể thay bằng một bước key agreement của kết nối mạng |

Trong nhiều hệ thống, khóa chứng chỉ, khóa thỏa thuận, traffic keys và DEK của database có **vòng đời khác nhau**. Gộp tất cả dưới một lịch rotation hoặc quyền quản trị chung có thể gây mất an toàn hoặc gián đoạn.

## 8. Ví dụ Java 17: X25519 và HKDF-SHA256

Ví dụ sau tạo cặp khóa X25519 tạm thời cho Alice và Bob, tính shared secret ở hai phía và dẫn xuất khóa AES-256 với **HKDF-SHA256**. Chương trình chỉ in **độ dài** và **kết quả so sánh**, không in private key, shared secret hoặc derived key.

Đây là **demo về nguyên lý thỏa thuận khóa**. Alice và Bob chạy trong cùng một tiến trình; mã **chưa xác thực peer qua chứng chỉ, chữ ký hoặc PSK**, chưa triển khai giao thức hoàn chỉnh, không nên dùng làm kênh bảo mật production. Với giao tiếp ứng dụng thật, dùng API **TLS 1.3** phù hợp.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
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

public final class KeyAgreementDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String HMAC = "HmacSHA256";

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();

        // Demo: trao đổi public keys. Production phải xác thực peer
        // và transcript trước khi tin session keys.
        byte[] aliceSecret = agree(alice.getPrivate(), bob.getPublic());
        byte[] bobSecret = agree(bob.getPrivate(), alice.getPublic());

        byte[] salt = new byte[32];
        RNG.nextBytes(salt); // Giá trị công khai, hai bên dùng giống nhau.

        // Transcript theo cùng thứ tự client trước server.
        byte[] transcript = transcriptHash(
            alice.getPublic().getEncoded(),
            bob.getPublic().getEncoded());

        byte[] aliceToBobA = null;
        byte[] aliceToBobB = null;
        byte[] bobToAliceA = null;
        byte[] bobToAliceB = null;
        try {
            aliceToBobA = deriveAesKey(
                aliceSecret, salt, transcript, "client-to-server");
            aliceToBobB = deriveAesKey(
                bobSecret, salt, transcript, "client-to-server");

            bobToAliceA = deriveAesKey(
                aliceSecret, salt, transcript, "server-to-client");
            bobToAliceB = deriveAesKey(
                bobSecret, salt, transcript, "server-to-client");

            System.out.println(
                "Shared secrets match: " +
                MessageDigest.isEqual(aliceSecret, bobSecret));
            System.out.println(
                "Client-to-server keys match: " +
                MessageDigest.isEqual(aliceToBobA, aliceToBobB));
            System.out.println(
                "Server-to-client keys match: " +
                MessageDigest.isEqual(bobToAliceA, bobToAliceB));
            System.out.println(
                "Directions have distinct keys: " +
                !Arrays.equals(aliceToBobA, bobToAliceA));
            System.out.println(
                "Derived AES key length: " + aliceToBobA.length);
        } finally {
            Arrays.fill(aliceSecret, (byte) 0);
            Arrays.fill(bobSecret, (byte) 0);
            if (aliceToBobA != null) Arrays.fill(aliceToBobA, (byte) 0);
            if (aliceToBobB != null) Arrays.fill(aliceToBobB, (byte) 0);
            if (bobToAliceA != null) Arrays.fill(bobToAliceA, (byte) 0);
            if (bobToAliceB != null) Arrays.fill(bobToAliceB, (byte) 0);
        }
    }

    private static byte[] agree(PrivateKey self, PublicKey peer)
            throws Exception {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(self);
        agreement.doPhase(peer, true);
        byte[] secret = agreement.generateSecret();

        // Phòng vệ đối với kết quả X25519 toàn zero.
        if (MessageDigest.isEqual(secret, new byte[secret.length])) {
            Arrays.fill(secret, (byte) 0);
            throw new SecurityException("Invalid shared secret");
        }
        return secret;
    }

    private static byte[] transcriptHash(
            byte[] clientPublic, byte[] serverPublic) throws Exception {
        byte[] context = "key-agreement-demo/v1"
            .getBytes(StandardCharsets.UTF_8);

        // Length-prefix để hai phía tạo cùng các byte transcript.
        ByteBuffer data = ByteBuffer.allocate(
            12 + context.length + clientPublic.length + serverPublic.length);
        data.putInt(context.length).put(context);
        data.putInt(clientPublic.length).put(clientPublic);
        data.putInt(serverPublic.length).put(serverPublic);

        return MessageDigest.getInstance("SHA-256").digest(data.array());
    }

    private static byte[] deriveAesKey(
            byte[] sharedSecret,
            byte[] salt,
            byte[] transcript,
            String direction) throws Exception {

        // HKDF-Extract, dùng HMAC-SHA256.
        Mac mac = Mac.getInstance(HMAC);
        mac.init(new SecretKeySpec(salt, HMAC));
        byte[] prk = mac.doFinal(sharedSecret);

        try {
            // HKDF-Expand một block T(1) cho L = 32 byte.
            // Nhãn chỉ là ví dụ, không phải nhãn của TLS 1.3.
            byte[] label = ("demo/v1|X25519|AES-256-GCM|" + direction)
                .getBytes(StandardCharsets.UTF_8);
            mac.init(new SecretKeySpec(prk, HMAC));
            mac.update(label);
            mac.update(transcript);
            mac.update((byte) 1);
            return mac.doFinal(); // 32 byte.
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }
}
~~~

**Kết quả dự kiến:**

~~~text
Shared secrets match: true
Client-to-server keys match: true
Server-to-client keys match: true
Directions have distinct keys: true
Derived AES key length: 32
~~~

### 8.1. Điều gì đáng chú ý trong ví dụ?

1. **X25519** giúp hai bên tính cùng shared secret mà không cần gửi private key hoặc shared secret qua mạng.
2. Java **KeyAgreement** nhận private key của bên mình và public key của đối tác; không dùng private key để ký, không dùng public key để giải mã.
3. Kết quả shared secret được đưa qua **HKDF-Extract/Expand**, rồi tách thành hai khóa cho hai hướng dữ liệu.
4. **Transcript hash** gắn kết các public key và phiên bản trong ví dụ, nhưng **chưa tạo ra xác thực danh tính**; kẻ đứng giữa vẫn có thể tạo hai transcript/phiên khác nhau.
5. Salt của HKDF được tạo ngẫu nhiên và là **giá trị công khai** cần đồng bộ giữa hai phía.
6. Hai derived keys có **32 byte**, nhưng việc dùng chúng với AES-GCM vẫn yêu cầu nonce không trùng dưới từng khóa, AAD, tag và giới hạn dung lượng/thời gian sử dụng.
7. Các mảng secret được xóa khi có thể. Java và provider mật mã có thể tạo bản sao nội bộ; xóa mảng **không bảo đảm** xóa sạch bí mật khỏi bộ nhớ managed runtime.

### 8.2. Ranh giới giữa minh họa và production

Ví dụ đã bỏ qua những thành phần bắt buộc đối với một giao thức hoàn chỉnh: định danh peer, xác thực chữ ký/chứng chỉ hoặc PSK, thỏa thuận phiên bản và thuật toán an toàn, chống downgrade, chống replay, key confirmation, quản lý nonce, traffic key update, quản lý lỗi và kiểm soát quyền ứng dụng.

Nó cũng cố ý không mã hóa bản tin thực tế; mục đích là kiểm chứng **key agreement và dẫn xuất khóa**. Nếu cần truyền dữ liệu an toàn, **không đưa bộ khung này trực tiếp vào server**: dùng thư viện TLS 1.3 hoặc một giao thức được chuẩn hóa, có phân tích bảo mật và implementation phù hợp.

## 9. Key agreement liên hệ với KMS/HSM, DEK/KEK và envelope encryption

### 9.1. Key agreement tạo nguồn cho session key; envelope encryption bảo vệ data key

Trong một hệ thống có cả giao tiếp mạng và lưu trữ dữ liệu, hai luồng khóa thường tồn tại song song:

~~~mermaid
flowchart TD
    subgraph S["Giao tiếp mạng"]
        PA["Private key tạm thời A"] --> KA["ECDH + KDF"]
        PB["Public key đối tác đã xác thực"] --> KA
        KA --> SK["Session / traffic keys"]
        SK --> NET["AEAD bảo vệ lưu lượng"]
    end
    subgraph D["Lưu trữ"]
        KEK["KEK được bảo vệ trong KMS/HSM"] --> WRAP["Wrap/Unwrap"]
        DEK["DEK mã hóa dữ liệu"] --> WRAP
        DEK --> DATA["AES-GCM mã hóa bản ghi"]
        WRAP --> WDEK["Wrapped DEK lưu với ciphertext"]
    end
~~~

- **Session key** thường có vòng đời ngắn, phục vụ truyền tin và được tái tạo theo giao thức.
- **DEK** bảo vệ bản ghi/tệp lưu lâu dài, có thể cần truy cập sau nhiều năm.
- **KEK** bảo vệ DEK ở tầng quản lý khóa và có chính sách rotation/retention riêng.

Khi một session key hết hạn, không có nghĩa phải mã hóa lại toàn bộ database. Ngược lại, rotation KEK của database không tự thay các session keys của TLS.

### 9.2. Key agreement có thể tham gia thiết kế trao đổi DEK cho đối tác

Ví dụ ứng dụng cần gửi một tài liệu cho đối tác. Ứng dụng có thể tạo **DEK ngẫu nhiên** để mã hóa tài liệu, rồi dùng một **giao thức được chuẩn hóa** kết hợp key agreement/KEM, KDF và cơ chế bọc khóa để bảo vệ DEK cho public key đã xác thực của đối tác.

Các điểm cần kiểm soát:

1. Public key của người nhận phải đúng danh tính, đúng thuật toán và đúng mục đích.
2. Giao thức phải xác định vai trò sender/receiver, cách sinh ephemeral key, context và key confirmation theo mô hình an ninh.
3. Khóa dùng để **bọc DEK** cần được dẫn xuất/thiết lập theo chuẩn; không lấy thẳng shared secret làm KEK AES.
4. Wrapped DEK, ciphertext, nonce và metadata định dạng phải được lưu đủ để giải mã hợp lệ.
5. Private key của người nhận phải được bảo vệ, có thể trong **HSM/KMS** nếu hỗ trợ loại khóa và thao tác cần dùng.
6. Rotation, thu hồi hoặc mất private key người nhận có thể ảnh hưởng khả năng mở DEK được gửi từ trước.
7. Hệ thống cần phân quyền và kiểm toán thao tác unwrap/decrypt, đặc biệt với dữ liệu nhiều tenant.

**Không phải KMS/HSM nào cũng hỗ trợ X25519.** Một số chỉ hỗ trợ ECDH trên các đường cong và giao diện nhất định; cần kiểm tra tính năng và cách cấu hình của nền tảng thay vì suy đoán tất cả đều có API giống Java JCA.

### 9.3. Key agreement không thay thế quyền truy cập

Một client có thể thỏa thuận khóa an toàn với server nhưng vẫn không được phép xem hóa đơn của tenant khác. **TLS xác thực kết nối**, còn **IAM và kiểm tra nghiệp vụ** quyết định chủ thể được đọc tài nguyên nào. Tương tự, quyền gọi thao tác DeriveKey của HSM hoặc Decrypt của KMS cần được giới hạn theo principal, key ID, mục đích và chính sách.

## 10. Vòng đời khóa khi sử dụng key agreement

| Giai đoạn | Việc cần làm | Rủi ro thường gặp |
| --- | --- | --- |
| **Sinh khóa** | Dùng CSPRNG/thư viện tin cậy sinh private key tạm thời hoặc khóa dài hạn phù hợp thuật toán | Private key yếu, tái sử dụng ngoài ý định, tự chọn tham số không an toàn |
| **Cấp phát/phân phối** | Trao đổi public key; xác thực danh tính và ràng buộc transcript | MITM hoặc tráo public key |
| **Lưu trữ** | Bảo vệ private key dài hạn bằng KMS/HSM khi phù hợp; giữ ephemeral secret trong phạm vi ngắn | Private key/secret xuất hiện trong code, log, core dump, bản sao lưu |
| **Sử dụng** | Kiểm tra public value, xử lý shared secret đúng chuẩn, KDF có domain separation | Invalid public key, all-zero secret, dùng raw secret làm AES key, nonce trùng |
| **Rekey/rotation** | Định nghĩa cryptoperiod, session expiry, traffic key update, vòng đời chứng chỉ | Session tồn tại quá lâu, tiếp tục dùng khóa yếu hoặc khóa đã bị thu hồi |
| **Thu hồi** | Thu hồi cert/khóa xác thực hoặc quyền sử dụng, chặn phiên/credential liên quan | Kẻ tấn công tiếp tục xác thực và thương lượng phiên mới |
| **Hủy** | Xóa ephemeral/session secret khi không còn cần; giữ lịch sử audit không nhạy cảm | Mất forward secrecy kỳ vọng nếu lưu private key phiên; hủy khóa lưu trữ quá sớm |
| **Kiểm toán** | Ghi key ID/fingerprint, sự kiện handshake, policy change và lỗi, không ghi secret | Không truy vết được abuse hoặc tự làm lộ secret qua log |

### 10.1. Không ghi shared secret và session key vào log

Những thông tin thích hợp để audit gồm: thời gian, workload, identity đã xác thực, certificate fingerprint hoặc key ID, phiên bản giao thức, nhóm key agreement đã thương lượng, kết quả handshake, request ID và lỗi đã được chuẩn hóa. **Không ghi private key, ECDH shared secret, PRK, traffic key, DEK rõ hoặc payload nhạy cảm**.

Khi điều tra sự cố mạng, log đầy đủ nội dung bí mật để “dễ debug” có thể khiến toàn bộ lợi ích mã hóa biến mất. Sử dụng môi trường thử nghiệm, khóa thử và transcript không nhạy cảm để tái hiện lỗi.

### 10.2. Sự cố lộ khóa dài hạn

Nếu **private signing key** của server bị lộ, kẻ tấn công có thể giả mạo server trong các lần bắt tay mới cho đến khi quyền tin cậy bị chặn, mặc dù bản ghi các phiên ECDHE cũ có thể vẫn được bảo vệ bởi forward secrecy nếu điều kiện của giao thức được đáp ứng.

Nếu **static DH private key** bị lộ, phạm vi các phiên bị ảnh hưởng phụ thuộc cách dùng static/ephemeral keys. Không được tự kết luận “ECDH lúc nào cũng có forward secrecy”.

Nếu **ephemeral private key hoặc traffic key** của một phiên bị lộ, nội dung phiên đó có thể bị ảnh hưởng. Việc đổi chứng chỉ dài hạn không thể tự thu hồi những bản sao session key đã bị đánh cắp.

Quy trình ứng phó nên xác định **loại khóa bị lộ, khoảng thời gian và phiên liên quan**, vô hiệu hóa credential/khóa phù hợp, thay khóa/cert, kết thúc phiên nguy cơ, đánh giá dữ liệu đã mất bí mật và điều tra nguyên nhân.

## 11. Các lỗi thiết kế key agreement thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| **Không xác thực public key của peer** | MITM lập hai kênh hợp lệ về toán học | Certificate/signature/PSK theo giao thức được kiểm chứng |
| **Không ràng buộc transcript và danh tính** | Có thể dẫn tới downgrade, nhầm vai trò, UKS hoặc ghép phiên | Dùng authenticated key exchange chuẩn hóa, context/role/identity rõ ràng |
| **Nhận public key hoặc kết quả ECDH bất thường** | Rủi ro small-subgroup/invalid-point/all-zero tùy thuật toán | Validation và xử lý lỗi đúng chuẩn loại khóa |
| **Dùng shared secret làm AES key trực tiếp** | Thiếu key schedule, tách miền và xử lý entropy | KDF như HKDF theo giao thức |
| **Dùng cùng key/nonce cho hai hướng** | Nonce reuse có thể phá bảo mật AEAD | Khóa riêng theo hướng và quản lý nonce theo đặc tả |
| **Tái sử dụng khóa phiên quá lâu** | Phơi nhiễm nhiều dữ liệu khi khóa bị lộ, vượt giới hạn AEAD | Cryptoperiod, hạn mức dữ liệu và traffic key update |
| **Lưu private key tạm thời để debug** | Lộ khóa về sau có thể phá forward secrecy | Hủy secret sớm nhất có thể, tránh log/core dump chứa key |
| **Tin rằng KDF tự xác thực người đối diện** | Thiếu xác thực; kẻ trung gian vẫn có khóa riêng với từng phía | Xác thực identity và transcript trước khi tin khóa |
| **Tự ghép DH + RSA signature + AES-GCM thành giao thức** | Dễ bỏ sót xác thực, replay, downgrade, nonce, lỗi trạng thái | Ưu tiên TLS 1.3 hoặc giao thức chuyên dụng được phân tích |
| **Cho workload gọi KeyAgreement/DeriveKey không giới hạn** | Lạm dụng private key trong HSM hoặc tạo bí mật cho mục đích trái phép | IAM least privilege, policy theo key usage/identity, audit |
| **Cho phép client chọn thuật toán/key ID tùy ý** | Đàm phán xuống thuật toán yếu hoặc nhầm khóa | Danh sách thuật toán cố định, chính sách tin cậy và chống downgrade |
| **Chỉ kiểm tra thành công handshake rồi coi có quyền truy cập** | Truy cập tài nguyên của tenant khác | Kiểm soát quyền nghiệp vụ độc lập với bảo mật đường truyền |

### 11.1. Replay và downgrade là hai vấn đề khác nhau

**Replay:** kẻ tấn công phát lại thông điệp handshake hoặc dữ liệu cũ. Một giao thức đúng cần xác định rõ giá trị tươi mới (freshness), session ID, nonce, số thứ tự, kiểm tra trạng thái hoặc cơ chế chống replay tương ứng; dùng ECDH đơn lẻ không ngăn phát lại mọi loại thông điệp.

**Downgrade:** kẻ tấn công tìm cách khiến hai bên sử dụng phiên bản hoặc bộ thuật toán yếu hơn khả năng thực sự. Giao thức phải bảo vệ việc đàm phán bằng transcript authentication hoặc cơ chế đặc tả; “ưu tiên thuật toán mạnh” ở phía client thôi chưa đủ.

### 11.2. Khi lỗi do cấu hình hay do tấn công?

Một thất bại key agreement có thể đến từ: public key sai định dạng, hai bên chọn nhóm khác nhau, chứng chỉ hết hạn, hostname không khớp, cipher suite bị cấm, key usage không phù hợp, KDF info không giống nhau hoặc thông điệp handshake bị sửa. Cần có audit để phân biệt nguyên nhân nhưng không tiết lộ secret hoặc chi tiết nhạy cảm qua thông báo lỗi API.

## 12. Tình huống thực tế: bảo vệ API Java truy cập dữ liệu tài chính

Giả sử một ứng dụng **PaymentClient** gọi **PaymentAPI** qua Internet và mỗi giao dịch có dữ liệu bí mật. Hệ thống còn dùng KMS để bảo vệ DEK mã hóa dữ liệu lưu trữ.

**Thiết kế khuyến nghị theo vai trò:**

1. **Kênh truyền:** dùng HTTPS/TLS 1.3 thông qua stack TLS chuẩn của Java. Client xác thực chứng chỉ và danh tính máy chủ đúng hostname/trust policy; với mTLS nếu yêu cầu, máy chủ cũng xác thực chứng chỉ client.
2. **Key agreement trong TLS:** để thư viện TLS thực hiện ECDHE/KDF/handshake authentication và quản lý traffic keys. Ứng dụng không truy cập hoặc ghi log shared secret.
3. **Phân quyền nghiệp vụ:** sau xác thực, server xác minh principal có quyền thực hiện giao dịch hoặc đọc dữ liệu của tenant cụ thể.
4. **Lưu trữ:** khi ghi hóa đơn, server dùng DEK AES-GCM, AAD ràng buộc tenant/document và wrapped DEK dưới KEK trong KMS. Đây là vòng đời khóa riêng với TLS.
5. **Giám sát:** audit thất bại xác thực TLS, thay chứng chỉ, chính sách KMS, yêu cầu unwrap và truy cập tài nguyên bất thường; không ghi khóa hay plaintext nhạy cảm.
6. **Rotation:** luân chuyển chứng chỉ và khóa xác thực server theo chính sách, bảo đảm tiếp tục truy cập dữ liệu đã lưu nhờ đường đọc DEK/KEK cũ trong giới hạn lưu giữ.

~~~mermaid
flowchart LR
    C["PaymentClient"] -->|"TLS 1.3: authenticated key agreement, AEAD"| P["PaymentAPI"]
    P --> IAM["Xác thực và phân quyền tenant"]
    IAM --> APP["Xử lý nghiệp vụ"]
    APP --> K["KMS/HSM quản lý KEK"]
    APP --> DB["Database: ciphertext + wrapped DEK"]
    K -->|"Cấp quyền unwrap/generate data key"| APP
~~~

Đặc điểm quan trọng: **bảo mật kết nối không tự bảo vệ database sau khi dữ liệu được ghi**, và **envelope encryption của database không tự xác thực người dùng trên đường truyền**. Hai lớp có nhiệm vụ và vòng đời khóa riêng.

## 13. Checklist khi thiết kế key agreement

Trước khi dùng một cơ chế thỏa thuận khóa trong sản phẩm, hãy trả lời:

1. **Giao thức:** có thể dùng TLS 1.3 hoặc giao thức chuẩn hiện có không? Ai chịu trách nhiệm cập nhật thư viện và cấu hình?
2. **Thuật toán:** nhóm DH/ECDH/KEM nào được phép, tham số có chuẩn và đủ mạnh theo chính sách hiện tại không?
3. **Xác thực:** public key của peer được ràng buộc với danh tính đúng bằng chứng chỉ, chữ ký hoặc PSK thế nào?
4. **Public-key validation:** xử lý public value không hợp lệ và shared secret bất thường theo đúng thuật toán chưa?
5. **Transcript:** thuật toán, public keys, vai trò và danh tính có được ràng buộc đúng trong handshake và key schedule không?
6. **KDF:** shared secret có qua KDF phù hợp, nhãn/role/context xác định và output length đúng thuật toán không?
7. **Key separation:** hai hướng truyền và mục đích khác nhau có dùng khóa khác nhau? Nonce/IV có được quản lý đúng không?
8. **Forward secrecy:** có dùng ephemeral keys và hủy đúng bí mật tạm thời khi giao thức yêu cầu không?
9. **Key lifecycle:** cryptoperiod, session expiry, rekey, cert/key rotation, thu hồi và xử lý phiên đang chạy được thiết kế chưa?
10. **KMS/HSM:** nếu private key được dùng trong KMS/HSM, API có hỗ trợ thuật toán không, ai có quyền gọi, có bảo vệ và audit đúng không?
11. **Business authorization:** việc một peer đã xác thực có được ánh xạ tới quyền truy cập tài nguyên/tenant cụ thể không?
12. **Incident response:** nếu private key, signing key, ECDH secret hoặc session key bị lộ, có xác định được phạm vi sự cố và các hành động cần thiết không?
13. **Logging:** có tránh log secret/traffic keys, đồng thời thu thập đủ thông tin không nhạy cảm để điều tra không?
14. **Recovery:** việc mất hay thu hồi khóa xác thực kết nối có ảnh hưởng đến khả năng giải mã các bản ghi lưu lâu dài không? Nếu có, có kế hoạch chuyển đổi phù hợp chưa?

### Câu hỏi tự kiểm tra

**Câu 1.** Alice và Bob thực hiện ECDH và cùng thu được một shared secret. Điều đó đã chứng minh Alice thật sự kết nối tới Bob chưa?

**Đáp án:** Chưa. ECDH không tự xác thực danh tính; nếu bị MITM, Alice có thể chia sẻ bí mật với kẻ tấn công. Cần xác thực public key/handshake theo giao thức.

**Câu 2.** Có nên dùng trực tiếp 32 byte đầu của kết quả X25519 làm AES-256 key cho cả hai hướng truyền?

**Đáp án:** Không. Shared secret cần qua KDF/key schedule có context và domain separation phù hợp; thiết kế nên tách traffic keys theo hướng và quản lý nonce theo giao thức.

**Câu 3.** Vì sao public key X25519 có thể gửi công khai mà vẫn phải xác thực?

**Đáp án:** Tính công khai chỉ nói khóa không cần giữ bí mật. Xác thực giúp bảo đảm khóa thuộc đúng đối tác, tránh việc attacker thay public key để tạo shared secret với mình.

**Câu 4.** Private signing key của máy chủ TLS bị lộ sau một năm. Có chắc kẻ tấn công giải mã được toàn bộ phiên TLS 1.3 từng ghi lại không?

**Đáp án:** Không. Các phiên ECDHE trước đó có thể được bảo vệ bởi forward secrecy nếu ephemeral/session secrets không bị lộ và giao thức được triển khai đúng. Tuy nhiên, kẻ tấn công có thể giả mạo trong các phiên mới cho đến khi khóa/chứng chỉ bị thu hồi hoặc thay thế theo chính sách.

**Câu 5.** Có được dùng public key Ed25519 để gọi X25519 KeyAgreement trực tiếp không?

**Đáp án:** Không. Ed25519 là thuật toán chữ ký, X25519 phục vụ key agreement; phải dùng đúng loại khóa/thuật toán và cơ chế chuyển đổi được đặc tả nếu một giao thức thực sự yêu cầu, không đổi định danh tùy tiện.

**Câu 6.** Nếu session key của kết nối mạng bị rotation, DEK mã hóa hóa đơn lưu trong database có tự thay đổi không?

**Đáp án:** Không. Session key bảo vệ lưu lượng; DEK và KEK bảo vệ dữ liệu lưu trữ có vòng đời riêng. Muốn thay DEK của hóa đơn cần quy trình mã hóa lại hoặc di chuyển dữ liệu theo thiết kế.

**Câu 7.** Một HSM giữ private key không xuất được. Vì sao vẫn phải giới hạn quyền gọi KeyAgreement/DeriveKey?

**Đáp án:** Tài khoản bị chiếm có thể lạm dụng **quyền sử dụng private key** để tham gia các phiên hoặc dẫn xuất vật liệu khóa trái phép mà không cần xuất private key. Cần IAM, giới hạn mục đích, xác thực workload và audit.

## Kết luận

**Key agreement là cách các bên thiết lập bí mật chung mà không cần gửi bí mật đó trực tiếp qua mạng.** DH/ECDH/X25519 giải quyết phần toán học; **KDF** biến shared secret thành khóa có mục đích và ngữ cảnh rõ; **xác thực** ngăn tin nhầm public key của kẻ tấn công; **AEAD** dùng các khóa đã dẫn xuất để bảo vệ lưu lượng.

Một thiết kế an toàn còn phải quản lý **sinh khóa, lưu trữ private key, phân quyền KMS/HSM, vòng đời ephemeral/session keys, rotation, thu hồi, hủy và kiểm toán**. Thông thường, ứng dụng Java nên dùng TLS 1.3 và thư viện đã được kiểm chứng cho truyền thông, còn DEK/KEK của dữ liệu lưu trữ được quản trị bằng envelope encryption và KMS/HSM theo mục đích riêng. **Thỏa thuận được cùng một khóa chưa đủ; hai bên còn phải biết họ đang thỏa thuận với ai và được phép dùng khóa đó vào việc gì.**
