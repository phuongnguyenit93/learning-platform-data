# Nhận diện deadlock, lỗi tuần tự hóa và ranh giới thử lại trong giao dịch SQL

Một ứng dụng có thể chạy hoàn hảo khi chỉ có một người dùng nhưng thỉnh thoảng thất bại khi nhiều tiến trình cùng cập nhật dữ liệu. Có giao dịch **chờ khóa**, có giao dịch bị **deadlock**, có giao dịch bị từ chối bằng **serialization failure**, và có giao dịch đã thất bại nhưng ứng dụng vẫn cố chạy thêm câu SQL trong trạng thái lỗi.

Điểm khó không chỉ là nhận ra thông báo lỗi. Quan trọng hơn là trả lời:

> Khi transaction bị lỗi do cạnh tranh đồng thời, phải thử lại **câu lệnh cuối cùng** hay **toàn bộ các bước đọc, kiểm tra, tính toán và ghi dữ liệu**?

Trong đa số tình huống PostgreSQL báo deadlock hoặc serialization failure, cần **hủy transaction bị lỗi rồi retry toàn bộ đơn vị nghiệp vụ** trong một transaction mới. Nếu chỉ chạy lại câu `UPDATE` cuối, bạn có thể dùng những dữ liệu và quyết định đã lỗi thời. Nếu vô tình gọi API bên ngoài mỗi lần thử, người dùng có thể bị thu tiền hoặc nhận thông báo nhiều lần.

Bài thuộc module **Database SQL**, chương **Giao dịch SQL**. Nội dung sử dụng PostgreSQL để minh họa, giải thích ý nghĩa SQLSTATE, mô phỏng hai phiên giao dịch, phân biệt tình huống khóa và lỗi isolation, thiết kế ranh giới retry, cùng ví dụ Java/JDBC và bài tập có lời giải.

## 1. Bốn hiện tượng dễ bị nhầm

| Hiện tượng | Mô tả | Ví dụ | Điều cần làm |
|---|---|---|---|
| **Lock wait** | Một transaction chờ tài nguyên do transaction khác giữ | B chờ A nhả khóa dòng 10 | Xác định người chặn, thời gian giữ khóa và nguyên nhân |
| **Deadlock** | Nhiều transaction tạo thành **vòng chờ** | A giữ dòng 10, đợi 20; B giữ 20, đợi 10 | Một transaction bị hủy; xem SQLSTATE `40P01` |
| **Serialization failure** | Lịch đọc/ghi cạnh tranh không thể thỏa bảo đảm tuần tự hóa | Hai người cùng kiểm tra còn 2 bác sĩ trực rồi cho hai người khác nhau nghỉ | Rollback và cân nhắc retry toàn transaction; xem `40001` |
| **Lost update** | Một thay đổi bị ghi đè do tác vụ dùng giá trị đã đọc cũ | A và B cùng đọc counter=0 rồi cùng ghi counter=1 | Dùng phép cập nhật nguyên tử, version/khóa phù hợp |

Còn hai trường hợp gần gũi:

- **Unique conflict:** hai transaction cố chèn cùng khóa duy nhất; PostgreSQL thường báo `23505` nếu câu SQL không có cách xử lý xung đột thích hợp.
- **Timeout/cancel:** câu SQL bị hủy vì quá thời gian hoặc không lấy được khóa ngay; không thể chỉ dựa vào chữ “lock” trong thông báo mà kết luận deadlock.

### 1.1. Lock wait không phải deadlock

```text
Session A giữ khóa X
Session B đợi khóa X
A COMMIT hoặc ROLLBACK
B tiếp tục
```

Đây là **chờ một chiều**. Khi A giải phóng khóa, B có thể tiến tiếp.

### 1.2. Deadlock là vòng chờ

```text
Session A giữ khóa X
Session B giữ khóa Y

A đợi Y đang do B giữ
B đợi X đang do A giữ

        A ──chờ──► B
        ▲          │
        └──chờ─────┘
```

Hai transaction không tự giải quyết được vòng chờ nếu không có bên từ bỏ một phần công việc. PostgreSQL có cơ chế phát hiện và chọn một transaction làm **nạn nhân deadlock**.

### 1.3. Serialization failure không nhất thiết có vòng khóa

Hai transaction có thể **không cập nhật cùng một dòng** nhưng cùng đọc một điều kiện tổng thể và cập nhật những dòng khác nhau, khiến kết quả chung không thể tương đương với cách thực thi tuần tự hợp lệ. PostgreSQL ở mức `SERIALIZABLE` có thể hủy một transaction bằng `40001` để giữ tính đúng đắn.

**Deadlock là một vấn đề đồ thị chờ khóa; serialization failure là một vấn đề tính hợp lệ của lịch giao dịch.**

## 2. Transaction và ranh giới công việc

Một transaction PostgreSQL:

```sql
BEGIN;

-- Đọc dữ liệu.
-- Kiểm tra điều kiện.
-- Cập nhật một hoặc nhiều bảng.

COMMIT;
```

Khi một bước thất bại:

```sql
ROLLBACK;
```

Tính nguyên tử (*atomicity*) giúp các thay đổi transactional trong database được **commit cùng nhau** hoặc **rollback cùng nhau**. Nhưng một transaction không có nghĩa các quyết định bên trong không thể cạnh tranh với transaction khác. Mức cô lập (*isolation*) và các khóa/ràng buộc mới quyết định những tương tác đồng thời được phép.

Với một nghiệp vụ chuyển tiền, ranh giới công việc thường gồm:

1. Đọc số dư và trạng thái tài khoản.
2. Kiểm tra hạn mức, số dư và quyền chuyển.
3. Trừ số dư tài khoản gửi.
4. Cộng số dư tài khoản nhận.
5. Ghi giao dịch, mã yêu cầu và thông tin kiểm toán.
6. Commit.

Nếu gặp lỗi `40001`/`40P01`, **chỉ lặp lại bước 4** không đủ: số dư và điều kiện ở bước 1–2 có thể đã thay đổi. Cần thực hiện lại **toàn bộ logic transaction** từ trạng thái mới.

### 2.1. Không được nhầm transaction với một HTTP request

Một HTTP request có thể bao gồm:

- Kiểm tra người dùng và dữ liệu đầu vào.
- Giao dịch SQL.
- Gửi email/SMS.
- Gọi dịch vụ thanh toán.
- Trả phản hồi.

Những thao tác ngoài DB không được PostgreSQL tự động rollback. Vì vậy, **ranh giới retry transaction** không được tự động bao gồm một API thu tiền hoặc gửi email không có cơ chế chống lặp.

## 3. SQLSTATE cần nhận diện

PostgreSQL trả mã SQLSTATE để phân loại lỗi độc lập với văn bản thông báo.

| SQLSTATE | Tên thường gặp | Ý nghĩa | Cách tiếp cận |
|---|---|---|---|
| `40P01` | `deadlock_detected` | Có vòng chờ khóa; một transaction bị hủy | Rollback; retry **toàn transaction** nếu nghiệp vụ cho phép |
| `40001` | `serialization_failure` | Transaction không thỏa yêu cầu isolation | Rollback; retry **toàn transaction** nếu an toàn |
| `25P02` | `in_failed_sql_transaction` | Transaction đã bị đánh dấu lỗi vì một lệnh trước đó | Tìm **lỗi gốc**, rollback |
| `55P03` | `lock_not_available` | Không lấy được khóa khi `NOWAIT` hoặc vượt `lock_timeout` | Xác định khóa/timeout; không mặc định deadlock |
| `57014` | `query_canceled` | Statement bị hủy, có thể do `statement_timeout`/cancel request | Xác định nguyên nhân và phạm vi hủy |
| `23505` | `unique_violation` | Trùng khóa duy nhất | Xem idempotency, `ON CONFLICT`, không retry mù |
| `23503` | `foreign_key_violation` | Vi phạm khóa ngoại | Kiểm tra dữ liệu và quan hệ |
| `23514` | `check_violation` | Vi phạm ràng buộc `CHECK` | Sửa điều kiện nghiệp vụ/dữ liệu |
| `23502` | `not_null_violation` | Giá trị cần có bị thiếu | Sửa nguồn dữ liệu |
| `08006` | `connection_failure` | Kết nối thất bại | Đặc biệt thận trọng nếu đúng lúc `COMMIT` |
| `08003` | `connection_does_not_exist` | Connection không còn hợp lệ | Xác định kết quả đã commit hay chưa |

### 3.1. Mã 25P02 không phải nguyên nhân ban đầu

Giả sử:

```sql
BEGIN;

-- Một câu UPDATE bị lỗi deadlock, unique hoặc constraint.

SELECT 1;  -- Có thể báo 25P02.

ROLLBACK;
```

Trong PostgreSQL, nhiều lỗi statement làm transaction rơi vào trạng thái aborted. Câu `SELECT 1` chạy sau đó chỉ báo rằng **transaction hiện hỏng**. Muốn biết có cần retry không, bạn phải đọc **SQLSTATE của lỗi đầu tiên**, không chỉ `25P02`.

### 3.2. Retryable không có nghĩa phải retry vô hạn

`40P01` và `40001` thường là ứng viên để retry transaction. Nhưng cần đồng thời đảm bảo:

- Công việc có thể được làm lại an toàn.
- Không lặp tác dụng phụ đã thực hiện bên ngoài DB.
- Không vượt thời hạn tổng thể của request.
- Có giới hạn attempt, backoff/jitter và ghi nhận lỗi.
- Mọi điều kiện nghiệp vụ được tính lại từ dữ liệu mới.

Lỗi `23505` đôi khi liên quan cạnh tranh đồng thời, nhưng có thể đơn thuần là “mã đã tồn tại”. Không nên tự động lặp đi lặp lại cùng câu `INSERT` mà không xem khóa nghiệp vụ.

## 4. Chuẩn bị cơ sở dữ liệu thực hành

Các đoạn SQL dưới đây dành cho **database thử nghiệm**. Chạy `CREATE TABLE` và các lệnh `INSERT` dữ liệu mẫu một lần.

### 4.1. Hai tài khoản cho bài deadlock

```sql
CREATE TABLE lesson307_accounts (
    account_id INTEGER PRIMARY KEY,
    owner_name VARCHAR(100) NOT NULL,
    balance NUMERIC(14, 2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO lesson307_accounts (
    account_id,
    owner_name,
    balance
)
VALUES
    (10, 'Tài khoản A', 1000.00),
    (20, 'Tài khoản B', 1000.00);
```

### 4.2. Hai bác sĩ trực cho bài serialization

```sql
CREATE TABLE lesson307_on_call (
    shift_date DATE NOT NULL,
    doctor_id INTEGER NOT NULL,
    doctor_name VARCHAR(100) NOT NULL,
    on_duty BOOLEAN NOT NULL,
    PRIMARY KEY (shift_date, doctor_id)
);

INSERT INTO lesson307_on_call (
    shift_date,
    doctor_id,
    doctor_name,
    on_duty
)
VALUES
    (DATE '2026-11-14', 1, 'Bác sĩ An', TRUE),
    (DATE '2026-11-14', 2, 'Bác sĩ Bình', TRUE);
```

Quy tắc nghiệp vụ giả định: **ít nhất một bác sĩ phải đang trực**. Bảng chưa có ràng buộc database ép điều kiện tổng hợp này.

### 4.3. Marker yêu cầu và outbox để giải thích retry

```sql
CREATE TABLE lesson307_transfers (
    request_key VARCHAR(80) PRIMARY KEY,
    from_account_id INTEGER NOT NULL
        REFERENCES lesson307_accounts(account_id),
    to_account_id INTEGER NOT NULL
        REFERENCES lesson307_accounts(account_id),
    transfer_amount NUMERIC(14, 2) NOT NULL
        CHECK (transfer_amount > 0),
    status VARCHAR(20) NOT NULL
        CHECK (status = 'DONE'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (from_account_id <> to_account_id)
);

CREATE TABLE lesson307_outbox (
    outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key VARCHAR(80) NOT NULL UNIQUE
        REFERENCES lesson307_transfers(request_key),
    event_type VARCHAR(40) NOT NULL,
    payload TEXT NOT NULL,
    delivered_at TIMESTAMPTZ
);
```

Bảng `transfers` dùng `request_key` duy nhất để nhận diện **một yêu cầu logic**; bảng `outbox` dùng để lưu sự kiện cần gửi **sau commit**.

Kiểm tra trạng thái bắt đầu:

```sql
SELECT account_id, balance
FROM lesson307_accounts
ORDER BY account_id;

SELECT doctor_id, on_duty
FROM lesson307_on_call
WHERE shift_date = DATE '2026-11-14'
ORDER BY doctor_id;
```

Kết quả ban đầu: số dư `1000` mỗi tài khoản và hai bác sĩ đều `TRUE`.

## 5. Minh họa lock wait bình thường

Mở **hai connection độc lập** đến cùng database thử nghiệm.

**Session A:**

```sql
BEGIN;

UPDATE lesson307_accounts
SET balance = balance + 10
WHERE account_id = 10;

-- Giữ transaction mở.
```

**Session B:**

```sql
BEGIN;

UPDATE lesson307_accounts
SET balance = balance + 20
WHERE account_id = 10;

-- Có thể đợi A nhả khóa.
```

Session B có thể đang chờ vì Session A đã sửa và khóa dòng 10. Nếu Session A chạy:

```sql
ROLLBACK;
```

thì B có thể tiếp tục. Sau đó B cũng chạy:

```sql
ROLLBACK;
```

để trả dữ liệu mẫu về trạng thái ban đầu.

Vì A **không đang chờ khóa của B**, trường hợp này **không tạo vòng deadlock**.

**Bài học:** một truy vấn đang chờ lâu chưa đủ để kết luận deadlock. Kiểm tra loại wait, PID chặn, transaction đang giữ khóa và SQLSTATE.

## 6. Minh họa deadlock với hai session

Đây là ví dụ chủ đạo. Bạn cần hai cửa sổ SQL chạy **song song**; thứ tự thao tác quan trọng.

### 6.1. Dòng thời gian

| Bước | Session A | Session B |
|---:|---|---|
| 1 | `BEGIN` | |
| 2 | Sửa tài khoản **10**, giữ khóa dòng 10 | |
| 3 | | `BEGIN` |
| 4 | | Sửa tài khoản **20**, giữ khóa dòng 20 |
| 5 | Sửa tài khoản **20**, phải **đợi B** | |
| 6 | | Sửa tài khoản **10**, phải **đợi A** |
| 7 | PostgreSQL phát hiện vòng chờ; hủy một transaction | |
| 8 | Kết thúc/rollback cả hai để không lưu thay đổi thử | |

### 6.2. Session A giữ khóa dòng 10

```sql
BEGIN;

UPDATE lesson307_accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Chưa COMMIT hoặc ROLLBACK.
```

### 6.3. Session B giữ khóa dòng 20

```sql
BEGIN;

UPDATE lesson307_accounts
SET balance = balance + 50
WHERE account_id = 20;

-- Chưa COMMIT hoặc ROLLBACK.
```

### 6.4. Session A muốn dòng 20

```sql
UPDATE lesson307_accounts
SET balance = balance + 100
WHERE account_id = 20;
```

Khi B còn giữ khóa dòng 20, câu lệnh của A có thể **đứng chờ**. Giữ nguyên cửa sổ A và quay sang cửa sổ B.

### 6.5. Session B muốn dòng 10

```sql
UPDATE lesson307_accounts
SET balance = balance - 50
WHERE account_id = 10;
```

B đang giữ khóa dòng 20 nhưng muốn khóa dòng 10 do A giữ. Đồng thời A vẫn muốn dòng 20.

```text
A giữ row 10, muốn row 20 ───────► B
▲                                   │
└──────── B muốn row 10, giữ row 20 ┘
```

PostgreSQL sẽ phát hiện vòng chờ và một transaction có thể nhận:

```text
ERROR: deadlock detected
SQLSTATE: 40P01
```

**Không thể dự đoán Session A hay B luôn là nạn nhân**: điều đó tùy lịch thực thi và cách engine xử lý.

### 6.6. Kết thúc thí nghiệm

- Session nhận `40P01` chạy `ROLLBACK` để kết thúc transaction lỗi.
- Session còn lại, khi đã tiếp tục được, cũng chạy `ROLLBACK` để giữ nguyên dữ liệu mẫu.
- Sau đó kiểm tra lại:

```sql
SELECT account_id, balance
FROM lesson307_accounts
ORDER BY account_id;
```

Nếu cả hai rollback, kết quả vẫn là hai tài khoản có `balance = 1000`.

### 6.7. Kết luận từ thí nghiệm

Một câu UPDATE đơn lẻ không nhất thiết sai. Chính **thứ tự lấy khóa kết hợp giữa các transaction** mới tạo ra vòng chờ.

Khi `40P01` xảy ra, PostgreSQL đã chọn một transaction để hủy và giúp các transaction khác có cơ hội tiếp tục. Với transaction bị hủy, không nên chạy lại chỉ câu UPDATE cuối: phải retry **toàn bộ bước nghiệp vụ** nếu yêu cầu thực sự cần hoàn tất.

## 7. Giảm deadlock bằng thứ tự khóa nhất quán

Nếu mọi transaction cần sửa tài khoản 10 và 20 đều lấy khóa theo thứ tự `10 → 20`, một transaction có thể phải chờ dòng 10, nhưng sẽ khó hình thành vòng chờ hai chiều như ở phần trước.

```sql
BEGIN;

SELECT account_id
FROM lesson307_accounts
WHERE account_id = 10
FOR UPDATE;

SELECT account_id
FROM lesson307_accounts
WHERE account_id = 20
FOR UPDATE;

-- Kiểm tra điều kiện và cập nhật theo nghiệp vụ.

ROLLBACK;
```

### 7.1. Quy tắc cho nhiều khóa

Khi cần xử lý một tập tài khoản động:

1. Chuẩn hóa danh sách ID.
2. Loại bản sao ID nếu phù hợp.
3. Sắp theo một quy tắc ổn định, ví dụ số tăng dần.
4. Lấy khóa theo đúng thứ tự đã thống nhất.
5. Mới tiến hành thay đổi.

Không mặc định thứ tự đọc vật lý của một bảng hoặc thứ tự kết quả không có `ORDER BY` chính là thứ tự khóa mong muốn.

### 7.2. Vẫn cần retry

Thứ tự khóa nhất quán **giảm** deadlock, không đảm bảo loại hoàn toàn. FK, trigger, nhiều bảng và những luồng khác có thể lấy thêm loại khóa ngoài dự kiến. Ứng dụng vẫn cần xử lý `40P01` có kiểm soát.

### 7.3. Transaction ngắn giúp giảm contention

Tránh giữ transaction mở trong khi:

- Đợi người dùng xác nhận.
- Gọi API mạng chậm.
- Tạo báo cáo nặng không cần thiết.
- Ngủ để retry.
- Đợi một hệ thống khác có thời gian phản hồi không xác định.

Giữ khóa càng lâu, các session khác càng dễ bị chờ và gặp vòng khóa phức tạp.

## 8. Lỗi tuần tự hóa: hai bác sĩ cùng xin nghỉ

Ta có hai bác sĩ đang trực. Quy tắc nghiệp vụ là **ít nhất một người phải còn trực**.

Mỗi transaction muốn cho **một bác sĩ khác nhau** nghỉ:

- A muốn cho bác sĩ 1 nghỉ.
- B muốn cho bác sĩ 2 nghỉ.

Quy trình của mỗi bên:

```text
Đếm số bác sĩ đang trực.
Nếu số lượng >= 2, có thể cho một người nghỉ.
Cập nhật on_duty = FALSE cho người được chọn.
```

### 8.1. Trong READ COMMITTED: có thể xảy ra write skew

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS on_duty_count
FROM lesson307_on_call
WHERE shift_date = DATE '2026-11-14'
  AND on_duty = TRUE;

-- Giả sử kết quả = 2.
```

**Session B**, trước khi A cập nhật:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS on_duty_count
FROM lesson307_on_call
WHERE shift_date = DATE '2026-11-14'
  AND on_duty = TRUE;

-- Cũng có thể nhận kết quả = 2.
```

**A cập nhật bác sĩ 1:**

```sql
UPDATE lesson307_on_call
SET on_duty = FALSE
WHERE shift_date = DATE '2026-11-14'
  AND doctor_id = 1;

COMMIT;
```

**B vẫn dựa vào lần đọc cũ và cập nhật bác sĩ 2:**

```sql
UPDATE lesson307_on_call
SET on_duty = FALSE
WHERE shift_date = DATE '2026-11-14'
  AND doctor_id = 2;

COMMIT;
```

Cả hai transaction có thể commit vì chúng sửa **hai dòng khác nhau**. Kết quả chỉ còn **0 bác sĩ trực**, trái quy tắc nghiệp vụ.

### 8.2. Vì sao đây là write skew?

Mỗi transaction:

- Đọc một điều kiện trên **tập nhiều dòng**.
- Dựa vào trạng thái đã đọc để ra quyết định.
- Chỉ cập nhật **một dòng riêng**.

Hai tập ghi không cần trùng nhau nhưng các quyết định đọc/ghi phụ thuộc lẫn nhau. Mỗi transaction riêng lẻ có vẻ đúng; cả hai cùng commit lại làm sai bất biến.

### 8.3. REPEATABLE READ có đủ không?

PostgreSQL `REPEATABLE READ` dùng snapshot isolation và cung cấp bảo đảm mạnh hơn `READ COMMITTED` về tính nhất quán giữa các lần đọc trong cùng transaction.

Tuy nhiên, **write skew trên hai dòng khác nhau** vẫn có thể xảy ra ở snapshot isolation. Do đó không suy luận “repeatable read” tự bảo vệ mọi ràng buộc tổng hợp.

## 9. Cùng bài toán ở SERIALIZABLE

Trước kịch bản, reset cả hai bác sĩ về trạng thái trực trong database thực hành:

```sql
UPDATE lesson307_on_call
SET on_duty = TRUE
WHERE shift_date = DATE '2026-11-14';
```

### 9.1. Cả A và B đọc trước khi ai cập nhật

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_duty_count
FROM lesson307_on_call
WHERE shift_date = DATE '2026-11-14'
  AND on_duty = TRUE;
```

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_duty_count
FROM lesson307_on_call
WHERE shift_date = DATE '2026-11-14'
  AND on_duty = TRUE;
```

Nếu điều phối đúng thứ tự, cả hai cùng đọc `2` trước khi xuất hiện cập nhật.

### 9.2. Cập nhật hai bác sĩ khác nhau

**Session A:**

```sql
UPDATE lesson307_on_call
SET on_duty = FALSE
WHERE shift_date = DATE '2026-11-14'
  AND doctor_id = 1;
```

**Session B:**

```sql
UPDATE lesson307_on_call
SET on_duty = FALSE
WHERE shift_date = DATE '2026-11-14'
  AND doctor_id = 2;
```

Sau đó thử `COMMIT` ở từng session.

Ở PostgreSQL `SERIALIZABLE`, kịch bản hai transaction cùng quan sát tập đầy đủ rồi cập nhật theo cách này không được phép dẫn đến **hai commit thành công** nếu kết quả không còn người trực. Một transaction có thể nhận:

```text
ERROR: could not serialize access ...
SQLSTATE: 40001
```

Lỗi có thể xuất hiện tại statement hoặc `COMMIT` tùy lịch thực thi. **Không cố định session nào sẽ thất bại.**

### 9.3. Retry toàn transaction mới giữ được bất biến

Nếu A đã commit làm bác sĩ 1 nghỉ, B gặp `40001`:

- **Sai:** chỉ chạy lại `UPDATE doctor_id = 2 SET on_duty = FALSE`.
- **Đúng:** rollback B, tạo transaction mới, **đếm lại** số bác sĩ đang trực. Lúc này chỉ còn bác sĩ 2, nên quy tắc nghiệp vụ **không cho phép** người này nghỉ.

Thử lại **có thể dẫn đến quyết định nghiệp vụ khác**. Đó chính là mục đích của việc đọc lại dữ liệu: không cố thực hiện một quyết định chỉ đúng với snapshot cũ.

### 9.4. Serializable Snapshot Isolation (SSI)

PostgreSQL sử dụng cơ chế Serializable Snapshot Isolation để phát hiện những phụ thuộc đọc/ghi nguy hiểm. Nó **không đơn giản khóa tất cả bảng mỗi khi SELECT**, và việc một transaction bị từ chối để đảm bảo tính tuần tự hóa không có nghĩa SQL sai cú pháp.

`40001` là kết quả cần được ứng dụng chuẩn bị xử lý khi sử dụng isolation mạnh trong môi trường cạnh tranh.

## 10. So sánh deadlock và serialization failure

| Tiêu chí | Deadlock `40P01` | Serialization `40001` |
|---|---|---|
| Nguyên nhân trực tiếp | **Vòng chờ khóa** | **Lịch giao dịch vi phạm bảo đảm tuần tự hóa** |
| Hai transaction có phải sửa cùng dòng không? | Không bắt buộc, nhưng thường tranh các khóa xung đột | Không; có thể ghi các dòng khác nhau |
| Xuất hiện ở mức nào? | Có thể ở nhiều mức isolation | Tùy mức và loại xung đột; nổi bật ở `REPEATABLE READ`/`SERIALIZABLE` |
| Hệ quản trị xử lý | Hủy một transaction để phá vòng | Từ chối một transaction để duy trì isolation |
| Có thể retry không? | Thường có, với điều kiện | Thường có, với điều kiện |
| Phạm vi retry | **Toàn transaction** | **Toàn transaction** |
| Giảm tần suất | Thứ tự khóa, thời gian khóa, index, giảm tranh chấp | Thiết kế bất biến, thao tác đọc/ghi, isolation và retry |

**Điểm chung quan trọng nhất:** khi transaction đã thất bại, mọi quyết định được ra từ trạng thái đọc trong lần đó phải được xem xét lại ở attempt mới.

## 11. Timeout, NOWAIT và SKIP LOCKED

### 11.1. lock_timeout

PostgreSQL cho phép giới hạn thời gian đợi khóa:

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';

UPDATE lesson307_accounts
SET balance = balance + 1
WHERE account_id = 10;

ROLLBACK;
```

Nếu một session khác đang giữ khóa xung đột quá lâu, câu SQL có thể bị hủy do `lock_timeout`, thường với SQLSTATE `55P03`.

Đó không nhất thiết là deadlock: có thể chỉ có một transaction chờ transaction khác.

### 11.2. statement_timeout

```sql
BEGIN;

SET LOCAL statement_timeout = '3s';

SELECT pg_sleep(10);

ROLLBACK;
```

Truy vấn có thể bị hủy bởi `statement_timeout`, thường với SQLSTATE `57014`. Đây là lỗi **statement bị cancel**, không tự chứng minh có vòng khóa hay lỗi tuần tự hóa.

Sau khi statement lỗi bên trong transaction PostgreSQL, cần rollback/kết thúc transaction lỗi hoặc dùng savepoint đã thiết kế phù hợp; không tiếp tục như thể không có lỗi.

### 11.3. FOR UPDATE NOWAIT

```sql
BEGIN;

SELECT account_id
FROM lesson307_accounts
WHERE account_id = 10
FOR UPDATE NOWAIT;

ROLLBACK;
```

`NOWAIT` yêu cầu không chờ khóa dòng. Nếu dòng đang bị giữ bởi transaction khác và khóa không lấy được ngay, câu này có thể báo `55P03`.

### 11.4. FOR UPDATE SKIP LOCKED

```sql
BEGIN;

SELECT account_id
FROM lesson307_accounts
WHERE account_id IN (10, 20)
ORDER BY account_id
FOR UPDATE SKIP LOCKED;

ROLLBACK;
```

`SKIP LOCKED` bỏ qua một số dòng đang bị khóa, hữu ích cho một số mô hình **queue nhiều worker**. Nhưng truy vấn có thể trả **tập không đầy đủ**, không phù hợp khi bạn cần tính tổng chính xác hoặc kiểm tra bất biến phải bao trùm mọi dòng.

**Không dùng `SKIP LOCKED` để né lỗi đồng thời trong bài toán chuyển tiền hoặc kiểm tra số người trực.**

## 12. Vì sao retry trong transaction bị lỗi là sai?

Luồng có rủi ro:

```text
BEGIN
Đọc số dư
UPDATE tài khoản A
UPDATE tài khoản B → lỗi 40P01
Ứng dụng bắt lỗi
UPDATE tài khoản B lần nữa → 25P02
COMMIT (không thể hoàn tất transaction như mong muốn)
```

Transaction PostgreSQL đã bị đánh dấu lỗi; chạy lại statement trong cùng transaction thường chỉ tạo thêm `25P02`.

Quy trình đúng cho `40001`/`40P01`:

1. Ghi nhận **SQLSTATE gốc**.
2. `ROLLBACK` transaction thất bại.
3. Giải phóng khóa và tài nguyên.
4. Chờ backoff có giới hạn nếu còn attempt.
5. Tạo **transaction mới**.
6. Đọc lại dữ liệu, kiểm tra, tính lại và ghi lại.
7. Chỉ báo thành công khi `COMMIT` thành công.

### 12.1. Cần retry cả phần tính toán

Giả sử lần đầu đọc số dư 1.000 và tính có thể chuyển 700. Trong thời gian bạn retry, transaction khác đã chuyển 500, khiến số dư chỉ còn 500.

Nếu chỉ chạy lại `UPDATE balance = balance - 700` với quyết định cũ, bạn có thể làm sai nghiệp vụ. Lần thử mới phải kiểm tra lại **số dư hiện tại**.

### 12.2. Không phải mọi biến phải tạo lại

Giữ ổn định qua các attempt:

- `request_key` đại diện cùng một yêu cầu.
- ID người yêu cầu đã xác thực.
- Số tiền người dùng đã gửi.
- Những tham số đầu vào không phụ thuộc kết quả đọc DB.

Phải đọc/tính lại:

- Số dư/tồn kho hiện tại.
- Trạng thái đơn và hạn mức.
- Điều kiện còn đủ người trực.
- Những phép tính dựa trên dữ liệu database có thể thay đổi.

## 13. Mẫu retry có giới hạn và backoff

Một vòng retry nên bao phủ **toàn bộ transaction**:

```text
request_key được tạo một lần trước vòng lặp

for attempt = 1..MAX_ATTEMPTS:
    mở connection/transaction mới
    try:
        đọc lại các dòng cần thiết
        kiểm tra nghiệp vụ và tính lại kết quả
        ghi toàn bộ bảng liên quan
        ghi marker/outbox trong cùng transaction nếu cần
        COMMIT
        return SUCCESS
    catch SQLSTATE 40001 hoặc 40P01:
        ROLLBACK
        nếu hết số lần: báo lỗi tạm thời
        chờ backoff và jitter SAU khi nhả khóa
        tiếp tục attempt mới
    catch lỗi nghiệp vụ hoặc constraint:
        ROLLBACK
        trả lỗi phù hợp, không retry vô hạn
    catch lỗi kết nối ở COMMIT:
        outcome có thể không rõ
        dùng request_key để xác minh trước khi thực hiện lại
```

### 13.1. Backoff và jitter

Một chính sách minh họa:

\[
\mathrm{delay} = \min(\mathrm{cap}, \mathrm{base}\times 2^{\mathrm{attempt}-1}) + \mathrm{jitter}.
\]

Ví dụ `base = 50 ms`, `cap = 1000 ms`, jitter chọn ngẫu nhiên `0..49 ms`.

Backoff giúp tránh worker liên tục va vào cùng khóa; jitter giúp các worker không retry đồng loạt đúng một nhịp.

**Chờ sau rollback**, không giữ transaction hoặc khóa trong thời gian nghỉ.

### 13.2. Có tối đa bao nhiêu attempt?

Không có số lần chung cho mọi hệ thống. Chọn giới hạn dựa trên SLA, độ tranh chấp, thời hạn request và độ quan trọng nghiệp vụ. Ví dụ `MAX_ATTEMPTS = 5` chỉ là minh họa.

Khi hết số lần, ghi nhận sự cố và trả lỗi rõ ràng hoặc đưa vào luồng xử lý sau theo thiết kế. **Retry vô hạn có thể biến một sự cố khóa thành một cơn bão tải.**

## 14. Java/JDBC: ví dụ ranh giới retry toàn giao dịch

Ví dụ dùng PostgreSQL JDBC và `DataSource`. Nó thể hiện cách tổ chức retry về mặt kỹ thuật; **không phải** mã chuyển tiền production đầy đủ vì còn cần phân quyền, sổ cái, kiểm toán, idempotency end-to-end và quy trình tài chính.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.ThreadLocalRandom;

public final class TxRetryExample {
    private static final int MAX_ATTEMPTS = 5;

    private TxRetryExample() {}

    public static void transfer(
            DataSource dataSource,
            int fromId,
            int toId,
            BigDecimal amount
    ) throws SQLException, InterruptedException {
        if (fromId == toId) {
            throw new IllegalArgumentException(
                    "Hai tài khoản phải khác nhau");
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try (Connection connection = dataSource.getConnection()) {
                connection.setTransactionIsolation(
                        Connection.TRANSACTION_SERIALIZABLE);
                connection.setAutoCommit(false);

                try {
                    // Khóa theo thứ tự ID giúp giảm deadlock.
                    lockAccount(connection, Math.min(fromId, toId));
                    lockAccount(connection, Math.max(fromId, toId));

                    debit(connection, fromId, amount);
                    credit(connection, toId, amount);

                    connection.commit();
                    return;
                } catch (SQLException error) {
                    rollbackQuietly(connection, error);
                    if (!isRetryable(error)
                            || attempt == MAX_ATTEMPTS) {
                        throw error;
                    }
                } catch (RuntimeException error) {
                    rollbackQuietly(connection, error);
                    throw error;
                }
            }

            // Connection cũ đã đóng và khóa đã được thả.
            long delay = Math.min(
                    1000L, 50L * (1L << (attempt - 1)));
            long jitter =
                    ThreadLocalRandom.current().nextLong(50L);
            Thread.sleep(delay + jitter);
        }

        throw new IllegalStateException("Không đạt tới đây");
    }

    private static void lockAccount(
            Connection connection, int id
    ) throws SQLException {
        String sql = """
            SELECT account_id
            FROM lesson307_accounts
            WHERE account_id = ?
            FOR UPDATE
            """;
        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {
            ps.setInt(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalArgumentException(
                            "Tài khoản không tồn tại: " + id);
                }
            }
        }
    }

    private static void debit(
            Connection connection, int id, BigDecimal amount
    ) throws SQLException {
        String sql = """
            UPDATE lesson307_accounts
            SET balance = balance - ?
            WHERE account_id = ?
              AND balance >= ?
            """;
        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setInt(2, id);
            ps.setBigDecimal(3, amount);
            if (ps.executeUpdate() != 1) {
                throw new IllegalStateException(
                        "Không đủ số dư hoặc tài khoản không tồn tại");
            }
        }
    }

    private static void credit(
            Connection connection, int id, BigDecimal amount
    ) throws SQLException {
        String sql = """
            UPDATE lesson307_accounts
            SET balance = balance + ?
            WHERE account_id = ?
            """;
        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setInt(2, id);
            if (ps.executeUpdate() != 1) {
                throw new IllegalStateException(
                        "Tài khoản nhận không tồn tại");
            }
        }
    }

    private static boolean isRetryable(SQLException error) {
        String state = error.getSQLState();
        return "40001".equals(state) || "40P01".equals(state);
    }

    private static void rollbackQuietly(
            Connection connection, Throwable original
    ) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            original.addSuppressed(rollbackError);
        }
    }
}
```

### 14.1. Điều gì được thử lại?

Mỗi attempt lấy connection và transaction mới, khóa đúng các dòng, thực hiện cả hai cập nhật, rồi commit. Nếu bị `40001`/`40P01`, attempt cũ rollback, connection đóng, sau đó attempt mới bắt đầu lại.

### 14.2. Lỗi nghiệp vụ không bị retry mù

Nếu không đủ số dư, code phát sinh `IllegalStateException` và rollback thay vì tự retry liên tục. Một hệ thống thật nên dùng loại exception nghiệp vụ riêng và hợp đồng trả lỗi rõ ràng.

### 14.3. Vì sao không retry lỗi kết nối ở COMMIT?

Nếu mất kết nối đúng lúc `COMMIT`, kết quả có thể **chưa rõ**: DB có thể đã commit và chỉ phản hồi bị mất. Mẫu trên **không** đưa mọi SQLException vào nhóm retry. Muốn an toàn cho nghiệp vụ thật, cần marker `request_key` và cơ chế đối chiếu kết quả.

### 14.4. Connection pool và autocommit

Nếu dùng connection pool:

- Không tái sử dụng transaction đang lỗi.
- Đảm bảo rollback/đóng connection đúng.
- Quản lý cấu hình isolation/autocommit theo hợp đồng pool.
- Không giữ transaction mở trong thời gian backoff.

## 15. Spring: retry nên nằm ngoài transaction

Khi dùng Spring `@Transactional`, một lỗi thường gặp là triển khai vòng retry **trong chính phương thức đang giữ transaction**. Những lần thử có thể tiếp tục dùng transaction đã bị đánh dấu rollback-only hoặc connection đã lỗi.

Mục tiêu:

```text
Coordinator có retry
    │
    ├── Attempt 1 → tạo transaction 1 → rollback
    ├── chờ backoff
    ├── Attempt 2 → tạo transaction 2 → rollback
    ├── chờ backoff
    └── Attempt 3 → tạo transaction 3 → commit
```

Một mẫu kiến trúc:

```java
// Minh họa ý tưởng, không phải một ứng dụng Spring hoàn chỉnh.

class RetryCoordinator {
    private final TransferTransactionService transferService;

    void execute(TransferRequest request) {
        for (int attempt = 1; attempt <= 5; attempt++) {
            try {
                transferService.runOneTransaction(request);
                return;
            } catch (RetryableDatabaseException ex) {
                if (attempt == 5) {
                    throw ex;
                }
                // Backoff sau khi transaction cũ đã rollback.
            }
        }
    }
}

class TransferTransactionService {
    // @Transactional trên method được gọi qua bean/proxy.
    void runOneTransaction(TransferRequest request) {
        // Đọc lại, tính lại, ghi và commit khi method hoàn tất.
    }
}
```

Trong Spring dùng proxy, gọi `this.runOneTransaction(...)` trong chính bean có thể **không đi qua proxy** nên không tạo transaction như mong muốn. Cũng cần lưu ý exception SQL có thể đã được framework dịch sang các loại exception khác; khi định nghĩa retry hãy kiểm tra đúng cause/SQLSTATE.

**Ranh giới vẫn phải bao quanh transaction thật**, bao gồm cả thời điểm commit xảy ra khi rời phương thức transactional.

## 16. Savepoint có thay thế rollback toàn transaction không?

PostgreSQL hỗ trợ savepoint:

```sql
BEGIN;

SAVEPOINT before_optional_step;

-- Thử một bước tùy chọn.

ROLLBACK TO SAVEPOINT before_optional_step;

ROLLBACK;
```

Savepoint hữu ích khi một bước có thể lỗi cục bộ và nghiệp vụ cho phép bỏ qua nó. Nhưng nó **không phải cơ chế mặc định để “cứu” các quyết định cũ sau `40001`/`40P01`**.

Ví dụ sai về tư duy:

```text
BEGIN
SELECT tồn kho → còn 1
SAVEPOINT s1
UPDATE đơn → serialization_failure
ROLLBACK TO s1
UPDATE đơn lần nữa với quyết định "còn 1"
COMMIT
```

Ngay cả khi một thao tác savepoint cụ thể được DBMS cho phép, dữ liệu đọc trước đó có thể đã lỗi thời; giữ nguyên quyết định nghiệp vụ là không an toàn.

Với lỗi serialization/deadlock, cách xử lý vững là **rollback transaction lỗi và chạy lại toàn bộ quy trình từ đầu**. Savepoint dành cho những tình huống xử lý lỗi cục bộ có ý nghĩa khác.

## 17. Trạng thái COMMIT không rõ là rủi ro khác

Giả sử ứng dụng thực hiện:

```text
BEGIN
UPDATE accounts ...
INSERT transfers(request_key = 'TR-001')
COMMIT
```

và **mất kết nối ngay sau khi gửi `COMMIT`**.

Hai khả năng:

1. PostgreSQL chưa commit; transaction đã bị bỏ.
2. PostgreSQL đã commit nhưng phản hồi bị mất trên đường mạng.

Nếu ứng dụng giả định trường hợp 1 rồi thực hiện lại bằng **request key mới**, trường hợp 2 có thể làm chuyển tiền **hai lần**.

### 17.1. Khác với 40001 như thế nào?

`40001` là thông báo DBMS từ chối transaction theo cơ chế serialization. Mất kết nối ở COMMIT có thể khiến client **không biết outcome**, nên không thể tự kết luận “chắc chắn rollback”.

### 17.2. Một request key bền vững

Nên dùng một `request_key` đại diện cho **cùng một yêu cầu logic**, ví dụ `TR-001`.

Trong cùng transaction với thay đổi số dư:

- Ghi một marker `lesson307_transfers(request_key, ...)`.
- Bảo đảm `PRIMARY KEY(request_key)`.
- Ghi các bút toán/audit cần thiết.
- Commit cùng nhau.

Khi kết nối bị mất, ứng dụng tạo kết nối mới, tra theo **cùng request_key** và xác định kết quả. Nếu marker xác nhận giao dịch đã hoàn tất, không làm lại phần chuyển tiền. Nếu chưa có kết quả, việc thử lại phải tiếp tục dùng **cùng request_key** với unique constraint và chính sách idempotency đúng.

**Marker phải nằm trong cùng transaction với các thay đổi nghiệp vụ**, không ghi sau khi số dư đã commit.

### 17.3. Cùng key nhưng payload khác

Nếu `TR-001` lần đầu yêu cầu chuyển 100, lần sau gửi lại cùng key nhưng số tiền 500, hệ thống phải nhận diện **yêu cầu không nhất quán** thay vì im lặng áp dụng kết quả cũ hoặc chuyển thêm tiền.

Thường cần lưu hash/fingerprint hoặc các trường bất biến của yêu cầu để so sánh.

## 18. Transactional outbox và tác dụng phụ sau commit

Nếu gửi email hoặc gọi API bên ngoài **trong transaction có retry**, hai attempt đầu có thể gửi sự kiện ra ngoài dù dữ liệu DB bị rollback.

Một mô hình thường dùng là **transactional outbox**:

1. Cập nhật dữ liệu nghiệp vụ.
2. Ghi marker/idempotency key.
3. Ghi bản ghi outbox cần phát.
4. Commit tất cả cùng transaction.
5. Một dispatcher **sau commit** đọc outbox để phát thông báo.

Minh họa cấu trúc marker/outbox, **không phải nghiệp vụ chuyển tiền đầy đủ**:

```sql
BEGIN;

-- Ở nghiệp vụ thật, các thay đổi số dư phải nằm
-- trong CÙNG transaction với marker và outbox này.

INSERT INTO lesson307_transfers (
    request_key,
    from_account_id,
    to_account_id,
    transfer_amount,
    status
)
VALUES (
    'TR-001',
    10,
    20,
    100.00,
    'DONE'
);

INSERT INTO lesson307_outbox (
    request_key,
    event_type,
    payload
)
VALUES (
    'TR-001',
    'TRANSFER_DONE',
    '{"requestKey":"TR-001","amount":"100.00"}'
);

COMMIT;
```

**Đoạn trên chỉ minh họa cấu trúc lưu dấu và sự kiện, không cập nhật số dư.** Không dùng riêng nó như giao dịch chuyển tiền hoàn chỉnh.

### 18.1. Outbox không tự tạo exactly-once end-to-end

Dispatcher có thể gửi sự kiện thành công nhưng chết trước khi đánh dấu `delivered_at`, dẫn đến gửi lại. Vì vậy consumer cần idempotency theo event ID hoặc request key.

Outbox thường hỗ trợ **at-least-once delivery**, không phải một phép đảm bảo tuyệt đối mọi email, SMS hay API ngoài DB sẽ chỉ chạy đúng một lần.

### 18.2. Retry chỉ lặp lại những thay đổi transactional

Nếu một attempt lỗi `40001` trước commit, cả cập nhật nghiệp vụ lẫn marker và outbox trong DB cùng rollback. Attempt sau có thể xây dựng lại các bản ghi trong transaction mới mà không trực tiếp gửi tác dụng phụ bên ngoài mỗi lần thử.

## 19. Quan sát transaction đang chờ trong PostgreSQL

Khi một câu SQL chậm hoặc bị chặn, PostgreSQL có các công cụ chẩn đoán. Cần quyền phù hợp để xem đủ thông tin session khác.

### 19.1. pg_stat_activity

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, pid;
```

Những trường hữu ích:

- `pid`: backend ID.
- `state`: ví dụ `active`, `idle`, `idle in transaction`.
- `wait_event_type`/`wait_event`: loại hoạt động đang chờ.
- `xact_start`: transaction bắt đầu lúc nào.
- `query_start`: thời điểm bắt đầu câu SQL được ghi nhận.
- `query`: nội dung truy vấn (có thể bị giới hạn/ẩn theo quyền).

**`idle in transaction` đặc biệt đáng chú ý**: session có thể không chạy câu mới nhưng vẫn giữ khóa từ transaction đang mở.

### 19.2. pg_blocking_pids

```sql
SELECT
    a.pid AS waiting_pid,
    a.application_name,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.query AS waiting_query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.pid;
```

`pg_blocking_pids(pid)` giúp xác định các backend có thể đang chặn một backend khác tại thời điểm quan sát.

Nếu deadlock đã bị phát hiện và PostgreSQL đã hủy một transaction, vòng chờ có thể biến mất nhanh. Truy vấn monitoring không nhất thiết bắt được đúng khoảnh khắc lỗi.

### 19.3. pg_locks

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::REGCLASS AS locked_relation,
    transactionid
FROM pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, granted, locktype;
```

`pg_locks` có nhiều loại khóa, bao gồm những khóa không thể hiểu đơn giản như “một dòng SQL đang bị khóa”. Để xác định phiên nào đang chặn, `pg_blocking_pids` thường tiện hơn việc tự viết JOIN phức tạp trên view khóa.

### 19.4. Bộ đếm deadlock tích lũy

```sql
SELECT
    datname,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

`deadlocks` là bộ đếm tích lũy từ lần reset thống kê, **không phải số deadlock đang xảy ra**. Trong giám sát production, nên xem chênh lệch theo khoảng thời gian và tương quan với lưu lượng.

### 19.5. Cấu hình liên quan

PostgreSQL có các tham số như:

- `deadlock_timeout`: thời gian chờ trước khi kiểm tra deadlock.
- `log_lock_waits`: ghi log các trường hợp chờ khóa theo cấu hình.
- `lock_timeout`: giới hạn chờ lấy khóa.
- `statement_timeout`: giới hạn thời gian thực thi câu lệnh.

Không tự hạ timeout quá thấp hoặc bật log ồ ạt trong production; phải xét tải và chính sách vận hành.

## 20. EXPLAIN và chỉ mục không chứng minh hết race

Một câu SQL nhanh vẫn có thể gặp deadlock nếu hai transaction cùng lấy khóa theo thứ tự trái nhau. Một câu dùng index đúng vẫn có thể bị serialization failure do phụ thuộc đọc/ghi.

`EXPLAIN` giúp tìm:

- Quét bảng lớn không cần thiết.
- JOIN đắt.
- Điều kiện lọc không dùng index.
- Các thao tác kéo dài thời gian giữ tài nguyên.

Nhưng **EXPLAIN không thay việc kiểm thử hai session**, và không tự chứng minh tính đúng đắn về concurrency.

Chỉ mục trên các cột tìm khóa có thể giúp transaction nhanh hơn, giảm thời gian giữ khóa. Đồng thời, các index và ràng buộc cũng tham gia quá trình thực thi ghi; cần đánh giá trong toàn bộ workload.

## 21. Test đúng concurrency và ranh giới retry

### 21.1. Dùng hai connection thật

Chạy A rồi B trong một connection duy nhất **không phải** mô phỏng concurrency. Hãy dùng hai cửa sổ SQL với connection tách biệt, và nếu cần một connection thứ ba chỉ để monitoring.

### 21.2. Điều khiển thời điểm

Để tạo deadlock:

1. A khóa tài khoản 10.
2. B khóa tài khoản 20.
3. A xin khóa tài khoản 20.
4. B xin khóa tài khoản 10.

Để tạo write skew ở SERIALIZABLE:

1. A và B cùng bắt đầu transaction.
2. Cả hai đọc số người trực **trước bất kỳ cập nhật nào**.
3. Mỗi bên cập nhật một bác sĩ khác nhau.
4. Thử commit; quan sát `40001` theo lịch thực thi.

Nếu transaction thứ nhất đã commit trước khi transaction thứ hai đọc, bạn có thể **không tái hiện được** tình huống muốn khảo sát.

### 21.3. Kiểm tra dữ liệu sau thử nghiệm

```sql
SELECT account_id, balance
FROM lesson307_accounts
ORDER BY account_id;

SELECT
    shift_date,
    COUNT(*) FILTER (WHERE on_duty) AS on_duty_count
FROM lesson307_on_call
GROUP BY shift_date;
```

Không chỉ kiểm tra có exception hay không. Với bài ca trực, cần xác nhận bất biến `on_duty_count >= 1` khi ứng dụng áp dụng kiểm tra và retry đúng quy tắc.

### 21.4. Test trường hợp lỗi ở COMMIT

Một ứng dụng đúng phải phân biệt:

- Transaction chắc chắn rollback và client biết.
- Transaction chắc chắn commit và client biết.
- Client không biết trạng thái commit do lỗi kết nối.

Trường hợp thứ ba cần test idempotency và cơ chế đối chiếu trạng thái, không đơn giản “bắt exception rồi gửi request mới”.

## 22. Bảng quyết định kỹ thuật

| Tình huống | Ưu tiên xử lý |
|---|---|
| `40P01` | Rollback, kiểm tra đồ thị khóa và retry toàn transaction nếu phù hợp |
| `40001` | Rollback, đọc/tính lại toàn bộ trong transaction mới |
| `25P02` | Tìm lỗi gốc; không chạy tiếp như transaction còn hợp lệ |
| Chờ khóa lâu | Kiểm tra blocking PID, transaction giữ khóa, thời gian và query |
| `55P03` | Xem `NOWAIT`/`lock_timeout`; quyết định có nên chờ hoặc xử lý lại |
| `57014` | Xác định `statement_timeout`/cancel, không mặc định retry |
| `23505` | Xem ràng buộc unique, idempotency, UPSERT hoặc xung đột nghiệp vụ |
| Deadlock thường xuyên | Sửa thứ tự khóa, thu hẹp transaction, xem index và trigger |
| Serialization thường xuyên | Đánh giá phạm vi đọc/ghi, invariant, tải, isolation và retry |
| Mất kết nối lúc COMMIT | Không tự suy luận rollback; đối chiếu bằng request key |
| Gửi thông báo trong transaction | Tách side effect bằng cơ chế phù hợp, ví dụ outbox |
| Nhiều worker retry đồng loạt | Backoff + jitter + giới hạn attempt |
| Counter bị ghi đè | Cập nhật nguyên tử hoặc optimistic locking theo yêu cầu |
| Queue nhiều worker | Có thể dùng `FOR UPDATE SKIP LOCKED`, nhưng không cho phép bỏ qua dữ liệu quan trọng |
| Transaction nhiều bảng | Xác định một ranh giới commit và retry bao trọn invariant |

## 23. Các lỗi phổ biến

### Lỗi 1. Coi mọi lock wait là deadlock

Một transaction chỉ chờ người khác commit chưa chắc tạo vòng. Nhận diện `40P01` và xem đồ thị chặn.

### Lỗi 2. Coi `25P02` là nguyên nhân gốc

`25P02` thường chỉ là lỗi theo sau. Phải ghi nhận SQLSTATE của statement đầu tiên thất bại.

### Lỗi 3. Chạy lại câu UPDATE cuối sau `40001`

Quyết định ban đầu có thể dựa vào snapshot cũ. Cần retry toàn transaction và tính lại.

### Lỗi 4. Retry trong transaction chưa rollback

Một transaction đã aborted không được xem như còn hợp lệ. Phải kết thúc nó rồi mở transaction mới.

### Lỗi 5. Nghĩ SERIALIZABLE loại mọi lỗi

PostgreSQL có thể chủ động hủy transaction bằng `40001` để giữ tính tuần tự hóa. Ứng dụng phải có retry có giới hạn.

### Lỗi 6. Nghĩ REPEATABLE READ tự ngăn write skew

Snapshot nhất quán không tự bảo vệ mọi bất biến giữa nhiều dòng; cần isolation/khóa hoặc mô hình ràng buộc phù hợp.

### Lỗi 7. Dùng hai thứ tự khóa khác nhau

A khóa X→Y, B khóa Y→X là mẫu tạo deadlock. Chuẩn hóa thứ tự khóa.

### Lỗi 8. Giữ transaction khi gọi API chậm

Việc đó kéo dài thời gian giữ khóa và tăng contention. Thiết kế để transaction DB ngắn nhưng vẫn bao trọn bất biến.

### Lỗi 9. Sleep trước khi rollback

Backoff nên diễn ra **sau khi transaction lỗi đã kết thúc** để không giữ khóa/tài nguyên không cần thiết.

### Lỗi 10. Retry vô hạn mọi SQLException

Không phải `23505`, lỗi FK, CHECK hay lỗi quyền đều có thể sửa bằng retry. Phân loại mã lỗi, có giới hạn attempt.

### Lỗi 11. Không bắt exception ở COMMIT

Lỗi serialization có thể xuất hiện khi commit. Bao cả bước commit trong phạm vi xử lý attempt.

### Lỗi 12. Giả định mất kết nối nghĩa là transaction chưa commit

Outcome có thể chưa rõ. Dùng request key và cơ chế xác minh; không tự chuyển tiền hai lần.

### Lỗi 13. Đổi request key ở mỗi lần retry

Một yêu cầu logic cần giữ cùng mã để nhận biết việc xử lý trước đó đã hoàn thành hay chưa.

### Lỗi 14. Gửi email/SMS trước COMMIT trong transaction retry

DB có thể rollback nhưng email đã gửi. Cần xử lý side effect sau commit với idempotency thích hợp.

### Lỗi 15. Nghĩ outbox đảm bảo exactly-once tuyệt đối

Dispatcher có thể gửi lại sau crash. Consumer phải xử lý trùng theo event key.

### Lỗi 16. Tin `SKIP LOCKED` cho kết quả đầy đủ

`SKIP LOCKED` có thể bỏ qua dòng đang bị khóa. Không dùng để tính tổng/invariant cần đủ dữ liệu.

### Lỗi 17. Không kiểm thử hai connection

Hai câu chạy nối tiếp không tái hiện vòng chờ hoặc write skew. Cần nhiều connection và điều phối lịch thực thi.

### Lỗi 18. Chỉ xem lỗi mà không xem trạng thái nghiệp vụ cuối

Một transaction retry thành công về SQL vẫn có thể gửi SMS trùng hoặc cộng counter hai lần. Kiểm tra toàn bộ invariant và side effect.

## 24. Bài tập kèm lời giải

### Bài 1. Lock wait hay deadlock?

A giữ dòng 10; B đợi dòng 10; A không đợi tài nguyên của B.

**Đáp án:** đây là lock wait một chiều, chưa phải deadlock.

### Bài 2. Vòng khóa nào tạo deadlock?

A giữ dòng 10 và muốn dòng 20. B giữ dòng 20 và muốn dòng 10.

**Đáp án:** vòng `A → B → A`. PostgreSQL có thể báo `40P01` và hủy một transaction.

### Bài 3. Sau `40P01`, chạy lại câu UPDATE thứ hai?

**Đáp án:** không. Rollback transaction lỗi, mở transaction mới, đọc lại và thực hiện toàn bộ công việc nếu an toàn.

### Bài 4. `25P02` có chứng minh lỗi đầu là deadlock?

**Đáp án:** không. Nó chỉ cho biết transaction hiện đã lỗi. Cần xem SQLSTATE của lỗi đầu tiên.

### Bài 5. Giảm deadlock khi chuyển giữa tài khoản 10 và 20

**Đáp án:** mọi giao dịch lấy khóa theo thứ tự `10 → 20`, bất kể chiều chuyển tiền. Không loại trừ mọi deadlock ở các bảng/trigger khác.

### Bài 6. Hai bác sĩ cùng xin nghỉ dưới READ COMMITTED

A và B đều đọc số người trực là 2, rồi mỗi bên tắt một dòng khác nhau.

**Đáp án:** cả hai có thể commit và làm số người trực trở thành 0. Đây là write skew.

### Bài 7. Vì sao SERIALIZABLE có thể báo `40001`?

**Đáp án:** vì hai giao dịch cạnh tranh không thể đồng thời commit mà vẫn tương đương một thứ tự tuần tự hợp lệ với điều kiện đã đọc. PostgreSQL từ chối một transaction để bảo vệ isolation.

### Bài 8. B gặp `40001` sau khi A cho bác sĩ 1 nghỉ

**Câu hỏi:** B có được chạy lại ngay `UPDATE doctor_id=2 SET on_duty=FALSE` không?

**Đáp án:** không. B phải mở transaction mới và đếm lại; nếu chỉ còn bác sĩ 2 trực, phải từ chối cho người cuối nghỉ.

### Bài 9. `FOR UPDATE NOWAIT` không lấy được khóa

**Đáp án:** có thể báo `55P03`. Đó là từ chối chờ khóa, không chứng minh vòng deadlock.

### Bài 10. `statement_timeout` hủy câu SQL

**Đáp án:** thường `57014`, khác `40P01` và `40001`. Cần xem lý do timeout/cancel.

### Bài 11. Trong vòng retry, số dư đã đọc có được dùng lại không?

**Đáp án:** không. Phải đọc lại số dư và kiểm tra/tính lại quy tắc nghiệp vụ từ trạng thái mới.

### Bài 12. Có nên retry lỗi `23514` mãi không?

**Đáp án:** không. Đây là vi phạm `CHECK`; cần sửa dữ liệu hoặc quyết định nghiệp vụ. Retry không làm một giá trị âm tự hợp lệ.

### Bài 13. Lỗi `40001` xuất hiện ở COMMIT

**Đáp án:** phải nằm trong try/catch của toàn attempt; rollback theo cơ chế cần thiết và thử lại toàn transaction nếu an toàn.

### Bài 14. Vì sao backoff phải sau rollback?

**Đáp án:** để không giữ transaction/khóa/tài nguyên trong khi ngủ và tăng contention.

### Bài 15. Giao dịch đã commit nhưng phản hồi bị mất

**Đáp án:** không tự động chạy lại bằng request key mới. Cần xác minh kết quả theo idempotency key bền vững.

### Bài 16. Transaction retry gọi API gửi SMS trước COMMIT

Attempt 1 và 2 rollback, attempt 3 commit.

**Đáp án:** SMS có thể đã gửi ba lần. Tách tác dụng phụ qua outbox/idempotency phù hợp.

### Bài 17. Outbox có bảo đảm gửi đúng một lần không?

**Đáp án:** không tự động. Dispatcher có thể gửi lại sau crash; consumer phải xử lý trùng.

### Bài 18. Xem session chặn bằng SQL

```sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

**Đáp án:** mảng `blockers` giúp tìm PID có thể đang chặn mỗi session tại thời điểm quan sát. Mảng rỗng không chứng minh câu SQL không chậm do CPU/I/O.

### Bài 19. `pg_stat_database.deadlocks` bằng 5 nghĩa là có 5 deadlock ngay lúc này?

**Đáp án:** không. Đây là số đếm tích lũy từ lần reset thống kê, không phải số vòng chờ đang diễn ra.

### Bài 20. Khi nào cần retry toàn transaction?

| Tình huống | Kết luận |
|---|---|
| `40P01` | Rollback và retry toàn transaction nếu an toàn |
| `40001` | Rollback và retry toàn transaction nếu an toàn |
| `25P02` | Tìm lỗi gốc, rollback |
| `23505` | Xử lý xung đột khóa nghiệp vụ; không retry mù |
| Mất kết nối lúc COMMIT | Xác minh outcome/idempotency trước khi làm lại |

**Đáp án:** mỗi lỗi có ngữ nghĩa khác nhau. Chỉ đặt `40P01` và `40001` vào nhóm tự động retry transaction có điều kiện theo mẫu của bài.

### Bài 21. Vì sao retry chỉ UPDATE sau đọc tồn kho có thể sai?

Một transaction đọc tồn kho 10 và quyết định bán 8, rồi gặp `40001`. Giao dịch khác đã bán 5.

**Đáp án:** lần thử mới có thể chỉ còn 5 sản phẩm. Phải đọc lại tồn kho và ra quyết định mới, không dùng kết quả phép tính cũ.

### Bài 22. Sắp xếp thao tác giao dịch

**Yêu cầu:** xếp lại các bước `ROLLBACK`, `sleep`, `BEGIN`, đọc/ghi lại khi gặp `40P01`.

**Đáp án:** `ROLLBACK` transaction lỗi → `sleep` backoff (nếu còn attempt) → `BEGIN` transaction mới → đọc/kiểm tra/tính/ghi lại → `COMMIT`.

## 25. Bảng ghi nhớ nhanh

| Khái niệm | Ghi nhớ |
|---|---|
| Deadlock | Vòng chờ khóa, SQLSTATE `40P01` |
| Serialization failure | Không thể bảo đảm lịch giao dịch tuần tự, `40001` |
| Chờ khóa | Không nhất thiết deadlock |
| `25P02` | Transaction đã lỗi; xem nguyên nhân trước đó |
| `55P03` | Không lấy được khóa theo `NOWAIT`/`lock_timeout` |
| `57014` | Statement bị hủy |
| Retry toàn transaction | Đọc lại, tính lại, ghi lại, commit lại |
| Không retry trong transaction cũ | Rollback trước khi bắt đầu attempt mới |
| Backoff + jitter | Giảm retry đồng loạt, thực hiện sau khi nhả khóa |
| Thứ tự khóa | Nhất quán trên mọi đường ghi |
| Serializable | Có thể hủy transaction bằng `40001` |
| Repeatable Read | Không tự ngăn mọi write skew |
| Savepoint | Không thay thế retry toàn transaction khi quyết định đã lỗi thời |
| Lỗi ở COMMIT | Vẫn nằm trong phạm vi xử lý transaction |
| Connection loss tại COMMIT | Outcome có thể chưa rõ |
| Idempotency key | Giữ cùng key cho cùng request qua mọi attempt |
| Outbox | Ghi sự kiện cùng transaction, phát sau commit |
| `pg_stat_activity` | Quan sát trạng thái/điểm chờ của session |
| `pg_blocking_pids` | Xác định backend đang chặn |
| `pg_stat_database.deadlocks` | Đếm tích lũy, không phải deadlock hiện tại |
| Test concurrency | Hai connection thực và lịch thao tác có kiểm soát |

## 26. Kết luận

**Deadlock, lỗi tuần tự hóa và chờ khóa là những vấn đề khác nhau**, dù đều xuất hiện khi nhiều giao dịch cùng truy cập dữ liệu. Deadlock là vòng chờ tài nguyên và thường mang SQLSTATE `40P01`; serialization failure là cơ chế PostgreSQL bảo vệ ngữ nghĩa isolation và thường mang `40001`; chờ khóa hoặc timeout không tự chứng minh có deadlock.

Quy tắc cốt lõi:

> **Sau `40P01` hoặc `40001`, kết thúc transaction thất bại rồi thử lại toàn bộ logic giao dịch trong một transaction mới, có giới hạn và không lặp tác dụng phụ ngoài database.**

Một giải pháp đáng tin cần đồng thời xác định **invariant nghiệp vụ**, **thứ tự khóa**, **isolation**, **ranh giới commit/retry**, **idempotency**, **cách xử lý lỗi COMMIT không rõ kết quả**, và **công cụ quan sát trên DBMS**.

Mục tiêu không chỉ là để câu SQL “chạy được ở lần tiếp theo”, mà là bảo đảm dữ liệu cuối cùng **đúng** và yêu cầu nghiệp vụ **không bị thực hiện thừa hoặc thiếu**.

## Tài liệu tham khảo

- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): khóa dòng, deadlock và cách giảm vòng chờ.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): `READ COMMITTED`, `REPEATABLE READ`, SSI và `SERIALIZABLE`.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE `40P01`, `40001`, `25P02`, `55P03`, v.v.
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, `pg_locks`, `pg_blocking_pids` và `pg_stat_database`.
- [PostgreSQL — SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html): chọn mức cô lập giao dịch.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT` và xử lý xung đột unique.
- [Java SE — Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): `setTransactionIsolation`, `setAutoCommit`, `commit` và `rollback`.
- [Java SE — SQLException](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/SQLException.html): `getSQLState` để phân loại lỗi JDBC.

