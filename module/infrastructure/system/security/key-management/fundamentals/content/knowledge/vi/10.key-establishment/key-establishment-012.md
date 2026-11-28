# Forward secrecy: bảo vệ dữ liệu phiên cũ khi khóa dài hạn bị lộ

## 1. Forward secrecy giải quyết rủi ro nào?

Một hệ thống thương mại điện tử có **OrderService** giao tiếp với **PaymentService** bằng TLS. Kẻ tấn công chưa thể giải mã đường truyền nhưng đã âm thầm ghi lại các gói tin mã hóa trong nhiều tháng. Về sau, private key dùng để **xác thực danh tính máy chủ** bị lộ qua lỗi vận hành. Một câu hỏi rất thực tế xuất hiện:

**Kẻ tấn công có thể lấy khóa dài hạn vừa bị lộ để giải mã toàn bộ lưu lượng đã ghi lại từ nhiều tháng trước không?**

Câu trả lời phụ thuộc vào **cơ chế key establishment và vòng đời các bí mật phiên**. Nếu giao thức sử dụng **ephemeral Diffie–Hellman** đúng cách, xác thực phiên đầy đủ và các secret tạm thời trước đó không bị giữ lại/lộ, việc chiếm được **khóa xác thực dài hạn sau này** thường **không đủ** để khôi phục các khóa traffic cũ.

Đó là ý nghĩa trọng tâm của **forward secrecy (FS)**, còn thường được gọi là **perfect forward secrecy (PFS)** trong nhiều tài liệu lịch sử.

> **Forward secrecy là thuộc tính bảo mật của giao thức thiết lập khóa: việc lộ những bí mật dài hạn nhất định ở tương lai không tự làm lộ khóa phiên của các phiên đã kết thúc, trong mô hình đe dọa được xác định.**

Điểm quan trọng nằm ở các từ **“những bí mật dài hạn nhất định”** và **“không tự làm lộ”**. FS **không** nói rằng có thể bị đánh cắp mọi khóa, mọi secret phiên hoặc toàn bộ máy chủ mà dữ liệu quá khứ vẫn an toàn.

### Mô hình tấn công “record now, decrypt later”

~~~text
THỜI ĐIỂM T1                             THỜI ĐIỂM T2
Client <--- TLS session cũ ---> Server   Private signing key của server bị lộ
                 |
        Kẻ tấn công ghi lại
        ciphertext trên mạng
                 |
                 v
     Dữ liệu lưu ở phía attacker
                 |
                 +---- Với forward secrecy được thiết kế đúng:
                       signing key bị lộ ở T2 không đủ
                       để tái dựng session key của T1.
~~~

Không có FS, một số mô hình key establishment cũ có thể khiến **private key dài hạn** trở thành bí mật dùng để giải lại vật liệu khóa của các phiên đã ghi. FS là lớp phòng vệ nhằm giảm rủi ro từ kiểu tấn công lưu dữ liệu mã hóa để chờ một khóa lâu dài bị lộ về sau.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác **forward secrecy**, phạm vi và giả định của nó.
2. Phân biệt **ephemeral key**, **static key**, **signing key**, **ECDH shared secret**, **traffic key** và **DEK/KEK**.
3. Phân tích tại sao **ECDHE** thường hỗ trợ FS còn một số cách vận chuyển khóa dùng private key dài hạn thì không.
4. Hiểu **authenticated key establishment**, xác thực chống MITM và vai trò của **KDF/key schedule**.
5. Nhận diện các điểm cần chú ý trong **TLS 1.3**, **PSK**, **session resumption**, **0-RTT early data** và key update.
6. Phân biệt **forward secrecy** với **post-compromise security**, rotation, key erasure và chống replay.
7. Đọc ví dụ Java 17 về **X25519 theo từng phiên** và cách dùng **HttpClient với TLS 1.3**.
8. Thiết kế kiểm soát **KMS/HSM, IAM, quản lý vòng đời khóa, bảo mật bộ nhớ, audit và ứng phó sự cố**.

## 2. Nơi forward secrecy xuất hiện trong key establishment

**Key establishment** là quá trình những bên được phép thiết lập vật liệu khóa sử dụng trong giao thức. **Key agreement**, chẳng hạn **Diffie–Hellman (DH)** hoặc **Elliptic-Curve Diffie–Hellman (ECDH)**, là một cơ chế tạo shared secret mà các phía tính được từ private key của mình và public key đối tác.

FS không phải thuật toán ký, mã hóa hoặc hàm băm riêng. Nó là **thuộc tính của cách giao thức tạo, sử dụng, thay đổi và hủy khóa**.

| Thuật ngữ | Vai trò trong kết nối | Liên quan đến FS |
| --- | --- | --- |
| **Long-term signing private key** | Xác thực danh tính máy chủ/đối tác qua chữ ký trên handshake | Lộ về sau không nên tự giải được khóa phiên ECDHE cũ nếu FS đúng |
| **Static DH private key** | Tham gia key agreement qua nhiều phiên | Lộ khóa có thể ảnh hưởng dữ liệu lịch sử, tùy giao thức |
| **Ephemeral DH/ECDH private key** | Bí mật tạm thời cho một phiên/handshake | Cần hủy đúng lúc để giữ bảo đảm FS của phiên đó |
| **Public DH/ECDH key** | Thông tin công khai được trao đổi | Có thể bị ghi lại; phải được ràng buộc vào handshake đã xác thực |
| **Shared secret** | Kết quả DH/ECDH giữa các bên | Không được log, xuất tùy ý hoặc giữ lâu hơn cần thiết |
| **KDF / key schedule** | Dẫn xuất traffic secrets/keys từ vật liệu khóa và context | Phải dùng đúng chuẩn; không tự tạo FS nếu nguồn secret dài hạn vẫn bị lộ |
| **Traffic key** | Khóa bảo vệ thông điệp đang truyền | Lộ trực tiếp thì FS không thể bảo vệ các thông điệp thuộc khóa đó |
| **DEK/KEK dữ liệu lưu trữ** | Mã hóa và bọc khóa của file/database | Có vòng đời khác; FS của phiên TLS không bảo vệ chúng khi bị lộ |

**Cần phân biệt key agreement và key transport.** Với một cơ chế vận chuyển khóa cũ, client có thể tạo secret rồi mã hóa secret đó bằng public key RSA dài hạn của server. Nếu attacker lưu ciphertext chứa secret rồi sau này lấy được private key RSA của server, họ có thể giải ra secret cũ và tái tạo khóa phiên theo giao thức. Cách đó **không có FS trước việc private RSA key bị lộ**.

Ngược lại, trong một phiên **ECDHE được xác thực**, private signing key dài hạn chỉ xác thực các public key ephemeral hoặc transcript. Nó **không phải secret toán học trực tiếp** dùng để khôi phục ECDHE shared secret đã được tính từ private ephemeral keys khác nhau.

## 3. Ephemeral Diffie–Hellman đem lại điều gì?

### 3.1. Hai bên tạo bí mật tạm thời

Một phiên key agreement dựa trên ECDHE có dạng khái niệm:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>C: Sinh ephemeral private c và public C
    S->>S: Sinh ephemeral private s và public S
    C->>S: Public key C và thông điệp handshake
    S-->>C: Public key S và bằng chứng xác thực danh tính
    C->>C: Xác minh danh tính và transcript theo giao thức
    Note over C,S: Tính shared secret từ private ephemeral và public peer
    C->>C: ECDH(c, S) => secret phiên
    S->>S: ECDH(s, C) => cùng secret phiên
    Note over C,S: Key schedule gắn transcript và role
    C->>C: Dẫn xuất traffic keys
    S->>S: Dẫn xuất traffic keys
    Note over C,S: Bảo vệ thông điệp với AEAD
    C->>C: Hủy private c và secret khi không cần
    S->>S: Hủy private s và secret khi không cần
~~~

Private key tạm thời **c** và **s** không cần xuất hiện trên mạng. Kẻ quan sát chỉ thấy public key và các trường bắt tay được phép công khai.

Khi phiên đã kết thúc, nếu hai private ephemeral keys và session key material đã được hủy, một private signing key dài hạn bị lộ sau đó **không tự cung cấp giá trị ECDH(c, S)**. Bảo đảm này vẫn cần giả định thuật toán khó bị phá và bên thực thi không làm lộ các secret tạm thời.

### 3.2. ECDHE không đồng nghĩa “tự động an toàn”

**E** trong ECDHE nhấn mạnh dùng các giá trị **ephemeral**. Nhưng chỉ đặt tên biến là ephemeral chưa đủ:

- Mỗi phiên phải có key material được tạo **đúng quy tắc**, độc lập khi thiết kế yêu cầu.
- Dùng **CSPRNG** và thư viện DH/ECDH đáng tin.
- Kiểm tra public key/nhóm/kết quả thỏa thuận theo thuật toán.
- **Xác thực peer** để tránh man-in-the-middle (MITM).
- Ràng buộc public keys, thuật toán và danh tính với transcript theo giao thức.
- Dẫn xuất khóa traffic bằng KDF/key schedule, tách chiều và mục đích.
- Giới hạn thời gian giữ private ephemeral key, shared secret và traffic keys trong bộ nhớ.
- Không lưu lại những bí mật đó trong log, trace, crash dump hay cấu hình debug.
- Kết thúc phiên và xóa bí mật đúng lúc, trong phạm vi có thể của runtime.

Đặc biệt, **forward secrecy không đồng nghĩa chống MITM**. Nếu attacker thay public key chưa xác thực, họ có thể tạo hai phiên ECDHE hợp lệ về toán học và đọc dữ liệu ngay tại thời điểm truyền.

### 3.3. Minh họa hai phiên độc lập

~~~text
Phiên A:
  ephemeral client A + ephemeral server A
       └─ ECDH ─> secret A ─> KDF ─> traffic keys A

Phiên B:
  ephemeral client B + ephemeral server B
       └─ ECDH ─> secret B ─> KDF ─> traffic keys B

Lộ signing key của server sau khi A và B đã kết thúc
không tự suy ra ephemeral secrets/traffic keys A, B.
~~~

Đây là **sự tách biệt của secret theo phiên**, khác với việc lấy một **root secret dài hạn** rồi chỉ đổi nhãn HKDF để tạo hai traffic keys. Nếu attacker lấy root secret dài hạn, họ có thể tái tạo khóa dẫn xuất cho các phiên cũ khi biết salt/context công khai. Một KDF tốt **không thể tự sinh FS** khi toàn bộ tính bí mật của các phiên đều dựa vào cùng một secret lâu dài còn được giữ.

## 4. So sánh có và không có forward secrecy

### 4.1. Ví dụ key transport không có FS

Trong một kiểu key transport dùng RSA lâu dài trước đây:

~~~text
Client:
  tạo premaster secret ngẫu nhiên
  RSA-Encrypt(server long-term RSA public key, premaster secret)
                      |
                      v
Server:
  RSA-Decrypt(server long-term RSA private key, ciphertext)
  KDF(premaster secret, transcript, ...) -> session keys

Attacker:
  ghi encrypted premaster secret và traffic
  nhiều tháng sau lấy server long-term RSA private key
  -> có thể giải premaster secret cũ, tái tạo session keys cũ
~~~

Đây là **mô hình minh họa một kiểu RSA key transport lịch sử**, không mô tả các bước hiện tại của TLS 1.3. TLS 1.3 **không sử dụng RSA key transport**.

### 4.2. Ví dụ ECDHE có FS đối với signing key

~~~text
Client <---- authenticated ECDHE ----> Server
  private ephemeral client             private ephemeral server
           |                                       |
           +-- ECDH shared secret + key schedule --+
                               |
                    session traffic keys
                               |
                     Hủy secret tạm thời

Attacker lưu toàn bộ public ECDHE handshake và traffic.
Sau này attacker có private signing key lâu dài của server.
=> Chỉ từ signing key đó và bản ghi mạng, thường không suy ra
   private ephemeral keys hoặc shared secret của phiên cũ.
~~~

**Đừng suy rộng** rằng mọi thứ bị lấy cắp ở tương lai đều không làm lộ quá khứ. Nếu attacker lấy được **ephemeral private key, ECDH shared secret, traffic secret hoặc plaintext** của phiên cũ, dữ liệu thuộc phiên đó có thể vẫn bị lộ.

### 4.3. Bảng so sánh theo loại bí mật bị xâm phạm

| Bí mật bị lộ **sau khi phiên kết thúc** | Với authenticated ECDHE và xóa secret đúng | Diễn giải |
| --- | --- | --- |
| **Long-term signing private key** | Có thể vẫn bảo vệ traffic cũ | Đây là một mục tiêu trung tâm của FS |
| **Ephemeral private key của phiên cũ** | Traffic phiên đó có thể bị ảnh hưởng | Bên ghi traffic/public key có thể suy ra secret phiên tùy giao thức |
| **Traffic key hoặc traffic secret cũ** | Traffic tương ứng có thể bị lộ | FS không bảo vệ khỏi việc bị lấy trực tiếp khóa phiên |
| **Plaintext đã lưu ở endpoint** | Plaintext đã lộ | FS không giải quyết việc endpoint lưu hoặc để lộ dữ liệu |
| **Static DH private key** | Phụ thuộc giao thức | Không kết luận chung từ tên ECDH |
| **PSK dài hạn** | Phụ thuộc chế độ/key schedule | Một số chế độ PSK không có FS; PSK+DHE có thể có FS |
| **DEK của database** | Dữ liệu database có thể bị lộ | Đây là khóa lưu trữ, không phải traffic key TLS |
| **KEK KMS của database** | Wrapped DEKs/dữ liệu có thể chịu rủi ro | FS mạng không thay thế envelope encryption |

## 5. Forward secrecy là thuộc tính có điều kiện

### 5.1. Các giả định cần nói rõ

Khi tuyên bố “hệ thống có forward secrecy”, phải xác định:

1. **Bí mật dài hạn nào** có thể bị lộ mà lịch sử vẫn được bảo vệ?
2. **Phiên nào** được coi là đã kết thúc và đã xóa secret?
3. **Đối tượng attacker quan sát được** là traffic, handshake, chứng chỉ hay dữ liệu lưu trữ nào?
4. **Có bí mật phiên nào bị lộ** trong hoặc sau phiên không?
5. **Có trust và xác thực peer đúng** tại thời điểm handshake không?
6. **KDF/key schedule** có ràng buộc transcript và tách miền sử dụng đúng không?
7. **Có nguồn bí mật dài hạn khác** (PSK, session ticket key, shared root, exported key) ảnh hưởng tới key schedule không?
8. **Implementation có lưu khóa** trong log, memory dump, key log file, telemetry hoặc backup không?

Không có mô hình đe dọa, câu “PFS bảo vệ mọi dữ liệu đã mã hóa” là quá rộng và sai.

### 5.2. “Perfect” không có nghĩa bất khả xâm phạm tuyệt đối

Thuật ngữ **perfect forward secrecy** có từ lâu trong tài liệu giao thức, nhưng “perfect” **không** có nghĩa rằng:

- Dữ liệu vẫn bí mật khi attacker đã có session key.
- Thuật toán không bao giờ bị phá.
- Mọi endpoint đều an toàn trước malware.
- Bản mã cũ không thể bị giải mã nếu máy chủ ghi lại plaintext.
- Việc lộ root secret của một thiết kế tự chế chắc chắn vô hại.

Trong bài này, dùng thuật ngữ **forward secrecy (FS)** và luôn nêu rõ **trước loại xâm phạm nào, với điều kiện nào**.

### 5.3. Authentication vẫn bắt buộc

ECDHE đơn lẻ giúp hai bên tính cùng secret. Nếu public key được thay trên đường truyền, attacker có thể thương lượng secret với từng phía. Cần **authenticated key establishment** như TLS 1.3 với xác minh chứng chỉ/hostname, hoặc phương thức xác thực thích hợp theo giao thức.

Việc một phiên có khả năng FS đối với **lộ signing key về sau** không thể bù cho tình huống attacker **giả mạo peer ngay từ đầu**.

## 6. Forward secrecy trong TLS 1.3

**TLS 1.3** là ví dụ tiêu biểu của giao thức kết hợp **key establishment, xác thực, key schedule và AEAD**. Tuy nhiên, không được kết luận **mọi chế độ, mọi loại dữ liệu TLS 1.3 đều tự động có FS**.

### 6.1. Full handshake dựa trên (EC)DHE

Trong một kết nối TLS 1.3 thông thường sử dụng (EC)DHE, client và server trao đổi key share tạm thời; kết quả thỏa thuận được đưa vào key schedule theo quy tắc giao thức. Chứng chỉ/chữ ký của máy chủ dùng để xác thực handshake, **không dùng private signing key làm khóa giải mã traffic**.

Các yếu tố thường gặp:

- (EC)DHE hoặc nhóm key establishment được giao thức quy định.
- **Transcript hash** ràng buộc những thông điệp bắt tay quan trọng.
- **HKDF-based key schedule** theo nhãn/secret riêng của TLS 1.3.
- Traffic keys tách theo hướng gửi–nhận và giai đoạn handshake/application.
- Bản tin **Finished** kiểm tra hoàn tất handshake theo key schedule.
- AEAD và cách tạo nonce/sequence đã được giao thức quy định.

~~~mermaid
sequenceDiagram
    participant C as TLS Client
    participant S as TLS Server
    C->>C: Sinh ephemeral key share
    C->>S: ClientHello + key_share C
    S->>S: Sinh ephemeral key share
    S-->>C: ServerHello + key_share S
    Note over C,S: (EC)DHE shared secret + TLS 1.3 key schedule
    S-->>C: Thông điệp xác thực máy chủ theo TLS
    S-->>C: Finished
    C->>C: Xác minh chain/identity/handshake/Finished
    C->>S: Finished
    Note over C,S: Application traffic qua AEAD
    C->>C: Hủy ephemeral/traffic material khi không còn cần
    S->>S: Hủy ephemeral/traffic material khi không còn cần
~~~

Sơ đồ lược bỏ các trường và thông điệp chi tiết; không nên coi nó là thứ tự byte-level hoặc bản đặc tả đầy đủ của mọi nhánh handshake TLS 1.3.

### 6.2. PSK-only và PSK+DHE không giống nhau

TLS 1.3 hỗ trợ **Pre-Shared Key (PSK)**, bao gồm PSK gắn với cơ chế **session resumption**. Điểm cần phân biệt:

| Chế độ key establishment | Forward secrecy đối với lộ PSK sau này |
| --- | --- |
| **(EC)DHE handshake thông thường** | Có bảo đảm FS trong mô hình giao thức, nếu ephemeral secrets được hủy và peer xác thực đúng |
| **PSK-only (psk_ke, không có DHE)** | **Không có FS đối với việc PSK bị lộ sau này** trong mô hình này |
| **PSK với (EC)DHE (psk_dhe_ke)** | Có thể có FS cho traffic được thiết lập từ sự đóng góp DHE, theo giả định giao thức và xóa secret |
| **0-RTT early data** | **Không có forward secrecy cho early data** theo mô hình TLS 1.3; còn cần lưu ý nguy cơ replay |

**Kết luận vận hành:** bật TLS 1.3 **không đủ** để suy ra mọi dữ liệu trong mọi lựa chọn PSK/resumption/0-RTT đều có cùng mức forward secrecy. Phải kiểm tra cấu hình, cách ứng dụng dùng resumption và có chấp nhận early data hay không.

### 6.3. 0-RTT early data và replay

**0-RTT** cho phép client gửi dữ liệu ứng dụng sớm trên một kết nối TLS 1.3 resumed trong một số cấu hình, trước khi hoàn tất handshake mới. Cơ chế này giảm độ trễ nhưng có hai đặc điểm quan trọng:

1. **Early data không có FS** theo cách bảo vệ bằng các ephemeral secrets mới của lần handshake hiện tại.
2. **Early data có nguy cơ bị replay**; hệ thống phải tuân thủ hướng dẫn ứng dụng/giao thức và không tự coi nội dung 0-RTT là “mới”.

Đối với API có tác động không thể lặp như **chuyển tiền, tạo đơn hàng, trừ tồn kho**, không nên chấp nhận 0-RTT cho thao tác không có chính sách chống replay/idempotency phù hợp.

**Không suy luận** rằng một giao thức có authenticated encryption thì tự chống được replay. Bản tin cũ có tag hợp lệ vẫn có thể được gửi lại nếu thiếu trạng thái/sequence/check.

### 6.4. Session resumption và ticket protection

Session resumption giúp tái thiết lập kết nối nhanh hơn nhờ thông tin/PSK đã có. Nhưng:

- Cần bảo vệ **resumption PSK** và các cơ chế server dùng để bảo vệ/khôi phục resumption state.
- Phải kiểm soát **thời hạn ticket**, rotation của ticket-protection key, reuse và quyền truy cập.
- Lộ các bí mật resumption có thể làm thay đổi phạm vi an toàn của các resumed sessions, tùy chế độ PSK/DHE.
- Chọn **psk_dhe_ke** cho những phiên cần FS theo chính sách phù hợp; không đồng nhất với PSK-only.
- Thiết lập chính sách **0-RTT** riêng cho dữ liệu có tác động nghiệp vụ.

**Ticket encryption key không phải traffic key**. Lộ ticket key có thể ảnh hưởng khả năng bảo vệ resumption state; phạm vi còn phụ thuộc việc ticket/PSK và chế độ handshake đã dùng.

### 6.5. TLS 1.2 và TLS 1.3: không đánh đồng

Trong TLS 1.2, một số cipher suite dùng **ECDHE** có thể cung cấp FS, trong khi những suite **RSA key transport** lịch sử thì không trước việc lộ private RSA key về sau. Trong TLS 1.3, **RSA key transport đã bị loại bỏ** và key schedule thay đổi đáng kể, nhưng những ngoại lệ về **PSK-only và 0-RTT** vẫn phải được nhận diện.

Không chọn cipher suite chỉ vì có chữ “AES-256” rồi suy ra FS. **Thuật toán mã hóa dữ liệu** và **cách thiết lập khóa** là hai vấn đề khác nhau.

## 7. Phân biệt forward secrecy với post-compromise security

Đây là một nhầm lẫn kiến trúc rất quan trọng.

### 7.1. Forward secrecy nhìn về quá khứ

FS trả lời câu hỏi:

> Nếu một bí mật dài hạn bị lộ **sau khi phiên cũ đã hoàn tất**, người tấn công có khôi phục khóa phiên cũ từ traffic đã ghi lại hay không?

Một cơ chế FS đúng giúp hạn chế ảnh hưởng **hồi tố** của kiểu lộ bí mật được đưa vào mô hình.

### 7.2. Post-compromise security nhìn về tương lai

**Post-compromise security (PCS)** hoặc **healing sau xâm phạm** là thuộc tính khác: sau khi attacker đã biết một số bí mật tại thời điểm T, giao thức có thể **lấy lại bảo mật cho những thông điệp tương lai** khi có đóng góp bí mật mới và các điều kiện cần thiết khác được đáp ứng.

| Thuộc tính | Câu hỏi trung tâm | Điều không được ngộ nhận |
| --- | --- | --- |
| **Forward secrecy** | Lộ long-term secret về sau có giải được session cũ không? | Không bảo vệ session key đã bị lấy trực tiếp |
| **Post-compromise security** | Sau khi bị lộ trạng thái khóa, có thể phục hồi bảo mật trong tương lai không? | Không tự có nếu attacker vẫn kiểm soát endpoint/secret nguồn |
| **Key rotation** | Chuyển sang phiên bản khóa mới khi nào? | Đổi key ID không chứng minh có entropy độc lập hoặc đã hết rủi ro |
| **Traffic key update** | Tạo traffic key mới từ key schedule đang có | Không nhất thiết “healing” trước attacker đã biết toàn bộ trạng thái/secret update |
| **Fresh authenticated DH** | Đưa đóng góp bí mật tạm thời mới vào thiết lập khóa | Phải có xác thực và xử lý việc attacker có thể vẫn MITM |
| **Key erasure** | Giảm thời gian bí mật cũ còn trong bộ nhớ/lưu trữ | Không thể xóa bản sao attacker đã lấy trước đó |

### 7.3. Tại sao KeyUpdate chưa đủ để gọi là PCS?

Một số cơ chế **traffic key update** chỉ dẫn xuất traffic secrets mới **từ trạng thái bí mật hiện tại**. Nếu attacker đã biết đầy đủ trạng thái đó, họ có thể có khả năng tính tiếp các trạng thái sau. Không được kết luận “đã KeyUpdate nên đã phục hồi khỏi compromise”.

Để có khả năng phục hồi sau lộ khóa, giao thức cần **nguồn bí mật mới** và các tính chất xác thực/đồng bộ thích hợp; một số giao thức messaging còn có cấu trúc ratchet phức tạp. **FS, key update và PCS không phải ba tên gọi cho cùng một tính chất.**

## 8. Vòng đời ephemeral key và bảo mật bộ nhớ

Một thiết kế có thể có FS rất tốt ở tầng toán học nhưng triển khai lại **ghi toàn bộ session secrets vào ổ đĩa**. Khi đó việc private signing key lộ về sau chưa chắc là rủi ro chính: attacker có thể chỉ cần lấy **session key logs** hoặc dump bộ nhớ đã được lưu.

### 8.1. Phân biệt key material theo thời gian sống

| Key material | Thời gian sống mong đợi | Kiểm soát |
| --- | --- | --- |
| **Ephemeral DH private key** | Trong phạm vi handshake/phiên theo giao thức | Tạo đúng chuẩn, không export/log, hủy khi không còn cần |
| **ECDH shared secret** | Ngắn; dùng tạo key schedule | Tránh lưu/truyền ra ngoài, xóa khi có thể |
| **Handshake secrets/PRK** | Theo giai đoạn key schedule | Chỉ dùng đúng purpose, hạn chế rò rỉ |
| **Application traffic keys** | Theo phiên/epoch và giới hạn sử dụng | Bảo vệ runtime, key update/expiry đúng chuẩn |
| **Long-term signing key** | Theo cryptoperiod xác thực của dịch vụ | KMS/HSM khi phù hợp, IAM Sign, rotation/thu hồi |
| **PSK / ticket protection key** | Theo chính sách resumption | Quản trị riêng, expiry/rotation và phạm vi |
| **DEK/KEK lưu trữ** | Theo vòng đời dữ liệu và backup | Envelope encryption, KMS/HSM, kiểm soát restore |

### 8.2. Những nơi bí mật có thể vô tình tồn tại

- **Application logs** và structured logs ghi toàn bộ handshake/context.
- **Key logging** hỗ trợ debug TLS, ví dụ các cơ chế xuất session secrets dùng cho phân tích lưu lượng.
- **Heap dumps**, core dumps, crash reports và file swap.
- **APM/observability traces** thu biến môi trường, buffer hoặc request/response nhạy cảm.
- **Memory snapshots**, VM/container snapshots và hình ảnh máy ảo.
- **Debug endpoints**, remote debugger hoặc công cụ instrumentation có quyền đọc bộ nhớ.
- **Backup/log archives** có độ lưu giữ rất dài.

Việc sử dụng TLS stack chuẩn chỉ giúp tránh tự thiết kế key agreement; nó **không tự cấu hình an toàn mọi cơ chế debug và retention**. Nhóm vận hành cần phân quyền, cấu hình không log secrets ở production, kiểm soát dump/snapshot và giảm khả năng một tài khoản bị chiếm thu thập traffic keys.

### 8.3. Xóa secret trong JVM có giới hạn

~~~java
byte[] secret = obtainEphemeralSecretForDemo();
try {
    // Chỉ dùng trong phạm vi cho phép.
} finally {
    java.util.Arrays.fill(secret, (byte) 0);
}
~~~

Đây là minh họa **best-effort zeroization**. JVM, JCA provider, các lớp **SecretKeySpec**, native TLS provider hoặc GC có thể giữ bản sao nội bộ. Không khẳng định gọi Arrays.fill là bằng chứng đã xóa **mọi** bản sao bí mật.

Tốt hơn là **để TLS provider quản lý key material**, không export session keys, không kéo chúng lên tầng ứng dụng khi không cần, và cấu hình nền tảng runtime với chính sách bảo mật bộ nhớ/nhật ký phù hợp.

### 8.4. Không tái sử dụng ephemeral key vì “hiệu năng”

Nếu một private ephemeral key được tái sử dụng qua nhiều kết nối dài hơn giả định thiết kế, việc nó lộ có thể ảnh hưởng **nhiều phiên** thay vì một phiên. Các giao thức có thể có cơ chế tối ưu được quy định; không tự giữ một cặp ECDH “ephemeral” trong cache tùy ý và gọi đó là PFS.

Điều cần đo là **key reuse, phạm vi phiên, thời gian giữ secret và giới hạn key schedule** theo giao thức, không chỉ số lần tạo đối tượng **KeyPairGenerator**.

## 9. Java 17: minh họa nhiều phiên X25519 độc lập

Ví dụ dưới đây dùng API **JCA/JCE** trong Java 17 để tạo **hai phiên X25519 độc lập**, tính shared secret ở hai phía rồi dùng **HKDF-SHA256** dẫn xuất cùng traffic key trong từng phiên. Kết quả demo nhằm minh họa sự tách biệt secret giữa phiên A và B.

**Đây không phải giao thức bảo mật sử dụng được trong production:** code không xác thực public key, không dùng certificate/PSK, không trao đổi các thông điệp handshake qua mạng, không xử lý Finished, replay/downgrade hoặc AEAD record layer. Một kẻ MITM vẫn có thể thay public keys nếu áp dụng trực tiếp ngoài đời.

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

public final class ForwardSecrecyX25519Demo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String HMAC = "HmacSHA256";
    private static final int KEY_BYTES = 32;

    private static byte[] sharedSecret(
            PrivateKey own, PublicKey peer)
            throws GeneralSecurityException {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(own);
        agreement.doPhase(peer, true);
        byte[] secret = agreement.generateSecret();

        // Phòng vệ với shared secret toàn zero của X25519.
        int combined = 0;
        for (byte value : secret) {
            combined |= value & 0xff;
        }
        if (combined == 0) {
            Arrays.fill(secret, (byte) 0);
            throw new GeneralSecurityException(
                "Invalid X25519 shared secret");
        }
        return secret;
    }

    private static byte[] transcriptHash(
            byte[] clientPublic, byte[] serverPublic,
            byte[] sessionRandom) throws GeneralSecurityException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        addField(digest,
            "fs-demo/v1".getBytes(StandardCharsets.UTF_8));
        addField(digest, sessionRandom);
        addField(digest, clientPublic);
        addField(digest, serverPublic);
        return digest.digest();
    }

    private static void addField(
            MessageDigest digest, byte[] bytes) {
        digest.update(ByteBuffer.allocate(4)
            .putInt(bytes.length).array());
        digest.update(bytes);
    }

    // RFC 5869: Extract -> PRK, Expand -> 32-byte output T(1).
    private static byte[] deriveTrafficKey(
            byte[] secret, byte[] transcript) throws GeneralSecurityException {

        Mac mac = Mac.getInstance(HMAC);
        mac.init(new SecretKeySpec(transcript, HMAC));
        byte[] prk = mac.doFinal(secret);

        try {
            byte[] purpose =
                "fs-demo/v1|client-to-server|AES-256-GCM"
                    .getBytes(StandardCharsets.UTF_8);

            mac.init(new SecretKeySpec(prk, HMAC));
            mac.update(purpose);
            mac.update(transcript);
            mac.update((byte) 1); // HKDF-Expand block T(1).
            return mac.doFinal();
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    // Trả một dấu hiệu kiểm tra kết quả, không xuất secret ra ngoài.
    private static byte[] runDemoSession() throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("X25519");
        KeyPair client = generator.generateKeyPair();
        KeyPair server = generator.generateKeyPair();

        byte[] random = new byte[KEY_BYTES];
        RNG.nextBytes(random);
        byte[] transcript = transcriptHash(
            client.getPublic().getEncoded(),
            server.getPublic().getEncoded(),
            random);

        byte[] clientSecret = null;
        byte[] serverSecret = null;
        byte[] clientTraffic = null;
        byte[] serverTraffic = null;

        try {
            clientSecret = sharedSecret(
                client.getPrivate(), server.getPublic());
            serverSecret = sharedSecret(
                server.getPrivate(), client.getPublic());

            clientTraffic = deriveTrafficKey(
                clientSecret, transcript);
            serverTraffic = deriveTrafficKey(
                serverSecret, transcript);

            if (!MessageDigest.isEqual(clientSecret, serverSecret)
                    || !MessageDigest.isEqual(
                        clientTraffic, serverTraffic)) {
                throw new GeneralSecurityException(
                    "Key agreement mismatch");
            }

            // Demo chỉ dùng bản sao để so sánh khác phiên.
            return Arrays.copyOf(clientTraffic, clientTraffic.length);
        } finally {
            if (clientSecret != null)
                Arrays.fill(clientSecret, (byte) 0);
            if (serverSecret != null)
                Arrays.fill(serverSecret, (byte) 0);
            if (clientTraffic != null)
                Arrays.fill(clientTraffic, (byte) 0);
            if (serverTraffic != null)
                Arrays.fill(serverTraffic, (byte) 0);
            Arrays.fill(random, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] sessionA = runDemoSession();
        byte[] sessionB = runDemoSession();
        try {
            System.out.println(
                "Separate sessions: " +
                !Arrays.equals(sessionA, sessionB));
            System.out.println(
                "Derived key size: " + sessionA.length);
        } finally {
            Arrays.fill(sessionA, (byte) 0);
            Arrays.fill(sessionB, (byte) 0);
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
Separate sessions: true
Derived key size: 32
~~~

### 9.1. Điều demo chứng minh và không chứng minh

**Demo cho thấy:**

- Mỗi lần chạy **runDemoSession** tạo cặp X25519 mới cho cả client và server.
- Hai phía tính cùng **ECDH shared secret** trong một phiên.
- HKDF với transcript cùng byte tạo kết quả thống nhất cho hai phía.
- Hai phiên dùng secret/ephemeral keys độc lập nên các derived keys khác nhau với xác suất áp đảo.
- Mảng secret được xóa theo cách best-effort khi hết phạm vi.

**Demo không chứng minh bằng thực nghiệm một giao thức có FS**. FS là thuộc tính cần được phân tích theo **mô hình đe dọa và giao thức hoàn chỉnh**. In ra hai khóa khác nhau không nói lên điều gì về xác thực peer, thời điểm lộ khóa, cấu trúc handshake hay việc nhà cung cấp JCA có giữ bản sao secret trong bộ nhớ hay không.

### 9.2. Vì sao HKDF có mặt trong ví dụ?

Kết quả ECDH phải được đưa vào **KDF/key schedule** thích hợp. HKDF giúp tách khóa theo purpose, role và transcript. Tuy nhiên:

- HKDF **không thay thế peer authentication**.
- HKDF **không tự cung cấp FS** nếu IKM lấy từ một bí mật dài hạn bị lộ.
- Nhãn trong demo **không phải** nhãn key schedule của TLS 1.3.
- Khi dùng khóa với **AES-GCM**, phải đảm bảo nonce không trùng dưới cùng khóa và tuân thủ giới hạn thuật toán.
- Không dùng chung một output 32 byte cho mọi hướng/thuật toán nếu giao thức chưa thiết kế key separation.

## 10. Java 17 trong sản phẩm: sử dụng TLS 1.3 chuẩn

Với dịch vụ Java giao tiếp qua HTTPS, thường nên chọn **JSSE/TLS 1.3** thay vì tự ghép **X25519 + HKDF + AES-GCM**.

Ví dụ dưới đây tạo **HttpClient** yêu cầu TLS 1.3, dùng trust configuration mặc định của JVM, gửi một yêu cầu tới endpoint minh họa và kiểm tra giao thức của TLS session được trả về. Mã chỉ có ý nghĩa khi endpoint thật khả dụng và trust store đã được cấu hình; **không cần chạy bài học**.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSession;

public final class ForwardSecrecyTlsClient {
    public static void main(String[] args) throws Exception {
        SSLParameters tls = new SSLParameters();
        tls.setProtocols(new String[] { "TLSv1.3" });

        // Dùng SSLContext/trust configuration an toàn của JVM.
        // Không thay bằng TrustManager bỏ qua kiểm tra chứng chỉ.
        HttpClient client = HttpClient.newBuilder()
            .sslParameters(tls)
            .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://payment.example.org/health"))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        SSLSession session = response.sslSession()
            .orElseThrow(() -> new IllegalStateException(
                "HTTPS response without SSL session"));

        if (!"TLSv1.3".equals(session.getProtocol())) {
            throw new IllegalStateException(
                "Unexpected TLS protocol");
        }

        System.out.println("Negotiated: " + session.getProtocol());
        System.out.println("HTTP status: " + response.statusCode());
    }
}
~~~

**Lưu ý giới hạn quan sát:** đoạn mã xác nhận **phiên sử dụng TLSv1.3** nếu kết nối thành công. Nó **không tự chứng minh** handshake được thực hiện qua nhóm (EC)DHE nào, không chứng minh cấu hình resumption/PSK, không chứng minh **0-RTT** bị tắt và không đo được secret đã bị xóa khỏi bộ nhớ hay chưa. Muốn đánh giá FS thực tế, cần kiểm tra **cấu hình TLS provider/server, giao thức/nhánh handshake và chính sách key retention** bằng công cụ/quan sát vận hành phù hợp.

### 10.1. Những cấu hình không nên làm

- **Không tắt hostname validation** hoặc chấp nhận tất cả certificate để kết nối thử.
- Không cấu hình **TrustManager** trả true cho mọi chứng chỉ.
- Không hạ cấp xuống TLS cũ hoặc bật nhóm/cipher không được chính sách chấp nhận chỉ để tương thích.
- Không tự cho phép 0-RTT trên những API có tác động nghiệp vụ nếu chưa thiết kế chống replay.
- Không giữ session key logs, key material debug hoặc bộ nhớ phiên trong log có retention dài.
- Không coi “TLSv1.3” trong log là bằng chứng tất cả traffic đều có FS trước mọi kiểu compromise.

### 10.2. Chứng chỉ dài hạn và ephemeral secrets có vòng đời khác nhau

Server certificate có thể chứa **public signing verification key**, được dùng để xác thực handshake theo giao thức. Private signing key tương ứng có thể nằm trong KMS/HSM hoặc kho khóa bảo vệ. Trong khi đó, **ECDHE ephemeral keys** và traffic secrets được TLS provider quản lý theo từng phiên.

**Thay server certificate** không phải thao tác **rotate traffic key của các phiên đã kết thúc**, và cũng không phải re-encrypt DEK của database.

## 11. Forward secrecy không thay thế bảo mật dữ liệu lưu trữ

Một ứng dụng thường có hai tập dữ liệu khác nhau:

1. **Data in transit:** byte trao đổi giữa client/server qua TLS.
2. **Data at rest:** file, hóa đơn, bản ghi database và backup được lưu sau khi kết nối kết thúc.

FS của TLS có mục tiêu hẹp: bảo vệ **traffic lịch sử** khỏi một số tình huống lộ khóa dài hạn. Nó không tự bảo đảm **bí mật hóa đơn lưu trên database**.

~~~mermaid
flowchart LR
    C["OrderService"] -->|"TLS 1.3 authenticated key establishment"| A["PaymentService"]
    A --> AUTH["IAM: principal + tenant + resource"]
    AUTH --> ENC["AES-GCM dữ liệu với DEK"]
    ENC --> DB["Database ciphertext + wrapped DEK"]
    K["KMS/HSM giữ KEK"] <-->|"Wrap/Unwrap, key policy"| ENC
    A --> LOG["Audit: kết nối, quyền, key IDs"]
~~~

### 11.1. DEK/KEK có vai trò gì?

- **DEK (Data Encryption Key):** khóa đối xứng mã hóa dữ liệu lưu trữ.
- **KEK (Key Encryption Key):** khóa dùng bọc DEK; thường do KMS/HSM bảo vệ.
- **AAD của AEAD:** ràng buộc ciphertext với tenant, object ID hoặc purpose khi phù hợp.
- **IAM:** giới hạn workload nào được yêu cầu unwrap hoặc đọc dữ liệu.

Những khóa này có thể có **cryptoperiod kéo dài** vì dữ liệu cần được khôi phục nhiều năm. Không được xóa DEK/KEK khi bản sao dữ liệu còn cần giải mã.

### 11.2. Đừng nhầm FS với key rotation ở tầng lưu trữ

| Sự kiện | Điều thay đổi | Không tự bảo vệ được điều gì? |
| --- | --- | --- |
| ECDHE ephemeral keys mới | Secret thiết lập khóa phiên mới | Không rotation DEK/KEK của database |
| Traffic KeyUpdate | Khóa lưu lượng trong kết nối | Không tự làm FS/PCS mạnh hơn mọi chế độ |
| Rotate certificate/signing key | Khóa xác thực identity trong handshake mới | Không re-encrypt dữ liệu at rest |
| Rotate KMS KEK | Khóa bọc DEK | Không thay traffic key TLS |
| Rewrap DEK | Lớp bọc của cùng DEK | Không sửa ciphertext hay khôi phục dữ liệu đã bị lộ |
| Re-encrypt bằng DEK mới | Khóa và bản mã dữ liệu | Không tự xác thực peer trong kết nối mạng |

Nếu **DEK hoặc KEK của dữ liệu lưu trữ** đã bị lộ, FS của TLS **không cứu được dữ liệu at rest**. Nếu server đã lưu **plaintext** vào log, FS cũng không xóa được bản log đó.

## 12. KMS/HSM và vòng đời khóa xác thực

**KMS/HSM** thường được dùng bảo vệ **long-term private signing key**, cung cấp thao tác ký và quản lý quyền. Chúng bổ trợ cho FS nhưng không thay thế việc dùng **ephemeral secrets** và key schedule đúng.

### 12.1. HSM giữ signing key không xuất được có giúp gì?

Có. Nó có thể giảm khả năng private signing key bị xuất ở dạng rõ, hỗ trợ phân quyền và audit. Nhưng:

- Nếu workload bị chiếm có quyền **Sign** quá rộng, attacker có thể yêu cầu tạo **chữ ký hợp lệ** để giả mạo các thông điệp mới.
- Non-exportable **không tự đảm bảo FS** cho giao thức key transport sử dụng static private key để mở các secret cũ.
- HSM không tự ngăn **session key logs** hoặc plaintext bị ghi tại ứng dụng.
- Không phải mọi HSM đều hỗ trợ **X25519, ECDH P-256, KEM hoặc DeriveKey** dưới cùng API.
- Trong nhiều cấu hình TLS, ephemeral private keys được **TLS provider** quản lý trong process, không nhất thiết nằm trong HSM.

Vì vậy cần bảo vệ cả **vật liệu khóa**, **quyền sử dụng khóa** và **môi trường thực thi giao thức**.

### 12.2. Nguyên tắc IAM cho key establishment

| Vai trò | Quyền thường cần | Không nên mặc định có |
| --- | --- | --- |
| **TLS termination workload** | Dùng signing credential/PSK theo policy để xác thực kênh | Quyền quản trị toàn bộ KEK và xuất mọi secret |
| **Key administrator** | Quản trị key lifecycle, policy, rotation có phê duyệt | Quyền Sign mọi nội dung nghiệp vụ |
| **Certificate administrator** | Cấp phát, thu hồi và quản lý trust phù hợp | Đọc session traffic keys hoặc DEK database |
| **Data-encryption workload** | GenerateDataKey/Unwrap trong phạm vi tenant/tài nguyên | Quyền dùng long-term signing key tùy ý |
| **Security auditor** | Đọc sự kiện metadata và trạng thái policy | Quyền lấy private key, traffic keys hoặc plaintext |
| **Incident responder** | Quyền theo tình huống, có thời hạn và audit | Quyền đặc biệt vĩnh viễn trên mọi hệ thống |

Đừng dùng một **service account** có cả quyền ký TLS, unwrap toàn bộ DEK, thay trust store và xóa log nếu không thật sự cần. Việc tách nhiệm vụ giúp giảm phạm vi ảnh hưởng khi một danh tính bị chiếm.

### 12.3. KDF và HSM

Một số nền tảng hỗ trợ **DeriveKey** hoặc thao tác agreement trong ranh giới HSM. Dù root/private key không xuất được, **quyền gọi DeriveKey** vẫn nhạy cảm: attacker có thể lạm dụng API để thiết lập hoặc dẫn xuất bí mật trái phép. Cần giới hạn theo **key ID, algorithm, purpose, principal, môi trường và policy nghiệp vụ**.

Không tự xuất root secret khỏi HSM để dùng HKDF trong JVM chỉ vì muốn “mang tính PFS”. Dẫn xuất nhiều khóa từ một root lâu dài **không có cùng ý nghĩa** với authenticated ECDHE ephemeral key establishment.

## 13. Threat model: điều gì làm mất hoặc thu hẹp FS?

| Rủi ro | Ảnh hưởng đến FS và dữ liệu | Biện pháp |
| --- | --- | --- |
| **RSA key transport/static secret phụ thuộc dài hạn** | Lộ private key tương lai có thể giải dữ liệu lịch sử | Dùng giao thức authenticated (EC)DHE khi phù hợp |
| **Ephemeral private key bị lưu lại** | Lộ bản lưu có thể khiến phiên cũ bị giải | Hủy secret, tránh log/dump/backup secret |
| **Traffic keys bị xuất qua debug** | Attacker có thể giải traffic tương ứng | Kiểm soát key logging, quyền debug và retention |
| **PSK-only resumption** | Không có FS đối với lộ PSK sau này | Dùng PSK+DHE theo chính sách và giao thức |
| **0-RTT early data** | Early data không có FS và có nguy cơ replay | Hạn chế/tắt 0-RTT, chỉ dùng khi có chính sách replay phù hợp |
| **MITM do không xác thực peer** | Kênh bị đọc/sửa ngay khi trao đổi | PKI/PSK đúng chuẩn, xác minh hostname/identity |
| **Sai thuật toán/nhóm key agreement** | Bảo mật có thể yếu hoặc xử lý public key sai | Allowlist nhóm, provider được kiểm chứng |
| **Key schedule không ràng buộc context** | Nhầm role, unknown key-share hoặc downgrade tùy thiết kế | Giao thức chuẩn, transcript authentication |
| **Dùng lại nonce AES-GCM** | Có thể phá bí mật/toàn vẹn traffic dù key thiết lập tốt | Nonce duy nhất theo key, giới hạn record |
| **Lộ signing key khi phiên đang diễn ra** | Có thể giả mạo kết nối mới và ảnh hưởng xác thực | Thu hồi credential, khóa phiên, điều tra endpoint |
| **Chiếm endpoint đang xử lý** | Attacker đọc plaintext/session key trực tiếp | Hardening runtime, cô lập quyền, endpoint detection |
| **Lưu plaintext trong log/backup** | FS mạng không bảo vệ dữ liệu đã ghi rõ | Data minimization, encryption at rest, audit |
| **Tái sử dụng ephemeral key ngoài chính sách** | Một khóa bị lộ có thể ảnh hưởng nhiều phiên | Tạo key theo phạm vi và xóa đúng vòng đời |
| **Chỉ KeyUpdate sau compromise** | Nếu trạng thái key đã lộ, key mới có thể tính được | Không nhầm key update với PCS; đánh giá fresh agreement |
| **Thu hồi chứng chỉ chậm** | Attacker tiếp tục giả mạo phiên mới nếu key bị lộ | Certificate revocation, trust update, giám sát |
| **Không thử backup/restore KMS** | Mất khả năng đọc dữ liệu lưu trữ | Key retention/rotation/restore riêng với FS |

### 13.1. Kẻ ghi traffic và kẻ chiếm endpoint có khả năng khác nhau

**Attacker thụ động** ghi lại ciphertext và handshake, sau này chỉ lấy long-term signing key: đây là mô hình quan trọng để đánh giá FS.

**Attacker có quyền chạy code trên endpoint** ngay trong phiên có thể đọc plaintext, lấy session secret từ bộ nhớ, giả mạo hành động ứng dụng hoặc thay cấu hình TLS. FS không phải cơ chế phòng vệ tuyệt đối trước **runtime compromise**.

Phải tránh tuyên bố “giao thức có PFS nên server bị hack cũng không lộ dữ liệu quá khứ”. Cần xác định **hack lúc nào, dữ liệu/khóa nào bị lấy, log và backup nào còn tồn tại**.

### 13.2. Forward secrecy không chống replay

Bản tin ứng dụng đã xác thực có thể vẫn bị phát lại nếu giao thức hoặc nghiệp vụ chấp nhận cùng dữ liệu một lần nữa. FS nói về **khả năng khôi phục khóa cũ sau lộ long-term secret**, không trực tiếp giải quyết **freshness**.

Trong hệ thống thanh toán, bên cạnh TLS còn cần **transaction ID, idempotency, kiểm tra trạng thái và phân quyền**.

### 13.3. Forward secrecy không chống tấn công lượng tử trong tương lai

DH/ECDH cổ điển dựa trên giả định khó tính toán đối với kẻ tấn công có khả năng tính toán cổ điển. **Máy tính lượng tử đủ mạnh** về nguyên tắc có thể làm thay đổi khả năng giải bài toán nền tảng của DH/ECDH từ các public keys đã ghi lại. FS trước việc lộ signing key trong mô hình cổ điển **không đồng nghĩa** chống được mọi hình thức “harvest now, decrypt later” khi đối thủ có năng lực lượng tử.

Hệ thống có nhu cầu bảo mật dữ liệu nhiều thập kỷ nên theo dõi **chuẩn key establishment hậu lượng tử/hybrid**, khả năng hỗ trợ của TLS/provider, chính sách thuật toán và kế hoạch di chuyển. Không tự ghép KEM hậu lượng tử với ECDH thành một protocol mới nếu chưa có đặc tả và phân tích.

## 14. Quy trình thiết kế FS cho hệ thống Java

Một tổ chức muốn bảo vệ lưu lượng nhạy cảm của microservices có thể áp dụng quy trình sau.

### Bước 1: xác định dữ liệu cần bảo vệ

Đánh giá:

- Dữ liệu nào đi qua mạng (thanh toán, thông tin khách hàng, token, bí mật API).
- Ai có thể **ghi lại traffic** và giữ trong bao lâu.
- Loại bí mật dài hạn nào có khả năng bị lộ trong tương lai.
- Độ dài yêu cầu bảo mật dữ liệu; có yêu cầu hậu lượng tử hay không.
- Dữ liệu có được lưu lại ở endpoint hoặc backup dưới dạng khác không.

### Bước 2: chọn giao thức key establishment phù hợp

Ưu tiên **TLS 1.3** hoặc một giao thức đã được phân tích, sử dụng authenticated key establishment. Xác định rõ **nhóm key agreement, server/client authentication, PSK/resumption và 0-RTT policy**.

Nếu hệ thống vẫn phải hỗ trợ TLS 1.2, phải kiểm soát **cipher suites dùng ECDHE** và loại bỏ những lựa chọn không đáp ứng chính sách FS. Không chỉ dựa vào độ dài khóa AES.

### Bước 3: xác thực peer và chống downgrade

- Cấu hình **trust anchors** từ nguồn tin cậy.
- Xác minh certificate chain, hostname/service identity, key usage và revocation theo mô hình ứng dụng.
- Cấu hình mTLS khi service-to-service cần xác thực hai chiều.
- Giới hạn protocol versions và groups theo chính sách.
- Không chấp nhận TrustManager/HostnameVerifier bỏ kiểm tra chỉ để giảm lỗi.

### Bước 4: kiểm soát vòng đời ephemeral secret

- Để TLS provider tự sinh ephemeral keys và quản lý handshake.
- Không bật xuất traffic keys ở production trừ trường hợp điều tra được phê duyệt và kiểm soát chặt.
- Giảm quyền đọc memory dump, crash report, container snapshot và các kho log.
- Cấu hình session timeout, key update và secret retention theo thiết kế.
- Kiểm tra các đường làm lộ session state ngoài ý muốn.

### Bước 5: quản lý các khóa dài hạn

- Private signing keys, certificate, PSK và ticket-protection keys có **owner, key ID, version và cryptoperiod**.
- Giới hạn quyền Sign/DeriveKey/Rotate/Delete bằng IAM.
- Hỗ trợ cấp phát và thu hồi trust/certificate đúng chính sách.
- Không đặt private signing key cạnh toàn bộ DEK/KEK và password của hệ thống.
- Theo dõi các sự kiện ký, thay grant, cấp chứng chỉ và lạm dụng workload.

### Bước 6: tách biệt data-at-rest

- Dùng **DEK** thích hợp để mã hóa dữ liệu, **KEK** được bảo vệ qua KMS/HSM.
- Dùng **AEAD/AAD** đúng ngữ cảnh dữ liệu và quyền truy cập.
- Định nghĩa backup/restore, rotation KEK, rewrap DEK và re-encrypt khi cần.
- Không lấy ephemeral TLS session key để mã hóa file lâu dài; sẽ không có đường khôi phục hợp lý sau khi phiên hủy.

### Bước 7: kiểm thử và giám sát

- Kết nối từ client có trust hợp lệ và từ client có trust sai.
- Chứng chỉ hết hạn/không đúng hostname hoặc bị thu hồi theo chính sách.
- Phiên bản TLS/nhóm không được phép.
- Các chế độ resumption và 0-RTT theo cấu hình thực.
- Thay signing certificate, ticket-protection key và session expiry.
- Bật/tắt chế độ debug trong môi trường thử nghiệm, kiểm tra không xuất session secrets ở production.
- Khả năng giám sát lộ khóa dài hạn và quy trình thu hồi khẩn cấp.

## 15. Tình huống thực tế: PaymentService bị lộ signing key sau 6 tháng

### Bối cảnh

PaymentService chạy Java 17, cung cấp API HTTPS. Client giao tiếp qua **authenticated TLS 1.3 sử dụng ephemeral (EC)DHE**; key material phiên được TLS stack quản lý, không lưu key logs. Hóa đơn trong database được mã hóa riêng bằng **DEK/KEK của KMS**.

Một ngày, nhân viên bảo mật phát hiện **private signing key** của certificate máy chủ có thể đã bị truy cập trái phép. Attacker trước đó đã ghi traffic HTTPS trong sáu tháng.

### Phân tích phạm vi

| Đối tượng | Có nguy cơ gì? |
| --- | --- |
| **Recorded TLS traffic cũ** | Có thể vẫn bảo mật trước riêng việc lộ signing key, nếu các phiên thực sự có FS và session secrets không lộ |
| **Kết nối mới** | Attacker có thể giả mạo máy chủ nếu có cơ hội và client tiếp tục tin credential cũ |
| **Phiên đang hoạt động** | Cần điều tra endpoint/session state, khả năng attacker có quyền khác ngoài signing key |
| **Traffic từ 0-RTT/PSK-only** | Phải đánh giá riêng; không mặc định cùng bảo đảm FS với full ECDHE |
| **Database ciphertext** | Không tự lộ do signing key bị lấy; còn phụ thuộc DEK/KEK và quyền KMS |
| **Plaintext/log/backup** | Nếu đã bị exfiltrate, FS của TLS không phục hồi bí mật đó |
| **Chứng chỉ và trust stores** | Phải cập nhật/thu hồi, xử lý cache và đối tác chưa nhận key mới |

### Hướng ứng phó

1. **Cô lập signing credential** và tạm dừng những principal/ngữ cảnh nghi vấn theo khả năng vận hành.
2. **Thu hồi hoặc vô hiệu hóa certificate/khóa** theo PKI và KMS/HSM, cấp phát key/certificate mới qua quy trình được phê duyệt.
3. **Kiểm tra sự kiện IAM và Sign** trong khoảng thời gian nghi ngờ; xem có forged handshake hay truy cập endpoint không.
4. **Đánh giá các phiên TLS đã chạy**: sử dụng ECDHE/PSK mode nào, 0-RTT có được phép không, session secret logs/dumps/snapshots có tồn tại không.
5. **Điều tra các bản ghi** và giao dịch đáng ngờ; kiểm tra phân quyền và replay protections ở tầng nghiệp vụ.
6. **Xử lý client cache/trust**, thử nghiệm và giám sát kết nối với certificate mới.
7. **Bảo vệ các khóa tầng dữ liệu**: xác minh KMS grants, DEK/KEK không đồng thời bị lộ; không tự động re-encrypt toàn database chỉ vì signing certificate bị đổi.
8. **Cập nhật hậu kiểm**: quyền ký, quy trình cấp certificate, retention của key logs/dumps, cảnh báo hoạt động bất thường và diễn tập khôi phục.

**Đánh giá đúng phải có điều kiện:** lộ private signing key **không tự chứng minh đã mất bí mật traffic lịch sử**, nhưng cũng không chứng minh mọi phiên cũ an toàn nếu attacker đã lấy traffic secrets hoặc chiếm endpoint từ trước.

## 16. Checklist thiết kế và vận hành forward secrecy

1. **Mô hình đe dọa:** muốn bảo vệ traffic cũ trước việc lộ loại long-term key nào?
2. **Giao thức:** có dùng TLS 1.3 hoặc authenticated key establishment được kiểm chứng không?
3. **Chế độ key establishment:** full DHE, PSK+DHE hay PSK-only? Có bằng chứng cấu hình?
4. **0-RTT:** có dùng early data không; có chặn hoặc xử lý replay cho thao tác nhạy cảm?
5. **Peer authentication:** chain, hostname, service identity, PSK và mTLS có đúng policy?
6. **Algorithm policy:** groups/cipher suites có bị giới hạn; còn RSA key transport cũ ở TLS 1.2 không?
7. **Ephemeral generation:** khóa tạm thời có được tạo đúng phạm vi và không tái dùng ngoài thiết kế?
8. **Input validation:** public key/nhóm/shared secret có được xử lý theo chuẩn?
9. **KDF:** transcript, label, role và direction có được ràng buộc đúng key schedule?
10. **AEAD:** traffic keys, nonce/sequence, tag và giới hạn số lần mã hóa có đúng giao thức?
11. **Erasure:** ephemeral private keys/shared secrets/traffic keys có được xóa khi không cần?
12. **Debug:** có cấm hoặc kiểm soát key logs, heap dumps, crash dumps, session snapshots?
13. **Resumption:** PSK/ticket keys có quản lý cryptoperiod, rotation, lifetime và cache?
14. **KeyUpdate:** có hiểu khác biệt với FS và post-compromise security?
15. **Long-term keys:** signing key, PSK và trust anchors có owner, rotation, revocation và audit?
16. **KMS/HSM:** private signing keys được bảo vệ và quyền Sign/DeriveKey có giới hạn?
17. **IAM:** sau khi có TLS, service đã kiểm tra tenant và quyền nghiệp vụ riêng?
18. **Data at rest:** DEK/KEK được quản lý độc lập, backup/restore có đủ quyền khóa?
19. **Compromise response:** đã có quy trình xử lý từng loại secret bị lộ và đánh giá ảnh hưởng?
20. **Historical traffic:** có nắm rõ key logs, 0-RTT và PSK-only để không tuyên bố FS quá mức?
21. **Observability:** theo dõi handshake failures, policy changes, key IDs và nghi vấn mà không log secrets?
22. **Migration:** có kế hoạch thuật toán/giao thức khi yêu cầu an ninh thay đổi trong tương lai?

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Server dùng authenticated ECDHE và các ephemeral/session secrets cũ đã được hủy. Một năm sau private signing key bị lộ. Có chắc attacker giải mã được mọi bản ghi TLS cũ không?

**Đáp án:** Không. Với FS đúng, lộ signing key về sau **không tự đủ** để tái tạo các session keys trước đó. Cần đánh giá thêm việc traffic keys, ephemeral secrets, endpoint, PSK/0-RTT hoặc key logs có bị lộ hay không.

**Câu 2.** Vì sao gọi SHA-256 hoặc HKDF nhiều lần từ cùng một root dài hạn không mặc định tạo FS?

**Đáp án:** Nếu root bị lộ về sau và các tham số dẫn xuất công khai, attacker có thể tái tạo các khóa con quá khứ. FS cần cấu trúc key establishment và loại bỏ những bí mật tạm thời đúng mô hình, không chỉ sinh ra các output khác nhau.

**Câu 3.** ECDHE có tự ngăn MITM khi public key được gửi qua kênh không xác thực không?

**Đáp án:** Không. Attacker có thể thay public keys và thực hiện hai phiên ECDHE riêng. Cần xác thực peer và transcript bằng chứng chỉ/chữ ký/PSK hoặc cơ chế chuẩn phù hợp.

**Câu 4.** Mọi traffic TLS 1.3 có FS giống nhau không?

**Đáp án:** Không. Cần phân biệt full (EC)DHE, **PSK-only**, **PSK+DHE** và **0-RTT early data**. PSK-only không cung cấp FS đối với lộ PSK, còn early data không có FS và có nguy cơ replay theo mô hình TLS 1.3.

**Câu 5.** TLS 1.3 KeyUpdate có chắc phục hồi bảo mật tương lai nếu attacker đã biết toàn bộ traffic secret hiện tại không?

**Đáp án:** Không. Một update chỉ suy ra key mới từ secret đã lộ có thể vẫn bị attacker tính tiếp. **Post-compromise security** cần các điều kiện và nguồn secret mới phù hợp; khác với FS và đổi key thông thường.

**Câu 6.** HSM giữ private signing key non-exportable thì không cần kiểm soát session secret logs?

**Đáp án:** Sai. HSM bảo vệ signing key dài hạn, còn traffic keys/ephemeral secrets có thể nằm trong TLS runtime. Bật key logging hoặc lưu dumps vẫn có thể làm lộ traffic lịch sử.

**Câu 7.** Một dịch vụ TLS 1.3 truyền hóa đơn an toàn và có FS. Có thể lưu plaintext hóa đơn trong database không cần bảo vệ không?

**Đáp án:** Không. FS chỉ đề cập bảo mật traffic lịch sử theo mô hình xâm phạm khóa, không thay thế **encryption at rest, IAM, DEK/KEK và backup protection**.

**Câu 8.** Tại sao không nên dùng 0-RTT cho thao tác chuyển tiền thiếu idempotency?

**Đáp án:** Early data có thể bị **replay** và không có FS theo cùng cách như dữ liệu được thiết lập sau handshake DHE mới. Giao dịch có tác động cần chống replay hoặc phải chờ kênh được thiết lập phù hợp.

**Câu 9.** Nếu attacker lấy private ephemeral key của đúng một phiên, FS có bảo vệ chính phiên đó không?

**Đáp án:** Không bảo đảm. FS không được thiết kế để bảo vệ traffic của một phiên khi bí mật phiên đó đã bị lộ. Mục tiêu của nó là hạn chế việc lộ một số **long-term secrets ở tương lai** làm lộ các phiên trước.

**Câu 10.** KMS KEK lưu trữ bị lộ nhưng TLS dùng ECDHE. Có phải không cần xử lý database vì TLS có PFS không?

**Đáp án:** Không. KEK/DEK là khóa bảo vệ dữ liệu lưu trữ; FS của TLS không áp dụng trực tiếp. Phải đánh giá wrapped DEK, các bản mã đã bị sao chép, quyền KMS và phương án rewrap/re-encrypt phù hợp.

**Câu 11.** Nếu certificate của server hết hạn, có nên xóa tất cả traffic keys đang nằm trong các phiên đã kết thúc và re-encrypt toàn bộ database?

**Đáp án:** Các traffic secrets phiên kết thúc cần được hủy theo vòng đời giao thức; **certificate hết hạn** là sự kiện quản lý khóa xác thực. Nó không tự yêu cầu re-encrypt database, vì dữ liệu lưu trữ dùng DEK/KEK riêng. Cần cập nhật certificate và xác minh trust/khả năng kết nối.

**Câu 12.** Vì sao FS trước việc lộ signing key không đồng nghĩa bảo vệ tuyệt đối trước tấn công lượng tử “harvest now, decrypt later”?

**Đáp án:** ECDHE cổ điển vẫn dựa trên độ khó tính toán của DH/ECDH. Một đối thủ có năng lực lượng tử đủ mạnh trong tương lai có thể tấn công bài toán nền tảng từ public handshake đã lưu. Cần đánh giá các tiêu chuẩn key establishment hậu lượng tử/hybrid khi yêu cầu bảo mật dài hạn đòi hỏi.

## Kết luận

**Forward secrecy là thuộc tính của cách thiết lập và quản lý khóa phiên**, nhằm bảo vệ lưu lượng đã kết thúc trước một số tình huống **lộ khóa dài hạn về sau**. Authenticated ephemeral Diffie–Hellman, KDF/key schedule phù hợp và **hủy bí mật phiên khi không còn cần** là những thành phần quan trọng; một phép ECDH đơn lẻ hoặc một nhãn “ephemeral” không tự tạo ra giao thức an toàn.

Trong hệ thống Java, hãy ưu tiên **TLS 1.3/JSSE với peer authentication chuẩn**, kiểm soát **PSK, resumption, 0-RTT, key logging và vòng đời secret**. Đồng thời bảo vệ **private signing keys qua KMS/HSM, phân quyền IAM, xoay vòng và thu hồi khóa, audit**, và quản lý **DEK/KEK/envelope encryption** độc lập cho dữ liệu lưu trữ. **Forward secrecy bảo vệ một phần quá khứ trước một kiểu rủi ro cụ thể; an toàn toàn hệ thống còn phụ thuộc việc ai được dùng khóa, bí mật nào bị lưu lại và dữ liệu được bảo vệ ở mỗi tầng ra sao.**
