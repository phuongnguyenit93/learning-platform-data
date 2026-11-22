# DelegatingPasswordEncoder và định dạng lưu có tiền tố thuật toán

## Mục tiêu và bối cảnh

Khi ứng dụng Spring Security Servlet quản lý tài khoản bằng mật khẩu, không nên lưu mật khẩu nguyên văn và không nên tự so sánh chuỗi mật khẩu với giá trị trong cơ sở dữ liệu. Spring Security cung cấp giao diện PasswordEncoder để lưu giá trị đã được băm bằng thuật toán phù hợp, xác minh mật khẩu khi đăng nhập và hỗ trợ nâng cấp cách lưu trữ theo thời gian.

**DelegatingPasswordEncoder** là một triển khai của PasswordEncoder cho phép **một định dạng lưu trữ chứa tiền tố định danh thuật toán**; nhờ đó dữ liệu cũ và mới có thể cùng tồn tại trong giai đoạn chuyển đổi mà ứng dụng vẫn biết bộ mã hóa tương ứng để kiểm tra. Mấu chốt của bài này là hiểu chính xác vai trò của tiền tố, cách chọn encoder khi lưu mới và khi xác minh dữ liệu đã lưu.

Sau khi học, bạn sẽ biết:

- Cú pháp chính xác của chuỗi lưu mật khẩu: **{id}encodedPassword** và ý nghĩa từng phần.
- Sự khác biệt giữa encode(rawPassword), matches(rawPassword, storedPassword) và upgradeEncoding(storedPassword).
- DelegatingPasswordEncoder chọn encoder nào để **mã hóa mới** và encoder nào để **xác minh hash cũ**.
- Vai trò của PasswordEncoderFactories.createDelegatingPasswordEncoder(), idForEncode và bảng ánh xạ id → PasswordEncoder.
- Cách xử lý chuỗi không có tiền tố, tiền tố không được nhận diện, dữ liệu legacy và nguy cơ khi dùng encoder fallback.
- Cách tạo ví dụ Java 17+ có thể chạy với Spring Boot 3.x/Spring Security 6.x và viết kiểm thử có đầu ra xác định.
- Hướng triển khai nâng cấp hash trong quá trình đăng nhập mà không bắt người dùng đổi ngay mật khẩu.

Bối cảnh: Spring Security 6.x trên **Servlet stack**, Java 17+, nhưng cơ chế PasswordEncoder nằm ở tầng quản lý mật khẩu và có thể dùng độc lập với web filter. Những ví dụ có phiên bản Spring Boot được ghi rõ để tránh nhầm cú pháp của các phiên bản cũ.

## 1. PasswordEncoder giải quyết vấn đề gì?

Giao diện cốt lõi (diễn giải chữ ký công khai, không phải mã nguồn thư viện đầy đủ):

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);

    boolean matches(CharSequence rawPassword, String encodedPassword);

    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Ba thao tác có trách nhiệm riêng:

1. **encode(rawPassword)**: tạo giá trị đã mã hóa/băm để **lưu**. Với thuật toán thích hợp cho mật khẩu, một đầu vào có thể cho các output khác nhau do salt ngẫu nhiên.
2. **matches(rawPassword, encodedPassword)**: nhận mật khẩu do người dùng vừa nhập và chuỗi đã lưu. Hàm trả về đúng/sai sau khi sử dụng bộ mã hóa phù hợp; nó **không giải mã hash** để lấy mật khẩu gốc.
3. **upgradeEncoding(encodedPassword)**: cho biết chuỗi đã lưu có cần được chuyển sang cách mã hóa hiện tại hay cấu hình mạnh hơn không. Nó chỉ đưa ra quyết định; **không tự cập nhật database**.

Một bản ghi tài khoản điển hình:

~~~text
username       password_hash
------------   ---------------------------------------------------
alice          {bcrypt}$2a$10$...<các ký tự hash và salt hợp lệ>...
bob            {argon2@SpringSecurity_v5_8}...<giá trị hợp lệ>...
~~~

Các dấu ba chấm chỉ là **minh họa cấu trúc**, không phải hash hợp lệ để đưa trực tiếp vào matches(). Không bao giờ coi ví dụ có dấu ba chấm là giá trị kiểm thử.

**Mục tiêu an toàn:** hash mật khẩu phải được thiết kế cho password storage (có salt và work factor/chi phí tính toán thích hợp), không chỉ SHA-256/MD5 thuần. Mật khẩu đủ mạnh vẫn cần chính sách chống dò, rate limiting, MFA khi phù hợp, truyền tải HTTPS và bảo vệ cơ sở dữ liệu.

## 2. Định dạng {id}encodedPassword

Một chuỗi lưu bởi DelegatingPasswordEncoder thường có dạng:

~~~text
{id}encodedPassword
~~~

Giải thích:

- Dấu ngoặc nhọn mở/đóng là dấu phân cách tiền tố.
- **id** là chuỗi định danh bộ mã hóa được đăng ký trong DelegatingPasswordEncoder, ví dụ bcrypt.
- **encodedPassword** là kết quả trả về từ encoder tương ứng; nó có thể tự bao gồm thông tin salt, cost, tham số thuật toán hoặc phiên bản nội bộ.
- Toàn bộ giá trị **{id}encodedPassword** được lưu trong cột password_hash. Đừng tự bỏ tiền tố trước khi lưu hoặc trước khi gọi matches() của DelegatingPasswordEncoder.

Ví dụ cấu trúc một hash bcrypt:

~~~text
{bcrypt}$2a$10$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
|      | | |  |
|      | | |  +-- payload salt/hash bcrypt (minh họa, không dùng làm hash thật)
|      | | +----- cost của bcrypt trong chuỗi bcrypt (ví dụ 10)
|      | +------- phần bắt đầu của định dạng bcrypt: $2a$
|      +--------- phần chuỗi hash của encoder được chọn
+---------------- tiền tố id do DelegatingPasswordEncoder dùng
~~~

**Tiền tố {bcrypt} không phải salt**, không phải secret và cũng không tự làm hash an toàn hơn. Nó là **metadata định tuyến** để ứng dụng biết triển khai PasswordEncoder nào phải xử lý encodedPassword. Thuật toán bcrypt vẫn nhúng salt/cost riêng vào chuỗi hash bcrypt.

Một vài dạng id bạn có thể bắt gặp (tập id được factory hỗ trợ và phiên bản tham số có thể thay đổi theo Spring Security version):

| Dạng chuỗi lưu | Ý nghĩa |
| --- | --- |
| {bcrypt}$2a$... | Băm bằng BCryptPasswordEncoder; phần bcrypt chứa salt và cost |
| {pbkdf2}... | Chuỗi do encoder PBKDF2 tương ứng với id pbkdf2 tạo |
| {pbkdf2@SpringSecurity_v5_8}... | ID riêng cho một phiên bản cấu hình PBKDF2 |
| {scrypt}... | Chuỗi do SCryptPasswordEncoder tương ứng tạo |
| {argon2@SpringSecurity_v5_8}... | Một ID versioned cho encoder Argon2 |
| {noop}literal-password | Dữ liệu rõ chữ kiểu legacy/test, **không được dùng để lưu mật khẩu mới trong production** |

Không khẳng định mọi factory của mọi phiên bản đều đăng ký chính xác tất cả id trong bảng; cần kiểm tra phiên bản Spring Security và mapping thực tế. Nếu cột database đang lưu {bcrypt}..., bản thân id là “bcrypt”, **không phải** “$2a$” hay “10”. Các thành phần đó nằm trong encodedPassword của bcrypt.

Đừng thêm hai tiền tố cho cùng một bản ghi, ví dụ {bcrypt}{bcrypt}$2a$..., hoặc cắt phần {bcrypt} khi gọi DelegatingPasswordEncoder.matches(). Cả hai đều có thể làm xác minh thất bại.

## 3. Hai hướng đi: encode và matches

Hãy tưởng tượng constructor:

~~~java
DelegatingPasswordEncoder encoder =
        new DelegatingPasswordEncoder("bcrypt", encoders);
~~~

Trong đó encoders là Map<String, PasswordEncoder> được cung cấp trước và có entry với key bcrypt.

### Khi lưu mật khẩu mới: encode

~~~text
rawPassword
     |
DelegatingPasswordEncoder.encode(rawPassword)
     |
idForEncode = "bcrypt"
     |
encoders.get("bcrypt").encode(rawPassword)
     |
trả về "{bcrypt}" + encodedValue
     |
lưu nguyên chuỗi vào password_hash
~~~

**idForEncode** chỉ định encoder chính cho **mật khẩu mới**, không buộc các mật khẩu cũ có id khác phải đổi ngay. Nếu muốn tất cả mật khẩu mới chuyển sang thuật toán/cấu hình mới, bạn thay idForEncode và mapping phù hợp; vẫn có thể duy trì các mapping cũ cho matches().

### Khi đăng nhập: matches

~~~text
mật khẩu vừa nhập + password_hash đã lưu
     |
DelegatingPasswordEncoder.matches(raw, "{id}encoded")
     |
đọc id nằm giữa { và }
     |
tìm encoders.get(id)
     |
delegate.matches(raw, encoded)
     |
true hoặc false
~~~

Ở bước này, **id trong chính bản ghi** quyết định encoder nào được chọn. Đừng tự dùng idForEncode để kiểm tra tất cả dữ liệu cũ, vì điều đó phá tính tương thích với hash đời trước.

Một lần xác minh đúng:

~~~java
String stored = passwordEncoder.encode("ForLocalDemo#2026");
boolean correct = passwordEncoder.matches("ForLocalDemo#2026", stored);
boolean wrong   = passwordEncoder.matches("incorrect", stored);
~~~

Với encoder được cấu hình đúng, correct là true và wrong là false. Không thể đoán trước chuỗi stored đầy đủ vì salt ngẫu nhiên; không so sánh hai lần encode(raw) bằng String.equals() để xác minh password.

## 4. Sử dụng factory có sẵn trong Spring Security

Cách bắt đầu thông dụng:

~~~java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder passwordEncoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Đoạn trích này cần đặt trong class/method Java phù hợp và có thư viện spring-security-crypto trên classpath. Với cấu hình phổ biến của Spring Security 6, factory tạo DelegatingPasswordEncoder, dùng **bcrypt làm idForEncode** và có mapping cho các phương pháp hỗ trợ tương thích dữ liệu cũ. Không diễn giải factory như thể nó tự động quét và đoán loại hash chỉ từ hình dáng chuỗi khi không có prefix: việc xác minh dựa vào id được khai báo.

Ví dụ lưu mới khi dùng factory:

~~~text
raw = "ForLocalDemo#2026"
encoded = passwordEncoder.encode(raw)
encoded thường bắt đầu bằng "{bcrypt}$2a$..." hoặc định dạng bcrypt hợp lệ tương đương
passwordEncoder.matches(raw, encoded) == true
~~~

Các chuỗi trong ví dụ chỉ mô tả kết quả kỳ vọng; hash thực tế thay đổi theo salt. Trong factory mặc định, tập encoder/id có thể gồm các phương pháp cũ vì mục tiêu **đọc và di chuyển dữ liệu legacy**, không có nghĩa những phương pháp như noop, MD5 hoặc SHA-256 thuần được khuyến nghị cho password storage mới.

### Phân biệt factory và bản thân DelegatingPasswordEncoder

- PasswordEncoderFactories.createDelegatingPasswordEncoder() là **phương thức tiện lợi** tạo DelegatingPasswordEncoder với mapping mặc định tương ứng phiên bản.
- DelegatingPasswordEncoder là **cơ chế** phân nhánh dựa vào id và cho phép cấu hình mapping/idForEncode riêng.
- BCryptPasswordEncoder là **một bộ mã hóa cụ thể**, có thể dùng trực tiếp nhưng khi dùng trực tiếp sẽ không tự thêm tiền tố {bcrypt}.
- Nếu bạn dùng trực tiếp BCryptPasswordEncoder để lưu từ trước, DB có thể chỉ có $2a$... mà không có {bcrypt}. Sau khi đổi sang DelegatingPasswordEncoder, dữ liệu đó cần chiến lược migration rõ ràng thay vì giả định nó vẫn khớp.

## 5. Ví dụ Java 17+ hoàn chỉnh, có thể chạy

Để tập trung vào việc băm/xác minh, ta tạo một ứng dụng Spring Boot chạy dạng command-line, **không cần HTTP endpoint**. Nó vẫn dùng đúng PasswordEncoder của Spring Security mà ứng dụng Servlet thường dùng. Phần tích hợp với đăng nhập Servlet sẽ được giải thích sau.

Ví dụ project Spring Boot 3.3.x (Gradle Groovy DSL, Java 17). Có thể dùng một project Spring Boot tương thích khác nếu thay đúng phiên bản plugin/dependency.

### 5.1. Cấu trúc file

~~~text
password-encoder-lab/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (nếu project có Gradle wrapper)
  src/main/java/dev/example/passwords/
    PasswordEncodingDemoApplication.java
  src/test/java/dev/example/passwords/
    PasswordEncodingDemoApplicationTest.java
~~~

Tệp settings.gradle:

~~~groovy
rootProject.name = 'password-encoder-lab'
~~~

Tệp build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp src/main/java/dev/example/passwords/PasswordEncodingDemoApplication.java:

~~~java
package dev.example.passwords;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class PasswordEncodingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordEncodingDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    CommandLineRunner runPasswordDemo(PasswordEncoder encoder) {
        return args -> {
            String raw = "ForLocalDemo#2026";
            String stored = encoder.encode(raw);

            System.out.println("prefix=" + stored.startsWith("{bcrypt}"));
            System.out.println("correct=" + encoder.matches(raw, stored));
            System.out.println("wrong=" + encoder.matches("not-the-password", stored));

            String oldNoopValue = "{noop}legacy-test-only";
            System.out.println("legacyMatches="
                    + encoder.matches("legacy-test-only", oldNoopValue));
            System.out.println("needsUpgrade="
                    + encoder.upgradeEncoding(oldNoopValue));
        };
    }
}
~~~

Đây là **mã Java đầy đủ của một ứng dụng trong project đã có dependency**, không cần tự đăng ký SecurityFilterChain vì bài thực hành tập trung vào PasswordEncoder, không mở HTTP server. String raw và {noop} chỉ là dữ liệu giả cho mục đích học, không được dùng làm password thật.

Chạy trong thư mục có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell có thể dùng:

~~~powershell
./gradlew.bat bootRun
~~~

Các dòng dữ liệu ứng dụng in ra (Spring Boot có thể in thêm banner/log, thứ tự dòng log khác tùy môi trường):

~~~text
prefix=true
correct=true
wrong=false
legacyMatches=true
needsUpgrade=true
~~~

Tại sao xác định được các giá trị trên?

- Factory đang dùng bcrypt cho encode mới, nên chuỗi được lưu bắt đầu bằng {bcrypt}.
- matches() gọi đúng bcrypt encoder với password vừa nhập nên true; mật khẩu sai trả false.
- Factory mặc định cho phép kiểm tra dữ liệu {noop} cũ để hỗ trợ chuyển đổi, nên oldNoopValue được xác minh bằng giá trị nguyên văn.
- upgradeEncoding("{noop}...") là true vì id của bản ghi khác idForEncode hiện tại (bcrypt).

**Không in giá trị stored hoặc raw ra log production**; demo chỉ in kết quả boolean. Nếu chạy nhiều lần, hash bcrypt của cùng raw thường khác nhau do salt ngẫu nhiên, nhưng mỗi hash vẫn xác minh được đúng raw.

### 5.2. Kiểm thử bằng JUnit 5

Tệp src/test/java/dev/example/passwords/PasswordEncodingDemoApplicationTest.java:

~~~java
package dev.example.passwords;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PasswordEncodingDemoApplicationTest {

    @Autowired
    PasswordEncoder encoder;

    @Test
    void newHashesCarryAlgorithmPrefixAndMatchRawPassword() {
        String raw = "ForLocalDemo#2026";
        String stored = encoder.encode(raw);

        assertThat(stored).startsWith("{bcrypt}");
        assertThat(encoder.matches(raw, stored)).isTrue();
        assertThat(encoder.matches("bad-password", stored)).isFalse();
    }

    @Test
    void legacyNoopCanBeReadButRequiresUpgrade() {
        String stored = "{noop}legacy-test-only";

        assertThat(encoder.matches("legacy-test-only", stored)).isTrue();
        assertThat(encoder.upgradeEncoding(stored)).isTrue();
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Bộ test không so sánh với hash bcrypt hard-code, nên không bị lỗi do salt thay đổi. Để kiểm thử kết quả trả về, chỉ khẳng định prefix cùng matches/upgradeEncoding phù hợp. **Sự tồn tại của mapping {noop} trong factory là khả năng tương thích, không phải lời khuyên lưu plain text.**

### 5.3. Tại sao không dùng javac trên một file riêng?

Các class PasswordEncoderFactories, PasswordEncoder, @SpringBootApplication và JUnit đến từ thư viện ngoài JDK. Vì vậy lệnh javac PasswordEncodingDemoApplication.java đơn lẻ sẽ không thành công nếu không cấp đầy đủ classpath. Ví dụ này cần build tool nạp đúng dependency; dùng bootRun/test như trên là cách tái lập minh bạch. Có thể triển khai cùng encoder trong ứng dụng Servlet thật mà không thay đổi hợp đồng encode/matches.

## 6. Tự chọn id và danh sách encoder

Factory mặc định thuận tiện cho hệ thống phổ thông, nhưng dự án có thể muốn work factor cao hơn hoặc xác định chính xác tập thuật toán chấp nhận. DelegatingPasswordEncoder cho phép truyền **idForEncode và Map**.

Ví dụ Bean trong một lớp @Configuration Spring (mã method kèm import, không phải chương trình tự chạy):

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
class PasswordPolicyConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        Map<String, PasswordEncoder> encoders = Map.of(
                "bcrypt", new BCryptPasswordEncoder(12));

        return new DelegatingPasswordEncoder("bcrypt", encoders);
    }
}
~~~

Giải thích:

1. idForEncode là bcrypt; encode mới trả về prefix {bcrypt} rồi nối hash bcrypt.
2. Mỗi lần gọi matches() trên {bcrypt}... sẽ sử dụng BCryptPasswordEncoder.
3. BCryptPasswordEncoder(12) có cost/work factor 12. Cần benchmark theo tài nguyên máy chủ và ngân sách độ trễ xác thực; **không có một cost hợp lý cho mọi hạ tầng**.
4. Mapping này **không hỗ trợ {noop}, {pbkdf2}, {argon2}...**. Nếu DB còn các id đó, chỉ được chuyển sang mapping hẹp khi đã có kế hoạch tương thích và di chuyển.
5. Không khai báo đồng thời PasswordPolicyConfig này và bean PasswordEncoder trong demo ở phần 5 mà không xử lý xung đột bean; đây là **phương án cấu hình thay thế**, không phải đoạn thêm vào ứng dụng hiện có.

Nếu đã có hash {bcrypt} sử dụng cost thấp hơn, bcrypt hash lưu sẵn thông tin cost; BCryptPasswordEncoder(12) vẫn có thể kiểm tra hash bcrypt có cost cũ theo định dạng hợp lệ. Sau khi xác thực thành công, upgradeEncoding có thể chỉ ra bản ghi cần nâng cost. Không phải tự ghi “cost 12” vào tiền tố: ID và thông số cost bên trong bcrypt là hai lớp khác nhau.

### Chuyển từ bcrypt sang một thuật toán/version khác

Tình huống thường gặp là thay encoder dùng cho giá trị mới:

~~~text
Giai đoạn đầu: idForEncode = "bcrypt"  --> lưu {bcrypt}...
Giai đoạn sau: idForEncode = "argon2-v2" --> lưu {argon2-v2}...
                 |
                 +-- mapping vẫn có "bcrypt" để matches hash cũ
                 +-- mapping có "argon2-v2" cho hash mới
~~~

Tên argon2-v2 ở đây **chỉ là ID do ứng dụng tự đặt để minh họa**, không phải id mặc định bảo đảm tồn tại. Để triển khai cần encoder thật có tham số đúng, dependency cần thiết và tài nguyên/bộ nhớ được benchmark; không thay id bằng cách sửa chuỗi prefix của hash cũ. Một hash bcrypt không thể biến thành Argon2 bằng cách đổi {bcrypt} thành {argon2}.

Nếu chỉ thay đổi **tham số cost trong cùng thuật toán**, có thể giữ id hiện tại hoặc dùng id phiên bản rõ ràng, tùy chiến lược tương thích và khả năng upgradeEncoding của delegate. Không có nghĩa mọi PasswordEncoder đều tự biết cần nâng cấp; phải kiểm tra implementation.

## 7. Sai tiền tố, thiếu tiền tố và lỗi khi đọc dữ liệu legacy

### 7.1. Không có prefix

Giả sử database lưu một chuỗi bcrypt trực tiếp:

~~~text
$2a$10$...<hash bcrypt hợp lệ nhưng không có tiền tố Spring Security>...
~~~

Khi sử dụng BCryptPasswordEncoder trực tiếp, chuỗi này có thể được xác minh. Khi chuyển sang DelegatingPasswordEncoder, id trích ra là **null** vì không có {id}, nên mặc định không có encoder nào ứng với null. Thực tế có thể xuất hiện IllegalArgumentException về việc không tìm thấy PasswordEncoder cho id này.

Giải pháp an toàn cần **xác định chắc chắn nguồn gốc dữ liệu**:

- Nếu tất cả record legacy đã xác minh là bcrypt hợp lệ, có thể migration offline bằng cách thêm {bcrypt} cho **chính các record đó** sau khi kiểm tra kỹ và backup.
- Hoặc có cơ chế chuyển đổi có kiểm soát ở tầng repository/đăng nhập, xác định record thiếu prefix thuộc legacy format nào, xác minh rồi lưu giá trị mới qua PasswordEncoder hiện hành.
- Không tự gán {bcrypt} cho các record có thể là MD5, salted SHA-256, plain text hoặc một cấu trúc khác.

Ví dụ SQL diễn tả ý tưởng, **không chạy trực tiếp trên production**:

~~~sql
-- Chỉ sau khi đã chứng minh tập dữ liệu này là bcrypt hợp lệ.
-- Câu lệnh cụ thể phụ thuộc hệ quản trị CSDL và điều kiện chọn record.
UPDATE users
SET password_hash = CONCAT('{bcrypt}', password_hash)
WHERE password_hash LIKE '$2a$%'
  AND password_hash NOT LIKE '{%';
~~~

Câu SQL chỉ là **mô phỏng chiến lược thêm metadata**, không đủ kiểm tra hash hợp lệ và chưa xử lý mọi biến thể bcrypt. Trước migration thực tế phải backup, chạy kiểm chứng trên bản sao, xử lý transaction/batch, rà đúng biến thể '$2a$', '$2b$', '$2y$' mà encoder hiện tại hỗ trợ, và tránh ghi chồng khi nhiều instance đang xác thực.

### 7.2. ID không có trong mapping

Giả sử DB lưu {custom-id}... nhưng bạn chưa đăng ký encoders.get("custom-id"). DelegatingPasswordEncoder mặc định thường ném IllegalArgumentException thay vì âm thầm thử tất cả encoder. Đây là hành vi hợp lý: **không đoán thuật toán từ chuỗi không tin cậy**.

Phân biệt hai tình huống:
- ID được nhận diện, nhưng raw sai → delegate.matches(...) trả false.
- ID không có mapping → lỗi cấu hình/dữ liệu, có thể phát sinh exception; cần xử lý và cảnh báo vận hành thay vì chỉ gán là “user sai password”.

Không đưa thông điệp exception chi tiết về ID, cấu trúc hash hoặc tên account vào response public. Đừng để API báo sai 500 hàng loạt sau khi deploy mà không có kiểm thử tính tương thích database.

### 7.3. setDefaultPasswordEncoderForMatches có nên dùng?

DelegatingPasswordEncoder có API setDefaultPasswordEncoderForMatches(...) cho phép chỉ định fallback trong những trường hợp không có encoder ứng với id đã trích. Tính năng này có thể hỗ trợ giai đoạn migration **khi bạn hiểu chính xác tập dữ liệu legacy**, nhưng có rủi ro:

- Fallback có thể được gọi cả khi id không biết, không chỉ khi bản ghi không có prefix.
- Encoder fallback nhận giá trị đã lưu theo hợp đồng của API; không nên tự giả định nó được gỡ prefix hoặc chuẩn hóa theo cách bạn chưa kiểm thử.
- Chọn NoOpPasswordEncoder làm fallback có thể vô tình biến dữ liệu rõ chữ/định dạng lạ thành thông tin đăng nhập được chấp nhận.
- Fallback “thử mọi encoder” làm mờ nguồn gốc dữ liệu, tăng bề mặt tấn công và che giấu dữ liệu hỏng.

Ưu tiên migration tường minh, giới hạn thời gian, có metrics và test. Nếu vẫn phải dùng fallback, viết test cho **record có id hợp lệ, id thiếu và id lạ**, đồng thời kế hoạch loại bỏ fallback sau migration.

## 8. upgradeEncoding và chiến lược nâng cấp hash khi đăng nhập

Hãy xét ba bản ghi:

~~~text
alice: {bcrypt}<hash bcrypt với cost hiện hành>
bob:   {bcrypt}<hash bcrypt với cost cũ, thấp hơn>
carol: {noop}legacy-password (chỉ mô tả dữ liệu cũ không an toàn)
~~~

Khi idForEncode hiện tại là bcrypt và delegate BCryptPasswordEncoder có cost được cấu hình mới:

- alice có thể không cần upgrade.
- bob có thể cần upgrade vì cấu hình BCryptPasswordEncoder mới nhận thấy cost cũ.
- carol cần upgrade vì id noop khác idForEncode.
- Nếu id hiện tại chuyển sang argon2/version mới, các record {bcrypt} cũ thường được đánh dấu cần upgrade do khác id.

**upgradeEncoding chỉ kiểm tra trạng thái hash**, không xác minh raw password và không sinh hash mới. Quy trình nâng cấp an toàn xảy ra **sau khi password đã được chứng thực**:

~~~text
Người dùng submit rawPassword qua HTTPS
      |
nạp password_hash hiện có từ DB
      |
passwordEncoder.matches(rawPassword, storedHash)
      |
      +-- false: thất bại, không sửa hash
      |
      +-- true: mật khẩu hợp lệ
                |
       passwordEncoder.upgradeEncoding(storedHash)
                |
                +-- false: giữ nguyên
                |
                +-- true: newHash = passwordEncoder.encode(rawPassword)
                            |
                    cập nhật DB có kiểm soát
                            |
                  tiếp tục flow đăng nhập
~~~

Với Spring Security Servlet sử dụng DaoAuthenticationProvider, **UserDetailsPasswordService** là extension point dành cho việc cập nhật password đã mã hóa sau khi xác thực, nếu provider được cấu hình dùng nó. Đối tượng này nhận UserDetails và **một encoded password mới**, cập nhật kho dữ liệu rồi trả lại UserDetails tương ứng. Không nhầm với PasswordEncoder: encoder không tự ghi dữ liệu vào database.

Chữ ký khái quát:

~~~java
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

Tên tham số newPassword trong API **chỉ giá trị mật khẩu đã encode lại do provider chuyển đến**, không phải plaintext mà bạn cần encode thêm lần thứ hai. Nếu lưu giá trị đó bằng cách gọi encode(...) lần nữa, bạn sẽ lưu hash của một hash và người dùng không thể login đúng bằng mật khẩu gốc nữa.

Mã SQL minh họa **compare-and-swap** để chống overwrite do đăng nhập đồng thời:

~~~sql
UPDATE users
SET password_hash = :new_hash
WHERE id = :user_id
  AND password_hash = :old_hash;
~~~

Ở đây :new_hash phải là hash hợp lệ mới, :old_hash là giá trị đã đọc khi kiểm tra. Cần kiểm tra số dòng cập nhật và xử lý retry/đọc lại dữ liệu nếu có concurrent update hoặc người dùng vừa đổi mật khẩu. Logic chính xác phụ thuộc transaction/repository; đoạn SQL không phải implementation UserDetailsPasswordService hoàn chỉnh.

### Vì sao không “đổi tất cả hash” bằng batch nếu không có mật khẩu gốc?

Một hash một chiều không thể chuyển trực tiếp từ bcrypt sang Argon2 bằng cách giải mã. Nếu không có raw password, bạn không thể tính hash của một thuật toán mới dựa trên mật khẩu gốc. Các phương án hợp lệ gồm:

- **Rehash on successful login** vì lúc đó có mật khẩu vừa được người dùng nhập và xác minh.
- **Yêu cầu reset mật khẩu** cho những tài khoản không đăng nhập lâu hoặc đang dùng định dạng không an toàn/không xác minh được.
- **Thêm prefix metadata** cho dữ liệu cũ *nếu thuật toán lưu đã được chứng minh*, vì chỉ bổ sung thông tin định tuyến, không thay hash bên trong.

Không dựa vào việc “hash lại hash cũ” như một migration tương đương: đó không phải giá trị của mật khẩu gốc dưới thuật toán mới.

## 9. Tích hợp PasswordEncoder với Spring Security Servlet

Trong ứng dụng Servlet, các điểm tiếp xúc thông thường:

~~~text
Form Login / HTTP Basic / cơ chế xác thực mật khẩu
         |
AuthenticationManager / AuthenticationProvider
         |
UserDetailsService: nạp user + password_hash
         |
PasswordEncoder.matches(rawCredential, storedHash)
         |
Authentication thành công hoặc thất bại
         |
SecurityContext / authorization / response
~~~

Cấu hình PasswordEncoder làm bean:

~~~java
package dev.example.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
~~~

File này là **mã cấu hình hoàn chỉnh trong project Spring Boot có Spring Security**; khi tích hợp vào app thật cần bảo đảm không có nhiều bean PasswordEncoder xung đột, và provider thực tế dùng bean vừa khai báo.

Một ví dụ tạo tài khoản *minh họa* ở tầng service:

~~~java
String raw = registrationForm.password();
String encoded = passwordEncoder.encode(raw);
userRepository.saveNewUser(registrationForm.username(), encoded);
~~~

Các tên registrationForm và userRepository ở đây là **pseudocode Java theo ngữ cảnh**, không phải file độc lập để biên dịch. Cần thêm validation, transaction, kiểm tra trùng username, bảo vệ dữ liệu cá nhân và chống lạm dụng.

**Quan trọng:** việc dùng PasswordEncoder ở đăng ký và ở đăng nhập phải **tương thích**. Nếu đăng ký dùng bcrypt trực tiếp nhưng login dùng DelegatingPasswordEncoder, storedHash thiếu {bcrypt} và có thể bị lỗi. Nên thống nhất một PasswordEncoder bean/chính sách, kiểm thử toàn bộ luồng register → login → upgrade → login lại.

Trong Spring Security Servlet, handler đăng nhập không nên tự kiểm tra mật khẩu một cách tùy tiện rồi bỏ qua AuthenticationManager/Provider, bởi điều đó có thể phá SecurityContext, sự kiện xác thực, cơ chế khóa tài khoản và các chính sách an toàn liên quan.

## 10. Chọn thuật toán và tham số: tiền tố không thay thế chính sách an toàn

DelegatingPasswordEncoder là cơ chế chọn triển khai; bảo mật thực tế phụ thuộc vào **thuật toán, tham số, dữ liệu đầu vào, cách quản lý tài khoản và hệ thống vận hành**.

| Yếu tố | Điều cần xem xét |
| --- | --- |
| Thuật toán | Ưu tiên thuật toán thiết kế cho mật khẩu như Argon2id, scrypt, bcrypt hoặc PBKDF2 được cấu hình mạnh; chọn theo yêu cầu bảo mật, hỗ trợ và môi trường |
| Salt | Dùng salt ngẫu nhiên do password hashing encoder hỗ trợ; không tự dùng cùng một salt cố định cho tất cả user |
| Work factor | Điều chỉnh cost/iterations/memory dựa trên benchmark latency và khả năng chống tấn công offline |
| Prefix id | Lưu đúng ID tương ứng cấu hình dùng để encode; không sửa id tùy ý |
| Độ dài cột | Đủ chứa {id} và toàn bộ định dạng hash của thuật toán hiện tại/tương lai; không giả định mọi hash dài 60 ký tự |
| Password đầu vào | Chính sách Unicode, độ dài, xử lý input nhất quán; lưu ý bcrypt có giới hạn đầu vào thường được tính theo byte |
| Dò online | Rate limiting, lockout có kiểm soát, MFA, phát hiện bất thường và thông báo chung khi sai credential |
| Dữ liệu nhạy cảm | Không log raw password, encoded hash, token hoặc request body có password; kiểm soát quyền DB, backup và TLS |
| Migration | Test các id còn tồn tại, nâng cấp sau đăng nhập, xử lý account lâu không hoạt động, backup và rollback |

Một BCryptPasswordEncoder với cost lớn đến mức hệ thống bị tấn công DoS qua request login cũng không phải thiết kế tốt. Nâng cost cần đo hiệu năng thực tế, giới hạn số request xác thực và kiểm thử ở tải dự kiến.

**Pepper** (secret chung được quản lý ngoài DB) là lựa chọn bổ sung trong một số thiết kế, nhưng không được tự nối chuỗi pepper vào mật khẩu mà không có quy trình quản lý khóa, chuyển đổi và tương thích. PasswordEncoderFactories không tự quản lý pepper cho ứng dụng.

Đối với bcrypt, các hệ thống cần chú ý giới hạn dữ liệu đầu vào (đặc biệt mật khẩu dài theo UTF-8), hành vi của thư viện và cách chuẩn hóa Unicode. Không tự cắt mật khẩu rồi âm thầm chấp nhận hai chuỗi khác nhau như cùng mật khẩu; đưa ra chính sách và test đầu vào nhất quán.

## 11. Lỗi phổ biến và cách xử lý

### 11.1. Không có {id}, báo “There is no PasswordEncoder mapped for the id null”

**Nguyên nhân:** dữ liệu hash cũ không có tiền tố hoặc dữ liệu lưu bị mất dấu ngoặc nhọn. **Cách xử lý:** phân loại legacy format, thêm prefix chính xác khi có bằng chứng, hoặc tạo luồng migration tường minh. Không tắt kiểm tra mật khẩu.

### 11.2. Đổi idForEncode nhưng xóa mapping cũ

**Nguyên nhân:** tài khoản cũ vẫn có {bcrypt}, nhưng map mới chỉ còn encoder cho id mới. **Cách xử lý:** giữ mapping đọc cho những id còn trong DB, triển khai upgrade-on-login, theo dõi số bản ghi cần migration trước khi xóa encoder cũ.

### 11.3. Lưu BCryptPasswordEncoder.encode() rồi xác minh bằng factory

**Nguyên nhân:** BCryptPasswordEncoder trực tiếp chỉ trả bcrypt hash, không tự thêm {bcrypt}. **Cách xử lý:** dùng DelegatingPasswordEncoder ngay từ lúc lưu mới hoặc migration prefix có kiểm chứng.

### 11.4. So sánh hai hash thay vì dùng matches()

**Sai:** encoder.encode(input).equals(stored). **Đúng:** encoder.matches(input, stored). Thuật toán như bcrypt dùng salt ngẫu nhiên, nên hai lần encode cùng input thường không tạo cùng chuỗi.

### 11.5. Bỏ dấu ngoặc nhọn hoặc ghi sai ID

Các chuỗi bcrypt$2a$..., [bcrypt]$2a$... hoặc {BCrypt}... không tương đương {bcrypt}$2a$... trừ khi tự tạo mapping/format như vậy. ID là khóa chuỗi, phải trùng mapping.

### 11.6. Dùng {noop} cho tài khoản mới vì “dễ debug”

NoOpPasswordEncoder không bảo vệ password. Mapping legacy chỉ để có đường di chuyển trong môi trường đã kiểm soát. Đăng ký người dùng mới phải dùng thuật toán băm mật khẩu thích hợp và không trả hash trong API.

### 11.7. Tự sửa {bcrypt} thành {argon2} trong database

Đổi tiền tố **không biến** hash thành thuật toán khác. Khi được xác thực thành công bằng raw password, hãy encode lại bằng encoder mới và lưu toàn bộ output, không thay một vài ký tự.

### 11.8. Gọi encode() hai lần trên hash mới

Ví dụ tầng service encode raw rồi UserDetailsPasswordService tiếp tục encode hash đã có: bản ghi sẽ chứa hash của hash và user không thể login bằng password gốc. Phân biệt rõ biến tên rawPassword và encodedPassword; test flow cuối đến cuối.

### 11.9. Nhìn tiền tố hợp lệ và kết luận password đã an toàn

{bcrypt} là metadata; cost quá thấp hoặc hệ thống cho phép brute-force online vẫn không an toàn. Cần chính sách work factor, giám sát và rate limiting phù hợp.

### 11.10. Thiếu kiểm thử dữ liệu cũ trước khi deploy

Một migration hoặc update Spring Security có thể thay mapping, dependency hay policy. Hãy tạo bộ fixture gồm hash hợp lệ từ từng id đang dùng, dữ liệu hỏng, id lạ, record không prefix, và test đăng nhập/upgrade; không đợi production phát sinh lỗi người dùng.

## 12. Checklist triển khai production

Trước khi thay đổi cơ chế mã hóa mật khẩu:

1. **Thống kê id đang tồn tại:** đếm số bản ghi theo prefix mà không trích xuất hash sang log hoặc dashboard công khai.
2. **Đối chiếu mapping:** mọi id còn dùng phải có decoder xác minh phù hợp; xác định rõ chính sách xử lý id lạ và record không prefix.
3. **Chọn idForEncode mới:** cấu hình thuật toán, work factor, memory/iterations có benchmark; lưu cả prefix lẫn hash.
4. **Kiểm thử trước khi rollout:** encode mới, matches hash mới, matches dữ liệu cũ, wrong password, upgradeEncoding, user reset password.
5. **Tích hợp với provider thật:** bảo đảm AuthenticationProvider sử dụng PasswordEncoder tương thích; cấu hình UserDetailsPasswordService nếu muốn rehash-on-login.
6. **Ghi database an toàn:** lưu đủ độ dài, transaction thích hợp, concurrency control, backup và khả năng rollback.
7. **Bảo vệ luồng đăng nhập:** HTTPS, rate limit, MFA theo nhu cầu, không log raw/encoded password.
8. **Theo dõi migration:** số bản ghi theo id, tỷ lệ cần upgrade, lỗi id unknown; kiểm soát việc loại bỏ mapping cũ.
9. **Duy trì tính tương thích:** trong giai đoạn triển khai nhiều instance, đảm bảo các instance đều hiểu định dạng mới trước khi instance đầu tiên bắt đầu ghi hash với id mới.
10. **Kiểm soát thay đổi:** test qua các lần cập nhật Spring Security; không mặc định map factory và tham số thuật toán không bao giờ thay đổi.

### Câu hỏi tự luyện

1. Trong {bcrypt}$2a$10$..., phần nào do DelegatingPasswordEncoder sử dụng để chọn encoder? Phần nào là cost do bcrypt sử dụng?
2. Nếu idForEncode là bcrypt và DB có {pbkdf2}..., matches() sử dụng bcrypt hay PBKDF2? Vì sao?
3. Vì sao không nên kiểm tra password bằng cách encode(raw) rồi so sánh chuỗi?
4. Tại sao chuỗi bcrypt không prefix có thể hợp lệ với BCryptPasswordEncoder nhưng lỗi với DelegatingPasswordEncoder?
5. upgradeEncoding(hash) có tự ghi database không? UserDetailsPasswordService đóng vai trò gì?
6. Nếu đổi thuật toán cho mật khẩu mới, có phải đổi prefix của mọi hash cũ không?
7. Vì sao dùng NoOpPasswordEncoder làm fallback vô điều kiện có rủi ro?
8. Cần làm gì để rollout nhiều instance an toàn khi bắt đầu lưu id mới?
9. Tại sao chỉ thay {bcrypt} thành {argon2} không phải migration?
10. Nếu hash cũ đã được xác minh đúng nhưng cost thấp, làm thế nào nâng cấp mà không cần user tự nhập lại password lần thứ hai?

## Kết luận

**DelegatingPasswordEncoder không phải một thuật toán băm mới.** Nó là một cơ chế **lưu kèm id và định tuyến đến PasswordEncoder tương ứng**. Khi encode mới, idForEncode quyết định thuật toán cần dùng; khi matches, **{id} của dữ liệu đã lưu** quyết định thuật toán cần xác minh. Điều này cho phép nâng cấp mật khẩu theo từng lần đăng nhập và giữ khả năng đọc dữ liệu cũ trong quá trình migration.

Luôn lưu nguyên chuỗi **{id}encodedPassword**, dùng **matches()** để xác minh, hiểu đúng **upgradeEncoding()** là tín hiệu chứ không phải thao tác cập nhật DB, và thiết kế migration với kiểm thử, bảo vệ dữ liệu và quản lý phiên bản rõ ràng.