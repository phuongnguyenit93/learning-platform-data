# 7.1. Phân biệt lưu bộ kiểm tra mật khẩu với mã hóa dữ liệu bằng khóa từ mật khẩu

**Mật khẩu có thể tham gia hai bài toán bảo mật rất khác nhau:**

1. **Lưu bộ kiểm tra mật khẩu (password verifier):** hệ thống muốn biết người đăng nhập có đưa ra đúng mật khẩu đã đăng ký hay không. Hệ thống **không cần khôi phục mật khẩu gốc** để làm việc này.
2. **Mã hóa dữ liệu bằng khóa dẫn xuất từ mật khẩu (password-based encryption, PBE):** hệ thống muốn bảo vệ dữ liệu sao cho người có mật khẩu thích hợp **có thể tạo lại khóa giải mã** và lấy lại plaintext.

Hai bài toán thường dùng một hàm dẫn xuất khóa từ mật khẩu, salt và tham số chi phí, nhưng **giá trị đầu ra, cách lưu, vòng đời, hậu quả quên mật khẩu và cơ chế xác minh hoàn toàn khác nhau**. Trộn lẫn chúng dễ dẫn đến những lỗi nghiêm trọng: lưu mật khẩu dưới dạng có thể giải mã, dùng verifier trực tiếp làm khóa mã hóa, tái sử dụng một khóa cho nhiều mục đích, hoặc làm mất khả năng giải mã dữ liệu sau khi đổi mật khẩu.

Bài này tập trung vào **phân biệt và kết nối đúng hai mô hình**, không tự thiết kế thuật toán mật mã mới. Sau khi học, bạn có thể:

- Giải thích password verifier, password hashing, password-based key derivation, encryption key và authentication tag bằng đúng vai trò của chúng.
- Thiết kế hồ sơ lưu verifier có salt, thuật toán, tham số chi phí và kết quả dẫn xuất; xác minh mật khẩu nhập lại mà không cần lưu plaintext.
- Thiết kế envelope lưu dữ liệu mã hóa có KDF salt, nonce/IV, ciphertext và authentication tag; khôi phục dữ liệu bằng mật khẩu và kiểm tra toàn vẹn.
- Phân biệt **salt của KDF**, **nonce của AEAD**, **pepper**, **master key/DEK**, và lý do chúng không thể thay thế nhau.
- Nhận diện rủi ro tấn công đoán mật khẩu ngoại tuyến, đổi/reset mật khẩu, mất khóa, replay, format/version, và triển khai Java 17+ với API tiêu chuẩn.

## 1. Đặt đúng câu hỏi: “xác minh bí mật” hay “khôi phục dữ liệu”?

Hãy xét cùng một người dùng đặt mật khẩu `p`, nhưng hai hệ thống dùng nó theo hai mục đích:

**Hệ thống A — đăng nhập:** ứng dụng chỉ cần trả lời *mật khẩu vừa nhập có phù hợp với tài khoản không?* Khi đăng ký, hệ thống tính một bộ kiểm tra từ mật khẩu và lưu bộ kiểm tra đó. Khi đăng nhập, nó tính lại theo cùng quy tắc và so sánh. Hệ thống không có bước “giải mã password verifier”.

**Hệ thống B — mở két dữ liệu:** người dùng có một tài liệu đã mã hóa. Muốn lấy lại nội dung, hệ thống phải tái tạo đúng khóa (hoặc khóa dùng mở khóa dữ liệu), giải mã ciphertext và **xác minh authentication tag**. Nếu quên mật khẩu và không có một phương án recovery khác, dữ liệu có thể mất khả năng truy cập vĩnh viễn.

| Câu hỏi | Lưu password verifier | Mã hóa dữ liệu với khóa từ mật khẩu |
| --- | --- | --- |
| Mục tiêu | **Xác thực mật khẩu** đã đăng ký | **Giữ bí mật và khôi phục plaintext** |
| Đầu vào nhạy cảm | Password người dùng cung cấp | Password/secret dùng để mở dữ liệu |
| KDF/password hashing | Tạo bộ kiểm tra khó đoán offline | Dẫn xuất khóa mã hóa hoặc key-encryption key |
| Thứ được lưu | Salt, thuật toán, tham số, verifier | Salt KDF, tham số, nonce, ciphertext, tag; có thể wrapped DEK |
| Có lưu mật khẩu gốc? | Không | Không |
| Có cần giải mã verifier? | Không, chỉ tính lại và so sánh | Không; phải giải mã **ciphertext** bằng khóa dẫn xuất |
| Kết quả khi nhập đúng | Login được chấp nhận **sau các kiểm tra khác** | Plaintext được giải mã và tag hợp lệ |
| Kết quả khi nhập sai | Verifier không khớp | Không tạo được khóa đúng; AEAD tag thường không hợp lệ |
| Quên mật khẩu | Có thể tạo lại verifier bằng quy trình reset đã xác thực | Không thể tự khôi phục dữ liệu cũ nếu không có khóa/recovery path |
| Lộ database | Verifier có thể bị đoán mật khẩu offline | Ciphertext có thể bị đoán password offline để thử giải mã |
| Bảo vệ chính | Password hashing có chi phí phù hợp + chống tấn công online | KDF phù hợp + AEAD + quản lý khóa + chiến lược recovery |
| Danh tính/quyền | Phải kết hợp account identity, rate limiting, MFA, authorization | Cần kiểm soát quyền truy cập ciphertext, đúng chủ sở hữu dữ liệu |

**Mật khẩu không phải sẵn một khóa AES.** Mật khẩu do người dùng nhớ thường ít entropy, có độ dài/encoding bất kỳ. Không được `new SecretKeySpec(password.getBytes(UTF_8), "AES")` rồi xem đó là thiết kế an toàn. Cần một cơ chế chuyên dụng để xử lý password, salt, tham số chi phí và mục đích sử dụng.

## 2. Lưu bộ kiểm tra mật khẩu: Password hashing

### 2.1. Luồng đăng ký và đăng nhập

Ký hiệu:

- `P`: mật khẩu gốc do người dùng nhập.
- `S_v`: salt ngẫu nhiên riêng cho một verifier.
- `params_v`: thuật toán/phiên bản và chi phí tính toán.
- `V = PasswordHash(P, S_v, params_v)`: bộ kiểm tra được lưu.

```text
Đăng ký / đổi mật khẩu hợp lệ              Đăng nhập
-----------------------------              ----------------------------
Password P nhập qua kênh an toàn            Password P' vừa nhập
             |                                         |
    Sinh salt S_v ngẫu nhiên                      Đọc record người dùng
             |                                  (salt, params, verifier)
 PasswordHash(P, S_v, params_v)                        |
             |                              PasswordHash(P', S_v, params_v)
             v                                         |
 Lưu: algorithm, params, salt, verifier                v
 Không lưu password P                      So sánh verifier theo API an toàn
                                                       |
                                               Trùng -> qua bước xác thực mật khẩu
                                               Sai   -> từ chối
```

Đối với mật khẩu, nên chọn **password-hashing/KDF có chi phí điều chỉnh được**, ví dụ **Argon2id** qua thư viện được thẩm định (thường ưu tiên khi chính sách cho phép), hoặc **scrypt/bcrypt/PBKDF2** tùy yêu cầu tương thích và quy định. Argon2id có khả năng yêu cầu chi phí bộ nhớ; PBKDF2 dùng nhiều lượt tính toán và phổ biến trong môi trường yêu cầu tương thích/FIPS. Không chọn `SHA-256(password)` trực tiếp, vì nó quá nhanh để chống tấn công thử nhiều mật khẩu.

Trong Java 17, JCA/JCE có `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")`. Đây là ví dụ **tương thích với thư viện chuẩn**, không có nghĩa PBKDF2 luôn là lựa chọn tối ưu hơn Argon2id trong mọi hệ thống. Argon2id cần một implementation thư viện bảo mật phù hợp; không tự lập trình Argon2 từ đầu.

### 2.2. Record password verifier chứa những gì?

Mẫu logic:

```json
{
  "accountId": "user-42",
  "passwordVerifier": {
    "scheme": "PBKDF2WithHmacSHA256",
    "iterations": 600000,
    "salt": "base64-of-random-salt",
    "derivedVerifier": "base64-of-derived-bytes"
  }
}
```

Các giá trị `base64-of-...` minh họa vị trí dữ liệu nhị phân, **không phải record hợp lệ dùng ngay**. Trong production, định dạng có thể là chuỗi PHC hoặc một object được version hóa tùy scheme.

- **Salt:** mỗi bản ghi có salt độc lập do CSPRNG sinh, thông thường 16 byte hoặc hơn. Salt **không cần giữ bí mật**; cùng một password nhưng salt khác sẽ tạo verifier khác.
- **Cost:** iterations/memory/time/parallelism (tùy thuật toán) được lưu để hệ thống biết cách kiểm tra và có kế hoạch nâng cấp. Cần chọn theo khuyến nghị hiện hành, benchmark trên phần cứng triển khai và kiểm soát tải DoS.
- **Verifier:** kết quả được lưu để đối chiếu; không nên dùng nó như mật khẩu, API token, AES key hoặc bí mật phải gửi lại client.
- **Pepper (tùy thiết kế):** bí mật cấp hệ thống được giữ riêng khỏi database, ví dụ trong vault/HSM, có thể bổ sung bảo vệ khi database chỉ bị lộ. Pepper **không thay thế** salt hoặc password hashing; phải có chính sách rotation/recovery riêng.

Nếu hệ thống dùng một thư viện có định dạng password-hash chuẩn, hãy để thư viện quản lý record, verify, phiên bản và upgrade nếu phù hợp. Đừng viết parser tự chế dễ chấp nhận tham số quá lớn, giá trị malformed hoặc thuật toán yếu. Việc lưu verifier riêng cho từng user không tự kiểm soát việc ai được phép đặt lại mật khẩu.

### 2.3. Vì sao verifier “một chiều” vẫn có thể bị đoán?

Hàm password-hashing không phải phép biến đổi bất khả đảo về mặt tuyệt đối. Khi đối thủ lấy được `S_v`, `params_v` và `V`, họ có thể chọn ứng viên `P_i`, tính `PasswordHash(P_i, S_v, params_v)` rồi so sánh với `V`. Đây là **offline guessing**; mật khẩu yếu vẫn có thể bị tìm ra.

Năng lực bảo vệ đến từ **chi phí mỗi lần đoán**, salt riêng và độ mạnh mật khẩu thực tế, cộng với việc giảm quyền đọc dữ liệu và bảo vệ pepper khi dùng. Với tấn công **online** qua màn hình login, còn cần rate limiting, giám sát, khóa/ràng buộc phiên phù hợp, MFA và phản hồi không tiết lộ tài khoản có tồn tại hay không. KDF chậm một mình không hạn chế vô số request online.

Một ví dụ rất dễ nhầm:

```text
Password = "123456"
Salt random 128-bit
Verifier = PBKDF2(password, salt, cost)
```

Salt tốt khiến record của người khác không có cùng verifier, nhưng không biến `123456` thành một mật khẩu entropy cao. Kẻ có record vẫn có thể thử `123456` trong tập đoán của họ.

### 2.4. Chức năng reset password

Khi người dùng quên mật khẩu đăng nhập, ứng dụng có thể dùng quy trình khôi phục tài khoản đã xác thực để **thay bộ kiểm tra**:

```text
User proves recovery identity
        -> authorize password reset
        -> set NEW password
        -> generate NEW verifier salt
        -> store NEW verifier/params
        -> revoke sessions/tokens as policy requires
```

Ứng dụng không cần biết lại mật khẩu cũ. Đây là lợi ích thiết kế của verifier: **chỉ cần xác minh đúng/sai**, không cần bí mật cũ để tạo record mới.

Tuy nhiên, thay verifier **không tự đổi** dữ liệu đã mã hóa bằng khóa từ mật khẩu cũ. Đây là ranh giới quan trọng tiếp theo.

## 3. Mã hóa dữ liệu: Dẫn xuất khóa từ mật khẩu rồi dùng AEAD

Mô hình đơn giản hóa:

\[
K_e = KDF(P, S_e, params_e)
\]

\[
(C,T) = AEAD.Encrypt(K_e, nonce, plaintext, AAD)
\]

Bên giải mã phải có `P`, `S_e` và `params_e` để tái tạo đúng `K_e`, rồi đưa `C`, `T`, `nonce` và `AAD` vào AEAD decryption. **Chỉ chấp nhận plaintext sau khi tag xác thực thành công.**

```text
MÃ HÓA DỮ LIỆU                                    GIẢI MÃ DỮ LIỆU
----------------                                    ----------------
Password P                                          Password P'
   +-- KDF salt S_e / params_e                         +-- Đọc S_e / params_e
   |                                                       |
   +----> KDF --------> Encryption key K_e                 +----> KDF ---> K'_e
                             |                                             |
Plaintext -----> AES-GCM(K_e, fresh nonce, AAD)     Ciphertext+tag --> AES-GCM decrypt
                             |                                             |
         Lưu envelope (salt, params, nonce,          Auth tag đúng và metadata đúng?
         ciphertext, tag, version...)                    /              \
                                                       Đúng             Sai
                                                        |                |
                                                    Plaintext           Reject
```

Nên dùng một AEAD chuẩn như **AES-GCM** hoặc ChaCha20-Poly1305 theo thư viện và chính sách triển khai. AES-GCM cung cấp bí mật cho plaintext và kiểm tra tính toàn vẹn của ciphertext/AAD qua tag. Nếu giải mã trả `AEADBadTagException`, có thể do mật khẩu/khóa sai, nonce/AAD sai hoặc ciphertext/tag bị sửa: ứng dụng thường **không thể kết luận chắc chắn riêng nguyên nhân nào** chỉ từ exception đó.

### 3.1. Những gì phải lưu để có thể mở lại ciphertext

Một envelope minh họa (mang tính mô tả schema, không phải chuẩn wire chính thức):

```json
{
  "formatVersion": 1,
  "kdf": {
    "name": "PBKDF2WithHmacSHA256",
    "iterations": 600000,
    "saltBase64": "base64-of-independent-16-byte-salt",
    "outputBits": 256
  },
  "encryption": {
    "name": "AES-256-GCM",
    "nonceBase64": "base64-of-12-byte-nonce",
    "ciphertextAndTagBase64": "base64-of-ciphertext-and-16-byte-tag"
  }
}
```

Trong Java `Cipher.doFinal` với AES-GCM thường trả ciphertext kèm tag trong cùng mảng; định dạng trao đổi phải **quy định cụ thể** tag đặt ở đâu, độ dài bao nhiêu và encoding nào. Không được tùy tiện cắt/bỏ tag.

Thông tin như thuật toán, salt, tham số và nonce **không nhất thiết bí mật**. Tính an toàn dựa vào password có đủ entropy, KDF không dễ đoán quá nhanh, khóa đúng và xác thực dữ liệu đúng. **Bắt buộc giữ metadata cần để giải mã**: mất salt/nonce/format có thể khiến không thể mở lại ciphertext dù vẫn nhớ đúng password.

Một envelope do nguồn không tin cậy cung cấp không được tự động điều khiển thuật toán hoặc chi phí tính toán không giới hạn. Reader phải dùng allowlist phiên bản/thuật toán, kiểm tra kích thước/trường bắt buộc, giới hạn iteration và payload, và ràng buộc metadata an ninh trong AAD/format được xác thực khi phù hợp.

### 3.2. Salt của KDF không phải nonce của AES-GCM

| Giá trị | Dùng tại đâu? | Yêu cầu then chốt | Có thể công khai? |
| --- | --- | --- | --- |
| `S_v` — salt verifier | Password hashing để lưu bộ kiểm tra | Ngẫu nhiên, riêng cho verifier | Có |
| `S_e` — salt encryption KDF | Dẫn xuất khóa từ password cho dữ liệu | Tách biệt mục đích; lưu để dẫn xuất lại | Có |
| `nonce/IV` của GCM | Một lần mã hóa bằng khóa AEAD | **Không được dùng lại cùng (khóa, nonce)** | Có |
| `AAD` | AEAD trước khi mã hóa/giải mã | Cùng byte/ngữ cảnh ở hai phía; được kiểm tra toàn vẹn | Có |
| `authentication tag` | AEAD xác nhận ciphertext/AAD | Kiểm tra trước khi dùng plaintext | Có |
| `pepper` nếu có | Bảo vệ thêm credential/server policy | Bí mật, lưu riêng database | Không |
| `K_e` — encryption key | AES-GCM hoặc key wrap | Bí mật; đúng scope, vòng đời và bảo vệ | Không |

Salt được sinh lại khi tạo **một key derivation context mới**; nonce được sinh/cấp **cho mỗi lần mã hóa với cùng key** theo quy tắc mode. Không được lấy salt rồi dùng luôn làm nonce chỉ vì cả hai đều là byte ngẫu nhiên.

Nếu muốn mã hóa nhiều thông điệp bằng cùng password và salt (tức cùng khóa), phải quản lý **nonce duy nhất với khóa** và giới hạn số bản tin theo khuyến nghị của AEAD; hệ thống có nhiều instance cần cơ chế tránh collision. Nếu thiết kế luôn sinh salt mới cho mỗi envelope, khóa dẫn xuất thường khác; vẫn phải tạo nonce theo đúng yêu cầu của thuật toán và không được giả định salt luôn bảo đảm mọi thuộc tính của nonce.

### 3.3. “Có mật khẩu là giải mã được” chỉ đúng trong phạm vi nào?

Phải phân biệt **access control** với **cryptographic confidentiality**:

- Nếu server tự nắm khóa giải mã dữ liệu (KMS/DEK) và chỉ dùng password verifier để cấp quyền truy cập, **server vẫn có thể giải mã mà không cần password người dùng** theo chính sách.
- Nếu dữ liệu thực sự được mã hóa bằng khóa chỉ người dùng có thể tái tạo, thì server muốn giải mã cần password hoặc một khóa/recovery path có quyền tương đương.
- Nếu ứng dụng gửi password qua backend để derive key, backend có thể nhìn thấy password tại thời điểm xử lý. Không tuyên bố “zero knowledge” chỉ vì mật khẩu không được lưu vào database.
- Nếu chọn client-side encryption, cần xem xét nơi password đi qua, thiết bị nào giữ key, cách chia sẻ và phục hồi, cách lưu dữ liệu ở server.

Không có một mô hình mặc định nào vừa cho phép server đọc mọi dữ liệu vừa bảo đảm server không bao giờ có quyền giải mã. Cần ghi rõ **ai được tin cậy để sở hữu plaintext/key** trong threat model.

## 4. Vì sao không dùng cùng verifier làm khóa mã hóa?

Một thiết kế sai phổ biến:

```text
storedVerifier = PBKDF2(password, salt, cost)
encryptionKey  = storedVerifier
ciphertext     = AES-GCM(encryptionKey, data)
```

Nếu attacker đọc được database chứa `storedVerifier`, họ đã có **chính khóa mã hóa**, không cần biết password. Mục đích password verifier bị đảo ngược: bộ kiểm tra mật khẩu vốn phải có thể lưu để kiểm tra, không được đồng thời trở thành bí mật mở dữ liệu.

Một thiết kế sai khác là lấy `SHA-256(password)` làm verifier và AES key, rồi dùng cùng khóa cho HMAC, cookie signing và mã hóa. Việc tái sử dụng làm tăng phạm vi thiệt hại khi một giá trị bị lộ, gây nhầm vai trò khóa và khó xoay/thu hồi.

**Nguyên tắc:** tách **credential-verification material** khỏi **encryption key material**. Hai mục đích có thể cùng xuất phát từ một password nếu threat model cho phép, nhưng phải dùng **salt, tham số và ngữ cảnh dẫn xuất độc lập**, không bao giờ tái sử dụng giá trị verifier có thể đọc được làm key.

Một cách trình bày:

```text
                         Password P
                        /          \
           verifier purpose        encryption purpose
             salt S_v                  salt S_e
            cost_v                    cost_e
               |                        |
          PasswordHash               Password KDF
               |                        |
          Stored verifier            Secret K_e
           (can be stored)           (not stored as public verifier)
               |                        |
          Compare at login          AES-GCM / wrap DEK
```

Nhiều hệ thống còn không nên dùng password đăng nhập làm password mã hóa dữ liệu. Có thể sử dụng một khóa dữ liệu ngẫu nhiên được quản lý độc lập (KMS/HSM), hoặc một passphrase riêng cho encryption, tùy mục tiêu an ninh và usability.

## 5. Mô hình tốt hơn cho dữ liệu dài hạn: DEK và KEK

Để tránh mã hóa lại toàn bộ dữ liệu khi thay password, thường dùng **envelope encryption**:

- **DEK (Data Encryption Key):** khóa ngẫu nhiên đủ mạnh, sinh độc lập với password; dùng AEAD mã hóa dữ liệu.
- **KEK (Key Encryption Key):** khóa dẫn xuất từ password bằng password KDF, hoặc do hệ thống KMS cấp; dùng **wrap/mã hóa DEK** bằng một cơ chế xác thực.
- **Wrapped DEK:** DEK đã được mã hóa bảo vệ bằng KEK; lưu cùng metadata cho phép unwrap an toàn.

```text
Random DEK ────────────────> AEAD encrypt data ──> ciphertext + data nonce/tag
    |
    +-- AEAD wrap using KEK <──── KDF(password, independent salt, params)
                         |
                   wrappedDEK + wrap nonce/tag + KDF metadata

Open data:
password -> KDF -> KEK -> verify/unwrap DEK -> verify/decrypt ciphertext
```

Khi người dùng **biết cả password cũ và password mới**, ứng dụng có thể dùng password cũ unwrap DEK, sinh KEK mới từ password mới với salt mới, rồi **rewrap đúng DEK**. Ciphertext dữ liệu lớn có thể giữ nguyên nếu DEK không đổi. Cần bảo đảm thao tác update nguyên tử, metadata/version nhất quán và key không bị lộ.

Điểm này không có nghĩa password reset không biết mật khẩu cũ cũng làm được như vậy. Nếu **không còn password cũ hoặc recovery key**, không thể tạo lại KEK cũ để unwrap DEK chỉ từ verifier và ciphertext.

### 5.1. Đổi mật khẩu và reset mật khẩu không giống nhau

| Sự kiện | Verifier đăng nhập | Dữ liệu trực tiếp mã hóa từ password | Dữ liệu qua DEK/KEK |
| --- | --- | --- | --- |
| Đổi mật khẩu, biết password cũ | Tạo verifier mới | Phải giải mã bằng khóa cũ rồi mã hóa lại bằng khóa mới | Unwrap DEK bằng KEK cũ, rewrap bằng KEK mới |
| Quên password cũ, chỉ có quyền reset account | Có thể thay verifier sau quy trình recovery | **Không thể tự giải mã dữ liệu cũ** nếu không có recovery | Không unwrap được DEK nếu không có recovery path |
| Có recovery key được cấp trước | Reset verifier theo chính sách | Có thể giải mã nếu recovery key thực sự có đường mở dữ liệu | Có thể unwrap/rewrap DEK bằng recovery key/wrapped copy |
| Server giữ DEK trong KMS | Reset verifier độc lập | Phụ thuộc kiến trúc | Server có thể rewrap theo quyền KMS, nhưng không còn mô hình chỉ người dùng biết key |

**Reset account thành công không đồng nghĩa với khôi phục được dữ liệu mã hóa**. UX của sản phẩm cần thông báo rõ trước khi người dùng dựa vào password-only encryption. Nếu có recovery key, escrow, hoặc tổ chức có quyền khôi phục, phải nói rõ ai nắm quyền tương đương giải mã.

## 6. Java 17+: thực hiện cả hai luồng một cách tách biệt

Ví dụ sau sử dụng đúng **các API có sẵn trong Java 17+**:

- `SecretKeyFactory` + `PBEKeySpec` với `PBKDF2WithHmacSHA256` làm KDF có salt và chi phí.
- `SecureRandom` để tạo salt và nonce.
- `MessageDigest.isEqual` để so sánh verifier đã dẫn xuất.
- `Cipher` `AES/GCM/NoPadding` để mã hóa xác thực và kiểm tra tag trước khi lấy plaintext.
- **Hai salt độc lập:** một cho password verifier, một cho khóa mã hóa.

Đây là bản minh họa **PBKDF2 dùng để quan sát hai mục đích**. Với hệ thống thiết kế mới, hãy đánh giá Argon2id qua thư viện được kiểm toán và quy định hiện hành; không suy ra con số iteration trong demo là tham số an toàn vĩnh viễn. Mật khẩu trong code là dữ liệu demo công khai, **không phải secret để tái sử dụng**.

Tệp `PasswordVerifierVsEncryptionDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

public class PasswordVerifierVsEncryptionDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int ITERATIONS = 600_000;
    private static final byte[] CONTEXT =
            "private-note:v1".getBytes(StandardCharsets.UTF_8);

    static byte[] randomBytes(int length) {
        byte[] bytes = new byte[length];
        RANDOM.nextBytes(bytes);
        return bytes;
    }

    static byte[] derive(char[] password, byte[] salt) throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, ITERATIONS, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static boolean verify(char[] candidate, byte[] salt, byte[] storedVerifier)
            throws Exception {
        byte[] calculated = derive(candidate, salt);
        try {
            return MessageDigest.isEqual(storedVerifier, calculated);
        } finally {
            Arrays.fill(calculated, (byte) 0);
        }
    }

    static byte[] encrypt(char[] password, byte[] salt, byte[] nonce, byte[] plaintext)
            throws Exception {
        byte[] derivedKey = derive(password, salt);
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(derivedKey, "AES"),
                    new GCMParameterSpec(128, nonce));
            cipher.updateAAD(CONTEXT);
            return cipher.doFinal(plaintext);
        } finally {
            Arrays.fill(derivedKey, (byte) 0);
        }
    }

    static byte[] decrypt(char[] password, byte[] salt, byte[] nonce, byte[] ciphertext)
            throws Exception {
        byte[] derivedKey = derive(password, salt);
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(derivedKey, "AES"),
                    new GCMParameterSpec(128, nonce));
            cipher.updateAAD(CONTEXT);
            return cipher.doFinal(ciphertext);
        } finally {
            Arrays.fill(derivedKey, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "example demo password".toCharArray();
        char[] incorrect = "incorrect".toCharArray();

        // Mục đích A: lưu verifier; không cần giải mã mật khẩu.
        byte[] verifierSalt = randomBytes(16);
        byte[] storedVerifier = derive(password, verifierSalt);
        System.out.println("Correct login: "
                + verify(password, verifierSalt, storedVerifier));
        System.out.println("Wrong login: "
                + verify(incorrect, verifierSalt, storedVerifier));

        // Mục đích B: mã hóa rồi khôi phục plaintext với password.
        // Salt này độc lập với verifierSalt.
        byte[] fileSalt = randomBytes(16);
        byte[] nonce = randomBytes(12);
        byte[] ciphertext = encrypt(password, fileSalt, nonce,
                "Confidential note".getBytes(StandardCharsets.UTF_8));
        byte[] recovered = decrypt(password, fileSalt, nonce, ciphertext);
        System.out.println("Decrypted: " + new String(recovered, StandardCharsets.UTF_8));

        boolean wrongPasswordRejected = false;
        try {
            decrypt(incorrect, fileSalt, nonce, ciphertext);
        } catch (AEADBadTagException expected) {
            wrongPasswordRejected = true;
        }
        System.out.println("Wrong decryption password rejected: "
                + wrongPasswordRejected);

        byte[] tampered = ciphertext.clone();
        tampered[0] ^= 1;
        boolean tamperingRejected = false;
        try {
            decrypt(password, fileSalt, nonce, tampered);
        } catch (AEADBadTagException expected) {
            tamperingRejected = true;
        }
        System.out.println("Tampering rejected: " + tamperingRejected);

        Arrays.fill(password, '\0');
        Arrays.fill(incorrect, '\0');
        Arrays.fill(storedVerifier, (byte) 0);
    }
}
```

Biên dịch và chạy:

```bash
javac PasswordVerifierVsEncryptionDemo.java
java PasswordVerifierVsEncryptionDemo
```

**Stdout** (các salt, nonce và ciphertext được sinh ngẫu nhiên nhưng không in ra, nên các dòng kết quả vẫn như nhau):

```text
Correct login: true
Wrong login: false
Decrypted: Confidential note
Wrong decryption password rejected: true
Tampering rejected: true
```

### 6.1. Giải thích chi tiết từng phần

**Phần verifier:**

```java
byte[] verifierSalt = randomBytes(16);
byte[] storedVerifier = derive(password, verifierSalt);
boolean ok = verify(password, verifierSalt, storedVerifier);
```

`storedVerifier` là giá trị **dùng để so sánh khi xác thực**. Nếu lưu vào database, phải lưu kèm `verifierSalt`, `ITERATIONS` và id KDF. Dữ liệu cần giữ bí mật trong quá trình xử lý là password; record verifier/salt không được xem là tài liệu cho phép giải mã, nhưng vẫn là dữ liệu bảo mật nhạy cảm vì có thể hỗ trợ tấn công offline.

**Phần encryption:**

```java
byte[] fileSalt = randomBytes(16);
byte[] nonce = randomBytes(12);
byte[] ciphertext = encrypt(password, fileSalt, nonce, plaintext);
byte[] restored = decrypt(password, fileSalt, nonce, ciphertext);
```

Trong thực tế phải lưu ít nhất `fileSalt`, nonce, ciphertext kèm tag, profile version/KDF params và ngữ cảnh AAD cần thiết. Demo dùng AAD cố định `private-note:v1` để ràng buộc **kiểu dữ liệu/phiên bản**; khi thiết kế đa người dùng/tệp, nên ràng buộc cả id/tenant/resource với AAD theo schema rõ ràng và kiểm tra quyền tương ứng.

**Tại sao cùng password có thể cho ra hai giá trị KDF khác nhau?** `verifierSalt` và `fileSalt` được tạo độc lập. Ngay cả khi tình cờ cùng password, dữ liệu đầu vào KDF khác nên thường tạo kết quả khác. Trong thiết kế nâng cao nên có **domain separation** rành mạch cho verifier và encryption, chứ không chỉ trông chờ các call site dùng nhầm hay không. Với password hashing và password-based encryption, cũng có thể dùng các thuật toán/profile khác nhau.

**Xử lý sai password và dữ liệu bị sửa:** AEAD khi kiểm tra tag không khớp sẽ từ chối. Hệ thống không nên đưa plaintext được trả từ hoạt động chưa xác thực vào nghiệp vụ. Ngoài sai password, nguyên nhân tag sai còn có thể do dữ liệu, metadata, nonce hay AAD bị thay đổi. Không dùng ngoại lệ để tiết lộ cho client rằng phần nào của ciphertext đã bị chỉnh sửa.

### 6.2. Những giới hạn cố ý của demo

- Mật khẩu được viết trực tiếp trong source chỉ nhằm chạy lại bài; ứng dụng thật cần nhận qua kênh an toàn, không log và không hardcode.
- `PBKDF2WithHmacSHA256` với 600.000 lượt là **giá trị minh họa**, chưa thay thế benchmark/kế hoạch tham số hiện hành theo môi trường và chính sách. Thời gian chạy phụ thuộc CPU, quy mô dịch vụ và giới hạn DoS.
- `derive()` dùng một profile cố định, không serialize metadata. Sản phẩm thật phải lưu/version hóa thuật toán, cost, salt, nonce, AAD policy và ciphertext; áp kiểm tra input size và giới hạn cost khi đọc file từ bên ngoài.
- Mỗi lần mã hóa của demo sinh salt/nonce mới. Khi tái sử dụng một khóa dẫn xuất cho nhiều bản tin, phải có cơ chế cấp nonce duy nhất phù hợp với mode và quy mô lưu lượng. Việc AES-GCM nonce không được tái sử dụng với cùng khóa là yêu cầu riêng, **không được xem như được giải quyết vì có salt ở verifier**.
- Mảng `byte[]` được cố gắng xóa sau khi dùng và `PBEKeySpec.clearPassword()` được gọi; điều này **không bảo đảm tuyệt đối** mọi bản copy bên trong JCE/JVM được xóa ngay. Tránh tạo nhiều bản sao `String` của password trong code production khi có lựa chọn phù hợp.
- `SecretKeySpec` và `Cipher` có thể tạo bản sao key nội bộ; không coi Java heap làm vùng lưu khóa an toàn phần cứng. Với yêu cầu cao, cần xem xét KMS/HSM hoặc key service có chính sách phù hợp.
- Demo mã hóa dữ liệu nhỏ trực tiếp bằng khóa từ password để chỉ ra cơ chế. Dữ liệu dài hạn thường nên dùng **random DEK và KEK** như phần 5 để dễ quản lý key và hỗ trợ rotation.

## 7. So sánh hai cách lưu để tránh nhầm data model

### 7.1. Account credential record

```text
users
  accountId
  credentialVersion
  passwordHashScheme
  passwordHashParameters
  passwordHashSalt
  passwordVerifier
  passwordChangedAt
```

Record này phục vụ **xác thực tài khoản**. Không có `nonce`, `ciphertext` hay `authenticationTag` vì chúng không phải thành phần của password verifier. Một hệ thống có thể lưu verifier dưới dạng chuỗi tự mô tả của thư viện password hash thay vì tách trường; schema lựa chọn phải nhất quán.

Việc có `passwordChangedAt` không tự động tạo quyền truy cập tệp được mã hóa bằng password trước đó. Nếu password thay đổi, logic encryption có kế hoạch chuyển khóa riêng.

### 7.2. Password-encrypted file envelope

```text
encryptedFiles
  ownerId
  fileFormatVersion
  kdfAlgorithm
  kdfCostParameters
  encryptionSalt
  aeadAlgorithm
  nonce
  ciphertextAndTag
  authenticatedContext
```

Record này phục vụ **khôi phục dữ liệu**. `ownerId` và `authenticatedContext` là ngữ cảnh được ràng buộc vào format/AAD khi cần, không đồng nghĩa user đã đăng nhập là có quyền. Phía nhận phải kiểm tra authorization riêng.

Không có password verifier ở đây vẫn có thể giải mã bằng thử password rồi xem tag có đúng không. Trên thực tế, chính authentication tag của ciphertext tạo ra một kiểm tra offline cho mỗi password ứng viên: **encryption không xóa được nguy cơ đoán password nếu password yếu**.

### 7.3. Envelope encryption có wrapped DEK

```text
encryptedFiles
  ownerId
  fileFormatVersion
  dataCiphertextAndTag
  dataNonce
  wrappedDEK
  wrappingAlgorithm
  wrapNonce
  passwordKdfSalt
  passwordKdfCostParameters
  versionedAAD
```

Chủ thể có password/recovery key tương ứng có thể unwrap DEK rồi giải mã dữ liệu. Nếu hỗ trợ nhiều thiết bị hoặc chia sẻ nhiều người, có thể lưu **nhiều wrapped copy của cùng DEK** cho các người nhận hợp lệ, nhưng việc phân phối và thu hồi quyền phải được thiết kế cẩn thận. Thu hồi quyền với dữ liệu đã được người nhận tải/giải mã trước đó không thể đảm bảo chỉ bằng xóa một wrapped key.

## 8. Threat model và những trường hợp phải kiểm thử

### 8.1. Đối thủ chỉ có khả năng thử login online

- **Verifier:** áp rate limit, kiểm soát session, phát hiện credential stuffing, MFA theo nguy cơ, thông báo lỗi phù hợp. Password hashing có chi phí thích hợp nhưng phải có giới hạn tài nguyên để không tạo DoS.
- **Dữ liệu PBE:** nếu có API “thử password để decrypt”, API đó cũng có thể trở thành oracle thử đoán online. Cần giới hạn request và quyền truy cập, không trả thông tin giúp phân biệt lỗi cụ thể quá mức.

### 8.2. Đối thủ lấy được database hoặc file mã hóa

- **Verifier bị lộ:** có thể đoán offline theo `password + salt + cost`. Salt làm bảng tra dùng lại khó hơn; cost tăng công việc; không bảo đảm mật khẩu yếu tránh bị đoán.
- **Ciphertext PBE bị lộ:** có thể đoán offline bằng cách dẫn xuất khóa rồi thử AEAD tag, ngay cả khi không có một trường verifier tường minh.
- **Random DEK được wrap bởi KEK từ password:** nếu file chứa wrapped DEK và tag đủ kiểm tra, đối thủ cũng có thể thử password offline để unwrap. Random DEK giúp quản lý vòng đời, nhưng không tự làm passphrase yếu mạnh lên.

Không nên quảng cáo “ciphertext có AES-256 nên mật khẩu yếu cũng an toàn”. Khóa hiệu dụng từ password phụ thuộc vào **entropy của password**, chi phí KDF và mức độ kẻ tấn công có thể thử.

### 8.3. Đối thủ đọc được verifier lẫn encrypted file

Nếu hệ thống dùng **storedVerifier làm key**, attacker có thể giải mã ngay khi đọc DB. Nếu verifier và encryption material được tách đúng, attacker vẫn phải vượt qua các cơ chế riêng; tuy nhiên nếu cùng password được dùng, việc đoán thành công password từ một trong hai tài sản có thể làm lộ tài sản còn lại. Tốt nhất cân nhắc secret độc lập cho các mục đích hoặc dùng quản lý khóa server/KMS phù hợp threat model.

### 8.4. Password được đổi

Kiểm thử cả:
1. Biết password cũ, đổi password mới: verifier cũ ngừng nhận; encrypted data vẫn mở được theo kế hoạch re-encrypt/rewrap.
2. Reset mà không biết password cũ: login hoạt động, nhưng dữ liệu cũ phải **được báo mất quyền truy cập** hoặc có recovery path đã định; không hứa hẹn tự giải mã được.
3. Rotate KDF parameters: verifier có thể nâng cấp vào lúc login thành công; encrypted file phải được migrate/re-encrypt/rewrap theo quy trình thích hợp, không chỉ sửa metadata iterations rồi mong decrypt vẫn được.
4. Di chuyển môi trường/thư viện: bảo toàn salt, nonce, KDF id, encoding, iterations, tag format, AAD. Cần golden vectors để tránh lỗi interop.

## 9. Checklist thực hành thiết kế

### Khi thiết kế password verifier

- Chọn password-hashing scheme chuyên dụng có thư viện an toàn và chính sách tham số hiện hành; ưu tiên Argon2id khi phù hợp, PBKDF2 khi cần tương thích/FIPS theo chuẩn áp dụng.
- Sinh salt độc lập cho mỗi verifier, lưu salt + algorithm/version + cost + verifier. Không lưu password, không lưu reversible encryption của password.
- Thực hiện verification qua API chuyên dụng hoặc so sánh byte phù hợp sau khi dẫn xuất cùng tham số. Giới hạn đầu vào và chi phí, không cho dữ liệu client tùy ý chọn thuật toán yếu.
- Áp chính sách đăng nhập: rate limiting, MFA, bảo vệ reset token, session revocation, audit và kiểm tra danh tính/quyền.
- Có chiến lược rehash/upgrade sau khi người dùng login thành công, lưu ý migration không phá tài khoản.

### Khi thiết kế password-based encryption

- Xác định ai thực sự cần giải mã, ở đâu password xuất hiện, ai sở hữu key, có cần server/recovery access không.
- Chọn password KDF và cost phù hợp, salt ngẫu nhiên riêng cho encryption context. Dẫn xuất key length đúng yêu cầu thuật toán (ví dụ AES-256 cần 32 byte key).
- Mã hóa bằng AEAD đã được kiểm chứng, nonce duy nhất theo khóa; bảo vệ metadata/context trong AAD và kiểm tra tag trước khi dùng plaintext.
- Lưu tất cả tham số cần để giải mã (salt, KDF id/cost, nonce, ciphertext, tag, version), kiểm tra file/envelope format có giới hạn và policy.
- Nếu dữ liệu dài hạn/nhiều file, cân nhắc random DEK với KEK được dẫn xuất từ password, thiết kế rewrap và recovery trước khi sản phẩm có người dùng.
- Quy định rõ quá trình đổi/reset password, quên password, mất metadata/backup, rotate key, chia sẻ và thu hồi truy cập.
- Không lưu verifier như encryption key; không dùng password bytes trực tiếp làm AES key; không dùng `AES/ECB/PKCS5Padding` hay mã hóa không xác thực cho dữ liệu cần bảo vệ khỏi sửa đổi.

## 10. Những ngộ nhận nguy hiểm

| Nhận định sai | Thực tế |
| --- | --- |
| “Đã hash password thì muốn cũng decrypt được” | Password verifier không có phép giải mã khôi phục password; chỉ có thể thử đoán |
| “Muốn đọc lại password để login nên phải mã hóa password” | Login chỉ cần verify, không cần đọc lại password; không lưu reversible password |
| “Verifier PBKDF2 là 256 bit, dùng làm AES-256 key luôn” | Nếu DB lộ verifier thì attacker có ngay key; phải tách mục đích/secret |
| “Salt là bí mật, nên phải giấu cùng với key” | Salt thường công khai; bí mật thực sự là password/secret và key |
| “Salt mới nghĩa là không cần nonce GCM” | Nonce là tham số AEAD có quy tắc duy nhất theo key, khác vai trò KDF salt |
| “AES-GCM sai password sẽ cho ra rác, mình tự kiểm tra UTF-8 là đủ” | Phải xác minh tag; AEAD fail thì từ chối, không xử lý plaintext |
| “Mã hóa bằng password nên quên password có thể gửi email reset là đọc lại dữ liệu” | Reset verifier không khôi phục KEK/DEK cũ nếu không có recovery path |
| “Hash/password KDF tăng entropy của password” | KDF chỉ tăng chi phí mỗi lần thử; entropy đầu vào không tăng |
| “Pepper thay thế salt và password hashing” | Pepper là lớp bổ sung với vòng đời riêng, không thay salt/hash |
| “Lộ ciphertext thì an toàn tuyệt đối vì dùng AES-256” | Đối thủ có thể đoán password offline rồi kiểm tra tag nếu password yếu |
| “Đổi iterations trong envelope là đủ để migrate” | KDF output thay đổi; phải re-encrypt hoặc rewrap theo quy trình |
| “Dùng cùng password thì verifier và encryption bắt buộc cùng salt/key” | Phải tách context và key, có thể dùng salt riêng hoặc secret riêng |
| “Java `String` xóa password khỏi RAM khi đặt null” | Memory management có thể giữ bản sao; dùng API phù hợp, tránh log và giảm thời gian tồn tại của secret |
| “Password đúng là đủ quyền xem mọi file” | Xác thực không thay authorization đối với owner, tenant, resource |

## 11. Bài tập tự kiểm tra

**Câu 1.** Hệ thống chỉ cần xác định password login có đúng không. Nên lưu gì?

**Trả lời:** Lưu **password verifier** do password-hashing scheme tạo ra, kèm salt, cost, version/algorithm. Không cần lưu password hay dữ liệu mã hóa để có thể “giải mã password”.

**Câu 2.** Một người có file đã mã hóa bằng khóa dẫn xuất từ password. Tại sao họ cần lưu salt và nonce?

**Trả lời:** Salt KDF là input để tái tạo đúng key; nonce là input AEAD để giải mã/verify tag. Mất metadata cần thiết có thể khiến không mở lại file dù password đúng.

**Câu 3.** Nếu `storedVerifier = PBKDF2(password, salt)`, có nên làm `AES-GCM(storedVerifier, data)` không?

**Trả lời:** Không. Verifier được lưu nhằm xác minh và có thể lộ khi database bị rò rỉ; nếu cũng dùng làm key, attacker đọc verifier có thể giải mã trực tiếp. Dùng key material riêng và quản lý đúng scope.

**Câu 4.** Vì sao PBE có thể bị tấn công đoán password offline dù không lưu verifier?

**Trả lời:** Đối thủ có salt, params, nonce, ciphertext+tag có thể thử password ứng viên, derive key, rồi xác minh AEAD tag. Password yếu có thể bị đoán; KDF chậm làm tăng chi phí nhưng không xóa bỏ khả năng thử.

**Câu 5.** Người dùng quên password đăng nhập nhưng chứng minh được quyền tài khoản qua recovery email. Có thể reset login không? Có luôn đọc được file mã hóa bằng password cũ không?

**Trả lời:** Có thể reset verifier theo quy trình tài khoản; không tự giải mã file cũ nếu không có password cũ, DEK escrow/recovery key hoặc đường khôi phục khác đã thiết kế trước.

**Câu 6.** Tại sao đổi password với KEK/DEK có thể tiết kiệm hơn mã hóa trực tiếp?

**Trả lời:** Có thể unwrap một DEK ngẫu nhiên bằng KEK cũ rồi rewrap bằng KEK mới, giữ nguyên ciphertext dữ liệu lớn. Nhưng thao tác vẫn cần quyền truy cập DEK qua password cũ hoặc recovery path.

**Câu 7.** Trong ví dụ Java, tại sao sai password hoặc sửa byte ciphertext đều cho `AEADBadTagException`?

**Trả lời:** Cả hai có thể khiến tag không hợp lệ; AEAD chỉ xác nhận input/khóa/nonce/AAD tương thích với tag hoặc từ chối, không phân loại nguyên nhân một cách đáng tin cho ứng dụng.

**Câu 8.** Mã hóa dữ liệu dưới KMS server-controlled và lưu password verifier cho login có phải mô hình password-only encryption không?

**Trả lời:** Không. Server có thể mở data qua KMS mà không cần biết password người dùng; password chỉ là một phương tiện xác thực quyền truy cập, không phải secret duy nhất giải mã data.

## 12. Ghi nhớ ranh giới kiến trúc

```text
                    PASSWORD
                       |
           +-----------+-------------+
           |                         |
       XÁC THỰC                   MỞ DỮ LIỆU
           |                         |
  Password hashing              Password KDF
  + verifier salt               + encryption salt
  + cost parameters             + cost parameters
           |                         |
      STORE VERIFIER              SECRET KEK/KEY
      (cannot decrypt)                 |
           |                     AEAD / unwrap DEK
      COMPARE AT LOGIN                 |
           |                      CIPHERTEXT
      AUTHENTICATION                   |
           |                      RECOVER PLAINTEXT
   then AUTHORIZATION               verify tag
```

**Password verifier trả lời “mật khẩu này có đúng không?”; password-derived encryption key trả lời “với mật khẩu này có thể mở bản mã được không?”.** Cả hai dùng mật khẩu nhưng phục vụ mục tiêu, hồ sơ lưu trữ và cơ chế khôi phục khác nhau. Thiết kế vững chắc tách vai trò khóa, lưu metadata đúng mục đích, dùng thuật toán chuẩn và nói rõ hậu quả của việc quên/reset mật khẩu trước khi hệ thống lưu dữ liệu thực tế.

### Tài liệu tham khảo

- OWASP Password Storage Cheat Sheet — password hashing, salt, pepper, tham số chi phí: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- RFC 9106 — Argon2 Memory-Hard Function: https://www.rfc-editor.org/rfc/rfc9106
- RFC 8018 — PKCS #5 Password-Based Cryptography Specification, PBKDF2: https://www.rfc-editor.org/rfc/rfc8018
- NIST SP 800-132 — Recommendation for Password-Based Key Derivation, Part 1: https://csrc.nist.gov/pubs/sp/800/132/final
- NIST SP 800-38D — Galois/Counter Mode (GCM) và IV/nonce: https://csrc.nist.gov/pubs/sp/800/38/d/final
- Java SE 17 `PBEKeySpec`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html
- Java SE 17 `SecretKeyFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html
- Java SE 17 `Cipher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html
- Java SE 17 `MessageDigest`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
