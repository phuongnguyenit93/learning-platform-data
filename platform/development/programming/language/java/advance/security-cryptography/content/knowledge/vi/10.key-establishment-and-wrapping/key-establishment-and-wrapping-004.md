# 10.4 Bí mật chung, bước dẫn xuất khóa, ngữ cảnh sử dụng và tách khóa theo mục đích

Trong một giao thức mã hóa, hai bên có thể thực hiện thỏa thuận khóa như **X25519/ECDH** và thu được cùng một **bí mật chung (shared secret)**. Nhưng từ việc có cùng bí mật đó đến việc dùng an toàn các khóa cho **mã hóa hai chiều, MAC, bọc khóa dữ liệu (key wrapping)** và những mục đích khác còn một bước bắt buộc: **dẫn xuất khóa (key derivation) với ngữ cảnh và nhãn mục đích đúng**.

Không nên lấy thẳng các byte shared secret làm khóa AES, không cắt tùy ý thành nhiều khóa, và càng không sử dụng cùng một khóa cho nhiều thuật toán/hướng truyền. Bài học đi sâu vào **HKDF Extract/Expand, transcript/context binding, domain separation, phân chia vai trò gửi–nhận, phân biệt DEK/KEK**, cùng ví dụ Java 17+ chạy độc lập.

## 1. Mục tiêu và các thuật ngữ

Khi học xong, bạn có thể:

1. Mô tả vì sao **key agreement không đồng nghĩa đã có session key an toàn** và không tự xác thực danh tính.
2. Phân biệt **shared secret/IKM**, **PRK** sau HKDF-Extract và **OKM** sau HKDF-Expand; hiểu vai trò của `salt` và `info`.
3. Ràng buộc khóa với **phiên bản giao thức, thuật toán, transcript, vai trò, kênh, chiều truyền và mục đích** để tránh sử dụng nhầm khóa.
4. Tạo **khóa AES-GCM theo chiều c2s/s2c**, khóa HMAC và **key-encryption key (KEK)** tách biệt; biết khi nào cần dùng AES key wrap.
5. Triển khai ví dụ X25519 + HKDF-HMAC-SHA256 + AES-GCM + AESWrap trong Java 17+, kiểm chứng được đầu ra và những trường hợp thất bại.
6. Nhận diện lỗi MITM, sai ngữ cảnh, trùng nhãn, nonce reuse, replay, rekey, key confirmation và quản lý vòng đời secret.

Thuật ngữ chính:

| Thuật ngữ | Ý nghĩa | Có cần bí mật? |
| --- | --- | --- |
| **ECDH / X25519** | Cơ chế thỏa thuận bí mật từ private key của một bên và public key của bên kia | Private key phải bí mật; public key có thể công khai |
| **Z / shared secret** | Đầu ra raw của thỏa thuận khóa; hai bên hợp lệ thu cùng byte | **Có**; không phát tán hoặc log |
| **IKM (Input Keying Material)** | Vật liệu bí mật đưa vào HKDF-Extract, thường là shared secret | **Có** |
| **PRK (Pseudorandom Key)** | Khóa giả ngẫu nhiên do HKDF-Extract tạo ra | **Có**; là bí mật trung gian |
| **OKM (Output Keying Material)** | Byte khóa đã dẫn xuất theo `info`, dùng làm traffic key, MAC key, KEK... | **Có** |
| **Salt của HKDF** | Tham số đầu vào Extract; có thể công khai nhưng phải theo giao thức | Không cần bí mật |
| **Info/context** | Nhãn và ngữ cảnh dùng trong Expand để tạo các khóa tách biệt | Thường công khai, nhưng phải nhất quán và được ràng buộc đúng |
| **DEK** | Data Encryption Key: mã hóa dữ liệu thực | **Có** |
| **KEK** | Key Encryption Key: dùng bọc/bảo vệ một DEK hoặc khóa khác | **Có**, phải cách ly mục đích |

**Điểm phân biệt:** HKDF không làm mạnh lên một password yếu thành shared secret có entropy cao; password cần **password KDF/hash** chuyên dụng. HKDF thích hợp cho đầu vào đã có độ ngẫu nhiên/bí mật phù hợp như ECDH secret hoặc một secret master được sinh an toàn.

## 2. Đường đi từ thỏa thuận khóa đến các khóa ứng dụng

Sơ đồ tổng thể:

~~~text
Client                                       Server
  private a                                  private b
  public A = X25519(a, G)                    public B = X25519(b, G)
       \                                     /
        ---- trao đổi public keys A, B ----
       /                                     \
  Zc = X25519(a, B)                     Zs = X25519(b, A)
                    Zc == Zs
                         |
                HKDF-Extract(salt, Z)
                         |
                        PRK
                         |
    +--------------------+-------------------------+
    |                    |                         |
HKDF-Expand(         HKDF-Expand(             HKDF-Expand(
  info="c2s/enc")     info="s2c/enc")          info="wrap/kek")
    |                    |                         |
 client→server key   server→client key             KEK
                         |
               ...MAC/confirm/export keys riêng...
~~~

Ở cấp API, đừng coi `Z` là “khóa AES đã sẵn sàng” dù nó dài 32 byte với X25519. Độ dài đúng **không có nghĩa** byte đã được chuẩn hóa, gắn ngữ cảnh, ràng buộc danh tính hay có thuộc tính thích hợp cho mọi primitive. Đặc biệt, cùng một `Z` có thể xuất hiện ở các mục đích/giao thức khác nhau khi thiết kế thiếu domain separation.

**Key schedule** là tập quy tắc chính xác về cách sinh, đặt tên, phân phát và sử dụng khóa: từ đầu vào bí mật, transcript, vai trò đến thuật toán và thời hạn sử dụng. Một key schedule đúng cần được hai bên tính **giống hệt về byte**, không chỉ “cùng gọi HKDF”.

## 3. Vì sao shared secret không nên dùng trực tiếp?

### 3.1. Shared secret là vật liệu đầu vào, không phải khóa đa năng

Ví dụ X25519 trả một chuỗi byte 32 byte qua `KeyAgreement.generateSecret()`. Dù 32 byte trông vừa đủ cho AES-256, vẫn cần làm rõ:

- **Bí mật đó thuộc phiên nào?** Nếu dùng lại trong nhiều ngữ cảnh, khóa sẽ không tự tách theo phiên/giao thức.
- **Hai vai trò đối xứng hay có hướng?** Cùng một khóa c2s và s2c có thể dẫn đến rủi ro nonce trùng nếu cách phân phối nonce không được phối hợp.
- **Khóa sẽ dùng cho mục đích nào?** Encryption, MAC, xác thực handshake và key wrapping có yêu cầu và vòng đời khác.
- **Thuật toán nào đang được thương lượng?** Một suite mới không nên vô tình tạo cùng khóa với suite cũ.
- **Ngữ cảnh/đối tượng nào được bảo vệ?** Nếu khóa dùng đa tenant, đa channel hoặc nhiều loại thông điệp, cần tránh cross-context/key-confusion.

Dùng HKDF giúp **chuẩn hóa vật liệu, hỗ trợ xuất nhiều khóa với nhãn riêng và ràng buộc vào ngữ cảnh**. KDF không sửa được các lỗi như lộ private key, public key giả hoặc cấu hình giao thức thiếu xác thực.

### 3.2. Điều gì xảy ra nếu chỉ cắt secret?

Sai lầm ví dụ:

~~~java
// Không nên làm kiểu này:
byte[] raw = agreement.generateSecret();
byte[] encryptionKey = Arrays.copyOfRange(raw, 0, 16);
byte[] macKey = Arrays.copyOfRange(raw, 16, 32);
~~~

Đây không phải key schedule đã thẩm định. Hai đoạn không có nhãn mục đích, không được dẫn xuất theo transcript/role, và bạn đã tự giả định rằng các đoạn byte raw có thuộc tính độc lập phù hợp với mọi thuật toán. Cách đúng là **HKDF-Extract một lần**, sau đó **HKDF-Expand có nhãn đầy đủ và chiều dài riêng** cho từng khóa.

Nếu giao thức dùng một khóa làm đầu vào cho nhiều KDF khác nhau mà không có domain separation, có nguy cơ lặp đầu ra hoặc key confusion. Đừng tự thiết kế chuỗi `SHA-256(Z + "enc")` theo thói quen; dùng HKDF hoặc KDF chuẩn theo đặc tả.

## 4. HKDF-HMAC-SHA256: Extract và Expand

**HKDF** (HMAC-based Extract-and-Expand Key Derivation Function, RFC 5869) có hai giai đoạn:

### 4.1. Extract: chuẩn hóa bí mật đầu vào

~~~text
PRK = HKDF-Extract(salt, IKM)
    = HMAC-Hash(key = salt, message = IKM)
~~~

Với `HmacSHA256`, PRK dài **32 byte**. `salt` có thể công khai, không phải mật khẩu/pepper và không cần giữ bí mật. RFC 5869 cho phép salt vắng mặt bằng cách sử dụng chuỗi `HashLen` byte 0; tuy nhiên khi giao thức quy định salt, **hai bên phải sử dụng cùng byte**, không tùy tiện thay nó bằng chuỗi rỗng, timestamp hay digest khác.

Salt có thể là giá trị công khai theo handshake hoặc được dẫn xuất theo đặc tả từ các thành phần transcript; ví dụ phía dưới chọn một giá trị SHA-256 có nhãn từ transcript để hai bên tính giống nhau. **Salt không xác thực danh tính**, không thay kiểm chữ ký/certificate hoặc chống MITM.

Mục đích của Extract là đưa IKM có thể có cấu trúc vào PRK phù hợp cho bước Expand, không tăng entropy thực chất của một đầu vào yếu. Raw ECDH secret vẫn cần được xử lý theo quy tắc thuật toán, kiểm đầu vào public key và trường hợp shared secret bất thường theo giao thức/provider.

### 4.2. Expand: tạo khóa theo mục đích

~~~text
OKM = HKDF-Expand(PRK, info, L)

T(0) = empty
T(1) = HMAC(PRK, T(0) || info || 0x01)
T(2) = HMAC(PRK, T(1) || info || 0x02)
...
OKM  = first L bytes of T(1) || T(2) || ...
~~~

Trong đó:

- `PRK`: bí mật đầu vào của Expand, chỉ nằm phía các bên được phép.
- `info`: byte mô tả ngữ cảnh và mục đích xuất khóa, ví dụ `"c2s/aes-gcm"`; **không phải khóa bí mật**.
- `L`: độ dài đầu ra **tính bằng byte**, có giới hạn tối đa `255 × HashLen`; với SHA-256 là **8160 byte**. Một traffic key AES-128 cần 16 byte, HMAC-SHA256 thường dùng khóa được thiết kế với độ dài phù hợp như 32 byte.
- Các block có counter tăng từ **`0x01`**, không phải chuỗi ASCII `"1"` hoặc số nguyên 4 byte.

Nếu cùng `PRK`, `info` và `L`, HKDF Expand **trả cùng byte**. Đó là tính chất xác định để cả hai bên làm việc. Muốn khóa khác cho mục đích khác, phải dùng **info/nhãn khác nhau**; PRK không được đưa lên client logs hoặc lưu cùng ciphertext công khai.

### 4.3. Phân biệt HKDF với PBKDF2

| HKDF | PBKDF2/Argon2id/scrypt |
| --- | --- |
| Dùng khi đã có **key material bí mật đủ mạnh**, như X25519 secret hoặc random master key | Dùng cho **mật khẩu do con người tạo**, thường entropy thấp |
| Mục tiêu extract/expand và tách khóa theo ngữ cảnh | Mục tiêu làm chậm/đắt việc đoán password offline |
| `info` và nhãn mục đích giữ vai trò quan trọng | Salt, cost và cơ chế password hashing là trọng tâm |
| Không thể tự làm một password dễ đoán thành secret chống brute force | Được thiết kế để tăng chi phí tấn công đoán password |

Không dùng HKDF đơn lẻ làm password hashing mới, và không cần tự chạy PBKDF2 trên ECDH secret theo thói quen nếu giao thức đã quy định HKDF.

## 5. `info`, transcript và context binding

Một thiết kế trưởng thành cần thống nhất **không chỉ thuật toán HKDF, mà cả byte chính xác của `info` và salt**. Ví dụ một `info` có thể chứa:

| Thành phần | Tại sao quan trọng? |
| --- | --- |
| **Protocol ID/version** | Tránh vô tình dùng cùng key trong các protocol hoặc version khác nhau |
| **Algorithm suite** | Gắn khóa với lựa chọn X25519, HKDF-SHA256, AES-GCM/AEAD mode |
| **Handshake transcript hash** | Ràng buộc với thông điệp thương lượng, public keys, nonces, role và các trường đã định nghĩa |
| **Identity hoặc peer binding** | Phân biệt giao tiếp với đúng đối tác đã xác thực |
| **Hướng truyền/role** | `c2s` khác `s2c`, initiator khác responder |
| **Purpose label** | `enc`, `mac`, `wrap`, `confirm` tạo output riêng |
| **Tenant/channel/record context** | Chặn nhầm khóa giữa các miền sử dụng nếu nghiệp vụ cần |
| **Epoch/rekey counter** | Chuyển sang khóa mới có ngữ cảnh/chu kỳ rõ ràng |

**Đừng nối string một cách mơ hồ**, như:

~~~text
info = tenant + ":" + channel + ":" + purpose

("a:b", "c", "enc") và ("a", "b:c", "enc")
  → có thể tạo cùng chuỗi nếu chỉ nối bằng dấu ":"
~~~

Thay vào đó, quy định một binary encoding **không nhập nhằng**: mỗi trường có độ dài cố định hay tiền tố length, thứ tự trường, charset UTF-8, version, dạng ID chuẩn. Ví dụ Java dưới dùng `DataOutputStream.writeInt(length)` (big-endian 4 byte) rồi ghi đúng byte trường đó.

### 5.1. Handshake transcript là gì?

Một transcript là trình tự **chính xác các thông điệp/giá trị của phiên thỏa thuận khóa**, ví dụ version, suite, hai public keys, identities đã được xác thực, nonce và các lựa chọn thương lượng. Hai bên tính cùng một `transcriptHash` từ byte đã canonicalize, rồi gắn nó vào key schedule.

~~~text
transcriptBytes = encode(
    protocol/version,
    offered/chosen cipher suite,
    initiator role and public key,
    responder role and public key,
    relevant identities/nonces ...
)
transcriptHash = SHA-256(transcriptBytes)
info = encode("key-schedule/v1", suite, transcriptHash, purpose)
~~~

**Đừng nhầm:** gắn transcript hash vào HKDF **không tự xác thực transcript**. Nếu attacker kiểm soát quá trình trao đổi và hai bên không xác minh công khai/danh tính, họ vẫn có thể thực hiện hai phiên X25519 khác nhau rồi ngồi giữa. Transcript binding hỗ trợ chống key confusion và làm nền cho bước xác thực, nhưng **phải có cơ chế xác thực thật** (TLS đã cấu hình đúng, signature trên transcript, PSK authentication hoặc giao thức AKE đã được thẩm định).

### 5.2. Một handshake có thể cần key confirmation

Hai bên tính cùng shared secret không có nghĩa bên kia đã thực sự nhận đúng thông điệp và có cùng khóa. Giao thức có thể sử dụng **handshake Finished/confirmation MAC** từ khóa chuyên dụng, ràng buộc với transcript **đúng chiều**. Điều này phát hiện mismatch và xác nhận bên kia biết secret hiện tại, nhưng **nếu không có xác thực danh tính trước/đúng trong giao thức**, key confirmation **không ngăn MITM** giả lập hai phiên.

Không dùng traffic key AES-GCM để ký tùy tiện các thông điệp Finished; nếu cần confirmation key hãy **dẫn xuất nhãn `confirm` riêng**, hoặc dùng key schedule chuẩn của giao thức như TLS 1.3 thay vì tự ghép.

## 6. Tách khóa theo hướng và theo mục đích

Từ một PRK của phiên, tạo **đầu ra khác nhãn**:

~~~text
K_c2s_enc   = HKDF-Expand(PRK, info("c2s/aes-gcm"),     16)
K_s2c_enc   = HKDF-Expand(PRK, info("s2c/aes-gcm"),     16)
K_wrap      = HKDF-Expand(PRK, info("wrap/aes-kw"),     16)
K_hmac      = HKDF-Expand(PRK, info("auth/hmac-sha256"), 32)
K_confirm_c = HKDF-Expand(PRK, info("confirm/client"),   32)
K_confirm_s = HKDF-Expand(PRK, info("confirm/server"),   32)
~~~

Đây là **minh họa nhãn** cho một giao thức giả định. Trong thiết kế thực, hai bên phải theo một đặc tả duy nhất và **không mở thêm khóa/mục đích tùy hứng**. HKDF có thể tạo các giá trị khác nhau theo nhãn dưới giả định HMAC hoạt động như PRF; không có lời hứa toán học tuyệt đối “không bao giờ trùng”, nhưng xác suất trùng ngoài ý muốn khi dùng đúng kích thước là cực nhỏ.

| Key | Bên sử dụng | Primitive | Mục đích |
| --- | --- | --- | --- |
| `K_c2s_enc` | Client encrypt → Server decrypt | AES-GCM | Traffic client → server |
| `K_s2c_enc` | Server encrypt → Client decrypt | AES-GCM | Traffic server → client |
| `K_wrap` | Bên được phép bọc/mở DEK | AES Key Wrap / KEK | Bảo vệ khóa dữ liệu khác |
| `K_hmac` | Bên cần xác thực thông điệp ngoài AEAD theo giao thức | HMAC-SHA256 | Xác thực một loại message riêng, không mặc định dùng chung với GCM |
| `K_confirm_*` | Bên có trách nhiệm xác nhận handshake | MAC/protocol Finished | Kiểm tra handshake với nhãn/hướng riêng |

**Định danh hướng truyền:** Client và server phải **cùng hiểu** `c2s`/`s2c`, không phải mỗi bên tự gắn nhãn `"send"` rồi cho ra cùng khóa. Trong một kết nối peer-to-peer không có client/server cố định, đặt role `initiator`/`responder` hoặc quy tắc sắp xếp được xác thực. Nếu hai bên tự đảo role, key mismatch hoặc key reflection có thể xảy ra.

**Tách theo mục đích không đồng nghĩa tách theo nonce:** Dù có hai AES-GCM keys khác nhau, **mỗi key vẫn phải dùng nonce duy nhất cho từng lần mã hóa** dưới chính key đó. Nonce/replay sequencing là bài toán tiếp theo. Nếu dẫn xuất cả nonce base từ secret, phải dùng nhãn **`iv` khác `key`**, cộng sequence number theo giao thức đã được thẩm định.

### 6.1. Key lifecycle và rekey

Không nên dùng một traffic key cho số lượng message vô hạn. Hệ thống cần chính sách giới hạn theo thuật toán và mô hình nonce, ví dụ:

- Cấp nonce 96 bit duy nhất cho mỗi lần AES-GCM encrypt dưới một key; phối hợp counter giữa nhiều luồng/process hoặc dùng chiến lược nonce đã được thẩm định.
- Đếm/giới hạn số bản tin và lượng dữ liệu dưới cùng traffic key, xoay khóa theo chính sách an toàn.
- Nếu rekey từ secret trước, dùng **KDF epoch/sequence label** đã định nghĩa, thay đổi ngữ cảnh để không tái xuất cùng key; tránh rollback key.
- Quản lý retention/zeroization của secret cũ khi không còn cần để decrypt, đồng thời đáp ứng yêu cầu vận hành/khôi phục.
- Nếu dùng lại một master secret để bọc DEK lưu trữ, **vòng đời KEK khác traffic key**; không tùy tiện buộc lifetime của cả hai chỉ vì chúng cùng được dẫn xuất từ một PRK.

## 7. Shared secret có xác thực không? Rủi ro MITM

**X25519/ECDH thuần túy là thỏa thuận bí mật, không có chữ ký số.** Hai bên có thể tạo cùng một secret nếu public key đầu vào thật thuộc về đối phương, nhưng một attacker trên kênh trao đổi có thể tráo public keys:

~~~text
Alice ---- A_pub ----> Mallory ---- M1_pub ----> Bob
Alice <--- M2_pub ---- Mallory <--- B_pub ----- Bob

Alice ↔ Mallory: Z1 (bí mật của kết nối giả)
Mallory ↔ Bob:   Z2 (bí mật của kết nối giả)
Alice và Bob không trực tiếp có cùng shared secret.
Mallory có thể giải mã rồi mã hóa lại dữ liệu giữa hai phía.
~~~

Trong mô hình này, HKDF chạy đúng và key separation hoàn hảo **không ngăn attacker** nếu không xác minh danh tính công khai của bên kia. Cần một **authenticated key exchange (AKE)**: chữ ký trên transcript với khóa tin cậy, certificate xác minh đúng danh tính, PSK đã được phân phối an toàn hoặc một giao thức thỏa thuận khóa có xác thực được đánh giá độc lập. Đối với ứng dụng mạng, **TLS 1.3** đã triển khai key schedule và xác thực; thường nên dùng TLS thay vì tự xây handshake X25519.

Ngoài MITM, còn những kiểm tra quan trọng:

- Dữ liệu public key nhập từ mạng phải **được parse/validate đúng thuật toán**, không chấp nhận trộn curve/thuật toán, độ dài sai hoặc giá trị đặc biệt gây secret không an toàn theo chuẩn/provider.
- Với X25519, các triển khai/giao thức cần giải quyết trường hợp **low-order public input / all-zero shared secret** theo quy tắc thuật toán. Hãy dựa vào kiểm tra của provider/thư viện đáng tin và yêu cầu đặc tả, không coi chỉ cần public key parse được là đủ.
- Nếu private key dài hạn được dùng cho nhiều phiên, cân nhắc **forward secrecy**: khóa ephemeral riêng cho phiên thường là yếu tố quan trọng trong giao thức có xác thực.
- Xác thực identity không có nghĩa có quyền truy cập tài nguyên; vẫn cần **authorization**, tenant boundary, endpoint binding và logging an toàn.

Ví dụ chạy độc lập ở phần 9 chỉ mô phỏng hai bên trong cùng một tiến trình, **chưa chứng minh kết nối mạng chống MITM hoặc đã xác thực Alice/Bob**.

## 8. Bọc khóa: KEK, DEK và tách quyền hạn

Trong envelope encryption, hệ thống thường tạo một **DEK ngẫu nhiên** để mã hóa dữ liệu khối lượng lớn, rồi dùng **KEK** để bọc DEK:

~~~text
                 DEK (AES random)
                       |
             +---------+---------------------+
             |                               |
    AES-GCM Encrypt(data)            AES-KW Wrap(DEK, KEK)
             |                               |
    ciphertext + tag                wrapped DEK
             \                              /
              +---- lưu cùng metadata ------+
~~~

**DEK (Data Encryption Key)** và **KEK (Key Encryption Key)** khác vai trò, không nên là cùng byte. Khi key schedule có quyền xuất KEK, dùng nhãn riêng như `"wrap/aes-kw"`; không lấy `K_c2s_enc` dùng làm KEK.

**AES Key Wrap (AES-KW)** là thuật toán bọc vật liệu khóa, Java 17 có provider hỗ trợ transformation `"AESWrap"` trong JCE phổ biến. Nó không phải mode mã hóa bất kỳ metadata/payload dài tùy ý; với AES-KW theo RFC 3394, đầu vào khóa bọc phải tuân theo yêu cầu độ dài/khối của thuật toán. Các hệ thống cần bảo vệ **associated metadata** hoặc khóa với độ dài bất kỳ có thể cần AES-KWP hoặc AEAD wrapping theo đặc tả riêng.

- **Không xuất wrapped DEK rồi bỏ metadata định danh KEK.** Cần key ID/version/algorithm để giải bọc sau rotation.
- **Không giả định AESWrap tự ràng buộc tenant/record ID**. AES-KW có phép kiểm tính toàn vẹn của vật liệu được bọc, nhưng không nhận AAD như AES-GCM. Nếu metadata quyết định đối tượng/thuật toán, phải ràng buộc bằng thiết kế giao thức/metadata xác thực đúng.
- Với khóa lưu trữ lâu dài, thông thường **KEK lấy từ KMS/HSM hoặc một key hierarchy được quản lý**, không phải một traffic shared secret ngắn hạn bị hủy sau phiên mạng. Ví dụ dưới bọc DEK bằng khóa dẫn xuất từ phiên chỉ để minh họa **key-purpose separation**, không đề xuất quy trình lưu trữ production.
- Không nhầm **key wrapping** với gửi plaintext DEK qua kênh “đã mã hóa” nhưng không xác thực, hoặc với việc Base64-encode khóa.

## 9. Java 17+ hoàn chỉnh: X25519, HKDF, AES-GCM, AESWrap

Chương trình sau dùng JCA/JCE trong JDK 17+; không cần Maven. Nó thực hiện:

1. Kiểm chứng mã HKDF Extract/Expand theo **test vector số 1 của RFC 5869** (không in byte secret).
2. Tạo hai cặp khóa X25519, mỗi bên tính shared secret; in kết quả **so khớp** chứ không lộ secret.
3. Tạo hash của handshake transcript được encode có length-prefix; tạo một public salt từ transcript theo **quy tắc giả định của demo**.
4. Extract hai PRK bằng HMAC-SHA256; Expand các khóa `c2s/aes-gcm`, `s2c/aes-gcm`, `wrap/aes-kw` và `auth/hmac-sha256` theo **label/context độc lập**.
5. Dùng key c2s AES-GCM để mã hóa và phía kia giải mã; dùng sai key hướng/khác context sẽ lỗi authentication tag.
6. Bọc AES DEK bằng key `wrap` và bên còn lại mở bọc thành công.

**Lưu thành file `KeyScheduleDemo.java`:**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class KeyScheduleDemo {
    static byte[] utf8(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    // Framing không nhập nhằng: 4 byte độ dài (big-endian) + bytes.
    static byte[] frame(byte[]... fields) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        for (byte[] f : fields) {
            out.writeInt(f.length);
            out.write(f);
        }
        out.flush();
        return bytes.toByteArray();
    }

    static byte[] sha256(byte[] bytes) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(bytes);
    }

    static byte[] agree(PrivateKey me, PublicKey peer) throws Exception {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(me);
        agreement.doPhase(peer, true);
        return agreement.generateSecret();
    }

    // HKDF-Extract (RFC 5869), SHA-256 HashLen = 32.
    static byte[] extract(byte[] salt, byte[] ikm) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
                salt == null ? new byte[32] : salt, "HmacSHA256"));
        return mac.doFinal(ikm);
    }

    // HKDF-Expand với đúng các block T(i), counter từ 0x01.
    static byte[] expand(byte[] prk, byte[] info, int length)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(prk, "HmacSHA256"));
        int hashLen = mac.getMacLength();
        if (length < 1 || length > 255 * hashLen) {
            throw new IllegalArgumentException("Bad HKDF length");
        }
        byte[] okm = new byte[length];
        byte[] last = new byte[0];
        int offset = 0;
        for (int counter = 1; offset < length; counter++) {
            mac.update(last);
            mac.update(info);
            mac.update((byte) counter);
            byte[] block = mac.doFinal();
            int n = Math.min(block.length, length - offset);
            System.arraycopy(block, 0, okm, offset, n);
            offset += n;
            Arrays.fill(last, (byte) 0);
            last = block;
        }
        Arrays.fill(last, (byte) 0);
        return okm;
    }

    static byte[] info(String purpose, byte[] transcriptHash)
            throws Exception {
        return frame(
                utf8("lesson-key-schedule/v1"),
                utf8("X25519-HKDF-SHA256"),
                transcriptHash,
                utf8(purpose));
    }

    static byte[] seal(byte[] aesKey, byte[] nonce, byte[] aad, byte[] plain)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(aesKey, "AES"),
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plain);
    }

    static byte[] open(byte[] aesKey, byte[] nonce, byte[] aad,
            byte[] cipherAndTag) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(aesKey, "AES"),
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(cipherAndTag);
    }

    static boolean rejects(byte[] aesKey, byte[] nonce, byte[] aad,
            byte[] encrypted) throws Exception {
        try {
            open(aesKey, nonce, aad, encrypted);
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        // Vector RFC 5869 TC1 (IKM=0x0b * 22), kiểm tra HKDF.
        byte[] ikm = new byte[22];
        Arrays.fill(ikm, (byte) 0x0b);
        byte[] testSalt = HexFormat.of().parseHex(
                "000102030405060708090a0b0c");
        byte[] testInfo = HexFormat.of().parseHex(
                "f0f1f2f3f4f5f6f7f8f9");
        byte[] known = HexFormat.of().parseHex(
                "3cb25f25faacd57a90434f64d0362f2a"
                + "2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
                + "34007208d5b887185865");
        System.out.println("HKDF RFC5869       = "
                + MessageDigest.isEqual(known,
                        expand(extract(testSalt, ikm), testInfo, 42)));

        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();
        byte[] aliceSecret = agree(alice.getPrivate(), bob.getPublic());
        byte[] bobSecret = agree(bob.getPrivate(), alice.getPublic());
        System.out.println("Shared match       = "
                + MessageDigest.isEqual(aliceSecret, bobSecret));
        System.out.println("Shared bytes       = " + aliceSecret.length);

        // Transcript giả định: hai public key và role được cố định thứ tự.
        byte[] transcriptHash = sha256(frame(
                utf8("handshake-demo-v1"),
                utf8("initiator=Alice"),
                alice.getPublic().getEncoded(),
                utf8("responder=Bob"),
                bob.getPublic().getEncoded()));
        byte[] salt = sha256(frame(utf8("extract-salt/v1"), transcriptHash));
        byte[] aPrk = extract(salt, aliceSecret);
        byte[] bPrk = extract(salt, bobSecret);

        byte[] aC2s = expand(aPrk,
                info("c2s/aes-gcm", transcriptHash), 16);
        byte[] bC2s = expand(bPrk,
                info("c2s/aes-gcm", transcriptHash), 16);
        byte[] s2c = expand(aPrk,
                info("s2c/aes-gcm", transcriptHash), 16);
        byte[] aWrap = expand(aPrk,
                info("wrap/aes-kw", transcriptHash), 16);
        byte[] bWrap = expand(bPrk,
                info("wrap/aes-kw", transcriptHash), 16);
        byte[] macKey = expand(aPrk,
                info("auth/hmac-sha256", transcriptHash), 32);

        System.out.println("C2S key bytes      = " + aC2s.length);
        System.out.println("Wrap key bytes     = " + aWrap.length);
        System.out.println("MAC key bytes      = " + macKey.length);
        System.out.println("Same role keys     = "
                + MessageDigest.isEqual(aC2s, bC2s));
        System.out.println("C2S != S2C         = "
                + !MessageDigest.isEqual(aC2s, s2c));
        System.out.println("C2S != wrap        = "
                + !MessageDigest.isEqual(aC2s, aWrap));

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] sealed = seal(aC2s, nonce, transcriptHash,
                utf8("hello key schedule"));
        System.out.println("Decrypt C2S        = "
                + new String(open(bC2s, nonce, transcriptHash, sealed),
                StandardCharsets.UTF_8));
        System.out.println("Wrong role rejected= "
                + rejects(s2c, nonce, transcriptHash, sealed));
        byte[] wrongContext = sha256(utf8("different transcript"));
        byte[] wrongKey = expand(bPrk,
                info("c2s/aes-gcm", wrongContext), 16);
        System.out.println("Wrong ctx rejected = "
                + rejects(wrongKey, nonce, transcriptHash, sealed));

        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(128);
        SecretKey dataKey = keyGenerator.generateKey();
        Cipher wrapper = Cipher.getInstance("AESWrap");
        wrapper.init(Cipher.WRAP_MODE, new SecretKeySpec(aWrap, "AES"));
        byte[] wrapped = wrapper.wrap(dataKey);
        Cipher unwrapper = Cipher.getInstance("AESWrap");
        unwrapper.init(Cipher.UNWRAP_MODE,
                new SecretKeySpec(bWrap, "AES"));
        Key restored = unwrapper.unwrap(
                wrapped, "AES", Cipher.SECRET_KEY);
        System.out.println("Wrapped DEK matches= "
                + MessageDigest.isEqual(
                        dataKey.getEncoded(), restored.getEncoded()));

        // Giảm vòng đời secret do ứng dụng giữ; provider có thể giữ copy.
        Arrays.fill(aliceSecret, (byte) 0);
        Arrays.fill(bobSecret, (byte) 0);
        Arrays.fill(aPrk, (byte) 0);
        Arrays.fill(bPrk, (byte) 0);
        Arrays.fill(aC2s, (byte) 0);
        Arrays.fill(bC2s, (byte) 0);
        Arrays.fill(s2c, (byte) 0);
        Arrays.fill(aWrap, (byte) 0);
        Arrays.fill(bWrap, (byte) 0);
        Arrays.fill(macKey, (byte) 0);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac KeyScheduleDemo.java
java KeyScheduleDemo
~~~

Output kỳ vọng **ổn định dù cặp khóa, nonce và DEK được sinh ngẫu nhiên**:

~~~text
HKDF RFC5869       = true
Shared match       = true
Shared bytes       = 32
C2S key bytes      = 16
Wrap key bytes     = 16
MAC key bytes      = 32
Same role keys     = true
C2S != S2C         = true
C2S != wrap        = true
Decrypt C2S        = hello key schedule
Wrong role rejected= true
Wrong ctx rejected = true
Wrapped DEK matches= true
~~~

### 9.1. Giải thích theo thứ tự

1. **`HKDF RFC5869 = true`:** phép thử đối chiếu đầu ra 42 byte với vector chuẩn, giúp phát hiện sai công thức, byte counter hoặc copy block. Đừng tự triển khai HKDF trong production nếu đã có thư viện/provider chuẩn phù hợp.
2. **`Shared match = true`:** `KeyAgreement("X25519")` cho hai bên cùng byte khi dùng đúng cặp private/public. `Shared bytes = 32` là độ dài X25519 output; không phải tuyên bố đây đã là traffic key.
3. **`transcriptHash`:** encode các trường có độ dài, thứ tự role và hai public keys rồi SHA-256. Demo đặt `salt` từ hash này theo một quy ước riêng để hai bên cùng làm được. Giao thức thực tế phải có **thông điệp và quy tắc salt/transcript chính xác được đặc tả**, không sao chép demo như một handshake tiêu chuẩn.
4. **`aPrk/bPrk`:** hai bên Extract bằng cùng IKM/salt cho cùng PRK; mỗi `expand` có cùng PRK nhưng **info purpose khác** sẽ cho output khác.
5. **`Same role keys = true`:** Alice gửi với `aC2s`, Bob nhận với `bC2s`. Bob không dùng nhãn `"s2c"` khi nhận c2s. `C2S != S2C` chứng minh labels khác nhau trên chính lượt demo; không coi một ví dụ trùng/khác là chứng minh mật mã về mọi input.
6. **`Wrong role rejected` / `Wrong ctx rejected`:** AES-GCM từ chối bản mã khi dùng khóa khác; `Wrong ctx` được tạo bằng Expand với transcript khác. Điều này minh họa key binding, **không chứng minh đã chống MITM**.
7. **`Wrapped DEK matches`:** khóa `wrap` do hai phía dẫn xuất được dùng với `AESWrap`. Phép wrap bảo vệ bản thân DEK khi gửi trong phạm vi khóa KEK này; không thay chính sách KMS, phân quyền hoặc bảo vệ metadata.

Các mảng byte được `Arrays.fill` sau khi dùng để giảm thời gian tồn tại secret ở bộ nhớ do ứng dụng kiểm soát. Điều này không bảo đảm xóa các bản copy bên trong provider/JVM hoặc mọi secret còn tồn tại trong object `PrivateKey`/`SecretKey`. Demo không có giao tiếp mạng, certificate, key confirmation, chống replay hoặc persistence; đó là các lớp cần bổ sung bằng **giao thức chuẩn**.

## 10. KDF và bản tin thực tế: chọn đúng ngữ cảnh AAD, IV, role

Tách khóa mục đích mới là một phần. Nếu lưu/truyền encrypted data, bên nhận còn cần biết đúng **nonce, ciphertext, authentication tag, suite, key epoch và sequence**:

~~~text
handshake metadata:
    protocol version, suite, roles, public keys, identity/auth evidence
    -> transcript hash -> HKDF context

application record:
    version | epoch | sequence | nonce | ciphertext || tag
    AAD = canonical(version, epoch, direction, sequence, type, ...)
    key = K_direction_for_epoch
~~~

**Key derivation context và AEAD AAD là hai lớp khác nhau.** KDF ràng buộc key với phiên/vai trò; AAD ràng buộc **từng bản tin** với metadata không mã hóa. Có transcript binding trong KDF vẫn không tự bảo vệ mọi field header ứng dụng, và AAD đúng vẫn không sửa được việc cấp nonce trùng.

Một record đầy đủ có thể cần:

- **Key epoch/generation**: lựa chọn đúng khóa sau rekey; chống dùng epoch cũ trái phép theo policy.
- **Sequence / message ID**: dùng để xác thực thứ tự/chống replay; tag hợp lệ của message cũ vẫn hợp lệ nếu protocol không nhớ đã thấy.
- **Nonce**: 96 bit theo GCM phổ biến; duy nhất dưới cùng traffic key.
- **Ciphertext + tag**: không chấp nhận plaintext nếu `AEADBadTagException`/verification failure.
- **Header/AAD**: ràng buộc với đúng channel, tenant, type hoặc direction cần bảo vệ khỏi thay đổi.
- **Algorithm/key ID**: sử dụng mapping và chính sách xác thực chống downgrade, tránh attacker điều khiển chọn key/suite tùy tiện.

**Không nối dữ liệu không tin cậy vào HKDF info rồi kỳ vọng bảo mật tự xuất hiện**: cần xác thực/kiểm ngữ cảnh quan trọng trước khi coi nó là claim tin cậy, hoặc ràng buộc nó qua protocol transcript đã xác thực.

## 11. Tình huống thiết kế thường gặp

### 11.1. Ứng dụng chat hai chiều

Một phiên client/server dùng X25519 để tạo Z. Nếu chọn cùng `K_enc` cho cả gửi và nhận, client và server có thể dùng lại cùng nonce counter bắt đầu ở 0 rồi vô tình tái sử dụng **cùng (key, nonce)** trong AES-GCM. Chia `K_c2s_enc` và `K_s2c_enc` bằng labels khác làm giảm nguy cơ chồng miền sử dụng, nhưng **mỗi hướng vẫn phải bảo đảm nonce unique**. Dùng protocol sequence/AAD và chống replay.

### 11.2. Cùng thư viện dùng cho hai sản phẩm

Sản phẩm A có `"sync/v1"` và B có `"backup/v1"`, cùng nguồn secret trong key hierarchy. Nếu cả hai gọi `HKDF-Expand(PRK, "enc", 16)` thì có thể lấy cùng key. Hãy đưa **protocol/product ID, version, usage label** vào info khác nhau, tránh cross-protocol key reuse. Nếu thiết kế yêu cầu tổ chức tenant hoặc device, đưa những ID có ý nghĩa và đã xác minh vào context.

### 11.3. Bọc DEK để lưu hồ sơ

Hệ thống lưu ciphertext hồ sơ bằng DEK, wrapped DEK bằng KEK trong KMS. Khi rotation, cần metadata `keyId` để biết đúng KEK; nếu rewrap DEK, có thể không cần decrypt toàn bộ dữ liệu. **KEK storage dài hạn không nên mặc nhiên được dẫn xuất từ ephemeral X25519 session Z**, vì sau phiên KEK đó biến mất hoặc không có cơ chế khôi phục. Thiết kế key hierarchy, quyền unwrap, auditing và backup riêng cho lưu trữ.

### 11.4. Xác thực handshake

Alice/Bob cùng tính shared secret và PRK, sau đó tạo confirmation MAC trên transcript bằng `K_confirm_client`/`K_confirm_server`. Nó giúp phát hiện một bên thiếu secret hoặc transcript khác nhưng **không chứng minh danh tính** nếu public keys không được xác thực: MITM có thể có confirmation MAC hợp lệ ở từng phiên do chính họ tham gia. Cần thiết kế AKE có identity binding thật.

### 11.5. Chuyển thuật toán và rekey

Hệ thống chuyển từ AES-128-GCM sang AES-256-GCM hoặc một suite khác, không chỉ đổi độ dài từ 16 lên 32 byte mà quên **suite ID trong transcript/info**. Thỏa thuận thuật toán phải chống downgrade, hai bên derive đúng key length, key ID và được xác thực. Một server có nhiều bản cũ/mới phải có version rõ ràng và chính sách ngừng chấp nhận suite yếu.

## 12. Những lỗi bảo mật hay gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng trực tiếp 16/32 byte đầu của ECDH secret làm AES key | Không có context/purpose/role separation; key schedule tự phát | HKDF Extract/Expand theo giao thức, nhãn đầy đủ |
| Lấy SHA-256(Z) rồi dùng cho mọi mục đích | Không tách encryption, MAC, wrap | HKDF Expand với `info` riêng mỗi purpose |
| Client `"send"`, Server cũng `"send"` nhưng nhầm hướng | Hai bên derive sai key hoặc cùng key ở hai hướng | Định nghĩa `c2s/s2c` hoặc initiator/responder bất biến |
| Cùng HKDF `info` cho MAC và AES | Tái sử dụng khóa chéo primitive | Domain separation bằng label/thuật toán/role |
| `info = a + ":" + b` không đóng khung trường | Hai tuple ngữ cảnh có thể cùng byte string | Length prefix/canonical binary encoding |
| Không ràng buộc phiên bản và suite | Khóa giữa version/protocol có thể trùng hoặc bị nhầm | Thêm version, suite, transcript hash vào info |
| Cho rằng transcript hash là chữ ký số | Không ngăn MITM tráo public key | AKE có certificate/signature/PSK auth |
| Coi HKDF salt là bí mật bắt buộc | Khó đồng bộ giữa hai bên, sai giả định | Salt thường công khai, phải đúng quy tắc giao thức |
| Coi HKDF là password KDF | Bẻ password yếu rất nhanh | Argon2id/scrypt/PBKDF2 cho password |
| Dùng một AES-GCM key, nonce 0 cho cả hai phía | Nonce reuse gây hỏng bảo mật GCM | Khóa tách hướng + nonce duy nhất mỗi key |
| Dẫn xuất KEK từ phiên ngắn hạn rồi lưu DEK lâu dài | Sau restart/phiên kết thúc không còn KEK để unwrap | Dùng KMS/HSM/key hierarchy lưu trữ |
| Tưởng AES-KW có AAD như AES-GCM | Không có binding metadata tự động | Xác thực context/metadata bằng protocol riêng |
| Lưu log `generateSecret()` hoặc PRK | Lộ toàn bộ traffic/wrap keys liên quan | Secret không in/log; giảm tồn tại trong RAM |
| Không kiểm public key hoặc lỗi X25519 all-zero | Có thể nhận input bất thường/không an toàn | Parse/validate đúng algorithm và provider/standard |
| Không giới hạn HKDF `L` | Sai hoặc vượt HKDF output bound | Kiểm `1 ≤ L ≤ 255×HashLen` trong demo |
| Chỉ kiểm encrypt/decrypt đúng, bỏ negative tests | Không phát hiện sai context, role, length và tamper | Test expected failures, key separation và interoperability |
| Dùng code demo như giao thức mạng production | Thiếu danh tính, replay, metadata, rotation | Dùng TLS 1.3 hoặc AKE/record protocol chuẩn |

## 13. Kiểm thử key schedule và cross-system interoperability

**Kiểm tra byte không chỉ so người dùng thấy output giống nhau.** Hai triển khai Java/Python/Go có thể cùng gọi X25519/HKDF nhưng khác cách đóng khung public keys hoặc labels, dẫn tới khóa khác.

Bộ test nên có:

1. **RFC 5869 HKDF known-answer vectors:** input IKM/salt/info/length cố định và expected PRK/OKM. Chương trình minh họa chạy vector số 1.
2. **Role symmetry:** Alice c2s encryption key phải bằng Bob c2s decryption key; riêng c2s khác s2c và wrap.
3. **Purpose separation:** thay nhãn `"enc"` thành `"wrap"` phải tạo key khác; dùng nhãn cũ để giải bọc sai phải thất bại.
4. **Context separation:** thay transcript, suite version, tenant/channel hoặc identity được ràng buộc phải tạo khóa khác.
5. **Transcript canonicalization:** cùng các field nhưng serialization/byte order khác có thể ra khác hash; phải định nghĩa và test chính xác thứ tự/length.
6. **Negative AEAD tests:** dùng sai key, nonce, AAD, tag hoặc sửa ciphertext phải từ chối; không phát plaintext chưa xác thực.
7. **Public key validation:** peer key malformed, wrong curve, wrong encoding, low-order issues, error mapping an toàn.
8. **Replay/sequence:** gói hợp lệ cũ không được coi là message mới nếu giao thức đòi chống replay; state phải kiểm.
9. **Rekey/rotation:** epoch mới derive key khác, key ID chọn đúng và không chấp nhận rollback trái chính sách.
10. **Wrap/unwrap:** DEK wrap bằng KEK đúng mở được; KEK sai hoặc wrapped bytes sửa phải fail theo primitive/provider.
11. **Cross-provider:** Java JCE provider, thư viện C/Go/Python phải thống nhất X25519 encoding, HKDF info, nonce format, AES-KW variant và test vectors; không chỉ test ASCII labels đơn giản.

**Lưu ý khi test:** Mẫu known-answer có thể chứa byte giả cố định công khai, nhưng **không bao giờ log secret production** để đối chiếu. Test `MessageDigest.isEqual` trên byte để kiểm kết quả; giao thức xác thực sản xuất nên dùng verification API của primitive và phân tích thời gian/timing tùy mô hình đe dọa.

## 14. Bài tập (có đáp án)

**Bài 1.** Hai bên X25519 có cùng shared secret 32 byte. Có nên dùng toàn bộ secret làm khóa AES-256 rồi dùng lại làm HMAC key?

**Đáp án:** Không. Cần key schedule HKDF Extract/Expand, tách nhãn và chiều dài riêng cho AES và HMAC. Cùng kích thước không bảo đảm đúng mục đích hay ngữ cảnh.

**Bài 2.** `K_c2s = HKDF-Expand(PRK, "c2s", 16)` và `K_s2c = HKDF-Expand(PRK, "s2c", 16)` khác nhau để làm gì?

**Đáp án:** Để **tách hai hướng sử dụng**, tránh vô tình dùng cùng key cho traffic hai chiều và nhầm quyền/nonce. Vẫn cần bảo đảm nonce unique cho từng key.

**Bài 3.** `salt` HKDF và `info` có nhất thiết phải bí mật không?

**Đáp án:** Thường **không**. Chúng có thể công khai nhưng phải nhất quán/được ràng buộc vào giao thức, trong khi IKM, PRK và OKM phải giữ bí mật. Salt không thay xác thực identity.

**Bài 4.** Thay `info` từ `"wrap"` sang `"enc"` có đảm bảo có đúng cùng key không?

**Đáp án:** Không. HKDF Expand với nhãn khác được thiết kế để cho **key độc lập về mặt tính toán** dưới giả định PRF. Hai bên phải dùng cùng nhãn cho cùng mục đích; nhầm nhãn sẽ khiến decrypt/unwrap thất bại.

**Bài 5.** Nếu Alice/Bob dùng transcript hash trong HKDF info nhưng không ký hoặc xác minh public key, họ có tránh MITM chưa?

**Đáp án:** Chưa. Mallory có thể thực hiện hai phiên riêng với Alice và Bob, mỗi phiên có transcript/key hợp lệ. Phải có cơ chế xác thực identity/public key theo AKE/giao thức chuẩn.

**Bài 6.** Hai ứng dụng cùng dùng `info = "enc"` với cùng PRK. Lỗi gì có thể xảy ra?

**Đáp án:** **Cross-protocol key reuse/confusion**. Cần thêm protocol ID/version, cipher suite, purpose, hướng và ngữ cảnh phân biệt.

**Bài 7.** Trong Java, `new GCMParameterSpec(128, nonce)` dùng tag 128 bit. Có liên quan gì đến việc key AES-128 là 16 byte?

**Đáp án:** Đây là **hai thông số khác nhau**: AES-128 dùng key 128 bit (16 byte); tag GCM 128 bit là độ dài thẻ xác thực. Ngoài ra nonce 96 bit (12 byte) thường được dùng. Không lấy nhầm tag size làm key size.

**Bài 8.** DEK được bọc bằng KEK sinh từ shared secret X25519 ephemeral, rồi lưu 5 năm. Vấn đề gì?

**Đáp án:** KEK biến mất cùng phiên nếu không được duy trì/khôi phục; không thích hợp với lưu trữ dài hạn nếu chưa có thiết kế key hierarchy. Nên dùng KEK quản lý qua KMS/HSM hoặc hệ thống lưu khóa bền vững có rotation/backup/authorization.

**Bài 9.** Cặp key AES-GCM c2s/s2c đã tách riêng; hai process gửi cùng hướng lại dùng nonce counter khởi tạo từ 0 dưới cùng key. Có an toàn không?

**Đáp án:** Không. Nonce phải duy nhất **toàn miền các lần mã hóa dưới một key**, không chỉ theo từng process. Cần phân phối counter/partition hoặc chiến lược nonce được đánh giá.

**Bài 10.** Một record AES-KW có wrapped key hợp lệ, nhưng metadata tenant/record ID bị thay. AES-KW có tự kiểm chính xác tenant không?

**Đáp án:** Không. AES-KW kiểm vật liệu khóa theo thiết kế wrap, **không có AAD tenant/record ID** như AES-GCM. Cần binding metadata vào hệ thống xác thực/phân quyền hoặc định dạng wrapping có AAD theo đặc tả.

## 15. Checklist thiết kế và triển khai

- [ ] Public-key agreement dùng X25519/ECDH theo thư viện chuẩn; **peer key/identity được xác thực** bởi AKE/TLS/certificate/PSK policy.
- [ ] Không dùng raw shared secret trực tiếp làm AES/MAC/KEK; xử lý điều kiện public-key malformed/all-zero theo chuẩn/provider.
- [ ] HKDF-Extract đúng HMAC hash/salt/IKM; HKDF-Expand đúng byte info/counter/length; có known-answer tests.
- [ ] Dữ liệu `info` được đóng khung không nhập nhằng, có **protocol/version/suite/transcript/role/purpose** và những miền sử dụng cần ràng buộc.
- [ ] Các key cho `c2s`, `s2c`, MAC, confirmation và wrap có nhãn khác nhau, độ dài đúng primitive.
- [ ] Với AES-GCM, **nonce duy nhất** cho mỗi lần encrypt dưới từng key, tag được xác minh trước khi dùng plaintext, AAD gắn metadata message khi cần.
- [ ] Có chống replay, sequence/epoch, giới hạn sử dụng key và rekey/rotation theo giao thức.
- [ ] DEK để mã hóa dữ liệu, KEK để bọc DEK; KEK dài hạn dùng key management phù hợp, không buộc vào ephemeral session.
- [ ] Không log hoặc lưu công khai private key, shared secret, PRK/OKM; giảm vòng đời secret và quản lý quyền giải bọc.
- [ ] Chạy interoperability vectors trên các triển khai, kiểm cả negative cases và metadata/algorithm negotiation.
- [ ] Nếu ứng dụng cần kết nối an toàn thực tế, ưu tiên **giao thức chuẩn đã được thẩm định** (điển hình TLS 1.3) thay vì chắp vá key agreement, KDF và AEAD thành một handshake riêng.

## 16. Tóm tắt

**Shared secret chỉ là đầu vào cho key schedule**, không phải khóa chung dùng cho mọi việc. Với X25519, hai bên có thể có cùng byte bí mật; **HKDF-Extract** tạo PRK, **HKDF-Expand** với `info` có định dạng chuẩn và nhãn mục đích sinh ra các key **đúng thuật toán, chiều truyền và phạm vi sử dụng**. Ngữ cảnh handshake/transcript phải được ràng buộc, nhưng vẫn cần **xác thực danh tính và thỏa thuận thuật toán** theo giao thức. Tách `c2s/s2c`, AES-GCM, HMAC và KEK giúp giảm key confusion; kết hợp với nonce, AAD, chống replay và vòng đời khóa đúng mới tạo thành một hệ thống mã hóa an toàn.

Tài liệu tham khảo định nghĩa thuật toán: **RFC 5869 (HKDF)** https://www.rfc-editor.org/rfc/rfc5869 ; **RFC 7748 (X25519/X448)** https://www.rfc-editor.org/rfc/rfc7748 ; **RFC 3394 (AES Key Wrap)** https://www.rfc-editor.org/rfc/rfc3394 . Các RFC này định nghĩa primitive, không tự thay thế việc thiết kế/kiểm định một giao thức có xác thực đầu-cuối.
