# Thiếu chỉ mục hoặc kế hoạch thực thi thay đổi làm tăng tranh chấp

Chỉ mục (index) giúp database tìm dữ liệu mà không phải quét toàn bộ bảng hoặc một vùng dữ liệu quá rộng. Khi thiếu chỉ mục phù hợp, một câu truy vấn có thể phải đọc và xử lý nhiều dòng hơn mức cần thiết. Nếu truy vấn có thao tác ghi, locking read hoặc chạy ở isolation level cần bảo vệ phạm vi đọc, đường truy cập rộng có thể làm tăng số tài nguyên bị khóa, thời gian giữ lock và số transaction phải chờ.

Một vấn đề khác xuất hiện khi **execution plan thay đổi**. Cùng một câu SQL có thể trước đây dùng index seek, sau đó chuyển sang index scan hoặc table scan do thống kê, phân bố dữ liệu, tham số, index hoặc phiên bản optimizer thay đổi. Đường truy cập mới có thể chạm nhiều dòng và khóa nhiều tài nguyên hơn, làm tăng blocking, lock wait hoặc deadlock.

Cần phân biệt hai yếu tố:

- **Thiếu index phù hợp:** truy vấn phải đọc hoặc khóa một phạm vi lớn hơn cần thiết.
- **Plan regression (suy giảm kế hoạch thực thi):** optimizer chọn một kế hoạch kém phù hợp hơn so với trước, dù câu SQL không thay đổi.

Hai yếu tố có thể xảy ra đồng thời. Chúng không có nghĩa mọi table scan đều gây lock contention: truy vấn đọc theo MVCC có thể không giữ shared row lock trên các dòng được đọc. Mức độ tranh chấp phụ thuộc database engine, isolation level, loại thao tác, lock hint và cách engine bảo vệ phạm vi dữ liệu.

## 1. Chỉ mục ảnh hưởng đến đường truy cập dữ liệu như thế nào?

Khi nhận một câu SQL, optimizer chọn một execution plan để tìm, kết hợp, sắp xếp và xử lý dữ liệu. Index cung cấp đường truy cập dựa trên các cột được lập chỉ mục.

Giả sử bảng orders có hàng triệu dòng và ứng dụng thường tìm đơn hàng theo customer_id:

~~~sql
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 42;
~~~

Nếu không có index phù hợp, database có thể phải quét toàn bộ bảng:

~~~text
Table Scan: orders
    |
    +-- Đọc nhiều trang dữ liệu
    |
    +-- Kiểm tra customer_id trên từng dòng
    |
    +-- Giữ lại các dòng thỏa điều kiện
~~~

Nếu có index phù hợp:

~~~sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);
~~~

Optimizer có thể dùng index để tìm vùng khóa liên quan đến customer_id = 42, sau đó truy cập các dòng cần thiết:

~~~text
Index Seek / Index Range Scan
    |
    +-- Tìm vị trí customer_id = 42
    |
    +-- Đọc các entry phù hợp
    |
    +-- Truy cập các dòng cần trả về
~~~

Với điều kiện có tính chọn lọc cao, đường truy cập bằng index thường giảm đáng kể số page cần đọc. Tuy nhiên, index không phải lúc nào cũng nhanh hơn scan. Nếu truy vấn cần phần lớn dữ liệu của bảng, một sequential scan hoặc table scan có thể hiệu quả hơn.

Điểm cần quan tâm đối với concurrency là **phạm vi dữ liệu mà truy vấn thực sự phải đi qua**, đặc biệt khi database cần lấy lock trên các dòng hoặc khoảng khóa.

## 2. Thiếu index có thể làm tăng phạm vi khóa

Hãy xét một locking read dùng để lấy các đơn hàng đang chờ xử lý của một khách hàng:

~~~sql
BEGIN;

SELECT order_id, status
FROM orders
WHERE customer_id = 42
  AND status = 'PENDING'
FOR UPDATE;

-- Xử lý các đơn hàng được chọn.

COMMIT;
~~~

Câu lệnh trên dùng cú pháp PostgreSQL/MySQL tương thích ở mức khái niệm; phạm vi lock cụ thể phụ thuộc engine.

Nếu không có index phù hợp, engine có thể phải quét nhiều entry hoặc nhiều dòng để tìm các đơn hàng của customer_id = 42 có trạng thái PENDING. Tùy database:

- Một số engine chỉ khóa các dòng được chọn hoặc được truy cập theo quy tắc locking read.
- Một số engine có thể khóa các khóa index đã quét, bao gồm cả khoảng khóa trong những isolation level nhất định.
- Kế hoạch truy cập rộng có thể làm tăng thời gian thực hiện truy vấn và kéo dài thời gian các lock được giữ.
- Nếu lượng lock lớn, một số engine có thể áp dụng cơ chế quản lý hoặc escalation lock theo quy tắc riêng.

Điều đó có thể khiến transaction khác phải chờ lâu hơn, kể cả khi transaction đó chỉ cần một phần nhỏ của vùng dữ liệu đang bị truy cập.

### Ví dụ với hai transaction

Giả sử T1 cần khóa các đơn hàng PENDING của customer 42, còn T2 muốn cập nhật một đơn hàng PENDING của customer 84.

~~~text
Không có index phù hợp

T1                                      T2
|                                       |
|-- Bắt đầu scan orders                 |
|                                       |
|-- Đi qua nhiều page / index entry     |
|                                       |
|-- Tìm các dòng customer 42            |
|                                       |
|                                       |-- UPDATE order của customer 84
|                                       |
|                                       |-- Có thể phải chờ nếu tài nguyên
|                                       |   T1 đang giữ bị xung đột
|                                       |
|-- Hoàn tất xử lý                      |
|-- COMMIT, nhả lock                    |
|                                       |
|                                       |-- Tiếp tục UPDATE
~~~

Nếu có index giúp thu hẹp vùng tìm kiếm, truy vấn T1 có thể xử lý ít dữ liệu hơn. Khi đó, thời gian truy vấn và phạm vi tài nguyên bị khóa có thể giảm.

Tuy nhiên, không được kết luận rằng T1 chắc chắn khóa tất cả các dòng đã scan. PostgreSQL, InnoDB và SQL Server có quy tắc locking khác nhau. Cần kiểm tra loại lock thực tế và isolation level của hệ thống.

## 3. Phạm vi khóa phụ thuộc database engine

Cùng một câu SQL có thể tạo ra phạm vi lock khác nhau giữa các hệ quản trị. Để hiểu ảnh hưởng của index, cần xem cơ chế locking của engine đang sử dụng.

### 3.1. MySQL/InnoDB

InnoDB sử dụng index record lock và có thể dùng gap lock hoặc next-key lock để bảo vệ khoảng khóa trong những trường hợp nhất định.

Ở REPEATABLE READ, locking read hoặc UPDATE có điều kiện có thể lấy next-key lock trên các entry index được truy cập. Nếu truy vấn dùng index không phù hợp hoặc phải quét một vùng index lớn, phạm vi khóa có thể rộng hơn dự kiến.

Ví dụ:

~~~sql
BEGIN;

SELECT *
FROM orders
WHERE customer_id = 42
  AND status = 'PENDING'
FOR UPDATE;

COMMIT;
~~~

Nếu có index kết hợp:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

InnoDB có thể dùng index này để tìm vùng customer_id = 42 và status = PENDING hiệu quả hơn.

Nếu không có index thích hợp, InnoDB có thể phải quét nhiều index record hơn. Các record được truy cập trong quá trình locking statement có thể chịu lock theo quy tắc của InnoDB và isolation level. Điều này có thể làm tăng lock contention.

Cần nhớ rằng:

- Locking read và consistent read thông thường có hành vi khác nhau.
- Gap lock/next-key lock phụ thuộc isolation level, loại truy vấn và đường truy cập index.
- Một truy vấn trả về ít dòng vẫn có thể phải quét nhiều index entry.
- Index giúp thu hẹp phạm vi tìm kiếm nhưng không bảo đảm mọi lock sẽ chỉ nằm trên đúng các dòng trả về.

### 3.2. SQL Server

SQL Server có nhiều cấp độ lock như KEY, RID, PAGE, OBJECT và các loại lock khác. Optimizer có thể chọn index seek, index scan hoặc table/clustered index scan.

Với truy vấn chạy trong SERIALIZABLE hoặc sử dụng locking hints như UPDLOCK, HOLDLOCK, SQL Server có thể dùng key-range lock để bảo vệ phạm vi khóa.

Nếu thiếu index, việc bảo vệ một điều kiện có thể yêu cầu truy cập một vùng lớn hơn. Số lượng lock tăng có thể làm tăng chi phí quản lý và trong một số trường hợp dẫn đến lock escalation, chẳng hạn chuyển nhiều lock cấp dòng/page thành lock cấp bảng.

Ví dụ:

~~~sql
BEGIN TRANSACTION;

SELECT order_id, status
FROM dbo.orders WITH (UPDLOCK, HOLDLOCK)
WHERE customer_id = 42
  AND status = 'PENDING';

COMMIT TRANSACTION;
~~~

Index kết hợp có thể hỗ trợ truy vấn:

~~~sql
CREATE INDEX idx_orders_customer_status
ON dbo.orders (customer_id, status)
INCLUDE (order_id);
~~~

SQL Server có thể dùng index này để tìm vùng dữ liệu hẹp hơn và lấy thông tin cần thiết ngay trên index nếu kế hoạch thực thi cho phép.

Lock escalation không xảy ra chỉ vì optimizer chọn scan. Nó phụ thuộc số lượng lock, áp lực bộ nhớ, cấu hình và các quy tắc của lock manager. Không nên xem việc thêm index là cách duy nhất để xử lý escalation.

### 3.3. PostgreSQL

PostgreSQL sử dụng MVCC cho truy vấn đọc thông thường. Một SELECT không khóa thường đọc snapshot và không lấy shared row lock trên mọi dòng được đọc. Vì vậy, table scan của một SELECT thông thường không đồng nghĩa với việc khóa toàn bộ bảng.

Tuy nhiên, PostgreSQL vẫn dùng row-level lock cho các thao tác như:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 42
FOR UPDATE;
~~~

Nếu thiếu index, PostgreSQL có thể phải quét nhiều dòng để tìm các dòng phù hợp. Row lock được lấy trên các dòng được locking read chọn theo quy tắc của engine; scan rộng làm tăng công việc tìm kiếm và có thể kéo dài transaction. Nếu nhiều transaction cùng khóa các dòng đó, chúng có thể chờ nhau.

Ở SERIALIZABLE, PostgreSQL còn dùng Serializable Snapshot Isolation (SSI) với predicate lock để theo dõi các phụ thuộc đọc/ghi. Predicate lock không nhất thiết chặn transaction khác như row lock; nó giúp phát hiện nguy cơ serialization anomaly và có thể dẫn đến serialization failure. Phạm vi predicate lock có thể được quản lý ở mức tuple, page hoặc relation, tùy tình huống và tài nguyên theo dõi.

Index có thể giúp PostgreSQL theo dõi predicate hẹp hơn trong một số trường hợp, nhưng không bảo đảm tránh mọi serialization conflict. Nếu truy vấn thiếu index hoặc phải scan rộng, predicate lock có thể trở nên thô hơn và làm tăng khả năng phát hiện xung đột bảo thủ.

## 4. Index kết hợp giúp thu hẹp vùng tìm kiếm

Một index đơn cột không phải lúc nào cũng phù hợp với truy vấn có nhiều điều kiện.

Ví dụ:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 42
  AND status = 'PENDING'
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00';
~~~

Nếu chỉ có index trên customer_id, database có thể tìm các đơn hàng của khách hàng rồi tiếp tục lọc status và created_at.

Nếu workload thường xuyên truy vấn theo cả ba điều kiện, có thể cân nhắc index kết hợp:

~~~sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
~~~

Với B-tree, thứ tự cột trong composite index ảnh hưởng khả năng sử dụng các điều kiện lọc và phạm vi scan. Các cột equality thường được đặt trước cột range trong nhiều mẫu truy vấn, nhưng cần dựa trên workload thực tế, phân bố dữ liệu và các truy vấn khác cùng sử dụng index.

Ví dụ:

| Truy vấn | Index có thể phù hợp |
|---|---|
| WHERE customer_id = ? | (customer_id) |
| WHERE customer_id = ? AND status = ? | (customer_id, status) |
| WHERE customer_id = ? AND status = ? AND created_at >= ? | (customer_id, status, created_at) |
| WHERE status = ? AND created_at >= ? | Có thể cần index khác bắt đầu bằng status hoặc index được thiết kế theo workload |

Không nên tạo một index cho mọi tổ hợp cột. Mỗi index cần dung lượng lưu trữ và phải được duy trì khi INSERT, UPDATE hoặc DELETE. Quá nhiều index có thể làm chậm thao tác ghi, tăng I/O và làm tăng chi phí bảo trì.

Mục tiêu là tạo đường truy cập phù hợp cho những truy vấn quan trọng và có ảnh hưởng lớn đến concurrency.

## 5. Kế hoạch thực thi thay đổi có thể làm lock footprint thay đổi

Execution plan là cách optimizer dự định thực hiện một câu SQL. Kế hoạch có thể thay đổi dù câu SQL không đổi.

Một số nguyên nhân:

- Thống kê dữ liệu (statistics) được cập nhật hoặc trở nên lỗi thời.
- Phân bố dữ liệu thay đổi, khiến độ chọn lọc của điều kiện WHERE khác trước.
- Thêm hoặc xóa index.
- Thay đổi schema hoặc kiểu dữ liệu.
- Thay đổi tham số truy vấn.
- Parameter sniffing hoặc parameter-sensitive plan trong SQL Server.
- Optimizer thay đổi giữa các phiên bản database.
- Cấu hình cost model hoặc memory thay đổi.
- Query plan cache bị xóa và câu SQL được biên dịch lại.

Ví dụ, ban đầu truy vấn chọn một khách hàng có ít đơn hàng nên optimizer dùng index seek. Sau một thời gian, thống kê hoặc tham số khiến optimizer ước lượng số dòng trả về lớn và chọn scan.

~~~text
Kế hoạch trước

Index Seek
    |
    +-- Tìm customer_id = 42
    |
    +-- Truy cập một số dòng
    |
    +-- Hoàn tất nhanh


Kế hoạch sau

Table / Index Scan
    |
    +-- Đọc nhiều page hoặc index entry
    |
    +-- Lọc customer_id = 42
    |
    +-- Xử lý nhiều dữ liệu hơn
    |
    +-- Hoàn tất chậm hơn
~~~

Với SELECT thông thường theo MVCC, plan scan có thể làm tăng I/O và CPU nhưng không nhất thiết làm tăng row lock. Với locking read, UPDATE, DELETE hoặc SERIALIZABLE, plan mới có thể làm thay đổi phạm vi tài nguyên được truy cập, thứ tự lấy lock, số lượng lock và thời gian giữ lock.

Vì vậy, khi hiện tượng blocking xuất hiện ngay sau một lần deploy, cập nhật statistics hoặc thay đổi index, cần so sánh execution plan trước và sau thời điểm đó.

## 6. Plan regression có thể làm tăng blocking như thế nào?

Hãy xem một truy vấn cập nhật trạng thái đơn hàng:

~~~sql
UPDATE orders
SET status = 'PROCESSING'
WHERE customer_id = 42
  AND status = 'PENDING';
~~~

Nếu có index phù hợp, engine có thể tìm các dòng mục tiêu nhanh hơn.

Nếu index bị xóa hoặc không còn được sử dụng, engine có thể scan một vùng dữ liệu lớn. Trong khi đó, transaction khác có thể đang cập nhật những đơn hàng trong cùng bảng.

Tác động có thể xảy ra:

1. Truy vấn cần nhiều thời gian hơn để tìm dòng.
2. Lock ghi được lấy trên các dòng mục tiêu và được giữ theo quy tắc transaction.
3. Transaction khác cập nhật những dòng xung đột phải chờ.
4. Thời gian chờ tăng làm các transaction giữ lock lâu hơn.
5. Nhiều transaction chờ nhau hơn, tăng nguy cơ timeout hoặc deadlock.

Sơ đồ khái quát:

~~~text
Plan tốt                              Plan regression
--------                              ---------------
Index Seek                            Table / Index Scan
    |                                      |
Ít dữ liệu cần xử lý                   Nhiều dữ liệu cần xử lý
    |                                      |
Transaction hoàn tất sớm              Transaction kéo dài
    |                                      |
Lock được giữ trong thời gian ngắn     Lock có thể tồn tại lâu hơn
    |                                      |
Ít cơ hội chờ hơn                      Blocking có thể tăng
~~~

Đây là mối quan hệ có điều kiện, không phải quy luật rằng scan luôn khóa nhiều hơn seek. Cần xác định truy vấn đang dùng lock nào, engine có MVCC hay không, isolation level nào đang hoạt động và tài nguyên nào thực sự xung đột.

## 7. Thay đổi thứ tự truy cập có thể làm deadlock xuất hiện

Execution plan thay đổi có thể làm thứ tự truy cập index hoặc dòng dữ liệu thay đổi. Khi hai transaction lấy lock theo thứ tự khác nhau, nguy cơ deadlock có thể tăng.

Ví dụ, hai transaction cập nhật hai tài khoản:

~~~text
T1                                  T2
|                                   |
|-- Lock account A                  |
|                                   |-- Lock account B
|                                   |
|-- Chờ account B                   |-- Chờ account A
|                                   |
+----------- Deadlock -------------+
~~~

Nếu kế hoạch thực thi hoặc đường xử lý làm thay đổi thứ tự truy cập, hai transaction có thể hình thành chu trình chờ.

Một nguyên tắc thiết kế hữu ích là truy cập tài nguyên theo thứ tự ổn định. Ví dụ, khi chuyển tiền giữa hai tài khoản, luôn khóa account_id nhỏ hơn trước rồi đến account_id lớn hơn.

~~~sql
SELECT account_id, balance
FROM accounts
WHERE account_id IN (10, 20)
ORDER BY account_id
FOR UPDATE;
~~~

Thứ tự trong truy vấn và cách engine thực sự lấy lock cần được kiểm tra theo execution plan; ORDER BY trong một câu SELECT không phải cam kết phổ quát rằng mọi engine sẽ lấy lock đúng theo thứ tự hiển thị. Với logic nhiều bước, có thể khóa từng tài nguyên theo thứ tự định trước trong transaction.

## 8. Phân biệt scan rộng với lock escalation

Hai hiện tượng có thể liên quan nhưng không giống nhau.

**Scan rộng** là truy vấn phải đọc nhiều dòng hoặc index entry để tìm dữ liệu. Nó có thể làm tăng I/O, CPU và thời gian thực thi.

**Lock escalation** là cơ chế một số database chuyển nhiều lock ở cấp thấp thành lock ở cấp cao hơn, ví dụ nhiều KEY/PAGE lock thành TABLE lock, nhằm giảm chi phí quản lý lock.

Scan rộng có thể làm số lượng lock tăng nếu thao tác yêu cầu locking trên nhiều tài nguyên. Điều đó có thể góp phần kích hoạt escalation trong engine có cơ chế này. Nhưng scan rộng không tự động đồng nghĩa với escalation.

| Hiện tượng | Biểu hiện | Cần kiểm tra |
|---|---|---|
| Scan rộng | Logical reads, page reads hoặc CPU tăng | Execution plan, index, predicate, statistics |
| Lock footprint lớn | Nhiều key/row/page/range lock được giữ | Lock manager, isolation level, truy vấn đang chạy |
| Lock escalation | Lock cấp cao thay thế nhiều lock cấp thấp | Sự kiện escalation, loại lock, cấu hình và ngưỡng engine |
| Blocking | Session/transaction phải chờ lock không tương thích | Blocking chain, blocker, wait resource và thời gian giữ lock |
| Deadlock | Chu trình chờ tài nguyên giữa các transaction | Deadlock graph, thứ tự truy cập, plan và transaction scope |

PostgreSQL không triển khai lock escalation kiểu SQL Server cho row-level lock. InnoDB cũng có cơ chế quản lý record/gap lock riêng. Không nên áp dụng khái niệm escalation của một engine cho tất cả sản phẩm.

## 9. Cách điều tra khi tranh chấp tăng sau khi plan thay đổi

Khi hệ thống đột nhiên xuất hiện nhiều lock wait hoặc deadlock, nên thu thập bằng chứng theo thứ tự.

### 9.1. Xác định truy vấn và transaction đang chờ

Tìm:

- Session hoặc transaction đang chờ.
- Transaction đang giữ lock (blocker).
- Loại wait và tài nguyên bị chờ.
- Thời gian transaction đã mở.
- Câu SQL và tham số thực tế.
- Isolation level và lock hints.
- Transaction có thực hiện nhiều thao tác trước khi commit hay không.

Không nên chỉ nhìn vào truy vấn bị chặn. Cần tìm transaction giữ tài nguyên và câu lệnh khiến nó giữ lock lâu.

### 9.2. So sánh execution plan trước và sau

Kiểm tra:

- Index seek có chuyển thành scan không?
- Số dòng ước lượng có khác số dòng thực tế nhiều không?
- Join algorithm có thay đổi không?
- Có sort hoặc hash operation mới không?
- Có key lookup lặp lại nhiều lần không?
- Số logical reads và thời gian thực thi thay đổi thế nào?
- Predicate có được áp dụng sớm hay phải lọc sau khi đọc nhiều dòng?

Nếu optimizer ước lượng sai cardinality, plan có thể chọn đường truy cập kém phù hợp.

### 9.3. Kiểm tra statistics và dữ liệu

Statistics mô tả phân bố dữ liệu để optimizer ước lượng số dòng. Khi statistics lỗi thời, optimizer có thể đánh giá sai độ chọn lọc.

Ví dụ, một cột status trước đây phân bố đều giữa PENDING, PAID và CANCELLED, nhưng sau một đợt nhập dữ liệu, phần lớn đơn hàng chuyển sang PENDING. Kế hoạch cũ dựa trên thống kê cũ có thể không còn phù hợp.

Cần kiểm tra thời điểm cập nhật statistics, histogram, data skew và số dòng thực tế. Chỉ cập nhật statistics khi có bằng chứng chúng không phản ánh dữ liệu hiện tại.

### 9.4. Kiểm tra index

Xem xét:

- Index phục vụ predicate WHERE có tồn tại không?
- Thứ tự cột trong composite index có phù hợp không?
- Điều kiện truy vấn có sử dụng được index không?
- Có implicit conversion hoặc hàm áp lên cột khiến predicate kém sargable không?
- Index có bị phân mảnh hoặc có vấn đề bảo trì không?
- Index có bao phủ các cột cần đọc hay phát sinh quá nhiều lookup không?

Không nên tạo index chỉ dựa trên một execution plan riêng lẻ. Cần đánh giá workload đọc và ghi tổng thể.

## 10. Đọc execution plan để tìm nguyên nhân

Một execution plan thường cho biết database sử dụng scan, seek, join, sort hoặc lookup như thế nào.

Ví dụ trên PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status
FROM orders
WHERE customer_id = 42
  AND status = 'PENDING';
~~~

Các thông tin cần quan sát:

- **Seq Scan:** quét tuần tự bảng.
- **Index Scan:** truy cập index rồi có thể truy cập heap.
- **Index Only Scan:** có thể lấy dữ liệu từ index nếu visibility map và các điều kiện khác cho phép.
- **Rows:** số dòng thực tế và ước lượng.
- **Buffers:** số buffer được truy cập.
- **Execution Time:** thời gian thực thi.

EXPLAIN ANALYZE thực sự chạy câu truy vấn. Với câu SELECT có tác dụng phụ thông qua function hoặc câu UPDATE/DELETE, cần thận trọng khi đo. Có thể dùng EXPLAIN không ANALYZE để xem kế hoạch dự kiến mà không thực thi câu lệnh.

Trên SQL Server, có thể xem Actual Execution Plan và so sánh với Estimated Execution Plan. Actual plan cung cấp số dòng thực tế, số lần thực thi operator và các cảnh báo liên quan.

Một số công cụ hữu ích khác:

| Database | Công cụ/nguồn quan sát |
|---|---|
| PostgreSQL | EXPLAIN, EXPLAIN ANALYZE, pg_stat_statements, pg_stat_activity, pg_locks |
| MySQL/InnoDB | EXPLAIN, EXPLAIN ANALYZE, performance_schema, sys schema, InnoDB status |
| SQL Server | Actual Execution Plan, Query Store, DMVs, Extended Events, deadlock graph |
| Oracle | EXPLAIN PLAN, DBMS_XPLAN, V$SQL, V$SESSION, V$LOCK |

Cần ghép thông tin execution plan với lock wait và blocking graph. Một plan chậm không tự chứng minh nó là blocker; phải xác định transaction nào đang giữ tài nguyên và wait resource có liên quan đến truy vấn đó hay không.

## 11. Predicate không sargable có thể làm index kém hiệu quả

Một predicate có thể không sử dụng được index hiệu quả nếu biểu thức làm biến đổi cột trước khi so sánh.

Ví dụ:

~~~sql
SELECT order_id
FROM orders
WHERE DATE(created_at) = DATE '2026-11-14';
~~~

Nếu index được tạo trên created_at, việc áp dụng hàm DATE lên cột có thể khiến optimizer không sử dụng được index theo cách mong muốn, tùy engine và khả năng biến đổi biểu thức.

Có thể viết lại thành khoảng thời gian:

~~~sql
SELECT order_id
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-15 00:00:00';
~~~

Điều kiện range trên cột gốc thường dễ tận dụng B-tree index hơn.

Các trường hợp khác:

- CAST hoặc CONVERT trên cột được index.
- So sánh khác kiểu dữ liệu dẫn đến implicit conversion.
- LIKE với wildcard ở đầu chuỗi như %abc.
- OR trên nhiều cột mà optimizer không tìm được kế hoạch phù hợp.
- Biểu thức tính toán phức tạp trên cột lọc.

Không phải mọi biểu thức đều chắc chắn làm mất index. Một số engine hỗ trợ expression index, function-based index hoặc optimizer có thể biến đổi predicate. Cần kiểm tra plan thực tế.

## 12. Biện pháp giảm tranh chấp

Sau khi xác định nguyên nhân, có thể kết hợp nhiều hướng xử lý.

### 12.1. Tối ưu index theo workload

Tạo hoặc điều chỉnh index để hỗ trợ các điều kiện lọc, join và thứ tự truy cập quan trọng.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_status_created
ON orders (status, created_at);
~~~

Nếu truy vấn thường lọc theo status và khoảng created_at, index này có thể thu hẹp vùng scan. Tuy nhiên, cần xem phân bố dữ liệu và các truy vấn khác trước khi quyết định thứ tự cột.

### 12.2. Giữ transaction ngắn

Không giữ transaction mở trong lúc:

- Chờ HTTP API.
- Gửi email.
- Chờ người dùng nhập liệu.
- Xử lý file lớn.
- Thực hiện tính toán nặng không cần bảo vệ bằng lock.

Chỉ giữ lock trong khoảng thời gian cần thiết để đảm bảo tính đúng đắn của thay đổi database.

### 12.3. Cập nhật theo điều kiện nguyên tử

Với thao tác đơn giản, đưa điều kiện vào UPDATE:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity > 0;
~~~

Kiểm tra số dòng bị ảnh hưởng để xác định thao tác thành công. Cách này tránh khoảng trống giữa SELECT kiểm tra và UPDATE.

### 12.4. Truy cập tài nguyên theo thứ tự ổn định

Nếu một transaction cần khóa nhiều dòng, hãy định nghĩa thứ tự truy cập thống nhất giữa các luồng nghiệp vụ. Điều này giúp giảm chu trình chờ và deadlock.

### 12.5. Chia nhỏ batch

Một UPDATE hoặc DELETE xử lý quá nhiều dòng trong một transaction có thể giữ nhiều lock và kéo dài thời gian hoàn tất.

Có thể chia batch thành các phần nhỏ, nhưng cần xác định rõ yêu cầu nguyên tử. Chia nhỏ transaction thay đổi semantics: các batch trước có thể đã commit nếu batch sau thất bại. Ứng dụng phải hỗ trợ tiếp tục, retry hoặc đối soát.

### 12.6. Theo dõi plan regression

Với các truy vấn quan trọng, nên lưu lại plan hoặc theo dõi Query Store/pg_stat_statements và các chỉ số thực thi theo thời gian. Khi plan thay đổi, đánh giá tác động trước khi áp dụng hint hoặc ép plan.

Không nên ép một execution plan cố định khi chưa hiểu nguyên nhân. Dữ liệu có thể thay đổi và một plan từng tốt có thể trở nên kém hiệu quả.

## 13. Những nhầm lẫn thường gặp

**“Table scan luôn khóa toàn bộ bảng.”**

Không đúng. Table scan mô tả đường đọc dữ liệu. Việc có khóa hay không và khóa ở mức nào phụ thuộc loại câu lệnh, isolation level và engine. SELECT MVCC thông thường có thể scan bảng mà không giữ shared row lock trên mọi dòng.

**“Index seek luôn không gây blocking.”**

Không đúng. Index seek vẫn có thể lấy lock trên các dòng hoặc khoảng khóa cần bảo vệ. Hai transaction cùng cập nhật một dòng vẫn có thể chờ nhau dù cả hai đều dùng index seek.

**“Thêm càng nhiều index thì concurrency càng tốt.”**

Không đúng. Index giúp một số truy vấn đọc hoặc ghi tìm dữ liệu nhanh hơn, nhưng mỗi index làm tăng công việc duy trì khi dữ liệu thay đổi. Index không phù hợp có thể làm INSERT, UPDATE, DELETE chậm hơn và tăng chi phí lưu trữ.

**“Thấy lock escalation thì chỉ cần thêm index.”**

Không đủ. Cần kiểm tra số lượng lock, transaction scope, isolation level, batch size và cách engine escalation. Index có thể giảm số dòng được truy cập nhưng không thay thế việc thiết kế transaction hợp lý.

**“Execution plan thay đổi chỉ ảnh hưởng tốc độ.”**

Không đúng. Với locking query hoặc transaction ghi, plan có thể thay đổi đường truy cập, thứ tự xử lý và thời gian giữ lock, từ đó thay đổi blocking và deadlock. Với SELECT MVCC thông thường, tác động chính có thể là I/O và CPU thay vì row-lock contention.

**“Optimizer chọn scan là lỗi của optimizer.”**

Không nhất thiết. Nếu truy vấn cần phần lớn bảng, scan có thể là lựa chọn đúng. Cần so sánh cardinality ước lượng và thực tế, số page đọc, chi phí lookup và đặc điểm dữ liệu trước khi kết luận.

## 14. Quy trình điều tra thực tế

Khi lock wait hoặc deadlock tăng sau khi triển khai một phiên bản ứng dụng hoặc thay đổi database, có thể tiến hành:

1. Xác định thời điểm vấn đề bắt đầu và các thay đổi xảy ra ngay trước đó.
2. Thu thập blocking chain, wait type, wait resource và transaction đang giữ lock.
3. Xác định câu SQL thực tế cùng tham số và isolation level.
4. So sánh actual execution plan trước và sau.
5. Kiểm tra index, statistics, cardinality estimate và data skew.
6. Xác định scan rộng có thực sự làm tăng lock footprint hay chỉ tăng thời gian đọc.
7. Kiểm tra transaction duration, batch size, thứ tự lấy lock và side effect ngoài database.
8. Thử thay đổi index hoặc truy vấn trên môi trường phù hợp, đo lại logical reads, execution time và lock waits.
9. Theo dõi sau khi triển khai để xác nhận blocking và deadlock đã giảm mà workload ghi không bị suy giảm đáng kể.

Nên giữ lại bằng chứng trước và sau thay đổi. Nếu chỉ quan sát CPU hoặc thời gian truy vấn, có thể bỏ lỡ việc phạm vi khóa và blocking chain đã thay đổi.

## Kết luận

Thiếu chỉ mục phù hợp có thể khiến database quét một phạm vi dữ liệu lớn hơn cần thiết. Với locking read, UPDATE, DELETE hoặc isolation level cần bảo vệ phạm vi, điều này có thể làm tăng công việc lấy lock, lock footprint và thời gian transaction phải giữ tài nguyên. Một execution plan thay đổi cũng có thể làm đường truy cập, thứ tự xử lý và thời gian giữ lock khác trước, dẫn đến blocking hoặc deadlock mới.

Muốn xử lý đúng, cần kết hợp execution plan với bằng chứng từ lock manager và blocking chain. Index nên được thiết kế theo workload thực tế; transaction nên ngắn; các thao tác ghi nên có điều kiện nguyên tử; và kế hoạch thực thi quan trọng cần được theo dõi sau mỗi thay đổi statistics, schema hoặc dữ liệu. Không nên kết luận scan luôn gây khóa toàn bảng hoặc seek luôn tránh được blocking, vì hành vi cuối cùng phụ thuộc engine, isolation level và loại truy vấn.
