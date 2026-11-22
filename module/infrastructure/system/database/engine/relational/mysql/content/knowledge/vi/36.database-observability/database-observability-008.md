# Quan sát hệ thống

## Đọc SHOW ENGINE INNODB STATUS và trạng thái deadlock gần nhất

`SHOW ENGINE INNODB STATUS` là một trong những lệnh chẩn đoán quan trọng nhất khi vận hành MySQL với InnoDB. Kết quả cung cấp ảnh chụp trạng thái nội bộ của storage engine: transaction đang hoạt động, khóa và thao tác chờ, deadlock được phát hiện gần nhất, hoạt động I/O, redo log, buffer pool và một số bộ đếm xử lý hàng. Khi truy vấn bị treo, có deadlock hoặc I/O tăng bất thường, lệnh này giúp xác định khu vực cần điều tra tiếp.

Kết quả của lệnh khá dài và chứa nhiều số liệu tích lũy. Không nên đọc nó như một bản log đầy đủ hoặc kết luận chỉ từ một con số đơn lẻ. Hãy xác định đúng thời điểm chụp, đọc phần liên quan tới triệu chứng, so sánh các lần chụp và đối chiếu với `performance_schema`, `sys` schema, error log cùng kế hoạch thực thi.

### 1. Chạy SHOW ENGINE INNODB STATUS

Trong MySQL command-line client, dùng `\G` để hiển thị mỗi dòng kết quả theo chiều dọc, dễ đọc hơn một cột văn bản rất dài:

```sql
SHOW ENGINE INNODB STATUS\G
```

`\G` là ký hiệu kết thúc statement của MySQL client, không phải một phần của cú pháp SQL gửi từ ứng dụng. Trong JDBC, ứng dụng hoặc công cụ chỉ nhận kết quả SQL, hãy chạy:

```sql
SHOW ENGINE INNODB STATUS;
```

Kết quả thường có các cột `Type`, `Name` và `Status`; nội dung chẩn đoán nằm trong cột `Status`. Tài khoản cần quyền `PROCESS` để xem trạng thái InnoDB. Nếu không có quyền, yêu cầu DBA cấp quyền phù hợp theo nguyên tắc tối thiểu hoặc nhờ người có quyền thực hiện lệnh.

Nên lưu lại thời điểm lấy mẫu và phiên bản MySQL cùng với kết quả. Nếu so sánh hai lần chụp, hãy ghi rõ khoảng cách thời gian, tải ứng dụng và sự kiện đang diễn ra để tránh so sánh các bộ đếm tích lũy ở hai ngữ cảnh khác nhau.

### 2. Các khu vực chính trong kết quả

Kết quả có thể thay đổi theo phiên bản, cấu hình và hoạt động hiện tại, nhưng thường chứa những phần sau:

| Khu vực | Nội dung cần quan sát | Dùng khi điều tra |
| --- | --- | --- |
| `BACKGROUND THREAD` | Hoạt động của master thread và các background thread | Tìm dấu hiệu hoạt động nền bất thường |
| `SEMAPHORES` | Mutex, rw-lock, spin rounds, OS waits và contention nội bộ | Điều tra chờ đồng bộ trong InnoDB |
| `LATEST DETECTED DEADLOCK` | Hai hoặc nhiều transaction, khóa đang giữ/chờ và transaction bị rollback | Phân tích deadlock gần nhất |
| `TRANSACTIONS` | Transaction đang mở, trạng thái, số row lock, undo entries và query | Tìm transaction lâu, lock wait và read view cũ |
| `FILE I/O` | Pending read/write, I/O thread và số lượt đọc/ghi/flush | Điều tra tải I/O và hàng đợi ghi |
| `INSERT BUFFER AND ADAPTIVE HASH INDEX` | Hoạt động change buffer và adaptive hash index | Tìm hiểu chi phí cập nhật secondary index và truy cập index |
| `LOG` | LSN, redo log flush và checkpoint | Điều tra áp lực redo/checkpoint |
| `BUFFER POOL AND MEMORY` | Page trong buffer pool, free/dirty page, read-ahead và flush | Điều tra cache và page I/O |
| `ROW OPERATIONS` | Bộ đếm insert/update/delete/read và hoạt động xử lý hàng | Nhìn xu hướng hoạt động của engine |

Không phải mọi phiên bản đều hiển thị đúng cùng tên, cùng thứ tự hoặc cùng tập trường. Hãy đọc nhãn thực tế trong output của máy chủ đang chạy.

### 3. Đọc LATEST DETECTED DEADLOCK

`LATEST DETECTED DEADLOCK` mô tả deadlock gần nhất mà InnoDB phát hiện. Phần này thường cho biết:

1. Thời điểm deadlock được phát hiện.
2. Các transaction tham gia, transaction ID và trạng thái.
3. Câu SQL gần nhất hoặc câu SQL đang chờ của từng transaction.
4. Khóa mỗi transaction đang giữ (`HOLDS THE LOCK(S)`).
5. Khóa mà transaction đang yêu cầu (`WAITING FOR THIS LOCK TO BE GRANTED`).
6. Bảng, index, kiểu khóa và thông tin record/index entry liên quan.
7. Transaction được chọn làm nạn nhân và bị rollback (`WE ROLL BACK TRANSACTION`).

Ví dụ minh họa rút gọn:

```text
------------------------
LATEST DETECTED DEADLOCK
------------------------
*** (1) TRANSACTION:
TRANSACTION 81001, ACTIVE 8 sec starting index read
mysql tables in use 1, locked 1
UPDATE account SET balance = balance - 10 WHERE id = 2

*** (1) HOLDS THE LOCK(S):
RECORD LOCKS ... index PRIMARY ... lock_mode X locks rec but not gap

*** (1) WAITING FOR THIS LOCK TO BE GRANTED:
RECORD LOCKS ... index PRIMARY ... lock_mode X locks rec but not gap waiting

*** (2) TRANSACTION:
TRANSACTION 81002, ACTIVE 5 sec starting index read
UPDATE account SET balance = balance + 10 WHERE id = 1

*** (2) HOLDS THE LOCK(S):
RECORD LOCKS ... index PRIMARY ... lock_mode X locks rec but not gap

*** (2) WAITING FOR THIS LOCK TO BE GRANTED:
RECORD LOCKS ... index PRIMARY ... lock_mode X locks rec but not gap waiting

*** WE ROLL BACK TRANSACTION (2)
```

Đây là ví dụ minh họa cấu trúc, không phải output được lấy từ một server thật. Khi đọc output thực, cần ghép đúng phần `HOLDS` và `WAITING` theo từng transaction để dựng chu trình chờ. Dòng cuối cho biết transaction nào InnoDB đã chọn để rollback trong deadlock đó.

Thông tin `space id`, `page no`, `heap no`, `index` và record dump giúp xác định chính xác vị trí khóa ở mức InnoDB. Với người vận hành ứng dụng, tên bảng, tên index, câu SQL và thứ tự transaction thường là điểm bắt đầu dễ hành động nhất.

### 4. Hiểu chu trình deadlock qua hai phiên

Deadlock xảy ra khi các transaction tạo thành chu trình chờ: mỗi transaction giữ tài nguyên mà transaction khác cần, và không transaction nào có thể tiếp tục nếu không có một bên bị rollback.

Giả sử bảng tài khoản:

```sql
CREATE TABLE account (
    id BIGINT NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO account (id, balance)
VALUES (1, 1000.00), (2, 1000.00);
```

Hai phiên chuyển tiền theo thứ tự khóa ngược nhau.

**Phiên A:**

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 100 WHERE id = 1;
-- A giữ khóa X trên account.id = 1.
```

**Phiên B:**

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 50 WHERE id = 2;
-- B giữ khóa X trên account.id = 2.
```

**Phiên A tiếp tục:**

```sql
UPDATE account SET balance = balance + 100 WHERE id = 2;
-- A phải chờ khóa id = 2 do B đang giữ.
```

**Phiên B tiếp tục:**

```sql
UPDATE account SET balance = balance + 50 WHERE id = 1;
-- B phải chờ khóa id = 1 do A đang giữ.
-- InnoDB phát hiện chu trình và rollback một transaction.
```

Sau khi deadlock xảy ra, một phiên nhận lỗi `ERROR 1213 (40001): Deadlock found when trying to get lock; try restarting transaction`. Transaction được chọn làm nạn nhân bị rollback toàn bộ. Transaction còn lại có thể tiếp tục sau khi khóa được giải phóng. Phiên nào bị rollback phụ thuộc quyết định của InnoDB; không nên giả định luôn là phiên thực hiện câu lệnh cuối cùng.

Ngay sau sự cố, chạy `SHOW ENGINE INNODB STATUS\G` để xem deadlock gần nhất. Đối chiếu các hàng `id = 1` và `id = 2`, khóa đang giữ/chờ và câu SQL của từng phiên. Nguyên nhân trực tiếp ở ví dụ là hai luồng cập nhật cùng tập hàng nhưng theo thứ tự khác nhau.

### 5. Phân biệt deadlock và lock wait timeout

Deadlock và lock wait timeout đều khiến một câu lệnh ghi không thể tiếp tục, nhưng bản chất khác nhau:

| Hiện tượng | Deadlock | Lock wait timeout |
| --- | --- | --- |
| Nguyên nhân | Có chu trình chờ giữa các transaction | Một transaction chờ khóa quá thời gian cho phép |
| Phát hiện | InnoDB deadlock detector phát hiện chu trình | Hết thời gian chờ theo `innodb_lock_wait_timeout` |
| Lỗi thường gặp | `1213`, SQLSTATE `40001` | `1205`, SQLSTATE `HY000` |
| Phạm vi rollback mặc định | Transaction nạn nhân bị rollback toàn bộ | Thông thường statement bị rollback; toàn transaction chỉ rollback nếu cấu hình `innodb_rollback_on_timeout` bật |
| Bằng chứng | Có phần `LATEST DETECTED DEADLOCK` | Có thể không có deadlock entry; cần xem lock wait hiện tại hoặc log ứng dụng |

Không phải mọi lock wait lâu đều là deadlock. Một transaction có thể giữ khóa trong thời gian dài mà không có chu trình chờ; khi đó transaction khác chờ đến timeout. Nếu chỉ xem `LATEST DETECTED DEADLOCK`, bạn có thể bỏ sót nguyên nhân của một lock wait timeout.

Kiểm tra các biến liên quan:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_lock_wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'innodb_rollback_on_timeout';
SHOW GLOBAL VARIABLES LIKE 'innodb_deadlock_detect';
```

Ứng dụng cần phân biệt hai loại lỗi để quyết định retry. Với lỗi deadlock, transaction nạn nhân đã rollback toàn bộ; cần chạy lại toàn bộ đơn vị nghiệp vụ. Với timeout, phải xác định trạng thái transaction theo cấu hình và xử lý rollback rõ ràng trước khi retry.

### 6. Đọc TRANSACTIONS để tìm transaction giữ khóa lâu

Phần `TRANSACTIONS` thường liệt kê transaction đang hoạt động, transaction đang chờ và một số trạng thái nội bộ. Các trường đáng chú ý gồm:

- `TRANSACTION ... ACTIVE ...`: transaction ID và thời gian đã hoạt động.
- `LOCK WAIT`: transaction đang chờ khóa.
- `mysql tables in use` / `locked`: số bảng đang được sử dụng hoặc khóa theo cách engine báo cáo.
- `lock struct(s)`, `row lock(s)`: cấu trúc khóa và số row lock mà transaction đang giữ.
- `undo log entries`: lượng thay đổi cần xử lý khi rollback/purge.
- `MySQL thread id` và `query id`: giúp liên hệ với connection/processlist.
- `Trx read view`: thông tin snapshot của consistent read trong một số trạng thái.

Transaction mở lâu có thể giữ row lock, ngăn purge dọn phiên bản cũ hoặc giữ metadata lock ở cấp SQL. Một transaction `Sleep` trong processlist vẫn có thể đang mở transaction nếu ứng dụng đã bắt đầu transaction nhưng chưa commit/rollback. Không chỉ tìm query đang chạy; hãy tìm cả transaction lâu không có câu lệnh hiện tại.

Phần đầu hoặc cuối `TRANSACTIONS` có thể hiển thị `History list length`. Đây là chỉ báo về lượng lịch sử undo đang chờ purge, không phải số hàng đang bị khóa. Nếu giá trị tăng kéo dài, hãy kiểm tra transaction/read view cũ, tốc độ phát sinh undo, khả năng purge và tải ghi. Một lần chụp đơn lẻ không đủ kết luận purge bị nghẽn; cần so sánh theo thời gian.

### 7. Đọc FILE I/O và LOG

`FILE I/O` hiển thị các hoạt động đọc/ghi file của InnoDB, bao gồm pending reads/writes, I/O thread, số lần đọc/ghi và flush. Những số liệu này giúp nhận biết có hàng đợi I/O hay không, nhưng nhiều bộ đếm là tích lũy từ lúc khởi động hoặc từ mốc reset. Nên so sánh hai lần chụp cách nhau một khoảng thời gian để tính xu hướng thay vì diễn giải tổng số lớn như tải hiện tại.

Trong `LOG`, chú ý các thông tin như:

- Log sequence number (LSN): vị trí log hiện tại.
- Log flushed up to: mốc redo đã được flush.
- Pages flushed up to hoặc checkpoint LSN: mốc checkpoint tương ứng.
- Pending log flushes hoặc pending checkpoint writes nếu có.
- Log i/o và các bộ đếm liên quan tới ghi redo.

Khoảng cách giữa LSN hiện tại và checkpoint có thể phản ánh lượng redo cần xử lý trước khi checkpoint tiến lên. Nếu checkpoint bị tụt xa trong thời gian dài, hệ thống có thể chịu áp lực flush dirty page hoặc I/O. Không kết luận chỉ từ một giá trị; đối chiếu tốc độ tăng LSN, tốc độ checkpoint, redo capacity, write throughput và độ trễ storage.

### 8. Đọc BUFFER POOL AND MEMORY

Buffer pool giữ cache các data page và index page của InnoDB. Trong phần này, các chỉ số thường gặp gồm:

| Chỉ số | Ý nghĩa thực tế |
| --- | --- |
| `Buffer pool size` | Số page hoặc dung lượng buffer pool được cấu hình/cấp phát |
| `Free buffers` | Page đang rảnh, sẵn sàng được dùng |
| `Database pages` | Page dữ liệu/index đang nằm trong buffer pool |
| `Modified db pages` | Dirty page chưa được ghi hoàn toàn xuống tablespace |
| `Pending reads` | Số yêu cầu đọc page còn chờ |
| `Pending writes` | Số yêu cầu ghi page còn chờ theo nhóm flush được báo cáo |
| `Pages made young/not young` | Hoạt động đưa page vào vùng young/old của LRU |
| `Pages read`, `created`, `written` | Bộ đếm hoạt động page tương ứng |

Một tỷ lệ `Free buffers` thấp không tự động có nghĩa thiếu bộ nhớ. InnoDB có thể sử dụng phần lớn buffer pool để cache page hữu ích; page cũ được thay thế theo thuật toán LRU khi cần. Cần xem đồng thời buffer pool read requests, physical reads, dirty page, pending I/O, hit ratio theo khoảng thời gian và độ trễ storage.

Nếu `Modified db pages` cao, hãy xem tốc độ flush và checkpoint. Nếu `Pending reads` tăng cùng physical read latency, workload có thể đang cần nhiều page chưa nằm trong cache hoặc storage không đáp ứng. Nếu số page đọc cao nhưng truy vấn không cải thiện, kiểm tra index, working set và mẫu truy cập ngẫu nhiên.

### 9. Đọc SEMAPHORES và contention nội bộ

`SEMAPHORES` mô tả các mutex/rw-lock nội bộ mà thread InnoDB sử dụng để đồng bộ cấu trúc dữ liệu. Có thể thấy số vòng spin, OS waits, số lần signal hoặc thông tin thread đang chờ.

Phần này không đồng nghĩa với row lock của SQL. Row lock là khóa logic trên record/index dùng để phối hợp transaction; semaphore là cơ chế đồng bộ nội bộ của engine. Nếu thấy nhiều OS waits hoặc contention tăng, cần đối chiếu CPU, số thread đồng thời, cấu trúc workload, phiên bản MySQL và các wait event trong Performance Schema.

Không dùng một dòng `spin rounds` cao để kết luận có lỗi. Ý nghĩa phụ thuộc thời gian lấy mẫu, CPU, tải và thuật toán đồng bộ của phiên bản. Nếu vấn đề kéo dài, hãy thu thập nhiều mẫu và kiểm tra wait summary trước khi thay đổi cấu hình.

### 10. Đọc INSERT BUFFER, ADAPTIVE HASH INDEX và ROW OPERATIONS

Phần `INSERT BUFFER AND ADAPTIVE HASH INDEX` (tên có thể thay đổi theo phiên bản) cung cấp thông tin về change buffer và adaptive hash index. Change buffer có thể trì hoãn một số thay đổi đối với secondary index chưa nằm trong buffer pool để hợp nhất I/O sau; adaptive hash index là cấu trúc hash nội bộ giúp tăng tốc một số truy cập lặp lại vào B-tree. Các chỉ số này chỉ có ý nghĩa khi đặt trong bối cảnh workload và cấu hình.

`ROW OPERATIONS` cho biết tốc độ hoặc bộ đếm hàng được đọc, insert, update và delete. Đây là chỉ báo hoạt động của storage engine, không phải thống kê truy vấn theo từng bảng. Muốn biết câu SQL nào tạo tải, kết hợp Performance Schema statement digest, slow query log và processlist.

### 11. Ghi mọi deadlock vào error log

`SHOW ENGINE INNODB STATUS` chỉ giữ phần deadlock gần nhất. Nếu một deadlock mới xuất hiện, phần `LATEST DETECTED DEADLOCK` sẽ được thay bằng sự kiện mới; vì vậy, khi sự cố xảy ra nhiều lần, có thể mất bằng chứng của các deadlock trước đó nếu chưa thu thập kịp.

Để ghi mọi deadlock được phát hiện vào MySQL error log, có thể bật:

```sql
SET GLOBAL innodb_print_all_deadlocks = ON;
```

Kiểm tra trạng thái:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_print_all_deadlocks';
```

Sau khi thu thập đủ thông tin hoặc kết thúc giai đoạn điều tra, có thể tắt:

```sql
SET GLOBAL innodb_print_all_deadlocks = OFF;
```

Biến này giúp lưu lại nhiều deadlock hơn trong error log, nhưng log có thể tăng nhanh khi ứng dụng có lỗi đồng thời thường xuyên. Cần theo dõi dung lượng log, quyền truy cập và chính sách lưu trữ. Thay đổi runtime không nhất thiết còn hiệu lực sau restart; nếu muốn giữ cấu hình, phải dùng quy trình cấu hình máy chủ phù hợp.

### 12. Bật InnoDB Monitor output để theo dõi định kỳ

Có thể cấu hình InnoDB ghi monitor output định kỳ vào error log:

```sql
SET GLOBAL innodb_status_output = ON;
```

Để bổ sung chi tiết khóa trong monitor output:

```sql
SET GLOBAL innodb_status_output_locks = ON;
```

Khi không còn cần theo dõi, tắt để tránh log tăng không cần thiết:

```sql
SET GLOBAL innodb_status_output_locks = OFF;
SET GLOBAL innodb_status_output = OFF;
```

Monitor output định kỳ có thể hữu ích trong một đợt điều tra kéo dài, nhưng không nên bật vô thời hạn nếu không có nhu cầu. Hãy xác định trước nơi lưu error log, dung lượng, retention và cách lọc dữ liệu. Các biến là cấu hình ở phạm vi global; cần quyền quản trị phù hợp.

### 13. Dùng Performance Schema để xem lock wait hiện tại

InnoDB Status hữu ích cho ảnh chụp tổng thể và deadlock gần nhất. Để xem quan hệ chờ khóa hiện tại theo cấu trúc có thể truy vấn, MySQL 8.0 cung cấp `performance_schema.data_locks` và `performance_schema.data_lock_waits`.

Liệt kê lock đang được InnoDB theo dõi:

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks;
```

Xem cặp khóa đang chờ và khóa đang chặn:

```sql
SELECT
    r.ENGINE_TRANSACTION_ID AS waiting_trx,
    r.THREAD_ID AS waiting_thread,
    r.OBJECT_SCHEMA,
    r.OBJECT_NAME,
    r.INDEX_NAME,
    r.LOCK_MODE AS waiting_lock_mode,
    b.ENGINE_TRANSACTION_ID AS blocking_trx,
    b.THREAD_ID AS blocking_thread,
    b.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

Nếu có `sys` schema, view `sys.innodb_lock_waits` cung cấp cách đọc dễ hơn:

```sql
SELECT
    waiting_pid,
    waiting_query,
    blocking_pid,
    blocking_query,
    locked_table,
    locked_index,
    waiting_lock_mode,
    blocking_lock_mode,
    wait_age
FROM sys.innodb_lock_waits;
```

Các view này tập trung vào lock đang tồn tại/chờ tại thời điểm truy vấn. Deadlock đã được giải quyết có thể không còn xuất hiện ở `data_lock_waits`; hãy dùng `LATEST DETECTED DEADLOCK` hoặc error log để xem bằng chứng deadlock đã xảy ra.

### 14. Ghép transaction với connection và câu SQL

Từ `THREAD_ID` trong Performance Schema, có thể tìm processlist ID và thông tin statement hiện tại. Ví dụ:

```sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
ORDER BY PROCESSLIST_TIME DESC;
```

Với connection ID đã xác định, có thể xem câu SQL đang chạy bằng `SHOW FULL PROCESSLIST`. Để xem transaction InnoDB đang mở:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query,
    trx_rows_locked,
    trx_rows_modified
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Ghép `PROCESSLIST_ID` hoặc `trx_mysql_thread_id` với thông tin thread/transaction để tìm phiên giữ khóa. Lưu ý processlist có thể hiển thị `Sleep` trong khi connection vẫn giữ transaction mở; `PROCESSLIST_INFO` khi đó có thể là `NULL`, nên không chỉ lọc các session đang chạy câu SQL.

### 15. Quy trình điều tra khi ứng dụng báo deadlock

Khi nhận lỗi `1213`, hãy thu thập bằng chứng trước khi thay đổi cấu hình hoặc ép thứ tự truy vấn:

1. Ghi lại thời điểm, endpoint/job, request ID, transaction nghiệp vụ và câu SQL liên quan từ log ứng dụng.
2. Lấy `SHOW ENGINE INNODB STATUS\G` ngay sau khi phát hiện để lưu deadlock gần nhất.
3. Nếu deadlock xảy ra thường xuyên, bật `innodb_print_all_deadlocks` trong khoảng điều tra và thu thập error log.
4. Đọc từng transaction trong deadlock: bảng, index, câu SQL, khóa đang giữ và khóa đang chờ.
5. Dựng chu trình chờ; xác định thứ tự truy cập hàng/index giữa các luồng nghiệp vụ.
6. Kiểm tra index và `EXPLAIN` để biết câu lệnh có quét/khóa phạm vi rộng ngoài dự kiến không.
7. Sửa thiết kế transaction: truy cập tài nguyên theo thứ tự nhất quán, giữ transaction ngắn, thêm index phù hợp hoặc dùng câu cập nhật nguyên tử.
8. Retry toàn bộ transaction bị rollback với giới hạn số lần, jitter/backoff và idempotency.
9. Theo dõi tỷ lệ deadlock, latency, lock wait và tác động sau khi thay đổi.

Nếu ứng dụng chỉ log câu SQL cuối cùng mà không ghi request/transaction context, sẽ khó tái dựng thứ tự thao tác. Hãy bổ sung correlation ID, tên nghiệp vụ và thời điểm bắt đầu/kết thúc transaction vào log ứng dụng.

### 16. Cách giảm deadlock sau khi tìm được nguyên nhân

Không có một cấu hình duy nhất loại bỏ mọi deadlock. Các biện pháp nên dựa trên chu trình thực tế:

- **Thứ tự khóa nhất quán:** nếu nhiều luồng cập nhật cùng hai tài khoản, luôn khóa theo `id` tăng dần.
- **Transaction ngắn:** không gọi HTTP, gửi email hoặc chờ người dùng trong khi giữ row lock.
- **Index phù hợp:** giảm số record phải quét và khóa; kiểm tra kế hoạch của `UPDATE`/`DELETE`.
- **Cập nhật nguyên tử:** đưa điều kiện nghiệp vụ vào một câu `UPDATE` thay vì đọc rồi ghi bằng nhiều bước không được khóa.
- **Batch nhỏ:** chia thao tác hàng loạt thành các transaction có giới hạn.
- **Retry đúng cách:** retry toàn bộ transaction nạn nhân, không chỉ chạy lại câu lệnh cuối cùng.
- **Tính idempotent:** bảo đảm retry không tạo tác động nghiệp vụ trùng.

Không nên tắt `innodb_deadlock_detect` chỉ để giảm CPU khi chưa đo và hiểu nguyên nhân. Tắt detector làm InnoDB dựa nhiều hơn vào timeout để xử lý chu trình chờ, khiến transaction có thể phải chờ lâu hơn trước khi được giải phóng. Chỉ cân nhắc thay đổi này với workload có đặc điểm tranh chấp đã được đo đạc và có thiết kế thay thế phù hợp.

### 17. Những nhầm lẫn thường gặp khi đọc InnoDB Status

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `LATEST DETECTED DEADLOCK` là lịch sử tất cả deadlock | Đây chỉ là deadlock gần nhất; bật `innodb_print_all_deadlocks` nếu cần ghi mọi sự kiện vào error log |
| Không có deadlock section nghĩa là không có lock wait | Lock wait có thể tồn tại mà không tạo chu trình; xem `data_lock_waits` và `sys.innodb_lock_waits` |
| `History list length` là số row đang bị khóa | Đây là chỉ báo về lịch sử undo chờ purge, cần đọc cùng transaction lâu và hoạt động purge |
| `Free buffers` thấp luôn là thiếu RAM | Buffer pool được dùng để cache; cần xem physical read, pending I/O và hit behavior |
| `Pending writes` cao trong một mẫu là lỗi storage | Cần so sánh theo thời gian và đối chiếu latency, throughput, checkpoint |
| `Sleep` nghĩa là session không giữ tài nguyên | Session idle vẫn có thể giữ transaction và lock nếu chưa commit/rollback |
| Deadlock luôn do thiếu index | Thứ tự khóa ngược nhau có thể gây deadlock dù lookup dùng primary key hiệu quả |
| Tăng timeout sẽ sửa deadlock | Timeout không phá chu trình deadlock; detector xử lý deadlock riêng, còn timeout xử lý chờ quá lâu không có chu trình |

### 18. Bảo vệ thông tin khi chia sẻ output

InnoDB Status có thể chứa câu SQL, tên schema/bảng, tên người dùng, host, giá trị dữ liệu trong record dump và thông tin về hoạt động nghiệp vụ. Trước khi gửi output lên ticket công khai hoặc diễn đàn, hãy loại bỏ mật khẩu, token, email, dữ liệu cá nhân, literal nhạy cảm, hostname và tên database nội bộ theo chính sách của tổ chức.

Chỉ cấp quyền `PROCESS` và quyền đọc Performance Schema cho tài khoản vận hành cần thiết. Không cấp quyền rộng cho tài khoản ứng dụng chỉ để hỗ trợ chẩn đoán. Lưu error log và snapshot theo thời hạn phù hợp, hạn chế người đọc và tránh ghi lại dữ liệu nhạy cảm ngoài phạm vi cần thiết.

### 19. Checklist thực hành

1. Chạy `SHOW ENGINE INNODB STATUS\G` bằng tài khoản có quyền phù hợp.
2. Xác định thời điểm lấy mẫu và phiên bản MySQL.
3. Đọc `LATEST DETECTED DEADLOCK`, xác định hai transaction, lock held, lock waiting và victim.
4. Phân biệt lỗi deadlock `1213` với lock wait timeout `1205`.
5. Đọc `TRANSACTIONS` để tìm transaction lâu, row lock, undo entry và read view cũ.
6. Đọc `FILE I/O`, `LOG`, `BUFFER POOL AND MEMORY` và `SEMAPHORES` theo triệu chứng, so sánh nhiều mẫu.
7. Dùng `performance_schema.data_locks`, `data_lock_waits` hoặc `sys.innodb_lock_waits` để xem chờ khóa hiện tại.
8. Ghép thread/connection với processlist và `information_schema.innodb_trx`.
9. Bật `innodb_print_all_deadlocks` hoặc monitor output chỉ trong thời gian cần thiết và kiểm soát dung lượng error log.
10. Sửa thứ tự khóa, index hoặc phạm vi transaction dựa trên bằng chứng; retry toàn bộ transaction một cách an toàn.

`SHOW ENGINE INNODB STATUS` cung cấp bức tranh nội bộ hữu ích để bắt đầu điều tra, đặc biệt là phần deadlock gần nhất và danh sách transaction. Kết hợp nó với lock wait hiện tại trong Performance Schema, processlist, error log và kế hoạch truy vấn sẽ giúp chuyển từ triệu chứng “ứng dụng bị treo hoặc deadlock” sang nguyên nhân cụ thể ở transaction, index và thứ tự khóa.
