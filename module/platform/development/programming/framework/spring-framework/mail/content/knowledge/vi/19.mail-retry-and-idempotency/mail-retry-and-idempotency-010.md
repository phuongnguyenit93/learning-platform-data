# Lưu số lần thử và nguyên nhân thất bại

## 1. Bài toán trong Spring Framework Mail

Ứng dụng gửi email qua **Spring Framework Mail** có thể gặp lỗi khi kết nối SMTP, xác thực, chuẩn bị MIME message, gửi dữ liệu hoặc cập nhật trạng thái sau khi gửi. Nhiều lỗi chỉ mang tính tạm thời, nên hệ thống có thể thử lại. Nhưng nếu không **lưu số lần thử và nguyên nhân thất bại**, worker rất khó trả lời:

- Email này đã được thử gửi bao nhiêu lần?
- Lần thất bại gần nhất xảy ra lúc nào và ở giai đoạn nào?
- Đây là lỗi tạm thời, lỗi vĩnh viễn hay kết quả chưa xác định?
- Bao giờ được thử lại, và còn bao nhiêu lượt thử?
- Có phải hai worker cùng xử lý một bản ghi?
- SMTP đã nhận email rồi nhưng ứng dụng chưa kịp cập nhật database hay chưa?
- Khi operator xem một email thất bại, có đủ dữ liệu để quyết định **redrive** hay phải sửa cấu hình/dữ liệu trước?

Nếu chỉ bắt exception và log:

~~~java
try {
    mailSender.send(message);
} catch (Exception ex) {
    log.error("Cannot send email", ex);
}
~~~

thông tin sự cố có thể mất khi log bị xoay vòng hoặc tiến trình bị restart. Một worker khác không biết email cần retry lúc nào và tại sao. Ngược lại, retry vô hạn ngay trong một vòng lặp có thể làm provider quá tải, gửi trùng thư hoặc giữ worker không xử lý được các công việc khác.

Một thiết kế thường dùng là **transactional outbox**: lưu ý định gửi trong database cùng transaction nghiệp vụ, rồi worker lấy từng bản ghi để gửi. Bài học này tập trung vào cách **ghi nhận lịch sử các lần dispatch**, phân loại nguyên nhân thất bại và duy trì trạng thái nhất quán để retry và idempotency hoạt động có kiểm soát.

> **Phân biệt ngay từ đầu:** “Đã thử gửi” là một sự kiện ở phía ứng dụng; “SMTP chấp nhận thư” là kết quả của transport; “thư tới inbox” là một sự kiện khác. Không dùng một cờ `sent` duy nhất để biểu diễn tất cả.

## 2. Định nghĩa chính xác một lần thử

Số lần thử có thể được hiểu theo nhiều cách, vì vậy phải chọn một quy ước và dùng nhất quán.

Ví dụ quy ước khuyến nghị:

**`attempt_count` = số lần worker đã claim và bắt đầu một lượt dispatch cho bản ghi outbox.**

Mỗi khi một worker giành quyền xử lý hợp lệ, tăng `attempt_count` **một lần**, ngay trong transaction claim. Một lượt dispatch có thể:

1. Dựng template và MIME message.
2. Gọi `JavaMailSender.send(...)`.
3. Lưu kết quả `SENT`, `RETRY`, `FAILED` hoặc `UNKNOWN`.

Điều đó có nghĩa:

- Lỗi khi dựng MIME **vẫn có thể tính là một attempt** theo quy ước này, dù chưa mở kết nối SMTP.
- Lỗi executor reject **trước khi claim** không tính vào `attempt_count`; nếu reject xảy ra **sau claim** thì phải được ghi nhận và xử lý lease/trạng thái.
- Một lượt claim đã commit nhưng JVM chết ngay trước SMTP send vẫn là một attempt đã bắt đầu, dù chưa thật sự gửi bytes.
- Nếu cần đếm riêng số lần thực sự gọi `mailSender.send`, hãy có `smtp_attempt_count` hoặc sự kiện `SMTP_SEND_STARTED`, đừng đổi ý nghĩa `attempt_count` tùy trường hợp.

| Bộ đếm | Định nghĩa | Khi cập nhật |
| --- | --- | --- |
| `attempt_count` | Tổng số lượt dispatch đã được claim | Trong transaction claim |
| `smtp_attempt_count` (tùy chọn) | Số lượt thực sự bắt đầu gọi transport | Trước khi gọi SMTP; có giới hạn sai lệch khi crash |
| `failure_count` (tùy chọn) | Số lượt được ghi nhận thất bại | Khi lưu kết quả thất bại |
| `consecutive_failure_count` (tùy chọn) | Số lỗi liên tiếp tính tới hiện tại | Khi áp dụng chính sách retry |

Không nhất thiết cần mọi bộ đếm. Với một bản ghi chỉ gửi tới một người nhận và dừng ở `SENT`, `attempt_count` và **bảng lịch sử attempt** thường đủ. Đừng suy ra `failure_count = attempt_count - 1`: nếu có lượt bị crash hoặc kết quả chưa xác định, phép tính sẽ sai.

### 2.1. Số attempt bắt đầu khác số attempt đã hoàn thành

Giả sử:

~~~text
attempt_count = 3

Lần 1: SMTP connection refused -> RETRY
Lần 2: SMTP timeout sau DATA -> UNKNOWN
Lần 3: Worker được claim, JVM dừng trước khi gọi SMTP
~~~

Số lần claim đã bắt đầu là ba, nhưng chỉ có hai lượt đủ thông tin để phân loại kết quả và chưa thể kết luận email đã tới SMTP bao nhiêu lần. Vì vậy, **đếm phải gắn với trạng thái của mỗi attempt**, không chỉ một con số tổng.

## 3. Thiết kế trạng thái phù hợp với retry

Một outbox row thường có vòng đời:

| Trạng thái | Ý nghĩa | Có thể tự động claim? |
| --- | --- | --- |
| `PENDING` | Mới tạo, chưa dispatch | Có |
| `PROCESSING` | Worker đang giữ lease và xử lý | Không, trừ khi lease hết hạn và được reclaim |
| `RETRY` | Thất bại đã được phân loại là có thể thử lại | Có sau `next_attempt_at` |
| `SENT` | `JavaMailSender.send` trả về thành công, đã được ghi nhận | Không |
| `FAILED` | Hết số lượt thử hoặc lỗi thuộc chính sách dừng | Không tự động |
| `UNKNOWN` (tùy chọn) | Không xác định SMTP đã nhận thư hay chưa | Theo chính sách đối soát/duplicate risk |
| `CANCELLED` (tùy chọn) | Nghiệp vụ hủy yêu cầu gửi | Không |

Sơ đồ:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING: claim
    RETRY --> PROCESSING: due + claim
    PROCESSING --> SENT: SMTP accepted
    PROCESSING --> RETRY: temporary failure
    PROCESSING --> FAILED: permanent/max attempts
    PROCESSING --> UNKNOWN: ambiguous SMTP outcome
    PROCESSING --> PROCESSING: expired lease reclaimed
    PENDING --> CANCELLED: business cancel
    RETRY --> CANCELLED: business cancel
    UNKNOWN --> RETRY: approved retry
    UNKNOWN --> SENT: provider reconciliation
~~~

Không phải hệ thống nào cũng cần `UNKNOWN`. Nếu doanh nghiệp chấp nhận at-least-once, có thể coi lỗi mơ hồ là `RETRY`, nhưng phải nêu rõ **có thể gửi trùng**. Với email rất nhạy cảm, một trạng thái đối soát riêng giúp hạn chế gửi trùng ngoài ý muốn.

### 3.1. Quy tắc bất biến

Các invariant quan trọng:

1. `attempt_count` không giảm.
2. Một bản ghi chỉ có **một attempt đang nắm quyền hợp lệ** tại một thời điểm; điều này được thực thi bằng claim/lease/version ở database.
3. Chỉ worker sở hữu lease hiện tại mới cập nhật kết quả.
4. `SENT` không quay lại `RETRY` một cách tự động.
5. `FAILED` không tự retry mãi mãi; thao tác redrive cần được ủy quyền và ghi audit.
6. Không chuyển sang `SENT` **trước** lời gọi SMTP; làm vậy có thể đánh mất email khi tiến trình dừng.
7. `SENT` không có nghĩa đã đến hộp thư; bounce/delivery cần trạng thái hoặc nguồn sự kiện riêng.

## 4. Lưu trạng thái hiện tại và lịch sử từng attempt

Có hai mô hình dữ liệu cơ bản:

**Mô hình A — Một bảng outbox:** chứa `attempt_count`, `last_error_code`, `last_error_message`, `next_attempt_at` và trạng thái hiện tại. Dễ triển khai, phù hợp khi chỉ cần biết lần thất bại gần nhất.

**Mô hình B — Outbox + attempt history:** ngoài thông tin tổng hợp, mỗi lượt thử có bản ghi riêng chứa thời gian bắt đầu, kết thúc, worker, giai đoạn lỗi, mã lỗi và kết quả. Phù hợp khi cần audit, điều tra lỗi tái diễn hoặc đối soát tình huống SMTP mơ hồ.

| Nhu cầu | Một bảng outbox | Outbox + lịch sử attempt |
| --- | --- | --- |
| Worker lấy job đến hạn | Đủ | Đủ |
| Biết tổng số lượt thử | Đủ | Đủ |
| Biết lỗi gần nhất | Đủ | Đủ |
| So sánh các lỗi qua nhiều lần retry | Không đầy đủ | Có |
| Điều tra crash giữa SMTP và commit | Hạn chế | Tốt hơn |
| Audit redrive và worker xử lý | Có thể thêm cột | Dễ mở rộng |
| Chi phí storage/transaction | Thấp hơn | Cao hơn |

Với ứng dụng gửi email giao dịch quan trọng, nên lưu lịch sử attempt hoặc ít nhất có event log bền vững tương đương. Dù dùng mô hình nào, **số attempt phải được cập nhật nguyên tử** để tránh mất increment khi nhiều worker cạnh tranh.

## 5. Thiết kế bảng mail_outbox

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    delivery_key VARCHAR(180) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    template_name VARCHAR(160) NOT NULL,
    payload JSONB NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    lease_owner VARCHAR(120),
    lease_until TIMESTAMPTZ,
    claim_token UUID,

    last_error_code VARCHAR(100),
    last_error_kind VARCHAR(30),
    last_error_stage VARCHAR(40),
    last_error_summary VARCHAR(500),
    last_failed_at TIMESTAMPTZ,

    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT ck_mail_status CHECK (
        status IN (
            'PENDING', 'PROCESSING', 'RETRY',
            'SENT', 'FAILED', 'UNKNOWN', 'CANCELLED'
        )
    ),
    CONSTRAINT ck_mail_attempts CHECK (
        attempt_count >= 0 AND max_attempts > 0
    ),
    CONSTRAINT ux_mail_delivery_key UNIQUE (delivery_key)
);

CREATE INDEX ix_mail_outbox_due
    ON mail_outbox (status, next_attempt_at, created_at);

CREATE INDEX ix_mail_outbox_expired_lease
    ON mail_outbox (status, lease_until);
~~~

Ý nghĩa các cột:

- `delivery_key`: idempotency key ở thời điểm tạo yêu cầu gửi, phải phù hợp với nghiệp vụ. Nếu một event gửi cho nhiều người, khóa có thể gồm event ID, template và delivery/recipient identity.
- `attempt_count`: số lượt claim đã bắt đầu, không chỉ là số exception.
- `max_attempts`: trần retry riêng cho loại email hoặc policy.
- `next_attempt_at`: thời điểm được phép claim sau khi lỗi; không để worker retry ngay vô hạn.
- `lease_owner` / `lease_until`: quyền xử lý có thời hạn.
- `claim_token`: định danh duy nhất của lần claim để tránh worker cũ ghi đè kết quả của worker mới.
- `last_error_code`: mã lỗi do ứng dụng chuẩn hóa, hỗ trợ lọc/metric.
- `last_error_kind`: ví dụ `TRANSIENT`, `PERMANENT`, `UNKNOWN`.
- `last_error_stage`: nơi lỗi xảy ra, như `RENDER`, `MIME`, `SMTP_CONNECT`, `SMTP_SEND` hoặc `STATE_UPDATE`.
- `last_error_summary`: mô tả ngắn đã loại thông tin nhạy cảm.
- `last_failed_at`: thời điểm ghi nhận lỗi lần gần nhất.

`payload` có thể chứa thông tin cá nhân hoặc token; phải có kiểm soát truy cập, mã hóa/retention phù hợp. Không lưu password, secret SMTP hoặc nội dung không cần thiết vào payload.

### 5.1. Không dùng delivery_key sai phạm vi

Ví dụ khóa `order-confirmed:{orderId}` có thể đúng nếu nghiệp vụ chỉ phát một email xác nhận cho mỗi đơn hàng. Nhưng nếu cần gửi cùng loại email cho nhiều người hoặc phát lại hợp lệ sau một phiên bản đơn hàng mới, khóa đó quá rộng.

Một định dạng có chủ đích:

~~~text
delivery_key = event_type + ":" + event_id
             + ":" + notification_kind
             + ":" + recipient_identity
~~~

Nếu sử dụng recipient email trong khóa, cần cân nhắc chuẩn hóa, thay đổi địa chỉ và việc rò rỉ PII. Có thể dùng một delivery UUID được tạo từ yêu cầu đã deduplicate theo nghiệp vụ, hoặc hash có khóa theo chính sách riêng. Không sử dụng địa chỉ email làm metric label.

## 6. Bảng lịch sử mail_delivery_attempt

Mỗi lượt dispatch có một bản ghi riêng:

~~~sql
CREATE TABLE mail_delivery_attempt (
    id UUID PRIMARY KEY,
    outbox_id UUID NOT NULL REFERENCES mail_outbox(id),
    attempt_no INTEGER NOT NULL,
    claim_token UUID NOT NULL,
    worker_id VARCHAR(120) NOT NULL,

    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(24) NOT NULL DEFAULT 'STARTED',
    failure_kind VARCHAR(30),
    failure_stage VARCHAR(40),
    error_code VARCHAR(100),
    safe_error_summary VARCHAR(500),
    smtp_reply_code VARCHAR(10),
    duration_ms BIGINT,

    CONSTRAINT ux_mail_attempt_number UNIQUE (
        outbox_id, attempt_no
    ),
    CONSTRAINT ux_mail_attempt_claim UNIQUE (claim_token),
    CONSTRAINT ck_mail_attempt_no CHECK (attempt_no > 0),
    CONSTRAINT ck_mail_attempt_outcome CHECK (
        outcome IN (
            'STARTED', 'SMTP_ACCEPTED',
            'RETRYABLE_FAILURE', 'PERMANENT_FAILURE',
            'UNKNOWN', 'ABANDONED'
        )
    )
);

CREATE INDEX ix_mail_attempt_by_delivery
    ON mail_delivery_attempt(outbox_id, attempt_no DESC);
~~~

**Một attempt có thể còn `STARTED` lâu hơn dự kiến** nếu worker chết hoặc không ghi được kết quả. Đó là bằng chứng hữu ích: đã claim nhưng chưa xác định kết quả. Không nên mặc định mọi attempt chưa kết thúc đều là “SMTP chưa gửi”.

### 6.1. Snapshot tổng hợp và lịch sử phải thống nhất

Bảng outbox giữ trạng thái hiện tại để worker query nhanh. Bảng attempt giữ lịch sử để audit. Khi bắt đầu lượt mới, **tăng `attempt_count` và insert attempt row trong cùng transaction**. Khi hoàn tất, cập nhật outbox và attempt row trong cùng transaction ghi kết quả.

~~~text
Transaction claim
  UPDATE mail_outbox
    attempt_count = attempt_count + 1
    status = PROCESSING
    claim_token = new token
  INSERT mail_delivery_attempt
    attempt_no = new attempt_count
    outcome = STARTED
  COMMIT
             |
             v
    SMTP send (ngoài DB transaction)
             |
             v
Transaction result
  UPDATE mail_outbox -> SENT / RETRY / FAILED / UNKNOWN
  UPDATE mail_delivery_attempt -> final outcome
  COMMIT
~~~

Giữ hai phép ghi cùng một transaction giúp tránh tình huống outbox báo đã có lần thử thứ ba nhưng lịch sử chỉ có hai bản ghi đã commit, hoặc ngược lại.

## 7. Claim nguyên tử và tăng attempt_count

Khi có nhiều worker, cách sau **không an toàn**:

~~~java
MailOutbox row = repository.findPending();
row.setAttemptCount(row.getAttemptCount() + 1);
mailSender.send(message);
repository.save(row);
~~~

Hai worker có thể cùng đọc `attempt_count = 0`, cùng tăng lên một và gửi cùng email; lần ghi cuối ghi đè lần đầu. Đây vừa là lost update vừa là duplicate dispatch.

Với PostgreSQL, có thể claim bằng `FOR UPDATE SKIP LOCKED` và một transaction ngắn. Ví dụ truy vấn claim một batch:

~~~sql
WITH selected AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('PENDING', 'RETRY')
        AND next_attempt_at <= now()
        AND attempt_count < max_attempts
    )
    OR (
        status = 'PROCESSING'
        AND lease_until < now()
        AND attempt_count < max_attempts
    )
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS o
SET status = 'PROCESSING',
    attempt_count = o.attempt_count + 1,
    lease_owner = :worker_id,
    lease_until = :lease_until,
    claim_token = gen_random_uuid(),
    updated_at = now(),
    version = o.version + 1
FROM selected
WHERE o.id = selected.id
RETURNING o.id, o.attempt_count, o.claim_token,
          o.lease_owner, o.version, o.payload,
          o.recipient, o.template_name;
~~~

Truy vấn này là ví dụ theo PostgreSQL; `gen_random_uuid()` cần khả năng sinh UUID phù hợp của phiên bản/cấu hình database. Trong ứng dụng thật, repository phải chạy toàn bộ claim **trong transaction**, và ngay sau câu UPDATE cần insert attempt row với `attempt_no = attempt_count` và `claim_token` vừa trả về, trước khi commit.

**Điểm cần xử lý thêm:** nếu reclaim một `PROCESSING` đã hết lease, attempt cũ có thể còn `STARTED`. Nên đánh dấu attempt cũ `ABANDONED` hoặc `UNKNOWN` trong transaction claim theo policy, nhưng không tự suy ra SMTP chưa nhận thư. Nếu attempt cuối đã chạm `max_attempts` rồi worker chết, cần một reconciler/cleanup chuyển hàng tới `FAILED` hoặc `UNKNOWN`; không để nó `PROCESSING` hết hạn mãi mãi chỉ vì điều kiện claim giới hạn số lần thử.

### 7.1. Dùng claim_token để chặn cập nhật lỗi thời

`claim_token` là định danh cho **một lần chiếm quyền**, không chỉ cho worker process. Worker A claim token A. Nếu lease hết hạn và worker B claim token B, worker A không còn quyền ghi trạng thái dù nó vẫn đang chạy.

Ví dụ:

~~~text
12:00 Worker A claims -> token A, attempt 1
12:02 Lease A expires
12:03 Worker B claims -> token B, attempt 2
12:04 Worker A attempts mark SENT with token A -> UPDATE 0 rows
12:05 Worker B records its own result with token B
~~~

Giải pháp cập nhật có điều kiện theo claim token bảo vệ **database state**. Nó không thể thu hồi email mà worker A có thể đã gửi; duplicate vẫn cần chính sách riêng.

### 7.2. Thời điểm tăng counter

Nếu chỉ tăng `attempt_count` **sau khi** SMTP gửi thất bại, worker chết giữa lúc gửi sẽ không để lại dấu vết attempt; batch có thể retry vô hạn mà counter không tăng. Vì vậy, tăng khi claim và lưu `STARTED` trước khi gọi SMTP là một quy ước dễ phục hồi hơn.

Nếu yêu cầu đo chính xác “số lần gọi transport” thay vì “số lượt dispatch”, ghi thêm một timestamp/sự kiện `smtp_send_started_at` ngay trước call. Nhưng ngay cả sự kiện đó cũng không thể tạo atomic transaction với SMTP: luôn có crash window giữa database và side effect bên ngoài.

## 8. Lưu kết quả thành công và thông tin thất bại

Kết quả của một attempt gồm hai phần:

- **Outcome** của lần thử: thành công, thất bại có thể retry, thất bại vĩnh viễn, kết quả chưa rõ hoặc bị bỏ dở.
- **Quyết định cho outbox:** chuyển `SENT`, `RETRY`, `FAILED` hoặc `UNKNOWN`.

Không nên gộp hai ý này thành một chuỗi exception. Ví dụ `SMTP_CONNECTION_TIMEOUT` là nguyên nhân, `TRANSIENT` là phân loại, còn `RETRY` là quyết định scheduling. Những giá trị đó có quan hệ nhưng không giống nhau.

### 8.1. Lưu thành công sau JavaMailSender.send

Trình tự đúng:

~~~java
MimeMessage message = messageFactory.create(claimed);
mailSender.send(message);
stateService.markSent(claimed);
~~~

Chỉ sau khi `send` trả về bình thường mới cập nhật `SENT`. Một ví dụ update PostgreSQL:

~~~sql
UPDATE mail_outbox
SET status = 'SENT',
    sent_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    claim_token = NULL,
    last_error_code = NULL,
    last_error_kind = NULL,
    last_error_stage = NULL,
    last_error_summary = NULL,
    updated_at = now(),
    version = version + 1
WHERE id = :outbox_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;
~~~

Trong **cùng transaction** ghi thành công, cập nhật attempt hiện tại:

~~~sql
UPDATE mail_delivery_attempt
SET outcome = 'SMTP_ACCEPTED',
    finished_at = now(),
    duration_ms = :elapsed_ms,
    failure_kind = NULL,
    failure_stage = NULL,
    error_code = NULL,
    safe_error_summary = NULL
WHERE outbox_id = :outbox_id
  AND claim_token = :claim_token
  AND outcome = 'STARTED';
~~~

Chỉ commit khi cả hai update phù hợp với attempt hiện tại. Nếu update outbox trả về 0 hàng, worker có thể đã mất lease hoặc trạng thái bị thay đổi; **không đánh dấu attempt là accepted của một claim không còn hợp lệ như thể đã đồng bộ trạng thái**. Có thể ghi một sự kiện đối soát riêng, vì SMTP thực tế có thể đã chấp nhận email.

### 8.2. Lưu thất bại có thể retry

Giả sử lần thứ hai thất bại do SMTP tạm thời không khả dụng. Worker lưu:

~~~text
outbox.status          = RETRY
outbox.attempt_count   = 2
outbox.next_attempt_at = thời điểm tính theo backoff
outbox.last_error_code = SMTP_TEMPORARY_UNAVAILABLE
outbox.last_error_kind = TRANSIENT
outbox.last_error_stage = SMTP_CONNECT
outbox.last_failed_at  = thời điểm thất bại

attempt[2].outcome       = RETRYABLE_FAILURE
attempt[2].error_code    = SMTP_TEMPORARY_UNAVAILABLE
attempt[2].failure_stage = SMTP_CONNECT
attempt[2].finished_at   = thời điểm kết thúc
~~~

SQL minh họa:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY',
    next_attempt_at = :next_attempt_at,
    last_error_code = :error_code,
    last_error_kind = 'TRANSIENT',
    last_error_stage = :error_stage,
    last_error_summary = :safe_summary,
    last_failed_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    claim_token = NULL,
    updated_at = now(),
    version = version + 1
WHERE id = :outbox_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;
~~~

Với history:

~~~sql
UPDATE mail_delivery_attempt
SET outcome = 'RETRYABLE_FAILURE',
    finished_at = now(),
    duration_ms = :elapsed_ms,
    failure_kind = 'TRANSIENT',
    failure_stage = :error_stage,
    error_code = :error_code,
    safe_error_summary = :safe_summary,
    smtp_reply_code = :smtp_reply_code
WHERE outbox_id = :outbox_id
  AND claim_token = :claim_token
  AND outcome = 'STARTED';
~~~

Hai update cần được thực thi qua một service transaction ngắn và xác nhận số hàng được cập nhật. Nếu một update không khớp, rollback transaction và báo xung đột, không để trạng thái tổng hợp và lịch sử lệch nhau.

### 8.3. Lưu thất bại vĩnh viễn hoặc hết lượt

Nếu dữ liệu template không hợp lệ, địa chỉ bị từ chối vĩnh viễn hoặc đã đến giới hạn số lượt:

~~~text
outbox.status = FAILED
attempt.outcome = PERMANENT_FAILURE
outbox.last_error_code = MAIL_TEMPLATE_INVALID
outbox.last_error_kind = PERMANENT
~~~

Khi hết số lượt thử vì nhiều lỗi tạm thời, có thể ghi:

~~~text
outbox.status = FAILED
attempt.outcome = RETRYABLE_FAILURE
outbox.last_error_kind = TRANSIENT
outbox.last_error_code = SMTP_TEMPORARY_UNAVAILABLE
terminal_reason = MAX_ATTEMPTS_EXHAUSTED
~~~

Lần thử cuối vẫn có **nguyên nhân tạm thời**, nhưng hệ thống dừng vì **chính sách tối đa số lượt**. Đừng tự biến loại lỗi thành “permanent” chỉ vì đã retry nhiều lần. Nếu cần phân biệt rõ, thêm `terminal_reason` vào schema và audit event, thay vì ghi đè `last_error_code` bằng `MAX_ATTEMPTS` rồi mất nguyên nhân SMTP thực tế.

### 8.4. Giữ lỗi trước đó trong history khi đã SENT

Khi gửi thành công sau vài lần retry, `last_error_*` trên outbox có thể xóa để phản ánh trạng thái hiện tại đã thành công. Nhưng **bảng attempt history phải giữ nguyên lỗi của những lần trước** để điều tra độ ổn định SMTP.

Ví dụ:

| Attempt | Outcome | Error code |
| --- | --- | --- |
| 1 | RETRYABLE_FAILURE | SMTP_CONNECTION_TIMEOUT |
| 2 | RETRYABLE_FAILURE | SMTP_SERVER_BUSY |
| 3 | SMTP_ACCEPTED | — |

Outbox hiện tại: `SENT`, `attempt_count = 3`, `sent_at` có giá trị. Dữ liệu lịch sử cho biết thư cần ba lượt dispatch mới được chấp nhận.

## 9. Mô tả nguyên nhân thất bại một cách có cấu trúc

Một chuỗi `lastError = exception.toString()` không đủ ổn định để xử lý tự động, đồng thời có thể lộ dữ liệu cá nhân. Nên biểu diễn ít nhất bằng:

| Trường | Mục đích | Ví dụ |
| --- | --- | --- |
| `error_code` | Mã lỗi do ứng dụng kiểm soát, dùng cho filter/alert | `SMTP_AUTH_FAILED` |
| `failure_kind` | Nhóm chính sách | `TRANSIENT`, `PERMANENT`, `UNKNOWN` |
| `failure_stage` | Bước xử lý lỗi | `RENDER`, `MIME`, `SMTP_CONNECT`, `SMTP_SEND`, `STATE_UPDATE` |
| `safe_summary` | Tóm tắt ngắn, không có dữ liệu nhạy cảm | `SMTP authentication rejected` |
| `smtp_reply_code` | Mã SMTP nếu thực sự lấy được | `421` hoặc `550` |
| `exception_type` (tùy chọn) | Tên class exception để chẩn đoán | `MailSendException` |
| `occurred_at` | Thời điểm lỗi | Timestamp UTC |
| `attempt_no` | Số lượt được ghi nhận lỗi | `3` |

Không phải mọi exception đều có SMTP reply code. Ví dụ lỗi không resolve được DNS xảy ra trước khi có phản hồi SMTP, nên `smtp_reply_code` phải có thể null. Không “sáng tác” mã 4xx/5xx chỉ từ thông điệp exception.

### 9.1. Giai đoạn lỗi giúp quyết định retry

| Giai đoạn | Ví dụ | Có thể kết luận SMTP đã nhận thư? |
| --- | --- | --- |
| `VALIDATE` | Thiếu recipient, subject không hợp lệ | Chưa gọi SMTP |
| `RENDER` | Template thiếu biến, lỗi model | Chưa gọi SMTP |
| `MIME` | Không đọc được attachment, `MessagingException` | Thường chưa gọi SMTP |
| `SMTP_CONNECT` | Không kết nối được SMTP | Thường chưa submit message |
| `SMTP_AUTH` | Server từ chối xác thực | Chưa submit message |
| `SMTP_SEND` | Lỗi trong trao đổi với SMTP | Tùy thời điểm; có thể không chắc chắn |
| `STATE_UPDATE` | Database lỗi sau send | SMTP có thể đã chấp nhận thư |

Phân loại theo stage phải dựa trên sự kiện thực tế. Ví dụ nếu thư viện ném một `MailSendException` sau khi bắt đầu SMTP DATA, không thể mặc định stage là `SMTP_CONNECT`.

### 9.2. Error code ổn định hơn exception message

Exception message có thể thay đổi theo phiên bản thư viện, provider hoặc locale. Vì vậy, nên viết một bộ phân loại chuyển exception thành mã lỗi ổn định:

~~~java
public enum FailureKind {
    TRANSIENT,
    PERMANENT,
    UNKNOWN
}

public enum FailureStage {
    VALIDATE,
    RENDER,
    MIME,
    SMTP_CONNECT,
    SMTP_AUTH,
    SMTP_SEND,
    STATE_UPDATE
}

public record MailFailure(
        FailureKind kind,
        FailureStage stage,
        String errorCode,
        String safeSummary,
        String smtpReplyCode) {
}
~~~

`MailFailure` là dữ liệu để **lưu vào database**, không phải wrapper chứa nguyên `Throwable`. Có thể giữ exception stack trace trong hệ thống logging riêng theo chính sách bảo mật, nhưng đừng ghi nó vào một cột VARCHAR ngắn hoặc dùng nó làm khóa logic.

## 10. Phân loại exception trong Spring Framework Mail

API `JavaMailSender` và `MimeMessageHelper` có các loại lỗi khác nhau:

| Exception | Điều thường biểu hiện | Ví dụ phân loại |
| --- | --- | --- |
| `MailAuthenticationException` | Không xác thực được SMTP | `SMTP_AUTH_FAILED`, thường cần operator xử lý |
| `MailSendException` | Lỗi khi gửi message, có thể chứa nested cause | Cần xem response/phase, có thể transient/permanent/unknown |
| `MailPreparationException` | Lỗi chuẩn bị mail trong luồng ứng dụng | Thường cần sửa dữ liệu hoặc template |
| `MailParseException` | Lỗi parse message/địa chỉ theo Spring mail | Thường không retry nguyên trạng |
| `jakarta.mail.MessagingException` | Checked exception khi dựng MIME hoặc API Jakarta Mail | Phụ thuộc bước gây lỗi |
| `org.springframework.mail.MailException` | Lớp cha runtime | Chưa đủ để kết luận có thể retry |

SMTP reply:

- Nhóm **4xx** thường biểu thị lỗi tạm thời, ví dụ server đang bận hoặc một giới hạn tạm.
- Nhóm **5xx** thường biểu thị lỗi vĩnh viễn với yêu cầu hiện tại, ví dụ địa chỉ bị từ chối.
- Nhưng xử lý đúng còn phụ thuộc **lệnh SMTP**, response mở rộng và chính sách provider.

Nếu mất kết nối sau khi message được truyền nhưng trước khi ứng dụng nhận phản hồi cuối cùng, kết quả có thể **UNKNOWN**. Retry có thể tạo email trùng; dừng retry có thể làm mất email chưa được server chấp nhận. Đây là quyết định chính sách cần nêu rõ chứ không tự giải bằng một câu lệnh catch.

### 10.1. Ví dụ bộ phân loại tối giản

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailParseException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.MailSendException;

public class MailFailureClassifier {

    public MailFailure classify(MailException error) {
        if (error instanceof MailAuthenticationException) {
            return new MailFailure(
                    FailureKind.PERMANENT,
                    FailureStage.SMTP_AUTH,
                    "SMTP_AUTH_FAILED",
                    "SMTP authentication was rejected",
                    null);
        }

        if (error instanceof MailPreparationException
                || error instanceof MailParseException) {
            return new MailFailure(
                    FailureKind.PERMANENT,
                    FailureStage.MIME,
                    "MAIL_PREPARATION_FAILED",
                    "Cannot prepare outgoing mail",
                    null);
        }

        if (error instanceof MailSendException) {
            // Production: inspect nested causes / SMTP response / phase.
            return new MailFailure(
                    FailureKind.UNKNOWN,
                    FailureStage.SMTP_SEND,
                    "SMTP_SEND_UNCLASSIFIED",
                    "SMTP send outcome needs classification",
                    null);
        }

        return new MailFailure(
                FailureKind.UNKNOWN,
                FailureStage.SMTP_SEND,
                "MAIL_UNCLASSIFIED",
                "Mail transport failed",
                null);
    }
}
~~~

Đây là ví dụ cố ý **không tự coi mọi `MailSendException` là lỗi tạm thời**. Trong production, cần bổ sung phân tích nested cause và response code. Lỗi xác thực có thể redrive sau khi sửa cấu hình; `PERMANENT` ở đây nghĩa là không retry nguyên trạng ngay trong vòng tự động.

### 10.2. Thông điệp exception có thể chứa PII

Không làm:

~~~java
outbox.setLastErrorMessage(exception.getMessage());
~~~

Nguyên nhân: message đôi khi chứa địa chỉ email, host, token trong URL hoặc chi tiết message. Nếu muốn giữ một số thông tin chẩn đoán, hãy dùng mã lỗi đã chuẩn hóa và safe summary tự xây:

~~~java
MailFailure failure = classifier.classify(mailException);
outboxRepository.recordFailure(
        outboxId,
        failure.errorCode(),
        failure.safeSummary());
~~~

Nếu thực sự cần nguyên stack trace, lưu vào hệ thống logging có kiểm soát truy cập, masking và retention thích hợp. Không mặc định stack trace luôn an toàn để đưa vào dashboard hoặc gửi cho người dùng.

## 11. Từ nguyên nhân thất bại đến quyết định retry

Sau khi đã lưu phân loại nguyên nhân, worker cần quyết định:

- **RETRY:** lỗi có thể khắc phục bằng thử lại và chưa quá giới hạn.
- **FAILED:** lỗi không tự khắc phục bằng retry hoặc đã hết lượt.
- **UNKNOWN:** có nguy cơ SMTP đã nhận thư; cần đối soát hoặc retry theo chính sách chấp nhận duplicate.

Không nên đồng nhất `failure_kind = TRANSIENT` với `status = RETRY`: một lỗi tạm thời vẫn có thể dẫn đến `FAILED` nếu vượt số lần thử tối đa hoặc đã quá hạn nghiệp vụ.

### 11.1. Chính sách quyết định có xét max_attempts

Ví dụ:

~~~java
public enum NextAction {
    RETRY,
    FAIL,
    RECONCILE
}

public record RetryDecision(
        NextAction action,
        Instant nextAttemptAt,
        String terminalReason) {
}

public final class MailRetryPolicy {
    private final int maxAttempts;
    private final Duration initialDelay;
    private final Duration maxDelay;

    public MailRetryPolicy(
            int maxAttempts,
            Duration initialDelay,
            Duration maxDelay) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be positive");
        }
        this.maxAttempts = maxAttempts;
        this.initialDelay = initialDelay;
        this.maxDelay = maxDelay;
    }

    public RetryDecision decide(
            int currentAttempt,
            MailFailure failure,
            Instant now,
            Instant businessDeadline) {

        if (failure.kind() == FailureKind.UNKNOWN) {
            return new RetryDecision(
                    NextAction.RECONCILE,
                    null,
                    "SMTP_OUTCOME_UNKNOWN");
        }
        if (failure.kind() == FailureKind.PERMANENT) {
            return new RetryDecision(
                    NextAction.FAIL,
                    null,
                    "PERMANENT_FAILURE");
        }
        if (currentAttempt >= maxAttempts) {
            return new RetryDecision(
                    NextAction.FAIL,
                    null,
                    "MAX_ATTEMPTS_EXHAUSTED");
        }

        Duration delay = calculateDelay(currentAttempt);
        Instant nextAttempt = now.plus(delay);

        if (businessDeadline != null
                && nextAttempt.isAfter(businessDeadline)) {
            return new RetryDecision(
                    NextAction.FAIL,
                    null,
                    "BUSINESS_DEADLINE_EXCEEDED");
        }
        return new RetryDecision(
                NextAction.RETRY,
                nextAttempt,
                null);
    }

    private Duration calculateDelay(int currentAttempt) {
        // Chặn shift/overflow khi currentAttempt rất lớn.
        int exponent = Math.min(currentAttempt - 1, 20);
        long factor = 1L << exponent;
        Duration scaled = initialDelay.multipliedBy(factor);
        return scaled.compareTo(maxDelay) > 0
                ? maxDelay : scaled;
    }
}
~~~

Đây là một policy minh họa với delay không jitter. Trong ứng dụng production, cần validate `initialDelay`/`maxDelay` và thêm jitter có giới hạn. `currentAttempt` là số attempt **vừa thất bại**, đã được tăng lúc claim; nhờ vậy điều kiện `>= maxAttempts` có ý nghĩa rõ ràng.

### 11.2. Exponential backoff và jitter

Một công thức thường dùng:

\[
d_n = \min\left(d_{\max}, d_0 \times 2^{n-1}\right)
\]

Trong đó `n` là attempt number; `d_0` là delay ban đầu. Thêm jitter để các worker không retry đồng loạt:

\[
d^\prime_n = \operatorname{random}(0, d_n)
\]

hoặc dùng jitter một tỷ lệ nhỏ quanh `d_n`. Với email bảo mật có thời hạn sử dụng ngắn, còn phải xét `businessDeadline` để không gửi link hết hạn. Đừng schedule retry một giờ sau khi token reset password đã hết hiệu lực sau 15 phút.

Ví dụ cấu hình minh họa:

| Attempt vừa thất bại | Delay cơ sở | Hành động |
| --- | --- | --- |
| 1 | 30 giây | RETRY nếu transient |
| 2 | 1 phút | RETRY |
| 3 | 2 phút | RETRY |
| 4 | 4 phút | RETRY |
| 5 | — | FAILED nếu `max_attempts = 5` |

Không có một lịch retry cố định phù hợp cho mọi provider. Chọn theo SLA, quota SMTP, thời hạn hiệu lực của email và chính sách vận hành.

### 11.3. Lưu `next_attempt_at`, không sleep trong worker

Tránh:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    Thread.sleep(60_000); // Chiếm worker và không bền vững.
    mailSender.send(message);
}
~~~

Thay vào đó, cập nhật:

~~~text
status = RETRY
attempt_count = 2
next_attempt_at = 2026-11-12T09:00:00Z
last_error_code = SMTP_TEMPORARY_UNAVAILABLE
~~~

Worker hiện tại kết thúc và có thể xử lý email khác. Một scheduler hoặc queue consumer sẽ claim lại sau thời điểm đến hạn. Nếu tiến trình restart, lịch retry vẫn còn trong database.

## 12. Ví dụ Spring: tách transaction claim, send và lưu kết quả

Một kiến trúc dễ kiểm soát:

~~~text
MailOutboxPoller
        |
        v
OutboxClaimService (@Transactional)
        | claim + attempt_count++ + insert attempt
        v
ClaimedMail (snapshot with claimToken)
        |
        v
MailDispatchWorker (không giữ DB transaction)
        | render + JavaMailSender.send
        v
OutboxResultService (@Transactional)
        | markSent / recordFailure / markUnknown
        v
PostgreSQL outbox + attempt history
~~~

Điều quan trọng là **SMTP send không nằm trong transaction giữ khóa outbox**. Database không thể rollback một email đã được SMTP server chấp nhận.

### 12.1. DTO cho lượt claim

~~~java
package com.example.mail.outbox;

import java.util.UUID;

public record ClaimedMail(
        UUID outboxId,
        UUID claimToken,
        int attemptNumber,
        String recipient,
        String templateName,
        String payloadJson) {
}
~~~

Số attempt và claim token đi cùng job suốt một lượt xử lý. Không lấy `attempt_count` mới nhất từ database ở cuối rồi nhầm nó với attempt của worker cũ.

### 12.2. Service claim có transaction ngắn

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OutboxClaimService {

    private final MailOutboxRepository repository;

    public OutboxClaimService(MailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedMail> claimDue(
            String workerId,
            int batchSize,
            Instant leaseUntil) {

        // Repository phải claim nguyên tử và insert attempt
        // trong CÙNG transaction này.
        return repository.claimAndCreateAttempts(
                workerId, batchSize, leaseUntil);
    }
}
~~~

`claimAndCreateAttempts` là phương thức repository do ứng dụng triển khai bằng SQL/transaction phù hợp database. Nó phải:

1. Chọn hàng chưa có lease còn hiệu lực, đến hạn retry.
2. Claim hàng nguyên tử, tăng counter, tạo claim token mới.
3. Đóng/đánh dấu attempt cũ nếu reclaim theo policy.
4. Insert attempt row `STARTED` cho lượt mới.
5. Trả snapshot có attempt number và token đúng sau claim.

Nếu bất kỳ bước nào thất bại, toàn bộ transaction claim rollback, để worker khác có thể thử khi hệ thống ổn định.

### 12.3. Service ghi kết quả có transaction riêng

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OutboxResultService {

    private final MailOutboxRepository repository;

    public OutboxResultService(MailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public boolean recordAccepted(
            ClaimedMail mail, long durationMillis) {

        return repository.markSentAndCompleteAttempt(
                mail.outboxId(),
                mail.claimToken(),
                mail.attemptNumber(),
                durationMillis);
    }

    @Transactional
    public boolean recordFailure(
            ClaimedMail mail,
            MailFailure failure,
            RetryDecision retry,
            long durationMillis) {

        return repository.recordFailureAndCompleteAttempt(
                mail.outboxId(),
                mail.claimToken(),
                mail.attemptNumber(),
                failure,
                retry,
                durationMillis);
    }
}
~~~

Repository thực thi **cập nhật outbox và attempt trong một transaction**. Return `true` chỉ khi cả hai bản ghi của đúng claim được cập nhật. Nếu không còn owner hoặc claim token đã bị thay, hãy rollback, trả về `false` và phát cảnh báo/metric `state_conflict`.

Không coi `false` là lý do để gọi SMTP lại ngay. Đặc biệt nếu transport vừa trả về thành công, database conflict không chứng minh email chưa được gửi.

### 12.4. Worker phân loại lỗi và lưu kết quả

~~~java
package com.example.mail.outbox;

import java.time.Instant;
import java.util.List;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MailDispatchWorker {

    private final JavaMailSender mailSender;
    private final MailMessageFactory messageFactory;
    private final MailFailureClassifier classifier;
    private final MailRetryPolicy retryPolicy;
    private final OutboxResultService resultService;
    private final OutboxClaimService claimService;

    public MailDispatchWorker(
            JavaMailSender mailSender,
            MailMessageFactory messageFactory,
            MailFailureClassifier classifier,
            MailRetryPolicy retryPolicy,
            OutboxResultService resultService,
            OutboxClaimService claimService) {
        this.mailSender = mailSender;
        this.messageFactory = messageFactory;
        this.classifier = classifier;
        this.retryPolicy = retryPolicy;
        this.resultService = resultService;
        this.claimService = claimService;
    }

    public void dispatchBatch(
            String workerId, int batchSize, Instant leaseUntil) {
        List<ClaimedMail> batch =
                claimService.claimDue(workerId, batchSize, leaseUntil);

        for (ClaimedMail mail : batch) {
            dispatchOne(mail);
        }
    }

    private void dispatchOne(ClaimedMail mail) {
        long started = System.nanoTime();
        MimeMessage message;

        try {
            message = messageFactory.create(mail);
        } catch (MessagingException | MailContentException ex) {
            // Lỗi chuẩn bị xảy ra trước SMTP.
            recordFailure(
                    mail,
                    new MailFailure(
                            FailureKind.PERMANENT,
                            FailureStage.MIME,
                            "MAIL_PREPARATION_FAILED",
                            "Cannot build outgoing MIME message",
                            null),
                    elapsedMillis(started));
            return;
        }

        try {
            mailSender.send(message);
        } catch (MailException ex) {
            recordFailure(
                    mail, classifier.classify(ex),
                    elapsedMillis(started));
            return;
        }

        // SMTP send đã trả về thành công.
        // Lỗi database ở đây KHÔNG được xử lý như SMTP failure.
        boolean recorded = resultService.recordAccepted(
                mail, elapsedMillis(started));
        if (!recorded) {
            reportStateConflict(
                    mail.outboxId(), "SMTP_ACCEPTED");
        }
    }

    private void recordFailure(
            ClaimedMail mail, MailFailure failure, long durationMs) {
        RetryDecision decision = retryPolicy.decide(
                mail.attemptNumber(),
                failure,
                Instant.now(),
                null);

        boolean recorded = resultService.recordFailure(
                mail, failure, decision, durationMs);
        if (!recorded) {
            reportStateConflict(
                    mail.outboxId(), "FAILURE");
        }
    }

    private static long elapsedMillis(long startNanos) {
        return java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNanos);
    }

    private void reportStateConflict(
            java.util.UUID outboxId, String stage) {
        // Ghi event/metric/alert có kiểm soát dữ liệu cá nhân.
    }
}
~~~

Đoạn code là **skeleton minh họa**; các interface `MailMessageFactory`, `MailContentException`, `MailOutboxRepository` và cách xử lý `UNKNOWN` cần được triển khai theo ứng dụng. Mục tiêu là minh họa ba ranh giới:

- Lỗi dựng MIME xảy ra **trước** SMTP.
- `MailException` ở `send` được phân loại theo transport/provider.
- Lỗi `recordAccepted` hoặc `recordFailure` là lỗi **ghi state**, không phải bằng chứng SMTP chưa nhận thư.

Trong production, lỗi bất ngờ của renderer/serialization cũng cần được bắt ở ranh giới worker để bản ghi không kẹt vô hạn. Có thể ghi `FAILED` khi biết chắc chưa gọi SMTP; nếu lỗi xảy ra sau khi có side effect không rõ, cần `UNKNOWN` hoặc đối soát. Không dùng một `catch (Exception)` duy nhất để tự động retry mọi tình huống.

### 12.5. @Transactional và self-invocation

Trong Spring, transaction thường áp dụng qua proxy. Nếu một method của cùng class tự gọi method `@Transactional` của chính nó, lời gọi nội bộ có thể không được intercept. Hãy tách `OutboxClaimService` và `OutboxResultService` thành các bean khác nhau hoặc dùng `TransactionTemplate` khi cần transaction tường minh.

Đừng gọi repository update từng phần bên ngoài một transaction chung nếu yêu cầu là cập nhật outbox và attempt history **nguyên tử**.

## 13. Xử lý crash và kết quả SMTP không xác định

Lưu số lần thử và nguyên nhân thất bại giúp điều tra sau restart, nhưng không thể biến SMTP và database thành một transaction duy nhất.

### 13.1. Crash sau claim, trước SMTP

~~~text
T1: Claim row, attempt_count = 2
T2: Insert attempt #2 STARTED, commit
T3: JVM crashes before JavaMailSender.send
T4: Lease expires
T5: Another worker reclaims and starts attempt #3
~~~

Attempt #2 có thể được đánh dấu `ABANDONED`. Nhưng nếu worker chết đúng vào khoảng thời gian giữa lúc bắt đầu gọi send và lúc ghi một flag riêng, chỉ từ trạng thái database chưa thể chắc chắn SMTP đã nhận message hay chưa. Vì vậy hãy ghi lại chính xác **điều ứng dụng quan sát được**, không suy đoán kết quả bên ngoài.

### 13.2. Crash sau SMTP accepted, trước khi ghi SENT

~~~text
T1: Claim row, attempt #2 STARTED
T2: SMTP accepts message
T3: JVM crashes
T4: Outbox still PROCESSING, attempt #2 still STARTED
T5: Lease expires
T6: Another worker retries -> possible duplicate
~~~

Đây là cửa sổ quan trọng của mô hình **at-least-once**. Nếu không retry, email có thể mất khi SMTP thực ra chưa chấp nhận. Nếu retry, người nhận có thể nhận hai email. Không có cách nào bảo đảm exactly-once với SMTP thuần chỉ bằng `attempt_count` hoặc `Message-ID`.

Nếu nhà cung cấp có API hỗ trợ idempotency key, có thể dùng cùng `delivery_key` qua các lần retry theo phạm vi và thời hạn họ hỗ trợ. Nhưng **không được giả định SMTP server tự deduplicate theo `Message-ID`**.

### 13.3. Crash trong lúc ghi kết quả

Nếu transaction ghi outbox và attempt rollback, dữ liệu không ghi được `SENT`/`FAILED` dù worker đã quan sát thấy kết quả. Lần xử lý kế tiếp có thể thấy attempt cũ vẫn `STARTED`.

Nếu lỗi ghi state xảy ra **sau SMTP đã thành công**, log/alert cần ghi riêng:

~~~text
deliveryId = ...
claimToken = ...
attempt = 2
smtpResult = ACCEPTED
stateWriteResult = FAILED
action = RECONCILIATION_REQUIRED
~~~

Đừng gọi `mailSender.send` lại ngay trong catch của exception database. Quyết định retry sau đó phải xét nguy cơ duplicate và policy của loại email.

### 13.4. Xử lý attempt bị treo khi lease hết hạn

Một background reconciler có thể tìm:

~~~sql
SELECT id, attempt_count, claim_token, lease_until
FROM mail_outbox
WHERE status = 'PROCESSING'
  AND lease_until < now();
~~~

Với mỗi bản ghi:

- Nếu `attempt_count < max_attempts` và policy cho phép at-least-once, worker có thể reclaim atomically.
- Nếu attempt cuối đã dùng hết số lượt, cần chuyển hàng sang `FAILED` hoặc `UNKNOWN` theo bằng chứng sẵn có.
- Nếu có bằng chứng provider đã nhận message (ví dụ provider API report), có thể đối soát trước khi quyết định retry.
- Không cho phép worker cũ ghi đè quyết định của worker mới: luôn dùng `claim_token`/version.

Một bản ghi `PROCESSING` có lease hết hạn không nhất thiết là lỗi SMTP; nó có thể là crash, thread bị kẹt, lease quá ngắn hoặc sự cố database. `failure_stage` nên phản ánh nguyên nhân quan sát được, ví dụ `WORKER_LEASE_EXPIRED` là **một sự kiện vận hành**, không phải SMTP response.

## 14. Idempotency khi tạo yêu cầu và khi dispatch

Retry và idempotency có hai ranh giới riêng:

**1. Khi ghi outbox:** tránh tạo nhiều record cho cùng một thông báo nghiệp vụ. Dùng unique `delivery_key` đã được định nghĩa đúng phạm vi.

~~~sql
INSERT INTO mail_outbox (
    id, delivery_key, recipient,
    template_name, payload, status
)
VALUES (
    :id, :delivery_key, :recipient,
    :template_name, :payload, 'PENDING'
)
ON CONFLICT (delivery_key) DO NOTHING;
~~~

**2. Khi gửi ra provider:** nếu provider hỗ trợ idempotency key, sử dụng khóa ổn định để hạn chế duplicate khi client retry; nếu chỉ có SMTP, phải chấp nhận và kiểm soát duplicate window.

Không đổi `delivery_key` mỗi lần retry, vì lúc đó cùng một thông báo có thể biến thành nhiều delivery độc lập. Ngược lại, **`claim_token` phải đổi theo từng attempt** để fencing stale worker.

| Định danh | Cố định qua retry? | Mục đích |
| --- | --- | --- |
| `outbox.id` | Có | Định danh delivery |
| `delivery_key` | Có | Deduplicate yêu cầu nghiệp vụ |
| `attempt_no` | Không, tăng dần | Thứ tự các lần dispatch |
| `mail_delivery_attempt.id` | Không | Định danh một attempt |
| `claim_token` | Không | Quyền cập nhật của worker đang xử lý |
| `Message-ID` | Tùy cách tạo; không phải dedup guarantee | Correlation trong hệ thống mail |

### 14.1. Một record cho mỗi người nhận

Nếu gửi cùng nội dung cho nhiều người và cần biết ai thất bại, thường nên lưu một outbox/delivery record riêng cho từng recipient:

~~~text
event order-confirmed-123
  |
  +--> outbox A -> customer@example.net
  |
  +--> outbox B -> accounting@example.net
~~~

Mỗi bản ghi có attempt count, error code và trạng thái riêng. Nếu A được SMTP nhận còn B bị từ chối, chỉ B cần xử lý. Nếu gửi nhiều recipient trong một `MimeMessage`, có thể xảy ra partial acceptance; việc gom tất cả vào một trạng thái `SENT/FAILED` sẽ thiếu chính xác.

### 14.2. Redrive không phá idempotency

Nếu operator quyết định phát lại một email đã `FAILED`, có hai chính sách:

- **Redrive cùng record:** giữ `outbox.id`, ghi event redrive và đặt một retry window mới; phải định nghĩa cách xử lý `max_attempts` và lịch sử cũ.
- **Tạo delivery mới:** dùng ID/key mới có lý do audit rõ ràng; phù hợp nếu đây thực chất là một yêu cầu gửi lại hợp lệ.

Không tự xóa attempt history hoặc reset `attempt_count = 0` mà không lưu dấu vết. Nếu muốn “chu kỳ retry mới”, nên có `retry_cycle` riêng hoặc audit event cho lần redrive.

## 15. Bảo mật và quản lý dữ liệu lỗi

Thông tin lỗi hữu ích cho vận hành nhưng cũng có thể chứa dữ liệu nhạy cảm:

- Địa chỉ email, tên người nhận, nội dung subject.
- Nội dung email, dữ liệu hóa đơn, báo cáo.
- URL chứa token xác minh hoặc reset password.
- Tên host nội bộ và thông tin kết nối.
- Credential nếu thư viện/proxy vô tình đưa vào exception message.

Quy tắc thực tế:

1. Lưu **mã lỗi đã chuẩn hóa** và mô tả ngắn do ứng dụng kiểm soát thay cho raw exception message.
2. Giới hạn độ dài từng cột (`safe_error_summary` không cần hàng chục KB).
3. Phân quyền đọc bảng outbox/attempt vì nó có recipient và payload.
4. Định nghĩa thời hạn lưu history theo nhu cầu audit và quy định bảo mật.
5. Nếu ghi stack trace, dùng hệ thống log có masking, retention và quyền truy cập phù hợp.
6. Tránh dùng `recipient`, `delivery_key` chứa PII hoặc `outbox.id` làm metric label.
7. Khi chuyển dữ liệu cho dashboard hoặc support, chỉ hiển thị nội dung tối thiểu cần để điều tra.

### 15.1. Không lưu toàn bộ Throwable vào JSON

Không nên serialize trực tiếp:

~~~java
objectMapper.writeValueAsString(exception);
~~~

Object graph của exception có thể chứa nested cause, các trường provider-specific, stack trace rất dài hoặc dữ liệu không phù hợp để public. Thay vào đó:

~~~json
{
  "errorCode": "SMTP_AUTH_FAILED",
  "failureKind": "PERMANENT",
  "failureStage": "SMTP_AUTH",
  "safeSummary": "SMTP authentication was rejected",
  "smtpReplyCode": null
}
~~~

Đối với báo cáo lỗi theo attempt, thêm timestamp và attempt number ở các cột riêng để có thể lọc/sắp xếp bằng SQL.

## 16. Quan sát, dashboard và cảnh báo

Chỉ có `last_error_code` không đủ để biết hệ thống đang suy giảm hay một email đơn lẻ thất bại. Nên có metric ở cả mức hàng đợi và mức attempt.

| Metric | Ý nghĩa |
| --- | --- |
| `mail_outbox_pending_count` | Số delivery chờ dispatch |
| `mail_outbox_retry_count` | Số delivery đang chờ retry |
| `mail_outbox_failed_count` | Số delivery đã dừng retry |
| `mail_outbox_unknown_count` | Số delivery cần đối soát |
| `mail_outbox_oldest_due_age_seconds` | Thời gian chờ của hàng đến hạn lâu nhất |
| `mail_attempt_started_total` | Số attempt đã bắt đầu |
| `mail_attempt_smtp_accepted_total` | Số attempt được transport chấp nhận |
| `mail_attempt_failure_total` | Số attempt lỗi theo code/kind/stage |
| `mail_attempt_duration_seconds` | Thời gian một lượt xử lý |
| `mail_outbox_lease_reclaimed_total` | Số lease hết hạn và được claim lại |
| `mail_outbox_state_conflict_total` | Số cập nhật không khớp claim token/version |
| `mail_outbox_retry_exhausted_total` | Số hàng chạm max attempts |

Các chỉ số nên được phân nhóm theo `template_name`, provider, nhóm lỗi hoặc môi trường. Tránh đặt ID người nhận, outbox UUID hoặc nội dung lỗi tự do vào label vì có cardinality lớn và nguy cơ rò rỉ.

### 16.1. Ví dụ truy vấn các lỗi phổ biến

Với attempt history:

~~~sql
SELECT error_code, COUNT(*) AS failures
FROM mail_delivery_attempt
WHERE outcome IN (
    'RETRYABLE_FAILURE', 'PERMANENT_FAILURE', 'UNKNOWN'
)
  AND started_at >= now() - INTERVAL '24 hours'
GROUP BY error_code
ORDER BY failures DESC;
~~~

Để xem các delivery retry nhiều:

~~~sql
SELECT id, template_name, attempt_count,
       last_error_code, next_attempt_at
FROM mail_outbox
WHERE status IN ('RETRY', 'FAILED', 'UNKNOWN')
ORDER BY attempt_count DESC, updated_at DESC
LIMIT 100;
~~~

Query phục vụ giám sát phải được cấp quyền phù hợp và tránh xuất recipient/payload nếu không cần thiết.

### 16.2. Cảnh báo nên hướng tới hành động

Ví dụ:

- `SMTP_AUTH_FAILED` tăng đột ngột: kiểm tra credential và policy provider trước khi redrive.
- `SMTP_CONNECTION_TIMEOUT` tăng: kiểm tra mạng, DNS, SMTP timeout và giới hạn kết nối.
- Nhiều `UNKNOWN`: kiểm tra connectivity và cơ chế provider reconciliation, tránh retry mù.
- `STATE_CONFLICT` tăng: kiểm tra lease duration, clock/timeout, worker concurrency và claim token.
- `PENDING` lâu hơn SLA: kiểm tra worker/scheduler, backlog và capacity.

Một dashboard hữu ích nên phân biệt **attempt failure rate** với **delivery failure rate**. Ví dụ một email thất bại ba lần rồi thành công tạo ba attempt lỗi nhưng không còn là delivery thất bại ở trạng thái cuối.

## 17. Kiểm thử cách ghi số lần thử và nguyên nhân thất bại

Một hệ thống retry thường không hỏng ở câu lệnh `mailSender.send` đơn lẻ; lỗi nằm ở các ranh giới **claim, SMTP, lưu kết quả và crash**. Bộ test nên bao phủ tất cả.

### 17.1. Test tăng counter khi claim

Cho một outbox row:

~~~text
id = A
status = PENDING
attempt_count = 0
max_attempts = 5
~~~

Sau lần claim đầu:

~~~text
outbox.status = PROCESSING
outbox.attempt_count = 1
outbox.claim_token = T1

attempt #1:
    claim_token = T1
    outcome = STARTED
~~~

Nếu cùng lúc một worker khác cố claim hàng A, chỉ một worker được nhận nó. Test nên dùng **database thật hoặc Testcontainers** cho locking semantics; mock repository không chứng minh được `FOR UPDATE SKIP LOCKED` hoặc concurrent update an toàn.

### 17.2. Test lỗi tạm thời và lịch retry

Kịch bản:

1. Worker claim attempt #1.
2. SMTP ném lỗi đã được phân loại `TRANSIENT`.
3. Worker ghi outbox `RETRY` với `next_attempt_at` trong tương lai.
4. Attempt #1 được ghi `RETRYABLE_FAILURE`, có error code/stage/timestamp.
5. Worker không claim hàng đó trước thời điểm đến hạn.
6. Khi đến hạn, attempt #2 bắt đầu và counter tăng thành 2.

Nếu policy có jitter, không assert một timestamp cố định; kiểm tra delay nằm trong khoảng cho phép. Với logic thời gian, nên inject `Clock` để test không phụ thuộc `Instant.now()` của máy.

### 17.3. Test lỗi vĩnh viễn

Ví dụ lỗi template không tồn tại hoặc recipient sai:

- `attempt_count` đã tăng khi claim.
- Attempt row có `PERMANENT_FAILURE` và mã lỗi rõ ràng.
- Outbox chuyển `FAILED`, không có `next_attempt_at` mới cho retry tự động.
- Không gửi lại ở vòng poll tiếp theo.
- Error summary không chứa nguyên payload hoặc token.

### 17.4. Test hết max attempts

Với `max_attempts = 3`:

| Attempt | Lỗi | Quyết định |
| --- | --- | --- |
| 1 | SMTP tạm thời không khả dụng | RETRY |
| 2 | SMTP tạm thời không khả dụng | RETRY |
| 3 | SMTP tạm thời không khả dụng | FAILED: MAX_ATTEMPTS_EXHAUSTED |

Lịch sử phải giữ đủ ba nguyên nhân lỗi (có thể giống nhau), trong khi trạng thái cuối của outbox là `FAILED`. Không tăng attempt thứ tư khi không có redrive hợp lệ.

### 17.5. Test lỗi ghi kết quả và race condition

Một test integration quan trọng:

~~~text
Worker A claims -> T1, attempt 1
Lease T1 expires
Worker B claims -> T2, attempt 2
Worker A tries recordFailure(T1)
Expected: update 0 rows; outbox remains owned by T2
~~~

Test này xác minh `claim_token` và version fencing thật sự có tác dụng. Với tình huống worker A **gửi SMTP thành công** rồi state update thất bại, hệ thống phải tạo cảnh báo duplicate risk; không tự gọi `mailSender.send` thêm lần nữa ngay.

### 17.6. Test crash window

| Điểm dừng | Trạng thái có thể còn lại | Hành vi mong đợi |
| --- | --- | --- |
| Trước transaction claim commit | PENDING/RETRY như cũ | Có thể claim lại |
| Sau claim commit, trước SMTP | PROCESSING + attempt STARTED | Lease hết hạn, xử lý reclaim |
| SMTP accepted, trước state commit | PROCESSING + attempt STARTED | Ghi nhận duplicate window |
| Lỗi SMTP rõ ràng, trước recordFailure commit | PROCESSING + attempt STARTED | Hết lease, phân loại lại theo policy |
| Sau recordFailure commit | RETRY/FAILED + attempt hoàn tất | Scheduler tuân thủ trạng thái mới |
| Sau recordAccepted commit | SENT + attempt SMTP_ACCEPTED | Không dispatch lại |

Không thể chứng minh exactly-once email bằng một unit test. Test chỉ xác nhận ứng dụng xử lý các trạng thái đã biết và bảo vệ database khi có concurrency.

### 17.7. Ví dụ unit test chính sách retry

~~~java
@Test
void thirdAttemptStopsWhenMaxAttemptsIsThree() {
    MailRetryPolicy policy = new MailRetryPolicy(
            3,
            Duration.ofSeconds(30),
            Duration.ofMinutes(10));

    MailFailure failure = new MailFailure(
            FailureKind.TRANSIENT,
            FailureStage.SMTP_CONNECT,
            "SMTP_CONNECTION_TIMEOUT",
            "SMTP connection timed out",
            null);

    RetryDecision decision = policy.decide(
            3,
            failure,
            Instant.parse("2026-11-12T10:00:00Z"),
            null);

    assertEquals(NextAction.FAIL, decision.action());
    assertEquals(
            "MAX_ATTEMPTS_EXHAUSTED",
            decision.terminalReason());
}
~~~

Ví dụ dùng JUnit 5. Lớp policy trong phần trước là Java code minh họa; test dùng cùng hợp đồng của phương thức `decide`. Có thể bổ sung test `UNKNOWN`, `PERMANENT`, deadline và delay có giới hạn.

## 18. Ví dụ nhật ký một delivery qua nhiều lượt

Giả sử một hóa đơn cần gửi tới `customer@example.net`, `max_attempts = 4`. Trong bảng outbox, trạng thái thay đổi:

| Thời điểm | Trạng thái | Số lượt | Chi tiết |
| --- | --- | ---: | --- |
| 08:00 | `PENDING` | 0 | Transaction nghiệp vụ tạo outbox |
| 08:01 | `PROCESSING` | 1 | Worker claim T1 |
| 08:01 | `RETRY` | 1 | SMTP connection timeout; lịch retry 08:02 |
| 08:02 | `PROCESSING` | 2 | Worker claim T2 |
| 08:02 | `RETRY` | 2 | SMTP 421; lịch retry 08:04 |
| 08:04 | `PROCESSING` | 3 | Worker claim T3 |
| 08:04 | `SENT` | 3 | SMTP accepted; ghi `sent_at` |

Mốc thời gian chỉ là ví dụ. Lịch retry thực tế có thể có jitter, timeout và delay khác.

Lịch sử attempt sau đó:

| Attempt | Outcome | Kind | Error code |
| --- | --- | --- | --- |
| 1 | RETRYABLE_FAILURE | TRANSIENT | SMTP_CONNECTION_TIMEOUT |
| 2 | RETRYABLE_FAILURE | TRANSIENT | SMTP_SERVER_BUSY |
| 3 | SMTP_ACCEPTED | — | — |

Outbox hiện tại có `status = SENT`, `attempt_count = 3`. Không nên xóa history của attempt #1 và #2 chỉ vì attempt #3 đã thành công, nếu hệ thống cần thống kê hoặc audit.

Nếu attempt #3 kết thúc bằng timeout **sau khi DATA**, history có thể ghi `UNKNOWN` thay vì `RETRYABLE_FAILURE`. Quyết định có retry lần thứ tư không phụ thuộc vào ngoại lệ đơn thuần, mà phải xét chính sách duplicate/đối soát của ứng dụng.

## 19. Vận hành và redrive bản ghi thất bại

Một bản ghi `FAILED` cần đủ thông tin để operator hiểu chuyện gì xảy ra mà không cần đọc toàn bộ message body:

~~~text
Delivery ID:       8f...
Template:          invoice-ready
Status:            FAILED
Attempt count:     4 / 4
Last failure:      SMTP_AUTH_FAILED
Failure kind:      PERMANENT
Failure stage:     SMTP_AUTH
Last failed at:    2026-11-12T10:00:00Z
Terminal reason:   CONFIGURATION_REQUIRES_ACTION
~~~

Quy trình vận hành:

1. Xem error code và timeline attempts.
2. Xác định lỗi thuộc provider, dữ liệu, template, recipient hay state update.
3. Sửa nguyên nhân trước khi redrive, ví dụ cập nhật credential.
4. Xác nhận nội dung email còn giá trị; token/link có thể đã hết hạn.
5. Xác định gửi lại cùng delivery hay tạo một yêu cầu gửi mới.
6. Ghi audit lý do và người thực hiện.
7. Đặt lịch xử lý lại qua transaction có điều kiện, không sửa trực tiếp history cũ.

Không nên có nút “retry tất cả FAILED” không kiểm tra loại lỗi. Nếu vấn đề là địa chỉ recipient không hợp lệ, retry hàng nghìn lần không làm tăng tỷ lệ thành công.

### 19.1. Chính sách lưu trữ

Outbox và attempt history có thể tăng rất nhanh. Cần xác định:

- Giữ bản ghi `SENT` bao lâu để audit và deduplication?
- Các bản ghi `FAILED/UNKNOWN` cần lưu lâu hơn để đối soát không?
- Payload chứa dữ liệu cá nhân phải được xóa, ẩn danh hoặc mã hóa khi hết mục đích?
- Có thể archive attempt history sang storage rẻ hơn không?
- Unique delivery key phải còn hiệu lực bao lâu để ngăn event bị tạo trùng?

Không xóa bản ghi `SENT` quá sớm nếu ứng dụng dựa vào nó để ngăn tạo lại một email đã gửi khi nguồn event được replay. Nếu phải xóa theo chính sách bảo mật, cần thiết kế cơ chế deduplication có vòng đời tương ứng.

## 20. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `attempt_count` luôn bằng 0 dù email gửi thất bại | Chỉ tăng sau send thành công, hoặc exception làm rollback increment | Tăng trong transaction claim trước SMTP |
| Hai worker cùng gửi nhưng counter chỉ tăng 1 | Read-modify-write không nguyên tử | Claim nguyên tử, row lock/version |
| Bản ghi `PROCESSING` kẹt mãi | Không có lease hoặc không quét lease hết hạn | Lease, heartbeat/reclaim, reconciliation |
| `attempt_count` vượt max | Không kiểm tra trần tại claim | Áp dụng guard và xử lý terminal state |
| Error code bị thay đổi theo từng lần deploy | Dựa trực tiếp vào exception message | Dùng taxonomy mã lỗi ổn định |
| History trống nhưng counter tăng | Insert attempt không cùng transaction claim | Ghi atomically và rollback khi lệch |
| Outbox `SENT` nhưng history vẫn `STARTED` | Hai update không cùng transaction | Record result atomically |
| Email nhận trùng sau SMTP timeout | Server có thể đã nhận trước khi connection mất | UNKNOWN policy, provider idempotency khi có |
| Mọi lỗi đều retry | Không phân loại permanent/transient | Classifier có stage và response code |
| Last error bị xóa nên không biết các lần trước | Chỉ lưu snapshot gần nhất | Lưu bảng lịch sử attempt |
| Worker cũ ghi đè trạng thái mới | Không kiểm tra claim token/version | Conditional update/fencing |
| Lỗi database sau SMTP bị gọi là lỗi SMTP | Gộp send và state update trong cùng catch | Tách ranh giới transport/persistence |
| Dashboard chứa địa chỉ/token | Lưu raw exception hoặc metric label PII | Safe summary và kiểm soát truy cập |
| Retry vẫn gửi sau deadline | Policy không xét thời hạn nghiệp vụ | Kiểm tra businessDeadline trước khi schedule |

## 21. Câu hỏi thường gặp

**“Lưu `attempt_count` khi bắt đầu gửi hay sau khi gửi lỗi?”**  
Nếu quy ước là đếm lượt dispatch, nên tăng ngay trong transaction claim **trước** lời gọi SMTP. Điều này để lại dấu vết khi worker chết giữa chừng. Nếu cần đếm riêng số lượt SMTP call, dùng bộ đếm/sự kiện riêng với tên rõ nghĩa.

**“Số lần thử có bằng số lần gửi email thực tế không?”**  
Không nhất thiết. Một lượt claim có thể chết trước SMTP, hoặc timeout sau khi server đã nhận message. `attempt_count` là số lượt xử lý đã bắt đầu theo định nghĩa của ứng dụng, không phải bằng chứng provider đã nhận bao nhiêu thư.

**“Chỉ cần lưu last_error_message được không?”**  
Có thể đủ cho một hệ thống rất đơn giản, nhưng khó làm retry policy, thống kê và điều tra lịch sử. Nên có `error_code`, `failure_kind`, `failure_stage` và timestamp. Với hệ thống quan trọng, lưu attempt history.

**“Có nên lưu exception stack trace vào database?”**  
Thông thường không cần. Hãy lưu mã lỗi và safe summary ổn định; stack trace có thể ở hệ thống logging được bảo vệ. Không đưa raw exception chứa PII/token vào dashboard.

**“Một lỗi SMTP 421 có luôn retry được không?”**  
4xx thường là lỗi tạm thời, nhưng cần xem giai đoạn SMTP và chính sách provider. Retry vẫn phải có backoff, giới hạn số lượt và deadline.

**“Lỗi xác thực SMTP có nên ghi FAILED luôn không?”**  
Thường nên dừng retry tự động bằng cùng credential và cảnh báo operator. Sau khi sửa cấu hình, có thể redrive các delivery hợp lệ theo chính sách. Nguyên nhân `SMTP_AUTH_FAILED` cần được giữ để điều tra.

**“Vì sao cần `claim_token` nếu đã có `lease_owner`?”**  
Một worker có thể claim lại cùng row nhiều lần. Claim token riêng theo từng attempt giúp phân biệt lần giữ quyền cũ với lần mới, kể cả khi worker ID giống nhau.

**“Sau khi gửi thành công, có xóa last_error được không?”**  
Có thể xóa trên bản ghi tổng hợp `SENT`, nhưng nếu cần audit thì giữ lỗi các attempt trước trong bảng history. Không nên xóa lịch sử retry chỉ vì cuối cùng đã gửi thành công.

**“Khi hết max_attempts, có đổi nguyên nhân lỗi thành PERMANENT không?”**  
Không. Nếu lần cuối lỗi tạm thời, giữ `failure_kind = TRANSIENT` và lưu `terminal_reason = MAX_ATTEMPTS_EXHAUSTED` (hoặc sự kiện audit tương đương). Loại lỗi và lý do dừng retry là hai khái niệm khác nhau.

**“Một worker crash trước khi ghi recordFailure, làm sao biết lỗi?”**  
Không thể biết chính xác nguyên nhân nếu không có quan sát bền vững nào khác. Attempt `STARTED` không có `finished_at` là dấu vết; sau lease expiry, reconciler có thể ghi `ABANDONED/UNKNOWN` theo policy và tạo attempt mới nếu được phép.

**“Có thể bảo đảm exactly-once bằng transactional outbox không?”**  
Không với SMTP thuần. Outbox bảo đảm sự kiện được ghi cùng transaction nghiệp vụ, nhưng SMTP send và database state update không có commit chung. Hệ thống thường thực thi at-least-once, có duplicate window.

**“Có nên retry khi update SENT thất bại?”**  
Không retry SMTP ngay vì transport có thể đã nhận email. Nên cảnh báo state write failure, đối soát và chỉ dispatch lại theo chính sách có xét duplicate.

**“Có thể lưu chung nhiều người nhận trong một outbox row?”**  
Có thể nhưng partial failure khó theo dõi. Nếu cần retry, audit và status chính xác theo người nhận, một delivery row riêng cho mỗi recipient thường dễ quản lý hơn.

**“Có nên reset counter khi operator redrive không?”**  
Không nên âm thầm reset. Nếu bắt đầu một retry cycle mới, lưu thông tin cycle/audit để vẫn biết tổng số lượt dispatch trong lịch sử.

## 22. Checklist triển khai

Trước khi đưa worker gửi mail vào production, xác định rõ:

1. **Định nghĩa attempt:** đếm claim, lần gọi transport hay lần thất bại? Thống nhất tên cột và thời điểm tăng.
2. **Trạng thái:** PENDING/PROCESSING/RETRY/SENT/FAILED và có cần UNKNOWN hay không?
3. **Concurrency:** claim nguyên tử, lease, claim token và kiểm tra số hàng được cập nhật.
4. **Transaction:** tăng counter + insert attempt nguyên tử; gửi SMTP ngoài transaction database; ghi kết quả + attempt history nguyên tử.
5. **Lỗi:** lưu error code, kind, stage, timestamp, safe summary và SMTP reply code nếu có.
6. **Retry:** policy riêng theo loại mail, exponential backoff, jitter, max attempts và deadline.
7. **Idempotency:** unique delivery key ở đầu vào; không nhầm với claim token hoặc Message-ID.
8. **Crash:** xử lý lease hết hạn, attempt STARTED bị treo, lỗi ghi state và duplicate window.
9. **Bảo mật:** không ghi token, credential, full email body hoặc raw exception message vào history/log không được bảo vệ.
10. **Giám sát:** theo dõi backlog, retry/failed/unknown, tuổi hàng chờ, lease reclaim và state conflict.
11. **Vận hành:** có quy trình redrive, audit và retention.
12. **Kiểm thử:** success, transient, permanent, max attempts, crash, concurrency và state update conflict.

### Luồng tổng quát

~~~text
Transaction nghiệp vụ
    |-- ghi dữ liệu domain
    +-- insert outbox (PENDING, attempt_count=0)
                  |
                COMMIT
                  |
                  v
Worker claim nguyên tử
    |-- PROCESSING + lease + claim_token
    |-- attempt_count = attempt_count + 1
    +-- INSERT attempt STARTED
                  |
                COMMIT
                  |
                  v
             Gửi qua SMTP
                  |
         +--------+---------+
         |        |         |
      Accepted  Failure   Unknown
         |        |         |
         v        v         v
        SENT    RETRY/     UNKNOWN /
                FAILED   reconciliation
         |        |         |
         +--------+---------+
                  |
                  v
Transaction ghi outbox + attempt outcome
    |-- so khớp claim_token/owner
    |-- cập nhật trạng thái
    |-- ghi error code/attempt history
    +-- COMMIT
~~~

## Kết luận

Trong Spring Framework Mail, **lưu số lần thử** không chỉ là tăng một biến số nguyên sau khi bắt exception. Mỗi attempt cần có định nghĩa, quyền sở hữu, thời gian bắt đầu và kết quả tương ứng. **Lưu nguyên nhân thất bại** cũng không nên chỉ là sao chép chuỗi exception, mà cần thông tin có cấu trúc để phân loại, quyết định retry, giám sát và đối soát.

Kết hợp `attempt_count`, lịch sử từng lượt, `failure_kind`/`error_code`, lịch `next_attempt_at`, claim token và transaction ngắn giúp ứng dụng có thể phục hồi sau lỗi mà không mất dấu vết vận hành. Đồng thời, cần thừa nhận giới hạn at-least-once của SMTP: một lỗi hoặc crash sau khi thư được server chấp nhận vẫn có thể tạo trùng khi retry. Thiết kế tốt là thiết kế **ghi lại điều đã quan sát được**, cho phép người vận hành quyết định đúng và không đánh đồng “thử gửi”, “SMTP chấp nhận” với “người nhận đã nhận thư”.
