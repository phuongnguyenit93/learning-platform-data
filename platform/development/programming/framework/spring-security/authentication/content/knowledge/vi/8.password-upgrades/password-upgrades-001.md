# Lựa chọn thuật toán mới mà vẫn xác minh được dữ liệu cũ

> **Ngữ cảnh:** Spring Security → authentication → **Nâng cấp mật khẩu**. Trong một hệ thống đã có người dùng thật, đổi thuật toán hash mật khẩu không chỉ là thay `PasswordEncoder`. Hệ thống phải tiếp tục **xác minh chính xác các hash cũ**, tạo hash mới theo chính sách hiện tại, nâng cấp dần khi có bằng chứng mật khẩu hợp lệ, và không vô tình mở một đường đăng nhập yếu. Bài tập trung vào `DelegatingPasswordEncoder`, định dạng `{id}encodedPassword`, `upgradeEncoding`, `DaoAuthenticationProvider`, `UserDetailsPasswordService` và triển khai migration an toàn. Ví dụ Java 17 dùng Spring Security 6.5.11.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **thuật toán dùng để encode mật khẩu mới** và **thuật toán được giữ để verify hash cũ**; giải thích vì sao hai tập này không nhất thiết giống nhau.
2. Đọc đúng chuỗi `{id}encodedPassword` của `DelegatingPasswordEncoder`; biết ID là thông tin chọn bộ giải mã hash, **không phải secret** và cũng không phải bằng chứng mật khẩu hợp lệ.
3. Lựa chọn thuật toán và tham số mới dựa trên chính sách bảo mật, tài nguyên CPU/RAM, chi phí verify và khả năng tương thích dữ liệu.
4. Duy trì xác minh bcrypt/scrypt/Argon2/PBKDF2 legacy khi cần, nhưng **không tự động chấp nhận plaintext, MD5 hoặc hash không rõ nguồn**.
5. Hiểu `matches`, `encode`, `upgradeEncoding`, thời điểm dùng `UserDetailsPasswordService.updatePassword` và cơ chế `DaoAuthenticationProvider` hỗ trợ nâng hash sau khi đăng nhập thành công.
6. Xử lý hash cũ **không có tiền tố ID**, hash sai định dạng, ID không được hỗ trợ, user hiếm khi đăng nhập và thay đổi mật khẩu đồng thời.
7. Chạy chương trình Java 17 hoàn chỉnh minh họa **bcrypt cũ → Argon2id mới**, giữ login hoạt động, rehash khi login, kiểm mật khẩu sai và từ chối hash không có ID.
8. Thiết kế kế hoạch rollout nhiều instance: đọc được cả hai định dạng trước khi ghi định dạng mới; giám sát, rollback, rollback có giới hạn, canary và kiểm thử bảo mật.

## 2. Bài toán thực tế: không thể đổi encoder rồi giả định dữ liệu cũ tự tương thích

Giả sử cơ sở dữ liệu đang có:

~~~text
users
---------------------------------------------------------
username   password_hash
lan        $2a$10$...              (bcrypt legacy, không ID)
minh       {bcrypt}$2a$12$...      (bcrypt đã có ID)
mai        {scrypt}$...            (scrypt tham số cũ)
~~~

Mỗi chuỗi hash là kết quả của một thuật toán với salt/tham số riêng; mật khẩu gốc **không được lưu**. Tổ chức quyết định dùng Argon2id cho mật khẩu mới. Nếu chỉ thay một bean:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
}
~~~

thì `Argon2PasswordEncoder` **không tự biết cách xác minh chuỗi bcrypt/scrypt cũ**. Đường đăng nhập dùng hash cũ có thể lỗi dù người dùng nhập đúng mật khẩu. Điều này khác với “người dùng nhập sai password”: vấn đề là **ứng dụng đã mất khả năng đọc format hash cũ**.

Phương án đúng về mặt kiến trúc:

- Đầu ra **`encode(raw)`** dùng thuật toán/params **mới**.
- Đầu vào **`matches(raw, storedHash)`** chọn encoder **đúng với metadata của hash đã lưu**.
- Sau một lần xác minh thành công, có thể **encode lại raw password vừa nhập** bằng thuật toán mới và cập nhật bản ghi.
- Không cố “chuyển đổi trực tiếp” chuỗi bcrypt hash thành Argon2 hash của mật khẩu gốc; hàm hash mật khẩu là **một chiều**.

### 2.1. Một câu trả lời khác nhau cho ba câu hỏi

| Câu hỏi | Trách nhiệm |
| --- | --- |
| Đăng ký/reset mật khẩu từ hôm nay dùng thuật toán nào? | `idForEncode` và encoder chính sách hiện tại |
| Khi login, hash trong database được tạo bởi thuật toán nào? | ID/metadata đáng tin của từng bản ghi |
| Sau login thành công, hash cũ có cần nâng cấp không? | `upgradeEncoding`, chính sách bảo mật và `UserDetailsPasswordService`/logic DB |

**Điểm trọng tâm:** hỗ trợ xác minh hash cũ **không** có nghĩa tiếp tục tạo hash mới bằng thuật toán cũ. Tách đường **read/verify** khỏi **write/encode** để nâng cấp không làm khóa người dùng đang có.

## 3. Hash mật khẩu là dữ liệu một chiều và có phiên bản

Một `PasswordEncoder` phù hợp tạo hash thích ứng có salt. Khi verify, ứng dụng sử dụng mật khẩu thô **vừa được client đưa qua một luồng xác thực hợp lệ** và hash lưu trong kho account.

~~~java
String encoded = passwordEncoder.encode(rawPassword);
boolean match = passwordEncoder.matches(candidatePassword, encoded);
~~~

Với encoder chuẩn, hai lần `encode` cùng mật khẩu thường trả các chuỗi khác nhau vì salt ngẫu nhiên. Vì vậy **không** xác minh bằng:

~~~java
// SAI: encode() tạo salt mới; so sánh chuỗi thường không khớp.
boolean ok = passwordEncoder.encode(candidatePassword)
        .equals(storedHash);
~~~

### 3.1. Tại sao không thể rehash hàng loạt từ hash cũ?

Một chuỗi bcrypt không chứa raw password. Không thể dùng:

~~~text
Argon2id(bcryptHash)
~~~

rồi tuyên bố kết quả là:

~~~text
Argon2id(originalPassword)
~~~

Hai đầu vào là **hai chuỗi khác nhau**. “Hash của hash” còn dẫn tới hợp đồng verify khác và có thể tạo đường di trú dễ sai, không phải chuyển đổi thuật toán mật khẩu tương đương. Một migration đáng tin cần **raw password ở thời điểm người dùng xác thực thành công**, hoặc yêu cầu người dùng reset password theo quy trình có xác minh.

Không lưu raw password vào queue, log, analytics, audit table hay background job chỉ để thực hiện rehash sau. Nên nâng hash **ngay trong ranh giới xác thực** trước khi loại bỏ dữ liệu mật khẩu thô.

### 3.2. Tham số cũng là phiên bản

“Bcrypt” không phải một mức bảo mật duy nhất: bcrypt có cost factor. “Argon2id” không đủ để mô tả ngân sách CPU/RAM: cần memory cost, iterations và parallelism. Hash string của các encoder thường chứa dữ liệu cần thiết cho `matches`; metadata **chọn thuật toán** qua ID của `DelegatingPasswordEncoder` vẫn là lớp khác.

Khi thuật toán không đổi nhưng work factor tăng, encoder cũng có thể báo cần nâng cấp. Quyết định này phụ thuộc `upgradeEncoding` của implementation và policy của ứng dụng, không phải một cron job tự động đọc password từ hash.

## 4. Chọn thuật toán mới theo tiêu chí nào?

Một số lựa chọn phổ biến được Spring Security hỗ trợ:

| Encoder | Phân loại | Tham số tiêu biểu | Lưu ý khi migration |
| --- | --- | --- | --- |
| `BCryptPasswordEncoder` | Adaptive password hash | Cost/strength | Dễ tương thích hệ thống cũ có bcrypt; chỉ đổi cost cũng là một nâng cấp |
| `SCryptPasswordEncoder` | Memory-hard adaptive KDF | `N,r,p` | Tốn CPU/RAM; benchmark và giới hạn concurrency |
| `Argon2PasswordEncoder` | Memory-hard (Argon2id theo implementation Spring Security) | Memory KiB, iterations, parallelism | Bouncy Castle trên classpath; kiểm ngân sách tài nguyên |
| `Pbkdf2PasswordEncoder` | Adaptive KDF | Iterations, PRF, salt | Có thể phù hợp ràng buộc compliance; cần xác định phiên bản preset |
| MD5/SHA-1/SHA-256 đơn lẻ | Fast hashes, không thích hợp cho password mới | Không có work factor thích ứng | Không dùng làm mục tiêu nâng cấp; xử lý legacy hạn chế và ưu tiên reset |

Không có lựa chọn đúng chỉ vì thuật toán có tên mới. Một quyết định nên xét **mô hình đe dọa**, phiên bản thư viện được hỗ trợ, memory limit và concurrency của server, thời gian xác minh trên phần cứng thật, trạng thái database và lộ trình nâng cấp. Ví dụ dùng Argon2id để minh họa, **không có nghĩa mọi ứng dụng phải chuyển sang Argon2id**.

### 4.1. Argon2id, scrypt hay bcrypt cost mới?

- Nếu hệ thống chủ yếu lưu bcrypt cost thấp, **tăng cost bcrypt** là một phương án có thể đơn giản hơn di chuyển toàn bộ thuật toán, miễn policy và hiệu năng cho phép.
- Nếu tổ chức chọn Argon2id để tăng memory hardness, phải kiểm dependency, memory concurrency và khả năng rollout trên toàn bộ instance.
- Với hệ thống dùng PBKDF2 do yêu cầu compliance, giữ format và tham số phù hợp thay vì đổi sang một thuật toán khác chỉ vì xu hướng.
- Chọn công nghệ **được bảo trì** và tham số được benchmark, không áp một con số cố định từ laptop lên container production.

Tài liệu Spring Security hướng dẫn điều chỉnh độ nặng của một lần password verification trên hệ thống mục tiêu, thường lấy cỡ **một giây** như điểm tham chiếu. Đây là **gợi ý để benchmark**, không phải SLA áp dụng cho mọi hệ thống. Phải thử cả p95/p99 ở tải login đồng thời.

### 4.2. Đừng dùng “hash dài hơn” làm tiêu chí bảo mật duy nhất

Một hash 64 byte chưa chắc an toàn hơn hash 32 byte nếu thuật toán nhanh hoặc mật khẩu yếu. Salt ngẫu nhiên, thuật toán adaptive, work factor, memory hardness, kiểm soát đăng nhập và mức độ bí mật của dữ liệu được lưu mới quyết định tổng thể.

## 5. DelegatingPasswordEncoder: một encoder để ghi mới, nhiều encoder để đọc cũ

Spring Security dùng `DelegatingPasswordEncoder` để tách hai mục tiêu:

~~~text
                    encode(raw)
                        |
                        v
          {current-id}currentEncodedHash

stored {id}hash ---- matches(raw, stored)
         |
         +--- id=bcrypt-v1 ----> BCryptPasswordEncoder
         |
         +--- id=scrypt-v1 ----> SCryptPasswordEncoder
         |
         +--- id=argon2-v58 --> Argon2PasswordEncoder
~~~

Constructor:

~~~java
DelegatingPasswordEncoder encoder =
        new DelegatingPasswordEncoder(
                "argon2-v58",
                Map.of(
                        "bcrypt-v1", new BCryptPasswordEncoder(10),
                        "argon2-v58",
                            Argon2PasswordEncoder
                                    .defaultsForSpringSecurity_v5_8()));
~~~

**Hai vai trò của cấu hình:**

- `"argon2-v58"` ở tham số đầu là **`idForEncode`**: hash mới do `encode` tạo sẽ có prefix `{argon2-v58}`.
- `Map` cho phép `matches` chọn encoder tương ứng với từng **ID đã lưu**. Bản ghi `{bcrypt-v1}...` vẫn được verify bằng bcrypt, dù không còn được dùng để encode mới.

Các ID `bcrypt-v1` và `argon2-v58` trong ví dụ là **ID ứng dụng tự định nghĩa**. Chúng không phải các tên mà factory chuẩn bắt buộc phải dùng; khi thay ID trong cấu hình phải thay/duy trì mapping cho dữ liệu cũ tương ứng.

### 5.1. Format lưu trữ chuẩn

~~~text
{id}encodedPassword
~~~

Ví dụ:

~~~text
{bcrypt-v1}$2a$10$...
{argon2-v58}$argon2id$v=19$m=16384,t=2,p=1$...
~~~

Các phần dấu ba chấm ở đây **chỉ để minh họa format**, không phải hash đầy đủ có thể đem verify. Dữ liệu thực phải là chuỗi hash **nguyên vẹn** do encoder tạo, gồm salt và các thành phần thuật toán yêu cầu.

`DelegatingPasswordEncoder` đọc ID từ đầu chuỗi. Nếu không có prefix hoặc ID không có trong map, **mặc định `matches` ném `IllegalArgumentException`**, chứ không thử hết mọi thuật toán tới khi một cái khớp. Đây là hành vi fail-safe đáng giữ.

### 5.2. Đừng đồng nhất ID với thuật toán tự suy ra từ chuỗi

Dù bcrypt có tiền tố `$2a$` hoặc `$2b$`, `DelegatingPasswordEncoder` không tự nhận diện mọi format legacy khi thiếu `{id}`. Nó dùng **mapping ID mà bạn cấu hình**.

Nếu thiếu prefix, giải pháp phải dựa trên **metadata provenance đáng tin**: biết bản ghi đến từ ứng dụng version nào, cột/tenant nào và được tạo bởi encoder nào. Đừng chấp nhận bất kỳ chuỗi không prefix bằng một bộ đoán tự do có thể biến data sai format thành đường đăng nhập yếu.

### 5.3. Mapping factory mặc định có gì?

Spring Security cung cấp:

~~~java
PasswordEncoder defaults =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Theo tài liệu dòng Spring Security 6.5, factory có mapping cho nhiều format như bcrypt, pbkdf2, scrypt, argon2 và các biến thể preset gắn phiên bản. Nhưng `idForEncode` **mặc định là bcrypt** trong bản này, không tự chuyển sang Argon2id chỉ vì có decoder Argon2 trong map.

Các ID factory phổ biến (trên dòng 6.5) bao gồm `bcrypt`, `pbkdf2@SpringSecurity_v5_8`, `scrypt@SpringSecurity_v5_8`, `argon2@SpringSecurity_v5_8` cùng một số mapping cũ. Những mapping để đọc legacy **không có nghĩa thuật toán cũ còn phù hợp cho hash mới**.

Chọn map custom khi muốn kiểm soát chính xác những ID được chấp nhận và thuật toán mới. **Không tạo một map bỏ quên `idForEncode`**, vì constructor cần ID hiện diện và có encoder tương ứng.

## 6. Chu trình migrate ở thời điểm login thành công

Một đường xử lý điển hình:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Authentication filter
    participant P as DaoAuthenticationProvider
    participant S as UserDetailsService
    participant E as DelegatingPasswordEncoder
    participant U as UserDetailsPasswordService
    participant D as Database
    C->>F: Username + raw password qua HTTPS
    F->>P: Yêu cầu Authentication (thông qua manager)
    P->>S: loadUserByUsername
    S->>D: Đọc hash + trạng thái account
    D-->>S: {bcrypt-v1}oldHash
    S-->>P: UserDetails
    P->>E: matches(raw, {bcrypt-v1}oldHash)
    E-->>P: true nhờ BCrypt
    P->>P: Kiểm account status và các yêu cầu liên quan
    P->>E: upgradeEncoding(oldHash)
    E-->>P: true (ID khác idForEncode)
    P->>E: encode(raw)
    E-->>P: {argon2-v58}newHash
    P->>U: updatePassword(user, newHash)
    U->>D: Cập nhật hash an toàn
    D-->>U: Xác nhận cập nhật
    U-->>P: UserDetails đã cập nhật
    P-->>F: Authentication đã xác thực
~~~

Sơ đồ tập trung vào bước upgrade trong provider và rút gọn các bước filter/manager. Trong ứng dụng Servlet thực tế, filter gọi `AuthenticationManager`, thường là `ProviderManager`, rồi manager chuyển tiếp cho `DaoAuthenticationProvider`.

### 6.1. Trình tự đúng: verify trước, rehash sau

1. Client đưa credential qua cơ chế đăng nhập được bảo vệ (HTTPS).
2. `UserDetailsService` đọc đúng hash và trạng thái tài khoản.
3. `PasswordEncoder.matches(raw, oldHash)` xác minh bằng **encoder tương ứng ID cũ**.
4. Các kiểm tra account status và chính sách bổ sung phải được đáp ứng để cho phép authentication success.
5. `upgradeEncoding(oldHash)` cho biết hash đang dùng nên được nâng cấp hay không.
6. Nếu cần, `encode(raw)` tạo hash hiện tại và ghi bằng `UserDetailsPasswordService`/repository.
7. Authentication thành công được trả; các thành phần filter quản lý `SecurityContext` theo cơ chế đã cấu hình.

**Tuyệt đối không rehash và lưu password thô khi `matches` chưa thành công.** Làm vậy có thể thay hash account bằng giá trị do attacker đưa tới, tương đương chiếm quyền tài khoản.

### 6.2. `upgradeEncoding` không tự cập nhật database

Với `DelegatingPasswordEncoder`, khi hash có ID khác `idForEncode`, `upgradeEncoding` thường trả `true`. Khi ID giống encoder hiện tại, nó chuyển quyết định cho encoder tương ứng để kiểm work factor/params.

Đây chỉ là **tín hiệu**, không phải thao tác ghi. Nếu không có một `UserDetailsPasswordService` phù hợp hoặc logic cập nhật an toàn, account có thể tiếp tục giữ hash cũ sau login dù `upgradeEncoding` trả true.

### 6.3. `UserDetailsPasswordService` nhận **hash mới**, không phải raw password

Giao diện:

~~~java
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

Tên tham số `newPassword` trong API dễ khiến người mới hiểu sai: ở đường nâng hash của `DaoAuthenticationProvider`, nó là **chuỗi encoded mới** do `PasswordEncoder.encode(raw)` tạo. Triển khai repository **phải lưu nguyên chuỗi encoded đó**, không encode thêm lần nữa.

Sai:

~~~java
// SAI: newPassword đã được encode; đoạn này sẽ double-hash.
repository.savePassword(
        user.getUsername(),
        encoder.encode(newPassword));
~~~

Đúng trong ngữ cảnh API:

~~~java
// Đoạn tích hợp minh họa; newPassword là encoded hash.
repository.savePassword(user.getUsername(), newPassword);
~~~

Đoạn đúng vẫn cần transaction, đồng bộ và xử lý concurrent changes trong repository thật.

## 7. Ví dụ Java 17 độc lập: bcrypt cũ, Argon2id mới, tự nâng hash

Chúng ta tạo một project Gradle console dùng **encoder và provider thật**. Kho account dùng `ConcurrentHashMap` để mô phỏng database; `UserDetailsPasswordService` ghi hash vào map và đếm số lần nâng cấp.

Các điều đã được đảm bảo bởi thiết kế demo:

- Account `lan` lưu bcrypt cũ với ID `{bcrypt-v1}`.
- Account `minh` đã lưu Argon2id với ID `{argon2-v58}`.
- Cùng raw password demo được dùng **chỉ để dễ đối chiếu**, không phải khuyến nghị dùng chung password trong sản phẩm thật.
- `DaoAuthenticationProvider` xác minh password thật, sau đó nâng hash cũ khi cần.
- Trường hợp password sai **không** nâng cấp hash.
- Hash không có prefix không được tự động chấp nhận; ví dụ chỉ chấp nhận khi được gắn **đúng ID sau kiểm định provenance**.
- Mã không in raw password, salt hoặc hash vào stdout.

### 7.1. Cấu trúc project

~~~text
password-migration-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/passwordmigration/
    └── PasswordMigrationDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'password-migration-demo'
~~~

`build.gradle`:

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
    implementation 'org.bouncycastle:bcprov-jdk18on:1.86'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.passwordmigration.PasswordMigrationDemo'
}
~~~

`Argon2PasswordEncoder` dùng Bouncy Castle trong Spring Security; việc khai báo dependency là bắt buộc để tránh lỗi runtime khi thực hiện Argon2. Các version ở đây dùng **để tái hiện demo**, không phải khuyến nghị đóng băng production ở các phiên bản này; sản phẩm phải áp dụng bản vá còn được hỗ trợ và kiểm tra BOM/dependency compatibility.

### 7.2. Tệp Java hoàn chỉnh

Lưu tại `src/main/java/example/passwordmigration/PasswordMigrationDemo.java`:

~~~java
package example.passwordmigration;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class PasswordMigrationDemo {

    // Kho in-memory mô phỏng database, lưu encoded hash nguyên vẹn.
    static final class Accounts
            implements UserDetailsService, UserDetailsPasswordService {

        private final Map<String, String> stored =
                new ConcurrentHashMap<>();
        private final AtomicInteger writes = new AtomicInteger();

        void seed(String username, String encodedHash) {
            stored.put(username, encodedHash);
        }

        String encodedOf(String username) {
            return stored.get(username);
        }

        int updateCount() {
            return writes.get();
        }

        @Override
        public UserDetails loadUserByUsername(String username)
                throws UsernameNotFoundException {

            String encoded = stored.get(username);
            if (encoded == null) {
                throw new UsernameNotFoundException("Account not found");
            }

            // Trả một UserDetails mới; không để ProviderManager
            // eraseCredentials tác động trực tiếp lên bản ghi stored.
            return User.withUsername(username)
                    .password(encoded)
                    .authorities("profile.read")
                    .build();
        }

        @Override
        public UserDetails updatePassword(
                UserDetails user, String newPassword) {

            // newPassword ĐÃ LÀ encoded hash do encoder tạo.
            // Không encode(newPassword) lần nữa.
            String username = user.getUsername();

            stored.compute(username, (key, currentHash) -> {
                if (currentHash == null) {
                    throw new InternalAuthenticationServiceException(
                            "Account disappeared during upgrade");
                }

                // Chặn ghi đè hash khi password đã được đổi
                // bởi một request đồng thời.
                if (!currentHash.equals(user.getPassword())) {
                    throw new InternalAuthenticationServiceException(
                            "Concurrent password change; retry login");
                }

                writes.incrementAndGet();
                return newPassword;
            });

            return loadUserByUsername(username);
        }
    }

    static boolean authenticates(
            AuthenticationManager manager,
            String username,
            String rawPassword) {

        try {
            Authentication request =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, rawPassword);
            Authentication result = manager.authenticate(request);
            return result.isAuthenticated();
        }
        catch (AuthenticationException failure) {
            // Không in raw credential hoặc chi tiết user.
            return false;
        }
    }

    public static void main(String[] args) {
        String demoRaw = "demo-pass-for-local-lab";

        PasswordEncoder legacy =
                new BCryptPasswordEncoder(10);
        PasswordEncoder current =
                Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();

        DelegatingPasswordEncoder encoder =
                new DelegatingPasswordEncoder(
                        "argon2-v58",
                        Map.of(
                                "bcrypt-v1", legacy,
                                "argon2-v58", current));

        Accounts accounts = new Accounts();
        accounts.seed("lan", "{bcrypt-v1}" + legacy.encode(demoRaw));
        accounts.seed("minh",
                "{argon2-v58}" + current.encode(demoRaw));

        System.out.println("old-prefix-before="
                + accounts.encodedOf("lan").startsWith("{bcrypt-v1}"));
        System.out.println("old-match-before="
                + encoder.matches(demoRaw, accounts.encodedOf("lan")));
        System.out.println("old-upgrade-before="
                + encoder.upgradeEncoding(accounts.encodedOf("lan")));

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(accounts);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(accounts);

        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        System.out.println("old-user-login="
                + authenticates(manager, "lan", demoRaw));
        System.out.println("new-prefix-after="
                + accounts.encodedOf("lan").startsWith("{argon2-v58}"));
        System.out.println("new-hash-matches="
                + encoder.matches(demoRaw, accounts.encodedOf("lan")));
        System.out.println("upgrade-after="
                + encoder.upgradeEncoding(accounts.encodedOf("lan")));
        System.out.println("writes-after-first="
                + accounts.updateCount());

        System.out.println("old-user-relogin="
                + authenticates(manager, "lan", demoRaw));
        System.out.println("writes-after-relogin="
                + accounts.updateCount());

        System.out.println("already-new-login="
                + authenticates(manager, "minh", demoRaw));
        System.out.println("writes-after-new-user="
                + accounts.updateCount());

        System.out.println("wrong-password="
                + authenticates(manager, "lan", "incorrect"));
        System.out.println("writes-after-wrong="
                + accounts.updateCount());

        // Mặc định: thiếu ID => fail-safe, không auto-guess.
        String untaggedBcrypt = legacy.encode(demoRaw);
        try {
            encoder.matches(demoRaw, untaggedBcrypt);
            System.out.println("untagged=UNEXPECTED_ACCEPT");
        }
        catch (IllegalArgumentException rejected) {
            System.out.println("untagged=REJECTED");
        }

        // Chỉ minh họa một bản ghi có provenance đã kiểm định.
        // Với DB thật, bổ sung prefix cần quy trình dữ liệu riêng.
        System.out.println("audited-legacy-match="
                + encoder.matches(
                        demoRaw, "{bcrypt-v1}" + untaggedBcrypt));

        System.out.println("new-registration-prefix="
                + encoder.encode("another-local-demo-password")
                        .startsWith("{argon2-v58}"));
    }
}
~~~

### 7.3. Chạy chương trình

Trong thư mục `password-migration-demo`, dùng JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

Nếu có Gradle Wrapper, dùng `./gradlew run --quiet` (trên Windows PowerShell: `.\gradlew.bat run --quiet`).

Các dòng do `System.out.println` tạo ra (không tính log Gradle/framework):

~~~text
old-prefix-before=true
old-match-before=true
old-upgrade-before=true
old-user-login=true
new-prefix-after=true
new-hash-matches=true
upgrade-after=false
writes-after-first=1
old-user-relogin=true
writes-after-relogin=1
already-new-login=true
writes-after-new-user=1
wrong-password=false
writes-after-wrong=1
untagged=REJECTED
audited-legacy-match=true
new-registration-prefix=true
~~~

**Vì sao những dòng này có thể dự đoán?**

1. `lan` ban đầu có ID `bcrypt-v1`; mapping cho phép `matches` kiểm đúng. Vì `idForEncode` là `argon2-v58`, `upgradeEncoding` trả `true` cho hash cũ.
2. `DaoAuthenticationProvider` xác minh mật khẩu, gọi `UserDetailsPasswordService.updatePassword` khi cần, nên hash của `lan` chuyển sang ID hiện tại và `updateCount=1`.
3. Re-login bằng hash hiện tại không cần rehash nữa, vì `Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()` báo hash có đủ memory/iterations theo preset.
4. `minh` đã dùng ID hiện tại nên login vẫn đúng, không tăng số update.
5. Mật khẩu sai bị từ chối, không được quyền ghi lại hash.
6. Hash bcrypt thiếu `{id}` bị từ chối theo mặc định; chỉ sau khi **kiểm định đúng nguồn thuật toán** và bổ sung ID trong ví dụ, `matches` mới có thể dùng encoder legacy.
7. Hash mới do `encoder.encode` có ID hiện tại. Salt ngẫu nhiên khiến **giá trị hash cụ thể** thay đổi giữa các lần chạy nhưng không làm thay đổi những kết quả boolean trên.

**Lưu ý về bản ghi in-memory:** demo dùng `Map.compute` và so sánh hash trước khi ghi để minh họa kiểu cập nhật có điều kiện. Với database thật, cần **giao dịch/compare-and-swap bằng WHERE version/hash**, xử lý lỗi trùng phiên và bảo đảm kết quả cập nhật phản ánh trạng thái đã commit. Mã console không thay thế repository production.

### 7.4. Vì sao cập nhật trong demo chỉ xảy ra sau khi xác thực?

`DaoAuthenticationProvider` được cấu hình bằng:

~~~java
DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider(accounts);
provider.setPasswordEncoder(encoder);
provider.setUserDetailsPasswordService(accounts);
~~~

Đây là điểm nối của ba hợp đồng:

- `UserDetailsService` đọc user và hash cũ.
- `PasswordEncoder` kiểm cũ / encode mới.
- `UserDetailsPasswordService` **ghi hash mới** và trả `UserDetails` mới cho provider.

Nếu bỏ `setUserDetailsPasswordService(accounts)`, `DaoAuthenticationProvider` vẫn có thể xác minh hash cũ qua delegating encoder, nhưng **không có đường ghi hash mới vào kho này**. Chỉ gọi `upgradeEncoding` từ code controller cũng không đủ; phải có thao tác ghi an toàn và kiểm chính sách account.

## 8. Cập nhật database thật: tránh race khi user reset password đồng thời

### 8.1. Vì sao không dùng UPDATE không điều kiện?

Một tình huống nguy hiểm:

~~~text
T1: User login password cũ; đã verify thành công trên hash A.
T2: User đổi password qua recovery; DB lưu hash B.
T1: Luồng rehash login chậm hoàn tất và ghi hash C của password cũ.
Kết quả: password mới bị ghi đè; password cũ lại có hiệu lực.
~~~

Nếu `UserDetailsPasswordService` chỉ thực hiện:

~~~java
// SAI nếu không có chính sách đồng bộ/race.
repository.updatePasswordByUsername(username, newEncodedHash);
~~~

thì rehash từ một lần login cũ có thể **ghi đè thay đổi credential mới**. Trong thực tế, việc này còn phụ thuộc isolation và update policy, nhưng không nên dựa vào may mắn về thứ tự request.

### 8.2. Dùng conditional update

Một cách minh họa ở SQL:

~~~sql
UPDATE accounts
SET password_hash = :new_encoded_hash,
    credential_version = credential_version + 1
WHERE user_id = :user_id
  AND credential_version = :expected_version
  AND password_hash = :old_encoded_hash;
~~~

Sau câu lệnh, phải kiểm số row được cập nhật:

- **1 row:** update phù hợp với snapshot đã xác minh (nếu giao dịch/điều kiện được triển khai đúng).
- **0 row:** credential/version đã thay đổi hoặc row đã bị xóa; **không tự cho login thành công bằng snapshot cũ nếu chính sách đòi trạng thái hiện tại**. Có thể yêu cầu người dùng gửi login lại với password mới.
- **Lỗi database:** giữ lỗi hạ tầng, không giả làm bad password hoặc âm thầm bỏ qua.

Đây là **SQL minh họa**, schema và syntax bind parameter tùy framework database. `UserDetailsPasswordService.updatePassword(user, newPassword)` chỉ nhận `UserDetails` và encoded hash; nếu cần version CAS, phải lấy version từ principal/domain model hoặc repository context thích hợp. Không mong API cung cấp sẵn cột `credential_version`.

### 8.3. Tránh cập nhật hai lần qua nhiều request

Khi nhiều request login cùng một user chạy đồng thời:

- Hai request cùng đọc hash A, cùng verify và cùng tính hash mới khác nhau do salt.
- Cả hai có thể muốn đổi A → B1/B2.
- Với CAS, chỉ một request đổi được A; request kia phát hiện version/hash không còn phù hợp.
- Thiết kế retry an toàn (thường yêu cầu xác thực lại bằng trạng thái hiện tại), không overwrite mù.

Với phiên đã đăng nhập hay token còn hạn, có thể có chính sách riêng. Rehash hash mật khẩu trong database không tự làm mới mọi `Authentication` trong session, cũng không tự thu hồi JWT và không bảo đảm user logout.

## 9. Hash legacy không có {id}: xử lý dựa trên provenance

Một lỗi kinh điển khi bật `DelegatingPasswordEncoder`:

~~~text
java.lang.IllegalArgumentException:
There is no PasswordEncoder mapped for the id "null"
~~~

Điều này xảy ra khi dữ liệu không có tiền tố `{id}` và encoder không có default matcher riêng. **Không phải bằng chứng người dùng nhập sai password**; đó là lỗi mapping/format cần được xử lý có kế hoạch.

### 9.1. Trường hợp xác minh được tất cả bản ghi đều là bcrypt

Nếu hệ thống cũ có **một cột chỉ chứa bcrypt hash** do một ứng dụng đã kiểm định tạo ra, có thể thực hiện migration dữ liệu **chỉ thêm prefix**:

~~~text
Trước: $2a$10$... (hash bcrypt hợp lệ, nguyên vẹn)
Sau:   {bcrypt-v1}$2a$10$... (giữ nguyên phần hash)
~~~

Không cần raw password cho **thao tác gắn metadata** này. Vì nội dung hash không đổi, phép verify bằng `BCryptPasswordEncoder` vẫn hoạt động. Nhưng **gắn prefix** không đồng nghĩa nâng cấp thuật toán hoặc tăng work factor; account vẫn dùng bcrypt cost cũ cho đến lần rehash tương lai.

Trước khi chạy batch, phải khảo sát **phân phối format thực tế** và nguồn gốc: có hash của user LDAP, plaintext lịch sử, SHA-1, giá trị NULL, record bị hỏng hay cột chứa format khác không? Không áp một prefix cho toàn bộ database chỉ vì vài mẫu đầu trông giống bcrypt.

### 9.2. Trường hợp nhiều thuật toán trộn nhưng thiếu ID

Cần có metadata ngoài hash, chẳng hạn version ứng dụng đã tạo record, hệ thống nguồn, tenant hoặc cột thuật toán đáng tin. Nếu không thể xác định chính xác hoặc không còn encoder an toàn tương ứng, chọn **quy trình reset mật khẩu có xác minh** thay vì thử mọi thuật toán và chấp nhận cái nào khớp.

Không dùng:

~~~java
// KHÔNG ÁP DỤNG: đoán lần lượt các encoder trên input không rõ format.
if (argon2.matches(raw, value)
        || bcrypt.matches(raw, value)
        || legacyNoOp.matches(raw, value)) {
    // ...
}
~~~

Một bộ matcher đoán mò không nhất thiết phân biệt được format mơ hồ, tăng rủi ro fallback, kéo theo encoder không an toàn và mở rộng đường tấn công.

### 9.3. Vì sao không thiết lập NoOp fallback?

`DelegatingPasswordEncoder.setDefaultPasswordEncoderForMatches(...)` cho phép thay matcher khi ID không được ánh xạ. Có những lộ trình migration legacy kiểm soát chặt dùng cơ chế đó, nhưng **không nên bật `NoOpPasswordEncoder` cho mọi hash thiếu ID**.

Điều này có thể khiến một chuỗi dữ liệu sai format được đối chiếu như plaintext, hoặc bị attacker khai thác nếu có đường ghi password_hash ngoài kiểm soát. Ưu tiên gắn đúng ID tại **dữ liệu đã kiểm định**, giữ decoder legacy trong một khoảng thời gian có quản trị, và reset các record không thể phân loại.

### 9.4. Nguyên tắc với ID không được map

| Format DB | Xử lý |
| --- | --- |
| `{argon2-v58}...` | Kiểm bằng encoder hiện tại |
| `{bcrypt-v1}...` | Kiểm bằng BCrypt legacy nếu policy cho phép, sau đó rehash |
| `{unknown}...` | Không tự chấp nhận; báo lỗi format/triage và chuyển sang recovery |
| Không `{id}`, provenance đã xác minh là bcrypt | Gắn ID tương ứng bằng migration dữ liệu có kiểm soát |
| Không `{id}`, không biết thuật toán | Không đoán tùy tiện; yêu cầu reset đã xác minh |
| Hash sai định dạng, cắt cụt hoặc trống | Fail closed; xử lý dữ liệu và recovery |
| Account chỉ dùng passkey/OIDC không có mật khẩu local | Không tự tạo một password hoặc giả lập hash; dùng cơ chế danh tính thực tế |

**Không lưu ID theo đầu vào do client lựa chọn.** Algorithm metadata phải do hệ thống tin cậy tạo/lưu. Nếu attacker có thể sửa `password_hash` hoặc ID ở DB, đây là vấn đề integrity/authorization của kho tài khoản và cần khắc phục riêng.

## 10. Quy trình rollout nhiều node không làm mất login

Trong hệ thống chạy nhiều pod/instance, deploy không đồng bộ có thể làm xuất hiện **hash mà một số node chưa biết verify**.

### 10.1. Kế hoạch ba pha: expand → switch writer → contract

~~~text
PHA 1 — EXPAND READERS
  - Mọi node hỗ trợ kiểm hash cũ và hash mới.
  - Encoder encode mới VẪN dùng ID cũ hoặc chưa đổi luồng ghi.
  - Chạy test login với các format đang tồn tại.
  - Bảo đảm DB column đủ dài, constraints/schema tương thích.

PHA 2 — SWITCH WRITERS
  - Khi toàn bộ reader đã hỗ trợ format mới:
      + đổi idForEncode sang thuật toán hiện tại;
      + bật UserDetailsPasswordService / rehash-on-login;
      + bắt đầu ghi hash mới khi đăng ký, reset và login thành công.
  - Theo dõi tốc độ migration, lỗi login, DB update và tài nguyên.

PHA 3 — CONTRACT
  - Chỉ khi không còn hash cũ cần hỗ trợ (hoặc đã có policy reset):
      + cân nhắc loại mapping legacy theo quy trình change management;
      + lưu kế hoạch phục hồi và kiểm các tài khoản hiếm đăng nhập;
      + không xóa decoder cũ khi vẫn còn dữ liệu cũ hợp lệ.
~~~

**Lưu ý về rollback:** Sau khi PHA 2 đã ghi hash Argon2, rollback về bản ứng dụng **chỉ biết BCrypt** có thể làm user mới/đã migrate không đăng nhập được. Bản rollback an toàn tối thiểu phải **vẫn hỗ trợ đọc/verify cả hai loại hash**, kể cả khi tạm tắt ghi Argon2 mới.

### 10.2. Cơ sở dữ liệu phải chứa được hash mới

Kiểm tra:
- Độ dài tối đa cột `password_hash`, tránh truncate encoded hash.
- Encoding/collation; hash gồm ký tự đặc biệt như `{ } $ / + =`, không được “normalize” khi lưu.
- Index: thông thường không cần index theo giá trị hash, nên không tạo những index tăng độ lộ và phí ghi.
- Kết cấu backup/replica/CDC/logging; hash không được gửi sang hệ thống phân tích không cần truy cập.
- Chức năng update password, import user, admin reset và sync IdP có cùng quy tắc format.

Cần integration test **round-trip database thật**: encode → persist → retrieve → matches. Một unit test in-memory có thể chạy xanh dù DB cột `VARCHAR(60)` âm thầm cắt hash Argon2 dài hơn.

### 10.3. Canary có dữ liệu cũ

Tài khoản test/canary nên đại diện cho:
- bcrypt cost thấp và cao;
- scrypt/PBKDF2/Argon2 preset cũ nếu có;
- hash có/không có ID trong scope đã kiểm định;
- user locked/disabled/expired;
- user có phiên còn hiệu lực;
- user concurrent login/change password.

Chỉ test tài khoản vừa đăng ký mới (luôn dùng hash mới) sẽ **không kiểm được tính tương thích ngược**.

## 11. Các luồng ghi password phải thống nhất policy

Một hệ thống thường có nhiều điểm tạo/đổi password:

| Luồng | Hash cần dùng | Lưu ý |
| --- | --- | --- |
| Đăng ký người dùng mới | Encoder hiện tại (`encode`) | Không gửi raw vào log/event |
| Người dùng đổi password | Encoder hiện tại | Xác minh bằng chứng thích hợp, xử lý session/token, rate limit |
| Quên mật khẩu và reset | Encoder hiện tại | Reset token một lần, TTL, invalidation, audit |
| Admin cấp lại mật khẩu tạm | Encoder hiện tại hoặc flow invitation không lộ raw | Bảo vệ kênh, buộc đổi khi cần |
| Login thành công với hash cũ | Chỉ rehash sau `matches` thành công và policy account hợp lệ | `UserDetailsPasswordService`/CAS |
| Import/migrate từ hệ thống cũ | Đọc đúng provenance, có thể giữ hash cũ kèm ID | Không được lấy hash đã băm làm raw input |
| OIDC/passkey account không có password local | Không tự tạo hash giả | Giữ đúng cơ chế xác thực của account |

**Sai lầm thường gặp:** đăng ký đã chuyển sang Argon2 nhưng reset-password service vẫn encode bcrypt hoặc tự lưu chuỗi plaintext. Một lựa chọn algorithm chỉ có giá trị nếu **mọi điểm ghi mật khẩu** cùng tuân thủ.

## 12. Khi nào nên buộc reset thay vì tiếp tục verify legacy?

Không phải dữ liệu cũ nào cũng nên tiếp tục được chấp nhận vô thời hạn.

**Có thể giữ verifier legacy trong cửa sổ quản trị:** hash bcrypt/PBKDF2/scrypt với tham số cũ nhưng hợp đồng còn rõ, không có sự cố compromise và cho phép login theo chính sách, sau đó rehash tức thời.

**Nên cân nhắc reset bắt buộc:** hash plaintext, MD5/SHA-1 không qua password KDF, format không thể xác minh nguồn, credential bị lộ, hash bị hỏng, hoặc risk/compliance không chấp nhận cơ chế cũ. Quy trình reset cần xác minh account bằng một kênh đáng tin, rate limit và tránh user enumeration.

Một hệ thống có hàng triệu account nhưng chỉ vài phần trăm login mỗi tháng có thể rất lâu mới migrate xong bằng login-only. Cần **định nghĩa tuổi thọ hỗ trợ legacy**, đặt cut-off hợp lý và chủ động gửi thông báo/luồng recovery an toàn cho account không còn đăng nhập thường xuyên.

Không đặt một cron job đọc hash cũ rồi tạo hash mới từ chính hash đó. Nếu không có raw password và không muốn chấp nhận verifier cũ, **reset là lựa chọn đúng**.

## 13. Cache, session, JWT và thay đổi quyền

Nâng hash là cập nhật **dữ liệu credential trong kho account**, không phải cập nhật toàn bộ trạng thái xác thực đã tồn tại.

### 13.1. UserDetails cache

Nếu provider hoặc `CachingUserDetailsService` cache `UserDetails`, sau khi `updatePassword` ghi hash mới phải đảm bảo cache không trả snapshot chứa hash cũ. Cần eviction đúng key sau commit và xử lý multi-node. Không mong `DaoAuthenticationProvider` tự evict mọi cache tùy chỉnh ngoài cấu hình.

Một cached `UserDetails` có thể bị tác động bởi `ProviderManager.eraseCredentials()` nếu chia sẻ cùng object principal. Thiết kế bản copy/erase và chính sách cache phù hợp; không tắt tính năng xóa credentials chỉ vì cache hỏng mà chưa đánh giá an toàn.

### 13.2. Session

Một lần login thành công với hash cũ có thể đồng thời rehash DB và tạo `Authentication` trong session. Không có yêu cầu bắt buộc phải logout ngay vì đổi **format hash**, nếu đó chỉ là upgrade minh bạch và policy cho phép. Ngược lại, reset password do nghi ngờ compromise có thể cần vô hiệu các session trước đó.

Đừng đồng nhất “nâng thuật toán” với “reset mật khẩu” hoặc “đổi quyền”. Chúng có mục tiêu nghiệp vụ khác nhau.

### 13.3. JWT và refresh token

JWT đã ký có claims và thời hạn riêng; đổi hash trong database không tự thay đổi JWT hiện hữu. Nếu nâng hash chỉ để tăng cost offline, có thể không cần thu hồi token. Nếu việc đổi mật khẩu đi kèm incident/credential compromise, cần xem xét token revocation, refresh-token rotation và yêu cầu đăng nhập lại.

## 14. Lập ngân sách CPU/RAM và bảo vệ endpoint login

Khi đổi từ bcrypt sang Argon2id hoặc tăng work factor, chi phí xác thực thành công lẫn thất bại có thể thay đổi đáng kể.

Một vài lưu ý:

- `Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()` dùng memory `1 << 14` KiB (**16 MiB**), iterations `2`, parallelism `1`, salt `16` byte và hash `32` byte.
- Đây là **bộ nhớ cấu hình của thuật toán cho một phép hash**, không phải số RSS/heap đo thực.
- Tám phép verify/rehash đồng thời với vùng làm việc Argon2 khoảng 16 MiB/phép có thể cần khoảng **128 MiB cho phần memory-hard work**, trước các overhead khác.
- Rehash-on-login có thể phát sinh **hai công việc đắt** trong cùng request: verify hash cũ rồi encode hash mới. Nếu không giới hạn, đợt mở rollout có nhiều account legacy có thể làm tăng latency/CPU/RAM.
- BCrypt cũ có CPU cost, Argon2 có thêm memory cost; không so trực tiếp độ an toàn chỉ bằng millisecond hoặc MiB từ các preset.

Các biện pháp vận hành: benchmark p50/p95/p99, peak heap/RSS/GC, giới hạn số KDF đồng thời, rate limit login và reset, queue hữu hạn, báo động OOM/timeout và thử dưới tải tương tự production. Không bỏ qua cost của encode trong bước upgrade.

### 14.1. Đo tác động nâng cấp khi lượng legacy lớn

Giả sử trong một phút có 200 lần login hợp lệ của user legacy:
- Mỗi login cần verify hash cũ.
- Nếu toàn bộ account chưa migrate, phần lớn request cũng cần encode hash mới và update DB.
- Các request này có thể tạo tải **cao hơn** bình thường, đặc biệt trong đợt rollout đầu tiên.

Một kỹ thuật thực tế là rollout theo tenant/cohort, canary và rate/concurrency budget. **Không ghi raw password vào hàng đợi để xử lý hash trong background**. Nếu không đủ tài nguyên nâng hash, cần thiết kế hành vi fail-safe/giảm tải theo chính sách, không trả success và giả vờ đã commit hash mới khi chưa cập nhật.

### 14.2. Kiểm soát độ dài password và DoS

Các hàm KDF chạy trên dữ liệu do client gửi; hệ thống nên có giới hạn kích thước request/credential hợp lý, xử lý normalization nếu policy quy định và rate limiting. Không trim/case-fold mật khẩu âm thầm khi migrate nếu dữ liệu cũ không làm vậy: cùng một chuỗi raw phải được xử lý nhất quán khi `matches` và `encode`.

Không nhận tham số cost/hash algorithm từ client cho phép hắn yêu cầu verification tiêu tốn tài nguyên tùy ý. Đọc metadata thuật toán từ hash đã lưu **sau khi kiểm soát integrity của kho dữ liệu**, đồng thời đặt giới hạn và chuẩn hóa cấu hình chấp nhận.

## 15. Kiểm thử bắt buộc: cũ vẫn vào được, mới đúng thuật toán

Một bộ test migration nên kiểm **cả chiều đọc và chiều ghi**:

| Test | Fixture | Kỳ vọng |
| --- | --- | --- |
| Login bằng bcrypt legacy | `{bcrypt-v1}...` đúng mật khẩu | Thành công; có thể nâng hash |
| Login bcrypt legacy sai mật khẩu | Hash cũ, password sai | Thất bại; **không ghi hash mới** |
| Login Argon2 hiện tại | `{argon2-v58}...` | Thành công; không tăng số rehash |
| Registration mới | `encode(raw)` | ID và tham số mới, `matches` đúng |
| Missing ID | Hash bcrypt không prefix | Fail-safe trước khi migration metadata |
| Audited prefix | Hash đã biết chắc là bcrypt và được gắn ID | `matches` đúng |
| Unknown ID | `{unrecognized}...` | Không tự đoán/noop; phát hiện config/data |
| Hash cắt cụt | Bản ghi DB có giới hạn cột sai | Không cho success, telemetry báo lỗi |
| Mixed algorithms | Bcrypt/scrypt/PBKDF2/Argon2 có ID đúng | Chỉ các format được policy cho phép mới verify |
| Param upgrade | Same ID, work factor cũ | `upgradeEncoding` phản ánh chính sách encoder nếu hỗ trợ |
| Rehash-on-login | `UserDetailsPasswordService` được gọi | Hash mới persisted, trả updated UserDetails |
| No updater | Không cấu hình password service | Verify cũ vẫn chạy, nhưng DB không tự nâng |
| Concurrent reset | Login đang nâng hash, recovery đã đổi password | Không ghi đè recovery; fail closed/CAS |
| Two app versions | Reader mới + writer cũ, rồi writer mới | Không node nào gặp hash không hỗ trợ |
| Rollback | Một phần data đã chuyển Argon2 | Rollback vẫn **đọc Argon2** |
| User rarely logs in | Hash cũ tồn tại sau cut-off | Recovery/reset an toàn |
| Account disabled/locked | Password đúng, account status không hợp lệ | Không tạo success chỉ vì hash được match |
| Session/JWT | Login trước/sau upgrade | Kiểm policy session/token riêng |
| Concurrency load | Nhiều login/rewrite cùng lúc | p95, memory, DB writes trong budget |
| Privacy | Logger/audit | Không lộ raw/hash, không tiết lộ tài khoản qua lỗi |

### 15.1. Test thực qua DaoAuthenticationProvider

Unit test chỉ gọi `encoder.matches` chứng minh logic hash/ID, nhưng chưa chứng minh quá trình rehash được tích hợp đúng provider. Bài demo ở mục 7 dùng `DaoAuthenticationProvider` và `UserDetailsPasswordService` thật để kiểm **một lần login → verify → upgrade → persist**.

Trong Spring Boot Servlet, nên bổ sung integration test đi qua `SecurityFilterChain` và authentication filter để phát hiện việc app đang vô tình dùng một `AuthenticationManager` khác với manager được cấu hình trong test. Với `@WithMockUser`, framework đặt user giả vào context nên không kiểm password hashing và rehash-on-login; không dùng một mình để kết luận migration đã đúng.

### 15.2. Kiểm dữ liệu trên database thật

Tối thiểu:
- Mọi format hash đang dùng có một fixture nguyên vẹn và được verify bằng encoder đúng.
- Schema không cắt prefix/salt/hash Argon2.
- Transaction/cas update trả đúng số row; không làm thay đổi username/authorities/status ngoài yêu cầu.
- Đổi mật khẩu đồng thời với rehash không bị ghi đè.
- Replication/cache không đọc/ghi hash sai sau commit.
- Monitoring đếm hash theo **ID hợp lệ** và rate rehash thất bại, không log hash nguyên vẹn.

### 15.3. So sánh thông điệp lỗi công khai

Một người nhập sai password ở hash cũ và hash mới nên nhận thông báo công khai tương đồng theo policy. Nếu thiếu ID/unknown ID là lỗi vận hành, không đưa nguyên message `IllegalArgumentException` cho client. Chỉ log mã nội bộ an toàn, không tiết lộ raw hash, username hay thuật toán cụ thể nếu điều đó giúp tấn công tài khoản.

## 16. Observability: biết mức độ migrate mà không thu thập bí mật

Nên đo những chỉ số tổng hợp:

- Số bản ghi theo `password_algorithm_id` (chỉ ID thuộc allowlist).
- Tỉ lệ login verify thành công/thất bại theo **nhóm hash legacy/current**.
- `password_rehash_attempted`, `password_rehash_succeeded`, `password_rehash_conflict`, `password_rehash_failed`.
- Latency `matches` và `encode` theo nhóm thuật toán, p95/p99 auth end-to-end.
- Concurrency hashing, heap/RSS, GC pauses và OOM/restarts.
- Số account không thể xác minh format (không log hash), số người cần recovery.
- Mức độ rollout: phần trăm reader đã hiểu ID mới, phần trăm writer tạo ID mới, tốc độ giảm hash legacy.
- Số sự kiện reset-password, có phân biệt rehash minh bạch với user thực sự đổi password.

Tránh đặt username/email/password hash vào nhãn metric: tạo cardinality lớn, tăng rủi ro lộ dữ liệu. Nếu cần audit theo account, dùng ID nội bộ với chính sách quyền truy cập/retention; không đẩy secret vào hệ thống quan sát.

**Số account đã migrate không thể được suy ra chỉ từ số login**: một account có thể login nhiều lần, hoặc hash có thể được nâng ngay trong quá trình đổi/reset mật khẩu. Thống kê từ DB có quyền truy cập hạn chế với query theo prefix/metadata đáng tin sẽ chính xác hơn.

## 17. Những lỗi thường gặp trong dự án thật

1. **Đổi trực tiếp `PasswordEncoder` sang Argon2 mà không giữ verifier bcrypt.** Dữ liệu cũ không đăng nhập được.
2. **Cho rằng BCrypt hash có thể “giải mã” rồi rehash hàng loạt.** Hash là một chiều; dùng login/recovery có xác minh.
3. **Gọi `encoder.encode(raw)` rồi so với stored hash.** Salt mới khiến so sánh chuỗi sai; dùng `matches`.
4. **Quên tiền tố `{id}` trong DB.** Delegating encoder không tự chọn đúng format.
5. **Gắn cùng ID cho mọi hash legacy không khảo sát.** Có thể map sai thuật toán hoặc làm hỏng account.
6. **Bật `NoOpPasswordEncoder` làm default matcher trên mọi record không ID.** Tạo đường tương thích yếu nguy hiểm.
7. **Giữ legacy mapping nhưng vẫn encode password mới bằng legacy ID.** Không đạt mục tiêu nâng cấp.
8. **Gọi `upgradeEncoding` rồi tưởng DB tự đổi.** Cần `UserDetailsPasswordService` hoặc luồng lưu tương ứng.
9. **Double-hash tham số `newPassword` của `updatePassword`.** API đã đưa hash mới, không phải raw.
10. **Rehash trước khi password cũ được xác thực.** Có thể thay hash từ input của attacker.
11. **Cập nhật hash mới không có CAS/version.** Rehash có thể ghi đè password reset đồng thời.
12. **Rollout writer mới trước khi mọi reader hỗ trợ ID mới.** Login ngẫu nhiên thất bại tùy node.
13. **Rollback về ứng dụng chỉ biết hash cũ.** Các account đã chuyển không thể đăng nhập.
14. **DB cột hash quá ngắn.** Truncate Argon2 string, tạo lỗi verify chỉ cho account mới.
15. **Quên đường đổi password của admin/batch/import.** Dữ liệu có nhiều format không dự đoán được.
16. **Tưởng đổi format hash tự thu hồi JWT/session.** Đây là hai lớp trạng thái khác nhau.
17. **Tăng memory cost nhưng không kiểm concurrency.** Có thể gây OOM và DoS endpoint login.
18. **Log encoded hash để debug mapping ID.** Hash là dữ liệu nhạy cảm, có giá trị khi database bị lộ.
19. **Thử mọi encoder theo thứ tự cho hash không rõ nguồn.** Tăng sự mơ hồ và nguy cơ fallback vào scheme yếu.
20. **Không quan tâm user hiếm đăng nhập.** Migration login-only có thể để hash yếu tồn tại nhiều năm.
21. **Không kiểm `UserDetailsService` cache và erasure behavior.** Snapshot cũ có thể chặn việc làm mới chính xác.
22. **Coi `upgradeEncoding=false` nghĩa an toàn tuyệt đối.** Nó chỉ phản ánh policy và triển khai cụ thể.
23. **Ép thuật toán mới theo bài blog mà không benchmark.** Có thể làm login chậm, nghẽn hoặc cạn bộ nhớ.
24. **Thay đổi normalization mật khẩu trong migration.** Một password cũ có thể không còn khớp dù người dùng nhập đúng.
25. **Đồng nhất nâng hash với đổi password:** nâng hash có thể giữ raw password hiện tại, không tự giải quyết việc password đã bị lộ hoặc quá yếu.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Hệ thống đổi sang Argon2, nhưng DB còn `{bcrypt}...`. `Argon2PasswordEncoder` đơn lẻ có xác minh trực tiếp hash bcrypt được không?  
**Đáp án:** Không. Cần `DelegatingPasswordEncoder`/provider phù hợp với mapping ID cũ cho bcrypt.

**Câu 2.** `idForEncode="argon2-v58"` nhưng map có bcrypt. Hash mới tạo bằng thuật toán nào?  
**Đáp án:** Argon2id theo encoder gắn với ID hiện tại; bcrypt chỉ để đọc/verify hash cũ trong map.

**Câu 3.** Một hash legacy không có ID nhưng đã chứng minh chắc chắn là bcrypt. Có thể gắn `{bcrypt-v1}` vào trước mà không biết raw password không?  
**Đáp án:** Có, vì đó là **bổ sung metadata**, không phải rehash. Phần bcrypt hash phải được giữ nguyên và đúng format.

**Câu 4.** Nếu không xác định được thuật toán legacy, có nên thử BCrypt, SHA-1, NoOp đến khi một loại khớp không?  
**Đáp án:** Không. Cần provenance đáng tin hoặc reset password có xác minh.

**Câu 5.** `matches` thành công với hash cũ, `upgradeEncoding` trả true. Hash tự đổi trong DB chưa?  
**Đáp án:** Chưa. Cần luồng ghi, như `DaoAuthenticationProvider` với `UserDetailsPasswordService` đã cấu hình.

**Câu 6.** Trong `UserDetailsPasswordService.updatePassword(user, newPassword)`, có được gọi `encoder.encode(newPassword)` thêm lần nữa không?  
**Đáp án:** Không ở luồng nâng hash chuẩn; `newPassword` đã là encoded hash mới.

**Câu 7.** Tại sao không rehash mọi account từ hash bcrypt hiện có bằng cách Argon2(bcryptHash)?  
**Đáp án:** Đầu ra không phải Argon2 của mật khẩu gốc, và không thể dùng raw password để verify theo hợp đồng cũ sau đó.

**Câu 8.** Tại sao cần cập nhật DB có điều kiện?  
**Đáp án:** Tránh một login rehash chậm ghi đè password mới vừa được reset/đổi bởi request khác.

**Câu 9.** Rollback ứng dụng sau khi có account đã được nâng hash Argon2 cần điều kiện gì?  
**Đáp án:** Phiên bản rollback vẫn phải biết verify hash Argon2 đang tồn tại; có thể tắt writer mới, nhưng không xóa reader mới.

**Câu 10.** Tại sao mapping ID cũ có thể giữ tạm dù không khuyến khích tạo hash mới bằng thuật toán đó?  
**Đáp án:** Để user có hash cũ vẫn đăng nhập theo policy, sau đó migrate; đường đọc legacy và đường ghi mới là hai chính sách khác nhau.

**Câu 11.** Mỗi lần login sau migration có phải rehash lại không?  
**Đáp án:** Không nhất thiết. Khi hash đã dùng ID và tham số hiện tại, `upgradeEncoding` thường trả false; không ghi lại nếu không cần.

**Câu 12.** Vì sao nâng hash theo login có thể tạo peak tài nguyên khi bắt đầu rollout?  
**Đáp án:** Một login với hash cũ cần verify và sau đó encode hash mới, thêm công việc CPU/RAM và DB write; cần benchmark/concurrency budget.

**Câu 13.** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` có tự chọn Argon2 để encode trong Spring Security 6.5 không?  
**Đáp án:** Không; factory mặc định dùng bcrypt làm encoder ghi mới ở dòng này dù có mapping Argon2 để đọc.

**Câu 14.** Đổi hash bcrypt → Argon2 có tự thu hồi access token đã phát hành không?  
**Đáp án:** Không. Session/JWT/refresh token có vòng đời và chính sách riêng.

**Câu 15.** Một account chỉ đăng nhập qua OIDC/passkey và không có local password cần xử lý ra sao?  
**Đáp án:** Không tự tạo password/hash giả; giữ đúng cơ chế login và metadata của user. Nếu về sau bật local password, cần enrollment có xác minh.

**Câu 16.** Một hash Argon2 mới verify được trên node A nhưng lỗi trên node B có thể do đâu?  
**Đáp án:** Node B chưa deploy reader/mapping ID mới, thiếu Bouncy Castle, version lệch, hash bị truncate hoặc cấu hình khác nhau. Cần kiểm lại rollout và dependency.

## 19. Checklist bàn giao migration

- [ ] Thống kê format và provenance của **từng tập tài khoản** (không chỉ vài record mẫu).
- [ ] Chọn thuật toán/params mới theo security policy, compliance và benchmark thực tế.
- [ ] Định nghĩa `idForEncode` hiện tại và toàn bộ ID reader cần hỗ trợ; tránh default plaintext fallback.
- [ ] Kiểm cả hash có prefix và không prefix, lỗi unknown ID và hash bị hỏng.
- [ ] Xác nhận DB column/charset/replication/backup giữ nguyên toàn bộ encoded string.
- [ ] Mọi instance reader nhận diện thuật toán mới **trước** khi writer bắt đầu ghi format mới.
- [ ] Đăng ký, reset, change password, admin và import dùng cùng quy tắc encode mới.
- [ ] `DaoAuthenticationProvider` dùng đúng `UserDetailsService`, `PasswordEncoder` và `UserDetailsPasswordService`.
- [ ] `UserDetailsPasswordService` chỉ lưu encoded hash đã nhận, không double-hash.
- [ ] Update DB theo transaction/version/CAS, không ghi đè password reset đồng thời.
- [ ] Chỉ rehash sau khi credential và account status đủ điều kiện xác thực.
- [ ] Không đưa raw password, token, hash hoặc salt vào logs/queues.
- [ ] Evict đúng `UserDetails` cache sau commit và xử lý nhiều node nếu có.
- [ ] Test cả legacy login và new login, wrong password, missing ID, unknown ID, truncated hash.
- [ ] Test fallback, password rotation đồng thời và các session/token đang tồn tại.
- [ ] Benchmark latency, CPU, memory, GC và concurrency dưới tải pha migrate.
- [ ] Có canary, metrics, threshold dừng rollout, rollback **tương thích đọc hash mới**.
- [ ] Định nghĩa thời hạn hỗ trợ legacy và recovery cho user hiếm login.
- [ ] Duy trì cập nhật thư viện, encoder và bản vá theo advisory chính thức.

**Ghi nhớ:** Nâng cấp thuật toán hash mật khẩu an toàn là quá trình **thêm khả năng đọc hash cũ, chuyển bộ mã hóa ghi mới, rồi dần chuyển dữ liệu khi người dùng đã chứng minh biết mật khẩu**. `DelegatingPasswordEncoder` giải quyết việc chọn encoder theo ID; `upgradeEncoding` cho biết cần nâng cấp; `DaoAuthenticationProvider` và `UserDetailsPasswordService` có thể thực hiện rehash trong luồng xác thực. Nhưng chính ứng dụng phải đảm bảo **không đoán hash không rõ nguồn, không ghi đè password mới, rollout đúng thứ tự và vẫn đủ tài nguyên**.

### Tài liệu tham khảo

- Spring Security 6.5 — Password Storage: https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html
- Spring Security 6.5 — `DelegatingPasswordEncoder` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html
- Spring Security 6.5 — `PasswordEncoderFactories`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/factory/PasswordEncoderFactories.html
- Spring Security 6.5 — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security 6.5 — `UserDetailsPasswordService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html
- Spring Security 6.5 — `Argon2PasswordEncoder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/argon2/Argon2PasswordEncoder.html
- Spring Security 6.5 — `BCryptPasswordEncoder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
