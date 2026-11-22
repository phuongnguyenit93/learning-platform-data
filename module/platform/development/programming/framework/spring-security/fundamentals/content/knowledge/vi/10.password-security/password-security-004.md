# BCrypt, PBKDF2, SCrypt và Argon2: cách lựa chọn thuật toán lưu mật khẩu

Khi xây chức năng đăng ký hoặc đăng nhập với Spring Security, một quyết định bảo mật quan trọng là **lưu mật khẩu ở dạng nào**. Mật khẩu người dùng có thể yếu, bị tái sử dụng hoặc bị lấy cắp qua một vụ rò rỉ database. Một password hash tốt không làm mật khẩu yếu trở nên mạnh, nhưng có thể khiến việc **đoán mật khẩu offline từ cơ sở dữ liệu bị đánh cắp** tốn thời gian, bộ nhớ và tiền bạc hơn đáng kể.

Trong nhóm **Mật khẩu**, bốn lựa chọn thường gặp là **BCrypt**, **PBKDF2**, **SCrypt/scrypt** và **Argon2**, đặc biệt là **Argon2id**. Chúng đều có thể được dùng thông qua hợp đồng **PasswordEncoder** của Spring Security, nhưng khác nhau ở cơ chế tăng chi phí tính toán, nhu cầu RAM, khả năng tương thích, yêu cầu tuân thủ và các giới hạn triển khai.

Bài này trình bày theo **mức lựa chọn thuật toán**: hiểu mục tiêu, tiêu chí chọn, so sánh tham số, ưu/nhược điểm, cách cấu hình trong Spring Security, cách chuyển đổi an toàn khi có hash cũ và cách kiểm thử. Không yêu cầu tự triển khai thuật toán mật mã. Ví dụ Java 17/Spring Boot 3.3.6 cuối bài dùng thư viện có sẵn, không chứa mật khẩu thật.

## 1. Bắt đầu từ threat model: hash password đang bảo vệ trước điều gì?

Giả sử bảng account bị lộ:

~~~text
user_id | username | password
--------+----------+---------------------
101     | alice    | spring123
102     | bob      | Welcome2024!
~~~

Nếu lưu plain text, kẻ tấn công có ngay mật khẩu. Nếu lưu SHA-256(password) rất nhanh, kẻ tấn công có thể thử một lượng lớn từ điển mật khẩu offline, so hash và tìm kết quả. **Hash nhanh phù hợp kiểm tra tính toàn vẹn dữ liệu, không phù hợp trực tiếp cho lưu password.**

Mục tiêu của **password hashing** là biến một lần đoán mật khẩu thành công việc có chi phí có chủ đích.

~~~mermaid
flowchart LR
    R["Mật khẩu thô từ đăng ký/đổi mật khẩu"] --> E["Password hashing: salt + cost parameters"]
    E --> H["Stored encoded hash (kèm metadata cần thiết)"]
    L["Mật khẩu thô khi đăng nhập"] --> M["PasswordEncoder.matches(raw, stored)"]
    H --> M
    M --> D{"Khớp?"}
    D -- "Có" --> A["Tiếp tục account checks / authentication"]
    D -- "Không" --> F["Từ chối xác thực"]
~~~

Vài nguyên tắc độc lập với thuật toán:

1. **Không lưu mật khẩu thô**, không ghi mật khẩu vào log và không trả password hash qua API.
2. **Mỗi password cần salt ngẫu nhiên, duy nhất trên thực tế**, do encoder tốt sinh và lưu cùng hash theo định dạng của nó.
3. **Work factor** phải đủ tốn kém để cản đoán offline, nhưng không quá đắt đến mức endpoint đăng nhập tự gây cạn CPU/RAM.
4. **Độ an toàn của mật khẩu đầu vào** vẫn quan trọng: độ dài, mật khẩu bị lộ, MFA, rate limit và phát hiện credential stuffing.
5. **HTTPS bắt buộc** khi truyền credential ngoài môi trường local; hashing trong database không thay TLS.
6. **Bảo vệ database, secrets, backup, audit và quyền truy cập** vẫn cần thiết. Hash không thay các biện pháp đó.

Điều hash bảo vệ đặc biệt tốt là **khi attacker có danh sách hash và thử đoán offline**. Nó không tự ngăn một attacker đang đăng nhập qua API bằng mật khẩu thật đã bị đánh cắp. Tình huống online cần rate limiting, MFA, alerting và các cơ chế authentication khác.

## 2. Phân biệt hashing, encryption, salt và pepper

| Thuật ngữ | Chức năng | Có dùng cho lưu password không? |
| --- | --- | --- |
| **Hash nhanh** (SHA-256 đơn thuần) | Chuyển input thành digest nhanh, không có thiết kế làm chậm đoán mật khẩu. | **Không dùng trực tiếp** cho password. |
| **Password hashing / password KDF** | Chậm có chủ đích; có salt và tham số cost; xác minh bằng matches(). | **Có**: bcrypt, PBKDF2, scrypt, Argon2id. |
| **Encryption** (AES, v.v.) | Dữ liệu được mã hóa có thể giải mã bằng khóa; phù hợp khi phải khôi phục plaintext. | Thường **không chọn** làm cách lưu mật khẩu xác thực người dùng. |
| **Salt** | Giá trị ngẫu nhiên riêng cho mỗi hash, giúp phá lợi thế của precomputation và hash trùng. | **Bắt buộc trong thiết kế tốt**; không cần giữ bí mật. |
| **Pepper** | Bí mật cấp ứng dụng/hệ thống bổ sung vào quy trình hash/xác minh, lưu **ngoài database**. | Có thể tăng defense-in-depth nếu quản lý đúng, không thay salt. |
| **Work factor** | Cấu hình lượng công việc tính toán; với memory-hard còn có chi phí RAM. | Chọn sau khi xem threat model và benchmark. |

**Salt và pepper khác nhau:**

- Salt do encoder tạo ngẫu nhiên theo từng password, **không cần là secret**; thường nằm trong chuỗi encoded hash.
- Pepper là **secret chung hoặc theo nhóm** do hệ thống giữ ở secret manager/HSM hay nơi tách biệt với database.
- Pepper bị lộ thì phải có kế hoạch rotate; vì không có plaintext password nên nhiều kiểu rotation yêu cầu reset password hoặc đợi rehash khi người dùng đăng nhập.
- Không tạo một “pepper” hard-code trong source hoặc commit lên repository rồi tưởng đã có thêm lớp bảo vệ.
- Không tự ghép raw password với pepper bằng phép nối chuỗi tùy tiện rồi gọi là một protocol an toàn; nếu cần pepper, dùng thiết kế/HMAC và secret management đã được review.

Salt còn giúp hai tài khoản chọn **cùng một password** vẫn có các stored hash khác nhau trong điều kiện tạo salt ngẫu nhiên. Đừng test bằng cách yêu cầu encoded hash có giá trị cố định: encoder thường dùng randomness.

## 3. So sánh tổng quan bốn lựa chọn

| Tiêu chí | BCrypt | PBKDF2 | SCrypt (scrypt) | Argon2id |
| --- | --- | --- | --- | --- |
| Cơ chế chính | Password hashing dựa trên Blowfish, chi phí CPU điều chỉnh được. | Lặp HMAC/PRF theo nhiều vòng. | KDF được thiết kế dùng RAM đáng kể để cản phần cứng đoán song song. | Password hashing **memory-hard**, cân bằng các lớp tấn công thực tế. |
| Work factor nổi bật | **cost** (log2), ví dụ 10, 12. | **iteration count** và HMAC (SHA-256, SHA-512...). | **N**, **r**, **p** và chiều dài khóa/salt. | **m** (memory), **t** (passes), **p** (parallelism), độ dài salt/hash. |
| Sử dụng RAM | Thường không memory-hard như scrypt/Argon2. | Thường ít RAM; chủ yếu chi phí CPU. | **Memory-hard**. | **Memory-hard**, tùy chỉnh linh hoạt hơn. |
| Bối cảnh phù hợp | Hệ thống legacy đã dùng bcrypt; hỗ trợ rộng; triển khai đơn giản nếu quản lý đầu vào đúng. | Khi cần hệ sinh thái có **FIPS-validated implementation** hoặc yêu cầu tương thích chuẩn cụ thể. | Nếu không dùng được Argon2id nhưng có môi trường hỗ trợ scrypt và đủ RAM. | **Ứng viên ưu tiên cho thiết kế mới** khi runtime và memory budget cho phép. |
| Lưu ý | **Giới hạn 72 byte đầu vào** trong bcrypt truyền thống; phải xử lý policy/compatibility. | Dễ tăng iterations, nhưng không memory-hard như Argon2id/scrypt. | Tham số RAM lớn có thể gây DoS nếu không giới hạn tải. | Cần runtime/provider phù hợp; cost RAM và concurrency phải đo; Spring Security implementation dùng Bouncy Castle. |
| Có PasswordEncoder Spring Security? | BCryptPasswordEncoder | Pbkdf2PasswordEncoder | SCryptPasswordEncoder | Argon2PasswordEncoder |

Đây là **bảng quyết định**, không phải xếp hạng tuyệt đối cho mọi hệ thống. Mỗi lựa chọn có thể đạt mức bảo vệ tốt nếu dùng tham số phù hợp, thư viện an toàn, salt đúng và vận hành hợp lý. Một hệ thống PBKDF2 có FIPS requirement khác với một dịch vụ mới có nhiều RAM dành cho Argon2id.

**Tên Argon2 là họ thuật toán:** có Argon2d, Argon2i và **Argon2id**. Với lưu password ứng dụng, khuyến nghị thực tế thường là **Argon2id** vì kết hợp các đặc tính chống tấn công side-channel và phần cứng chuyên dụng. Không chọn Argon2d chỉ vì nhìn thấy tên Argon2 trong tài liệu.

## 4. BCrypt: tương thích rộng, work factor dựa trên CPU

BCrypt là lựa chọn phổ biến từ lâu cho password hashing. Nó kết hợp salt và chi phí tính toán được điều chỉnh bằng cost. Một hash bcrypt thường mang metadata như phiên bản, cost, salt và hash, ví dụ **cấu trúc**:

~~~text
$2a$12$[salt-and-hash-data]
~~~

Đây chỉ là ký hiệu dạng cấu trúc, **không phải một hash hợp lệ để copy vào database**. Các prefix như 2a/2b/2y phụ thuộc implementation và khả năng hỗ trợ. Bạn không cần tự bóc tách để kiểm mật khẩu: hãy dùng **BCryptPasswordEncoder.matches(raw, stored)**.

### 4.1. Work factor và thời gian xác minh

BCrypt có tham số **cost** dạng lũy thừa: từ cost 10 lên cost 11 sẽ tăng lượng công việc thuật toán lên khoảng gấp đôi, không đơn giản là cộng một vòng lặp. Thời gian thực phụ thuộc CPU, phiên bản thư viện, tải và môi trường.

~~~java
// Mảnh code Java dùng trong project có Spring Security Crypto.
PasswordEncoder bcrypt = new BCryptPasswordEncoder(12);

String encoded = bcrypt.encode("example-password");
boolean valid = bcrypt.matches("example-password", encoded);
~~~

Trong code này **valid sẽ là true**, nhưng **encoded thay đổi mỗi lần** nhờ salt ngẫu nhiên. Không đưa một kết quả hash cố định vào expected output.

Theo OWASP Password Storage Cheat Sheet được tham khảo cho bài học, bcrypt legacy nên có **cost ít nhất 10**, sau đó được benchmark và điều chỉnh theo khả năng hệ thống. Đây là mức tham khảo, không phải lý do để mọi dịch vụ đặt cùng một cost vĩnh viễn.

### 4.2. Cảnh báo 72 byte, không phải 72 ký tự

BCrypt truyền thống chỉ xét **72 byte đầu vào password**. Với Unicode UTF-8, 72 byte có thể là ít hơn 72 ký tự. Nếu implementation hoặc hệ thống tự động cắt ở ranh giới này, hai mật khẩu có cùng 72 byte đầu có thể bị coi tương đương.

Cần:

- Xác định hành vi giới hạn đầu vào của **implementation đang chạy** và đường chuyển String thành byte.
- Đặt chính sách độ dài mật khẩu rõ, không âm thầm cắt password khiến hai input khác nhau được chấp nhận.
- Ưu tiên Argon2id/PBKDF2/scrypt với thiết kế đầu vào phù hợp nếu cần hỗ trợ passphrase dài.
- Nếu có database bcrypt cũ, kiểm chính sách của bản triển khai cũ khi di chuyển và test cả mật khẩu chứa tiếng Việt/emoji/Unicode; không “fix” bằng cách hash nhanh tùy tiện trước bcrypt mà không đánh giá giao thức.

Cũng cần tránh xử lý password bằng **trim()** hoặc toLowerCase() vô tình: mật khẩu có phân biệt từng ký tự theo hợp đồng ứng dụng; nếu có Unicode normalization, phải được thiết kế nhất quán, không thay đổi đột ngột khi nâng phiên bản.

### 4.3. Chọn bcrypt khi nào?

- Có nhiều hash bcrypt trong hệ thống đang hoạt động và cần giữ khả năng xác minh.
- Các thư viện, môi trường runtime, hệ thống tích hợp đã hỗ trợ tốt.
- Muốn nâng cost của hash mới trong khi từng bước nâng hash cũ.
- Một ràng buộc vận hành khiến chuyển ngay sang Argon2id khó, với kế hoạch rà soát cost và giới hạn input rõ.

**Không chọn bcrypt đơn giản vì Spring Security từng dùng nó làm encoder mặc định cho hash mới.** Mặc định thư viện, yêu cầu bảo mật mới và ngân sách vận hành là ba yếu tố khác nhau.

## 5. PBKDF2: KDF lặp HMAC, thuận lợi cho một số yêu cầu tuân thủ

**PBKDF2** (Password-Based Key Derivation Function 2) được chuẩn hóa và có hệ sinh thái rộng. Tham số quan trọng gồm:

- **HMAC/PRF**: ví dụ HMAC-SHA-256.
- **Số vòng lặp**: tăng iteration count làm tăng chi phí tính toán.
- **Salt**: ngẫu nhiên và riêng cho mỗi hash.
- **Derived key length** và định dạng lưu trữ.
- Một số implementation có thể bổ sung secret/pepper riêng.

PBKDF2 chủ yếu làm việc bằng **CPU**, không phải memory-hard theo cùng nghĩa với Argon2id và scrypt. Điều đó có thể là điểm yếu tương đối khi đối thủ có phần cứng tối ưu hóa hash, nhưng lại thuận lợi cho môi trường yêu cầu HMAC/cryptographic modules có validation.

### 5.1. Khi nào PBKDF2 là lựa chọn thích hợp?

Khi hệ thống có **yêu cầu FIPS-140**, PBKDF2-HMAC-SHA-256 có thể là lựa chọn thực dụng nếu dùng **implementation và cryptographic module được validate** trong cấu hình được chấp thuận.

**Dùng PBKDF2 không tự làm ứng dụng trở thành FIPS compliant.** Phải xác minh provider/JCE, phiên bản module, mode vận hành, chính sách khóa và phần còn lại của yêu cầu compliance.

Theo OWASP Password Storage Cheat Sheet được đối chiếu cho bài này: với **PBKDF2-HMAC-SHA-256**, giá trị tham khảo là **600.000 iterations hoặc hơn**. Đó là khuyến nghị thực hành và có thể thay đổi theo thời gian; luôn xác minh khi triển khai production.

### 5.2. Spring Security: chú ý phiên bản default

~~~java
PasswordEncoder pbkdf2 =
    Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();
~~~

Trong Spring Security 6.3, factory **defaultsForSpringSecurity_v5_8()** sử dụng 16-byte salt, khoảng **310.000 iterations**, HMAC-SHA-256 và 256-bit derived key. Giá trị này **thấp hơn** mức 600.000 iterations ở khuyến nghị OWASP đã nêu.

Điều đó **không làm API sai**, nhưng có nghĩa **không nên coi giá trị default của một phiên bản framework là chuẩn bảo mật tối thiểu cập nhật cho mọi môi trường**.

Một cấu hình tường minh để áp dụng 600.000 iterations:

~~~java
PasswordEncoder pbkdf2 =
    new Pbkdf2PasswordEncoder(
        "", 16, 600_000,
        Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm.PBKDF2WithHmacSHA256
    );
~~~

Các tham số lần lượt là **secret bổ sung** (ở ví dụ để rỗng), **salt length tính bằng byte**, **iterations**, và **thuật toán SecretKeyFactory**. Nếu chọn secret bổ sung thực sự, phải có secret manager và kế hoạch rotation; đừng dùng một hằng literal trong source.

### 5.3. Các hash PBKDF2 không nhất thiết tương thích với nhau

Hai hash cùng được gọi là PBKDF2 nhưng dùng HMAC khác, salt length khác, iterations khác, output length/encoding khác **không mặc nhiên kiểm được** bằng cùng một cấu hình PasswordEncoder.

Khi migrate, phải lưu nhận diện phiên bản/parameters và đảm bảo encoder cũ vẫn có thể xác minh trước khi chuyển sang encoder mới. Với định dạng DelegatingPasswordEncoder, mỗi bộ tham số nên có một id rõ ràng.

## 6. SCrypt/scrypt: memory-hard để tăng chi phí đoán offline

**scrypt** chủ đích yêu cầu lượng RAM đáng kể, ngoài CPU, để làm phép đoán mật khẩu tốn tài nguyên hơn trên phần cứng tối ưu hóa song song. Trong Spring Security dùng **SCryptPasswordEncoder**.

Các tham số phổ biến:

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **N** (cpuCost) | Tham số chi phí công việc, thường là lũy thừa của 2. | 2^16 hoặc 2^17. |
| **r** (memoryCost ở API Spring) | Block size; ảnh hưởng lượng RAM và chi phí. | 8. |
| **p** (parallelization) | Tham số song song hóa/công việc. | 1 hoặc cao hơn theo mục tiêu benchmark. |
| **saltLength** | Độ dài salt ngẫu nhiên. | 16 byte. |
| **keyLength** | Độ dài derived key. | 32 byte. |

Ước lượng RAM lõi của scrypt thường được nêu xấp xỉ **128 × N × r byte** (chưa kể overhead implementation, JVM và các phép tính khác). Với N=65.536 và r=8, phần chính khoảng **64 MiB mỗi tác vụ**. Với N=131.072 và r=8, khoảng **128 MiB mỗi tác vụ**. Vì thế cần đo cả số request đăng nhập đồng thời, không chỉ thời gian một request.

### 6.1. Spring Security factory và tham số đề xuất

~~~java
PasswordEncoder scryptDemo =
    SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8();
~~~

Factory v5_8 trong Spring Security 6.3 dùng các giá trị như **N=2^16, r=8, p=1, 32-byte key, 16-byte salt**. Nó là một lựa chọn hợp lý để **học API** và so sánh, nhưng thấp hơn cấu hình **N=2^17, r=8, p=1** được OWASP đề cập như một mức khuyến nghị khi không dùng Argon2id.

Một cấu hình minh họa với thông số mạnh hơn:

~~~java
PasswordEncoder scrypt =
    new SCryptPasswordEncoder(
        1 << 17, // N = 131072
        8,       // r
        1,       // p
        32,      // key length, bytes
        16       // salt length, bytes
    );
~~~

Cấu hình này có chi phí RAM đáng kể, **không nên đẩy thẳng vào production khi chưa kiểm tải**. Đặc biệt trong môi trường container giới hạn heap/memory, nhiều lần xác minh đồng thời có thể gây memory pressure hoặc OOM. Các thông số OWASP là điểm xuất phát để đánh giá, không phải một lệnh “mỗi request phải cấp chính xác số MiB này” cho mọi hệ thống.

### 6.2. Khi nào chọn scrypt?

- Không thể dùng Argon2id nhưng có thư viện scrypt được cập nhật/kiểm tra.
- Có RAM và quota đủ để trả chi phí memory-hard khi đăng nhập.
- Muốn tránh dựa hoàn toàn vào CPU iterations như PBKDF2.
- Có kế hoạch giới hạn concurrency, timeout, rate limit và kiểm thử memory usage.

Nếu một nền tảng có ràng buộc compliance riêng, cần xác minh scrypt có được phép trong policy đó không. Không thay PBKDF2 bằng scrypt khi yêu cầu FIPS-validated module bắt buộc mà chưa rà soát.

## 7. Argon2: ưu tiên Argon2id cho lưu mật khẩu mới khi phù hợp

**Argon2** là họ thuật toán được chọn thắng Password Hashing Competition. Ba biến thể thường được nhắc tới:

- **Argon2d**: truy cập bộ nhớ phụ thuộc dữ liệu; không phải lựa chọn mặc định an toàn cho mọi môi trường có rủi ro side-channel.
- **Argon2i**: tập trung chống một số dạng side-channel bằng truy cập bộ nhớ độc lập dữ liệu.
- **Argon2id**: kết hợp hai cách tiếp cận; **lựa chọn được khuyến nghị phổ biến cho password hashing ở ứng dụng**.

Các tham số:

| Ký hiệu | Ý nghĩa | Tác động khi tăng |
| --- | --- | --- |
| **m** | Dung lượng bộ nhớ (thường tính bằng KiB theo API/format tương ứng). | Tăng RAM sử dụng; tăng chi phí cho attacker lẫn server. |
| **t** | Số lượt xử lý/passes. | Tăng công việc tính toán, thường tăng thời gian. |
| **p** | Mức song song hóa/lane. | Thay đổi cách thực thi và sử dụng tài nguyên; không đơn giản là “nhân RAM lên p”. |
| **saltLength** | Salt ngẫu nhiên riêng cho password. | Giúp chống precomputation/collision thực tế giữa hash. |
| **hashLength** | Độ dài output được lưu. | Không thay trực tiếp vai trò m/t/p. |

**Argon2id không tự tối ưu được mọi cấu hình.** Chọn m/t/p cần xét CPU, RAM, concurrent logins, triển khai container và sự chênh lệch hiệu năng giữa defender và attacker.

### 7.1. OWASP so với RFC 9106: hai loại mốc khác nhau

OWASP Password Storage Cheat Sheet đề xuất Argon2id với một mức tham khảo **m=19 MiB (19.456 KiB), t=2, p=1**. Đây là một baseline thực dụng có thể áp dụng cho nhiều ứng dụng nếu benchmark phù hợp.

**RFC 9106** đưa ra các cấu hình mạnh hơn cho những điều kiện RAM cho phép: ví dụ lựa chọn sử dụng **64 MiB, t=3, p=4**, hoặc lựa chọn dùng **2 GiB** RAM với các tham số của RFC. Không thể kết luận “OWASP sai” hoặc “RFC luôn phải chạy 2 GiB trong mọi web app”; chúng có bối cảnh và mục tiêu chi phí khác nhau.

Đối với một service có hàng trăm login request đồng thời, cấu hình 2 GiB cho một request có thể không khả thi về mặt vận hành. Chọn **mức baseline phù hợp + tuning và kiểm thử tải**, rồi nâng khi hạ tầng cho phép. Với workload nhạy cảm, cân nhắc thêm xác thực đa yếu tố và hạn chế thử mật khẩu.

### 7.2. Argon2PasswordEncoder trong Spring Security

~~~java
PasswordEncoder argon2Default =
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
~~~

Trong dòng Spring Security 6.3.x, factory này dùng 16-byte salt, 32-byte hash, **p=1, m=2^14 KiB (16 MiB), t=2**. Mức memory **16 MiB** thấp hơn baseline **19 MiB** của OWASP ở trên, nên production không nên dựa vào tên factory để suy ra đủ mọi khuyến nghị cập nhật.

Cấu hình tường minh gần mốc OWASP:

~~~java
PasswordEncoder argon2id =
    new Argon2PasswordEncoder(
        16,       // saltLength: bytes
        32,       // hashLength: bytes
        1,        // parallelism
        19 * 1024,// memory: KiB = 19456
        2         // iterations
    );
~~~

Đây là mảnh code thuộc **Spring Security Crypto**. Implementation **Argon2PasswordEncoder** sử dụng **Bouncy Castle** và cần dependency liên quan có mặt trên runtime classpath. Code mẫu Maven ở phần thực hành khai báo thư viện đó rõ ràng.

### 7.3. Những điều phải đo khi chọn Argon2id

- **Memory cost** mỗi lần encode/matches thực tế của implementation Java.
- **p95/p99 latency** khi vài chục request login đồng thời, không chỉ một phép hash riêng lẻ.
- CPU, GC, heap, native memory, RSS/container OOM risk.
- Khi autoscale, tổng lượng RAM/CPU và khả năng attacker khiến nhiều request xác thực được thực thi đồng thời.
- Hash cũ với parameters cũ có xác minh được khi nâng phiên bản không?
- Thay đổi code/BC dependency có làm output hoặc performance thay đổi không?

Spring Security dùng Bouncy Castle trong Argon2PasswordEncoder; các tối ưu/parallelism có thể khác implementation native. Vì vậy **benchmark Java implementation thực tế**, không dùng một benchmark thư viện ngôn ngữ khác để quyết định chính xác thời gian server.

## 8. Bảng lựa chọn cho các tình huống thường gặp

| Tình huống | Hướng lựa chọn thực tế | Vì sao |
| --- | --- | --- |
| Ứng dụng mới, có RAM và không bị ràng buộc compliance đặc biệt | **Argon2id** với m/t/p được benchmark, bắt đầu từ khuyến nghị hiện hành. | Memory-hard, cơ chế hiện đại và điều chỉnh cost linh hoạt. |
| Không triển khai Argon2id được nhưng cần memory-hard | **scrypt** với N/r/p đúng policy, kiểm RAM/concurrency. | Tăng chi phí memory cho đoán offline. |
| Cần cryptographic module phù hợp FIPS/interop quy định | **PBKDF2-HMAC-SHA-256** qua provider được validate, iteration đủ cao. | Hỗ trợ chuẩn và hệ sinh thái tương thích. |
| Hệ thống hiện tại có hàng triệu hash bcrypt | **Giữ verify bcrypt**, nâng cost dần hoặc rehash sang thuật toán mới khi login. | Không có plaintext để chuyển hàng loạt; tránh khóa người dùng đột ngột. |
| Hạ tầng thiếu RAM nhưng CPU đủ, có yêu cầu FIPS | **PBKDF2** với work factor được hiệu chỉnh và controls bổ sung. | Chi phí chủ yếu CPU, dễ cân đối RAM hơn memory-hard. |
| Nhiều login đồng thời, service bị giới hạn memory/container | Chọn theo **benchmark tải thực tế**, kiểm rate limit và khả năng scale; không tự đặt m cực cao. | Thông số quá cao có thể tạo DoS cho chính server. |
| Legacy hash MD5/SHA1/noop | **Lập kế hoạch migration/reset**; chỉ verify legacy trong phạm vi kiểm soát nếu bắt buộc và ngừng tạo hash mới kiểu đó. | Thuật toán nhanh/không hash không đủ bảo vệ password. |

Một cách tóm tắt không thay thế security review:

~~~text
Có yêu cầu FIPS và provider phù hợp?
  Có -> PBKDF2-HMAC-SHA-256 với số iterations hiện hành và module validated.
  Không ->
    Có thể dùng Argon2id và RAM budget đáp ứng?
      Có -> Argon2id, benchmark m/t/p.
      Không ->
        Có thể dùng scrypt và đủ RAM?
          Có -> scrypt, benchmark N/r/p.
          Không -> Xem xét bcrypt/PBKDF2 theo ràng buộc, policy input,
                   kế hoạch nâng cấp và compensating controls.
Đang có stored hash cũ?
  Có -> giữ khả năng verify đúng format + upgrade an toàn theo phiên bản.
~~~

Cây quyết định là hướng dẫn sơ bộ: chuẩn tổ chức, hỗ trợ library, mật khẩu dài, capacity/traffic, threat model và ngân sách bảo mật có thể thay đổi lựa chọn.

## 9. PasswordEncoder trong Spring Security

Spring Security định nghĩa hợp đồng:

~~~java
// Rút gọn chữ ký API, không phải một file Java độc lập.
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Ý nghĩa:

- **encode(raw)** dùng khi đăng ký hoặc thay đổi password; thường tạo salt mới.
- **matches(raw, stored)** kiểm password đã nhập với hash đang lưu, **không dùng raw.equals(stored)**.
- **upgradeEncoding(stored)** cho biết một hash có thể cần cập nhật theo cost/algorithm policy của encoder; ý nghĩa cụ thể phụ thuộc implementation. Nó không tự cập nhật database.

Không lấy kết quả encode(raw) lần hai rồi so String với stored: do salt ngẫu nhiên, hai hash đúng thuật toán có thể khác nhau. Hãy gọi **matches**.

### 9.1. Các lớp cần nhớ

~~~java
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.crypto.scrypt.SCryptPasswordEncoder;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
~~~

Không có nhu cầu tự viết implementation MD5/SHA-256 để lưu password. Những hash nhanh có thể xuất hiện như legacy support trong một số factory, **không có nghĩa an toàn để phát hành hash mới**.

### 9.2. DelegatingPasswordEncoder giúp tồn tại nhiều thuật toán

Khi cần chuyển dần từ bcrypt sang Argon2id, hệ thống thường không thể biết mật khẩu thô của tất cả user để rehash ngay. **DelegatingPasswordEncoder** lưu định danh bên ngoài stored hash:

~~~text
{bcrypt}$2a$10$...
{pbkdf2-600k}...
{scrypt-v1}$...
{argon2id-m19456-t2-p1}$argon2id$v=19$m=19456,t=2,p=1$...
~~~

Các chuỗi chứa **...** là mô tả định dạng, **không phải hash thật**. Phần **{id}** giúp router chọn đúng PasswordEncoder để matches; phần sau đó là encoded data theo implementation, có thể mang salt/cost metadata riêng.

Ví dụ:

~~~java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String stored = encoder.encode("a-demo-pass");
// Thường bắt đầu bằng "{bcrypt}" với factory mặc định trên 6.x.
boolean ok = encoder.matches("a-demo-pass", stored);
~~~

**Factory mặc định** giúp tương thích một số id/format legacy. Nó không đồng nghĩa mọi algorithm trong danh sách mapping đều nên dùng để **tạo hash mới**; id dùng cho encode có thể khác id được chấp nhận để verify hash cũ.

Không dùng một fallback như NoOpPasswordEncoder cho id không biết trên production. Khi một hash không có id hoặc id không được nhận diện, hệ thống phải **có chiến lược migration rõ** chứ không tự xem phần stored value là mật khẩu thô.

### 9.3. Vì sao không đổi thẳng PasswordEncoder bean rồi deploy?

Giả sử DB lưu:

~~~text
username: alice
password_hash: $2a$12$...
~~~

Nếu trước đó bean là BCryptPasswordEncoder và bạn đổi thành Argon2PasswordEncoder nhưng không lưu algorithm id, một lần login sau có thể thất bại vì decoder mới không hiểu format cũ. Cách an toàn hơn là **gắn id** và duy trì encoder hỗ trợ old hashes:

~~~text
Trước: bcrypt raw format, ví dụ $2a$12$...
Chuẩn hóa: {bcrypt}$2a$12$...
Sau login hợp lệ: có thể nâng thành {argon2id-...}...
~~~

Lưu ý: gắn prefix hàng loạt vào hash legacy chỉ được phép nếu bạn **biết chắc** dữ liệu đang có là bcrypt với format phù hợp. Không gắn {bcrypt} cho mọi chuỗi DB chỉ vì “trông giống hash”. Cần inventory và test mẫu trước.

## 10. Demo Maven Java 17: chọn và kiểm bốn thuật toán

Project này là **CLI Spring Boot** để tập trung vào thuật toán password. Nó không dựng HTTP server, không tạo tài khoản thật và không quản lý database; vì vậy dễ chạy và không có nguy cơ mở endpoint với mật khẩu demo.

Mục tiêu: gọi **bốn PasswordEncoder**, quan sát khả năng matches cho password đúng/sai, dùng **DelegatingPasswordEncoder** để đọc hash legacy bcrypt và tạo hash mới Argon2id. Không in password hash thật trong stdout; bảng output chỉ gồm nhãn algorithm và boolean.

### 10.1. Cấu trúc thư mục

~~~text
password-choice-lab/
  pom.xml
  src/main/java/com/example/hashchoice/
    PasswordChoiceApplication.java
    HashingPolicy.java
  src/test/java/com/example/hashchoice/
    HashingPolicyTests.java
~~~

Yêu cầu **JDK 17+, Maven 3.9+**. Bài dùng Spring Boot **3.3.6** và Spring Security **6.3.x** do Boot parent quản lý. Dòng 3.3.6 được cố định để demo nhất quán, **không phải khuyến nghị dùng bản cũ trong production năm hiện tại**. Khi xây hệ thống mới, chọn release đang được hỗ trợ và áp dụng bản vá.

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>password-choice-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-crypto</artifactId>
        </dependency>
        <!-- Argon2PasswordEncoder của Spring Security dùng Bouncy Castle. -->
        <dependency>
            <groupId>org.bouncycastle</groupId>
            <artifactId>bcprov-jdk18on</artifactId>
            <version>1.80</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot parent quản lý phiên bản của Spring Security. Ví dụ **pin Bouncy Castle 1.80** để POM lab có thể dựng dependency một cách xác định; **trước khi triển khai thực tế, phải kiểm phiên bản Bouncy Castle được hỗ trợ/vá mới nhất và chính sách của tổ chức**, thay vì giữ nguyên pin của tài liệu.

Lưu ý không đưa starter-web: đây là một **Spring Boot CLI** chạy CommandLineRunner và kết thúc, không phải server đăng nhập. Một sản phẩm thực có thể dùng spring-boot-starter-security với UserDetailsService/DaoAuthenticationProvider hoặc Resource Server tương ứng.

### 10.3. HashingPolicy.java

~~~java
package com.example.hashchoice;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.crypto.scrypt.SCryptPasswordEncoder;

public final class HashingPolicy {

    private HashingPolicy() {
    }

    public static Map<String, PasswordEncoder> algorithms() {
        Map<String, PasswordEncoder> encoders = new LinkedHashMap<>();

        encoders.put("bcrypt",
            new BCryptPasswordEncoder(10));

        encoders.put("pbkdf2-sha256-600k",
            new Pbkdf2PasswordEncoder(
                "", 16, 600_000,
                Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm
                    .PBKDF2WithHmacSHA256));

        // N=2^16 cho phòng lab; không coi nó là minimum production.
        encoders.put("scrypt-demo-n65536",
            SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8());

        encoders.put("argon2id-m19456-t2-p1",
            new Argon2PasswordEncoder(
                16, 32, 1, 19 * 1024, 2));

        return encoders;
    }

    public static PasswordEncoder delegating() {
        return new DelegatingPasswordEncoder(
            "argon2id-m19456-t2-p1", algorithms());
    }
}
~~~

**Vì sao chọn bốn cấu hình này?**

- **bcrypt cost 10**: thuận tiện lab/legacy và đáp ứng mức tối thiểu tham khảo của OWASP; production phải benchmark chọn cost phù hợp hơn khi cần.
- **PBKDF2-HMAC-SHA-256 600.000 iterations**: minh họa chọn tham số tường minh thay vì mù quáng dùng factory 310.000 iterations.
- **scrypt N=2^16, r=8, p=1**: giảm chi phí RAM của lab; mức này **không đạt baseline OWASP N=2^17/r=8/p=1** đã nêu. Để xây sản phẩm, nâng tham số sau load test hoặc chọn Argon2id.
- **Argon2id m=19 MiB, t=2, p=1**: gần baseline OWASP dùng trong bài, cần benchmark Java/Bouncy Castle và concurrency thực tế.
- **DelegatingPasswordEncoder** mới tạo hash với id argon2id-m19456-t2-p1, đồng thời vẫn hiểu hash có prefix {bcrypt}, {pbkdf2-sha256-600k}, {scrypt-demo-n65536} hoặc {argon2id-m19456-t2-p1} nếu cần verify.

Các id đặt tên riêng có chủ đích để tránh nhầm **cùng một thuật toán nhưng khác parameters**. Đừng dùng id {pbkdf2} cho hash đã tạo với cấu hình khác rồi mong mọi provider tự đoán iterations; hãy có version/parameter id rõ.

### 10.4. PasswordChoiceApplication.java

~~~java
package com.example.hashchoice;

import java.util.Map;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class PasswordChoiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordChoiceApplication.class, args);
    }

    @Bean
    CommandLineRunner runPasswordChoiceLab() {
        return args -> {
            String password = "a-safe-demo-passphrase";
            Map<String, PasswordEncoder> encoders =
                HashingPolicy.algorithms();

            for (var entry : encoders.entrySet()) {
                PasswordEncoder encoder = entry.getValue();
                String encoded = encoder.encode(password);

                boolean correct = encoder.matches(
                    password, encoded);
                boolean incorrect = encoder.matches(
                    "wrong-password", encoded);

                System.out.println(entry.getKey() + ": "
                    + correct + "/" + incorrect);
            }

            PasswordEncoder delegating = HashingPolicy.delegating();
            String newEncoded = delegating.encode(password);
            System.out.println("new-id="
                + newEncoded.startsWith(
                    "{argon2id-m19456-t2-p1}"));

            String legacyBcrypt = "{bcrypt}" +
                encoders.get("bcrypt").encode(password);
            System.out.println("legacy-verify="
                + delegating.matches(password, legacyBcrypt));
        };
    }
}
~~~

**Kết quả chuẩn** (những dòng nghiệp vụ trong console; Spring Boot còn in startup log và thứ tự map đã được bảo toàn bằng LinkedHashMap):

~~~text
bcrypt: true/false
pbkdf2-sha256-600k: true/false
scrypt-demo-n65536: true/false
argon2id-m19456-t2-p1: true/false
new-id=true
legacy-verify=true
~~~

**Không có hash cố định trong output**, vì salt ngẫu nhiên được sinh mỗi lần encode. Thời gian chạy có thể lâu hơn một demo Java thông thường do thuật toán cố tình tốn CPU/RAM; đây là điều bình thường trong mức giới hạn tài nguyên của máy.

### 10.5. Chạy chương trình

Từ thư mục chứa pom.xml:

~~~bash
mvn test
mvn spring-boot:run
~~~

Hoặc tạo JAR:

~~~bash
mvn package
java -jar target/password-choice-lab-1.0.0.jar
~~~

Nếu Bouncy Castle thiếu khi chạy Argon2PasswordEncoder, kiểm dependency runtime bằng Maven dependency tree, không xóa phần Argon2 rồi tự cho rằng đã test đủ bốn thuật toán. Nếu môi trường CI container thiếu RAM, điều chỉnh tài nguyên hoặc test bằng profile phù hợp; không âm thầm đổi tham số production để các test chạy nhanh hơn.

## 11. Bộ JUnit kiểm bốn encoder và migration

Tạo file **src/test/java/com/example/hashchoice/HashingPolicyTests.java**:

~~~java
package com.example.hashchoice;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class HashingPolicyTests {

    private static final String RAW = "a-safe-demo-passphrase";

    @Test
    void eachAlgorithmMatchesCorrectAndRejectsWrongPassword() {
        HashingPolicy.algorithms().forEach((name, encoder) -> {
            String encoded = encoder.encode(RAW);

            assertThat(encoded)
                .describedAs(name)
                .isNotBlank()
                .isNotEqualTo(RAW);

            assertThat(encoder.matches(RAW, encoded))
                .describedAs(name + " correct")
                .isTrue();

            assertThat(encoder.matches("wrong", encoded))
                .describedAs(name + " wrong")
                .isFalse();
        });
    }

    @Test
    void saltingProducesDifferentEncodedValues() {
        PasswordEncoder bcrypt = new BCryptPasswordEncoder(10);

        String first = bcrypt.encode(RAW);
        String second = bcrypt.encode(RAW);

        assertThat(first).isNotEqualTo(second);
        assertThat(bcrypt.matches(RAW, first)).isTrue();
        assertThat(bcrypt.matches(RAW, second)).isTrue();
    }

    @Test
    void newHashesUseArgon2idPolicyId() {
        PasswordEncoder encoder = HashingPolicy.delegating();

        String encoded = encoder.encode(RAW);

        assertThat(encoded)
            .startsWith("{argon2id-m19456-t2-p1}");
        assertThat(encoder.matches(RAW, encoded)).isTrue();
        assertThat(encoder.matches("wrong", encoded)).isFalse();
    }

    @Test
    void oldBcryptHashRemainsVerifiable() {
        String oldStored = "{bcrypt}"
            + new BCryptPasswordEncoder(10).encode(RAW);

        PasswordEncoder mixed = HashingPolicy.delegating();

        assertThat(mixed.matches(RAW, oldStored)).isTrue();
        assertThat(mixed.upgradeEncoding(oldStored)).isTrue();
    }

    @Test
    void oldPbkdf2HashRemainsVerifiableWithMatchingParams() {
        PasswordEncoder old = HashingPolicy.algorithms()
            .get("pbkdf2-sha256-600k");
        String stored = "{pbkdf2-sha256-600k}" + old.encode(RAW);

        PasswordEncoder mixed = HashingPolicy.delegating();

        assertThat(mixed.matches(RAW, stored)).isTrue();
    }

    @Test
    void unknownAlgorithmIdIsRejectedNotReadAsPlaintext() {
        PasswordEncoder mixed = HashingPolicy.delegating();

        assertThatThrownBy(() ->
            mixed.matches(RAW, "{unknown-algorithm}anything")
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Đây là **sáu JUnit test method**. Một test có thể thử nhiều algorithm trong vòng lặp; tính đúng của result không nên đo bằng số lượng test annotation riêng. Với việc dùng BCrypt/scrypt/Argon2id, **không ép timeout 100 ms** hoặc thời gian cố định; chi phí làm chậm là chủ đích. Mã được cung cấp để chạy, không phải báo cáo đã thực thi thành công ở máy của người học.

Test salt khác nhau có xác suất lý thuyết cực nhỏ bị trùng, nhưng đối với random salt đủ dài đây là kỳ vọng thực tế hợp lý. Nó không chứng minh entropy được sinh đúng trên mọi hệ điều hành; kiểm implementation/RNG theo yêu cầu hệ thống khi cần đánh giá sâu.

### 11.1. Điều gì chưa được bộ test chứng minh?

- Không đo sức chống đoán offline của một thuật toán trên GPU hoặc ASIC thật.
- Không kiểm throughput đăng nhập/đổi mật khẩu ở tải cao.
- Không xác minh FIPS compliance.
- Không bảo đảm giới hạn RAM của container khi 50 hoặc 500 request trùng thời điểm.
- Không kiểm password bị lộ, MFA, account lockout, rate limiting hay authz.
- Không chứng minh framework cũ đã lưu mọi bcrypt hash dưới format tương thích.

**Kiểm thử thuật toán là cần, nhưng không thay benchmark và security review.**

## 12. Rehash và nâng cấp password hash cũ một cách an toàn

Một hệ thống thật có thể có bảng account như:

~~~text
username | password_hash
---------+--------------------------------------
alice    | {bcrypt}$2a$12$...
bob      | {pbkdf2-sha256-600k}...
carol    | {argon2id-m19456-t2-p1}$argon2id$...
~~~

Các giá trị có dấu ba chấm là **minh họa**, không dùng trực tiếp để xác minh password. Ý nghĩa là **hash đã có id để định tuyến tới encoder phù hợp**.

### 12.1. Nâng cấp opportunistic rehash khi login

Một trình tự đúng:

1. Người dùng gửi username và mật khẩu qua kênh được bảo vệ bằng HTTPS.
2. Authentication service tải user và **stored hash hiện tại**.
3. Dùng DelegatingPasswordEncoder.matches(raw, stored) với mapper đủ hỗ trợ hash cũ.
4. Kiểm account state và chính sách xác thực khác trước khi tạo session/token.
5. Nếu login hợp lệ **và** encoder.upgradeEncoding(stored) cho biết cần nâng cấp, gọi encoder.encode(raw) theo **id mới hiện hành**.
6. Ghi hash mới bằng thao tác **có kiểm soát cạnh tranh**, ví dụ UPDATE ... WHERE user_id=? AND password_hash=? để không ghi đè thay đổi password khác vừa diễn ra.
7. Không trả raw password/hash trong log hoặc response, xóa dữ liệu credential khỏi nơi giữ không cần thiết.
8. Sau khi đủ coverage và có kế hoạch, loại bỏ hỗ trợ verify thuật toán legacy đã ngừng dùng.

Nếu dùng Spring Security, có thể tích hợp cơ chế **UserDetailsPasswordService.updatePassword(...)** với DaoAuthenticationProvider theo API của version, nhưng cần kiểm cách framework kích hoạt rehash và tác động dữ liệu. **PasswordEncoder.upgradeEncoding chỉ là tín hiệu; nó không tự cập nhật database**.

### 12.2. Vì sao không rehash mọi tài khoản bằng một SQL batch?

Bạn không có raw password để tạo hash Argon2id hợp lệ từ hash bcrypt cũ. **Argon2id(bcryptHash) không tương đương Argon2id(rawPassword)**; tạo lớp hash kiểu này tùy tiện thay đổi protocol đăng nhập và có rủi ro legacy design. Không nên tự biến hash cũ thành “mật khẩu mới” hoặc lưu double-hash mà không có một thiết kế được audit.

Các hướng thực tế:

- Rehash **khi người dùng đăng nhập hợp lệ**.
- Với tài khoản không còn đăng nhập, áp dụng **reset password** theo kênh an toàn nếu bắt buộc bỏ legacy.
- Nếu legacy hash quá yếu, có thể cần reset chủ động và giới hạn thời gian hỗ trợ.
- Thiết lập metrics (không chứa password/hash) theo algorithm id để biết bao nhiêu tài khoản chưa nâng cấp.
- Rollback phải có kế hoạch: instance cũ có thể không hiểu hash id mới, nên deploy theo trình tự tương thích.

### 12.3. Không bật fallback mật khẩu thô cho unknown id

Nếu một hash không có prefix hoặc không có id trong map, **đừng tự đối xử nó như {noop}**. Không thêm một default matching encoder kiểu NoOp để “login khỏi lỗi”.

Hãy inventory dữ liệu thật, phân nhóm theo schema/nguồn đáng tin và viết migration có kiểm thử. Với bcrypt raw hash có cấu trúc nhận diện rõ, có thể chuẩn hóa prefix sau khi xác nhận format đúng; với chuỗi mơ hồ cần xử lý riêng hoặc buộc reset.

### 12.4. Thay parameters cũng là một lần nâng cấp policy

Bạn có thể giữ Argon2id nhưng tăng memory từ 19 MiB lên 32/64 MiB. Khi đó cần id/metadata và upgradeEncoding logic phù hợp; **không nhất thiết phải đổi họ thuật toán**. Với PBKDF2, đổi iterations hoặc HMAC cũng cần cơ chế version. Với bcrypt, cost nằm trong encoded hash và encoder có thể nhận ra một số trường hợp cần nâng cấp.

Hash mới nên dùng policy hiện hành, hash cũ vẫn xác minh được trong thời gian được cho phép. Không phá quá trình đăng nhập bằng một lần thay bean không kiểm định.

## 13. Cách benchmark thực tế trước khi chọn cost

Không có một giá trị cost đảm bảo cho mọi CPU/container. Chọn bằng đo lường thay vì đoán:

1. **Xác định security baseline** từ policy tổ chức, OWASP/NIST/RFC và yêu cầu compliance.
2. **Đo encode và matches** trên hardware/runtime dự định triển khai, cùng phiên bản JDK và provider.
3. **Warm up JVM/JIT** trước khi đo. Tránh dùng lần encode đầu tiên làm đại diện cho p95/p99.
4. **Đo nhiều lần** và lấy percentile, không chỉ trung bình; không in raw password/hash trong log benchmark.
5. **Đo concurrency**, đặc biệt với scrypt/Argon2id: đồng thời 20 request x 64–128 MiB có thể làm memory pressure lớn.
6. **Xem cả latency API** (database lookup, network/IdP, encoder, session) để chọn ngân sách cho hashing.
7. **Kiểm rate limit/queue/circuit breaking** để attacker không mở hàng loạt tác vụ xác minh password tốn tài nguyên.
8. **Kiểm chi phí đăng ký/reset**, không chỉ login. Encode cũng có chi phí CPU/RAM và có thể bị lạm dụng nếu endpoint không bảo vệ.
9. **Theo dõi hệ thống thật** và review định kỳ; điều chỉnh cost khi phần cứng, lưu lượng hoặc threat model thay đổi.
10. **Triển khai migration có versioning**, không thay tất cả cùng lúc thiếu rollback.

Ví dụ phép đo đơn giản để quan sát (không thay benchmark JMH):

~~~java
// Mảnh code minh họa trong một method có PasswordEncoder encoder.
String stored = encoder.encode("a-safe-demo-passphrase");

long started = System.nanoTime();
boolean matched = encoder.matches(
    "a-safe-demo-passphrase", stored);
long elapsed = System.nanoTime() - started;

System.out.println("matched=" + matched);
System.out.println("elapsedMs=" + elapsed / 1_000_000);
~~~

**matched=true**, còn **elapsedMs không có giá trị đúng cố định**. Mỗi máy/JVM/tải sẽ cho thời gian khác. Không dùng số đo của 1 request để kết luận chi phí offline đối với attacker; môi trường GPU/ASIC và khả năng song song của attacker khác server Java.

### 13.1. Vì sao hash càng chậm không phải lúc nào cũng càng tốt?

Nếu m/t/p quá cao:

- Người dùng thấy login/reset chậm.
- Peak CPU hoặc RAM có thể gây timeout, GC, lỗi OOM và tăng chi phí hạ tầng.
- Một đợt credential-stuffing có thể trở thành **denial of service** làm server bị nghẽn.
- Container auto-scaling có thể không mở rộng kịp nhu cầu.
- Khi có nhiều node, mỗi node dùng library/provider khác có thể có latency khác nhau.

**Mục tiêu không phải tối đa hóa độ chậm**, mà là tăng chi phí đoán offline trong giới hạn latency/tài nguyên/availability được phép, cộng các cơ chế chặn tấn công online khác.

## 14. Dữ liệu đầu vào: độ dài, Unicode, normalization và secret handling

### 14.1. Độ dài mật khẩu

- Đừng đặt giới hạn tối đa quá thấp chỉ vì database schema hoặc một form UI cũ.
- Với bcrypt cần đặc biệt lưu ý giới hạn **72 byte** đầu vào.
- Phân biệt byte UTF-8 và số ký tự Java String; dấu tiếng Việt và emoji có thể nhiều byte.
- Nếu hỗ trợ passphrase dài, đặt giới hạn tài nguyên đủ lớn nhưng vẫn bảo vệ khỏi request cực lớn gây DoS.
- Không tự cắt password bằng substring() trước hashing.
- Không thay đổi trim/case-fold/normalization của password giữa registration và login.

### 14.2. Unicode và normalization

Giả sử người dùng đăng ký bằng một chuỗi có dấu tiếng Việt ở dạng Unicode tổ hợp, rồi đăng nhập bằng dạng dựng sẵn trông giống hệt. Nếu application không có quy tắc normalization thống nhất, password có thể không khớp.

Đừng tự normalize trong một nhánh mà quên nhánh khác; cần quyết định theo UX, chuẩn nhận diện, security policy và backward compatibility. Việc thay normalization có thể khiến nhiều password cũ không xác minh được. Nếu cần migration, hãy thực hiện theo kế hoạch có kiểm thử, không thử nhiều biến thể âm thầm thiếu review.

### 14.3. Pepper và quản lý secret

Pepper có thể giúp giảm tác hại của một cuộc tấn công chỉ lấy được database nhưng **không lấy được secret manager**. Tuy nhiên pepper cũng làm việc xác minh phụ thuộc một secret khác và yêu cầu:

- Quản lý qua KMS/HSM/secret store với quyền hạn tối thiểu.
- Định nghĩa cách dùng HMAC hay thiết kế hợp lệ, không tự trộn chuỗi thiếu audit.
- Plan rotation, secrets version và xử lý khi pepper bị lộ.
- Backup/restore và disaster recovery phải giữ khả năng xác minh phù hợp.
- Không in pepper, raw password hoặc hash trong logs, metrics và tracing.

Không bắt buộc mọi ứng dụng phải dùng pepper. **Mật khẩu đủ mạnh + password hashing tốt + MFA + rate limit + database security** thường là nền tảng quan trọng hơn việc tự thêm một cơ chế pepper không kiểm soát.

## 15. Những lỗi phổ biến và cách sửa

| Sai lầm | Vì sao rủi ro? | Cách làm đúng |
| --- | --- | --- |
| Lưu plain text password | Database bị đọc là lộ ngay credential. | Dùng encoder password hashing phù hợp. |
| Lưu SHA-256(password) không cost/salt | Cho phép đoán offline tốc độ cao. | Argon2id, scrypt, bcrypt hoặc PBKDF2 với parameters phù hợp. |
| Dùng một salt chung cho toàn bộ user | Cùng password có thể cho cùng kết quả, mất lợi ích salt theo user. | Salt ngẫu nhiên riêng mỗi lần encode. |
| Dùng BCryptPasswordEncoder.matches() bằng cách so hai lần encode() | Salt khiến hash mới khác hash cũ. | Gọi matches(raw, stored). |
| Chọn cost theo giá trị mặc định và không benchmark | Không biết có đáp ứng baseline/latency/memory không. | Đối chiếu khuyến nghị hiện hành, đo trên môi trường thật. |
| Dùng 310k PBKDF2 iterations và gọi đó là baseline OWASP hiện hành | Nhầm default framework với khuyến nghị external. | Xem baseline 600k HMAC-SHA-256 được đề cập và tune theo policy. |
| Dùng scrypt N=2^16 từ factory mà tin đạt OWASP N=2^17 | Thấp hơn một mốc tham khảo cụ thể. | Phân biệt demo/default với production target. |
| Dùng Argon2 factory 16 MiB và tưởng đang dùng 19 MiB | Sai tham số memory thực. | Cấu hình tường minh, đo và document m/t/p. |
| Tăng m/t/p cực cao để “an toàn nhất” | Login trở thành DoS hoặc cạn RAM. | Benchmark concurrency và đặt quota/rate limit. |
| Dùng bcrypt cho passphrase dài mà không xét 72 byte | Nguy cơ mất phần input theo hành vi bcrypt. | Chính sách input rõ hoặc chọn thuật toán phù hợp. |
| Tự động fallback unknown hash id sang noop | Stored data có thể bị so với plaintext. | Fail closed, inventory/migration hoặc reset password. |
| Xóa khả năng verify hash cũ ngay khi deploy policy mới | Người dùng không đăng nhập được. | DelegatingPasswordEncoder và migration theo đợt. |
| In raw password/hash vào console để debug | Rò credentials qua log và telemetry. | Chỉ log algorithm id/counters, không log secret. |
| Rehash trước khi credential được xác minh | Attacker có thể kích hoạt thay đổi không hợp lệ. | Chỉ rehash sau successful authentication. |
| Hash password ở frontend và xem hash là credential bí mật | Hash có thể trở thành password tương đương để replay. | Dùng TLS, giao thức xác thực và backend password hashing phù hợp. |
| Dùng PBKDF2 rồi tuyên bố tuân thủ FIPS | Thuật toán không bằng validated module/mode. | Kiểm provider, boundary và yêu cầu compliance. |
| Tắt rate limiting vì đã dùng slow hash | Offline và online là hai tình huống khác. | Giữ rate limit, MFA, chống credential stuffing. |

Một lỗi liên quan Spring Security nữa: nếu UserDetails#getPassword() trả raw password hoặc một hash không tương thích với PasswordEncoder bean, DaoAuthenticationProvider có thể từ chối login; **đừng sửa bằng NoOpPasswordEncoder**. Hãy xác định chính xác định dạng hash và encoder.

## 16. Spring MVC, WebFlux và nơi đặt password hashing

Trong Spring MVC với username/password:

~~~text
HTTP request -> Servlet authentication filter
             -> AuthenticationManager / DaoAuthenticationProvider
             -> UserDetailsService.loadUserByUsername
             -> PasswordEncoder.matches(raw, stored)
             -> Authentication / SecurityContext
~~~

Trong WebFlux:

~~~text
HTTP request -> SecurityWebFilterChain
             -> ReactiveAuthenticationManager
             -> ReactiveUserDetailsService.findByUsername
             -> PasswordEncoder.matches(raw, stored) trong luồng được quản lý
             -> Authentication / Reactor Context
~~~

**PasswordEncoder vẫn là hợp đồng đồng bộ** ngay cả khi được gọi trong reactive pipeline. BCrypt/PBKDF2/scrypt/Argon2id có chi phí CPU và có thể tiêu thụ RAM lớn. Không xem Mono là phép biến công việc hash thành nonblocking.

Nếu tự viết reactive authentication manager, cần đặc biệt tránh chặn event-loop và quản lý scheduler/độ đồng thời. Với cơ chế mặc định của Spring Security, hãy kiểm implementation của đúng version và đo latency thực, không tự thêm .block() trong WebFlux Controller/WebFilter.

Một lần nữa: **UserDetailsService và ReactiveUserDetailsService chỉ tra user**, PasswordEncoder xác minh hash, còn AuthenticationManager/Provider quyết định kết quả xác thực. Authorization như hasRole, scope hoặc object ownership là bước khác; một password đúng không tự cho phép truy cập mọi API.

## 17. Bài tập tự kiểm tra

1. **Hash nhanh:** Vì sao SHA-256(password) không có salt/work factor không phải lựa chọn tốt cho database tài khoản?
2. **Salt:** Hai user dùng cùng password, nếu encode() đúng cơ chế có salt ngẫu nhiên, vì sao hash thường khác nhau?
3. **Pepper:** Pepper khác salt ở tính bí mật và nơi lưu như thế nào? Khi bị lộ thì xử lý ra sao?
4. **BCrypt:** cost 12 và cost 10 khác nhau về lượng công việc như thế nào? Vì sao giới hạn 72 **byte** đáng chú ý với mật khẩu Unicode?
5. **PBKDF2:** Điều kiện FIPS có khiến bất cứ PBKDF2PasswordEncoder nào tự động compliant không? Cần xem những yếu tố nào?
6. **SCrypt:** Với N=65.536, r=8, công thức gần đúng 128×N×r cho bao nhiêu MiB? Tại sao concurrent requests khiến bài toán RAM nghiêm trọng hơn?
7. **Argon2id:** Phân biệt m/t/p. Vì sao tăng p không đơn giản là nhân lượng RAM m lên p?
8. **Default:** Spring Security Argon2 factory v5_8 16 MiB, nhưng OWASP đề cập 19 MiB. Bạn sẽ quyết định tham số production thế nào?
9. **Migration:** DB lưu bcrypt hash raw format, encoder mới là Argon2id. Vì sao đổi bean trực tiếp có thể làm login thất bại?
10. **Delegating:** Hash có prefix {bcrypt} được xác minh bằng encoder nào? Hash mới dùng id nào nếu cấu hình idForEncode là argon2id-m19456-t2-p1?
11. **Rehash:** Có được rehash một account trước khi xác minh raw password không? Làm sao tránh ghi đè password vừa được thay đổi đồng thời?
12. **Rate limiting:** Vì sao hash memory-hard mạnh không ngăn credential stuffing qua API?
13. **Load test:** Hãy thiết kế thử nghiệm 10/50/100 login đồng thời với m/t/p đã chọn. Theo dõi CPU, RSS, GC, p95, p99 và error rate.
14. **Phân biệt:** Password hash có thay encryption cho dữ liệu phải giải mã để sử dụng lại không? Vì sao không?
15. **Audit:** Nếu phát hiện bảng hash đã lộ, cần làm gì ngoài việc đổi thuật toán hash? Gợi ý: incident response, reset, MFA, audit, session/token revocation và kiểm soát quyền truy cập.
16. **Phiên bản:** Vì sao project mới nên sử dụng bản Spring Boot/Spring Security/Bouncy Castle đang được hỗ trợ thay vì copy nguyên pin của một bài lab cũ?

### Checklist lựa chọn thuật toán

- **Argon2id** thường là hướng ưu tiên cho hệ thống mới khi đáp ứng được RAM/runtime và không vướng yêu cầu compliance khác.
- **scrypt** là lựa chọn memory-hard thay thế khi không dùng được Argon2id; kiểm N/r/p và memory concurrency.
- **PBKDF2-HMAC-SHA-256** phù hợp với nhiều yêu cầu chuẩn/FIPS nếu có **validated implementation**, đủ iterations và quản lý provider đúng.
- **bcrypt** vẫn hữu ích cho legacy/compatibility; kiểm cost, giới hạn 72 byte và kế hoạch migration.
- **Salt ngẫu nhiên, riêng** cho từng hash; pepper là bí mật bổ sung tùy nhu cầu, không thay salt.
- **Không dùng fast digest hoặc plaintext** làm phương án lưu mật khẩu.
- **Spring Security default không tự đồng nghĩa khuyến nghị OWASP hiện hành**; so thông số cụ thể.
- **Benchmark CPU/RAM/latency dưới tải**; tránh DoS khi cost quá cao.
- **DelegatingPasswordEncoder** dùng id để xác minh nhiều loại hash; rehash chỉ sau login hợp lệ.
- **Không fallback unknown algorithm id sang NoOp**, không ghi raw password/hash vào log.
- **HTTPS, MFA, rate limit, lifecycle credential và security patch** vẫn quan trọng.

## Tài liệu tham khảo và cách dùng tài liệu

1. [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): giao diện PasswordEncoder, BCrypt/PBKDF2/SCrypt/Argon2 và DelegatingPasswordEncoder.
2. [Spring Security 6.3 — API Index](https://docs.spring.io/spring-security/site/docs/6.3.0/api/index-all.html): factory và method signature cho những encoder được dùng trong lab.
3. [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): baseline lựa chọn Argon2id, scrypt, bcrypt, PBKDF2 và lưu ý pepper.
4. [RFC 9106 — Argon2 Memory-Hard Function](https://www.rfc-editor.org/rfc/rfc9106): định nghĩa và khuyến nghị tham số m/t/p cho Argon2.
5. [Spring Security — Crypto Module](https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html): cơ chế các PasswordEncoder trong framework.
6. [NIST Digital Identity Guidelines — Passwords](https://pages.nist.gov/800-63-4/sp800-63b.html): các yêu cầu hiện hành về memorized secrets và vòng đời xác thực; cần đối chiếu chính sách cơ quan khi triển khai.

**Lưu ý về thời điểm và phiên bản:** Các mức như Argon2id m=19 MiB/t=2/p=1, scrypt N=2^17/r=8/p=1 và PBKDF2-HMAC-SHA-256 600.000 iterations là các **mốc tham khảo từ OWASP tại thời điểm soạn**, không phải điều luật vĩnh viễn. Một project thật cần kiểm tài liệu cập nhật, yêu cầu nội bộ, bản vá và benchmark trước khi ra quyết định. Phiên bản Spring Boot 3.3.6 của lab chỉ nhằm giữ code minh họa nhất quán với Spring Security 6.3.x.

## Kết luận

**BCrypt, PBKDF2, SCrypt và Argon2id đều có thể bảo vệ password khi được dùng đúng, nhưng không có một bộ tham số phù hợp cho mọi hệ thống.** Chọn thuật toán phải xét khả năng chống đoán offline, RAM/CPU, loại mật khẩu, FIPS/compliance, tương thích hash cũ và khả năng vận hành dưới tải. Với ứng dụng mới, Argon2id là ứng viên ưu tiên nếu đáp ứng điều kiện; với hệ thống cần validated crypto module có thể chọn PBKDF2; với legacy bcrypt cần giữ xác minh và nâng cấp có kiểm soát. Trong Spring Security, **PasswordEncoder** giúp encode/matches, **DelegatingPasswordEncoder** giúp giữ nhiều format và migrate, nhưng **chất lượng bảo mật phụ thuộc vào parameters, đo lường, secret handling và quy trình xác thực thực tế** — không chỉ tên class đã import.
