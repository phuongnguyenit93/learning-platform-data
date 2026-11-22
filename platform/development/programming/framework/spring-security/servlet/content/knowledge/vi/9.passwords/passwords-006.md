# Salt, pepper và cách quản lý bí mật phía máy chủ trong Spring Security

## 1. Vấn đề: lưu mật khẩu an toàn không chỉ là gọi hàm hash

Trong ứng dụng **Spring Boot / Spring Security Servlet**, mật khẩu người dùng là dữ liệu xác thực rất nhạy cảm. Hệ thống **không nên lưu mật khẩu dạng rõ** và cũng không nên dùng một hàm băm nhanh như SHA-256 đơn thuần để lưu password. Thay vào đó cần dùng **thuật toán băm mật khẩu có chi phí tính toán** (password hashing/KDF) với salt ngẫu nhiên, cùng cơ chế vận hành, quản lý bí mật và chính sách xác thực phù hợp.

Hai khái niệm thường được nhắc đến là:

- **Salt**: giá trị ngẫu nhiên **riêng cho mỗi lần tạo hash**, không cần bí mật. Salt giúp hai người có cùng mật khẩu không có cùng password hash và làm bảng tính trước (rainbow table) kém hiệu quả.
- **Pepper**: một **bí mật bổ sung do máy chủ quản lý**, dùng chung theo một phạm vi/phiên bản khóa trong thiết kế cụ thể, **không lưu cùng dữ liệu password hash**. Pepper có thể tăng khả năng chống tấn công **khi chỉ cơ sở dữ liệu bị lộ**, nhưng tạo thêm trách nhiệm về bảo vệ, vòng đời và xoay vòng khóa.

**Thông điệp quan trọng:** salt là phần bình thường và cần thiết của password hashing; pepper là **biện pháp phòng vệ bổ sung, có lựa chọn**, không thay thế salt, thuật toán hash chậm, xác thực đa yếu tố, throttling hay bảo vệ ứng dụng. Nếu kẻ tấn công chiếm được cả DB và bí mật pepper trên server, lợi ích bổ sung của pepper sẽ giảm đáng kể.

Bài học thuộc nhóm **Mật khẩu**, tập trung vào bảo mật mật khẩu được xác minh ở phía máy chủ với Spring Security trên Servlet stack. Ví dụ sử dụng Java 17+, Spring Security Crypto/`PasswordEncoder` và mô phỏng lưu hash; không phải một hệ thống quản lý user hoàn chỉnh.

## 2. Password hashing không phải mã hóa để giải mã

Ba thao tác có mục đích rất khác nhau:

| Kỹ thuật | Có khóa bí mật? | Có giải ngược để lấy lại giá trị gốc? | Ứng dụng với mật khẩu |
| --- | --- | --- | --- |
| **Mã hóa (encryption)** | Thường có | Có, nếu giữ khóa | Phù hợp cho dữ liệu cần giải mã, **không phải cách lưu mật khẩu đăng nhập thông thường** |
| **Hash nhanh** như SHA-256 | Không | Không trực tiếp, nhưng dễ thử nhiều mật khẩu đoán được ở tốc độ cao | **Không dùng riêng lẻ** để lưu mật khẩu |
| **Password hashing/KDF** như Argon2id, scrypt, BCrypt, PBKDF2 | Bản thân thuật toán không yêu cầu pepper | Không giải mã; xác minh bằng cách tính lại và so sánh | Hướng đi đúng với tham số cost/salt phù hợp |

Mật khẩu người dùng có entropy thường thấp hơn khóa ngẫu nhiên. Kẻ tấn công lấy được một hash có thể thử nhiều chuỗi mật khẩu ứng viên theo kiểu **offline guessing**. Vì thế khả năng chống tấn công phụ thuộc **chi phí mỗi lần thử** của thuật toán và chính sách chọn mật khẩu, không chỉ độ dài output của hàm hash.

Với Spring Security, API `PasswordEncoder` cho phép lưu hash qua `encode(rawPassword)` và kiểm tra qua `matches(rawPassword, storedHash)`. Thường sử dụng `BCryptPasswordEncoder`, hoặc cân nhắc thuật toán/adaptive encoder khác phù hợp với phiên bản, thư viện và yêu cầu vận hành.

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);

String storedHash = encoder.encode(rawPassword);
boolean valid = encoder.matches(loginPassword, storedHash);
~~~

Đây là snippet minh họa; cần import `org.springframework.security.crypto.password.PasswordEncoder` và `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder` và khai báo biến password. `12` là cost factor của BCrypt, không phải độ dài salt hay số vòng lặp mặc định cho mọi môi trường. Khi triển khai production, hãy benchmark trên phần cứng thật và cân nhắc tải đăng nhập/giới hạn DoS; ví dụ chạy được có ở phần 7.

## 3. Salt: công khai, ngẫu nhiên, riêng cho từng hash

### 3.1. Salt giải quyết vấn đề gì?

Giả sử hai tài khoản đều chọn mật khẩu `correct-horse-example`:

~~~text
Không salt (mô hình băm đơn giản, không nên dùng):
  alice  -> HASH("correct-horse-example") -> cùng giá trị
  bob    -> HASH("correct-horse-example") -> cùng giá trị

Với salt ngẫu nhiên riêng và KDF chậm:
  alice  -> KDF(password, salt_A, cost) -> hash_A
  bob    -> KDF(password, salt_B, cost) -> hash_B

  salt_A khác salt_B  => hash_A khác hash_B (với xác suất rất cao)
~~~

Salt còn ngăn việc một bảng precompute cố định dùng chung để tra hàng triệu hash với một cách băm quá đơn giản. Salt **không biến mật khẩu yếu thành mạnh**: nếu database bị lộ, kẻ tấn công vẫn có thể thử dictionary cho **từng hash** bằng thuật toán và salt công khai.

### 3.2. Salt có phải secret không?

**Không.** Salt thường được lưu **cùng password hash** hoặc được mã hóa trong chuỗi output của thuật toán. Bảo mật không dựa trên việc giấu salt; giá trị được lấy ngẫu nhiên, đủ mạnh, khác nhau giữa các lần hash.

Khi dùng `BCryptPasswordEncoder`, thư viện đã tự tạo salt cho mỗi lần `encode` bằng nguồn ngẫu nhiên phù hợp, đồng thời lưu thông tin phiên bản/cost/salt/derived hash trong chuỗi BCrypt. Một chuỗi thường có hình thức:

~~~text
$2a$12$<salt-encoded><hash-encoded>
~~~

Dòng trên là **mô hình cú pháp**, không phải một hash dùng để đăng nhập. Tiền tố như `$2a$`/`$2b$` và cách lưu cụ thể tùy implementation. Không tự cắt chuỗi ở vị trí bất kỳ để đoán thông số khi thư viện có API sẵn.

Vì salt đã nằm trong BCrypt encoded string, khi xác minh chỉ cần:

~~~java
boolean ok = encoder.matches(rawPassword, storedHash);
~~~

**Không cần** tự lấy salt từ DB rồi ghép `salt + password` trước khi gọi `BCryptPasswordEncoder.encode`, cũng không cần một cột salt riêng chỉ để hoạt động của BCrypt. Nếu dùng API khác thì kiểm tra định dạng/tham số của API đó; không áp dụng quy tắc BCrypt một cách máy móc cho mọi KDF.

### 3.3. Vì sao cùng mật khẩu mà hash khác nhau?

Ví dụ:

~~~java
PasswordEncoder bcrypt = new BCryptPasswordEncoder(10);
String hash1 = bcrypt.encode("same-password");
String hash2 = bcrypt.encode("same-password");

System.out.println(hash1.equals(hash2));  // thông thường false
System.out.println(bcrypt.matches("same-password", hash1)); // true
System.out.println(bcrypt.matches("same-password", hash2)); // true
~~~

Đây là snippet minh họa. Output mong đợi là `false`, `true`, `true`, bởi BCrypt sinh salt ngẫu nhiên mới cho mỗi lần encode. Về mặt xác suất, hai salt ngẫu nhiên vẫn có khả năng trùng cực kỳ nhỏ, nên diễn đạt chính xác là **hai hash sẽ khác nhau với xác suất rất cao**.

### 3.4. Không dùng salt dự đoán được

Không lấy username, email, timestamp, user ID hoặc một hằng số cố định làm salt thay cho salt ngẫu nhiên mạnh. Những giá trị đó có thể bị đoán, trùng hoặc thay đổi; làm suy giảm mục tiêu của salt.

Với BCrypt trong Spring Security, cách an toàn và đơn giản nhất là **để encoder sinh salt nội bộ** thay vì viết lại cơ chế này.

## 4. Pepper: một bí mật riêng ở phía máy chủ

### 4.1. Pepper khác salt ở đâu?

Pepper là bí mật cấp ứng dụng/hệ thống được đưa vào quá trình tạo và kiểm tra password hash. Pepper chỉ hữu ích khi attacker lấy được dữ liệu mật khẩu trong DB nhưng **không lấy được pepper**.

| Tiêu chí | Salt | Pepper |
| --- | --- | --- |
| Bản chất | Giá trị ngẫu nhiên, không bí mật | Bí mật có entropy cao |
| Phạm vi thường gặp | Riêng từng lần tạo hash | Có thể dùng chung cho nhiều bản ghi theo một `keyId`/phiên bản |
| Lưu trữ | Cùng hash trong DB là bình thường | **Tách khỏi DB password**; đưa vào secret manager/KMS/HSM hoặc nơi bảo vệ phù hợp |
| Cần để verify? | Có; thường embedded trong hash | Có, nếu thiết kế yêu cầu pepper |
| Khi DB bị rò rỉ | Kẻ tấn công vẫn có salt | Attacker thiếu pepper có thêm rào cản khi crack offline |
| Khi secret bị rò rỉ | Không có ý nghĩa “lộ salt” | Cần đánh giá sự cố, xoay khóa và chính sách reset/migration |
| Thay đổi/rotation | Hash mới tự dùng salt mới | Khó hơn; thường cần password gốc khi user login hoặc luồng reset |
| Mức độ bắt buộc | Thành phần căn bản của password hashing | Phòng vệ bổ sung tùy threat model |

**Pepper không phải mật khẩu thứ hai của người dùng** và không phải cách gửi thêm secret từ browser. Nó là một secret được xử lý **trên server**, không đưa xuống client, không lưu vào source code, Git, log, response, database backup hoặc bảng debug.

### 4.2. Pepper chống được và không chống được điều gì?

Giả sử chỉ bảng `users(id, username, password_hash, pepper_id)` bị sao chép. Attacker có salt/cost/hash BCrypt, nhưng không có secret dùng trong tiền xử lý password. Nếu pepper đủ mạnh và cách kết hợp với password đúng, attacker không thể kiểm thử mật khẩu ứng viên chỉ bằng DB một cách bình thường như khi không có pepper.

Nhưng pepper **không giúp nhiều** trong các tình huống:

- Attacker đồng thời lấy được DB **và** pepper từ máy chủ hoặc secret manager.
- Attacker điều khiển runtime có thể gọi dịch vụ xác thực hoặc quan sát mật khẩu trước khi được hash.
- Có SQL injection hoặc lỗi authorization cho phép truy cập thẳng dữ liệu nghiệp vụ; pepper không vá lỗi đó.
- Mật khẩu bị lừa qua phishing, malware, credential stuffing từ dịch vụ khác, hoặc session/token bị đánh cắp.
- Phần mềm gọi password verification không rate-limit, bị lạm dụng như online guessing oracle; pepper không thay thế throttling/MFA/giám sát.

Pepper là **defense in depth**, không phải cam kết “database leak thì password không thể crack”. Khả năng bảo vệ phụ thuộc cách triển khai, việc giữ bí mật và phạm vi quyền của attacker.

### 4.3. Không ghép pepper tùy tiện vào đầu/cuối password

Một thiết kế kiểu:

~~~java
// Chỉ là anti-pattern; không copy vào production.
String combined = password + pepperString;
String stored = bcrypt.encode(combined);
~~~

có thể gây lỗi do encoding/độ dài input, dễ dùng pepper dưới dạng String, khó quản lý, và đặc biệt vướng giới hạn đầu vào của một số BCrypt implementation. BCrypt truyền thống có **giới hạn khoảng 72 byte** đầu vào hiệu quả; nối pepper sau một password dài có thể khiến phần pepper không còn tác động đúng như mong đợi.

Để có cấu trúc rõ ràng, một phương án là **HMAC-SHA-256 có khóa bí mật trước BCrypt**, sau đó encode output HMAC sang Base64URL ASCII (43 ký tự đối với 32 byte, bỏ padding). HMAC giúp đưa toàn bộ mật khẩu vào đầu vào có độ dài ổn định, tránh ghép chuỗi mơ hồ và tránh vượt 72 byte khi đưa kết quả ASCII vào BCrypt.

Đây là **một lựa chọn kiến trúc có đánh đổi**, không phải điều kiện bắt buộc của Spring Security. Nếu hệ thống chọn Argon2id/scrypt hoặc framework có chính sách pepper khác, cần đánh giá thiết kế tổng thể, khả năng nâng cấp và khuyến nghị bảo mật tương ứng.

## 5. Quy trình kết hợp HMAC pepper và BCrypt

Với một phương án **pepper trước khi password hash**, luồng đăng ký:

~~~text
Mật khẩu mới do user cung cấp
  |
  v
UTF-8 bytes của mật khẩu (không trim/lowercase ngầm)
  |
  v
HMAC-SHA-256(key = SECRET_PEPPER_V1, message = passwordBytes)
  |
  v
Base64URL(HMAC output), 43 ký tự ASCII
  |
  v
BCryptPasswordEncoder.encode(hmacText)
    -> BCrypt tự sinh salt random + tính hash chậm
  |
  v
LƯU VÀO DB:
  pepper_id = "v1"           (mã phiên bản không bí mật)
  password_hash = "$2a$..."  (salt/cost/hash bên trong)
KHÔNG LƯU SECRET_PEPPER_V1 VÀO DB
~~~

Luồng xác minh đăng nhập:

~~~text
User gửi username/password qua kênh được bảo vệ (HTTPS)
  |
  v
Tìm bản ghi password_hash + pepper_id
  |
  v
Đọc secret tương ứng với pepper_id từ vùng secret được quản lý
  |
  v
candidate = Base64URL(HMAC(pepperKey, UTF8(password)))
  |
  v
BCryptPasswordEncoder.matches(candidate, password_hash)
  |
  +-- false -> authentication thất bại
  |
  +-- true  -> password hợp lệ theo hash và pepper hiện hành;
               tiếp tục kiểm tra account state, MFA, authorization...
~~~

Trong Spring Security, `PasswordEncoder` chính là điểm tích hợp thông thường cho tạo hash và verify password. Khi tự triển khai pepper, phải bảo đảm **cả encode và matches đều dùng cùng scheme**, cùng cách chuyển byte, cùng định dạng và cùng đúng key version. Nếu đang chạy nhiều phiên bản ứng dụng, mọi instance phải có thể xác minh những bản ghi do các instance còn lại tạo ra.

### Vì sao phải giữ phiên bản pepper?

Khi thay pepper từ `v1` sang `v2`, bản ghi hash cũ cần được xác minh bằng **v1** cho đến khi được migration hoặc reset. Đánh dấu một `pepper_id` **không bí mật** cho biết key nào được dùng. Nếu chỉ lưu hash và thay một biến môi trường duy nhất, phần lớn user chưa đổi mật khẩu sẽ mất khả năng đăng nhập sau rotation.

Các dạng lưu trữ có thể là hai cột:

~~~text
username       pepper_id       password_hash
alice          v2              $2a$...
bob            v1              $2a$...
~~~

Hoặc một định dạng password hash **có version và được parser kiểm soát**, chẳng hạn `pepper-v1:$2a$...`. Không nhầm `pepper_id` (chỉ là nhãn tham chiếu) với giá trị secret; không đặt base64 secret vào tên version.

### Những gì không nên làm

- Không dùng `SHA256(password)` thay thế BCrypt chỉ vì đã có salt/pepper.
- Không dùng chung một salt cố định cho tất cả tài khoản.
- Không lưu secret pepper cùng bảng `users`, trong cấu hình commit vào Git hoặc response/log.
- Không in HMAC output/password ra log; HMAC output là **đầu vào nhạy cảm** của password hash và không nên lộ.
- Không dùng secret JWT signing key cho pepper; nên **tách khóa theo mục đích** và quyền sử dụng.
- Không dùng salt làm pepper hoặc đặt pepper ở client; hai khái niệm khác nhau.
- Không dùng một secret quá ngắn/human-readable như `"myPepper123"`. Pepper phải là các byte ngẫu nhiên có entropy cao, tạo từ cryptographically secure RNG.

## 6. Quản lý pepper và server-side secrets đúng cách

### 6.1. Secret được tạo ở đâu?

Pepper nên được tạo từ một **CSPRNG** như `SecureRandom` hoặc hệ thống phát sinh khóa của KMS/HSM, với độ dài khóa đủ mạnh. Với HMAC-SHA-256, 32 byte ngẫu nhiên là một lựa chọn thuận tiện. Secret **không** phải do một người nghĩ ra rồi lưu vào file cấu hình.

Ví dụ dùng OpenSSL ở môi trường phát triển:

~~~bash
openssl rand -base64 32
~~~

Lệnh này **in secret Base64 ra terminal**; chỉ chạy khi môi trường hiển thị/ghi lịch sử/log được kiểm soát. Với production, nên tạo secret trực tiếp qua cơ chế secret manager/KMS/HSM của tổ chức, tránh copy-paste thủ công hoặc để lại bản sao trong ticket/chat.

### 6.2. Nơi lưu và nơi không lưu

Phương án thường gặp trong hệ thống thật:

- Dùng **secret manager** có IAM/access policy và audit, hoặc KMS/HSM khi thiết kế yêu cầu key không rời khỏi môi trường bảo vệ.
- Ứng dụng chỉ được **đọc đúng secret cần thiết**, theo least privilege; phân tách môi trường dev/staging/production.
- Dùng workload identity hoặc cơ chế cấp quyền ngắn hạn thay cho hard-code credentials để lấy secret.
- Secret được chuyển tới instance qua kênh bảo mật và nằm trong bộ nhớ **chỉ khi cần**, giới hạn người/process có quyền đọc.
- Theo dõi truy cập secret và có playbook khi nghi ngờ compromise; bảo vệ cả backup/snapshot và quyền quản trị secret manager.

Một biến môi trường như `PASSWORD_PEPPER_B64` **có thể dùng cho demo và một số cấu hình triển khai**, nhưng không nên xem mọi môi trường là “an toàn tuyệt đối”: biến môi trường có thể bị lộ qua process inspection, crash dump, diagnostic output, quyền quản trị host hoặc cấu hình orchestrator. Cách bảo vệ phụ thuộc nền tảng vận hành. Trong production nên ưu tiên secret manager phù hợp và đánh giá cách secret được inject, quyền đọc và log.

**Không đặt** pepper trong:

~~~yaml
# KHÔNG được dùng để lưu secret thật vào file được commit.
password:
  pepper: "plaintext-secret-goes-here"
~~~

Snippet YAML trên là **anti-pattern minh họa**, không phải cấu hình được đề xuất.

### 6.3. Tại sao dùng một pepper chung có rủi ro?

Nếu toàn hệ thống dùng chung một khóa, mất khóa đó có thể ảnh hưởng **mọi account**. Phân vùng secret theo môi trường, ứng dụng hoặc ranh giới dữ liệu phù hợp có thể giảm blast radius nhưng tăng độ phức tạp vận hành. Không cần tạo một pepper độc lập cho mỗi user chỉ để giả lập salt; nếu làm vậy phải có chiến lược key mapping/rotation chắc chắn và cân nhắc thực chất lợi ích so với cơ chế hiện có.

Pepper cần rotation/recovery strategy. Nếu secret bị mất mà không còn bản sao được quản lý hợp lệ, những password hash đã pepper bằng secret ấy **không thể xác minh** theo sơ đồ tiền HMAC này, dù DB vẫn còn nguyên. Đó là một lý do quan trọng phải có backup/key escrow theo chính sách bảo mật, phân quyền khôi phục và kịch bản buộc user reset password khi không thể verify.

### 6.4. Luân chuyển pepper: thêm khóa mới không làm hash cũ tự đổi

Giả sử DB có các bản ghi dùng `v1` và mục tiêu chuyển sang `v2`:

1. Tạo secret `v2` mới bằng CSPRNG, lưu trong secret manager, cấp quyền đọc theo nhu cầu.
2. Triển khai verifier có thể đọc **cả v1 và v2** trong giai đoạn chuyển tiếp; encoder dành cho mật khẩu mới mặc định dùng **v2**.
3. Khi user đăng nhập thành công với record `v1` và raw password đang hiện diện, xác minh bằng v1 rồi **tạo hash mới** bằng v2, salt mới/cost phù hợp, và lưu `pepper_id=v2`.
4. Dùng cập nhật an toàn khi có concurrent login/đổi password, ví dụ điều kiện `WHERE old_password_hash = ...` hoặc phiên bản bản ghi, để tránh ghi đè dữ liệu mới.
5. Theo dõi số record còn ở v1; account không đăng nhập trong khoảng chuyển tiếp có thể cần quy trình reset password theo chính sách.
6. Chỉ xóa/thu hồi v1 khi chắc chắn không còn bản ghi cần xác minh bằng v1 **hoặc đã có kế hoạch reset/phục hồi cho chúng**. Nếu v1 bị lộ, áp dụng ứng phó sự cố phù hợp, không giữ vô hạn chỉ để tránh đổi password.

Đây là **migration logic của ứng dụng**, không phải một tính năng tự động có sẵn chỉ vì gọi `PasswordEncoder.upgradeEncoding`. Spring Security có hook liên quan việc nâng cấp password hash trong một số flow, nhưng ứng dụng phải xây cơ chế versioned pepper và lưu/đổi khóa đúng.

### 6.5. Vì sao không “đổi khóa hàng loạt” bằng cách đọc hash cũ?

Với sơ đồ:

~~~text
stored = BCrypt(Base64URL(HMAC(oldPepper, rawPassword)), randomSalt)
~~~

server **không thể lấy lại rawPassword** từ stored BCrypt hash. Không thể tính `HMAC(newPepper, rawPassword)` nếu không biết rawPassword. Vì vậy không thể rehash v1 → v2 hoàn toàn **offline** chỉ từ database. Phải dựa vào mật khẩu user cung cấp khi đăng nhập thành công hoặc quy trình reset password đã xác minh danh tính.

Một số kiến trúc pepper *sau* password hash có đặc tính migration khác, nhưng cần xem cách lưu/verify và mô hình đe dọa cụ thể, không tự suy rằng chỉ cần thay secret là mọi stored hash vẫn xác thực được.

## 7. Ví dụ Java 17+ chạy được: PasswordEncoder có pepper trước BCrypt

Ví dụ này là một chương trình Java console sử dụng **Spring Security Crypto** với một `PasswordEncoder` tùy chỉnh. Nó trình bày đúng ba điểm:

1. Pepper là **32 byte ngẫu nhiên** được cung cấp qua môi trường chạy; không hard-code.
2. Input mật khẩu đi qua **HMAC-SHA-256**, sau đó **Base64URL** để đưa vào BCrypt (43 ký tự ASCII, tránh vượt giới hạn 72 byte của BCrypt).
3. BCrypt tự tạo **salt ngẫu nhiên riêng mỗi lần encode**; cùng mật khẩu với cùng pepper vẫn tạo hai hash khác nhau, và mỗi hash vẫn verify được.

Mẫu chạy được ở đây dùng **một key version `p1`** để tập trung vào quy trình encode/verify. Để rotate cần bộ lưu nhiều version và upgrade có điều kiện như mục 6.4; **đừng chỉ sửa chuỗi `p1` trong code rồi thay secret**.

### 7.1. Cấu trúc file

~~~text
pepper-demo/
├── pom.xml
└── src/main/java/demo/PepperDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>pepper-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-crypto</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jcl</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**`src/main/java/demo/PepperDemo.java`**

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.Base64;
import java.util.Objects;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PepperDemo {

    private static final String PEPPER_VERSION = "p1:";
    private static final String PEPPER_ENV = "PASSWORD_PEPPER_B64";

    private static final class PepperedEncoder implements PasswordEncoder {
        private final BCryptPasswordEncoder bcrypt =
            new BCryptPasswordEncoder(10);

        private final SecretKeySpec hmacKey;

        private PepperedEncoder(byte[] pepper) {
            if (pepper == null || pepper.length != 32) {
                throw new IllegalArgumentException(
                    "Pepper must be exactly 32 random bytes");
            }
            // SecretKeySpec sao chép byte[] theo API của nó.
            this.hmacKey = new SecretKeySpec(pepper, "HmacSHA256");
        }

        // Input BCrypt luôn là Base64URL của 32 byte HMAC:
        // 43 ký tự ASCII, không còn phụ thuộc độ dài chuỗi raw UTF-8.
        private String keyedInput(CharSequence rawPassword) {
            Objects.requireNonNull(rawPassword, "rawPassword");
            byte[] rawBytes = rawPassword.toString()
                .getBytes(StandardCharsets.UTF_8);
            byte[] digest = null;
            try {
                Mac hmac = Mac.getInstance("HmacSHA256");
                hmac.init(hmacKey);
                digest = hmac.doFinal(rawBytes);
                return Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(digest);
            } catch (GeneralSecurityException ex) {
                throw new IllegalStateException("HMAC-SHA-256 unavailable", ex);
            } finally {
                Arrays.fill(rawBytes, (byte) 0);
                if (digest != null) {
                    Arrays.fill(digest, (byte) 0);
                }
            }
        }

        @Override
        public String encode(CharSequence rawPassword) {
            return PEPPER_VERSION + bcrypt.encode(keyedInput(rawPassword));
        }

        @Override
        public boolean matches(CharSequence rawPassword,
                               String encodedPassword) {
            if (encodedPassword == null ||
                !encodedPassword.startsWith(PEPPER_VERSION)) {
                return false; // Unknown/missing pepper scheme is rejected.
            }
            String bcryptHash =
                encodedPassword.substring(PEPPER_VERSION.length());
            return bcrypt.matches(keyedInput(rawPassword), bcryptHash);
        }

        @Override
        public boolean upgradeEncoding(String encodedPassword) {
            if (encodedPassword == null ||
                !encodedPassword.startsWith(PEPPER_VERSION)) {
                return true; // App phải có logic migration cho scheme khác.
            }
            return bcrypt.upgradeEncoding(
                encodedPassword.substring(PEPPER_VERSION.length()));
        }
    }

    public static void main(String[] args) {
        String secretB64 = System.getenv(PEPPER_ENV);
        if (secretB64 == null || secretB64.isBlank()) {
            throw new IllegalStateException(
                "Set PASSWORD_PEPPER_B64 to Base64 of 32 random bytes");
        }

        byte[] secret = Base64.getDecoder().decode(secretB64);
        try {
            PasswordEncoder encoder = new PepperedEncoder(secret);
            String stored1 = encoder.encode("correct-horse-example");
            String stored2 = encoder.encode("correct-horse-example");

            System.out.println("correct password: " +
                encoder.matches("correct-horse-example", stored1));
            System.out.println("wrong password: " +
                encoder.matches("wrong-password", stored1));
            System.out.println("same encoded hash: " +
                stored1.equals(stored2));
            System.out.println("stored scheme: " +
                stored1.substring(0, PEPPER_VERSION.length()));
        } finally {
            // Giảm thời gian một bản sao key nằm trong mảng local.
            Arrays.fill(secret, (byte) 0);
        }
    }
}
~~~

**Giải thích thiết kế:**

- `PepperedEncoder` implements `PasswordEncoder`, nên có thể được đăng ký làm bean `@Bean PasswordEncoder` trong một ứng dụng dùng `DaoAuthenticationProvider`/`UserDetailsService`, miễn là định dạng stored hashes và key version được thiết kế đồng bộ.
- `PEPPER_VERSION` chỉ là nhãn version **không bí mật** nằm đầu stored string; secret `PASSWORD_PEPPER_B64` không được lưu vào hash.
- `matches` **không** gọi `encode(raw).equals(stored)`. BCrypt sinh salt mới ở mỗi `encode` nên phải dùng `bcrypt.matches(...)` để đối chiếu dựa trên salt đã embedded trong hash lưu trữ.
- `HmacSHA256` tạo output nhị phân 32 byte; Base64URL không padding có đúng **43 ký tự ASCII**, nên phần đưa vào BCrypt tránh bẫy giới hạn ~72 byte của bcrypt truyền thống.
- `Mac` được tạo mới trong mỗi lần gọi, thay vì chia sẻ một `Mac` mutable giữa nhiều request; đây là cách dễ tránh concurrency hazard.
- `upgradeEncoding` ở ví dụ chỉ hỏi BCrypt về cost và đánh dấu scheme lạ cần upgrade. Nó **không tự triển khai** migration nhiều pepper key. Nếu triển khai version p2 cần map version→secret, cách verify hash cũ và rehash khi có raw password.
- `Arrays.fill` chỉ xóa **những mảng byte có thể kiểm soát**. Java `String`, environment, bộ nhớ JVM và internal copies không bảo đảm xóa hoàn toàn; đoạn mã không tuyên bố key không thể tồn tại trong memory dump.

**Giới hạn của ví dụ:** đây là mô hình console cho lập trình viên học `PasswordEncoder`, không thực hiện đăng nhập HTTP/session/user database, không kiểm thử tốc độ bruteforce, không có cơ chế rotation production. Trong một hệ thống thật cần kiểm tra khả năng sẵn có của secret, chính sách fail closed, audit/metrics và xử lý đồng bộ khi nâng cấp hash.

### 7.2. Tạo pepper demo và chạy

**Linux/macOS shell** (chỉ cho môi trường học tập; tránh in secret thật trong terminal/log):

~~~bash
export PASSWORD_PEPPER_B64="$(openssl rand -base64 32)"
mvn -q compile exec:java -Dexec.mainClass=demo.PepperDemo
~~~

Lệnh tạo một secret ngẫu nhiên, giữ trong biến môi trường của shell hiện hành; Java đọc qua `System.getenv`. Không gắn secret trực tiếp trong tham số command line vì command line có thể bị ghi lại trong process list và lịch sử lệnh. Với môi trường production, không tạo key mới mỗi lần app start vì sẽ làm hash cũ không còn verify được.

**Windows PowerShell** (ví dụ local):

~~~powershell
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$key = New-Object byte[] 32
$rng.GetBytes($key)
$env:PASSWORD_PEPPER_B64 = [Convert]::ToBase64String($key)
[Array]::Clear($key, 0, $key.Length)
$rng.Dispose()
mvn -q compile exec:java "-Dexec.mainClass=demo.PepperDemo"
~~~

Hai đoạn trên là hai cách chuẩn bị **một secret demo tạm thời**. Khi thay secret trong những lần chạy tiếp theo, `PepperedEncoder` có thể verify các hash được tạo **trong lần chạy với cùng secret**; nếu ứng dụng persist hash giữa các lần chạy, key phải được giữ ổn định và quản lý an toàn. Không copy secret demo vào source code để “chữa” lỗi mất key.

**Đầu ra mong đợi** (không phụ thuộc vào giá trị pepper ngẫu nhiên nếu tất cả lời gọi diễn ra trong một lần chạy thành công):

~~~text
correct password: true
wrong password: false
same encoded hash: false
stored scheme: p1:
~~~

Vì BCrypt sinh salt ngẫu nhiên, `stored1` và `stored2` sẽ **khác nhau với xác suất áp đảo** dù input/một pepper như nhau. Chương trình không in secret và không in stored hash để tránh lẫn nhầm demo output với dữ liệu cần chia sẻ.

### 7.3. Tích hợp vào Spring Security Servlet như thế nào?

Trong ứng dụng Spring Boot Servlet, cách đặt điểm tích hợp cơ bản là:

~~~java
@Configuration
class PasswordConfiguration {

    @Bean
    PasswordEncoder passwordEncoder(PepperSecretProvider secrets) {
        return new PepperedPasswordEncoder(
            secrets.activeKeyId(),
            secrets.availableVerificationKeys()
        );
    }
}
~~~

Đây là **mẫu kiến trúc/pseudocode có kiểu Java**, không phải class độc lập biên dịch: `PepperSecretProvider` và `PepperedPasswordEncoder` nhiều-version chưa được định nghĩa trong project demo. Không được copy snippet này và kỳ vọng chạy ngay. Nó nhấn mạnh rằng production encoder cần nhận key từ một secret provider có ACL rõ ràng, lưu version vào stored value, và biết verify các version hợp lệ khi migration.

`DaoAuthenticationProvider` dùng `PasswordEncoder.matches(raw, stored)` để xác minh khi user được tải từ `UserDetailsService`. Ứng dụng cần bảo đảm khi đăng ký password mới, đổi password và load user đều dùng đúng **cùng scheme**. Với `DelegatingPasswordEncoder` hoặc store có prefix `{bcrypt}`, phải thiết kế thứ tự prefix hợp lệ, tránh bọc sai để gây lỗi "There is no PasswordEncoder mapped for id". Không chuyển dữ liệu cũ sang prefix mới bằng cách sửa string đơn thuần; hash phải được tính với đúng đầu vào/secret/thuật toán.

Nếu ứng dụng có `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, giá trị prefix `{bcrypt}` là **định danh thuật toán** cho delegating encoder, **khác** với `pepper_id` là định danh secret của ứng dụng. Có thể hỗ trợ cả hai loại version nhưng phải định nghĩa rõ parser, thứ tự encode/verify và migration; đừng coi hai prefix là một.

## 8. So sánh các lựa chọn khi thiết kế hệ thống thật

### 8.1. Không pepper + BCrypt an toàn có thể đã phù hợp

Nhiều hệ thống dùng `BCryptPasswordEncoder` với salt random nội bộ, cost thích hợp, HTTPS, MFA, rate limiting, bảo vệ DB và chính sách password tốt vẫn có một thiết kế hợp lý. Pepper không phải điều kiện để Spring Security xác thực đúng.

Câu hỏi nên hỏi trước khi thêm pepper:

1. Threat model có tình huống **DB leak nhưng runtime/secret manager chưa bị lộ** không?
2. Đội vận hành có quản lý key lifecycle, backup, rotation và mất key an toàn không?
3. Có khả năng thực hiện migration/reset password theo chính sách không?
4. Có điều kiện kiểm thử và giám sát đảm bảo cùng key version ở mọi instance không?
5. Lợi ích phòng vệ có lớn hơn rủi ro do thiết kế pepper phức tạp và sai lệch không?

Nếu chưa có năng lực quản lý secret, **đừng tự tạo pepper rồi hard-code vào cùng repository**. Làm vậy có thể gần như không giúp gì khi repository bị lộ và còn tạo thêm điểm lỗi.

### 8.2. Vì sao vẫn cần đánh giá thuật toán thích hợp?

Argon2id là lựa chọn password hashing có tham số memory/time hiện đại; scrypt cũng có thuộc tính memory-hard; BCrypt là giải pháp đã được sử dụng rộng rãi với hỗ trợ tốt trong Spring Security; PBKDF2 đôi khi phù hợp các yêu cầu tuân thủ/môi trường cụ thể. Chọn thuật toán theo chính sách bảo mật, thư viện sẵn có, chất lượng triển khai và benchmark. **Pepper không làm SHA-256 nhanh trở thành một password hash hiện đại**.

Với BCrypt, các biến thể implementation có giới hạn xử lý chuỗi dài và encoding; quy trình HMAC → Base64URL → BCrypt như trên chủ động tạo input ASCII 43 byte. Nhưng điều này **không** tự khắc phục password quá yếu hoặc chính sách nhập liệu bất hợp lý.

### 8.3. Chi phí vận hành và tấn công DoS

Adaptive password hashing cố ý tiêu tốn CPU/memory. Pepper HMAC thường rẻ hơn BCrypt, nhưng verification bcrypt vẫn tốn tài nguyên. Kẻ tấn công có thể cố gửi nhiều request để chiếm CPU, do đó endpoint login phải có throttling/rate limit, giám sát, giới hạn input và capacity planning. Tăng cost thật cao không đồng nghĩa luôn an toàn hơn nếu server bị quá tải.

Không silently trim/lowercase password trước khi hash; nếu chuẩn hóa Unicode hoặc có giới hạn độ dài, phải thống nhất rõ với UX và giữa encode/matches. Đừng lưu/ghi log raw password để xử lý lỗi encoding. Dữ liệu mật khẩu quá dài nên có giới hạn hợp lý để bảo vệ hệ thống khỏi tiêu thụ tài nguyên quá mức, đồng thời tránh yêu cầu password ngắn một cách không cần thiết.

## 9. Checklist triển khai và điều tra lỗi

### Khi đăng ký hoặc đổi mật khẩu

1. Mật khẩu nhận qua HTTPS, không log raw hoặc secret.
2. Kiểm tra chính sách mật khẩu ở tầng thích hợp.
3. Nếu có pepper, lấy **active key/version** từ nơi lưu bí mật đáng tin cậy.
4. HMAC/tiền xử lý nhất quán, không tự nối chuỗi tùy tiện.
5. Gọi adaptive `PasswordEncoder.encode(...)`; để BCrypt tự tạo salt.
6. Lưu version + hash, không lưu raw password, salt riêng không cần thiết cho BCrypt, và **không lưu pepper** vào DB.
7. Nếu thay password, nên xử lý session/token cũ theo chính sách, audit sự kiện mà không lộ secret.

### Khi đăng nhập

1. Load user record và đọc đúng `pepper_id`/scheme.
2. Đọc đúng phiên bản secret còn hợp lệ (không mặc định thử key bất kỳ vô hạn).
3. Tính lại HMAC input từ raw password, gọi `BCryptPasswordEncoder.matches` với hash đã lưu.
4. Xử lý failed authentication bằng response nhất quán, không phơi trạng thái nội bộ hoặc key ID cho client không được phép.
5. Nếu xác minh thành công với key/cost cũ, cân nhắc nâng cấp hash bằng secret/cost mới và lưu an toàn.
6. Tiếp tục kiểm tra account status, MFA, session và authorization ở tầng tương ứng.

### Các lỗi hay gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Hash cùng mật khẩu cho ra hai chuỗi khác nhau → cho là lỗi | BCrypt tự tạo salt mới | Dùng `matches`, đừng so sánh `encode(raw)` với hash cũ |
| Lưu salt trong code như một hằng | Salt thiếu tính ngẫu nhiên/riêng từng hash | Dùng encoder sinh salt tự động |
| Đặt pepper cùng bảng user | DB leak sẽ mang theo cả pepper | Tách secret khỏi dữ liệu hash |
| Hard-code pepper vào `application.yml` được commit | Repo leak làm mất lợi ích pepper | Dùng secret manager và cơ chế inject phù hợp |
| Đổi key nhưng không version hash | User cũ không thể verify | Versioned key, migration khi login hoặc reset |
| Ghép `password + pepper` trực tiếp trước BCrypt | Dễ gặp giới hạn input/encoding và lỗi thiết kế | Dùng một scheme được xác định rõ, ví dụ HMAC → Base64URL → BCrypt |
| Dùng pepper để thay salt | Không có salt riêng cho từng hash | Salt random vẫn bắt buộc |
| Dùng `SHA256(password + salt + pepper)` | Hash nhanh dễ bị thử offline nếu secret lộ | Dùng adaptive password hash với cost |
| In HMAC output ra log | HMAC output là đầu vào nhạy cảm của BCrypt | Không log bí mật hoặc thông tin tiền xử lý |
| Coi environment variable an toàn tuyệt đối | Có đường lộ qua runtime/process/config | Đánh giá nền tảng, ưu tiên secret manager/IAM |
| Dùng cùng key cho JWT và pepper | Tăng blast radius, lẫn chính sách rotation | Tách khóa theo mục đích |
| Mất pepper mà không có recovery | Password hash không thể verify | Thiết kế backup/version/forced reset |
| Đăng nhập thành công bằng token cũ sau đổi password | Password hash không tự revoke token | Thiết kế session/token revocation nếu cần |

### Khi nghi ngờ pepper bị lộ

Xác định nhanh **phạm vi key**, những môi trường/bản ghi dùng key đó, khả năng attacker đã có DB, quyền truy cập secret manager, token/session đang có và mức độ kiểm soát runtime. Sau đó thực hiện incident response theo chính sách: cô lập nguyên nhân, xoay key có kiểm soát, cập nhật verifier và kế hoạch rehash/reset, hủy token/session khi cần, giám sát login bất thường và thông báo theo yêu cầu. Không tự ý xóa key cũ trước khi hiểu ảnh hưởng tới khả năng xác minh tài khoản.

Cần phân biệt **planned rotation** (khóa cũ còn được quản lý trong giai đoạn chuyển tiếp) với **rotation do compromise** (có thể phải buộc reset ngay, không tin vào secret cũ). Giữ pepper bị nghi lộ lâu dài chỉ để tương thích có thể đánh đổi bảo mật không chấp nhận được.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Vì sao hai account dùng cùng password nhưng BCrypt hash khác nhau?

**Đáp:** Mỗi `encode` dùng salt ngẫu nhiên riêng rồi lưu salt/cost cùng output hash; hai hash khác nhau với xác suất rất cao.

**Câu 2.** Salt có phải cất trong KMS như pepper không?

**Đáp:** Không. Salt không cần bí mật và thường được embedded vào BCrypt hash. Pepper là secret ngoài DB nếu hệ thống lựa chọn áp dụng.

**Câu 3.** Khi attacker lấy DB nhưng không lấy pepper, pepper có thể giúp gì?

**Đáp:** Thêm một rào cản cho việc kiểm thử mật khẩu ứng viên offline theo scheme có key, miễn là pepper đủ mạnh và được bảo vệ. Nó không ngăn các hình thức tấn công khác hoặc DB+key compromise.

**Câu 4.** Vì sao không nối chuỗi dài `password + pepper` rồi BCrypt một cách ngây thơ?

**Đáp:** Dễ vướng giới hạn khoảng 72 byte đầu vào của BCrypt và các vấn đề encoding, khiến pepper không tác động như mong muốn. Scheme HMAC → Base64URL → BCrypt có input ASCII cố định dễ kiểm soát hơn.

**Câu 5.** Khi đổi pepper v1 sang v2, có thể sửa toàn bộ hash ngay chỉ từ DB không?

**Đáp:** Không đối với scheme tiền HMAC rồi BCrypt ở bài này: cần raw password để tính HMAC với key mới. Có thể rehash lúc user đăng nhập thành công hoặc yêu cầu reset, theo chính sách.

**Câu 6.** `PasswordEncoder.matches(raw, stored)` khác gì so sánh `encode(raw).equals(stored)`?

**Đáp:** `matches` xác minh dựa trên salt và tham số của stored hash. `encode` tạo hash có salt mới, nên so sánh chuỗi trực tiếp là sai.

**Câu 7.** Có pepper thì có thể dùng SHA-256 nhanh thay BCrypt không?

**Đáp:** Không. Salt/pepper không thay thế tính toán có chi phí của password hashing được thiết kế chống offline guessing.

**Câu 8.** Đưa pepper vào biến môi trường có đồng nghĩa bí mật tuyệt đối không?

**Đáp:** Không. Vẫn có rủi ro từ runtime, log, process inspection, crash dump hoặc quản trị host; production cần secret management và least privilege phù hợp.

**Câu 9.** Khi user đăng nhập với hash version v1 hợp lệ, thao tác nâng cấp an toàn là gì?

**Đáp:** Verify bằng v1, tạo hash mới với pepper v2 + salt/cost mới bằng raw password đang có, rồi update bản ghi có kiểm soát; không thay version text đơn thuần.

**Câu 10.** Nếu app deploy 3 instance với ba pepper ngẫu nhiên khác nhau thì sao?

**Đáp:** Một password hash tạo ở instance này có thể không được instance khác verify. Các instance trong cùng scope phải dùng đúng secret/version chung được quản lý ổn định; key rotation cần được điều phối.

**Ghi nhớ:** **Salt ngẫu nhiên là một phần công khai của password hash và BCrypt đã quản lý salt. Pepper là secret riêng ở phía server, chỉ thêm khi có threat model và năng lực quản lý key. Mọi hash vẫn phải dùng thuật toán thích hợp; việc quản lý, backup, xoay và thu hồi pepper quan trọng không kém cách kết hợp nó với password.**