# Quyền xử lý có thời hạn (lease) và thu hồi công việc sau sự cố

Trong hệ thống hàng đợi, một công việc thường được giao cho một worker xử lý. Nếu worker bị tắt đột ngột, mất kết nối hoặc treo giữa chừng, hệ thống cần cho phép worker khác tiếp tục công việc đó. Tuy nhiên, nếu chỉ đánh dấu công việc là “đang xử lý” và không có thời hạn, công việc có thể bị mắc kẹt mãi mãi sau khi worker chết.

**Lease** là quyền xử lý một tài nguyên trong một khoảng thời gian hữu hạn. Worker nhận quyền xử lý đến một thời điểm hết hạn (`lease_until`). Trong khi còn làm việc, worker có thể gia hạn lease bằng heartbeat. Nếu lease hết hạn mà công việc chưa hoàn tất, hệ thống có thể thu hồi quyền cũ và giao công việc cho worker khác.

Lease giúp phục hồi sau sự cố, nhưng cần hiểu một giới hạn quan trọng: **hết hạn lease không thể buộc tiến trình cũ dừng chạy**. Worker cũ có thể chỉ bị tạm dừng do GC, mất mạng hoặc quá tải rồi hoạt động trở lại sau khi worker mới đã nhận việc. Vì vậy, hệ thống cần token sở hữu, fencing token và idempotency để ngăn worker cũ ghi kết quả lỗi thời hoặc tạo tác động trùng lặp.

## 1. Lease khác khóa thông thường như thế nào?

Khóa (lock) thường biểu diễn quyền truy cập được giữ cho đến khi chủ sở hữu giải phóng hoặc transaction/session kết thúc. Lease bổ sung một thời điểm hết hạn. Sau thời điểm đó, hệ thống có thể xem quyền sở hữu cũ là không còn hiệu lực và cấp quyền mới.

| Khái niệm | Ý nghĩa | Điều gì kết thúc quyền sở hữu? |
|---|---|---|
| Lock | Quyền truy cập được DBMS hoặc hệ thống đồng bộ quản lý | Release, commit/rollback, đóng session hoặc cơ chế timeout của hệ thống |
| Lease | Quyền sử dụng tài nguyên có thời hạn | Hết hạn, release sớm hoặc bị thay thế theo giao thức |
| Heartbeat/renewal | Yêu cầu kéo dài thời hạn lease hiện tại | Không gia hạn được hoặc lease đã mất hiệu lực |
| Fencing token | Số thế hệ tăng đơn điệu để phân biệt chủ sở hữu mới/cũ | Token mới hơn làm token cũ bị từ chối tại tài nguyên được bảo vệ |

Ví dụ, worker A nhận công việc `job-42` trong 60 giây. Nếu A vẫn làm việc sau 45 giây, nó gia hạn lease thêm 60 giây. Nếu A chết sau 20 giây, lease vẫn tồn tại đến thời điểm hết hạn; sau đó worker B có thể nhận lại công việc.

```text
Thời gian ---------------------------------------------------->

Worker A:  claim job-42 -------- xử lý -------- mất kết nối
Lease A:   [===================== hết hạn ]
Worker B:                                   claim lại --- xử lý
Lease B:                                    [==================]
```

Lease thường dùng cho job queue, scheduler, distributed worker, xử lý file, đồng bộ dữ liệu, tác vụ định kỳ và tài nguyên logic chỉ nên có một chủ sở hữu tại một thời điểm.

## 2. Vòng đời của một công việc có lease

Một mô hình đơn giản có các trạng thái:

```text
                 claim thành công
        +------------------------------+
        |                              v
     READY                         LEASED
        ^                              |
        | retry có backoff             | hoàn tất và ack hợp lệ
        |                              v
     RETRY <--- lỗi có thể retry     DONE
        |
        | hết số lần thử
        v
      DEAD

LEASED -- lease hết hạn --> có thể được worker khác claim lại
```

Các trạng thái thường gặp:

- `READY`: công việc có thể được nhận, khi `available_at` đã đến.
- `LEASED`: một worker đang sở hữu quyền xử lý đến `lease_until`.
- `DONE`: công việc đã được xác nhận hoàn tất.
- `DEAD`: công việc vượt quá số lần thử hoặc gặp lỗi không thể tự phục hồi; cần điều tra hoặc xử lý thủ công.

Một hệ thống có thể dùng trạng thái `RETRY` riêng hoặc chỉ đưa công việc trở lại `READY` với `available_at` ở tương lai. Điều quan trọng là trạng thái, thời điểm sẵn sàng và quyền sở hữu phải được cập nhật nhất quán.

Quy trình cơ bản:

1. Worker yêu cầu một công việc sẵn sàng.
2. DBMS cấp quyền sở hữu có thời hạn và trả về lease token/generation.
3. Worker commit thao tác claim nhanh chóng rồi thực hiện công việc bên ngoài transaction claim.
4. Worker gửi heartbeat để gia hạn nếu cần.
5. Khi hoàn tất, worker xác nhận (acknowledge) bằng đúng token đang sở hữu.
6. Nếu worker chết hoặc không gia hạn, lease hết hạn và công việc có thể được claim lại.
7. Nếu công việc lỗi, worker có thể đưa nó về hàng đợi với backoff hoặc chuyển sang `DEAD` theo chính sách.

## 3. Thiết kế bảng hàng đợi

Ví dụ sau dùng PostgreSQL để minh họa. Các kiểu dữ liệu và cú pháp cần điều chỉnh nếu dùng DBMS khác.

```sql
CREATE TABLE job_queue (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload         JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'READY'
                    CHECK (status IN ('READY', 'LEASED', 'DONE', 'DEAD')),
    priority        INTEGER NOT NULL DEFAULT 0,
    available_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    lease_owner     TEXT,
    lease_token     UUID,
    lease_until     TIMESTAMPTZ,
    lease_epoch     BIGINT NOT NULL DEFAULT 0,
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 8,
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at    TIMESTAMPTZ,
    CHECK (attempts >= 0 AND max_attempts > 0),
    CHECK (lease_epoch >= 0),
    CHECK (
        (status = 'LEASED'
         AND lease_owner IS NOT NULL
         AND lease_token IS NOT NULL
         AND lease_until IS NOT NULL)
        OR
        (status <> 'LEASED'
         AND lease_owner IS NULL
         AND lease_token IS NULL
         AND lease_until IS NULL)
    )
);

CREATE INDEX ix_job_queue_ready
    ON job_queue (priority DESC, available_at, id)
    WHERE status = 'READY';

CREATE INDEX ix_job_queue_expired_lease
    ON job_queue (lease_until, id)
    WHERE status = 'LEASED';
```

Ý nghĩa các cột quan trọng:

- `lease_owner`: định danh worker đang nhận việc. Đây là thông tin quan sát và kiểm tra chủ sở hữu.
- `lease_token`: token ngẫu nhiên mới cho mỗi lần claim. Worker phải gửi lại token này khi gia hạn hoặc xác nhận.
- `lease_until`: thời điểm lease hết hạn theo đồng hồ DB.
- `lease_epoch`: fencing token tăng dần mỗi lần cấp quyền mới cho cùng job.
- `attempts` và `max_attempts`: giới hạn số lần giao việc để tránh retry vô hạn.
- `available_at`: thời điểm công việc được phép nhận lại sau backoff.

Token ngẫu nhiên và fencing token giải quyết hai vấn đề khác nhau. Token ngẫu nhiên giúp xác định đúng lần claim hiện tại. Fencing token cho biết quyền nào mới hơn theo thứ tự tăng dần, giúp tài nguyên downstream từ chối thao tác của worker cũ.

## 4. Claim công việc một cách nguyên tử

Không nên thực hiện hai bước độc lập “SELECT một job READY” rồi “UPDATE job thành LEASED” mà không khóa hoặc kiểm tra điều kiện. Hai worker có thể cùng đọc một hàng trước khi worker nào cập nhật.

Với PostgreSQL, có thể dùng `FOR UPDATE SKIP LOCKED` trong một câu lệnh claim. Mỗi worker truyền `worker_id` và một UUID mới làm `claim_token`:

```sql
WITH candidate AS (
    SELECT id
    FROM job_queue
    WHERE attempts < max_attempts
      AND (
          (status = 'READY' AND available_at <= clock_timestamp())
          OR
          (status = 'LEASED' AND lease_until <= clock_timestamp())
      )
    ORDER BY priority DESC, available_at, id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE job_queue AS job
SET status = 'LEASED',
    lease_owner = :worker_id,
    lease_token = :claim_token,
    lease_until = clock_timestamp() + INTERVAL '60 seconds',
    lease_epoch = job.lease_epoch + 1,
    attempts = job.attempts + 1
FROM candidate
WHERE job.id = candidate.id
RETURNING job.*;
```

Điều gì xảy ra?

1. Worker tìm một job đã đến `available_at` hoặc một job đang leased nhưng đã hết hạn.
2. `FOR UPDATE` khóa hàng ứng viên trong transaction claim.
3. `SKIP LOCKED` bỏ qua hàng đang bị worker khác khóa, tránh để nhiều worker cùng chờ một job đầu hàng.
4. Câu UPDATE đặt owner, token, thời hạn, tăng epoch và số lần thử.
5. `RETURNING` trả thông tin claim cho worker.

Worker phải commit transaction claim ngay sau khi nhận được hàng. Không giữ transaction mở trong suốt thời gian xử lý job; lease được lưu trong các cột và tồn tại sau commit. Nếu worker giữ transaction mở lâu, nó có thể giữ row lock không cần thiết và ngăn worker khác reclaim khi lease hết hạn.

`SKIP LOCKED` phù hợp cho hàng đợi vì worker có thể lấy hàng khác thay vì chờ hàng đang được xử lý. Nó không bảo đảm thứ tự công bằng tuyệt đối; một job thường xuyên bị khóa có thể bị bỏ qua nhiều lần. Nếu nghiệp vụ yêu cầu FIFO nghiêm ngặt hoặc ưu tiên công bằng, cần một thiết kế hàng đợi riêng.

## 5. Gia hạn lease bằng heartbeat

Worker xử lý công việc có thể cần nhiều thời gian hơn lease ban đầu. Heartbeat cho phép worker chứng minh nó vẫn còn hoạt động và yêu cầu gia hạn.

Một heartbeat phải là thao tác có điều kiện, chỉ gia hạn khi worker vẫn sở hữu đúng lần claim và lease chưa hết hạn:

```sql
UPDATE job_queue
SET lease_until = clock_timestamp() + INTERVAL '60 seconds'
WHERE id = :job_id
  AND status = 'LEASED'
  AND lease_owner = :worker_id
  AND lease_token = :claim_token
  AND lease_epoch = :lease_epoch
  AND lease_until > clock_timestamp()
RETURNING lease_until;
```

Nếu câu lệnh trả về một hàng, lease đã được gia hạn. Nếu trả về không hàng, worker không còn quyền sở hữu hợp lệ: token có thể đã bị thay thế, job đã hoàn tất, hoặc lease đã hết hạn.

Khi heartbeat thất bại, worker phải dừng việc tạo tác động mới và không được tiếp tục ghi như thể nó vẫn là owner. Nếu một thao tác không thể dừng ngay, mọi kết quả gửi đến hệ thống đích vẫn phải được bảo vệ bằng fencing token hoặc idempotency.

### Chọn chu kỳ heartbeat và thời hạn lease

Lease quá ngắn có thể hết hạn trong lúc worker đang bị pause do GC, CPU quá tải hoặc network chập chờn. Worker khác sẽ nhận lại công việc trong khi worker cũ vẫn có thể tiếp tục. Lease quá dài làm chậm phục hồi sau khi worker chết.

Một số nguyên tắc thực tế:

- Chọn thời hạn dài hơn đáng kể so với khoảng heartbeat dự kiến.
- Gia hạn trước khi còn quá ít thời gian, có dư địa cho độ trễ mạng và DB.
- Thêm jitter để nhiều worker không heartbeat cùng một thời điểm.
- Theo dõi độ trễ heartbeat, tỷ lệ renew thất bại và số lease hết hạn khi job còn chạy.
- Điều chỉnh theo phân phối thời gian xử lý thực tế, không chỉ theo thời gian trung bình.

Ví dụ, job thường chạy trong vài phút có thể dùng lease 60 giây và heartbeat khoảng mỗi 20 giây. Đây chỉ là điểm bắt đầu để đo, không phải giá trị mặc định phù hợp cho mọi workload.

## 6. Xác nhận hoàn tất chỉ khi còn sở hữu lease

Worker không được đánh dấu job `DONE` chỉ dựa trên `job_id`. Worker cũ có thể hoàn tất sau khi lease đã hết hạn và một worker khác đã nhận lại job. Cần xác nhận bằng owner, token, epoch và thời hạn:

```sql
UPDATE job_queue
SET status = 'DONE',
    completed_at = clock_timestamp(),
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL
WHERE id = :job_id
  AND status = 'LEASED'
  AND lease_owner = :worker_id
  AND lease_token = :claim_token
  AND lease_epoch = :lease_epoch
  AND lease_until > clock_timestamp()
RETURNING id;
```

Nếu có một hàng trả về, xác nhận hoàn tất thành công. Nếu không có hàng, worker đã mất quyền sở hữu hoặc lease hết hạn; nó không được ghi đè trạng thái của lần claim mới.

Đối với một job có kết quả dữ liệu trong cùng database, nên ghi kết quả và cập nhật `DONE` trong cùng transaction, đồng thời kiểm tra token/epoch trước khi ghi. Nếu chỉ cập nhật `DONE` sau khi đã ghi kết quả ở transaction khác, worker mới có thể bắt đầu lại trong khoảng giữa hai thao tác.

## 7. Thu hồi và giao lại công việc sau sự cố

Khi worker chết, nó không thể gửi release hoặc thông báo thất bại. Hệ thống dựa vào `lease_until` để phát hiện công việc bị bỏ lại.

Có hai cách phổ biến:

- **Claim trực tiếp job hết hạn:** câu lệnh claim xem job `LEASED` nhưng `lease_until <= now` là ứng viên và thay owner/token/epoch trong cùng thao tác.
- **Sweeper/reaper riêng:** một tiến trình định kỳ tìm lease hết hạn rồi đưa job về `READY` hoặc `DEAD`; worker sau đó claim job `READY`.

Claim trực tiếp thường giảm một bước cập nhật và tránh trạng thái trung gian. Reaper riêng hữu ích khi cần ghi audit, phân loại job quá số lần thử hoặc thực hiện chính sách dọn dẹp riêng.

### Reclaim bằng token mới

Khi worker B nhận lại job mà A đã để hết hạn, B phải nhận một `lease_token` mới và `lease_epoch` lớn hơn. Không tái sử dụng token cũ.

```text
Lần claim 1:
  owner = worker-A
  token = token-A
  epoch = 12
  lease_until = 10:01

Lease hết hạn.

Lần claim 2:
  owner = worker-B
  token = token-B
  epoch = 13
  lease_until = 10:03

Worker A thức dậy:
  token-A / epoch 12 không còn hợp lệ.
```

Việc thay token và tăng epoch phải diễn ra nguyên tử cùng với việc claim. Nếu cập nhật owner và token ở các câu lệnh riêng, có thể tạo một khoảng thời gian mà dữ liệu thể hiện quyền sở hữu không nhất quán.

### Đưa job hết số lần thử vào DEAD

Nếu một job đã đạt `max_attempts` và lease cuối cùng hết hạn, hệ thống không nên tiếp tục giao vô hạn. Một reaper có thể chuyển nó sang `DEAD`:

```sql
UPDATE job_queue
SET status = 'DEAD',
    last_error = COALESCE(last_error, 'Lease expired after final attempt'),
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL
WHERE status = 'LEASED'
  AND lease_until <= clock_timestamp()
  AND attempts >= max_attempts;
```

Điều kiện `lease_until <= clock_timestamp()` bảo đảm job chỉ được chuyển khi lease đã hết hạn tại thời điểm cập nhật. Nếu worker vừa gia hạn thành công, điều kiện cần được đánh giá lại sau khi DBMS giải quyết cạnh tranh trên hàng.

Job `DEAD` nên lưu thông tin lỗi, số lần thử, thời điểm và nguyên nhân cuối cùng. Cần có quy trình xem xét, sửa dữ liệu hoặc đưa job trở lại hàng đợi một cách có kiểm soát.

## 8. Lease hết hạn không dừng được worker cũ

Đây là giới hạn quan trọng nhất của lease phân tán. Giả sử A nhận lease 60 giây rồi bị pause 90 giây. Sau 60 giây, B nhận lại job và bắt đầu xử lý. Khi A hoạt động trở lại, cả A lẫn B đều có thể đang chạy.

```text
Thời gian ---------------------------------------------------->

Worker A: claim ---- pause lâu ---------------- thức dậy ---- ghi?
Lease A:  [=========== hết hạn
Worker B:                         claim lại ---- xử lý ---- ghi
Lease B:                          [==========================]
```

DBMS có thể từ chối heartbeat hoặc ACK của A, nhưng điều đó không tự ngăn A gọi một API bên ngoài, ghi vào một hệ thống khác hoặc gửi thông điệp. Lease chỉ là quyền được công nhận bởi nơi quản lý lease. Muốn bảo vệ tài nguyên downstream, cần một cơ chế mà downstream cũng kiểm tra quyền sở hữu hiện tại.

## 9. Fencing token ngăn worker cũ ghi đè

**Fencing token** là số thế hệ tăng đơn điệu mỗi lần cấp quyền mới cho một tài nguyên. Worker nhận token khi claim và gửi token đó cùng mọi thao tác ghi đến tài nguyên được bảo vệ. Tài nguyên đích chỉ chấp nhận token lớn hơn token đã chấp nhận trước đó.

Ví dụ:

1. A nhận epoch 12.
2. Lease của A hết hạn.
3. B nhận epoch 13.
4. B ghi với epoch 13; tài nguyên đích lưu epoch 13.
5. A hoạt động lại và gửi ghi với epoch 12.
6. Tài nguyên đích từ chối vì `12` nhỏ hơn epoch mới nhất `13`.

Một bảng đích có thể kiểm tra fencing token như sau:

```sql
UPDATE protected_resource
SET value = :new_value,
    last_fence = :fence
WHERE resource_id = :resource_id
  AND last_fence < :fence;
```

Nếu không có hàng nào được cập nhật, token đã cũ hoặc tài nguyên không tồn tại. Trong thực tế, logic kiểm tra và cập nhật phải nguyên tử; nếu cần cho phép nhiều thao tác hợp lệ trong cùng epoch, có thể dùng điều kiện `last_fence <= :fence` cùng kiểm tra owner/request sequence phù hợp. Thiết kế phải xác định rõ một epoch có thể gửi bao nhiêu thao tác.

### Fencing token phải thuộc phạm vi tài nguyên được bảo vệ

Nếu nhiều job cùng thay đổi một tài khoản, epoch tăng riêng trên từng job không đủ để sắp thứ tự quyền sở hữu của tài khoản. Token cần được cấp tăng dần theo chính tài nguyên đang được bảo vệ, ví dụ `account:42`, và mọi hệ thống ghi vào tài khoản đó phải kiểm tra token.

Fencing token chỉ có hiệu lực nếu hệ thống đích lưu và kiểm tra nó. Gửi kèm một con số mà API đích bỏ qua không tạo ra bảo vệ nào. Với hệ thống ngoài không hỗ trợ fencing, có thể cần idempotency key, version/conditional write hoặc một dịch vụ điều phối duy nhất.

## 10. Lease và tính lũy đẳng (idempotency)

Lease thường dẫn đến mô hình **at-least-once processing**: một job có thể được giao lại nếu worker hoàn tất tác động nhưng chết trước khi gửi ACK, hoặc nếu ACK bị mất trên đường truyền. Hệ thống không thể chỉ dựa vào lease để bảo đảm công việc chỉ chạy đúng một lần.

Ví dụ:

1. Worker A gọi cổng thanh toán thành công.
2. A chết trước khi cập nhật job thành `DONE`.
3. Lease hết hạn và worker B nhận lại job.
4. B gọi thanh toán lần nữa.

Nếu không có idempotency, khách hàng có thể bị tính tiền hai lần.

### 10.1. Dùng idempotency key ổn định

Mỗi hiệu ứng nghiệp vụ cần một key ổn định theo ý nghĩa của thao tác, ví dụ `charge:order-123`, không phải một UUID mới cho mỗi lần retry. Worker A và B phải dùng cùng key cho cùng một yêu cầu thanh toán.

Hệ thống đích lưu key đã xử lý và kết quả tương ứng. Khi nhận lại cùng key, nó trả về kết quả trước đó thay vì thực hiện hiệu ứng lần nữa. Với API bên ngoài, cần dùng idempotency mechanism mà nhà cung cấp hỗ trợ và hiểu thời gian lưu key của họ.

### 10.2. Unique constraint cho hiệu ứng trong cùng DB

Nếu hiệu ứng và trạng thái job nằm trong cùng database, có thể dùng bảng ghi nhận xử lý với unique key:

```sql
CREATE TABLE processed_effect (
    effect_key TEXT PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    result JSONB
);
```

Trong một transaction, ứng dụng tạo `effect_key` bằng INSERT; nếu key đã tồn tại thì không áp dụng hiệu ứng lần nữa. INSERT idempotency record và thay đổi nghiệp vụ phải nằm trong cùng transaction. Nếu record được commit riêng trước khi thay đổi dữ liệu, lỗi giữa hai bước có thể khiến hệ thống đánh dấu đã xử lý nhưng hiệu ứng chưa xảy ra.

### 10.3. Transactional outbox cho tác động bên ngoài

Nếu cần cập nhật DB rồi phát message, ghi thay đổi nghiệp vụ và outbox event trong cùng transaction. Một publisher riêng đọc outbox và gửi message; phía nhận xử lý idempotent theo event ID.

```text
Transaction nghiệp vụ:
  UPDATE order
  INSERT outbox(event_id, payload)
  COMMIT

Publisher:
  đọc outbox chưa gửi
  gửi message(event_id)
  đánh dấu đã gửi

Consumer:
  kiểm tra event_id đã xử lý chưa
  áp dụng hiệu ứng một lần theo idempotency key
```

Publisher cũng có thể gửi lặp nếu chết sau khi gửi nhưng trước khi đánh dấu đã gửi. Vì vậy, outbox bảo đảm event không bị mất giữa DB commit và publish, còn consumer vẫn cần idempotency.

## 11. Retry, backoff và dead-letter policy

Không phải mọi lỗi đều nên retry giống nhau. Phân loại lỗi giúp tránh lặp vô hạn và không làm quá tải hệ thống:

| Loại lỗi | Cách xử lý thường phù hợp |
|---|---|
| Timeout mạng hoặc dịch vụ tạm thời không khả dụng | Retry có giới hạn, exponential backoff và jitter |
| DB deadlock/serialization failure | Rollback transaction và retry toàn bộ đơn vị dữ liệu nếu an toàn |
| Dữ liệu đầu vào không hợp lệ | Đưa vào DEAD hoặc trả lỗi nghiệp vụ; không retry cùng payload vô hạn |
| Thiếu quyền/cấu hình sai | Dừng hoặc chuyển DEAD để vận hành can thiệp |
| Worker chết hoặc lease hết hạn | Cho phép reclaim sau expiry; dùng token mới và fencing |
| Lỗi không xác định sau khi tác động ngoài đã xảy ra | Tra cứu theo idempotency key trước khi thử lại |

Exponential backoff có thể dùng dạng:

```text
delay = min(max_delay, base_delay * 2^attempt) + jitter
```

Giới hạn số lần thử, thời gian tối đa và độ trễ tối đa. Không nên cho mọi job lỗi retry ngay lập tức vì có thể tạo retry storm khi dịch vụ phụ thuộc đang gặp sự cố.

Một job chuyển sang `DEAD` không có nghĩa là bỏ quên nó. Cần metric về số job DEAD, tuổi của job lâu nhất, lý do lỗi và quy trình redrive. Khi đưa job DEAD trở lại hàng đợi, cần quyết định giữ hay reset attempt counter, tạo lịch sử audit và bảo đảm idempotency vẫn dùng cùng định danh hiệu ứng.

## 12. Đồng hồ và thời điểm hết hạn

Lease cần một nguồn thời gian thống nhất. Nếu worker A so sánh lease bằng đồng hồ máy A và worker B dùng đồng hồ máy B, clock skew có thể khiến hai worker có cách hiểu khác nhau về thời điểm hết hạn.

Với lease lưu trong database, nên dùng đồng hồ DB để tạo và kiểm tra thời hạn trong câu SQL. Ví dụ PostgreSQL dùng `clock_timestamp()` để lấy thời gian thực tại thời điểm gọi. `CURRENT_TIMESTAMP`/`now()` trong PostgreSQL cố định theo thời điểm bắt đầu transaction; nếu transaction kéo dài, giá trị đó có thể cũ. Đây là một lý do nữa để giữ transaction claim ngắn và dùng hàm thời gian phù hợp.

Các điểm cần xác định:

- Lease hết hạn khi `lease_until <= now` hay chỉ khi `< now`? Chọn một quy ước và dùng nhất quán.
- Heartbeat có được gia hạn sau khi đã hết hạn không? Quy tắc an toàn thường từ chối renewal sau expiry.
- ACK có được chấp nhận sau expiry nếu chưa ai reclaim không? Quy tắc nghiêm ngặt nên từ chối; worker phải coi lease đã mất hiệu lực.
- DB failover hoặc thay đổi đồng hồ có ảnh hưởng thế nào đến lease đang tồn tại? Cần dùng nguồn thời gian ổn định và chính sách phục hồi phù hợp.

Đừng dùng timestamp do worker tự gửi làm bằng chứng duy nhất rằng lease còn hiệu lực. Worker có thể sai giờ hoặc gửi lại yêu cầu cũ. DBMS/lease service phải đánh giá thời hạn bằng đồng hồ có thẩm quyền.

## 13. Lease trong các DBMS và hệ thống hàng đợi

Lease là một mẫu thiết kế; DBMS có thể cung cấp các công cụ hỗ trợ claim và khóa hàng khác nhau.

### PostgreSQL

- `SELECT ... FOR UPDATE SKIP LOCKED` phù hợp để nhiều worker claim các hàng khác nhau.
- Có thể kết hợp CTE, UPDATE và `RETURNING` trong một câu lệnh để claim nguyên tử.
- `clock_timestamp()` giúp kiểm tra expiry theo thời gian thực của DB.
- Row lock chỉ bảo vệ transaction claim; lease lâu dài được biểu diễn bằng các cột owner/token/expiry sau khi commit.

### MySQL/InnoDB

- MySQL 8.0 hỗ trợ `SELECT ... FOR UPDATE SKIP LOCKED` với InnoDB cho các pattern hàng đợi.
- Cần claim và cập nhật trạng thái trong cùng transaction.
- Dùng `CURRENT_TIMESTAMP(6)` hoặc hàm thời gian phù hợp theo phiên bản, và giữ transaction ngắn.
- Kiểm tra kỹ isolation, index và engine; không giả định cú pháp hoặc hành vi giống PostgreSQL hoàn toàn.

### SQL Server

- Các hint như `UPDLOCK`, `READPAST` và `ROWLOCK` thường được dùng trong pattern claim hàng đợi.
- `READPAST` bỏ qua một số row lock đang bị giữ nhưng không phải mọi loại khóa; page lock và cấu hình isolation/RCSI có thể ảnh hưởng hành vi.
- Có thể dùng `UPDATE ... OUTPUT` để cập nhật trạng thái và trả hàng được claim trong một thao tác.
- Cần kiểm thử đúng phiên bản, isolation và cấu hình database; hint không thay thế token, expiry và điều kiện ownership.

Ví dụ khái niệm cho SQL Server:

```sql
;WITH candidate AS (
    SELECT TOP (1) *
    FROM dbo.JobQueue WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE Status = 'READY'
      AND AvailableAt <= SYSUTCDATETIME()
    ORDER BY Priority DESC, AvailableAt, JobId
)
UPDATE candidate
SET Status = 'LEASED',
    LeaseOwner = @workerId,
    LeaseToken = @claimToken,
    LeaseUntil = DATEADD(SECOND, 60, SYSUTCDATETIME()),
    LeaseEpoch = LeaseEpoch + 1,
    Attempts = Attempts + 1
OUTPUT inserted.*;
```

Đây là mẫu minh họa cho hàng READY; để reclaim job hết hạn, mở rộng predicate theo `Status = 'LEASED' AND LeaseUntil <= SYSUTCDATETIME()` và bảo đảm điều kiện không giao job quá số lần thử. `OUTPUT` trả hàng sau UPDATE. Cần đặt transaction boundary và xử lý lỗi theo ứng dụng.

### Message broker

Một số broker có visibility timeout, acknowledgement deadline hoặc delivery lease tích hợp. Worker nhận message và phải ACK trước deadline; nếu không, broker giao lại message. Dù broker quản lý việc giao lại, ứng dụng vẫn cần idempotency vì message có thể được giao nhiều lần. Không nên giả định broker delivery là exactly-once cho mọi hiệu ứng bên ngoài.

## 14. Những lỗi thường gặp khi triển khai lease

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ có cột `status = 'PROCESSING'`, không có expiry | Job mắc kẹt khi worker chết | Lưu `lease_until` và cơ chế reclaim |
| Claim bằng SELECT rồi UPDATE riêng rẽ | Hai worker có thể cùng nhận một job | Claim nguyên tử bằng row lock/conditional update |
| Không đổi token khi reclaim | Worker cũ có thể ACK thay worker mới | Token ngẫu nhiên mới và epoch tăng mỗi lần claim |
| Chỉ kiểm tra lease ở queue, không ở tài nguyên đích | Worker cũ vẫn có thể ghi sau expiry | Fencing token hoặc conditional write ở downstream |
| Heartbeat gia hạn sau expiry | Owner cũ có thể hồi sinh quyền đã mất | Renewal yêu cầu lease vẫn còn hiệu lực và token khớp |
| ACK chỉ theo job ID | Worker cũ có thể đánh dấu DONE job đã được giao lại | ACK phải kiểm tra owner, token, epoch và expiry |
| Giữ transaction mở trong suốt job | Giữ row lock và connection quá lâu | Commit claim nhanh, xử lý ngoài transaction |
| Không có idempotency | Retry có thể tạo thanh toán/message/tác động trùng | Idempotency key ổn định và unique constraint ở nơi nhận |
| Lease quá ngắn hoặc quá dài | Reclaim nhầm hoặc phục hồi chậm | Đo thời gian xử lý, heartbeat và độ trễ thực tế |
| Retry vô hạn | Retry storm và job lỗi lặp mãi | Giới hạn attempts, backoff và DEAD queue |

## 15. Quy trình thiết kế lease an toàn

Trước khi triển khai, hãy xác định rõ:

1. **Định danh công việc:** job ID có ổn định qua mọi lần retry không?
2. **Chủ sở hữu:** worker ID và claim token được tạo, lưu và kiểm tra thế nào?
3. **Thời hạn:** lease dài bao lâu, heartbeat theo chu kỳ nào và dùng đồng hồ nào?
4. **Claim nguyên tử:** hai worker có thể cùng nhận một job không?
5. **Gia hạn:** chỉ owner hiện tại mới được renew; renewal sau expiry có bị từ chối không?
6. **ACK/release:** có kiểm tra token và epoch không; điều gì xảy ra nếu ACK thất bại?
7. **Reclaim:** worker khác nhận job hết hạn trong một thao tác nguyên tử nào?
8. **Fencing:** tài nguyên downstream có từ chối token cũ không?
9. **Idempotency:** nếu công việc chạy lại, hiệu ứng nghiệp vụ có bị lặp không?
10. **Retry/dead-letter:** giới hạn lần thử, backoff, audit và redrive được thiết kế ra sao?
11. **Quan sát:** có metric về lease expiry, renewal failure, job age, attempts và duplicate suppression không?

Lease cho phép hệ thống thu hồi công việc khi worker không còn hoạt động và giao lại cho worker khác sau một thời hạn. Nhưng lease không dừng được worker cũ và cũng không bảo đảm một hiệu ứng chỉ xảy ra một lần. Một thiết kế đáng tin cậy cần claim nguyên tử, token sở hữu mới cho mỗi lần nhận, heartbeat có điều kiện, ACK có xác thực, fencing token tại tài nguyên được bảo vệ và idempotency cho mọi tác động có thể được thực hiện lại. Khi kết hợp các cơ chế này với backoff, giới hạn retry và dead-letter policy, hàng đợi có thể phục hồi sau sự cố mà vẫn giữ được tính đúng đắn của dữ liệu.
