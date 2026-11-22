# DelegatingPasswordEncoder, tiền tố thuật toán và nâng cấp hàm băm

## 1. Bối cảnh: vì sao một ứng dụng cần nhiều thuật toán băm mật khẩu?

Trong Spring Security Reactive (Spring WebFlux), quá trình đăng nhập bằng username/password phải kiểm tra mật khẩu do người dùng gửi với **giá trị băm một chiều** đã lưu. Dữ liệu tài khoản có thể tồn tại nhiều năm, trong khi khuyến nghị về hàm băm, tham số tính toán và yêu cầu bảo mật thay đổi theo thời gian.

Ví dụ, cùng một hệ thống có thể chứa:
- Một nhóm tài khoản cũ có chuỗi BCrypt không ghi tiền tố Spring Security.
- Một nhóm tài khoản được lưu theo định dạng có tiền tố `{bcrypt}`.
- Các hash PBKDF2, scrypt hoặc Argon2 được tạo bởi các cấu hình trước đó.
- Một số tài khoản demo/legacy từng lưu `{noop}` (mật khẩu dạng rõ; **không an toàn**, chỉ cần nhận diện để loại bỏ).

Nếu toàn bộ hệ thống chỉ dùng một `BCryptPasswordEncoder` đơn lẻ và đổi thuật toán đột ngột, ứng dụng dễ làm người dùng cũ không thể đăng nhập. Ngược lại, nếu tiếp tục tạo hash mới bằng thuật toán yếu để tương thích, hệ thống không cải thiện độ an toàn.

**`DelegatingPasswordEncoder`** cho phép **tạo hash mới bằng thuật toán được chọn** trong khi **xác minh hash cũ bằng đúng thuật toán đã sử dụng**, nhờ tiền tố định danh ở đầu chuỗi được lưu. Nó còn có API `upgradeEncoding` để cho biết một hash nên được tạo lại theo cấu hình hiện tại.

> **Nguyên tắc bảo mật:** tiền tố chỉ là metadata chọn bộ kiểm tra; nó không chứng minh tính hợp lệ, không mã hóa plaintext và không tự thay mật khẩu đã lưu. Quy trình nâng cấp chỉ diễn ra khi có raw password hợp lệ (thường sau xác thực thành công) và có cơ chế ghi dữ liệu bền vững.

Mục tiêu bài học:
1. Hiểu chính xác định dạng `{id}encodedPassword`.
2. Phân biệt `encode`, `matches`, `upgradeEncoding` và việc **ghi hash mới vào kho người dùng**.
3. Sử dụng `PasswordEncoderFactories.createDelegatingPasswordEncoder()` hoặc mapping tùy biến có kiểm soát.
4. Thiết kế migration từ hash không có tiền tố, hash yếu hoặc tham số cũ mà không làm mất khả năng đăng nhập.
5. Liên hệ việc nâng cấp với `UserDetailsRepositoryReactiveAuthenticationManager` và `ReactiveUserDetailsPasswordService`.
6. Chạy ví dụ Java 17+ có mã nguồn và kiểm thử, đồng thời nhận diện lỗi bảo mật phổ biến.

## 2. PasswordEncoder là hợp đồng gì?

Spring Security cung cấp interface:

~~~java
// Chữ ký API minh họa; không phải chương trình Java độc lập.
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Ba ý nghĩa khác nhau:

| Phương thức | Đầu vào | Kết quả | Không làm |
| --- | --- | --- | --- |
| `encode(raw)` | Mật khẩu gốc, ví dụ lúc đăng ký/đổi mật khẩu | Một chuỗi băm phù hợp với encoder hiện tại | Không tự lưu database |
| `matches(raw, stored)` | Mật khẩu người dùng vừa nhập và chuỗi **đã lưu** | `true` hoặc `false` khi có hash/thuật toán hợp lệ | Không giải mã hash để lấy lại mật khẩu |
| `upgradeEncoding(stored)` | Chuỗi **đã lưu** | `true` nếu policy cho rằng nên tạo hash mới | Không tự băm lại và không cập nhật người dùng |

Một hash mật khẩu hiện đại là cơ chế **một chiều và có chi phí tính toán**. Hệ thống không được “decrypt” hash để biết mật khẩu; khi đăng nhập, nó dùng `matches` để kiểm tra mật khẩu được trình bày với hash đã lưu. Khi muốn nâng cấp, phải có raw password đã được kiểm tra đúng rồi mới có thể `encode(raw)` lại theo thuật toán/chính sách mới.

Một password hash khác với **token JWT**, refresh token hay dữ liệu phải mã hóa để giải mã. DelegatingPasswordEncoder chỉ giải quyết lớp kiểm tra **mật khẩu**; nó không tự xác minh Bearer JWT và không thay thế các bước authentication/authorization của WebFlux.

## 3. Định dạng lưu trữ: `{id}encodedPassword`

Dạng tổng quát của `DelegatingPasswordEncoder`:

~~~text
{id}encodedPassword
 ^^^ ^^^^^^^^^^^^^^^
  |        |
  |        +-- kết quả encode của PasswordEncoder tương ứng
  +----------- định danh dùng để tra bộ giải mã/bộ so khớp
~~~

Ví dụ minh họa:

~~~text
{bcrypt}$2a$10$dXJ3SW6G7P50lGmMkkmwe.20cQQubK3.HZWzG3YB1tlRy.fqvM/BG
{noop}temporary-demo-only
{pbkdf2@SpringSecurity_v5_8}<encoded-value-thuc-te>
{argon2@SpringSecurity_v5_8}<encoded-value-thuc-te>
~~~

Hai dòng cuối chỉ cho thấy **hình dạng tiền tố**; phần `<encoded-value-thuc-te>` là chỗ mô tả, **không phải hash hợp lệ để dùng đăng nhập**. `{noop}` là dạng rõ, không nên tồn tại trong kho production.

Các thành phần:
- `{` và `}` phân định một `id` ở đầu chuỗi.
- `id` không nhất thiết là tên thuật toán thuần túy; có thể gồm nhãn phiên bản policy như `pbkdf2@SpringSecurity_v5_8`.
- Phần sau ngoặc đóng được chuyển tới encoder đã map với `id`.
- Các format như BCrypt chứa thông tin cost/salt của chính thuật toán ở **bên trong** phần `encodedPassword`. `{bcrypt}` không phải salt và không đại diện cho cost.
- Mặc định Spring Security dùng dấu ngoặc nhọn; API `DelegatingPasswordEncoder` có constructor cho phép thay prefix/suffix khi cần, nhưng không nên tự thay nếu không có yêu cầu tương thích rõ ràng.

### 3.1. Quy trình `encode`

Nếu `idForEncode = "bcrypt"`, `encode("correct-password")` thực hiện:
1. Tra mapping `bcrypt -> BCryptPasswordEncoder`.
2. Gọi BCrypt để tạo hash mới, có salt ngẫu nhiên.
3. Ghép `{bcrypt}` vào đầu chuỗi trả về.

Hai lần `encode` cùng một mật khẩu thường tạo **hash khác nhau** do salt ngẫu nhiên. Vì vậy, không kiểm tra bằng `newHash.equals(oldHash)`; phải gọi `matches(raw, oldHash)`.

### 3.2. Quy trình `matches`

Với dữ liệu `{bcrypt}...`, bộ delegating:
1. Tách `id = bcrypt`.
2. Chọn `BCryptPasswordEncoder`.
3. Chuyển phần hash phía sau tiền tố vào `BCryptPasswordEncoder.matches(raw, hash)`.
4. Trả kết quả xác minh mật khẩu; nó không cần biết plaintext ban đầu của hash.

Với `{pbkdf2@SpringSecurity_v5_8}...`, mapping phải có đúng ID này. Không được giả định ID `pbkdf2` và `pbkdf2@SpringSecurity_v5_8` dùng tham số giống nhau.

### 3.3. Khi ID thiếu hoặc không được đăng ký

Nếu một hash không có `{id}`, hoặc có `{unknown}...`, mặc định `DelegatingPasswordEncoder.matches` **ném `IllegalArgumentException`** vì không tìm thấy encoder phù hợp, chứ không phải luôn trả `false`. Có API `setDefaultPasswordEncoderForMatches` để thay behavior, nhưng cấu hình sai có thể tạo đường xác thực yếu hoặc nhầm lẫn scheme.

Cần phân biệt:
- **Sai mật khẩu với hash hợp lệ:** thường `matches` trả `false`.
- **Hash không xác định ID:** có thể `IllegalArgumentException` theo mặc định.
- **Hash lỗi định dạng:** cách xử lý tùy encoder cụ thể; cần giám sát lỗi dữ liệu và xử lý an toàn, không suy đoán mọi trường hợp đều đơn giản là `false`.

Việc API ném lỗi là tín hiệu **dữ liệu hoặc mapping chưa đúng**, không phải yêu cầu cho phép login fallback.

## 4. `PasswordEncoderFactories.createDelegatingPasswordEncoder()`

Cách tạo một encoder có mapping Spring Security khuyến nghị:

~~~java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Trong Spring Security 6.x tương ứng với ví dụ, encoder mặc định **tạo hash mới bằng BCrypt** và thêm `{bcrypt}`. Mapping kiểm tra có nhiều ID để hỗ trợ dữ liệu cũ và các policy khác, gồm các nhóm BCrypt, PBKDF2, scrypt, Argon2 và một số thuật toán legacy. **Mapping khả dụng có thể thay đổi theo phiên bản thư viện**, nên cần kiểm tra Javadoc/version được triển khai thay vì ghi cứng danh sách cho mọi Spring Security.

Sự hiện diện của một ID yếu trong mapping **không phải lời khuyên dùng ID đó cho mật khẩu mới**. Ví dụ `noop`, MD5, SHA-1 có thể xuất hiện vì yêu cầu tương thích dữ liệu cũ, không phải lựa chọn an toàn cho người dùng hiện tại.

### 4.1. Khi nào cần encoder tùy biến?

Khi tổ chức có policy riêng cho thuật toán/chi phí hoặc ID phiên bản, có thể khởi tạo mapping tường minh:

~~~java
// Đoạn Java có thể đặt trong @Bean PasswordEncoder.
Map<String, PasswordEncoder> encoders = new HashMap<>();
encoders.put("bcrypt-v2", new BCryptPasswordEncoder(12));
encoders.put("bcrypt", new BCryptPasswordEncoder());

PasswordEncoder passwordEncoder =
        new DelegatingPasswordEncoder("bcrypt-v2", encoders);
~~~

Đoạn này là snippet cấu hình, cần import `java.util.Map`, `java.util.HashMap`, `PasswordEncoder`, `BCryptPasswordEncoder` và `DelegatingPasswordEncoder`. Chuỗi mới có `{bcrypt-v2}`; các bản ghi `{bcrypt}` cũ vẫn khớp vì mapping cũ còn tồn tại.

**Lưu ý:** một ID tùy chỉnh như `bcrypt-v2` phải được duy trì tương thích trên mọi instance và qua mọi lần deploy. Đổi nội dung của cùng một ID sang thuật toán khác trong khi hash cũ tồn tại là lỗi migration. Nếu thay đổi tham số quan trọng ảnh hưởng khả năng so khớp, nên dùng ID phiên bản mới hoặc bảo đảm encoder có thể đọc format cũ một cách an toàn.

Không đưa `NoOpPasswordEncoder` vào mapping production mới chỉ để tránh lỗi login. Nếu phải hỗ trợ legacy cực kỳ ngắn hạn, cần giới hạn phạm vi, đo lường tiến độ, và có kế hoạch loại bỏ.

## 5. Băm mật khẩu cần thuật toán thích nghi và tham số phù hợp

**BCrypt, PBKDF2, scrypt và Argon2** được thiết kế để tăng chi phí thử đoán mật khẩu so với các digest nhanh như SHA-256/MD5. Tuy nhiên, “dùng BCrypt” không tự đảm bảo toàn bộ hệ thống an toàn; độ dài/entropy mật khẩu, chính sách quản lý tài khoản, rate limiting, MFA, bảo vệ dữ liệu và tham số hàm băm cũng quan trọng.

| Phương án | Đặc điểm | Lưu ý vận hành |
| --- | --- | --- |
| BCrypt | Work factor/cost, salt gắn với hash; phổ biến rộng rãi | Đo và chỉnh cost theo năng lực hạ tầng và SLA |
| PBKDF2 | Nhiều vòng lặp, theo policy/phiên bản | Muốn xác minh đúng phải biết số vòng, PRF, salt, format |
| scrypt | Có chi phí bộ nhớ và thời gian | Điều chỉnh memory/CPU để tránh quá tải |
| Argon2 | Thiết kế memory-hard, nhiều tham số | Đảm bảo dependency và kiểm tra tài nguyên trước deploy |
| MD5/SHA-1/SHA-256 đơn thuần | Digest nhanh | Không dùng trực tiếp làm phương án băm mật khẩu mới |
| `noop` | Mật khẩu dạng rõ | Chỉ nhận diện legacy/demo để loại bỏ; không an toàn |

Một hash BCrypt có thể có phần đầu giống `$2a$10$...`, trong đó `10` là log cost của BCrypt. `{bcrypt}` là tiền tố **Spring Security**, còn `$2a$10$...` thuộc định dạng **BCrypt**. Hai tiền tố phục vụ các mục đích khác nhau.

Đừng chọn cost chỉ theo cảm tính. Hãy benchmark thời gian `encode`/`matches` trên cấu hình production (CPU/memory/traffic/concurrency), đặt giới hạn thời gian và chống brute force. Thông số nên được xem xét lại định kỳ khi phần cứng và yêu cầu bảo mật thay đổi.

## 6. `upgradeEncoding`: phát hiện nhu cầu nâng cấp

Phương thức:

~~~java
boolean shouldUpgrade = encoder.upgradeEncoding(storedHash);
~~~

giúp ứng dụng hỏi: “Nếu người dùng vừa xác thực thành công, hash đã lưu có nên được tạo lại theo policy hiện tại không?”

Đối với `DelegatingPasswordEncoder`:
- Nếu `id` của hash lưu **khác** `idForEncode`, kết quả thường là `true`: dữ liệu lưu ở scheme cũ.
- Nếu `id` trùng `idForEncode`, encoder chuyển việc đánh giá nâng cấp cho implementation tương ứng; ví dụ `BCryptPasswordEncoder` có thể yêu cầu nâng work factor khi hash cũ có cost thấp hơn cấu hình.
- Kết quả trả về là **một quyết định**, không có thao tác ghi database nào được thực hiện.

Dù `upgradeEncoding` trả `true`, không thể băm lại chỉ từ chuỗi hash cũ. Tình huống phổ biến nhất là **nâng cấp lúc login thành công**: raw password vừa được người dùng cung cấp và được xác minh qua `matches`.

### 6.1. Chuỗi sự kiện nâng cấp đúng

~~~text
POST /login (username, rawPassword)
       |
       v
Tải user: storedPassword = {oldId}...
       |
       v
passwordEncoder.matches(rawPassword, storedPassword)
       |
       +--> false: từ chối, KHÔNG cập nhật hash
       |
       +--> true:
                |
                v
        passwordEncoder.upgradeEncoding(storedPassword)
                |
          +-----+-----+
          |           |
        false        true
          |           |
     Giữ hash      encode(rawPassword) bằng policy mới
     hiện tại          |
                      v
             Lưu hash mới một cách an toàn
                      |
                      v
                Hoàn tất login
~~~

Khi nâng cấp:
1. Chỉ chạy sau khi xác minh mật khẩu thành công.
2. Gọi `encode(rawPassword)` để tạo hash mới (salt mới nếu thuật toán hỗ trợ).
3. Ghi hash mới vào kho user bằng thao tác update đáng tin cậy.
4. Không log raw password hoặc hash đầy đủ.
5. Trong hệ thống nhiều request đồng thời, dùng optimistic locking/CAS để không ghi đè thao tác đổi mật khẩu vừa diễn ra.
6. Xử lý lỗi persistence rõ ràng và không tạo trạng thái “login thành công nhưng âm thầm tưởng đã nâng cấp” khi chính sách yêu cầu nâng cấp là bắt buộc.

### 6.2. Nâng cấp không giống đổi mật khẩu

Nâng cấp hàm băm có thể giữ **cùng raw password** nhưng đổi thuật toán/cost/salt. Đổi mật khẩu là thay **bí mật xác thực**; hai hành vi có yêu cầu kiểm tra và audit khác nhau.

Nếu nghi mật khẩu đã lộ hoặc từng lưu dạng rõ, việc băm lại sau login **không xóa** nguy cơ đã bị lộ trước đó. Tổ chức có thể phải yêu cầu người dùng đặt mật khẩu mới, kiểm tra credential compromise và thu hồi phiên/token theo chính sách sự cố.

## 7. Liên hệ với xác thực reactive trong WebFlux

Trong Spring Security Reactive, `UserDetailsRepositoryReactiveAuthenticationManager` có thể dùng một `ReactiveUserDetailsService` để tìm user và `PasswordEncoder` để xác minh credentials. Lớp nền `AbstractUserDetailsReactiveAuthenticationManager` có hai điểm cấu hình quan trọng:

~~~java
manager.setPasswordEncoder(passwordEncoder);
manager.setUserDetailsPasswordService(passwordService);
~~~

`ReactiveUserDetailsPasswordService` khai báo:

~~~java
// Chữ ký rút gọn để đọc; import/interface thực tế do Spring Security cung cấp.
Mono<UserDetails> updatePassword(UserDetails user, String newPassword);
~~~

Khi được cấu hình cho luồng authentication thích hợp, manager có thể thực hiện password upgrade sau xác thực thành công và gọi service để **lưu hash mới**. Không có service ghi cập nhật, chỉ nhìn thấy `upgradeEncoding=true` không tự sửa database.

### 7.1. Các phần cần phân biệt

| Thành phần | Trách nhiệm |
| --- | --- |
| `ServerAuthenticationConverter` hoặc built-in Basic/form login converter | Trích xuất username/password từ request |
| `AuthenticationWebFilter` | Kích hoạt/điều phối xác thực trong security chain |
| `UserDetailsRepositoryReactiveAuthenticationManager` | Tìm người dùng, kiểm tra mật khẩu và các trạng thái account |
| `PasswordEncoder` | Băm, xác minh và đánh giá nâng cấp hash |
| `ReactiveUserDetailsPasswordService` | Cập nhật hash đã được tạo lại vào kho user |
| `ReactiveSecurityContextHolder` | Cung cấp context của request đã xác thực cho downstream |
| Authorization | Kiểm tra role/quyền truy cập sau khi danh tính được xác minh |

**`PasswordEncoder` bản thân là API đồng bộ**: `encode` và `matches` tiêu tốn CPU, dù được gọi trong ứng dụng reactive. Điều này không có nghĩa phải tự gọi `block()` trong controller; manager reactive có cơ chế điều phối việc xác minh phù hợp, và khi tự viết manager cần tránh để phép băm CPU nặng chặn event-loop. Không giải quyết bằng việc tạo `subscribe()` phụ hoặc chạy vô hạn không kiểm soát.

### 7.2. MapReactiveUserDetailsService hỗ trợ bài demo thế nào?

`MapReactiveUserDetailsService` implements cả `ReactiveUserDetailsService` và `ReactiveUserDetailsPasswordService`. Vì vậy, nó có thể phục vụ ví dụ nâng cấp **trong bộ nhớ**. Trong hệ thống thật, thay bằng implementation đọc/ghi kho dữ liệu không chặn, kèm version/CAS, audit và chính sách lỗi.

Đừng suy luận rằng mọi `ReactiveUserDetailsService` tự động có thể cập nhật password: interface tra cứu user và interface thay đổi password **là hai hợp đồng khác nhau**.

## 8. Dự án Java 17+ chạy được: nâng hash từ `{noop}` sang `{bcrypt}`

Đây là demo **console có Reactor và Spring Security Core**, không phải HTTP server. Nó minh họa chính xác phần lõi password upgrade mà một ứng dụng WebFlux sẽ dùng. Việc gọi `block()` chỉ xuất hiện tại **biên `main()` của chương trình console** để đợi kết quả trước khi in; không sao chép cách đó vào WebFlux controller, WebFilter hoặc reactive service.

**Giả lập legacy:** user `learner` có password `{noop}legacy-pass`. Đây là dữ liệu cố ý không an toàn để mô tả di trú, **tuyệt đối không phải cách lưu password khi triển khai thực tế**.

Cấu trúc dự án:

~~~text
password-upgrade-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   └── PasswordUpgradeDemo.java
    └── test/java/demo/
        └── PasswordUpgradeTest.java
~~~

### 8.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'password-upgrade-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.security:spring-security-core'
    implementation 'org.springframework.security:spring-security-crypto'
    implementation 'io.projectreactor:reactor-core'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.PasswordUpgradeDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Gradle Platform sử dụng Spring Boot BOM để quản lý các phiên bản tương thích của Spring Security, Reactor và JUnit. Không cần chạy một ứng dụng Spring Boot vì demo chỉ tập trung vào cơ chế băm và reactive authentication. Cần một phiên bản Gradle tương thích Java 17 cùng JDK 17+.

### 8.2. Mã Java đầy đủ

`src/main/java/demo/PasswordUpgradeDemo.java`:

~~~java
package demo;

import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordUpgradeDemo {

    private PasswordUpgradeDemo() {
    }

    public static void main(String[] args) {
        // CHỈ ĐỂ HỌC: mật khẩu legacy dạng rõ, không dùng ngoài demo.
        String legacyStoredHash = "{noop}legacy-pass";

        UserDetails legacyUser = User.withUsername("learner")
                .password(legacyStoredHash)
                .roles("USER")
                .build();

        MapReactiveUserDetailsService users =
                new MapReactiveUserDetailsService(legacyUser);

        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetailsRepositoryReactiveAuthenticationManager manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);

        manager.setPasswordEncoder(encoder);
        // Cho phép manager lưu hash được nâng cấp sau khi xác thực đúng.
        manager.setUserDetailsPasswordService(users);

        System.out.println("upgradeBefore="
                + encoder.upgradeEncoding(legacyStoredHash));

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "learner", "legacy-pass");

        // Chỉ tại ranh giới console main(), không dùng block() trong WebFlux.
        Authentication verified = manager.authenticate(request).block();

        String updatedHash = users.findByUsername("learner")
                .map(UserDetails::getPassword)
                .block();

        System.out.println("authenticated="
                + (verified != null && verified.isAuthenticated()));
        System.out.println("prefixBcrypt="
                + (updatedHash != null
                        && updatedHash.startsWith("{bcrypt}")));
        System.out.println("passwordStillMatches="
                + encoder.matches("legacy-pass", updatedHash));
        System.out.println("upgradeAfter="
                + encoder.upgradeEncoding(updatedHash));
    }
}
~~~

Lệnh chạy trong thư mục có `build.gradle`:

~~~bash
gradle run --quiet
~~~

Nếu dự án đã tạo Gradle Wrapper, thay `gradle` bằng `./gradlew` trên macOS/Linux hoặc `gradlew.bat` trên Windows.

**Kết quả stdout mong đợi của mã demo:**

~~~text
upgradeBefore=true
authenticated=true
prefixBcrypt=true
passwordStillMatches=true
upgradeAfter=false
~~~

Giải thích:
1. `upgradeBefore=true` vì policy mặc định dùng `bcrypt` để tạo hash mới, trong khi user cũ có ID `noop`.
2. Manager xác thực raw password `legacy-pass` với giá trị cũ đã lưu.
3. Khi đã gắn `ReactiveUserDetailsPasswordService`, manager có thể băm lại và cập nhật user **trong bộ nhớ** sau khi xác thực thành công.
4. Hash mới có `{bcrypt}`, dù nội dung bên trong khác nhau sau mỗi lần chạy do salt.
5. `matches` xác nhận cùng mật khẩu vẫn đăng nhập được sau migration.
6. Với work factor mặc định của encoder mới, `upgradeAfter=false` cho thấy chính sách hiện tại không yêu cầu nâng thêm.

Không in toàn bộ hash để làm kiểm thử snapshot: BCrypt có salt ngẫu nhiên nên **không có giá trị hash cố định**. Các dòng boolean nói trên mới là kết quả so sánh có thể dự đoán. Chương trình cần tải dependencies Gradle và có thể có thông báo riêng từ build tool, không tính vào stdout của class.

**Giới hạn của demo:** `MapReactiveUserDetailsService` chỉ lưu trong bộ nhớ tiến trình. Khởi động lại chương trình sẽ tạo user legacy mới từ mã nguồn. Production phải lưu hash mới vào database hoặc identity store thực sự; không ghi raw password, không lưu in-memory rồi tuyên bố đã di trú dữ liệu bền vững.

## 9. Kiểm thử bằng JUnit 5 + Reactor StepVerifier

Kiểm thử cần chứng minh ba điều: đúng mật khẩu thì được xác thực và nâng hash, sai mật khẩu không nâng hash, ID lạ không được âm thầm chấp nhận.

`src/test/java/demo/PasswordUpgradeTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordUpgradeTest {

    private static final String LEGACY = "{noop}legacy-pass";

    @Test
    void successfulLoginUpgradesStoredPassword() {
        var users = new MapReactiveUserDetailsService(
                User.withUsername("learner")
                        .password(LEGACY).roles("USER").build());

        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        var manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        manager.setUserDetailsPasswordService(users);

        StepVerifier.create(manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "learner", "legacy-pass")))
                .assertNext(authentication ->
                        assertTrue(authentication.isAuthenticated()))
                .verifyComplete();

        StepVerifier.create(users.findByUsername("learner"))
                .assertNext(user -> {
                    String hash = user.getPassword();
                    assertTrue(hash.startsWith("{bcrypt}"));
                    assertTrue(encoder.matches("legacy-pass", hash));
                    assertFalse(encoder.upgradeEncoding(hash));
                })
                .verifyComplete();
    }

    @Test
    void wrongPasswordDoesNotUpgrade() {
        var users = new MapReactiveUserDetailsService(
                User.withUsername("learner")
                        .password(LEGACY).roles("USER").build());

        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        var manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        manager.setUserDetailsPasswordService(users);

        StepVerifier.create(manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "learner", "wrong")))
                .expectError(BadCredentialsException.class)
                .verify();

        StepVerifier.create(users.findByUsername("learner"))
                .assertNext(user -> assertEquals(LEGACY, user.getPassword()))
                .verifyComplete();
    }

    @Test
    void unknownIdIsNotSilentlyAccepted() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        assertThrows(IllegalArgumentException.class,
                () -> encoder.matches(
                        "anything", "{notRegistered}some-hash"));
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kỳ vọng:** ba test PASS khi được xây dựng với các dependency đã khai báo. Đây là nhận định kiểm tra logic và API, **không phải báo cáo một lần chạy Gradle đã được thực hiện**.

Để diễn giải test đúng:
- Test đầu tiên đặt `setUserDetailsPasswordService(users)`, nên một lần authentication thành công có cơ chế ghi hash mới. Nếu bỏ dòng này, không được mặc định dữ liệu đã đổi.
- Test thứ hai xác nhận không nâng cấp khi người dùng cung cấp mật khẩu sai.
- Test thứ ba xác nhận ID không có trong mapping không âm thầm đi qua.
- `StepVerifier` subscribe vào publisher của manager và đợi hoàn thành; không cần `subscribe()` thủ công trong service.

## 10. Trường hợp hash BCrypt cũ **không có** `{bcrypt}`

Đây là bài toán migration rất thực tế:

~~~text
Dữ liệu trước đây:
$2a$10$...BCryptPayload...

Định dạng Spring Security DelegatingPasswordEncoder:
{bcrypt}$2a$10$...BCryptPayload...
~~~

Một hash có thể đã là BCrypt đúng chuẩn nhưng thiếu tiền tố Spring Security. Khi đó:
- `DelegatingPasswordEncoder` mặc định không biết ID để chọn thuật toán.
- Không phải raw password sai. Đây có thể là lỗi **format migration**.
- Nếu xác định chắc chắn toàn bộ nhóm đó là BCrypt đúng format, việc thêm tiền tố `{bcrypt}` vào chuỗi lưu là **thao tác metadata**, không thay đổi bản thân hash và không cần raw password.
- Nhưng **không** được thêm `{bcrypt}` bừa bãi vào mọi hash vô danh: những bản ghi SHA, PBKDF2 hoặc dữ liệu hỏng sẽ bị dán nhãn sai và không thể xác minh.

Quy trình an toàn cho dữ liệu thiếu prefix:
1. Inventory schema và nguồn xuất phát để xác định thuật toán thực tế.
2. Kiểm tra format/cost và lấy mẫu đại diện trong môi trường kiểm thử có kiểm soát.
3. Viết script migration idempotent chỉ thay nhóm bản ghi đã nhận diện chắc chắn.
4. Sao lưu, có kế hoạch rollback và đo lỗi đăng nhập sau triển khai.
5. Với hash không chắc loại, yêu cầu reset password/điều tra thay vì đoán mapping.
6. Sau khi thêm tiền tố, có thể dùng `upgradeEncoding` để nâng tiếp khi người dùng login đúng.

Nếu phải hỗ trợ tạm thời định dạng legacy ngay lúc xác thực, Spring Security có:

~~~java
// API minh họa, không nên áp dụng đại trà không kiểm soát.
delegating.setDefaultPasswordEncoderForMatches(legacyEncoder);
~~~

**Rủi ro:** đây là đường fallback cho **ID không được map, bao gồm ID thiếu hoặc ID lạ**. Đối tượng fallback nhận **chuỗi hash gốc đầy đủ**, kể cả tiền tố `{unexpected}` nếu có. Một fallback quá thoáng có thể che lỗi dữ liệu, tạo downgrade hoặc cho phép dữ liệu giả mạo đi theo scheme khác. Tốt hơn là chuẩn hóa dữ liệu có thể nhận diện bằng migration rõ ràng; nếu cần adapter, phải kiểm tra nghiêm ngặt format legacy và từ chối mọi ID không thuộc danh sách được chấp thuận.

Đừng “sửa” lỗi no prefix bằng cách lưu hash trần thành `{noop}...`: như vậy bạn biến **hash** thành “password plaintext” theo ý nghĩa của NoOpPasswordEncoder, dễ tạo kết quả sai và nguy cơ bảo mật nghiêm trọng.

## 11. Nâng thuật toán và nâng tham số: hai kiểu migration

### 11.1. Thay ID sang thuật toán mới

Giả sử kho dữ liệu có các hash `{bcrypt}...`, còn `idForEncode` mới là `argon2-policy-v2`. Mapping vẫn giữ `bcrypt` để xác minh tài khoản cũ. Khi user đăng nhập hợp lệ, `upgradeEncoding(stored)` có thể báo cần nâng vì ID khác, sau đó `encode(raw)` tạo hash theo `argon2-policy-v2`.

Lúc đổi thuật toán cần:
- Benchmark CPU/memory và phân bổ tài nguyên.
- Kiểm tra thư viện/dependency thực tế của encoder mới.
- Giữ mapping cũ cho đến khi tỷ lệ tài khoản chưa nâng còn dưới ngưỡng chính sách và có phương án reset.
- Đảm bảo mọi instance đọc được **cả ID mới lẫn cũ** trước khi bắt đầu ghi ID mới (rolling deploy).
- Theo dõi kết quả login và storage update sau deploy.

### 11.2. Giữ BCrypt nhưng tăng work factor

Khi dùng cùng ID `bcrypt`, `BCryptPasswordEncoder.upgradeEncoding` có thể kiểm tra cost trong hash cũ so với strength hiện tại. Ví dụ tăng policy lên `new BCryptPasswordEncoder(12)` có thể đánh dấu các hash có cost thấp hơn cần nâng. Mức 12 chỉ là **ví dụ**, không phải cost chuẩn cho mọi hệ thống.

Vì cùng ID đã có thể chứa work factor trong payload, không nhất thiết phải tạo `{bcrypt-v2}` chỉ để tăng cost nếu encoder của bạn hỗ trợ nâng cấp cùng ID ổn định. Nhưng nếu thay đổi tham số hay format không tương thích, ID phiên bản riêng có thể giúp migration rõ ràng hơn.

### 11.3. PBKDF2, scrypt, Argon2 có policy version

Đối với các thuật toán phụ thuộc iterations, memory, parallelism, salt length hoặc format encode, phải biết đúng tham số đã tạo hash cũ. Một số ID của Spring Security mang nhãn phiên bản, ví dụ `pbkdf2@SpringSecurity_v5_8` hoặc `argon2@SpringSecurity_v5_8`. Đây là cách tránh map lại một ID cũ sang policy không đọc được dữ liệu cũ.

Không dựa vào duy nhất tên `pbkdf2` để kết luận hai hash có cùng PRF/iterations/salt. Trong migration, phải giữ đúng mapping phiên bản lịch sử theo thư viện đã dùng khi tạo dữ liệu.

## 12. Thiết kế lưu hash mới bền vững trong môi trường reactive

Trong hệ thống thật, `ReactiveUserDetailsPasswordService.updatePassword` nên dùng kho dữ liệu reactive, ví dụ R2DBC hoặc client tương đương. Một mô hình cập nhật an toàn cần:
- Ghi hash **đã băm**, không ghi raw password.
- Áp dụng điều kiện so khớp với hash phiên bản cũ hoặc version cũ để tránh race.
- Thông báo lỗi ghi khi không thành công, thay vì trả `Mono.empty()` một cách khó chẩn đoán.
- Không đưa thông tin nhạy cảm vào response, tracing hay audit log.
- Không mở subscription riêng ngoài pipeline authentication đang sở hữu công việc.

Ví dụ pseudocode kiểu Java:

~~~java
// MINH HỌA cấu trúc: cần định nghĩa UserEntity, repository và mapper.
// Đây không phải chương trình Java có thể chạy riêng.

public Mono<UserDetails> updatePassword(UserDetails user, String newHash) {
    return userRepository.findByUsername(user.getUsername())
        .flatMap(current ->
            userRepository.updateHashIfCurrentMatches(
                    current.id(),
                    current.passwordHash(),
                    newHash)
                .flatMap(rowsUpdated -> {
                    if (rowsUpdated == 1) {
                        return userRepository.findByUsername(user.getUsername())
                                .map(this::toUserDetails);
                    }
                    return Mono.error(new IllegalStateException(
                            "Password changed concurrently"));
                })
        );
}
~~~

Đây là mẫu **compare-and-swap (CAS)** theo old hash, không phải ví dụ R2DBC đầy đủ. Repository thực tế cần đảm bảo `updateHashIfCurrentMatches` là một thao tác atomic trong database; không tách kiểm tra và cập nhật thành hai câu SQL độc lập không có điều kiện.

Đặc biệt, nếu người dùng đồng thời đổi mật khẩu trên thiết bị khác, login bằng mật khẩu cũ **không được** ghi đè hash của mật khẩu mới. CAS giúp phát hiện thay đổi cạnh tranh; chính sách của ứng dụng quyết định có yêu cầu thử lại/đăng nhập lại hay không.

Một cách kiểm soát triển khai là ghi số lượng user theo **ID thuật toán/phiên bản**, đếm upgrade thành công/thất bại, đo latency và theo dõi tỷ lệ user còn hash yếu. Không bao giờ gửi từng hash hay raw password sang dashboard.

## 13. Lỗi thường gặp với DelegatingPasswordEncoder

| Lỗi | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Lưu hash BCrypt trần rồi dùng Delegating mặc định | Không có `{id}` để chọn mapping | Migration format hoặc adapter legacy có kiểm soát |
| Dùng `{noop}` cho user thật | Lưu password dạng rõ | Dùng thuật toán thích nghi; loại bỏ dữ liệu cũ |
| `encode(raw).equals(stored)` | Hash có salt ngẫu nhiên | Dùng `matches(raw, stored)` |
| Converter/controller tự tạo token authenticated chỉ vì `matches` chưa chạy | Bỏ qua authentication | Để manager kiểm tra rồi cấp authentication |
| Dùng `upgradeEncoding` rồi tưởng DB tự đổi | Hàm chỉ trả boolean | Cần `encode(raw)` và service persistence |
| Cập nhật hash ngay cả khi raw password sai | Kẻ tấn công có thể làm hỏng tài khoản | Chỉ nâng cấp sau xác thực thành công |
| Tự thêm `{bcrypt}` vào mọi hash cũ | Sai nhận diện thuật toán | Inventory format và migration theo nhóm đã xác minh |
| Đặt fallback quá rộng cho unknown ID | Che dữ liệu hỏng, có thể downgrade | Giới hạn ID hợp lệ, từ chối format lạ |
| Xóa mapping cũ ngay sau deploy | Tài khoản chưa nâng không đăng nhập được | Rolling migration rồi mới thu hẹp mapping |
| Chọn cost quá cao mà không đo | Login CPU/memory nghẽn, nguy cơ DoS | Benchmark theo concurrency và SLA |
| Chạy encode/matches nặng trên event-loop | Giảm khả năng phục vụ request | Dùng manager reactive/scheduler có kiểm soát |
| Đưa hash/password vào log | Rò rỉ bí mật hoặc metadata người dùng | Log trạng thái kỹ thuật không nhạy cảm |
| Nhầm Spring Security Reactive với Servlet | Cấu hình nhầm manager/user service | Dùng `ReactiveUserDetailsService` và `ReactiveUserDetailsPasswordService` |
| Tự `subscribe()` trong password update | Mất error/cancellation/transaction flow | Trả `Mono<UserDetails>` để manager compose |
| Hiểu hash upgrade là password reset | Không thay secret bị lộ | Quy định rõ khi nào buộc đổi mật khẩu thật |

Một failure cần phân loại rõ: **mật khẩu sai**, **hash sai format/không biết ID**, **kho dữ liệu không truy cập được**, **nâng cấp không ghi được** và **tài khoản bị khóa** là những nguyên nhân khác nhau. Response public nên tránh tiết lộ quá nhiều thông tin nhưng hệ thống quan sát nội bộ cần đủ để xử lý đúng nguyên nhân.

## 14. Quy trình migration thực tế theo giai đoạn

### Giai đoạn A — Khảo sát và đặt policy

1. Xác định tất cả nguồn tài khoản và các định dạng hash đang lưu.
2. Thống kê số lượng theo ID hoặc nhóm format, không lộ password/hash.
3. Chọn thuật toán/chi phí mục tiêu dựa trên benchmark thực tế, yêu cầu bảo mật và khả năng vận hành.
4. Xác định tài khoản không thể nâng nếu người dùng không đăng nhập, cùng chính sách reset.
5. Chuẩn bị monitoring, rollback và cách xử lý thay đổi đồng thời.

### Giai đoạn B — Triển khai khả năng đọc trước, viết sau

6. Deploy bản đọc được **hash cũ và hash mới** trên tất cả instance.
7. Bổ sung `PasswordEncoder` mapping, kiểm thử ID được phép/không được phép.
8. Tạo/cấu hình `ReactiveUserDetailsPasswordService` có cơ chế atomic update.
9. Chỉ khi đảm bảo mọi instance đọc được ID mới, mới bật tạo hash mới hoặc opportunistic upgrade.
10. Đo authentication failure, update conflict, latency và lỗi hashing.

### Giai đoạn C — Nâng cấp dần và kết thúc

11. Người đăng nhập đúng được nâng hash trong cùng luồng đáng tin cậy.
12. Người không đăng nhập trong thời gian dài cần chương trình thông báo/đặt lại mật khẩu theo chính sách.
13. Khi không còn dữ liệu cần scheme legacy, gỡ mapping yếu để giảm bề mặt tấn công.
14. Kiểm tra backup, restore, reporting và công cụ quản trị cũng hiểu format mới.
15. Không giả định “100% upgraded” từ việc code đã có `upgradeEncoding`; phải đo dữ liệu thực tế.

**Với dữ liệu `{noop}` hoặc hash rất yếu từng xuất hiện trong môi trường thật**, cần đánh giá khả năng lộ credential và cân nhắc **buộc đổi mật khẩu**, không coi việc hash lại sau đăng nhập là khắc phục trọn vẹn.

## 15. Các trường hợp kiểm thử nên có trong ứng dụng WebFlux

| Trường hợp | Kết quả cần kiểm chứng |
| --- | --- |
| User mới đăng ký/đổi password | Chỉ lưu `{id}` của policy hiện hành; không có plaintext |
| User cũ có `{bcrypt}` và đúng mật khẩu | Đăng nhập thành công; nâng nếu policy/cost yêu cầu |
| User cũ có format được hỗ trợ khác | Đăng nhập thành công, lưu lại hash mới khi đủ điều kiện |
| Sai mật khẩu | Xác thực thất bại, không đổi hash |
| Thiếu/unknown `{id}` | Xử lý lỗi cấu hình/format an toàn; không tự fallback permissive |
| Có hai login đồng thời | Update không ghi đè lẫn nhau hoặc ghi đè password change |
| User vừa đổi password trong lúc upgrade | Không phục hồi password cũ |
| Mất kết nối database khi cập nhật | Có lỗi theo chính sách, giám sát và dữ liệu không hỏng |
| Một instance cũ, một instance mới trong rolling deploy | Cả hai hiểu format mới trước khi có ghi hash mới |
| Password hash đã nâng nhưng role bị từ chối | Authorization vẫn độc lập, không phải lỗi hash |
| Tải login cao | Có rate limiting, cân bằng tài nguyên và không chặn WebFlux event-loop |
| Reset password do credential lộ | Phải thay secret và chính sách session/token, không chỉ rehash cùng secret |

Để test end-to-end WebFlux, dùng `WebTestClient` với một security chain phù hợp và một kho user có thể quan sát trạng thái trước/sau. Unit test `PasswordEncoder` chưa đủ xác nhận endpoint, login filter hoặc database persistence.

### 15.1. Câu hỏi 401, 403 có liên hệ gì?

- **401 Unauthorized:** credentials thiếu hoặc không xác minh được (với API có entry point trả 401).
- **403 Forbidden:** người dùng có authentication hợp lệ nhưng không có quyền được yêu cầu.
- Hash upgrade ảnh hưởng cách xác minh **mật khẩu**, không tự cấp quyền `ADMIN` hay bỏ qua check role/ownership.

Nếu user đăng nhập được nhưng vẫn nhận 403, không nên thay `PasswordEncoder` hoặc gán thêm authorities trong converter để “sửa lỗi”.

## 16. Bài tập tự kiểm tra và đáp án

**Câu 1.** `{bcrypt}` và `$2a$10$...` khác nhau thế nào?

> `{bcrypt}` là ID của DelegatingPasswordEncoder để chọn encoder; `$2a$10$...` là payload theo định dạng BCrypt, chứa metadata riêng của thuật toán như cost và salt.

**Câu 2.** Vì sao không so sánh `encoder.encode(input)` với hash đã lưu bằng `equals`?

> Các hàm hash password thích nghi thường tạo salt ngẫu nhiên mỗi lần encode. `matches(raw, stored)` mới là API xác minh đúng.

**Câu 3.** Khi hash có ID `{unknown}`, vì sao `matches` có thể ném `IllegalArgumentException`?

> Mặc định không có encoder tương ứng trong mapping. Điều này khác với trường hợp mật khẩu sai trong một hash có format hợp lệ.

**Câu 4.** `upgradeEncoding(stored)` trả `true` có làm database đổi theo không?

> Không. Cần xác minh raw password, tạo hash mới qua `encode(raw)` và lưu thông qua cơ chế cập nhật đáng tin cậy.

**Câu 5.** Trong Spring Security Reactive, interface nào có trách nhiệm lưu hash được nâng cấp?

> `ReactiveUserDetailsPasswordService`, thường được cấu hình cho reactive authentication manager. Trong demo, `MapReactiveUserDetailsService` triển khai được hợp đồng này.

**Câu 6.** Hash BCrypt cũ không có `{bcrypt}` có thể thêm tiền tố mà không cần raw password không?

> Chỉ khi có bằng chứng đáng tin cậy rằng payload chính là BCrypt đúng định dạng. Đây là chuẩn hóa metadata, không phải tạo hash mới.

**Câu 7.** Tại sao không đặt `setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder...)` cho toàn hệ thống?

> Vì mọi ID thiếu/lạ có thể đi qua fallback nguy hiểm, che lỗi dữ liệu và khiến credential không an toàn được chấp nhận.

**Câu 8.** Nâng công thức băm có sửa được việc raw password đã bị lộ trong quá khứ không?

> Không. Cần đánh giá rủi ro, có thể buộc reset password, thu hồi phiên/token và áp dụng kiểm soát khác.

**Câu 9.** Vì sao không nâng hash trong background task tạo bởi `subscribe()` thủ công?

> Vì mất sự gắn kết giữa xác thực, lưu dữ liệu, error/cancellation và kiểm soát thứ tự. Hãy compose publisher của password service vào authentication flow.

**Câu 10.** Khi chuyển từ `bcrypt` sang một policy Argon2 mới, cần triển khai mapping theo trình tự nào?

> Cho tất cả instance đọc được cả ID cũ và mới trước; sau đó mới cho phép encode ID mới, theo dõi migration và chỉ gỡ ID cũ khi dữ liệu còn lại đã được giải quyết.

## 17. Tổng kết

`DelegatingPasswordEncoder` giải quyết bài toán **đa phiên bản mật khẩu** bằng cách tách **thuật toán dùng tạo hash mới** khỏi **thuật toán dùng xác minh hash đã lưu**. Tiền tố `{id}` định tuyến việc so khớp; nó không phải salt, không phải encryption và không bảo đảm mật khẩu an toàn nếu thuật toán bên trong yếu.

Ba câu lệnh nên nhớ:

~~~java
String newStoredHash = encoder.encode(rawPassword);
boolean passwordIsCorrect = encoder.matches(rawPassword, storedHash);
boolean needsUpgrade = encoder.upgradeEncoding(storedHash);
~~~

Để hoàn thành migration trong Spring Security Reactive, cần **xác thực thành công → đánh giá nâng cấp → băm lại → lưu bền vững qua `ReactiveUserDetailsPasswordService`**, bảo đảm không ghi đè thay đổi đồng thời, tránh chạy băm trên event-loop và có chiến lược xử lý tài khoản không đăng nhập trong thời gian dài.

### Tài liệu tham khảo chính thức

- Spring Security Reference — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security Javadoc — DelegatingPasswordEncoder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html
- Spring Security Javadoc — PasswordEncoderFactories: https://docs.spring.io/spring-security/site/docs/6.4.5/api/org/springframework/security/crypto/factory/PasswordEncoderFactories.html
- Spring Security Javadoc — AbstractUserDetailsReactiveAuthenticationManager: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html
- Spring Security Javadoc — ReactiveUserDetailsPasswordService: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsPasswordService.html
- Spring Security Javadoc — MapReactiveUserDetailsService: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html
- Spring Security Javadoc — BCryptPasswordEncoder: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html