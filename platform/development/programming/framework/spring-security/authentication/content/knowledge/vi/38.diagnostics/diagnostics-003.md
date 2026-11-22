# Mật khẩu đúng nhưng xác minh thất bại do encoder, tiền tố hoặc dữ liệu băm

Một tình huống dễ gây nhầm trong **Spring Security - authentication**: người dùng khẳng định đã nhập đúng mật khẩu nhưng hệ thống vẫn trả “Bad credentials”, HTTP 401 hoặc chuyển hướng đến `/login?error`. Đôi khi log có câu `There is no PasswordEncoder mapped for the id "null"`, đôi khi `PasswordEncoder.matches(...)` chỉ trả `false`, và đôi khi phương thức xác thực chưa hề đi tới bước kiểm mật khẩu.

Nguyên nhân có thể không phải người dùng gõ sai: **encoder được chọn không khớp dữ liệu băm đã lưu**, tiền tố thuật toán `{id}` bị thiếu/sai, hash bị cắt khi lưu database, mật khẩu bị biến đổi giữa lúc đăng ký và đăng nhập, hoặc luồng xác thực đang tải nhầm account/hash.

Bài học thuộc nhóm **Chẩn đoán**, dùng **Java 17+, Spring Boot 3.x và Spring Security 6.x (ưu tiên tài liệu 6.5)**. Nội dung gồm cơ chế `DaoAuthenticationProvider`/`PasswordEncoder`; ý nghĩa của `{bcrypt}` và các ID khác; cây chẩn đoán không rò credential; ví dụ runnable; test JUnit/Spring Security; cách xử lý legacy hash an toàn; và checklist để tránh gây gián đoạn đăng nhập khi nâng cấp.

> **Quy tắc bảo mật xuyên suốt:** Không yêu cầu người dùng gửi mật khẩu, hash, access token hay bản dump bảng users vào chat/ticket. Không log raw password, `UserDetails.getPassword()`, toàn bộ đối tượng `Authentication` hoặc câu SQL chứa mật khẩu. Khi cần điều tra, thu thập **mã loại hash, độ dài, trạng thái, phiên bản encoder, ID sự kiện** trong môi trường kiểm soát; không ghi giá trị hash đầy đủ.

## 1. Trước hết, xác định “thất bại” xảy ra ở đâu

Một request password login tiêu biểu theo Servlet `formLogin`:

~~~text
Browser/HTTP client
   │
   ├── POST /login + username/password + CSRF token
   ▼
Spring Security FilterChain
   │
   ├── CsrfFilter: token có hợp lệ?
   │       └─ Không → 403 (chưa cần so password)
   ▼
UsernamePasswordAuthenticationFilter
   │
   ▼
AuthenticationManager (thường ProviderManager)
   │
   ▼
DaoAuthenticationProvider
   │
   ├── UserDetailsService.loadUserByUsername(username)
   │       ├── User không tồn tại / lỗi nguồn dữ liệu
   │       └── Trả UserDetails: getPassword() = encoded password
   │
   ├── Pre-check account: enabled / locked / expired
   │
   ├── PasswordEncoder.matches(rawFromRequest, encodedFromStore)
   │       ├── true  → password được chấp nhận
   │       ├── false → BadCredentialsException
   │       └── lỗi cấu hình/hash → có thể ném exception
   │
   └── Post-check, MFA/policy bổ sung, thành công hoặc thất bại
   ▼
Form success/failure handler hoặc Basic authentication entry point
   │
   ├── Form: thường redirect 302 tới /login?error
   └── HTTP Basic: thường 401 với WWW-Authenticate
~~~

**Đừng đọc HTTP 403 hoặc 302 rồi kết luận ngay “encoder sai”.** Một 403 trên `POST /login` có thể do CSRF; một 403 sau khi login thành công có thể do không đủ role; một 302 có thể là redirect bình thường của form login; còn 401 Basic cũng có thể do user bị disabled hoặc provider chưa được cấu hình.

### 1.1. Hai đối số của PasswordEncoder.matches

Phương thức quan trọng nhất:

~~~java
boolean accepted = encoder.matches(rawPassword, storedEncodedPassword);
~~~

- `rawPassword`: giá trị người dùng nhập, **chưa hash**, sau các bước normalization đã được policy xác nhận là nhất quán.
- `storedEncodedPassword`: **chuỗi hash đã lưu** (có thể gồm prefix `{id}`), được lấy từ user repository.
- `PasswordEncoder.matches` chọn thuật toán, tính phép kiểm dựa trên salt/parameters nằm trong hash và so sánh phù hợp.

**Sai phổ biến:** truyền `encoder.encode(rawPassword)` vào tham số thứ nhất, rồi so với hash đã lưu. Nhiều thuật toán sử dụng salt ngẫu nhiên, nên hash mới của cùng password khác hash cũ; đó không phải cách xác minh.

~~~java
// ĐÚNG: raw + stored encoded
encoder.matches(rawPassword, storedEncodedPassword);

// SAI: encode lại trước khi matches
encoder.matches(encoder.encode(rawPassword), storedEncodedPassword);

// SAI: so hai hash tạo độc lập
encoder.encode(rawPassword).equals(storedEncodedPassword);
~~~

Một password khi encode hai lần có thể tạo **hai hash khác nhau** vì salt; hai chuỗi hash khác nhau **không chứng minh mật khẩu khác nhau**.

### 1.2. DaoAuthenticationProvider có vai trò gì?

Theo tài liệu Spring Security 6.5, `DaoAuthenticationProvider`:

1. Nhận username/password trong một `UsernamePasswordAuthenticationToken`.
2. Gọi `UserDetailsService` để lấy `UserDetails` tương ứng.
3. Dùng `PasswordEncoder` kiểm raw password với `userDetails.getPassword()`.
4. Kiểm trạng thái account phù hợp và trả `Authentication` thành công khi mọi điều kiện cho phép.

Có thể cấu hình encoder ở bean toàn ứng dụng hoặc trực tiếp trên một provider. Nếu ứng dụng có **nhiều `SecurityFilterChain`, nhiều authentication managers/providers hoặc cấu hình test riêng**, đừng chỉ tìm bean `PasswordEncoder` rồi kết luận mọi đường login đều sử dụng bean ấy. Phải xác định **provider thực được chọn cho endpoint và user repository thật**.

Trong Spring Security 6.5, API constructor nên dùng:

~~~java
DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider(userDetailsService);
provider.setPasswordEncoder(passwordEncoder);
~~~

Đây là **snippet bên trong một method/config bean** có các biến `userDetailsService` và `passwordEncoder` đã được cấp. Imports thuộc `org.springframework.security.authentication.dao.DaoAuthenticationProvider`, `org.springframework.security.core.userdetails.UserDetailsService`, `org.springframework.security.crypto.password.PasswordEncoder`. Không tạo thêm một provider như vậy vào project đang chạy chỉ để sửa lỗi khi chưa hiểu wiring hiện tại.

## 2. Cấu trúc mật khẩu lưu với DelegatingPasswordEncoder

Spring Security dùng `DelegatingPasswordEncoder` để cho phép **mã hóa mới bằng thuật toán hiện hành nhưng vẫn xác minh hash cũ theo đúng thuật toán của từng bản ghi**.

Cú pháp lưu:

~~~text
{id}encodedPassword
~~~

Ví dụ bcrypt:

~~~text
{bcrypt}$2a$10$.....................................................
│       └─ BCrypt encoded hash chứa version, cost, salt và checksum
└─ ID để DelegatingPasswordEncoder chọn đúng encoder
~~~

Dấu chấm trong hình là **ký hiệu minh họa**, không phải hash hợp lệ. Một bcrypt hash compact hợp lệ thường dài **60 ký tự**; tiền tố `{bcrypt}` dài **8 ký tự**, nên dạng prefixed thường dài **68 ký tự**.

| Chuỗi lưu | Ý nghĩa | Encoder kỳ vọng |
| --- | --- | --- |
| `{bcrypt}$2a$10$...` | Bcrypt đã gắn prefix | `BCryptPasswordEncoder` được map với key `bcrypt` |
| `$2a$10$...` | Bcrypt **raw**, thiếu Spring prefix | Dùng trực tiếp BCrypt; Delegating mặc định báo thiếu ID |
| `{pbkdf2@SpringSecurity_v5_8}...` | PBKDF2 cấu hình phiên bản Spring 5.8 | `Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8()` |
| `{pbkdf2}...` | Một cấu hình PBKDF2 legacy trong mapping mặc định | Không tự đổi ID sang `pbkdf2@SpringSecurity_v5_8` |
| `{scrypt@SpringSecurity_v5_8}...` | SCrypt với bộ tham số theo ID cụ thể | Encoder SCrypt tương ứng |
| `{argon2@SpringSecurity_v5_8}...` | Argon2 theo cấu hình Spring tương ứng | Encoder Argon2 tương ứng và dependencies phù hợp |
| `{noop}plaintext` | Legacy/no-op, không hash | **Không dùng cho mật khẩu mới ở production** |
| `{unknown}...` | ID không được map | Delegating mặc định ném exception |
| `$2y$...` hoặc `$2b$...` không prefix | Biến thể bcrypt raw từ hệ thống khác | Phải xác nhận compatibility/thư viện rồi migrate |
| `bcrypt:...` | Không phải format mặc định `{id}...` | Cần adapter/migration, không tự đoán |

**Dấu `{id}` là metadata chọn thuật toán**, không phải salt, không phải thuật toán bcrypt và không phải một chuỗi cần ghép vào **raw password**. Với `DelegatingPasswordEncoder.matches(raw, "{bcrypt}"+bcryptHash)`, Spring tách `{bcrypt}` ra rồi chuyển **phần hash phía sau** cho `BCryptPasswordEncoder`.

Không suy ra “bcrypt đúng” chỉ vì hash bắt đầu bằng `$2`: phải kiểm format/độ dài/phiên bản hợp lệ và xác minh bằng encoder phù hợp, không log hoặc công khai giá trị.

### 2.1. Tạo encoder mặc định

~~~java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Import:

~~~java
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
~~~

Theo tài liệu 6.5, factory mặc định **encode mới bằng `bcrypt`**, trả chuỗi bắt đầu `{bcrypt}`, và có mapping cho một số format cũ như PBKDF2, SCrypt, Argon2 và các legacy IDs. **Hỗ trợ verify một format legacy không có nghĩa thuật toán legacy vẫn nên dùng để tạo password mới.**

Nếu hệ thống ban đầu dùng `new BCryptPasswordEncoder()`, `encode(...)` thường sinh chuỗi `$2a$...` không có `{bcrypt}`. Sau này đổi bean sang `PasswordEncoderFactories.createDelegatingPasswordEncoder()` mà **không migrate các giá trị lưu cũ** thì người dùng nhập đúng vẫn gặp lỗi prefix.

### 2.2. idForEncode khác với ID của hash đang kiểm

Trong `DelegatingPasswordEncoder`:

- `idForEncode` quyết định thuật toán khi **encode mới**.
- `{id}` trong mỗi stored hash quyết định thuật toán khi **matches**.
- Hash cũ `{bcrypt}...` có thể vẫn verify trong khi password mới được encode bằng PBKDF2/Argon2 (nếu cấu hình cả mappings đúng).
- Không được gắn tiền tố thuật toán mới lên **phần hash cũ thuộc thuật toán khác**; làm vậy chỉ thay nhãn, không đổi thuật toán.

Ví dụ migrate sai:

~~~text
Trước:  {bcrypt}$2a$10$...
Sai:    {pbkdf2@SpringSecurity_v5_8}$2a$10$...
~~~

Phần đuôi vẫn là bcrypt; PBKDF2 không thể xác minh hash bcrypt chỉ vì prefix bị thay. Để chuyển thuật toán phải **xác minh mật khẩu người dùng hiện tại rồi re-encode bằng encoder mới**, hoặc bắt buộc reset password qua quy trình đáng tin.

## 3. Lỗi “There is no PasswordEncoder mapped for the id null”

Đây là trường hợp điển hình:

~~~text
java.lang.IllegalArgumentException:
There is no PasswordEncoder mapped for the id "null"
~~~

Thông điệp là **dấu hiệu chẩn đoán** trong tài liệu Spring Security 6.5; văn bản exception có thể khác theo phiên bản. Nó thường có nghĩa `DelegatingPasswordEncoder` không tìm thấy `{id}` tại đầu `storedEncodedPassword`. Nó **không phải** bằng chứng password nhập sai.

Ví dụ:

~~~java
BCryptPasswordEncoder legacy = new BCryptPasswordEncoder();
String rawBcryptHash = legacy.encode("lab-password-2026");

PasswordEncoder delegating =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

delegating.matches("lab-password-2026", rawBcryptHash);
// Thường ném IllegalArgumentException vì rawBcryptHash thiếu {id}.
~~~

Đây là đoạn **đặt bên trong method**; cần imports `BCryptPasswordEncoder`, `PasswordEncoder` và `PasswordEncoderFactories`. Không dùng password thật trong snippet/console.

### 3.1. Cách sửa đúng khi biết chắc format là bcrypt

Nếu người quản trị đã **xác định bằng migration inventory có kiểm chứng** rằng một nhóm bản ghi là bcrypt raw hợp lệ (ví dụ chuỗi compact dạng `$2a$...`), có thể thêm tiền tố `{bcrypt}` khi lưu **mà không biết plaintext**:

~~~java
// Chỉ chạy trong migration có validation, backup và kiểm ownership.
String updated = "{bcrypt}" + verifiedLegacyRawBcryptHash;
~~~

Sau đó với `DelegatingPasswordEncoder`:

~~~java
boolean accepted = delegating.matches(
        userEnteredRawPassword,
        "{bcrypt}" + verifiedLegacyRawBcryptHash);
~~~

Điều kiện bảo đảm:

1. Xác nhận hash thuộc bcrypt, không chỉ dùng một ký tự đầu hoặc đoán từ email.
2. Kiểm tra hash nguyên vẹn, độ dài và format trước migration.
3. Không đổi prefix của bản ghi đã có `{id}`.
4. Lưu cả chuỗi `{bcrypt}...` trong cột đủ dài, không cắt vì `VARCHAR(60)`.
5. Thực hiện **transaction/backup**, thống kê số bản ghi và có kế hoạch rollback.
6. Tại production không log toàn bộ hash hoặc giá trị raw password.
7. Kiểm thử sample data giả và xác minh đăng nhập sau migration bằng quy trình an toàn.
8. Không thêm prefix cho bản ghi mà format **không thể xác định**; cần password reset hoặc adapter legacy được kiểm định.

**Không** sửa bằng cách gắn `{noop}` trước bcrypt hash: điều đó làm `NoOpPasswordEncoder` so password nhập với chuỗi hash literal và là cấu hình không an toàn.

### 3.2. Trường hợp ID đã có nhưng không được map

Nếu stored value là `{pbkdf2@SpringSecurity_v5_8}...` nhưng ứng dụng chỉ cấu hình map `bcrypt`, lỗi là **unknown/unmapped ID** dù prefix hợp lệ. Cần bổ sung encoder tương ứng **nếu ứng dụng đã từng lưu format đó**. Không làm fallback “thử mọi hash” trên mọi tài khoản, không silently allow khi không hiểu format.

Ví dụ cấu hình chỉ hỗ trợ hai format đã được phê duyệt:

~~~java
Map<String, PasswordEncoder> encoders = new HashMap<>();
encoders.put("bcrypt", new BCryptPasswordEncoder());
encoders.put("pbkdf2@SpringSecurity_v5_8",
        Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8());

PasswordEncoder delegating =
        new DelegatingPasswordEncoder("pbkdf2@SpringSecurity_v5_8", encoders);
~~~

Đoạn trên là **snippet trong một bean method**, cần imports `java.util.Map`, `java.util.HashMap` và `org.springframework.security.crypto.password.*`. Nó tạo hash mới có tiền tố PBKDF2 phiên bản 5.8, đồng thời **verify bcrypt prefixed**. Dữ liệu raw bcrypt chưa có prefix **vẫn chưa được xử lý**: cần migrate hoặc một chiến lược legacy chặt chẽ riêng.

### 3.3. Tại sao setDefaultPasswordEncoderForMatches không phải nút sửa chung?

`DelegatingPasswordEncoder#setDefaultPasswordEncoderForMatches(PasswordEncoder)` cho phép dùng encoder thay thế khi stored ID không được map. Nhưng Javadoc cảnh báo: **đối số encodedPassword đưa vào fallback là TOÀN BỘ giá trị lưu, kể cả prefix không nhận biết**.

Nếu đặt fallback là `BCryptPasswordEncoder` mà gặp `{unknown}$2a$...`, nó không tự cắt `{unknown}`. Nếu đặt fallback `NoOpPasswordEncoder` hoặc một encoder quá dễ dãi, có thể tạo hành vi **không an toàn**. Vì vậy:

- Không dùng fallback “chấp nhận mọi password” hay `NoOpPasswordEncoder`.
- Không tự gỡ prefix lạ rồi thử toàn bộ thuật toán.
- Không để fallback chung tồn tại vĩnh viễn mà không có metrics và thời hạn migration.
- Ưu tiên inventory định dạng hash, lưu metadata đúng và backfill/migration có điều kiện.

## 4. Phân biệt exception, false và lỗi authentication khác

| Hiện tượng | Thường biểu thị | Bước điều tra đầu tiên |
| --- | --- | --- |
| `There is no PasswordEncoder mapped for the id "null"` | Stored hash thiếu `{id}` hoặc format không đúng | Kiểm loại hash và nguồn DB, không kiểm lại bằng password plaintext qua log |
| `There is no PasswordEncoder mapped for the id "..."` | ID lưu không được đăng ký trong encoder map | So cấu hình map và prefix đã lưu, kiểm có typo/case/version |
| `matches(raw, encoded) == false` | Mật khẩu khác, hash bị hỏng, encoder/parameters không khớp, raw bị biến đổi | Test với fixture kiểm soát, tra lịch sử migration/storage |
| BCrypt warning “Encoded password does not look like BCrypt” | Chuỗi sau prefix không đúng format BCrypt, bị truncate hoặc truyền sai kiểu | Kiểm metadata cột và prefix/encoded tail |
| `BadCredentialsException` | Provider không chấp nhận credentials; có thể che user-not-found | Phân biệt user load/encoder bằng log category an toàn |
| `UsernameNotFoundException` | UserDetailsService không tìm thấy user | Kiểm username normalization, tenant, repository, cache; không leak existence |
| `DisabledException` / `LockedException` / `AccountExpiredException` | Account không được phép đăng nhập | Kiểm account flags, không reset hash bừa |
| `CredentialsExpiredException` | Credential bị đánh dấu hết hạn | Kiểm expiration/password change flow |
| POST form login trả 403 | Có thể CSRF thiếu/sai | Kiểm CsrfFilter, chưa nên đụng password encoder |
| GET protected trả 403 sau login | Có thể thiếu role/authority | Kiểm authorization, không phải hash |
| Basic trả 401 | Sai credentials, account state, cấu hình provider hoặc entry point | So flow Basic với form login trong test |
| Form trả 302 `/login?error` | Failure handler đã chạy | Xem audit category đã sanitize; không kết luận thuật toán từ status |
| Mỗi lần restart user không login được | User store in-memory, salt/secret tham số mất ổn định, DB trỏ nhầm môi trường | Kiểm Datasource, deployment env, encoder parameters, migration |
| Chỉ một số user fail sau deploy | Nhóm hash legacy/mixed IDs, truncate hoặc encoding khác nhau theo thời điểm | Phân loại record theo metadata, không đọc giá trị full |
| Password đúng nhưng login mới vẫn bị chặn | MFA, account lock, session policy, compromised-password checker | Kiểm từng lớp xác thực và policy theo đúng request |

**Điểm bảo mật:** phản hồi công khai của hệ thống thường nên chung (“Thông tin đăng nhập không hợp lệ”) để tránh user enumeration. Bên trong audit có thể phân loại `ENCODER_ID_MISSING`, `ENCODER_ID_UNSUPPORTED`, `STORED_HASH_MALFORMED`, `ACCOUNT_DISABLED`, `CSRF_REJECTED`... nhưng chỉ dùng các giá trị đã whitelist, không đặt raw username/password/hash vào log.

## 5. Cây chẩn đoán có kiểm chứng, không sửa bừa database

~~~text
User: "Mật khẩu chắc chắn đúng nhưng đăng nhập lỗi"
       │
       ▼
1. Request có tới AuthenticationProvider không?
       ├─ Không: CSRF, filter-chain match, URL, HTTP method,
       │          session, reverse proxy, authorization
       └─ Có
           │
           ▼
2. UserDetailsService có nạp đúng account và password hash?
       ├─ Không: username/tenant/email lookup, DB, cache, locked
       └─ Có
           │
           ▼
3. Stored encoded value có {id} hợp lệ không?
       ├─ Không: inventory legacy format / missing prefix
       ├─ ID unknown: cấu hình Delegating map khác dữ liệu
       └─ Có
           │
           ▼
4. encoded tail có nguyên vẹn, đúng format/length không?
       ├─ Không: VARCHAR/CHAR, truncation, migration, encoding
       └─ Có
           │
           ▼
5. Password raw có đi qua phép biến đổi nào không?
       ├─ Có: trim, lowercase, NFC/NFD, charset, Base64,
       │       double-encoding, form/client transforms
       └─ Không
           │
           ▼
6. Encoder params/secret/version có giống lúc lưu?
       ├─ Không: PBKDF2 secret/iterations, Argon2/scrypt params
       │         hoặc custom encoder thay đổi
       └─ Có
           │
           ▼
7. matches() trả gì trên fixture thử nghiệm?
       ├─ Throws: format/mapper/implementation exception
       ├─ False: hash không khớp raw theo pipeline hiện tại
       └─ True: quay lại account flags, provider, MFA,
                authorization, session, response handling
~~~

Đối với một người dùng cụ thể, **không yêu cầu hoặc trích xuất mật khẩu thật** để test theo cây này. Thay vào đó dùng fixture account chuyên dụng, logs có mã category và metadata hash không nhạy cảm; nếu cần cứu account không thể xác định hash, cung cấp reset password an toàn.

### 5.1. Phải biết DB đang lưu gì mà không lộ bí mật

Nên ghi nhận metadata ở môi trường có quyền:

- Nguồn user table/repository **đúng tenant** (không trả thông tin này cho người dùng).
- Prefix algorithm ID đã cho phép, ví dụ `bcrypt` hoặc `pbkdf2@SpringSecurity_v5_8`.
- Độ dài chuỗi hash đã lưu (code units/characters/bytes tùy DB).
- Có hay không dấu hiệu hash bị cắt, dấu cách cuối do CHAR padding.
- Hash được cập nhật khi nào, từ phiên bản ứng dụng/encoder nào.
- `PasswordEncoder`/`AuthenticationProvider` thực sự dùng ở request đó.
- Trạng thái user `enabled/accountNonLocked/credentialsNonExpired`.
- Các thay đổi gần đây của serializer, ORM, database migration, policy Unicode.

**Không** lấy prefix bằng cách log toàn bộ 60 ký tự bcrypt; cũng không lưu/reveal SHA-256 của password để “so sánh”. Khi báo lỗi cần một correlation ID ngẫu nhiên do server sinh, không dùng session ID/token/raw credential.

### 5.2. Query có thể cho biết lỗi độ dài mà không in hash

Một câu SQL **ví dụ PostgreSQL**, cần điều chỉnh đúng tên bảng/cột trong schema của dự án:

~~~sql
-- Chỉ thống kê tổng số bản ghi theo độ dài.
-- Không SELECT password_hash và không export user_id cá nhân.
SELECT char_length(password_hash) AS stored_chars, count(*) AS users
FROM app_users
WHERE password_hash IS NOT NULL
GROUP BY char_length(password_hash)
ORDER BY stored_chars;
~~~

Kết quả có thể chia nhóm 60, 68 hoặc các độ dài PBKDF2/Argon2 khác. **Độ dài không đủ để khẳng định format hợp lệ**; thống kê chỉ giúp phát hiện số đông bị cắt. Không cần và không nên đưa số liệu người dùng thực vào bài/ticket nếu không được phép.

Nếu cột `VARCHAR(60)`, một bcrypt raw hash có thể vừa; nhưng `{bcrypt}` + bcrypt dài 68 ký tự sẽ **không vừa**. Tùy DB, insert có thể bị từ chối hoặc bị cắt/biến đổi do code/migration. Cột `VARCHAR(255)` thường là điểm khởi đầu cho nhiều format hash, nhưng **phải kiểm kích thước tối đa thực tế** của các encoder được dùng; không xem 255 là đảm bảo cho mọi tương lai.

### 5.3. CHAR padding, trimming và kiểu lưu

- Cột `CHAR(n)` có thể tự pad spaces, làm chuỗi nhận lại khác giá trị đã encode.
- Mapper/JPA converter có thể `trim()`/`strip()` hoặc thay `null` thành `""`.
- Serializer có thể loại dấu `{...}`, escape JSON hoặc thay encoding.
- Password hash là chuỗi có ký tự đặc biệt `$`, `{`, `}`, `/`, `+`, `=` tùy thuật toán; không được escape/URL-decode hai lần khi lưu.
- Dùng `String`/VARCHAR phù hợp thay vì chuyển một digest binary thành string tùy ý bằng charset nền tảng.
- Nếu lưu dạng `VARBINARY`, phải biết chính xác đã encode Base64/hex trước hay sau khi hash; **không** lấy bytes chưa rõ format rồi gọi `new String(bytes)` mặc định.

Không tự “sửa” bằng cách `trim()` toàn bộ dữ liệu trong bảng. Việc mất/đổi bất kỳ byte hash nào có thể làm xác minh thất bại; cần xác định format và có migration/backup riêng.

## 6. Những lỗi dữ liệu rất thực tế

### 6.1. Lúc tạo user dùng BCrypt nhưng lúc login dùng Delegating

~~~text
Registration:
  BCryptPasswordEncoder.encode(raw)
  → "$2a$10$..." (không {id})

Login sau khi refactor:
  PasswordEncoderFactories.createDelegatingPasswordEncoder()
  → matches(raw, "$2a$10$...")
  → không tìm được id → lỗi
~~~

Khắc phục: xác minh toàn bộ legacy rows thực sự là bcrypt rồi backfill `{bcrypt}`, hoặc dùng compatibility adapter có phạm vi/timeout chặt. **Không chuyển sang `NoOpPasswordEncoder`.**

### 6.2. Lúc tạo user dùng Delegating nhưng lúc login dùng BCrypt trực tiếp

~~~text
Registration:
  DelegatingPasswordEncoder.encode(raw)
  → "{bcrypt}$2a$10$..."

Login:
  new BCryptPasswordEncoder().matches(raw, "{bcrypt}$2a$10$...")
  → phần hash không có dạng bcrypt compact ở vị trí đầu
~~~

Khắc phục: dùng Delegating cho stored format có prefix hoặc migrate đúng cách. **Không tạo một bean BCrypt mới chỉ vì nhìn thấy `$2a$` trong hash** nếu stored value có `{bcrypt}`.

### 6.3. Lưu hash hai lần

~~~text
rawPassword
   │
   └─ encode(...) → {bcrypt}$2a$...
                          │
                          └─ encode(...) lần nữa → {bcrypt}$2a$...
                                        (hash của chuỗi hash lần 1)
~~~

Nếu login dùng `matches(rawPassword, hash2)`, sẽ thất bại. Nguyên nhân thường là controller encode trước rồi `UserService.saveNewPassword(...)` lại encode hoặc database callback/mapper encode thêm. Nên quy định **một tầng chịu trách nhiệm hash**, nhận raw password ở đúng chỗ và chỉ lưu encoded once.

**Không thể khôi phục raw password từ hash2**. Nếu không còn cách xác thực hợp lệ, dùng password reset thay vì cố “decode hash”.

### 6.4. Lưu sai cột/trả sai giá trị UserDetails.getPassword()

Một entity có nhiều trường:

~~~text
users.password_hash
users.previous_password_hash
users.password_reset_hash
users.temporary_hash
~~~

`UserDetailsService` có thể vô tình trả `previous_password_hash` hoặc `password_reset_hash`; hoặc query sai tenant/account. Password “đúng với hiện tại” vẫn không khớp. Kiểm migration/mapper/projection và cập nhật cache; **không** cho phép login bằng reset token hash.

### 6.5. Thay PBKDF2/SCrypt/Argon2 parameters mà không giữ metadata

PBKDF2 có hash function, salt length, iterations và có thể secret/pepper ngoài DB. SCrypt/Argon2 có memory/iteration/parallelism/cấu trúc output. Nếu custom encoder hoặc cấu hình khác phiên bản **không còn biết thông số dùng để hash ban đầu**, cùng raw password cũng có thể không xác minh được.

Vì vậy mỗi hash cần tự mô tả hoặc có **version/ID mapping ổn định**. Spring đã hỗ trợ IDs như `pbkdf2@SpringSecurity_v5_8` và `argon2@SpringSecurity_v5_8` để phân biệt bộ tham số. Không xóa prefix/tự chuyển tất cả thành `{pbkdf2}` chỉ vì thay phiên bản Spring.

Với encoder dùng **pepper/secret** ngoài DB, nếu secret mất hoặc chuyển sai qua environment khi deploy, tất cả hash tương ứng có thể không match. Phải quản lý key version, backup và kế hoạch rotation; không log secret.

### 6.6. Biến đổi password trước khi encode/matches

Các lỗi thường gặp:

~~~java
// SAI nếu đăng ký không áp cùng quy tắc:
String toCheck = rawPassword.trim().toLowerCase();
encoder.matches(toCheck, storedHash);
~~~

- Form/frontend có thể tự xóa trailing space, đổi kiểu Unicode hoặc sửa chữ hoa/chữ thường.
- Password mới khi đăng ký áp `Normalizer.Form.NFC` nhưng login không áp, hoặc ngược lại.
- JSON UTF-8 chuyển sai charset khiến ký tự tiếng Việt bị thay.
- Một service encode password raw; service khác Base64-encode trước khi hash.
- Password manager điền ký tự khoảng trắng/ngắt dòng và ứng dụng không minh bạch.
- BCrypt legacy có giới hạn input bytes; một hệ thống đã từng cắt password dài có thể có semantics khác sau khi cập nhật.

Khi đổi policy Unicode, **không áp ngược tùy ý cho mọi tài khoản cũ**. Cần versioned pipeline/migration: nếu hash cũ được tạo từ raw không chuẩn hóa, áp NFC trước matches có thể làm mất khả năng login; hãy test account giả với ký tự tổ hợp và thiết kế bước chuyển đổi an toàn.

## 7. Chương trình Java 17 độc lập: phân loại hình dạng hash, không xác minh password

Đây là công cụ minh họa **chỉ dựa trên chuỗi thử nghiệm giả**, không dùng credential thật và không làm lộ hash. Nó phát hiện sự khác biệt giữa bcrypt raw và bcrypt có `{bcrypt}`, nhưng **không khẳng định chuỗi là hash hợp lệ**. Một chuỗi có đúng độ dài vẫn có thể sai salt/checksum.

Tệp `HashShapeInspector.java`:

~~~java
public class HashShapeInspector {

    static String classify(String stored) {
        if (stored == null || stored.isBlank()) {
            return "EMPTY";
        }
        if (stored.startsWith("{bcrypt}$2") && stored.length() == 68) {
            return "PREFIXED_BCRYPT_SHAPE";
        }
        if (stored.startsWith("$2") && stored.length() == 60) {
            return "RAW_BCRYPT_SHAPE";
        }
        if (stored.startsWith("{")) {
            return "PREFIXED_OTHER_OR_MALFORMED";
        }
        return "UNKNOWN_NO_PREFIX";
    }

    public static void main(String[] args) {
        // Chỉ là dữ liệu hình dạng GIẢ; không phải BCrypt hash hợp lệ.
        String fakeRaw = "$2a$10$" + "x".repeat(53);

        System.out.println(classify("{bcrypt}" + fakeRaw));
        System.out.println(classify(fakeRaw));
        System.out.println(classify("{argon2}fixture"));
        System.out.println(classify(""));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**, không cần Spring:

~~~bash
javac --release 17 HashShapeInspector.java
java HashShapeInspector
~~~

**Stdout chính xác:**

~~~text
PREFIXED_BCRYPT_SHAPE
RAW_BCRYPT_SHAPE
PREFIXED_OTHER_OR_MALFORMED
EMPTY
~~~

Lý do: `"$2a$10$"` dài 7 ký tự, `"x".repeat(53)` tạo 60; thêm `"{bcrypt}"` dài 8 tạo 68. Hàm chỉ kiểm prefix/length, **không thay thế `PasswordEncoder.matches` hoặc kiểm integrity dữ liệu thật**. Không copy `HashShapeInspector` để in hoặc export toàn bộ hash thật ra console.

## 8. Spring Boot 3.5 / Spring Security 6.5: ví dụ đầy đủ dùng cùng một encoder

Ví dụ này dựng một application Servlet nhỏ có:

- Một `PasswordEncoder` bean thống nhất: `PasswordEncoderFactories.createDelegatingPasswordEncoder()`.
- Một `UserDetailsService` in-memory chứa user lab; hash được encode **một lần** khi khởi tạo.
- Form login và HTTP Basic để minh họa hai loại request đi qua provider.
- Endpoint protected `GET /api/me` để xác minh account đã authenticated.
- JUnit tests chỉ ra missing-prefix, wrong-password, double-encoding và truncated hash.

**Không phải ứng dụng account production:** password trong example là credential **giả chỉ dùng local/test**, không có database, reset/MFA/rate limit. Dùng HTTPS và secrets manager trong sản phẩm thật. Không dùng tài khoản lab và password dưới đây ở môi trường Internet.

### 8.1. Dependencies Gradle

Trong `build.gradle` của một project **Spring Boot 3.5.x**, Java 17+ và Boot BOM đã quản lý version:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Không dùng `spring-security-crypto` version khác Spring Security runtime. Nếu có nhiều dependency tự ghi version, kiểm `./gradlew dependencyInsight` theo module liên quan để tránh module 6.3/6.5 bị trộn.

### 8.2. Cấu hình ứng dụng

Tệp `src/main/java/example/encdiag/PasswordDiagnosticsApplication.java`:

~~~java
package example.encdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordDiagnosticsApplication.class, args);
    }
}
~~~

Tệp `src/main/java/example/encdiag/PasswordSecurityConfig.java`:

~~~java
package example.encdiag;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class PasswordSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // Mọi lần đăng ký/đổi password cũng phải dùng encoder này.
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService labUserDetails(PasswordEncoder encoder) {
        // Chỉ data lab; encode đúng một lần trước khi lưu.
        String encoded = encoder.encode("lab-only-correct-password-2026");

        UserDetails user = User.withUsername("student")
                .password(encoded)
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated());

        http.formLogin(Customizer.withDefaults());
        http.httpBasic(Customizer.withDefaults());

        // Không tắt CSRF cho form login; Basic dùng HTTPS trong thực tế.
        return http.build();
    }
}
~~~

Tệp `src/main/java/example/encdiag/WhoAmIController.java`:

~~~java
package example.encdiag;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return "me:" + authentication.getName();
    }
}
~~~

Khi startup, user `student` có hash được tạo bởi **DelegatingPasswordEncoder**; chuỗi sẽ bắt đầu `{bcrypt}`, nhưng phần bcrypt phía sau **khác theo từng lần chạy** vì salt. Không hard-code một hash mẫu cố định làm expected stdout.

### 8.3. Chạy và thử với HTTP Basic

Chạy bằng Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows: `gradlew.bat bootRun`. Gọi endpoint public:

~~~bash
curl -i http://localhost:8080/public
~~~

Body:

~~~text
public
~~~

Với Basic credentials **lab**:

~~~bash
curl -i -u student:lab-only-correct-password-2026 \
  -H "Accept: application/json" \
  http://localhost:8080/api/me
~~~

Response thành công có body:

~~~text
me:student
~~~

Nếu password sai, Basic thường trả HTTP **401**; nếu dùng form login tại `/login`, sai password thường chuyển tới `/login?error`. **Không** log header `Authorization: Basic ...`: Base64 có thể giải mã thành username/password. Chỉ chạy các command chứa password giả này tại localhost, không dùng secret thật trong shell history.

## 9. JUnit: phân biệt thiếu ID, đúng encoder, hash bị cắt và hash hai lần

Tệp `src/test/java/example/encdiag/PasswordEncodingDiagnosisTest.java`:

~~~java
package example.encdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordEncodingDiagnosisTest {

    private static final String RAW =
            "synthetic-password-for-tests-2026";

    @Autowired
    MockMvc mvc;

    @Autowired
    PasswordEncoder appEncoder;

    @Test
    void delegatedBcryptHashContainsIdAndMatches() {
        String encoded = appEncoder.encode(RAW);
        assertTrue(encoded.startsWith("{bcrypt}"));
        assertTrue(appEncoder.matches(RAW, encoded));
        assertFalse(appEncoder.matches("wrong-password", encoded));
    }

    @Test
    void legacyRawBcryptNeedsFormatMigration() {
        BCryptPasswordEncoder legacy = new BCryptPasswordEncoder();
        String oldHash = legacy.encode(RAW);
        assertEquals(60, oldHash.length());
        assertTrue(legacy.matches(RAW, oldHash));

        PasswordEncoder delegated =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        // Delegating mặc định không tìm được {id}.
        assertThrows(IllegalArgumentException.class,
                () -> delegated.matches(RAW, oldHash));

        // Sau khi đã xác định oldHash là bcrypt hợp lệ,
        // thêm đúng metadata {bcrypt} vào dữ liệu thử nghiệm.
        assertTrue(delegated.matches(RAW, "{bcrypt}" + oldHash));
    }

    @Test
    void truncatedBcryptHashDoesNotVerify() {
        String full = appEncoder.encode(RAW);
        String truncated = full.substring(0, full.length() - 4);

        // Không làm điều này với hash production; test chỉ dùng fake.
        assertFalse(appEncoder.matches(RAW, truncated));
    }

    @Test
    void doubleEncodingIsNotTheSameAsEncodingRawOnce() {
        String once = appEncoder.encode(RAW);
        String twice = appEncoder.encode(once);

        assertTrue(appEncoder.matches(RAW, once));
        assertFalse(appEncoder.matches(RAW, twice));
        assertTrue(appEncoder.matches(once, twice));
    }

    @Test
    void pbkdf2VersionedIdMustMapToMatchingEncoder() {
        var pbkdf2 = Pbkdf2PasswordEncoder
                .defaultsForSpringSecurity_v5_8();

        String pbkdf2Hash = pbkdf2.encode(RAW);
        PasswordEncoder delegated =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        assertTrue(delegated.matches(
                RAW, "{pbkdf2@SpringSecurity_v5_8}" + pbkdf2Hash));
    }

    @Test
    void correctPasswordAuthenticatesWithHttpBasic()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic(
                        "student", "lab-only-correct-password-2026"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("student"))
            .andExpect(content().string("me:student"));
    }

    @Test
    void wrongPasswordFailsHttpBasic()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "incorrect"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void sameHashWorksForFormLogin() throws Exception {
        mvc.perform(formLogin()
                .user("student")
                .password("lab-only-correct-password-2026"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("student"));
    }
}
~~~

Có **8 test methods**: năm phép kiểm `PasswordEncoder` cục bộ và ba phép thử HTTP qua `SecurityFilterChain`. Khi project đủ dependencies/phiên bản, kết quả dự kiến là tất cả pass; không khẳng định đã chạy Gradle trong môi trường khác.

Chạy test:

~~~bash
./gradlew test --tests example.encdiag.PasswordEncodingDiagnosisTest
~~~

**Test nào chứng minh điều gì?**

| Method | Khẳng định được | Không khẳng định được |
| --- | --- | --- |
| `delegatedBcryptHashContainsIdAndMatches` | Bean hiện tại tạo `{bcrypt}` và verify chính hash ấy | Hash đã lưu trong DB thật không bị cắt |
| `legacyRawBcryptNeedsFormatMigration` | Raw BCrypt thiếu prefix gây lỗi khi dùng Delegating; prefix đúng khôi phục verify | Mọi raw record production đều là BCrypt |
| `truncatedBcryptHashDoesNotVerify` | Bỏ 4 ký tự cuối làm hash thử nghiệm không còn match | DB của bạn thực sự bị truncation |
| `doubleEncodingIsNotTheSameAsEncodingRawOnce` | Hash hai lần làm raw không verify như hash một lần | Phần mềm thật đã encode hai lần |
| `pbkdf2VersionedIdMustMapToMatchingEncoder` | Factory nhận ID versioned của PBKDF2 | Tham số custom PBKDF2 ở hệ thống thật giống default |
| `correctPasswordAuthenticatesWithHttpBasic` | Provider/encoder + user store demo dùng được qua Basic | Form, session và DB production đúng |
| `wrongPasswordFailsHttpBasic` | Negative Basic credential test | Mọi lỗi Basic đều là sai mật khẩu |
| `sameHashWorksForFormLogin` | Form login demo xác minh hash thành công qua filter | Cookie/redirect ở browser thật được xử lý đúng |

### 9.1. Tại sao không tạo endpoint GET /debug/hash?

Một số cách điều tra lỗi tiện nhưng nguy hiểm:

~~~java
// SAI: không đưa hash ra endpoint dù chỉ nghĩ là nội bộ.
@GetMapping("/debug/hash")
String getHash() {
    return userDetailsService.loadUserByUsername("student")
            .getPassword();
}
~~~

Dù hash không phải plaintext, nó có thể bị tấn công offline và chứa metadata về thuật toán/cost. Debug account phải qua kênh bảo mật, có dữ liệu giả trong test, không xuất hash vào response/log hoặc ticket. Nếu cần so sánh bảng dữ liệu thật, dùng báo cáo **tổng hợp** chỉ trả số lượng/độ dài/ID algorithm và truy cập có kiểm soát.

### 9.2. Test lỗi hash thật mà không cần mật khẩu của người dùng

Một cách thực tế trong môi trường staging:

1. Tạo **account canary** với password giả chỉ dành cho test.
2. Đăng ký qua đường HTTP/Service thật, không tạo hash trực tiếp trong test bỏ qua DAO.
3. Đọc metadata (algorithm ID/length) từ DB **không in hash**.
4. Xác minh login qua form/Basic với password canary đã biết.
5. Restart app, thử login lại với cùng DB; xác minh persistence.
6. Đổi work factor hoặc deploy phiên bản code mô phỏng migration; kiểm backward compatibility.
7. Gây lỗi có kiểm soát ở một bản ghi canary (bỏ prefix/truncate) rồi khôi phục fixture, kiểm test fail đúng nguyên nhân.
8. Đảm bảo log/trace không chứa raw password, hash hoặc full credential.

**Đừng sửa hoặc “phá” bản ghi của người dùng thật để thử.** Mọi negative test cần fixture và database cách ly; copy DB production có hash/PII vào local test là rủi ro nghiêm trọng.

## 10. Migrate an toàn từ hash cũ sang DelegatingPasswordEncoder

Có ba nhóm dữ liệu khác nhau:

| Nhóm dữ liệu | Chiến lược |
| --- | --- |
| Hash hiện đại **đã có ID đúng** | Giữ nguyên, bảo đảm map tương ứng; lên kế hoạch rehash khi login thành công nếu cần |
| Raw bcrypt không prefix **được xác nhận hợp lệ** | Migration metadata `{bcrypt}` có kiểm chứng, không cần plaintext; kiểm column capacity |
| Hash không xác định/corrupt/mất pepper | Không tự đặt tiền tố; cần legacy adapter đã kiểm định hoặc password reset an toàn |

### 10.1. Pha inventory (chỉ đọc)

1. Thống kê theo độ dài và dạng prefix **mà không export full hash**.
2. So version Spring và cấu hình encoder đã từng được dùng trong từng giai đoạn.
3. Kiểm DB schema, persistence mapping, collation, password column, ORM converters.
4. Xác định account nào sẽ bị ảnh hưởng và phương án notification/recovery.
5. Kiểm có nguồn dữ liệu legacy khác: LDAP, JDBC, custom SSO, password reset service, mobile API.
6. Chuẩn bị phương án rollback và xác nhận không ai đang ghi hash đồng thời ngoài migration.

### 10.2. Pha migrate có kiểm soát

Với một bản ghi **đã xác minh là raw bcrypt**:

~~~text
before = "$2a$10$..."        (60 chars)
after  = "{bcrypt}$2a$10$..." (68 chars)
~~~

Đây là **thêm metadata**, không phải giải mã/re-hash. Phải có database transaction, backup, condition chỉ chọn đúng các record, kiểm số lượng và verify canary. **Không áp dụng một câu UPDATE cho mọi row có password_hash không rỗng**, vì trong hệ thống mixed-format sẽ làm hỏng các user dùng PBKDF2/Argon2.

Nếu hash là legacy PBKDF2 custom có secret/cost/salt khác mặc định, việc thêm `{pbkdf2@SpringSecurity_v5_8}` **chỉ vì tên PBKDF2** không bảo đảm verify được; phải có adapter cho đúng parameters.

### 10.3. Pha online rehash để chuyển thuật toán/cost

Khi người dùng login thành công, ứng dụng đang có raw password trong RAM của **request hiện tại**. Có thể dùng cơ chế `PasswordEncoder.upgradeEncoding(encodedPassword)` cùng `UserDetailsPasswordService` của Spring Security để cập nhật hash theo chính sách mới.

Javadoc Spring Security 6.5 có:

- `PasswordEncoder.upgradeEncoding(String encodedPassword)`: hỏi encoder xem hash cần nâng cấp không.
- `UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)`: cập nhật encoded password cho user.
- `DaoAuthenticationProvider#setUserDetailsPasswordService(UserDetailsPasswordService)`: gắn service để provider có khả năng nâng cấp password hash sau authentication thành công theo implementation.

Tuy nhiên **không** có nghĩa cứ tạo bean `PasswordEncoder` mới là tất cả user tự đổi hash. Cần:

1. `DaoAuthenticationProvider` thực sự sử dụng đúng encoder và password service.
2. Password service có thể ghi DB theo **đúng account ID**, cùng transaction/optimistic version khi cần.
3. Tách khả năng verify hash cũ khỏi thuật toán encode mới.
4. Chỉ rehash sau khi password được xác minh, không dựa vào email/account ID từ client.
5. Bảo vệ concurrency để login đồng thời không ghi đè password change mới.
6. Không log raw password/hash; audit chỉ ghi event code `PASSWORD_HASH_UPGRADED` và algorithm version (khi policy cho phép).

**Nếu password không verify được**, không thể dùng online rehash để “phỏng đoán” raw password; phải sửa format metadata đúng (nếu có thể) hoặc cho người dùng reset.

### 10.4. Làm gì với mã hash “không biết thuật toán”?

Không thử mọi encoder và nhận kết quả đầu tiên `true` một cách tùy tiện, vì điều đó tạo bề mặt kiểm tra ngoài kiểm soát. Không chuyển sang NoOp/không hash để “hết lỗi”. Quy trình an toàn:

- Đánh dấu loại record `LEGACY_UNKNOWN`.
- Đánh giá lịch sử source/version/migration và xác minh sample với dữ liệu canary.
- Nếu xác định được thuật toán/tham số, viết adapter có unit tests.
- Nếu không, yêu cầu reset password bằng token ngẫu nhiên một lần với kiểm tra identity phù hợp.
- Theo dõi tỷ lệ chuyển đổi và gỡ compatibility code sau khi migration hoàn tất.

## 11. Tham số BCrypt và cảnh báo input dài

BCrypt là thuật toán password hashing có chi phí điều chỉnh được. `BCryptPasswordEncoder` lưu salt/cost trong hash compact; đổi strength ở lần encode mới **không nhất thiết** làm hash cũ mất khả năng verify. Vì vậy khi một user bcrypt fail sau deploy, **đừng vội đổ lỗi do thay cost từ 10 sang 12**: hãy kiểm prefix, hash integrity, provider wiring và password transformation.

### 11.1. Giới hạn input dài và CVE-2025-22228

BCrypt có giới hạn xử lý input truyền thống; trong Java/Spring có các behavior theo phiên bản. Spring công bố **CVE-2025-22228** vào **19/03/2025**: một số phiên bản `BCryptPasswordEncoder.matches` cũ không áp trần độ dài đúng cách, có thể cho phép các password có cùng phần đầu được coi là trùng.

Các phiên bản bị ảnh hưởng do advisory nêu gồm Spring Security 6.4.0–6.4.3, 6.3.0–6.3.7 và một số nhánh cũ; bản sửa open-source gồm **6.4.4 và 6.3.8**. Với 6.5, không áp dụng suy luận rằng bản 6.5 mặc định mắc CVE đó; luôn kiểm advisory và dependency tree thực tế.

Điểm cần nhớ cho chẩn đoán:

- Dài hơn ngưỡng xử lý/byte của thuật toán có thể gây behavior khác nhau giữa thư viện/phiên bản.
- Unicode một ký tự có thể chiếm nhiều UTF-8 bytes.
- Không truncate password thủ công trước khi hash/verify.
- Nếu policy cho phép passphrase dài, chọn encoder/config phù hợp và test cả boundary/surrogate pairs, không chỉ `String.length()`.
- Khi nâng Spring Security, cần kiểm các test login cho password dài để phát hiện thay đổi semantics và rủi ro legacy.
- Thay vì hạ thấp kiểm tra để “login được”, tuân thủ bản vá và thiết kế password reset/migration an toàn.

Tham khảo advisory chính thức ở cuối bài; không dùng các chuỗi “72 ký tự” và “72 bytes” thay thế tùy tiện, vì charset/implementation ảnh hưởng behavior.

## 12. Trường hợp password đúng nhưng lỗi không liên quan encoder

### 12.1. Account flags

`UserDetails` có:

~~~java
boolean enabled = user.isEnabled();
boolean notLocked = user.isAccountNonLocked();
boolean credentialsValid = user.isCredentialsNonExpired();
boolean accountValid = user.isAccountNonExpired();
~~~

Snippet nằm trong method có biến `UserDetails user`. Nếu một trong các điều kiện bắt buộc sai, provider có thể từ chối login dù `PasswordEncoder.matches` sẽ trả true. Hãy phân biệt lý do nội bộ và chỉ dùng thông báo chung cho client chưa xác thực.

### 12.2. Nạp sai tài khoản do username/tenant

Một ứng dụng nhiều tenant có thể dùng `username` không duy nhất toàn cục. Nếu `UserDetailsService.loadUserByUsername` bỏ tenant policy hoặc tìm account dựa trên email case-insensitive không nhất quán, provider tải **hash của người khác**. Kiểm khóa nội bộ/canonical username, tenant-scoped lookup và DB unique constraints; không “sửa” bằng cách đổi encoder.

### 12.3. Security filter chain khác nhau

App có thể có:

- `/login` qua form login.
- `/api/**` qua Basic hoặc Bearer.
- Admin endpoint qua SSO.
- Multiple `AuthenticationManager` và `DaoAuthenticationProvider`.

Một test chỉ gọi `PasswordEncoder.matches` thành công **không chứng minh** request HTTP đang đi qua đúng provider/encoder. Muốn debug, test với `MockMvc` và Security filters bật; xác minh behavior của endpoint thật, không dùng `@WithMockUser` vì helper này bỏ qua password check.

### 12.4. CSRF, authorization, MFA và sessions

Khi form trả 403 do thiếu CSRF, `DaoAuthenticationProvider` có thể chưa được gọi. Khi password được verify nhưng chưa MFA, application không nên cấp truy cập đầy đủ. Khi login thành công nhưng protected resource 403, nguyên nhân có thể là thiếu role. Khi response login redirect mà request sau trở lại /login, có thể do cookie/session/context persistence. Mỗi lỗi cần một bài test phù hợp; không thay hash của người dùng để xử lý sự cố session.

## 13. Ma trận kiểm thử xác minh chính xác loại lỗi

| ID | Scenario | Kết quả mong đợi |
| --- | --- | --- |
| D01 | Raw password đúng + hash `{bcrypt}` hợp lệ | `matches=true` |
| D02 | Raw password sai + hash `{bcrypt}` hợp lệ | `matches=false` |
| D03 | Raw bcrypt `$2a$...` không prefix với Delegating default | Lỗi thiếu `{id}` |
| D04 | Cùng raw bcrypt đã kiểm chứng, thêm `{bcrypt}` | Delegating verify được |
| D05 | Prefix `{unknown}` chưa map | Exception unmapped ID, không fallback NoOp |
| D06 | Prefix `{pbkdf2@SpringSecurity_v5_8}` đúng + dữ liệu PBKDF2 cùng config | Verify được |
| D07 | Prefix PBKDF2 gắn vào BCrypt tail | Từ chối/lỗi định dạng; không coi ID là thuật toán thật |
| D08 | Bcrypt hash bị cắt 4 ký tự | `matches=false` |
| D09 | DB cột `VARCHAR(60)`, app lưu `{bcrypt}` 68 ký tự | Bị chặn/truncated; migration phải mở rộng cột |
| D10 | `CHAR(n)` pad spaces hoặc mapper trim encoded hash | Phát hiện roundtrip khác trước/ sau DB |
| D11 | Password bị encode hai lần | Raw password không verify hash2 |
| D12 | Registration áp NFC, login không NFC | Test password có tổ hợp dấu cho kết quả không nhất quán |
| D13 | Raw password bị trim/casefold ở một đầu | Có thể mismatch, không sửa bằng cách trim bừa |
| D14 | UserDetailsService trả hash của tenant khác | Lỗi user mapping, không phải encoder |
| D15 | Account disabled/locked nhưng password match | Authentication bị từ chối bởi account flags |
| D16 | `POST /login` thiếu CSRF | 403 trước password check |
| D17 | Basic đúng password + hash đúng | HTTP 200 protected |
| D18 | Basic sai password | HTTP 401 (trong chain phù hợp) |
| D19 | Form đúng password | Redirect success, principal được xác thực |
| D20 | Test dùng `@WithMockUser` | Không được xem là kiểm chứng password |
| D21 | PBKDF2 pepper/iterations đổi không có version | Mismatch; cần adapter/version |
| D22 | BCrypt strength đổi nhưng hash cũ nguyên vẹn | Kiểm verify backward compatibility thay vì mặc định thất bại |
| D23 | Hash bị replace khi account đổi password đồng thời | Không ghi đè dữ liệu mới, dùng optimistic locking |
| D24 | Deploy lên node dùng config encoder khác node khác | Phát hiện inconsistent auth path |
| D25 | Cache chứa UserDetails cũ sau đổi mật khẩu | Login với mật khẩu mới có thể fail cho tới khi invalidation |
| D26 | Password reset cập nhật nhầm cột/không commit transaction | Hash không tương ứng request mới |
| D27 | Legacy hash không thể xác định | Chuyển password-reset flow, không set NoOp |
| D28 | Logs chứa raw password/hash từ test thất bại | QA FAIL, loại bỏ dữ liệu nhạy cảm |
| D29 | Nâng library qua bản vá BCrypt input dài | Kiểm boundary/password dài và tư vấn migration |
| D30 | Một test canary qua REST và cùng account qua form | Đúng behavior từng chain; không suy từ mỗi matches |

Mục tiêu không phải làm tất cả user login bằng mọi giá, mà là **định vị nguyên nhân chính xác rồi khôi phục tính đúng đắn mà không hạ bảo mật**.

## 14. Troubleshooting theo hiện tượng

| Hiện tượng | Bước kiểm | Hướng khắc phục |
| --- | --- | --- |
| `id "null"` sau deploy | Chuỗi hash cũ có bắt đầu `{id}` không? | Inventory; prefix-only migration cho format đã xác minh |
| `id "pbkdf2@SpringSecurity_v5_8"` unmapped | Map encoder phiên bản có tồn tại không? | Bổ sung chính xác mapping; kiểm dependency |
| `Encoded password does not look like BCrypt` | Tail có đúng bcrypt shape/độ dài sau prefix không? | Kiểm VARCHAR/CHAR, prefix đặt sai, double encoding |
| Password đúng nhưng `matches=false` ở canary | Có encode hai lần, normalize khác, hash bị cắt? | Test xuyên registration/DB/login; sửa pipeline |
| Tất cả user fail sau đổi bean | Có chuyển từ BCrypt sang Delegating hoặc ngược lại? | Khôi phục compatible config, migrate có kiểm chứng |
| Chỉ legacy users fail | Có mixed hash formats và thiếu ID? | Tách cohort, migration/upgrade từng nhóm |
| Chỉ Unicode password fail | Charset/normalization/trim khác ở hai đầu | Định nghĩa policy thống nhất và migration legacy |
| User đổi password xong vẫn vào bằng mật khẩu cũ | User store cache, transaction chưa commit, concurrent update | Kiểm invalidate cache/DB version và audit |
| User đổi password xong **không** vào được bằng mật khẩu mới | Hash cập nhật sai cột, encoder mismatch, mapper cắt | Trace canary qua service/repository, không log secret |
| Một replica login được, replica khác fail | Encoder secret/config/BOM/data source khác nhau | So config version, secrets, shared DB |
| Test `encoder.matches` pass nhưng form login fail | UserDetailsService/account state/provider chain khác | Test HTTP đúng path + filter chain |
| Password đúng nhưng POST login trả 403 | Thiếu CSRF, access denied | Kiểm CSRF và method |
| Password đúng nhưng API trả 403 sau login | Thiếu authority/role | Kiểm authorization, không reset hash |
| Lỗi biến mất khi dùng `{noop}` | Đang bypass hash security chứ không sửa cấu hình | Gỡ NoOp, làm migration/reset |
| Không thể giải mã hash về password cũ | Hash một chiều hoạt động như thiết kế | Reset/re-encode khi có password hợp lệ |

## 15. Checklist khắc phục tại production

- [ ] Xác định endpoint, filter chain, provider và `UserDetailsService` thực chạy.
- [ ] Phân biệt 401/403/302 với exception missing-prefix và `matches=false`.
- [ ] Không xin người dùng gửi raw password/hash; không log secret/Authentication object.
- [ ] Có một cấu hình encode mới rõ ràng và mapping verify legacy rõ ràng.
- [ ] Cột DB đủ dài, không silent truncate/padding; serializer giữ nguyên hash qua roundtrip.
- [ ] Prefix `{id}` đúng với thuật toán tail; không đổi ID để “đổi thuật toán”.
- [ ] Không dùng `NoOpPasswordEncoder`/fallback cho unknown hashes production.
- [ ] Với legacy bcrypt raw: chỉ thêm `{bcrypt}` sau khi xác định cohort/format, có backup và rollback.
- [ ] Với PBKDF2/scrypt/Argon2: giữ đúng parameter/secret/ID của thời điểm encode.
- [ ] Registration, password change, reset và login có normalization/password handling nhất quán.
- [ ] Không encode hai lần; `UserDetails.getPassword()` trả đúng encoded field.
- [ ] Test canary pass qua HTTP, DB persistence, restart, nhiều node và migration.
- [ ] Account flags, tenant lookup, CSRF/MFA/authorization/session được kiểm độc lập.
- [ ] Có quy trình `UserDetailsPasswordService`/`upgradeEncoding` khi muốn rehash online.
- [ ] Có reset password an toàn nếu hash không thể phục hồi/định danh.
- [ ] Có test password Unicode/dài, ứng xử đúng với BCrypt version và advisory bảo mật.
- [ ] Logs/audit chỉ dùng mã category và correlation ID, không lưu credential hay hash.

## 16. Câu hỏi tự kiểm tra

1. `PasswordEncoder.matches` nhận raw password ở vị trí đối số nào?
2. Vì sao `encoder.encode(raw).equals(storedHash)` thường sai?
3. `{bcrypt}` là thành phần bcrypt salt hay metadata của Spring Delegating?
4. Raw bcrypt bắt đầu `$2a$10$`, tại sao Delegating mặc định có thể báo `id "null"`?
5. Vì sao một cột `VARCHAR(60)` có thể chứa bcrypt raw nhưng không chứa `{bcrypt}` + bcrypt?
6. Vì sao thêm `{pbkdf2}` vào tail bcrypt không thể biến nó thành PBKDF2?
7. Tình huống nào dùng `setDefaultPasswordEncoderForMatches` gây rủi ro?
8. Nếu `PasswordEncoder.matches` true nhưng form login vẫn trả lỗi, kiểm gì tiếp?
9. Thêm prefix cho hash legacy đã kiểm chứng có cần biết raw password không?
10. Chuyển từ bcrypt sang Argon2/PBKDF2 **thật sự** cần gì?
11. Tại sao phải kiểm cả Unicode normalization và số bytes của password?
12. `UserDetailsPasswordService` có tự động hoạt động chỉ vì tạo bean `PasswordEncoder` không?
13. Trong production khi hash không thể xác định, hướng khôi phục an toàn là gì?
14. Một test `@WithMockUser` trả 200 có chứng minh password encoder hoạt động không?
15. Có nên log encoded password để so sánh hai lần đăng nhập thất bại không?

**Đáp án định hướng:** (1) đối số thứ nhất; (2) salt ngẫu nhiên; (3) metadata; (4) thiếu `{id}`; (5) 60 vs 68 ký tự; (6) chỉ đổi nhãn, không đổi thuật toán; (7) fallback NoOp/không kiểm format; (8) account state, provider, MFA, session, CSRF; (9) không nếu đã xác minh format; (10) xác thực raw password rồi re-encode hoặc reset; (11) ký tự/code point/bytes khác nhau và tác động tới hash; (12) không, provider và service phải được cấu hình đúng; (13) password reset đáng tin; (14) không, mock user bỏ qua kiểm password; (15) không.

## 17. Tài liệu tham khảo

- [Spring Security 6.5 — Password Storage / DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — DelegatingPasswordEncoder API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html)
- [Spring Security 6.5 — PasswordEncoderFactories API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/crypto/factory/PasswordEncoderFactories.html)
- [Spring Security 6.5 — DaoAuthenticationProvider API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security 6.5 — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — Testing HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security — CVE-2025-22228 / BCryptPasswordEncoder input length](https://spring.io/security/cve-2025-22228/)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
