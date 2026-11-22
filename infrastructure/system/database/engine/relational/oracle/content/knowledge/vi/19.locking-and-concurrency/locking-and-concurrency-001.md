# Khóa dòng, khóa bảng, enqueue và latch/mutex trong Oracle Database

Khi nhiều session cùng đọc và cập nhật dữ liệu, Oracle Database phải điều phối quyền truy cập để tránh ghi đè ngoài ý muốn, giữ tính nhất quán và bảo vệ các cấu trúc nội bộ. Oracle sử dụng nhiều cơ chế đồng bộ khác nhau. Trong đó, cần phân biệt rõ:

- **Row lock (khóa dòng):** bảo vệ một hàng dữ liệu được transaction thay đổi hoặc khóa tường minh.
- **Table lock (khóa bảng):** điều phối các thao tác ở mức bảng; DML thường tự lấy table lock ở chế độ cho phép nhiều session cùng sửa các hàng khác nhau.
- **Enqueue:** cơ chế khóa có hàng đợi dùng để điều phối quyền truy cập vào tài nguyên như transaction (`TX`) hoặc bảng (`TM`).
- **Latch và mutex:** cơ chế đồng bộ nội bộ, bảo vệ các cấu trúc trong bộ nhớ dùng chung của Oracle, ví dụ shared pool, library cache hoặc buffer cache.

Các khái niệm này liên quan với nhau nhưng không thể thay thế cho nhau. Một session chờ `enq: TX - row lock contention` thường đang đợi transaction khác nhả khóa trên dữ liệu; một session chờ latch hoặc mutex thường đang đợi quyền truy cập một cấu trúc nội bộ trong SGA. `COMMIT` có thể giải phóng row lock, nhưng không phải cách xử lý chung cho mọi loại contention.

## 1. Vì sao database cần khóa và cơ chế đồng bộ?

Giả sử hai session cùng cập nhật số dư một tài khoản:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;
```

Nếu cả hai transaction cùng đọc một giá trị cũ và ghi đè lên nhau mà không có điều phối, một cập nhật có thể làm mất kết quả của cập nhật kia. Đây là dạng vấn đề thường được gọi là *lost update*.

Oracle dùng khóa để điều phối các thao tác ghi xung đột. Khi một transaction thay đổi một hàng, transaction đó giữ row lock cho tới khi commit hoặc rollback. Transaction khác muốn thay đổi cùng hàng phải chờ transaction đang giữ khóa kết thúc, trừ khi sử dụng một chiến lược ứng dụng khác.

Ngoài dữ liệu bảng, Oracle còn có cấu trúc nội bộ trong SGA được nhiều process truy cập đồng thời. Những cấu trúc này cần cơ chế đồng bộ ngắn hạn như latch và mutex. Mục tiêu của chúng là bảo vệ bộ nhớ dùng chung, không phải khóa một hàng nghiệp vụ.

```text
                 Nhiều session/process
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Truy cập dữ liệu          Truy cập SGA
             |                       |
             v                       v
       Row lock / TM lock        Latch / Mutex
       qua enqueue              đồng bộ nội bộ
             |                       |
             v                       v
       Bảo vệ hàng/bảng         Bảo vệ cấu trúc bộ nhớ
```

## 2. Row lock: khóa ở mức hàng dữ liệu

**Row lock** là khóa mà Oracle sử dụng để bảo vệ các hàng bị thay đổi hoặc được khóa tường minh trong transaction. Các thao tác DML như `UPDATE` và `DELETE` khóa những hàng bị tác động; `SELECT ... FOR UPDATE` yêu cầu khóa hàng để ứng dụng có thể đọc rồi cập nhật một cách có kiểm soát.

### 2.1. UPDATE khóa những hàng được cập nhật

```sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = 101;
```

Oracle khóa hàng nhân viên có `EMPLOYEE_ID = 101` trong transaction hiện tại. Một session khác muốn cập nhật hoặc khóa cùng hàng sẽ phải chờ nếu khóa đang được giữ. Session khác vẫn có thể cập nhật hàng khác trong cùng bảng.

### 2.2. DELETE khóa hàng bị xóa

```sql
DELETE FROM employees
WHERE employee_id = 101;
```

Hàng bị xóa được khóa cho tới khi transaction kết thúc. Trước khi commit, transaction khác không thể coi việc xóa chưa commit như một thay đổi đã xác nhận; Oracle sử dụng read consistency để phục vụ truy vấn.

### 2.3. INSERT và row lock

Khi insert một hàng mới, transaction sở hữu thay đổi chưa commit đó. Session khác không nhìn thấy hàng mới qua truy vấn thông thường cho tới khi insert được commit. Nếu một transaction khác cố insert cùng khóa duy nhất đang được transaction đầu tạo nhưng chưa commit, nó có thể phải chờ transaction đầu kết thúc để xác định kết quả vi phạm unique constraint hay không.

Vì vậy, chờ enqueue `TX` không phải lúc nào cũng chỉ là hai session cùng `UPDATE` một row đã tồn tại. TX enqueue còn tham gia điều phối một số tình huống cạnh tranh transaction khác, ví dụ xung đột khóa duy nhất.

### 2.4. Row lock được giữ tới COMMIT hoặc ROLLBACK

```sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = 101;

-- Row lock vẫn được giữ tại đây.

COMMIT;
-- Hoặc ROLLBACK;
```

Khóa hàng được giải phóng khi transaction commit hoặc rollback. Chỉ chạy xong statement chưa đủ để giải phóng row lock nếu transaction vẫn mở.

### 2.5. SELECT thông thường không khóa hàng

Trong Oracle, truy vấn `SELECT` thông thường sử dụng read consistency và không tự lấy row lock để ngăn session khác cập nhật dữ liệu.

```sql
SELECT employee_id, salary
FROM employees
WHERE employee_id = 101;
```

Truy vấn này không khóa hàng nhân viên. Session khác có thể cập nhật hàng trong lúc session hiện tại đang đọc; Oracle cung cấp phiên bản dữ liệu nhất quán theo thời điểm đọc của câu truy vấn.

Nếu ứng dụng cần đọc một hàng rồi giữ quyền ưu tiên cập nhật hàng đó, có thể dùng `SELECT ... FOR UPDATE`.

## 3. SELECT FOR UPDATE: đọc và khóa hàng tường minh

`SELECT ... FOR UPDATE` khóa các hàng được chọn để session hiện tại có thể xử lý chúng trước khi transaction kết thúc.

```sql
SELECT employee_id, salary
FROM employees
WHERE employee_id = 101
FOR UPDATE;
```

Session giữ khóa trên hàng được chọn tới khi `COMMIT` hoặc `ROLLBACK`. Session khác muốn cập nhật hoặc lấy `FOR UPDATE` trên cùng hàng phải chờ hoặc áp dụng tùy chọn chờ phù hợp.

### 3.1. Đọc rồi cập nhật trong cùng transaction

Ví dụ ứng dụng muốn đọc trạng thái đơn hàng, kiểm tra rồi chuyển trạng thái:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 9001
FOR UPDATE;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 9001;

COMMIT;
```

Khóa được giữ giữa câu `SELECT FOR UPDATE` và câu `UPDATE`, nên transaction khác không thể đồng thời sửa cùng hàng theo cách xung đột. Nếu kiểm tra nghiệp vụ thất bại, rollback để nhả khóa.

### 3.2. OF chỉ định bảng được khóa trong truy vấn join

Trong truy vấn có nhiều bảng, mệnh đề `OF` có thể chỉ định cột thuộc bảng nào cần khóa:

```sql
SELECT o.order_id,
       o.status,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_id = 9001
FOR UPDATE OF o.status;
```

`OF o.status` xác định bảng `ORDERS` là bảng cần khóa; nó **không có nghĩa chỉ khóa riêng cột STATUS**. Row lock bảo vệ hàng của bảng được chỉ định, không phải khóa từng cột. Nếu không chỉ định `OF`, Oracle có thể khóa các hàng thuộc các bảng có thể khóa trong truy vấn theo quy tắc của `FOR UPDATE`.

### 3.3. NOWAIT: không chờ khóa

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 9001
FOR UPDATE NOWAIT;
```

Nếu hàng đang bị session khác khóa, câu lệnh không chờ mà trả lỗi ngay (thường là `ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired`). Ứng dụng có thể báo người dùng thử lại hoặc xử lý theo nghiệp vụ.

### 3.4. WAIT n: chờ tối đa một khoảng thời gian

```sql
SELECT order_id, status
FROM orders
WHERE order_id = 9001
FOR UPDATE WAIT 5;
```

Session chờ tối đa 5 giây để lấy khóa. Nếu hết thời gian mà tài nguyên vẫn bận, Oracle trả lỗi timeout. Số giây phải được chọn theo SLA và thời gian xử lý của ứng dụng; không đặt quá dài khiến request giữ connection mà không làm được việc.

### 3.5. SKIP LOCKED: bỏ qua hàng đang bị khóa

```sql
SELECT job_id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` bỏ qua những hàng đang bị transaction khác khóa và tiếp tục tìm hàng khác có thể khóa. Đây là mẫu hữu ích cho nhiều worker cùng lấy việc từ một queue, vì worker này có thể xử lý job khác thay vì chờ job đang được worker khác giữ.

Ứng dụng thường thực hiện trong cùng transaction:

1. Chọn một hoặc một nhóm job `READY` bằng `FOR UPDATE SKIP LOCKED`.
2. Cập nhật trạng thái job thành `RUNNING` hoặc ghi nhận worker nhận việc.
3. Commit để xác nhận việc nhận job.
4. Xử lý job theo cơ chế phù hợp; khi hoàn thành, cập nhật trạng thái trong transaction riêng.

`SKIP LOCKED` không tự bảo đảm job được xử lý đúng một lần trong mọi tình huống. Cần có trạng thái, lease/timeout, retry và idempotency để phục hồi khi worker chết sau khi nhận việc.

### 3.6. Giới hạn của FOR UPDATE

Không phải mọi câu SELECT đều có thể thêm `FOR UPDATE`. Oracle đặt các hạn chế với truy vấn có `DISTINCT`, group function, `GROUP BY`, set operator và một số dạng view/subquery. Khi cần khóa dữ liệu đầu vào cho một phép tổng hợp, hãy xác định rõ bảng/hàng nguồn và thực hiện truy vấn khóa phù hợp thay vì thêm `FOR UPDATE` vào một truy vấn tổng hợp không được hỗ trợ.

## 4. Table lock: khóa ở mức bảng

Oracle sử dụng **table lock** để điều phối những thao tác cần quyền truy cập ở mức đối tượng bảng. Table lock không đồng nghĩa với việc toàn bộ hàng trong bảng đều bị khóa khỏi mọi truy cập. Một số chế độ cho phép nhiều session cùng đọc và DML trên các hàng khác nhau.

### 4.1. DML tự lấy Row Exclusive table lock

Khi session thực hiện DML như `INSERT`, `UPDATE`, `DELETE` hoặc `MERGE`, Oracle thường tự lấy table lock ở chế độ **Row Exclusive (RX)** trên bảng bị thay đổi, cùng các row lock cần thiết.

```sql
UPDATE employees
SET salary = salary + 100
WHERE employee_id = 101;
```

Trong lúc transaction chưa kết thúc:

- Session giữ table lock RX trên `EMPLOYEES`.
- Hàng nhân viên 101 được khóa ở mức row.
- Session khác vẫn có thể DML trên hàng khác của bảng.
- Session khác có thể bị chặn nếu yêu cầu table lock ở mode xung đột với RX, ví dụ `LOCK TABLE ... IN SHARE MODE`.

### 4.2. Oracle không tự nâng hàng loạt row lock thành table lock độc quyền

Oracle không thực hiện lock escalation theo kiểu tự động chuyển hàng nghìn row lock thành một table lock độc quyền chỉ vì transaction cập nhật nhiều hàng. DML vẫn sử dụng table-level DML lock ở mode phù hợp và row locks trên các hàng bị tác động.

Điều này giúp các transaction khác tiếp tục cập nhật những hàng không xung đột, ngay cả khi một transaction đang sửa nhiều hàng trong cùng bảng. Dù vậy, transaction cập nhật quá nhiều hàng vẫn có thể gây nhiều undo/redo, giữ nhiều khóa và làm session khác chờ trên các hàng cụ thể.

## 5. Năm chế độ table lock trong Oracle

Oracle cung cấp năm chế độ table lock thường được mô tả như sau:

| Chế độ | Viết tắt | Mode trong V$LOCK | Ý nghĩa khái quát |
|---|---|---:|---|
| Row Share | RS | 2 | Cho phép truy cập đồng thời; thường được lấy bởi `SELECT FOR UPDATE` |
| Row Exclusive | RX | 3 | Cho phép nhiều transaction DML đồng thời trên các hàng khác nhau; DML tự lấy mode này |
| Share | S | 4 | Cho phép truy vấn đồng thời nhưng hạn chế DML từ transaction khác |
| Share Row Exclusive | SRX | 5 | Cho phép đọc; hạn chế transaction khác lấy các mode DML/share xung đột |
| Exclusive | X | 6 | Khóa bảng ở mức mạnh nhất; ngăn các table lock khác không tương thích |

`V$LOCK.LMODE` và `V$LOCK.REQUEST` dùng số mode. Giá trị 0 biểu thị không giữ/không yêu cầu mode; các giá trị 2–6 tương ứng các mode trên.

### 5.1. Khả năng tương thích tổng quát

Bảng dưới thể hiện tính tương thích cơ bản giữa các table lock mode của Oracle. `Y` nghĩa là có thể cùng tồn tại; `N` nghĩa là xung đột. Mode 1 là Null lock, tương thích với mọi mode.

| Mode đang giữ \ Mode yêu cầu | Null (1) | RS (2) | RX (3) | S (4) | SRX (5) | X (6) |
|---|---:|---:|---:|---:|---:|---:|
| Null (1) | Y | Y | Y | Y | Y | Y |
| RS (2) | Y | Y | Y | Y | Y | N |
| RX (3) | Y | Y | Y | N | N | N |
| S (4) | Y | Y | N | Y | N | N |
| SRX (5) | Y | Y | N | N | N | N |
| X (6) | Y | N | N | N | N | N |

Hãy dùng ma trận như công cụ hiểu xung đột table lock, không suy luận rằng mọi row lock đều xung đột với mọi table lock. Row-level lock và table-level lock có vai trò khác nhau.

### 5.2. Row Share (RS)

RS cho phép truy vấn và nhiều hoạt động đồng thời, nhưng ngăn một session khác lấy table lock độc quyền không tương thích. `SELECT ... FOR UPDATE` thường lấy table lock RS cùng row locks trên các hàng được chọn.

### 5.3. Row Exclusive (RX)

RX là mode được DML lấy tự động. Nhiều transaction có thể cùng giữ RX trên một bảng; xung đột thực tế trên cùng hàng được giải quyết bởi row lock/TX enqueue.

### 5.4. Share (S)

Share lock cho phép các session khác đọc bảng nhưng xung đột với Row Exclusive và một số mode mạnh hơn. Nó thường được lấy tường minh bằng `LOCK TABLE ... IN SHARE MODE` khi transaction cần bảo vệ trạng thái bảng khỏi DML của transaction khác trong một khoảng thời gian.

### 5.5. Share Row Exclusive (SRX)

SRX mạnh hơn S, cho phép session giữ khóa đọc và sửa bảng trong khi hạn chế các transaction khác lấy mode DML/share không tương thích. Chế độ này có thể làm giảm concurrency rõ rệt; chỉ dùng khi yêu cầu nghiệp vụ thật sự cần.

### 5.6. Exclusive (X)

Exclusive là mode table lock mạnh nhất. Nó ngăn các session khác lấy các table lock không tương thích; truy vấn thông thường vẫn có thể đọc dữ liệu theo read consistency, nhưng DML của session khác sẽ bị chặn cho tới khi khóa được nhả.

## 6. LOCK TABLE: khóa bảng tường minh

Cú pháp tổng quát:

```sql
LOCK TABLE table_name
IN [ROW SHARE | ROW EXCLUSIVE | SHARE | SHARE ROW EXCLUSIVE | EXCLUSIVE] MODE
    [NOWAIT | WAIT integer];
```

Ví dụ:

```sql
LOCK TABLE employees IN ROW EXCLUSIVE MODE;
```

hoặc:

```sql
LOCK TABLE employees IN SHARE MODE NOWAIT;
```

Khóa bảng được giữ tới `COMMIT` hoặc `ROLLBACK`. Nếu không chỉ định `NOWAIT`/`WAIT`, lệnh có thể chờ theo hành vi mặc định của Oracle cho đến khi khóa được cấp.

### 6.1. Khóa bảng không phải cách thay thế mặc định cho row lock

Ví dụ:

```sql
LOCK TABLE employees IN EXCLUSIVE MODE;
```

khóa ở mức bảng, làm các thao tác DML của session khác bị chặn trên bảng. Nếu mục tiêu chỉ là sửa một nhân viên, thông thường nên dùng `UPDATE ... WHERE employee_id = ...` hoặc `SELECT ... FOR UPDATE`, để transaction khác có thể tiếp tục làm việc trên các hàng không xung đột.

### 6.2. WAIT và NOWAIT với LOCK TABLE

```sql
LOCK TABLE employees IN SHARE MODE WAIT 10;
```

Lệnh chờ tối đa 10 giây để lấy table lock. Nếu không lấy được, Oracle trả lỗi timeout. Với `NOWAIT`, lỗi được trả ngay khi không thể lấy khóa.

### 6.3. Khóa nhiều bảng

Có thể khóa nhiều bảng trong một câu:

```sql
LOCK TABLE orders, order_items
IN SHARE ROW EXCLUSIVE MODE;
```

Nếu nhiều transaction khóa cùng nhiều bảng theo thứ tự khác nhau, có thể tạo tình huống chờ hoặc deadlock. Nên thống nhất thứ tự lấy khóa trong ứng dụng và chỉ khóa những đối tượng thật sự cần.

## 7. Enqueue: cơ chế khóa có hàng đợi

**Enqueue** là cơ chế đồng bộ có quản lý mode và hàng đợi, được Oracle dùng để kiểm soát truy cập đồng thời vào các tài nguyên cần bảo vệ. Enqueue có thể được giữ trong thời gian transaction hoặc trong thời gian cần thiết theo loại tài nguyên.

Hai loại enqueue quan trọng nhất khi phân tích DML là:

- **TX:** transaction enqueue, liên quan đến transaction và các tình huống chờ transaction khác kết thúc.
- **TM:** DML enqueue, liên quan đến khóa đối tượng bảng.

Enqueue được quản lý bởi lock manager của Oracle. Session yêu cầu một mode không tương thích với mode đang được giữ có thể phải xếp hàng chờ.

### 7.1. TX enqueue

TX đại diện cho khóa liên quan đến transaction. Khi transaction sửa hàng, Oracle ghi thông tin transaction vào cấu trúc block/row tương ứng. Session khác cần sửa cùng hàng có thể phải chờ transaction đang sở hữu thay đổi kết thúc.

Trong `V$LOCK`, TX enqueue được nhận diện bằng `TYPE = 'TX'`. `ID1` và `ID2` nhận diện transaction; chúng **không phải OBJECT_ID của bảng**. Không join TX `ID1` trực tiếp với `DBA_OBJECTS.OBJECT_ID` để tìm bảng bị khóa.

Một transaction có thể khóa nhiều hàng nhưng không có nghĩa `V$LOCK` hiển thị một TX enqueue riêng cho từng hàng. TX enqueue là cơ chế gắn với transaction; thông tin hàng cụ thể cần được điều tra thêm qua session wait information, SQL đang chạy, row wait fields và block data.

### 7.2. TM enqueue

TM là DML enqueue bảo vệ đối tượng bảng. Ví dụ DML trên bảng thường giữ TM mode Row Exclusive (mode 3). Trong `V$LOCK`, `TYPE = 'TM'`, `ID1` thường tương ứng `OBJECT_ID` của đối tượng được khóa.

TM lock không có nghĩa mọi hàng trong bảng đều bị khóa. Nó là table-level lock mode được phối hợp với row-level locks để cho phép các transaction cập nhật các hàng khác nhau đồng thời.

### 7.3. Enqueue wait event

Một số wait event có thể gặp:

| Wait event | Ý nghĩa thường gặp |
|---|---|
| `enq: TX - row lock contention` | Session chờ transaction khác nhả khóa liên quan đến hàng/xung đột transaction |
| `enq: TX - allocate ITL entry` | Session chờ có ITL slot phù hợp trong data block |
| `enq: TM - contention` | Session chờ table DML lock không tương thích |
| `enq: TX - index contention` | Một dạng contention liên quan đến transaction/index; cần xem nguyên nhân cụ thể và phiên bản |

Tên wait event giúp định hướng điều tra nhưng không đủ để kết luận nguyên nhân duy nhất. Hãy xem session blocker, SQL, object, transaction age và loại thao tác đang chạy.

## 8. Row lock được biểu diễn trong block: ITL và TX

Oracle lưu thông tin transaction liên quan đến các hàng trong data block. Một phần quan trọng là **Interested Transaction List (ITL)**. ITL entries trong block ghi nhận các transaction đang quan tâm/thay đổi hàng trong block, cùng thông tin cần thiết để Oracle xác định transaction và phục vụ read consistency.

Row header có thông tin liên hệ tới ITL entry tương ứng. Vì vậy, row lock không đơn giản là một object riêng biệt trong `V$LOCK` cho từng hàng. Khi session khác cần thay đổi một hàng đang được transaction chưa commit sở hữu, nó có thể phải đợi TX enqueue của transaction đó.

### 8.1. ITL slot là gì?

Một data block có số ITL entry giới hạn tại một thời điểm. Nếu nhiều transaction đồng thời muốn thay đổi các hàng nằm trong cùng block và không còn ITL entry có thể dùng, một session có thể chờ:

```text
enq: TX - allocate ITL entry
```

Đây không giống tình huống hai session cập nhật cùng một hàng. Nguyên nhân là block không còn ITL slot sẵn sàng cho transaction mới, hoặc các entry hiện có đang gắn với transaction chưa kết thúc.

### 8.2. INITRANS và PCTFREE

`INITRANS` quy định số ITL entry ban đầu được dành trong block cho segment/table hoặc index. Oracle có thể mở rộng ITL trong block khi còn không gian phù hợp. `PCTFREE` giữ lại một phần không gian block để hỗ trợ cập nhật hàng và các nhu cầu không gian khác.

Khi điều tra ITL contention, DBA có thể xem xét `INITRANS`, `PCTFREE`, mức độ đồng thời và phân bố dữ liệu. Không nên tăng `INITRANS` hoặc thay đổi storage parameter theo cảm tính; cần đo wait, kiểm tra block contention và thử nghiệm trên môi trường phù hợp.

## 9. Latch: đồng bộ ngắn hạn cho cấu trúc SGA

**Latch** là cơ chế đồng bộ nội bộ nhẹ được Oracle dùng để bảo vệ các cấu trúc dữ liệu trong bộ nhớ dùng chung (SGA). Latch thường được giữ trong thời gian rất ngắn để process có thể đọc hoặc thay đổi một cấu trúc nội bộ mà không bị process khác truy cập đồng thời theo cách gây hỏng dữ liệu.

Ví dụ các vùng/cấu trúc có thể liên quan đến latch:

- Shared pool và các cấu trúc quản lý SQL/cursor.
- Buffer cache và các chuỗi buffer.
- Một số cấu trúc quản lý bộ nhớ và tài nguyên nội bộ.

Latch không phải row lock hay table lock:

| Đặc điểm | Row/table lock | Latch |
|---|---|---|
| Mục đích | Điều phối truy cập dữ liệu/đối tượng database | Bảo vệ cấu trúc nội bộ trong SGA |
| Thời gian giữ | Có thể kéo dài đến COMMIT/ROLLBACK với transaction lock | Thường rất ngắn, trong critical section |
| Liên quan nghiệp vụ | Có thể gắn với hàng/bảng đang xử lý | Thường liên quan hoạt động nội bộ của Oracle |
| Giải phóng bằng COMMIT | Transaction lock được giải phóng khi commit/rollback | Không phải cơ chế giải phóng latch |
| Ví dụ chờ | `enq: TX - row lock contention` | `latch: shared pool`, `latch: cache buffers chains` |

### 9.1. Latch contention

Nếu nhiều process cạnh tranh cùng latch, một số process phải chờ hoặc thử lấy latch lại. Wait event có thể bắt đầu bằng `latch:`. Ví dụ:

- `latch: shared pool`: contention trên latch liên quan shared pool.
- `latch: cache buffers chains`: contention trên chuỗi buffer trong buffer cache.

Không nên xử lý latch contention bằng cách tìm một row lock rồi commit, vì nguyên nhân có thể nằm ở SQL pattern, hot block, parse workload hoặc hoạt động nội bộ khác.

### 9.2. Latch không bảo vệ một câu SQL trong suốt thời gian chạy

Một câu SQL có thể thực hiện nhiều bước và chỉ lấy latch trong các đoạn ngắn khi cần truy cập cấu trúc SGA. Latch không được giữ từ lúc câu SQL bắt đầu đến lúc transaction commit như một row lock. Vì vậy, một truy vấn chạy lâu không đồng nghĩa nó giữ một latch liên tục trong suốt thời gian đó.

## 10. Mutex: cơ chế đồng bộ nội bộ nhẹ hơn cho một số cấu trúc

**Mutex** (mutual exclusion) là cơ chế đồng bộ nội bộ được Oracle sử dụng để bảo vệ một số cấu trúc dùng chung, đặc biệt có các trường hợp liên quan library cache và cursor. Mutex cho phép kiểm soát cạnh tranh ở mức chi tiết hơn đối với một số tài nguyên so với các cơ chế latch truyền thống.

Mutex cũng không phải khóa hàng nghiệp vụ. Một session chờ mutex có thể đang đợi quyền truy cập/pin một cursor hoặc đối tượng trong library cache, chứ không phải chờ transaction khác commit một hàng trong bảng.

Một số wait event liên quan mutex/library cache có thể gặp tùy phiên bản và workload:

- `cursor: pin S wait on X`
- `library cache: mutex X`
- `library cache: mutex S`

Tên và cách hiển thị wait event có thể khác giữa các bản Oracle. Cần xem tài liệu phiên bản và dữ liệu chẩn đoán thực tế.

### 10.1. Nguyên nhân có thể dẫn đến mutex contention

Một số workload có thể gây cạnh tranh mutex:

- Nhiều session truy cập cùng cursor hoặc library cache object với tần suất cao.
- SQL bị hard parse quá nhiều do literal SQL khác nhau hoặc thiếu bind variable phù hợp.
- Cursor invalidation/reload thường xuyên.
- Một số pattern truy cập object/cursor gây tập trung cạnh tranh.

Đây là các hướng điều tra, không phải kết luận tự động. Khi thấy wait event mutex, cần xem SQL_ID, cursor, module/action, phiên bản, AWR/ASH (nếu được cấp phép) và tài liệu Oracle tương ứng.

## 11. So sánh row lock, table lock, enqueue, latch và mutex

| Cơ chế | Bảo vệ cái gì? | Thời gian/ranh giới | Ví dụ nhận diện |
|---|---|---|---|
| Row lock | Một hàng dữ liệu | Thường tới COMMIT/ROLLBACK | Transaction khác chờ sửa cùng hàng |
| Table lock | Đối tượng bảng theo mode | Thường tới COMMIT/ROLLBACK với DML/table lock | TM mode 3 (RX) |
| Enqueue | Tài nguyên cần điều phối bằng mode/hàng đợi; có thể là transaction hoặc bảng | Theo loại enqueue và transaction/resource | TX, TM; wait `enq: ...` |
| Latch | Cấu trúc nội bộ trong SGA | Critical section ngắn | `latch: shared pool` |
| Mutex | Một số cấu trúc nội bộ như library cache/cursor | Critical section ngắn | `library cache: mutex X` |

Enqueue là một cơ chế quản lý lock; TX/TM là các loại enqueue cụ thể. Row lock và table lock là khái niệm về phạm vi bảo vệ dữ liệu/đối tượng. Latch và mutex là các cơ chế đồng bộ nội bộ khác loại.

## 12. Deadlock: hai transaction chờ nhau

Deadlock xảy ra khi hai hoặc nhiều session giữ tài nguyên mà session khác cần, đồng thời chờ tài nguyên do session kia giữ. Ví dụ kinh điển:

**Session A:**

```sql
UPDATE lab_accounts
SET balance = balance - 10
WHERE account_id = 1;

-- Sau đó cố khóa account 2.
UPDATE lab_accounts
SET balance = balance + 10
WHERE account_id = 2;
```

**Session B:**

```sql
UPDATE lab_accounts
SET balance = balance - 20
WHERE account_id = 2;

-- Sau đó cố khóa account 1.
UPDATE lab_accounts
SET balance = balance + 20
WHERE account_id = 1;
```

Nếu A giữ khóa hàng 1 và chờ hàng 2, trong khi B giữ khóa hàng 2 và chờ hàng 1, hai transaction tạo vòng chờ. Oracle phát hiện deadlock và báo:

```text
ORA-00060: deadlock detected while waiting for resource
```

Oracle thường rollback statement tham gia deadlock ở một session để phá vòng chờ; **không nên giả định toàn bộ transaction của session đó đã tự rollback**. Ứng dụng cần xử lý lỗi, xác định trạng thái transaction và rollback toàn bộ nghiệp vụ nếu đó là yêu cầu.

### 12.1. Cách giảm nguy cơ deadlock

- Các luồng cập nhật nhiều hàng nên lấy khóa theo cùng một thứ tự, ví dụ account ID tăng dần.
- Giữ transaction ngắn; không chờ người dùng hoặc gọi dịch vụ mạng trong lúc đang giữ row lock.
- Cập nhật đúng tập hàng cần thiết, tránh khóa quá rộng.
- Dùng điều kiện cập nhật rõ ràng và index phù hợp để tránh quét/khóa ngoài dự kiến.
- Khi retry deadlock, retry toàn bộ đơn vị nghiệp vụ có kiểm soát và bảo đảm idempotency.

### 12.2. Deadlock khác lock wait

Nếu A giữ khóa và B chỉ chờ A, đó là lock wait, không nhất thiết deadlock. Deadlock cần có vòng phụ thuộc chờ. Oracle có thể tiếp tục cho B chờ đến khi A commit/rollback hoặc timeout theo cơ chế của câu lệnh/ứng dụng.

## 13. Các wait event thường gặp và cách phân biệt

| Wait event | Nhóm vấn đề | Hướng điều tra ban đầu |
|---|---|---|
| `enq: TX - row lock contention` | Transaction/row conflict | Tìm blocker, SQL cập nhật hàng, transaction chưa commit, unique key conflict |
| `enq: TM - contention` | Table DML lock conflict | Kiểm tra TM mode, DDL, `LOCK TABLE`, transaction giữ mode mạnh |
| `enq: TX - allocate ITL entry` | ITL trong data block | Kiểm tra hot block, INITRANS/PCTFREE, transaction đồng thời |
| `latch: cache buffers chains` | Latch/buffer cache | Tìm hot block, SQL truy cập tập trung, buffer contention |
| `latch: shared pool` | Latch/shared pool | Kiểm tra parse workload, shared pool pressure, SQL/cursor pattern |
| `cursor: pin S wait on X` | Cursor/library cache mutex-related wait | Kiểm tra cursor invalidation, parse/compile và session đang giữ pin |
| `library cache: mutex X` | Library cache mutex | Xem SQL/cursor/object, hard parse và hoạt động DDL |
| `buffer busy waits` | Buffer/block concurrency | Xác định segment/block và loại truy cập gây cạnh tranh |

Không gộp mọi wait event thành “database bị lock”. Cần xác định loại tài nguyên và cơ chế đồng bộ trước khi chọn cách xử lý.

## 14. Chẩn đoán session đang chờ khóa

Việc xem các dynamic performance view thường cần quyền phù hợp như `SELECT_CATALOG_ROLE` hoặc quyền trực tiếp trên view. Tài khoản ứng dụng thông thường không nên được cấp quyền rộng chỉ để chạy truy vấn chẩn đoán.

### 14.1. Xem session đang chờ và blocker

```sql
SELECT sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       blocking_session,
       blocking_instance,
       final_blocking_session,
       sql_id,
       seconds_in_wait
FROM v$session
WHERE blocking_session IS NOT NULL
   OR event LIKE 'enq:%'
ORDER BY seconds_in_wait DESC;
```

Các cột blocker giúp tìm session đang chặn. `BLOCKING_SESSION` có thể null tùy trạng thái wait, cấu hình hoặc loại wait; cần kết hợp thêm thông tin session và lock.

### 14.2. Xem enqueue đang giữ/yêu cầu

```sql
SELECT sid,
       type,
       id1,
       id2,
       lmode,
       request,
       ctime,
       block
FROM v$lock
WHERE type IN ('TX', 'TM')
ORDER BY type, id1, id2, sid;
```

Các cột quan trọng:

- `TYPE`: loại enqueue, ví dụ TX hoặc TM.
- `ID1`, `ID2`: định danh tài nguyên theo loại enqueue.
- `LMODE`: mode session đang giữ.
- `REQUEST`: mode session đang yêu cầu; khác 0 thường cho biết đang chờ lấy mode đó.
- `CTIME`: thời gian session giữ mode hiện tại hoặc chờ theo ngữ cảnh view.
- `BLOCK`: thông tin session đang chặn session khác theo cách biểu diễn của view.

Không diễn giải `ID1` giống nhau cho mọi `TYPE`. Với TM, `ID1` thường là `OBJECT_ID`; với TX, `ID1`/`ID2` nhận diện transaction.

### 14.3. Liên kết TM với object

```sql
SELECT l.sid,
       s.serial#,
       s.username,
       o.owner,
       o.object_name,
       o.object_type,
       l.lmode,
       l.request,
       l.ctime
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
LEFT JOIN dba_objects o
  ON o.object_id = l.id1
WHERE l.type = 'TM'
ORDER BY l.ctime DESC;
```

Truy vấn này dùng `ID1` để tra object cho TM lock. Không áp dụng join đó cho TX. Nếu không có quyền `DBA_OBJECTS`, DBA có thể dùng `ALL_OBJECTS`/`USER_OBJECTS` theo phạm vi quyền phù hợp.

### 14.4. Xem đối tượng có TM lock

```sql
SELECT lo.session_id,
       lo.oracle_username,
       lo.os_user_name,
       o.owner,
       o.object_name,
       o.object_type,
       lo.locked_mode
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.session_id, o.owner, o.object_name;
```

`V$LOCKED_OBJECT` hữu ích để xem đối tượng đang có DML lock. Nó không cung cấp một danh sách rowid đầy đủ cho mọi row lock đang được giữ.

### 14.5. Xem row wait information của session

Khi session đang chờ row lock, một số cột của `V$SESSION` có thể cung cấp thông tin row wait như `ROW_WAIT_OBJ#`, `ROW_WAIT_FILE#`, `ROW_WAIT_BLOCK#`, `ROW_WAIT_ROW#` (giá trị chỉ có ý nghĩa trong trạng thái wait phù hợp).

```sql
SELECT sid,
       serial#,
       event,
       row_wait_obj#,
       row_wait_file#,
       row_wait_block#,
       row_wait_row#,
       blocking_session,
       sql_id
FROM v$session
WHERE event = 'enq: TX - row lock contention';
```

Có thể dùng thông tin object/file/block/row để điều tra sâu hơn. Các cột row wait không phải lúc nào cũng được điền; đừng coi giá trị 0 hoặc null là bằng chứng chắc chắn không có row conflict.

## 15. Thực hành hai session: quan sát row lock

Các bài lab dùng bảng giả `LAB_LOCK_ACCOUNTS`. Chỉ thực hành trong schema **DEV/TEST** được cấp quyền và xác nhận đúng PDB/service. Không dùng tài khoản thật hoặc thử tạo deadlock trên bảng nghiệp vụ production.

### 15.1. Tạo bảng lab

```sql
CREATE TABLE lab_lock_accounts (
    account_id NUMBER PRIMARY KEY,
    owner_name VARCHAR2(80 CHAR) NOT NULL,
    balance    NUMBER(12, 2) NOT NULL
);

INSERT INTO lab_lock_accounts VALUES (1, 'Account A', 1000);
INSERT INTO lab_lock_accounts VALUES (2, 'Account B', 2000);
INSERT INTO lab_lock_accounts VALUES (3, 'Account C', 3000);
COMMIT;
```

### 15.2. Session A khóa một hàng

```sql
UPDATE lab_lock_accounts
SET balance = balance - 100
WHERE account_id = 1;
```

Không commit. Session A đang giữ row lock trên account 1.

### 15.3. Session B cập nhật cùng hàng

```sql
UPDATE lab_lock_accounts
SET balance = balance + 50
WHERE account_id = 1;
```

Session B phải chờ Session A kết thúc transaction. Trong khi đó, thử cập nhật hàng khác:

```sql
UPDATE lab_lock_accounts
SET balance = balance + 50
WHERE account_id = 2;
```

Hàng account 2 không bị session A khóa nên có thể được cập nhật độc lập, tùy các lock khác đang tồn tại.

### 15.4. Kết thúc transaction A

Trong Session A:

```sql
COMMIT;
```

Session B có thể tiếp tục sau khi khóa được giải phóng. Kiểm tra số dư và commit/rollback Session B theo ý định của bài lab.

### 15.5. Thử SELECT FOR UPDATE NOWAIT

Session A:

```sql
SELECT *
FROM lab_lock_accounts
WHERE account_id = 3
FOR UPDATE;
```

Giữ transaction mở. Session B:

```sql
SELECT *
FROM lab_lock_accounts
WHERE account_id = 3
FOR UPDATE NOWAIT;
```

Quan sát lỗi trả về ngay. Sau đó Session A `ROLLBACK` để giải phóng khóa.

### 15.6. Thử SKIP LOCKED

Session A khóa account 1:

```sql
SELECT *
FROM lab_lock_accounts
WHERE account_id = 1
FOR UPDATE;
```

Session B:

```sql
SELECT account_id, balance
FROM lab_lock_accounts
WHERE account_id IN (1, 2, 3)
ORDER BY account_id
FOR UPDATE SKIP LOCKED;
```

Session B bỏ qua account 1 đang bị khóa và có thể lấy account 2, 3. Sau đó rollback cả hai session.

## 16. Thực hành table lock và enqueue TM

### 16.1. Session A lấy table lock SHARE

```sql
LOCK TABLE lab_lock_accounts IN SHARE MODE;
```

Giữ transaction mở. Session A có table lock S trên bảng.

### 16.2. Session B thử DML

```sql
UPDATE lab_lock_accounts
SET balance = balance + 1
WHERE account_id = 1;
```

DML cần TM Row Exclusive (RX), xung đột với Share lock S đang được Session A giữ. Session B sẽ chờ.

### 16.3. Giải phóng khóa

Session A:

```sql
COMMIT;
```

Session B có thể tiếp tục. Quan sát `V$LOCK`/`V$SESSION` nếu có quyền phù hợp để thấy enqueue TM và trạng thái chờ.

## 17. Thực hành deadlock có kiểm soát

Chỉ thực hiện trong database lab riêng, với hai session do người học kiểm soát. Không thử tạo deadlock trên bảng dùng chung.

Session A:

```sql
UPDATE lab_lock_accounts
SET balance = balance - 10
WHERE account_id = 1;
```

Session B:

```sql
UPDATE lab_lock_accounts
SET balance = balance - 20
WHERE account_id = 2;
```

Sau khi mỗi session giữ khóa hàng riêng, Session A:

```sql
UPDATE lab_lock_accounts
SET balance = balance + 10
WHERE account_id = 2;
```

Session A chờ B. Tiếp theo Session B:

```sql
UPDATE lab_lock_accounts
SET balance = balance + 20
WHERE account_id = 1;
```

Session B chờ A, tạo vòng deadlock. Oracle phát hiện và trả `ORA-00060` cho một statement. Ghi nhận session/statement bị lỗi; sau đó kiểm tra transaction còn mở hay không và rollback rõ ràng ở cả hai session trước khi tiếp tục.

## 18. Phân biệt lock contention với latch/mutex contention

Khi một session chờ lâu, trước tiên đọc `EVENT` và `WAIT_CLASS` trong `V$SESSION` hoặc công cụ giám sát.

| Dấu hiệu | Hướng suy nghĩ |
|---|---|
| `enq: TX - row lock contention` | Có transaction khác đang giữ khóa liên quan hàng/transaction; tìm blocker và transaction chưa kết thúc |
| `enq: TM - contention` | Table DML lock mode xung đột; kiểm tra `LOCK TABLE`, DDL và transaction giữ TM |
| `enq: TX - allocate ITL entry` | Cạnh tranh ITL slot trong block; kiểm tra block nóng và cấu hình segment |
| `latch: ...` | Cạnh tranh latch trên cấu trúc SGA; điều tra SQL/workload và cấu trúc nội bộ liên quan |
| `... mutex ...` hoặc `cursor: pin ...` | Cạnh tranh mutex/library cache/cursor; kiểm tra parse, invalidation và SQL/cursor |
| `buffer busy waits` | Cạnh tranh truy cập buffer/block; không mặc định là row lock |

Không khuyến nghị kill session chỉ dựa trên một wait event. Trước hết xác định blocker, transaction age, SQL đang chạy, nghiệp vụ bị ảnh hưởng và khả năng rollback. Kill session có thể kích hoạt rollback dài, giữ tài nguyên trong lúc rollback và gây ảnh hưởng dây chuyền.

## 19. Các lỗi và hiểu lầm thường gặp

| Nhầm lẫn/triệu chứng | Cách hiểu đúng |
|---|---|
| SELECT thông thường khóa hàng | SELECT thông thường dùng read consistency, không tự khóa row |
| DML khóa toàn bộ bảng | DML lấy table lock mode RX và row locks trên hàng bị tác động; hàng khác vẫn có thể được sửa |
| Oracle nâng row lock thành table lock khi sửa nhiều hàng | Oracle không tự động lock escalation kiểu đó |
| TX enqueue luôn là một row lock cụ thể | TX là transaction enqueue; có nhiều nguyên nhân TX wait, không chỉ row conflict |
| TM lock nghĩa là mọi hàng của bảng đều bị khóa | TM là table-level DML lock mode; row locks điều phối xung đột hàng |
| V$LOCK có một dòng TX cho từng hàng | TX enqueue gắn với transaction; row lock information nằm trong data block/ITL |
| COMMIT giải quyết mọi loại contention | COMMIT nhả transaction locks; latch/mutex là đồng bộ nội bộ ngắn hạn |
| Latch và mutex giống row lock | Chúng bảo vệ cấu trúc SGA, không phải hàng nghiệp vụ |
| FOR UPDATE khóa riêng cột ghi trong OF | OF xác định bảng có hàng cần khóa; row lock khóa hàng, không khóa cột riêng |
| SKIP LOCKED bảo đảm job chỉ chạy đúng một lần | Cần trạng thái, retry, lease và idempotency ở tầng ứng dụng |
| ORA-00060 luôn rollback toàn transaction | Oracle rollback statement liên quan deadlock; ứng dụng cần xử lý transaction còn lại |
| ORA-00054 là deadlock | Đây thường là resource busy/NOWAIT/timeout, không nhất thiết có vòng chờ |
| Dùng LOCK TABLE luôn an toàn hơn SELECT FOR UPDATE | Table lock có phạm vi rộng và có thể giảm concurrency mạnh |
| Mọi TX wait đều do hai người sửa cùng row | TX wait cũng có thể liên quan unique key, ITL hoặc cơ chế transaction khác |

## 20. Checklist điều tra lock contention

Khi một request bị chờ khóa, hãy đi theo trình tự:

1. Xác định session chờ: SID, SERIAL#, SQL_ID, module/action, event, thời gian chờ.
2. Xác định blocker: `BLOCKING_SESSION`, session/instance tương ứng và transaction đang mở.
3. Xác định loại tài nguyên: TX, TM, ITL, latch, mutex hay buffer wait.
4. Nếu là TM, xác định object và lock mode; kiểm tra DDL hoặc `LOCK TABLE`.
5. Nếu là TX, xác định statement và hàng/unique key/ITL liên quan; xem transaction nào chưa commit.
6. Kiểm tra thời điểm bắt đầu transaction và vì sao ứng dụng giữ connection/lock lâu.
7. Xác định nghiệp vụ có thể retry, rollback hay cần thao tác bù.
8. Chỉ thay đổi index, INITRANS, PCTFREE, SQL hoặc code sau khi có bằng chứng về nguyên nhân và kiểm thử trên môi trường phù hợp.

## 21. Câu hỏi ôn tập

**Câu 1.** Row lock bảo vệ tài nguyên nào?

**Đáp án:** Một hàng dữ liệu bị transaction thay đổi hoặc được khóa tường minh, ví dụ bằng `SELECT FOR UPDATE`.

**Câu 2.** SELECT thông thường trong Oracle có tự lấy row lock không?

**Đáp án:** Không. SELECT thông thường dùng read consistency; muốn khóa hàng phải dùng cơ chế tường minh như `SELECT FOR UPDATE`.

**Câu 3.** DML tự lấy table lock mode nào?

**Đáp án:** Thông thường là Row Exclusive (RX, mode 3), đồng thời khóa các hàng bị tác động.

**Câu 4.** Hai session có thể cùng giữ RX trên một bảng không?

**Đáp án:** Có. RX tương thích với RX; xung đột trên cùng hàng được xử lý ở mức row/transaction.

**Câu 5.** `SELECT ... FOR UPDATE NOWAIT` làm gì khi hàng đang bị khóa?

**Đáp án:** Trả lỗi ngay thay vì chờ.

**Câu 6.** `SKIP LOCKED` phù hợp với tình huống nào?

**Đáp án:** Nhiều worker cùng lấy hàng công việc từ queue; mỗi worker bỏ qua hàng đang bị worker khác khóa và lấy hàng khác.

**Câu 7.** TX và TM enqueue khác nhau thế nào?

**Đáp án:** TX liên quan transaction và các tình huống chờ transaction; TM là DML enqueue bảo vệ đối tượng bảng.

**Câu 8.** Vì sao không join `V$LOCK.ID1` của TX trực tiếp với `DBA_OBJECTS.OBJECT_ID`?

**Đáp án:** TX ID1/ID2 nhận diện transaction, không phải object ID. Với TM, ID1 thường tương ứng object ID.

**Câu 9.** Latch/mutex khác row lock ở điểm nào?

**Đáp án:** Latch/mutex bảo vệ cấu trúc nội bộ trong SGA trong critical section ngắn; row lock bảo vệ hàng dữ liệu và thường được giữ tới commit/rollback.

**Câu 10.** `enq: TX - allocate ITL entry` có nhất thiết là hai session sửa cùng một hàng không?

**Đáp án:** Không. Nó thường cho biết block thiếu ITL entry có thể dùng cho transaction mới.

**Câu 11.** Oracle có tự động nâng hàng nghìn row lock thành exclusive table lock không?

**Đáp án:** Không có cơ chế lock escalation tự động như vậy; DML vẫn dùng table DML lock và row locks.

**Câu 12.** ORA-00060 có nghĩa gì?

**Đáp án:** Deadlock detected while waiting for resource. Oracle phá vòng chờ bằng cách rollback statement liên quan; ứng dụng phải xử lý transaction còn lại.

## Kết luận

**Row lock, table lock, enqueue, latch và mutex giải quyết các phạm vi đồng bộ khác nhau.** Row lock bảo vệ hàng dữ liệu; DML thường lấy thêm table lock RX để điều phối truy cập ở mức bảng; TX và TM là các loại enqueue thường gặp khi điều tra lock wait. Oracle không tự động nâng row lock thành exclusive table lock chỉ vì một transaction cập nhật nhiều hàng.

`SELECT FOR UPDATE` dùng để khóa hàng tường minh, với `NOWAIT`, `WAIT` hoặc `SKIP LOCKED` tùy cách ứng dụng muốn xử lý chờ. `LOCK TABLE` khóa đối tượng ở mode rộng hơn và cần dùng thận trọng. Latch và mutex bảo vệ cấu trúc nội bộ SGA trong thời gian ngắn, không phải khóa hàng nghiệp vụ và không được giải phóng bằng cách commit transaction. Khi chẩn đoán, hãy đọc đúng wait event, tìm blocker và phân biệt TX/TM/ITL với latch/mutex trước khi thay đổi SQL, schema hoặc cấu hình.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): read consistency, row locks và table locks.
- [Oracle Database 19c Concepts — Automatic Locks in DML Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): khóa tự động trong DML và các table lock mode.
- [Oracle Database 19c SQL Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `FOR UPDATE`, `NOWAIT`, `WAIT` và `SKIP LOCKED`.
- [Oracle Database 19c SQL Reference — LOCK TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LOCK-TABLE.html): cú pháp và mode của table lock.
- [Oracle Database 19c Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html): enqueue lock information.
- [Oracle Database 19c Reference — V$LOCKED_OBJECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCKED_OBJECT.html): đối tượng có DML lock.
- [Oracle Database 19c Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): session, wait event và blocking session.
- [Oracle Database 19c Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/index.html): chẩn đoán contention, latch và hiệu năng instance.
