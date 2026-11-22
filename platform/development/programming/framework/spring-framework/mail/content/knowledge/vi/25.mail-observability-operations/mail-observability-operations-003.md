# Theo dõi queue, retry count và dead letter

## 1. Vì sao gửi mail thành công không đủ để vận hành hệ thống?

Trong một ứng dụng dùng **Spring Framework Mail**, `JavaMailSender` thực hiện việc tạo/kết nối và gửi email qua SMTP. Nếu HTTP request phải đợi SMTP, hệ thống dễ chậm khi nhà cung cấp mail phản hồi lâu. Vì vậy, email giao dịch thường được chuyển sang **queue, message broker hoặc transactional outbox** để xử lý bất đồng bộ.

Nhưng từ khi đưa email vào hàng đợi, một vấn đề mới xuất hiện: ứng dụng đã tiếp nhận yêu cầu gửi mà **người vận hành chưa chắc biết email có đang được xử lý, bị retry, bị kẹt hay đã rơi vào dead letter**.

Một số tình huống:

- Người dùng vừa đặt hàng nhưng email xác nhận chờ trong queue 20 phút.
- SMTP provider tạm từ chối kết nối; cùng một job được thử lại nhiều lần.
- Consumer chết giữa lúc xử lý khiến job ở trạng thái `PROCESSING` không được trả về queue.
- Mailbox không tồn tại: việc retry vô hạn chỉ làm tăng bounce và giảm sender reputation.
- Hệ thống liên tục ném lỗi template, nhưng phần mềm chỉ log từng exception mà không có trạng thái `FAILED` để xử lý.
- Queue depth gần bằng 0 nhưng email vẫn không gửi: worker đã lấy hết job rồi treo khi kết nối SMTP.
- Broker đã chấp nhận message, nhưng worker mất kết nối trước khi ack; message có thể được giao lại và gửi trùng.

Để xử lý được những tình huống này, cần theo dõi ít nhất ba khía cạnh:

1. **Queue:** Có bao nhiêu email đang chờ, đã đến hạn, đang xử lý và chờ bao lâu?
2. **Retry count:** Có bao nhiêu lượt thử đã xảy ra, vì sao thất bại, bao giờ thử tiếp, đã vượt giới hạn chưa?
3. **Dead letter:** Những job không thể tự phục hồi đang ở đâu, có lý do thất bại, bằng chứng và quy trình xử lý lại không?

Đây là bài học về **quan sát và vận hành** luồng gửi mail. Mục tiêu không chỉ là vẽ dashboard mà còn là định nghĩa số đo đúng, xây cảnh báo có thể hành động và tổ chức quy trình khôi phục an toàn.

> **Ranh giới kỹ thuật:** Spring Framework Mail không tự có một queue, retry store hay dead-letter queue tích hợp sẵn cho mọi ứng dụng. `JavaMailSender.send(...)` là API gửi; queue/outbox, retry, DLQ và metrics phải do ứng dụng hoặc hạ tầng như RabbitMQ/Kafka/database quản lý.

## 2. Kiến trúc tham chiếu

Một pipeline gửi email giao dịch có thể tổ chức:

~~~text
HTTP API / Business service
          |
          v
Database transaction
  +--> Save business state
  +--> Save mail_outbox(PENDING)
          |
          v
       COMMIT
          |
          v
Queue or outbox dispatcher
          |
          +--> Claim / consume job
          |
          v
Mail worker (PROCESSING)
          |
          +--> Render template / build MIME
          |
          +--> JavaMailSender.send(...)
          |
     +----+--------------------+
     |                         |
     v                         v
  Success                   Failure
     |                         |
     v                         v
  SENT/SMTP_ACCEPTED     Classify exception
                               |
                   +-----------+-------------+
                   |                         |
                   v                         v
               Retryable                Terminal / limit
                   |                         |
                   v                         v
            RETRY + nextAttemptAt        FAILED / DLQ
                   |                         |
                   v                         v
             Queue when due              Operator runbook
                   |                         |
                   +-------------+-----------+
                                 |
                                 v
                       Metrics / traces / alerts
~~~

**Queue** có thể là một bảng database được worker poll, một broker message queue hoặc kết hợp cả hai. Phương thức thu thập số liệu phải phản ánh đúng kiến trúc thực tế.

### 2.1. Các mốc cần phân biệt

| Mốc | Điều hệ thống biết | Có thể kết luận gì? |
| --- | --- | --- |
| Request accepted | API đã nhận yêu cầu | Chưa chắc job đã được lưu bền vững |
| Job persisted/enqueued | Outbox row hoặc broker message được xác nhận | Có một yêu cầu gửi chờ xử lý |
| Job claimed/delivered | Worker bắt đầu một attempt | Chưa chắc đã gọi SMTP |
| SMTP accepted | `JavaMailSender.send` trả về thành công | Relay SMTP chấp nhận message theo quan sát của ứng dụng |
| Retry scheduled | Hệ thống lưu `next_attempt_at` hoặc chuyển delay queue | Chưa gửi thành công; còn đường tự khắc phục |
| Dead-lettered | Hệ thống dừng retry tự động | Cần điều tra/khắc phục hoặc quyết định không gửi nữa |
| Provider delivered/bounced | Provider gửi feedback sau submission | Phản ánh một giai đoạn giao thư sau SMTP, không đồng nhất inbox |

Không nên dùng một metric duy nhất mang tên `mail_sent_total` rồi cộng cả trường hợp “job vừa được xếp hàng”. Các chỉ số phải có ý nghĩa và ranh giới rõ ràng.

## 3. Các trạng thái queue cần quan sát

Với mô hình outbox database, trạng thái thường là:

| Trạng thái | Ý nghĩa | Hành vi worker |
| --- | --- | --- |
| `PENDING` | Đã lưu job, chưa xử lý | Có thể claim khi đến hạn |
| `PROCESSING` | Worker đang giữ lease/claim token | Không claim lại khi lease còn hiệu lực |
| `RETRY` | Lỗi có thể thử lại, có thời điểm retry | Chỉ claim khi `next_attempt_at <= now()` |
| `SENT` | SMTP send hoàn tất thành công | Không xử lý tự động tiếp |
| `FAILED` | Dừng tự retry: permanent error, max attempts hoặc deadline | Giữ để điều tra/redrive |
| `UNKNOWN` (tùy chọn) | Không rõ SMTP đã chấp nhận hay chưa | Đối soát hoặc retry theo chính sách duplicate |
| `CANCELLED` (tùy chọn) | Nghiệp vụ hủy delivery | Không dispatch nữa |

Với RabbitMQ, các tên trạng thái vật lý khác: message **ready**, **unacked**, nằm trong **retry/delay queue**, hoặc được chuyển vào **dead-letter queue**. Với Kafka, việc theo dõi thường dựa trên **consumer lag, offset, retry topic và DLQ topic**, không phải queue depth theo nghĩa RabbitMQ.

### 3.1. Một job có thể xuất hiện qua nhiều tầng

Nếu ứng dụng lưu một outbox row và đồng thời publish tới broker:

~~~text
outbox PENDING/PROCESSING
        |
        v
broker ready/unacked
        |
        v
consumer processing
~~~

Không thể cộng thẳng số outbox rows và số broker messages để gọi là “tổng số email đang chờ”, vì **một delivery có thể đang có biểu diễn ở nhiều tầng**. Cần chọn một nguồn sự thật cho trạng thái delivery, còn số đo broker dùng để chẩn đoán hạ tầng.

### 3.2. Không nhầm hàng chờ rỗng với hệ thống khỏe

`queue_depth = 0` có thể xảy ra khi:

- Worker xử lý nhanh và thực sự không còn backlog.
- Worker đã claim hàng loạt job nhưng đang treo SMTP.
- Publisher/outbox relay đã lỗi và không đẩy job vào queue.
- Consumer ack quá sớm rồi làm mất job trước khi gửi.
- Hệ thống ngừng tạo event do upstream bị lỗi.

Do đó dashboard cần kết hợp **queue depth, in-flight jobs, oldest age, throughput, error rate và producer activity**.

## 4. Định nghĩa những chỉ số queue quan trọng

Một dashboard nên trả lời được “có bao nhiêu”, “đợi bao lâu” và “có đang tiến triển không”.

| Metric logic | Kiểu đo | Ý nghĩa |
| --- | --- | --- |
| `mail_queue_ready` | Gauge | Job đủ điều kiện và đang chờ worker |
| `mail_queue_delayed` | Gauge | Job chờ tới thời điểm retry hoặc scheduled send |
| `mail_queue_inflight` | Gauge | Job đã được claim/consumer nhận nhưng chưa có kết quả cuối |
| `mail_queue_oldest_ready_age_seconds` | Gauge | Tuổi của job đến hạn lâu nhất chưa được xử lý |
| `mail_queue_oldest_unfinished_age_seconds` | Gauge | Tuổi của job chưa hoàn tất lâu nhất |
| `mail_queue_enqueue_total` | Counter | Tổng số yêu cầu được ghi bền vững vào queue/outbox |
| `mail_queue_claim_total` | Counter | Tổng số lượt claim/bắt đầu xử lý |
| `mail_queue_complete_total` | Counter | Tổng số delivery đã hoàn tất theo loại kết quả |
| `mail_queue_claim_latency_seconds` | Timer/Histogram | Thời gian từ enqueue/eligible tới khi worker claim |
| `mail_dispatch_duration_seconds` | Timer/Histogram | Thời gian xử lý một attempt |
| `mail_worker_active` | Gauge | Worker đang xử lý |
| `mail_worker_heartbeat_age_seconds` | Gauge | Khoảng cách từ heartbeat gần nhất |

Không nhất thiết phải có tất cả metric ngay ngày đầu. Nhưng **depth mà không có age** khó phát hiện job bị đói (starvation); **age mà không có completion rate** khó biết hệ thống có đang cải thiện.

### 4.1. Ready khác delayed

Ví dụ tại 10:00:

~~~text
12 rows status=PENDING, next_attempt_at <= 10:00
18 rows status=RETRY, next_attempt_at <= 10:00
70 rows status=RETRY, next_attempt_at > 10:00
 4 rows status=PROCESSING, lease still valid
~~~

Có thể định nghĩa:

~~~text
ready   = 12 + 18 = 30
delayed = 70
inflight = 4
~~~

Nếu dashboard chỉ ghi tổng `PENDING + RETRY = 100`, người vận hành không biết có 30 job cần xử lý ngay và 70 job đang đợi lịch retry hợp lệ.

### 4.2. Oldest age và backlog growth

Giả sử worker xử lý 100 email/phút còn producer tạo 130 email/phút. Queue depth tăng 30/phút; nếu xu hướng kéo dài, thời gian đợi sẽ tăng dù không có exception.

Để phát hiện:

- Theo dõi tốc độ **enqueue** và **completion**.
- Theo dõi queue depth theo thời gian.
- Đo tuổi của delivery lâu nhất đang chờ và độ trễ p95/p99 từ enqueue tới completion.
- Quan sát số worker và giới hạn tốc độ provider.

Một ước lượng thô cho backlog drain time:

\[
T_{\mathrm{drain}} \approx
\frac{\mathrm{ready\ backlog}}{\mathrm{completion\ rate}-\mathrm{new\ arrival\ rate}}
\]

Chỉ dùng khi completion rate lớn hơn arrival rate và các tốc độ tương đối ổn định; không dùng công thức này để khẳng định thời gian hoàn thành chính xác trong hệ thống có retry, quota và batching.

## 5. Đo queue với transactional outbox trong PostgreSQL

Giả sử bảng `mail_outbox` có các cột:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    delivery_key VARCHAR(180) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    last_error_kind VARCHAR(30),
    last_failed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ
);

CREATE INDEX ix_mail_outbox_due
    ON mail_outbox (status, next_attempt_at);

CREATE INDEX ix_mail_outbox_lease
    ON mail_outbox (status, lease_until);
~~~

Đây là schema **tối giản để giải thích metrics**, không phải migration production đầy đủ. Trong hệ thống nhiều worker cần cơ chế atomic claim, claim token/version, unique idempotency key, retention và transaction boundaries phù hợp database. Với PostgreSQL, `FOR UPDATE SKIP LOCKED` là một cách chọn hàng đồng thời thường gặp.

### 5.1. Đếm ready, delayed, processing, failed

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status IN ('PENDING', 'RETRY')
          AND next_attempt_at <= now()
    ) AS ready_count,
    COUNT(*) FILTER (
        WHERE status IN ('PENDING', 'RETRY')
          AND next_attempt_at > now()
    ) AS delayed_count,
    COUNT(*) FILTER (
        WHERE status = 'PROCESSING'
          AND lease_until > now()
    ) AS inflight_count,
    COUNT(*) FILTER (
        WHERE status = 'PROCESSING'
          AND (lease_until <= now() OR lease_until IS NULL)
    ) AS expired_lease_count,
    COUNT(*) FILTER (
        WHERE status = 'FAILED'
    ) AS failed_count,
    COUNT(*) FILTER (
        WHERE status = 'UNKNOWN'
    ) AS unknown_count
FROM mail_outbox;
~~~

Query này cho một **snapshot tại thời điểm database thực thi**, không phải số lượng bất biến. Worker có thể claim hoặc hoàn tất job ngay sau đó, nên một dashboard không nên yêu cầu các biểu đồ từ những snapshot khác nhau phải cộng khớp từng mili-giây.

### 5.2. Tính tuổi job đến hạn lâu nhất

~~~sql
SELECT COALESCE(
    EXTRACT(EPOCH FROM (
        now() - MIN(next_attempt_at)
    )),
    0
) AS oldest_ready_age_seconds
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY')
  AND next_attempt_at <= now();
~~~

Đây là **tuổi quá hạn so với lịch `next_attempt_at`**. Nếu một email được lên lịch gửi ngày mai, nó không nên làm chỉ số “đang chờ quá lâu” hôm nay tăng lên.

Để quan sát độ tuổi kể từ lần enqueue ban đầu của những job chưa hoàn tất:

~~~sql
SELECT COALESCE(
    EXTRACT(EPOCH FROM (
        now() - MIN(created_at)
    )),
    0
) AS oldest_unfinished_age_seconds
FROM mail_outbox
WHERE status IN ('PENDING', 'PROCESSING', 'RETRY', 'UNKNOWN');
~~~

Chỉ số này có ý nghĩa khác: nó có thể tăng trong lúc job chờ retry hợp lệ. Nên hiển thị cả **oldest ready age** và **oldest unfinished age**, không dùng cùng tên cho hai phép tính.

### 5.3. Phát hiện lease đã hết hạn

~~~sql
SELECT id, attempt_count, lease_owner,
       lease_until, last_error_code
FROM mail_outbox
WHERE status = 'PROCESSING'
  AND (lease_until < now() OR lease_until IS NULL)
ORDER BY lease_until NULLS FIRST
LIMIT 100;
~~~

Một bản ghi `PROCESSING` quá hạn có thể do:

- Worker crash hoặc bị kill.
- SMTP transport treo vì timeout quá dài.
- Lease duration ngắn hơn p99 latency.
- Lỗi ghi trạng thái sau SMTP success.
- Worker không heartbeat hoặc database không nhận được update.

Không mặc định xóa hàng hoặc resend ngay. Cần cơ chế reclaim có kiểm soát, fencing token và hiểu duplicate window nếu SMTP có thể đã nhận email.

### 5.4. Lưu ý chi phí query

Trên bảng outbox lớn, `COUNT(*)` toàn bảng nhiều lần/giây có thể tạo áp lực database. Các phương án:

- Thu thập định kỳ với cadence hợp lý thay vì mỗi HTTP request.
- Dùng index/partial index phù hợp trạng thái và `next_attempt_at`.
- Partition/archive các hàng `SENT` cũ theo chính sách retention.
- Dùng counter/gauge được cập nhật từ event cho khối lượng rất lớn, kết hợp reconciliation định kỳ.
- Giới hạn số tenant/nhãn metric để tránh cardinality bùng nổ.

Query `COUNT(*) FILTER` cần kiểm thử trên phiên bản PostgreSQL và lượng dữ liệu thực tế; dashboard không được trở thành nguồn gây nghẽn mail queue.

## 6. Retry count: định nghĩa và cách đọc số liệu

**Retry count** thường dễ bị hiểu nhầm vì có ít nhất ba ý nghĩa:

1. **Số lượt thử của một delivery:** `attempt_count` trên outbox row.
2. **Số lần retry đã xảy ra:** `max(attempt_count - 1, 0)` nếu attempt đầu tiên được tính là lần gửi đầu.
3. **Số lần retry được lên lịch trong một khoảng thời gian:** counter `mail_retry_scheduled_total` tăng khi hệ thống commit quyết định retry.

Chúng không thay thế lẫn nhau. Nếu một job đang ở `RETRY` sau attempt #3, có thể mô tả:

~~~text
attempt_count = 3
completed attempt #1 = initial attempt
completed attempt #2 = retry 1
completed attempt #3 = retry 2
next_attempt_at = ...
~~~

Trên dashboard, đặt tên cột chính xác:

| Trường/metric | Đơn vị | Ví dụ |
| --- | --- | --- |
| `attempt_count` | Lượt dispatch đã claim | 3 |
| `retry_attempts_used` | Lượt dispatch sau attempt đầu | 2 |
| `max_attempts` | Giới hạn tổng số lượt | 5 |
| `mail_retry_scheduled_total` | Counter các quyết định retry đã được lưu | 1.256 kể từ khi counter được ghi nhận |
| `mail_retry_due_count` | Gauge số job RETRY đã đến hạn | 42 |
| `mail_retry_delayed_count` | Gauge số job RETRY chưa đến hạn | 87 |
| `mail_retry_exhausted_total` | Counter số job dừng do hết số lượt | 19 |

Không nên dùng metric counter tích lũy để hiển thị “hiện tại còn bao nhiêu job đang retry” mà không tính rate hoặc range. Counter tiếp tục tăng và có thể reset khi process restart; gauge biểu diễn số lượng tại thời điểm đo.

### 6.1. Đếm số lần thử theo phân bố

Một truy vấn dùng cho phân tích backlog/retry:

~~~sql
SELECT attempt_count, status, COUNT(*) AS deliveries
FROM mail_outbox
WHERE status IN ('PENDING', 'PROCESSING', 'RETRY', 'FAILED')
GROUP BY attempt_count, status
ORDER BY attempt_count, status;
~~~

Hoặc báo cáo tổng hợp:

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'RETRY'
    ) AS retry_jobs,
    COUNT(*) FILTER (
        WHERE status = 'RETRY'
          AND next_attempt_at <= now()
    ) AS retry_due_jobs,
    COUNT(*) FILTER (
        WHERE status = 'FAILED'
          AND attempt_count >= max_attempts
    ) AS failed_at_attempt_limit,
    COALESCE(MAX(attempt_count), 0) AS max_attempts_seen
FROM mail_outbox;
~~~

**Lưu ý:** `FAILED AND attempt_count >= max_attempts` chỉ cho biết các job đã chạm trần, không chứng minh tất cả thất bại **vì** trần. Một lỗi permanent có thể xảy ra đúng attempt cuối. Nếu muốn phân biệt chính xác, cần cột `terminal_reason` hoặc lịch sử sự kiện như `MAX_ATTEMPTS_EXHAUSTED`.

### 6.2. Attempt count phải tăng ở ranh giới xác định

Một quy ước dễ vận hành:

- Tăng `attempt_count` **một lần trong transaction claim** khi worker bắt đầu lượt dispatch.
- Lưu attempt history với `attempt_no`, `started_at`, `claim_token` và `worker_id`.
- Khi send thành công hoặc lỗi, hoàn tất attempt record với outcome.
- Nếu process chết, attempt có thể còn `STARTED`; nó là dấu vết cần đối soát, không tự kết luận SMTP đã nhận hay chưa.

~~~text
Claim transaction:
  outbox.attempt_count += 1
  outbox.status = PROCESSING
  INSERT mail_attempt(outcome=STARTED)
  COMMIT
                 |
                 v
       JavaMailSender.send
                 |
            +----+----+
            |         |
            v         v
         Success     Exception
            |         |
            v         v
      mark SENT    mark RETRY/FAILED/UNKNOWN
            |         |
            +----+----+
                 |
                 v
       Commit outcome + attempt history
~~~

Đừng tăng counter chỉ trong `catch (MailException)`. Nếu worker chết sau claim nhưng trước `catch`, lần xử lý đó có thể không được đếm, khiến số lần dispatch thực tế sai lệch.

### 6.3. Lịch sử attempt quan trọng hơn một counter đơn lẻ

Ví dụ bảng `mail_delivery_attempt`:

~~~sql
CREATE TABLE mail_delivery_attempt (
    id UUID PRIMARY KEY,
    outbox_id UUID NOT NULL REFERENCES mail_outbox(id),
    attempt_no INT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(40) NOT NULL DEFAULT 'STARTED',
    failure_kind VARCHAR(30),
    failure_stage VARCHAR(50),
    error_code VARCHAR(100),
    safe_summary VARCHAR(400),
    worker_id VARCHAR(100),
    UNIQUE (outbox_id, attempt_no)
);

CREATE INDEX ix_mail_attempt_error_code
    ON mail_delivery_attempt(error_code, started_at);
~~~

Một timeline hữu ích:

| Attempt | Thời gian | Kết quả | Mã lỗi |
| --- | --- | --- | --- |
| #1 | 10:00:01 | `RETRYABLE_FAILURE` | `SMTP_CONNECTION_TIMEOUT` |
| #2 | 10:01:02 | `RETRYABLE_FAILURE` | `SMTP_SERVER_BUSY` |
| #3 | 10:03:06 | `SMTP_ACCEPTED` | — |

Outbox ở trạng thái `SENT` với `attempt_count = 3`; lịch sử vẫn cho thấy có hai lượt lỗi trước khi thành công. Nếu chỉ giữ `last_error_code` trên row outbox rồi xóa khi gửi thành công, phần lịch sử phục vụ điều tra sẽ mất đi.

### 6.4. Retry schedule và retry execution là hai metric khác nhau

Khi một attempt thất bại và được chuyển `RETRY`, tăng:

~~~text
mail_retry_scheduled_total{reason="smtp_temporary"}
~~~

Khi worker thật sự claim lại một job đã từng có attempt, tăng:

~~~text
mail_retry_started_total{trigger="due"}
~~~

Hai counter có thể khác nhau do lịch retry trong tương lai, job bị hủy hoặc instance shutdown. Không lấy số `scheduled` rồi coi đó là số lần SMTP đã được gọi lại.

## 7. Phân loại lỗi để retry count có ý nghĩa

Một job có retry nhiều chưa đủ để biết cần hành động gì. Cần phân loại **nguyên nhân** và **giai đoạn**:

| Lỗi | Ví dụ | Chiến lược thường gặp |
| --- | --- | --- |
| Chuẩn bị template/MIME | Thiếu template, dữ liệu không hợp lệ | Thường terminal; sửa code/dữ liệu |
| Xác thực SMTP | `MailAuthenticationException` | Dừng retry dồn dập; kiểm tra secret/provider policy |
| Kết nối SMTP tạm lỗi | Connection refused, network outage | Retry sau backoff |
| Provider rate limit | SMTP temporary response, quota | Backoff và giảm throughput |
| Recipient bị từ chối vĩnh viễn | Địa chỉ không tồn tại | Terminal/suppression sau xác minh |
| SMTP kết quả mơ hồ | Timeout sau khi DATA đã truyền | `UNKNOWN`/đối soát hoặc retry có duplicate policy |
| Worker/executor lỗi | Task rejected, worker bị kill | Khôi phục capacity, reclaim có điều kiện |
| Database không ghi được kết quả | SMTP accepted nhưng `markSent` thất bại | Báo state-write failure; không tự coi SMTP failed |

Trong Spring Mail:

- `MailAuthenticationException` cho thấy lỗi authentication.
- `MailSendException` có thể bọc nhiều loại lỗi transport/message, không phải mọi trường hợp đều transient.
- `MailPreparationException` và `MailParseException` thường liên quan tới chuẩn bị/parsing.
- `MailException` là lớp cơ sở, chưa đủ để quyết định retry.
- `jakarta.mail.MessagingException` có thể xảy ra khi dựng `MimeMessage` hoặc trong các thao tác Jakarta Mail.

Một classifier nên trả về dữ liệu có cấu trúc:

~~~java
public enum FailureKind {
    TRANSIENT, PERMANENT, UNKNOWN
}

public record FailureDecision(
        FailureKind kind,
        String errorCode,
        String stage,
        String safeSummary) {
}
~~~

Không đưa nguyên `exception.getMessage()` vào metric label hoặc dashboard mà chưa kiểm soát dữ liệu nhạy cảm. Nested SMTP exception có thể chứa địa chỉ email, tên host hoặc các thông tin chi tiết khác.

### 7.1. Soft failure chưa chắc cần application retry

Cần phân biệt:

1. **SMTP submission chưa được chấp nhận:** ứng dụng có thể retry delivery nếu lỗi rõ ràng.
2. **SMTP relay đã chấp nhận và đang thử giao:** provider có thể tự retry; ứng dụng không nên tạo email mới khi chỉ nhận feedback `DEFERRED`.
3. **Provider báo final soft bounce:** policy nghiệp vụ mới quyết định có tạo delivery khác hay không.

Không gộp tất cả vào `mail_retry_total` rồi hiểu là “cứ gặp 4xx thì gửi lại”. Retry của provider sau SMTP accepted và retry của outbox trước accepted là hai vòng khác nhau.

### 7.2. Backoff, jitter và tuổi hàng chờ

Một chính sách retry minh họa:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Với `d_0 = 30 giây` và `max_attempts = 5`:

| Attempt thất bại | Delay cơ sở sau lỗi | Quyết định |
| --- | --- | --- |
| 1 | 30 giây | RETRY nếu transient |
| 2 | 60 giây | RETRY |
| 3 | 120 giây | RETRY |
| 4 | 240 giây | RETRY |
| 5 | — | FAILED/dead letter nếu đã hết lượt |

Jitter giúp các worker không cùng retry vào một thời điểm gây “retry storm”. Ngưỡng delay thực tế phụ thuộc SLA, loại email, quota provider và business deadline. Email chứa token xác minh 10 phút không nên được gửi lại sau khi token đã hết hạn.

Khi đo queue age, **delayed retry** phải có chỉ số riêng; không cảnh báo “ready backlog quá lâu” cho job chưa tới `next_attempt_at`.

## 8. Dead letter là gì?

**Dead-letter queue (DLQ)** là nơi nhận những message mà consumer/hệ thống không thể xử lý theo chính sách tự động nữa. Trong mô hình database, chức năng tương tự có thể là:

- Bản ghi outbox với `status = FAILED`.
- Bảng `mail_dead_letter` hoặc `mail_failure_archive` riêng.
- Broker queue/topic tên `mail.dead-letter` / `mail.dlq`.

Điểm chung: các delivery này **không tiếp tục retry tự động**, nhưng vẫn được giữ để điều tra, giải quyết nguyên nhân và redrive có kiểm soát.

### 8.1. Những nguyên nhân thường dẫn tới dead letter

- Hết `max_attempts`.
- Lỗi template hoặc dữ liệu không thể tự khắc phục.
- SMTP authentication thất bại kéo dài do credential sai.
- Recipient/domain bị từ chối vĩnh viễn.
- Payload không parse được hoặc vi phạm schema.
- Hết hạn nghiệp vụ: email không còn giá trị.
- Retry vẫn không thành công sau circuit breaker/recovery window.
- Operator chủ động chuyển job sang trạng thái terminal.

Không phải mọi lỗi đều nên được tự động redrive sau khi đã vào DLQ. Một email xác minh đã hết hạn nếu phát lại có thể gây nhầm lẫn hoặc tạo liên kết không còn hoạt động.

### 8.2. Dead letter khác lost message

| Trạng thái | Có dấu vết bền vững? | Có thể điều tra? |
| --- | --- | --- |
| RETRY | Có, job đang được lên lịch lại | Có |
| FAILED/DLQ | Có, job đang chờ hành động rõ ràng | Có |
| UNKNOWN | Có, kết quả SMTP cần đối soát | Có nếu lưu evidence |
| Lost message | Không còn job/event cần gửi | Khó hoặc không thể |

Một hệ thống tốt không “giấu” lỗi bằng cách bắt exception rồi bỏ job, nhưng cũng không “che” lỗi bằng retry vô hạn. **Dead letter là tín hiệu để khôi phục có quy trình**.

### 8.3. Trường dữ liệu cần có trong dead-letter record

| Trường | Vai trò |
| --- | --- |
| `delivery_id` | Định danh delivery trong hệ thống |
| `business_event_id` / `delivery_key` | Liên hệ nghiệp vụ, phục vụ idempotency |
| `failed_at` | Thời điểm terminal |
| `attempt_count` và `max_attempts` | Hiểu số lần đã thử |
| `terminal_reason` | Vì sao dừng tự retry |
| `last_error_code` / `failure_kind` | Nguyên nhân đã chuẩn hóa |
| `failure_stage` | Bước gây lỗi: MIME, SMTP, state update... |
| `next_action` (tùy chọn) | Cần sửa template, rotate credential, xem lại địa chỉ... |
| `safe_summary` | Thông tin chẩn đoán không chứa secret |
| `created_at` / `updated_at` | Audit timeline |
| `owner/worker` hoặc correlation | Điều tra log/trace |

Không tự động lưu nguyên exception object, toàn bộ MIME body hoặc SMTP password trong dead letter. Payload có thể chứa email, token, thông tin khách hàng; cần retention và quyền truy cập chặt chẽ.

## 9. Dead letter trong outbox database

Nếu queue chính là bảng `mail_outbox`, cách đơn giản là chuyển status sang `FAILED`:

~~~sql
UPDATE mail_outbox
SET status = 'FAILED',
    last_error_code = :error_code,
    last_error_kind = :failure_kind,
    last_failed_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :outbox_id
  AND status = 'PROCESSING'
  AND lease_owner = :worker_id;
~~~

Đây là SQL **minh họa trạng thái terminal**. Trong hệ thống concurrent, nên kiểm tra thêm `claim_token`/version và số hàng update, vì một worker mất lease không được ghi đè quyết định của worker mới.

### 9.1. Dùng terminal reason riêng

Ví dụ hai lỗi:

~~~text
Delivery A:
  last_error_code = SMTP_TEMPORARY_UNAVAILABLE
  last_error_kind = TRANSIENT
  terminal_reason = MAX_ATTEMPTS_EXHAUSTED

Delivery B:
  last_error_code = TEMPLATE_MISSING_FIELD
  last_error_kind = PERMANENT
  terminal_reason = NON_RETRYABLE_FAILURE
~~~

Cả hai đều `FAILED` nhưng **nguyên nhân vận hành khác nhau**. Không nên ghi `last_error_kind=PERMANENT` cho delivery A chỉ vì đã hết retry; lỗi gần nhất vẫn transient, còn chính sách dừng do số lượt thử.

Nếu cần lưu `terminal_reason`, thêm cột hoặc bảng event tương ứng vào schema. Không trộn hai khái niệm error class và terminal state.

### 9.2. Đếm dead letter và theo dõi tăng trưởng

~~~sql
SELECT
    COALESCE(last_error_code, 'UNKNOWN') AS error_code,
    COUNT(*) AS failed_jobs
FROM mail_outbox
WHERE status = 'FAILED'
GROUP BY COALESCE(last_error_code, 'UNKNOWN')
ORDER BY failed_jobs DESC;
~~~

Với lịch sử attempt, có thể thống kê số job **mới vào FAILED trong 15 phút** thay vì chỉ nhìn tổng tích lũy. Nếu bảng chỉ có `last_failed_at`, cần hiểu timestamp đó có thể là lần gửi lỗi gần nhất, không nhất thiết là thời điểm chuyển trạng thái terminal. Tốt hơn có `failed_at` hoặc một event transition.

Một dashboard nên hiển thị cả:

- **Current DLQ depth:** hiện có bao nhiêu job terminal chưa được xử lý.
- **New DLQ arrivals:** bao nhiêu job mới rơi vào dead letter mỗi khoảng thời gian.
- **DLQ oldest age:** job terminal lâu nhất chưa được triage.
- **DLQ by cause:** loại lỗi, template, provider.
- **Redrive success/failure:** bao nhiêu job sau khi xử lý nguyên nhân được khôi phục thành công.

## 10. Dead-letter queue trong RabbitMQ và hệ thống broker

Nếu ứng dụng dùng RabbitMQ, có thể cấu hình **dead-letter exchange (DLX)**. Broker đưa message tới DLX trong các trường hợp như bị reject/nack không requeue, TTL hết hoặc các điều kiện dead-lettering theo phiên bản/chính sách broker.

Ví dụ đường đi:

~~~text
mail.work queue
    |
    +--> Consumer ack success -> complete
    |
    +--> Transient failure -> retry policy
    |       |
    |       +--> Delayed/retry queue (TTL/backoff)
    |               |
    |               +--> Re-route to mail.work
    |
    +--> Terminal failure / retries exhausted
            |
            v
       DLX routing
            |
            v
       mail.dead-letter queue
            |
            v
        Operator / redrive service
~~~

Các thành phần `mail.work`, `mail.retry` và `mail.dead-letter` chỉ là tên ví dụ. Spring AMQP cung cấp các abstraction như listener, queue/exchange binding và error handling, nhưng **không phải Spring Mail tự sinh DLQ** chỉ vì ứng dụng đã thêm `spring-boot-starter-mail`.

### 10.1. Ack, nack, requeue: tránh vòng lặp vô hạn

Trong consumer broker:

- **Ack sau khi hoàn tất công việc theo hợp đồng** để broker không redeliver vô cớ.
- **Nack/reject có requeue** khi policy cho phép thử lại, nhưng không nên requeue tức thì vô hạn.
- **Nack/reject không requeue** khi muốn broker dead-letter theo DLX đã cấu hình.
- **Đừng ack trước khi đã lưu kết quả cần thiết**, nếu không process crash có thể làm mất dấu vết xử lý.

Nếu luôn `requeue=true` cho một lỗi permanent, cùng một message có thể được lấy lại liên tục và tiêu tốn CPU/network, không bao giờ đi vào DLQ.

### 10.2. Retry counter trong broker không phải attempt counter nghiệp vụ

Một broker có thể cung cấp header redelivery, dead-letter history hoặc metadata tương tự (ví dụ RabbitMQ `x-death` trong các đường dead-lettering). Nhưng:

- Redelivery có thể xảy ra do consumer disconnect, chưa chắc `JavaMailSender.send` đã được gọi.
- Một message có thể đi qua nhiều exchange/queue retry.
- Header có thể thay đổi theo broker, policy và cách republish.
- Khi ứng dụng republish message mới, metadata gốc có thể không được giữ nếu không chủ động copy.

Nếu cần biết chính xác số **lượt dispatch của một delivery**, nên lưu attempt history/idempotency state trong cơ sở dữ liệu hoặc nguồn sự thật bền vững được kiểm soát, thay vì chỉ dựa vào `redelivered=true`.

### 10.3. Kafka DLQ là pattern ở tầng ứng dụng

Kafka thường có consumer lag và offset; “DLQ” thường là **một topic riêng** mà consumer hoặc framework routing đưa record thất bại vào sau khi hết retry.

Các vấn đề cần tính:

- Khi nào commit consumer offset?
- Ghi DLQ record đã bền vững chưa trước khi bỏ record gốc?
- Topic retry dùng delay/backoff như thế nào?
- Có bảo đảm cùng key/order khi xử lý lại không?
- Cần retention, ACL và mã hóa payload DLQ ra sao?

Không mô tả Kafka consumer lag là “số email chưa gửi” tuyệt đối: cùng một topic có thể chứa nhiều event type, partition có offset, hoặc delivery đã chuyển sang retry topic/DLQ.

### 10.4. Một nguồn sự thật cho delivery

Trong hệ thống dùng outbox + broker, nên quyết định:

~~~text
Business delivery state -> database/outbox record
Broker queue depth      -> infrastructure backlog
Attempt history         -> dispatch execution
Dead letter event       -> terminal outcome
~~~

Sử dụng broker metrics để chẩn đoán nhanh capacity, kết hợp application metrics/database để trả lời **email nào đã được gửi, email nào cần retry và email nào đã thất bại cuối**.

## 11. Thu thập metrics với Micrometer và Spring Boot Actuator

Spring Boot tích hợp **Micrometer** để đo counter, gauge, timer và phân phối metrics tới hệ giám sát như Prometheus. Đối với queue/outbox, cần phân biệt:

- **Gauge:** số lượng hiện tại tại thời điểm scrape: ready, delayed, in-flight, failed.
- **Counter:** tổng sự kiện xảy ra: claim, retry scheduled, attempt failed, dead-letter arrived.
- **Timer/Histogram:** latency và duration: enqueue-to-claim, dispatch time, time-to-SMTP-accepted.
- **Long task / heartbeat:** worker có còn xử lý, có đang quá thời gian hay không?

Ví dụ dependency Maven ở mức khái niệm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Các phiên bản nên do BOM phù hợp của Spring Boot quản lý. Không trộn tùy tiện các bản Micrometer không tương thích với Spring Boot của dự án.

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      show-details: when-authorized

app:
  mail:
    metrics:
      refresh-ms: 30000
~~~

Endpoint Prometheus thường ở `/actuator/prometheus` khi dependency và cấu hình hỗ trợ. **Không nên expose endpoint quản trị công khai**: bảo vệ bằng network policy, authentication/authorization, ingress nội bộ và nguyên tắc quyền tối thiểu.

### 11.1. Ghi counter khi attempt kết thúc

Một lớp đo metrics cho worker:

~~~java
package com.example.mail.ops;

import java.time.Duration;
import java.util.concurrent.Callable;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class MailDispatchMeters {

    private final MeterRegistry registry;

    public MailDispatchMeters(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordAttemptOutcome(
            String outcome,
            String failureKind,
            String errorCode) {

        Counter.builder("mail.dispatch.attempts")
                .description("Completed mail dispatch attempts")
                .tag("outcome", outcome)
                .tag("failure_kind", failureKind)
                .tag("error_code", errorCode)
                .register(registry)
                .increment();
    }

    public void recordDispatchDuration(
            Duration duration, String outcome) {

        Timer.builder("mail.dispatch.duration")
                .description("Mail dispatch attempt duration")
                .tag("outcome", outcome)
                .register(registry)
                .record(duration);
    }
}
~~~

Ví dụ dùng giá trị label được chuẩn hóa:

~~~text
outcome = smtp_accepted | retry | failed | unknown
failure_kind = transient | permanent | unknown | none
error_code = smtp_timeout | smtp_auth | mime_invalid | none
~~~

Trong production:

- Không truyền giá trị tự do từ exception message vào `error_code`.
- Giữ danh mục tag **hữu hạn**: không dùng recipient, delivery ID, UUID hoặc nguyên SMTP response làm tag.
- Counter in-memory có thể mất một số event khi process chết; metrics không thay thế attempt history/outbox state trong database.
- Khi dùng nhiều instance, Prometheus tổng hợp counter theo instance và window; chú ý restart/reset.

**Lưu ý:** Đừng đo “attempt thành công” ngay sau khi `JavaMailSender.send` ném/không ném mà bỏ qua trạng thái kết quả. Có thể dùng hai metric riêng: một metric về **SMTP result** (transport returned successfully) và một metric về **state persistence result** (đã commit `SENT`). Nếu cập nhật database thất bại sau SMTP acceptance, hai tín hiệu sẽ khác nhau và đó là thông tin vận hành quan trọng.

### 11.2. Gauge queue depth từ snapshot database

Với outbox được lưu trong PostgreSQL, có thể lấy số liệu định kỳ rồi đưa vào một đối tượng chứa gauge:

~~~java
package com.example.mail.ops;

import java.util.concurrent.atomic.AtomicLong;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class MailQueueGauges {

    private final AtomicLong ready = new AtomicLong();
    private final AtomicLong delayed = new AtomicLong();
    private final AtomicLong inflight = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();
    private final AtomicLong oldestReadyAgeSeconds = new AtomicLong();

    public MailQueueGauges(MeterRegistry registry) {
        Gauge.builder("mail.queue.ready", ready, AtomicLong::doubleValue)
                .register(registry);
        Gauge.builder("mail.queue.delayed", delayed, AtomicLong::doubleValue)
                .register(registry);
        Gauge.builder("mail.queue.inflight", inflight, AtomicLong::doubleValue)
                .register(registry);
        Gauge.builder("mail.deadletter.current", failed, AtomicLong::doubleValue)
                .register(registry);
        Gauge.builder("mail.queue.oldest.ready.age.seconds",
                oldestReadyAgeSeconds, AtomicLong::doubleValue)
                .register(registry);
    }

    public void update(MailQueueSnapshot value) {
        ready.set(value.ready());
        delayed.set(value.delayed());
        inflight.set(value.inflight());
        failed.set(value.failed());
        oldestReadyAgeSeconds.set(value.oldestReadyAgeSeconds());
    }
}

public record MailQueueSnapshot(
        long ready,
        long delayed,
        long inflight,
        long failed,
        long oldestReadyAgeSeconds) {
}
~~~

Khi đưa vào dự án Java, `public record MailQueueSnapshot` phải nằm ở file riêng theo quy tắc Java. Cách viết này minh họa **giữ strong reference tới `AtomicLong`** để gauge đọc được đối tượng ổn định; không tạo một gauge mới có tag `deliveryId` mỗi lần queue thay đổi.

Một scheduler/collector riêng có thể chạy SQL ở phần trước theo nhịp 30–60 giây:

~~~java
@Component
public class MailQueueSnapshotCollector {

    private final MailQueueSnapshotRepository repository;
    private final MailQueueGauges gauges;

    public MailQueueSnapshotCollector(
            MailQueueSnapshotRepository repository,
            MailQueueGauges gauges) {
        this.repository = repository;
        this.gauges = gauges;
    }

    @Scheduled(fixedDelayString =
            "${app.mail.metrics.refresh-ms:30000}")
    public void refresh() {
        MailQueueSnapshot snapshot = repository.readSnapshot();
        gauges.update(snapshot);
    }
}
~~~

Ví dụ giả định ứng dụng đã bật `@EnableScheduling` và có repository đọc snapshot. Trong triển khai thật, collector cần xử lý database outage: **không ghi tất cả gauge bằng 0 nếu query thất bại** vì như vậy dashboard sẽ báo giả “queue đã trống”. Nên giữ snapshot trước, ghi metric `mail_queue_snapshot_refresh_failure_total` và timestamp lần thu thập thành công để phân biệt số liệu bị stale.

### 11.3. Counter và gauge có thể không khớp tức thời

Giả sử counter `mail.retry.scheduled` tăng ngay khi worker đã quyết định retry, nhưng transaction DB rollback. Dashboard có thể ghi thêm một retry chưa được lưu. Nếu muốn metric phản ánh **quyết định đã commit**, hãy tăng sau khi transaction thành công hoặc xây metrics từ committed outbox events.

Ngay cả khi tăng sau commit, process vẫn có thể crash trước khi counter tăng. **Database/event log là nguồn audit bền vững; Micrometer metrics là nguồn quan sát vận hành**. Không đặt điều kiện tài chính/tuân thủ dựa duy nhất vào counter của process.

### 11.4. SMTP timing cần đo gì?

Thời gian từ claim đến SMTP accepted nên được tách nếu có thể:

~~~text
Enqueue wait time
  created_at -> claimed_at

Message preparation time
  render start -> MIME built

SMTP transport duration
  send start -> send return/error

State update duration
  result commit start -> commit complete

Total end-to-end time
  created_at -> SENT commit
~~~

Nếu `send` rất nhanh nhưng end-to-end latency cao, vấn đề có thể là queue backlog; nếu queue gần như trống nhưng `send` chậm, cần kiểm tra network/provider/timeouts. Một timer tổng hợp duy nhất sẽ khó xác định nguyên nhân.

## 12. Prometheus/Grafana: biểu đồ cần hiển thị

Khi Micrometer xuất metric ra Prometheus, tên với dấu chấm thường được chuyển thành dấu gạch dưới và counter thường có hậu tố `_total`. **Tên chính xác phụ thuộc registry/convention và phiên bản**; kiểm tra nội dung `/actuator/prometheus` trước khi viết PromQL.

Một dashboard vận hành có thể chia làm bốn vùng:

### 12.1. Queue health

| Biểu đồ | Câu hỏi |
| --- | --- |
| Ready depth | Có bao nhiêu email cần worker xử lý ngay? |
| Delayed/retry depth | Bao nhiêu email đang chờ retry hợp lệ? |
| In-flight / unacked | Worker có đang giữ nhiều job quá lâu không? |
| Oldest ready age | Email đến hạn lâu nhất đã đợi bao lâu? |
| Enqueue vs completed rate | Backlog đang tăng hay giảm? |
| Worker active / heartbeat | Có worker còn sống và đang tiến triển không? |

PromQL mẫu (giả định metric được export với tên tương ứng):

~~~promql
# Số job đang chờ tại thời điểm scrape
sum(mail_queue_ready)

# Tuổi quá hạn lớn nhất trong các instance/service
max(mail_queue_oldest_ready_age_seconds)

# Số job worker đang xử lý
sum(mail_queue_inflight)
~~~

Nếu mỗi instance đều query **cùng một database** để cập nhật gauge toàn cục, `sum(mail_queue_ready)` sẽ **đếm trùng** theo số replica. Khi đó cần lấy `max` theo nhóm/queue, dùng collector duy nhất hoặc tạo recording rule chọn một nguồn authoritative. Không áp dụng công thức tổng hợp cho gauge database global khi chưa xác định scope.

### 12.2. Retry health

| Biểu đồ | Ý nghĩa |
| --- | --- |
| Retry scheduled rate | Hệ thống đang lên lịch retry với tốc độ nào? |
| Retry started rate | Bao nhiêu retry thực sự được worker thực hiện? |
| Retryable failure rate | SMTP/provider có đang gặp sự cố tạm thời? |
| Attempts per delivery | Bao nhiêu email cần nhiều lượt? |
| Retry exhaustion rate | Có bao nhiêu delivery chạm giới hạn? |
| Next-attempt overdue | Có job retry đến hạn nhưng không được xử lý? |

Ví dụ PromQL (đặt tên theo convention đã xác minh):

~~~promql
sum by (error_code) (
  rate(mail_dispatch_attempts_total{outcome="retry"}[5m])
)

sum(
  increase(mail_retry_exhausted_total[1h])
)
~~~

Một sự tăng của retry rate không tự chứng minh lỗi mạng. Cần xem `error_code` và provider: nếu `smtp_auth` tăng đồng loạt, phải sửa credential hoặc cấu hình thay vì tăng max attempts.

### 12.3. Dead-letter health

| Biểu đồ | Hành động vận hành |
| --- | --- |
| DLQ current depth | Có còn nhiều job chờ triage? |
| New DLQ arrivals by error code | Có sự cố mới hay lỗi cũ tái phát? |
| Oldest dead-letter age | Có ticket/sự cố bị bỏ quên? |
| Redrive attempts/success/failure | Việc khôi phục có hiệu quả không? |
| Terminal reasons | Thất bại do max attempts hay permanent? |

Ví dụ:

~~~promql
# Số job FAILED còn nằm ở dead-letter area
max(mail_deadletter_current)

# Tốc độ phát sinh dead letter theo loại lỗi
sum by (reason) (
  rate(mail_deadletter_arrivals_total[15m])
)
~~~

Các tên metric trong ví dụ là một **đề xuất instrumentation**. Cần export counter `mail.deadletter.arrivals` từ application hoặc broker adapter tương ứng trước khi sử dụng PromQL. Một dashboard không nên hiển thị đường số 0 giả nếu metric thực tế chưa được xuất.

### 12.4. SMTP health

Nên tách biểu đồ:

- SMTP accepted per minute.
- SMTP authentication failures.
- Transport timeout/connect errors.
- SMTP send duration p95/p99.
- Provider/relay-specific rate limit errors.
- Message preparation failures.
- Database state-update failures sau SMTP acceptance.

Nếu provider cung cấp delivery/bounce events, hãy tạo dashboard **deliverability** riêng. SMTP accepted rate không bằng delivered rate; queue monitoring không thay thế bounce/complaint tracking.

## 13. Thiết kế cảnh báo có thể hành động

Một hệ thống gửi email có thể có queue depth tăng trong các đợt cao điểm mà vẫn đang xử lý đúng SLA. Vì vậy, chỉ cảnh báo khi “queue_depth > 100” có thể gây nhiều báo động giả.

Hãy ưu tiên **tuổi hàng đến hạn, khả năng tiến triển, lỗi terminal và tốc độ lỗi có ý nghĩa**.

| Tín hiệu | Ví dụ điều kiện | Cần kiểm tra |
| --- | --- | --- |
| Oldest ready age vượt SLA | Job đến hạn lâu nhất chờ quá 5 phút | Worker availability, provider throttle, backlog |
| Ready backlog tăng liên tục | Queue depth tăng trong 15 phút | Enqueue vs completion rate, capacity |
| No progress | Có ready jobs nhưng completion = 0 trong 10 phút | Worker hang, scheduler, queue consumer |
| Expired lease | Nhiều `PROCESSING` quá hạn | Crash, SMTP timeout, lease duration |
| Auth failure spike | Lỗi auth tăng đột ngột | Secret rotation, tài khoản SMTP, provider policy |
| Retry exhaustion | Số job mới vào `FAILED` tăng | Loại lỗi, max attempts, network/provider |
| Dead letter lâu chưa xử lý | Oldest DLQ age vượt policy | Triage, owner, ticket |
| UNKNOWN result | Có job không rõ SMTP đã accepted | Duplicate risk, database failure, reconciliation |
| Metrics freshness | Không có snapshot mới hoặc scrape thất bại | Monitoring collector/DB access |

Các ngưỡng “5 phút”, “10 phút” và “15 phút” chỉ để minh họa. Phải căn cứ vào **SLO của từng loại email**. Email reset password có thời gian hữu dụng ngắn khác hóa đơn hàng tháng hoặc newsletter.

### 13.1. SLO theo loại email

Ví dụ một SLO nội bộ:

~~~text
Transactional email:
  99% of accepted requests reach SMTP_ACCEPTED
  within 2 minutes, excluding provider-wide incident policy.

Password reset:
  99% of eligible jobs are submitted within 30 seconds,
  with expiry-aware handling.
~~~

Đây là giả định minh họa; không có SLO mặc định cho Spring Mail. Khi đo, phải xác định:

- “Request accepted” có nghĩa job đã được lưu bền vững hay chỉ nhận HTTP?
- Mốc hoàn tất là SMTP accepted hay provider delivered?
- Deadline nằm ở lúc request đến, lúc transaction commit hay lúc job đến hạn?
- Job bị suppress/cancel có được tính vào mẫu số không?
- Hệ thống có xử lý lịch gửi trong tương lai không?

Một SLO tốt gắn với trải nghiệm thực tế, tránh đánh đồng “worker không có exception” với “người dùng đã nhận thư”.

### 13.2. Cảnh báo theo tốc độ và tỷ lệ

Một tỷ lệ lỗi:

\[
\mathrm{failureRate} =
\frac{\mathrm{failed\ attempts\ in\ window}}
{\mathrm{completed\ attempts\ in\ window}}
\]

Nếu chỉ có 1 attempt trong 5 phút và nó thất bại, tỷ lệ = 100% nhưng mức độ nghiêm trọng khác với 10.000 attempt đều thất bại. Alert cần **minimum traffic floor** hoặc số lỗi tuyệt đối kết hợp tỷ lệ.

Ví dụ:

~~~text
Alert if:
  auth_failures >= 10 over 5 minutes
  AND auth_failure_rate > 20%
  AND environment = production
~~~

Với lỗi nghiêm trọng và có ý nghĩa cao như secret leakage hoặc không có worker nào sống, có thể alert ngay theo trạng thái hệ thống mà không cần volume lớn.

### 13.3. Không đánh thức trực ca vì mọi job FAILED

Một địa chỉ email không tồn tại có thể tạo một job `FAILED` hợp lệ, không nhất thiết là incident cần gọi trực ca. Hệ thống nên phân biệt:

- Lỗi cá biệt cần xử lý qua ticket hoặc quy trình xác minh địa chỉ.
- Lỗi tăng hàng loạt do SMTP auth/TLS/network làm ảnh hưởng nhiều tenant.
- DLQ growth đột biến sau deploy, có thể là regression của template.
- Job bảo mật/hóa đơn quá deadline, có ảnh hưởng người dùng rõ ràng.

Phân cấp severity theo **mức tác động**, không chỉ theo tên exception.

## 14. Theo dõi producer, worker và broker cùng lúc

Quan sát end-to-end cần thấy cả phía tạo job và phía tiêu thụ:

~~~text
Producer                                Worker
   |                                      |
   +-- enqueue_total                      +-- claim_total
   |                                      |
   +-- enqueue_error_total                +-- active_workers
   |                                      |
   +-- business_event_to_enqueue_time     +-- send_success_total
                                          |
                                          +-- send_failure_total
                                          |
                                          +-- state_update_failure_total
                                          |
                                          +-- heartbeat / last_success_time
                          |
                          v
                      Queue/Broker
                       ready
                       delayed
                       inflight
                       dead letter
~~~

Một tình huống như “ready queue trống, completion rate = 0” chỉ có ý nghĩa khi biết producer có đang tạo job không.

### 14.1. Worker heartbeat không đủ để chứng minh progress

Worker có thể gửi heartbeat đều đặn nhưng:

- Không claim được job do bug SQL.
- Bị kẹt ở một delivery.
- Bắt và nuốt exception rồi tiếp tục loop.
- Chỉ đọc queue sai partition/tenant.
- Poll thành công nhưng không commit kết quả.

Vì vậy, theo dõi **heartbeat**, **last successful claim**, **last SMTP accepted** và **last state commit** riêng khi cần. Một worker “alive” không đồng nghĩa xử lý hữu ích.

### 14.2. Timeouts và lease cần cùng chính sách

Giả sử:

~~~text
SMTP connection timeout = 5s
SMTP read timeout = 10s
SMTP write timeout = 10s
outbox lease duration = 2s
~~~

Lease 2 giây có thể hết hạn khi SMTP call còn đang chạy, dẫn tới worker khác reclaim cùng job và gửi trùng.

Một cấu hình tốt cần xét:

- Worst-case/p99 end-to-end processing.
- SMTP connect/read/write timeout.
- Thời gian render attachment/template.
- Queue scheduling jitter và GC pause.
- Heartbeat/lease extension khi job dài.
- Concurrency và fencing token.

Không có quy tắc “lease = đúng SMTP timeout” cho mọi hệ thống. Nhưng **lease phải đủ cho workflow hoặc có heartbeat**, đồng thời stale worker không được phép ghi đè state của claim mới.

## 15. Structured log và correlation ID

Metrics hữu ích để phát hiện xu hướng; log/trace giúp tìm một delivery cụ thể.

Một log event có cấu trúc:

~~~json
{
  "event": "mail.dispatch.retry_scheduled",
  "deliveryId": "opaque-id",
  "template": "order-confirmation",
  "attempt": 3,
  "worker": "mail-worker-2",
  "errorCode": "SMTP_TEMPORARY",
  "failureKind": "TRANSIENT",
  "nextAttemptAt": "2026-11-12T10:30:00Z"
}
~~~

Ví dụ này không chứa địa chỉ người nhận, password, nội dung body hoặc token xác minh. `deliveryId` là ID opaque; nếu hệ thống coi cả ID là nhạy cảm, cũng phải hạn chế quyền đọc log.

### 15.1. Những trường hữu ích để điều tra

| Trường | Lý do |
| --- | --- |
| `deliveryId` / `outboxId` | Liên kết mọi bước của một yêu cầu gửi |
| `businessEventType` | Xác định loại thông báo |
| `attemptNo` | Biết một sự kiện nằm ở lượt nào |
| `claimToken` (giới hạn truy cập) | Điều tra concurrency/stale worker |
| `workerId` / `instanceId` | Tìm instance gặp sự cố |
| `provider` | Phân biệt nhiều SMTP relay |
| `smtpResult` | Accepted/rejected/unknown |
| `errorCode` / `failureStage` | Điều tra lỗi không cần raw exception |
| `queueWaitMs` / `smtpDurationMs` | Phân tích latency |
| `stateWriteResult` | Phát hiện SMTP success nhưng DB failed |

Không log nguyên `MimeMessage`, toàn bộ email content, SMTP credential, password reset token, danh sách To/Cc/Bcc hoặc raw exception message trong các log phổ thông.

### 15.2. Trace giữa API, outbox và worker

Với observability tracing, có thể tạo các span:

~~~text
HTTP request span
   |
   +--> business transaction
            |
            +--> outbox insert
                      |
                      +-- (asynchronous boundary)
                                |
                                v
                        worker claim span
                           |
                           +--> render MIME
                           +--> SMTP send
                           +--> state update
~~~

Trace context qua queue cần được truyền đúng cách theo thư viện/instrumentation được dùng; không giả định `ThreadLocal` từ HTTP request tự động sang worker thread. Có thể lưu trace/correlation metadata tối thiểu trong outbox để liên kết trace.

Không đưa message body hoặc token vào span attribute. Trace giúp chẩn đoán latency, nhưng **không thay thế nguồn state bền vững**.

## 16. Runbook: queue tăng bất thường

Khi nhận alert `oldest ready age > SLO` hoặc `queue ready depth increasing`:

**Bước 1 — Xác minh số đo.** Kiểm tra metric freshness, timestamp của snapshot và phạm vi tenant/queue. Nếu gauge được export từ nhiều replica cùng query một DB, đừng cộng trùng.

**Bước 2 — Xem producer và consumer.** So sánh enqueue rate với completion rate; worker có hoạt động không, có heartbeat nhưng không progress không?

**Bước 3 — Xem các lỗi gần đây.** Kiểm tra `mail_dispatch_attempts_total` theo `error_code`, nhất là auth/TLS/connection timeout/rate limit.

**Bước 4 — Xem in-flight/lease.** Nếu ready thấp nhưng `PROCESSING` hoặc unacked cao, có thể worker treo hoặc SMTP chậm.

**Bước 5 — Kiểm tra provider quota.** Có thể hệ thống gửi nhanh hơn giới hạn SMTP; tăng worker không giúp nếu provider đang throttle.

**Bước 6 — Chọn biện pháp phù hợp.**

- Worker crash: khôi phục worker và reclaim lease hết hạn có điều kiện.
- SMTP auth/TLS: sửa secret, certificate hoặc cấu hình; đừng tăng retry rate.
- Provider rate limit: giảm concurrency/throughput, tăng backoff.
- Quá nhiều producer: đặt backpressure hoặc scale worker khi an toàn với quota.
- Template lỗi hàng loạt: rollback/sửa deploy; đưa job lỗi terminal vào quy trình redrive.
- Monitoring lỗi: khôi phục collector; không suy đoán queue trống từ metrics stale.

**Bước 7 — Xác nhận hồi phục.** Ready age giảm, completion rate tăng, error rate về mức nền, DLQ không còn tăng bất thường và những job quan trọng được xử lý trước deadline.

### 16.1. Những hành động nên tránh khi queue tăng

- Tăng thread pool vô hạn mà không xét SMTP quota.
- Xóa queue hoặc reset DB để dashboard trở về 0.
- Đặt mọi `FAILED` lại thành `PENDING` không kiểm tra lý do.
- Retry ngay với credential đang sai.
- Reclaim `PROCESSING` đang có lease hợp lệ.
- Chuyển mọi job sang `SENT` để “thông luồng”.
- Bỏ qua email hết hạn hoặc suppression policy.

Vận hành queue là giải quyết nguyên nhân gốc, không phải chỉ giảm một chỉ số nhìn thấy trên dashboard.

## 17. Runbook: retry tăng đột ngột

Khi `mail_retry_scheduled_total` hoặc số hàng `RETRY` tăng nhanh:

1. **Phân nhóm theo error code:** smtp_auth, smtp_timeout, smtp_busy, mime_invalid, provider_policy, state_conflict...
2. **Kiểm tra thay đổi gần đây:** secret rotation, deploy mới, thay đổi template, DNS/network hoặc provider limit.
3. **Đánh giá khả năng tạm thời:** chỉ retry tự động với lỗi thực sự có cơ hội hồi phục.
4. **Xem backoff và jitter:** có quá nhiều worker cùng thử lại mỗi 1 giây hay không?
5. **Xem max attempts và deadline:** liệu nhiều job sắp hết lượt/hết hạn?
6. **Xem rate limiting/circuit breaker:** có cần tạm giảm dispatch để bảo vệ provider?
7. **Kiểm tra duplicate risk:** có timeout sau DATA hoặc lỗi state update sau SMTP acceptance?
8. **Theo dõi sau khắc phục:** retry due giảm, SMTP accepted tăng, không phát sinh DLQ mới nhiều bất thường.

### 17.1. Ví dụ sự cố credential

~~~text
09:00 Secret SMTP cũ bị revoke
09:01 mail_auth_failures tăng mạnh
09:02 worker retry 1.000 job cùng credential cũ
09:03 queue + retry_count tăng, provider cảnh báo abuse
~~~

Hành động phù hợp:

- Kiểm tra phiên bản secret đã được ứng dụng load.
- Khôi phục quyền truy cập đúng credential hoặc rotate/reload.
- Tạm ngưng retry dồn dập khi xác nhận đây là lỗi auth.
- Đánh dấu lỗi theo code `SMTP_AUTH_FAILED` và giữ trạng thái chờ/terminal theo policy.
- Sau khi khắc phục, redrive hoặc cho job đến hạn tiếp tục một cách kiểm soát.

Không dùng cùng credential sai để gửi lại hàng nghìn lần chỉ vì hệ thống đặt `max_attempts=10`.

## 18. Runbook: dead letter tăng nhanh

DLQ tăng thường cho thấy **một lớp lỗi không thể tự phục hồi** hoặc **retry policy không phù hợp**. Quy trình:

1. Xác định phạm vi: template, provider, environment, tenant, thời gian bắt đầu.
2. Lấy mẫu vài delivery từ DLQ, xem attempt history và mã lỗi đã sanitize.
3. Phân biệt **permanent** với **transient nhưng hết số lượt**.
4. Kiểm tra deploy/secret/provider changes gần thời điểm spike.
5. Sửa nguyên nhân: template invalid, secret sai, policy giới hạn hoặc dữ liệu recipient.
6. Xác minh payload còn giá trị; email bảo mật có thể hết hạn.
7. Quyết định redrive cùng delivery hay tạo yêu cầu mới được audit.
8. Dispatch redrive với rate limit; quan sát tỷ lệ thành công và lỗi mới.
9. Đóng sự cố khi backlog được xử lý theo SLA, không chỉ khi DLQ depth giảm bằng thao tác xóa.

### 18.1. Triage theo loại lỗi

| Nguyên nhân DLQ | Hành động thường phù hợp |
| --- | --- |
| `SMTP_AUTH_FAILED` | Rotate/sửa credential, kiểm tra các instance, sau đó redrive |
| `SMTP_RATE_LIMIT` đã hết retry | Điều chỉnh throughput/backoff/quota; redrive có rate limit |
| `MAIL_TEMPLATE_INVALID` | Sửa template/model, kiểm tra payload schema trước redrive |
| `RECIPIENT_INVALID` | Xác minh/sửa địa chỉ, không resend nguyên trạng |
| `BUSINESS_DEADLINE_EXPIRED` | Thường không gửi lại email đã hết giá trị |
| `SMTP_OUTCOME_UNKNOWN` | Đối soát nguy cơ duplicate trước khi gửi thêm |
| `STATE_UPDATE_CONFLICT` | Điều tra lease/fencing và lịch sử SMTP trước redrive |

### 18.2. Không redrive trực tiếp từ dashboard chỉ bằng nút “Retry all”

Một chức năng redrive nên yêu cầu:

- Phân quyền theo vai trò.
- Phạm vi rõ: delivery IDs, template, thời gian, loại lỗi.
- Kiểm tra policy suppression/deadline/idempotency.
- Dry-run: dự kiến bao nhiêu message, có bao nhiêu không hợp lệ.
- Rate limit và batch size.
- Audit `who/when/why`.
- Xác nhận trạng thái sau redrive.

Một số message phải được **bỏ qua có chủ đích**, không phải mọi DLQ đều cần gửi lại. Kết quả redrive cần phân biệt “requeued”, “SMTP accepted”, “bị chặn bởi suppression” và “không đủ điều kiện”.

## 19. Thiết kế redrive có kiểm soát

**Redrive** là đưa một message đã ở trạng thái terminal/quarantine trở lại luồng xử lý sau khi có quyết định vận hành hợp lệ. Với database outbox, không nên sửa tay tùy tiện một row `FAILED` rồi xóa lịch sử; với broker, không nên publish lại hàng loạt DLQ mà bỏ metadata về nguồn gốc.

### 19.1. Hai mô hình redrive

**Mô hình A — Tiếp tục cùng delivery record:**

~~~text
delivery_id = D1
attempt history: 1, 2, 3 (FAILED)
operator approves redrive
retry_cycle = 2
attempt history: 4, 5...
~~~

Ưu điểm: giữ một lịch sử liên tục. Nhược điểm: phải thiết kế rõ `max_attempts` là giới hạn theo **một retry cycle** hay toàn thời gian tồn tại delivery; không tùy tiện reset `attempt_count` về 0.

**Mô hình B — Tạo delivery mới liên kết delivery cũ:**

~~~text
original_delivery_id = D1 (FAILED)
redrive_delivery_id  = D2 (PENDING)
redrive_of = D1
reason = "SMTP credentials fixed"
~~~

Ưu điểm: giữ `D1` bất biến để audit; `D2` là một yêu cầu mới được ủy quyền. Nhược điểm: cần thiết kế idempotency key để phân biệt legitimate resend với duplicate ngoài ý muốn.

Không có một cách áp dụng cho mọi hệ thống. Điểm bắt buộc là **giữ audit và tránh resend ngoài chính sách nghiệp vụ**.

### 19.2. SQL minh họa redrive một bản ghi FAILED

Giả sử có cơ chế ghi audit riêng và policy cho phép tạo retry cycle mới:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY',
    next_attempt_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :delivery_id
  AND status = 'FAILED'
  AND :redrive_authorized = TRUE;
~~~

Đây chỉ là thao tác trạng thái **minh họa**; trong production, yêu cầu:

- Xác thực/ủy quyền request redrive ở service layer.
- Kiểm tra recipient chưa bị suppress, event chưa hết hạn.
- Định nghĩa việc xử lý `attempt_count >= max_attempts`: nếu không cấp lượt mới hoặc retry cycle mới thì worker vẫn không thể claim.
- Ghi audit event trong cùng transaction.
- Giữ nguyên nguyên nhân thất bại trong attempt history.
- Chặn hai operator redrive cùng một message đồng thời.
- Kiểm tra update count và version để tránh race.

Không thêm tham số boolean `redrive_authorized` do client tự gửi như một cơ chế bảo mật. Trong ví dụ, đây chỉ là nhãn minh họa cho **quyết định đã được service layer kiểm chứng**; quyền thực tế phải dựa trên authentication/authorization đáng tin cậy.

### 19.3. Audit table

Một bảng audit có thể ghi:

~~~sql
CREATE TABLE mail_redrive_audit (
    id UUID PRIMARY KEY,
    delivery_id UUID NOT NULL,
    actor_id VARCHAR(120) NOT NULL,
    action VARCHAR(40) NOT NULL,
    reason VARCHAR(300) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    previous_status VARCHAR(40),
    next_status VARCHAR(40)
);
~~~

Không ghi password/token vào `reason`. Nếu operator cần liên kết ticket, dùng một incident/ticket ID thay vì dán nguyên log/credential vào bảng audit.

### 19.4. Broker redrive cần tránh gửi trùng

Với DLQ vật lý:

1. Đọc message và metadata nguồn.
2. Xác định delivery ID và tra trạng thái nghiệp vụ.
3. Validate redrive eligibility/suppression/deadline.
4. Publish message trở lại queue hoặc retry topic **có xác nhận bền vững**.
5. Chỉ ack/xóa message DLQ nguồn khi đã xác nhận publish theo hợp đồng broker.
6. Ghi audit và cập nhật trạng thái delivery trong ranh giới transaction/outbox phù hợp.

Nếu publish thành công nhưng worker redrive chết trước khi ack/xóa DLQ, message có thể bị redrive lại. Đây là lý do cần **idempotency theo delivery ID**, không chỉ dựa vào một thao tác “move” như thể luôn nguyên tử trên mọi broker.

## 20. Xử lý outage: pause, circuit breaker và rate limit

Khi SMTP provider bị outage, retry mọi job cùng lúc có thể làm hệ thống quá tải. Một kiến trúc có thể dùng ba cơ chế phối hợp:

1. **Rate limiter:** kiểm soát số request/giây và concurrency theo provider/account.
2. **Circuit breaker:** tạm dừng gọi SMTP khi lỗi tăng liên tục; tránh làm tình hình xấu hơn.
3. **Backoff/jitter:** phân tán thời điểm retry của từng delivery.

~~~text
Ready queue
    |
    v
Rate limiter
    |
    v
Circuit breaker
    |
    +--> CLOSED: allow send
    |
    +--> OPEN: do not invoke SMTP
                |
                v
          Schedule retry / wait
~~~

Nếu circuit đang mở, **không** đánh dấu `SENT`. Tùy kiến trúc, job có thể vẫn `RETRY` hoặc được requeue sau delay; đừng claim quá nhiều job rồi để lease hết hạn trong lúc circuit mở.

### 20.1. Các metrics hỗ trợ quyết định scale

- `mail_queue_ready` và oldest ready age tăng.
- `mail_dispatch_duration_seconds` p95 cao.
- Worker active count gần max.
- Queue claim rate thấp hơn enqueue rate.
- SMTP error code báo rate limiting hay auth failure.
- Broker unacked count hoặc Kafka consumer lag.

Scale worker chỉ hữu ích khi bottleneck thực sự do worker capacity. Nếu provider limit là 100 email/phút, tăng từ 4 lên 40 worker có thể làm nhiều request bị throttle hơn.

### 20.2. Khi nào nên tạm dừng producer?

Nếu backlog vượt khả năng xử lý hoặc queue storage gần đầy, cần backpressure:

- Giới hạn tần suất tạo notification không bắt buộc.
- Gộp email không khẩn cấp nếu nghiệp vụ cho phép.
- Trả response quá tải thích hợp nếu request chưa được nhận bền vững.
- Đưa thông báo không khẩn cấp vào lịch gửi sau.
- Giữ email giao dịch cần thiết với ưu tiên phù hợp.

Không bỏ qua event nghiệp vụ quan trọng mà không ghi trạng thái; một queue đầy phải là **tín hiệu vận hành và hợp đồng API rõ ràng**, không phải lỗi bị nuốt.

## 21. Sự cố SMTP accepted nhưng state update thất bại

Đây là một trong những tình huống vận hành khó nhất:

~~~text
Worker claims delivery #D1
       |
       v
JavaMailSender.send returns successfully
       |
       v
Database commit markSENT fails
       |
       v
Outbox still PROCESSING/RETRY after lease expiry
       |
       v
New worker may dispatch again
       |
       v
Duplicate email possible
~~~

Một lỗi database sau khi SMTP accepted **không** đồng nghĩa transport thất bại. Nên có metric/log riêng:

~~~text
mail.smtp.accepted.total
mail.state.update.failures.total{operation="mark_sent"}
mail.outbox.unknown.current
mail.outbox.lease.reclaimed.total
~~~

Trong thực tế, tên metric có thể chuẩn hóa theo Micrometer/Prometheus, nhưng ý nghĩa phải tách biệt.

### 21.1. Không quảng cáo exactly-once nếu dùng SMTP thuần

Transactional outbox giúp bảo đảm thay đổi nghiệp vụ và ý định gửi được commit cùng nhau, nhưng không tạo distributed transaction giữa SMTP và database. Thông thường, dispatch có **at-least-once semantics**, nên có cửa sổ gửi trùng.

`Message-ID` có thể dùng correlation nhưng không buộc mọi SMTP server loại bỏ bản gửi trùng. Nếu email provider có API với idempotency key, có thể áp dụng theo hợp đồng của họ; SMTP thuần không cung cấp cam kết exactly-once toàn cục.

Trong dashboard, hãy tách:

- **SMTP accepted count:** send method hoàn tất.
- **SENT state commit count:** database đã ghi nhận.
- **Potential duplicate count:** kết quả mơ hồ hoặc state conflict sau send.

Với các delivery ở trạng thái `UNKNOWN`, một runbook có thể yêu cầu đối soát provider logs/API (nếu hỗ trợ) trước khi operator chọn retry. Không xử lý bằng cách “retry tất cả đến khi dashboard xanh”.

## 22. Bảo mật số liệu, queue và dead letter

Queue và DLQ có thể chứa payload email: recipient, subject, body, thông tin hóa đơn, reset token hoặc URL xác minh. Những dữ liệu này có thể nhạy cảm ngay cả khi nằm trong môi trường nội bộ.

**Các biện pháp cần có:**

- Chỉ cho worker có quyền truy cập queue/outbox tương ứng.
- RBAC/ACL cho broker queue, DLQ topic, database và dashboard.
- Mã hóa kết nối giữa producer, broker, worker và database khi cần theo policy.
- Không đưa password SMTP, OAuth token hoặc body email vào metric tags.
- Không log toàn bộ message khi consumer throw exception.
- Giới hạn quyền đọc DLQ và thao tác redrive.
- Thiết lập retention, archive và xóa dữ liệu theo chính sách.
- Hạn chế hiển thị email/PII trong UI vận hành; dùng ID opaque và truy vấn có audit.
- Cẩn thận khi export DLQ payload vào support bundle/ticket.
- Giám sát thay đổi quyền và các lần redrive hàng loạt.

### 22.1. Metric cardinality

Không nên:

~~~text
mail_retry_total{recipient="alice@example.com",deliveryId="uuid-1"}
mail_retry_total{recipient="bob@example.com",deliveryId="uuid-2"}
...
~~~

Mỗi delivery tạo một bộ time series riêng và có thể lộ PII. Thay bằng:

~~~text
mail_retry_total{template="order_confirmation",error_code="smtp_timeout"}
mail_retry_total{template="password_reset",error_code="smtp_auth"}
~~~

Nếu số template rất lớn hoặc do người dùng tự tạo, cũng phải chuẩn hóa/giới hạn category. Cần cân bằng khả năng chẩn đoán với số lượng nhãn.

### 22.2. DLQ không nên giữ dữ liệu vô hạn

Một mail verification token có thể hết hạn sau vài phút nhưng payload bị giữ trong DLQ nhiều tháng nếu không có retention. Nên xác định:

| Loại dữ liệu | Gợi ý quản lý |
| --- | --- |
| Delivery ID / error code | Có thể giữ theo audit policy |
| Recipient email | Giới hạn quyền, thời hạn lưu theo nhu cầu |
| Message body / attachment | Không lưu nếu không cần, mã hóa và xóa đúng hạn |
| Token xác minh/reset password | Không đưa vào log/DLQ ngoài mức bắt buộc; dùng reference/expire |
| Raw exception | Tránh serialize trong DB, log có masking |
| Redrive audit | Giữ actor/reason/time theo chính sách tổ chức |

Không có một số ngày retention chung cho mọi sản phẩm; phải xét bảo mật, nhu cầu nghiệp vụ và quy định áp dụng.

## 23. Kiểm thử luồng queue, retry và dead letter

Observability cần được kiểm thử ở hai mức:

1. **Trạng thái nghiệp vụ thật:** outbox/broker có tiến triển đúng, không mất job và không retry vượt policy.
2. **Số liệu vận hành:** metrics phản ánh đúng sự kiện đã xảy ra và cảnh báo phát hiện những lỗi chủ chốt.

Không chỉ test rằng `meterRegistry.counter(...).increment()` đã được gọi. Nếu thuật toán state transition sai, metrics có thể đẹp nhưng email thực tế thất bại.

### 23.1. Unit test retry policy

Giả sử một policy phân loại lỗi transient và giới hạn ba attempt:

~~~java
@Test
void transientFailureSchedulesRetryBeforeMaxAttempts() {
    MailRetryPolicy policy = new MailRetryPolicy(
            3,
            Duration.ofSeconds(30),
            Duration.ofMinutes(5));

    FailureDecision failure = new FailureDecision(
            FailureKind.TRANSIENT,
            "SMTP_TIMEOUT",
            "SMTP_CONNECT",
            "Connection timed out");

    RetryDecision result = policy.decide(
            1, failure, Instant.parse("2026-11-12T10:00:00Z"));

    assertThat(result.action()).isEqualTo(NextAction.RETRY);
    assertThat(result.nextAttemptAt())
            .isAfter(Instant.parse("2026-11-12T10:00:00Z"));
}
~~~

Các lớp `MailRetryPolicy`, `RetryDecision` và enum được dùng ở đây là **abstraction minh họa của ứng dụng**, không phải API built-in của Spring Mail. Test thật phải sử dụng policy đang triển khai và có kiểm tra max attempts, deadline, jitter bằng `Clock` giả khi cần.

### 23.2. Integration test atomic claim và attempt count

Với PostgreSQL/Testcontainers:

1. Insert một row `PENDING, attempt_count=0`.
2. Cho hai worker claim đồng thời.
3. Xác nhận chỉ một worker claim được row khi lease còn hiệu lực.
4. Xác nhận `attempt_count=1` và attempt history có đúng một record `STARTED`.
5. Cho SMTP fake từ chối tạm thời.
6. Kiểm tra `status=RETRY` và `next_attempt_at` trong tương lai.
7. Trước thời điểm đó, worker không claim được.
8. Khi đến hạn, attempt tiếp theo tăng counter đúng một lần.
9. Không dùng `SELECT` rồi `UPDATE` rời rạc nếu production yêu cầu atomicity.

Test concurrency nên chạy trên **database engine tương thích production**, vì H2 hoặc mock repository có thể không mô phỏng đúng `FOR UPDATE SKIP LOCKED`, row locking hoặc transaction isolation.

### 23.3. Test SMTP accepted + state write failure

Kịch bản:

~~~text
Fake SMTP accepts message
          |
          v
markSent() throws database exception
          |
          v
Expected:
  - do not immediately resend SMTP
  - record state-write failure / UNKNOWN risk
  - preserve delivery ID and attempt history
  - alert/reconciliation path is available
~~~

Đây là một kiểm thử rất quan trọng cho retry/idempotency. Nếu test chỉ mock `JavaMailSender` ném exception, nó không bao phủ trường hợp **SMTP đã thành công nhưng database cập nhật thất bại**.

### 23.4. Test max attempts → dead letter

Với `max_attempts=3`:

| Attempt | SMTP outcome | State sau xử lý |
| --- | --- | --- |
| 1 | Temporary failure | RETRY |
| 2 | Temporary failure | RETRY |
| 3 | Temporary failure | FAILED/DLQ |

Assert:

- Counter tăng đúng một lần mỗi claim.
- Không tạo attempt #4 tự động.
- `terminal_reason=MAX_ATTEMPTS_EXHAUSTED`.
- Last error code vẫn là nguyên nhân SMTP thật (nếu đã phân loại).
- Dead-letter arrival event được ghi một lần.
- DLQ/outbox record vẫn đủ dữ liệu để operator điều tra.

Nếu lỗi đầu tiên là permanent, test có thể xác nhận chuyển `FAILED` ngay, không cần dùng hết mọi attempt.

### 23.5. Test idempotency của broker redelivery

Broker có thể deliver lại message nếu consumer chết trước ack. Test nên kiểm tra:

- Business delivery ID giống nhau không tạo nhiều outbox rows trái policy.
- Worker nhận redelivery không resend nếu delivery đã `SENT` và có bằng chứng bền vững.
- Consumer không ack trước khi kết quả cần thiết được commit.
- Retry message có attempt count và correlation data được lưu/khôi phục chính xác.
- Redrive DLQ lặp lại không làm tạo nhiều job độc lập thiếu kiểm soát.

Không tuyên bố exactly-once chỉ vì một integration test nhận đúng một message trong happy path. Tình huống crash giữa SMTP accepted và DB commit vẫn có thể gây duplicate.

### 23.6. Test metrics với SimpleMeterRegistry

Micrometer có thể được kiểm thử bằng `SimpleMeterRegistry`:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

@Test
void recordsRetryAttemptWithBoundedTags() {
    try (SimpleMeterRegistry registry =
                 new SimpleMeterRegistry()) {
        MailDispatchMeters meters = new MailDispatchMeters(registry);

        meters.recordAttemptOutcome(
                "retry",
                "transient",
                "smtp_timeout");

        double count = registry.get("mail.dispatch.attempts")
                .tag("outcome", "retry")
                .tag("failure_kind", "transient")
                .tag("error_code", "smtp_timeout")
                .counter()
                .count();

        assertThat(count).isEqualTo(1.0);
    }
}
~~~

Test này kiểm tra **instrumentation** và tag schema của helper được minh họa ở phần trước, không thay thế integration test trạng thái database. Cần dùng JUnit 5/AssertJ và import các class tương ứng.

### 23.7. Test metrics freshness

Giả sử collector đang xuất:

~~~text
ready = 42
snapshotCollectedAt = T1
~~~

Sau đó database không truy cập được trong 10 phút. Hành vi đúng nên thể hiện:

~~~text
last ready snapshot = 42 (stale)
snapshot age = 600 seconds
snapshot refresh failures > 0
~~~

Không giả vờ `ready=0` chỉ vì truy vấn fail. Cảnh báo nên phân biệt **“queue đã được xử lý hết”** và **“không còn quan sát được queue”**.

### 23.8. Test cảnh báo bằng kịch bản

Một số tình huống phù hợp với integration/staging:

| Tình huống | Tín hiệu mong đợi |
| --- | --- |
| Tắt worker khi queue có 100 job đến hạn | Ready age tăng; no progress alert |
| Tăng tốc producer vượt consumer | Backlog depth và age tăng |
| SMTP auth fail hàng loạt | Auth failure rate tăng; retries không dồn dập |
| SMTP timeout kéo dài | Dispatch duration tăng; lease/UNKNOWN được theo dõi |
| Template lỗi mọi delivery | DLQ arrivals theo `mime_invalid` tăng |
| Consumer chết trước ack | Có redelivery, không mất business delivery |
| Metrics collector mất kết nối DB | Snapshot freshness alert, không hiện queue=0 giả |
| Operator redrive sau sửa lỗi | Audit có event, DLQ giảm, accepted tăng |

Các bài test nên có timeout và dữ liệu cô lập. Không gửi mail thật tới người nhận công cộng để “tạo lỗi” trong bài test tự động.

## 24. Ví dụ dashboard của một sự cố cụ thể

Giả sử vào một buổi sáng, provider SMTP bị tạm giới hạn tốc độ:

~~~text
10:00
  enqueue rate           200 messages/min
  SMTP accepted rate     180 messages/min
  ready depth             80
  retry due               12
  dead letter              0

10:10
  enqueue rate           200 messages/min
  SMTP accepted rate      40 messages/min
  ready depth          1,200
  retry due              300
  oldest ready age         6 min
  error_code=smtp_throttle spike

10:20
  worker rate limit reduced
  backoff with jitter enabled
  SMTP accepted rate      80 messages/min
  retry due              220
  dead letter             10
~~~

**Đọc dashboard:**

- Lỗi không nằm ở producer vì enqueue vẫn hoạt động.
- Ready depth và oldest age tăng do throughput thấp hơn arrival rate.
- Retry due tăng vì provider trả transient errors.
- Việc tăng worker ngay lúc provider throttle có thể làm tình hình xấu hơn.
- Dead letter mới xuất hiện cần phân loại: hết số lượt hay lỗi permanent độc lập?
- Nếu tốc độ chấp nhận thấp hơn tốc độ enqueue trong thời gian dài, backlog chưa thể tự giảm, dù retry count bắt đầu ổn định.

### 24.1. Đánh giá sau khắc phục

Khi quota được tăng hoặc provider phục hồi:

- Error rate của `smtp_throttle` giảm.
- SMTP accepted rate tăng.
- Ready depth giảm dần.
- Oldest ready age trở về dưới SLO.
- DLQ không tiếp tục tăng.
- Operator xử lý 10 delivery dead-letter còn lại sau khi xác định nguyên nhân và deadline.

Đừng chỉ nhìn tổng số email đã gửi tăng. Cần biết **độ trễ, số chưa hoàn tất và các delivery đã thất bại cuối** để kết luận hệ thống phục hồi.

## 25. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ đo queue depth | Không phát hiện worker đang treo in-flight | Theo dõi in-flight, oldest age, throughput |
| Cộng gauge toàn DB từ mọi replica | Dashboard nhân backlog lên N lần | Chỉ chọn collector authoritative hoặc aggregation đúng |
| Coi scheduled retry là attempted retry | Số lượt gửi bị báo phóng đại | Tách scheduled/started/finished |
| Chỉ tăng retry count trong catch | Crash trước catch không được ghi nhận | Tăng attempt count trong claim transaction |
| Retry mọi exception vô hạn | Quá tải SMTP, có thể gửi trùng | Classifier, backoff, max attempts |
| Dead-letter khi chưa lưu last_error_code | Không có thông tin triage | Ghi mã lỗi, stage, terminal reason |
| Gộp transient error và max attempts thành permanent | Mất nguyên nhân thực | Tách failure kind khỏi terminal reason |
| Nhầm SMTP accepted với inbox delivered | Báo cáo giao thư sai | Tách submission và delivery feedback |
| Ack broker trước khi lưu kết quả | Crash có thể làm mất job | Theo hợp đồng ack/transaction bền vững |
| Requeue ngay mọi lần nack | Hot loop, broker/SMTP overload | Delay/backoff/DLX |
| Không có lease/fencing | Hai worker cùng gửi, state race | Atomic claim + claim token/version |
| Redrive toàn bộ DLQ không kiểm tra | Gửi email hết hạn/recipient sai | Eligibility, suppression, audit, rate limit |
| Sử dụng raw exception làm tag | Cardinality lớn, lộ PII | Error taxonomy hữu hạn |
| Metrics query thất bại thì set gauge=0 | Báo queue rỗng giả | Đánh dấu stale và tăng refresh failure metric |
| Xóa FAILED để dashboard về 0 | Mất audit và chưa sửa sự cố | Retention/triage/redrive có quy trình |
| Scale workers bất chấp provider quota | Thêm rate limit và retry storm | Rate limiter, circuit breaker, backpressure |

## 26. Câu hỏi thường gặp

**“Spring Framework Mail có sẵn queue và DLQ không?”**  
Không. `JavaMailSender` là API gửi email. Queue/retry/DLQ thường do ứng dụng triển khai bằng database outbox hoặc tích hợp message broker, chẳng hạn RabbitMQ/Kafka. Các thư viện broker có khả năng riêng; không nên nhầm với Spring Mail.

**“Queue depth bằng 0 có nghĩa tất cả email đã gửi?”**  
Không. Job có thể đang `PROCESSING`, đang chờ retry ở một queue khác, đã vào DLQ hoặc đã bị mất vì ack sai. Cần xem in-flight, delayed, failed, producer activity và completion state.

**“Nên cảnh báo theo queue depth hay queue age?”**  
Thường nên có cả hai. Queue depth cho biết khối lượng; oldest ready age gắn trực tiếp với việc email đã chờ quá lâu. Chỉ nhìn depth có thể bỏ sót một job lâu ngày bị đói; chỉ nhìn age mà không biết throughput cũng khó quyết định scale.

**“Retry count nên bắt đầu từ 0 hay 1?”**  
Có thể chọn quy ước, nhưng phải nhất quán. Một mô hình dễ giải thích là `attempt_count=0` khi chưa xử lý, tăng lên `1` khi lần đầu được claim; số lần retry đã sử dụng là `max(attempt_count-1,0)`. Không đổi nghĩa giữa các module.

**“Tại sao số retry scheduled nhiều hơn số retry started?”**  
Vì job có thể mới được lên lịch sau backoff, chưa tới hạn, bị hủy, chuyển DLQ hoặc worker chưa có capacity. Scheduled là quyết định tương lai; started là lượt xử lý đã thực sự bắt đầu.

**“MailSendException có luôn được retry không?”**  
Không. `MailSendException` có thể bọc lỗi tạm thời, lỗi vĩnh viễn hoặc kết quả chưa chắc chắn. Phải xem nested cause, mã SMTP, giai đoạn lỗi và provider policy.

**“Có nên retry lỗi SMTP authentication ngay lập tức?”**  
Thường không. Nếu password hoặc quyền bị sai, retry cùng credential liên tục sẽ không khắc phục lỗi và có thể kích hoạt khóa tài khoản/provider throttling. Cần kiểm tra credential/rotation và chỉ redrive khi đã sửa.

**“Một email timeout có chắc chưa được gửi không?”**  
Không. Nếu timeout sau khi message DATA đã tới relay, server có thể đã chấp nhận nhưng client không nhận được phản hồi cuối. Retry có nguy cơ duplicate; cần policy `UNKNOWN`/đối soát.

**“Tại sao retry đúng ba lần nhưng attempt_count bằng bốn?”**  
Nếu attempt đầu tiên không được gọi là retry, ba lần thử lại cộng lần đầu là bốn lượt dispatch. Cần đặt tên chính xác và giải thích cho người đọc dashboard.

**“Dead letter có bắt buộc là một queue vật lý?”**  
Không. Với database outbox, `status=FAILED` hoặc một bảng dead-letter có thể đóng vai trò terminal store. Với broker, DLQ có thể là một queue/topic riêng. Điểm chung là dừng retry tự động và giữ thông tin điều tra.

**“Một message FAILED có nên bị xóa ngay không?”**  
Không nếu cần audit, redrive hoặc điều tra. Có thể archive/xóa theo retention policy nhưng không xóa chỉ để làm dashboard đẹp.

**“Khi nào chuyển từ RETRY sang DEAD LETTER?”**  
Khi policy dừng retry: lỗi permanent, hết max attempts, hết deadline hoặc operator quyết định không tiếp tục. Nên lưu `terminal_reason` tách khỏi error code.

**“Có nên redrive mọi DLQ sau khi sửa SMTP password?”**  
Không tự động. Phải lọc những job thất bại do lỗi đó, kiểm tra hạn dùng, suppression và tính hợp lệ của recipient/payload. Redrive có rate limit và audit.

**“Khi retry, có nên giữ nguyên delivery ID không?”**  
Thông thường có khi đây vẫn là **cùng một yêu cầu gửi**. Attempt ID hoặc claim token thay đổi theo lượt; delivery/business idempotency key ổn định. Nếu tạo một yêu cầu gửi mới hợp lệ, cần liên kết nguồn gốc để audit.

**“RabbitMQ x-death có phải là tổng số lần gửi SMTP không?”**  
Không. Nó phản ánh dead-lettering theo cơ chế broker, không phải số lần `JavaMailSender.send` thực sự chạy. Nếu cần attempt count nghiệp vụ, lưu riêng.

**“Kafka có queue depth như RabbitMQ không?”**  
Kafka thường được quan sát bằng consumer lag/offset theo topic và partition. Nếu có retry/DLQ topic, cần theo dõi từng luồng; không cộng tất cả offsets để gọi là số email chưa gửi nếu không có mô hình rõ.

**“Có nên tăng worker khi queue backlog cao?”**  
Chỉ sau khi xác định bottleneck là worker capacity. Nếu SMTP provider đang giới hạn tốc độ, tăng worker có thể làm lỗi nhiều hơn. Hãy xem provider quota, send duration, error rate và CPU/threads trước.

**“Tại sao queue metrics và database query không khớp?”**  
Vì thời điểm snapshot khác nhau, một job có thể ở nhiều tầng, metric counter có thể reset theo process, hoặc dashboard đang cộng trùng gauge toàn cục từ nhiều replica. Cần thống nhất scope và sampling.

**“Có nên đặt delivery ID vào tag Prometheus?”**  
Không. Nó tạo số lượng time series rất lớn và có thể lộ thông tin. Delivery ID phù hợp trong structured log/trace có kiểm soát; metrics nên dùng tag hữu hạn như template category, provider, error code.

**“Outbox SENT đã là email vào inbox chưa?”**  
Chưa nếu `SENT` được định nghĩa là SMTP accepted. Bounce, spam filtering, recipient mailbox và provider delivery feedback thuộc tầng deliverability riêng.

**“Có nên alert khi một job rơi vào DLQ?”**  
Tùy loại email và mức ảnh hưởng. Một email gửi tới địa chỉ không tồn tại có thể là lỗi cá biệt; DLQ tăng hàng loạt do authentication/template failure cần cảnh báo nghiêm trọng hơn.

**“Làm sao phân biệt worker chết và worker đang xử lý chậm?”**  
Kết hợp heartbeat, last progress, in-flight count, lease expiry, SMTP timeout và trace duration. Một heartbeat vẫn tăng không chứng minh tác vụ đang tiến triển.

**“Bật circuit breaker có nên chuyển job thành FAILED?”**  
Không mặc định. Circuit breaker chỉ cho biết tạm dừng gọi provider vì lỗi hệ thống, không chứng minh từng delivery không thể gửi. Thường nên giữ job ở trạng thái chờ/retry với backoff.

**“Monitoring DB lỗi có nên hiển thị queue depth = 0?”**  
Không. Phải coi là dữ liệu không còn mới, cảnh báo collector lỗi và phân biệt với queue thực sự rỗng.

**“Sau redrive, có nên reset attempt_count về 0?”**  
Không âm thầm reset nếu cần audit. Có thể mở một retry cycle mới hoặc tạo delivery mới có liên kết; giữ lịch sử cũ và ghi nhận operator/reason.

## 27. Checklist triển khai quan sát và vận hành mail queue

### Định nghĩa trạng thái

1. Xác định nguồn sự thật cho delivery: database outbox, broker hay kết hợp.
2. Định nghĩa `PENDING`, `PROCESSING`, `RETRY`, `SENT`, `FAILED` và `UNKNOWN` nếu có.
3. Phân biệt enqueue, claim, SMTP accepted, state committed và provider delivered.
4. Định nghĩa attempt count và retry count nhất quán.
5. Dùng atomic claim, lease/fencing token khi nhiều worker.

### Queue dashboard

6. Có ready, delayed, in-flight, expired lease và terminal counts.
7. Có oldest ready age và oldest unfinished age riêng.
8. Có enqueue/claim/completion rate.
9. Có SMTP duration, queue wait và total time.
10. Biết gauge là theo instance, queue hay toàn database để tránh cộng trùng.
11. Có metric freshness và collector error rate.

### Retry

12. Lưu attempt history và error code đã chuẩn hóa.
13. Phân loại transient/permanent/unknown, không chỉ nhìn tên exception.
14. Có backoff, jitter, max attempts, deadline và retry scheduling bền vững.
15. Theo dõi retry scheduled, started, exhausted riêng.
16. Không retry dồn dập lỗi auth hoặc provider throttle.
17. Có chính sách đối soát khi SMTP outcome không rõ.

### Dead letter

18. Có nơi lưu terminal job cùng nguyên nhân và lịch sử.
19. Đo DLQ depth, arrivals, oldest age và terminal reasons.
20. Không bỏ message khi consumer crash hoặc ack sai.
21. Có runbook triage và quy trình redrive được phân quyền.
22. Redrive phải kiểm tra suppression, deadline, idempotency và rate limit.
23. Có audit actor/time/reason khi redrive.
24. Có retention và bảo vệ dữ liệu nhạy cảm trong DLQ.

### Kiểm thử và vận hành

25. Test SMTP success, transient/permanent, max attempts và timeout.
26. Test concurrency, lease expiry, broker redelivery và crash window.
27. Test SMTP success nhưng database state update thất bại.
28. Test alert khi worker không tiến triển và queue age vượt SLO.
29. Test metrics không lộ recipient/secret và không có tag cardinality cao.
30. Có dashboard và escalation owner rõ ràng cho queue/DLQ.

## 28. Kiến trúc quan sát hoàn chỉnh

~~~text
                     Business service
                           |
                           v
                    Outbox / broker
                    PENDING / ready
                           |
                +----------+-----------+
                |                      |
                v                      v
        Queue snapshots          Broker telemetry
        depth + age              ready/unacked/lag
                |                      |
                +----------+-----------+
                           |
                           v
                        Worker
                           |
                  +--------+--------+
                  |                 |
                  v                 v
             JavaMailSender     Error classifier
                  |                 |
            +-----+-----+     +-----+------+
            |           |     |            |
            v           v     v            v
      SMTP accepted   Unknown RETRY       FAILED/DLQ
            |           |     |            |
            v           v     v            v
      SENT state   Reconcile Next time  Triage/redrive
            |           |     |            |
            +-----------+-----+------------+
                            |
                            v
                  Durable state + attempt history
                            |
                            v
                  Micrometer / Prometheus
                            |
                    +-------+---------+
                    |                 |
                    v                 v
                 Grafana          Alert manager
                    |                 |
                    v                 v
             On-call dashboard   Runbooks / tickets
~~~

### Nguyên tắc ghi nhớ

- Queue depth cần đi kèm **tuổi hàng chờ, throughput, in-flight và worker progress**.
- Retry count không chỉ là số lỗi; phải phân biệt **attempt, retry scheduled và retry started**.
- Dead letter là nơi **giữ thất bại đã dừng retry**, không phải thùng rác có thể xóa vô điều kiện.
- Metrics là tín hiệu vận hành; **outbox/attempt history và broker state** mới là bằng chứng bền vững để đối soát.
- Đối với SMTP, `send` thành công chỉ chứng minh transport đã chấp nhận theo quan sát của ứng dụng, **không chứng minh inbox delivery**.
- Retry có thể tạo duplicate nếu SMTP accepted nhưng database chưa commit trạng thái `SENT`.
- Alert phải gắn với SLO và hành động được, không chỉ dựa trên một con số đẹp/xấu.
- Log, metric và DLQ phải được bảo vệ khỏi rò rỉ địa chỉ email, nội dung thư và credential.

## Kết luận

**Theo dõi queue, retry count và dead letter** là nền tảng để vận hành đáng tin cậy một hệ thống gửi email bất đồng bộ bằng Spring Framework Mail. Queue cho thấy công việc còn chờ và có đang tiến triển không; retry count và attempt history cho biết vì sao việc gửi chưa thành công; dead letter giữ những delivery không thể tự phục hồi để người vận hành xử lý an toàn.

Một giải pháp hiệu quả kết hợp **trạng thái bền vững, metrics có định nghĩa rõ, log/trace theo correlation ID, cảnh báo dựa trên độ trễ và runbook cho retry/DLQ**. Nhờ đó, ứng dụng không chỉ gửi email khi mọi thứ hoạt động bình thường mà còn phát hiện sớm, giải thích được nguyên nhân và phục hồi có kiểm soát khi SMTP, worker, database hoặc broker gặp sự cố.
