# SKIP LOCKED, tính công bằng và nguy cơ công việc bị bỏ qua lâu

Trong một hàng đợi công việc được lưu trong cơ sở dữ liệu, nhiều worker thường cùng tìm các hàng đang sẵn sàng để xử lý. `SKIP LOCKED` cho phép một worker bỏ qua hàng đang bị transaction khác khóa và tiếp tục nhận hàng khác có thể khóa ngay. Cách này giảm thời gian chờ giữa các worker và tăng thông lượng khi queue có nhiều công việc độc lập.

Đổi lại, `SKIP LOCKED` không bảo đảm mọi công việc được xử lý đúng thứ tự đến hoặc đúng thứ tự ưu tiên toàn cục. Một hàng cũ có thể bị bỏ qua qua nhiều lượt; hàng ưu tiên thấp hơn có thể được xử lý trước; một nhóm tenant có thể nhận nhiều worker hơn nhóm khác. Nếu không có chính sách lập lịch bổ sung, queue có thể đạt throughput cao nhưng vẫn thiếu tính công bằng.

Để hiểu giới hạn đó, cần tách hai việc: **khóa hàng để tránh nhiều worker claim cùng một công việc**, và **lập lịch để quyết định công việc hoặc nhóm công việc nào được phục vụ trước**. `SKIP LOCKED` hỗ trợ việc đầu tiên. Nó không tự xây dựng chính sách fairness cho việc thứ hai.

## 1. Cách SKIP LOCKED phân phối công việc

Giả sử bảng `job_queue` có các công việc đang ở trạng thái `READY`. Worker A khóa hàng đầu tiên để nhận việc. Trong lúc A còn giữ khóa, Worker B chạy truy vấn claim với `SKIP LOCKED`; B bỏ qua hàng đang bị A khóa và tìm hàng kế tiếp.

```text
Queue theo thứ tự ưu tiên:

job 101  priority 100  [đang bị Worker A khóa]
job 102  priority  80  [có thể khóa]
job 103  priority  60  [có thể khóa]

Worker A: khóa và claim job 101
Worker B: bỏ qua job 101, claim job 102
Worker C: bỏ qua các hàng đang khóa, có thể claim job 103
```

Worker B không cần chờ A hoàn tất job 101. Điều này hữu ích khi công việc độc lập và mục tiêu là giữ worker bận làm việc thay vì xếp hàng chờ cùng một hàng.

Trong PostgreSQL, locking read có thể viết như sau:

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

`FOR UPDATE` khóa những hàng được chọn. `SKIP LOCKED` khiến truy vấn bỏ qua xung đột khóa hàng thay vì chờ. Thứ tự `ORDER BY` sắp xếp các hàng mà truy vấn có thể lấy; nó không buộc worker phải chờ một hàng ưu tiên cao đang bị khóa.

### 1.1. Claim phải gắn với cập nhật trạng thái

Chọn hàng, khóa hàng và chuyển trạng thái cần nằm trong cùng transaction hoặc statement có tính nguyên tử. Nếu ứng dụng chỉ đọc `job_id`, commit hoặc kết thúc transaction, rồi mới cập nhật trạng thái ở một bước riêng, worker khác có thể nhận cùng công việc.

Một mẫu PostgreSQL dùng CTE và `UPDATE ... RETURNING`:

```sql
WITH candidate AS (
    SELECT job_id
    FROM job_queue
    WHERE queue_name = :queue_name
      AND status = 'READY'
      AND available_at <= clock_timestamp()
    ORDER BY priority DESC, created_at, job_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE job_queue AS j
SET status = 'RUNNING',
    claimed_by = :worker_id,
    claimed_at = clock_timestamp(),
    lease_until = clock_timestamp() + interval '2 minutes',
    lease_token = :lease_token,
    attempts = attempts + 1
FROM candidate AS c
WHERE j.job_id = c.job_id
RETURNING j.job_id, j.payload, j.lease_token, j.lease_until;
```

Worker commit ngay sau khi claim thành công:

```sql
BEGIN;

-- Chạy câu lệnh CTE UPDATE ở trên.

COMMIT;
```

Nếu `RETURNING` không trả hàng nào, lượt claim hiện tại không tìm được công việc có thể khóa theo điều kiện. Điều đó không chứng minh queue rỗng: các hàng phù hợp có thể đang bị worker khác khóa hoặc chưa đến `available_at`.

### 1.2. Khóa của database và quyền sở hữu công việc là hai thứ khác nhau

Row lock chỉ tồn tại trong thời gian transaction giữ nó. Khi transaction claim commit, row lock được giải phóng. Trạng thái `RUNNING`, lease và token mới thể hiện quyền xử lý mà worker đang sở hữu sau commit.

Vì vậy, một queue kiểu claim-then-process thường có hai giai đoạn:

1. Transaction ngắn khóa hàng, chuyển `READY` thành `RUNNING`, ghi worker/token/lease rồi commit.
2. Worker xử lý bên ngoài transaction; khi hoàn tất, mở transaction khác để ghi `DONE` nếu vẫn sở hữu đúng lease.

Không nên giữ transaction và row lock trong suốt một tác vụ dài chỉ để ngăn worker khác nhận hàng. Nếu worker bị treo trong khi connection vẫn mở, các worker khác có thể liên tục bỏ qua hàng đó. Lease có thời hạn giúp phục hồi công việc sau khi quyền claim cũ hết hạn.

## 2. SKIP LOCKED không bảo đảm FIFO nghiêm ngặt

FIFO (First In, First Out) nghĩa là công việc đến trước được xử lý trước. `SKIP LOCKED` chủ động cho phép worker bỏ qua hàng đầu nếu hàng đó đang bị khóa. Vì vậy, nó không thể đồng thời bảo đảm strict FIFO trên toàn queue.

Ví dụ:

```text
Thứ tự tạo:
  job 101  tạo lúc 09:00  [Worker A đang giữ khóa]
  job 102  tạo lúc 09:01  [có thể claim]
  job 103  tạo lúc 09:02  [có thể claim]

Worker B dùng SKIP LOCKED:
  bỏ qua job 101
  claim job 102

Worker C dùng SKIP LOCKED:
  có thể claim job 103
```

Job 102 và 103 có thể hoàn tất trước job 101 dù chúng đến sau. Đây là trade-off có chủ ý: hệ thống ưu tiên sử dụng worker hiệu quả hơn là chờ hàng đầu tiên.

### 2.1. ORDER BY chỉ sắp xếp ứng viên có thể lấy

Truy vấn:

```sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at, job_id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

ưu tiên hàng cũ trong số các hàng có thể khóa ở lượt truy vấn. Nếu một hàng cũ bị khóa, worker có thể lấy hàng mới hơn. `ORDER BY` không biến `SKIP LOCKED` thành một hàng đợi FIFO toàn cục.

Nếu yêu cầu nghiệp vụ bắt buộc công việc phải hoàn tất theo đúng thứ tự, chỉ sắp xếp khi claim là chưa đủ. Cần một dispatcher tuần tự, một cơ chế khóa đầu queue hoặc phân vùng theo khóa thứ tự. Những cách đó có thể giảm throughput và tạo điểm nóng, nên chỉ dùng khi thứ tự là yêu cầu thực sự.

### 2.2. Batch lớn có thể làm lệch cơ hội giữa worker

Worker claim 100 hàng mỗi lượt có thể giữ một lượng công việc lớn trong khi worker khác chỉ nhận được vài hàng. Nếu thời gian xử lý không đồng đều, một worker có thể bị quá tải còn các worker khác nhàn rỗi.

Batch nhỏ thường tăng số lượt điều phối nhưng phân phối công việc linh hoạt hơn. Batch lớn giảm round trip và có thể tăng hiệu suất với công việc ngắn, đồng đều. Cần đo thời gian xử lý và độ lệch tải trước khi chọn kích thước batch.

## 3. Fairness có nhiều phạm vi

Khi nói queue công bằng, cần xác định công bằng giữa những ai và trên tài nguyên nào. Ít nhất có ba phạm vi khác nhau:

- **Fairness giữa các hàng công việc:** job cũ hoặc job ưu tiên thấp có được cơ hội xử lý hay liên tục bị bỏ qua?
- **Fairness giữa các nhóm/tenant:** một tenant có chiếm phần lớn worker hoặc tài nguyên database khiến tenant khác phải chờ không?
- **Fairness giữa các worker:** một worker có nhận batch lớn và giữ phần lớn công việc, trong khi worker khác không có việc?

`SKIP LOCKED` chỉ điều chỉnh hành vi khi một hàng bị khóa. Nó không tự bảo đảm công bằng ở cả ba phạm vi. Chính sách lập lịch ở tầng ứng dụng phải quyết định thứ tự, quota, trọng số và mức độ song song.

### 3.1. Fairness của lock manager khác fairness của queue

Lock manager quản lý thứ tự cấp khóa trên một tài nguyên. Queue scheduler quản lý công việc nào được chọn để xử lý. Một lock manager có thể có quy tắc chống yêu cầu khóa bị bỏ đói, nhưng job vẫn có thể bị starvation vì worker liên tục bỏ qua nó bằng `SKIP LOCKED`.

Ngược lại, scheduler có thể chọn một job cũ trước, nhưng transaction claim vẫn phải chờ một row lock hoặc table lock. Khi điều tra, cần phân biệt job đang chờ được scheduler chọn với transaction đang chờ lock trong database.

## 4. Nguy cơ starvation: một công việc bị bỏ qua lâu

Starvation xảy ra khi một công việc liên tục không được phục vụ trong khi các công việc khác vẫn tiến triển. Với `SKIP LOCKED`, một job có thể bị bỏ qua vì:

- Nó đang bị worker khác khóa hoặc giữ lease.
- Worker sở hữu nó chạy quá lâu, gia hạn lease nhiều lần hoặc bị treo.
- Job ưu tiên thấp liên tục bị job ưu tiên cao mới vượt qua.
- Job thuộc tenant ít lưu lượng bị tenant khác chiếm phần lớn worker.
- Job liên tục hết lease, bị claim lại rồi thất bại.
- Job là “poison message” gây lỗi mỗi lần xử lý, khiến nó liên tục được retry mà không hoàn tất.

Thông lượng toàn queue vẫn có thể cao trong lúc một job cũ không tiến triển. Vì vậy, chỉ đo số job hoàn tất mỗi giây không đủ để kết luận hệ thống công bằng.

### 4.1. Hàng ưu tiên cao có thể làm đói hàng ưu tiên thấp

Giả sử worker luôn sắp xếp `priority DESC`. Nếu công việc ưu tiên cao liên tục đến, job ưu tiên thấp có thể không bao giờ lọt vào nhóm được claim.

```text
09:00  job L (priority 1) được tạo
09:01  job H1 (priority 10) được tạo và claim
09:02  job H2 (priority 10) được tạo và claim
09:03  job H3 (priority 10) được tạo và claim
09:04  job H4 (priority 10) được tạo và claim
...    job L tiếp tục chờ
```

Đây là starvation do chính sách ưu tiên. Nếu nghiệp vụ cho phép, có thể tăng dần ưu tiên của job theo thời gian chờ, dành một phần năng lực cho job cũ hoặc chia queue theo lớp ưu tiên.

### 4.2. Job bị khóa lâu có thể bị bỏ qua nhiều lượt

Nếu Worker A claim job 101 nhưng giữ transaction mở trong lúc xử lý tác vụ kéo dài, các worker khác sẽ bỏ qua job 101. Nếu A không kết thúc transaction vì bị treo hoặc chờ một dịch vụ ngoài, job có thể không được xử lý dù worker khác liên tục làm xong các job sau.

Giải pháp là claim trong transaction ngắn rồi commit, dùng lease có hạn, heartbeat để gia hạn khi cần, và phục hồi job hết lease. Khi worker mất quyền sở hữu, nó không được phép ghi đè kết quả của worker đã nhận lại job.

## 5. Lease, token và phục hồi job bị bỏ lại

Một lease là quyền xử lý có thời hạn. Khi worker claim job, nó ghi `lease_until`; nếu worker chết hoặc ngừng gia hạn, job có thể được claim lại sau khi lease hết hạn.

Ví dụ schema PostgreSQL:

```sql
CREATE TABLE job_queue (
    job_id       bigint PRIMARY KEY,
    queue_name   text NOT NULL,
    tenant_id    bigint,
    payload      jsonb NOT NULL,
    status       text NOT NULL,
    priority     integer NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now(),
    available_at timestamptz NOT NULL DEFAULT now(),
    claimed_by   text,
    claimed_at   timestamptz,
    lease_until  timestamptz,
    lease_token  uuid,
    attempts     integer NOT NULL DEFAULT 0,
    CONSTRAINT ck_job_status
        CHECK (status IN ('READY', 'RUNNING', 'DONE', 'FAILED'))
);
```

Claim mới hoặc nhận lại job hết lease:

```sql
WITH candidate AS (
    SELECT job_id
    FROM job_queue
    WHERE queue_name = :queue_name
      AND (
          (status = 'READY' AND available_at <= clock_timestamp())
          OR
          (status = 'RUNNING' AND lease_until < clock_timestamp())
      )
    ORDER BY priority DESC, created_at, job_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE job_queue AS j
SET status = 'RUNNING',
    claimed_by = :worker_id,
    claimed_at = clock_timestamp(),
    lease_until = clock_timestamp() + interval '2 minutes',
    lease_token = :new_token,
    attempts = attempts + 1
FROM candidate AS c
WHERE j.job_id = c.job_id
RETURNING j.job_id, j.payload, j.lease_token, j.lease_until;
```

Điều kiện nhận lại job hết lease là một chính sách cần cân nhắc. Nếu job cũ có thể vẫn đang chạy, worker mới có thể bắt đầu xử lý cùng công việc. Lease token giúp phân biệt lần claim, nhưng tác động ngoài database vẫn cần idempotency hoặc fencing token ở hệ thống đích.

### 5.1. Token ngăn worker cũ ghi đè lần claim mới

Giả sử A claim job với token `token-A`. Lease hết hạn, B claim lại job với token `token-B`. Sau đó A hoàn tất muộn và cố cập nhật trạng thái. Điều kiện theo `lease_token` ngăn A cập nhật hàng đã được B nhận lại:

```sql
UPDATE job_queue
SET status = 'DONE',
    claimed_by = NULL,
    lease_until = NULL
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND lease_token = :lease_token;
```

Worker phải kiểm tra số hàng được cập nhật. Nếu bằng 0, worker không còn sở hữu lease hiện tại và không được tự coi job đã hoàn tất trong queue.

Token ngẫu nhiên bảo vệ cập nhật trong database khi token đã bị thay thế. Nếu worker cũ có thể gửi lệnh đến một hệ thống bên ngoài, hệ thống đó cũng cần idempotency key hoặc fencing token tăng đơn điệu để từ chối lệnh từ owner cũ.

### 5.2. Heartbeat và thời hạn lease

Job dài có thể cần heartbeat để gia hạn lease:

```sql
UPDATE job_queue
SET lease_until = clock_timestamp() + interval '2 minutes'
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND lease_token = :lease_token;
```

Chỉ coi gia hạn thành công nếu đúng một hàng được cập nhật. Lease quá ngắn làm job bị nhận lại khi worker vẫn đang xử lý; lease quá dài làm phục hồi chậm khi worker thực sự chết.

Heartbeat không nên được dùng để giữ một job vô hạn khi worker không có tiến triển. Có thể đặt giới hạn tổng thời gian, số lần gia hạn hoặc kiểm tra tiến độ để phát hiện worker bị kẹt.

## 6. Các chiến lược cải thiện tính công bằng

Không có một chính sách duy nhất phù hợp cho mọi queue. Có thể kết hợp nhiều chiến lược tùy yêu cầu thứ tự, độ trễ và mức độ độc lập của công việc.

### 6.1. FIFO cho các công việc có cùng mức ưu tiên

Thêm `created_at` và một khóa phụ ổn định như `job_id` vào `ORDER BY`:

```sql
ORDER BY priority DESC, created_at, job_id
```

Điều này tạo thứ tự xác định giữa các job cùng priority trong số các hàng có thể claim. Tuy nhiên, do `SKIP LOCKED`, job cũ đang khóa vẫn có thể bị bỏ qua. Đây là FIFO best-effort, không phải FIFO nghiêm ngặt.

Nếu cần FIFO tuyệt đối, không được bỏ qua job đầu đang khóa. Có thể dùng dispatcher tuần tự hoặc khóa tài nguyên điều phối; cần chấp nhận một job đầu chậm có thể làm các job phía sau chờ theo.

### 6.2. Priority aging

Priority aging tăng ưu tiên của một job theo thời gian chờ để job cũ cuối cùng có cơ hội vượt lên.

Một công thức minh họa:

\[
effectivePriority = basePriority + \left\lfloor\frac{waitAge}{agingInterval}\right\rfloor
\]

Trong đó `waitAge` là thời gian từ lúc job sẵn sàng, không nhất thiết là thời gian từ lúc job được tạo. Job bị trì hoãn đến `available_at` chỉ bắt đầu tích lũy tuổi chờ sau thời điểm đó.

Có thể tính priority động trong truy vấn để minh họa:

```sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
  AND available_at <= clock_timestamp()
ORDER BY
    priority + floor(
        extract(epoch FROM (clock_timestamp() - available_at)) / 60
    ) DESC,
    created_at,
    job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

Đây là mẫu minh họa cho quy tắc aging, không phải kế hoạch tối ưu mặc định. Biểu thức động trong `ORDER BY` có thể khiến DBMS phải tính và sắp xếp nhiều ứng viên, khó tận dụng index theo thứ tự ưu tiên. Với queue lớn, có thể cập nhật `effective_priority` theo lịch, chia bucket theo tuổi, hoặc dùng scheduler riêng.

Nên giới hạn mức ưu tiên tối đa và xác định rõ job nào được aging. Nếu mọi job đều tăng không giới hạn, mức ưu tiên gốc có thể mất ý nghĩa.

### 6.3. Dành quota cho job cũ hoặc lớp ưu tiên thấp

Thay vì chỉ dùng một thứ tự ưu tiên, scheduler có thể dành một tỷ lệ worker cho các lớp khác nhau:

```text
Mỗi 10 lượt claim:
  6 lượt cho HIGH
  3 lượt cho NORMAL
  1 lượt cho LOW hoặc job đã chờ lâu
```

Quota bảo đảm lớp thấp vẫn có cơ hội được phục vụ khi lớp cao liên tục có việc. Tỷ lệ cần dựa trên SLO và năng lực thực tế. Nếu quota thấp hơn tốc độ job mới đến, hàng đợi lớp đó vẫn tiếp tục tăng.

### 6.4. Weighted fair queuing giữa tenant

Nếu nhiều tenant dùng chung queue, một tenant có lưu lượng lớn có thể chiếm phần lớn worker. Weighted fair queuing hoặc round-robin theo tenant giúp phân phối năng lực theo trọng số.

Ví dụ:

```text
Tenant A: weight 5
Tenant B: weight 3
Tenant C: weight 2

Một chu kỳ phân phối có thể cấp gần 5:3:2 lượt claim
cho A, B và C khi cả ba đều có công việc chờ.
```

Một cách triển khai đơn giản là scheduler chọn tenant tiếp theo dựa trên quota/deficit, rồi worker claim job trong queue của tenant đó bằng `SKIP LOCKED`. Cách này tách fairness giữa tenant khỏi tranh chấp hàng cụ thể.

Trọng số không nhất thiết phải bằng số job nếu chi phí xử lý khác nhau. Nếu một job của A tốn 10 phút còn một job của B tốn 10 ms, fairness theo số lượt claim có thể không công bằng theo CPU, thời gian worker hoặc chi phí database. Có thể dùng weighted deficit round-robin theo ước lượng chi phí.

### 6.5. Partition theo ordering key

Một số nghiệp vụ yêu cầu giữ thứ tự giữa các job cùng một đối tượng, ví dụ mọi sự kiện của cùng một tài khoản phải được xử lý tuần tự. Trong khi đó, các tài khoản khác nhau có thể xử lý song song.

Có thể phân vùng queue theo `account_id`, `tenant_id` hoặc một khóa logic. Trong mỗi partition, chỉ job đầu đủ điều kiện được claim; giữa các partition, worker dùng `SKIP LOCKED` để lấy việc từ partition sẵn sàng.

```text
Partition account 42: job A -> job B -> job C  (tuần tự)
Partition account 77: job D -> job E           (tuần tự)
Partition account 91: job F -> job G           (tuần tự)

Worker pool có thể xử lý đồng thời ba partition.
```

Điều này giữ thứ tự theo key mà không tuần tự hóa toàn bộ queue. Cần xác định rõ trạng thái nào được coi là “đang chặn job tiếp theo”, và bảo đảm mọi producer dùng cùng quy tắc partition.

## 7. Tính công bằng có thể xung đột với throughput

`SKIP LOCKED` tăng thông lượng vì worker không phải chờ hàng đang khóa. Nhưng việc bỏ qua hàng có thể làm lệch thứ tự. FIFO chặt hơn làm giảm bỏ qua, nhưng một job chậm ở đầu queue có thể gây head-of-line blocking.

| Chính sách | Ưu điểm | Đánh đổi |
|---|---|---|
| `SKIP LOCKED` với priority | Worker ít chờ, ưu tiên job sẵn sàng có điểm cao | Job đang khóa hoặc priority thấp có thể chờ lâu |
| FIFO nghiêm ngặt | Dễ dự đoán thứ tự, giảm bypass | Job đầu chậm có thể chặn cả queue |
| Priority aging | Job cũ dần được ưu tiên | Thứ tự thay đổi theo thời gian; query/index phức tạp hơn |
| Quota theo lớp | Mỗi lớp có cơ hội được phục vụ | Có thể để worker rảnh ở một lớp trong khi lớp khác còn việc nếu quota cứng |
| Weighted fair queuing | Phân bổ năng lực giữa tenant theo trọng số | Cần scheduler và ước lượng chi phí; triển khai phức tạp hơn |
| Partition theo key | Giữ thứ tự trong phạm vi nghiệp vụ, chạy song song giữa key | Một key nóng vẫn là điểm tuần tự hóa |

Không nên tối ưu chỉ theo số job/giây. Một queue có thể đạt throughput cao nhưng vi phạm SLO của job cũ hoặc tenant nhỏ. Cần đo cả độ trễ và độ công bằng.

## 8. Poison job và retry có thể làm một hàng bị kẹt lâu

Một job có payload lỗi, dữ liệu không còn hợp lệ hoặc handler luôn thất bại có thể được claim lại nhiều lần. Nếu job được đặt lại `READY` ngay sau mỗi lỗi, nó có thể chiếm lượt claim và tài nguyên worker lặp đi lặp lại.

Nên có chính sách retry riêng cho job:

- Tăng `attempts` khi claim hoặc khi ghi nhận lần xử lý thất bại theo quy ước nhất quán.
- Đặt `available_at` trong tương lai với backoff để job lỗi không lập tức quay lại đầu queue.
- Giới hạn số lần thử.
- Sau khi vượt ngưỡng, chuyển sang `FAILED` hoặc dead-letter queue để điều tra.
- Lưu `last_error`, thời điểm lỗi và worker xử lý nếu cần audit.
- Cho phép replay thủ công sau khi nguyên nhân đã được sửa.

Ví dụ lên lịch retry:

```sql
UPDATE job_queue
SET status = CASE
        WHEN attempts >= :max_attempts THEN 'FAILED'
        ELSE 'READY'
    END,
    available_at = clock_timestamp() + :retry_delay,
    claimed_by = NULL,
    lease_until = NULL,
    lease_token = NULL,
    last_error = :error_message
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND lease_token = :lease_token;
```

Trong hệ thống thật, trạng thái `FAILED` có thể được thay bằng `DEAD`, `RETRY` hoặc một bảng dead-letter riêng. Cần giữ lịch sử attempt nếu phục vụ audit hoặc phân tích lỗi.

## 9. Idempotency khi job được nhận lại

`SKIP LOCKED` ngăn hai worker cùng claim một hàng trong lúc lock đang được giữ. Nó không bảo đảm job chỉ được thực thi đúng một lần end-to-end.

Ví dụ:

1. Worker A claim job và commit trạng thái `RUNNING`.
2. A gửi yêu cầu thanh toán đến dịch vụ ngoài.
3. Dịch vụ thanh toán xử lý thành công.
4. A crash trước khi đánh dấu `DONE`.
5. Lease hết hạn; worker B claim lại job và gửi yêu cầu thanh toán lần nữa.

Database không thể rollback khoản thanh toán đã được dịch vụ bên ngoài chấp nhận. Queue kiểu này thường có semantics at-least-once; handler cần idempotent.

Các biện pháp:

- Dùng idempotency key ổn định theo `job_id` hoặc mã nghiệp vụ.
- Đặt unique constraint trên khóa chống lặp ở bảng ghi nhận kết quả.
- Dùng transactional outbox/inbox khi phối hợp database và message broker.
- Dùng fencing token tăng đơn điệu nếu hệ thống đích có thể từ chối lệnh từ worker cũ.
- Chỉ đánh dấu `DONE` khi worker vẫn sở hữu đúng lease token.

Fairness không nên được cải thiện bằng cách bỏ qua kiểm tra ownership. Worker cũ hoàn tất muộn không được ghi đè kết quả của worker mới; bảo vệ tính lũy đẳng và quyền sở hữu vẫn là yêu cầu độc lập.

## 10. Theo dõi công việc bị bỏ qua lâu

`SKIP LOCKED` không nhất thiết cung cấp trực tiếp một bộ đếm cho biết mỗi hàng đã bị bỏ qua bao nhiêu lần. Có thể theo dõi starvation bằng các chỉ số proxy và truy vấn giám sát không dùng `SKIP LOCKED`.

### 10.1. Tuổi job READY lâu nhất

```sql
SELECT
    queue_name,
    min(available_at) AS oldest_available_at,
    clock_timestamp() - min(available_at) AS oldest_ready_age,
    count(*) AS ready_count
FROM job_queue
WHERE status = 'READY'
  AND available_at <= clock_timestamp()
GROUP BY queue_name
ORDER BY oldest_ready_age DESC;
```

Tuổi job lớn trong khi `ready_count` vẫn cao có thể chỉ ra năng lực xử lý không đủ, ưu tiên không công bằng hoặc một nhóm job không được scheduler chọn. Truy vấn này không claim hàng và không cố ý bỏ qua row lock.

### 10.2. Job RUNNING có lease sắp hết hoặc đã quá hạn

```sql
SELECT
    job_id,
    queue_name,
    claimed_by,
    claimed_at,
    lease_until,
    attempts
FROM job_queue
WHERE status = 'RUNNING'
ORDER BY lease_until, claimed_at;
```

Các job có lease quá hạn cần được điều tra: worker có chết, heartbeat bị lỗi, thời gian xử lý vượt dự kiến hay job liên tục được nhận lại không?

### 10.3. Phân phối thời gian chờ theo tenant và priority

Đo queue wait từ `available_at` đến `claimed_at`, rồi tổng hợp p50/p95/p99 theo tenant, lớp ưu tiên và loại job. Nếu một tenant luôn có p99 cao hơn nhiều tenant khác, có thể scheduler đang phân bổ worker không cân bằng.

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa | Tín hiệu cần chú ý |
|---|---|---|
| Oldest READY age | Job sẵn sàng lâu nhất chưa được claim | Tuổi tăng liên tục trong khi queue vẫn có throughput |
| Queue wait p50/p95/p99 | Thời gian từ lúc sẵn sàng đến lúc claim | p99 tăng mạnh hoặc chênh lệch lớn giữa tenant |
| Completion share by tenant | Tỷ lệ công việc hoàn tất theo tenant | Một tenant chiếm phần lớn năng lực ngoài trọng số mong muốn |
| Attempts per job | Số lần claim/thử xử lý | Job có attempt cao bất thường hoặc poison job |
| Lease expiration count | Số lease hết hạn | Worker treo, lease quá ngắn hoặc tác vụ không ổn định |
| Empty claim with READY rows | Lượt claim không có kết quả dù còn job sẵn sàng | Nhiều hàng đang bị khóa hoặc điều kiện claim quá hẹp |
| Longest RUNNING age | Thời gian job ở RUNNING lâu nhất | Worker không hoàn tất hoặc heartbeat sai |
| Dead-letter count | Số job bị chuyển sang trạng thái cần điều tra | Handler lỗi kéo dài hoặc dữ liệu đầu vào không hợp lệ |

Một lượt claim trả rỗng không chứng minh queue rỗng. Nếu truy vấn giám sát cho thấy vẫn có job READY nhưng worker liên tục claim rỗng, có thể nhiều job đang bị khóa, chưa đến thời điểm chạy hoặc điều kiện queue/tenant không khớp.

## 11. Index và hiệu năng của truy vấn claim

Nhiều worker cùng tìm job có thể làm truy vấn claim tốn CPU/I/O nếu phải scan nhiều hàng rồi bỏ qua phần lớn vì bị khóa. Index phù hợp giúp định vị ứng viên nhanh hơn.

Ví dụ partial index trong PostgreSQL:

```sql
CREATE INDEX idx_job_queue_ready
ON job_queue (queue_name, priority DESC, created_at, job_id)
WHERE status = 'READY';
```

Index này hỗ trợ lọc queue và thứ tự ưu tiên cho hàng `READY`. Điều kiện `available_at <= clock_timestamp()` vẫn cần được đánh giá; tùy phân bố dữ liệu và kế hoạch, có thể cần thiết kế index khác hoặc chia nhóm delayed job.

Nếu query nhận lại job `RUNNING` hết lease, đó là một tập ứng viên khác và có thể cần index riêng, ví dụ trên `(queue_name, lease_until, job_id)` với predicate `status = 'RUNNING'`. Không nên gộp mọi trạng thái vào một index duy nhất mà chưa đo.

Hãy xem actual execution plan và đo:

- Số hàng/index entry phải xem trước khi tìm được batch.
- Tỷ lệ job READY thực sự có thể claim.
- Số worker cạnh tranh trên cùng queue.
- Thời gian claim và thời gian giữ transaction.
- Tần suất job bị bỏ qua lâu hoặc lease hết hạn.
- Chi phí duy trì index khi job chuyển từ READY sang RUNNING/DONE.

Index tốt giúp tìm ứng viên nhanh, nhưng không tự tạo fairness. Chính sách scheduler vẫn quyết định ai được phục vụ.

## 12. Tránh starvation mà không làm mất thứ tự nghiệp vụ

Một số hệ thống không thể tùy ý cho job sau vượt job trước. Ví dụ, các sự kiện cập nhật cùng tài khoản cần theo thứ tự. Nếu dùng `SKIP LOCKED` trên toàn queue, worker có thể bỏ qua một sự kiện cũ đang khóa và xử lý sự kiện sau trước, làm sai thứ tự nghiệp vụ.

Giải pháp là phân biệt:

- Công việc độc lập, có thể xử lý theo thứ tự gần đúng: `SKIP LOCKED` phù hợp.
- Công việc cần thứ tự theo một khóa logic: partition theo khóa, chỉ cho phép job đầu trong partition được claim.
- Công việc cần strict FIFO toàn cục: dùng dispatcher hoặc cơ chế tuần tự hóa đầu queue; chấp nhận head-of-line blocking.

Một thiết kế partition có thể cho phép nhiều account xử lý song song nhưng giữ thứ tự trong cùng account. Cần đảm bảo job tiếp theo trong partition không được claim khi job trước đang `RUNNING`, `RETRY` hoặc ở trạng thái chưa hoàn tất theo quy tắc nghiệp vụ.

## 13. Khi nào không nên dùng SKIP LOCKED?

Không dùng `SKIP LOCKED` khi truy vấn phải trả về toàn bộ hàng thỏa điều kiện hoặc phải chứng minh một điều kiện trên toàn bộ tập dữ liệu.

Ví dụ không phù hợp:

- Báo cáo đối soát cần tất cả giao dịch trong ngày.
- Truy vấn đếm chính xác số đơn đang chờ.
- Kiểm tra rằng không có reservation nào chồng lấn.
- Xuất danh sách đầy đủ mọi bản ghi theo tenant.
- Xử lý các sự kiện phải theo strict FIFO toàn cục.

`SKIP LOCKED` cố ý bỏ qua hàng đang bị khóa. Kết quả phụ thuộc trạng thái khóa tại thời điểm truy vấn và không phải một danh sách đầy đủ của mọi hàng thỏa predicate. Với báo cáo, hãy dùng semantics đọc nhất quán phù hợp. Với bất biến dữ liệu, dùng constraint, khóa phạm vi hoặc `SERIALIZABLE` theo DBMS.

## 14. Khác biệt giữa các DBMS

Không nên giả định mọi hệ quản trị có cùng semantics hoặc cú pháp:

| DBMS | Cơ chế thường gặp | Lưu ý |
|---|---|---|
| PostgreSQL | `FOR UPDATE SKIP LOCKED` | Bỏ qua xung đột khóa hàng; table lock vẫn theo quy tắc bình thường. Kết quả không đầy đủ theo chủ ý. |
| MySQL InnoDB | `SELECT ... FOR UPDATE SKIP LOCKED` ở các phiên bản hỗ trợ | Phạm vi lock phụ thuộc index, isolation level và access path; kiểm tra gap/next-key lock. |
| Oracle | `SELECT ... FOR UPDATE SKIP LOCKED` | Hữu ích cho nhiều consumer; cú pháp cursor và giới hạn phụ thuộc phiên bản. |
| SQL Server | `READPAST` kết hợp locking hints trong một số queue pattern | `READPAST` có giới hạn và không tương đương hoàn toàn `SKIP LOCKED`; có thể không bỏ qua page lock. |

Các ví dụ SQL trong bài chủ yếu dùng PostgreSQL. Khi triển khai, cần kiểm tra tài liệu đúng phiên bản DBMS và isolation level. Không thay một hint bằng tên gần giống rồi mặc định rằng nó có cùng bảo đảm về fairness hoặc phạm vi khóa.

## 15. Quy trình thiết kế queue có fairness

Trước khi triển khai, hãy xác định rõ các yêu cầu:

1. **Công việc có độc lập không?** Nếu các job có thể chạy theo thứ tự bất kỳ, `SKIP LOCKED` có thể phù hợp. Nếu cần thứ tự theo key, hãy partition.
2. **Fairness áp dụng cho ai?** Job, tenant, worker, priority class hay ordering key?
3. **Có cần strict FIFO không?** Nếu có, `SKIP LOCKED` sẽ làm mất bảo đảm đó khi bỏ qua hàng đầu đang khóa.
4. **Có giới hạn thời gian sở hữu không?** Thiết kế lease, heartbeat và reclaim.
5. **Worker cũ có thể ghi đè worker mới không?** Dùng lease token/fencing và kiểm tra ownership khi hoàn tất.
6. **Job lỗi có chiếm queue không?** Dùng backoff, max attempts và dead-letter.
7. **Job cũ có được tăng ưu tiên không?** Cân nhắc aging hoặc quota cho lớp thấp.
8. **Tenant lớn có lấn át tenant nhỏ không?** Dùng weighted fair queuing hoặc quota theo tenant.
9. **Có quan sát được starvation không?** Theo dõi oldest READY age, queue wait percentiles, lease expiration và completion share.
10. **Thứ tự nghiệp vụ có được giữ không?** Kiểm thử nhiều worker trên cùng ordering key và các key khác nhau.

## 16. Ví dụ chính sách tổng hợp

Giả sử một hệ thống có nhiều tenant, mỗi tenant có queue riêng về mặt logic. Yêu cầu là:

- Công việc độc lập trong cùng tenant có thể chạy song song.
- Tenant lớn không được chiếm toàn bộ worker.
- Job chờ lâu dần được tăng ưu tiên.
- Job đang xử lý có lease; worker chết thì job có thể được nhận lại.
- Các sự kiện cùng `account_id` phải giữ thứ tự.

Một thiết kế có thể gồm:

1. Scheduler chọn tenant theo weighted round-robin hoặc deficit round-robin.
2. Trong tenant đã chọn, query dùng `SKIP LOCKED` để claim một job có thể xử lý.
3. Effective priority tăng theo tuổi chờ để job cũ không bị đói bởi job mới.
4. Job được phân partition theo `account_id`; chỉ job đầu chưa hoàn tất trong partition được claim.
5. Claim transaction ngắn, cập nhật `RUNNING`, lease và token rồi commit.
6. Worker xử lý bên ngoài transaction; heartbeat gia hạn lease khi còn tiến triển.
7. Khi hoàn tất, worker cập nhật `DONE` với điều kiện token vẫn khớp.
8. Khi lỗi tạm thời, job được lên lịch `READY` lại với backoff; lỗi vĩnh viễn hoặc vượt retry limit chuyển sang dead-letter.
9. Dashboard theo dõi oldest job age và queue wait p95/p99 theo tenant, priority và partition.

Thiết kế này kết hợp throughput từ `SKIP LOCKED` với fairness ở scheduler. Các quy tắc quota, aging và partition phải được điều chỉnh theo tải thật; không có cấu hình chung phù hợp mọi workload.

## 17. Những điểm cần ghi nhớ

- `SKIP LOCKED` tăng khả năng worker tiếp tục khi hàng đầu đang bị khóa, nhưng không bảo đảm FIFO hoặc priority toàn cục.
- `ORDER BY` sắp xếp ứng viên có thể claim; job cũ đang khóa có thể bị bỏ qua để job mới được xử lý trước.
- Fairness giữa job, tenant và worker là các vấn đề riêng; cần chính sách scheduler ngoài locking clause.
- Starvation có thể xảy ra khi job ưu tiên thấp, job cũ hoặc tenant ít lưu lượng liên tục bị bỏ qua.
- Claim trong transaction ngắn, dùng lease và token để phục hồi job bị bỏ lại và ngăn worker cũ ghi đè lần claim mới.
- Priority aging, quota theo lớp, weighted fair queuing và partition theo ordering key giúp cân bằng cơ hội xử lý.
- FIFO nghiêm ngặt có thể gây head-of-line blocking; throughput cao có thể yêu cầu chấp nhận bỏ qua hàng đang khóa.
- Poison job cần backoff, giới hạn attempt và dead-letter để không chiếm lượt xử lý liên tục.
- `SKIP LOCKED` không bảo đảm exactly-once; job được giao lại cần idempotency và có thể cần fencing token cho tác động bên ngoài.
- Theo dõi oldest READY age, queue wait p95/p99, lease expiration, attempts per job và completion share theo tenant để phát hiện bất công mà throughput che khuất.
- Không dùng `SKIP LOCKED` cho báo cáo hoặc kiểm tra cần tập kết quả đầy đủ.

`SKIP LOCKED` là công cụ phân phối công việc hiệu quả khi các job có thể được xử lý độc lập và worker nên tiếp tục làm việc thay vì chờ một hàng đang khóa. Để tránh công việc bị bỏ qua lâu, cần bổ sung chính sách fairness phù hợp với thứ tự nghiệp vụ, tenant và mức ưu tiên; đồng thời theo dõi tuổi job, lease và kết quả xử lý. Thông lượng chỉ là một phần của chất lượng queue: mọi công việc hợp lệ cũng cần có cơ hội tiến triển trong giới hạn thời gian mà nghiệp vụ yêu cầu.
