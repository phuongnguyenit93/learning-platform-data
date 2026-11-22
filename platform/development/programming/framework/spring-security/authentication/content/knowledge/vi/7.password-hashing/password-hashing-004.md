# BCryptPasswordEncoder và đặc điểm giới hạn đầu vào cần kiểm tra

> **Chủ đề:** Spring Security → Authentication → **Băm mật khẩu**. Bài này giải thích `BCryptPasswordEncoder`, cách bcrypt lưu và kiểm tra password, **giới hạn 72 byte của đầu vào UTF-8**, sự khác nhau giữa byte/ký tự Unicode, cách kiểm tra cả khi đăng ký, đổi và đăng nhập, các lưu ý về work factor, hash format, lỗi phiên bản cũ và việc lựa chọn thuật toán thay thế. Ví dụ sử dụng **Java 17+ và Spring Security 6.5.11**, có project Gradle đầy đủ, kết quả console có thể đối chiếu và mẫu tích hợp với Spring Security.

## 1. Những câu hỏi cần giải quyết

Khi triển khai username/password, developer dễ viết:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String hash = encoder.encode(rawPassword);
boolean correct = encoder.matches(candidatePassword, hash);
```

Đoạn trên là ví dụ nằm trong một method có biến `rawPassword` và `candidatePassword`; không phải chương trình Java độc lập. Nó nêu đúng hai thao tác cơ bản nhưng **chưa mô tả toàn bộ chính sách đầu vào**, đặc biệt với mật khẩu dài hoặc Unicode.

Các câu hỏi quan trọng:

1. BCrypt khác SHA-256 thuần hoặc mã hóa hai chiều ở đâu?
2. Tại sao hai lần `encode` cùng password thường tạo **hai hash khác nhau** mà `matches` vẫn đúng?
3. Work factor (`strength`) có nghĩa gì, mặc định bao nhiêu và nên chọn thế nào?
4. **72 byte** là giới hạn của điều gì? Có giống `String.length() == 72` không?
5. Người dùng nhập 25 chữ Unicode ba byte có thể chạm giới hạn trước một người dùng nhập 72 chữ ASCII không?
6. Nếu frontend cho 100 ký tự nhưng bcrypt chỉ xử lý một tiền tố, hậu quả đối với tính duy nhất của password là gì?
7. Một bản Spring Security từng gặp lỗi kiểm tra đầu vào dài như thế nào và tại sao cần cập nhật bản vá?
8. Kiểm tra input nên đặt ở registration, login, password reset hay chính `PasswordEncoder`?
9. Khi nào nên sử dụng `DelegatingPasswordEncoder` hoặc thuật toán khác như Argon2id?

**Tóm tắt định hướng:** bcrypt là một password-hashing function có salt và chi phí tính toán điều chỉnh được, nhưng **đầu vào bcrypt có giới hạn byte**. Đừng chờ tới lúc `encode` hoặc `matches` xử lý mới bắt đầu quyết định chính sách password. Một ứng dụng an toàn cần quy tắc thống nhất trên mọi đường sử dụng password.

## 2. BCryptPasswordEncoder nằm ở đâu trong Spring Security?

Spring Security cung cấp interface:

```java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
```

Đây là chữ ký minh họa ý nghĩa API, không phải mã để khai lại interface trong dự án.

- `encode(raw)` biến password ban đầu thành **password hash để lưu**, không phải mã hóa có thể giải mã.
- `matches(raw, storedHash)` xác minh password đầu vào đối với hash đã lưu; **không** `encode` raw rồi so sánh hai chuỗi hash mới.
- `upgradeEncoding(storedHash)` có thể cho biết hash hiện tại sử dụng thông số yếu hơn cấu hình mong muốn và nên được nâng cấp sau một lần xác minh thành công.

`BCryptPasswordEncoder` là implementation trong package:

```java
org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder
```

Luồng username/password thông dụng:

```text
HTTP POST login / HTTP Basic
    ↓
Authentication Filter → UsernamePasswordAuthenticationToken
    ↓
AuthenticationManager → DaoAuthenticationProvider
    ├─ UserDetailsService.loadUserByUsername(username)
    │     └─ getPassword() trả password hash đã lưu trong DB
    └─ PasswordEncoder.matches(rawPassword, storedHash)
    ↓
Đúng credential + account hợp lệ → Authentication thành công
Sai credential hoặc account bị chặn → AuthenticationException
```

`UserDetailsService` thường chỉ tải username, hash, quyền và trạng thái user; nó không tự kiểm tra mật khẩu. `DaoAuthenticationProvider` sử dụng `PasswordEncoder`. Khi password được tạo hoặc đổi thành công, ứng dụng nên dùng **cùng chính sách encoding và giới hạn input** với đường đăng nhập.

Không lưu raw password; không đưa password/hash vào response, URL, metrics hoặc log. Password hash vẫn là dữ liệu nhạy cảm vì có thể bị tấn công đoán mật khẩu offline nếu DB bị lộ.

## 3. BCrypt hoạt động thế nào?

BCrypt dựa trên thuật toán có chi phí tính toán tăng được, mỗi lần hash thông thường dùng **salt ngẫu nhiên 16 byte (128 bit)**. Salt được mã hóa **bên trong chuỗi hash**, giúp hai tài khoản có cùng password không tự có cùng hash; cũng làm các bảng tra cứu hash dựng trước trở nên kém hiệu quả.

Hash BCrypt thông dụng theo định dạng modular crypt:

```text
$2a$10$<22 ký tự salt><31 ký tự hash>
│   │  └──────── phần salt và kết quả hash được mã hóa theo bcrypt
│   └─────────── cost / log-rounds
└─────────────── phiên bản bcrypt ($2a, $2b, $2y...)
```

Dòng trên dùng các ký hiệu mô tả, không phải một hash thật để lưu. Với bcrypt hiện đại:

- Chuỗi trực tiếp từ `BCryptPasswordEncoder` thường dài **60 ký tự ASCII**.
- `$2a$`, `$2b$`, `$2y$` là các nhãn phiên bản được encoder hỗ trợ. Mặc định của `new BCryptPasswordEncoder()` trong Spring Security 6.5 là `$2a$`.
- `10` là cost mặc định. Đây là tham số logarithmic, chi phí công việc tăng gần theo `2^cost`; tăng từ 10 lên 11 có thể làm lượng công việc tính hash tăng xấp xỉ hai lần, không phải tăng 10%.
- Salt đã có trong encoded hash, **không cần** thêm một cột salt khác chỉ để bcrypt hoạt động.
- Trường được lưu phải đủ dài: với BCrypt trực tiếp thường 60 ký tự; với `DelegatingPasswordEncoder` chuỗi có thêm `{bcrypt}`; khi hỗ trợ nâng cấp thuật toán, nên thiết kế cột rộng hơn như `VARCHAR(255)` hoặc theo yêu cầu encoder của dự án.

Ví dụ:

```java
BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(10);

String a = encoder.encode("demo-passphrase-123");
String b = encoder.encode("demo-passphrase-123");

boolean okA = encoder.matches("demo-passphrase-123", a);
boolean okB = encoder.matches("demo-passphrase-123", b);
```

Đoạn trên là snippet, nhưng hành vi quan trọng là `okA` và `okB` đều `true`. Hai lần `encode` thường có salt khác nên `a` và `b` khác nhau; **không dùng phép so sánh `a.equals(b)` để xác thực password**. Với salt ngẫu nhiên, không hứa một giá trị hash cố định cho một password.

### BCrypt khác SHA-256 thuần

```text
SAI cho lưu password:
stored = SHA256(password)

ĐÚNG hướng dùng password hashing:
stored = BCrypt(password, random salt, tuned cost)
login: BCrypt.verify(candidate, stored)
```

SHA-256 thuần là hash nhanh, hữu ích cho các mục đích khác nhưng **không thích hợp làm password-storage hash độc lập** vì cho phép thử đoán với tốc độ cao. BCrypt được cố ý thiết kế chậm để tăng chi phí brute-force offline. BCrypt **không phải encryption**, không có thao tác giải mã để lấy lại mật khẩu gốc; nếu quên thì thực hiện flow reset có xác minh, không “decode hash”.

## 4. Giới hạn quan trọng nhất: **72 byte**, không phải 72 ký tự

BCrypt truyền thống chỉ hỗ trợ tối đa **72 byte đầu vào** cho dữ liệu password; nhiều implementation lịch sử âm thầm chỉ xét 72 byte đầu. Trong Spring Security đã được vá, việc tạo bcrypt hash mới với input vượt quá 72 byte bị từ chối ở thư viện nền; ứng dụng vẫn nên **chủ động kiểm tra trước** để thông báo rõ ràng và bảo vệ đồng nhất các đường nhập.

OWASP Password Storage Cheat Sheet khuyến nghị giới hạn password bcrypt ở **72 byte hoặc thấp hơn nếu implementation thực tế có giới hạn chặt hơn**.

### 4.1. Ba loại độ dài không được nhầm

| Cách đo | Ví dụ Java | Ý nghĩa |
| --- | --- | --- |
| UTF-16 code units | `password.length()` | Độ dài của `String`, **không phải byte** |
| Unicode code points | `password.codePointCount(0, password.length())` | Số code point, không phải số ký tự người dùng nhìn thấy |
| **UTF-8 bytes** | `password.getBytes(StandardCharsets.UTF_8).length` | **Đơn vị cần kiểm tra cho bcrypt** |

Số grapheme người dùng nhìn thấy lại có thể khác số code point: ký tự có dấu ghép từ nhiều code point; emoji có thể gồm nhiều code point kết nối với nhau. Không lấy `maxlength="72"` trong HTML làm bằng chứng server đã áp dụng giới hạn 72 byte.

Bảng minh họa theo UTF-8:

| Giá trị password (minh họa) | Java `String.length()` | UTF-8 bytes | Trạng thái với giới hạn 72 byte |
| --- | ---: | ---: | --- |
| `"A".repeat(72)` | 72 | 72 | Vừa giới hạn |
| `"A".repeat(73)` | 73 | 73 | Vượt |
| `"é"` (U+00E9, dạng dựng sẵn) | 1 | 2 | Hợp lệ theo kích thước |
| `"e\u0301"` (e + dấu kết hợp) | 2 | 3 | Hợp lệ theo kích thước |
| `"界".repeat(24)` | 24 | 72 | Vừa giới hạn |
| `"界".repeat(25)` | 25 | 75 | Vượt |
| `"😀".repeat(18)` | 36 | 72 | Vừa giới hạn |
| `"😀".repeat(19)` | 38 | 76 | Vượt |

Một emoji `😀` thường chiếm **4 byte UTF-8** và **2 UTF-16 code units**. Một chữ Hán `界` chiếm **3 byte UTF-8**. Vì vậy hai password cùng “25 ký tự” trực quan có thể có số byte rất khác nhau.

### 4.2. Vì sao vượt 72 byte là vấn đề bảo mật?

Trong một số implementation bcrypt cũ, các byte sau mốc giới hạn **không góp phần phân biệt password khi kiểm tra**. Khi đó hai input cùng tiền tố 72 byte nhưng khác hậu tố có thể được xem là giống nhau. Điều này làm người dùng tưởng password dài hơn và mạnh hơn thực tế.

Ví dụ khái niệm:

```text
input #1 = <cùng 72 byte đầu> + "X"
input #2 = <cùng 72 byte đầu> + "Y"

Trong implementation tự cắt đuôi:
      bcrypt(input #1) và bcrypt(input #2)
      có thể chỉ phụ thuộc vào phần tiền tố chung.
```

Đây là **mô hình rủi ro của implementation không kiểm soát độ dài**, không phải mô tả hành vi được cho phép ở bản Spring Security 6.5.11 đã vá. Không nên dùng ví dụ này để thử truy cập tài khoản của người khác.

**Không tự gọi `substring(0,72)` hoặc `Arrays.copyOf(...,72)`** để “sửa” input trước khi hash/match. Cắt mật khẩu là thay đổi bí mật do người dùng chọn; hai mật khẩu khác nhau có thể trở thành giống nhau. Quy tắc đúng là **từ chối đầu vào vượt giới hạn trước khi hashing**, hoặc chọn thuật toán hỗ trợ độ dài theo yêu cầu sản phẩm.

### 4.3. CVE-2025-22228 và giới hạn phiên bản

Spring đã công bố **CVE-2025-22228** liên quan `BCryptPasswordEncoder.matches(...)` chấp nhận sai một số password dài hơn giới hạn khi có tiền tố giống nhau. Các nhánh Spring Security bị ảnh hưởng được sửa ở các phiên bản như **6.4.4, 6.3.8** (và các phiên bản sửa tương ứng của nhánh cũ). Tài liệu công bố chính thức: https://spring.io/security/cve-2025-22228/.

**Phần cần áp dụng:** cập nhật thư viện lên bản vá của nhánh đang dùng hoặc bản mới được tổ chức hỗ trợ, kiểm tra dependency tree và transitive dependencies, rồi test tình huống input quá dài. Chỉ giới hạn phía frontend không thay thế bản vá hoặc chính sách server-side.

Spring Security **6.5.11** của ví dụ là phiên bản sau các bản vá đã nêu; khi dùng phiên bản khác, đọc advisory/changelog và test chính implementation đó. Không kết luận rằng **mọi thư viện bcrypt** đều ném cùng loại exception trên `encode` hoặc trả cùng trạng thái trên `matches`: khác biệt implementation là lý do cần kiểm soát giới hạn tại boundary của ứng dụng.

## 5. Quy tắc validate password: áp dụng cả khi **ghi** và **kiểm tra**

### 5.1. Các đường phải có chính sách chung

- **Đăng ký tài khoản:** validate password trước khi gọi `PasswordEncoder.encode(...)`, rồi lưu hash, không lưu raw.
- **Đổi mật khẩu khi đã đăng nhập:** kiểm tra password hiện tại bằng cơ chế đáng tin; validate password mới trước khi encode; cập nhật hash theo transaction.
- **Quên mật khẩu:** xác minh recovery proof trước; validate password mới rồi encode; thu hồi token recovery/session theo chính sách.
- **Đăng nhập:** xác minh input theo chính sách encoder đang áp dụng; không âm thầm bỏ phần đuôi, không hạ cấp về thuật toán yếu hơn khi gặp input quá dài.
- **Import hoặc tạo user từ admin:** cũng phải tuân thủ chính sách nếu có password do người dùng/administrator đặt.
- **API khác gọi password encoder trực tiếp:** tránh đường phụ bỏ qua bộ validate của controller.

### 5.2. Tại sao cần validate ở backend?

Frontend có thể kiểm tra để cung cấp UX nhanh, nhưng người dùng/API client có thể bỏ qua frontend. Do đó check **ở backend** phải là nguồn quyết định. Đừng coi annotation `@Size(max=72)` trên Java `String` là đủ vì Bean Validation đếm **đơn vị ký tự**, không đồng nghĩa số byte UTF-8.

Một quy tắc tối thiểu phù hợp cho bcrypt:

```text
rawPassword không null
rawPassword không rỗng
UTF-8 encoding hợp lệ (không có surrogate hỏng)
UTF-8 byteLength <= 72
Không tự trim, lowercase, cắt bớt hoặc đổi Unicode normalization
Các rule khác (minimum length, blocklist, breached passwords...) áp dụng riêng
```

Với nhập rất dài, nên chặn ở gateway/request limit và application **trước khi thực hiện password hashing tốn CPU**, chống nguy cơ denial-of-service. `BCryptPasswordEncoder` cũng có chi phí CPU cho mỗi lần kiểm tra password; rate limiting và giám sát xác thực là thiết yếu.

### 5.3. Không tự ý normalize mật khẩu

Hai chuỗi trông giống nhau có thể khác bytes:

```text
U+00E9       : "é"            → UTF-8 2 bytes
U+0065 U+0301: "e" + dấu sắc  → UTF-8 3 bytes
```

Password được chọn là **chuỗi bí mật**, không phải trường tìm kiếm cần bỏ dấu. Nếu ứng dụng chủ ý dùng Unicode normalization như NFC theo một chính sách được phê duyệt, phải áp dụng nhất quán trong **mọi** điểm đặt/kiểm tra/đổi password và có kế hoạch migrate password cũ; không âm thầm thay đổi khi đã có hash vì người dùng có thể không đăng nhập được.

**Không trim whitespace, không tự chuyển chữ thường, không bỏ dấu, không thay ký tự điều khiển bằng chuỗi khác.** Không chỉ làm sai password mà còn có thể tạo collision do biến đổi ngoài ý muốn.

## 6. Java 17+ runnable: kiểm tra 72 byte UTF-8 và BCryptPasswordEncoder

Demo dưới đây là một chương trình Java chạy từ Gradle. Nó dùng **Spring Security Crypto 6.5.11** thông qua dependency Spring Security Core, tạo password hash bằng `BCryptPasswordEncoder(10)` và bọc encoder bằng một policy kiểm tra đầu vào ở cả `encode` lẫn `matches`.

Các ví dụ chỉ in **độ dài và kết quả boolean**, không in hash đầy đủ, password cá nhân hoặc secret. Các password trong code đều là test fixtures.

### 6.1. Cấu trúc

```text
bcrypt-input-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/BCryptInputDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'bcrypt-input-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

application {
    mainClass = 'demo.BCryptInputDemo'
}
```

### 6.2. Chương trình đầy đủ

Tạo `src/main/java/demo/BCryptInputDemo.java`:

```java
package demo;

import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class BCryptInputDemo {
    private static final int MAX_BCRYPT_UTF8_BYTES = 72;

    public static void main(String[] args) {
        PasswordEncoder encoder = new ValidatedBcryptEncoder(10);

        String password = "demo-passphrase-123";
        String hash = encoder.encode(password);

        // Không in toàn bộ hash hoặc password thật.
        System.out.println("prefix=" + hash.substring(0, 7));
        System.out.println("hashLength=" + hash.length());
        System.out.println("matchCorrect="
                + encoder.matches(password, hash));
        System.out.println("matchWrong="
                + encoder.matches("wrong-password", hash));

        String ascii72 = "A".repeat(72);
        String ascii73 = "A".repeat(73);
        String unicode24 = "界".repeat(24);
        String unicode25 = "界".repeat(25);

        System.out.println("ascii72Bytes=" + utf8BytesForDisplay(ascii72));
        System.out.println("ascii73Bytes=" + utf8BytesForDisplay(ascii73));
        System.out.println("unicode24Bytes="
                + utf8BytesForDisplay(unicode24));
        System.out.println("unicode25Bytes="
                + utf8BytesForDisplay(unicode25));

        System.out.println("encodeAscii72="
                + acceptedByEncode(encoder, ascii72));
        System.out.println("encodeAscii73="
                + acceptedByEncode(encoder, ascii73));
        System.out.println("encodeUnicode24="
                + acceptedByEncode(encoder, unicode24));
        System.out.println("encodeUnicode25="
                + acceptedByEncode(encoder, unicode25));

        // Policy được bọc vào PasswordEncoder nên áp dụng cả login.
        System.out.println("overlongLogin="
                + encoder.matches(ascii73, hash));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("accentBytes="
                + utf8BytesForDisplay(composed) + "/"
                + utf8BytesForDisplay(decomposed));
    }

    // Chỉ dùng đo byte cho literal test; không log độ dài password thật.
    private static int utf8BytesForDisplay(String input) {
        return input.getBytes(StandardCharsets.UTF_8).length;
    }

    private static boolean acceptedByEncode(
            PasswordEncoder encoder, String input) {
        try {
            encoder.encode(input);
            return true;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    // Một chính sách kiểm tra được gọi ở cả registration và login.
    private static void checkBcryptInput(CharSequence rawPassword) {
        if (rawPassword == null) {
            throw new IllegalArgumentException("Password is required");
        }

        String input = rawPassword.toString();

        if (input.isEmpty()) {
            throw new IllegalArgumentException("Password is empty");
        }

        // Bất kỳ chuỗi UTF-16 hợp lệ nào có >72 code units cũng
        // chắc chắn vượt >72 bytes UTF-8. Chặn sớm tránh cấp phát lớn.
        if (input.length() > MAX_BCRYPT_UTF8_BYTES) {
            throw new IllegalArgumentException(
                    "Password exceeds bcrypt UTF-8 byte limit");
        }

        try {
            int bytes = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(input))
                    .remaining();

            if (bytes > MAX_BCRYPT_UTF8_BYTES) {
                throw new IllegalArgumentException(
                        "Password exceeds bcrypt UTF-8 byte limit");
            }
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException(
                    "Password contains invalid Unicode", ex);
        }
    }

    // Wrapper giữ quy tắc thống nhất ngay ở PasswordEncoder.
    private static final class ValidatedBcryptEncoder
            implements PasswordEncoder {
        private final BCryptPasswordEncoder delegate;

        private ValidatedBcryptEncoder(int strength) {
            this.delegate = new BCryptPasswordEncoder(strength);
        }

        @Override
        public String encode(CharSequence rawPassword) {
            checkBcryptInput(rawPassword);
            return delegate.encode(rawPassword);
        }

        @Override
        public boolean matches(
                CharSequence rawPassword, String encodedPassword) {
            try {
                checkBcryptInput(rawPassword);
            } catch (IllegalArgumentException ex) {
                // Trong login: từ chối credential không hợp lệ;
                // không cho exception làm rò rỉ chi tiết vào response.
                return false;
            }
            return delegate.matches(rawPassword, encodedPassword);
        }

        @Override
        public boolean upgradeEncoding(String encodedPassword) {
            return delegate.upgradeEncoding(encodedPassword);
        }
    }
}
```

Chạy trong thư mục `bcrypt-input-demo` với Gradle tương thích JDK 17:

```bash
gradle run
```

Nếu dự án có Gradle Wrapper thì dùng `./gradlew run` (macOS/Linux) hoặc `gradlew.bat run` (Windows). Phần stdout của chương trình (không bao gồm log của Gradle):

```text
prefix=$2a$10$
hashLength=60
matchCorrect=true
matchWrong=false
ascii72Bytes=72
ascii73Bytes=73
unicode24Bytes=72
unicode25Bytes=75
encodeAscii72=true
encodeAscii73=false
encodeUnicode24=true
encodeUnicode25=false
overlongLogin=false
accentBytes=2/3
```

**Vì sao những dòng này đáng tin?**

1. `new BCryptPasswordEncoder(10)` trong dòng 6.5 cho định dạng hash mặc định có prefix `$2a$10$`, tổng độ dài trực tiếp là 60 ký tự. Phần salt và hash phía sau ngẫu nhiên nên **không in hoặc cam kết chuỗi hash cố định**.
2. `matches` sử dụng salt/cost đã nằm trong hash, nên mật khẩu đúng trả `true` và mật khẩu sai trả `false`.
3. ASCII `"A"` là một byte UTF-8, 72 chữ A đúng 72 byte; 73 chữ A vượt giới hạn.
4. `界` có ba byte UTF-8; 24 ký tự là 72 byte, 25 ký tự là 75 byte.
5. `ValidatedBcryptEncoder` chặn trước mọi đường encode/matches nếu vượt giới hạn. Vì vậy `overlongLogin=false` là **hành vi do wrapper của chương trình bảo đảm**, không phụ thuộc vào cách một bản bcrypt nội bộ xử lý password dài.
6. Hai cách viết chữ é trông giống nhau nhưng có kích thước 2 và 3 byte, nên không thể kiểm tra giới hạn Unicode chỉ bằng số ký tự nhìn thấy.
7. `checkBcryptInput` dùng `CharsetEncoder` với `CodingErrorAction.REPORT` để từ chối Unicode UTF-16 không hợp lệ thay vì im lặng thay bằng ký tự khác trong một thao tác encode.
8. Hàm `acceptedByEncode` dùng các test literal, bắt exception có chủ đích; code production nên ánh xạ lỗi thành thông báo validation rõ ràng, **không dựa vào exception text từ dependency để hiện trực tiếp cho client**.

**Giới hạn của demo:** đây là một **policy kiểm tra độ dài tối thiểu**, không phải dịch vụ đăng ký/đăng nhập hoàn chỉnh. Nó chưa có kiểm tra password bị rò rỉ, rate limit, lưu DB, MFA, xử lý account lock, session và transaction. Những trách nhiệm đó phải được bổ sung trong ứng dụng thật.

### 6.3. Tại sao có bước kiểm tra `input.length() > 72` trước?

Một `String` hợp lệ có số byte UTF-8 **ít nhất bằng số UTF-16 code units** của nó (ASCII: 1 byte mỗi unit; ký tự không phải ASCII thường nhiều byte hơn). Vì vậy nếu `String.length() > 72`, chắc chắn password dài quá 72 byte.

Đây là **bộ lọc trước để giảm cấp phát khi gặp input khổng lồ**, còn **quyết định cuối cùng vẫn phải dựa trên UTF-8 byte length**. Không đảo chiều suy luận: một `String` dài 25 code units vẫn có thể dài 75 byte.

Nên có request-body limit ở HTTP layer để chặn đầu vào rất lớn trước khi chuyển thành `String` và trước khi gọi password hashing. Kiểm soát mối liên hệ giữa độ dài password, bộ nhớ và CPU là vấn đề an toàn vận hành, không chỉ UX.

## 7. Tích hợp vào Spring Boot: PasswordEncoder phải là chính sách chung

Một số dự án chỉ kiểm tra giới hạn trong controller `POST /register` nhưng bỏ qua các đường khác: HTTP Basic, form login, API admin, reset password. Như vậy việc nhập liệu và xác minh có thể **không đồng nhất**.

Một giải pháp là đăng ký `PasswordEncoder` bean đã được bọc validator:

```java
@Configuration
class PasswordConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new ValidatingPasswordEncoder(
                new BCryptPasswordEncoder(12));
    }
}
```

Đây là **snippet cấu hình**, giả định lớp `ValidatingPasswordEncoder` tồn tại và áp dụng logic giống `ValidatedBcryptEncoder` ở mục 6. Nó không phải file Java hoàn chỉnh. `12` chỉ là một **tham số ví dụ**, không phải cost được khuyến nghị mặc định cho mọi môi trường. Hãy benchmark trên phần cứng thật trước khi chọn.

Nếu dùng `DaoAuthenticationProvider` và một bean `PasswordEncoder` nhất quán, provider sẽ dùng `matches(...)` của encoder để kiểm tra mật khẩu. Controller đăng ký/đổi password dùng `encode(...)` của cùng encoder. Một chốt kiểm tra ở encoder giúp giảm rủi ro quên validation ở các entry point — tuy nhiên vẫn nên validation trước ở request/service để trả thông báo phù hợp và không gọi BCrypt vô ích.

### Khi dùng DelegatingPasswordEncoder

Spring Security thường khuyến nghị `PasswordEncoderFactories.createDelegatingPasswordEncoder()` để hỗ trợ nhiều thuật toán/phiên bản hash qua tiền tố:

```text
Direct bcrypt hash:
$2a$10$...

DelegatingPasswordEncoder hash:
{bcrypt}$2a$10$...
```

`DelegatingPasswordEncoder` đọc `{id}` để chọn encoder phù hợp; nó hỗ trợ migration từ hash cũ và thay đổi thuật toán trong tương lai. Nếu bạn bọc **toàn bộ** `DelegatingPasswordEncoder` bằng một policy cứng 72 byte, điều đó cũng có thể từ chối những password dài được lưu hợp lệ bằng Argon2id/scrypt. Vì thế:

- Nếu **mọi hash mới đều là bcrypt** và chính sách thống nhất là 72 byte, áp dụng validator 72 byte cho tất cả đường password là hợp lý.
- Nếu hệ thống có **nhiều thuật toán đồng thời**, chính sách kiểm tra phải xét **algorithm của hash đang verify** và algorithm dùng cho **password mới**, nhưng không được mở ra một đường downgrade hay khiến UX khó hiểu.
- Nếu muốn hỗ trợ passphrase dài hơn 72 byte trong tương lai, **chọn thuật toán phù hợp trước khi ra chính sách password mới**; đừng chỉ sửa một `maxlength` rồi giữ BCrypt.
- Với hash cũ không có `{id}`, cần migration rõ ràng; `DelegatingPasswordEncoder` mặc định có thể ném lỗi vì id không được ánh xạ. Không tự ghép `{bcrypt}` vào mọi hàng mà chưa xác định thuật toán thực tế.

**Không dùng `NoOpPasswordEncoder`** để bỏ lỗi input; điều đó biến password thành plaintext trong DB và gây rủi ro nghiêm trọng. Không dùng một encoder SHA-256 thuần làm đường fallback “nhanh hơn” khi password dài.

## 8. Tại sao không nên tự cắt hoặc pre-hash tùy tiện?

### 8.1. Truncate làm thay đổi bí mật

Một anti-pattern thường gặp:

```java
// KHÔNG LÀM: cắt password để vừa "72 ký tự".
String shortened = rawPassword.substring(
        0, Math.min(rawPassword.length(), 72));
String encoded = encoder.encode(shortened);
```

Đoạn trên còn sai ở chỗ đếm **ký tự Java**, không phải bytes UTF-8. Cắt một chuỗi chứa surrogate pair không cẩn thận còn có thể tạo Unicode hỏng.

Hậu quả nghiêm trọng hơn: user nghĩ mình đặt password `secret...A` nhưng hệ thống lưu hash của một tiền tố ngắn hơn. Tùy triển khai, việc xác minh một chuỗi khác cùng tiền tố có thể thành công. **Từ chối input quá dài**, không rút ngắn nó trong backend.

### 8.2. Pre-hash không phải bản sửa miễn phí

Một số tài liệu nói đến cách hash password bằng SHA-256/SHA-512 trước rồi đưa digest vào bcrypt. Ý tưởng này có các rủi ro:

- Hash bytes có thể chứa **NUL** đối với implementation bcrypt xử lý chuỗi kết thúc bằng NUL.
- Nếu biểu diễn digest bằng Base64/Hex, chiều dài vẫn phải nằm trong giới hạn của bcrypt và cần versioning.
- Nếu dùng inner hash **không có secret** và hash đó bị lộ ở hệ thống khác, mô hình **password shucking** có thể làm tấn công offline hiệu quả hơn mong đợi.
- Một thay đổi pipeline `bcrypt(password)` → `bcrypt(SHA256(password))` **không tương thích với hash cũ** nếu không có kế hoạch migration.

OWASP có thảo luận về việc dùng **HMAC với pepper bảo vệ riêng** trước bcrypt trong trường hợp thật sự cần pre-hash; đây là một thiết kế bảo mật bổ sung, không phải mẹo copy/paste từ blog. Nếu ứng dụng mới muốn password dài, **Argon2id là lựa chọn nên đánh giá trước** thay vì tự sáng tạo biến thể BCrypt.

### 8.3. Không tự normalize/trimming

`encode` và `matches` phải áp dụng cùng cách xử lý chuỗi. Không normalize password trong login nhưng quên trong registration hoặc ngược lại. Không hiển thị password hash hay biến thể password đã chuẩn hóa ra log để debug.

## 9. Work factor, hiệu năng và nguy cơ DoS

`BCryptPasswordEncoder` dùng `strength` — tham số work factor. Trong Spring Security 6.5:

- Có constructor `new BCryptPasswordEncoder()` mặc định cost **10**.
- Có constructor `new BCryptPasswordEncoder(int strength)` nhận cost trong khoảng **4 đến 31**.
- Có overload chỉ định phiên bản `BCryptVersion`, `SecureRandom` và cost.
- Cost được lưu trong encoded hash. Khi thay encoder sang cost mới, các hash cũ vẫn có thể kiểm tra bằng thông số nằm trong hash.
- `upgradeEncoding(encodedHash)` có thể trả true nếu cost lưu thấp hơn cost của encoder hiện tại; việc **rehash chỉ được thực hiện sau khi đã xác minh password đúng** và có quy trình lưu hash cập nhật.

### 9.1. Cách chọn cost

Không cố định tất cả ứng dụng tại cost 10 hoặc 16 một cách máy móc. Cost tăng một đơn vị làm công việc thường tăng gần gấp đôi; thời gian thực tế tùy CPU, runtime, đồng thời số request và hệ thống. Theo tài liệu Spring Security, hãy đo và điều chỉnh hướng tới thời gian xác minh phù hợp với yêu cầu vận hành (tài liệu nêu khoảng một giây làm mốc tham khảo).

Đo bằng benchmark có kiểm soát:

1. Chọn tập máy/node và tải đồng thời đại diện môi trường production.
2. Đo latency median/p95/p99 của `matches(...)` cho password có độ dài thực tế.
3. Kiểm tra CPU, memory, request queue và login throughput dưới concurrent load.
4. Chọn cost đủ chậm để khó đoán offline nhưng không làm hệ thống hết tài nguyên khi có nhiều login.
5. Đặt rate limit, login throttling và monitoring; không dùng cost quá cao thay thế các biện pháp chống credential stuffing.

**Không ghi thời gian xác thực như một hằng số** trong tài liệu: một hash cost 12 không có số milliseconds cố định trên mọi phần cứng.

### 9.2. Mật khẩu dài và cost cao là hai vấn đề khác nhau

Giới hạn 72 byte giải quyết vấn đề **semantics của bcrypt input**. Rate limiting và việc chọn cost giải quyết **lượng CPU phải chi cho mỗi lần kiểm tra**. Một hệ thống đã chặn password >72 byte vẫn có thể bị quá tải do quá nhiều lần thử login có password ngắn. Ngược lại, một hệ thống có rate limiting nhưng âm thầm truncate password vẫn có lỗi về tính toàn vẹn của credential.

## 10. Tương thích hệ thống cũ và kế hoạch migration

Khi đang có hàng triệu bcrypt hash trong DB, phải đánh giá **algorithm, phiên bản thư viện và lịch sử validation** trước khi thay đổi chính sách:

### 10.1. Kiểm kê

- Đọc cấu hình encoder, version dependency và cách ứng dụng thật dùng `encode/matches`.
- Kiểm tra dạng hash lưu (`$2a$...`, `{bcrypt}$2a$...`, prefix khác) và cost đã dùng.
- Kiểm tra ứng dụng cũ có cho password >72 byte hay không; frontend `maxlength` có kiểm tra bytes hay chỉ ký tự?
- Kiểm tra thư viện cũ có truncate hay chấp nhận password dài sai cách không.
- Không log hoặc xuất bảng hash để phân tích ngoài vùng bảo mật; làm thống kê cấu hình và code trước.

### 10.2. Không thể tự khôi phục password gốc từ hash

Vì password hash một chiều, hệ thống không thể đọc hash rồi biết user đã nhập bao nhiêu byte hoặc byte nào sau mốc 72 trước đây. Nếu có rủi ro hash cũ được tạo từ password quá dài/đã bị truncate:

1. Ưu tiên cập nhật bản vá và ngăn tạo credential mới không hợp lệ.
2. Có kế hoạch **buộc đổi password** hoặc recovery có proof cho nhóm ảnh hưởng, theo mức độ rủi ro.
3. Không tự động đánh dấu một hash cũ “đã chuyển sang Argon2id” chỉ bằng việc sửa tiền tố.
4. Khi user có password đúng hợp lệ, có thể nâng cấp hash theo cơ chế verify-then-rehash với thuật toán mới; giữ chính sách và lưu trữ có version.
5. Thu hồi session/token nếu chính sách incident yêu cầu; đổi password trong DB không tự làm JWT cũ vô hiệu ngay.

Một số user có thể đã nhập password dài trong bản thư viện cũ và sau bản vá không còn đăng nhập được như trước. Cần có **quy trình recovery rõ ràng, bảo mật**, không tạm bật lại phiên bản thư viện có lỗ hổng để “chữa lỗi UX”.

### 10.3. Dùng DelegatingPasswordEncoder để chuyển dần

Một hệ thống có nhiều encoded-password format thường nên dùng `DelegatingPasswordEncoder` vì có cơ chế ánh xạ `{id}` tới encoder cụ thể. Khi điều chỉnh thuật toán:

- Hash cũ vẫn dùng encoder tương ứng để verify.
- Hash mới dùng thuật toán `idForEncode` đã chọn.
- Sau verify thành công, ứng dụng có thể lưu hash mới nếu `upgradeEncoding`/chính sách migration yêu cầu.
- Password validation phải xét giới hạn algorithm của hash cũ và của hash mới; không làm mất khả năng đăng nhập hợp lệ hoặc tạo đường downgrade.

Tuy nhiên, nếu người dùng đã có hash bcrypt từ một password vượt 72 byte do đường cũ truncate, không có cách tự biết password đầy đủ bằng cách đọc hash. Recovery vẫn có thể cần thiết.

## 11. Các trường hợp kiểm thử bắt buộc

Bộ test nên xác minh **giới hạn byte và đường xác thực thật**, không chỉ riêng một hàm đếm ký tự.

| Trường hợp | Input | Kết quả cần bảo đảm |
| --- | --- | --- |
| ASCII đúng giới hạn | 72 ký tự `A` | Được chấp nhận nếu pass các rule khác |
| ASCII vượt giới hạn | 73 ký tự `A` | Bị từ chối khi đặt password và khi đăng nhập |
| Unicode ba byte đúng giới hạn | 24 ký tự `界` | 72 byte, hợp lệ theo giới hạn |
| Unicode ba byte vượt giới hạn | 25 ký tự `界` | 75 byte, bị từ chối |
| Emoji 4 byte đúng giới hạn | 18 ký tự `😀` | 72 byte |
| Emoji vượt giới hạn | 19 ký tự `😀` | 76 byte, bị từ chối |
| Chữ có dấu dựng sẵn và ghép dấu | `é` vs `e + combining mark` | Không tự coi giống nhau nếu không có normalization policy |
| Surrogate UTF-16 không hợp lệ | Một high surrogate lẻ | Bị từ chối, không âm thầm thay bằng `?` |
| Password rỗng/null | `""`, `null` | Bị từ chối trước BCrypt |
| Password đúng | Hash đã lưu | `matches` trả true |
| Password sai | Chuỗi khác | `matches` trả false |
| Input >72 có cùng tiền tố | Thêm đuôi khác sau 72 byte | Không được chấp nhận như cùng password |
| Hai lần encode giống raw | Cùng raw, salt ngẫu nhiên | Mỗi hash đều xác minh được; không so sánh hash mới bằng equals |
| Hash sai định dạng | String không phải bcrypt | Login fail an toàn; không tự fallback plaintext |
| BCrypt cost cũ | Hash với work factor thấp | Verify được, có thể báo `upgradeEncoding` |
| Password reset | New raw password | Validator và encoder được gọi trước khi lưu |
| HTTP Basic/form login | Raw vượt giới hạn | Backend từ chối, không chỉ frontend |
| Hash legacy và delegating prefix | `{bcrypt}` hoặc format cũ | Verify/migration đúng theo versioned policy |

### 11.1. Unit test cho ranh giới

Đoạn dưới là ví dụ JUnit 5 **phụ thuộc class validator/wrapper được đưa thành class riêng trong production**. Không phải test độc lập nếu không có package/import/project:

```java
@Test
void bcryptInputLimitMustBeCheckedInUtf8Bytes() {
    PasswordEncoder encoder = new ValidatedBcryptEncoder(10);

    assertDoesNotThrow(() -> encoder.encode("A".repeat(72)));
    assertThrows(IllegalArgumentException.class,
            () -> encoder.encode("A".repeat(73)));

    assertDoesNotThrow(() -> encoder.encode("界".repeat(24)));
    assertThrows(IllegalArgumentException.class,
            () -> encoder.encode("界".repeat(25)));
}
```

Với project demo, `ValidatedBcryptEncoder` là nested private class trong `BCryptInputDemo`; để sử dụng test độc lập, chuyển class ra file riêng (ví dụ `ValidatedBcryptEncoder.java`), giữ logic kiểm tra và chọn visibility phù hợp. Khi test qua `AuthenticationManager`/`DaoAuthenticationProvider`, cần test rằng input dài không thể xác thực thành công ngay cả khi hash cũ có tiền tố trùng. Test controller chỉ trả lỗi validation không thay thế integration test đăng nhập thực.

### 11.2. Test với Spring Security thật

- Tạo account với hash hợp lệ; `DaoAuthenticationProvider` phải chấp nhận đúng raw và từ chối sai raw.
- Đăng nhập HTTP Basic/form login với password dài >72 byte phải không tạo `Authentication` thành công.
- Password reset dùng cùng validator và không lưu dữ liệu khi validation fail.
- Nếu dùng `DelegatingPasswordEncoder`, test đúng các prefix và trường hợp id không được hỗ trợ.
- Với thư viện bị vá và thư viện lịch sử trên môi trường thử nghiệm kiểm soát, test trường hợp CVE để xác minh đã cập nhật. Không triển khai bản lỗi trong production.
- Với DB, confirm password column không truncate encoded hash. Hash bcrypt trực tiếp và hash có `{bcrypt}` có độ dài khác nhau.
- Test Unicode NFC/NFD và surrogate để bảo đảm xử lý nhất quán theo policy.
- Test đồng thời nhiều login để đo latency/CPU, không coi một unit test là load test.

## 12. Các sai lầm phổ biến

1. **Dùng `password.length() <= 72` làm kiểm tra duy nhất.** Sai với Unicode nhiều byte; cần UTF-8 bytes.
2. **Chỉ đặt `maxlength=72` ở frontend.** Có thể bypass bằng API client, và bản thân maxlength thường không đếm byte.
3. **Cắt password xuống 72 ký tự hoặc byte.** Làm mất phần bí mật người dùng chọn, tạo khả năng password khác bị coi giống nhau.
4. **Cho rằng bản Spring Security nào cũng xử lý password dài giống nhau.** Có lịch sử lỗ hổng CVE-2025-22228; phải dùng phiên bản đã vá và test behavior.
5. **Không kiểm tra trên đường login.** Kiểm tra registration nhưng để provider legacy xử lý dài ngoài dự kiến.
6. **Cho rằng BCrypt hash là encryption có thể decrypt.** Mật khẩu phải reset, không thể lấy lại từ hash.
7. **So sánh hai chuỗi `encode(raw)`.** Salt ngẫu nhiên làm hash khác nhau; dùng `matches(raw, hash)`.
8. **Lưu password plaintext, reversible encryption hoặc SHA-256 thuần.** Không đạt tính chống tấn công offline mong muốn.
9. **Tự thêm salt bên ngoài mà không hiểu format.** BCrypt đã tự quản lý salt; custom format làm tăng phức tạp migration.
10. **Hardcode salt hoặc RNG có seed cố định.** Dễ mất tính ngẫu nhiên; dùng cơ chế ngẫu nhiên an toàn mặc định.
11. **Chọn cost quá thấp hoặc quá cao mà không benchmark.** Cost thấp yếu trước offline attacks; quá cao có thể gây nghẽn login.
12. **Quên rate limiting vì nghĩ BCrypt đủ chậm.** Online abuse vẫn có thể làm cạn tài nguyên.
13. **Dùng BCrypt và tăng `maxlength` lên 200 để khuyến khích passphrase dài.** Nếu muốn >72 UTF-8 bytes phải xem xét thuật toán thích hợp.
14. **Dùng `substring` với Unicode và tạo surrogate lẻ.** Gây mất dữ liệu/khác nhau khi encode.
15. **Âm thầm trim hoặc normalize password.** Phá khả năng xác thực nhất quán với hash đã lưu.
16. **Quên cập nhật dependency bị ảnh hưởng CVE.** Chỉ thêm UI validation không sửa behavior đã biết của thư viện.
17. **Dùng `NoOpPasswordEncoder` làm workaround.** Dẫn đến password lưu plaintext, không được chấp nhận.
18. **Giải quyết input dài bằng pre-hash SHA-256 tùy tiện.** Có thể phát sinh password shucking, NUL và migration issues.
19. **Chặn mọi password >72 trên toàn ứng dụng multi-algorithm.** Vô tình từ chối những password hợp lệ dưới Argon2id/scrypt; cần policy theo encoder đang dùng.
20. **Bắt exception BCrypt và gửi nguyên message nội bộ ra client.** Nên trả validation error phù hợp; không tiết lộ thông tin không cần thiết.
21. **Không có test Unicode.** Test toàn chữ ASCII không phát hiện lỗi byte limit.
22. **Giữ cost 10 mãi mãi không đánh giá lại.** Hardware và risk thay đổi; lên kế hoạch benchmark/nâng cấp có kiểm soát.
23. **Tưởng upgradeEncoding tự lưu hash mới.** Đây chỉ là tín hiệu; cần flow sau verify và transaction lưu hash mới.
24. **Log hash hoặc password để debug login.** Có thể lộ credential và dữ liệu nhạy cảm; audit tối thiểu, có redaction.

## 13. Bài tập thực hành

**Bài A — 72 byte khác 72 ký tự.** Với `"x".repeat(72)`, `"界".repeat(24)`, `"😀".repeat(18)` và `"界".repeat(25)`, tính số UTF-16 code units, số Unicode code points và UTF-8 bytes. Giải thích vì sao hai chuỗi có số ký tự khác nhau lại cùng chạm giới hạn bcrypt.

**Bài B — Viết validator.** Tạo hàm `checkBcryptInput(CharSequence)` như mục 6; thêm test password rỗng, null, 72/73 ASCII bytes, 72/75 Unicode bytes, emoji và một surrogate bị hỏng. Đừng dùng `String.length()` làm điều kiện đủ để cho phép.

**Bài C — Tích hợp vào DaoAuthenticationProvider.** Định nghĩa `PasswordEncoder` bean bọc validator, cấu hình `UserDetailsService` và đăng nhập thật với một tài khoản test. Gửi password quá dài qua HTTP Basic/form login và xác minh authentication bị từ chối.

**Bài D — Hai hash khác nhau.** Gọi `encode` hai lần cho cùng một passphrase hợp lệ. Giải thích salt được lưu ở đâu, vì sao hash không ổn định và tại sao `matches` vẫn đúng.

**Bài E — Cost.** Trên môi trường test, benchmark cost 10/11/12 với concurrency đại diện, ghi median/p95 và CPU. Chọn cost dựa trên kết quả và yêu cầu vận hành; không chép một số milliseconds tưởng tượng từ tài liệu.

**Bài F — Nâng cấp.** Cho một DB có hash `$2a$...` cost thấp và hash `{bcrypt}$2a$...`. Xây kế hoạch chuyển dần sang `DelegatingPasswordEncoder`, xác định quy tắc parse prefix và bước rehash sau xác minh.

**Bài G — Kiểm kê CVE.** Từ dependency tree, xác định phiên bản `spring-security-crypto` và bản vá tương ứng. Viết integration test chứng minh password dài có chung tiền tố không được nhận sai. Không chạy bản bị ảnh hưởng ở production.

**Bài H — Chính sách password dài.** Một sản phẩm muốn hỗ trợ passphrase UTF-8 dài hơn 72 byte. Đề xuất kiến trúc với Argon2id, cột password hash có version, quy tắc migration và kiểm thử; giải thích vì sao không chỉ sửa giới hạn frontend.

### Tiêu chí hoàn thành

Người học có thể trình bày được:

- BCrypt có salt và work factor, lưu trực tiếp hash dạng gì và dùng `matches` ra sao?
- Tại sao giới hạn bcrypt là **72 byte UTF-8**, không phải 72 ký tự?
- Cách kiểm tra an toàn cho ASCII, Unicode nhiều byte, emoji và malformed UTF-16?
- Vì sao không truncate password và tại sao CVE-2025-22228 liên quan tới điều đó?
- Đặt validation ở đâu để mọi luồng registration, login, đổi/reset mật khẩu đều nhất quán?
- Khi nào cần `DelegatingPasswordEncoder`, `upgradeEncoding` hoặc chuyển sang Argon2id?
- Làm thế nào kiểm tra performance và migration mà không gây login DoS hoặc mất khả năng truy cập tài khoản hợp lệ?

## 14. Tài liệu gốc và tham khảo

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): BCryptPasswordEncoder, cost, DelegatingPasswordEncoder và migration.
- [Spring Security 6.5 — BCryptPasswordEncoder API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html): constructor, version, strength, `encode`, `matches` và `upgradeEncoding`.
- [Spring Security 6.5 — Crypto Module](https://www.springframework.org/spring-security/reference/6.5/features/integrations/cryptography.html): salt 16 byte và các tham số work factor.
- [Spring Security — CVE-2025-22228](https://spring.io/security/cve-2025-22228/): advisory chính thức về kiểm tra password dài hơn giới hạn; các nhánh và bản vá.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): bcrypt 72-byte input limit, nguy cơ pre-hash/password shucking và hướng lựa chọn Argon2id.
- [Spring Security — DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html#_delegatingpasswordencoder): tiền tố `{id}`, hỗ trợ nhiều hash format.
- [Java 17 — CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): `CodingErrorAction.REPORT` cho Unicode không hợp lệ.

**Ghi chú:** mã runnable bám theo Spring Security 6.5.11. Với Spring Security 7, bản vendor-patched hoặc encoder tùy chỉnh, phải kiểm tra Javadoc, advisory và test độ dài byte trên đúng implementation được triển khai. Mục đích là **xây chính sách đầu vào rõ ràng và an toàn**, không dựa vào một thông báo exception hay hành vi truncate lịch sử của thư viện.