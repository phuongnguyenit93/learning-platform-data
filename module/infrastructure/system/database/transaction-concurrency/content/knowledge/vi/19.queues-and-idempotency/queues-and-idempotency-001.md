# Nhận công việc trong cơ sở dữ liệu mà không giao trùng đồng thời

Khi nhiều worker cùng đọc một hàng đợi trong cơ sở dữ liệu, chúng có thể nhìn thấy cùng một công việc đang chờ và cùng bắt đầu xử lý nó. Nếu mỗi worker chỉ chạy `SELECT` rồi mới `UPDATE`, hai worker có thể cùng chọn một hàng trước khi một bên kịp đánh dấu đã nhận. Kết quả là công việc bị giao trùng, dẫn đến gửi email hai lần, trừ tồn kho hai lần hoặc tạo ra các tác dụng phụ không mong muốn.

Để tránh giao trùng đồng thời, thao tác chọn và nhận quyền xử lý phải được phối hợp nguyên tử tại cơ sở dữ liệu. Worker cần claim (nhận quyền xử lý) một nhóm công việc trong transaction ngắn, ghi rõ chủ sở hữu và thời hạn claim, rồi commit trước khi thực hiện phần việc dài. Những worker khác phải bỏ qua hoặc thất bại khi cố nhận cùng hàng.

Điều này ngăn hai worker cùng sở hữu một claim đang còn hiệu lực. Nó không tự bảo đảm một công việc chỉ được thực thi đúng một lần trong mọi tình huống: worker có thể chết sau khi thực hiện tác dụng phụ nhưng trước khi đánh dấu hoàn tất. Vì vậy, hàng đợi thường cần giao ít nhất một lần (at-least-once), kết hợp idempotency, lease và fencing token để xử lý retry an toàn.

## 1. Vấn đề khi chỉ SELECT rồi UPDATE

Giả sử bảng hàng đợi có các cột cơ bản:

```sql
CREATE TABLE job_queue (
    job_id BIGINT PRIMARY KEY,
    job_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

Hai worker cùng chạy cách làm ngây thơ:

```sql
-- Worker A
SELECT job_id, payload
FROM job_queue
WHERE status = 'PENDING'
ORDER BY job_id
FETCH FIRST 1 ROW ONLY;

-- Worker B cũng chạy cùng SELECT trước khi A cập nhật.
```

Một lịch xen kẽ có thể xảy ra:

| Thời điểm | Worker A | Worker B |
|---|---|---|
| 1 | Đọc job 101, thấy `PENDING` | |
| 2 | | Đọc job 101, cũng thấy `PENDING` |
| 3 | Cập nhật job 101 thành `PROCESSING` | |
| 4 | | Cập nhật job 101 thành `PROCESSING` |
| 5 | Bắt đầu xử lý job 101 | Bắt đầu xử lý job 101 |

Hai worker đã nhận cùng một công việc. Việc cập nhật trạng thái sau lần đọc không đủ để ngăn race condition, bởi cả hai quyết định dựa trên cùng trạng thái cũ.

Quy tắc cần đạt là: chỉ một worker có thể chuyển một hàng từ `PENDING` sang trạng thái đã claim thành công. Việc kiểm tra điều kiện và cập nhật trạng thái phải diễn ra trong một thao tác nguyên tử hoặc trong một transaction có khóa phù hợp.

## 2. Mô hình trạng thái của công việc

Một hàng đợi thường có các trạng thái như sau:

```text
PENDING
   |
   | Worker claim thành công
   v
PROCESSING
   |       \
   |        \ Lease hết hạn / worker mất quyền sở hữu
   |         v
   |       PENDING hoặc RETRY
   |
   +----> DONE
   |
   +----> RETRY ----> PENDING
   |
   +----> FAILED / DEAD_LETTER
```

Ý nghĩa thường gặp:

- `PENDING`: công việc sẵn sàng được nhận.
- `PROCESSING`: một worker đang giữ claim còn hiệu lực.
- `DONE`: công việc đã hoàn tất và kết quả được ghi nhận.
- `RETRY`: công việc thất bại tạm thời và sẽ được thử lại sau.
- `FAILED` hoặc `DEAD_LETTER`: công việc đã vượt giới hạn retry hoặc gặp lỗi không thể tự phục hồi.

Ngoài `status`, nên lưu thông tin claim:

| Cột | Mục đích |
|---|---|
| `claimed_by` | ID worker đang sở hữu claim. |
| `claimed_at` | Thời điểm worker nhận công việc. |
| `lease_until` | Thời điểm claim hết hạn nếu không được gia hạn. |
| `claim_generation` | Số thế hệ claim tăng sau mỗi lần nhận lại, dùng làm fencing token. |
| `attempt_count` | Số lần đã thử xử lý. |
| `available_at` | Thời điểm sớm nhất công việc được phép nhận. |
| `last_error` | Thông tin lỗi gần nhất để chẩn đoán. |

Ví dụ cấu trúc mở rộng:

```sql
CREATE TABLE job_queue (
    job_id BIGINT PRIMARY KEY,
    job_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    available_at TIMESTAMP NOT NULL,
    claimed_by VARCHAR(100),
    claimed_at TIMESTAMP,
    lease_until TIMESTAMP,
    claim_generation BIGINT NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);
```

Các kiểu thời gian và cú pháp DDL cần điều chỉnh theo hệ quản trị. Nếu nhiều worker chạy trên nhiều máy, nên dùng thời gian từ database làm cơ sở cho `lease_until` để tránh lệch đồng hồ giữa các máy.

## 3. Claim phải là một thao tác nguyên tử

Có hai chiến lược phổ biến:

1. Khóa các hàng được chọn trong transaction, bỏ qua hàng đã bị worker khác khóa, cập nhật chủ sở hữu rồi commit.
2. Dùng câu `UPDATE` có điều kiện như compare-and-swap; worker chỉ thắng nếu trạng thái vẫn còn là `PENDING` tại thời điểm cập nhật.

Không được để khoảng trống không được bảo vệ giữa lúc chọn hàng và lúc nhận quyền. Nếu worker chọn ID, commit, rồi mới cập nhật trạng thái trong transaction khác, worker khác vẫn có thể chọn cùng ID.

## 4. Dùng `FOR UPDATE SKIP LOCKED`

Các hệ quản trị hỗ trợ `SKIP LOCKED` cho phép worker bỏ qua những hàng đang bị transaction khác khóa, thay vì chờ chúng. Đây là cơ chế hữu ích cho hàng đợi vì worker có thể tiếp tục nhận công việc khác.

Một mẫu PostgreSQL minh họa dùng CTE để chọn và cập nhật trong cùng câu lệnh:

```sql
WITH picked AS (
    SELECT job_id
    FROM job_queue
    WHERE status = 'PENDING'
      AND available_at <= CURRENT_TIMESTAMP
    ORDER BY available_at, job_id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE job_queue AS j
SET status = 'PROCESSING',
    claimed_by = :worker_id,
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    claim_generation = j.claim_generation + 1,
    attempt_count = j.attempt_count + 1
FROM picked
WHERE j.job_id = picked.job_id
RETURNING j.job_id, j.job_type, j.payload,
          j.claim_generation, j.lease_until;
```

Câu lệnh phải chạy trong transaction và được commit ngay sau khi claim. Các hàng được chọn bị khóa trong lúc transaction claim mở; worker khác dùng `SKIP LOCKED` sẽ bỏ qua chúng. Câu `UPDATE` đánh dấu trạng thái và tăng `claim_generation` trước khi transaction kết thúc.

Một luồng tổng quát:

```text
Worker A                         Worker B
   |                                |
   | BEGIN                          | BEGIN
   | SELECT ... FOR UPDATE          | SELECT ... FOR UPDATE
   | SKIP LOCKED                    | SKIP LOCKED
   | khóa job 101                   | bỏ qua job 101
   |                                | nhận job 102
   | UPDATE job 101                 | UPDATE job 102
   | COMMIT                         | COMMIT
   |                                |
   v                                v
 Xử lý job 101                  Xử lý job 102
```

Điều quan trọng là commit ngay sau khi ghi claim. Nếu worker giữ transaction mở trong suốt thời gian gọi API hoặc xử lý payload, nó sẽ giữ khóa quá lâu và làm giảm lợi ích của hàng đợi.

`SKIP LOCKED` tạo một view không nhất quán theo nghĩa thông thường vì nó bỏ qua hàng đang khóa. Điều này phù hợp với việc phân phối công việc, nhưng không phù hợp cho báo cáo cần đọc đầy đủ tập dữ liệu hoặc nghiệp vụ yêu cầu FIFO tuyệt đối.

## 5. Mẫu tương ứng trên MySQL InnoDB

MySQL 8 với InnoDB hỗ trợ locking read cùng `SKIP LOCKED`. Một cách triển khai gồm chọn hàng và cập nhật trong cùng transaction:

```sql
START TRANSACTION;

SELECT job_id
FROM job_queue
WHERE status = 'PENDING'
  AND available_at <= CURRENT_TIMESTAMP
ORDER BY available_at, job_id
LIMIT :batch_size
FOR UPDATE SKIP LOCKED;

UPDATE job_queue
SET status = 'PROCESSING',
    claimed_by = :worker_id,
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = CURRENT_TIMESTAMP + INTERVAL 2 MINUTE,
    claim_generation = claim_generation + 1,
    attempt_count = attempt_count + 1
WHERE job_id IN (:selected_job_ids)
  AND status = 'PENDING';

COMMIT;
```

Ứng dụng phải giữ danh sách ID được chọn trong cùng transaction, thực hiện update trước commit và chỉ xử lý sau khi commit thành công. `FOR UPDATE SKIP LOCKED` yêu cầu transaction và engine hỗ trợ locking read; không áp dụng tương tự cho mọi storage engine hoặc phiên bản cũ.

Điều kiện `AND status = 'PENDING'` trong câu update là lớp bảo vệ bổ sung. Ứng dụng cũng cần xác nhận số hàng được cập nhật đúng bằng số hàng đã claim; nếu không, phải xử lý theo trạng thái thực tế thay vì giả định toàn bộ lô đã được nhận.

## 6. Mẫu trên SQL Server với `UPDLOCK` và `READPAST`

SQL Server có thể dùng các lock hint để phối hợp worker:

```sql
;WITH picked AS (
    SELECT TOP (@batch_size) *
    FROM dbo.job_queue WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE status = 'PENDING'
      AND available_at <= SYSUTCDATETIME()
    ORDER BY available_at, job_id
)
UPDATE picked
SET status = 'PROCESSING',
    claimed_by = @worker_id,
    claimed_at = SYSUTCDATETIME(),
    lease_until = DATEADD(MINUTE, 2, SYSUTCDATETIME()),
    claim_generation = claim_generation + 1,
    attempt_count = attempt_count + 1
OUTPUT inserted.job_id, inserted.job_type, inserted.payload,
       inserted.claim_generation, inserted.lease_until;
```

`UPDLOCK` yêu cầu update lock khi đọc để giảm khả năng hai worker cùng chọn một hàng; `READPAST` cho phép bỏ qua một số khóa đang chặn; `ROWLOCK` là gợi ý về mức khóa, không phải cam kết tuyệt đối rằng engine luôn chỉ khóa từng hàng. Hành vi còn phụ thuộc isolation level, cấu hình `READ_COMMITTED_SNAPSHOT`, kiểu khóa và phiên bản SQL Server.

Không sao chép nguyên xi cú pháp giữa PostgreSQL, MySQL và SQL Server. Hãy dùng cú pháp đúng với DBMS, kiểm tra lock hint có hiệu lực trong isolation level đang chạy và xác nhận bằng thử nghiệm nhiều connection.

## 7. Compare-and-swap khi không có SKIP LOCKED

Nếu không có `SKIP LOCKED`, một cách an toàn là dùng `UPDATE` có điều kiện để tranh quyền claim. Ví dụ, worker đã có một `job_id` ứng viên:

```sql
UPDATE job_queue
SET status = 'PROCESSING',
    claimed_by = :worker_id,
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = :lease_until,
    claim_generation = claim_generation + 1,
    attempt_count = attempt_count + 1
WHERE job_id = :job_id
  AND status = 'PENDING'
  AND available_at <= CURRENT_TIMESTAMP;
```

Chỉ worker làm cho câu lệnh cập nhật đúng một hàng mới nhận được claim. Worker khác cập nhật cùng ID sẽ thấy số hàng bị ảnh hưởng bằng 0 vì trạng thái không còn `PENDING`.

Mẫu này bảo vệ quyền nhận một ID cụ thể. Tuy nhiên, việc tìm ID ứng viên vẫn cần thiết kế phù hợp. Nếu nhiều worker cùng chọn một ID rồi một worker thắng CAS, worker thua phải thử ID khác hoặc lấy lại danh sách ứng viên. Không được coi kết quả `SELECT` trước đó là quyền sở hữu công việc.

Nếu DBMS hỗ trợ `UPDATE ... RETURNING` hoặc `OUTPUT`, hãy lấy thông tin công việc từ chính thao tác cập nhật thành công để tránh một lần đọc khác có thể thấy trạng thái thay đổi. Nếu không, đọc lại hàng sau khi claim bằng token/chủ sở hữu đã ghi.

## 8. Vì sao transaction claim phải ngắn?

Transaction claim chỉ nên làm những việc cần thiết để chuyển quyền sở hữu:

1. Chọn hàng đủ điều kiện.
2. Khóa hoặc cập nhật có điều kiện.
3. Ghi worker, lease và claim token.
4. Commit.

Sau đó mới xử lý payload, gọi dịch vụ ngoài hoặc thực hiện tính toán lâu. Nếu giữ transaction mở trong suốt quá trình xử lý, worker sẽ giữ khóa trên các hàng queue và có thể chặn worker khác, tác vụ quản trị hoặc quy trình thu hồi lease.

Không nên dùng một transaction dài như sau:

```text
BEGIN
  SELECT ... FOR UPDATE SKIP LOCKED
  gọi dịch vụ HTTP mất 30 giây
  xử lý file
  ghi nhiều bảng
  UPDATE job_queue SET status = 'DONE'
COMMIT
```

Mẫu này giữ khóa queue suốt thời gian xử lý và làm cho việc worker chết trở nên tốn kém: database phải đợi session timeout hoặc rollback trước khi giải phóng khóa. Thay vào đó, commit claim nhanh rồi mở transaction riêng để ghi kết quả.

Nếu cập nhật kết quả và trạng thái `DONE` cần cùng thành công, hãy ghi chúng trong cùng transaction cuối cùng. Claim transaction và transaction hoàn tất là hai đơn vị ngắn riêng biệt, nối với nhau bằng claim token.

## 9. Lease để thu hồi công việc khi worker bị dừng

Worker có thể bị crash, mất mạng hoặc bị terminate sau khi claim. Nếu hàng cứ ở `PROCESSING` mãi, công việc sẽ không bao giờ được nhận lại.

Lease là thời hạn của claim. Khi `lease_until` đã qua, công việc có thể đủ điều kiện để worker khác nhận lại:

```sql
WHERE status = 'PROCESSING'
  AND lease_until < CURRENT_TIMESTAMP
```

Một quy trình thu hồi có thể chuyển công việc hết lease về `PENDING`, hoặc claim trực tiếp hàng hết lease thành worker mới. Việc chuyển trạng thái và tăng `claim_generation` cần nguyên tử để hai worker thu hồi không cùng thắng.

Lease nên dài hơn thời gian xử lý thông thường hoặc được gia hạn định kỳ. Nếu quá ngắn, worker vẫn làm việc bình thường nhưng lease hết hạn, khiến worker khác nhận lại cùng công việc. Nếu quá dài, công việc của worker đã chết phải chờ lâu mới được phục hồi.

Worker gia hạn lease bằng điều kiện sở hữu:

```sql
UPDATE job_queue
SET lease_until = :new_lease_until
WHERE job_id = :job_id
  AND status = 'PROCESSING'
  AND claimed_by = :worker_id
  AND claim_generation = :claim_generation;
```

Nếu số hàng bị ảnh hưởng bằng 0, worker không còn sở hữu claim hiện tại. Nó phải dừng hoặc không ghi kết quả như chủ sở hữu hợp lệ.

## 10. Fencing token ngăn worker cũ ghi đè worker mới

Chỉ dùng `claimed_by` và `lease_until` có thể chưa đủ. Hãy xét tình huống:

1. Worker A claim job 101 với lease đến 10:02.
2. A bị treo hoặc xử lý quá lâu.
3. Lease hết hạn; worker B claim lại job 101.
4. B hoàn tất công việc.
5. A hoạt động trở lại và cố ghi kết quả cũ.

Nếu chỉ kiểm tra `job_id` hoặc trạng thái `PROCESSING`, A có thể ghi đè kết quả của B. Cần một fencing token tăng đơn điệu theo mỗi lần claim. Ví dụ `claim_generation` tăng từ 4 lên 5 khi B nhận lại. Mọi thao tác gia hạn hoặc hoàn tất phải gửi token đã nhận:

```sql
UPDATE job_queue
SET status = 'DONE',
    completed_at = CURRENT_TIMESTAMP,
    result_payload = :result
WHERE job_id = :job_id
  AND status = 'PROCESSING'
  AND claimed_by = :worker_id
  AND claim_generation = :claim_generation;
```

Worker A mang generation 4 không thể cập nhật hàng đang ở generation 5. Đây là fencing: token mới hơn làm mất hiệu lực quyền của worker cũ.

Nếu worker ghi vào một hệ thống bên ngoài, chỉ kiểm tra token ở bảng queue chưa chắc ngăn tác dụng phụ bên ngoài. Hệ thống đích cũng cần hỗ trợ idempotency key hoặc kiểm tra fencing token, hoặc ứng dụng phải thiết kế thao tác ngoài sao cho chạy lại an toàn.

## 11. Không nhầm claim duy nhất với thực thi đúng một lần

Claim nguyên tử có thể bảo đảm tại một thời điểm chỉ một worker giữ quyền sở hữu hợp lệ của một job. Nhưng không thể tự bảo đảm mọi tác dụng phụ xảy ra đúng một lần trong môi trường có crash và retry.

Ví dụ:

1. Worker A claim job gửi email.
2. A gửi email thành công.
3. A chết trước khi cập nhật job thành `DONE`.
4. Lease hết hạn và B claim lại job.
5. B gửi email lần nữa.

Email đã được gửi hai lần dù không có hai worker cùng claim trong cùng thời điểm. Đây là khác biệt giữa:

- **Single active claim:** không có hai worker cùng giữ claim còn hiệu lực theo giao thức.
- **At-least-once processing:** công việc có thể được giao lại sau lỗi và được thực thi nhiều lần.
- **Exactly-once effect:** tác dụng phụ chỉ xuất hiện một lần; điều này cần idempotency hoặc một giao thức giao dịch chung với hệ thống đích, không chỉ cần khóa hàng queue.

Đối với tác dụng phụ có thể lặp, dùng idempotency key ổn định, thường là `job_id` hoặc một operation ID riêng. Hệ thống nhận tác dụng phụ phải lưu key và từ chối xử lý trùng.

Nếu kết quả chỉ được ghi vào cùng database, có thể đặt cập nhật dữ liệu nghiệp vụ và chuyển job sang `DONE` trong cùng transaction. Khi transaction rollback, cả kết quả và trạng thái hoàn tất cùng rollback; khi commit, cả hai cùng tồn tại.

## 12. Tạo công việc không trùng bằng khóa duy nhất

Một nguồn gây trùng khác là producer tạo cùng một công việc nhiều lần. Ví dụ, một sự kiện thanh toán được phát lại và tạo hai job gửi hóa đơn. Claim không giải quyết trùng lặp ở bước tạo job.

Có thể lưu một khóa chống trùng (deduplication key):

```sql
CREATE TABLE job_queue (
    job_id BIGINT PRIMARY KEY,
    deduplication_key VARCHAR(200) NOT NULL UNIQUE,
    job_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL
);
```

Producer ghi job với một key ổn định đại diện cho công việc nghiệp vụ. Unique constraint khiến hai lần tạo cùng key không thể cùng tồn tại. Ứng dụng xử lý xung đột bằng cách tìm job đã có và trả lại kết quả phù hợp.

Key cần đại diện đúng một đơn vị công việc. Nếu key quá rộng, hai công việc hợp lệ có thể bị gộp nhầm; nếu key không ổn định, cùng một công việc có thể được tạo nhiều lần.

## 13. Index và thứ tự chọn job

Truy vấn claim thường lọc theo trạng thái và thời điểm sẵn sàng, sau đó sắp xếp theo ưu tiên hoặc thời gian tạo. Index phù hợp giúp giảm số hàng phải quét và giảm thời gian giữ khóa.

Ví dụ, một index có thể bắt đầu bằng các cột thường dùng trong điều kiện lọc và tiếp tục bằng thứ tự chọn:

```sql
CREATE INDEX ix_job_queue_pending
ON job_queue (status, available_at, job_id);
```

Đây chỉ là gợi ý ban đầu. Một số hệ quản trị hỗ trợ filtered/partial index cho `status = 'PENDING'`; một số hệ thống có nhiều trạng thái và cần index khác. Hãy kiểm tra execution plan trên dữ liệu thực tế.

Nếu có ưu tiên:

```sql
ORDER BY priority DESC, available_at, job_id
```

cần cân nhắc index theo thứ tự phù hợp. Nếu job có thể liên tục được thêm với ưu tiên cao, job ưu tiên thấp có thể bị đói (starvation). Có thể cần aging — tăng ưu tiên theo thời gian chờ — hoặc phân vùng hàng đợi theo loại công việc.

`SKIP LOCKED` cũng có thể bỏ qua một job cũ đang bị khóa liên tục. Nó ưu tiên tiến độ của worker hơn thứ tự FIFO tuyệt đối. Nếu thứ tự là yêu cầu nghiệp vụ, cần một cơ chế tuần tự hóa hoặc phân vùng phù hợp thay vì mặc định dùng skip-locked.

## 14. Xử lý lỗi, retry và dead-letter queue

Không phải lỗi nào cũng nên retry vô hạn. Phân loại lỗi:

- Lỗi tạm thời: timeout mạng, dịch vụ ngoài không sẵn sàng, deadlock hoặc serialization failure.
- Lỗi dữ liệu/validation: payload sai, thiếu trường bắt buộc, tham chiếu không tồn tại.
- Lỗi không thể phục hồi tự động: vượt số lần thử, dữ liệu không hợp lệ kéo dài hoặc lỗi logic cần can thiệp.

Khi lỗi tạm thời, cập nhật `attempt_count`, đặt `available_at` trong tương lai theo backoff và chuyển về `RETRY` hoặc `PENDING`. Khi vượt ngưỡng, chuyển sang `DEAD_LETTER` để điều tra.

Không giữ transaction mở trong khi chờ backoff. Ghi trạng thái retry và thời điểm thử lại trong transaction ngắn, commit rồi để worker lấy lại sau.

## 15. Kiểm thử hai worker nhận việc đồng thời

Kiểm thử phải dùng nhiều connection hoặc process thực sự chạy đồng thời. Một kịch bản cơ bản:

1. Tạo một job ở trạng thái `PENDING`.
2. Cho worker A và B cùng bắt đầu claim tại một barrier.
3. Cả hai chạy câu claim trong transaction riêng.
4. Commit cả hai transaction.
5. Xác nhận chỉ một worker nhận được `job_id` đó; worker còn lại nhận job khác hoặc không nhận được hàng nào.
6. Kiểm tra `claimed_by`, `claim_generation` và `lease_until` của hàng.

Kiểm thử tiếp các trường hợp:

- Nhiều job và nhiều worker claim các batch đồng thời; không có cùng `job_id` trong hai claim đang hiệu lực.
- Worker chết sau claim nhưng trước xử lý; job được nhận lại sau khi lease hết hạn.
- Worker cũ tiếp tục sau khi job đã được claim lại; fencing token ngăn nó hoàn tất.
- Worker chết sau tác dụng phụ nhưng trước khi đánh dấu `DONE`; idempotency ngăn tác dụng phụ trùng.
- Hai producer tạo cùng deduplication key; unique constraint giữ một job logic.
- Job bị lỗi liên tục được chuyển sang dead-letter theo giới hạn retry.
- Hàng bị khóa lâu không làm worker khác chờ vô hạn; chính sách skip, timeout và fairness hoạt động như mong muốn.

Một truy vấn kiểm tra claim hiện hành có thể nhóm theo `job_id` và tìm những hàng có nhiều chủ sở hữu trong log claim. Bảng queue hiện tại chỉ lưu một chủ sở hữu nên không thể một mình chứng minh lịch sử chưa từng giao trùng; cần event log hoặc bảng claim history nếu yêu cầu audit.

## 16. Theo dõi hàng đợi trong vận hành

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa |
|---|---|
| Pending count | Số job đang chờ. |
| Oldest pending age | Tuổi của job chờ lâu nhất; phát hiện starvation hoặc worker thiếu năng lực. |
| Active claims | Số job đang ở `PROCESSING` với lease còn hiệu lực. |
| Expired leases | Số job có claim đã hết hạn nhưng chưa được thu hồi. |
| Claim conflicts | Số lần CAS thất bại hoặc worker không lấy được hàng. |
| Retry/dead-letter count | Mức độ lỗi và công việc cần can thiệp. |
| Processing duration | Thời gian xử lý p50/p95/p99. |
| Duplicate side-effect signals | Dấu hiệu idempotency bị thiếu hoặc lỗi. |
| Lock wait/deadlock | Tác động của truy vấn claim lên cơ sở dữ liệu. |

Không chỉ nhìn số job `PROCESSING`: một hàng có thể ở trạng thái đó nhưng lease đã hết hạn hoặc worker đã chết. Trạng thái và thời hạn claim cần được quan sát cùng nhau.

## 17. Quy trình nhận và xử lý job an toàn

Một luồng xử lý thực tế có thể gồm:

1. Worker mở transaction ngắn để chọn một batch đủ điều kiện bằng `SKIP LOCKED`, lock hint phù hợp hoặc CAS.
2. Trong cùng transaction, cập nhật trạng thái `PROCESSING`, worker ID, claim generation, lease và attempt count.
3. Commit claim và chỉ xử lý các job mà thao tác claim xác nhận thành công.
4. Thực hiện công việc ngoài transaction claim; gia hạn lease nếu cần bằng điều kiện worker và generation còn khớp.
5. Mở transaction ngắn để kiểm tra fencing token, ghi kết quả nghiệp vụ và chuyển job sang `DONE`.
6. Nếu có tác dụng phụ ngoài database, dùng idempotency key và outbox hoặc cơ chế tương đương.
7. Nếu lỗi tạm thời, ghi retry time và commit; nếu lỗi không thể phục hồi, chuyển dead-letter.
8. Nếu worker chết, worker khác thu hồi job hết lease bằng một thao tác claim nguyên tử và tăng generation.

## 18. Checklist trước khi chạy nhiều worker

- [ ] Chọn và cập nhật quyền sở hữu job trong cùng transaction hoặc một câu lệnh nguyên tử.
- [ ] Không dùng kết quả `SELECT` đơn thuần làm bằng chứng đã claim.
- [ ] Dùng `SKIP LOCKED`, lock hint hoặc compare-and-swap đúng với DBMS.
- [ ] Commit claim nhanh trước khi xử lý payload dài hoặc gọi dịch vụ ngoài.
- [ ] Ghi worker ID, lease và claim generation cho mỗi lần nhận.
- [ ] Gia hạn lease và hoàn tất job bằng điều kiện owner/token còn khớp.
- [ ] Dùng fencing token để worker cũ không ghi đè worker mới.
- [ ] Có cơ chế thu hồi claim khi worker chết hoặc lease hết hạn.
- [ ] Có idempotency cho tác dụng phụ có thể được thực hiện lại.
- [ ] Có unique deduplication key nếu producer có thể phát lại cùng công việc.
- [ ] Có retry giới hạn, backoff và dead-letter queue.
- [ ] Có index phù hợp, theo dõi lock wait, starvation và tuổi job chờ.
- [ ] Đã kiểm thử nhiều worker, worker crash, lease expiry và stale worker.

Để không giao trùng công việc cho nhiều worker, quyền nhận phải được quyết định nguyên tử ở cơ sở dữ liệu. `SKIP LOCKED` giúp các worker lấy những hàng khác nhau mà không chờ nhau; compare-and-swap là lựa chọn khi cần tranh quyền trên một ID. Claim transaction nên ngắn, có lease và fencing token để thu hồi an toàn. Vì worker có thể chết ở bất kỳ thời điểm nào, hãy thiết kế xử lý theo hướng có thể giao lại, với idempotency bảo vệ tác dụng phụ và unique key ngăn producer tạo trùng công việc.
