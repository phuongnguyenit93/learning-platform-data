# Giới hạn tốc độ theo nhà cung cấp

## 1. Vì sao ứng dụng gửi mail phải tuân theo tốc độ của nhà cung cấp?

Trong **Spring Framework Mail**, ứng dụng thường gọi `JavaMailSender.send(...)` để nộp email cho SMTP server. Mã Java có thể tạo hàng nghìn yêu cầu gửi chỉ trong vài giây, nhưng năng lực của **nhà cung cấp email** không vô hạn: mỗi tài khoản, tên miền, địa chỉ gửi, IP, gói dịch vụ hoặc API key có thể bị giới hạn số thư, số người nhận, số kết nối đồng thời và tốc độ submit.

Ví dụ một hệ thống thương mại điện tử vừa chạy chiến dịch cập nhật đơn hàng cho 60.000 người nhận, vừa phải gửi email OTP. Nếu worker lập tức mở nhiều kết nối SMTP để xử lý tất cả công việc:

- SMTP provider có thể trả lỗi tạm thời vì vượt quota hoặc bị throttling.
- Số task retry tăng, làm queue đầy và chiếm thread.
- Email OTP quan trọng bị chậm vì cùng chia năng lực với thông báo ít khẩn cấp.
- Danh tiếng người gửi có thể giảm khi hệ thống phát sinh spike bất thường.
- Một tenant hoặc chiến dịch có thể làm cạn quota chung của toàn tổ chức.
- Nếu không quản lý kết quả SMTP cẩn thận, retry có thể gây email trùng hoặc mất.

**Giới hạn tốc độ theo nhà cung cấp (provider-aware rate limiting)** là cơ chế điều phối lượng mail được nộp tới mỗi provider theo giới hạn thực tế, thay vì đợi server từ chối rồi mới xử lý.

~~~text
Nguồn phát sinh email
  order / security / campaign / batch
                  |
                  v
        Mail outbox / queue
                  |
                  v
       Provider-aware dispatcher
                  |
         +--------+--------+
         |                 |
         v                 v
  Policy Provider A   Policy Provider B
    rate + quota        rate + quota
    concurrency         concurrency
         |                 |
         v                 v
    SMTP/API A          SMTP/API B
~~~

Mục tiêu không chỉ là tránh lỗi `421` hoặc `429`. Một hệ thống tốt còn phải biết **thời điểm được gửi tiếp**, **số job đang chờ**, **ưu tiên loại email quan trọng**, **cách phân phối quota giữa replica/tenant**, và **điều gì xảy ra nếu provider tạm thời không khả dụng**.

## 2. Phân biệt rate limit, concurrency limit và quota

Ba khái niệm thường bị nhầm:

| Loại giới hạn | Câu hỏi trả lời | Ví dụ minh họa |
|---|---|---|
| **Rate limit** | Tối đa bao nhiêu sự kiện trong khoảng thời gian? | 10 message/giây |
| **Concurrency limit** | Tối đa bao nhiêu thao tác đang diễn ra đồng thời? | 5 SMTP submissions đang hoạt động |
| **Quota/budget** | Tổng cộng được tiêu thụ bao nhiêu trong một chu kỳ? | 20.000 recipient/ngày |
| **Connection limit** | Mở bao nhiêu kết nối SMTP đồng thời? | 4 connection/tài khoản |
| **Per-message limit** | Một message chứa bao nhiêu RCPT hoặc bao nhiêu byte? | 50 recipient/message, giới hạn kích thước riêng |
| **Reputation/policy throttle** | Có thể gửi chậm hơn theo mức tin cậy hoặc lỗi trước đó? | Provider tạm giảm tốc sau đợt bounce cao |

**Những con số trong bảng chỉ là giả định để giải thích thuật toán**, không phải quota của Gmail, Microsoft 365, Amazon SES hoặc bất kỳ dịch vụ cụ thể nào.

Một provider có thể đồng thời áp:

~~~text
Per SMTP credential:
  <= 8 messages/second

Per provider account:
  <= 30,000 recipients/24h

Per sender identity:
  <= 3 concurrent submissions

Per message:
  <= 100 recipients

Per SMTP connection:
  provider-specific lifecycle/limits
~~~

Nếu chỉ giới hạn 8 message/giây mà không đếm số recipient trong mỗi message, ứng dụng vẫn có thể vượt quota recipient. Nếu chỉ giới hạn số worker, ứng dụng có thể vượt rate khi các SMTP call hoàn tất rất nhanh.

### Rate không đồng nghĩa số thread

`ThreadPoolTaskExecutor(maxPoolSize=8)` chỉ có thể giữ tối đa 8 task đang chạy, không có nghĩa tối đa 8 thư/giây. Một thread có thể thực hiện nhiều SMTP calls trong một giây nếu provider phản hồi nhanh.

Ngược lại, nếu một SMTP call mất 10 giây, giới hạn 8 thread khiến tốc độ tối đa lý tưởng chỉ khoảng 0,8 call/giây dù policy cho phép 8 call/giây. Muốn đạt throughput vừa đủ cần cân đối **cả rate lẫn concurrency**.

### Quota không phải khoảng chờ giữa hai mail

Đặt `Thread.sleep(1000)` giữa các lần gửi có vẻ tạo tốc độ 1 mail/giây trong một worker; nhưng nếu có 10 worker trên 4 replica thì tổng tốc độ có thể lên tới hàng chục mail/giây. Thao tác sleep còn giữ worker khi nó không làm việc hữu ích.

Rate limiter nên quyết định **có được cấp phép submit lúc này hay không**; khi chưa được, job nên nằm trong queue/outbox tới thời điểm phù hợp.

## 3. “Theo nhà cung cấp” nghĩa là giới hạn theo đúng phạm vi quota

Không có một “tốc độ SMTP” chung cho mọi hệ thống. Hãy xác định quota thực sự được áp ở cấp nào:

| Phạm vi | Ví dụ về khóa giới hạn | Hệ quả kiến trúc |
|---|---|---|
| Provider | `provider=A` | Tất cả sender dùng cùng provider chia budget |
| Account/tenant tại provider | `account=prod-tenant-1` | Nhiều ứng dụng có thể chia một quota |
| SMTP credential / API key | `credential=orders-key` | Tách credential có thể tách hoặc không tách quota |
| Verified domain | `domain=example.com` | Nhiều From cùng domain vẫn dùng quota liên quan |
| Sender identity | `sender=security@example.com` | Policy riêng cho từng From được duyệt |
| IP egress | `ip-group=nat-cluster-A` | Nhiều pod chia cùng IP có thể ảnh hưởng nhau |
| Recipient domain | `recipientDomain=gmail.com` | Có thể cần điều tiết theo domain để giảm deferral |
| Customer tenant | `tenant=customer-A` | Cần fair-share trong ứng dụng, dù provider chỉ giới hạn account |
| Mail category | `lane=SECURITY` | Cần bảo vệ email quan trọng khỏi campaign |

Một account có thể chịu **nhiều giới hạn chồng nhau**. Ví dụ mỗi thông báo cần đồng thời qua:

~~~text
Global provider/account quota
          AND
Per-credential rate
          AND
Per-sender policy
          AND
Application tenant fairness
          AND
Concurrency slot
~~~

Một job chỉ được gửi khi **mọi điều kiện cần thiết đều được đáp ứng**. Đừng chỉ tạo một bucket theo SMTP host nếu provider áp quota cho toàn bộ account hoặc khóa API; đồng thời đừng mặc định chia credential thành nhiều account sẽ tự tăng quota nếu thực tế provider cộng dồn theo organization/domain.

### Một sender có thể dùng nhiều provider

Ứng dụng có thể có một provider chính và một provider dự phòng. Nhưng chuyển route không được dùng để **né chính sách chống spam, quota hoặc giới hạn hợp đồng**. Failover phải được phép theo chính sách của từng provider, đồng thời đáp ứng SPF/DKIM/DMARC, sender verification và quy định gửi mail của tổ chức.

Khi chuyển sang provider khác, không mặc định các con số từ provider A áp dụng cho provider B. Tạo policy riêng và xác định khóa quota của đường gửi mới.

## 4. Những dữ liệu cần thu thập trước khi đặt giới hạn

Trước khi chọn `messagesPerSecond` trong `application.yml`, cần biết:

1. **Hợp đồng hoặc gói dịch vụ:** giới hạn được công bố theo message, recipient, request, ngày, giờ, kết nối hay IP?
2. **Phạm vi tính quota:** account, tenant, domain, API key, sender hoặc pool shared?
3. **Chu kỳ reset:** giờ UTC, timezone provider, rolling 24h, tháng, hoặc sliding window?
4. **Burst allowance:** có cho phép bùng phát ngắn không, hay rate phải đều?
5. **Lưu lượng thực tế:** trung bình, p95/p99 và spike khi campaign/cron chạy.
6. **Độ trễ mỗi submission:** thời gian thiết lập kết nối, chờ SMTP và truyền file.
7. **Số người nhận trong một email:** một thư có một hay nhiều To/Cc/Bcc?
8. **Kết quả lỗi:** mã SMTP/HTTP nào thể hiện throttling; có thông tin thời điểm retry không?
9. **Tham số kết nối:** timeout, connection reuse, limit concurrency và hạn chế attachment.
10. **Số replica và ứng dụng khác:** còn service nào cùng dùng account/provider không?

Nếu provider có dashboard quota hoặc API thống kê, nên lấy đó làm **nguồn tình trạng quota** nhưng xem xét độ trễ cập nhật của dữ liệu. Đồng hồ tự đếm tại ứng dụng không tự phản ánh các message được gửi ngoài ứng dụng bằng cùng credential.

Không bịa quota từ ví dụ Internet hoặc cấu hình của tài khoản khác. Những nhà cung cấp lớn thay đổi quota theo loại tài khoản, gói, reputation, khu vực hoặc lịch sử sử dụng. Kiểm tra tài liệu và account console chính thức khi cấu hình production.

## 5. Đếm theo message hay recipient?

Một message SMTP có thể có nhiều người nhận trong envelope:

~~~text
MAIL FROM:<orders@example.com>
RCPT TO:<a@example.net>
RCPT TO:<b@example.net>
RCPT TO:<c@example.net>
DATA
...
~~~

Với một lần `mailSender.send(message)`, có thể xảy ra:

- **1 message submission**;
- **3 SMTP recipients**;
- nhiều đơn vị quota tùy provider;
- trường hợp một số recipient bị từ chối, những recipient khác vẫn có thể được server chấp nhận theo giao thức và cơ chế gửi.

Nếu quota được tính theo recipient, không được sử dụng bộ đếm **message đơn thuần**.

### Quy tắc cost theo đơn vị

Một policy có thể quy định:

~~~text
Message rate cost    = 1 trên mỗi message
Recipient rate cost  = số recipient envelope thực sự
Daily recipient cost = số recipient tính theo chính sách provider
Attachment budget    = tổng raw MIME bytes khi cần giới hạn size
~~~

Ứng dụng cần tạo một `sendPlan` trước khi submit:

~~~java
public record SendPlan(
        String providerId,
        String credentialId,
        String senderProfileId,
        String notificationType,
        int messageCount,
        int recipientCount) {
}
~~~

`SendPlan` là DTO nghiệp vụ minh họa. Không dùng `email address` làm tag metric hoặc key log. Khi một message gồm nhiều người nhận, các recipient phải được tính theo **SMTP envelope** mà sender thực sự sử dụng, không chỉ dựa vào `getRecipients(Message.RecipientType.TO)` nếu còn Cc/Bcc.

### Vì sao nhiều người nhận có thể khó tính?

Nếu provider từ chối một phần recipient trước hoặc sau DATA, phần quota bị trừ có thể phụ thuộc chính sách cụ thể. Nên dùng quy tắc accounting bảo thủ: **reserve capacity trước submit theo số recipient dự kiến**, rồi đối soát outcome và báo cáo của provider. Không tự “refund quota” sau exception nếu chưa chắc provider không hạch toán thao tác đó.

## 6. Ước lượng tốc độ cần thiết từ backlog và thời hạn

Giả sử có 12.000 email subscription cần hoàn thành trong 60 phút. Tốc độ trung bình tối thiểu theo giả định mỗi email một người nhận:

\[
r_{\mathrm{required}} = \frac{12\,000}{60\times60}
  \approx 3.33\ \mathrm{messages/second}
\]

Nếu nhà cung cấp cho phép một tốc độ an toàn vận hành 5 message/giây, chiến dịch có thể hoàn thành trong khoảng:

\[
t_{\mathrm{ideal}} = \frac{12\,000}{5}
  = 2\,400\ \mathrm{s}\approx40\ \mathrm{minutes}
\]

Đây là **ước lượng lý tưởng** khi không có retry, đứt mạng, quota ngày, thời gian khởi tạo/đóng message, attachment lớn hoặc giới hạn concurrency. Trong thực tế cần chừa biên độ.

Một đại lượng khác:

\[
\text{required concurrency}
\approx \text{target rate}\times\text{mean SMTP service time}
\]

Nếu muốn 5 submission/giây và một submission giữ worker trung bình 0,8 giây:

\[
C \approx 5\times0.8=4
\]

Khoảng 4 SMTP operations đồng thời là điểm bắt đầu để đo, **không phải cấu hình đảm bảo throughput**. Latency biến thiên, connection overhead, server throttling và quota đồng thời có thể làm kết quả khác đi.

### Vì sao nên cấu hình thấp hơn quota tối đa?

Nếu provider công bố một hạn mức, việc đặt đúng bằng ngưỡng có thể gây lỗi khi:

- Provider có sliding window hoặc burst policy khác mô hình ứng dụng.
- Nhiều replica không đồng bộ tuyệt đối.
- Có service khác chia cùng credential.
- Clock/telemetry có độ trễ.
- Một message nhiều recipient bị tính cost khác dự kiến.

Thường cần **operational headroom**, ví dụ chọn một phần quota rồi tăng dần theo đo đạc. Tỷ lệ headroom không cố định; phải căn cứ policy và dữ liệu vận hành.

## 7. Các thuật toán rate limiting phổ biến

Một hệ thống gửi email có thể sử dụng nhiều thuật toán. Không có thuật toán duy nhất phù hợp mọi provider.

| Thuật toán | Cách hoạt động | Phù hợp | Hạn chế |
|---|---|---|---|
| Fixed window counter | Đếm gửi trong cửa sổ cố định | Quota đơn giản theo phút/ngày | Burst tại ranh giới hai cửa sổ |
| Sliding window log/counter | Xem các sự kiện trong khoảng thời gian trượt | Giới hạn sát rolling window | Có thể tốn bộ nhớ/truy vấn |
| Token bucket | Token nạp lại theo tốc độ, cho burst có giới hạn | Giới hạn trung bình kèm burst cho phép | Phải chọn burst capacity đúng provider |
| Leaky bucket / paced queue | Đưa công việc ra theo tốc độ đều | SMTP provider nhạy với spike | Có thể tăng latency cho burst |
| Concurrency semaphore | Giới hạn task đang gửi | Giới hạn connection/SMTP in-flight | Không giới hạn số message/giây |
| Daily budget counter | Đếm tổng quota của chu kỳ | Recipient/day hoặc message/day | Cần xác định đúng reset/window |

Trong thực tế thường kết hợp:

~~~text
Daily quota counter
        AND
Token bucket per provider/account
        AND
Semaphore per SMTP identity
        AND
Per-tenant fair share
~~~

Nếu provider **không cho phép burst**, token bucket có capacity lớn sẽ không phù hợp dù average rate đúng. Có thể chọn capacity nhỏ hoặc một cơ chế pacing đều.

## 8. Token bucket: giới hạn trung bình và burst

Token bucket hoạt động như sau:

1. Bucket có tối đa `capacity` token.
2. Token được nạp lại với tốc độ `refillRate` token/giây.
3. Muốn gửi một message, cần lấy số token tương ứng với cost.
4. Nếu đủ token, cấp phép ngay.
5. Nếu thiếu token, chưa gửi; tính thời điểm có thể thử lại.

Ví dụ:

~~~text
capacity = 10 tokens
refill   = 4 tokens/second
cost     = 1 token/message

Time 0s:       10 tokens, cho phép burst tới 10 message
Sau burst:      0 tokens
Time +0.25s:    1 token, cho phép một message
Time +1.00s:    4 tokens nếu không tiêu thụ
~~~

Bucket cho phép một burst ban đầu nhưng **giới hạn tốc độ dài hạn** xấp xỉ 4 token/giây. Nếu provider yêu cầu gửi đều, nên giảm capacity hoặc kết hợp pacer.

### Cost theo recipient

Nếu provider tính quota theo recipient, một message có 5 người nhận có thể tiêu tốn 5 token:

~~~java
int cost = sendPlan.recipientCount();
RateDecision decision = recipientRateGate.tryAcquire(cost);
~~~

Lúc này `capacity` phải lớn đủ cho cost hợp lệ cao nhất, hoặc ứng dụng phải chia message theo policy. Nếu cost lớn hơn capacity, chờ sẽ **không bao giờ** đủ token; đó là lỗi thiết kế/admission cần phát hiện sớm, không nên retry vô hạn.

### Token bucket không quản lý quota ngày

Bucket refill liên tục có thể cho phép lượng tổng cộng vượt quota 24 giờ. Nếu nhà cung cấp đặt cả `5 messages/second` lẫn `20.000 recipients/day`, cần một bộ đếm daily budget riêng với chu kỳ provider, không thay thế bằng bucket refill.

## 9. Ví dụ Java: một token bucket trong bộ nhớ

Đây là ví dụ **không cần thư viện bên ngoài**, phù hợp minh họa cơ chế cấp phép trong **một JVM**. Nó chủ động **không sleep** khi hết token, để caller có thể để job chờ trong outbox.

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.function.LongSupplier;

public record RateDecision(
        boolean allowed,
        Duration retryAfter) {

    public static RateDecision granted() {
        return new RateDecision(true, Duration.ZERO);
    }

    public static RateDecision denied(Duration retryAfter) {
        return new RateDecision(false, retryAfter);
    }
}

public final class LocalTokenBucket {
    private final double capacity;
    private final double refillTokensPerSecond;
    private final LongSupplier ticker;

    private double tokens;
    private long lastNanos;

    public LocalTokenBucket(
            int capacity,
            double refillTokensPerSecond,
            LongSupplier ticker) {

        if (capacity <= 0 || !Double.isFinite(
                refillTokensPerSecond)
                || refillTokensPerSecond <= 0) {
            throw new IllegalArgumentException(
                    "Capacity and refill rate must be positive");
        }

        this.capacity = capacity;
        this.refillTokensPerSecond = refillTokensPerSecond;
        this.ticker = Objects.requireNonNull(ticker);
        this.tokens = capacity;
        this.lastNanos = ticker.getAsLong();
    }

    public synchronized RateDecision tryAcquire(int cost) {
        if (cost <= 0 || cost > capacity) {
            throw new IllegalArgumentException(
                    "Cost must fit within bucket capacity");
        }

        refill();
        if (tokens >= cost) {
            tokens -= cost;
            return RateDecision.granted();
        }

        double missing = cost - tokens;
        double waitNanos = Math.ceil(
                missing * 1_000_000_000d
                        / refillTokensPerSecond);

        long clampedNanos = (long) Math.min(
                waitNanos, (double) Long.MAX_VALUE);
        return RateDecision.denied(
                Duration.ofNanos(clampedNanos));
    }

    private void refill() {
        long now = ticker.getAsLong();
        long elapsedNanos = Math.max(0L, now - lastNanos);
        lastNanos = now;

        double added = (elapsedNanos / 1_000_000_000d)
                * refillTokensPerSecond;
        tokens = Math.min(capacity, tokens + added);
    }
}
~~~

Sử dụng:

~~~java
LocalTokenBucket limiter = new LocalTokenBucket(
        10, 4.0, System::nanoTime);

RateDecision decision = limiter.tryAcquire(1);
if (decision.allowed()) {
    // Job được phép bắt đầu SMTP submission.
} else {
    // Chưa submit. Lưu lịch thử sau thay vì sleep giữ thread.
    Duration delay = decision.retryAfter();
}
~~~

### Đặc điểm và giới hạn của ví dụ

- `synchronized` bảo đảm việc đọc/nạp/trừ token không cạnh tranh sai khi nhiều thread trong **cùng JVM** cùng gọi.
- `System.nanoTime()` được dùng cho khoảng thời gian trôi qua, không dùng wall-clock có thể bị chỉnh bởi NTP.
- `tryAcquire` trả `retryAfter` để caller xử lý scheduling; **không chờ ngay trong method**.
- Sau khi token được trừ, ví dụ không có hoàn trả. Nếu SMTP chưa bắt đầu do lỗi ngay sau cấp phép, hệ thống có thể mất một ít capacity — cách accounting bảo thủ này an toàn hơn việc hoàn lại sai khi outcome không rõ.
- Không có persistence. Restart process tạo bucket mới đầy token, có thể làm burst ngoài ý muốn.
- Không chia sẻ trạng thái giữa replica.
- Chưa tính quota ngày, nhiều chiều hạn mức hoặc SMTP concurrency.

Do đó, **không dùng local bucket trên nhiều replica để cam kết tuân thủ quota provider toàn cụm**. Nó là một thành phần minh họa, phù hợp cho unit test và những trường hợp đơn process với yêu cầu đơn giản.

### Vì sao không sleep trong tryAcquire?

~~~java
// Thiết kế không mong muốn khi có hàng nghìn job:
while (!limiter.tryAcquire(1).allowed()) {
    Thread.sleep(250);
}
~~~

Vòng lặp giữ thread gửi mail dù không được phép submit, làm giảm năng lực và gây shutdown chậm. Worker nên đặt job về `available_at`/`next_attempt_at` rồi xử lý job khác hoặc chờ event scheduler.

## 10. Unit test token bucket bằng đồng hồ giả

Kiểm tra rate limiter bằng cách `Thread.sleep(...)` trong test dễ tạo flaky test, đặc biệt khi CI bận. Với `LongSupplier ticker`, có thể mô phỏng thời gian.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;
import org.junit.jupiter.api.Test;

final class FakeTicker implements LongSupplier {
    private long nanos;

    @Override
    public long getAsLong() {
        return nanos;
    }

    void advanceMillis(long millis) {
        nanos += TimeUnit.MILLISECONDS.toNanos(millis);
    }
}

class LocalTokenBucketTest {
    @Test
    void grantsBurstThenWaitsForRefill() {
        FakeTicker ticker = new FakeTicker();
        LocalTokenBucket bucket =
                new LocalTokenBucket(2, 1.0, ticker);

        assertThat(bucket.tryAcquire(1).allowed()).isTrue();
        assertThat(bucket.tryAcquire(1).allowed()).isTrue();

        RateDecision denied = bucket.tryAcquire(1);
        assertThat(denied.allowed()).isFalse();
        assertThat(denied.retryAfter().toMillis())
                .isEqualTo(1000);

        ticker.advanceMillis(500);
        assertThat(bucket.tryAcquire(1).allowed()).isFalse();

        ticker.advanceMillis(500);
        assertThat(bucket.tryAcquire(1).allowed()).isTrue();
    }

    @Test
    void rejectsCostLargerThanMaximumBurst() {
        FakeTicker ticker = new FakeTicker();
        LocalTokenBucket bucket =
                new LocalTokenBucket(2, 1.0, ticker);

        org.assertj.core.api.Assertions
                .assertThatThrownBy(() -> bucket.tryAcquire(3))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Test này xác minh thuật toán trong một process; không chứng minh hệ thống đa replica không vượt quota. Distributed limiter cần integration test cạnh tranh đồng thời qua shared store.

## 11. Concurrency limiter: semaphore bên cạnh rate limiter

Ngay cả khi mail rate được giới hạn 4 message/giây, thời gian một SMTP submission có thể kéo dài nhiều giây. Để bảo vệ kết nối và thread, cần một giới hạn **in-flight** riêng:

~~~java
import java.util.concurrent.Semaphore;

public final class LocalSmtpConcurrencyGate {
    private final Semaphore slots;

    public LocalSmtpConcurrencyGate(int maxConcurrent) {
        if (maxConcurrent <= 0) {
            throw new IllegalArgumentException(
                    "maxConcurrent must be positive");
        }
        this.slots = new Semaphore(maxConcurrent);
    }

    public boolean tryEnter() {
        return slots.tryAcquire();
    }

    public void exit() {
        slots.release();
    }
}
~~~

Khi kết hợp:

~~~java
if (!concurrencyGate.tryEnter()) {
    // Worker/dispatcher chưa có slot, chưa gọi SMTP.
    return;
}

try {
    RateDecision rate = tokenBucket.tryAcquire(1);
    if (!rate.allowed()) {
        // Đặt job lại lịch, không gọi SMTP.
        return;
    }

    mailSender.send(message);
} finally {
    concurrencyGate.exit();
}
~~~

**Chỉ gọi `exit()` khi đã thật sự chiếm một slot thành công.** Trong ví dụ, nhánh không có slot return trước try/finally nên không release sai. Khi có exception từ `mailSender.send`, finally trả slot về.

### Giới hạn của local semaphore

Nếu có 5 replica và mỗi replica đặt 4 slot, toàn cụm có thể có **20 SMTP calls đồng thời**. Nếu provider giới hạn 4 connection chung cho toàn account, local semaphore chưa đủ. Cần điều phối **global concurrency**, hoặc đặt worker tập trung/cấu hình mỗi replica theo quota tổng và có cơ chế chống skew.

Ngoài ra, một SMTP submission có thể dùng connection reuse theo thư viện/provider; giới hạn số task đang chạy không phải lúc nào cũng đúng bằng số TCP connections. Cần đo thực tế.

## 12. Daily quota: giới hạn riêng với chu kỳ reset rõ ràng

Giả sử provider quy định tối đa 30.000 recipient trong mỗi chu kỳ 24 giờ. Hệ thống cần theo dõi:

- Đơn vị quota là message hay recipient.
- Chu kỳ là **calendar day** theo timezone provider hay **rolling 24h**.
- Việc gửi từ ứng dụng/credential khác có dùng cùng quota không.
- Provider có hạch toán cả submission bị reject hoặc retry không.
- Có API trả remaining quota hay reset time không.

Một cơ chế đếm theo ngày UTC có thể biểu diễn:

~~~text
quota:provider-A:account-prod:2026-11-12
usedRecipients = 18,420
maxRecipients  = 30,000
remaining      = 11,580
~~~

**Đừng lấy UTC calendar day nếu provider dùng rolling 24-hour window hoặc timezone khác.** Một fixed daily counter có thể cho gửi gần gấp đôi trong vài phút quanh nửa đêm dù provider chỉ cho giới hạn rolling 24h.

### Hành động khi gần cạn quota

Với email quan trọng:

1. Hạn chế hoặc tạm dừng lane không khẩn cấp (marketing/digest).
2. Duy trì một phần budget cho OTP và giao dịch nếu policy cho phép.
3. Giảm rate và tăng delay cho campaign.
4. Cảnh báo backlog/estimated completion time.
5. Nếu vượt ngưỡng, giữ job chưa gửi trong outbox tới kỳ quota mới.

Không nên retry dồn dập mỗi giây trong khi quota ngày còn bằng 0. Khi biết reset time, đặt `next_attempt_at` tương ứng; nếu không biết, dùng lịch poll thận trọng và đối chiếu dashboard/provider.

## 13. Vì sao giới hạn cục bộ không đủ khi chạy nhiều replica?

Spring Boot thường được triển khai dưới nhiều instance:

~~~text
Provider account shared quota: 12 messages/s

Replica A: local limit 12/s
Replica B: local limit 12/s
Replica C: local limit 12/s
Replica D: local limit 12/s
--------------------------------
Tổng có thể lên tới 48/s
~~~

Mỗi replica tự tin rằng mình đang tuân theo quota, nhưng **cả cụm** vẫn có thể gửi nhanh gấp bốn lần giới hạn account.

Một số giải pháp:

| Thiết kế | Ưu điểm | Điểm cần chú ý |
|---|---|---|
| Một dispatcher SMTP tập trung cho một quota account | Dễ quản lý tốc độ chung | Cần HA và xử lý backlog |
| Redis/distributed token bucket | Cấp permit nguyên tử giữa replica | Shared store, latency, consistency và failover |
| Database-backed quota reservation | Tận dụng database hiện có, transaction rõ | Row contention, throughput và locking |
| Broker với consumer có concurrency/rate giới hạn | Điều phối và phân phối job bền vững | Quota vẫn cần giới hạn chung khi tăng consumer |
| Chia quota tĩnh cho replica | Đơn giản khi số replica cố định | Autoscaling/skew/lãng phí quota |
| Provider-native rate control | Provider là nguồn enforcement cuối cùng | Thường không bảo đảm độ trễ/retry tối ưu |

**Redis không tự khiến rate limiter phân tán trở nên đúng.** Cần thiết kế phép trừ token nguyên tử, đồng hồ, TTL, scope key, khả năng restart, đánh đổi khi Redis mất kết nối và cách thử lại.

### Không dùng một khóa chung cho các quota độc lập

Nếu Provider A và Provider B có ngân sách riêng, không nên đưa cả hai vào một bucket duy nhất. Ngược lại, nếu hai SMTP credentials thực chất dùng chung quota organization, tạo bucket riêng cho mỗi credential có thể làm vượt quota chung.

Khóa rate limit phải phản ánh **đúng phạm vi provider áp dụng**, không dựa vào tên bean hoặc host nhìn thấy trong cấu hình.

## 14. Distributed token bucket: reservation phải nguyên tử

Giả sử hai worker cùng đọc trạng thái bucket:

~~~text
Bucket còn 1 token

Worker A đọc = 1
Worker B đọc = 1
Worker A gửi một email
Worker B gửi một email

Kết quả: tiêu thụ 2 dù chỉ còn 1 token.
~~~

Giải pháp không phải chỉ cache số token trong Redis. Cần **atomically read–refill–decrement–write** cho cùng bucket, ví dụ qua Redis Lua script hoặc transaction/compare-and-swap đúng semantics.

Pseudo-code:

~~~text
reserve(providerAccountKey, cost, now):
    ATOMIC {
        state = load(key)
        state.tokens = min(
            capacity,
            state.tokens + elapsed(now, state.updatedAt)*refillRate)

        if cost > capacity:
            return INVALID_COST

        if state.tokens < cost:
            persist(refilled state)
            return DENIED_WITH_RETRY_AFTER

        state.tokens -= cost
        state.updatedAt = now
        persist(state, with suitable TTL)
        return GRANTED
    }
~~~

Không thể thực hiện pseudo-code bằng một loạt `GET`, tính toán rồi `SET` rời rạc trong nhiều replica nếu không có khóa/đảm bảo atomicity. Trong thực tế cần chọn một thư viện distributed rate limiting đã được kiểm chứng hoặc triển khai script/transaction và test race rõ ràng.

### Những yếu tố phải xác định trong distributed implementation

- **Clock:** thời gian lấy từ client hay Redis server? Chênh lệch clock giữa replica có ảnh hưởng token refill không?
- **Atomicity:** trừ token và ghi state có cùng một atomic operation không?
- **TTL:** khi key hết hạn, bucket có khởi tạo đầy lại tạo burst trái policy không?
- **Persistence:** khi Redis restart hoặc failover, trạng thái quota có bị mất?
- **Network partition:** khi không lấy được permit, hệ thống dừng gửi hay gửi có giới hạn fallback?
- **Idempotency:** nếu client timeout sau khi Redis đã cấp permit, retry yêu cầu permit có tiêu tốn thêm token?
- **Scope:** tên khóa có chứa recipient/PII không và có khớp quota account/provider thực tế?
- **Capacity:** chi phí message nhiều recipient có thể lớn hơn token capacity không?

### Không lưu địa chỉ người nhận trong rate limiter key

Ví dụ:

~~~text
mail:limit:provider-A:account-orders
mail:limit:provider-A:sender-security
mail:limit:provider-A:tenant-42
~~~

Các định danh provider/account/tenant nên là ID nội bộ đã được kiểm soát. Không dùng `mail:limit:user@example.com` nếu không có lý do chính đáng; đây cũng là một nơi lưu dữ liệu nhạy cảm trong key của Redis/metrics/log.

## 15. Trường hợp đơn giản: chia quota tĩnh giữa replica

Nếu chưa có distributed store và số replica cố định, một giải pháp tạm là chia ngân sách:

~~~text
Account safe budget: 12/s
4 replicas
Mỗi replica: 3/s
~~~

Điều này có thể giữ tổng dưới quota **nếu thật sự chỉ có bốn replica, tất cả dùng đúng cấu hình và không có sender khác tiêu thụ cùng account**. Nhưng có vấn đề:

- Autoscaling lên 6 replica có thể làm tổng vượt giới hạn.
- Một replica không có job thì quota của nó bị lãng phí.
- Rolling deployment có thể tạm tồn tại thêm nhiều replica.
- Những ứng dụng khác dùng chung account vẫn không được tính.
- Provider có rolling window không khớp ranh giới local limiter.

Vì vậy chỉ dùng cách này khi giả định được kiểm soát rõ, kèm monitoring và biên độ. Với hệ thống mail quan trọng đa replica, **shared admission control** thường đáng tin hơn.

## 16. Database quota reservation: khi đã có outbox

Nếu toàn bộ job gửi mail đã được lưu trong cùng database, có thể quản lý quota cho provider/account bằng transaction. Ví dụ PostgreSQL cho **calendar window** đơn giản:

~~~sql
CREATE TABLE mail_quota_window (
    quota_key VARCHAR(150) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    capacity BIGINT NOT NULL CHECK (capacity > 0),
    reserved BIGINT NOT NULL DEFAULT 0
        CHECK (reserved >= 0),
    PRIMARY KEY (quota_key, window_start),
    CHECK (window_end > window_start)
);
~~~

Một worker muốn reserve 3 recipient trong window đã được xác định:

~~~sql
UPDATE mail_quota_window
SET reserved = reserved + :cost
WHERE quota_key = :quota_key
  AND window_start = :window_start
  AND reserved + :cost <= capacity
RETURNING reserved;
~~~

Nếu câu lệnh trả về một row, reservation thành công. Nếu không có row, budget của window đã hết hoặc dữ liệu window/key không tồn tại. **Không được tự coi “không có row” là còn quota.**

Với PostgreSQL, update cùng row được đồng bộ qua row-level locking nên điều kiện capacity được đánh giá lại khi transaction cạnh tranh. Tuy nhiên, cần đảm bảo:

- Window row được tạo an toàn, tránh race khởi tạo.
- Window chọn theo chính sách reset thật của provider.
- Cùng account/organization đều dùng cùng `quota_key`.
- Dự phòng trường hợp provider đã trừ quota ngoài ứng dụng.
- Câu lệnh reserve kết thúc transaction nhanh, không giữ lock trong lúc gửi SMTP.

Đây là **counter reservation theo cửa sổ cố định**, không phải triển khai rolling 24h chính xác. Nếu provider dùng rolling window, cần một cấu trúc/cơ chế phù hợp với rolling window hoặc dùng data từ provider.

### Tại sao không giữ transaction mở khi SMTP call?

~~~text
BEGIN TRANSACTION
  SELECT ... FOR UPDATE quota row
  JavaMailSender.send(...)  ← có thể block nhiều giây
  UPDATE ...
COMMIT
~~~

Thiết kế này giữ database lock và connection trong suốt thao tác mạng; throughput có thể giảm mạnh và tạo contention. Nên **reserve quota nhanh trong transaction**, commit, rồi gửi SMTP ở ngoài transaction.

Nếu worker chết sau khi reserve nhưng trước khi gửi, một phần quota bị “mất” ở bộ đếm. Đây là lựa chọn bảo thủ giúp giảm rủi ro vượt quota; có thể thiết kế reservation lease/reconciliation nếu cần tận dụng tối đa, nhưng không được hoàn quota khi có khả năng server đã chấp nhận message.

## 17. Nhiều giới hạn cùng lúc: tránh cấp phát dở dang

Giả sử một message phải vượt qua hai quota:

- Account còn 10 token.
- Sender identity đã hết quota.

Nếu code thực hiện:

~~~text
reserve account token  → thành công
reserve sender token   → thất bại
~~~

thì account đã bị trừ dù chưa gửi. Nếu caller liên tục retry, account budget có thể bị mất mà không có mail đi ra.

Một số cách xử lý:

1. **Atomic multi-key reservation:** nếu các key trong cùng store và có thể dùng transaction/script đúng cách, kiểm tra rồi trừ **tất cả hoặc không cái nào**.
2. **Coordinated reservation:** quản lý reservation state với transaction/lease và rollback có kiểm soát cho trường hợp chắc chắn chưa gửi.
3. **Conservative accounting:** chấp nhận tiêu tốn một ít quota ảo để tránh vi phạm quota; hạn chế retry quá thường xuyên.
4. **Dispatcher điều phối tuần tự:** nếu throughput vừa phải, một coordinator duy nhất có thể dễ quản lý hơn.

Trong thiết kế dùng Redis Cluster, multi-key Lua script có thể cần các key cùng hash slot; không giả định mọi key tùy ý đều cập nhật nguyên tử trên cluster. Với DB có nhiều row counter, phải khóa theo thứ tự nhất quán để giảm deadlock và ghi các reservation trong một transaction.

**Không tự viết một chuỗi `tryAcquire()` cho ba bucket rồi gọi SMTP mà không xác định hành vi khi bucket thứ hai/thứ ba từ chối.**

## 18. Fail closed hay fail open khi bộ giới hạn bị lỗi?

Nếu Redis/quota service không hoạt động, dispatcher có vài lựa chọn:

| Chính sách | Hành vi | Rủi ro/lợi ích |
|---|---|---|
| Fail closed | Không submit mail, giữ job trong outbox | Không vượt quota do mất kiểm soát; backlog tăng |
| Fail open | Vẫn gửi không có permit | Giữ throughput nhưng có thể vượt quota/khóa account |
| Bounded emergency fallback | Chỉ gửi một nhóm quan trọng ở tốc độ rất thấp | Cần budget và quy trình điều hành rõ ràng |
| Chuyển sang provider dự phòng | Chỉ khi route được phê duyệt | Cần hạn mức, sender auth và quota riêng |

Với mail marketing/batch, fail closed thường dễ kiểm soát hơn. Với OTP hoặc thông báo bảo mật, có thể cân nhắc **một đường dự phòng đã thiết kế trước**, nhưng không có lý do để bỏ qua vô hạn mọi rate limit khi store gặp lỗi.

Nếu chọn fallback, phải biết giới hạn **toàn cụm**, không chỉ dùng local limiter 1/s trên 100 replica rồi kết luận tổng an toàn. Ghi audit về thời điểm bật/tắt chế độ, người phê duyệt, số job được gửi và quota dự phòng tiêu thụ.

### Hệ thống điều phối quota cũng cần được giám sát

Một limiter hoạt động sai có thể không gây lỗi SMTP ngay nhưng làm job không bao giờ được gửi. Cần metric:

- Permit granted / denied.
- Latency lấy permit.
- Số lỗi kết nối limiter store.
- Reservation timeout.
- Tuổi job bị trì hoãn vì quota.
- Tỷ lệ token/budget còn lại nếu biết.

Không nhầm “không có SMTP errors” với “hệ thống vận hành tốt” khi backlog đang tăng vì limiter không cấp phép.

## 19. Tách ý định gửi bền vững khỏi việc được phép gửi lúc này

Một rate limiter không phải hàng đợi. Khi bucket hết token, yêu cầu gửi cần **được lưu ở nơi bền vững** nếu email không được phép mất.

Một kiến trúc phù hợp với Spring:

~~~mermaid
flowchart TD
    A[Application use case] --> B[Database transaction]
    B --> C[Business state + Mail outbox]
    C --> D[Commit]
    D --> E[Outbox dispatcher]
    E --> F{Provider quota available?}
    F -- No --> G[Reschedule available_at]
    G --> E
    F -- Yes --> H{Concurrency slot available?}
    H -- No --> G
    H -- Yes --> I[SMTP submission]
    I --> J{Outcome}
    J -- Accepted --> K[Mark SUBMITTED]
    J -- Temporary rejection --> L[Backoff + RETRY]
    J -- Permanent rejection --> M[DEAD / review]
    J -- Unknown --> N[UNKNOWN + policy]
    L --> E
~~~

Điểm cần lưu ý:

- **Outbox** bảo đảm ý định gửi sống qua restart khi được ghi trong transaction phù hợp.
- **Rate limiter** quyết định có được bắt đầu một lần submit tại thời điểm hiện tại không.
- **Concurrency limiter** kiểm soát số thao tác SMTP đang diễn ra.
- **Retry policy** xử lý kết quả, không mặc định thử lại vô hạn.
- **Database state** cho biết job đang chờ quota, đang retry lỗi SMTP hay đã submitted.

Các cơ chế này giải quyết các vấn đề khác nhau; `@Async` hoặc một thread pool lớn không thay thế chúng.

### Mẫu trạng thái job

~~~text
PENDING
   |
   +-- quota chưa đủ ----------> WAITING_RATE_LIMIT
   |                                 |
   |                                 v
   |                              PENDING
   |
   +-- claim + permit ----------> PROCESSING
                                     |
                  +------------------+----------------+
                  |                  |                |
                  v                  v                v
              SUBMITTED           RETRY              UNKNOWN
                                     |
                                     v
                                   PENDING
~~~

`WAITING_RATE_LIMIT` là tên trạng thái gợi ý, không phải enum có sẵn của Spring Mail. Hệ thống đơn giản có thể giữ `PENDING` với `available_at` trong tương lai thay vì thêm trạng thái mới; quan trọng là worker không coi “chưa đủ token” thành lỗi SMTP đã được thử.

## 20. Claim outbox và giữ kết nối database ngắn

Một outbox worker thường có vòng xử lý:

1. Xác định provider/account và năng lực còn lại.
2. Claim một batch nhỏ job đã đến hạn, với lease để tránh nhiều worker claim cùng một job.
3. Tính cost theo message/recipient và policies có liên quan.
4. Lấy quota permit và concurrency slot.
5. Gửi SMTP **ngoài transaction DB**.
6. Lưu outcome hoặc lịch retry trong transaction ngắn.

Ví dụ SQL claim batch PostgreSQL:

~~~sql
WITH ready AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND available_at <= CURRENT_TIMESTAMP
      AND provider_id = :provider_id
    ORDER BY priority DESC, available_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS job
SET status = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP,
    claim_token = :claim_token,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds'
FROM ready
WHERE job.id = ready.id
RETURNING job.id, job.provider_id, job.recipient_count;
~~~

Đây là ví dụ SQL thiết kế, giả định bảng `mail_outbox` đã có những cột tương ứng. `SKIP LOCKED` giúp nhiều worker không chờ cùng các row đã bị khóa, nhưng không tự bảo đảm FIFO tuyệt đối. `claim_token` phải đủ khả năng phân biệt lượt claim, và các state update sau gửi cần kiểm tra token để worker cũ không ghi đè worker mới.

**Đừng claim 50.000 job rồi submit tất cả vào queue `ThreadPoolTaskExecutor`.** Với giới hạn thực tế 5 mail/giây, việc giữ hàng nghìn job đã claim trong RAM gây lease expiry, duplicate work và khó kiểm soát backpressure.

### Khi bucket không cấp phép

Nếu có `RateDecision.denied(retryAfter)`:

- Đưa job về trạng thái chờ hoặc cập nhật `available_at`.
- Giải phóng claim/lease theo transaction ngắn.
- Không tăng “số SMTP attempt” vì chưa gọi SMTP.
- Có thể tăng metric `rate_limit_deferral_total`.
- Tránh worker lặp lại claim cùng job trong cùng mili giây.

Nếu một provider có quota ngày và hạn mức giây, `available_at` nên phản ánh thời điểm sớm nhất mà **tất cả điều kiện được thỏa mãn**, không chỉ bucket refill nhanh nhất.

## 21. Spring Boot cấu hình policy theo provider

Đặt policy trong namespace ứng dụng thay vì hardcode rải rác:

~~~yaml
app:
  mail:
    limits:
      primary:
        bucket-capacity: 10
        refill-tokens-per-second: 4.0
        max-concurrent: 3
        max-recipients-per-message: 20
        safe-daily-recipient-budget: 15000
      backup:
        bucket-capacity: 4
        refill-tokens-per-second: 1.5
        max-concurrent: 2
        max-recipients-per-message: 10
        safe-daily-recipient-budget: 3000
~~~

Các số này **chỉ để minh họa**; không phải quota chính thức của provider cụ thể. `app.mail.limits` là namespace **do ứng dụng tự định nghĩa**; Spring Boot sẽ không tự thực thi quota chỉ vì file YAML có những trường này.

Ví dụ bind kiểu record:

~~~java
import org.springframework.boot.context.properties
        .ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.limits")
public record MailLimitProperties(
        ProviderLimit primary,
        ProviderLimit backup) {

    public record ProviderLimit(
            int bucketCapacity,
            double refillTokensPerSecond,
            int maxConcurrent,
            int maxRecipientsPerMessage,
            long safeDailyRecipientBudget) {
    }
}
~~~

Đăng ký bằng `@EnableConfigurationProperties`:

~~~java
import org.springframework.boot.context.properties
        .EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MailLimitProperties.class)
public class MailLimitConfiguration {
}
~~~

Tạo local rate limiter minh họa theo hai provider:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LocalRateGateConfiguration {

    @Bean("primaryRateGate")
    LocalTokenBucket primaryRateGate(
            MailLimitProperties config) {
        var policy = config.primary();
        return new LocalTokenBucket(
                policy.bucketCapacity(),
                policy.refillTokensPerSecond(),
                System::nanoTime);
    }

    @Bean("backupRateGate")
    LocalTokenBucket backupRateGate(
            MailLimitProperties config) {
        var policy = config.backup();
        return new LocalTokenBucket(
                policy.bucketCapacity(),
                policy.refillTokensPerSecond(),
                System::nanoTime);
    }
}
~~~

**Cảnh báo:** hai bean trên là **local JVM limiter** để minh họa dependency injection. Với nhiều replica cùng dùng một provider account, phải thay bằng shared rate gate hoặc dispatcher tập trung. `safeDailyRecipientBudget` và `maxConcurrent` chưa được thực thi bởi những bean đó; cần thêm bộ đếm quota ngày và concurrency gate tương ứng.

### Validate cấu hình trước khi khởi động

Không nên khởi động service với:

- `bucketCapacity <= 0`.
- `refillTokensPerSecond <= 0`.
- `maxConcurrent <= 0`.
- `maxRecipientsPerMessage <= 0`.
- Budget ngày âm hoặc bằng 0 ngoài trường hợp chủ đích tắt lane.
- Cost lớn hơn burst capacity nhưng không có cơ chế chia job.

Có thể dùng Jakarta Bean Validation với `@Validated` và `@Min`/`@Positive`, cùng kiểm tra chéo giữa các tham số. Cấu hình là **điều kiện an toàn vận hành**; giá trị không hợp lệ nên fail fast thay vì gây job chờ vô hạn ở runtime.

### Thay đổi policy khi đang chạy

Khi operator giảm rate từ 4 xuống 2 token/giây, các replica phải nhận cấu hình mới một cách nhất quán. Nếu local bucket khởi tạo một lần tại startup, sửa YAML không làm bean tự đổi ngay trừ khi ứng dụng có cơ chế reload rõ ràng. Distributed limiter cũng phải có policy version để tránh một số worker dùng capacity mới, số khác dùng capacity cũ.

Không nên cho endpoint public tự chỉnh provider limit. Việc thay quota cần authorization, audit và nguyên tắc không vượt hợp đồng provider.

## 22. Sử dụng rate gate từ service/dispatcher

Một abstraction giúp tách thuật toán cụ thể khỏi mail submission:

~~~java
public interface ProviderRateGate {
    RateDecision reserve(
            String providerAccountId, int recipientCost);
}

public interface MailJobStore {
    void deferForQuota(String jobId, java.time.Duration delay);
    void markSubmitted(String jobId);
    void recordFailure(String jobId, MailDispatchFailure failure);
}
~~~

Các interface và `MailDispatchFailure` là kiểu ứng dụng tự định nghĩa. Một coordinator ở mức khái niệm:

~~~java
import org.springframework.mail.javamail.JavaMailSender;

public final class MailDispatchCoordinator {
    private final ProviderRateGate rateGate;
    private final MailJobStore jobStore;
    private final JavaMailSender mailSender;

    public MailDispatchCoordinator(
            ProviderRateGate rateGate,
            MailJobStore jobStore,
            JavaMailSender mailSender) {
        this.rateGate = rateGate;
        this.jobStore = jobStore;
        this.mailSender = mailSender;
    }

    public void dispatch(ClaimedMailJob job) {
        RateDecision permit = rateGate.reserve(
                job.providerAccountId(),
                job.recipientCost());

        if (!permit.allowed()) {
            jobStore.deferForQuota(
                    job.id(), permit.retryAfter());
            return;
        }

        try {
            mailSender.send(job.mimeMessage());
            jobStore.markSubmitted(job.id());
        } catch (org.springframework.mail.MailException ex) {
            // Phân loại lỗi; không log raw exception/recipient.
            jobStore.recordFailure(
                    job.id(), MailDispatchFailure.from(ex));
        }
    }
}
~~~

`ClaimedMailJob` và `MailDispatchFailure.from` là abstraction minh họa. Code tập trung thể hiện **vị trí lấy permit trước SMTP**. Một triển khai production phải thêm:

- Concurrency gate và cách chọn JavaMailSender theo provider/account.
- Kiểm tra ownership/claim token trong các state transitions.
- Transaction boundaries cho cập nhật trạng thái job.
- Xử lý exception khi **rate gate hoặc job store** lỗi.
- Logic xử lý outcome không chắc chắn; không giả định mọi `MailException` đều là thất bại an toàn để retry.
- Chặn job đã unsubscribe hoặc hết hạn nghiệp vụ trước khi gửi.
- Bảo đảm state vẫn đúng nếu process crash sau SMTP acceptance.

### Không làm việc SMTP trong @Scheduled method

Một scheduler nên chủ yếu **đánh thức dispatcher**:

~~~java
@Scheduled(fixedDelayString = "${app.mail.poll-delay-ms:1000}")
public void wakeUpDispatcher() {
    dispatcher.dispatchReadyBatch();
}
~~~

Nếu method scheduled tự gửi hàng nghìn email đồng bộ, nó có thể chiếm scheduler thread và làm các lịch khác trễ. Các worker thực thi SMTP nên có executor riêng và queue/concurrency hữu hạn. Scheduler không cần claim job khi rate gate đã biết sẽ từ chối toàn bộ traffic trong một khoảng.

## 23. Điều phối nhiều chiều: tốc độ, quota và concurrency

Một lần gửi có thể phải vượt qua những cổng sau:

~~~text
Mail job
   |
   v
Check business eligibility / suppression
   |
   v
Check per-message recipient and size limits
   |
   v
Reserve provider-account daily budget
   |
   v
Reserve provider-account rate token
   |
   v
Reserve sender-specific rate token
   |
   v
Acquire SMTP concurrency slot
   |
   v
JavaMailSender.send(...)
   |
   v
Save outcome, release concurrency slot
~~~

Đây là sơ đồ logic. **Không nhất thiết thực hiện từng bước bằng các phép trừ độc lập** như một chuỗi không thể rollback. Hãy xác định một cơ chế coordinated reservation/atomic admission đúng cho quota thực tế. Nếu quota account đã được reserve nhưng sender rate từ chối, cần xử lý reservation còn treo một cách đã thiết kế, hoặc dùng một operation nguyên tử.

Thứ tự cụ thể phụ thuộc chi phí:

- Kiểm tra business/recipient hợp lệ trước, tránh tiêu tốn quota cho job đã hủy.
- Kiểm tra những điều kiện không thay đổi hoặc rẻ trước.
- Với nhiều quota, ưu tiên quyết định admission nguyên tử nếu có thể.
- Không giữ DB transaction/lock hoặc thread slot qua một khoảng chờ quota dài.
- Chỉ gọi SMTP khi đủ điều kiện và có slot thực thi.

### Lệnh gọi một message nhưng nhiều recipient

Nếu message có 10 recipient, cần trừ 10 đơn vị **ở limiter theo recipient**, nhưng chỉ trừ 1 đơn vị ở limiter theo message. Một cost model duy nhất áp cho mọi quota có thể sai.

~~~text
messagesPerSecond bucket:    cost = 1
recipientsPerSecond bucket:  cost = 10
recipientsPerDay budget:    cost = 10
connectionConcurrency:      cost = 1 slot
~~~

Mỗi quota cần đơn vị rõ ràng, được ghi trong tên trường/cấu hình/metric. Tránh một tham số mơ hồ `limit=100` mà không biết 100 thư hay 100 người nhận.

## 24. Fairness: đừng để chiến dịch chiếm hết quota của OTP

Một account có thể xử lý nhiều lane:

~~~text
HIGH:  security / OTP
MED:   order receipts / account notifications
LOW:   newsletter / marketing digest
~~~

Nếu tất cả job vào một queue FIFO duy nhất, 100.000 newsletter được enqueue trước có thể khiến OTP mới đến phải chờ rất lâu dù provider vẫn cho gửi một phần.

Một số giải pháp:

| Chính sách | Lợi ích | Cần chú ý |
|---|---|---|
| Strict priority | Email quan trọng được ưu tiên | Lane thấp có thể starvation |
| Reserved capacity | Chừa một phần quota cho security | Lãng phí nếu lane ưu tiên không có việc |
| Weighted fair queueing | Phân bổ năng lực giữa các lane | Phức tạp hơn FIFO |
| Separate provider accounts | Cách ly quota mạnh khi thực sự độc lập | Tăng quản lý và có thể vẫn bị quota chung |
| Time-based campaign throttling | Marketing gửi trải đều | Phải đảm bảo thời hạn chiến dịch |

Ví dụ một budget minh họa:

~~~text
Safe account rate = 10 message/s

Security lane   -> reserve 3/s khi cần
Transaction     -> target tối đa 5/s
Marketing       -> sử dụng capacity còn lại
~~~

Đừng coi các giá trị này là quota thật. Khi thiết kế reservation, cần xác định rõ slot không dùng có được “mượn” bởi lane khác không và có bị thu hồi khi email ưu tiên đến không.

### Fairness giữa tenant

Nếu 50 khách hàng tổ chức dùng chung provider account, một tenant có batch lớn có thể đẩy backlog của tenant khác. Có thể bổ sung quota mềm theo tenant, weighted round robin hoặc token bucket riêng bên dưới quota toàn account.

**Tenant quota không được vượt account quota chung.** Một bộ giới hạn theo tenant chỉ phân chia công bằng quota có sẵn, không tạo thêm năng lực của provider.

## 25. Provider throttling biểu hiện qua SMTP như thế nào?

Khác với một HTTP email API, SMTP trả mã phản hồi theo các bước như kết nối, `MAIL FROM`, `RCPT TO` và `DATA`. Một số mã thường gặp:

| SMTP reply | Ý nghĩa khái quát | Hướng xử lý |
|---|---|---|
| `421` | Dịch vụ tạm không sẵn sàng/đóng kết nối | Thường cần trì hoãn và thử lại theo policy |
| `450` | Thao tác mailbox tạm không khả dụng | Xem nguyên nhân, trì hoãn hợp lý |
| `451` | Lỗi cục bộ tạm thời | Retry có backoff nếu outcome rõ ràng |
| `452` | Không đủ tài nguyên/hạn chế tạm thời | Giảm tốc hoặc trì hoãn |
| `454` | Một số điều kiện xác thực/TLS tạm thời | Kiểm tra nguyên nhân cụ thể |
| `4.7.x` enhanced status | Thường liên quan security/policy hoặc rate/tạm hoãn tùy provider | Phải đọc tài liệu và ngữ cảnh provider |
| `5xx` | Lỗi không được chấp nhận theo semantics của reply | Thường cần sửa nguyên nhân, không retry mù |

**Không phải mọi phản hồi `4xx` đều có nghĩa “đã vượt rate limit”.** Provider có thể tạm từ chối vì mailbox, anti-abuse, greylisting, DNS hoặc sự cố nội bộ. Ngược lại, một provider có thể báo quota/rate bằng error code riêng trong SMTP response.

Phân loại chính xác dựa trên:

1. SMTP reply code.
2. Enhanced status code nếu có.
3. Phase giao thức lúc nhận phản hồi.
4. Quy tắc của provider/account đang dùng.
5. Sự chắc chắn về kết quả nộp message.

Không nên dựa duy nhất vào `exception.getMessage().contains("rate limit")` vì message có thể đổi ngôn ngữ/format hoặc chứa địa chỉ người nhận và dữ liệu nhạy cảm.

### SMTP throttling và HTTP 429 không phải một

Nếu dùng **HTTP email API**, provider có thể trả:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{"code":"RATE_LIMIT_EXCEEDED"}
~~~

`Retry-After` là một HTTP header có thể chứa số giây hoặc một HTTP-date theo quy tắc HTTP. Nếu provider dùng API HTTP, hãy tôn trọng thông tin này theo tài liệu của họ.

**Không có một header `Retry-After` chuẩn phổ quát trong giao thức SMTP giống HTTP.** Với SMTP, thời điểm thử lại thường được xác định từ reply/giới hạn provider, chính sách backoff và thời điểm quota reset do provider công bố.

### Một reply sau RCPT TO khác với reply sau DATA

Trước khi SMTP client gửi body DATA, server có thể từ chối một recipient hoặc toàn bộ transaction. Sau khi server nhận body và trước khi client nhận được reply cuối, connection có thể rơi vào trạng thái **không rõ server đã accepted hay chưa**.

Do đó cần phân biệt:

~~~text
RATE_LIMIT_REJECTED_BEFORE_ACCEPTANCE
        -> Có bằng chứng không accepted, có thể lịch retry

SMTP_ACCEPTED
        -> Không retry như chưa gửi

SMTP_OUTCOME_UNKNOWN
        -> Có nguy cơ duplicate nếu gửi lại
~~~

Giới hạn tốc độ không làm SMTP trở thành exactly-once. Xử lý retry và duplicate vẫn cần idempotency/correlation theo khả năng của luồng nghiệp vụ, cùng chính sách chấp nhận rủi ro.

## 26. Cách phân loại lỗi trong Spring Mail

Spring Mail có các exception như `MailSendException`, `MailAuthenticationException` và `MailPreparationException`. Một lỗi gửi SMTP có thể bao bọc exception của Jakarta Mail hoặc SMTP transport provider.

Một bảng gợi ý:

| Loại lỗi | Rate limiter có phải nguyên nhân? | Cách phản ứng |
|---|---|---|
| Invalid email address | Không | Validation, không retry như throttling |
| MIME preparation failed | Không | Sửa dữ liệu/template/resource |
| SMTP authentication rejected | Thường không | Kiểm tra credential/OAuth/policy |
| SMTP temporary throttle có bằng chứng | Có thể | Trì hoãn, giảm rate và retry |
| Network connect timeout trước khi gửi | Không chắc | Kiểm tra availability, backoff |
| Connection lost sau DATA | Outcome không chắc | Trạng thái UNKNOWN, chính sách duplicate |
| Provider daily quota exhausted | Có | Chờ quota reset hoặc route khác đã được duyệt |
| HTTP 429 từ email API | Có thể | Tôn trọng Retry-After và quota key |
| SMTP permanent sender not permitted | Không | Sửa sender permission, không retry vô hạn |

Vì `MailSendException` có thể đại diện cho nhiều message/cause, **không nên chỉ catch loại exception này rồi suy ra tất cả message bị throttled**.

Ví dụ một classifier chỉ xuất mã nội bộ:

~~~java
public enum SubmissionFailureKind {
    RATE_THROTTLED,
    TEMPORARY_TRANSPORT_FAILURE,
    AUTHENTICATION_FAILURE,
    INVALID_MESSAGE,
    PERMANENT_REJECTION,
    UNKNOWN_OUTCOME
}
~~~

Đây là enum **do ứng dụng định nghĩa**. Bộ phân loại cần dùng cause chain/SMTP status/phase có thể quan sát, ưu tiên dựa vào type và code thay vì text chứa recipient. Nếu không đủ bằng chứng, phân loại `UNKNOWN_OUTCOME` hoặc một mã lỗi chưa xác định, không tự khẳng định server không nhận message.

### Log an toàn khi provider echo recipient

Một SMTP error có thể chứa:

~~~text
451 4.7.0 Temporarily throttled for <person@example.test>
~~~

Không log raw exception message hoặc raw SMTP transcript nếu chúng chứa email, token, subject hoặc nội dung. Log:

~~~text
event=mail_submission_failed
jobId=mail-job-001
provider=PRIMARY
failureKind=RATE_THROTTLED
smtpStatusClass=4xx
attempt=3
~~~

Điều này giúp giám sát tốc độ mà không biến hệ thống log thành một bản sao dữ liệu người nhận.

## 27. Retry có exponential backoff và jitter

Khi nhiều worker cùng bị provider từ chối vì throttling, nếu tất cả thử lại đúng sau 1 giây, chúng tạo ra một “làn sóng” mới:

~~~text
00:00  1000 jobs bị throttle
00:01  cả 1000 retry đồng thời
00:02  cả 1000 retry đồng thời
...
~~~

**Exponential backoff** làm khoảng chờ tăng theo số lần thử:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Trong đó:

- `d0`: khoảng chờ cơ bản.
- `n`: số lần thất bại liên tiếp hoặc số retry theo chính sách.
- `dmax`: trần delay.

Thêm **jitter** để các worker không thức dậy đồng loạt:

\[
d_{\mathrm{jitter}} \sim U(0, d_n)
\]

Đây là *full jitter*: chọn ngẫu nhiên trong khoảng 0 đến delay trần cho lần thử đó. Một hệ thống cần có **minimum retry delay** nếu không muốn một số job được thử lại gần như ngay lập tức.

### Ví dụ Java tạo retry delay

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryBackoff {
    private final long baseMillis;
    private final long maxMillis;

    public RetryBackoff(
            Duration baseDelay,
            Duration maxDelay) {
        this.baseMillis = baseDelay.toMillis();
        this.maxMillis = maxDelay.toMillis();
        if (baseMillis <= 0 || maxMillis < baseMillis) {
            throw new IllegalArgumentException(
                    "Invalid retry delay bounds");
        }
    }

    public Duration forFailureNumber(int failureNumber) {
        if (failureNumber < 1) {
            throw new IllegalArgumentException(
                    "Failure number starts at 1");
        }

        long cap = baseMillis;
        for (int i = 1; i < failureNumber; i++) {
            if (cap >= maxMillis) {
                break;
            }
            cap = cap > maxMillis / 2
                    ? maxMillis
                    : cap * 2;
        }

        long randomized = ThreadLocalRandom.current()
                .nextLong(cap + 1);
        return Duration.ofMillis(randomized);
    }
}
~~~

Trong môi trường thực tế có thể cần:

- Minimum delay để tránh retry ngay trong cùng sát-na.
- Tôn trọng `Retry-After` hoặc quota reset time nếu **HTTP API/provider** công bố.
- Max attempts, deadline và tuổi tối đa của job.
- Tách lỗi tạm thời khỏi lỗi permanent và UNKNOWN.
- Giữ `next_attempt_at` trong database để sống qua restart.
- Cảnh báo khi backlog tuổi cao hoặc job đi vào dead-letter.

### Retry delay và rate gate phải phối hợp

Khi job đến hạn retry, worker **vẫn phải xin permit** theo provider hiện tại. Backoff không thay thế rate limiting, vì nhiều job khác có thể đang tiêu thụ quota. Ngược lại, một permit không chứng minh lỗi trước đó đã hết.

Khi server công bố một thời điểm retry tối thiểu đáng tin (ví dụ HTTP `Retry-After`), lịch retry thường không nên sớm hơn thời điểm đó. Đồng thời không được thử lại khi daily budget đã cạn và chưa reset.

## 28. Adaptive rate control khi provider liên tục throttle

Một rate limit tĩnh đặt từ tài liệu provider có thể vẫn quá cao trong giai đoạn danh tiếng người gửi giảm hoặc provider đang có sự cố. Một số hệ thống bổ sung cơ chế **adaptive throttling**:

~~~text
Nếu gửi ổn định trong khoảng quan sát:
    tăng rate chậm, không vượt safe configured cap

Nếu tỷ lệ throttle tăng:
    giảm rate tương đối nhanh

Nếu provider quota ngày gần hết:
    hạn chế lane không ưu tiên
~~~

Một biến thể đơn giản là **AIMD** (*additive increase, multiplicative decrease*):

\[
r_{t+1} =
\begin{cases}
  \max(r_{\min}, \beta r_t),
    & \text{khi provider throttle đáng kể} \\
  \min(r_{\max}, r_t + \alpha),
    & \text{khi ổn định và còn budget}
\end{cases}
\]

Trong đó `0 < β < 1` là hệ số giảm, `α > 0` là bước tăng nhỏ.

**Adaptive controller không được vượt giới hạn hard cap của provider** và không được biến một đợt network outage thành việc tăng tốc sau khi khôi phục. Cần quan sát trên cửa sổ đủ dài để tránh dao động liên tục.

### Không tăng rate khi hệ thống không có tải

Nếu không có job nào trong queue, việc không thấy throttling không có nghĩa provider đủ sức gửi nhanh hơn. Adaptive policy nên dựa vào mẫu request thực, success rate và độ trễ, không tăng không giới hạn theo những phút không gửi email.

### Backpressure và circuit breaker khác nhau

- **Rate limiter:** giới hạn mức sử dụng khi provider hoạt động.
- **Backpressure:** ngừng nhận/dispatch thêm công việc khi năng lực xử lý không theo kịp.
- **Circuit breaker:** giảm hoặc chặn call mới khi dependency đang lỗi liên tục.
- **Retry/backoff:** đặt lịch thử lại những lỗi có khả năng phục hồi.

Một email provider có outage lớn có thể cần circuit breaker và giữ job trong outbox, không chỉ giảm rate từ 10 xuống 8 mail/giây. Ngược lại, khi provider hoạt động tốt nhưng quota thấp, circuit breaker không thay thế token bucket.

## 29. Multi-provider routing và failover

Nếu tổ chức cho phép dùng nhiều provider:

~~~text
Outbox
    |
    v
Routing policy
    |
    +-- Primary SMTP
    |      +-- own quota/rate/concurrency
    |
    +-- Backup SMTP
           +-- own quota/rate/concurrency
~~~

Tuy nhiên failover cần xét:

1. Sender domain và `From` đã được provider B xác minh chưa?
2. DKIM/SPF/DMARC có tương thích tuyến gửi mới?
3. Có quota dự phòng riêng theo hợp đồng?
4. Có đang vi phạm một quota organization/provider tổng hợp?
5. Bounced/complaints/feedback được nhận về hệ thống nào?
6. Job có ở trạng thái SMTP **UNKNOWN** ở provider A không?
7. Việc gửi trùng từ hai provider có thể gây hậu quả nghiệp vụ gì?

Không tự động chuyển ngay một job timeout sau DATA sang provider B khi chưa xác định khả năng provider A đã accepted. Đây là một nguyên nhân phổ biến tạo email trùng ngoài ý muốn.

### Failover không phải cách né giới hạn của provider

Nếu nhà cung cấp tạm chặn vì hành vi giống spam, việc tự động quay vòng qua nhiều tài khoản/provider để tiếp tục bắn mail có thể làm vấn đề nghiêm trọng hơn và vi phạm chính sách dịch vụ. Tách tuyến cho **khả dụng và mục đích hợp lệ** cần được thiết kế, phê duyệt và giám sát rõ ràng.

## 30. Monitoring: đo cả số thư gửi và số thư bị chặn vì quota

Một dashboard chỉ hiển thị `mail_sent_total` chưa đủ. Khi limiter hoạt động tốt, **SMTP errors có thể giảm** nhưng backlog lại tăng nếu nhu cầu vượt khả năng provider. Cần quan sát cả admission, queue và thực tế submission.

| Metric | Ý nghĩa | Khi bất thường |
|---|---|---|
| `mail_rate_limit_permit_total` | Số permit được cấp | Có thể quá thấp hoặc quá cao so với kỳ vọng |
| `mail_rate_limit_denied_total` | Số lần bị limiter trì hoãn | Tăng kéo dài khi backlog lớn |
| `mail_provider_throttle_total` | Số lần provider báo throttling | Tăng ngay cả khi có limiter nội bộ |
| `mail_quota_remaining` | Phần budget còn lại theo account | Gần 0 trước thời điểm reset |
| `mail_outbox_pending` | Số job chờ gửi | Tăng liên tục, vượt năng lực |
| `mail_outbox_oldest_age_seconds` | Tuổi job lâu nhất còn chờ | Vượt SLA theo loại email |
| `mail_submission_duration_seconds` | Độ trễ gửi | p95/p99 tăng |
| `mail_executor_active_threads` | Số worker đang bận | Thường xuyên đạt trần |
| `mail_executor_queue_size` | Job đang xếp trong RAM | Tăng hoặc chạm capacity |
| `mail_rate_gate_duration_seconds` | Thời gian lấy permit | Shared limiter/store chậm |
| `mail_rate_gate_errors_total` | Lỗi lấy quota permit | Redis/DB điều phối sự cố |
| `mail_job_retry_total` | Số lần job đi vào retry | Tăng do SMTP lỗi |
| `mail_job_unknown_total` | Outcome không chắc chắn | Nguy cơ duplicate |
| `mail_submission_accepted_total` | Provider accepted | Throughput thực |

Một cách phân chia label có kiểm soát:

~~~text
provider_id=PRIMARY
account_id=ORDERS
mail_lane=TRANSACTIONAL
result=PERMIT_DENIED
reason=RATE_WINDOW
~~~

Không nên có:

~~~text
recipient=user@example.net
subject="Your order #12345"
jobId=mail-unique-per-message
~~~

Địa chỉ email là PII; subject có thể chứa thông tin khách hàng; jobId có cardinality rất cao. Các field này thuộc hệ thống tra cứu job có quyền hoặc log an toàn theo chính sách, **không phải metric label**.

### Ví dụ Micrometer: đếm lần chạm rate limiter

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class MailLimiterMetrics {
    private final MeterRegistry metrics;

    public MailLimiterMetrics(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    public void decision(
            String providerId,
            String lane,
            boolean allowed) {
        metrics.counter(
                "mail_rate_limit_decisions",
                "provider", providerId,
                "lane", lane,
                "result", allowed ? "granted" : "denied")
                .increment();
    }
}
~~~

`providerId` và `lane` phải là các giá trị **thuộc danh sách cố định**. Không cho caller truyền tùy ý email, dynamic token hoặc tên chiến dịch riêng lẻ vào tag.

## 31. Alert và runbook khi provider gần hết quota

Các alert hữu ích thường gắn với ảnh hưởng thực tế:

- **Rate-limit denials tăng**, đồng thời backlog age vượt mục tiêu của lane.
- **Provider throttle tăng** sau khi triển khai thay đổi cấu hình hoặc tăng replica.
- **Daily budget còn thấp** nhưng vẫn còn nhiều giờ đến chu kỳ reset.
- **OTP backlog tăng** dù marketing đang tiêu thụ nhiều quota.
- **Rate gate store bị lỗi** làm toàn bộ worker dừng xin permit.
- **SMTP latency cao** khiến concurrency bị bão hòa dù rate limiter không từ chối.
- **Đột ngột không có job được submit** nhưng outbox vẫn nhận job mới.

### Runbook: provider bắt đầu trả lỗi throttling

1. Xác minh **provider/account/sender** nào chịu ảnh hưởng.
2. Tách loại lỗi: SMTP 4xx do rate, lỗi network, auth hay quota ngày.
3. Kiểm tra tốc độ thực tế **toàn cụm** và các service chia cùng account.
4. Xem quota remaining/reset time trên provider console nếu có.
5. Kiểm tra cấu hình limiter, số replica, recent deploy và burst capacity.
6. Giảm rate hoặc tạm dừng lane thấp; bảo vệ email quan trọng.
7. Xem retry/backoff có đang gây thundering herd không.
8. Giữ job trong outbox, tránh drop hoặc resend liên tục.
9. Theo dõi backlog age và ETA theo từng lane.
10. Khôi phục tốc độ từng bước khi provider ổn định, ghi lại nguyên nhân.

**Không giải quyết mặc định bằng cách tăng số thread hoặc SMTP connections.** Nếu provider đang throttling, tăng concurrency có thể làm nhiều thao tác bị từ chối hơn.

### Dashboard cần thấy cả demand và supply

Một biểu đồ nên đặt cạnh nhau:

~~~text
Demand: incoming jobs/second
Supply: accepted SMTP submissions/second

Nếu Demand > Supply trong thời gian dài:
    backlog sẽ tăng

Nếu Demand < Supply:
    backlog có cơ hội giảm
~~~

Khi có nhiều loại email, nên phân chia theo lane với mức cardinality thấp để thấy liệu email ưu tiên đang bị ảnh hưởng hay không.

## 32. Ước lượng thời gian xử lý backlog

Giả sử:

- Có `B` job đang chờ.
- Mỗi job tiêu tốn trung bình `c` đơn vị quota.
- Rate thực còn lại dành cho queue là `r` đơn vị/giây.
- Không phát sinh thêm job.

Ước lượng lý tưởng:

\[
t_{\mathrm{drain}} \approx \frac{B\times c}{r}
\]

Ví dụ `B = 30.000` email, mỗi email một recipient, rate ròng là 5 recipient/giây:

\[
t_{\mathrm{drain}} \approx 6\,000\ \mathrm{s}
  \approx 100\ \mathrm{phút}
\]

Nếu traffic mới đến liên tục với tốc độ `a` và rate xử lý là `r`, giả sử `r>a`, backlog giảm xấp xỉ ở tốc độ `r-a`:

\[
t_{\mathrm{drain}} \approx \frac{B\times c}{r-a}
\]

Công thức chỉ là một mô hình đơn giản. Nếu `r \le a`, backlog **không thể giảm bền vững** trong điều kiện ổn định.

### Yếu tố làm dự đoán sai

- Daily quota cạn và phải chờ reset.
- Rate dành cho các lane ưu tiên khác.
- Retry và lỗi SMTP tiêu tốn capacity.
- Attachment lớn hoặc latency/connection limit.
- Recipient per message khác nhau.
- Provider điều chỉnh giới hạn theo reputation.
- Nhiều replica/chính sách shared limiter.

Nên đo throughput thực tế **accepted** trong một cửa sổ ổn định, không dùng maxPoolSize hoặc số permit granted làm throughput thực tế để tính ETA.

### Deadline của mail quan trọng

Một OTP có hiệu lực 5 phút không nên nằm trong backlog 30 phút rồi mới gửi. Job có thể chứa:

~~~text
created_at
available_at
expires_at
priority
notification_type
~~~

Nếu `now > expires_at`, worker nên đánh dấu job hết hạn theo nghiệp vụ, không tự gửi mã đã mất hiệu lực chỉ vì còn quota. Với email subscription, campaign có thể có một deadline hoặc lịch gửi khác; mọi loại email không nên dùng một retry policy.

## 33. Kiểm thử provider-aware rate limiting

Cần kiểm tra nhiều lớp, không chỉ xem một method `tryAcquire()` trả true/false:

| Lớp test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Unit — token bucket | Burst ở mức capacity | Không cấp vượt capacity |
| Unit — refill | Thời gian giả trôi qua | Token được bổ sung đúng |
| Unit — cost | Message có 5 recipient | Trừ đúng 5 đơn vị recipient |
| Unit — invalid configuration | Rate <= 0, burst <= 0 | Fail fast |
| Unit — concurrency | Worker đang dùng hết slot | Không nhận thêm in-flight |
| Unit — multi-policy | Một hạn mức hết | Không thực hiện SMTP |
| Unit — retries | SMTP throttle | Đặt lịch retry có backoff |
| Unit — rejected before submit | Rate gate deny | Không tăng SMTP attempt |
| Unit — unknown outcome | Mất kết nối sau DATA | Không tự đánh dấu failed an toàn |
| Integration — Redis/DB | N worker reserve cùng key | Không vượt token/quota count |
| Integration — crash | Worker chết sau claim | Job trở lại trạng thái có thể xử lý theo lease |
| Integration — multi-replica | Nhiều instance cùng account | Aggregate throughput không vượt policy được kiểm thử |
| Integration — daily quota | Gần reset boundary | Accounting đúng window |
| Integration — failover | Provider A lỗi | Provider B chỉ được dùng theo routing/permission |
| System — backlog | Inbound rate > allowed rate | Job xếp hàng, không mất |
| System — priority | Marketing batch + OTP mới | OTP được dispatch theo SLA |

### Test cạnh tranh ở distributed store

Một bài test cần mô phỏng nhiều worker đồng thời xin permit cho cùng quota key:

~~~text
capacity = 10
refill disabled for duration of test
100 parallel workers each request 1 token

Expected:
    exactly 10 successful reservations
    90 denied
    total charged <= 10
~~~

Khi test này, phải kiểm tra **state ở shared store**, không chỉ đếm lời gọi tại từng replica. Nếu công cụ limiter tự refill theo thời gian, cần một phương pháp clock/test window kiểm soát để tránh kết quả bị ảnh hưởng bởi thời gian chạy.

### Test concurrency không dùng Thread.sleep tùy tiện

Dùng `CountDownLatch`, executor test và timeout để giữ một số SMTP tasks giả lập ở trạng thái đang chạy. Sau đó xác minh không vượt số slot đã định và mọi slot được release khi xảy ra exception.

### Test HTTP 429 không đồng nghĩa test SMTP 4xx

Nếu adapter dùng SMTP, giả lập phản hồi/thrown exception của SMTP transport. Nếu adapter dùng HTTP API, mock status `429` và `Retry-After`. Hai giao thức có cơ chế báo lỗi khác nhau; test không nên gọi chung tất cả là “429 SMTP”.

## 34. Kiểm thử tích hợp bằng SMTP sink có giới hạn giả lập

Một local SMTP sink chỉ lưu message (như Mailpit hoặc GreenMail) có thể giúp xác minh:

- Ứng dụng thực sự chỉ submit số message theo permit.
- Queue vẫn giữ job khi limiter từ chối.
- Không có nhiều SMTP sends đồng thời hơn concurrency limit.
- Worker cập nhật trạng thái đúng sau accepted/rejected.
- Message không bị gửi trùng khi nhiều worker claim cùng job.

Tuy nhiên, SMTP sink có thể không tự áp chính sách throttle của provider. Để kiểm thử lỗi quota cần một **SMTP test double** hoặc server giả lập có thể cố ý trả mã SMTP 4xx/5xx theo kịch bản.

### Bộ kịch bản có kiểm soát

~~~text
Scenario A: Provider accepts 3 per second
    -> rate gate giới hạn <= 3/s theo cửa sổ kiểm thử

Scenario B: Provider replies 451 for transient throttle
    -> record RETRY, backoff, no immediate retry storm

Scenario C: Provider disconnects after DATA
    -> record UNKNOWN, do not claim exactly-once

Scenario D: Shared limiter unavailable
    -> job remains durable; no uncontrolled flood

Scenario E: 4 replicas, one shared provider account
    -> quota reservation aggregate correctly enforced
~~~

Không dùng mail thật gửi tới người dùng production để thử vượt quota hoặc tạo hàng nghìn lỗi throttling. Những bài test này cần chạy trong môi trường sandbox được phê duyệt.

## 35. Những anti-pattern thường gặp

### 35.1. Cho mỗi thread `sleep(1000)` và coi đó là quota 1/s

Nếu có nhiều worker hoặc replica, tổng tốc độ không còn là 1/s. Sleep còn giữ thread và gây shutdown chậm. Dùng limiter có phạm vi đúng quota và trì hoãn job bền vững.

### 35.2. Chỉ giới hạn ThreadPoolTaskExecutor

~~~java
executor.setMaxPoolSize(10);
~~~

Điều này giới hạn concurrency cục bộ, **không phải** 10 message/giây, cũng không phải 10.000 recipient/ngày. Cần rate gate và quota budget.

### 35.3. Một local token bucket cho toàn bộ cụm

Local bucket được tạo riêng ở mỗi JVM. Khi scale out, aggregate throughput tăng theo số replica. Nếu provider quota là shared, dùng distributed limiter hoặc coordinator phù hợp.

### 35.4. Dùng riêng mỗi credential làm quota key dù account chia hạn mức chung

Hai credentials khác nhau có thể bị cộng dồn vào cùng organization quota. Tìm hiểu scope thật và đặt key theo provider policy, không tự giả định credentials độc lập.

### 35.5. Coi mọi lần `send(MimeMessage)` là một recipient

Message có nhiều `RCPT TO`, có thể bị tính nhiều đơn vị recipient quota. Áp cost theo đúng đơn vị và theo thông tin envelope của message.

### 35.6. Tự hoàn permit mỗi khi gặp exception

Nếu client mất kết nối sau khi provider accepted, hoàn permit và retry ngay có thể vượt quota và gửi trùng. Phân biệt lỗi trước submission với outcome UNKNOWN; thiết kế reservation semantics rõ ràng.

### 35.7. Retry ngay tất cả SMTP 4xx

~~~java
catch (MailSendException ex) {
    mailSender.send(message); // Retry lập tức có thể gây bão lỗi.
}
~~~

Không phân loại 4xx, không backoff hoặc quota check sẽ tạo thundering herd. Lưu job, phân loại lỗi và đặt lịch retry có jitter.

### 35.8. Coi 429 là mã SMTP

`429 Too Many Requests` là mã HTTP; SMTP dùng reply code theo chuẩn giao thức và có thể có enhanced status. Không áp parser/Retry-After HTTP vào SMTP transport mà không có hỗ trợ riêng của provider.

### 35.9. Chỉ tối ưu messages/second, bỏ qua daily quota

Một bucket refill liên tục vẫn có thể tiêu thụ quá nhiều recipient trong 24 giờ. Cần budget theo chu kỳ và đúng đơn vị.

### 35.10. Dùng fixed calendar day cho rolling 24h

Hai đợt gửi ngay trước và sau mốc reset ngày có thể vượt rolling quota. Chọn thuật toán theo chính sách thật của provider.

### 35.11. Claim toàn bộ outbox vào RAM khi chỉ gửi được vài thư mỗi giây

Queue bùng nổ, lease hết hạn, worker khác claim lại và khó phân biệt job nào đã gửi. Claim batch theo capacity, giữ backlog bền vững và dùng backpressure.

### 35.12. Coi `@Async` là cơ chế bảo đảm không mất mail

Executor queue nằm trong RAM, restart có thể làm mất task. Dùng transactional outbox hoặc broker khi cần durable delivery intent.

### 35.13. Gửi SMTP trong transaction giữ quota row lock

Giữ lock database trong lúc mạng chậm gây contention và deadlock risk. Reserve/quản lý state trong transaction ngắn; gửi ngoài transaction.

### 35.14. Cho marketing ăn hết quota bảo mật

Một campaign lớn có thể làm chậm OTP/password reset. Tách lane, áp ưu tiên/fairness và bảo vệ budget nếu policy cho phép.

### 35.15. Bất kỳ lỗi nào cũng failover qua provider khác

Outcome UNKNOWN có thể gây gửi trùng; provider B có sender/DKIM/quota khác; failover không được dùng để né anti-abuse restrictions.

### 35.16. Không quan sát rate limiter từ chối

Không có SMTP error không có nghĩa hệ thống khỏe. Nếu limiter từ chối và backlog tăng, cần cảnh báo theo tuổi job và SLA.

### 35.17. Log raw SMTP exception hoặc recipient để debug

Provider có thể echo địa chỉ, nội dung SMTP. Log jobId, providerId, status class, errorCode đã làm sạch và số lần thử; bảo vệ dữ liệu người nhận.

### 35.18. Đặt quá nhiều token capacity để “chống queue”

Burst cao có thể làm provider rate window bị vượt dù average rate đúng. Chọn capacity theo burst allowance được phép, không dùng queue delay làm lý do tăng burst vô hạn.

### 35.19. Chỉ giới hạn từ Spring app khi còn nhiều hệ thống cùng dùng account

Nếu một batch job legacy hoặc dashboard provider cũng gửi bằng cùng account, quota accounting trong app không đủ. Cần điều phối ở nguồn chung hoặc dành headroom, theo dõi provider usage và giới hạn quyền chia sẻ account.

### 35.20. Không tính chính sách ở thời điểm gửi

Job đã enqueue có thể hết hạn, người dùng rút consent hoặc tenant đổi sender policy. Trước khi xin permit và SMTP submit, kiểm tra lại những điều kiện nghiệp vụ cần thiết; đừng tốn quota cho mail không còn được phép gửi.

## 36. Quy trình triển khai rate limiting theo provider

Một lộ trình thực tế:

1. **Inventory nhà cung cấp và identities:** SMTP/API endpoints, account, credentials, sender domains và các ứng dụng cùng dùng.
2. **Thu thập quota chính thức:** message/recipient/rate/concurrency/window/reset và hành vi throttling.
3. **Chọn đơn vị cost:** mỗi message và mỗi recipient tùy policy.
4. **Xác định SLA:** OTP/transactional/batch, deadline và backlog age cho từng lane.
5. **Chọn giới hạn an toàn:** rate cap thấp hơn quota công bố nếu cần headroom.
6. **Thiết kế durable queue:** outbox/broker để giữ job khi quota hết hoặc provider lỗi.
7. **Tạo provider-aware admission:** quota ngày, rate bucket và concurrency cùng đơn vị, phạm vi.
8. **Lựa chọn trạng thái phân tán:** Redis atomic limiter, database reservation hoặc dispatcher tập trung theo năng lực hệ thống.
9. **Định nghĩa kết quả deny:** không gửi SMTP, không tăng SMTP attempt, defer job đến thời gian phù hợp.
10. **Định nghĩa retry:** phân biệt throttling, temporary, permanent và UNKNOWN; backoff với jitter và deadline.
11. **Phân bổ fairness:** bảo vệ luồng quan trọng và không làm starvation lane khác vô hạn.
12. **Tạo metrics/alerts:** permit, deny, provider throttle, quota remaining, accepted throughput và backlog age.
13. **Kiểm thử concurrency:** nhiều replica xin cùng quota, failover store và crash windows.
14. **Rollout có kiểm soát:** traffic nhỏ/sandbox, kiểm tra error rate và throughput, sau đó tăng dần.
15. **Lập runbook:** quota cạn, provider giảm tốc, retry storm, global store outage và campaign backlog.
16. **Đánh giá định kỳ:** khi đổi provider/gói dịch vụ, tăng replica, thêm app dùng account hoặc thay loại email.

### Mẫu policy tài liệu hóa

~~~yaml
# Ví dụ tài liệu thiết kế, không phải quota chính thức.
provider: PRIMARY
quotaScope: provider-account
rateUnit: recipients_per_second
burstCapacity: 12
refillPerSecond: 4
maxConcurrentSubmissions: 3
dailyQuotaUnit: recipients
dailyBudget: 15000
quotaWindow: provider-defined
priorities:
  - SECURITY
  - TRANSACTIONAL
  - SUBSCRIPTION
onRateDenied: defer_outbox
onLimiterUnavailable: fail_closed
retryPolicy: exponential_backoff_with_jitter
~~~

Đây là một policy document minh họa, không phải schema cấu hình tự động của Spring Boot. Mỗi hệ thống phải ánh xạ các trường vào implementation và xác minh provider thực tế.

## 37. Câu hỏi thường gặp

**Có thể cấu hình rate limit chỉ bằng `spring.mail.*` không?** Các thuộc tính Spring Mail chủ yếu cấu hình sender/SMTP session và transport. Provider-aware rate limiting là trách nhiệm của dispatcher/rate limiter hoặc dịch vụ điều phối được tích hợp, không tự xuất hiện khi đặt username/password.

**Có thể đặt `maxPoolSize=5` để gửi tối đa 5 thư/giây?** Không. Max pool size giới hạn số task đồng thời trong một executor, không phải throughput theo giây.

**Dùng một bucket trong mỗi Spring Boot instance có đủ không?** Chỉ khi quota được áp độc lập cho từng instance hoặc toàn cụm có cơ chế chia hạn mức an toàn. Với provider account shared quota, cần phối hợp toàn cụm.

**Có thể giới hạn theo SMTP host không?** Chỉ khi đó thực sự là phạm vi quota. Nhiều credentials/senders đi cùng host có thể độc lập hoặc cùng quota tùy provider.

**Provider thường giới hạn message hay recipient?** Tùy dịch vụ/gói. Có thể áp cả hai và thêm quota theo ngày/kết nối. Phải đọc chính sách của tài khoản thật, không giả định một message luôn là một recipient.

**Rate limit và quota ngày có thay thế nhau không?** Không. Rate giới hạn tốc độ; daily quota giới hạn tổng tiêu thụ trong cửa sổ.

**Đặt token bucket capacity lớn có tốt hơn không?** Chỉ khi provider cho phép burst lớn. Capacity cao có thể gây spike vượt policy dù refill rate thấp.

**Khi hết token nên đợi bằng Thread.sleep?** Không nên giữ mail worker trong thời gian dài. Tốt hơn là defer job trong queue/outbox và giải phóng tài nguyên.

**Có cần Redis cho mọi ứng dụng?** Không. Một process với lưu lượng nhỏ có thể dùng local limiter. Khi có nhiều replica, shared quota hoặc nhiều applications, cần cơ chế điều phối phù hợp; Redis chỉ là một lựa chọn.

**Nếu Redis bị lỗi, có nên gửi không giới hạn?** Không nên. Chọn fail closed hoặc fallback giới hạn được phê duyệt, đặc biệt khi provider có quota/anti-abuse nghiêm ngặt.

**SMTP trả 421 có chắc do rate limit không?** Không. 421 biểu thị dịch vụ tạm không sẵn sàng, có thể do nhiều nguyên nhân. Dùng ngữ cảnh/response/provider policy để phân loại.

**SMTP có Retry-After như HTTP 429 không?** Không có một cơ chế header Retry-After HTTP chung cho SMTP. Với HTTP email API, dùng hướng dẫn của API/provider; với SMTP, retry delay dựa vào reply code, trạng thái và policy.

**Nếu một email có 20 người nhận thì trừ mấy token?** Theo quota: một token nếu tính message, 20 nếu tính recipient, hoặc các cost khác nếu provider quy định. Có thể cần xin permit ở nhiều bucket khác nhau.

**Có nên refund token khi SMTP call exception?** Chỉ khi có bằng chứng chắc chắn quota chưa tiêu thụ và reservation mechanism cho phép. Nếu outcome không rõ, hoàn permit sai có thể gây vượt quota và duplicate.

**Giới hạn quota có làm mất email không?** Không nếu ý định gửi được lưu bền vững và worker defer đúng. Queue RAM thuần và fire-and-forget `@Async` không có cùng bảo đảm.

**Làm sao bảo đảm OTP không bị campaign làm chậm?** Dùng priority/fairness, budget reservation và tách lane/account nếu provider cho phép, kèm cảnh báo deadline.

**Có thể tự tăng rate khi không thấy throttling?** Có thể theo adaptive policy có giới hạn, nhưng phải chừa headroom, chỉ tăng khi có bằng chứng đủ tải, và không vượt hard cap provider.

**Có nên chuyển provider sau mỗi lỗi timeout?** Không. Một timeout sau DATA có thể là outcome UNKNOWN; retry/failover ngay có thể gửi trùng. Cần phân loại điểm lỗi và chính sách đối soát.

**Khi nhà cung cấp tăng quota, app có tự tăng theo không?** Chỉ khi có cơ chế cập nhật policy an toàn và nhất quán. Local bean tạo lúc startup không tự reload chỉ vì console provider đã thay đổi.

**Cách tính ETA xử lý backlog?** Dùng backlog hiện tại và throughput ròng accepted sau khi trừ traffic mới, retry và quota cho lane khác. Không dùng số thread làm ETA.

**Rate limit có giúp cải thiện deliverability không?** Điều tiết spike và giảm provider throttling có thể giúp vận hành ổn định, nhưng deliverability còn phụ thuộc consent, nội dung, authentication, reputation, bounce/complaints và chính sách người nhận.

## 38. Tổng kết

Trong **Spring Framework Mail**, giới hạn tốc độ theo nhà cung cấp là bài toán **điều phối tài nguyên và trạng thái gửi**, không chỉ là thêm `Thread.sleep` hoặc giảm số thread của `ThreadPoolTaskExecutor`.

Một hệ thống vững cần:

1. **Hiểu đúng quota:** message/recipient, rate/window, daily budget, concurrency và phạm vi provider/account/domain.
2. **Cấp permit có kiểm soát:** token bucket/sliding window và concurrency gate, đúng đơn vị và đúng scope.
3. **Điều phối toàn cụm:** một limiter cục bộ không đủ nếu nhiều replica cùng dùng account.
4. **Giữ job bền vững:** khi chưa có permit hoặc provider lỗi, defer trong outbox/broker thay vì mất email hoặc giữ worker ngủ.
5. **Phân loại SMTP outcome:** throttled, permanent, temporary, accepted và UNKNOWN; retry có backoff/jitter và tránh duplicate.
6. **Bảo vệ luồng quan trọng:** ưu tiên OTP/transactional, fair-share và deadline.
7. **Quan sát demand và capacity:** permit denied, quota remaining, provider throttle, accepted throughput và backlog age.

Sơ đồ kiến trúc tổng quát:

~~~text
Business events / Requests
           |
           v
  Transactional Mail Outbox
           |
           v
    Mail Dispatcher
           |
           +-- Validate eligibility / expiration
           +-- Choose allowed provider/account
           +-- Reserve shared quota & rate
           +-- Acquire concurrency slot
           |
           v
      JavaMailSender
           |
           v
      SMTP Provider
           |
      +----+-----+
      |          |
   Accepted   Rejected/Unknown
      |          |
      v          v
  SUBMITTED   Retry/DEAD/UNKNOWN
                 |
                 v
            Durable Outbox
~~~

**Nguyên tắc cuối cùng:** hãy để provider quota quyết định tốc độ gửi, để durable queue giữ các yêu cầu chưa đến lượt, và để ứng dụng theo dõi chính xác kết quả. Khi các lớp này được thiết kế nhất quán, hệ thống có thể gửi email đều đặn, tránh throttling không cần thiết, bảo vệ các thông báo quan trọng và tăng tải theo năng lực thực thay vì theo số thread được cấp.
