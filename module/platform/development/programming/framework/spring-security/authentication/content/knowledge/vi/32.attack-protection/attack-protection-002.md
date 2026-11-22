# Giới hạn tốc độ theo tài khoản, nguồn yêu cầu và dấu hiệu rủi ro

## 1. Bối cảnh: vì sao chỉ giới hạn theo IP là chưa đủ?

Một API đăng nhập trên Internet không chỉ đối mặt với người dùng nhập sai mật khẩu. Những cuộc tấn công thường gặp gồm **brute force** (thử nhiều mật khẩu cho một tài khoản), **password spraying** (thử một vài mật khẩu cho rất nhiều tài khoản), **credential stuffing** (thử cặp username/password bị lộ), dò tài khoản và lạm dụng tính năng gửi email/SMS/OTP.

Nếu chỉ đặt giới hạn “100 request/phút/IP”:

- Attacker có thể dùng hàng nghìn địa chỉ IP/proxy để thử cùng một tài khoản, tránh ngưỡng của từng IP.
- Một IP duy nhất vẫn có thể thử 1–2 lần trên hàng nghìn tài khoản, không vi phạm ngưỡng riêng của từng username nếu hệ thống chỉ theo tài khoản.
- Người dùng thật ở văn phòng, trường học hoặc mạng di động dùng chung một NAT có thể bị khóa vì hoạt động của người khác.
- Tác vụ xác thực qua endpoint khác như `/login`, `/api/authenticate`, `/mfa/verify` hoặc `/password/reset` có thể trở thành đường vòng nếu không được bảo vệ nhất quán.

Giải pháp là kết hợp **các bộ đếm độc lập theo tài khoản, nguồn yêu cầu, phạm vi dịch vụ và tín hiệu rủi ro**, rồi chọn hành động thích hợp. Mục tiêu là hạn chế khả năng tự động thử credential mà vẫn bảo vệ người dùng hợp lệ khỏi khóa nhầm hoặc tấn công từ chối dịch vụ.

Bài thuộc mục **Chống tấn công** của module **Spring Security - authentication**, sử dụng Java 17+, Spring Security 6.x/Spring Boot 3.x ở các ví dụ tích hợp Servlet/Spring MVC. Các thuật toán và quy tắc thiết kế vẫn áp dụng cho hệ thống dùng OIDC, API token và MFA, nhưng điểm tích hợp tùy luồng.

## 2. Phân biệt các kiểu tấn công để chọn khóa giới hạn

| Kiểu tấn công | Mô thức lưu lượng | Chỉ giới hạn theo IP? | Chỉ giới hạn theo tài khoản? |
| --- | --- | --- | --- |
| Brute force một user | Nhiều mật khẩu thử trên cùng username | Có thể bị vượt qua bằng botnet | Hữu ích nhưng dễ gây lockout DoS |
| Password spraying | Một mật khẩu thử trên nhiều username | Phát hiện tốt nguồn tập trung; không đủ với IP phân tán | Mỗi tài khoản ít lần nên có thể không chạm ngưỡng |
| Credential stuffing | Rất nhiều cặp username/password bị lộ | Chặn một phần; proxy rotation phá hiệu quả | Chặn một phần; mỗi account có ít lần |
| Username enumeration | Quan sát khác biệt status/timing hoặc thông báo | Không ngăn logic lộ sự tồn tại tài khoản | Counter/response thiếu nhất quán có thể làm lộ user |
| OTP/OTT abuse | Xin gửi mã nhiều lần, thử mã hoặc kích hoạt SMS/email tốn phí | IP limit chưa đủ | Per-recipient, per-account, per-device, per-channel quan trọng |
| Distributed low-and-slow | Thử ít, rải thời gian và nhiều nguồn | Ngưỡng ngắn hạn khó thấy | Cần cửa sổ dài hơn và risk signals |

**Không chọn một khóa tổng hợp duy nhất `IP + username` thay cho cả hai khóa riêng.** Nếu dùng một bucket `login:ip1:alice`, cùng IP có thể thử tối đa ngưỡng cho Alice, rồi Bob, rồi Carol... mà không có giới hạn tổng theo nguồn. Cũng có thể đổi IP liên tục cho cùng Alice. Hãy **kiểm riêng `account` và `source`**, sau đó có thể thêm bucket cặp `(account,source)` làm tín hiệu phụ.

## 3. Ma trận nhiều chiều: tài khoản, nguồn và rủi ro

Một lần `POST /login` có thể được đánh giá theo:

1. **Tài khoản hoặc định danh được gửi:** giới hạn tổng số lần thử cho cùng username đã chuẩn hóa, bất kể IP. Áp dụng thống nhất cả với tên tài khoản chưa tồn tại.
2. **Nguồn yêu cầu đáng tin:** IP khách đã được chuẩn hóa qua biên proxy tin cậy; có thể thêm subnet, ASN, egress network hoặc credential client đã được xác minh.
3. **Toàn endpoint/tenant:** giới hạn tổng lưu lượng đăng nhập để tránh làm cạn CPU (password hashing), database hoặc IdP; có lớp bảo vệ hạ tầng trước backend.
4. **Cặp account–source:** phát hiện một nguồn cố thử nhiều lần trên một account; **chỉ bổ sung**, không thay hai trục chính.
5. **Device/session cookie:** giúp phân biệt các luồng thông thường nhưng dễ bị xóa hoặc giả; không được là bằng chứng duy nhất.
6. **Dấu hiệu rủi ro:** số username khác nhau từ một nguồn, nguồn mới, bot signal, tỷ lệ thất bại, địa chỉ đã biết lạm dụng, thiết bị bất thường, IP reputation và sự kiện bảo mật gần đây.

### 3.1. Kiểm đồng thời, không kiểm lần lượt bằng OR

Cho các bucket độc lập `B_account`, `B_source`, `B_global` và điều kiện bổ sung `R(request)`. Một request được phép đi đến password verifier chỉ khi **tất cả các điều kiện bắt buộc** đạt:

```text
allowed =
    accountBudgetAvailable
    AND sourceBudgetAvailable
    AND globalBudgetAvailable
    AND riskPolicyAllowsOrChallengeCompleted
```

Nếu chỉ một bucket đã hết, từ chối/challenge trước khi tốn CPU xác minh mật khẩu. Với hệ thống phân tán, nên **kiểm và trừ token ở các bucket liên quan một cách nguyên tử**, tránh request đồng thời vượt giới hạn hoặc trừ một bucket dù request cuối cùng bị chặn bởi bucket khác.

Bảng ngưỡng **minh họa để thảo luận**, không phải giá trị chuẩn dùng cho mọi sản phẩm:

| Bucket | Ví dụ chính sách | Mục tiêu |
| --- | --- | --- |
| Per account | 5 yêu cầu/10 phút; theo dõi thêm thất bại 24 giờ | Hạn chế brute force phân tán |
| Per source/IP | 20 yêu cầu/1 phút và 200/1 giờ | Giảm credential stuffing từ một nguồn |
| Global login | Giới hạn theo dung lượng máy chủ/IdP | Chống nghẽn hạ tầng |
| Account × source | 3 lỗi/5 phút | Thêm tín hiệu về một cặp lặp lại |
| OTP send | 3 lần/10 phút/recipient + giới hạn nguồn và chi phí | Ngăn spam/SMS pumping |
| High-risk source | Ngưỡng thấp hơn hoặc bước thử thách | Bảo vệ khi có nhiều tín hiệu đáng tin |

**Phải hiệu chỉnh** ngưỡng dựa trên traffic thật, số người dùng sau NAT, đặc điểm mobile, SLO và độ nhạy của thao tác. Không chọn cố định 5 lần là khóa tài khoản vĩnh viễn; attacker có thể cố ý khóa hàng loạt tài khoản để gây DoS.

## 4. Chọn thuật toán: fixed window, sliding window, token bucket

### 4.1. Fixed-window counter

Đếm request trong các khung như 00:00–00:59, 01:00–01:59. Dễ triển khai, nhưng attacker có thể gửi sát cuối và đầu hai cửa sổ để có gần gấp đôi số request trong một khoảng ngắn. Dùng fixed window chỉ khi chấp nhận burst ở biên hoặc có lớp bảo vệ bổ sung.

### 4.2. Sliding window

Một cửa sổ trượt tính các lần thử trong **60 giây gần nhất**. Cài bằng timestamps hoặc xấp xỉ theo hai cửa sổ. Sliding log chính xác nhưng dùng bộ nhớ theo số sự kiện; sliding-window counter xấp xỉ gọn hơn.

Ví dụ budget 3 lần/60 giây cho Alice:

```text
Thời điểm (giây):  0     10     20     30                 60
                   |      |      |      |                  |
Alice              OK     OK     OK     BLOCK            thử lại
Count              1      2      3      3                  0/1
```

Khi đã có 3 lần ở giây 0,10,20, lần ở giây 30 bị chặn. Sau đúng 60 giây, sự kiện ở thời điểm 0 rời cửa sổ nếu quy ước xóa `timestamp <= now-window`; lúc đó một lượt mới có thể được phép.

### 4.3. Token bucket

Bucket có sức chứa `C`, bổ sung `r` token/giây, mỗi request tiêu thụ một token. Lượng token gần đúng:

```text
tokens(now) = min(C, tokens(previous) + r * elapsedSeconds)
allow if tokens(now) >= cost
```

Token bucket hỗ trợ burst có kiểm soát và tốc độ trung bình dài hạn; phù hợp API throughput. Login throttling thường cần thêm **failure history** và chính sách account riêng vì các nguồn rải rác có thể tránh giới hạn ngắn.

### 4.4. Exponential backoff và progressive challenge

Không phải mọi dấu hiệu xấu đều cần khóa cứng. Có thể tăng khoảng trì hoãn/challenge theo số lỗi:

```text
delay = min(cap, base * 2^(failures - threshold))
```

Cần cẩn thận tràn số, jitter, giới hạn chờ và không chiếm worker thread bằng `Thread.sleep(...)` cho mỗi request (dễ bị DoS). Tốt hơn là trả 429/challenge từ gateway hoặc state machine thay vì giữ connection chờ. Với rủi ro thấp, chỉ quan sát; với rủi ro vừa, step-up bằng MFA hoặc bot challenge; với rủi ro cao, từ chối có thời hạn và cảnh báo.

## 5. Định danh tài khoản mà không gây username enumeration

Một request login chứa `username` **chưa được xác thực**. Nó vẫn hữu ích để giới hạn theo account-key, nhưng không được dùng bừa bãi:

- Chuẩn hóa tên theo đúng quy tắc của hệ thống identity: whitespace, case sensitivity, Unicode normalization, email alias nếu có. **Không** tự biến mọi username thành lowercase khi kho tài khoản của hệ thống phân biệt hoa/thường.
- Giới hạn độ dài input và body trước khi tạo khóa để tránh attacker buộc tạo key Redis vô hạn, làm nghẽn log hoặc memory.
- Với username chưa tồn tại, vẫn tính budget và dùng phản hồi/timing tương tự username tồn tại, để không biến “bucket nào bị khóa” thành oracle dò account.
- Không lưu username/email nguyên văn vào metrics label, Redis key dễ truy xuất hoặc log. Thường lưu **HMAC-SHA256(normalizedIdentifier, serverSecret)** hoặc ID nội bộ sau khi đã xác minh chính sách lookup; HMAC làm giảm rò rỉ từ điển khi namespace username dễ đoán.
- Có thể dùng tenant ID đáng tin trong key; tenant do client khai chưa xác thực phải được xác minh trước khi đưa vào chính sách quyền.
- Thông báo public phải chung chung (“Quá nhiều yêu cầu. Thử lại sau.”); không tiết lộ account có tồn tại, có bị khóa hay còn mấy lần.
- Account bị throttled có nguy cơ bị attacker gây từ chối dịch vụ bằng cách liên tục gửi sai password. Có thể dùng challenge/step-up hoặc kênh khôi phục được bảo vệ, thay vì khóa vĩnh viễn theo input username chưa xác thực.

**Đừng xóa mọi giới hạn ngay khi login thành công.** Có thể reset bộ đếm **thất bại** sau xác thực mạnh hợp lệ, nhưng vẫn giữ budget tổng request theo IP/account và rủi ro của nguồn. Nếu reset tất cả buckets, một attacker có một credential đúng có thể tạo kẽ hở tăng tốc hoặc chiếm tài nguyên.

## 6. Xác định nguồn IP khi có reverse proxy

Dùng `request.getRemoteAddr()` sẽ trả IP của peer kết nối tới servlet. Sau load balancer/reverse proxy, đó có thể là **IP proxy**, khiến mọi người dùng cùng một bucket. Nhưng trực tiếp tin `X-Forwarded-For` từ client cũng nguy hiểm: attacker có thể tự thay đổi IP khai báo ở mỗi request để né giới hạn.

Thiết kế đúng:

1. Cấu hình mạng để backend chỉ nhận kết nối từ gateway/proxy được phép, hạn chế truy cập trực tiếp.
2. **Tại trust boundary**, gateway phải xóa mọi `Forwarded` và `X-Forwarded-*` do client gửi, rồi tạo mới chuỗi hop đáng tin; không chắp thêm vô điều kiện một giá trị do client cung cấp.
3. Cấu hình ứng dụng/container hiểu forwarded headers **chỉ từ proxy tin cậy**; có thể dùng cơ chế xử lý forwarded headers của Spring Framework/Servlet container. Không tự lấy phần tử đầu/cuối của header mà không biết topology proxy.
4. Chuẩn hóa IPv4/IPv6, xử lý dual-stack, IPv6 privacy address và giới hạn prefix phù hợp; không ghép username và IP thô dài vào Redis key.
5. Kiểm tra hành vi với Nginx/Ingress/CDN thực tế, IPv6, nhiều hop và request không qua proxy trong staging.

**Lưu ý:** `ForwardedHeaderFilter` chỉ hữu ích khi biên mạng đã được bảo vệ và headers đã được sanitize; bản thân filter không thể phân biệt header thật/giả nếu request có thể tới trực tiếp từ Internet.

Per-IP giúp giảm lưu lượng từ một nguồn, nhưng không đủ để chặn attacker dùng botnet và có thể làm ảnh hưởng người dùng NAT. Vì vậy đây là **một trục**, không phải lý do để bỏ per-account và rủi ro.

## 7. Dấu hiệu rủi ro: bổ sung, không thay thế kiểm chứng

Một bộ phát hiện rủi ro có thể quan sát:

- Nhiều username khác nhau bị thử từ cùng IP/subnet/ASN trong thời gian ngắn (spraying).
- Một account bị thử từ nhiều nguồn mới hoặc có tốc độ tăng đột biến (distributed guessing).
- Lượng lỗi so với success; tần suất 429, CAPTCHA failures, user-agent/header bất thường.
- Thiết bị/trình duyệt mới, session cookie mới, IP reputation đã được kiểm chứng.
- Vị trí/ASN quá khác với lịch sử sử dụng, đăng nhập từ khu vực khó phù hợp với thời gian trước đó.
- Account quyền cao, giao dịch nhạy cảm, đăng nhập khi đang có cảnh báo credential bị lộ.
- Sự kiện xác thực khác như login thất bại MFA, yêu cầu gửi OTT nhiều lần, password reset, token reuse.

**Risk score không phải bằng chứng danh tính.** Fingerprint, user-agent, cookie và vị trí dễ sai, bị giả hoặc gây tác động không công bằng. Rủi ro phải được kết hợp với yếu tố đã xác thực, cùng UX khôi phục hợp lý; không tự cấp `ROLE_ADMIN` hoặc bỏ MFA chỉ vì IP được đánh giá “tốt”.

Mô hình chính sách minh họa:

| Mức rủi ro | Chính sách gợi ý | Điều phải bảo đảm |
| --- | --- | --- |
| Thấp | Budgets cơ bản; login bình thường | Vẫn kiểm password/hash, CSRF/session và quyền |
| Vừa | Hạ ngưỡng mềm, yêu cầu challenge hoặc MFA bổ sung | Không cung cấp oracle xác định username |
| Cao | Tạm từ chối, kích hoạt alert, yêu cầu recovery được bảo vệ | Không khóa vĩnh viễn do tín hiệu dễ giả |
| Rất cao / tấn công diện rộng | Bảo vệ edge, limit toàn dịch vụ, cách ly traffic xấu | Không làm outage người dùng hợp lệ |

Ví dụ risk service trả `StepUpRequired`; ứng dụng **không** chấp nhận POST có `risk=low` hoặc `X-Trusted-Device=true` do client tự đặt. Một challenge chỉ được coi là hoàn thành khi backend hoặc IdP kiểm chứng kết quả.

## 8. Ở đâu trong kiến trúc Spring Security?

Một request login `POST /login` thông thường được Spring Security xử lý bởi `UsernamePasswordAuthenticationFilter`, tạo `UsernamePasswordAuthenticationToken` rồi gọi `AuthenticationManager`; provider dùng `UserDetailsService` và `PasswordEncoder` để xác thực.

Đặt throttle theo hai lớp bổ sung:

```text
Internet → CDN/WAF/Gateway
             | quota nguồn, vùng mạng, bot mitigation, global capacity
             v
        Servlet/Spring Security
             | before authentication:
             |  - normalized submitted account
             |  - trusted source
             |  - risk & multi-key reserve
             |  - nếu vượt: 429/challenge
             v
   UsernamePasswordAuthenticationFilter
             | AuthenticationManager/Provider
             v
      success/failure events
             | update failure history, user/device risk, telemetry
             v
         session / MFA / authorization
```

**Không chỉ ghi nhận `AuthenticationFailureEvent` rồi mới giới hạn:** event xảy ra sau khi đã xử lý credential, có thể đã tốn CPU BCrypt/Argon2. Bộ lọc **pre-auth** chặn request trước bước hash, còn các event/handler phản ánh outcome để cập nhật risk.

**Không phải Spring Security mặc định cung cấp một bộ throttling đa chiều hoàn chỉnh.** Framework có filter chain, handler và events làm điểm tích hợp; thuật toán bucket, lưu trữ Redis, account policy, risk engine và observability là phần ứng dụng/hạ tầng phải xây hoặc tích hợp từ thư viện phù hợp.

### 8.1. Những điểm tích hợp thường dùng

| Điểm tích hợp | Thời điểm | Phù hợp để làm gì? |
| --- | --- | --- |
| CDN/WAF/API gateway | Trước app | Rate limit volumetric, IP/ASN, bot signals |
| `OncePerRequestFilter` trước authentication filter | Trước password verifier | Kiểm budgets account + IP, 429 nhanh |
| `AuthenticationFailureHandler` | Sau login sai | Ghi failure risk, phản hồi UI thống nhất |
| `AuthenticationSuccessHandler` | Sau login đúng | Ghi success, cập nhật risk/session |
| `AuthenticationEventPublisher` và event listener | Sau provider emit event | Telemetry và policy dùng chung nhiều phương thức |
| Method/service authorization | Sau authentication | Chặn thao tác nhạy cảm khi cần MFA, tenant policy |
| Async analytics | Sau xử lý | Tổng hợp pattern và điều chỉnh ngưỡng |

Khi dùng cả failure handler và event listener, phải tránh **đếm một lần lỗi thành hai lần**. Chọn một nguồn outcome authoritative hoặc gắn event ID/idempotency.

## 9. Chương trình Java 17 chạy độc lập: hai bucket riêng biệt

Ví dụ dưới đây hiện thực **sliding-window log** trong một tiến trình Java với hai giới hạn độc lập: tối đa **3 lần/phút/tài khoản** và **5 lần/phút/nguồn**. Nó có synchronized để kiểm hai bucket trong một thao tác trên JVM và có thời gian giả lập để stdout xác định.

**Đây là demo thuật toán, không phải giải pháp production:** Map không có TTL/xóa key định kỳ, không dùng Redis, không giải quyết multi-instance, normalization/HMAC, quota toàn cục hay risk engine. Tài khoản và nguồn trong demo đã được chuẩn hóa trước.

**`DualAxisLimiter.java`**

```java
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DualAxisLimiter {

    record Rule(String key, int limit, long windowMillis) {}
    record Decision(boolean allowed, long retryAfterMillis) {}

    private final Map<String, ArrayDeque<Long>> timestamps = new HashMap<>();

    public synchronized Decision acquire(
            String accountKey, String sourceKey, long nowMillis) {

        List<Rule> rules = List.of(
                new Rule("account:" + accountKey, 3, 60_000),
                new Rule("source:" + sourceKey, 5, 60_000));

        long retryAfter = 0;
        for (Rule rule : rules) {
            ArrayDeque<Long> hits =
                    timestamps.computeIfAbsent(
                            rule.key(), unused -> new ArrayDeque<>());
            while (!hits.isEmpty()
                    && hits.peekFirst() <= nowMillis - rule.windowMillis()) {
                hits.removeFirst();
            }
            if (hits.size() >= rule.limit()) {
                long wait = hits.peekFirst()
                        + rule.windowMillis() - nowMillis;
                retryAfter = Math.max(retryAfter, wait);
            }
        }

        // Giữ tính nguyên tử: nếu một bucket đầy, không ghi vào bucket còn lại.
        if (retryAfter > 0) {
            return new Decision(false, retryAfter);
        }
        for (Rule rule : rules) {
            timestamps.get(rule.key()).addLast(nowMillis);
        }
        return new Decision(true, 0);
    }

    private static void print(
            DualAxisLimiter limiter,
            String label, String user, String source, long nowMillis) {
        System.out.println(label + " = "
                + limiter.acquire(user, source, nowMillis).allowed());
    }

    public static void main(String[] args) {
        DualAxisLimiter limiter = new DualAxisLimiter();
        long t = 1_000L;

        print(limiter, "alice/ip1", "alice", "ip1", t);
        print(limiter, "alice/ip2", "alice", "ip2", t);
        print(limiter, "alice/ip3", "alice", "ip3", t);
        print(limiter, "alice/ip4", "alice", "ip4", t);

        print(limiter, "bob/ip1", "bob", "ip1", t);
        print(limiter, "carol/ip1", "carol", "ip1", t);
        print(limiter, "dave/ip1", "dave", "ip1", t);
        print(limiter, "eve/ip1", "eve", "ip1", t);
        print(limiter, "frank/ip1", "frank", "ip1", t);

        print(limiter, "alice/after60s", "alice", "ip4", t + 60_000);
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac DualAxisLimiter.java
java DualAxisLimiter
```

Stdout chính xác:

```text
alice/ip1 = true
alice/ip2 = true
alice/ip3 = true
alice/ip4 = false
bob/ip1 = true
carol/ip1 = true
dave/ip1 = true
eve/ip1 = true
frank/ip1 = false
alice/after60s = true
```

**Giải thích:** Alice đã dùng 3 lượt dù đến từ ba IP khác nhau nên bị chặn ở IP4. IP1 đã có Alice/Bob/Carol/Dave/Eve (5 lượt) nên Frank bị chặn dù account Frank chưa có lần thử nào. Sau 60 giây, các timestamps cũ hết hạn và Alice có thể thử lại.

Trong hệ thống thật, phải giới hạn memory/key cardinality, tránh thời gian đi ngược, dùng nguồn đồng hồ nhất quán và lưu state chia sẻ giữa nhiều instance. Cơ chế này đếm **mọi lần thử**, không chỉ password sai, nên cần chính sách UX chống account lockout DoS.

## 10. Spring Security Servlet: chặn trước form login

Ví dụ tích hợp **có thể biên dịch sau khi cung cấp implementation của `LoginGate`** (Redis/bucket store được quản lý). Nó chủ ý tách **contract/adapter** khỏi backend limiter để tránh giả vờ một Map local đã giải quyết bài toán multi-instance.

### 10.1. Hợp đồng giữa filter và throttle service

**`LoginGate.java`**

```java
package com.example.loginprotection;

public interface LoginGate {

    record Decision(boolean allowed, long retryAfterSeconds) {}

    // Service chịu trách nhiệm chuẩn hóa/HMAC username, source và
    // kiểm + giữ chỗ các bucket bắt buộc nguyên tử.
    Decision reserve(String submittedUsername, String trustedSourceAddress);

    // Ghi sự kiện thành công/thất bại vào risk/failure counters.
    // Không dùng kết quả này để xóa per-IP hoặc per-attempt budgets.
    void recordOutcome(String submittedUsername,
                       String trustedSourceAddress,
                       boolean success);
}
```

Implementation cần tạo Redis keys từ identifier chuẩn hóa bằng cùng quy tắc lookup của identity system; riêng phần raw username trong interface **chỉ nằm trong bộ nhớ request**, không được log hoặc đưa vào metric label. `trustedSourceAddress` là IP đã qua trust boundary, không đọc tùy ý `X-Forwarded-For`.

### 10.2. Filter tiền xác thực

**`LoginRateLimitFilter.java`**

```java
package com.example.loginprotection;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public final class LoginRateLimitFilter extends OncePerRequestFilter {

    private final LoginGate gate;

    public LoginRateLimitFilter(LoginGate gate) {
        this.gate = gate;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !("POST".equals(request.getMethod())
                && "/login".equals(request.getServletPath()));
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        final LoginGate.Decision decision;
        try {
            decision = gate.reserve(
                    request.getParameter("username"),
                    request.getRemoteAddr());
        } catch (RuntimeException failure) {
            // Tránh cho qua khi không thể kiểm giới hạn.
            response.sendError(
                    HttpServletResponse.SC_SERVICE_UNAVAILABLE);
            return;
        }

        if (!decision.allowed()) {
            response.setStatus(429);
            response.setContentType("application/json;charset=UTF-8");
            response.setHeader("Cache-Control", "no-store");
            // Không tiết lộ account / bucket nào đã hết.
            response.getWriter().write(
                    "{\"error\":\"Too many attempts. Try again later.\"}");
            return;
        }

        chain.doFilter(request, response);
    }
}
```

**Điều kiện để đoạn code đúng trong app thật:**

- Chỉ dùng cho `POST /login` mặc định; nếu thay `loginProcessingUrl`, cần đổi matcher tương ứng. `getServletPath()` phụ thuộc Servlet mapping/context path.
- Gateway phải giới hạn request body và chuẩn hóa remote address trước khi filter đọc parameter.
- Lớp `LoginGate` phải check **cả account và source** (và global bucket nếu có), dùng storage shared/atomic. Không bọc mọi lỗi rồi “cho qua nếu Redis down”.
- Trả 429 với thông báo chung. Nếu dùng `Retry-After`, chọn thời gian làm tròn thích hợp, không tiết lộ bucket, số lượt còn lại hoặc username.
- Nếu chưa có username/username quá dài, service phải có chính sách đầu vào riêng và vẫn áp source/global limit. Không gán tất cả input trống vào một khóa account làm khóa người dùng khác.
- Không tạo filter thành `@Component`/`@Bean Filter` để Boot đăng ký toàn cục nếu đồng thời dùng `addFilterBefore`; tạo instance trong chain hoặc vô hiệu đăng ký Servlet tự động.

### 10.3. Ghép vào SecurityFilterChain và theo dõi outcome

**`SecurityConfig.java`**

```java
package com.example.loginprotection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, LoginGate gate) throws Exception {

        var success = new SavedRequestAwareAuthenticationSuccessHandler();
        var failure = new SimpleUrlAuthenticationFailureHandler("/login?error");

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .successHandler((request, response, auth) -> {
                            gate.recordOutcome(
                                    request.getParameter("username"),
                                    request.getRemoteAddr(),
                                    true);
                            success.onAuthenticationSuccess(
                                    request, response, auth);
                        })
                        .failureHandler((request, response, exception) -> {
                            gate.recordOutcome(
                                    request.getParameter("username"),
                                    request.getRemoteAddr(),
                                    false);
                            failure.onAuthenticationFailure(
                                    request, response, exception);
                        }))
                .addFilterBefore(
                        new LoginRateLimitFilter(gate),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
```

**Hành vi:** filter chặn trước `UsernamePasswordAuthenticationFilter` nên không thực hiện password hash nếu đã vượt budget. Sau một lần đăng nhập thực sự qua form login, success/failure handlers cập nhật tín hiệu outcome; không đếm lần nữa qua listener nếu không có idempotency. `/login` được phép truy cập anonymous nhưng **throttle filter vẫn xử lý POST**; `permitAll()` không có nghĩa bỏ qua custom filter.

Code trên là **mảnh tích hợp Spring Boot 3.x / Security 6.x** trong một project có web/security dependencies, user store, password encoder và **LoginGate implementation do ứng dụng cung cấp**. Không phải một hệ thống có Redis limiter sẵn; phải cài đặt thêm backend và thử thực tế. Browser form login mặc định vẫn sử dụng CSRF protection. Với MockMvc POST /login, cung cấp CSRF token khi test.

**Bảo vệ lỗi outcome:** trong app production, `recordOutcome` nên có cơ chế xử lý lỗi quan sát được và tính idempotent; không cho backend telemetry không quan trọng phá vỡ việc xác thực đã thành công theo cách khó dự đoán. Nhưng lỗi **reserve** trước kiểm mật khẩu phải đi theo fail-closed hoặc degraded control được phân tích rủi ro rõ ràng, không mặc định permit.

## 11. Lưu state phân tán: Redis và thao tác nguyên tử

Một Map/ConcurrentHashMap trong từng instance **không đủ** khi có nhiều pod. Attacker có thể gửi request song song đến nhiều instance, mỗi instance tự đếm và cho phép số lượt lớn hơn giới hạn. Thường dùng Redis với TTL và primitive nguyên tử (Lua/function), hoặc dịch vụ rate limit tập trung tại gateway.

### 11.1. Cấu trúc keys

Ví dụ service đã HMAC username thành chuỗi ngắn:

```text
rl:login:acct:<HMAC(normalizedUsername)>      # mọi nguồn trên cùng account
rl:login:src:<normalizedSourceId>             # mọi account từ cùng nguồn
rl:login:global                               # bảo vệ tổng endpoint
rl:login:pair:<accountDigest>:<sourceDigest>  # tùy chọn, không thay 2 trục
```

Trong production, dùng Redis hash tags/sharding phù hợp nếu dùng một script nhiều key trên Redis Cluster: các KEYS của một lệnh Lua atomic **phải nằm trên cùng hash slot** hoặc đổi kiến trúc. Không dồn vô điều kiện toàn bộ traffic vào một hot slot/key nếu hệ thống cần scale lớn; có thể chuyển một số lớp bảo vệ sang gateway, dùng quota hierarchical và chiến lược phân vùng rõ ràng.

### 11.2. Lua sliding-window log minh họa

Đây là **Lua script minh họa cho Redis đơn node hoặc tập KEYS cùng slot**; mỗi key là Sorted Set chứa timestamp của các lượt đã được chấp nhận. Cần unique attempt ID để không bị `ZADD` ghi đè phần tử cùng thời điểm.

Đầu vào: `KEYS[1]` account, `KEYS[2]` source; `ARGV[1]` windowMilliseconds; `ARGV[2]` unique random attemptId; `ARGV[3]` limit account; `ARGV[4]` limit source. Đồng hồ lấy từ Redis `TIME` để giảm lệch thời gian giữa app nodes.

```lua
local clock = redis.call("TIME")
local now = tonumber(clock[1]) * 1000
          + math.floor(tonumber(clock[2]) / 1000)

local window = tonumber(ARGV[1])
local attemptId = ARGV[2]
local limits = { tonumber(ARGV[3]), tonumber(ARGV[4]) }
local boundary = now - window

for i = 1, 2 do
    redis.call("ZREMRANGEBYSCORE", KEYS[i], "-inf", boundary)
end

for i = 1, 2 do
    if redis.call("ZCARD", KEYS[i]) >= limits[i] then
        return {0, now}
    end
end

for i = 1, 2 do
    redis.call("ZADD", KEYS[i], now, attemptId)
    redis.call("PEXPIRE", KEYS[i], window)
end

return {1, now}
```

Tính nguyên tử: nếu **một** bucket hết, script không `ZADD` vào **bất kỳ** bucket nào; nếu còn cả hai, ghi hai lượt trong một thao tác Redis. `attemptId` phải duy nhất cho từng request, không phải username hoặc timestamp (nhiều request có cùng millisecond).

**Các điều còn thiếu để chạy production:** kiểm kiểu/dải ARGV; khống chế key cardinality và memory, max payload, TTL, Redis eviction policy, có thể hạn chế Lua execution time, metrics; error handling và retry idempotency cho request khi timeout; thiết kế khi Redis failover/partition, limit nhiều window, global quota và risk score. Với Redis Cluster, dùng cùng slot hoặc chuyển cách tính cho phù hợp; không dùng script xuyên nhiều slot rồi giả định transaction toàn cluster.

Một điểm dễ bỏ sót: nếu Redis request thành công nhưng network response bị mất, client retry với **attemptId mới** sẽ tiêu tốn thêm quota. Cần chính sách idempotency, retry và xử lý lỗi phù hợp. Bucket state phải không tồn tại mãi cho mọi username ngẫu nhiên; có TTL và limit tổng trên ingress.

### 11.3. Dữ liệu không nên lưu

Không lưu mật khẩu, OTP, bearer token, cookie session trong key, value hoặc logs. Không dùng email/username thô làm metric label có cardinality lớn. Chỉ đo nhóm sự kiện: `allowed`, `limited_by_account`, `limited_by_source` (internal only), `challenge_required`, `redis_error`, `login_success` và `login_failure` với sampling/privacy phù hợp.

## 12. Những lưu ý về kết quả thành công và thất bại

**Pre-auth attempt budget** và **failure history** không giống nhau:

- Attempt budget chặn tiêu hao tài nguyên **trước** khi password hash, đếm cả request đúng/sai.
- Failure history chỉ cập nhật khi authentication thực sự **thất bại**, giúp tính rủi ro và delay/challenge.
- Success event dùng để ghi nhận hành vi hợp lệ và có thể giảm độ nghi ngờ ở account/device, nhưng không xóa sạch tín hiệu rủi ro của IP/botnet.

Spring Security 6.5 hỗ trợ `AuthenticationFailureEvent`, `AuthenticationSuccessEvent` khi cấu hình `AuthenticationEventPublisher`; có thể dùng `DefaultAuthenticationEventPublisher` rồi `@EventListener`. Form login còn có `AuthenticationFailureHandler` / `AuthenticationSuccessHandler`.

Ví dụ cấu hình publisher (nếu ứng dụng muốn thu thập events ở cấp provider):

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    return new DefaultAuthenticationEventPublisher(publisher);
}
```

Đây là **snippet đặt bên trong class @Configuration** với imports từ `org.springframework.security.authentication.AuthenticationEventPublisher`, `DefaultAuthenticationEventPublisher` và `org.springframework.context.ApplicationEventPublisher`, không phải Java file chạy độc lập. Nếu có event listener, đừng đếm outcome cả ở handlers **và** listeners mà không có idempotency.

Lưu ý khi xác thực external OIDC, API key, client credentials hoặc WebAuthn: sự kiện và vị trí username có thể khác form login. Không giả định mọi `Authentication.getName()` đều là email người dùng hay mọi failure có principal tồn tại. Việc rate limit password endpoint và callback OAuth2 cần các khóa/chính sách khác nhau.

## 13. MFA, CAPTCHA và các tuyến khôi phục

### 13.1. MFA làm giảm giá trị của mật khẩu bị lộ

MFA, nhất là phương thức chống phishing phù hợp, giúp giảm account takeover khi mật khẩu bị dò hoặc bị lộ. Tuy nhiên MFA không thay limiter: attacker vẫn có thể gây tốn CPU, spam push/OTP hoặc khóa tài khoản.

Risk-based step-up có thể yêu cầu MFA khi thiết bị mới, nguồn bất thường hoặc hành động nhạy cảm. Không cấp quyền bỏ qua MFA chỉ vì IP trong allowlist nếu chính sách yêu cầu xác thực mạnh hơn.

### 13.2. CAPTCHA chỉ là lớp bổ sung

CAPTCHA có thể làm tăng chi phí automation nhưng có dịch vụ giải hộ và kỹ thuật bypass. Không dùng `captchaPassed=true` gửi bởi client để bỏ rate limit; server phải xác minh challenge, ràng buộc request/session và TTL. Với người dùng dùng trình đọc màn hình, mạng chậm hoặc VPN, cần giải pháp accessibility và recovery.

### 13.3. Đường reset password và gửi mã là mục tiêu riêng

Đối với `/forgot-password`, `/reset-password`, `/otp/send`, `/otp/verify` hoặc magic-link generation:

- Theo dõi **recipient/account**, **IP/source**, số đích khác nhau, thiết bị, kênh gửi và global cost.
- Trả thông báo chung dù account có tồn tại hay không; tránh dùng bộ đếm account mà tạo oracle.
- Khống chế tần suất gửi và xác thực OTP, TTL, một lần dùng, chống replay, chi phí SMS.
- Khi account đang bị login throttled, quy trình khôi phục phải được bảo vệ riêng, không tự trở thành lối tắt xác thực yếu.
- Không dùng chung một ngưỡng cho GET trang login và POST password, vì nhu cầu và chi phí khác nhau.

Tương tự, `/mfa/verify` cần limit số lần đoán mã theo user/transaction/credential, không chỉ theo IP. Một mã OTP có không gian nhỏ đòi chống brute force mạnh hơn endpoint nhập password có entropy cao.

## 14. Chính sách trả về 429, 401 và 403

| Trường hợp | Phản hồi thường gặp | Ghi chú |
| --- | --- | --- |
| Vượt rate limit trước xác thực | `429 Too Many Requests` | Thông báo chung, có thể `Retry-After` làm tròn |
| Username/password sai nhưng còn budget | Login thất bại bình thường | Web form thường redirect lỗi; API có thể 401 |
| Đăng nhập thành công | Theo flow login | Session/context được Spring Security tạo |
| User đã xác thực nhưng không có quyền | `403 Forbidden` | Authorization; không phải password failure |
| Dịch vụ limiter không khả dụng | `503` hoặc degraded mode fail-closed | Quy định theo risk/SLO; không mặc định permit |
| OTP sai quá nhiều lần | Chặn/challenge theo OTP policy | Không để OTP thử vô hạn |
| User bị khóa hoặc account không tồn tại | Phản hồi generic | Không biến chi tiết nội bộ thành username oracle |

Với web form, không phải lúc nào cũng nên trả JSON 429 vì browser cần UX phù hợp. Có thể hiển thị trang thông báo chung hoặc challenge, nhưng không tiết lộ “tài khoản tồn tại”, “nguồn nào đã bị chặn”, số lần còn lại chính xác. Nếu dùng header `Retry-After`, không cung cấp thời điểm chính xác đủ để attacker tự đồng bộ tấn công.

**Phân biệt limiter error với authentication failure:** nếu Redis outage, không tăng “sai password” cho hàng triệu account. Ngược lại, khi account thiếu credential, không trả thông báo cho biết account có nằm trong DB.

## 15. Kiểm thử nhiều trục trong Spring Security

### 15.1. Bảng test bắt buộc

| Tình huống | Điểm cần chứng minh |
| --- | --- |
| Nhiều mật khẩu trên 1 username từ nhiều IP | Per-account budget chặn dù đổi nguồn |
| Một IP thử nhiều username khác nhau | Per-source budget chặn dù account nào cũng ít lượt |
| Một cặp account/IP lặp liên tục | Không vượt qua budget; pair bucket nếu có chỉ bổ sung |
| Cùng account còn budget nhưng IP đã hết | Request bị chặn |
| IP còn budget nhưng account đã hết | Request bị chặn |
| Không tồn tại username | Response/timing không lộ sự tồn tại tài khoản |
| Một nguồn NAT đông user hợp lệ | Ngưỡng/challenge không gây false positive không thể khôi phục |
| Nhiều instance/pod đồng thời | Không vượt quota do race/đếm local |
| Concurrent requests đúng biên quota | Số request được phép không vượt giới hạn |
| Redis timeout/failover | Không mặc định đi qua password verifier không giới hạn |
| Spoofed `X-Forwarded-For` | Không tạo nguồn giả để né limit |
| JWT/OIDC login, OTP, recovery khác route | Có policy riêng, không mở đường bypass |
| User login thành công | Tín hiệu risk được cập nhật; per-source budget không bị xóa sạch |
| Account bị cố tình spam sai | Có recovery/challenge không gây lockout DoS quá mức |
| User có MFA nhưng risk cao | Step-up theo policy, không bỏ authentication |
| Không lộ key/password/token trong logs | Quan sát vẫn đủ chẩn đoán |

### 15.2. Test thuật toán khác test wiring

**Unit test thuật toán:** dùng clock giả (như ví dụ Java) để kiểm cửa sổ, số lượt, atomic denial, boundary và cleanup. Không dùng `Thread.sleep` để làm test nhanh hơn.

**MockMvc security test:** với Spring Boot 3.x, tạo `@SpringBootTest` + `@AutoConfigureMockMvc`, dùng service mock/fake `LoginGate` rồi gọi `POST /login` có `.with(csrf())`. Kiểm request vượt limit trả 429 **trước khi** `AuthenticationManager` xử lý; kiểm request bình thường đi tới filter login. Khi test happy path, cần cấu hình user/password encoder hoặc authentication provider test.

Ví dụ **snippet MockMvc**, không phải test class độc lập:

```java
mvc.perform(post("/login")
        .param("username", "alice@example.test")
        .param("password", "not-real")
        .with(csrf()))
    .andExpect(status().isTooManyRequests());
```

Điều kiện để test trên đúng: test double của `LoginGate.reserve(...)` phải trả `Decision(false, ...)` cho request, và filter được gắn vào chain. Vì vậy không thể copy snippet vào project rồi kết luận limiter hoạt động nếu chưa cấu hình stub và context.

**Integration test phân tán:** chạy nhiều app instances dùng Redis thật/test container, gửi đồng thời requests có cùng account nhưng IP khác, và cùng IP nhưng account khác; số được phép phải không vượt quota, kể cả khi có retry, network latency và clock skew. Tạo test XFF spoof qua proxy, Redis failover, key eviction và OIDC/MFA endpoint ngoài form login.

### 15.3. Đánh giá không chỉ “chặn được bot”

Ngoài số request bị chặn, cần đo **false positives**: người dùng thật bị chặn trong NAT lớn, login success rate, MFA challenge completion, password reset success và support ticket. Một limiter quá gắt có thể làm giảm khả năng truy cập thực tế và bị attacker lợi dụng để khóa user có chủ đích.

## 16. Vận hành và bảo mật dữ liệu

Các metrics hữu ích:

- Số lượt login tổng, số thành công/thất bại/429 theo từng endpoint.
- Phần trăm/thời gian chạm giới hạn theo **loại trục**, không log chi tiết account.
- Tỷ lệ account có lỗi từ nhiều IP, tỷ lệ IP thử nhiều account, số nguồn mới.
- Latency của store/Redis, retry, failover, số bucket active, memory, eviction rate.
- CAPTCHA/MFA step-up rates, completion rates, false-positive complaints.
- Tải CPU password hash, DB/IdP latency và mức tiêu hao email/SMS.

**Bảo vệ quyền riêng tư:** không ghi mật khẩu, token, mã OTP, full username/email vào telemetry không cần thiết. IP address có thể là dữ liệu cá nhân; xác định mục đích, thời hạn lưu, quyền truy cập, anonymization và chính sách pháp lý tương ứng. Tránh dùng PII hoặc high-cardinality keys làm label metrics; tách access logs an toàn khỏi audit bảo mật.

**Kế hoạch incident:** khi credential stuffing bùng phát, có thể thắt quota tại gateway, tăng challenge ở nhóm rủi ro cao, cảnh báo người dùng có dấu hiệu compromise và yêu cầu reset/step-up theo chính sách. Không tắt logging hay bỏ toàn bộ rate limits khi hệ thống quá tải; ưu tiên bảo vệ lõi xác thực theo SLO và cơ chế fallback đã được xem xét.

## 17. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ limit theo IP | Botnet đổi IP, brute force cùng account vẫn chạy | Thêm per-account độc lập |
| Chỉ limit theo account | Spraying một password qua nhiều account | Thêm per-source và global |
| Chỉ dùng khóa `IP:username` | Không chặn sweep IP hoặc đổi IP trên một account | Dùng hai bucket độc lập + pair phụ |
| Tin `X-Forwarded-For` do client gửi | IP spoofing né quota | Trust boundary xóa/ghi header, xác minh proxy |
| Dùng counter local khi có nhiều pod | Quota bị nhân theo số instance | Distributed atomic limiter |
| Đếm outcome sau password verifier mới chặn | CPU/hash đã bị tiêu hao | Pre-auth gate trước verifier |
| Reset mọi bucket khi login thành công | Kẽ hở tăng tốc sau một credential đúng | Chỉ reset failure signals có chủ đích |
| Khóa tài khoản vĩnh viễn sau vài lỗi | Attacker gây DoS người dùng | Progressive challenge và recovery bảo vệ |
| Trả riêng “user không tồn tại” / “account locked” | Username enumeration | Public response generic, timing gần nhau |
| Lưu email/password trong Redis key/log | Rò dữ liệu và tăng rủi ro | HMAC identifier, redact secrets, retention |
| Trả bucket ID chính xác khi 429 | Attacker tối ưu nhịp tấn công | Response chung, telemetry riêng |
| Dùng CAPTCHA thay vì rate limiting | Bypass bởi bot/challenge solving | Defense in depth |
| Dùng `Thread.sleep` cho mọi request lỗi | Chiếm worker threads, tự gây DoS | Async challenge / 429 / backoff không block |
| Tắt toàn bộ limiter khi Redis gặp lỗi | Attacker tận dụng outage | Fail closed hoặc degraded control rõ ràng |
| Giới hạn POST login nhưng bỏ OTP/reset/API login | Đường bypass qua flow khác | Inventory mọi auth endpoint |
| Không test biên thời gian/concurrency | Burst/race vượt quota | Clock giả + integration concurrency |
| Không quản lý lượng key/TTL | Memory exhaustion do username giả | Input bounds, TTL, ingress global caps |

## 18. Bài tập thực hành

1. Viết test cho `DualAxisLimiter`: Alice thử từ 4 IP khác nhau, và IP1 thử 6 username khác nhau. Vì sao hai trục độc lập chặn hai mẫu tấn công khác nhau?
2. Chuyển demo local sang Redis sorted-set hoặc token bucket, bảo đảm kiểm và tiêu thụ hai bucket **nguyên tử** khi nhiều pod cùng xử lý.
3. Cấu hình Nginx/Ingress để gỡ `X-Forwarded-*` do client cung cấp. Test cùng source IP với header `X-Forwarded-For` giả ở mỗi request; budget có bị bypass không?
4. Thiết kế policy cho `POST /otp/send`, `POST /otp/verify` và `POST /password/reset` với giới hạn per-recipient, per-IP, global cost, failed attempts và reuse.
5. Dùng MockMvc để chứng minh request bị gate từ chối **trước** khi password verifier chạy; giữ CSRF token trong test POST form login.
6. Thiết kế risk rule phát hiện một IP thử 500 tài khoản trong một giờ nhưng chỉ một lần mỗi tài khoản. Tại sao per-account-only không đủ?
7. Thiết kế UX cho người dùng bị attacker cố tình spam password sai: challenge, recovery, cooldown, support escalation và tránh username enumeration.
8. Viết dashboard theo dõi 429, false positives, challenge success, Redis latency và tỷ lệ thành công của người dùng NAT lớn.
9. Chạy test một backend bị restart hoặc Redis failover giữa lúc nhiều requests; xác định giới hạn sai lệch quota và degraded mode.

## 19. Tổng kết và tài liệu tham khảo

- **Giới hạn theo tài khoản** chống brute force phân tán trên một user; **theo nguồn** chống một IP thử nhiều accounts; chúng phải độc lập, không được thay bằng khóa cặp.
- **Rủi ro** giúp chọn mức bảo vệ thích nghi, nhưng không thay kiểm password/MFA hoặc chứng minh danh tính.
- **Trước authentication**, throttle giảm khả năng tốn CPU/hash; **sau authentication**, events/handlers cập nhật failure/risk history.
- **Hệ thống nhiều instance** phải có distributed store và thao tác nguyên tử, có TTL, giới hạn memory, metrics và failure policy.
- **Proxy/IP phải có trust boundary**, tránh XFF spoof; không khóa quá tay người dùng NAT.
- **Không lộ account tồn tại**, không log secrets, không để reset/OTP/MFA trở thành đường vòng, và không mở rộng phạm vi chặn hơn cần thiết.
- **Thử nghiệm đủ ba chiều**: account, source, risk; có cả concurrency, recovery, false positives và người dùng thật.

Tài liệu tham khảo:

- [OWASP Authentication Cheat Sheet — Login Throttling](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)
- [OWASP Bot Management and Anti-Automation — Rate Limiting](https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security — Servlet Filter Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [RFC 6585 — HTTP 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585)