# 7.7. Phân biệt password-based encryption với khóa sinh ngẫu nhiên

## Mục tiêu học tập

Khi hoàn thành bài, bạn có thể:

1. Giải thích vì sao **mật khẩu do con người chọn** và **khóa mật mã sinh ngẫu nhiên** có nguồn độ mạnh hoàn toàn khác nhau, ngay cả khi kết quả cuối đều là khóa AES-256 dài 32 byte.
2. Mô tả chính xác quy trình **password-based encryption (PBE)**: mật khẩu → KDF với salt, work factor → khóa → mã hóa có xác thực; phân biệt **salt**, **nonce**, **khóa**, **authentication tag** và thông tin cấu hình phải lưu.
3. Chọn khi nào nên **dẫn xuất khóa trực tiếp từ password**, khi nào nên **tạo data encryption key (DEK) ngẫu nhiên**, và khi nào cần **envelope encryption** với DEK được bọc bởi key encryption key (KEK) dẫn xuất từ password hoặc được quản lý bởi KMS/HSM.
4. Hiểu chi phí đoán mật khẩu ngoại tuyến, thay đổi mật khẩu, khôi phục dữ liệu, xoay khóa và các rủi ro khi hệ thống mất password hoặc key.
5. Thực hiện ví dụ **Java 17+** dùng `PBKDF2WithHmacSHA256`, `SecureRandom`, `KeyGenerator` và `AES/GCM/NoPadding`; kiểm tra mật khẩu sai và ciphertext bị sửa đều bị từ chối.

**Phạm vi:** Đây là bài trong phần *Mật khẩu và dẫn xuất khóa* của Java Advance security-cryptography. Trọng tâm là **kiến trúc bảo vệ dữ liệu bằng mật khẩu so với khóa sinh ngẫu nhiên**, không phải cách lưu mật khẩu đăng nhập của người dùng hoặc tự thiết kế thuật toán mật mã mới.

---

## 1. Hai nguồn khóa dẫn đến hai mức bảo mật khác nhau

Một hệ thống có dữ liệu nhạy cảm cần mã hóa bằng AES-GCM. Nhà phát triển có hai lựa chọn ban đầu:

- Người dùng nhớ một **mật khẩu/passphrase** để sau này giải mã. Chương trình không thể sử dụng chuỗi ký tự trực tiếp làm khóa AES đúng chuẩn; nó phải **dẫn xuất** khóa từ password bằng thuật toán như PBKDF2, scrypt hoặc Argon2id với các tham số đã thống nhất.
- Hệ thống dùng bộ sinh số ngẫu nhiên an toàn mật mã (**CSPRNG**) để tạo một **khóa AES ngẫu nhiên**. Khóa có thể được giữ trong KMS/HSM, keystore được bảo vệ hoặc được bọc bằng một khóa khác. Người dùng thường không cần nhớ khóa này.

Ví dụ một passphrase dễ đoán được đưa qua PBKDF2 để tạo ra 32 byte. Mặc dù đầu ra dài 256 bit và *trông* ngẫu nhiên, kẻ tấn công có thể thử danh sách mật khẩu, thực hiện lại KDF rồi kiểm chứng với ciphertext. **KDF tăng chi phí cho mỗi lần đoán; nó không biến mật khẩu có entropy thấp thành một bí mật 256 bit mạnh thực sự.**

Ngược lại, 32 byte sinh ngẫu nhiên đúng cách từ `KeyGenerator`/`SecureRandom` có không gian khóa lớn không bị giới hạn bởi khả năng ghi nhớ của người dùng. Điểm khó của cách này là **phân phối và bảo quản khóa**: nếu mất key thì không thể giải mã, nếu key lộ thì ciphertext có thể bị giải mã.

### 1.1. Mô hình luồng dữ liệu

**PBE trực tiếp:**

```text
Password do người dùng nhập
             │
             ├── Salt ngẫu nhiên riêng cho mỗi lần thiết lập mã hóa
             ├── KDF algorithm và work factor
             ▼
       Password KDF (chậm có chủ đích)
             │
             ▼
        Khóa AES được dẫn xuất
             │                 Nonce/IV mới
             └────────────┬─────────┘
                          ▼
                    AES-GCM
                          │
             Ciphertext + authentication tag
```

**Khóa ngẫu nhiên:**

```text
CSPRNG / KeyGenerator
           │
           ▼
   Khóa AES ngẫu nhiên ───────────────┐
           │                         │ lưu hoặc wrap an toàn
           ▼                         ▼
AES-GCM(data, nonce mới)        KMS / HSM / keystore
           │
Ciphertext + authentication tag
```

Có thể chọn cách thứ ba: **mã hóa dữ liệu bằng DEK ngẫu nhiên, rồi dùng KEK dẫn xuất từ password để bọc DEK**. Khi đổi password, trong một số kiến trúc chỉ cần bọc lại DEK; không cần mã hóa lại toàn bộ dữ liệu. Đây là **envelope encryption** sẽ được phân tích ở mục 6.

## 2. Bảng so sánh password-based encryption và khóa sinh ngẫu nhiên

| Khía cạnh | PBE trực tiếp (password → KDF → key) | Khóa sinh ngẫu nhiên (CSPRNG → key) |
| --- | --- | --- |
| Nguồn bí mật | Password/passphrase do con người hoặc cơ chế nhập khác cung cấp | Bộ sinh ngẫu nhiên có chất lượng mật mã |
| Độ mạnh thực tế | Bị giới hạn bởi entropy của password và chi phí tấn công KDF | Có thể đạt độ mạnh của khóa ngẫu nhiên và thuật toán khi generator đúng |
| Muốn lấy khóa | Phải có **password đúng**, **salt**, **KDF/parameters** | Phải truy cập được khóa đã lưu hoặc giải bọc bằng cơ chế được phép |
| Tốc độ thiết lập khóa | **Cố ý chậm** để gây khó cho brute force password | Thường nhanh hơn: tạo khóa bằng `KeyGenerator`, không cần KDF password chậm |
| Salt | **Bắt buộc/thiết yếu** cho dẫn xuất password, nên mới và riêng | Không cần salt để tạo raw AES key từ CSPRNG |
| Nonce AES-GCM | **Vẫn cần**, độc lập với salt | **Vẫn cần**, độc lập với việc khóa được sinh ngẫu nhiên |
| Authentication tag | **Vẫn cần** để phát hiện sửa đổi/sai key | **Vẫn cần** để phát hiện sửa đổi/sai key |
| Rủi ro đoán ngoại tuyến | Có: người giữ ciphertext+salt có thể thử password không cần liên hệ server | Không có “đoán password” nếu dữ liệu chỉ được bảo vệ bởi random key không phụ thuộc password |
| Lưu secret | Không nhất thiết lưu password; lưu metadata PBE để có thể tái tạo key | Phải lưu/bao bọc DEK hoặc không thể giải mã về sau |
| Đổi password | Thường phải giải mã và mã hóa lại nếu key dẫn xuất trực tiếp | Không bị ảnh hưởng nếu key độc lập với password |
| Rotation / thu hồi | Đổi password/cost/salt làm đổi key; cần kế hoạch migration | Rotate/re-encrypt hoặc rewrap key qua KMS/KEK |
| Khôi phục | Phụ thuộc khả năng nhớ/khôi phục password | Phụ thuộc backup/key escrow/KMS recovery controls |
| Phù hợp | File/vault cá nhân, backup mà người dùng mở bằng passphrase, yêu cầu user-held secret | Dịch vụ backend, DB/application encryption, khối lượng dữ liệu lớn, key lifecycle tập trung |
| Rủi ro điển hình | Password yếu, KDF quá nhanh, salt lặp, nhập password qua log, offline guessing | Hard-code key, lộ KMS credential, mất key/backup, dùng lại nonce hoặc chia sẻ key sai |

**Điểm giống nhau:** Cả hai cuối cùng đều có thể cho ra một `SecretKey` AES và dùng **cùng** `Cipher.getInstance("AES/GCM/NoPadding")`. Phân biệt PBE và random-key encryption chủ yếu ở **nguồn khóa, khả năng đoán, cách lấy lại khóa và quản trị vòng đời**, không phải ở việc “AES của PBE” là một thuật toán AES khác.

## 3. PBE là quy trình nhiều bước, không phải “AES(password)”

PBE cần hai thành phần tách biệt:

1. **Password-Based Key Derivation Function (KDF)** biến password thành vật liệu khóa, có salt và work factor.
2. **Encryption scheme** dùng khóa đó để mã hóa dữ liệu, tốt nhất là AEAD có authentication tag.

Ví dụ:

```text
password: char[]
salt: 16 byte ngẫu nhiên
KDF: PBKDF2-HMAC-SHA256, iterations = một tham số được cấu hình
derivedKey: 32 byte
nonce: 12 byte mới cho AES-GCM
ciphertextAndTag: doFinal(plaintext) qua AES/GCM/NoPadding
```

Những thông số như **KDF algorithm, số vòng lặp, kích thước khóa, salt, thuật toán mã hóa, nonce, phiên bản và định dạng tag** phải được lưu cùng bản mã hoặc có một cơ chế truy xuất đáng tin cậy. Người nhận dùng cùng password và chính xác cùng metadata để tạo lại khóa và giải mã.

### 3.1. Tại sao cần KDF chậm?

Password do con người chọn thường có mẫu dễ đoán. Nếu ứng dụng làm:

```java
// Sai cho PBE: SHA-256 quá nhanh, không có work factor hay salt.
byte[] aesBytes = java.security.MessageDigest
        .getInstance("SHA-256")
        .digest(new String(password)
                .getBytes(java.nio.charset.StandardCharsets.UTF_8));
```

Đây là **đoạn minh họa mẫu sai**, không phải code sản xuất. SHA-256 chạy rất nhanh, giúp kẻ tấn công thử hàng triệu mật khẩu. Việc tạo đối tượng `String` từ password cũng để lại bản sao khó xóa sạch khỏi bộ nhớ.

KDF dành cho password được thiết kế để làm mỗi phép đoán tốn **CPU và/hoặc RAM**:

- **PBKDF2-HMAC-SHA256:** có sẵn qua `SecretKeyFactory` trên các JDK 17 thông dụng; work factor là số lần lặp. Tiện cho ứng dụng thuần JDK và môi trường có yêu cầu chuẩn hóa/FIPS khi provider được chấp thuận.
- **scrypt:** KDF tiêu tốn bộ nhớ và CPU, gây khó cho phần cứng thử password hàng loạt. Không coi nó là API chuẩn sẵn trong mọi Java SE 17; dùng thư viện đã được đánh giá.
- **Argon2id:** KDF memory-hard thường được khuyến nghị cho nhiều ứng dụng hiện đại. Java SE 17 không có class chuẩn `Argon2id`; muốn dùng cần thư viện/provider phù hợp và kiểm soát tham số.
- Các thuật toán **PBE cũ** như `PBEWithMD5AndDES`, DES hay cấu hình PBKDF yếu không nên được chọn cho thiết kế mới chỉ vì tên có chữ `PBE`.

Độ lớn iteration của PBKDF2 phải được cập nhật theo chính sách tổ chức và phần cứng. Ví dụ OWASP Password Storage Cheat Sheet khuyến nghị **PBKDF2-HMAC-SHA256 600.000 vòng hoặc hơn cho bài toán lưu mật khẩu** ở thời điểm tài liệu tham khảo; đó **không phải hằng số áp dụng mọi PBE file**, và không thay thế benchmarking theo latency, threat model, tài nguyên và rủi ro DoS. Mỗi bản mã nên ghi rõ work factor thực sự đã dùng để giải mã và hỗ trợ nâng cấp sau này.

### 3.2. Salt có vai trò gì?

Một salt là byte ngẫu nhiên **không cần bí mật**, nên được tạo riêng cho mỗi lần thiết lập key từ password. Nếu người dùng dùng cùng password cho hai file nhưng mỗi file có salt riêng, KDF tạo ra hai khóa khác nhau với xác suất rất cao. Kẻ tấn công không thể dùng một kết quả hash/key derivation đã tính cho tất cả bản mã có salt khác nhau.

Trong Java:

```java
SecureRandom rng = new SecureRandom();
byte[] salt = new byte[16];
rng.nextBytes(salt);
```

Đây là **đoạn mã dùng bên trong method**, cần `import java.security.SecureRandom;`. Salt 16 byte là một lựa chọn thông dụng. **Salt không thay thế password có entropy tốt và không loại bỏ tấn công đoán ngoại tuyến**.

Tránh: salt hard-code cho mọi dữ liệu, dùng địa chỉ email làm salt duy nhất cho tất cả phiên bản file, dùng timestamp thay random salt hoặc nghĩ salt phải được giấu như secret. Khi dẫn xuất lại khóa để giải mã, phải dùng **salt đã lưu đúng với bản mã**, không tạo salt mới tùy ý.

### 3.3. Salt khác nonce/IV của AES-GCM

| Thuộc tính | Salt KDF | Nonce/IV AES-GCM |
| --- | --- | --- |
| Dùng trong | `PBKDF2WithHmacSHA256` / KDF password | `AES/GCM/NoPadding` |
| Mục đích | Làm mỗi lần dẫn xuất khóa khác nhau, chống tính toán sẵn/rộng trên nhiều bản mã | Bảo đảm các lần mã hóa với **cùng khóa** có đầu vào nonce không trùng |
| Bí mật? | Không | Không |
| Trong demo | 16 byte | 12 byte |
| Có thể lưu kèm ciphertext? | Có, cần để tái tạo khóa | Có, cần để giải mã |
| Có thể dùng cố định? | Không nên: mất tác dụng salt riêng | **Không được** tái sử dụng nonce khi mã hóa với cùng key |
| Thay đổi khi giải mã? | Không, phải dùng lại salt gốc | Không, phải dùng lại nonce gốc |

Salt và nonce dù đều có thể được sinh bằng `SecureRandom` **là hai trường riêng của giao thức**; không tự suy ra có thể thay thế cho nhau. Với AES-GCM, tái sử dụng cặp *key + nonce* là lỗi nghiêm trọng có thể phá confidentiality và authentication. Ngay cả khi mỗi file có salt mới, vẫn cần quản lý nonce đúng với khóa dùng trong mỗi lần mã hóa.

### 3.4. Mật khẩu đúng chưa đủ: phải xác thực bản mã

Mã hóa cần **confidentiality**, nhưng nếu không có integrity/authentication, dữ liệu đã mã hóa có thể bị sửa hoặc đánh tráo mà backend không phát hiện. Hãy ưu tiên **AEAD** như AES-GCM (hoặc cơ chế AEAD chuẩn phù hợp) khi xây PBE mới.

Một record khái niệm:

```text
version | kdf-id | iterations | salt | enc-id | nonce | ciphertext | tag
             \_______________ authenticated metadata ______________/
```

Việc xác thực metadata chỉ có tác dụng khi **quy trình thực sự đưa những bytes đó vào AAD hoặc phần được MAC/tag bảo vệ**. Nếu version/iteration/salt bị thay đổi mà không có validation có kiểm soát, hệ thống có thể bị lỗi, đổi hành vi hoặc bị lợi dụng tiêu tốn tài nguyên. Với GCM, ciphertext kèm tag có thể lưu nối nhau; bên nhận phải kiểm xác thực thành công trước khi dùng plaintext.

**Không dùng CBC/ECB không xác thực** để làm PBE cho dữ liệu mới. Một transformation có tên như `PBEWithHmacSHA256AndAES_256` không tự chứng minh rằng mode bên trong là AEAD có tag. Cần đọc đặc tả/provider và thực hiện riêng kiểm integrity nếu thuật toán PBE không cung cấp xác thực.

## 4. Tấn công đoán mật khẩu ngoại tuyến: giới hạn căn bản của PBE

Giả sử attacker lấy được:

```text
salt + iterations + nonce + ciphertext + authentication tag
```

Đối thủ không cần gửi yêu cầu đến server để đoán password. Họ có thể:

1. Chọn một mật khẩu ứng viên trong dictionary hoặc từ quy tắc biến đổi mật khẩu đã biết.
2. Chạy cùng `KDF(candidate, storedSalt, storedIterations)` để tạo khóa thử.
3. Thử giải mã/xác thực bản mã; nếu authentication tag không hợp lệ thì loại ứng viên, thử ứng viên tiếp theo.
4. Lặp nhiều lần trên GPU/CPU/thiết bị chuyên dụng tùy KDF cho phép.

Đây là **offline password guessing**. Rate limiting, captcha hoặc khóa tài khoản trên API **không ngăn được việc thử mật khẩu ngoại tuyến trên bản sao ciphertext bị đánh cắp**. Mỗi lần đoán có chi phí được làm tăng bởi KDF, song mật khẩu quá yếu vẫn có thể bị tìm ra.

Điều này tạo khác biệt lớn với **khóa ngẫu nhiên thực sự được giữ trong KMS/HSM**: nếu đối thủ chỉ có ciphertext và không có quyền lấy key/unwrap DEK, họ không có một password có thể thử từ từ điển để tái tạo khóa. Họ cần phá cơ chế quản trị key, đánh cắp quyền truy cập, khai thác hệ thống hoặc tấn công primitive, là một threat model khác.

**Kết luận kỹ thuật:** độ dài output của KDF **không đo trực tiếp entropy password**. Một khóa 256-bit dẫn xuất từ `"123456"` vẫn đối mặt với không gian đoán password rất nhỏ. KDF tốt + password đủ mạnh là điều kiện của PBE, không có đường tắt bằng hash hoặc Base64.

### 4.1. Pepper có cứu mật khẩu yếu không?

**Pepper** là một bí mật phía hệ thống (ví dụ được giữ trong KMS/HSM) có thể được kết hợp qua quy trình được thiết kế cẩn thận để tăng lớp phòng vệ. Pepper **khác salt**: salt công khai và riêng từng record; pepper phải bí mật. Nếu cả ciphertext, password yếu và pepper đều lộ, lớp này không còn lợi ích.

Với **PBE offline mà người dùng phải tự giải mã khi không kết nối server**, pepper bắt buộc có từ dịch vụ bên ngoài có thể làm mất khả năng sử dụng offline. Nếu mục tiêu là user-held backup, hãy quyết định trade-off rõ ràng thay vì bổ sung pepper vô điều kiện.

## 5. Khóa ngẫu nhiên: tại sao tránh được giới hạn entropy của password?

Trong Java:

```java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, new SecureRandom());
SecretKey dataKey = generator.generateKey();
```

Đây là **đoạn Java minh họa**, cần `javax.crypto.KeyGenerator`, `javax.crypto.SecretKey`, `java.security.SecureRandom` và xử lý checked exception. Với provider JDK 17 phổ biến, đoạn này tạo AES key 256 bit từ CSPRNG thích hợp, không dẫn xuất từ password có thể đoán.

Nhưng **sinh ngẫu nhiên là một nửa câu chuyện**:

- Khóa phải được lưu/giữ kín trong hệ thống thích hợp; tuyệt đối không hard-code key vào source, JSON config hay lộ qua log.
- Xác định chính sách key ownership: user, tenant, service, object hay phiên bản dữ liệu?
- Có backup/rotation, quản lý quyền đọc/unwrap và quy trình khôi phục hay không?
- Có thể dùng KMS/HSM để giữ **KEK** hoặc tạo/unwrap **DEK**; khi mã hóa cục bộ, phải quản lý plaintext DEK trong bộ nhớ và xóa khi hợp lý.
- Nếu mất key và không có bản backup/escrow phù hợp, dữ liệu **có thể không khôi phục được**, kể cả còn đủ ciphertext.
- Mặc dù key ngẫu nhiên mạnh, mã hóa vẫn phải có IV/nonce không lặp, AEAD tag và schema/authorization đúng.

Trong môi trường backend xử lý hàng triệu record, **khóa ngẫu nhiên và envelope encryption** thường cho phép quản lý rotation, access control, audit và lưu trữ theo dịch vụ tốt hơn việc lấy một password chung cho tất cả dữ liệu.

### 5.1. Có nên dùng `SecureRandom.nextBytes` thay cho `KeyGenerator`?

Có thể sinh byte bằng `SecureRandom` rồi tạo `SecretKeySpec` khi thuật toán cho phép và chiều dài/chất lượng được bảo đảm. Tuy nhiên, `KeyGenerator` thường làm rõ **ý định tạo khóa cho thuật toán cụ thể**, kiểm tra kích thước khóa và dễ tích hợp provider. Khi HSM/KMS tạo key không cho xuất `getEncoded()`, phương thức quản lý key khác với raw byte trong ví dụ.

Không dùng `Random`, `ThreadLocalRandom`, `Math.random()` hoặc `UUID.toString()` một cách tùy tiện để tạo AES key. UUID v4 có cấu trúc/bit cố định, không thể coi bất kỳ chuỗi UUID nào là một khóa AES-256 đủ entropy. Đừng dùng secret lấy từ database ID hoặc timestamp như raw key.

## 6. Envelope encryption: phối hợp password và random key

**Envelope encryption** tách:

- **DEK (Data Encryption Key):** khóa sinh ngẫu nhiên để mã hóa dữ liệu.
- **KEK (Key Encryption Key):** khóa dùng để **wrap/bảo vệ DEK**. KEK có thể dẫn xuất từ password thông qua KDF hoặc được giữ bởi KMS/HSM.

Luồng mẫu cho file người dùng bảo vệ bằng password:

```text
                 User password
                      │ + salt + KDF parameters
                      ▼
                      KEK
                       │
Random DEK ────────────┼──> Wrap DEK bằng KEK ──> wrappedDEK
    │                  │
    │                  └──── Bảo vệ metadata/version/policy tương ứng
    ▼
AES-GCM mã hóa dữ liệu bằng DEK + dataNonce
    │
ciphertext + tag

Lưu: file format/version | KDF params | salt
     KEK wrapping nonce | wrappedDEK + wrap tag
     data nonce | data ciphertext + data tag | AAD/context
```

Ở đây, **wrap key** cần cơ chế có integrity chuẩn (ví dụ AES-KW hoặc AEAD đúng cách), nonce/key discipline và ràng buộc metadata; không chỉ XOR DEK với password hash. Nếu có hai lớp AEAD dùng cùng thuật toán, phải dùng khóa tương ứng độc lập và quản lý **nonce riêng cho từng khóa/lần mã hóa**.

### 6.1. Ưu điểm so với PBE trực tiếp

| Thao tác | PBE trực tiếp | Random DEK + password-derived KEK |
| --- | --- | --- |
| Mã hóa file lớn | Mã hóa bằng khóa dẫn xuất từ password | Mã hóa file bằng random DEK |
| Mở file | KDF password → key → decrypt data | KDF password → KEK → unwrap DEK → decrypt data |
| Thay password | Cần có khả năng decrypt/re-encrypt toàn bộ file (hoặc thiết kế migration khác) | Có thể unwrap DEK bằng KEK cũ và **rewrap DEK** bằng KEK mới, giữ nguyên ciphertext dữ liệu |
| Đổi work factor | Thường thay key dẫn xuất, cần tạo lại ciphertext | Có thể rewrap DEK với cost mới |
| Dữ liệu nhiều GB | Mã hóa lại khi thay password có thể rất tốn I/O | Rewrap DEK thường xử lý vật liệu nhỏ hơn |
| Thêm nhiều người được cấp quyền | Phức tạp nếu mọi người dùng chung password hoặc phải giữ nhiều bản mã | Có thể wrap cùng DEK cho mỗi recipient theo cơ chế/KEK khác nhau |
| Rủi ro đoán password ngoại tuyến | Có | **Vẫn có** nếu wrappedDEK và salt bị lấy; tách DEK không biến password yếu thành mạnh |

**Điểm quan trọng:** random DEK được wrap bằng KEK từ password **không loại bỏ offline dictionary attack trên password**, vì attacker có thể thử giải bọc DEK. Lợi ích chính của envelope ở trường hợp này là **tách khóa dữ liệu khỏi khóa truy cập**, đơn giản hóa đổi password, chia quyền và đổi cách bảo vệ KEK.

Nếu cần chống rủi ro đoán password với ciphertext bị đánh cắp, người dùng phải có password đủ mạnh và KDF đúng; hoặc hệ thống cần thêm bí mật độc lập được quản lý tập trung bằng KMS/HSM và kiểm soát truy cập.

### 6.2. Khi KEK ở KMS/HSM

Một backend có thể dùng random DEK để mã hóa payload; chỉ lưu **wrapped DEK** cùng ciphertext. Khi được phép giải mã, dịch vụ gọi KMS để unwrap DEK trong phạm vi quyền xác định. Đây là **kiến trúc dịch vụ quản lý khóa**, khác với việc người dùng nhớ một password.

Ưu điểm: kiểm soát IAM, policy, audit, khóa master, rotation/backup theo hệ thống. Giới hạn: phụ thuộc dịch vụ, network, availability, chi phí, quyền cấp cho ứng dụng và rủi ro key/credential trong RAM. **KMS không thay thế authorization của ứng dụng**: API vẫn phải kiểm tra tenant/record access trước khi yêu cầu unwrap.

### 6.3. Chú ý khi đổi password và rotate key

Nếu password cũ bị lộ và attacker đã giữ **bản sao wrappedDEK cũ**, việc thay password và ghi đè header **không làm bản sao đã bị đánh cắp trở nên an toàn**. Tương tự, KMS rotation không tự thu hồi toàn bộ ciphertext/DEK cũ đã lộ trước đó. Cần phân tích dữ liệu nào bị ảnh hưởng, hủy quyền, thay DEK hoặc mã hóa lại khi threat model đòi hỏi.

Có thể giữ DEK cũ để đọc dữ liệu cũ trong giai đoạn migration, nhưng phải có key-version và quy trình retire. Đừng chỉ tăng iteration count hoặc thay salt **trong metadata** mà không thực hiện derivation/rewrap/re-encrypt phù hợp: dữ liệu sẽ không còn giải mã được.

## 7. Định dạng dữ liệu phải lưu để giải mã được sau nhiều năm

Ví dụ PBE trực tiếp dùng PBKDF2-HMAC-SHA256 và AES-GCM:

```text
+----------+---------+------------+----------+----------+----------+----------------+
| format v | kdf id  | iterations | salt     | nonce    | enc id   | ciphertext+tag |
+----------+---------+------------+----------+----------+----------+----------------+
    1 byte    enum       int          16 B       12 B      AES-GCM     arbitrary
```

Sơ đồ chỉ để mô tả; **không phải chuẩn byte layout chính thức**, và các định dạng thực tế cần field lengths, endian, AAD, versioning, maximum payload, authenticated parsing và bảo vệ chống downgrades.

Trường metadata quan trọng:

| Trường | Có bí mật không? | Tại sao cần? |
| --- | --- | --- |
| Phiên bản format | Không | Biết cách parse/migrate, từ chối phiên bản không hợp lệ |
| Tên KDF và PRF | Không | Tạo lại đúng khóa từ password |
| Số vòng lặp / memory cost / parallelism | Không | Tái hiện chính xác work factor đã dùng |
| Salt | Không | Dẫn xuất cùng khóa từ password |
| Cipher mode, key size, tag size | Không | Chọn đúng transformation và tham số |
| Nonce/IV | Không | Giải mã đúng; khi mã hóa cần bảo đảm uniqueness dưới cùng key |
| Ciphertext + authentication tag | Không cần giấu tag; **plaintext được bảo vệ** | Lưu dữ liệu và kiểm nguyên vẹn |
| Key ID hoặc wrapped DEK (nếu envelope) | Không giống secret key raw; phải bảo vệ toàn vẹn | Giúp chọn key phù hợp và mở dữ liệu |
| Secret password / raw random key / KEK plaintext | **Có** | **Không** đặt vào bản mã/header/log dưới dạng raw |

Không giữ tất cả thông số PBE chỉ trong config “hiện tại” rồi thay đổi config sau vài tháng. Khi KDF cost nâng lên, file cũ cần **đọc bằng đúng tham số cũ**, sau đó migration/re-encrypt có kiểm soát. Nếu lưu KDF id trong header do attacker kiểm soát, cần **allowlist, giới hạn tài nguyên và authenticated metadata** để ngăn downgrade/DoS hoặc khai thác parser.

### 7.1. AAD bảo vệ ngữ cảnh

AEAD có **AAD (Additional Authenticated Data)**: metadata được **xác thực nhưng không mã hóa**. Ví dụ có thể đưa vào AAD: version, KDF parameters, salt/nonce nếu thiết kế, tenant ID, object ID, content type, quyền/ngữ cảnh ứng dụng. Bên decrypt phải cung cấp chính xác cùng AAD; mismatch sẽ làm tag check thất bại.

Đừng đặt secret vào AAD nếu kỳ vọng nó được mã hóa; AAD thường được lưu/truyền rõ. Không cho ứng dụng nhận plaintext trước khi xác thực GCM tag hoàn thành. Một ciphertext GCM hợp lệ vẫn có thể bị **phát lại** nguyên vẹn; chống replay phải dùng sequence/ID/trạng thái nghiệp vụ.

## 8. Ví dụ Java 17+: PBE với PBKDF2 + AES-GCM so với khóa AES sinh ngẫu nhiên

Tạo file **`PasswordVsRandomKeyDemo.java`**. Chương trình Java 17+ độc lập gồm hai nhánh:

- **PBE trực tiếp:** dẫn xuất AES-256 từ password, salt 16 byte ngẫu nhiên và PBKDF2-HMAC-SHA256; mã hóa AES-GCM với nonce 12 byte. Bản ghi chứa tham số KDF cần cho lần giải mã sau. Header version + iterations + salt + nonce được đưa vào AAD.
- **Random key:** tạo AES-256 trực tiếp bằng `KeyGenerator` và mã hóa cùng plaintext với AES-GCM dùng nonce mới. Khóa chỉ tồn tại trong ví dụ, không có lưu trữ/recovery.
- Thử password sai và sửa tag để chứng minh **không xuất plaintext khi authentication thất bại**. Stdout chỉ in boolean và độ dài, không tiết lộ password hoặc key.

**Lưu ý trước khi chạy:** Password chuỗi cố định dưới đây **chỉ là dữ liệu demo, tuyệt đối không hard-code password trong ứng dụng thực tế**. Số vòng lặp là ví dụ được cố ý đặt rõ ràng và nên benchmark/tune theo chính sách hiện hành. Mã dùng `PBKDF2WithHmacSHA256` có sẵn trên các JDK 17 thông dụng; một provider đặc biệt có thể yêu cầu cấu hình khác. `record` là cú pháp Java 17 hợp lệ.

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

public class PasswordVsRandomKeyDemo {
    private static final SecureRandom RNG = new SecureRandom();

    private static final int ROUNDS = 600_000; // Demo; tune theo hệ thống.
    private static final int SALT_BYTES = 16;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int KEY_BITS = 256;
    private static final byte VERSION = 1;

    // In-memory record: production cần serialization chuẩn và defensive copy.
    private record PasswordEnvelope(
            int iterations, byte[] salt, byte[] nonce, byte[] ciphertextAndTag) {}

    private static SecretKey derivePasswordKey(
            char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {

        PBEKeySpec spec =
                new PBEKeySpec(password, salt, iterations, KEY_BITS);
        byte[] material = null;
        try {
            SecretKeyFactory kdf =
                    SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
            material = kdf.generateSecret(spec).getEncoded();
            // SecretKeySpec tạo bản sao key bytes trước khi xóa buffer tạm.
            return new SecretKeySpec(material, "AES");
        } finally {
            if (material != null) {
                Arrays.fill(material, (byte) 0);
            }
            spec.clearPassword();
        }
    }

    private static byte[] header(
            int iterations, byte[] salt, byte[] nonce) {
        return ByteBuffer.allocate(1 + 4 + salt.length + nonce.length)
                .put(VERSION)
                .putInt(iterations)
                .put(salt)
                .put(nonce)
                .array();
    }

    private static PasswordEnvelope encryptWithPassword(
            char[] password, byte[] plaintext)
            throws GeneralSecurityException {

        byte[] salt = new byte[SALT_BYTES];
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(salt);
        RNG.nextBytes(nonce);

        SecretKey key = derivePasswordKey(password, salt, ROUNDS);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(header(ROUNDS, salt, nonce));
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new PasswordEnvelope(ROUNDS, salt, nonce, ciphertextAndTag);
    }

    private static byte[] decryptWithPassword(
            char[] password, PasswordEnvelope stored)
            throws GeneralSecurityException {

        // Giới hạn tài nguyên và định dạng trước KDF.
        if (stored.iterations() < 100_000
                || stored.iterations() > 2_000_000
                || stored.salt().length != SALT_BYTES
                || stored.nonce().length != NONCE_BYTES
                || stored.ciphertextAndTag().length < TAG_BITS / 8) {
            throw new GeneralSecurityException("Invalid envelope");
        }

        SecretKey key = derivePasswordKey(
                password, stored.salt(), stored.iterations());
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, stored.nonce()));
        cipher.updateAAD(header(
                stored.iterations(), stored.salt(), stored.nonce()));
        return cipher.doFinal(stored.ciphertextAndTag());
    }

    private static SecretKey generateRandomKey()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(KEY_BITS, RNG);
        return generator.generateKey();
    }

    private static boolean randomKeyRoundTrip(byte[] plaintext)
            throws GeneralSecurityException {
        SecretKey key = generateRandomKey();
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        byte[] ciphertextAndTag = encrypt.doFinal(plaintext);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        return Arrays.equals(plaintext, decrypt.doFinal(ciphertextAndTag));
    }

    public static void main(String[] args) throws Exception {
        // DEMO ONLY: production lấy password từ input bảo mật.
        char[] password = "classroom-demo-only".toCharArray();
        char[] wrong = "wrong-password".toCharArray();
        try {
            byte[] plaintext = "PBE vs random data key"
                    .getBytes(StandardCharsets.UTF_8);

            PasswordEnvelope stored =
                    encryptWithPassword(password, plaintext);
            boolean pbeRoundTrip = Arrays.equals(
                    plaintext, decryptWithPassword(password, stored));

            boolean wrongRejected = false;
            try {
                decryptWithPassword(wrong, stored);
            } catch (AEADBadTagException expected) {
                wrongRejected = true;
            }

            byte[] changed = stored.ciphertextAndTag().clone();
            changed[changed.length - 1] ^= 1;
            PasswordEnvelope tampered = new PasswordEnvelope(
                    stored.iterations(),
                    stored.salt(),
                    stored.nonce(),
                    changed);
            boolean tamperRejected = false;
            try {
                decryptWithPassword(password, tampered);
            } catch (AEADBadTagException expected) {
                tamperRejected = true;
            }

            System.out.println("pbeRoundTrip=" + pbeRoundTrip);
            System.out.println("wrongPasswordRejected=" + wrongRejected);
            System.out.println("pbeTamperRejected=" + tamperRejected);
            System.out.println("saltBytes=" + stored.salt().length);
            System.out.println("pbeNonceBytes=" + stored.nonce().length);
            System.out.println("randomKeyRoundTrip=" +
                    randomKeyRoundTrip(plaintext));
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

Biên dịch và chạy với JDK 17+ hỗ trợ các thuật toán được dùng:

```shell
javac PasswordVsRandomKeyDemo.java
java PasswordVsRandomKeyDemo
```

**Stdout kỳ vọng** (giá trị khóa, salt, nonce đều ngẫu nhiên nên code cố ý không in các giá trị đó):

```text
pbeRoundTrip=true
wrongPasswordRejected=true
pbeTamperRejected=true
saltBytes=16
pbeNonceBytes=12
randomKeyRoundTrip=true
```

### 8.1. Đọc đúng từng kết quả

- `pbeRoundTrip=true`: cùng password + salt + iterations tái tạo cùng AES key; đúng nonce và metadata AAD cho phép GCM xác thực và trả plaintext gốc.
- `wrongPasswordRejected=true`: password khác tạo key khác; GCM authentication tag không hợp lệ, ném `AEADBadTagException`. Đây là cơ chế nhận biết giải mã thất bại, **không phải dịch vụ giới hạn số lượt thử password ngoại tuyến**.
- `pbeTamperRejected=true`: thay đổi byte tag làm xác thực thất bại. Không được bắt `AEADBadTagException` rồi vẫn trả plaintext cũ/chưa kiểm chứng cho nghiệp vụ.
- `saltBytes=16` và `pbeNonceBytes=12`: có **hai trường** khác chức năng, lưu kèm ciphertext khi cần giải mã.
- `randomKeyRoundTrip=true`: cùng AES-GCM nhưng khóa được tạo ngẫu nhiên bởi `KeyGenerator`, không cần PBKDF2 hay password.
- Chương trình **không chứng minh** rằng password demo có đủ entropy cho production; chính vì password hard-code công khai nên nó chỉ minh họa API và định dạng, tuyệt đối không dùng để bảo vệ dữ liệu thật.

### 8.2. Các giới hạn có chủ ý của chương trình

Đây là ví dụ Java **chạy độc lập**, không phải thư viện sản xuất. Không có lưu file, backup/key escrow, key IDs, rotation, tenant isolation, chống replay, identity/authorization, UI nhập password hoặc logging/audit. `PasswordEnvelope` là record chứa các mảng có thể thay đổi, **chưa phải immutable serialized envelope**; production nên có defensive copies, parser/serializer chuẩn, maximum total ciphertext length và phiên bản/algorithm identifiers được kiểm chứng.

Lời gọi `PBEKeySpec.clearPassword()` xóa **bản sao** password bên trong spec. `Arrays.fill(password, '\0')` xóa mảng caller đang giữ; **không thể đảm bảo xóa mọi bản sao password trong JVM, heap dumps hay thư viện**. Trong code demo, literal string của password có thể còn trong memory; đó là lý do phải lấy input qua cơ chế bảo mật của hệ thống trong production.

Việc đưa header vào AAD bảo vệ byte version/iterations/salt/nonce khi xác thực. Tuy nhiên, trước khi chạy KDF tốn CPU, bên nhận vẫn phải parse header và **áp đặt allowlist/giới hạn chi phí**. Nếu nhận từ mạng, cần thêm input size/rate limits để giảm DoS. Không tự thay đổi AAD encoding giữa các phiên bản; ví dụ `ByteBuffer` dùng thứ tự byte mặc định big-endian và chỉ giới thiệu một layout nội bộ.

Chương trình tạo random key nhưng **không lưu key**; khi JVM kết thúc sẽ không có cách giải mã bản mã random-key đã tạo nếu không có quản lý key thật. Với PBE, key có thể tái tạo từ password+tham số; với random key, phải có nơi giữ/bao bọc an toàn.

## 9. Khi nào chọn cách nào?

### Tình huống A – người dùng khóa một file backup để tự mở offline

**PBE với password mạnh** hợp lý nếu người dùng phải tự giữ bí mật và không muốn phụ thuộc máy chủ key. Lưu salt, work factor, nonce, ciphertext/tag, version; có quy trình reset/recovery rõ ràng. Nếu quên password và không có key recovery, hệ thống không thể “tự khôi phục” chỉ từ salt/ciphertext.

Với file lớn hoặc thay đổi password thường xuyên, cân nhắc **random DEK + password-derived KEK** để chỉ rewrap DEK thay vì mã hóa lại gigabyte. Mô hình này vẫn bị tấn công đoán password ngoại tuyến khi attacker lấy được wrapped DEK.

### Tình huống B – backend mã hóa trường dữ liệu khách hàng

Ưu tiên **random DEK**, có thể qua envelope encryption với KMS/HSM. Service cấp quyền truy cập DEK theo tenant/record, ghi audit và hạn chế quyền tài khoản dịch vụ. Một password hard-code chung trong code/config để “dẫn xuất khóa” thường tạo single point of failure; khi leak password, toàn bộ ciphertext liên quan có thể bị giải mã.

### Tình huống C – nhiều người có quyền mở cùng tài liệu

Nếu mỗi người giữ password riêng, random DEK có thể được wrap cho từng recipient với KEK/key riêng. Thu hồi quyền cần quản lý phiên bản và điều kiện phân phối DEK; chỉ xóa một wrapped key **không thu hồi bản DEK đã được người cũ lấy về và lưu lại**. Dữ liệu nhạy cảm cần phân tích quyền truy cập và rotation DEK theo sự kiện thu hồi.

### Tình huống D – khóa mã hóa cho dữ liệu dài hạn

Random key trong KMS với backup/rotation thường dễ tổ chức hơn một password phụ thuộc trí nhớ của cá nhân. Nhưng phụ thuộc availability của KMS, mạng và chính sách lưu bản sao. Quy trình khôi phục/escrow cần được kiểm thử thực tế; mất key có thể đồng nghĩa mất dữ liệu.

### Tình huống E – ứng dụng quản lý mật khẩu đăng nhập

**Không dùng PBE để lưu password đăng nhập rồi giải mã để so sánh.** Với authentication, lưu password verifier bằng thuật toán password hashing/KDF chuyên dụng như Argon2id, scrypt, PBKDF2 theo chính sách, salt riêng, thông số cost và kiểm chứng an toàn. Không cần khôi phục plaintext password để login; chức năng “quên mật khẩu” nên đặt lại bằng quy trình xác thực riêng.

PBE phục vụ tình huống **cần lấy lại plaintext dữ liệu** từ một bí mật người dùng cung cấp; password hashing phục vụ tình huống **cần xác nhận password đúng mà không khôi phục password gốc**.

## 10. Đổi mật khẩu, đổi KDF cost và rotate khóa

### 10.1. Đổi password của PBE trực tiếp

Giả sử file đang dùng `keyOld = KDF(oldPassword, oldSalt, oldCost)`. Sau khi người dùng nhập đúng password cũ:

1. Đọc metadata cũ; validate cấu hình/sizes.
2. Dẫn xuất `keyOld`, xác thực GCM tag và giải mã dữ liệu.
3. Tạo salt mới, cost/KDF version theo policy mới; dẫn xuất `keyNew` từ password mới.
4. Tạo nonce mới và mã hóa lại dữ liệu bằng AEAD, với AAD/version mới.
5. Ghi bản mới **theo cách atomic** và có recovery/backup phù hợp, xóa vật liệu nhạy cảm tạm trong khả năng.
6. Chỉ khi xác minh migration thành công mới cập nhật active version/retire old key.

Không thể chỉ đổi chuỗi password lưu trong UI rồi “giữ nguyên ciphertext PBE” vì key thay đổi.

### 10.2. Rewrap DEK của envelope encryption

Với `dataCiphertext = Encrypt(DEK, plaintext)` và `wrappedDEK = Wrap(KEK, DEK)`:

1. Xác thực/truy xuất DEK bằng password/KEK cũ.
2. Sinh salt mới và KEK mới từ password mới (hoặc chuyển sang KMS key theo chính sách).
3. Wrap cùng DEK bằng KEK mới, nonce/key-wrap format mới và tag hợp lệ.
4. Ghi metadata mới và wrapped DEK an toàn, bảo đảm chính sách rollback/backup.

Dữ liệu chính có thể không cần mã hóa lại khi chỉ thay cơ chế bảo vệ DEK. Nếu **DEK đã lộ**, rewrap không giải quyết được; cần rotate DEK và mã hóa lại dữ liệu được bảo vệ.

### 10.3. Nâng cấp PBKDF2/scrypt/Argon2id

Khi workload/phần cứng thay đổi, work factor cũ có thể không còn phù hợp. Thiết kế version giúp giải mã record cũ đúng tham số rồi re-encrypt hoặc rewrap bằng cấu hình mới. Nếu chọn Argon2id/scrypt ngoài JDK, phải kiểm version, thuật toán và tham số để các hệ thống tương thích. Không xem thay số iterations trong metadata là một upgrade hoàn tất.

## 11. Vận hành, performance và những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `new SecretKeySpec(password.getBytes(), "AES")` | Password không đúng kích thước AES, hoặc đủ dài nhưng entropy yếu | Dùng KDF chuyên dụng cho password |
| `SHA-256(password)` làm AES key | KDF quá nhanh, cho phép offline guessing quy mô lớn | Dùng PBKDF2/scrypt/Argon2id theo policy |
| Salt cố định cho mọi user/file | Trùng key nếu password giống nhau, thuận lợi tính toán sẵn | Salt riêng và sinh bằng CSPRNG |
| Giấu salt như secret chính | Phân tích sai threat model, quên giữ true secret | Salt công khai; bảo vệ password/key |
| Không lưu KDF params | Sau khi đổi config, file cũ không giải mã được | Versioned, self-describing envelope |
| Dùng `Random` cho salt/key/nonce | Nguồn có thể dự đoán, nguy cơ lặp/weak key | `SecureRandom` hoặc engine mật mã chuẩn |
| Tái sử dụng AES-GCM nonce cùng key | Có thể phá confidentiality và authentication | Nonce unique dưới từng key, giới hạn số lần dùng khóa |
| Dùng AES-CBC không MAC | Không bảo vệ integrity, padding oracle | AEAD, hoặc Encrypt-then-MAC đúng chuẩn trong legacy |
| Chỉ kiểm “decrypt không exception” | Có thể chấp nhận dữ liệu bị thay đổi trong mode không xác thực | Dùng AEAD tag/MAC, không xử lý dữ liệu chưa auth |
| Đặt cost quá nhỏ | Attacker thử rất nhiều candidate/giây | Benchmark và cập nhật policy KDF |
| Tin rằng cost cực lớn luôn tốt | Tự gây latency/CPU DoS, nhất là service mở nhiều file | Giới hạn iterations/memory, kiểm resource policy trước KDF |
| Hard-code password hoặc key trong JAR | Ai có artifact/source có thể đọc bí mật | Secure input, secret manager/KMS/keystore |
| Log password, raw key, decrypted data | Mất bí mật dù thuật toán đúng | Redact log, hạn chế debug dumps và access |
| Dùng password mạnh rồi lưu plaintext cạnh ciphertext | Password bị lộ từ nơi lưu, PBE mất bảo vệ | Bảo vệ đường nhập và vòng đời secret |
| Dùng random DEK rồi quên lưu/backup | Mất khả năng giải mã mãi mãi | KMS/wrapped DEK, key escrow/recovery |
| Rewrap DEK nhưng không xét bản sao cũ đã lộ | Đối thủ giữ wrapped key hoặc DEK cũ vẫn truy cập | Threat-model rotation/re-encryption và backup |
| Dùng key truy cập để thay authorization | Người giữ ciphertext hoặc ID không đương nhiên có quyền nghiệp vụ | IAM, tenant policy, quyền đọc/unwrap độc lập |

### 11.1. Cẩn thận với thời gian và lỗi

KDF chậm có chủ đích; trong API có nhiều người dùng, không cho phép một client đẩy iterations lên hàng tỷ hoặc cung cấp ciphertext không giới hạn rồi yêu cầu backend tự xử lý. Áp đặt size limits, allowlist KDF, dải cost có thể chấp nhận, rate limiting, timeout/resource budget. Với GCM, lỗi key/nonce/AAD/tag cần được xử lý bằng **từ chối bản mã**, không trả plaintext hoặc tiết lộ nội dung. Đừng biến khác biệt `wrong password` và `bad ciphertext` thành thông báo phân biệt dựa trên các chi tiết mật mã ngoài luồng phù hợp.

KDF có thể tiêu tốn CPU đáng kể; nếu hệ thống cần mã hóa rất nhiều record, **không dẫn xuất khóa bằng password mới cho từng row/request** nếu kiến trúc này không cần thiết. Có thể dẫn xuất KEK khi mở vault rồi dùng random DEK cho các record, tùy threat model/session lifecycle. Nhưng caching plaintext key kéo dài cũng làm tăng rủi ro khi memory bị truy cập; phải cân nhắc cả hiệu năng và an ninh.

### 11.2. Java API cần nhớ

| API | Mục đích | Ghi chú |
| --- | --- | --- |
| `PBEKeySpec` | Giữ password dạng `char[]` + salt + iterations + key length | Có `clearPassword()` cho bản sao trong spec |
| `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` | Dẫn xuất key từ password | Không phải AES cipher hay memory-hard KDF |
| `SecretKeySpec` | Bao raw derived bytes thành key cho AES | Xóa buffer trung gian khi thích hợp; đừng log |
| `KeyGenerator.getInstance("AES")` | Sinh key AES ngẫu nhiên theo provider | Phân biệt với password derivation |
| `SecureRandom` | Sinh salt/nonce/key material an toàn | Không dùng `Random` cho secret |
| `Cipher.getInstance("AES/GCM/NoPadding")` | AEAD encryption/decryption | Nonce unique với cùng key, tag được kiểm khi giải mã |
| `GCMParameterSpec(128, nonce)` | Tag length và nonce cho AES-GCM | Nonce 12 byte phổ biến; tag 128 bit |
| `Cipher.updateAAD(...)` | Xác thực metadata ngoài plaintext | AAD phải cung cấp trước dữ liệu ciphertext |
| `AEADBadTagException` | Dấu hiệu giải mã AEAD không xác thực được | Từ chối toàn bộ bản mã, không dùng plaintext |

**Lưu ý interoperability password:** `char[]` trong `PBEKeySpec` không tự chứng minh toàn bộ hệ thống dùng cùng chuẩn hóa Unicode/encoding. Khi cần tương tác Java với thư viện/ngôn ngữ khác, phải xác định cách biến password thành byte string, Unicode normalization, KDF variant và test vector. Một password tiếng Việt có dấu có thể tạo key khác nếu hai hệ thống tiền xử lý Unicode khác nhau. Không tự chuyển password thành String nhiều bản sao chỉ để “dễ encode”.

## 12. Câu hỏi tự kiểm tra

**1. PBKDF2 xuất 256 bit có làm một password 6 chữ số thành khóa mạnh như random AES-256 không?**  
Không. Output dài 256 bit nhưng không gian password có thể bị duyệt ngoại tuyến. Work factor khiến mỗi lần đoán chậm hơn, không tạo thêm entropy cho mật khẩu.

**2. Nếu không lưu salt thì có giải mã PBE được không?**  
Thông thường không thể dẫn xuất lại đúng key nếu thiếu salt gốc, trừ khi còn bản key/metadata khác. Phải lưu salt kèm format/version/cost và ciphertext.

**3. Salt và nonce có giống nhau không?**  
Không. Salt đi vào KDF; nonce đi vào AES-GCM. Cả hai thường không bí mật nhưng có quy tắc riêng; đặc biệt GCM nonce không được lặp khi encrypt bằng cùng key.

**4. Khóa AES sinh ngẫu nhiên có cần PBKDF2 nữa không?**  
Không cần PBKDF2 để *tạo* raw random key. Nếu muốn **bọc** DEK bằng password thì có thể dùng KDF tạo KEK ở tầng riêng.

**5. Vì sao PBE phải dùng AEAD?**  
Để không chỉ giấu plaintext mà còn phát hiện dữ liệu bị thay đổi. Mật khẩu đúng mà ciphertext bị sửa vẫn phải bị từ chối.

**6. Dữ liệu có được bảo vệ trước đoán password ngoại tuyến chỉ vì server giới hạn 5 lần login không?**  
Không. Người giữ ciphertext có thể thử candidate offline; cần password mạnh và KDF được cấu hình đúng.

**7. Envelope encryption có loại bỏ việc phải tin password mạnh không?**  
Không khi KEK dẫn xuất từ password. Nó chủ yếu giúp tách DEK khỏi KEK, dễ rewrap/rotate và chia sẻ quyền.

**8. Nếu thay password trong envelope, ciphertext dữ liệu có luôn cần re-encrypt không?**  
Không, có thể rewrap DEK. Nhưng nếu DEK hoặc wrappedDEK cũ đã lộ, cần đánh giá rotate/re-encrypt theo mức độ compromise.

**9. Với hệ thống backend tự mã hóa dữ liệu, nên giữ key như thế nào?**  
Thường dùng random DEK với wrapped key/KMS hoặc HSM và IAM/audit/recovery; không hard-code một password chung trong source.

**10. PBE có phải là cách lưu mật khẩu đăng nhập tốt nhất?**  
Không. Password login nên lưu verifier băm bằng thuật toán password hashing phù hợp, không mã hóa đảo ngược chỉ để so sánh password.

## Tài liệu tham khảo

- [NIST SP 800-132 – Recommendation for Password-Based Key Derivation: Storage Applications](https://csrc.nist.gov/pubs/sp/800/132/final): nền tảng password-derived master key, salt và iteration.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): lựa chọn Argon2id/scrypt/PBKDF2, chi phí đoán mật khẩu và khác biệt hashing/encryption.
- [Java SE 17 – PBEKeySpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): mô hình password `char[]`, salt, iteration, key length và `clearPassword()`.
- [Java SE 17 – SecretKeyFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html): tạo `SecretKey` từ `KeySpec`.
- [Java SE 17 – Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): PBKDF2, AES, PBE schemes và các tên thuật toán Java.
- [Java SE 17 – Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): `AES/GCM/NoPadding`, `updateAAD`, authentication tag và nonce uniqueness.
- [Java SE 17 – KeyGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html) và [SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): tạo khóa ngẫu nhiên và nguồn entropy theo provider.