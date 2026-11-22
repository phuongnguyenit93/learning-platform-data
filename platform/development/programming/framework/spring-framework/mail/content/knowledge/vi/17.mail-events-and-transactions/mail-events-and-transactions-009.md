# Cập nhật trạng thái outbox sau khi gửi

## 1. Vì sao phải cập nhật trạng thái outbox?

Trong một ứng dụng Spring Framework Mail, email thường được gửi sau khi một nghiệp vụ hoàn tất: đơn hàng được xác nhận, thanh toán thành công, tài khoản được tạo hoặc hóa đơn được phát hành. Nếu ứng dụng gửi email trực tiếp ngay giữa transaction nghiệp vụ, có thể xảy ra tình huống database rollback nhưng email đã được gửi, hoặc database đã commit nhưng ứng dụng dừng trước khi gửi email.

**Transactional outbox** giải quyết phần lớn vấn đề phối hợp giữa database và việc phát sự kiện bằng cách ghi sự kiện cần xử lý vào một bảng outbox ngay trong transaction nghiệp vụ. Một worker đọc các bản ghi đó và thực hiện hành động bên ngoài, chẳng hạn gửi email qua `JavaMailSender`.

Tuy nhiên, ghi outbox mới chỉ là bước đầu. Worker cần cập nhật trạng thái của từng bản ghi theo kết quả gửi để hệ thống biết:

- Email đang chờ gửi hay đã được worker nhận xử lý?
- SMTP đã chấp nhận message hay thao tác gửi gặp lỗi?
- Bản ghi cần retry vào lúc nào?
- Có lỗi vĩnh viễn cần chuyển sang trạng thái cuối cùng hay không?
- Một worker khác có đang xử lý cùng bản ghi không?

Nếu không cập nhật trạng thái có kiểm soát, cùng một email có thể bị gửi lặp nhiều lần, bị bỏ sót hoặc bị kẹt mãi ở trạng thái đang xử lý.

Luồng khái quát:

~~~text
Business transaction
        |
        +--> Update business data
        |
        +--> Insert outbox record (PENDING)
        |
        v
      COMMIT
        |
        v
   Outbox worker claims row
        |
        v
   Build/render email
        |
        v
   JavaMailSender.send(...)
        |
        +--> SMTP accepted --> mark SENT
        |
        +--> Send failed ----> RETRY or FAILED
~~~

**Điểm quan trọng:** Trạng thái outbox phản ánh tiến trình xử lý và kết quả quan sát được của worker. Nó không tự chứng minh email đã vào inbox hoặc người nhận đã đọc thư.

## 2. Mô hình trạng thái của một email outbox

Một state machine thường có các trạng thái sau:

| Trạng thái | Ý nghĩa | Có được worker lấy tiếp không? |
| --- | --- | --- |
| `PENDING` | Bản ghi mới, đang chờ xử lý lần đầu | Có |
| `PROCESSING` | Một worker đã claim và đang xử lý, có lease | Chỉ sau khi lease hết hạn và được claim lại |
| `RETRY` | Lần gửi trước thất bại theo chính sách retry; chờ đến thời điểm tiếp theo | Có khi `next_attempt_at` đến hạn |
| `SENT` | `JavaMailSender.send` đã trả về thành công; SMTP transport đã chấp nhận message | Không |
| `FAILED` | Đã hết số lần thử hoặc gặp lỗi được phân loại là không thể retry | Không tự động |
| `CANCELLED` (tùy chọn) | Nghiệp vụ hủy việc gửi trước khi dispatch | Không |

Các trạng thái có thể rút gọn theo yêu cầu hệ thống. Điều quan trọng là định nghĩa rõ **điều kiện chuyển trạng thái**, ai được phép chuyển và thời điểm nào worker có thể claim bản ghi.

### 2.1. Sơ đồ chuyển trạng thái

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING: worker claims
    RETRY --> PROCESSING: due time reached
    PROCESSING --> SENT: SMTP send returns successfully
    PROCESSING --> RETRY: retryable failure
    PROCESSING --> FAILED: permanent failure / max attempts
    PROCESSING --> PROCESSING: lease expires and another worker reclaims
    PENDING --> CANCELLED: business cancellation
    RETRY --> CANCELLED: business cancellation
~~~

Một số hệ thống dùng trạng thái `NEW` thay cho `PENDING`, `IN_PROGRESS` thay cho `PROCESSING` hoặc `DEAD` thay cho `FAILED`. Tên không quan trọng bằng ý nghĩa và quy tắc chuyển trạng thái nhất quán.

### 2.2. Khi nào đánh dấu SENT?

Chỉ đánh dấu `SENT` **sau khi** lời gọi gửi trả về thành công:

~~~java
mailSender.send(message);
outboxService.markSent(outboxId);
~~~

`JavaMailSender.send(...)` hoàn tất bình thường nghĩa là transport đã gửi message tới SMTP server và server đã chấp nhận thao tác theo giao thức. Điều đó không bảo đảm message cuối cùng được giao vào inbox, không bị bounce, không vào spam hoặc người nhận đã đọc.

Các sự kiện delivery/bounce nếu cần theo dõi phải được thu thập qua cơ chế riêng của mail provider, DSN hoặc webhook phù hợp. Trạng thái `SENT` của outbox chỉ nên mang nghĩa **đã nộp thành công cho transport**.

### 2.3. Không đánh dấu SENT trước khi gửi

Trình tự sau có thể làm mất email:

~~~java
outboxService.markSent(outboxId);
mailSender.send(message);
~~~

Nếu ứng dụng dừng sau khi cập nhật database nhưng trước khi gọi SMTP, bản ghi đã là `SENT` và worker sẽ không gửi lại. Người nhận không nhận được thư dù outbox báo thành công.

Do đó, thứ tự thông thường là **gửi trước, cập nhật SENT sau**. Cách này vẫn có một cửa sổ lỗi khác liên quan tới việc gửi thành công nhưng cập nhật database thất bại; phần sau sẽ giải thích giới hạn đó.

## 3. Thiết kế bảng outbox

Một bảng outbox email có thể chứa:

| Cột | Kiểu dữ liệu minh họa | Mục đích |
| --- | --- | --- |
| `id` | UUID / BIGINT | Định danh bản ghi |
| `event_key` | VARCHAR | Khóa nghiệp vụ hoặc idempotency key |
| `recipient` | VARCHAR | Địa chỉ nhận |
| `template_name` | VARCHAR | Loại template cần render |
| `template_version` | VARCHAR | Phiên bản template nếu cần tái tạo nội dung nhất quán |
| `payload` | JSON / TEXT | Snapshot dữ liệu cần cho email |
| `status` | VARCHAR | PENDING, PROCESSING, RETRY, SENT, FAILED |
| `attempt_count` | INTEGER | Số lần dispatch đã bắt đầu |
| `next_attempt_at` | TIMESTAMP | Thời điểm sớm nhất được retry |
| `lease_owner` | VARCHAR | Worker đang giữ quyền xử lý |
| `lease_until` | TIMESTAMP | Thời điểm lease hết hạn |
| `sent_at` | TIMESTAMP | Thời điểm SMTP chấp nhận gửi |
| `last_error_code` | VARCHAR | Mã/loại lỗi đã chuẩn hóa |
| `last_error_message` | TEXT | Thông tin lỗi đã loại bỏ dữ liệu nhạy cảm |
| `created_at`, `updated_at` | TIMESTAMP | Thời điểm tạo và cập nhật |
| `version` | BIGINT | Version để optimistic locking nếu dùng |

Không phải hệ thống nào cũng cần toàn bộ cột. Với worker chạy song song, `lease_owner` và `lease_until` hoặc một cơ chế claim tương đương giúp tránh hai worker cùng xử lý một hàng. `attempt_count` và `next_attempt_at` hỗ trợ retry có giới hạn.

### 3.1. Ví dụ DDL

Ví dụ SQL theo cú pháp PostgreSQL:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    event_key VARCHAR(160) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    template_name VARCHAR(160) NOT NULL,
    template_version VARCHAR(80),
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner VARCHAR(120),
    lease_until TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    last_error_code VARCHAR(120),
    last_error_message TEXT,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_mail_outbox_status CHECK (
        status IN (
            'PENDING', 'PROCESSING', 'RETRY',
            'SENT', 'FAILED', 'CANCELLED'
        )
    )
);

CREATE UNIQUE INDEX ux_mail_outbox_event_key
    ON mail_outbox(event_key);

CREATE INDEX ix_mail_outbox_due
    ON mail_outbox(status, next_attempt_at, created_at);

CREATE INDEX ix_mail_outbox_lease
    ON mail_outbox(status, lease_until);
~~~

Đây là schema tham khảo. Unique constraint trên `event_key` chỉ phù hợp nếu nghiệp vụ bảo đảm một event key tương ứng đúng một email. Nếu một sự kiện gửi tới nhiều người nhận, hãy dùng khóa duy nhất có thêm recipient/delivery identity, hoặc tạo một outbox record riêng cho mỗi lần giao email.

`payload` nên chứa snapshot đủ để render email theo yêu cầu nghiệp vụ. Nếu payload có thông tin cá nhân, địa chỉ email hoặc token, cần có chính sách mã hóa, phân quyền đọc, thời hạn lưu trữ và xóa dữ liệu. Không lưu password hoặc bí mật không cần thiết trong outbox.

### 3.2. Tạo outbox trong cùng transaction nghiệp vụ

Ví dụ:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final MailOutboxRepository outboxRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            MailOutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public void confirmOrder(String orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        MailOutboxEntry entry = MailOutboxEntry.pending(
                UUID.randomUUID(),
                "order-confirmed:" + order.getPublicId(),
                order.getCustomerEmail(),
                "order-confirmation",
                createMailPayload(order));

        outboxRepository.save(entry);
    }
}
~~~

`createMailPayload` là hàm tạo snapshot chỉ chứa dữ liệu email cần thiết. Nếu transaction commit, cả cập nhật đơn hàng và bản ghi outbox cùng tồn tại. Nếu transaction rollback, cả hai cùng rollback.

Worker đọc outbox sau khi transaction commit. Điều này giúp tránh tình huống gửi email cho một thay đổi nghiệp vụ chưa được commit.

## 4. Claim bản ghi bằng lease trước khi gửi

Khi có nhiều worker hoặc nhiều instance ứng dụng, không thể chỉ làm:

~~~java
List<MailOutboxEntry> rows = repository.findByStatus("PENDING");
~~~

Hai worker có thể cùng đọc một hàng trước khi một trong hai cập nhật trạng thái. Cả hai đều nghĩ mình được quyền gửi và tạo duplicate.

Một giải pháp là **claim** bản ghi trong transaction database:

1. Chọn các hàng đến hạn và chưa được worker khác giữ lease.
2. Khóa/chọn chúng theo cơ chế an toàn với concurrency.
3. Chuyển trạng thái sang `PROCESSING`.
4. Ghi `lease_owner` và `lease_until`.
5. Commit transaction claim.
6. Chỉ sau commit mới thực hiện SMTP send.

Lease là quyền xử lý có thời hạn. Nếu worker chết, lease hết hạn và một worker khác có thể claim lại.

### 4.1. PostgreSQL: FOR UPDATE SKIP LOCKED

Một truy vấn claim theo batch có thể viết:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE
        (
            status IN ('PENDING', 'RETRY')
            AND next_attempt_at <= now()
        )
        OR
        (
            status = 'PROCESSING'
            AND lease_until < now()
        )
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS o
SET status = 'PROCESSING',
    lease_owner = :worker_id,
    lease_until = :lease_until,
    attempt_count = o.attempt_count + 1,
    updated_at = now(),
    version = o.version + 1
FROM picked
WHERE o.id = picked.id
RETURNING o.*;
~~~

Truy vấn trên dành cho PostgreSQL. `FOR UPDATE SKIP LOCKED` giúp các worker bỏ qua hàng đang bị transaction khác khóa thay vì chờ và claim trùng. `UPDATE ... RETURNING` trả về các hàng vừa được claim.

Điều kiện `PROCESSING` có lease hết hạn cho phép phục hồi hàng bị kẹt khi worker chết hoặc mất kết nối. Việc reclaim cần được giám sát vì worker cũ có thể vẫn còn chạy sau một pause dài; phần cập nhật kết quả phải kiểm tra `lease_owner` để worker cũ không ghi đè kết quả của worker mới.

Với database khác, cách viết claim có thể khác. Có thể dùng pessimistic lock, atomic update có điều kiện hoặc cơ chế queue phù hợp của hệ quản trị. Không sao chép SQL PostgreSQL vào mọi database mà chưa kiểm tra dialect.

### 4.2. Commit claim trước khi gọi SMTP

Transaction claim nên kết thúc trước khi gửi. Nếu giữ transaction database mở trong suốt thời gian SMTP, hệ thống có thể:

- Giữ row lock lâu khi server mail chậm.
- Tăng contention và thời gian chờ transaction.
- Giữ connection pool trong lúc chờ mạng.
- Làm rollback database dù SMTP đã nhận email.

Hãy tách thành hai giai đoạn:

~~~text
Transaction A: claim row -> PROCESSING -> COMMIT
                           |
                           v
                   SMTP send outside DB transaction
                           |
               +-----------+-----------+
               |                       |
               v                       v
Transaction B: mark SENT       Transaction B: mark RETRY/FAILED
               |                       |
               +-----------+-----------+
                           v
                         COMMIT
~~~

SMTP là một hệ thống bên ngoài database; transaction JDBC không thể rollback email đã được SMTP server chấp nhận.

## 5. Cập nhật SENT sau khi send thành công

Sau khi `JavaMailSender.send(message)` trả về bình thường, worker cập nhật outbox:

~~~sql
UPDATE mail_outbox
SET status = 'SENT',
    sent_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    last_error_code = NULL,
    last_error_message = NULL,
    updated_at = now(),
    version = version + 1
WHERE id = :id
  AND status = 'PROCESSING'
  AND lease_owner = :worker_id;
~~~

Điều kiện `status` và `lease_owner` bảo đảm worker chỉ cập nhật bản ghi mà nó đang giữ. Trong hệ thống dùng optimistic locking, có thể thêm `AND version = :claimed_version`. Nếu số hàng được cập nhật bằng 0, quyền xử lý có thể đã hết hạn hoặc hàng đã được worker khác claim.

### 5.1. Vì sao phải kiểm tra số hàng được cập nhật?

Không nên bỏ qua kết quả update:

~~~java
int updated = repository.markSent(id, workerId);
if (updated != 1) {
    // Ghi nhận trạng thái xung đột để vận hành xử lý.
}
~~~

Nếu update không khớp, worker không thể khẳng định database đã ghi `SENT`. Tuy nhiên, nếu SMTP send vừa thành công, **không được coi email là chưa gửi**. Đây là tình huống cần cảnh báo/đối soát vì lần xử lý khác có thể retry và tạo email trùng.

### 5.2. sent_at có ý nghĩa gì?

`sent_at` nên là thời điểm ứng dụng xác nhận lời gọi send thành công và cập nhật trạng thái. Nếu cần phân biệt thời điểm SMTP chấp nhận với thời điểm database ghi nhận, có thể lưu riêng `smtp_accepted_at` hoặc một timestamp quan sát từ worker.

Không gọi trường này là `delivered_at` nếu hệ thống không nhận được bằng chứng giao thư từ provider. Tên cột nên phản ánh đúng sự kiện mà ứng dụng thực sự quan sát được.

## 6. Cập nhật RETRY hoặc FAILED khi gửi thất bại

Nếu worker bắt được lỗi khi chuẩn bị hoặc gửi email, nó phải quyết định bản ghi có được thử lại hay không.

Một cách phân loại:

| Loại lỗi | Ví dụ | Hành động thường phù hợp |
| --- | --- | --- |
| Lỗi tạm thời | SMTP server tạm không truy cập được, connection timeout trước khi gửi dữ liệu, provider trả lỗi tạm thời | `RETRY` với backoff |
| Lỗi cấu hình/vĩnh viễn | Sai credential, sender bị từ chối theo policy, địa chỉ/định dạng message không hợp lệ | `FAILED` hoặc giữ trong hàng chờ vận hành sau khi sửa cấu hình |
| Lỗi dữ liệu/template | Thiếu biến bắt buộc, template không tồn tại, payload không hợp lệ | `FAILED` và điều tra dữ liệu/code |
| Kết quả không xác định | Kết nối mất sau khi message đã được gửi nhưng trước khi ứng dụng nhận phản hồi | Chính sách retry có thể tạo duplicate; cần ghi nhận rõ sự không chắc chắn |

Không phải mọi exception của Spring Mail đều có thể phân loại chỉ bằng tên class. Ví dụ `MailSendException` có thể bao bọc lỗi mạng tạm thời hoặc lỗi từ chối người nhận. Hãy xem cause và thông tin phản hồi SMTP mà provider cung cấp. Lỗi xác thực thường là lỗi cấu hình cần cảnh báo, không nên retry liên tục với tần suất cao.

### 6.1. Cập nhật trạng thái sau lỗi

Một truy vấn PostgreSQL minh họa:

~~~sql
UPDATE mail_outbox
SET status = CASE
        WHEN attempt_count >= :max_attempts THEN 'FAILED'
        ELSE 'RETRY'
    END,
    next_attempt_at = CASE
        WHEN attempt_count >= :max_attempts THEN next_attempt_at
        ELSE :next_attempt_at
    END,
    last_error_code = :error_code,
    last_error_message = :safe_error_message,
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = now(),
    version = version + 1
WHERE id = :id
  AND status = 'PROCESSING'
  AND lease_owner = :worker_id;
~~~

Khi còn lượt thử, hàng chuyển sang `RETRY` và `next_attempt_at` được đặt theo backoff. Khi đạt giới hạn, hàng chuyển `FAILED` để không tiếp tục retry tự động vô hạn.

Điều kiện `lease_owner` bảo vệ hàng khỏi worker cũ. Nếu update trả về 0 hàng, worker không còn quyền cập nhật bản ghi đó; hãy ghi nhận xung đột và đưa vào giám sát.

### 6.2. Exponential backoff và jitter

Retry ngay lập tức có thể tạo một đợt tải lớn khi SMTP provider đang gặp sự cố. Một chính sách thường dùng là exponential backoff:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Trong đó:

- `d_0` là thời gian chờ ban đầu.
- `n` là số lần dispatch đã bắt đầu.
- `d_max` là giới hạn thời gian chờ.

Thêm jitter ngẫu nhiên giúp nhiều worker không đồng loạt retry cùng một thời điểm:

\[
d_{\text{scheduled}} = d_n + U(0,j)
\]

Ví dụ cấu hình:

| Attempt | Delay cơ sở minh họa |
| --- | --- |
| 1 | 30 giây |
| 2 | 1 phút |
| 3 | 2 phút |
| 4 | 4 phút |
| 5 | 8 phút |
| Các lần sau | Tăng tới mức trần đã cấu hình |

Đây là ví dụ chính sách, không phải quy tắc cố định. Hệ thống cần chọn mức trần, jitter và số lần thử theo SLA, giới hạn provider và loại email. Email reset password có thể có deadline khác email hóa đơn.

### 6.3. Không retry lỗi vĩnh viễn theo vòng lặp nhanh

Ví dụ sai:

~~~java
while (true) {
    try {
        mailSender.send(message);
        break;
    } catch (MailException ex) {
        // Retry ngay lập tức.
    }
}
~~~

Vòng lặp này có thể tiêu thụ CPU, làm SMTP provider bị quá tải và giữ worker mãi ở một message. Hãy lưu lần thử vào database, đặt `next_attempt_at` và để scheduler/worker lấy lại sau.

### 6.4. Lưu thông tin lỗi có kiểm soát

Nên lưu:

- Loại exception hoặc error code đã chuẩn hóa.
- Mã phản hồi SMTP nếu có và được provider expose.
- Thời điểm thất bại và số lần thử.
- Thông tin ngắn đủ cho vận hành điều tra.

Không lưu raw email body, credential, access token hoặc toàn bộ exception có thể chứa địa chỉ/chi tiết nhạy cảm vào cột lỗi. Hãy sanitize và giới hạn độ dài `last_error_message`.

## 7. Cửa sổ lỗi giữa SMTP và database

Một điểm quan trọng của transactional outbox là database và SMTP không tham gia cùng một distributed transaction. Vì vậy không thể bảo đảm **exactly-once email delivery** chỉ bằng việc cập nhật trạng thái outbox.

### 7.1. Trường hợp A: gửi thành công, ứng dụng chết trước khi cập nhật SENT

Trình tự:

~~~text
Worker claims row -> PROCESSING
        |
        v
SMTP accepts email
        |
        v
Application process crashes
        |
        v
Database row still PROCESSING
        |
        v
Lease expires; another worker claims row
        |
        v
Email may be sent again
~~~

Email đầu tiên có thể đã được SMTP server chấp nhận, nhưng database chưa ghi nhận `SENT`. Khi lease hết hạn, worker khác có thể gửi lại. Đây là **duplicate window** của cách gửi at-least-once.

### 7.2. Trường hợp B: đánh dấu SENT trước, sau đó gửi thất bại

~~~text
Database row -> SENT
        |
        v
Application crashes before SMTP send
        |
        v
Worker will not pick row again
        |
        v
Email is lost
~~~

Đây là lý do không cập nhật `SENT` trước khi gọi SMTP.

### 7.3. Kết quả gửi không xác định do timeout

Có thể xảy ra trường hợp ứng dụng đã truyền phần lớn hoặc toàn bộ message tới SMTP server, nhưng mất kết nối trước khi nhận phản hồi cuối cùng. Worker không biết server đã chấp nhận message hay chưa.

Nếu retry, có nguy cơ gửi trùng. Nếu không retry, có nguy cơ email chưa được chấp nhận và bị mất. Không có một câu lệnh SQL nào giải quyết được sự không chắc chắn của một hệ thống bên ngoài đã nhận dữ liệu hay chưa.

Với email quan trọng, có thể bổ sung trạng thái `UNKNOWN` hoặc `NEEDS_RECONCILIATION` để đưa trường hợp mơ hồ vào hàng chờ đối soát thủ công/provider. Nếu hệ thống chấp nhận at-least-once và duplicate nhỏ có thể chấp nhận, worker có thể retry với cảnh báo rõ ràng.

### 7.4. Message-ID không phải idempotency guarantee

Có thể tạo một Message-ID ổn định cho cùng outbox event để hỗ trợ truy vết:

~~~java
message.setHeader("Message-ID", stableMessageId);
~~~

Tuy nhiên, **không được giả định mọi SMTP server hoặc mail client tự loại bỏ email trùng chỉ vì Message-ID giống nhau**. Message-ID hữu ích cho correlation và debugging, không phải cơ chế exactly-once phổ quát.

Nếu provider có API gửi email hỗ trợ idempotency key, hãy dùng một khóa ổn định theo delivery/event. Provider có thể bảo đảm không tạo hai lần gửi cho cùng khóa trong phạm vi và thời hạn mà họ công bố. Với SMTP thuần, ứng dụng thường phải chấp nhận mô hình at-least-once và thiết kế nội dung/email workflow để giảm tác hại của duplicate.

## 8. Tách transaction claim, send và update state trong Spring

Không nên giữ một transaction database mở trong lúc gọi mạng SMTP. Có thể chia thành ba thành phần:

- `OutboxClaimService`: claim batch trong transaction ngắn.
- `MailDispatchWorker`: xử lý từng bản ghi và gọi `JavaMailSender` ngoài transaction.
- `OutboxStateService`: cập nhật `SENT`, `RETRY` hoặc `FAILED` trong transaction mới.

### 8.1. Record đại diện cho bản ghi đã claim

~~~java
public record ClaimedMail(
        UUID id,
        String recipient,
        String templateName,
        String payloadJson,
        int attemptCount,
        long version,
        String leaseOwner) {
}
~~~

Worker nhận snapshot dữ liệu đã claim. Không cần giữ một entity JPA mutable và session persistence trong suốt thời gian gửi email.

### 8.2. Service claim có transaction riêng

~~~java
@Service
public class OutboxClaimService {

    private final MailOutboxRepository repository;
    private final String workerId;

    public OutboxClaimService(
            MailOutboxRepository repository,
            WorkerIdentity workerIdentity) {
        this.repository = repository;
        this.workerId = workerIdentity.id();
    }

    @Transactional
    public List<ClaimedMail> claimBatch(
            int batchSize,
            Instant leaseUntil) {

        return repository.claimDue(
                batchSize,
                workerId,
                leaseUntil);
    }
}
~~~

`repository.claimDue` cần thực hiện thao tác claim nguyên tử tương ứng với database đang dùng. Method trả về sau khi Spring commit transaction, do đó worker bên ngoài có thể gửi mà không giữ row lock của transaction claim.

### 8.3. Service cập nhật trạng thái

~~~java
@Service
public class OutboxStateService {

    private final MailOutboxRepository repository;

    public OutboxStateService(MailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public boolean markSent(ClaimedMail mail) {
        return repository.markSent(
                mail.id(),
                mail.leaseOwner(),
                mail.version()) == 1;
    }

    @Transactional
    public boolean markRetry(
            ClaimedMail mail,
            Instant nextAttemptAt,
            String errorCode,
            String safeErrorMessage) {

        return repository.markRetry(
                mail.id(),
                mail.leaseOwner(),
                mail.version(),
                nextAttemptAt,
                errorCode,
                safeErrorMessage) == 1;
    }

    @Transactional
    public boolean markFailed(
            ClaimedMail mail,
            String errorCode,
            String safeErrorMessage) {

        return repository.markFailed(
                mail.id(),
                mail.leaseOwner(),
                mail.version(),
                errorCode,
                safeErrorMessage) == 1;
    }
}
~~~

Các method repository phải update có điều kiện theo ID, status, owner và version để tránh worker cũ ghi đè kết quả mới. `boolean` trả về cho biết đúng một hàng đã được cập nhật.

### 8.4. Worker gửi email ngoài transaction

~~~java
@Service
public class MailDispatchWorker {

    private final OutboxClaimService claimService;
    private final OutboxStateService stateService;
    private final MailMessageFactory messageFactory;
    private final JavaMailSender mailSender;
    private final RetryPolicy retryPolicy;
    private final FailureClassifier failureClassifier;

    public MailDispatchWorker(
            OutboxClaimService claimService,
            OutboxStateService stateService,
            MailMessageFactory messageFactory,
            JavaMailSender mailSender,
            RetryPolicy retryPolicy,
            FailureClassifier failureClassifier) {
        this.claimService = claimService;
        this.stateService = stateService;
        this.messageFactory = messageFactory;
        this.mailSender = mailSender;
        this.retryPolicy = retryPolicy;
        this.failureClassifier = failureClassifier;
    }

    public void dispatchBatch(
            int batchSize,
            Duration leaseDuration) {

        Instant leaseUntil = Instant.now().plus(leaseDuration);
        List<ClaimedMail> batch =
                claimService.claimBatch(batchSize, leaseUntil);

        for (ClaimedMail mail : batch) {
            dispatchOne(mail);
        }
    }

    private void dispatchOne(ClaimedMail mail) {
        try {
            MimeMessage message = messageFactory.create(mail);
            mailSender.send(message);

            boolean updated = stateService.markSent(mail);
            if (!updated) {
                // SMTP có thể đã chấp nhận mail, nhưng worker mất lease.
                // Ghi metric/cảnh báo và đưa vào quy trình đối soát.
                reportStateConflict(mail.id(), "SENT");
            }
        } catch (MailException ex) {
            handleFailure(mail, ex);
        } catch (MailContentException ex) {
            stateService.markFailed(
                    mail,
                    "CONTENT_ERROR",
                    safeMessage(ex));
        }
    }

    private void handleFailure(ClaimedMail mail, MailException ex) {
        FailureDecision decision = failureClassifier.classify(ex);

        if (decision.retryable()
                && mail.attemptCount() < retryPolicy.maxAttempts()) {
            Instant nextAttempt = retryPolicy.nextAttemptAt(
                    mail.attemptCount());
            boolean updated = stateService.markRetry(
                    mail,
                    nextAttempt,
                    decision.code(),
                    safeMessage(ex));
            if (!updated) {
                reportStateConflict(mail.id(), "RETRY");
            }
        } else {
            boolean updated = stateService.markFailed(
                    mail,
                    decision.code(),
                    safeMessage(ex));
            if (!updated) {
                reportStateConflict(mail.id(), "FAILED");
            }
        }
    }

    private String safeMessage(Exception ex) {
        return ex.getClass().getSimpleName();
    }

    private void reportStateConflict(UUID id, String expectedState) {
        // Ghi log/metric/alert; không gửi lại ngay trong method này.
    }
}
~~~

Đây là skeleton minh họa, cần bổ sung import, triển khai repository, policy và factory theo ứng dụng. `MailContentException` là exception ứng dụng đại diện cho lỗi dữ liệu/template đã được phân loại. `FailureClassifier` quyết định loại lỗi dựa trên cause/provider response; không nên coi mọi `MailException` đều retryable.

Một chi tiết quan trọng: `dispatchBatch` không có `@Transactional`. `claimBatch` và các method cập nhật trạng thái là những lần gọi sang bean riêng có transaction riêng. Điều này tránh transaction claim bao trùm lời gọi SMTP.

### 8.5. Lưu ý về Spring transaction proxy

Trong Spring, `@Transactional` thường được áp dụng qua proxy. Nếu một method trong cùng class tự gọi một method khác có `@Transactional` (self-invocation), lời gọi nội bộ có thể không đi qua proxy nên annotation không được áp dụng như mong đợi.

Tách `OutboxClaimService` và `OutboxStateService` thành bean riêng giúp ranh giới transaction rõ ràng. Có thể dùng `TransactionTemplate` nếu cần điều khiển transaction tường minh.

## 9. Claim lease, timeout và worker chạy lâu

Lease cần dài hơn thời gian tối đa dự kiến cho thao tác gửi, nhưng không nên quá dài khiến bản ghi bị kẹt lâu khi worker chết.

Ví dụ:

| Thông số | Ý nghĩa |
| --- | --- |
| `mail.smtp.connectiontimeout` | Giới hạn thời gian mở kết nối SMTP |
| `mail.smtp.timeout` | Giới hạn thời gian chờ phản hồi đọc từ SMTP |
| `mail.smtp.writetimeout` | Giới hạn thời gian ghi dữ liệu tới SMTP |
| `lease_duration` | Thời gian worker giữ quyền xử lý một hàng |
| `max_attempts` | Giới hạn số lần dispatch |

Các timeout SMTP nên được cấu hình để worker không giữ lease vô thời hạn. Nếu xử lý có thể kéo dài hơn lease, worker cần **gia hạn lease (heartbeat)** trong transaction ngắn và kiểm tra kết quả gia hạn trước khi tiếp tục.

### 9.1. Gia hạn lease

Ví dụ update có điều kiện:

~~~sql
UPDATE mail_outbox
SET lease_until = :new_lease_until,
    updated_at = now(),
    version = version + 1
WHERE id = :id
  AND status = 'PROCESSING'
  AND lease_owner = :worker_id;
~~~

Nếu không cập nhật được hàng, worker đã mất lease. Không nên tiếp tục bắt đầu thêm side effect mới. Nếu SMTP send đang diễn ra thì không thể thu hồi bytes đã gửi; đây vẫn là lý do phải giới hạn timeout và chọn lease phù hợp.

### 9.2. Worker cũ không được ghi đè kết quả worker mới

Giả sử worker A claim hàng, bị pause quá lâu, lease hết hạn. Worker B claim lại và gửi. Sau đó worker A tỉnh dậy và cố cập nhật `SENT` hoặc `RETRY`.

Điều kiện `lease_owner` và `version` trong câu lệnh update giúp worker A không ghi đè trạng thái do worker B sở hữu. Có thể dùng một **fencing token** tăng đơn điệu (version/generation) để mọi thao tác state update phải mang token của lần claim hiện tại.

Fencing token bảo vệ database state. Nó không thể ngăn worker cũ tiếp tục một SMTP call đã bắt đầu; để giảm rủi ro đó, cần timeout, lease và thiết kế duplicate-tolerant.

## 10. Phân loại exception của Spring Mail

`JavaMailSender` ném các exception thuộc hệ thống `org.springframework.mail` khi chuẩn bị hoặc gửi message. Một số loại thường gặp:

| Exception | Điều có thể cho biết | Hướng xử lý |
| --- | --- | --- |
| `MailAuthenticationException` | Lỗi xác thực SMTP hoặc credential/policy | Thường cần sửa cấu hình và cảnh báo; tránh retry dồn dập |
| `MailSendException` | Transport không gửi được một hay nhiều message; có thể chứa chi tiết lỗi theo message | Phân tích cause và phản hồi provider để quyết định retry |
| `MailPreparationException` | Không chuẩn bị được message | Thường là lỗi dữ liệu/template/cấu hình, cần điều tra |
| `MailParseException` | Lỗi khi parse/chuẩn bị dữ liệu mail | Thường không giải quyết bằng retry ngay |
| `MailException` | Lớp cơ sở cho lỗi mail | Không đủ thông tin để kết luận retryable chỉ từ tên lớp |

Ví dụ phân loại ở mức khái niệm:

~~~java
public record FailureDecision(
        boolean retryable,
        String code) {
}

public class FailureClassifier {

    public FailureDecision classify(MailException exception) {
        if (exception instanceof MailAuthenticationException) {
            return new FailureDecision(false, "SMTP_AUTH");
        }

        if (exception instanceof MailPreparationException
                || exception instanceof MailParseException) {
            return new FailureDecision(false, "MAIL_PREPARATION");
        }

        if (exception instanceof MailSendException) {
            // Cần kiểm tra nested cause / SMTP response code.
            // Không mặc định mọi MailSendException đều tạm thời.
            return classifyTransportFailure(exception);
        }

        return classifyTransportFailure(exception);
    }

    private FailureDecision classifyTransportFailure(Throwable cause) {
        // Ví dụ: connection refused/timeout có thể retry.
        // Lỗi SMTP 4xx thường tạm thời; 5xx thường cần xử lý vĩnh viễn.
        // Việc xác định chính xác phụ thuộc provider và exception lồng nhau.
        return new FailureDecision(true, "SMTP_TRANSPORT");
    }
}
~~~

Phần `classifyTransportFailure` là placeholder để thể hiện nơi đặt policy; **không nên đưa nguyên logic trả về true cho mọi lỗi vào production**. Cần kiểm tra nested cause, SMTP response code và chi tiết từ provider. Lỗi timeout sau khi truyền message có thể có kết quả mơ hồ, vì vậy retryable không đồng nghĩa chắc chắn email chưa được chấp nhận.

### 10.1. SMTP response 4xx và 5xx

Ở mức giao thức, phản hồi SMTP 4xx thường chỉ ra lỗi tạm thời; 5xx thường chỉ ra lỗi không thể xử lý bằng retry y hệt. Nhưng ứng dụng phải hiểu phản hồi ở đúng giai đoạn:

- Lỗi tạm thời khi kết nối hoặc provider đang quá tải có thể retry sau backoff.
- Sender bị từ chối vì policy hoặc địa chỉ không hợp lệ thường cần sửa dữ liệu/cấu hình.
- Lỗi sau khi server đã nhận DATA nhưng phản hồi bị mất có thể không xác định được trạng thái cuối.

Không phải mọi implementation Jakarta Mail đều expose cùng loại exception hoặc response code. Nếu cần phân loại chi tiết, phải dựa trên provider/transport implementation đang dùng và kiểm thử nó trong môi trường tương ứng.

## 11. Một dispatcher có scheduler

Worker có thể được gọi định kỳ bằng Spring scheduling:

~~~java
@Component
public class MailOutboxScheduler {

    private final MailDispatchWorker worker;

    public MailOutboxScheduler(MailDispatchWorker worker) {
        this.worker = worker;
    }

    @Scheduled(fixedDelayString = "${mail.outbox.poll-delay:2000}")
    public void poll() {
        worker.dispatchBatch(
                20,
                Duration.ofMinutes(2));
    }
}
~~~

Ví dụ này giả định ứng dụng đã bật scheduling bằng `@EnableScheduling`, cấu hình worker và đặt timeout SMTP phù hợp. `fixedDelay` tính khoảng chờ sau khi lần gọi trước hoàn tất; nếu cần throughput cao hơn, có thể dùng worker pool hoặc queue riêng nhưng phải giữ cơ chế claim an toàn.

Chữ ký worker tương ứng:

~~~java
public void dispatchBatch(int batchSize, Duration leaseDuration) {
    Instant leaseUntil = Instant.now().plus(leaseDuration);
    List<ClaimedMail> batch =
            claimService.claimBatch(batchSize, leaseUntil);

    for (ClaimedMail mail : batch) {
        dispatchOne(mail);
    }
}
~~~

### 11.1. Giới hạn batch size

Không nên claim quá nhiều bản ghi nếu worker xử lý tuần tự và mỗi lần gửi có thể mất vài giây. Các hàng ở cuối batch có thể hết lease trước khi tới lượt gửi.

Chọn batch size dựa trên:

- Thời gian trung bình và p95/p99 của SMTP send.
- Số worker đồng thời.
- Lease duration và timeout.
- Giới hạn tốc độ của SMTP provider.
- Khả năng xử lý khi một worker dừng giữa batch.

Nếu batch dài, có thể claim theo từng nhóm nhỏ, tăng worker pool hoặc gia hạn lease cho các hàng đang xử lý. Không claim hàng trăm email rồi để chúng nằm trong memory trong khi lease vẫn tiếp tục đếm.

### 11.2. Không gửi đồng thời quá mức provider cho phép

Nhiều worker giúp tăng throughput, nhưng cần giới hạn số kết nối SMTP và tốc độ gửi. Có thể áp dụng:

- Thread pool có giới hạn.
- Rate limiter theo provider hoặc sender account.
- Batch size và polling interval.
- Backoff toàn cục khi provider trả nhiều lỗi tạm thời.
- Circuit breaker để ngừng gọi provider trong khoảng thời gian khi lỗi tăng cao.

Circuit breaker không thay thế trạng thái outbox. Khi circuit đang mở, các bản ghi vẫn phải ở `RETRY` hoặc chờ đến hạn, không được đánh dấu `SENT`.

## 12. Idempotency và chống tạo outbox record trùng

Transactional outbox bảo đảm bản ghi sự kiện được lưu cùng transaction nghiệp vụ, nhưng một request nghiệp vụ có thể được gửi lại do client retry hoặc do handler xử lý sự kiện lặp. Nếu mỗi lần đều insert một outbox row mới, worker sẽ gửi nhiều email giống nhau.

Một khóa nghiệp vụ ổn định có thể giúp deduplicate:

~~~text
event_key = "order-confirmed:" + publicOrderId
~~~

Đặt unique constraint trên khóa phù hợp với định nghĩa một lần gửi. Khi insert gặp conflict, application service cần xử lý theo chính sách: bỏ qua event đã tạo, hoặc xác nhận bản ghi cũ đã có.

Ví dụ SQL PostgreSQL:

~~~sql
INSERT INTO mail_outbox (
    id, event_key, recipient, template_name, payload, status
)
VALUES (
    :id, :event_key, :recipient, :template_name, :payload, 'PENDING'
)
ON CONFLICT (event_key) DO NOTHING;
~~~

Nếu cùng một order có thể gửi nhiều email hợp lệ (ví dụ xác nhận, cập nhật vận chuyển, hóa đơn), khóa phải chứa **loại sự kiện và phiên bản/lần phát sinh** chứ không chỉ order ID.

### 12.1. Deduplicate outbox không đồng nghĩa deduplicate SMTP

Unique key giúp tránh tạo hai hàng cho cùng một event. Nó không xử lý duplicate window sau khi SMTP đã chấp nhận email nhưng database chưa cập nhật `SENT`.

Đây là hai tầng khác nhau:

1. **Idempotency khi tạo outbox:** ngăn tạo nhiều delivery record cho cùng event.
2. **Idempotency khi dispatch:** ngăn provider thực hiện cùng một delivery nhiều lần nếu provider hỗ trợ khóa idempotency.

SMTP thuần không có một cơ chế idempotency key chuẩn được mọi server bắt buộc hỗ trợ. Vì thế không nên tuyên bố transactional outbox bảo đảm exactly-once email.

### 12.2. Một record cho mỗi recipient

Nếu gửi cho nhiều người nhận, nên cân nhắc tạo một delivery/outbox record riêng cho từng recipient. Điều này giúp:

- Theo dõi trạng thái riêng từng địa chỉ.
- Retry người nhận thất bại mà không gửi lại cho người đã nhận.
- Xử lý partial failure rõ hơn.
- Giới hạn dữ liệu cá nhân xuất hiện trong message gửi tới từng người.

Nếu truyền nhiều recipient trong một lần `send`, provider có thể chấp nhận một số địa chỉ nhưng từ chối số khác. `MailSendException` có thể cung cấp thông tin về các message thất bại, nhưng việc phân biệt delivery từng recipient phức tạp hơn. Một record một recipient thường dễ vận hành hơn cho email giao dịch.

## 13. Xử lý bản ghi FAILED và quy trình redrive

`FAILED` nên là trạng thái cuối của retry tự động, không có nghĩa dữ liệu bị xóa hoặc không thể xử lý nữa. Vận hành có thể cần:

- Xem error code, số lần thử và thời điểm thất bại.
- Sửa cấu hình SMTP hoặc dữ liệu template.
- Xác định bản ghi có được phép gửi lại không.
- Chuyển bản ghi về `RETRY` hoặc tạo một delivery mới theo audit policy.
- Ghi nhận ai đã redrive, lý do và thời điểm.

Không nên có một thao tác reset hàng loạt mọi `FAILED` về `PENDING` mà không xem nguyên nhân. Nếu recipient sai, việc retry sẽ tiếp tục thất bại; nếu lỗi credential, cần sửa credential trước.

Ví dụ thao tác redrive có kiểm soát:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY',
    next_attempt_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = now(),
    version = version + 1
WHERE id = :id
  AND status = 'FAILED';
~~~

Đây chỉ là câu lệnh trạng thái minh họa. Một thao tác vận hành thực tế cần kiểm tra nguyên nhân đã được xử lý, phân quyền người thực hiện và ghi audit record. Không sửa payload hoặc recipient tùy tiện để làm một bản ghi cũ gửi sang người khác.

### 13.1. Dead-letter queue hoặc trạng thái terminal

Với khối lượng lớn, có thể tách bản ghi lỗi cuối cùng sang bảng dead-letter hoặc giữ `FAILED` trong cùng bảng với metadata đầy đủ. Mục đích:

- Ngăn worker tự retry vô hạn.
- Giữ thông tin phục vụ điều tra.
- Theo dõi tỷ lệ lỗi theo template, provider và loại sự kiện.
- Cho phép redrive có kiểm soát.

Không xóa bản ghi outbox ngay khi gửi thành công nếu hệ thống cần audit hoặc chống event trùng. Có thể lưu trữ/partition dữ liệu cũ theo retention policy.

## 14. Các chỉ số vận hành cần theo dõi

Chỉ nhìn số lượng email đã gửi chưa đủ để biết outbox có đang hoạt động tốt. Nên theo dõi:

| Metric | Ý nghĩa |
| --- | --- |
| `outbox_pending_count` | Số bản ghi chờ xử lý |
| `outbox_processing_count` | Số bản ghi đang có lease |
| `outbox_retry_count` | Số bản ghi đang chờ retry |
| `outbox_failed_count` | Số bản ghi lỗi cuối |
| `outbox_oldest_pending_age` | Tuổi của bản ghi chờ lâu nhất |
| `outbox_send_success_total` | Tổng số lần gửi được transport chấp nhận |
| `outbox_send_failure_total` | Tổng số lần dispatch thất bại |
| `outbox_send_duration` | Thời gian gọi SMTP |
| `outbox_lease_expired_total` | Số lần lease hết hạn/reclaim |
| `outbox_state_conflict_total` | Số lần update không khớp owner/version |
| `outbox_retry_exhausted_total` | Số bản ghi hết số lần thử |

Cảnh báo có thể kích hoạt khi:

- Bản ghi `PENDING` lâu hơn SLA.
- Số lượng `PROCESSING` tăng bất thường hoặc lease liên tục hết hạn.
- Tỷ lệ SMTP failure vượt ngưỡng.
- `FAILED` tăng đột ngột theo template hoặc recipient domain.
- State update conflict xuất hiện sau các lần send thành công.

Metric label không nên chứa email người nhận, token hoặc ID cá nhân có cardinality cao. Dùng loại template, provider, error category và môi trường làm dimension phù hợp.

### 14.1. Log có correlation ID

Log nên mang `outboxId` hoặc event key đã được làm sạch để liên kết:

~~~text
outboxId=...
eventType=ORDER_CONFIRMED
template=order-confirmation
attempt=2
worker=mail-worker-3
result=RETRY
errorCode=SMTP_TEMPORARY
~~~

Không log toàn bộ payload, nội dung email, token xác minh, password hoặc SMTP credential. Correlation ID giúp truy vết một delivery mà không phải đưa thông tin nhạy cảm vào log.

## 15. Kiểm thử cập nhật trạng thái outbox

Kiểm thử nên bao phủ các chuyển trạng thái và các cửa sổ lỗi quan trọng, không chỉ test rằng repository đã được gọi.

### 15.1. Unit test worker: gửi thành công

Kịch bản:

1. Claim service trả về một hàng `PROCESSING`.
2. Message factory tạo message hợp lệ.
3. Mock `JavaMailSender.send` trả về bình thường.
4. State service được gọi để đánh dấu `SENT`.
5. Không có thao tác retry hoặc failed.

Ví dụ:

~~~java
@Test
void marksOutboxSentAfterSuccessfulMailSend() {
    ClaimedMail claimed = sampleClaimedMail();
    when(claimService.claimBatch(anyInt(), any()))
            .thenReturn(List.of(claimed));

    worker.dispatchBatch(10, Duration.ofMinutes(2));

    verify(mailSender).send(any(MimeMessage.class));
    verify(stateService).markSent(claimed);
    verify(stateService, never())
            .markRetry(any(), any(), anyString(), anyString());
}
~~~

Ví dụ giả định dùng JUnit/Mockito và worker có các dependency tương ứng. Có thể cần stub `messageFactory.create` và `markSent` theo implementation thực tế.

### 15.2. Unit test worker: lỗi tạm thời

Kịch bản:

1. `mailSender.send` ném một `MailException` được classifier xác định là retryable.
2. Worker tính `next_attempt_at`.
3. Worker gọi `markRetry`.
4. Không gọi `markSent`.

Kiểm tra thời điểm retry nằm sau hiện tại và tuân thủ backoff policy; không assert một timestamp tuyệt đối nếu policy có jitter.

### 15.3. Unit test worker: lỗi vĩnh viễn

Ví dụ lỗi dữ liệu/template hoặc credential đã được policy phân loại là terminal:

- Worker gọi `markFailed`.
- Không gọi `markRetry`.
- Error code được chuẩn hóa.
- Error message không chứa token hoặc nội dung email.

### 15.4. Repository integration test

Với database thật hoặc Testcontainers, nên xác nhận:

- `PENDING` đủ điều kiện được claim.
- `RETRY` chỉ được claim khi `next_attempt_at` đến hạn.
- `PROCESSING` có lease còn hiệu lực không bị claim lần nữa.
- `PROCESSING` hết lease có thể được reclaim.
- Hai transaction/worker đồng thời không claim cùng một hàng.
- Update `SENT` yêu cầu đúng lease owner/version.
- Worker cũ không thể ghi đè hàng đã được worker mới claim.
- Retry vượt max attempts chuyển sang `FAILED`.

SQL claim phụ thuộc database nên test trên cùng hệ quản trị production hoặc một phiên bản tương thích. H2 có thể không mô phỏng đầy đủ hành vi `SKIP LOCKED` hoặc concurrency của PostgreSQL.

### 15.5. Kiểm thử crash window

Có thể mô phỏng:

| Điểm dừng | Trạng thái DB | Kỳ vọng |
| --- | --- | --- |
| Sau insert outbox, trước commit nghiệp vụ | Transaction rollback | Không có outbox row đã commit |
| Sau claim, trước SMTP send | `PROCESSING` | Lease hết hạn, worker khác reclaim |
| SMTP send thất bại rõ ràng | `PROCESSING` trước update | Chuyển `RETRY` hoặc `FAILED` |
| SMTP chấp nhận, trước mark SENT | `PROCESSING` | Có thể retry và duplicate; phải được nhận diện là cửa sổ at-least-once |
| Mark SENT commit thành công | `SENT` | Không tự động gửi lại |
| Mark SENT gặp DB outage sau SMTP thành công | `PROCESSING` cho tới lease expiry | Cảnh báo và xử lý duplicate risk |

Không thể chứng minh exactly-once bằng mock unit test. Cần hiểu và chấp nhận rõ hành vi khi side effect bên ngoài thành công nhưng database chưa ghi nhận.

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đánh dấu `SENT` trước SMTP | Email có thể bị mất nếu process dừng | Gửi trước, cập nhật sau |
| Giữ DB transaction trong lúc gửi | Lock/connection bị giữ lâu | Claim, commit, send, update bằng transaction riêng |
| Chỉ đọc `PENDING` mà không claim nguyên tử | Nhiều worker gửi cùng email | Atomic claim, lock hoặc lease |
| Không có lease expiry | Hàng có thể kẹt `PROCESSING` vĩnh viễn | Lease và reclaim có điều kiện |
| Không kiểm tra lease owner/version | Worker cũ ghi đè kết quả mới | Conditional update/fencing token |
| Retry mọi exception vô hạn | Spam provider, worker bị chiếm dụng | Phân loại lỗi, backoff và max attempts |
| Retry ngay lập tức | Tạo retry storm | Exponential backoff + jitter |
| Coi `send` thành công là đã vào inbox | Báo cáo delivery sai | Định nghĩa SENT là SMTP accepted; theo dõi bounce riêng |
| Tin Message-ID ngăn duplicate | Vẫn có thể gửi trùng | Provider idempotency nếu có; chấp nhận at-least-once với SMTP |
| Lưu raw exception/payload trong log | Rò rỉ PII/token | Error code và thông điệp đã sanitize |
| Gửi nhiều recipient trong một row | Khó xử lý partial failure | Một delivery row cho mỗi recipient khi cần |
| Xóa row ngay khi SENT | Mất audit/dedup evidence | Retention/archive theo chính sách |

## 17. Câu hỏi thường gặp

**“Khi nào cập nhật outbox thành SENT?”**  
Sau khi `JavaMailSender.send` trả về thành công và trước khi kết thúc xử lý row. Nếu cập nhật database thất bại, row chưa được xác nhận SENT dù SMTP có thể đã nhận thư.

**“SENT có nghĩa email đã vào inbox không?”**  
Không. Nó chỉ có nghĩa lời gọi gửi qua transport đã hoàn tất thành công theo quan sát của ứng dụng. Bounce, spam filtering và delivery status cần cơ chế theo dõi riêng.

**“Có thể dùng một transaction bao cả database và SMTP không?”**  
Không thể rollback SMTP bằng transaction JDBC thông thường. Giữ transaction mở trong lúc gửi cũng làm tăng lock và connection time. Hãy dùng transaction ngắn để claim/update state, gửi ngoài transaction.

**“Tại sao không đánh dấu SENT trước khi gửi rồi rollback nếu gửi lỗi?”**  
Rollback database không thu hồi được email đã gửi, và process có thể dừng trước khi gửi. Cách đó có thể làm mất email. Gửi trước rồi cập nhật sau tạo at-least-once với duplicate window.

**“Transactional outbox có bảo đảm exactly-once không?”**  
Không. Nó giúp đồng bộ thay đổi nghiệp vụ và việc ghi nhận sự kiện trong database, nhưng không tạo distributed transaction với SMTP. Dispatch thường có ngữ nghĩa at-least-once.

**“Có nên retry MailSendException không?”**  
Không nên phân loại chỉ theo class. Hãy xem nested cause và SMTP response. Một số lỗi tạm thời có thể retry; lỗi địa chỉ, policy hoặc cấu hình thường cần xử lý khác.

**“Nếu worker chết khi đang PROCESSING thì sao?”**  
Lease hết hạn cho phép worker khác reclaim. Cần conditional update để worker cũ không ghi đè trạng thái mới.

**“Lease nên dài bao lâu?”**  
Phải dựa trên timeout kết nối/đọc/ghi SMTP và thời gian xử lý dự kiến. Nếu tác vụ dài hơn lease, cần heartbeat. Không để SMTP timeout vô hạn.

**“Có nên retry khi timeout không?”**  
Timeout trước khi kết nối/gửi thường có thể retry. Timeout sau khi truyền message có thể có kết quả không xác định; retry có thể duplicate. Chính sách cần cân nhắc tầm quan trọng của email và khả năng idempotency của provider.

**“Có thể dùng Message-ID làm idempotency key không?”**  
Có thể dùng để truy vết và correlation, nhưng SMTP server không bắt buộc deduplicate theo Message-ID. Chỉ dựa vào nó không bảo đảm exactly-once.

**“Có cần lưu trạng thái từng người nhận?”**  
Nếu gửi nhiều người và cần retry/đối soát riêng, nên có một delivery record cho từng recipient. Như vậy lỗi một địa chỉ không buộc gửi lại cho tất cả.

**“FAILED có nghĩa phải xóa bản ghi không?”**  
Không. FAILED thường là trạng thái cuối của retry tự động, giữ lại để audit và redrive sau khi xử lý nguyên nhân.

## 18. Ghi nhớ khi cập nhật trạng thái outbox sau khi gửi

Luồng điển hình:

~~~text
Business transaction
  - update domain state
  - insert outbox row (PENDING)
  - COMMIT
          |
          v
Outbox worker
  - atomically claim row
  - set PROCESSING + lease
  - COMMIT
          |
          v
Build and send message outside DB transaction
          |
      +---+---+
      |       |
      v       v
    Success  Failure
      |       |
      v       v
   mark SENT  classify exception
      |       |
      |    +--+---+
      |    |      |
      |    v      v
      |  RETRY  FAILED
      |    |
      |    v
      |  next_attempt_at + backoff
      |
      v
    COMMIT
~~~

Khi triển khai trong Spring Framework Mail:

1. Ghi outbox cùng transaction nghiệp vụ.
2. Claim từng batch bằng thao tác database nguyên tử và lease.
3. Commit claim trước khi gọi SMTP.
4. Gửi bằng `JavaMailSender` ngoài transaction database.
5. Nếu send trả về thành công, cập nhật `SENT` trong transaction ngắn.
6. Nếu lỗi, phân loại và cập nhật `RETRY` hoặc `FAILED` với error code, backoff và giới hạn số lần thử.
7. Dùng lease owner/version để ngăn worker cũ ghi đè trạng thái của worker mới.
8. Theo dõi duplicate window giữa SMTP accepted và database commit; không tuyên bố exactly-once khi dùng SMTP thuần.

Trạng thái outbox là cơ sở để worker phục hồi sau lỗi, vận hành quan sát backlog và retry có kiểm soát. Việc cập nhật đúng thời điểm, có điều kiện và trong transaction riêng giúp tránh mất email, hạn chế duplicate và giữ lịch sử xử lý nhất quán với kết quả mà ứng dụng thực sự quan sát được.
