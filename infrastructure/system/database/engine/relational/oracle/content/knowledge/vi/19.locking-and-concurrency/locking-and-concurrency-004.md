# NOWAIT, WAIT, SKIP LOCKED và mô hình nhận việc từ bảng trong Oracle

## 1. Bài toán nhiều người cùng làm việc trên một bảng

Một ứng dụng có thể có nhiều người dùng cùng sửa một đơn hàng, hoặc nhiều worker cùng đọc một bảng `JOB_QUEUE` để xử lý công việc nền. Nếu hai session cùng chọn một hàng rồi cùng xử lý, hệ thống có thể thực hiện trùng công việc, ghi đè dữ liệu hoặc tạo ra trạng thái không nhất quán.

Oracle cung cấp cơ chế khóa hàng tường minh qua `SELECT ... FOR UPDATE`. Khi cần lấy khóa, session có thể chọn một trong các chính sách:

- **`NOWAIT`**: nếu hàng cần khóa đang bị session khác khóa, trả lỗi ngay.
- **`WAIT n`**: chờ tối đa `n` giây để lấy khóa; hết thời gian thì trả lỗi.
- **`SKIP LOCKED`**: bỏ qua các hàng đang bị session khác khóa và tiếp tục lấy những hàng khả dụng.

Ba chế độ này phục vụ các tình huống khác nhau. `NOWAIT` phù hợp với thao tác tương tác cần phản hồi ngay khi có xung đột. `WAIT` phù hợp khi có thể chờ trong một khoảng hữu hạn. `SKIP LOCKED` đặc biệt hữu ích khi nhiều worker cùng nhận việc từ một bảng queue.

Ví dụ, hai worker cùng đọc những job đang ở trạng thái READY:

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

Nếu worker A đã khóa một số hàng, worker B có thể bỏ qua các hàng đó và nhận những hàng READY khác chưa bị khóa. Sau khi nhận việc, worker cần cập nhật trạng thái job trong cùng transaction rồi COMMIT để các worker khác không nhận lại cùng job.

Bài học thuộc chương **Khóa và đồng thời**, trình bày khóa hàng, cú pháp `SELECT FOR UPDATE`, khác biệt giữa `NOWAIT`, `WAIT` và `SKIP LOCKED`, cách xây dựng queue nhiều worker, transaction nhận việc, lease, retry, xử lý worker bị dừng và các lưu ý về fairness, hiệu năng, JDBC và PL/SQL.

## 2. Khóa hàng và transaction trong Oracle

### 2.1. SELECT thông thường không khóa hàng để đọc

Oracle dùng cơ chế multiversion concurrency control (MVCC) và read consistency. Một câu SELECT thông thường thường đọc phiên bản dữ liệu nhất quán mà không cần chờ một transaction khác chỉ vì transaction đó đang sửa hàng.

Ví dụ:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001;
```

Nếu session khác đang UPDATE đơn hàng 1001 nhưng chưa COMMIT, SELECT thông thường có thể đọc phiên bản đã commit trước đó theo snapshot phù hợp.

### 2.2. SELECT FOR UPDATE chủ động khóa hàng

Khi ứng dụng đọc một hàng để chuẩn bị thay đổi, có thể khóa hàng ngay trong lúc đọc:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE;
```

Session lấy được khóa hàng sẽ giữ khóa cho đến khi transaction kết thúc bằng `COMMIT` hoặc `ROLLBACK`. Session khác muốn khóa hoặc UPDATE cùng hàng có thể phải chờ theo chính sách của câu lệnh đó.

`SELECT FOR UPDATE` không phải chỉ là một SELECT có thêm thông tin. Nó là thao tác lấy khóa, vì vậy cần có kế hoạch kết thúc transaction. Không mở transaction rồi để người dùng suy nghĩ hoặc chờ một dịch vụ bên ngoài trong khi vẫn giữ khóa.

### 2.3. UPDATE cũng tự lấy khóa

Không nhất thiết phải SELECT FOR UPDATE trước mọi UPDATE:

```sql
UPDATE orders
SET status = 'APPROVED'
WHERE order_id = 1001;
```

Oracle tự lấy các khóa cần thiết để thực hiện DML. `SELECT FOR UPDATE` hữu ích khi ứng dụng cần đọc dữ liệu, quyết định dựa trên dữ liệu đó, rồi cập nhật trong cùng transaction và muốn ngăn session khác thay đổi hàng giữa bước đọc và ghi.

### 2.4. Khóa được giữ đến khi nào?

Khóa hàng do `SELECT FOR UPDATE` hoặc DML lấy được giữ đến khi transaction kết thúc:

```sql
SELECT *
FROM orders
WHERE order_id = 1001
FOR UPDATE;

-- Thực hiện kiểm tra/cập nhật trong cùng transaction.
UPDATE orders
SET status = 'APPROVED'
WHERE order_id = 1001;

COMMIT;
```

Đóng cursor không đồng nghĩa giải phóng khóa. Khóa được giải phóng khi COMMIT hoặc ROLLBACK transaction. Đây là lý do worker queue phải khóa, đổi trạng thái và commit nhanh trước khi thực hiện công việc dài.

### 2.5. Khóa hàng không có nghĩa khóa toàn bảng

Oracle dùng khóa ở nhiều cấp. `SELECT FOR UPDATE` chủ yếu lấy row locks trên các hàng được chọn và có thể lấy table-level lock ở chế độ tương thích với DML khác. Một câu UPDATE cũng có khóa hàng và table lock cần thiết để bảo vệ thao tác.

Đừng hiểu `SKIP LOCKED` là bỏ qua mọi loại khóa trong database. Nó xử lý xung đột khóa hàng theo ngữ nghĩa của SELECT FOR UPDATE; table lock, DDL lock, khóa tài nguyên khác hoặc các điều kiện chờ khác vẫn có thể khiến session phải chờ.

## 3. Cú pháp SELECT FOR UPDATE

Cú pháp khái quát:

```sql
SELECT select_list
FROM table_name
WHERE condition
ORDER BY sort_expression
FOR UPDATE
    [OF column_list]
    [NOWAIT | WAIT integer | SKIP LOCKED];
```

Các phần:

- `FOR UPDATE`: yêu cầu khóa những hàng được chọn.
- `OF column_list`: chỉ định các bảng có cột được liệt kê mà Oracle cần khóa trong truy vấn có nhiều bảng. Đây là cách chỉ rõ bảng, không phải chỉ khóa riêng các cột được nêu.
- `NOWAIT`: không chờ khi gặp hàng đang bị khóa.
- `WAIT integer`: chờ tối đa số giây được chỉ định.
- `SKIP LOCKED`: bỏ qua hàng đang bị transaction khác khóa.

Ví dụ cơ bản:

```sql
SELECT order_id, status
FROM orders
WHERE status = 'PENDING'
FOR UPDATE;
```

Nếu có nhiều hàng thỏa điều kiện, câu lệnh có thể khóa các hàng được chọn. Hãy dùng WHERE đủ chọn lọc để không khóa một tập dữ liệu lớn ngoài ý muốn.

### 3.1. Dùng OF trong truy vấn JOIN

Khi truy vấn nhiều bảng:

```sql
SELECT o.order_id,
       o.status,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PENDING'
FOR UPDATE OF o.status;
```

`OF o.status` xác định bảng `ORDERS` là bảng có hàng cần khóa. Oracle khóa hàng của bảng chứa cột được chỉ định; nó không có nghĩa chỉ khóa riêng cột `STATUS`.

Khi không chỉ định `OF`, phạm vi khóa trong truy vấn nhiều bảng có thể rộng hơn. Hãy chỉ rõ bảng cần khóa để giảm khóa không cần thiết và làm ý định dễ hiểu.

### 3.2. Các hạn chế của SELECT FOR UPDATE

`FOR UPDATE` không thể kết hợp tùy ý với mọi cấu trúc SELECT. Một số cấu trúc bị hạn chế, gồm:

- `DISTINCT`.
- `GROUP BY` và các hàm aggregate.
- Set operators như `UNION`, `INTERSECT`, `MINUS`.
- Một số view hoặc inline view không thể cập nhật/khóa theo quy tắc của Oracle.
- Một số dạng truy vấn phức tạp có các hạn chế riêng theo phiên bản.

Nếu cần khóa hàng nguồn rồi tính tổng hợp, hãy tách bước khóa các hàng cơ sở phù hợp khỏi bước aggregate. Không cố đặt `FOR UPDATE` trực tiếp lên một kết quả đã GROUP BY.

### 3.3. ORDER BY có ích khi lấy hàng theo thứ tự

```sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

`ORDER BY` định nghĩa thứ tự ưu tiên trong số các hàng đủ điều kiện. Với queue, thường ưu tiên job có priority cao, sau đó job cũ hơn. Thêm `job_id` làm tie-breaker để thứ tự có tính xác định khi các giá trị ưu tiên và thời gian giống nhau.

Thứ tự ưu tiên không bảo đảm FIFO tuyệt đối khi dùng SKIP LOCKED: một job cũ đang bị worker khác khóa có thể bị bỏ qua để worker nhận job mới hơn.

## 4. NOWAIT — không chờ khóa

### 4.1. Cú pháp

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE NOWAIT;
```

Nếu hàng cần khóa đang bị transaction khác giữ khóa, Oracle trả lỗi ngay thay vì chờ.

Lỗi thường gặp:

```text
ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired
```

Thông báo có thể được dùng để báo cho ứng dụng rằng tài nguyên đang bận và người dùng cần thử lại sau.

### 4.2. Khi nào dùng NOWAIT?

NOWAIT phù hợp khi:

- Người dùng đang mở một bản ghi để chỉnh sửa và cần biết ngay bản ghi đang được người khác xử lý.
- Một thao tác không được phép chờ vì yêu cầu phản hồi nhanh.
- Một quy trình chỉ muốn thử lấy khóa một lần rồi chuyển sang nhánh xử lý khác.
- Ứng dụng có cơ chế retry/backoff riêng ở tầng service.

Ví dụ:

```sql
BEGIN
    SELECT order_id, status
    INTO v_order_id, v_status
    FROM orders
    WHERE order_id = p_order_id
    FOR UPDATE NOWAIT;

    -- Xử lý tiếp trong cùng transaction.
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
/
```

Đây là khung PL/SQL minh họa; cần khai báo biến và xử lý riêng lỗi ORA-00054 trong ứng dụng thực tế. Không bắt mọi exception rồi coi chúng đều là lỗi khóa.

### 4.3. NOWAIT không tự giải quyết xung đột nghiệp vụ

Nếu ứng dụng nhận ORA-00054, điều đó chỉ cho biết không lấy được khóa theo yêu cầu tại thời điểm đó. Nó không cho biết người đang giữ khóa sẽ commit hay rollback, cũng không đảm bảo thử lại ngay sẽ thành công.

Ứng dụng có thể:

- Trả thông báo “bản ghi đang được xử lý”.
- Cho người dùng tải lại dữ liệu.
- Retry một số lần với backoff ngắn nếu thao tác có thể lặp an toàn.
- Chuyển sang một hàng khác nếu đây là queue worker.

Không retry liên tục không có khoảng nghỉ vì có thể làm tăng tải và tạo thêm tranh chấp.

## 5. WAIT n — chờ trong thời gian giới hạn

### 5.1. Cú pháp

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE WAIT 5;
```

Nếu hàng đang bị khóa, Oracle chờ tối đa 5 giây để lấy khóa. Nếu hết thời gian mà vẫn không lấy được, câu lệnh báo lỗi timeout, thường là:

```text
ORA-30006: resource busy; acquire with WAIT timeout expired
```

### 5.2. Khi nào dùng WAIT?

WAIT phù hợp khi:

- Xung đột thường ngắn và ứng dụng có thể chờ.
- Một thao tác nghiệp vụ cần lấy khóa nhưng không muốn chờ vô hạn.
- Có SLA cụ thể, ví dụ không chờ quá 3 hoặc 5 giây.
- Một batch có thể chờ tài nguyên ngắn hạn nhưng cần thất bại có kiểm soát nếu quá thời gian.

Chọn timeout theo trải nghiệm người dùng và SLA, không chọn tùy tiện một con số lớn.

### 5.3. WAIT khác timeout kết nối và timeout câu lệnh

`WAIT n` ở `SELECT FOR UPDATE` là thời gian chờ lấy khóa theo cú pháp Oracle. Nó khác:

- Connection timeout khi mở kết nối.
- Statement/query timeout do JDBC hoặc client quản lý.
- Timeout của một request HTTP.
- Timeout của một job hoặc transaction ở tầng ứng dụng.

Nếu hệ thống có nhiều lớp timeout, cần cấu hình nhất quán. Ví dụ, HTTP request hết hạn sau 3 giây nhưng SQL đang `WAIT 30`, ứng dụng có thể trả timeout trong khi database vẫn đang giữ connection và tiếp tục chờ nếu driver không hủy câu lệnh đúng cách.

### 5.4. WAIT không có nghĩa chờ transaction hoàn tất toàn bộ công việc

Oracle chỉ chờ để lấy khóa theo chính sách được chỉ định. Sau khi lấy được khóa, transaction vẫn phải thực hiện công việc và kết thúc. Nếu transaction tiếp tục mở lâu, các session khác vẫn bị ảnh hưởng.

## 6. SKIP LOCKED — bỏ qua hàng đang bị khóa

### 6.1. Cú pháp

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

Khi một hàng phù hợp đang bị transaction khác khóa, Oracle bỏ qua hàng đó và tiếp tục tìm hàng phù hợp khác. Câu lệnh không chờ khóa hàng ấy như WAIT.

Đây là cơ chế phù hợp cho nhiều consumer cùng nhận việc:

- Worker A khóa job 101.
- Worker B chạy cùng truy vấn.
- Worker B bỏ qua job 101 và có thể lấy job 102.
- Worker C có thể lấy job 103 nếu các hàng ấy chưa bị khóa.

Các worker không phải lần lượt chờ một hàng đầu tiên được mở khóa.

### 6.2. Không có hàng trả về không đồng nghĩa queue rỗng

Với SKIP LOCKED, một truy vấn có thể trả 0 hàng vì:

1. Không có job nào thỏa điều kiện.
2. Có job thỏa điều kiện nhưng tất cả đều đang bị session khác khóa.
3. Có job nhưng chưa đến `AVAILABLE_AT`.

Vì vậy, worker nên hiểu kết quả rỗng là **không có hàng hiện đang claim được**. Nó không đủ để kết luận queue không còn job. Có thể chờ một khoảng ngắn, nhận tín hiệu từ hệ thống điều phối hoặc thử lại theo lịch polling.

### 6.3. SKIP LOCKED không phải bỏ qua mọi loại khóa

SKIP LOCKED được thiết kế để tránh chờ các row locks trên những hàng cần lấy. Nó không bỏ qua table-level locks, DDL locks hoặc mọi loại chờ tài nguyên khác. Một thao tác DDL hoặc khóa bảng không tương thích vẫn có thể ảnh hưởng truy vấn.

### 6.4. SKIP LOCKED không bảo đảm FIFO tuyệt đối

Giả sử job 101 có priority cao nhất nhưng đang bị worker A khóa. Worker B bỏ qua job 101 và nhận job 102. Điều đó có nghĩa thứ tự xử lý thực tế có thể khác thứ tự ưu tiên tuyệt đối.

SKIP LOCKED tối ưu khả năng nhiều worker tiến triển song song; nó không phải cơ chế bảo đảm công bằng tuyệt đối. Nếu một hàng liên tục bị giữ khóa hoặc liên tục không đủ điều kiện, cần giám sát tuổi job, thời gian chờ và chính sách lease/retry.

## 7. So sánh NOWAIT, WAIT và SKIP LOCKED

| Chế độ | Hành vi khi hàng bị khóa | Kết quả điển hình | Tình huống phù hợp |
|---|---|---|---|
| Không chỉ định | Chờ theo hành vi mặc định của Oracle | Chờ cho đến khi khóa được giải phóng hoặc có điều kiện lỗi khác | Tương tác thông thường khi chấp nhận chờ |
| `NOWAIT` | Không chờ | ORA-00054 | Giao diện cần phản hồi ngay |
| `WAIT n` | Chờ tối đa n giây | ORA-30006 khi timeout | Xung đột thường ngắn, có SLA |
| `SKIP LOCKED` | Bỏ qua hàng đang bị khóa | Trả các hàng khả dụng khác; có thể 0 hàng | Worker queue nhiều consumer |

Không có một lựa chọn tốt nhất cho mọi trường hợp. Chọn theo câu hỏi nghiệp vụ: người dùng cần biết có xung đột không, có thể chờ bao lâu, hay có thể làm một việc khác trong lúc hàng đầu tiên đang bận.

## 8. Minh họa hai session cạnh tranh cùng một hàng

Giả sử bảng `orders` có `ORDER_ID = 1001`.

### 8.1. Session A lấy khóa

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE;
```

Session A chưa COMMIT hoặc ROLLBACK nên vẫn giữ khóa.

### 8.2. Session B thử NOWAIT

Trong một connection khác:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE NOWAIT;
```

Session B nhận lỗi ngay vì hàng đang bị A khóa.

### 8.3. Session B thử WAIT

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE WAIT 5;
```

Session B chờ tối đa 5 giây. Nếu A COMMIT trong khoảng chờ, B có thể lấy khóa. Nếu A vẫn giữ khóa quá thời hạn, B nhận timeout.

### 8.4. Session B thử SKIP LOCKED

```sql
SELECT order_id, status
FROM orders
WHERE order_id IN (1001, 1002, 1003)
ORDER BY order_id
FOR UPDATE SKIP LOCKED;
```

Nếu A đang khóa 1001, B có thể nhận 1002 và 1003, tùy trạng thái khóa thực tế của các hàng đó.

### 8.5. Giải phóng khóa

Trong Session A:

```sql
COMMIT;
-- Hoặc ROLLBACK nếu muốn hủy thay đổi trong transaction.
```

Sau khi transaction kết thúc, khóa được giải phóng. Session B có thể thử lại hàng trước đó nếu nghiệp vụ vẫn yêu cầu.

## 9. Mô hình queue từ một bảng

Một queue dựa trên bảng thường có các trạng thái:

```text
READY -> RUNNING -> DONE
                  -> READY (retry)
                  -> FAILED
```

Các trường dữ liệu thường dùng:

| Cột | Ý nghĩa |
|---|---|
| `JOB_ID` | Khóa chính của job |
| `PAYLOAD` | Nội dung hoặc tham chiếu đến dữ liệu cần xử lý |
| `STATUS` | READY, RUNNING, DONE hoặc FAILED |
| `PRIORITY` | Độ ưu tiên |
| `AVAILABLE_AT` | Thời điểm job đủ điều kiện nhận |
| `ATTEMPTS` | Số lần đã claim/thử xử lý |
| `MAX_ATTEMPTS` | Giới hạn số lần thử |
| `WORKER_ID` | Worker đang nhận job |
| `CLAIM_TOKEN` | Token của lần claim hiện tại |
| `CLAIMED_AT` | Thời điểm claim |
| `LEASE_UNTIL` | Thời điểm lease hết hạn |
| `COMPLETED_AT` | Thời điểm hoàn tất |
| `LAST_ERROR` | Lỗi gần nhất nếu thất bại |
| `CREATED_AT` | Thời điểm tạo job |

### 9.1. Tạo bảng queue minh họa

```sql
CREATE TABLE job_queue (
    job_id NUMBER GENERATED ALWAYS AS IDENTITY
        CONSTRAINT pk_job_queue PRIMARY KEY,
    payload CLOB NOT NULL,
    status VARCHAR2(16) DEFAULT 'READY' NOT NULL,
    priority NUMBER DEFAULT 0 NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    attempts NUMBER DEFAULT 0 NOT NULL,
    max_attempts NUMBER DEFAULT 5 NOT NULL,
    worker_id VARCHAR2(64),
    claim_token RAW(16),
    claimed_at TIMESTAMP WITH TIME ZONE,
    lease_until TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    last_error VARCHAR2(2000),
    created_at TIMESTAMP WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_job_queue_status
        CHECK (status IN ('READY', 'RUNNING', 'DONE', 'FAILED')),
    CONSTRAINT ck_job_queue_attempts
        CHECK (attempts >= 0 AND max_attempts > 0)
);
```

Identity cần Oracle 12c Release 1 trở lên. Với database cũ hơn, có thể dùng sequence kết hợp INSERT hoặc trigger theo thiết kế phù hợp.

### 9.2. Thêm job vào queue

```sql
INSERT INTO job_queue (
    payload,
    priority,
    available_at
)
VALUES (
    '{"type":"SEND_EMAIL","customerId":501}',
    10,
    SYSTIMESTAMP
);

COMMIT;
```

Trong ứng dụng, payload có thể là JSON, CLOB, ID tham chiếu hoặc một cấu trúc dữ liệu được lưu ở bảng riêng. Hãy chọn cách lưu phù hợp với kích thước, khả năng truy vấn và yêu cầu bảo mật.

### 9.3. Tạo index cho việc tìm job

Một index ứng viên:

```sql
CREATE INDEX ix_job_queue_claim
ON job_queue (
    status,
    available_at,
    priority DESC,
    created_at,
    job_id
);
```

Index thực tế phụ thuộc số lượng trạng thái, độ chọn lọc của `AVAILABLE_AT`, cách sắp xếp priority và phân bố job. Vì điều kiện thời gian là range predicate, index trên không nhất thiết loại bỏ được bước sort. Hãy kiểm tra execution plan và đo trên workload thật trước khi chốt thứ tự cột.

## 10. Quy trình claim job an toàn

Một worker nên thực hiện ba bước trong transaction ngắn:

1. Chọn một hoặc nhiều job READY bằng `SELECT FOR UPDATE SKIP LOCKED`.
2. Cập nhật trạng thái thành RUNNING, ghi worker, token và lease.
3. COMMIT để giải phóng row locks và xác nhận quyền xử lý theo trạng thái đã ghi.

Sau COMMIT, worker mới thực hiện công việc thực tế. Không giữ transaction và row locks trong suốt thời gian gọi API, gửi email, xử lý file hoặc chờ dịch vụ bên ngoài.

### 10.1. Claim một job bằng PL/SQL cursor

```sql
DECLARE
    v_worker_id   CONSTANT VARCHAR2(64) := 'worker-A';
    v_job_id      job_queue.job_id%TYPE;
    v_claim_token RAW(16) := SYS_GUID();

    CURSOR c_jobs IS
        SELECT job_id
        FROM job_queue
        WHERE status = 'READY'
          AND available_at <= SYSTIMESTAMP
        ORDER BY priority DESC, created_at, job_id
        FOR UPDATE SKIP LOCKED;
BEGIN
    OPEN c_jobs;
    FETCH c_jobs INTO v_job_id;

    IF c_jobs%FOUND THEN
        UPDATE job_queue
        SET status = 'RUNNING',
            worker_id = v_worker_id,
            claim_token = v_claim_token,
            claimed_at = SYSTIMESTAMP,
            lease_until = SYSTIMESTAMP + INTERVAL '5' MINUTE,
            attempts = attempts + 1
        WHERE CURRENT OF c_jobs;

        DBMS_OUTPUT.PUT_LINE('JOB_ID=' || v_job_id);
        DBMS_OUTPUT.PUT_LINE('CLAIM_TOKEN=' || RAWTOHEX(v_claim_token));
    ELSE
        DBMS_OUTPUT.PUT_LINE('No currently claimable job');
    END IF;

    CLOSE c_jobs;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF c_jobs%ISOPEN THEN
            CLOSE c_jobs;
        END IF;
        ROLLBACK;
        RAISE;
END;
/
```

Điểm cần chú ý:

- Cursor dùng `FOR UPDATE SKIP LOCKED`.
- `FETCH` lấy hàng khả dụng và cursor giữ row lock tương ứng.
- `WHERE CURRENT OF c_jobs` cập nhật đúng hàng hiện tại của cursor.
- `CLAIM_TOKEN` phân biệt lần nhận việc này với lần nhận việc khác.
- COMMIT sau khi đổi trạng thái; worker xử lý payload sau transaction này.

Đây là block minh họa chạy trong schema lab. Trong ứng dụng thực tế, worker ID và token nên được truyền/nhận qua tham số procedure hoặc bind output thay vì hard-code và chỉ in DBMS_OUTPUT.

### 10.2. Claim một batch bằng cursor

Khi cần nhận tối đa 10 job:

```sql
DECLARE
    v_worker_id   CONSTANT VARCHAR2(64) := 'worker-A';
    v_batch_size  CONSTANT PLS_INTEGER := 10;
    v_claim_token RAW(16) := SYS_GUID();
    v_job_id      job_queue.job_id%TYPE;
    v_claimed     PLS_INTEGER := 0;

    CURSOR c_jobs IS
        SELECT job_id
        FROM job_queue
        WHERE status = 'READY'
          AND available_at <= SYSTIMESTAMP
        ORDER BY priority DESC, created_at, job_id
        FOR UPDATE SKIP LOCKED;
BEGIN
    OPEN c_jobs;

    LOOP
        FETCH c_jobs INTO v_job_id;
        EXIT WHEN c_jobs%NOTFOUND;

        UPDATE job_queue
        SET status = 'RUNNING',
            worker_id = v_worker_id,
            claim_token = v_claim_token,
            claimed_at = SYSTIMESTAMP,
            lease_until = SYSTIMESTAMP + INTERVAL '5' MINUTE,
            attempts = attempts + 1
        WHERE CURRENT OF c_jobs;

        v_claimed := v_claimed + 1;
        EXIT WHEN v_claimed >= v_batch_size;
    END LOOP;

    CLOSE c_jobs;
    COMMIT;

    DBMS_OUTPUT.PUT_LINE('CLAIMED=' || v_claimed);
    DBMS_OUTPUT.PUT_LINE('CLAIM_TOKEN=' || RAWTOHEX(v_claim_token));
EXCEPTION
    WHEN OTHERS THEN
        IF c_jobs%ISOPEN THEN
            CLOSE c_jobs;
        END IF;
        ROLLBACK;
        RAISE;
END;
/
```

Ví dụ dùng cursor và giới hạn số lần FETCH trong PL/SQL. Không giả định có thể ghép mọi cú pháp row limiting như `FETCH FIRST 10 ROWS ONLY` trực tiếp với `FOR UPDATE`; Oracle có hạn chế kết hợp row-limiting clause với `FOR UPDATE`. Cách cursor giúp kiểm soát batch rõ ràng.

Sau khi block hoàn tất, ứng dụng lấy claim token qua output/bind parameter rồi truy vấn các job của batch:

```sql
SELECT job_id, payload, attempts, lease_until
FROM job_queue
WHERE status = 'RUNNING'
  AND claim_token = :claim_token
ORDER BY priority DESC, created_at, job_id;
```

Trong hệ thống thật, không dùng một worker ID chung cho nhiều tiến trình đang chạy đồng thời. Token phải riêng cho mỗi lần claim hoặc batch để tránh nhầm quyền sở hữu.

### 10.3. Vì sao phải đổi trạng thái trước COMMIT?

Nếu worker chỉ SELECT FOR UPDATE SKIP LOCKED rồi COMMIT mà không đổi `STATUS`, khóa được giải phóng và job vẫn READY. Worker khác có thể nhận lại ngay job ấy.

Việc cập nhật READY thành RUNNING trong cùng transaction với thao tác lấy khóa tạo ra điểm chuyển trạng thái nguyên tử. Sau COMMIT, các worker khác lọc `STATUS = 'READY'` nên không chọn job đã được claim.

## 11. Xử lý job sau khi claim

Sau khi claim và COMMIT, worker thực hiện công việc bên ngoài transaction ngắn. Khi thành công:

```sql
UPDATE job_queue
SET status = 'DONE',
    completed_at = SYSTIMESTAMP,
    worker_id = NULL,
    claim_token = NULL,
    lease_until = NULL,
    last_error = NULL
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND claim_token = :claim_token;
```

Kiểm tra số hàng được cập nhật. Nếu bằng 1, worker vẫn sở hữu claim hiện tại và đã đánh dấu hoàn tất. Nếu bằng 0, job có thể đã bị thu hồi/reclaim hoặc token không còn hợp lệ; worker cũ không được tự ý ghi đè trạng thái mới.

### 11.1. Khi xử lý thất bại

Có thể đưa job trở lại READY với thời gian thử lại trong tương lai, hoặc chuyển FAILED khi đã hết số lần:

```sql
UPDATE job_queue
SET status = CASE
                 WHEN attempts >= max_attempts THEN 'FAILED'
                 ELSE 'READY'
             END,
    available_at = CASE
                       WHEN attempts >= max_attempts THEN available_at
                       ELSE SYSTIMESTAMP + INTERVAL '1' MINUTE
                   END,
    worker_id = NULL,
    claim_token = NULL,
    lease_until = NULL,
    last_error = :error_message
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND claim_token = :claim_token;
```

Đây là backoff cố định một phút để minh họa. Hệ thống thực tế thường dùng exponential backoff, jitter và phân loại lỗi retryable/non-retryable.

Nếu UPDATE không tác động hàng nào, worker phải coi claim đã mất hiệu lực và không ghi đè trạng thái của worker mới.

### 11.2. Xóa hoặc lưu kết quả sau khi hoàn tất?

Thông thường nên giữ hàng DONE một thời gian để audit, thống kê và điều tra sự cố. Một job có thể được chuyển sang bảng archive hoặc xóa theo chính sách retention sau khi không còn cần tra cứu.

Không xóa hàng ngay nếu hệ thống cần biết job đã từng được xử lý, cần idempotency hoặc cần phân tích retry.

## 12. Lease: phục hồi job khi worker bị dừng

Một worker có thể bị tắt máy, mất kết nối hoặc crash sau khi đã claim job. Khi đó hàng có thể ở trạng thái RUNNING mãi nếu không có cơ chế thu hồi.

**Lease** là khoảng thời gian quyền xử lý có hiệu lực. Khi claim, worker đặt:

```sql
lease_until = SYSTIMESTAMP + INTERVAL '5' MINUTE
```

Nếu worker không hoàn tất hoặc gia hạn trước thời điểm này, job có thể được xem là hết lease và được đưa trở lại hàng chờ.

### 12.1. Tìm và thu hồi job hết lease

Một tác vụ phục hồi có thể chạy định kỳ:

```sql
UPDATE job_queue
SET status = 'READY',
    worker_id = NULL,
    claim_token = NULL,
    claimed_at = NULL,
    lease_until = NULL,
    available_at = SYSTIMESTAMP
WHERE status = 'RUNNING'
  AND lease_until < SYSTIMESTAMP;

COMMIT;
```

Ví dụ đơn giản này thu hồi mọi job RUNNING đã hết lease. Với workload lớn, nên xử lý theo batch và đo tác động. Cần có cơ chế giám sát để tránh job đang chạy bình thường bị thu hồi do lease quá ngắn hoặc worker bị pause tạm thời.

### 12.2. Gia hạn lease (heartbeat)

Worker đang xử lý lâu có thể gia hạn:

```sql
UPDATE job_queue
SET lease_until = SYSTIMESTAMP + INTERVAL '5' MINUTE
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND claim_token = :claim_token;
```

Nếu số hàng cập nhật bằng 0, worker không còn sở hữu claim hiện tại. Nó nên dừng hoặc chuyển sang trạng thái xử lý an toàn; không được giả định lease vẫn thuộc về mình.

### 12.3. Token ngăn worker cũ ghi đè worker mới

Giả sử:

1. Worker A claim job bằng token A.
2. A bị treo lâu và lease hết hạn.
3. Tác vụ phục hồi đưa job về READY.
4. Worker B claim lại bằng token B.
5. Worker A thức dậy và cố cập nhật DONE.

Điều kiện `AND claim_token = :claim_token` khiến câu UPDATE của A không khớp vì token hiện tại là B. Nhờ vậy A không thể ghi đè trạng thái của B trong bảng queue.

Token không tự ngăn A thực hiện một side effect bên ngoài, ví dụ gửi email hoặc gọi API. Để hạn chế tác động trùng, job cần idempotency key, cơ chế fencing ở hệ thống đích hoặc một giao thức xử lý side effect có thể retry an toàn.

### 12.4. Lease không tạo exactly-once một cách tự động

Một tình huống không thể loại bỏ chỉ bằng row lock:

- Worker gửi email thành công.
- Worker crash trước khi cập nhật trạng thái DONE.
- Lease hết hạn và job được giao lại.
- Worker mới gửi email lần nữa.

Database không thể tự biết email đã được hệ thống bên ngoài gửi thành công hay chưa nếu hai hệ thống không có giao thức phối hợp. Vì vậy, queue dựa trên bảng thường cung cấp semantics **at-least-once** khi có retry; handler cần idempotent hoặc dịch vụ đích hỗ trợ idempotency key.

## 13. Tại sao không giữ row lock trong lúc xử lý job?

Một thiết kế dễ mắc lỗi:

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;

-- Gọi API ngoài, xử lý file, chờ phản hồi trong khi transaction vẫn mở.
```

Nếu worker giữ transaction trong 2 phút để gọi API:

- Hàng bị khóa lâu hơn cần thiết.
- Worker khác phải bỏ qua hàng đó trong suốt thời gian xử lý.
- Connection và transaction resources bị giữ.
- Nếu batch có nhiều hàng, các hàng khác cũng bị khóa.
- Lỗi hoặc timeout làm trạng thái khóa kéo dài cho đến khi transaction được kết thúc.

Mẫu tốt hơn:

```text
Transaction ngắn:
  SELECT FOR UPDATE SKIP LOCKED
  UPDATE READY -> RUNNING + token + lease
  COMMIT

Ngoài transaction:
  Đọc payload theo claim token
  Thực hiện công việc

Transaction ngắn:
  RUNNING -> DONE hoặc READY/FAILED
  COMMIT
```

Khóa hàng chỉ cần bảo vệ thao tác **claim**. Trạng thái RUNNING và token thể hiện quyền xử lý sau khi khóa được giải phóng.

## 14. Queue nhiều worker: diễn tiến minh họa

Giả sử có ba job READY: 101, 102, 103.

| Thời điểm | Worker A | Worker B |
|---|---|---|
| T1 | Khóa job 101 bằng SKIP LOCKED | |
| T2 | Cập nhật 101 thành RUNNING | Bắt đầu SELECT |
| T3 | Chưa COMMIT | Bỏ qua 101, khóa 102 |
| T4 | COMMIT | Cập nhật 102 thành RUNNING |
| T5 | Bắt đầu xử lý job 101 ngoài transaction | COMMIT, bắt đầu xử lý 102 |
| T6 | Cập nhật 101 thành DONE | Cập nhật 102 thành DONE |

Không worker nào claim cùng một hàng trong hai transaction claim đang diễn ra. Sau khi commit, trạng thái RUNNING giúp các worker khác không chọn lại hàng.

Nếu A rollback trước khi commit trạng thái RUNNING, hàng 101 trở lại trạng thái READY và có thể được worker khác claim.

## 15. Chọn WAIT hay SKIP LOCKED cho thao tác người dùng và worker

### 15.1. Màn hình chỉnh sửa một đơn hàng

Người dùng mở đơn hàng và muốn biết ngay có người khác đang sửa:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE order_id = :order_id
FOR UPDATE NOWAIT;
```

Nếu bận, trả thông báo xung đột. Đây là trường hợp NOWAIT dễ hiểu.

Nếu người dùng chấp nhận chờ ngắn:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = :order_id
FOR UPDATE WAIT 3;
```

### 15.2. Worker xử lý queue

Worker không nhất thiết phải đợi một job đang bị worker khác claim. Nó có thể nhận job khác:

```sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
  AND available_at <= SYSTIMESTAMP
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

SKIP LOCKED phù hợp hơn vì mục tiêu là tăng số job được xử lý song song, không phải thông báo xung đột cho người dùng.

### 15.3. Khi không có hàng khả dụng

Worker có thể:

- Chờ một khoảng ngắn rồi thử lại.
- Dùng backoff tăng dần khi queue trống.
- Ngủ theo tín hiệu/notification từ hệ thống điều phối.
- Kiểm tra số job READY và số job RUNNING để quan sát tải.

Không vòng lặp SELECT SKIP LOCKED liên tục không nghỉ vì sẽ tạo tải polling không cần thiết.

## 16. Lưu ý về thứ tự, fairness và starvation

### 16.1. ORDER BY là thứ tự ưu tiên, không phải bảo đảm FIFO tuyệt đối

```sql
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED
```

Worker chọn theo thứ tự này trong số hàng có thể claim. Nếu job đầu danh sách đang bị khóa, worker bỏ qua và nhận job tiếp theo.

### 16.2. Job có thể bị trì hoãn lâu

Nếu một job liên tục không được claim do bị khóa lâu, hoặc liên tục bị job ưu tiên cao hơn chiếm trước, job đó có thể chờ lâu. Theo dõi:

- Tuổi của job READY lâu nhất.
- Thời gian từ CREATED_AT đến CLAIMED_AT.
- Thời gian ở trạng thái RUNNING.
- Số lần retry.
- Số job lease hết hạn.
- Số job FAILED.

Có thể thiết kế aging priority, chia queue theo loại hoặc giới hạn số job ưu tiên cao liên tiếp để tăng fairness.

### 16.3. Batch lớn làm giảm tính linh hoạt

Một worker claim 1.000 job rồi xử lý tuần tự có thể khiến các worker khác không còn hàng để lấy, dù worker đầu chỉ xử lý được một số nhỏ tại một thời điểm. Chọn batch gần với năng lực xử lý đồng thời thực tế.

Batch nhỏ giảm thời gian khóa và giúp phân phối công việc linh hoạt hơn, nhưng tăng số transaction claim. Hãy đo theo workload.

## 17. Khóa trong truy vấn JOIN

Nếu queue cần đọc thêm thông tin khách hàng hoặc loại job, có thể JOIN:

```sql
SELECT q.job_id,
       q.payload,
       q.priority,
       t.type_name
FROM job_queue q
JOIN job_types t
  ON t.type_id = q.type_id
WHERE q.status = 'READY'
ORDER BY q.priority DESC, q.created_at, q.job_id
FOR UPDATE OF q.status SKIP LOCKED;
```

`OF q.status` chỉ định bảng queue là bảng cần khóa. Cột `STATUS` là đại diện để chỉ ra bảng; Oracle khóa hàng trong bảng chứa cột đó, không khóa riêng cột status.

Tránh khóa bảng tra cứu `JOB_TYPES` nếu worker chỉ cần khóa job. Khi truy vấn JOIN phức tạp, kiểm tra giới hạn của `FOR UPDATE` đối với view, outer join, aggregate hoặc các cấu trúc khác theo phiên bản Oracle.

## 18. Những lỗi và giới hạn thường gặp

| Lỗi/hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `ORA-00054` | NOWAIT gặp tài nguyên đang bận | Báo xung đột hoặc retry có backoff |
| `ORA-30006` | WAIT hết thời gian | Điều chỉnh timeout theo SLA hoặc xử lý timeout |
| `ORA-00060` | Deadlock do các session khóa tài nguyên theo thứ tự xung đột | Khóa theo thứ tự nhất quán, giữ transaction ngắn, retry có kiểm soát |
| Queue trả 0 hàng | Queue rỗng hoặc mọi hàng phù hợp đang bị khóa/chưa đến giờ | Xem là không có job hiện claim được; thử lại sau |
| Job được xử lý hai lần | Chỉ SELECT FOR UPDATE rồi COMMIT mà không đổi trạng thái, hoặc retry sau crash | Đổi READY -> RUNNING trong cùng transaction, dùng idempotency |
| Job RUNNING mãi | Worker crash, không có lease recovery | Dùng lease, heartbeat và tác vụ phục hồi |
| Worker cũ ghi đè worker mới | Không kiểm tra claim token/version khi hoàn tất | Guard mọi update bằng token hiện tại |
| Job ưu tiên thấp chờ quá lâu | SKIP LOCKED không bảo đảm fairness | Aging priority, phân nhóm queue và giám sát tuổi job |
| `FOR UPDATE` không chạy với query | Query dùng DISTINCT/GROUP BY/set operator/aggregate hoặc view không khóa được | Khóa hàng cơ sở bằng query phù hợp |
| `SKIP LOCKED` vẫn chờ | Có table lock hoặc loại chờ khác, không phải row lock mà SKIP LOCKED bỏ qua | Kiểm tra loại lock và blocker |
| Batch khóa quá nhiều hàng | Claim batch quá lớn hoặc transaction chưa commit | Giảm batch, commit ngay sau claim |
| Không lấy được job dù READY tồn tại | Điều kiện `AVAILABLE_AT`, trạng thái hoặc quyền sở hữu không phù hợp | Kiểm tra predicate, lease và metadata |

### 18.1. ORA-00060 và thứ tự khóa

Deadlock có thể xảy ra nếu:

- Session A khóa hàng 1 rồi chờ hàng 2.
- Session B khóa hàng 2 rồi chờ hàng 1.

Một quy tắc thiết kế thường hữu ích là mọi quy trình khóa nhiều hàng theo cùng một thứ tự khóa. Điều này không loại bỏ mọi deadlock nhưng giảm nguy cơ. Ứng dụng vẫn cần xử lý lỗi và retry transaction khi thích hợp.

### 18.2. SKIP LOCKED không chữa dữ liệu sai

SKIP LOCKED chỉ điều phối cạnh tranh khóa. Nó không xác minh payload, không bảo đảm trạng thái nghiệp vụ đúng và không chống xử lý trùng do worker crash sau side effect. Queue vẫn cần constraint, state transition hợp lệ, idempotency và giám sát.

## 19. Hiệu năng và thiết kế vận hành

### 19.1. Predicate phải chọn lọc

Truy vấn claim nên lọc trạng thái và thời điểm sẵn sàng:

```sql
WHERE status = 'READY'
  AND available_at <= SYSTIMESTAMP
```

Nếu không có điều kiện, worker có thể quét và khóa các hàng không cần thiết.

### 19.2. Index cho queue

Index ứng viên:

```sql
CREATE INDEX ix_job_queue_status_ready
ON job_queue (status, available_at, priority DESC, created_at, job_id);
```

Tuy nhiên, điều kiện range trên `AVAILABLE_AT` và thứ tự ưu tiên có thể khiến Oracle vẫn cần sort. Tùy phân bố dữ liệu, một index khác hoặc partitioning có thể phù hợp hơn. Đo execution plan với dữ liệu gần thực tế.

### 19.3. Giữ transaction claim ngắn

Transaction claim chỉ nên:

1. Tìm hàng.
2. Khóa hàng.
3. Cập nhật trạng thái và metadata.
4. COMMIT.

Đừng gọi API ngoài, gửi email hoặc xử lý file trong transaction này.

### 19.4. Dùng batch vừa đủ

Batch lớn giảm số lần claim nhưng làm một worker giữ nhiều job hơn, có thể gây mất cân bằng khi worker chậm. Batch nhỏ tăng tính linh hoạt nhưng tăng overhead transaction. Chọn theo throughput và thời gian xử lý job.

### 19.5. Giám sát hàng bị kẹt

Các chỉ số nên theo dõi:

- Số READY theo tuổi và priority.
- Số RUNNING theo worker.
- Job quá hạn lease.
- Attempts trung bình và số job đạt max attempts.
- Thời gian xử lý p50/p95/p99.
- Số lần claim rỗng.
- Số lần lỗi khóa và retry.

Giám sát giúp phân biệt queue thiếu worker, worker chậm, payload lỗi, lock contention và hệ thống đích đang không khả dụng.

### 19.6. Cân nhắc Oracle Advanced Queuing

Với hệ thống cần queue có tính năng phong phú như consumer, enqueue/dequeue, retry, delay, exception queue và quản lý message, hãy cân nhắc Oracle Advanced Queuing (AQ) hoặc giải pháp messaging phù hợp. Bảng tự xây với SKIP LOCKED phù hợp khi quy trình đơn giản và cần kiểm soát schema trực tiếp, nhưng đội ngũ phải tự xây các phần lease, retry, retention, monitoring và idempotency.

## 20. Sử dụng NOWAIT, WAIT và SKIP LOCKED trong Java/JDBC

### 20.1. NOWAIT với PreparedStatement

```java
String sql =
    "SELECT order_id, status " +
    "FROM orders " +
    "WHERE order_id = ? " +
    "FOR UPDATE NOWAIT";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String status = rs.getString("status");
            // Kiểm tra và cập nhật trong cùng transaction.
        }
    }
}
```

Nếu gặp lỗi khóa, driver ném `SQLException`; ứng dụng nên phân loại mã lỗi Oracle thay vì coi mọi SQL exception là xung đột.

### 20.2. WAIT n

```java
String sql =
    "SELECT order_id, status " +
    "FROM orders " +
    "WHERE order_id = ? " +
    "FOR UPDATE WAIT 5";
```

`WAIT 5` là cú pháp SQL. Không ghép số giây do người dùng nhập trực tiếp vào SQL; nếu cần cấu hình động, validate giá trị theo whitelist/range ở ứng dụng và tạo statement phù hợp.

### 20.3. Claim queue bằng JDBC

Với queue, một cách triển khai là gọi PL/SQL procedure thực hiện claim trong transaction ngắn và trả về claim token. Procedure nên:

- Mở cursor `FOR UPDATE SKIP LOCKED`.
- Fetch tối đa batch size.
- Đổi trạng thái thành RUNNING và gắn token/lease.
- Commit hoặc để transaction manager commit sau khi procedure hoàn tất.
- Trả danh sách job ID/token cho worker.

Không nên mở một `ResultSet` FOR UPDATE rồi giữ connection trong suốt thời gian xử lý job ngoài database.

### 20.4. Transaction JDBC

```java
connection.setAutoCommit(false);

try {
    // Gọi procedure claim job; procedure chỉ khóa và cập nhật trạng thái.
    // Lấy danh sách job đã claim.
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}

// Xử lý payload ngoài transaction claim.
```

Sau khi xử lý, mở transaction ngắn khác để cập nhật DONE/READY/FAILED với điều kiện `job_id`, `status` và `claim_token`. Nếu connection pool quản lý transaction, hãy tuân theo transaction manager của ứng dụng thay vì tự ý commit ở nhiều tầng.

## 21. Bài thực hành tổng hợp

Các bước sau tạo bảng riêng trong schema lab. Chỉ chạy khi có quyền tạo bảng và không dùng tên trùng với đối tượng nghiệp vụ.

### Bước 1. Tạo bảng queue

```sql
CREATE TABLE demo_job_queue (
    job_id NUMBER GENERATED ALWAYS AS IDENTITY
        CONSTRAINT pk_demo_job_queue PRIMARY KEY,
    payload VARCHAR2(200) NOT NULL,
    status VARCHAR2(16) DEFAULT 'READY' NOT NULL,
    priority NUMBER DEFAULT 0 NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    worker_id VARCHAR2(64),
    claim_token RAW(16),
    claimed_at TIMESTAMP WITH TIME ZONE,
    lease_until TIMESTAMP WITH TIME ZONE,
    CONSTRAINT ck_demo_job_status
        CHECK (status IN ('READY', 'RUNNING', 'DONE'))
);
```

### Bước 2. Thêm một số job

```sql
INSERT INTO demo_job_queue (payload, priority)
VALUES ('Job A', 10);

INSERT INTO demo_job_queue (payload, priority)
VALUES ('Job B', 20);

INSERT INTO demo_job_queue (payload, priority)
VALUES ('Job C', 5);

COMMIT;
```

### Bước 3. Session A khóa job đầu tiên

```sql
SELECT job_id, payload
FROM demo_job_queue
WHERE status = 'READY'
ORDER BY priority DESC, job_id
FOR UPDATE;
```

Giữ transaction mở trong Session A để quan sát xung đột.

### Bước 4. Session B thử NOWAIT

```sql
SELECT job_id, payload
FROM demo_job_queue
WHERE job_id = 2
FOR UPDATE NOWAIT;
```

Nếu Session A đang khóa job 2, Session B nhận lỗi ngay.

### Bước 5. Session B thử WAIT

```sql
SELECT job_id, payload
FROM demo_job_queue
WHERE job_id = 2
FOR UPDATE WAIT 3;
```

Giữ khóa ở Session A quá ba giây để quan sát timeout, hoặc COMMIT ở A trong thời gian chờ để B lấy được khóa.

### Bước 6. Session B thử SKIP LOCKED

```sql
SELECT job_id, payload
FROM demo_job_queue
WHERE status = 'READY'
ORDER BY priority DESC, job_id
FOR UPDATE SKIP LOCKED;
```

Quan sát các hàng đang bị A khóa bị bỏ qua và các hàng khác có thể được trả về. Sau thử nghiệm, COMMIT hoặc ROLLBACK ở cả hai session.

### Bước 7. Claim và đổi trạng thái trong cùng transaction

Trong Session A, chạy PL/SQL:

```sql
DECLARE
    v_job_id demo_job_queue.job_id%TYPE;
    v_token RAW(16) := SYS_GUID();
    CURSOR c IS
        SELECT job_id
        FROM demo_job_queue
        WHERE status = 'READY'
        ORDER BY priority DESC, job_id
        FOR UPDATE SKIP LOCKED;
BEGIN
    OPEN c;
    FETCH c INTO v_job_id;

    IF c%FOUND THEN
        UPDATE demo_job_queue
        SET status = 'RUNNING',
            worker_id = 'worker-lab-A',
            claim_token = v_token,
            claimed_at = SYSTIMESTAMP,
            lease_until = SYSTIMESTAMP + INTERVAL '2' MINUTE
        WHERE CURRENT OF c;

        DBMS_OUTPUT.PUT_LINE('JOB_ID=' || v_job_id);
        DBMS_OUTPUT.PUT_LINE('TOKEN=' || RAWTOHEX(v_token));
    END IF;

    CLOSE c;
    COMMIT;
END;
/
```

### Bước 8. Kiểm tra job đã được claim

```sql
SELECT job_id,
       payload,
       status,
       worker_id,
       claimed_at,
       lease_until
FROM demo_job_queue
ORDER BY job_id;
```

Job đã claim chuyển thành RUNNING. Worker khác lọc READY sẽ không nhận lại job ấy.

### Bước 9. Đánh dấu hoàn tất

Dùng job ID và token vừa in ở bước 7:

```sql
UPDATE demo_job_queue
SET status = 'DONE',
    worker_id = NULL,
    claim_token = NULL,
    lease_until = NULL
WHERE job_id = :job_id
  AND status = 'RUNNING'
  AND claim_token = HEXTORAW(:token_hex);

COMMIT;
```

Kiểm tra số hàng cập nhật. Nếu bằng 0, claim có thể không còn thuộc worker này.

### Bước 10. Dọn bảng thực hành

Chỉ khi chắc chắn đây là bảng do bạn tạo và không cần giữ dữ liệu:

```sql
DROP TABLE demo_job_queue PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin theo hành vi lệnh; đây là DDL có commit ngầm. Không chạy trên bảng nghiệp vụ hoặc đối tượng dùng chung.

## 22. Quy tắc ghi nhớ

| Nhu cầu | Lựa chọn |
|---|---|
| Đọc một hàng rồi cập nhật trong cùng transaction | `SELECT ... FOR UPDATE` |
| Báo ngay khi hàng đang bị khóa | `FOR UPDATE NOWAIT` |
| Chờ khóa trong thời gian giới hạn | `FOR UPDATE WAIT n` |
| Nhiều worker lấy các hàng khả dụng khác nhau | `FOR UPDATE SKIP LOCKED` |
| Chỉ khóa hàng của một bảng trong JOIN | `FOR UPDATE OF alias.column` |
| Claim job an toàn | Lock + đổi READY thành RUNNING + token/lease + COMMIT |
| Xử lý job dài | Thực hiện sau khi transaction claim đã commit |
| Worker crash | Lease timeout và cơ chế reclaim |
| Ngăn worker cũ cập nhật sau reclaim | Điều kiện claim token/version |
| Retry job | Attempts, backoff, max attempts, trạng thái FAILED |
| Hạn chế xử lý side effect trùng | Idempotency key hoặc fencing ở hệ thống đích |
| Đảm bảo transaction ngắn | Không gọi dịch vụ ngoài khi đang giữ row lock |

## 23. Câu hỏi tự kiểm tra

**Câu 1.** `SELECT FOR UPDATE` khác SELECT thông thường ở đâu?

**Trả lời:** SELECT FOR UPDATE chủ động lấy row locks trên các hàng được chọn để bảo vệ thao tác đọc rồi cập nhật trong transaction; SELECT thông thường dùng read consistency và không khóa hàng chỉ để đọc.

**Câu 2.** NOWAIT có hành vi gì khi hàng đang bị khóa?

**Trả lời:** Trả lỗi ngay, thường là ORA-00054, thay vì chờ.

**Câu 3.** `WAIT 5` có nghĩa gì?

**Trả lời:** Chờ tối đa năm giây để lấy khóa; hết thời gian thì câu lệnh timeout.

**Câu 4.** SKIP LOCKED phù hợp nhất với tình huống nào?

**Trả lời:** Nhiều worker/consumer cùng nhận việc từ queue và có thể bỏ qua hàng đang được worker khác xử lý.

**Câu 5.** SKIP LOCKED trả 0 hàng có chắc queue rỗng không?

**Trả lời:** Không. Các hàng phù hợp có thể đang bị khóa hoặc chưa đến thời điểm AVAILABLE_AT.

**Câu 6.** Khóa do SELECT FOR UPDATE được giữ đến khi nào?

**Trả lời:** Đến COMMIT hoặc ROLLBACK của transaction; đóng cursor không tự giải phóng khóa.

**Câu 7.** Vì sao worker phải cập nhật READY thành RUNNING trước COMMIT?

**Trả lời:** Sau COMMIT row lock được giải phóng; trạng thái RUNNING ngăn worker khác chọn lại cùng job.

**Câu 8.** Vì sao không giữ transaction trong khi gửi email hoặc gọi API?

**Trả lời:** Điều đó giữ row locks và connection quá lâu, làm tăng contention và nguy cơ chờ.

**Câu 9.** Lease giải quyết vấn đề gì?

**Trả lời:** Cho phép phục hồi job nếu worker crash hoặc không hoàn tất trong thời gian quy định.

**Câu 10.** Claim token có tác dụng gì?

**Trả lời:** Phân biệt lần claim hiện tại; worker cũ không thể cập nhật trạng thái nếu token đã đổi sau khi job được reclaim.

**Câu 11.** Claim token có bảo đảm side effect bên ngoài chỉ xảy ra một lần không?

**Trả lời:** Không. Cần idempotency key, fencing hoặc giao thức với hệ thống đích; queue có retry thường có semantics at-least-once.

**Câu 12.** SKIP LOCKED có bảo đảm FIFO tuyệt đối không?

**Trả lời:** Không. Hàng ưu tiên cao đang bị khóa có thể bị bỏ qua để xử lý hàng sau.

**Câu 13.** `FOR UPDATE OF q.status` khóa riêng cột STATUS hay khóa gì?

**Trả lời:** Nó chỉ định bảng chứa cột STATUS là bảng cần khóa; Oracle khóa hàng của bảng đó, không khóa riêng cột.

**Câu 14.** Có thể luôn dùng FETCH FIRST 10 ROWS ONLY cùng FOR UPDATE không?

**Trả lời:** Không nên giả định. Oracle có hạn chế kết hợp row-limiting clause với FOR UPDATE; dùng cursor và giới hạn số lần FETCH để kiểm soát batch.

## 24. Kết luận

`SELECT ... FOR UPDATE` cho phép ứng dụng lấy khóa hàng ngay khi đọc dữ liệu. **`NOWAIT`** trả lỗi ngay nếu không lấy được khóa; **`WAIT n`** chờ trong một khoảng hữu hạn; **`SKIP LOCKED`** bỏ qua hàng đang bị khóa để tiếp tục với hàng khả dụng. NOWAIT và WAIT phù hợp với thao tác cần phản hồi hoặc chờ có giới hạn, còn SKIP LOCKED là lựa chọn quan trọng cho mô hình nhiều worker cùng nhận việc từ một bảng.

Một queue an toàn không chỉ SELECT SKIP LOCKED. Worker phải khóa hàng, chuyển trạng thái READY sang RUNNING, ghi worker/token/lease và COMMIT trong transaction ngắn. Công việc dài được thực hiện sau đó; khi thành công hoặc thất bại, worker cập nhật trạng thái bằng điều kiện token hiện tại. Lease giúp thu hồi job bị bỏ dở, còn idempotency/fencing bảo vệ các side effect khi một job phải retry.

SKIP LOCKED tăng khả năng xử lý song song nhưng không bảo đảm FIFO tuyệt đối, không bỏ qua mọi loại lock và không tự cung cấp exactly-once. Hãy chọn batch phù hợp, giữ transaction ngắn, theo dõi lease và tuổi job, thiết kế retry có backoff, đồng thời kiểm tra execution plan và hành vi trên đúng phiên bản Oracle đang triển khai.
