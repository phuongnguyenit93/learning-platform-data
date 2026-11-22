# PasswordEncoderFactories và DelegatingPasswordEncoder

**Module:** Spring Security – authentication. **Nhóm kiến thức:** Băm mật khẩu.

## 1. Vấn đề thực tế: một hệ thống có nhiều thế hệ mật khẩu

Hãy tưởng tượng một ứng dụng phát triển qua nhiều năm:

- Tài khoản rất cũ có password được lưu bằng một định dạng lịch sử, ví dụ `{noop}legacy-password` (chỉ để minh họa, **không an toàn**).
- Tài khoản khác có hash PBKDF2, scrypt hoặc bcrypt được tạo theo những tham số khác nhau.
- Tài khoản mới cần dùng thuật toán/password hashing policy hiện tại.
- Ứng dụng không biết raw password của người dùng để chuyển toàn bộ database sang định dạng mới trong một lần.

Nếu cấu hình chỉ `new BCryptPasswordEncoder()`, bạn có thể **không kiểm chứng được** chuỗi đang lưu dưới dạng `{pbkdf2}...` hoặc `{noop}...`. Nếu giữ một encoder cũ để tất cả tài khoản đăng nhập được, các password tạo mới tiếp tục dùng thuật toán kém an toàn.

Spring Security giải quyết bằng **`DelegatingPasswordEncoder`**, và cung cấp factory tiện dụng **`PasswordEncoderFactories.createDelegatingPasswordEncoder()`**:

1. **Encode** password mới bằng một encoder được chọn làm chuẩn hiện tại, mặc định trong Spring Security 6.5 là bcrypt.
2. **Match** password được nhập với hash có sẵn bằng encoder tương ứng với tiền tố `{id}` của **giá trị lưu trữ**.
3. **Xác định nhu cầu upgrade** khi hash dùng thuật toán hoặc work factor cũ để ứng dụng có thể nâng cấp khi biết raw password hợp lệ.
4. Cho phép các định dạng lịch sử cùng tồn tại trong giai đoạn chuyển đổi, thay vì buộc người dùng reset ngay tất cả tài khoản.

**Điểm cốt lõi:** `PasswordEncoderFactories` là **lớp factory** tạo encoder. `DelegatingPasswordEncoder` là **encoder thực tế** định tuyến theo ID. Cả hai không phải cơ chế mã hóa giải mã hai chiều, không phải authentication manager và không tự quản lý tài khoản.

## 2. Nhớ đúng hợp đồng PasswordEncoder

Giao diện `org.springframework.security.crypto.password.PasswordEncoder` có các phương thức chính:

~~~java
String encode(CharSequence rawPassword);

boolean matches(CharSequence rawPassword, String encodedPassword);

boolean upgradeEncoding(String encodedPassword);
~~~

| Phương thức | Đầu vào | Công việc | Kết quả |
| --- | --- | --- | --- |
| `encode(raw)` | Password người dùng vừa tạo/đổi | Tạo giá trị hash mới theo cấu hình encoder | `String` để lưu (có `{id}` với DelegatingPasswordEncoder) |
| `matches(raw, stored)` | Raw password từ yêu cầu login và chuỗi lưu trong kho | Kiểm tra có khớp không; **không cần giải mã** | `true` hoặc `false` nếu có encoder phù hợp và định dạng hợp lệ; ID không hợp lệ có thể ném exception |
| `upgradeEncoding(stored)` | Hash đã lưu | Chỉ ra hash nên được tạo lại với policy mới hay không | `boolean`; không tự ghi dữ liệu |

Ví dụ **không nên** kiểm tra bằng:

~~~java
// SAI trong đa số password encoder có salt ngẫu nhiên:
boolean valid = encoder.encode(rawPassword).equals(storedPassword);
~~~

Vì hai lần encode cùng raw password có thể tạo **hai hash khác nhau** do salt ngẫu nhiên. Phải dùng:

~~~java
boolean valid = encoder.matches(rawPassword, storedPassword);
~~~

**Băm mật khẩu** là phép biến đổi một chiều có salt và work factor phù hợp. Không dùng `Base64.getEncoder()`, AES giải mã được, MD5/SHA-256 đơn lượt hoặc `String.hashCode()` như phương pháp lưu password. Dữ liệu bị rò rỉ vẫn có thể bị tấn công đoán password offline, nên cần thuật toán chậm và password policy phù hợp.

## 3. PasswordEncoderFactories tạo gì?

API đầy đủ:

~~~java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder passwordEncoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Đây là **đoạn minh họa API**, cần dependency `spring-security-crypto` (và dependency tương ứng của ứng dụng); không phải chương trình Java độc lập.

Với Spring Security **6.5.11**, factory trả một `PasswordEncoder` thực tế là `DelegatingPasswordEncoder`, cấu hình:

- **`idForEncode = "bcrypt"`**: tạo password mới với `BCryptPasswordEncoder`.
- Một map `id -> PasswordEncoder`: chọn encoder để **đối chiếu** hash lịch sử theo ID.
- Format string `{id}encodedPassword` được sử dụng để biết algorithm ở lúc đối chiếu.

**Quan trọng:** Kiểu trả về của method factory là interface `PasswordEncoder`, nên code ứng dụng thường chỉ cần phụ thuộc vào interface. Factory không phải nơi bạn gọi `matches` trực tiếp; phải gọi lên **instance** trả về.

### Những mapping có sẵn trong 6.5.11

| ID trong giá trị lưu | Encoder tương ứng | Ý nghĩa khi đọc dữ liệu |
| --- | --- | --- |
| `bcrypt` | `BCryptPasswordEncoder` | **Mặc định dùng để encode hash mới** trong factory này |
| `pbkdf2` | PBKDF2 với thông số Spring Security 5.5 | Hỗ trợ đọc dữ liệu theo bộ thông số lịch sử |
| `pbkdf2@SpringSecurity_v5_8` | PBKDF2 với thông số Spring Security 5.8 | Phân biệt cấu hình theo phiên bản |
| `scrypt` | scrypt theo cấu hình Spring Security 4.1 | Đọc hash thuộc cấu hình lịch sử |
| `scrypt@SpringSecurity_v5_8` | scrypt theo thông số Spring Security 5.8 | Phân biệt work factor/định dạng phiên bản |
| `argon2` | Argon2 theo thông số Spring Security 5.2 | Hỗ trợ định dạng cũ của Argon2 |
| `argon2@SpringSecurity_v5_8` | Argon2 theo thông số Spring Security 5.8 | Hỗ trợ thông số khác |
| `noop` | `NoOpPasswordEncoder` | Đối chiếu plaintext lịch sử; **không dùng để lưu mật khẩu mới** |
| `ldap` | `LdapShaPasswordEncoder` | Tương thích một định dạng LDAP cũ |
| `MD4`, `MD5` | Message-digest encoder tương ứng | Lịch sử, không đủ an toàn cho password mới |
| `SHA-1`, `SHA-256` | `MessageDigestPasswordEncoder` | Digest nhanh lịch sử, **không khuyến nghị** cho password mới |
| `sha256` | `StandardPasswordEncoder` cũ | Khác `SHA-256` phía trên; chỉ phục vụ legacy |

Danh sách lấy theo Javadoc factory Spring Security 6.5.11. Cách cấu hình mapping và thuật toán encode mặc định **có thể thay đổi qua phiên bản Spring Security**; đừng hardcode suy đoán mà không kiểm tra version của dự án.

**Tương thích cũ không đồng nghĩa mọi thuật toán đều an toàn.** Có `noop`, MD5 hay SHA-1 trong map chỉ giúp ứng dụng nhận diện/vượt qua giai đoạn migration. Không dùng những ID này để tạo account mới. Khi không còn bản ghi cần các encoder legacy, hãy đánh giá việc thu hẹp mapping hoặc di chuyển hệ thống sang policy phù hợp hơn.

## 4. Chuỗi `{id}encodedPassword` có cấu trúc gì?

Với factory mặc định, đầu ra có thể trông như sau:

~~~text
{bcrypt}$2a$10$XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
└──────┘└──────────────────────────────────────────────────────────┘
   id              encodedPassword do BCrypt tạo
~~~

Dòng trên **là sơ đồ cấu trúc, không phải một hash bcrypt thật có thể xác thực**. Mỗi lần encode thường có salt ngẫu nhiên nên kết quả thay đổi. Không được dùng chuỗi `X...` như hash thật.

Cú pháp tổng quát:

~~~text
{id}encodedPassword
~~~

- `{` và `}` định vị **ID** ở **đầu chuỗi**.
- `id` là khóa tra encoder, ví dụ `bcrypt`, `pbkdf2@SpringSecurity_v5_8`.
- `encodedPassword` giữ định dạng do encoder cụ thể tạo ra; có thể bao gồm salt, cost, digest hoặc metadata nội bộ của thuật toán.
- ID **phân biệt hoa/thường**: `{bcrypt}` và `{BCrypt}` không mặc nhiên là cùng khóa.
- ID không phải secret/key, không mã hóa thông tin bằng cách giấu tên thuật toán; bí mật cần bảo vệ vẫn là password raw và các yếu tố vận hành liên quan.

Ví dụ minh họa định dạng:

~~~text
{bcrypt}$2a$10$...                          # bcrypt
{noop}legacy-password                      # plaintext, chỉ đọc trong migration
{pbkdf2@SpringSecurity_v5_8}...             # PBKDF2 theo bộ thông số 5.8
{scrypt@SpringSecurity_v5_8}...             # scrypt theo bộ thông số 5.8
{argon2@SpringSecurity_v5_8}...             # Argon2 theo bộ thông số 5.8
~~~

Những ký hiệu `...` là **minh họa**, không phải giá trị hash hợp lệ.

### Hai loại thông tin thường bị nhầm

**ID encoder:** `{bcrypt}` chỉ ra phải dùng implementation BCrypt để match, và với factory mặc định đó cũng là ID tạo mới.

**Cost/salt của bcrypt:** Phần `$2a$10$...` chứa thông số riêng của bcrypt, chẳng hạn work factor. Thay đổi `BCryptPasswordEncoder` strength **không yêu cầu** thay tên ID nhất thiết; encoder biết đọc cost từ hash bcrypt lưu trữ và có thể xác định việc cần nâng cấp.

Không cắt bỏ phần `{bcrypt}` trước khi ghi xuống DB nếu ứng dụng đang sử dụng `DelegatingPasswordEncoder`. Không tự cắt một đoạn hash để “tiết kiệm cột” vì sẽ làm đối chiếu thất bại.

## 5. DelegatingPasswordEncoder chọn encoder như thế nào?

### 5.1. Encode: luôn theo idForEncode

~~~text
rawPassword
    |
    v
DelegatingPasswordEncoder.encode(raw)
    |
    +--> idForEncode = "bcrypt"
                 |
                 v
          BCryptPasswordEncoder.encode(raw)
                 |
                 v
   "{bcrypt}" + bcryptEncodedPassword
~~~

Mặc dù map có cả PBKDF2, scrypt, MD5, noop..., **điều đó không khiến encode tự thay đổi theo từng user**. Nếu không tự cấu hình lại, phương thức `encode` của factory hiện tại vẫn dùng bcrypt.

### 5.2. Matches: ID được lấy từ stored password

~~~text
rawPassword từ form + storedPassword từ DB
                          |
                          v
                 Parse prefix {id}
                          |
             +------------+-------------+
             |                          |
         {bcrypt}                   {pbkdf2}
             |                          |
             v                          v
  BCryptPasswordEncoder       Pbkdf2PasswordEncoder
             |                          |
             +------------+-------------+
                          |
                          v
                matches(raw, payload)
                          |
                          v
                     true / false
~~~

Trong ví dụ này, **client không được chọn algorithm** qua body/query. Hệ thống đọc **stored encoded password đáng tin** để biết cách kiểm tra. Nếu cho client gửi `{noop}...` và dùng nó như stored value để “authenticate”, bạn đã bỏ qua ranh giới tin cậy.

#### Ví dụ các kết quả theo ID

| Giá trị lưu | Điều xảy ra với factory mặc định |
| --- | --- |
| `{bcrypt}<hash-bcrypt-hợp-lệ>` | Gọi BCrypt matches |
| `{noop}legacy-password` | Gọi NoOp matches với chuỗi `legacy-password`; chỉ dùng như tình huống migration |
| `{pbkdf2@SpringSecurity_v5_8}<hash-phù-hợp>` | Gọi PBKDF2 version 5.8 |
| `$2a$10$...` **không có prefix** | Không tìm được ID → mặc định ném `IllegalArgumentException` |
| `{unknown}<payload>` | ID không có trong mapping → mặc định ném `IllegalArgumentException` |
| `{bcrypt}chuoi-khong-phai-bcrypt` | Có ID nhưng payload không hợp lệ → BCrypt có thể trả false và ghi cảnh báo an toàn tùy implementation |

**Không tự kết luận** mọi exception do format sai tương đương user nhập password sai. Sai ID/cấu hình/DB schema có thể là lỗi vận hành cần xử lý và audit. Đặc biệt, đừng trả chi tiết hash, prefix không hỗ trợ hoặc stack trace cho client chưa xác thực.

## 6. Demo Java 17 chạy độc lập: tạo, kiểm tra, tương thích cũ và unknown ID

Demo dùng Gradle, **Spring Security 6.5.11**, không cần Spring Boot, web server hoặc DB. Mục tiêu là tạo output deterministic dù bcrypt có salt ngẫu nhiên.

### 6.1. Cấu trúc dự án

~~~text
password-delegation/
├── build.gradle
└── src/main/java/demo/PasswordDelegationDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.PasswordDelegationDemo'
}
~~~

**File `src/main/java/demo/PasswordDelegationDemo.java`:**

~~~java
package demo;

import java.util.Map;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordDelegationDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String raw = "learning-only-password";
        String stored = encoder.encode(raw);

        System.out.println("factory.type="
                + encoder.getClass().getSimpleName());
        System.out.println("new.hasBcryptPrefix="
                + stored.startsWith("{bcrypt}"));
        System.out.println("new.matchesCorrect="
                + encoder.matches(raw, stored));
        System.out.println("new.matchesIncorrect="
                + encoder.matches("wrong-password", stored));
        System.out.println("new.needsUpgrade="
                + encoder.upgradeEncoding(stored));

        // Chỉ minh họa khả năng đọc legacy {noop}; không dùng để
        // tạo mật khẩu mới hoặc làm policy production.
        String legacy = "{noop}old-learning-password";
        System.out.println("legacy.matches="
                + encoder.matches("old-learning-password", legacy));
        System.out.println("legacy.needsUpgrade="
                + encoder.upgradeEncoding(legacy));

        // Minh họa rehash khi đã biết raw password đúng.
        String migrated = encoder.encode("old-learning-password");
        System.out.println("migrated.hasBcryptPrefix="
                + migrated.startsWith("{bcrypt}"));
        System.out.println("migrated.matches="
                + encoder.matches("old-learning-password", migrated));

        try {
            encoder.matches("guess", "unprefixed-legacy");
            System.out.println("missingPrefix=unexpected-success");
        } catch (IllegalArgumentException expected) {
            System.out.println("missingPrefix=IllegalArgumentException");
        }

        try {
            encoder.matches("guess", "{notMapped}payload");
            System.out.println("unknownId=unexpected-success");
        } catch (IllegalArgumentException expected) {
            System.out.println("unknownId=IllegalArgumentException");
        }

        // Cấu hình map tùy biến hẹp: chỉ nhận bcrypt.
        PasswordEncoder bcryptOnly = new DelegatingPasswordEncoder(
                "bcrypt", Map.of("bcrypt", new BCryptPasswordEncoder())
        );
        System.out.println("custom.matchesBcrypt="
                + bcryptOnly.matches(raw, stored));

        try {
            bcryptOnly.matches("old-learning-password", legacy);
            System.out.println("custom.rejectsNoop=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("custom.rejectsNoop=true");
        }
    }
}
~~~

Chạy từ thư mục `password-delegation` với JDK 17+ và Gradle tương thích:

~~~bash
gradle -q run
~~~

Nếu dự án có Gradle Wrapper, dùng `./gradlew -q run`; Windows dùng `gradlew.bat -q run`. Lần đầu cần tải thư viện từ Maven Central.

**Stdout do chương trình tự in** (không kể log riêng của Gradle/các thư viện nếu môi trường có cấu hình khác):

~~~text
factory.type=DelegatingPasswordEncoder
new.hasBcryptPrefix=true
new.matchesCorrect=true
new.matchesIncorrect=false
new.needsUpgrade=false
legacy.matches=true
legacy.needsUpgrade=true
migrated.hasBcryptPrefix=true
migrated.matches=true
missingPrefix=IllegalArgumentException
unknownId=IllegalArgumentException
custom.matchesBcrypt=true
custom.rejectsNoop=true
~~~

### 6.2. Giải thích chi tiết output

- `factory.type=DelegatingPasswordEncoder`: factory trả instance implements `PasswordEncoder`.
- `new.hasBcryptPrefix=true`: ID tạo mới được factory 6.5.11 chọn là `bcrypt`.
- `new.matchesCorrect=true` dù hash mỗi lần ngẫu nhiên: `matches` đọc salt/work factor từ hash và kiểm chứng raw password.
- `new.matchesIncorrect=false`: hai raw password khác nhau không khớp hash lưu.
- `new.needsUpgrade=false`: bcrypt vừa được tạo với cost mặc định của cùng encoder nên chưa cần rehash theo chính sách đó.
- `legacy.matches=true`: factory **có mapping legacy noop**; điều này chỉ phục vụ minh họa chuyển đổi và **là rủi ro nếu production còn password dạng plaintext**.
- `legacy.needsUpgrade=true`: ID legacy khác `idForEncode=bcrypt`, nên có tín hiệu cần migrate.
- `migrated.hasBcryptPrefix=true`: khi biết raw password hợp lệ, có thể tạo hash mới theo policy hiện tại.
- `missingPrefix` và `unknownId`: không có mapping phù hợp; mặc định không fallback im lặng.
- `custom.matchesBcrypt=true` và `custom.rejectsNoop=true`: một map chỉ chứa bcrypt vẫn kiểm chứng bcrypt, nhưng chủ động không tiếp nhận noop; custom map **không tự kế thừa mapping từ factory**.

**Không so sánh nguyên văn chuỗi bcrypt.** Salt ngẫu nhiên khiến hash cụ thể khác nhau giữa các lần chạy, nên ví dụ chỉ in prefix và các điều kiện boolean có thể dự đoán.

### 6.3. Demo không tự làm migration ở database

Ví dụ tạo biến `migrated` trong bộ nhớ; **chưa update record nào**. Một ứng dụng thật chỉ nên persist hash mới sau khi đã xác thực raw password thành công và bảo đảm request không thuộc tài khoản bị khóa/disabled. Update nên tránh ghi đè bản password mới hơn do thay đổi đồng thời.

## 7. Nâng cấp password hash an toàn

### 7.1. Tại sao phải nâng cấp?

Thuật toán và cost tối ưu thay đổi theo thời gian, phần cứng và yêu cầu an ninh. Hệ thống có thể muốn:

- Chuyển từ `{noop}` hoặc digest không đủ chậm sang bcrypt/Argon2/PBKDF2 được cấu hình phù hợp;
- Tăng work factor cho bcrypt khi phần cứng mạnh hơn;
- Từ một bộ thông số PBKDF2/scrypt/Argon2 cũ sang thông số mới;
- Dùng thêm policy phát hiện password yếu/bị lộ theo khuyến nghị hiện hành.

`DelegatingPasswordEncoder.upgradeEncoding(stored)` giúp đánh giá việc **có nên rehash**. Với default factory 6.5.11, hash có ID khác `bcrypt` thường được xem là ứng viên nâng cấp; hash bcrypt cũng có thể cần nâng nếu cost thấp hơn cấu hình bcrypt hiện tại.

**Phương thức này không tự giải mã password và không tự ghi DB.** Không thể chuyển hash một chiều thành bcrypt mới nếu không biết raw password. Có hai con đường phổ biến: **rehash sau login thành công** hoặc **yêu cầu reset password** cho user chưa quay lại.

### 7.2. Rehash-on-login đúng ranh giới

~~~text
POST /login: username + raw password
                |
                v
      AuthenticationManager / Provider
                |
         +------+------+
         |             |
    thất bại        thành công
         |             |
         v             v
      deny       matches(raw, stored) = true
                       |
                       v
                upgradeEncoding(stored)?
                       |
               +-------+-------+
               |               |
              no              yes
               |               |
               v               v
          giữ hash       encode(raw) bằng policy mới
                               |
                               v
                          ghi vào DB
                    bằng compare-and-swap
                               |
                               v
                     audit event, evict cache
                               |
                               v
                       trả auth result
~~~

**Quan trọng:** Chỉ rehash **sau khi credentials và trạng thái account đã được kiểm tra hợp lệ**. Không nâng cấp hash cho một yêu cầu username giả hoặc password sai. Hạn chế nhật ký chứa raw password, hash mới và thời gian sống của credentials.

### 7.3. DaoAuthenticationProvider + UserDetailsPasswordService

Spring Security có interface `UserDetailsPasswordService` với method:

~~~java
UserDetails updatePassword(UserDetails user, String newPassword);
~~~

`newPassword` ở đây là **encoded password mới** do `PasswordEncoder.encode(...)` tạo ra, không phải plaintext. Khi `DaoAuthenticationProvider` được cấu hình `UserDetailsPasswordService`, provider có thể gọi `PasswordEncoder.upgradeEncoding(...)` sau khi xác thực thành công và ủy quyền việc lưu hash mới cho service.

**Mẫu cấu hình tích hợp, không phải class độc lập:**

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
DaoAuthenticationProvider daoAuthenticationProvider(
        UserDetailsService userDetailsService,
        UserDetailsPasswordService passwordUpdater,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);

    provider.setPasswordEncoder(passwordEncoder);
    provider.setUserDetailsPasswordService(passwordUpdater);
    return provider;
}
~~~

Mẫu này giả định ứng dụng Spring Boot Servlet đã có `@Bean` imports, beans `UserDetailsService`/`UserDetailsPasswordService`, kho tài khoản và wiring `SecurityFilterChain` thích hợp. **Không phải** chỉ copy hai bean trên vào ứng dụng là mọi đường login tự dùng provider hoặc tự migrate database.

Nếu không có `UserDetailsPasswordService` phù hợp hoặc chưa gắn nó vào provider, **đừng mặc định migration tự diễn ra**. Việc gọi `encoder.matches(...)` và `encoder.upgradeEncoding(...)` một mình chỉ kiểm tra điều kiện; sẽ không ghi password mới.

`UserDetailsPasswordService` khác với `UserDetailsManager.changePassword(oldPassword,newPassword)` của luồng user tự thay đổi password. Một interface phục vụ provider **nâng cấp hash sau login**, interface kia phục vụ **thao tác account management**. Cần phân biệt quyền actor, audit và cách sử dụng raw password.

### 7.4. Kiểm soát concurrency khi nâng cấp

Ví dụ request A login bằng password cũ và bắt đầu rehash; đồng thời request B đã reset password sang giá trị mới. Nếu A ghi hash mới của password cũ sau khi B reset, hệ thống có thể **vô tình khôi phục password cũ**.

Không chỉ dùng:

~~~java
// MÃ MINH HỌA KHÔNG AN TOÀN nếu thiếu kiểm tra concurrency:
repository.updatePasswordHash(userId, freshlyEncodedHash);
~~~

Thiết kế an toàn hơn là cập nhật có điều kiện, ví dụ:

~~~sql
-- SQL minh họa: thay đổi đồng thời không bị ghi đè.
UPDATE users
SET password_hash = :newHash,
    password_version = password_version + 1
WHERE id = :userId
  AND password_hash = :oldHash
  AND password_version = :oldVersion;
~~~

**Số hàng được update phải là 1** mới coi upgrade thành công. Nếu bằng 0, có thay đổi đồng thời; không ghi đè, xử lý lại hoặc chấp nhận bản hash mới theo logic xác thực đã xác nhận. Tùy schema, có thể chỉ dùng version thay vì so sánh hash; cách thực thi phải phù hợp transaction/DB của ứng dụng.

Sau upgrade, cần xóa cache `UserDetails`/authentication data tương ứng, xử lý dữ liệu replica và mọi mapping username/tenant. Đừng hiểu việc upgrade hash tự động logout session hoặc thu hồi JWT; đó là một quyết định session/token policy khác.

## 8. Dữ liệu legacy không có prefix: xử lý thế nào?

Một lỗi thường gặp khi nâng cấp Spring Security:

~~~text
There is no PasswordEncoder mapped for the id "null"
~~~

Lỗi này có thể xuất hiện nếu DB lưu trực tiếp bcrypt payload:

~~~text
$2a$10$...
~~~

mà ứng dụng đã chuyển sang `DelegatingPasswordEncoder`, vốn tìm ID ở **đầu giá trị lưu**, ví dụ `{bcrypt}$2a$10$...`.

**Không phải khắc phục bằng `NoOpPasswordEncoder` toàn cục.** Điều đó có thể làm yếu xác thực, đặc biệt nếu DB đang chứa plaintext không được bảo vệ.

### Phương án A – Chuyển dữ liệu đã biết thuật toán sang prefix chính xác

Nếu đã xác minh **toàn bộ nhóm record** là bcrypt (đúng format, đúng nguồn, đúng policy), có thể bổ sung `{bcrypt}` ở đầu theo migration được kiểm soát.

~~~text
Trước: $2a$10$<bcrypt-hash-hợp-lệ>
Sau:   {bcrypt}$2a$10$<cùng-hash>
~~~

Không cần biết raw password vì **chỉ thêm metadata ID**, không đổi hash gốc. Nhưng nếu dữ liệu là hỗn hợp bcrypt, scrypt, SHA..., không được thêm `{bcrypt}` đồng loạt.

Các bước thực tế: backup, phân tích dữ liệu và những định dạng thực có, kiểm thử trên bản sao, SQL migration có điều kiện, kiểm tra độ dài cột và encoding, triển khai có rollback, giám sát login failures. Nếu DB có password hash không rõ loại, yêu cầu reset có thể an toàn hơn đoán format.

### Phương án B – Fallback có kiểm soát cho cohort xác định

`DelegatingPasswordEncoder` có:

~~~java
void setDefaultPasswordEncoderForMatches(
        PasswordEncoder defaultPasswordEncoderForMatches);
~~~

Đây là **API cấu hình** để sử dụng một encoder thay thế khi stored ID không có trong map (kể cả thiếu ID). Mặc định Spring Security **ném IllegalArgumentException** cho những trường hợp đó.

**Nguy cơ:** Fallback có thể khiến dữ liệu sai format/unknown ID được diễn giải theo thuật toán không mong muốn. Ngoài ra, encoder fallback nhận **toàn bộ chuỗi stored** bao gồm cả `{id}` chưa được ánh xạ, không tự được tách phần prefix. Không được mù quáng gắn `NoOpPasswordEncoder` hoặc fallback “thử tất cả thuật toán đến khi match” cho mọi user.

Nếu thật sự phải dùng fallback ngắn hạn:

1. Giới hạn cohort bằng dữ liệu migrate đã xác minh, không dựa vào dữ liệu client.
2. Viết và kiểm thử parser định dạng cụ thể; unknown ID phải bị từ chối.
3. Tạo metric migration để biết số record còn thiếu prefix.
4. Bắt buộc nâng cấp sau login thành công hoặc reset.
5. Gỡ fallback khi cohort đã được xử lý.

### Phương án C – Reset password

Khi lịch sử hash không đáng tin, algorithm không còn hỗ trợ, hoặc không thể xác minh định dạng, yêu cầu người dùng đặt password mới qua **kênh khôi phục đã được xác minh**. Không bao giờ suy ra raw password từ hash; password hashing đúng thiết kế không có hàm decrypt.

## 9. Tự cấu hình DelegatingPasswordEncoder

Bạn có thể dùng constructor trực tiếp khi cần map được kiểm soát:

~~~java
import java.util.Map;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

Map<String, PasswordEncoder> encoders = Map.of(
        "bcrypt", new BCryptPasswordEncoder(12)
);

PasswordEncoder encoder =
        new DelegatingPasswordEncoder("bcrypt", encoders);
~~~

Đây là đoạn Java minh họa, **không phải class standalone**. Nó có các tính chất:

- ID mặc định để encode là `bcrypt`, với strength 12 được chỉ định.
- Khi `matches` gặp `{bcrypt}`, encoder có thể kiểm tra hash bcrypt có work factor cũ do thông tin cost nằm trong hash.
- `{noop}...` hoặc ID khác **không được hỗ trợ** vì map chỉ có bcrypt.
- Factory map mặc định **không tự được kế thừa**. Nếu hệ thống cần đọc nhiều định dạng cũ, phải khai báo các encoder tương ứng theo chính sách migration.

**Đừng tăng strength tùy ý** khi chưa benchmark. BCrypt dùng work factor khiến thời gian tính tăng nhanh; quá cao có thể làm login chậm hoặc gây quá tải CPU trước request flood. Quá thấp làm hash dễ bị tấn công offline hơn. Xem yêu cầu hiệu năng, chính sách an toàn, khả năng phần cứng, cơ chế rate limit và thời gian login mục tiêu.

### ID và thuật toán không buộc phải trùng tên mặc định

Một hệ thống có thể muốn ID versioned:

~~~java
Map<String, PasswordEncoder> encoders = Map.of(
        "bcrypt-v2", new BCryptPasswordEncoder(12),
        "bcrypt-v1", new BCryptPasswordEncoder(10)
);

PasswordEncoder encoder =
        new DelegatingPasswordEncoder("bcrypt-v2", encoders);
~~~

Khi encode mới, chuỗi bắt đầu `{bcrypt-v2}`; khi match chuỗi có `{bcrypt-v1}`, map chọn implementation tương ứng, và `upgradeEncoding(...)` thường nhận ra ID cũ khác chuẩn mới.

**Lưu ý:** Với BCrypt, hash đã chứa cost nên nhiều hệ thống chỉ cần một ID `bcrypt` và đổi strength qua policy; sử dụng ID versioned hay không là một quyết định về dữ liệu, triển khai và khả năng migration. Đừng đổi ID tùy tiện rồi quên map/DB history.

### Khi chọn Argon2/PBKDF2/scrypt làm encoder tạo mới

Có thể tự tạo `DelegatingPasswordEncoder` với ID và encoder phù hợp thay vì dựa vào factory mặc định là bcrypt. Nhưng cần kiểm tra:

- Phiên bản thuật toán, cost/iteration/memory/concurrency và các dependency cần thiết;
- Khả năng tương thích Java/runtime và dữ liệu hash đã lưu;
- Benchmark trên phần cứng production, giới hạn tải login và password reset;
- Cách hoạt động của `upgradeEncoding(...)` và chính sách chuyển đổi khi đổi tham số;
- Các quy định nội bộ/ngành (ví dụ một môi trường có yêu cầu tuân thủ nhất định).

**Không suy ra** factory mặc định sẽ tự chuyển sang Argon2 chỉ vì map có ID Argon2.

## 10. Tích hợp trong ứng dụng Spring Boot Servlet

### 10.1. Khai báo một bean PasswordEncoder

~~~java
@Configuration
class SecurityPasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

Đây là **một mảnh cấu hình** trong ứng dụng Spring Boot đã có dependency và imports của `@Configuration`, `@Bean`, `PasswordEncoder`, `PasswordEncoderFactories`. Nó không chứa main class, repository, provider hay routes nên không phải chương trình độc lập.

Nếu ứng dụng dùng Spring Boot, thường quản lý version của các mô-đun Spring Security bằng BOM/dependency management của Boot, thay vì trộn nhiều version thủ công.

### 10.2. Khi tạo user

~~~java
// Bên trong service được authorize; không phải class độc lập.
String passwordHash = passwordEncoder.encode(signupRawPassword);

UserDetails user = User.withUsername(validatedUsername)
        .password(passwordHash)
        .roles("USER") // role phía server, không từ request
        .build();

userDetailsManager.createUser(user);
~~~

**Lưu chính xác chuỗi `{bcrypt}...`** do `encode(...)` trả về vào DB. Không gọi encode lần nữa trước khi persist, vì double hashing sẽ làm password gốc không khớp. Không cố định “hash luôn dài 60 ký tự” vì có tiền tố `{id}` và những thuật toán khác có độ dài khác.

### 10.3. Khi login

~~~text
UsernamePasswordAuthenticationFilter
               |
               v
AuthenticationManager / ProviderManager
               |
               v
DaoAuthenticationProvider
       |                |
       v                v
UserDetailsService   PasswordEncoder
   load hash         matches(raw, stored)
       |                |
       +--------+-------+
                |
         valid credential?
                |
        +-------+-------+
        |               |
       no              yes
        |               |
        v               v
 AuthenticationException   authenticated Authentication
                            |
                            v
                        SecurityContext
~~~

`DaoAuthenticationProvider` dùng `PasswordEncoder` được cấu hình để đối chiếu password người dùng vừa nhập với `UserDetails.getPassword()`. Với Spring Security 6.5, nếu không cấu hình riêng, provider có cơ chế dùng delegating encoder mặc định; nhưng trong hệ thống thực nên cấu hình rõ ràng **để policy tạo password và policy kiểm tra password nhất quán**.

Nên viết test end-to-end qua đúng filter chain/controller của ứng dụng, vì một bean đúng nhưng provider/filter khác không dùng bean đó vẫn có thể gây lỗi.

### 10.4. Khi đổi mật khẩu

Luồng self-service đổi password khác với rehash-on-login:

1. Người dùng đã xác thực, có thể cần xác thực lại password cũ/MFA tùy rủi ro.
2. Kiểm tra chính sách password mới và bảo vệ CSRF/session.
3. `passwordEncoder.encode(newRawPassword)` tạo giá trị `{id}...`.
4. Cập nhật kho tài khoản đúng user/tenant trong transaction và audit an toàn.
5. Áp dụng chính sách session/token invalidation nếu cần.
6. Xóa/refresh `UserDetails` cache và nguồn quyền liên quan khi dữ liệu auth thay đổi.

Đừng truyền plaintext vào nơi nhận **encoded password** với kỳ vọng manager tự băm. `UserDetailsManager.changePassword` và các implementation phải được kiểm tra contract cụ thể.

## 11. Dữ liệu, giao dịch và các quy tắc vận hành

### 11.1. Độ dài cột

Một cột `password_hash VARCHAR(60)` có thể đủ cho payload bcrypt cổ điển nhưng **không đủ** cho `{bcrypt}` + payload, và càng không phải lời bảo đảm cho Argon2/PBKDF2 hoặc dữ liệu tương lai. Chọn giới hạn theo thuật toán đang hỗ trợ và lộ trình migration; ví dụ `VARCHAR(255)` hoặc lớn hơn **theo thiết kế schema và thực tế lưu trữ**. Test insert/readback để chắc chắn không bị cắt mất prefix/salt.

### 11.2. Tính nhất quán của hash

Khi nâng cấp hash trong môi trường có DB replication, multiple nodes hoặc cache:

- Cập nhật hash và password version atomically;
- Evict cache user details **sau commit**; tránh loader repopulate bản cũ;
- Trong login có upgrade, kiểm tra race với password reset/new password;
- Đảm bảo các node đều biết mapping `{id}` đã được deploy trước khi DB ghi format mới;
- Trong rolling deployment, không ghi hash với ID mà phiên bản ứng dụng cũ chưa hỗ trợ;
- Giám sát tỉ lệ login fail do unknown ID và tỉ lệ migration thành công.

Nếu rollout encoder mới theo nhiều node, ưu tiên **dual-read, single-write**: mọi node đọc được cả format cũ và mới trước khi bất kỳ node nào bắt đầu ghi format mới. Khi toàn bộ dữ liệu đã nâng cấp và giai đoạn rollback kết thúc, có thể dần bỏ mapping cũ theo chính sách.

### 11.3. Quyền truy cập dữ liệu hash

Hash một chiều không biến database thành công khai. Bảo vệ quyền SELECT cột password, backup, export, log, traces, Redis/cache, quyền DBA/admin và dữ liệu gửi qua mạng. Không log cả `UserDetails` hay giá trị hash khi có lỗi `matches(...)`. Dùng TLS cho login và có rate-limit phù hợp để bảo vệ chi phí tính hash.

### 11.4. Hashing không thay thế MFA hoặc kiểm tra mật khẩu bị lộ

Thuật toán password hashing chậm giúp giảm hiệu quả tấn công offline sau khi DB lộ. Nó **không tự ngăn** password spraying online, credential stuffing hoặc phishing. Cần thêm bảo vệ rate limit, chống enumeration, MFA/passkey khi phù hợp, session hygiene và quy trình reset/recovery an toàn.

## 12. Một số lỗi và cách xác định đúng nguyên nhân

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra và sửa |
| --- | --- | --- |
| `There is no PasswordEncoder mapped for id "null"` | DB đang chứa hash không có `{id}`, hoặc sai prefix | Phân tích format đã lưu, migration thêm prefix đúng thuật toán |
| `There is no PasswordEncoder mapped for id "foo"` | `{foo}` không có trong mapping | Kiểm tra version, map và dữ liệu, không fallback tùy tiện |
| Đăng ký thành công nhưng login luôn fail | DB lưu raw password trong hệ thống mong đợi `{bcrypt}`, hoặc double-encode | Kiểm tra path tạo account/encode đúng một lần |
| Login fail sau khi nâng cấp | Code nơi tạo user dùng BCrypt thô, nơi login dùng Delegating hoặc ngược lại | Thống nhất encoder và định dạng dữ liệu ở mọi nơi |
| Hash bị cắt trong DB | Cột quá ngắn cho prefix/format mới | Mở rộng schema, kiểm tra dữ liệu hư, reset password cần thiết |
| `matches(raw, encoded)` trả false | Password sai hoặc payload đúng ID nhưng không khớp, đôi khi dữ liệu bị sai | Không tiết lộ chi tiết cho client; kiểm tra nội bộ format/hash/encoder |
| `newHash.equals(oldHash)` false dù raw giống nhau | Random salt | Dùng `matches(...)`, không so sánh chuỗi hash |
| `upgradeEncoding` true nhưng DB không đổi | Chưa gắn `UserDetailsPasswordService` hoặc chưa triển khai write | Cấu hình upgrade pipeline, test storage readback |
| Password cũ được khôi phục sau reset | Race giữa rehash-on-login và password reset | CAS/version trong DB transaction |
| Cấu hình custom chỉ có bcrypt làm user cũ không đăng nhập | Bỏ mapping legacy cần thiết | Triển khai migration có dual-read trước, sau đó retire legacy |
| `{noop}` được dùng để tạo tài khoản mới | Chọn thuật toán không an toàn hoặc test config lọt production | Factory mặc định dùng bcrypt; kiểm soát security config theo môi trường |
| Dùng SHA-256 một lượt để lưu password | Digest quá nhanh cho password storage | Chọn password hashing algorithm được thiết kế cho passwords |
| Rollout app cũ không hiểu ID mới | Thiếu backward compatibility khi deploy nhiều node | Dual-read trước single-write, rollback plan |
| Auth thất bại nhưng trả exception class/hash ra JSON | Lộ thông tin credential policy và account | Public failure generic; audit chi tiết nhưng an toàn |
| Gán `setDefaultPasswordEncoderForMatches(NoOp...)` | Bỏ qua ID không đáng tin; rủi ro fallback quá rộng | Từ chối unknown id, migration cohort an toàn |
| Coi `{id}` là salt hoặc key | Nhầm metadata thuật toán với secret/hash | Phân biệt prefix và payload của algorithm |
| Tăng bcrypt cost quá cao | Login bị chậm/DoS CPU | Benchmark, rate-limit và điều chỉnh cost theo policy |

## 13. Checklist kiểm thử khi triển khai

### Unit tests cho PasswordEncoder

- `encode(raw)` trả hash có tiền tố `{bcrypt}` nếu dùng factory 6.5.11 mặc định.
- `matches(raw, encode(raw))` trả true; `matches(other, encode(raw))` trả false.
- Hai lần encode raw giống nhau có thể khác nhau do random salt; chỉ kiểm tra prefix và matches.
- `matches(raw, "{noop}" + raw)` có thể true trong chế độ tương thích legacy, **không** xem đó là thuật toán sản xuất hợp lệ.
- `matches(raw, storedWithoutId)` và unknown id mặc định ném `IllegalArgumentException`.
- `upgradeEncoding(legacyHash)` true khi ID cũ khác ID encode; hash mới false nếu policy không đổi.
- Custom mapping không tự hỗ trợ các ID bạn không đưa vào map.

### Tests cho account/login thật

- Tạo user bằng luồng đăng ký hiện có, ghi DB, tải `UserDetails.getPassword()`, đối chiếu bằng đúng encoder.
- Login đúng/sai credential qua `AuthenticationManager` hoặc filter chain thật; account locked/disabled vẫn bị từ chối.
- Legacy user đăng nhập thành công và nâng cấp hash **chỉ** nếu `UserDetailsPasswordService` đã được gắn; readback DB thấy prefix/cost mới.
- Khi password reset xảy ra đồng thời với login upgrade, không khôi phục password cũ.
- Tất cả node sau deployment hiểu cả prefix cũ và prefix mới trong rolling upgrade.
- Cache `UserDetails` bị invalidation đúng, không làm xóa hash trong shared object vì `ProviderManager.eraseCredentials()`.
- Lỗi unknown ID/format được ghi metric/audit nội bộ nhưng không tiết lộ cho người chưa xác thực.
- Tài khoản không quay lại được xử lý qua chính sách reset, không dùng plaintext recovery.

### Kiểm thử vận hành

Đo thời gian `encode` và `matches` tại cost dự kiến trên phần cứng và quy mô tải thực tế. Các test xác thực không nên chứa password thật hoặc hash production. Test database có Unicode username, password chứa ký tự ngoài ASCII, cột dài, collation và migration id case-sensitive. Quan sát login failures, CPU, tỷ lệ upgrade, số legacy records còn tồn tại và version compatibility trong mỗi lần rollout.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` có tạo MD5 cho user mới vì map chứa MD5 không?  
**Đáp:** Không. Với factory 6.5.11, `idForEncode=bcrypt`, nên encode mới dùng bcrypt. Các encoder khác dùng cho việc match định dạng tương ứng.

**Câu 2.** Vì sao `{bcrypt}...` khác với `$2a$...` khi dùng DelegatingPasswordEncoder?  
**Đáp:** DelegatingPasswordEncoder dùng `{id}` để chọn implementation. Hash không có prefix có `id=null` và mặc định bị từ chối, dù payload có thể là bcrypt hợp lệ.

**Câu 3.** Gọi `encoder.encode("abc")` hai lần được hai chuỗi khác nhau. Đó có phải lỗi không?  
**Đáp:** Không. Salt ngẫu nhiên tạo hash khác nhau; `matches("abc", stored)` là thao tác đúng để kiểm tra.

**Câu 4.** App lưu `{noop}password` và factory mặc định match được. Có nghĩa bảo mật password đang tốt?  
**Đáp:** Không. Plaintext storage là rủi ro lớn. Mapping tồn tại để đọc legacy trong migration; nên nâng cấp hoặc reset.

**Câu 5.** Có `{unknown}hash` thì tự thêm fallback `NoOpPasswordEncoder` là cách sửa an toàn?  
**Đáp:** Không. Điều đó làm mơ hồ ranh giới định dạng và có thể vô tình chấp nhận chuỗi không được xác minh đúng; nên phân tích/migrate rõ dữ liệu.

**Câu 6.** Sau login, `encoder.upgradeEncoding(oldHash)` true. Database có tự được cập nhật chưa?  
**Đáp:** Chưa. Cần rehash từ raw password đã xác thực và persist; trong DaoAuthenticationProvider có thể sử dụng `UserDetailsPasswordService` được cấu hình thích hợp.

**Câu 7.** Có thể đổi hash MD5 cũ sang bcrypt mà không biết raw password không?  
**Đáp:** Không thể tính bcrypt(raw) từ hash MD5 một chiều theo cách đảm bảo tương đương. Phải rehash khi raw password được cung cấp hợp lệ hoặc reset.

**Câu 8.** Tại sao cả hai node phải hiểu ID mới **trước khi** node đầu tiên ghi hash mới?  
**Đáp:** Node cũ có thể đọc record vừa được nâng cấp và không tìm được encoder cho ID mới, gây lỗi login. Triển khai dual-read trước single-write.

**Câu 9.** Vì sao cột `VARCHAR(60)` có thể sai sau khi chuyển sang delegating?  
**Đáp:** Chuỗi mới có prefix `{bcrypt}` ngoài payload bcrypt, và thuật toán khác còn dài hơn; cắt chuỗi làm mất dữ liệu cần cho `matches`.

**Câu 10.** `PasswordEncoder` có phải nơi quyết định khóa account, roles hoặc session không?  
**Đáp:** Không. Nó chỉ encode/match/đánh giá upgrade. Provider quản lý auth, `UserDetails` cung cấp flags/authorities và web/security context quyết định phiên đăng nhập; còn account management là tầng nghiệp vụ.

## 15. Tài liệu tham khảo chính thức

- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): lịch sử password hashing, format `{id}encodedPassword`, encode/matches và nâng cấp.
- [Spring Security 6.5.11 – PasswordEncoderFactories Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/factory/PasswordEncoderFactories.html): `createDelegatingPasswordEncoder()`, ID bcrypt mặc định và toàn bộ default mappings.
- [Spring Security 6.5.11 – DelegatingPasswordEncoder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): constructors, ID parsing, `setDefaultPasswordEncoderForMatches` và `upgradeEncoding`.
- [Spring Security 6.5.11 – PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches` và `upgradeEncoding`.
- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): phối hợp `UserDetailsService` và `PasswordEncoder` trong auth.
- [Spring Security 6.5.11 – UserDetailsPasswordService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html): lưu password hash mới qua `updatePassword`.
- [OWASP – Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): salt, thuật toán băm mật khẩu thích hợp, cost và migration.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): chống brute force, credential stuffing và quản lý tài khoản.

**Ghi nhớ:** **Factory** cung cấp mapping mặc định, **DelegatingPasswordEncoder** dùng `{id}` của hash lưu trong kho để chọn encoder khi match, nhưng dùng `idForEncode` để tạo hash mới. **`upgradeEncoding` chỉ là tín hiệu**: cần biết raw password đã được xác thực, cập nhật storage có điều kiện và giữ policy security đồng nhất ở mọi node. Không dùng cơ chế tương thích legacy như một lý do tiếp tục tạo mật khẩu yếu.
