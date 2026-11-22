# Rate limiter theo tài khoản hoặc tenant

## 1. Bài toán production: ai được dùng bao nhiêu năng lực gửi mail?

Trong ứng dụng **Spring Framework Mail**, `JavaMailSender.send(...)` có thể được gọi đồng thời từ HTTP requests, scheduler, event consumers hoặc worker đọc outbox. Khi chỉ một người dùng thử gửi vài thư, giới hạn tốc độ dường như không quan trọng. Nhưng với dịch vụ SaaS phục vụ hàng trăm **tenant** hoặc một hệ thống dùng nhiều **tài khoản gửi mail**, một khách hàng có chiến dịch lớn có thể chiếm toàn bộ tài nguyên SMTP và khiến email giao dịch của những khách hàng khác bị chậm.

Giả sử một ứng dụng có:

- Tenant A gửi 20.000 email marketing trong một giờ.
- Tenant B chỉ cần vài chục email hóa đơn.
- Tenant C có email xác thực tài khoản cần xử lý trong vài giây.
- Tất cả cùng dùng một SMTP provider account với một hạn mức tổng.

Nếu worker lấy job theo FIFO và tăng số thread để xử lý backlog, có thể xảy ra:

1. Provider từ chối tạm thời vì vượt giới hạn gửi.
2. Tenant A tiêu hết quota chung trước khi B/C được xử lý.
3. Retry của A tạo thêm tải, gây **retry storm**.
4. Một tài khoản bị khóa hoặc giảm reputation vì spike bất thường.
5. Worker bị chiếm bởi các lệnh chờ quota; mail quan trọng nằm trong queue.
6. Autoscaling thêm pod làm số request SMTP tăng nhanh hơn dự tính.
7. Job bị xử lý trùng khi claim hết hạn giữa lúc provider đã nhận email.

**Rate limiter theo tài khoản hoặc tenant** là một thành phần admission control: nó quyết định một job đã được phép bắt đầu SMTP submission ở thời điểm hiện tại hay phải đợi, dựa trên quota của **provider account**, **tenant**, **sender identity**, và đôi khi cả **loại thông báo**.

~~~text
HTTP / Business events / Batch
              |
              v
       Durable Mail Outbox
              |
              v
         Dispatcher
              |
       Tenant authorization
              |
              v
      Hierarchical rate gate
       /       |         \
      v        v          v
 Global     Account     Tenant
 budget     bucket      bucket
      \        |         /
       +-------+--------+
               |
               v
    SMTP concurrency control
               |
               v
        JavaMailSender
               |
               v
         SMTP provider
~~~

Trong bài này, “rate limiter” được trình bày như một **mẫu thiết kế production**, không chỉ là một helper `sleep(1000)`. Nó phải hoạt động đúng khi có nhiều instance, account, tenant và trạng thái lỗi, đồng thời không làm mất email.

## 2. Phân biệt account, tenant, sender và quota scope

Không nên dùng bốn khái niệm dưới đây thay thế nhau:

| Thực thể | Vai trò | Ví dụ minh họa |
|---|---|---|
| **Tenant** | Khách hàng tổ chức trong SaaS | `tenant-42` |
| **Provider** | Dịch vụ cung cấp SMTP/API gửi thư | `PRIMARY_SMTP` |
| **Provider account** | Account/organization/sending pool của provider | `primary-prod-account` |
| **Credential** | Username/password, OAuth token hoặc API key dùng xác thực | `orders-key-v3` |
| **Sender identity** | Domain hoặc địa chỉ `From` được phép sử dụng | `orders@example.test` |
| **Quota scope** | Phạm vi mà provider hoặc ứng dụng thực sự áp hạn mức | `provider-account:primary-prod` |
| **Notification lane** | Loại lưu lượng có yêu cầu ưu tiên khác nhau | `SECURITY`, `TRANSACTIONAL`, `BULK` |

Ví dụ một account có hai credentials:

~~~text
SMTP Provider A
  |
  +-- Organization/account PROD
         |
         +-- credential "orders"  -> tenant A
         +-- credential "support" -> tenant B
         |
         +-- shared account quota
~~~

Nếu provider đếm quota theo organization, việc tạo hai token bucket hoàn toàn độc lập theo credential có thể làm **vượt hạn mức chung**. Ngược lại, nếu tenant A và tenant B dùng hai account độc lập, một bộ đếm duy nhất cho tất cả sẽ khiến A vô tình làm cạn năng lực gửi của B.

### Một job có thể chịu nhiều giới hạn đồng thời

Giả sử:

~~~text
Provider account limit:  20 recipient/second
Tenant A policy:          6 recipient/second
Tenant B policy:          4 recipient/second
Transactional lane:      reserved capacity when needed
SMTP concurrent sends:    5 operations
Daily account quota:   50,000 recipients/day
~~~

Những con số này **chỉ dùng để giải thích thiết kế**, không phải hạn mức chính thức của bất kỳ provider nào.

Job của tenant A chỉ có thể submit khi:

~~~text
Provider account rate permit
  AND tenant A rate permit
  AND account daily quota available
  AND SMTP concurrency slot available
  AND sender/tenant permission valid
~~~

Quan trọng: quota tenant không thể tạo thêm quota của provider; nó chỉ **phân chia** và bảo vệ năng lực gửi sẵn có.

## 3. Rate, burst, concurrency và quota ngày là các trục riêng

| Giới hạn | Đơn vị thường gặp | Câu hỏi |
|---|---|---|
| Rate | messages/s, recipients/s, requests/min | Bao nhiêu đơn vị trong khoảng thời gian? |
| Burst | tokens hoặc số event tức thời | Có thể gửi nhanh trong thời gian ngắn đến mức nào? |
| Concurrency | in-flight SMTP submissions hoặc connections | Có bao nhiêu thao tác mạng đang chạy? |
| Daily quota | recipients/day, messages/rolling 24h | Tổng gửi trong chu kỳ còn bao nhiêu? |
| Per-message cap | RCPT TO/message, MIME bytes | Một thư lớn nhất có thể chứa bao nhiêu người nhận/dữ liệu? |
| Application tenant budget | units/tenant/window | Tenant được quyền tiêu thụ tối đa bao nhiêu? |

**Giới hạn thread không phải rate limit.** Ví dụ:

~~~java
executor.setMaxPoolSize(8);
~~~

Chỉ khống chế số task cùng thực thi trong executor; nếu SMTP trả kết quả rất nhanh, tám thread vẫn có thể gửi hàng trăm requests mỗi giây. Ngược lại, nếu mỗi call mất vài giây, rate gate có thể còn permit nhưng concurrency đã đầy.

Một token bucket liên tục nạp lại cũng **không thay thế quota ngày**: nó có thể hợp lệ ở từng giây nhưng gửi vượt số recipient được cho phép trong 24 giờ.

### Rate theo message hay theo recipient?

Một lệnh `send(MimeMessage)` có thể có nhiều người nhận trong envelope:

~~~text
MAIL FROM:<orders@example.test>
RCPT TO:<a@example.test>
RCPT TO:<b@example.test>
RCPT TO:<c@example.test>
DATA
...
~~~

Đó có thể là **1 message nhưng 3 recipients**. Khi provider tính quota theo recipient, cost phải là 3; khi tính theo message, cost là 1; khi áp cả hai, cần hai bucket/limiter khác đơn vị. Bcc cũng có thể xuất hiện trong SMTP envelope dù không xuất hiện trong thư hiển thị cho những người nhận khác.

Không tự động hoàn quota đã reserve mỗi khi có `MailException`: provider có thể đã hạch toán hoặc accepted một phần submission, nhất là khi connection mất sau DATA.

## 4. Đặt mục tiêu: bảo vệ provider và đảm bảo công bằng giữa tenant

Hai yêu cầu liên quan nhưng không đồng nhất:

**Provider protection:** tổng số submission qua một account phải nằm trong safe quota của provider.

**Tenant fairness:** tenant gửi batch rất lớn không thể độc chiếm toàn bộ năng lực, làm tenant khác bị đói tài nguyên (*starvation*).

Ví dụ account có safe throughput 12 recipients/giây, 3 tenant:

~~~text
Account bucket = 12 recipients/second
                |
                +-- Tenant A: soft cap 5/s
                +-- Tenant B: soft cap 5/s
                +-- Tenant C: soft cap 5/s
~~~

Tổng soft cap là 15/s, nhưng account chỉ còn 12/s. Điều này **không sai nếu các tenant budgets là hạn mức tối đa và admission account vẫn chặn tổng 12/s**. Nó trở thành sai nếu dispatcher cấp riêng cho mỗi tenant toàn bộ cap rồi bỏ qua account bucket.

Các mục tiêu vận hành:

- Không gửi vượt quota/hạn mức hợp đồng provider.
- Không để một tenant làm nghẽn toàn bộ outbox.
- Email bảo mật/giao dịch được ưu tiên hợp lý.
- Giới hạn số SMTP connections và outbound tasks.
- Không làm mất mail khi chưa có permit.
- Retry không tạo bão request.
- Có thể quan sát các lý do bị chặn theo account và tenant.
- Có thể tăng hoặc giảm replica mà không phá giới hạn chung.

### Fairness không nhất thiết là chia đều

Một số tenant có hợp đồng throughput cao hơn. Có thể dùng *weighted fair scheduling*, ví dụ tenant gói cao được nhiều share hơn tenant gói cơ bản. Tuy nhiên, quota chung và SLA của email quan trọng vẫn là ràng buộc cao nhất. Không dùng một queue FIFO duy nhất rồi tin rằng “ai đến trước phục vụ trước” sẽ luôn công bằng.

## 5. Chọn quota key theo phạm vi được phép

Một thiết kế key:

~~~text
mail:rate:provider-account:primary-prod
mail:rate:tenant:tenant-42
mail:rate:sender:orders-profile
mail:daily:provider-account:primary-prod
mail:concurrency:primary-prod
~~~

Các key đều là **ID nội bộ đã được chuẩn hóa**, không phải raw SMTP password, địa chỉ người nhận hoặc chuỗi tùy ý do API client truyền vào.

Một job cần được map tới một nhóm quota:

~~~text
jobId             = opaque UUID
tenantId          = tenant-42
senderProfileId   = ORDERS
providerId        = PRIMARY
providerAccountId = primary-prod
notificationType  = ORDER_RECEIPT
quotaCost         = 1 recipient
~~~

**Server phải tự xác định `tenantId` từ authentication/authorization context**, không tin một field `tenantId` trong request body rồi cho người dùng tiêu thụ hạn mức của tenant khác.

### Ưu tiên khóa theo scope, không theo phiên bản secret

Nếu rotate credential từ `key-v3` sang `key-v4` nhưng cùng provider account, quota account thường không reset. Dùng credential version làm khóa quota dễ vô tình mở thêm một bucket đầy sau rotation. Quota key cần ổn định theo phạm vi hợp đồng.

### Có cần giới hạn theo recipient domain?

Đôi khi có: provider/receiving domain có thể thực hiện deferral khi lượng mail đến một domain tăng đột biến. Tuy nhiên, bucket theo từng địa chỉ email tạo PII/high cardinality không cần thiết. Nếu có policy theo recipient domain, chỉ dùng domain/nhóm được cấu hình có kiểm soát và hiểu rằng domain cũng có thể tiết lộ traffic patterns.

## 6. Kiến trúc khuyến nghị: durable outbox trước, rate gate ngay trước SMTP

~~~mermaid
flowchart TD
    A[Business transaction] --> B[Write mail intent to outbox]
    B --> C[Commit]
    C --> D[Scheduled dispatcher]
    D --> E[Claim due jobs with lease]
    E --> F[Check tenant and sender eligibility]
    F --> G{Hierarchical quota available?}
    G -- No --> H[Defer via next_attempt_at]
    H --> D
    G -- Yes --> I{SMTP concurrency slot?}
    I -- No --> H
    I -- Yes --> J[Create attempt and submit]
    J --> K{Submission outcome}
    K -- Accepted --> L[SUBMITTED]
    K -- Temporary rejection --> M[RETRY with backoff]
    K -- Permanent rejection --> N[FAILED]
    K -- Unknown --> O[UNKNOWN and reconcile]
    M --> D
~~~

Tại sao lưu mail trong outbox?

- Khi limiter từ chối, job vẫn tồn tại bền vững.
- Khi service restart, scheduler đọc lại job tới hạn.
- Có thể hủy/đổi lịch/đánh dấu hết hạn theo chính sách.
- Một worker không cần giữ hàng nghìn thread ngủ đợi quota.
- Có thể tách chính sách tenant fairness khỏi việc xử lý SMTP.
- Có thể đo backlog theo tenant, account và loại email.

Tuy nhiên **outbox không bảo đảm exactly-once SMTP delivery**. Worker có thể crash sau khi server accepted nhưng trước khi cập nhật `SUBMITTED`; retry vô điều kiện khi lease hết hạn sẽ tạo thư trùng. Cần mô hình `UNKNOWN`/reconciliation và business idempotency.

## 7. Token bucket: giữ tốc độ trung bình và burst trong giới hạn

Token bucket là một thuật toán phù hợp khi provider cho phép một mức **burst ngắn hạn**:

1. Bucket chứa tối đa `capacity` token.
2. Token được nạp lại theo `refillTokensPerSecond`.
3. Một job xin số token bằng cost của submission.
4. Nếu đủ token, trừ token và cấp permit.
5. Nếu chưa đủ, không submit; trả thời gian chờ đề xuất để worker defer.

Ví dụ:

~~~text
capacity = 8 tokens
refill   = 2 tokens/s
cost     = 1 token/message

t=0: 8 tokens available -> có thể burst tới 8 messages
t=0: sau 8 submits -> 0 tokens
t=0.5s: +1 token
t=1.0s: +2 tokens tổng cộng nếu không dùng
~~~

Tốc độ dài hạn trung bình bị giới hạn bởi refill, nhưng burst tối đa phụ thuộc capacity. **Không đặt capacity lớn nếu provider không cho phép burst**, vì ngay cả khi average đúng thì các message gửi dồn vẫn có thể bị throttling.

### Cost lớn hơn capacity

Khi quota tính theo recipient, message có 20 recipients mà bucket capacity chỉ 8:

~~~text
cost = 20
capacity = 8
~~~

Job sẽ **không bao giờ có đủ token** nếu code chỉ chờ. Cần:

- Từ chối hoặc chia message hợp lệ thành nhiều job/nhóm recipients theo policy.
- Hoặc điều chỉnh capacity cho phép cost tối đa mà vẫn tôn trọng burst policy thực tế.
- Phân biệt message rate bucket (cost 1) và recipient rate bucket (cost 20).

### Token bucket có phù hợp quota rolling day?

Không hoàn toàn. Token bucket giới hạn tốc độ trung bình trong thời gian dài, nhưng không tự hạch toán chuẩn xác một hạn mức cố định như 50.000 recipients trong **rolling 24 giờ**. Cần thêm daily/rolling-window budget được thiết kế riêng.

## 8. Java token bucket một JVM: minh họa thuật toán

Đây là ví dụ **dùng trong một JVM**, không đủ để giới hạn toàn bộ cụm khi nhiều Spring Boot replicas chia account quota.

~~~java
import java.time.Duration;
import java.util.function.LongSupplier;

public record RateDecision(
        boolean allowed,
        Duration retryAfter) {
    public static RateDecision granted() {
        return new RateDecision(true, Duration.ZERO);
    }
    public static RateDecision denied(Duration wait) {
        return new RateDecision(false, wait);
    }
}

public final class LocalTokenBucket {
    private final int capacity;
    private final double refillPerSecond;
    private final LongSupplier ticker;
    private double tokens;
    private long updatedAtNanos;

    public LocalTokenBucket(
            int capacity, double refillPerSecond,
            LongSupplier ticker) {
        if (capacity <= 0
                || !Double.isFinite(refillPerSecond)
                || refillPerSecond <= 0) {
            throw new IllegalArgumentException(
                    "Invalid token bucket policy");
        }
        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
        this.ticker = java.util.Objects.requireNonNull(ticker);
        this.tokens = capacity;
        this.updatedAtNanos = ticker.getAsLong();
    }

    public synchronized RateDecision tryAcquire(int cost) {
        if (cost <= 0 || cost > capacity) {
            throw new IllegalArgumentException(
                    "Invalid token cost");
        }

        long now = ticker.getAsLong();
        long elapsedNanos = Math.max(0, now - updatedAtNanos);
        updatedAtNanos = now;

        tokens = Math.min(
                capacity,
                tokens + (elapsedNanos / 1_000_000_000d)
                        * refillPerSecond);

        if (tokens >= cost) {
            tokens -= cost;
            return RateDecision.granted();
        }

        double missing = cost - tokens;
        long waitNanos = (long) Math.ceil(
                missing / refillPerSecond * 1_000_000_000d);
        return RateDecision.denied(
                Duration.ofNanos(waitNanos));
    }
}
~~~

Ví dụ sử dụng:

~~~java
LocalTokenBucket tenantBucket = new LocalTokenBucket(
        10, 3.0, System::nanoTime);

RateDecision rate = tenantBucket.tryAcquire(1);
if (rate.allowed()) {
    // Chỉ một trong nhiều điều kiện được thỏa mãn.
    // Còn phải xét account quota và concurrency.
} else {
    // Lưu next_attempt_at trong database.
    Duration delay = rate.retryAfter();
}
~~~

Đặc điểm:

- `synchronized` tránh hai thread trong **cùng process** trừ trùng token.
- `System.nanoTime()` thích hợp đo khoảng trôi qua, không phụ thuộc chỉnh đồng hồ tường.
- Không block worker: caller nhận `retryAfter` rồi defer job.
- Sau restart bucket đầy lại, có thể tạo burst nếu policy không dự phòng.
- Mỗi replica có trạng thái riêng, không thể bảo đảm account-level aggregate rate.
- Không có daily quota, per-provider cost và multi-bucket atomic admission.

Do đó **không giới thiệu local bucket như một giải pháp production đa replica**. Nó hữu ích để giải thích thuật toán hoặc cho ứng dụng đơn instance với giả định triển khai được kiểm soát.

## 9. Hierarchical limiter: cấp phép tất cả điều kiện hoặc không điều kiện nào

Một job tenant A phải đi qua account bucket và tenant bucket. Nếu viết:

~~~java
if (accountBucket.tryAcquire(1).allowed()
        && tenantBucket.tryAcquire(1).allowed()) {
    sender.send(message);
}
~~~

thì khi account bucket cho phép nhưng tenant bucket từ chối, **account đã mất một token dù chưa gửi**. Trong tải cao, lỗi “cấp phép dở dang” lặp lại làm thất thoát budget nội bộ và gây starvation.

Đây không nhất thiết làm vượt quota provider, nhưng có thể làm hệ thống không dùng được năng lực đã cấp. Nếu logic hoàn token không chuẩn hoặc có race, hệ thống còn có thể vượt quota.

Một thiết kế tốt cho các buckets cùng store:

~~~text
ATOMIC reserve(account, tenant, costs):
  refill account bucket
  refill tenant bucket
  check account has enough
  check tenant has enough
  if either fails:
      grant none
      return denied + next eligible time
  else:
      subtract from both
      return granted
~~~

Với nhiều cấp (account, tenant, sender, lane), mở rộng cùng nguyên tắc. Không nên cập nhật nhiều key rời rạc bằng Redis GET/SET không có atomicity.

### Nếu account quota tính recipient, tenant quota tính message

Cost phải tương ứng:

~~~text
Account recipient bucket: cost = 5
Tenant message bucket:    cost = 1
Sender concurrency:       cost = 1 in-flight slot
~~~

**Một cost scalar không phù hợp mọi quota.** Có thể mô hình:

~~~java
public record MailQuotaCost(
        int messages,
        int recipients,
        long mimeBytes) {
    public MailQuotaCost {
        if (messages <= 0 || recipients <= 0 || mimeBytes < 0) {
            throw new IllegalArgumentException(
                    "Invalid mail quota cost");
        }
    }
}
~~~

Quyết định cost dựa vào **SMTP envelope recipients thực tế** và provider policy, không chỉ số lần gọi API hay số header To.

## 10. Vì sao multi-replica bắt buộc có shared admission control?

Giả sử provider account cho phép 10 messages/second:

~~~text
             Shared provider account 10/s
                         ^
                         |
       +-----------+-----+-----------+
       |           |                 |
    Pod A        Pod B             Pod C
  local 10/s   local 10/s        local 10/s

Potential aggregate = 30/s, not 10/s.
~~~

Các phương án:

| Thiết kế | Phù hợp khi | Đánh đổi |
|---|---|---|
| Single dispatcher theo account | Throughput vừa phải, muốn đơn giản | Cần HA và tránh single point of failure |
| Redis atomic buckets | Nhiều replicas, rate admission nhanh | Shared store, TTL/failover/consistency |
| PostgreSQL quota reservations | Có database và throughput vừa | Contention trên counter rows |
| Provider-native throttling | Provider là lớp bảo vệ cuối cùng | Backlog/retry và SLA dễ khó dự báo |
| Static per-pod partition | Số replica cố định, traffic kiểm soát | Autoscaling, rolling deploy và uneven load |

Không chỉ vì Redis là một bộ nhớ dùng chung mà mọi phép cấp phép sẽ đúng. Một chuỗi `GET`, tính toán trong Java và `SET` vẫn có race giữa các pods; cần operation nguyên tử.

### Rolling deployment

Ngay cả hệ thống thường có 2 replicas vẫn có thể tạm chạy 3–4 replicas trong quá trình deploy. Nếu chia quota tĩnh theo số pods “bình thường”, tổng rate có thể vượt giới hạn khi số instance tăng tạm thời.

### Các ứng dụng khác dùng cùng SMTP account

Nếu một legacy service và một marketing tool cũng gửi bằng account đó, limiter chỉ của Spring app **không biết toàn bộ usage**. Cần account-wide coordination khi có thể, hoặc chừa headroom và đối soát provider dashboard/usage API. Không mặc định rằng tất cả submissions đi qua dispatcher mình kiểm soát.

## 11. Redis distributed limiter: dữ liệu và atomicity

Với Redis, có thể lưu trạng thái mỗi token bucket dưới dạng:

~~~text
key: mail:rate:{primary-prod}:account
  tokens = 7.0
  updated_at = 1794480000.123

key: mail:rate:{primary-prod}:tenant:tenant-42
  tokens = 2.0
  updated_at = 1794480000.123
~~~

`{primary-prod}` là **hash tag** của Redis Cluster, giúp những key cùng tag được đặt trong một hash slot; điều này cần thiết nếu dùng một Lua script thao tác nhiều keys trong Redis Cluster. Đây là ID account logic, không phải username/password thật.

Một atomic reservation cần:

1. Lấy thời gian theo quy tắc chung (ví dụ Redis server time).
2. Load state từng bucket.
3. Refill dựa trên elapsed time.
4. Kiểm tra đủ token của **tất cả** bucket.
5. Nếu có bucket thiếu, **không trừ bucket nào**.
6. Nếu đều đủ, trừ và lưu state cho tất cả.
7. Trả `granted` hoặc khoảng delay đề xuất.

### TTL không được ngắn hơn thời gian refill đầy

Giả sử bucket có capacity 100, refill 1/s. Sau khi tiêu sạch, phải mất 100 giây để refill đầy. Nếu Redis key bị expire sau 10 giây và khởi tạo lại với 100 token, application sẽ cho phép burst quá sớm. Đặt TTL theo **thời gian refill đầy lớn nhất + biên độ phù hợp** (hoặc không dùng expiration theo kiểu làm quên trạng thái nguy hiểm).

### Không được fail open vô hạn khi Redis mất kết nối

Nếu limiter không cấp phép vì timeout/Redis outage, không tự coi đó là permit. Đặc biệt khi nhiều replicas, local fallback 5/s trên 100 pods vẫn có thể thành 500/s toàn cụm. Chọn fail closed hoặc một emergency mode có ngân sách **toàn cụm** và được phê duyệt trước.

## 12. Ví dụ Lua: reserve nguyên tử hai bucket account và tenant

Sau đây là một **mẫu triển khai minh họa** cho Redis (token bucket theo account và tenant). Nó giả định hai key cùng hash slot, policy có hai cấp và cost được xác định trước. Production cần quản lý policy version, TTL, Redis failover và các chiều quota khác.

Input:

~~~text
KEYS[1] = account bucket key
KEYS[2] = tenant bucket key

ARGV[1] = account capacity
ARGV[2] = account refill tokens/s
ARGV[3] = account cost
ARGV[4] = tenant capacity
ARGV[5] = tenant refill tokens/s
ARGV[6] = tenant cost
ARGV[7] = TTL milliseconds (đủ dài cho refill hoàn toàn)
~~~

~~~lua
-- Atomic reservation for two token buckets.
-- Return [1, 0] if granted.
-- Return [0, waitMillis] if denied.
-- Return [-1, 0] for invalid cost/capacity/rate.

local capA    = tonumber(ARGV[1])
local rateA   = tonumber(ARGV[2])
local costA   = tonumber(ARGV[3])
local capT    = tonumber(ARGV[4])
local rateT   = tonumber(ARGV[5])
local costT   = tonumber(ARGV[6])
local ttlMs   = tonumber(ARGV[7])

if not capA or not rateA or not costA
   or not capT or not rateT or not costT or not ttlMs
   or capA <= 0 or capT <= 0
   or rateA <= 0 or rateT <= 0
   or costA <= 0 or costT <= 0
   or costA > capA or costT > capT
   or ttlMs <= 0 then
    return {-1, 0}
end

local redisTime = redis.call("TIME")
local now = tonumber(redisTime[1])
          + tonumber(redisTime[2]) / 1000000

local function currentState(key, capacity, refill)
    local fields = redis.call("HMGET",
            key, "tokens", "updated_at")
    local tokens = tonumber(fields[1])
    local previous = tonumber(fields[2])

    if not tokens or not previous then
        return capacity
    end

    local elapsed = math.max(0, now - previous)
    return math.min(capacity, tokens + elapsed * refill)
end

local tokensA = currentState(KEYS[1], capA, rateA)
local tokensT = currentState(KEYS[2], capT, rateT)

local accountWait = math.max(0, costA - tokensA) / rateA
local tenantWait  = math.max(0, costT - tokensT) / rateT

if accountWait > 0 or tenantWait > 0 then
    -- Read-only deny: no bucket is consumed.
    -- The next request can recalculate refill from saved state.
    return {0, math.ceil(
            math.max(accountWait, tenantWait) * 1000)}
end

redis.call("HSET", KEYS[1],
        "tokens", tokensA - costA,
        "updated_at", now)
redis.call("PEXPIRE", KEYS[1], ttlMs)

redis.call("HSET", KEYS[2],
        "tokens", tokensT - costT,
        "updated_at", now)
redis.call("PEXPIRE", KEYS[2], ttlMs)

return {1, 0}
~~~

### Giải thích các điểm quan trọng

- Một Lua script chạy như một thao tác **nguyên tử** trên Redis cho các keys hợp lệ trong cùng execution context; hai worker không thể cùng đọc một token rồi cả hai trừ token đó.
- Nếu tenant thiếu token, account **không bị trừ dở dang**.
- Nếu một bucket thiếu, trả khoảng chờ lớn nhất giữa hai bucket, vì phải chờ **cả hai** đủ.
- Delay trả về là ước lượng tại thời điểm thực thi; trước khi SMTP submit phải **lấy permit lại**, không coi delay hết là đã được cấp.
- Trường hợp `cost > capacity` trả lỗi cấu hình/tham số, không đợi vô hạn.
- Khi deny, state cũ được giữ; lần request sau có thể tính lại refill dựa trên `updated_at` đã lưu.
- TTL phải lớn hơn thời gian để token của bucket được refill đầy khi không có request và có biên độ an toàn; không để key tự biến mất khi budget vẫn cần bảo vệ.

### Phạm vi của script minh họa

Script **chưa giải quyết** quota ngày, policy reload atomically, dynamic capacity giảm mạnh, per-recipient-domain bucket, global tenant quota xuyên nhiều account, global concurrency slot hoặc các vấn đề durability của Redis failover.

Nếu một tenant sử dụng **nhiều provider accounts** nhưng phải chịu một quota toàn tenant, key toàn tenant và các account keys có thể thuộc **nhiều Redis Cluster hash slots**. Không giả định một script có thể atomic update tùy ý các hash slots. Lựa chọn gồm:

1. Sắp key placement về cùng slot (nếu mô hình scale cho phép).
2. Dùng một coordination service/transactional database cùng ranh giới nguyên tử.
3. Chia quota thành reservations/allocations có giới hạn rõ ràng.
4. Chấp nhận conservative accounting kèm reconciliation được thiết kế trước.

Không gọi nhiều script độc lập rồi giả định đó là một distributed transaction.

## 13. Gọi RedisScript từ Spring Data Redis

Ví dụ Spring Data Redis minh họa cách adapter gọi script và ánh xạ kết quả về đối tượng ứng dụng.

~~~java
import java.time.Duration;

public record QuotaPermit(
        boolean granted,
        Duration retryAfter) {

    public static QuotaPermit allow() {
        return new QuotaPermit(true, Duration.ZERO);
    }

    public static QuotaPermit defer(Duration delay) {
        return new QuotaPermit(false, delay);
    }
}

public interface AccountTenantRateGate {
    QuotaPermit reserve(
            String providerAccountId,
            String tenantId,
            int accountCost,
            int tenantCost);
}
~~~

Lớp Redis adapter ở mức khái niệm:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

public final class RedisAccountTenantRateGate
        implements AccountTenantRateGate {

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<List> script;
    private final MailQuotaPolicyRegistry policies;

    public RedisAccountTenantRateGate(
            StringRedisTemplate redis,
            DefaultRedisScript<List> script,
            MailQuotaPolicyRegistry policies) {
        this.redis = redis;
        this.script = script;
        this.policies = policies;
    }

    @Override
    public QuotaPermit reserve(
            String accountId, String tenantId,
            int accountCost, int tenantCost) {

        var p = policies.forAccountAndTenant(
                accountId, tenantId);

        // Same Redis Cluster hash tag for these two keys.
        String tag = "{" + p.accountScopeId() + "}";
        String accountKey = "mail:rate:" + tag + ":account";
        String tenantKey = "mail:rate:" + tag
                + ":tenant:" + p.tenantScopeId();

        List<?> result = redis.execute(
                script,
                List.of(accountKey, tenantKey),
                Integer.toString(p.accountBurstCapacity()),
                Double.toString(p.accountRefillPerSecond()),
                Integer.toString(accountCost),
                Integer.toString(p.tenantBurstCapacity()),
                Double.toString(p.tenantRefillPerSecond()),
                Integer.toString(tenantCost),
                Long.toString(p.ttl().toMillis()));

        if (result == null || result.size() != 2) {
            throw new IllegalStateException(
                    "Rate gate returned an invalid response");
        }

        long code = ((Number) result.get(0)).longValue();
        long waitMs = ((Number) result.get(1)).longValue();
        if (code == 1) {
            return QuotaPermit.allow();
        }
        if (code == 0 && waitMs >= 0) {
            return QuotaPermit.defer(
                    Duration.ofMillis(waitMs));
        }

        throw new IllegalStateException(
                "Invalid rate gate policy or script error");
    }
}
~~~

`MailQuotaPolicyRegistry` và policy fields là abstraction **do ứng dụng xây dựng**. Để dùng lớp này cần tạo `DefaultRedisScript<List>` với Lua content ở trên, `setResultType(List.class)`, và chọn Redis serializer phù hợp. Cần kiểm tra result serialization phù hợp version Spring Data Redis/Jedis/Lettuce đang dùng; không nên copy fragment chưa có bean registration rồi coi là ứng dụng đầy đủ.

### Không tin accountId/tenantId tùy ý từ bên ngoài

`policies.forAccountAndTenant(...)` phải xác nhận mapping tenant → account và trả **những ID đã được chuẩn hóa**, không nối request input trực tiếp vào key Redis vì key space injection/high cardinality. Redis key chỉ chứa ID logic được cấp từ identity/policy store.

### Trả lỗi rate gate khác với trả DENIED

Nếu Redis timeout, script lỗi hoặc result không hợp lệ, không được trả `QuotaPermit.defer(Duration.ZERO)` hay `allow()`. Đó là **sự cố của hệ thống cấp quota**, cần fail closed (hoặc fallback đã được phê duyệt), giữ job và phát alert. `DENIED` là kết quả bình thường khi quota hết, khác với `ERROR`.

## 14. Daily quota: bộ đếm chu kỳ riêng

Nếu provider áp cả:

~~~text
10 messages/second
20,000 recipients/rolling 24h
~~~

thì có **ít nhất hai cơ chế**:

1. Token bucket hoặc sliding window cho messages/second.
2. Budget accounting theo chính xác rolling 24h cho recipients.

Một bộ đếm cố định calendar day không thay thế rolling window:

~~~text
23:59 -> gửi gần hết quota
00:01 -> bộ đếm app reset về 0
~~~

Nếu provider tính rolling 24h, lượng gửi ở 23:59 vẫn nằm trong cửa sổ và sẽ khiến gửi tiếp lúc 00:01 vượt quota.

Với provider áp **calendar window**, có thể dùng một bảng DB:

~~~sql
CREATE TABLE mail_quota_window (
    quota_scope_key VARCHAR(140) NOT NULL,
    quota_unit VARCHAR(32) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    capacity BIGINT NOT NULL CHECK (capacity > 0),
    reserved BIGINT NOT NULL DEFAULT 0
        CHECK (reserved >= 0),
    PRIMARY KEY (
        quota_scope_key, quota_unit, window_start
    ),
    CHECK (window_end > window_start)
);
~~~

Reserve theo DB transaction:

~~~sql
UPDATE mail_quota_window
SET reserved = reserved + :cost
WHERE quota_scope_key = :scope
  AND quota_unit = :unit
  AND window_start = :window_start
  AND reserved + :cost <= capacity
RETURNING reserved;
~~~

Với PostgreSQL, update trên cùng row được đồng bộ qua row lock. Khi không có row được trả về, **không mặc định là quota đủ**: row có thể không tồn tại, dùng sai window hoặc đã cạn quota.

### Nếu có cả account và tenant daily budgets

Cần reserve cả hai trong **một transaction**, hoặc dùng một cơ chế coordinated reservation:

~~~text
BEGIN
  Lock account window row
  Lock tenant window row (theo thứ tự cố định)
  Validate both capacities
  Increment both counters
COMMIT
~~~

Nếu một counter không đủ, transaction **rollback toàn bộ**, tránh trừ dở dang. Lock rows theo thứ tự nhất quán để giảm deadlock. Nếu provider dùng rolling 24h, thiết kế bảng calendar trên không áp dụng trực tiếp; cần event/window accounting hoặc nguồn quota provider hỗ trợ.

### Tại sao không giữ transaction qua SMTP?

Một network call có thể treo lâu. Không giữ quota row lock và DB transaction trong suốt `JavaMailSender.send(...)`. Reserve/commit nhanh, rồi submit SMTP ngoài transaction. Nếu worker chết sau reserve nhưng trước submit, có thể mất capacity ảo; điều đó an toàn về quota hơn hoàn permit mù khi provider có thể đã accepted. Reconciliation phải dựa trên evidence và reservation semantics.

## 15. Concurrency limiter: tách slot khỏi rate token

Ngay cả khi throughput trung bình hợp lệ, việc mở quá nhiều SMTP connections cùng lúc có thể làm provider từ chối hoặc treo worker.

~~~java
import java.util.concurrent.Semaphore;

public final class LocalSmtpConcurrencyGate {
    private final Semaphore slots;

    public LocalSmtpConcurrencyGate(int maximum) {
        if (maximum <= 0) {
            throw new IllegalArgumentException(
                    "maximum must be positive");
        }
        this.slots = new Semaphore(maximum);
    }

    public boolean tryAcquire() {
        return slots.tryAcquire();
    }

    public void release() {
        slots.release();
    }
}
~~~

Sử dụng:

~~~java
if (!slots.tryAcquire()) {
    deferJobForCapacity(jobId);
    return;
}

try {
    // Reserve rate permit ngay trước submission.
    // Sau đó gọi JavaMailSender.send(...).
    sender.send(message);
} finally {
    slots.release();
}
~~~

**Chỉ release khi đã acquire slot thành công.** Local semaphore giới hạn thao tác trong một JVM; nếu có 4 replicas, mỗi pod 5 slots, toàn cụm có thể có tới 20 SMTP operations đồng thời.

Đối với hard concurrency cap theo provider account, cần global slot allocator/distributed semaphore hoặc một worker pool tập trung. Khi dùng **lease cho distributed slot**, phải xét worker pause, mất network và lease expiry: slot có thể hết hạn trong khi SMTP call cũ vẫn chạy, gây vượt hard limit. Cần timeout, renewal/fencing và một chính sách ứng xử thận trọng; không mặc định distributed semaphore dựa TTL là bảo đảm tuyệt đối trước mọi failure.

### Xin slot trước hay token trước?

- Nếu lấy token trước rồi không có SMTP slot, token có thể bị lãng phí.
- Nếu giữ slot rồi chờ token hàng phút, concurrency capacity bị khóa không cần thiết.
- Có thể kiểm tra khả năng slot nhanh, xin quota permit nguyên tử **gần thời điểm submission**, và nếu permit deny thì release slot ngay.
- Nếu xử lý nhiều chiều phân tán, cần tài liệu hóa thứ tự reservation và cách bù trừ các trường hợp chắc chắn chưa submit.

Không giữ database transaction trong khi chờ slot hoặc chờ quota.

## 16. Fair scheduling: quota tenant chưa đủ để tránh starvation

Một queue FIFO chứa:

~~~text
A1, A2, A3, ..., A100000, B1, C1
~~~

Kể cả tenant A bị giới hạn 5/s, worker có thể liên tục claim hàng trăm A-jobs, bị limiter từ chối rồi defer, khiến B/C khó được chọn kịp lúc.

Vì vậy **rate limiter** nên kết hợp một **fair scheduler**:

~~~text
Ready queues by tenant/lane
        |
        v
Weighted round robin / Deficit round robin
        |
        v
Hierarchical rate admission
        |
        v
SMTP worker pool
~~~

Một số cách:

| Chính sách | Ưu điểm | Hạn chế |
|---|---|---|
| Round robin giữa tenant | Đơn giản, tránh một tenant chiếm hết lượt chọn | Không phản ánh cost đa recipient |
| Weighted fair queueing | Ưu tiên gói dịch vụ theo trọng số | Phải cấu hình/điều chỉnh weights |
| Deficit round robin | Phù hợp job cost khác nhau, fairness theo đơn vị | Phải quản lý deficit/quantum |
| Priority lanes | Email security/transactional được ưu tiên | Strict priority có thể làm bulk starvation |
| Reserved slots/rate | Bảo vệ năng lực cho email quan trọng | Có thể lãng phí nếu lane ít tải |

### Tại sao fairness phải tính cost?

Nếu tenant A gửi một message có 20 recipients còn tenant B gửi một message 1 recipient, round robin theo **message count** vẫn cho A tiêu thụ 20 lần recipient quota. Khi provider tính theo recipient, thuật toán fair-share cần xét cost tương ứng.

### Tránh starvation ngược

Không nên cho security lane chiếm 100% năng lực vô thời hạn nếu SLA/policy không yêu cầu. Có thể dùng reserved capacity, weighted scheduling và aging của các job chờ lâu. Một email marketing có consent và deadline cũng cần được xử lý trong khả năng provider cho phép.

## 17. Cấu hình policy account/tenant trong Spring Boot

Một namespace do ứng dụng tự định nghĩa:

~~~yaml
app:
  mail:
    rate-limits:
      accounts:
        primary-prod:
          unit: recipients
          refill-tokens-per-second: 10.0
          burst-capacity: 20
          max-concurrent-submissions: 5
          safe-daily-recipient-budget: 20000
      tenant-defaults:
        unit: recipients
        refill-tokens-per-second: 2.0
        burst-capacity: 5
      tenant-overrides:
        tenant-gold:
          refill-tokens-per-second: 5.0
          burst-capacity: 10
      fallback:
        on-limiter-unavailable: fail-closed
~~~

**Các con số là ví dụ, không phải quota của provider thật.** `app.mail.rate-limits.*` không phải cấu hình Spring Mail tự động thi hành; ứng dụng cần đọc, validate và chuyển thành rate gates và scheduler policy.

### Bind và validate policy

Ví dụ với Spring Boot configuration properties:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties
        .ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.rate-limits")
public record MailRateLimitsProperties(
        Map<String, AccountLimit> accounts,
        TenantLimit tenantDefaults,
        Map<String, TenantLimit> tenantOverrides) {

    public record AccountLimit(
            String unit,
            double refillTokensPerSecond,
            int burstCapacity,
            int maxConcurrentSubmissions,
            long safeDailyRecipientBudget) {
    }

    public record TenantLimit(
            String unit,
            double refillTokensPerSecond,
            int burstCapacity) {
    }
}
~~~

Đăng ký:

~~~java
import org.springframework.boot.context.properties
        .EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(
        MailRateLimitsProperties.class)
public class MailRateLimitConfiguration {
}
~~~

Ở production cần thêm **validation**: các giá trị phải dương (trừ trường hợp disabled được mô hình rõ), `Double.isFinite`, burst capacity đủ cho cost hợp lệ, tenant mapping hợp lệ, quota units khớp provider và TTL lớn hơn thời gian refill hoàn toàn. Không cho cấu hình thiếu account policy rồi silently dùng unlimited.

### Điều chỉnh policy khi đang chạy

Một thay đổi từ 10/s xuống 3/s trên nhiều replicas cần có **policy version** chung. Nếu một số pods dùng config cũ, số khác dùng mới, aggregate behavior có thể sai. Redis bucket đang có token theo capacity cũ cũng cần được xử lý khi giảm cap; script minh họa đã clamp token theo capacity, nhưng không giải quyết toàn bộ vấn đề khi nhiều pods dùng policy version khác nhau.

Chỉ cho người/role có quyền thay quota, ghi audit thay đổi và rollout theo thứ tự rõ ràng; không cho tenant gửi HTTP request tùy ý đặt `limit=1000000`.

## 18. Cấp quyền tenant và chọn provider account

Rate limiter không phải cơ chế authorization. Trước khi cấp permit, hệ thống phải biết job thực sự thuộc tenant nào và tenant đó **được phép** sử dụng sender/provider account nào.

~~~text
Authenticated caller
        |
        v
Resolve trusted tenant from security context
        |
        v
Validate notification type + sender profile
        |
        v
Select approved provider account
        |
        v
Lookup quota policy for account and tenant
        |
        v
Rate gate
~~~

API gửi mail không nên nhận trực tiếp:

~~~json
{
  "tenantId": "tenant-of-another-customer",
  "providerAccountId": "admin-smtp-account",
  "smtpPassword": "any-value",
  "rateLimit": 999999
}
~~~

Rồi tin các giá trị này để quyết định quota. Người dùng có thể “mượn” budget của khách khác hoặc biến backend thành email relay.

Thay vào đó, API nghiệp vụ:

~~~java
public record SendInvoiceCommand(
        String invoiceId,
        String locale) {
}
~~~

Application service xác minh invoice thuộc tenant đang đăng nhập, lấy recipient từ nguồn tin cậy, chọn sender profile đã phê duyệt, sau đó tạo mail job. `tenantId` và `providerAccountId` do server xác định và lưu bền vững cho mục đích audit/quota.

### Tenant quotas có thể thay đổi theo hợp đồng

Một tenant nâng gói dịch vụ có thể tăng từ 2 recipients/s lên 5 recipients/s. Những job đang chờ cần được áp policy hiện hành theo quyết định sản phẩm; không nhất thiết chụp một bản quota cũ vào từng job. Tuy nhiên, việc tăng budget không đồng nghĩa tăng quota account của provider.

## 19. Outbox schema có tenant, account, trạng thái và thời điểm gửi

Một bảng minh họa bằng PostgreSQL:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    provider_account_id VARCHAR(100) NOT NULL,
    sender_profile_id VARCHAR(80) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    lane VARCHAR(24) NOT NULL,

    recipient_ref VARCHAR(160) NOT NULL,
    payload_ref VARCHAR(255) NOT NULL,
    recipient_count INT NOT NULL
        CHECK (recipient_count > 0),
    business_event_key VARCHAR(180) NOT NULL,

    status VARCHAR(24) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    attempt_count INT NOT NULL DEFAULT 0,
    last_error_code VARCHAR(80),

    claim_token UUID,
    lease_until TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT chk_outbox_status CHECK (
        status IN (
            'PENDING', 'CLAIMED', 'PROCESSING',
            'RETRY', 'SUBMITTED',
            'FAILED', 'CANCELLED', 'EXPIRED', 'UNKNOWN'
        )
    ),
    CONSTRAINT uq_outbox_business_event UNIQUE (
        tenant_id, business_event_key
    )
);

CREATE INDEX idx_mail_outbox_ready
    ON mail_outbox (
        provider_account_id,
        available_at,
        id
    )
    WHERE status IN ('PENDING', 'RETRY');
~~~

`business_event_key` giúp tạo mail intent idempotently cho cùng nghiệp vụ. Nó không bảo đảm SMTP exactly-once khi retry. `recipient_ref`/`payload_ref` nên chỉ tới kho có access control, encryption và retention phù hợp; không snapshot SMTP credential trong job.

### Lưu lane để phục vụ fairness

`lane` có thể là `SECURITY`, `TRANSACTIONAL` hoặc `BULK`. Đó là một classification đã được duyệt trong ứng dụng, không phải tham số tenant tùy ý chọn nhằm lấy thêm quota ưu tiên.

### Không trộn số lần bị deny với SMTP attempt

Nếu rate gate trả DENIED, worker **chưa gọi SMTP**. Đặt lại `available_at` nhưng không tăng `attempt_count`. Có thể đo `rate_limit_deferral_total` riêng.

## 20. Tạo mail intent trong cùng transaction nghiệp vụ

Một use case tạo hóa đơn và enqueue email:

~~~text
BEGIN TRANSACTION
  INSERT/UPDATE invoice data
  INSERT mail_outbox (
    tenant_id,
    provider_account_id,
    status=PENDING,
    scheduled_at,
    available_at,
    ...
  )
COMMIT

Sau commit, dispatcher mới được phép submit qua SMTP.
~~~

Nếu business data commit nhưng enqueue thất bại, yêu cầu gửi bị mất; nếu email được gửi trước khi business transaction commit, người nhận có thể nhận thông tin của một giao dịch đã rollback.

Spring:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {
    private final InvoiceRepository invoices;
    private final MailOutboxRepository outbox;
    private final TenantMailPolicy tenantPolicy;

    public InvoiceService(
            InvoiceRepository invoices,
            MailOutboxRepository outbox,
            TenantMailPolicy tenantPolicy) {
        this.invoices = invoices;
        this.outbox = outbox;
        this.tenantPolicy = tenantPolicy;
    }

    @Transactional
    public void issueInvoice(IssueInvoiceCommand command) {
        Invoice invoice = invoices.issue(command);
        TenantMailRoute route = tenantPolicy
                .approvedRoute(invoice.tenantId(), "INVOICE");

        outbox.insertIfAbsent(
                MailIntent.forInvoice(invoice, route));
    }
}
~~~

Các interfaces/types `InvoiceRepository`, `MailOutboxRepository`, `TenantMailPolicy` và `MailIntent` là các abstraction ứng dụng minh họa. `insertIfAbsent` cần unique constraint hoặc UPSERT atomic theo khóa nghiệp vụ; một check-then-insert rời rạc có thể race khi hai requests cùng tới.

**Không đặt `JavaMailSender.send(...)` trong transaction tạo hóa đơn.** SMTP không rollback cùng database.

## 21. Claim batch nhỏ bằng SKIP LOCKED

Khi có nhiều worker, một query `SELECT ... WHERE status='PENDING'` rồi gửi ngay có thể khiến hai instances xử lý cùng một mail job.

Trong PostgreSQL:

~~~sql
WITH ready AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND provider_account_id = :account_id
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND available_at <= CURRENT_TIMESTAMP
      AND (expires_at IS NULL
           OR expires_at > CURRENT_TIMESTAMP)
    ORDER BY available_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS job
SET status = 'CLAIMED',
    claim_token = :claim_token,
    lease_until = CURRENT_TIMESTAMP
        + INTERVAL '120 seconds',
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
FROM ready
WHERE job.id = ready.id
RETURNING job.id, job.tenant_id,
    job.provider_account_id, job.recipient_count,
    job.claim_token;
~~~

Đây là một **transaction ngắn**: claim và commit, không gửi SMTP trong transaction đó. `SKIP LOCKED` tránh chờ rows đang bị transaction khác khóa, nhưng **không bảo đảm strict FIFO** và không tạo fairness giữa tenant; query `ORDER BY available_at` có thể vẫn chọn rất nhiều job tenant A trước B.

### Tại sao không claim 100.000 job?

Nếu account chỉ gửi được 5 recipients/s, hàng trăm job đã claim có thể nằm lâu trong RAM/executor. Lease có thể hết hạn trước khi tới lượt; worker khác claim lại gây duplicate work và giảm khả năng hủy/đổi lịch.

Chọn batch size theo throughput thật, giới hạn executor queue và số claims đang hoạt động. Fair selector có thể chọn một số job từ mỗi tenant/lane trước khi claim. Nếu triển khai fair scheduling qua nhiều workers, scheduler fairness state cũng cần khả năng khôi phục; không chỉ giữ vòng round-robin trong bộ nhớ một pod.

## 22. Khi limiter trả DENIED: defer job không gọi SMTP

Ví dụ job:

~~~text
id               = job-123
tenant_id        = tenant-42
status           = CLAIMED
scheduled_at     = 09:00
available_at     = 09:00
attempt_count    = 0
~~~

Account còn permit nhưng tenant bucket chưa đủ. Rate gate **không trừ bất kỳ bucket nào** và trả delay 3 giây:

~~~text
new status       = PENDING
new available_at = 09:00:03
attempt_count    = 0
defer reason     = TENANT_RATE_LIMIT
~~~

SQL cập nhật có điều kiện:

~~~sql
UPDATE mail_outbox
SET status = 'PENDING',
    available_at = :next_available_at,
    claim_token = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :job_id
  AND status = 'CLAIMED'
  AND claim_token = :claim_token
RETURNING id;
~~~

Nếu update 0 row, worker đã mất claim hoặc trạng thái thay đổi. Không update không điều kiện rồi vô tình hồi sinh job đã hủy.

### available_at phải tính nhiều điều kiện

Nếu:

~~~text
account bucket next permit: 09:01
tenant bucket next permit:  09:00:03
daily quota recheck:       10:00
business quiet hours:      10:30
~~~

thì có thể cần defer tới mốc **không sớm hơn tất cả ràng buộc**, nếu các mốc được biết. Với provider có quota chưa rõ hoặc dữ liệu usage chậm, dùng khoảng kiểm tra lại bảo thủ, không khẳng định chắc chắn đã có permit tại thời điểm đó.

**Không gọi permit lần hai chỉ vì delay hết**; rate gate có thể đã cấp token đó cho job khác. Mỗi lần chuẩn bị thực sự submit phải lấy admission mới.

## 23. Mẫu interface để tách limiter khỏi Spring Mail

Thay vì viết quota logic bên trong mỗi controller/handler, một dispatcher nên dùng interface chung:

~~~java
import java.time.Duration;
import java.util.UUID;

public record MailDispatchContext(
        UUID jobId,
        String tenantId,
        String providerAccountId,
        String senderProfileId,
        String notificationType,
        int messageCost,
        int recipientCost) {
}

public interface MailAdmissionPolicy {
    QuotaPermit reserve(MailDispatchContext context);
}

public interface SmtpSubmission {
    void submit(ClaimedMailJob job);
}
~~~

`MailAdmissionPolicy` có thể kết hợp:

1. Provider account rate.
2. Tenant rate.
3. Daily quota.
4. Sender/account concurrency.
5. Lane reservation và explicit business restrictions.

**Lưu ý:** các quota dùng chung phải được reserve phối hợp/atomic theo thiết kế; việc interface chỉ có một method không tự làm các backend Redis/DB/slots trở thành một distributed transaction.

`SmtpSubmission` ẩn chi tiết `JavaMailSender`, giúp unit test dispatcher bằng fake sender. Mỗi attempt cần có `providerAccountId` từ cấu hình đã được phê duyệt; không lấy arbitrary host/password từ input của tenant.

### RateDecision, QuotaPermit và lỗi hệ thống

Nên phân biệt ba kết quả:

~~~text
GRANTED
  -> đã reserve capacity, có thể bắt đầu submission

DENIED
  -> provider/tenant budget chưa đủ; có retryAfter

ERROR
  -> limiter DB/Redis unavailable hoặc policy invalid
~~~

Không dùng một boolean `allowed=false` để che cả lỗi cấu hình/Redis outage rồi âm thầm retry mỗi mili-giây. Một lỗi hạ tầng quota cần alert và trạng thái `WAITING_LIMITER` hoặc cơ chế defer riêng, không làm nhầm với tenant đã tiêu hết budget.

## 24. Spring @Scheduled chỉ đánh thức dispatcher

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class MailDispatcherSchedulingConfig {
}
~~~

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class MailOutboxPoller {
    private final AccountAwareMailDispatcher dispatcher;

    public MailOutboxPoller(
            AccountAwareMailDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(
            fixedDelayString =
                    "${app.mail.dispatch.poll-delay-ms:1000}")
    public void dispatchReadyMail() {
        dispatcher.processReadyBatch();
    }
}
~~~

`AccountAwareMailDispatcher` là service ứng dụng, không có sẵn trong Spring Mail. Chỉ dùng `@Scheduled` mà không có outbox không lưu được trạng thái chờ quota sau restart.

### Không dùng Thread.sleep khi hết permit

~~~java
// Không nên:
while (!rateLimiter.tryAcquire(1)) {
    Thread.sleep(1000);
}
~~~

Với hàng nghìn jobs, mô hình này giữ nhiều worker/executor slots chỉ để chờ; có thể làm đầy queue và tăng thời gian shutdown. Một lần DENIED nên kết thúc xử lý job, cập nhật `available_at` rồi giải phóng claim/slot.

### Một pod hay nhiều pods?

Trong Kubernetes, mỗi pod có `@Scheduled` của riêng mình. Không giả định chỉ một instance chạy scheduler. Dùng atomic claim/lease hoặc một leader per account mailbox/queue phù hợp. `@Scheduled` không tự tạo cluster-wide leader.

## 25. Ví dụ dispatcher tích hợp quota gate và SMTP adapter

Khung sau mô tả **vị trí** cấp permit và cập nhật trạng thái; các repositories, classifier và worker lease là abstractions ứng dụng:

~~~java
import java.time.Clock;
import org.springframework.stereotype.Service;

@Service
public final class AccountAwareMailDispatcher {
    private final MailOutboxRepository jobs;
    private final MailAdmissionPolicy admission;
    private final SmtpSubmission submission;
    private final MailSubmissionErrorPolicy errors;
    private final Clock clock;

    public AccountAwareMailDispatcher(
            MailOutboxRepository jobs,
            MailAdmissionPolicy admission,
            SmtpSubmission submission,
            MailSubmissionErrorPolicy errors,
            Clock clock) {
        this.jobs = jobs;
        this.admission = admission;
        this.submission = submission;
        this.errors = errors;
        this.clock = clock;
    }

    public void processReadyBatch() {
        for (ClaimedMailJob job :
                jobs.claimReadyBatch(clock.instant(), 20)) {
            dispatchOne(job);
        }
    }

    private void dispatchOne(ClaimedMailJob job) {
        if (!jobs.isStillEligible(job)) {
            jobs.releaseOrExpire(job);
            return;
        }

        final QuotaPermit permit;
        try {
            permit = admission.reserve(job.dispatchContext());
        } catch (RuntimeException limiterFailure) {
            jobs.deferForLimiterOutage(
                    job, clock.instant().plusSeconds(30));
            reportRateGateFailure(job, limiterFailure);
            return;
        }

        if (!permit.granted()) {
            jobs.deferWithoutAttempt(
                    job,
                    clock.instant().plus(permit.retryAfter()));
            return;
        }

        if (!jobs.beginSubmission(job)) {
            // Claim bị thay đổi hoặc job đã bị hủy.
            // Permit có thể bị tiêu tốn bảo thủ;
            // không gửi khi chưa sở hữu job.
            return;
        }

        try {
            submission.submit(job);
            boolean persisted = jobs.markSubmitted(
                    job, clock.instant());
            if (!persisted) {
                reportOutcomeConflict(job);
            }
        } catch (Exception ex) {
            // Chính sách phải phân biệt phase/SMTP outcome.
            var outcome = errors.classify(ex);
            jobs.persistClassifiedOutcome(
                    job, outcome, clock.instant());
        }
    }

    private void reportRateGateFailure(
            ClaimedMailJob job, Exception error) {
        // Log jobId, account, mã lỗi an toàn.
        // Không dump raw exception chứa recipient/token.
    }

    private void reportOutcomeConflict(ClaimedMailJob job) {
        // Cần reconciliation; không tự retry SMTP.
    }
}
~~~

`ClaimedMailJob`, `MailOutboxRepository`, `MailSubmissionErrorPolicy` và các method được dùng là **abstraction minh họa**, không phải API có sẵn. Ví dụ làm rõ thứ tự:

~~~text
Claim -> Validate -> Rate admission
       -> Begin attempt -> SMTP
       -> Persist classified outcome
~~~

### Những điểm production phải bổ sung

- Account/tenant authorization và mapping quota scope được kiểm tra tại dispatcher.
- Đọc lại trạng thái business: email hết hạn, đã unsubscribe hoặc đã hủy phải không gửi.
- Lấy và giải phóng SMTP concurrency slot; đảm bảo không giữ slot trong thời gian defer.
- Phối hợp daily budget + rate token + slot theo reservation semantics rõ ràng.
- `beginSubmission` phải kiểm tra claim token/lease/status trong transaction ngắn.
- Exception khi **compose**, khi **SMTP submit** và khi **DB persistence** phải được tách phase; một `catch(Exception)` trong khung không đủ để khẳng định lỗi nào an toàn để retry.
- Nếu SMTP accepted nhưng `markSubmitted` không lưu được, phải đối soát `UNKNOWN`, không gửi lại ngay.
- Khi một batch gồm nhiều messages/recipients, kết quả có thể partial; cần trạng thái per message/recipient nếu provider trả partial acceptance.
- Không log exception raw vì provider có thể echo địa chỉ người nhận hoặc MIME.
- Mỗi bước không cần giữ một DB transaction xuyên SMTP I/O.

### Vị trí chính xác để xác minh quota

Permit nên được lấy **gần lúc network submission thực sự bắt đầu**. Nếu reserve hàng nghìn permit rồi xếp job vào executor lâu, rate limiter không còn phản ánh chính xác tốc độ gửi ra. Dùng bounded worker pool và hạn chế số in-flight reservations.

## 26. Khi rate gate lỗi: fail closed, bounded fallback hay fail open?

| Chính sách | Hành vi | Khi cân nhắc |
|---|---|---|
| **Fail closed** | Không gọi SMTP, defer job bền vững | Mặc định an toàn cho bulk/marketing |
| **Fail open** | Vẫn submit khi không kiểm soát được quota | Có nguy cơ vượt quota, chỉ có thể cân nhắc trong điều kiện đặc biệt đã chấp nhận rủi ro |
| **Bounded emergency fallback** | Gửi lượng rất nhỏ theo budget toàn cụm | Email bảo mật quan trọng, có phê duyệt và nguồn quota dự phòng rõ |
| **Failover provider** | Route sang provider đã được phê duyệt | Cần sender verification, quota riêng và outcome cũ an toàn |

**Không mặc định fail open để “không mất email”.** Nếu dùng outbox, fail closed **không làm mất mail intent**; nó trì hoãn gửi cho đến khi có thể cấp phép. Vấn đề còn lại là SLA và deadline, cần quan sát.

### Bounded fallback phải có giới hạn toàn cụm

Một local emergency limiter 1/s trên 50 pods có thể tạo 50/s, vẫn vượt quota account. Nếu chọn fallback, cần:

- Một nguồn admission chung hoặc một coordinator đã định trước.
- Account/lane được phép sử dụng.
- Budget/TTL/fallback window và audit.
- Cơ chế tự tắt khi shared limiter phục hồi.
- Cảnh báo tới vận hành.

Không âm thầm chuyển sang SMTP credential “admin” có quyền gửi rộng để bypass quota.

## 27. Retry throttling khác với rate limiter DENIED

Hai tình huống:

**Ứng dụng tự DENY trước khi gọi SMTP:**

~~~text
job.status        = PENDING
job.available_at  = now + retryAfter
job.attempt_count = giữ nguyên
reason            = TENANT_RATE_LIMIT
~~~

**Provider đã nhận submission request và báo tạm từ chối:**

~~~text
job.status        = RETRY
job.available_at  = now + backoff
job.attempt_count = đã tăng cho lần thử SMTP
reason            = PROVIDER_TEMPORARY_THROTTLE
~~~

Trạng thái `RETRY` chỉ dùng khi đã có lỗi mà policy quyết định có thể thử lại. Một request chưa được rate gate cấp permit **không phải SMTP failure**.

### SMTP throttling khác HTTP 429

SMTP có reply codes như `421`, `450`, `451`, `452`, và enhanced status tùy provider; không phải mọi 4xx đều là throttling. Với **HTTP email API** có thể nhận HTTP 429 và header `Retry-After`. Không dùng “429 SMTP” như một mã chung.

Một SMTP response có thể chứa recipient:

~~~text
451 4.7.0 Temporarily deferred <someone@example.test>
~~~

Không log nguyên exception message/SMTP transcript. Log mã nội bộ, provider account ID và jobId opaque.

## 28. Retry có backoff, jitter và không chiếm quota trước thời điểm cần thiết

Một retry policy:

\[
d_n = \min(d_{\max},d_0\times 2^{n-1})
\]

Với *full jitter*:

\[
d_{\text{retry}} \sim U(0,d_n)
\]

Nếu provider đề nghị một thời gian tối thiểu hoặc quota day reset time, `available_at` không được sớm hơn mốc đó.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

public final class MailRetryBackoff {
    private final long baseMillis;
    private final long maximumMillis;

    public MailRetryBackoff(
            Duration base, Duration maximum) {
        this.baseMillis = base.toMillis();
        this.maximumMillis = maximum.toMillis();
        if (baseMillis <= 0
                || maximumMillis < baseMillis) {
            throw new IllegalArgumentException(
                    "Invalid retry delays");
        }
    }

    public Instant nextAttempt(
            Instant now, int failedAttemptCount) {
        if (failedAttemptCount < 1) {
            throw new IllegalArgumentException(
                    "failedAttemptCount must be positive");
        }

        long cap = baseMillis;
        for (int i = 1; i < failedAttemptCount; i++) {
            cap = cap > maximumMillis / 2
                    ? maximumMillis
                    : Math.min(maximumMillis, cap * 2);
        }
        long wait = ThreadLocalRandom.current()
                .nextLong(cap + 1);
        return now.plusMillis(wait);
    }
}
~~~

Đây là helper minh họa. Với production, cần minimum retry delay nếu không muốn delay gần 0, max attempts, job expiry, error classification và lịch provider-specified cooldown. Không retry một lỗi authentication/permanent sender permission như temporary throttling.

**Backoff không thay thế rate gate.** Khi job tới `available_at`, nó vẫn xin permit theo tenant/provider account vì những job khác đã có thể tiêu thụ quota trong lúc chờ.

## 29. SMTP UNKNOWN outcome và tác động tới quota accounting

Điểm khó nhất trong kết hợp DB outbox, Redis limiter và SMTP là ba hệ thống **không có cùng transaction**:

~~~text
Worker reserves account + tenant rate tokens
          |
          v
Worker writes PROCESSING / attemptStarted
          |
          v
JavaMailSender.send(message)
          |
          +-- Server accepts DATA
          |
          +-- Network drops before client receives result
          |
          v
App sees exception; DB still PROCESSING
~~~

Nếu app tự động:

~~~text
refund all rate tokens
mark job RETRY
resend through provider B immediately
~~~

thì cả accounting lẫn delivery có thể sai: provider A đã hạch toán và accepted message, và email mới qua B tạo bản trùng.

Một chính sách thận trọng:

1. Phân loại outcome theo phase SMTP và evidence.
2. Khi không biết provider đã accepted hay chưa, đặt `UNKNOWN` hoặc trạng thái cần reconciliation.
3. Không hoàn quota reservation chỉ vì có exception.
4. Dùng provider message trace/idempotency feature **nếu provider thật hỗ trợ**.
5. Chỉ retry hoặc failover theo quy tắc rủi ro duplicate của nghiệp vụ.
6. Ghi attempt history với provider/account, started/finished/status code an toàn.

**Rate limiter không đem lại exactly-once delivery.** Nó chỉ hạn chế số thao tác được phép bắt đầu ở một phạm vi thời gian.

### Lease expiry không chứng minh SMTP chưa gửi

Khi worker đã bắt đầu submit rồi bị kill, lease hết hạn. Worker sau không thể suy ra rằng job chưa được server chấp nhận. Cần tách `CLAIMED` trước network call khỏi `PROCESSING` đã bắt đầu attempt, kiểm tra claim token/fencing và đưa status không rõ tới reconciliation thay vì replay mù.

## 30. Failover provider phải có quota và quyền riêng

Một hệ thống có Provider A chính và B dự phòng:

~~~text
Tenant A job
   |
   v
Routing policy
   |
   +-- Provider A account
   |       +-- Account A quota
   |       +-- Tenant A share on account A
   |
   +-- Provider B account
           +-- Account B quota
           +-- Tenant A share on account B
~~~

Khi chuyển tuyến:

- Job chỉ được dùng Provider B nếu sender identity/domain đã được xác minh và policy cho phép.
- Provider B có quota scopes riêng, **không dùng lại bucket A** nếu hoàn toàn độc lập.
- Nếu A/B nằm dưới một organization quota chung, cả hai phải đồng thời tôn trọng global scope.
- Không chuyển ngay khi A có `UNKNOWN` outcome.
- Không dùng nhiều providers như cách né anti-abuse restrictions hoặc hợp đồng gửi mail.

Provider failover không đơn thuần là thay giá trị `spring.mail.host` trên một singleton `JavaMailSenderImpl` đang dùng chung giữa nhiều thread. Tạo sender/adapter riêng theo route, với credential và sender permission độc lập.

## 31. Quota theo tenant khi cùng một tenant có nhiều sản phẩm

Một tenant có thể gửi email từ nhiều module:

~~~text
Tenant A
   |
   +-- Billing service
   +-- Account security service
   +-- Campaign service
   |
   +-- Tenant-level policy
   |
   +-- Provider-account-level policy
~~~

Nếu mỗi module có một limiter 5/s độc lập, tổng tenant rate có thể lên tới 15/s. Nếu tenant quota áp trên **toàn bộ sản phẩm**, các module phải chia chung một tenant-level budget. Nếu policy chỉ áp theo product/lane, khóa và giới hạn cần thể hiện chính xác phạm vi đó.

### Cross-account tenant quota

Một tenant có thể dùng:

~~~text
tenant-42 → provider account A (transactional)
tenant-42 → provider account B (subscription)
~~~

Nếu hợp đồng tenant cho tối đa 100.000 recipients/ngày **trên tất cả providers**, quota tenant phải bao phủ cả hai. Một Lua script hai bucket trong **cùng Redis Cluster slot** không tự giải quyết atomicity khi account A/B và tenant-global quota ở những slots khác nhau.

Có thể chọn:

- Database transaction chung cho global daily budget.
- Quota allocator phân phát “sub-budgets” có giới hạn cho từng provider route.
- Một coordinator trung tâm xử lý account và tenant quota đồng thời.
- Đưa keys vào cùng Redis hash slot khi quy mô/chính sách chấp nhận được.

Không cấp cho mỗi provider account toàn bộ quota tenant rồi coi tổng vẫn đúng.

## 32. Quota định kỳ, lịch gửi và ưu tiên theo giờ

Tenant có thể có **quota theo tháng** hoặc gói trả phí, còn provider có **quota rolling 24h**. Một khách hàng dùng gần hết monthly budget có thể vẫn được provider cho phép gửi, nhưng **application tenant policy phải chặn**.

Ví dụ:

~~~text
Tenant contractual budget: 60,000 recipients/month
  remaining = 0

Provider sending account:
  remaining today = 8,000

Result:
  Tenant email is not admitted despite provider capacity.
~~~

Ngược lại, tenant còn ngân sách nhưng provider đã cạn thì cũng phải defer.

### Quiet hours và lịch marketing

Rate limiter chỉ kiểm soát số lượng/tốc độ; không thay thế điều kiện *được phép gửi vào giờ nào*. Một job có thể phải đợi vì:

- Người dùng chọn `scheduled_at` trong tương lai.
- Tenant bị giới hạn chỉ gửi trong business hours.
- Consent/suppression policy.
- Account quota chưa sẵn sàng.
- Provider đang degraded.

`available_at` trong outbox nên phản ánh mốc sớm nhất đã được tính từ các điều kiện biết trước, nhưng **mọi eligibility quan trọng phải được kiểm tra lại trước SMTP submit**. Một job đã được tạo tuần trước có thể không còn đủ consent ở hôm nay.

## 33. Monitoring: metrics của rate limiter phải có ba chiều

Quan sát theo:

1. **Demand:** có bao nhiêu job được tạo và đang chờ?
2. **Admission:** bao nhiêu permit được cấp/từ chối và vì sao?
3. **Supply:** SMTP provider thật sự accepted bao nhiêu submissions?

| Metric | Ý nghĩa |
|---|---|
| `mail_outbox_ready_jobs` | Job đã đến hạn chờ dispatch |
| `mail_outbox_oldest_ready_age_seconds` | Tuổi job due lâu nhất |
| `mail_rate_permit_total` | Số permit cấp theo account/lane |
| `mail_rate_denied_total` | Số lần chặn do quota |
| `mail_rate_denied_duration_seconds` | Delay đề xuất khi bị chặn |
| `mail_rate_gate_errors_total` | Redis/DB/shared limiter lỗi |
| `mail_rate_gate_latency_seconds` | Độ trễ reserve permit |
| `mail_account_daily_quota_remaining` | Budget account còn lại nếu biết |
| `mail_tenant_budget_remaining` | Budget theo tenant nếu tracking phù hợp |
| `mail_smtp_inflight` | Số SMTP operations đang chạy |
| `mail_provider_throttle_total` | Số phản hồi throttling từ provider |
| `mail_submitted_total` | Số accepted submissions |
| `mail_attempt_unknown_total` | Attempts có outcome không chắc chắn |
| `mail_expired_total` | Job quá hạn trước submission |
| `mail_fair_scheduler_wait_seconds` | Thời gian chờ đến lượt theo lane/tier |

### Phân biệt backlog tương lai với backlog thật sự chậm

Một job có `scheduled_at` tuần sau là PENDING nhưng không phải một job quá hạn. Một dashboard tốt nên tách:

~~~text
scheduled_future:
  scheduled_at > now

ready_now:
  scheduled_at <= now
  available_at <= now
  status in PENDING/RETRY

waiting_quota:
  scheduled_at <= now
  available_at > now
  deferReason in QUOTA/TENANT_LIMIT
~~~

Chỉ đếm tổng PENDING sẽ tạo báo động sai khi tenant đặt nhiều lịch tương lai. Chỉ đếm ready_now lại bỏ qua backlog bị defer hàng giờ do cạn daily budget. Cần cả hai.

### Metric labels: tránh cardinality cao và dữ liệu cá nhân

Label nên là tập giá trị nhỏ, đã được kiểm soát:

~~~text
provider=PRIMARY
account_tier=PRODUCTION
lane=TRANSACTIONAL
decision=DENIED
reason=TENANT_RATE
~~~

Không dùng `recipient`, raw email address, mail job UUID, subject hoặc một tenant ID vô hạn làm tag Prometheus mặc định. Nếu có hàng chục nghìn tenants, một label `tenant_id` trên mọi metric cũng có cardinality cao và chi phí lớn; cân nhắc aggregate theo plan/tier và dùng hệ thống job/audit riêng để tra tenant cụ thể.

## 34. Ví dụ Micrometer: ghi nhận permit và deny

Trong Spring Boot thường sử dụng Micrometer để xuất application metrics:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public final class MailQuotaMetrics {
    private final MeterRegistry metrics;

    public MailQuotaMetrics(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    public void recordDecision(
            String providerGroup,
            String lane,
            String reason,
            boolean permitted) {
        metrics.counter(
                "mail_quota_admission_decisions",
                "provider_group", providerGroup,
                "lane", lane,
                "reason", reason,
                "decision", permitted ? "granted" : "denied")
                .increment();
    }
}
~~~

`providerGroup`, `lane` và `reason` phải đến từ **enum/allowlist**, không truyền input tự do của tenant hoặc địa chỉ email. Nếu muốn đo chi tiết theo từng tenant trong một bảng quản trị, hãy dùng database với quyền truy cập và pagination, không đẩy hàng trăm nghìn tenant IDs vào metric labels.

### Có cần gauge remaining tokens?

Remaining tokens trong Redis là trạng thái tức thời. Một gauge lấy dữ liệu quá thường xuyên cho hàng nghìn tenant buckets có thể làm Redis bị tải bởi monitoring. Thường nên quan sát permit/deny, latency, backlog và policy caps; chỉ lấy quota remaining theo scope trọng yếu hoặc phục vụ điều tra có giới hạn.

## 35. Cảnh báo theo SLA thay vì chỉ nhìn SMTP error rate

Một hệ thống có thể có:

~~~text
SMTP 4xx error rate = 0
Outbox backlog      = 200,000 jobs
Oldest OTP pending  = 7 minutes
~~~

Nếu limiter đã chặn tất cả SMTP calls vì quota cạn, provider có thể không có lỗi, nhưng hệ thống vẫn vi phạm SLA của OTP. Các alert nên gắn vào:

- Tuổi job ready vượt mức cho phép theo lane.
- Tenant rate deny kéo dài và backlog tăng.
- Provider throttle tăng dù account limiter đã bật.
- Limiter latency p95/p99 tăng.
- Redis/DB quota store unavailable.
- Outbox scheduler không claim job dù có ready backlog.
- Daily budget cạn quá sớm trong chu kỳ.
- OTP bị starvation bởi lane bulk.
- Submission accepted throughput thấp hơn demand quá lâu.
- `UNKNOWN` outcomes tăng bất thường.

### Đánh giá năng lực bằng số liệu thực

Ví dụ:

~~~text
Demand: 8 recipients/s
Provider safe supply: 5 recipients/s
Net backlog growth: ~3 recipients/s
~~~

Nếu không thay đổi policy, tăng số worker không thể làm backlog giảm bền vững; nó chỉ tạo nhiều requests bị defer. Cần điều tiết nguồn tạo mail, thay lịch campaign, dùng quota/provider được phép hoặc thương lượng tăng hạn mức.

Một ước lượng backlog drain:

\[
t_{\mathrm{drain}} \approx
\frac{\text{backlog cost}}
{\text{accepted capacity} - \text{new demand}}
\]

Chỉ hợp lệ khi accepted capacity lớn hơn new demand và các giá trị theo **cùng một đơn vị**. Daily quota reset, retry, nhiều lane và giá trị cost khác nhau khiến thực tế phức tạp hơn.

## 36. Unit test token bucket bằng đồng hồ giả

Một rate limiter không nên được test bằng cách `Thread.sleep(1000)` rồi hy vọng CI chạy chính xác. Với `LongSupplier ticker`, có thể điều khiển thời gian giả:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;

public final class FakeTicker implements LongSupplier {
    private long nanos;

    @Override
    public long getAsLong() {
        return nanos;
    }

    public void advanceMillis(long milliseconds) {
        nanos += TimeUnit.MILLISECONDS.toNanos(milliseconds);
    }
}
~~~

JUnit 5 + AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.junit.jupiter.api.Test;

class LocalTokenBucketTest {

    @Test
    void grantsBurstButNotBeyondCapacity() {
        FakeTicker ticker = new FakeTicker();
        LocalTokenBucket bucket = new LocalTokenBucket(
                2, 1.0, ticker);

        assertThat(bucket.tryAcquire(1).allowed()).isTrue();
        assertThat(bucket.tryAcquire(1).allowed()).isTrue();

        RateDecision denied = bucket.tryAcquire(1);
        assertThat(denied.allowed()).isFalse();
        assertThat(denied.retryAfter().toMillis())
                .isEqualTo(1000);
    }

    @Test
    void replenishesTokensWithElapsedTime() {
        FakeTicker ticker = new FakeTicker();
        LocalTokenBucket bucket = new LocalTokenBucket(
                1, 2.0, ticker);

        assertThat(bucket.tryAcquire(1).allowed()).isTrue();
        assertThat(bucket.tryAcquire(1).allowed()).isFalse();

        ticker.advanceMillis(500);
        assertThat(bucket.tryAcquire(1).allowed()).isTrue();
    }

    @Test
    void rejectsCostThatCanNeverFit() {
        FakeTicker ticker = new FakeTicker();
        LocalTokenBucket bucket = new LocalTokenBucket(
                2, 1.0, ticker);

        assertThatThrownBy(() -> bucket.tryAcquire(3))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Những test trên chỉ xác minh **local algorithm**. Chúng không chứng minh một cụm Kubernetes với 10 pods giữ được aggregate rate. Với Redis/shared store, cần integration test concurrency thật.

## 37. Integration test Redis: nhiều worker không lấy quá quota chung

Một bài test quan trọng:

~~~text
Account bucket:
  capacity = 10
  refill = disabled for test observation interval

Tenant A bucket:
  capacity = 10

100 concurrent workers each reserve cost 1

Expected in the controlled window:
  Granted = 10
  Denied  = 90
  Total consumed = 10
~~~

Với Lua script minh họa ở bài, refill luôn dương; trong integration test có thể dùng một refill rất nhỏ, một cửa sổ test đủ ngắn, hoặc một clock/test implementation được kiểm soát. **Không đặt refill=0 vào script hiện tại**, vì nó chủ động từ chối policy không hợp lệ. Test phải kiểm soát thời gian và race để không sinh kết quả sai do token nạp lại trong lúc chạy.

### Trường hợp hai bucket không được trừ dở dang

~~~text
Account tokens = 1
Tenant A tokens = 0
Tenant B tokens = 1

Request Tenant A -> DENIED
Request Tenant B -> GRANTED

If Tenant A had consumed the shared token first,
Tenant B would have failed incorrectly.
~~~

Test cần đọc lại Redis state để xác minh request DENIED **không trừ account**. Nếu hệ thống dùng script nhiều khóa, test phải chạy trên môi trường Redis Cluster thật hoặc cấu hình tương ứng để thấy lỗi CROSSSLOT khi hash tags không khớp.

### Những kịch bản cần bao phủ

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| RD-01 | Nhiều threads cùng xin token account | Tổng grant không vượt bucket theo cửa sổ |
| RD-02 | Tenant A hết, account còn | A denied, account không bị trừ |
| RD-03 | Account hết, tenant B còn | B denied, tenant B không bị trừ |
| RD-04 | Cost recipient khác nhau | Trừ đúng đơn vị theo policy |
| RD-05 | Cost lớn hơn capacity | Invalid cost, không chờ vô hạn |
| RD-06 | Redis script timeout | ERROR/fail closed, không cấp phép giả |
| RD-07 | Redis restart/failover | Xử lý state lost theo policy và headroom |
| RD-08 | Key TTL expiry | Không phục hồi token quá sớm |
| RD-09 | Account policy thay đổi | Không để replica dùng hai policy versions ngoài kiểm soát |
| RD-10 | Cluster keys khác hash slot | Phát hiện lỗi, không fallback không giới hạn |
| RD-11 | Chia quota tenant nhiều provider | Global budget vẫn được bảo vệ |
| RD-12 | Credential rotation | Không reset provider-account bucket |
| RD-13 | Retry cùng request bị timeout | Accounting bảo thủ/idempotent reservation nếu thiết kế hỗ trợ |
| RD-14 | Cả hai bucket còn permit | Chỉ một atomic grant chung |

### Tránh một hiểu nhầm về retry reserve

Nếu client gọi Lua script, Redis đã cấp permit nhưng reply mất trên mạng, client có thể thử lại và **tiêu thụ token lần thứ hai**. Điều đó không nhất thiết làm vượt quota, nhưng có thể giảm throughput thực tế. Với nhu cầu tối ưu hơn, có thể bổ sung **reservation ID** và idempotent accounting có TTL/retention phù hợp, nhưng chính nó tạo thêm state và phải xử lý race. Không hoàn token nếu không biết đã xảy ra SMTP submission hay chưa.

## 38. Load test kết hợp database outbox và SMTP sink

Để kiểm tra production design, cần test từ **đầu vào job** đến **SMTP adapter** chứ không chỉ mỗi bucket:

~~~text
Test producer
      |
      v
PostgreSQL outbox
      |
      v
N Spring worker replicas
      |
      v
Shared Redis limiter
      |
      v
SMTP sink / server giả lập
      |
      v
Record accepted submissions
~~~

Ví dụ các kịch bản:

| Test | Mục tiêu |
|---|---|
| 1 tenant, burst 10.000 jobs | Không vượt account safe rate |
| 50 tenants đều có job | Không tenant nào bị starvation không có lý do |
| 1 tenant gửi cực lớn, 1 tenant gửi OTP | OTP có độ trễ trong SLA |
| Autoscale từ 2 lên 10 pods | Aggregate throughput vẫn giới hạn |
| Rolling deploy 2 phiên bản config | Không cấp quá permit theo policy chuyển đổi |
| Provider nhận chậm 10 giây | Concurrency slot bảo vệ in-flight calls |
| Redis tạm mất kết nối | Job không biến mất và không flood provider |
| Worker crash sau claim | Lease phục hồi, không mất job |
| Worker crash sau SMTP accepted | UNKNOWN/reconciliation, không resend mù |
| Account quota ngày cạn | Job defer đến window/recheck hợp lệ |
| Campaign đồng loạt ở nhiều tenant | Fair scheduler xử lý theo weights/cost |
| Bulk recipient message | Đếm recipient cost đúng, không chỉ message |

Sử dụng một SMTP sink hoặc test double như Mailpit/GreenMail tùy công nghệ dự án, kết hợp một cơ chế tạo responses/latency theo kịch bản. Sink không nhất thiết có quota thật; muốn test provider throttling cần giả lập reply codes hoặc dùng **sandbox account được phê duyệt**.

### Không test bằng tài khoản/recipient production

Không cần gửi hàng nghìn email thật để chứng minh limiter. Các load tests nên dùng sandbox SMTP, dữ liệu giả và nội dung không nhạy cảm; đo rate, concurrency, loss/retry và trạng thái DB thay vì “thư có vào Gmail thật không”.

### Thông số cần thu thập

- Requests accepted by SMTP sink theo cửa sổ.
- Account/tenant granted vs denied permits.
- Retry/queue backlog age và số job expired.
- Rate gate p95 latency, Redis CPU/network.
- DB claim latency và row contention.
- Executor active threads/queue length.
- Fairness theo tenant tier/lane.
- Email duplicate rate trong các crash windows.

Một throughput cao nhưng gây duplicate, mất job hoặc vượt quota **không phải thành công**.

## 39. Runbook: tenant bị chặn quá lâu

Giả sử tenant B báo email xác nhận đơn hàng chậm 20 phút:

~~~text
tenant B:
  due jobs = 2,100
  submitted last 15 min = 0
  rate denied = high
  SMTP errors = 0
~~~

Đừng kết luận provider hoạt động tốt chỉ vì không có SMTP errors. Limiter có thể chặn mọi submissions trước khi provider nhận request.

### Bước 1: phân biệt nguyên nhân quota

1. Xem job còn `PENDING/RETRY`, `available_at` và defer reason.
2. Xác định account/tenant quota key đang áp dụng.
3. Kiểm tra tenant contract/tier, policy version và quota window.
4. Xem provider account budget còn hay đã hết.
5. Kiểm tra công cụ khác có đang dùng account mà dispatcher không biết.
6. Kiểm tra Redis script errors, TTL và delay đề xuất.
7. So sánh số permits granted với số SMTP accepted.

### Bước 2: xem fairness và queue chọn job

Nếu account còn quota nhưng B không được chọn:

- Một tenant khác có đang đứng đầu FIFO quá lâu?
- Scheduler có phân phối theo tenant/lane không?
- Bị giới hạn `batchSize` và claim quá nhiều job của một tenant không?
- B có lỗi permission/eligibility mà metric đang ghi nhầm thành quota deny?
- Tenant B có cost per message lớn hơn burst capacity nên không bao giờ được cấp?
- Một rate limiter key có bị sai scope hoặc bị giữ stale policy không?

### Bước 3: thao tác có thể làm

- Tạm ngưng batch không khẩn cấp để bảo vệ email quan trọng.
- Giảm token burst của nguồn đang tạo spike, không chỉ tăng worker.
- Sửa quota key/policy nếu có bằng chứng mapping sai.
- Reconcile account usage với provider dashboard.
- Điều chỉnh fair scheduler weights trong phạm vi hợp đồng/provider quota.
- Giữ job bền vững, không xóa hàng loạt mail vì backlog lớn.

### Bước 4: kiểm tra hậu sửa

- Tenant B bắt đầu có permits và SMTP accepted.
- Aggregate account throughput vẫn trong safe cap.
- Backlog age giảm.
- Không xuất hiện retry storm hoặc duplicate spike.
- Không có tenant khác bị starvation do thay policy.

## 40. Runbook: provider vẫn throttling dù đã dùng limiter

Một provider có thể báo SMTP 4xx throttling dù limiter nội bộ đúng theo lý thuyết:

1. **Scope sai:** quota thực theo organization, nhưng application giới hạn từng credential.
2. **Nhiều nguồn gửi:** app legacy, marketing platform hoặc scripts chia account.
3. **Rolling window khác:** app dùng fixed window, provider dùng sliding window.
4. **Burst quá cao:** refill trung bình đúng nhưng burst không được phép.
5. **Đơn vị sai:** app đếm messages còn provider đếm recipients.
6. **Replica scaling:** một số pods dùng local limiter hoặc policy cũ.
7. **TTL/failover reset:** Redis key được tạo lại đầy token quá sớm.
8. **Reputation throttle:** provider giảm tốc tạm thời ngoài quota công bố.
9. **Connection cap:** quá nhiều SMTP operations dù message rate thấp.
10. **Clock/policy drift:** scheduler có thời điểm/điều kiện chờ sai.

### Quy trình giảm thiểu

~~~text
Provider begins throttling
        |
        v
Pause or reduce noncritical bulk lane
        |
        v
Verify provider account and quota unit
        |
        v
Inspect aggregate sends across all workers/apps
        |
        v
Lower rate/burst and apply safe backoff
        |
        v
Keep jobs in outbox until permits available
        |
        v
Restore gradually based on observed acceptance
~~~

Không “sửa” bằng cách tăng `ThreadPoolTaskExecutor.maxPoolSize` hoặc tạo thêm SMTP credentials với cùng quota account. Tăng concurrency khi provider đang throttling thường làm lỗi nặng hơn.

### Adaptive throttling

Nếu provider giảm tốc động theo reputation, có thể dùng policy **additive increase, multiplicative decrease (AIMD)**:

\[
r_{t+1} =
\begin{cases}
\max(r_{\min}, \beta r_t), & \text{throttle đáng kể}\\
\min(r_{\max}, r_t+\alpha), & \text{ổn định và còn nhu cầu}
\end{cases}
\]

Trong đó `0 < β < 1`, `α > 0`. Giới hạn tối đa `rmax` vẫn phải tuân thủ provider contract/safe cap; khi không có traffic, đừng tự tăng rate vô hạn chỉ vì chưa thấy lỗi.

## 41. Bảo mật và quyền riêng tư trong quota state

Redis keys, metrics, logs và tracing cũng là nơi có thể tiết lộ thông tin khách hàng. Một số nguyên tắc:

| Đối tượng | Rủi ro | Kiểm soát |
|---|---|---|
| Redis quota key | Chứa email/username/tenant nhạy cảm | Chỉ dùng stable opaque IDs; ACL/TTL |
| Quota policy | Tenant sửa limit của khách khác | Server-side authorization và audit |
| Mail job/outbox | Chứa recipients/payload | DB encryption/RBAC/retention |
| SMTP exception | Provider echo address | Mã lỗi chuẩn hóa, không raw transcript |
| Metrics labels | High-cardinality tenant/recipient | Aggregate theo tier/lane/provider |
| Support UI | Lộ trạng thái gửi của tenant khác | Row-level tenant authorization |
| Audit trail | Lộ cách tổ chức hoạt động | Hạn chế quyền/retention |
| Config secrets | SMTP password/API token | Secret manager, rotation, least privilege |

### Không dùng recipient email làm rate limiter key mặc định

~~~text
mail:rate:recipient:customer@example.test
~~~

Đây là dữ liệu cá nhân trong key của Redis và có thể xuất hiện trong monitoring snapshot, logs hoặc backups. Nếu sản phẩm cần abuse prevention per recipient, hãy thiết kế một scope/token có kiểm soát quyền và retention, cân nhắc privacy implications, thay vì dùng email thô như một thói quen.

### Không dùng tenant ID làm bí mật

Tenant ID có thể là định danh nội bộ không trực tiếp nhận diện người dùng, nhưng khi kết hợp timestamp, loại email và khối lượng gửi có thể bộc lộ thông tin hoạt động doanh nghiệp. Hạn chế chi tiết công khai và audit quyền truy cập, đặc biệt với dashboard cross-tenant.

### Rate limiter không thay consent/suppression

Một tenant có thể còn quota nhưng không được phép gửi spam hoặc email tới người đã unsubscribe. Trước SMTP submit, cần kiểm tra authorization nghiệp vụ, consent/suppression và loại thông báo. Rate limiting chỉ là một lớp bảo vệ tài nguyên, không phải xác nhận tính hợp lệ của nội dung gửi.

## 42. Anti-pattern trong hệ thống đa tenant

### 42.1. Chỉ `Thread.sleep` giữa hai lần `send`

Nhiều workers/replicas làm tổng rate vượt giới hạn; sleep giữ thread. Dùng distributed gate và durable deferral.

### 42.2. Chỉ đặt maxPoolSize để “giới hạn thư/giây”

Pool size là concurrency, không phải rate hoặc quota ngày.

### 42.3. Một local bucket trên mỗi replica

Khi scale từ 2 lên 10 pods, aggregate throughput có thể tăng gấp năm. Dùng shared admission hoặc phân chia budget có kiểm soát.

### 42.4. Key theo credential version thay vì provider account

Rotate password rồi bucket reset, trong khi quota provider vẫn là một account. Chọn scope theo hợp đồng provider.

### 42.5. Chỉ có tenant limiter, không có account limiter

Mỗi tenant gửi dưới giới hạn của mình, nhưng tổng các tenants vẫn có thể vượt provider account quota.

### 42.6. Chỉ có account limiter, không có tenant fairness

Một khách hàng batch lớn có thể chiếm toàn bộ shared capacity; các tenant khác bị starvation.

### 42.7. Cấp token account rồi phát hiện tenant bucket thiếu

Quota bị tiêu tốn dở dang. Dùng atomic hierarchical reservation hoặc cơ chế coordinated admission.

### 42.8. Dùng Redis GET/SET không nguyên tử

Hai workers có thể đọc cùng số tokens và cùng cho phép, vượt budget. Cần script/transaction với atomicity phù hợp.

### 42.9. Redis TTL quá ngắn hoặc restart khởi tạo bucket đầy

State bị quên trước khi refill đủ, cho phép burst vượt policy. Định nghĩa TTL, Redis persistence/failover và headroom.

### 42.10. Nhầm calendar day với rolling 24 giờ

Counter reset ở nửa đêm có thể vượt quota rolling ngay sau reset.

### 42.11. Coi một message bằng một recipient

Email nhiều To/Cc/Bcc có thể tiêu tốn quota theo số envelope recipients. Chọn cost units đúng.

### 42.12. Refund permit sau mọi SMTP exception

Provider có thể đã accepted/hạch toán dù client nhận timeout. Không refund mù khi outcome không rõ.

### 42.13. Retry ngay khi bị provider throttle

Retry storm làm tăng 4xx; cần backoff/jitter, quota recheck và max attempts.

### 42.14. Tạo thêm SMTP accounts/keys để né anti-abuse

Việc này có thể vi phạm chính sách provider, ảnh hưởng deliverability và danh tiếng. Failover chỉ cho route hợp lệ, không dùng để bypass restrictions.

### 42.15. Cho tenant tự chọn quota scope/account của tenant khác

Nguy cơ lạm dụng budget và sender identity. Mapping phải được xác minh server-side.

### 42.16. Claim quá nhiều job trước khi có capacity

Lease hết hạn trong executor queue, làm duplicate work. Claim batch nhỏ, có backpressure và chỉ reserve gần lúc submit.

### 42.17. Gửi SMTP trong transaction quota/outbox đang giữ lock

Network I/O kéo dài gây DB contention; commit reservation/claim nhanh rồi gửi ngoài transaction.

### 42.18. Fail open vô giới hạn khi Redis gặp sự cố

Mất shared control trên nhiều replicas có thể lập tức flood provider. Fail closed hoặc emergency budget chung.

### 42.19. Không theo dõi backlog age

SMTP error rate bằng 0 không có nghĩa thư đang tới hạn được gửi; các jobs có thể bị quota deny nhiều giờ.

### 42.20. Log raw exception, recipient hoặc tenant quota detail không cần thiết

Tăng rủi ro lộ dữ liệu và high cardinality. Sử dụng structured log, ID opaque, reason code, quyền và retention.

## 43. Checklist triển khai production theo giai đoạn

Một lộ trình triển khai tránh bật full traffic ngay khi vừa có token bucket:

### Giai đoạn 1: inventory và chính sách

1. Liệt kê tất cả provider accounts, SMTP credentials và applications cùng sử dụng.
2. Xác định quota scope thật theo provider/organization/account/credential/sender.
3. Xác định đơn vị: messages, recipients, API requests, connections, byte size.
4. Xác định cửa sổ: per second, sliding minute, rolling 24h hoặc calendar day.
5. Xác định burst allowance và concurrency cap.
6. Liệt kê tenant tiers, các loại email và SLA.
7. Thiết kế access policy của tenant với sender/provider account.
8. Chọn safe budget thấp hơn giới hạn provider khi cần headroom.

### Giai đoạn 2: lưu job bền vững

1. Tạo outbox trong cùng transaction với business event.
2. Thêm idempotency key cho ý định gửi.
3. Lưu `scheduled_at`, `available_at`, `status`, `attempt_count`.
4. Thêm claim token, lease và conditional status transitions.
5. Không cho SMTP send trước khi transaction tạo job commit.
6. Có chính sách khi job expired/cancelled hoặc người nhận unsubscribe.

### Giai đoạn 3: admission control

1. Định nghĩa policy account và tenant, với đơn vị cost đúng.
2. Triển khai atomic multi-bucket reservation.
3. Chọn DB/Redis/shared service phù hợp với quy mô và nhất quán cần thiết.
4. Xác định TTL, policy version, clock và failover behavior của limiter.
5. Thêm daily quota/rolling window và SMTP concurrency cap.
6. Chỉ reserve gần lúc submission, không lấy permit cho hàng nghìn jobs trước.
7. Khi deny, đặt lịch lại trong outbox, không tăng SMTP attempt.
8. Khi limiter outage, fail closed hoặc bounded fallback có audit.

### Giai đoạn 4: fairness và SLA

1. Tách lane SECURITY/TRANSACTIONAL/BULK.
2. Chọn fair scheduler (round robin, weighted hoặc deficit).
3. Tránh batch một tenant giữ toàn bộ worker claims.
4. Theo dõi tuổi job theo tenant tier/lane, không chỉ tổng backlog.
5. Dành quota cho email cần thời gian phản hồi ngắn theo policy.
6. Định nghĩa deadline; không gửi OTP đã hết hạn.

### Giai đoạn 5: kiểm thử và vận hành

1. Unit test refill, burst và cost.
2. Integration test nhiều workers reserve cùng account key.
3. Test cross-tenant permissions và quota isolation.
4. Test Redis timeout/failover/TTL/policy reload.
5. Test database claim/lease và crash windows.
6. Test SMTP temporary throttle/unknown outcome bằng sink/test double.
7. Test load nhiều replicas và fairness khi một tenant gửi burst.
8. Bổ sung alerts permit deny, backlog age, quota remaining và limiter errors.
9. Rollout trước với sandbox hoặc một phần traffic hợp lệ.
10. Đo provider accepted throughput và điều chỉnh safe cap theo số liệu.

### Tiêu chí nghiệm thu

| Điều kiện | Bằng chứng cần có |
|---|---|
| Không vượt quota account | Multi-replica rate test và provider telemetry |
| Tenant không “mượn” quota trái quyền | Authorization tests và mapping policy |
| Một tenant không làm đói tenant khác | Fairness/load tests theo lane/tier |
| Không mất mail khi bị DENIED | Outbox persisted + recovery tests |
| Không tạo SMTP attempts khi chưa có permit | Attempt count và adapter mocks |
| Không gửi trùng do claim race đơn giản | DB concurrency/claim-token tests |
| Crash sau SMTP không bị retry mù | UNKNOWN/reconciliation tests |
| Redis outage không flood provider | Fail-closed test |
| Quota ngày reset đúng | Calendar/rolling-window tests theo provider policy |
| Không rò recipient/credential | Logging/security tests |
| Có cảnh báo job trễ | Dashboard và alert rehearsal |

## 44. Câu hỏi thường gặp

**Rate limiter theo tenant khác theo provider account như thế nào?** Provider-account limiter bảo vệ quota chung của nhà cung cấp, còn tenant limiter phân chia năng lực và thực thi chính sách sản phẩm. Với account shared, một job cần qua cả hai.

**Nếu mỗi tenant được 5 mail/giây mà provider account cho 10 mail/giây, có thể có 100 tenants không?** Có thể, miễn **tổng submissions** vẫn bị account gate giới hạn 10/giây và có chính sách fairness. Tenant cap là mức tối đa riêng, không phải bảo đảm tất cả tenants được 5/giây đồng thời.

**Rate limiter có tự bảo đảm mỗi tenant được công bằng không?** Không. Limiter ngăn vượt cap, còn thứ tự chọn job và share năng lực cần fair scheduler hoặc queue policy phù hợp.

**Có thể dùng `@Async` với ThreadPoolTaskExecutor để rate limit không?** Không đủ. Nó giúp thực thi bất đồng bộ/giới hạn concurrency cục bộ, không hạch toán rate của provider account/tenant trên toàn cụm.

**Spring Mail có sẵn per-tenant rate limiter không?** `JavaMailSender` chỉ phục vụ SMTP submission, không tự nhận biết tenant hoặc provider quota. Cần admission layer trong application/dispatcher hoặc dịch vụ chuyên trách.

**Có thể chỉ cấu hình `spring.mail.*` để giới hạn email/giây không?** Không. Các thuộc tính SMTP không tự tạo token bucket, daily quota counter hoặc fair scheduler.

**Một tenant có 20 recipients trong một message thì tốn mấy tokens?** Phụ thuộc policy: account recipient bucket có thể trừ 20, tenant message bucket trừ 1, và concurrency gate trừ 1 slot. Phải xác định từng đơn vị.

**Tại sao cost phải được tính trước SMTP?** Limiter cần biết lượng capacity cần reserve. Với multiple recipients, chỉ đếm lời gọi `send` có thể đánh giá thấp quota bị tiêu thụ.

**Có nên split một message khi cost vượt burst capacity?** Chỉ khi nghiệp vụ và provider cho phép; cần bảo vệ quyền riêng tư giữa recipients, Bcc semantics và đảm bảo mỗi nhóm được tính quota đúng. Nếu không, từ chối job/config không hợp lệ.

**Dùng Redis là tự động phân tán đúng chưa?** Chưa. Phải có atomic reservation, key scope đúng, TTL/failover policy, xử lý Redis timeout và phiên bản cấu hình nhất quán.

**Tại sao cần hai Redis keys cùng hash tag?** Redis Cluster chỉ cho phép thao tác atomic nhiều keys qua Lua khi các keys nằm cùng hash slot. Hash tag là một cách colocate theo account scope.

**Nếu tenant có quota toàn tổ chức nhưng gửi qua nhiều provider accounts thì sao?** Cần một global tenant quota được điều phối cùng các account quotas; không giả định script với keys ở nhiều cluster slots luôn atomic.

**Có thể đặt một rate limiter riêng trong mỗi replica?** Chỉ khi tổng giới hạn đã được chia an toàn và số replicas được kiểm soát. Với account shared, local buckets độc lập có thể vượt quota khi autoscale.

**Bật thêm SMTP credentials có tăng quota không?** Không nhất thiết. Nhiều credentials có thể chia một account/organization limit. Chọn quota key theo phạm vi nhà cung cấp công bố.

**Token bucket có tự kiểm soát daily sending limit?** Không. Cần bộ đếm budget theo đúng window, đặc biệt nếu nhà cung cấp dùng rolling 24h.

**Tại sao không hoàn token khi MailSendException được ném?** Vì provider có thể đã accepted hoặc hạch toán một phần dù client gặp lỗi. Hoàn token không có bằng chứng có thể phá quota accounting.

**Rate gate bị lỗi có nên gửi mail tiếp để tránh mất mail?** Với durable outbox, có thể giữ job mà không mất intent. Fail closed thường an toàn hơn; emergency fallback cần budget toàn cụm rõ ràng.

**Khi bị DENIED có nên tăng `attempt_count` không?** Không nếu SMTP chưa được gọi. Sử dụng counter defer riêng; attempt count phản ánh lần submit thực.

**Nếu SMTP trả 421 thì chắc chắn do rate limit?** Không. SMTP 421 có thể là service unavailable/closing connection. Cần classifier theo provider response, phase và tài liệu thực tế.

**HTTP 429 có dùng cho SMTP không?** HTTP 429 thuộc API HTTP. SMTP có reply/status codes riêng; không gọi “429 SMTP” như một mã phổ quát.

**Làm sao tránh retry storm khi provider throttle?** Lưu `available_at`, dùng exponential backoff/jitter, max retry policy và xin quota permit lại ở lần thử sau. Đừng retry ngay trong vòng while.

**Nếu email đã accepted nhưng database crash trước update thì sao?** Outcome có thể UNKNOWN. Không resend mù; đối soát/provider trace, idempotency theo khả năng provider và chính sách rủi ro duplicate.

**Có thể dùng Message-ID để bảo đảm exactly-once?** Không. Message-ID giúp correlation nhưng SMTP/receiver không cam kết deduplicate theo header đó.

**Rate limiter có làm email OTP luôn nhanh không?** Không tự động. Cần reserved capacity/priority, scheduler fairness, expiry và provider SLA phù hợp.

**Backlog tăng dù không có SMTP errors có phải lỗi không?** Có thể. Limiter có thể đang chặn đúng nhưng demand vượt quota; vẫn cần capacity planning và cảnh báo theo job age.

**Có nên để tenant chỉnh rate limit qua public API?** Chỉ nếu đó là một chức năng đã được ủy quyền, nằm trong caps hợp đồng và được kiểm tra server-side. Tenant không được thay quota account của tenant khác hoặc bypass hard cap.

**Có thể ghi tenant ID vào Prometheus labels không?** Với số tenant ít và cố định có thể cân nhắc, nhưng high-cardinality thường gây chi phí/khó vận hành. Nên aggregate theo tier/lane; chi tiết theo tenant truy vấn qua kho có quyền.

**Làm sao test rate limit mà không gửi spam thật?** Unit test đồng hồ giả; Redis/PostgreSQL integration tests; SMTP sink/adapter fake để đếm submissions và mô phỏng errors.

**Khi đổi quota trong runtime cần làm gì?** Version policy, đồng bộ cấu hình giữa replicas, xử lý bucket tokens/capacity cũ và kiểm tra không vượt safe provider quota trong thời gian chuyển đổi.

**Failover sang provider khác có cần rate limiting riêng không?** Có. Provider B có sender permission, quota scope và limits khác, hoặc có thể cùng organization budget. Không chuyển route khi outcome A chưa rõ.

## 45. Tổng kết

Trong **Spring Framework Mail**, “rate limiter theo tài khoản hoặc tenant” là một **mẫu thiết kế nhiều lớp**, không phải chỉ một thư viện giới hạn số lời gọi `JavaMailSender.send(...)`.

Các lớp cần phối hợp:

~~~text
Authorized business intent
         |
         v
Durable mail outbox
         |
         v
Fair dispatcher by tenant/lane
         |
         v
Resolve provider account + tenant policy
         |
         v
Atomic hierarchical rate admission
  +-- provider account rate
  +-- tenant or tenant-tier budget
  +-- daily quota when applicable
         |
         v
SMTP concurrency control
         |
         v
JavaMailSender.submit
         |
         v
Classified submission outcome
  +-- SUBMITTED
  +-- RETRY with backoff
  +-- FAILED
  +-- UNKNOWN for reconciliation
         |
         v
Audit, metrics, alerts, recovery
~~~

**Các nguyên tắc cần nhớ:**

1. **Provider account limit là cap tổng**, tenant budget là cơ chế phân phối/giới hạn bên dưới; không lấy một trong hai thay cho cái còn lại.
2. **Đúng scope và đúng đơn vị:** credential khác không nhất thiết quota khác; recipients khác messages; rate khác concurrency và daily quota.
3. **Atomic admission:** khi job cần cả account và tenant tokens, không trừ dở dang giữa các buckets.
4. **Phân tán đúng:** nhiều pods phải chia sẻ quota state, với TTL/failover/clock và policy version được quản lý.
5. **Không mất ý định gửi:** quota DENIED chỉ trì hoãn job trong outbox; không giữ thread ngủ hay bỏ job.
6. **Fairness là vấn đề scheduling:** có thể cần round robin/weighted/deficit scheduling để ngăn tenant lớn chiếm toàn bộ worker.
7. **SMTP retry không phải miễn phí và không hoàn toàn an toàn:** quản lý backoff/jitter, permanent errors và `UNKNOWN` outcome để giảm duplicate.
8. **Quan sát đủ ba mặt:** demand/backlog, admission/denial và provider accepted throughput; cảnh báo theo SLA.
9. **Bảo mật tenant và recipient:** quota key từ server-side identity, logs và metrics không chứa email hoặc credential.

Khi triển khai nhất quán, hệ thống có thể phục vụ nhiều tenant trên một hoặc nhiều tài khoản gửi mail mà vẫn bảo vệ quota, giữ được email quan trọng, phục hồi sau sự cố và phân bổ tài nguyên hợp lý. Thành công của mẫu thiết kế không chỉ đo bằng số thư gửi mỗi giây, mà còn bằng **khả năng giữ đúng ranh giới quota, tính công bằng, tính bền vững và khả năng giải thích vì sao một job được gửi hoặc phải đợi**.
