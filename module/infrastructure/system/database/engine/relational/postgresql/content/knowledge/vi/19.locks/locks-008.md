# Advisory lock theo phiên hoặc theo giao dịch trong PostgreSQL

## 1. Vấn đề: một công việc không được chạy đồng thời hai lần

Hãy tưởng tượng ứng dụng có hai worker nhận yêu cầu tổng hợp hóa đơn cho cùng một khách hàng:

```text
Worker A                              Worker B
   |                                     |
   | Kiểm tra "chưa tổng hợp"             | Kiểm tra "chưa tổng hợp"
   |                                     |
   | Bắt đầu tổng hợp                    | Bắt đầu tổng hợp
   |                                     |
   v                                     v
Ghi kết quả A                         Ghi kết quả B
                 \                   /
                  Có thể xử lý trùng
```

Chỉ kiểm tra trạng thái bằng `SELECT` rồi quyết định làm việc có thể gây race condition. Một giải pháp là dùng **advisory lock** — khóa do ứng dụng chủ động yêu cầu PostgreSQL giữ trên một **khóa định danh logic**, ví dụ:

```text
(namespace = 700, job_id = 1001)
```

Worker lấy được khóa mới được thực hiện phần việc cần độc quyền. Worker khác cố lấy **cùng khóa** sẽ phải chờ hoặc nhận kết quả không lấy được, tùy hàm sử dụng.

PostgreSQL có hai họ advisory lock quan trọng:

- **Khóa theo phiên (*session-level*)**: tồn tại cho đến khi session giải phóng khóa hoặc session kết thúc; không tự nhả chỉ vì `COMMIT` hay `ROLLBACK`.
- **Khóa theo giao dịch (*transaction-level*)**: tự giải phóng khi transaction kết thúc bằng `COMMIT` hoặc `ROLLBACK`; không có thao tác mở khóa riêng trong lúc transaction vẫn đang diễn ra.

Điểm quan trọng là advisory lock **không tự biết ý nghĩa của tài khoản, job hay bảng**. PostgreSQL chỉ kiểm tra xung đột giữa các session cùng sử dụng một khóa logic; **ứng dụng phải tự thống nhất** khóa nào tương ứng với tài nguyên nào và kiểm tra nghiệp vụ đúng cách.

## 2. Mục tiêu bài học

Sau khi học, bạn có thể:

1. Giải thích advisory lock khác row lock và table lock ở đâu.
2. Chọn đúng **session-level** hoặc **transaction-level** cho từng workflow.
3. Sử dụng khóa **độc quyền** (*exclusive*) và **chia sẻ** (*shared*).
4. Phân biệt hàm **chờ** và hàm `pg_try_advisory_...` không chờ.
5. Sử dụng hai dạng khóa `bigint` và `(integer, integer)` đúng namespace.
6. Giải thích tác động của `COMMIT`, `ROLLBACK`, lỗi statement và mất kết nối.
7. Thiết kế workflow lấy khóa trước khi đọc/ghi trạng thái.
8. Hiểu rủi ro snapshot cũ, nhất là khi dùng `REPEATABLE READ`.
9. Dùng advisory lock an toàn trong Java/JDBC và connection pool.
10. Quan sát khóa đang giữ/đang chờ qua `pg_locks` và `pg_stat_activity`.
11. Giảm deadlock, chờ quá lâu, rò rỉ khóa và số lượng khóa quá lớn.
12. Biết những bài toán không nên dùng advisory lock, như thay thế `UNIQUE`, khóa hàng hay cơ chế điều phối phân tán có yêu cầu fencing.

## 3. Advisory lock là gì?

Trong PostgreSQL, các khóa thông thường có thể được lấy **tự động** vì một câu SQL tác động đến bảng/hàng:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;
```

Câu `UPDATE` phải phối hợp với các transaction cập nhật cùng hàng. Khóa hàng gắn với dữ liệu thực sự mà PostgreSQL quản lý.

Ngược lại, advisory lock là **khóa do ứng dụng tự chọn**:

```sql
SELECT pg_advisory_xact_lock(700, 1001);
```

PostgreSQL **không biết** `700` nghĩa là “quy trình xuất hóa đơn” hay `1001` là “job ID”. Nó chỉ biết có một khóa mang định danh đó và các yêu cầu khóa khác có tương thích với nó hay không.

### 3.1. So sánh trực quan

```text
Row lock
  UPDATE bảng A, hàng ID=1001
       |
       v
  PostgreSQL tự khóa hàng liên quan đến UPDATE

Advisory lock
  Ứng dụng chọn cặp key (700,1001)
       |
       v
  SELECT pg_advisory_xact_lock(700,1001)
       |
       v
  PostgreSQL phối hợp các yêu cầu advisory cùng key
```

### 3.2. Khóa mang tính hợp tác (*cooperative*)

Advisory lock chỉ có tác dụng khi **những thành phần cần phối hợp đều tuân thủ quy ước lấy khóa**.

Ví dụ Worker A đã giữ:

```sql
SELECT pg_advisory_xact_lock(700, 1001);
```

Worker B không lấy được cùng khóa độc quyền trong lúc khóa đang bị giữ. Nhưng Worker C vẫn có thể chạy:

```sql
UPDATE lock_lab.jobs
SET status = 'DONE'
WHERE job_id = 1001;
```

nếu Worker C **không dùng advisory lock** và không bị một loại khóa/ràng buộc khác ngăn cản.

Advisory lock không tự khóa hàng `jobs(1001)`. Đây là lý do không được coi advisory lock là **ràng buộc dữ liệu**.

### 3.3. Phạm vi PostgreSQL, không phải phạm vi toàn hệ thống

Advisory locks được quản lý bởi lock manager của PostgreSQL trong phạm vi **một database**. Cùng một khóa định danh ở hai database khác nhau không tự xung đột với nhau; hai PostgreSQL cluster độc lập cũng không chia sẻ lock manager.

Nếu một ứng dụng có nhiều database hoặc nhiều cluster, chỉ gọi `pg_advisory_lock` trên một node bất kỳ **không** tạo khóa toàn cục giữa tất cả các node.

## 4. Chuẩn bị dữ liệu thực hành

Chạy các ví dụ trong database **thử nghiệm**, không phải hệ thống production. Một số ví dụ cần **hai hoặc ba kết nối độc lập**.

### 4.1. Tạo bảng công việc

```sql
CREATE SCHEMA IF NOT EXISTS lock_lab;

CREATE TABLE lock_lab.jobs (
    job_id integer PRIMARY KEY,
    job_type text NOT NULL,
    status text NOT NULL
        CHECK (status IN (
            'PENDING', 'RUNNING', 'DONE', 'FAILED'
        )),
    attempt_count integer NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lock_lab.jobs
    (job_id, job_type, status)
VALUES
    (1001, 'invoice-report', 'PENDING'),
    (1002, 'invoice-report', 'PENDING'),
    (2001, 'daily-summary',  'PENDING');
```

Dữ liệu ban đầu:

| job_id | job_type | status | attempt_count |
| ---: | --- | --- | ---: |
| 1001 | invoice-report | PENDING | 0 |
| 1002 | invoice-report | PENDING | 0 |
| 2001 | daily-summary | PENDING | 0 |

### 4.2. Tạo bảng yêu cầu tổng hợp

```sql
CREATE TABLE lock_lab.report_requests (
    request_id bigint PRIMARY KEY,
    customer_id integer NOT NULL,
    report_month date NOT NULL,
    status text NOT NULL
        CHECK (status IN ('NEW', 'RUNNING', 'READY')),
    CONSTRAINT uq_customer_month
        UNIQUE (customer_id, report_month)
);

INSERT INTO lock_lab.report_requests (
    request_id, customer_id, report_month, status
) VALUES
    (1, 101, DATE '2026-10-01', 'NEW'),
    (2, 102, DATE '2026-10-01', 'NEW');
```

Bảng này sẽ giúp phân biệt **advisory lock** và **ràng buộc UNIQUE**: khóa ứng dụng giúp phối hợp công việc, còn UNIQUE mới bảo vệ chắc chắn việc không lưu hai dòng có cùng `(customer_id, report_month)` dù một chương trình bỏ qua quy ước khóa.

### 4.3. Hai session phải là hai backend khác nhau

Trên mỗi cửa sổ `psql`, chạy:

```sql
SELECT pg_backend_pid();
```

Nếu hai cửa sổ trả **cùng PID**, rất có thể công cụ đang dùng chung connection hoặc kết quả thuộc cùng backend. Muốn thử xung đột advisory lock, cần **hai session PostgreSQL thật sự độc lập**.

Đặt tên:

- **Session A**: kết nối nắm khóa.
- **Session B**: kết nối thử lấy khóa.
- **Session C**: tùy chọn khi thử khóa chia sẻ hoặc giám sát.

Các câu lệnh trong ví dụ phải được thực thi theo đúng thứ tự mô tả. Một `SELECT pg_advisory_lock(...)` không kèm cơ chế unlock có thể giữ session lock đến khi kết nối đóng.

## 5. Hai vòng đời khóa: session-level và transaction-level

Đây là khác biệt quan trọng nhất của bài.

| Đặc điểm | Khóa theo phiên | Khóa theo giao dịch |
| --- | --- | --- |
| Hàm tiêu biểu | `pg_advisory_lock` | `pg_advisory_xact_lock` |
| Thời điểm bắt đầu | Khi yêu cầu khóa lấy được | Khi yêu cầu khóa lấy được trong transaction |
| `COMMIT` | **Không tự nhả** | **Tự nhả** |
| `ROLLBACK` | **Không tự nhả** | **Tự nhả** |
| Mở khóa chủ động | `pg_advisory_unlock` | Không có hàm mở riêng |
| Kết thúc session/backend | Tự nhả | Tự nhả vì transaction cũng kết thúc |
| Dùng trong autocommit | Có thể giữ khóa sau statement | Thường nhả ngay cuối statement |
| Connection pool | Dễ rò rỉ nếu thiếu cleanup | Thường phù hợp hơn với transaction được quản lý |
| Phù hợp | Quy trình trải dài qua nhiều transaction trên cùng session cố định | Đoạn xử lý database nằm trong một transaction |

### 5.1. Session-level: vòng đời của physical connection

```text
Session A
   |
   +-- SELECT pg_advisory_lock(key)
   |            |
   |            +----- khóa đang được giữ ----------------+
   |                                                    |
   +-- BEGIN                                            |
   +-- UPDATE                                           |
   +-- ROLLBACK  -------- khóa VẪN còn ------------------+
   +-- BEGIN                                            |
   +-- COMMIT    -------- khóa VẪN còn ------------------+
   |                                                    |
   +-- SELECT pg_advisory_unlock(key) --- khóa được nhả -+
   |
   +-- Kết thúc kết nối
```

### 5.2. Transaction-level: vòng đời transaction

```text
Session A
   |
   +-- BEGIN
   |    |
   |    +-- SELECT pg_advisory_xact_lock(key)
   |    |            |
   |    |            +-- khóa đang được giữ --+
   |    +-- SELECT / UPDATE                   |
   |    +-- COMMIT hoặc ROLLBACK ------------+
   |
   +-- Transaction tiếp theo không còn sở hữu khóa đó
```

**Quy tắc chọn nhanh:** nếu mục tiêu là bảo vệ một chuỗi đọc/ghi **bên trong một transaction**, ưu tiên **transaction-level advisory lock**, trừ khi có lý do rõ ràng phải giữ khóa xuyên qua ranh giới transaction.

## 6. Danh sách các hàm advisory lock quan trọng

PostgreSQL có hai dạng định danh khóa:

1. **Một số nguyên 64 bit:** `key bigint`.
2. **Hai số nguyên 32 bit:** `key1 integer, key2 integer`.

Dưới đây dùng `(key1, key2)` để ví dụ.

### 6.1. Khóa độc quyền theo phiên

| Hàm | Kết quả | Hành vi |
| --- | --- | --- |
| `pg_advisory_lock(key1, key2)` | `void` | Chờ đến khi lấy được khóa độc quyền theo phiên |
| `pg_try_advisory_lock(key1, key2)` | `boolean` | Thử ngay: `true` nếu lấy được, `false` nếu đang xung đột |
| `pg_advisory_unlock(key1, key2)` | `boolean` | Nhả một lượt khóa tương ứng; `false` nếu phiên không giữ khóa cần nhả |

Dạng `bigint` tương ứng:

```sql
SELECT pg_advisory_lock(900001::bigint);
SELECT pg_try_advisory_lock(900001::bigint);
SELECT pg_advisory_unlock(900001::bigint);
```

### 6.2. Khóa chia sẻ theo phiên

| Hàm | Ý nghĩa |
| --- | --- |
| `pg_advisory_lock_shared(key1, key2)` | Chờ để lấy shared session lock |
| `pg_try_advisory_lock_shared(key1, key2)` | Thử shared session lock không chờ |
| `pg_advisory_unlock_shared(key1, key2)` | Nhả một lượt shared session lock |

Ví dụ:

```sql
SELECT pg_advisory_lock_shared(700, 1001);
SELECT pg_advisory_unlock_shared(700, 1001);
```

### 6.3. Khóa độc quyền theo giao dịch

| Hàm | Ý nghĩa |
| --- | --- |
| `pg_advisory_xact_lock(key1, key2)` | Chờ để lấy exclusive transaction lock |
| `pg_try_advisory_xact_lock(key1, key2)` | Thử lấy exclusive transaction lock không chờ |

Ví dụ:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);

-- Công việc database cần phối hợp.
SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

COMMIT;
```

Khóa được nhả sau `COMMIT`. **Không cần và cũng không có** `pg_advisory_xact_unlock`.

### 6.4. Khóa chia sẻ theo giao dịch

```sql
BEGIN;

SELECT pg_advisory_xact_lock_shared(700, 1001);

-- Đọc trạng thái trong đoạn được phối hợp.
SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

COMMIT;
```

Dạng không chờ:

```sql
SELECT pg_try_advisory_xact_lock_shared(700, 1001);
```

Dạng `bigint` cũng hỗ trợ các hàm shared và transaction-level tương ứng.

### 6.5. Không có mở khóa transaction-level riêng

Một trong những nhầm lẫn phổ biến:

```sql
-- Hàm này KHÔNG tồn tại:
SELECT pg_advisory_xact_unlock(700, 1001);
```

Nếu bạn cần nhả khóa **trước khi transaction kết thúc**, hãy xem lại thiết kế:

- Thu hẹp transaction.
- Dùng một transaction riêng cho phần cần khóa.
- Hoặc cân nhắc session-level với cleanup tường minh nếu vòng đời công việc thật sự phải dài hơn transaction.

Đừng cố giả lập “unlock transaction-level” bằng `pg_advisory_unlock`: hàm đó dành cho **session-level locks**, không giải phóng transaction-level lock.

## 7. Thiết kế định danh khóa: không chỉ là chọn một con số

Các advisory key **không liên quan tự động** đến tên bảng, khóa chính hay chuỗi văn bản nào. Ứng dụng phải tự quản lý namespace.

### 7.1. Dùng hai integer: namespace và resource ID

Một quy ước dễ hiểu:

| key1 | Loại tài nguyên | key2 |
| ---: | --- | --- |
| 700 | Job đồng bộ hóa | `job_id` |
| 701 | Báo cáo khách hàng | `customer_id` |
| 702 | Tác vụ bảo trì theo nhóm | `group_id` |
| 703 | Xử lý đối soát theo đơn | `order_id`, nếu vừa kiểu integer |

Ví dụ:

```sql
-- Khóa job 1001:
SELECT pg_advisory_xact_lock(700, 1001);

-- Khóa job 1002: khác tài nguyên, không xung đột với 1001.
SELECT pg_advisory_xact_lock(700, 1002);

-- Khóa báo cáo khách hàng 1001:
-- Khác namespace nên không xung đột với (700,1001).
SELECT pg_advisory_xact_lock(701, 1001);
```

Việc chia namespace giúp các đội/nghiệp vụ không vô tình cùng lấy một key cho hai tài nguyên khác nhau.

### 7.2. Hai dạng `bigint` và `(int,int)` thuộc hai không gian khóa khác nhau

Điểm dễ bỏ qua: một số `bigint` và cặp hai số nguyên **không dùng chung namespace advisory lock**.

Ví dụ:

```sql
SELECT pg_advisory_lock(700, 1001);
SELECT pg_advisory_lock(3006477108201::bigint);
```

Không nên tự cho rằng “số 64 bit được ghép từ 700 và 1001” chắc chắn xung đột với dạng hai khóa. PostgreSQL phân biệt hai cách định danh đó.

**Trong một nghiệp vụ, hãy thống nhất một dạng key.** Không trộn `pg_advisory_xact_lock(bigint)` và `pg_advisory_xact_lock(int,int)` rồi kỳ vọng chúng bảo vệ cùng tài nguyên.

### 7.3. Chú ý miền giá trị

- `integer` là kiểu signed 32-bit.
- `bigint` là kiểu signed 64-bit.

Nếu `job_id` thực tế là `bigint` vượt phạm vi `integer`, đừng ép về integer chỉ để nhét vào cặp khóa. Lựa chọn:

- Dùng một khóa `bigint` ổn định với quy hoạch namespace rõ ràng.
- Sử dụng cơ chế ánh xạ key có kiểm soát collision.
- Hoặc dùng hàng điều phối trong bảng nếu cần bảo đảm duy nhất theo khóa nghiệp vụ phức tạp.

### 7.4. Khóa theo chuỗi: cẩn thận với hàm hash

Một ứng dụng có thể có mã tài nguyên:

```text
invoice:customer-101:2026-10
```

PostgreSQL advisory lock không nhận trực tiếp chuỗi `text` làm key theo API chính. Có thể thấy gợi ý:

```sql
-- Minh họa ý tưởng, KHÔNG bảo đảm không collision:
SELECT pg_advisory_xact_lock(
    hashtext('invoice:customer-101:2026-10')
);
```

**Cảnh báo:** `hashtext` cho giá trị hash 32-bit, không phải một định danh duy nhất về mặt toán học. Hai chuỗi khác nhau **có thể va chạm hash**, dẫn tới khóa nhầm tài nguyên hoặc không đạt mô hình namespace mong muốn.

Không dùng hash 32-bit như một chứng minh “mỗi chuỗi có một lock key duy nhất”. Nếu collision không được chấp nhận, lưu ánh xạ từ khóa nghiệp vụ sang ID duy nhất trong database hoặc phối hợp bằng hàng dữ liệu/constraint.

### 7.5. Khóa không phải mật khẩu hay cơ chế phân quyền

Bất kỳ client có khả năng thực thi hàm advisory lock phù hợp cũng có thể yêu cầu key trùng với một nghiệp vụ khác. Một key “đoán khó” không tạo bảo mật.

Quyền đọc/ghi bảng phải tiếp tục được kiểm soát bằng role, GRANT, RLS và kiểm tra ứng dụng theo thiết kế. Advisory locks chỉ phục vụ **phối hợp tương tranh**.

## 8. Session-level lock: hai phiên quan sát việc chờ

Bài này dùng key `(800, 1)`, tránh trùng các ví dụ job.

### 8.1. Session A lấy exclusive session lock

**Session A:**

```sql
SELECT pg_backend_pid();

SELECT pg_advisory_lock(800, 1);
-- Lệnh trả về sau khi lấy được khóa.
```

`pg_advisory_lock` trả kiểu `void`; client thường hiển thị một ô trống. Không phải “không có kết quả nên thất bại”: hàm chỉ kết thúc khi đã lấy được khóa hoặc câu lệnh bị lỗi/cancel.

### 8.2. Session B thử không chờ

**Session B:**

```sql
SELECT pg_backend_pid();

SELECT pg_try_advisory_lock(800, 1) AS acquired;
```

Kết quả:

```text
acquired
--------
false
```

Session B không sở hữu khóa vì A đang giữ khóa độc quyền cùng key.

### 8.3. Session B dùng hàm chờ

Nếu B chạy:

```sql
SELECT pg_advisory_lock(800, 1);
```

nó có thể **chờ** đến khi A nhả khóa, hoặc kết thúc vì timeout/cancel/lỗi khác. Không chạy một câu `pg_advisory_lock` có khả năng chờ vô hạn mà không biết cách giải phóng từ session khác.

### 8.4. Session A giải phóng

**Session A:**

```sql
SELECT pg_advisory_unlock(800, 1) AS released;
```

Kết quả:

```text
released
--------
true
```

Khi A nhả khóa, B đang chờ có thể lấy được khóa. **Nếu B đã dùng hàm chờ và lấy được khóa, B cũng phải unlock**:

```sql
SELECT pg_advisory_unlock(800, 1);
```

### 8.5. Phiên khác không thể tùy ý unlock hộ

Một session chỉ có thể giải phóng **session advisory lock mà chính nó giữ**. Session B gọi:

```sql
SELECT pg_advisory_unlock(800, 1);
```

khi B chưa sở hữu khóa thì kết quả là `false`; không có tác dụng “ra lệnh cho Session A nhả khóa”.

Khi cần xử lý session treo trong production, việc terminate backend là hoạt động vận hành nhạy cảm và ảnh hưởng cả transaction/connection đó; không dùng như bước unlock mặc định.

## 9. Bẫy quan trọng: `ROLLBACK` không nhả session-level lock

Đây là bài thử nên tự thực hiện.

### 9.1. Session A lấy khóa trong transaction

```sql
BEGIN;

SELECT pg_advisory_lock(800, 2);

-- Thực hiện một thay đổi rồi quyết định hủy:
UPDATE lock_lab.jobs
SET attempt_count = attempt_count + 1
WHERE job_id = 1001;

ROLLBACK;
```

Lệnh `UPDATE` bị rollback. Nhưng **session advisory lock (800,2) vẫn còn**.

### 9.2. Session B thử key đó

```sql
SELECT pg_try_advisory_lock(800, 2) AS acquired;
```

Vẫn là `false`, miễn là Session A chưa nhả khóa và hai session thực sự khác backend.

### 9.3. Session A unlock sau rollback

```sql
SELECT pg_advisory_unlock(800, 2) AS released;
```

Sau khi A nhả, B có thể thử lại và nhận `true`:

```sql
SELECT pg_try_advisory_lock(800, 2) AS acquired;

-- Nếu true, B cũng phải nhả:
SELECT pg_advisory_unlock(800, 2);
```

### 9.4. Kể cả unlock trong transaction rồi rollback cũng không phục hồi session lock

Một đặc điểm đối xứng:

- Lấy session-level lock trong transaction rồi `ROLLBACK`: **khóa vẫn được giữ**.
- Nhả session-level lock trong transaction rồi `ROLLBACK`: **khóa vẫn đã được nhả**.

Session advisory lock có vòng đời **ngoài commit/rollback của transaction**.

**Đây là nguyên nhân gây lỗi nghiêm trọng khi ứng dụng chỉ gọi unlock ở nhánh thành công, còn nhánh exception làm rollback mà không cleanup.**

## 10. Khóa session-level có thể được lấy lặp trong cùng phiên

PostgreSQL cho phép một session **lấy lại khóa mà chính nó đang giữ**, ngay cả khi session khác đang chờ khóa đó.

Ví dụ:

```sql
-- Cùng Session A:
SELECT pg_advisory_lock(800, 3);
SELECT pg_advisory_lock(800, 3);
```

Lượt lấy thứ hai không tự bị chặn bởi khóa thứ nhất của chính session. Nhưng session-level advisory locks có cơ chế **đếm số lần giữ khóa**: phải nhả tương ứng với số lần đã lấy.

```sql
-- Nhả lần giữ thứ nhất:
SELECT pg_advisory_unlock(800, 3);

-- Khóa vẫn còn bị phiên A giữ vì đã lấy hai lần.
-- Nhả lần còn lại:
SELECT pg_advisory_unlock(800, 3);
```

### 10.1. Lời gọi reentrant không phải bằng chứng key đang trống

Nếu bạn thử khóa trong một connection đã sở hữu cùng key:

```sql
SELECT pg_try_advisory_lock(800, 3);
```

nó có thể trả `true` vì **chính connection đang có quyền giữ khóa**, không phải vì chẳng còn ai quan tâm đến tài nguyên.

Khi test cơ chế chống chạy trùng, **phải dùng hai physical backend** và không dùng cùng một connection lấy khóa hai lần rồi kết luận đã kiểm tra tính cạnh tranh.

### 10.2. Cẩn thận với thư viện gọi lồng nhau

Một hàm A lấy khóa, gọi hàm B cũng lấy cùng khóa, rồi B chỉ nhả một lượt. Nếu A tiếp tục và gặp exception mà không nhả lượt của mình, session có thể giữ khóa quá lâu.

Vì thế, session-level lock cần được quản lý theo nguyên tắc ownership rõ ràng:

```text
acquire -> try { work } finally { release }
```

Đừng phụ thuộc vào việc `COMMIT` hay `ROLLBACK` “dọn giúp”.

## 11. Transaction-level: tự động nhả khi COMMIT/ROLLBACK

### 11.1. Session A bắt đầu transaction và lấy khóa

```sql
BEGIN;

SELECT pg_advisory_xact_lock(800, 10);

SELECT job_id, status
FROM lock_lab.jobs
WHERE job_id = 1001;
```

Giữ Session A chưa commit.

### 11.2. Session B thử cùng khóa

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(800, 10) AS acquired;
-- false khi A vẫn đang giữ exclusive lock.

ROLLBACK;
```

### 11.3. Session A kết thúc transaction

```sql
COMMIT;
```

Hoặc dùng:

```sql
ROLLBACK;
```

Trong cả hai trường hợp, **transaction-level advisory lock được nhả** khi transaction kết thúc.

### 11.4. Session B thử trong transaction mới

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(800, 10) AS acquired;
-- true nếu không có chủ sở hữu xung đột khác.

COMMIT;
```

Ngay sau `COMMIT` của B, khóa transaction-level B vừa lấy cũng được nhả.

### 11.5. Không cần `pg_advisory_unlock`

Với khóa được lấy bởi:

```sql
pg_advisory_xact_lock(800, 10)
```

không gọi `pg_advisory_unlock(800, 10)` để giải phóng. Hàm unlock này là cho session-level ownership; nó không giải phóng khóa theo transaction.

## 12. Bẫy autocommit: transaction-level lock có thể mất tác dụng

Một lỗi phổ biến:

```sql
-- Công cụ đang ở autocommit = ON.
SELECT pg_advisory_xact_lock(700, 1001);

-- Sau statement trên, transaction của statement đã kết thúc.
-- Khóa xact-level đã được nhả.

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

UPDATE lock_lab.jobs
SET status = 'RUNNING'
WHERE job_id = 1001;
```

Mỗi statement có thể là một transaction độc lập. Khi `SELECT pg_advisory_xact_lock(...)` hoàn tất trong chế độ autocommit, PostgreSQL nhả transaction-level lock. Hai câu lệnh sau **không còn được bảo vệ**.

### 12.1. Đúng: mở một transaction tường minh

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

UPDATE lock_lab.jobs
SET status = 'RUNNING',
    attempt_count = attempt_count + 1,
    updated_at = now()
WHERE job_id = 1001
  AND status = 'PENDING';

COMMIT;
```

Khóa tồn tại từ lúc được lấy đến `COMMIT`.

### 12.2. Phải kiểm tra số hàng cập nhật

Câu `UPDATE` có điều kiện `status = 'PENDING'` có thể cập nhật **0 hàng** khi job đã được worker khác nhận. Lock lấy thành công **không chứng minh** job vẫn còn PENDING.

Nên dùng:

```sql
UPDATE lock_lab.jobs
SET status = 'RUNNING',
    attempt_count = attempt_count + 1,
    updated_at = now()
WHERE job_id = 1001
  AND status = 'PENDING'
RETURNING job_id, status, attempt_count;
```

Trong ứng dụng thực, chỉ worker nhận được **đúng một hàng** mới được coi là đã claim job thành công.

### 12.3. Không tách các bước sang nhiều connection

```text
Connection A: BEGIN + pg_advisory_xact_lock
Connection B: SELECT/UPDATE job
Connection A: COMMIT
```

Đây không phải một transaction chung. Khóa advisory có thể vẫn ngăn **worker cùng tuân thủ khóa đó**, nhưng những SELECT/UPDATE trên B thuộc transaction khác, không được hưởng atomicity/cùng snapshot và các thuộc tính transaction mà thiết kế kỳ vọng.

Với workflow cần nguyên tử, chạy các bước database liên quan trong **cùng connection và transaction**.

## 13. Khóa shared và exclusive xung đột như thế nào?

Có hai chế độ:

- **Exclusive lock**: tại một thời điểm, không cho một backend khác giữ khóa shared hoặc exclusive **không tương thích** trên cùng key.
- **Shared lock**: nhiều backend có thể cùng giữ shared lock trên cùng key, nhưng xung đột với yêu cầu exclusive từ backend khác.

Bảng tương thích trên **cùng advisory key**, xét các backend khác nhau:

| Khóa đang giữ | Yêu cầu shared | Yêu cầu exclusive |
| --- | --- | --- |
| Không có | Có | Có |
| Shared | Có | **Chờ / thử thất bại** |
| Exclusive | **Chờ / thử thất bại** | **Chờ / thử thất bại** |

Các quy tắc reentrant trong cùng session có thể cho kết quả khác khi chính session đã giữ khóa; bảng trên dành cho **các backend độc lập**.

### 13.1. Hai reader cùng dùng shared lock

**Session A:**

```sql
BEGIN;
SELECT pg_advisory_xact_lock_shared(810, 1);
```

**Session B:**

```sql
BEGIN;
SELECT pg_try_advisory_xact_lock_shared(810, 1)
    AS acquired;
-- true.
```

Cả A và B đang giữ shared advisory lock cho `(810,1)`.

### 13.2. Writer không lấy được exclusive khi reader còn giữ shared

**Session C:**

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(810, 1)
    AS acquired;
-- false.

ROLLBACK;
```

Khi A và B đều `COMMIT`/`ROLLBACK`, shared locks được nhả. Session C ở transaction mới có thể lấy exclusive lock.

### 13.3. Shared lock không tự ngăn SELECT/UPDATE SQL bình thường

Nếu Session C **không gọi hàm advisory** mà chạy:

```sql
UPDATE lock_lab.jobs
SET attempt_count = attempt_count + 1
WHERE job_id = 1001;
```

nó không bị shared advisory lock ngăn theo cách tự động. Khóa shared chỉ phối hợp giữa các thao tác **có sử dụng đúng advisory key và chế độ**.

### 13.4. Khi nào shared hữu ích?

Một ví dụ là “nhiều công việc đọc định kỳ được phép chạy đồng thời, nhưng tác vụ tái xây dựng dữ liệu chuẩn hóa phải độc quyền”.

- Reader lấy `pg_advisory_xact_lock_shared(namespace, key)`.
- Writer lấy `pg_advisory_xact_lock(namespace, key)`.
- **Mọi thành phần liên quan** phải cùng tuân thủ quy ước.

Trong nhiều bài toán chỉ đọc dữ liệu PostgreSQL, MVCC đã đủ để reader không chặn writer; **không nên tự thêm advisory shared lock** nếu không có yêu cầu điều phối nghiệp vụ ngoài khả năng MVCC.

## 14. Hàm chờ và hàm `try`: chọn theo độ trễ mong muốn

Hai hướng xử lý thường gặp:

### 14.1. Chờ đến khi lấy được khóa

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);

-- Chỉ chạy khi đã lấy được khóa.
SELECT status FROM lock_lab.jobs WHERE job_id = 1001;

COMMIT;
```

Nếu khóa đang bị giữ bởi transaction khác, câu gọi khóa **chờ**.

Phù hợp khi:

- Bắt buộc công việc phải được xử lý.
- Thời gian chờ có giới hạn phù hợp.
- Có chính sách timeout/cancel.
- Ứng dụng chịu được việc request chậm hơn.

### 14.2. Thử và bỏ qua nếu bận

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(700, 1001)
    AS acquired;

-- Nếu acquired = false:
--   ROLLBACK và báo BUSY/SKIPPED cho ứng dụng.
-- Nếu acquired = true:
--   tiếp tục đọc trạng thái, thực thi và COMMIT.
```

Hàm `pg_try_advisory_xact_lock` trả **boolean** ngay thay vì chờ khóa.

Phù hợp khi:

- Một cron job có thể bỏ lượt nếu phiên trước đang chạy.
- Scheduler có thể hoãn và thử lại sau.
- Worker muốn nhận việc khác thay vì chờ một tài nguyên duy nhất.
- API muốn phản hồi “đang xử lý” hơn là treo request.

### 14.3. `false` không phải SQL error

Nếu hàm try trả `false`:

- Transaction không bị chuyển sang trạng thái lỗi chỉ vì `false`.
- Ứng dụng phải **tự quyết định** rollback, commit hoặc chọn công việc khác.
- Không được chạy các bước độc quyền khi chưa thực sự có khóa.

### 14.4. `true` không chứng minh nghiệp vụ thành công

`true` chỉ báo **đã lấy được advisory lock**. Nó không nói rằng:

- Job còn ở trạng thái PENDING.
- Tài khoản/đơn hàng tồn tại.
- Có quyền thực hiện nghiệp vụ.
- Không có request trùng.
- Kết quả của các câu SQL sau chắc chắn commit.

Luôn phân biệt **acquire lock** với **validate state** và **commit business transition**.

## 15. Workflow đúng: lấy khóa, đọc lại, cập nhật, commit

Một mô hình nên dùng trong ứng dụng:

```text
BEGIN
   |
   v
Lấy advisory transaction lock cho đúng resource
   |
   +-- Không lấy được (try=false) -> ROLLBACK / defer
   |
   v
ĐỌC LẠI dữ liệu nghiệp vụ sau khi đã có khóa
   |
   +-- Trạng thái không hợp lệ -> ROLLBACK / no-op
   |
   v
UPDATE/INSERT có điều kiện và kiểm tra số hàng
   |
   v
COMMIT
   |
   v
Advisory xact lock được nhả tự động
```

### 15.1. Ví dụ xử lý job theo cách chờ

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

-- Bước 1: khóa theo namespace=700, job_id=1001.
SELECT pg_advisory_xact_lock(700, 1001);

-- Bước 2: kiểm tra trạng thái SAU KHI đã lấy khóa.
SELECT job_id, status, attempt_count
FROM lock_lab.jobs
WHERE job_id = 1001;

-- Bước 3: claim nếu còn PENDING.
UPDATE lock_lab.jobs
SET status = 'RUNNING',
    attempt_count = attempt_count + 1,
    updated_at = now()
WHERE job_id = 1001
  AND status = 'PENDING'
RETURNING job_id, status, attempt_count;

-- Trong ứng dụng: chỉ công nhận claim thành công
-- nếu UPDATE trả đúng một hàng.

COMMIT;
```

Nếu một worker đã claim job trước đó, worker tới sau vẫn có thể lấy khóa sau khi worker đầu commit, nhưng `UPDATE ... WHERE status = 'PENDING'` sẽ trả **0 hàng**. Đó là cách trạng thái dữ liệu bổ sung cho cơ chế khóa.

### 15.2. Vì sao phải đọc sau khi lấy khóa?

Sai thứ tự:

```text
Worker A: SELECT status='PENDING'
Worker B: SELECT status='PENDING'
Worker B: lấy khóa, đổi status='RUNNING', COMMIT
Worker A: lấy khóa, vẫn tin kết quả SELECT cũ
Worker A: thực hiện job trùng
```

Advisory lock không làm kết quả SELECT đã lấy từ trước tự cập nhật. Bất kỳ quyết định dựa trên dữ liệu **đọc trước khi lấy khóa** đều có thể đã cũ.

**Nên đọc lại và kiểm tra điều kiện sau acquire**.

### 15.3. Tại sao nên tách bước lấy khóa và bước SELECT dữ liệu?

Ở `READ COMMITTED`, mỗi statement thông thường chọn một snapshot phù hợp khi statement bắt đầu. Nếu bạn trộn:

```sql
SELECT
    pg_advisory_xact_lock(700, 1001),
    status
FROM lock_lab.jobs
WHERE job_id = 1001;
```

thì câu SELECT có thể chọn **snapshot trước khi chờ khóa**. Sau khi khóa được cấp, giá trị `status` từ chính statement đó không được bảo đảm là trạng thái mới nhất đã được một transaction trước commit trong lúc chờ.

Vì vậy, với logic “đợi worker trước rồi đọc trạng thái mới”, hãy dùng **hai SQL statements riêng**:

```sql
SELECT pg_advisory_xact_lock(700, 1001);

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;
```

Ở READ COMMITTED, statement SELECT thứ hai bắt đầu **sau khi khóa được cấp**, nên có cơ hội nhìn thấy commit đã xảy ra trước lúc nó bắt đầu.

### 15.4. Cẩn thận với REPEATABLE READ

Nếu transaction ở `REPEATABLE READ` đã thiết lập snapshot **trước khi chờ khóa**, việc lấy được advisory lock về sau **không làm mới snapshot** đó.

Thậm chí nếu câu `SELECT pg_advisory_xact_lock(...)` là truy vấn đầu tiên, bạn cũng không nên mặc định nó thiết lập snapshot **sau khi** thời gian chờ kết thúc. Hãy coi thời điểm snapshot được thiết lập là một phần của thiết kế transaction.

Với mẫu “chờ khóa rồi đọc trạng thái mới nhất đã commit”, `READ COMMITTED` và **SELECT dữ liệu sau acquire ở một statement riêng** thường là lựa chọn dễ lý giải. Nếu nghiệp vụ cần REPEATABLE READ/SERIALIZABLE, phải phân tích snapshot, khóa hàng và xử lý `40001` đúng cách.

## 16. Advisory lock và MVCC: hai cơ chế phục vụ hai mục đích

MVCC và advisory lock không phải hai cách gọi khác nhau cho cùng một tính năng.

| Cơ chế | Mục tiêu |
| --- | --- |
| MVCC snapshot | Quy định phiên bản hàng nào được thấy khi đọc |
| Row lock | Phối hợp cập nhật/khóa những hàng thực tế |
| Table lock | Phối hợp thao tác cấp bảng và xung đột liên quan |
| Advisory lock | Phối hợp các thao tác **do ứng dụng định nghĩa**, theo key logic |
| UNIQUE/FK/CHECK | Thực thi ràng buộc dữ liệu |
| SERIALIZABLE | Ngăn một số lịch giao dịch đồng thời không tương đương tuần tự |

### 16.1. Advisory lock không tăng isolation level

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT pg_advisory_xact_lock(700, 1001);
```

Transaction vẫn ở `READ COMMITTED`. Không có chuyện advisory lock tự nâng nó thành `SERIALIZABLE`.

### 16.2. Advisory lock không làm snapshot cũ biến mất

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

-- Transaction khác UPDATE status và COMMIT.

SELECT pg_advisory_xact_lock(700, 1001);

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;
```

Lần SELECT sau có thể vẫn thấy trạng thái cũ theo snapshot REPEATABLE READ. Khóa logic không cưỡng ép “refresh snapshot”.

### 16.3. Advisory lock không thay ràng buộc UNIQUE

```sql
CREATE TABLE lock_lab.once_per_customer (
    customer_id integer PRIMARY KEY,
    processed_at timestamptz NOT NULL DEFAULT now()
);
```

Nếu nghiệp vụ yêu cầu chỉ một dòng mỗi khách hàng, `PRIMARY KEY` bảo vệ điều đó ngay cả khi có một client **không dùng advisory lock** cố INSERT trùng.

Với các bất biến có thể thể hiện bằng constraint, ưu tiên constraint. Advisory lock có thể là cơ chế **bổ sung** để sắp thứ tự công việc, tránh tính toán đắt lặp, hoặc phối hợp phạm vi không khớp một hàng dữ liệu.

## 17. Session-level lock và connection pool

Trong ứng dụng Java, Node.js hoặc Go, một “request kết thúc” **không có nghĩa physical PostgreSQL session kết thúc**.

Connection pool thường giữ TCP connection/backend để tái sử dụng.

### 17.1. Tình huống rò rỉ khóa

```text
HTTP Request A
  |
  +-- Mượn connection #5
  +-- SELECT pg_advisory_lock(900,1)
  +-- Làm việc
  +-- Lỗi trước khi unlock
  +-- Trả connection #5 cho pool

HTTP Request B
  |
  +-- Mượn connection #5
  +-- Nhận backend vẫn giữ session lock (900,1)
  +-- Một lần pg_try_advisory_lock có thể trả true do reentrant
  +-- Hoặc gây chặn những backend khác
```

Nếu ứng dụng chỉ rollback transaction khi request A lỗi, session-level lock **vẫn tồn tại**. Đây là lý do advisory lock theo phiên cần cleanup chính xác hơn so với xact-level.

### 17.2. Mô hình an toàn hơn: transaction-level

```text
Mượn connection
    |
    v
BEGIN
    |
    v
pg_advisory_xact_lock(...)
    |
    v
Thực hiện các statement database
    |
    +-- thành công -> COMMIT -> khóa tự nhả
    |
    +-- lỗi -> ROLLBACK -> khóa tự nhả
    |
    v
Trả connection về pool
```

Vẫn phải đảm bảo connection thật sự hoàn tất transaction trước khi trả pool. Một transaction bị để mở cũng có thể giữ transaction-level lock rất lâu.

### 17.3. Session-level cần `finally`

Nếu buộc phải giữ khóa theo phiên, mã ứng dụng cần đặt unlock trong khối cleanup thực sự được thực hiện cả khi thành công lẫn exception.

Nhưng lưu ý:

- Unlock phải chạy trên **chính physical session** đã lấy khóa.
- Nếu connection mất, backend sẽ nhả khi session kết thúc trên server; nếu mạng đứt nhưng backend chưa phát hiện, khóa có thể còn trong một khoảng thời gian.
- Không thể mượn một connection **khác** rồi gọi unlock cho session ban đầu.
- Nếu transaction trên connection đang ở trạng thái aborted, cần xử lý rollback để có thể chạy các lệnh cleanup phù hợp.

Khi có connection pool phức tạp, giải pháp thiết kế ít lỗi hơn thường là **xact-level** hoặc một workflow có worker/transaction boundary rõ.

### 17.4. PgBouncer transaction pooling

Trong **transaction pooling**, các transaction của cùng client logic có thể được phục vụ bởi **những server backend khác nhau**.

Do đó session-level advisory lock là lựa chọn nguy hiểm nếu client kỳ vọng giữ cùng backend qua nhiều transaction:

```text
Client:
  TX 1 -> backend A -> pg_advisory_lock(...)
  TX 2 -> backend B -> pg_advisory_unlock(...)

Kết quả: B không giữ lock của A.
```

Đừng dùng session advisory lock xuyên ranh giới transaction khi kết nối có thể bị multiplex theo transaction.

Transaction-level advisory lock **có thể phù hợp hơn**, vì việc lấy khóa và những statement cần bảo vệ diễn ra trong một transaction được ghim vào backend theo cơ chế pool phù hợp. Tuy nhiên, hãy xác minh cấu hình pool thực tế và giữ toàn bộ workflow trong một transaction.

## 18. Java/JDBC: xử lý job bằng transaction-level advisory lock

Ví dụ ứng dụng Java muốn nhận job 1001 nếu chưa có worker khác xử lý. Sử dụng `pg_try_advisory_xact_lock` để tránh đợi vô hạn.

### 18.1. Một transaction, một physical connection

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class JobClaimService {
    private final DataSource dataSource;

    public JobClaimService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean claimJob(int jobId) throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            conn.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED
            );
            conn.setAutoCommit(false);

            try {
                // Namespace 700 dành riêng cho job.
                boolean acquired;
                try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT pg_try_advisory_xact_lock(?, ?)"
                )) {
                    ps.setInt(1, 700);
                    ps.setInt(2, jobId);

                    try (ResultSet rs = ps.executeQuery()) {
                        rs.next();
                        acquired = rs.getBoolean(1);
                    }
                }

                if (!acquired) {
                    conn.rollback();
                    return false;
                }

                // Đây là một statement SAU khi đã lấy khóa.
                // Kiểm tra và chuyển trạng thái theo điều kiện.
                int changed;
                try (PreparedStatement ps = conn.prepareStatement(
                    "UPDATE lock_lab.jobs " +
                    "SET status = 'RUNNING', " +
                    "    attempt_count = attempt_count + 1, " +
                    "    updated_at = now() " +
                    "WHERE job_id = ? AND status = 'PENDING'"
                )) {
                    ps.setInt(1, jobId);
                    changed = ps.executeUpdate();
                }

                if (changed != 1) {
                    conn.rollback();
                    return false;
                }

                conn.commit();
                return true;
            } catch (SQLException | RuntimeException error) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
```

Trong ví dụ:

- `setAutoCommit(false)` đảm bảo khóa xact-level tồn tại cho các bước tiếp theo.
- `pg_try_advisory_xact_lock` trả boolean; `false` không được coi là đã claim job.
- Câu `UPDATE` diễn ra **sau** câu lấy khóa, nên READ COMMITTED có snapshot statement mới.
- Điều kiện `status = 'PENDING'` bảo vệ khỏi việc claim lại sau khi worker trước đã commit.
- `commit` hoặc `rollback` giải phóng advisory xact lock.
- Nếu câu UPDATE ảnh hưởng 0 hàng, ứng dụng không trả về “claim thành công”.

### 18.2. Phân biệt claim job và thực thi job

Ví dụ trên chỉ **claim** một job trong một transaction ngắn. Sau `COMMIT`, advisory xact lock đã nhả, còn trạng thái `RUNNING` được lưu trong bảng.

Nó **không** giữ khóa trong suốt thời gian worker làm CPU/HTTP/email bên ngoài database.

Nếu yêu cầu là **không có hai worker thực thi đồng thời một job dài** sau khi claim, cần cơ chế ownership riêng như:

- Job state và worker ownership.
- Lease có thời gian hết hạn và cơ chế gia hạn.
- Fencing token hoặc version để chặn worker cũ ghi kết quả sau khi quyền sở hữu đã chuyển.
- Cơ chế retry/job recovery khi worker crash.
- Ràng buộc idempotency khi side effect có thể lặp.

Không nói rằng transaction-level advisory lock được giải phóng ở `COMMIT` sẽ tiếp tục bảo vệ công việc chạy **sau commit**.

### 18.3. Không mở transaction dài để chờ HTTP hoặc người dùng

Một phương án nguy hiểm là:

```text
BEGIN
pg_advisory_xact_lock
UPDATE state
Gọi HTTP API mất 60 giây
Đợi message queue mất 20 giây
COMMIT
```

Transaction giữ khóa/tài nguyên trong thời gian chờ bên ngoài. Điều này có thể làm tăng contention và ảnh hưởng VACUUM/connection pool.

Ưu tiên **transaction ngắn để claim/chuyển trạng thái**, rồi điều phối thực thi dài bằng trạng thái bền vững và cơ chế lease/fencing nếu cần.

## 19. Tác vụ dài: vì sao advisory lock không phải distributed lease?

Giả sử một worker:

1. Lấy session advisory lock.
2. Bắt đầu xử lý một API bên ngoài.
3. Mất kết nối PostgreSQL trong khi vẫn còn đang chạy API.
4. PostgreSQL phát hiện backend kết thúc và giải phóng khóa.
5. Worker khác lấy được cùng khóa và cũng chạy API.
6. Worker cũ vẫn chưa dừng hoạt động.

Cả hai worker có thể **đang làm việc đồng thời** dù cơ chế advisory lock từng đảm bảo không có hai backend giữ cùng khóa độc quyền.

Advisory lock **không phải một chứng minh về quyền sở hữu bên ngoài database sau khi session mất kết nối**.

### 19.1. Cần fencing token khi side effect phải được bảo vệ mạnh

Một mô hình phổ biến là cung cấp **fencing token tăng dần** cho mỗi lần nhận quyền làm việc. Hệ thống nhận side effect từ chối những thao tác mang token cũ hơn token mới nhất đã được chấp nhận.

Ví dụ:

```text
Worker A nhận token 41
Worker A bị mất quyền nhưng vẫn còn chạy

Worker B nhận token 42
Downstream ghi nhận token 42

Worker A gửi request token 41
Downstream từ chối vì token 41 đã cũ
```

Advisory lock bản thân **không tự sinh fencing token** và không bắt API bên ngoài tuân thủ token. Đây là lớp thiết kế bổ sung.

### 19.2. Với DB-only work, transaction-level thường đủ rõ

Khi toàn bộ nghiệp vụ nằm trong một transaction PostgreSQL, xact-level lock rất hữu ích vì quyền giữ khóa gắn với commit/rollback.

Nhưng nếu tác vụ kéo dài vượt transaction, hãy thiết kế **durable state/lease/idempotency** thay vì giữ transaction mở không thời hạn hoặc nhầm session lock với distributed lock có TTL.

## 20. Timeouts: không để worker chờ khóa vô hạn

### 20.1. `lock_timeout`

Trong PostgreSQL:

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';

SELECT pg_advisory_xact_lock(820, 1);

-- Chỉ tiếp tục nếu khóa được lấy thành công.
SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

COMMIT;
```

Nếu không lấy được khóa trong thời gian chờ phù hợp, PostgreSQL có thể báo lỗi do lock timeout. Transaction có thể rơi vào trạng thái aborted; cần `ROLLBACK`.

`SET LOCAL` chỉ áp dụng trong transaction hiện tại, giảm rủi ro thay đổi cấu hình timeout của những request khác khi connection được tái sử dụng.

### 20.2. `statement_timeout`

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';

SELECT pg_advisory_xact_lock(820, 1);

ROLLBACK;
```

`statement_timeout` giới hạn thời gian của **statement**, bao gồm thời gian chờ liên quan nếu statement chưa hoàn thành.

Khác biệt:

- `lock_timeout` tập trung vào **thời gian chờ lấy khóa**.
- `statement_timeout` giới hạn tổng thời gian statement.
- `idle_in_transaction_session_timeout` xử lý session **idle trong transaction**, không phải tất cả các session giữ session-level lock.

### 20.3. Dùng hàm try khi không muốn chờ

Nếu yêu cầu là “nếu có worker khác thì bỏ lượt”, thay vì dùng timeout ngắn, thường có thể rõ ràng hơn với:

```sql
SELECT pg_try_advisory_xact_lock(820, 1) AS acquired;
```

Nhưng hàm này phải nằm trong transaction bao quanh phần việc cần bảo vệ. Nếu autocommit bật, `true` có thể chỉ có ý nghĩa trong thời gian rất ngắn của statement.

### 20.4. Khi statement bị cancel

Nếu một session-level advisory lock **đã được lấy thành công trước đó**, việc cancel một statement khác hoặc rollback transaction **không tự nhả** khóa theo phiên.

Đối với xact-level lock, nó nhả khi transaction kết thúc; nếu statement lỗi khiến transaction bị aborted nhưng client cứ để transaction mở, cần chủ động rollback/kết thúc transaction để giải phóng tài nguyên.

## 21. Deadlock với advisory lock

Advisory lock có thể gây deadlock giống các loại khóa khác khi nhiều backend lấy nhiều tài nguyên theo thứ tự không nhất quán.

### 21.1. Ví dụ vòng chờ

**Session A:**

```sql
BEGIN;

SELECT pg_advisory_xact_lock(830, 1);
-- A giữ key (830,1).

SELECT pg_advisory_xact_lock(830, 2);
-- Có thể phải chờ B.
```

**Session B:**

```sql
BEGIN;

SELECT pg_advisory_xact_lock(830, 2);
-- B giữ key (830,2).

SELECT pg_advisory_xact_lock(830, 1);
-- Có thể phải chờ A.
```

Thực thi đúng thứ tự để tạo vòng chờ:

1. A lấy `(830,1)`.
2. B lấy `(830,2)`.
3. A yêu cầu `(830,2)` và chờ.
4. B yêu cầu `(830,1)` và chờ.

PostgreSQL có cơ chế deadlock detection và có thể hủy một transaction, với lỗi:

```text
SQLSTATE 40P01: deadlock_detected
```

**Chỉ thử deadlock trên database lab**, không làm trên production.

### 21.2. Phòng tránh bằng thứ tự khóa thống nhất

Nếu một workflow phải khóa job 1001 và 1002, mọi worker nên lấy theo cùng thứ tự, ví dụ tăng theo ID:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);
SELECT pg_advisory_xact_lock(700, 1002);

-- Công việc cần cả hai khóa.

COMMIT;
```

Worker khác cũng phải lấy 1001 trước 1002 để tránh tình huống “mỗi worker giữ một khóa và chờ khóa của bên kia”.

Đừng chỉ thống nhất thứ tự giữa các **advisory locks** mà quên thứ tự của các **row locks/table locks** khác trong cùng workflow. Nếu transaction A lấy advisory rồi row lock, B lấy row lock rồi advisory, vẫn có thể deadlock.

### 21.3. Reentrant và upgrade lock cũng cần cẩn trọng

Hai session cùng giữ shared lock rồi cùng muốn nâng lên exclusive có thể tạo chờ nhau, tùy mẫu khóa. Không dùng một trình tự “lấy shared rồi upgrade exclusive” khi chưa đánh giá khả năng deadlock và retry.

Nếu nghiệp vụ cần exclusive từ đầu, lấy exclusive ngay từ đầu thường đơn giản hơn.

### 21.4. Deadlock abort khác với session-level cleanup

Khi một transaction bị hủy vì deadlock:

- Transaction-level advisory locks được nhả khi transaction kết thúc.
- **Session-level advisory locks đã giữ có thể vẫn còn** sau transaction rollback.

Vì vậy, nếu dùng session-level ở một workflow có deadlock, application cleanup vẫn phải được thiết kế riêng.

## 22. Quan sát advisory locks qua `pg_locks`

PostgreSQL cung cấp view `pg_locks`, trong đó advisory locks xuất hiện với:

```sql
locktype = 'advisory'
```

### 22.1. Xem các advisory locks trong database

```sql
SELECT
    pid,
    database,
    locktype,
    mode,
    granted,
    classid,
    objid,
    objsubid,
    waitstart
FROM pg_locks
WHERE locktype = 'advisory'
ORDER BY pid NULLS LAST, granted, mode;
```

Ý nghĩa:

| Cột | Ý nghĩa |
| --- | --- |
| `pid` | PID backend giữ hoặc yêu cầu khóa, khi có |
| `database` | OID của database liên quan |
| `locktype` | `advisory` với khóa tư vấn |
| `mode` | Thường là `ExclusiveLock` hoặc `ShareLock` |
| `granted` | `true` đã được cấp, `false` đang chờ |
| `classid`, `objid`, `objsubid` | Các trường dùng mã hóa định danh advisory key |
| `waitstart` | Thời điểm bắt đầu chờ khi có, phụ thuộc phiên bản/trạng thái |

Không xem một dòng trong `pg_locks` như “một lần gọi hàm”. Session giữ cùng khóa nhiều lần có thể có bộ đếm ownership nội bộ; view không nhất thiết cho biết chính xác số lần reentrant acquire.

### 22.2. Lọc khóa của chính kết nối hiện tại

```sql
SELECT
    pid,
    mode,
    granted,
    classid,
    objid,
    objsubid
FROM pg_locks
WHERE locktype = 'advisory'
  AND pid = pg_backend_pid();
```

Hữu ích để quan sát session hiện đang nắm khóa nào.

### 22.3. Đọc dạng key từ thông tin `pg_locks`

Ở cách hiển thị advisory lock hiện hành, `classid` và `objid` chứa thông tin khóa, còn `objsubid` phân biệt dạng key:

- `objsubid = 1` thường biểu thị dạng khóa `bigint`.
- `objsubid = 2` thường biểu thị dạng hai số `integer`.

Các trường này thuộc **mô hình nội bộ của lock manager**; ứng dụng thông thường nên lưu key nghiệp vụ riêng thay vì dựa vào `pg_locks` làm bảng trạng thái chính.

### 22.4. Xác định transaction chờ khóa

```sql
SELECT
    l.pid,
    l.mode,
    l.granted,
    l.waitstart,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.locktype = 'advisory'
ORDER BY l.granted, l.waitstart NULLS LAST;
```

Nếu thấy `granted = false` và `wait_event_type = 'Lock'`, đó có thể là backend đang chờ advisory lock.

### 22.5. Ai đang chặn một backend?

```sql
SELECT
    a.pid AS waiting_pid,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event,
    a.state,
    a.query
FROM pg_stat_activity AS a
WHERE EXISTS (
    SELECT 1
    FROM pg_locks AS l
    WHERE l.pid = a.pid
      AND l.locktype = 'advisory'
      AND NOT l.granted
)
ORDER BY a.pid;
```

`pg_blocking_pids(pid)` giúp lấy PID các backend đang chặn tiến trình tương ứng theo cơ chế khóa PostgreSQL, không cần tự suy đoán chỉ từ một cặp dòng `pg_locks`.

### 22.6. Thận trọng với quyền và dữ liệu nhạy cảm

Không phải mọi role đều xem được đầy đủ `query` của session khác. Query có thể chứa thông tin nhạy cảm.

Chỉ chạy query giám sát trong phạm vi quyền được cấp; không chia sẻ nguyên văn câu lệnh có tham số bảo mật ra log hoặc ticket không được kiểm soát.

## 23. Giải phóng session-level locks khi cần

### 23.1. Unlock một key cụ thể

```sql
SELECT pg_advisory_unlock(800, 1) AS released;
```

`true` cho biết lời gọi đã giải phóng được một mức giữ khóa phù hợp; nếu session giữ nhiều lần, có thể cần nhiều lượt unlock.

Đối với shared session lock:

```sql
SELECT pg_advisory_unlock_shared(810, 1)
    AS released;
```

### 23.2. `pg_advisory_unlock_all()`

PostgreSQL cung cấp:

```sql
SELECT pg_advisory_unlock_all();
```

Hàm này giải phóng **các session-level advisory locks mà backend hiện tại giữ**. Nó **không** phải API nhả transaction-level advisory locks.

**Không gọi bừa `pg_advisory_unlock_all()` trong một connection dùng chung.** Nó có thể nhả cả những session locks mà thư viện hoặc tác vụ khác đang kỳ vọng giữ, gây lỗi phối hợp tương tranh.

### 23.3. Khi backend kết thúc

PostgreSQL tự giải phóng session advisory locks khi backend/session kết thúc thực sự. Nhưng một sự cố mạng có thể khiến client nghĩ connection đã mất trong khi backend chưa phát hiện ngay; không nên giả định thời gian giải phóng là tức thì ở mọi môi trường.

### 23.4. Không có “unlock theo key từ session khác”

Nếu Session A giữ một khóa, Session B không thể gọi `pg_advisory_unlock` để trực tiếp nhả ownership của A. Muốn khôi phục tình huống session treo cần công cụ vận hành phù hợp để xác định backend, request owner và hậu quả khi hủy kết nối.

Terminate backend có thể hủy công việc đang chạy, rollback transaction và nhả các khóa khác; đây là thao tác nhạy cảm, không phải cách giải phóng khóa hàng ngày.

## 24. SQL evaluation order: tránh lấy quá nhiều advisory locks ngoài ý muốn

Advisory locks được gọi qua các hàm SQL có **side effect lên lock manager**. Vì vậy, cần thận trọng khi dùng chúng trong SELECT với `LIMIT`, filter hoặc join.

### 24.1. Mẫu dễ gây hiểu nhầm

```sql
-- KHÔNG nên dựa vào câu này để đảm bảo chỉ lấy 5 khóa:
SELECT pg_advisory_lock(900, job_id)
FROM lock_lab.jobs
ORDER BY job_id
LIMIT 5;
```

Không nên giả định một biểu thức lấy khóa luôn được đánh giá **chỉ sau LIMIT** theo đúng thứ tự bạn hình dung. Tối ưu hóa truy vấn và thứ tự evaluation có thể gây việc lấy nhiều khóa hơn dự kiến trong những kiểu truy vấn phức tạp.

Đặc biệt với session-level lock, khóa lấy ngoài ý muốn có thể tồn tại sau khi SELECT hoàn tất và không được app theo dõi để unlock.

### 24.2. Chọn danh sách trước, rồi mới gọi hàm

Nếu thực sự cần lấy khóa cho một tập hữu hạn:

```sql
WITH selected_jobs AS MATERIALIZED (
    SELECT job_id
    FROM lock_lab.jobs
    WHERE status = 'PENDING'
    ORDER BY job_id
    LIMIT 5
)
SELECT pg_advisory_xact_lock(900, job_id)
FROM selected_jobs;
```

`MATERIALIZED` (trên PostgreSQL hỗ trợ cú pháp này) tạo ranh giới xử lý cho tập job được chọn, giúp thể hiện rõ ý định **chọn tối đa năm hàng trước khi lấy khóa**.

Nhưng:

- Đừng dùng session-level locks hàng loạt khi không có cách theo dõi và unlock từng key.
- Với nhiều key, phải có **thứ tự lấy khóa nhất quán** để giảm deadlock.
- Không mặc định một SELECT chứa nhiều hàm khóa có thứ tự đánh giá tuần tự được bảo đảm chỉ vì thêm ORDER BY ở cuối.
- Với workflow cần thứ tự chắc chắn, có thể chọn danh sách rồi lấy từng khóa theo thứ tự có kiểm soát ở tầng ứng dụng hoặc thủ tục thích hợp.

### 24.3. Khóa một resource cụ thể là mẫu dễ kiểm soát nhất

Khi có thể:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);

-- Các câu SQL nghiệp vụ của đúng job 1001.

COMMIT;
```

Mỗi transaction chỉ lấy một hoặc vài khóa có chủ đích sẽ dễ debug và ít tạo áp lực lock table hơn so với hàng chục nghìn khóa theo từng hàng.

## 25. Hiệu năng và giới hạn tài nguyên

Advisory locks là công cụ tiện dụng, nhưng không miễn phí.

### 25.1. Số lượng khóa có giới hạn

PostgreSQL dùng cấu trúc quản lý khóa trong shared memory. Khả năng chứa rất nhiều lock cùng lúc phụ thuộc cấu hình và tài nguyên, trong đó có `max_locks_per_transaction` và số backend/transaction mà hệ thống hỗ trợ.

**Không nên lấy một advisory lock riêng cho hàng triệu ID cùng lúc** chỉ vì khóa có vẻ nhẹ. Bạn có thể tạo áp lực lên shared lock table hoặc gặp lỗi tài nguyên.

### 25.2. Độ tranh chấp (*contention*)

Nếu hàng nghìn worker cùng yêu cầu:

```sql
SELECT pg_advisory_xact_lock(700, 1001);
```

tất cả cùng cạnh tranh một key, throughput của đoạn bảo vệ sẽ bị giới hạn theo thời gian giữ khóa.

Cách tối ưu thường là:

- Giữ critical section ngắn.
- Chỉ khóa phạm vi cần thiết.
- Phân chia job theo key hợp lý.
- Dùng `pg_try_advisory_xact_lock` để chuyển sang job khác khi bận.
- Tránh thực hiện I/O mạng bên ngoài trong lúc giữ khóa.
- Không giữ nhiều khóa không cần thiết.

### 25.3. Session lock không tự hết hạn

PostgreSQL không gắn một TTL nghiệp vụ tự động cho session advisory lock. Nếu session sống và vẫn giữ khóa, nó có thể giữ lâu bất thường.

Timeout trên một statement không phải “lease TTL” cho mọi session lock đang được giữ.

### 25.4. `EXPLAIN` không thay giám sát khóa

Một query có thể chạy nhanh khi không có tranh chấp nhưng rất chậm khi phải chờ advisory lock của worker khác. Để xác định nguyên nhân, theo dõi:

- `pg_locks.granted`.
- `pg_stat_activity.wait_event_type`/`wait_event`.
- `pg_blocking_pids`.
- Thời gian giữ transaction.
- Thời gian chờ, timeout, deadlock trong log/metrics.

Đánh giá hiệu năng lock cần bao gồm **tải đồng thời**, không chỉ thời gian một SELECT khi chạy một mình.

## 26. So sánh advisory lock với các công cụ khác

| Công cụ | Nên dùng khi | Lưu ý |
| --- | --- | --- |
| `pg_advisory_xact_lock` | Phối hợp một resource logic trong transaction | Tự nhả khi commit/rollback |
| `pg_advisory_lock` | Cần giữ khóa xuyên transaction trên một physical session cố định | Phải tự unlock, dễ rò rỉ trong pool |
| `SELECT ... FOR UPDATE` | Bảo vệ/chỉnh sửa những hàng hiện hữu cụ thể | Dùng row locks trực tiếp |
| `FOR UPDATE SKIP LOCKED` | Worker queue nhận từng hàng, bỏ qua hàng worker khác đang giữ | Không thích hợp nếu bỏ qua hàng sẽ làm sai nghiệp vụ |
| `UNIQUE` / `PRIMARY KEY` | Bảo đảm tính duy nhất của dữ liệu | Tác dụng ngay cả khi client không hợp tác advisory |
| `CHECK` / `FOREIGN KEY` | Thực thi bất biến trong phạm vi constraint | Không bị thay thế bởi advisory |
| `SERIALIZABLE` | Bảo vệ lịch giao dịch khỏi serialization anomalies | Có thể cần retry toàn transaction |
| Lease + fencing token | Công việc dài/side effect ngoài database hoặc nhiều hệ thống | Cần giao thức ownership ngoài advisory lock |
| Message queue có claim/ack | Phân phối công việc bất đồng bộ, retry và theo dõi | Phải xử lý idempotency/delivery semantics |

### 26.1. Tại sao không dùng `FOR UPDATE` trong mọi trường hợp?

Nếu tài nguyên cần khóa là một **tên nghiệp vụ trừu tượng** chưa có hàng trong bảng, advisory lock có thể thuận tiện hơn việc tạo row chỉ để làm mutex.

Ví dụ “chỉ một migration cho module X chạy tại một thời điểm” có thể dùng một advisory key cố định.

Ngược lại, nếu công việc là “claim một hàng `jobs` đã tồn tại”, `SELECT ... FOR UPDATE SKIP LOCKED` kết hợp transaction có thể biểu đạt trực tiếp hơn, đồng thời không cần quy hoạch namespace số nguyên.

### 26.2. Advisory lock không thay `UNIQUE`

Để chống hai request tạo cùng hóa đơn, có thể dùng advisory lock để giảm tranh chấp, nhưng vẫn nên có một ràng buộc dữ liệu:

```sql
CREATE TABLE lock_lab.invoice_batches (
    customer_id integer NOT NULL,
    report_month date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, report_month)
);
```

Nếu mọi worker quên lấy advisory lock, constraint vẫn chặn việc commit hai hàng trùng `(customer_id, report_month)`.

### 26.3. Advisory lock không tự ngăn write skew

Hai transaction có thể đọc một bất biến nhiều hàng rồi cập nhật các hàng khác nhau. Nếu chúng không dùng **cùng advisory key** cho bất biến đó, khóa theo từng hàng/từng ID khác nhau có thể không ngăn write skew.

Muốn dùng advisory lock bảo vệ một bất biến, hãy xác định **đúng resource logic chung**, đảm bảo mọi đường ghi cùng hợp tác, và duy trì logic snapshot/transaction đúng.

Trong nhiều trường hợp, `SERIALIZABLE` hoặc ràng buộc dữ liệu được thiết kế lại sẽ dễ chứng minh tính đúng hơn.

## 27. Pattern thực tế: tránh hai cron job chạy cùng đợt

Giả sử cron job chạy mỗi phút, nhưng một lần tổng hợp có thể mất 90 giây. Không muốn lần tiếp theo chạy đồng thời với lần trước.

### 27.1. Trường hợp công việc nằm hoàn toàn trong một transaction

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(1000, 1) AS acquired;

-- Nếu acquired=false: rollback và bỏ lượt.
-- Nếu true: tính toán và ghi dữ liệu trong transaction.

COMMIT;
```

Ví dụ ở trên chỉ là **khung điều khiển**; một client phải đọc giá trị `acquired` và quyết định có thực thi câu SQL tiếp theo hay không.

### 27.2. Trường hợp cron phải gọi API bên ngoài

Nếu cron cần:

1. Đọc database.
2. Gọi API trong vài phút.
3. Ghi kết quả.

Giữ một transaction PostgreSQL mở trong vài phút chỉ để giữ xact advisory lock là rủi ro. Cân nhắc:

- Claim một bản ghi công việc với UNIQUE/row lock trong transaction ngắn.
- Ghi owner/lease/version hoặc fencing token.
- Commit.
- Gọi API bên ngoài với idempotency key.
- Ghi kết quả theo quy tắc ownership kiểm tra lại.

Session-level advisory lock có thể tiện cho một tiến trình batch chỉ dùng **một session cố định** và không có yêu cầu fencing mạnh, nhưng phải chấp nhận việc kết nối mất sẽ nhả khóa trong khi worker có thể chưa dừng mọi tác động bên ngoài.

### 27.3. Không dùng khóa như nguồn sự thật duy nhất

Ngay cả khi scheduler bảo “job không đang chạy”, hãy lưu trạng thái/tiến độ trong bảng để có thể:

- Khôi phục sau crash.
- Hiển thị lịch sử.
- Retry có kiểm soát.
- Đối soát kết quả.
- Phân biệt “chưa làm”, “đang làm”, “đã xong” và “lỗi”.

Khóa chỉ diễn đạt **quyền phối hợp tạm thời**, không thay lịch sử bền vững của job.

## 28. Pattern thực tế: chỉ một tiến trình chạy migration/bảo trì

Một công cụ triển khai có thể dùng khóa logic cố định:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(1100, 1);

-- Kiểm tra phiên bản schema và thực hiện những thao tác
-- được PostgreSQL cho phép bên trong transaction block.

COMMIT;
```

Khi các thao tác triển khai đều transactional và nằm trong một transaction, xact-level lock là cách phối hợp gọn.

### 28.1. Không phải mọi DDL đều chạy được trong transaction block

Ví dụ `CREATE INDEX CONCURRENTLY` không được phép chạy trong transaction block tường minh.

Nếu quy trình bảo trì bắt buộc có những lệnh **ngoài transaction**, không thể đơn giản dùng một xact-level lock bao toàn bộ rồi giả định khóa tồn tại xuyên qua mọi lệnh.

Khi cân nhắc session-level lock cho một quy trình triển khai nhiều transaction, phải bảo đảm:

- Toàn bộ lệnh chạy trên đúng **physical PostgreSQL session**.
- Có `unlock` trong mọi đường kết thúc.
- Không dùng transaction pooling làm thay đổi backend.
- Có biện pháp xử lý mất kết nối, rollback từng thao tác và kiểm tra trạng thái trước khi retry.
- Không coi advisory lock là phương án recovery sau migration hỏng.

### 28.2. Không khóa mọi migration chỉ bằng một key nếu có nhiều database

Advisory locks là cục bộ theo database/cluster lock manager. Nếu công cụ deploy song song trên hai database khác nhau, cùng key không tạo exclusivity xuyên cả hai.

Nếu workflow có phạm vi nhiều database, cần cơ chế điều phối chung khác hoặc một thiết kế có nguồn quyền sở hữu duy nhất.

## 29. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `pg_try_advisory_lock` trả `true` dù nghĩ có worker khác | Cùng physical backend đã giữ khóa; reentrant | Test bằng hai backend PID khác nhau |
| Session B thử khóa nhưng luôn `false` sau khi A rollback | A đang giữ **session-level lock** | Gọi unlock trên A hoặc kết thúc backend |
| `pg_advisory_xact_lock` lấy xong nhưng job vẫn chạy trùng | Autocommit khiến khóa nhả sau statement | Mở transaction bao đúng toàn critical section |
| Hai key “cùng số” không xung đột | Một bên dùng `bigint`, bên kia dùng `(int,int)` | Thống nhất key signature |
| Không thấy xung đột giữa hai môi trường | Hai database/cluster khác nhau | Hiểu phạm vi lock manager |
| Worker lấy khóa rồi vẫn xử lý trạng thái cũ | SELECT dữ liệu trước acquire hoặc snapshot cũ | Đọc lại sau khóa; chú ý isolation |
| `REPEATABLE READ` sau khi chờ khóa vẫn thấy dữ liệu cũ | Snapshot đã cố định | Thiết kế READ COMMITTED hoặc retry/cơ chế khác |
| Exclusive lock không lấy được dù chỉ có readers | Readers giữ shared advisory cùng key | Dùng đúng compatibility rules |
| Chạy rollback nhưng session khóa vẫn còn | Session lock không phụ thuộc transaction | Cleanup trong finally |
| Một lần unlock mà khóa vẫn bị giữ | Session đã acquire cùng key nhiều lần | Unlock đúng số lượt hoặc quản lý owner |
| `pg_advisory_unlock` trả false | Backend hiện tại không giữ session lock đó | Kiểm tra PID và key |
| `pg_advisory_unlock_all` gây lỗi phối hợp khác | Nhả cả session locks thuộc logic khác trong backend | Chỉ unlock key thuộc trách nhiệm |
| Worker chờ mãi | Hàm blocking và lock holder lâu | Dùng try/timeout/giám sát blocking PIDs |
| `lock_timeout` gây transaction aborted | Lỗi chờ khóa làm transaction thất bại | ROLLBACK rồi xử lý theo chính sách |
| Xung đột nhiều key gây `40P01` | Thứ tự lấy khóa ngược nhau | Thống nhất thứ tự và retry toàn transaction |
| Connection trả pool nhưng lock vẫn còn | Session-level lock leaked | Cleanup đúng physical connection; cân nhắc xact-level |
| PgBouncer transaction pooling làm unlock thất bại | Backend thay đổi giữa hai transaction | Tránh session lock xuyên TX |
| Hai worker cùng gọi API sau khi A mất DB connection | Advisory lock không phải distributed fencing | Dùng lease/fencing/idempotency |
| Chỉ có advisory lock nhưng dữ liệu trùng | Client khác không hợp tác | Đặt UNIQUE/PK |
| Lấy hàng nghìn khóa làm shared memory tăng | Quá nhiều keys đồng thời | Giảm số khóa, dùng worker queue/row locks |
| Khóa trong SELECT với LIMIT không kiểm soát | Evaluation order không như mong đợi | Chọn tập trước, khóa có kiểm soát |
| `pg_locks` không cho biết số lần reentrant | View không phải counter ownership đầy đủ | Theo dõi acquire/unlock ở ứng dụng |
| Query đọc bình thường vẫn chạy dù advisory exclusive đang giữ | Advisory không tự chặn SELECT/UPDATE | Mọi luồng muốn phối hợp phải cùng dùng khóa |

## 30. Bài tập thực hành có đáp án

Dùng schema `lock_lab` và kết nối thử nghiệm. Với các bài có khóa theo phiên, nhớ unlock sau khi hoàn thành; với xact-level, kết thúc transaction để giải phóng.

### Bài 1. Khóa job 1001 theo transaction

Yêu cầu: dùng namespace 700, chỉ giữ khóa trong một transaction.

```sql
BEGIN;

SELECT pg_advisory_xact_lock(700, 1001);

SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

COMMIT;
```

**Đáp án:** khóa exclusive `(700,1001)` được nhả tự động ở `COMMIT`.

### Bài 2. Thử khóa không chờ

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(700, 1001)
    AS acquired;

ROLLBACK;
```

**Đáp án:** `true` nếu lấy được; `false` khi có backend khác giữ khóa xung đột. `ROLLBACK` nhả khóa nếu đã lấy.

### Bài 3. Session lock có tự nhả khi COMMIT không?

```sql
SELECT pg_advisory_lock(800, 11);

BEGIN;
SELECT 1;
COMMIT;
```

**Đáp án:** không. Session vẫn giữ `(800,11)`; phải gọi:

```sql
SELECT pg_advisory_unlock(800, 11);
```

hoặc kết thúc session.

### Bài 4. Session lock có tự nhả khi ROLLBACK không?

```sql
BEGIN;
SELECT pg_advisory_lock(800, 12);
ROLLBACK;
```

**Đáp án:** không. Gọi `pg_advisory_unlock(800,12)` trong chính session giữ khóa.

### Bài 5. Xact-level lock có hàm unlock riêng không?

**Đáp án:** không. Nó tự nhả khi transaction kết thúc. `pg_advisory_unlock` chỉ làm việc với session-level locks.

### Bài 6. Vì sao autocommit làm xact-level lock không bảo vệ câu lệnh kế tiếp?

**Đáp án:** khi statement `SELECT pg_advisory_xact_lock(...)` kết thúc với autocommit, transaction của statement cũng kết thúc và khóa nhả. Phải mở `BEGIN` trước rồi chạy tất cả câu SQL liên quan trong cùng transaction.

### Bài 7. Dạng một bigint và dạng hai integer có cùng key space không?

**Đáp án:** không. Hai chữ ký sử dụng hai không gian advisory key riêng. Phải thống nhất một dạng để các worker thực sự tranh chấp đúng resource.

### Bài 8. Session A exclusive, Session B try exclusive

**Session A:**

```sql
SELECT pg_advisory_lock(800, 21);
```

**Session B:**

```sql
SELECT pg_try_advisory_lock(800, 21) AS acquired;
```

**Đáp án:** B nhận `false`. Sau thử nghiệm, A unlock `(800,21)`.

### Bài 9. Vì sao `pg_try_advisory_lock` có thể trả true dù chính session đã giữ key?

**Đáp án:** advisory session locks hỗ trợ reacquire/reentrant ownership. Muốn kiểm tra xung đột giữa worker, phải dùng backend khác nhau.

### Bài 10. Hai lần acquire, một lần unlock

```sql
SELECT pg_advisory_lock(800, 22);
SELECT pg_advisory_lock(800, 22);
SELECT pg_advisory_unlock(800, 22);
```

**Đáp án:** khóa vẫn được giữ thêm một lượt. Cần:

```sql
SELECT pg_advisory_unlock(800, 22);
```

### Bài 11. Shared/shared có tương thích không?

**Đáp án:** có. Hai backend có thể đồng thời giữ shared advisory lock cùng key.

### Bài 12. Shared/exclusive có tương thích không?

**Đáp án:** không, nếu hai backend độc lập. Exclusive có thể phải chờ cho đến khi mọi shared ownership xung đột được nhả.

### Bài 13. `pg_try_advisory_xact_lock` trả false có làm transaction aborted không?

**Đáp án:** không. `false` là kết quả boolean thông thường; ứng dụng phải tự chọn rollback, bỏ lượt hoặc thử key khác.

### Bài 14. Đã lấy advisory lock thì có cần kiểm tra `status` nữa không?

**Đáp án:** có. Lock chỉ bảo vệ phối hợp tạm thời. Worker tới sau vẫn có thể lấy khóa sau khi worker trước commit, nhưng job đã ở `RUNNING` hoặc `DONE`.

### Bài 15. Vì sao phải SELECT trạng thái sau khi acquire?

**Đáp án:** vì dữ liệu đọc trước acquire có thể cũ nếu worker khác vừa commit trong thời gian chờ khóa. Ở READ COMMITTED nên để lệnh đọc là một statement riêng sau khi khóa được cấp.

### Bài 16. REPEATABLE READ có tự đổi snapshot khi lấy được advisory lock không?

**Đáp án:** không. Nếu snapshot đã được chọn, advisory lock không làm mới nó. Có thể vẫn thấy dữ liệu cũ và cần thiết kế isolation/retry phù hợp.

### Bài 17. Vì sao session lock khó dùng với connection pool?

**Đáp án:** request hoàn tất không đồng nghĩa backend kết thúc. Nếu không unlock trong mọi đường xử lý, physical connection quay về pool vẫn giữ khóa và ảnh hưởng request khác.

### Bài 18. Transaction pooling có giữ cùng PostgreSQL backend qua hai transaction không?

**Đáp án:** không được đảm bảo. Vì vậy session-level advisory lock lấy trong transaction này rồi unlock từ transaction khác có thể thất bại do backend thay đổi.

### Bài 19. Viết một query xem các advisory locks

```sql
SELECT
    pid,
    mode,
    granted,
    classid,
    objid,
    objsubid
FROM pg_locks
WHERE locktype = 'advisory';
```

**Đáp án:** mỗi dòng mô tả một trạng thái khóa được lock manager báo, với `granted` cho biết đã cấp hay đang chờ.

### Bài 20. Tìm PID đang chặn backend chờ advisory lock

```sql
SELECT
    a.pid,
    pg_blocking_pids(a.pid) AS blockers
FROM pg_stat_activity AS a
WHERE EXISTS (
    SELECT 1
    FROM pg_locks AS l
    WHERE l.pid = a.pid
      AND l.locktype = 'advisory'
      AND NOT l.granted
);
```

**Đáp án:** `blockers` trả danh sách PID đang chặn theo cơ chế PostgreSQL.

### Bài 21. Khóa job 1001 và 1002 theo thứ tự nào để hạn chế deadlock?

**Đáp án:** mọi worker lấy theo cùng thứ tự, ví dụ `(700,1001)` trước `(700,1002)`, rồi commit/rollback để nhả khóa.

### Bài 22. Làm gì khi gặp `40P01`?

**Đáp án:** rollback transaction thất bại, phân tích thứ tự lấy khóa và retry toàn transaction nếu nghiệp vụ an toàn, có giới hạn retry/backoff.

### Bài 23. Phân biệt `pg_advisory_unlock_all` với rollback

**Đáp án:** `pg_advisory_unlock_all()` nhả session-level locks do backend hiện tại giữ; `ROLLBACK` kết thúc transaction và tự nhả transaction-level locks, nhưng không tự nhả session-level advisory locks.

### Bài 24. Tại sao không dùng advisory lock thay `UNIQUE`?

**Đáp án:** advisory lock chỉ có tác dụng khi mọi writer cùng hợp tác lấy đúng key. Một client bỏ qua khóa vẫn có thể INSERT trùng nếu schema không có constraint. `UNIQUE`/`PRIMARY KEY` mới bảo đảm tính duy nhất ở database.

### Bài 25. Vì sao hash của chuỗi không chứng minh duy nhất?

**Đáp án:** hàm hash ánh xạ nhiều chuỗi có thể khác nhau vào miền giá trị hữu hạn; collision có thể xảy ra. Nếu không chấp nhận collision, cần ID/ánh xạ duy nhất hoặc thiết kế khóa khác.

### Bài 26. `lock_timeout` và `statement_timeout` khác nhau ở đâu?

**Đáp án:** lock_timeout giới hạn thời gian chờ khóa, statement_timeout giới hạn thời gian thực thi statement nói chung. Nếu lỗi timeout khiến transaction aborted, cần rollback.

### Bài 27. Vì sao advisory session lock không phải lease TTL?

**Đáp án:** nó không tự hết hạn sau một khoảng thời gian nghiệp vụ. Khóa giữ đến khi backend unlock hoặc session kết thúc; mất kết nối còn có thể khiến worker ngoài database vẫn làm việc.

### Bài 28. Khi nào cần fencing token?

**Đáp án:** khi worker có thể mất quyền sở hữu nhưng vẫn tiếp tục gây side effect ở hệ thống ngoài. Token tăng dần giúp bên nhận từ chối thao tác từ worker cũ nếu đã chuyển quyền sang worker mới.

### Bài 29. Vì sao không nên lấy advisory lock qua SELECT có LIMIT tùy tiện?

**Đáp án:** evaluation order của hàm có side effect so với filter/LIMIT có thể không giống giả định. Chọn tập tài nguyên trước, giới hạn rõ ràng, rồi lấy khóa có kiểm soát.

### Bài 30. Khi nào nên dùng `FOR UPDATE SKIP LOCKED` thay advisory lock?

**Đáp án:** khi worker queue được mô hình hóa bằng **các hàng công việc có sẵn** và muốn nhiều worker claim những hàng khác nhau mà không phải tự thiết kế namespace advisory. Phải hiểu cơ chế row locks và trạng thái job.

### Bài 31. Một transaction-level lock giữ tới khi nào nếu transaction đang idle?

**Đáp án:** đến khi transaction kết thúc, không phải chỉ đến lúc câu `pg_advisory_xact_lock` trả kết quả. Vì vậy phải tránh `idle in transaction` kéo dài.

### Bài 32. Worker claim xong COMMIT rồi xử lý API: khóa còn giữ không?

**Đáp án:** không. Xact-level advisory lock đã nhả tại commit. Muốn tránh hai worker thực thi cùng job sau commit, cần quản lý ownership/trạng thái/lease/idempotency riêng.

### Bài 33. Shared advisory lock có chặn SQL UPDATE không dùng advisory không?

**Đáp án:** không tự động. UPDATE có cơ chế row/table locks riêng, nhưng advisory shared lock chỉ phối hợp với những thao tác advisory khác dùng đúng key.

### Bài 34. Có nên gọi `pg_advisory_unlock_all` để “dọn phòng” trong pool không?

**Đáp án:** không tùy tiện. Nó có thể nhả khóa phiên của logic khác cùng dùng backend. Nên quản lý ownership cụ thể và chỉ unlock những key đã acquire.

### Bài 35. Đặt tên namespace và lựa chọn khóa cho quy trình xuất báo cáo

Một hệ thống có job xuất báo cáo theo `customer_id`. Muốn chỉ một báo cáo khách hàng được xử lý trong một transaction tại một thời điểm.

**Đáp án gợi ý:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT pg_advisory_xact_lock(701, 101);

SELECT request_id, status
FROM lock_lab.report_requests
WHERE customer_id = 101
  AND report_month = DATE '2026-10-01';

-- Kiểm tra trạng thái; UPDATE/INSERT có điều kiện
-- và xử lý theo UNIQUE(customer_id, report_month).

COMMIT;
```

Nếu nghiệp vụ cần phân biệt **khách hàng và tháng** để không khóa các tháng khác nhau của cùng khách, cặp `(701, customer_id)` là khóa **quá rộng**. Cần một ánh xạ duy nhất được thiết kế cho tổ hợp `(customer_id, report_month)`, hoặc dùng hàng điều phối và UNIQUE, tránh hash collision tùy tiện.

## 31. Checklist trước khi triển khai advisory lock

| Câu hỏi | Cách quyết định |
| --- | --- |
| Tài nguyên logic cần khóa là gì? | Định nghĩa key rõ, tránh khóa quá rộng/hẹp |
| Những client nào phải tuân thủ cùng key? | Bao gồm mọi đường xử lý có thể gây cạnh tranh |
| Có bao nhiêu database/cluster? | Advisory không phối hợp xuyên database độc lập |
| Dùng một bigint hay hai integer? | Thống nhất signature/namespace |
| Key có thể va chạm không? | Tránh hash thiếu kiểm soát |
| Khóa cần sống đến khi nào? | Chọn session-level hay transaction-level |
| Công việc hoàn toàn trong transaction? | Ưu tiên xact-level |
| Có connection pool? | Tránh rò rỉ session-level |
| Có PgBouncer transaction pooling? | Tránh session lock xuyên transaction |
| Có autocommit không? | Mở explicit transaction nếu dùng xact-level |
| Có dùng shared/exclusive đúng không? | Hiểu compatibility |
| Muốn chờ hay bỏ lượt? | Blocking vs `pg_try_advisory...` |
| Nếu chờ lâu thì sao? | Timeout, cancellation, metrics |
| Có đọc dữ liệu trước acquire không? | Đọc lại sau khi khóa được cấp |
| Transaction isolation là gì? | Snapshot READ COMMITTED vs REPEATABLE READ |
| Dữ liệu có được kiểm tra sau acquire? | Trạng thái, quyền, số hàng UPDATE |
| Có constraint bảo vệ tính đúng? | Không dùng advisory thay UNIQUE/FK/CHECK |
| Có bao nhiêu khóa trong một transaction? | Giảm số key, tránh cạn shared memory |
| Có thứ tự lấy nhiều khóa nhất quán? | Giảm deadlock |
| Có row locks khác cùng workflow? | Xem thứ tự khóa toàn bộ |
| Có side effect ngoài database? | Cân nhắc outbox, idempotency, fencing |
| Worker chết hoặc mất kết nối thì sao? | Thiết kế recovery của trạng thái công việc |
| Session-level có cleanup đúng không? | Unlock cùng backend trong finally |
| Có lời gọi nested/reentrant? | Theo dõi số lần acquire/unlock |
| Có query monitor khóa? | `pg_locks`, `pg_stat_activity`, blocking PIDs |
| Có test bằng hai backend PID khác nhau? | Tránh kết luận sai vì reentrancy |
| Có kiểm thử timeout/deadlock/rollback? | Kịch bản lỗi quan trọng |
| Có giới hạn thời gian transaction? | Không để idle trong transaction lâu |
| Có đánh giá điều phối ở nhiều cluster? | Nếu cần, chọn cơ chế ngoài advisory |
| Có định nghĩa kết quả khi try=false? | BUSY/SKIPPED/RETRY phù hợp |

## 32. Tổng kết

**Advisory lock** trong PostgreSQL là công cụ phối hợp tương tranh theo **định danh logic do ứng dụng chọn**. Nó rất hữu ích khi tài nguyên cần khóa không gắn trực tiếp với một hàng dữ liệu hoặc khi muốn nhiều worker thống nhất quyền thực hiện một công việc.

Những điểm phải nhớ:

1. **Session-level**: `pg_advisory_lock` / `pg_try_advisory_lock` tồn tại xuyên `COMMIT` và `ROLLBACK`, đến khi chính session unlock hoặc backend kết thúc.
2. **Transaction-level**: `pg_advisory_xact_lock` / `pg_try_advisory_xact_lock` tự giải phóng khi transaction kết thúc. Không có hàm xact unlock riêng.
3. **Shared và exclusive** có quy tắc tương thích: nhiều shared holders có thể cùng tồn tại, nhưng exclusive xung đột với holders khác trên cùng key.
4. **Hàm thường** chờ khóa; **hàm try** trả boolean ngay. `false` không phải ngoại lệ SQL, còn `true` không chứng minh trạng thái nghiệp vụ đã hợp lệ.
5. **Dạng `bigint` và dạng `(int,int)` có namespace khác nhau**; phải thống nhất signature và thiết kế key.
6. **Advisory lock mang tính hợp tác**: những client không dùng key đó vẫn có thể đọc/ghi bảng; UNIQUE/PK/FK/CHECK vẫn cần thiết.
7. **Lấy khóa rồi đọc lại trạng thái**. Ở READ COMMITTED, nên tách hàm acquire và câu SELECT nghiệp vụ thành **hai statements** để không dùng snapshot chọn trước khi chờ khóa.
8. **REPEATABLE READ không tự refresh snapshot khi khóa được cấp**. Khóa logic và tầm nhìn MVCC là hai cơ chế riêng.
9. **Autocommit có thể làm xact-level lock nhả ngay sau statement**, trước khi phần việc thực sự bắt đầu.
10. **Connection pool và PgBouncer transaction pooling** khiến session-level lock đặc biệt dễ sai nếu session ownership không được kiểm soát.
11. **Deadlock và timeout có thể xảy ra**; cần thống nhất thứ tự khóa, giám sát chờ và retry toàn transaction khi phù hợp.
12. **`pg_locks` và `pg_blocking_pids`** hỗ trợ quan sát holders/waiters; đừng nhầm metadata này với bảng trạng thái job.
13. **Advisory lock không phải distributed lease có fencing**. Nếu worker mất kết nối nhưng vẫn thực hiện side effect ngoài database, cần ownership/idempotency/fencing thích hợp.
14. **Giữ transaction và critical section ngắn**, tránh lấy quá nhiều khóa cùng lúc và không dùng session lock hàng loạt khi thiếu cleanup.

Mẫu cơ bản dễ dùng cho một đoạn công việc database:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

-- 1. Phối hợp trên key logic xác định.
SELECT pg_advisory_xact_lock(700, 1001);

-- 2. Đọc trạng thái trong một statement SAU khi có khóa.
SELECT status
FROM lock_lab.jobs
WHERE job_id = 1001;

-- 3. Cập nhật có điều kiện, kiểm tra số hàng.
UPDATE lock_lab.jobs
SET status = 'RUNNING',
    attempt_count = attempt_count + 1
WHERE job_id = 1001
  AND status = 'PENDING'
RETURNING job_id, status;

-- 4. Chỉ commit khi nghiệp vụ xác định kết quả hợp lệ.
COMMIT;
```

**Quy tắc cốt lõi:** trước khi gọi một hàm advisory lock, hãy trả lời ba câu hỏi: **khóa tài nguyên logic nào, giữ đến khi nào, và điều gì xảy ra nếu transaction hoặc kết nối thất bại?** Trả lời rõ ba câu hỏi này giúp lựa chọn đúng giữa **khóa theo phiên** và **khóa theo giao dịch** và tránh những lỗi đồng thời khó phát hiện.
