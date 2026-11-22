# Kiểm thử worker hết thời hạn xử lý và quay lại sau khi mất quyền

Trong một hàng đợi công việc dùng database, worker thường nhận một job bằng cách ghi nhận quyền sở hữu có thời hạn (lease). Worker xử lý job sau khi transaction claim đã commit. Nếu worker bị treo, mất kết nối hoặc xử lý lâu hơn dự kiến, lease có thể hết hạn. Một worker khác được phép nhận lại job và tiếp tục xử lý.

Tình huống khó nhất xuất hiện khi worker cũ quay lại sau khi job đã được worker mới nhận. Worker cũ có thể vẫn chạy trong bộ nhớ, chưa biết lease của mình đã hết hạn, và cố ghi kết quả hoặc gửi tác động ra hệ thống bên ngoài. Nếu không có cơ chế fencing, hai worker có thể cùng tác động lên một job, hoặc worker cũ ghi đè trạng thái của worker mới.

Bài thực hành này kiểm chứng vòng đời đó bằng hai worker A và B: A claim job, lease hết hạn, B claim lại, sau đó A quay lại và thử heartbeat, hoàn tất hoặc phát tác động. Ta sẽ kiểm tra database từ chối thao tác của owner cũ như thế nào, và vì sao kiểm tra token trong database vẫn chưa đủ để bảo vệ một hệ thống bên ngoài không biết token đó.

## 1. Phân biệt lease, row lock và quyền sở hữu

Ba khái niệm này thường bị nhầm lẫn:

- **Row lock:** khóa do database giữ trong transaction. Nó được giải phóng khi transaction commit/rollback hoặc kết thúc theo quy tắc DBMS.
- **Lease:** quyền xử lý được lưu trong dữ liệu với thời điểm hết hạn. Lease tồn tại qua nhiều transaction và cho phép phục hồi job khi worker không còn hoạt động.
- **Ownership token/fencing token:** thông tin nhận diện lần claim hiện tại. Nó giúp database hoặc hệ thống đích phân biệt worker cũ với worker mới.

Một worker không nên giữ transaction và row lock trong toàn bộ thời gian xử lý job dài. Thay vào đó, worker mở transaction ngắn để claim, ghi owner và lease rồi commit. Sau đó worker xử lý bên ngoài transaction. Khi xong, worker mở transaction mới và chỉ được cập nhật job nếu lease vẫn còn thuộc về lần claim của mình.

```text
Worker A                         Database                         Worker B
--------                         --------                         --------
Claim job ----------------------> status=RUNNING
                                  owner=A, generation=1
                                  lease_until=T1
COMMIT
Xử lý bên ngoài transaction
                                 lease hết hạn
                                                                  Claim lại job
                                  owner=B, generation=2 <---------
                                                                  COMMIT
Worker A quay lại
Complete với generation=1 -----> Bị từ chối: owner đã đổi
                                                                  Complete gen=2
```

Row lock giúp hai transaction claim không cùng sửa hàng tại một thời điểm. Lease quyết định khi nào job có thể được nhận lại. Token/generation bảo vệ các thao tác đến muộn của worker đã mất quyền.

## 2. Mô hình dữ liệu cho bài lab

Ví dụ dưới đây dùng PostgreSQL. Một hàng job lưu trạng thái, owner, thời điểm hết lease, token nhận diện lần claim và generation tăng dần.

```sql
CREATE TABLE job_lease_lab (
    job_id           bigint PRIMARY KEY,
    payload          jsonb NOT NULL,
    status           text NOT NULL,
    priority         integer NOT NULL DEFAULT 0,
    available_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease_owner      text,
    lease_until      timestamptz,
    lease_token      uuid,
    lease_generation bigint NOT NULL DEFAULT 0,
    attempts         integer NOT NULL DEFAULT 0,
    completed_at     timestamptz,
    CONSTRAINT ck_job_lease_status
        CHECK (status IN ('READY', 'RUNNING', 'DONE', 'FAILED')),
    CONSTRAINT ck_job_lease_fields
        CHECK (
            (status = 'RUNNING'
             AND lease_owner IS NOT NULL
             AND lease_until IS NOT NULL
             AND lease_token IS NOT NULL)
            OR
            (status <> 'RUNNING'
             AND lease_owner IS NULL
             AND lease_until IS NULL
             AND lease_token IS NULL)
        )
);

INSERT INTO job_lease_lab(job_id, payload, status, priority)
VALUES (1, '{"task":"generate-report"}', 'READY', 10);
```

Trong bài lab, `lease_token` là UUID mới do worker tạo cho mỗi lần claim. `lease_generation` là số tăng đơn điệu theo từng job. Hai giá trị có mục đích khác nhau:

- UUID token nhận diện đúng lần claim và được dùng trong điều kiện `UPDATE` của database.
- Generation là fencing token tăng dần. Hệ thống đích có thể so sánh generation để từ chối lệnh đến muộn từ owner cũ.

Có thể dùng một generation duy nhất cho cả kiểm tra database và downstream nếu mô hình phù hợp. Bài lab giữ cả hai để minh họa rõ sự khác nhau giữa token nhận diện và fencing token có thứ tự.

### 2.1. Dùng đồng hồ database làm nguồn thời gian

Lease được so sánh giữa nhiều worker và database. Nếu mỗi worker dùng đồng hồ máy riêng, lệch giờ có thể khiến worker nghĩ lease còn hiệu lực trong khi database đã coi nó hết hạn, hoặc ngược lại.

Trong ví dụ PostgreSQL, thời điểm lease được tạo và kiểm tra bằng `clock_timestamp()` của database. Không dùng timestamp local của worker để quyết định quyền sở hữu cuối cùng. Worker có thể dùng đồng hồ monotonic để đo thời lượng xử lý, nhưng quyết định claim/renew/complete phải được database xác nhận.

`now()` trong PostgreSQL trả về thời điểm bắt đầu transaction, nên nếu transaction kéo dài thì giá trị không thay đổi trong transaction đó. Với phép kiểm tra lease cần thời gian thực tại thời điểm đánh giá, `clock_timestamp()` thường phù hợp hơn. Dù vậy, transaction claim/complete vẫn nên ngắn.

## 3. Câu lệnh claim có lease và generation

Worker tìm một job sẵn sàng hoặc một job `RUNNING` đã hết lease. CTE khóa ứng viên bằng `FOR UPDATE SKIP LOCKED`, sau đó `UPDATE` trạng thái và tăng generation trong cùng statement.

```sql
WITH candidate AS (
    SELECT job_id
    FROM job_lease_lab
    WHERE (status = 'READY'
           AND available_at <= clock_timestamp())
       OR (status = 'RUNNING'
           AND lease_until <= clock_timestamp())
    ORDER BY priority DESC, available_at, job_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE job_lease_lab AS j
SET status = 'RUNNING',
    lease_owner = :worker_id,
    lease_until = clock_timestamp() + :lease_duration,
    lease_token = :new_lease_token,
    lease_generation = j.lease_generation + 1,
    attempts = j.attempts + 1,
    completed_at = NULL
FROM candidate AS c
WHERE j.job_id = c.job_id
RETURNING j.job_id,
          j.payload,
          j.lease_owner,
          j.lease_until,
          j.lease_token,
          j.lease_generation,
          j.attempts;
```

`:lease_duration` trong ví dụ là tham số có kiểu `interval`, còn `:new_lease_token` là UUID mới. Tên placeholder cần được điều chỉnh theo driver/ORM.

Mỗi worker thực hiện claim trong transaction ngắn:

```sql
BEGIN;

-- Chạy statement claim ở trên.

COMMIT;
```

Nếu không có hàng trả về, worker không claim được job ở lượt đó. Sau commit, row lock được giải phóng; quyền sở hữu được biểu diễn bằng các cột `lease_owner`, `lease_until`, `lease_token` và `lease_generation`.

### 3.1. Vì sao phải tăng generation khi claim lại?

Giả sử A claim lần đầu, generation bằng 1. Lease hết hạn, B claim lại và generation thành 2. Bất kỳ lệnh nào mang generation 1 đều cũ hơn lần claim hiện tại.

```text
Lần claim 1: owner=A, generation=1, token=token-A
Lần claim 2: owner=B, generation=2, token=token-B
Lần claim 3: owner=C, generation=3, token=token-C
```

Generation không được đặt lại về 1 khi job quay lại `READY`; nó phải tiếp tục tăng. Nếu reset generation, một worker cũ có thể mang giá trị trùng với một lần claim mới và fencing mất tác dụng.

## 4. Quyền gia hạn lease (heartbeat)

Worker đang xử lý có thể gửi heartbeat để gia hạn lease. Heartbeat phải xác nhận đúng owner, token và generation hiện tại; đồng thời lease chưa hết hạn tại thời điểm database kiểm tra.

```sql
UPDATE job_lease_lab
SET lease_until = clock_timestamp() + :lease_duration
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND lease_owner = :worker_id
  AND lease_token = :lease_token
  AND lease_generation = :lease_generation
  AND lease_until > clock_timestamp();
```

Worker chỉ được coi heartbeat thành công nếu `row_count = 1`. Nếu cập nhật 0 hàng, worker đã mất quyền, lease hết hạn hoặc token/generation không còn khớp. Worker cần dừng tác vụ nếu có thể, không tiếp tục gia hạn bằng cách bỏ điều kiện ownership.

Điều kiện `lease_until > clock_timestamp()` thể hiện chính sách nghiêm ngặt: ngay khi lease hết hạn, worker cũ mất quyền, kể cả khi chưa có worker khác claim lại. Nếu hệ thống muốn có grace period, phải thiết kế rõ thời điểm và quy tắc; không được để mỗi worker tự suy diễn.

### 4.1. Heartbeat không chứng minh công việc đang tiến triển

Một worker bị kẹt nhưng vẫn gửi heartbeat có thể giữ lease vô hạn. Heartbeat chỉ chứng minh worker còn có thể gửi thông điệp gia hạn; nó không chứng minh business operation đang tiến triển.

Có thể kết hợp heartbeat với:

- Thời điểm tiến triển gần nhất hoặc checkpoint.
- Giới hạn tổng thời gian xử lý.
- Số lần gia hạn tối đa.
- Health check của worker và dependency.
- Cơ chế hủy tác vụ khi mất lease.

Không đặt lease quá ngắn khiến worker bình thường liên tục mất quyền; cũng không đặt quá dài khiến phục hồi worker chết bị trì hoãn. Chọn thời lượng dựa trên phân phối thời gian xử lý và khả năng gia hạn.

## 5. Hoàn tất job phải kiểm tra quyền sở hữu hiện tại

Khi xử lý xong, worker cập nhật `DONE` bằng một câu lệnh có điều kiện theo owner, token, generation và lease còn hiệu lực.

```sql
UPDATE job_lease_lab
SET status = 'DONE',
    completed_at = clock_timestamp(),
    lease_owner = NULL,
    lease_until = NULL,
    lease_token = NULL
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND lease_owner = :worker_id
  AND lease_token = :lease_token
  AND lease_generation = :lease_generation
  AND lease_until > clock_timestamp();
```

Nếu row count là 1, worker đã hoàn tất job khi vẫn còn quyền. Nếu là 0, worker không còn là owner hợp lệ. Không được bỏ điều kiện token hoặc generation chỉ để “cho phép job hoàn tất”.

Điều kiện lease còn hạn giúp xử lý cả trường hợp A quay lại sau khi lease hết hạn nhưng trước khi B claim lại. Theo chính sách nghiêm ngặt, A vẫn không được hoàn tất sau thời điểm hết lease.

### 5.1. Vì sao không chỉ kiểm tra lease trong code worker?

Một kiểm tra ở phía worker như:

```text
if local_clock < my_lease_until:
    mark_job_done()
```

không an toàn. Sau khi worker kiểm tra, lease có thể hết hạn hoặc B có thể claim lại trước khi câu `UPDATE` của A chạy. Đây là race condition giữa check và use.

Quyền sở hữu phải được kiểm tra nguyên tử trong chính câu lệnh database ghi kết quả. Worker có thể dùng local check để dừng sớm, nhưng database là nơi xác nhận cuối cùng.

## 6. Thực hành hai worker: A claim, lease hết hạn, B claim lại

Bài lab dùng hai session database độc lập. Có thể chạy trên hai tab SQL client hoặc hai connection riêng trong test harness.

### Bước 1 — Reset dữ liệu

Chạy ngoài các transaction đang mở:

```sql
DELETE FROM job_lease_lab WHERE job_id = 1;

INSERT INTO job_lease_lab(job_id, payload, status, priority)
VALUES (1, '{"task":"generate-report"}', 'READY', 10);
```

### Bước 2 — Worker A claim job

Session A:

```sql
BEGIN;

-- Chạy claim statement với:
-- worker_id       = 'worker-A'
-- new_lease_token = UUID A
-- lease_duration  = interval '30 seconds'

COMMIT;
```

Ghi lại kết quả trả về, ví dụ:

```text
job_id           = 1
lease_owner      = worker-A
lease_generation = 1
lease_token      = token-A
lease_until      = thời điểm T1
```

Worker A bắt đầu xử lý nhưng bị tạm dừng, mất mạng hoặc process bị pause lâu hơn 30 giây. Không giữ transaction mở trong thời gian chờ này.

### Bước 3 — Làm lease hết hạn một cách xác định

Để test không phải `sleep` 30 giây, dùng câu lệnh fixture mô phỏng lease đã hết hạn. Chỉ chạy trong database lab:

```sql
UPDATE job_lease_lab
SET lease_until = clock_timestamp() - interval '1 second'
WHERE job_id = 1
  AND lease_owner = 'worker-A'
  AND lease_generation = 1;
```

Đây là thao tác điều khiển thời gian cho bài test. Không dùng câu lệnh này trong logic production để cưỡng ép lease hết hạn.

### Bước 4 — Worker B nhận lại job

Session B chạy claim statement với:

```text
worker_id       = worker-B
new_lease_token = token-B (UUID mới)
lease_duration  = interval '30 seconds'
```

Kết quả kỳ vọng:

```text
job_id           = 1
lease_owner      = worker-B
lease_generation = 2
lease_token      = token-B
lease_until      = thời điểm T2, lớn hơn thời điểm hiện tại
```

B đã nhận quyền xử lý mới. Generation tăng từ 1 lên 2; token A đã bị thay thế.

### Bước 5 — Worker A quay lại và thử hoàn tất

Session A chạy câu `UPDATE ... SET status = 'DONE'` ở phần trước với các giá trị cũ:

```text
worker_id       = worker-A
lease_token     = token-A
lease_generation = 1
```

Kết quả mong đợi là `row_count = 0`. A không còn owner, token và generation hiện tại. Trạng thái job vẫn là `RUNNING` do B sở hữu.

### Bước 6 — Worker A thử heartbeat muộn

Chạy heartbeat với token A và generation 1. Kết quả cũng phải là 0 hàng được cập nhật. A không được gia hạn lease đã mất.

### Bước 7 — Worker B hoàn tất

B chạy câu complete với token B và generation 2. Nếu lease vẫn còn hạn, câu lệnh cập nhật đúng một hàng và chuyển job sang `DONE`.

### Bước 8 — Xác nhận trạng thái cuối

```sql
SELECT job_id,
       status,
       lease_owner,
       lease_until,
       lease_token,
       lease_generation,
       attempts,
       completed_at
FROM job_lease_lab
WHERE job_id = 1;
```

Kết quả cuối mong đợi: `status = 'DONE'`, các trường owner/lease/token được xóa, generation vẫn là 2 và attempts phản ánh hai lần claim. A không thể ghi đè kết quả B.

## 7. Thực hành tình huống worker cũ quay lại trước khi B claim

Một race quan trọng khác: lease A đã hết hạn nhưng B chưa claim lại. Worker A quay lại và cố hoàn tất.

Với điều kiện `lease_until > clock_timestamp()` trong câu complete, A vẫn bị từ chối vì lease đã hết hạn. Đây là chính sách strict lease: quyền tự động hết khi đến hạn.

Thí nghiệm:

1. Reset job và để A claim generation 1.
2. Đặt `lease_until` về thời điểm quá khứ.
3. Chưa cho B claim.
4. A chạy complete với token/generation cũ.
5. Xác nhận row count bằng 0.
6. Cho B claim lại và nhận generation 2.

Điều này cho thấy kiểm tra generation/token mà không kiểm tra thời hạn vẫn có thể cho phép A hoàn tất sau khi lease đã hết hạn nếu B chưa thay token. Nếu yêu cầu là lease hết hạn đồng nghĩa mất quyền ngay lập tức, phải kiểm tra cả expiry trong câu lệnh ghi.

Một số hệ thống chọn semantics khác: owner cũ được phép hoàn tất nếu chưa có owner mới nhận lại. Nếu chọn cách đó, câu lệnh complete chỉ kiểm tra token hiện tại, không kiểm tra expiry; khi ấy lease hết hạn chỉ có nghĩa “được phép reclaim”, không có nghĩa “owner cũ lập tức mất quyền”. Hai chính sách đều có thể thiết kế được, nhưng phải chọn rõ và kiểm thử nhất quán. Bài lab này dùng strict lease.

## 8. Kiểm thử race tại thời điểm hết hạn

Tại ranh giới expiry, A có thể cố complete trong lúc B cố reclaim. Cả hai cùng cập nhật một hàng job nên database tuần tự hóa thao tác ghi trên hàng đó. Điều kiện `WHERE` được đánh giá khi statement thực hiện; kết quả phụ thuộc transaction nào lấy được quyền cập nhật và lease còn hiệu lực hay không.

Với strict lease:

- Nếu A complete trước khi hết hạn và câu lệnh cập nhật thành công, trạng thái chuyển `DONE`; B không còn điều kiện để reclaim.
- Nếu lease đã hết hạn trước khi A complete được chấp nhận, điều kiện expiry làm A cập nhật 0 hàng.
- Nếu B reclaim thành công trước, generation/token đổi; A cập nhật 0 hàng ngay cả khi A vẫn nghĩ mình đang chạy.

```text
                 Lease A hết hạn
                       |
            +----------+----------+
            |                     |
      A complete trước       B reclaim trước
      expiry và thành công    sau expiry
            |                     |
       status = DONE          owner=B, gen=2
       B không claim          A stale update = 0
```

Để kiểm thử race, dùng hai connection và barrier để bắt đầu complete/reclaim gần nhau. Lặp nhiều lần với các điểm thời gian khác nhau. Không kết luận chỉ từ một lần chạy vì lịch CPU và lock scheduling có thể thay đổi.

## 9. Fencing token bảo vệ tài nguyên bên ngoài

Điều kiện `WHERE lease_token = :token` bảo vệ hàng job trong database. Nhưng nó không ngăn A tiếp tục gọi một dịch vụ bên ngoài sau khi mất lease. Ví dụ A có thể đã gửi lệnh ghi file, trừ tiền hoặc cập nhật thiết bị trước khi quay lại database để đánh dấu `DONE`.

Một **fencing token** là số tăng đơn điệu theo mỗi lần cấp quyền. Hệ thống đích lưu generation lớn nhất đã chấp nhận và từ chối lệnh có generation nhỏ hơn.

Ví dụ:

```text
Worker A được cấp generation 1
Worker B được cấp generation 2

Downstream nhận lệnh từ B, generation 2
  -> lưu highest_generation = 2

Downstream nhận lệnh muộn từ A, generation 1
  -> từ chối vì 1 < 2
```

Một bảng tài nguyên ở hệ thống đích có thể lưu `last_fencing_token`:

```sql
UPDATE protected_resource
SET value = :new_value,
    last_fencing_token = :generation
WHERE resource_id = :resource_id
  AND last_fencing_token < :generation;
```

Ví dụ này minh họa nguyên tắc. Nếu cần cho phép nhiều thao tác của cùng một generation, điều kiện có thể là `last_fencing_token <= :generation` kết hợp operation sequence/idempotency key; nếu mỗi generation chỉ được áp dụng một lần, cần thêm unique constraint hoặc bảng deduplication.

Fencing chỉ hiệu quả nếu **hệ thống đích thực sự kiểm tra token**. Gửi generation trong payload nhưng downstream bỏ qua nó không tạo ra bảo vệ.

### 9.1. Lease token ngẫu nhiên và fencing token tăng dần khác nhau

UUID token dùng để xác nhận một lần claim cụ thể, nhưng không có thứ tự. Downstream không thể kết luận token UUID nào mới hơn.

Generation số nguyên tăng dần có thứ tự, nên downstream có thể từ chối generation cũ. Cần bảo đảm generation không bị reset hoặc tái sử dụng khi job được tạo lại; nếu ID job có thể tái sử dụng, fencing scope nên bao gồm một resource/job epoch duy nhất.

### 9.2. Fencing không thay thế idempotency

Fencing ngăn owner cũ ghi sau owner mới. Idempotency ngăn cùng một thao tác nghiệp vụ tạo tác động lặp. Hai cơ chế giải quyết hai vấn đề khác nhau.

Ví dụ, B có generation 2 nhưng gửi cùng một lệnh thanh toán hai lần do timeout. Fencing token 2 vẫn hợp lệ cho cả hai lần; nếu downstream không có idempotency key, thanh toán có thể bị thực hiện hai lần. Cần dùng cả generation và operation idempotency key khi nghiệp vụ yêu cầu.

## 10. Outbox và xử lý tác động ngoài database

Không nên thực hiện tác động ngoài database rồi mới hy vọng cập nhật `DONE` thành công. A có thể mất lease sau khi downstream đã nhận tác động nhưng trước khi database xác nhận hoàn tất.

Một cách phối hợp là ghi kết quả hoặc sự kiện vào outbox trong cùng transaction với việc hoàn tất job, với điều kiện ownership vẫn hợp lệ:

```sql
BEGIN;

WITH completed AS (
    UPDATE job_lease_lab
    SET status = 'DONE',
        completed_at = clock_timestamp(),
        lease_owner = NULL,
        lease_until = NULL,
        lease_token = NULL
    WHERE job_id = :job_id
      AND status = 'RUNNING'
      AND lease_owner = :worker_id
      AND lease_token = :lease_token
      AND lease_generation = :lease_generation
      AND lease_until > clock_timestamp()
    RETURNING job_id, lease_generation
)
INSERT INTO outbox(event_key, payload)
SELECT :event_key, :event_payload
FROM completed;

COMMIT;
```

Nếu CTE `completed` không trả hàng, outbox không nhận event. Như vậy worker mất lease không thể ghi một sự kiện hoàn tất giả trong cùng transaction.

Outbox dispatcher có thể gửi event nhiều lần nếu mất phản hồi sau khi downstream đã nhận. Consumer cần idempotency/deduplication. Outbox bảo đảm database ghi nhận ý định phát event cùng với trạng thái job; nó không tự bảo đảm exactly-once qua mạng.

## 11. Kiểm thử worker chết, pause và partition mạng

Không phải mọi sự cố đều giống nhau. Cần kiểm thử các kiểu worker mất khả năng giao tiếp khác nhau:

| Tình huống | Điều xảy ra | Điều cần xác nhận |
|---|---|---|
| Process crash | Worker dừng hoàn toàn | Lease hết hạn và worker khác có thể claim |
| Process pause dài | Worker không chạy nhưng sau đó tiếp tục | Worker cũ không được ghi khi đã mất quyền |
| Network partition | Worker không liên lạc được database nhưng vẫn chạy logic cục bộ | Khi kết nối lại, token/generation cũ bị từ chối |
| Database connection timeout | Worker không biết statement/commit đã hoàn tất chưa | Tra cứu ownership/idempotency trước khi gửi lại tác động |
| Downstream timeout | Không biết hệ thống đích đã nhận lệnh chưa | Dùng idempotency key và fencing ở downstream |
| Heartbeat bị trễ | Lease hết hạn dù tác vụ vẫn tiến triển | Worker dừng hoặc nhận lại quyền theo giao thức, không tự giả định còn lease |
| Clock skew ở worker | Đồng hồ local khác database | Quyết định expiry dựa trên clock database |

Để mô phỏng process pause, test harness có thể chặn A sau khi claim bằng barrier, cho test driver hết lease và cho B claim lại, rồi giải phóng A. Để mô phỏng crash, không giải phóng A và xác nhận B vẫn có thể reclaim sau expiry.

## 12. Kiểm thử không cần chờ thời gian thực

Test dùng `sleep(lease_duration)` thường chậm và dễ flaky. Có thể làm thời gian hết hạn xác định bằng cách đặt `lease_until` trong quá khứ trong fixture hoặc dùng một clock abstraction ở tầng ứng dụng.

Ví dụ fixture:

```sql
UPDATE job_lease_lab
SET lease_until = clock_timestamp() - interval '1 second'
WHERE job_id = 1
  AND status = 'RUNNING';
```

Trong test tích hợp, câu lệnh này mô phỏng worker đã vượt quá thời hạn. Test không nên dùng nó như một thao tác production.

Nếu cần kiểm thử chính xác các race ở ranh giới thời gian, hãy tách:

- Unit test logic tính deadline bằng fake clock.
- Integration test database với lease đã đặt quá hạn trong fixture.
- Concurrency test hai connection dùng barrier để điều khiển thứ tự claim/complete.
- End-to-end test với thời gian thật ở một số trường hợp crash/timeout quan trọng.

Không mock hoàn toàn database lock trong unit test rồi kết luận concurrency behavior của engine đã được xác nhận. Cơ chế khóa phải được kiểm chứng bằng database thật hoặc engine tương đương với production.

## 13. Ma trận test cần có

Một bộ test tốt nên kiểm tra ít nhất các trường hợp sau:

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| L1 | A claim và hoàn tất trước expiry | A complete thành công, job `DONE` |
| L2 | A claim, lease hết hạn, B reclaim | B nhận generation mới và token mới |
| L3 | B reclaim rồi A complete bằng token cũ | A cập nhật 0 hàng |
| L4 | Lease hết hạn nhưng chưa có B; A complete theo strict lease | A cập nhật 0 hàng |
| L5 | Lease hết hạn nhưng chưa có B; A heartbeat | Heartbeat 0 hàng, A không tự gia hạn sau expiry |
| L6 | B đã reclaim; A heartbeat | A không gia hạn lease của B |
| L7 | B hoàn tất với token/generation hiện tại | B complete đúng một hàng |
| L8 | Hai worker cùng claim một job chưa hết lease | Chỉ một worker nhận được job |
| L9 | A complete và B reclaim chạy gần nhau tại expiry | Chỉ một chuyển trạng thái hợp lệ theo điều kiện và thứ tự lock |
| L10 | A gửi lệnh downstream generation 1 sau khi B đã gửi generation 2 | Downstream từ chối generation 1 |
| L11 | B gửi cùng operation idempotency key hai lần | Downstream chỉ áp dụng tác động nghiệp vụ một lần |
| L12 | Worker chết sau khi claim, trước khi xử lý | Job được reclaim sau expiry |
| L13 | Worker chết sau side effect nhưng trước `DONE` | Retry không nhân đôi side effect nhờ idempotency/outbox protocol |
| L14 | Heartbeat bị mất do timeout | Worker không giả định heartbeat thành công nếu chưa xác nhận |
| L15 | Job được claim lại nhiều lần | Generation tăng đơn điệu, không reset |

Với mỗi test, kiểm tra cả row count, trạng thái job, owner, token, generation, attempts và tác động ngoài database. Chỉ kiểm tra `status = DONE` chưa đủ để phát hiện side effect bị lặp.

## 14. Pseudocode worker có kiểm tra lease

Một worker nên coi lease như quyền có thể mất bất cứ lúc nào. Mỗi heartbeat và thao tác hoàn tất đều cần xác nhận từ database.

```text
function processClaimedJob(claim):
    jobId = claim.jobId
    token = claim.leaseToken
    generation = claim.leaseGeneration

    try:
        result = performWorkWithCancellation(jobId)

        completed = completeAndWriteOutboxIfLeaseStillOwned(
            jobId,
            workerId,
            token,
            generation,
            result
        )

        if not completed:
            discardLocalResultIfPossible()
            stopUsingThisClaim()
            return LOST_OWNERSHIP

        # An outbox dispatcher publishes the committed event separately.
        return SUCCESS

    catch error:
        if isRetryable(error):
            scheduleRetryOnlyIfLeaseStillOwned(
                jobId, workerId, token, generation
            )
        else:
            markFailedOnlyIfLeaseStillOwned(
                jobId, workerId, token, generation
            )
        throw error
```

Trong thiết kế thực tế, thứ tự ghi `DONE` và phát kết quả cần được phối hợp bằng outbox hoặc giao thức idempotent. Không nên commit `DONE` rồi phát một sự kiện không thể phục hồi nếu process crash giữa hai bước.

Worker cũng cần một cancellation token được kích hoạt khi heartbeat hoặc ownership check thất bại. Cancellation là best effort: một thread đã gửi request ra ngoài hoặc một tác vụ không hỗ trợ hủy có thể vẫn tiếp tục. Vì vậy, downstream vẫn cần fencing/idempotency.

## 15. Các chính sách khi worker mất quyền

Khi database báo heartbeat hoặc complete không còn ownership, worker nên:

1. Đánh dấu claim cục bộ là mất hiệu lực.
2. Ngừng nhận thêm công việc dựa trên claim đó.
3. Hủy tác vụ có thể hủy an toàn.
4. Không cập nhật `DONE`, `FAILED` hoặc retry schedule bằng token cũ.
5. Không gửi thêm tác động ngoài database nếu downstream không kiểm tra fencing/idempotency.
6. Ghi log sự kiện mất quyền cùng job ID, worker ID và generation.
7. Giải phóng tài nguyên local sau khi tác vụ dừng hoặc đạt giới hạn.

Không nên tự đổi trạng thái job về `READY` chỉ vì worker cũ phát hiện mình mất quyền. Worker mới có thể đang xử lý; chỉ owner hợp lệ hoặc scheduler/reaper có giao thức riêng mới được thay đổi trạng thái.

## 16. Những lỗi thiết kế thường gặp

- **Giữ row lock suốt tác vụ dài:** worker khác không thể reclaim dù process đã treo nhưng connection còn sống.
- **Không có lease:** job có thể mắc `RUNNING` mãi sau khi worker chết.
- **Không tăng generation:** token cũ có thể trùng hoặc không phân biệt được lần claim mới.
- **Chỉ kiểm tra ownership trong code worker:** race check-then-update cho phép lease thay đổi giữa hai bước.
- **Complete không kiểm tra expiry:** worker cũ có thể hoàn tất sau khi lease đã hết hạn nếu chưa ai reclaim.
- **Heartbeat không kiểm tra token:** worker cũ có thể gia hạn lease đã thuộc worker mới.
- **Dùng local clock để quyết định quyền:** clock skew tạo quyết định không nhất quán.
- **Chỉ dùng UUID như fencing token:** UUID không có thứ tự để downstream so sánh owner cũ/mới.
- **Tin rằng token trong database ngăn side effect ngoài:** downstream không kiểm tra token vẫn có thể nhận lệnh từ worker cũ.
- **Không có idempotency:** worker mới có thể lặp tác động mà worker cũ đã thực hiện trước khi crash.
- **Reset generation khi retry:** fencing token mất tính đơn điệu.
- **Đánh dấu DONE rồi mới ghi outbox ở transaction khác:** crash giữa hai bước có thể làm mất event.
- **Dùng sleep dài trong test:** kiểm thử chậm và dễ không ổn định; dùng fixture expiry và barrier cho test xác định.
- **Chỉ kiểm tra trạng thái cuối:** không phát hiện hai lần side effect hoặc worker cũ vẫn chạy.

## 17. Giám sát lease và worker quay lại muộn

Queue cần theo dõi cả trạng thái hiện tại lẫn lịch sử ownership. Các metric hữu ích:

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Lease expiration count | Số lease hết hạn | Worker chết, pause dài hoặc lease quá ngắn |
| Reclaim count | Số job được worker mới nhận lại | Tăng đột biến có thể do timeout hoặc xử lý chậm |
| Stale heartbeat count | Heartbeat bị từ chối vì token/generation/expiry không khớp | Worker cũ tiếp tục chạy hoặc heartbeat trễ |
| Stale completion count | Complete bị từ chối do mất ownership | Worker xử lý lâu hơn lease hoặc cancellation chậm |
| Lease renewal latency | Thời gian heartbeat được database xác nhận | Connection pool/DB chậm làm lease dễ hết hạn |
| Job processing duration | Thời gian từ claim đến kết thúc | Lease không phù hợp với phân phối thời gian thực tế |
| Generation increments per job | Số lần job được claim/reclaim | Job liên tục bị nhận lại |
| Duplicate side-effect attempts | Số lần downstream nhận cùng idempotency key | Retry hoặc worker overlap |
| Oldest RUNNING age | Job chạy lâu nhất | Worker treo hoặc lease được gia hạn không tiến triển |

Log nên có `job_id`, `worker_id`, `lease_generation`, token đã băm hoặc định danh an toàn, `attempts`, `lease_until`, event type và correlation ID. Tránh log payload nhạy cảm hoặc token bí mật nguyên văn.

Một số truy vấn giám sát PostgreSQL:

```sql
SELECT job_id,
       lease_owner,
       lease_generation,
       attempts,
       lease_until,
       clock_timestamp() - lease_until AS past_due_by
FROM job_lease_lab
WHERE status = 'RUNNING'
ORDER BY lease_until;
```

Và thống kê job theo trạng thái:

```sql
SELECT status, count(*)
FROM job_lease_lab
GROUP BY status
ORDER BY status;
```

Đừng chỉ cảnh báo khi job ở `RUNNING` quá lâu. Cần phân biệt lease còn hiệu lực, lease hết hạn chưa reclaim và job đã bị worker khác nhận lại.

## 18. Chọn lease duration và heartbeat interval

Lease quá ngắn làm worker bình thường mất quyền khi tác vụ chậm do tải, GC pause, network jitter hoặc database latency. Lease quá dài làm thời gian phục hồi worker chết tăng lên.

Một cách chọn ban đầu:

- Đo phân phối processing duration, đặc biệt p95/p99.
- Chọn lease đủ dài để chịu biến động bình thường giữa các heartbeat.
- Gửi heartbeat ở một phần nhỏ của lease duration, có khoảng đệm cho network/database latency.
- Đặt timeout cho heartbeat thấp hơn thời gian còn lại của lease.
- Nếu heartbeat không được xác nhận trước ngưỡng an toàn, dừng hoặc hủy tác vụ.
- Giới hạn tổng thời gian job để worker không gia hạn vô hạn.

Ví dụ minh họa: lease 120 giây, heartbeat mỗi 30 giây, heartbeat timeout 5 giây. Đây không phải giá trị mặc định; phải điều chỉnh theo thời gian xử lý, độ trễ database và khả năng phục hồi mong muốn.

Không nên chọn lease bằng đúng thời gian trung bình của job. Phân phối thời gian xử lý thường có đuôi dài; một số job lâu hơn nhiều so với median. Có thể dùng lease gia hạn động cho job dài và lưu checkpoint để tiếp tục sau khi reclaim.

## 19. Khác biệt khi triển khai trên DBMS khác

Các ví dụ SQL chính trong bài dùng PostgreSQL. Ý tưởng lease/token/generation có thể áp dụng cho DBMS khác, nhưng cú pháp claim và locking read khác nhau:

| DBMS | Cơ chế claim thường gặp | Lưu ý |
|---|---|---|
| PostgreSQL | CTE chọn ứng viên `FOR UPDATE SKIP LOCKED`, sau đó `UPDATE ... RETURNING` | Dùng `clock_timestamp()` cho expiry cần thời gian thực; SSI và row lock có semantics riêng |
| MySQL InnoDB | `SELECT ... FOR UPDATE SKIP LOCKED` trong transaction rồi `UPDATE` | Cần chú ý isolation, gap/next-key lock và cú pháp returning khác PostgreSQL |
| Oracle | `SELECT ... FOR UPDATE SKIP LOCKED` rồi cập nhật/cursor claim | Cú pháp cursor, row limiting và khả năng trả dữ liệu phụ thuộc phiên bản |
| SQL Server | `UPDATE`/CTE kết hợp locking hints như `UPDLOCK`, `READPAST`, `ROWLOCK` trong queue pattern | `READPAST` không tương đương hoàn toàn `SKIP LOCKED`; kiểm tra isolation và page locks |

Dù dùng engine nào, điều kiện hoàn tất phải xác minh quyền sở hữu hiện tại. Dùng transaction/locking syntax đúng phiên bản, kiểm tra row count và đảm bảo generation không reset. Không port nguyên câu SQL PostgreSQL sang DBMS khác rồi giả định semantics giống nhau.

## 20. Quy trình thực hành đầy đủ

Với mỗi bài test, thực hiện theo trình tự:

1. Tạo bảng lab và một job `READY`.
2. Mở hai connection độc lập A và B.
3. Cho A claim job, ghi lại token, generation và expiry.
4. Tạm dừng A sau khi commit claim, không giữ transaction mở.
5. Làm lease hết hạn bằng fixture hoặc fake clock.
6. Cho B claim lại, xác nhận token mới và generation tăng.
7. Cho A quay lại và thử heartbeat; phải bị từ chối.
8. Cho A thử complete; phải bị từ chối.
9. Cho B complete; phải thành công nếu lease còn hiệu lực.
10. Lặp lại với A complete trước expiry, sau expiry nhưng trước reclaim, và chạy đua với B reclaim.
11. Mô phỏng side effect ngoài database, xác nhận downstream kiểm tra fencing và idempotency.
12. Kiểm tra trạng thái cuối, lịch sử attempts, generation và số side effect thực tế.

Ghi lại kết quả theo mẫu:

| Trường | Giá trị cần ghi |
|---|---|
| DBMS/version | Engine và phiên bản test |
| Lease duration | Khoảng thời gian được cấp |
| Worker A claim | Owner, token, generation, expiry |
| Expiry simulation | Fake clock, fixture hoặc thời gian thực |
| Worker B reclaim | Owner, token, generation mới |
| A heartbeat muộn | Row count và kết quả |
| A complete muộn | Row count và trạng thái job |
| B complete | Row count và trạng thái cuối |
| Downstream fencing | Generation được chấp nhận/từ chối |
| Idempotency | Số tác động nghiệp vụ thực tế |

## 21. Những điểm cần ghi nhớ

- Row lock chỉ sống trong transaction; lease là quyền xử lý có thời hạn được lưu trong dữ liệu.
- Worker có thể quay lại sau khi lease hết hạn và worker mới đã nhận job; mọi thao tác ghi phải kiểm tra ownership tại database.
- Heartbeat và complete cần xác nhận owner, token, generation và expiry theo chính sách lease.
- Dùng đồng hồ database để quyết định expiry; local clock chỉ hỗ trợ đo thời lượng và cancellation.
- Generation tăng đơn điệu giúp downstream nhận ra lệnh từ worker cũ; UUID token chỉ nhận diện lần claim, không thể hiện thứ tự.
- Strict lease có nghĩa worker mất quyền ngay khi expiry, kể cả chưa có worker mới reclaim; hãy chọn và kiểm thử chính sách rõ ràng.
- Database token không tự ngăn side effect ngoài database. Downstream cần kiểm tra fencing token và idempotency key.
- Outbox giúp ghi ý định phát event cùng transaction; consumer vẫn phải xử lý giao hàng lặp.
- Test bằng hai session độc lập, barrier và lease đã hết hạn xác định; không chỉ dựa vào sleep dài.
- Kiểm tra cả heartbeat, complete, reclaim, race tại expiry, worker crash/pause và tác động bên ngoài.
- Theo dõi lease expiration, reclaim, stale heartbeat/completion, processing duration và duplicate side-effect attempts.

Một worker quay lại sau khi mất lease là tình huống bình thường trong hệ thống phân tán: process có thể pause, mạng có thể đứt rồi hồi phục, hoặc phản hồi database có thể đến muộn. Thiết kế an toàn không dựa vào giả định worker cũ sẽ tự dừng đúng lúc. Nó buộc database và hệ thống đích xác nhận quyền sở hữu ở thời điểm ghi, dùng generation để fencing owner cũ, và dùng idempotency để kiểm soát tác động được giao lại.
