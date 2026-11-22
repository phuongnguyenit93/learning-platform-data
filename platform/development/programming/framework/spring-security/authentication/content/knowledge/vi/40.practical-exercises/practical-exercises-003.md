# Nâng cấp giá trị băm mật khẩu mà không yêu cầu mọi người dùng đặt lại cùng lúc

> **Thực hành tổng hợp — Spring Security Authentication (Java 17+, Spring Boot 3.x / Spring Security 6.x).** Khi một ứng dụng đã lưu hàng trăm nghìn password hashes bằng thuật toán hoặc work factor cũ, không nhất thiết phải yêu cầu toàn bộ người dùng thay mật khẩu trong một ngày. Có thể thực hiện **lazy rehash**: tiếp tục xác minh các hash cũ được nhận diện rõ, rồi ngay khi người dùng đăng nhập bằng password đúng, dùng password vừa được xác minh để tạo hash theo chính sách mới và lưu lại bằng cập nhật nguyên tử. Cơ chế này giảm gián đoạn nhưng phải có kế hoạch cho tài khoản không hoạt động, bảo vệ khỏi race với password reset và bảo đảm các phiên bản ứng dụng đều đọc được hash mới.

## 1. Hiểu đúng yêu cầu

Có ba vấn đề phải giải cùng lúc:

1. **Bảo mật:** Hash mới dùng thuật toán thích hợp và chi phí đã benchmark; hash cũ không được dùng để ghi credential mới.
2. **Trải nghiệm người dùng:** User đăng nhập đúng như bình thường, không phải tất cả reset đồng loạt.
3. **Tính nhất quán:** Password change/reset cùng lúc với lazy rehash không được làm password cũ có hiệu lực lại; rollout/rollback không khiến các node khác nhau chấp nhận những định dạng khác nhau.

Một password hash là kết quả **một chiều**. Không có phép tính đáng tin nào biến `hash_old(password)` thành `hash_new(password)` mà không có password gốc. Chạy `bcrypt(oldHash)` cho mọi hàng chỉ tạo hash của chuỗi hash cũ, **không phải** hash của password người dùng đã đặt; nếu không thiết kế verifier khác hoàn toàn, họ sẽ không đăng nhập được.

Vì vậy quy trình đúng là:

~~~text
User gửi password tới server qua TLS
  -> Tải password hash và account status hiện hành
  -> Verify password với thuật toán/parameters của hash đó
  -> Sai: từ chối, KHÔNG đổi hash
  -> Đúng: xem hash có cần nâng cấp không
            |
            +-- Không: hoàn tất xác thực theo policy
            |
            +-- Có: encode(password vừa verified) theo scheme mới
                    -> CAS update stored hash/version
                    -> reload/return UserDetails mới
                    -> hoàn tất xác thực nếu account/MFA vẫn hợp lệ
~~~

**Lazy** nghĩa là chỉ nâng khi người dùng cung cấp password đúng. Không có password được lưu tạm trong queue/job hay lấy từ log. **Rehash** nghĩa là tạo lại hash từ password raw vừa được kiểm chứng, **không** là thay label hoặc mã hóa lại digest cũ.

## 2. Tại sao phải nâng cấp thuật toán hoặc work factor?

Hash phù hợp để lưu mật khẩu cần chống thử đoán ngoại tuyến sau khi database bị lộ. SHA-256/MD5/SHA-1 thuần tính quá nhanh; attacker có thể thử nhiều mật khẩu mỗi giây. Thuật toán mật khẩu hiện đại như Argon2id, bcrypt hoặc PBKDF2 có tham số chi phí (CPU, bộ nhớ, số vòng) và salt riêng cho mỗi hash.

| Thành phần | Ý nghĩa | Lưu ý migration |
| --- | --- | --- |
| Algorithm | bcrypt, Argon2id, PBKDF2 hoặc legacy cũ | Verifier phải chọn chính xác thuật toán của từng record |
| Unique salt | Giá trị ngẫu nhiên riêng cho mỗi hash | Thường có trong chuỗi hash, không phải secret |
| Work factor | bcrypt cost, PBKDF2 iterations, Argon2 memory/time | Phiên bản mới có thể tăng tham số |
| Password hash format | Layout lưu salt/parameters/digest | Không tự cắt ngắn hoặc thay đổi encoding |
| `{id}` | Nhãn định tuyến encoder trong Spring | Cho phép cùng tồn tại nhiều format |
| Pepper | Secret giữ bên ngoài DB nếu threat model đòi hỏi | Có kế hoạch KMS rotation; không tự trộn sai scheme |
| Credential version | Version tăng mỗi khi đổi hash/secret | Chống ghi đè khi login và reset chạy đua |
| PasswordEncoder | Component `encode`, `matches`, `upgradeEncoding` | Dùng đúng API, không tự ghép hash thủ công |

**Hash có salt không cần có hai chuỗi giống nhau cho cùng password.** Hai lần bcrypt/Argon2 encode password giống nhau thường tạo hash khác vì salt mới. `matches(raw, storedHash)` mới là phép so sánh đúng.

Chọn work factor phải dựa vào hướng dẫn OWASP, môi trường chạy, độ nhạy tài khoản, yêu cầu compliance và **benchmark p95/p99 dưới tải thực**. Tăng cost quá cao dễ bị khai thác làm CPU/memory exhaustion khi có credential stuffing. Cần rate limit/bulkhead trước password verification.

## 3. Các kiểu migration thường gặp

| Trường hợp | Hash cũ | Hash đích | Cách chuyển |
| --- | --- | --- | --- |
| Tăng cost bcrypt | bcrypt cost 10 | bcrypt cost 12 | `matches` hash cũ, `upgradeEncoding`, encode từ password vừa nhập |
| Thay scheme | PBKDF2 định dạng cũ | Argon2id hoặc bcrypt mới | `DelegatingPasswordEncoder` ánh xạ cả hai theo ID |
| Gắn nhãn format | Chuỗi bcrypt `$2a$...` thiếu prefix | `{bcrypt}$2a$...` | Metadata-only prefix update sau khi kiểm chứng |
| Thay pepper | Có key/pepper cũ | Pepper mới ở KMS | Verify được cũ rồi nâng trên login; inactive accounts cần kế hoạch |
| Legacy SHA-256 không salt | SHA-256 digest | Adaptive KDF mới | Chỉ verify đúng định dạng legacy trong transition, rehash ngay khi login đúng |
| SSO/LDAP | Password tại IdP/directory | Không có hash local | Không thể tự migration ở app; nguồn sở hữu credential phải xử lý |

**Metadata-only prefix update khác cryptographic upgrade.** Thêm `{bcrypt}` vào một bcrypt hash sẵn có chỉ giúp Spring chọn verifier; cost của hash vẫn như cũ. Phải thực hiện lazy rehash sau đó mới tăng bảo vệ.

Nếu legacy không xác định được salt, pepper, encoding hoặc layout, **không nên đoán thuật toán**. Một số tài khoản sẽ cần reset/re-enrollment an toàn; mục tiêu là tránh reset đồng loạt, không hứa rằng không một người nào cần reset.

## 4. Điều kiện thành công và các bất biến

Một kế hoạch migration đạt yêu cầu khi:

- Hash cũ được **đọc và verify** chỉ khi scheme được phép và đã biết chính xác.
- Tất cả **đăng ký/đổi/reset password mới** đều ghi bằng encoder hiện hành.
- Password sai, unknown user, disabled/locked account hoặc lỗi LDAP/DB **không** tạo hash mới.
- User có hash cũ login đúng -> hash mới được ghi vào DB **chỉ với đúng account/version/hash**.
- Hai lần login đồng thời không thể ghi đè lần password reset, không mở lại disabled account.
- Khi hash đã ở cost/algorithm mới, lần login sau **không phải rehash mãi**.
- Node ở các region/phiên bản được triển khai biết verify **cả hash cũ và hash mới** trong giai đoạn rolling deployment.
- Có metrics theo scheme, migration progress, CAS conflicts, login error, CPU và kế hoạch loại bỏ legacy.
- Hash/password không được xuất hiện trong logs, metrics labels, events, tickets hoặc queues.

Không chỉ kiểm thử “đăng nhập thành công” rồi coi là hoàn tất; phải **đọc lại DB** và chứng minh lần login sau verify được hash mới, **không có cách vô tình chấp nhận password cũ sau reset**.

## 5. Kiểm kê dữ liệu và thiết kế cột trước khi ghi

Không cần biết password gốc để thống kê:

- Số account theo thuật toán/prefix và work factor; số record malformed/không rõ format.
- Mỗi record có local password hay chỉ dùng LDAP/OIDC/passkey.
- Bao nhiêu account có hash cũ nhưng ít hoạt động hoặc vô hiệu hóa.
- Độ dài hash hiện tại, độ dài hash đích, character set và collation.
- Password/credential version, account status, tenant ID ổn định, hash last-upgraded timestamp.
- Pepper/key cũ còn được giữ và truy cập đúng policy không.
- Những write paths ngoài form login: API login, reset, admin, mobile, batch provisioning.

**Không dump plaintext hoặc stored hashes ra logging.** Có thể thống kê `scheme=PBKDF2_V1`, `cost_bucket=low`, số lượng/tuổi nhóm tài khoản, nhưng không đưa raw hash/email vào Prometheus labels.

### Schema gợi ý

~~~sql
CREATE TABLE account_credentials (
    account_id          VARCHAR(64) PRIMARY KEY,
    tenant_id           VARCHAR(64) NOT NULL,
    password_hash       VARCHAR(512),
    credential_version  BIGINT NOT NULL DEFAULT 0,
    account_status      VARCHAR(32) NOT NULL,
    password_updated_at TIMESTAMP WITH TIME ZONE,
    hash_upgraded_at    TIMESTAMP WITH TIME ZONE
);
~~~

SQL trên là **schema minh họa kiểu PostgreSQL**; dự án thực tế phải có unique constraints/foreign keys, nullable policy và định nghĩa account status phù hợp. Dùng kiểu cột đủ dài cho hash đích, không để DB âm thầm truncate, không thay đổi case của base64 hoặc prefix. Hash string phải được lưu và đọc lại **nguyên văn**.

Với nhiều tenant, một account ID có thể chỉ unique trong tenant; khi update phải dùng cặp `(tenant_id, account_id)`. Tên đăng nhập/email do browser gửi **không** đủ làm khóa update password; dùng stable ID được repository xác định.

## 6. Cách Spring Security nhận diện nhiều hash bằng DelegatingPasswordEncoder

`DelegatingPasswordEncoder` dùng định dạng:

~~~text
{id}encodedPassword

{bcrypt}$2a$10$...         -> bcrypt cost 10
{bcrypt}$2a$12$...         -> bcrypt cost 12
{pbkdf2-v1}...             -> verifier PBKDF2 cũ
{argon2id-v2}...           -> verifier Argon2id mới
~~~

`idForEncode` quyết định thuật toán **ghi mới**; map `id -> PasswordEncoder` quyết định thuật toán **đọc/xác minh**. Khi dữ liệu cũ có `id` khác current id, `upgradeEncoding` có thể trả true. Khi cùng ID nhưng work factor thấp hơn, encoder tương ứng có thể yêu cầu upgrade.

### Cấu hình Spring Security 6 minh họa: tăng bcrypt cost

~~~java
package example.migration;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordEncodingConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // 12 là ví dụ, không phải mức cost tối ưu cho mọi hệ thống.
        return new DelegatingPasswordEncoder(
                "bcrypt",
                Map.of("bcrypt", new BCryptPasswordEncoder(12)));
    }
}
~~~

Với một record `{bcrypt}$2a$10$...`, encoder dùng bcrypt để verify password. Khi user nhập đúng, `upgradeEncoding` nhận thấy cost cũ thấp hơn cấu hình mới và có thể yêu cầu rehash. Hash mới sử dụng cost hiện hành và một salt mới, vẫn có prefix `{bcrypt}`.

**Cấu hình trên KHÔNG hỗ trợ** một record `$2a$10$...` không có `{bcrypt}` hoặc một `{pbkdf2-v1}` chưa được map. Khi migrate nhiều thuật toán, phải có verifier v1 chính xác (bao gồm salt layout, pepper, iterations, Unicode policy), không chỉ thêm một ID rồi dùng sai factory mặc định.

### Sai lầm: fallback tùy tiện cho unknown ID

Mặc định `DelegatingPasswordEncoder` báo lỗi khi thiếu prefix/ID không được ánh xạ. Có thể cấu hình `setDefaultPasswordEncoderForMatches`, nhưng fallback rộng, đặc biệt `NoOpPasswordEncoder` hoặc “thử mọi thuật toán”, có nguy cơ mở đường xác thực không mong muốn. Tốt hơn là:

1. Kiểm chứng và gắn nhãn legacy theo DB metadata/format có kiểm soát.
2. Chỉ đăng ký verifier cũ đã xác định.
3. Unknown hash ID: fail closed, alert và đưa account tới recovery nếu không thể nhận diện.
4. Không tự chấp nhận plaintext password lưu trong DB dưới bất kỳ ID tùy ý nào.

## 7. Hai con đường upgrade trong Spring

Các API chính:

~~~java
String encode(CharSequence rawPassword);
boolean matches(CharSequence rawPassword, String storedHash);
boolean upgradeEncoding(String storedHash);
~~~

`PasswordEncoder.matches(...)` **chứng minh** password vừa nhập đúng với encoded password hiện tại. `PasswordEncoder.upgradeEncoding(...)` chỉ **quyết định** hash đó cần rehash; nó không tự ghi DB. `encode(rawPassword)` sinh hash mới từ raw password đang được xác minh.

`DaoAuthenticationProvider` có thể sử dụng hai cấu hình sau:

~~~java
provider.setPasswordEncoder(encoder);
provider.setUserDetailsPasswordService(passwordService);
~~~

`UserDetailsPasswordService.updatePassword(UserDetails user, String newPassword)` nhận **newPassword đã encode**, phải thay hash trong persistent store và trả `UserDetails` đã cập nhật.

**Điểm dễ bị bỏ quên:** Nếu developer chỉ tăng `BCryptPasswordEncoder` từ cost 10 lên 12 nhưng không cấu hình `UserDetailsPasswordService`, provider vẫn có thể verify hash cost 10 **mãi** mà không ghi hash mới. Cần test chứng minh DB thật sự thay đổi. Nếu cấu hình custom `AuthenticationProvider`/JSON login ngoài `DaoAuthenticationProvider`, logic tự động này có thể không được gọi.

## 8. Luồng xác thực và rehash trong ứng dụng web

~~~text
POST /login qua TLS
   |
   +-- CSRF (nếu browser form), rate limit, session safeguards
   |
   v
AuthenticationManager -> DaoAuthenticationProvider
   |
   +-- UserDetailsService đọc account + version + storedHash
   |
   +-- Kiểm tra account status: enabled, locked, expired
   |
   +-- PasswordEncoder.matches(raw, storedHash)
           |-- false -> BAD_CREDENTIALS; KHÔNG rehash
           |
           +-- true -> check upgradeEncoding(storedHash)
                             |-- false -> normal authentication
                             |
                             +-- true:
                                   newHash = encode(raw)
                                   UserDetailsPasswordService.updatePassword(
                                        user, newHash)
                                   DB CAS oldHash/version -> newHash
                                   return updated UserDetails
   |
   +-- MFA nếu có, session persistence, success handling
~~~

Không truyền password vào `AuthenticationSuccessHandler` hay event listener chỉ để rehash. Spring có thể đã xóa credentials khỏi Authentication; handler không phải chỗ giữ secret. Không log hoặc cache password để rehash sau trong background.

**MFA:** Provider password thành công có thể nâng cấp hash **trước** khi hoàn tất TOTP/WebAuthn trong một flow nhiều yếu tố. Điều này **không** chứng minh MFA thành công hoặc cho phép cấp full session. Nếu sản phẩm muốn rehash chỉ sau MFA, phải thiết kế flow khác với trust boundary và password lifecycle rõ ràng, tuyệt đối không cất plaintext trong session.

## 9. CAS: tuyệt đối không để lazy upgrade ghi đè password reset

Vấn đề khó nhất là một lần xác thực có snapshot cũ:

~~~text
10:00:00 Login A đọc hash=H_old, credential_version=7
10:00:01 Password reset B ghi hash=H_reset, version=8
10:00:02 Login A verify password cũ đúng với H_old
10:00:03 Login A rehash password cũ -> H_upgraded_old
10:00:04 UPDATE account SET hash=H_upgraded_old WHERE account_id=A
Kết quả sai: password cũ được phục hồi dù user đã reset thành công!
~~~

**Không dùng** unconditional update theo account ID. Dùng compare-and-swap trong một transaction:

~~~sql
UPDATE account_credentials
SET password_hash = :new_encoded_hash,
    credential_version = credential_version + 1,
    hash_upgraded_at = CURRENT_TIMESTAMP
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
  AND password_hash = :expected_old_hash
  AND credential_version = :expected_version
  AND account_status = 'ACTIVE';
~~~

- **1 row updated**: upgrade thành công.
- **0 rows updated**: password/status/version đã thay đổi; từ chối ghi đè và xử lý conflict theo policy.
- **DB timeout/exception**: lỗi hạ tầng, không phải password sai; không tăng lockout counter sai.
- **Transaction rollback**: tuyệt đối không báo upgraded khi DB chưa commit.

**Tại sao so cả version và hash?** Nếu mọi password reset/change đều tăng `credential_version`, version giúp chặn stale write; expected hash bổ sung một guard không cho update nhầm khi code nơi khác quên version. Cần bảo đảm secret status có điều kiện bảo vệ tương ứng.

### Hai login đúng chạy đồng thời

~~~text
Login 1 đọc H_old/v3, verify đúng, encode H1 với salt1.
Login 2 đọc H_old/v3, verify đúng, encode H2 với salt2.
Login 1 CAS thành công -> H1/v4.
Login 2 CAS 0 rows -> không được ghi H2 bằng update không điều kiện.
~~~

Đây có thể chỉ là **race lành tính**, nhưng cũng có thể là password reset từ một actor khác. Nếu chưa phân biệt được, chính sách bảo thủ là **trả yêu cầu retry** rồi tải credential hiện tại để verify lại, không cấp session dựa trên snapshot đã lỗi thời. Nếu có metadata phân biệt reset vs competing rehash, có thể thiết kế đường xử lý tinh hơn nhưng phải chứng minh không mở lại password cũ.

**Không giữ DB row lock trong lúc chạy bcrypt/Argon2**: hoạt động hashing tốn CPU; compute bên ngoài transaction rồi CAS với điều kiện version trong transaction ngắn.

## 10. UserDetailsPasswordService tích hợp với kho dữ liệu

Đây là **mảnh code dành cho Spring project**, dùng interface repository/app principal có version. Không phải file tự chạy bằng `javac`; implementation DB phải cung cấp atomic update.

~~~java
package example.migration;

import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;

public final class CasPasswordUpgradeService
        implements UserDetailsPasswordService {

    private final PasswordHashStore store;

    public CasPasswordUpgradeService(PasswordHashStore store) {
        this.store = store;
    }

    @Override
    public UserDetails updatePassword(UserDetails user, String newPassword) {
        if (!(user instanceof VersionedUserDetails principal)) {
            throw new AuthenticationServiceException(
                    "Unversioned account cannot be upgraded");
        }

        int rows = store.replaceIfCurrent(
                principal.accountId(),
                principal.credentialVersion(),
                principal.getPassword(),
                newPassword);
        if (rows != 1) {
            throw new AuthenticationServiceException(
                    "Credential state changed; retry authentication");
        }

        return principal.withPasswordAndVersion(
                newPassword, principal.credentialVersion() + 1);
    }

    public interface PasswordHashStore {
        int replaceIfCurrent(String id, long expectedVersion,
                String oldHash, String newEncodedHash);
    }

    public interface VersionedUserDetails extends UserDetails {
        String accountId();
        long credentialVersion();
        UserDetails withPasswordAndVersion(String encoded, long newVersion);
    }
}
~~~

**Ý nghĩa của đoạn code:**

- `newPassword` là **chuỗi hash mới đã được PasswordEncoder sinh**, không phải raw password. Không băm `newPassword` thêm lần nữa.
- `replaceIfCurrent` phải chạy CAS trong DB đúng account/tenant/status; interface demo dùng ID đơn nhưng repository thực phải có tenant scope khi áp dụng.
- Nếu trả 0 rows, throw lỗi service để **không báo session success từ credential stale** trong chính sách bảo thủ.
- Method `withPasswordAndVersion` phải giữ trạng thái account và authorities đúng; không auto-enable user do update hash.
- Không log hash mới, oldHash, password, SQL bind params nhạy cảm, hay `Authentication.toString()`.
- Nếu account disabled ngay trong lúc verify, chỉ đổi hash khi policy cho phép và đã kiểm tra trạng thái đủ mới; phiên đã phát cũng có thể cần revocation/session freshness.

### Gắn vào DaoAuthenticationProvider

~~~java
package example.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class LoginProviderConfiguration {

    @Bean
    DaoAuthenticationProvider daoProvider(
            UserDetailsService users,
            PasswordEncoder encoder,
            CasPasswordUpgradeService passwordUpgrade) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(passwordUpgrade);
        return provider;
    }
}
~~~

Trong một ứng dụng thật, cần tạo bean `CasPasswordUpgradeService` (ví dụ với `@Service`) và repository CAS, cùng `SecurityFilterChain` đăng ký đúng provider. Đừng đăng ký thêm một provider username/password không áp dụng migration hoặc dùng encoder cũ để vô tình tạo đường bypass. Spring Boot/Security version cụ thể phải được pin bằng BOM tương thích.

## 11. Java 17 chạy độc lập: rehash chỉ sau khi password đúng

Chương trình này tự mô phỏng một store và cơ chế transition:

- Hash **legacy fixture** sử dụng SHA-256 không salt, **chỉ để minh họa một định dạng cũ không an toàn**, tuyệt đối không sinh hash mới như vậy.
- Hash mới dùng PBKDF2-HMAC-SHA256 với 16-byte salt từ SecureRandom, 600.000 iterations **để minh họa**, phải benchmark nếu ứng dụng thực tế sử dụng PBKDF2.
- Password sai không làm store thay đổi; password đúng lần đầu nâng hash; password đúng lần sau không nâng nữa.
- CAS stale sau reset bị từ chối, mật khẩu cũ không được nhận lại.
- Không in password hoặc digest; stdout chỉ có kết quả boolean/status.

Tệp `PasswordMigrationDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordMigrationDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int ROUNDS = 600_000;
    private static final String LEGACY = "{legacy-sha256}";
    private static final String MODERN = "{pbkdf2-v2}$";

    static String oldHashForTest(String raw) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(raw.getBytes(StandardCharsets.UTF_8));
        return LEGACY + HexFormat.of().formatHex(digest);
    }

    static byte[] derive(String raw, byte[] salt, int rounds)
            throws Exception {
        char[] chars = raw.toCharArray();
        PBEKeySpec spec = new PBEKeySpec(chars, salt, rounds, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
            Arrays.fill(chars, '\0');
        }
    }

    static String modernHash(String raw) throws Exception {
        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        return MODERN + ROUNDS + "$"
                + Base64.getEncoder().encodeToString(salt) + "$"
                + Base64.getEncoder().encodeToString(
                        derive(raw, salt, ROUNDS));
    }

    static boolean matches(String raw, String stored) throws Exception {
        if (stored.startsWith(LEGACY)) {
            byte[] expected = HexFormat.of()
                    .parseHex(stored.substring(LEGACY.length()));
            byte[] actual = MessageDigest.getInstance("SHA-256")
                    .digest(raw.getBytes(StandardCharsets.UTF_8));
            return MessageDigest.isEqual(expected, actual);
        }
        if (!stored.startsWith(MODERN)) {
            return false;
        }
        String[] f = stored.split("\\$", -1);
        if (f.length != 4) {
            return false;
        }
        int rounds = Integer.parseInt(f[1]);
        if (rounds < 100_000 || rounds > 2_000_000) {
            return false;
        }
        byte[] salt = Base64.getDecoder().decode(f[2]);
        byte[] expected = Base64.getDecoder().decode(f[3]);
        if (salt.length != 16 || expected.length != 32) {
            return false;
        }
        return MessageDigest.isEqual(
                expected, derive(raw, salt, rounds));
    }

    static final class Store {
        private String hash;

        Store(String hash) {
            this.hash = hash;
        }

        synchronized String read() {
            return hash;
        }

        synchronized boolean cas(String expected, String next) {
            if (!hash.equals(expected)) {
                return false;
            }
            hash = next;
            return true;
        }
    }

    static String login(Store store, String password)
            throws Exception {
        String previous = store.read();
        if (!matches(password, previous)) {
            return "DENIED";
        }
        if (previous.startsWith(LEGACY)) {
            String next = modernHash(password);
            return store.cas(previous, next)
                    ? "AUTHENTICATED_AND_UPGRADED"
                    : "RETRY_REQUIRED";
        }
        return store.read().equals(previous)
                ? "AUTHENTICATED"
                : "RETRY_REQUIRED";
    }

    public static void main(String[] args) throws Exception {
        Store store = new Store(oldHashForTest("demo-secret"));
        System.out.println("initial legacy: " +
                store.read().startsWith(LEGACY));
        System.out.println("wrong password: " +
                login(store, "wrong"));
        System.out.println("first correct: " +
                login(store, "demo-secret"));
        System.out.println("modern now: " +
                store.read().startsWith(MODERN));
        System.out.println("second correct: " +
                login(store, "demo-secret"));

        String stale = store.read();
        store.cas(stale, modernHash("reset-secret"));
        System.out.println("stale CAS accepted: " +
                store.cas(stale, modernHash("demo-secret")));
        System.out.println("old after reset: " +
                login(store, "demo-secret"));
        System.out.println("new after reset: " +
                login(store, "reset-secret"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ (không cần Spring):

~~~bash
javac PasswordMigrationDemo.java
java PasswordMigrationDemo
~~~

Stdout **chính xác** bất kể salt ngẫu nhiên là gì:

~~~text
initial legacy: true
wrong password: DENIED
first correct: AUTHENTICATED_AND_UPGRADED
modern now: true
second correct: AUTHENTICATED
stale CAS accepted: false
old after reset: DENIED
new after reset: AUTHENTICATED
~~~

**Giải thích:** Hash mới khác nhau ở mỗi lần encode do salt ngẫu nhiên, nhưng `matches` dùng salt/iterations lưu cùng digest nên password đúng vẫn được nhận. `stale CAS accepted: false` chứng minh lần upgrade bắt đầu từ snapshot cũ không được ghi đè reset.

**Giới hạn của demo:**

- Legacy SHA-256 chỉ được tạo trong fixture để mô phỏng dữ liệu yếu; **không dùng** cho hệ thống mới.
- Store giữ trong một JVM và CAS dựa trên hash string; production cần DB transaction với credential version, account/tenant ID và status.
- Parser mẫu chưa bắt toàn bộ malformed formats/NumberFormatException/Base64 errors; adapter thực tế phải validate/handle fail closed, không chuyển lỗi parse thành authenticated.
- Không xử lý HTTP, MFA, session, rate limits, credential resets từ IdP hoặc phân quyền; demo không thay `DaoAuthenticationProvider`.
- `PBEKeySpec` clearPassword giúp giảm thời gian tồn tại của char[] bản sao, nhưng Java String password đầu vào có thể tồn tại trên heap. Không ghi vào logs/queue và không cố giữ password cho background job.
- Việc đọc version sau verify chỉ giảm race trong mô hình đơn giản; production phải thực thi trạng thái/freshness ở transaction và session issuance theo policy.

## 12. Hash cũ không có prefix: quy trình gắn nhãn không cần raw password

Ví dụ hàng DB lưu bcrypt `$2a$10$...` nhưng `DelegatingPasswordEncoder` muốn `{bcrypt}$2a$10$...`. Nếu biết chắc đó là bcrypt từ metadata và format, có thể thêm prefix vào DB **không thay digest**:

~~~sql
-- PostgreSQL minh họa; không phải script production tự chạy.
UPDATE account_credentials
SET password_hash = '{bcrypt}' || password_hash
WHERE hash_scheme = 'BCRYPT'
  AND password_hash LIKE '$2%'
  AND password_hash NOT LIKE '{bcrypt}%';
~~~

Trước khi dùng cần:

1. Dry run, đếm affected rows, xác minh chính xác bcrypt structure/cost/version.
2. Backup/canary; tránh bảng lớn bị khóa lâu, dùng batch theo PK.
3. **Expand reader** trước: các node cũ/mới phải verify được cả dạng trước/sau, không gây login outage khi một pod chưa deploy.
4. Không dùng chuỗi độ dài hoặc `LIKE$2%` đơn thuần làm bằng chứng format đúng.
5. Kiểm tra exact readback, cả format và collation, không nhân đôi prefix.
6. Khi đã prefix, bcrypt cost vẫn thấp; lazy rehash sẽ nâng cost lần login đúng kế tiếp.

Nếu chọn adapter thêm prefix “ảo” lúc đọc, phải **giữ old DB hash nguyên vẹn cho CAS**. Dùng giá trị có prefix ảo trong `WHERE password_hash=:expected_hash` sẽ không khớp giá trị DB và khiến upgrade mãi fail. Có thể lưu `storedHashRaw`/scheme/version trong custom UserDetails và thiết kế repository so đúng bản ghi.

Không chuyển mọi unknown hash thành `{noop}` hoặc tự giả định plaintext. Khi không biết schema cũ, chọn recovery thay vì mở một verifier quá rộng.

## 13. Password registration, change và reset phải ghi bằng scheme mới

Lazy upgrade là **đường bổ sung** cho hash cũ. Các thao tác tạo password mới phải dùng encoder hiện hành ngay:

- Đăng ký local password.
- Đổi password khi người dùng đã xác thực và policy yêu cầu reauthentication.
- Đặt password qua reset token ngắn hạn, một lần, có quota và xác minh owner.
- Admin khởi tạo một credential tạm có quy trình riêng nếu chính sách cho phép.
- Bật local password cho tài khoản trước đây chỉ dùng OIDC/SSO.

Quy trình password reset/change:

~~~text
Verified user / verified recovery token / MFA (theo risk)
   -> password policy & breached-password check
   -> currentEncoder.encode(newRawPassword)
   -> UPDATE password_hash + credential_version atomically
   -> audit PASSWORD_CHANGED/RESET (không log hash)
   -> session/refresh-token/remember-me invalidation theo policy
~~~

Không dùng cached old password hay mật khẩu do support biết để “reset tất cả”. Không tạo thêm bản copy hash yếu trong cột legacy_backup để rollback trừ khi có quy trình backup được bảo vệ/giới hạn riêng; hash yếu cũ để lại là mục tiêu tấn công.

Nếu user reset trong lúc một login cũ đang rehash, CAS phải làm password cũ **không thể sống lại**. Sau reset, test cả login bằng password cũ bị từ chối và login bằng password mới thành công.

## 14. Tài khoản không hoạt động: giới hạn không thể vượt của lazy migration

Người dùng không đăng nhập sẽ **không nhập password**, nên hệ thống không thể nâng hash của họ từ dữ liệu một chiều. Vì thế không thể tuyên bố “nâng 100% không ai cần reset” với user dormant, hash không nhận diện hoặc legacy pepper đã mất.

| Nhóm | Chiến lược |
| --- | --- |
| User thường đăng nhập | Nâng trong login đúng đầu tiên, không đổi UX |
| User dùng remember-me lâu ngày | Khi cần, yêu cầu fresh password reauthentication theo policy |
| User không hoạt động nhiều tháng | Theo dõi cohort và mốc sunset, không reset đồng loạt ngay |
| Legacy hash quá yếu hoặc bị nghi rò | Tăng ưu tiên reset/recovery dù UX bị ảnh hưởng |
| Unknown format/pepper cũ đã mất | Không verify an toàn; hỗ trợ recovery có xác minh |
| LDAP/SSO-only không có local password | Không thuộc local hash migration |
| Service account/headless client | Xoay secret hoặc thiết kế workload identity, không chờ interactive login |
| Disabled/expired account | Không bật lại chỉ để rehash |

Cần đặt **sunset date** theo rủi ro, pháp luật/chính sách và thời gian hoạt động; sau mốc đó các account còn hash yếu có thể buộc recovery **khi quay lại**, thay vì email “tất cả phải đổi ngay”. Đừng hứa không có bất cứ reset nào nếu scheme cũ đã bị compromise.

**Tránh phishing:** Thông báo migration không yêu cầu người dùng gửi password qua email, không gửi link login lạ. Nếu cần reauthentication, đưa tới domain/channels chính thức, không làm lộ account existence.

## 15. Bcrypt input length, Unicode, pepper và chính sách tương thích

- Bcrypt phổ biến có giới hạn khoảng **72 bytes** password input; chuỗi Unicode dài có thể vượt giới hạn byte. Khi chuyển bcrypt sang thuật toán khác, password nhập ở lần upgrade trở thành đầu vào thực tế của scheme mới; phải đánh giá trường hợp người dùng từng có suffix không được bcrypt tính.
- Không tự `trim` khoảng trắng ở đầu/cuối hay lowercase password nếu phiên bản cũ không làm như vậy.
- Không đổi Unicode normalization/charset trong migration mà không có test vectors, nhất là nếu hệ thống trước từng pre-hash trên client.
- Legacy pepper có thể làm hash không verify được nếu key mất. Không bỏ qua pepper hoặc dùng pepper sai mà vẫn cho authentication.
- Pepper rotation thường yêu cầu lần nhập password mới; hash stored không thể tự “đổi pepper” offline nếu không biết raw password.
- Không để stored hash được chuẩn hóa case bởi DB collation hoặc ORM mapping; base64 và prefix là chuỗi case-sensitive.
- Không xóa phiên cũ ngay chỉ vì user login bằng hash yếu nếu policy không yêu cầu: việc vô hiệu hàng loạt session có thể thành availability incident. Nếu có bằng chứng compromise, session revocation là quyết định sự cố riêng.

**Kết hợp MFA:** Password factor được xác minh và rehash không có nghĩa user đã vượt TOTP/WebAuthn; protected route đòi full MFA phải tiếp tục bị chặn. Không dùng OTP hoặc JWT làm nguyên liệu để nâng local password hash.

## 16. Đăng nhập ngoài DaoAuthenticationProvider

Có nhiều login entry points:

| Cơ chế | Có raw local password được xác minh? | Nên xử lý |
| --- | --- | --- |
| Spring form login + DaoAuthenticationProvider | Có | Đăng ký `UserDetailsPasswordService` để auto-upgrade |
| JSON login custom với AuthenticationManager | Có, nếu dùng provider đúng | Kiểm tra auto-upgrade có được gọi |
| AuthenticationProvider viết riêng | Có thể | Phải tự kết nối `matches/upgradeEncoding/CAS` an toàn |
| LDAP BindAuthenticator / Active Directory | Không sở hữu hash password ở DB ứng dụng | Directory tự chịu trách nhiệm password policy |
| OAuth2/OIDC/SAML login | Không | Không hash ID token/subject thành local password |
| Passkey/WebAuthn | Không có password local trong flow | Quản lý credential public key riêng |
| Remember-me cookie | Không | Không được dùng cookie để suy ra raw password |
| JWT/Bearer stateless request | Không | Token validation riêng, không chạy password rehash |
| Password reset có password mới | Có, được tạo mới | Current encoder trực tiếp, không phải lazy upgrade |

Trong hệ thống có nhiều `SecurityFilterChain`, xác minh form login/API login dùng đúng provider bean. Nếu một custom filter tự set `SecurityContextHolder` và bỏ qua `AuthenticationManager`, những policy về account state, password upgrade, compromised password, audit hoặc MFA có thể bị bỏ qua.

## 17. Chi phí migration trên CPU, RAM và độ trễ

Một login đầu tiên của user legacy phải làm **hai phép KDF** thay vì một: verify hash cũ, rồi encode hash mới. Nếu bcrypt cost cũ 10 và mới 12, lần đầu có thể tăng CPU đáng kể (bên cạnh SQL CAS), còn lần login kế tiếp chỉ verify hash mới.

~~~text
Trước rollout:
  login -> verify bcrypt(cost=10) -> session

Lần login đầu sau rollout:
  login -> verify bcrypt(cost=10)
        -> encode bcrypt(cost=12)
        -> UPDATE CAS
        -> session

Các lần sau:
  login -> verify bcrypt(cost=12) -> session
~~~

Cần benchmark tải **thật** với login burst, đặc biệt khi sau deploy user được yêu cầu đăng nhập lại hoặc session timeout đồng loạt. Những cách giảm rủi ro:

- Rate limit theo account và IP/network độc lập, tổng quota tại edge.
- Giới hạn số hash operations đồng thời (bulkhead); với Argon2id cần budget memory.
- Ghi metric duration/p95/p99 của verify, upgrade, DB CAS; không ghi password/hash.
- Triển khai canary, feature flag có thể **tạm ngừng upgrade** khi quá tải nhưng vẫn verify hash mới và cũ.
- Không hạ KDF mới một cách tùy ý khi quá tải; bảo toàn write-new policy theo risk decision.
- Không retry rehash vô hạn khi CAS conflict, không giữ transaction lock trong lúc hashing.
- Không gom hàng trăm nghìn account vào background job lấy password từ cache/log.

**Lưu ý:** Spring `PasswordEncoderFactories.createDelegatingPasswordEncoder()` có default mappings để tương thích, không đồng nghĩa tham số mặc định là mục tiêu bảo mật tối ưu trong mọi năm. Dùng cấu hình explicit có benchmark và kế hoạch cập nhật.

## 18. Rolling deployment và rollback không mất khả năng đăng nhập

Với hai phiên bản đồng thời, writer mới **không được tạo hash mà reader cũ không hiểu**. Lộ trình bảo toàn tương thích:

1. **Expand schema:** Cột hash đủ dài, version/metadata và indexes sẵn.
2. **Expand readers:** Phát hành code biết verify tất cả scheme cũ và mới trên mọi pod/region, chưa ghi scheme mới nếu vẫn còn node cũ không hỗ trợ.
3. **Verify mixed fleet:** Test cùng account lần lượt qua node A/B; cả sign-in/reset/change paths.
4. **Switch writer:** Bật current encoder cho new passwords, sau đó lazy rehash theo cohort/canary.
5. **Observe:** Theo dõi upgrade success, unknown IDs, CAS conflicts, CPU, DB writes và login failure.
6. **Contract:** Sau khi account dormant đã được xử lý, tắt legacy verifier theo deadline và release policy.

**Rollback:** Nếu phiên bản cũ không verify được hash mới, rollback toàn bộ sau khi upgrade có thể gây login outage. Phải có **compatible rollback reader** hoặc giữ phần đọc hash mới trong bản phục hồi. Không phục hồi hash cũ từ backup để “undo” upgrade cho user đã đổi password, vì có thể làm password cũ sống lại.

Đặc biệt với batch prefix `{bcrypt}`, bảo đảm cả ứng dụng cũ và mới hiểu prefix nếu rollout từng node. Việc tăng cost bcrypt thường vẫn giữ định dạng bcrypt, nhưng phải test library cũ chứ không mặc định mọi implementation đều tương thích vô điều kiện.

## 19. Observability, audit và chỉ số thành công

| Metric/category | Mục đích |
| --- | --- |
| `password_hash_inventory{scheme,cost_bucket}` | Thống kê tỷ lệ legacy/current |
| `password_upgrade_attempts_total{scheme}` | Số lần xác thực đúng cần upgrade |
| `password_upgrade_success_total{scheme}` | Số CAS update thành công |
| `password_upgrade_conflict_total` | Số 0-row CAS |
| `password_upgrade_error_total{reason}` | DB, unsupported scheme, malformed hash |
| `password_upgrade_duration_seconds` | Độ trễ rehash |
| `login_results_total{outcome}` | Bad credentials, locked, disabled, infra error |
| `password_reset_change_total{method}` | Tất cả new write paths |
| `legacy_inactive_accounts_bucket` | Tài khoản cần recovery khi sunset |

Các tên là ví dụ, không phải metrics Spring tự cung cấp. **Không dùng user ID, email, raw hash, token, session ID, IP hoặc password làm metric label** vì privacy/cardinality. Audit riêng có thể ghi event ID, account ref pseudonym, scheme trước/sau, version, UTC time, CAS result và request ID có RBAC/retention, không log hash thực.

Cảnh báo khi: login failure đột nhiên tăng sau deploy; số legacy không giảm dù có login đúng; CAS conflict hàng loạt; KDF p99 tăng bất thường; DB truncate; hash ID lạ tăng; upgrade phải tắt do saturation. Những tín hiệu đó giúp phát hiện lỗi cấu hình trước khi toàn hệ thống bị khóa ngoài ý muốn.

## 20. Ma trận kiểm thử tự động

### PasswordEncoder tests

- [ ] Password đúng với legacy hash -> `matches=true` và `upgradeEncoding=true`.
- [ ] Password sai -> `matches=false`, không có write.
- [ ] Old bcrypt cost thấp nhưng vẫn verify với encoder cost mới; đánh dấu upgrade.
- [ ] Current hash verify đúng và `upgradeEncoding=false`, không rehash vô hạn.
- [ ] Two encodes of same password dùng salt khác; cả hai đều verify.
- [ ] Unknown ID/malformed hash fail closed, không fallback `NoOp`.
- [ ] Prefix/metadata legacy phản ánh đúng DB format, không double-prefix.
- [ ] Unicode, spaces, long passwords, byte-length và pepper đúng test vectors.
- [ ] Hash column round-trips không bị truncate/case-fold/encoding corruption.

### Spring Security integration

- [ ] DaoAuthenticationProvider dùng đúng `PasswordEncoder`/`UserDetailsPasswordService`.
- [ ] Login đúng legacy -> persisted new hash, credential version tăng; lần login sau không upgrade.
- [ ] Password sai, account locked/disabled/expired/unknown -> không tạo hash mới.
- [ ] New registration/change/reset đều tạo current scheme.
- [ ] CAS conflict do password reset giữa matches và update: **không overwrite reset**, không cấp phiên stale.
- [ ] Hai login đúng đồng thời: chỉ một CAS success, conflict được xử lý an toàn.
- [ ] DB exception khi upgrade không bị phân loại thành wrong password hoặc tăng lockout counter.
- [ ] Khi login có MFA, password upgrade không khiến user truy cập full-MFA route trước khi verified.
- [ ] Custom API login/multiple providers không bỏ qua policy.
- [ ] Sau hash migration, cùng user login từ cả pod cũ tương thích và pod mới vẫn ổn.

### Storage, tải và vận hành

- [ ] Repository CAS dùng row count và version trong transaction, check tenant/status.
- [ ] Cache UserDetails bị invalidation/reload đúng sau upgrade, không dùng hash cũ vô hạn.
- [ ] DB outage, rollback, duplicate request, lost write và read replica lag không tạo success giả.
- [ ] p95/p99 authentication cost, CPU, memory, pool/threads và DB lock time dưới tải burst.
- [ ] Canary/feature flag tắt rehash nhưng không tắt verifier với hash mới.
- [ ] Sau sunset, account legacy chưa chuyển được buộc recovery thay vì fallback yếu.
- [ ] Rollback code tương thích với hash mới đã ghi, không restore hash cũ làm mất security.

## 21. Runbook khi rollout lỗi

**Triệu chứng: nhiều user báo mật khẩu đúng nhưng login thất bại.**

1. Kiểm tra `hash_scheme`/prefix phân bố và error category: Unknown `{id}`, bad credentials, malformed hash, DB outage hay CAS conflict.
2. Dùng **tài khoản test** mỗi scheme để reproduce, không yêu cầu người dùng gửi mật khẩu qua email.
3. Xác minh tất cả nodes đọc được hash current; rolling deployment có còn node chỉ hiểu legacy không?
4. Kiểm tra column length, encoding, ORM mapping, old PBKDF2 salt/pepper và work factor.
5. Nếu update CAS thất bại, xem version/status/race với password reset, không đổi thành unconditional UPDATE.
6. Nếu latency/CPU cao, giảm tốc traffic/canary, tạm tắt auto-upgrade nếu policy cho phép; **vẫn giữ current encoder cho passwords mới**.
7. Không log raw credentials/hashes để debug; ghi reason code và ID đã pseudonymized.
8. Kiểm thử rollback reader trước khi triển khai, theo dõi login outcomes sau sửa.

**Triệu chứng: legacy hash count không giảm.**

- Kiểm tra `DaoAuthenticationProvider.setUserDetailsPasswordService` có được gắn đúng bean và đúng chain không.
- Kiểm tra `upgradeEncoding` có thật sự trả true trên test hash cũ không.
- Xem custom UserDetailsService có trình bày đúng hash ID/cost và CAS có dùng giá trị DB thật không.
- Xem repository transaction có commit, version/row count có được ghi và cache stale không.
- Phân biệt tài khoản không login: không thể tự hứa migration nếu password không được nhập.
- Không bật lại legacy write-path chỉ để “giữ tiến độ” khi lỗi.

## 22. Kế hoạch chuyển đổi một hệ thống ví dụ

Giả định inventory (số liệu chỉ minh họa):

~~~text
45% {bcrypt} cost 12
40% {bcrypt} cost 10
15% {pbkdf2-v1} legacy
~~~

**Tuần triển khai 1:** Chuẩn hóa schema, kiểm tra PBKDF2 v1 verifier bằng test vectors, rollout tất cả readers hỗ trợ ba loại. Kiểm thử các pods và có rollback tương thích.

**Giai đoạn canary:** Bật current writer cho tài khoản mới/reset/change; thử một tỷ lệ traffic nhỏ cho lazy upgrade. Xác minh 1 login đúng nâng hash, 1 login sai không chạm DB, mỗi CAS kiểm version, login sau không rehash lại.

**Giai đoạn mở rộng:** Tăng traffic khi p99/CPU/CAS/DB ở mức chấp nhận, giữ anti-bot và bulkhead. Tài khoản cũ có hash yếu được nâng dần theo login thực. Theo dõi regression của browser form, API, MFA, user cache.

**Giai đoạn dormant:** Phân loại user lâu không hoạt động; gửi hướng dẫn chính thức và thiết kế reset/recovery khi họ quay lại, theo rủi ro của legacy hash. Không mở một “password fallback” để tránh reset.

**Giai đoạn retirement:** Đặt mốc bỏ verifier yếu, kiểm thử recovery và tác động support, sau đó tắt parser/secret cũ. Kiểm tra logs không rò hashes, xóa backup/cache cũ theo retention và quy trình pháp lý.

**Kết quả cần giải thích đúng:** Mục tiêu là **không bắt mọi người đổi mật khẩu cùng lúc**, không phải cam kết mọi bản ghi được nâng offline. Account không hoạt động vẫn có thể phải reset khi được kích hoạt lại sau mốc sunset.

## 23. Những sai lầm phổ biến và checklist

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Rehash chính `oldHash` | Password người dùng không thể verify như cũ | Chỉ rehash raw password sau `matches` |
| Đổi writer trước khi mọi reader hiểu format mới | Login fail theo pod/region | Expand-reader first |
| Unknown prefix fallback plaintext | Credential bypass | Whitelist schema, fail closed |
| Lưu hash mới không tăng version | CAS không chặn concurrent reset | Version tăng trên mọi thay đổi secret |
| UPDATE theo account ID không có expected hash | Password cũ ghi đè password reset | CAS expected hash/version/status |
| CAS conflict vẫn cấp login với stale user | Có thể sai bảo mật sau reset/disable | Retry/reverify an toàn |
| Không cấu hình UserDetailsPasswordService | Hash cũ tồn tại vĩnh viễn | Gắn đúng provider, test DB readback |
| Ghi `newPassword` từ service như raw | Băm hai lần hoặc lộ secret | `newPassword` trong service đã encoded |
| Chọn bcrypt cost rất cao mà không benchmark | Login CPU saturation/DoS | Canary, rate limit, p99/peak load |
| Nâng hash trong background bằng password cache | Rò secret nghiêm trọng | Trong authentication trust boundary |
| Chuyển local hash khi user login SSO | Không có raw local password | Không làm, chuyển tại IdP |
| Xóa legacy verifier ngay | Dormant users không thể login | Cohort sunset + recovery |
| Giữ legacy verifier mãi | Không hoàn thành giảm rủi ro | Deadline và ownership |
| Rollback bằng hash cũ từ backup | Có thể hồi sinh password đã reset | Rollback reader tương thích |
| Ghi hash/username vào metrics | Lộ dữ liệu, cardinality tăng | Aggregate metrics, audit RBAC |
| Thay `trim`/UTF-8 bất ngờ | Password user không còn verify | Giữ policy, test vectors |
| Quên password reset/write paths riêng | Vẫn tạo hash cũ | Kiểm kê mọi create/change/reset path |

**Checklist triển khai:**

- [ ] Inventory exact legacy scheme/params, current scheme/params và account types.
- [ ] Prefix/metadata chính xác, column đủ dài, DB collation an toàn.
- [ ] Cấu hình `DelegatingPasswordEncoder` có mapping cũ và writer mới, unknown ID fail closed.
- [ ] `DaoAuthenticationProvider` dùng `setUserDetailsPasswordService` qua đúng chain.
- [ ] Repository CAS trên account/tenant/version/oldHash/status, test reset race và two-login race.
- [ ] Wrong password, disabled/locked/unknown user không làm update.
- [ ] Đăng ký/reset/change sinh hash current; password reset không thể bị rehash cũ ghi đè.
- [ ] Không giữ raw password trong logs/queues/cache, không xuất hash ra metrics.
- [ ] Benchmark work factor, concurrency, rate limit, p99 và DB cost, có canary/rollback.
- [ ] Các node/phiên bản readers tương thích trước khi bật writer mới.
- [ ] Có plan cho dormant users và sunset legacy, kiểm thử recovery với user inactive.
- [ ] MFA, SSO, remember-me và token flows không bị nhầm là cung cấp raw password.
- [ ] QA integration/chaos/rollback đã pass và audit không tiết lộ credential.

**Kết luận:** Cách nâng hash mà không ép reset đồng loạt là **verify hash cũ → kiểm tra `upgradeEncoding` → tạo hash mới từ raw password vừa xác thực → CAS cập nhật đúng credential**. Spring Security cung cấp `DelegatingPasswordEncoder`, `DaoAuthenticationProvider` và `UserDetailsPasswordService`, nhưng ứng dụng phải hoàn thiện transaction, version, cache, rollout, observability và recovery. Đó là chuyển đổi có kiểm soát khi người dùng quay lại, **không phải phép biến đổi hash hàng loạt mà không biết mật khẩu**.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Password Storage và DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — UserDetailsPasswordService API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/core/userdetails/UserDetailsPasswordService.html)
- [Spring Security — PasswordEncoder interface](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/crypto/password/PasswordEncoder.html)
- [Spring Security — BCryptPasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/crypto/bcrypt/BCryptPasswordEncoder.html)
- [Spring Security — Cryptography and work factor](https://docs.spring.io/spring-security/reference/6.5/features/integrations/cryptography.html)
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [Java SE 17 — PBEKeySpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html)
- [Java SE 17 — SecretKeyFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html)
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html)
