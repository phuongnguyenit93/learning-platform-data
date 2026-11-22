# Kiểm tra outbox bị tồn đọng

Trong ứng dụng sử dụng **Spring Framework Mail**, việc ghi một công việc gửi email vào **transactional outbox** giúp tách transaction nghiệp vụ khỏi thao tác SMTP. Tuy nhiên, bản ghi outbox được commit thành công **không có nghĩa email đã được gửi**. Nếu worker dừng, SMTP bị chậm, retry bị trì hoãn hoặc một hàng đợi bị khóa, các bản ghi sẽ tích tụ. Người dùng có thể không nhận được thư xác nhận đơn hàng, biên nhận hoặc thông báo bảo mật đúng thời điểm dù HTTP API vẫn trả thành công.

**Kiểm tra outbox bị tồn đọng** là công việc quan sát và vận hành để trả lời: bao nhiêu notification đã đến hạn nhưng chưa được xử lý, notification cũ nhất đã chờ bao lâu, hàng đợi đang tăng hay giảm, worker có thực sự gửi được thư, và có công việc nào kẹt ở trạng thái không rõ kết quả hay không.

Bài học này xây dựng cách quan sát outbox mail dựa trên **trạng thái, tuổi, tốc độ đến/xử lý, lease, retry và kết quả SMTP**, cung cấp ví dụ **PostgreSQL**, **Spring Boot/Micrometer**, dashboard, alert, quy trình tìm nguyên nhân và cách khôi phục mà không gây gửi trùng. Các bảng, service và metric đặt tên trong bài là **thiết kế minh họa của ứng dụng**, không phải tính năng outbox được JavaMailSender tự tạo.

> **Nguyên tắc vận hành:** Không chỉ nhìn tổng số bản ghi outbox. Phải phân biệt **job chưa đến hạn**, **job đến hạn đang chờ**, **job đang thực thi**, **job thất bại đang đợi retry** và **job không rõ đã được SMTP chấp nhận hay chưa**. Tuyệt đối không giải quyết backlog bằng cách đổi tất cả trạng thái về PENDING rồi gửi lại.

## 1. Vì sao có outbox rồi vẫn phải giám sát?

Một luồng mail giao dịch điển hình:

~~~text
OrderService / AccountService
             |
             v
       BEGIN TRANSACTION
             |
        +----+----+
        |         |
        v         v
    Save Order   Insert MailOutbox(PENDING)
        |         |
        +----+----+
             |
             v
           COMMIT
             |
             v
       Mail dispatcher
             |
             v
      SMTP / mail provider
             |
       +-----+------+
       |            |
       v            v
    ACCEPTED       ERROR
                    |
               RETRY / UNKNOWN
~~~

Outbox bảo đảm rằng **sự kiện gửi mail được lưu cùng thay đổi nghiệp vụ**, nếu cùng database transaction được cấu hình đúng. Nhưng sau commit, phần việc còn lại phụ thuộc vào:

- Worker scheduler hoặc consumer có đang hoạt động không.
- Database có cho phép claim job đúng và đủ nhanh không.
- SMTP server có phản hồi không, credentials/TLS có hợp lệ không.
- Rate limit, connection pool, retry/backoff và queue capacity.
- Logic chuyển trạng thái có ghi nhận outcome chính xác không.
- Có job bị treo do worker chết, lease quá hạn hoặc không thể đối soát không.

Hệ thống vẫn có thể lưu outbox chính xác nhưng **ngừng gửi thư trong nhiều giờ** nếu không có metric và cảnh báo.

### Tồn đọng không đồng nghĩa với lỗi

Giả sử:

~~~text
12:00 Tạo email nhắc gia hạn có lịch gửi 17:00
12:01 Outbox chứa record PENDING
12:05 Dashboard hiển thị 1 record chưa gửi
~~~

Record đó **không bị kẹt** vì chưa đến lịch. Ngược lại:

~~~text
12:00 Tạo email xác nhận đăng nhập cần gửi ngay
12:01 Outbox status=PENDING, available_at=12:00
12:20 Chưa worker nào claim
~~~

Đây là một **due backlog** cần điều tra. Vì thế phải định nghĩa rõ “đã đến hạn” và SLA theo loại thư.

## 2. Mô hình trạng thái để quan sát

Một state machine cho outbox mail có thể có:

| Trạng thái | Ý nghĩa | Hành động vận hành |
| --- | --- | --- |
| **PENDING** | Đã ghi nhận notification, đang đợi thời điểm gửi | Kiểm tra lịch, worker, backlog |
| **RETRY_WAIT** | Lần thử trước có lỗi được phép retry; chờ backoff | Quan sát lý do lỗi, lịch retry và attempt count |
| **IN_FLIGHT** | Worker đã claim và có quyền xử lý tạm thời | Theo dõi thời gian chạy, lease/heartbeat |
| **ACCEPTED** | SMTP/provider đã xác nhận chấp nhận submission | Không retry theo backlog |
| **UNKNOWN** | Không xác định được attempt đã được server chấp nhận chưa | Đối soát, tránh tự gửi lại |
| **SUPPRESSED** | Không được gửi do opt-out/complaint/bounce hoặc policy | Không tính là lỗi worker phải retry |
| **PERMANENT_FAILED** | Lỗi không thể hoặc không nên tự retry | Đưa vào xử lý dữ liệu/cấu hình hoặc vận hành |
| **CANCELLED** | Notification bị hủy theo nghiệp vụ | Không gửi |

Tên trạng thái chỉ là ví dụ. Trong một dự án, có thể dùng **SENT** thay **ACCEPTED**, **FAILED_RETRYABLE** thay **RETRY_WAIT**, hoặc lưu retry trong bảng attempt riêng. Quan trọng là nhất quán về semantics: **ACCEPTED** ở đây nói về sự chấp nhận của transport/provider, **không khẳng định Inbox đã nhận hoặc người dùng đã đọc**.

### Sơ đồ chuyển trạng thái

~~~text
PENDING --đến hạn/claim--> IN_FLIGHT
   ^                          |
   |                          +-- SMTP nhận thành công --> ACCEPTED
   |                          |
   |                          +-- lỗi có thể retry -----> RETRY_WAIT
   |                          |                              |
   |                          |                              v
   |                          |                         đến lịch retry
   |                          |                              |
   |                          +-- lỗi vĩnh viễn --> PERMANENT_FAILED
   |                          |
   |                          +-- kết quả mơ hồ / crash --> UNKNOWN
   |
   +--- quyết định retry an toàn sau đối soát ---- UNKNOWN

PENDING / RETRY_WAIT --không còn đủ điều kiện gửi--> SUPPRESSED
PENDING / RETRY_WAIT --bị hủy theo nghiệp vụ-----> CANCELLED
~~~

Một email có thể được tạo ngay nhưng chỉ đủ điều kiện gửi sau một khoảng thời gian. Vì vậy một job PENDING nằm lâu trong bảng không nhất thiết đang chậm; cần so sánh với **available_at** hoặc **scheduled_at**.

## 3. Định nghĩa chính xác “outbox tồn đọng”

Đề xuất chia hàng đợi thành các nhóm tách biệt:

| Nhóm | Điều kiện tham khảo | Tại sao cần đo riêng |
| --- | --- | --- |
| **Due backlog** | PENDING/RETRY_WAIT và available_at đã đến hạn | Công việc phải được claim nhưng vẫn chờ |
| **Scheduled future** | PENDING/RETRY_WAIT nhưng available_at ở tương lai | Công việc hợp lệ chưa cần gửi |
| **Active in-flight** | IN_FLIGHT, lease còn hiệu lực | Công việc đang được thực hiện |
| **Expired in-flight** | IN_FLIGHT, lease_until đã qua | Có thể worker chết hoặc tiến trình bị treo |
| **Unknown outcomes** | UNKNOWN | Cần xác định đã được provider chấp nhận chưa |
| **Permanent failures** | PERMANENT_FAILED | Cần xử lý lỗi có chủ đích, không tự retry |
| **Terminal outcomes** | ACCEPTED/SUPPRESSED/CANCELLED | Không phải backlog công việc phải gửi |

### Ba câu hỏi khác nhau

1. **Có bao nhiêu việc đang chờ?** Đo số job đã đến hạn.
2. **Việc chờ cũ nhất bao lâu?** Đo tuổi job đã đến hạn và delay vượt SLA.
3. **Có xử lý kịp tốc độ tạo việc không?** So sánh incoming rate và successful/terminal processing rate.

Tổng **COUNT(*)** của mail_outbox thường đánh lừa vì còn chứa hàng triệu bản ghi ACCEPTED phục vụ audit. Tương tự, **COUNT(status=PENDING)** có thể tăng vì lịch gửi trong tương lai được nhập trước, không hẳn worker gặp lỗi.

### Phân biệt hai khái niệm tuổi

Với một notification:

~~~text
created_at   = 08:00
available_at = 13:00
now          = 13:03
~~~

- **Age since creation:** 5 giờ 3 phút. Hữu ích khi đo tổng độ trễ từ lúc sự kiện phát sinh.
- **Delay after eligible:** 3 phút. Hữu ích để xác định worker đã chậm xử lý sau thời điểm đến hạn.

Với email phải gửi ngay, hai giá trị thường gần nhau. Với email theo lịch, dùng tuổi từ created_at làm chỉ số backlog chính sẽ tạo alert sai.

## 4. Các chỉ số quan trọng nhất

<table>
  <tr><th>Chỉ số</th><th>Câu hỏi trả lời</th><th>Hướng xử lý khi bất thường</th></tr>
  <tr><td>Due backlog count</td><td>Bao nhiêu job đang quá thời điểm đủ điều kiện?</td><td>Kiểm tra worker và throughput</td></tr>
  <tr><td>Oldest due age</td><td>Job quá hạn lâu nhất bao nhiêu?</td><td>Ưu tiên job cũ, tìm starvation</td></tr>
  <tr><td>P95/P99 queue delay</td><td>Phần lớn job phải chờ bao lâu trước claim?</td><td>Phân tích tail latency, phân nhóm purpose</td></tr>
  <tr><td>Enqueue rate</td><td>Công việc được tạo nhanh tới đâu?</td><td>So với năng lực xử lý</td></tr>
  <tr><td>Accept/terminal rate</td><td>Công việc rời hàng đợi nhanh tới đâu?</td><td>Kiểm tra SMTP, worker, lỗi</td></tr>
  <tr><td>Retry due count</td><td>Có bao nhiêu retry đến hạn chưa chạy?</td><td>Kiểm tra scheduler/backoff</td></tr>
  <tr><td>Expired leases</td><td>Có attempt được claim nhưng không hoàn thành?</td><td>Kiểm tra worker, crash, network</td></tr>
  <tr><td>UNKNOWN count/age</td><td>Bao nhiêu outcome không rõ và treo bao lâu?</td><td>Đối soát, không replay mù</td></tr>
  <tr><td>SMTP latency/error rate</td><td>Transport đang mất bao lâu, lỗi gì?</td><td>Kiểm tra TLS/AUTH, rate limit, timeout</td></tr>
  <tr><td>Suppressed/failed count</td><td>Job bị loại có chủ đích hay không thể gửi?</td><td>Xử lý theo reason, không retry tràn lan</td></tr>
</table>

Các tên metric cụ thể sẽ được thiết kế trong phần Micrometer. Không có một meter “outbox backlog” mặc định do **JavaMailSender** cung cấp: ứng dụng phải đo trạng thái của outbox/worker.

## 5. Ví dụ schema PostgreSQL cho outbox mail

Để các truy vấn nhất quán, dùng một bảng minh họa:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    notification_key VARCHAR(250) NOT NULL,
    purpose VARCHAR(80) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_attempt_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_owner VARCHAR(120),
    lease_token BIGINT NOT NULL DEFAULT 0,
    lease_until TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    provider VARCHAR(80),
    last_error_category VARCHAR(80),
    CONSTRAINT uq_mail_business_notification
        UNIQUE (tenant_id, notification_key)
);
~~~

Một số điểm thiết kế:

- **id**: định danh bản ghi outbox, nên dùng khi truy vết, không dùng email address làm metric label.
- **notification_key**: khóa logic ổn định để chống tạo nhiều notification cùng một event.
- **purpose/priority**: phân nhóm SLA và thứ tự xử lý; cần policy công bằng để tránh starvation.
- **available_at**: thời điểm sớm nhất có thể claim, bao gồm lịch gửi và retry backoff.
- **created_at**: thời điểm notification được ghi, dùng để đo end-to-end age.
- **lease_owner/lease_token/lease_until**: phục vụ claim, phát hiện attempt bị mất chủ.
- **status**: trạng thái có semantics rõ.
- **last_error_category**: mã phân loại an toàn cho vận hành, không phải raw SMTP transcript.

Đây là schema **tự thiết kế**, không phải DDL của Spring Mail. Cần điều chỉnh theo PostgreSQL version, ORM, partitioning, yêu cầu retention và nhiều tenant của sản phẩm. Bảng này cũng không chứa recipient PII hoặc MIME payload để ví dụ tập trung vào backlog; ứng dụng thật có thể lưu chúng ở storage/bảng riêng theo chính sách bảo mật.

### Chỉ mục hỗ trợ truy vấn due job

~~~sql
CREATE INDEX idx_mail_outbox_due
ON mail_outbox (priority, available_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX idx_mail_outbox_due_time
ON mail_outbox (available_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX idx_mail_outbox_lease_expired
ON mail_outbox (lease_until, id)
WHERE status = 'IN_FLIGHT';

CREATE INDEX idx_mail_outbox_unknown_age
ON mail_outbox (updated_at, id)
WHERE status = 'UNKNOWN';
~~~

Không nhất thiết tạo cả hai chỉ mục due trong mọi hệ thống. Nếu worker luôn claim theo **priority rồi available_at**, index đầu có thể hữu ích; nếu dashboard chủ yếu truy vấn theo available_at, index thứ hai có thể phù hợp hơn. Cần đánh giá **EXPLAIN ANALYZE**, write overhead và distribution dữ liệu trong môi trường thực. Index hỗ trợ workload, không thay thế phân tích bottleneck.

## 6. Truy vấn trạng thái tổng quan, không nhầm scheduled với overdue

PostgreSQL hỗ trợ aggregate **FILTER** để thống kê nhiều nhóm trong cùng một lần đọc:

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status IN ('PENDING', 'RETRY_WAIT')
          AND available_at <= CURRENT_TIMESTAMP
    ) AS due_backlog,
    COUNT(*) FILTER (
        WHERE status IN ('PENDING', 'RETRY_WAIT')
          AND available_at > CURRENT_TIMESTAMP
    ) AS scheduled_future,
    COUNT(*) FILTER (
        WHERE status = 'IN_FLIGHT'
          AND lease_until > CURRENT_TIMESTAMP
    ) AS active_in_flight,
    COUNT(*) FILTER (
        WHERE status = 'IN_FLIGHT'
          AND (
              lease_until IS NULL
              OR lease_until <= CURRENT_TIMESTAMP
          )
    ) AS expired_or_invalid_lease,
    COUNT(*) FILTER (WHERE status = 'UNKNOWN') AS unknown_count,
    COUNT(*) FILTER (
        WHERE status = 'PERMANENT_FAILED'
    ) AS permanent_failed_count
FROM mail_outbox;
~~~

**Lưu ý:** đây là truy vấn phục vụ dashboard/điều tra, không nên chạy **COUNT(*) trên toàn bộ bảng rất lớn mỗi giây** mà không đánh giá tải. Với dataset lớn, có thể dùng metrics được tổng hợp bởi worker, bảng thống kê theo bucket, truy vấn định kỳ có index/partition hoặc event stream và đối chiếu bằng SQL khi cần.

### Truy vấn job đã đến hạn cũ nhất

~~~sql
SELECT
    id,
    tenant_id,
    purpose,
    status,
    priority,
    created_at,
    available_at,
    CURRENT_TIMESTAMP - available_at AS overdue_duration,
    attempt_count,
    last_error_category
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= CURRENT_TIMESTAMP
ORDER BY available_at ASC, id ASC
LIMIT 20;
~~~

Truy vấn này ưu tiên **available_at** cũ nhất để thấy những công việc đã đủ điều kiện từ lâu. Nó không cần lấy recipient email hoặc nội dung thư, tránh lộ PII trong màn hình vận hành.

### Tính tuổi quá hạn lớn nhất theo giây

~~~sql
SELECT COALESCE(
    EXTRACT(EPOCH FROM (
        CURRENT_TIMESTAMP - MIN(available_at)
    )),
    0
) AS oldest_due_age_seconds
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= CURRENT_TIMESTAMP;
~~~

Khi không có job đến hạn, **MIN(available_at)** là NULL nên kết quả được đặt là 0 trong ví dụ. Dashboard cần phân biệt **không có backlog** với **không truy vấn được database**; không ghi 0 khi truy vấn thất bại.

### Thống kê theo trạng thái và purpose

~~~sql
SELECT
    purpose,
    status,
    COUNT(*) AS job_count,
    MIN(available_at) AS oldest_available_at,
    MAX(attempt_count) AS max_attempts
FROM mail_outbox
WHERE status NOT IN (
    'ACCEPTED', 'SUPPRESSED', 'CANCELLED'
)
GROUP BY purpose, status
ORDER BY purpose, status;
~~~

Phân nhóm giúp nhận ra tình huống toàn bộ email marketing đang backlog do rate limit, trong khi email bảo mật vẫn được xử lý bình thường; hoặc ngược lại, email xác nhận đăng nhập bị starve vì worker ưu tiên một campaign quá lớn.

## 7. Nhìn độ trễ theo mục đích gửi và SLA

Không phải mọi loại mail cần cùng một thời gian xử lý:

| Loại notification | Ví dụ | Ý nghĩa khi chậm |
| --- | --- | --- |
| **Security-critical** | Mã xác thực, đặt lại mật khẩu | Đường đăng nhập có thể không dùng được; token có thể hết hạn |
| **Transactional** | Xác nhận đơn, biên nhận | Người dùng hoang mang hoặc liên hệ support |
| **Operational** | Thông báo vận hành tới khách hàng | Cập nhật quan trọng bị trễ |
| **Product update** | Thông báo tính năng | Thường có độ linh hoạt cao hơn |
| **Marketing scheduled** | Newsletter, campaign | Có lịch gửi, không nên coi trước giờ hẹn là backlog |

SLA cụ thể phải được thiết kế theo sản phẩm, không có giá trị mặc định chung của Spring Framework Mail. Ví dụ **oldest_due_age_seconds** lớn hơn 120 giây có thể nghiêm trọng với OTP nhưng không nhất thiết nghiêm trọng với một bản tin theo lô.

### Truy vấn độ trễ theo purpose

~~~sql
SELECT
    purpose,
    COUNT(*) AS due_jobs,
    COALESCE(
        EXTRACT(EPOCH FROM (
            CURRENT_TIMESTAMP - MIN(available_at)
        )),
        0
    ) AS oldest_due_seconds,
    COALESCE(
        EXTRACT(EPOCH FROM (
            CURRENT_TIMESTAMP - MIN(created_at)
        )),
        0
    ) AS oldest_end_to_end_seconds
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= CURRENT_TIMESTAMP
GROUP BY purpose
ORDER BY oldest_due_seconds DESC;
~~~

Kết quả cần được đối chiếu với lịch gửi và retry policy. Một job **RETRY_WAIT** mới đến hạn sau nhiều lần backoff có thể đã được tạo từ lâu, nên end-to-end age lớn nhưng worker mới thực sự quá hạn trong thời gian ngắn.

### Sự khác nhau giữa queue delay và end-to-end latency

Đối với một job:

~~~text
T0 created_at
     |
T1 available_at
     |
T2 first_claimed_at
     |
T3 SMTP accepted_at
~~~

- **Eligibility wait:** T2 - T1, phản ánh scheduler/worker backlog.
- **Processing duration:** T3 - T2, phản ánh thời gian xử lý và SMTP.
- **End-to-end latency:** T3 - T0, phản ánh trải nghiệm từ lúc nghiệp vụ phát sinh đến lúc SMTP accepted.

Nếu có lịch gửi trong tương lai, end-to-end latency bao gồm thời gian chờ có chủ đích. Khi đo SLO cho mail gửi ngay, có thể dùng T3 - T0; với mail theo lịch, nên đo **T3 - T1** hoặc một deadline cụ thể.

### Bản ghi nên chứa các mốc thời gian có nghĩa

Các timestamp hữu ích là created_at, available_at, first_claimed_at, last_attempt_at, accepted_at và updated_at. Không dùng duy nhất **updated_at** để suy ra tuổi backlog, vì field này có thể được làm mới do heartbeat/lease hoặc retry mà không có tiến triển thực sự.

Nếu job được claim nhiều lần, nên có bảng **mail_attempt** riêng để ghi lịch sử từng lần thử, giúp biết queue delay, SMTP duration và lỗi của mỗi attempt. Một field last_attempt_at không thay thế được toàn bộ lịch sử.

## 8. Phát hiện backlog đang tăng hay đang giảm

Một snapshot hiện tại có thể cho thấy 10.000 job đến hạn. Nhưng hệ thống đang xử lý 20.000 job/phút và sẽ sớm hết backlog, hay đang chỉ xử lý 100 job/phút trong khi tạo thêm 5.000 job/phút?

Để trả lời, cần **tốc độ đến** và **tốc độ xử lý**:

~~~text
incoming_rate  = notifications created / second
terminal_rate  = notifications reaching a terminal state / second
net_growth     ~= incoming_rate - terminal_rate
~~~

Khi **incoming_rate vượt terminal_rate** trong một khoảng đủ dài, tổng công việc chưa kết thúc có xu hướng tăng. Tuy nhiên, **due backlog** có thể tăng/giảm không hoàn toàn theo phương trình đơn giản đó do job scheduled, retry backoff, suppression hoặc dịch chuyển giữa các state. Hãy dùng công thức như tín hiệu xu hướng, không thay thế đo các nhóm trạng thái.

### Ví dụ minh họa

~~~text
Enqueued:    2.000 notification/phút
Accepted:    1.100 notification/phút
Suppressed:    100 notification/phút
Failed final:   50 notification/phút

Net outstanding growth ≈ 750 notification/phút
~~~

Nếu tốc độ này giữ 20 phút, số notification chưa terminal có thể tăng khoảng 15.000, bỏ qua thay đổi lịch và các trạng thái đặc biệt. Đây là dấu hiệu cần điều tra năng lực worker hoặc lỗi upstream.

### Không đánh đồng attempts với notifications

Nếu một job thất bại và retry năm lần, metric **attempts_total** tăng năm lần nhưng **notifications_created_total** chỉ tăng một lần. Khi tính throughput thực sự, nên dùng số **notification đạt ACCEPTED lần đầu**, không phải tổng số lần gọi JavaMailSender.send(...). Nếu không, một hệ thống gửi thất bại liên tục có thể trông như đang “xử lý rất nhiều thư”.

### Năng lực và dự báo thời gian giải phóng backlog

Giả sử backlog đã đến hạn là **B** và năng lực xử lý terminal thực tế cao hơn tốc độ công việc đến hạn mới là **D = processing_rate - due_arrival_rate**, với D lớn hơn 0. Có thể ước lượng:

\[
\text{estimated drain time} \approx \frac{B}{D}
\]

Đây chỉ là xấp xỉ khi tốc độ ổn định, job có chi phí gần giống nhau và không có biến động lớn do retry, provider throttling hoặc thay đổi lịch gửi. Nếu D nhỏ hơn hoặc bằng 0, backlog sẽ không tự được giải phóng dưới tải hiện tại.

Ví dụ: 6.000 job đến hạn, năng lực xử lý 150 job/phút và 50 job/phút mới đến hạn. Năng lực giải phóng ròng khoảng 100 job/phút, tức xấp xỉ 60 phút. Không dùng ước lượng này như lời hứa giao hàng chính xác.

## 9. Phân tích P95/P99 delay thay vì chỉ giá trị trung bình

Trung bình queue delay thấp không bảo đảm không có job bị treo. Ví dụ 99% email được xử lý sau 1 giây nhưng 1% còn lại đợi 30 phút; average có thể che khuất tail latency trong một số phân bố tải.

Các chỉ số nên tách:

- **Oldest due age:** nêu chính xác trường hợp chậm nhất hiện tại.
- **P50/P95/P99 queue delay:** cho biết trải nghiệm phân bố của job đã được claim.
- **P95/P99 end-to-end acceptance latency:** cho biết độ trễ từ đủ điều kiện đến transport accepted.
- **Count of jobs beyond SLA:** số job hiện vượt ngưỡng theo purpose.

### Ví dụ SQL đếm job quá SLA theo purpose

Giả sử chính sách ứng dụng quy định ngưỡng tính bằng giây trong một bảng hoặc một cấu hình đáng tin cậy. Ví dụ điều tra nhanh với một ngưỡng minh họa:

~~~sql
SELECT
    purpose,
    COUNT(*) AS overdue_over_5_minutes
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'
GROUP BY purpose
ORDER BY overdue_over_5_minutes DESC;
~~~

Không mặc định 5 phút là SLA cho mọi purpose. Với OTP có thể cần ngưỡng chặt hơn, còn marketing theo lô có thể khác. Một bảng policy chứa purpose + maximum_due_delay thường phù hợp hơn việc hard-code ngưỡng trong tất cả dashboard.

### Percentile nên đo trên event hoàn thành

P95 delay từ thời điểm job được claim có thể ghi trực tiếp vào **Micrometer Timer** hoặc histogram. Không nên tính percentiles bằng cách lấy một tập rất lớn job PENDING rồi gửi tất cả lên ứng dụng; điều đó vừa tốn database vừa khó diễn giải khi job đang thay đổi.

Histogram/metrics cần có retention và labels phù hợp. Tránh đưa recipient ID hoặc notification ID vào tags vì cardinality tăng rất nhanh.

## 10. Truy vấn IN_FLIGHT quá hạn và worker bị mất

Một job bị IN_FLIGHT lâu có thể do SMTP chậm, process crash hoặc lease không được gia hạn. Truy vấn:

~~~sql
SELECT
    id,
    tenant_id,
    purpose,
    lease_owner,
    lease_token,
    lease_until,
    last_attempt_at,
    attempt_count,
    last_error_category
FROM mail_outbox
WHERE status = 'IN_FLIGHT'
  AND (
      lease_until IS NULL
      OR lease_until <= CURRENT_TIMESTAMP
  )
ORDER BY lease_until NULLS FIRST, id
LIMIT 100;
~~~

**lease_until IS NULL** trong IN_FLIGHT là dấu hiệu trạng thái không hợp lệ nếu hệ thống yêu cầu mọi claim đều có lease. Không bỏ qua nó chỉ vì phép so sánh NULL không trả true trong SQL.

### Lease quá hạn chưa chắc email chưa gửi

Một worker có thể:

1. Claim job và commit IN_FLIGHT.
2. Gửi message, SMTP server chấp nhận.
3. Worker chết trước khi lưu ACCEPTED.
4. Lease hết hạn.

Nếu tự đổi tất cả expired leases thành PENDING và retry, recipient có thể nhận email lần hai. Vì vậy:

~~~text
IN_FLIGHT + expired lease
           |
           v
          UNKNOWN
           |
           v
  Reconcile / safe retry policy
~~~

UNKNOWN không phải tình trạng “mất job”; đây là trạng thái để hệ thống ngừng suy đoán và tìm bằng chứng hoặc ra quyết định rủi ro rõ ràng.

### Lease không chỉ để đặt deadline

Các trường **lease_owner**, **lease_token** và **lease_until** giúp:

- Một worker claim job trong một khoảng thời gian xác định.
- Phát hiện worker không hoàn thành.
- Ngăn worker cũ ghi đè kết quả của worker mới bằng điều kiện **lease_token**.
- Thống kê worker/instance nào thường xuyên có lease hết hạn.

**Fencing token chỉ bảo vệ cập nhật storage**, không ngăn một SMTP submission bên ngoài đã xảy ra. Đừng khẳng định chính sách lease tạo exactly-once email delivery.

### Truy vấn thống kê theo worker

~~~sql
SELECT
    lease_owner,
    COUNT(*) AS active_jobs,
    MIN(last_attempt_at) AS oldest_attempt_started
FROM mail_outbox
WHERE status = 'IN_FLIGHT'
GROUP BY lease_owner
ORDER BY active_jobs DESC;
~~~

Nếu một worker có nhiều job đang xử lý cùng lúc, cần đối chiếu với **worker concurrency**, số kết nối SMTP và queue executor. Lease_owner không nên chứa bí mật; tên instance hoặc opaque ID đủ cho vận hành.

## 11. Trạng thái UNKNOWN phải có bảng quan sát riêng

Một email có thể gặp timeout sau khi đã truyền xong SMTP DATA; server có thể đã nhận thư nhưng client không nhận final response. Nếu JavaMailSender báo lỗi, không có bằng chứng chắc chắn rằng message chưa được chấp nhận.

Với outbox, **UNKNOWN** cần:

- Số notification đang chờ đối soát.
- Tuổi UNKNOWN cũ nhất.
- Lý do/loại exception gần nhất.
- Provider được dùng khi attempt.
- Correlation ID hoặc Message-ID để tra cứu nếu provider hỗ trợ.
- Số lượng UNKNOWN vừa được xác nhận ACCEPTED, retry an toàn hoặc escalated.

### Truy vấn UNKNOWN cũ

~~~sql
SELECT
    id,
    tenant_id,
    purpose,
    provider,
    updated_at,
    last_attempt_at,
    CURRENT_TIMESTAMP - updated_at AS unknown_duration,
    attempt_count,
    last_error_category
FROM mail_outbox
WHERE status = 'UNKNOWN'
ORDER BY updated_at ASC, id
LIMIT 100;
~~~

Truy vấn giả định **updated_at** được ghi tại thời điểm chuyển sang UNKNOWN và không bị thay đổi liên tục vì heartbeat/monitoring. Nếu ứng dụng có nhiều thao tác chỉnh sửa record UNKNOWN, nên thêm **unknown_since** riêng để tuổi UNKNOWN luôn chính xác.

### Reconciliation khác retry

~~~text
UNKNOWN
  |
  v
Tìm bằng chứng ở mail provider / SMTP logs / webhook
  |
  +-- Có bằng chứng accepted --> ACCEPTED
  |
  +-- Chứng minh chưa được nhận --> RETRY_WAIT / PENDING
  |
  '-- Không đủ bằng chứng --> Giữ UNKNOWN / NEEDS_REVIEW
~~~

SMTP thuần không có API tiêu chuẩn để hỏi “message có khóa K được chấp nhận chưa”. **Message-ID** hỗ trợ correlation nhưng không phải khóa idempotency chung. Một provider API có chức năng tra cứu/idempotency có thể giúp giải quyết UNKNOWN, nhưng phải dựa trên khả năng và thời hạn lưu key được công bố.

Nếu hệ thống quyết định retry UNKNOWN vì mục tiêu không bỏ lỡ email, phải thừa nhận và ghi lại **nguy cơ gửi trùng**. Không thể đảm bảo SMTP gửi đúng một lần chỉ bằng outbox và retry.

## 12. Lịch retry và backoff cũng có thể gây “tồn đọng”

Một đợt SMTP outage có thể khiến nhiều job chuyển sang RETRY_WAIT. Sau khi provider phục hồi, các job có thể đến hạn cùng lúc:

~~~text
10:00 Provider lỗi
10:01 10.000 job nhận lỗi tạm thời
10:02 Scheduled retry lúc 10:07
10:07 10.000 job cùng đủ điều kiện
      -> retry storm
~~~

Thay vì đặt tất cả next retry cùng một thời điểm, dùng **exponential backoff + jitter**, giới hạn attempts và tổng thời gian retry.

~~~text
base delay: 10s
max delay: 10m
delay: min(max delay, base * 2^(attempt-1))
actual delay: delay * random factor
~~~

Đây là ví dụ chính sách, không phải ngưỡng mặc định của Spring Mail. Với lỗi **4xx đã xác nhận** có thể retry theo provider policy; với lỗi vĩnh viễn **5xx** cần phân loại; với **timeout kết quả không rõ** cần UNKNOWN/reconciliation thay vì retry mù.

### Phân biệt số đang chờ backoff và số retry đã quá hạn

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE available_at > CURRENT_TIMESTAMP
    ) AS retry_not_due,
    COUNT(*) FILTER (
        WHERE available_at <= CURRENT_TIMESTAMP
    ) AS retry_due
FROM mail_outbox
WHERE status = 'RETRY_WAIT';
~~~

Không alert vì **retry_not_due** tăng một cách đơn lẻ nếu chính sách đang cố ý giảm tải sau outage. Nhưng cần quan sát **retry_due**, tuổi retry quá hạn và tốc độ provider phục hồi.

### Không giải quyết backlog bằng cách xóa backoff

Việc đặt toàn bộ **available_at=CURRENT_TIMESTAMP** có thể tạo một đợt gửi dồn, vượt rate limit hoặc gây spam. Nếu cần tăng tốc phục hồi, hãy nâng throughput có kiểm soát, giữ jitter và điều phối theo quota của provider.

## 13. Nhìn từ database tới SMTP transport

Khi backlog tăng, phải biết bottleneck nằm ở tầng nào:

~~~text
Outbox SQL / database
        |
        v
Claim worker
        |
        v
Executor / concurrency
        |
        v
Render template / MIME
        |
        v
JavaMailSender
        |
        v
SMTP network + TLS/AUTH
        |
        v
SMTP server acceptance
~~~

Một vấn đề ở bất kỳ giai đoạn nào cũng có thể làm due backlog tăng:

| Dấu hiệu | Khả năng nguyên nhân | Dữ liệu kiểm tra |
| --- | --- | --- |
| Due backlog tăng, không có claim | Scheduler chết, query không chọn job, lock | Worker heartbeat, poll count, DB locks |
| Claim rate cao, accepted rate bằng 0 | SMTP lỗi, render exception, AUTH | Error categories, SMTP latency, exception logs |
| IN_FLIGHT tăng, worker threads bận | SMTP chậm hoặc timeout cấu hình thiếu | Thread dumps, socket timeouts, executor stats |
| RETRY_WAIT tăng | Provider throttle, network outage | SMTP 4xx, retry distribution |
| UNKNOWN tăng | Timeout mơ hồ hoặc worker crash sau submission | Last stage, provider evidence, lease expiry |
| Job của một tenant chờ lâu | Noisy neighbor, priority starvation | Due age theo tenant/purpose/priority |
| Database CPU/lock tăng | Query claim kém index hoặc transaction dài | EXPLAIN, pg_stat_activity, lock waits |
| Accepted rate tăng nhưng user không thấy email | Delivery/bounce/spam sau provider | ESP webhook, bounce events, deliverability |

**JavaMailSender.send(...) thành công** chỉ là một bước quan sát. Nếu vấn đề là thư được provider chấp nhận nhưng không tới hộp thư, cần chuyển sang theo dõi **delivery status**, suppression, bounce và danh tiếng gửi, không kết luận outbox worker còn bị kẹt.

## 14. Kiểm tra worker scheduler và cơ chế claim

Một outbox worker thường có vòng lặp:

~~~text
poll due jobs
     |
     v
claim atomically
     |
     v
commit claim
     |
     v
execute SMTP outside DB transaction
     |
     v
commit outcome in separate transaction
     |
     v
repeat
~~~

Nếu worker không claim được job, dù database có nhiều record PENDING, cần phân biệt:

- **Worker không chạy:** scheduler chưa bật, instance đang down, leader election/feature flag.
- **Worker chạy nhưng không thấy job:** WHERE condition sai, available_at chưa đến hạn, filtering tenant/priority sai, timezone.
- **Worker query lỗi:** database connection pool, timeout, deadlock, permission hoặc schema mismatch.
- **Worker liên tục SKIP LOCKED:** có transaction khác đang khóa nhiều row.
- **Worker có claim nhưng không gửi:** executor đầy, template render lỗi, circuit breaker hoặc SMTP không khả dụng.

### SQL claim nhiều worker với SKIP LOCKED

Một câu lệnh PostgreSQL tham khảo:

~~~sql
WITH candidate AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND available_at <= CURRENT_TIMESTAMP
    ORDER BY priority ASC, available_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_outbox AS m
SET
    status = 'IN_FLIGHT',
    lease_owner = :worker_id,
    lease_token = m.lease_token + 1,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    last_attempt_at = CURRENT_TIMESTAMP,
    attempt_count = m.attempt_count + 1,
    updated_at = CURRENT_TIMESTAMP
FROM candidate
WHERE m.id = candidate.id
RETURNING
    m.id,
    m.tenant_id,
    m.purpose,
    m.notification_key,
    m.attempt_count,
    m.lease_token,
    m.lease_until;
~~~

**:worker_id** là tham số được bind từ ứng dụng. Ví dụ giả định priority thấp hơn có mức ưu tiên cao hơn. Transaction claim phải ngắn và **commit trước khi kết nối SMTP**, vì không nên giữ database row lock suốt quá trình chờ network.

### Đừng dùng SKIP LOCKED làm bằng chứng không có job

Khi **SKIP LOCKED** được sử dụng, một worker có thể không thấy những row đang được transaction khác khóa. Một kết quả **0 row returned** có thể có nghĩa:

- Không có job đến hạn.
- Các job phù hợp đều đang bị lock.
- Bộ lọc của worker không khớp.

Dashboard cần đếm due jobs dựa trên trạng thái/available_at độc lập với kết quả claim để phát hiện chênh lệch. Nếu due count lớn nhưng claim count bằng 0, kiểm tra lock/transaction và điều kiện query.

### Query plan và index

Dùng **EXPLAIN (ANALYZE, BUFFERS)** có kiểm soát khi điều tra:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= CURRENT_TIMESTAMP
ORDER BY priority ASC, available_at ASC, id ASC
LIMIT 100;
~~~

Một truy vấn SELECT thường đơn giản hơn để quan sát chi phí lọc/sắp xếp trước, rồi mới phân tích câu lệnh claim trong môi trường an toàn. **EXPLAIN ANALYZE thực thi query**; đối với UPDATE/DELETE, tránh chạy trực tiếp trên production nếu không có kế hoạch transaction/rollback và quyền thao tác phù hợp.

Nếu bảng chứa rất nhiều bản ghi terminal, thiếu partial index có thể khiến worker quét/sắp xếp dữ liệu tốn kém. Nhưng thêm index cũng làm tăng write amplification và dung lượng, nên chọn dựa trên workload.

### Claim nhanh không đồng nghĩa gửi nhanh

Một worker có thể claim 1.000 job/phút nhưng chỉ nộp 50 email/phút do SMTP latency hoặc pool không đủ. Nếu claim quá sớm so với năng lực xử lý, nhiều job sẽ IN_FLIGHT, lease có nguy cơ hết hạn trước khi bắt đầu gửi.

Vì vậy:

- Giới hạn số job claim theo concurrency thực sự.
- Không pre-claim quá nhiều trong một transaction.
- Theo dõi **claimed_jobs**, **executor_queue_depth** và **smtp_submission_duration**.
- Chỉ tăng batch size khi đã biết bottleneck nằm ở database polling.

## 15. Worker heartbeat, lease và zombie worker

Một instance worker có thể vẫn chạy process nhưng không xử lý job vì scheduler thread đã chết, circuit breaker đang mở hoặc không lấy được connection. Vì vậy metric **process_up** chưa đủ để chứng minh dispatcher khỏe.

Các tín hiệu hữu ích:

- **Last successful poll timestamp:** lần gần nhất query due jobs thành công.
- **Last successful claim timestamp:** lần gần nhất claim được job.
- **Last terminal transition timestamp:** lần gần nhất ACCEPTED/SUPPRESSED/PERMANENT_FAILED.
- **Poll errors total:** số lỗi đọc/claim database.
- **Active worker threads:** số tác vụ đang xử lý.
- **Lease renewals/expirations:** worker có bị quá thời hạn.
- **Last SMTP success timestamp:** lần cuối provider chấp nhận một message.

### Khi nào không có claim là bình thường?

Nếu **due backlog = 0**, việc 30 phút không có successful claim có thể hoàn toàn bình thường. Không nên alert “worker đã chết” chỉ vì không có email cần gửi. Một alert có ý nghĩa hơn:

~~~text
due_backlog > 0
AND no successful claim for N minutes
AND scheduler should be active
~~~

### Lease duration phải tương thích timeout SMTP

Giả sử:

~~~text
Lease duration            = 15s
SMTP connection timeout   = 10s
SMTP read timeout         = 30s
SMTP write timeout        = 30s
~~~

Một message có thể đang xử lý hợp lệ nhưng lease hết hạn trước khi network operation hoàn tất. Để giảm expired leases sai:

- Đặt lease đủ cho tác vụ và điều kiện tải.
- Có heartbeat/renewal an toàn nếu tác vụ thực sự dài.
- Không claim nhiều hơn năng lực worker.
- Giới hạn SMTP timeouts.
- Giữ **lease_token** để chặn stale DB updates.
- Vẫn chuyển outcome mơ hồ thành UNKNOWN khi không biết đã gửi hay chưa.

Không có một công thức lease duration duy nhất; cần quan sát distribution thời gian xử lý và worst-case/GC pauses.

### Worker cũ hoàn tất sau khi mất lease

Nếu worker A chậm rồi lease hết hạn, worker B hoặc recovery job có thể thay đổi trạng thái. A không được ghi đè bằng một UPDATE thiếu điều kiện.

~~~sql
UPDATE mail_outbox
SET
    status = 'ACCEPTED',
    accepted_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND status = 'IN_FLIGHT'
  AND lease_owner = :worker_id
  AND lease_token = :lease_token;
~~~

Nếu câu lệnh ảnh hưởng **0 row**, worker đã mất quyền hoặc trạng thái không còn phù hợp. Hệ thống có thể ghi nhận một late outcome vào bảng attempt để reconciliation sử dụng, nhưng không nên bỏ qua điều kiện fencing chỉ để “fix” trạng thái.

## 16. Instrumentation với Spring Boot Actuator và Micrometer

**Spring Boot Actuator** và **Micrometer** có thể xuất các metric ứng dụng qua Prometheus hoặc hệ thống observability đang dùng. Đối với outbox, phần lớn metric phải được **ứng dụng tự tạo**.

Một tập metric gợi ý:

| Tên logic | Loại | Ý nghĩa |
| --- | --- | --- |
| **mail_outbox_due_jobs** | Gauge | Job PENDING/RETRY_WAIT đã đến hạn |
| **mail_outbox_oldest_due_seconds** | Gauge | Độ trễ lớn nhất tính từ available_at |
| **mail_outbox_scheduled_jobs** | Gauge | Job chờ lịch trong tương lai |
| **mail_outbox_inflight_jobs** | Gauge | Job IN_FLIGHT |
| **mail_outbox_expired_leases** | Gauge | Job IN_FLIGHT có lease quá hạn/thiếu |
| **mail_outbox_unknown_jobs** | Gauge | Job UNKNOWN cần đối soát |
| **mail_outbox_notifications_enqueued** | Counter | Notification được ghi outbox thành công |
| **mail_outbox_notifications_terminal** | Counter | Notification mới chuyển sang trạng thái terminal |
| **mail_outbox_attempts** | Counter | Số lần worker thử gửi |
| **mail_outbox_queue_wait_seconds** | Timer/histogram | Delay từ available_at đến lúc claim |
| **mail_smtp_submission_seconds** | Timer/histogram | Thời gian gọi transport SMTP |
| **mail_outbox_status_refresh_failures** | Counter | Lỗi khi lấy snapshot metric |

Đây là tên ở tầng Micrometer; khi export sang Prometheus, tên có thể được chuẩn hóa và Counter có hậu tố **_total** theo cơ chế registry. Kiểm tra endpoint metrics thực tế trước khi viết PromQL, không giả định mọi registry giữ tên hoàn toàn giống nhau.

### Một snapshot dữ liệu để cập nhật Gauge

Thay vì thực hiện SQL COUNT(*) mỗi khi Prometheus scrape, có thể định kỳ lấy snapshot rồi cập nhật các Gauge trong bộ nhớ:

~~~java
public record OutboxMonitoringSnapshot(
        long dueJobs,
        long scheduledJobs,
        long inflightJobs,
        long expiredLeases,
        long unknownJobs,
        double oldestDueSeconds
) {
}

public interface OutboxMonitoringRepository {
    OutboxMonitoringSnapshot loadSnapshot();
}
~~~

Repository trên là thành phần do dự án triển khai bằng JDBC/JPA. Nó nên đọc một snapshot nhất quán vừa đủ cho dashboard, hạn chế quét quá nhiều row và không đọc MIME body hoặc PII khi tính thống kê.

### Bean xuất Gauge và cập nhật theo lịch

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OutboxMetricsReporter {

    private final OutboxMonitoringRepository repository;
    private final MeterRegistry registry;

    private final AtomicLong dueJobs = new AtomicLong();
    private final AtomicLong scheduledJobs = new AtomicLong();
    private final AtomicLong inflightJobs = new AtomicLong();
    private final AtomicLong expiredLeases = new AtomicLong();
    private final AtomicLong unknownJobs = new AtomicLong();
    private final AtomicLong oldestDueSeconds = new AtomicLong();
    private final AtomicLong lastSuccessEpoch = new AtomicLong();

    public OutboxMetricsReporter(
            OutboxMonitoringRepository repository,
            MeterRegistry registry
    ) {
        this.repository = repository;
        this.registry = registry;

        registry.gauge("mail_outbox_due_jobs", dueJobs);
        registry.gauge("mail_outbox_scheduled_jobs", scheduledJobs);
        registry.gauge("mail_outbox_inflight_jobs", inflightJobs);
        registry.gauge("mail_outbox_expired_leases", expiredLeases);
        registry.gauge("mail_outbox_unknown_jobs", unknownJobs);
        registry.gauge("mail_outbox_oldest_due_seconds",
                oldestDueSeconds);
        registry.gauge("mail_outbox_metrics_last_success_epoch_seconds",
                lastSuccessEpoch);
    }

    @Scheduled(fixedDelayString =
            "${app.mail.outbox.metrics.refresh-ms:30000}")
    public void refresh() {
        try {
            OutboxMonitoringSnapshot s = repository.loadSnapshot();
            dueJobs.set(s.dueJobs());
            scheduledJobs.set(s.scheduledJobs());
            inflightJobs.set(s.inflightJobs());
            expiredLeases.set(s.expiredLeases());
            unknownJobs.set(s.unknownJobs());
            oldestDueSeconds.set(
                    Math.max(0L, (long) Math.ceil(s.oldestDueSeconds()))
            );
            lastSuccessEpoch.set(Instant.now().getEpochSecond());
        } catch (Exception ex) {
            registry.counter(
                    "mail_outbox_status_refresh_failures"
            ).increment();
            // Log có kiểm soát; không ghi recipient hoặc raw MIME.
            // Không đặt các Gauge về 0 khi database query thất bại.
        }
    }
}
~~~

Mẫu minh họa này dùng **@Scheduled** nên cần bật scheduling trong Spring context (ví dụ **@EnableScheduling**) nếu ứng dụng chưa có. **Gauge có thể bằng 0 trước lần refresh đầu tiên**; metric **last_success_epoch_seconds** cho biết dữ liệu đã từng được tải thành công hay chưa. Các giá trị có thể trễ tối đa theo chu kỳ refresh, nên phải có alert riêng cho dữ liệu stale.

Trong hệ thống nhiều instance, mỗi instance sẽ phát metric snapshot giống nhau nếu tất cả query cùng database; **không được sum các gauge đó một cách mù quáng**, vì sẽ nhân đôi/nhân ba count. Có thể đặt một exporter/leader chuyên đo global backlog, hoặc dùng **max by (...)**/chọn đúng instance để hiển thị. Metric theo worker instance như active tasks nên được xử lý khác với metric toàn bộ database.

### Event counters nên đo ở nơi chuyển trạng thái

Khi ghi một notification outbox thành công hoặc khi trạng thái lần đầu chuyển ACCEPTED, service có thể tăng Counter:

~~~java
registry.counter(
        "mail_outbox_notifications_terminal",
        "outcome", "accepted"
).increment();
~~~

Chú ý **không tăng counter trước một transaction có thể rollback** nếu muốn counter phản ánh sự kiện durable. Nếu xảy ra crash sau DB commit nhưng trước khi ghi metric, counter trong bộ nhớ vẫn có thể thiếu sự kiện. Vì vậy với yêu cầu audit/chính xác tuyệt đối, dùng DB/event stream làm nguồn đối chiếu; metric ứng dụng là tín hiệu vận hành gần thời gian thực, không phải sổ cái.

### Tags có cardinality thấp

Nên dùng các tags hữu hạn như **purpose**, **status**, **provider**, **result**, hoặc **worker_role**. Không dùng recipient email, notification ID, order ID hoặc raw exception text làm tags. Metric high-cardinality gây tốn bộ nhớ/storage và có thể làm lộ dữ liệu cá nhân.

## 17. Dashboard giám sát outbox mail

Một dashboard nên trả lời được cả **tình trạng hiện tại**, **xu hướng** và **nguyên nhân** mà không cần người vận hành mở ngay SQL console.

### Bố cục đề xuất

~~~text
MAIL OUTBOX — OVERVIEW

Due jobs        Oldest due        UNKNOWN        Expired lease
   1,240          08m 12s           12                3

Due backlog over time           Enqueued vs terminal / minute
          /\                             incoming  --__
      ___/  \___                         terminal  ---_
  ___/          \__                      backlog trend

By purpose                      SMTP results
SECURITY     25                 accepted      85%
TRANSACTION  215                temp failure  11%
MARKETING    1,000              unknown        2%
                                permanent      2%

Workers                          Top error categories
active      8                    RATE_LIMIT     750
last claim  3s ago               AUTH_ERROR     220
leases      3 expired            READ_TIMEOUT    20
~~~

Các số ở trên chỉ minh họa cách trình bày, không phải dữ liệu hệ thống thật. Nên đặt **timestamp cập nhật metric** và tình trạng kết nối data source ở vị trí dễ thấy.

### Các panel tối thiểu

| Panel | Kiểu dữ liệu | Tác dụng |
| --- | --- | --- |
| Due backlog count | Single value + timeline | Phát hiện job đang chờ đến hạn |
| Oldest due age | Single value + timeline | Phát hiện vi phạm SLA |
| Due count by purpose | Grouped bar/stack | Phân biệt security và marketing |
| Enqueue/terminal rate | Hai line series | Nhận biết backlog đang tăng |
| In-flight and expired leases | Gauge/time series | Phát hiện worker treo |
| Retry due vs future | Stacked series | Phân biệt backoff có chủ đích |
| Unknown count and oldest age | Single value + table | Tập trung đối soát |
| SMTP latency/error rate | Histogram/time series | Xác định bottleneck transport |
| Worker poll/claim/heartbeat | Time series | Phân biệt worker chết và không có việc |
| Metric snapshot age | Single value | Phân biệt dữ liệu hiện tại và stale |

Một dashboard chỉ có tổng **PENDING** và **ACCEPTED** sẽ không đủ để xử lý incident vì không thể thấy job theo lịch, retry hoặc UNKNOWN.

### Không cộng trùng metrics đa instance

Khi mỗi replica Spring Boot query cùng bảng mail_outbox, các gauge global có thể trùng nhau. Ví dụ ba pod cùng báo **due_jobs=100**; phép sum của Prometheus trả **300** nhưng database chỉ có 100.

Các cách giải quyết:

- Dành một **metrics collector leader** chịu trách nhiệm export global backlog.
- Sử dụng metric từ một job/instance exporter duy nhất.
- Dùng phép tổng hợp **max** phù hợp khi tất cả replica đo cùng một global state.
- Với metrics mang nghĩa **per-worker**, mới dùng sum theo pod/instance khi cần tổng năng lực.

Giải pháp tổng hợp phải dựa trên ngữ nghĩa metric. Không có quy tắc “luôn sum mọi gauge” hoặc “luôn max mọi gauge”.

## 18. Ví dụ PromQL để xem tồn đọng

Giả sử registry xuất:

~~~text
mail_outbox_due_jobs
mail_outbox_oldest_due_seconds
mail_outbox_unknown_jobs
mail_outbox_expired_leases
mail_outbox_metrics_last_success_epoch_seconds
mail_outbox_notifications_enqueued_total
mail_outbox_notifications_terminal_total
~~~

Đây là tên **ví dụ sau khi export**. Cần kiểm tra tên thực tế ở endpoint Actuator/Prometheus vì các registry có thể đổi dấu chấm, dấu gạch dưới, unit suffix và Counter naming.

### Xem backlog hiện tại

~~~promql
mail_outbox_due_jobs
~~~

### Tuổi job đến hạn lớn nhất

~~~promql
mail_outbox_oldest_due_seconds
~~~

### Hàng đợi đã lớn và quá hạn đáng kể

~~~promql
(mail_outbox_due_jobs > 100)
and
(mail_outbox_oldest_due_seconds > 300)
~~~

Biểu thức trên giả định hai series có **bộ labels tương ứng**. Nếu một metric có nhãn purpose/tenant mà metric kia không có, cần điều chỉnh vector matching hoặc aggregation cho đúng, tránh nhầm kết quả do labels không khớp.

### Tốc độ notification được tạo

~~~promql
rate(mail_outbox_notifications_enqueued_total[5m])
~~~

### Tốc độ notification đạt trạng thái terminal

~~~promql
rate(mail_outbox_notifications_terminal_total[5m])
~~~

Nếu terminal metric có label **outcome**, muốn tính tổng cho một phạm vi có thể dùng:

~~~promql
sum without (outcome) (
    rate(mail_outbox_notifications_terminal_total[5m])
)
~~~

Không đưa **attempts_total** vào phép so sánh throughput notification vì một notification có thể có nhiều attempts.

### Phát hiện metric snapshot stale

~~~promql
time() - mail_outbox_metrics_last_success_epoch_seconds > 180
~~~

Ví dụ giả định snapshot được refresh thường xuyên hơn 180 giây. Khi exporter chưa refresh lần nào, giá trị last_success bằng 0 và biểu thức báo stale, đây là hành vi cần chú ý khi startup. Nếu exporter không tồn tại hoặc Prometheus không scrape được, biểu thức này có thể không trả series; cần alert riêng cho **up == 0** hoặc **absent(...)**.

### Thống kê UNKNOWN và expired lease

~~~promql
mail_outbox_unknown_jobs
~~~

~~~promql
mail_outbox_expired_leases
~~~

Với UNKNOWN/expired leases, nhiều hệ thống muốn cảnh báo ngay khi có bất thường bền vững thay vì chờ backlog count lên hàng nghìn. Ngưỡng cụ thể tùy RTO, khả năng reconciliation và hệ thống có support on-call.

## 19. Thiết kế alert tránh báo động giả

Nếu mỗi đợt campaign tạo 100.000 bản ghi **scheduled future**, alert dựa trên tổng PENDING có thể báo động dù hệ thống khỏe. Alert cần gắn với **điều kiện đến hạn** và **thời gian tồn tại**, đồng thời phân loại theo purpose.

### Các cảnh báo gợi ý

| Alert | Điều kiện minh họa | Hành động |
| --- | --- | --- |
| **Due backlog growing** | Due lớn và tăng liên tục | Kiểm tra processing/arrival rate |
| **Oldest due SLA breach** | Oldest due age vượt SLA | Ưu tiên purpose bị ảnh hưởng |
| **No progress** | Due > 0 nhưng không terminal/claim tiến triển | Kiểm tra scheduler/worker |
| **Expired leases** | Có nhiều IN_FLIGHT quá lease | Kiểm tra worker crash và UNKNOWN |
| **UNKNOWN backlog** | UNKNOWN quá ngưỡng số lượng/tuổi | Chạy reconciliation có kiểm soát |
| **Retry storm** | Retry due tăng đột biến | Rate limit, backoff/jitter |
| **Metrics stale** | Snapshot quá cũ hoặc exporter down | Không dùng gauge cũ để kết luận |
| **SMTP error spike** | Transport errors tăng | Xác định AUTH/TLS/rate-limit/network |
| **Database claim failure** | Poll/claim errors tăng | DB health, connection pool, index/locks |

### Ví dụ Prometheus alert rules

~~~yaml
groups:
  - name: mail-outbox
    rules:
      - alert: MailOutboxDueBacklog
        expr: >
          (mail_outbox_due_jobs > 100)
          and
          (mail_outbox_oldest_due_seconds > 300)
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Mail outbox có job đã đến hạn nhưng chưa được gửi"
          description: "Kiểm tra worker, retry và SMTP transport."

      - alert: MailOutboxUnknownNotResolved
        expr: mail_outbox_unknown_jobs > 0
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Có notification chưa rõ kết quả SMTP"

      - alert: MailOutboxMetricsStale
        expr: >
          time() -
          mail_outbox_metrics_last_success_epoch_seconds > 180
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Snapshot metrics outbox không được cập nhật"
~~~

Đây là **rule minh họa**, không phải chính sách ngưỡng chuẩn. Giá trị 100 job, 300 giây hoặc 15 phút phải được hiệu chỉnh theo throughput, purpose, volume và lịch vận hành. Nếu metrics có nhiều replica với gauge global lặp lại, cần chuẩn hóa/aggregate series trước khi alert để không sinh nhiều cảnh báo cho một vấn đề.

### Nguyên tắc giảm nhiễu alert

- Dùng **for:** để loại dao động rất ngắn khi workload burst.
- Cảnh báo mức độ khác nhau cho **security/transactional** và **marketing**.
- Cảnh báo khi metric stale, không tự coi DB query thất bại là backlog bằng 0.
- Gộp/silence alert phụ thuộc một root cause lớn, ví dụ SMTP provider outage.
- Theo dõi alert được giải quyết khi backlog và oldest age giảm, không chỉ khi provider trở lại bình thường.
- Đính kèm runbook và panel liên quan; tránh log token, email address hoặc payload trong annotation.

### SLO nên dựa vào thời điểm đủ điều kiện

Một SLO minh họa có thể là: “99% notification giao dịch được SMTP accepted trong khoảng X giây kể từ lúc available_at”. Đây là mục tiêu do sản phẩm xác định. Với provider API có submission không đồng bộ, **ACCEPTED** có thể có nghĩa provider nhận yêu cầu, còn giao vào mailbox là một trạng thái khác.

SLO tốt cần mô tả rõ start/end event, loại notification được tính, cách tính khi SUPPRESSED/UNKNOWN và xử lý lịch gửi có chủ đích.

## 20. Tính đa tenant, phân vùng và chống starvation

Nếu một ứng dụng phục vụ nhiều tenant hoặc nhiều loại email, một campaign lớn có thể khiến các notification nhỏ nhưng quan trọng bị chờ lâu.

Ví dụ:

~~~text
Tenant A marketing  = 100.000 email cần gửi theo lô
Tenant B security   = 20 email xác nhận đăng nhập

Worker chung: 10 concurrent SMTP connections
~~~

Nếu chỉ dùng FIFO và một queue chung, notification của tenant B có thể phải chờ rất lâu. Các lựa chọn:

- Tách queue hoặc worker pools theo **purpose**.
- Dành phần concurrency cho notification quan trọng.
- Áp **priority** nhưng có cơ chế aging/fairness để tránh starvation.
- Giới hạn throughput theo tenant và provider quota.
- Đo **oldest due age** riêng theo purpose/tenant quan trọng.
- Thực hiện suppression trước send để không tốn SMTP capacity cho thư không được phép.

### Priority index không giải quyết fairness

Worker dùng:

~~~sql
ORDER BY priority ASC, available_at ASC
~~~

Nếu luôn có job priority rất cao, job priority thấp có thể chờ vô hạn. Cần cơ chế quota/weighted scheduling hoặc aging policy theo yêu cầu sản phẩm.

### Đo theo tenant: vừa đủ cho vận hành

Trong một hệ thống có hàng chục nghìn tenant, thêm **tenant_id** vào mọi metric label có thể tạo cardinality lớn. Có thể:

- Dùng dashboard SQL/drill-down chọn tenant khi cần.
- Gộp theo **tier/region/purpose** có tập giá trị nhỏ.
- Chỉ tạo metric per-tenant cho một số tenant cần SLO riêng, với chính sách cardinality rõ.
- Dùng logs/traces có quyền truy cập phù hợp khi điều tra một notification cụ thể.

Không dùng recipient email làm nhãn metric để phân tích backlog từng người.

## 21. Khi database rất lớn: quan sát mà không tạo thêm bottleneck

Một hệ thống gửi nhiều mail mỗi ngày có thể giữ hàng triệu outbox records phục vụ audit. Query liên tục toàn bảng để đếm số pending có thể trở thành bottleneck mới.

### Chiến lược tối ưu

1. **Partial indexes** cho các trạng thái đang xử lý.
2. **Retention/archival** bản ghi terminal theo chính sách.
3. **Snapshot định kỳ** thay vì COUNT(*) mỗi lần scrape.
4. **Batch query với LIMIT** cho màn hình điều tra.
5. **Bảng thống kê hoặc counters** nếu workload cần nhiều dashboard.
6. **EXPLAIN ANALYZE và monitoring DB** trước khi thêm index.
7. **Partitioning** khi dung lượng/retention thực sự đòi hỏi, sau khi đánh giá tradeoffs.

### Lưu ý với partitioning và unique key

Trong PostgreSQL, một unique constraint trên partitioned table có quy tắc liên quan partition key. Nếu partition theo thời gian nhưng cần **UNIQUE(tenant_id, notification_key)** toàn bộ vòng đời, không nên giả định constraint cũ vẫn hoạt động nguyên trạng trên mọi partition. Có thể cần một bảng dedup riêng hoặc thiết kế partition key thích hợp.

Khi archive outbox records ACCEPTED, cũng phải giữ khả năng chống tạo notification trùng nếu event upstream có thể replay về sau. Xóa record và unique key quá sớm có thể khiến một message cũ được tạo lại thành công việc mới.

### Tách operational DB và analytics

Nếu dashboard cần thống kê dài hạn theo hàng trăm chiều dữ liệu, có thể đẩy event/state transitions sang một analytics store hoặc metrics backend; đừng làm transaction database phải quét lịch sử trong mỗi lần scrape. Nhưng số liệu analytics có thể có độ trễ, nên vẫn cần phép kiểm tra trực tiếp operational DB cho incident nghiêm trọng.

## 22. Runbook khi cảnh báo outbox tồn đọng

Runbook phải giúp người trực vận hành đi từ **triệu chứng** tới **nguyên nhân** và chọn hành động an toàn. Không nên mở đầu incident bằng lệnh UPDATE trạng thái hàng loạt.

### Bước 1 — Xác minh dữ liệu quan sát còn mới

Kiểm tra:

- Prometheus/metrics exporter có đang hoạt động?
- **last_success_epoch_seconds** có còn được cập nhật?
- Kết quả truy vấn read-only trực tiếp trên operational database có khớp tương đối với gauge không?
- Có đang nhìn đúng cluster/environment, tenant hoặc schema không?

Nếu metric đã stale, đừng kết luận backlog bằng 0 hoặc không còn lỗi. Một biểu đồ phẳng có thể phản ánh việc metric không được cập nhật, không phải worker đã phục hồi.

### Bước 2 — Xác định phạm vi và độ ưu tiên

Phân loại:

- Số due jobs, oldest due age.
- Job của **SECURITY**, **TRANSACTIONAL** hay chỉ marketing scheduled.
- Số UNKNOWN và expired leases.
- Một tenant, một provider, một cluster hay toàn bộ hệ thống.
- Incident kéo dài bao lâu; SLA của những loại mail bị ảnh hưởng.

Nếu email bảo mật/transactional cần gửi ngay bị chậm, có thể nâng mức ưu tiên xử lý hơn backlog marketing theo lịch. Tuy nhiên, ưu tiên không có nghĩa bỏ qua suppression, retry policy hoặc provider quota.

### Bước 3 — Phân biệt backlog mới và backlog tồn tại lâu

Quan sát ít nhất:

~~~text
Due count now
Due count 5 phút trước
Oldest due age now
Enqueued/s
Terminal/s
Unknown count
Expired leases
~~~

Nếu due count giảm và oldest due age cũng giảm, hệ thống có thể đang tự giải phóng backlog. Nếu accepted rate bằng 0 trong khi due count tăng, khả năng đường xử lý đã tắc hoàn toàn cao hơn.

### Bước 4 — Kiểm tra tiến độ worker

Đọc dashboard worker:

- Scheduler/consumer đã start chưa?
- Last successful poll/claim có gần đây không?
- Có lỗi connection pool hoặc database permission?
- Worker có bị restart liên tục, OOM hoặc CPU/GC quá cao?
- Executor queue có đầy và rejection tăng?
- Số in-flight có tương ứng worker concurrency?
- Lease expired có tăng?

Nếu **poll rate = 0**, điều tra service lifecycle/scheduling trước khi kiểm tra SMTP. Nếu **poll/claim bình thường nhưng accepted rate thấp**, đi sâu vào transport hoặc render.

### Bước 5 — Phân tích lỗi SMTP và provider

Các nhóm dấu hiệu:

| Lỗi/signal | Nghi vấn | Hành động điều tra |
| --- | --- | --- |
| AUTH 535 hoặc authentication failures | Credentials bị đổi, sai account, thiếu AUTH | Kiểm tra secret rotation, provider status |
| STARTTLS/certificate exception | TLS trust/hostname, protocol mismatch | Kiểm tra chain, SAN, TLS policy |
| Connection refused/timeout | Network, DNS, firewall, SMTP outage | Kiểm tra endpoint và egress policy |
| 4xx/rate limit | Provider throttling | Kiểm tra quota, backoff, concurrency |
| 5xx/permanent recipient rejection | Địa chỉ hoặc sender policy | Phân loại per recipient, không retry mù |
| Timeout sau SMTP DATA | Outcome không rõ | UNKNOWN và reconciliation |
| MIME render failure | Template/model không hợp lệ | Kiểm tra loại template, không dump body nhạy cảm |

Không tắt TLS verification, không thử đổi SMTP server lạ và không dùng credential khác tùy tiện để “giải quyết nhanh” backlog. Điều đó có thể tạo lỗ hổng và lỗi deliverability mới.

### Bước 6 — Kiểm tra database

Nếu worker không claim được dù due jobs nhiều:

- Kết nối database có đủ không?
- Query claim có dùng index không?
- Row locks hoặc transaction kéo dài có khiến SKIP LOCKED liên tục bỏ qua row?
- Có migration/schema mismatch vừa xảy ra?
- Bảng outbox có tăng kích thước/đầy disk?
- Các query metric có gây thêm tải hay không?
- Có transaction dùng read-only mode hoặc permission sai?

Với PostgreSQL, các nguồn thông tin như **pg_stat_activity**, **pg_locks**, query plan và database monitoring có thể hữu ích, nhưng cần quyền phù hợp và tránh chạy query nặng khi database đang quá tải.

### Bước 7 — Chọn biện pháp khôi phục có kiểm soát

Tùy nguyên nhân:

- Restart worker/scheduler nếu nó thực sự chết và bảo đảm claim/recovery an toàn.
- Rollback deployment lỗi nếu incident bắt đầu sau một release.
- Sửa cấu hình credentials/TLS/host bằng quy trình secret/config management.
- Giảm/tạm dừng marketing để dành capacity cho transactional mail.
- Giảm concurrency hoặc tăng backoff khi provider rate-limit.
- Tăng worker capacity **nếu** provider và DB còn chịu được, không chỉ tăng thread pool.
- Thêm/fix index khi đo được bottleneck và có kế hoạch migration an toàn.
- Đối soát UNKNOWN và expired lease trước khi xét retry.

Không có một lệnh “reprocess all pending” an toàn cho mọi tình huống.

### Bước 8 — Xác nhận phục hồi

Đừng đóng incident chỉ vì SMTP endpoint đã trở lại. Cần xác nhận:

- Due backlog giảm về mức ổn định.
- Oldest due age giảm dưới ngưỡng của từng purpose.
- Incoming và terminal rate được cân bằng.
- UNKNOWN/expired leases không tiếp tục tăng.
- Không phát sinh duplicate hoặc mail gửi cho recipient bị suppression.
- Worker/DB/provider error rate trở về mức phù hợp.

Nếu backlog vẫn lớn nhưng đang giảm có kiểm soát, cần ghi nhận tiến độ và mốc theo dõi tiếp theo; không tuyên bố phục hồi hoàn toàn khi SLA chưa đạt.

## 23. Khôi phục backlog mà không gửi trùng

Tình huống nguy hiểm: SMTP provider vừa phục hồi sau outage, dashboard báo 20.000 job PENDING/RETRY_WAIT và 200 job UNKNOWN. Một nhân viên thực hiện:

~~~sql
-- KHÔNG NÊN chạy như một giải pháp khôi phục:
UPDATE mail_outbox
SET status = 'PENDING',
    available_at = CURRENT_TIMESTAMP
WHERE status <> 'ACCEPTED';
~~~

Lệnh này có thể:

- Biến UNKNOWN thành retry mặc dù server đã nhận thư.
- Gửi lại mail SUPPRESSED hoặc CANCELLED.
- Retry lỗi vĩnh viễn/recipient không hợp lệ.
- Xóa bỏ mục đích của backoff, tạo retry storm.
- Làm đảo lộn lịch gửi trong tương lai.
- Vi phạm yêu cầu opt-out hoặc do-not-contact.

**Không được xử lý mọi trạng thái chưa ACCEPTED như một nhóm có thể gửi lại.**

### Quy trình khôi phục theo từng nhóm

| Nhóm | Hành động an toàn hơn |
| --- | --- |
| PENDING đã đến hạn | Cho worker claim bình thường theo capacity và priority |
| PENDING theo lịch | Giữ available_at, không kéo lên hiện tại |
| RETRY_WAIT chưa đến hạn | Tôn trọng backoff, chỉ điều chỉnh có kiểm soát |
| RETRY_WAIT đã đến hạn | Retry theo policy, kiểm tra suppression trước gửi |
| IN_FLIGHT với lease hợp lệ | Để worker xử lý; theo dõi deadline |
| IN_FLIGHT lease quá hạn | Recovery đưa vào UNKNOWN hoặc trạng thái cần đối soát |
| UNKNOWN | Tra provider/logs; không retry mù |
| PERMANENT_FAILED | Sửa dữ liệu/cấu hình hoặc xử lý thủ công |
| SUPPRESSED/CANCELLED | Không gửi |
| ACCEPTED | Không enqueue lại cùng notification chỉ vì monitoring lỗi |

### Một lệnh recovery an toàn hơn cho expired leases

Khi chính sách quy định lease quá hạn phải chuyển sang UNKNOWN để đối soát:

~~~sql
UPDATE mail_outbox
SET
    status = 'UNKNOWN',
    last_error_category = 'LEASE_EXPIRED',
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'IN_FLIGHT'
  AND (
      lease_until IS NULL
      OR lease_until <= CURRENT_TIMESTAMP
  )
RETURNING id, tenant_id, purpose, attempt_count;
~~~

Đây là **ví dụ về state transition của recovery service**, không phải lời khuyên chạy thủ công trên production. Cần triển khai với transaction, quyền, giới hạn batch, audit, cơ chế tránh race và giám sát. Một worker có thể vẫn đang gửi SMTP khi lease hết hạn; late outcome cần được reconciliation xử lý.

### Requeue một job theo id phải có điều kiện

Một API quản trị **requeue(jobId, reason)** nên:

1. Kiểm tra quyền operator và ghi audit.
2. Đọc trạng thái hiện tại và lịch sử attempt.
3. Kiểm tra notification còn phù hợp nghiệp vụ và suppression.
4. Chỉ cho chuyển trạng thái nếu đã biết outcome trước an toàn để retry.
5. Sử dụng compare-and-set theo status/version hoặc lease token.
6. Không tạo notification_key mới cho cùng logic chỉ để né dedup.
7. Giữ retry limit, rate limit và schedule thích hợp.

Nếu không xác định được SMTP có accepted hay chưa, phải trình bày rõ rằng requeue có **nguy cơ duplicate** và có thể yêu cầu quyết định từ người có trách nhiệm sản phẩm.

### Retry sau opt-out

Người nhận có thể hủy newsletter trong lúc backlog đang chờ. Khi worker khôi phục, phải kiểm tra lại **mail delivery policy/suppression** trước mọi attempt marketing. Không sử dụng danh sách nhận đã snapshot từ trước incident như bằng chứng người nhận vẫn muốn thư.

## 24. Đối soát UNKNOWN bằng bằng chứng thực tế

Một số nguồn có thể giúp:

- Mail provider API tìm trạng thái theo request ID hoặc idempotency key, **nếu provider hỗ trợ**.
- SMTP server logs với queue ID, thời gian, recipient hoặc correlation ID.
- Provider webhook về accepted/delivered/bounced.
- Event/attempt history và logs có timestamp.

### Những giới hạn cần thừa nhận

SMTP thuần không có một câu lệnh tiêu chuẩn để hỏi một message đã được server chấp nhận trước đó chưa. Header **Message-ID** có thể hỗ trợ truy vết nhưng không bắt SMTP server deduplicate.

Một lần tìm không thấy message trong provider dashboard có thể do độ trễ indexing hoặc giới hạn retention. **Không tìm thấy** chưa luôn là **chắc chắn không được accepted**.

### Gợi ý record điều tra UNKNOWN

~~~text
notification_id:     6b91...
event_type:          ORDER_CONFIRMED
provider:            primary-smtp
attempt_id:          001...
attempt_started_at:  ...
last_error_category: SMTP_READ_TIMEOUT
outbox_status:       UNKNOWN
provider_evidence:   NOT_YET_AVAILABLE
reconciliation:      OPEN
operator_action:     HOLD
~~~

Không đưa plaintext password, OTP, reset link hoặc nguyên nội dung MIME vào record điều tra. Với PII như địa chỉ người nhận, có thể hiển thị che một phần theo quyền truy cập.

### Chuyển trạng thái sau đối soát

~~~text
UNKNOWN
   |
   +-- Có bằng chứng provider đã nhận
   |       -> ACCEPTED
   |
   +-- Có bằng chứng provider chắc chắn chưa nhận
   |       -> RETRY_WAIT (nếu vẫn đủ điều kiện)
   |
   +-- Không có bằng chứng
           -> HOLD / NEEDS_REVIEW
           -> retry chỉ theo chính sách chấp nhận rủi ro
~~~

Nếu provider có API idempotency chính thức, dùng đúng khóa và thời hạn retention khi retry; không gán cho SMTP Message-ID chức năng idempotency mà giao thức không bảo đảm.

## 25. Kế hoạch xử lý sự cố theo mức độ nghiêm trọng

Mức độ incident tùy sản phẩm, nhưng có thể xây khung:

| Mức | Tình huống minh họa | Mục tiêu |
| --- | --- | --- |
| **High** | Email đăng nhập/khôi phục tài khoản đến hạn bị kẹt diện rộng | Phục hồi đường gửi thiết yếu, xác định phạm vi người dùng |
| **Medium** | Transactional mail chậm, backlog tăng, provider đang throttle | Ổn định throughput, bảo vệ SLA và tránh duplicate |
| **Low** | Marketing scheduled backlog nhỏ, vẫn trong cửa sổ gửi | Giám sát xu hướng, điều chỉnh capacity khi phù hợp |
| **Investigate** | UNKNOWN tăng nhưng due backlog không lớn | Đối soát và xử lý outcome mơ hồ |

Không có số lượng backlog tuyệt đối tương đương severity trong mọi hệ thống. **10 email OTP bị chậm 20 phút** có thể nghiêm trọng hơn **20.000 newsletter chưa đến giờ gửi**.

### Vai trò khi ứng cứu

Một incident có thể phân trách nhiệm:

- **On-call/application owner:** kiểm tra worker, queue metrics và release gần đây.
- **Database operator:** phân tích locks, connection pool, query plan và index.
- **Mail/provider owner:** kiểm tra trạng thái SMTP, credentials/TLS, rate limit, provider events.
- **Product/support:** xác định notification nào có mức độ ảnh hưởng cao, giải thích trạng thái với người dùng.
- **Security/privacy:** tham gia khi có khả năng rò rỉ credential, gửi sai người hoặc vi phạm opt-out.

Các vai trò có thể thuộc một nhóm nhỏ trong dự án ít người, nhưng cần rõ ai được quyền **thay đổi trạng thái job** và ai chỉ được **truy vấn đọc**.

## 26. Kiểm thử khả năng phát hiện backlog

Một hệ thống có metric đúng ở happy path vẫn có thể bỏ qua job kẹt khi worker chết. Cần kiểm thử cả **trạng thái hàng đợi** và **tính đúng của metric/alert**, không chỉ việc mailSender.send(...) được gọi.

### Trường hợp 1 — Một job PENDING đã đến hạn

~~~text
Given:
    status=PENDING
    available_at=now - 10 minutes
When:
    monitoring snapshot được lấy
Then:
    due_jobs tăng 1
    oldest_due_age >= 10 minutes (xấp xỉ)
~~~

Thời gian trong test có thể được tạo tương đối so với một **Clock** cố định hoặc timestamp của database. Đừng dùng các timestamp sát ranh giới now khiến test lúc đúng lúc sai.

### Trường hợp 2 — Job scheduled trong tương lai

~~~text
Given:
    status=PENDING
    available_at=now + 2 hours
Then:
    scheduled_jobs tăng 1
    due_jobs không tăng
    oldest_due_age không bị ảnh hưởng
~~~

Trường hợp này ngăn việc phát cảnh báo giả khi chiến dịch email được tạo trước giờ gửi.

### Trường hợp 3 — Retry có backoff

~~~text
Given:
    status=RETRY_WAIT
    available_at=now + 15 minutes
Then:
    retry_not_due tăng
    due_jobs không tăng

Sau khi available_at đến hạn:
    retry_due tăng
    due_jobs tăng
~~~

Test nên xác nhận scheduler không tự điều chỉnh available_at về hiện tại chỉ vì worker restart.

### Trường hợp 4 — Job IN_FLIGHT với lease còn hạn

~~~text
Given:
    status=IN_FLIGHT
    lease_until=now + 30 seconds
Then:
    inflight_jobs tăng
    expired_leases không tăng
~~~

### Trường hợp 5 — Lease quá hạn

~~~text
Given:
    status=IN_FLIGHT
    lease_until=now - 30 seconds
Then:
    expired_leases tăng
    recovery đánh dấu UNKNOWN theo policy
    worker không gửi lại tự động
~~~

Đặc biệt, hãy mô phỏng server đã accepted message nhưng process chết trước khi markAccepted. Test này chứng minh **recovery không biến một kết quả không rõ thành retry mù**.

### Trường hợp 6 — UNKNOWN đang tồn đọng

~~~text
Given:
    status=UNKNOWN
    updated_at=now - 20 minutes
Then:
    unknown_jobs tăng
    oldest_unknown_age phản ánh thời gian treo
    job không được claim như PENDING
~~~

Trong schema minh họa, nếu updated_at có thể thay đổi khi thực hiện reconciliation, cần dùng unknown_since riêng. Test phản ánh semantics timestamp được chọn.

### Trường hợp 7 — Metric refresh thất bại

~~~text
Given:
    snapshot trước: due_jobs=50
When:
    database query ném exception
Then:
    refresh_failure counter tăng
    last_success_epoch không đổi
    gauge không bị ép về 0
    stale alert có thể kích hoạt sau deadline
~~~

Không nên khiến dashboard hiển thị “không có backlog” chỉ vì database tạm thời không truy vấn được.

### Trường hợp 8 — Hai worker cùng claim

Trong database integration test, tạo một due row rồi cho hai transaction cạnh tranh bằng **FOR UPDATE SKIP LOCKED**. Chỉ một worker được claim row đó; worker còn lại không được gửi cùng notification ở cùng thời điểm.

Các test concurrency nên dùng database có locking semantics tương ứng production. Nếu production là PostgreSQL, Testcontainers PostgreSQL sẽ phù hợp hơn việc giả định in-memory map mô phỏng đúng row locks.

### Trường hợp 9 — Một tenant tạo campaign lớn

Tạo backlog marketing rất lớn và một số email bảo mật; xác nhận scheduler/priority/quota giúp email bảo mật không bị chờ vượt SLO. Một hệ thống dùng priority thuần có thể lại làm job marketing bị starvation; test cần phản ánh fairness policy được thiết kế.

### Trường hợp 10 — Unsubscribe sau khi enqueue

~~~text
T0: Marketing notification PENDING
T1: Recipient opt-out
T2: Worker claim job
Expected: SUPPRESSED, không gọi JavaMailSender
~~~

Recovery của backlog không được vô tình vượt qua delivery policy.

### Trường hợp 11 — SMTP timeout sau DATA

Fake transport mô phỏng server đã nhận message nhưng client không nhận ACK. Worker cần ghi UNKNOWN và không tự retry khi chính sách yêu cầu hold-on-unknown.

Test này mạnh hơn việc mock JavaMailSender luôn ném exception trước khi có external side effect, vì nó thể hiện rủi ro gửi trùng thực tế.

### Trường hợp 12 — Metrics đa replica

Cho ba metrics exporters cùng đọc một bảng có 100 due jobs. Kiểm tra dashboard/alert aggregation cho kết quả **100**, không phải **300**, nếu gauge mang nghĩa global.

### Trường hợp 13 — Job ACCEPTED không còn trong due backlog

Một job đã được SMTP server chấp nhận phải nằm ở terminal state. Test tránh trường hợp SQL đếm mọi record được tạo trong 24 giờ thay vì đếm những record còn due.

### Trường hợp 14 — No-work không phải worker-down

Trong một thời gian không có email:

~~~text
due_jobs=0
last_claim_at=30 minutes ago
scheduler polling normally
~~~

Test rule cảnh báo không được kích hoạt chỉ vì không có claim mới. Trái lại, khi due_jobs > 0 và poll/claim không tiến triển, alert phải có ý nghĩa.

### Ví dụ JUnit cho classifier thời gian

Phần logic nhỏ có thể unit test độc lập với database:

~~~java
import java.time.Instant;

public record OutboxForMonitoring(
        String status,
        Instant availableAt,
        Instant leaseUntil
) {
}

public final class OutboxClassification {

    private OutboxClassification() {
    }

    public static boolean isDue(
            OutboxForMonitoring job,
            Instant now
    ) {
        return ("PENDING".equals(job.status())
                || "RETRY_WAIT".equals(job.status()))
                && !job.availableAt().isAfter(now);
    }

    public static boolean isExpiredLease(
            OutboxForMonitoring job,
            Instant now
    ) {
        return "IN_FLIGHT".equals(job.status())
                && (job.leaseUntil() == null
                    || !job.leaseUntil().isAfter(now));
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class OutboxClassificationTest {

    private static final Instant NOW =
            Instant.parse("2026-01-01T12:00:00Z");

    @Test
    void scheduledMailIsNotDue() {
        OutboxForMonitoring job = new OutboxForMonitoring(
                "PENDING",
                NOW.plusSeconds(3600),
                null
        );
        assertFalse(OutboxClassification.isDue(job, NOW));
    }

    @Test
    void retryBecomesDueAtItsAvailableTime() {
        OutboxForMonitoring job = new OutboxForMonitoring(
                "RETRY_WAIT",
                NOW,
                null
        );
        assertTrue(OutboxClassification.isDue(job, NOW));
    }

    @Test
    void expiredLeaseRequiresInvestigation() {
        OutboxForMonitoring job = new OutboxForMonitoring(
                "IN_FLIGHT",
                NOW.minusSeconds(60),
                NOW.minusSeconds(1)
        );
        assertTrue(
                OutboxClassification.isExpiredLease(job, NOW)
        );
    }
}
~~~

Ví dụ dùng record và Java time để tập trung vào logic. **Kiểm thử classifier không thay thế integration test SQL**, vì database có thể dùng transaction timestamp, isolation level và null semantics khác với logic Java. Khi hệ thống triển khai nhiều nơi tính due count, nên có một quy tắc thống nhất để metric và claim query không bất đồng.

## 27. Các tình huống điều tra thực tế

### Tình huống A — 50.000 PENDING nhưng không có cảnh báo

Truy vấn cho thấy tất cả available_at đều là ngày mai.

**Kết luận:** đây là scheduled workload, không phải due backlog. Nếu alert dựa trên COUNT(PENDING), cần sửa cách đo.

### Tình huống B — Due backlog 500, oldest due age tăng liên tục

Worker heartbeat vẫn có, nhưng last successful claim không thay đổi.

**Hướng điều tra:** kiểm tra claim query, feature flag, database lock, transaction lỗi hoặc scheduler không thực sự poll.

### Tình huống C — Claim rate cao, ACCEPTED rate gần 0

Dashboard cho thấy nhiều IN_FLIGHT, SMTP latency tăng mạnh.

**Hướng điều tra:** worker có đang kẹt socket, thiếu SMTP timeout, provider throttling hoặc executor overload không? Không vội tăng worker vì có thể làm provider quá tải hơn.

### Tình huống D — SMTP provider trả 4xx hàng loạt

RETRY_WAIT tăng, các available_at được đặt cách nhau bằng backoff.

**Hướng xử lý:** xác định đây là lỗi tạm thời hay rate limit, giữ retry policy và jitter; tránh đặt lại tất cả available_at về now.

### Tình huống E — UNKNOWN tăng sau một đợt read timeout

Một số attempt có thể đã được SMTP accepted.

**Hướng xử lý:** không retry mù; tra provider logs/API và đối soát trước khi chuyển trạng thái. Đặt alert theo tuổi UNKNOWN.

### Tình huống F — IN_FLIGHT bị treo sau khi deploy

Deployment mới có bug khiến worker chết giữa SMTP và cập nhật trạng thái.

**Hướng xử lý:** rollback/fix ứng dụng, chuyển expired leases sang UNKNOWN bằng recovery có audit, không replay toàn bộ.

### Tình huống G — Email OTP chậm nhưng marketing vẫn đang xử lý

Worker pool bị campaign chiếm hết.

**Hướng xử lý:** phân vùng capacity theo purpose, ưu tiên bảo mật/giao dịch, kiểm tra fairness; không chỉ tăng priority trong một queue có thể starvation.

### Tình huống H — Metrics báo backlog bằng 0 dù người dùng không nhận email

last_success_epoch đã cũ; exporter mất kết nối database.

**Hướng xử lý:** xác minh metric freshness và truy vấn DB read-only, không tin gauge đã stale.

### Tình huống I — Đã tăng worker gấp đôi nhưng throughput không tăng

SMTP provider vẫn giới hạn tổng số request/connections.

**Hướng xử lý:** kiểm tra rate limit, retry policy và SMTP latency. Tăng worker khi bottleneck ở provider chỉ tạo thêm lỗi và backlog retry.

### Tình huống J — Query claim rất chậm khi outbox hàng chục triệu rows

Phần lớn record đã ACCEPTED nhưng query vẫn quét toàn bảng.

**Hướng xử lý:** đánh giá partial index, retention/archival, batch queries và query plan. Đừng chạy COUNT(*) toàn bảng mỗi lần scrape.

### Tình huống K — Worker báo đã gửi nhưng outbox vẫn IN_FLIGHT

Provider có thể đã nhận mail, nhưng UPDATE ACCEPTED thất bại.

**Hướng xử lý:** kiểm tra database outcome write, fencing token và attempt log. Không coi lease expired là bằng chứng chưa gửi.

### Tình huống L — Người dùng unsubscribe trong lúc backlog chờ

Một campaign đã tạo job từ hôm trước.

**Hướng xử lý:** worker kiểm tra suppression trước gửi và chuyển job sang SUPPRESSED, không cố “giải phóng” backlog bằng cách gửi tất cả.

### Tình huống M — Noisy neighbor trong multi-tenant

Một tenant chiếm phần lớn concurrency làm tenant khác chậm.

**Hướng xử lý:** đo due age theo tenant/tier khi cần, giới hạn quota và thiết kế fairness. Không tăng cardinality của Prometheus bằng cách gắn mọi tenant/user vào metric.

### Tình huống N — Một đợt import làm enqueued rate tăng 20 lần

Không có lỗi worker, nhưng throughput không theo kịp.

**Hướng xử lý:** xác nhận import hợp lệ, lịch gửi, batch/admission control, chia tải và giới hạn provider. Không tự tăng mọi worker không giới hạn.

### Tình huống O — SMTP accepted nhưng thư chưa tới Inbox

Outbox đã ACCEPTED và due backlog thấp.

**Hướng xử lý:** chuyển sang theo dõi provider delivery, bounce, suppression và spam; đây không còn là bài toán job outbox chưa được dispatch.

## 28. Những lỗi thường gặp khi kiểm tra outbox tồn đọng

### Lỗi 1 — Chỉ đếm tất cả các dòng trong bảng

Một database có hàng triệu dòng ACCEPTED phục vụ audit có thể làm biểu đồ tăng mãi dù mail gửi tốt.

**Cách xử lý:** tách due, scheduled, in-flight, UNKNOWN và terminal states. Không dùng COUNT(*) tổng để đánh giá backlog đang chờ gửi.

### Lỗi 2 — Coi mọi PENDING là bị kẹt

PENDING có thể là email theo lịch trong tương lai.

**Cách xử lý:** kiểm tra **available_at <= CURRENT_TIMESTAMP** rồi mới kết luận job đến hạn.

### Lỗi 3 — Dùng created_at làm tuổi backlog theo lịch

Một newsletter tạo trước một tuần nhưng chỉ đến hạn hôm nay có created_at rất cũ.

**Cách xử lý:** đo overdue từ **available_at** và theo dõi end-to-end age riêng.

### Lỗi 4 — Dùng updated_at để che tình trạng job cũ

Một job bị retry nhiều lần có updated_at mới, khiến tuổi công việc trông như rất trẻ.

**Cách xử lý:** theo dõi created_at, available_at và last_attempt_at riêng. Với UNKNOWN dùng unknown_since nếu cần.

### Lỗi 5 — Đo attempts thay cho accepted notifications

Một job retry 10 lần khiến throughput attempts tăng nhưng chưa có email nào được chấp nhận.

**Cách xử lý:** có counter riêng cho notification enqueued/terminal và attempts.

### Lỗi 6 — Gộp job RETRY_WAIT chưa đến hạn vào due backlog

Hệ thống backoff đúng nhưng dashboard vẫn báo quá hạn.

**Cách xử lý:** phân biệt retry_due và retry_not_due theo available_at.

### Lỗi 7 — Coi lease expired là chưa gửi

Worker có thể đã thực hiện SMTP side effect trước khi mất kết nối hoặc chết.

**Cách xử lý:** expired lease cần recovery/UNKNOWN và reconciliation, không chuyển trực tiếp về PENDING.

### Lỗi 8 — Dùng reset status hàng loạt để “chạy lại”

Lệnh reset có thể gửi trùng, gửi lại mail đã suppressed hoặc phá lịch retry.

**Cách xử lý:** khôi phục theo trạng thái, bằng chứng và policy, có audit và idempotency key.

### Lỗi 9 — Không kiểm tra suppression trước retry

Job marketing được enqueue khi recipient còn subscribed, nhưng người đó đã opt-out.

**Cách xử lý:** kiểm tra delivery policy ở mỗi lần submit, kể cả khi backlog cần được giải phóng.

### Lỗi 10 — Không tính database polling failure

Gauges giữ giá trị 0 do reporter bắt exception rồi đặt về 0.

**Cách xử lý:** giữ giá trị gần nhất kèm last_success timestamp, tăng refresh-failure counter và cảnh báo stale metrics.

### Lỗi 11 — Cộng các gauge global trên mọi replica

Ba worker cùng báo due_jobs=100 tạo biểu đồ 300.

**Cách xử lý:** một nguồn metric global, hoặc chọn cách aggregation không nhân đôi trạng thái database.

### Lỗi 12 — Tăng thread pool mà không xác định bottleneck

Nếu provider đang rate-limit hoặc DB connection pool đầy, thêm threads có thể làm backlog xấu hơn.

**Cách xử lý:** đo claim rate, SMTP latency, error categories, worker concurrency và provider quota trước khi scale.

### Lỗi 13 — Không có index cho due query

Worker phải quét và sort hàng triệu terminal rows.

**Cách xử lý:** dùng partial index phù hợp truy vấn, kiểm tra query plan và retention.

### Lỗi 14 — Đặt priority cao nhất cho mọi campaign

Không có cơ chế fairness, notification giao dịch quan trọng bị starvation.

**Cách xử lý:** tách capacity theo purpose/tier và thiết kế quota/aging.

### Lỗi 15 — Bật raw SMTP debug trên production khi backlog tăng

Log có thể chứa PII, credentials hoặc nội dung MIME, lại thêm tải I/O.

**Cách xử lý:** ưu tiên structured error categories, metrics và correlation IDs; bật debug có kiểm soát, redact dữ liệu, không ghi raw AUTH.

### Lỗi 16 — Coi SMTP accepted là delivered

Outbox có thể đã hoàn tất submission nhưng người dùng vẫn không nhận do bounce/spam.

**Cách xử lý:** tách giám sát outbox acceptance và các event giao tới mailbox từ provider.

### Lỗi 17 — Xóa terminal rows làm mất deduplication

Event cũ được replay sau khi outbox record và unique key đã bị xóa, khiến mail được tạo lại.

**Cách xử lý:** thiết kế retention/dedup tombstone riêng phù hợp phạm vi event replay và yêu cầu dữ liệu.

### Lỗi 18 — Không phát hiện lỗi khi không có email

Alert “không có claim 5 phút” báo động trong ban đêm dù due_backlog=0, dẫn tới alert fatigue.

**Cách xử lý:** kết hợp điều kiện due_backlog>0 với no-progress, và dùng health check riêng cho scheduler.

### Lỗi 19 — Không kiểm tra nhật ký phiên bản khi bị nghẽn sau deploy

Một thay đổi SQL claim hoặc property SMTP có thể gây toàn bộ backlog.

**Cách xử lý:** trên dashboard lưu annotations cho deployment/config changes và kiểm tra thời điểm sự cố bắt đầu so với release.

### Lỗi 20 — Điều tra bằng cách lấy toàn bộ raw payload

Một truy vấn SELECT * hoặc log raw MIME có thể làm lộ email, token xác thực và hóa đơn.

**Cách xử lý:** truy vấn metadata tối thiểu, giới hạn quyền vận hành và chỉ truy cập payload khi có lý do hợp lệ.

## 29. Mẫu bản ghi sự cố outbox

Một incident record cô đọng giúp bàn giao từ on-call cho người phụ trách tiếp theo:

~~~text
Incident: MAIL-OUTBOX-LAG
Environment: production / cluster-a
Observed at: ...
Purpose affected: ORDER_RECEIPT
Due backlog count: 8,200
Oldest due age: 00:18:30
Scheduled future: 120,000 (không nằm trong due backlog)
In-flight: 24
Expired leases: 2
Unknown count: 4
Enqueue rate: 180/min
Terminal rate: 45/min
Top error: SMTP_RATE_LIMIT
Worker poll: healthy
Database claim: healthy
Provider status: throttled

Mitigation:
  - Giảm marketing concurrency
  - Duy trì retry backoff + jitter
  - Không retry UNKNOWN
  - Theo dõi quota/accepted rate

Next check:
  - Due backlog + oldest due age giảm?
  - UNKNOWN có được đối soát?
  - Transactional SLA có phục hồi?

Owner / reason / timestamps: ...
~~~

Các số trong mẫu chỉ minh họa. Một bản ghi incident thật nên dùng dữ liệu xác thực từ metrics/DB, ghi thời gian cụ thể kèm timezone, và tránh chứa thông tin cá nhân hoặc SMTP credentials.

### Sau incident: phân tích nguyên nhân gốc

Khi backlog trở về ổn định:

1. Xác định **thời điểm đầu tiên** incoming vượt terminal rate hoặc accepted rate giảm.
2. Liên kết với deployment, credential rotation, provider outage, quota và lỗi DB.
3. Phân tích vì sao alert có hoặc không có tác dụng; có metric bị stale không?
4. Xác định email nào bị trễ và phạm vi tác động tới người dùng.
5. Xác minh có duplicate/retry không an toàn hoặc suppression bị bỏ qua không.
6. Điều chỉnh capacity, retry, indexes, SLA hoặc ownership theo nguyên nhân đã xác thực.
7. Thêm integration test/fault-injection cho chế độ lỗi đã gặp.
8. Cập nhật runbook và dashboard để lần sau chẩn đoán nhanh hơn.

Không nên chỉ kết luận “worker xử lý chậm” nếu nguyên nhân thực là provider rate limit hoặc truy vấn database bị lock.

## 30. Sơ đồ kiểm tra nhanh khi có backlog

~~~text
Có cảnh báo outbox?
         |
         v
Metric còn mới?
   |             |
  Không          Có
   |             |
   v             v
Sửa exporter    Due backlog > 0?
                 |             |
                Không          Có
                 |             |
                 v             v
            Xem scheduled/    Oldest due age vượt SLA?
            UNKNOWN riêng        |             |
                                Không          Có
                                 |             |
                                 v             v
                           Theo dõi xu hướng  Worker có poll/claim?
                                                  |          |
                                                 Không       Có
                                                  |          |
                                                  v          v
                                             Scheduler/DB   SMTP/Executor?
                                                            |         |
                                                           Lỗi       Bình thường
                                                            |         |
                                                            v         v
                                                       TLS/AUTH/     Capacity,
                                                       timeout/     priority,
                                                       rate limit   fairness
                                                            |
                                                            v
                                                   Giải pháp có kiểm soát
                                                            |
                                                            v
                                              Reconcile UNKNOWN/expired lease
                                                            |
                                                            v
                                             Due age và count có giảm bền vững?
                                                            |
                                                            v
                                                 Ghi incident + follow-up
~~~

Đây là sơ đồ triage, không phải state machine. Trong thực tế có thể đồng thời tồn tại nhiều nguyên nhân, ví dụ database claim chậm và SMTP rate-limit. Dữ liệu đo được phải quyết định bước điều tra.

## 31. Tóm tắt nguyên tắc cốt lõi

~~~text
COUNT(outbox rows)               != due backlog
PENDING                           != luôn bị kẹt
Scheduled future                  != quá hạn
Available_at đã đến hạn           -> due job
Oldest due age                    -> đo trễ sau thời điểm đủ điều kiện
Enqueued rate > terminal rate     -> backlog có xu hướng tăng
Claim rate cao                    != accepted rate cao
Expired lease                     != chắc chắn SMTP chưa gửi
UNKNOWN                           -> đối soát trước retry
SMTP accepted                     != Inbox delivered
Metric không cập nhật             != backlog bằng 0
Nhiều exporter đo cùng DB         -> không sum gauge mù
Gửi lại hàng loạt                 -> nguy cơ duplicate, spam, mất policy
Retry marketing                   -> vẫn phải kiểm tra suppression
~~~

**Kiểm tra outbox bị tồn đọng** phải dựa trên **số job đã đến hạn, tuổi job cũ nhất, tốc độ enqueue/terminal, retry schedule, expired leases và UNKNOWN outcomes**. Trong Spring Framework Mail, **JavaMailSender** đảm nhiệm transport; còn việc đo hàng đợi, claim job, instrument Micrometer và tạo dashboard/alert thuộc trách nhiệm thiết kế của ứng dụng. Một hệ thống vận hành tốt không chỉ phát hiện backlog mà còn phân biệt rõ **vì sao nó tăng**, đánh giá ảnh hưởng theo purpose, khôi phục worker/provider/database có kiểm soát và xác nhận độ trễ thực sự giảm. Khi xử lý sự cố, hãy giữ nguyên **idempotency**, **suppression** và trạng thái **UNKNOWN** cho đến khi có bằng chứng; tuyệt đối không đổi mọi job thành PENDING chỉ để làm đẹp biểu đồ.
