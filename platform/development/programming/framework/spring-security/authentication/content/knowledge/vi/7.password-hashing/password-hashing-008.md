# Định dạng {id}encodedPassword và lựa chọn encoder khi xác minh

Một ứng dụng Spring Security có thể đã lưu mật khẩu bằng bcrypt ở phiên bản cũ, sau đó tăng cost hoặc chuyển dần sang thuật toán mạnh hơn. Khi đăng nhập, hệ thống phải biết **chuỗi hash đang lưu thuộc thuật toán nào** để gọi đúng bộ kiểm tra mật khẩu. Nếu chỉ lấy password người dùng vừa nhập rồi băm lại bằng thuật toán hiện tại để so sánh hai chuỗi, việc xác minh có thể sai — nhất là với thuật toán có salt ngẫu nhiên.

Spring Security giải quyết bài toán chọn thuật toán bằng **`DelegatingPasswordEncoder`** và định dạng lưu trữ:

~~~text
{id}encodedPassword
~~~

Trong đó **`{id}`** là nhãn chọn một `PasswordEncoder` đã được cấu hình, còn **`encodedPassword`** là toàn bộ chuỗi hash do encoder tương ứng tạo ra. Khi *tạo hash mới*, `idForEncode` quyết định encoder sẽ dùng; khi *xác minh hash đã lưu*, **ID lấy từ chính hash trong database** quyết định encoder được gọi. Hai quyết định này **không nhất thiết là cùng một thuật toán**.

Bài thuộc nhóm **Băm mật khẩu** của Spring Security Authentication. Nội dung tập trung vào cấu trúc và cách đọc tiền tố `{id}`, phân luồng `encode`/`matches`, cấu hình factory và custom map, lỗi ID không nhận diện được, chuyển đổi dữ liệu legacy, `upgradeEncoding`, tích hợp `DaoAuthenticationProvider`, kiểm thử và một ví dụ Java 17 chạy được.

## 1. Đọc đúng chuỗi {id}encodedPassword

Các ví dụ mang tính minh họa:

~~~text
{bcrypt}$2a$12$.....................................................
{pbkdf2}...dữ liệu PBKDF2 tương ứng...
{scrypt}...dữ liệu scrypt tương ứng...
{argon2}...dữ liệu Argon2 tương ứng...
~~~

Dấu `{` và `}` bao quanh nhãn ID của encoder. Đừng nhầm với `$2a$`, `$2b$`, cost và salt **bên trong định dạng bcrypt**; chúng thuộc phần `encodedPassword` và có nhiệm vụ riêng.

| Thành phần | Ví dụ | Chịu trách nhiệm gì? |
|---|---|---|
| Tiền tố ID | `{bcrypt}` | Chọn encoder đăng ký với khóa `"bcrypt"` |
| Phần encoded | `$2a$12$...` | Hash bcrypt kèm thông tin thuật toán/cost/salt theo định dạng của bcrypt |
| `idForEncode` | `"bcrypt"` | Chọn encoder tạo **hash mới** |
| Map `idToPasswordEncoder` | `"bcrypt" → BCryptPasswordEncoder` | Chỉ những ID đã đăng ký mới có thể được chọn khi xác minh |
| `matches(raw, stored)` | `matches("guess", "{bcrypt}$2a$...")` | Lấy ID, chọn delegate, xác minh mật khẩu ứng viên |

Ví dụ: với `{bcrypt}$2a$12$...`, Spring lấy ID `bcrypt`, tìm encoder bcrypt trong map, **bỏ phần `{bcrypt}`** rồi chuyển phần `$2a$12$...` cho `BCryptPasswordEncoder.matches(...)`. Bcrypt sử dụng thông tin salt và cost có trong hash để kiểm tra raw password vừa nhập.

### 1.1. Tiền tố không phải secret

`{bcrypt}` không phải mật khẩu, salt, pepper, encryption key hay mã định danh của người dùng. Nó là **metadata** để chương trình biết cách đọc hash. Việc tên thuật toán lộ ra không làm hỏng thiết kế password hashing đúng; hệ thống không nên dựa vào việc giấu thuật toán làm biện pháp an toàn.

Trong database, thường nên lưu **nguyên chuỗi** `{id}encodedPassword` ở cột `password_hash`; không tự xóa tiền tố khi trả kết quả `encode`. Salt/cost do từng encoder quản lý theo format của nó, không cần tách thủ công khi lưu bcrypt.

### 1.2. Tiền tố phải nằm ở vị trí nào?

Với cấu hình mặc định của `DelegatingPasswordEncoder`, ký tự đầu tiên phải là `{` và phải tìm được `}` đóng ID. Chẳng hạn:

~~~text
{bcrypt}$2a$12$...   -> id = "bcrypt"
$2a$12$...           -> id = null (không có tiền tố)
 bcrypt}$2a$12$...   -> id = null (thiếu dấu mở đầu)
{unknown}...         -> id = "unknown" nhưng có thể không có encoder
{}...                -> id = "" (không tự đồng nghĩa bcrypt)
~~~

Không nên giả định “nhìn phần hash thấy `$2a$` thì framework chắc chắn tự chọn bcrypt”. **`DelegatingPasswordEncoder` chọn theo `{id}`**, không đoán thuật toán từ nội dung bằng cách thử tất cả encoder. Một số constructor cho phép đổi ký tự delimiters, nhưng định dạng `{id}...` là quy ước phổ biến và nên được chuẩn hóa nhất quán giữa các phiên bản ứng dụng.

## 2. Hai hướng đi độc lập: encode và matches

### 2.1. Encode — tạo một password hash mới

~~~text
rawPassword
    |
    v
DelegatingPasswordEncoder.encode(rawPassword)
    |
    +--> idForEncode = "bcrypt"
    +--> map["bcrypt"] = BCryptPasswordEncoder
    +--> bcrypt.encode(rawPassword)
    |
    v
"{bcrypt}" + bcryptEncodedPassword
~~~

Ví dụ:

~~~java
String raw = "Example!Pass123";
String stored = encoder.encode(raw);
~~~

Đây là **mảnh code**, giả định `encoder` là `DelegatingPasswordEncoder` hoặc `PasswordEncoder` phù hợp. Nếu `idForEncode="bcrypt"` thì đầu ra thường bắt đầu bằng `{bcrypt}`. Phần sau sử dụng salt ngẫu nhiên nên **không cố định** giữa các lần encode.

### 2.2. Matches — kiểm tra password ứng viên với hash đã lưu

~~~text
rawPassword được gửi khi đăng nhập
                       |
storedHash lấy từ DB ---+--> DelegatingPasswordEncoder.matches(raw, stored)
                                  |
                                  +--> Đọc id trong storedHash
                                  +--> Tìm encoder theo id trong map
                                  +--> Bỏ {id} khỏi storedHash
                                  +--> delegate.matches(raw, encodedPart)
                                  |
                                  v
                              true / false
~~~

Nếu row lưu `{pbkdf2}...` và map có `pbkdf2`, Spring dùng PBKDF2 để kiểm tra, **kể cả khi `idForEncode` cho hash mới là `bcrypt`**. Đó là lý do ứng dụng có thể cho các tài khoản được tạo ở nhiều thế hệ thuật toán cùng đăng nhập hợp lệ.

Hợp đồng `PasswordEncoder`:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là **chữ ký API được rút gọn**, không phải file cần tự tạo. `matches` không giải mã hash để lấy raw password gốc. Encoder sử dụng raw password ứng viên, salt và tham số đã lưu để tính/kiểm tra theo đúng thuật toán.

### 2.3. Vì sao không encode lại rồi equals?

Sai:

~~~java
boolean valid = encoder.encode(submittedPassword).equals(storedHash);
~~~

Đúng:

~~~java
boolean valid = encoder.matches(submittedPassword, storedHash);
~~~

Với bcrypt/scrypt/Argon2/PBKDF2 có salt riêng, `encode` tạo chuỗi mới; hai password trùng nhau không bắt buộc tạo hash giống hệt. Và nếu có nhiều thuật toán legacy, `encode` hiện tại có thể dùng **một loại mới**, trong khi hash đang lưu cần được kiểm tra bằng **một loại cũ**.

## 3. Tạo DelegatingPasswordEncoder bằng factory và bằng map tự cấu hình

### 3.1. Factory có mapping mặc định

Spring Security cung cấp:

~~~java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Trong Spring Security 6.x, factory thường chọn **bcrypt làm ID tạo hash mới** và có mapping tương thích để đọc một số định dạng cũ, bên cạnh bcrypt và các thuật toán mới. Mappings/version cụ thể có thể thay đổi qua phiên bản thư viện; nếu dự án cần pin một tập thuật toán được phép, **kiểm tra API theo phiên bản dự án và định nghĩa map cụ thể**.

Ví dụ những tên đã xuất hiện ở các phiên bản Spring Security:

| ID minh họa | Họ encoder | Lưu ý |
|---|---|---|
| `bcrypt` | BCryptPasswordEncoder | Thường là `idForEncode` của factory Spring Security 6 |
| `pbkdf2` | Pbkdf2PasswordEncoder theo mapping được pin | Tham số có thể phụ thuộc phiên bản |
| `pbkdf2@SpringSecurity_v5_8` | Cấu hình PBKDF2 có version trong ID | ID có thể gồm `@`, không phải chỉ chữ cái |
| `scrypt` | SCryptPasswordEncoder | Có mapping nhiều đời tham số |
| `scrypt@SpringSecurity_v5_8` | Bản thông số SCrypt khác | Cho phép kiểm tra hash lịch sử |
| `argon2@SpringSecurity_v5_8` | Argon2PasswordEncoder theo phiên bản cấu hình | Có thể cần crypto dependency bổ sung |
| `noop` | NoOpPasswordEncoder | **Không băm bảo vệ password**; chỉ liên quan tương thích/test/migration được kiểm soát |
| `MD5`, `SHA-256` hoặc những nhãn cũ | Encoder legacy | Không dùng để tạo password mới trong production |

**Điểm bảo mật:** có decoder để *đọc hash lịch sử* khác với chủ trương cho *ghi hash mới*. Với factory, password mới dùng `idForEncode`; tuy nhiên, việc factory hỗ trợ legacy/noop không phải lời khuyên dùng các thuật toán này. Nếu tổ chức cấm hoàn toàn plaintext/legacy, chọn map có kiểm soát hoặc migration loại bỏ dần và áp dụng security policy phù hợp.

### 3.2. Map tự cấu hình: whitelist rõ ràng

`DelegatingPasswordEncoder` có constructor:

~~~java
DelegatingPasswordEncoder(
        String idForEncode,
        Map<String, PasswordEncoder> idToPasswordEncoder)
~~~

Ví dụ trong một class cấu hình:

~~~java
Map<String, PasswordEncoder> supported = Map.of(
        "bcrypt", new BCryptPasswordEncoder(12),
        "bcrypt10", new BCryptPasswordEncoder(10));

PasswordEncoder encoder =
        new DelegatingPasswordEncoder("bcrypt", supported);
~~~

Đoạn Java **minh họa trong một file đã khai báo imports**, chưa phải chương trình chạy độc lập. Với map này:

- `encode` tạo hash mới gắn `{bcrypt}`, dùng BCrypt cost 12.
- `matches` với `{bcrypt}...` sử dụng encoder cost 12 (bcrypt đọc cost thực tế từ chính stored hash).
- `matches` với `{bcrypt10}...` sử dụng encoder cho alias legacy.
- `{argon2}...` hoặc `{noop}...` **không** được tự nhận nếu ID không có trong map.
- ID `"bcrypt10"` là nhãn do ứng dụng chủ động đặt, không phải built-in bắt buộc của factory.

Đây là cách có thể **giới hạn tập encoder nhận đọc** theo nhu cầu migration. Cần bảo đảm tồn tại mapping cho `idForEncode`; cấu hình không hợp lệ sẽ thất bại sớm thay vì cho phép lưu hash không xác minh được.

### 3.3. Cần giữ ID bất biến về ý nghĩa

Nếu trước đây map `"bcrypt"` trỏ đến bcrypt và nay vô tình đổi `"bcrypt"` sang một decoder khác, toàn bộ hash mang `{bcrypt}` có thể không còn kiểm tra được. **ID là contract lưu trữ**, không chỉ là alias tạm cho Java class.

Khi một thuật toán có nhiều profile tham số không tự đọc được từ hash, bạn có thể dùng các ID có version, ví dụ `pbkdf2@2026`, thay vì gán lại `pbkdf2` sang cấu hình mới và làm hash cũ không tương thích. Cách đặt ID phải nhất quán giữa tất cả node đang chạy cùng database; không tự đổi nhãn trên row nếu phần hash không thay đổi thuật toán tương ứng.

## 4. Lựa chọn encoder khi xác minh: từng bước và các lỗi ID

Hãy xét việc gọi:

~~~java
boolean valid = delegating.matches(raw, storedPasswordHash);
~~~

Diễn tiến logic của `DelegatingPasswordEncoder` là:

1. Đọc `id` từ đầu `storedPasswordHash` theo delimiter đang cấu hình.
2. Tìm `PasswordEncoder` với key bằng `id` trong map.
3. Nếu có delegate, lấy **phần encoded** sau tiền tố rồi gọi `delegate.matches(raw, encodedPart)`.
4. Nếu delegate trả `true`, password ứng viên khớp hash đã lưu; nếu `false`, không khớp.
5. Nếu không có ID hoặc ID không có mapping, mặc định dùng nhánh **`UnmappedIdPasswordEncoder`** và ném **`IllegalArgumentException`**. Điều này thể hiện lỗi định dạng/cấu hình, không phải câu trả lời “password sai” thông thường.
6. Ứng dụng có thể cấu hình một fallback qua `setDefaultPasswordEncoderForMatches`, nhưng việc làm này cần được đánh giá bảo mật, vì nó thay đổi ý nghĩa của dữ liệu không có/không nhận diện được ID.

### 4.1. Các trường hợp cụ thể

| `storedPasswordHash` | ID lấy ra | Nếu map chỉ hỗ trợ `bcrypt` và `bcrypt10` |
|---|---|---|
| `{bcrypt}$2a$12$...` | `bcrypt` | Gọi BCryptPasswordEncoder với encoded part |
| `{bcrypt10}$2a$10$...` | `bcrypt10` | Gọi encoder alias legacy |
| `$2a$10$...` | `null` | Mặc định ném `IllegalArgumentException` |
| `{foo}whatever` | `foo` | Mặc định ném `IllegalArgumentException` |
| `{noop}plain` | `noop` | Mặc định ném lỗi nếu map đã loại `noop` |
| `{bcrypt}not-a-bcrypt-hash` | `bcrypt` | Delegate bcrypt có thể trả `false` hoặc xử lý lỗi format theo implementation |
| `{bcrypt}...` nhưng dùng raw password sai | `bcrypt` | `matches` trả `false` khi encoded hash hợp lệ |

Phân biệt **password không khớp**, **hash hỏng**, **ID thiếu** và **ID không hỗ trợ**. Không vội chuyển tất cả thành “username sai” trong server metrics, nhưng cũng không trả nguyên stacktrace hoặc thuật toán/hash cho client.

### 4.2. Vì sao lỗi “There is no PasswordEncoder mapped for the id null” xuất hiện?

Một database đã lưu bcrypt hash từ khi chưa dùng delegating thường có dạng:

~~~text
$2a$10$... (bcrypt hash không có tiền tố)
~~~

Sau khi chuyển sang `DelegatingPasswordEncoder`, chương trình chờ `{id}...`. Vì chuỗi bắt đầu bằng `$` thay vì `{`, ID được xác định là `null`; mặc định ném `IllegalArgumentException`.

**Không phải bcrypt hash tự nhiên mất hiệu lực.** Vấn đề là lớp routing chưa biết hash thuộc encoder nào. Nếu đã chứng minh row legacy thật sự là bcrypt, bạn có thể thực hiện migration **chỉ thêm tiền tố phù hợp**:

~~~text
Trước: $2a$10$<encoded bcrypt hợp lệ>
Sau  : {bcrypt}$2a$10$<encoded bcrypt hợp lệ>
~~~

Đây là **format minh họa**, không phải hash hợp lệ để copy trực tiếp vào DB. Trong migration thực, giữ nguyên từng byte của encoded part; không tự viết lại salt, cost hay hash. Cần backup, kiểm kê legacy algorithms, kiểm thử `matches` với credential test đã biết và bảo đảm migration idempotent.

### 4.3. Fallback có những rủi ro gì?

Có method:

~~~java
delegating.setDefaultPasswordEncoderForMatches(fallbackEncoder);
~~~

Nó được gọi khi không tìm được encoder theo ID. Một chi tiết API quan trọng: **fallback nhận toàn bộ chuỗi encoded ban đầu, kể cả `{unknown}` nếu có**, không tự động nhận phần sau tiền tố đã được cắt. Vì vậy nếu cần xử lý legacy hash không ID, fallback phải biết chính xác format được phép, từ chối các tiền tố không nhận diện được và không tự chọn NoOp cho mọi input.

Một cấu hình nguy hiểm:

~~~java
delegating.setDefaultPasswordEncoderForMatches(
        NoOpPasswordEncoder.getInstance());
~~~

Đó là **mã phản ví dụ**, không dùng trong production. Nó có nguy cơ biến các giá trị không ID thành chuỗi so sánh plaintext hoặc tạo hành vi xác thực ngoài mong đợi. Nếu phải dùng fallback để quá độ, hãy giới hạn bằng **định dạng legacy đã kiểm chứng** và gỡ bỏ sau migration; việc prefix trực tiếp hash đã biết format thường rõ ràng và an toàn hơn.

### 4.4. Lưu ý với lỗi ở tầng web

`IllegalArgumentException` do ID không mapped không phải `BadCredentialsException`. Trong luồng `DaoAuthenticationProvider`, một số lỗi cấu hình runtime có thể không được chuyển thành lỗi login 401 tiêu chuẩn mà đi qua exception handling khác. Không được dựa vào hành vi HTTP đoán trước; hãy test loại exception và mapping đúng ở phiên bản ứng dụng, ghi sự cố server có correlation ID và trả phản hồi an toàn không tiết lộ hash/schema.

## 5. Ví dụ Java 17 hoàn chỉnh: nhiều ID, đúng delegate, migration và upgrade

Ví dụ này dùng **Spring Security Crypto/Core 6.3.8** và Gradle, không cần Spring Boot hay web server. Mục tiêu là thấy sự khác nhau giữa **encoder tạo hash mới** và **encoder kiểm tra hash lịch sử** bằng những dòng stdout ổn định, không phụ thuộc salt ngẫu nhiên.

Chúng ta chọn:

- `idForEncode = "bcrypt"` với encoder cost 12.
- Encoder thứ hai có ID tùy chỉnh `"bcrypt10"`, dùng để minh họa hash lịch sử tạo bằng bcrypt cost 10.
- Không ánh xạ `noop` hay một thuật toán yếu nào trong map thử nghiệm.
- Một raw password để tạo hash mới và hash cũ. Không in password hoặc hash thật vào console.

### 5.1. Cấu trúc project

~~~text
delegating-password-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/DelegatingPasswordDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'delegating-password-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-crypto:6.3.8'
    implementation 'org.springframework.security:spring-security-core:6.3.8'
}

application {
    mainClass = 'example.DelegatingPasswordDemo'
}
~~~

Trong dự án Spring Boot thực, thông thường dùng dependency management do Boot cung cấp. Ví dụ pin version để đối chiếu API, cần JDK 17+ và Gradle phù hợp; chương trình không chạy endpoint HTTP.

### 5.2. Toàn bộ tệp Java

Tạo `src/main/java/example/DelegatingPasswordDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class DelegatingPasswordDemo {

    public static void main(String[] args) {
        String raw = "Example!Pass123";

        BCryptPasswordEncoder bcrypt12 =
                new BCryptPasswordEncoder(12);
        BCryptPasswordEncoder bcrypt10 =
                new BCryptPasswordEncoder(10);

        Map<String, PasswordEncoder> known = Map.of(
                "bcrypt", bcrypt12,
                "bcrypt10", bcrypt10);

        DelegatingPasswordEncoder delegating =
                new DelegatingPasswordEncoder("bcrypt", known);

        // Encode mới: idForEncode="bcrypt" => {bcrypt} + hash.
        String fresh = delegating.encode(raw);
        System.out.println("new prefix -> "
                + fresh.startsWith("{bcrypt}"));
        System.out.println("new correct -> "
                + delegating.matches(raw, fresh));
        System.out.println("new wrong -> "
                + delegating.matches("wrong-password", fresh));

        // Hash lịch sử tạo riêng, rồi gắn một ID đã đăng ký.
        String oldBcrypt = bcrypt10.encode(raw);
        String taggedLegacy = "{bcrypt10}" + oldBcrypt;

        System.out.println("legacy correct -> "
                + delegating.matches(raw, taggedLegacy));
        System.out.println("legacy needs upgrade -> "
                + delegating.upgradeEncoding(taggedLegacy));
        System.out.println("new needs upgrade -> "
                + delegating.upgradeEncoding(fresh));

        // Không có ID: mặc định không tự đoán từ "$2a$...".
        try {
            delegating.matches(raw, oldBcrypt);
            System.out.println("missing id -> unexpectedly accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("missing id -> "
                    + ex.getClass().getSimpleName());
        }

        // ID lạ: không có encoder trong map.
        try {
            delegating.matches(raw, "{other}" + oldBcrypt);
            System.out.println("unknown id -> unexpectedly accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("unknown id -> "
                    + ex.getClass().getSimpleName());
        }

        // Factory Spring Security 6.3 cũng dùng {bcrypt} cho hash mới.
        PasswordEncoder factory =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();
        String factoryHash = factory.encode(raw);
        System.out.println("factory prefix -> "
                + factoryHash.startsWith("{bcrypt}"));
        System.out.println("factory verifies -> "
                + factory.matches(raw, factoryHash));
    }
}
~~~

Code sử dụng một map với **hai ID** và một `DelegatingPasswordEncoder`. `"bcrypt10"` là nhãn do chúng ta đặt riêng cho demo: nó không yêu cầu format hash bcrypt có tiền tố nào khác; sau `}` là chuỗi bcrypt đầy đủ. Trong cả hai nhánh, bcrypt đọc cost thực tế từ encoded hash.

Không test bằng cách so `fresh.equals(delegating.encode(raw))` vì hai lần encode sử dụng salt ngẫu nhiên, sẽ không có chuỗi cố định. Các dòng stdout kiểm tra ý nghĩa đúng/sai thay vì in hash.

### 5.3. Lệnh chạy và kết quả

Nếu đã tạo Gradle Wrapper tương thích:

~~~bash
./gradlew run
~~~

Nếu chưa có wrapper nhưng có Gradle cài sẵn, dùng `gradle run`. Trên Windows PowerShell với wrapper, lệnh thường là `.\gradlew.bat run`.

Chỉ tính các dòng `System.out.println` của chương trình:

~~~text
new prefix -> true
new correct -> true
new wrong -> false
legacy correct -> true
legacy needs upgrade -> true
new needs upgrade -> false
missing id -> IllegalArgumentException
unknown id -> IllegalArgumentException
factory prefix -> true
factory verifies -> true
~~~

Giải thích:

1. `delegating.encode(raw)` dùng `idForEncode="bcrypt"` và thêm tiền tố `{bcrypt}`.
2. `matches(raw, fresh)` tìm `bcrypt` trong map và kiểm tra đúng; mật khẩu sai trả false.
3. `taggedLegacy` có `{bcrypt10}`. Dù hash mới dùng `bcrypt`, hash cũ vẫn được xác minh bởi delegate có nhãn `bcrypt10`.
4. `upgradeEncoding(taggedLegacy)` trả true vì ID cũ khác `idForEncode`, dù raw password vẫn đúng.
5. `upgradeEncoding(fresh)` trả false với hash bcrypt cost 12 và encoder bcrypt cost 12. Đây là kết quả mong đợi theo implementation được dùng cho demo.
6. Hash thiếu tiền tố và hash có tiền tố `{other}` đều không mapped nên `matches` ném `IllegalArgumentException` theo mặc định, **không** đơn thuần trả false.
7. Factory mặc định trong Spring Security 6.3 tạo hash mới với `{bcrypt}` và tự xác minh được.

**Giới hạn ví dụ:** chưa kết nối `UserDetailsService` hoặc xử lý HTTP, session, registration, database, MFA và quy trình cập nhật password hash. Trọng tâm là **format hash và routing tới đúng encoder**.

### 5.4. Biến thể để kiểm tra mức độ hiểu

**Biến thể A:** đổi `"bcrypt10"` trong map thành `"old-bcrypt"` mà không đổi tiền tố của `taggedLegacy`. Kết quả `legacy correct` không còn xác minh được mà mặc định ném `IllegalArgumentException`, vì ID lưu và ID map không khớp.

**Biến thể B:** đổi `idForEncode` sang `"bcrypt10"` trong constructor. Hash mới nhận `{bcrypt10}`, dù map vẫn có bcrypt cost 12. Đây là ví dụ cho thấy **sự hiện diện của encoder mạnh hơn trong map không tự quyết định thuật toán ghi mới**.

**Biến thể C:** thêm mapping cho một thuật toán khác và tạo một hash có ID tương ứng; nếu đúng encoded part, `matches` có thể xác minh, không cần đổi `idForEncode`. Nên chọn thuật toán được hỗ trợ và phụ thuộc phiên bản trong quá trình test thay vì ngẫu nhiên gắn ID của một thuật toán khác vào hash bcrypt.

## 6. Tích hợp cùng DaoAuthenticationProvider trong Spring Boot

Trong login username/password, `UserDetailsService` lấy `UserDetails` từ database, còn `DaoAuthenticationProvider` gọi `PasswordEncoder.matches(raw, storedHash)` để kiểm tra.

~~~text
HTTP login request
   |
   v
Authentication filter
   |
   v
DaoAuthenticationProvider
   +--> UserDetailsService.loadUserByUsername(username)
   |       -> UserDetails.password = "{bcrypt}..."
   |
   +--> delegatingPasswordEncoder.matches(raw, stored)
           +--> đọc id = "bcrypt"
           +--> map tìm bcrypt
           +--> BCryptPasswordEncoder.matches(raw, encodedPart)
   |
   v
Authentication thành công / AuthenticationException
~~~

Ví dụ bean trong một Spring Boot app có Spring Security 6.3.x:

~~~java
@Configuration
class PasswordSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    AuthenticationProvider daoProvider(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(userDetailsService);
        provider.setPasswordEncoder(passwordEncoder);
        return provider;
    }
}
~~~

Đây là **mảnh cấu hình** trong ứng dụng Spring Boot 3.x, không phải file Java độc lập. Cần imports cho annotation, bean, các class và `UserDetailsService` thực tế. Một số phiên bản mới của `DaoAuthenticationProvider` thay cách khởi tạo khuyến nghị; đối chiếu JavaDoc theo version đang triển khai.

`UserDetailsService` phải trả **nguyên chuỗi hash đã lưu**, bao gồm `{id}` nếu DB đang dùng delegating. Không tự cắt tiền tố trước khi trả `UserDetails`, bởi encoder delegating cần nhìn thấy tiền tố để chọn delegate.

### 6.1. Đăng ký: lấy hash từ chính bean encoder

~~~java
String encoded = passwordEncoder.encode(request.rawPassword());
account.setPasswordHash(encoded);
repository.save(account);
~~~

Đây là **mảnh tích hợp**, giả định đã có request/bean/repository và chính sách validation. Phải lưu nguyên `encoded`, giới hạn quyền truy cập DB, không trả `passwordHash` qua API. Nếu encoder bean là delegating, format có ID cần được bảo toàn qua ORM/DAO/backup/migration.

### 6.2. Đăng nhập: không tự chọn bcrypt cố định

Một anti-pattern:

~~~java
new BCryptPasswordEncoder().matches(raw, user.getPassword());
~~~

Nếu `user.getPassword()` là `{bcrypt}$2a$...`, giá trị không phải raw bcrypt format thuần nên BCryptPasswordEncoder có thể từ chối. Với DB có cả `{pbkdf2}...`, càng không thể dùng bcrypt cho mọi row. Thay vào đó, dùng **cùng delegating policy** cho luồng xác minh, để chọn encoder dựa trên ID đã lưu.

### 6.3. Không nhầm ID encoder với accountId

ID `{bcrypt}` chỉ nói thuật toán hash, không phải identity của người đăng nhập. Chính `UserDetailsService`/repository và namespace login xác định account, còn password encoder xác minh credential của account ấy. Nếu login chọn sai account do username trùng hay tenant scope sai, việc dùng đúng encoder cũng không sửa được lỗi định danh.

## 7. Migration từ dữ liệu legacy: khi nào chỉ thêm ID và khi nào phải rehash?

### 7.1. Chỉ thêm ID khi hash đã được xác định chính xác

Nếu biết chắc cột trước đây lưu **bcrypt hash thuần**, migration có thể thêm `{bcrypt}` vào đầu **nguyên hash**. Đây là **thay đổi metadata format**; không cần raw password và không làm thay đổi password mà người dùng cần nhập.

~~~text
OLD: $2a$10$...  (verified bcrypt)
NEW: {bcrypt}$2a$10$...
~~~

Lưu ý:

- Chỉ áp dụng với rows **chưa có tiền tố** và thật sự thuộc định dạng bcrypt.
- Không prepend `{bcrypt}` vào SHA-256, Base64, plaintext hoặc hash đã gắn ID.
- Không prepend nhiều lần; migration cần idempotent.
- Bảo đảm database column đủ dài, tránh cắt tiền tố hoặc toàn bộ hash.
- Test với các credential thuộc dữ liệu test/fixtures đã được xác nhận, đo tỷ lệ đăng nhập thành công trước/sau.
- Nếu DB có nhiều format, phải phân nhóm nguồn dữ liệu và có adapter/migration cho từng nhóm; **không suy tất cả row không ID là bcrypt**.

### 7.2. Rehash là thay encoded password, không chỉ thêm prefix

Giả sử account A đang dùng `{bcrypt10}...` còn policy mới dùng `{bcrypt}...`. Khi login:

1. `matches(rawPassword, storedHash)` dùng encoder theo ID của hash cũ.
2. Nếu khớp, xem `upgradeEncoding(storedHash)` theo policy.
3. Nếu cần nâng cấp, gọi `encode(rawPassword)` **bằng encoder tạo mới**, nhận một hash mới có prefix mới.
4. Ghi hash mới vào DB dưới một transaction và kiểm soát concurrency.
5. Những lần login tiếp theo sẽ đọc ID mới và xác minh bằng encoder mới.

Không làm `encode(storedHash)` để “nâng cấp” từ hash cũ. Một hash một chiều không chứa plaintext để bạn có thể đổi thuật toán theo cách đó; kết quả sẽ hash **chuỗi hash**, khiến password ban đầu không còn khớp.

### 7.3. upgradeEncoding của DelegatingPasswordEncoder

`DelegatingPasswordEncoder.upgradeEncoding(storedHash)` có thể trả true khi **ID lưu khác ID hiện được dùng để encode**, hoặc khi delegate hiện tại nhận diện thông số hash của chính mình đã lỗi thời. Với BCryptPasswordEncoder, cost thấp hơn cấu hình mục tiêu là một nguyên nhân có thể cần nâng cấp.

Tuy nhiên, đây là **tín hiệu**, không phải thao tác ghi DB. Quy tắc rehash an toàn minh họa:

~~~java
if (encoder.matches(rawPassword, storedHash)
        && encoder.upgradeEncoding(storedHash)) {
    String replacement = encoder.encode(rawPassword);
    // Ghi replacement theo transaction/CAS hoặc optimistic locking.
}
~~~

Đoạn code giả định các biến được khởi tạo, chỉ minh họa flow. **Đừng rehash trước khi matches thành công.** Nếu login và password reset xảy ra đồng thời, một request login cũ có thể ghi đè password mới; dùng điều kiện cập nhật như `WHERE id=? AND password_hash=?` hoặc version column.

### 7.4. Rolling deploy và mapping trên nhiều node

Khi một số node đã ghi hash với ID mới nhưng node cũ chưa biết ID đó, người dùng có thể đăng nhập thành công ở node mới và thất bại ở node cũ. Triển khai an toàn thường theo thứ tự:

1. Đưa khả năng **đọc** ID mới lên mọi node.
2. Xác minh node mới/cũ đều `matches` được hash cũ và mới.
3. Chuyển `idForEncode` để **ghi hash mới**.
4. Theo dõi tỷ lệ lỗi hash format, upgrade và login.
5. Chỉ bỏ mapping legacy sau khi dữ liệu đã được rehash/reset và không còn phụ thuộc.

Phải điều phối giữa các service dùng cùng account database: ứng dụng mobile/backend khác, batch worker, admin UI và login portal đều có thể cần đọc hash format mới. Cần cân nhắc phương án rollback khi một node cũ không đọc được hash mới.

### 7.5. Dữ liệu thật có thể cần bảo mật hơn là "tự động tương thích"

Nếu một hệ thống từng lưu `{noop}plainPassword` hoặc hash nhanh không salt, chỉ giữ encoder yếu trong map để hỗ trợ login vô thời hạn sẽ duy trì rủi ro. Có thể cần reset mật khẩu bắt buộc, tắt login kiểu cũ, thông báo bảo mật, đánh giá sự cố hoặc migration chủ động. **Khả năng tương thích không phải lý do cho phép password mới tiếp tục dùng encoder yếu.**

## 8. Lưu trữ và ràng buộc dữ liệu ở database

Một cột PostgreSQL minh họa:

~~~sql
CREATE TABLE account_credentials (
    account_id    UUID PRIMARY KEY,
    password_hash TEXT NOT NULL,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Cột `TEXT` giúp tránh cắt hash khi thuật toán/prefix thay đổi; có thể dùng kiểu varchar với giới hạn đã phân tích nếu hệ thống cần. **Không** đặt unique constraint trên password_hash: hai user có thể dùng cùng password, salt ngẫu nhiên tạo hash khác nhau; không nên sử dụng hash làm định danh hay để phát hiện trùng password giữa người dùng.

Không dùng một câu SQL `LOWER(password_hash)`, `TRIM(password_hash)` hoặc tự chuyển đổi case trong phần encoded data: phần hash/ID có semantics cụ thể và hash **phân biệt chữ hoa/chữ thường**. Nếu loại bỏ dấu `{`, `}` hoặc escape sai khi export CSV/JSON, cấu trúc định tuyến encoder có thể bị hỏng.

Một migration audit hợp lý có thể thống kê:

~~~text
Tổng số credential rows
Số row gắn {bcrypt}
Số row gắn các ID cũ
Số row thiếu ID
Số row có ID không nằm trong allowlist
Số row null/rỗng/không khớp schema
Số row đã rehash trong từng phiên bản triển khai
~~~

Không ghi nguyên encoded hash hay raw password trong dashboard, logs hoặc báo cáo migration. Chỉ lưu **số lượng**, loại ID đã được duyệt, và mã sự kiện vận hành đủ để xử lý lỗi. Hash vẫn là dữ liệu nhạy cảm có thể bị tấn công offline nếu bị lộ.

## 9. Ranh giới bảo mật: ID có thể được đọc, nhưng không được tin vô điều kiện

Tiền tố `{id}` nằm trong dữ liệu lưu trữ. Mọi ID phải được xử lý qua **một map cho phép**. Đừng thiết kế code như:

~~~java
String className = userSuppliedId;
Class<?> encoderType = Class.forName(className);
// Tạo encoder bất kỳ do client quyết định.
~~~

Đây là **phản ví dụ**, không phải chương trình chạy độc lập. ID dùng cho routing hash không được cho phép chọn lớp Java arbitrary, execute code, hoặc động tạo thuật toán ngoài allowlist.

Không lấy ID encoder trực tiếp từ request login để quyết định raw password được xác minh bằng thuật toán nào. ID đúng là metadata của **hash đã lưu cho account**; attacker không được phép tự ghi password_hash hoặc đổi ID. Tuy nhiên, nếu DB bị attacker sửa, họ có thể thay credential theo nhiều cách; input validation và phân quyền ghi account credential vẫn phải được bảo vệ.

### 9.1. Không dùng {noop} trong dữ liệu production

`{noop}password` có nghĩa encoded part **giống plaintext password** khi map cho phép NoOp. Nó chỉ có mục đích thử nghiệm/tương thích đặc biệt, không phải thuật toán bảo vệ password. Nếu có dữ liệu `{noop}` thật trong DB, đó là nguy cơ lưu plaintext cần được xử lý theo chính sách sự cố/migration, không chỉ để mapping mãi mãi vì “đăng nhập vẫn chạy”.

### 9.2. Không dùng thuật toán bí mật thay password hash mạnh

Đôi khi có ý tưởng đặt ID `{custom}` và dùng thuật toán tự chế. Việc tự tạo crypto scheme có nguy cơ tấn công offline, entropy yếu, salt/cost không đủ và migration không chuẩn. Ưu tiên password KDF đã được kiểm chứng như Argon2id, scrypt, bcrypt hoặc PBKDF2 với tham số được duyệt, tùy yêu cầu hệ thống/compliance.

**Pepper** là bí mật được quản lý tách khỏi database, khác với `{id}` và salt. Nếu bổ sung pepper, phải có key management và versioning rõ; ID encoder có thể giúp lựa chọn profile xác minh, nhưng không đưa pepper plaintext vào ID, hash, code hay logs.

### 9.3. Encoding không giống encryption

`{bcrypt}` prefix không liên quan Base64 decoding để khôi phục password. `PasswordEncoder.matches` kiểm tra ứng viên, không giải mã plaintext. Nếu hệ thống cần khôi phục một API secret để gửi đến bên thứ ba, đó là bài toán **authenticated encryption** và key management riêng. Lưu password người dùng bằng reversible encryption chỉ để “đọc lại khi quên” là sai mục tiêu lưu trữ mật khẩu.

## 10. Xử lý lỗi, quan sát vận hành và các tình huống thường gặp

### 10.1. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `There is no PasswordEncoder mapped for the id "null"` | Hash cũ không có `{id}` | Kiểm kê format, gắn prefix **đúng thuật toán** hoặc migration |
| ID `bcrypt` nhưng `matches` luôn false | Raw sai, hash bị cắt, encoder/data format sai | Dùng test fixture và kiểm tra hash không bị mutate/trim |
| `{unknown}...` gây `IllegalArgumentException` | Map không có ID tương ứng | Xem migration/compatibility; không mở fallback bừa |
| `{bcrypt}{bcrypt}$2a$...` không xác minh | Prefix bị prepend hai lần | Làm migration idempotent, sửa dữ liệu theo quy trình an toàn |
| Hash mới có `{bcrypt}` nhưng node cũ fail | Node cũ chưa có mapping/phiên bản | Deploy read compatibility trước write switch |
| Lỗi login chỉ sau reset password | Reset dùng encoder khác không gắn prefix | Dùng chung policy lưu/đọc encoded password |
| `NoOpPasswordEncoder` làm password login đúng với plaintext | Cấu hình yếu/legacy | Ngừng viết hash yếu, xử lý reset và migration |
| `upgradeEncoding` luôn true cho legacy ID | ID khác `idForEncode` | Nâng cấp sau login đúng, không tự rehash raw chưa xác minh |
| `encode(raw)` rồi equals hash DB cho false | Salt ngẫu nhiên/mapping khác | Dùng `matches(raw,stored)` |
| UserDetails password hash bị null sau login | Credential erasure làm mutate shared object | Tách principal khỏi cache, không tắt erasure tùy tiện |
| Exception map ID sai trả stacktrace 500 | Chưa phân biệt lỗi config và credentials | Log an toàn; xử lý lỗi vận hành và phản hồi public thống nhất |
| Đổi cost bcrypt nhưng hash mới/đang lưu khác nhau | Hash chứa cost riêng; config thay đổi | Kiểm tra `upgradeEncoding` và lộ trình tăng cost |

### 10.2. Quy tắc logging

Không log raw password, hash, token reset hoặc toàn bộ `Authentication` khi gặp lỗi. Có thể log một **error code nội bộ** như `PASSWORD_HASH_ID_UNMAPPED`, request correlation ID, phiên bản ứng dụng và ID đã được chuẩn hóa/allowlisted (nếu policy cho phép), tránh ghi tùy ý cả chuỗi từ DB nếu có dữ liệu nhạy cảm.

Nếu một ID không nhận diện xuất hiện đột ngột sau deploy, đó có thể là lỗi migration, schema corruption hoặc node lệch phiên bản. Không nên lặng lẽ cho đăng nhập thành công; cần fail closed và báo động có thể điều tra.

### 10.3. Account không tồn tại khác hash ID không đọc được

`UserDetailsService.loadUserByUsername` có thể ném `UsernameNotFoundException` khi không có account. `DaoAuthenticationProvider` thường che lỗi người dùng không tồn tại thành `BadCredentialsException`. Nhưng khi account tồn tại và hash có ID không được mapping, đây là vấn đề **credential format/configuration**, không nên mặc định diễn giải thành “account không tồn tại”.

Trong phản hồi public, có thể dùng thông điệp không làm lộ sự tồn tại account; trong observability nội bộ phải tách nguyên nhân để nhóm vận hành không “chữa” một vấn đề cấu hình bằng cách reset nhầm tất cả password.

## 11. Bộ kiểm thử đầy đủ cho encoder routing

Nên kiểm thử ở ít nhất ba lớp: **unit test encoder**, **integration test UserDetailsService/DaoAuthenticationProvider**, và **migration/rolling-deploy test** trên dữ liệu fixture thực tế.

| Kịch bản | Điều cần chứng minh |
|---|---|
| `encode(raw)` theo ID hiện tại | Trả `{idForEncode}...` và `matches(raw, encoded) == true` |
| Raw khác | `matches` trả `false` với hash hợp lệ |
| Hash mang ID legacy có mapping | Delegate legacy được chọn, password đúng vẫn xác minh được |
| Hash mang ID không có mapping | Mặc định ném `IllegalArgumentException` |
| Hash không có tiền tố | Không tự đoán encoder nếu chưa cấu hình fallback |
| Tiền tố không đặt ở đầu/thiếu đóng `}` | Không được tự xem là hash hợp lệ |
| Bcrypt encoded part bị cắt ở DB | Không đăng nhập nhầm, có cảnh báo schema/data |
| Cùng raw được encode hai lần | Cả hai đều matches; không dựa vào equals hai hash |
| `upgradeEncoding` legacy ID | Tín hiệu nâng cấp phù hợp với `idForEncode` |
| `upgradeEncoding` hash mới | Không yêu cầu nâng cấp khi policy hiện tại đã đáp ứng |
| Rehash sau matches đúng | Hash mới dùng thuật toán hiện hành và vẫn xác minh password cũ |
| Rehash và reset xảy ra đồng thời | Không ghi đè password vừa đổi |
| Registration và password reset | Cùng encoded format/prefix theo bean encoder |
| Hai node đọc cùng DB | Cùng allowlist ID, không lệch phiên bản |
| Old node trong rolling deploy | Đọc được ID mới trước khi chuyển sang ghi mới |
| Factory mapping `noop` legacy | Không tạo mới hoặc giữ lâu plaintext trong production |
| DB có nhiều loại hash legacy | Migration phân nhóm đúng, không gắn nhầm prefix |
| Hash có ID cố tình giả mạo | Không chọn encoder ngoài allowlist; không cấp authenticated token |
| HTTP login với hash lỗi format | Không lộ hash, SQL schema hay stacktrace trong response |
| Cache UserDetails | Không làm hỏng encoded part khi xóa credential sau login |

### 11.1. Câu hỏi tự ôn tập

**Câu 1.** `{bcrypt}` trong `{bcrypt}$2a$12$...` dùng để làm gì?  
**Đáp án:** Chọn `PasswordEncoder` theo ID; phần sau là encoded bcrypt hash chứa thông tin thuật toán/cost/salt theo format bcrypt.

**Câu 2.** `idForEncode="bcrypt"` có buộc mọi password cũ dùng bcrypt khi login không?  
**Đáp án:** Không. `matches` chọn delegate theo **ID ở hash đã lưu**; `idForEncode` chỉ quyết định thuật toán **ghi hash mới**.

**Câu 3.** Vì sao legacy bcrypt hash `$2a$...` gây lỗi ID null?  
**Đáp án:** Vì thiếu `{id}` ở đầu. DelegatingPasswordEncoder không tự suy bcrypt từ prefix `$2a$` theo mặc định.

**Câu 4.** Có thể thêm `{bcrypt}` vào một chuỗi SHA-256 để “convert thành bcrypt” không?  
**Đáp án:** Không. Prefix chỉ chọn decoder, không biến đổi dữ liệu bên dưới.

**Câu 5.** Khi nào thêm prefix mà không cần password plaintext là đúng?  
**Đáp án:** Khi đã **xác minh chắc chắn** từng hash legacy thuộc đúng thuật toán và chỉ thiếu metadata ID. Phải giữ nguyên encoded part.

**Câu 6.** Khi nào phải rehash?  
**Đáp án:** Sau khi password ứng viên đã `matches` thành công và policy yêu cầu upgrade; gọi `encode(raw)` bằng encoder mới rồi cập nhật DB an toàn.

**Câu 7.** `setDefaultPasswordEncoderForMatches` có tự loại tiền tố unknown trước khi gọi fallback không?  
**Đáp án:** Không. Fallback nhận cả chuỗi encoded ban đầu, kể cả tiền tố không nhận diện, nên cần thiết kế cẩn thận.

**Câu 8.** `{noop}` có phải cách tốt để hệ thống tạm thời chạy qua lỗi ID null?  
**Đáp án:** Không. Nó so sánh plaintext và có thể khiến hệ thống tiếp tục lưu/cho phép credential yếu; hãy migration theo format đã kiểm kê.

**Câu 9.** Vì sao một node cũ có thể login fail sau khi node mới đổi `idForEncode`?  
**Đáp án:** Node cũ chưa có decoder mapping cho ID mới trong DB. Cần triển khai khả năng đọc trước khi ghi.

## 12. Checklist trước production

- [ ] Chọn thuật toán/password KDF cho hash **mới**, gắn đúng `idForEncode` và benchmark work factor.
- [ ] Kiểm kê các ID/format hash đang nằm trong database, bao gồm row không prefix và ID legacy.
- [ ] Bảo đảm map ID → PasswordEncoder được kiểm soát, versioned và đồng nhất trên các nodes.
- [ ] Lưu toàn bộ `{id}encodedPassword`, không cắt prefix, salt hoặc cost; chọn column đủ dài.
- [ ] Đăng ký, đổi/reset mật khẩu và login sử dụng **cùng chính sách encoder**.
- [ ] Với `matches`, ID lấy từ hash đã lưu, không từ client request.
- [ ] Thiếu/không nhận diện ID thì không tự đoán plaintext, không fallback NoOp theo phản xạ.
- [ ] Nếu migrate hash không prefix, chỉ thêm ID **sau khi đã biết chính xác thuật toán**.
- [ ] Khi nâng cấp, xác minh raw trước, dùng `upgradeEncoding` và CAS/optimistic lock để chống ghi đè reset.
- [ ] Triển khai decoder mới lên mọi node trước khi đổi `idForEncode` cho ghi mới.
- [ ] Có kiểm thử ID cũ/mới, unmapped ID, malformed hash, bcrypt cost và concurrent update.
- [ ] Không lưu `{noop}` plaintext mới, không cho legacy decoder yếu sống lâu nếu không còn cần.
- [ ] Không trả raw password/hash/exception internals ra response hoặc log.
- [ ] Xác minh `DaoAuthenticationProvider` thực sự dùng encoder bean đã chọn và `UserDetailsService` trả đúng stored hash.
- [ ] Theo dõi lỗi ID không mapped, tỷ lệ rehash, login success/failure và sự cố rolling deploy.

**Ghi nhớ:** `{id}encodedPassword` là **hợp đồng định dạng lưu trữ** cho phép Spring Security **đọc nhiều thế hệ hash bằng encoder phù hợp**, còn `idForEncode` chỉ ra **thuật toán ghi mới**. Giữ hai quyết định này tách biệt, cùng với migration an toàn và map được kiểm soát, là nền tảng để thay đổi chính sách băm mật khẩu mà không làm người dùng bị khóa tài khoản.

### Tài liệu chính thức để đối chiếu

- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `{id}encodedPassword`, ví dụ bcrypt/PBKDF2/scrypt, `DelegatingPasswordEncoder` và troubleshooting ID null.
- [Spring Security — DelegatingPasswordEncoder JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html): constructor, `idForEncode`, routing `matches`, fallback và `upgradeEncoding`.
- [Spring Security — PasswordEncoderFactories JavaDoc](https://docs.spring.io/spring-security/site/docs/6.4.5/api/org/springframework/security/crypto/factory/PasswordEncoderFactories.html): factory cùng mapping mặc định theo phiên bản.
- [Spring Security — PasswordEncoder JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches` và `upgradeEncoding`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): provider xác minh raw password dựa trên stored hash từ `UserDetailsService`.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): chọn password KDF, salt/work factor, migration và rủi ro legacy hash.
