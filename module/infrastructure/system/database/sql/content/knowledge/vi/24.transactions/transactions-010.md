# NOWAIT, SKIP LOCKED và ngữ nghĩa tập kết quả

Trong ứng dụng nhiều người dùng, có lúc hai giao dịch cùng muốn xử lý một hàng dữ liệu. Ví dụ hai worker cùng tìm “công việc đang chờ có độ ưu tiên cao nhất” trong bảng hàng đợi; hoặc hai nhân viên cùng muốn sửa thông tin của một đơn hàng. Nếu cả hai cùng đọc và sửa không có cơ chế phối hợp, hệ thống có thể xử lý trùng công việc, ghi đè thay đổi hoặc phải chờ khóa quá lâu.

Các hệ quản trị quan hệ cung cấp **khóa giao dịch (*locks*)** để điều phối việc truy cập đồng thời. Với truy vấn khóa hàng, hai lựa chọn quan trọng là:

- **`NOWAIT`**: nếu không thể lấy khóa hàng ngay vì giao dịch khác đang giữ khóa xung đột, **báo lỗi thay vì chờ**.
- **`SKIP LOCKED`**: khi gặp hàng đang bị khóa xung đột, **bỏ qua hàng đó và tiếp tục tìm những hàng khác có thể khóa**.

Hai lựa chọn này làm thay đổi **cách truy vấn ứng xử khi tranh chấp** và đặc biệt là **ý nghĩa của tập kết quả**. Một truy vấn `SKIP LOCKED` trả 0 hàng **không chứng minh** bảng không còn hàng thỏa điều kiện; có thể các hàng đó đang bị worker khác giữ khóa. Ngược lại, truy vấn `NOWAIT` có thể **ném lỗi khóa**, chứ không trả “không tìm thấy dữ liệu”.

Bài học đặt các kỹ thuật này trong ngữ cảnh **Giao dịch SQL**, giải thích bằng ví dụ PostgreSQL với hai phiên kết nối độc lập, sau đó đối chiếu MySQL, Oracle, SQL Server và SQLite. Chúng ta cũng xây dựng mẫu **nhận công việc từ hàng đợi một cách nguyên tử**, phân tích độ công bằng, giới hạn thời gian chờ, transaction, lỗi đồng thời và cách diễn giải số hàng trả về.

> Các đoạn `BEGIN`, `SELECT ... FOR UPDATE` và `UPDATE` nên được thực hành trong database thử nghiệm. Để quan sát hiện tượng tranh chấp khóa, cần **hai kết nối độc lập** tới cùng database. Một cửa sổ SQL chạy nối tiếp không thể mô phỏng hai giao dịch đồng thời đang giữ khóa cho nhau.

## 1. Khóa hàng trong giao dịch là gì?

Một giao dịch có thể cần bảo vệ một hàng khỏi việc giao dịch khác sửa hoặc xóa trong lúc nó đang quyết định hành động. Trên PostgreSQL, `SELECT ... FOR UPDATE` yêu cầu **khóa hàng được chọn** để ngăn những thao tác cạnh tranh không tương thích cho đến khi giao dịch giải phóng khóa.

Ví dụ:

```sql
BEGIN;

SELECT job_id, state, priority
FROM job_queue
WHERE job_id = 101
FOR UPDATE;

-- Giao dịch vẫn mở: khóa hàng 101 chưa được giải phóng.

COMMIT;
```

Nếu một giao dịch khác cũng yêu cầu khóa xung đột trên hàng 101 trong khoảng giữa `BEGIN` và `COMMIT`, nó có thể phải **chờ**. Thời điểm khóa được giải phóng thông thường là lúc giao dịch **`COMMIT` hoặc `ROLLBACK`**. Trong một số tình huống rollback về savepoint cũng có thể giải phóng những khóa được lấy sau savepoint, theo quy tắc DBMS.

### 1.1. Phân biệt khóa hàng và việc đọc dữ liệu

Trên PostgreSQL với cơ chế MVCC, một truy vấn `SELECT` thông thường thường có thể **đọc phiên bản đã commit** của hàng ngay cả khi một giao dịch khác đang giữ khóa hàng để cập nhật. Nhưng:

```sql
SELECT ...
FROM job_queue
WHERE job_id = 101
FOR UPDATE;
```

không chỉ đọc: nó còn cố **lấy khóa trên hàng**, nên có thể chờ. Hai câu `SELECT` trả cùng cột nhưng có **ngữ nghĩa đồng thời khác nhau**.

### 1.2. FOR UPDATE không phải là thao tác cập nhật

`SELECT ... FOR UPDATE` **không tự sửa `state` hoặc `quantity`**. Nó đặt khóa để giao dịch có thể quyết định thao tác tiếp theo. Muốn thay đổi trạng thái một công việc, vẫn cần một câu `UPDATE`.

Không nên giữ khóa trong thời gian dài chỉ để “đánh dấu công việc đang chạy”. Khóa hàng là trạng thái **tạm thời của giao dịch**; sau `COMMIT` hoặc `ROLLBACK`, khóa không còn giữ. Muốn ghi nhận **quyền sở hữu công việc lâu dài**, cần một cột trạng thái hoặc cơ chế thuê (*lease*) được lưu vào bảng.

### 1.3. Ba lựa chọn khi gặp hàng đang bị khóa

Giả sử giao dịch A đã giữ khóa độc quyền cần thiết trên hàng 101, giao dịch B muốn đọc và khóa hàng đó:

| Truy vấn của giao dịch B | Khi hàng 101 đang có khóa xung đột | Điều cần hiểu |
|---|---|---|
| `FOR UPDATE` | Thường **chờ** cho tới khi có thể lấy khóa, hoặc đến khi bị hủy/timeout | Chờ không phải đồng nghĩa deadlock |
| `FOR UPDATE NOWAIT` | **Báo lỗi ngay** khi không lấy được khóa hàng | Đây là lỗi tranh chấp, không phải hàng không tồn tại |
| `FOR UPDATE SKIP LOCKED` | **Bỏ qua hàng đang khóa**, tìm hàng phù hợp khác nếu có | Kết quả có thể thiếu hàng thỏa `WHERE` |

Trên PostgreSQL, `NOWAIT` và `SKIP LOCKED` là **hai lựa chọn loại trừ nhau trong cùng một locking clause**. Không ghép `FOR UPDATE NOWAIT SKIP LOCKED`.

## 2. Bộ dữ liệu hàng đợi để thực hành

Các ví dụ chính dùng PostgreSQL. Tạo bảng mới trong database luyện tập:

```sql
CREATE TABLE job_queue (
    job_id INTEGER PRIMARY KEY,
    job_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')),
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    worker_id TEXT,
    claimed_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
```

Các trường quan trọng:

- `job_id`: khóa chính duy nhất của từng công việc.
- `state`: `PENDING` đang chờ; `RUNNING` đã được nhận; `DONE` hoàn tất; `FAILED` lỗi theo quy tắc của ứng dụng.
- `priority`: số lớn hơn được ưu tiên trước.
- `created_at`: thời điểm tạo, dùng để ưu tiên công việc cũ hơn khi cùng priority.
- `attempts`: số lần nhận công việc; hỗ trợ retry và xác minh phiên xử lý.
- `worker_id`, `claimed_at`, `lease_until`: thông tin worker đang nhận và thời hạn thuê.
- `payload`: thông tin công việc. Trong hệ thống thật có thể chứa ID bản ghi liên quan thay vì toàn bộ nội dung nhạy cảm.

### 2.1. Dữ liệu mẫu

```sql
INSERT INTO job_queue
    (job_id, job_type, payload, state, priority, created_at,
     attempts, worker_id, claimed_at, lease_until, finished_at)
VALUES
    (101, 'EMAIL',   'send welcome A',  'PENDING', 100,
     TIMESTAMPTZ '2025-10-01 08:00:00+00', 0, NULL, NULL, NULL, NULL),
    (102, 'EMAIL',   'send welcome B',  'PENDING', 90,
     TIMESTAMPTZ '2025-10-01 08:01:00+00', 0, NULL, NULL, NULL, NULL),
    (103, 'REPORT',  'daily report',    'PENDING', 90,
     TIMESTAMPTZ '2025-10-01 08:02:00+00', 0, NULL, NULL, NULL, NULL),
    (104, 'INVOICE', 'generate invoice','PENDING', 80,
     TIMESTAMPTZ '2025-10-01 08:03:00+00', 0, NULL, NULL, NULL, NULL),
    (105, 'EMAIL',   'send reminder',   'RUNNING', 70,
     TIMESTAMPTZ '2025-10-01 08:04:00+00', 1, 'worker-old',
     TIMESTAMPTZ '2025-10-01 08:05:00+00',
     TIMESTAMPTZ '2025-10-01 08:10:00+00', NULL),
    (106, 'REPORT',  'weekly report',   'DONE', 60,
     TIMESTAMPTZ '2025-10-01 08:05:00+00', 1, 'worker-old',
     TIMESTAMPTZ '2025-10-01 08:06:00+00', NULL,
     TIMESTAMPTZ '2025-10-01 08:07:00+00'),
    (107, 'EMAIL',   'send follow-up',  'PENDING', 50,
     TIMESTAMPTZ '2025-10-01 08:06:00+00', 0, NULL, NULL, NULL, NULL),
    (108, 'REPORT',  'retry old task',  'FAILED', 40,
     TIMESTAMPTZ '2025-10-01 08:07:00+00', 2, NULL, NULL, NULL, NULL);
```

Trạng thái đầu vào:

| job_id | state | priority | created_at (UTC) | Vai trò trong bài |
|---:|---|---:|---|---|
| 101 | PENDING | 100 | 08:00 | Hàng ưu tiên cao nhất, sẽ bị A khóa |
| 102 | PENDING | 90 | 08:01 | Hàng tiếp theo, B có thể nhận |
| 103 | PENDING | 90 | 08:02 | Cùng priority 102 nhưng tạo sau |
| 104 | PENDING | 80 | 08:03 | Hàng chờ thấp hơn |
| 105 | RUNNING | 70 | 08:04 | Đã được nhận từ trước |
| 106 | DONE | 60 | 08:05 | Đã hoàn tất |
| 107 | PENDING | 50 | 08:06 | Hàng chờ thấp nhất |
| 108 | FAILED | 40 | 08:07 | Lỗi, chưa được đưa lại vào hàng chờ |

Bảng có **8 hàng**, trong đó có **5 hàng `PENDING`**: 101, 102, 103, 104, 107.

```sql
SELECT job_id, state, priority
FROM job_queue
WHERE state = 'PENDING'
ORDER BY priority DESC, created_at ASC, job_id ASC;
```

Kết quả: **101, 102, 103, 104, 107**. Đây là truy vấn **đọc thông thường**. Nó không có nghĩa một worker đã lấy quyền xử lý những hàng này.

### 2.2. Sắp xếp xác định bằng khóa phụ

Thứ tự của hàng chờ là:

```sql
ORDER BY priority DESC, created_at ASC, job_id ASC
```

Nó có nghĩa:

1. Priority lớn hơn trước.
2. Nếu bằng priority, công việc tạo **sớm hơn** trước.
3. Nếu cùng thời điểm, `job_id` nhỏ hơn trước để phân định duy nhất.

`job_id` là khóa chính, nên thứ tự này xác định trên một tập dữ liệu không đổi. **Tuy nhiên, thứ tự ưu tiên mong muốn không biến `SKIP LOCKED` thành FIFO tuyệt đối:** một hàng ưu tiên cao có thể bị khóa và bị bỏ qua, làm hàng ưu tiên thấp được nhận trước.

## 3. PostgreSQL FOR UPDATE: chờ khóa theo mặc định

Giả sử ta mở **hai kết nối riêng**, gọi là **Phiên A** và **Phiên B**, tới cùng database.

### 3.1. Phiên A giữ khóa hàng 101

Chạy ở **Phiên A**:

```sql
BEGIN;

SELECT job_id, state, priority
FROM job_queue
WHERE job_id = 101
FOR UPDATE;

-- Kết quả: 101 | PENDING | 100
-- ĐỂ GIAO DỊCH MỞ; chưa COMMIT hoặc ROLLBACK.
```

Ngay sau `SELECT ... FOR UPDATE`, A đã giữ khóa cần thiết trên hàng 101 và chưa giải phóng.

### 3.2. Phiên B muốn khóa cùng hàng

Chạy ở **Phiên B** khi A vẫn giữ khóa:

```sql
BEGIN;

SELECT job_id, state, priority
FROM job_queue
WHERE job_id = 101
FOR UPDATE;
```

Thông thường B sẽ **chờ** vì A đang giữ khóa xung đột. B không lập tức nhận được “0 hàng”; hàng 101 **vẫn tồn tại**. Nếu A `COMMIT` hoặc `ROLLBACK` và không còn giữ khóa xung đột, B có thể tiếp tục.

Trong khi B đang chờ, chuyển lại **Phiên A**:

```sql
COMMIT;
```

Khi A giải phóng khóa, B có thể nhận hàng 101. Sau đó, ở **Phiên B**:

```sql
COMMIT;
```

Khi thực hành theo chuỗi lệnh này, không nên nhập lệnh tiếp theo trên một cửa sổ đang bị chặn và mong nó tự thực thi trước khi câu đang chờ kết thúc. Hãy sử dụng đúng **hai phiên kết nối**.

### 3.3. Chờ khóa không đồng nghĩa deadlock

Một giao dịch chờ giao dịch khác giải phóng khóa là **lock wait** thông thường. **Deadlock** xuất hiện khi có vòng chờ, chẳng hạn:

```text
Giao dịch A đã khóa hàng 101, chờ hàng 102.
Giao dịch B đã khóa hàng 102, chờ hàng 101.
```

DBMS thường có cơ chế phát hiện deadlock và hủy một giao dịch. `NOWAIT` có thể giúp một câu lệnh **không chờ** khi không lấy được khóa, còn `SKIP LOCKED` có thể giảm tranh chấp trong một số mẫu queue; nhưng chúng **không loại bỏ mọi khả năng deadlock** trong toàn bộ transaction có nhiều thao tác khác.

## 4. NOWAIT: không lấy được khóa thì báo lỗi

Lặp lại trạng thái ban đầu, bảo đảm A và B đã kết thúc transaction thử nghiệm trước đó. Sau đó khóa hàng 101 ở A:

**Phiên A:**

```sql
BEGIN;

SELECT job_id
FROM job_queue
WHERE job_id = 101
FOR UPDATE;

-- Giữ giao dịch mở.
```

**Phiên B:**

```sql
BEGIN;

SELECT job_id
FROM job_queue
WHERE job_id = 101
FOR UPDATE NOWAIT;
```

Trên PostgreSQL, B nhận lỗi tương ứng với **không lấy được khóa ngay**, thường có SQLSTATE **`55P03`** (`lock_not_available`).

Ví dụ nội dung lỗi có thể có dạng:

```text
ERROR: could not obtain lock on row in relation "job_queue"
```

**Đây không phải kết quả 0 hàng.** Câu `SELECT` đã **thất bại** vì không lấy được khóa. Ứng dụng phải xử lý trường hợp lỗi riêng với tình huống truy vấn thành công và không có dữ liệu.

### 4.1. Sau lỗi NOWAIT trong transaction PostgreSQL

Trong PostgreSQL, nhiều lỗi SQL làm transaction hiện tại chuyển sang trạng thái **aborted**. Nếu Phiên B đã chạy `BEGIN` rồi `FOR UPDATE NOWAIT` lỗi, những lệnh tiếp theo trong transaction đó có thể nhận thông báo:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

Để làm sạch trạng thái **Phiên B**, chạy:

```sql
ROLLBACK;
```

Sau đó kết thúc **Phiên A**:

```sql
COMMIT;
```

Đừng viết code theo giả định rằng `NOWAIT` trả `NULL` hoặc danh sách rỗng khi gặp khóa. Với PostgreSQL, đó là **luồng xử lý exception**; có thể retry theo chính sách hoặc trả thông báo “đối tượng đang được xử lý”.

### 4.2. NOWAIT phù hợp khi nào?

Ví dụ hợp lý:

- Người dùng bấm “Chỉnh sửa đơn” và hệ thống muốn báo nhanh “đơn đang được phiên khác chỉnh sửa”, thay vì để màn hình treo.
- Worker muốn thử lấy một công việc **cụ thể** và chấp nhận báo bận nếu có người khác giữ khóa.
- Một thao tác bảo trì không được phép chờ hàng lâu vì độ trễ có giới hạn.

`NOWAIT` thích hợp khi **đối tượng cụ thể phải được bảo vệ hoặc báo bận rõ ràng**. Nếu mục tiêu là “cứ lấy một công việc khác nếu hàng đầu đang bận”, `SKIP LOCKED` thường diễn đạt ý định tốt hơn.

## 5. SKIP LOCKED: bỏ qua hàng đang bị khóa

Thử lại từ trạng thái dữ liệu ban đầu.

**Phiên A:** khóa 101 và giữ giao dịch:

```sql
BEGIN;

SELECT job_id
FROM job_queue
WHERE job_id = 101
FOR UPDATE;

-- Chưa kết thúc giao dịch A.
```

**Phiên B:** tìm một công việc `PENDING` có độ ưu tiên cao nhất nhưng không chờ hàng bị khóa:

```sql
BEGIN;

SELECT job_id, priority, state
FROM job_queue
WHERE state = 'PENDING'
ORDER BY priority DESC, created_at ASC, job_id ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

Trong bộ dữ liệu mẫu, khi chỉ có A khóa 101 và không có tranh chấp khác, B nhận:

```text
job_id | priority | state
-------+----------+--------
102    | 90       | PENDING
```

Vì sao B nhận **102** dù 101 có priority 100?

1. 101 thỏa điều kiện `WHERE state = 'PENDING'` nhưng đang bị A giữ khóa xung đột.
2. `SKIP LOCKED` không chờ 101 mà **bỏ qua** nó.
3. 102 là ứng viên có thứ tự ưu tiên cao nhất trong những hàng còn có thể khóa.
4. B lấy khóa trên 102 và trả hàng đó.

Khi hoàn thành quan sát, ở **Phiên B**:

```sql
ROLLBACK;
```

và ở **Phiên A**:

```sql
COMMIT;
```

Vì B chỉ `SELECT ... FOR UPDATE` mà chưa `UPDATE`, trạng thái `PENDING` của 102 **không thay đổi**; rollback chỉ giải phóng khóa B và hủy những thay đổi khác (nếu có) của giao dịch.

### 5.1. Một hàng đang khóa có thể “biến mất” khỏi kết quả

Giữ A đang khóa 101, rồi ở B chạy:

```sql
SELECT job_id
FROM job_queue
WHERE job_id = 101
FOR UPDATE SKIP LOCKED;
```

Kết quả của B có thể là **0 hàng**, dù hàng 101 vẫn đang tồn tại.

Trong cùng khoảng thời gian, một `SELECT` thông thường ở B:

```sql
SELECT job_id, state
FROM job_queue
WHERE job_id = 101;
```

vẫn có thể đọc **101 | PENDING** theo cơ chế MVCC của PostgreSQL và snapshot tương ứng, vì nó **không yêu cầu khóa hàng `FOR UPDATE`**.

Không có mâu thuẫn:

- Truy vấn đọc thông thường hỏi “có hàng nào nhìn thấy trong snapshot thỏa điều kiện?”.
- Truy vấn `FOR UPDATE SKIP LOCKED` hỏi thêm “có hàng nào vừa thỏa điều kiện, vừa có thể **lấy khóa ngay mà không chờ**?”.

**Tập kết quả của hai câu không bắt buộc giống nhau.**

### 5.2. SKIP LOCKED trả ít hàng không có nghĩa dữ liệu đã bị xóa

Giả sử 101 và 102 đều `PENDING` nhưng bị hai giao dịch khác khóa:

```sql
SELECT job_id
FROM job_queue
WHERE state = 'PENDING'
ORDER BY priority DESC, created_at, job_id
LIMIT 2
FOR UPDATE SKIP LOCKED;
```

Truy vấn có thể trả **103 và 104**, là những ứng viên đứng sau nhưng không bị khóa. Nếu tất cả năm hàng `PENDING` đều bị khóa, truy vấn có thể trả **0 hàng**.

Kết quả 0 hàng lúc này chỉ diễn đạt:

> “Trong lần đọc và theo quy tắc khóa hiện tại, không có hàng ứng viên nào tôi lấy được ngay.”

Nó **không** chứng minh:

> “Bảng hàng đợi đã hết công việc, tất cả công việc đã DONE, hoặc không cần kiểm tra lại.”

### 5.3. So sánh ba kết quả cùng một tình huống

Với A đang giữ khóa 101, B yêu cầu chính hàng 101:

| Truy vấn ở B | Kết quả có thể quan sát |
|---|---|
| `SELECT ... WHERE job_id=101` | Trả 101 theo snapshot đọc, không lấy khóa hàng |
| `SELECT ... WHERE job_id=101 FOR UPDATE` | Chờ A |
| `SELECT ... WHERE job_id=101 FOR UPDATE NOWAIT` | Lỗi khóa, ví dụ SQLSTATE `55P03` |
| `SELECT ... WHERE job_id=101 FOR UPDATE SKIP LOCKED` | Thành công với **0 hàng** vì bỏ qua 101 |

Sự khác biệt thuộc **ngữ nghĩa truy cập đồng thời**, không phải do điều kiện `WHERE` có nhiều cách viết.

## 6. Ngữ nghĩa tập kết quả: tại sao SKIP LOCKED cho một “cái nhìn không đầy đủ”?

SQL bình thường thường được dùng để trả lời câu hỏi “những hàng nào thỏa điều kiện?”. Khi thêm `SKIP LOCKED`, người đọc phải bổ sung một điều kiện **không được viết trong WHERE**: **“và hiện tại không gặp khóa xung đột cản trở việc lấy hàng”**.

### 6.1. Tập khớp điều kiện khác tập lấy được khóa

Đặt:

- `M`: tập hàng nhìn thấy và thỏa `WHERE` tại ngữ cảnh truy vấn.
- `L`: tập hàng có thể lấy được khóa theo chiến lược khóa của câu lệnh tại thời điểm xử lý.
- `R`: tập hàng thực sự trả về sau việc bỏ qua khóa, giới hạn và sắp xếp.

Về trực giác:

```text
Hàng khớp WHERE (M)
       |
       v
Bỏ qua hàng không khóa được ngay (SKIP LOCKED)
       |
       v
Giữ ứng viên có thể lấy khóa (L)
       |
       v
Áp dụng các quy tắc giới hạn/trả kết quả
       |
       v
Tập kết quả R
```

`R` có thể **nhỏ hơn** số hàng thỏa `WHERE`. Trong một hệ có cập nhật đồng thời, thời điểm xác định tập khớp và việc lấy khóa còn phụ thuộc MVCC/isolation; hình trên chỉ là mô hình tư duy, **không phải cam kết thứ tự vật lý mọi DBMS thực thi**.

### 6.2. NOWAIT và SKIP LOCKED trả lời hai câu hỏi nghiệp vụ khác nhau

`NOWAIT` phù hợp với:

> “Tôi muốn xử lý **hàng này**; nếu hàng đang bận, hãy **báo bận ngay**.”

`SKIP LOCKED` phù hợp với:

> “Tôi muốn lấy **một hàng bất kỳ phù hợp trong số các hàng đang lấy được ngay**; nếu một hàng đang bận, hãy chuyển sang hàng khác.”

Trong ứng dụng:

- Người dùng sửa một bản ghi cụ thể có thể cần **NOWAIT** để không chờ lâu và không sửa nhầm bản ghi khác.
- Hệ thống phân phối nhiều công việc độc lập có thể cần **SKIP LOCKED** để các worker ít tranh chấp và có thể tiếp tục xử lý phần việc khác.

Không thay `NOWAIT` bằng `SKIP LOCKED` chỉ để tránh exception nếu nghiệp vụ **bắt buộc xử lý đúng ID**.

### 6.3. Không sử dụng SKIP LOCKED cho báo cáo kiểm toán đầy đủ

Giả sử cần báo cáo “có bao nhiêu đơn `PENDING` lúc chốt kỳ?”. Dùng:

```sql
SELECT COUNT(*)
FROM job_queue
WHERE state = 'PENDING';
```

với snapshot/isolation phù hợp, thay vì dựa vào số hàng một truy vấn `FOR UPDATE SKIP LOCKED` lấy được. `SKIP LOCKED` có thể bỏ qua hàng do khóa, làm số lượng thấp hơn thực tế nhìn thấy.

Không nên dùng `SKIP LOCKED` cho các nghiệp vụ cần **một tập đầy đủ và nhất quán**, chẳng hạn kết sổ tài chính, đối soát tất cả giao dịch hoặc kiểm chứng không còn bản ghi chưa xử lý. Nó chủ yếu phù hợp với **công việc kiểu hàng đợi**, nơi chấp nhận tạm thời bỏ qua hàng bận và quay lại sau.

## 7. ORDER BY, LIMIT và sự công bằng của hàng đợi

Một câu chọn việc thường viết:

```sql
SELECT job_id
FROM job_queue
WHERE state = 'PENDING'
ORDER BY priority DESC, created_at ASC, job_id ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

Các phần có vai trò khác nhau:

- `WHERE state = 'PENDING'`: chỉ xét công việc đang chờ.
- `ORDER BY ...`: quy tắc ưu tiên ứng viên.
- `LIMIT 1`: cần một công việc.
- `FOR UPDATE`: lấy khóa hàng của ứng viên.
- `SKIP LOCKED`: không chờ những ứng viên có khóa xung đột.

### 7.1. LIMIT 1 không đảm bảo luôn có một hàng

Ngay cả khi có năm hàng `PENDING`, câu `LIMIT 1 ... SKIP LOCKED` có thể trả:

- **1 hàng** nếu có ứng viên khóa được.
- **0 hàng** nếu không có hàng thỏa điều kiện, hoặc các ứng viên đều đang bị khóa theo ngữ cảnh xử lý.

`LIMIT 1` đặt **giới hạn tối đa**, không bảo đảm số hàng tối thiểu.

### 7.2. ORDER BY không đảm bảo FIFO tuyệt đối khi có khóa

Nếu 101 luôn bị một transaction giữ khóa, các worker khác có thể liên tục nhận 102, 103, 104 hoặc 107 trước 101. Đây là hành vi mong đợi của `SKIP LOCKED`: **ưu tiên tiến độ công việc khác** thay vì bắt mọi worker đứng chờ một hàng.

Hậu quả là:

- Thứ tự hoàn thành có thể khác thứ tự `priority` hoặc `created_at`.
- Một hàng bận lâu có nguy cơ **starvation** (bị trì hoãn quá lâu).
- Các công việc phụ thuộc thứ tự nghiêm ngặt không nên được nhận tự do bằng `SKIP LOCKED` nếu không có cơ chế thứ tự/bảo vệ phụ thuộc.

### 7.3. PostgreSQL và sắp xếp khi có khóa

PostgreSQL ở mức `READ COMMITTED` có những chi tiết về `ORDER BY` và locking clause: trong lúc truy vấn chờ khóa, giá trị cột được dùng sắp xếp có thể đã thay đổi, dẫn đến kết quả quan sát **không đúng thứ tự mới nhất** theo cách người đọc kỳ vọng. `SKIP LOCKED` tránh chờ hàng bị khóa xung đột nhưng **không biến thứ tự thành hàng đợi FIFO tuyệt đối**.

Để giảm bất ngờ:

- Coi `priority` và `created_at` là tiêu chí chọn tại thời điểm nhận, không phải lời hứa thứ tự thực thi tuyệt đối.
- Bổ sung khóa duy nhất `job_id` làm tie-breaker.
- Không thay đổi `priority` tùy tiện trong lúc nhiều worker chọn việc, trừ khi đã chấp nhận ngữ nghĩa tương ứng.
- Nếu bắt buộc xử lý theo thứ tự nghiêm ngặt, thiết kế cơ chế điều phối khác (ví dụ một consumer theo phân vùng khóa).

### 7.4. OFFSET có thể khóa những hàng bị bỏ qua

Trên PostgreSQL, locking query có `OFFSET` có thể lấy khóa trên những hàng **bị bỏ qua bởi OFFSET**; `LIMIT` chỉ giới hạn số hàng trả ra nhưng không có nghĩa mọi hành vi khóa tương đương “chỉ đụng đúng hàng trên màn hình” trong mọi cấu trúc truy vấn. Vì vậy không nên dùng:

```sql
SELECT job_id
FROM job_queue
WHERE state = 'PENDING'
ORDER BY priority DESC, created_at, job_id
OFFSET 100
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

như một cơ chế “phân trang công việc” thông thường khi nhiều worker chạy đồng thời. Offset còn có thể dịch chuyển khi trạng thái hàng đổi. Hàng đợi nên dựa trên **chọn/nhận nguyên tử**, không dùng số trang để chia việc giữa các worker.

## 8. Mẫu thực tế: nhận một công việc bằng UPDATE ... RETURNING

Chỉ `SELECT ... FOR UPDATE SKIP LOCKED` **chưa đủ** để nhận quyền xử lý lâu dài. Nếu worker đọc 102 rồi `COMMIT` mà không đổi `state`, một worker khác có thể nhận lại 102 ngay sau đó.

Một mẫu PostgreSQL phổ biến là **chọn và đổi trạng thái trong cùng một câu DML**:

```sql
BEGIN;

WITH candidate AS (
    SELECT j.job_id
    FROM job_queue AS j
    WHERE j.state = 'PENDING'
    ORDER BY j.priority DESC, j.created_at ASC, j.job_id ASC
    LIMIT 1
    FOR UPDATE OF j SKIP LOCKED
)
UPDATE job_queue AS j
SET state = 'RUNNING',
    worker_id = 'worker-b',
    claimed_at = clock_timestamp(),
    lease_until = clock_timestamp() + INTERVAL '5 minutes',
    attempts = j.attempts + 1
FROM candidate AS c
WHERE j.job_id = c.job_id
RETURNING
    j.job_id,
    j.job_type,
    j.payload,
    j.state,
    j.worker_id,
    j.attempts,
    j.lease_until;

COMMIT;
```

### 8.1. Vì sao phải đặt chọn và UPDATE cùng nhau?

Các bước logic:

1. `candidate` chỉ xét những job `PENDING`.
2. CTE tìm job ưu tiên cao nhất **có thể khóa ngay**.
3. Khóa của CTE bảo vệ ứng viên khỏi worker khác đang cố nhận nó trong cùng thời gian.
4. `UPDATE` đổi `state` sang `RUNNING`, tăng `attempts` và ghi worker nhận.
5. `RETURNING` trả **chính hàng đã cập nhật**, giúp ứng dụng biết ID/payload nào được nhận.
6. `COMMIT` xác nhận việc nhận công việc; khóa giao dịch được giải phóng, nhưng `state = 'RUNNING'` vẫn được lưu.

Nếu không có công việc lấy được, `candidate` không có hàng, `UPDATE` cập nhật **0 hàng** và `RETURNING` trả **0 hàng**. Điều đó vẫn **không chứng minh queue đã hết việc**: có thể các hàng `PENDING` hiện đang bị giao dịch khác khóa.

### 8.2. Kết quả của ví dụ phụ thuộc phiên khác

Nếu **không có ai giữ khóa**, truy vấn nhận công việc sẽ chọn **101** vì priority 100.

Nếu **Phiên A đang khóa 101** mà không thay đổi trạng thái, worker B sẽ bỏ qua 101 và thường nhận **102** (giả sử không có khóa cạnh tranh khác).

Với bảng mẫu ban đầu, công việc được nhận có:

```text
state       = RUNNING
worker_id   = worker-b
attempts    = 1 (nếu trước đó là 0)
claimed_at  = thời điểm nhận
lease_until = thời điểm nhận + khoảng 5 phút
```

Nếu dùng `ROLLBACK` thay `COMMIT`, thay đổi nhận việc sẽ bị hủy và trạng thái trở về trước lệnh, miễn không có tác động khác ngoài database.

### 8.3. Dùng RETURNING thay cho SELECT riêng sau UPDATE

Nếu chỉ chạy:

```sql
UPDATE job_queue
SET state = 'RUNNING'
WHERE ...;
```

worker vẫn cần biết **đã nhận chính xác job nào**. `RETURNING` cho biết hàng đã được cập nhật trong câu lệnh, tránh việc suy đoán bằng một câu `SELECT` về sau khi dữ liệu đã thay đổi.

Đối với PostgreSQL, `RETURNING` là cách tự nhiên lấy `job_id`, `payload` và số lần thử của chính thao tác `UPDATE`.

### 8.4. Không xử lý API bên ngoài khi vẫn giữ transaction mở quá lâu

Một thiết kế không tốt:

```text
BEGIN
  -> SELECT FOR UPDATE SKIP LOCKED
  -> gọi API gửi email trong 2 phút
  -> UPDATE job thành DONE
COMMIT
```

Nó giữ khóa trong suốt hai phút, có thể tạo tải khóa, chặn bảo trì hoặc gây sự cố khi kết nối rớt. Hơn nữa, **`ROLLBACK` không thể thu hồi một email đã gửi ra ngoài**.

Thiết kế hàng đợi thường chia thành:

```text
Transaction ngắn:
  Chọn và chuyển PENDING -> RUNNING -> COMMIT

Xử lý bên ngoài database:
  Gửi email / tạo file / gọi API

Transaction ngắn:
  Ghi DONE hoặc FAILED, hoặc gia hạn lease khi cần
```

Đây là **mẫu thường gặp**, không phải giải pháp bảo đảm “exactly once”. Ứng dụng vẫn phải xử lý retry, trùng tác động và crash.

## 9. Lease, crash recovery và idempotency

`SKIP LOCKED` ngăn nhiều worker cùng **lấy một hàng đang bị khóa**, nhưng sau `COMMIT` khóa đã được giải phóng. Công việc vẫn được phân biệt bằng trạng thái `RUNNING` và thông tin worker.

### 9.1. Nếu worker chết trước COMMIT

Nếu worker vừa khóa/cập nhật job nhưng **chưa commit**, rồi kết nối bị hủy, transaction thường bị rollback. Job vẫn `PENDING`, và worker khác có thể nhận lại sau khi khóa được giải phóng.

### 9.2. Nếu worker chết sau COMMIT nhưng trước khi hoàn thành

Job đã đổi thành `RUNNING`. Các worker khác chỉ tìm `state = 'PENDING'` nên **không nhận lại job này**, dù worker ban đầu đã ngừng hoạt động.

Vì vậy, hệ thống thực cần chính sách:

- Đặt `lease_until` khi nhận.
- Gia hạn lease nếu công việc lâu hơn dự kiến.
- Phát hiện lease hết hạn và đưa job về trạng thái có thể retry nếu an toàn.
- Giới hạn số lần thử `attempts` và có hàng chờ lỗi/quarantine.
- Ghi lại nguyên nhân thất bại.

**Bảng mẫu có cột `lease_until` nhưng không tự có cơ chế phục hồi.** Một tiến trình giám sát riêng mới thực hiện chính sách retry; không nên tự coi hàng `RUNNING` hết lease là đã được xử lý xong.

### 9.3. Worker cũ không được ghi đè kết quả của worker mới

Giả sử worker A nhận job 102 với `attempts = 1`, mất mạng và hết lease. Hệ thống đưa job về `PENDING` để worker B nhận lại với `attempts = 2`. Sau đó A kết nối lại và muốn đánh dấu `DONE`.

Nếu chỉ viết:

```sql
UPDATE job_queue
SET state = 'DONE'
WHERE job_id = 102;
```

A có thể **ghi đè trạng thái của phiên nhận mới**. Một điều kiện bảo vệ nên kiểm tra worker và phiên nhận:

```sql
-- Ví dụ một worker đã được cấp job 102 ở attempt 2.
UPDATE job_queue
SET state = 'DONE',
    finished_at = clock_timestamp(),
    lease_until = NULL
WHERE job_id = 102
  AND state = 'RUNNING'
  AND worker_id = 'worker-b'
  AND attempts = 2
RETURNING job_id;
```

Nếu giá trị worker/attempt không còn khớp, kết quả `RETURNING` là 0 hàng. **Không tự coi 0 hàng là DONE.** Trong ứng dụng thật có thể dùng **claim token/fencing token** duy nhất cho mỗi lần nhận thay vì chỉ dùng `attempts`; token được truyền cùng tất cả thao tác hoàn thành và gia hạn.

### 9.4. Không hứa “exactly once” chỉ nhờ khóa database

Một job gửi email có thể hoàn thành ở phía nhà cung cấp email nhưng worker chết **trước khi ghi `DONE`**. Khi retry, email có thể được gửi lần thứ hai.

Vì vậy cần tính **idempotent**:

- Sự kiện có ID duy nhất, không xử lý lại tác động đã ghi nhận.
- API bên ngoài có **idempotency key** nếu hỗ trợ.
- Tác vụ có thể chạy lại mà không nhân đôi dữ liệu, hoặc có cơ chế đối soát.
- Với giao dịch tài chính, thiết kế quy trình ghi sổ và giao dịch riêng có quy tắc kiểm soát chặt chẽ hơn.

`NOWAIT`/`SKIP LOCKED` là công cụ điều phối **tranh chấp khóa**, không phải toàn bộ cơ chế xử lý chính xác một lần.

## 10. Mức cô lập và snapshot: tập “nhìn thấy” khác tập “lấy được”

### 10.1. READ COMMITTED của PostgreSQL

Ở mức cô lập `READ COMMITTED` (thông dụng trên PostgreSQL), mỗi câu lệnh có **snapshot đọc** thích hợp tại thời điểm bắt đầu. Truy vấn thông thường thường thấy các giá trị đã commit; giao dịch chưa commit của người khác không tự hiển thị thành giá trị mới.

Nhưng truy vấn `SELECT ... FOR UPDATE` còn phải **lấy khóa hàng**. Nếu hàng đã được giao dịch khác sửa và khóa, câu lệnh chờ hoặc xử lý theo `NOWAIT`/`SKIP LOCKED`. Với dạng chờ mặc định ở `READ COMMITTED`, sau khi giao dịch khác hoàn thành, PostgreSQL có thể kiểm tra lại điều kiện của phiên bản hàng đã thay đổi theo quy tắc thực thi.

Ví dụ:

**A:**

```sql
BEGIN;
UPDATE job_queue
SET state = 'DONE'
WHERE job_id = 101;
-- Chưa COMMIT.
```

**B:** (một truy vấn khóa có thể bị chờ)

```sql
SELECT job_id, state
FROM job_queue
WHERE job_id = 101
  AND state = 'PENDING'
FOR UPDATE;
```

Nếu A `COMMIT`, B có thể tiếp tục và **không còn trả 101**, vì hàng mới không còn thỏa `state = 'PENDING'`. Nếu B dùng `SKIP LOCKED` trong khi A vẫn giữ khóa, B có thể bỏ qua 101 ngay, không đợi biết phiên bản cuối của A là gì.

Điều này giải thích vì sao không nên diễn giải `SKIP LOCKED` đơn giản thành một `WHERE` bổ sung cố định: nó phụ thuộc **trạng thái khóa và thời điểm giao dịch**.

### 10.2. REPEATABLE READ/SERIALIZABLE không làm SKIP LOCKED thành snapshot đầy đủ

Ở mức cô lập cao hơn, DBMS có thêm quy tắc về snapshot, xung đột và khả năng phải retry transaction. Nhưng `SKIP LOCKED` vẫn là yêu cầu **không chờ hàng có khóa xung đột**, và kết quả không thể được coi là “toàn bộ hàng khớp trong bảng” chỉ vì isolation level cao hơn.

Một số tổ hợp mức cô lập và truy vấn khóa có thể gây lỗi serialization hoặc cần retry. Không áp dụng một kết luận của PostgreSQL cho MySQL, Oracle hoặc SQL Server mà không kiểm tra quy tắc MVCC/locking của DBMS đó.

### 10.3. Truy vấn SELECT thường không đồng nghĩa đã nhận việc

Trong hàng đợi:

```sql
SELECT job_id
FROM job_queue
WHERE state = 'PENDING'
ORDER BY priority DESC, created_at, job_id
LIMIT 1;
```

hai worker có thể cùng đọc 101 vì đây chỉ là truy vấn đọc. Nếu sau đó cả hai gọi API bên ngoài rồi mới đánh dấu `DONE`, một job có thể được xử lý **hai lần**.

`SELECT ... FOR UPDATE SKIP LOCKED` trong một transaction ngắn, sau đó `UPDATE` nhận việc trước `COMMIT`, giúp tránh race của giai đoạn **claim**. Nó không thay thế idempotency cho các side effect xảy ra sau claim.

## 11. Phạm vi NOWAIT và SKIP LOCKED: hàng khác khóa bảng

Một điểm dễ bị bỏ qua trên PostgreSQL: `NOWAIT` và `SKIP LOCKED` trong locking clause `FOR UPDATE` chủ yếu điều chỉnh **việc lấy khóa hàng**. Truy vấn vẫn phải lấy những **khóa cấp bảng cần thiết** theo cơ chế SQL thông thường.

Ví dụ:

```sql
SELECT job_id
FROM job_queue
WHERE state = 'PENDING'
FOR UPDATE SKIP LOCKED;
```

Không có nghĩa “câu này không bao giờ bị chặn bởi bất kỳ khóa nào”. Nó có thể vẫn phải chờ một khóa cấp bảng không tương thích, chẳng hạn trong một thao tác DDL hoặc bảo trì đặc biệt.

### 11.1. Khóa cấp bảng có cách kiểm soát khác

Trong PostgreSQL, `SELECT ... FOR UPDATE` còn cần khóa cấp bảng thích hợp (ví dụ `ROW SHARE`) theo quy tắc của hệ. Tùy tình huống, một thao tác DDL lấy khóa mạnh trên bảng có thể khiến câu lệnh **chờ trước cả lúc kiểm tra các hàng**.

Nếu muốn một thao tác **lấy khóa bảng** cũng thất bại ngay khi không có khóa phù hợp, PostgreSQL có:

```sql
BEGIN;

LOCK TABLE job_queue IN ROW SHARE MODE NOWAIT;

-- Tiếp tục truy vấn khi lấy được khóa bảng cần thiết.

ROLLBACK;
```

Đây là thao tác cấp bảng, **không phải** một biến thể của `FOR UPDATE SKIP LOCKED`. Chỉ dùng khi thật sự hiểu phạm vi khóa và ảnh hưởng với các phiên khác.

### 11.2. Lock timeout và statement timeout

Trên PostgreSQL:

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';

SELECT job_id
FROM job_queue
WHERE job_id = 101
FOR UPDATE;

ROLLBACK;
```

- `lock_timeout` giới hạn thời gian chờ lấy một khóa theo quy tắc PostgreSQL.
- `statement_timeout` giới hạn thời gian thực thi cả câu lệnh.
- `NOWAIT` chỉ định **không chờ khi gặp khóa hàng không lấy được ngay** trong locking clause.
- `SKIP LOCKED` yêu cầu **bỏ qua hàng bị khóa**, không chờ thời gian timeout mới bỏ qua.

Hai timeout áp dụng cho phạm vi rộng hơn một tình huống khóa hàng đơn giản. Chúng không thay thế cơ chế lựa chọn tập kết quả kiểu `SKIP LOCKED`.

## 12. MySQL 8.0+: FOR UPDATE NOWAIT và SKIP LOCKED

Với **MySQL 8.0+ và engine hỗ trợ khóa hàng như InnoDB**, có cú pháp:

```sql
START TRANSACTION;

SELECT job_id, state, priority
FROM job_queue
WHERE state = 'PENDING'
ORDER BY priority DESC, created_at ASC, job_id ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;

COMMIT;
```

MySQL cũng hỗ trợ:

```sql
START TRANSACTION;

SELECT job_id
FROM job_queue
WHERE job_id = 101
FOR UPDATE NOWAIT;

ROLLBACK;
```

Ý tưởng gần PostgreSQL: `NOWAIT` báo lỗi khi không thể khóa ngay, `SKIP LOCKED` bỏ qua những hàng có khóa xung đột. Nhưng **không thể suy luận hai engine có mọi chi tiết giống nhau**.

### 12.1. InnoDB locking read phải nằm trong transaction có ý nghĩa

Với hàng đợi:

```text
BEGIN / START TRANSACTION
  -> SELECT FOR UPDATE SKIP LOCKED
  -> UPDATE state = 'RUNNING'
COMMIT
```

Nếu chạy `SELECT ... FOR UPDATE` trong chế độ autocommit, khóa có thể được giải phóng ngay khi statement kết thúc, trước khi ứng dụng kịp chạy `UPDATE` tiếp theo. Muốn **giữ khóa xuyên qua các câu**, dùng transaction tường minh.

### 12.2. Khác biệt về isolation và loại khóa

MySQL InnoDB thường dùng `REPEATABLE READ` làm mức mặc định. **Locking read** có ngữ nghĩa đọc và lấy khóa khác với plain consistent read; một số truy vấn theo phạm vi còn có thể liên quan **next-key/gap locks** tùy mức cô lập, chỉ mục và kế hoạch.

Vì vậy, không nên coi `SKIP LOCKED` trên MySQL là một cam kết “chỉ khóa một hàng, không có bất kỳ phạm vi khóa khác” cho mọi điều kiện. Hãy kiểm tra cấu trúc chỉ mục và thử hai phiên thực tế.

### 12.3. Kết quả SKIP LOCKED trên MySQL không nhất quán để làm báo cáo tổng quát

MySQL cũng nhấn mạnh rằng truy vấn bỏ qua hàng khóa có thể cho **cái nhìn không đầy đủ** về tập dữ liệu. Nó phù hợp với queue-like workloads nhưng không phù hợp cho những tác vụ cần một bức tranh nhất quán và đầy đủ.

Ứng dụng nên xử lý riêng:

- Không tìm được công việc hiện có thể khóa.
- Lỗi `NOWAIT` do lock contention.
- Timeout/deadlock/serialization khi có.
- Lỗi ràng buộc hoặc transaction khác.

Đừng diễn giải mọi trường hợp thành “không còn công việc”.

## 13. Oracle Database: NOWAIT, WAIT và SKIP LOCKED

Oracle hỗ trợ locking read bằng `SELECT ... FOR UPDATE` và các biến thể:

```sql
-- Oracle: thất bại ngay nếu hàng cần khóa đang bị giữ.
SELECT job_id, state
FROM job_queue
WHERE job_id = 101
FOR UPDATE NOWAIT;
```

```sql
-- Oracle: bỏ qua các hàng đang khóa.
SELECT job_id, priority
FROM job_queue
WHERE state = 'PENDING'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

Oracle còn có hình thức:

```sql
SELECT job_id
FROM job_queue
WHERE job_id = 101
FOR UPDATE WAIT 5;
```

`WAIT 5` cho phép chờ đến một khoảng thời gian xác định theo cú pháp Oracle, khác với `NOWAIT` và `SKIP LOCKED`. Chọn cách nào phụ thuộc yêu cầu độ trễ và xử lý tranh chấp.

### 13.1. Không sao chép LIMIT của PostgreSQL

Oracle không dùng `LIMIT 1` giống PostgreSQL/MySQL. Khi xây hàng đợi “lấy một hàng” theo thứ tự, có thể cần **cursor và fetch** cùng locking clause, hoặc cấu trúc truy vấn riêng được hỗ trợ ở phiên bản Oracle đang dùng.

Không mặc định rằng mọi tổ hợp `FETCH FIRST 1 ROW ONLY`, truy vấn con và `FOR UPDATE SKIP LOCKED` có thể ghép tùy ý: các phiên bản Oracle có những giới hạn về **row limiting clause** và **FOR UPDATE**. Hãy đối chiếu cú pháp của phiên bản cụ thể thay vì dịch bằng cách chỉ thay `LIMIT` thành `FETCH FIRST`.

### 13.2. Oracle có thể báo mã lỗi khác

Trên Oracle, lỗi `NOWAIT` khi tài nguyên đang bị khóa thường được báo bằng các mã lỗi Oracle thích hợp, ví dụ **ORA-00054** trong những tình huống khóa thường gặp. Không dùng mã lỗi PostgreSQL `55P03` để nhận diện lock contention trên Oracle.

Một chương trình đa DBMS cần phân loại lỗi bằng mã/exception của **driver và hệ quản trị tương ứng**.

## 14. SQL Server: READPAST, UPDLOCK và NOWAIT

SQL Server không có cùng cú pháp PostgreSQL:

```sql
-- Không phải cú pháp SQL Server:
SELECT ... FOR UPDATE SKIP LOCKED;
```

Thay vào đó, SQL Server có các **table hints** để xây hành vi tương đương trong một số mẫu queue.

### 14.1. READPAST để bỏ qua hàng đang có khóa

Ví dụ đọc một công việc `PENDING` theo thứ tự:

```sql
-- SQL Server (schema tương đương dbo.job_queue).
BEGIN TRANSACTION;

SELECT TOP (1)
    j.job_id,
    j.priority,
    j.state
FROM dbo.job_queue AS j WITH (UPDLOCK, READPAST, ROWLOCK)
WHERE j.state = 'PENDING'
ORDER BY j.priority DESC, j.created_at ASC, j.job_id ASC;

COMMIT TRANSACTION;
```

Ý nghĩa các hint:

- `UPDLOCK` yêu cầu loại khóa thích hợp cho ý định cập nhật, giúp giảm tình huống hai transaction đọc cùng ứng viên trước khi sửa.
- `READPAST` có thể **bỏ qua hàng đang bị khóa** bởi transaction khác, phù hợp một số kiểu job queue.
- `ROWLOCK` đề nghị ưu tiên khóa cấp hàng, **không phải bảo đảm tuyệt đối** SQL Server sẽ không sử dụng kiểu khóa khác.

**Giới hạn quan trọng:** `READPAST` chủ yếu bỏ qua **row-level locks**, không bảo đảm bỏ qua mọi **page-level/table-level lock**. Câu lệnh vẫn có thể bị chặn bởi những khóa khác. Cơ chế và các hint hợp lệ còn phụ thuộc isolation level, chế độ `READ_COMMITTED_SNAPSHOT` và cấu hình database.

### 14.2. READ_COMMITTED_SNAPSHOT có thể thay đổi cách dùng hint

Trên SQL Server có `READ_COMMITTED_SNAPSHOT = ON`, một số tổ hợp `READPAST` và mức cô lập không hợp lệ hoặc không có hành vi như mong muốn. Trong những trường hợp phù hợp, tài liệu SQL Server yêu cầu kết hợp với hint như `READCOMMITTEDLOCK`.

**Không** sao chép `WITH (UPDLOCK, READPAST, ROWLOCK)` vào mọi ứng dụng SQL Server mà không xác nhận transaction isolation, tùy chọn database và hành vi thực tế. Đặc biệt, hint là yêu cầu liên quan **bảng được chỉ định**, không phải câu thần chú bảo đảm an toàn đồng thời.

### 14.3. NOWAIT trong SQL Server

SQL Server có table hint `NOWAIT` để không chờ khi gặp khóa không tương thích trong phạm vi áp dụng:

```sql
-- SQL Server: minh họa fail-fast khi không lấy được khóa.
BEGIN TRANSACTION;

SELECT j.job_id
FROM dbo.job_queue AS j WITH (UPDLOCK, NOWAIT)
WHERE j.job_id = 101;

ROLLBACK TRANSACTION;
```

SQL Server cũng có:

```sql
SET LOCK_TIMEOUT 0;
```

để cấu hình timeout chờ khóa ở mức session. Hai cơ chế này **không giống cú pháp** `FOR UPDATE NOWAIT` của PostgreSQL. Cần xử lý exception/trạng thái giao dịch theo cơ chế SQL Server.

### 14.4. Xây thao tác nhận việc nguyên tử trên SQL Server

Một ý tưởng thường gặp là chọn một hàng bằng CTE có `TOP (1)` và hints, rồi **UPDATE trực tiếp hàng đã chọn** và dùng `OUTPUT inserted.job_id` để lấy ID nhận việc:

```sql
-- SQL Server: minh họa pattern cập nhật một hàng được chọn.
BEGIN TRANSACTION;

;WITH next_job AS (
    SELECT TOP (1)
        job_id,
        state,
        worker_id,
        attempts
    FROM dbo.job_queue WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE state = 'PENDING'
    ORDER BY priority DESC, created_at ASC, job_id ASC
)
UPDATE next_job
SET state = 'RUNNING',
    worker_id = 'worker-b',
    attempts = attempts + 1
OUTPUT inserted.job_id, inserted.state, inserted.attempts;

COMMIT TRANSACTION;
```

Ví dụ này cần có bảng/cột và isolation phù hợp trong SQL Server. Nó minh họa **trả ID từ chính UPDATE**, tương tự mục tiêu `UPDATE ... RETURNING` của PostgreSQL, không có nghĩa mọi kế hoạch SQL Server đều sẽ khóa đúng một hàng trong mọi tình huống. Nếu dùng sản xuất, cần thử với nhiều phiên, deadlock, RCSI, chỉ mục và retry.

## 15. SQLite: không có FOR UPDATE SKIP LOCKED theo kiểu khóa hàng

SQLite có mô hình đồng thời khác PostgreSQL/MySQL/SQL Server. SQLite không cung cấp cú pháp tương đương trực tiếp với:

```sql
SELECT ...
FOR UPDATE SKIP LOCKED;
```

SQLite thường điều phối **ghi ở phạm vi database/file với cơ chế khóa và WAL**, không phải cho phép nhiều worker đồng thời khóa rồi bỏ qua **những hàng riêng lẻ** giống một số DBMS server.

### 15.1. BEGIN IMMEDIATE

SQLite có thể dùng:

```sql
BEGIN IMMEDIATE;

-- SELECT/UPDATE một công việc theo quy tắc của ứng dụng.

COMMIT;
```

`BEGIN IMMEDIATE` yêu cầu bắt đầu transaction với ý định ghi theo cơ chế SQLite. Nếu một writer khác đang giữ quyền ghi không tương thích, giao dịch có thể bị chặn hoặc báo `SQLITE_BUSY` tùy cấu hình chờ.

Có thể cấu hình thời gian chờ:

```sql
PRAGMA busy_timeout = 0;
```

để yêu cầu hành vi fail-fast trong những tình huống `SQLITE_BUSY`, nhưng đây **không phải `NOWAIT` khóa hàng** và càng không phải `SKIP LOCKED`. Không được nói “SQLite sẽ bỏ qua job 101 đang bị khóa và chọn job 102” theo cùng ngữ nghĩa vì SQLite không cung cấp khóa hàng kiểu đó.

### 15.2. Hướng thiết kế khi dùng SQLite làm hàng đợi

Với lượng worker nhỏ hoặc ứng dụng nhúng, có thể dùng **một transaction ngắn để tìm và cập nhật job**, dựa trên cơ chế ghi của SQLite; sau commit mới xử lý công việc bên ngoài.

Nếu yêu cầu nhiều worker tranh chấp mạnh và muốn skip từng hàng, có thể cần cân nhắc DBMS hỗ trợ khóa hàng hoặc một hệ thống queue chuyên dụng. Việc lựa chọn phụ thuộc tải, yêu cầu độ tin cậy, cách triển khai và kiến trúc tổng thể.

## 16. Bảng đối chiếu phương ngữ

| Khía cạnh | PostgreSQL | MySQL 8.0+/InnoDB | Oracle | SQL Server | SQLite |
|---|---|---|---|---|---|
| Khóa hàng để cập nhật | `FOR UPDATE` | `FOR UPDATE` | `FOR UPDATE` | `UPDLOCK`/cơ chế khóa tương ứng | Không có `FOR UPDATE` khóa hàng cùng kiểu |
| Không chờ khóa xung đột | `FOR UPDATE NOWAIT` | `FOR UPDATE NOWAIT` | `FOR UPDATE NOWAIT` | `NOWAIT` hint hoặc `LOCK_TIMEOUT 0` | `busy_timeout`/xử lý `SQLITE_BUSY`, không tương đương khóa hàng |
| Bỏ qua hàng đang khóa | `FOR UPDATE SKIP LOCKED` | `FOR UPDATE SKIP LOCKED` | `FOR UPDATE SKIP LOCKED` | `READPAST` với hint/isolation phù hợp | Không có tương đương trực tiếp |
| Nhận job và trả ID | `UPDATE ... RETURNING` | `UPDATE` + chiến lược trả ID/kiểm tra theo phiên bản | `RETURNING INTO`/PLSQL hay cursor | `UPDATE ... OUTPUT inserted...` | `UPDATE ... RETURNING` từ 3.35.0 |
| Tính nhất quán của tập trả về | Có thể bỏ qua hàng khớp WHERE | Có thể bỏ qua hàng khớp WHERE | Có thể bỏ qua hàng khớp WHERE | `READPAST` có thể bỏ qua hàng bị khóa theo loại khóa | Không áp dụng khái niệm skip row locks |
| Giới hạn đáng chú ý | Table-level lock vẫn có thể chờ | Isolation/next-key/gap locks | Cú pháp row limiting + FOR UPDATE phụ thuộc phiên bản | READPAST không bỏ qua mọi khóa cấp page/table, RCSI ảnh hưởng hint | Writer concurrency theo cơ chế riêng |

**Kết luận từ bảng:** khái niệm **“không chờ”** và **“bỏ qua hàng bận”** xuất hiện ở nhiều DBMS, nhưng không có một câu SQL duy nhất bảo đảm hoàn toàn cùng hành vi trên mọi hệ. Phải kiểm tra **phiên bản, storage engine, isolation level và kế hoạch truy cập**.

## 17. Tối ưu hiệu năng và độ ổn định

### 17.1. Chỉ mục hỗ trợ tìm ứng viên

Trên PostgreSQL, với quy tắc chọn:

```sql
WHERE state = 'PENDING'
ORDER BY priority DESC, created_at ASC, job_id ASC
```

có thể cân nhắc chỉ mục:

```sql
CREATE INDEX idx_job_queue_pending_priority
ON job_queue (priority DESC, created_at ASC, job_id ASC)
WHERE state = 'PENDING';
```

Đây là **partial index** đặc thù PostgreSQL, chỉ chứa các hàng `PENDING`. Nó có thể giúp truy vấn chọn ứng viên mà không phải quét/sắp toàn bộ bảng. Vì mỗi job thường chuyển `PENDING → RUNNING`, chỉ mục có chi phí bảo trì khi cập nhật trạng thái; cần dùng `EXPLAIN` và đo trên dữ liệu thực.

Chỉ mục phù hợp cũng giúp giảm số hàng phải xem xét trong quá trình tìm ứng viên; nhưng **không bảo đảm không có lock contention** hoặc không bao giờ bị chặn ở cấp bảng.

### 17.2. Transaction ngắn

Tối ưu quan trọng nhất cho queue thường không phải viết SQL ngắn hơn vài ký tự, mà là:

- Chỉ giữ giao dịch đủ lâu để **chọn và nhận việc**.
- Không gọi dịch vụ mạng chậm trước `COMMIT` trong transaction đang giữ khóa.
- Ghi nhận trạng thái `RUNNING` và token nhận việc để các worker khác không nhận lại.
- Có timeout, giới hạn retry và xử lý crash.

### 17.3. Theo dõi độ trễ và starvation

Một hàng `PENDING` priority rất cao nhưng luôn bị khóa hoặc luôn thất bại có thể bị bỏ qua hết lần này đến lần khác. Cần giám sát:

- Số lượng `PENDING` theo độ tuổi.
- Job tồn tại quá lâu ở `RUNNING` hoặc đã quá `lease_until`.
- Số lần retry/attempts và lỗi cuối cùng.
- Thời gian worker nhận việc và hoàn thành.
- Số lần truy vấn nhận job không trả hàng dù vẫn có job `PENDING`.
- Số lượng giao dịch dài và các khóa chờ.

Nếu chỉ nhìn vào tốc độ hoàn thành của những job đã nhận, bạn có thể bỏ sót hàng bị **starvation**.

### 17.4. Thăm dò lại và backoff

Khi `SKIP LOCKED` trả 0 hàng, worker không nên kết luận vĩnh viễn rằng queue rỗng. Có thể:

1. Chờ ngắn hoặc dùng tín hiệu đánh thức.
2. Thử lại sau theo lịch/backoff.
3. Phân biệt không có job mới với mọi job đang bị khóa hoặc đang RUNNING.
4. Tránh hàng trăm worker spin liên tục tạo quá nhiều truy vấn khi tạm thời không có việc.

Khi `NOWAIT` báo lỗi, retry cần có **giới hạn và backoff** phù hợp; chạy lại ngay trong vòng lặp nóng có thể làm tăng tranh chấp.

## 18. Những lỗi thường gặp

### Lỗi 1 — Nghĩ SKIP LOCKED trả 0 hàng tức là bảng không có dữ liệu

Hàng 101 có thể còn `PENDING` và vẫn được `SELECT` thông thường nhìn thấy, nhưng không xuất hiện trong `FOR UPDATE SKIP LOCKED` vì bị A giữ khóa. Một result set rỗng chỉ có nghĩa **không lấy được ứng viên trong lượt đó**.

### Lỗi 2 — Nghĩ NOWAIT trả một tập rỗng

Trên PostgreSQL, không lấy được khóa hàng với `NOWAIT` thường tạo **lỗi**, ví dụ SQLSTATE `55P03`. Phải xử lý exception và trạng thái transaction; không dùng số hàng bằng 0 thay thế.

### Lỗi 3 — Quên transaction khi SELECT FOR UPDATE

Nếu truy vấn khóa kết thúc trong autocommit trước khi chạy `UPDATE` nhận việc, khóa không còn bảo vệ thao tác tiếp theo. Chọn và cập nhật cần được phối hợp trong **cùng transaction**, tốt hơn nữa là một câu `UPDATE ... RETURNING` dùng CTE khóa ứng viên.

### Lỗi 4 — Chỉ SELECT khóa hàng rồi COMMIT, không đổi trạng thái

Sau commit, `PENDING` vẫn `PENDING` nên worker khác có thể nhận lại. Phải lưu trạng thái claim/lease khi nghiệp vụ đòi hỏi quyền xử lý kéo dài.

### Lỗi 5 — Dùng SKIP LOCKED cho kiểm toán đầy đủ

`SKIP LOCKED` cố ý trả **cái nhìn không đầy đủ khi có khóa xung đột**; không dùng để chứng minh mọi đơn đã đối soát, mọi bút toán đã xử lý hoặc mọi hàng `PENDING` đã hết.

### Lỗi 6 — Cho rằng ORDER BY bảo đảm không ai vượt hàng ưu tiên cao

Hàng ưu tiên cao có thể bị khóa và bị bỏ qua; worker nhận hàng thấp hơn. Nếu yêu cầu thứ tự nghiêm ngặt, phải có điều phối khác chứ không chỉ thêm `ORDER BY`.

### Lỗi 7 — Nghĩ LIMIT 1 luôn trả đúng một hàng

`LIMIT 1` là **tối đa một hàng**, không phải tối thiểu một. Không có ứng viên hoặc mọi ứng viên đang bị khóa thì result set có thể rỗng.

### Lỗi 8 — Dùng OFFSET như cách phân trang queue

`OFFSET` có thể khóa những hàng đã bỏ qua trong PostgreSQL và bị dịch chuyển khi nhiều worker cập nhật trạng thái. Không dùng phân trang offset để cấp phát công việc đồng thời.

### Lỗi 9 — Nghĩ NOWAIT/SKIP LOCKED loại bỏ mọi chờ khóa

Trên PostgreSQL, các lựa chọn này tập trung vào **khóa hàng**; câu truy vấn vẫn có thể phải chờ khóa cấp bảng hoặc bị ảnh hưởng bởi cơ chế khác. Cần xét timeout và loại khóa thực tế.

### Lỗi 10 — Dùng FOR UPDATE SKIP LOCKED trên SQLite

SQLite không cung cấp cùng cú pháp khóa hàng. `BEGIN IMMEDIATE` và `busy_timeout` thuộc mô hình writer locking khác, không phải kỹ thuật skip từng hàng.

### Lỗi 11 — Coi SQL Server READPAST giống hệt PostgreSQL SKIP LOCKED

`READPAST` có phạm vi và giới hạn theo loại khóa, hint, isolation và RCSI; nó không bảo đảm bỏ qua mọi page/table lock. Phải thử nghiệm trên SQL Server thực tế.

### Lỗi 12 — Giữ transaction trong suốt lúc gọi API bên ngoài

Giữ khóa khi gửi email hoặc gọi dịch vụ chậm làm kéo dài transaction, tăng tranh chấp và không giải quyết side effect khi rollback. Nên claim ngắn, commit, rồi xử lý và cập nhật kết quả.

### Lỗi 13 — Nghĩ khóa hàng đảm bảo exactly once

Nếu worker thực thi tác động bên ngoài rồi chết trước khi ghi `DONE`, retry có thể lặp tác động. Cần idempotency, retry và cơ chế ghi nhận trạng thái phù hợp.

### Lỗi 14 — Worker cũ cập nhật kết quả sau khi lease hết hạn

Nếu không kiểm tra claim token/worker/attempt khi cập nhật `DONE`, một worker cũ có thể ghi đè tiến độ worker mới. Điều kiện `WHERE` hoàn thành phải xác minh phiên claim.

### Lỗi 15 — Không có chỉ mục cho điều kiện chọn queue

Quét/sắp bảng lớn có thể làm tăng thời gian tìm job và tranh chấp. Cân nhắc chỉ mục dựa trên `state`, `priority`, `created_at` và `job_id`, nhưng xác nhận bằng kế hoạch thực thi.

### Lỗi 16 — Nghĩ transaction isolation cao hơn làm tập SKIP LOCKED đầy đủ

`REPEATABLE READ` hoặc `SERIALIZABLE` có quy tắc nhất quán riêng, nhưng không đổi bản chất **bỏ qua hàng có khóa xung đột**. Có thể còn phát sinh lỗi serialization cần retry.

### Lỗi 17 — Không phân biệt PENDING và RUNNING

Job `RUNNING` thường không nên được worker mới nhận chỉ vì khóa giao dịch đã hết sau commit. Phải lọc `state = 'PENDING'`, có chính sách lease và đưa lại hàng chờ khi phù hợp.

### Lỗi 18 — Diễn giải một SELECT thông thường là đã có quyền xử lý

Hai worker có thể cùng đọc 101 bằng `SELECT` không khóa. Muốn claim an toàn, phải có transaction và thao tác đổi trạng thái nguyên tử với điều kiện thích hợp.

## 19. Bài tập thực hành có đáp án

Tất cả bài giả định dữ liệu `job_queue` ở mục 2 và, nếu cần, **hai kết nối A/B độc lập**. Mỗi bài nên bắt đầu từ trạng thái ban đầu; khi cần thử DML, dùng transaction rồi `ROLLBACK` để bảo toàn dữ liệu mẫu.

### Bài 1 — Đếm hàng PENDING

```sql
SELECT COUNT(*) AS pending_count
FROM job_queue
WHERE state = 'PENDING';
```

**Đáp án:** **5 hàng**: 101, 102, 103, 104, 107. Đây là đếm dữ liệu, không có nghĩa cả năm hàng đều đang lấy được khóa ngay.

### Bài 2 — Khóa hàng cụ thể

Phiên A chạy:

```sql
BEGIN;
SELECT job_id FROM job_queue WHERE job_id = 101 FOR UPDATE;
```

Phiên B chạy cùng câu `FOR UPDATE`. Điều gì xảy ra?

**Đáp án:** B thường **chờ** A giải phóng khóa. Kết quả không phải mặc định 0 hàng. Sau A `COMMIT` hoặc `ROLLBACK`, B có thể tiếp tục theo trạng thái dữ liệu/isolation.

### Bài 3 — NOWAIT gặp khóa

Giữ A khóa 101; B chạy:

```sql
BEGIN;
SELECT job_id
FROM job_queue
WHERE job_id = 101
FOR UPDATE NOWAIT;
```

**Đáp án:** PostgreSQL báo lỗi không lấy được khóa ngay, thường SQLSTATE **`55P03`**. B cần `ROLLBACK` để kết thúc transaction lỗi; không coi đây là “không tìm thấy job”.

### Bài 4 — SKIP LOCKED với khóa chính

Giữ A khóa 101; B chạy:

```sql
SELECT job_id
FROM job_queue
WHERE job_id = 101
FOR UPDATE SKIP LOCKED;
```

**Đáp án:** có thể trả **0 hàng** vì 101 bị khóa. `SELECT` thường không `FOR UPDATE` vẫn có thể nhìn thấy 101 trong snapshot.

### Bài 5 — Chọn một job khác khi 101 bận

Giữ A khóa 101; B chạy:

```sql
BEGIN;
SELECT job_id
FROM job_queue
WHERE state = 'PENDING'
ORDER BY priority DESC, created_at ASC, job_id ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
ROLLBACK;
```

**Đáp án:** nếu chỉ A khóa 101, B nhận **102**. Sau rollback, B không còn giữ khóa 102 và `state` vẫn PENDING vì chưa cập nhật.

### Bài 6 — Tại sao 101 không được trả về?

101 có priority 100, còn 102 có priority 90. Có phải `ORDER BY` sai khi B nhận 102 không?

**Đáp án:** không. `SKIP LOCKED` cho phép **bỏ qua** 101 đang bận rồi lấy hàng phù hợp tiếp theo. Thứ tự ưu tiên không đồng nghĩa FIFO tuyệt đối trong điều kiện khóa đồng thời.

### Bài 7 — Không có hàng không đồng nghĩa hết việc

Giả sử tất cả 5 hàng PENDING đang bị các giao dịch khác giữ khóa. Worker chạy `FOR UPDATE SKIP LOCKED LIMIT 1` trả 0. Ứng dụng có nên đặt trạng thái “queue đã hết vĩnh viễn” không?

**Đáp án:** **không**. Nó chỉ biết không có hàng **khóa được ngay trong lượt đó**. Cần retry/backoff hoặc tín hiệu đánh thức khi có thể.

### Bài 8 — Nhận việc nguyên tử

Viết câu PostgreSQL chọn hàng `PENDING` ưu tiên cao nhất có thể khóa, rồi cập nhật trạng thái `RUNNING`, tăng `attempts` và trả `job_id`:

```sql
BEGIN;

WITH candidate AS (
    SELECT job_id
    FROM job_queue
    WHERE state = 'PENDING'
    ORDER BY priority DESC, created_at, job_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE job_queue AS j
SET state = 'RUNNING',
    worker_id = 'worker-x',
    attempts = attempts + 1
FROM candidate AS c
WHERE j.job_id = c.job_id
RETURNING j.job_id, j.attempts;

ROLLBACK;
```

**Đáp án:** nếu không có khóa cạnh tranh, nhận **101** với `attempts = 1`. Khi A giữ 101, worker có thể nhận **102**. `ROLLBACK` hủy cập nhật thử nghiệm.

### Bài 9 — Chọn xong rồi COMMIT mà không UPDATE

Worker chạy `SELECT ... FOR UPDATE SKIP LOCKED` lấy 101, ngay sau đó `COMMIT` nhưng vẫn để `state = 'PENDING'`. Worker khác có thể nhận 101 không?

**Đáp án:** **có**. Khóa được giải phóng khi transaction kết thúc, còn cột `state` vẫn `PENDING`. Phải ghi nhận claim trong cùng transaction.

### Bài 10 — Tác động của crash trước và sau commit

So sánh:

1. Worker chết **trước commit** thao tác đổi PENDING → RUNNING.
2. Worker chết **sau commit** nhưng trước khi gửi email.

**Đáp án:** trường hợp 1 transaction thường rollback và job có thể vẫn PENDING. Trường hợp 2 job đã RUNNING nên cần cơ chế lease/recovery để có thể xử lý lại an toàn; không tự chuyển sang DONE.

### Bài 11 — Hoàn thành an toàn bằng phiên claim

Worker B đã nhận job 102 ở `attempts = 2`. Viết `UPDATE` hoàn thành có điều kiện:

```sql
UPDATE job_queue
SET state = 'DONE',
    finished_at = clock_timestamp()
WHERE job_id = 102
  AND state = 'RUNNING'
  AND worker_id = 'worker-b'
  AND attempts = 2
RETURNING job_id;
```

**Đáp án:** chỉ cập nhật nếu phiên claim vẫn hợp lệ. Nếu kết quả 0 hàng, không được coi là đã hoàn thành; cần kiểm tra xem job đã đổi chủ/phiên nhận hay chưa.

### Bài 12 — NOWAIT hay SKIP LOCKED?

Chọn kỹ thuật:

1. Người dùng yêu cầu sửa **đúng đơn #101**, nếu đơn bận thì báo ngay.
2. Worker lấy **bất kỳ job PENDING khả dụng** nào, ưu tiên cao nhất có thể.

**Đáp án:** tình huống 1 phù hợp **NOWAIT**; tình huống 2 phù hợp **SKIP LOCKED**. Không tráo hai lựa chọn vì ngữ nghĩa tập kết quả khác.

### Bài 13 — MySQL và transaction

Trên MySQL InnoDB, vì sao `SELECT ... FOR UPDATE SKIP LOCKED` thường phải đi cùng `START TRANSACTION` rồi `UPDATE` trước `COMMIT`?

**Đáp án:** để khóa bảo vệ quá trình claim xuyên qua việc đọc và cập nhật. Nếu autocommit làm giải phóng khóa sau câu `SELECT`, bước cập nhật tiếp theo có thể không còn được bảo vệ.

### Bài 14 — SQL Server READPAST

Trên SQL Server, gợi ý nhóm hint:

```sql
WITH (UPDLOCK, READPAST, ROWLOCK)
```

Các hint này dùng để làm gì và có giới hạn gì?

**Đáp án:** `UPDLOCK` hỗ trợ ý định cập nhật, `READPAST` có thể bỏ qua hàng có row-level lock, `ROWLOCK` yêu cầu ưu tiên khóa hàng. Nhưng không có bảo đảm tuyệt đối bỏ qua page/table lock; RCSI/isolation có thể yêu cầu cách dùng hint khác.

### Bài 15 — Oracle WAIT 5

Phân biệt `FOR UPDATE NOWAIT`, `FOR UPDATE WAIT 5` và `FOR UPDATE SKIP LOCKED`.

**Đáp án:** NOWAIT báo lỗi ngay khi không có khóa; WAIT 5 chờ có giới hạn theo Oracle; SKIP LOCKED bỏ qua hàng khóa và tìm ứng viên khác. Không chuyển `WAIT 5` nguyên văn sang PostgreSQL.

### Bài 16 — SQLite có SKIP LOCKED không?

Ứng dụng SQLite muốn hai worker bỏ qua từng hàng đang có khóa. Có thể viết `FOR UPDATE SKIP LOCKED` không?

**Đáp án:** **không**. SQLite có mô hình writer locking và cơ chế như `BEGIN IMMEDIATE`/`SQLITE_BUSY`, không có tính năng skip row locks tương đương.

### Bài 17 — Khóa cấp bảng

PostgreSQL `FOR UPDATE NOWAIT` có bảo đảm **không bao giờ chờ bất kỳ khóa nào** không?

**Đáp án:** không. Lựa chọn NOWAIT trong locking clause điều chỉnh lấy **khóa hàng**; câu lệnh vẫn có thể phải lấy khóa cấp bảng theo quy tắc thông thường. Cần xem `LOCK TABLE ... NOWAIT` hoặc timeout khi yêu cầu fail-fast ở phạm vi rộng hơn.

### Bài 18 — Hàng ưu tiên cao bị đói việc

Job 101 liên tục bị một transaction giữ khóa. Các worker khác cứ dùng `SKIP LOCKED` nhận công việc mới hơn/thấp hơn. Vấn đề là gì?

**Đáp án:** nguy cơ **starvation** của 101. Cần theo dõi tuổi công việc, transaction dài, lease, retry và quy tắc ưu tiên; `ORDER BY` không tự bảo đảm công bằng tuyệt đối.

### Bài 19 — Vì sao không gọi API trước commit?

Worker nhận job gửi email, giữ transaction và khóa trong suốt 2 phút gọi dịch vụ email. Điều gì sai?

**Đáp án:** giao dịch dài gây tranh chấp, khóa bị giữ lâu, và rollback database **không thu hồi email đã gửi**. Nên claim/commit nhanh, xử lý bên ngoài và có cơ chế idempotency/recovery khi ghi kết quả.

### Bài 20 — Báo cáo “đã hết PENDING”

Một hệ thống muốn chốt rằng tất cả job cần xử lý trong ngày đã hoàn tất. Có nên dùng số hàng `FOR UPDATE SKIP LOCKED` trả ra bằng 0 làm chứng cứ?

**Đáp án:** **không**. Cần kiểm tra trạng thái toàn bộ tập công việc theo phạm vi/snapshot nhất quán, bao gồm PENDING, RUNNING, FAILED, lease hết hạn và các job chưa đồng bộ. `SKIP LOCKED` không được thiết kế để xác minh tính đầy đủ.

## 20. Bảng ghi nhớ nhanh

| Mục tiêu | Cách tiếp cận | Ý nghĩa cần nhớ |
|---|---|---|
| Đọc hàng thông thường | `SELECT ... WHERE ...` | Không tự giữ quyền xử lý |
| Đọc và lấy khóa hàng | `SELECT ... FOR UPDATE` | Có thể chờ khóa |
| Không chờ hàng cụ thể | `FOR UPDATE NOWAIT` | Báo lỗi nếu hàng bận; **không phải 0 hàng** |
| Lấy hàng khả dụng khác | `FOR UPDATE SKIP LOCKED` | Bỏ qua hàng bận; result set có thể thiếu hàng |
| Chọn tối đa một job | `ORDER BY ... LIMIT 1 FOR UPDATE SKIP LOCKED` | 0 hoặc 1 hàng, không cam kết FIFO tuyệt đối |
| Claim job nguyên tử | CTE khóa ứng viên + `UPDATE ... RETURNING` | Đổi PENDING → RUNNING trước commit |
| Giữ quyền xử lý sau commit | `state`, `worker_id`, `lease_until`, claim token | Khóa transaction không đủ |
| Worker chết giữa chừng | Retry/lease/idempotency | Không có exactly once chỉ nhờ khóa |
| Cần đếm đầy đủ mọi PENDING | Truy vấn/snapshot nhất quán, không dùng SKIP LOCKED | Không nhầm “không lấy được” với “không tồn tại” |
| PostgreSQL/MySQL/Oracle | `FOR UPDATE NOWAIT/SKIP LOCKED` | Chi tiết khác theo DBMS |
| SQL Server | `READPAST`, `UPDLOCK`, `NOWAIT` hints | Không tương đương tuyệt đối; page locks/RCSI |
| SQLite | `BEGIN IMMEDIATE` và quản lý writer contention | Không có SKIP LOCKED khóa hàng |
| Ngăn transaction chờ quá lâu | `lock_timeout`/`statement_timeout` hoặc cơ chế DBMS | Không thay thế ý nghĩa SKIP LOCKED |
| Giảm scan queue | Chỉ mục theo trạng thái/ưu tiên/thời điểm | Cần kiểm tra kế hoạch và tải thật |

## Kết luận

`NOWAIT` và `SKIP LOCKED` đều giúp kiểm soát tranh chấp khóa, nhưng **không giải quyết cùng một câu hỏi**:

- **`NOWAIT`** ưu tiên **phản hồi nhanh về xung đột**. Khi hàng cần khóa đang bận, truy vấn có thể **thất bại bằng lỗi**; ứng dụng cần xử lý lỗi và transaction đúng cách.
- **`SKIP LOCKED`** ưu tiên **tiến độ xử lý của các hàng khác**. Khi một hàng đang bận, truy vấn bỏ qua nó và có thể trả ứng viên tiếp theo, hoặc **trả 0 hàng dù dữ liệu vẫn tồn tại**.
- **`ORDER BY` và `LIMIT`** xác định thứ tự mong muốn và số hàng tối đa, nhưng không bảo đảm công bằng/FIFO tuyệt đối khi có skip.
- **`SELECT ... FOR UPDATE`** chỉ giữ khóa trong transaction; ứng dụng hàng đợi cần **UPDATE trạng thái nhận việc**, commit ngắn, lease, retry, idempotency và xác minh phiên claim.
- **Cú pháp khác nhau theo phương ngữ**: PostgreSQL/MySQL/Oracle hỗ trợ những dạng `FOR UPDATE NOWAIT/SKIP LOCKED`; SQL Server thường dùng hints `READPAST`/`UPDLOCK`/`NOWAIT`; SQLite không có khóa hàng tương đương.

Nguyên tắc quan trọng nhất là **đọc đúng ý nghĩa của result set**. Với `SKIP LOCKED`, tập kết quả diễn đạt **“những hàng tôi lấy được để xử lý ngay”**, không nhất thiết là **“mọi hàng tồn tại và thỏa WHERE”**. Khi phân biệt được hai tập này, bạn sẽ chọn đúng chiến lược khóa cho nghiệp vụ, thiết kế worker an toàn hơn và tránh những kết luận sai do nhầm “bị khóa” với “không có dữ liệu”.
