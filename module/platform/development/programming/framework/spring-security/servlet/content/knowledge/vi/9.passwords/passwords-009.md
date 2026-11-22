# Vì sao NoOpPasswordEncoder và mật khẩu rõ chỉ phù hợp tình huống minh họa

## 1. Vấn đề cốt lõi: xác thực đúng không đồng nghĩa lưu mật khẩu an toàn

Trong Spring Security **Servlet**, ứng dụng thường nhận tên đăng nhập và mật khẩu qua giao diện login, rồi so sánh mật khẩu người dùng vừa cung cấp với **giá trị đã lưu** cho tài khoản. Lớp `PasswordEncoder` quyết định cách biểu diễn và kiểm tra giá trị đã lưu đó.

Khi bắt đầu học, đôi khi ta gặp:

```java
PasswordEncoder encoder = NoOpPasswordEncoder.getInstance();
```

Hoặc thấy dữ liệu người dùng có dạng:

```text
username: alice
password: password123
```

Hai ví dụ trên **chỉ giúp mô tả luồng đăng nhập trong môi trường học tập được cô lập**. Chúng **không đủ an toàn để giữ mật khẩu của người dùng thật**. `NoOpPasswordEncoder` có thể khiến chương trình xác thực được, nhưng nó không thực hiện phép băm mật khẩu, không tạo salt, không làm chậm quá trình thử mật khẩu và không bảo vệ dữ liệu khi kho lưu trữ bị đọc trái phép.

Để hiểu ranh giới đó, cần phân biệt:

- **Authentication:** mật khẩu được kiểm tra có khớp với tài khoản không?
- **Password storage:** nếu cơ sở dữ liệu, log, bản sao lưu hoặc file cấu hình bị lộ, người khác có đọc được mật khẩu ban đầu không?
- **Security controls khác:** TLS, chống brute-force, MFA, session và phân quyền vẫn cần thiết ngay cả khi đã băm mật khẩu đúng cách.

**Thông điệp chính:** một hệ thống “login chạy được” với mật khẩu rõ chỉ chứng minh luồng phần mềm hoạt động; nó **không** chứng minh rằng hệ thống được thiết kế để bảo vệ credential.

## 2. NoOpPasswordEncoder thực sự làm gì?

`NoOpPasswordEncoder` triển khai interface `PasswordEncoder` nhưng cố ý **không mã hóa/băm mật khẩu**.

Về mặt hành vi:

- `encode(rawPassword)` trả lại nội dung mật khẩu đầu vào, thay vì tạo một password hash.
- `matches(rawPassword, encodedPassword)` kiểm tra chuỗi mật khẩu đầu vào so với giá trị được cung cấp, mà không có bước xác minh hash có salt và work factor.
- Không tạo salt ngẫu nhiên, không có chi phí tính toán điều chỉnh nhằm làm chậm việc đoán mật khẩu offline.
- Là lựa chọn được giữ chủ yếu để tương thích, minh họa hoặc một số tình huống thử nghiệm đặc biệt; không phải encoder được khuyến nghị cho tài khoản thật.

Ví dụ logic tương đương:

```text
Đầu vào từ form:        demo-only-password
NoOpPasswordEncoder:   demo-only-password
Giá trị lưu vào DB:    demo-only-password

User gửi đúng mật khẩu -> matches(...) = true
User gửi mật khẩu sai  -> matches(...) = false
```

Một bài test chỉ kiểm tra `matches(...)` thành công sẽ **không phát hiện được** việc mật khẩu đã bị lưu nguyên văn. Vì vậy phải kiểm tra cả **hình thức dữ liệu lưu trữ** và thiết kế password encoder.

### “NoOp” không phải mã hóa yếu; nó là không bảo vệ mật khẩu

Tên “encoder” dễ tạo hiểu lầm rằng dữ liệu đã được xử lý an toàn. Nhưng nếu `encode` trả nguyên chuỗi, kẻ đọc được cơ sở dữ liệu cũng đọc được chính mật khẩu có thể mang đi dùng ở nơi khác. Không có bước giải mã; dữ liệu **chưa từng được che giấu**.

Ngay cả mật khẩu chỉ gồm ký tự vô nghĩa cũng không an toàn nếu bị lưu nguyên văn: người dùng có thể tái sử dụng nó ở nhiều dịch vụ; hệ thống không biết chuỗi đó là duy nhất hay đã được dùng ở nơi khác.

## 3. Mật khẩu rõ (plaintext) nguy hiểm ở những điểm nào?

Các vị trí có thể lộ credential không giới hạn ở bảng `users` trong database:

1. **SQL dump, backup và snapshot.** Quản trị viên, công cụ sao lưu hoặc đối tượng truy cập nhầm bucket có thể thấy mọi mật khẩu.
2. **Lỗi phân quyền database.** SQL injection hoặc tài khoản read-only bị lộ vẫn đủ để đọc password plaintext; kẻ tấn công không cần quyền sửa dữ liệu.
3. **Log và monitoring.** Nếu ứng dụng log HTTP body, form parameters, exception hoặc object người dùng, raw password có thể xuất hiện tại nhiều hệ thống ngoài database.
4. **Dữ liệu thử nghiệm hoặc môi trường staging.** Copy database production sang môi trường ít được kiểm soát có thể nhân bản toàn bộ mật khẩu rõ.
5. **Credential reuse và credential stuffing.** Khi một hệ thống lộ mật khẩu, kẻ tấn công có thể thử chính cặp username/password đó trên email, tài chính hoặc dịch vụ khác.
6. **Nhân sự và tích hợp bên thứ ba.** Không cần cố ý xấu: một report, export CSV, dashboard hoặc ticket chứa cột password cũng tạo rủi ro.
7. **Lưu plaintext làm tăng tác động sự cố.** Khi hash được thiết kế tốt, kẻ tấn công phải thử đoán password offline; khi là plaintext, bước đó được bỏ qua hoàn toàn.

Một số ứng dụng còn gửi hoặc ghi mật khẩu vào URL query string, analytics và request logs. **Không dùng URL để truyền mật khẩu**; chỉ gửi credential qua kênh HTTPS thích hợp và tránh giữ bản sao không cần thiết.

> Băm mật khẩu an toàn **không thay thế** quyền truy cập database, encryption at rest, TLS hay bảo vệ backup; nó là một lớp phòng vệ riêng để giảm tác động khi password verifier bị lộ.

## 4. Băm mật khẩu khác mã hóa, Base64 và hash thông thường

| Cách lưu | Có khôi phục trực tiếp mật khẩu không? | Có phù hợp cho password verifier không? |
|---|---|---|
| Plaintext / `NoOpPasswordEncoder` | Có; dữ liệu gốc nằm nguyên ở nơi lưu | **Không** |
| Base64, hex, URL encoding | Có; chỉ là biểu diễn dữ liệu | **Không** |
| Mã hóa đối xứng có thể giải mã | Có nếu có khóa; việc giữ khóa trở thành rủi ro lớn | Thông thường **không** phải thiết kế thích hợp để xác minh password |
| SHA-256/MD5 một lần, không salt | Không có phép giải mã trực tiếp, nhưng đoán offline rất nhanh | **Không**; quá nhanh và dễ bị tấn công từ điển |
| Password hashing chuyên dụng có salt và cost (BCrypt, PBKDF2, scrypt, Argon2id) | Không khôi phục trực tiếp; xác minh bằng hàm kiểm tra | **Có**, khi dùng thuật toán và tham số phù hợp |

**Password hashing** là một quá trình một chiều, có salt ngẫu nhiên và tham số chi phí để người tấn công phải bỏ công tính toán đáng kể cho từng lần thử. Ứng dụng lưu **password verifier** (hash cùng metadata cần thiết), không lưu bản gốc.

Tại login:

```text
Tạo tài khoản:
raw password --password KDF(salt, cost)--> encoded verifier trong DB

Đăng nhập:
raw password từ client
         +
encoded verifier từ DB
         |
PasswordEncoder.matches(raw, verifier)
         |
true / false (không giải mã verifier thành mật khẩu gốc)
```

**Salt** thường **không cần bí mật** và có thể nằm trong encoded hash. Mỗi lần tạo verifier phải có salt thích hợp để hai người có cùng mật khẩu không đương nhiên tạo cùng dữ liệu lưu. **Pepper**, nếu sử dụng, là bí mật bổ sung được quản lý riêng; không thay thế salt/work factor và phải có chiến lược xoay vòng/khôi phục rõ ràng.

BCrypt cố ý tốn công hơn hash thông thường; scrypt và Argon2id còn có khả năng điều chỉnh bộ nhớ nhằm làm các chiến dịch đoán mật khẩu quy mô lớn tốn kém hơn. Lựa chọn thuật toán và tham số cần cân bằng sức chịu tải, chính sách bảo mật và khả năng bảo trì thư viện.

## 5. PasswordEncoder: hợp đồng encode, matches và upgradeEncoding

Trong Spring Security, interface có những thao tác quan trọng:

```java
String encode(CharSequence rawPassword);
boolean matches(CharSequence rawPassword, String encodedPassword);
boolean upgradeEncoding(String encodedPassword);
```

Đây là chữ ký minh họa của interface, không phải chương trình Java độc lập.

- **`encode(raw)`:** dùng khi tạo hoặc thay mật khẩu; đầu ra là chuỗi được lưu vào kho dữ liệu.
- **`matches(raw, stored)`:** dùng trong lần đăng nhập; nhận mật khẩu vừa gửi và verifier đã lưu, kiểm tra chúng tương ứng không. **Không** gọi `encode(raw)` rồi so sánh hai hash mới bằng string equality nếu encoder có salt ngẫu nhiên.
- **`upgradeEncoding(stored)`:** có thể báo verifier cũ cần nâng thuật toán/chi phí theo encoder đang dùng. Hành vi phụ thuộc implementation và cấu hình, không phải mọi encoder đều tự nâng được.

Ví dụ lỗi phổ biến với BCrypt:

```java
// SAI: hai lần encode thường dùng salt khác nhau.
String first = encoder.encode(rawPassword);
String second = encoder.encode(rawPassword);
boolean sameHash = first.equals(second);
```

Biến `sameHash` trong ví dụ có thể là `false` dù mật khẩu ban đầu giống nhau; đây là hành vi **mong muốn** của encoder dùng salt ngẫu nhiên. Kiểm tra đúng là:

```java
String stored = encoder.encode(rawPassword);
boolean accepted = encoder.matches(rawPassword, stored);
```

Hai đoạn chỉ là mảnh Java với các biến đã được khai báo, dùng để nêu nguyên tắc; mã runnable đầy đủ nằm ở mục 8.

## 6. BCryptPasswordEncoder: thay NoOp bằng hash có salt và cost

`BCryptPasswordEncoder` là lựa chọn được Spring Security hỗ trợ rộng rãi để băm mật khẩu. BCrypt sử dụng salt riêng và tham số cost để làm chậm quá trình đoán mật khẩu. Chuỗi encoded chứa thông tin cần thiết để xác minh, bao gồm phiên bản/định dạng BCrypt, cost, salt và dữ liệu kết quả.

Ví dụ Spring Security:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String stored = encoder.encode("demo-only-password");

boolean ok = encoder.matches("demo-only-password", stored);
boolean rejected = encoder.matches("wrong-password", stored);
```

Kỳ vọng `ok == true` và `rejected == false`. **Không có một chuỗi BCrypt output duy nhất** cho cùng mật khẩu, vì salt được tạo ngẫu nhiên. Không hard-code giá trị hash mẫu rồi kỳ vọng hai lần `encode` bằng nhau.

### Điều chỉnh cost cần đo lường

Cost quá thấp khiến đoán offline nhanh hơn; cost quá cao làm login tốn CPU, tăng độ trễ và tạo áp lực lên hệ thống nếu bị tấn công bằng nhiều request. Chọn tham số theo khuyến nghị cập nhật cho thuật toán, đo trên môi trường triển khai thật và có rate limiting/account lockout phù hợp.

**Lưu ý riêng với BCrypt:** một số biến thể BCrypt có giới hạn khoảng **72 byte** đầu vào và cách xử lý chuỗi vượt giới hạn có thể khác theo implementation. Với mật khẩu Unicode dài, số byte không bằng số ký tự; cần đọc tài liệu version cụ thể và thiết kế chính sách đầu vào/migration nhất quán, **không tự cắt/truncate mật khẩu âm thầm**. Khi có yêu cầu bảo vệ tốt hơn cho mật khẩu dài hoặc cần memory-hard KDF, đánh giá Argon2id/scrypt theo khả năng thư viện và môi trường.

### Tại sao không tự viết hash bằng MessageDigest?

Một lời gọi `MessageDigest.getInstance("SHA-256")` nhanh, không tự có salt/cost và không cung cấp quy trình nâng cấp an toàn. Tự ghép vòng lặp hash, salt hay encryption không tương đương password KDF chuyên dụng đã được đánh giá. Dùng `PasswordEncoder` và implementation đã được kiểm thử; đừng thiết kế thuật toán mật khẩu mới chỉ để tránh dependency.

## 7. DelegatingPasswordEncoder: quản lý nhiều thuật toán và nguy cơ còn bản ghi {noop}

Spring Security cung cấp cơ chế delegate theo **ID thuật toán được ghi trong chuỗi verifier**, thường tạo qua:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
```

Đây là mảnh code minh họa. Trong cấu hình phổ biến của Spring Security 6.x, giá trị được mã hóa mới mặc định dùng BCrypt và có tiền tố ID:

```text
{bcrypt}<chuỗi BCrypt gồm cost, salt và verifier>
```

**Dấu ngoặc {bcrypt} là metadata, không phải mật khẩu và không phải salt.** Khi `matches(raw, stored)` chạy, `DelegatingPasswordEncoder` đọc ID trước rồi chọn encoder tương ứng để kiểm tra.

### {noop} không tạo bảo vệ chỉ nhờ có prefix

Một bản ghi như:

```text
{noop}demo-only-password
```

vẫn chứa nguyên văn password sau prefix. `DelegatingPasswordEncoder` có thể nhận dạng ID `noop` và kiểm chứng theo NoOp nếu delegate đó được đăng ký, nhưng không vì vậy mà dữ liệu cũ trở nên an toàn.

**Điểm cần kiểm toán:** dùng `createDelegatingPasswordEncoder()` giúp **bản ghi mới** thường được lưu với `{bcrypt}`, nhưng các bản ghi `{noop}` cũ có thể **tiếp tục được chấp nhận để xác thực** nhằm tương thích. Thay encoder bean không tự biến plaintext đã có trong database thành BCrypt.

| Dữ liệu lưu | Ý nghĩa |
|---|---|
| `demo-only-password` | Plaintext không có ID; Delegating encoder có thể không xác định được thuật toán, gây lỗi ID không hợp lệ nếu không cấu hình fallback |
| `{noop}demo-only-password` | Plaintext với ID NoOp; nếu delegate NoOp được chấp nhận, vẫn kiểm chứng trực tiếp |
| `{bcrypt}$2a$...` hoặc format BCrypt phù hợp | Password verifier dùng BCrypt, không thể coi phần sau prefix là mật khẩu gốc |
| `{argon2}...`, `{pbkdf2}...`, v.v. | Chỉ hợp lệ khi ID và implementation được đăng ký đúng theo version |

**Không đổi mọi password hash thành chuỗi có prefix `{bcrypt}` bằng cách thêm text.** Nếu dữ liệu ban đầu là plaintext, thêm prefix BCrypt không biến nó thành hash; kết quả sẽ không khớp định dạng/verify và không có tác dụng bảo vệ.

Tránh cấu hình một fallback decoder chấp nhận mọi chuỗi không có ID như plaintext chỉ để “sửa nhanh” login. Việc đó có thể mở rộng ranh giới chấp nhận credential thiếu an toàn. Chuyển đổi dữ liệu cũ cần có kế hoạch và bằng chứng chính xác về format trước khi thay đổi.

## 8. Ví dụ Java 17+ chạy được: quan sát NoOp, BCrypt, Delegating

Bộ demo dưới đây dùng **Spring Boot 3.3.5 BOM/parent với Spring Security Crypto**, Java 17 và Maven. Đây là mốc cố định để học; khi xây hệ thống thật, chọn phiên bản Spring Boot/Security còn hỗ trợ và kiểm tra release notes, dependency tree, chính sách mã hóa. Demo **không cần mở server Servlet và không cần kết nối database**: nó kiểm tra lõi PasswordEncoder trước khi tích hợp vào `DaoAuthenticationProvider` hoặc form login.

Cấu trúc:

```text
password-encoder-demo/
├── pom.xml
└── src/
    ├── main/java/example/password/PasswordEncoderDemo.java
    └── test/java/example/password/PasswordEncoderDemoTest.java
```

### 8.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>password-encoder-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

Spring Boot parent cung cấp dependency management cho các module Spring Security; `exec-maven-plugin` cho phép chạy class `main` từ Maven mà không cần tạo một Spring Boot web application.

### 8.2. File Java main

Tạo `src/main/java/example/password/PasswordEncoderDemo.java`:

```java
package example.password;

import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class PasswordEncoderDemo {

    public static void main(String[] args) {
        String raw = "demo-only-password";

        PasswordEncoder noOp = NoOpPasswordEncoder.getInstance();
        String noOpStored = noOp.encode(raw);

        PasswordEncoder modern =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();
        String hash = modern.encode(raw);

        System.out.println("NoOp stores raw: " + raw.equals(noOpStored));
        System.out.println("NoOp accepts raw: " + noOp.matches(raw, noOpStored));
        System.out.println("Modern uses bcrypt: " + hash.startsWith("{bcrypt}"));
        System.out.println("Modern stores raw: " + raw.equals(hash));
        System.out.println("Modern accepts raw: " + modern.matches(raw, hash));
        System.out.println("Modern rejects wrong: " +
            !modern.matches("wrong-password", hash));
        System.out.println("Legacy noop accepted: " +
            modern.matches(raw, "{noop}" + raw));
    }
}
```

Kết quả **stdout của riêng chương trình** dự kiến với bộ dependency minh họa:

```text
NoOp stores raw: true
NoOp accepts raw: true
Modern uses bcrypt: true
Modern stores raw: false
Modern accepts raw: true
Modern rejects wrong: true
Legacy noop accepted: true
```

Điều quan trọng là dòng cuối: Delegating encoder có thể **đọc bản ghi cũ có ID noop**. Vì vậy “ứng dụng đã đổi PasswordEncoder bean sang Delegating” chưa phải bằng chứng mọi mật khẩu đã được băm. Demo cố ý **không in password hash ngẫu nhiên**; nếu in hash, các ký tự cụ thể sẽ khác sau mỗi lần chạy.

Mật khẩu cố định `demo-only-password` chỉ là dữ liệu mẫu, không được dùng làm credential thật. Việc dòng demo in `NoOp stores raw: true` là **cảnh báo**, không phải kỹ thuật được khuyên áp dụng.

### 8.3. Test JUnit

Tạo `src/test/java/example/password/PasswordEncoderDemoTest.java`:

```java
package example.password;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.NoOpPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

class PasswordEncoderDemoTest {

    private static final String RAW = "demo-only-password";

    @Test
    void noOpReallyStoresPlaintext() {
        PasswordEncoder encoder = NoOpPasswordEncoder.getInstance();
        assertEquals(RAW, encoder.encode(RAW));
        assertTrue(encoder.matches(RAW, RAW));
        assertFalse(encoder.matches("wrong-password", RAW));
    }

    @Test
    void delegatingEncoderHashesNewPasswordsAndMatchesThem() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();
        String stored = encoder.encode(RAW);

        assertTrue(stored.startsWith("{bcrypt}"));
        assertNotEquals(RAW, stored);
        assertTrue(encoder.matches(RAW, stored));
        assertFalse(encoder.matches("wrong-password", stored));
    }

    @Test
    void bcryptUsesSaltRatherThanProducingTheSameHashEveryTime() {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        String a = encoder.encode(RAW);
        String b = encoder.encode(RAW);

        assertNotEquals(a, b);
        assertTrue(encoder.matches(RAW, a));
        assertTrue(encoder.matches(RAW, b));
    }

    @Test
    void legacyNoOpPrefixRemainsUnprotected() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();
        String stored = "{noop}" + RAW;

        assertTrue(encoder.matches(RAW, stored));
        assertTrue(stored.contains(RAW));
    }
}
```

Test salt kiểm tra hai lần `encode` thông thường sinh verifier khác nhau; thuật toán salt là ngẫu nhiên nên khả năng trùng salt cực nhỏ nhưng về mặt lý thuyết không tuyệt đối bằng 0. Test chủ yếu nhằm minh họa tính chất salt, không phải bằng chứng toán học của entropy.

Chạy tại thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn -q -DskipTests compile exec:java -Dexec.mainClass=example.password.PasswordEncoderDemo
```

Với JDK 17+, Maven và dependencies tải/resolve thành công, **4 JUnit test dự kiến pass**. Console của Maven có thể xuất hiện log download hoặc plugin tùy môi trường; bảng stdout ở trên là nội dung của `System.out.println`, không phải log đầy đủ của Maven. Đây là mã minh họa để chạy kiểm chứng; kết quả chưa được đo trực tiếp trên máy của người đọc.

Nếu Maven chạy với JDK thấp hơn yêu cầu, plugin/dependency không tải được hoặc classpath thiếu `spring-security-crypto`, cần sửa môi trường trước khi kết luận do PasswordEncoder.

## 9. Tích hợp đúng với Spring Security Servlet

Trong ứng dụng Spring Boot 3.x dùng form login, trách nhiệm thường chia như sau:

```text
POST /login
  |
UsernamePasswordAuthenticationFilter
  |
AuthenticationManager / DaoAuthenticationProvider
  |
UserDetailsService -> tìm user và password verifier đã lưu
  |
PasswordEncoder.matches(raw từ request, verifier trong DB)
  |
Thành công -> SecurityContext/session theo cấu hình
Thất bại   -> authentication failure handler
```

**PasswordEncoder không tự gọi database và không tự thay đổi mật khẩu đã lưu.** Nó chỉ cung cấp phép encode và kiểm chứng. `UserDetailsService` hoặc tầng repository lấy verifier; `AuthenticationProvider` phối hợp kiểm tra. Sau khi đăng nhập thành công, các bước session/context thuộc authentication flow của Spring Security, không phải PasswordEncoder.

Cấu hình kiểu demo cho Servlet:

```java
package example.websecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUserConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build()
        );
    }
}
```

Đây là một class bean hoàn chỉnh **trong project Spring Boot Servlet đã có starter web/security**; không phải một web app độc lập chỉ dùng `javac`. Nó tạo verifier đã băm cho tài khoản in-memory, thay vì lưu raw password như:

```java
// KHÔNG dùng với tài khoản thật:
User.withUsername("alice")
    .password("{noop}demo-only-password")
    .roles("USER")
    .build();
```

Với database thật, tầng đăng ký hoặc đổi mật khẩu cần **`encoder.encode(raw)` trước khi lưu**. Khi login, tầng xác thực sử dụng **`encoder.matches(raw, stored)`**. Một password hash trong DB không phải credential để ứng dụng trả ngược cho client. Đừng cho phép endpoint API xuất trả trường `passwordHash` vì “nó đã được băm”.

Nếu ứng dụng dùng identity provider bên ngoài qua OIDC, thường không cần lưu password user tại ứng dụng. Khi đó xử lý danh tính/token phù hợp với trust boundary thay vì tạo thêm kho password riêng.

## 10. Chuyển đổi hệ thống đã lưu plaintext hoặc {noop}

Thay encoder mới chỉ giúp các lần **encode sau đó** sử dụng thuật toán mới; nó không tự xử lý user records hiện hữu. Một kế hoạch chuyển đổi cần có baseline, kiểm soát dữ liệu, đường lùi và kiểm thử.

### Phương án A — Được phép đọc plaintext trong migration có kiểm soát

Nếu hệ thống cũ còn lưu password plaintext và có một lần migration được phê duyệt, có thể duyệt dữ liệu **trong môi trường đã bảo vệ** để tạo password verifier mới bằng `encoder.encode(raw)`, sau đó ghi cập nhật vào DB theo giao dịch/chế độ kiểm soát phù hợp.

Nhưng phải đặc biệt chú ý: backup, replica, log, snapshot, analytics và các bản export cũ **có thể vẫn chứa plaintext**. Chuyển DB hiện tại sang BCrypt không khiến các bản sao cũ biến mất. Quy trình cần kế hoạch bảo vệ/hủy/rotate dữ liệu cũ, giám sát bất thường và chính sách thông báo hoặc đặt lại mật khẩu nếu có lý do nghi ngờ dữ liệu đã bị lộ.

Không nên in plaintext, chuyển nó qua nhiều hệ thống hay lưu tệp trung gian mới chỉ để migrate. Khi không chắc bản ghi có bị xâm phạm không, bắt buộc phải đánh giá nguy cơ credential reuse và khả năng cần yêu cầu reset password.

### Phương án B — Rehash khi user đăng nhập thành công

Khi không muốn xử lý tất cả password rõ hàng loạt, có thể chấp nhận một cơ chế legacy **rất hẹp**, chỉ cho những tài khoản đã xác minh được format dữ liệu. Sau lần đăng nhập thành công:

1. Lấy credential từ request qua kênh bảo vệ và verifier hiện tại của user.
2. Kiểm chứng bằng cơ chế được phép áp dụng đúng record/version legacy; không tự động coi mọi chuỗi là plaintext.
3. Nếu xác thực thành công, tạo verifier mới bằng password KDF có salt/cost và ghi atomically; không log hoặc giữ raw credential quá thời gian cần thiết.
4. Lần login tiếp theo dùng verifier mới. Quan sát tỷ lệ record còn legacy và có deadline loại bỏ phương thức cũ.
5. Với tài khoản không đăng nhập trong thời gian chuyển đổi, cần chính sách reset bắt buộc hoặc cơ chế khác đã được duyệt.

Đoạn code **pseudocode ở tầng service sau khi đã xác thực thành công**:

```java
if (legacyCredentialVerified && legacyRecord) {
    String strongerVerifier = modernEncoder.encode(rawPassword);
    userRepository.updateVerifierIfUnchanged(
        userId, previouslyStoredVerifier, strongerVerifier
    );
}
```

Các biến và method trong đoạn này là **minh họa về giao dịch nguyên tử/concurrency**, không phải class có thể biên dịch: `legacyCredentialVerified` phải đến từ bước xác thực đáng tin, `updateVerifierIfUnchanged` cần do hệ thống tự cài đặt/kiểm thử, và dữ liệu `rawPassword` chỉ được sử dụng trong ranh giới request đáng tin. Không cho endpoint công khai tự gửi lên “hash mới” để cập nhật credential nếu chưa có flow xác minh và authorization đúng.

### Những điều không được làm khi migration

- **Không** thay mọi record bằng `{noop}` để vượt lỗi đăng nhập.
- **Không** thêm `{bcrypt}` vào đầu plaintext để “chuyển sang BCrypt”.
- **Không** tự động chấp nhận chuỗi không có ID là plaintext cho mọi account nếu không có kiểm kê format và giới hạn chuyển đổi.
- **Không** ghi raw password vào log, ticket hoặc CSV để hỗ trợ migration.
- **Không** xem migration xong nếu backup/replica/old hash và đường xác thực legacy vẫn còn chưa được kiểm soát.
- **Không** tự mở rộng quyền truy cập dữ liệu cũ để tiện quá trình chuyển đổi.

## 11. Khi nào NoOp còn chấp nhận được trong quá trình học?

Có thể sử dụng NoOp để **minh họa rõ tác hại của việc không băm password** trong một unit test hoặc ví dụ chạy độc lập với credential giả, có điều kiện:

- Chỉ sử dụng **chuỗi giả** không có giá trị, không dùng mật khẩu hoặc tài khoản thật.
- Không triển khai bản demo thành service public hoặc kết nối tới kho user production.
- Không lưu dữ liệu nhạy cảm, không copy DB người dùng thật vào môi trường test để thử.
- Có chú thích rằng dữ liệu được `NoOpPasswordEncoder` tạo ra **là plaintext** và không được dùng trong sản phẩm.
- Bài tập không kết thúc ở “NoOp login thành công”, mà so sánh với BCrypt/delegating encoder để hiểu tại sao cần thay.
- Code production hoặc production-like integration tests nên dùng PasswordEncoder thực tế và credential fixture được hash; các flow xác thực/đổi mật khẩu phải được test giống hành vi triển khai.

Mặc dù có thể dùng NoOp ở bài tập cực nhỏ, **có nhiều cách demo an toàn ngay từ đầu** bằng `BCryptPasswordEncoder` hoặc `PasswordEncoderFactories.createDelegatingPasswordEncoder()`. Chi phí triển khai thêm thường rất ít so với nguy cơ copy nhầm code `{noop}` vào ứng dụng thật.

## 12. Password hashing chỉ là một phần của chính sách đăng nhập

Dù cơ sở dữ liệu không lưu plaintext, vẫn phải bảo vệ:

- **HTTPS/TLS:** bảo vệ mật khẩu trên đường truyền. KDF không mã hóa form submission khi client gửi raw password đến server.
- **CSRF:** với website có cookie/session, form login và các thao tác thay đổi trạng thái cần CSRF protection phù hợp; băm password không thay thế CSRF.
- **Rate limiting và chống credential stuffing:** password hash làm chậm đoán offline, không tự ngăn kẻ tấn công gửi hàng triệu request đăng nhập online. Cần kiểm soát tốc độ, phát hiện gian lận và chính sách khóa/tạm hoãn phù hợp.
- **MFA/passkey:** bảo vệ bổ sung trước password reuse, phishing và các tình huống chỉ mật khẩu bị lộ.
- **Phân quyền:** dù xác thực thành công, user không tự có quyền truy cập mọi tài nguyên; kiểm tra ownership/tenant và role/scope đúng.
- **Bảo vệ database, logs, backup, secrets:** phân quyền tối thiểu, encryption phù hợp và quy trình vòng đời dữ liệu.
- **Thay đổi/reset mật khẩu:** bắt buộc kiểm chứng quyền sở hữu tài khoản, hết hạn token reset, chặn replay và kiểm tra phiên còn hiệu lực sau khi reset theo chính sách.
- **Theo dõi và nâng cấp KDF:** đánh giá chi phí encoder theo năng lực hạ tầng, audit các record legacy và chuẩn bị chiến lược đổi thuật toán khi có hướng dẫn bảo mật mới.

Băm mật khẩu không có nghĩa không thể bị đoán. Password yếu như `123456` vẫn dễ bị brute-force offline nếu verifier bị lộ, chỉ tốn thêm thời gian tùy KDF và chi phí. Khuyến khích mật khẩu mạnh hoặc phương thức xác thực chống phishing thay vì xem hash là lớp phòng thủ duy nhất.

## 13. Các lỗi thường gặp khi cấu hình Spring Security

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| Login được dù DB lưu password nguyên văn | Đang dùng `NoOpPasswordEncoder` hoặc `{noop}` | Kiểm toán encoder/record, chuyển sang KDF có salt/cost, loại bỏ legacy theo kế hoạch |
| `There is no PasswordEncoder mapped for the id "null"` hoặc ID lạ | Delegating encoder không nhận dạng format đã lưu | Kiểm tra prefix thực tế; không dùng fallback plaintext toàn cục để che lỗi |
| Mật khẩu đã hash nhưng luôn login thất bại | Encode lại raw rồi so string hash; thuật toán/prefix không tương thích | Dùng `matches(raw, stored)` và đồng bộ encoder theo ID |
| Hai tài khoản cùng password có hash khác nhau | Salt ngẫu nhiên | **Đây thường là hành vi đúng**, không phải lỗi |
| Sau khi đổi encoder, user cũ không login được | Records legacy thiếu prefix hoặc encoder chưa có chiến lược migration | Xác định format, lập kế hoạch rehash/reset |
| CPU login tăng nhiều sau khi nâng work factor | Cost quá cao so với tải thực tế hoặc hệ thống bị brute-force | Benchmark và kiểm soát tốc độ, capacity, monitoring |
| Hash xuất hiện trong API response | Serialize entity trực tiếp, không loại bỏ trường password verifier | DTO tối giản, bảo vệ serialization và kiểm thử response |
| Password lộ trong logs/traces | Log request form body, object user, debug authentication | Redact/sanitize dữ liệu và giới hạn observability |
| Người dùng đổi mật khẩu nhưng session cũ vẫn tồn tại | Chính sách session/logout không xử lý invalidation | Thiết kế reauthentication, revocation/session invalidation |
| Dùng `bcrypt` nhưng chấp nhận record `{noop}` cũ | Delegating encoder vẫn có mapping noop | Audit bản ghi, chặn tạo record mới và chuyển đổi hết legacy |

**Điểm phân biệt cần nhớ:** lỗi 401/redirect login không đủ để chẩn đoán encoder; kiểm tra HTTP method, CSRF, username lookup, PasswordEncoder và nhánh `AuthenticationFailureHandler` theo đúng luồng. Đừng tắt bảo mật để “làm cho bài test xanh”.

## 14. Checklist trước khi đưa hệ thống có password login vào hoạt động

- [ ] Không có password người dùng thật được lưu plaintext hoặc dưới dạng `{noop}` trong database, cấu hình, log, backup chưa được kiểm soát.
- [ ] Password mới được xử lý bằng PasswordEncoder chuyên dụng như BCrypt hoặc password KDF phù hợp chính sách, có salt và cost.
- [ ] Authentication dùng `matches(raw, stored)`; không so hai lần `encode` bằng string equality.
- [ ] Có cơ chế phân loại/migrate record cũ, không duy trì fallback plaintext vô thời hạn.
- [ ] Dữ liệu verifier không được đưa ra API response, analytics, logs hoặc công cụ hỗ trợ.
- [ ] HTTPS, CSRF (theo loại client), rate limiting, MFA và session management được thiết kế độc lập.
- [ ] Đã benchmark cost ở môi trường triển khai, xem xét nguy cơ login DoS và chọn thuật toán hỗ trợ mật khẩu đầu vào phù hợp.
- [ ] Đã kiểm tra các rủi ro credential reuse và thủ tục reset password khi có sự cố dữ liệu.
- [ ] Integration tests bao gồm user đúng/sai mật khẩu, verifier cũ/mới, đổi mật khẩu, session logout và quyền truy cập tài nguyên.
- [ ] Toàn bộ code dùng NoOp trong test có dấu hiệu rõ “demo-only” và không bị copy vào cấu hình production.

### Câu hỏi tự kiểm tra

**1.** `NoOpPasswordEncoder.encode("abc")` trả về gì và vì sao nguy hiểm?  
**Đáp án:** Trả về `"abc"` theo đúng ý nghĩa no-op. Người đọc được verifier cũng biết mật khẩu gốc, không cần crack hash.

**2.** Vì sao không dùng `MessageDigest SHA-256` một lần để lưu password?  
**Đáp án:** Hash thông thường quá nhanh và không tự cung cấp salt/cost phù hợp password storage, khiến việc thử hàng tỷ candidate offline dễ hơn nhiều so với password KDF.

**3.** Hai lần BCrypt encode cùng password cho kết quả khác nhau, `matches` vẫn đúng; có mâu thuẫn không?  
**Đáp án:** Không. Salt ngẫu nhiên khiến verifier khác nhau; hàm matches dùng thông tin trong verifier để tính toán và kiểm tra chính xác.

**4.** Đã dùng `DelegatingPasswordEncoder`, nhưng record DB vẫn có `{noop}alice-password`. Đã an toàn chưa?  
**Đáp án:** Chưa. Dữ liệu sau prefix vẫn là plaintext và có thể còn được delegate NoOp chấp nhận; phải kiểm kê và chuyển đổi/reset password theo chính sách.

**5.** Có thể thêm prefix `{bcrypt}` trước một plaintext password rồi coi là hash BCrypt không?  
**Đáp án:** Không. Prefix chỉ là nhãn thuật toán; cần thật sự chạy password KDF và lưu verifier đúng format.

**6.** Dùng BCrypt có cần HTTPS và chống brute-force online nữa không?  
**Đáp án:** Có. BCrypt bảo vệ khi verifier bị lộ và làm việc đoán offline tốn chi phí hơn; nó không mã hóa đường truyền hoặc chặn tấn công login online.

**Kết luận:** `NoOpPasswordEncoder` và mật khẩu rõ chỉ phù hợp để **nhìn thấy đường đi của dữ liệu giả trong bài minh họa được cô lập**. Ứng dụng phục vụ người dùng thật cần lưu **password verifier tạo bởi KDF chuyên dụng**, kiểm chứng bằng `PasswordEncoder.matches`, quản lý format/upgrade cẩn thận và bảo vệ toàn bộ vòng đời credential — từ form, database, backup đến logs và reset.