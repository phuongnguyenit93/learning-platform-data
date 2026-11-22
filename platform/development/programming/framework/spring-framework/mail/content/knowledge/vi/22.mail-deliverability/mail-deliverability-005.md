# Nhà cung cấp giới hạn tốc độ và quota

Một ứng dụng Spring Framework Mail có thể gửi email rất nhanh ở môi trường thử nghiệm nhưng gặp vấn đề khi triển khai thật: SMTP relay tạm hoãn thư, một chiến dịch newsletter làm email đặt lại mật khẩu đến chậm, hàng đợi tăng đột ngột hoặc provider báo đã vượt ngưỡng gửi trong ngày. Không phải mọi tình huống này đều là lỗi cấu hình `JavaMailSender`. Nhiều nhà cung cấp áp dụng **giới hạn tốc độ (rate limit)**, **quota**, **giới hạn kết nối đồng thời** và các chính sách bảo vệ uy tín gửi để ngăn lạm dụng tài nguyên.

**SMTP AUTH thành công không có nghĩa tài khoản được gửi vô hạn.** Provider có thể giới hạn theo tài khoản, tổ chức, IP, sender domain, người nhận, thời gian hoặc nhiều cấp cùng lúc. Con số cụ thể và cách tính quota thay đổi theo nhà cung cấp và gói dịch vụ. Spring Framework Mail không tự cung cấp một bộ điều tiết biết trước toàn bộ những giới hạn đó; ứng dụng cần thiết kế cơ chế điều phối gửi phù hợp.

Bài này phân biệt các loại giới hạn, phân tích phản hồi SMTP và HTTP email API, mô tả thiết kế outbox, rate limiter, concurrency guard, retry có backoff và jitter, phân bổ quota theo mức ưu tiên, giám sát vận hành và cách kiểm thử khi bị throttling. Mục tiêu là **gửi có kiểm soát, không làm mất công việc đang chờ và không biến một đợt retry thành cơn bão yêu cầu mới**.

## 1. Rate limit, quota, concurrency và deliverability khác nhau thế nào?

| Khái niệm | Định nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| Rate limit | Số thao tác tối đa trong một khoảng thời gian | 60 message/phút |
| Quota | Tổng lượng được phép dùng trong một chu kỳ/ngân sách | 10.000 recipient/ngày |
| Concurrency limit | Số thao tác hoặc kết nối cùng hoạt động | 5 phiên SMTP cùng lúc |
| Deliverability | Khả năng thư được tiếp nhận và chuyển đến người nhận theo mong muốn | Thư không bị bounce hoặc lọc spam |

Những con số trong bảng chỉ là **ví dụ giả định**, không phải giới hạn chung của SMTP.

Một tài khoản có thể chưa dùng hết 10.000 recipient/ngày nhưng vẫn bị throttling vì gửi 500 message trong vài giây. Ngược lại, gửi chậm nhưng đều đặn nhiều giờ có thể khiến tổng lượng recipient vượt quota ngày.

Deliverability là mục tiêu rộng hơn: tôn trọng quota giúp tránh bị nhà cung cấp tạm hoãn, nhưng không bảo đảm email vào inbox. Còn có uy tín sender, SPF, DKIM, DMARC, danh sách người nhận, bounce, complaint và nội dung thư.

### Ví dụ ba giới hạn cùng áp dụng

Provider giả định quy định:

~~~text
Tối đa 100 message/phút
Tối đa 15.000 recipient trong 24 giờ
Tối đa 4 kết nối SMTP đồng thời
~~~

Một message gửi tới 1 recipient có thể tiêu thụ một message và một recipient unit. Một message gửi tới 50 recipient có thể vẫn là một submission nhưng tiêu thụ 50 recipient units, tùy quy tắc của provider. Dù chưa vượt 100 message/phút, ứng dụng vẫn có thể gặp lỗi vì mở 10 kết nối SMTP đồng thời.

**Không chỉ đếm số lần gọi `JavaMailSender.send(...)` để kết luận đã dùng bao nhiêu quota.**

## 2. Những loại giới hạn nhà cung cấp thường đặt ra

### 2.1. Message throughput

Provider có thể giới hạn số message theo giây, phút hoặc giờ. Đây là giới hạn về tốc độ **submit**. Dùng nhiều thread hoặc `@Async` không làm giới hạn biến mất; nó chỉ tạo nhiều tác vụ gửi song song.

### 2.2. Recipient quota

Một provider có thể tính quota theo tổng số người nhận được chấp nhận. Ví dụ một message có `To`, `Cc` và `Bcc` có thể tiêu tốn nhiều recipient units. Cách tính các địa chỉ bị từ chối, submit thất bại hoặc retry tùy hợp đồng provider.

### 2.3. Recipient per message

Có thể tồn tại giới hạn số địa chỉ trong một message. Vì thế gộp 1.000 recipient vào một MIME message để “tiết kiệm quota” có thể bị từ chối, đồng thời làm tăng nguy cơ lộ danh sách địa chỉ ở To/Cc.

### 2.4. Concurrent SMTP connections

Provider có thể giới hạn số connection/session đồng thời. Một `ThreadPoolTaskExecutor` có 50 worker không nhất thiết đạt throughput cao hơn pool 5 worker; nó có thể gây authentication failures, throttling hoặc connection rejection.

### 2.5. Message size và attachment

Một giới hạn khác là tổng kích thước MIME. File đính kèm có thể được base64 encode và tăng kích thước trên đường truyền. Một message vượt giới hạn kích thước sẽ thất bại dù số message/recipient còn trong quota.

### 2.6. Sender account, domain, IP và tenant

Các giới hạn có thể ở:

- SMTP username hoặc API key.
- Provider account/subaccount.
- Organization hoặc tenant.
- Sender domain, subdomain hoặc IP pool.
- Domain của người nhận.
- Một recipient cụ thể.
- Một connection hay một loại dịch vụ.

Nếu ba SMTP user dùng chung một provider organization, quota có thể vẫn được cộng ở cấp tổ chức. **Nhiều credential không mặc nhiên có nghĩa quota hoàn toàn độc lập.**

## 3. Cửa sổ giới hạn: fixed, sliding và token bucket

Một quy định “100 email/phút” có thể được triển khai theo nhiều thuật toán:

| Thuật toán | Đặc điểm | Rủi ro hiểu sai |
| --- | --- | --- |
| Fixed window | Bộ đếm reset theo mốc thời gian | Có thể burst ở ranh giới hai cửa sổ |
| Sliding window | Giới hạn trên một cửa sổ thời gian trượt | Tốc độ được kiểm soát đều hơn |
| Token bucket | Token hồi theo thời gian, cho phép burst có giới hạn | Capacity lớn có thể tạo burst quá mạnh |
| Leaky bucket | Đầu ra được điều tiết theo nhịp | Tác vụ cần chờ |
| Rolling daily quota | Giới hạn tổng lượng trong 24 giờ gần nhất | Không reset đúng 00:00 địa phương |

Không nên giả định quota “theo ngày” reset lúc nửa đêm theo múi giờ của ứng dụng. Một nhà cung cấp có thể dùng UTC, múi giờ tài khoản hoặc cửa sổ 24 giờ trượt.

### Burst rate và sustained rate

Giả sử provider cho 60 message/phút, nhưng cấm hơn 2 message/giây. Nếu ứng dụng gửi cả 60 trong giây đầu tiên, tổng message/phút vẫn đúng nhưng tốc độ tức thời đã sai.

Cần cấp permit theo **nhiều cấp giới hạn** khi provider công bố nhiều ngưỡng, ví dụ một bucket theo giây và một quota theo ngày.

## 4. Ứng dụng Spring Mail chịu ảnh hưởng ra sao?

Lời gọi:

~~~java
MimeMessage message = mailSender.createMimeMessage();
// Thiết lập From, To, Subject và body.
mailSender.send(message);
~~~

có thể **blocking** trong lúc kết nối TCP, TLS, SMTP AUTH, chuyển dữ liệu và đợi phản hồi. Khi provider tạm hoãn:

- Thời gian xử lý có thể tăng.
- `JavaMailSender.send` có thể ném `MailException`.
- Các thread gửi bị chiếm tới timeout.
- Outbox hoặc executor queue có thể tăng.
- HTTP latency tăng nếu gửi trực tiếp trong request.
- Retry không giới hạn có thể khiến provider chặn mạnh hơn.

`@Async` chỉ chuyển công việc sang executor thread. Nó **không** tự điều tiết message/giây, recipient/ngày hoặc số kết nối đồng thời.

### Nhiều thread không chắc mang lại nhiều throughput

Ví dụ provider chấp nhận 20 message/giây. Nếu một worker gửi trung bình 10 message/giây, tăng số worker từ một lên bốn có thể đẩy tổng nhu cầu vượt giới hạn. Hệ thống có thể nhận nhiều lỗi hơn trong khi số message thực sự được nhận không tăng.

Cần kiểm soát cả **rate** và **concurrency**, đồng thời đặt SMTP timeout và giới hạn backlog.

## 5. SMTP response khi bị giới hạn

SMTP sử dụng reply code ba chữ số. Một số server bổ sung enhanced status code và câu giải thích.

| Nhóm | Ý nghĩa tổng quát | Hướng xử lý |
| --- | --- | --- |
| `2xx` | Positive completion | Tiếp tục lệnh/phiên theo giao thức |
| `4xx` | Transient negative completion | Đánh giá retry có trì hoãn |
| `5xx` | Permanent negative completion | Không retry mù quáng |

Các mã có thể gặp:

- `421`: Service không sẵn sàng hoặc đóng phiên; một số provider dùng khi quá nhiều connection.
- `450`: Mailbox tạm thời không sẵn sàng hoặc bị từ chối tạm thời.
- `451`: Lỗi tạm thời ở phía server; có thể dùng cho policy/throttling.
- `452`: Thiếu tài nguyên hoặc giới hạn tạm thời, có thể liên quan recipient/quota.
- `454`: Lỗi tạm thời liên quan authentication/TLS tùy ngữ cảnh.
- `550` / `553`: Có thể là recipient, relay hay policy rejection.
- `552`: Có thể liên quan storage hoặc message size theo ngữ cảnh.

**Không phải mọi `421`, `451` hay `452` đều là quota throttling.** Cần xem câu trả lời và tài liệu provider.

Ví dụ response mang tính minh họa:

~~~text
451 4.7.0 Temporarily deferred due to sending rate
~~~

Mã `4.7.0` là enhanced status thuộc nhóm liên quan policy/security. Phần text cho biết lý do throttling trong ví dụ này, nhưng nhà cung cấp khác có thể diễn đạt hoặc mã hóa khác. Không nên parse exception bằng cách chỉ tìm từ “quota”.

### Thất bại tạm thời không nghĩa thử lại ngay

Một phản hồi `4xx` có thể cho thấy điều kiện sẽ thay đổi sau một khoảng thời gian. Nếu ứng dụng retry lập tức, nó có thể tạo một vòng lặp tấn công chính provider của mình.

Cần backoff, jitter, giới hạn attempts và chính sách dừng.

## 6. HTTP API của provider khác SMTP

Một hệ thống có thể gửi qua:

1. SMTP bằng `JavaMailSender`.
2. HTTP REST API của provider qua WebClient/HTTP client.

Với HTTP API, provider có thể trả:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
~~~

`429` và `Retry-After` thuộc giao thức HTTP. Không có lý do để giả định `JavaMailSender` sẽ tự nhận HTTP status hay header này khi dùng SMTP.

| Transport | Tín hiệu | Lưu ý |
| --- | --- | --- |
| SMTP | Reply code, enhanced code, Jakarta Mail exception | Cần error classifier theo provider |
| HTTP API | HTTP status, Retry-After, JSON error | Tôn trọng hợp đồng HTTP API |
| Provider dashboard/API quản trị | Quota, usage, bounce, complaint | Có thể là dữ liệu không hoàn toàn real-time |

Nếu đổi từ SMTP sang HTTP API, application command và outbox có thể giữ nguyên, nhưng lớp transport/error classifier/quota integration cần được điều chỉnh.

## 7. Message quota và recipient quota phải được đếm riêng

Xem một message có nhiều recipient:

~~~java
helper.setTo("buyer@example.org");
helper.setCc("accounting@example.org");
helper.setBcc("audit@example.org");
~~~

Có một lệnh gửi message nhưng ba người nhận dự định. Theo provider, có thể tiêu thụ một submission và ba recipient units.

Các metric nên tách:

~~~text
message_attempt_total
message_submitted_total
recipient_attempt_total
recipient_accepted_total
recipient_rejected_total
local_quota_denied_total
provider_quota_remaining
~~~

Phải xác định rõ định nghĩa accepted là ứng dụng thấy lệnh gửi thành công hay provider xác nhận từng recipient. Không ghi “delivered” chỉ vì SMTP send trả về bình thường.

### Partial acceptance

SMTP session có thể gặp trường hợp một số recipient được chấp nhận, một số bị từ chối, tùy server và cấu hình Jakarta Mail. Retry **nguyên message** khi một recipient thất bại có thể làm những người đã được chấp nhận nhận thêm email.

Với email cá nhân hóa và hệ thống cần retry/audit chính xác, thường dễ quản lý hơn khi mỗi recipient logic có **một outbox job và một message riêng**.

## 8. Kiến trúc outbox và rate-controlled worker

Một luồng gửi phù hợp cho ứng dụng có yêu cầu độ tin cậy:

~~~mermaid
flowchart TD
    A["HTTP request / Business event"] --> B["Application service"]
    B --> C["Authorization + recipient policy"]
    C --> D["Persist business state + outbox"]
    D --> E["Worker claim PENDING job"]
    E --> F["Global / account / tenant quota gate"]
    F --> G{"Có permit?"}
    G -->|"Không"| H["Hoãn theo nextAttemptAt"]
    H --> E
    G -->|"Có"| I["Concurrency gate"]
    I --> J["JavaMailSender.send"]
    J --> K["SMTP relay"]
    K --> L["Ghi result / retry"]
~~~

Vai trò:

- Application service quyết định khi nào có email và ai được phép nhận.
- Outbox lưu ý định gửi bền vững cùng transaction nghiệp vụ nếu cần.
- Worker claim job có lease/token để nhiều instance không xử lý đồng thời một job.
- Quota gate quyết định thời điểm được phép dùng account.
- Concurrency gate giới hạn số kết nối/tác vụ đang chạy.
- Mail gateway gửi qua SMTP, không chứa business policy.
- State service cập nhật `SENT`, `RETRY` hoặc `DEAD` bằng transaction ngắn.

Khi quota chưa đủ, worker **không gọi SMTP**. Job được trì hoãn có kiểm soát, không biến thành SMTP failure và không bị xóa khỏi outbox.

### Outbox có bắt buộc không?

Không. Với email không quan trọng, lưu lượng thấp và chấp nhận mất task khi process chết, một bounded executor có thể đủ. Nhưng với hóa đơn, xác nhận giao dịch hoặc email cần audit/retry, outbox có lợi hơn vì công việc còn tồn tại sau restart.

## 9. Rate limiter theo nhiều scope

Giả sử provider account có global limit 100 message/giây. Hai tenant có hạn mức nội bộ riêng:

~~~text
Provider account: 100 message/giây

Tenant A: 30 message/giây
Tenant B: 20 message/giây
Các tenant khác: chia phần còn lại

Security: giữ một phần capacity ưu tiên
Marketing: có thể xếp hàng lâu hơn
~~~

Các con số minh họa. Một job chỉ được gửi nếu **tất cả scope liên quan đều cho phép**:

~~~text
provider-account
  → tenant
  → mail-purpose
  → recipient-domain (nếu policy yêu cầu)
~~~

Limiter theo tenant không thay thế global limiter. Limiter global không bảo vệ fairness giữa tenant. Tương tự, quota theo message không thay thế quota theo recipient.

### Khi quota service unavailable

Nếu Redis/database cấp permit gặp lỗi, việc cho tất cả worker gửi không giới hạn có thể gây provider throttling. Nên có chính sách fail-safe:

- Hoãn bulk mail.
- Giữ job trong outbox.
- Dùng giới hạn bảo thủ đã cấu hình nếu có cơ sở.
- Báo alert.
- Với security email, dùng phương án dự phòng được phê duyệt, không tùy tiện bỏ quota.

**Không nên mở toàn bộ limiter vì hệ thống điều tiết gặp lỗi.**

## 10. Token bucket: tốc độ hồi và burst

Token bucket là cách dễ hiểu để điều tiết:

- Bucket có capacity tối đa `C`.
- Token hồi theo rate `r` đơn vị/giây.
- Mỗi message cần một hoặc nhiều token.
- Khi đủ token, trừ token và cho phép.
- Khi thiếu token, lên lịch gửi sau.

Ví dụ bucket capacity 20 token, refill 5 token/giây:

~~~text
Tại thời điểm đầu: 20 token
Gửi 8 message: còn 12 token
Sau một giây không gửi: thêm tối đa 5 token
Không đủ token: không được gọi SMTP
~~~

Công thức:

\[
T_{\mathrm{new}} = \min(C,\; T + r \times \Delta t)
\]

Nếu chi phí job là `c` và `T_new ≥ c`, cấp permit rồi trừ `c`. Nếu không đủ, trả kết quả `DENIED` cùng thời điểm thử lại.

### Burst capacity không được quá rộng

Bucket hồi đúng 1 token/giây nhưng capacity 1.000 token có thể cho burst 1.000 message ngay khi bucket đầy. Nếu provider có limit theo giây, cấu hình này vẫn có thể gây throttle.

Cần dựa vào provider contract, sử dụng nhiều limiter khi cần cả burst cap và long-term quota.

## 11. Ví dụ sliding-window limiter chỉ trong một JVM

Có thể minh họa một gate bằng Java chuẩn:

~~~java
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.Deque;

public final class LocalMailRateGate {

    private final int maxMessages;
    private final long windowNanos;
    private final Deque<Long> acceptedAt =
            new ArrayDeque<>();

    public LocalMailRateGate(
            int maxMessages,
            Duration window) {

        if (maxMessages <= 0
                || window == null
                || window.isZero()
                || window.isNegative()) {
            throw new IllegalArgumentException(
                    "Invalid rate window"
            );
        }

        this.maxMessages = maxMessages;
        this.windowNanos = window.toNanos();
    }

    public synchronized boolean tryAcquire() {
        long now = System.nanoTime();

        while (!acceptedAt.isEmpty()
                && now - acceptedAt.peekFirst()
                        >= windowNanos) {
            acceptedAt.removeFirst();
        }

        if (acceptedAt.size() >= maxMessages) {
            return false;
        }

        acceptedAt.addLast(now);
        return true;
    }
}
~~~

Ví dụ sử dụng:

~~~java
LocalMailRateGate gate = new LocalMailRateGate(
        60,
        Duration.ofMinutes(1)
);

if (gate.tryAcquire()) {
    mailGateway.send(mail);
} else {
    // Ghi nextAttemptAt và trả job vào trạng thái chờ.
    // Không sleep trên SMTP worker thread.
}
~~~

Đây là **ví dụ thuật toán**, không phải giải pháp production hoàn chỉnh:

- Bộ đếm chỉ tồn tại trong một process.
- Không chia sẻ permit với các instance khác.
- Không tính cost theo recipient.
- Không biết daily quota của provider.
- Không bảo toàn counter qua restart.
- Không bảo đảm fairness hay nhiều cửa sổ quota.
- Không tự giải quyết việc permit đã cấp nhưng SMTP chưa bắt đầu.

Với nhiều instance, cần một hệ thống cấp permit chung hoặc phân vùng capacity chính thức.

## 12. Limiter phân tán và cập nhật nguyên tử

Nếu có ba worker instance, mỗi instance cho phép 60 message/phút, tổng có thể đạt 180/phút dù provider chỉ cho 60/phút.

Giải pháp có thể là:

- Redis + Lua atomic script/token bucket.
- Database counter với transaction/conditional update.
- Một dispatcher tập trung.
- Broker/queue với số worker và throughput đã định.
- Hệ thống rate limiter phân tán phù hợp hạ tầng.

Cốt lõi là **check-and-consume phải nguyên tử**. Không làm:

~~~text
count = GET(account_key)
if count < limit:
    SET(account_key, count + 1)
    return ALLOWED
~~~

Hai worker có thể cùng đọc count còn chỗ và cùng tăng.

Thay vào đó, quota authority cần thực thi:

~~~text
tryAcquire(account, tenant, purpose, cost):
  atomically:
    cập nhật window/token
    kiểm tra các hạn mức liên quan
    nếu đủ:
      tiêu thụ permit
      trả ALLOWED
    nếu thiếu:
      không tiêu thụ
      trả DENIED + retryAt
~~~

Khi một job cần nhiều scope, hãy thiết kế cách cấp permit để không tiêu thụ một phần quota rồi thất bại ở scope khác mà không có chủ đích. Với Redis cần xử lý đồng hồ, TTL, key cardinality và tính sẵn sàng. Nếu quota authority mất kết nối, worker phải theo fail-safe policy.

### Quota local là ước lượng, provider là nguồn giới hạn thực tế

Bộ đếm của ứng dụng có thể không phản ánh chính xác usage ở provider nếu có:

- Ứng dụng khác dùng chung credential.
- Admin gửi thủ công.
- Provider tính recipient và submission khác dự kiến.
- Retry hoặc partial acceptance.
- Provider thay đổi quota/gói dịch vụ.

Nếu provider có API báo quota remaining/reset, có thể sử dụng để hiệu chỉnh limiter, nhưng cần xem độ trễ cập nhật, phạm vi account và semantics của số liệu.

## 13. Rate gate nằm ở bước nào của outbox worker?

Có hai cách thường gặp:

**Claim trước rồi xin permit.** Worker claim job trong transaction ngắn. Nếu limiter từ chối, ghi trạng thái chờ và `nextAttemptAt` rồi nhả lease. Không giữ transaction mở và không tăng SMTP attempt count nếu chưa gọi send.

**Xin permit trước rồi claim.** Dispatcher cấp capacity trước, sau đó claim số job phù hợp. Cần xử lý permit đã cấp nhưng không có job hoặc worker chết trước khi sử dụng permit.

Cả hai đều có đánh đổi. Quan trọng là:

- Không giữ DB row lock trong lúc chờ quota.
- Không giữ nhiều worker thread `sleep` hàng giờ.
- Không retry nóng.
- Không ghi nhận “SMTP failed” khi chưa gọi SMTP.
- Không biến quota denial thành job bị xóa.
- Không cấp permit theo account A rồi gửi qua account B.

### Phân biệt trạng thái chờ quota và lỗi gửi

Có thể dùng state machine:

~~~text
PENDING
WAITING_RATE_LIMIT
SENDING
RETRY
SENT
DEAD
~~~

`WAITING_RATE_LIMIT` biểu thị job chưa được provider gọi vì thiếu permit. `RETRY` có thể biểu thị đã có một lần gửi lỗi hoặc outcome chưa rõ. Nếu không muốn thêm status, có thể dùng `PENDING + nextAttemptAt + reasonCode`; vẫn cần phân biệt **attempt thực** với **lần hoãn nội bộ**.

## 14. Pseudocode worker kết hợp quota và concurrency

~~~java
public void process(ClaimedMailJob job) {

    SenderAccount account =
            routingPolicy.resolve(
                    job.tenantId(),
                    job.mailPurpose()
            );

    QuotaCost cost = new QuotaCost(
            1,                      // Message submission.
            job.recipientCount()    // Recipient units.
    );

    PermitDecision permit =
            quotaService.tryAcquire(
                    account.id(),
                    job.tenantId(),
                    job.mailPurpose(),
                    cost
            );

    if (!permit.allowed()) {
        stateService.scheduleForQuota(
                job.id(),
                job.claimToken(),
                permit.retryAt()
        );
        return;
    }

    try {
        concurrencyGate.withPermit(
                account.id(),
                () -> mailGateway.send(
                        account,
                        renderer.render(job)
                )
        );

        stateService.markSent(
                job.id(),
                job.claimToken()
        );

    } catch (MailException transportError) {
        stateService.recordTransportFailure(
                job.id(),
                job.claimToken(),
                transportError
        );
    }
}
~~~

Đây là **pseudocode kiến trúc Java**. Các class `ClaimedMailJob`, `QuotaCost`, `PermitDecision`, `StateService` và gateway là abstractions ứng dụng tự định nghĩa. Mã production phải phân biệt lỗi renderer, gửi, cập nhật trạng thái và trường hợp job mất lease. Không bao toàn bộ SMTP call trong một transaction DB kéo dài.

### Permit đã cấp nhưng chưa gửi thì sao?

Provider có thể tính quota theo submission thực, còn local limiter tiêu thụ token trước. Nếu worker chết ngay sau khi lấy token, local count có thể cao hơn usage thật. Điều này thường **bảo thủ** hơn việc cấp lại token bừa bãi rồi có nguy cơ vượt quota. Muốn hoàn permit, phải xác định chắc chắn chưa tạo external side effect và hợp đồng limiter hỗ trợ.

Không hoàn token tự động khi timeout mà không biết SMTP relay đã nhận hay chưa.

## 15. Giới hạn kết nối đồng thời với Semaphore

Rate limiter không thay thế giới hạn concurrency. Nếu một lần gửi mất 10 giây, ngay cả tốc độ submit 30 message/phút cũng có thể giữ nhiều connection đang hoạt động.

Một ví dụ cục bộ:

~~~java
import java.util.concurrent.Semaphore;

public final class LocalConnectionGate {

    private final Semaphore permits =
            new Semaphore(5, true);

    public void runWithPermit(Runnable operation)
            throws InterruptedException {

        permits.acquire();

        try {
            operation.run();
        } finally {
            permits.release();
        }
    }
}
~~~

Con số 5 chỉ là ví dụ. Cần giới hạn thời gian chờ permit, xử lý interruption và shutdown. Một `Runnable` không ném checked exception; trong ứng dụng có thể dùng functional interface riêng.

**Semaphore trên một JVM không bảo vệ giới hạn tổng của provider khi có nhiều JVM.** Có thể dùng limiter phân tán hoặc cấp capacity cố định cho các worker group sao cho tổng không vượt cap.

## 16. @Async và ThreadPoolTaskExecutor không phải quota manager

~~~java
@Async("mailExecutor")
public CompletableFuture<Void> sendAsync(MailCommand command) {
    mailGateway.send(command);
    return CompletableFuture.completedFuture(null);
}
~~~

`@Async` chỉ làm cho method được thực thi qua executor nếu lời gọi đi qua Spring proxy phù hợp. Nó không tự biết quota provider. Nếu 10.000 event được đẩy vào executor:

- Queue trong bộ nhớ có thể rất lớn.
- Nhiều thread có thể gọi SMTP cùng lúc.
- Queue đầy có thể gây task rejection.
- `CallerRunsPolicy` có thể đẩy tác vụ về request thread.
- Khi JVM chết, task còn trong RAM có thể bị mất.

Một outbox với worker được rate-controlled có thể phù hợp hơn cho notification quan trọng. `@Async` có thể hỗ trợ concurrency bên trong worker, nhưng cần bounded executor, rate gate và giám sát.

## 17. Phân loại lỗi từ JavaMailSender

`JavaMailSender.send` có thể ném exception từ tầng `org.springframework.mail` như `MailSendException`, với nguyên nhân sâu hơn đến từ Jakarta Mail hoặc SMTP provider.

Có thể xây một error taxonomy:

~~~java
public enum MailFailureCategory {
    PROVIDER_THROTTLED,
    QUOTA_EXHAUSTED,
    TEMPORARY_TRANSPORT,
    PERMANENT_RECIPIENT,
    MESSAGE_TOO_LARGE,
    AUTHENTICATION_FAILED,
    TLS_CONFIGURATION,
    UNKNOWN_OUTCOME
}
~~~

~~~java
public interface MailErrorClassifier {
    MailFailureCategory classify(
            Throwable error,
            SenderAccount account);
}
~~~

Implementation phải dựa trên exception chain, SMTP status/enhanced status có thể truy xuất, tài liệu provider, ngữ cảnh lệnh và trạng thái giao tiếp. Nếu có nhiều recipient, cần xem thông tin accept/reject theo địa chỉ mà thư viện cung cấp.

Sai:

~~~java
if (error.getMessage().contains("limit")) {
    retryImmediately();
}
~~~

Chuỗi thông báo có thể thay đổi, không có cấu trúc, chứa PII hoặc nói đến một limit không liên quan tốc độ. Nên có nhánh `UNKNOWN_OUTCOME` và ghi reason code có cấu trúc.

### 4xx có thể retry, nhưng cần lịch

Lỗi tạm thời không có nghĩa thử ngay. Hãy dùng backoff/jitter, quota reset hint nếu có, max attempts và policy ưu tiên.

## 18. Exponential backoff và jitter

Một công thức phổ biến:

\[
d_n = \min(d_{\max}, d_{\mathrm{base}} \cdot 2^{n-1}) + J_n
\]

Trong đó `n` là attempt thứ n, `d_base` là thời gian chờ ban đầu, `d_max` là trần và `J_n` là jitter.

Ví dụ nếu base 30 giây, cap 30 phút:

| Retry | Thời gian cơ bản chưa jitter |
| --- | --- |
| 1 | 30 giây |
| 2 | 60 giây |
| 3 | 120 giây |
| 4 | 240 giây |
| 5 | 480 giây |
| 6 | 960 giây |

Các số chỉ minh họa. Không tính số mũ vô hạn trên integer gây overflow. Nếu provider HTTP API có `Retry-After` hoặc dashboard cung cấp reset time, dùng tín hiệu được tài liệu hóa để điều chỉnh lịch.

### Retry storm

Không làm:

~~~java
while (true) {
    try {
        mailSender.send(message);
        break;
    } catch (MailException ex) {
        // Thử lại ngay, không sleep/backoff.
    }
}
~~~

Vòng lặp này không giới hạn attempts, không phân loại lỗi, có thể spam provider và gây duplicate khi timeout không rõ kết quả.

Thay vào đó, worker ghi `RETRY` với `nextAttemptAt`, nhả thread, scheduler chỉ claim khi đến hạn. Quota denial nội bộ có thể dùng lịch riêng và không nhất thiết được tính như SMTP attempt.

## 19. Quota ngày cạn khác với limit theo giây

Provider báo không còn quota ngày lúc 13:00. Retry sau 5 giây sẽ không giúp nếu quota chỉ reset nhiều giờ sau.

Một decision object:

~~~java
public record PermitDecision(
        boolean allowed,
        Instant retryAt,
        String reasonCode) {
}
~~~

Các reason code nội bộ ví dụ:

~~~text
RATE_PER_SECOND
RATE_PER_MINUTE
DAILY_QUOTA
ACCOUNT_SUSPENDED
CONCURRENCY_FULL
PROVIDER_BACKOFF
~~~

Không xử lý `ACCOUNT_SUSPENDED` như throttle bình thường; có thể cần can thiệp vận hành. Thời điểm reset quota cần lấy từ contract/provider hoặc ước lượng bảo thủ có quan sát, không tự mặc định đúng nửa đêm.

### Bảo vệ một phần capacity

Nếu security và marketing chia quota account, campaign bulk có thể tiêu hết ngân sách trước khi khách hàng cần reset password. Có thể:

- Tách account/subaccount nếu provider cung cấp quota riêng.
- Dự phòng capacity cho security/transactional.
- Trì hoãn marketing khi quota còn ít.
- Dùng priority queue và per-purpose limit.
- Đặt global cap bao phủ mọi account dùng chung tổ chức/IP.

Không cho phép yêu cầu marketing tự đổi purpose thành security để vượt quota.

## 20. Idempotency khi retry

Hai dạng trùng:

1. **Duplicate enqueue:** Một event tạo hai outbox jobs.
2. **Duplicate external submission:** Cùng job được gửi hai lần sau retry/crash.

Unique idempotency key theo event/purpose/recipient giúp giảm duplicate enqueue. Nhưng không tạo atomic transaction giữa database và SMTP.

~~~text
Worker gửi mail
SMTP relay chấp nhận message
Mạng đứt trước khi worker nhận phản hồi
Worker thấy timeout
Worker retry
SMTP có thể chấp nhận message lần hai
~~~

`Message-ID` là header định danh thư để tracing/threading; nó không buộc SMTP relay phải dedupe. Nếu provider HTTP API thật sự hỗ trợ idempotency key, cần dùng đúng hợp đồng của provider với cùng key qua retry.

**Không tuyên bố exactly-once delivery chỉ vì dùng outbox và `JavaMailSender`.**

## 21. Fairness giữa tenant và loại email

Một global FIFO queue có thể khiến 100.000 mail marketing của tenant A chặn email giao dịch mới của tenant B.

Các cách giảm tình trạng này:

- Queue hoặc lane ưu tiên theo purpose.
- Giới hạn số job claim mỗi tenant mỗi lượt.
- Weighted fair scheduling.
- Rate cap theo tenant, provider account và purpose.
- Reserved capacity cho security.
- Rate limit riêng cho bulk/campaign.
- Quan sát queue age theo loại thư, không chỉ tổng backlog.

Priority không có nghĩa được bỏ qua quota provider. Khi quota thực sự cạn, ứng dụng cần hoãn hoặc dùng tuyến dự phòng **đã được phê duyệt cho cùng mục đích**, không tự động gửi marketing qua account security.

## 22. Tách SMTP account để cách ly tải

Ứng dụng có thể dùng:

~~~text
securityMailSender
transactionalMailSender
marketingMailSender
~~~

Mỗi `JavaMailSenderImpl` có host/credential/sender identity riêng, được routing theo `MailPurpose`.

~~~java
public enum MailPurpose {
    SECURITY,
    TRANSACTIONAL,
    MARKETING
}
~~~

~~~java
public interface MailRoutingPolicy {
    SenderAccount resolve(
            MailPurpose purpose,
            UUID tenantId);
}
~~~

**Không để HTTP client chọn SMTP account tùy ý.** Application service quyết định purpose từ use case đã được ủy quyền.

Và cần nhớ: nhiều username dưới cùng provider organization có thể vẫn chia sẻ quota, reputation hoặc IP pool. Phân tách muốn thực sự giảm ảnh hưởng phải được kiểm tra ở cấp provider.

## 23. Ước lượng capacity theo throughput

Giả sử cần gửi 12.000 email giao dịch trong 2 giờ. Mỗi message có một recipient; provider giới hạn giả định 150 message/phút và 20.000 recipient/ngày.

Tốc độ trung bình cần có:

\[
r = \frac{12\,000}{120} = 100\ \text{message/phút}
\]

Theo số học, 100/phút thấp hơn 150/phút và 12.000 recipient thấp hơn 20.000/ngày. Nhưng hệ thống còn phải xét:

- Traffic của các chức năng khác dùng cùng quota.
- Giới hạn theo giây và concurrency.
- SMTP latency, timeout, attachment size.
- Retry làm tăng tổng attempts.
- Quota reset time và domain-specific deferral.
- Capacity cần dự phòng cho security.
- Mức tải từng thời điểm thay vì chỉ trung bình.

Nếu provider cap thấp hơn nhu cầu, **thêm thread không giải quyết bài toán**. Cần kéo dài lịch gửi, giảm burst, phân bổ capacity hoặc thay đổi gói/provider theo chính sách.

### Ước lượng concurrency với Little's Law

Nếu throughput mong muốn là `λ` message/giây và một lần gửi trung bình mất `W` giây, concurrency trung bình xấp xỉ:

\[
L \approx \lambda W
\]

Ví dụ cần 2 message/giây, SMTP latency trung bình 1,5 giây, concurrency tối thiểu lý thuyết khoảng 3. Đây chỉ là ước lượng; p95/p99 latency, connection reuse và cap provider có thể khiến cần hiệu chỉnh. Không dùng công thức này để bỏ qua hard concurrency limit.

## 24. Cấu hình SMTP timeout trong Spring Boot

~~~yaml
spring:
  mail:
    host: smtp.provider.example
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

Host, port và thời gian chờ là giá trị minh họa. Các JavaMail timeout tính bằng mili giây. Chúng giúp tránh thread bị treo vô hạn, **không phải rate limiter**. Một send bị timeout vẫn có thể là kết quả chưa xác định.

STARTTLS/implicit TLS và kiểm tra chứng chỉ bảo vệ kết nối; chúng không quyết định quota. SPF/DKIM/DMARC xác thực sender domain; chúng cũng không tự tăng throughput. Không tắt TLS hoặc đổi domain chỉ để né throttling.

## 25. Deliverability và phản hồi sau SMTP

Một lần `JavaMailSender.send` trả về bình thường không đồng nghĩa email đã vào inbox. Relay có thể tiếp tục:

- Tạm hoãn ở server nhận.
- Bounce vì mailbox không tồn tại.
- Chuyển vào spam folder.
- Từ chối về sau theo policy/domain.
- Nhận spam complaint hoặc unsubscribe.

Muốn cải thiện deliverability cần:

1. Recipient hợp lệ, được phép nhận thư và đã được kiểm tra theo purpose.
2. Xử lý hard bounce, unsubscribe và complaint.
3. Sender domain được xác thực SPF/DKIM/DMARC phù hợp.
4. Nội dung, tần suất và danh sách gửi có chất lượng.
5. Warm-up và ramp tốc độ khi sender domain/IP còn mới.
6. Tránh gửi trùng do retry không có idempotency.
7. Đo provider feedback, không chỉ local send success.

**Submitted, SMTP accepted, delivered và opened là các trạng thái khác nhau.** Không gộp chúng thành một cờ “email thành công”.

## 26. Warm-up, ramp-up và recipient domain

Một sender domain hoặc IP mới có thể bị đánh giá bất thường nếu đột ngột tăng từ vài chục lên hàng chục nghìn message. Dù quota kỹ thuật cho phép, deliverability vẫn có thể xấu.

Chiến lược:

- Bắt đầu với lượng gửi phù hợp và người nhận hợp lệ.
- Tăng theo tín hiệu accept/bounce/complaint.
- Tránh burst lớn ngay sau deploy.
- Giảm tốc nếu tạm hoãn hoặc complaint tăng.
- Không dùng danh sách chưa có consent để “warm-up”.

Không có một lịch tăng chung an toàn cho mọi provider. Các ngưỡng cụ thể cần dựa vào hướng dẫn provider và quan sát thực tế.

Một server nhận có thể tạm hoãn nhiều message tới cùng domain, dù provider sender còn quota. Khi thấy tín hiệu nhất quán có căn cứ, có thể đặt rate limit theo recipient domain. Nhưng không coi mọi lỗi của domain đó là throttling mà thiếu phân tích.

## 27. Monitoring và cảnh báo quota

Những metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| `mail_send_attempt_total` | Số lần thử gửi |
| `mail_smtp_accepted_total` | Số thao tác gửi thành công theo API |
| `mail_provider_throttle_total` | Số lỗi được phân loại là throttling |
| `mail_quota_denied_total` | Số công việc bị local gate hoãn |
| `mail_queue_depth` | Số job chờ |
| `mail_oldest_pending_age_seconds` | Thời gian chờ lâu nhất |
| `mail_retry_total` | Số lần retry |
| `mail_send_duration_seconds` | SMTP latency |
| `mail_active_send_count` | Số lần send đồng thời |
| `mail_provider_remaining_quota` | Quota remaining do provider báo |
| `mail_dead_job_total` | Số job cần can thiệp |

Nên gắn account/purpose/tenant label theo khả năng vận hành và tránh metric cardinality quá lớn. Provider quota metric có thể cập nhật trễ; không tự giả định local estimate khớp số liệu provider.

### Các alert đáng chú ý

- Security email chờ lâu hơn SLA.
- Quota remaining thấp hơn nhu cầu gửi dự kiến.
- SMTP throttling tăng bất thường.
- Retry rate tăng nhưng throughput accepted không tăng.
- Connection timeout hoặc latency tăng.
- Queue age tăng liên tục.
- Worker vẫn retry quá nhanh khi daily quota đã cạn.
- Có SMTP account lạ phát sinh lưu lượng.
- `DEAD` jobs tăng theo một reason code.

Một trăm email reset password chờ 15 phút có thể nghiêm trọng hơn hàng chục nghìn email marketing đang gửi đúng lịch. Theo dõi **queue age và purpose**, không chỉ count.

## 28. Audit an toàn

Một bản ghi gửi có thể chứa:

~~~text
mail_job_id: job-412
business_event_id: evt-981
tenant_id: tenant-42
purpose: TRANSACTIONAL
sender_profile: tx-primary
recipient_contact_id: contact-77
attempt: 3
failure_category: PROVIDER_THROTTLED
next_attempt_at: 2026-11-12T12:30:00Z
provider_reply_class: 4xx
~~~

Không log SMTP password, reset token, body email, attachment hoặc địa chỉ người nhận đầy đủ nếu không có nhu cầu và cơ chế bảo vệ. Ưu tiên correlation ID, contact ID, masking và reason code có cấu trúc.

Audit cần trả lời: job nào, sự kiện nào, account nào, vì sao bị hoãn, còn bao nhiêu quota, khi nào retry, outcome từ provider và ai đã kích hoạt manual replay.

## 29. Kiểm thử rate limit và throttling

### 29.1. Local limiter

- Cấp được đúng số permit tối đa.
- Permit tiếp theo bị từ chối.
- Permit mới sau khi cửa sổ trôi qua.
- Hai thread cùng gọi không vượt cap.
- Time math không bị overflow hoặc reset sai.

### 29.2. Phân tán nhiều instance

- Hai hoặc nhiều worker cùng xin permit trên quota shared.
- Tổng permit không vượt global cap mô phỏng.
- Tenant A không vượt tenant cap.
- Khi quota authority unavailable, hệ thống xử lý theo fail-safe policy.

### 29.3. SMTP test server giả lập throttling

- Server trả lỗi `4xx` có nội dung minh họa.
- Classifier nhận dạng đúng lỗi được provider tài liệu hóa.
- Job chuyển `RETRY` và có `nextAttemptAt`.
- Không retry nóng.
- Có max attempts và phân loại `DEAD` khi phù hợp.

### 29.4. Daily quota exhaustion

- Local gate từ chối và reschedule job.
- Không giữ thread ngủ nhiều giờ.
- Alert quota và queue age được phát.
- Priority/security policy được tôn trọng nhưng không vượt provider cap.

### 29.5. Concurrency

- Với 50 job và cap 5, không có hơn 5 send cùng lúc trong phạm vi bảo vệ.
- Permit được giải phóng khi lỗi xảy ra.
- Test toàn cluster khi provider giới hạn toàn account, không chỉ một JVM.

### 29.6. Partial recipient success

- Một số RCPT được chấp nhận, một số bị từ chối.
- Không retry toàn bộ recipient mà không xem trạng thái đã được relay chấp nhận.
- Có cơ chế retry/audit phù hợp với từng recipient.

### 29.7. Ambiguous timeout

- Fake transport mô phỏng relay đã nhận message nhưng caller gặp timeout.
- Worker không khẳng định chắc chắn “chưa gửi”.
- Chính sách retry/đối soát và cảnh báo rủi ro duplicate được kiểm tra.

### 29.8. Restart

- Outbox job chờ không bị mất.
- Lease hết hạn cho phép reclaim.
- `SENT` không bị claim lại bình thường.
- Rate-limit denial không bị đếm là một SMTP attempt.

Không dùng SMTP credential production trong automated test; dùng fake mail sender, SMTP test server hoặc provider sandbox phù hợp.

## 30. Sai lầm thường gặp

### 30.1. Tưởng SMTP AUTH thành công là gửi không giới hạn

Authentication chỉ chứng minh account được xác thực. Rate, quota và policy vẫn áp dụng.

### 30.2. Chỉ tăng thread pool

Concurrency không đồng nghĩa throughput hợp lệ; có thể chạm connection limit nhanh hơn.

### 30.3. Dùng @Async như rate limiter

`@Async` không quản lý quota provider.

### 30.4. Limiter cục bộ khi deploy nhiều JVM

Tổng các limiter có thể vượt global cap. Cần quota authority phân tán.

### 30.5. Coi mọi SMTP 4xx là quota error

SMTP 4xx có nhiều nguyên nhân. Phân loại theo provider reply và context.

### 30.6. Retry ngay, không backoff/jitter

Gây retry storm, làm giảm khả năng phục hồi và có thể gửi trùng.

### 30.7. Nhầm HTTP 429 với SMTP reply

`429`/`Retry-After` thuộc HTTP API. SMTP có response code riêng.

### 30.8. Không đếm recipient

`To`, `Cc` và `Bcc` có thể dùng nhiều recipient units theo provider.

### 30.9. Giữ SMTP thread chờ reset quota

Ngốn thread và tài nguyên. Lưu `nextAttemptAt` rồi trả job về queue.

### 30.10. Không phân bổ fairness

Một campaign có thể chiếm hết quota, làm email security chậm.

### 30.11. Marketing tự chuyển sang account security

Phá sender policy, quota isolation và có thể ảnh hưởng reputation.

### 30.12. Không đặt SMTP timeout

Network I/O có thể giữ worker lâu ngoài dự tính.

### 30.13. Coi send không lỗi là delivered

SMTP relay có thể chấp nhận thư nhưng bounce hoặc spam về sau.

### 30.14. Retry toàn bộ người nhận khi chỉ một RCPT bị từ chối

Có thể làm người đã được chấp nhận nhận thêm bản sao.

### 30.15. Không ghi nhận kết quả không chắc chắn

Timeout sau SMTP DATA không chứng minh chưa gửi.

### 30.16. Chỉ giới hạn theo ngày, bỏ qua burst theo giây

Có thể bị throttling dù còn daily quota.

### 30.17. Fail-open khi Redis quota bị lỗi

Có thể khiến mọi worker dồn vào provider. Cần fail-safe policy.

### 30.18. Tăng quota mà bỏ qua deliverability

Quota cao hơn không sửa bounce, complaint, thiếu SPF/DKIM/DMARC hoặc chất lượng danh sách.

## 31. Câu hỏi thực hành

**Câu 1.** Provider cho 10.000 recipient/ngày, mỗi message có 5 recipient. Nếu 2.000 message được nhận đầy đủ, lượng recipient units là bao nhiêu theo quy tắc một unit/người nhận?

10.000 recipient units. Tuy nhiên, cần xem cách tính quota thực tế của provider.

**Câu 2.** Ba instance mỗi instance cho 100 message/phút, provider cho toàn account 100/phút. Có an toàn không?

Không. Tổng lý thuyết có thể lên 300/phút. Cần limiter chung hoặc phân bổ capacity chính thức.

**Câu 3.** `@Async("mailExecutor")` với 50 thread có tự chống throttling không?

Không. Nó chỉ điều phối thread.

**Câu 4.** SMTP trả `451 4.7.0`. Có thể khẳng định đã hết quota ngày?

Không. Cần reply text, provider contract và ngữ cảnh.

**Câu 5.** HTTP API trả `429 Retry-After: 120`. `JavaMailSender` có tự đọc không?

Không. `JavaMailSender` là SMTP sender; HTTP API là transport khác.

**Câu 6.** Relay đã chấp nhận thư nhưng worker timeout trước khi thấy phản hồi. Retry có thể gây trùng không?

Có. Kết quả không chắc chắn, cần policy riêng.

**Câu 7.** Daily quota hết và reset sau 10 giờ. Có nên cho worker `Thread.sleep` 10 giờ?

Không. Ghi `nextAttemptAt` rồi nhả thread.

**Câu 8.** Làm sao để 100.000 marketing jobs không chặn reset password?

Dùng routing/purpose, priority lane, reserved capacity và fairness cùng global quota cap.

**Câu 9.** Token bucket 100/phút có đủ nếu provider giới hạn 4 connections đồng thời?

Chưa. Cần concurrency gate.

**Câu 10.** Hai SMTP user dưới cùng provider account có mặc định quota độc lập?

Không. Phải xác minh phạm vi quota của provider.

**Câu 11.** Chưa gọi SMTP nhưng local gate đã từ chối job. Có nên tăng SMTP attempt count?

Thông thường không; cần phân biệt local delay với một attempt thực tế.

**Câu 12.** `JavaMailSender.send` thành công có chứng minh email tới inbox?

Không. Cần theo dõi delivery/bounce riêng nếu nghiệp vụ yêu cầu.

## 32. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Email command / Business event"] --> B["Authorization + recipient policy"]
    B --> C["Durable outbox"]
    C --> D["Worker claim"]
    D --> E["Account/global quota"]
    E --> F["Tenant/purpose quota"]
    F --> G{"Có permit?"}
    G -->|"Không"| H["Reschedule / backpressure"]
    H --> D
    G -->|"Có"| I["Concurrency guard"]
    I --> J["JavaMailSender"]
    J --> K["SMTP provider"]
    K --> L{"Outcome"}
    L -->|"Accepted"| M["Mark submitted/sent"]
    L -->|"Temporary throttle"| N["Backoff + jitter"]
    L -->|"Permanent"| O["Dead + audit"]
    L -->|"Unknown"| P["Đối soát hoặc retry có kiểm soát"]
    N --> D
~~~

Những điều cần nhớ:

1. **Rate limit, quota, concurrency và deliverability là các khái niệm khác nhau.**
2. **Một provider có thể giới hạn theo nhiều phạm vi cùng lúc**: message, recipient, account, domain, IP, tenant và thời gian.
3. **Không có quota SMTP chung cho mọi provider**; phải xem hợp đồng và tín hiệu thực tế.
4. **`@Async`/thread pool không phải rate limiter**; SMTP vẫn blocking ở worker.
5. **Dùng outbox/queue và backpressure** để không làm mất job khi chờ quota.
6. **Cấp permit nguyên tử trên toàn cluster** khi nhiều instance dùng chung account.
7. **Kiểm soát cả tốc độ gửi và số kết nối đồng thời.**
8. **SMTP 4xx có thể tạm thời nhưng không phải mọi 4xx là throttling**; phân loại lỗi theo provider.
9. **HTTP 429/Retry-After thuộc HTTP API**, không tự xuất hiện trong SMTP.
10. **Retry có backoff, jitter và max attempts**, không busy-loop.
11. **Idempotency và outcome unknown** cần được thiết kế để giới hạn trùng khi retry/crash.
12. **Tách security/transactional khỏi bulk marketing**, nhưng vẫn tuân thủ global provider cap.
13. **Theo dõi quota, queue age, throttle, bounce và complaint**, không chỉ đếm `send` thành công.
14. **SMTP accepted chưa chắc delivered**, và quota còn không nghĩa thư sẽ vào inbox.

Trong Spring Framework Mail, `JavaMailSender` chịu trách nhiệm gửi MIME qua transport đã cấu hình. **Ứng dụng chịu trách nhiệm giữ nhịp gửi trong hạn mức provider**, lưu bền vững công việc khi cần, phân bổ công bằng giữa các loại email và xử lý lỗi với trạng thái chính xác. Khi rate limiter, outbox, retry và quan sát vận hành được kết hợp đúng cách, email giao dịch quan trọng sẽ ít bị ảnh hưởng bởi những đợt gửi hàng loạt, hệ thống giảm throttling và có nền tảng để cải thiện deliverability lâu dài.
