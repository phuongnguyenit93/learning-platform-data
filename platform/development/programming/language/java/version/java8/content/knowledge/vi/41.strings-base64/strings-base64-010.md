# Phân biệt Base64 với mã hóa bảo mật trong Java

**Base64 không phải mã hóa bảo mật (encryption).** Base64 chỉ là một cách **mã hóa biểu diễn dữ liệu nhị phân thành ký tự văn bản** (*binary-to-text encoding*). Ai đọc được chuỗi Base64 đều có thể đảo ngược phép biến đổi để lấy các byte gốc: **không cần mật khẩu, khóa bí mật hay quyền đặc biệt**.

Ví dụ:

~~~text
Văn bản UTF-8:  Man
Base64:         TWFu
Giải mã Base64: Man
~~~

Nếu gửi một mật khẩu, số thẻ, access token hoặc thông tin cá nhân ở dạng Base64 mà không có biện pháp bảo vệ khác, dữ liệu **không được giữ bí mật**. Một kẻ đọc được chuỗi Base64 có thể dùng công cụ rất phổ biến để giải mã.

Trong Java, `java.util.Base64` được cung cấp từ **Java 8** và vẫn là API hiện hành để chuyển đổi dữ liệu giữa `byte[]` và dạng Base64. Để **bảo mật**, phải dùng đúng cơ chế theo mục tiêu: **TLS** cho truyền tải, **mã hóa có xác thực** như AES-GCM cho dữ liệu cần giữ bí mật, **HMAC/chữ ký số** để xác minh thông điệp, và **thuật toán băm mật khẩu thích hợp** để lưu mật khẩu. Base64 có thể được dùng **bên ngoài** các cơ chế ấy để đóng gói byte thành text, nhưng không thay thế bất cứ cơ chế bảo vệ nào.

Bài thuộc nhóm **Chuỗi và Base64** với đề tài **Phân biệt Base64 với mã hóa bảo mật**, chỉ sử dụng kiến thức **vẫn áp dụng trong Java hiện đại**. Bài giải thích khái niệm, các dạng Base64, encoding/decoding Java, khác biệt với hashing/encryption/signature, xử lý dữ liệu nhạy cảm, ví dụ Java chạy được, lỗi phổ biến và checklist an toàn.

## 1. Bốn khái niệm rất dễ nhầm

| Cơ chế | Mục tiêu chính | Có thể đảo ngược? | Có khóa bí mật? | Chống người lạ đọc nội dung? |
| --- | --- | --- | --- | --- |
| **Base64 encoding** | Biểu diễn byte bằng ký tự phù hợp khi vận chuyển/lưu trữ text | **Có**, decoder công khai | **Không** | **Không** |
| **Encryption** | Bảo mật nội dung (confidentiality) | **Có**, nếu có khóa/điều kiện giải mã hợp lệ | **Có**, theo thuật toán | **Có**, nếu thiết kế đúng |
| **Cryptographic hash** | Tạo digest một chiều cho dữ liệu | Không có phép giải mã ngược chuẩn | Không, với hash thông thường | **Không** (digest không che plaintext nếu plaintext vẫn được gửi) |
| **HMAC / chữ ký số** | Kiểm tra tính toàn vẹn và xác thực theo mô hình khóa | Không phải phép khôi phục plaintext | HMAC dùng khóa chia sẻ; chữ ký dùng private/public key | **Không**, trừ khi kết hợp encryption |

**Chữ “mã hóa” trong tiếng Việt có thể chỉ hai việc khác nhau:**

- *Encoding*: đổi cách **biểu diễn** nhưng vẫn giữ nguyên thông tin để hệ thống khác đọc được.
- *Encryption*: biến đổi bằng **mật mã và khóa** để ngăn bên không có quyền đọc nội dung.

Vì vậy, khi viết thiết kế bảo mật, nên dùng cụm **“mã hóa biểu diễn Base64”** và **“mã hóa bảo mật AES-GCM”**, hoặc giữ nguyên từ tiếng Anh để tránh nhầm.

### 1.1. Ba mục tiêu bảo mật cần tách biệt

- **Confidentiality — tính bí mật:** người không có khóa/quyền phù hợp không đọc được dữ liệu.
- **Integrity — tính toàn vẹn:** phát hiện dữ liệu đã bị thay đổi trái phép.
- **Authenticity — xác thực nguồn gốc/thông điệp:** có cơ sở mật mã để tin thông điệp đến từ thực thể nắm khóa phù hợp.

Base64 **không cung cấp cả ba mục tiêu**. Encryption thuần cũng không nhất thiết cung cấp integrity; do đó thiết kế mới nên ưu tiên **AEAD** như AES-GCM, vốn cung cấp mã hóa **kèm kiểm tra tính toàn vẹn/xác thực thông điệp theo khóa bí mật**. HMAC hoặc chữ ký số hỗ trợ integrity/authenticity nhưng **không giấu nội dung**.

### 1.2. Encoding không tạo entropy hay quyền truy cập

~~~text
"role=user"  --Base64--> chuỗi A
"role=admin" --Base64--> chuỗi B

Người biết thuật toán công khai có thể tự tạo chuỗi B.
Không có khóa nào cần biết để đổi role.
~~~

Một server không được tin rằng một field đã được Base64-encode thì field đó không thể bị sửa. Quyền admin, giá tiền, userId, tenantId, ngày hết hạn hoặc phạm vi token **phải được kiểm tra bằng cơ chế xác thực/ủy quyền hợp lệ**, không phải nhờ “giấu chữ” trong Base64.

## 2. Base64 hoạt động như thế nào?

Base64 nhóm **3 byte (24 bit)** rồi chia thành **4 nhóm 6 bit**. Mỗi nhóm 6 bit có 64 giá trị (0–63), được ánh xạ sang 64 ký tự thuộc bảng chữ cái Base64.

~~~text
3 bytes = 24 bits
24 bits / 6 bits = 4 ký tự Base64

Ví dụ "Man":
ASCII/UTF-8 bytes:  4D 61 6E
Các bit:            01001101 01100001 01101110
Nhóm 6 bit:         010011 010110 000101 101110
Chỉ số:             19     22     5      46
Ký tự:              T      W      F      u
Kết quả:            TWFu
~~~

Trong biến thể Basic, bảng ký tự gồm `A–Z`, `a–z`, `0–9`, `+`, `/`. Khi số byte không chia hết cho 3, ký tự `=` được sử dụng làm **padding** ở cuối để hoàn thiện nhóm bốn ký tự, theo dạng padded phổ biến.

| Đầu vào | Base64 Basic | Giải thích |
| --- | --- | --- |
| `M` | `TQ==` | Một byte, cần hai ký tự `=` |
| `Ma` | `TWE=` | Hai byte, cần một `=` |
| `Man` | `TWFu` | Đúng ba byte, không padding |
| Chuỗi rỗng | Chuỗi rỗng | Không có byte để biểu diễn |

**Padding không phải mật khẩu.** Bỏ `=` ở cuối theo quy tắc Base64url không thêm bảo mật. Một decoder phù hợp vẫn khôi phục byte ban đầu.

### 2.1. Kích thước tăng khoảng 33%

Với `n` byte đầu vào, chiều dài Base64 **có padding** thường là:

\[
L = 4 \left\lceil \frac{n}{3} \right\rceil
\]

Đối với dữ liệu lớn, mỗi 3 byte thành 4 ký tự, tức kích thước dạng văn bản Base64 tăng khoảng **một phần ba**, chưa tính xuống dòng MIME, JSON envelope hoặc metadata.

Base64 **không nén dữ liệu**. Encode rồi decode không khiến dữ liệu nhỏ hơn hay khó đoán hơn. Đầu ra có thể dễ đưa vào JSON, URL, email hoặc hệ thống chỉ truyền văn bản, nhưng phải tính phí băng thông/bộ nhớ.

### 2.2. Base64 bảo toàn byte, không tự bảo toàn “ký tự” nếu dùng sai charset

~~~java
String input = "Tiếng Việt";
byte[] bytes = input.getBytes(StandardCharsets.UTF_8);

String encoded =
    Base64.getEncoder().encodeToString(bytes);

byte[] decoded =
    Base64.getDecoder().decode(encoded);

String restored = new String(decoded, StandardCharsets.UTF_8);
~~~

Đây là **đoạn minh họa**, cần import `Base64` và `StandardCharsets`. `restored.equals(input)` là true.

Bước `String → byte[]` và `byte[] → String` cần **cùng charset**. Dùng `getBytes()` không có tham số và `new String(bytes)` không chỉ định charset có thể phụ thuộc default charset của môi trường. Với giao thức, nên chỉ định `StandardCharsets.UTF_8`.

**Không chuyển binary tùy ý qua `new String(binaryBytes, UTF_8)` rồi lấy lại byte**. Một số chuỗi byte không hợp lệ theo UTF-8 có thể bị thay bằng ký tự replacement, khiến dữ liệu bị biến đổi. Base64 làm cầu nối *byte[] → ASCII text → byte[]*, không phải cầu nối chuyển mọi byte thành “chuỗi Unicode có nghĩa”.

## 3. API Base64 trong Java 8

Java cung cấp class tiện ích:

~~~java
import java.util.Base64;

Base64.Encoder encoder = Base64.getEncoder();
Base64.Decoder decoder = Base64.getDecoder();
~~~

`Base64.Encoder` và `Base64.Decoder` có các phương thức cho `byte[]`, `String` và một số dạng buffer/stream. Chúng phù hợp tái sử dụng theo hợp đồng Java hiện hành; không cần tự viết một bảng chuyển đổi byte thành 6-bit.

### 3.1. Basic Base64

~~~java
byte[] original = "Man".getBytes(StandardCharsets.UTF_8);

String text = Base64.getEncoder().encodeToString(original);
byte[] bytes = Base64.getDecoder().decode(text);

// text.equals("TWFu") == true
// Arrays.equals(original, bytes) == true
~~~

Basic dùng `+` và `/`, không tự chèn xuống dòng. `getDecoder()` **từ chối ký tự không thuộc alphabet** của Basic (và padding không hợp lệ). Với input hỏng, nó có thể ném `IllegalArgumentException`.

**Không nhất thiết mọi chuỗi thiếu dấu `=` đều bị từ chối.** Java Base64 decoder chấp nhận một số dạng **không padding** có cấu trúc hợp lệ. Nếu một giao thức yêu cầu dạng canonical đặc biệt, phải **kiểm tra quy tắc dạng văn bản** ở cấp giao thức; đừng đánh đồng việc decoder chấp nhận với mọi yêu cầu normalization/canonicalization.

### 3.2. URL-safe Base64

~~~java
byte[] binary = {
    (byte) 0xFB, (byte) 0xFF, (byte) 0xFF
};

String basic = Base64.getEncoder().encodeToString(binary);
String url = Base64.getUrlEncoder().encodeToString(binary);

// basic = "+///"
// url   = "-___"
~~~

Trong Base64url (RFC 4648), ký tự `+` được thay bằng `-` và `/` được thay bằng `_`. Đó là **biến thể bảng chữ cái**, không phải “Base64 dùng khóa URL”.

~~~java
String compact = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString("M".getBytes(StandardCharsets.UTF_8));

// compact = "TQ"
String restored = new String(
    Base64.getUrlDecoder().decode(compact),
    StandardCharsets.UTF_8
);
// restored = "M"
~~~

`withoutPadding()` bỏ `=` ở cuối **khi encode**. `Base64.getUrlDecoder()` là decoder tương ứng. Tránh trộn Basic decoder với Base64url khi chuỗi có `-` hoặc `_`.

**Base64url không thay cho URL encoding toàn bộ URL.** Nó chỉ làm cho **phần dữ liệu đã encode** có alphabet URL-safe hơn; đường dẫn/query/cấu trúc URL còn có quy tắc percent-encoding, phân tách và validation riêng.

### 3.3. MIME Base64

~~~java
Base64.Encoder mimeEncoder = Base64.getMimeEncoder();
Base64.Decoder mimeDecoder = Base64.getMimeDecoder();
~~~

Biến thể MIME phù hợp nội dung email MIME. Encoder mặc định chia dòng dài tối đa 76 ký tự, thường với `CRLF`. Decoder MIME **bỏ qua ký tự không thuộc bảng Base64** theo hợp đồng MIME. Đây là khác biệt rất quan trọng khi xử lý dữ liệu không tin cậy.

Nếu ứng dụng API/security cần kiểm tra định dạng nghiêm ngặt, **đừng tự chọn MIME decoder chỉ vì nó “dễ giải mã mọi đầu vào”**. Việc bỏ qua nhiều ký tự ngoài alphabet có thể làm hai chuỗi văn bản khác nhau được hiểu thành cùng dữ liệu; điều đó nguy hiểm nếu code có bước xác minh/so sánh/log ở dạng text trước khi decode.

### 3.4. Bảng quyết định dạng Base64

| Dạng | Java encoder/decoder | Alphabet/format | Khi dùng |
| --- | --- | --- | --- |
| Basic | `getEncoder/getDecoder` | `A-Za-z0-9+/`, padding thông thường, không thêm line breaks | JSON property chứa binary, file nội dung Base64, giao thức chấp nhận Basic |
| URL-safe | `getUrlEncoder/getUrlDecoder` | `A-Za-z0-9-_`, có thể bỏ padding theo schema | URL-safe token representation, phần text phù hợp URL/filename |
| MIME | `getMimeEncoder/getMimeDecoder` | Basic alphabet, có line breaks MIME, decoder bỏ qua ký tự ngoài alphabet | Email MIME và cấu trúc MIME theo chuẩn |

Luôn chọn dạng theo **định dạng của bên gửi/bên nhận**, không đoán theo “trông giống Base64”.

## 4. Base64 không che được dữ liệu

Ai có chuỗi `TWFu` chỉ cần:

~~~java
String text = new String(
    Base64.getDecoder().decode("TWFu"),
    StandardCharsets.UTF_8);

System.out.println(text); // Man
~~~

Không có khóa, không có bước “xác thực người giải mã”. Đây là nguyên nhân Base64 **không đủ** cho:

- Mật khẩu, mã OTP, câu trả lời khôi phục tài khoản.
- Số thẻ, thông tin định danh, tài liệu cá nhân.
- Private key, secret API key, refresh token.
- Giá trị quyền như `isAdmin`, `role`, `tenantId` hoặc số tiền cần chống sửa.
- Cookie hoặc tham số URL mà server định tin từ người dùng.

### 4.1. Không bảo vệ quyền hạn bằng cách Base64-encode JSON

Ví dụ **thiết kế sai**:

~~~text
Server gửi Base64 của JSON:
{"user":"u1","role":"user"}

Client giải mã, sửa role thành "admin", Base64-encode lại.
Server chỉ decode rồi tin role => lỗi xác thực/ủy quyền.
~~~

Một biến thể của dữ liệu “trông vô nghĩa” không phải **tamper protection**. Server cần lấy quyền từ hệ tin cậy hoặc xác minh một chữ ký/MAC hợp lệ trên thông tin được phép do client giữ, rồi vẫn áp chính sách phân quyền.

### 4.2. Base64 có làm dữ liệu “an toàn để log” không?

Không. Log Base64 của access token hoặc thông tin khách hàng vẫn là **log bí mật**, chỉ khác cách biểu diễn. Người đọc log có thể decode ngay. Tương tự, chuỗi Basic Authorization trong header có thể giải mã ra cặp thông tin đăng nhập. Cần redaction, phân quyền log, thời hạn lưu và quản lý secret theo chính sách.

### 4.3. Base64 cũng không chống replay

Nếu một attacker lấy được một token hợp lệ, việc token được chuyển thành Base64url không ngăn họ gửi lại. Để chống replay, cần thiết kế riêng: expiration, nonce/challenge, binding với kênh/thiết bị, idempotency, token revocation hoặc cơ chế hợp lệ theo giao thức. Không dùng độ dài/độ phức tạp nhìn thấy của chuỗi Base64 làm bằng chứng token chống replay.

## 5. Encryption: có khóa, có mục tiêu giữ bí mật

Mã hóa bảo mật biến plaintext thành ciphertext bằng thuật toán mật mã và khóa. Bên không có khóa hợp lệ **không thể dễ dàng khôi phục plaintext** khi thuật toán và cách dùng đủ mạnh.

~~~text
plaintext --[encrypt + secret key + nonce]--> ciphertext + tag
ciphertext + tag --[decrypt + đúng key + nonce]--> plaintext

ciphertext/nonce/tag --Base64url--> text để đưa vào JSON/URL
text --Base64url decode--> ciphertext/nonce/tag
~~~

Trong sơ đồ này, **Base64 chỉ là lớp đóng gói bên ngoài**. Nếu chỉ dùng phép Base64 ở bước đầu mà không có encrypt, thông tin vẫn công khai.

### 5.1. Vì sao nên ưu tiên AES-GCM cho ví dụ Java?

`AES/GCM/NoPadding` là một cơ chế **AEAD** (*Authenticated Encryption with Associated Data*) được Java hỗ trợ: nó mã hóa và tạo **authentication tag**. Khi decrypt, JCE kiểm tra tag; nếu ciphertext, AAD hoặc thông tin khóa/nonce không đúng, phép giải mã sẽ thất bại.

- **Key:** bí mật, phải quản lý cẩn thận.
- **IV/nonce:** không nhất thiết bí mật, nhưng phải **độc nhất đối với cùng key** theo quy tắc GCM. Một nonce bị dùng lại với cùng key có thể gây hậu quả nghiêm trọng.
- **AAD:** dữ liệu không được mã hóa nhưng được xác thực bởi tag, chẳng hạn record ID, tenant, loại thông điệp hoặc version.
- **Authentication tag:** giúp phát hiện sửa đổi, thường dùng độ dài 128 bit trong ví dụ.
- **Ciphertext:** byte mã hóa; có thể Base64-encode để vận chuyển.

`AES/GCM/NoPadding` là tên transformation; `NoPadding` ở đây **không liên quan** đến ký tự `=` của Base64. Hai từ “padding” nói về **hai tầng hoàn toàn khác nhau**.

### 5.2. Nonce không được dùng lại với cùng key

Ví dụ Java sử dụng nonce 12 byte được tạo bằng `SecureRandom` cho mỗi lần mã hóa và một AES key 128-bit ngẫu nhiên. Với lượng dữ liệu lớn, hệ thống thực phải theo dõi **giới hạn số lần sử dụng key, xác suất nonce collision, chiến lược cấp nonce độc nhất và key rotation**. Không được hard-code một IV 12 byte rồi dùng lại cho mọi record.

**Không làm như sau:**

~~~java
// PHẢN VÍ DỤ bảo mật, không dùng trong sản phẩm:
byte[] fixedIv = new byte[12];
// Dùng lại fixedIv với cùng AES-GCM key cho nhiều messages!
~~~

Việc ngẫu nhiên hóa mỗi nonce chỉ là một cách quản lý; tại quy mô rất lớn, cần chính sách đảm bảo uniqueness thích hợp, không chỉ hy vọng không đụng.

### 5.3. Không tự viết thuật toán mã hóa riêng

Không tạo một “encryption” bằng cách XOR với một chuỗi mật khẩu, đảo thứ tự byte, rotate bits rồi Base64, hoặc “encode nhiều lần”. Những phép này không cung cấp mức bảo mật tương đương thuật toán đã được kiểm định.

Ứng dụng production nên dùng thư viện/primitive được duy trì, API cấp cao thích hợp và hệ quản lý khóa (KMS/HSM/secret manager) theo threat model. Đoạn JCE bên dưới để **minh họa khác biệt Base64 và encryption**, không thay thế quy trình thiết kế cryptographic envelope versioning, key management và audit.

## 6. Hashing: một chiều, không bảo vệ tính bí mật của plaintext

Hash mật mã như SHA-256 biến input thành digest có độ dài cố định:

~~~java
byte[] digest = MessageDigest.getInstance("SHA-256")
    .digest(messageBytes);

String printableHash = Base64.getEncoder()
    .encodeToString(digest);
~~~

Đây là đoạn **minh họa**, cần `MessageDigest`, `Base64` và `messageBytes` do ứng dụng cung cấp. Mã **Base64-encode digest** chỉ để có một chuỗi tiện vận chuyển; digest vẫn là giá trị hash, không phải ciphertext.

- Hash không có phép **decrypt** để lấy lại input theo cách dùng chuẩn.
- SHA-256 là hash nhanh, phù hợp nhiều mục tiêu checksum/digest; **không** phải cách lưu mật khẩu hiện đại.
- Một hash công khai **không chứng minh người gửi đáng tin**: nếu attacker sửa dữ liệu, họ có thể tính lại hash và gửi hash mới.
- Nếu input có entropy thấp (mật khẩu ngắn, mã PIN, role), attacker có thể thử nhiều giá trị rồi so digest.

Đừng nghĩ “không thể giải mã SHA-256” đồng nghĩa “ai đó không thể đoán được mật khẩu”. An toàn mật khẩu phụ thuộc thuật toán chuyên dụng và thông số cost.

### 6.1. Lưu mật khẩu: Argon2id hoặc lựa chọn được khuyến nghị

Mật khẩu **không nên lưu ở dạng plaintext, Base64 hoặc SHA-256 thuần**. Theo hướng dẫn OWASP hiện hành, ưu tiên **Argon2id** với cấu hình memory/time/parallelism phù hợp; có thể dùng **scrypt** khi phù hợp, **PBKDF2** trong môi trường cần tương thích/FIPS theo hướng dẫn và tham số đủ mạnh. Mỗi mật khẩu có **salt riêng** và cấu hình cost được theo dõi/điều chỉnh.

Lưu trữ mật khẩu đúng thường gồm:

~~~text
password + per-password random salt
  --[password hashing/KDF với cost]--> password verifier

Khi đăng nhập:
password được nhập + salt đã lưu
  --[cùng thuật toán/tham số]--> so khớp verifier
~~~

Không “giải mã” password verifier. Không dùng AES-GCM để lưu mật khẩu đăng nhập chỉ nhằm sau này lấy lại plaintext nếu không có yêu cầu đặc biệt; thiết kế an toàn ưu tiên xác minh một chiều.

**Lưu ý Java:** JDK có `SecretKeyFactory` và một số thuật toán PBKDF2; Argon2id/scrypt thường cần thư viện phù hợp. Không giả định `java.util.Base64` hay `MessageDigest.getInstance("SHA-256")` đã cung cấp cơ chế password hashing an toàn.

## 7. HMAC và chữ ký số: xác minh nhưng không giấu nội dung

### 7.1. HMAC

HMAC kết hợp dữ liệu với **khóa bí mật dùng chung**, ví dụ `HmacSHA256`. Người có khóa có thể tạo/kiểm tra tag hợp lệ. Nếu dữ liệu bị sửa mà attacker không biết khóa, tag mới hợp lệ sẽ khó tạo.

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secretKeyBytes, "HmacSHA256"));

byte[] tag = mac.doFinal(messageBytes);
String tagText = Base64.getEncoder().encodeToString(tag);
~~~

Đây là **mã minh họa**: cần imports `javax.crypto.Mac`, `SecretKeySpec`, `Base64` và byte arrays do ứng dụng cung cấp. Tag có thể Base64-encode để đưa vào HTTP header/JSON; **đó là HMAC tag dưới dạng text**, không phải Base64 tự tạo tính toàn vẹn.

Trong production, cần quy tắc canonicalization rõ cho dữ liệu ký/MAC (HTTP method, path, body bytes, timestamp, nonce...), quản lý key, chính sách hết hạn/chống replay và so sánh tag đúng cách. Với giá trị MAC dự kiến do server tự tính, có thể dùng `MessageDigest.isEqual(expectedTag, receivedTag)` thay vì so sánh chuỗi qua `String.equals` không được thiết kế làm primitive so sánh mật mã.

**HMAC không giấu plaintext.** Nếu body vẫn công khai, mọi người có thể đọc; chỉ bên có khóa hợp lệ mới tạo tag xác minh được theo giả định mật mã.

### 7.2. Chữ ký số

Chữ ký số dùng **private key để ký** và **public key để xác minh**; bên xác minh không cần nắm private key. Chữ ký giúp integrity/authenticity theo mô hình trust/certificate phù hợp, nhưng **không tự mã hóa nội dung**.

Nếu một JWT dùng dạng JWS (ký), các phần header và payload được **Base64url-encode** nên vẫn có thể đọc bởi bên sở hữu token. Cần **xác minh chữ ký**, thuật toán được phép, issuer, audience, expiration và claims trước khi tin dữ liệu. Nếu muốn JWT có phần nội dung được giữ bí mật, cần mô hình **JWE** hoặc một thiết kế token khác; Base64url của JWS payload không phải encryption.

Không tự viết phép xác minh chữ ký bằng cách “decode payload rồi kiểm tra role”, cũng không mặc định mọi token có ba phần văn bản đều là token hợp lệ.

## 8. Các tình huống thực tế: chọn công cụ đúng

| Nhu cầu | Cơ chế đề xuất | Base64 đóng vai trò gì? |
| --- | --- | --- |
| Gửi hình ảnh/byte trong trường JSON text | Base64 Basic hoặc Base64url theo schema | Chuyển binary sang text |
| Gửi dữ liệu trong URL-safe token representation | Base64url theo giao thức | Chuyển byte sang alphabet URL-safe |
| Giữ bí mật thông tin người dùng khi lưu | Mã hóa có xác thực như AES-GCM + quản lý key | Có thể encode ciphertext/nonce/tag để lưu dưới dạng String |
| Bảo vệ HTTP traffic khỏi nghe lén | **HTTPS/TLS** đúng cấu hình | Không phải lớp bảo mật vận chuyển |
| Chống sửa message giữa các service có shared key | HMAC hoặc AEAD tùy có cần bí mật không | Encode tag/envelope nếu giao thức dùng text |
| Xác minh nguồn gửi bằng cặp private/public key | Chữ ký số | Encode chữ ký nếu cần text |
| Lưu verifier mật khẩu | Password hashing/KDF có salt/cost | Có thể encode blob salt/hash để lưu, không thay hashing |
| Kiểm tra file bị thay đổi trong môi trường tin cậy | Hash/digest như SHA-256 | Có thể encode digest thành String |
| Phát hiện file bị sửa bởi attacker biết cả file và hash công khai | MAC/chữ ký số trên digest/nội dung | Chỉ biểu diễn tag/signature |
| Lưu phân quyền trong cookie client-side | Server-side session hoặc token được MAC/ký và kiểm tra | Có thể là lớp serialization, không phải trust boundary |
| Giới hạn truy cập dữ liệu trên backend | Authorization và access control | Không có tác dụng cấp quyền |

**Nguyên tắc tổng quát:** Base64 là **transport/serialization format**, còn các yêu cầu bí mật, tính toàn vẹn, xác thực và phân quyền phải được giải quyết ở **tầng an ninh tương ứng**.

## 9. Chương trình Java hoàn chỉnh: Base64 so với AES-GCM và HMAC

Chương trình **`Base64VsEncryptionDemo.java`** sau đây minh họa:

1. Basic Base64, URL-safe Base64, padding và round-trip UTF-8.
2. Decoder Basic từ chối ký tự không hợp lệ.
3. Một người không có khóa vẫn tự Base64-encode/giải mã một claim `role`.
4. SHA-256 tạo digest 32 byte nhưng không giấu dữ liệu.
5. HMAC-SHA256 tạo tag bằng secret, xác minh tag đúng và phát hiện sửa input.
6. AES-GCM mã hóa plaintext với **AES-128 key ngẫu nhiên**, **IV 12 byte ngẫu nhiên**, **authentication tag 128 bit**, AAD gắn ngữ cảnh.
7. Chỉ **sau khi encrypt**, lấy envelope `IV || ciphertext || tag` rồi Base64url-encode để vận chuyển. Decode và decrypt lại đúng.
8. Sửa một byte tag hoặc thay AAD khiến phép decrypt báo `AEADBadTagException`.
9. Output chỉ in các kết quả cố định/boolean, không in secret key, nonce, ciphertext ngẫu nhiên hoặc dữ liệu nhạy cảm.

Toàn bộ API mã dùng có từ **Java 8**, biên dịch/chạy được bằng JDK 17+ với nhà cung cấp mật mã chuẩn hỗ trợ AES-GCM. **Đây là ví dụ giáo dục**: trong sản phẩm thật cần envelope có version, key ID, key rotation, hạn mức nonce và quản lý secret thích hợp.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class Base64VsEncryptionDemo {

    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    private Base64VsEncryptionDemo() {
    }

    // Trả IV(12) || ciphertext || GCM tag(16).
    private static byte[] encrypt(
            byte[] clear,
            SecretKey key,
            byte[] aad) throws GeneralSecurityException {

        byte[] iv = new byte[IV_BYTES];
        RANDOM.nextBytes(iv); // IV mới cho mỗi lần encrypt.

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, iv));

        // AAD phải được cung cấp trước doFinal.
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(clear);

        return ByteBuffer.allocate(
                iv.length + ciphertextAndTag.length)
                .put(iv)
                .put(ciphertextAndTag)
                .array();
    }

    private static byte[] decrypt(
            byte[] envelope,
            SecretKey key,
            byte[] aad) throws GeneralSecurityException {

        if (envelope.length < IV_BYTES + TAG_BITS / 8) {
            throw new IllegalArgumentException("invalid envelope");
        }

        byte[] iv = Arrays.copyOfRange(
                envelope, 0, IV_BYTES);
        byte[] ciphertextAndTag = Arrays.copyOfRange(
                envelope, IV_BYTES, envelope.length);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, iv));

        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    private static byte[] hmacSha256(
            byte[] data,
            byte[] secret) throws GeneralSecurityException {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(data);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        System.out.println("basicMan="
                + Base64.getEncoder().encodeToString(
                    "Man".getBytes(StandardCharsets.UTF_8)));

        System.out.println("basicM="
                + Base64.getEncoder().encodeToString(
                    "M".getBytes(StandardCharsets.UTF_8)));

        byte[] binary = {
                (byte) 0xFB, (byte) 0xFF, (byte) 0xFF
        };
        String basic = Base64.getEncoder()
                .encodeToString(binary);
        String url = Base64.getUrlEncoder()
                .encodeToString(binary);

        System.out.println("basicBinary=" + basic);
        System.out.println("urlBinary=" + url);
        System.out.println("urlRoundTrip="
                + Arrays.equals(
                    binary, Base64.getUrlDecoder().decode(url)));

        String withoutPadding = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(
                    "M".getBytes(StandardCharsets.UTF_8));

        System.out.println("urlNoPadding=" + withoutPadding);
        System.out.println("noPaddingRoundTrip="
                + "M".equals(new String(
                    Base64.getUrlDecoder().decode(withoutPadding),
                    StandardCharsets.UTF_8)));

        String vietnamese = "Tiếng Việt";
        byte[] utf8 = vietnamese.getBytes(StandardCharsets.UTF_8);
        String encodedUtf8 = Base64.getEncoder()
                .encodeToString(utf8);

        System.out.println("utf8RoundTrip="
                + vietnamese.equals(new String(
                    Base64.getDecoder().decode(encodedUtf8),
                    StandardCharsets.UTF_8)));

        boolean malformedRejected = false;
        try {
            Base64.getDecoder().decode("T@Fu");
        } catch (IllegalArgumentException ex) {
            malformedRejected = true;
        }
        System.out.println("malformedRejected="
                + malformedRejected);

        // Ai cũng có thể encode claim do họ tự tạo.
        String forged = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(
                    "role=admin".getBytes(StandardCharsets.UTF_8));

        String decodedClaim = new String(
                Base64.getUrlDecoder().decode(forged),
                StandardCharsets.UTF_8);

        System.out.println("attackerCanReencodeRole="
                + "role=admin".equals(decodedClaim));

        byte[] message =
                "Xin chào Java 8".getBytes(StandardCharsets.UTF_8);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(message);
        System.out.println("sha256Bytes=" + digest.length);

        // HMAC có secret, Base64 chỉ là cách hiển thị tag.
        byte[] macSecret = new byte[32];
        RANDOM.nextBytes(macSecret);

        byte[] tag = hmacSha256(message, macSecret);
        byte[] changedMessage = message.clone();
        changedMessage[0] ^= 1;

        System.out.println("hmacBytes=" + tag.length);
        System.out.println("hmacValid="
                + MessageDigest.isEqual(
                    tag, hmacSha256(message, macSecret)));
        System.out.println("hmacRejectsChange="
                + !MessageDigest.isEqual(
                    tag, hmacSha256(changedMessage, macSecret)));

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, RANDOM);
        SecretKey aesKey = generator.generateKey();

        byte[] aad = "record-id:42|v1"
                .getBytes(StandardCharsets.UTF_8);

        byte[] envelope = encrypt(message, aesKey, aad);
        String tokenText = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(envelope);

        byte[] received = Base64.getUrlDecoder()
                .decode(tokenText);
        byte[] clear = decrypt(received, aesKey, aad);

        System.out.println("gcmRoundTrip="
                + Arrays.equals(message, clear));
        System.out.println("envelopeLengthExpected="
                + (envelope.length
                   == message.length + IV_BYTES + TAG_BITS / 8));
        System.out.println("envelopeTextUrlSafe="
                + tokenText.matches("[A-Za-z0-9_-]+"));

        // Đổi 1 bit của tag để mô phỏng sửa ciphertext.
        byte[] tampered = envelope.clone();
        tampered[tampered.length - 1] ^= 1;

        boolean tamperRejected = false;
        try {
            decrypt(tampered, aesKey, aad);
        } catch (AEADBadTagException ex) {
            tamperRejected = true;
        }
        System.out.println("tamperRejected=" + tamperRejected);

        boolean wrongAadRejected = false;
        try {
            decrypt(envelope, aesKey,
                "record-id:99|v1".getBytes(StandardCharsets.UTF_8));
        } catch (AEADBadTagException ex) {
            wrongAadRejected = true;
        }
        System.out.println("wrongAadRejected="
                + wrongAadRejected);
    }
}
~~~

### Lệnh biên dịch và chạy

~~~bash
javac -encoding UTF-8 Base64VsEncryptionDemo.java
java Base64VsEncryptionDemo
~~~

### Kết quả đầu ra kỳ vọng

~~~text
basicMan=TWFu
basicM=TQ==
basicBinary=+///
urlBinary=-___
urlRoundTrip=true
urlNoPadding=TQ
noPaddingRoundTrip=true
utf8RoundTrip=true
malformedRejected=true
attackerCanReencodeRole=true
sha256Bytes=32
hmacBytes=32
hmacValid=true
hmacRejectsChange=true
gcmRoundTrip=true
envelopeLengthExpected=true
envelopeTextUrlSafe=true
tamperRejected=true
wrongAadRejected=true
~~~

### Vì sao không in ciphertext và secret key?

AES key và IV của ví dụ được tạo ngẫu nhiên. Vì vậy, **ciphertext và Base64url token thật thay đổi giữa các lần chạy**. Nếu in chúng rồi tuyên bố một chuỗi cố định là expected stdout sẽ sai. Thay vào đó, chương trình kiểm tra:

- Round-trip Base64 và UTF-8 cho kết quả cố định.
- Basic và Base64url có hai alphabet khác nhau với cùng `byte[]`.
- Hash SHA-256 luôn dài 32 byte; HMAC-SHA256 tag trong ví dụ cũng 32 byte.
- HMAC xác minh đúng thông điệp ban đầu; thay một byte của message khiến tag mới khác tag cũ.
- AES-GCM decrypt với đúng key, IV, AAD và tag khôi phục plaintext.
- Envelope gồm **12 byte IV + đúng số byte plaintext + 16 byte GCM tag**, nên chiều dài đáp ứng quan hệ đã kiểm tra.
- Base64url của envelope chỉ chứa ký tự thuộc alphabet dùng trong ví dụ.
- Sửa tag và thay AAD bị phát hiện khi xác thực, biểu hiện qua `AEADBadTagException`.

Về mật mã, việc một thông điệp giả mạo ngẫu nhiên vượt được kiểm tra tag có xác suất cực nhỏ theo kích thước tag, nhưng ví dụ cố ý **đổi một bit trên tag của cùng ciphertext**, nên tag xác thực không còn trùng tag được tính cho thông điệp ban đầu. Java JCE từ chối phép decrypt trước khi trả plaintext cho caller.

### 9.1. Thứ tự bước quan trọng

~~~text
Sender:
plaintext bytes
 -> AES-GCM encrypt(key, fresh nonce, AAD)
 -> nonce + ciphertext + tag
 -> Base64url-encode
 -> text transport

Receiver:
text transport
 -> Base64url-decode
 -> tách nonce và ciphertext+tag
 -> AES-GCM decrypt(key, same AAD)
 -> verified plaintext bytes
 -> UTF-8 decode nếu plaintext được định nghĩa là text
~~~

**Không đảo vị trí để nghĩ rằng “Base64 trước rồi AES” tạo thêm bảo mật.** Base64 trước encryption chỉ tăng kích thước dữ liệu đầu vào (nếu không có lý do giao thức); lớp Base64 hữu ích nhất ở đây là để chuyển **envelope nhị phân sau mã hóa** thành text.

### 9.2. Định dạng envelope trong production

Ví dụ đơn giản chỉ lưu `IV || ciphertext || tag`. Hệ thống thật nên định nghĩa rõ:

- **Version** của envelope và thuật toán/parameters được hỗ trợ.
- **Key identifier** để tìm đúng khóa trong KMS khi key rotation.
- Kích thước IV/tag và cách parse; giới hạn chiều dài trước khi cấp phát.
- **AAD** ràng buộc bản ghi, tenant, mục đích sử dụng, schema version.
- Cơ chế bảo đảm **nonce uniqueness** với cùng key, số lượng bản mã mỗi key.
- Quy tắc xử lý thất bại: không tiết lộ nội dung/secret hoặc phân biệt quá chi tiết cho attacker qua thông báo lỗi.
- Quyền truy cập tới KMS, logging/monitoring, backup và chính sách xóa khóa.

Ví dụ tự viết chỉ để học nguyên tắc, **không nên coi là thư viện mã hóa hoàn chỉnh**.

## 10. Base64 trong HTTP Basic Authorization

Header Basic Authorization có thể biểu diễn cặp `username:password` dưới dạng Base64, ví dụ:

~~~text
Authorization: Basic <chuỗi Base64 của "user:password">
~~~

Đây là **cú pháp minh họa**, không phải header chứa credential thật. Một attacker có thể decode value từ header nếu bắt được nó. Vì vậy HTTP Basic phải được sử dụng trên **HTTPS/TLS** và cần cơ chế kiểm soát credential phù hợp.

**HTTPS/TLS mới bảo vệ việc truyền tải**, không phải Base64. Kể cả khi có TLS, đừng ghi nguyên header Authorization vào logs, error traces, analytics, hoặc gửi cho domain không tin cậy. Với hệ thống cần xác thực hiện đại, cân nhắc session/OAuth/OIDC phù hợp thay vì gửi user password ở mọi request nếu có lựa chọn tốt hơn.

### 10.1. Đừng nhầm URL-safe encoding với HTTPS

`Base64.getUrlEncoder()` chỉ thay alphabet để tránh `+` và `/` ở dữ liệu đã encode. Nó **không tạo TLS tunnel**, không chứng thực server, không che query string khỏi log hoặc lịch sử trình duyệt. URL-safe chỉ nói về **tính tương thích khi biểu diễn**, không phải tính bảo mật.

## 11. JWT, cookies và các chuỗi “trông bí mật”

Một chuỗi có nhiều dấu chấm và các đoạn Base64url thường khiến người mới học nghĩ rằng nội dung đã được giấu. Với JWT dùng **JWS**, header/payload có thể decode để đọc claims mà không cần secret. Mục tiêu của chữ ký nằm ở việc **xác minh claims chưa bị sửa và được ký bởi khóa tin cậy**.

Các quy tắc:

1. **Không lưu secret trong JWT payload mà mong Base64url giấu nó.**
2. **Không tin `role`/`scope` chỉ vì parse JSON thành công.** Phải xác minh chữ ký hoặc MAC theo implementation tin cậy, whitelist thuật toán, issuer, audience, expiration và những điều kiện liên quan.
3. **Không tự implement JWT validation bằng vài dòng Base64 decoding.** Dùng thư viện được duy trì và cấu hình an toàn.
4. **Không đồng nhất chữ ký với encryption.** JWS payload thường đọc được; nếu cần bí mật, dùng JWE hoặc token opaque và lưu thông tin nhạy cảm ở server.
5. **Không đặt token trong URL nếu có thể tránh**, vì URL dễ lọt vào history, referrer, analytics và logs; tuân thủ best practices giao thức.

**Cookie** có thể được Base64-encode hoặc serialize theo nhiều cách. Chỉ có dạng Base64 không làm cookie chống sửa. Các thuộc tính `Secure`, `HttpOnly`, `SameSite`, session binding, signature/encryption và CSRF policy giải quyết các rủi ro khác nhau; không thay thế lẫn nhau.

## 12. Những lỗi nghiêm trọng khi nhầm Base64 với bảo mật

### Lỗi 1 — Lưu mật khẩu dưới dạng Base64

~~~java
String stored = Base64.getEncoder().encodeToString(
    password.getBytes(StandardCharsets.UTF_8));
~~~

Đây là **phản ví dụ**, không dùng trong sản phẩm. Ai lấy được `stored` có thể decode ra password nguyên văn. Cần password hashing hiện đại với salt và cost theo hướng dẫn OWASP.

### Lỗi 2 — “Mã hóa hai/ba lần” bằng Base64

~~~text
plaintext -> Base64 -> Base64 -> Base64
~~~

Tất cả các bước đều đảo ngược được công khai. Lặp lại không thêm khóa hay thuộc tính mật mã; chỉ làm output dài hơn và khó đọc bằng mắt.

### Lỗi 3 — Xem việc decode thành công là xác minh dữ liệu

Decoder chỉ kiểm tra **cú pháp encoding**, không xác minh nguồn dữ liệu. Một chuỗi Base64 hợp lệ vẫn có thể chứa dữ liệu giả mạo hoặc payload độc hại. Sau decode vẫn phải validate schema, độ dài, kiểu, quyền và provenance.

### Lỗi 4 — Dùng hash công khai như HMAC

~~~text
body + SHA-256(body)   không đủ bảo đảm body do bên tin cậy gửi.
~~~

Attacker có thể sửa body rồi tính lại SHA-256. Với integrity/authenticity chống giả mạo, cần **keyed MAC** hoặc chữ ký số, hoặc AEAD nếu cần cả bảo mật nội dung.

### Lỗi 5 — Dùng SHA-256 thuần để lưu mật khẩu

SHA-256 nhanh khiến attacker thử nhiều giả thuyết mật khẩu với chi phí thấp. Chọn Argon2id/scrypt/PBKDF2 phù hợp, salt mỗi mật khẩu, cost đủ mạnh và chính sách chống brute force ở tầng đăng nhập.

### Lỗi 6 — Dùng AES ở chế độ không có xác thực mà tưởng có integrity

Không phải mode nào của AES cũng cho authentication. **AES-GCM** khi dùng đúng giúp kiểm tra tag; tự dùng AES-ECB là thiết kế không phù hợp cho dữ liệu thông thường. Với mode không có authentication, phải có phương án xác thực tách biệt được thiết kế chính xác. Tránh phát minh giao thức mật mã riêng.

### Lỗi 7 — Dùng lại IV/nonce trong AES-GCM

Dùng lại IV với cùng key có thể phá nghiêm trọng tính bảo mật/xác thực. Dùng `SecureRandom` hoặc chính sách nonce uniqueness được kiểm chứng; lưu/đưa nonce cùng ciphertext (nonce thường không cần bí mật) và quản lý lifecycle key.

### Lỗi 8 — Hard-code AES/HMAC secret vào source code

Secret trong repository, cấu hình công khai hoặc log dễ rò rỉ. Quản lý bằng KMS/secret manager hoặc cơ chế an toàn phù hợp; có rotation, access control và audit.

### Lỗi 9 — Mã hóa dữ liệu nhưng đưa key cùng ciphertext ở một nơi không bảo vệ

Nếu attacker có cả ciphertext và key giải mã, encryption mất ý nghĩa. Key phải được quản lý qua một trust boundary thích hợp; thiết kế tách key khỏi data ở mức phù hợp theo threat model.

### Lỗi 10 — Đánh đồng Base64url với URL percent-encoding

Base64url cho **dữ liệu biểu diễn** dễ dùng trong URL, không tự encode cấu trúc URL. Query parameter, Unicode path, reserved characters và delimiter vẫn cần xử lý đúng theo URI/HTTP API.

### Lỗi 11 — Dùng MIME decoder như validator nghiêm ngặt

MIME decoder có thể bỏ qua các ký tự không thuộc Base64 alphabet. Với input bảo mật, nếu giao thức yêu cầu strict/canonical encoding, phải chọn decoder và bước validation phù hợp.

### Lỗi 12 — Không giới hạn kích thước input Base64

Một string Base64 khổng lồ có thể buộc server cấp phát nhiều byte khi decode, làm tăng tải CPU và bộ nhớ. Đặt **giới hạn chiều dài đầu vào**, kích thước output, timeout và quota trước khi decode/lưu/parse. Đừng dựa chỉ vào việc decoder ném IllegalArgumentException.

### Lỗi 13 — Đưa binary bất kỳ qua String UTF-8 trước khi Base64

~~~java
// PHẢN VÍ DỤ cho byte tùy ý:
String damaged = new String(binary, StandardCharsets.UTF_8);
byte[] roundTrip = damaged.getBytes(StandardCharsets.UTF_8);
~~~

Nếu `binary` có các chuỗi byte UTF-8 không hợp lệ, quá trình chuyển sang String có thể thay byte, dẫn tới dữ liệu không còn nguyên vẹn. Encode **byte[] trực tiếp** bằng Base64.

### Lỗi 14 — Không chỉ định charset

`getBytes()`/`new String(bytes)` không chỉ định charset có thể phụ thuộc default charset của runtime, đặc biệt khi ứng dụng chạy trên nhiều phiên bản Java hoặc OS. Chọn `StandardCharsets.UTF_8` rõ ràng.

### Lỗi 15 — Coi dấu `=` là tín hiệu mã hóa bảo mật

Dấu `=` chỉ là padding theo cấu trúc encoding. Bỏ padding với `withoutPadding` không làm dữ liệu khó giải mã, và không phải chữ ký.

### Lỗi 16 — Thay Basic bằng URL encoder rồi vẫn dùng Basic decoder

Các byte có index 62/63 dùng ký tự `+`/`/` trong Basic nhưng `-`/`_` trong URL-safe. Phải dùng cặp encoder/decoder tương ứng theo schema.

### Lỗi 17 — So Base64 text để chứng minh hai plaintext khác nhau

Dạng Basic/MIME/Base64url, padding/không padding và cách xử lý whitespace có thể tạo **những biểu diễn khác nhau cho cùng byte**. Nếu cần so dữ liệu gốc, decode theo giao thức rồi so byte và xác minh chữ ký/MAC trước khi tin. Nếu cần canonical token serialization, định nghĩa và enforce một dạng duy nhất.

### Lỗi 18 — In ciphertext hoặc token ra log vì nghĩ không đọc được

Ciphertext có thể cần policy bảo vệ riêng; token access còn có thể dùng để xác thực như bearer token ngay cả khi bên đọc không biết plaintext. Đừng log secret, raw Authorization header, private key hoặc token. Base64 không phải redaction.

### Lỗi 19 — Bỏ qua lỗi xác thực GCM

`AEADBadTagException` báo ciphertext/tag/AAD/key không xác minh được. Đừng catch rồi trả plaintext chưa xác thực hoặc “tiếp tục dùng một phần dữ liệu”. Decrypt AEAD **phải thành công hoàn chỉnh** trước khi tin nội dung.

### Lỗi 20 — Mất metadata của AES-GCM envelope

Base64 chỉ lưu byte; nếu không lưu hoặc truyền đúng IV, tag length, key ID/version và AAD context, receiver không thể decrypt/verify chính xác. Không phải decoder Base64 tự biết khóa hoặc kiểu cipher.

### Lỗi 21 — Tưởng mã hóa dữ liệu giải quyết luôn authorization

AES-GCM bảo vệ confidentiality/integrity khi dùng đúng, nhưng người đã được cấp key hoặc quyền truy cập vẫn cần được kiểm soát **ai được đọc record nào**. Access control, key authorization, audit và TLS không bị thay thế bởi việc tất cả giá trị đều là ciphertext.

### Lỗi 22 — Dùng thông báo lỗi giải mã làm oracle

Không trả thông tin chi tiết không cần thiết để attacker phân biệt nguyên nhân thất bại; thống nhất error handling, giới hạn retry, log nội bộ có kiểm soát và không leak secret/crypto parameters nhạy cảm qua response.

## 13. Hướng dẫn chọn encoding trên API và trong database

### JSON REST nhận byte[]
Nếu API dùng JSON text và không hỗ trợ nhị phân trực tiếp, có thể quy định:

~~~json
{
  "fileName": "report.pdf",
  "encoding": "base64",
  "content": "JVBERi0xLjQK..."
}
~~~

Đây là **JSON minh họa**, chuỗi content được viết rút gọn để giải thích schema, không phải file PDF hoàn chỉnh. Bên nhận phải giới hạn kích thước, validate định dạng, decode, xác minh file type bằng nội dung/tập luật và lưu xử lý an toàn. Trường `content` Base64 **không bảo mật file**; HTTPS/TLS bảo vệ transport, còn data-at-rest encryption/authorization tùy threat model.

### Database lưu binary
Nếu DB có cột `BLOB`/`VARBINARY` hoặc cơ chế binary tương ứng, thường có thể lưu **byte gốc** để tránh overhead Base64. Nếu phải lưu text, Base64 là lựa chọn serialization; **đừng coi cột Base64 là cột đã mã hóa bảo mật**. Với dữ liệu nhạy cảm, phải thiết kế encryption at rest/column-level encryption và key management riêng.

### Trường hợp file cấu hình
Một tệp YAML/JSON có string Base64 của API key vẫn **chứa secret thật**, không an toàn để commit vào git. Chỉ chuyển secret thành ký tự ASCII không làm mất khả năng giải mã. Dùng secret manager hoặc hệ quản lý cấu hình bí mật, và loại secret khỏi log/error reporting.

### Hệ thống gửi message
Nếu message broker truyền byte, gửi byte khi schema cho phép. Nếu schema dùng text, Base64 có thể tiện lợi nhưng tốn kích thước. Với message cần chống giả mạo giữa các service, dùng HMAC/signature hoặc AEAD theo trust boundaries; broker TLS và access control vẫn cần được cấu hình.

## 14. Phân biệt hashing, HMAC và password hashing bằng câu hỏi thiết kế

Hãy hỏi **mục tiêu của dữ liệu** trước khi chọn API:

1. **Cần đổi byte sang text để vận chuyển?** `Base64`.
2. **Cần phục hồi plaintext nhưng không cho người không có khóa đọc?** Mã hóa bảo mật, thường **AEAD** như AES-GCM.
3. **Cần kiểm tra nội dung thay đổi trong môi trường tin cậy, không cần secret?** SHA-256 digest có thể phù hợp.
4. **Cần chống attacker sửa dữ liệu khi hai bên có shared secret?** HMAC.
5. **Cần bên xác minh không nắm khóa ký?** Chữ ký số và quản lý public key/certificate.
6. **Cần lưu password để kiểm tra đăng nhập?** Password hashing/KDF có salt, cost, và defense-in-depth chống brute force.
7. **Cần bảo vệ truyền dữ liệu giữa browser và server?** HTTPS/TLS đúng cấu hình.
8. **Cần kiểm tra người dùng được phép làm gì?** Authorization ở backend, không phải Base64.

Không có API đơn lẻ đáp ứng mọi mục tiêu. Ví dụ một API lưu thông tin khách hàng có thể cần **TLS khi truyền**, **AEAD khi lưu**, **IAM/authorization khi truy cập**, và **Base64url chỉ khi đóng gói dữ liệu nhị phân trong một trường text**.

## 15. Checklist code review

- [ ] Mọi chỗ ghi “encrypt bằng Base64” đã được sửa thành “Base64 encoding” chưa?
- [ ] Có bất kỳ mật khẩu/token/secret nào chỉ được Base64-encode trước khi lưu hoặc log không?
- [ ] Mục tiêu chính là transport, confidentiality, integrity, authenticity, password verifier hay authorization?
- [ ] Đã chọn đúng Basic, URL-safe hay MIME và decoder tương ứng chưa?
- [ ] Có quy tắc padding/canonicalization rõ khi giao thức yêu cầu không?
- [ ] Có dùng `StandardCharsets.UTF_8` tường minh khi chuyển String/byte không?
- [ ] Dữ liệu binary có được encode trực tiếp từ `byte[]`, tránh round-trip qua String không phù hợp không?
- [ ] Input Base64 không tin cậy có giới hạn kích thước và xử lý `IllegalArgumentException` không?
- [ ] Có tránh MIME decoder permissive khi cần strict validation không?
- [ ] Nếu dữ liệu chứa quyền hạn/giá trị nhạy cảm do client cung cấp, server đã xác thực và phân quyền độc lập chưa?
- [ ] Nếu cần encryption, đang dùng primitive AEAD được hỗ trợ và quản lý key không?
- [ ] AES-GCM nonce có độc nhất theo key, IV mới đúng cách, tag được xác minh đầy đủ chưa?
- [ ] AAD có ràng buộc đúng record/tenant/type/version theo policy chưa?
- [ ] Envelope có version/key ID/nonce/tag format rõ và khả năng key rotation không?
- [ ] Không in raw key, access token, password, Authorization header hoặc ciphertext nhạy cảm ra log chứ?
- [ ] Nếu dùng hash để bảo đảm integrity chống attacker, có cần HMAC/chữ ký số thay vì SHA-256 public không?
- [ ] Nếu lưu password, có salt riêng, thuật toán memory-hard/work factor phù hợp theo OWASP không?
- [ ] JWT/JWS có được verify signature, issuer, audience, expiry, algorithm allowlist bằng thư viện phù hợp không?
- [ ] Có phân biệt Base64url với TLS và với URL percent-encoding không?
- [ ] Có test input rỗng, Unicode, byte tùy ý, padding, malformed alphabet và token bị sửa không?
- [ ] Có kiểm tra rằng decrypt AEAD thất bại khi tag/AAD sai, không bao giờ dùng plaintext chưa xác thực không?
- [ ] Có xem xét replay, timeout, rate limits và threat model ngoài phạm vi Base64 không?

## 16. Tổng kết và nguyên tắc ghi nhớ

**Base64 là encoding — không phải encryption.** Nó có thể biến một mảng byte thành chuỗi dễ gửi trong JSON/email/URL, nhưng **không giữ bí mật**, **không ngăn sửa dữ liệu**, **không xác minh người gửi** và **không cấp quyền truy cập**.

**Encryption** như AES-GCM dùng khóa và nonce phù hợp để bảo vệ bí mật nội dung, đồng thời dùng authentication tag để phát hiện sửa đổi. **Hashing** là một chiều nhưng SHA-256 công khai không tự xác thực nguồn gửi và không phù hợp để lưu mật khẩu. **HMAC/chữ ký số** giúp xác minh thông điệp theo mô hình khóa; **password hashing** cần salt và cost riêng; **TLS** bảo vệ kênh truyền.

Một workflow đúng thường là:

~~~text
1. Xác định mục tiêu bảo mật hoặc tương thích transport.
2. Dùng primitive bảo mật phù hợp nếu cần.
3. Chỉ Base64-encode BYTE OUTPUT của primitive khi giao thức cần TEXT.
4. Khi nhận: Base64 decode -> verify/decrypt -> validate -> authorize.
5. Không tin dữ liệu chỉ vì nó giải mã Base64 thành công.
~~~

Trong Java hiện đại, `java.util.Base64` vẫn là công cụ đúng cho bước **biểu diễn dữ liệu**, còn mật mã bảo vệ dữ liệu dùng `javax.crypto`, TLS và những thư viện/hệ quản lý khóa được duy trì. **Học cách phân biệt mục đích của từng bước là quan trọng hơn việc ghi nhớ một phương thức encode.**

## Tài liệu chính thức và hướng dẫn bảo mật

- [Oracle Java SE 26 — Base64: Basic, URL-safe, MIME, Encoder/Decoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.html)
- [Oracle Java SE 26 — Base64.Encoder, withoutPadding](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.Encoder.html)
- [Oracle Java SE 26 — Base64.Decoder, xử lý dữ liệu không hợp lệ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.Decoder.html)
- [Oracle Java SE 26 — Cipher: AES/GCM/NoPadding, AEAD, updateAAD](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html)
- [Oracle Java SE 26 — GCMParameterSpec: IV và authentication tag length](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html)
- [Oracle Java SE 26 — MessageDigest: SHA-256 và isEqual](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/MessageDigest.html)
- [Oracle Java SE 26 — Mac: HmacSHA256](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Mac.html)
- [OWASP Cryptographic Storage Cheat Sheet — AEAD, key management, tránh tự viết mật mã](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [OWASP Password Storage Cheat Sheet — Argon2id, scrypt, PBKDF2, salts và cost](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [RFC 4648 — The Base16, Base32, and Base64 Data Encodings](https://www.rfc-editor.org/rfc/rfc4648)
