# pgcrypto và lựa chọn hàm mật mã phù hợp trong PostgreSQL

PostgreSQL cung cấp extension **pgcrypto** để thực hiện một số phép toán mật mã ngay trong database. Extension có các nhóm hàm khác nhau: hàm băm để tạo fingerprint, HMAC để xác thực dữ liệu bằng secret key, hàm băm mật khẩu có salt và cost thích nghi, bộ sinh byte ngẫu nhiên mật mã, cùng các hàm mã hóa OpenPGP đối xứng và khóa công khai.

Điều quan trọng nhất là chọn đúng primitive cho đúng mục tiêu. Hash không thể giải mã; HMAC không mã hóa dữ liệu; mã hóa không thay thế password hashing; random token không nên sinh bằng hàm random thông thường. Một lựa chọn sai có thể làm lộ mật khẩu, cho phép sửa dữ liệu mà không bị phát hiện, hoặc khiến khóa bí mật nằm cạnh ciphertext trong cùng database.

pgcrypto cũng có giới hạn về ranh giới tin cậy: các hàm chạy bên trong PostgreSQL server. Khi ứng dụng gửi plaintext và key vào hàm pgcrypto, server xử lý được cả hai. Database administrator hoặc người kiểm soát server có thể có khả năng quan sát dữ liệu đó. Nếu yêu cầu là ngay cả DBA cũng không được đọc plaintext, cần cân nhắc mã hóa phía client trước khi dữ liệu tới database.

Bài học này giúp phân biệt từng nhóm hàm, chọn thuật toán và cách lưu trữ phù hợp, quản lý khóa, kiểm tra kết quả và tránh những cách dùng nguy hiểm.

~~~text
                 Nhu cầu bảo vệ dữ liệu
                           |
       +-------------------+-------------------+
       |                   |                   |
       v                   v                   v
  Kiểm tra fingerprint  Xác thực dữ liệu   Bảo vệ bí mật
       |                   |                   |
       v                   v                   v
    digest()             hmac()          pgp_*_encrypt()
                                               |
       +-------------------+-------------------+
       |                   |
       v                   v
  Lưu password         Token ngẫu nhiên
       |                   |
       v                   v
 crypt() + gen_salt() gen_random_bytes()

Mỗi nhánh giải quyết một bài toán khác nhau.
~~~

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Mở rộng**, với đề tài **“pgcrypto và lựa chọn hàm mật mã phù hợp”**. Nội dung tập trung vào cách cài extension, phân biệt digest/HMAC/password hash/encryption/randomness, sử dụng OpenPGP, thiết kế schema, quản lý và luân chuyển khóa, kiểm thử và vận hành an toàn.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích pgcrypto là gì và vì sao nó được cung cấp dưới dạng extension.
2. Cài đặt và xác nhận pgcrypto trong từng database.
3. Phân biệt hàm băm, HMAC, password hashing và encryption.
4. Dùng digest để tạo hash SHA-256 hoặc SHA-512.
5. Hiểu vì sao hash không xác thực được dữ liệu nếu attacker có thể thay cả data lẫn hash.
6. Dùng hmac với secret key để kiểm tra integrity/authenticity.
7. Dùng crypt và gen_salt để lưu password hash có salt và cost.
8. Phân biệt bcrypt với các password hashing schemes cũ trong crypt.
9. Biết giới hạn 72 bytes của bcrypt và cách xử lý password dài.
10. Sinh random bytes bằng gen_random_bytes thay vì random().
11. Mã hóa và giải mã dữ liệu bằng pgp_sym_encrypt/pgp_sym_decrypt.
12. Mã hóa bằng public key và giải mã bằng private key.
13. Dùng armor/dearmor và đọc metadata OpenPGP.
14. Phân biệt text functions với bytea functions.
15. Chọn primitive theo yêu cầu: checksum, password, token, integrity hay confidentiality.
16. Thiết kế schema lưu ciphertext, key version và metadata.
17. Quản lý khóa ngoài database bằng secret manager/KMS/HSM.
18. Hiểu vì sao pgcrypto server-side không che plaintext khỏi database server.
19. Lập kế hoạch key rotation và migration ciphertext.
20. Đánh giá index/search implications của encryption.
21. Giới hạn quyền truy cập, logging và query visibility.
22. Kiểm tra performance, error handling và compatibility.
23. Thực hành digest, HMAC, password hashing, symmetric encryption và public-key encryption.
24. Xây dựng checklist vận hành pgcrypto an toàn.

**Phạm vi:** PostgreSQL hiện đại với pgcrypto được build/package có hỗ trợ OpenSSL. Tên thuật toán khả dụng, extension package và một số chi tiết có thể phụ thuộc OpenSSL, PostgreSQL version, OS và nhà cung cấp dịch vụ. Ví dụ dùng placeholder bind parameters như $1, $2; không đặt key hoặc password thật trực tiếp vào SQL source.

---

## 2. Mật mã học cơ bản trước khi dùng pgcrypto

Không thể chọn đúng hàm nếu chưa xác định mục tiêu bảo mật.

### 2.1. Confidentiality — tính bí mật

Chỉ người có key phù hợp mới đọc được nội dung. Đây là mục tiêu của encryption.

Ví dụ: mã hóa số tài khoản ngân hàng hoặc nội dung ghi chú nhạy cảm trước khi lưu.

### 2.2. Integrity — tính toàn vẹn

Phát hiện dữ liệu đã thay đổi ngoài ý muốn hoặc bị sửa trái phép. Hash có thể tạo fingerprint, nhưng để chống attacker có thể tính lại hash cần một secret key hoặc cơ chế chữ ký.

### 2.3. Authenticity — tính xác thực nguồn

Xác định dữ liệu có được tạo bởi một bên nắm giữ credential/key hợp lệ hay không. HMAC dùng shared secret; digital signature dùng private/public key pair.

### 2.4. Password verification

Hệ thống cần xác minh người dùng biết password mà không lưu password gốc. Cách phù hợp là password hashing có salt và cost thích nghi, không phải mã hóa reversible.

### 2.5. Randomness

Token, nonce, salt và key cần được sinh từ nguồn random mật mã. Hàm random thông thường phục vụ mô phỏng/thống kê không phù hợp cho security token.

### 2.6. Các khái niệm không thay thế nhau

| Primitive | Có thể khôi phục dữ liệu gốc? | Dùng secret key? | Mục tiêu chính |
| --- | --- | --- | --- |
| digest/hash | Không | Không | Fingerprint/checksum |
| HMAC | Không | Có | Integrity/authenticity với shared secret |
| Password hash | Không | Có salt; thường không cần secret riêng | Xác minh password |
| Symmetric encryption | Có, với cùng key | Có | Confidentiality |
| Public-key encryption | Có, với private key | Public/private key pair | Confidentiality và phân phối key |
| Digital signature | Không khôi phục plaintext từ chữ ký | Private key để ký | Xác thực người ký và integrity |
| Random bytes | Không phải phép biến đổi dữ liệu | CSPRNG nội bộ | Token, nonce, key material |

pgcrypto cung cấp các hàm cho nhiều hàng trong bảng này, nhưng không phải thư viện bao trọn mọi hệ thống quản lý khóa hoặc chữ ký số.

---

## 3. Threat model: xác định ai cần bị ngăn truy cập

Trước khi chọn pgcrypto, hãy xác định dữ liệu cần bảo vệ khỏi ai.

### 3.1. Người dùng ứng dụng không được đọc dữ liệu của nhau

Có thể cần kết hợp:
- PostgreSQL roles và grants.
- Row-level security.
- Application authorization.
- Encryption cho một số fields nếu cần thêm lớp bảo vệ.

Encryption không thay thế authorization.

### 3.2. Kẻ đánh cắp backup hoặc storage snapshot

Mã hóa ở tầng database/application hoặc encryption-at-rest của storage có thể giảm rủi ro khi backup/snapshot bị lấy cắp. Key phải được lưu tách biệt với ciphertext.

### 3.3. Người nghe lén network

TLS bảo vệ dữ liệu trên đường truyền. pgcrypto không tự thay thế TLS giữa client và server.

### 3.4. Database administrator hoặc người kiểm soát server

Với pgcrypto server-side, plaintext và key được đưa vào PostgreSQL để hàm xử lý. Người có quyền đủ cao hoặc kiểm soát host có thể có khả năng quan sát chúng.

Nếu DBA không được phép đọc plaintext, dùng client-side encryption với key chỉ có ở client/trusted service, hoặc một kiến trúc HSM/KMS phù hợp.

### 3.5. Attacker có quyền sửa dữ liệu

Hash không keyed có thể được tính lại sau khi sửa payload. HMAC hoặc chữ ký số có thể phát hiện việc sửa nếu key/private key được bảo vệ.

### 3.6. Insider có quyền xem logs

Query text, error details, audit logs và tracing có thể vô tình chứa password, plaintext hoặc key. Không đưa secret vào literal SQL và không ghi secret vào logs.

### 3.7. Không có một hàm giải quyết mọi threat

Một hệ thống thường cần nhiều lớp: TLS, authorization, backup encryption, key management, password hashing, audit và database encryption cho các fields phù hợp.

---

## 4. Cài đặt pgcrypto

pgcrypto là extension, nên package phải có trên server và extension phải được tạo trong từng database cần dùng.

### 4.1. Kiểm tra PostgreSQL version

~~~sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
~~~

### 4.2. Kiểm tra extension package có sẵn

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_catalog.pg_available_extensions
WHERE name = 'pgcrypto';
~~~

Nếu không có row, server installation/service có thể chưa cung cấp package pgcrypto. Cài package phù hợp với PostgreSQL major version hoặc hỏi nhà cung cấp managed service.

### 4.3. Cài extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

Lệnh này phải chạy trong database cần sử dụng pgcrypto.

### 4.4. Xác nhận version và schema

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS extension_schema,
    e.extowner::regrole AS extension_owner
FROM pg_catalog.pg_extension AS e
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = e.extnamespace
WHERE e.extname = 'pgcrypto';
~~~

### 4.5. Extension theo database

CREATE EXTENSION chỉ cài extension trong database hiện tại. Nếu ứng dụng dùng nhiều databases, cần kiểm tra từng database.

### 4.6. OpenSSL dependency

pgcrypto dựa vào OpenSSL cho các chức năng mật mã. Nếu PostgreSQL build không có hỗ trợ OpenSSL hoặc package extension không được cung cấp, không thể giả định CREATE EXTENSION sẽ hoạt động.

Trên host có thể kiểm tra build configuration bằng:

~~~bash
pg_config --configure
pg_config --version
~~~

### 4.7. Schema và search_path

Các functions được tạo trong schema extension. Không giả định luôn nằm ở public nếu extension được cài với schema khác.

Dùng schema-qualified names trong security-sensitive code, ví dụ public.digest(...) nếu extension thực sự nằm trong public. Nếu extension nằm ở schema khác, thay tên schema theo catalog.

### 4.8. Quyền cài đặt và sử dụng

pgcrypto được đánh dấu trusted trong các PostgreSQL distributions hỗ trợ metadata này; user có quyền CREATE trên database có thể được phép cài. Chính sách managed service hoặc package có thể bổ sung giới hạn. Quyền gọi function vẫn chịu ảnh hưởng của grants và schema privileges.

### 4.9. Kiểm tra function sau khi cài

~~~sql
SELECT
    n.nspname AS function_schema,
    p.proname,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
    pg_catalog.pg_get_function_result(p.oid) AS result_type
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.proname IN (
    'digest',
    'hmac',
    'crypt',
    'gen_salt',
    'gen_random_bytes',
    'pgp_sym_encrypt',
    'pgp_sym_decrypt'
)
ORDER BY n.nspname, p.proname;
~~~

---

## 5. digest: hàm băm dữ liệu

digest tạo hash/fingerprint từ dữ liệu. Kết quả là bytea; có thể dùng encode để hiển thị dưới dạng hex hoặc base64.

### 5.1. Cú pháp

**digest(data, type) RETURNS bytea**

data có thể là text hoặc bytea. type là tên digest algorithm.

### 5.2. Ví dụ SHA-256

~~~sql
SELECT encode(
    public.digest('hello PostgreSQL', 'sha256'),
    'hex'
) AS sha256_hex;
~~~

Nếu extension không nằm trong public, thay schema bằng schema thực tế.

### 5.3. Ví dụ SHA-512

~~~sql
SELECT encode(
    public.digest('hello PostgreSQL', 'sha512'),
    'hex'
) AS sha512_hex;
~~~

SHA-512 tạo digest dài hơn SHA-256. Chọn thuật toán theo interoperability, policy và use case; không phải digest dài hơn luôn cần thiết.

### 5.4. Hash bytea

~~~sql
SELECT encode(
    public.digest(convert_to('Tiếng Việt', 'UTF8'), 'sha256'),
    'hex'
);
~~~

convert_to chuyển text thành bytea theo encoding được chỉ định. Khi nhiều hệ thống cùng tính hash, phải thống nhất encoding và canonical representation.

### 5.5. Các thuật toán thường gặp

| Algorithm | Nhận xét |
| --- | --- |
| md5 | Legacy; không dùng cho security-sensitive integrity |
| sha1 | Legacy; collision resistance không còn phù hợp cho thiết kế mới |
| sha224 | SHA-2 với digest 224 bit |
| sha256 | Lựa chọn phổ biến cho fingerprint/integrity không keyed |
| sha384 | SHA-2 với digest 384 bit |
| sha512 | SHA-2 với digest 512 bit |

Khả năng hỗ trợ thuật toán có thể phụ thuộc OpenSSL build. Không dựa vào việc một thuật toán có mặt trên môi trường development để kết luận nó có trên mọi target.

### 5.6. Hash không phải encryption

Từ digest không thể giải mã để lấy plaintext ban đầu. Nếu ứng dụng cần đọc lại giá trị, digest không phù hợp.

### 5.7. Hash không tự xác thực nguồn

Nếu attacker có thể sửa cả payload lẫn digest, họ có thể tính digest mới. Để xác thực dữ liệu với shared secret, dùng HMAC; để xác thực public-key identity, dùng chữ ký số từ hệ thống phù hợp.

### 5.8. Không dùng digest để lưu password

Password thường có entropy thấp và dễ bị đoán offline. SHA-256 rất nhanh, nên attacker có thể thử số lượng lớn password guesses. Dùng password hashing có salt và cost như bcrypt/Argon2id theo policy.

### 5.9. Canonicalization trước khi hash

Cùng một dữ liệu logic có thể có nhiều biểu diễn byte khác nhau:
- Unicode composed/decomposed.
- JSON key ordering/whitespace.
- Timestamp timezone/format.
- Numeric scale/locale.
- Line endings.
- Text encoding.

Nếu nhiều hệ thống cần so sánh digest, hãy chuẩn hóa dữ liệu trước khi hash và ghi rõ canonical format/version.

### 5.10. Fingerprint file hoặc payload

digest có thể hữu ích để:
- So sánh artifact.
- Phát hiện thay đổi ngoài ý muốn khi digest được bảo vệ.
- Định danh content.
- Kiểm tra dữ liệu sau truyền tải.

Với nội dung có giá trị bảo mật cao, digest không keyed không đủ để chống attacker chủ động thay thế.

---

## 6. encode và decode kết quả bytea

digest và hmac trả bytea. Để hiển thị hoặc truyền qua text interface, dùng encode/decode.

### 6.1. Hex

~~~sql
SELECT encode(
    public.digest('sample', 'sha256'),
    'hex'
);
~~~

Hex dễ đọc và có độ dài gấp đôi số bytes.

### 6.2. Base64

~~~sql
SELECT encode(
    public.digest('sample', 'sha256'),
    'base64'
);
~~~

Base64 gọn hơn hex nhưng có ký tự đặc biệt và có thể cần URL-safe transformation khi đưa vào URL.

### 6.3. Decode hex

~~~sql
SELECT decode('48656c6c6f', 'hex');
~~~

decode trả bytea. Input phải có encoding hợp lệ.

### 6.4. Không nhầm text với bytea

Một digest là binary bytes. Nếu lưu vào cột text, cần encode rõ ràng. Nếu lưu vào bytea, không cần chuyển sang hex trừ khi cần representation dạng text.

### 6.5. Binary equality

So sánh bytea có thể dùng cho equality logic trong database. Tuy nhiên, nếu MAC verification ở bối cảnh attacker có thể quan sát timing, cần dùng cách so sánh constant-time ở trusted application/library phù hợp thay vì tự giả định mọi phép so sánh SQL đều constant-time.

---

## 7. hmac: hash có khóa bí mật

HMAC (Hash-based Message Authentication Code) kết hợp hash algorithm với secret key. Nó tạo mã xác thực để kiểm tra payload có bị thay đổi và có được tạo bởi bên biết secret hay không.

### 7.1. Cú pháp

**hmac(data, key, type) RETURNS bytea**

- data: payload dạng text hoặc bytea.
- key: secret key dạng bytea.
- type: digest algorithm.

### 7.2. Ví dụ

~~~sql
SELECT encode(
    public.hmac(
        convert_to('order=42&amount=100', 'UTF8'),
        $1::bytea,
        'sha256'
    ),
    'hex'
);
~~~

$1 là bind parameter do client truyền. Không thay bằng secret literal trong SQL source.

### 7.3. Xác minh MAC

Bên gửi và bên nhận tính HMAC trên cùng payload, cùng key và cùng algorithm. Nếu kết quả khớp, dữ liệu có thể được xác thực trong phạm vi bảo mật của shared key.

### 7.4. HMAC không mã hóa

Payload vẫn có thể đọc được. HMAC chỉ cung cấp integrity/authenticity với secret; muốn confidentiality cần encryption riêng.

### 7.5. HMAC khác digest

| Đặc điểm | digest | hmac |
| --- | --- | --- |
| Secret key | Không | Có |
| Ngăn attacker tự tính lại sau khi sửa payload | Không, nếu digest không được bảo vệ | Có, nếu key an toàn |
| Khôi phục plaintext | Không | Không |
| Mục đích | Fingerprint/checksum | Message authentication |

### 7.6. Chọn key

HMAC key nên được sinh ngẫu nhiên với entropy đủ lớn. Không dùng password người dùng trực tiếp làm HMAC key. Nếu cần derive key từ password, dùng KDF được thiết kế cho mục đích đó ở tầng phù hợp.

### 7.7. Phải thống nhất payload representation

Nếu hai bên tính HMAC từ JSON, phải thống nhất canonical JSON, encoding, field ordering, numeric representation và version của message format.

### 7.8. Domain separation

Nếu cùng một secret phục vụ nhiều mục đích, thêm context/purpose vào dữ liệu được MAC hoặc dùng key riêng cho từng purpose. Điều này giảm nguy cơ một MAC hợp lệ ở context này bị tái sử dụng ở context khác.

### 7.9. Replay protection

HMAC không tự ngăn replay. Nếu message cũ có MAC hợp lệ bị gửi lại, MAC vẫn hợp lệ. Thêm timestamp, nonce hoặc sequence number và lưu trạng thái đã dùng để kiểm soát replay.

### 7.10. So sánh MAC

Không tiết lộ thông tin chi tiết về việc MAC sai ở từng byte. Trong ứng dụng có attacker quan sát được timing, xác minh MAC bằng constant-time comparison trong thư viện ứng dụng đáng tin cậy.

---

## 8. crypt và gen_salt: password hashing

Password hashing biến password thành chuỗi xác minh một chiều. Khi đăng nhập, hệ thống tính lại hash từ password nhập vào và salt/cost lưu trong hash đã tạo.

### 8.1. Cú pháp

**crypt(password, salt) RETURNS text**

**gen_salt(type [, iter_count]) RETURNS text**

crypt là hàm password hashing theo các scheme mà pgcrypto hỗ trợ. gen_salt sinh salt có format phù hợp với scheme.

### 8.2. Bcrypt

Với hệ thống mới dùng pgcrypto, bcrypt (bf) thường là lựa chọn phù hợp nhất trong các schemes mà crypt cung cấp, nếu đáp ứng policy của ứng dụng.

~~~sql
SELECT public.crypt(
    $1,
    public.gen_salt('bf', 12)
);
~~~

Ở đây 12 là cost parameter của bcrypt, không phải số vòng lặp tuyến tính. Cost cao hơn làm tính toán tốn thời gian hơn theo cấp số nhân.

### 8.3. Lưu password hash

~~~sql
CREATE TABLE app_user_auth (
    user_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_scheme TEXT NOT NULL DEFAULT 'pgcrypto-bf',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

~~~sql
INSERT INTO app_user_auth (
    user_id,
    username,
    password_hash
)
VALUES (
    $1,
    $2,
    public.crypt($3, public.gen_salt('bf', 12))
);
~~~

Chỉ lưu hash. Không lưu password gốc, reversible ciphertext hoặc log password.

### 8.4. Xác minh password

~~~sql
SELECT
    password_hash = public.crypt($1, password_hash) AS password_ok
FROM app_user_auth
WHERE username = $2;
~~~

crypt sử dụng hash đã lưu làm salt/setting để tính kết quả mới. Nếu kết quả khớp, password được xác minh.

### 8.5. Không cần lưu salt riêng nếu hash đã chứa salt

Format bcrypt lưu thông tin scheme, cost và salt trong chuỗi hash. Không cần thêm một cột salt riêng cho cách dùng này, trừ khi hệ thống có thiết kế đặc biệt.

### 8.6. Cost cần benchmark

Cost 12 chỉ là ví dụ. Đo thời gian xác minh trên hardware production-like, concurrency thực tế và latency budget. Cost quá thấp làm giảm khả năng chống brute force; cost quá cao có thể tạo CPU exhaustion khi login burst.

### 8.7. Giới hạn 72 bytes của bcrypt

Bcrypt chỉ xử lý tối đa 72 bytes password input. Với UTF-8, 72 bytes không nhất thiết bằng 72 ký tự. Nếu password dài hơn, phần sau có thể bị bỏ qua theo behavior của bcrypt.

Không tự ghép SHA-256(password) vào bcrypt như một giải pháp nhanh nếu chưa có thiết kế chuẩn hóa, domain separation và migration rõ ràng. Với policy cần password dài hoặc thuật toán hiện đại hơn, cân nhắc Argon2id ở application layer hoặc giải pháp được tổ chức phê duyệt.

### 8.8. Các scheme cũ

pgcrypto crypt có thể hỗ trợ các scheme như DES, extended DES, MD5 và bcrypt tùy build/version. DES, xdes và md5 là lựa chọn legacy; không dùng cho hệ thống mới khi bcrypt hoặc password hashing library hiện đại có sẵn.

### 8.9. Bcrypt không phải mã hóa

Không thể giải mã hash để lấy password. Không có hàm crypt_decrypt. Nếu cần khôi phục dữ liệu, đó là bài toán encryption, không phải password storage.

### 8.10. Không tiết lộ username tồn tại

Login endpoint nên trả thông báo chung cho user không tồn tại và password sai. Tránh để timing/response code phân biệt tài khoản có tồn tại, đồng thời rate-limit login attempts.

### 8.11. Rehash khi policy thay đổi

Khi cost hoặc scheme cần tăng:
1. Xác minh password thành công.
2. Kiểm tra scheme/cost của hash hiện tại.
3. Nếu thấp hơn policy, tính hash mới với cost mới.
4. Cập nhật password_hash trong transaction.
5. Ghi scheme/version metadata nếu hệ thống cần.

Không cần reset toàn bộ passwords ngay nếu có thể rehash an toàn khi user đăng nhập.

### 8.12. Argon2id và policy hiện đại

pgcrypto crypt không cung cấp Argon2id. Nếu policy yêu cầu Argon2id hoặc scrypt, dùng thư viện password hashing được duy trì ở application layer hoặc giải pháp được security team phê duyệt. Không thay bằng digest(password, 'sha256').

---

## 9. gen_random_bytes: tạo dữ liệu ngẫu nhiên mật mã

Token, nonce và key material cần nguồn random mật mã (CSPRNG).

### 9.1. Cú pháp

**gen_random_bytes(count) RETURNS bytea**

Hàm trả về số bytes ngẫu nhiên được yêu cầu. pgcrypto giới hạn một lần gọi tối đa 1024 bytes.

### 9.2. Sinh token 32 bytes

~~~sql
SELECT encode(public.gen_random_bytes(32), 'hex') AS token;
~~~

32 bytes có 256 bits raw entropy nếu nguồn random hoạt động đúng.

### 9.3. Sinh secret key material

~~~sql
SELECT public.gen_random_bytes(32);
~~~

Kết quả bytea có thể được chuyển tới key management system theo quy trình an toàn. Không lưu key raw vào cùng bảng với ciphertext.

### 9.4. Không dùng random()

~~~sql
SELECT random();
~~~

random() phục vụ mục đích số ngẫu nhiên thông thường, không phải token/key generation an toàn.

### 9.5. Salt và nonce

gen_salt tạo salt theo password hashing scheme; gen_random_bytes tạo bytes ngẫu nhiên tổng quát. Không nhầm salt của bcrypt với encryption key.

### 9.6. Token cần encoding

Khi đưa token vào text field hoặc URL, encode bytes bằng hex/base64 và xử lý URL-safe encoding ở application layer. Lưu ý base64 thông thường có thể chứa ký tự cần escaping.

### 9.7. Randomness failure

Nếu hệ thống không có nguồn random đủ an toàn, hàm có thể báo lỗi. Không thay bằng random() để né lỗi; xử lý entropy/OS/container environment.

---

## 10. Mã hóa đối xứng với OpenPGP

Mã hóa đối xứng dùng cùng một passphrase/key để mã hóa và giải mã.

### 10.1. Các hàm chính

| Function | Input/output |
| --- | --- |
| pgp_sym_encrypt(text, psw [, options]) | Mã hóa text thành bytea |
| pgp_sym_decrypt(bytea, psw [, options]) | Giải mã bytea thành text |
| pgp_sym_encrypt_bytea(bytea, psw [, options]) | Mã hóa binary bytea |
| pgp_sym_decrypt_bytea(bytea, psw [, options]) | Giải mã về bytea |

### 10.2. Mã hóa text

~~~sql
SELECT public.pgp_sym_encrypt(
    $1::text,
    $2::text
);
~~~

$1 là plaintext; $2 là passphrase được bind từ secret management flow.

### 10.3. Giải mã text

~~~sql
SELECT public.pgp_sym_decrypt(
    encrypted_value,
    $1::text
)
FROM app.customer_secret
WHERE secret_id = $2;
~~~

### 10.4. Lưu ciphertext

~~~sql
CREATE TABLE app.customer_secret (
    secret_id BIGINT PRIMARY KEY,
    ciphertext BYTEA NOT NULL,
    key_version SMALLINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

key_version là metadata tham chiếu tới key ở hệ thống quản lý khóa. Không lưu passphrase trong bảng này.

### 10.5. Mã hóa binary

Với payload không phải text như file fragments hoặc binary blobs, dùng pgp_sym_encrypt_bytea và pgp_sym_decrypt_bytea. Không ép bytea thành text bằng encoding không phù hợp.

### 10.6. OpenPGP packet format

pgcrypto dùng định dạng OpenPGP cho các hàm PGP. Cipher, compression và string-to-key (S2K) behavior có thể điều chỉnh qua options. Chọn options theo interoperability và policy, không tự hạ cipher/integrity protection để tăng tốc.

### 10.7. Cipher option

Có thể chỉ định cipher được hỗ trợ bởi pgcrypto/OpenPGP build, ví dụ AES-256 khi target hỗ trợ:

~~~sql
SELECT public.pgp_sym_encrypt(
    $1::text,
    $2::text,
    'cipher-algo=aes256'
);
~~~

Xác nhận cipher được hỗ trợ trên source và target, đồng thời tuân thủ policy của tổ chức. Không giả định mọi build có cùng danh sách thuật toán.

### 10.8. S2K và passphrase derivation

OpenPGP dùng String-to-Key để tạo encryption key từ passphrase. pgcrypto có options liên quan S2K mode, count, digest và cipher. Đây là cơ chế riêng của OpenPGP, không phải API KDF tổng quát cho mọi application secret.

### 10.9. Integrity protection

OpenPGP encrypted data có cơ chế kiểm tra integrity theo format/options. Không bật tùy chọn tắt MDC/integrity check như disable-mdc=1 cho dữ liệu mới. Integrity packet không chứng minh danh tính người gửi; muốn xác thực sender cần HMAC hoặc digital signature thích hợp.

### 10.10. Passphrase phải đủ mạnh

Passphrase yếu có thể bị brute-force offline nếu attacker lấy ciphertext. Dùng secret ngẫu nhiên dài do KMS/secret manager tạo và quản lý, hoặc passphrase có entropy cao theo policy. Không dùng mật khẩu đăng nhập thông thường làm encryption passphrase.

### 10.11. Encryption output không deterministic

Cùng plaintext và passphrase có thể tạo ciphertext khác nhau do salt/session key/randomness. Không dùng ciphertext equality làm phép so sánh plaintext equality.

---

## 11. Mã hóa khóa công khai

Public-key encryption dùng public key để mã hóa và private key để giải mã.

### 11.1. Các hàm chính

| Function | Vai trò |
| --- | --- |
| pgp_pub_encrypt(text, public_key [, options]) | Mã hóa text bằng public key |
| pgp_pub_decrypt(bytea, private_key [, psw [, options]]) | Giải mã bằng private key |
| pgp_pub_encrypt_bytea(bytea, public_key [, options]) | Mã hóa binary |
| pgp_pub_decrypt_bytea(bytea, private_key [, psw [, options]]) | Giải mã binary |
| pgp_key_id(bytea) | Lấy key ID từ PGP key/message phù hợp |

### 11.2. Public key/private key

Public key có thể phân phối cho bên gửi. Private key phải được giữ bí mật và chỉ người/dịch vụ được phép giải mã mới truy cập.

### 11.3. Mã hóa với public key

Nếu public key ở dạng ASCII-armored text, dùng dearmor để chuyển thành bytea:

~~~sql
SELECT public.pgp_pub_encrypt(
    $1::text,
    public.dearmor($2::text)
);
~~~

$2 là armored public key được lấy từ key registry đáng tin cậy.

### 11.4. Giải mã với private key

~~~sql
SELECT public.pgp_pub_decrypt(
    encrypted_value,
    public.dearmor($1::text),
    $2::text
)
FROM app.encrypted_message
WHERE message_id = $3;
~~~

Tham số thứ ba là passphrase của private key nếu private key được bảo vệ bằng passphrase; dùng đúng signature của version cài đặt.

### 11.5. Public-key encryption không phải digital signature

Bất kỳ ai có public key đều có thể mã hóa cho người nhận. Điều đó không chứng minh ai đã tạo plaintext. Để xác thực người gửi, cần chữ ký số bằng private signing key và verify bằng public key qua công cụ/thư viện phù hợp.

### 11.6. Key generation

pgcrypto cung cấp các hàm sử dụng PGP keys, nhưng không phải công cụ quản lý vòng đời key pair đầy đủ. Tạo key pair, backup private key, revoke, rotate và publish public key bằng hệ thống key management/OpenPGP tooling được phê duyệt.

### 11.7. Key ID

pgp_key_id có thể giúp nhận diện key được dùng trong PGP packet. Key ID không phải bằng chứng tin cậy đầy đủ; dùng fingerprint đầy đủ từ key management tooling để xác minh identity.

### 11.8. Không lưu private key cạnh ciphertext

Nếu cùng một database chứa ciphertext và private key không được bảo vệ, attacker lấy database có thể lấy cả hai. Private key phải được quản lý ngoài database với access control và audit riêng.

---

## 12. armor, dearmor và PGP headers

OpenPGP thường có binary representation hoặc ASCII-armored representation.

### 12.1. armor

armor chuyển binary bytea thành text ASCII-armored:

~~~sql
SELECT public.armor(encrypted_value);
~~~

### 12.2. dearmor

dearmor chuyển ASCII-armored text về bytea:

~~~sql
SELECT public.dearmor($1::text);
~~~

### 12.3. pgp_armor_headers

Hàm này đọc các armor headers:

~~~sql
SELECT *
FROM public.pgp_armor_headers($1::text);
~~~

Kết quả có các trường key/value theo format armor.

### 12.4. Headers không phải trust anchor

Không tin cậy identity chỉ vì armor header ghi một tên/email. Metadata có thể bị giả mạo hoặc không được xác minh bằng cryptographic identity.

### 12.5. Lưu trữ dạng nào?

- bytea phù hợp để lưu ciphertext binary trong database.
- armor text thuận tiện cho truyền tải qua hệ thống text/email.
- Encoding không làm dữ liệu an toàn hơn; security đến từ key và cryptographic operation.

---

## 13. Chọn hàm nào cho từng bài toán?

| Nhu cầu | Lựa chọn | Không nên dùng |
| --- | --- | --- |
| Fingerprint payload công khai | digest với SHA-256/512 | crypt hoặc encryption |
| Xác thực payload với shared secret | hmac với SHA-256/512 | digest không keyed |
| Lưu password người dùng | crypt + gen_salt('bf', cost), hoặc Argon2id ở app | digest(password, 'sha256') |
| Sinh token/nonce/key bytes | gen_random_bytes | random() |
| Mã hóa field text nhỏ bằng shared secret | pgp_sym_encrypt/decrypt | digest |
| Mã hóa binary nhỏ bằng shared secret | pgp_sym_encrypt_bytea/decrypt_bytea | ép binary thành text tùy tiện |
| Mã hóa cho một người nhận | pgp_pub_encrypt/decrypt | HMAC |
| Xác thực người ký | Digital signature tooling | Public-key encryption đơn thuần |
| Bảo vệ dữ liệu khỏi DBA | Client-side encryption/KMS architecture | pgcrypto server-side một mình |
| Tìm kiếm equality trên ciphertext | Blind index/HMAC token được thiết kế cẩn thận | So sánh ciphertext ngẫu nhiên |

### 13.1. Câu hỏi chọn primitive

1. Có cần đọc lại plaintext không? Nếu không, cân nhắc hash/password hash.
2. Có cần xác thực bằng shared secret không? Dùng HMAC.
3. Có cần password verification không? Dùng adaptive password hash.
4. Có cần token khó đoán không? Dùng CSPRNG.
5. Có cần confidentiality không? Dùng encryption.
6. Có cần xác thực người gửi bằng public identity không? Dùng digital signature.
7. Có cần che plaintext khỏi DB server không? Mã hóa trước khi gửi tới server.

### 13.2. Đừng chọn theo tên hàm

Một hàm có chữ hash hoặc encrypt không tự đảm bảo đáp ứng threat model. Hãy xác định attacker, key ownership, data lifetime, recovery và rotation.

---

## 14. Thiết kế bảng lưu dữ liệu mã hóa

Ciphertext thường được lưu trong bytea. Bảng nên có metadata đủ để giải mã trong tương lai mà không để lộ key.

### 14.1. Schema minh họa

~~~sql
CREATE TABLE app.protected_value (
    value_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ciphertext BYTEA NOT NULL,
    crypto_scheme TEXT NOT NULL,
    key_version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 14.2. crypto_scheme

Ghi nhận format/algorithm family để biết cách xử lý ciphertext cũ. Không cho phép client tùy ý gửi algorithm name vào dynamic SQL.

### 14.3. key_version

Tham chiếu key version trong KMS/secret manager. Không lưu raw key trong cột này.

### 14.4. Format version

Khi cần, tách thêm format_version để phân biệt payload format, serialization và encryption envelope. Thay đổi format cần migration plan.

### 14.5. Key identifier

Có thể lưu identifier không nhạy cảm để tìm key trong KMS. Không lưu private key/passphrase hoặc secret bytes.

### 14.6. Associated metadata

PGP encryption trong pgcrypto không cung cấp một API AEAD tổng quát nhận arbitrary associated data như một số thư viện ứng dụng. Nếu cần gắn ciphertext với tenant ID, record ID hoặc purpose, thiết kế authenticated context rõ ràng ở application protocol hoặc dùng encryption library hỗ trợ AEAD.

### 14.7. Không để plaintext tồn tại song song lâu hơn cần thiết

Khi migration sang ciphertext:
1. Tạo cột ciphertext và key version.
2. Backfill theo batches.
3. Verify decrypt/round-trip.
4. Chuyển reads/writes sang encrypted path.
5. Xóa plaintext theo retention/backup policy sau khi xác nhận.
6. Kiểm tra logs, replicas, exports và backups theo quy trình data lifecycle.

---

## 15. Quản lý khóa: phần quan trọng hơn câu gọi hàm

Thuật toán tốt không cứu được key bị lộ.

### 15.1. Tách key khỏi ciphertext

Không lưu encryption key/passphrase trong cùng row hoặc cùng database với ciphertext. Nếu attacker lấy database dump, họ không nên có đủ thành phần để giải mã.

### 15.2. Dùng KMS, HSM hoặc secret manager

Quản lý key trong hệ thống có:
- Access control.
- Audit trail.
- Rotation.
- Revocation.
- Backup/recovery.
- Separation of duties.
- Policy theo environment/service.

### 15.3. Envelope encryption

Một mô hình phổ biến:
1. Sinh data encryption key (DEK) ngẫu nhiên.
2. Mã hóa dữ liệu bằng DEK.
3. Dùng key-encryption key (KEK) trong KMS để wrap DEK.
4. Lưu ciphertext và wrapped DEK.
5. Khi đọc, KMS unwrap DEK rồi giải mã ciphertext.

pgcrypto có thể thực hiện một phần encryption trong flow, nhưng việc wrap/unwrap và lifecycle của KEK nên do KMS/client service đảm nhận.

### 15.4. Không truyền key bằng SQL literal

Không viết:

~~~sql
SELECT public.pgp_sym_decrypt(ciphertext, 'my-production-secret');
~~~

Literal có thể xuất hiện trong source, query history, logs, monitoring, shell history hoặc audit. Dùng bind parameters và secret retrieval theo policy. Bind parameters giảm rủi ro lộ trong query text nhưng không làm key bí mật khỏi PostgreSQL server khi server cần xử lý nó.

### 15.5. Key rotation

Rotation có thể gồm:
- Tạo key version mới.
- Dùng key mới cho writes.
- Giải mã/re-encrypt dữ liệu cũ theo batches.
- Theo dõi tỷ lệ rows còn dùng key cũ.
- Thu hồi key cũ sau khi backup/retention và recovery requirements được đáp ứng.

### 15.6. Rotation không phải đổi nhãn version

Không thể đổi key_version từ 1 sang 2 nếu ciphertext vẫn được mã hóa bằng key 1. Cần decrypt bằng key cũ và encrypt bằng key mới.

### 15.7. Recovery và backup

Mất key có thể làm dữ liệu không thể giải mã dù database backup còn nguyên. Backup/recovery plan phải bảo vệ key material và metadata theo quy trình riêng, có test restore thực tế.

### 15.8. Least privilege

Tách quyền:
- Service chỉ được yêu cầu decrypt các records cần thiết.
- Operator không tự động có quyền lấy mọi keys.
- Key administrator quản lý KMS policies.
- Database role chỉ có quyền cần thiết trên encrypted tables/functions.

### 15.9. Key scope

Dùng key riêng theo environment, tenant hoặc purpose khi yêu cầu isolation cao. Tránh một key toàn hệ thống cho mọi ứng dụng và mọi dữ liệu.

---

## 16. Search, equality và indexing trên ciphertext

Encryption có ảnh hưởng trực tiếp tới cách query dữ liệu.

### 16.1. Ciphertext ngẫu nhiên không hỗ trợ equality search trực tiếp

Cùng plaintext có thể tạo ciphertext khác nhau. Do đó, so sánh ciphertext với output của lần encrypt mới không phải cách tìm kiếm ổn định.

### 16.2. Không dùng deterministic encryption tùy tiện

Deterministic encryption làm lộ equality pattern: attacker có thể biết hai rows chứa cùng giá trị, dù không thấy plaintext. Nó còn có thể dễ bị dictionary attack nếu plaintext có entropy thấp.

### 16.3. Blind index

Một thiết kế có thể lưu HMAC của normalized value bằng key riêng:

~~~sql
CREATE TABLE app.customer_lookup (
    customer_id BIGINT PRIMARY KEY,
    encrypted_email BYTEA NOT NULL,
    email_lookup_token BYTEA NOT NULL,
    lookup_key_version INTEGER NOT NULL
);
~~~

Token được tính bằng HMAC trên canonicalized email với secret key riêng. Query equality so sánh token, sau đó decrypt/verify kết quả nếu cần.

### 16.4. Blind index vẫn rò rỉ thông tin

Blind index có thể tiết lộ:
- Các giá trị giống nhau.
- Tần suất lặp.
- Pattern truy vấn.
- Một số thông tin qua known-plaintext hoặc chosen-query scenarios.

Không dùng blind index nếu threat model không chấp nhận leakage đó.

### 16.5. Tách key cho encryption và lookup

Dùng key khác nhau cho ciphertext encryption và HMAC blind index. Có thể derive subkeys từ master key bằng KMS-approved key derivation design, nhưng không tự chế KDF.

### 16.6. Rotation blind index

Khi lookup key thay đổi, cần tính lại tokens cho records hiện có. Lập dual-read/dual-write hoặc migration phase để không làm mất khả năng tìm kiếm trong thời gian chuyển đổi.

---

## 17. pgcrypto server-side và client-side encryption

### 17.1. Server-side pgcrypto

Application gửi plaintext/key tới PostgreSQL function; PostgreSQL mã hóa/giải mã và trả kết quả.

Ưu điểm:
- SQL integration thuận tiện.
- Có thể áp dụng gần data access.
- Có thể giảm logic crypto lặp lại ở nhiều clients.

Giới hạn:
- Server xử lý plaintext và key.
- DBA/host compromise có thể làm lộ dữ liệu.
- Query/logging/configuration có thể làm lộ inputs.
- Khó đáp ứng mô hình zero-knowledge với database operator.

### 17.2. Client-side encryption

Ứng dụng mã hóa trước khi gửi ciphertext tới PostgreSQL và giải mã sau khi đọc.

Ưu điểm:
- DB server không cần nhận plaintext/key.
- Có thể giảm trust vào DBA/server.
- Key policy gắn với application identity.

Đổi lại:
- Search, sorting, constraints và indexing bị hạn chế.
- Client cần quản lý serialization và key lifecycle.
- Nhiều ứng dụng phải thống nhất format.
- Key rotation và migration cần orchestration.

### 17.3. Khi nào chọn?

| Yêu cầu | Hướng tiếp cận |
| --- | --- |
| Cần encryption trong SQL workflow và DB server được tin cậy | pgcrypto server-side có thể phù hợp |
| DBA không được đọc plaintext | Client-side encryption hoặc kiến trúc KMS phù hợp |
| Cần password storage | Password hashing ở application hoặc pgcrypto crypt theo policy |
| Cần nhiều dịch vụ giải mã có kiểm soát | KMS/envelope encryption |
| Cần tìm kiếm equality trên encrypted fields | Blind index có đánh giá leakage hoặc thiết kế chuyên dụng |
| Cần file lớn/streaming | Application/file encryption library phù hợp |

---

## 18. TLS, encryption at rest và pgcrypto

Ba lớp này bảo vệ những ranh giới khác nhau.

### 18.1. TLS

TLS bảo vệ dữ liệu khi truyền giữa client và server. Bật pgcrypto không có nghĩa connection đã được mã hóa.

### 18.2. Storage encryption

Disk encryption, cloud volume encryption hoặc backup encryption bảo vệ storage media/snapshot theo threat model. Nếu database server đang chạy và có quyền đọc file, dữ liệu vẫn có thể được truy cập qua server.

### 18.3. Column-level encryption

pgcrypto có thể mã hóa riêng fields trước khi lưu. Nó giảm khả năng đọc plaintext từ database dumps nếu key tách biệt.

### 18.4. Defense in depth

Một hệ thống có thể cần cả TLS, disk/backup encryption, column encryption, role grants, RLS, audit và key management. Không lớp nào thay thế toàn bộ các lớp khác.

---

## 19. Permissions, schema và logging

### 19.1. Quyền function

Kiểm tra quyền EXECUTE trên các pgcrypto functions và quyền schema USAGE. Tránh cấp EXECUTE rộng cho roles không cần.

### 19.2. Schema qualification

Gọi function bằng schema-qualified name để tránh search_path bị thay đổi hoặc object shadowing.

### 19.3. SECURITY DEFINER

Nếu bọc pgcrypto trong SECURITY DEFINER function:
- Cố định search_path an toàn.
- Schema-qualify objects.
- Kiểm soát EXECUTE grants.
- Không cho input tùy ý tạo SQL động.
- Không trả plaintext cho caller không đủ quyền.

### 19.4. Query logging

Không log password, passphrase, key hoặc plaintext nhạy cảm. Kiểm tra:
- log_statement.
- log_min_duration_statement.
- log_parameter_max_length.
- log_parameter_max_length_on_error.
- Application/APM query capture.
- Audit extension configuration.

Tên và availability của logging parameters phụ thuộc PostgreSQL version.

### 19.5. Error details

Lỗi decrypt có thể phát sinh message/detail. Trả lỗi chung cho client và ghi thông tin chẩn đoán đã mask vào log bảo mật.

### 19.6. Backups và replicas

Ciphertext được replicate/backup như data thông thường. Đảm bảo backup chứa ciphertext nhưng key được bảo vệ riêng. Kiểm tra access policy của replica, analytics export và support dumps.

---

## 20. Performance và giới hạn vận hành

### 20.1. Hashing có cost

digest/HMAC thường nhanh hơn password hashing. bcrypt cố ý chậm để tăng chi phí brute force; cost phải được benchmark.

### 20.2. Encryption tốn CPU

Mã hóa/giải mã từng row trong query lớn có thể tăng CPU và latency. Đo theo payload size, concurrency và query plan.

### 20.3. PGP format overhead

OpenPGP có metadata, session key, integrity information và có thể compression. Ciphertext lớn hơn plaintext. Đừng giả định encrypted column có cùng kích thước.

### 20.4. Không dùng SQL crypto cho file cực lớn

Các hàm pgcrypto nhận toàn bộ value theo kiểu dữ liệu PostgreSQL. Với file lớn hoặc streaming workloads, dùng application/file encryption library có streaming support và lưu object encrypted ở storage phù hợp.

### 20.5. Compression

PGP có options compression. Nén trước encryption thường hiệu quả hơn nén ciphertext; ciphertext gần như không nén thêm được. Cân nhắc data sensitivity, CPU và side-channel concerns khi nén dữ liệu có secrets cùng dữ liệu attacker kiểm soát.

### 20.6. Connection concurrency

Password hashing cost cao có thể tạo CPU spike nếu login concurrency tăng. Rate-limit, queue hoặc thực hiện password hashing ở application auth service.

### 20.7. Query planner

Một predicate gọi pgp_sym_decrypt trên từng row có thể tốn CPU và ngăn index sử dụng hiệu quả. Thiết kế blind index/search path riêng nếu thật sự cần.

### 20.8. Resource isolation

Theo dõi CPU, query duration, lock waits, memory, connection pool và errors. Không để một API cho phép client gửi payload khổng lồ vào hàm crypto mà không có giới hạn.

---

## 21. Error handling và validation

### 21.1. Sai passphrase hoặc key

Giải mã có thể thất bại nếu key/passphrase sai, ciphertext hỏng hoặc format không hợp lệ. Không coi mọi lỗi decrypt là "password sai".

### 21.2. Ciphertext bị truncate

bytea bị cắt hoặc serialization sai có thể khiến decryption lỗi. Kiểm tra transport, schema type và application encoding.

### 21.3. Algorithm mismatch

Các bên cần thống nhất PGP format/options và key material. Lưu crypto_scheme/format version để chọn đúng decrypt path.

### 21.4. Input validation

Giới hạn payload length, validate encoding và phân quyền trước khi decrypt. Tránh cho attacker dùng endpoint decrypt như oracle tùy ý.

### 21.5. Không trả raw crypto error ra ngoài

Trả response chung, tránh tiết lộ key validity, parsing details hoặc nội dung dữ liệu. Ghi error code nội bộ và correlation ID không chứa secret.

### 21.6. Round-trip tests

Với dữ liệu text/binary, test:
- Plaintext → encrypt → decrypt.
- Unicode.
- Empty string/empty bytea nếu use case cho phép.
- Null handling.
- Payload lớn nhất.
- Key sai.
- Ciphertext hỏng.
- Key version cũ/mới.
- Cross-version compatibility.

---

## 22. Các anti-pattern thường gặp

| Anti-pattern | Vấn đề | Cách phù hợp hơn |
| --- | --- | --- |
| digest(password, 'sha256') | Hash quá nhanh, dễ brute force | crypt bcrypt hoặc Argon2id |
| Dùng md5/sha1 cho integrity mới | Collision resistance không phù hợp | SHA-256/512 hoặc HMAC |
| Dùng digest thay HMAC | Attacker có thể tự tính lại sau khi sửa payload | hmac với key bí mật |
| Dùng HMAC để giấu plaintext | HMAC không mã hóa | Encryption |
| Dùng encryption cho password | Có thể giải mã nếu key lộ | Password hashing |
| Lưu key cạnh ciphertext | Database dump có cả hai | KMS/secret manager tách biệt |
| Đưa key vào SQL literal | Có thể lộ qua logs/history | Bind parameter + secret manager |
| Dùng random() tạo token | Không phải CSPRNG | gen_random_bytes |
| So sánh ciphertext để tìm plaintext | Encryption ngẫu nhiên | Blind index có đánh giá leakage |
| Dùng PGP encryption để chứng minh sender | Public key có thể dùng bởi bất kỳ ai | Digital signature/HMAC |
| Tin armor header như identity | Header không phải trust proof | Verify fingerprint/signature |
| Bật disable-mdc | Tắt integrity protection | Giữ integrity check |
| Dùng một key cho mọi mục đích | Cross-purpose compromise | Key separation |
| Không lưu key version | Không biết decrypt bằng key nào | Metadata version |
| Rotate key bằng đổi version column | Ciphertext vẫn dùng key cũ | Decrypt/re-encrypt |
| Cho DBA key dù threat model cấm DBA | Server-side pgcrypto thấy key | Client-side encryption |
| Mã hóa toàn bộ file lớn trong SQL | Memory/CPU/size overhead | Streaming encryption ngoài DB |
| Không test restore key | Backup có thể không giải mã được | Recovery rehearsal |

---

## 23. Ví dụ tổng hợp: checksum cho payload

Checksum phù hợp khi cần fingerprint dữ liệu và digest được lưu/nhận qua kênh đáng tin cậy.

### 23.1. Tạo digest

~~~sql
SELECT encode(
    public.digest(convert_to($1::text, 'UTF8'), 'sha256'),
    'hex'
) AS payload_fingerprint;
~~~

### 23.2. So sánh

Tính digest lại trên payload nhận được và so với fingerprint đã lưu.

### 23.3. Giới hạn

Nếu attacker có thể sửa cả payload và fingerprint, họ có thể tạo cặp mới. Dùng HMAC hoặc signature nếu cần xác thực.

### 23.4. Lưu metadata

Ghi algorithm và canonicalization version để hệ thống biết cách tính lại fingerprint khi format thay đổi.

---

## 24. Ví dụ tổng hợp: HMAC cho webhook

### 24.1. Payload

Giả sử webhook body được nhận dưới dạng bytea để giữ nguyên byte sequence. Không parse JSON rồi serialize lại trước khi xác minh nếu sender tính HMAC trên raw body.

### 24.2. Tính HMAC

~~~sql
SELECT public.hmac(
    $1::bytea,
    $2::bytea,
    'sha256'
);
~~~

### 24.3. Xác minh

So sánh MAC nhận được với MAC tính lại bằng phương pháp constant-time ở trusted application/library. SQL query minh họa không thay thế yêu cầu constant-time comparison trong security boundary có thể quan sát timing.

### 24.4. Chống replay

Xác minh timestamp/signature window, nonce hoặc event ID và lưu các event đã xử lý. HMAC hợp lệ không tự ngăn một webhook cũ bị phát lại.

### 24.5. Key rotation

Có thể duy trì một thời gian ngắn key hiện tại và key trước đó trong quá trình rotate, kèm key identifier không nhạy cảm. Thu hồi key cũ sau khi hết compatibility window.

---

## 25. Ví dụ tổng hợp: password authentication

### 25.1. Tạo hash

~~~sql
INSERT INTO app_user_auth (
    user_id,
    username,
    password_hash
)
VALUES (
    $1,
    $2,
    public.crypt($3, public.gen_salt('bf', 12))
);
~~~

### 25.2. Verify

~~~sql
SELECT password_hash = public.crypt($1, password_hash)
FROM app_user_auth
WHERE username = $2;
~~~

### 25.3. Rate limit

Đặt rate limits ở auth service/API, theo user và network risk. Hash cost cao không tự chống credential stuffing nếu endpoint cho phép request vô hạn.

### 25.4. Rehash

Sau khi xác minh đúng password, nếu cost cũ thấp hơn policy, tạo hash mới và update trong transaction.

### 25.5. Không log input

Không log bind parameter password hoặc request body chứa credentials. Kiểm tra APM/error capture.

---

## 26. Ví dụ tổng hợp: mã hóa field nhạy cảm

### 26.1. Bảng

~~~sql
CREATE TABLE app.customer_private_data (
    customer_id BIGINT PRIMARY KEY,
    encrypted_tax_id BYTEA NOT NULL,
    key_version INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 26.2. Insert ciphertext

~~~sql
INSERT INTO app.customer_private_data (
    customer_id,
    encrypted_tax_id,
    key_version
)
VALUES (
    $1,
    public.pgp_sym_encrypt($2::text, $3::text),
    $4
);
~~~

$3 là passphrase/key được truyền theo secret flow; ví dụ này không khuyến khích đặt key trong SQL source hoặc bảng database.

### 26.3. Decrypt có phân quyền

~~~sql
SELECT public.pgp_sym_decrypt(encrypted_tax_id, $1::text)
FROM app.customer_private_data
WHERE customer_id = $2;
~~~

Chỉ service role được phép gọi path giải mã. Xem xét bọc trong function có authorization rõ ràng và không trả plaintext cho role không đủ quyền.

### 26.4. Lưu key version

Khi đọc row, ứng dụng dùng key_version để lấy key phù hợp từ KMS/secret manager. Không dùng một key hard-coded cho mọi version.

### 26.5. Xử lý search

Không tìm bằng decrypt toàn bộ bảng trong request path nếu có thể tránh. Nếu cần lookup exact match, đánh giá blind index bằng HMAC key riêng và chấp nhận rõ equality leakage.

---

## 27. Quy trình key rotation

### Bước 1: Chuẩn bị key mới

Tạo key version mới trong KMS/secret manager, đặt policy và quyền truy cập.

### Bước 2: Bắt đầu writes bằng key mới

Application ghi ciphertext mới cùng key_version mới.

### Bước 3: Đọc dữ liệu cũ theo version

Khi đọc row, chọn key theo metadata. Không thử lần lượt mọi key nếu có thể xác định version.

### Bước 4: Re-encrypt theo batches

1. Đọc ciphertext cũ.
2. Decrypt bằng key cũ.
3. Encrypt bằng key mới.
4. Cập nhật ciphertext và key_version atomically.
5. Commit batch.
6. Ghi progress/idempotency marker.

### Bước 5: Xác minh

Đếm rows theo key_version; thử decrypt sample và kiểm tra application workflows. Theo dõi lỗi decrypt và latency.

### Bước 6: Backup và retention

Xác nhận backup cần thiết có thể khôi phục bằng key cũ trong thời gian retention. Không revoke key cũ trước khi hết nhu cầu restore hợp lệ.

### Bước 7: Thu hồi key cũ

Sau khi toàn bộ data, replicas, exports và backups đã được xử lý theo policy, revoke key cũ và lưu audit evidence.

### Bước 8: Blind index rotation

Nếu lookup HMAC key cũng đổi, lập kế hoạch tính lại token và dual-read/dual-write trong thời gian chuyển đổi.

---

## 28. Lab 1: cài pgcrypto và dùng digest

Dùng database development/staging.

### 28.1. Kiểm tra package

~~~sql
SELECT *
FROM pg_catalog.pg_available_extensions
WHERE name = 'pgcrypto';
~~~

### 28.2. Cài extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

### 28.3. Tạo SHA-256

~~~sql
SELECT encode(public.digest('hello', 'sha256'), 'hex');
~~~

### 28.4. Thử encoding

~~~sql
SELECT encode(
    public.digest(convert_to('Xin chào PostgreSQL', 'UTF8'), 'sha256'),
    'hex'
);
~~~

### 28.5. So sánh hai payload

Tính digest cho hai strings khác nhau và quan sát output khác nhau. Không dùng lab này để tuyên bố hash chứng minh sender identity.

### 28.6. Kết luận

digest tạo fingerprint một chiều và trả bytea; encode chỉ chuyển representation để hiển thị.

---

## 29. Lab 2: HMAC và integrity verification

### 29.1. Chuẩn bị test key

Dùng một key giả lập trong môi trường lab; không dùng secret production. Trong ứng dụng thật, truyền key bằng bind parameter.

### 29.2. Tạo HMAC

~~~sql
SELECT encode(
    public.hmac(
        convert_to('event=created&id=42', 'UTF8'),
        decode($1, 'hex'),
        'sha256'
    ),
    'hex'
);
~~~

$1 là test key dạng hex.

### 29.3. Thay đổi payload

Tính HMAC cho payload có một byte/character khác và quan sát MAC thay đổi.

### 29.4. Thay đổi key

Dùng key khác và quan sát MAC không khớp.

### 29.5. Thảo luận replay

Gửi lại đúng payload và MAC cũ vẫn tạo một cặp hợp lệ. Thiết kế timestamp/nonce/event ID để chống replay.

### 29.6. Kết luận

HMAC cần shared secret và bảo vệ key. Nó xác thực payload nhưng không mã hóa payload.

---

## 30. Lab 3: password hashing với crypt

### 30.1. Tạo test hash

~~~sql
SELECT public.crypt(
    'Lab-only-password',
    public.gen_salt('bf', 10)
) AS password_hash;
~~~

Cost 10 chỉ dùng cho lab; production cần benchmark và policy.

### 30.2. Verify đúng password

~~~sql
SELECT
    public.crypt('Lab-only-password', password_hash) = password_hash
FROM (
    SELECT public.crypt(
        'Lab-only-password',
        public.gen_salt('bf', 10)
    ) AS password_hash
) AS test_data;
~~~

### 30.3. Verify sai password

Thay input bằng một password khác. Kết quả phải false.

### 30.4. So sánh cost

Sinh hash với các cost khác nhau và đo thời gian trong môi trường lab. Không tạo benchmark gây CPU exhaustion trên production.

### 30.5. Thảo luận bcrypt length

Xem xét UTF-8 byte length và giới hạn 72 bytes. Đề xuất cách xử lý password dài theo application policy.

### 30.6. Kết luận

crypt dùng salt/setting để xác minh password. Không dùng digest nhanh để thay thế.

---

## 31. Lab 4: symmetric encryption và binary data

### 31.1. Mã hóa text

~~~sql
SELECT public.pgp_sym_encrypt(
    'Sensitive lab note',
    $1::text
);
~~~

Dùng passphrase giả lập trong lab.

### 31.2. Giải mã

~~~sql
SELECT public.pgp_sym_decrypt(
    $1::bytea,
    $2::text
);
~~~

### 31.3. Thử sai passphrase

Dùng passphrase khác và quan sát lỗi. Không trả raw error details cho end users trong ứng dụng.

### 31.4. Thử bytea

~~~sql
SELECT public.pgp_sym_encrypt_bytea(
    decode('000102ff', 'hex'),
    $1::text
);
~~~

Sau đó dùng pgp_sym_decrypt_bytea và encode kết quả để xác nhận bytes khớp.

### 31.5. Kiểm tra ciphertext size

So sánh octet_length của plaintext và ciphertext. PGP packet metadata làm ciphertext có overhead.

### 31.6. Kết luận

Dùng text hoặc bytea API đúng loại dữ liệu và quản lý passphrase bên ngoài database.

---

## 32. Lab 5: public-key encryption và armor

Lab cần một cặp PGP key thử nghiệm được tạo bởi OpenPGP tool được phê duyệt. Không tạo hoặc dùng private key production trong lab.

### 32.1. Lấy public key armor

Đưa armored public key thử nghiệm vào bind parameter hoặc một fixture an toàn.

### 32.2. Mã hóa

~~~sql
SELECT public.pgp_pub_encrypt(
    'Message for lab recipient',
    public.dearmor($1::text)
);
~~~

### 32.3. Armor ciphertext

~~~sql
SELECT public.armor($1::bytea);
~~~

### 32.4. Đọc headers

~~~sql
SELECT *
FROM public.pgp_armor_headers($1::text);
~~~

### 32.5. Giải mã

~~~sql
SELECT public.pgp_pub_decrypt(
    $1::bytea,
    public.dearmor($2::text),
    $3::text
);
~~~

$2 là armored private key thử nghiệm; $3 là private-key passphrase nếu có.

### 32.6. Kiểm tra identity

Dùng fingerprint từ OpenPGP key management tool để xác nhận public key. Không dựa vào armor headers hoặc key ID đơn lẻ.

### 32.7. Kết luận

Public-key encryption giải quyết việc mã hóa cho người nhận; nó không tự tạo chữ ký xác thực sender.

---

## 33. Bài tập thực hành

### Bài 1 — Primitive selection

Phân biệt digest, HMAC, password hash, symmetric encryption và public-key encryption.

### Bài 2 — Threat model

Một DBA có quyền superuser. pgcrypto server-side có bảo vệ plaintext khỏi DBA không? Giải thích.

### Bài 3 — Installation

Viết các câu lệnh kiểm tra pgcrypto package, cài extension và xác nhận schema/version.

### Bài 4 — Multi-database

Vì sao CREATE EXTENSION pgcrypto phải được thực hiện trong từng database cần dùng?

### Bài 5 — Digest

Viết query tạo SHA-256 cho text UTF-8 và hiển thị dạng hex.

### Bài 6 — Digest algorithms

So sánh MD5, SHA-1, SHA-256 và SHA-512. Thuật toán nào phù hợp cho fingerprint mới?

### Bài 7 — Canonicalization

Hai hệ thống tính hash cho cùng JSON nhưng output khác. Liệt kê nguyên nhân và cách chuẩn hóa.

### Bài 8 — Hash integrity

Một attacker có thể sửa payload và digest. Vì sao digest không ngăn được attacker này?

### Bài 9 — HMAC

Viết query tạo HMAC-SHA256 từ bytea payload và key bind parameter.

### Bài 10 — HMAC vs encryption

Vì sao HMAC không làm payload bí mật?

### Bài 11 — Replay

Một webhook có HMAC hợp lệ bị gửi lại. Thiết kế nonce/timestamp/event ID để chống replay.

### Bài 12 — Key management

Đề xuất nơi lưu HMAC key và cách phân quyền service.

### Bài 13 — Password hashing

Viết INSERT dùng crypt và gen_salt('bf', cost) để lưu password hash.

### Bài 14 — Password verification

Viết query xác minh password từ hash đã lưu.

### Bài 15 — Cost

Giải thích cost bcrypt ảnh hưởng thời gian tính toán như thế nào và cách benchmark.

### Bài 16 — Password schemes

Vì sao DES/xdes/MD5 schemes trong crypt không nên dùng cho hệ thống mới?

### Bài 17 — Bcrypt length

Giải thích giới hạn 72 bytes và vì sao bytes khác số ký tự Unicode.

### Bài 18 — Argon2id

pgcrypto có cung cấp Argon2id không? Nếu policy yêu cầu Argon2id, nên đặt phần password hashing ở đâu?

### Bài 19 — Randomness

Viết query tạo 32 random bytes và encode thành token text.

### Bài 20 — random()

Vì sao random() không phù hợp tạo reset token hoặc encryption key?

### Bài 21 — Symmetric encryption

Viết ví dụ pgp_sym_encrypt và pgp_sym_decrypt cho một text field.

### Bài 22 — Binary encryption

Phân biệt pgp_sym_encrypt với pgp_sym_encrypt_bytea.

### Bài 23 — Cipher options

Nêu những yếu tố cần xác nhận trước khi chỉ định cipher-algo=aes256.

### Bài 24 — PGP integrity

MDC/integrity protection giải quyết điều gì? Vì sao nó không chứng minh danh tính sender?

### Bài 25 — Public-key encryption

Giải thích bên nào dùng public key để encrypt và bên nào dùng private key để decrypt.

### Bài 26 — Digital signature

Vì sao pgp_pub_encrypt không thay thế digital signature?

### Bài 27 — Armor

Viết query armor ciphertext và dearmor text trở lại bytea.

### Bài 28 — Key ID

pgp_key_id giúp ích gì và vì sao fingerprint đầy đủ đáng tin hơn để xác minh identity?

### Bài 29 — Key separation

Thiết kế key riêng cho encryption và HMAC blind index.

### Bài 30 — Envelope encryption

Mô tả DEK, KEK, wrapping/unwrapping và vai trò KMS.

### Bài 31 — Key rotation

Viết các bước re-encrypt ciphertext từ key version 1 sang version 2.

### Bài 32 — Backup recovery

Vì sao database backup không đủ nếu key version cũ đã bị revoke hoặc mất?

### Bài 33 — Search encrypted field

Vì sao ciphertext PGP không thể được dùng làm equality lookup trực tiếp?

### Bài 34 — Blind index

Thiết kế HMAC lookup token cho email. Nêu equality leakage và key rotation requirements.

### Bài 35 — DBA threat

Một yêu cầu quy định DBA không được xem plaintext. So sánh pgcrypto server-side với client-side encryption.

### Bài 36 — Logging

Liệt kê nơi password, passphrase hoặc key có thể bị ghi lại ngoài ý muốn.

### Bài 37 — Performance

Một query decrypt 10 triệu rows rất chậm. Nêu cách thiết kế lại access path và giới hạn decryption.

### Bài 38 — PGP key lifecycle

Thiết kế quy trình tạo, xác minh fingerprint, lưu private key, revoke và rotate key pair.

### Bài 39 — Failure handling

Thiết kế API response khi decrypt thất bại mà không tiết lộ thông tin về key hoặc ciphertext.

### Bài 40 — End-to-end design

Một ứng dụng lưu password, webhook payload, email tìm kiếm được và tax ID cần mã hóa. Chọn primitive cho từng loại, thiết kế key separation/KMS, schema, rotation, logging, permissions, backup recovery và test plan. Giải thích vì sao không thể dùng một hàm pgcrypto cho tất cả.

---

## 34. Checklist vận hành pgcrypto

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| Use case | Confidentiality, integrity, password verification hay randomness |
| Threat model | Ai cần bị ngăn đọc/sửa dữ liệu |
| PostgreSQL version | Source/target major version |
| OpenSSL | Build/package hỗ trợ pgcrypto |
| Extension | Package có sẵn và extension đã cài trong đúng database |
| Extension schema | Schema thực tế và qualified function names |
| Function grants | EXECUTE/USAGE theo least privilege |
| Digest | Algorithm hiện đại và canonical input |
| HMAC | Key entropy, purpose separation và rotation |
| Password | bcrypt cost benchmark hoặc Argon2id policy |
| Bcrypt length | Password UTF-8 byte length và 72-byte behavior |
| Randomness | gen_random_bytes, không dùng random() |
| Encryption | Text/bytea function đúng kiểu dữ liệu |
| PGP options | Cipher, S2K và integrity protection |
| Public/private keys | Fingerprint verification và ownership |
| Digital signatures | Có giải pháp ký/verify riêng nếu cần |
| Key management | KMS/HSM/secret manager ngoài DB |
| Key separation | Encryption/HMAC keys khác nhau |
| Key version | Metadata gắn với ciphertext |
| Rotation | Re-encryption và recovery window |
| Search | Blind index leakage được đánh giá |
| Client/server boundary | DB server có nhìn plaintext/key không |
| TLS | Connection transport được bảo vệ |
| Storage/backup | Ciphertext và key backup tách biệt |
| Logging | Query/error/APM không chứa secrets |
| Permissions | Role không có quyền decrypt ngoài nhu cầu |
| SECURITY DEFINER | search_path và object qualification an toàn |
| Performance | CPU, payload size, concurrency và latency |
| Input validation | Size, encoding và decrypt authorization |
| Error handling | Không lộ crypto internals cho client |
| Compatibility | Cipher/format tương thích source và target |
| Restore test | Có thể lấy key và decrypt backup sample |
| Audit | Ai truy cập key, decrypt và rotate |
| Incident response | Revoke/rotate khi key compromise |

## Kết luận

pgcrypto cung cấp các building blocks hữu ích cho mật mã trong PostgreSQL: digest tạo fingerprint, HMAC xác thực dữ liệu bằng shared secret, crypt/gen_salt lưu password hash, gen_random_bytes tạo random bytes, và các pgp functions mã hóa/giải mã dữ liệu theo OpenPGP.

Những nguyên tắc cần nhớ:

1. **Chọn primitive theo mục tiêu.** Hash, HMAC, password hashing, encryption và randomness giải quyết các bài toán khác nhau.
2. **digest không phải HMAC.** Digest không keyed không ngăn attacker tự tính lại hash sau khi sửa payload.
3. **HMAC không mã hóa.** Nó xác thực dữ liệu với shared secret nhưng plaintext vẫn đọc được.
4. **Không dùng SHA-256 để lưu password.** Dùng password hashing có salt/cost như bcrypt hoặc Argon2id theo policy.
5. **Bcrypt có giới hạn input 72 bytes.** Xem xét UTF-8 byte length và policy cho password dài.
6. **Dùng CSPRNG cho token và key material.** gen_random_bytes phù hợp hơn random().
7. **PGP encryption cần key mạnh và được quản lý.** Đừng lưu passphrase/private key cạnh ciphertext.
8. **Public-key encryption không phải chữ ký số.** Nó mã hóa cho người nhận nhưng không xác minh sender.
9. **pgcrypto chạy bên trong server.** PostgreSQL xử lý plaintext/key; nếu DBA không được phép thấy plaintext, cân nhắc client-side encryption.
10. **Quản lý key là yêu cầu bắt buộc.** Dùng KMS/HSM/secret manager, key version, separation và rotation.
11. **Ciphertext ngẫu nhiên không hỗ trợ equality search trực tiếp.** Blind index có thể giúp nhưng làm lộ equality/frequency patterns.
12. **TLS và encryption at rest vẫn cần thiết.** pgcrypto không thay thế transport/storage protections.
13. **Không đưa secret vào SQL literal hoặc logs.** Dùng bind parameters và kiểm soát query/error capture.
14. **Test recovery cùng key lifecycle.** Backup chỉ hữu ích nếu key cần thiết vẫn có thể truy cập theo policy.
15. **Đo performance trên workload thật.** Password hashing, encryption và decryption đều có chi phí CPU và có thể ảnh hưởng concurrency.

Một thiết kế pgcrypto tốt bắt đầu bằng threat model, chọn đúng primitive, giữ key ngoài database khi cần, lưu metadata đủ cho rotation và kiểm tra cả đường đọc, ghi, backup lẫn recovery. Hàm mật mã chỉ là một phần của hệ thống; an toàn phụ thuộc vào cách key, quyền truy cập, logs và ứng dụng cùng được quản lý.
