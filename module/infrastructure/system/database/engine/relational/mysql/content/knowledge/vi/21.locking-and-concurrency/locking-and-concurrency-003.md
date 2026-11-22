# Khóa theo chỉ mục được quét và ảnh hưởng của kế hoạch thực thi

Trong InnoDB, khóa của một câu lệnh UPDATE, DELETE hoặc locking read thường được đặt trên các index record mà engine truy cập khi thực hiện tìm kiếm. Vì vậy, phạm vi khóa không chỉ phụ thuộc vào số hàng cuối cùng thỏa điều kiện WHERE; nó còn phụ thuộc vào chỉ mục được chọn, vùng index phải quét, isolation level và cách MySQL đánh giá điều kiện lọc.

Một câu UPDATE dự kiến sửa 10 hàng có thể phải duyệt một vùng index lớn hơn nhiều. Nếu không có index phù hợp, optimizer có thể chọn full table scan; InnoDB phải kiểm tra nhiều record hơn và có thể giữ nhiều khóa hơn trong lúc thực thi. Ngược lại, một index ghép đúng thứ tự có thể thu hẹp vùng tìm kiếm, giảm số record phải khóa và hạn chế transaction khác phải chờ.

Trong module **DATABASE_MYSQL**, hiểu mối liên hệ giữa execution plan và lock footprint giúp chẩn đoán lock wait, giảm deadlock và thiết kế index cho workload ghi. Bài học này tập trung vào cách InnoDB khóa index record, cách access path làm thay đổi phạm vi khóa, sự khác nhau giữa REPEATABLE READ và READ COMMITTED, cùng quy trình kiểm tra bằng EXPLAIN và Performance Schema.

## 1. Vì sao chỉ mục quyết định phạm vi khóa?

InnoDB tổ chức dữ liệu bằng clustered index và các secondary index. Một câu lệnh tìm hàng thông qua một index sẽ đi qua các entry của B-tree. Khi câu lệnh cần khóa dữ liệu, InnoDB đặt khóa trên index record liên quan; với secondary index, engine còn cần bảo vệ record tương ứng trong clustered index khi thực hiện thao tác ghi hoặc locking read.

Hãy phân biệt ba khái niệm:

- **Rows matched:** số hàng cuối cùng thỏa điều kiện WHERE.
- **Rows examined/scanned:** số record hoặc entry optimizer và storage engine phải xem xét để tìm kết quả.
- **Lock footprint:** tập index record và khoảng index mà transaction thực sự khóa trong quá trình thực thi.

Ba đại lượng này liên quan với nhau nhưng không nhất thiết bằng nhau. Một kế hoạch quét rộng có thể làm tăng lock footprint dù số hàng cập nhật cuối cùng nhỏ. Các chi tiết giải phóng khóa cho hàng không thỏa điều kiện còn phụ thuộc isolation level và cách điều kiện được đánh giá.

### 1.1. Khóa gắn với index record

InnoDB không khóa một khái niệm hàng logic trừu tượng theo cách độc lập với index. Record lock bảo vệ index record. Gap lock bảo vệ khoảng giữa các index record. Next-key lock kết hợp record lock với gap ngay trước record đó.

Vì vậy, nếu UPDATE dùng secondary index để tìm hàng, khóa có thể xuất hiện trên entry của secondary index và record tương ứng trong clustered index. Khi kiểm tra lock, bạn có thể thấy tên index khác với PRIMARY.

Ví dụ bảng:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_tenant_status_created (
        tenant_id,
        status,
        created_at
    )
) ENGINE = InnoDB;
```

Truy vấn:

```sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

Nếu optimizer dùng idx_tenant_status_created, InnoDB có thể tìm trong một vùng hẹp được xác định bởi tenant_id, status và khoảng created_at. Nếu không có index phù hợp, server có thể phải đọc nhiều hàng hơn để kiểm tra ba điều kiện.

## 2. Phân biệt loại access path trong execution plan

Execution plan mô tả cách optimizer dự định tìm dữ liệu. Các giá trị trong cột type của EXPLAIN cho biết kiểu truy cập, nhưng không tự nó cho biết chính xác số lock sẽ được giữ.

Một số access type thường gặp:

| Access type | Ý nghĩa khái quát | Tác động tiềm tàng đến lock |
|---|---|---|
| const / system | Tìm tối đa một hàng bằng khóa duy nhất hoặc bảng rất nhỏ | Thường có phạm vi hẹp |
| eq_ref | Mỗi tổ hợp hàng trước đó khớp tối đa một hàng qua unique key | Thường khóa ít record cho mỗi lần lookup |
| ref | Tìm các hàng theo giá trị index không unique | Có thể khóa nhiều entry cùng giá trị |
| range | Quét một khoảng index | Có thể khóa các record và gap trong khoảng |
| index | Quét toàn bộ một index | Phạm vi quét rộng dù chỉ đọc cấu trúc index |
| ALL | Full table scan | Có thể dẫn đến phạm vi khóa rất lớn với DML/locking read |

Không nên kết luận chỉ từ access type. Hãy xem thêm key, key_len, rows, filtered, Extra, điều kiện range và phân bố dữ liệu. Ví dụ, type=range trên một vùng rất nhỏ có thể tốt hơn ref trên một giá trị có hàng triệu bản ghi.

### 2.1. Những cột EXPLAIN cần đọc

```sql
EXPLAIN
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

Các cột quan trọng:

| Cột | Cách đọc |
|---|---|
| type | Kiểu truy cập như range, ref, eq_ref, index hoặc ALL |
| possible_keys | Các index optimizer có thể cân nhắc |
| key | Index được chọn thực tế |
| key_len | Độ dài phần index được sử dụng; giúp suy ra các key part đã tham gia |
| ref | Giá trị/cột dùng để so khớp với index |
| rows | Số hàng ước lượng cần đọc |
| filtered | Tỷ lệ phần trăm hàng ước tính còn lại sau điều kiện lọc bổ sung |
| Extra | Thông tin như Using where, Using index condition, Using temporary hoặc Using filesort |

EXPLAIN thường cung cấp ước lượng, không phải số khóa chính xác. rows và filtered không thể được dùng như số lock thực tế. Hãy kết hợp execution plan với quan sát lock tại thời điểm transaction đang mở.

Nếu phiên bản hoặc cú pháp không hỗ trợ EXPLAIN trực tiếp cho một loại DML, có thể dùng EXPLAIN cho SELECT có cùng điều kiện và JOIN để hiểu access path như một phép tham chiếu. Kế hoạch SELECT tương đương không đảm bảo hoàn toàn giống kế hoạch DML trong mọi trường hợp.

### 2.2. EXPLAIN ANALYZE không phải bộ đếm lock

Trên MySQL hỗ trợ EXPLAIN ANALYZE, câu lệnh này thực thi SELECT và hiển thị số hàng thực tế cùng thời gian ở các iterator:

```sql
EXPLAIN ANALYZE
SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

Dữ liệu thực tế giúp so sánh rows estimate với rows examined/returned. Tuy nhiên, đây là SELECT thông thường, không phải phép đo số record lock mà một UPDATE sẽ lấy. Không dùng EXPLAIN ANALYZE như công cụ chứng minh lock footprint.

EXPLAIN ANALYZE chạy truy vấn thật và có thể đọc nhiều dữ liệu, vì vậy cần chọn thời điểm phù hợp trên môi trường có tải.

## 3. Index phù hợp thu hẹp vùng quét và lock footprint

Giả sử truy vấn thường xuyên lọc theo tenant_id, status rồi giới hạn thời gian:

```sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

Index ghép:

```sql
CREATE INDEX idx_tenant_status_created
    ON orders (tenant_id, status, created_at);
```

Thứ tự cột này hỗ trợ hai điều kiện equality ở đầu index, sau đó là range trên created_at. B-tree có thể đi đến đúng vùng tenant/status và quét phần thời gian cần thiết.

### 3.1. Leftmost prefix và thứ tự cột

Index ghép (tenant_id, status, created_at) có thể phục vụ các điều kiện dựa trên:

- tenant_id
- tenant_id và status
- tenant_id, status và một khoảng created_at

Nó không trực tiếp cung cấp một vùng liên tục hiệu quả cho truy vấn chỉ lọc status hoặc chỉ lọc created_at mà không ràng buộc cột đầu tiên, trừ khi optimizer có chiến lược khác như skip scan trong các điều kiện phù hợp và phiên bản hỗ trợ.

Với điều kiện equality trên nhiều cột, các cột equality thường được đặt trước cột range. Thứ tự giữa các cột equality còn phải xét các truy vấn khác, độ chọn lọc và thứ tự sắp xếp cần phục vụ.

### 3.2. So sánh hai index

| Index | Điều kiện truy vấn | Khả năng thu hẹp |
|---|---|---|
| (tenant_id, status, created_at) | tenant_id = ?, status = ?, created_at < ? | Có thể dùng cả equality prefix và range |
| (status, created_at) | tenant_id = ?, status = ?, created_at < ? | Có thể lọc status/range; tenant_id có thể thành điều kiện bổ sung |
| (created_at) | tenant_id = ?, status = ?, created_at < ? | Quét vùng thời gian rồi kiểm tra tenant/status |
| Không có index phù hợp | Ba điều kiện trên | Có thể phải full scan |

Index không phù hợp vẫn có thể được chọn nếu optimizer ước tính nó rẻ hơn. Khi đó, số record phải kiểm tra có thể lớn hơn mong muốn và lock footprint có thể tăng.

### 3.3. Index bao phủ không đồng nghĩa không cần khóa clustered record

Covering index giúp SELECT thông thường lấy đủ cột từ secondary index mà không phải đọc clustered record. Nhưng với locking read và DML, không nên suy luận rằng covering index loại bỏ nhu cầu bảo vệ clustered record. InnoDB vẫn cần bảo vệ hàng thực sự bị khóa hoặc cập nhật.

Vì thế, thêm cột vào index để tạo covering có thể giảm I/O đọc, nhưng không tự động loại bỏ lock cần thiết của UPDATE/DELETE.

## 4. Full table scan và nguy cơ khóa quá rộng

Nếu điều kiện WHERE không có index phù hợp, optimizer có thể chọn ALL:

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE DATE(created_at) = '2025-12-31';
```

Việc gọi hàm DATE trên cột created_at thường làm index B-tree thông thường trên created_at không được dùng như một range access trực tiếp. MySQL có thể phải kiểm tra nhiều hàng để tìm các bản ghi thuộc ngày cần xử lý.

Trong locking DML, InnoDB khóa các index record mà quá trình tìm kiếm đi qua theo quy tắc của isolation level. Một scan rộng có thể tạo nhiều khóa hơn đáng kể so với số hàng cuối cùng thay đổi. Ở REPEATABLE READ, next-key locking trên phạm vi scan có thể còn ngăn insert vào các gap tương ứng.

Viết điều kiện dạng range thường giúp index hoạt động tốt hơn:

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE created_at >= '2025-12-31 00:00:00'
  AND created_at <  '2026-01-01 00:00:00';
```

Nếu workload còn lọc tenant_id, cân nhắc index ghép bắt đầu bằng tenant_id rồi created_at. Kiểm tra kế hoạch trước khi chạy UPDATE diện rộng.

### 4.1. Tránh chuyển đổi ngầm trên cột được index

So sánh:

```sql
-- Có thể làm mất range access hiệu quả tùy kiểu dữ liệu và biểu thức
SELECT order_id
FROM orders
WHERE CAST(tenant_id AS CHAR) = '42';

-- So sánh trực tiếp với kiểu số
SELECT order_id
FROM orders
WHERE tenant_id = 42;
```

Giữ kiểu dữ liệu tham số tương thích với kiểu cột, tránh bọc cột trong hàm khi không cần thiết. Điều này giúp optimizer sử dụng index dễ dự đoán hơn.

### 4.2. LIKE và wildcard đầu chuỗi

Điều kiện LIKE có wildcard đầu chuỗi thường không dùng được B-tree range theo prefix:

```sql
UPDATE customers
SET status = 'REVIEW'
WHERE email LIKE '%@example.com';
```

Nếu cần tìm theo domain thường xuyên, cân nhắc lưu domain đã chuẩn hóa vào một cột riêng và tạo index phù hợp. Không nên tạo functional index hoặc generated column mà chưa xác định rõ quy tắc chuẩn hóa và collation.

## 5. Secondary index và clustered index cùng tham gia khóa

Khi UPDATE/DELETE tìm hàng qua secondary index, InnoDB dùng entry secondary để xác định hàng và cũng cần truy cập clustered index record tương ứng để thay đổi dữ liệu hàng. Vì vậy, trong Performance Schema có thể thấy lock trên cả secondary index và PRIMARY.

Ví dụ:

```sql
UPDATE orders
SET total_amount = total_amount + 10000
WHERE tenant_id = 42
  AND status = 'PENDING';
```

Nếu dùng idx_tenant_status_created, phạm vi tìm kiếm đi qua index đó. Mỗi hàng cần cập nhật còn liên quan đến clustered record theo order_id.

Nếu cập nhật một cột xuất hiện trong secondary index, engine còn phải bảo trì index chứa cột đó. Cần phân biệt:

- **Search index:** index optimizer dùng để tìm hàng và xác định vùng scan.
- **Updated index:** các index cần bảo trì vì giá trị cột được thay đổi.
- **Clustered index:** nơi chứa record dữ liệu và khóa chính.

Một index có thể vừa là search index vừa là updated index. Việc cập nhật cột được index có thể làm phát sinh thêm công việc index và khóa, ngay cả khi điều kiện WHERE chỉ tìm một hàng.

## 6. Isolation level thay đổi cách khóa phạm vi

### 6.1. REPEATABLE READ

REPEATABLE READ là isolation level mặc định phổ biến của InnoDB. Với locking read và DML dùng range scan, InnoDB thường sử dụng next-key lock để khóa record cùng gap liên quan, nhằm ngăn transaction khác chèn phantom vào vùng đang được bảo vệ.

Ví dụ:

```sql
START TRANSACTION;

SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at >= '2026-01-01'
FOR UPDATE;
```

Nếu có index phù hợp, khóa có thể giới hạn trong vùng index được quét. Transaction khác chèn một hàng vào gap thuộc vùng đã khóa có thể phải chờ.

### 6.2. READ COMMITTED

Ở READ COMMITTED, gap locking cho search và index scan thường được tắt, ngoại trừ những trường hợp cần để kiểm tra FOREIGN KEY và duplicate-key. Record lock vẫn được dùng cho hàng cần cập nhật/khóa.

Một điểm quan trọng của READ COMMITTED là InnoDB có thể dùng semi-consistent read cho UPDATE: khi gặp hàng đang bị khóa bởi transaction khác, MySQL có thể đọc phiên bản committed gần nhất để kiểm tra WHERE; nếu hàng không thỏa điều kiện thì có thể bỏ qua và không cần chờ lấy khóa X trên hàng đó. Nếu hàng thỏa điều kiện, transaction sẽ chờ rồi đọc lại để cập nhật.

Điều này có thể làm phạm vi khóa thực tế khác REPEATABLE READ. Không nên suy ra rằng hai isolation level có lock footprint giống nhau chỉ vì execution plan giống nhau.

Kiểm tra isolation level của session:

```sql
SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@GLOBAL.transaction_isolation AS global_isolation;
```

Đổi isolation level có thể thay đổi semantics đọc, khả năng xuất hiện phantom và hành vi cạnh tranh. Hãy thử nghiệm trong môi trường kiểm soát và xác nhận yêu cầu nghiệp vụ trước khi thay đổi.

## 7. Unique lookup, range scan và gap lock

Một số mẫu truy cập thường có phạm vi khóa khác nhau:

| Mẫu truy cập | Hành vi khóa thường gặp |
|---|---|
| Tìm thấy đúng một hàng bằng toàn bộ PRIMARY/UNIQUE key | Thường khóa record, không cần gap lock trước record đó |
| Tìm bằng non-unique index | Có thể khóa nhiều record cùng giá trị và các gap liên quan ở REPEATABLE READ |
| Quét range trên index | Có thể dùng next-key lock trên phạm vi scan |
| Không tìm thấy giá trị bằng unique index | Có thể cần gap lock tại vị trí mà giá trị sẽ được chèn, tùy isolation và thao tác |
| Full table scan trong locking DML | Có thể khóa rất nhiều record và gap, gây ảnh hưởng rộng |

Các mô tả trên là quy tắc thường gặp, không phải công thức thay thế cho việc quan sát thực tế. Locking read, UPDATE, DELETE, isolation level và kiểu index đều có thể làm thay đổi chi tiết.

## 8. Kế hoạch thực thi có thể thay đổi theo thống kê

Optimizer lựa chọn index dựa trên thống kê, cardinality, selectivity, chi phí I/O/CPU và cấu trúc truy vấn. Khi dữ liệu tăng hoặc phân bố thay đổi, cùng một câu UPDATE có thể dùng access path khác.

Ví dụ:

```sql
EXPLAIN
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

Nếu trước đây key là idx_tenant_status_created nhưng sau này key trở thành một index kém chọn lọc hơn hoặc ALL, lock footprint có thể thay đổi. Hệ quả có thể là:

- Nhiều index record phải scan hơn.
- Transaction giữ lock lâu hơn.
- Nhiều transaction khác chờ cùng một vùng.
- Deadlock tăng do thứ tự truy cập record thay đổi.
- Thời gian rollback tăng khi transaction đã sửa nhiều hàng.

Khi thống kê cũ, có thể cân nhắc cập nhật bằng ANALYZE TABLE trong cửa sổ vận hành phù hợp:

```sql
ANALYZE TABLE orders;
```

ANALYZE TABLE cập nhật thống kê optimizer, không phải lệnh tối ưu tự động. Sau khi cập nhật, hãy đọc lại EXPLAIN và benchmark vì kế hoạch có thể đổi. Không chạy thay đổi thống kê tùy tiện trong lúc hệ thống đang chịu tải cao mà chưa đánh giá tác động.

## 9. Dùng EXPLAIN để kiểm tra kế hoạch trước khi ghi

Trước một UPDATE/DELETE quan trọng, hãy đọc kế hoạch:

```sql
EXPLAIN
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = 42
  AND status = 'PENDING'
  AND created_at < '2026-01-01';
```

Nếu phiên bản hỗ trợ EXPLAIN cho DML, dùng trực tiếp câu lệnh cần kiểm tra. Nếu không, dùng SELECT với cùng bảng, JOIN và điều kiện như một proxy, đồng thời hiểu rằng kế hoạch có thể khác.

Một quy trình đọc plan:

1. Kiểm tra type có phải ALL hoặc index scan toàn bộ không.
2. Kiểm tra key có phải index dự kiến không.
3. Kiểm tra key_len để biết bao nhiêu key part được dùng.
4. Xem rows ước lượng có lớn bất thường không.
5. Xem filtered và Extra để hiểu điều kiện còn phải lọc sau khi đọc index.
6. Kiểm tra điều kiện WHERE có hàm, implicit conversion hoặc wildcard đầu chuỗi không.
7. So sánh plan với dữ liệu thực tế và phân bố giá trị.

EXPLAIN không hiển thị chính xác các record lock sẽ được giữ. Nó cho biết access path để từ đó dự đoán phạm vi scan. Để xác minh lock, phải quan sát transaction đang mở.

## 10. Quan sát lock thực tế bằng Performance Schema

MySQL 8.0 cung cấp các bảng Performance Schema để quan sát lock InnoDB.

### 10.1. Các lock đang tồn tại

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
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'orders';
```

Các cột hữu ích:

- OBJECT_NAME: bảng đang được khóa.
- INDEX_NAME: index record liên quan, ví dụ PRIMARY hoặc secondary index.
- LOCK_TYPE: loại đối tượng khóa, thường là TABLE hoặc RECORD.
- LOCK_MODE: chế độ như X, S, X,GAP, X,REC_NOT_GAP hoặc các dạng intention.
- LOCK_STATUS: GRANTED hoặc WAITING.
- LOCK_DATA: giá trị khóa được hiển thị nếu có.

LOCK_DATA có thể NULL khi trang/index record không còn trong buffer pool hoặc dữ liệu không thể hiển thị theo cách đó. Không diễn giải NULL thành "không khóa".

### 10.2. Ai đang chờ ai?

```sql
SELECT
    REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx
FROM performance_schema.data_lock_waits;
```

Để lấy thông tin thread và câu lệnh, có thể JOIN với data_locks và Performance Schema threads. Tên/cột cần được xác nhận trên đúng phiên bản:

```sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    r.OBJECT_SCHEMA,
    r.OBJECT_NAME,
    r.INDEX_NAME,
    r.LOCK_MODE AS requested_mode,
    r.LOCK_DATA AS requested_data,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    b.LOCK_MODE AS blocking_mode,
    b.LOCK_DATA AS blocking_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

Kết quả giúp xác định transaction đang chờ trên index nào và transaction nào đang chặn. Để tìm câu SQL, nối transaction/thread với Performance Schema events_statements hoặc xem INFORMATION_SCHEMA.INNODB_TRX.

### 10.3. Transaction đang mở

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx;
```

Transaction lâu có thể giữ khóa và làm tăng cạnh tranh. Trước khi kết thúc transaction của ứng dụng, xác định chủ sở hữu, câu lệnh, phạm vi dữ liệu và tác động nghiệp vụ.

### 10.4. Bảng sys hỗ trợ chẩn đoán

Nếu schema sys được cài đặt và có quyền phù hợp, có thể xem view tổng hợp như sys.innodb_lock_waits:

```sql
SELECT *
FROM sys.innodb_lock_waits;
```

View giúp đọc nhanh blocking/waiting transaction. Khi cần phân tích sâu, quay lại Performance Schema để kiểm tra index, lock mode và dữ liệu cụ thể.

## 11. Thực nghiệm hai session: cùng dữ liệu, khác access path

Thí nghiệm nên chạy trong database lab với hai cửa sổ kết nối riêng. Dùng bảng nhỏ để dễ quan sát, và luôn ROLLBACK/COMMIT sau khi hoàn tất.

Tạo bảng:

```sql
CREATE TABLE lock_demo (
    id BIGINT NOT NULL,
    tenant_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_tenant_status (tenant_id, status)
) ENGINE = InnoDB;

INSERT INTO lock_demo (id, tenant_id, status, note)
VALUES
    (1, 10, 'PENDING', 'a'),
    (2, 10, 'PENDING', 'b'),
    (3, 10, 'PAID', 'c'),
    (4, 20, 'PENDING', 'd'),
    (5, 20, 'PAID', 'e');
```

### 11.1. Session A: khóa vùng theo index

Chạy ở Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM lock_demo
WHERE tenant_id = 10
  AND status = 'PENDING'
FOR UPDATE;
```

Với index idx_tenant_status, truy vấn có thể đi vào vùng khóa tenant 10 và status PENDING. Kiểm tra performance_schema.data_locks từ một session khác để quan sát lock trên index.

### 11.2. Session B: thử thao tác cùng và khác vùng

Trong Session B, thử cập nhật một hàng thuộc vùng vừa khóa:

```sql
UPDATE lock_demo
SET note = 'blocked'
WHERE id = 1;
```

Câu lệnh có thể chờ Session A vì cùng record bị khóa. Thử thao tác trên hàng thuộc tenant 20 để so sánh:

```sql
UPDATE lock_demo
SET note = 'other-range'
WHERE id = 4;
```

Nếu index range và gap không chồng lấn, thao tác này thường có thể hoàn tất. Kết quả thực tế phụ thuộc các gap được khóa, vị trí key và kế hoạch đã chọn.

Kết thúc Session A:

```sql
ROLLBACK;
```

Nếu Session B đang chờ, nó có thể tiếp tục sau khi khóa được giải phóng. Sau thí nghiệm, rollback Session B nếu cần và dọn dữ liệu lab.

### 11.3. So sánh khi bỏ index

Không xóa index trên hệ thống thật. Trong lab, có thể tạo một bảng bản sao không có idx_tenant_status hoặc dùng IGNORE INDEX để thử kế hoạch khác:

```sql
EXPLAIN
SELECT *
FROM lock_demo IGNORE INDEX (idx_tenant_status)
WHERE tenant_id = 10
  AND status = 'PENDING';
```

Sau đó thực hiện một locking read trong transaction riêng và quan sát data_locks. IGNORE INDEX ở đây chỉ để học và so sánh. Không dùng hint để ép production plan khi chưa benchmark và hiểu tác động trên mọi phân bố dữ liệu.

## 12. Khi nào plan tốt vẫn có thể gây lock contention?

Index tốt giảm vùng scan nhưng không bảo đảm không có lock wait. Một số nguyên nhân:

- Nhiều transaction cùng cập nhật một hàng nóng (hot row).
- Nhiều session cập nhật các hàng khác nhau nhưng cần cùng một unique key hoặc gap.
- Foreign key buộc kiểm tra hàng cha mà transaction khác đang khóa.
- Trigger hoặc cascade mở rộng tập hàng được sửa.
- Transaction giữ lock lâu do thực hiện công việc ngoài database trước khi commit.
- Hai transaction lấy khóa theo thứ tự khác nhau và tạo chu trình deadlock.
- Một hàng được truy cập qua nhiều index và các thao tác cập nhật giao nhau.

Khi đó, cải thiện access path chỉ giải quyết một phần. Cần xem lại mô hình dữ liệu, phân vùng workload, thứ tự cập nhật, transaction scope và chiến lược retry.

## 13. Lock order và deadlock khi kế hoạch thay đổi

Execution plan không chỉ ảnh hưởng số record scan mà còn có thể ảnh hưởng thứ tự record được truy cập. Nếu hai transaction cập nhật cùng tập hàng nhưng theo thứ tự khác nhau, nguy cơ deadlock tăng.

Ví dụ:

- Transaction A cập nhật order_id 10 rồi 20.
- Transaction B cập nhật order_id 20 rồi 10.

Mỗi transaction giữ khóa hàng đầu tiên và chờ khóa hàng thứ hai, tạo chu trình chờ.

Nếu có thể, xử lý các khóa theo thứ tự nhất quán, ví dụ tăng dần theo primary key. Khi câu lệnh dùng range scan theo một index khác, thứ tự truy cập có thể không giống thứ tự primary key. Hãy kiểm tra plan và lock thực tế thay vì giả định thứ tự SQL trong danh sách IN quyết định thứ tự khóa.

InnoDB phát hiện deadlock và rollback một transaction làm nạn nhân. Ứng dụng cần retry toàn bộ transaction có kiểm soát, dùng backoff và bảo đảm thao tác có tính idempotent khi cần. Không chỉ chạy lại câu SQL cuối cùng nếu các bước trước đã bị rollback.

## 14. Cách giảm lock footprint trong thực tế

1. **Viết điều kiện có thể dùng index.** Tránh hàm trên cột được index, ép kiểu không cần thiết và wildcard đầu chuỗi.
2. **Thiết kế composite index đúng thứ tự.** Đặt cột equality phù hợp trước cột range và cân nhắc workload còn lại.
3. **Giảm số hàng ngoài trước khi cập nhật.** Chia batch theo khóa ổn định hoặc lọc theo tenant/time range.
4. **Giữ transaction ngắn.** Không giữ khóa trong khi gọi HTTP, chờ người dùng hoặc thực hiện công việc không liên quan.
5. **Cập nhật theo thứ tự ổn định.** Giảm khả năng deadlock giữa các luồng.
6. **Không dùng locking read nếu không cần.** SELECT thông thường ở InnoDB là consistent read và không đặt row lock; FOR UPDATE/FOR SHARE chỉ dùng khi yêu cầu nghiệp vụ cần.
7. **Đánh giá isolation level theo semantics.** READ COMMITTED có thể giảm gap locking nhưng không phải giải pháp mặc định cho mọi workload.
8. **Đo trước khi thêm index.** Index mới giảm scan nhưng làm tăng chi phí ghi, dung lượng và bảo trì.
9. **Theo dõi lock wait.** Dùng data_locks, data_lock_waits, INNODB_TRX và deadlock log.
10. **Xác nhận sau khi thống kê hoặc schema đổi.** Đọc lại EXPLAIN vì plan có thể thay đổi.

### 14.1. Chia batch bằng khóa chính

Nếu cần cập nhật số lượng lớn, có thể chia thành từng lô nhỏ theo primary key:

```sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE order_id > 0
  AND order_id <= 1000
  AND status = 'PENDING';
```

Các batch tiếp theo xử lý khoảng khóa kế tiếp. Trong thực tế, cần xác định watermark, xử lý hàng mới phát sinh và bảo đảm không bỏ sót dữ liệu. Không dùng một khoảng ID cố định nếu key không phản ánh thứ tự hoặc dữ liệu có lỗ lớn mà không có quy trình theo dõi.

Batch nhỏ giảm thời gian giữ lock mỗi transaction và giúp replica theo kịp hơn trong nhiều workload, nhưng tạo thêm overhead commit. Hãy chọn kích thước dựa trên latency, throughput, lock wait và replication lag.

## 15. Quy trình điều tra lock wait do kế hoạch thực thi

Khi một UPDATE/DELETE bị chậm hoặc chặn transaction khác, thực hiện:

1. Thu thập câu SQL, bind parameter, thời gian bắt đầu và transaction ID.
2. Xác định hàng dự kiến thay đổi và số hàng thực tế bị tác động.
3. Chạy EXPLAIN cho DML nếu hỗ trợ; nếu không, dùng SELECT tương đương để xem access path.
4. Đọc type, key, key_len, rows, filtered và Extra.
5. Xác định index record và lock mode từ performance_schema.data_locks.
6. Tìm transaction chặn trong data_lock_waits và INNODB_TRX.
7. Kiểm tra isolation level, gap lock, foreign key, trigger và cascade.
8. Kiểm tra plan có thay đổi do thống kê hoặc dữ liệu phân bố khác trước đây không.
9. Thử index hoặc rewrite query trong staging; đo cả tốc độ lẫn lock footprint.
10. Kiểm thử hai session để xác nhận transaction khác còn bị chặn trên những vùng nào.
11. Theo dõi deadlock, p95/p99 latency, rows examined và throughput sau triển khai.

Không kết luận "thiếu index" chỉ từ một lock wait. Hot row, transaction dài, gap lock hoặc thứ tự cập nhật có thể là nguyên nhân chính dù plan đã dùng index tốt.

## 16. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ nhìn số hàng UPDATE thành công | Bỏ qua số record đã scan và khóa trong quá trình tìm | Đọc access path và quan sát lock |
| Thấy type=range là chắc chắn ít khóa | Range có thể rất rộng | Xem key, rows, điều kiện và phân bố dữ liệu |
| Nghĩ covering index làm UPDATE không khóa clustered record | Hiểu sai locking behavior của InnoDB | Phân biệt search index và record thực sự được cập nhật |
| Không có index vẫn chỉ khóa các hàng thỏa WHERE | Scan rộng có thể làm phạm vi khóa lớn | Tạo index phù hợp và đo lại |
| Dùng EXPLAIN ANALYZE để đếm lock | EXPLAIN ANALYZE SELECT không đo lock footprint của UPDATE | Dùng Performance Schema trong transaction thực nghiệm |
| Ép FORCE INDEX mà không benchmark | Có thể tạo plan tệ hơn khi dữ liệu thay đổi | Chỉ dùng hint sau khi đo và có lý do rõ |
| Cho rằng READ COMMITTED không có gap lock trong mọi trường hợp | Bỏ qua FK và duplicate-key checking | Hiểu ngoại lệ của isolation level |
| Nghĩ SQL ORDER BY luôn quyết định lock order | Optimizer có thể dùng access path khác | Kiểm tra plan và lock thực tế |
| Chỉ retry câu lệnh gây deadlock | Transaction trước đó đã bị rollback | Retry toàn bộ transaction |
| Thêm index mà không xét write cost | DML tốn thêm dung lượng và index maintenance | Đánh giá workload đọc/ghi tổng thể |

## 17. Ghi nhớ

- InnoDB đặt khóa trên index record và khoảng index; lock footprint chịu ảnh hưởng trực tiếp của access path.
- Số hàng được cập nhật, số hàng scan và số khóa giữ không phải lúc nào cũng bằng nhau.
- UPDATE/DELETE dùng secondary index để tìm hàng vẫn cần bảo vệ clustered record tương ứng.
- Full table scan trong locking DML có thể tạo phạm vi khóa rất rộng; index phù hợp giúp thu hẹp vùng tìm kiếm.
- Composite index nên phản ánh điều kiện equality, range và workload thực tế; leftmost prefix quyết định khả năng sử dụng.
- REPEATABLE READ thường dùng next-key locking cho range; READ COMMITTED thường giảm gap lock nhưng vẫn có ngoại lệ cho FK và duplicate-key.
- EXPLAIN cho biết access path và ước lượng; nó không hiển thị chính xác số record lock.
- EXPLAIN ANALYZE SELECT đo số hàng/thời gian thực tế của SELECT, không phải lock count của UPDATE.
- Dùng Performance Schema data_locks, data_lock_waits, INFORMATION_SCHEMA.INNODB_TRX và SHOW ENGINE INNODB STATUS để tìm lock thực tế.
- Thống kê optimizer thay đổi có thể làm plan và lock footprint đổi; đọc lại EXPLAIN sau thay đổi dữ liệu/index.
- Giảm lock wait bằng index phù hợp, transaction ngắn, batch có kiểm soát và thứ tự cập nhật nhất quán.
- Deadlock cần retry toàn bộ transaction với giới hạn hợp lý.

Khi một câu DML gây lock wait, hãy xem execution plan như bản đồ chỉ ra InnoDB phải đi qua những index record nào. Đối chiếu bản đồ đó với lock thực tế sẽ giúp tìm ra vùng scan quá rộng, index chưa phù hợp hoặc điểm nóng cần xử lý.

