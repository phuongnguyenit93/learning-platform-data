# Pepper, kho bí mật và kế hoạch thay đổi bí mật phía máy chủ

## 1. Vì sao cần hiểu pepper khi nâng cấp bảo vệ mật khẩu?

Khi người dùng tạo tài khoản, ứng dụng nên lưu **password verifier** được tạo bằng thuật toán băm mật khẩu thích nghi một chiều như **Argon2id, scrypt, bcrypt hoặc PBKDF2 với tham số phù hợp**, thay vì lưu mật khẩu dạng rõ. Verifier thường gồm một **salt ngẫu nhiên** và dữ liệu dẫn xuất từ mật khẩu. Salt cho phép xác minh sau này và **không cần giữ bí mật**.

Nếu kẻ tấn công chiếm được bảng tài khoản chứa salt và password hash, họ vẫn có thể **thử đoán mật khẩu offline**: lấy từng password ứng viên, chạy cùng thuật toán và so kết quả. Mật khẩu yếu vẫn có thể bị đoán, dù việc dùng hàm băm thích nghi khiến mỗi lần thử tốn tài nguyên hơn.

**Pepper** là một **bí mật bổ sung ở phía máy chủ**, sử dụng trong quá trình tạo hoặc xác minh password verifier nhưng **không lưu chung với bảng hash mật khẩu**. Khi thiết kế đúng, kẻ tấn công **chỉ lấy được database** sẽ thiếu pepper và không thể tự kiểm tra các password ứng viên theo cùng quy trình như ứng dụng. Đây là một lớp bảo vệ bổ sung, **không thay thế salt, thuật toán băm thích nghi, mật khẩu mạnh, rate limiting hoặc MFA**.

Trong module **Spring Security - authentication**, chủ đề này nằm ở nhóm **Nâng cấp mật khẩu** vì thêm pepper, đổi pepper và thay đổi thuật toán password hashing có ảnh hưởng trực tiếp đến khả năng xác thực **tất cả tài khoản đã tồn tại**. Đổi một biến cấu hình không phải là migration hoàn chỉnh.

**Mục tiêu học tập:** hiểu threat model, thiết kế nơi giữ bí mật, tổ chức version/key ID, phân biệt **luân chuyển thường kỳ** với **xử lý pepper bị lộ**, minh họa bằng Java 17 chạy được và tích hợp đúng ranh giới `PasswordEncoder`/`DaoAuthenticationProvider`.

## 2. Salt, pepper, password hash và khóa KMS khác nhau thế nào?

| Thành phần | Có cần bí mật? | Phạm vi | Nơi đặt thích hợp | Mục đích |
| --- | --- | --- | --- | --- |
| **Mật khẩu gốc** | Có | Mỗi người dùng | Người dùng nhập; chỉ tồn tại tạm thời trong luồng xử lý | Chứng minh sở hữu credential. |
| **Salt** | Không | Thường là một giá trị ngẫu nhiên mới cho mỗi lần tạo verifier | Lưu cùng password hash trong database | Làm các hash giống password không trùng nhau và giảm lợi thế bảng tính sẵn. |
| **Password hash/KDF output** | Là dữ liệu xác thực nhạy cảm dù không phải secret key | Mỗi credential | Kho tài khoản, có kiểm soát truy cập | Cho phép xác minh password; cần chống tấn công đoán offline. |
| **Pepper/khóa pepper** | **Có** | Có thể dùng chung cho nhiều tài khoản theo một phiên bản khóa | Vault/KMS/HSM ngoài database; quyền truy cập tối thiểu | Tăng bảo vệ nếu **chỉ** bản dump database bị lộ. |
| **Key ID/version** | Không | Mỗi verifier chỉ ra phiên bản khóa | Metadata cạnh hash hoặc trong verifier format | Chọn đúng khóa cũ/mới khi verify và luân chuyển. |
| **Tham số thuật toán** | Không | Theo profile/version | Trong hash format hoặc metadata | Chọn đúng KDF, salt, iterations/memory/work factor để xác minh hash cũ. |

**Điểm cần nhớ:** salt ngẫu nhiên **không phải pepper**. Một salt được để trong database không phải “pepper bị lộ”; thiết kế đó hoàn toàn bình thường. Ngược lại, pepper bị lưu cạnh hash trong cùng database hoặc backup sẽ **không còn tạo ra ranh giới bảo vệ độc lập** trước người đã lấy được cả hai.

Pepper thường là một khóa bí mật có entropy cao được tạo bằng bộ sinh ngẫu nhiên mật mã, không phải một từ dễ nhớ như `"MyCompany2026"`. Nó cũng không phải mật khẩu admin, JWT signing key, encryption key của session cookie hay API token: **tách khóa theo mục đích**, để một sự cố không kéo theo mọi chức năng khác.

### Một threat model chính xác hơn

Giả sử ứng dụng dùng một KDF hiện đại với salt và thêm pepper tách biệt:

- **Chỉ lộ database, vault/KMS còn an toàn:** pepper có thể làm khó hoặc ngăn quy trình kiểm tra password offline từ dữ liệu DB, nếu thiết kế **không đồng thời lưu một verifier không pepper mà attacker có thể dùng**.
- **Chỉ lộ pepper, không có database:** chưa chắc attacker xác minh được hash người dùng, nhưng phải coi đó là một sự kiện mất bí mật và đánh giá hệ quả, vì database có thể bị lộ riêng trong tương lai hoặc trước đó.
- **Lộ database và pepper:** lợi thế của pepper trước tấn công offline đã mất; mức bảo vệ còn lại phụ thuộc KDF, tham số và chất lượng password.
- **Attacker kiểm soát tiến trình ứng dụng có quyền dùng KMS:** có thể yêu cầu phép HMAC/verify thông qua ứng dụng hoặc chiếm dữ liệu trước KDF. Pepper không bảo đảm an toàn khi toàn bộ tầng chạy ứng dụng bị kiểm soát.
- **Vault/KMS không khả dụng:** thiết kế fail-closed có thể làm nhiều đăng nhập tạm thời không hoạt động. Pepper bổ sung một **phụ thuộc về tính sẵn sàng**, cần lập kế hoạch vận hành.

Đừng tuyên bố “có pepper thì database bị lộ cũng không sao”. Salt, khóa riêng, KDF, rate limiting, giám sát, bảo vệ cơ sở dữ liệu, quyền IAM và quy trình phản ứng sự cố vẫn quan trọng.

## 3. Hai chiến lược pepper: trước và sau KDF

OWASP Password Storage Cheat Sheet mô tả hai lớp chiến lược: **pre-hashing pepper** và **post-hashing pepper**. Việc chọn vị trí phối hợp bí mật có ảnh hưởng đến format lưu, khả năng tương thích, tốc độ và cách đổi khóa.

### 3.1. Pre-hashing pepper: đưa bí mật vào trước bước KDF

Một thiết kế minh họa:

```text
raw password
     |
     +-----> HMAC(pepper_key, domain_separator || raw_password)
                      |
                      v
          input bí mật hóa có độ dài xác định
                      |
        random salt --+--> Argon2id / scrypt / PBKDF2
                              |
                              v
                    stored KDF verifier
                    + salt + KDF profile + key ID
```

Ưu điểm: khi không có pepper, attacker không tính được đầu vào KDF đúng cho password ứng viên. Nếu dùng HMAC chuẩn và có phân tách mục đích khóa, tránh kiểu nối chuỗi tùy ý `pepper + password` với encoding không rõ ràng.

**Cần xem kỹ thuật toán:** với bcrypt, giới hạn xử lý mật khẩu theo byte và cách mã hóa HMAC đầu vào có thể tạo những bẫy về truncation/NUL/encoding. Không tự xây `bcrypt(pepper + rawPassword)` rồi cho đó là thiết kế chuẩn an toàn. Nếu buộc tự tích hợp, dùng mô hình được thiết kế, review và kiểm thử rõ ràng; cân nhắc một thư viện đã hỗ trợ đúng cơ chế.

**Không lưu pre-hash HMAC output** ngoài database nếu giá trị đó đóng vai trò mật khẩu thay thế. Khi bị lộ, nó có thể trở thành một secret mới đủ để thử chống lại verifier.

### 3.2. Post-hashing pepper: bảo vệ kết quả KDF bằng HMAC

Một mô hình khác:

```text
raw password + random salt
            |
            v
   Adaptive KDF (ví dụ PBKDF2-HMAC-SHA256)
            |
            v
   derived password verifier (tạm thời trong bộ nhớ)
            |
            +---- HMAC(pepper_key, context || salt || derived)
                              |
                              v
                  MAC tag + salt + KDF profile + key ID
                              |
                              v
                          Database

      Pepper key ở vault/KMS/HSM, không ở DB.
      Derived value KHÔNG được lưu như một verifier riêng.
```

Lần đăng nhập sau, ứng dụng đọc salt/KDF profile/key ID, lấy đúng pepper đã được phép sử dụng, tính lại KDF với password do người dùng cung cấp và dùng HMAC để tạo tag so sánh với giá trị đã lưu.

**Bẫy quan trọng nhất của post-hashing:** nếu database vẫn lưu **cả** `KDF(password,salt)` nguyên bản **và** `HMAC(pepper, KDF(...))`, attacker chỉ có database đã có thể tấn công đoán password bằng chính KDF không pepper. Lúc đó pepper không thực hiện được mục tiêu bảo vệ trước *database-only compromise*. Với mô hình post-hash ở đây, lưu **salt, params, key ID, MAC tag**; không lưu nguyên bản KDF output làm password verifier độc lập.

Cũng không nên dùng HMAC nhanh trực tiếp trên raw password để thay toàn bộ KDF. HMAC có pepper là **lớp bổ sung**, còn hàm băm mật khẩu thích nghi là cơ chế tạo chi phí đoán.

### 3.3. Chọn kiểu nào?

| Tiêu chí | Pre-hash pepper | Post-hash HMAC |
| --- | --- | --- |
| Điểm phối hợp secret | Trước KDF | Sau KDF |
| Phần lưu | KDF output có salt/params/key ID | MAC tag có salt/params/key ID; **không giữ unpeppered verifier** |
| Hỗ trợ KMS/HSM | Có thể dùng HMAC trên password trước KDF | Có thể dùng HMAC trên derived value sau KDF |
| Đổi pepper không biết raw password | Thường không thể chuyển đúng verifier | **Không thể** nếu chỉ lưu MAC tag mà không giữ unpeppered output |
| Rủi ro tích hợp | Encoding/giới hạn đầu vào KDF, lựa chọn HMAC | Lỡ lưu KDF output không pepper, định dạng/tag, key ID |
| Yêu cầu chung | KDF phù hợp, khóa riêng, format versioned, reset/migration | KDF phù hợp, khóa riêng, format versioned, reset/migration |

Hai hình thức đều có thể có các biến thể. **Chọn một thuật toán kết hợp cố định, công bố version và kiểm tra đầu-cuối**, thay vì thử nhiều phép nối pepper tùy ý theo password khi login.

## 4. Một password verifier cần những metadata gì?

Nếu tự thiết kế cơ chế pepper, bản ghi có thể mang các trường:

```text
user_id         = 42
password_format = "v1"
kdf_algorithm   = "PBKDF2WithHmacSHA256"
kdf_iterations  = 600000
salt_b64        = "..."
pepper_key_id   = "password-pepper-v1"
mac_tag_b64     = "..."
updated_at      = "..."
version         = 17
```

Đây chỉ là **schema minh họa**. Các giá trị `salt`, `iterations`, `format`, `pepper_key_id` **không bí mật**; việc biết chúng không được phép giúp attacker tính verifier khi thiếu pepper. Chuỗi tag là dữ liệu xác thực nhạy cảm, không đưa vào URL/log.

Một format đơn giản cho ví dụ Java ở phần 8 là:

```text
v1$k1$600000$<salt-base64url>$<hmac-tag-base64url>
```

Nó có **5 thành phần**: version, logical key ID, KDF iterations, salt và HMAC tag. ID ở đây chỉ minh họa; production nên dùng version ID/key reference do tổ chức quản lý, không đưa thông tin mật vào tên. Ví dụ cố định thuật toán và độ dài bằng `v1`; nếu đổi KDF, kiểu HMAC, cách ghép dữ liệu hoặc cách mã hóa, phải tạo **format version mới**, không âm thầm đổi ý nghĩa của `v1`.

Đừng dùng metadata người dùng có thể sửa để ép server chạy `iterations` khổng lồ hoặc giải mã dữ liệu tùy ý. **Parse chặt chẽ, giới hạn độ dài, xác minh thuật toán/format theo allow-list** trước khi tính KDF. Định dạng sai và key ID không hợp lệ phải thất bại an toàn.

### Key ID không phải key material

`pepper_key_id="k1"` được lưu cùng hash có nghĩa “hãy dùng khóa được kho bí mật nhận diện bằng ID k1”. Nó **không được** là giá trị pepper, API key để gọi KMS, password của vault hoặc ciphertext vô tình chứa nguyên pepper.

Thiết kế có thể tách hai lớp version:

- **Password format/KDF version:** thuật toán, rounds, salt length, cấu trúc tag.
- **Pepper key version:** secret KMS/HSM được dùng để tạo tag.

Tách được hai chiều này thì tăng work factor và luân chuyển pepper không buộc phải diễn ra cùng một thời điểm, dễ kiểm soát migration và rollback hơn.

## 5. Đặt pepper ở đâu: vault, KMS, HSM và quyền truy cập

### 5.1. Các lựa chọn và đánh đổi

| Cách giữ pepper | Đánh giá |
| --- | --- |
| Hard-code trong Java source/`application.yml` được commit | **Không phù hợp**: secret dễ lộ qua Git, artifact, log, backup. |
| Lưu cùng bảng `users` hoặc cùng database backup | **Không đáp ứng** mục tiêu tách secret khỏi DB. |
| Environment variable do deployment cấp | Có thể dùng trong một số kiến trúc, nhưng cần bảo vệ CI/CD, process environment, crash dump và rotation; không tự động tốt bằng vault/HSM. |
| Secrets manager/vault | Giữ secret ngoài DB, hỗ trợ IAM, audit, version, rotation; ứng dụng vẫn cần kiểm soát cách secret được cấp vào RAM. |
| HSM/KMS có hỗ trợ HMAC trên key không xuất được | Có thể giữ key material không rời phần cứng/dịch vụ và cho ứng dụng gọi MAC. Cần đánh giá latency, quota, chi phí và quyền gọi. |
| Secret được “mã hóa” bằng key nằm cùng repository/config | Chỉ đổi chỗ cất secret; attacker có cả hai phần vẫn giải mã được. |

**Ưu tiên:** tách miền quản trị của pepper khỏi kho user/password, dùng **workload identity/role của dịch vụ** để xin quyền tối thiểu thay vì API token lâu dài, audit truy cập và có quy trình sao lưu/khôi phục khóa an toàn.

Đừng giả định bất kỳ sản phẩm mang tên `KMS` nào đều cung cấp **HMAC-SHA256 với key không xuất được**. API, thuật toán, giới hạn request và chính sách key khác nhau theo nhà cung cấp. Nếu KMS chỉ mã hóa/giải mã secret để trả raw bytes cho ứng dụng, **pepper vẫn nằm trong RAM ứng dụng** trong một thời gian và có thể bị lộ khi tiến trình bị chiếm. Tuyên bố “khóa không bao giờ ra khỏi HSM” chỉ đúng với thiết kế thật sự thực hiện phép keyed operation trong boundary đó.

### 5.2. Tách quyền truy cập

Một phương án IAM có thể là:

- **Authentication service production:** chỉ được thực hiện MAC/verify với các key ID còn được phép; dùng key mới để tạo verifier mới.
- **Service quản trị/rotation:** được tạo version mới, điều chỉnh trạng thái active/retired và lịch chuyển đổi theo quy trình phê duyệt.
- **Migration job:** chỉ có quyền cần thiết để cập nhật hash khi đã xác minh mật khẩu/reset, không mặc nhiên được xem raw secret.
- **Database service:** có thể đọc/ghi password verifier theo quyền ứng dụng nhưng **không có quyền xuất pepper**.
- **Observability/analytics:** chỉ đọc ID/version, số lần lỗi và metrics đã giảm nhạy cảm; không đọc key hoặc raw password.

Nguyên tắc là **least privilege** và **separation of duties**. Không cấp quyền `admin` cho app chỉ để nó tìm được pepper mỗi khi login.

### 5.3. Phụ thuộc về tính sẵn sàng

Nếu vault/KMS mất kết nối, hoặc version cũ bị disabled ngoài kế hoạch, những account còn dùng key đó có thể không đăng nhập được. Vì vậy cần:

- Khóa cũ vẫn có thể verify trong **giai đoạn chuyển tiếp có thời hạn** của rotation thường kỳ.
- Quản lý quota/HMAC call throughput và latency của KMS theo tải xác thực.
- Có monitoring cho missing key, access denied, timeout, lỗi version và tỷ lệ login fail.
- Xác định fail-closed: **không bỏ qua HMAC, không tự match hash không pepper, không chuyển sang NoOp**.
- Tách phản hồi khách hàng và lỗi vận hành: sự cố KMS nên được quan sát/ứng phó như **authentication infrastructure unavailable**, không tự quy toàn bộ thành “user nhập sai mật khẩu”.
- Có phương án disaster recovery cho key **chưa bị lộ**. Backup phải được bảo vệ và kiểm thử restore; không lưu một bản raw key dễ truy cập cạnh database.

Không cache pepper vô thời hạn chỉ để tránh lỗi KMS. Nếu kiến trúc cho phép cache key ngắn hạn, cần threat model, hạn TTL, rotation/invalidation và bảo vệ memory. Với HSM key không xuất được, cache nên ở mức handle/connection/permission, không buộc phải xuất khóa thô.

## 6. Kế hoạch luân chuyển pepper bình thường (chưa có bằng chứng lộ)

Một lần rotation thông thường có thể do chính sách vòng đời secret, đổi hạ tầng hay giảm tác động nếu khóa bị lộ trong tương lai. Nó khác hẳn xử lý sự cố đã biết bị xâm phạm.

### 6.1. Trạng thái của một khóa

```text
CREATED  -> ACTIVE_FOR_WRITE  -> VERIFY_ONLY  -> RETIRED/REVOKED
               |                     |
               |                     +--> chỉ chấp nhận hash cũ trong
               |                          thời gian migration có kiểm soát
               |
               +--> hash đăng ký/đổi password mới
```

Trạng thái nên được quản lý trong hệ thống key management. Không dùng danh sách key vô hạn mà không có lịch loại bỏ. `ACTIVE_FOR_WRITE` là **một phiên bản rõ ràng**, không phải “key nào có timestamp mới nhất” theo suy đoán của mỗi instance.

### 6.2. Các bước triển khai an toàn

1. **Inventory:** thống kê số bản ghi theo key ID và password format; xác định tài khoản không hoạt động lâu, cơ chế reset và người chịu trách nhiệm.
2. **Chuẩn bị K2:** tạo khóa ngẫu nhiên mới trong vault/HSM, áp IAM, audit và kiểm tra dùng khóa trong staging.
3. **Deploy đọc được cả K1 và K2:** tất cả node xác thực đang hoạt động phải nhận diện version mới **trước** khi bất kỳ node nào bắt đầu ghi hash bằng K2.
4. **Chuyển chế độ ghi:** đặt K2 là active-for-write. Account mới hoặc người đổi/reset mật khẩu được bảo vệ bằng K2. K1 chỉ verify.
5. **Lazy migration sau login đúng:** khi nhận password hợp lệ của bản ghi K1, chạy lại quy trình tạo hash dưới K2 và ghi có transaction/optimistic locking.
6. **Theo dõi và xử lý tài khoản không login:** thống kê hash K1 còn lại, yêu cầu đổi/reset mật khẩu hoặc thực hiện chiến dịch tương tác phù hợp; đừng giữ K1 vô thời hạn.
7. **Rà soát nhiều instance và rollback:** node cũ phải đọc K2 hoặc chặn ghi K2 cho đến khi rollout đủ; chạy thử rollback và kiểm tra tình trạng đang ghi.
8. **Retire/revoke K1 khi đủ điều kiện:** xác định rõ thời điểm, chính sách đối với account chưa migrate và xác minh backup/restore; sau đó chấm dứt quyền verify bằng K1.
9. **Audit hậu kiểm:** số tài khoản chuyển sang K2, tài khoản cần reset, tỷ lệ lỗi, latency KMS và dữ liệu nhạy cảm không xuất hiện trong log.

**Không được đánh đồng “rotate active key” với “toàn bộ record đã được rehash”.** Thay K2 trong vault không làm HMAC tag của các bản ghi K1 tự đổi.

### 6.3. Vì sao không đổi pepper offline nếu không biết password?

Với mô hình post-hash ở mục 3.2, database có **chỉ MAC tag cũ, salt và metadata**; không có giá trị KDF gốc. Không thể dùng riêng `oldTag` để tạo `newTag` mà vẫn giữ khả năng xác minh bằng password gốc, vì HMAC không có phép chuyển đổi tương đương một cách tổng quát.

Với pre-hash pepper cũng tương tự: output KDF đã phụ thuộc pepper cũ. Để tạo verifier dưới K2 theo thiết kế, cần biết **raw password đúng** tại thời điểm đăng nhập/đổi password hoặc thực hiện reset.

Một số hệ thống giữ unpeppered KDF output riêng để “re-MAC offline”. Điều đó có thể làm được về mặt phép tính, nhưng **đồng thời trao cho attacker DB-only một verifier KDF không pepper** để đoán password. Do đó cách làm ấy **không phù hợp với threat model đã chọn** trừ khi bạn đã thiết kế một cơ chế khác được đánh giá riêng.

### 6.4. Cập nhật DB phải an toàn trước ghi đè đồng thời

Trình tự “đăng nhập bằng K1 → rehash K2 → UPDATE password” có thể đụng một thao tác **đổi/reset mật khẩu** trên thiết bị khác. Nếu UPDATE không có điều kiện, một login cũ có thể ghi đè hash được tạo bởi password mới.

Mẫu SQL khái niệm:

```sql
UPDATE user_credentials
SET password_verifier = :new_verifier,
    version = version + 1
WHERE user_id = :user_id
  AND version = :version_read
  AND password_verifier = :old_verifier;
```

Đây là **trích đoạn SQL minh họa**, không phải schema đầy đủ. Chỉ coi migration thành công khi số hàng update đúng kỳ vọng; nếu có xung đột, đọc lại trạng thái, không ghi đè cưỡng bức. Cũng cần tránh chạy rehash khi tài khoản bị khóa hoặc chính sách xác thực khác chưa cho phép thành công.

## 7. Khi pepper bị lộ: cần kế hoạch xử lý sự cố, không phải chỉ rotation

Đây là tình huống nghiêm trọng hơn rotation thường kỳ.

Giả sử xuất hiện bằng chứng khóa K1 đã bị truy cập trái phép, xuất hiện trong log hoặc repository, hay workload với quyền HMAC bị attacker chiếm. **Không thể coi chỉ thay active key thành K2 là đã bảo vệ toàn bộ những password có tag K1.**

### 7.1. Những hành động cần xem xét

1. **Containment:** giới hạn quyền truy cập, vô hiệu hóa tài khoản/hạ tầng bị xâm nhập, bảo toàn bằng chứng và xác định phạm vi quyền đối với key; không vội xóa log điều tra.
2. **Xác định phạm vi:** K1 dùng cho bao nhiêu tài khoản, version nào, có bằng chứng database/hash hoặc backup cũng bị lấy không, bao lâu hệ thống đã bị tác động.
3. **Tạo K2 độc lập:** trong một miền quản trị đã được làm sạch và kiểm soát, rà soát IAM và cơ chế cấp bí mật.
4. **Đánh giá nguy cơ đoán offline:** nếu attacker có cả K1 và DB, không còn lợi thế pepper cho dữ liệu đó. KDF và mật khẩu yếu trở thành tuyến phòng thủ còn lại.
5. **Bắt buộc đổi/reset password cho tài khoản bị ảnh hưởng** theo mức độ và chính sách sự cố; OWASP nhấn mạnh không thể thay pepper an toàn cho toàn bộ user mà không có password của họ.
6. **Kết thúc khả năng dùng K1** theo kế hoạch incident response; tránh giữ verify-only lâu để chờ tất cả user tự login nếu điều đó kéo dài cửa sổ bị xâm phạm.
7. **Thu hồi session/token khi cần**, kiểm soát login/reset flows, kiểm tra MFA và phát hiện credential stuffing/account takeover.
8. **Thông báo và khắc phục** theo yêu cầu pháp lý, quy trình nội bộ và nghĩa vụ với người dùng; loại bỏ secret đã rò trong pipeline/log/backups phù hợp khả năng thực tế.
9. **Không hứa khôi phục hoàn toàn chỉ bằng rehash:** nếu password đã bị attacker biết hoặc đoán được, tạo tag dưới K2 từ **cùng password** không thay đổi sự thật password đó có thể bị lạm dụng ở nơi khác.

**Quy tắc vận hành:** rotation bình thường có thể dùng giai đoạn đọc K1 và ghi K2 có thời hạn. **Pepper bị lộ** cần đánh giá và thường buộc reset, thu hồi key và giảm cửa sổ K1 còn được chấp nhận, chứ không thụ động chờ người dùng đăng nhập trong nhiều tháng.

### 7.2. Nếu mất pepper nhưng không bị lộ?

Nếu key cần thiết bị hủy mất và **không còn bản backup/khả năng truy cập hợp lệ**, những verifier phụ thuộc key đó có thể **không thể xác minh** dù user nhập đúng password. Đây là lỗi về **khả năng khôi phục key**, không đồng nghĩa password sai. Cách xử lý thường là quy trình khôi phục khóa hợp lệ hoặc reset password an toàn; tuyệt đối không bypass HMAC.

Thiết kế tài khoản recovery cần chống việc attacker lợi dụng tình trạng KMS lỗi để chiếm user, ví dụ không tự chấp nhận email chưa xác minh hoặc cho phép reset theo dữ liệu client tự khai.

## 8. Ví dụ Java 17 chạy độc lập: KDF + HMAC pepper + versioned rotation

Ví dụ này **không cần Spring Boot hay thư viện ngoài JDK 17**. Nó chứng minh cách *post-hashing pepper* hoạt động và luân chuyển khóa **khi chưa có bằng chứng compromise**. Chương trình:

- Dùng `PBKDF2WithHmacSHA256` với salt 16 byte ngẫu nhiên và 600.000 vòng cho minh họa.
- Dùng `HmacSHA256` với khóa 256 bit để tạo tag.
- Chỉ lưu trong password verifier: **format, key ID, số vòng, salt và HMAC tag**. **Không lưu derived key không pepper**.
- Key ring tạo K1/K2 tại runtime để mô phỏng hệ thống bí mật. **Production phải lưu/khôi phục khóa qua vault/KMS/HSM**; khóa sinh mới ở mỗi lần chạy demo không đọc được verifier từ lần chạy trước.
- Dùng `MessageDigest.isEqual` để so tag nhị phân; không dùng `String.equals` cho secret tag.
- Mô phỏng K1 còn được phép verify trong khi K2 là active-for-write; sau migration thì retire K1.

**Lưu ý:** đây là **bản học tập thể hiện thuật toán**, không phải thư viện password storage đã được audit để triển khai production. Ví dụ cố định format v1 và không tích hợp KMS thật, database, chống DoS, audit, limits cho mọi đầu vào hay quy trình reset.

### 8.1. File `PepperRotationDemo.java`

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PepperRotationDemo {

    private static final int ROUNDS = 600_000;
    private static final int SALT_BYTES = 16;
    private static final int KEY_BITS = 256;
    private static final int TAG_BYTES = 32;
    private static final String FORMAT = "v1";

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DECODER =
            Base64.getUrlDecoder();

    // Mô phỏng vault: chỉ giữ key ID -> SecretKey trong RAM của demo.
    // Không dùng Map chứa raw key làm kho bí mật production.
    static final class KeyRing {
        private final Map<String, SecretKey> byId = new HashMap<>();
        private String activeId;

        void add(String id, SecretKey key) {
            if (byId.containsKey(id)) {
                throw new IllegalArgumentException("Duplicate key ID");
            }
            byId.put(id, key);
        }

        void activate(String id) {
            if (!byId.containsKey(id)) {
                throw new IllegalArgumentException("Unknown active key ID");
            }
            activeId = id;
        }

        String activeId() {
            return activeId;
        }

        SecretKey key(String id) {
            return byId.get(id);
        }

        void retire(String id) {
            if (id.equals(activeId)) {
                throw new IllegalStateException("Cannot retire active key");
            }
            byId.remove(id);
        }
    }

    static final class PasswordVerifier {
        private final KeyRing keys;

        PasswordVerifier(KeyRing keys) {
            this.keys = keys;
        }

        String encode(char[] password) throws GeneralSecurityException {
            byte[] salt = new byte[SALT_BYTES];
            RANDOM.nextBytes(salt);

            String keyId = keys.activeId();
            SecretKey key = keys.key(keyId);
            if (key == null) {
                throw new IllegalStateException("Active pepper unavailable");
            }

            byte[] derived = pbkdf2(password, salt);
            byte[] tag;
            try {
                tag = hmac(key, salt, derived);
            } finally {
                Arrays.fill(derived, (byte) 0);
            }

            return FORMAT + "$" + keyId + "$" + ROUNDS + "$"
                    + ENCODER.encodeToString(salt) + "$"
                    + ENCODER.encodeToString(tag);
        }

        boolean matches(char[] password, String stored)
                throws GeneralSecurityException {

            if (password == null || stored == null) {
                return false;
            }

            String[] parts = stored.split("\\$", -1);
            if (parts.length != 5 || !FORMAT.equals(parts[0])
                    || !Integer.toString(ROUNDS).equals(parts[2])) {
                return false;
            }

            // Thiếu key không cho phép bypass pepper.
            // Production cần phân biệt outage với mật khẩu sai trong audit.
            SecretKey key = keys.key(parts[1]);
            if (key == null) {
                return false;
            }

            byte[] salt;
            byte[] expectedTag;
            try {
                salt = DECODER.decode(parts[3]);
                expectedTag = DECODER.decode(parts[4]);
            } catch (IllegalArgumentException invalidFormat) {
                return false;
            }

            if (salt.length != SALT_BYTES
                    || expectedTag.length != TAG_BYTES) {
                return false;
            }

            byte[] derived = pbkdf2(password, salt);
            try {
                byte[] actualTag = hmac(key, salt, derived);
                return MessageDigest.isEqual(expectedTag, actualTag);
            } finally {
                Arrays.fill(derived, (byte) 0);
            }
        }

        boolean needsRehash(String stored) {
            if (stored == null) {
                return false;
            }
            String[] parts = stored.split("\\$", -1);
            return parts.length == 5
                    && FORMAT.equals(parts[0])
                    && !keys.activeId().equals(parts[1]);
        }

        private static byte[] pbkdf2(char[] password, byte[] salt)
                throws GeneralSecurityException {

            PBEKeySpec spec =
                    new PBEKeySpec(password, salt, ROUNDS, KEY_BITS);
            try {
                SecretKeyFactory factory =
                        SecretKeyFactory.getInstance(
                                "PBKDF2WithHmacSHA256");
                return factory.generateSecret(spec).getEncoded();
            } finally {
                spec.clearPassword();
            }
        }

        private static byte[] hmac(
                SecretKey pepper, byte[] salt, byte[] derived)
                throws GeneralSecurityException {

            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(pepper);

            // Domain separation: HMAC key này chỉ dùng cho mục đích
            // password verifier với format v1.
            mac.update("pwd-verifier:v1".getBytes(
                    StandardCharsets.UTF_8));
            mac.update((byte) 0);
            mac.update(salt);
            mac.update(derived);
            return mac.doFinal();
        }
    }

    private static SecretKey randomPepper()
            throws GeneralSecurityException {
        KeyGenerator generator =
                KeyGenerator.getInstance("HmacSHA256");
        generator.init(256);
        return generator.generateKey();
    }

    public static void main(String[] args) throws Exception {
        KeyRing keys = new KeyRing();
        keys.add("k1", randomPepper());
        keys.activate("k1");

        PasswordVerifier verifier = new PasswordVerifier(keys);
        char[] password = "DemoPass123!".toCharArray();
        char[] wrong = "wrong-password".toCharArray();

        try {
            // Bản ghi được tạo dưới K1.
            String oldRecord = verifier.encode(password);
            String[] oldFields = oldRecord.split("\\$", -1);

            System.out.println("record.version=" + oldFields[0]);
            System.out.println("record.kid=" + oldFields[1]);
            System.out.println("record.containsRaw="
                    + oldRecord.contains("DemoPass123!"));
            System.out.println("k1.correct="
                    + verifier.matches(password, oldRecord));
            System.out.println("k1.wrong="
                    + verifier.matches(wrong, oldRecord));

            // Luân chuyển BÌNH THƯỜNG: K2 ghi mới, K1 chỉ đọc cũ.
            keys.add("k2", randomPepper());
            keys.activate("k2");

            System.out.println("rotation.oldWorks="
                    + verifier.matches(password, oldRecord));
            System.out.println("rotation.needsRehash="
                    + verifier.needsRehash(oldRecord));

            // Raw password chỉ có ở thời điểm đăng nhập/reset.
            // Trong DB thật: UPDATE bản ghi với version/compare-and-set.
            String newRecord = verifier.encode(password);
            System.out.println("new.kid="
                    + newRecord.split("\\$", -1)[1]);
            System.out.println("new.correct="
                    + verifier.matches(password, newRecord));

            // Chỉ retire K1 khi không còn user nào cần record K1
            // hoặc đã có chiến lược reset account tương ứng.
            keys.retire("k1");

            System.out.println("retired.oldUnavailable="
                    + !verifier.matches(password, oldRecord));
            System.out.println("retired.newWorks="
                    + verifier.matches(password, newRecord));
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrong, '\0');
        }
    }
}
```

### 8.2. Biên dịch, chạy và stdout

Cần **JDK 17+**, không cần Gradle/Maven vì chỉ dùng Java standard library. Lưu file UTF-8 và chạy:

```bash
javac -encoding UTF-8 PepperRotationDemo.java
java PepperRotationDemo
```

**Các dòng stdout do chương trình in ra**, không kể thông báo riêng của JVM nếu môi trường có:

```text
record.version=v1
record.kid=k1
record.containsRaw=false
k1.correct=true
k1.wrong=false
rotation.oldWorks=true
rotation.needsRehash=true
new.kid=k2
new.correct=true
retired.oldUnavailable=true
retired.newWorks=true
```

Chương trình **không in pepper, salt, derived key hoặc HMAC tag**. Hash/tag có ngẫu nhiên nên giá trị thực tế thay đổi; những dòng đã in dựa trên **thuộc tính ổn định** của quy trình. Số vòng 600.000 có thể khiến chương trình chạy chậm trên một số máy; đó là work factor tính toán, không phải lỗi treo.

### 8.3. Đọc kết quả theo thứ tự

**`record.version=v1` và `record.kid=k1`:** metadata cho biết thuật toán/format và ID khóa đang dùng; bản ghi **không chứa bản thân key**.

**`record.containsRaw=false`:** chuỗi lưu không chứa mật khẩu trong demo. Lưu ý rằng “không chứa raw string” **chưa đủ để chứng minh an toàn**; thiết kế còn phải có KDF thích nghi, salt, pepper tách biệt và kiểm thử mật mã.

**`k1.correct=true` / `k1.wrong=false`:** phải có đúng password, salt, tham số KDF và K1 mới tái tạo được MAC tag.

**`rotation.oldWorks=true`:** chỉ sau khi K2 được kích hoạt để **ghi**, K1 vẫn tồn tại trong key ring **để đọc**. Đây là cơ chế chuyển tiếp không gián đoạn, không dành để kéo dài vô hạn khi có compromise.

**`rotation.needsRehash=true`:** bản ghi đang dùng ID khác với key active. Nó là dấu hiệu **có thể chuyển đổi sau xác thực đúng**, không tự động làm DB thay đổi.

**`new.kid=k2`:** nhập raw password đúng vào luồng tạo verifier mới theo K2. Do salt mới, tag cũng mới.

**`retired.oldUnavailable=true`:** khi bỏ K1, bản ghi cũ không còn xác thực được. Trong production, đây là sự cố với tài khoản chưa migrate, không nên âm thầm trả thông báo sai mật khẩu cho người dùng hoặc bypass pepper để “sửa nhanh”.

**`retired.newWorks=true`:** bản ghi đã chuyển đổi sang K2 vẫn xác thực được khi K1 đã retire.

### 8.4. Giới hạn của ví dụ

- `KeyRing` chỉ mô phỏng vault trong cùng tiến trình. Khởi động lại chương trình sẽ tạo **K1/K2 mới**, không thể đọc record từ tiến trình cũ. Production phải giữ **cùng key material theo version** qua deploy/region/instance cho đến khi key được retire có kiểm soát.
- `KeyGenerator` tạo key ngẫu nhiên bằng JCA; đây **không tự chứng minh** key nằm trong HSM hay phần triển khai đạt chứng nhận FIPS.
- `PasswordVerifier.matches` trả `false` khi không có key. Ứng dụng thật nên phân biệt **key unavailable/access denied** với **password mismatch** cho alert và SLO, vẫn giữ thông điệp bên ngoài an toàn và **không bỏ qua kiểm tra**.
- Ví dụ cố định PBKDF2-HMAC-SHA256/600.000 rounds và format `v1`. Nếu muốn cho phép nhiều KDF/cost profile, cần một parser/registry version được kiểm thử và giới hạn chặt.
- `MessageDigest.isEqual` phù hợp để so tag nhị phân có độ dài đã kiểm tra. Tính bảo mật tổng thể còn phụ thuộc code parse, xử lý lỗi, KMS, thời gian phản hồi, cách tìm tài khoản và throttling.
- Việc xóa `char[]` và `derived` theo khả năng Java giúp giảm thời gian giữ secret, nhưng **không có lời hứa toàn bộ bản sao trong JVM/GC đã được xóa tuyệt đối**.
- Không kiểm thử bằng cách lấy tag hiện có rồi áp HMAC lần nữa dưới K2: như vậy **không tương đương** một verifier được tạo từ password gốc.

## 9. Tích hợp với Spring Security: ai chịu trách nhiệm ở đâu?

`DaoAuthenticationProvider` dùng `UserDetailsService` để tải `UserDetails`, rồi gọi `PasswordEncoder.matches(rawPassword, encodedPassword)`. Vì vậy nếu hệ thống dùng pepper, logic phiên bản pepper phù hợp nên được gói thành **một implementation `PasswordEncoder` đã kiểm thử**, hoặc một adapter với dịch vụ KMS chuyên trách.

```text
HTTP login filter
        |
        v
AuthenticationManager / ProviderManager
        |
        v
DaoAuthenticationProvider
        |
        +--> UserDetailsService.loadUserByUsername()
        |      -> lấy password_verifier (format, KDF, key ID, salt, tag)
        |      -> lấy trạng thái account, authorities
        |
        +--> PasswordEncoder.matches(raw, stored)
        |      -> parse format / key ID
        |      -> PBKDF2/Argon2id/... theo profile
        |      -> HMAC với pepper đúng version qua vault/KMS
        |      -> so tag an toàn
        |
        +--> Account-state checks / optional password upgrade
        |
        v
Authenticated Authentication (khi tất cả điều kiện hợp lệ)
        |
        v
SecurityContext do filter web quản lý
```

**Không** đặt logic pepper trong controller để sau đó tự cấp `UsernamePasswordAuthenticationToken.authenticated(...)` từ dữ liệu client. Làm vậy có nguy cơ bỏ qua account locked/disabled/expired, các cơ chế chống brute force và authority mapping.

### 9.1. Chữ ký của một adapter `PasswordEncoder`

Ví dụ **cấu trúc minh họa**, không phải class độc lập vì `PepperVerifierService` và `KeyProvider` do dự án thiết kế:

```java
public final class PepperAwarePasswordEncoder implements PasswordEncoder {

    private final PepperVerifierService service;

    public PepperAwarePasswordEncoder(PepperVerifierService service) {
        this.service = service;
    }

    @Override
    public String encode(CharSequence rawPassword) {
        return service.encodeUsingActiveVersion(rawPassword);
    }

    @Override
    public boolean matches(CharSequence rawPassword, String stored) {
        return service.verifyUsingRecordedKeyId(rawPassword, stored);
    }

    @Override
    public boolean upgradeEncoding(String stored) {
        return service.isOlderThanActivePolicy(stored);
    }
}
```

Adapter phải giải quyết rành mạch:

- **Encode:** dùng key active-for-write do hệ thống tin cậy cấp, **không** do client gửi.
- **Matches:** dùng key ID/profile đã lưu, chỉ chấp nhận danh sách version được phép; key đang verify-only phải có chính sách thời hạn rõ.
- **UpgradeEncoding:** đánh dấu khi key ID, KDF cost hoặc format cũ cần chuyển; đây **không phải thao tác cập nhật DB**.
- **Lỗi vault/KMS:** ném/ghi nhận lỗi vận hành phù hợp; không trả `true`, không fallback sang KDF không pepper và không tiết lộ key trong exception message.
- **Thiết kế mật mã:** không cho phép người gọi chuyển thuật toán hoặc số vòng tự do theo request; chỉ đọc profile được chấp thuận.

### 9.2. Kết nối `DaoAuthenticationProvider` và dịch vụ nâng hash

Đoạn **wiring minh họa**, cần các bean của ứng dụng:

```java
DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider(userDetailsService);

provider.setPasswordEncoder(pepperAwarePasswordEncoder);
provider.setUserDetailsPasswordService(userDetailsPasswordService);
```

Trong Spring Security 6.5, `DaoAuthenticationProvider` hỗ trợ `setUserDetailsPasswordService` để cập nhật verifier sau lần xác thực thành công khi encoder báo cần nâng cấp. `UserDetailsPasswordService.updatePassword(user, newPassword)` nhận **giá trị đã encode** theo format mới, không phải mật khẩu dạng rõ. `UserDetailsService` vẫn phải đọc từ kho tài khoản và trả password verifier kèm metadata, không tự tính password hash ngoài transaction một cách tùy tiện.

Quan trọng khi KMS tham gia đường login:

1. Không chặn quá nhiều luồng worker bằng một KMS call chậm mà không có giới hạn/timeout.
2. Không log raw password hoặc pepper khi exception trong provider.
3. Không để key ID từ database dẫn tới truy vấn secret tuỳ ý ngoài allow-list/quyền của ứng dụng.
4. Nếu password được mã hóa dưới nhiều `{id}` khác nhau, có thể dùng `DelegatingPasswordEncoder` để chọn **password format/KDF algorithm**, trong khi chính pepper-aware encoder xử lý **key ID** bên trong. Không lẫn hai lớp ID này.
5. Đừng tự động nhận `{noop}` hoặc một formatter legacy insecure chỉ để vá lỗi migration. Chính sách hỗ trợ hash cũ phải được giới hạn và giám sát.

### 9.3. Hợp đồng `PasswordEncoder` không tự giải quyết vault/key lifecycle

Spring Security không tự tạo pepper, HSM key, rotation schedule hay recovery plan cho hệ thống chỉ vì có bean `PasswordEncoder`. Các việc đó là trách nhiệm thiết kế của ứng dụng/hạ tầng.

Một `Pbkdf2PasswordEncoder` có tham số `secret` bổ sung không đồng nghĩa sản phẩm đã có **hệ quản trị versioned pepper**. Đổi secret mà không quản lý verifier cũ có thể khiến toàn bộ user dùng secret cũ bị từ chối. Nếu chọn extension này, cần hiểu chính xác nó kết hợp secret ra sao, format nào được lưu và cơ chế lookup theo key ID trước khi deploy.

Tương tự, sử dụng `DelegatingPasswordEncoder` với ID `{bcrypt}` không chứng minh mọi hash được pepper: ID chỉ xác định encoder đã đăng ký. Nếu thay mapping `bcrypt` sang cơ chế không tương thích, các password cũ có thể thất bại. Hãy dành ID/version riêng cho profile mới và giữ decoder cũ cho giai đoạn migration.

## 10. Kế hoạch nâng cấp hệ thống đang có password hash không pepper

Nhiều ứng dụng đã lưu `{bcrypt}...` hoặc PBKDF2 theo Spring Security từ trước. Thêm pepper là **thay đổi format/xác minh**, không phải một cấu hình thuần túy.

### 10.1. Những nhóm tài khoản cần quản lý

| Dữ liệu hiện có | Cách verify trong giai đoạn chuyển tiếp | Cách nâng cấp |
| --- | --- | --- |
| Hash BCrypt/PBKDF2/Argon2id hợp lệ nhưng chưa pepper | Decoder cũ theo ID đã lưu | Sau password đúng, encode sang verifier có pepper + version mới. |
| Verifier pepper K1 | Key K1 verify-only (nếu chưa bị lộ), format K1 | Sau password đúng/reset, rehash với K2. |
| Verifier pepper K2 | K2 đang active | Không cần đổi chỉ vì có K1 trong key ring. |
| Plaintext/`{noop}` legacy | Đánh giá và cô lập riêng; không tự mặc định cho phép | Ưu tiên đánh giá sự cố, reset và chuyển sang KDF phù hợp. |
| Unknown format/missing key ID | Fail-closed, theo dõi và sửa dữ liệu có kiểm soát | Không thử tất cả key/encoder vô hạn cho đến khi có kết quả true. |

**Không xem việc thêm prefix như là thêm pepper.** `{peppered-v1}{bcrypt}...` không tự trở thành một HMAC verifier. Mỗi ID phải ánh xạ tới đúng implementation thật và đúng dữ liệu được tạo bởi nó.

### 10.2. Các bước triển khai

1. **Phân loại dữ liệu cũ** bằng bản ghi mẫu không nhạy cảm và số lượng theo ID/profile, tránh dump hash hàng loạt ra log.
2. **Chọn threat model** DB-only compromise, mức cần HSM, hạn mức KMS, kế hoạch recovery và cách xử lý khi mất key.
3. **Đóng băng decoder legacy**, xây password encoder versioned mới và test golden vectors của cả hai đường.
4. **Deploy dual-read trước:** mọi node biết đọc format cũ và mới, nhưng chưa chuyển ghi để tránh node cũ không nhận diện bản ghi mới.
5. **Chuyển new-write:** đăng ký/reset/đổi password ghi format pepper mới.
6. **Opportunistic upgrade:** khi login thành công và policy cho phép, rehash password raw sang format mới; dùng `UserDetailsPasswordService` và compare-and-set.
7. **Cập nhật tài khoản không hoạt động:** chủ động yêu cầu đổi/reset theo kế hoạch, không giữ decoder cũ vĩnh viễn.
8. **Quan sát và kiểm toán:** metrics theo version, tỷ lệ upgrade, lỗi vault, latency KDF, memory/CPU và tỷ lệ authentication fail.
9. **Rút ngắn legacy window** theo mức độ rủi ro; xác định điều kiện retire các ID/key cũ.
10. **Diễn tập rollback/DR:** xác nhận key version không mất khi thay pod, region, restore database, đổi KMS account và rolling deploy.

Nếu muốn nâng **work factor** đồng thời với thêm pepper, metadata phải thể hiện cả hai thay đổi. Không đổi tham số KDF của ID cũ trong registry khiến hash cũ không còn verify.

### 10.3. Xử lý mật khẩu bị quên và account không đăng nhập

Vì một verifier được tạo đúng là **một chiều**, hệ thống không thể “giải mã” password để thêm pepper. Tài khoản không đăng nhập trong giai đoạn rotation cần:

- Gửi luồng khôi phục/reset theo cơ chế xác minh danh tính thích hợp.
- Giới hạn thời gian token reset, chống replay và abuse.
- Không dùng email chưa xác minh hay token dễ đoán làm bằng chứng sở hữu tài khoản.
- Không gửi password mới qua email dạng rõ.
- Sau reset, tạo verifier bằng key active và chính sách KDF hiện hành.
- Có phương án đối với user không phản hồi trước hạn retire key cũ, ví dụ bắt reset ở lần truy cập sau.

Một tổ chức không nên giữ pepper cũ bị nghi đã lộ vô thời hạn chỉ để tránh gây bất tiện cho người dùng.

## 11. Kiểm thử và tiêu chí chấp nhận

### 11.1. Ma trận test chức năng và bảo mật

| Bài test | Đầu vào/thiết lập | Kỳ vọng |
| --- | --- | --- |
| **Đúng password** | Password và key ID tồn tại | Xác minh đúng, không lộ verifier. |
| **Sai password** | Password sai, key đúng | Xác minh thất bại, không cấp `Authentication`. |
| **Salt riêng** | Tạo verifier hai lần cho cùng password/key | Stored verifier khác nhau do salt ngẫu nhiên. |
| **DB-only leak** | Chỉ có metadata và tag trong DB | Không có unpeppered KDF output để thử đoán offline trực tiếp. |
| **Version mismatch** | Format hoặc KDF profile không được hỗ trợ | Từ chối có kiểm soát; không chọn default insecure. |
| **K1 verify-only** | Ghi mới bằng K2, bản ghi K1 còn hợp lệ | K1 có thể verify trong thời gian chuyển tiếp có chính sách. |
| **Rehash after correct login** | Bản ghi K1, raw password đúng | Bản ghi chuyển sang K2, giữ account và quyền. |
| **No rehash after wrong login** | Bản ghi K1, password sai | Không mutate password verifier. |
| **K1 retired** | Bản ghi cũ chưa migrate | Không bypass pepper; kích hoạt flow recovery/failure rõ ràng. |
| **KMS unavailable** | Mất quyền hoặc timeout khi dùng key | Fail-closed, observability và response vận hành phù hợp. |
| **Concurrent reset vs upgrade** | Một login cũ cùng lúc đổi password | Compare-and-set ngăn rehash cũ ghi đè password mới. |
| **Rolling deployment** | Node cũ/mới phục vụ cùng user | Node nào cũng đọc được format đang ghi hoặc rollout được chặn đúng. |
| **Restore from backup** | Database được khôi phục, key version vẫn cần dùng | Có khả năng verify hoặc có kế hoạch reset/DR rõ. |
| **Compromise drill** | K1 bị đánh dấu lộ | Chặn write K1, kích hoạt reset, containment, đánh giá revocation. |

### 11.2. Những bất biến cần kiểm tra ở cấp dữ liệu

- Mật khẩu gốc **không** tồn tại trong bảng user, JSON response, log hoặc tracing.
- Pepper/key bytes **không** tồn tại trong database/backup chứa password verifier.
- Database **không** lưu một verifier KDF không pepper đủ để tự kiểm tra password ứng viên nếu kiến trúc post-HMAC được chọn.
- Mỗi record có metadata đủ để chọn thuật toán và key version một cách xác định.
- Không chấp nhận format có trường tùy ý có thể gây tiêu tốn CPU vô hạn hoặc truy vấn secret ngoài allow-list.
- Password migration chỉ chạy sau xác minh hợp lệ, và viết bằng transaction/phiên bản đúng.
- Hết thời hạn chuyển tiếp thì key/ID cũ thực sự được rút khỏi đường verify.
- Khi key provider lỗi, hệ thống không tự rơi về NoOp, bcrypt không pepper hoặc mật khẩu mặc định.

### 11.3. Test Spring Security đúng phạm vi

`@WithMockUser` hữu ích cho kiểm tra authorization nhưng **không chứng minh `PepperAwarePasswordEncoder.matches` đã chạy**. Để test đường login thực:

1. Tạo user có password verifier pepper version K1/K2 trong một store cô lập.
2. Dùng `DaoAuthenticationProvider` với encoder adapter thật hoặc một fake KMS theo contract được kiểm thử.
3. Gọi `AuthenticationManager.authenticate(...)` với username/password đúng; kiểm tra authenticated token, principal và authorities mong đợi.
4. Gọi với password sai; kiểm tra từ chối.
5. Làm KMS trả lỗi hoặc mất quyền; xác nhận fail-closed và không lộ thông tin key.
6. Cấu hình `UserDetailsPasswordService` trong test upgrade; xác nhận sau login đúng hash được ghi bằng key active.
7. Kiểm tra test account status: locked/disabled không được đăng nhập chỉ vì HMAC tag khớp.
8. Khi test HTTP, chạy filter chain thật với Basic/form login, TLS/session/CSRF policy tương ứng.

Chọn data fixtures giả, không copy pepper production hoặc password thật vào source, test fixtures, CI logs hay tài liệu.

## 12. Quan sát vận hành mà không làm lộ bí mật

Hệ thống cần biết việc rotation có tiến triển hay không, nhưng không được dùng log như một kho chứa secret thứ hai.

**Metrics hữu ích:**

- Số lượng verifier theo **format/KDF version/pepper key ID** (chỉ key ID).
- Tỷ lệ password rehash từ K1 sang K2 theo ngày.
- Số tài khoản còn phụ thuộc key verify-only trước thời điểm retire.
- Số yêu cầu KMS/HSM thất bại do timeout, denied, key disabled, rate limit.
- `p50/p95/p99` thời gian của KDF và keyed MAC, lượng CPU và concurrency.
- Tỷ lệ login failure ở mức tổng hợp, phân biệt một sự cố HSM với lỗi password sai.
- Đã thực hiện diễn tập backup/restore, reset và key retirement lần cuối khi nào.

**Không log:** password raw, derived key, pepper bytes, toàn bộ verifier/hash, key material trả từ vault, request body login, HTTP Authorization header, token reset, API credential truy cập secrets manager.

**Audit quyền cao:** ai tạo/activate/disable key, workload nào dùng key, khi nào quyền truy cập bị từ chối, ai phê duyệt rotation và khi nào K1 được retire. Giữ chính sách chống sửa log và đồng bộ thời gian.

**Alert ưu tiên cao:** xuất hiện truy cập key từ workload/region lạ, thay đổi IAM bất thường, secret bị export vào CI/log, số lần dùng K1 tăng sau ngày chuyển ghi K2, nhiều login đồng thời thất bại vì KMS, hoặc DB ghi format cũ khi policy đã cấm.

## 13. Các sai lầm phổ biến

1. **“Pepper giống salt.”** Không: salt thường có trong DB và riêng theo verifier; pepper là secret được quản lý ngoài DB.
2. **“Có pepper thì khỏi cần băm mật khẩu chậm.”** Sai: HMAC nhanh không thay thế Argon2id/scrypt/bcrypt/PBKDF2.
3. **“Đặt pepper cạnh cột hash trong DB là đủ.”** Không có ranh giới độc lập trước một bản dump DB.
4. **“Để pepper trong Git nhưng mã hóa Base64.”** Base64 là cách biểu diễn, không phải bảo vệ secret.
5. **“Hard-code pepper trong application.yml rồi gắn nhãn secret.”** Nếu cùng repository/artifact/backup, secret có thể bị chiếm cùng ứng dụng.
6. **“Lưu cả KDF output và HMAC tag để dễ rotate.”** Với post-HMAC, unpeppered KDF output có thể cho attacker DB-only đường đoán password offline, làm mất mục tiêu pepper.
7. **“Đổi KMS active key là mọi user đã dùng key mới.”** Hash cũ vẫn gắn K1 đến khi được tạo lại.
8. **“Có thể re-MAC K1 tag thành K2 tag mà không có raw password.”** Không theo cấu trúc post-HMAC chỉ lưu tag.
9. **“K1 lộ thì cứ giữ K1 verify-only chờ login tự nhiên.”** Có thể duy trì đường rủi ro quá lâu; cần reset/incident response theo phạm vi ảnh hưởng.
10. **“Thay pepper là thu hồi được password đã bị đoán.”** Không: password bị lộ/đoán vẫn có thể bị lạm dụng; phải đổi/reset credential.
11. **“Pepper không cần version.”** Không có key ID, rotation và khôi phục dễ trở thành phép thử nhiều key không kiểm soát.
12. **“Key ID là key.”** ID chỉ là nhãn công khai, key material phải được bảo vệ riêng.
13. **“Đã gọi KMS thì key chắc chắn không vào RAM ứng dụng.”** Chỉ đúng nếu KMS/HSM thực hiện phép keyed operation mà không trả raw key.
14. **“App cần quyền admin KMS để login.”** Quyền quá rộng làm tăng blast radius; dùng IAM tối thiểu.
15. **“Nếu KMS hỏng, cho phép đăng nhập không pepper.”** Bypass là hạ mức bảo mật không được phép.
16. **“Mọi lỗi KMS đều là user nhập sai password.”** Che mất sự cố vận hành; cần phân loại nội bộ và phản hồi không lộ bí mật.
17. **“Cùng một secret dùng cho JWT, cookie và pepper cho tiện.”** Reuse key liên mục đích làm sự cố lan rộng, trái domain separation.
18. **“Cập nhật hash sau login không cần concurrency control.”** Có thể ghi đè thao tác đổi/reset mật khẩu gần đó.
19. **“Thay mapping `{bcrypt}` thành pepper mới không cần version.”** Làm những bản ghi hash cũ bị giải mã sai.
20. **“Mọi user đều đăng nhập đủ thường xuyên nên không cần reset.”** Tài khoản không hoạt động sẽ ngăn retire K1; cần lộ trình rõ.
21. **“Có thể chọn iterations từ request hoặc metadata chưa validate.”** Attacker có thể gây DoS bằng giá trị bất thường.
22. **“Mã Java có `char[]` thì đã xóa sạch password khỏi JVM.”** Có thể còn bản copy, logs, request buffers hoặc string bất biến.
23. **“Một lần test thành công là đủ chứng minh kiến trúc an toàn.”** Cần test data, KMS outage, rotation, multi-node, rollback và compromise.
24. **“Pepper giải quyết rate limiting/MFA.”** Không: các lớp bảo vệ chống online guessing và account takeover là trách nhiệm riêng.
25. **“Chỉ cần tính số tài khoản K2, không cần biết còn bao nhiêu K1.”** Không thể quyết định thời điểm retire an toàn nếu thiếu inventory cũ.
26. **“Reset password lúc sự cố là chỉ gửi email có mật khẩu mới.”** Không gửi raw password; dùng luồng reset có token ngắn hạn và xác minh danh tính.
27. **“Thay pepper thường kỳ buộc reset tất cả ngay trong mọi hệ thống.”** Với key cũ chưa bị lộ, có thể chuyển tiếp có thời hạn sau login đúng; khi **compromise**, chính sách nghiêm ngặt hơn và thường buộc reset.
28. **“Số vòng KDF cao luôn tốt, không cần benchmark.”** Xác minh mật khẩu tốn tài nguyên; cần cân bằng bảo mật, latency và chống DoS.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Salt và pepper khác nhau ở đâu? Salt có phải lưu trong KMS không?

**Đáp án:** Salt là dữ liệu ngẫu nhiên riêng cho verifier, có thể công khai và lưu trong DB cùng hash. Pepper là secret phía server, cần được giữ riêng ở vault/KMS/HSM. Salt không cần cất trong KMS.

**Câu 2.** Attacker lấy toàn bộ DB nhưng không lấy được pepper. Còn có thể tấn công offline hash mật khẩu không?

**Đáp án:** Nếu thiết kế pepper đúng và DB **không chứa unpeppered verifier**, attacker không thể tái tạo phép verify từ DB đơn thuần. Nhưng khả năng bảo vệ còn phụ thuộc mô hình tấn công, thiết kế kết hợp và việc attacker có thể khai thác tầng ứng dụng hay KMS hay không.

**Câu 3.** Vì sao lưu cả PBKDF2 output và HMAC tag trong DB lại là bẫy khi chọn post-hash pepper?

**Đáp án:** PBKDF2 output có salt có thể tự làm verifier cho việc thử password ứng viên, nên người lấy DB không cần pepper để kiểm tra đoán offline. Không lưu KDF output không pepper nếu mục tiêu là ngăn trường hợp đó.

**Câu 4.** Có key K1 cho hash cũ, muốn mọi hash mới dùng K2. Chỉ đổi `activeKeyId` đã đủ migrate chưa?

**Đáp án:** Chưa. Nó chỉ đổi đường ghi mới. Hash K1 cần được tạo lại khi có raw password hợp lệ (login thành công/reset) và cập nhật DB an toàn; tài khoản chưa hoạt động cần lộ trình riêng.

**Câu 5.** Vì sao không tự tính K2-tag bằng HMAC(K2, K1-tag)?

**Đáp án:** Đó là một giá trị khác, không tương đương phép tạo verifier v1 từ password và salt. K1-tag không chứa thông tin cần thiết để tái tạo KDF gốc.

**Câu 6.** Nếu K1 bị lộ cùng bản dump DB, có thể chỉ tạo K2 rồi không reset password không?

**Đáp án:** Không nên coi là đủ. K1 + DB đã cho attacker cơ hội đoán password cũ; cần đánh giá sự cố, chuyển key, kiểm soát phiên và yêu cầu reset mật khẩu tài khoản bị ảnh hưởng theo policy.

**Câu 7.** `pepper_key_id` có cần giấu như pepper không?

**Đáp án:** Không. Key ID là metadata dùng chọn version; phải tránh nhúng key material hoặc credentials vào ID, nhưng việc biết tên key không nên giúp attacker tính verifier.

**Câu 8.** Khi KMS mất kết nối, có nên chuyển sang kiểm tra hash không pepper cho khỏi mất login không?

**Đáp án:** Không. Phải fail-closed và xử lý lỗi vận hành, timeout/alert/recovery. Fallback làm mất ranh giới bảo mật.

**Câu 9.** `PasswordEncoder.upgradeEncoding` trả true là đã thay pepper trong DB?

**Đáp án:** Không. Nó chỉ báo cần nâng cấp; ứng dụng/provider phải có luồng cập nhật thực sự, ví dụ `UserDetailsPasswordService` sau xác thực đúng và kiểm soát ghi đồng thời.

**Câu 10.** Vì sao không đặt pepper trong `UserDetailsService` rồi tự cấp `Authentication`?

**Đáp án:** `UserDetailsService` là nguồn đọc account, còn `PasswordEncoder`/`DaoAuthenticationProvider` xác thực credentials và trạng thái. Bỏ qua provider có thể phá cơ chế kiểm tra locked/disabled và quản lý token.

**Câu 11.** Tại sao cần key version và password format version riêng?

**Đáp án:** Key version chọn bí mật, còn format version chỉ KDF/HMAC/salt/encoding. Tách giúp đổi một thành phần có kế hoạch, không làm hash cũ bị diễn giải theo tham số mới.

**Câu 12.** HSM có ý nghĩa gì nếu app vẫn có quyền gọi MAC cho mọi login?

**Đáp án:** HSM có thể ngăn xuất raw key, giảm khả năng lấy key material từ DB/source/app memory. Tuy nhiên workload có quyền gọi MAC vẫn có thể bị lạm dụng, nên IAM, rate/quota, audit, kiểm soát tầng ứng dụng và incident response vẫn cần thiết.

## 15. Tài liệu chính thức và checklist trước triển khai

### Tài liệu tham khảo

- [OWASP — Password Storage Cheat Sheet: Peppering](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#peppering): vai trò pepper, tách khỏi database, pre-hash/post-hash, cảnh báo reset khi bị lộ.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): vòng đời secret, IAM, audit, rotation, recovery và hạn chế lưu plaintext.
- [NIST SP 800-63B-4 — Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html): salted password hashing và khuyến nghị phép keyed hash/encryption bổ sung, khóa lưu riêng và bảo vệ bằng phần cứng khi thích hợp.
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): `PasswordEncoder`, adaptive hashing, `DelegatingPasswordEncoder` và versioned format.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): sử dụng `UserDetailsService` và `PasswordEncoder` trong authentication.
- [Spring Security 6.5.11 — DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): cấu hình encoder và `UserDetailsPasswordService` để nâng cấp verifier.
- [Oracle JDK 17 — SecretKeyFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html): PBKDF2 và các key derivation provider.
- [Oracle JDK 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): HMAC dùng key, không phải băm nhanh không khóa.

### Checklist quyết định kiến trúc

- [ ] Đã xác định threat model: DB-only, app compromise, key compromise và mức rủi ro chấp nhận.
- [ ] Thuật toán password hashing có salt riêng, work factor được benchmark và metadata versioned.
- [ ] Mô hình pepper không lưu unpeppered verifier có thể bị attacker DB-only dùng thử đoán.
- [ ] Pepper được tạo ngẫu nhiên, giữ **ngoài database** và quản trị bởi vault/KMS/HSM theo IAM tối thiểu.
- [ ] Có **key ID** cho mỗi bản ghi và một **active-for-write ID** rõ ràng.
- [ ] Có đường verify phiên bản cũ có thời hạn và kế hoạch retire, không giữ key cũ mãi.
- [ ] Có migration sau password đúng và đường reset cho account không hoạt động.
- [ ] Có compare-and-set/optimistic locking để tránh ghi đè password sau reset.
- [ ] Có đường xử lý KMS unavailable **fail-closed**, metrics/alerts và DR.
- [ ] Có kế hoạch khẩn cấp khi pepper bị lộ: containment, kiểm kê, revoke/reset và xử lý phiên.
- [ ] Có integration test qua Spring Security provider và test rolling deploy/multi-region.
- [ ] Không log raw password, key material hoặc verifier đầy đủ; audit quyền sử dụng key.
- [ ] Đã review việc dùng key cho HMAC: key purpose riêng, domain separation và không reuse JWT/session key.

**Kết luận:** Pepper là **một bí mật bổ sung được quản lý ở phía máy chủ** nhằm tăng bảo vệ password verifier khi **chỉ dữ liệu database bị lộ**. Sự an toàn đến từ cả kiến trúc: KDF thích nghi + salt riêng + pepper không nằm cùng DB + quản trị vault/KMS/HSM + versioned format + luân chuyển có kế hoạch. **Rotation bình thường** có thể triển khai “K2 ghi mới, K1 verify có thời hạn, migrate sau login đúng”; **pepper bị lộ** đòi hỏi đánh giá sự cố, thường phải yêu cầu reset password và thu hồi K1 sớm, không thể chỉ đổi tên active key rồi coi tất cả credential cũ đã an toàn.