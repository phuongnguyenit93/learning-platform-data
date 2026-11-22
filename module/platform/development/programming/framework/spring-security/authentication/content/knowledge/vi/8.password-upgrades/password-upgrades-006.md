# Đổi mật khẩu, xác minh mật khẩu hiện tại và cập nhật dữ liệu nguyên tử

## Mục tiêu bài học

Đổi mật khẩu khi người dùng vẫn còn truy cập được tài khoản là một thao tác **nhạy cảm về bảo mật**. Không đủ để nhận `newPassword` rồi gọi `PasswordEncoder.encode(...)` và ghi đè cột `password_hash`: ứng dụng còn phải xác định **ai** được đổi, kiểm tra bằng chứng người đó **biết mật khẩu hiện tại** (hoặc một cơ chế tái xác thực tương đương được chính sách cho phép), kiểm tra mật khẩu mới, và cập nhật dữ liệu sao cho hai yêu cầu đồng thời không làm mất thay đổi của nhau.

Bài thuộc nhóm **Nâng cấp mật khẩu** trong module *Spring Security - authentication*. Trọng tâm là ba vấn đề gắn với nhau: **xác minh mật khẩu hiện tại**, **ghi hash mới theo cách nguyên tử**, và **nhất quán các dữ liệu liên quan**. Ví dụ chính dùng Java 17+, Spring Boot 3.x, Spring Security 6.x (`PasswordEncoder`) và Spring JDBC/H2. Ví dụ chạy dưới dạng chương trình dòng lệnh để thấy rõ logic transaction, không tự dựng một endpoint login thiếu CSRF/session protection.

Học xong, bạn sẽ biết:

1. Phân biệt **đổi mật khẩu** khi người dùng đang đăng nhập với **quên mật khẩu / reset** qua recovery token, và với **nâng cấp hash** tự động khi đăng nhập.
2. Lấy đúng account từ danh tính đã xác thực phía server, thay vì tin `username` do client gửi.
3. Xác minh `currentPassword` bằng `PasswordEncoder.matches(rawCurrent, storedHash)`, không so chuỗi hash và không lấy mật khẩu từ `Authentication.getCredentials()`.
4. Mã hóa `newPassword` bằng `PasswordEncoder.encode(rawNew)`, sau đó cập nhật hash và phiên bản credential bằng một câu SQL **compare-and-set**.
5. Dùng `@Transactional` để hash update và outbox/audit dữ liệu cùng commit hoặc cùng rollback, nhưng không tưởng nhầm transaction tự giải quyết lost update.
6. Giải thích hai yêu cầu đổi mật khẩu đồng thời, stale read, optimistic locking, row locking, transaction rollback và các điểm không nguyên tử như email hoặc thu hồi session ở hệ thống khác.
7. Chạy ví dụ H2 có đầu ra kiểm chứng được: mật khẩu hiện tại sai không làm đổi DB, mật khẩu đúng đổi thành công, hash cũ không còn khớp, version tăng đúng một lần, outbox chỉ thêm một event.

**Nguyên tắc cốt lõi:** luôn kiểm chứng mật khẩu hiện tại trên **hash đang có trong kho tài khoản**; ghi hash mới bằng một cập nhật có điều kiện bảo vệ chống ghi đè cạnh tranh; gắn các side effect thuộc DB vào cùng transaction; và có chính sách thu hồi phiên/token sau khi đổi.

## 1. Phân biệt ba luồng thường bị trộn lẫn

| Luồng | Người dùng chứng minh điều gì? | Nguồn xác minh | Hệ quả chính |
| --- | --- | --- | --- |
| **Đổi mật khẩu** khi đang đăng nhập | Có session/identity hợp lệ **và** biết password hiện tại (hoặc tái xác thực mạnh tương đương) | `PasswordEncoder.matches(current, stored)` + policy | Lưu hash mới, tăng credential version, xem xét thu hồi phiên |
| **Quên mật khẩu / reset** | Chứng minh quyền sở hữu bằng flow recovery hợp lệ khi không nhớ password | Reset token/OTP/passkey hoặc phương thức recovery được phép | Không yêu cầu biết password cũ; token recovery dùng một lần/ngắn hạn |
| **Nâng cấp hash khi login** | Password người dùng vừa nhập đã được provider xác minh thành công | `PasswordEncoder.upgradeEncoding(stored)`, `UserDetailsPasswordService` | Rehash cùng mật khẩu với cost/algorithm mới; không phải người dùng chủ động đổi password |

Những luồng này có thể cùng ghi vào một cột password hash, nhưng **quyền truy cập, bằng chứng xác thực và race condition khác nhau**. Không đưa một “mã đổi mật khẩu” chung cho cả ba rồi cho phép client chọn `skipCurrentPassword=true`.

### 1.1. Vì sao đăng nhập rồi vẫn nên yêu cầu current password?

Người dùng có thể quên đăng xuất trên máy dùng chung; session cookie có thể bị đánh cắp; một phiên đăng nhập rất lâu có thể không còn là bằng chứng đủ mạnh cho việc thay đổi credential. Vì vậy OWASP khuyến nghị **tái xác thực** trước những thay đổi nhạy cảm như mật khẩu hoặc email.

Người dùng đổi mật khẩu bình thường thường phải cung cấp `currentPassword`. Khi account đăng nhập hoàn toàn bằng passkey/SSO và không có password local, cần thiết kế một bước **step-up authentication** tương đương theo assurance policy; không giả rằng có thể kiểm tra một password không tồn tại.

**Không** lấy password hiện tại từ `Authentication.getCredentials()`. Spring Security có thể đã xóa credentials sau authentication; nhiều cơ chế (JWT, session, OAuth2) hoàn toàn không lưu raw password. Password hiện tại phải được **người dùng nhập lại qua kênh TLS** trong thao tác đổi hoặc được thay thế bằng cơ chế tái xác thực hợp lệ đã thiết kế.

### 1.2. Ai được đổi mật khẩu cho account nào?

Giả sử user Alice đã authenticated nhưng gửi request body:

~~~json
{
  "username": "bob",
  "currentPassword": "alice-current",
  "newPassword": "new-value"
}
~~~

Một endpoint `/me/password` **không được tin trường `username` này** để chọn account. Server phải lấy danh tính từ `Authentication.getName()`, một account ID đã được gắn vào principal đáng tin, hoặc kết quả của một bước tái xác thực; sau đó thay đổi **đúng credential của danh tính ấy**. Admin reset password cho người khác là một flow riêng, có authorization, audit và phương pháp recovery phù hợp; không biến endpoint tự phục vụ thành “đổi cho bất cứ username nào”.

Nếu ứng dụng đa tenant, chỉ username không nhất thiết đủ định danh user; nên dùng account ID ổn định đã được ánh xạ từ identity/tenant context đáng tin. **Không** tin `X-Tenant` hoặc `userId` do client tự khai báo để chỉ định row cần ghi.

## 2. Một quy trình đổi mật khẩu đúng

Quy trình ở mức nghiệp vụ:

~~~text
(1) User đã đăng nhập gọi hành động đổi mật khẩu qua HTTPS
        |
        v
(2) Server lấy account ID từ principal đáng tin;
    áp dụng authorization, CSRF, rate limit, step-up policy
        |
        v
(3) Tải hash hiện tại + credential_version + trạng thái account
        |
        +-- Account không còn hợp lệ? -> từ chối
        |
        v
(4) PasswordEncoder.matches(currentRaw, storedHash)
        |
        +-- false -> từ chối; KHÔNG ghi hash, không ghi audit success
        |
        v
(5) Kiểm tra policy cho newRaw:
    độ dài, mật khẩu bị lộ, reuse policy, confirmation nếu có
        |
        v
(6) PasswordEncoder.encode(newRaw)
        |
        v
(7) Atomic UPDATE ... WHERE id = ? AND version = ?
        |
        +-- 0 hàng -> stale/concurrent update; rollback, không ghi sự kiện thành công
        |
        v
(8) INSERT outbox/audit record vào cùng transaction DB
        |
        v
(9) Commit; chỉ sau commit mới là thay đổi thành công
        |
        v
(10) Thu hồi/điều chỉnh session và token, thông báo, quan sát
     theo kiến trúc; retry idempotent nếu side effects ngoài DB lỗi
~~~

Điểm dễ bỏ sót: nếu thao tác đang chạy trong transaction, bước `encode` có thể tương đối tốn CPU. Trong ví dụ học, ta đặt toàn flow vào một service `@Transactional` để quan sát rõ tính nhất quán. Trong production tải lớn, có thể **đọc và verify ngoài transaction**, sau đó dùng một transaction **ngắn** với conditional update + audit/outbox; nhưng phải giữ điều kiện phiên bản để chống dữ liệu thay đổi giữa lúc verify và commit, và kiểm tra lại policy trạng thái account thích hợp.

### 2.1. currentPassword phải được verify với hash đã lưu

Cách đúng:

~~~java
boolean correctCurrent = passwordEncoder.matches(
    currentPasswordFromRequest,
    passwordHashFromDatabase
);

if (!correctCurrent) {
    throw new CurrentPasswordRejectedException();
}
~~~

Đây là **fragment minh họa** trong service đã có biến và exception riêng; không phải file Java độc lập. Trong Spring Security, `matches(CharSequence rawPassword, String encodedPassword)` nhận raw ở tham số thứ nhất và **toàn bộ encoded string** ở tham số thứ hai. Nó đọc salt/cost cần thiết từ chuỗi hash đã lưu.

Hai cách sai phổ biến:

~~~java
// SAI: encode() với bcrypt tạo salt ngẫu nhiên mới.
boolean wrong = passwordEncoder.encode(currentPasswordFromRequest)
    .equals(passwordHashFromDatabase);

// SAI: lấy credentials từ Authentication và tưởng đó là password cũ.
Object guessedCurrent = authentication.getCredentials();
// Credentials có thể null/đã xóa hoặc là credential loại khác.
~~~

**Không** dùng `String.equals(rawCurrent, storedHash)`; raw password không phải hash. Không giải mã bcrypt, không log raw password/hash, không bật `NoOpPasswordEncoder` để “fix” login.

### 2.2. newPassword phải được encode một lần để lưu

Sau khi xác minh current password và qua policy:

~~~java
String newEncodedPassword =
    passwordEncoder.encode(newPasswordFromRequest);
~~~

Giữ **toàn bộ** giá trị `newEncodedPassword`, gồm salt/cost/algorithm prefix nếu encoder có. Với `BCryptPasswordEncoder`, cùng raw password được encode hai lần thường cho hash khác nhau; việc password có đổi hay không nên dựa trên policy và `matches(newRaw, oldStoredHash)` nếu cần cấm dùng lại password hiện tại, **không** dựa trên `newEncoded.equals(oldEncoded)`.

Nếu dùng `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, giá trị lưu thường có prefix kiểu `{bcrypt}...`; nếu dùng `BCryptPasswordEncoder` thuần thì là `$2a$...` hoặc biến thể tương ứng. Chỉ nên dùng encoder tương thích với định dạng trong database, không tự cắt prefix hay ép kiểu dữ liệu.

### 2.3. Xác nhận new password trong form có khác gì?

Trong UI có trường `newPassword` và `confirmNewPassword`. Đây là **hai raw field cùng request**, nên có thể so sánh trực tiếp để kiểm tra người dùng gõ trùng:

~~~java
if (!newPassword.equals(confirmNewPassword)) {
    throw new IllegalArgumentException("Confirmation mismatch");
}
String newEncoded = passwordEncoder.encode(newPassword);
~~~

Đây là fragment cho validation; không thay bước verify **current password**. Không encode hai field rồi so hai chuỗi encoded vì salt độc lập khiến chúng thường khác nhau dù người dùng gõ đúng.

## 3. “Nguyên tử” có nghĩa chính xác là gì?

Một phép đổi mật khẩu thành công phải chuyển hệ thống từ:

~~~text
Trước:
  account_id = 17
  password_hash = H_old
  credential_version = 8

Sau:
  account_id = 17
  password_hash = H_new
  credential_version = 9
~~~

Ta muốn **một trạng thái hoàn chỉnh**, không để DB có hash mới nhưng version cũ (hoặc ghi audit success nhưng hash không đổi). Cũng không muốn request cũ ghi đè một password mới hơn.

### 3.1. Ba khái niệm không đồng nghĩa

| Kỹ thuật | Giải quyết được | Không tự bảo đảm |
| --- | --- | --- |
| `@Transactional` cùng một DB | Một nhóm câu SQL commit/rollback cùng nhau | Không tự phát hiện read–modify–write bị cạnh tranh; không tự thu hồi JWT/email ngoài DB |
| SQL conditional update / compare-and-set | Chỉ cập nhật nếu row còn ở version dự kiến | Không tự bao gộp các câu INSERT audit khác nếu không có transaction |
| Row lock (`SELECT ... FOR UPDATE`) | Khóa row trong thời gian transaction theo database/isolation | Không thay policy xác thực và không khiến remote API/email thành atomic |

Một transaction **không phải phép màu chống lost update**. Ví dụ hai request cùng đọc hash/version 8, đều thấy current password đúng, rồi cả hai dùng `UPDATE accounts SET password_hash = ? WHERE id = 17` không có điều kiện version. Request sau có thể ghi đè thay đổi từ request trước; người dùng không biết mật khẩu nào cuối cùng có hiệu lực.

### 3.2. Dùng optimistic compare-and-set với version

Câu SQL quan trọng:

~~~sql
UPDATE account_credentials
SET password_hash = ?,
    version = version + 1
WHERE id = ?
  AND version = ?
  AND enabled = TRUE;
~~~

Các placeholder lần lượt là:

1. Hash mới được encoder tạo ra trên server.
2. Account ID ổn định từ hàng đã nạp.
3. Version vừa đọc trước lúc verify current password.

Nếu `updatedRows == 1`: đúng một hàng còn ở version dự kiến và đã được cập nhật (trước khi transaction commit). Nếu `updatedRows == 0`: dữ liệu thay đổi, account bị disable, hoặc account không còn tồn tại; **không được nói rằng đã đổi mật khẩu thành công**. Dùng lỗi conflict phù hợp và yêu cầu thao tác lại trên trạng thái mới.

Để bảo đảm condition vẫn chính xác, các đường thay password **khác** (reset qua recovery, admin change, self-service, migration credential) phải cùng tham gia quy ước tăng `version`. Nếu một đường update hash bỏ qua version, không thể mong CAS ở một đường khác phát hiện đầy đủ.

**Không dùng `newHash.equals(oldHash)` làm optimistic lock.** Salt ngẫu nhiên và định dạng hash không phải cơ chế version. Cũng không dựa vào timestamp có độ phân giải thấp nếu nhiều thay đổi có thể xảy ra trong cùng đơn vị thời gian; integer version rõ ràng và dễ kiểm thử.

### 3.3. Timeline hai yêu cầu đồng thời

~~~text
A: SELECT account #17, hash H8, version 8
B: SELECT account #17, hash H8, version 8

A: matches(current, H8) == true
B: matches(current, H8) == true

A: UPDATE ... WHERE id=17 AND version=8
   -> updatedRows=1, version trở thành 9
   -> COMMIT

B: UPDATE ... WHERE id=17 AND version=8
   -> updatedRows=0 vì version hiện đã là 9
   -> conflict/rollback

Kết quả: KHÔNG thể âm thầm ghi đè password do A vừa đặt.
~~~

Với database/isolation cụ thể, request B có thể phải **đợi lock**, bị deadlock/serialization failure hoặc thấy dữ liệu mới nếu đọc sau commit. Không bắt buộc luôn nhận chính xác `updatedRows=0` ở mọi kiểu giao tranh, nhưng ý nghĩa phải bảo toàn: **không được ghi đè và nhận thành công sai**. Thử lại từ bước xác minh hiện tại sau khi có conflict, không reuse blindly phiên bản/giá trị hash cũ.

### 3.4. Khi nào nên dùng SELECT FOR UPDATE?

Một lựa chọn khác là:

~~~sql
SELECT id, password_hash, version, enabled
FROM account_credentials
WHERE id = ?
FOR UPDATE;
~~~

Trong transaction, row lock khiến transaction khác chờ hoặc tranh chấp trước khi sửa. Nó hợp lý khi nhiều state phức tạp phải kiểm tra và thay đổi nhất quán, nhưng khiến lock được giữ trong lúc kiểm tra bcrypt/Argon2 (có thể tốn thời gian). Với đổi password, phương án **đọc rồi verify + CAS update version** thường dễ kiểm soát contention hơn. Không trộn `FOR UPDATE` với một giao dịch dài chứa email/network calls.

## 4. Ví dụ chạy đầy đủ: Spring Boot 3.x, JDBC, H2, BCrypt và transaction

Ví dụ này được thiết kế để có thể chạy bằng Maven trên Java 17+. Nó **không chạy web server**, chỉ dùng `CommandLineRunner` để thử các trường hợp; vì thế không cần mô phỏng cookie, CSRF hoặc status HTTP sai lệch. Lớp service tách riêng, được Spring quản lý để `@Transactional` thực sự chạy qua proxy.

Mục tiêu thực nghiệm:

- Alice có hash của password ban đầu và `version=0`.
- Đưa current password sai → bị từ chối, version vẫn `0`.
- Đưa current password đúng → hash mới được lưu, version thành `1`.
- Password cũ không còn khớp, password mới khớp.
- Có **một** event `PASSWORD_CHANGED` trong outbox cùng database.
- Cố đổi lần nữa bằng password cũ → bị từ chối, không thêm outbox event.

### 4.1. Tạo project và dependencies

Tạo project Maven từ Spring Initializr:

- Spring Boot **3.x**, Java **17 hoặc 21**.
- Group `com.example`, artifact `atomic-password-change`.
- Package `com.example.demo`.
- Chọn dependency **JDBC API / Spring JDBC** (`spring-boot-starter-jdbc`) và **H2 Database** (runtime).
- Thêm trực tiếp Spring Security Crypto vào `pom.xml` trong `dependencies`; Spring Boot parent/dependency management quản lý phiên bản:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-crypto</artifactId>
</dependency>
~~~

Ta không cần `spring-boot-starter-security` hoặc `spring-boot-starter-web` trong CLI này. `spring-security-crypto` cung cấp `PasswordEncoder`/`BCryptPasswordEncoder` mà không tạo HTTP security flow. Khi xây endpoint thật sẽ cần Spring Web/Security Starter và cấu hình bảo mật tương ứng.

Cây file:

~~~text
atomic-password-change/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── AtomicPasswordChangeApplication.java
    │   └── PasswordChangeService.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 4.2. Schema có credential version và transactional outbox

Tạo `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE account_credentials (
    id BIGINT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE credential_outbox (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES account_credentials(id)
);
~~~

`account_credentials.version` phải được tăng **cùng** hash trong UPDATE; nó không phải số phiên login hay số lần nhập sai. Trong production, có thể gọi là `credential_version` để phân biệt với version dùng cho profile hoặc trạng thái account.

`credential_outbox` là một bảng ghi sự kiện thay đổi credential **không chứa raw password hoặc hash**. Nó là ví dụ mô hình transactional outbox: ghi một sự kiện vào cùng DB transaction để một tiến trình khác có thể nhận và thực hiện thông báo/thu hồi token sau commit. Bản demo không triển khai worker tiêu thụ outbox.

### 4.3. Cấu hình DataSource H2

Tạo `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:password_change;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=embedded
~~~

H2 memory không có độ bền khi ứng dụng tắt; SQL chỉ dùng cho demo. Với Spring Boot và JDBC starter, `schema.sql` được áp dụng cho embedded database trước lúc `CommandLineRunner` chạy. Trên database production, dùng migration (Flyway/Liquibase) và connection pool/permissions/secret manager; không chạy `schema.sql` học tập lên dữ liệu thật.

### 4.4. Service @Transactional: verify current, CAS, outbox

Tạo file `src/main/java/com/example/demo/PasswordChangeService.java`:

~~~java
package com.example.demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PasswordChangeService {

    private final JdbcTemplate jdbc;
    private final PasswordEncoder encoder;

    public PasswordChangeService(
        JdbcTemplate jdbc,
        PasswordEncoder encoder
    ) {
        this.jdbc = jdbc;
        this.encoder = encoder;
    }

    // Ghi nhận giá trị đọc từ DB và dùng để compare-and-set.
    private record Credential(
        long id,
        String passwordHash,
        long version,
        boolean enabled
    ) { }

    public static final class InvalidCurrentPassword
            extends RuntimeException {
        public InvalidCurrentPassword() {
            super("Credential change rejected");
        }
    }

    public static final class InvalidNewPassword
            extends RuntimeException {
        public InvalidNewPassword() {
            super("New password rejected by policy");
        }
    }

    public static final class ConcurrentPasswordChange
            extends RuntimeException {
        public ConcurrentPasswordChange() {
            super("Credential changed concurrently");
        }
    }

    @Transactional
    public void changePassword(
        String authenticatedUsername,
        String currentPassword,
        String newPassword
    ) {
        if (authenticatedUsername == null
                || authenticatedUsername.isBlank()
                || currentPassword == null) {
            throw new InvalidCurrentPassword();
        }

        // Chính sách tối giản chỉ dành cho demo.
        if (newPassword == null
                || newPassword.length() < 12
                || newPassword.length() > 128) {
            throw new InvalidNewPassword();
        }

        Credential credential = jdbc.query(
            """
            SELECT id, password_hash, version, enabled
            FROM account_credentials
            WHERE username = ?
            """,
            rs -> {
                if (!rs.next()) {
                    return null;
                }
                return new Credential(
                    rs.getLong("id"),
                    rs.getString("password_hash"),
                    rs.getLong("version"),
                    rs.getBoolean("enabled")
                );
            },
            authenticatedUsername
        );

        if (credential == null
                || !credential.enabled()
                || !encoder.matches(
                    currentPassword, credential.passwordHash()
                )) {
            throw new InvalidCurrentPassword();
        }

        // Không dùng lại cùng mật khẩu hiện tại.
        if (encoder.matches(
            newPassword, credential.passwordHash()
        )) {
            throw new InvalidNewPassword();
        }

        String nextHash = encoder.encode(newPassword);

        int changed = jdbc.update(
            """
            UPDATE account_credentials
            SET password_hash = ?,
                version = version + 1
            WHERE id = ?
              AND version = ?
              AND enabled = TRUE
            """,
            nextHash,
            credential.id(),
            credential.version()
        );

        if (changed != 1) {
            throw new ConcurrentPasswordChange();
        }

        // Cùng DB transaction với UPDATE: không có event
        // thành công nếu thay đổi credential không commit.
        jdbc.update(
            """
            INSERT INTO credential_outbox(account_id, event_type)
            VALUES (?, ?)
            """,
            credential.id(),
            "PASSWORD_CHANGED"
        );
    }
}
~~~

**Giải thích từng lựa chọn quan trọng:**

- `authenticatedUsername` được đặt tên như vậy để nhắc rằng **caller phải truyền username từ danh tính đã xác thực của server**, không phải username do client tự chỉ định. Trong CLI, ta tự truyền chuỗi `alice` chỉ để mô phỏng.
- Trước khi đổi hash, service đọc đúng record hiện tại rồi dùng `encoder.matches(current, storedHash)`. Không có current password đúng → không sinh hash mới, không update.
- `enabled` được kiểm tra từ DB; trong UPDATE còn có điều kiện `enabled=TRUE`. Nếu account chuyển disabled trong lúc thao tác, conditional update bảo vệ một phần. Nếu policy yêu cầu bảo vệ mọi trạng thái khác, cần đưa chúng vào điều kiện và chiến lược version phù hợp.
- `newPassword.length()` kiểm tra **UTF-16 code units**, chỉ là giới hạn demo, không phải chính sách production hoàn chỉnh. Trong sản phẩm cần policy theo Unicode/byte, password bị lộ, tối đa payload để chống DoS, điều kiện reuse và hỗ trợ passphrase dài.
- `encoder.matches(new, oldHash)` được dùng để cấm chọn lại **chính mật khẩu hiện tại**; việc so hai chuỗi `encode` sẽ sai vì salt ngẫu nhiên.
- `UPDATE ... WHERE version = ?` là CAS: chỉ một request dùng phiên bản cũ được ghi thành công. `changed != 1` ném unchecked exception để rollback.
- `INSERT credential_outbox` được thực hiện sau update, **trong cùng transaction**, để commit/rollback cùng thay đổi password. Không đưa hash/raw password vào bảng sự kiện.
- Bean service được gọi từ **bean khác**, nên Spring transaction proxy có thể can thiệp. Nếu gọi `this.changePassword(...)` từ một phương thức khác trong chính object đó, `@Transactional` trong chế độ proxy mặc định có thể **không** tạo transaction.
- Nếu outbox INSERT thất bại, unchecked `DataAccessException` dẫn đến rollback cả UPDATE theo mặc định. Nếu một nghiệp vụ ném **checked exception** và muốn rollback, cần cấu hình quy tắc rollback, không giả mặc định checked exception sẽ rollback.

### 4.5. Main application, seed và thử các nhánh

Tạo file `src/main/java/com/example/demo/AtomicPasswordChangeApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class AtomicPasswordChangeApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            AtomicPasswordChangeApplication.class, args
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    CommandLineRunner demonstrate(
        JdbcTemplate jdbc,
        PasswordEncoder encoder,
        PasswordChangeService changes
    ) {
        return args -> {
            String oldPassword = "Initial-Password-2026!";
            String newPassword = "Future-Password-2027!";

            jdbc.update(
                """
                INSERT INTO account_credentials
                    (id, username, password_hash, enabled, version)
                VALUES (?, ?, ?, ?, ?)
                """,
                1L, "alice",
                encoder.encode(oldPassword),
                true, 0L
            );

            boolean badCurrentRejected = false;
            try {
                changes.changePassword(
                    "alice", "wrong-current", newPassword
                );
            }
            catch (PasswordChangeService.InvalidCurrentPassword ex) {
                badCurrentRejected = true;
            }

            Long versionAfterBad = jdbc.queryForObject(
                "SELECT version FROM account_credentials "
                    + "WHERE username = ?",
                Long.class,
                "alice"
            );

            changes.changePassword(
                "alice", oldPassword, newPassword
            );

            boolean oldCannotChangeAgain = false;
            try {
                changes.changePassword(
                    "alice", oldPassword, "Another-Password-2028!"
                );
            }
            catch (PasswordChangeService.InvalidCurrentPassword ex) {
                oldCannotChangeAgain = true;
            }

            String storedHash = jdbc.queryForObject(
                "SELECT password_hash FROM account_credentials "
                    + "WHERE username = ?",
                String.class,
                "alice"
            );

            Long newVersion = jdbc.queryForObject(
                "SELECT version FROM account_credentials "
                    + "WHERE username = ?",
                Long.class,
                "alice"
            );

            Integer eventCount = jdbc.queryForObject(
                "SELECT COUNT(*) FROM credential_outbox "
                    + "WHERE account_id = ?",
                Integer.class,
                1L
            );

            System.out.println("badCurrentRejected="
                + badCurrentRejected);
            System.out.println("versionAfterBad="
                + versionAfterBad);
            System.out.println("newPasswordMatches="
                + encoder.matches(newPassword, storedHash));
            System.out.println("oldPasswordRejected="
                + !encoder.matches(oldPassword, storedHash));
            System.out.println("versionAfterSuccess="
                + newVersion);
            System.out.println("outboxEvents="
                + eventCount);
            System.out.println("oldCannotChangeAgain="
                + oldCannotChangeAgain);
        };
    }
}
~~~

Spring Boot khởi tạo DataSource H2 từ `application.properties`, chạy `schema.sql`, sau đó chạy `CommandLineRunner`. Các lời gọi `changes.changePassword(...)` từ runner sang service là **external bean calls**, nhờ đó `@Transactional` được áp dụng khi transaction manager đã được auto-configure bởi JDBC starter.

Trong demo, cost BCrypt 10 chỉ nhằm giảm thời gian học; bản triển khai thật phải chọn thông số hash phù hợp qua benchmark/khuyến nghị bảo mật. Chuỗi mật khẩu demo được hardcode để dễ chạy, **không được dùng trong production**, và code không in raw password hoặc hash.

### 4.6. Cách chạy và output kỳ vọng

Trong thư mục chứa `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Ngoài log Spring Boot, các dòng **do `CommandLineRunner` in ra** là:

~~~text
badCurrentRejected=true
versionAfterBad=0
newPasswordMatches=true
oldPasswordRejected=true
versionAfterSuccess=1
outboxEvents=1
oldCannotChangeAgain=true
~~~

Đây là kết quả logic ổn định của chương trình, không phụ thuộc chuỗi hash BCrypt cụ thể (salt được sinh ngẫu nhiên). Nếu tự in `storedHash` để học trên máy thử, giá trị sẽ thay đổi giữa những lần chạy; **không log hash khi vận hành thật**.

Ý nghĩa:

1. `badCurrentRejected=true`: service từ chối mật khẩu hiện tại sai.
2. `versionAfterBad=0`: nhánh thất bại không ghi đè password.
3. `newPasswordMatches=true`: hash trong DB khớp mật khẩu mới.
4. `oldPasswordRejected=true`: hash mới không còn chấp nhận mật khẩu cũ.
5. `versionAfterSuccess=1`: một lần đổi thành công tăng version đúng một đơn vị.
6. `outboxEvents=1`: sự kiện success chỉ được ghi một lần, cùng transaction với update.
7. `oldCannotChangeAgain=true`: sau khi đổi, người dùng không thể dùng mật khẩu cũ để thay đổi thêm lần nữa.

**Giới hạn:** ví dụ không chạy hai thread đồng thời, không tự triển khai invalidation session/token và không mô phỏng lỗi H2 commit. Thuộc tính **atomic CAS** đến từ câu SQL điều kiện version; muốn chứng minh ở production cần thêm concurrency integration test với database engine/isolation thực tế.

## 5. Kiểm tra tính nguyên tử: những ca test bắt buộc

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Current password sai | Không đổi hash; version giữ nguyên; không có outbox success |
| Account không tồn tại hoặc bị disabled | Không đổi DB; public response không tiết lộ chi tiết account |
| New password vi phạm policy | Không đổi hash/version; trả lỗi policy có kiểm soát |
| New password trùng password hiện tại | Từ chối theo chính sách ví dụ; không ghi DB |
| Current đúng, new hợp lệ | Một UPDATE thành công; version +1; outbox có một event |
| Hai request cùng đọc version `v` | Tối đa một request commit đổi từ `v` sang `v+1`; request kia stale/conflict hoặc lỗi concurrency; không silent overwrite |
| Outbox INSERT thất bại | Rollback transaction: hash/version quay lại trạng thái cũ |
| Reset password đồng thời với self-service change | Cùng quy ước version phải ngăn stale update ghi đè reset |
| Account bị disable giữa read và update | Điều kiện status/version phải khiến cập nhật sai policy thất bại |
| DB transaction commit rồi email gửi lỗi | Hash **đã đổi**; outbox cần retry; không tự nói DB rollback |
| Gọi phương thức `@Transactional` bằng `this.method()` | Test để phát hiện thiếu proxy và transaction không được áp dụng |
| Retry sau network timeout không biết commit hay chưa | Phải đọc trạng thái mới / dùng idempotency policy; không blind retry với version cũ |

### 5.1. Test tính toàn vẹn của outbox

Một cách test là chủ động làm `INSERT credential_outbox` thất bại trong **database test độc lập**, rồi đọc lại `password_hash` và `version` sau khi transaction kết thúc. Vì code ném unchecked exception từ Spring JDBC, transaction manager mặc định sẽ rollback. Không tạo trigger phá schema production để thử.

Nếu test theo cách đó không rollback được, cần kiểm tra:

- Service có thực sự được tạo bởi Spring dưới proxy `@Transactional`?
- Có gọi qua bean khác hay đang self-invocation?
- `JdbcTemplate` ghi password và outbox có dùng **cùng DataSource và transaction manager**?
- Có đoạn code đã catch exception và không rethrow hoặc không mark rollback?
- Có query/driver không tham gia transaction hoặc DDL tự commit?
- Quy tắc rollback có bị thay bởi `noRollbackFor`/transaction configuration không?

`@Transactional` không đảm bảo 2PC cho nhiều database hoặc email service; ví dụ chọn **cùng một DB** để bảo đảm atomic commit giữa hash và outbox.

### 5.2. Test đồng thời mà không phụ thuộc thứ tự thread

Trong integration test, tạo hai thao tác đổi mật khẩu cùng dùng current password cũ nhưng chọn **hai mật khẩu mới khác nhau**. Dùng barrier/latch để chúng có cơ hội đọc cùng version, rồi giải phóng cùng lúc; hoặc inject một test seam sau read nếu cần tái hiện chắc chắn.

Assert những điều **bất biến** thay vì assert thread A thắng:

- Version từ `v` chỉ tăng lên `v+1` cho **một** thay đổi hợp lệ.
- Hash cuối cùng khớp **một trong hai** mật khẩu mới, không bị ghi hai lần âm thầm từ cùng version.
- Có **một** event success cho version đó.
- Transaction thua nhận conflict, re-authentication failure hoặc một concurrency exception tương đương, **không** trả success sai.
- Retry phải đọc/version và xác minh lại current password; không tự dùng các giá trị snapshot cũ.

Với database isolation/driver cụ thể, losing transaction có thể gặp lock timeout/deadlock/serialization failure thay vì `updatedRows=0`; ứng dụng nên ánh xạ nhóm lỗi cạnh tranh sang hành vi API phù hợp, không ghi thêm side effects.

## 6. Cần chú ý gì khi biến service thành HTTP endpoint?

Service demo **không có HTTP**, còn một API thực tế phải nhận request có authenticated identity, yêu cầu current password và áp dụng các bảo vệ web.

Một controller **minh họa, không phải file runnable độc lập** khi chưa cấu hình Spring Web/Spring Security/filter chain:

~~~java
record ChangePasswordRequest(
    String currentPassword,
    String newPassword
) { }

@PostMapping("/me/password")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void changePassword(
    Authentication authentication,
    @RequestBody ChangePasswordRequest request
) {
    // /me/password phải được SecurityFilterChain bảo vệ.
    // authentication lấy từ Spring Security, KHÔNG từ body.
    changes.changePassword(
        authentication.getName(),
        request.currentPassword(),
        request.newPassword()
    );
}
~~~

Ở đây cần Spring MVC/Security imports, inject `PasswordChangeService changes`, cấu hình endpoint `/me/password` yêu cầu `authenticated()`, và một exception handler phù hợp. Nếu principal mang ID nội bộ, ưu tiên dùng ID đó, nhất là khi username có thể đổi hoặc trùng giữa tenant.

**Không** đặt API thực tế là `POST /users/{id}/password` rồi chỉ kiểm tra user đã đăng nhập mà không kiểm tra ID/path thuộc chính họ, trừ một flow admin được authorization riêng. Đây là lỗi **IDOR/BOLA**.

### 6.1. Authentication khác “vừa xác thực lại”

Một cookie session được tạo từ hôm qua có thể vẫn là `authenticated()`. Điều đó **không** thay xác minh current password cho thao tác nhạy cảm. Service phải thực hiện `matches` với hash hiện hành ngay tại thao tác đổi, hoặc sử dụng cơ chế step-up phù hợp có giới hạn thời gian/chính sách rõ ràng.

Nếu client dùng JWT/SSO và local account **không có password**, không được cho phép caller nhập chuỗi bất kỳ rồi bỏ qua kiểm tra; phải xác định provider và cơ chế tái xác thực của issuer, hoặc hướng dẫn luồng quản lý credential ở IdP. Đừng tự lưu/đổi password local cho một account mà chỉ IdP quản lý mà không có quy trình được ủy quyền.

### 6.2. CSRF, CORS, SameSite và TLS

Khi ứng dụng dựa vào **cookie/session** hoặc browser tự gửi Basic credentials, endpoint đổi mật khẩu dạng POST phải được bảo vệ khỏi **CSRF**. Bước nhập current password tăng độ tin cậy nhưng **không** thay thế tất cả biện pháp chống CSRF. Với Spring Security Servlet, hãy giữ cơ chế CSRF phù hợp cho trình duyệt và triển khai đúng token/cookie/session flow; không tắt `csrf` chỉ để curl demo chạy.

CORS chỉ kiểm soát đọc/khởi tạo một số loại request từ browser, **không phải thay thế CSRF**. `SameSite` của cookie là lớp hỗ trợ, không nên được coi là lớp duy nhất. Mọi mật khẩu trong request phải đi qua **HTTPS**, không đưa vào URL/query string hay server logs, và nên dùng response `Cache-Control: no-store` cho nội dung nhạy cảm.

### 6.3. HTTP error mapping có kiểm soát

| Lỗi | Cách xử lý API có thể chọn |
| --- | --- |
| Không có authentication hoặc phiên hết hạn | `401 Unauthorized`, yêu cầu đăng nhập |
| User đã xác thực nhưng không được phép thao tác | `403 Forbidden` |
| Current password không khớp | `400` hoặc `403` theo contract; thông điệp không rò dữ liệu |
| New password không đạt policy | `400` với policy errors đã chuẩn hóa |
| Concurrent change / stale version | `409 Conflict` hoặc contract retry phù hợp |
| Thành công | `204 No Content` hoặc `200` không chứa raw/hash |
| Lỗi hạ tầng DB/outbox | `5xx`/retry policy, không trả success trước commit |

Đây là **gợi ý API contract**, không phải Spring Security tự động ánh xạ các exception custom thành các status đó. Không suy đoán user tồn tại hay account bị disable từ thông điệp công khai. Tất cả nhánh lỗi phải không để hash/transaction ở trạng thái nửa vời.

## 7. Transaction nguyên tử không đồng nghĩa với thu hồi phiên tức thì

Đổi password trong database thành công **không tự động vô hiệu hóa** mọi session cookie, remember-me token, refresh token và JWT access token đã cấp trước đó. `SecurityContext` của phiên cũ có thể còn chứa `Authentication` hợp lệ; resource server dùng JWT có thể chỉ kiểm tra chữ ký, thời hạn, issuer và scopes.

Nên xác định policy:

1. Có giữ phiên hiện tại nhưng yêu cầu login lại ở các phiên khác, hay logout **tất cả** phiên?
2. Session store là in-memory một node hay phân tán? Có cách lấy và hủy mọi session theo account ID không?
3. Remember-me persistent token, refresh token, OAuth2 authorization và access token được thu hồi thế nào?
4. Nếu dùng stateless JWT, cần TTL ngắn, token revocation list, introspection hay so sánh `credential_version` trong token với account hiện hành?
5. Nếu event không gửi được ngay, tài nguyên nhạy cảm có chấp nhận một cửa sổ eventual consistency không?
6. Sau change/reset, notification qua kênh đã đăng ký có cần gửi không? Không đưa new password hoặc hash vào email.

### 7.1. Phân biệt atomicity của DB với side effects ngoài DB

Một transaction SQL **không thể rollback email đã gửi**, HTTP request đến IdP, hay một session đã xóa trong Redis khác nếu không có cơ chế phân tán phù hợp.

Sai lầm:

~~~text
BEGIN DB TRANSACTION
  UPDATE password
  call email service
  invalidate Redis sessions
COMMIT DB
~~~

Nếu gọi email thành công rồi COMMIT DB thất bại, user nhận thông báo đổi mật khẩu nhưng hash vẫn cũ. Nếu đã xóa session trước commit rồi transaction rollback, user bị logout mà không đổi được password. Kết quả không nguyên tử xuyên hệ thống.

Thiết kế **transactional outbox** trong ví dụ:

~~~text
Trong transaction của cùng một DB:
  UPDATE account_credentials ... CAS
  INSERT credential_outbox(..., 'PASSWORD_CHANGED')
COMMIT

Sau commit, một worker/outbox relay:
  đọc event
  -> gửi thông báo
  -> thu hồi session/token theo policy
  -> retry nếu hạ tầng lỗi
  -> đánh dấu event đã xử lý, idempotent
~~~

Outbox giải quyết bài toán **không đánh mất ý định side effect** khi DB đã commit, nhưng **không biến mọi tác động ngoài DB thành nguyên tử hoặc tức thời**. Nếu yêu cầu thu hồi credential không được trễ dù chỉ một request, kiến trúc kiểm tra access token/session phải có cơ chế version hoặc state check cưỡng chế đồng bộ theo SLA, không chỉ dựa vào email/event bất đồng bộ.

### 7.2. Password change và password reset khác nhau về phiên

Với **quên mật khẩu/reset**, người dùng có thể không đăng nhập; cần token recovery có entropy phù hợp, TTL, single-use, rate limit và verification chính xác. OWASP khuyến nghị xem xét hoặc tự động vô hiệu hóa các phiên hiện có và **không tự động đăng nhập user** sau reset nếu không có lý do bảo mật rõ ràng.

Với **đổi mật khẩu khi đã đăng nhập**, có thể giữ phiên hiện tại sau step-up hoặc yêu cầu đăng nhập lại; điều này phụ thuộc rủi ro, policy và sản phẩm. Nhưng các phiên khác bị thu hồi/không thu hồi phải là quyết định có chủ đích và được kiểm thử, không “tự xảy ra” chỉ nhờ `password_hash` thay đổi.

## 8. Vai trò của UserDetailsManager và UserDetailsPasswordService

Hai interface rất dễ nhầm:

| Thành phần | Contract | Dùng trong trường hợp |
| --- | --- | --- |
| `UserDetailsService` | `loadUserByUsername(...)` để tải account | Xác thực username/password qua provider |
| `UserDetailsManager` | Mở rộng service với CRUD và `changePassword(oldPassword, newPassword)` | Quản lý user/password nếu implementation đáp ứng policy |
| `UserDetailsPasswordService` | `updatePassword(UserDetails user, String newPassword)`, nhận password **đã encode** | Hỗ trợ nâng hash do provider khởi động sau authentication thành công |
| `PasswordEncoder` | `encode(raw)`, `matches(raw,encoded)`, `upgradeEncoding(encoded)` | Hash/verify/migration |
| Domain `PasswordChangeService` trong demo | Verify current, áp policy, CAS version và outbox | Tự phục vụ đổi password với điều kiện nhất quán riêng của ứng dụng |

Theo JavaDoc Spring Security 6.5, `UserDetailsManager.changePassword(String oldPassword, String newPassword)` nhằm sửa mật khẩu của user hiện hành trong kho bền vững; oldPassword dùng để **re-authentication nếu implementation yêu cầu**. **Không được suy luận chỉ từ interface** rằng mọi implementation đều verify old password, cập nhật cùng transaction, có optimistic locking hay thu hồi session. Cần đọc implementation và test trên schema/provider thực tế.

`UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)` có thể dùng cùng `DaoAuthenticationProvider` khi nâng password **encoding** sau một lần login thành công, thường bằng `provider.setUserDetailsPasswordService(...)`. Đây không phải là endpoint đổi mật khẩu chủ động có input `currentPassword`/`newPassword` cho user. Tên `newPassword` của API này thường đại diện **giá trị đã mã hóa** và việc update cần được thiết kế đúng.

### 8.1. Đổi password không phải chỉ “nâng cost”

Ví dụ user đang dùng raw `P`, stored hash có bcrypt cost 10:

- **Hash upgrade:** sau khi provider verify `P` thành công, tạo một hash khác của **cùng `P`** với cost cao hơn và lưu lại có version/race control.
- **User change:** user cung cấp current `P` và new `Q`, server verify `P` rồi lưu hash của **`Q`**.
- **Forgot password reset:** user không nhất thiết biết `P`; họ chứng minh quyền sở hữu bằng recovery token rồi đặt `Q`.

Các flow có thể chạm cùng credential version. Một reset hoặc hash-upgrade đồng thời không được phép âm thầm ghi đè password-change thành công; dùng chung quy ước CAS và conflict resolution phù hợp.

## 9. Sai lầm triển khai và cách chẩn đoán

| Hiện tượng | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Ai có session cũng đổi được mà không biết current password | Thiếu step-up/re-authentication | Yêu cầu current password hoặc factor tương đương |
| Đổi password cho ID do client gửi | IDOR/BOLA | Lấy account ID từ principal/tenant đáng tin và authorization |
| Verify bằng `encode(raw).equals(storedHash)` | Salt khiến hash mới khác hash cũ | Dùng `matches(raw,storedHash)` |
| So raw password với stored hash | Hai định dạng khác nhau | Dùng đúng `PasswordEncoder` |
| Password hiện tại lấy từ `Authentication.getCredentials()` | Credentials có thể bị xóa hoặc không phải raw password | Yêu cầu nhập lại qua bước step-up |
| Hai request đổi mật khẩu đều báo OK, chỉ một password dùng được | Lost update, không có CAS/version | UPDATE có điều kiện version, kiểm tra affected rows |
| Có `@Transactional` mà vẫn lost update | Transaction không tự bảo vệ stale read | CAS hoặc locking/isolation phù hợp |
| Có `@Transactional` nhưng outbox không rollback | Self-invocation, sai transaction manager/DataSource, catch exception | Gọi qua Spring bean proxy, dùng cùng DB transaction, test rollback |
| Thay password thành công nhưng audit thiếu | Audit không nằm trong transaction hoặc sự cố viết audit không được kiểm tra | Ghi transactional outbox/audit cùng DB |
| Notification đã gửi dù DB rollback | Gọi remote service trước commit | Outbox + after-commit relay, idempotent retry |
| Đổi password nhưng session khác vẫn chạy | Session/token chưa bị thu hồi | Xây revocation policy cho các loại credential |
| User change dùng username không kèm tenant | Tra nhầm account | Stable account ID và tenant context đã xác minh |
| Mật khẩu mới trùng mật khẩu cũ vẫn được lưu | Không có reuse policy | Dùng `matches(newRaw, oldStoredHash)` để ngăn reuse hiện tại |
| Đổi encoder làm hash cũ không verify | Sai bcrypt/delegating/legacy format | Migration format có kiểm soát, test trước rollout |
| Người dùng báo đổi thất bại nhưng hash đã đổi | Timeout sau commit, retry không rõ trạng thái | Thiết kế error/idempotency và recovery, đọc trạng thái |
| Password xuất hiện trong log/outbox | Thiết kế telemetry không an toàn | Không log/hash đưa vào event; quản lý secret nghiêm ngặt |

### 9.1. Những trường hợp dữ liệu cần cân nhắc

**Hash đã bị migrate:** cột có thể chứa `{bcrypt}$2a$...` (delegating) hoặc `$2a$...` (bcrypt thuần). Encoder phải khớp format trong DB. Nếu chỉ so chuỗi khi đổi password, một hash có salt/cost khác dù password không đổi vẫn gây hiểu sai.

**Account status:** bản demo kiểm tra `enabled`. Hệ thống thật có thể có `locked`, `accountExpired`, `credentialsExpired`, `suspended` và policy MFA. Đừng chỉ check enabled rồi bỏ qua các trạng thái khác trong flow đổi credential.

**Multiple credential stores:** một account có thể có local password, IdP password, API key hoặc passkey. Phải xác định rõ **credential nào** đang được đổi; không viết hash mới vào kho local nếu user xác thực hoàn toàn bằng SSO và không có password local hợp lệ.

**Credential re-use history:** nhiều sản phẩm yêu cầu không được dùng lại N mật khẩu gần nhất. Vì salt ngẫu nhiên, không thể so chuỗi hash để phát hiện reuse. Phải kiểm tra `PasswordEncoder.matches(newRaw, historicalEncodedHash)` trên tập hash lịch sử có kiểm soát hoặc áp policy khác, cân bằng CPU/DoS và data retention; không lưu password raw để so.

**Unicode/normalization:** không tự `trim()`, lowercase hoặc sửa dấu tiếng Việt ở một đầu của registration/change/login. Password có thể chứa khoảng trắng. Nếu policy yêu cầu chuẩn hóa, phải nhất quán và có kế hoạch migration. `String.length()` là UTF-16 code units, không phải byte hoặc Unicode grapheme count.

**Bcrypt work factor:** hash mới có salt mới và cost hiện tại. Cost cao tăng CPU latency của verify/encode; transaction có thể giữ connection trong lúc bcrypt tính toán. Test dưới concurrency và cân nhắc rút ngắn transaction, bảo vệ login/change-password bằng rate limiting.

## 10. Bài tập và đáp án

**Bài 1 — Sai current password.** Service đã đọc `version=4`, người dùng nhập current sai. Có nên sinh new hash rồi update trước khi trả lỗi để không lộ timing không?

**Đáp án:** không. Không cập nhật account khi chưa verify current. Nếu cần bảo vệ timing, áp dụng cơ chế an toàn được kiểm định, tránh thay credential khi xác thực thất bại.

**Bài 2 — Hai update không có version.** A và B cùng đọc hash cũ. A lưu hash `A-new`, B lưu `B-new`. Cả hai update trả 1 hàng. Có thể gọi hai request đều “thành công” theo policy không?

**Đáp án:** không nếu policy yêu cầu không được ghi đè cạnh tranh. Phải dùng CAS/version hoặc row lock phù hợp; kiểm tra affected rows và kiểm soát side effects.

**Bài 3 — CAS trả 0 hàng.** Đã verify current trước đó nhưng `UPDATE ... WHERE version=?` cập nhật 0 hàng. Có nên tiếp tục INSERT outbox “PASSWORD_CHANGED” rồi trả 204 không?

**Đáp án:** không. Đó là conflict hoặc trạng thái đã đổi; rollback, không phát success, yêu cầu caller xác minh lại với trạng thái mới.

**Bài 4 — Hash mới và audit có hai bảng trong một DB.** Transaction commit cả hai hay rollback cả hai được không?

**Đáp án:** có nếu cùng transaction manager/DataSource và cả hai câu SQL thực sự nằm trong transaction. `@Transactional` không bảo đảm email/Redis bên ngoài đồng bộ cùng commit.

**Bài 5 — Email gửi lỗi sau commit.** Hash đã đổi, outbox có event. Có nên rollback DB?

**Đáp án:** không thể đơn giản rollback một transaction đã commit. Worker retry từ outbox, idempotent; xem xét policy thông báo và revocation trong thời gian chờ.

**Bài 6 — User có JWT hợp lệ, không có password local.** Có được bỏ qua current password rồi cho client ghi bất cứ `newPassword` nào?

**Đáp án:** không. Phải xác định flow được ủy quyền để tạo/đổi local credential và bước step-up tương đương; JWT bearer thông thường không chứng minh user biết password hiện tại.

**Bài 7 — Dùng `UserDetailsManager.changePassword(old,new)`.** Có thể khẳng định luôn có optimistic locking và rollback outbox không?

**Đáp án:** không. Giao diện không quy định các thuộc tính triển khai đó. Kiểm tra provider/manager cụ thể và test trên DB thực tế.

**Bài 8 — Chỉ đổi hash trong DB.** Một session cũ còn chứa authenticated principal, JWT còn hạn. Có chắc bị từ chối request mới không?

**Đáp án:** không. Cần chính sách vô hiệu hóa session, refresh token, remember-me và JWT/token version phù hợp.

**Bài 9 — Gọi service qua `this.changePassword(...)`.** Tại sao `@Transactional` có thể không hoạt động?

**Đáp án:** ở proxy mode mặc định, self-invocation không đi qua Spring proxy nên interceptor transaction không chạy. Gọi service qua bean được Spring quản lý, test rollback.

**Bài 10 — Có password confirm field.** Nên so hai raw fields hay encode rồi so hai hash?

**Đáp án:** so raw values trong validation của cùng request, sau đó chỉ encode mật khẩu mới khi policy và current verification đã đạt. Hai hash bcrypt có salt riêng nên không thể dùng `equals` để xác nhận form.

## 11. Checklist thiết kế trước khi triển khai

- [ ] Endpoint change chỉ dành cho danh tính đã authenticated; account ID lấy từ principal/tenant context đáng tin.
- [ ] Xác minh current password bằng `PasswordEncoder.matches(currentRaw, storedEncoded)` hoặc step-up equivalent đã được policy cho phép.
- [ ] Không dùng `Authentication.getCredentials()` như nguồn mặc định của current password; không tạo authenticated token thủ công để bỏ qua kiểm tra.
- [ ] Xác thực policy mật khẩu mới (độ dài, breach check, Unicode, reuse, giới hạn payload) trước khi lưu.
- [ ] Dùng `encode(newRaw)` một lần để lưu toàn bộ hash; không băm hash cũ và không so hai kết quả `encode`.
- [ ] Có cột `credential_version` hoặc concurrency guard tương đương, đồng bộ giữa change/reset/admin/migration.
- [ ] Dùng SQL `UPDATE ... WHERE id=? AND version=?`, kiểm tra số hàng cập nhật và xử lý conflict/rollback.
- [ ] Các thay đổi DB đi kèm (outbox/audit/version) cùng transaction và được test rollback khi lỗi.
- [ ] Không nghĩ transaction tự bao trùm email, Redis, IdP; dùng outbox và retry idempotent cho side effects sau commit.
- [ ] Bảo vệ endpoint bằng HTTPS, CSRF với browser cookie, rate limits, authorization, reauthentication/MFA khi cần.
- [ ] Có chính sách rõ ràng cho logout sessions, remember-me, refresh token và access JWT sau password change/reset.
- [ ] Không ghi raw password/hash/pepper/token vào log, audit event, email, URL hoặc response.
- [ ] Đã thử current sai/đúng, new invalid/reuse, account disabled, cùng lúc hai change, rollback outbox, stale version, lỗi DB và token cũ.
- [ ] Đã benchmark cost encoder, lock/transaction duration và retry behavior trên cùng database engine/isolation như production.
- [ ] Có phương án vận hành khi request timeout sau commit và client không biết đã đổi thành công hay chưa.

**Kết luận:** đổi mật khẩu an toàn không chỉ là `passwordEncoder.encode(newPassword)`. Bước quan trọng là **xác minh mật khẩu hiện tại từ hash đáng tin**, sau đó **cập nhật hash mới bằng conditional SQL bảo vệ version** và dùng **transaction** để đồng bộ credential cùng outbox/audit trong DB. Như vậy, current sai không đổi dữ liệu, request cạnh tranh không âm thầm ghi đè, và sự kiện được ghi đúng khi transaction commit. Thu hồi session/token và thông báo sau commit là bài toán riêng cần policy, cơ chế xử lý lỗi và kiểm thử đầy đủ.

## Tài liệu tham khảo

- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — PasswordEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security 6.5 — UserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/UserDetailsManager.html)
- [Spring Security 6.5 — UserDetailsPasswordService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction Rollback Rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [OWASP — Authentication Cheat Sheet: Change Password Feature](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
