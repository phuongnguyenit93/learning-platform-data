# lock_timeout, statement_timeout và tác động khác nhau trong PostgreSQL

Trong PostgreSQL, một câu SQL có thể chậm vì nhiều nguyên nhân: đọc quá nhiều hàng, lập kế hoạch hoặc sắp xếp dữ liệu lớn, chạy hàm tốn CPU, chờ I/O, hoặc **đợi transaction khác nhả khóa**. Nhìn từ phía ứng dụng, chúng có vẻ giống nhau: request chưa có kết quả. Nhưng giải pháp cho một truy vấn chạy lâu không giống giải pháp cho một câu `UPDATE` bị chặn bởi row lock.

Hai tham số thường được dùng để kiểm soát tình huống đó là:

- **`lock_timeout`**: giới hạn thời gian một statement được **chờ lấy một khóa**.
- **`statement_timeout`**: giới hạn thời gian xử lý **cả câu statement** tại PostgreSQL, trong đó có cả thời gian chờ khóa.

Ví dụ, truy vấn mất bốn giây vì tính toán nhưng không chờ khóa sẽ không bị `lock_timeout = '500ms'` hủy chỉ vì chạy lâu; nó có thể bị `statement_timeout = '2s'` hủy. Ngược lại, câu UPDATE chờ một hàng do transaction khác giữ có thể bị `lock_timeout = '500ms'` hủy dù `statement_timeout = '10s'` chưa hết.

Bài học thuộc chương **Khóa** của module *Database Engine Relational PostgreSQL*. Mục tiêu không chỉ nhớ cú pháp SET, mà hiểu **bộ đếm nào đang chạy, lỗi nào phát sinh, trạng thái transaction sau khi lỗi, cách tìm blocker, và phối hợp timeout database với ứng dụng và migration**.

## 1. Phân biệt thời gian thực thi, chờ khóa và transaction

Giả sử câu lệnh sau được gửi đến PostgreSQL:

~~~sql
UPDATE inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001'
  AND stock > 0;
~~~

Bảng `inventory` ở đây là ví dụ cấu trúc; phần lab sẽ tạo bảng với schema riêng.

Một lịch thực thi khái niệm:

~~~text
Bắt đầu statement                                    Kết thúc
|--------------------------------------------------------|
| Parse/plan | Chờ lock | Đọc, kiểm tra, UPDATE, ghi WAL |
|    20ms    |  2400ms  |             1580ms            |
             |<------->|
              lock wait
|<--------------------- 4000ms ------------------------>|
                   statement duration
~~~

Nếu chỉ chờ một khóa 2400ms và:

- `lock_timeout='500ms'`, câu lệnh thường bị hủy khoảng sau 500ms chờ khóa.
- `statement_timeout='2s'`, câu lệnh bị hủy khi ngân sách thời gian statement hết dù có hay không lock wait.
- Một HTTP timeout 5s tính từ thời điểm request đến gateway lại có phạm vi khác: nó có thể bao gồm routing, pool wait và network trước khi PostgreSQL nhận SQL.

### 1.1. Một statement khác một transaction

~~~sql
BEGIN;
SELECT ...;
UPDATE ...;
SELECT ...;
COMMIT;
~~~

Transaction có thể chứa nhiều statements. Nếu mỗi câu mất 1,5 giây và statement_timeout là 2 giây, tổng thời gian transaction vẫn có thể vượt 2 giây mà không câu riêng lẻ nào chạm giới hạn.

### 1.2. Lock wait khác lock hold

- **Lock wait**: transaction muốn lấy lock nhưng chưa được cấp vì xung đột.
- **Lock hold**: transaction đã lấy được lock và đang giữ lock cho tới khi được nhả theo ngữ nghĩa PostgreSQL.

`lock_timeout` nhắm vào **wait**, không phải giới hạn **hold**. Đây là phân biệt quan trọng nhất của chương này.

## 2. lock_timeout là gì?

`lock_timeout` là tham số PostgreSQL giới hạn thời gian một câu lệnh chờ khi cố lấy một lock đang bị tranh chấp.

~~~sql
SET lock_timeout = '750ms';
~~~

Nếu khóa không được cấp trong khoảng thời gian cho phép, PostgreSQL hủy statement với thông báo thường gặp:

~~~text
ERROR: canceling statement due to lock timeout
~~~

SQLSTATE điển hình là **`55P03`** (`lock_not_available`).

### 2.1. Được áp dụng ở đâu?

Không chỉ với `LOCK TABLE` tường minh. PostgreSQL cần lock trong nhiều công việc:

- Cập nhật/xóa cùng hàng trong các transaction khác nhau.
- `SELECT ... FOR UPDATE</BT> trên hàng đang bị khóa.
- `INSERT/UPDATE/DELETE</BT> cần những table-level locks phù hợp.
- `ALTER TABLE</BT> hoặc DDL cần lock mạnh.
- Một `SELECT` thông thường cần lock trên quan hệ và có thể bị chặn bởi một `ACCESS EXCLUSIVE</BT> đang được giữ.
- Những thao tác phải lấy lock theo cơ chế PostgreSQL Lock Manager.

Không phải mọi thao tác trên cùng bảng đều xung đột. PostgreSQL sử dụng MVCC và các lock modes khác nhau để cho phép nhiều đọc/ghi diễn ra đồng thời khi tương thích.

### 2.2. Không giới hạn thời gian chạy câu lệnh

~~~sql
SET lock_timeout = '100ms';

SELECT pg_sleep(2);
~~~

Nếu không có lock contention liên quan, `pg_sleep(2)` vẫn có thể hoàn thành, bởi delay này không phải chờ lấy lock.

### 2.3. Không giới hạn thời gian giữ khóa

Nếu T1:

~~~sql
BEGIN;
UPDATE inventory SET stock = stock + 1 WHERE sku = 'BOOK-001';
-- Ứng dụng bỏ quên COMMIT.
~~~

thì `lock_timeout='500ms'` **ở chính T1** không bắt transaction tự kết thúc sau 500ms đã giữ khóa. Session khác chờ nó có thể timeout, nhưng blocker vẫn giữ lock tới khi COMMIT, ROLLBACK hoặc connection/transaction kết thúc theo cơ chế khác.

### 2.4. Tính riêng từng lần cố lấy khóa

Một statement có thể cần nhiều locks theo trình tự. Timeout áp dụng cho **mỗi lần chờ lấy lock**, không cộng dồn tất cả lock waits thành một ngân sách tổng.

Ví dụ:

~~~text
wait lock A = 400ms
wait lock B = 400ms
wait lock C = 400ms

lock_timeout = 500ms
~~~

Ba lần chờ đều dưới 500ms. Không được kết luận statement chắc chắn bị lock_timeout chỉ vì tổng wait là 1200ms. Một `statement_timeout='1s'` có thể hủy do tổng statement vượt ngân sách.

## 3. statement_timeout là gì?

`statement_timeout` giới hạn thời gian xử lý **toàn câu lệnh SQL** trên server.

~~~sql
SET statement_timeout = '3s';
~~~

Nếu vượt giới hạn, thông báo thường là:

~~~text
ERROR: canceling statement due to statement timeout
~~~

SQLSTATE điển hình là **`57014`** (`query_canceled`).

### 3.1. Có tính thời gian chờ khóa

Nếu câu UPDATE bị chặn bởi row lock trong 5 giây nhưng statement_timeout là 2 giây, nó có thể bị hủy do statement_timeout ngay cả khi `lock_timeout=0`.

### 3.2. Có tính các hoạt động khác

Statement timeout có thể chấm dứt câu SQL chạy lâu vì:

- Scan hoặc join quá lớn.
- Sort, aggregation hay thao tác trên dữ liệu lớn.
- Thực thi function/extension.
- Chờ I/O.
- Chờ lock.
- Một câu `pg_sleep()`.
- DDL hoặc một utility statement đang chạy trong phạm vi áp dụng.

### 3.3. Không phải timeout tổng của transaction

~~~sql
BEGIN;
SELECT pg_sleep(0.4);
SELECT pg_sleep(0.4);
SELECT pg_sleep(0.4);
COMMIT;
~~~

Nếu statement_timeout 500ms, mỗi SELECT vẫn có thể thành công dù tổng thời gian lớn hơn 500ms.

### 3.4. Không phải đồng hồ tính từ lúc người dùng nhấn nút

PostgreSQL đo statement theo giao thức server. Với simple-query protocol, ở các phiên bản hiện đại, các statement riêng biệt trong cùng query string được áp dụng timeout theo từng statement; behavior chi tiết có khác biệt lịch sử giữa phiên bản. Với extended-query protocol, các message `Parse</BT>, `Bind</BT>, `Execute</BT>, `Describe</BT> và mốc kết thúc liên quan quyết định lúc tính timeout.

Điểm thực hành: statement_timeout **không tự bao gồm** thời gian request chờ trên gateway, chờ mượn connection pool hoặc xử lý trong ứng dụng trước khi SQL đến PostgreSQL.

## 4. So sánh trực tiếp

| Khía cạnh | `lock_timeout` | `statement_timeout` |
|---|---|---|
| Phạm vi | Chờ lấy một lock | Toàn bộ statement |
| Có cần lock contention? | Có, để bộ đếm chờ khóa có ý nghĩa | Không |
| Chờ row/table lock | Có | Có |
| CPU/I/O query | Không phải mục tiêu | Có |
| Nhiều lock waits | Giới hạn từng wait | Giới hạn tổng statement |
| Thời gian giữ khóa sau khi cấp | Không giới hạn | Không giới hạn trực tiếp toàn transaction |
| Thời gian toàn transaction | Không | Không |
| Lỗi thường gặp | 55P03 | 57014 |
| Dùng trong DDL | Fail fast khi đợi lock | Giới hạn cả thời gian chạy |
| Giá trị 0 | Tắt timeout này | Tắt timeout này |
| Giá trị số nguyên không đơn vị | Mili-giây | Mili-giây |

Một câu dễ nhớ: **lock_timeout bảo vệ “đừng chờ một khóa quá lâu”; statement_timeout bảo vệ “đừng để một câu SQL chạy quá lâu”.**

## 5. Hai timeout cùng hoạt động: cái nào hết trước?

Giả sử câu SQL đang đợi lock không được nhả.

### 5.1. lock_timeout nhỏ hơn

~~~sql
SET lock_timeout = '400ms';
SET statement_timeout = '5s';
~~~

Nếu khóa bị giữ lâu hơn 400ms, thông thường lỗi 55P03 xuất hiện trước. Đây là cách tách một ngân sách **chờ khóa ngắn** và một ngân sách **thực thi tổng dài hơn**.

### 5.2. statement_timeout nhỏ hơn

~~~sql
SET lock_timeout = '5s';
SET statement_timeout = '400ms';
~~~

Statement timeout có thể chấm dứt câu SQL khoảng sau 400ms, ngay khi nó đang chờ lock. Khi đó ứng dụng thường nhận 57014 chứ không cần đợi 55P03.

### 5.3. lock_timeout bằng hoặc lớn hơn statement_timeout

Thông thường cấu hình này **ít có ý nghĩa** vì statement timeout đã bao phủ thời gian lock wait và có thể kích hoạt trước hoặc cùng lúc. Nếu mục tiêu là phân biệt lock contention, hãy đặt hai ngưỡng đủ tách biệt.

### 5.4. Không dựa vào thứ tự lỗi khi hai ngưỡng sát nhau

Scheduling, thời điểm khóa được nhả và tín hiệu hủy có thể xảy ra gần nhau. Không nên xây logic nghiệp vụ với giả định hai timeout bằng nhau chắc chắn cho một SQLSTATE cụ thể.

### 5.5. Ví dụ với nhiều lock

~~~text
lock_timeout = 700ms
statement_timeout = 1600ms

wait A 600ms
CPU    250ms
wait B 600ms
CPU    250ms

Tổng = 1700ms
~~~

Từng lock wait dưới 700ms, nhưng tổng statement vượt 1600ms. Đây là trường hợp có thể gặp statement_timeout mà không có lock_timeout.

## 6. Giá trị, đơn vị và cách xem cấu hình

~~~sql
SHOW lock_timeout;
SHOW statement_timeout;

SELECT name, setting, unit, source
FROM pg_settings
WHERE name IN ('lock_timeout', 'statement_timeout')
ORDER BY name;
~~~

### 6.1. Đơn vị

~~~sql
SET lock_timeout = '250ms';
SET statement_timeout = '3s';
~~~

Có thể dùng các hậu tố thời gian PostgreSQL hỗ trợ, ví dụ `ms`, `s` hoặc `min`.

### 6.2. Số nguyên mặc định là mili-giây

~~~sql
SET lock_timeout = 500;
SET statement_timeout = 4000;
~~~

Tương đương 500ms và 4000ms. **`SET statement_timeout = 5` là 5ms, không phải 5 giây.**

### 6.3. Giá trị 0

~~~sql
SET lock_timeout = 0;
SET statement_timeout = 0;
~~~

Tắt hai giới hạn tương ứng; không có nghĩa các câu SQL không bao giờ bị cancel vì client disconnect, administrator, lỗi transaction, bảo vệ hệ thống hoặc timeout khác.

### 6.4. Cấu hình thực tế có thể khác file config

Một session có thể có giá trị được đặt bởi `ALTER ROLE</BT>, `ALTER DATABASE</BT>, tham số kết nối hoặc `SET</BT> ở runtime. Khi điều tra một request cụ thể, đọc `SHOW</BT> trong connection liên quan và xem `pg_settings.source` nếu cần.

## 7. SET, SET LOCAL, RESET

### 7.1. SET ở phạm vi session

~~~sql
SET lock_timeout = '500ms';
SET statement_timeout = '3s';
~~~

Giá trị thường tiếp tục có hiệu lực trong session cho tới khi được đổi/reset hoặc session kết thúc, với ngữ nghĩa transaction của PostgreSQL.

### 7.2. SET LOCAL ở phạm vi transaction

~~~sql
BEGIN;
SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '3s';

SELECT COUNT(*) FROM pg_class;

COMMIT;
~~~

`SET LOCAL` hữu ích khi chỉ một workflow cần ngân sách riêng. Sau khi transaction kết thúc, các giá trị local được trả về cấu hình hiệu lực thích hợp của session.

### 7.3. Không dùng SET LOCAL ngoài transaction rồi kỳ vọng có tác dụng ở câu kế tiếp

`SET LOCAL` có ý nghĩa trong transaction block. Trong autocommit, không nên viết nó ở một statement riêng rồi mong một SELECT sau đó vẫn thừa hưởng.

### 7.4. RESET về default hiệu lực

~~~sql
RESET lock_timeout;
RESET statement_timeout;
~~~

`RESET</BT> không mặc định nghĩa là về 0 nếu default hiệu lực đã được role/database cấu hình khác.

### 7.5. SET trong transaction và rollback

Nếu thay giá trị bằng `SET</BT> trong một transaction rồi transaction bị rollback, thay đổi cấu hình có thể bị rollback theo ngữ nghĩa PostgreSQL. Đối với một transaction nghiệp vụ, `SET LOCAL` thường biểu đạt phạm vi mong muốn rõ hơn.

## 8. Cấu hình theo role và database

Các câu sau là ví dụ cấu trúc, chỉ chạy nếu có role/database và quyền tương ứng:

~~~sql
ALTER ROLE app_writer
SET lock_timeout = '500ms';

ALTER ROLE app_writer
SET statement_timeout = '8s';

ALTER DATABASE app_db
SET statement_timeout = '10s';

ALTER ROLE app_writer IN DATABASE app_db
SET lock_timeout = '700ms';
~~~

### 8.1. Tác động lên kết nối

Default ở role/database thường được áp dụng khi thiết lập session mới. Kết nối trong pool đã mở có thể không nhận giá trị default mới cho tới khi reconnect hoặc đổi cấu hình trực tiếp.

### 8.2. Phạm vi cấu hình quan trọng

Một ứng dụng OLTP cần xử lý nhanh khác với báo cáo hàng giờ hoặc migration schema. Không đặt mọi workload dưới một statement_timeout quá ngắn nếu không có cơ sở.

### 8.3. Nguy cơ session leak trong pool

Nếu một request thực hiện:

~~~sql
SET statement_timeout = '200ms';
~~~

rồi trả connection về pool mà không reset, request khác có thể gặp timeout bất ngờ. Dùng `SET LOCAL` trong transaction hoặc cơ chế transaction manager/connection initialization chuẩn hóa.

### 8.4. Quyền điều chỉnh

Một số cấu hình ở mức server/role/database cần quyền phù hợp. Không mở rộng quyền production chỉ để một endpoint tự điều chỉnh timeout; hãy để việc cấu hình qua migration/ops hoặc API đã được kiểm soát.

## 9. Chuẩn bị lab hai phiên PostgreSQL

Phần tiếp theo cần **hai connection độc lập** đến cùng database: Session A và Session B. Dùng database **thử nghiệm**, không chạy trên production. Nếu schema `timeout_lab` đã tồn tại, hãy chọn database hoặc tên schema khác; không xóa dữ liệu không thuộc lab.

### 9.1. Tạo schema

~~~sql
CREATE SCHEMA timeout_lab;
~~~

### 9.2. Tạo bảng tồn kho

~~~sql
CREATE TABLE timeout_lab.inventory (
    sku TEXT PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO timeout_lab.inventory (sku, stock)
VALUES ('BOOK-001', 10), ('BOOK-002', 20);
~~~

### 9.3. Tạo bảng ghi chú

~~~sql
CREATE TABLE timeout_lab.notes (
    note_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content TEXT NOT NULL
);

INSERT INTO timeout_lab.notes (content)
VALUES ('A'), ('B'), ('C');
~~~

### 9.4. Cách chạy

- Session A giữ khóa, không commit vội.
- Session B chạy câu SQL cần lock và có timeout.
- Có thể mở Session C để quan sát trong khi B đang đợi.
- Sau thí nghiệm, luôn kết thúc transaction bằng COMMIT hoặc ROLLBACK.
- Nếu B bị lỗi trong explicit BEGIN, rollback B trước khi chạy việc khác.
- Nếu dùng GUI, xác nhận A và B thực sự dùng **hai backend connections**, không chỉ hai editor tabs của một connection.

## 10. Lab 1: lock_timeout trên một row UPDATE

### 10.1. Session A — chiếm row lock

~~~sql
BEGIN;

UPDATE timeout_lab.inventory
SET stock = stock + 1
WHERE sku = 'BOOK-001';

-- Chưa COMMIT/ROLLBACK.
~~~

### 10.2. Session B — chờ khóa

~~~sql
BEGIN;

SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '10s';

UPDATE timeout_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001';
~~~

B muốn sửa cùng hàng do A đang cập nhật trong một transaction chưa kết thúc.

Sau khoảng 500ms chờ lock, B thường nhận:

~~~text
ERROR: canceling statement due to lock timeout
SQLSTATE 55P03
~~~

### 10.3. Dọn dẹp

Session B:

~~~sql
ROLLBACK;
~~~

Session A:

~~~sql
ROLLBACK;
~~~

Dùng ROLLBACK ở A để đưa tồn kho về trạng thái trước lab. Nếu A COMMIT thì phép cộng stock được giữ lại.

### 10.4. Rút ra

- B thất bại do **không lấy được lock kịp thời**.
- A không bị lock_timeout của B hủy.
- B không tự nhả lock đang do A giữ.
- Nếu A nhả khóa trước ngưỡng 500ms, B có thể tiếp tục và thành công.

## 11. Lab 2: statement_timeout khi không bị lock contention

Ở một connection không có explicit BEGIN:

~~~sql
SET lock_timeout = '200ms';
SET statement_timeout = '500ms';

SELECT pg_sleep(2);
~~~

Thông thường PostgreSQL trả:

~~~text
ERROR: canceling statement due to statement timeout
SQLSTATE 57014
~~~

Hàm `pg_sleep(2)` được dùng để mô phỏng statement chạy lâu; không phải chờ một row lock do session khác giữ.

### 11.1. Vì sao không nhận 55P03?

`lock_timeout` không đo thời gian statement nói chung. Không có yêu cầu lock bị chặn đủ lâu để kích hoạt lock timeout.

### 11.2. Dọn dẹp

~~~sql
RESET lock_timeout;
RESET statement_timeout;
~~~

Không chạy pg_sleep kéo dài trên production. Lab chỉ cần thời gian ngắn để quan sát.

## 12. Lab 3: statement_timeout thắng dù đang chờ khóa

### 12.1. Session A

~~~sql
BEGIN;

UPDATE timeout_lab.inventory
SET stock = stock + 1
WHERE sku = 'BOOK-001';

-- Giữ transaction mở.
~~~

### 12.2. Session B

~~~sql
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '500ms';

UPDATE timeout_lab.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-001';
~~~

B đang chờ khóa, nhưng đồng hồ toàn statement 500ms hết trước. Lỗi thường là:

~~~text
ERROR: canceling statement due to statement timeout
SQLSTATE 57014
~~~

### 12.3. Dọn dẹp

Ở B:

~~~sql
ROLLBACK;
~~~

Ở A:

~~~sql
ROLLBACK;
~~~

### 12.4. So sánh kết quả ba lab

| Lab | lock_timeout | statement_timeout | Tình huống | Kỳ vọng |
|---|---:|---:|---|---|
| 1 | 500ms | 10s | Chờ row lock | 55P03 |
| 2 | 200ms | 500ms | pg_sleep(2) | 57014 |
| 3 | 5s | 500ms | Chờ row lock | 57014 |

Thời điểm thực tế có thể dao động theo tải server. Khi hai đồng hồ sát nhau, không nên dựa vào mã lỗi nhất định theo từng mili-giây.

## 13. Lab 4: SELECT vẫn có thể gặp lock_timeout

Một SELECT thông thường thường không chặn UPDATE thông thường nhờ MVCC và lock compatibility, nhưng vẫn cần table lock và có thể bị chặn bởi `ACCESS EXCLUSIVE`.

### 13.1. Session A

~~~sql
BEGIN;

LOCK TABLE timeout_lab.notes IN ACCESS EXCLUSIVE MODE;

-- Giữ transaction mở.
~~~

### 13.2. Session B

~~~sql
BEGIN;

SET LOCAL lock_timeout = '600ms';
SET LOCAL statement_timeout = '5s';

SELECT COUNT(*)
FROM timeout_lab.notes;
~~~

Nếu A chưa nhả lock, SELECT ở B thường gặp 55P03.

### 13.3. Dọn dẹp

Session B:

~~~sql
ROLLBACK;
~~~

Session A:

~~~sql
ROLLBACK;
~~~

### 13.4. Ý nghĩa

Không đúng khi nói **“mọi SELECT đều không bao giờ bị lock”**. Cần xét lock mode được yêu cầu và lock đang được giữ, đặc biệt khi có DDL hoặc LOCK TABLE mạnh.

## 14. Sau khi timeout, transaction ở trạng thái nào?

### 14.1. Autocommit

Khi `SELECT pg_sleep(2)` bị statement_timeout mà không có `BEGIN` tường minh, transaction ngầm của câu đó bị hủy. Connection thường vẫn có thể dùng cho statement kế tiếp nếu còn hợp lệ.

### 14.2. Explicit transaction

~~~sql
BEGIN;

SET LOCAL statement_timeout = '400ms';

SELECT pg_sleep(2);
-- ERROR 57014

SELECT 1;
-- Thường báo: current transaction is aborted.

ROLLBACK;
~~~

Một statement lỗi trong explicit transaction thường khiến transaction rơi vào trạng thái failed/aborted. Chạy câu SELECT khác không làm nó tự lành.

### 14.3. UPDATE trước timeout không tự commit

~~~sql
BEGIN;

UPDATE timeout_lab.inventory
SET stock = stock + 1
WHERE sku = 'BOOK-002';

SELECT pg_sleep(2);
-- Nếu câu này bị timeout, transaction bị lỗi.

ROLLBACK;
~~~

Phép UPDATE trước đó không tự trở thành dữ liệu đã commit. Nếu ứng dụng phát thông báo thành công **trước COMMIT**, có thể báo sai.

### 14.4. SAVEPOINT

PostgreSQL hỗ trợ `SAVEPOINT</BT> và `ROLLBACK TO SAVEPOINT</BT> để xử lý một số lỗi statement trong transaction:

~~~sql
BEGIN;

SAVEPOINT before_optional_step;

-- Bước tùy chọn có thể gặp lỗi.
-- Nếu lỗi: ROLLBACK TO SAVEPOINT before_optional_step.

COMMIT;
~~~

Nhưng savepoint không đảm bảo quyết định nghiệp vụ còn đúng sau lỗi. Với workflow phụ thuộc kiểm tra điều kiện, có thể cần rollback và đánh giá lại toàn transaction.

## 15. Timeout không sửa blocker

Một kịch bản:

~~~text
Session A:
  BEGIN
  UPDATE inventory WHERE sku='BOOK-001'
  chờ payment API 20 giây nhưng không COMMIT

Session B:
  UPDATE cùng SKU
  lock_timeout 500ms
  => B lỗi 55P03

Session A vẫn còn mở.
~~~

Lỗi B **không tự động rollback A**. Do vậy nếu nhiều request liên tục gặp 55P03, đừng chỉ tăng retry của B; phải tìm vì sao A giữ lock lâu.

### 15.1. Kiểu bug thường gặp

- Quên COMMIT/ROLLBACK trong nhánh exception.
- Gọi dịch vụ bên ngoài khi đang mở transaction.
- Một transaction phục vụ nhiều tương tác người dùng.
- Worker giữ kết nối trong lúc chờ queue.
- DDL/migration mở BEGIN và bị bỏ dở.
- Connection pool trả lại connection còn trong transaction.

### 15.2. Transaction ngắn là biện pháp quan trọng

Chỉ giữ transaction mở cho phần cần atomic, tránh network calls kéo dài trong lúc giữ row locks. Timeout là hàng rào bảo vệ, không thay thiết kế transaction đúng.

## 16. pg_stat_activity: backend nào đang chờ khóa?

Từ kết nối quan sát:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST;
~~~

### 16.1. wait_event_type='Lock'

Đây là dấu hiệu backend đang chờ một loại lock. Nhưng query chậm không nhất thiết có wait_event_type='Lock': có thể đang chờ I/O, WAL, client hoặc sử dụng CPU.

### 16.2. state='idle in transaction'

Session có thể đang nhàn rỗi giữa hai câu SQL nhưng **vẫn mở transaction** và giữ locks đã lấy trước đó. Đây là một nguyên nhân contention phổ biến.

### 16.3. xact_start khác query_start

- `xact_start`: khi transaction đang mở bắt đầu.
- `query_start`: thời điểm câu SQL được theo dõi bắt đầu.
- Transaction có thể kéo dài lâu hơn statement cuối cùng.

Chỉ tìm truy vấn “đang chạy lâu” có thể bỏ sót một blocker đang idle in transaction.

### 16.4. Quyền giám sát

Role thiếu quyền xem thống kê của những session khác có thể chỉ thấy thông tin hạn chế. Dùng role monitoring thích hợp, không cấp quyền cao không cần thiết.

## 17. pg_blocking_pids: ai đang chặn ai?

~~~sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock'
ORDER BY a.pid;
~~~

Khi B chờ row lock do A giữ, cột `blocking_pids</BT> có thể chứa PID của A.

### 17.1. Chụp trạng thái khi đang chờ

Nếu B hết lock_timeout sau 500ms, sau đó mới chạy query monitoring thì B có thể không còn chờ lock. Vì vậy một snapshot rỗng **không chứng minh không từng có contention**.

### 17.2. Blocker có thể đang idle

Một transaction giữ lock trong trạng thái `idle in transaction` vẫn có thể nằm trong danh sách PID chặn B, dù bản thân A không chạy câu SQL nào lúc quan sát.

### 17.3. Hàng đợi khóa cũng quan trọng

Một backend có thể bị chặn bởi lock holder hoặc bởi lock request khác đang chờ theo thứ tự hàng đợi, tùy ngữ nghĩa. Không chỉ dựa vào cặp PID đơn giản để suy ra mọi phụ thuộc khóa trong hệ thống.

## 18. pg_locks: nhìn mode và granted

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name,
    page,
    tuple
FROM pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, locktype, mode;
~~~

| Trường | Ý nghĩa |
|---|---|
| `pid` | Backend liên quan |
| `locktype` | Kiểu đối tượng |
| `mode` | Chế độ lock |
| `granted` | Đã được cấp hay đang chờ |
| `relation_name` | Quan hệ có liên quan khi có |
| `page</BT>, `tuple` | Chi tiết cho một số kiểu lock |

### 18.1. Không tìm row lock chỉ bằng một dòng

Khi UPDATE cùng hàng đang tranh chấp, backend chờ có thể hiện lock trên `transactionid`, không đơn thuần một dòng tuple lock có tên hàng. Kết hợp `pg_blocking_pids</BT> và `pg_stat_activity</BT> thường dễ điều tra hơn.

### 18.2. pg_locks là trạng thái hiện tại

Nó không phải bảng lịch sử 55P03/57014. Muốn thống kê lỗi qua thời gian cần application metrics hoặc server logs phù hợp.

## 19. FOR UPDATE NOWAIT và SKIP LOCKED

Có những tình huống không muốn chờ lock theo thời gian, mà muốn ứng xử theo loại công việc.

### 19.1. NOWAIT

~~~sql
BEGIN;

SELECT sku, stock
FROM timeout_lab.inventory
WHERE sku = 'BOOK-001'
FOR UPDATE NOWAIT;

COMMIT;
~~~

Nếu row đang bị khóa xung đột, `NOWAIT` khiến truy vấn không chờ row lock theo cách thông thường mà có thể trả lỗi ngay.

### 19.2. SKIP LOCKED

~~~sql
BEGIN;

SELECT sku, stock
FROM timeout_lab.inventory
WHERE stock > 0
ORDER BY sku
FOR UPDATE SKIP LOCKED
LIMIT 1;

COMMIT;
~~~

`SKIP LOCKED` cho phép bỏ qua các hàng đang bị khóa. Hữu ích cho một số mô hình worker queue, trong đó có thể lấy **bất kỳ job khả dụng**.

### 19.3. Không dùng SKIP LOCKED khi cần đúng một hàng

Nếu request cần sửa đúng `BOOK-001`, việc skip hàng đang khóa và trả kết quả rỗng có thể khiến ứng dụng hiểu nhầm “không có sản phẩm”.

### 19.4. NOWAIT không phải lock_timeout thay thế hoàn toàn

`NOWAIT` áp dụng theo cú pháp khóa được hỗ trợ. Một statement còn có thể cần lock mức bảng hay những loại lock khác. `lock_timeout` giới hạn chờ lock nói chung ở những request liên quan.

### 19.5. SKIP LOCKED không bỏ qua mọi loại lock

Tùy truy vấn, `FOR UPDATE SKIP LOCKED` vẫn cần table lock phù hợp; không nên nghĩ nó miễn nhiễm với mọi DDL contention.

## 20. lock_timeout trong migration/DDL

Một số câu `ALTER TABLE` cần lock mạnh. Nếu chờ lâu, migration có thể gây hàng đợi khóa và tăng latency cho ứng dụng.

### 20.1. Fail fast khi không lấy được khóa

~~~sql
BEGIN;

SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE timeout_lab.inventory
ADD COLUMN warehouse_note TEXT;

COMMIT;
~~~

Trong lab, câu này thêm cột mới. Không chạy lại nguyên văn khi cột đã tồn tại và không dùng trực tiếp trên production khi chưa có kế hoạch migration.

### 20.2. Hai ngân sách khác nhau

- `lock_timeout='1s'`: nếu không lấy được lock kịp, dừng sớm.
- `statement_timeout='30s'`: sau khi lấy được lock, vẫn có giới hạn tổng cho phần việc thực thi.

### 20.3. DDL có thể vừa chờ vừa xử lý lâu

Một số thao tác thay schema còn phải scan, validate hoặc rewrite bảng. `lock_timeout` không giới hạn phần thực thi này. Chọn timeout theo loại migration, dữ liệu và SLA.

### 20.4. CREATE INDEX CONCURRENTLY

`CREATE INDEX CONCURRENTLY` không chạy trong explicit transaction block. Không copy mẫu BEGIN + SET LOCAL cho mọi migration. Các công cụ migration cần đặt cấu hình theo scope phù hợp với từng lệnh và trạng thái transaction.

### 20.5. Retry migration khác retry request

Migration có thể gồm nhiều bước đã commit. Sau timeout, phải kiểm tra schema thực tế và checkpoint/idempotency trước khi thử lại, không chỉ chạy lại toàn file SQL mù quáng.

## 21. idle_in_transaction_session_timeout

Tham số này xử lý nguyên nhân khác hẳn hai tham số chính:

~~~sql
SHOW idle_in_transaction_session_timeout;
~~~

Mục tiêu là **session đang idle nhưng vẫn ở trong transaction** quá lâu. Nếu kích hoạt theo cấu hình, PostgreSQL có thể chấm dứt session đó để giải phóng tài nguyên/locks.

### 21.1. So sánh

| Tham số | Nhắm vào |
|---|---|
| `lock_timeout` | Một lần chờ lấy lock |
| `statement_timeout` | Thời gian xử lý câu SQL |
| `idle_in_transaction_session_timeout` | Session idle trong transaction |
| `idle_session_timeout` | Session idle ngoài transaction theo cấu hình |
| `deadlock_timeout` | Mốc liên quan kiểm tra deadlock, không phải kill-after-wait thông thường |

### 21.2. Ảnh hưởng pool

Nếu PostgreSQL chấm dứt một session idle quá hạn, connection pool phải biết connection đó không còn hợp lệ. Cần cấu hình validation/recovery thay vì cho các request sau dùng connection chết.

### 21.3. Không dùng timeout để thay việc đóng transaction đúng

Code vẫn phải COMMIT hoặc ROLLBACK trong `finally</BT>/transaction manager. Session timeout là mạng an toàn, không phải cơ chế điều khiển nghiệp vụ bình thường.

## 22. transaction_timeout trên những phiên bản hỗ trợ

Các phiên bản PostgreSQL mới có thể cung cấp `transaction_timeout` để giới hạn thời gian transaction theo cơ chế server tương ứng. Vì không phải mọi phiên bản đều hỗ trợ, cần xem **server_version** và `pg_settings` trước khi triển khai.

~~~sql
SHOW server_version;

SELECT name, setting, unit
FROM pg_settings
WHERE name = 'transaction_timeout';
~~~

Nếu câu SELECT không trả hàng, server hiện tại không công bố tham số này.

### 22.1. Khác statement_timeout

Transaction có thể chạy nhiều statements; `transaction_timeout` nhắm vào thời lượng giao dịch theo semantics của phiên bản, chứ không chỉ một SELECT hay UPDATE.

### 22.2. Không thay ứng dụng quản lý deadline

Một transaction quá dài vì đợi API ngoài vẫn cần được thiết kế ngắn lại. Timeout chỉ xử lý hậu quả, còn ứng dụng phải xác định khi nào có thể abort, retry và trả kết quả.

### 22.3. Quy tắc vận hành

Không đưa một tên tham số không có trong phiên bản đang chạy vào script cấu hình production mà không kiểm tra. Những thay đổi GUC theo server/role/database cần kế hoạch triển khai và kiểm soát quyền.

## 23. deadlock_timeout không giống lock_timeout

Một **deadlock** là chu trình chờ khóa:

~~~text
T1 giữ lock A, chờ lock B.
T2 giữ lock B, chờ lock A.
~~~

PostgreSQL phát hiện và hủy một transaction, thường với **SQLSTATE 40P01**.

`deadlock_timeout` liên quan tới **thời gian chờ trước khi chạy kiểm tra deadlock**, cũng có liên quan tới việc ghi log lock waits khi `log_lock_waits` được bật. Nó **không có nghĩa mọi lock wait vượt ngưỡng đó đều tự bị hủy**.

### 23.1. Ba lỗi cần phân biệt

| SQLSTATE | Ngữ cảnh |
|---|---|
| `55P03` | Lock không lấy được theo điều kiện, gồm lock_timeout/NOWAIT |
| `57014` | Query canceled, gồm statement_timeout |
| `40P01` | Deadlock được phát hiện |

### 23.2. Tránh deadlock đúng cách

Giữ transaction ngắn, lấy locks theo thứ tự nhất quán, giảm phạm vi khóa, và retry toàn transaction khi một deadlock đã xảy ra.

Không chỉ hạ `lock_timeout` xuống vài mili-giây để che một protocol lấy lock sai thứ tự.

## 24. Client timeout và server timeout

Một request có nhiều tầng thời gian:

~~~text
Browser
  |
API gateway                -> request timeout
  |
Application service         -> business deadline
  |
Connection pool             -> pool acquire timeout
  |
JDBC driver                 -> query timeout / socket timeout
  |
PostgreSQL
  |-- lock_timeout
  |-- statement_timeout
  |-- session/transaction timers khác
~~~

### 24.1. JDBC setQueryTimeout

~~~java
PreparedStatement ps = connection.prepareStatement(sql);
ps.setQueryTimeout(5);
~~~

Trong JDBC, API query timeout nhận **giây**, còn nhiều GUC PostgreSQL nhận mili-giây nếu nhập số nguyên không đơn vị. Driver có thể triển khai cơ chế hủy query riêng.

`ps.setQueryTimeout(5)</BT> **không nên bị coi là tương đương tuyệt đối** với `SET statement_timeout='5s'` ở mọi mặt.

### 24.2. Pool wait không nằm trong statement timeout

Nếu request đợi 2 giây để mượn connection và SQL mất 1 giây, statement_timeout=2s có thể không hủy câu SQL dù tổng request đã mất 3 giây.

### 24.3. HTTP timeout không bảo đảm database đã rollback

Gateway trả 504 không tự chứng minh câu SQL đã dừng ngay. Driver cần hủy hoặc connection/transaction manager cần rollback theo giao thức.

### 24.4. Thiết kế deadline có tầng

Một ví dụ định hướng cho một câu UPDATE nhỏ:

~~~text
lock_timeout         300ms
statement_timeout   2500ms
API request limit   5000ms
~~~

Nhưng với request gồm nhiều statements và retries, phải tính thêm tổng thời gian. Không áp dụng một bộ số cho mọi loại workload.

## 25. Java/JDBC: đặt timeout theo transaction và xử lý SQLSTATE

Ví dụ transaction giảm tồn kho:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public class StockService {
    private final DataSource dataSource;

    public StockService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean reserveOne(String sku) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement settings =
                        connection.prepareStatement(
                            "SELECT set_config('lock_timeout', '500ms', true), " +
                            "set_config('statement_timeout', '3s', true)")) {
                    settings.execute();
                }

                try (PreparedStatement update =
                        connection.prepareStatement(
                            "UPDATE timeout_lab.inventory " +
                            "SET stock = stock - 1 " +
                            "WHERE sku = ? AND stock >= 1")) {
                    update.setString(1, sku);
                    int changed = update.executeUpdate();

                    if (changed != 1) {
                        connection.rollback();
                        return false;
                    }
                }

                connection.commit();
                return true;

            } catch (SQLException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }

                switch (error.getSQLState()) {
                    case "55P03":
                        // Lock timeout hoặc lock-not-available.
                        break;
                    case "57014":
                        // Query canceled: timeout hoặc hủy theo ngữ cảnh khác.
                        break;
                    case "40P01":
                        // Deadlock; có thể cần retry transaction.
                        break;
                    default:
                        // Các lỗi khác cần xử lý riêng.
                }
                throw error;
            }
        }
    }
}
~~~

### 25.1. set_config với is_local=true

Câu:

~~~sql
SELECT
    set_config('lock_timeout', '500ms', true),
    set_config('statement_timeout', '3s', true);
~~~

khi chạy **trong transaction** đặt cấu hình local cho transaction đó. Nó mang ý nghĩa tương tự hai câu `SET LOCAL` phù hợp, giúp tránh timeout session bị sót lại trong connection pool.

### 25.2. Không trả thành công trước COMMIT

`executeUpdate()</BT> trả số hàng thay đổi nhưng transaction có thể vẫn chưa commit. Code chỉ trả true sau `connection.commit()</BT> thành công.

### 25.3. SQLException có thể tới từ nhiều nguồn

`57014` là mã query-canceled, không chỉ statement_timeout. Cần xem ngữ cảnh và thông điệp server. Một số lỗi mạng/pool có mã khác hẳn và không thể chỉ xử lý bằng retry SQL.

### 25.4. Production cần quản lý trạng thái connection

Framework transaction manager/pool có thể cung cấp cách an toàn hơn để quản lý autoCommit, isolation và rollback. Code minh họa không thay thế toàn bộ quy tắc lifecycle connection của một hệ thống thực.

## 26. Retry: nên hay không?

| Tình huống | Cách phản ứng thường cân nhắc |
|---|---|
| 55P03 do một giao dịch ngắn đang giữ lock | Retry giới hạn, backoff/jitter |
| 55P03 do blocker idle hàng phút | Điều tra và sửa blocker |
| 57014 do truy vấn join/sort quá nặng | Tối ưu query hoặc tăng budget có cơ sở |
| 57014 do chờ lock kéo dài | Phân tích contention, điều chỉnh ngưỡng |
| 40P01 deadlock | Retry toàn transaction sau rollback |
| 40001 serialization failure | Retry toàn transaction, đọc/đánh giá lại |
| 23505 unique violation | Thường xử lý conflict nghiệp vụ |
| Client timeout không rõ COMMIT | Kiểm tra idempotency/reconciliation |

### 26.1. Retry không phải lặp ngay vô hạn

Với một hot row, hàng trăm request retry lập tức có thể khiến contention tệ hơn. Cần giới hạn attempts, exponential backoff/jitter, deadline và metrics.

### 26.2. Retry cả transaction nếu quyết định phụ thuộc dữ liệu đã đọc

Nếu workflow SELECT tồn kho rồi UPDATE/INSERT order, sau một lỗi transaction cần rollback và kiểm tra lại dữ liệu trong lần thử mới. Không chỉ lặp câu SQL cuối với quyết định lấy từ trạng thái cũ.

### 26.3. External side effect cần idempotency

Nếu service đã gọi payment API hoặc gửi email rồi PostgreSQL timeout/rollback, việc retry không kiểm soát có thể gây thanh toán hoặc thông báo lặp. Dùng idempotency key, outbox/inbox và reconciliation phù hợp.

### 26.4. Không đổi SLA vì muốn giảm số lỗi

Tăng lock_timeout từ 500ms lên 30 giây có thể giảm 55P03 nhưng khiến P99 request trầm trọng hơn, chiếm nhiều connection pool và làm tăng nguy cơ request xếp hàng. Đo tác động tổng thể.

## 27. Timeout trong transaction có nhiều statement

Một workflow có thể cần:

1. Đọc khách hàng.
2. Kiểm tra đơn trùng.
3. Giảm kho.
4. Tạo order.
5. Tạo order_items.
6. COMMIT.

Ví dụ từng statement mất 1,5 giây, statement_timeout=2 giây. Tổng thời gian có thể vượt 7 giây dù không statement nào hết hạn.

### 27.1. Cần transaction deadline riêng

Có thể kết hợp deadline ứng dụng, transaction timeout server (nếu phiên bản hỗ trợ), và giữ transaction ngắn bằng cách chuyển phần việc không cần atomic ra ngoài transaction.

### 27.2. Timeout không thay invariant

Với tồn kho, cần điều kiện:

~~~sql
UPDATE timeout_lab.inventory
SET stock = stock - 2
WHERE sku = 'BOOK-001'
  AND stock >= 2
RETURNING stock;
~~~

Lock timeout không tự ngăn tồn kho âm nếu code ghi giá trị sai. CHECK/atomic condition bảo vệ nghiệp vụ, timeout bảo vệ tài nguyên và độ trễ.

## 28. Performance: khi nào tối ưu query, khi nào tối ưu lock?

### 28.1. Query chậm vì đọc nhiều dữ liệu

~~~sql
EXPLAIN
SELECT sku, SUM(stock)
FROM timeout_lab.inventory
GROUP BY sku;
~~~

`EXPLAIN` giúp xem kế hoạch dự kiến. Trên database thử nghiệm có thể đo:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, SUM(stock)
FROM timeout_lab.inventory
GROUP BY sku;
~~~

`EXPLAIN ANALYZE` **thực sự thực thi query**, nên không chạy vô tư trên DML hoặc câu truy vấn nặng ở production.

### 28.2. Query chậm vì blocker

Một UPDATE được index giúp truy cập đúng SKU nhưng vẫn có thể chờ row lock khi transaction khác cập nhật cùng SKU. Index không loại bỏ nhu cầu điều phối các writers.

### 28.3. Cải thiện lock contention

- Giữ transaction ngắn.
- Tránh external API calls trong transaction.
- Cập nhật cùng hàng theo batch nhỏ khi phù hợp.
- Lấy lock theo thứ tự nhất quán.
- Giảm số writers tranh chấp hot row.
- Cân nhắc worker queue hoặc thiết kế phân vùng tải.
- Cân nhắc `NOWAIT</BT>/`SKIP LOCKED</BT> khi semantics cho phép.

### 28.4. Cải thiện execution chậm

- Thống kê và query plan.
- Index phù hợp predicate.
- Viết query rõ, giảm fanout join.
- Pagination hoặc giới hạn trả dữ liệu.
- Pre-aggregation/materialized views cho báo cáo khi phù hợp.
- Sizing tài nguyên và quản lý workload.

Hai danh sách cần được áp dụng dựa trên **bằng chứng**, không dựa vào cảm giác “query bị timeout”.

## 29. Logging và metrics

~~~sql
SHOW log_lock_waits;
SHOW deadlock_timeout;
~~~

Khi `log_lock_waits` bật, PostgreSQL có thể ghi log lock waits kéo dài theo mốc được quyết định bởi `deadlock_timeout`. Đây là cơ chế quan sát, không phải timeout hủy query.

### 29.1. Tại sao không có log chưa chứng minh không có chờ lock?

Nếu lock_timeout 300ms nhưng mốc logging phù hợp là 1 giây, statement có thể bị hủy **trước khi** log chờ dài xuất hiện.

### 29.2. pg_stat_database không đếm 55P03/57014 riêng

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

`deadlocks` đếm deadlock, không phải mọi timeout. `xact_rollback` gồm nhiều nguyên nhân rollback.

### 29.3. Ghi SQLSTATE theo operation

Một hệ thống có thể theo dõi:

~~~text
db_error_total{operation="reserve_stock", sqlstate="55P03"}
db_error_total{operation="orders_report", sqlstate="57014"}
db_transaction_duration_seconds{operation="checkout"}
db_retry_attempts_total{operation="reserve_stock"}
~~~

Đây là tên metrics minh họa. Không đưa email, account ID hoặc giá trị nhạy cảm vào metrics labels có cardinality cao.

### 29.4. Kết hợp số lỗi với impact

Điều quan trọng không chỉ là bao nhiêu timeout, mà là:

- Tỷ lệ request thất bại sau retry.
- P95/P99 latency.
- Số connection đang chờ.
- Thời lượng transaction.
- Tần suất blocker idle.
- Số deadlocks và serialization failures.
- Tác động với tính đúng của dữ liệu.

## 30. Những trường hợp thực tế

### 30.1. DDL chờ lock khi deploy

Migration cố lấy ACCESS EXCLUSIVE lock trong giờ cao điểm. `lock_timeout` ngắn giúp migration fail fast thay vì kéo dài hàng đợi lock. Nhưng vẫn cần kế hoạch rollback/retry và đánh giá lock mode của từng DDL.

### 30.2. Một transaction idle giữ hàng nóng

Một request cập nhật SKU rồi đợi service ngoài. Những request khác bị lock_timeout. Sửa đúng là rút ngắn transaction hoặc tách external call; tăng ngưỡng chờ có thể làm tải xấu đi.

### 30.3. Báo cáo bị statement_timeout

Một query báo cáo có nhiều JOIN/aggregation cần 30 giây nhưng role đang có statement_timeout 5 giây. Không nhất thiết là lock issue. Cần xem query plan và cân nhắc role/report timeout riêng.

### 30.4. Queue worker tranh chấp job

Nếu các worker được phép xử lý bất kỳ job sẵn sàng nào, `FOR UPDATE SKIP LOCKED` có thể giảm chờ hàng bận. Nếu phải xử lý một job xác định, dùng NOWAIT hoặc lock_timeout rõ hơn.

### 30.5. JDBC báo timeout nhưng backend còn hoạt động

Timeout client không bảo đảm server nhận cancel ngay. Theo dõi driver, connection state, pg_stat_activity và transaction cleanup; không chỉ tăng socket timeout.

### 30.6. Migration chạy trong transaction không thích hợp

`CREATE INDEX CONCURRENTLY` không chạy trong explicit transaction block. Cần cấu hình timeout và luồng migration phù hợp chứ không áp dụng một template BEGIN/SET LOCAL cho mọi lệnh.

## 31. Những hiểu lầm thường gặp

### 31.1. “lock_timeout là thời gian chạy tối đa của query”

Sai. Nó giới hạn thời gian **chờ lấy lock**.

### 31.2. “statement_timeout chỉ tính CPU”

Sai. Nó tính thời gian xử lý statement trên server, bao gồm chờ lock.

### 31.3. “lock_timeout 500ms nghĩa tổng mọi chờ khóa không vượt 500ms”

Sai. Mỗi lần đợi lấy lock được xét riêng.

### 31.4. “statement_timeout 2s nghĩa transaction chỉ chạy tối đa 2s”

Sai. Nó tính theo statement.

### 31.5. “Một transaction đã có lock sẽ bị lock_timeout tự nhả sau 500ms”

Sai. Không có giới hạn hold như vậy.

### 31.6. “Mọi SELECT đều không bao giờ bị lock”

Sai. SELECT có thể chờ table lock xung đột với ACCESS EXCLUSIVE.

### 31.7. “UPDATE luôn chặn mọi SELECT trên cùng bảng”

Sai. MVCC và lock modes cho phép nhiều đọc/ghi đồng thời.

### 31.8. “Đặt lock_timeout >= statement_timeout để phân biệt lỗi khóa”

Thường không có ích vì statement_timeout có thể hết trước.

### 31.9. “SET LOCAL trong autocommit tác động tới request sau”

Sai. SET LOCAL cần transaction scope phù hợp.

### 31.10. “RESET chắc chắn trả về 0”

Sai. Có thể trở về default do role/database đặt.

### 31.11. “SET ở connection pool không ảnh hưởng request sau”

Sai nếu session SET không được reset.

### 31.12. “55P03 và 57014 là cùng một lỗi”

Sai. Chúng phản ánh các nguyên nhân/cơ chế hủy khác nhau.

### 31.13. “Mọi 57014 chắc chắn do statement_timeout”

Sai. Query canceled có thể do client hoặc administrator cancel.

### 31.14. “deadlock_timeout hủy mọi lock wait quá hạn”

Sai. Nó liên quan tới kiểm tra deadlock, không phải giới hạn chờ lock bình thường.

### 31.15. “NOWAIT và lock_timeout hoàn toàn giống nhau”

Sai. NOWAIT yêu cầu fail fast cho các lock requests hỗ trợ; lock_timeout cho chờ có giới hạn.

### 31.16. “SKIP LOCKED phù hợp mọi truy vấn”

Sai. Nó thay đổi tập hàng được xử lý và không phù hợp nếu cần chính xác một hàng.

### 31.17. “Timeout một statement trong BEGIN không ảnh hưởng các statement trước”

Transaction có thể rơi vào trạng thái aborted và các thay đổi trước đó chưa được commit sẽ rollback.

### 31.18. “RETURNING thành công nghĩa là cả transaction đã commit”

Sai. Chỉ COMMIT thành công mới xác nhận kết quả transaction.

### 31.19. “Cứ tăng timeout là giảm rủi ro”

Sai. Có thể chỉ tăng p99 latency, connection usage và hàng đợi lock.

### 31.20. “Không nhìn thấy blocker sau khi timeout nghĩa là không từng có blocker”

Sai. Lock wait có thể đã kết thúc trước khi lấy mẫu.

### 31.21. “pg_locks là bảng lịch sử mọi lock timeouts”

Sai. Nó hiển thị trạng thái lock hiện tại.

### 31.22. “HTTP 504 có nghĩa PostgreSQL đã rollback”

Sai. Cần biết cancel, driver, session và commit state.

### 31.23. “Timeout thay được điều kiện tồn kho >= 0”

Sai. Timeout kiểm soát thời gian, không bảo vệ mọi bất biến dữ liệu.

## 32. Bài tập thực hành

### Bài 1 — Phép đo

Một SELECT mất 8 giây vì sort, không chờ lock. `lock_timeout='500ms'` có tự hủy vì chạy lâu không?

**Gợi ý:** Không; statement_timeout mới là công cụ đo tổng câu SQL.

### Bài 2 — Row lock 3 giây

T1 giữ row lock trong 3 giây. T2 có lock_timeout='400ms' và statement_timeout='5s'. SQLSTATE kỳ vọng?

**Đáp án:** 55P03.

### Bài 3 — Statement ngắn hơn

T2 chờ lock 3 giây, lock_timeout='5s', statement_timeout='600ms'. SQLSTATE kỳ vọng?

**Đáp án:** 57014.

### Bài 4 — Nhiều lock waits

Ba lần chờ lock 400ms, lock_timeout=500ms. Có chắc lock_timeout hủy vì tổng 1,2 giây?

**Gợi ý:** Không.

### Bài 5 — Đơn vị

`SET statement_timeout = 5` là 5ms hay 5s?

**Đáp án:** 5ms.

### Bài 6 — Giá trị 0

Đặt `lock_timeout = 0` có làm mọi yêu cầu lock thành NOWAIT không?

**Đáp án:** Không; tắt lock timeout.

### Bài 7 — SET LOCAL

Vì sao SET LOCAL có ích hơn SET session trong connection pool cho một transaction?

**Gợi ý:** Cấu hình kết thúc theo transaction, giảm rủi ro leak.

### Bài 8 — RESET

RESET có luôn trả về 0 không?

**Gợi ý:** Không, trở về default hiệu lực.

### Bài 9 — Lab pg_sleep

`SELECT pg_sleep(2)` với statement_timeout 500ms thường báo gì?

**Đáp án:** 57014.

### Bài 10 — Autocommit

Một statement bị timeout ngoài explicit BEGIN, connection còn hợp lệ. Có thể chạy SELECT tiếp không?

**Gợi ý:** Thường có thể.

### Bài 11 — Trong BEGIN

Một SELECT timeout giữa transaction. Muốn tiếp tục transaction mới, cần làm gì?

**Đáp án:** ROLLBACK trước khi bắt đầu mới.

### Bài 12 — Idle blocker

Phiên A đang `idle in transaction` giữ row lock. Timeout nào nhắm vào session A nếu nó idle quá lâu?

**Đáp án:** idle_in_transaction_session_timeout.

### Bài 13 — DDL

Tại sao lock_timeout ngắn hữu ích cho một số migration ALTER TABLE?

**Gợi ý:** Fail fast thay vì chờ lock mạnh quá lâu.

### Bài 14 — CREATE INDEX CONCURRENTLY

Có thể chạy trong explicit BEGIN không?

**Đáp án:** Không.

### Bài 15 — ACCESS EXCLUSIVE

T1 LOCK TABLE notes ACCESS EXCLUSIVE; T2 SELECT COUNT(*) có thể bị block không?

**Đáp án:** Có.

### Bài 16 — SHOW

Viết SQL xem timeout hiệu lực:

~~~sql
SHOW lock_timeout;
SHOW statement_timeout;
~~~

### Bài 17 — pg_settings

Cột nào giúp biết nguồn cấu hình của tham số?

**Gợi ý:** `source`.

### Bài 18 — pg_stat_activity

Giá trị `wait_event_type='Lock'` biểu thị điều gì?

**Gợi ý:** Backend đang chờ một đối tượng khóa.

### Bài 19 — Blocking PIDs

Hàm nào trả danh sách PID đang chặn một backend?

**Đáp án:** `pg_blocking_pids(pid)`.

### Bài 20 — pg_locks

Cột nào cho biết lock request đã được cấp?

**Đáp án:** `granted`.

### Bài 21 — NOWAIT

Một ứng dụng cần đúng SKU đang bị khóa và không muốn chờ. Cân nhắc NOWAIT hay SKIP LOCKED?

**Gợi ý:** NOWAIT để phát hiện contention trên đúng SKU.

### Bài 22 — SKIP LOCKED

Một queue worker nhận bất kỳ job chưa khóa. Cơ chế nào phù hợp?

**Gợi ý:** FOR UPDATE SKIP LOCKED cùng transaction protocol.

### Bài 23 — Deadlock

Hai transaction giữ A và B theo thứ tự đảo ngược. SQLSTATE phổ biến?

**Đáp án:** 40P01.

### Bài 24 — Log lock waits

`log_lock_waits` có tự hủy query không?

**Đáp án:** Không; nó phục vụ logging.

### Bài 25 — Metrics

`pg_stat_database.deadlocks` có phải bộ đếm mọi 55P03 không?

**Đáp án:** Không.

### Bài 26 — Retry

Khi 55P03 vì một hot row, có nên retry vô hạn ngay lập tức không?

**Gợi ý:** Không, dùng bounded retries/backoff/deadline.

### Bài 27 — Client deadline

HTTP timeout 1s và statement_timeout 10s. Database có chắc tự hủy SQL trước HTTP 504 không?

**Đáp án:** Không.

### Bài 28 — Transaction nhiều câu

Ba SELECT mỗi câu 1,5s dưới statement_timeout 2s. Tổng transaction có thể vượt 2s không?

**Đáp án:** Có.

### Bài 29 — Invariant

Viết UPDATE giảm stock 3 đơn vị chỉ khi còn đủ:

~~~sql
UPDATE timeout_lab.inventory
SET stock = stock - 3
WHERE sku = 'BOOK-001'
  AND stock >= 3
RETURNING stock;
~~~

### Bài 30 — Idempotency

Vì sao client retry tạo order sau network timeout cần idempotency key?

**Gợi ý:** Có thể request trước đã commit, tránh tạo trùng.

### Bài 31 — Default role

ALTER ROLE đặt statement_timeout mới có chắc thay ngay mọi connection pool đang mở không?

**Gợi ý:** Không; cần xét reconnect/session config.

### Bài 32 — Theo dõi nguyên nhân

Một request nhận 57014. Bạn cần phân biệt những nhóm nguyên nhân nào?

**Gợi ý:** Lock wait, thực thi nặng, I/O, function delay và cancel từ nguồn khác.

### Bài 33 — Query tốt vẫn bị khóa

Một UPDATE có index tìm đúng hàng trong 1ms nhưng T1 giữ row lock trong 10s. Index có xóa contention không?

**Đáp án:** Không.

### Bài 34 — Lock hold

T1 giữ lock 30s nhưng lock_timeout=500ms ở T1. Lock của T1 tự nhả sau 500ms không?

**Đáp án:** Không.

### Bài 35 — Đề xuất cấu hình

Giả sử OLTP update nhanh, bạn có thể thử lock_timeout 300ms, statement_timeout 3s. Hãy giải thích hai budget khác nhau và cách đo để điều chỉnh.

**Gợi ý:** Một cái giới hạn chờ khóa, một cái giới hạn toàn câu SQL; đo latency, contention, retries và lỗi thực tế.

## 33. Bảng ghi nhớ nhanh

| Nhu cầu | PostgreSQL hoặc cách tiếp cận |
|---|---|
| Giới hạn chờ lấy lock | `lock_timeout` |
| Giới hạn toàn statement | `statement_timeout` |
| Xem cấu hình | `SHOW lock_timeout; SHOW statement_timeout;` |
| Không đặt giới hạn tương ứng | `SET ... = 0` |
| Đặt tạm trong transaction | `SET LOCAL ...` |
| Đặt session | `SET ...` |
| Trở về default hiệu lực | `RESET ...` |
| Đặt default role | `ALTER ROLE ... SET ...` |
| Đặt default database | `ALTER DATABASE ... SET ...` |
| Lỗi chờ lock quá lâu | `55P03` |
| Lỗi query canceled | `57014` |
| Lỗi deadlock | `40P01` |
| Phát hiện một row đang khóa, không muốn chờ | `FOR UPDATE NOWAIT` |
| Bỏ qua hàng đang khóa trong queue | `FOR UPDATE SKIP LOCKED` |
| Giới hạn idle trong transaction | `idle_in_transaction_session_timeout` |
| Giới hạn transaction toàn phần | `transaction_timeout` nếu phiên bản hỗ trợ |
| Mốc kiểm tra deadlock | `deadlock_timeout` |
| Log chờ lock dài | `log_lock_waits` |
| Theo dõi backend | `pg_stat_activity` |
| Tìm blocker | `pg_blocking_pids(pid)` |
| Quan sát lock mode | `pg_locks` |
| Phân tích query plan | `EXPLAIN` |
| Timeout trong explicit transaction | Rollback hoặc xử lý savepoint phù hợp |
| Retry khi lock contention tạm thời | Có giới hạn, backoff, kiểm tra lại điều kiện |
| Timeout từ JDBC/HTTP | Khác timeout server, cần phối hợp deadline |
| Thao tác có side effect ngoài DB | Idempotency/outbox/reconciliation |

---

## Kết luận

**`lock_timeout` và `statement_timeout` giải quyết hai vấn đề khác nhau.** `lock_timeout` giới hạn **mỗi lần phải chờ để lấy một lock**, còn `statement_timeout` giới hạn **toàn thời gian xử lý câu SQL trên PostgreSQL**, bao gồm cả thời gian chờ khóa. Khi dùng cùng nhau, thường nên đặt lock_timeout **nhỏ hơn** statement_timeout để một statement không đợi lock quá lâu nhưng vẫn có thời gian thực thi bình thường sau khi lấy lock.

Lỗi **`55P03`** thường phản ánh lock-not-available/lock timeout, còn **`57014`** phản ánh query-canceled, trong đó có statement timeout. Timeout ở session đang chờ **không tự hủy transaction khác đang giữ khóa**, và cả hai tham số đều **không phải deadline cho toàn transaction**. Trong explicit transaction, một statement bị timeout thường khiến transaction thất bại và cần rollback trước khi thử lại.

Khi triển khai, nên sử dụng **SET LOCAL** để giữ phạm vi timeout theo transaction, kết hợp **pg_stat_activity**, **pg_blocking_pids** và **pg_locks** để tìm blocker, **EXPLAIN** để xử lý execution chậm, cùng **idle_in_transaction_session_timeout** để hạn chế session giữ transaction bỏ quên. Với concurrency cao, retry phải có giới hạn và idempotency; với migrations, cần chọn timeout phù hợp cho từng loại DDL và kế hoạch rollback.

Nguyên tắc quan trọng nhất: **trước khi tăng timeout, hãy xác định câu SQL đang chờ khóa hay đang thực sự chạy lâu; trước khi retry, hãy xác nhận transaction cũ đã kết thúc và điều kiện nghiệp vụ vẫn còn hợp lệ**. Khi phân biệt đúng hai bộ đếm, hệ thống có thể fail fast ở những chỗ cần thiết mà vẫn để các câu lệnh hữu ích hoàn thành.
