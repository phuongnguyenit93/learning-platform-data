# Những giả định dễ hỏng khi chuyển ứng dụng sang hệ quản trị khác

Chuyển một ứng dụng từ PostgreSQL sang MySQL, SQL Server hoặc Oracle thường được bắt đầu bằng việc đổi cú pháp SQL, kiểu dữ liệu và cấu hình kết nối. Nhưng phần khó hơn nằm ở những giả định mà ứng dụng đã dựa vào về **transaction, isolation, khóa, lỗi đồng thời và thời điểm commit**. Hai hệ quản trị có thể chấp nhận cùng một câu SQL tương đương nhưng tạo ra lịch thực thi, phạm vi khóa và kết quả quan sát khác nhau.

Một ứng dụng có thể chạy ổn định trên hệ quản trị cũ vì một giả định ngầm tình cờ đúng: một truy vấn đọc không chặn writer, một lần `SELECT` nhìn thấy commit mới, một lỗi deadlock tự rollback toàn transaction, một unique constraint cho phép nhiều giá trị `NULL`, hoặc một câu DDL có thể rollback. Khi chuyển sang hệ khác, giả định đó có thể không còn đúng và dẫn đến blocking, deadlock, lost update, dữ liệu trùng, transaction bị hủy hoặc dữ liệu đọc không nhất quán.

Vì vậy, migration cần xem **semantics** trước cú pháp. Hãy xác định chính xác ứng dụng cần bảo đảm điều gì, sau đó ánh xạ sang cơ chế tương ứng của DBMS đích. Tên isolation level giống nhau không chứng minh cách triển khai giống nhau; một hint khóa có tên gần giống cũng không đảm bảo cùng phạm vi khóa hay cùng hành vi chờ.

## 1. Vì sao cùng một ứng dụng có thể hành xử khác sau migration?

Mỗi DBMS có lock manager, MVCC/version store, optimizer, transaction manager và quy tắc lỗi riêng. Những khác biệt đó ảnh hưởng trực tiếp đến thứ tự các thao tác đồng thời.

Ví dụ, một request thực hiện:

```sql
BEGIN;

SELECT quantity
FROM inventory
WHERE product_id = 42;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;

COMMIT;
```

Ứng dụng có thể ngầm giả định rằng:

- `SELECT` sẽ khóa hàng cho đến khi transaction kết thúc.
- Một transaction khác không thể đọc hoặc sửa cùng hàng trong lúc này.
- Nếu có xung đột, DBMS sẽ chờ thay vì báo lỗi.
- Khi câu `UPDATE` thất bại, toàn bộ transaction đã tự rollback.
- `COMMIT` xác nhận dữ liệu đã nhìn thấy ngay trên mọi node đọc.

Không giả định nào trong số này đúng với mọi DBMS và mọi isolation level. Chẳng hạn, ở nhiều cấu hình MVCC, `SELECT` thông thường không khóa hàng để ngăn writer; nếu cần khóa trước khi sửa, phải dùng locking read hoặc câu lệnh cập nhật nguyên tử. Một lỗi có thể rollback cả transaction ở DBMS này nhưng chỉ rollback statement ở cấu hình khác. Commit trên primary cũng không đồng nghĩa mọi read replica đã replay thay đổi.

## 2. Tên isolation level giống nhau không có nghĩa semantics giống nhau

Các mức cô lập chuẩn SQL là Read Uncommitted, Read Committed, Repeatable Read và Serializable. DBMS có thể triển khai các mức này bằng khóa, row version, snapshot hoặc kết hợp nhiều kỹ thuật.

| DBMS | Hành vi thường gặp ở mức mặc định | Điểm cần xác minh khi migration |
|---|---|---|
| PostgreSQL | `READ COMMITTED`; mỗi statement thường có snapshot riêng | `REPEATABLE READ` là snapshot isolation; `SERIALIZABLE` dùng SSI và có thể abort transaction |
| MySQL InnoDB | `REPEATABLE READ` thường là mặc định; consistent read dùng read view | Snapshot read và locking read có hành vi khác nhau; gap/next-key lock phụ thuộc isolation, index và access path |
| SQL Server | Thường là `READ COMMITTED`; có thể dùng khóa hoặc row version tùy `READ_COMMITTED_SNAPSHOT` | Cần biết RCSI và `ALLOW_SNAPSHOT_ISOLATION`; `SNAPSHOT` là lựa chọn riêng, `SERIALIZABLE` có key-range lock |
| Oracle | `READ COMMITTED` theo statement là mặc định phổ biến | `SERIALIZABLE` dùng snapshot ở mức transaction; xung đột cập nhật có thể trả `ORA-08177` |

Bảng trên chỉ mô tả hành vi phổ biến. Phiên bản, cấu hình database, session, driver và connection pool có thể thay đổi mặc định. Khi migration, hãy đọc cấu hình thực tế của hệ thống cũ và mới thay vì chỉ nhìn tên isolation level trong code.

### 2.1. Read Committed không phải lúc nào cũng có cùng cách đọc

Trong PostgreSQL, một statement ở Read Committed thường nhìn thấy các transaction đã commit trước khi statement đó bắt đầu. Hai câu `SELECT` liên tiếp trong cùng transaction có thể nhìn thấy hai trạng thái khác nhau nếu transaction khác commit ở giữa.

Trong SQL Server, Read Committed có thể được triển khai bằng shared lock hoặc row version tùy tùy chọn `READ_COMMITTED_SNAPSHOT`. Khi dùng khóa, truy vấn đọc có thể chờ writer; khi dùng row version, reader thường đọc phiên bản phù hợp mà ít chặn writer hơn.

Trong Oracle, Read Committed cung cấp statement-level read consistency qua undo. Mỗi câu lệnh có thể nhìn thấy một snapshot nhất quán riêng.

Do đó, một ứng dụng chuyển từ SQL Server với RCSI bật sang PostgreSQL hoặc ngược lại có thể thay đổi hành vi blocking dù vẫn khai báo `READ COMMITTED`.

### 2.2. Repeatable Read có thể cho phép anomaly khác nhau

Trong PostgreSQL, Repeatable Read dùng snapshot ổn định cho transaction và có thể cho phép write skew. Hai transaction đọc cùng điều kiện rồi ghi các hàng khác nhau có thể cùng commit nếu không có xung đột ghi trực tiếp.

InnoDB ở Repeatable Read kết hợp consistent read với locking behavior như gap/next-key locking cho một số locking read và thao tác ghi. Câu `SELECT` thông thường và `SELECT ... FOR UPDATE` không nhất thiết đọc theo cùng cách.

SQL Server có Snapshot Isolation riêng, dựa trên row version và kiểm tra xung đột ghi; mức Repeatable Read truyền thống dùng khóa để giữ hàng đã đọc nhưng không bảo vệ mọi khoảng để ngăn phantom như Serializable.

Oracle Repeatable Read không phải isolation level được cung cấp theo cùng bộ tên chuẩn như PostgreSQL/MySQL; Oracle thường dùng Read Committed và Serializable với semantics riêng. Không thể chỉ thay chuỗi `REPEATABLE READ` trong cấu hình rồi giả định hành vi tương đương.

## 3. Autocommit và ranh giới transaction có thể khác

Một trong những giả định nguy hiểm nhất là cho rằng mỗi câu SQL tự động thuộc cùng transaction hoặc tự động commit theo cùng cách trên mọi môi trường.

Autocommit có thể được điều khiển bởi:

- DBMS hoặc session setting.
- Driver JDBC/ODBC hoặc provider ORM.
- Framework transaction manager.
- Connection pool khi cấp và trả connection.
- Cấu hình riêng của từng request hoặc worker.

Ví dụ, JDBC thường khởi tạo connection ở chế độ autocommit; khi gọi `setAutoCommit(false)`, các câu lệnh tiếp theo thuộc transaction cho đến commit/rollback. Nhiều client MySQL cũng bật autocommit theo mặc định. Nhưng ứng dụng không nên suy ra trạng thái thực tế từ hành vi của một công cụ quản trị.

### 3.1. Một câu lệnh có thể đã commit trước khi câu sau chạy

Nếu autocommit bật, hai câu lệnh sau có thể là hai transaction độc lập:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;

INSERT INTO order_item(order_id, product_id, quantity)
VALUES (900, 42, 1);
```

Nếu câu `UPDATE` commit nhưng `INSERT` thất bại, tồn kho đã giảm dù order item chưa được tạo. Ứng dụng tưởng hai thao tác nguyên tử nhưng thực tế đã chia thành hai transaction.

Hãy dùng transaction tường minh cho các thao tác cần commit/rollback cùng nhau:

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42
  AND quantity > 0;

-- Xác nhận đúng một hàng được cập nhật.

INSERT INTO order_item(order_id, product_id, quantity)
VALUES (900, 42, 1);

COMMIT;
```

`BEGIN`/`COMMIT` là cú pháp phổ biến nhưng cú pháp bắt đầu transaction, API driver và quy tắc DDL có thể khác nhau. Cần xác nhận framework có tự mở transaction hay không để tránh lồng transaction không đúng cách.

### 3.2. Connection pool có thể giữ trạng thái session

Một connection được trả về pool có thể còn isolation level, schema, timezone, autocommit, temporary table hoặc session variable từ request trước nếu pool không reset đúng cách. Request tiếp theo nhận connection đó và chạy dưới cấu hình không mong đợi.

Khi chuyển DBMS hoặc đổi driver, hãy kiểm tra:

- Pool có rollback transaction chưa kết thúc trước khi trả connection không.
- Autocommit được đặt lại đúng trạng thái không.
- Isolation level và session settings có được reset không.
- Có session variable, temporary object hoặc role còn sót không.
- Một connection có bị dùng đồng thời bởi nhiều request không.

Không dùng connection pool như nơi lưu trạng thái nghiệp vụ. Transaction state phải có vòng đời rõ và kết thúc trước khi connection được tái sử dụng.

## 4. SELECT thông thường không phải locking read ở mọi DBMS

Ứng dụng có thể giả định rằng đọc một hàng đồng nghĩa với việc giữ khóa ngăn transaction khác sửa hàng đó. Giả định này thường sai trong hệ thống MVCC.

Ví dụ:

```sql
SELECT quantity
FROM inventory
WHERE product_id = 42;
```

Trong PostgreSQL, MySQL InnoDB, Oracle và các chế độ row-versioning của SQL Server, một truy vấn đọc thông thường có thể lấy phiên bản dữ liệu phù hợp mà không giữ shared row lock để chặn writer đến hết transaction.

Nếu ứng dụng cần đọc rồi cập nhật dựa trên giá trị vừa đọc, có thể dùng một trong các cách:

- Cập nhật nguyên tử có điều kiện, chẳng hạn `UPDATE ... WHERE quantity >= :needed`.
- Optimistic locking với version column.
- Locking read như `SELECT ... FOR UPDATE` ở DBMS hỗ trợ.
- Lock hints hoặc key-range lock theo cú pháp DBMS.
- Serializable khi bất biến phụ thuộc nhiều hàng hoặc predicate.

Không nên thêm lock chỉ vì “đọc rồi ghi” nếu có thể diễn đạt thao tác thành một câu cập nhật nguyên tử. Nhưng cũng không được bỏ bảo vệ khi quy tắc phụ thuộc vào nhiều hàng.

## 5. Cú pháp khóa và phạm vi khóa không portable

Các DBMS có cú pháp và quy tắc riêng để yêu cầu khóa.

| Nhu cầu | PostgreSQL | MySQL InnoDB | SQL Server | Oracle |
|---|---|---|---|---|
| Khóa hàng để cập nhật | `FOR UPDATE` | `FOR UPDATE` | Thường dùng hints như `UPDLOCK`/`XLOCK` kết hợp transaction | `FOR UPDATE` |
| Không chờ khóa | `NOWAIT` | `NOWAIT` ở các phiên bản hỗ trợ | `NOWAIT` qua lock hint như `NOWAIT`/timeout theo cú pháp | `NOWAIT` |
| Bỏ qua hàng đang khóa | `SKIP LOCKED` | `SKIP LOCKED` ở phiên bản hỗ trợ | `READPAST` trong một số queue pattern | `SKIP LOCKED` |
| Bảo vệ phạm vi/predicate | SSI predicate tracking ở Serializable | Gap/next-key locks theo điều kiện | Key-range locks ở Serializable | Cơ chế khóa và read consistency riêng |

Các ô trong bảng chỉ là gợi ý tương đương về mục đích, không phải thay thế cú pháp một-một. Ví dụ SQL Server `READPAST` không hoàn toàn tương đương `SKIP LOCKED`: nó có giới hạn về loại khóa và isolation setting, có thể không bỏ qua page lock. PostgreSQL SIREAD predicate lock trong SSI không phải gap lock chặn insert; nó ghi nhận phụ thuộc để có thể abort transaction.

### 5.1. Cùng một query có thể khóa phạm vi khác do index

InnoDB có thể dùng gap/next-key lock khi truy vấn locking read trên một range index ở Repeatable Read. Nếu index phù hợp bị thiếu, access path có thể rộng hơn và lock footprint tăng.

SQL Server Serializable có thể dùng key-range lock trên index. Index seek có thể bảo vệ một dải hẹp; scan rộng có thể làm phạm vi bảo vệ rộng hơn.

PostgreSQL SSI có thể ghi nhận SIREAD ở mức tuple, page hoặc relation tùy access path và cơ chế quản lý predicate lock. Đây là theo dõi xung đột, không phải khóa chặn thông thường.

Khi migration, hãy kiểm tra actual execution plan và lock diagnostics trên DBMS đích. Không giả định index cũ có cùng vai trò hoặc lock footprint khi optimizer mới chọn một kế hoạch khác.

## 6. Phantom và range protection không giống nhau

Khóa các hàng hiện có không tự động ngăn một transaction khác chèn hàng mới thỏa điều kiện truy vấn. Ví dụ:

```sql
SELECT *
FROM reservation
WHERE room_id = 8
  AND starts_at < :requested_end
  AND ends_at > :requested_start;
```

Nếu T1 không tìm thấy reservation nào, T2 có thể chèn một reservation trùng khoảng. `SELECT FOR UPDATE` trên tập kết quả rỗng không nhất thiết khóa khoảng trống trong mọi DBMS.

Các hệ thống xử lý phantom khác nhau:

- InnoDB có thể dùng gap/next-key lock trên index phù hợp.
- SQL Server Serializable có thể dùng key-range lock.
- PostgreSQL Serializable dùng SSI để theo dõi phụ thuộc và có thể abort một transaction.
- Một số DBMS hoặc isolation mode khác có quy tắc riêng.

Nếu nghiệp vụ là “không có hai reservation chồng lấn”, hãy ưu tiên constraint chuyên biệt nếu DBMS hỗ trợ, chẳng hạn exclusion constraint của PostgreSQL. Nếu không, thiết kế hàng guard, khóa phạm vi đúng hoặc Serializable. Không dùng một câu `SELECT` kiểm tra trước rồi `INSERT` như thể nó tự bảo vệ khỏi cuộc đua.

## 7. Deadlock và lỗi đồng thời có mã khác nhau

Ứng dụng thường bắt một exception chung rồi retry mọi lỗi. Điều này có thể chạy trên DBMS cũ nhưng sai trên DBMS mới vì mã lỗi và phạm vi rollback khác nhau.

Một số mã thường gặp:

| DBMS | Lỗi | Mã thường gặp | Lưu ý xử lý |
|---|---|---|---|
| PostgreSQL | Deadlock detected | SQLSTATE `40P01` | Transaction bị hủy; rollback/đưa connection về trạng thái sạch rồi retry toàn bộ nếu an toàn |
| PostgreSQL | Serialization failure | SQLSTATE `40001` | Retry toàn bộ transaction trên snapshot mới |
| PostgreSQL | Lock not available | SQLSTATE `55P03` | Có thể liên quan `NOWAIT`/lock timeout; xem chính sách trước khi retry |
| MySQL InnoDB | Deadlock found | Error 1213 | InnoDB rollback transaction victim; retry transaction có giới hạn |
| MySQL InnoDB | Lock wait timeout | Error 1205 | Mặc định có thể chỉ rollback statement tùy cấu hình; không giả định transaction luôn đã rollback |
| SQL Server | Deadlock victim | Error 1205 | Transaction victim bị rollback; retry toàn bộ đơn vị công việc |
| SQL Server | Lock request timeout | Error 1222 | Câu lệnh timeout; transaction có thể vẫn còn hoạt động tùy ngữ cảnh |
| Oracle | Deadlock detected | ORA-00060 | Statement liên quan bị rollback; transaction cần được ứng dụng xử lý theo trạng thái thực tế |
| Oracle | Cannot serialize access | ORA-08177 | Transaction Serializable không thể tiếp tục; retry theo quy tắc Oracle |

Mã lỗi, trạng thái transaction và phạm vi rollback có thể thay đổi theo phiên bản, driver và cấu hình. Ứng dụng nên phân loại bằng SQLSTATE/vendor code và kiểm tra trạng thái transaction thay vì so khớp thông báo lỗi dạng text.

### 7.1. Retry phải chạy lại toàn bộ đơn vị công việc

Nếu quyết định ghi phụ thuộc vào dữ liệu đã đọc, retry riêng câu lệnh cuối có thể sử dụng giá trị cũ. Sau deadlock victim hoặc serialization failure, thông thường cần rollback transaction, bắt đầu transaction mới, đọc lại trạng thái và tính lại quyết định.

Không retry vô hạn. Dùng giới hạn số lần, deadline, backoff có jitter và idempotency cho tác động bên ngoài. Nếu nhiều tầng cùng retry, số lần gọi database có thể bị nhân lên.

## 8. Savepoint và phạm vi rollback không đồng nhất

Savepoint cho phép đánh dấu một vị trí trong transaction để rollback một phần thao tác. Nhưng cách DBMS xử lý lỗi sau savepoint và các loại statement không giống nhau.

PostgreSQL đánh dấu transaction là aborted sau nhiều lỗi statement; ứng dụng phải rollback về savepoint hoặc rollback toàn transaction trước khi tiếp tục. SQL Server có `SAVE TRANSACTION`, nhưng một số lỗi làm transaction không còn có thể commit; cần kiểm tra `XACT_STATE()`. MySQL InnoDB hỗ trợ savepoint, nhưng deadlock thường rollback toàn transaction victim; lock wait timeout mặc định có thể chỉ rollback statement. Oracle hỗ trợ savepoint và `ROLLBACK TO SAVEPOINT`; deadlock có thể rollback statement gây deadlock mà transaction còn lại vẫn cần được xử lý.

Ví dụ SQL Server:

```sql
BEGIN TRANSACTION;

SAVE TRANSACTION before_optional_step;

-- Thực hiện thao tác có thể thất bại.

-- Khi phù hợp, rollback về savepoint:
ROLLBACK TRANSACTION before_optional_step;

COMMIT TRANSACTION;
```

Đoạn code trên không có nghĩa mọi lỗi đều cho phép tiếp tục commit. Với SQL Server, kiểm tra `XACT_STATE()` trước khi quyết định tiếp tục; với DBMS khác, dùng API và semantics tương ứng. Không port một handler exception có `ROLLBACK TO SAVEPOINT` mà không kiểm tra trạng thái transaction sau lỗi.

## 9. DDL có thể commit transaction ngoài dự kiến

Một ứng dụng migration hoặc job quản trị có thể giả định DDL nằm trong transaction và có thể rollback cùng DML. Giả định này khác nhau giữa các DBMS.

| DBMS | Hành vi DDL khái quát |
|---|---|
| PostgreSQL | Nhiều lệnh DDL có thể chạy trong transaction và rollback; một số lệnh bị cấm trong transaction block hoặc có giới hạn riêng |
| MySQL | Nhiều lệnh DDL gây implicit commit; transactional DDL phụ thuộc loại statement và phiên bản |
| Oracle | Nhiều lệnh DDL thực hiện implicit commit trước/sau thao tác |
| SQL Server | Nhiều DDL có thể nằm trong transaction, nhưng có ngoại lệ và giới hạn theo statement/tính năng |

Ví dụ, nếu script chạy `ALTER TABLE` rồi sau đó `INSERT` dữ liệu seed và gặp lỗi, PostgreSQL có thể rollback cả phần DDL hỗ trợ transactional; MySQL hoặc Oracle có thể đã commit ngầm trước khi lỗi xảy ra. Kết quả là schema đã thay đổi dù script báo thất bại.

Với migration schema:

- Chia DDL và DML thành các bước có trạng thái rõ.
- Không giả định một transaction bao trùm tất cả statement.
- Thiết kế migration có thể chạy lại hoặc có bước kiểm tra trạng thái.
- Kiểm tra lock mà DDL cần và thời gian chờ trên bảng đang có tải.
- Dùng chiến lược expand/contract khi thay đổi schema có rolling deployment.

## 10. Constraint có thể khác semantics

### 10.1. CHECK và phiên bản DBMS

Một số phiên bản MySQL cũ chấp nhận cú pháp `CHECK` nhưng không thực thi constraint; MySQL bắt đầu thực thi `CHECK` trong các bản 8.0.16 trở đi. Khi chuyển từ PostgreSQL hoặc SQL Server sang phiên bản MySQL cũ, ứng dụng có thể nghĩ dữ liệu được bảo vệ trong khi DBMS bỏ qua điều kiện.

PostgreSQL không cho `CHECK` thông thường đọc subquery hoặc bảng khác; nhiều DBMS cũng giới hạn CHECK ở biểu thức trên hàng. Không dùng hàm tùy chỉnh đọc bảng khác để giả lập constraint tổng hợp vì concurrency và invalidation không được bảo vệ đúng.

### 10.2. NULL trong UNIQUE

Các DBMS không nhất thiết xử lý `NULL` trong unique constraint giống nhau:

- PostgreSQL mặc định xem các giá trị `NULL` là khác nhau trong unique constraint; có tùy chọn `NULLS NOT DISTINCT` ở phiên bản hỗ trợ.
- MySQL thường cho phép nhiều `NULL` trong unique index.
- SQL Server unique index thông thường coi các `NULL` ở cùng khóa là trùng theo quy tắc index; filtered unique index có thể dùng để giới hạn chỉ các giá trị không NULL.
- Oracle unique constraint cho phép nhiều hàng có giá trị NULL theo semantics của Oracle; composite key có quy tắc riêng khi có các cột NULL.

Vì vậy, constraint `UNIQUE(email)` có thể cho phép số lượng hàng NULL khác nhau khi chuyển DBMS. Nếu nghiệp vụ yêu cầu email bắt buộc, khai báo `NOT NULL` rõ ràng. Nếu cần “unique khi có giá trị nhưng cho phép nhiều hàng chưa có giá trị”, hãy mô hình hóa và kiểm thử bằng index/constraint phù hợp của DBMS đích.

### 10.3. Deferrable constraint

PostgreSQL và Oracle hỗ trợ một số constraint có thể trì hoãn kiểm tra đến cuối transaction (`DEFERRABLE`/`SET CONSTRAINTS`). SQL Server và MySQL không cung cấp semantics deferrable constraint tương đương cho các constraint phổ biến.

Một quy trình cập nhật hai hàng có khóa ngoại tham chiếu vòng có thể dựa vào deferred constraint ở hệ cũ nhưng thất bại khi port sang hệ không hỗ trợ. Có thể cần thay đổi thứ tự insert/update, dùng nullable staging state, thêm bước hoàn thiện hoặc thiết kế lại quan hệ.

Không nhầm deferred constraint với Serializable. Trì hoãn thời điểm kiểm tra không tự ngăn mọi race condition giữa các transaction.

### 10.4. Partial/filtered index

PostgreSQL hỗ trợ partial index với predicate; SQL Server hỗ trợ filtered index. MySQL không có cú pháp partial index tổng quát tương đương, nhưng có thể dùng generated column hoặc thiết kế index khác trong một số trường hợp. Oracle có function-based index và các lựa chọn riêng.

Nếu unique partial index đang bảo vệ quy tắc “mỗi tài khoản chỉ có một phiên hoạt động”, cần chuyển semantics đó sang cơ chế DBMS đích. Chỉ bỏ index vì không có cú pháp tương tự sẽ làm mất một phần bảo vệ concurrency.

## 11. Sequence, identity và giá trị sinh tự động

Ứng dụng đôi khi giả định số ID liên tục, không có khoảng trống hoặc được rollback khi transaction thất bại. Giả định này không an toàn trên hầu hết DBMS.

- PostgreSQL sequence không rollback giá trị đã lấy; transaction thất bại vẫn có thể để lại khoảng trống.
- MySQL `AUTO_INCREMENT` có thể tạo khoảng trống do rollback, cache hoặc concurrency.
- SQL Server `IDENTITY` có thể có gap sau rollback, restart hoặc cache behavior.
- Oracle sequence là đối tượng độc lập với transaction; giá trị `NEXTVAL` không được trả lại khi rollback.

ID sinh tự động nên được coi là định danh, không phải số thứ tự nghiệp vụ liên tục. Nếu cần số hóa đơn liên tục theo quy định, phải có thiết kế cấp số riêng với kiểm soát concurrency và quy tắc xử lý rollback; không dựa vào identity/sequence mặc định.

## 12. Lock escalation, row versioning và hot row

SQL Server có lock escalation từ nhiều lock chi tiết lên table lock trong một số điều kiện. PostgreSQL không có cơ chế lock escalation row-to-table tương tự theo cùng cách. InnoDB quản lý row/index locks và có thể phát sinh lock footprint rộng do range scan hoặc thiếu index. Oracle có row-level locking và các cơ chế khác.

Nếu ứng dụng dựa vào việc “chỉ khóa một số hàng”, migration sang DBMS khác có thể khiến một transaction quét/khóa nhiều hàng hơn hoặc bị escalation. Các transaction độc lập bắt đầu chặn nhau dù câu SQL không đổi.

Hãy đo:

- Số hàng và index entry được đọc/khóa.
- Lock wait và deadlock theo table/index/resource.
- Execution plan thực tế.
- Tỷ lệ transaction dài và số lượng lock giữ đồng thời.
- Có escalation hoặc range lock hay không.

Đừng mặc định tăng lock timeout là giải pháp. Timeout dài hơn có thể chỉ khiến request chờ lâu hơn và giữ connection lâu hơn. Cần giảm lock footprint hoặc điều chỉnh mô hình transaction.

## 13. SKIP LOCKED, NOWAIT và queue worker không tương đương hoàn toàn

Một queue có thể dùng `SKIP LOCKED` để nhiều worker nhận các hàng khác nhau. Khi chuyển DBMS, cú pháp tương đương và semantics có thể khác.

- PostgreSQL, MySQL InnoDB ở phiên bản hỗ trợ và Oracle có locking clause `SKIP LOCKED` với giới hạn riêng.
- SQL Server thường dùng `READPAST` kết hợp lock hints cho queue pattern. `READPAST` không bỏ qua mọi loại khóa và không phải thay thế một-một cho `SKIP LOCKED`.
- `NOWAIT` báo lỗi khi không lấy được khóa ngay; `SKIP LOCKED` bỏ qua hàng xung đột và tiếp tục tìm hàng khác.

Ngay cả khi query claim đã port được, ứng dụng vẫn cần lease, token, retry và idempotency. Row lock chỉ ngăn hai worker cùng claim trong thời gian transaction giữ lock. Sau commit, quyền sở hữu phải được thể hiện bằng trạng thái và lease trong dữ liệu.

Không dùng `SKIP LOCKED` cho báo cáo cần toàn bộ hàng thỏa điều kiện: kết quả được trả về có chủ ý không đầy đủ.

## 14. ORM có thể che giấu khác biệt database

ORM giúp trừu tượng hóa mapping, nhưng không loại bỏ khác biệt concurrency của DBMS.

Những điểm cần kiểm tra:

- ORM có tự mở transaction quanh request hay chỉ quanh từng thao tác không.
- Flush xảy ra khi nào: trước query, khi commit hay theo explicit call.
- Pessimistic lock mode được dịch thành SQL/hint nào trên DBMS đích.
- Optimistic version column có được cập nhật bởi mọi đường ghi không.
- Bulk DML có đồng bộ persistence context hay không.
- Isolation level được đặt ở driver, transaction manager hay database default.
- Exception của DBMS được ORM ánh xạ thành loại exception nào.
- Connection pool có reset session state và rollback transaction chưa kết thúc không.

Ví dụ JPA `LockModeType.PESSIMISTIC_WRITE` có thể được dịch thành `FOR UPDATE` trên một DBMS và lock hints trên DBMS khác. Phạm vi khóa, timeout và cách provider xử lý lỗi có thể khác. Cần kiểm tra SQL thực tế được sinh ra và hành vi của database, không chỉ đọc annotation trong entity.

## 15. Thời gian, collation và kiểu dữ liệu cũng ảnh hưởng concurrency

Các khác biệt về kiểu dữ liệu có thể làm thay đổi index và điều kiện tìm kiếm, từ đó thay đổi lock footprint.

- So sánh chuỗi phụ thuộc collation, phân biệt hoa/thường, dấu và quy tắc locale.
- Ép kiểu ngầm có thể khiến predicate không dùng index như dự kiến.
- Độ chính xác timestamp khác nhau có thể làm hai giá trị tưởng khác trở thành bằng nhau hoặc ngược lại.
- Kiểu boolean, decimal, UUID và binary có cách biểu diễn/so sánh khác nhau.
- Timezone và cách lưu UTC/local time có thể làm điều kiện range lệch.

Ví dụ, một unique constraint trên email có thể coi `User@example.com` và `user@example.com` là trùng ở một collation nhưng khác nhau ở collation khác. Nếu ứng dụng dựa vào quy tắc phân biệt hoa thường của DBMS cũ, migration có thể tạo thêm xung đột unique hoặc cho phép dữ liệu trùng theo nghĩa nghiệp vụ.

Các thay đổi này không chỉ là vấn đề dữ liệu. Khi index được xây dựng theo collation hoặc kiểu mới, optimizer có thể chọn access path khác và lock footprint thay đổi.

## 16. Read replica và synchronous replication có semantics riêng

Ứng dụng có thể giả định commit trên primary lập tức được đọc thấy từ mọi replica. Điều này sai với asynchronous replication và vẫn cần xem chính xác mức xác nhận trong synchronous replication.

Phải phân biệt:

- Log đã được gửi đến replica.
- Log đã được nhận/ghi vào relay hoặc WAL storage.
- Log đã được replay/apply để truy vấn đọc nhìn thấy.
- Primary đã xác nhận commit cho client.

Các chế độ synchronous replication có thể chờ những mốc khác nhau. Một cấu hình chờ replica nhận log không nhất thiết chờ replica áp dụng dữ liệu. Khi cần read-your-writes, có thể định tuyến về primary hoặc dùng commit token/LSN/GTID và chờ replica replay đến vị trí đó.

Một transaction trên replica chỉ bảo vệ snapshot tại node đó; nó không tạo transaction phân tán với primary. Không định tuyến các statement của cùng transaction sang nhiều replica khác nhau.

## 17. Timeout và cancellation không có một ý nghĩa chung

Một ứng dụng có thể có connection timeout, statement timeout, lock timeout, transaction timeout và request deadline. DBMS và driver không nhất thiết áp dụng chúng ở cùng phạm vi.

| Loại timeout | Câu hỏi cần xác minh |
|---|---|
| Connection timeout | Chỉ giới hạn kết nối mới hay cả chờ lấy connection từ pool? |
| Lock timeout | Hủy statement hay rollback toàn transaction? |
| Statement timeout | Transaction còn mở sau khi statement bị hủy không? |
| Transaction timeout | Có được DBMS hỗ trợ hay phải do ứng dụng quản lý? |
| Client/request deadline | Khi client ngắt kết nối, driver có cancel statement và rollback không? |
| Idle transaction timeout | DBMS có tự kết thúc transaction không hoạt động không? |

Nếu client timeout nhưng câu SQL vẫn chạy ở database, request retry có thể tạo thêm một transaction trùng trong khi lần đầu vẫn còn thực thi. Cần xác nhận cancellation đã đến driver và DBMS; với kết quả commit không rõ, dùng idempotency key để tra cứu trước khi gửi lại tác động.

## 18. DDL, index và triển khai không gián đoạn

Tạo index hoặc thay đổi schema trên bảng đang có tải có thể cần lock mạnh và ảnh hưởng request đang chạy. Cú pháp “online” hoặc “concurrently” khác nhau giữa DBMS:

- PostgreSQL có `CREATE INDEX CONCURRENTLY` với giới hạn không chạy trong transaction block thông thường.
- MySQL/InnoDB có các algorithm và lock mode cho online DDL tùy thao tác/phiên bản.
- SQL Server hỗ trợ một số lựa chọn online index operation theo edition và loại index.
- Oracle có online operation cho một số thao tác và điều kiện.

Không nên thay `CREATE INDEX CONCURRENTLY` bằng `CREATE INDEX` thông thường trong một migration production mà chưa đánh giá lock và thời gian. Cũng không giả định online DDL hoàn toàn không khóa; thường vẫn có các pha cần lock hoặc điều kiện giới hạn.

Với rolling deployment, cân nhắc expand/contract:

1. Thêm cột hoặc cấu trúc mới theo cách tương thích code cũ.
2. Deploy ứng dụng có thể đọc/ghi cả hai dạng trong giai đoạn chuyển tiếp.
3. Backfill dữ liệu theo batch nhỏ, có checkpoint.
4. Chuyển traffic sang cấu trúc mới.
5. Xác nhận không còn caller cũ rồi mới bỏ cấu trúc cũ.

Các bước này giảm thời gian giữ lock lớn và tránh code mới phụ thuộc schema chưa sẵn sàng.

## 19. Bảng kiểm các giả định cần kiểm chứng trước migration

| Giả định trong ứng dụng | Vì sao có thể hỏng | Cách kiểm chứng |
|---|---|---|
| Isolation level cùng tên có cùng hành vi | DBMS dùng locking, MVCC hoặc snapshot khác nhau | Chạy concurrency test tái hiện dirty/non-repeatable/phantom/write skew |
| `SELECT` khóa hàng | MVCC read có thể không lấy shared row lock | Kiểm tra lock diagnostics; thử writer đồng thời |
| `FOR UPDATE` khóa cùng phạm vi | Index và cú pháp locking khác nhau | Xem execution plan và lock footprint |
| Query không có kết quả nghĩa là không ai có thể insert | Hàng chưa tồn tại không tự được khóa ở mọi DBMS | Test hai transaction cùng kiểm tra rồi insert |
| Deadlock và timeout đều rollback transaction | Phạm vi rollback khác theo lỗi/DBMS | Kiểm tra transaction state sau từng mã lỗi |
| Retry một câu lệnh là đủ | Quyết định có thể dựa trên snapshot cũ | Retry toàn bộ transaction trong test |
| Autocommit giống nhau | Driver/session/framework có thể đổi trạng thái | Kiểm tra JDBC/ODBC/provider và pool thực tế |
| DDL có thể rollback | MySQL/Oracle có implicit commit cho nhiều DDL | Thử migration lỗi giữa chừng trên bản sao dữ liệu |
| CHECK luôn được thực thi | Phiên bản MySQL cũ từng không thực thi CHECK | Xác nhận phiên bản và thử insert vi phạm |
| UNIQUE xử lý NULL giống nhau | Semantics NULL khác DBMS | Test nhiều NULL và composite unique key |
| Sequence không có gap | Sequence/identity thường không rollback giá trị | Test rollback và restart; không dùng ID làm số thứ tự nghiệp vụ |
| SKIP LOCKED tương đương READPAST | Lock types bị bỏ qua và isolation rules khác | Chạy nhiều worker và kiểm tra fairness/duplicate claim |
| Commit primary đọc được ngay trên replica | Replication lag và apply position | Test read-after-write với commit token |
| ORM refresh luôn thấy dữ liệu mới | Snapshot và cache có thể vẫn cũ | Test với context mới, isolation level và cache bật/tắt |
| Timeout đồng nghĩa query đã dừng | Cancellation có thể không đến DBMS | Theo dõi session/query sau khi client timeout |

## 20. Xây dựng bộ kiểm thử concurrency cho migration

Unit test tuần tự thường không phát hiện khác biệt transaction. Cần các test có nhiều connection độc lập, điều khiển thứ tự thao tác bằng barrier hoặc latch để tạo đúng lịch cạnh tranh.

### 20.1. Kiểm thử lost update

1. T1 và T2 cùng đọc version hoặc số lượng ban đầu.
2. Cả hai cùng tính giá trị mới.
3. Cho T1 ghi và commit trước.
4. Cho T2 ghi sau.
5. Xác nhận optimistic locking, atomic update hoặc lock ngăn ghi đè ngoài ý muốn.

### 20.2. Kiểm thử write skew

1. T1 và T2 cùng đọc điều kiện tổng hợp.
2. T1 và T2 cập nhật hai hàng khác nhau.
3. Cùng cho commit.
4. Xác nhận constraint/guard/Serializable giữ bất biến.

### 20.3. Kiểm thử phantom/range

1. T1 đọc một range hoặc xác nhận chưa có hàng thỏa predicate.
2. T2 chèn hoặc cập nhật một hàng để nó thỏa predicate.
3. T1 đọc lại hoặc commit.
4. Xác nhận semantics của isolation level đích và cơ chế range/predicate protection.

### 20.4. Kiểm thử deadlock và lỗi rollback

1. T1 khóa A rồi chờ B.
2. T2 khóa B rồi yêu cầu A.
3. Xác nhận DBMS phát hiện deadlock và chọn victim.
4. Kiểm tra transaction state, connection state và dữ liệu sau lỗi.
5. Xác nhận retry toàn bộ transaction không lặp tác động ngoài database.

### 20.5. Kiểm thử queue worker

1. Nhiều worker cùng claim một batch.
2. Xác nhận một job không bị hai worker sở hữu đồng thời theo giao thức lease.
3. Dừng worker sau khi claim nhưng trước khi hoàn tất.
4. Chờ lease hết hạn và claim lại.
5. Cho worker cũ quay lại, xác nhận token/fencing ngăn nó ghi đè lần claim mới.
6. Kiểm tra job cũ, job ưu tiên thấp và tenant ít lưu lượng không bị starvation.

### 20.6. Chạy trên đúng phiên bản và cấu hình production

Test phải dùng cùng engine, phiên bản chính, isolation default, extension, collation, index, driver và cấu hình liên quan với môi trường đích. Một test trên database khác phiên bản hoặc cấu hình mặc định không chứng minh behavior production.

## 21. Chiến lược migration an toàn

Một quy trình migration nên bắt đầu từ hợp đồng dữ liệu và transaction của ứng dụng, không chỉ từ danh sách câu SQL.

1. **Liệt kê bất biến nghiệp vụ.** Nêu rõ điều kiện phải đúng qua nhiều hàng, nhiều transaction hoặc nhiều dịch vụ.
2. **Ghi lại giả định concurrency hiện tại.** Isolation level, autocommit, lock mode, timeout, retry, transaction boundary và replica routing.
3. **Đo hành vi DBMS cũ.** Lấy execution plan, lock graph, deadlock log, transaction duration và replication behavior.
4. **Ánh xạ sang DBMS đích.** Xác định constraint, locking read, range protection, versioning và error code tương ứng.
5. **Chuyển code dựa trên semantics.** Dùng atomic update, version column, guard row hoặc Serializable khi phù hợp.
6. **Kiểm tra ORM/driver/pool.** Xác nhận transaction boundary, flush, exception mapping và connection reset.
7. **Chạy concurrency tests.** Tái hiện lost update, write skew, phantom, deadlock, timeout, retry và queue contention.
8. **Kiểm thử migration schema.** Xác nhận DDL transactionality, online index, implicit commit và khả năng rollback/roll-forward.
9. **Shadow/canary theo dõi.** So sánh error rate, lock wait, latency, transaction abort và kết quả nghiệp vụ trước khi chuyển toàn bộ traffic.
10. **Chuẩn bị rollback và đối soát.** Xác định cách khôi phục dữ liệu nếu semantics mới làm phát sinh vi phạm hoặc kết quả khác.

## 22. Ví dụ: port thao tác đặt chỗ giữa các DBMS

Giả sử ứng dụng cần bảo đảm không có hai reservation trùng giờ cho cùng một phòng. Cách triển khai hiện tại chỉ kiểm tra bằng `SELECT` rồi `INSERT`:

```sql
BEGIN;

SELECT count(*)
FROM reservation
WHERE room_id = :room_id
  AND starts_at < :requested_end
  AND ends_at > :requested_start;

-- Nếu count = 0 thì INSERT.

COMMIT;
```

Đây là một cuộc đua nếu hai transaction cùng thấy `count = 0`. Trên DBMS cũ, ứng dụng có thể tình cờ được bảo vệ bởi một range lock do isolation/index cụ thể. Sau migration, cùng câu SQL có thể không còn khóa khoảng đó và hai reservation chồng lấn cùng commit.

Các cách bảo vệ có thể chọn:

- PostgreSQL: exclusion constraint trên `room_id` và range thời gian; hoặc Serializable nếu quy tắc phức tạp hơn.
- SQL Server: Serializable với key-range lock trên index phù hợp, hoặc thiết kế guard row/constraint tương đương.
- MySQL InnoDB: locking read trên index range phù hợp ở isolation level và access path đã xác minh; có thể dùng hàng guard theo `room_id` để tạo điểm đồng bộ rõ.
- Oracle: dùng khóa tài nguyên/phòng hoặc transaction Serializable theo semantics Oracle; cần xử lý lỗi và retry đúng cách.

Không có một câu SQL duy nhất có cùng lock footprint trên cả bốn hệ quản trị. Mục tiêu cần port là bất biến “không có khoảng thời gian chồng lấn”, sau đó chọn cơ chế phù hợp của DBMS đích.

## 23. Những điểm cần ghi nhớ

- Migration DBMS là thay đổi semantics transaction và concurrency, không chỉ là đổi cú pháp SQL.
- Isolation level cùng tên có thể dùng snapshot, row version, khóa hoặc kết hợp kỹ thuật khác nhau.
- Autocommit, transaction boundary và session state chịu ảnh hưởng của driver, ORM, framework và connection pool.
- `SELECT` thông thường không nhất thiết khóa hàng; locking read và phạm vi khóa khác nhau giữa DBMS.
- Gap/next-key lock, key-range lock và PostgreSQL SSI predicate tracking có mục tiêu liên quan nhưng không tương đương về cơ chế.
- Deadlock, lock timeout và serialization failure có mã lỗi, trạng thái transaction và phạm vi rollback khác nhau; retry cần phân loại rõ và thường phải chạy lại toàn transaction.
- DDL có thể implicit commit hoặc không được phép trong transaction tùy DBMS; migration schema phải kiểm thử lỗi giữa chừng.
- CHECK, UNIQUE với NULL, deferrable constraint, partial index, sequence/identity và kiểu dữ liệu có semantics khác nhau.
- `SKIP LOCKED` và `READPAST` không phải cú pháp thay thế một-một; queue vẫn cần lease, token và idempotency.
- ORM không che được khác biệt database: cần kiểm tra SQL sinh ra, flush, optimistic/pessimistic locking, exception mapping và cache.
- Read replica có replication lag; commit ở primary không tự bảo đảm replica đã apply dữ liệu.
- Bộ kiểm thử migration phải tái hiện lịch concurrency bằng nhiều connection, đúng phiên bản và cấu hình production.

Khi chuyển hệ quản trị, hãy bảo toàn các bất biến và hành vi mà ứng dụng thực sự cần, thay vì cố giữ nguyên một cấu hình hoặc câu SQL cũ. Việc kiểm chứng bằng concurrency test, lock diagnostics và transaction timeline giúp phát hiện sớm những giả định không còn đúng trước khi chúng trở thành lỗi dữ liệu hoặc sự cố production.
