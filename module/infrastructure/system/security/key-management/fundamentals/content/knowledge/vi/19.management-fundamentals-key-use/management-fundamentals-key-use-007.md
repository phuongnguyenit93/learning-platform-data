# Nonce uniqueness theo key (Tính duy nhất của nonce đối với từng khóa mật mã)

## 1. Vì sao nonce phải duy nhất theo key?

**Nonce** là giá trị được dùng trong một số phép toán mật mã, nhất là mã hóa xác thực (AEAD), để phân biệt những lần sử dụng **cùng một khóa**. Trong các chế độ như **AES-GCM** và **ChaCha20-Poly1305**, việc dùng lại cùng một cặp **(key, nonce)** cho những thông điệp khác nhau có thể phá hỏng tính bí mật và tính toàn vẹn, dù thuật toán và bản thân khóa đều mạnh.

Ví dụ có lỗi:

~~~text
Key AES-GCM: DEK-v7
Lần mã hóa #1: nonce = 000...001, plaintext = "invoice-A"
Lần mã hóa #2: nonce = 000...001, plaintext = "invoice-B"
                     ^^^^^^^^^
               Trùng nonce dưới cùng DEK!
~~~

Một thiết kế có thể dùng **cùng giá trị nonce** với **hai khóa độc lập khác nhau** mà không tạo ra chính lỗi lặp cặp (key, nonce). Bởi vậy, yêu cầu trọng tâm là **nonce uniqueness *theo từng key material***, không phải xây một bộ đếm toàn cầu cho tất cả khóa trong tổ chức.

Trong chương **Key use** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, hiểu đúng nonce uniqueness có ảnh hưởng trực tiếp đến:

- **Key generation:** sinh DEK bằng CSPRNG/KMS và chọn chiến lược sinh nonce.
- **Key storage/envelope encryption:** lưu nonce cùng ciphertext, tag, encrypted DEK và key version.
- **Key distribution:** nhiều writer dùng cùng DEK cần tránh trùng vùng nonce.
- **Key use:** bảo đảm mọi lần Encrypt dưới cùng material không dùng lại nonce.
- **Key rotation/revocation:** phân biệt thay KEK với thay DEK, chặn writer cũ.
- **KMS/HSM/IAM/audit:** quản lý quyền, giới hạn sử dụng, quan sát và ứng phó lỗi nonce.

**Ghi nhớ ngay:** **Nonce không cần bí mật nhưng phải tuân thủ yêu cầu duy nhất của thuật toán dưới khóa đang dùng**. Một nonce ngẫu nhiên không đồng nghĩa chắc chắn duy nhất.

## 2. Phân biệt key, nonce, IV, counter, salt, AAD và authentication tag

| Thuật ngữ | Vai trò | Có cần bí mật? | Đòi hỏi quan trọng |
|---|---|---|---|
| **Key/DEK** | Bí mật điều khiển Encrypt/Decrypt | Có | Sinh mạnh, đúng purpose và cryptoperiod |
| **Nonce** | Phân biệt các lần dùng khóa theo thuật toán | Thường không | Không trùng dưới key trong AES-GCM/ChaCha20-Poly1305 |
| **IV (Initialization Vector)** | Tham số khởi tạo chế độ mã hóa | Tùy chế độ | Quy tắc khác nhau tùy mode; không đồng nhất mọi IV với nonce GCM |
| **Counter** | Dãy số tăng hoặc thành phần nonce | Không nhất thiết | Không lặp, không tràn, cấp phát nhất quán |
| **Salt** | Tham số KDF/password hashing để phân tách kết quả | Thường không | Theo yêu cầu KDF; **không thay nonce AEAD** |
| **AAD** | Dữ liệu liên kết được xác thực nhưng không mã hóa | Không mặc định | Hai phía dùng cùng bytes; ràng buộc tenant/object/format |
| **Tag** | Kết quả xác thực AEAD | Thường không | Bắt buộc verify; tag sai không trả plaintext |
| **Key ID/material version** | Tham chiếu xác định key | Thường không | Chọn đúng material, không nhầm alias với rotate |

Trong giao diện Java JCA, **GCMParameterSpec** gọi tham số là **IV**, nhưng với cấu hình AES-GCM, nó được sử dụng như nonce/initialization vector của GCM. Không áp dụng nguyên tắc cho mọi mode theo cách máy móc: ví dụ **AES-CBC** cần IV không dự đoán được theo điều kiện an toàn tương ứng, còn **AES-GCM** đặc biệt nhạy với nonce reuse.

### 2.1. Đơn vị để xét uniqueness là gì?

Với một thuật toán AEAD yêu cầu nonce duy nhất, có thể diễn đạt:

\[
\forall i\ne j,\quad
(K_i=K_j) \Rightarrow (N_i \ne N_j)
\]

cho các **lần mã hóa riêng biệt** thuộc phạm vi yêu cầu của thuật toán, với \(K_i\) là key material thực tế và \(N_i\) là nonce.

Trong thực hành, **alias thay đổi** nhưng vẫn trỏ tới cùng material thì không tạo không gian nonce mới. **KEK thay đổi** nhưng **DEK giữ nguyên** cũng không tạo không gian nonce mới.

### 2.2. Nonce không phải một dạng key phụ

Một nonce lưu công khai với ciphertext là bình thường. Kẻ quan sát biết nonce **không đủ giải mã** nếu key mạnh và cặp (key, nonce) không lặp theo quy tắc.

Do vậy:

- Không cần giấu nonce trong một secret store riêng chỉ để “tăng bảo mật”.
- Không dùng nonce làm key hoặc lấy SHA-256(nonce) để suy DEK.
- Không xem việc giữ nonce bí mật là biện pháp chữa reuse.
- Không dùng salt của PBKDF2/scrypt thay cho nonce AES-GCM mà không có thiết kế đúng.

## 3. Điều gì xảy ra khi tái sử dụng nonce dưới AES-GCM?

AES-GCM dùng cơ chế tương đương **counter mode để mã hóa** và **GHASH để xác thực**. Khi dùng lại nonce với cùng key, phần counter-mode có thể tái sử dụng cùng dãy key-stream cho hai plaintext.

Ở mức trực giác:

\[
C_1=P_1\oplus S,\qquad
C_2=P_2\oplus S
\]

nên:

\[
C_1\oplus C_2=P_1\oplus P_2.
\]

Trong đó \(S\) là cùng key-stream phát sinh khi nonce/key bị lặp, và các phép XOR được hiểu trên phần bytes tương ứng. Nếu attacker biết hoặc đoán một plaintext, họ có thể thu được thông tin về plaintext còn lại.

### 3.1. Không chỉ lộ nội dung: xác thực cũng có thể bị phá

GCM còn có cơ chế xác thực dựa trên GHASH. Nonce reuse có thể tạo điều kiện cho attacker suy ra thông tin giúp **giả mạo tag/thông điệp** trong những điều kiện cụ thể. Không được coi đó chỉ là một lỗi “hai ciphertext tiết lộ một chút XOR” mà không ảnh hưởng tính toàn vẹn.

Mức độ khai thác còn phụ thuộc **cấu trúc bản tin, AAD, số thông điệp quan sát được và khả năng chọn plaintext**. Hướng xử lý an toàn là **coi nonce reuse dưới GCM là sự cố mật mã nghiêm trọng**, không chờ chứng minh đã bị khai thác.

### 3.2. Một ví dụ truy vết sự cố

~~~mermaid
flowchart LR
    K["DEK v3"] --> E1["Encrypt P1 với nonce N"]
    K --> E2["Encrypt P2 với nonce N"]
    E1 --> C1["Ciphertext C1 + tag1"]
    E2 --> C2["Ciphertext C2 + tag2"]
    C1 --> X["Đối thủ có cả hai records"]
    C2 --> X
    X --> R["Lộ quan hệ P1 XOR P2; tăng rủi ro giả mạo"]
~~~

**Không phải mọi trường hợp lặp nonce đều lập tức chứng minh attacker đã đọc được toàn bộ plaintext.** Nhưng các bảo đảm an toàn đã bị vi phạm và cần điều tra.

## 4. “Theo key” nghĩa là theo key material, không theo tên file hay alias

Một số tình huống:

| Lần mã hóa | DEK material | Nonce | Đánh giá theo nguyên tắc GCM |
|---|---|---|---|
| Object A | DEK-A | 0x0001 | Hợp lệ nếu chưa dùng nonce đó dưới DEK-A |
| Object B | DEK-A | 0x0002 | Khác nonce, đáp ứng uniqueness ở cặp này |
| Object C | DEK-A | 0x0001 | **Lỗi reuse** dưới DEK-A |
| Object D | DEK-B độc lập | 0x0001 | Không phải reuse với DEK-A |
| Object E | DEK-A được rewrap từ KEK-v1 sang KEK-v2 | 0x0001 | **Vẫn lỗi** vì DEK material chưa đổi |
| Object F | KEK alias đổi nhưng DEK-A vẫn dùng | 0x0001 | **Vẫn lỗi** |
| Object G | DEK-C mới thực sự được sinh | 0x0001 | Có thể dùng trong không gian nonce của DEK-C |

Với **AES-GCM**, không cần nonce duy nhất trong **toàn bộ database** nếu mỗi object có DEK độc lập. Nhưng một object được mã hóa lại **nhiều lần dưới cùng DEK** vẫn cần nonce khác ở mỗi lần Encrypt.

### 4.1. Khóa có cùng bytes nhưng hai ID khác nhau

Nếu hệ thống import cùng bytes AES vào hai key IDs hoặc sao chép DEK material sang service khác, thì hai ID khác nhau **không biến chúng thành hai khóa độc lập**. Không gian nonce vẫn được chia sẻ bởi cùng vật liệu mật mã.

### 4.2. Xét chiều và mục đích dùng khóa

Một giao thức hai chiều nên có **key separation** cho client-to-server và server-to-client hoặc một quy tắc nonce phân tách bảo đảm không trùng theo protocol. Nếu hai phía độc lập cùng dùng một key và counter bắt đầu ở 0, rủi ro lặp xuất hiện ngay khi mỗi phía gửi bản tin đầu tiên.

## 5. Nonce/IV theo từng thuật toán: không đánh đồng

| Thuật toán/chế độ | Tham số | Yêu cầu nổi bật |
|---|---|---|
| **AES-GCM** | Nonce/IV, thường 96 bit | **Uniqueness dưới key** là yêu cầu thiết yếu; reuse gây rủi ro nghiêm trọng |
| **ChaCha20-Poly1305 theo IETF** | Nonce 96 bit | Phải không lặp dưới key; lặp có thể tái sử dụng stream và khóa Poly1305 một lần |
| **XChaCha20-Poly1305** | Nonce 192 bit | Không gian lớn, hỗ trợ random nonces với xác suất va chạm thấp trong giới hạn thiết kế; cần thư viện tương thích |
| **AES-CTR** | Counter/IV | Không lặp **counter blocks** dưới cùng key, kể cả khi có nhiều message |
| **AES-CBC** | IV theo block size | Cần quy tắc IV khó dự đoán khi mã hóa và bảo vệ tính toàn vẹn riêng; không thay bằng “nonce uniqueness” là đủ |
| **AES-GCM-SIV** | Nonce cho AEAD misuse-resistant | Chịu đựng một số trường hợp nonce reuse tốt hơn GCM thông thường, nhưng không miễn phí hoặc cho phép tái sử dụng vô hạn |
| **AES-SIV** | Cơ chế synthetic IV | Có thuộc tính misuse resistance theo thiết kế, nhưng có thể lộ tính bằng nhau/điều kiện khác; cần xem security bounds |
| **TLS 1.3 AEAD** | Nonce do giao thức xây từ IV/sequence number | Phải dùng key schedule, sequence và giới hạn của TLS; không tự thay cơ chế |
| **Password KDF** | Salt | Không phải nonce AEAD; cần salt/params theo chính sách của KDF |

### 5.1. Không tự đưa GCM nonce rule vào mọi thuật toán

Một **IV ngẫu nhiên** có thể phù hợp với một chế độ nhưng không phù hợp với chế độ khác; **counter deterministic** có thể đúng trong AES-GCM khi bảo đảm uniqueness, nhưng không thể dùng để suy rằng IV trong CBC có cùng tính chất.

Khi chọn thuật toán/mode mới, hãy đọc chuẩn và API provider về **nonce/IV construction, maximum invocations, key sizes, tag lengths và state recovery**.

### 5.2. Thư viện XChaCha không có nghĩa API JCA mặc định

Java 17 chuẩn hỗ trợ AES-GCM qua JCA phổ biến. **XChaCha20-Poly1305** cần thư viện/provider cụ thể được kiểm chứng, không giả định có thể gọi tên thuật toán bất kỳ trong Cipher của JDK.

## 6. Nonce ngẫu nhiên và xác suất đụng độ

Khi nonce được chọn **độc lập và đều** từ một không gian \(2^b\) giá trị, xác suất có ít nhất một cặp trùng sau \(q\) lần lấy có thể xấp xỉ theo bài toán birthday:

\[
\Pr[\text{collision}]\approx
1-\exp\left(-\frac{q(q-1)}{2^{b+1}}\right)
\]

Khi \(q\ll 2^{b/2}\), xấp xỉ thường dùng là:

\[
\Pr[\text{collision}]\approx\frac{q(q-1)}{2^{b+1}}.
\]

### 6.1. Ví dụ nonce 96 bit

| Số lần dùng cùng DEK \(q\) | Xấp xỉ xác suất trùng nonce ngẫu nhiên 96 bit |
|---:|---:|
| 1.000 | Khoảng \(6,3\times10^{-24}\) |
| 1.000.000 | Khoảng \(6,3\times10^{-18}\) |
| 1.000.000.000 | Khoảng \(6,3\times10^{-12}\) |
| \(2^{32}\) | Khoảng \(1,16\times10^{-10}\) |

Các con số minh họa theo giả định **nguồn ngẫu nhiên độc lập, đều và không tái tạo trạng thái**. Nếu clone VM hoặc PRNG state được khôi phục cùng seed, giả định independence có thể không đúng và xác suất thực tế không thể đánh giá chỉ bằng công thức này.

**Không coi 96 bit random là bảo đảm uniqueness tuyệt đối.** Nó là một chiến lược cần kết hợp **usage budget** và review theo chuẩn/thuật toán.

### 6.2. Không hiểu sai xác suất nhỏ

Vì lỗi nonce reuse dưới GCM có hậu quả nghiêm trọng, “rất hiếm” vẫn cần đánh giá khi một DEK phục vụ nhiều năm, nhiều instances, multi-region, hoặc nhiều tỷ phép mã hóa. Không được tính riêng mỗi instance nếu chúng chia sẻ **cùng key material**.

## 7. Giới hạn số lần mã hóa theo key và cryptoperiod

Trong quản lý khóa, nonce uniqueness phải được xem cùng **giới hạn số lượng phép mã hóa dưới từng key**. Với AES-GCM, tài liệu chuẩn như NIST SP 800-38D đặt ra các ràng buộc với **cấu trúc IV, số invocations và độ dài dữ liệu**; một số cấu hình dùng random IV phải tuân thủ giới hạn theo chuẩn, chẳng hạn mốc **\(2^{32}\) invocations** trong các điều kiện tương ứng, không được dùng như ngân sách bảo đảm chung cho mọi cấu hình.

Một chính sách sử dụng key nên định nghĩa:

- **Maximum Encrypt operations** dưới material, theo thuật toán, nonce construction và tag length.
- **Maximum bytes/blocks encrypted** và giới hạn bản tin.
- **Time-based cryptoperiod** cho phép tạo bản mã mới.
- **Maximum unique nonces** hoặc giới hạn counter.
- **High-watermark threshold** để chuẩn bị rotation trước khi hết ngân sách.
- **Phạm vi toàn hệ thống**: cộng dồn các writers, regions, jobs và batch operations chia sẻ cùng DEK.
- **Emergency stop** khi phát hiện counter rollback, unknown writer ID hoặc khả năng nonce reuse.

### 7.1. Budget không đồng nghĩa cryptoperiod

Một key được phép dùng trong 90 ngày **không có nghĩa** được phép mã hóa vô hạn bản tin trong 90 ngày. Ngược lại một key còn dưới quota **không có nghĩa** tiếp tục Encrypt nếu đã hết thời hạn hoặc bị revoke.

### 7.2. Đừng tự kết luận từ “AES-256”

Khóa 256 bit không nới lỏng yêu cầu GCM nonce uniqueness. AES-256-GCM vẫn bị nguy cơ reuse nonce dù key material có entropy rất cao.

## 8. Ba chiến lược phổ biến để bảo đảm uniqueness

| Chiến lược | Cách làm | Ưu điểm | Giới hạn và yêu cầu |
|---|---|---|---|
| **Random nonce** | SecureRandom tạo nonce mới, ví dụ 96 bit cho AES-GCM | Dễ dùng trong từng instance, không cần counter tập trung | Xác suất collision; trạng thái RNG sau clone/snapshot; giới hạn số lần dưới DEK |
| **Deterministic nonce** | Counter/sequence không lặp theo DEK | Có thể bảo đảm uniqueness có điều kiện | Phải có state bền vững, không rollback, kiểm soát concurrency/overflow |
| **DEK riêng theo object/message** | Generate key mới theo phạm vi, nonce theo mỗi key | Giảm việc phối hợp nonce giữa các objects | Chi phí key generation/wrap/storage; vẫn phải đúng quy tắc nếu cùng DEK mã hóa lại |

### 8.1. Không có “chiến lược tốt nhất” cho mọi hệ thống

- **Backup offline một file:** DEK ngẫu nhiên riêng file, nonce ngẫu nhiên cho một operation có thể hợp lý theo threat model.
- **Streaming nhiều chunk:** cần protocol nonce/chunk indices và tính toàn vẹn tổng thể.
- **High-throughput multiwriter cùng key:** deterministic nonce với phân vùng writer/counter thường dễ chứng minh hơn random không giới hạn.
- **KMS Encrypt API:** nếu provider tự sinh IV/nonce và quản lý an toàn, ứng dụng không nên tự thay bằng tham số không được kiểm soát.

### 8.2. Không dùng timestamp một mình làm nonce

Timestamp theo millisecond có thể trùng khi nhiều threads cùng Encrypt, đồng hồ có thể lùi, tiến trình có thể khởi động lại hoặc các máy có đồng hồ tương tự. **Timestamp không phải cơ chế bảo đảm uniqueness** trừ khi nằm trong một giao thức được thiết kế và kiểm chứng tổng thể.

## 9. Thiết kế deterministic nonce: writer ID và counter

Một cấu trúc minh họa cho **nonce AES-GCM 96 bit**:

~~~text
+--------------------------+---------------------------------------+
| writerId: 32 bit         | monotonic counter: 64 bit             |
+--------------------------+---------------------------------------+
|                   nonce = 12 bytes                              |
+-----------------------------------------------------------------+
~~~

Mục tiêu là mỗi writer được cấp **writerId duy nhất trong phạm vi DEK**, còn counter dưới writerId **không bao giờ dùng lại** trong thời gian DEK còn được dùng Encrypt.

### 9.1. Điều kiện đúng

1. **writerId không trùng** giữa các writers chia sẻ cùng DEK, bao gồm sau restart/scale-out.
2. **Counter được cấp phát nguyên tử và bền vững** trước khi dùng.
3. **Rollback/failover không cấp lại counter đã dùng**, kể cả khi bản ghi ciphertext chưa commit.
4. **Counter không overflow** và không bị tự đặt lại về 0 khi process restart.
5. **Không cho clone VM** dùng lại writerId + counter state cùng DEK.
6. **Key ID/material version** là một phần của kho cấp phát nonce và audit.
7. **Revoke/rotate** phải chặn writer cũ tiếp tục mã hóa khi hết quota hoặc policy.

### 9.2. Counter range leasing

Để tránh gọi DB/KMS mỗi lần Encrypt, một allocator có thể cấp trước một **dải counter** cho writer:

~~~text
DEK-v12 / writerId=47
  lease A -> counter 1000..1999
  lease B -> counter 2000..2999

Mỗi lần Encrypt lấy một counter chưa dùng trong lease.
Nếu worker chết: phần còn lại của lease cũ bị bỏ.
Không cấp lại các counter đã reserve.
~~~

Bất kỳ cơ chế lease nào cũng cần **atomic reservation, durable high-watermark và fencing** phù hợp. Không tái cấp vùng counter vì nghĩ một job “chắc chưa gửi bản mã ra ngoài”.

### 9.3. Không dùng bộ đếm trong RAM làm nguồn sự thật

~~~java
// ANTI-PATTERN: counter mất khi restart.
// Khi cùng DEK được dùng lại, nonce có thể lặp.
long nonceCounter = 0L;
~~~

AtomicLong giúp tránh hai threads lấy cùng một giá trị **trong một process đang chạy**, nhưng **không** giải quyết reboot, snapshot restore, region failover hoặc hai instances khác nhau.

## 10. Multiwriter và multi-region: bài toán cấp phát nonce thực tế

~~~mermaid
flowchart TD
    K["DEK material v8"] --> A["Writer A - region 1"]
    K --> B["Writer B - region 1"]
    K --> C["Writer C - region 2"]
    N["Durable nonce allocator / writer-id registry"] --> A
    N --> B
    N --> C
    A --> S["Encrypted object store"]
    B --> S
    C --> S
    S --> Q["Audit theo DEK, writer, counter và key version"]
~~~

Ba writer dùng cùng DEK phải tuân một **toàn cục uniqueness domain đối với DEK đó**, không phải mỗi writer tự đếm từ 0 mà không phân vùng.

### 10.1. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả |
|---|---|
| Mỗi instance chạy counter 0,1,2… dưới cùng DEK | Trùng nonce ngay giữa instances |
| Random writerId mỗi lần boot nhưng không kiểm tra trùng | Không có bảo đảm uniqueness theo mô hình deterministic |
| Container snapshot giữ cùng writerId/counter/DEK | Hai bản clone có thể phát cùng nonce |
| DB failover phục hồi high-watermark cũ | Cấp lại counters đã dùng ở node khác |
| Retry request mà reuse nonce với plaintext khác | Lặp cặp (key,nonce), rủi ro GCM |
| Hai vùng tự cấp phát cùng range | Collision khi replication hoặc network partition |
| Alias/KEK đổi nhưng DEK cũ giữ nguyên | Counter reset sai vì nhầm key version |
| Thay key ID nhưng import cùng key bytes | Nonce state bị phân đôi dù vật liệu giống |

### 10.2. “Exactly once” không thể chỉ dựa vào HTTP hoặc queue ACK

Một Encrypt operation có thể tạo ciphertext, sau đó timeout trước khi caller nhận ACK. Caller không biết operation đã ghi ra storage hay chưa. Thiết kế an toàn cần **idempotency và state**:

- Nếu retry có thể **tái sử dụng đúng record bất biến đã được commit** theo protocol được kiểm chứng, không thực hiện lần mã hóa mới với cùng nonce và plaintext khác.
- Nếu cần **mã hóa lại**, cấp **nonce mới chưa từng dùng** dưới DEK.
- Không phát hành lại counter đã reserve chỉ vì ACK thất bại.
- Phân biệt “retry gửi lại ciphertext đã tạo” với “retry gọi Encrypt tạo ciphertext mới”.

### 10.3. Network partition và lỗi allocator

Nếu không thể chứng minh một range chưa được cấp ở vùng khác, fail-closed cho việc tạo ciphertext mới hoặc dùng DEK/namespace tách biệt đã được thiết kế. **Không tự fallback về nonce random/timestamp** trộn với deterministic layout mà không bảo đảm hai miền nonce rời nhau.

## 11. Retry, idempotency và nonce reuse

**Retry** là một trong những nguồn gây trùng nonce khó nhận ra nhất ở hệ thống phân tán. Cần phân biệt ba tình huống:

| Tình huống | Cách xử lý |
|---|---|
| Gửi lại **chính xác ciphertext, nonce, tag và AAD đã tạo** để hoàn thành ghi idempotent | Không phải thực hiện thêm phép Encrypt với cùng nonce; có thể hợp lệ khi protocol bảo đảm nội dung không đổi và record được quản lý đúng |
| Thực hiện **Encrypt mới** cùng plaintext dưới cùng DEK | Cấp nonce **mới**, không tái sử dụng nonce của operation trước |
| Thực hiện Encrypt lại với plaintext/AAD đã thay đổi | Bắt buộc dùng nonce mới nếu DEK giữ nguyên; cần kiểm soát revision và object identity |

### 11.1. Encrypt và persist là hai trạng thái khác nhau

~~~mermaid
stateDiagram-v2
    [*] --> RESERVED: Cấp nonce/chọn DEK
    RESERVED --> ENCRYPTED: AEAD Encrypt
    ENCRYPTED --> PERSISTING: Ghi ciphertext + metadata
    PERSISTING --> COMMITTED: Xác nhận bền vững
    PERSISTING --> RECONCILE: Timeout / trạng thái không rõ
    RECONCILE --> COMMITTED: Đã có record đúng operationId
    RECONCILE --> RETRY_NEW_NONCE: Cần Encrypt lại
    RETRY_NEW_NONCE --> RESERVED: Lấy nonce chưa dùng
    COMMITTED --> [*]
~~~

Nếu storage **trả timeout sau khi đã ghi thành công**, thao tác tiếp theo cần **đọc lại theo operationId/revision** rồi quyết định gửi lại bản mã hay mã hóa lại với nonce mới. Không được mặc nhiên reset counter hoặc lấy lại nonce cũ cho một payload khác.

### 11.2. AEAD tag hợp lệ không thay nonce policy

Dùng lại nonce và cùng plaintext có thể tạo ciphertext/tag giống nhau trong một số cấu hình, nhưng **đừng dựa vào điều đó làm quy tắc retry chung**. Thực hiện một phép Encrypt mới dưới nonce đã dùng vẫn đi ngược thiết kế uniqueness; nếu cần gửi lại, **tái gửi chính record bất biến**, không gọi Encrypt lại.

### 11.3. Idempotency key và nonce là hai biến khác nhau

**operationId** giúp backend biết một giao dịch đã được xử lý; nó không tự là nonce trừ khi có thiết kế ánh xạ được kiểm chứng. Một operationId có thể chứa UUID ngẫu nhiên hoặc giá trị người dùng cung cấp, không bảo đảm uniqueness của nonce trong namespace DEK.

## 12. Envelope encryption và KMS: KEK rotation không đặt lại nonce của DEK

Trong envelope encryption:

- **DEK** mã hóa payload bằng AEAD.
- **KEK** trong KMS/HSM wrap/unwrap DEK.
- **Encrypted DEK** được lưu cạnh ciphertext, cùng nonce/tag và key reference.
- **KEK material version** không nhất thiết là **DEK material version**.

~~~mermaid
flowchart TD
    P["Plaintext + trusted AAD"] --> E["AES-GCM Encrypt với DEK-A"]
    K["DEK-A"] --> E
    E --> C["Ciphertext + nonce + tag"]
    K --> W1["Wrap DEK-A dưới KEK-v1"]
    W1 --> D1["EncryptedDEK-v1"]
    D1 --> R["KMS Rewrap sang KEK-v2"]
    R --> D2["EncryptedDEK-v2"]
    D2 --> S["Envelope sau rotation"]
    C --> S
    N["Nonce state của DEK-A không đổi!"] --> K
~~~

### 12.1. Vì sao rewrap không tạo nonce namespace mới?

Khi KEK-v1 → KEK-v2, lớp bảo vệ của DEK thay đổi, nhưng **DEK bytes vẫn là DEK-A**. Nếu writer tiếp tục mã hóa bằng DEK-A, các nonces mới vẫn phải khác **mọi nonce đã dùng từ trước dưới DEK-A**.

**Đổi alias KMS, đổi encryptedDEK bytes hoặc đổi keyRef không phải là RotateDEK.**

### 12.2. Khi thay DEK thật

Nếu generate **DEK-B mới độc lập** bằng CSPRNG/KMS, DEK-B có nonce namespace của riêng mình. Tuy nhiên:

- Mọi writer phải biết chính xác **DEK material version** đang dùng.
- Không được lẫn DEK-A và DEK-B trong record khi schema không ghi version.
- Old writers phải dừng Encrypt bằng DEK-A khi hết cryptoperiod hoặc có incident.
- Reader vẫn có thể cần DEK-A để Decrypt dữ liệu lịch sử, trong giới hạn policy.
- Nếu DEK-A bị compromise/nonce reuse, cần **đánh giá re-encrypt** dữ liệu đã tạo dưới material đó; chỉ chuyển writer mới không cứu dữ liệu cũ.

### 12.3. KMS không tự nhìn thấy nonce của payload

Khi ứng dụng gọi **GenerateDataKey**, sau đó tự mã hóa AES-GCM trong JVM, KMS có thể **không quan sát từng nonce hoặc số lần Encrypt**. KMS biết những lần cấp/unwrap/wrap, không mặc nhiên biết ứng dụng đã dùng DEK bao nhiêu lần.

Vì vậy **nonce usage budget** phải do ứng dụng, key registry hoặc provider encryption API tương ứng kiểm soát, tùy kiến trúc.

### 12.4. Đừng dùng chung DEK across tenants vì thuận tiện

Nếu mọi tenant chia sẻ một DEK, tất cả requests thuộc cùng nonce namespace và một lỗi phân bổ nonce có thể ảnh hưởng nhiều khách hàng. **DEK riêng theo object, tenant hoặc domain** tùy threat model làm giảm blast radius và giảm áp lực phối hợp nonce.

## 13. Java 17: AES-GCM với DEK mới cho mỗi object

Đoạn sau minh họa **một DEK mới cho mỗi object encrypted record**, cách làm giảm nhu cầu phối hợp nonces giữa các objects. KMS abstraction sẽ generate DEK và bọc nó dưới KEK; **KEK dạng rõ không rời KMS**.

Đây là mẫu minh họa thiết kế, **không phải KMS SDK hoàn chỉnh**. KeyService cần implementation thực tế và caller phải xác thực/ủy quyền tenant/object trước khi gọi.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class PerObjectDekGcmExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    public record GeneratedDataKey(
        byte[] plaintextDek,
        byte[] encryptedDek
    ) {}

    public interface KeyService {
        GeneratedDataKey generateDataKey(
            String authorizedKekRef,
            Map<String, String> context
        ) throws Exception;

        byte[] unwrapDataKey(
            String authorizedKekRef,
            byte[] encryptedDek,
            Map<String, String> context
        ) throws Exception;
    }

    public record CipherRecord(
        String tenantId,
        String objectId,
        String kekRef,
        byte[] encryptedDek,
        byte[] nonce,
        byte[] ciphertextAndTag
    ) {}

    private static Map<String, String> context(
            String tenant, String objectId) {
        return Map.of(
            "tenant", tenant,
            "object", objectId,
            "purpose", "document-encryption"
        );
    }

    // Stable length-prefixed AAD, dựa vào identity đã xác thực.
    private static byte[] aad(
            String tenant, String objectId) {
        byte[] a = tenant.getBytes(StandardCharsets.UTF_8);
        byte[] b = objectId.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(8 + a.length + b.length)
            .putInt(a.length).put(a)
            .putInt(b.length).put(b)
            .array();
    }

    public static CipherRecord encryptNewObject(
            KeyService kms,
            String authorizedKekRef,
            String tenantId,
            String objectId,
            byte[] plaintext
    ) throws Exception {
        Objects.requireNonNull(kms);
        Objects.requireNonNull(plaintext);
        if (authorizedKekRef == null || tenantId == null
                || objectId == null || tenantId.isBlank()
                || objectId.isBlank()) {
            throw new IllegalArgumentException("Invalid object scope");
        }

        // Production: phải xác minh object/tenant ownership tại caller.
        GeneratedDataKey generated = kms.generateDataKey(
            authorizedKekRef, context(tenantId, objectId));
        if (generated == null
                || generated.plaintextDek() == null
                || generated.plaintextDek().length != 32
                || generated.encryptedDek() == null
                || generated.encryptedDek().length == 0) {
            throw new IllegalStateException("Unexpected KMS response");
        }

        byte[] dek = generated.plaintextDek();
        try {
            // Mẫu này chỉ dùng DEK mới cho một lần Encrypt.
            byte[] nonce = new byte[NONCE_BYTES];
            RNG.nextBytes(nonce);

            Cipher cipher = Cipher.getInstance(
                "AES/GCM/NoPadding");
            cipher.init(
                Cipher.ENCRYPT_MODE,
                new SecretKeySpec(dek, "AES"),
                new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(tenantId, objectId));

            return new CipherRecord(
                tenantId, objectId, authorizedKekRef,
                generated.encryptedDek().clone(),
                nonce,
                cipher.doFinal(plaintext));
        } finally {
            // Xóa best-effort mảng trả về từ KMS SDK.
            // Provider/JVM có thể còn bản sao nội bộ khác.
            Arrays.fill(dek, (byte) 0);
        }
    }

    public static byte[] decrypt(
            KeyService kms,
            String expectedKekRef,
            String trustedTenant,
            String trustedObjectId,
            CipherRecord record
    ) throws Exception {
        Objects.requireNonNull(kms);
        Objects.requireNonNull(record);
        if (!Objects.equals(expectedKekRef, record.kekRef())
                || !Objects.equals(trustedTenant, record.tenantId())
                || !Objects.equals(trustedObjectId, record.objectId())
                || record.nonce() == null
                || record.nonce().length != NONCE_BYTES
                || record.ciphertextAndTag() == null
                || record.ciphertextAndTag().length < 16
                || record.encryptedDek() == null) {
            throw new SecurityException("Scope or format mismatch");
        }

        byte[] dek = kms.unwrapDataKey(
            expectedKekRef,
            record.encryptedDek(),
            context(trustedTenant, trustedObjectId));
        if (dek == null || dek.length != 32) {
            throw new SecurityException("Invalid DEK");
        }
        try {
            Cipher cipher = Cipher.getInstance(
                "AES/GCM/NoPadding");
            cipher.init(
                Cipher.DECRYPT_MODE,
                new SecretKeySpec(dek, "AES"),
                new GCMParameterSpec(TAG_BITS, record.nonce()));
            cipher.updateAAD(aad(trustedTenant, trustedObjectId));
            // Tag được kiểm tra ở doFinal.
            return cipher.doFinal(record.ciphertextAndTag());
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }
}
~~~

### 13.1. Vì sao một DEK cho mỗi object giảm áp lực nonce?

Nếu mỗi record được mã hóa **một lần dưới một DEK được sinh độc lập**, mỗi DEK chỉ cần một nonce cho operation đó. Nhưng **không được tái sử dụng cùng DEK** khi object được cập nhật lần hai trừ khi nonce mới vẫn được cấp an toàn.

### 13.2. Các giới hạn của ví dụ

- **KeyService chưa triển khai**: cần KMS/SDK thật với IAM, key policy, context và audit.
- **Không có persistence, idempotency, key inventory hoặc rotation**; app phải lưu đầy đủ encrypted DEK, nonce, tag và key reference.
- **Mỗi object một DEK** cần đánh giá KMS throughput, cost, key caching và backup.
- **Random nonce** vẫn cần chất lượng CSPRNG; mẫu dựa vào giả định mỗi material thực sự mới.
- **CipherRecord chứa mutable arrays**, production cần defensive copy/serialization và input bounds.
- **Không dùng constructor trực tiếp** làm public API cho dữ liệu chưa tin cậy nếu chưa có parser validation và size limits.
- **Người gọi phải xác thực business authorization**; tên tham số trustedTenant không tự cấp quyền.
- **Không tạo plaintext KEK** trong code để giả lập provider.
- **Arrays.fill không đảm bảo xóa mọi bản sao của SecretKey trong JVM**.

### 13.3. Bài học triển khai

Mẫu này giải quyết bài toán **sinh DEK và nonce cho một lần Encrypt** theo cách tách vật liệu theo object; nó không tự động giải quyết **nhiều writers cùng DEK, streaming/chunking, replay, KMS grants hoặc key recovery**.

## 14. Java 17: deterministic nonce từ writer ID và counter cấp phát bền vững

Khi một DEK phải được dùng nhiều lần, có thể áp dụng nonce construction theo **writerId 32 bit + counter 64 bit**, nhưng uniqueness chỉ đúng nếu **writer ID và counter được cấp phát đúng trong hệ thống phân tán**.

Đoạn mẫu cố ý để **NonceAllocator** là interface: nó phải có triển khai **transactional/durable** tại infrastructure, không dùng AtomicLong trong RAM rồi tự gọi là an toàn.

~~~java
import java.nio.ByteBuffer;
import java.util.Objects;

public final class DurableNonceExample {
    // Định danh chính xác material; không chỉ là KEK alias.
    public record DekIdentity(
        String materialId,
        String materialVersion
    ) {}

    // Mỗi claim duy nhất theo DEK material.
    public record NonceClaim(
        int writerId,
        long counter
    ) {}

    public interface NonceAllocator {
        // Transactional, durable, không cấp lại claim.
        // Chịu trách nhiệm phân vùng writer ID và fencing.
        NonceClaim reserveNext(DekIdentity dek)
            throws Exception;
    }

    public static byte[] nextGcmNonce(
            NonceAllocator allocator,
            DekIdentity dek
    ) throws Exception {
        Objects.requireNonNull(allocator);
        Objects.requireNonNull(dek);
        if (dek.materialId() == null
                || dek.materialVersion() == null
                || dek.materialId().isBlank()
                || dek.materialVersion().isBlank()) {
            throw new IllegalArgumentException("Invalid DEK identity");
        }

        NonceClaim claim = allocator.reserveNext(dek);
        if (claim == null || claim.counter() < 0) {
            throw new IllegalStateException("Nonce state exhausted");
        }

        // 32-bit writerId + 64-bit counter -> 96-bit nonce.
        // Chỉ dùng counters 0..Long.MAX_VALUE trong Java.
        return ByteBuffer.allocate(12)
            .putInt(claim.writerId())
            .putLong(claim.counter())
            .array();
    }
}
~~~

### 14.1. Không gian nonce và endianness

Java ByteBuffer mặc định dùng **big-endian**. Bên decrypt chỉ cần **12 bytes nonce nguyên vẹn** đã lưu, nên không cần tái tạo từ counter. Nếu các dịch vụ khác ngôn ngữ phối hợp cấp nonce, phải tài liệu hóa **byte layout, bit width, unsigned/signed representation và writer ID registration**.

### 14.2. Tính an toàn không nằm trong 12 byte ByteBuffer

Nếu NonceAllocator cấp cùng NonceClaim hai lần dưới cùng DekIdentity, cả hai calls sẽ cho cùng nonce. Mẫu code **không thể bù** cho allocator thiếu tính nhất quán.

Một triển khai production nên có:

- **Uniqueness constraint**/atomic transaction hoặc cơ chế distributed consensus phù hợp.
- **Durable commit** trước khi trả claim để dùng Encrypt.
- **Monotonic high-watermark** và failover không rollback.
- **Fencing tokens** để ngăn worker cũ dùng lại vùng được cấp.
- **Version/material identity** không đổi khi chỉ rewrap KEK.
- **Exhaustion checks** và rotation trước khi hết ngân sách/khả năng counter.
- **Audit** metadata cấp phát, không log key bytes.

### 14.3. Không trộn random và deterministic construction tùy tiện

Nếu cùng DEK đã có nonce **random 96-bit** và sau đó một writer chuyển sang nonce **writerId||counter**, hai tập vẫn có thể trùng. Muốn đổi strategy dưới cùng DEK phải chứng minh **hai nonce namespaces rời nhau** theo chuẩn/chính sách, hoặc an toàn hơn là **Generate DEK mới** rồi dùng strategy mới.

## 15. Record schema: nonce phải gắn với đúng key material và ciphertext

Một envelope record minh họa:

~~~json
{
  "formatVersion": 2,
  "algorithm": "AES-256-GCM",
  "tenantId": "tenant-42",
  "objectId": "invoice-901",
  "dekMaterialId": "dek-object-901",
  "dekMaterialVersion": "v1",
  "kekRef": "kms/prod/orders-kek",
  "encryptedDek": "BASE64_WRAPPED_DEK",
  "nonce": "BASE64_12_BYTE_NONCE",
  "ciphertextAndTag": "BASE64_CIPHERTEXT_WITH_TAG",
  "aadSchemaVersion": 2,
  "recordRevision": 17
}
~~~

Đây là **placeholder schema**, không phải payload KMS chuẩn. Một số KMS lưu key/material version trong encrypted DEK blob, còn một số cung cấp reference khác. **Không tự bịa key version nếu provider không có**; thay vào đó định nghĩa format và key identity thực tế.

### 15.1. Metadata cần giữ ổn định đến khi Decrypt

| Trường | Vai trò |
|---|---|
| **nonce** | Phải chính xác byte array lúc Encrypt; không tự tạo lại ngẫu nhiên khi đọc |
| **encryptedDek/kekRef** | Tìm và unwrap đúng DEK để Decrypt |
| **algorithm/tag length** | Chọn AEAD mode, reject downgrade hoặc format không hợp lệ |
| **key/material version** | Kiểm kê usage và phân biệt DEK cũ/mới |
| **tenant/object/purpose** | Hỗ trợ trusted AAD và business authorization |
| **recordRevision** | Ngăn stale update và race khi migration |
| **createdAt/rotation epoch** | Audit và policy; không dùng timestamp như nonce duy nhất |

### 15.2. Nonce và tag thường không bí mật

Lưu nonce cạnh ciphertext là một phần thiết kế AEAD bình thường. Không lưu **plaintext DEK** cạnh ciphertext. KMS KEK cần được bảo vệ độc lập; keyRef không phải credential.

### 15.3. AAD bảo vệ ngữ cảnh, không cứu nonce reuse

AAD có thể giúp ngăn tráo object/tenant khi cùng DEK, nhưng nếu cặp (DEK, nonce) đã bị lặp, **đổi AAD không làm phép Encrypt an toàn**. Nonce uniqueness và metadata authentication là hai yêu cầu riêng.

### 15.4. Chunked encryption

Nếu một file được chia thành nhiều chunks AEAD:

- Mỗi chunk dưới cùng DEK phải có **nonce riêng**.
- AAD có thể chứa **file ID, chunk index, expected total count, stream version**.
- Cần bảo vệ tính **đầy đủ và thứ tự** của stream, tránh truncate/reorder khi từng chunk tag riêng vẫn hợp lệ.
- Không reset counter về 0 giữa các phiên ghi chunk với cùng DEK.
- Mỗi file/stream có thể dùng DEK riêng để giảm phối hợp, tùy memory/throughput.

## 16. Rotation: không reset nonce state sai thời điểm

| Thao tác | DEK material có đổi? | Nonce namespace | Ghi chú |
|---|---|---|---|
| KMS alias chỉ đổi tên | Không | **Giữ nguyên** | Alias không làm key bytes mới |
| **KEK rotation** + rewrap encrypted DEK | Không | **Giữ nguyên** | DEK vẫn mã hóa payload |
| Đổi IAM grant hoặc KMS policy | Không | **Giữ nguyên** | Chỉ thay quyền |
| Chuyển DEK material qua HSM khác (same bytes) | Không | **Giữ nguyên** | Không gian nonce theo bytes |
| Sinh DEK mới độc lập | **Có** | Namespace mới | Mọi writer cần chuyển key version |
| Re-encrypt data với DEK mới | **Có** | Namespace mới | Cần nonce/tag mới cho ciphertext mới |
| Disable/Suspend DEK usage | Không | Không cấp nonce mới để Encrypt | Reader historical theo policy |
| Revoke vì nonce reuse | Thường tạo material mới | Chặn Encrypt cũ, đánh giá data lịch sử | Không sửa lỗi cũ chỉ bằng đổi alias |

### 16.1. Producer và consumer phải đồng bộ key epoch

Trong quá trình chuyển DEK-v3 → DEK-v4, hệ thống có thể tạm đọc cả hai version nhưng chỉ cho **Encrypt mới dưới v4**. Mỗi record phải chỉ rõ version và encrypted DEK tương ứng. Không gửi writer stale trở lại v3 sau khi đã khóa Encrypt v3.

### 16.2. Không hủy DEK/KEK để “dọn nonce” nếu còn dữ liệu

Nonce reuse là lý do **dừng sử dụng key** và xử lý bảo mật; nhưng **Destroy vật liệu không thể đảo ngược** trong khi backup/DEK phụ thuộc còn tồn tại có thể gây mất dữ liệu. Thực hiện containment, inventory, re-encrypt/migrate, restore validation rồi mới xử lý destruction theo policy.

### 16.3. KMS RotateKey tự động có thể chưa phải DEK rotation

Một KMS managed-key rotation có thể thay material KEK để bọc key nhưng không thay **mọi DEK do ứng dụng đã tạo**. Không tuyên bố “GCM nonce space reset sau khi bật KMS automatic rotation” nếu không chứng minh chính DEK bytes đã đổi.

## 17. API Decrypt và retry: nonce reuse không phải lỗi ở Decrypt

Nonce uniqueness chủ yếu áp dụng cho **các lần Encrypt**. Để giải mã cùng một record, ứng dụng thường **dùng lại đúng key và nonce đã lưu** nhiều lần, điều này **không phải** thực hiện các phép Encrypt mới và không tạo lỗi nonce reuse cùng loại.

Ví dụ:

~~~text
Encrypt lần 1:
  DEK-A + nonce-7 + plaintext -> ciphertext/tag

Decrypt lần 1:
  DEK-A + nonce-7 + ciphertext/tag -> plaintext (tag OK)

Decrypt lần 2:
  DEK-A + nonce-7 + ciphertext/tag -> plaintext (tag OK)
~~~

Hai lần Decrypt dùng nonce-7 là bình thường theo chức năng xác thực bản mã. Điều cần cấm là một **lần Encrypt thứ hai dưới DEK-A với nonce-7**.

### 17.1. Replay attack là vấn đề khác

Một ciphertext/tag hợp lệ có thể bị **replay** nếu business protocol không kiểm tra operation ID, sequence, timestamp/challenge hoặc trạng thái giao dịch. **Unique nonce khi Encrypt không tự tạo anti-replay**: attacker có thể gửi lại chính ciphertext và tag hợp lệ đã quan sát.

Thiết kế cần phân biệt:

- **Nonce uniqueness:** tránh dùng trùng (key, nonce) cho các phép Encrypt riêng.
- **Replay protection:** tránh xử lý lại một thông điệp hợp lệ nhưng đã hết hiệu lực/đã dùng.
- **Business idempotency:** tránh tạo giao dịch trùng khi retry.
- **AEAD tag verification:** từ chối bản mã bị sửa nhưng không tự phát hiện replay.

## 18. Key agreement, traffic keys và nonce ở các giao thức đã chuẩn hóa

Các giao thức như **TLS 1.3** không yêu cầu ứng dụng tự sinh nonce theo timestamp hoặc SecureRandom cho từng record. Chúng định nghĩa **key schedule, implicit nonce/IV và record sequence** cụ thể.

Nếu ứng dụng xây một protocol truyền thông riêng trên X25519/ECDHE:

1. Phải xác thực đúng peer và transcript.
2. Dẫn xuất secret thành **traffic keys riêng cho từng hướng** qua KDF/giao thức phù hợp.
3. Định nghĩa nonce construction/sequence/epoch rõ ràng.
4. Chặn counter rollback, reorder/replay theo protocol.
5. Rotate/rekey trước giới hạn số record/bytes.
6. Không dùng trực tiếp raw ECDH output làm key AES.

**Không sao chép ý tưởng “XOR seq với IV” từ TLS 1.3 vào một giao thức tự chế** mà thiếu các phần còn lại của key schedule và security proofs.

## 19. Thuật toán misuse-resistant: có thay được nonce uniqueness không?

Một số AEAD như **AES-GCM-SIV** hoặc **AES-SIV** được thiết kế để giảm mức độ thảm họa khi nonce bị sử dụng lại, so với AES-GCM thông thường. Nhưng **misuse-resistant không đồng nghĩa reuse nonce vô hạn không có tác dụng phụ**.

### 19.1. Trade-off của misuse resistance

- Có thể để lộ **sự bằng nhau của plaintext/AAD** trong điều kiện tái sử dụng nonce hoặc đặc tính determinism của thuật toán.
- Giới hạn về số phép toán, dữ liệu và security bounds vẫn tồn tại.
- API/provider và hiệu năng có thể khác.
- Không tự động thay authorization, replay protection, key rotation hay nonce allocation.
- Không thể dùng ciphertext AES-GCM cũ như GCM-SIV bằng cách đổi string algorithm.

### 19.2. Khi nào cân nhắc?

Nếu một kiến trúc **khó bảo đảm nonce uniqueness** do offline writers, storage snapshots hoặc distributed operation, một misuse-resistant AEAD được chuẩn hóa và thư viện được đánh giá có thể là lựa chọn phù hợp **trong threat model và giới hạn sử dụng**. Tuy nhiên, vẫn nên thiết kế nonce/key management tốt thay vì cố ý lặp nonce.

### 19.3. Không dùng thuật toán “mạnh hơn” để bỏ tính toán usage

Ngay cả AES-256-GCM-SIV hoặc một mode misuse-resistant có thể có giới hạn bảo mật riêng. Cần chọn theo **yêu cầu data size, keying, performance, protocol compatibility và security analysis**, không chỉ vì tên mode có chữ SIV.

## 20. Quan sát nonce usage và xây dựng key inventory

Một hệ thống AEAD có nhiều writers cần biết **ai đang dùng key material nào và đã dùng đến đâu**, không chỉ việc “KMS đang bật”. Key inventory cần định danh **DEK thật**, không dựa duy nhất vào alias của KEK.

| Nhóm | Thông tin | Mục đích |
|---|---|---|
| **Key identity** | DEK material ID/version, KEK reference, provider | Xác định nonce namespace |
| **Algorithm** | AES-GCM/ChaCha20-Poly1305, nonce construction, tag length | Kiểm tra yêu cầu và giới hạn tương ứng |
| **Owner/purpose** | Service, data owner, tenant/domain, allowed usage | Phân trách nhiệm |
| **Writers** | Writer IDs, regions, active leases và fencing status | Ngăn cấp trùng nonce giữa các consumers |
| **Usage** | Encrypt count/bytes/blocks, counter high-watermark | Theo dõi key usage budget |
| **Lifecycle** | Activated, rotated, retired, revoked | Không dùng Encrypt ngoài cryptoperiod |
| **Observability** | Operation IDs, allocation conflicts, rollback alerts | Điều tra concurrency/failover |
| **Dependencies** | Ciphertext objects, encrypted DEKs, backups | Migration và destruction an toàn |

### 20.1. Có cần ghi mọi nonce vào log?

Không phải lúc nào cũng cần ghi mỗi nonce vào audit tập trung. Có thể ghi **counter ranges đã cấp, writer ID, key material version và operation ID**, đồng thời duy trì cơ chế kiểm soát uniqueness ở đường Encrypt.

Nếu hệ thống cần **phát hiện cặp trùng ở từng operation**, dữ liệu quan sát phải bao phủ những lần Encrypt thực sự, bao gồm operation sau retry, vùng khác và những ciphertext đã bị ghi đè. Chỉ log các records còn tồn tại không đủ chứng minh không có reuse.

### 20.2. Một hash set cục bộ không bao quát mọi writers

Hash set trong một process chỉ phát hiện nonces trùng **bên trong chính process đó**. Nó không thấy encryptions ở pods khác, backup jobs, vùng khác hoặc hoạt động trước khi restart.

Nếu dùng deterministic nonces, nguồn cấp phát phải **durable, atomic, có phân vùng và được kiểm soát ở toàn bộ phạm vi DEK**.

### 20.3. Một số chỉ số hữu ích

| Chỉ số | Ý nghĩa |
|---|---|
| **Active key usage / budget** | Số Encrypt operations/bytes so với ngưỡng của DEK |
| **Nonce allocation conflicts** | Số claim bị phát hiện trùng |
| **Writer ID conflicts** | Nguy cơ hai writers cùng namespace |
| **Counter rollback detections** | Dấu hiệu failover/snapshot phục hồi state cũ |
| **Stale-key Encrypt attempts** | Writer chưa chuyển DEK version |
| **AEAD authentication failures** | Có thể do tamper, sai AAD/key/nonce/format; **không tự chứng minh reuse** |
| **DEK provenance gaps** | Material không xác định được origin/version |
| **Recovery readiness** | Khả năng restore encrypted DEK/nonce/tag với KEK đúng |

### 20.4. GCM tag vẫn có thể hợp lệ sau một lần nonce reuse

Hai records mã hóa bằng cùng (DEK, nonce) có thể **đều tự decrypt và verify tag thành công**. Vì vậy **không thấy authentication failure không chứng minh nonce uniqueness**.

## 21. Kiểm thử nonce uniqueness: từ unit test đến chaos/failover

Để chứng minh kiến trúc quản lý nonce đúng, cần kết hợp **positive tests, negative tests, concurrency và failure injection**.

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Hai lần Encrypt dưới cùng DEK | Nonce khác nhau |
| Hai DEK độc lập dùng cùng nonce | Không bị coi là reuse dưới một key |
| Hai key IDs import cùng key bytes | Có kiểm soát để không tách nonce state sai |
| Rewrap KEK giữ nguyên DEK | Không reset nonce/counter |
| Đổi KMS alias nhưng DEK material giữ nguyên | Nonce namespace giữ nguyên |
| Generate DEK mới thật | Namespace và usage budget mới |
| Hai threads tranh counter | Atomic reservation, mỗi claim duy nhất |
| Hai pods đồng thời Encrypt dưới cùng DEK | Không cấp lại cùng nonce |
| Hai regions gặp network partition | Ranges không chồng hoặc fail-safe |
| Trùng writer ID trong registry | Từ chối và cảnh báo |
| Counter gần overflow/giới hạn | Dừng Encrypt, chuẩn bị rotation |
| Counter state rollback do backup | Chặn cấp lại giá trị cũ |
| VM/container clone | Không dùng cùng writer identity/counter state sai |
| Retry sau Encrypt trước Persist | Không mã hóa lại bằng nonce cũ |
| Retry chỉ gửi lại immutable ciphertext record | Không sinh Encrypt mới |
| Timeout sau Persist | Reconcile operation ID, không cấp lại nonce |
| Cryptoperiod hết hạn | Không tiếp tục Encrypt |
| Writer offline reconnect với old revoked DEK | Không kích hoạt lại Encrypt với DEK cũ |
| Nonce/tag/AAD/ciphertext bị sửa | AEAD verification thất bại |
| Decrypt lại cùng một record nhiều lần | Hợp lệ, không tạo Encrypt mới |
| Replay ciphertext hợp lệ | Nếu protocol cần anti-replay, kiểm tra state riêng |
| Chunked stream nhiều chunks cùng DEK | Mỗi chunk có nonce riêng, chống reorder/truncate |
| 10.000 random nonces không trùng trong test | **Không** coi là chứng minh chất lượng RNG |
| KMS/nonce allocator outage | Không fallback sang timestamp/PRNG yếu |
| Delete KEK khi encrypted DEK còn phụ thuộc | Dependency guard từ chối |
| Audit Encrypt operation | Không chứa plaintext key, có key/version và metadata cần thiết |

### 21.1. SQL minh họa phát hiện reuse từ operation events

Nếu hệ thống có bảng append-only chứa **mỗi operation Encrypt thực sự**, có thể tìm cặp trùng như sau:

~~~sql
-- PostgreSQL-like. Chỉ lưu nonce và định danh key material,
-- không lưu plaintext DEK/private key.
SELECT
    dek_material_id,
    dek_material_version,
    nonce_bytes,
    COUNT(DISTINCT operation_id) AS independent_encrypt_ops
FROM encryption_operation_events
WHERE operation_status = 'ENCRYPTED'
GROUP BY
    dek_material_id,
    dek_material_version,
    nonce_bytes
HAVING COUNT(DISTINCT operation_id) > 1;
~~~

**Giới hạn bắt buộc của cách kiểm tra:**

- Phải có **đủ log của những lần Encrypt**, kể cả bản ghi đã bị xóa hoặc overwrite.
- Nếu event được giao lặp qua queue nhưng là cùng một operation, cần **deduplicate theo operation ID đáng tin**.
- Nếu cùng DEK bytes được copy/import dưới nhiều IDs, grouping theo ID riêng có thể bỏ sót reuse.
- **Random nonces không trùng trong mẫu log** không chứng minh nguồn CSPRNG đủ mạnh.
- Counter đã reserve nhưng không dùng Encrypt có thể được bỏ phí; **không được tự tái cấp** chỉ vì object chưa commit.
- Không thu thập key bytes rồi GROUP BY để “chứng minh”; đó là một hành động làm lộ secret.

### 21.2. Test lớp allocator quan trọng hơn test thống kê

Với deterministic nonces, cần kiểm tra:

1. **Concurrency:** nhiều workers reserve counter đồng thời.
2. **Crash after reservation:** worker chết sau commit nhưng trước Encrypt.
3. **Uncertain commit:** DB commit xong, client timeout trước ACK.
4. **Failover:** replica không cấp counter từ state stale.
5. **Backup restore:** snapshot cũ không cho rollback high-watermark của DEK.
6. **Regional partition:** không có overlapping leases/ids.
7. **Writer fencing:** worker cũ không thể tiếp tục tạo bản mã mới từ lease bị thu hồi theo policy.
8. **Counter exhaustion:** không wrap từ giá trị lớn về 0.

Một bài test tạo 10.000 nonces không trùng hữu ích về chức năng nhưng **chưa thể thay phân tích trạng thái bền vững và tính nhất quán khi lỗi**.

## 22. Playbook khi phát hiện nonce reuse dưới AES-GCM

Phát hiện hai phép Encrypt khác nhau với **cùng DEK và nonce** là một **security incident**, ngay cả khi chưa biết có attacker hay không.

~~~mermaid
flowchart TD
    A["Phát hiện trùng DEK + nonce"] --> B["Chặn Encrypt mới dưới material liên quan"]
    B --> C["Khoanh vùng writers, thời gian, objects, backups"]
    C --> D["Xác minh independent operations; phân biệt duplicate logs"]
    D --> E["Generate DEK mới + cutover writers"]
    E --> F["Đánh giá confidentiality/integrity và exposure"]
    F --> G["Re-encrypt dữ liệu có nguy cơ theo policy"]
    G --> H["Verify integrity, restore, authorization"]
    H --> I["Retire/revoke old DEK theo dependency policy"]
    I --> J["Sửa allocator/retry/failover + bổ sung tests"]
~~~

### 22.1. Containment và bằng chứng

- Dừng Encrypt mới dưới DEK material có nguy cơ; không chỉ đổi alias KEK.
- Không Destroy vật liệu cũ ngay khi backup/ciphertext hợp lệ còn phụ thuộc.
- Xác định **key material identity**, nonce, encrypted records, operation IDs, writers và timestamps.
- Kiểm tra counter ranges, leases, writer ID registry, PRNG state, deployments và snapshots.
- Bảo quản evidence đúng quyền, **không đưa raw DEK vào logs/ticket/chat**.

### 22.2. Khoanh vùng ảnh hưởng

Cần xác định khả năng có:

- **Known/chosen plaintext**, khiến quan hệ XOR giữa ciphertexts dễ khai thác.
- **Khả năng giả mạo dữ liệu/tag** theo cấu trúc bản tin và GHASH.
- Bản mã trong backups, archives, object versions và exports.
- Những cặp nonce khác có thể trùng bởi cùng root cause.
- Sự khác biệt giữa key material version và KEK reference.
- Data bị đọc hoặc sửa trái phép; thiếu audit coverage.

Không giới hạn điều tra ở cặp duplicate đầu tiên nếu nguyên nhân là **counter reset/overlapping writer ranges**.

### 22.3. Vì sao rewrap không đủ?

Rewrap DEK dưới KEK mới **không thay key AES dùng cho ciphertext** và không xóa tác động của nonce reuse đã xảy ra. Cần **Generate DEK mới** cho mã hóa tiếp theo và đánh giá **re-encrypt** bản ghi bị ảnh hưởng, đồng thời đánh giá khả năng dữ liệu đã bị lộ.

### 22.4. Không “chỉnh nonce” trên metadata cũ

Nonce là tham số của phép Encrypt đã tạo ciphertext/tag. Đổi trường nonce trên record mà không thực hiện lại một phép mã hóa hợp lệ **không sửa lỗ hổng**; thường khiến giải mã/tag verification thất bại.

Nếu cần migrate, hãy **Decrypt/Verify bản gốc hợp lệ** trong workflow được kiểm soát rồi Encrypt dưới DEK/nonce mới và lưu metadata tương ứng.

### 22.5. Xử lý nguyên nhân gốc

- Sửa allocator, writer IDs hoặc chính sách clone/restore.
- Ràng buộc nonce state với DEK material, không KEK alias.
- Bổ sung guard cryptoperiod/usage limits.
- Thiết kế retry idempotent và tránh re-encrypt bằng nonce cũ.
- Thử chaos với failover/region partitions/snapshots.
- Theo dõi producer cutover và old-key Encrypt attempts.

**Re-encrypt hôm nay không khiến thông tin attacker có thể đã suy ra ngày hôm qua trở lại bí mật.**

## 23. Case study A: hai mươi pods cùng reset bộ đếm về 0

Một hệ thống đơn hàng chạy 20 pods. Mỗi pod giải bọc **cùng DEK** từ KMS rồi dùng logic sau:

~~~java
// KHÔNG AN TOÀN khi nhiều pod cùng dùng DEK.
long counter = 0L;
// nonce = encodeAs96Bits(counter++);
~~~

Mỗi pod có một AtomicLong/thread-safe counter riêng trong RAM, nên test một pod không phát hiện trùng. Nhưng khi scale-out, cả 20 pods có thể Encrypt bản tin đầu tiên với nonce=0 dưới cùng DEK.

### 23.1. Vì sao đây là một lỗi nghiêm trọng?

Đây là nhiều phép Encrypt khác nhau nhưng cùng (DEK, nonce), làm suy yếu cả confidentiality và integrity của AES-GCM.

### 23.2. Những hướng khắc phục

- **DEK riêng cho từng pod/session/epoch** nếu mô hình có thể quản lý key lifecycle và không tái dùng material sau restart.
- **Writer ID duy nhất theo DEK + counter bền vững** với allocator/quorum và fencing.
- **Encryption service** có cơ chế cấp nonce tập trung nếu khả năng/hiệu năng cho phép.
- **Producer cutover + restore validation** trước khi cho hoạt động bình thường.

Nếu ciphertext cũ đã reuse nonce, phải theo **incident playbook** chứ không chỉ sửa counter của pods mới.

## 24. Case study B: Rotate KEK rồi reset nonce của DEK

Một nền tảng dùng chung **DEK-A** cho nhiều invoice versions, rồi bảo vệ DEK-A bằng KEK-v1:

~~~text
DEK-A -> AES-GCM Encrypt nhiều invoices
KEK-v1 -> Wrap(DEK-A)

Sau khi xoay KEK:
KEK-v2 -> Rewrap(DEK-A)
~~~

Vì thấy tên **KEK-v2**, nhóm vận hành khởi tạo lại nonce counter về 0 cho “key mới”. Đây là lỗi thiết kế: **DEK-A chưa hề đổi**.

### 24.1. Sai ở ranh giới nào?

- **KEK version** mô tả lớp bảo vệ DEK.
- **DEK material version** mô tả khóa dùng trực tiếp cho AES-GCM.
- **Nonce state** phải được gắn với **DEK material**, không với KEK alias/version.
- **Rewrap** chỉ thay encrypted DEK và wrapping metadata; không tạo nonce namespace mới.

### 24.2. Cách sửa

1. Key inventory theo **DEK material ID/version** độc lập với KEK.
2. Nonce allocator dùng DEK identity, không keyRef alias.
3. KEK rewrap không reset counter hoặc writer ID registry.
4. Nếu muốn namespace mới, Generate **DEK-B mới thực sự** và cập nhật producers/readers.
5. Record lưu đúng DEK/wrapped DEK và nonce/tag/AAD.
6. Kiểm tra old writers đã dừng Encrypt dưới DEK-A trước khi retire.
7. Nếu nonce đã bị reuse dưới DEK-A, kích hoạt incident playbook, không chỉ rewrap thêm lần nữa.

### 24.3. Tại sao KMS rotation không đủ?

Nếu ứng dụng tự dùng DEK-A trong JVM, KMS có thể chỉ quan sát các lần GenerateDataKey/Unwrap và **không biết bao nhiêu nonce đã dùng**. Bật KMS automatic KEK rotation không đồng nghĩa DEK-A được thay và không tự giải quyết các vấn đề GCM nonce.

## 25. Case study C: khôi phục snapshot khiến counter quay về giá trị cũ

Một dịch vụ mã hóa backup dùng cùng DEK cho nhiều revisions của một object. Hệ thống đã mã hóa hàng trăm revisions dưới DEK-v5:

~~~text
Object revision 10:
  DEK-v5
  nonce counter=42
  ciphertext/tag revision 10

Production counter đã cấp tới: 900
Snapshot cũ của counter lưu giá trị: 41

Sau restore: counter được tăng thành 42 lần nữa
~~~

Lúc đó lần Encrypt mới có thể dùng lại nonce=42 **dưới cùng DEK-v5**.

### 25.1. Vì sao nhìn các record còn tồn tại chưa đủ?

Có những counters đã từng được dùng trong phép Encrypt nhưng:

- Object bị overwrite hoặc xóa theo retention.
- Ghi dữ liệu ở region khác chưa replicate về.
- Encrypt đã hoàn thành nhưng DB persist timeout.
- Backup không chứa những operations mới nhất.
- Ciphertext đã được gửi tới một consumer trước khi job lỗi.

Vì vậy không được suy counter an toàn đơn giản bằng **MAX(nonce) trong database đã restore**, nếu database không có toàn bộ lịch sử.

### 25.2. Các lựa chọn phục hồi an toàn

1. Khôi phục high-watermark từ **durable, non-rollback allocator state** có evidence đáng tin.
2. Nếu không thể chứng minh dải giá trị nào đã dùng, **chặn Encrypt dưới DEK-v5** và Generate **DEK mới**.
3. Dùng nonce range leasing ngoài phạm vi snapshot thông thường với fencing/consensus phù hợp khi thiết kế yêu cầu.
4. Đánh giá những ciphertext được tạo trong khoảng có khả năng rollback, không chỉ phiên bản mới.
5. Kiểm thử DR thật, bao gồm idempotency, producer cutover, quyền KMS, encrypted DEK và backup metadata.

### 25.3. Cẩn trọng với cloned VM và random nonces

Ngay cả khi không dùng counter mà sử dụng CSPRNG, việc clone một máy với **trạng thái RNG giống hệt** và cùng DEK có thể vi phạm giả định independence. Cần runtime/OS/provider được thiết kế cho snapshot/restore, hoặc cấp key material mới sau khi khôi phục tùy threat model.

**Không coi một lần “khởi động lại app” là reset nonce namespace nếu DEK material không đổi.**

## 26. Câu hỏi tự kiểm tra

**Câu 1. Vì sao nonce uniqueness phải xét theo key?**

**Trả lời:** Vì trong các mode như AES-GCM, lỗi nguy hiểm xảy ra khi **cùng (key, nonce)** dùng cho nhiều phép Encrypt khác nhau. Trùng nonce dưới hai keys độc lập không phải reuse cùng key.

**Câu 2. Nonce có cần bí mật không?**

**Trả lời:** Thường không. Nonce có thể lưu cạnh ciphertext; nhưng phải đáp ứng quy tắc của mode, đặc biệt là uniqueness theo key đối với GCM.

**Câu 3. AES-GCM reuse nonce chỉ gây lộ một ít thông tin hay có thể ảnh hưởng tính toàn vẹn?**

**Trả lời:** Có thể ảnh hưởng nghiêm trọng cả confidentiality và integrity. Tái dùng keystream tiết lộ quan hệ plaintext, và GHASH có thể bị khai thác để giả mạo trong những điều kiện cụ thể.

**Câu 4. Vì sao KEK rewrap không reset nonce của DEK?**

**Trả lời:** Vì nó chỉ đổi **lớp bọc DEK**, không đổi **DEK bytes** đang mã hóa payload.

**Câu 5. Đổi key alias có tạo nonce namespace mới không?**

**Trả lời:** Không nếu key material vẫn là một. Alias/key ID chỉ là metadata.

**Câu 6. Random 96-bit nonce có bảo đảm không trùng tuyệt đối không?**

**Trả lời:** Không. Có birthday collision risk, nên cần nguồn RNG tốt, usage budget và giới hạn theo chuẩn.

**Câu 7. Vì sao timestamp millisecond là nonce nguy hiểm?**

**Trả lời:** Nhiều operations cùng millisecond, đồng hồ lùi, multiwriter hoặc restore có thể gây trùng. Timestamp một mình không bảo đảm uniqueness.

**Câu 8. Dùng AtomicLong làm counter nonce đã đủ chưa?**

**Trả lời:** Chưa. AtomicLong chỉ xử lý concurrency trong một JVM, không giải quyết restart, snapshot, multiwriter, region failover hoặc counter state bị rollback.

**Câu 9. Khi nào writer ID + counter là một construction đúng?**

**Trả lời:** Khi writer IDs duy nhất theo DEK, counter được reserve bền vững và nguyên tử, không cấp lại/overflow, có fencing và lifecycle policy.

**Câu 10. Một Encrypt retry có được dùng nonce cũ không?**

**Trả lời:** Không cho một phép Encrypt mới dưới cùng DEK. Nếu chỉ gửi lại **ciphertext/tag/AAD bất biến đã tạo** theo protocol idempotent thì không thực hiện thêm Encrypt. Nếu mã hóa lại, dùng nonce mới.

**Câu 11. Hai lần Decrypt cùng record dùng lại nonce có bị cấm không?**

**Trả lời:** Không. Decrypt phải dùng đúng nonce đã lưu; đây không phải hai phép Encrypt mới.

**Câu 12. Nonce uniqueness có chặn replay không?**

**Trả lời:** Không. Một bản mã/tag hợp lệ cũ có thể được replay; cần anti-replay/sequence/idempotency ở protocol hoặc business layer.

**Câu 13. Nếu mỗi object có DEK độc lập thì có cần nonce strategy không?**

**Trả lời:** Vẫn cần. Mỗi lần Encrypt dưới mỗi DEK phải tuân quy tắc; nếu object cập nhật và DEK bị reuse, cần nonce mới hoặc generate DEK mới cho revision.

**Câu 14. AES-GCM-SIV có cho phép bỏ hẳn quản lý nonce không?**

**Trả lời:** Không. Nó chịu lỗi reuse tốt hơn AES-GCM truyền thống nhưng vẫn có leakage/security bounds, usage limits và yêu cầu vận hành.

**Câu 15. Thay DEK/re-encrypt có làm dữ liệu đã bị attacker đọc trở lại bí mật không?**

**Trả lời:** Không. Migration bảo vệ trạng thái tiếp theo, không thu hồi thông tin đã bị lộ.

**Câu 16. Vì sao SQL không tìm ra cặp trùng chưa chứng minh tính an toàn?**

**Trả lời:** Có thể thiếu log của Encrypt operations, object đã xóa, hoạt động ở region khác, hoặc cùng material được import dưới IDs khác nhau.

**Câu 17. Khi counter allocator down, có nên chuyển tạm sang timestamp/random nonce dưới key cũ không?**

**Trả lời:** Không tự ý. Fail-safe hoặc dùng key/strategy khác đã được chứng minh không giao nhau, theo policy.

**Câu 18. GCM authentication tag lỗi có chắc vì nonce reuse không?**

**Trả lời:** Không. Sai tag có thể do sửa ciphertext/AAD/key/nonce hoặc bug. Nonce reuse vẫn có thể tồn tại dù từng record tự Decrypt/Verify thành công.

## 27. Checklist triển khai và ghi nhớ

Trước khi cho ứng dụng **Encrypt dưới một key**, xác nhận:

- **Key material:** biết DEK identity, version, origin và scope; không chỉ biết alias KEK?
- **Mode:** AES-GCM, ChaCha20-Poly1305, CTR, CBC hay misuse-resistant AEAD có IV/nonce rules và usage bounds đúng?
- **Nonce format:** độ dài đúng suite; ví dụ 96 bit cho AES-GCM thông dụng?
- **Uniqueness scope:** xét mọi Encrypt operations dưới **cùng key material**, kể cả nhiều pods/regions, backups và imported duplicates?
- **Random nonces:** SecureRandom/CSPRNG đúng, usage budget và giả định independence được kiểm tra?
- **Deterministic nonces:** writer IDs duy nhất, counter được reserve durable/atomic, không rollback/overflow và có fencing?
- **Concurrency:** đã test multiwriter, network partitions, stale replicas, failover và clone VM?
- **Retry:** có operation IDs/idempotency, không re-Encrypt bằng nonce đã sử dụng?
- **DEK scoping:** có thể dùng DEK riêng theo object/tenant/stream để giảm blast radius?
- **KMS/envelope:** lưu nonce, tag, encrypted DEK, keyRef/version; KEK rewrap không reset nonce state?
- **DEK rotation:** Generate material mới thật, chuyển producer và bảo đảm reader còn đọc lịch sử theo policy?
- **Usage budget:** Cryptoperiod, max Encrypt operations, bytes/blocks và counter ranges được giám sát?
- **AAD/tag:** business context được ràng buộc, tag được kiểm tra trước khi dùng plaintext?
- **Decrypt:** dùng nonce đã lưu, không tạo phép Encrypt mới khi chỉ đọc record?
- **Anti-replay:** protocol có kiểm soát sequence/operation states riêng nếu cần?
- **Chunking:** nonce riêng từng chunk dưới DEK, thứ tự/số lượng/manifest được xác thực?
- **Monitoring:** có key inventory, nonce claims/leases, high-watermark và cảnh báo conflict/rollback?
- **Negative testing:** kiểm tra counter reset, rewrap KEK, race, backup restore, retry và failover?
- **Incident response:** có thể chặn Encrypt dưới DEK lỗi, tìm data/writers bị ảnh hưởng, thay DEK và re-encrypt theo rủi ro?
- **Revocation/destruction:** không Destroy KEK/DEK khi ciphertext/backups hợp lệ còn phụ thuộc; provider evidence đầy đủ?

**Ghi nhớ:** **Nonce uniqueness theo key** là yêu cầu cốt lõi của các chế độ AEAD như AES-GCM: **mỗi phép Encrypt riêng dưới cùng DEK phải sử dụng nonce chưa từng dùng với DEK đó**. Nonce ngẫu nhiên cần nguồn CSPRNG, hạn mức và phân tích va chạm; nonce dạng counter cần **allocator bền vững, phân vùng writer và chống rollback**. **KEK rewrap hoặc đổi alias không tạo DEK mới, nên không được reset nonce state**. Kết hợp điều này với **KMS/HSM, envelope encryption, IAM, key inventory, cryptoperiod, rotation, audit, backup/DR và ứng phó sự cố** để bảo vệ tính bí mật và toàn vẹn trong suốt quá trình sử dụng khóa.
