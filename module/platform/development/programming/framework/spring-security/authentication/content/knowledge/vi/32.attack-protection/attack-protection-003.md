# Khóa tạm thời và tránh biến cơ chế khóa thành công cụ từ chối dịch vụ

> **Ngữ cảnh:** Chống brute-force, credential stuffing và password spraying tại endpoint đăng nhập Spring Security. Một chính sách “sai 5 lần thì khóa account 30 phút” có thể giảm đoán mật khẩu nhưng cũng cho phép kẻ tấn công cố ý **khóa tài khoản của người dùng thật**. Bài này giải thích cách cân bằng bảo mật và tính sẵn sàng: giới hạn thử đăng nhập nhiều lớp, thời hạn khóa hợp lý, khả năng khôi phục, trạng thái phân tán, chống rò username và cách tích hợp vào Spring Boot 3.x/Spring Security 6.x với Java 17.

## 1. Câu hỏi thiết kế cốt lõi

Người dùng A nhập mật khẩu sai nhiều lần có thể là đang quên mật khẩu; người không quen biết B cũng có thể gửi mật khẩu sai cho username của A. Server **không thể dùng riêng số lần thất bại để phân biệt hai người**. Nếu ngay lập tức khóa cứng A mỗi khi đủ số lần sai, B có công cụ gây **denial of service (DoS)** mà không cần biết mật khẩu A.

Cần đồng thời đạt:

1. **Giảm khả năng đoán mật khẩu online:** giới hạn tốc độ, số lần thử, phân biệt xác thực password và MFA.
2. **Không dễ gây lockout cho nạn nhân:** request từ nguồn không tin cậy không được kéo dài khóa vô hạn; có lối đăng nhập/khôi phục đã được chứng minh quyền sở hữu.
3. **Không làm tê liệt hạ tầng:** limiter, CAPTCHA, delay, gửi thông báo và password hashing không trở thành nguồn tiêu thụ CPU/DB/thread không giới hạn.
4. **Không cấp quyền khi chưa xác minh:** bất kỳ cơ chế “giảm gây phiền” nào cũng không được bỏ qua password, MFA, account disabled hay chính sách authorization.

**Nguyên tắc:** Account lockout là **một công cụ hạn chế thử mật khẩu**, không phải toàn bộ hệ thống chống bot. Giới hạn theo nhiều tín hiệu cùng phản ứng tăng dần thường an toàn hơn một boolean `locked` bị bất kỳ attacker nào kích hoạt.

## 2. Phân biệt các kiểu tấn công

| Kiểu tấn công | Hành vi | Vì sao một limiter không đủ |
| --- | --- | --- |
| Brute-force | Nhiều password cho một username | Per-IP đơn thuần bị né khi đổi IP |
| Credential stuffing | Cặp email/password từ vụ lộ khác thử trên nhiều account | Mỗi username có thể chỉ có 1 lần sai |
| Password spraying | Một vài password yếu trên nhiều tài khoản | Chỉ per-account không thấy toàn chiến dịch |
| Distributed low-and-slow | Nhiều proxy, mỗi nguồn chỉ gửi ít request | Per-IP threshold có thể không bao giờ chạm |
| Lockout DoS | Gửi đúng số lần sai để khóa tài khoản nạn nhân | Hard lock theo username bị attacker điều khiển |
| Notification bombing | Gây liên tục sự kiện khóa hoặc reset password | Email/SMS vô hạn cũng là DoS và tăng chi phí |
| Resource exhaustion | Gửi username rất dài/ngẫu nhiên, dùng password hashing đắt | Tốn CPU, bộ nhớ limiter và Redis keys |

Một cách cấu hình sai phổ biến là chỉ có bucket `username+ip`. Khi attacker đổi IP vẫn có thể thử account đó; khi đổi username, một IP có thể thử hàng nghìn account mà mỗi cặp vẫn dưới ngưỡng. Cần các bucket **độc lập** theo account, IP/mạng, endpoint/toàn dịch vụ; bucket theo cặp chỉ là tín hiệu bổ sung.

## 3. Khóa tạm thời khác khóa vĩnh viễn như thế nào?

| Trạng thái | Ngữ nghĩa | Cách được phép mở |
| --- | --- | --- |
| `ACTIVE` | Có thể thử đăng nhập theo policy | Vẫn cần password/MFA hợp lệ |
| `THROTTLED` | Phải chờ hoặc làm bước bổ sung để hạn chế bot | Hết cooldown hoặc qua challenge đúng |
| `TEMP_LOCKED` | Một đường password auth bị chặn đến `lockedUntil` | Hết hạn hoặc recovery tin cậy |
| `AUTHENTICATOR_DISABLED` | Một authenticator không còn được phép sử dụng theo chính sách | Rebind/reset/recovery được xác thực |
| `ACCOUNT_DISABLED` | Tài khoản bị vô hiệu bởi quản trị/chính sách | Phải có quyết định admin thích hợp |
| `ACCOUNT_EXPIRED` | Vòng đời tài khoản kết thúc | Không tự mở vì một timer brute-force hết |

**Không dùng một trường `locked=true` duy nhất** cho tất cả loại trên: khi cooldown hết, code “set locked=false” có thể vô tình mở lại account do admin vô hiệu hóa. Mốc `lockedUntil` cũng **không** được tự gia hạn mỗi khi có thêm request trong thời gian đang khóa.

### Quy định và số lần thử

Trong NIST SP 800-63B-4, với loại authenticator thuộc phạm vi yêu cầu, verifier phải giới hạn các lần xác thực thất bại liên tiếp với authenticator trên một account theo giới hạn **không quá 100**, và thực hiện disable/rebinding theo trường hợp chuẩn quy định. **100 là trần, không phải cấu hình mặc định khuyến nghị.** Quy tắc “khóa 2 phút sau 3 lỗi” trong ví dụ Java dưới đây chỉ minh họa tính toán; bản thân nó **không chứng minh tuân thủ NIST**. Cần xét riêng loại authenticator, mức đảm bảo và cơ chế recovery/rebind.

## 4. Các tham số chính của chính sách

Một chính sách cần xác định rõ:

- **Ngưỡng (`threshold`):** bao nhiêu lỗi trong cửa sổ mới áp dụng một biện pháp; chọn theo threat model, không tự sao chép số 3 hoặc 5 từ demo.
- **Cửa sổ quan sát (`observationWindow`):** 5, 10 hoặc 15 phút là ví dụ; dùng sliding window/token bucket để tránh burst đúng ranh giới fixed window.
- **Thời gian làm chậm/khóa (`cooldown`):** phải hữu hạn, có trần, không tăng chỉ vì request khi đã khóa.
- **Phản ứng tăng dần (`escalation`):** source-scoped throttle, challenge, step-up, điều tra hoặc disable authenticator theo chính sách; không đồng nghĩa khóa account dài vô hạn.
- **Reset/decay:** khi mật khẩu thật sự đúng, khi hết observation window, khi cooldown kết thúc và sau recovery.
- **Giới hạn phát thông báo:** một account bị spam không được sinh hàng trăm email/SMS cùng nội dung.
- **Điều kiện khôi phục:** không có endpoint “unlock” chỉ cần biết email, cũng không có bypass bằng header của client.

| Cách giới hạn | Mạnh ở đâu | Lỗi thiết kế có thể xảy ra |
| --- | --- | --- |
| Fixed-window count | Đơn giản | Burst tại mép hai khoảng thời gian |
| Sliding-window count | Thấy nhiều lần thử trong một khoảng dịch chuyển | Phải atomic khi nhiều node |
| Token bucket | Giới hạn trung bình và burst | Burst capacity có thể quá lớn |
| Exponential backoff có trần | Tăng chi phí guessing | Nếu chờ bằng `Thread.sleep` gây hết thread |
| Soft account cooldown | Ngăn một loạt lần thử | Có thể bị lặp re-lock để DoS nạn nhân |
| Hard account lock | Chặn mọi password attempt | Kẻ tấn công chủ động ngăn user hợp lệ |
| Conditional CAPTCHA | Tăng chi phí automation | Không chống được bot thuê giải và ảnh hưởng accessibility |
| Adaptive MFA/step-up | Có thêm bằng chứng sở hữu | Chỉ an toàn với factor đã đăng ký, server xác minh |

**Khóa 5 lần sai trong 15 phút chưa đủ chống DoS.** Attacker có thể gửi năm lỗi ngay lúc khóa hết, biến một hình phạt 15 phút thành từ chối truy cập kéo dài nhiều giờ.

## 5. Tấn công minh họa: trước và sau

**Thiết kế sai — chỉ hard lock theo username:**

~~~text
09:00  Attacker biết username "an" từ trang công khai.
09:01  Attacker gửi 5 password sai cho "an".
09:01  Server khóa account "an" 30 phút.
09:05  Chủ tài khoản nhập password đúng -> vẫn bị từ chối.
09:31  Hết lock. Attacker lại gửi 5 password sai.
09:32  Chủ tài khoản lại bị chặn.
~~~

Không cần đoán trúng password để phá khả năng sử dụng dịch vụ. Nếu UI trả “Tài khoản an tồn tại, khóa đến 09:31” thì attacker còn có **oracle để dò danh tính và điều phối đợt khóa kế tiếp**.

**Thiết kế cải thiện — đa lớp và ràng buộc tác động:**

~~~text
Internet traffic
  |
  +-- Gateway/WAF: global + IP/network burst + request cost limits
  |
  +-- Login guard: independent account bucket, source bucket,
  |                account-risk/tenant signals, adaptive challenge
  |
  +-- Quyết định:
  |       ALLOW -> xác minh password
  |       THROTTLE_SOURCE -> từ chối source trong thời gian ngắn
  |       STEP_UP -> bằng chứng độc lập có sẵn
  |       TEMP_ACCOUNT_LOCK -> chỉ nếu policy đánh giá phù hợp
  |
  +-- DaoAuthenticationProvider: UserDetailsService + PasswordEncoder
  |
  +-- Thành công: reset đúng password counter, tiếp tục MFA nếu cần
  +-- Sai password: cập nhật counter nguyên tử
  +-- Lỗi backend: infrastructure error, không đếm như sai password
~~~

Điều này **không bảo đảm** attacker không bao giờ làm phiền người dùng, nhưng giảm khả năng một nguồn không tin cậy trực tiếp khóa cứng nạn nhân và tạo các đường xử lý sự cố rõ ràng. Đừng giả định CAPTCHA là bằng chứng người dùng chính chủ; nó chỉ hạn chế automation.

## 6. Thiết kế limiter đa chiều

| Bucket | Giá trị khóa | Lý do |
| --- | --- | --- |
| **Account** | ID account ổn định, chuẩn hóa cùng login repository | Chống brute-force phân tán nhiều IP |
| **Nguồn** | IP do trusted reverse proxy xác nhận, subnet/ASN nếu phù hợp | Chống quét nhiều username từ một nguồn |
| **Endpoint/global** | Login, reset, OTP verification và tổng sức chứa | Chống lưu lượng lớn gây nghẽn hệ thống |
| **Tenant** | Tenant đáng tin từ server context | Giới hạn chiến dịch tập trung vào tổ chức |
| **Session/device** | Mã ràng buộc và đã kiểm chứng khi có | Nhận diện automation, không tin fingerprint tuyệt đối |

**Tách riêng account bucket và source bucket**: không thay chúng bằng một bucket duy nhất `login:{username}:{ip}`. Nên kiểm tra ở edge trước password hashing vì BCrypt/Argon2id có chủ ý tốn tài nguyên; một bot flood nhiều username có thể bão hòa CPU nếu mỗi request đều được phép chạy hash.

### IP không đáng tin nếu lấy từ header tùy ý

Nếu ứng dụng trực tiếp lấy `X-Forwarded-For` làm IP và không xác minh nguồn, attacker có thể tự gửi một IP mới mỗi request. Chỉ tin forwarded headers do reverse proxy/gateway **đã được quản trị** thiết lập; cấu hình trusted proxies, xử lý IPv4/IPv6/NAT và không chọn bừa phần tử đầu tiên trong chuỗi khi không có trust model.

Giới hạn IP quá gắt cũng khóa cả trường học, mạng doanh nghiệp, NAT nhà mạng hoặc người dùng VPN. IP là **tín hiệu**, không phải danh tính chắc chắn. Không buộc mọi người trong một ASN dùng cùng một “account lock”.

### Username không tồn tại

Unknown usernames vẫn có thể là mục tiêu probing. Nếu tạo Redis key theo mọi username tự do mà không TTL, attacker gửi hàng triệu chuỗi ngẫu nhiên sẽ làm đầy bộ nhớ. Cần normalization nhất quán, giới hạn length/charset theo policy, TTL, bounded cardinality, và có thể dùng HMAC fingerprint thay vì lưu email rõ. Response cho unknown username phải đủ giống trường hợp username tồn tại nhưng password sai.

## 7. Chính sách phản ứng tăng dần thay vì khóa tất cả

| Tín hiệu | Phản ứng gợi ý | Giới hạn ảnh hưởng |
| --- | --- | --- |
| Một số lỗi do gõ sai, nguồn quen thuộc | Cho retry; reset sau auth thành công | Không khóa account quá sớm |
| Một nguồn có burst vượt mức | Trả 429/cooldown theo nguồn, không chạy password hash thêm | Không phạt cả account quá rộng |
| Nhiều nguồn cùng đoán một account | Account budget + risk scoring + challenge/step-up | Không biến vài lỗi thành khóa vĩnh viễn |
| Một nguồn thử hàng nghìn account | Global/source quota và phát hiện spraying | Không chỉ nhìn per-user count |
| Nghi ngờ account takeover | Hạn chế thao tác rủi ro, yêu cầu reauth mạnh | Giữ đường recovery tin cậy |
| Authenticator đạt ngưỡng disable theo chuẩn | Disable/rebind authenticator tương ứng | Khôi phục theo chuẩn, không chỉ xóa timer |

Có thể giảm tốc theo **cấp độ rủi ro** thay vì “sai bao nhiêu là khóa tất cả”. Không nên dựa đơn độc vào geolocation, user-agent hay device fingerprint do client điều khiển; kết hợp tín hiệu backend và tránh phân biệt đối xử bất hợp lý với người dùng di chuyển hoặc dùng công nghệ hỗ trợ.

**Quan trọng:** Một nguồn có thể *liên tục tái khóa* account bằng cách chờ hết cooldown rồi thử lại. Việc chỉ cấm gia hạn lock **trong khi đang khóa** không giải quyết toàn bộ DoS; cần phát hiện repeated re-lock, hạn chế nguồn/automation và lối recovery/step-up có mức đảm bảo phù hợp.

## 8. Mô hình trạng thái và thời gian

Thông tin lưu trữ gợi ý:

| Trường | Công dụng |
| --- | --- |
| `account_key` | Định danh an toàn, thống nhất với UserDetailsService |
| `window_started_at` / sliding-window events | Cửa sổ lỗi quan sát |
| `fail_count` | Số lỗi thuộc window, độc lập counter chuẩn nếu cần |
| `consecutive_failure_count` | Đếm liên tiếp theo authenticator nếu policy bắt buộc |
| `locked_until` | Thời điểm kết thúc khóa tạm, UTC |
| `version` / `lock_generation` | Tránh stale write và mất cập nhật |
| `last_success_at`, `last_failed_at` | Reset, telemetry và audit |
| `risk_state` | Trạng thái từ các tín hiệu nguồn/thiết bị |
| `account_status` | Admin-disabled/expired tách khỏi temp lock |
| `last_notification_at` | Hạn chế email/SMS bombing |

Quy ước rõ:

~~~text
isTemporaryLocked(now) = now < lockedUntil
canTryPassword = accountEnabled
             AND not authenticatorDisabled
             AND not temporaryLocked
             AND sourceAndGlobalBudgetsAllow
~~~

Khi `now == lockedUntil`, khóa tạm **hết hiệu lực**. Không xóa trạng thái admin-disabled hay authenticator-disabled chỉ vì deadline qua. Server dùng `Instant`/UTC, đồng hồ đồng bộ; không tin timestamp gửi từ browser.

## 9. Java 17 chạy độc lập: khóa hữu hạn, spam không gia hạn

Chương trình minh họa cửa sổ trượt 5 phút, threshold 3, lock 2 phút. Các số **chỉ để test**, không nên dùng trực tiếp ở production. `synchronized` chỉ bảo vệ trong **một JVM**; hệ phân tán cần Redis/DB có tính nguyên tử.

Tạo `TemporaryLockDemo.java`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayDeque;
import java.util.Deque;

public final class TemporaryLockDemo {

    static final class Guard {
        private static final int LIMIT = 3;
        private static final Duration WINDOW = Duration.ofMinutes(5);
        private static final Duration LOCK = Duration.ofMinutes(2);

        private final Deque<Instant> failures = new ArrayDeque<>();
        private Instant lockedUntil = Instant.EPOCH;

        synchronized String check(Instant now) {
            return now.isBefore(lockedUntil) ? "TEMP_LOCKED" : "ALLOW";
        }

        synchronized void badPassword(Instant now) {
            if (now.isBefore(lockedUntil)) {
                // Request lúc khóa không được kéo dài deadline.
                return;
            }
            if (!lockedUntil.equals(Instant.EPOCH)) {
                lockedUntil = Instant.EPOCH;
                failures.clear();
            }

            Instant cutoff = now.minus(WINDOW);
            while (!failures.isEmpty()
                    && !failures.peekFirst().isAfter(cutoff)) {
                failures.removeFirst();
            }
            failures.addLast(now);
            if (failures.size() >= LIMIT) {
                lockedUntil = now.plus(LOCK);
                failures.clear();
            }
        }

        synchronized void realSuccess(Instant now) {
            if (!now.isBefore(lockedUntil)) {
                failures.clear();
                lockedUntil = Instant.EPOCH;
            }
        }

        synchronized Instant deadline() {
            return lockedUntil;
        }
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-06T00:00:00Z"), ZoneOffset.UTC);
        Instant t = clock.instant();
        Guard guard = new Guard();

        System.out.println("initial: " + guard.check(t));
        guard.badPassword(t.plusSeconds(1));
        guard.badPassword(t.plusSeconds(2));
        System.out.println("after 2 failures: " +
                guard.check(t.plusSeconds(2)));

        guard.badPassword(t.plusSeconds(3));
        System.out.println("after 3 failures: " +
                guard.check(t.plusSeconds(3)));

        Instant firstDeadline = guard.deadline();
        guard.badPassword(t.plusSeconds(4));
        System.out.println("attack extended lock: " +
                !guard.deadline().equals(firstDeadline));

        System.out.println("before deadline: " +
                guard.check(t.plusSeconds(122)));
        System.out.println("at deadline: " +
                guard.check(t.plusSeconds(123)));

        guard.badPassword(t.plusSeconds(124));
        System.out.println("first new failure: " +
                guard.check(t.plusSeconds(124)));

        guard.realSuccess(t.plusSeconds(125));
        System.out.println("after real success: " +
                guard.check(t.plusSeconds(126)));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac TemporaryLockDemo.java
java TemporaryLockDemo
~~~

Stdout **chính xác**:

~~~text
initial: ALLOW
after 2 failures: ALLOW
after 3 failures: TEMP_LOCKED
attack extended lock: false
before deadline: TEMP_LOCKED
at deadline: ALLOW
first new failure: ALLOW
after real success: ALLOW
~~~

Giải thích: Ba lỗi xảy ra lúc 00:00:01–00:00:03Z nên deadline là **00:02:03Z**. Request sai lúc 00:00:04Z bị bỏ qua, không gia hạn; 00:02:02Z còn lock và 00:02:03Z đã mở. Lần lỗi sau khi khóa hết mở window mới; `realSuccess` chỉ được gọi từ kết quả xác thực password thật, không được gọi khi client tự nói “success”.

Cửa sổ của ví dụ là `(now-5 phút, now]`: lỗi ở chính ranh giới trái bị bỏ. Hãy kiểm thử boundary, không kết luận từ khoảng phút được làm tròn.

**Giới hạn bắt buộc nhắc lại:** Đây là **mô phỏng lock state**, chưa chống attacker liên tục khóa lại ngay sau mỗi lần hết 2 phút. Chưa có shared storage, nhiều nguồn/IP, MFA, chuẩn NIST, khôi phục, chống username enumeration, lockout DoS ở quy mô thật hoặc bảo vệ password hash CPU. **Không sử dụng độc lập cho production**.

## 10. Atomicity và nhiều instance: đừng dùng counter trong RAM

Nếu hai request sai đến hai pod, cả hai có thể đọc `fail_count=4` và cùng ghi `5`. Một lần thử bị thất lạc; điều ngược lại cũng có thể làm một thành công bị tính hai lần và khóa sớm. Đưa trạng thái vào store chia sẻ, với transaction/atomic script và TTL.

### SQL trong một transaction

~~~sql
BEGIN;

SELECT fail_count, window_started_at, locked_until, version
FROM login_throttle
WHERE account_key = :account_key
FOR UPDATE;

-- Code server xét thời gian tin cậy:
--   còn khóa -> không extend locked_until;
--   window cũ hết -> reset window theo policy;
--   nếu password thực sự sai -> cập nhật counter;
--   đủ ngưỡng -> đặt locked_until hữu hạn.

UPDATE login_throttle
SET fail_count = :updated_count,
    window_started_at = :updated_window,
    locked_until = :updated_deadline,
    version = version + 1
WHERE account_key = :account_key;

COMMIT;
~~~

Đây là **pseudocode SQL** cho DB hỗ trợ `SELECT ... FOR UPDATE`, không phải script production chạy độc lập. Cần triển khai `INSERT/UPSERT` record đầu tiên với unique constraint, xử lý 0 row, isolation, retry/idempotency, trạng thái disabled và reset thích hợp. Nếu dùng optimistic locking, thêm `WHERE version = :expected_version` và **không ghi đè** snapshot khi phiên bản đã đổi.

### Redis và token bucket

Một Lua script/transaction ở Redis có thể đọc `fail_count`, deadline, window, kiểm tra `now` và cập nhật **atomic**. Khi khóa còn hiệu lực phải trả decision mà không kéo dài deadline. Thiết lập TTL ngắn phù hợp và bounded cardinality. Nếu dùng Redis Cluster, thiết kế hash slot cho các keys cần atomicity; không giả định script nhiều slot chạy nguyên tử.

Đừng dùng `GET` rồi `SET` riêng qua mạng mà không xử lý concurrency. Không dùng user-controlled raw email dài làm Redis key không TTL. Không coi cache local của một pod là source of truth cho lock trên toàn cụm.

### Không tạo delay bằng sleep

Chèn `Thread.sleep(30_000)` trong mỗi HTTP login request bị từ chối sẽ giữ Servlet thread và connection 30 giây. Attacker chỉ cần flood vài trăm request để làm cạn thread pool. Hãy từ chối sớm với 429/response chung, hoặc scheduling/backoff không blocking **có giới hạn concurrency** khi thật sự cần. Password encoder có chi phí CPU, do đó giới hạn nguồn/edge trước khi verify password là phần thiết yếu của khả năng sẵn sàng.

## 11. Các điểm Spring Security cung cấp sẵn

Spring Security 6 có các thành phần:

- `DaoAuthenticationProvider` xác thực username/password qua `UserDetailsService` và `PasswordEncoder`.
- `UserDetails.isAccountNonLocked()` cùng `AccountStatusUserDetailsChecker` kiểm tra trạng thái account, có thể ném `LockedException`.
- `AuthenticationProvider`, `AuthenticationManager` để điều phối phép xác thực.
- `AuthenticationFailureHandler`/`AuthenticationSuccessHandler` và application events xử lý thành công/thất bại trong form login.
- `SecurityFilterChain`, `AuthenticationEntryPoint`, `AuthorizationManager` và session management.

Framework **không tự tạo** account/IP/global budget nhiều tầng, sliding-window store, risk engine, chính sách unlock giảm DoS hoặc recovery. Chỉ override `isAccountNonLocked()` để trả false khi gặp vài lỗi password không bảo đảm hệ thống an toàn trước lockout DoS.

**Khi dùng `LockedException`:** Exception này chỉ có nghĩa request bị từ chối vì trạng thái khóa; nó **không khẳng định password đúng hay sai**. Vì vậy không cộng vào counter bad-password một lần nữa. Tương tự, lỗi DB/KMS/timeout không phải `BadCredentialsException` và không được ghi như lỗi do user.

## 12. Tích hợp với AuthenticationProvider: tránh double-count

Luồng gợi ý:

~~~text
Request /login
    |
    +-- gateway source/global rate limits
    |
    +-- policy.accountCooldown(login) -> nếu chặn, báo generic error
    |
    v
AuthenticationManager -> ThrottledPasswordProvider
    |
    +-- delegate DaoAuthenticationProvider -> UserDetails + PasswordEncoder
    |
    +-- BadCredentialsException -> recordBadPassword một lần, atomically
    +-- LockedException -> account state error, không tăng lỗi password
    +-- DB outage -> infrastructure error, không tăng lỗi password
    +-- success -> reset password counter của đúng account/factor
    |
    v
MFA nếu cần -> full session chỉ sau khi đủ factor
~~~

Ví dụ một interface ứng dụng tự triển khai (bắt buộc có shared store, policy theo nguồn/rủi ro riêng):

~~~java
package example.security;

public interface LoginAttemptPolicy {
    boolean temporaryAccountCooldown(String username);
    void recordBadPassword(String username);
    void recordPasswordSuccess(String username);
}
~~~

Wrapper provider cho username/password:

~~~java
package example.security;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

public final class ThrottledPasswordProvider implements AuthenticationProvider {
    private final AuthenticationProvider delegate;
    private final LoginAttemptPolicy policy;

    public ThrottledPasswordProvider(
            AuthenticationProvider delegate, LoginAttemptPolicy policy) {
        this.delegate = delegate;
        this.policy = policy;
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {
        if (!(request instanceof UsernamePasswordAuthenticationToken)) {
            return null;
        }

        String username = request.getName();
        if (policy.temporaryAccountCooldown(username)) {
            throw new LockedException("Temporarily restricted");
        }

        try {
            Authentication result = delegate.authenticate(request);
            if (result != null && result.isAuthenticated()) {
                policy.recordPasswordSuccess(username);
            }
            return result;
        } catch (BadCredentialsException invalid) {
            policy.recordBadPassword(username);
            throw invalid;
        }
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(authentication)
                && delegate.supports(authentication);
    }
}
~~~

**Đọc code đúng phạm vi:** `temporaryAccountCooldown` phải là **quyết định của policy giảm lockout DoS**, không phải ngưỡng 3 lỗi thô áp cứng. Interface ở trên chưa mang IP/counter, vì lớp nguồn/IP nằm ở gateway hoặc một service riêng; cần integrate cả hai. `LoginAttemptPolicy` phải là bean đã kiểm thử kỹ và cập nhật atomic.

`recordPasswordSuccess` chỉ xác nhận password factor đúng. Nếu user còn MFA, phải thực thi MFA trước full authentication. Không reset counter TOTP chỉ vì password đúng; không nâng authority theo field do client gửi.

**Tránh bypass:** Không đăng ký delegate gốc và wrapper làm hai provider độc lập cùng hỗ trợ `UsernamePasswordAuthenticationToken`. Nếu ProviderManager có đường dự phòng khác, account throttle có thể bị lách. Cần kiểm tra cả login API khác, OAuth2/OIDC, remember-me, mobile API và multiple `SecurityFilterChain`.

### Cấu hình Spring Boot 3.x / Spring Security 6.5

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LoginSecurityConfiguration {

    @Bean
    AuthenticationProvider throttledProvider(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder,
            LoginAttemptPolicy attemptPolicy) {

        DaoAuthenticationProvider delegate =
                new DaoAuthenticationProvider(userDetailsService);
        delegate.setPasswordEncoder(passwordEncoder);
        return new ThrottledPasswordProvider(delegate, attemptPolicy);
    }

    @Bean
    SecurityFilterChain loginChain(
            HttpSecurity http, AuthenticationProvider throttledProvider)
            throws Exception {
        return http
                .authenticationProvider(throttledProvider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error",
                                "/assets/**", "/account/recovery/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.failureUrl("/login?error"))
                .build();
    }
}
~~~

Đây là **mảnh cấu hình**, không phải ví dụ tự chạy bằng `javac`. Ứng dụng phải có `UserDetailsService`, `PasswordEncoder`, policy/Redis/DB, login form và controller recovery; còn các source/global limits cần được cấu hình ở gateway hoặc filter riêng. URL `/login?error` chỉ nên đưa thông điệp chung, không hiển thị trạng thái nội bộ từ `LockedException`.

Nếu đã ghi counter ở wrapper thì `AuthenticationFailureHandler` **không** nên ghi thêm một lần lỗi. Failure handler thích hợp cho response chung hoặc telemetry đã được kiểm soát; riêng nó không thực thi pre-auth limit vì chỉ được gọi **sau** failure.

### Lưu ý bản vá Spring Security 2026

Spring công bố **CVE-2026-22746 (20/04/2026)** liên quan việc **dò trạng thái thuộc tính người dùng qua timing** khi dùng `DaoAuthenticationProvider` với account disabled/expired/locked. Với các nhánh liên quan, bản sửa có trong **6.5.10** và **7.0.5**. Dùng bản vá mới nhất được hỗ trợ trong nhánh bạn vận hành; không cho rằng chỉ có thông điệp lỗi chung là đủ bảo vệ username enumeration nếu code path có thời gian xử lý khác biệt.

## 13. Phản hồi công khai và chống username enumeration

Một endpoint đăng nhập không nên trả khác biệt dễ nhận ra giữa:

- User không tồn tại.
- User có tồn tại nhưng password sai.
- Account bị tạm khóa hoặc disabled.
- Authenticator hết hạn/chưa đủ yếu tố để được cấp phiên.
- Một nguồn phải chờ do risk-based policy.

Ví dụ câu chung: **“Không thể hoàn tất đăng nhập. Hãy kiểm tra thông tin hoặc thử lại sau.”**

Đừng trả: “Tài khoản minh@example.test tồn tại, đã sai 5 lần, sẽ mở lúc 09:35” cho người chưa xác thực. Thông tin đó có thể giúp attacker tìm username, căn giờ tấn công hoặc liên tục tái khóa.

Kiểm tra không chỉ **body** mà còn HTTP status, redirect khác nhau, độ dài phản hồi, cookie, thời gian xác minh, dữ liệu side-channel và sự kiện reset email. Trạng thái chính xác có thể hiển thị trong **kênh account management đã được xác thực mạnh**, không phải public login.

Giới hạn thời gian phản hồi bằng `Thread.sleep` ngẫu nhiên không phải giải pháp mặc định: sleep dài có thể gây DoS CPU/thread. Ưu tiên bản vá timing, kiểm soát chi phí và giới hạn request trước password hash.

## 14. Reset, recovery và tránh lối mở khóa bị lạm dụng

**Khi xác thực password thật thành công:** reset/giảm counter password theo policy; không xóa security audit hoặc thay đổi `ACCOUNT_DISABLED`. **Khi MFA sai:** tăng counter của MFA factor, không coi là sai password. **Khi store hỏng:** không đếm lỗi password của người dùng.

**Đường recovery phải xác minh sở hữu**, ví dụ:

1. Passkey/WebAuthn hoặc MFA đã enrollment cung cấp bằng chứng độc lập theo policy.
2. Password reset token ngẫu nhiên, hạn ngắn, dùng một lần, có quota và kiểm tra quyền; không mặc định email reset đủ cho mọi yêu cầu của tài khoản MFA cao.
3. Recovery codes có entropy và rate limit, lưu hash, tiêu thụ atomically.
4. Helpdesk kiểm tra danh tính theo quy trình, chống social engineering, có audit người mở.
5. Notifications out-of-band được gộp và giới hạn tốc độ để tránh email/SMS bombing.

Không tạo endpoint `POST /unlock` mà ai biết username cũng gọi được để mở khóa. Không hủy tất cả session hợp lệ chỉ vì attacker nhập sai vài password, trừ khi có tín hiệu compromise và policy cho phép; ngược lại, khi đã xác nhận account compromise phải có thể buộc reauth/revoke session.

Khi mở khóa tạm, chỉ sửa trường cooldown/counter đúng phạm vi. Trường admin-disabled, factor revoked, account expired và risk flags không được ghi đè bởi một bản ghi “active” cũ. Với nhiều request đồng thời, sử dụng version/transaction để một password success cũ không xóa quyết định khóa khẩn sau đó.

## 15. Sự cố limiter store và availability

Nếu Redis/DB cho throttle unavailable, có hai kiểu lỗi:

- **Fail open không có kiểm soát:** bỏ qua mọi rate limits, cho bot brute-force và tạo overload password hash.
- **Fail closed toàn bộ lâu dài:** mọi user không thể đăng nhập, chính limiter trở thành single point of failure và DoS.

Phương án hợp lý phải được threat-model, ví dụ store HA, timeout ngắn, circuit breaker, edge quotas vẫn hoạt động, risk-adaptive MFA và fallback **được phê duyệt trước** theo loại tài nguyên. Nếu thiếu một kiểm chứng bảo mật **bắt buộc** cho loại authenticator/session, không được ngầm cho qua. Khi có degradation, log sự kiện nội bộ, cảnh báo và phục hồi nhanh; không chia sẻ trạng thái sai/trễ vô hạn.

Các lỗi vận hành thường gặp:

| Sai lầm | Hậu quả | Sửa |
| --- | --- | --- |
| `Thread.sleep` trong HTTP thread | Pool exhaustion | Reject sớm/async bounded |
| Redis key theo raw username không TTL | RAM exhaustion | Normalization, TTL, cardinality limit |
| Chỉ memory counter trên một pod | Dễ đổi pod để né | Shared atomic store |
| Rate limit theo header IP chưa tin | Header spoofing | Trusted proxy model |
| Chỉ giới hạn account, không source | Password spraying | Independent source/global budgets |
| Chỉ giới hạn source, không account | Phân tán botnet | Independent account budget |
| Timer lock gia hạn bởi mỗi request sai | Nạn nhân không thể mở khóa | Không đổi deadline khi đang locked |
| Hết timer tự bật cả admin-disabled | Mở lại account trái policy | State types riêng |
| Đếm lỗi tại cả provider và handler | Khóa account quá sớm | Ownership của counter |
| Lỗi DB bị quy thành sai password | Lock nạn nhân do outage | Phân loại infrastructure error |
| Email mỗi lần request sai | Notification bombing | Throttled notification workflow |
| Generic message nhưng timing khác | Account enumeration | Bản vá Spring và integration tests |

## 16. Ma trận kiểm thử

### Unit test với thời gian cố định

- 0/1/2/3 lỗi theo threshold minh họa, window và deadline cho kết quả đúng.
- `now = lockedUntil.minusNanos(1)` còn lock; `now = lockedUntil` hết lock.
- Sai liên tục trong thời gian lock không gia hạn `lockedUntil`; sau lock hết có thể bắt đầu window mới.
- **Repeated re-lock** vẫn được phát hiện và hạn chế bằng source/risk controls, không chỉ unit test timer.
- Password success thật reset đúng counter; OTP sai không thay đổi password counter.
- `BadCredentialsException` đếm một lần; `LockedException`, account disabled, DB outage và timeout không bị tính là password sai.
- Username normalization cùng quy tắc giữa DB lookup, limiter và logs; case/Unicode khác biệt không tạo identity khác ngoài policy.
- Thử từ 1 IP vào 1.000 users và 1.000 IP vào 1 user: mỗi chiến dịch gặp bucket tương ứng.
- Unknown usernames không tăng memory không giới hạn, không lộ account qua status/body/timing.

### Concurrency và hạ tầng

- Hai password sai cùng lúc trên hai pod tại threshold: counter, lock deadline, version chính xác.
- Một success cũ đến sau admin-disable không mở lại user.
- Redis failover, replication lag, event loss, service timeout: không silent bypass.
- Shared NAT/IPv6/enterprise proxy: false positive ở mức chấp nhận được và có lối challenge hợp lệ.
- Bot gửi body cực dài, header giả, username ngẫu nhiên: limiter và password hash không gây cạn CPU/thread.
- Load test `/login`, `/account/recovery` và `/otp/verify` với budgets độc lập.

### Spring Security MockMvc/integration

| Trường hợp | Kết quả phải kiểm chứng |
| --- | --- |
| Password đúng, bình thường | Tạo Authentication đúng và reset password counter |
| Password sai | Lỗi chung, một lần tăng counter |
| User không tồn tại | Không lộ qua body/status/timing |
| Temp-locked | Không cấp session mới, không extend deadline |
| Admin-disabled | Không tự mở khi timer hết |
| User qua password nhưng chưa MFA | Resource yêu cầu MFA bị từ chối |
| Đường unlock/recovery chưa đủ bằng chứng | Không mở khóa hoặc cấp quyền |
| Store lỗi | Báo infrastructure failure, không coi là sai password |
| Hai filter/handlers quan sát một failure | Không double-count |
| Multiple AuthenticationProviders | Không có đường bypass throttled provider |
| IP shared và botnet nhiều IP | Các limiter hoạt động đúng policy |
| Request bị WAF chặn | Không cần vào controller, có log/metric tương ứng |

Kiểm tra cả ranh giới HTTP: một controller được bảo vệ có thể trả 404 vì nghiệp vụ; không mặc định cứ auth hợp lệ thì response phải 200. Test gateway/WAF ngoài MockMvc vì request bị chặn ở edge không đi vào Spring MVC.

## 17. Metric và quy trình vận hành

Theo dõi những chỉ số ảnh hưởng **cả bảo mật và availability**:

- Tỷ lệ `login_attempts` thành công, sai credentials, throttled, locked và infrastructure error.
- Số **tài khoản thật bị khóa tạm**, tần suất repeated re-lock, trung vị/p95 thời gian bị chặn.
- Tỷ lệ khôi phục thành công, thời gian phục hồi, số lần user cần helpdesk.
- Số request password spraying từ một nguồn và thử phân tán vào một user.
- CPU password hashing, Redis latency, DB saturation, limiter error và request backlog.
- CAPTCHA fail/solve rate, accessibility complaints và false positives theo nhóm mạng hợp lệ.
- Số email/SMS cảnh báo và tín hiệu notification bombing.
- Chênh lệch kết quả giữa gateway/region và thời gian đồng bộ `lockedUntil`.

Không đưa raw username/email/password/OTP/session cookie vào metric label hoặc HTTP access log. Sử dụng cardinality thấp cho metric; audit chi tiết tách riêng có RBAC, redaction và thời gian giữ hợp lý. Nếu policy mới làm lock tăng đột biến ở user thật, cần feature flag/canary/rollback có kiểm soát chứ không âm thầm nới lỏng bảo vệ tất cả.

## 18. Checklist trước production

**Policy và chống DoS**

- [ ] Đã threat-model brute-force, stuffing, spraying, distributed attack và targeted lockout DoS.
- [ ] Account/IP/endpoint buckets tách biệt; hạn mức phù hợp loại user, MFA và chuẩn cần tuân thủ.
- [ ] Lock duration hữu hạn, không gia hạn từ request đã blocked, có phương án giảm repeated re-lock.
- [ ] Phân biệt temp lock, authenticator disabled và admin-disabled; không tự mở trạng thái admin.
- [ ] Có recovery/reauth bằng bằng chứng độc lập được xác thực; không có public unlock bypass.

**Kỹ thuật**

- [ ] UTC timestamp/`Instant`, test boundary, atomic store, unique key/TTL và version hoặc row locking.
- [ ] Tin địa chỉ nguồn chỉ qua trusted proxy; bảo vệ NAT, IPv6 và username normalization.
- [ ] Giới hạn tải trước password hashing, không sleep blocking dài trong servlet thread.
- [ ] Mỗi bad password chỉ tăng counter một lần; backend failures không bị tính như sai password.
- [ ] Response lỗi chung, không rò account existence, trạng thái locked hoặc thời điểm mở.
- [ ] Spring Security dùng phiên bản đã vá advisory tương ứng, test timing và nhiều security chains.
- [ ] Limiter store HA và có chính sách failure/degraded mode được phê duyệt, không silent bypass.

**Vận hành**

- [ ] Test multi-instance, race, DB/Redis outage, các nguồn botnet và mạng người dùng dùng chung.
- [ ] Password reset, OTP verify, recovery và notification cũng có chống abuse.
- [ ] Monitoring đo lockout amplification, false positives, recovery, throughput, CPU và latency.
- [ ] Có audit và feature rollout/rollback, không ghi secrets/PII vào telemetry.

**Kết luận:** Nếu chỉ cần vài mật khẩu sai để khóa tài khoản của bất kỳ ai, hệ thống đã trao cho attacker một công cụ DoS. Cách chống tấn công bền vững kết hợp **giới hạn độc lập theo account và nguồn, phản ứng tăng dần, thời hạn khóa xác định, state nguyên tử, đường khôi phục có xác thực và kiểm thử ở nhiều node**. Spring Security hỗ trợ phần kiểm tra danh tính và authorization; **chính sách throttle chống lockout DoS, lưu trữ, khôi phục và vận hành** phải được ứng dụng thiết kế.

## Tài liệu tham khảo

- [OWASP — Authentication Cheat Sheet (Account Lockout, Login Throttling)](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)
- [OWASP — Bot Management and Anti-Automation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html)
- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security — LockedException](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/LockedException.html)
- [Spring Security — CVE-2026-22746 User Attribute Enumeration](https://spring.io/security/cve-2026-22746/)
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)
