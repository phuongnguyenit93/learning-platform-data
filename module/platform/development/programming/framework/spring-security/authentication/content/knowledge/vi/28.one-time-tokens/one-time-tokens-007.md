# Hết hạn, tiêu thụ một lần và xử lý yêu cầu đồng thời của token dùng một lần

## 1. Vì sao token “dùng một lần” là bài toán trạng thái, không chỉ là chuỗi ngẫu nhiên?

Một **one-time token (OTT)** là một bí mật chỉ được phép tạo ra một kết quả xác thực/hành động thành công **một lần**, trong **một khoảng thời gian** và **một mục đích** đã định. Ví dụ điển hình: magic link đăng nhập, liên kết xác minh email, token đặt lại mật khẩu hoặc chấp thuận một hành động nhạy cảm.

Ba điều kiện phải được kiểm tra **cùng lúc**:

1. **Hợp lệ về nguồn và mục đích:** token được tạo bởi hệ thống có thẩm quyền, liên kết đúng tài khoản/hành động/tenant.
2. **Chưa hết hạn:** thời điểm kiểm tra của server còn **trước** `expiresAt`.
3. **Chưa bị tiêu thụ:** chưa có request khác thắng quyền sử dụng token.

Nếu chỉ đáp ứng hai trong ba điều kiện, hệ thống có thể chấp nhận token sai mục đích, hết hạn hoặc bị phát lại (*replay*).

### Các bất biến bảo mật

- **At-most-once acceptance:** với một token cụ thể, tại mọi thời điểm, **tối đa một request** được chuyển trạng thái từ chưa dùng sang đã dùng thành công.
- **Expiry enforced:** token không được dùng khi `now >= expiresAt`; xóa bản ghi hết hạn theo lịch chỉ là dọn dẹp, **không thể thay cho kiểm tra hết hạn khi tiêu thụ**.
- **Purpose binding:** token reset password không được dùng để đăng nhập; token verify email không được dùng để đổi mật khẩu.
- **No silent privilege escalation:** việc token hợp lệ không bỏ qua kiểm tra trạng thái account, tenant và các điều kiện hành động.
- **Fail closed:** nếu không xác minh được trạng thái token vì DB/service lỗi, không mặc định chấp nhận.
- **Atomicity across concurrent requests:** không tạo ra hai lần thành công do các request đọc cùng một giá trị `unused`.

**Lưu ý thuật ngữ:** “one-time” nói về **một token được phát hành**, không tự bảo đảm một account chỉ được yêu cầu một token đang còn hiệu lực. Chính sách “mỗi người chỉ có một link mới nhất” là một yêu cầu bổ sung, phải thiết kế riêng.

## 2. Phân biệt OTT, OTP, TOTP/HOTP và authorization code

| Khái niệm | Cách tạo và sử dụng | Điều phải bảo đảm |
| --- | --- | --- |
| **OTT** (one-time token, magic link) | Server phát chuỗi ngẫu nhiên đủ entropy và giữ trạng thái/mapping để tiêu thụ | TTL, mục đích, tiêu thụ nguyên tử, chống replay |
| **OTP giao qua SMS/email** | Code ngắn do server phát cho một lần xác minh | TTL ngắn, giới hạn số lần thử, chống brute force, tiêu thụ nguyên tử |
| **TOTP** | Code theo thời gian từ shared secret và thuật toán | Chống phát lại trong cửa sổ thời gian nếu policy yêu cầu single-use; giới hạn số lần thử |
| **HOTP** | Code từ secret và counter | Counter được cập nhật nguyên tử; chống replay và xử lý lệch counter |
| **OAuth2 authorization code** | Authorization Server cấp code một lần đổi token | Ràng buộc client/redirect URI/PKCE và loại bỏ code sau lần đổi hợp lệ |
| **CSRF token** | Giá trị bảo vệ giao dịch hoặc form | Quy tắc vòng đời riêng; không mặc định mọi CSRF token là OTT chỉ dùng một lần |

Trong **Spring Security 6.4+**, tính năng `oneTimeTokenLogin()` là hỗ trợ **OTT server-issued**. Không đồng nhất nó với TOTP/HOTP do authenticator app tạo, hoặc với access token JWT có thể dùng nhiều request đến `exp`.

## 3. State machine và thời điểm hết hạn

Một token đi qua các trạng thái nghiệp vụ:

```text
                     issue(secure random, account, purpose, TTL)
                                      |
                                      v
                                ISSUED/UNUSED
                                  /       \
                      consume hợp lệ      now >= expiresAt
                                |                |
                                v                v
                           CONSUMED           EXPIRED
                                |
                           replay -> DENY

   REVOKED: admin/user đổi mật khẩu, hủy yêu cầu, phát hành token mới
             theo chính sách -> DENY dù TTL còn.
```

Ở mức DB có thể lưu `consumed_at` và `revoked_at` hoặc dùng một cột trạng thái. Không nhất thiết phải cập nhật `EXPIRED` trên từng bản ghi; nếu thời gian đã quá hạn, truy vấn tiêu thụ phải từ chối ngay cả khi DB vẫn ghi `unused`. Job dọn dẹp có thể xóa record cũ sau này.

### Quy tắc biên thời gian

Cho `issuedAt = 10:00:00Z` và `expiresAt = 10:05:00Z`:

| Thời điểm nhận/đánh giá | Chấp nhận khi token còn UNUSED? |
| --- | --- |
| `10:04:59.999Z` | Có, nếu đúng purpose và atomic claim thành công |
| `10:05:00.000Z` | **Không** |
| `10:05:00.001Z` | **Không** |

Điều kiện đúng là `now.isBefore(expiresAt)` trong Java, hoặc `expires_at > now` trong SQL. Đừng dùng `now <= expiresAt` nếu yêu cầu tại đúng mốc hết hạn phải bị từ chối.

**Đồng hồ:** lưu thời gian dạng `Instant`/UTC; hệ thống nhiều máy phải đồng bộ thời gian. Trong DB tập trung, cân nhắc kiểm tra với đồng hồ DB để tránh lệch thời gian giữa node. Với PostgreSQL, `CURRENT_TIMESTAMP` là thời điểm bắt đầu transaction; nếu một transaction phải chờ khóa lâu, có thể cần kiểm tra bằng `clock_timestamp()` tại lúc đánh giá để tránh chấp nhận theo thời điểm cũ. Không dùng thời gian do client gửi để quyết định còn hạn.

**TTL là giới hạn, không phải bảo đảm phát thư nhanh:** người dùng nhận mail muộn có thể thấy link đã hết hạn. Không “tự gia hạn token cũ”; cung cấp khả năng xin token mới theo chính sách chống abuse.

## 4. Lỗi race condition kinh điển: check rồi update

Mã không an toàn:

```java
// PSEUDOCODE SAI: hai lời gọi độc lập không tạo thành một operation atomic.
var token = repository.findByHash(hash);
if (token != null && !token.isUsed() && token.getExpiresAt().isAfter(now)) {
    createLoginSession(token.getAccountId()); // side effect
    repository.markUsed(hash);
}
```

Có thể xảy ra lịch xen kẽ:

```text
Thời gian      Request A                         Request B
    1          read token: unused
    2                                            read token: unused
    3          expiry check: pass
    4                                            expiry check: pass
    5          create session A
    6                                            create session B
    7          mark used
    8                                            mark used

=> Hai lần thành công dù cuối cùng chỉ còn một hàng ghi used=true.
```

Các biến thể **vẫn không đủ**:

- Dùng `synchronized` trên một controller trong **một JVM**: không khóa các instance khác.
- Đọc bản ghi rồi gọi `deleteById`: hai request có thể đọc thành công trước khi delete; return value từ bước read không chứng minh mình thắng.
- Đặt `@Transactional` quanh `SELECT` rồi `UPDATE` nhưng không khóa/conditional update thích hợp: tùy isolation level, vẫn có thể đọc cùng trạng thái.
- Kiểm tra cache `containsKey` sau đó `remove` ở hai lệnh riêng: đây vẫn là check-then-act.
- Dùng Redis `GET` rồi `DEL`: hai network commands không nguyên tử; cần một lệnh atomic/transaction/script có điều kiện và expiry được kiểm tra trong cùng bước.

**Cách đúng:** kiểm tra điều kiện chưa dùng/chưa hết hạn/đúng mục đích và **claim quyền tiêu thụ như một thao tác tuyến tính hóa** (*linearizable claim*) trên kho dữ liệu chung. Chỉ request được store xác nhận “claim thành công” mới được phép tiếp tục hành động.

## 5. Thiết kế dữ liệu để ngăn replay

Một model token có thể gồm:

| Trường | Ý nghĩa |
| --- | --- |
| `token_hash` | Hash của token bí mật; unique/index; không lưu nguyên raw token khi không cần |
| `account_id` | Tài khoản sở hữu hoặc chủ thể dự kiến |
| `purpose` | `MAGIC_LOGIN`, `RESET_PASSWORD`, `VERIFY_EMAIL`, ... |
| `created_at` | Thời điểm phát hành |
| `expires_at` | Thời điểm kết thúc hiệu lực, lưu theo UTC |
| `consumed_at` | Null khi chưa dùng, có thời gian khi đã claim |
| `revoked_at` | Null khi chưa bị thu hồi |
| `tenant_id` / `challenge_id` | Phân vùng và ràng buộc nghiệp vụ nếu hệ thống cần |
| `attempt_count` / metadata audit | Hỗ trợ rate limiting và điều tra, tránh ghi raw secret |

Ví dụ DDL **PostgreSQL minh họa**, không phải schema tự động của Spring Security:

```sql
CREATE TABLE app_one_time_tokens (
    token_hash CHAR(64) PRIMARY KEY,
    account_id VARCHAR(100) NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);

CREATE INDEX idx_ott_account_purpose
    ON app_one_time_tokens (account_id, purpose);
```

**Sinh token:** dùng `SecureRandom` sinh ít nhất 128 bit entropy, thường chọn 256 bit, rồi encode bằng Base64URL. Một token 32 bytes ngẫu nhiên có không gian tìm kiếm quá lớn để brute force trực tiếp khi giữ bí mật đúng cách. Với **token entropy cao**, lưu SHA-256 của raw value có thể là lựa chọn hợp lý; với **OTP 6–8 chữ số**, SHA-256 thuần không bảo vệ tốt nếu DB bị lộ vì không gian tìm kiếm quá nhỏ: cân nhắc HMAC với secret phía server, keyed lookup và rate limiting, hoặc thiết kế kiểm chứng thích hợp.

**Không dùng** `java.util.Random`, timestamp, UUID dễ đoán theo quy trình tùy biến, email hay số thứ tự DB như token bí mật. Random UUID v4 có entropy đáng kể nhưng cần bảo đảm thực sự là UUID v4 được tạo an toàn và phù hợp chính sách; raw 32 bytes từ `SecureRandom` là ví dụ rõ ràng hơn.

Trong các request HTTP, không đưa raw token vào log, traces, query metrics hoặc exception message; chỉ gửi token qua kênh dự kiến và giữ đúng purpose.

## 6. PostgreSQL: tiêu thụ bằng một UPDATE có điều kiện

Một giao dịch an toàn có thể dùng câu lệnh **atomic claim**:

```sql
-- PostgreSQL: chạy trong transaction của nghiệp vụ.
UPDATE app_one_time_tokens
SET consumed_at = clock_timestamp()
WHERE token_hash = :token_hash
  AND purpose = :purpose
  AND consumed_at IS NULL
  AND revoked_at IS NULL
  AND expires_at > clock_timestamp()
RETURNING account_id;
```

Giải thích:

- Request tính `token_hash` từ raw token nhận được; `:purpose` đến từ **endpoint/server policy**, không để client quyết định mở rộng mục đích.
- Database khóa và cập nhật hàng đáp ứng predicate. Nếu request A thắng, request B sẽ không thể cập nhật cùng hàng vì điều kiện `consumed_at IS NULL` không còn đúng sau khi A commit.
- **Một row được trả về** nghĩa là token được claim thành công; **không row** nghĩa là không tìm thấy/hết hạn/đã dùng/đã revoke/sai purpose.
- `clock_timestamp()` là thời gian hiện tại của PostgreSQL khi được gọi; không dựa trên `CURRENT_TIMESTAMP` cố định từ đầu transaction dài. Giá trị ghi `consumed_at` và giá trị so sánh hạn có thể chênh lệch rất nhỏ vì được gọi hai lần: hệ thống yêu cầu một mốc thống nhất tuyệt đối có thể tính mốc theo một biểu thức hoặc thời điểm được xác định sau khi lấy lock, rồi dùng nhất quán.
- Đảm bảo index theo `token_hash`. Query dùng `RETURNING` là cú pháp **PostgreSQL**, không áp dụng nguyên văn cho mọi RDBMS.

Nếu cập nhật mật khẩu:

```text
BEGIN TRANSACTION
    claim token bằng UPDATE ... WHERE chưa used + chưa expired
    nếu 0 row -> reject và ROLLBACK (hoặc kết thúc không thay đổi gì)
    nếu 1 row -> kiểm tra account, password policy, account state
                -> UPDATE users SET password_hash = ...
                -> invalidate sessions/recovery links theo policy
COMMIT
```

Việc **claim token và cập nhật dữ liệu nghiệp vụ cần cùng transaction DB** khi hai hành động phải cùng thành công hoặc cùng rollback. Không gửi email, gọi API ngoài hoặc tạo session ở service khác trong một transaction rồi tự khẳng định có được “exactly once” end-to-end: external side effect có thể thành công nhưng DB rollback hoặc ngược lại. Với tác vụ bên ngoài, dùng **transactional outbox + idempotency key**, trạng thái nghiệp vụ rõ và cơ chế retry an toàn.

### Trường hợp thực sự cần nhiều thao tác

Một số flow cần kiểm tra account, trạng thái MFA, token purpose, điều kiện đổi mật khẩu… sau khi lock. Cần chọn giữa:

- Một `UPDATE ... WHERE ... RETURNING` đặt toàn bộ điều kiện có thể đặt được vào một câu lệnh;
- `SELECT ... FOR UPDATE` rồi kiểm tra/ghi **trong cùng transaction** và không nhả khóa sớm;
- Conditional write theo version/CAS/optimistic lock, kiểm tra số row được cập nhật.

Đặc biệt, không thực hiện hành động có side effect **trước** khi biết claim có thành công.

## 7. Redis, MongoDB và nhiều instance

Nếu token tồn tại trên Redis:

- Với token đã được lưu cùng TTL và chỉ cần tiêu thụ giá trị đang tồn tại, `GETDEL key` (ở phiên bản Redis có hỗ trợ) là lệnh atomic lấy và xóa. Hết hạn key được Redis kiểm soát trên Redis server.
- Nếu phải kiểm tra đồng thời `purpose`, account state hoặc nhiều key trước khi xóa, dùng Lua script/transaction được thiết kế nguyên tử. Không làm `GET` rồi `DEL` tách biệt.
- Nếu cần rollback token khi thao tác DB thất bại, Redis và DB là **hai hệ thống transaction khác nhau**. Thiết kế saga/idempotency hoặc đặt trạng thái cần đồng bộ ở cùng DB; đừng coi `GETDEL` là transaction phủ cả DB.
- Chọn TTL phù hợp, bảo vệ Redis credentials/TLS, và cân nhắc failover/replication consistency; nếu cần bảo đảm chống replay mạnh, cần kiểm thử hành vi khi primary failover.

Trong MongoDB, có thể dùng `findOneAndUpdate` với filter `used=false` và `expiresAt > now` để claim atomic một document; TTL index chỉ lo dọn record, không thay kiểm tra expiry tại lúc claim.

**Lưu trong ConcurrentHashMap của JVM** đủ để minh họa atomic trong một process, nhưng **không** bảo đảm single-use giữa 2 pod/instance của cùng service. Khi triển khai phân tán, store và transaction phải dùng chung và nhất quán.

## 8. Ví dụ Java 17 chạy được: một token, 12 request cạnh tranh, đúng một request thắng

Đoạn sau chỉ dùng Java SE 17, không cần Spring hoặc server, có thể copy vào file **`OneTimeTokenDemo.java`** và chạy để quan sát replay/concurrency/expiry/purpose. Code sinh raw token bằng `SecureRandom`, lưu **SHA-256 hash** trong `ConcurrentHashMap`, tiêu thụ qua `compute` nguyên tử theo từng key.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

public class OneTimeTokenDemo {
    record TokenRecord(String subject, String purpose, Instant expiresAt) {}

    // Đồng hồ thay đổi được CHỈ để test thời điểm hết hạn, không dùng
    // MutableClock này trong production.
    static final class MutableClock extends Clock {
        private volatile Instant current;

        MutableClock(Instant current) {
            this.current = Objects.requireNonNull(current);
        }

        @Override public ZoneId getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(ZoneId zone) {
            return Clock.fixed(current, zone);
        }
        @Override public Instant instant() { return current; }

        void advance(Duration duration) {
            current = current.plus(duration);
        }
    }

    static final class TokenStore {
        private final ConcurrentHashMap<String, TokenRecord> records =
                new ConcurrentHashMap<>();
        private final SecureRandom random = new SecureRandom();
        private final Clock clock;

        TokenStore(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        String issue(String subject, String purpose, Duration lifetime) {
            if (subject == null || subject.isBlank()
                    || purpose == null || purpose.isBlank()
                    || lifetime == null
                    || lifetime.isZero() || lifetime.isNegative()) {
                throw new IllegalArgumentException("Invalid token request");
            }

            byte[] secret = new byte[32];
            random.nextBytes(secret);
            String raw = Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(secret);

            TokenRecord item = new TokenRecord(
                    subject, purpose, clock.instant().plus(lifetime));
            if (records.putIfAbsent(digest(raw), item) != null) {
                throw new IllegalStateException("Random token collision");
            }
            return raw;
        }

        Optional<String> consume(String raw, String requiredPurpose) {
            if (raw == null || raw.isBlank()
                    || requiredPurpose == null || requiredPurpose.isBlank()) {
                return Optional.empty();
            }

            AtomicReference<TokenRecord> accepted = new AtomicReference<>();

            // compute() khóa thao tác cập nhật cho một key trong CHM.
            records.compute(digest(raw), (hash, stored) -> {
                if (stored == null) {
                    return null;
                }
                if (!clock.instant().isBefore(stored.expiresAt())) {
                    return null; // expired -> remove
                }
                if (!stored.purpose().equals(requiredPurpose)) {
                    return stored; // sai purpose: không tiêu thụ token
                }

                accepted.set(stored);
                return null; // đúng purpose/chưa hết hạn -> xóa nguyên tử
            });

            TokenRecord result = accepted.get();
            return result == null
                    ? Optional.empty()
                    : Optional.of(result.subject());
        }

        private static String digest(String raw) {
            try {
                byte[] hash = MessageDigest.getInstance("SHA-256")
                        .digest(raw.getBytes(StandardCharsets.UTF_8));
                return HexFormat.of().formatHex(hash);
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        MutableClock clock =
                new MutableClock(Instant.parse("2026-01-01T00:00:00Z"));
        TokenStore store = new TokenStore(clock);
        String token = store.issue(
                "alice", "magic-login", Duration.ofMinutes(5));

        int workers = 12;
        ExecutorService executor = Executors.newFixedThreadPool(workers);
        CountDownLatch gate = new CountDownLatch(1);
        List<Future<Boolean>> attempts = new ArrayList<>();

        for (int i = 0; i < workers; i++) {
            attempts.add(executor.submit(() -> {
                gate.await();
                return store.consume(token, "magic-login").isPresent();
            }));
        }

        gate.countDown();
        int accepted = 0;
        for (Future<Boolean> future : attempts) {
            if (future.get()) {
                accepted++;
            }
        }
        executor.shutdown();

        System.out.println("simultaneousAccepted=" + accepted);
        System.out.println("replayAccepted="
                + store.consume(token, "magic-login").isPresent());

        String purposeToken =
                store.issue("bob", "reset-password", Duration.ofMinutes(2));
        System.out.println("wrongPurposeAccepted="
                + store.consume(purposeToken, "verify-email").isPresent());
        System.out.println("correctPurposeSubject="
                + store.consume(purposeToken, "reset-password")
                        .orElse("none"));

        String expiring =
                store.issue("carol", "magic-login", Duration.ofSeconds(30));
        clock.advance(Duration.ofSeconds(30));
        System.out.println("atExpirationAccepted="
                + store.consume(expiring, "magic-login").isPresent());
    }
}
```

Chạy:

```bash
javac OneTimeTokenDemo.java
java OneTimeTokenDemo
```

**Stdout xác định:**

```text
simultaneousAccepted=1
replayAccepted=false
wrongPurposeAccepted=false
correctPurposeSubject=bob
atExpirationAccepted=false
```

### Vì sao ví dụ không bị race?

- `ConcurrentHashMap.compute(hash, remapping)` tuần tự hóa cập nhật trên **một key** trong process, không tách bước kiểm tra và bước xóa.
- Lần đầu tiên thấy entry hợp lệ sẽ đặt `accepted` cho đúng lần gọi rồi trả `null`, khiến entry bị xóa trong chính thao tác atomic.
- Các request sau nhìn thấy `stored == null`, do đó trả `Optional.empty()`; không request thứ hai nào có thể đọc entry hợp lệ trước khi thay đổi hoàn tất.
- `AtomicReference` dùng để trả kết quả của **lần compute hiện tại** ra ngoài lambda một cách an toàn. Mỗi call có một instance riêng, không chia sẻ kết quả giữa các request.
- Nếu hết hạn, entry được xóa nhưng không được trả `accepted`. Nếu sai purpose, entry **không bị tiêu thụ**, nên chủ sở hữu có thể dùng đúng purpose trước expiry.
- `CountDownLatch` giúp 12 tác vụ bắt đầu cạnh tranh gần cùng lúc; kết quả phụ thuộc thứ tự luồng về *ai* thắng nhưng **không phụ thuộc** vào số người thắng: luôn tối đa một.
- `MutableClock` cho phép kiểm tra chính xác mốc `now == expiresAt` mà không dùng `Thread.sleep(...)` (test sleep thường flaky).

### Giới hạn của ví dụ

- Đây là **in-memory single-JVM demo**, không phải code repository phân tán hoặc production token store.
- Việc “consume” mới trả subject, **chưa tạo HTTP session, kiểm tra trạng thái account hoặc commit hành động nghiệp vụ**.
- Demo không có cơ chế giới hạn số lần yêu cầu token, dọn record theo batch, account revocation, audit, email sender hoặc TTL của hàng database.
- Với ràng buộc “mỗi account chỉ một token active”, cần index/generation policy ngoài map token hash.
- `SHA-256` ở đây là hợp lý chỉ vì token có 256 bit ngẫu nhiên; **không sao chép thiết kế hash này nguyên xi cho OTP vài chữ số**.
- Nếu định triển khai WebFlux, `ConcurrentHashMap.compute` rất ngắn/không I/O; các truy vấn DB/network phải dùng async driver hoặc scheduler phù hợp, không chạy JDBC blocking trong event loop.

## 9. Kết nối với tính năng Spring Security One-Time Token Login

Spring Security **6.4 trở lên** hỗ trợ `oneTimeTokenLogin()`. Với Servlet (Spring MVC):

```java
// Mảnh cấu hình thuộc class @Configuration trong Spring MVC:
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/ott/sent").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults())
            .build();
}
```

Các imports chính cho đoạn này:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Đây là **mảnh cấu hình**, không phải app Java độc lập. Cần app Spring Boot thực, user store và một bean gửi token/magic link qua kênh người dùng đã xác minh. Spring Security không tự biết email/SMS phù hợp với từng tài khoản, nên phải có `OneTimeTokenGenerationSuccessHandler` được cấu hình hoặc đăng ký theo hướng dẫn chính thức.

### Các API cần hiểu

| API | Vai trò |
| --- | --- |
| `OneTimeTokenService` | Giao diện tạo và tiêu thụ one-time token |
| `generate(GenerateOneTimeTokenRequest)` | Sinh và lưu token mới gắn user/expiration |
| `consume(OneTimeTokenAuthenticationToken)` | Claim token đã gửi; trả `OneTimeToken` nếu hợp lệ, `null` nếu không |
| `OneTimeToken.getTokenValue()` | Raw secret để gửi người dùng qua kênh được bảo vệ |
| `OneTimeToken.getUsername()` | Danh tính người dùng được liên kết với token |
| `OneTimeToken.getExpiresAt()` | Mốc hết hạn |
| `OneTimeTokenAuthenticationProvider` | Dùng service tiêu thụ token, thực hiện bước xác thực theo policy/provider |
| `OneTimeTokenAuthenticationFilter` | Nhận token và xử lý đăng nhập trong Servlet |
| `InMemoryOneTimeTokenService` | Implementation mặc định phù hợp demo/đơn máy |
| `JdbcOneTimeTokenService` | Implementation có persistence qua JDBC, phù hợp để cân nhắc ở môi trường nhiều instance |

**Mặc định của Spring Security 6.5:** thời lượng token có thể cấu hình qua `GenerateOneTimeTokenRequestResolver`; tài liệu minh họa mặc định **5 phút** và cho phép thay đổi `expiresIn`. Đây là mặc định của tính năng cụ thể, không có nghĩa mọi loại token của ứng dụng phải dùng TTL 5 phút.

Chữ ký interface:

```java
// Trích yếu chữ ký API, không phải một file Java độc lập:
public interface OneTimeTokenService {
    OneTimeToken generate(GenerateOneTimeTokenRequest request);
    @Nullable
    OneTimeToken consume(OneTimeTokenAuthenticationToken authenticationToken);
}
```

`@Nullable` ở đây nhấn mạnh trường hợp **invalid/expired/already used** không có token để xác thực. Không bao giờ gọi `getUsername()` trên kết quả `consume` khi chưa kiểm tra null.

### Thay store in-memory bằng JDBC

`JdbcOneTimeTokenService` nhận `JdbcOperations`:

```java
@Bean
OneTimeTokenService oneTimeTokenService(JdbcOperations jdbcOperations) {
    return new JdbcOneTimeTokenService(jdbcOperations);
}
```

Imports: `org.springframework.security.authentication.ott.OneTimeTokenService`, `org.springframework.security.authentication.ott.JdbcOneTimeTokenService`, `org.springframework.jdbc.core.JdbcOperations`. Ví dụ này đòi hỏi schema SQL chính thức tương ứng tại classpath `org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql`; **không dùng** bảng `app_one_time_tokens` ở mục 5 để giả vờ JDBC implementation mặc định đọc được.

**Điểm cần review khi triển khai thật:** xác minh giao dịch/logic consume của implementation và phiên bản Spring Security đang dùng dưới tải đồng thời, đặc biệt với database engine, isolation level và nhiều instance. Thực hiện integration test chứng minh chỉ một token được chấp nhận. Thay implementation mặc định khi cần ràng buộc purpose/account state, audit hoặc khả năng thu hồi theo chính sách riêng.

### Thay TTL trong Spring Security 6.5

Tài liệu 6.5 minh họa `DefaultGenerateOneTimeTokenRequestResolver`:

```java
// Mảnh cấu hình, cần Spring Security 6.5 tương ứng.
@Bean
GenerateOneTimeTokenRequestResolver generateOneTimeTokenRequestResolver() {
    var delegate = new DefaultGenerateOneTimeTokenRequestResolver();
    return request -> {
        var generated = delegate.resolve(request);
        return new GenerateOneTimeTokenRequest(
                generated.getUsername(), Duration.ofMinutes(10));
    };
}
```

Imports nằm trong package `org.springframework.security.web.authentication.ott` với resolver, và `org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest` với request, cộng `java.time.Duration`. Đoạn này minh họa **cơ chế đặt TTL**; việc chọn 10 phút cần xuất phát từ phân tích rủi ro, độ trễ nhận email và yêu cầu trải nghiệm.

### Servlet và WebFlux khác nhau

Trong **Spring WebFlux**, DSL cũng có `oneTimeTokenLogin()` nhưng hợp đồng service là `ReactiveOneTimeTokenService`: `generate(...)` và `consume(...)` trả `Mono<OneTimeToken>`; token không hợp lệ trả publisher rỗng. Implementation mặc định là `InMemoryReactiveOneTimeTokenService`. Filter chain dùng `ServerHttpSecurity` và `SecurityWebFilterChain`, không dùng `HttpSecurity`.

Dù app là Servlet hay reactive, **atomic consume vẫn là trách nhiệm persistence layer**. `Mono` hoặc `@Transactional` không tự biến câu `SELECT` rồi `DELETE` thành một thao tác nguyên tử giữa các node.

## 10. Khi nhiều request đến đồng thời: hiểu chính xác “một lần”

Ba khái niệm khác nhau:

- **At-most-once acceptance:** chỉ một request được claim token; tính chất tối thiểu cần có cho OTT.
- **At-least-once processing:** client retry đến khi nhận xác nhận; một hệ thống không có idempotency có thể chạy lại tác vụ.
- **Exactly-once effect:** tác động nghiệp vụ xuất hiện đúng một lần ở nơi cần quan sát. Đây là tính chất mạnh hơn và khó hơn, đặc biệt khi có nhiều hệ thống.

Ví dụ: request A claim token, cập nhật password, nhưng kết nối tới client đứt trước khi trả HTTP 200. Client retry bằng token cũ sẽ bị từ chối. Điều đó **không có nghĩa** reset password lần đầu thất bại; cần UX và tracking trạng thái phù hợp mà không tiết lộ dữ liệu nhạy cảm.

Nếu request A claim token trong transaction DB và lỗi trước commit, transaction rollback trả token về trạng thái unused. Request B/retry sau có thể thắng. Kết quả cuối cùng vẫn có thể đúng nếu operation và consume cùng transaction. Nhưng nếu hệ thống đã gửi email hoặc gọi downstream API trước khi rollback, side effect đó có thể đã xảy ra và lặp lại. Khi yêu cầu “một lần” ở hệ thống ngoài, dùng **outbox, event id và idempotent consumer**, không chỉ một cờ `used`.

### Linearization point là gì?

Điểm tuyến tính hóa là thời điểm mà hệ thống quyết định **chính xác request nào thắng**. Trong demo Java đó là `ConcurrentHashMap.compute(...)` với một key; trong DB đó là `UPDATE ... WHERE ... RETURNING` hoặc transaction/lock tương đương; trong Redis có thể là `GETDEL` hoặc script atomic được thiết kế đúng.

Mọi request thua không được tạo session/đổi mật khẩu/phát hành quyền; cũng không nên tiết lộ request nào thắng hoặc chi tiết account nếu điều đó giúp enumeration.

## 11. Hai yêu cầu phát hành token mới đồng thời

Ngoài race khi **tiêu thụ**, còn race khi **phát hành**:

```text
T1: User yêu cầu "Gửi lại liên kết" -> tạo token A
T2: User nhanh tay yêu cầu lần nữa -> tạo token B
Mail B đến trước, Mail A đến sau.
User nhấp A: có được dùng hay không?
```

Các lựa chọn policy:

1. **Cho phép nhiều token active độc lập:** A và B đều hợp lệ trước expiry, nhưng mỗi token chỉ tiêu thụ được một lần. Dễ triển khai; giảm “link đến chậm bị vô hiệu” nhưng tăng số secret còn hiệu lực.
2. **Latest-wins:** phát hành B sẽ revoke A theo cùng account + purpose. Cần thực hiện revoke-old + insert-new atomically, hoặc dùng generation/version và kiểm tra version ở bước consume.
3. **Một outstanding token mỗi account/purpose:** unique constraint hoặc row-level transaction ngăn hai request tạo ra hai bản ghi active. Cần định nghĩa retry và resend có gửi cùng secret hay tạo mới.
4. **Single-flight request:** rate-limit/gộp các yêu cầu gần nhau để giảm spam email/SMS; cần cẩn thận không gửi lại raw token đã chỉ lưu hash nếu không có thiết kế an toàn.

**Latest-wins không thay thế single-use.** Dù chỉ có token B còn active, hai request cùng dùng B vẫn cần atomic consume.

Nếu hệ thống lưu version, tiêu thụ phải kiểm tra **version hiện hành của account trong cùng transaction hoặc với quy tắc nhất quán rõ ràng**. Không kiểm tra version một lần ở đầu request rồi thực hiện side effect sau khi version đã đổi.

## 12. Magic link: tránh bot, trình quét link và yêu cầu GET tiêu thụ token

Email security scanner, preview bot, phần mềm chat hoặc trình duyệt có thể **mở link trước người dùng** để kiểm tra an toàn. Nếu endpoint `GET /login?token=...` **tiêu thụ ngay**, token sẽ bị dùng bởi bot và người dùng thật thấy “link đã sử dụng”.

Một flow an toàn hơn:

1. Email chứa link đến trang xác nhận qua HTTPS.
2. `GET` chỉ hiển thị trang/form phù hợp, **không tạo session và không consume**.
3. Người dùng chủ động bấm “Tiếp tục/Đăng nhập”; `POST` gửi token trong body, kèm các bảo vệ CSRF/state theo flow.
4. Backend thực hiện **atomic consume**, kiểm tra account status và chỉ sau đó hoàn tất authentication/action.
5. Đưa người dùng đến URL không chứa raw token, tránh lưu token vào history, Referer, logs hoặc analytics.

Lưu ý: chuyển token vào `POST` không tự giải quyết mọi vấn đề. Nếu link ban đầu có secret trong query URL, secret vẫn có thể xuất hiện trong browser history, email service hoặc reverse proxy logs. Cần `Referrer-Policy`, sanitize URL nhanh, hạn chế third-party scripts, không đưa token vào fragment/JavaScript mà không hiểu ranh giới tin cậy và chặn clickjacking/phishing phù hợp.

**Không để scanner gửi POST một cách dễ dàng** nếu yêu cầu bảo mật cao; cân nhắc bước xác nhận của con người, challenge gắn session/nonce, bảo vệ anti-automation và policy theo mục đích. Không dựa vào User-Agent để phân biệt bot.

## 13. Trạng thái tài khoản và hành động nghiệp vụ

Một token reset password được gửi khi tài khoản còn active; đến lúc người dùng nhấp link, tài khoản có thể đã:

- bị khóa/disable;
- bị xóa hoặc chuyển tenant;
- đổi địa chỉ email chính;
- bị admin buộc re-authenticate/MFA;
- đổi mật khẩu bằng một phương thức khác;
- được revoke toàn bộ recovery token.

Vì vậy **token hợp lệ không được đồng nghĩa “được thực hiện mọi thứ”**. Khi consume, cần kiểm tra điều kiện account và mục đích hiện hành. Chính sách có thể chọn revoke ngay khi password đổi hoặc account disabled; triển khai phải nhất quán và được test.

**Tình huống nhạy cảm:** token magic login có thể tạo phiên cho tài khoản, nhưng session sau đó vẫn phải tuân thủ session fixation protection, cookie bảo mật, timeout, điều kiện MFA/step-up khi nghiệp vụ yêu cầu. Không cấp quyền admin chỉ vì sở hữu một link trong email.

**Đăng nhập versus reset mật khẩu:**

- Với magic login, side effect có thể là tạo authenticated session trong Servlet/WebFlux. Atomic consume xảy ra trước khi thông báo login thành công; nếu session creation thất bại, ứng dụng cần thiết kế UX xin token mới.
- Với password reset, đặt thay đổi password hash và claim token vào **cùng transaction DB** khi có thể; sau commit, invalidates session/refresh tokens theo policy.
- Với email verification, cập nhật verified flag có thể idempotent nhưng token vẫn cần policy single-use để chống các flow chuyển quyền hoặc đổi email nhầm.
- Với payment/approval, không dựa vào một OTT như giao thức giao dịch đầy đủ; phải có authorization và idempotent business operation.

## 14. Lỗi bảo mật và lỗi triển khai thường gặp

**1. Token hết hạn nhưng vẫn dùng được.** Chỉ có cron job xóa token, không có predicate `expiresAt > now` khi consume. Sửa tại path xác thực/DB update; cleanup không là ranh giới tin cậy.

**2. Token bị phát lại và cả hai request đều thành công.** Đọc `used=false` rồi ghi `used=true` riêng biệt. Sửa bằng atomic claim, kiểm tra update-count và concurrency test.

**3. Dùng `synchronized` nhưng vẫn bị race ở Kubernetes.** Mutex chỉ áp dụng trong một JVM. Dùng DB/Redis state chung, transaction/atomic operation phù hợp.

**4. Dùng `get` rồi `remove` trong `ConcurrentHashMap`.** Đây là check-then-act không nguyên tử. Dùng `remove(key, expectedValue)` với kiểm tra an toàn khi applicable hoặc `compute` theo từng key.

**5. Dùng clock của client.** Client có thể sửa thời gian. Dùng Clock được inject server hoặc DB clock; test boundary và lệch đồng hồ.

**6. Token dùng sai mục đích.** Hash được chấp nhận tại tất cả endpoint vì không lưu `purpose`. Ràng buộc token với action, account, tenant và policy trong bước claim.

**7. Token được dùng rồi nhưng log/email chứa raw secret.** Người có quyền truy cập log có thể xem dữ liệu nhạy cảm, nhất là khi logs được stream tới nhiều hệ thống. Redact raw token ngay từ URL/header/body và audit bằng ID/hash không thể đảo.

**8. OTP chỉ 6 chữ số được lưu SHA-256 không khóa.** Nếu DB lộ, có thể thử toàn bộ không gian một triệu mã offline. Thiết kế keyed hash/server secret, TTL ngắn, attempt limit; không coi “đã hash” đồng nghĩa chống brute force.

**9. Một request claim token thành công rồi action thất bại.** Token đã mất mà nghiệp vụ chưa hoàn thành; hoặc action đã thành công nhưng DB rollback. Thiết kế transaction chung khi được, outbox/idempotency khi có service ngoài.

**10. Link bị scanner truy cập trước.** GET thực hiện consume. Đổi sang GET hiển thị trang, POST xác nhận; đánh giá các cơ chế bảo vệ automation và rò URL.

**11. Admin khóa tài khoản nhưng token cũ vẫn đăng nhập.** Không check account status hoặc session revocation sau consume. Kiểm tra chính sách ở thời điểm sử dụng.

**12. Một email xin lại nhiều token và gửi bị đảo thứ tự.** Không có quy tắc latest-wins/multi-active rõ. Xác định policy, lưu version/generation nếu cần.

**13. Cứ nhận token là trả chi tiết account.** Response khác nhau cho “user không tồn tại”, “token hết hạn”, “token đã dùng” có thể tiết lộ dữ liệu. Dùng thông báo phù hợp và audit riêng, vẫn bảo đảm UX.

**14. Retry vô hạn khi DB/introspection lỗi.** Retry không kiểm soát có thể gây tải cao và race; không được fail-open. Chọn bounded retries, timeout, circuit breaker và idempotent semantics.

**15. Chỉ unit-test tuần tự.** Test 1 request thành công rồi request 2 thất bại không đủ chứng minh an toàn dưới concurrency. Cần barrier/concurrent load và kiểm tra kết quả **trên cùng kho dữ liệu**.

**16. Xóa token khỏi DB trước khi commit side effect ở service khác.** Dẫn đến “token consumed nhưng hành động mất” hoặc “thực hiện hai lần” khi retry. Thiết kế outbox/transaction và compensate theo nghiệp vụ.

## 15. Bộ kiểm thử thiết yếu cho OTT

| Test case | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ lần đầu | Token đúng owner/purpose, trước `expiresAt` | Một lần thành công |
| Replay | Token đã consume | Từ chối, không chạy lại side effect |
| Biên thời gian | `now == expiresAt` | Từ chối |
| Gần trước biên | `now < expiresAt` một lượng nhỏ | Có thể nhận nếu claim atomic |
| Expired vẫn nằm trong DB | Cron cleanup chưa chạy | Từ chối |
| Wrong purpose | Token reset password gửi vào verify email | Từ chối, không tiêu thụ cho purpose đúng |
| Invalid/unknown token | Chuỗi không có trong store | Từ chối an toàn |
| Disabled account | Token còn hạn nhưng account bị khóa | Từ chối theo policy |
| Đồng thời trong một JVM | 12–100 request cùng token | Tổng request thắng **không quá 1**; với token hợp lệ và store khỏe: đúng 1 |
| Đồng thời nhiều instance | Request phân tán trên nhiều pod | Tổng thắng không quá 1 trên shared store |
| Race với expiry | Token hết hạn ngay khi chờ lock | Không chấp nhận sau hạn theo định nghĩa thời gian đã chọn |
| Race với revoke | Admin revoke gần thời điểm consume | Quy tắc thứ tự/transaction nhất quán |
| DB rollback | Consume thành công trong txn nhưng nghiệp vụ lỗi | Không có side effect commit dở; retry behavior theo policy |
| Hai yêu cầu phát hành mới | A/B tạo đồng thời | Đúng policy latest-wins hoặc multi-active |
| Email scanner GET | Link bị mở không có xác nhận | Không consume token trên GET |
| Xóa record hết hạn | Cleanup chạy trùng với consume | Không tạo hai lần thành công hoặc exception không kiểm soát |
| Abuse phát hành/đoán code | Tần suất cao, brute force | Rate limit, generic response, telemetry, không lộ account |

### Test tải đúng cách

- Dùng barrier (như `CountDownLatch`) để gần đồng thời gửi nhiều request.
- Không chỉ đọc response HTTP: kiểm tra DB `consumed_at`, số session/action được tạo, số bản ghi audit.
- Chạy test nhiều lần, cả trên **hai instance** chia sẻ DB, các isolation level đúng production và khi có network delay.
- Test cả failure giữa các bước: sau claim, trước business update; trước commit; sau commit nhưng trước khi trả response.
- Không chấp nhận một kiểm thử chỉ xác minh “DB cuối cùng dùng cờ true”; phải xác minh **số side effects thành công bằng một**.

## 16. Giám sát và vận hành

Theo dõi những chỉ số phục vụ hành động nhưng tránh chứa secret:

- Số request phát token mỗi account/IP/tenant theo cửa sổ, tỷ lệ gửi email/SMS lỗi.
- Tỷ lệ consume thành công, invalid, expired, already-used (chi tiết chỉ ở audit an toàn).
- Độ trễ request từ issue đến consume, tỷ lệ token hết hạn trước khi được dùng; dùng để hiệu chỉnh TTL.
- Các lần retry/concurrency bất thường trên một hash/token ID đã ẩn danh.
- Số lần rollback sau claim, DB lock wait timeout/deadlock, Redis failover, email scanner incidents.
- Tỷ lệ user phải xin token mới; cảnh báo khi có chiến dịch brute force hoặc email flooding.

Không cần lưu raw token trong audit để phát hiện replay: lưu hash/ID ngắn có chủ đích, thời điểm, tài khoản đã che, result code và request correlation ID. Hash có thể được xem là dữ liệu liên kết danh tính nếu audit lâu dài; áp dụng retention/access control.

**Xử lý dọn dữ liệu:** token hết hạn/consumed cần được xóa hoặc archive theo retention và audit policy. Xóa bằng job không thay nghĩa vụ kiểm tra hạn khi consume. Với bảng lớn, index/partition và lịch cleanup ảnh hưởng hiệu năng.

## 17. Checklist quyết định trước khi triển khai

1. Token có entropy đủ mạnh, kênh gửi an toàn và không lộ trong log/analytics không?
2. Từng token có **purpose**, account/tenant và thời điểm hết hạn server-side rõ ràng không?
3. Ranh giới hết hạn có đúng `now < expiresAt` và clock/UTC không?
4. Tiêu thụ có phải **một thao tác atomic/transactional** ngay cả khi có nhiều pod không?
5. Claim thành công và business action có nằm trong transaction chung khi cần không?
6. Khi phải gọi hệ thống ngoài, có outbox/idempotent consumer và cách xử lý retry không?
7. Chính sách nhiều token cùng user là latest-wins hay multi-active? Có giải quyết race issue/revoke không?
8. GET email/magic-link có vô tình consume khi crawler/link scanner truy cập không?
9. Account bị khóa/đổi mật khẩu/thu hồi quyền có vô hiệu hóa các token chưa dùng không?
10. Error response có chống username/token enumeration mà vẫn giúp user xin lại link hợp lệ không?
11. Test concurrency có chạy trên shared store thật, cả failure injection, expiry boundary và rollback không?
12. Với Spring Security `oneTimeTokenLogin()`, service persistence và TTL có đáp ứng yêu cầu của **phiên bản framework đang dùng** không?

### Tài liệu tham khảo

- Spring Security 6.5 — One-Time Token Login (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html
- Spring Security 6.5 — One-Time Token Login (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/onetimetoken.html
- Spring Security API — `OneTimeTokenService`, `consume` và `generate`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authentication/ott/OneTimeTokenService.html
- Spring Security API — `InMemoryOneTimeTokenService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/InMemoryOneTimeTokenService.html
- Spring Security API — `JdbcOneTimeTokenService`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/JdbcOneTimeTokenService.html
- PostgreSQL — `UPDATE ... RETURNING`: https://www.postgresql.org/docs/current/sql-update.html
- Redis — `GETDEL`: https://redis.io/docs/latest/commands/getdel/
- OWASP — Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html

**Điểm cốt lõi:** token chỉ “dùng một lần” khi kho dữ liệu có thể quyết định **nguyên tử request nào được phép tiêu thụ token**; TTL phải được kiểm tra **trong chính bước đó**. Session, email, cập nhật mật khẩu và các tác động ngoài DB vẫn cần giao dịch/idempotency thích hợp — một cờ `used=true` không tự tạo ra exactly-once behavior trên toàn hệ thống.
