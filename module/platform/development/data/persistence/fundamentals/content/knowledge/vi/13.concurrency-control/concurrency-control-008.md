# Chờ khóa, timeout và hiện tượng deadlock

Trong một ứng dụng Java có lưu trữ dữ liệu bền vững, nhiều HTTP request, tác vụ nền và giao dịch có thể cùng đọc hoặc cập nhật một tập dữ liệu. Cơ sở dữ liệu phải điều phối các hoạt động này để bảo đảm tính đúng đắn: một transaction có thể **chờ khóa** (*lock wait*) do transaction khác đang giữ; chờ quá lâu có thể dẫn đến **timeout**; nếu các transaction chờ nhau thành vòng, chúng có thể tạo ra **deadlock** (*bế tắc*).

Ba hiện tượng đều có thể khiến một lời gọi repository chậm hoặc thất bại, nhưng nguyên nhân và cách khắc phục khác nhau. Lock wait có thể kết thúc bình thường khi bên giữ khóa commit. Timeout là giới hạn thời gian áp dụng tại một lớp cụ thể. Deadlock là vòng phụ thuộc khiến các transaction không thể tự tiến lên nếu không có hành động phá vòng.

Bài nằm trong chương **Kiểm soát đồng thời** của **DATA_PERSISTENCE_FUNDAMENTALS**, mô-đun giúp người học thiết kế ranh giới persistence cho Java, từ truy vấn và chỉ mục đến giao dịch, cô lập, lỗi kết nối và tối ưu hiệu năng. Ví dụ thực hành sử dụng PostgreSQL và có đối chiếu với MySQL/InnoDB, SQL Server và Oracle để làm rõ giới hạn theo hệ quản trị.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích cơ chế khóa, thời gian giữ khóa và lý do một giao dịch phải chờ.
2. Phân biệt lock wait thông thường, lock timeout, statement timeout, transaction timeout, timeout kết nối và deadlock.
3. Vẽ *wait-for graph* (đồ thị chờ) để nhận biết chu trình deadlock.
4. Tạo thí nghiệm hai phiên cho lock wait và deadlock, hiểu cách engine chọn transaction bị hủy.
5. Dùng thông tin phiên của PostgreSQL để xác định ai đang chờ ai và vì sao.
6. Viết thao tác Java/JDBC giữ transaction ngắn, khóa theo thứ tự thống nhất và retry ở đúng ranh giới.
7. Chọn biện pháp giảm tranh chấp phù hợp với yêu cầu nhất quán và tải thực tế.

## 2. Cơ chế khóa và nguyên nhân chờ

Khóa (*lock*) là cơ chế đồng bộ mà DBMS dùng để phối hợp truy cập tới một tài nguyên. Tài nguyên có thể là hàng, khóa chỉ mục, khoảng giá trị, trang, bảng, đối tượng lược đồ hoặc metadata. Không phải mọi DBMS có cùng các loại khóa hay bảng tương thích khóa.

Giả sử cơ sở dữ liệu có bảng tài khoản thử nghiệm:

~~~sql
CREATE TABLE accounts (
    id      BIGINT PRIMARY KEY,
    balance NUMERIC(14, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts (id, balance)
VALUES (1, 500.00), (2, 700.00);
~~~

**Phiên A:**

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

-- A chưa COMMIT/ROLLBACK, khóa ghi liên quan hàng 1 còn được giữ.
~~~

**Phiên B:**

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance + 100
WHERE id = 1;

-- B thường phải đợi khóa xung đột mà A đang giữ.
~~~

Nếu A `COMMIT` hoặc `ROLLBACK`, B có thể tiếp tục sau khi khóa được giải phóng. Bản thân việc B phải chờ **không phải lỗi**; đó là cơ chế tránh hai giao dịch sửa cùng dữ liệu một cách không kiểm soát.

### 2.1. Đọc thường không phải lúc nào cũng đợi ghi

Nhiều hệ quản trị hỗ trợ **MVCC** (*multiversion concurrency control*), duy trì các phiên bản dữ liệu để truy vấn đọc có thể quan sát dữ liệu đã commit phù hợp với mức cô lập.

Trong PostgreSQL ở `READ COMMITTED`, một câu `SELECT` thông thường có thể đọc phiên bản cũ đã commit trong khi A đang cập nhật hàng. Tuy nhiên, `UPDATE`, `DELETE` và `SELECT ... FOR UPDATE` trên hàng liên quan có thể cần chờ. Truy vấn đọc cũng có thể bị ảnh hưởng bởi khóa bảng hoặc DDL xung đột.

Ở engine dùng chiến lược khóa khác, kết quả có thể không giống. **Không có quy tắc phổ quát rằng SELECT luôn chặn hoặc luôn không chặn UPDATE.** Phải xét engine, mức cô lập, loại câu SQL và chế độ khóa.

### 2.2. Khóa tương thích và xung đột

DBMS định nghĩa nhiều chế độ khóa. Có những chế độ cùng tồn tại được, và những chế độ xung đột:

- Nhiều lần đọc tương thích có thể chạy đồng thời.
- Hai phép ghi trên cùng một hàng thường phải phối hợp qua khóa hoặc cơ chế kiểm soát đồng thời tương đương.
- Khóa ghi có thể chặn yêu cầu khóa ghi hoặc khóa đọc có tính bảo vệ.
- Thao tác DDL có thể yêu cầu khóa bảng/metadata và ảnh hưởng cả câu truy vấn thông thường.
- Ở một số hệ quản trị và điều kiện, khóa phạm vi hoặc khóa khoảng có thể chặn việc chèn hàng mới.

Ví dụ các tên như `ACCESS EXCLUSIVE` (PostgreSQL), *next-key lock* (InnoDB) và *key-range lock* (SQL Server) diễn đạt các cơ chế riêng, không nên coi chúng là một loại khóa giống hệt nhau.

### 2.3. Khóa có thể tồn tại sau khi câu UPDATE đã chạy xong

Trong transaction tường minh, các khóa ghi thường được giữ đến `COMMIT` hoặc `ROLLBACK`. Vì vậy đoạn mã có hình thức sau rất nguy hiểm về hiệu năng:

~~~text
BEGIN
  UPDATE số dư                         -> lấy khóa
  gọi HTTP tới dịch vụ khác            -> transaction vẫn mở
  xử lý dữ liệu lâu trong Java         -> khóa có thể vẫn bị giữ
  chờ phản hồi từ bên ngoài            -> các request khác tiếp tục chờ
COMMIT                                  -> kết thúc transaction
~~~

Nếu chương trình để transaction mở khi không có SQL đang thực thi, phiên có thể xuất hiện ở trạng thái **idle in transaction**. Tình trạng đó khiến một giao dịch gần như “không làm gì” vẫn có thể giữ khóa cần thiết và tạo hàng đợi phía sau.

## 3. Phân biệt lock wait, timeout và deadlock

### 3.1. Lock wait một chiều: có thể tiếp tục

~~~text
Transaction A: giữ khóa hàng X
Transaction B: muốn khóa X -> WAIT

Quan hệ: B -> A  (B chờ A)

A COMMIT / ROLLBACK
        |
        v
B có thể lấy khóa và tiếp tục.
~~~

Nếu A vẫn có thể chạy và kết thúc, đây chỉ là **chờ khóa thông thường**, dù thời gian chờ có thể rất dài. Phía sau B còn có thể có C, D, E cùng đợi, gây hiệu ứng hàng đợi (*lock convoy*).

### 3.2. Deadlock: chờ nhau thành vòng

~~~mermaid
flowchart LR
    A["Transaction A: giữ X, cần Y"]
    B["Transaction B: giữ Y, cần X"]
    A -->|"A đợi B"| B
    B -->|"B đợi A"| A
~~~

Đồ thị có hai cạnh `A → B` và `B → A`. A không thể hoàn tất vì cần khóa do B giữ, còn B không thể hoàn tất vì cần khóa do A giữ. Nếu các bên đều chỉ chờ nhau, chúng không thể tự phá chu trình.

Một DBMS có **deadlock detector** có thể chọn một transaction làm *victim*, hủy thao tác hoặc rollback theo quy tắc của engine để phần còn lại tiến lên. Chu trình có thể gồm nhiều hơn hai transaction, và không nhất thiết chỉ liên quan khóa hàng.

### 3.3. Timeout không chứng minh đã xảy ra deadlock

**Timeout** là kết quả vượt ngưỡng thời gian được cấu hình. Transaction B có thể timeout khi đợi A đang xử lý rất lâu mà **không tồn tại chu trình**. Ngược lại, detector có thể nhận ra deadlock và hủy một bên trước khi đạt bất kỳ lock timeout nào.

| Tình huống | Có chu trình chờ? | Kết cục |
|---|---|---|
| B đợi A, A vẫn có thể kết thúc | Không | A giải phóng khóa, B tiếp tục |
| B đợi A quá thời gian quy định | Không nhất thiết | B có thể nhận lock timeout |
| A đợi B, B đợi A | Có | Detector có thể hủy một victim |
| Query chạy quá lâu vì I/O/CPU | Không nhất thiết liên quan khóa | Có thể gặp statement/query timeout |
| Pool hết connection rảnh | Không phải đồ thị khóa DB | Ứng dụng gặp timeout lấy connection |

**Starvation** cũng là khái niệm khác: một yêu cầu liên tục không được phục vụ vì chính sách điều phối hoặc bị các yêu cầu khác vượt trước, dù không có chu trình chờ cố định.

## 4. Thí nghiệm chờ khóa trên PostgreSQL

Chạy bằng **hai kết nối SQL độc lập** trên môi trường thử nghiệm. Không dùng dữ liệu thật để chủ động tạo tình huống blocking/deadlock. Nếu tái sử dụng bảng `accounts` ở trên, bảo đảm không còn transaction thử nghiệm nào đang mở trước khi bắt đầu.

### 4.1. Quan sát một lần chờ rồi tiếp tục

**Phiên A:**

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance + 10
WHERE id = 1;

-- Giữ transaction, chưa COMMIT.
~~~

**Phiên B:**

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance + 20
WHERE id = 1;

-- Câu UPDATE có thể tạm dừng vì đợi A.
~~~

Sau đó chạy ở **phiên A**:

~~~sql
COMMIT;
~~~

B có thể tiếp tục và trả kết quả cập nhật. Kết thúc B bằng `COMMIT` hoặc `ROLLBACK` một cách tường minh. Nếu đo bằng nhiều phiên, có thể mở thêm phiên C để đọc `pg_stat_activity` và `pg_blocking_pids` như phần chẩn đoán.

### 4.2. Lock timeout giới hạn thời gian chờ lấy khóa

Trong PostgreSQL:

~~~sql
-- Phiên A đang giữ khóa hàng 1.

-- Phiên B:
BEGIN;
SET LOCAL lock_timeout = '2s';

UPDATE accounts
SET balance = balance + 20
WHERE id = 1;

-- Nếu khóa chưa được cấp trước timeout:
-- ERROR: canceling statement due to lock timeout
-- SQLSTATE: 55P03

ROLLBACK;
~~~

`SET LOCAL` áp dụng cho transaction hiện tại. `lock_timeout` giới hạn **thời gian chờ lấy khóa**, không giới hạn tổng thời gian thực thi một query. Sau lỗi từ câu SQL trong transaction PostgreSQL, transaction thường ở trạng thái **aborted** và cần `ROLLBACK`; không thể giả định transaction vẫn dùng được.

### 4.3. Deadlock hai phiên với thứ tự khóa đối nghịch

Khởi đầu từ bảng `accounts` có hàng `id = 1` và `id = 2`. Chạy theo đúng thứ tự xen kẽ.

**Phiên A khóa hàng 1:**

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance + 10
WHERE id = 1;
~~~

**Phiên B khóa hàng 2:**

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance + 20
WHERE id = 2;
~~~

**Phiên A thử cập nhật hàng 2, lệnh đang đợi B:**

~~~sql
UPDATE accounts
SET balance = balance + 10
WHERE id = 2;
~~~

**Khi A còn đang chờ, phiên B thử cập nhật hàng 1:**

~~~sql
UPDATE accounts
SET balance = balance + 20
WHERE id = 1;
~~~

~~~text
A: UPDATE id=1  -> giữ X
B: UPDATE id=2  -> giữ Y
A: UPDATE id=2  -> chờ B
B: UPDATE id=1  -> chờ A
                  -> A <-> B, chu trình deadlock
~~~

PostgreSQL có thể phát hiện và báo cho một phiên:

~~~text
ERROR: deadlock detected
SQLSTATE: 40P01
~~~

**Không biết trước A hay B sẽ là victim.** Khi một transaction bị hủy và rollback, transaction còn lại có thể tiếp tục. Sau thí nghiệm phải đóng hoặc rollback/commit đầy đủ hai transaction. Không nhầm việc một bên thành công sau khi bên kia thất bại với bảo đảm cả hai thao tác nghiệp vụ đều được thực hiện.

PostgreSQL có tham số `deadlock_timeout` ảnh hưởng thời điểm bắt đầu kiểm tra deadlock. Đây là tham số vận hành phục vụ detection, **không phải** giới hạn thời gian xử lý một request. Nếu `lock_timeout` rất ngắn, query có thể bị hủy trước khi detector báo deadlock.

## 5. Các loại timeout trong hệ thống Java

Trong báo cáo lỗi, từ “timeout” chưa đủ để kết luận nguyên nhân. Cần biết timeout xảy ra ở đâu:

| Loại timeout | Giới hạn điều gì? | Ví dụ | Ý nghĩa |
|---|---|---|---|
| **Connection acquisition** | Chờ lấy connection rảnh từ pool | Pool đầy | Query có thể chưa được gửi |
| **Connection establishment** | Thiết lập kết nối mạng/DB | DB không phản hồi | Không đồng nghĩa chờ khóa |
| **Lock wait** | Thời gian chờ được cấp một khóa | PostgreSQL `lock_timeout` | Query có thể nhanh nếu khóa được cấp |
| **Statement/query** | Thời gian thực thi một câu SQL | PostgreSQL `statement_timeout`, JDBC `setQueryTimeout` | Thường bao gồm cả chờ khóa |
| **Transaction** | Thời gian của toàn transaction theo chính sách engine/framework | Spring transaction timeout | Có thể được thực thi khác nhau tùy transaction manager |
| **Socket/read** | Thời gian đợi dữ liệu mạng | Driver socket timeout | Có thể không biết COMMIT đã xảy ra chưa |

Ví dụ PostgreSQL:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';

UPDATE accounts
SET balance = balance + 1
WHERE id = 1;

COMMIT;
~~~

Ở đây, nếu `UPDATE` phải chờ một khóa xung đột hơn hai giây, giới hạn khóa có thể phát huy. Nếu lấy khóa nhanh mà xử lý dữ liệu lâu, giới hạn câu lệnh có thể phát huy. Nếu `statement_timeout` quá ngắn so với `lock_timeout`, timeout toàn câu lệnh có thể đến trước, khiến giới hạn khóa riêng khó quan sát.

Các giới hạn trên **không tự tạo một SLA tuyệt đối cho HTTP request** vì request còn thời gian chờ pool, xác thực, mạng, xử lý Java và các thao tác khác.

### 5.1. Lỗi timeout có thể ảnh hưởng phạm vi rollback khác nhau

Trong PostgreSQL, lỗi từ một statement bên trong transaction thường làm transaction bị đánh dấu thất bại cho tới khi rollback (trừ các cơ chế savepoint phù hợp). Trong InnoDB, **row lock wait timeout** theo cấu hình phổ biến thường chỉ rollback **statement hiện tại**, trong khi deadlock thường rollback **toàn transaction**. Các chính sách này có thể thay đổi theo engine và cấu hình.

Nếu nghiệp vụ cần cả ba lệnh ghi cùng thành công, đừng bắt timeout của lệnh thứ ba rồi vô tình commit hai lệnh đầu. Tầng service phải quyết định kết quả **toàn bộ nghiệp vụ nguyên tử**, dựa trên trạng thái transaction thực tế của DBMS.

## 6. Chẩn đoán phiên chờ và blocker trong PostgreSQL

### 6.1. Truy vấn `pg_stat_activity`

Ví dụ quan sát các phiên của database hiện tại:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.xact_start,
    a.query_start,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.xact_start NULLS LAST, a.query_start NULLS LAST;
~~~

Đọc kết quả theo các câu hỏi:

- Có phiên `wait_event_type = 'Lock'` nào không? `wait_event` cụ thể là gì?
- `pg_blocking_pids(pid)` trả PID nào đang chặn?
- Blocker đang chạy SQL hay `idle in transaction`?
- Transaction đã mở bao lâu tính từ `xact_start`?
- `query` hiển thị SQL đang chạy hay câu gần nhất? Với phiên idle, đó thường là câu cuối đã chạy.
- Có mối liên hệ nào giữa `application_name`, request ID và endpoint đang lỗi?

Một kết quả `blocking_pids` rỗng không có nghĩa hệ thống không có sự cố; phiên có thể chờ tài nguyên khác, không còn ở trạng thái chờ khi đo, hoặc chịu những loại phụ thuộc cần công cụ khác để phân tích. Quyền truy cập cũng có thể giới hạn thông tin nhìn thấy.

### 6.2. Liệt kê cặp waiter–blocker

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.wait_event_type,
    waiting.wait_event,
    waiting.query AS waiting_query,
    blocking.pid AS blocking_pid,
    blocking.state AS blocking_state,
    blocking.xact_start AS blocking_xact_start,
    blocking.query AS blocking_last_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid))
    AS blocker(pid)
JOIN pg_stat_activity AS blocking
  ON blocking.pid = blocker.pid
WHERE waiting.datname = current_database();
~~~

Truy vấn này cung cấp một góc nhìn **tại thời điểm chạy**. Các phiên có thể commit, rollback hoặc thay đổi SQL ngay sau đó. Một vài blocker đặc biệt (chẳng hạn transaction đã prepare) có thể không hiển thị như kết nối thông thường qua phép join PID; cần thêm công cụ điều tra nếu thông tin chưa đầy đủ.

Có thể xem `pg_locks` để biết thêm tài nguyên và chế độ khóa, nhưng **không suy đoán blocker chỉ bằng cách tự join `pg_locks` đơn giản**: tương thích khóa, thứ tự trong hàng đợi và khóa cấp nội bộ khiến việc suy luận phức tạp. Với PostgreSQL, `pg_blocking_pids` là điểm xuất phát tốt để xác định ai đang chặn ai.

### 6.3. Tìm nguyên nhân gốc

~~~text
API cập nhật thanh toán chậm
       |
       v
PID 3810 đang WAIT theo loại Lock
       |
       v
pg_blocking_pids(3810) -> [3790]
       |
       v
PID 3790 idle in transaction, xact_start rất cũ
       |
       v
Tìm request/job giữ transaction mà chưa kết thúc
       |
       v
Sửa phạm vi transaction / đường code / truy vấn gây chờ
~~~

Tăng timeout có thể giúp tránh thất bại tạm thời nhưng **không giải quyết** khóa bị giữ vô lý. Việc buộc ngắt/kết thúc session đang giữ khóa là thao tác vận hành có thể rollback công việc đang chạy; cần đánh giá tác động và tuân theo quy trình xử lý sự cố.

### 6.4. Những chỉ số nên kết hợp

- Thời gian chờ khóa theo query và theo endpoint; số lần xảy ra `40P01`, `55P03`.
- Tuổi transaction, số phiên `idle in transaction` và độ dài truy vấn.
- p95/p99 độ trễ request, số connection đang dùng, thời gian chờ pool.
- Số lần retry, số lần rollback, số giao dịch thất bại liên tiếp.
- SQLSTATE, mã lỗi vendor, tên transaction, request/trace ID.
- Log deadlock của engine và kế hoạch truy vấn có liên quan, khi quyền truy cập cho phép.

Không ghi thừa tham số nhạy cảm hoặc toàn bộ thông tin khách hàng vào log điều tra.

## 7. Khác biệt quan trọng giữa các hệ quản trị

| DBMS | Chờ khóa/timeout thông dụng | Deadlock | Điều phải lưu ý |
|---|---|---|---|
| **PostgreSQL** | `lock_timeout`, `statement_timeout` | SQLSTATE `40P01` | Statement lỗi trong transaction thường làm transaction aborted cho đến rollback |
| **MySQL/InnoDB** | `innodb_lock_wait_timeout` cho nhiều trường hợp chờ row lock; `NOWAIT` và `SKIP LOCKED` ở phiên bản phù hợp | Thường lỗi `1213`, SQLSTATE `40001` | Deadlock thường rollback cả transaction; row lock wait timeout thường chỉ rollback statement theo mặc định |
| **SQL Server** | `SET LOCK_TIMEOUT` đặt giới hạn chờ khóa theo mili-giây | Deadlock victim thường lỗi `1205` | Trạng thái transaction sau lỗi phụ thuộc loại lỗi/cấu hình; cần xử lý rõ |
| **Oracle Database** | Một số lệnh khóa hỗ trợ `NOWAIT` và `WAIT n` | Deadlock thường `ORA-00060` | Rollback và trạng thái transaction phụ thuộc loại lỗi, không tự suy ra từ PostgreSQL |

Đây là các tín hiệu thường gặp, không phải danh sách đầy đủ mọi loại lỗi. Phải xác minh theo **phiên bản, driver, engine, mức cô lập và kiểu câu lệnh** thực tế.

PostgreSQL và InnoDB có MVCC cho nhiều dạng đọc. SQL Server có các mức cô lập khóa và các tùy chọn đọc phiên bản tùy cấu hình. Vì vậy chuyện một SELECT chặn writer hay không có thể khác nhau rõ rệt giữa các hệ thống.

## 8. Nguyên nhân và cách giảm deadlock

### 8.1. Chuẩn hóa thứ tự lấy khóa

Giả sử hai request chuyển tiền ngược chiều:

~~~text
Request R1: khóa account 1 -> khóa account 2
Request R2: khóa account 2 -> khóa account 1
~~~

Nếu các request đều khóa tài khoản theo **ID tăng dần**, chu trình do cặp khóa này có thể tránh được:

~~~text
Request R1: khóa account 1 -> khóa account 2
Request R2: khóa account 1 -> khóa account 2
~~~

PostgreSQL ví dụ:

~~~sql
BEGIN;

-- Các code path cùng tuân thủ thứ tự tăng dần:
SELECT id FROM accounts WHERE id = 1 FOR UPDATE;
SELECT id FROM accounts WHERE id = 2 FOR UPDATE;

-- Kiểm tra điều kiện và sửa dữ liệu trong cùng transaction.
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;

COMMIT;
~~~

Ví dụ này minh họa việc sắp thứ tự khóa, **không phải quy trình chuyển tiền đầy đủ**. Mọi luồng cập nhật liên quan cần thống nhất thứ tự, bao gồm thứ tự bảng khi phải cập nhật nhiều bảng. Thống nhất thứ tự cho một cặp hàng không chứng minh hệ thống không còn deadlock do khóa ngoại, trigger, metadata hay tài nguyên khác.

### 8.2. Giảm thời gian giữ transaction

Các nguyên nhân phổ biến gồm:

- Gọi HTTP, gửi email hoặc chờ bên thứ ba sau khi đã lấy khóa.
- Xử lý CPU lâu trong lúc transaction vẫn mở.
- Mở transaction rồi chờ người dùng xác nhận.
- Transaction có quá nhiều câu ghi hoặc quét lượng lớn dữ liệu không cần thiết.
- Bắt exception nhưng không rollback và đóng connection đúng lúc.

Ưu tiên chuẩn bị dữ liệu trước transaction, mở transaction sát phần nghiệp vụ cần nguyên tử, commit hoặc rollback sớm. Nếu phải công bố sự kiện sau commit, cân nhắc **transactional outbox** thay vì gọi hệ thống ngoài trong lúc giữ khóa.

### 8.3. Tối ưu điều kiện lọc và chỉ mục

Một câu `UPDATE` hoặc `SELECT ... FOR UPDATE` có điều kiện không chọn lọc có thể đọc, khóa hoặc tranh chấp nhiều tài nguyên hơn dự kiến. Ở InnoDB, loại chỉ mục và đường truy cập ảnh hưởng những record/gap cần khóa; ở PostgreSQL, phạm vi hàng được cập nhật và thời gian thực thi cũng ảnh hưởng cạnh tranh.

~~~sql
UPDATE jobs
SET state = 'RUNNING'
WHERE tenant_id = 10
  AND state = 'READY';
~~~

Nếu lệnh trên cập nhật hàng chục nghìn job, nó có thể giữ nhiều khóa. Cân nhắc chỉ mục phù hợp, xử lý theo lô nhỏ, hoặc thiết kế giao thức claim job; nhưng tách một thao tác thành nhiều transaction **thay đổi tính nguyên tử** nên phải được nghiệp vụ cho phép.

### 8.4. Dữ liệu nóng gây tranh chấp thật

Một hàng bộ đếm tổng, một số dư trung tâm hoặc một bản ghi trạng thái chung có thể bị hàng nghìn giao dịch ghi cùng lúc. Trong trường hợp đó, sắp thứ tự khóa không làm mất tranh chấp trên chính hàng nóng.

Có thể cân nhắc gộp cập nhật, phân vùng bộ đếm nếu cho phép tổng hợp trễ, dùng `UPDATE counter = counter + 1` nguyên tử, phân phối job hoặc thay đổi mô hình dữ liệu. Các cách này phải giữ đúng yêu cầu nghiệp vụ, kiểm toán và nhất quán.

## 9. NOWAIT và SKIP LOCKED

### 9.1. NOWAIT: từ chối chờ một khóa

PostgreSQL:

~~~sql
BEGIN;

SELECT id, balance
FROM accounts
WHERE id = 1
FOR UPDATE NOWAIT;

-- Nếu có khóa xung đột, câu lệnh trả lỗi ngay thay vì đợi lâu.
ROLLBACK;
~~~

`NOWAIT` phù hợp khi yêu cầu có thể nhận kết quả “đang bận, thử lại sau”. Không coi lỗi không lấy được khóa là bằng chứng hàng không tồn tại. Sau một lỗi SQL trong transaction PostgreSQL, vẫn phải xử lý trạng thái transaction đúng cách.

### 9.2. SKIP LOCKED: bỏ qua công việc đang được giữ khóa

Một worker xử lý hàng đợi có thể dùng:

~~~sql
BEGIN;

SELECT id
FROM jobs
WHERE state = 'READY'
ORDER BY created_at, id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Nếu lấy được hàng: UPDATE state = 'RUNNING' cho cùng id
-- ngay trong transaction này.

COMMIT;
~~~

Các hàng đang bị khóa xung đột có thể bị bỏ qua, cho phép worker khác lấy job kế tiếp. Cách này thích hợp cho mô hình **claim job** độc lập, nhưng cho góc nhìn **không đầy đủ** và không bảo đảm mọi job luôn được xử lý đúng thứ tự tuyệt đối. Không dùng `SKIP LOCKED` để kiểm tra ràng buộc tài chính, tổng hợp số liệu cần đầy đủ hay đưa ra kết luận từ những hàng đã bị bỏ qua.

Cần giao thức claim, lease/timeout và phục hồi khi worker chết; nếu chỉ SELECT rồi COMMIT mà không đánh dấu job, job có thể lại được worker khác lấy.

## 10. Java/JDBC: transaction ngắn, khóa nhất quán và retry

Ranh giới transaction thuộc về connection và transaction manager. Nếu một nghiệp vụ cần nhiều SQL là một khối nguyên tử, các lệnh phải nằm trong cùng transaction, kiểm soát `commit` và `rollback` phù hợp.

### 10.1. Mẫu JDBC khóa hai tài khoản theo thứ tự ID

Đoạn mã minh họa PostgreSQL, không phải dịch vụ tài chính hoàn chỉnh. Điều kiện nghiệp vụ được thực thi bằng câu `UPDATE` có điều kiện trong cùng transaction:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transferOnce(long fromId, long toId, BigDecimal amount)
            throws SQLException {
        if (fromId == toId || amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean oldAutoCommit = connection.getAutoCommit();
            try {
                connection.setAutoCommit(false);

                // PostgreSQL: giới hạn chờ khóa cho transaction này.
                try (Statement s = connection.createStatement()) {
                    s.execute("SET LOCAL lock_timeout = '2s'");
                }

                lockAccount(connection, Math.min(fromId, toId));
                lockAccount(connection, Math.max(fromId, toId));

                try (PreparedStatement debit = connection.prepareStatement(
                        "UPDATE accounts SET balance = balance - ? "
                      + "WHERE id = ? AND balance >= ?")) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, fromId);
                    debit.setBigDecimal(3, amount);
                    if (debit.executeUpdate() != 1) {
                        throw new IllegalStateException("Insufficient balance");
                    }
                }

                try (PreparedStatement credit = connection.prepareStatement(
                        "UPDATE accounts SET balance = balance + ? "
                      + "WHERE id = ?")) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, toId);
                    if (credit.executeUpdate() != 1) {
                        throw new IllegalStateException("Account not found");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            } finally {
                // Tùy driver/pool, cleanup có thể cần xử lý lỗi riêng
                // để không che khuất ngoại lệ gốc.
                connection.setAutoCommit(oldAutoCommit);
            }
        }
    }

    private static void lockAccount(Connection connection, long id)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT id FROM accounts WHERE id = ? FOR UPDATE")) {
            statement.setLong(1, id);
            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    throw new IllegalStateException("Account not found: " + id);
                }
            }
        }
    }
}
~~~

Đoạn này áp dụng quy tắc lấy khóa ID thấp trước, cập nhật dưới một transaction và rollback nếu bước bắt buộc thất bại. Trong sản phẩm thực, cần bổ sung idempotency, mã giao dịch duy nhất, kiểm toán, quy tắc đơn vị tiền tệ, phân quyền, transaction manager và xử lý khi không rõ COMMIT đã thành công hay chưa. Không dùng nguyên xi `SET LOCAL` ở DBMS khác.

Trong mã dùng connection pool, việc khôi phục `autoCommit`/thuộc tính session phải theo quy định của pool. Nếu cleanup thất bại, cần giữ được lỗi gốc; trường hợp kết nối lỗi không nên trả về pool như một kết nối lành mạnh.

### 10.2. Retry toàn bộ transaction

PostgreSQL có thể báo `40P01` (deadlock detected) hoặc `40001` (serialization failure). Nếu nghiệp vụ cho phép, có thể retry **toàn bộ transaction** trên một lần thực thi mới. Một cơ chế retry hợp lý:

~~~text
for attempt = 1 .. MAX_ATTEMPTS:
    try:
        BEGIN new transaction
        read fresh business state
        validate invariants
        acquire locks in defined order
        write changes
        COMMIT
        return success
    catch recognized transient concurrency failure:
        ROLLBACK if transaction is still active
        if last attempt: return meaningful failure
        bounded backoff + jitter
        retry all steps on a new transaction
~~~

Không retry riêng câu `UPDATE` cuối trong một transaction đã hỏng. Tránh retry không giới hạn vì có thể làm áp lực cạnh tranh nặng hơn.

`55P03` (lock not available hoặc lock timeout) không đương nhiên đáng retry trong mọi trường hợp: đối với giao diện có `NOWAIT` có thể nên trả “đang bận”; đối với job nền có thể cho retry ở vòng công việc sau.

### 10.3. Phân loại lỗi trước khi hành động

| PostgreSQL SQLSTATE | Ý nghĩa phổ biến | Hướng xử lý |
|---|---|---|
| `40P01` | Deadlock detected | Rollback, retry cả transaction khi phù hợp |
| `40001` | Serialization failure | Retry cả transaction theo chính sách có giới hạn |
| `55P03` | Không lấy được khóa hoặc lock timeout | Trả “đang bận” hoặc retry tùy SLA và nghiệp vụ |
| `57014` | Query canceled, có thể do statement timeout hoặc hủy từ phía ngoài | Xác định nguyên nhân thực trước khi retry |
| Mã dữ liệu/ràng buộc khác | Dữ liệu không hợp lệ hoặc vi phạm bất biến | Thường cần xử lý nghiệp vụ, không retry mù |

Trong JDBC có thể lấy SQLSTATE qua `SQLException.getSQLState()`; mã lỗi của MySQL/SQL Server/Oracle cần xử lý theo driver. Không bắt mọi `SQLException` rồi lặp lại: lỗi cú pháp, quyền, dữ liệu vi phạm và mất kết nối đều cần cách xử lý khác.

**Commit mơ hồ:** nếu kết nối đứt sau khi gửi `COMMIT` nhưng trước lúc nhận phản hồi, ứng dụng không thể luôn biết DB đã commit hay chưa. Retry mù một lệnh thanh toán có thể thực hiện hai lần. Cần operation ID ổn định, ràng buộc unique, idempotency và cơ chế đối soát.

### 10.4. Spring transaction và retry framework

Ví dụ:

~~~java
@Transactional(timeout = 5)
public void postTransfer(TransferCommand command) {
    // Các repository tham gia cùng một transaction do Spring quản lý.
    // Tránh network I/O lâu và tác dụng phụ ngoài DB khi giữ khóa.
}
~~~

`timeout = 5` được transaction manager diễn giải; nó không tự đồng nhất với `lock_timeout` của PostgreSQL hay timeout lấy connection từ pool. Nếu có retry framework, phải bảo đảm **mỗi lần retry được mở một transaction mới**. Retry bên trong transaction đã thất bại không phục hồi tính hợp lệ của transaction.

Với Spring proxy/AOP phổ biến, lời gọi nội bộ trong cùng bean có thể không đi qua proxy nên annotation không được áp dụng như dự định. Kiểm thử ranh giới transaction thực tế trước khi dựa vào cơ chế này để bảo vệ nghiệp vụ.

## 11. Quy trình xử lý sự cố trong thực tế

| Triệu chứng | Kiểm tra đầu tiên | Hướng khắc phục |
|---|---|---|
| API chậm, `wait_event_type = 'Lock'` | PID blocker, trạng thái và tuổi transaction | Sửa transaction dài và đường code giữ khóa |
| Nhiều `40P01` khi chuyển dữ liệu hai chiều | Thứ tự lock giữa các code path | Chuẩn hóa thứ tự lấy khóa |
| Lỗi `55P03` thường xuyên | Lock timeout có quá ngắn? Query đang đợi ai? | Giảm tranh chấp, cân nhắc timeout theo SLA |
| Job queue cùng tranh một hàng | Có thể lấy job khác hợp lệ không? | Xem `SKIP LOCKED` và giao thức lease |
| UPDATE ảnh hưởng nhiều hàng | Có chỉ mục và điều kiện chọn lọc không? | Giảm phạm vi khóa nếu nghiệp vụ cho phép |
| Pool timeout nhưng query chưa gửi | Pool đang giữ connection vì transaction dài? | Kiểm tra leak, thời gian giữ connection, tải |
| Retry sinh tác dụng phụ lặp | Có gửi email/thanh toán trong vòng retry không? | Dùng idempotency và outbox |
| Connection mất đúng lúc commit | Có biết đã commit hay chưa? | Đối soát bằng operation ID trước khi gửi lại |

Cách tiếp cận khi có sự cố:

1. Xác định request/job, câu SQL, transaction và loại timeout/lỗi.
2. Đo số phiên đang chờ, PID giữ khóa, tuổi transaction và thời gian chờ.
3. Xác định code path, thứ tự lấy khóa và điều kiện truy vấn gây tranh chấp.
4. Sửa nguyên nhân: thu ngắn transaction, nhất quán thứ tự, giảm hàng nóng hoặc tối ưu SQL/chỉ mục.
5. Kiểm tra bằng lịch chạy đồng thời có kiểm soát, không chỉ bằng một yêu cầu tuần tự.
6. Theo dõi p95/p99, deadlock count, lock wait time, pool usage và retry count sau thay đổi.

## 12. Câu hỏi và bài tập vận dụng

**Bài 1 — Deadlock hay chờ thông thường?** T1 giữ khóa hàng X rồi gọi HTTP 30 giây. T2 cần khóa X và bị chặn. Đây có chắc chắn là deadlock?

*Gợi ý:* Không. Có thể chỉ có cạnh `T2 → T1`, trong khi T1 không đợi khóa nào từ T2. Cần giải phóng transaction sớm và tránh gọi HTTP trong lúc giữ khóa.

**Bài 2 — Chu trình hai hàng.** T1 khóa X rồi đợi Y; T2 khóa Y rồi đợi X. Có tác dụng gì khi nâng `lock_timeout` lên một phút?

*Gợi ý:* Không loại bỏ chu trình; detector vẫn có thể chọn victim. Chuẩn hóa thứ tự khóa X/Y và vẫn chuẩn bị retry khi có xung đột.

**Bài 3 — Lỗi InnoDB.** Hai SQL đầu trong transaction thành công, SQL thứ ba gặp row lock wait timeout. Có thể chắc chắn hai SQL trước đã rollback?

*Gợi ý:* Không. Theo cơ chế phổ biến của InnoDB, lock wait timeout chỉ rollback statement hiện tại. Nghiệp vụ nguyên tử cần rollback toàn transaction khi bước bắt buộc thất bại.

**Bài 4 — Pool timeout.** API bị timeout khi chờ lấy connection, trong khi SQL của API chưa chạy. `lock_timeout` ở DB có phải nguyên nhân trực tiếp của lỗi đó?

*Gợi ý:* Không. Đây là timeout ở pool. Các connection khác có thể bị giữ vì lock wait, nhưng phải xác định đúng điểm phát sinh lỗi và điều tra nguyên nhân gián tiếp.

**Bài 5 — Đọc blocker.** PostgreSQL cho thấy PID 123 đang chờ Lock, `pg_blocking_pids(123)` trả `[456]`, PID 456 `idle in transaction` đã hai phút. Bước tiếp theo là gì?

*Gợi ý:* Xác định request/job của PID 456, câu lệnh đã lấy khóa và vì sao transaction chưa kết thúc. Sửa đường code giữ transaction lâu; tăng timeout chỉ che triệu chứng.

**Bài 6 — SKIP LOCKED.** Một worker bỏ qua job cũ nhất đang bị khóa và lấy job tiếp theo. Có thể dùng cách này để tính tổng các giao dịch tài chính tại một thời điểm không?

*Gợi ý:* Không. `SKIP LOCKED` có thể bỏ qua hàng và tạo góc nhìn thiếu dữ liệu; nó phù hợp hơn cho phân phối công việc độc lập.

**Bài 7 — Retry và tác dụng phụ.** T1 gửi email xác nhận rồi transaction DB nhận `40P01`, service retry cả nghiệp vụ. Lỗi thiết kế là gì?

*Gợi ý:* Email đã gửi là tác dụng phụ ngoài DB và có thể bị gửi lặp. Tách việc công bố khỏi transaction bằng outbox/idempotency, chỉ retry phần có thể đảo ngược/kiểm soát.

## 13. Ghi nhớ

- **Lock wait** là chờ một khóa xung đột; transaction có thể tiếp tục khi bên giữ khóa kết thúc.
- **Timeout** giới hạn thời gian ở một lớp cụ thể: pool, kết nối mạng, câu SQL, chờ khóa hoặc transaction. Muốn sửa đúng phải phân loại đúng.
- **Deadlock** là chu trình chờ giữa các transaction; detector có thể hủy một victim. Không đồng nhất deadlock với mọi truy vấn chậm.
- **Phòng tránh** bằng transaction ngắn, thứ tự khóa nhất quán, truy vấn chọn lọc và kiểm soát hàng nóng; vẫn phải thiết kế xử lý lỗi vì không thể tránh hết mọi tranh chấp.
- **Tầng persistence Java** cần rollback đúng phạm vi, retry **trọn transaction** khi phù hợp, giới hạn số lần thử và bảo vệ các tác dụng phụ bằng idempotency.

Kiểm soát đồng thời hiệu quả không có nghĩa mọi giao dịch đều chạy mà không cần chờ. Mục tiêu là **duy trì bất biến dữ liệu, nhận diện và xử lý tranh chấp có giới hạn, giải phóng tài nguyên đúng lúc**, đồng thời giữ độ trễ và thông lượng ổn định khi ứng dụng tăng tải.
