# Key derivation function (KDF): dẫn xuất khóa an toàn từ bí mật đầu vào

## 1. KDF giải quyết vấn đề nào?

Một hệ thống Java có thể cần đồng thời:

- Khóa AES-256-GCM để mã hóa nội dung hóa đơn.
- Khóa HMAC-SHA256 để xác thực một loại thông điệp.
- Khóa phiên cho hai chiều truyền trong giao thức mạng.
- Một khóa được hình thành từ passphrase khi người dùng muốn mã hóa tệp cục bộ.

**Không nên lấy một chuỗi bí mật rồi dùng nguyên xi cho mọi mục đích.** Các đầu vào có chất lượng khác nhau và các thuật toán có yêu cầu khác nhau. Một mật khẩu do người dùng đặt thường có entropy thấp; ngược lại, một shared secret từ thỏa thuận khóa an toàn hoặc một root key được tạo bằng CSPRNG có thể là vật liệu mật mã mạnh.

**Key Derivation Function (KDF), hay hàm dẫn xuất khóa**, là cơ chế tạo vật liệu khóa mật mã từ bí mật đầu vào và các tham số được quy định. KDF giúp **chuẩn hóa cách sinh khóa, tách khóa theo mục đích, dẫn xuất khóa phiên và quản lý hệ phân cấp khóa**. Một số KDF được thiết kế riêng để làm **tấn công thử mật khẩu tốn tài nguyên**.

~~~text
Vật liệu đầu vào có entropy cao                 Mật khẩu người dùng
(root secret, ECDH shared secret)                (thường dễ đoán hơn)
            |                                             |
            v                                             v
   HKDF / KDF theo giao thức                    Password-based KDF
            |                                   Argon2id, scrypt, PBKDF2
            v                                             |
    Khóa mã hóa / MAC / phiên                  Password verifier hoặc
    với nhãn mục đích riêng                    khóa mã hóa từ passphrase
~~~

Điều quan trọng không phải chỉ là “gọi KDF để nhận 32 byte”. Phải biết **nguồn entropy**, **thuật toán**, **salt**, **nhãn ngữ cảnh**, **tham số chi phí**, **quyền truy cập bí mật gốc**, **vòng đời rotation** và **mục đích của khóa đầu ra**.

### Mục tiêu bài học

Sau khi học, bạn có thể:

1. Giải thích KDF, key material, derived key và khác biệt giữa KDF với hash thông thường, mã hóa hoặc key wrapping.
2. Phân biệt **HKDF** cho vật liệu mật mã mạnh với **Argon2id, scrypt, PBKDF2** cho mật khẩu.
3. Hiểu **salt**, **info/context**, **pepper**, **iteration count**, **memory cost**, **parallelism** và **output length**.
4. Áp dụng **domain separation** để không dùng cùng một khóa cho các mục đích khác nhau.
5. Thực hiện ví dụ **PBKDF2-HMAC-SHA256** và **HKDF-SHA256** với Java 17, biết phần nào không phù hợp cho production.
6. Thiết kế vòng đời khóa dẫn xuất gắn với **DEK/KEK, KMS/HSM, IAM, envelope encryption, rotation, thu hồi và kiểm toán**.
7. Phân tích lỗi phổ biến: SHA-256(password), salt cố định, lưu root secret cạnh ciphertext, lộ pepper, migration sai phiên bản và nhầm KDF với xác thực danh tính.

## 2. KDF là gì và không phải là gì?

Một mô hình khái niệm:

~~~text
DerivedKey = KDF(
    secretInput,
    salt,
    purposeOrContext,
    outputLength,
    algorithmParameters
)
~~~

Đây không phải chữ ký API áp dụng nguyên xi cho mọi thuật toán. Một số KDF có **salt** và **info** riêng; một số khác có **memory cost**, **iterations**, **parallelism** hoặc cấu trúc theo giao thức. Khóa đầu ra thường có tính **xác định**: cùng toàn bộ đầu vào và cùng cấu hình sẽ tạo cùng byte đầu ra.

### 2.1. Phân biệt KDF với hash, mã hóa và key wrapping

| Cơ chế | Mục tiêu | Đầu vào chính | Khác biệt |
| --- | --- | --- | --- |
| **Cryptographic hash** | Tạo digest cố định để đối chiếu/integrity | Message bytes | Không có secret bắt buộc; SHA-256(message) không tự xác thực nguồn |
| **KDF** | Sinh vật liệu khóa từ đầu vào đã xác định | Bí mật đầu vào + tham số | Có mô hình entropy, key separation và định dạng đầu ra phù hợp |
| **Password-based KDF** | Dẫn xuất kết quả từ mật khẩu, tăng chi phí đoán mật khẩu | Password + salt + cost | Phải được điều chỉnh theo CPU/bộ nhớ và khả năng chống tấn công |
| **HMAC** | Tạo MAC xác thực thông điệp hoặc làm PRF | Secret key + message | HKDF/PBKDF2 có thể **sử dụng HMAC bên trong**, nhưng mục đích tổng thể khác |
| **Symmetric encryption** | Mã hóa dữ liệu và khi dùng AEAD thì xác thực | DEK + plaintext + nonce/AAD | Khóa đã có là đầu vào, không phải khóa được dẫn xuất |
| **Key wrapping** | Bảo vệ khóa đã có dưới KEK | KEK + DEK | Wrap/unwrap và derive là hai thao tác khác nhau |
| **Key agreement** | Tạo bí mật chung giữa các phía | Private key bên mình + public key đối tác | ECDH thường tạo input cho KDF; KDF không xác thực peer |

Ví dụ, **DEK** là vai trò khóa dùng mã hóa dữ liệu; **derived key** mô tả cách khóa được tạo. Một derived key có thể là **DEK**, **KEK**, **MAC key** hoặc **traffic key**. Không phải mọi DEK đều được dẫn xuất: nhiều hệ thống dùng **DEK ngẫu nhiên** do KMS tạo rồi bọc bằng KEK.

### 2.2. KDF không làm bí mật yếu tự trở nên mạnh

Nếu mật khẩu chỉ có khoảng 20 bit entropy thực tế, việc băm hoặc dẫn xuất thành 256 bit **không tạo ra 256 bit độ khó để đoán mật khẩu**. Kẻ tấn công biết salt, thuật toán và dữ liệu kiểm tra có thể tiếp tục thử những mật khẩu khả dĩ.

Một password-based KDF làm mỗi lần thử **tốn chi phí hơn**, chứ không sinh thêm entropy bí mật cho mật khẩu do người dùng đặt. Một root secret 256 bit được tạo ngẫu nhiên đúng cách khác căn bản với một mật khẩu dễ đoán, cho dù cả hai cuối cùng đều được biểu diễn thành mảng byte dài 32.

**Kết luận thiết kế:** chọn loại KDF **theo tính chất đầu vào và use case**, không chọn chỉ theo độ dài khóa đầu ra.

## 3. Thành phần đầu vào và ý nghĩa bảo mật

### 3.1. Secret input: entropy là nền tảng

Các nguồn thường gặp:

- **Root/master secret:** vật liệu bí mật ngẫu nhiên mạnh được quản lý như khóa cấp cao.
- **IKM (Input Keying Material):** thuật ngữ dùng trong HKDF; có thể là shared secret của ECDH, đầu vào ngẫu nhiên hoặc key material phù hợp.
- **Password/passphrase:** bí mật do con người tạo, dễ bị thử đoán hơn; phải xử lý bằng password-based KDF khi thích hợp.
- **Pre-shared key (PSK):** khóa bí mật phân phối trước giữa các bên, cần có nguồn entropy, cấp quyền và vòng đời rõ.
- **Kết quả KDF trước đó:** vật liệu khóa có thể được sử dụng làm đầu vào cho một tầng dẫn xuất tiếp theo **nếu giao thức và giả định bảo mật cho phép**.

**Không lấy timestamp, UUID đoán được, tenant ID hay request ID làm secret input.** Chúng có thể là **context**, **identifier** hoặc một phần metadata, nhưng thông thường không phải nguồn bí mật đủ mạnh.

### 3.2. Salt

**Salt** là giá trị đưa vào phép dẫn xuất theo quy định thuật toán. Salt **thường không phải bí mật** và có thể lưu cùng kết quả.

- Với **password-based KDF**, salt riêng và đủ ngẫu nhiên giúp những tài khoản có cùng mật khẩu **không mặc định có cùng giá trị lưu trữ**, đồng thời làm khó việc dùng lại bảng tính toán sẵn trên toàn bộ tập người dùng.
- Với **HKDF**, salt tham gia bước Extract và có thể hỗ trợ tách các lần dẫn xuất theo mô hình; không dùng salt để bù đắp input quá yếu.
- Salt cần được **tạo, lưu và tái sử dụng đúng** khi xác minh lại hoặc giải mã dữ liệu cũ.
- Salt khác **nonce/IV của AES-GCM**: chúng có vai trò và quy tắc dùng lại khác nhau.
- Salt không phải **pepper**: pepper thường là một bí mật bổ sung do hệ thống bảo vệ riêng.

Ví dụ với tài khoản người dùng:

~~~text
User A password = "same-password" + salt_A ──password KDF──> verifier_A
User B password = "same-password" + salt_B ──password KDF──> verifier_B

salt_A ≠ salt_B  =>  verifier_A và verifier_B thông thường khác nhau
~~~

**Salt cố định toàn ứng dụng** không mang lại lợi ích phân tách từng tài khoản của salt riêng. Đừng dùng địa chỉ email hoặc tên người dùng làm “salt” thay cho giá trị ngẫu nhiên khi thiết kế yêu cầu salt ngẫu nhiên.

### 3.3. Context, info, label và domain separation

**Context/info** ràng buộc khóa dẫn xuất với một mục đích và phạm vi sử dụng. Ví dụ:

~~~text
HKDF(..., info="billing/v2|invoice|encrypt|tenant-A") -> DEK-like key A
HKDF(..., info="billing/v2|invoice|mac|tenant-A")     -> MAC key B
HKDF(..., info="billing/v2|audit|mac|tenant-A")       -> MAC key C
~~~

Mỗi nhãn phải có **quy ước byte không nhập nhằng**. Một phép nối đơn giản có thể gây va chạm ngữ nghĩa: giá trị (“ab”, “c”) và (“a”, “bc”) đều thành “abc” nếu bỏ độ dài/dấu phân cách. Có thể dùng **length-prefix**, định dạng nhị phân xác định hoặc canonical encoding theo giao thức.

Thông tin context có thể bao gồm **tên ứng dụng, protocol version, purpose, hướng truyền, tenant đã xác thực, ID tài nguyên, key version hoặc transcript hash**. Nhưng đây là giá trị mang tính ràng buộc **mật mã**, không phải giấy phép truy cập; ứng dụng vẫn phải kiểm tra **IAM và quyền nghiệp vụ**.

### 3.4. Output length và tham số chi phí

KDF phải tạo đúng số byte cần thiết cho mục đích:

- AES-128 cần **16 byte** khóa.
- AES-256 cần **32 byte** khóa.
- HMAC-SHA256 dùng khóa bí mật phù hợp với chính sách; không nhất thiết “phải” là một chuỗi 32 byte trong mọi giao thức.
- Key schedule có thể tạo nhiều khóa theo nhãn hoặc tạo một vùng output rồi phân đoạn **theo chuẩn đã định**.

**Đầu ra dài hơn không tự tăng entropy nguồn.** Ngoài ra, có những giới hạn đầu ra cụ thể theo KDF, chẳng hạn HKDF-Expand bị giới hạn bởi số block.

Tham số **iterations, memory cost và parallelism** đặc biệt quan trọng cho password-based KDF; chúng làm thay đổi chi phí phía kiểm tra hợp lệ và chi phí của kẻ tấn công. Không chọn những giá trị cực lớn chỉ để “an toàn” mà không tính tới latency, tài nguyên và nguy cơ DoS.

## 4. Hai nhóm use case: khóa mật mã mạnh và mật khẩu

| Câu hỏi | Trường hợp mật mã mạnh | Trường hợp mật khẩu |
| --- | --- | --- |
| Bí mật đầu vào đến từ đâu? | CSPRNG, HSM/KMS, ECDH hợp lệ, PSK mạnh | Người dùng nhập/mật khẩu có thể đoán |
| Mục tiêu chính | Tách miền sử dụng, dẫn xuất session/traffic keys, chuẩn hóa key material | Làm tấn công thử đoán tốn tài nguyên; tạo verifier hoặc khóa từ passphrase |
| Cơ chế thường chọn | **HKDF**, KDF được đặc tả trong giao thức, NIST SP 800-108 khi phù hợp | **Argon2id**, **scrypt**, **PBKDF2** theo chính sách/nền tảng |
| Salt | Theo KDF/giao thức, thường công khai | Mỗi người dùng/đối tượng cần salt riêng phù hợp |
| Tham số chính | Hash/PRF, info, key schedule, output length | Salt, memory/time/parallelism hoặc iterations, output length |
| Nguy cơ trọng tâm | Lộ root, nhầm purpose, thiếu ràng buộc giao thức | Offline guessing, password yếu, tham số chi phí thấp |
| Vòng đời | Rotation root/IKM, session expiration, phân tách khóa | Nâng cost, rehash, đổi mật khẩu, khôi phục, pepper rotation |

**Quy tắc nhanh:**

- **Shared secret từ ECDH →** dùng KDF/key schedule của **giao thức được chuẩn hóa**, thường có HKDF.
- **Root secret ngẫu nhiên cần nhiều khóa con →** dùng HKDF hoặc KDF chuẩn với nhãn mục đích khác nhau.
- **Password cần xác minh đăng nhập →** dùng **password hashing/password-based KDF** được khuyến nghị và định dạng lưu verifier có version.
- **Passphrase dùng để mã hóa tệp →** password-based KDF để tạo khóa mã hóa, sau đó **AEAD** và quản lý salt/nonce/tag.
- **Cần DEK cho dữ liệu doanh nghiệp →** nhiều trường hợp đơn giản và an toàn hơn nếu tạo **DEK ngẫu nhiên** và bọc bằng **KEK trong KMS**, thay vì dẫn xuất DEK từ một mật khẩu.

## 5. HKDF: Extract và Expand

**HKDF** (*HMAC-based Extract-and-Expand Key Derivation Function*) được mô tả trong **RFC 5869**. Nó đặc biệt hữu ích khi đầu vào là vật liệu mật mã có entropy phù hợp. HKDF có hai giai đoạn:

1. **Extract:** kết hợp IKM và salt để tạo **PRK (Pseudorandom Key)**.
2. **Expand:** từ PRK, info và độ dài đầu ra để tạo **OKM (Output Keying Material)**.

~~~mermaid
flowchart TD
    I["IKM: vật liệu bí mật đầu vào"] --> E["HKDF-Extract"]
    S["salt theo quy ước"] --> E
    E --> P["PRK"]
    P --> A["HKDF-Expand: info A"]
    P --> B["HKDF-Expand: info B"]
    A --> K1["Khóa phiên client → server"]
    B --> K2["Khóa phiên server → client"]
~~~

Với **HKDF-SHA256**, công thức rút gọn:

~~~text
PRK = HMAC-SHA256(salt, IKM)

T(0) = chuỗi byte rỗng
T(1) = HMAC-SHA256(PRK, T(0) || info || 0x01)
T(2) = HMAC-SHA256(PRK, T(1) || info || 0x02)
...
OKM = L byte đầu của T(1) || T(2) || ...
~~~

Dấu **||** là phép nối byte, còn 0x01, 0x02 là bộ đếm block một byte. Vì SHA-256 cho **HashLen = 32 byte**, RFC 5869 giới hạn độ dài đầu ra của HKDF-Expand ở **255 × 32 = 8160 byte**. Khóa AES-256 cần **32 byte**.

### 5.1. Salt trong HKDF có bắt buộc không?

HKDF cho phép **không cung cấp salt**; trong mô tả của RFC, salt mặc định là dãy byte 0 dài bằng HashLen. Tuy nhiên, salt độc lập phù hợp có thể cải thiện một số tính chất của bước Extract, và giao thức thường quy định rõ cách sử dụng.

**Không coi việc thêm salt là cách biến mật khẩu yếu thành IKM mạnh.** Nếu nguồn là password, phải dùng loại password-based KDF phù hợp, không dùng HKDF nhanh như một cơ chế chính để chống đoán mật khẩu.

### 5.2. Khóa nào nên tách?

Khi có một secret mạnh, ít nhất cần xem xét tách khóa theo:

- **Mục đích:** encrypt, MAC, wrap, exporter, session.
- **Hướng truyền:** client-to-server khác server-to-client.
- **Ứng dụng/giao thức:** billing khác audit, giao thức v1 khác v2.
- **Môi trường:** production khác staging/development khi có ranh giới tin cậy khác.
- **Tenant hoặc tài nguyên:** khi có chính sách tách biệt rõ và identity/context được xác thực.
- **Phiên/giai đoạn:** khóa traffic của phiên mới không nên mặc định tái sử dụng khóa phiên cũ.

Trong giao thức như **TLS 1.3**, hãy dùng **toàn bộ key schedule đã được đặc tả**, không tự thay bằng một vài lời gọi HKDF có nhãn tự đặt. KDF tốt không thể bù cho **thiếu xác thực public key, lỗi replay hay downgrade**.

## 6. Password-based KDF: Argon2id, scrypt và PBKDF2

Mật khẩu cần đối phó với một mô hình đe dọa khác: khi kẻ tấn công lấy được database chứa salt và verifier, họ có thể thử các password ứng viên **ngoại tuyến**, không chịu rate limit của API đăng nhập.

Password-based KDF được thiết kế để khiến từng lần thử **tốn CPU, bộ nhớ hoặc cả hai**.

### 6.1. Argon2id

**Argon2id** là biến thể Argon2 kết hợp đặc tính chống tấn công trên các mô hình kênh phụ và phần cứng song song theo thiết kế. Nó cho phép cấu hình:

- **Memory cost:** lượng bộ nhớ sử dụng.
- **Time cost:** số lượt/vòng làm việc.
- **Parallelism:** mức song song (số lane/thread logic theo triển khai).
- **Salt:** giá trị ngẫu nhiên riêng theo đối tượng.
- **Output length:** độ dài kết quả cần lấy.

Argon2id là lựa chọn phổ biến cho **password hashing mới** khi nền tảng và chính sách cho phép. Nó **không** có trong Java 17 JCA chuẩn theo cách gọi tương tự SecretKeyFactory PBKDF2; để dùng cần **thư viện có bảo trì và hỗ trợ đúng định dạng**, kiểm thử cấu hình và cập nhật bảo mật.

Không nên chọn tham số chỉ theo một con số trong ví dụ trên Internet. Cần dựa vào **khuyến nghị an ninh đang áp dụng**, benchmark trên hạ tầng thật, giới hạn request song song và kế hoạch tăng chi phí theo thời gian.

### 6.2. scrypt

**scrypt** (RFC 7914) cũng là một password-based KDF tiêu tốn bộ nhớ, với các tham số chi phí điều chỉnh được. Nó hữu ích khi hệ sinh thái có implementation phù hợp và cần giảm lợi thế của những hệ thống thử mật khẩu song song quy mô lớn.

Chi phí lớn cũng là **chi phí phía dịch vụ hợp lệ**: triển khai cần giới hạn đồng thời, timeout hợp lý, tách tài nguyên hoặc các kiểm soát khác để giảm khả năng người dùng xấu gây cạn bộ nhớ qua hàng loạt yêu cầu đăng nhập.

### 6.3. PBKDF2

**PBKDF2** (RFC 8018, dùng trong nhiều hệ sinh thái) lấy password, salt và **iteration count**, sử dụng một PRF như **HMAC-SHA256** để dẫn xuất output.

~~~text
PBKDF2-HMAC-SHA256(
  password,
  salt ngẫu nhiên riêng cho tài khoản,
  iterations theo chính sách,
  outputLength
) -> verifier hoặc key material
~~~

PBKDF2 có ưu điểm **tương thích rộng** và sẵn có trong Java qua **SecretKeyFactory**. Tuy nhiên, PBKDF2 không có mục tiêu sử dụng bộ nhớ lớn như Argon2id/scrypt. Khi chọn PBKDF2, cần thông số iterations đủ theo chính sách tại thời điểm triển khai và tăng dần khi cần; không coi một con số cố định là tốt mãi mãi.

### 6.4. So sánh nhanh

| Tiêu chí | Argon2id | scrypt | PBKDF2-HMAC-SHA256 |
| --- | --- | --- | --- |
| Đầu vào thông dụng | Password | Password | Password |
| Khả năng điều chỉnh chi phí | Memory, time, parallelism | CPU/memory parameters | Iterations |
| Chi phí bộ nhớ có chủ đích | Có | Có | Không theo cùng mô hình |
| Khả dụng trong Java 17 chuẩn | Cần thư viện ngoài | Cần thư viện ngoài | Có SecretKeyFactory |
| Lựa chọn triển khai | Thường ưu tiên nếu chính sách và thư viện cho phép | Phù hợp khi hệ thống hỗ trợ | Hữu ích cho tương thích/yêu cầu cụ thể |
| Điểm phải lưu | Thuật toán, version, salt, tham số, hash/verifier | Thuật toán, salt, cost, verifier | Thuật toán/PRF, salt, iterations, output length, verifier |

**Không thay thế một password-based KDF bằng SHA-256(password)** chỉ để tăng tốc. Khả năng tính nhanh của SHA-256 chính là lợi thế cho kẻ tấn công khi thử từ điển ngoại tuyến.

### 6.5. Password hashing không giống mã hóa password

Đối với **đăng nhập**, server không cần giải mã mật khẩu gốc. Nó lưu một **password verifier** có salt và tham số; khi người dùng đăng nhập, tính lại và so sánh theo cách phù hợp. Đây là bài toán một chiều.

Đối với **mã hóa dữ liệu bằng passphrase**, ứng dụng cần **tái dẫn xuất chính xác khóa mã hóa** khi người dùng nhập cùng passphrase, rồi giải mã bằng AEAD. Phải lưu salt/param/version/nonce/tag, và có chính sách khi passphrase bị quên.

**Không dùng verifier/hash lưu trong database làm khóa mã hóa dữ liệu nghiệp vụ.** Nếu database bị lộ, người lấy verifier có thể có khả năng dùng nó như khóa, làm mất mục đích bảo vệ password. Phân tách **password authentication** khỏi **data encryption**.

## 7. Salt, pepper và chính sách quản lý bí mật

### 7.1. Pepper là gì?

**Pepper** là bí mật do server giữ riêng, có thể được kết hợp vào quy trình bảo vệ password/verifier theo thiết kế đã được phân tích. Khác salt, pepper **không được lưu chung database password hash**.

Ví dụ tổng quát:

~~~text
Password + per-user salt ──Password KDF──> kết quả trung gian
                                       |
                                       v
                            Cơ chế bảo vệ có pepper
                            (ví dụ HMAC theo chính sách)
                                       |
                                       v
                           Password verifier lưu trong DB

Pepper ──► KMS/HSM hoặc secret storage riêng, quản trị chặt
~~~

Sơ đồ là minh họa ý tưởng, **không phải một công thức password hashing chuẩn có thể tự ghép tùy tiện**. Nên dùng chiến lược pepper được thư viện/chính sách hỗ trợ, chẳng hạn một lớp HMAC sau password KDF với quản lý key version và yêu cầu xử lý khi mất pepper.

### 7.2. Pepper không thay thế salt hoặc KDF

- Salt có thể công khai và phải được **riêng hóa** phù hợp cho từng password verifier.
- Pepper là bí mật bổ sung; nếu pepper bị lộ, hệ thống vẫn cần KDF/password đủ mạnh để hạn chế đoán mật khẩu.
- Pepper làm tăng độ phức tạp vận hành: **backup, phân quyền, rotation và khôi phục**.
- Nếu mất pepper không thể khôi phục, hệ thống có thể **không xác minh được password cũ**; thường phải cho người dùng đặt lại mật khẩu hoặc có phương án được thiết kế trước.
- Đổi pepper không luôn có thể thực hiện bằng cách đổi một giá trị trong cấu hình: tùy cấu trúc verifier, có thể cần biết mật khẩu gốc lúc người dùng đăng nhập hoặc quy trình migration đặc biệt.

Một pepper lưu trong **cùng database** hoặc cùng bản backup/phân quyền với toàn bộ verifier thường không đạt được mục đích tách ranh giới bảo vệ.

### 7.3. Không thể dựa vào password KDF để thay kiểm soát đăng nhập

Ngay cả Argon2id với tham số tốt vẫn cần:

- Password policy hợp lý và cơ chế xác thực bổ sung khi rủi ro yêu cầu.
- Rate limit, chống credential stuffing và giám sát bất thường.
- Quy trình reset/recovery an toàn.
- Giao tiếp qua TLS, không ghi password vào log/telemetry.
- Kiểm soát session, token, IAM và quyền nghiệp vụ.

Password-based KDF chủ yếu giảm hiệu quả **offline cracking** sau khi verifier bị lộ. Nó không tự chặn kẻ dùng một mật khẩu hợp lệ đã bị đánh cắp.

## 8. Ví dụ Java 17: PBKDF2 để tạo và kiểm tra password verifier

Ví dụ này minh họa **PBKDF2WithHmacSHA256** có sẵn trong JDK 17, salt ngẫu nhiên và việc giữ thuật toán/iteration count để xác minh lại. Mật khẩu là dữ liệu **chỉ phục vụ demo**. Trong sản phẩm mới, cân nhắc Argon2id/scrypt bằng thư viện được bảo trì khi chính sách hỗ trợ.

> **Các tham số minh họa không phải ngưỡng khuyến nghị bất biến.** Đội an ninh cần cập nhật theo chính sách, benchmark CPU, kiểm soát tải và nhu cầu tương thích trước khi triển khai.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordKdfDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;
    // Chỉ cho demo; điều chỉnh theo chính sách và benchmark thực tế.
    private static final int ITERATIONS = 600_000;

    // Đại diện record được lưu trong DB; tuyệt đối không lưu password.
    public record Verifier(
            String algorithm, int iterations,
            String saltBase64, String hashBase64) {}

    private static byte[] derive(
            char[] password, byte[] salt, int iterations) throws Exception {
        if (salt.length < SALT_BYTES || iterations <= 0) {
            throw new IllegalArgumentException("Invalid KDF parameters");
        }
        PBEKeySpec spec = new PBEKeySpec(
            password, salt, iterations, KEY_BITS);
        try {
            return SecretKeyFactory.getInstance(ALGORITHM)
                .generateSecret(spec)
                .getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    public static Verifier register(char[] password) throws Exception {
        byte[] salt = new byte[SALT_BYTES];
        RNG.nextBytes(salt);
        byte[] digest = derive(password, salt, ITERATIONS);
        try {
            return new Verifier(
                ALGORITHM,
                ITERATIONS,
                Base64.getEncoder().encodeToString(salt),
                Base64.getEncoder().encodeToString(digest));
        } finally {
            Arrays.fill(digest, (byte) 0);
        }
    }

    public static boolean verify(char[] candidate, Verifier stored)
            throws Exception {
        // Chỉ chấp nhận thuật toán và phiên bản do server cho phép.
        if (!ALGORITHM.equals(stored.algorithm())
                || stored.iterations() <= 0
                || stored.iterations() > 5_000_000) {
            return false;
        }
        byte[] salt = Base64.getDecoder().decode(stored.saltBase64());
        byte[] expected = Base64.getDecoder().decode(stored.hashBase64());
        if (salt.length < SALT_BYTES || expected.length != KEY_BITS / 8) {
            return false;
        }

        byte[] calculated = derive(
            candidate, salt, stored.iterations());
        try {
            return MessageDigest.isEqual(expected, calculated);
        } finally {
            Arrays.fill(calculated, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "demo-only-password".toCharArray();
        char[] wrong = "incorrect-password".toCharArray();
        try {
            Verifier saved = register(password);
            System.out.println("Algorithm: " + saved.algorithm());
            System.out.println("Right password: " + verify(password, saved));
            System.out.println("Wrong password: " + verify(wrong, saved));
            // Không in password, password-derived bytes hoặc pepper.
            // salt và verifier là dữ liệu được lưu có chính sách truy cập.
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
Algorithm: PBKDF2WithHmacSHA256
Right password: true
Wrong password: false
~~~

### 8.1. Những điểm cần hiểu chính xác

- **SecureRandom** tạo salt ngẫu nhiên riêng cho mỗi lần đăng ký.
- **PBEKeySpec** giữ password dạng mảng char để có thể giảm thời gian giữ dữ liệu rõ; phải gọi **clearPassword**.
- **SecretKeyFactory** thực hiện PBKDF2 theo thuật toán được khai báo.
- **Base64** chỉ biểu diễn byte để lưu/đọc; không phải mã hóa bảo mật.
- **MessageDigest.isEqual** là cách so sánh phù hợp hơn phép so sánh tùy tiện đối với vật liệu xác thực; kiểm tra cấu trúc và độ dài trước.
- **Password không được lưu** trong record; record cần thuật toán, salt, iterations và verifier để xác minh về sau.
- **Bảo vệ account và database** vẫn cần thiết. Hash/verifier bị lộ có thể tạo cơ hội thử mật khẩu ngoại tuyến.
- Mã có **giới hạn iterations tối đa** nhằm tránh nhận giá trị phi lý từ dữ liệu chưa tin cậy; production cần bảo vệ cả nguồn record và giới hạn tải/tài nguyên thực tế.

**Không coi việc xóa mảng char là bảo đảm xóa mọi bản sao password khỏi JVM.** Biểu diễn ở các lớp framework, request parser hoặc provider có thể tạo bản sao khác. Quy trình xử lý secrets, log và memory dumps vẫn phải được kiểm soát.

### 8.2. Thiếu gì để thành một dịch vụ đăng nhập?

Code trên không bao gồm đăng ký tài khoản, xác thực session, xử lý lỗi thống nhất, rate limit, khóa tạm theo chính sách, phát hiện credential stuffing, reset password, password rehash khi đổi cost hoặc thư viện Argon2id, pepper, monitoring và kiểm toán.

Đặc biệt, **không dùng dữ liệu do client tùy ý truyền đến để chọn algorithm/iterations**. Định dạng lưu verifier có thể có version nhưng server phải áp dụng **allowlist** của thuật toán và giới hạn tham số.

## 9. Ví dụ Java 17: HKDF-SHA256 tạo hai khóa con từ IKM mạnh

Ví dụ tiếp theo minh họa công thức **RFC 5869** bằng HMAC-SHA256 có sẵn trong JCA. Đầu vào là IKM ngẫu nhiên 32 byte. Hai khóa đầu ra có **info khác nhau**, tránh dùng một khóa cho cả mã hóa và xác thực.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HkdfExample {
    private static final String HMAC = "HmacSHA256";
    private static final int HASH_LEN = 32;
    private static final SecureRandom RNG = new SecureRandom();

    // HKDF-Extract(salt, IKM); demo luôn dùng salt 32 byte.
    private static byte[] extract(byte[] ikm, byte[] salt)
            throws Exception {
        Mac mac = Mac.getInstance(HMAC);
        mac.init(new SecretKeySpec(salt, HMAC));
        return mac.doFinal(ikm);
    }

    // HKDF-Expand(PRK, info, L), giới hạn theo RFC 5869.
    private static byte[] expand(byte[] prk, byte[] info, int length)
            throws Exception {
        if (length <= 0 || length > 255 * HASH_LEN) {
            throw new IllegalArgumentException("Invalid output length");
        }

        Mac mac = Mac.getInstance(HMAC);
        mac.init(new SecretKeySpec(prk, HMAC));
        byte[] output = new byte[length];
        byte[] previous = new byte[0]; // T(0) rỗng.
        int offset = 0;

        try {
            for (int i = 1; offset < length; i++) {
                mac.reset();
                mac.update(previous);
                mac.update(info);
                mac.update((byte) i); // Một byte đếm block.

                byte[] next = mac.doFinal();
                Arrays.fill(previous, (byte) 0);
                previous = next;
                int count = Math.min(next.length, length - offset);
                System.arraycopy(next, 0, output, offset, count);
                offset += count;
            }
            return output;
        } finally {
            Arrays.fill(previous, (byte) 0);
        }
    }

    // Mã hóa info bằng length-prefix để không nhập nhằng.
    private static byte[] label(String app, String purpose) {
        byte[] a = app.getBytes(StandardCharsets.UTF_8);
        byte[] p = purpose.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(8 + a.length + p.length)
            .putInt(a.length).put(a)
            .putInt(p.length).put(p)
            .array();
    }

    public static void main(String[] args) throws Exception {
        byte[] ikm = new byte[32];
        byte[] salt = new byte[32];
        RNG.nextBytes(ikm);
        RNG.nextBytes(salt);

        byte[] prk = null;
        byte[] encryptionKey = null;
        byte[] macKey = null;
        try {
            prk = extract(ikm, salt);
            encryptionKey = expand(
                prk, label("billing/v1", "invoice-encrypt"), 32);
            macKey = expand(
                prk, label("billing/v1", "audit-hmac"), 32);

            System.out.println("Encryption key bytes: "
                + encryptionKey.length);
            System.out.println("MAC key bytes: " + macKey.length);
            System.out.println("Different keys: "
                + !Arrays.equals(encryptionKey, macKey));
        } finally {
            Arrays.fill(ikm, (byte) 0);
            if (prk != null) Arrays.fill(prk, (byte) 0);
            if (encryptionKey != null) Arrays.fill(encryptionKey, (byte) 0);
            if (macKey != null) Arrays.fill(macKey, (byte) 0);
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
Encryption key bytes: 32
MAC key bytes: 32
Different keys: true
~~~

### 9.1. Những ranh giới của ví dụ

1. **IKM ngẫu nhiên** khác password; không thay trực tiếp bằng mật khẩu dễ đoán.
2. **Salt và info thường không bí mật**; phải giữ chính xác nếu muốn tái dẫn xuất khóa khi khôi phục dữ liệu cũ.
3. **Domain separation** dùng nhãn khác nhau; một bên tự ý thay tên/byte của nhãn sẽ dẫn xuất khóa khác.
4. Trong Java, **Mac/SecretKeySpec/provider có thể sao chép key material**; Arrays.fill không bảo đảm xóa sạch toàn bộ bản sao.
5. **Ví dụ không mã hóa dữ liệu.** Khi dùng khóa AES-GCM phải quản lý nonce không trùng dưới cùng khóa, tag và AAD.
6. **Ví dụ không xác thực danh tính hoặc người gọi.** Nếu dùng shared secret từ ECDH, cần authenticated key agreement đúng giao thức trước khi tin khóa.
7. **Production nên ưu tiên KDF chuẩn của giao thức hoặc thư viện được kiểm chứng**; đừng tự dùng lớp demo để xây giao thức mạng riêng.

## 10. KDF trong vòng đời khóa và envelope encryption

### 10.1. Derived key có thể là DEK hoặc KEK

Khi một hệ thống cần mã hóa dữ liệu lâu dài:

- **DEK (Data Encryption Key)** trực tiếp bảo vệ dữ liệu, thường với AES-GCM.
- **KEK (Key Encryption Key)** dùng bọc/mở DEK.
- **Root/master secret** có thể tham gia dẫn xuất KEK hoặc các khóa con trong một **kiến trúc cho phép**, nhưng không mặc định nên đưa root vào ứng dụng.
- **KDF** có thể dẫn xuất khóa theo tenant/purpose hoặc tạo key material cho một giao thức; **key wrapping** lại dùng KEK để bảo vệ một DEK đã có.

~~~mermaid
flowchart TB
    subgraph A["Hệ phân cấp dẫn xuất"]
        R["Root secret entropy cao"] --> F["KDF + context + version"]
        F --> K1["Derived key theo purpose A"]
        F --> K2["Derived key theo purpose B"]
    end
    subgraph B["Envelope encryption"]
        C["DEK ngẫu nhiên"] --> E["AES-GCM mã hóa dữ liệu"]
        C --> W["Wrap DEK"]
        H["KEK trong KMS/HSM"] --> W
        W --> WD["Wrapped DEK"]
        E --> CT["Ciphertext + nonce + tag"]
    end
~~~

Hai mô hình không loại trừ nhau. Nhưng nếu **mỗi ứng dụng đều giữ một root secret dùng chung** để tự dẫn xuất DEK của mọi tenant, lộ một tiến trình có thể khiến toàn bộ khóa con bị ảnh hưởng. Trong nhiều hệ thống doanh nghiệp, tạo **DEK ngẫu nhiên từ KMS và bọc dưới KEK không xuất được** thường dễ cô lập quyền và quản lý rotation hơn.

### 10.2. KMS/HSM giúp bảo vệ điều gì?

**KMS/HSM** có thể hỗ trợ các vai trò sau, tùy loại khóa và API của nhà cung cấp:

- Sinh root/key material ngẫu nhiên mạnh; kiểm soát khả năng xuất khóa.
- Thực hiện **GenerateDataKey, Wrap/Unwrap, Encrypt/Decrypt, DeriveKey hoặc HMAC** nếu tính năng được hỗ trợ.
- Quản lý key ID/version, cryptoperiod, disable, rotation và lịch hủy.
- Áp dụng policy theo principal/workload, môi trường, loại thao tác và ngữ cảnh.
- Ghi audit các lần gọi thao tác nhạy cảm và thay đổi policy.

**Không phải KMS nào cũng có API HKDF hoặc Argon2id.** Việc một khóa nằm trong KMS không tự bảo đảm ứng dụng có thể dùng nó làm IKM, cũng không bảo đảm dẫn xuất được nhiều khóa con theo công thức tự chọn.

Nếu phải dùng KDF trong ứng dụng, cần định nghĩa rõ **phạm vi xuất key material**, chủ sở hữu root, nơi lưu, backup, quyền đọc, thời gian sống trong JVM và cách bảo vệ khi crash/core dump. Không log root, PRK, derived key hay password.

### 10.3. IAM và tenant isolation

Ví dụ **tenant-A** và **tenant-B** được dẫn xuất khóa bằng info khác nhau từ cùng root. Tách info có thể giúp tạo khóa con khác nhau, nhưng không thay thế **phân quyền tenant**:

- Principal yêu cầu dẫn xuất phải được xác thực.
- Tenant ID đưa vào context phải lấy từ **nguồn tin cậy**, không chỉ tin header client.
- Workload chỉ được dẫn xuất khóa đúng purpose/tenant theo chính sách.
- Không cho một dịch vụ có quyền root rộng vô cớ chỉ vì nó cần một DEK.
- Audit phải giúp xác định **ai đã dùng root/derive/unwrap** theo phiên bản nào.

Một hệ thống cần ranh giới cách ly mạnh có thể chọn **root/KEK độc lập theo môi trường hoặc tenant** thay vì chỉ dùng nhãn tenant khác nhau.

## 11. Rotation, migration và khả năng giải mã dữ liệu cũ

### 11.1. Khi thuật toán/tham số KDF thay đổi

Đối với password verifier, record nên có **algorithm, version, salt, iterations hoặc cost parameters, output length và verifier**. Khi chính sách tăng cost hoặc đổi sang Argon2id, ứng dụng có thể:

1. Xác minh mật khẩu theo **định dạng cũ được cho phép**.
2. Khi người dùng đăng nhập thành công, tính verifier mới với salt và tham số mới.
3. Ghi verifier mới một cách an toàn, tránh race hoặc cập nhật một phần.
4. Dần loại bỏ định dạng cũ theo chính sách; tài khoản không quay lại có thể cần luồng reset.

Không thể chỉ đổi trường **iterations** từ thấp lên cao mà giữ nguyên verifier và hy vọng vẫn xác minh đúng. Giá trị dẫn xuất phụ thuộc tham số.

### 11.2. Khi root secret/IKM dùng cho dữ liệu thay đổi

Giả sử một bản ghi hóa đơn cũ dùng:

~~~text
DEK-v1 = HKDF(root-v1, salt-A, info="billing|tenant-A|invoice|v1", 32)
ciphertext-v1 = AES-GCM(DEK-v1, plaintext, nonce-v1, AAD)
~~~

Nếu ứng dụng chuyển sang root-v2, việc tính HKDF với root-v2 sẽ tạo khóa khác; **ciphertext-v1 không tự giải mã được bằng DEK-v2**.

| Thao tác | Có đổi ciphertext dữ liệu? | Lưu ý |
| --- | --- | --- |
| **Thay salt/info/version của KDF** | Chưa tự đổi | Muốn giải mã dữ liệu cũ vẫn phải giữ cách tái tạo DEK cũ |
| **Thay root/IKM** | Chưa tự đổi | Cần giữ đường giải mã cũ hoặc re-encrypt dữ liệu |
| **Rewrap DEK đã được lưu** | Không nhất thiết | Thay lớp bọc, **giữ nguyên giá trị DEK** |
| **Thay DEK và re-encrypt** | Có | Cần tạo nonce/tag/ciphertext phù hợp và đảm bảo khôi phục |
| **Hủy root/KEK cũ** | Không tự đổi | Có thể làm dữ liệu/backup cũ không giải mã được |

**Rewrap không giống re-encrypt.** Nếu root/DEK cũ đã bị lộ và attacker có bản mã liên quan, chỉ bọc lại DEK **không thể làm bí mật lại** bản sao cũ. Cần đánh giá việc phát hành DEK mới, re-encrypt và thu hồi credential.

### 11.3. Metadata tái dẫn xuất

Một định dạng minh họa khi chủ động dùng KDF cho khóa mã hóa:

~~~json
{
  "ciphertextAndTag": "<base64 ciphertext and AEAD tag>",
  "nonce": "<base64 nonce>",
  "rootKeyRef": "root-prod-v3",
  "kdf": "HKDF-SHA256",
  "kdfVersion": 1,
  "salt": "<base64 salt>",
  "infoFormat": "length-prefixed-utf8-v1",
  "purpose": "invoice-encryption",
  "tenantId": "tenant-A",
  "recordId": "invoice-154",
  "cipher": "AES-256-GCM"
}
~~~

Đây là cấu trúc **khái niệm**, không chứa dữ liệu mật mã thật. **Root secret/derived DEK ở dạng rõ không được lưu** trong record. AAD và policy cần ràng buộc metadata với identity/tài nguyên đã được phân quyền. Nếu thiết kế dùng **wrapped DEK**, phải lưu **wrapped DEK, KEK ID/version** phù hợp.

**Sao lưu ciphertext mà quên root/KEK hoặc thiếu salt/info/version có thể khiến dữ liệu không thể phục hồi**, dù hash của file backup hoàn toàn khớp. Do đó thử restore phải bao gồm đường giải mã và khóa cần thiết.

## 12. Threat model: lỗi thường gặp và cách khắc phục

| Sai lầm | Vì sao nguy hiểm? | Biện pháp |
| --- | --- | --- |
| **SHA-256(password)** để lưu verifier | Quá nhanh; attacker thử từ điển ngoại tuyến hiệu quả | Argon2id/scrypt/PBKDF2 phù hợp chính sách, salt riêng và cost |
| **HKDF cho mật khẩu yếu** | HKDF không được thiết kế để làm chậm password guessing | Dùng password-based KDF, nâng chất lượng password và kiểm soát tài khoản |
| **Một salt cố định cho mọi tài khoản** | Những mật khẩu trùng dễ cho kết quả trùng, hỗ trợ tấn công trên nhiều record | Salt ngẫu nhiên riêng khi tạo verifier |
| **Dùng tenant ID làm secret** | ID thường dự đoán/biết được, không có entropy bí mật | Dùng root key/PSK ngẫu nhiên mạnh; tenant ID là context |
| **Không phân tách purpose trong HKDF** | Nhiều giao thức hoặc chức năng có thể dùng lại cùng khóa | Info có namespace, version, purpose, role và encoding xác định |
| **Đổi encoding password tùy môi trường** | Cùng ký tự hiển thị nhưng khác input byte | Chính sách Unicode/encoding được định nghĩa và kiểm thử tương thích |
| **Root secret hard-code trong Java source** | Lộ qua Git, image hoặc log; ảnh hưởng mọi derived key | KMS/HSM hoặc kho secret đúng quyền, hạn chế xuất root |
| **Lưu pepper cùng database verifier** | Khi database lộ, attacker có cả hai lớp | Tách pepper trong hệ thống bí mật, quản lý rotation |
| **Cho client chọn iterations tùy ý** | Có thể gây DoS hoặc hạ cấp tham số | Server allowlist và giới hạn chi phí/thuật toán |
| **Không lưu KDF version/salt/info** | Không thể tái tạo khóa, không giải mã được dữ liệu cũ | Versioned metadata, migration và restore test |
| **Chỉ đổi root sau khi root cũ bị lộ** | Bản sao root cũ vẫn có thể dẫn xuất khóa cũ | Điều tra phạm vi, re-encrypt nếu cần, revoke và kiểm toán |
| **Dùng cùng DEK với nonce AES-GCM lặp** | Có thể phá confidentiality/integrity | Thiết kế nonce duy nhất, giới hạn sử dụng và key rotation |
| **Tin HKDF tự chống MITM** | KDF không xác thực public key/peer | Giao thức authenticated key agreement như TLS |
| **Tin Argon2id tự chống credential stuffing** | Mật khẩu hợp lệ bị đánh cắp vẫn đăng nhập được | Rate limit, MFA theo chính sách, giám sát, token/session controls |

### 12.1. KDF không tự chống replay hoặc giả mạo peer

Nếu hai máy thực hiện ECDH với public key chưa xác thực, attacker có thể đứng giữa và thương lượng bí mật riêng với từng máy. HKDF có thể tạo session keys đúng toán học cho cả hai kênh giả mạo; **vẫn phải xác thực peer và handshake**.

Tương tự, HMAC/chữ ký dựa trên derived key có thể hợp lệ cho một thông điệp đã bị phát lại. Cần timestamp, sequence, nonce hoặc idempotency state theo giao thức. KDF không tạo freshness thay cho tầng truyền tin.

### 12.2. Root key compromise có phạm vi ảnh hưởng lớn

Nếu root chung cho một nhóm tenant bị lộ, attacker biết salt và info (thường công khai) có thể tái tạo nhiều khóa con. **Không đủ** nếu chỉ đổi info label mà chưa xử lý dữ liệu cũ. Cần xác định các khóa con đã được dẫn xuất, dữ liệu đã mã hóa, các bản sao, quyền dùng root, khoảng thời gian bị ảnh hưởng và biện pháp migration thích hợp.

Ngược lại, nếu chỉ **một derived key** bị lộ, KDF với domain separation đúng có thể hạn chế khả năng suy ngược root hoặc tính khóa con khác trong giả định bảo mật. Tuy vậy, dữ liệu bảo vệ bởi **khóa con đã lộ** vẫn phải được xử lý như có nguy cơ mất bí mật.

## 13. Kiểm toán và vận hành KDF trong hệ thống Java

Một quy trình quản lý khóa phải bảo vệ cả **quyền sử dụng**, không chỉ vật liệu khóa.

Nên theo dõi:

- Ai tạo/thay root key, KEK hoặc cấu hình password hashing.
- Workload nào có quyền gọi **DeriveKey/GenerateDataKey/Unwrap**, ở môi trường nào.
- Thuật toán KDF nào đang dùng, phiên bản và mức chi phí, thời điểm thay đổi.
- Số lần login verify/rehash thất bại bất thường, nhưng không ghi password hoặc verifier không cần thiết vào log.
- Các lần đổi policy, disable/revoke/rotate/destroy khóa, cấp grant mới.
- Tỷ lệ lỗi giải mã tăng sau khi thay root, salt/info format hoặc KDF version.
- Kết quả kiểm thử khôi phục backup và trạng thái các key version còn phụ thuộc.

**Audit log** có thể ghi timestamp, principal/workload, key ID/version, tên thuật toán, request ID, loại thao tác, trạng thái và mã lỗi. Không ghi **password, root secret, PRK, derived key, DEK rõ, HMAC key, pepper hoặc payload nhạy cảm**.

### 13.1. Ranh giới trách nhiệm mẫu

| Vai trò | Quyền hợp lý | Không nên mặc định có |
| --- | --- | --- |
| **identity-service** | Verify password/rehash theo policy, sử dụng pepper qua dịch vụ được cấp quyền | Quyền quản trị/xóa root hoặc đọc mọi DEK |
| **data-encryption-service** | Tạo DEK, dùng wrapped DEK trong phạm vi tài nguyên được phép | Quyền xuất root secret toàn hệ thống |
| **key-admin** | Quản trị lifecycle/policy với phê duyệt | Quyền giải mã mọi bản ghi hoặc xem password |
| **security-auditor** | Xem key metadata/audit và cảnh báo | Quyền DeriveKey/Unwrap/GenerateMac |
| **recovery-operator** | Phục hồi có kiểm soát và ghi nhận | Quyền vĩnh viễn thao tác mọi khóa |

KMS/HSM có thể giới hạn việc **xuất secret**, nhưng nếu principal có quyền yêu cầu derive/unwrap quá rộng, attacker chiếm principal đó vẫn có thể lạm dụng API. Cần phân quyền theo identity, key ID, purpose/tenant và giám sát hoạt động.

## 14. Tình huống thiết kế thực tế

### Tình huống A: đăng nhập vào hệ thống quản lý hóa đơn

Yêu cầu: lưu verifier cho tài khoản quản trị và nhân viên, hạn chế nguy cơ sau khi database bị lộ.

Thiết kế:

1. Chọn **Argon2id** với tham số và thư viện được kiểm chứng theo chính sách; nếu ràng buộc công nghệ yêu cầu PBKDF2, dùng HMAC-SHA256 với chi phí được duyệt.
2. Sinh **salt riêng** cho mỗi verifier; lưu thuật toán/params/version cùng verifier.
3. Nếu dùng pepper, giữ pepper trong ranh giới bí mật khác database, có key version và kế hoạch mất/đổi pepper.
4. Khi đăng nhập, kiểm tra theo thuật toán record được server cho phép; so sánh an toàn, áp dụng rate limit/session policy.
5. Nâng cost hoặc chuyển thuật toán theo **rehash-on-login** hoặc migration có kiểm soát.
6. Không dùng password verifier làm **DEK hóa đơn**; dùng KMS và envelope encryption cho dữ liệu nghiệp vụ.

### Tình huống B: thiết lập khóa phiên giữa hai dịch vụ

Yêu cầu: hai dịch vụ trao đổi dữ liệu trên mạng không tin cậy.

Thiết kế:

1. Dùng **TLS 1.3** và thư viện có hỗ trợ, xác thực danh tính máy chủ/client theo yêu cầu.
2. Để key schedule theo chuẩn xử lý ECDH shared secret, HKDF, transcript và tách khóa theo hướng.
3. Không tự lấy **ECDH shared secret** làm AES key hoặc dùng HKDF tự chế thay giao thức TLS.
4. Không log shared secret/traffic keys; giới hạn thời gian phiên và tuân thủ rekey.
5. Kiểm tra quyền nghiệp vụ riêng sau khi thiết lập kết nối.

### Tình huống C: mã hóa tài liệu dài hạn

Yêu cầu: mã hóa hóa đơn lưu nhiều năm, có backup và khả năng khôi phục.

Thiết kế:

1. Cân nhắc **DEK ngẫu nhiên** cho mỗi đối tượng hoặc nhóm dữ liệu phù hợp, thay vì KDF từ password của quản trị viên.
2. Dùng **AES-GCM** với nonce đúng quy tắc, AAD gắn tenant/record đã xác thực.
3. Bọc DEK bằng **KEK trong KMS/HSM**; quản lý key ID, wrapped DEK và version.
4. Thiết kế rotation KEK/rewrap khác với DEK rotation/re-encrypt.
5. Audit quyền unwrap và thử khôi phục backup bao gồm **khóa, context, metadata và plaintext được xác thực**.

Nếu cố ý dùng root/KDF để tạo DEK, phải kiểm kê nguy cơ **một root chung lộ ảnh hưởng mọi tài liệu** và tính khả thi khi di chuyển root. KDF không thay thế việc xác định **blast radius**.

## 15. Checklist thiết kế KDF an toàn

1. **Nguồn entropy:** đầu vào là password yếu hay key material mạnh? Có bằng chứng về cách tạo bí mật?
2. **Mục đích:** đang tạo verifier đăng nhập, encryption key, MAC key, KEK hay session key?
3. **Chọn thuật toán:** HKDF/KDF giao thức cho key material mạnh; password-based KDF cho password?
4. **Thuật toán chuẩn:** thư viện được kiểm chứng và có chính sách thuật toán/phiên bản rõ ràng không?
5. **Salt:** có theo đúng mô hình của KDF, riêng theo đối tượng khi cần, được tạo ngẫu nhiên và lưu đủ metadata không?
6. **Pepper:** nếu có, giữ ngoài database, quản lý rotation/backup/thu hồi và không tự ghép công thức chưa phân tích?
7. **Info/context:** có nhãn ứng dụng, mục đích, role, version, tenant đúng nguồn tin cậy và encoding không nhập nhằng không?
8. **Output length:** đủ cho thuật toán đích, không vượt giới hạn KDF và không dùng một output cho nhiều mục đích tùy tiện?
9. **KDF cost:** memory/time/iterations có được benchmark, hạn chế DoS và điều chỉnh theo chính sách hiện tại không?
10. **Phân quyền:** ai có quyền lấy IKM/root, DeriveKey, Unwrap hoặc dùng derived key ở tenant nào?
11. **Lưu trữ:** root/derived key có bị lộ qua source, biến môi trường, log, crash dump, backup hoặc hệ thống quản trị không?
12. **Mã hóa:** nếu khóa đầu ra dùng cho AES-GCM, nonce/tag/AAD và key usage có đúng không?
13. **Rotation:** khi đổi root, thuật toán KDF, salt/info version hoặc password cost, có xử lý dữ liệu/verifier cũ không?
14. **Khôi phục:** có đủ metadata và quyền KMS để đọc dữ liệu/backup cũ không?
15. **Sự cố:** nếu password verifier, pepper, root hoặc một khóa con bị lộ, có biết phạm vi và biện pháp xử lý riêng không?
16. **Audit:** thao tác quản trị/key use và lỗi được ghi nhận không làm lộ bí mật?
17. **Business controls:** KDF có được kết hợp với xác thực peer, phân quyền tenant và chống replay khi thích hợp không?

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một mật khẩu có entropy thực tế thấp, dùng SHA-256 rồi lấy 32 byte có thành khóa AES-256 khó đoán tương đương khóa ngẫu nhiên không?

**Đáp án:** Không. Độ dài output không làm tăng entropy đầu vào. Nếu nguồn là mật khẩu, dùng password-based KDF phù hợp và chấp nhận rằng an toàn vẫn bị giới hạn bởi khả năng đoán password.

**Câu 2.** Vì sao không nên dùng HKDF(password, salt, info) thay Argon2id hoặc PBKDF2 để lưu password verifier?

**Đáp án:** HKDF là KDF nhanh cho key material mật mã; không thiết kế để làm mỗi lần đoán password tốn chi phí. Password-based KDF có cơ chế tăng CPU/bộ nhớ nhằm làm chậm offline guessing.

**Câu 3.** Salt có cần bí mật và có thể dùng cùng một salt cho mọi tài khoản không?

**Đáp án:** Salt thường công khai. Với password verifier, nên có salt riêng theo tài khoản/record và đúng quy tắc thuật toán; dùng salt cố định toàn hệ thống làm mất lợi ích phân tách.

**Câu 4.** Pepper có thể lưu ngay cạnh password verifier trong database không?

**Đáp án:** Điều đó làm mất mục đích bảo vệ bằng ranh giới độc lập. Nếu dùng pepper, phải giữ nó trong kho bí mật/KMS/HSM hoặc cơ chế có quyền tách biệt và có kế hoạch rotation/recovery.

**Câu 5.** HKDF-Expand dùng cùng PRK nhưng info khác nhau để tạo khóa mã hóa và khóa MAC. Điều này có ích gì?

**Đáp án:** Tạo **domain separation**: hai mục đích không dùng cùng key material đầu ra, giảm nguy cơ tương tác sai giữa các primitive/giao thức, trong giới hạn giả định bảo mật của HKDF.

**Câu 6.** Thay root-v1 thành root-v2 có tự giúp giải mã bản mã được tạo từ derived key của root-v1 không?

**Đáp án:** Không. Để đọc dữ liệu cũ phải giữ điều kiện dẫn xuất cũ hoặc giải mã và re-encrypt bằng khóa mới theo quy trình an toàn. Nếu root cũ bị lộ, cần đánh giá bản mã và phạm vi khóa con liên quan.

**Câu 7.** Nếu đã dùng Argon2id tốt, có thể bỏ rate limit/MFA và giám sát đăng nhập không?

**Đáp án:** Không. Password-based KDF giảm hiệu quả thử đoán **ngoại tuyến** với verifier bị lộ; nó không tự ngăn credential stuffing, replay token hay truy cập bằng mật khẩu hợp lệ bị đánh cắp.

**Câu 8.** KMS giữ root secret ở trạng thái non-exportable. Dịch vụ có quyền DeriveKey rất rộng có thể gây rủi ro không?

**Đáp án:** Có. Kẻ chiếm workload có thể lạm dụng **quyền sử dụng khóa** để dẫn xuất khóa cho các mục đích hoặc tenant trái phép, dù không lấy được root ở dạng rõ. Cần IAM least privilege, policy và audit.

**Câu 9.** Tại sao phải lưu algorithm version, salt, info format và tham số KDF cùng metadata cần thiết?

**Đáp án:** Vì KDF có tính xác định theo đầu vào và cấu hình. Thiếu hoặc thay sai các tham số sẽ tạo output khác, làm password verify hoặc giải mã dữ liệu cũ thất bại.

**Câu 10.** Một hệ thống mã hóa hóa đơn dài hạn nên mặc định dẫn xuất tất cả DEK từ password quản trị viên hay cân nhắc DEK ngẫu nhiên được bọc trong KMS?

**Đáp án:** Nên đánh giá mô hình đe dọa và thường cân nhắc **DEK ngẫu nhiên + KEK trong KMS/HSM**. Password yếu và một bí mật chung có thể tạo blast radius lớn, khó phân quyền, rotation và phục hồi.

## Kết luận

**Key derivation function (KDF)** là công cụ tạo khóa từ bí mật đầu vào theo quy tắc đã xác định. KDF giúp **tách mục đích khóa, chuẩn hóa key material và thiết lập khóa phiên**; password-based KDF giúp **tăng chi phí thử đoán mật khẩu**. Hai use case cần cơ chế và chính sách khác nhau: **HKDF** phù hợp cho key material mạnh, còn **Argon2id/scrypt/PBKDF2** hướng đến đầu vào mật khẩu.

Một KDF đúng thuật toán vẫn không đủ nếu root secret bị lộ, salt/info/version bị mất, khóa con dùng sai mục đích hoặc workload được cấp quyền quá rộng. Trong hệ thống Java, phải kết hợp KDF với **CSPRNG, KMS/HSM, DEK/KEK và envelope encryption, IAM, mã hóa có xác thực, rotation, thu hồi, hủy và audit**. **Chọn đúng KDF chỉ là bước đầu; quản lý đúng nguồn bí mật, ngữ cảnh và toàn bộ vòng đời mới giúp khóa dẫn xuất thực sự an toàn.**
