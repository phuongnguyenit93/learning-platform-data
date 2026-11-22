# SKIP LOCKED cho phân phối công việc và giới hạn về kết quả đầy đủ

Trong một hàng đợi công việc được lưu trong cơ sở dữ liệu, nhiều worker thường cùng tìm một công việc đang sẵn sàng để xử lý. Nếu tất cả worker cùng đọc hàng đầu tiên rồi mới cập nhật trạng thái, chúng có thể chọn trùng một công việc. Khóa tường minh giúp đồng bộ việc nhận công việc; `SKIP LOCKED` cho phép một worker bỏ qua những hàng đang bị worker khác khóa và tiếp tục tìm hàng khác có thể nhận ngay.

Đây là cách hữu ích để phân phối công việc giữa nhiều worker mà không buộc chúng chờ cùng một hàng. Tuy nhiên, `SKIP LOCKED` cố ý trả về một tập kết quả **không đầy đủ theo nghĩa toàn bộ hàng thỏa điều kiện**: các hàng đang bị khóa có thể bị bỏ qua. Vì vậy, nó phù hợp cho queue hoặc tác vụ tranh quyền xử lý, nhưng không phù hợp cho truy vấn cần đọc đầy đủ mọi hàng thỏa điều kiện, báo cáo chính xác hoặc kiểm tra một bất biến trên toàn bộ tập dữ liệu.

## 1. Vấn đề nhiều worker cùng nhận một công việc

Giả sử bảng `job_queue` có ba công việc đang chờ:

| job_id | status | priority |
|---:|---|---:|
| 101 | READY | 10 |
| 102 | READY | 8 |
| 103 | READY | 5 |

Worker A và Worker B cùng chạy truy vấn lấy công việc có độ ưu tiên cao nhất. Nếu cả hai chỉ `SELECT` hàng đầu tiên rồi sau đó mới `UPDATE status`, cả hai có thể đọc `job_id = 101` trước khi bất kỳ bên nào cập nhật trạng thái.

```text
Worker A                         Worker B
-----------------------------    -----------------------------
SELECT job 101                   SELECT job 101
UPDATE job 101 -> RUNNING        UPDATE job 101 -> RUNNING
Xử lý job 101                    Cũng nghĩ mình nhận job 101
```

Ứng dụng có thể xử lý cùng một công việc hai lần. Một cách sửa là khóa hàng trước khi đọc và cập nhật. Khi A giữ khóa hàng 101, B phải chờ khóa đó được giải phóng. Nhưng nếu queue có nhiều công việc khác, B không cần chờ 101; B có thể nhận 102 ngay.

`SKIP LOCKED` hỗ trợ đúng kiểu xử lý này: khi truy vấn gặp một hàng bị khóa bởi transaction khác, nó bỏ qua hàng đó thay vì chờ.

## 2. Ý nghĩa của FOR UPDATE SKIP LOCKED

Trong PostgreSQL, `SELECT ... FOR UPDATE` yêu cầu khóa cập nhật trên những hàng được chọn. Khóa hàng được giữ đến khi transaction kết thúc. Một transaction khác muốn lấy khóa xung đột trên cùng hàng sẽ phải chờ.

Khi thêm `SKIP LOCKED`, truy vấn không chờ các hàng bị khóa ở cấp hàng mà nó gặp; nó bỏ qua chúng và tiếp tục tìm hàng khác thỏa điều kiện có thể khóa ngay.

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

Nếu Worker A đã khóa hàng 101, Worker B chạy câu lệnh trên có thể bỏ qua 101 và lấy 102. Sau đó B cập nhật trạng thái 102 trong cùng transaction rồi commit.

`SKIP LOCKED` thay đổi cách xử lý xung đột khóa hàng. Nó không có nghĩa là:

- Bỏ qua mọi loại lock trong DBMS.
- Bỏ qua điều kiện `WHERE` hoặc tự động chọn hàng bất kỳ.
- Đảm bảo thứ tự FIFO tuyệt đối giữa các worker.
- Đảm bảo một công việc chỉ được thực thi đúng một lần trong mọi tình huống lỗi.
- Trả về toàn bộ các hàng thỏa điều kiện.

Trong PostgreSQL, `SKIP LOCKED` bỏ qua xung đột khóa ở cấp hàng. Khóa ở cấp bảng vẫn được lấy theo quy tắc bình thường và truy vấn vẫn có thể chờ một table-level lock xung đột. Đây là điểm cần nhớ khi một truy vấn có `SKIP LOCKED` vẫn bị chậm do DDL hoặc lock ở cấp bảng.

### 2.1. So sánh chờ khóa, NOWAIT và SKIP LOCKED

| Cách lấy khóa | Khi hàng cần khóa đang bị transaction khác giữ | Kết quả phù hợp |
|---|---|---|
| `FOR UPDATE` | Chờ đến khi có thể lấy khóa hoặc transaction bị hủy/timeout | Khi cần đúng hàng theo điều kiện và chấp nhận chờ |
| `FOR UPDATE NOWAIT` | Báo lỗi ngay nếu không thể lấy khóa | Khi không muốn chờ và muốn ứng dụng tự quyết định xử lý lỗi |
| `FOR UPDATE SKIP LOCKED` | Bỏ qua hàng đang xung đột, tiếp tục tìm hàng khác | Queue, worker pool và phân phối công việc |

`NOWAIT` và `SKIP LOCKED` giải quyết hai nhu cầu khác nhau. `NOWAIT` nói rằng không lấy được khóa ngay thì toàn bộ yêu cầu thất bại. `SKIP LOCKED` nói rằng hàng đang xung đột không cần thiết cho lượt nhận việc hiện tại; hãy thử hàng tiếp theo.

## 3. Luồng nhận công việc an toàn

Một queue thường cần thực hiện ba việc trong một thao tác nguyên tử:

1. Chọn một hoặc một nhóm hàng đang sẵn sàng.
2. Khóa các hàng đã chọn để worker khác không cùng nhận chúng.
3. Đổi trạng thái sang đang xử lý và ghi nhận worker nhận việc.

Nếu việc chọn hàng và đổi trạng thái nằm trong cùng transaction, lock manager điều phối các worker. PostgreSQL có thể dùng CTE kết hợp `FOR UPDATE SKIP LOCKED` và `UPDATE ... RETURNING`:

```sql
WITH picked AS (
    SELECT job_id
    FROM job_queue
    WHERE status = 'READY'
      AND available_at <= now()
    ORDER BY priority DESC, created_at, job_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE job_queue AS j
SET status = 'RUNNING',
    locked_by = :worker_id,
    locked_at = clock_timestamp(),
    attempts = attempts + 1
FROM picked
WHERE j.job_id = picked.job_id
RETURNING j.job_id, j.payload, j.attempts;
```

Ứng dụng thực hiện câu lệnh trong transaction rồi commit ngay sau khi nhận được hàng:

```sql
BEGIN;

-- Chạy câu lệnh CTE UPDATE ở trên.

COMMIT;
```

Nếu `RETURNING` trả về một hàng, worker đã claim được công việc đó. Nếu không có hàng nào, lượt nhận việc hiện tại không tìm được hàng có thể khóa theo điều kiện và chính sách đang dùng.

Việc cập nhật `status`, `locked_by` và `attempts` trong cùng statement giúp tránh khoảng trống giữa lúc chọn và lúc đánh dấu công việc. Worker khác sẽ không nhận cùng hàng trong lúc transaction đầu đang giữ khóa; sau khi commit, worker khác thấy trạng thái mới và không còn coi hàng đó là `READY`.

### 3.1. Vì sao cần UPDATE ... RETURNING?

Nếu ứng dụng chạy một câu `SELECT` để lấy `job_id`, sau đó chạy một câu `UPDATE` riêng mà không giữ transaction và lock phù hợp, một worker khác có thể thay đổi hàng trong khoảng giữa hai câu lệnh.

`UPDATE ... RETURNING` trả về dữ liệu của hàng đã được cập nhật trong cùng statement. Nhờ đó, ứng dụng có thể nhận payload và thông tin công việc sau khi claim thành công mà không phải mở thêm một khoảng tranh chấp.

### 3.2. Nhận nhiều công việc trong một lượt

Worker có thể claim một batch bằng cách tăng `LIMIT`:

```sql
WITH picked AS (
    SELECT job_id
    FROM job_queue
    WHERE status = 'READY'
      AND available_at <= now()
    ORDER BY priority DESC, created_at, job_id
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE job_queue AS j
SET status = 'RUNNING',
    locked_by = :worker_id,
    locked_at = clock_timestamp(),
    attempts = attempts + 1
FROM picked
WHERE j.job_id = picked.job_id
RETURNING j.job_id, j.payload;
```

Mỗi worker có thể nhận tối đa 20 hàng trong lượt này. Batch lớn giảm số lần round trip đến database nhưng có thể làm một worker giữ nhiều công việc trong khi worker khác thiếu việc. Kích thước batch nên dựa trên thời gian xử lý, số worker, độ lớn payload và khả năng phục hồi khi worker dừng giữa chừng.

## 4. Transaction nên kết thúc ở thời điểm nào?

Một lựa chọn quan trọng là giữ transaction mở trong suốt thời gian xử lý công việc hay commit ngay sau khi claim.

### 4.1. Giữ khóa trong lúc xử lý

Worker có thể `SELECT ... FOR UPDATE SKIP LOCKED`, xử lý công việc rồi mới cập nhật trạng thái và commit. Trong toàn bộ thời gian xử lý, khóa hàng vẫn được giữ.

```text
BEGIN
  Claim job và giữ row lock
  Xử lý công việc trong nhiều giây/phút
  Đánh dấu DONE
COMMIT (giải phóng lock)
```

Cách này có thể hữu ích nếu phần xử lý ngắn, nằm hoàn toàn trong database và cần commit/rollback cùng một transaction. Nhưng nếu xử lý lâu hoặc gọi dịch vụ bên ngoài, transaction dài sẽ giữ lock lâu, làm worker khác bỏ qua hàng đó, chiếm connection và có thể giữ snapshot hoặc tài nguyên khác lâu hơn cần thiết.

Nếu worker chết, database rollback transaction và giải phóng lock, nhưng mọi tác động bên ngoài transaction có thể đã xảy ra mà không rollback được. Vì vậy, giữ transaction mở trong lúc gọi HTTP, chạy chương trình ngoài hoặc chờ người dùng thường không phải thiết kế tốt.

### 4.2. Claim rồi commit, sau đó xử lý

Một cách phổ biến hơn là claim công việc trong transaction ngắn, cập nhật trạng thái và commit ngay. Worker xử lý bên ngoài transaction; khi xong, nó mở transaction khác để đánh dấu hoàn tất.

```text
Transaction 1:
  Claim job bằng SKIP LOCKED
  Đổi READY -> RUNNING
  COMMIT

Xử lý job ngoài transaction

Transaction 2:
  Đổi RUNNING -> DONE
  COMMIT
```

Sau commit đầu tiên, row lock được giải phóng. Worker khác không nhận lại hàng vì trạng thái đã là `RUNNING`. Thiết kế này không cần giữ transaction trong suốt thời gian chạy tác vụ.

Tuy nhiên, nếu worker bị dừng sau khi commit claim nhưng trước khi hoàn thành, hàng có thể mắc ở `RUNNING`. Queue cần cơ chế lease/timeout để một worker khác có thể nhận lại công việc sau khi quyền claim hết hạn.

## 5. Lease, timeout và phục hồi worker bị chết

Trong mô hình claim rồi commit, trạng thái `RUNNING` cần có thời hạn sở hữu. Một **lease** (quyền xử lý có thời hạn) thường gồm:

- Worker đang sở hữu công việc.
- Thời điểm lease hết hạn (`locked_until`).
- Mã token hoặc số phiên bản claim để nhận diện lần claim hiện tại.
- Số lần thử (`attempts`) và thời điểm bắt đầu.

Ví dụ schema minh họa:

```sql
CREATE TABLE job_queue (
    job_id       bigint PRIMARY KEY,
    payload      jsonb NOT NULL,
    status       text NOT NULL,
    priority     integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    locked_by    text,
    locked_at    timestamptz,
    locked_until timestamptz,
    lease_token  uuid,
    attempts     integer NOT NULL DEFAULT 0
);
```

Một worker chỉ claim hàng đang `READY` hoặc hàng `RUNNING` đã hết lease theo chính sách phục hồi. Cần cập nhật lease và token trong cùng thao tác claim.

```sql
WITH picked AS (
    SELECT job_id
    FROM job_queue
    WHERE (status = 'READY' AND available_at <= now())
       OR (status = 'RUNNING' AND locked_until < now())
    ORDER BY priority DESC, available_at, job_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE job_queue AS j
SET status = 'RUNNING',
    locked_by = :worker_id,
    locked_at = clock_timestamp(),
    locked_until = now() + interval '2 minutes',
    lease_token = :new_lease_token,
    attempts = attempts + 1
FROM picked
WHERE j.job_id = picked.job_id
RETURNING j.job_id, j.payload, j.lease_token, j.locked_until;
```

Đây là mẫu khái quát; điều kiện phục hồi, thời gian lease, retry limit và xử lý công việc quá hạn phải phù hợp với nghiệp vụ. Một số hệ thống dùng bảng lịch sử claim riêng hoặc trạng thái `RETRY`/`FAILED` thay vì gộp hàng hết lease vào điều kiện claim.

### 5.1. Vì sao cần lease token?

Giả sử Worker A nhận job với token `token-A`, nhưng xử lý quá lâu. Lease hết hạn và Worker B nhận lại job với token `token-B`. Sau đó A tỉnh lại và cố đánh dấu job hoàn tất. Nếu A chỉ cập nhật theo `job_id`, nó có thể ghi đè trạng thái của lần claim mới do B đang sở hữu.

Token giúp điều kiện cập nhật xác nhận worker vẫn sở hữu đúng lần claim:

```sql
UPDATE job_queue
SET status = 'DONE',
    locked_by = NULL,
    locked_until = NULL
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND lease_token = :lease_token;
```

Nếu số hàng được cập nhật là 0, token đã hết hiệu lực hoặc hàng không còn ở trạng thái mà worker mong đợi. Worker cũ không được tự ý ghi đè kết quả của worker mới.

Token ngẫu nhiên giúp nhận diện lần claim. Với hệ thống cần bảo vệ tài nguyên bên ngoài khỏi một worker cũ vẫn tiếp tục chạy, có thể cần fencing token dạng số tăng đơn điệu và hệ thống đích cũng phải kiểm tra token. Chỉ kiểm tra token trong database không thể ngăn một worker cũ tiếp tục gửi lệnh đến dịch vụ bên ngoài nếu dịch vụ đó không tham gia giao thức.

### 5.2. Gia hạn lease

Nếu công việc có thời gian xử lý dài hoặc không dự đoán được, worker có thể gia hạn lease định kỳ:

```sql
UPDATE job_queue
SET locked_until = now() + interval '2 minutes'
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND lease_token = :lease_token;
```

Worker chỉ được coi việc gia hạn thành công nếu câu lệnh cập nhật đúng một hàng. Nếu cập nhật 0 hàng, lease đã mất hoặc claim đã được thay thế; worker nên dừng xử lý nếu có thể làm an toàn.

Lease quá ngắn có thể khiến công việc bị nhận lại khi worker vẫn đang xử lý. Lease quá dài làm chậm phục hồi khi worker thực sự chết. Có thể chọn thời gian dựa trên phân phối thời gian xử lý, gia hạn định kỳ và giới hạn tổng số lần thử.

## 6. SKIP LOCKED không bảo đảm exactly-once

`SKIP LOCKED` giải quyết tranh chấp khi nhiều worker chọn hàng trong database. Nó không thể tự bảo đảm một tác vụ bên ngoài chỉ được thực hiện đúng một lần.

Ví dụ, worker thực hiện các bước:

1. Claim job và commit trạng thái `RUNNING`.
2. Gửi yêu cầu thanh toán đến dịch vụ bên ngoài.
3. Dịch vụ thanh toán xử lý thành công.
4. Worker bị crash trước khi cập nhật `DONE`.
5. Lease hết hạn và worker khác nhận lại job.
6. Yêu cầu thanh toán được gửi lần nữa.

Database không thể rollback một khoản thanh toán đã được dịch vụ khác chấp nhận. Vì vậy, queue kiểu này thường cung cấp ngữ nghĩa **at-least-once**: công việc có thể được giao lại khi kết quả chưa được xác nhận.

Để tránh tác động trùng lặp, handler nên idempotent (cùng một yêu cầu xử lý nhiều lần vẫn tạo ra một kết quả nghiệp vụ duy nhất). Có thể dùng:

- Idempotency key ổn định theo `job_id` hoặc theo thao tác nghiệp vụ.
- Bảng ghi nhận kết quả đã xử lý với unique constraint.
- Transactional outbox/inbox để phối hợp thay đổi database với phát sự kiện.
- Fencing token nếu tài nguyên đích hỗ trợ từ chối lệnh từ worker có token cũ.

Không nên tuyên bố hệ thống exactly-once chỉ vì một hàng được khóa bằng `SKIP LOCKED`. Exactly-once end-to-end cần một giao thức bao phủ cả database, worker và hệ thống đích; trong nhiều ứng dụng, at-least-once kết hợp idempotency là lựa chọn thực tế hơn.

## 7. Giới hạn quan trọng: kết quả không đầy đủ

`SKIP LOCKED` được thiết kế để không chờ những hàng đang bị khóa. Vì vậy, tập kết quả trả về phụ thuộc vào trạng thái lock tại thời điểm truy vấn chạy.

Giả sử có 5 hàng `READY`, nhưng hai hàng đầu đang bị worker khác khóa:

```text
Theo thứ tự ưu tiên:

job 101  READY  [locked by A]  -> B bỏ qua
job 102  READY  [locked by A]  -> B bỏ qua
job 103  READY  [unlocked]     -> B nhận
job 104  READY  [unlocked]     -> B có thể nhận tiếp nếu LIMIT cho phép
job 105  READY  [unlocked]     -> có thể còn lại
```

Kết quả của B không phải toàn bộ hàng `READY`. Đó là những hàng thỏa điều kiện và có thể khóa ngay trong lượt truy vấn của B.

### 7.1. Không có hàng trả về không có nghĩa queue rỗng

Nếu truy vấn trả về 0 hàng, có nhiều khả năng:

- Không có công việc thỏa điều kiện.
- Có công việc thỏa điều kiện nhưng tất cả đang bị worker khác khóa.
- Công việc chưa đến `available_at`.
- Điều kiện lọc hoặc trạng thái queue không khớp.
- Worker khác vừa claim các hàng trước khi truy vấn này có thể khóa chúng.

Vì vậy, kết quả rỗng chỉ nói rằng **lượt claim này không lấy được hàng nào**. Nó không chứng minh không còn công việc trong hệ thống. Worker có thể đợi một khoảng ngắn, nhận tín hiệu đánh thức từ hệ thống queue hoặc thử lại theo backoff có giới hạn.

### 7.2. Không dùng để đếm chính xác hoặc báo cáo đầy đủ

Truy vấn sau không phù hợp nếu mục tiêu là đếm tất cả công việc đang `READY`:

```sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
```

Nó bỏ qua những hàng đang bị khóa. Một báo cáo dựa trên tập hàng đó sẽ thiếu dữ liệu tùy thuộc worker đang chạy và lock hiện tại. Tương tự, không dùng `SKIP LOCKED` để:

- Xuất danh sách đầy đủ mọi đơn hàng, khách hàng hoặc giao dịch thỏa điều kiện.
- Kiểm tra chính xác số lượng hàng trong một nhóm.
- Tạo báo cáo tài chính hoặc đối soát cần đầy đủ bản ghi.
- Xác nhận không tồn tại một hàng thỏa điều kiện.
- Thực hiện kiểm tra bất biến trên toàn bộ tập dữ liệu.

Với truy vấn cần kết quả đầy đủ, hãy dùng một cách đọc có semantics phù hợp: truy vấn thông thường theo isolation level yêu cầu, constraint, transaction Serializable hoặc cơ chế khóa/phạm vi được thiết kế rõ ràng. Không thêm `SKIP LOCKED` chỉ để truy vấn chạy nhanh hơn nếu bỏ sót hàng làm sai kết quả nghiệp vụ.

### 7.3. Kết quả có thể không phản ánh thứ tự ưu tiên toàn cục

`ORDER BY priority DESC` sắp xếp các hàng mà truy vấn có thể xử lý, nhưng những hàng ưu tiên cao đang bị khóa có thể bị bỏ qua. Worker khác có thể nhận công việc ưu tiên thấp hơn trước.

Ví dụ, job 101 có priority 100 đang bị A khóa; B bỏ qua và nhận job 102 có priority 20. Do đó, `SKIP LOCKED` không bảo đảm mọi worker trên toàn hệ thống luôn xử lý đúng thứ tự ưu tiên nghiêm ngặt. Nó ưu tiên tiến độ và khả năng song song hơn việc chờ hàng đầu tiên.

Nếu yêu cầu nghiệp vụ bắt buộc strict FIFO hoặc strict priority, cần thiết kế một cơ chế điều phối khác, chẳng hạn một dispatcher tuần tự, partition queue theo nhóm hoặc khóa một tài nguyên điều phối. Cách này có thể giảm thông lượng và tạo điểm nóng, nên cần cân nhắc yêu cầu thực tế.

### 7.4. Có thể xảy ra starvation

Một hàng liên tục bị khóa lâu hoặc luôn nằm trong nhóm hàng mà worker khác nhận trước có thể bị bỏ qua qua nhiều lượt. Công việc đó có thể chờ lâu hơn các công việc mới có độ ưu tiên thấp hơn.

Để giảm starvation:

- Giữ transaction claim ngắn và không khóa hàng trong suốt tác vụ dài.
- Dùng lease có thời hạn để phục hồi hàng bị bỏ lại.
- Theo dõi tuổi của công việc READY và RUNNING.
- Tăng ưu tiên theo thời gian chờ (aging) nếu nghiệp vụ cho phép.
- Chia queue theo loại công việc hoặc tenant để một nhóm không chiếm hết worker.
- Có cơ chế cảnh báo khi công việc chờ vượt ngưỡng.

Không có một `ORDER BY` đơn giản nào loại bỏ hoàn toàn starvation khi các hàng có thể liên tục bị khóa hoặc có worker đến nhận cạnh tranh.

## 8. Thứ tự, LIMIT và phân trang

Queue thường dùng `ORDER BY` để ưu tiên công việc. Nên có cột phụ ổn định, chẳng hạn `job_id`, để xử lý các hàng có cùng priority:

```sql
ORDER BY priority DESC, available_at, job_id
```

Nếu không có thứ tự phụ ổn định, thứ tự giữa các hàng bằng priority có thể thay đổi theo kế hoạch thực thi và trạng thái dữ liệu. Tuy nhiên, kể cả có thứ tự xác định, `SKIP LOCKED` vẫn có thể bỏ qua hàng đầu tiên đang bị khóa.

Không nên áp dụng phân trang offset thông thường cho worker queue đang thay đổi liên tục:

```sql
-- Không phải cách phân trang claim an toàn cho queue đồng thời
SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY job_id
OFFSET 100 LIMIT 20
FOR UPDATE SKIP LOCKED;
```

Khi các worker khác claim hoặc hoàn tất hàng, vị trí offset có thể dịch chuyển. Worker có thể bỏ sót hoặc gặp lại các hàng khác giữa các lượt. Queue thường claim batch kế tiếp từ tập hàng hiện có thay vì dùng offset như một báo cáo phân trang ổn định.

Nếu cần quét toàn bộ tập dữ liệu để đối soát, hãy dùng một snapshot/read transaction phù hợp hoặc cơ chế export riêng. Không xem các batch `SKIP LOCKED` là các trang đầy đủ, không chồng lấn của một snapshot chung.

## 9. Index và hiệu năng của queue

Khi nhiều worker liên tục tìm công việc sẵn sàng, truy vấn claim cần lọc và sắp xếp hiệu quả. Nếu không có index phù hợp, mỗi worker có thể quét nhiều hàng rồi bỏ qua phần lớn vì chúng đang bị khóa.

Ví dụ với PostgreSQL, có thể cân nhắc partial index cho hàng `READY`:

```sql
CREATE INDEX idx_job_queue_ready
ON job_queue (priority DESC, available_at, job_id)
WHERE status = 'READY';
```

Index phải phù hợp với điều kiện lọc và thứ tự ưu tiên thực tế. Nếu truy vấn cũng claim hàng hết lease ở trạng thái `RUNNING`, phần điều kiện đó có thể cần index hoặc chiến lược riêng. Một index rộng trên toàn bảng không phải lúc nào cũng tốt hơn partial index.

Các yếu tố cần đo:

- Số hàng phải quét trước khi tìm được batch có thể khóa.
- Tỷ lệ hàng `READY` so với hàng đã hoàn tất hoặc thất bại.
- Số worker cạnh tranh trên cùng queue/partition.
- Thời gian giữ row lock và thời gian transaction.
- Số lần claim trả về rỗng dù queue vẫn còn việc.
- Độ trễ từ `created_at` đến lúc claim và từ claim đến lúc hoàn tất.
- Tần suất lease hết hạn và công việc được giao lại.

Khi bảng queue tích lũy nhiều hàng hoàn tất, có thể cần chính sách lưu trữ/archive hoặc xóa lịch sử theo thời hạn. Không nên xóa ngay dữ liệu cần cho audit, retry hoặc idempotency.

## 10. Hạn chế về loại truy vấn và phạm vi khóa

`FOR UPDATE SKIP LOCKED` áp dụng cho những hàng mà DBMS có thể khóa trong truy vấn. Trong PostgreSQL, locking clause không dùng được với một số dạng truy vấn tổng hợp như `GROUP BY`, `HAVING`, `DISTINCT` hoặc hàm aggregate ở cùng query level. Một mô hình phổ biến là chọn hàng cơ sở trong CTE, khóa chúng, rồi thực hiện cập nhật; việc tổng hợp hoặc báo cáo thực hiện ở câu truy vấn khác.

Ngoài ra, `SKIP LOCKED` không thay thế khóa bảng hoặc khóa khác mà statement cần lấy. Một truy vấn vẫn có thể chờ table lock, advisory lock hoặc tài nguyên khác. Nó cũng không bỏ qua hàng bị ẩn bởi điều kiện visibility hoặc điều kiện `WHERE`; nó chỉ bỏ qua xung đột khóa hàng theo cơ chế của DBMS.

Nếu query join nhiều bảng, cần hiểu chính xác bảng nào đang được khóa. Trong PostgreSQL có thể chỉ định bảng cho locking clause, ví dụ `FOR UPDATE OF j SKIP LOCKED`, để giới hạn hàng thuộc bảng alias `j` được khóa. Khóa không cần thiết trên bảng khác có thể làm tăng tranh chấp.

Ví dụ:

```sql
SELECT j.job_id, q.name
FROM job_queue AS j
JOIN queue_type AS q ON q.queue_type_id = j.queue_type_id
WHERE j.status = 'READY'
ORDER BY j.priority DESC, j.job_id
LIMIT 10
FOR UPDATE OF j SKIP LOCKED;
```

Trong PostgreSQL, `OF j` chỉ định hàng từ bảng `job_queue` được khóa. Hãy xác nhận cú pháp và hành vi join theo DBMS cụ thể đang dùng.

## 11. Khác biệt giữa các hệ quản trị cơ sở dữ liệu

Tên và cú pháp có thể khác nhau giữa các sản phẩm. Không nên giả định mọi hệ thống đều thực hiện `SKIP LOCKED` giống PostgreSQL.

| DBMS | Cơ chế thường gặp | Điểm cần lưu ý |
|---|---|---|
| PostgreSQL | `FOR UPDATE SKIP LOCKED` hoặc các locking clause phù hợp | Bỏ qua xung đột khóa hàng; table-level lock vẫn theo quy tắc bình thường. Phù hợp queue, trả kết quả có chủ ý không đầy đủ. |
| MySQL InnoDB | `SELECT ... FOR UPDATE SKIP LOCKED` (MySQL 8.0+) | Dùng locking read; phạm vi lock phụ thuộc index, isolation level và access path. Cần kiểm tra gap/next-key locking và giới hạn câu lệnh. |
| Oracle | `SELECT ... FOR UPDATE SKIP LOCKED` | Thường dùng cho nhiều consumer lấy các hàng khác nhau; cú pháp cursor và giới hạn truy vấn phụ thuộc phiên bản. |
| SQL Server | `READPAST` kết hợp locking hints trong một số queue pattern | `READPAST` có hành vi và giới hạn riêng; có thể không bỏ qua page lock, phụ thuộc isolation level và cấu hình. Không phải cú pháp thay thế hoàn toàn tương đương. |

Ví dụ SQL trong bài chủ yếu dùng PostgreSQL. Khi triển khai trên MySQL, Oracle hoặc SQL Server, hãy kiểm tra tài liệu chính thức của phiên bản, isolation level, loại lock và kế hoạch thực thi. Đặc biệt, không thay `SKIP LOCKED` bằng một hint có tên gần giống rồi giả định semantics giống hệt.

## 12. Xây dựng worker loop có backoff

Một worker thường lặp lại quá trình claim, xử lý và hoàn tất. Khi không claim được việc, nó không nên quay vòng liên tục gây tải truy vấn vô ích.

```text
while worker_is_running:
    job = claim_one_job_with_skip_locked()

    if job is empty:
        wait_for_notification_or_backoff()
        continue

    try:
        process_idempotently(job)
        mark_done_if_lease_token_matches(job)
    catch retryable_error:
        schedule_retry_if_lease_token_matches(job)
    catch permanent_error:
        mark_failed_if_lease_token_matches(job)
```

Backoff có thể tăng dần đến một giới hạn và thêm jitter để nhiều worker không cùng thức dậy, truy vấn queue đúng một thời điểm. Nếu hệ thống có notification, worker có thể kết hợp notification với polling định kỳ vì notification không nên là nguồn sự thật duy nhất; worker có thể bỏ lỡ tín hiệu khi đang ngắt kết nối.

Khi claim trả về rỗng, worker có thể đợi ngắn rồi thử lại. Nó không nên kết luận queue đã hoàn tất cho đến khi có một giao thức kết thúc rõ ràng, ví dụ producer đã đóng queue, không còn job READY/RUNNING/RETRY và không có worker nào đang giữ lease hợp lệ.

## 13. Kiểm tra trạng thái queue mà không dùng SKIP LOCKED

Để quan sát số lượng công việc, hãy dùng truy vấn đọc thống kê phù hợp thay vì truy vấn claim:

```sql
SELECT status, count(*)
FROM job_queue
GROUP BY status
ORDER BY status;
```

Truy vấn này không thêm `SKIP LOCKED`, nên nó thống kê các hàng nhìn thấy theo snapshot/isolation level của câu lệnh. Trong hệ thống thay đổi liên tục, số liệu vẫn là ảnh chụp tại một thời điểm và có thể thay đổi ngay sau đó; nhưng nó không cố ý bỏ qua hàng chỉ vì worker đang khóa hàng đó.

Để xem công việc chờ lâu nhất:

```sql
SELECT job_id, priority, created_at, status, locked_by, locked_until
FROM job_queue
WHERE status IN ('READY', 'RUNNING')
ORDER BY created_at, job_id
LIMIT 50;
```

Đây là truy vấn giám sát. Nó có thể đọc các hàng mà worker đang khóa theo semantics đọc của DBMS, nhưng không claim hay thay đổi quyền sở hữu. Nếu cần một báo cáo kiểm toán nhất quán qua nhiều bảng hoặc nhiều câu lệnh, hãy chọn isolation level và transaction phù hợp với yêu cầu đó.

## 14. Những lỗi thiết kế thường gặp

- **Chọn rồi mới khóa:** hai worker cùng đọc một hàng trước khi đổi trạng thái. Hãy khóa và cập nhật trong cùng transaction/statement.
- **Giữ transaction trong lúc xử lý tác vụ dài:** row lock, connection và snapshot có thể bị giữ lâu. Claim, commit rồi xử lý với lease thường phù hợp hơn.
- **Không có lease hoặc cơ chế phục hồi:** worker chết sau khi claim khiến hàng mắc ở `RUNNING` mãi mãi.
- **Không kiểm tra token khi hoàn tất:** worker cũ có thể ghi đè kết quả của worker đã nhận lại lease.
- **Cho rằng SKIP LOCKED bảo đảm exactly-once:** crash giữa tác động ngoài và commit có thể khiến job được thực hiện lại; cần idempotency.
- **Coi kết quả rỗng là queue rỗng:** các hàng có thể đang bị khóa hoặc chưa đến thời điểm chạy.
- **Dùng SKIP LOCKED cho báo cáo:** kết quả cố ý bỏ qua hàng đang khóa nên không đầy đủ.
- **Cho rằng ORDER BY bảo đảm FIFO toàn cục:** hàng ưu tiên cao đang khóa có thể bị bỏ qua để worker tiến tới hàng thấp hơn.
- **Không theo dõi starvation:** một hàng có thể bị bỏ qua nhiều lượt hoặc lease liên tục hết hạn.
- **Dùng index không phù hợp:** worker phải quét nhiều hàng, làm tăng CPU/I/O và thời gian tìm hàng có thể claim.

## 15. Quy trình chọn SKIP LOCKED

Trước khi dùng `SKIP LOCKED`, hãy xác định rõ các điều kiện sau:

1. **Có phải đây là công việc phân phối cho consumer không?** Mỗi worker chỉ cần nhận một phần công việc có thể xử lý ngay, không cần xem toàn bộ queue trong một lượt.
2. **Hàng bị khóa có thể được bỏ qua tạm thời không?** Nếu thứ tự nghiêm ngặt hoặc kết quả đầy đủ là bắt buộc, `SKIP LOCKED` không đáp ứng trực tiếp yêu cầu.
3. **Việc claim có nguyên tử không?** Chọn, khóa và chuyển trạng thái phải nằm trong cùng transaction hoặc statement có semantics an toàn.
4. **Transaction có kết thúc sớm không?** Tránh giữ row lock trong suốt tác vụ dài nếu không thật sự cần.
5. **Có cơ chế phục hồi worker chết không?** Thiết kế lease, timeout, retry và trạng thái thất bại.
6. **Có chống tác động trùng lặp không?** Dùng idempotency key hoặc cơ chế tương đương cho thao tác có thể được giao lại.
7. **Có quan sát được queue không?** Theo dõi tuổi job, số lần thử, lease hết hạn, claim rỗng, throughput và thời gian chờ.
8. **Truy vấn có index phù hợp không?** Đo execution plan và lock contention dưới tải đồng thời.

## 16. Những điểm cần ghi nhớ

- `FOR UPDATE SKIP LOCKED` cho phép worker bỏ qua hàng đang bị khóa ở cấp hàng và claim hàng khác có thể lấy ngay.
- Chọn hàng, khóa và cập nhật trạng thái trong cùng transaction giúp tránh hai worker nhận cùng một hàng.
- Claim rồi commit nhanh, sau đó xử lý với lease thường tránh giữ transaction trong suốt tác vụ dài.
- Lease cần token hoặc fencing mechanism để worker cũ không ghi đè lần claim mới; thao tác bên ngoài vẫn cần idempotency.
- `SKIP LOCKED` không bảo đảm exactly-once, FIFO tuyệt đối, công bằng hoặc kết quả đầy đủ.
- Kết quả rỗng không chứng minh queue rỗng; các hàng thỏa điều kiện có thể đang bị worker khác khóa.
- Không dùng `SKIP LOCKED` cho báo cáo, đối soát, đếm chính xác hoặc kiểm tra cần toàn bộ hàng thỏa điều kiện.
- `ORDER BY` sắp xếp các hàng có thể claim trong lượt hiện tại; hàng ưu tiên cao đang khóa vẫn có thể bị bỏ qua.
- Hành vi cụ thể và cú pháp khác nhau giữa PostgreSQL, MySQL, Oracle và SQL Server; cần xác nhận theo DBMS đang triển khai.

`SKIP LOCKED` là công cụ điều phối cạnh tranh rất hữu ích khi mục tiêu là để nhiều worker lấy các công việc khác nhau mà không phải chờ cùng một hàng. Nó đạt được thông lượng đó bằng cách chấp nhận rằng mỗi lượt chỉ nhìn thấy phần hàng có thể khóa ngay. Khi yêu cầu nghiệp vụ cần một danh sách đầy đủ hoặc một kết luận chính xác trên toàn bộ tập dữ liệu, hãy dùng cơ chế đọc và cô lập phù hợp thay vì bỏ qua những hàng đang bị khóa.
