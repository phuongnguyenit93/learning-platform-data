# Password verification: lưu trữ và xác minh mật khẩu an toàn

> **Chương:** Password authentication  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** nghiên cứu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào cách hệ thống lưu bằng chứng mật khẩu, xác minh lần đăng nhập, chống đoán mật khẩu và xử lý vòng đời credential an toàn.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao máy chủ không lưu mật khẩu dạng rõ và phân biệt password hashing với mã hóa có thể giải ngược.
2. Mô tả quy trình tạo password hash với salt riêng, thuật toán chuyên dụng và tham số chi phí.
3. So sánh Argon2id, scrypt, bcrypt và PBKDF2 trong bối cảnh lưu trữ mật khẩu.
4. Thiết kế xác minh mật khẩu với thông báo lỗi nhất quán, so sánh an toàn và kiểm soát lạm dụng đăng nhập.
5. Xử lý pepper, nâng cấp hash, đổi mật khẩu, khôi phục tài khoản và dữ liệu rò rỉ.
6. Sử dụng thư viện Java/Spring phù hợp, không tự thiết kế thuật toán mật khẩu.
7. Kiểm thử các tình huống sai mật khẩu, tài khoản không tồn tại, hash cũ, credential bị lộ và đăng nhập đồng thời.

## 2. Password verification là gì?

**Password verification (xác minh mật khẩu)** là quá trình kiểm tra xem mật khẩu người dùng vừa cung cấp có khớp với mật khẩu đã đăng ký hay không. Hệ thống không cần biết lại mật khẩu ban đầu; nó chỉ cần xác minh đầu vào bằng một phép tính phù hợp với hash đã lưu.

Khi tạo tài khoản hoặc đổi mật khẩu:

1. Nhận mật khẩu qua kênh bảo vệ, thông thường là HTTPS/TLS.
2. Kiểm tra chính sách độ dài, danh sách mật khẩu phổ biến/bị lộ và các quy tắc liên quan.
3. Tạo salt ngẫu nhiên riêng cho credential.
4. Dùng thuật toán password hashing chuyên dụng với tham số chi phí đã chọn để tạo hash.
5. Lưu chuỗi hash đã mã hóa định dạng cùng thông tin thuật toán, salt và tham số cần thiết.

Khi đăng nhập:

1. Nhận tên đăng nhập và mật khẩu.
2. Tìm bản ghi credential của tài khoản theo định danh đã chuẩn hóa.
3. Dùng thuật toán và tham số ghi trong hash đã lưu để tính toán, so sánh mật khẩu được nhập.
4. Nếu khớp, tiếp tục các kiểm tra trạng thái tài khoản, MFA/rủi ro và thiết lập phiên.
5. Nếu hash dùng tham số cũ, có thể nâng cấp sau khi xác minh thành công.

Mô hình:

~~~text
Đăng ký / đổi mật khẩu:
password + unique random salt + password-hash parameters
                   |
                   v
             Password KDF
                   |
                   v
       encoded password hash -> database

Đăng nhập:
submitted password + stored encoded hash
                   |
                   v
     verify using stored algorithm/parameters
                   |
             match / no match
~~~

**Hash mật khẩu không phải mã hóa mật khẩu.** Mã hóa thường có thể giải mã khi có khóa; password hashing được thiết kế để xác minh mà không cần khôi phục mật khẩu gốc. Nếu cơ sở dữ liệu bị đánh cắp, kẻ tấn công vẫn có thể thử đoán mật khẩu ngoại tuyến, nên thuật toán phải làm mỗi lần thử đủ tốn kém.

## 3. Vì sao không lưu mật khẩu dạng rõ?

Nếu cơ sở dữ liệu lưu mật khẩu trực tiếp, một lần rò rỉ có thể làm lộ ngay thông tin đăng nhập của tất cả người dùng. Người dùng còn có thể tái sử dụng mật khẩu ở nhiều dịch vụ, khiến rủi ro lan sang hệ thống khác.

| Cách lưu | Nếu database bị lộ | Đánh giá |
|---|---|---|
| Plaintext | Kẻ tấn công đọc ngay mật khẩu | Không chấp nhận |
| Mã hóa đối xứng với một khóa dùng chung | Kẻ tấn công có thể giải mã nếu lấy được khóa; khóa có thể bị lộ cùng hệ thống | Không phải cách lưu password verifier mặc định |
| Hash nhanh như MD5, SHA-1, SHA-256 thuần | Kẻ tấn công thử rất nhiều phỏng đoán mỗi giây, đặc biệt với mật khẩu yếu | Không phù hợp để lưu mật khẩu |
| Hash chuyên dụng, salt riêng, tham số chi phí phù hợp | Mỗi lần đoán tốn tài nguyên hơn; salt ngăn bảng tra cứu dùng chung | Cách lưu phù hợp |

TLS bảo vệ mật khẩu khi truyền qua mạng; password hashing bảo vệ verifier khi lưu trữ. Hai lớp giải quyết hai rủi ro khác nhau. Hash mạnh không bảo vệ người dùng khỏi trang phishing, keylogger hoặc mã độc đọc mật khẩu trước khi gửi.

## 4. Salt: mỗi mật khẩu cần một giá trị ngẫu nhiên riêng

**Salt** là giá trị ngẫu nhiên được tạo cho từng password hash và được lưu cùng encoded hash. Salt không phải bí mật. Mục tiêu là bảo đảm cùng một mật khẩu không tạo ra cùng một hash giữa các tài khoản và khiến bảng rainbow table/tập hash tính sẵn khó dùng lại.

Ví dụ:

~~~text
An:
  password = "correct horse ..."
  salt     = random-A
  hash     = KDF(password, random-A, parameters)

Bình:
  password = "correct horse ..."
  salt     = random-B
  hash     = KDF(password, random-B, parameters)

random-A != random-B
=> stored hashes khác nhau
~~~

Quy tắc:

- Sinh salt bằng bộ tạo số ngẫu nhiên mật mã của nền tảng (CSPRNG), không dùng timestamp, user ID hoặc chuỗi cố định.
- Mỗi lần tạo credential/hash mới phải có salt riêng.
- Salt được lưu cùng hash để máy chủ có thể xác minh về sau.
- Độ dài salt và cách mã hóa phải theo thư viện/chuẩn đang dùng; thực hành hiện đại thường dùng salt ngẫu nhiên ít nhất 16 byte.
- Không tái sử dụng một salt toàn hệ thống cho mọi người dùng.

**Salt không phải pepper.** Salt công khai và riêng cho từng hash; pepper là bí mật bổ sung do hệ thống quản lý tách khỏi cơ sở dữ liệu. Không dùng salt thay cho pepper hoặc ngược lại.

## 5. Chọn thuật toán password hashing

Thuật toán lưu mật khẩu cần làm cho mỗi lần thử đoán tốn tài nguyên, đặc biệt là bộ nhớ và/hoặc CPU. Không dùng hash tổng quát nhanh như SHA-256 một lần để lưu mật khẩu.

| Thuật toán | Đặc tính | Khi cân nhắc |
|---|---|---|
| **Argon2id** | Password hashing memory-hard; kết hợp khả năng chống tấn công dựa trên bộ nhớ và các đặc tính của Argon2 | Lựa chọn ưu tiên phổ biến cho hệ thống mới khi thư viện và môi trường hỗ trợ |
| **scrypt** | Memory-hard KDF, thiết kế để làm tăng chi phí phần cứng chuyên dụng | Phù hợp khi có triển khai đã được kiểm chứng và tham số được hiệu chỉnh |
| **bcrypt** | Thuật toán password hashing lâu đời, điều chỉnh chi phí CPU; có giới hạn độ dài đầu vào cần lưu ý | Thường gặp trong hệ thống hiện hữu; cần quản lý giới hạn byte và kế hoạch nâng cấp |
| **PBKDF2** | Lặp hàm dẫn xuất khóa dựa trên PRF, thường HMAC; có triển khai rộng và profile được chuẩn hóa | Có thể phù hợp môi trường yêu cầu FIPS hoặc nền tảng có hỗ trợ chuẩn tương ứng; phải chọn số vòng đủ mạnh |
| **MD5/SHA-1/SHA-256 thuần** | Hàm băm tổng quát, rất nhanh | Không dùng trực tiếp để lưu mật khẩu |

### 5.1. Vì sao Argon2id và scrypt hữu ích?

Kẻ tấn công có thể lấy bản sao database và thử đoán mật khẩu ngoại tuyến. Một KDF memory-hard buộc mỗi lần đoán phải tiêu tốn một lượng bộ nhớ và thời gian nhất định. Điều này làm giảm lợi thế của GPU/ASIC khi thử hàng tỷ phỏng đoán, dù không thể biến mật khẩu yếu thành bí mật mạnh tuyệt đối.

Argon2 có nhiều biến thể. **Argon2id** thường được ưu tiên cho password storage vì kết hợp đặc tính bảo vệ trước các kiểu tấn công dựa trên bộ nhớ và side-channel theo thiết kế của thuật toán. Dùng thư viện được duy trì, profile được khuyến nghị và định dạng encoded hash có lưu tham số.

### 5.2. Chi phí phải được hiệu chỉnh

Không có một cấu hình phù hợp mọi máy chủ. Tham số cần cân bằng:

- **Memory cost:** lượng bộ nhớ cho mỗi lần xác minh đồng thời.
- **Time cost / iterations:** số vòng hoặc mức công việc.
- **Parallelism:** mức song song mà thuật toán sử dụng.
- **Throughput:** số lần đăng nhập hợp lệ hệ thống cần xử lý.
- **Abuse resistance:** khả năng chống đoán ngoại tuyến và không để đăng nhập trực tuyến gây cạn CPU/RAM.

Hiệu chỉnh trên phần cứng production-like, đo p95/p99 latency và thử tải đồng thời. Cấu hình quá thấp khiến hash dễ bị đoán; cấu hình quá cao có thể bị lạm dụng để làm cạn tài nguyên bằng cách gửi nhiều lần đăng nhập. Phải kết hợp KDF đủ mạnh với rate limiting và kiểm soát tải.

### 5.3. Lưu định dạng tự mô tả

Encoded hash nên mang theo thuật toán, phiên bản, salt và tham số để hệ thống xác minh đúng cách và nâng cấp khi cần. Ví dụ hình thức Argon2id:

~~~text
$argon2id$v=19$m=<memory>,t=<time>,p=<parallelism>$<salt>$<hash>
~~~

Đây là sơ đồ định dạng, các giá trị trong dấu ngoặc là chỗ giữ chỗ. Không tự cắt chuỗi hash để suy luận tham số bằng logic tùy tiện; dùng parser/thư viện tương ứng.

## 6. Pepper: bí mật bổ sung ngoài database

**Pepper** là bí mật bổ sung mà hệ thống có thể kết hợp với mật khẩu trước hoặc sau KDF theo một thiết kế được hỗ trợ, nhưng phải được lưu **tách khỏi password database** — ví dụ secret manager hoặc HSM phù hợp.

| Đặc điểm | Salt | Pepper |
|---|---|---|
| Có bí mật không? | Không | Có |
| Phạm vi | Riêng cho từng hash | Thường dùng chung theo phiên bản/nhóm hệ thống |
| Lưu ở đâu? | Cùng encoded hash | Secret manager/HSM, tách khỏi database |
| Mục tiêu | Ngăn hash giống nhau, chống bảng tra cứu dùng chung | Thêm một lớp bảo vệ nếu chỉ database bị lấy cắp |
| Khi thay đổi | Mỗi hash mới có salt mới | Cần kế hoạch phiên bản hóa và xử lý khi xoay/mất pepper |

Pepper không thay thế salt, KDF hoặc bảo vệ database. Nếu ứng dụng và secret manager cùng bị xâm nhập, lớp bảo vệ này có thể mất. Nếu pepper bị mất, hệ thống có thể không xác minh được các hash phụ thuộc nó; vì vậy phải có kế hoạch backup/rotation và quy trình chuyển đổi.

Không hardcode pepper trong source code, image container, repository hoặc biến cấu hình công khai. Quyền đọc secret cần tối thiểu và có audit.

## 7. Quy trình xác minh mật khẩu an toàn

Khi người dùng gửi form đăng nhập, server nên thực hiện các bước theo một thứ tự có chủ đích:

1. Nhận username/password qua HTTPS và kiểm tra kích thước đầu vào để tránh payload bất thường.
2. Chuẩn hóa định danh tài khoản theo quy tắc nhất quán (ví dụ email không phân biệt hoa/thường nếu chính sách quy định); không tùy tiện thay đổi mật khẩu đã nhập.
3. Tìm credential record; nếu không có tài khoản, vẫn xử lý theo cách tránh tiết lộ sự tồn tại của tài khoản.
4. Xác minh password với encoded hash và thư viện KDF.
5. Áp dụng trạng thái tài khoản: disabled, locked theo chính sách, pending recovery hoặc yêu cầu đổi mật khẩu nếu credential bị thu hồi.
6. Kiểm tra MFA/risk/step-up nếu policy yêu cầu.
7. Nếu hợp lệ, rotate session ID hoặc tạo phiên mới; ghi sự kiện bảo mật không chứa mật khẩu/token.
8. Nếu hash cũ hoặc dùng profile yếu, nâng cấp sau xác minh thành công bằng cách tạo salt mới và hash mới.

~~~mermaid
flowchart TD
    A["Nhận username + password qua TLS"] --> B["Kiểm tra kích thước và định dạng"]
    B --> C["Tra credential record"]
    C --> D["Verify bằng KDF và tham số đã lưu"]
    D --> E{"Mật khẩu khớp?"}
    E -->|"Không"| F["Ghi nhận thất bại, áp rate limit"]
    F --> G["Trả lỗi chung"]
    E -->|"Có"| H["Kiểm tra trạng thái tài khoản"]
    H --> I{"Tài khoản hoạt động?"}
    I -->|"Không"| G
    I -->|"Có"| J["MFA / risk / step-up theo policy"]
    J --> K{"Đạt yêu cầu?"}
    K -->|"Không"| G
    K -->|"Có"| L["Nâng cấp hash nếu cần"]
    L --> M["Rotate session / tạo phiên mới"]
    M --> N["Đăng nhập thành công"]
~~~

Sơ đồ rút gọn; triển khai thực tế có thể kiểm tra rate limit trước khi chạy KDF, xử lý tài khoản không tồn tại bằng dummy hash và quản lý lockout theo chính sách. Mục tiêu là không tạo khác biệt dễ khai thác giữa các trường hợp tài khoản không tồn tại, sai mật khẩu hoặc bị khóa.

## 8. So sánh mật khẩu an toàn và timing

Không nên tự viết code so sánh chuỗi hash bằng vòng lặp dừng ngay khi ký tự đầu tiên khác nhau. Thời gian thực thi có thể tiết lộ một phần thông tin về kết quả so sánh.

Hãy dùng thư viện password encoder/KDF có hàm verify chuyên dụng. Hàm này cần xử lý so sánh an toàn theo thiết kế của thư viện. Không tự triển khai Argon2, bcrypt hoặc phép so sánh hash.

Ngoài timing của phép so sánh, toàn bộ luồng đăng nhập có thể rò rỉ thông tin qua:

- Thông báo lỗi khác nhau giữa “không có tài khoản” và “sai mật khẩu”.
- HTTP status code, redirect, kích thước response hoặc nội dung response khác nhau.
- Thời gian xử lý khác biệt đáng kể khi tài khoản tồn tại và không tồn tại.
- Rate limit chỉ áp dụng cho một nhánh, cho phép dò tên đăng nhập.

### Chống account enumeration

Phản hồi công khai nên nhất quán, ví dụ: **“Tên đăng nhập hoặc mật khẩu không đúng.”** Không xác nhận email có đăng ký hay tài khoản đang bị khóa trong màn hình đăng nhập thông thường. Kênh hỗ trợ hoặc recovery đã xác thực có thể cung cấp hướng dẫn phù hợp hơn.

Để giảm chênh lệch timing, một số hệ thống dùng một dummy password hash hợp lệ khi không tìm thấy tài khoản và vẫn thực hiện một lần verify có chi phí tương tự. Đây là biện pháp giảm tín hiệu, không bảo đảm thời gian tuyệt đối giống nhau; cần đo thực tế và tránh làm endpoint dễ bị DoS.

## 9. Rate limiting và chống lạm dụng đăng nhập

Password hashing làm tốn tài nguyên cho mỗi lần thử. Đăng nhập trực tuyến còn cần giới hạn số lần thử để ngăn brute force, password spraying và credential stuffing.

| Kiểu lạm dụng | Dấu hiệu | Biện pháp |
|---|---|---|
| Brute force một tài khoản | Nhiều mật khẩu khác nhau cho cùng account | Giới hạn theo account, progressive delay, phát hiện bất thường |
| Password spraying | Một vài mật khẩu phổ biến thử trên nhiều account | Theo dõi theo IP/ASN, account cohort, thiết bị và thời gian |
| Credential stuffing | Thử cặp username/password bị lộ từ dịch vụ khác | Rate limit đa chiều, phát hiện tự động, blocklist password bị lộ, MFA/passkey |
| Distributed guessing | Nhiều IP hoặc proxy cùng thử một account | Tín hiệu theo account, thiết bị, mạng và hành vi; không chỉ giới hạn theo IP |
| Enumeration | Thăm dò account tồn tại qua phản hồi | Thông báo chung, response/timing nhất quán, giới hạn tốc độ |
| Login DoS | Cố tình kích hoạt lockout hoặc KDF tốn tài nguyên | Progressive controls, không khóa cứng dễ bị lợi dụng, giới hạn concurrency và tải |

Rate limit nên kết hợp nhiều chiều: account identifier, IP/ASN, device/session, nguồn request và hành vi. Chỉ giới hạn theo IP sẽ gây vấn đề với NAT/mạng dùng chung; chỉ khóa cứng account sau vài lần sai có thể cho phép kẻ tấn công khóa tài khoản nạn nhân.

CAPTCHA có thể là một tín hiệu bổ sung khi có rủi ro tự động hóa, nhưng không thay thế rate limiting, bảo vệ credential, MFA hoặc giám sát.

## 10. Mật khẩu đầu vào: độ dài, Unicode và blocklist

Password verification chỉ an toàn khi bước nhận mật khẩu không âm thầm biến đổi hoặc cắt cụt giá trị.

- Cho phép mật khẩu dài và hỗ trợ passphrase; giới hạn tối đa cần đủ lớn để tránh DoS, nhưng không được cắt ngắn mà người dùng không biết.
- Không áp đặt quy tắc thành phần phức tạp máy móc như bắt buộc một chữ hoa, một số và một ký tự đặc biệt nếu không có yêu cầu phù hợp; tập trung vào độ dài, mật khẩu phổ biến/bị lộ và MFA.
- Cho phép password manager, paste và autofill; đây là công cụ giúp tạo và dùng mật khẩu duy nhất.
- Không ép người dùng đổi mật khẩu định kỳ nếu không có dấu hiệu compromise hoặc lý do chính sách cụ thể.
- Có thể dùng danh sách mật khẩu phổ biến, đã bị lộ hoặc dễ đoán để chặn khi tạo/đổi mật khẩu; thông báo cần giúp người dùng chọn mật khẩu khác mà không tiết lộ thông tin nhạy cảm.
- Nếu hỗ trợ Unicode, xác định quy tắc chuẩn hóa (chẳng hạn NFC) và áp dụng nhất quán khi tạo lẫn xác minh. Không tự ý trim khoảng trắng, đổi chữ hoa/thường hoặc chuẩn hóa khác nhau giữa hai luồng.
- Kiểm tra giới hạn độ dài theo byte/encoding mà thư viện thực sự sử dụng; đặc biệt lưu ý giới hạn đầu vào của bcrypt và không để hai mật khẩu khác nhau bị cắt thành cùng một chuỗi.

NIST và các hướng dẫn hiện đại nhấn mạnh mật khẩu đủ dài, kiểm tra blocklist và hỗ trợ password manager; quy tắc chính xác cần đối chiếu ấn bản chuẩn/chính sách áp dụng tại thời điểm triển khai.

## 11. Java/Spring: dùng PasswordEncoder thay vì tự viết KDF

Spring Security cung cấp interface PasswordEncoder để tạo và xác minh encoded password. Ví dụ sau chọn Argon2id profile do thư viện cung cấp; cần dependency/provider tương ứng và phải hiệu chỉnh profile theo tải thực tế.

~~~java
@Configuration
class PasswordConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        // Dùng profile Argon2id được thư viện cung cấp.
        // Kiểm tra dependency/provider và hiệu chỉnh chi phí theo môi trường.
        return Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
    }
}
~~~

Đăng ký và đăng nhập:

~~~java
@Service
class PasswordService {
    private final PasswordEncoder encoder;
    private final UserRepository users;

    PasswordService(PasswordEncoder encoder, UserRepository users) {
        this.encoder = encoder;
        this.users = users;
    }

    void setInitialPassword(UUID userId, String rawPassword) {
        validatePasswordPolicy(rawPassword);
        String encoded = encoder.encode(rawPassword);
        users.updatePasswordHash(userId, encoded);
    }

    boolean verify(UUID userId, String rawPassword) {
        User user = users.findById(userId)
            .orElseThrow(InvalidCredentialsException::new);

        boolean matches = encoder.matches(
            rawPassword, user.passwordHash()
        );
        if (!matches) {
            return false;
        }

        if (encoder.upgradeEncoding(user.passwordHash())) {
            String upgraded = encoder.encode(rawPassword);
            users.replacePasswordHashIfUnchanged(
                userId, user.passwordHash(), upgraded
            );
        }
        return true;
    }

    private void validatePasswordPolicy(String password) {
        if (password == null || password.isEmpty()) {
            throw new InvalidPasswordException();
        }
        // Thêm kiểm tra độ dài, blocklist và chính sách Unicode.
        // Không log password hoặc ghi raw password vào exception.
    }
}
~~~

Đây là ví dụ khung; repository, exception, validation và giao dịch DB do ứng dụng định nghĩa. upgradeEncoding biểu diễn kiểm tra xem hash hiện tại có cần nâng cấp không. replacePasswordHashIfUnchanged biểu diễn cập nhật có điều kiện để tránh ghi đè một mật khẩu vừa được đổi trong request khác. Đoạn verify giả định userId đã được tra cứu ở lớp trước; không dùng nhánh orElseThrow khác biệt này trực tiếp làm phản hồi công khai cho endpoint đăng nhập. Luồng đăng nhập thực cần xử lý tài khoản không tồn tại bằng phản hồi chung và có thể dùng dummy hash để giảm chênh lệch timing, đồng thời áp dụng rate limit trước/đồng thời với phép tính KDF.

**Không lưu rawPassword sau khi verify**, không trả password hash về client và không ghi mật khẩu/token vào log. Nếu dùng DelegatingPasswordEncoder, giữ prefix định danh thuật toán để hệ thống chọn encoder đúng khi xác minh và có kế hoạch loại bỏ profile cũ.

## 12. Nâng cấp hash và di trú dữ liệu

Thuật toán và tham số có thể trở nên yếu theo thời gian hoặc không còn phù hợp với phần cứng hiện tại. Vì vậy encoded hash cần cho biết nó được tạo bằng profile nào.

Quy trình nâng cấp phổ biến:

1. Khi người dùng đăng nhập, xác minh bằng đúng thuật toán/tham số ghi trong hash cũ.
2. Nếu thành công và profile hiện tại yêu cầu chi phí cao hơn hoặc thuật toán mới, tạo salt mới và hash lại từ mật khẩu vừa được cung cấp.
3. Cập nhật bản ghi bằng thao tác an toàn, tránh ghi đè một mật khẩu vừa được đổi trong request khác.
4. Nếu người dùng không đăng nhập trong thời gian dài, có thể yêu cầu đổi mật khẩu hoặc recovery theo chính sách thay vì cố khôi phục mật khẩu gốc.

Không thể nâng cấp hash cũ lên hash mới chỉ từ hash cũ, vì password hashing không thể giải ngược. Muốn tạo hash mới cần mật khẩu gốc do người dùng cung cấp trong lần đăng nhập hoặc sau khi đặt lại.

### Đổi thuật toán khi có legacy hash

| Hash đang lưu | Hành động |
|---|---|
| Argon2id với profile hiện hành | Xác minh và giữ nguyên nếu vẫn đạt policy |
| Argon2id/scrypt với tham số cũ | Xác minh, rehash khi đăng nhập thành công |
| bcrypt với cost thấp | Xác minh, rehash bằng profile mới sau thành công |
| PBKDF2 với tham số cũ | Xác minh bằng cấu hình cũ, sau đó nâng cấp theo policy |
| MD5/SHA-1/SHA-256 thuần hoặc plaintext legacy | Lên kế hoạch di trú có kiểm soát; cân nhắc buộc reset thay vì coi hash cũ là bảo vệ đủ mạnh |

Khi xử lý dữ liệu legacy, không tự động ghi đè hash nếu xác minh thất bại. Ghi nhận phiên bản thuật toán, theo dõi tỷ lệ tài khoản chưa di trú và đặt thời hạn kết thúc hỗ trợ profile yếu.

## 13. Đổi mật khẩu và khôi phục tài khoản

**Đổi mật khẩu khi đang đăng nhập** và **khôi phục khi mất quyền truy cập** là hai luồng khác nhau.

### Đổi mật khẩu

- Yêu cầu xác thực lại gần thời điểm thao tác, nhất là khi phiên đã tồn tại lâu hoặc tài khoản có rủi ro cao.
- Kiểm tra mật khẩu mới với blocklist và policy.
- Tạo hash mới bằng salt mới và profile hiện hành.
- Thu hồi hoặc đánh dấu lại các session/refresh token khác theo chính sách; thông báo thay đổi qua kênh liên hệ đã xác minh.
- Không gửi mật khẩu cũ/mới qua log, email hoặc thông báo.

### Khôi phục mật khẩu

- Dùng token khôi phục ngẫu nhiên, khó đoán, thời hạn ngắn và dùng một lần; chỉ lưu verifier/hash của token nếu thiết kế cho phép.
- Ràng buộc token với đúng account và mục đích recovery; không dùng access token thông thường thay token reset.
- Trả thông báo chung để tránh enumeration; gửi hướng dẫn qua kênh đã xác minh.
- Sau khi đặt mật khẩu mới, vô hiệu token recovery và cân nhắc thu hồi session cũ, thông báo sự kiện và yêu cầu MFA.
- Không dùng câu hỏi bảo mật có câu trả lời dễ tìm trên mạng làm bằng chứng khôi phục duy nhất.

Nếu kẻ tấn công có thể chiếm email hoặc số điện thoại khôi phục, luồng reset có thể vô hiệu hóa mọi bảo vệ của mật khẩu. Vì vậy recovery phải có mức assurance tương xứng với tài khoản, có audit và có hỗ trợ khi người dùng mất authenticator.

## 14. Khi nào password hash không đủ?

Password hashing chủ yếu giảm hậu quả khi **database verifier bị đánh cắp**. Nó không ngăn:

- Phishing khiến người dùng nhập mật khẩu vào trang giả.
- Malware/keylogger đọc mật khẩu trước khi gửi.
- Credential stuffing bằng mật khẩu đã lộ ở dịch vụ khác.
- Session cookie/access token bị đánh cắp sau khi đăng nhập.
- Kẻ tấn công khai thác lỗi reset hoặc account linking để chiếm tài khoản.
- Người dùng dùng mật khẩu yếu hoặc tái sử dụng ở nhiều nơi.

Các lớp bổ sung:

| Rủi ro | Lớp kiểm soát |
|---|---|
| Phishing mật khẩu | Passkey/WebAuthn chống phishing, kiểm tra domain, MFA phù hợp |
| Credential stuffing | Blocklist, rate limit, phát hiện tự động, MFA/passkey |
| Lộ database | Argon2id/scrypt/PBKDF2 profile phù hợp, salt riêng, pepper tùy mô hình |
| Chiếm phiên | Cookie an toàn, TLS, session rotation, timeout, revoke và bảo vệ thiết bị |
| Reset takeover | Recovery token một lần, kênh xác minh và chính sách recovery mạnh |
| Lạm dụng endpoint đăng nhập | Rate limiting, giới hạn concurrency KDF, giám sát và phản hồi nhất quán |

Mật khẩu vẫn có thể là một credential trong hệ thống MFA, nhưng với thao tác nhạy cảm nên cân nhắc xác thực tăng cường hoặc passkey thay cho việc chỉ tăng số vòng hash.

## 15. Log, giám sát và bảo vệ dữ liệu

Log đăng nhập cần đủ để điều tra nhưng không được biến thành kho bí mật thứ hai.

Nên ghi:

- Account identifier ở dạng được bảo vệ hoặc định danh nội bộ phù hợp.
- Thời gian server, kết quả thành công/thất bại và lý do nội bộ theo mã phân loại.
- Client/application, request correlation ID và tín hiệu rủi ro cần thiết.
- Sự kiện hash upgrade, password change, recovery và thu hồi session.
- IP/thiết bị ở mức tối thiểu phù hợp với mục đích, quyền riêng tư và chính sách lưu giữ.

Không ghi:

- Raw password, password confirmation, reset token hoặc OTP.
- Access/refresh token, session cookie, client secret, pepper.
- Password hash đầy đủ nếu không cần cho mục đích vận hành; hash cũng là dữ liệu nhạy cảm và không nên đưa vào log phổ thông.

Giới hạn quyền đọc credential table; dùng mã hóa đĩa/database, backup an toàn, audit truy cập và quy trình ứng phó khi phát hiện bản sao dữ liệu bị lấy cắp.

## 16. Ma trận kiểm thử password verification

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Đăng nhập bằng đúng mật khẩu | Verify thành công; sau đó vẫn kiểm tra trạng thái/MFA/policy |
| Mật khẩu sai một ký tự | Từ chối với thông báo chung |
| Username không tồn tại | Không tiết lộ account; xử lý timing/rate limit phù hợp |
| Hai account dùng cùng mật khẩu | Hash khác nhau do salt ngẫu nhiên riêng |
| Hash dùng thuật toán/tham số cũ | Verify theo metadata cũ; rehash sau khi thành công nếu policy yêu cầu |
| Hash bị sửa/truncated/định dạng không hợp lệ | Từ chối an toàn, ghi lỗi nội bộ không làm lộ dữ liệu |
| Database dump bị lộ | Không có plaintext; hash chậm/memory-hard và salt riêng |
| Pepper không truy cập được | Không bypass xác minh; xử lý sự cố secret và recovery theo kế hoạch |
| Nhiều lần đoán trên một account | Rate limit/progressive controls kích hoạt |
| Nhiều account bị thử từ nhiều IP | Phát hiện password spraying/distributed guessing |
| Lockout bị lạm dụng để khóa nạn nhân | Chính sách không tạo DoS dễ dàng; có cách phục hồi |
| Mật khẩu dài hoặc Unicode | Không bị cắt/ngầm biến đổi; tạo và verify nhất quán |
| Đổi mật khẩu đồng thời với login khác | Hash mới không bị ghi đè bởi hash upgrade cũ |
| Reset token được dùng lại hoặc hết hạn | Từ chối; token đã dùng bị vô hiệu |
| Xác minh thành công sau hash cũ | Phiên được tạo an toàn; hash được nâng cấp có điều kiện |

Khi kiểm thử timing và enumeration, đo nhiều lần trong môi trường tương đương production và đánh giá phân bố thời gian/response. Không kết luận an toàn chỉ từ một lần đo hoặc một status code.

## 17. Tình huống phân tích

### Tình huống A: cùng hash cho hai người

Một hệ thống cũ lưu SHA-256(password) mà không có salt. Hai người dùng chọn cùng mật khẩu nên có cùng hash. Kẻ tấn công lấy database và dùng bảng hash tính sẵn để dò các mật khẩu phổ biến.

**Phân tích:** hash nhanh và thiếu salt khiến tấn công ngoại tuyến hiệu quả. Cần chuyển sang password KDF chuyên dụng với salt ngẫu nhiên riêng, quản lý profile và nâng cấp sau xác minh thành công hoặc buộc reset cho nhóm rủi ro.

### Tình huống B: tài khoản không tồn tại phản hồi nhanh hơn

Endpoint đăng nhập trả ngay khi không tìm thấy username, nhưng thực hiện Argon2id khi username tồn tại và mật khẩu sai. Attacker đo thời gian để xây dựng danh sách tài khoản.

**Phân tích:** khác biệt thời gian có thể hỗ trợ enumeration. Dùng phản hồi chung và cân nhắc dummy hash cho nhánh không tìm thấy account; đo timing, rate limit và bảo vệ tải KDF.

### Tình huống C: hash cũ không được nâng cấp

Một tài khoản có bcrypt cost thấp. Người dùng đăng nhập thành công nhưng ứng dụng không kiểm tra upgradeEncoding.

**Phân tích:** hệ thống bỏ lỡ cơ hội di trú. Sau khi verify thành công, tạo hash mới bằng profile hiện hành và cập nhật có điều kiện; không thể rehash nếu không có mật khẩu gốc.

### Tình huống D: pepper bị mất

Nhóm vận hành xoay secret nhưng xóa pepper cũ trước khi tất cả credential được chuyển đổi. Một phần người dùng không thể đăng nhập.

**Phân tích:** pepper có vòng đời và yêu cầu availability. Cần versioning, kế hoạch dual-read/rehash hoặc recovery, backup secret theo chính sách và diễn tập rotation trước khi xóa phiên bản cũ.

## 18. Quy trình thiết kế và vận hành

Trước khi phát hành password authentication, hãy trả lời:

1. Thuật toán/password encoder nào được dùng và vì sao phù hợp?
2. Salt được tạo bằng CSPRNG và có riêng cho từng hash không?
3. Tham số KDF được hiệu chỉnh theo phần cứng, tải đồng thời và mức chống đoán ngoại tuyến như thế nào?
4. Encoded hash có lưu thuật toán/phiên bản/tham số để verify và nâng cấp không?
5. Có cần pepper không; secret được lưu, xoay, backup và thu hồi ra sao?
6. Thông báo lỗi và timing có làm lộ account tồn tại không?
7. Rate limit có bao phủ brute force, spraying, stuffing và phân tán IP không?
8. Mật khẩu dài, password manager, paste và Unicode được xử lý nhất quán không?
9. Đổi mật khẩu, recovery, logout và revoke session có an toàn không?
10. Có log đủ điều tra mà không lưu raw password, hash hay token ngoài nhu cầu không?
11. Khi thuật toán/tham số thay đổi, hệ thống có kế hoạch nâng cấp và loại bỏ hash cũ không?
12. MFA/passkey có được áp dụng cho các thao tác cần assurance cao hơn không?

## 19. Ghi nhớ trọng tâm

- **Không lưu plaintext hoặc hash nhanh thuần.** Dùng password hashing chuyên dụng với salt ngẫu nhiên riêng và tham số chi phí phù hợp.
- **Argon2id thường là lựa chọn ưu tiên cho hệ thống mới** khi thư viện được duy trì và môi trường hỗ trợ; scrypt, bcrypt và PBKDF2 có chỗ dùng theo profile và ràng buộc cụ thể.
- **Salt công khai, pepper bí mật.** Salt nằm cùng hash; pepper phải được quản lý tách khỏi database và có kế hoạch rotation/recovery.
- **Verify bằng thư viện chuyên dụng**, phản hồi nhất quán, chống timing/enumeration và rate limit đa chiều.
- **Nâng cấp hash sau khi xác minh thành công** bằng mật khẩu người dùng vừa cung cấp; không thể chuyển hash cũ sang hash mới chỉ từ hash cũ.
- **Bảo vệ vòng đời credential:** đổi mật khẩu, recovery, session, log, secret và thu hồi phải được thiết kế cùng nhau.
- **Password hashing không chống phishing hay đánh cắp phiên.** Kết hợp MFA/passkey, quản lý phiên và phát hiện lạm dụng để bảo vệ toàn bộ luồng xác thực.

Password verification an toàn không chỉ là chọn một hàm băm. Đó là một quy trình có thể vận hành và nâng cấp: lưu verifier khó đoán ngoại tuyến, xác minh không rò rỉ thông tin, kiểm soát đăng nhập trực tuyến và xử lý credential trong suốt vòng đời tài khoản.
