# Independent keys — Sinh các khóa mật mã độc lập

## 1. Independent keys là gì?

**Independent keys** (*các khóa độc lập*) là những khóa được **tạo hoặc dẫn xuất theo một thiết kế bảo đảm chúng không bị phụ thuộc nguy hiểm vào nhau**, để việc biết, sử dụng hoặc làm lộ một khóa **không tự động cho phép suy ra các khóa khác** trong những giả định bảo mật của cơ chế đang dùng.

Trong chương **Key generation (Sinh khóa)**, thuật ngữ này cần được hiểu chính xác theo **hai mô hình khác nhau**:

1. **Sinh các khóa riêng bằng CSPRNG/DRBG đáng tin cậy**: ví dụ tạo một DEK AES-256 và một HMAC key bằng các lần sinh khóa riêng biệt. Với bộ sinh ngẫu nhiên mật mã an toàn, các đầu ra phải không thể phân biệt với những giá trị ngẫu nhiên phù hợp đối với đối thủ bị giới hạn tính toán, theo giả định của bộ sinh.
2. **Dẫn xuất những subkey tách biệt bằng KDF chuẩn từ một master secret**: ví dụ dùng HKDF với các giá trị `info` khác nhau để tạo khóa mã hóa và khóa xác thực. Các subkey này có thể được xem là **tách biệt về mặt mật mã dưới giả định KDF an toàn**, nhưng **không độc lập tuyệt đối về mặt thông tin** vì cùng phụ thuộc master secret.

Một **key ID khác**, tên alias khác hoặc hai đối tượng `SecretKey` khác nhau trong Java **không phải bằng chứng về tính độc lập của vật liệu khóa**. Nếu hai key record trỏ đến cùng raw key, nếu private key bị sao chép, hoặc nếu các key được tính từ seed dễ đoán, tách tên không làm tăng bảo mật.

Ví dụ một dịch vụ Billing cần:

- **DEK** mã hóa hóa đơn bằng AES-GCM.
- **KEK** bọc DEK thông qua envelope encryption.
- **HMAC key** xác thực webhook.
- **Private signing key** ký hóa đơn điện tử.
- **Private ECDH key** cho cơ chế thỏa thuận khóa với một peer theo giao thức.

Năm nhiệm vụ này có **mục đích, thuật toán, ranh giới tin cậy, tuổi thọ và khả năng bị lộ khác nhau**. Tạo các khóa độc lập hoặc dẫn xuất khóa với **domain separation** phù hợp giúp giảm tình trạng một lỗi nhỏ lan thành sự cố toàn hệ thống.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, Independent keys liên kết trực tiếp với việc **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy** khóa, cùng các cơ chế mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Thông điệp chính:** “Hai khóa khác nhau” là điều kiện quá yếu. Cần chứng minh **nguồn tạo/đường dẫn xuất an toàn**, **phân tách mục đích**, **không dùng lại cùng vật liệu một cách vô ý**, **quyền truy cập độc lập ở mức phù hợp**, và **phạm vi compromise được hiểu rõ**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **key uniqueness**, **unpredictability**, **cryptographic independence** và **domain separation**.
2. Chọn giữa **sinh khóa riêng bằng CSPRNG** và **dẫn xuất subkey bằng KDF** trong các tình huống thích hợp.
3. Giải thích vì sao khóa con HKDF có thể tách mục đích tốt nhưng vẫn phụ thuộc master secret.
4. Nhận diện nguy cơ **reused seed, VM/container snapshot, hard-coded key và cross-protocol key reuse**.
5. Tạo khóa AES/HMAC/EC riêng bằng Java JCA và minh họa HKDF-SHA-256 an toàn ở mức giáo dục.
6. Thiết kế kiểm soát KMS/HSM, IAM, key inventory, rotation, audit và ứng cứu khi một khóa bị lộ.

## 2. Vì sao cùng một khóa không nên làm mọi việc?

Giả sử nhóm phát triển dùng một chuỗi 32 byte `shared-secret` cho cả **AES-GCM encrypt**, **HMAC-SHA-256** và **bảo vệ token**. Dù mỗi thuật toán riêng lẻ có thể an toàn trong những điều kiện nhất định, **việc tái sử dụng cùng secret cho nhiều giao thức** gây ra những vấn đề:

- **Tăng blast radius:** một service làm lộ secret có thể ảnh hưởng tất cả dữ liệu và thông điệp dùng secret đó.
- **Tăng nguy cơ tương tác giao thức:** việc một API cho phép attacker tương tác với cùng key qua nhiều chức năng có thể phá các giả định chứng minh bảo mật riêng.
- **Khó đặt key usage:** policy `Encrypt`/`GenerateMac` có thể bị trộn lẫn; kiểm soát least privilege trở nên phức tạp.
- **Khó rotation:** đổi key vì sự cố webhook có thể làm mất khả năng giải mã dữ liệu.
- **Khó kiểm toán:** log không giải thích được mỗi lượt dùng secret phục vụ mục đích nào.
- **Khó thu hồi theo phạm vi:** không thể thay chỉ một chức năng mà vẫn giữ các chức năng khác như cũ.

Một thiết kế tốt thường tạo **key material riêng cho những mục đích có rủi ro, giao thức hoặc cryptoperiod khác nhau**. Đây không phải lời khẳng định mọi hệ thống đều cần sinh một khóa mới cho *từng hàm gọi*; quyết định về granularity vẫn phụ thuộc thuật toán, data scope và mô hình đe dọa.

### Ví dụ về thay đổi phạm vi ảnh hưởng

| Thiết kế | Khi HMAC key webhook bị lộ | Khả năng cô lập |
| --- | --- | --- |
| Một secret cho HMAC và AES dữ liệu | Phải đánh giá cả giả mạo webhook **và** dữ liệu đã mã hóa | Kém |
| Secret webhook riêng, DEK/KEK riêng | Điều tra webhook trước; DEK không tự động bị lộ vì biết HMAC secret | Tốt hơn, nếu các khóa thật sự được tách |
| Mỗi đối tác có HMAC key riêng | Có thể tập trung vào một đối tác và các sự kiện liên quan | Tốt hơn theo phạm vi đối tác |
| Các subkey cùng một master bị lộ | Phải xem xét **tất cả** subkey và dữ liệu phụ thuộc | Master vẫn là điểm rủi ro chung |

**Tách khóa** phải được phối hợp với **tách quyền và boundary**. Nếu mọi secret vẫn cùng nằm trong một file cấu hình ai cũng đọc được, một sự cố lộ file có thể làm lộ tất cả dù chúng được tạo độc lập.

## 3. Bốn khái niệm cần phân biệt

| Khái niệm | Câu hỏi | Ví dụ | Điều không được suy ra |
| --- | --- | --- | --- |
| **Uniqueness** (*khác giá trị*) | Hai khóa có giá trị khác nhau không? | DEK-v1 và DEK-v2 không trùng byte | Hai giá trị khác nhau chưa chắc không đoán được |
| **Unpredictability** (*không thể dự đoán*) | Đối thủ có thể dự đoán key từ thông tin biết trước không? | Key từ CSPRNG có entropy phù hợp | Không tự chứng minh dùng đúng mục đích |
| **Independence** (*độc lập*) | Biết key A có giúp suy ra key B không, dưới giả định mô hình? | Hai khóa được sinh an toàn riêng | Không có nghĩa hai khóa ở hai HSM độc lập về vận hành |
| **Domain separation** (*phân tách miền*) | Các mục đích/ngữ cảnh có nhận output mật mã khác nhau không? | HKDF `info="aes-gcm"` và `info="hmac"` | Không làm master key trở nên an toàn nếu master bị lộ |

### 3.1. Độc lập lý tưởng và độc lập tính toán

Với hai khóa lý tưởng **K₁, K₂** được rút **độc lập và đều** từ không gian khóa n bit:

~~~text
P(K2 = x | K1 = y) = P(K2 = x) = 2^(-n)

Việc biết K1 không làm tăng xác suất đoán K2.
~~~

Hai khóa lý tưởng **vẫn có xác suất trùng**: nếu lấy hai giá trị n-bit đều độc lập, xác suất chúng bằng nhau là **2⁻ⁿ**. Độc lập không đồng nghĩa bảo đảm “không bao giờ trùng”.

Một **DRBG/CSPRNG thực tế** thường xuất nhiều giá trị từ cùng trạng thái nội bộ. Các đầu ra **không độc lập theo nghĩa thông tin tuyệt đối**, nhưng một DRBG được thiết kế và sử dụng đúng có thể cho đầu ra **không thể phân biệt với ngẫu nhiên độc lập đối với đối thủ khả thi**, trong giả định bảo mật quy định.

Vì thế, khi nói “sinh hai key độc lập” trong hệ thống thực, nên hiểu là **đáp ứng mức độc lập mật mã cần thiết**, không hứa hẹn tính độc lập toán học tuyệt đối của mọi bit bộ nhớ.

### 3.2. Khác khóa không đủ để bảo mật

~~~text
keyA = SHA-256("service-a" || "seed-co-dinh")
keyB = SHA-256("service-b" || "seed-co-dinh")
~~~

Hai kết quả có thể khác nhau nhưng nếu seed được biết hoặc đoán được, đối thủ **tính được cả hai**. Chạy hash không tạo entropy mới; đầu ra 256 bit không đồng nghĩa có 256 bit entropy.

**Không dùng timestamp, PID, địa chỉ IP, tên service hay UUID dự đoán được làm bí mật chính để sinh khóa.**

## 4. Sinh trực tiếp các khóa riêng bằng CSPRNG

Cách trực quan nhất là tạo mỗi khóa bằng **một lần gọi API sinh khóa mật mã** từ nguồn ngẫu nhiên được chấp nhận.

~~~mermaid
flowchart TD
    E[Nguồn entropy được đánh giá] --> DRBG[CSPRNG/DRBG an toàn]
    DRBG --> GenA[Sinh DEK AES-GCM]
    DRBG --> GenB[Sinh KEK theo chính sách]
    DRBG --> GenC[Sinh HMAC key]
    DRBG --> GenD[Sinh EC signing key pair]
    DRBG --> GenE[Sinh EC agreement key pair]
    GenA --> ScopeA[Purpose: dữ liệu lưu trữ]
    GenB --> ScopeB[Purpose: wrap/unwrap DEK]
    GenC --> ScopeC[Purpose: webhook authentication]
    GenD --> ScopeD[Purpose: chữ ký số]
    GenE --> ScopeE[Purpose: key agreement]
~~~

**Cùng sử dụng một CSPRNG đáng tin** không có nghĩa các khóa sinh ra là “cùng một khóa” hoặc tự động không an toàn. Điều cốt yếu là DRBG có trạng thái bí mật đủ mạnh, được seed/reseed đúng, không lặp trạng thái và được sử dụng đúng API/provider.

### Các bước sinh khóa riêng

1. Xác định **purpose, key type, algorithm, kích thước, cryptoperiod, key usage** trước khi sinh.
2. Chọn provider JCA/JCE, HSM/KMS hoặc bộ sinh khóa **được tổ chức chấp thuận**.
3. Tạo **mỗi key material bằng yêu cầu sinh mới**, không sao chép lại từ key trước.
4. Tạo key ID/version rõ ràng và gắn với inventory; không dùng tên key để thay kiểm tra vật liệu.
5. Thiết lập **quyền sử dụng tối thiểu**, hạn chế export và đường truy cập.
6. Tách các khóa có mục đích khác nhau qua **IAM, service boundary, tenant và environment** theo rủi ro.
7. Ghi nhận sự kiện tạo, thuật toán, key origin, owner và policy — **không ghi raw key**.

### Sinh một cặp bất đối xứng không phải hai khóa bí mật độc lập

Trong cặp khóa bất đối xứng:

~~~text
privateKey --hàm công khai xác định--> publicKey
~~~

Public key **được tính từ private key**. Hai phần này **không độc lập**; chúng thuộc **một cặp liên quan toán học**. “Independent signing and agreement keys” nghĩa là nên sinh **hai cặp khóa riêng** (và theo policy key usage tương ứng), chứ không yêu cầu public key độc lập với private key trong mỗi cặp.

## 5. Dẫn xuất subkey từ một master secret có phải independent keys?

Có thể, nhưng cần nói rõ **mức bảo đảm**.

Giả sử hệ thống có **master secret M** đủ mạnh. Thay vì lưu nhiều raw secret riêng biệt, hệ thống dùng một **KDF chuẩn** để sinh:

~~~text
K_enc = KDF(M, context = "app/v1 | encryption | tenant-A")
K_mac = KDF(M, context = "app/v1 | webhook-mac | tenant-A")
K_exp = KDF(M, context = "app/v1 | exporter | tenant-A")
~~~

Với KDF có tính chất PRF/PRG phù hợp, **các đầu ra ở các miền khác nhau có thể tách biệt về mặt tính toán**. Khi biết `K_enc`, đối thủ không mặc nhiên suy ra `K_mac` nếu KDF và master secret an toàn.

Nhưng **K_enc, K_mac, K_exp đều là hàm của M**, nên không độc lập theo nghĩa thông tin tuyệt đối. Nếu M bị lộ, **mọi subkey có thể bị tính lại** nếu ngữ cảnh dẫn xuất đã biết.

| Câu hỏi | Sinh khóa độc lập trực tiếp | Dẫn xuất từ master bằng KDF |
| --- | --- | --- |
| Có master secret chung không? | Không bắt buộc | **Có** |
| Lộ một key có tự suy ra key khác? | Không trong mô hình sinh an toàn | Không trong giả định KDF/PRF an toàn |
| Lộ toàn bộ trạng thái DRBG/master thì sao? | Có thể ảnh hưởng những key liên quan tùy thời điểm/state compromise | **Master lộ ảnh hưởng mọi subkey dẫn xuất** |
| Tái tạo key từ metadata có được không? | Không nếu không lưu/sao lưu key | Có nếu còn master và context |
| Rủi ro quản trị tập trung | Phân tán nhiều tài sản/key locations | Master trở thành **tài sản trọng yếu** |
| Hợp với trường hợp nào? | Cách ly thực sự giữa purpose/service, HSM key riêng | Key schedule giao thức, subkey tạm, domain separation |
| Điều kiện then chốt | CSPRNG/DRBG an toàn, key material mới | Master mạnh, KDF chuẩn, labels/context rõ |

**Không coi HKDF là phương tiện biến một password yếu thành master key đủ mạnh.** Password-based key material phải được xử lý bằng KDF làm chậm đoán mật khẩu phù hợp như Argon2id/scrypt/PBKDF2 theo chính sách, sau đó mới dùng trong thiết kế dẫn xuất/bọc khóa thích hợp.

## 6. Domain separation — ngăn các mục đích đụng nhau

**Domain separation** có nghĩa là mỗi **mục đích hoặc ngữ cảnh sử dụng** có một định danh không mơ hồ trong đầu vào dẫn xuất hoặc thao tác mật mã.

Ví dụ, khi dùng HKDF:

~~~text
infoA = encode("billing", "v1", "prod", "tenant-A", "AES-256-GCM", "record")
infoB = encode("billing", "v1", "prod", "tenant-A", "HMAC-SHA-256", "webhook")

K_record  = HKDF-Expand(PRK, infoA, 32)
K_webhook = HKDF-Expand(PRK, infoB, 32)
~~~

Hai giá trị `info` khác nhau giúp hai tác vụ nhận **subkey khác nhau theo thiết kế**, miễn là KDF/PRK được dùng đúng.

### Điều nên đưa vào context

- **Application/protocol ID và version**, ví dụ `billing-key-schedule/v2`.
- **Purpose:** `encrypt-record`, `webhook-mac`, `transport-client-write`…
- **Thuật toán/suite và độ dài yêu cầu**, ví dụ AES-256-GCM, HMAC-SHA-256.
- **Environment, tenant, key version** nếu đây là các miền cần cách ly.
- **Peer identities/roles, transcript hash, session ID** nếu giao thức key agreement yêu cầu.
- **Hướng truyền** như client → server và server → client để không tái sử dụng cùng traffic key cho hai chiều.

### Encoding phải không mơ hồ

Cách nối chuỗi ngây thơ có thể cho kết quả trùng giữa những bộ trường khác nhau:

~~~text
["ab", "c"]  ->  "abc"
["a", "bc"]  ->  "abc"
~~~

Trong production, dùng **canonical encoding**, length-prefix hoặc định dạng cấu trúc có quy tắc xác định; tránh ghép chuỗi tùy ý không có quy tắc. Những nhãn đã được quy định cố định theo giao thức cũng phải **được kiểm thử không trùng miền**.

### Salt không thay thế Purpose

Salt trong HKDF giúp **Extract** hoạt động theo mô hình phù hợp; `info` được dùng phân tách ngữ cảnh trong **Expand**. Salt không phải bí mật và không nên bị lạm dụng thay cho tất cả trường ngữ cảnh.

**Dùng một salt khác cho mỗi lần dẫn xuất** có thể làm khóa thay đổi, nhưng không tự bảo đảm rằng hệ thống phân biệt đúng **mục đích, vai trò và thuật toán**. Phải tuân theo key schedule của giao thức.

## 7. HKDF-SHA-256: mô hình tách khóa có cấu trúc

**HKDF** (*HMAC-based Key Derivation Function*, RFC 5869) gồm hai giai đoạn:

~~~text
PRK = HKDF-Extract(salt, IKM)

OKM_1 = HKDF-Expand(PRK, info="billing/v1/record-encryption", L=32)
OKM_2 = HKDF-Expand(PRK, info="billing/v1/webhook-authentication", L=32)
~~~

- **IKM (Input Keying Material):** vật liệu bí mật có entropy phù hợp, ví dụ master secret ngẫu nhiên hoặc kết quả agreement theo giao thức đã được phân tích.
- **PRK (Pseudorandom Key):** kết quả trung gian của Extract.
- **OKM (Output Keying Material):** byte khóa được dẫn xuất cho một mục đích cụ thể.
- **Salt:** giá trị bổ trợ cho Extract, thường không bí mật; việc chọn, lưu và truyền theo đặc tả hệ thống.
- **Info:** chuỗi ngữ cảnh phân tách mục đích; hai bên phải thống nhất và mã hóa không mơ hồ.
- **L:** độ dài output, có giới hạn theo hàm hash của HKDF.

### Những bảo đảm không được nhầm

1. **Hai output khác label** không được xem là hoàn toàn độc lập toán học với master; chúng **phụ thuộc M**.
2. **Lộ một subkey** không mặc nhiên làm lộ subkey khác **nếu** master/KDF và cách tách miền còn an toàn.
3. **Lộ master** phá vỡ tính cách ly của mọi subkey dẫn xuất có thể tái tạo.
4. **Tái sử dụng cùng PRK + info + L** tạo **cùng output** một cách quyết định; không được nhầm với yêu cầu sinh một khóa hoàn toàn mới.
5. **Một input IKM yếu** không trở nên khó đoán chỉ bằng cách hash/HKDF.
6. **HKDF không cấp quyền IAM**; việc ứng dụng có thể tự yêu cầu dẫn xuất subkey cho miền khác phải được quản trị riêng.

### Ví dụ key schedule đơn giản

~~~mermaid
flowchart TD
    M[Master secret đủ entropy] --> X[HKDF-Extract với salt]
    S[Salt/thiết lập theo protocol] --> X
    X --> PRK[PRK: chỉ lưu trong vùng an toàn cần thiết]
    PRK --> A[Expand info: record AES-GCM]
    PRK --> B[Expand info: webhook HMAC]
    PRK --> C[Expand info: exporter]
    A --> KA[K_record]
    B --> KB[K_webhook]
    C --> KC[K_export]
    Z[Compromise master] -.-> M
    Z --> R[Phải đánh giá mọi subkey và dữ liệu phụ thuộc]
~~~

**Đây là mô hình giáo dục.** Không tự thiết kế key schedule cho TLS, Noise hay giao thức production nếu có key schedule chuẩn đã được phân tích; hãy tuân theo chính xác giao thức.

## 8. Independent keys không chỉ là khác thuật toán

Một số lỗi thường gặp:

### 8.1. Khóa AES và HMAC dùng cùng byte

`AES-256-GCM` và `HMAC-SHA-256` là hai thuật toán khác nhau, nhưng việc dùng **cùng một mảng 32 byte** để khởi tạo cả `SecretKeySpec(raw, "AES")` và `SecretKeySpec(raw, "HmacSHA256")` vẫn là **key reuse**.

Cần **hai raw key độc lập** hoặc hai subkey được **dẫn xuất theo miền riêng** bằng KDF chuẩn và chính sách phù hợp.

### 8.2. Hai alias cùng trỏ một key material

~~~text
alias: billing-record-dek  ──┐
                             ├──> KMS key resource / material X
alias: billing-recovery-kek ─┘
~~~

Dù có hai alias, vật liệu khóa **không độc lập**. Trong một số hệ thống, alias chỉ là **đường định tuyến tới resource**. Phải đối soát **provider key ID, material version và mục đích**.

### 8.3. Cặp khóa EC dùng cho cả ECDSA và ECDH

Private EC key có thể được biểu diễn dưới cùng loại dữ liệu toán học, nhưng **ECDSA ký số** và **ECDH thỏa thuận khóa** có mô hình đe dọa, key usage và giao thức khác nhau. Với thiết kế mới, **tách signing key pair và agreement key pair** là lựa chọn nên ưu tiên; không tự tái sử dụng một cặp chỉ vì API nhận cùng `ECPrivateKey`.

### 8.4. Chữ ký Ed25519 và thỏa thuận X25519

**Ed25519** dùng cho chữ ký số; **X25519** dùng cho key agreement. Không sử dụng cùng secret một cách tùy ý, không tự chuyển đổi khóa giữa hai thuật toán và không cho rằng cùng họ đường cong có nghĩa chúng có cùng purpose hoặc cùng API.

## 9. Nguồn entropy, DRBG và lỗi sinh khóa tương quan

Dù bạn gọi `generateKey()` nhiều lần, **nguồn sinh yếu hoặc trạng thái bộ sinh bị lặp** vẫn có thể khiến nhiều khóa tương quan hoặc trùng nhau.

### Các nguy cơ

| Nguy cơ | Vì sao phá tính độc lập/an toàn | Kiểm soát |
| --- | --- | --- |
| Seed cố định trong source code | Các lần khởi động tạo cùng chuỗi khóa | Không hard-code seed; dùng provider CSPRNG |
| Seed bằng timestamp/PID | Đối thủ thu hẹp không gian tìm kiếm | Entropy source/DRBG chuẩn |
| VM/container snapshot sau khi DRBG đã khởi tạo | Clone có thể tái sử dụng trạng thái và phát cùng đầu ra | Thiết kế reseed/clone handling theo runtime/provider; đánh giá môi trường |
| Device chưa có đủ entropy tại boot | Key sinh sớm có thể yếu hoặc dự đoán được | Kiểm tra khả năng entropy, DRBG readiness |
| Tự dùng `java.util.Random` để tạo AES key | Không phải bộ sinh mật mã | `SecureRandom`/KMS/HSM đúng thuật toán |
| Tự rút private key bằng `% n` thiếu phân tích | Có thể gây bias hoặc giá trị không hợp lệ | `KeyPairGenerator`/thư viện EC chuẩn |
| Nhập cùng raw key vào nhiều tenant | Toàn bộ tenant dùng cùng secret | Sinh key theo scope, kiểm kê provenance |
| Ghi seed vào log hoặc backup không kiểm soát | Khôi phục được nhiều key tương lai/quá khứ tùy DRBG | Không log seed; bảo vệ trạng thái/backup |

### 9.1. Không tự seed bằng `setSeed(System.currentTimeMillis())`

Đối với Java, `SecureRandom` có cơ chế seed của provider. Tự cung cấp một seed **ít entropy** không phải cách “làm bộ sinh ngẫu nhiên hơn”. Việc `setSeed` trộn hay thay thế trạng thái và các bảo đảm liên quan là **đặc thù provider/thuật toán**; không dựa vào các giả định tự đặt để thiết kế nguồn entropy.

Trong production, dùng **provider đã được đánh giá**, môi trường có entropy phù hợp và kiểm tra cấu hình ở thời điểm khởi tạo. Với KMS/HSM, cần xác nhận cơ chế sinh khóa và nguồn gốc vật liệu qua **tài liệu và bằng chứng của provider**.

### 9.2. Reseed, fork và snapshot

Một CSPRNG an toàn thường có bảo đảm theo mô hình DRBG, nhưng **snapshot/fork/clone** có thể sao chép trạng thái mật mã ở mức runtime. Không suy luận rằng chỉ dùng một class `SecureRandom` thì mọi container clone chắc chắn sẽ sinh key khác nhau.

Các kiểm soát có thể gồm tạo key **trực tiếp trong KMS/HSM**, đánh giá reseed sau restore/snapshot, dùng runtime/provider hỗ trợ clone/fork an toàn và kiểm thử môi trường. Không tự bổ sung timestamp làm “chất liệu ngẫu nhiên” để che lỗi state duplication.

## 10. Java 11+: sinh AES, HMAC và EC key pair riêng

Đoạn mã minh họa dùng **JCA/JCE** để tạo **DEK AES-256**, **KEK AES-256**, **HMAC-SHA-256 key**, **ECDSA signing key pair** và **ECDH agreement key pair** qua các lần gọi **riêng**.

Các khóa là **minh họa trong cùng JVM**, không được đưa vào production chỉ bằng cách copy code. Trường hợp cần bảo vệ key bằng HSM/KMS, phải dùng API/provider được phê duyệt và thiết kế quyền cùng lifecycle phù hợp.

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class IndependentKeyGenerationDemo {
    private static final SecureRandom RNG = new SecureRandom();

    static SecretKey newAes256Key()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static SecretKey newHmacSha256Key()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("HmacSHA256");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static KeyPair newP256KeyPair()
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"), RNG);
        return generator.generateKeyPair();
    }

    public static void main(String[] args) throws Exception {
        // Hai lần sinh riêng: DEK và KEK KHÔNG dùng cùng object/key bytes.
        SecretKey dekForRecords = newAes256Key();
        SecretKey kekForWrapping = newAes256Key();

        // HMAC key có mục đích/thuật toán khác AES.
        SecretKey webhookHmacKey = newHmacSha256Key();

        // Sinh hai cặp EC riêng, dù cùng dùng curve P-256.
        KeyPair invoiceSigningPair = newP256KeyPair();
        KeyPair peerAgreementPair = newP256KeyPair();

        // Chỉ in metadata, KHÔNG in getEncoded() hoặc private key.
        System.out.println("DEK algorithm: " + dekForRecords.getAlgorithm());
        System.out.println("KEK algorithm: " + kekForWrapping.getAlgorithm());
        System.out.println("HMAC algorithm: " + webhookHmacKey.getAlgorithm());
        System.out.println("Signing key type: "
                + invoiceSigningPair.getPrivate().getAlgorithm());
        System.out.println("Agreement key type: "
                + peerAgreementPair.getPrivate().getAlgorithm());

        // Production còn cần:
        // - KMS/HSM hoặc keystore/secret protection theo threat model.
        // - Purpose, key usage, IAM, owner, cryptoperiod và audit.
        // - Phân phối public key có xác thực cho signing/ECDH.
        // - Không lưu plaintext key bytes vào cấu hình hoặc log.
    }
}
~~~

### Kết quả minh họa điển hình

~~~text
DEK algorithm: AES
KEK algorithm: AES
HMAC algorithm: HmacSHA256
Signing key type: EC
Agreement key type: EC
~~~

**Kết quả trên là tên thuật toán, không phải bằng chứng độc lập được đo bằng một vài dòng log.** Tính an toàn đến từ **cơ chế sinh khóa, cấu hình provider, phân tách use case và kiểm soát vật liệu**.

### Những điểm cần hiểu

1. **`KeyGenerator("AES")`:** tạo vật liệu đối xứng theo API chuẩn. Gọi hai lần sinh hai khóa mới về mặt thiết kế; không copy `dekForRecords` làm `kekForWrapping`.
2. **`KeyGenerator("HmacSHA256")`:** sinh secret dành riêng cho HMAC, không dùng AES key làm MAC key.
3. **`KeyPairGenerator("EC")`:** mỗi lần sinh một **cặp private/public key**. Signing pair và agreement pair là hai tài sản khác nhau, cần key usage và trust khác nhau.
4. **`SecureRandom`:** nguồn ngẫu nhiên mật mã ở JCA; bảo đảm chi tiết phụ thuộc provider và môi trường. Không dùng `java.util.Random` thay thế.
5. **Không gọi `getEncoded()` để in ra khóa:** raw bytes có thể bị sao chép vào bộ nhớ/log; trong HSM khóa có thể không xuất được.
6. **Không tạo cặp ECDH là đủ an toàn phiên mạng:** phải có **peer authentication, public key validation, KDF, transcript binding và AEAD** theo giao thức chuẩn.

### Vấn đề với `KEK` trong demo

Hai khóa AES được sinh riêng, nhưng chỉ một **AES key object trong JVM** không tự tạo ra hệ thống **key wrapping**. Cơ chế bọc DEK phải được chọn và triển khai đúng theo đặc tả hoặc API KMS. Trong thiết kế thực tế, nên cân nhắc **KEK được quản lý trong KMS/HSM**, không để ứng dụng tự giữ raw KEK nếu không có lý do và kiểm soát phù hợp.

## 11. Java 11+: HKDF-SHA-256 để dẫn xuất subkey có domain separation

Mã dưới đây minh họa **hai khóa con 32 byte** từ cùng master secret 32 byte, với nhãn `info` khác nhau. Đây là **ví dụ học thuật về HKDF-Extract và một block HKDF-Expand**, không phải key schedule mạng production.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HkdfDomainSeparationDemo {
    private static final SecureRandom RNG = new SecureRandom();

    static byte[] hmacSha256(byte[] key, byte[] input)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(input);
    }

    static byte[] hkdfExpandOneBlock(byte[] prk, String info)
            throws GeneralSecurityException {
        // ĐÚNG MỘT block output cho SHA-256: T(1)=HMAC(PRK, info || 0x01).
        // Trong production dùng implementation HKDF chuẩn.
        byte[] context = info.getBytes(StandardCharsets.UTF_8);
        byte[] expandedInput = Arrays.copyOf(context, context.length + 1);
        expandedInput[context.length] = (byte) 1;
        try {
            return hmacSha256(prk, expandedInput); // 32 byte
        } finally {
            Arrays.fill(expandedInput, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] masterSecret = new byte[32];
        byte[] salt = new byte[32];
        RNG.nextBytes(masterSecret); // IKM có entropy cao cho ví dụ
        RNG.nextBytes(salt);         // salt không cần là bí mật

        byte[] prk = null;
        byte[] recordKey = null;
        byte[] webhookKey = null;
        try {
            // HKDF-Extract(salt, IKM).
            prk = hmacSha256(salt, masterSecret);

            // Các label cố định, khác nhau về PURPOSE.
            // Với context biến đổi theo tenant/session, dùng encoding
            // chính tắc có length-prefix theo đặc tả hệ thống.
            recordKey = hkdfExpandOneBlock(
                    prk, "billing/v1/prod/tenant-a/aes-gcm-record");
            webhookKey = hkdfExpandOneBlock(
                    prk, "billing/v1/prod/tenant-a/hmac-webhook");

            System.out.println("Derived keys equal: "
                    + MessageDigest.isEqual(recordKey, webhookKey));

            // Không in raw key bytes, PRK hoặc masterSecret.
            // Production cần xác thực scope, version và bảo vệ master.
        } finally {
            Arrays.fill(masterSecret, (byte) 0);
            Arrays.fill(salt, (byte) 0);
            if (prk != null) Arrays.fill(prk, (byte) 0);
            if (recordKey != null) Arrays.fill(recordKey, (byte) 0);
            if (webhookKey != null) Arrays.fill(webhookKey, (byte) 0);
        }
    }
}
~~~

**Kết quả điển hình**:

~~~text
Derived keys equal: false
~~~

Kết quả `false` chỉ minh họa hai label dẫn xuất khác output trong lần chạy; nó **không chứng minh một định lý** về tính độc lập. Bảo đảm thực sự dựa trên **HKDF và độ mạnh IKM/PRK trong mô hình mật mã**. Code chỉ sinh một block 32 byte; nếu cần output dài hơn, dùng thư viện HKDF chuẩn và tuân theo giới hạn/đặc tả.

### Giới hạn an toàn

- **Master và PRK vẫn có thể có bản sao trong provider/JVM.** `Arrays.fill` chỉ là biện pháp *best effort*, không bảo đảm xóa mọi bản sao bí mật trong bộ nhớ.
- **Cùng master + salt + info tạo cùng subkey.** Muốn phiên bản mới cần master hoặc context/salt được thiết kế lại theo key schedule.
- Nếu master bị lộ, đối thủ có thể tính lại cả hai subkey. **Không dùng một master chung khi threat model yêu cầu các key hoàn toàn tách miền compromise**.
- Đoạn mã **không thực hiện encryption hoặc MAC**. Trong production, khóa AES cần nonce/AAD/tag đúng; HMAC cần serialization, anti-replay và chính sách phân phối.
- Nếu master là password, quy trình tạo phải dùng **password hashing/password-based KDF** phù hợp; đoạn `RNG.nextBytes` không mô phỏng password-derived master.
- **`info` phải được ràng buộc đúng danh tính, giao thức và scope**; tránh cho một tenant tùy ý yêu cầu HKDF của tenant khác từ cùng master.
- Không tự dùng HKDF demo làm thay thế key schedule chuẩn của TLS 1.3.

## 12. Cách ly độc lập ở ba lớp: vật liệu, quyền và vận hành

Tính độc lập có **ít nhất ba chiều** cần xem xét.

~~~mermaid
flowchart TD
    I[Thiết kế Independent keys] --> M[Cryptographic separation]
    I --> P[Authorization separation]
    I --> O[Operational separation]
    M --> MS[Khác vật liệu hoặc subkey đúng domain]
    P --> PS[Principal, tenant, purpose và key usage riêng]
    O --> OS[Rotation, backup, incident và audit theo key]
    MS --> B[Giới hạn phạm vi tác động]
    PS --> B
    OS --> B
~~~

### 12.1. Cryptographic separation

Đảm bảo raw key không bị dùng chung trái mục đích; nếu dùng KDF, domain separation và master protection phải đúng.

### 12.2. Authorization separation

Một service có quyền `GenerateMac` không nên mặc nhiên có quyền `Decrypt` DEK hoặc `Sign` bằng private key khác. IAM/role/grant phải ánh xạ theo **key ID/version + operation + principal + scope**.

### 12.3. Operational separation

Các key nên có **owner, custodian, cryptoperiod, key policy, key inventory, backup, rotation và incident runbook** theo rủi ro. Nếu tất cả cùng nằm sau một master, một superadmin hoặc một backup plaintext, đó là **điểm rủi ro chung** cần được ghi nhận.

### Không hứa hẹn “mất một key không ảnh hưởng key khác” nếu có shared boundary

Một kẻ tấn công chiếm root account KMS có thể ảnh hưởng nhiều tài nguyên, ngay cả khi vật liệu được sinh riêng. Tính độc lập mật mã **không tự chuyển thành độc lập quyền quản trị hoặc an toàn trước compromise của hạ tầng chung**.

## 13. Independent DEK và KEK trong envelope encryption

**Envelope encryption** thường sử dụng hai tầng:

1. **DEK (Data Encryption Key)** trực tiếp mã hóa plaintext bằng AEAD như AES-GCM.
2. **KEK (Key Encryption Key)** trong KMS/HSM bảo vệ DEK qua cơ chế wrap/unwrap hoặc API mã hóa khóa phù hợp.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant KMS as KMS/HSM
    participant DB as Data store
    App->>KMS: Yêu cầu DEK mới / key material theo policy
    KMS-->>App: DEK plaintext dùng ngắn hạn + wrapped DEK (nếu API hỗ trợ)
    App->>App: AES-GCM Encrypt dữ liệu bằng DEK, nonce mới
    App->>DB: Ciphertext, tag, nonce, wrapped DEK, KEK ID
    Note over App: Không ghi raw DEK vào log, giới hạn cache
    DB-->>App: Ciphertext + wrapped DEK + metadata
    App->>KMS: Unwrap/Decrypt DEK bằng KEK được cấp quyền
    KMS-->>App: DEK plaintext (nếu API cho phép)
    App->>App: AES-GCM Decrypt và kiểm tra tag/AAD
~~~

### DEK/KEK có thật sự độc lập?

- Trong một thiết kế điển hình, **DEK sinh ngẫu nhiên riêng**; **KEK là key material khác**, có purpose và quyền khác.
- KMS có thể tạo DEK và trả **cả plaintext DEK lẫn bản bọc** theo API; nội dung và tính năng thực tế phụ thuộc nhà cung cấp.
- Nếu cả DEK và KEK được dẫn xuất từ cùng master mà không có policy/đánh giá rủi ro, khả năng cách ly khi master lộ sẽ kém hơn mô hình cần master/KEK được bảo vệ riêng.
- **DEK và KEK có vòng đời khác**: rotate KEK có thể chỉ **rewrap** DEK, còn rotate DEK có thể phải **re-encrypt** dữ liệu.

### Tại sao không dùng KEK để mã hóa trực tiếp mọi record?

Trộn KEK và DEK làm gia tăng số lần dùng vật liệu có phạm vi lớn, khó phân quyền và khó phục hồi/rotation. Khóa dùng bọc DEK nên được quản trị riêng với khóa dùng mã hóa dữ liệu.

### Khi một DEK bị lộ

**Rewrap DEK đó bằng KEK mới không phục hồi tính bí mật.** Kẻ tấn công có bản sao DEK vẫn giải mã được ciphertext liên quan. Cần đánh giá **thay DEK và re-encrypt dữ liệu**, đồng thời xem xét dữ liệu đã bị sao chép hoặc giải mã.

### Khi một KEK bị lộ

Phải đánh giá tập **wrapped DEK** và khả năng đối thủ tiếp cận chúng. Những DEK được bảo vệ bởi KEK có thể bị ảnh hưởng tùy cơ chế và dữ liệu đối thủ giữ. Đổi KEK chỉ là một phần của ứng cứu; không mặc định mọi ciphertext trước đó an toàn trở lại.

## 14. Independent signing keys và agreement keys

### 14.1. Khóa ký số

Mỗi **private signing key** cần mục đích và phạm vi rõ: ký hóa đơn, phát hành software artifact, ký access token hoặc ký chứng thư PKI. **Không trộn các quy trình này chỉ vì cùng là ECDSA hoặc RSA-PSS**.

Public key tương ứng có thể được công bố trong certificate/JWKS. Khi private key ký bị rotate, **public verification key cũ** có thể cần lưu để xác minh chữ ký lịch sử theo retention. Việc key ký cũ không còn active **không tự làm chữ ký cũ biến mất**.

### 14.2. Khóa ECDH/X25519

Khóa agreement dùng tạo **shared secret**, sau đó **KDF** dẫn xuất traffic keys. Không tự dùng agreement private key như signing key. Một giao thức ECDH thuần túy **không tự chống MITM**; public peer key và transcript phải được xác thực theo AKE chuẩn.

### 14.3. Ephemeral keys và forward secrecy

Với ECDHE, mỗi handshake có thể sinh private agreement key tạm thời, hỗ trợ **forward secrecy** khi giao thức xác thực đúng và bí mật tạm được loại bỏ theo thiết kế. Không nên lưu private ephemeral key vào key inventory dài hạn; thay vào đó quản trị **policy/giao thức/provider** và các key dài hạn liên quan.

**Một signing key dài hạn và một ephemeral ECDH key không phải hai phiên bản của cùng purpose.** Chúng có key usage, cryptoperiod và tác động compromise khác nhau.

### 14.4. HMAC và signing key khác nhau

Với HMAC, cả người tạo và người xác minh MAC biết **cùng symmetric secret**. Với chữ ký số, private signing key có thể chỉ ở bên ký, còn bên xác minh dùng **public key**. Vì thế **ranh giới phân phối khóa, điều kiện thu hồi và số bản sao bí mật** rất khác nhau.

## 15. Multi-tenant, multi-service và multi-environment

Trong SaaS, việc dùng **cùng một secret** cho tất cả tenant có thể tạo điểm lỗi chung, kể cả khi mỗi tenant có key ID ảo.

### 15.1. Các cách phân đoạn

| Mô hình | Phù hợp khi | Điểm cần đánh giá |
| --- | --- | --- |
| **DEK riêng cho từng object/record** | Cần granularity nhỏ, envelope encryption | Số lượng key, metadata, chi phí unwrap |
| **DEK riêng theo tenant hoặc data shard** | Cần giới hạn phạm vi tenant | Mức độ dùng key/nonce và blast radius mỗi tenant |
| **KEK riêng theo tenant** | Yêu cầu cách ly mạnh hơn | IAM, quota, rotation, backup và vận hành |
| **Một KEK chung, DEK riêng theo tenant** | Chấp nhận rủi ro chung ở KEK, quản trị đơn giản | KEK compromise có thể ảnh hưởng nhiều DEK |
| **Subkey HKDF theo tenant từ master chung** | Protocol/hierarchy chấp nhận master là trust root | Master compromise ảnh hưởng mọi tenant; cần context chuẩn |
| **Khóa riêng dev/staging/prod** | Giảm nguy cơ môi trường thấp lộ khóa production | Không sao chép raw key qua môi trường |
| **Khóa riêng signing và agreement** | Khác key usage và threat model | Certificate, KMS permissions, lifecycle |

**Không có lựa chọn duy nhất đúng cho mọi hệ thống.** Quyết định phải dựa trên phân loại dữ liệu, nghĩa vụ cách ly tenant, hiệu năng, giới hạn provider và chi phí quản lý.

### 15.2. Context theo tenant không thay thế IAM

Nếu dùng cùng master và HKDF `info=tenantId`, kẻ tấn công có quyền **gọi API derive subkey tùy ý với tenantId bất kỳ** có thể tạo khóa cho tenant khác. Cần kiểm tra **principal ↔ tenant** ở API và boundary; không coi tham số `tenantId` do client gửi là bằng chứng ủy quyền.

### 15.3. Cẩn trọng với bản sao môi trường

Không clone cơ sở dữ liệu production kèm plaintext DEK/KEK hoặc private signing key sang staging để kiểm thử. Nếu cần dữ liệu thử, dùng **khóa và dữ liệu thay thế** hoặc quy trình khử nhạy cảm phù hợp, không tái sử dụng secret production trong môi trường ít kiểm soát.

## 16. KMS/HSM hỗ trợ sinh và quản lý independent keys thế nào?

**KMS/HSM** thường cung cấp cách sinh, lưu giữ và thực thi phép toán đối với khóa theo chính sách. Nhưng khả năng **sinh key, sinh DEK, dẫn xuất subkey, tạo cặp EC/RSA, import, export và backup** khác nhau giữa các sản phẩm.

### Các câu hỏi cần hỏi nhà cung cấp

1. **Generation provenance:** Key được tạo trong cryptographic boundary nào? Nguồn RNG/DRBG ra sao?
2. **Key types/algorithms:** Có hỗ trợ AES, HMAC, RSA, EC P-256, X25519, key agreement và wrapping theo nhu cầu?
3. **Non-exportable:** Loại nào thật sự không xuất raw material? Có ngoại lệ backup/replication?
4. **Key derivation:** Có API `DeriveKey`/HKDF hoặc chỉ `GenerateDataKey`/Encrypt/Decrypt/Sign?
5. **Key ID vs material version:** Một logical key resource có thể có nhiều backing material version? Alias thay đổi thế nào?
6. **IAM:** Có giới hạn theo key/operation/principal/tenant/context, hoặc cần business gate ngoài KMS?
7. **Audit:** Có log generation, grant, `Decrypt/Sign/Derive` và thay policy với key ID/version?
8. **Lifecycle:** Disable, rotate, pending deletion, restore và replica hoạt động ra sao?
9. **Blast radius:** Một principal hoặc administrator có thể tự sửa key policy và sử dụng nhiều key?
10. **DR:** Nếu một region, HSM partition hoặc key store bị mất, khóa và dữ liệu có phục hồi được theo chính sách không?

### Đừng ngộ nhận độc lập do resource ID

Hai key resources có thể cùng chịu rủi ro từ **một root IAM principal**, provider account hoặc bản backup. “Independent keys” ở lớp vật liệu không đồng nghĩa **independent trust domain**. Muốn cách ly cao, có thể cần phân tách account/tenant/partition và vai trò theo threat model.

### HSM và key derivation

Một số HSM cho phép dẫn xuất subkey với **non-exportable parent key**, trả về child key handle không xuất được. Một số KMS không cung cấp phép dẫn xuất tùy ý. **Không được mặc định mọi cloud KMS có thể thực hiện HKDF bên trong HSM**; cần xác minh API, thuật toán và chính sách nhà cung cấp.

## 17. Quản lý key inventory, purpose và vòng đời

Independent keys chỉ có ý nghĩa vận hành khi tổ chức biết **mỗi khóa phục vụ gì**, được tạo từ đâu, đang ở trạng thái nào và có quan hệ cha–con hay không.

### Ví dụ metadata cho hai mô hình

~~~yaml
# Dữ liệu mẫu, không phải schema KMS tiêu chuẩn.
keys:
  - keyId: "billing-dek-v2"
    generationModel: "INDEPENDENT_RANDOM"
    purpose: "DATA_AT_REST_ENCRYPTION"
    algorithm: "AES-256-GCM"
    environment: "production"
    tenantScope: "billing"
    materialLocation: "protected-key-handle-or-wrapped-DEK"
    parentKeyId: null
    lifecycleState: "ACTIVE"
    owner: "billing-data-owner"
    custodian: "platform-key-team"
    approvedOperations: ["Encrypt", "Decrypt"]

  - keyId: "billing-webhook-subkey-v2"
    generationModel: "KDF_DERIVED"
    purpose: "WEBHOOK_AUTHENTICATION"
    algorithm: "HMAC-SHA-256"
    environment: "production"
    tenantScope: "billing"
    materialLocation: "protected-key-handle"
    parentKeyId: "billing-master-v2"
    kdf: "HKDF-SHA-256"
    derivationContextReference: "billing-v2-webhook-domain"
    lifecycleState: "ACTIVE"
    owner: "billing-integration-owner"
    custodian: "platform-key-team"
    approvedOperations: ["GenerateMac", "VerifyMac"]
~~~

**Không lưu master, raw DEK/HMAC key, seed, private scalar hay PRK** trong key inventory. Việc ghi `parentKeyId` là để **quản trị dependency và blast radius**, không biến inventory thành kho secret.

### Key state và cryptoperiod

| Trạng thái | Với independent key | Với subkey dẫn xuất |
| --- | --- | --- |
| **Pre-activation** | Đã sinh, chưa cho phép new-use | Đã định nghĩa master/context và quyền, chưa cho dùng |
| **Active** | Dùng đúng purpose và operation | Dẫn xuất/sử dụng subkey theo key schedule được duyệt |
| **Suspended** | Chặn key ID/version và đường sử dụng | Có thể phải chặn khả năng derive lại hoặc sử dụng subkey đã cache |
| **Deactivated** | Ngừng tạo bảo vệ mới, xử lý legacy theo policy | Giữ khả năng xử lý dữ liệu cũ nếu cần master/context |
| **Compromised** | Đánh giá dữ liệu phụ thuộc khóa đó | Nếu **master** lộ, phải đánh giá tất cả descendants |
| **Destroyed** | Hủy vật liệu và bản sao theo chính sách | Hủy master có thể làm **mọi descendant không thể rederive** |

### Xoay khóa con có nhất thiết đổi master?

Không phải lúc nào cũng vậy. Một giao thức có thể dẫn xuất subkey mới từ master còn an toàn với context/epoch mới. Nhưng nếu **master nghi lộ**, chỉ đổi label hoặc epoch dưới master cũ **không phục hồi tính bí mật**. Phải đánh giá thay master và mọi subkey liên quan.

## 18. Rotation và compromise: độc lập giúp giảm phạm vi tới đâu?

### 18.1. Lộ một DEK sinh ngẫu nhiên riêng

Khi DEK `record-v7` bị lộ, cần ngừng dùng nó cho dữ liệu mới, kiểm kê ciphertext đã mã hóa bằng DEK đó và đánh giá **re-encrypt**. Các DEK khác được sinh an toàn và lưu trong boundary khác **không tự động bị suy ra** từ DEK v7; tuy nhiên phải kiểm tra nguồn lộ có liên quan nhiều key không.

### 18.2. Lộ một subkey HKDF

Nếu chỉ lộ `K_webhook`, trong thiết kế HKDF đúng, đối thủ **không mặc nhiên tính được** `K_record` hoặc master. Nhưng nếu nguyên nhân là đọc được **master secret** hoặc service có API derive các purpose khác, phạm vi không còn giới hạn ở một subkey.

### 18.3. Lộ master key của một cây dẫn xuất

Master lộ thì **mọi subkey có thể được dẫn xuất lại** trong scope tương ứng. Cần coi đây là sự cố ảnh hưởng **toàn bộ cây phụ thuộc**, xử lý cả output trước đây và những key dự định tạo sau đó từ cùng master.

### 18.4. Lộ KEK nhưng DEK được sinh riêng

Nếu đối thủ có KEK và các **wrapped DEK** tương ứng, có thể ảnh hưởng tới nhiều DEK tùy cơ chế wrap. Phải đánh giá ciphertext và quyền truy cập. **Tính độc lập ban đầu của DEK so với KEK không có nghĩa DEK luôn an toàn sau khi bản bọc của nó bị mở**.

### 18.5. Lộ credential KMS

Nếu credential có quyền `Decrypt` với hàng nghìn key, kẻ tấn công có thể **khai thác quyền**, dù không biết raw material và các khóa được sinh độc lập. Đây là rủi ro **authorization boundary**, cần thu hồi credential/grant, xem log sử dụng và đánh giá đầu ra KMS đã bị lấy.

### Ma trận rủi ro tóm tắt

| Compromise | Đánh giá đầu tiên | Không được kết luận |
| --- | --- | --- |
| Một DEK độc lập | Ciphertext, dữ liệu và các bản sao DEK | “Mọi DEK khác chắc chắn vô sự” nếu chưa xét nơi lộ |
| Một HMAC subkey | Thông điệp/MAC, partner, derivation API | “Lộ subkey nghĩa là master đã lộ” |
| Master secret | Tất cả descendant keys, dữ liệu lịch sử | “Đổi mỗi nhãn `info` là đủ” |
| KEK | Wrapped DEK, permissions, ciphertext | “DEK độc lập nên mọi bản bọc vẫn an toàn” |
| Signing private key | Chữ ký đã phát, chứng thư, trust, identity | “Chỉ cần disable khóa là xóa chữ ký cũ” |
| KMS administrator credential | IAM, grants, audit, key resources | “Các key độc lập nên một admin lộ không gây lan truyền” |

## 19. Kiểm thử: làm sao biết thiết kế thực sự tách khóa?

**Không thể chứng minh tính an toàn của một DRBG/KDF bằng cách tạo 100 khóa rồi thấy chúng khác nhau.** Các thử nghiệm thống kê đơn giản không thay thế đánh giá thuật toán, provenance và provider. Nhưng bạn có thể kiểm tra những **bất biến thiết kế và đường quyền** rất cụ thể.

### Checklist kiểm thử kỹ thuật

1. **Key provenance:** Mỗi key có bằng chứng được tạo từ đúng API/thuật toán/provider hay dẫn xuất bằng KDF chuẩn.
2. **No duplicate material by construction:** Không có code sao chép `getEncoded()` từ DEK sang HMAC/KEK; không tạo aliases trỏ nhầm cùng material.
3. **Domain labels:** Mỗi purpose/protocol/tenant/role có context không mơ hồ, không trùng ID; có test cho encoding.
4. **KDF test vectors:** So khớp implementation HKDF với **test vectors chuẩn**, không chỉ xem hai output có khác nhau.
5. **Wrong-purpose negative test:** Workload webhook không thể gọi `Decrypt` hoặc `Sign` bằng key thuộc purpose khác.
6. **Cross-tenant negative test:** Tenant A không thể truy vấn/derive/access key của tenant B qua API hoặc thay ID.
7. **Lifecycle test:** Key pre-activation/suspended không thể dùng cho new-use ở provider và app.
8. **Rotation test:** Thay DEK không khiến record cũ trỏ nhầm key; thay KEK không làm mất wrapped DEK.
9. **DR/snapshot test:** Restore VM/container/DRBG không dẫn đến tái dùng key hoặc nonce trong điều kiện triển khai đã kiểm tra.
10. **Backup access test:** Một operator không thể tải nhiều key plaintext từ nơi sao lưu không theo policy.
11. **Audit reconciliation:** Key ID/version trên ciphertext, wrapper, signature và log khớp inventory.
12. **Master compromise tabletop:** Phải chỉ ra được toàn bộ descendant keys và runbook thay khóa tương ứng.

### Ví dụ các kiểm thử cần được từ chối

~~~text
Request:
  principal = webhook-service
  operation = kms:Decrypt
  keyId = billing-record-dek-v4
Expected:
  DENIED

Request:
  principal = billing-service
  operation = HKDF-derive
  tenant = tenant-B    # nhưng principal chỉ thuộc tenant-A
Expected:
  DENIED

Request:
  principal = app-worker
  operation = Sign
  keyId = billing-ecdsa-signing-v2
  state = SUSPENDED
Expected:
  DENIED
~~~

Các kết quả phải được kiểm tra **ở provider hoặc đường sử dụng thực**, không chỉ trong một unit test hàm `if`. Unit test giúp kiểm tra logic; integration test chứng minh IAM/resource policy thực sự cưỡng chế.

## 20. Case study: Billing thiết kế lại kho khóa

### Bối cảnh

Một nhóm phát triển xây hệ thống hóa đơn gồm: lưu hóa đơn mã hóa, ký hóa đơn, gửi webhook và quản lý token đăng nhập. Phiên bản cũ sử dụng một `billing-master-secret` trong biến môi trường và tạo nhiều khóa bằng cách **hash master ghép tên chức năng**.

Vấn đề:

- Không có chuẩn KDF, không có version context rõ ràng.
- `billing-master-secret` nằm trong cùng môi trường của nhiều dịch vụ.
- Khi secret lộ, **mọi mục đích** đều bị ảnh hưởng.
- Rotation một nhánh có thể phá dữ liệu của nhánh khác.
- Không có key inventory hoặc phân quyền theo purpose.

### Thiết kế phân tách

| Nhu cầu | Thiết kế gợi ý | Ranh giới |
| --- | --- | --- |
| Mã hóa bản ghi | **DEK riêng**, sinh bằng CSPRNG hoặc KMS GenerateDataKey theo policy | Dữ liệu/tenant hoặc shard |
| Bọc DEK | **KEK trong KMS/HSM** khác DEK | KMS IAM, key ID/version |
| Ký hóa đơn | **Private signing key pair riêng**, không xuất khi phù hợp | Billing signing workflow |
| Webhook đối tác | **HMAC key riêng theo partner** hoặc subkey domain-separated dưới secret được bảo vệ | Mỗi đối tác |
| Ký JWT | **Signing key riêng** của identity service | Identity/token issuance |
| TLS/ECDH | Theo **TLS stack** với ephemeral key agreement và authentication key đúng mục đích | Phiên/giao thức |
| Recovery | **Recovery KEK/path riêng** có quyền, dual control khi rủi ro yêu cầu | Sự cố/phục hồi |

~~~mermaid
flowchart TD
    Data[Hóa đơn] --> AES[AES-GCM với DEK riêng]
    AES --> Store[(Ciphertext + key/version/nonce/tag)]
    DEK[DEK theo record/tenant] --> AES
    DEK --> Wrap[Wrapped DEK]
    KEK[KEK KMS được quản lý riêng] --> Wrap
    Wrap --> Store
    Invoice[Hóa đơn đã duyệt] --> Sign[Signing key HSM riêng]
    Sign --> Cert[Signature + cert/public verification key]
    Webhook[Webhook event] --> MAC[HMAC key theo partner]
    MAC --> Tag[MAC + key version]
    Identity[Identity service] --> JWT[JWT signing key độc lập]
    TLS[HTTPS client/server] --> Agreement[Ephemeral ECDHE + authenticated TLS]
~~~

### Cách chuyển đổi từ hệ thống cũ

1. **Kiểm kê** master hiện tại, đầu ra dẫn xuất, nơi giữ secret và dữ liệu phụ thuộc.
2. **Đánh giá compromise**: nếu master đã bị lộ, cần phân tích mọi output/ciphertext/chữ ký đã phát, không chỉ key mới.
3. **Sinh key mới** qua KMS/HSM hoặc JCA provider được phê duyệt cho từng purpose.
4. **Chuẩn bị reader/verifier** nhận key version mới, chứng thư/JWKS/HMAC secret theo kênh an toàn.
5. **Chuyển new-use** sang key mới theo rollout có kiểm soát.
6. **Rewrap/re-encrypt** hoặc giữ legacy decrypt/verify đúng retention; tránh hủy key cũ khi dữ liệu chưa được di chuyển.
7. **Thu hồi quyền** dịch vụ đối với secret chung; xóa secret cũ và bản backup theo điều kiện đã xác minh.
8. **Audit và negative tests**: xác nhận không service nào còn dùng raw master cho những purpose không được phép.

### Điểm dễ bị hiểu sai

Một thiết kế dùng **mỗi key một KMS resource** có thể tăng khả năng kiểm soát nhưng cũng tăng số policy và thao tác. Một thiết kế dùng **HKDF** có thể đơn giản hơn cho key schedule tạm, nhưng master là điểm rủi ro chung. Quyết định phải dựa trên mục tiêu cách ly và khả năng vận hành, không dựa vào số lượng tên key.

## 21. Sai lầm phổ biến và cách xử lý

| Sai lầm | Hậu quả | Phòng tránh |
| --- | --- | --- |
| Sinh hai key ID nhưng cùng raw secret | Không có cryptographic independence | Kiểm tra đường tạo, không copy material |
| Tự hash timestamp/seed cố định để tạo nhiều key | Khóa có thể tính lại | CSPRNG/DRBG đủ entropy |
| Tự nghĩ `SHA-256(master || purpose)` là key schedule an toàn cho mọi trường hợp | Thiếu đặc tả và domain separation chuẩn | HKDF/KDF chuẩn, context có cấu trúc |
| Tin `different info` làm HKDF subkeys độc lập tuyệt đối | Master compromise vẫn ảnh hưởng tất cả | Ghi rõ dependency/parent ID và rủi ro chung |
| Dùng lại raw AES key làm HMAC key | Trộn cryptographic purpose | Key riêng hoặc subkey tách miền |
| Cùng EC private key cho ECDSA và ECDH | Tăng cross-protocol và key-usage risk | Tạo cặp ký và agreement riêng |
| Sao chép private key production sang staging | Môi trường kém an toàn lộ khóa thật | Khóa khác theo environment |
| Nhiều tenant dùng key chung mà không có chính sách | Blast radius lớn | Phân đoạn theo data scope và risk tier |
| Lấy `tenantId` từ request làm HKDF info nhưng không xác thực quyền | Cross-tenant derivation | IAM/principal-tenant binding |
| Cho rằng KMS hai key resource là hai trust domain | Root admin/credential có thể dùng cả hai | Tách admin quyền/boundary khi cần |
| Lưu master và tất cả subkeys cùng một file plaintext | Một lần lộ lấy toàn bộ bí mật | KMS/HSM, least privilege, no raw secret logging |
| Dùng UUID/tên alias làm key material | Không đủ entropy/threat model | KeyGenerator/SecureRandom/KMS |
| Clone VM snapshot sau khi tạo DRBG state | Có thể phát trùng chuỗi khóa | Provider/runtime hỗ trợ reseed/clone, đánh giá môi trường |
| Dựa vào equality test 100 key để chứng minh RNG an toàn | Test không chứng minh security properties | Thẩm định nguồn/provider, chuẩn và test vectors |
| Rewrap DEK đã bị lộ rồi tuyên bố an toàn | Đối thủ vẫn có raw DEK | Thay DEK, re-encrypt và ứng cứu |
| Xoay master nhưng không rà soát cây subkey cũ | Descendants vẫn bị lộ/phụ thuộc | Dependency mapping và migration |
| Hủy master khi còn subkey cần rederive | Mất khả năng phục hồi/giải mã | Retention và restore tests |
| In `getEncoded()` để debug | Có thể làm lộ raw key trong log | Chỉ in metadata/key ID |
| Coi non-exportable là không thể lạm dụng | Workload có thể dùng signing/decrypt oracle | Authorization và business gate |
| Thiếu inventory parent/subkey | Không xác định phạm vi master compromise | Quản lý lineage, key version, KDF context |
| Không phân biệt independent key và public/private pair | Nhầm cấu trúc toán học | Giải thích cặp liên quan; sinh pair riêng theo purpose |

## 22. Checklist triển khai Independent keys trong production

1. **Purpose:** Mỗi khóa có mục đích, dữ liệu/giao thức và phạm vi được phê duyệt rõ ràng?
2. **Model:** Cần **độc lập bằng vật liệu sinh riêng**, hay các subkey HKDF được tách miền là đủ cho threat model?
3. **Entropy:** Source CSPRNG/DRBG, HSM/KMS và cấu hình sinh khóa có được đánh giá?
4. **Seed:** Không có hard-coded seed, timestamp, PID hoặc `java.util.Random` làm nguồn key?
5. **Fork/snapshot:** Provider/runtime/container có kế hoạch xử lý clone hoặc phục hồi trạng thái RNG?
6. **Material reuse:** Có kiểm tra không copy cùng raw key sang AES/HMAC/signing/agreement hoặc các tenant?
7. **Asymmetric pairs:** Signing key pair và agreement key pair được tách đúng usage; public/private trong cùng pair được hiểu là có liên hệ toán học?
8. **KDF:** Nếu dùng HKDF, master/IKM đủ entropy, salt/info theo đúng đặc tả, context canonical và không trùng?
9. **Master boundary:** Có ghi rõ master compromise ảnh hưởng tất cả descendant keys; parent được bảo vệ cao hơn?
10. **Service/tenant:** Mỗi dịch vụ, môi trường và tenant có scope, key policy và grants phù hợp?
11. **KMS/HSM:** Provider hỗ trợ thuật toán, `GenerateDataKey`/`DeriveKey`/key handle và hạn chế export đúng như thiết kế?
12. **DEK/KEK:** Hai vai trò tách biệt; dữ liệu, wrapped DEK, KEK ID và key version có metadata để phục hồi?
13. **AEAD:** Với AES-GCM có nonce không lặp dưới cùng DEK, AAD/tag được xác minh và giới hạn sử dụng?
14. **HMAC:** Key riêng hoặc subkey được tách miền, có anti-replay và phiên bản đối tác?
15. **Sign/ECDH:** Chữ ký số và key agreement dùng cặp riêng; peer public key được xác thực và Z qua KDF chuẩn?
16. **Identity/IAM:** Workload chỉ dùng đúng key/operation/purpose; không thể tự mở policy hay derive cho tenant khác?
17. **Key inventory:** Có key ID/version, origin, purpose, owner/custodian, cryptoperiod, parent-child lineage khi có?
18. **Pre-activation/Active:** Khóa mới không dùng production trước phê duyệt; operation sai bị provider từ chối?
19. **Rotation:** Có trigger scheduled/usage/event, kế hoạch rewrap/re-encrypt, cutover và rollback?
20. **Compromise:** Runbook phân biệt lộ child, master, KEK, DEK, signing key và IAM credential?
21. **Recovery/DR:** Key material có backup/restore đúng boundary; không hủy master/KEK khi còn dữ liệu phụ thuộc?
22. **Audit:** Ghi generation, key origin, policy, operation, key version và incident mà không log secret?
23. **Tests:** Có negative tests, KDF vectors, kiểm thử mã hóa/giải mã và chống wrong-tenant/wrong-purpose?
24. **Tính khả dụng:** Số lượng khóa, hạn mức KMS, latency và chi phí có nằm trong kế hoạch khi tăng phân đoạn?
25. **Review định kỳ:** Có kiểm tra key reuse ngoài dự kiến, orphan keys, quyền rộng và dependency trước destruction?

### Ghi nhớ

**Independent keys** trong thực tế có thể là **những khóa được sinh riêng bằng CSPRNG/DRBG đáng tin** hoặc những **subkey được dẫn xuất với domain separation qua KDF chuẩn**. Hai mô hình có thể cùng cung cấp sự tách biệt hữu ích về mặt mật mã, nhưng **subkey cùng master không độc lập tuyệt đối**: lộ master đe dọa mọi descendant có thể dẫn xuất. **Khác key ID, alias, thuật toán hay tên biến không chứng minh hai khóa độc lập**. Thiết kế an toàn phải tách **purpose, key usage, principal, tenant, environment và lifecycle**, đồng thời kiểm tra RNG/entropy, KDF context, key lineage, quyền KMS/HSM, DEK/KEK trong envelope encryption, khóa ký số và ECDH. Khi một key bị lộ, việc phân đoạn đúng giúp giới hạn ảnh hưởng — nhưng **quyền quản trị, master secret, key cache và backup chung vẫn có thể tạo điểm lỗi chung**. Độc lập mật mã chỉ thật sự có giá trị khi đi cùng **quản trị vòng đời, rotation, phân quyền và kiểm toán có thể kiểm chứng**.
