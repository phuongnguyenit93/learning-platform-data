# Thêm cột, đổi kiểu, tạo chỉ mục và thay đổi khóa chính trên bảng lớn

Bài học này thuộc module **DATABASE_MYSQL**. Khi phát triển ứng dụng, schema thường phải thay đổi cùng với yêu cầu nghiệp vụ: thêm thuộc tính mới, mở rộng kiểu dữ liệu, bổ sung index để tối ưu truy vấn hoặc thay đổi khóa chính. Trên bảng nhỏ, các thao tác này thường hoàn tất nhanh. Trên bảng có hàng triệu hoặc hàng tỷ bản ghi, một lệnh `ALTER TABLE` có thể đọc và ghi lại lượng dữ liệu rất lớn, tiêu tốn I/O, dung lượng, redo/binlog và gây gián đoạn ứng dụng.

Mục tiêu của schema evolution là thay đổi cấu trúc có kiểm soát trong khi giữ dữ liệu đúng và dịch vụ hoạt động trong giới hạn cho phép. Cần hiểu thuật toán DDL của InnoDB, mức khóa, metadata lock, tác động lên replication và cách triển khai theo nhiều bước. Không thể kết luận một lệnh là “online” chỉ từ tên thao tác; phải kiểm tra khả năng hỗ trợ của phiên bản MySQL, storage engine và định nghĩa bảng cụ thể.

## 1. Vì sao thay đổi schema trên bảng lớn cần kế hoạch?

Một bảng InnoDB lớn có thể gồm data pages, clustered index, nhiều secondary index và các metadata liên quan. Khi thay đổi cấu trúc, MySQL có thể:

- Chỉ cập nhật metadata mà không di chuyển các hàng dữ liệu.
- Tạo lại một index nhưng giữ nguyên cấu trúc bảng.
- Tạo lại bảng hoặc clustered index, sau đó xây dựng lại các index liên quan.
- Sao chép bảng sang cấu trúc mới, chuyển dữ liệu và thay thế bảng cũ.

Chi phí phụ thuộc vào số hàng, kích thước hàng, tổng dung lượng index, kiểu dữ liệu, khóa ngoại, workload ghi và tài nguyên storage. Một thao tác chạy vài giây trên bản sao nhỏ có thể kéo dài hàng giờ trên production.

Các rủi ro thường gặp:

1. **Downtime hoặc query bị chặn:** DDL cần metadata lock ở một số thời điểm; thao tác không hỗ trợ concurrent DML có thể giữ khóa lâu.
2. **Hết dung lượng:** quá trình rebuild có thể cần thêm chỗ cho bảng/index mới, file tạm, redo log và binary log.
3. **Tăng tải:** quét bảng và tạo index tiêu thụ CPU, I/O, buffer pool và băng thông storage.
4. **Replication lag:** thay đổi schema hoặc lượng binlog phát sinh có thể khiến replica chậm áp dụng.
5. **Sai lệch dữ liệu:** đổi kiểu có thể làm tròn, cắt chuỗi, tràn số hoặc thay đổi cách so sánh.
6. **Rollback khó:** nhiều DDL gây implicit commit; không thể dựa vào `ROLLBACK` để hoàn tác như một transaction DML thông thường.

Vì vậy, hãy khảo sát, thử nghiệm, đo thời gian và chuẩn bị phương án quay lui trước khi chạy DDL trên bảng lớn.

## 2. Thuật toán DDL của InnoDB

MySQL cung cấp các lựa chọn `ALGORITHM` để xác định cách thực hiện một số thay đổi bảng. Các thuật toán chính:

| Thuật toán | Cách hoạt động khái quát | Tác động |
|---|---|---|
| `INSTANT` | Thay đổi metadata, không rebuild bảng | Thường hoàn tất rất nhanh; có giới hạn và điều kiện hỗ trợ theo phiên bản/định nghĩa bảng |
| `INPLACE` | Storage engine thực hiện thay đổi mà không dùng quy trình copy toàn bảng của server | Có thể vẫn rebuild bảng hoặc index; nhiều thao tác cho phép DML đồng thời |
| `COPY` | Tạo bản sao bảng theo cấu trúc mới, sao chép dữ liệu rồi thay thế | Có thể tốn thời gian và dung lượng lớn; thường hạn chế DML trong quá trình copy |

**`INPLACE` không có nghĩa là không rebuild.** Ví dụ, thêm secondary index có thể xây dựng index mới mà không copy toàn bộ bảng; thay đổi primary key có thể yêu cầu tổ chức lại clustered index và các secondary index. Hãy phân biệt thuật toán với mức độ công việc thực tế.

### 2.1. Yêu cầu thuật toán một cách tường minh

Nếu muốn thao tác chỉ chạy khi hỗ trợ instant, chỉ định:

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM=INSTANT;
```

Nếu phiên bản hoặc định nghĩa bảng không hỗ trợ thao tác đó bằng `INSTANT`, câu lệnh sẽ báo lỗi thay vì tự chuyển sang một thuật toán tốn kém hơn. Đây là cách hữu ích để tránh bất ngờ trong production.

Tương tự, có thể yêu cầu `INPLACE` hoặc mức khóa cụ thể cho thao tác đã được xác minh:

```sql
ALTER TABLE orders
  ADD INDEX idx_orders_customer_created (customer_id, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

`LOCK=NONE` yêu cầu cho phép đọc và ghi đồng thời trong phần lớn quá trình mà thuật toán hỗ trợ. Nếu thao tác không đáp ứng mức khóa này, MySQL sẽ báo lỗi thay vì âm thầm dùng mức khóa rộng hơn. Dù vậy, vẫn có thể cần metadata lock ngắn ở đầu/cuối thao tác.

### 2.2. Xem trước khả năng thực hiện

Trên MySQL 8.0.18 trở lên, có thể dùng `EXPLAIN ALTER TABLE` để xem kế hoạch thuật toán và mức khóa mà MySQL dự kiến:

```sql
EXPLAIN ALTER TABLE orders
  ADD INDEX idx_orders_customer_created (customer_id, created_at);
```

Kết quả giúp đánh giá liệu thao tác có thể dùng `INSTANT`, `INPLACE` hay cần `COPY`, cùng mức khóa tương ứng. Đây là bước khảo sát hữu ích, nhưng vẫn cần thử trên bản sao có kích thước và workload gần production vì thời gian thực tế phụ thuộc tài nguyên và tải đồng thời.

Khả năng hỗ trợ DDL thay đổi theo phiên bản MySQL, storage engine, kiểu cột, vị trí cột, index, foreign key và các đặc tính khác của bảng. Tài liệu của đúng phiên bản đang chạy là nguồn quyết định.

## 3. Mức khóa và metadata lock

Tham số `LOCK` điều khiển mức độ truy cập đồng thời trong các thuật toán DDL hỗ trợ:

| Mức khóa | Ý nghĩa khái quát |
|---|---|
| `NONE` | Cho phép đọc và ghi đồng thời trong giai đoạn chính của thao tác |
| `SHARED` | Cho phép đọc nhưng hạn chế ghi |
| `EXCLUSIVE` | Yêu cầu khóa độc quyền, chặn truy cập đồng thời tới bảng trong phạm vi khóa |

Không phải thuật toán nào cũng hỗ trợ mọi mức khóa. `LOCK=NONE` không xóa bỏ mọi khóa; MySQL vẫn phải lấy metadata lock (MDL) để bảo vệ định nghĩa bảng khi bắt đầu và hoàn tất thay đổi.

### 3.1. Metadata lock có thể chặn DDL

Một transaction dài đã truy cập bảng có thể giữ metadata lock cho đến khi transaction kết thúc. Khi DDL chờ lấy MDL, các truy vấn mới cũng có thể bị xếp hàng phía sau yêu cầu đang chờ, tạo ra hiện tượng nhiều truy vấn bị treo dù DDL chưa bắt đầu thực hiện phần rebuild.

Kiểm tra metadata lock trên bảng:

```sql
SELECT OBJECT_TYPE, OBJECT_SCHEMA, OBJECT_NAME,
       LOCK_TYPE, LOCK_DURATION, LOCK_STATUS,
       OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'shop'
  AND OBJECT_NAME = 'orders';
```

Kết hợp với:

```sql
SHOW FULL PROCESSLIST;
```

Tìm transaction hoặc session giữ lock lâu, xác định ứng dụng và chủ sở hữu trước khi xử lý. Không kill session một cách máy móc: transaction có thể đang thực hiện nghiệp vụ quan trọng và việc rollback cũng có chi phí.

### 3.2. Giới hạn thời gian chờ MDL

Có thể đặt `lock_wait_timeout` cho session chạy DDL để thao tác thoát ra nếu không lấy được metadata lock trong thời gian đã định:

```sql
SET SESSION lock_wait_timeout = 10;
```

Giá trị trên là ví dụ tính bằng giây. Đây là timeout chờ metadata lock, khác với `innodb_lock_wait_timeout` vốn điều khiển việc chờ row lock của InnoDB. Đặt timeout ngắn giúp tránh một lệnh DDL chờ lâu rồi gây hàng đợi truy vấn, nhưng cần lập lịch thử lại khi nguyên nhân giữ MDL đã được xử lý.

## 4. Thêm cột trên bảng lớn

Thêm cột là thay đổi phổ biến khi ứng dụng có thuộc tính mới. Cách làm phù hợp phụ thuộc phiên bản MySQL và đặc điểm bảng.

### 4.1. Thêm cột bằng `INSTANT`

Với nhiều trường hợp InnoDB trên MySQL 8.0.12 trở lên, thêm cột ở cuối bảng có thể dùng instant DDL:

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM=INSTANT;
```

Instant DDL cập nhật metadata và không cần ghi lại mọi hàng chỉ để thêm cột. Các hàng cũ được diễn giải theo metadata/default của phiên bản hàng tương ứng. Tuy nhiên, không phải mọi bảng hay mọi kiểu thay đổi đều hỗ trợ instant. Ví dụ, giới hạn về row format, bảng có đặc tính đặc biệt, vị trí cột và số lần instant DDL đã thực hiện có thể ảnh hưởng.

Từ MySQL 8.0.29, một số thao tác instant add/drop column có thể tạo row version trong metadata; số row version có giới hạn. Nếu vượt giới hạn hoặc bảng không đáp ứng điều kiện, thao tác có thể cần rebuild. Vì thế, không nên coi `INSTANT` là phương thức vô hạn cho mọi thay đổi cột.

### 4.2. Thêm cột có giá trị mặc định

Ví dụ:

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NOT NULL DEFAULT 'web',
  ALGORITHM=INSTANT;
```

Khả năng thực hiện instant với default phụ thuộc phiên bản và loại default. Với default biểu thức hoặc trường hợp đặc biệt, hãy kiểm tra tài liệu và dùng `EXPLAIN ALTER TABLE` khi phiên bản hỗ trợ. Không nên giả định rằng mọi giá trị mặc định đều được xử lý giống nhau.

Trong các migration cần tương thích nhiều phiên bản hoặc cần backfill có kiểm soát, có thể thêm cột nullable trước:

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM=INSTANT;
```

Sau đó ứng dụng bắt đầu ghi giá trị mới và backfill dữ liệu cũ theo từng lô. Khi đã xác minh không còn `NULL`, mới cân nhắc đổi sang `NOT NULL` trong một migration riêng. Bước đổi constraint có thể cần thuật toán khác; phải khảo sát trước.

### 4.3. Backfill theo lô

Không nên chạy một câu `UPDATE` khổng lồ trên hàng tỷ dòng nếu có thể chia nhỏ. Dùng khóa chính để xác định phạm vi từng lô:

```sql
UPDATE orders
SET source_channel = 'legacy'
WHERE order_id > 100000
  AND order_id <= 110000
  AND source_channel IS NULL;
```

Ứng dụng hoặc script điều phối tăng dần khoảng `order_id`, ghi lại checkpoint và chỉ chuyển sang lô tiếp theo khi lô hiện tại hoàn tất. Kích thước lô cần được đo và điều chỉnh theo latency, lock wait, redo, binlog, replication lag và tải ứng dụng.

Nguyên tắc backfill:

- Chọn phạm vi theo primary key hoặc index phù hợp để tránh quét toàn bảng ở mỗi lô.
- Giữ transaction mỗi lô ngắn để giảm thời gian giữ row lock và undo history.
- Có thể tạm dừng hoặc giảm tốc độ khi replication lag, I/O hoặc latency vượt ngưỡng.
- Làm cho thao tác idempotent để có thể chạy lại an toàn sau lỗi.
- Theo dõi số hàng đã cập nhật, số hàng còn thiếu và lỗi từng lô.

Kiểm tra tiến độ:

```sql
SELECT COUNT(*) AS rows_pending
FROM orders
WHERE source_channel IS NULL;
```

Trên bảng rất lớn, `COUNT(*)` với điều kiện có thể tốn tài nguyên nếu không có index phù hợp. Có thể dùng checkpoint theo khóa chính hoặc thống kê theo lô thay vì chạy phép đếm toàn bảng liên tục.

## 5. Đổi kiểu dữ liệu

Đổi kiểu cột có thể thay đổi cách lưu trữ, cách so sánh, dung lượng, giá trị hợp lệ và khả năng dùng index. Trước khi đổi, cần trả lời:

1. Dữ liệu hiện tại có chuyển đổi được không?
2. Có giá trị bị cắt, làm tròn, tràn số hoặc đổi collation không?
3. Ứng dụng, truy vấn, view, routine, trigger và index có phụ thuộc kiểu cũ không?
4. MySQL hỗ trợ `INSTANT`, `INPLACE` hay phải `COPY` cho chuyển đổi cụ thể?
5. Có thể triển khai theo kiểu thêm cột mới, backfill và chuyển ứng dụng hay không?

### 5.1. Kiểm tra dữ liệu trước khi đổi

Giả sử muốn đổi mã đơn hàng từ chuỗi sang số. Trước hết, tìm giá trị không phải chữ số:

```sql
SELECT order_code
FROM orders
WHERE order_code IS NOT NULL
  AND order_code NOT REGEXP '^[0-9]+$'
LIMIT 50;
```

Kiểm tra độ dài và phạm vi số trước khi đổi sang `INT` hoặc `BIGINT`. Với kiểu `DECIMAL`, xác định precision và scale để tránh làm tròn phần thập phân hoặc tràn số. Với `VARCHAR`, kiểm tra độ dài lớn nhất và charset/collation.

Đặc biệt chú ý các thay đổi sau:

- `BIGINT` sang `INT`: có thể tràn số nếu giá trị vượt giới hạn `INT`.
- `DECIMAL(p,s)` giảm precision hoặc scale: có thể làm tròn hoặc không lưu được giá trị.
- `VARCHAR(200)` sang `VARCHAR(50)`: chuỗi dài có thể bị cắt hoặc thao tác bị từ chối tùy SQL mode.
- Thay signed/unsigned: giá trị âm có thể không hợp lệ khi chuyển sang unsigned.
- Thay charset/collation: có thể thay đổi thứ tự sắp xếp, phép so sánh và tính duy nhất của index.
- Đổi kiểu cột được index hoặc tham gia foreign key: có thể cần thay đổi đồng bộ ở các đối tượng phụ thuộc.

### 5.2. Thử kế hoạch ALTER trước khi chạy

Ví dụ muốn mở rộng precision của cột tiền:

```sql
EXPLAIN ALTER TABLE orders
  MODIFY COLUMN total_amount DECIMAL(15,2) NOT NULL;
```

Sau khi kiểm tra dữ liệu và kế hoạch, mới chọn thuật toán phù hợp. Nếu thao tác đã được xác nhận hỗ trợ inplace và cho phép DML đồng thời, có thể yêu cầu rõ:

```sql
ALTER TABLE orders
  MODIFY COLUMN total_amount DECIMAL(15,2) NOT NULL,
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

Đây là mẫu cú pháp, không phải cam kết rằng mọi phiên bản MySQL đều hỗ trợ chuyển đổi này bằng `INPLACE`. Nếu không hỗ trợ, lệnh sẽ lỗi do thuật toán bị yêu cầu tường minh. Khi đó cần đánh giá `COPY`, một quy trình shadow table hoặc công cụ online schema change.

### 5.3. Mở rộng kiểu theo mô hình expand-contract

Với chuyển đổi rủi ro hoặc không hỗ trợ online phù hợp, có thể chia thành nhiều bản phát hành:

1. **Expand:** thêm cột mới có kiểu đích, giữ nguyên cột cũ.
2. **Dual-write:** ứng dụng ghi đồng thời vào cột cũ và cột mới, hoặc dùng một cơ chế đồng bộ có kiểm soát.
3. **Backfill:** chuyển dữ liệu cũ sang cột mới theo lô.
4. **Validate:** đối chiếu dữ liệu hai cột, kiểm tra giá trị biên và các nghiệp vụ quan trọng.
5. **Switch reads:** ứng dụng chuyển sang đọc cột mới.
6. **Stop old writes:** sau khi xác nhận, ngừng ghi cột cũ.
7. **Contract:** ở một lần phát hành sau, xóa cột cũ và các phụ thuộc không còn dùng.

Mẫu này cho phép triển khai ứng dụng theo từng bước và giữ thời gian quay lui. Tuy nhiên, dual-write có thể thất bại một phần; cần transaction phù hợp hoặc cơ chế retry/đối soát để hai cột không lệch nhau. Tránh duy trì hai nguồn dữ liệu authoritative quá lâu.

## 6. Tạo chỉ mục trên bảng lớn

Index giúp giảm số hàng cần đọc cho một truy vấn, nhưng tạo index trên bảng lớn là một tác vụ tiêu thụ tài nguyên. InnoDB phải quét dữ liệu để xây dựng cấu trúc index, sắp xếp khóa và ghi các trang index mới.

### 6.1. Xác định index cần thiết

Trước khi tạo index, xem truy vấn thực tế và kế hoạch thực thi:

```sql
EXPLAIN
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 501
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC;
```

Nếu truy vấn thường lọc theo `customer_id`, sau đó theo khoảng `created_at`, có thể cân nhắc composite index:

```sql
ALTER TABLE orders
  ADD INDEX idx_orders_customer_created (customer_id, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

Thứ tự cột trong composite index quan trọng. Index `(customer_id, created_at)` hỗ trợ truy vấn lọc theo `customer_id` và có thể tiếp tục dùng phần `created_at`; nó không tương đương với index chỉ có `(created_at, customer_id)`. Hãy chọn thứ tự theo điều kiện lọc, join và sort thực tế.

Không tạo index chỉ vì một cột xuất hiện trong `WHERE`. Cần xem độ chọn lọc, tần suất truy vấn, kích thước index và chi phí ghi. Mỗi index bổ sung làm tăng dung lượng và khiến `INSERT`, `UPDATE`, `DELETE` phải duy trì thêm cấu trúc.

### 6.2. Online index creation

Với nhiều loại secondary index InnoDB, MySQL hỗ trợ tạo index bằng `ALGORITHM=INPLACE, LOCK=NONE`, cho phép DML đồng thời trong phần lớn quá trình. Tuy vậy:

- MySQL vẫn phải đọc bảng và xây dựng index; CPU và I/O có thể tăng đáng kể.
- Thay đổi phát sinh từ DML đồng thời được ghi nhận và hợp nhất vào index mới.
- Có thể cần metadata lock ngắn ở đầu/cuối.
- Online DDL có thể thất bại nếu lượng thay đổi đồng thời vượt giới hạn log cho phép, chẳng hạn `innodb_online_alter_log_max_size`.
- Tạo index unique có thể thất bại nếu dữ liệu hiện tại có giá trị trùng.

Kiểm tra giới hạn online alter log:

```sql
SHOW VARIABLES LIKE 'innodb_online_alter_log_max_size';
```

Không tăng biến này tùy tiện để xử lý một lần build index thất bại. Cần tìm hiểu lượng ghi đồng thời, dung lượng storage và khả năng bắt kịp của replica trước khi điều chỉnh.

### 6.3. Kiểm tra index sau khi tạo

```sql
SHOW INDEX FROM orders;

EXPLAIN
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 501
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC;
```

So sánh kế hoạch trước và sau, số hàng ước lượng, key được chọn và thời gian thực thi trên workload đại diện. Có thể dùng `EXPLAIN ANALYZE` trên phiên bản hỗ trợ để quan sát thời gian và số hàng thực tế, nhưng lệnh này thực thi truy vấn; không chạy một truy vấn nặng tùy tiện trên production.

Nếu cần đánh giá tác động trước khi optimizer sử dụng index, MySQL 8.0 hỗ trợ invisible index cho các loại index phù hợp. Index invisible vẫn được duy trì khi dữ liệu thay đổi và vẫn tiêu thụ dung lượng; nó chỉ bị bỏ qua trong lựa chọn kế hoạch thông thường. Việc chuyển visible/invisible không loại bỏ chi phí xây dựng ban đầu.

## 7. Thay đổi khóa chính trên bảng lớn

Khóa chính (primary key) có vai trò đặc biệt trong InnoDB. InnoDB tổ chức dữ liệu hàng theo clustered index, thường chính là primary key. Các secondary index lưu giá trị khóa chính để tham chiếu tới hàng tương ứng.

Hệ quả:

- Thay đổi primary key thường yêu cầu tổ chức lại clustered index.
- Các secondary index có thể phải xây dựng lại vì giá trị primary key được lưu trong leaf entry của chúng.
- Primary key rộng làm các secondary index lớn hơn và tốn thêm bộ nhớ/storage.
- Khóa chính được foreign key tham chiếu sẽ có phụ thuộc cần xử lý trước khi thay đổi.
- Thứ tự clustered index ảnh hưởng locality của dữ liệu và một số truy vấn range.

Vì vậy, thay đổi primary key thường là một trong những thao tác schema tốn kém nhất trên bảng lớn.

### 7.1. Kiểm tra thiết kế khóa mới

Trước khi thay khóa chính, xác định:

1. Khóa mới có duy nhất, ổn định và `NOT NULL` không?
2. Các bảng con đang tham chiếu khóa cũ ở đâu?
3. Ứng dụng, API, cache, message queue và job nền có dùng khóa cũ không?
4. Có cần giữ unique constraint trên khóa nghiệp vụ cũ không?
5. Các secondary index sẽ tăng dung lượng bao nhiêu khi lưu khóa mới?
6. Có thể thay đổi bằng một DDL native hay cần shadow table?

Ví dụ minh họa chuyển từ khóa nghiệp vụ sang surrogate key:

```sql
ALTER TABLE orders
  DROP PRIMARY KEY,
  ADD COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ADD PRIMARY KEY (id);
```

Lệnh trên chỉ minh họa cấu trúc thay đổi. Trên bảng đã có dữ liệu, thao tác này có thể rebuild bảng và index, tốn nhiều thời gian/dung lượng. Nếu khóa cũ đang được foreign key tham chiếu, cần lập kế hoạch chuyển các bảng con và constraint; không chạy nguyên lệnh ví dụ mà chưa kiểm kê phụ thuộc.

### 7.2. Giữ tính duy nhất của khóa cũ

Nếu khóa nghiệp vụ cũ vẫn phải duy nhất, hãy tạo unique index tương ứng sau khi xác minh dữ liệu:

```sql
ALTER TABLE orders
  ADD UNIQUE KEY uq_orders_external_ref (external_ref),
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

Trước đó, kiểm tra duplicate và `NULL` theo quy tắc nghiệp vụ. Unique index cho phép nhiều `NULL` trong một số trường hợp tùy định nghĩa cột; nếu yêu cầu mỗi hàng phải có giá trị, cần constraint `NOT NULL` phù hợp.

### 7.3. Shadow table cho thay đổi khóa lớn

Với bảng rất lớn hoặc thay đổi khóa phức tạp, có thể cân nhắc dựng bảng mới có cấu trúc đích:

1. Tạo `orders_new` với primary key mới và đầy đủ index/constraint cần thiết.
2. Bắt đầu đồng bộ thay đổi mới từ bảng cũ sang bảng mới bằng công cụ CDC/online schema change hoặc cơ chế ứng dụng được thiết kế rõ.
3. Copy dữ liệu cũ theo lô, theo thứ tự khóa phù hợp.
4. Đối chiếu số hàng, unique key, quan hệ và các tổng hợp nghiệp vụ.
5. Khi đã bắt kịp thay đổi, dừng ghi trong khoảng cutover ngắn.
6. Đổi tên hoặc chuyển endpoint theo quy trình đã thử, sau đó chạy smoke test.
7. Giữ bảng cũ trong thời gian rollback đã định, rồi mới dọn dẹp.

Đây là mẫu kiến trúc, không phải một script SQL hoàn chỉnh. Việc đồng bộ DML, trigger, foreign key, auto_increment, view và các đối tượng phụ thuộc cần được giải quyết cụ thể. `RENAME TABLE` có thể cần metadata lock; việc đổi tên không đảm bảo cutover luôn không chặn truy vấn.

## 8. Công cụ online schema change

Khi native online DDL không đáp ứng yêu cầu, có thể cân nhắc công cụ tạo shadow table và đồng bộ thay đổi trong lúc copy dữ liệu.

| Công cụ | Cách tiếp cận khái quát | Điểm cần kiểm tra |
|---|---|---|
| `pt-online-schema-change` | Tạo bảng mới, copy theo chunk và dùng trigger để đồng bộ thay đổi | Trigger hiện có, foreign key, tải ghi, quyền và điều kiện cutover |
| `gh-ost` | Tạo bảng ghost, copy theo lô và đọc binlog để đồng bộ thay đổi | Cấu hình binlog/replication, topology, quyền, loại bảng và điều kiện cutover |
| Native online DDL | Dùng thuật toán DDL do MySQL/InnoDB hỗ trợ | `ALGORITHM`, `LOCK`, MDL, thời gian rebuild và khả năng hỗ trợ của phiên bản |

Các công cụ trên không phải tính năng tự động an toàn trong mọi trường hợp. Cần kiểm tra phiên bản công cụ, phiên bản MySQL, topology, loại bảng, trigger, foreign key, replication filter và chính sách vận hành. Shadow table cần thêm dung lượng gần với kích thước bảng/index hiện tại; quá trình copy cũng tạo tải và có thể làm replica lag.

Chạy thử trên bản sao production, đo tốc độ copy, đặt giới hạn tải và chuẩn bị cách dừng/tiếp tục. Đặc biệt, thao tác cutover cuối cùng vẫn cần metadata lock và có thể bị chặn bởi transaction dài.

## 9. Quy trình triển khai schema change an toàn

### 9.1. Khảo sát trước thay đổi

1. Xác định mục tiêu thay đổi và truy vấn/ứng dụng phụ thuộc.
2. Ghi lại phiên bản MySQL, engine, kích thước bảng, index, khóa ngoại và workload.
3. Kiểm tra dữ liệu biên, giá trị trùng, `NULL`, overflow và khả năng chuyển kiểu.
4. Dùng `EXPLAIN ALTER TABLE` nếu phiên bản hỗ trợ; xác định thuật toán và mức khóa.
5. Kiểm tra metadata lock, transaction dài, replica lag và dung lượng còn trống.
6. Thử trên bản sao có kích thước gần production; đo thời gian và mức tải.
7. Xác định ngưỡng dừng, người trực, kế hoạch rollback và tiêu chí thành công.

### 9.2. Trong khi thực hiện

- Chạy một thay đổi nặng tại một thời điểm, tránh ghép nhiều thao tác không cần thiết vào một DDL khó kiểm soát.
- Dùng `ALGORITHM` và `LOCK` tường minh khi đã xác nhận hỗ trợ, để MySQL báo lỗi nếu không đáp ứng điều kiện mong muốn.
- Chạy ngoài giờ cao điểm nếu thao tác tiêu tốn tài nguyên hoặc có bước khóa.
- Theo dõi processlist, metadata lock, CPU, I/O, disk space, redo/binlog, replication lag và latency ứng dụng.
- Nếu backfill, dùng chunk nhỏ, checkpoint, retry và điều tiết tốc độ.
- Không kill DDL hoặc session giữ lock nếu chưa đánh giá tác động và trạng thái transaction.

### 9.3. Sau thay đổi

1. Kiểm tra định nghĩa bảng bằng `SHOW CREATE TABLE`.
2. Kiểm tra index bằng `SHOW INDEX`.
3. Đối chiếu dữ liệu, giá trị biên, `NULL`, duplicate và quan hệ giữa bảng.
4. Chạy `EXPLAIN` cho các truy vấn quan trọng; đo query latency thực tế.
5. Kiểm tra replica đã áp dụng thay đổi và lag trở lại mức bình thường.
6. Theo dõi error log, slow query log, deadlock và lỗi ứng dụng.
7. Cập nhật migration version, tài liệu vận hành và kế hoạch dọn dẹp đối tượng cũ.

## 10. Rollback và khả năng phục hồi

DDL thường có implicit commit. Ngay cả khi một số DDL có atomic DDL trong MySQL 8.0, điều đó không có nghĩa người vận hành có thể `ROLLBACK` một thay đổi đã hoàn tất. Atomic DDL bảo đảm tính nguyên tử của thao tác trong các tình huống lỗi được hỗ trợ, không phải cơ chế rollback nghiệp vụ tùy ý.

Các phương án quay lui:

- Nếu thêm cột hoặc index mới và ứng dụng chưa dùng, có thể giữ nguyên rồi đánh giá cách xóa trong migration sau.
- Nếu đổi kiểu gây lỗi, cần có backup hoặc cột shadow để phục hồi dữ liệu gốc; đổi ngược kiểu không nhất thiết khôi phục được giá trị đã bị cắt/làm tròn.
- Nếu chuyển primary key, giữ khóa cũ dưới dạng unique index và giữ mapping trong thời gian chuyển đổi nếu ứng dụng cần quay lại.
- Nếu dùng shadow table, giữ bảng cũ và cơ chế đồng bộ trong cửa sổ rollback, nhưng phải xác định rõ bảng nào là nguồn ghi authoritative.
- Nếu dữ liệu đã bị thay đổi không thể đảo ngược, dùng backup/PITR hoặc quy trình phục hồi dữ liệu đã thử.

Trước thay đổi lớn, xác minh backup có thể restore và lưu binary log/GTID cần thiết. Không coi việc tạo một backup là đủ; cần biết thời gian phục hồi và khả năng đưa dữ liệu về đúng điểm.

## 11. Ví dụ chiến lược expand-contract cho bảng orders

Giả sử bảng `orders` cần thêm `source_channel`, sau đó đổi cột tiền sang precision lớn hơn và bổ sung index phục vụ báo cáo.

**Giai đoạn A — mở rộng schema**

```sql
ALTER TABLE orders
  ADD COLUMN source_channel VARCHAR(30) NULL,
  ALGORITHM=INSTANT;
```

Triển khai ứng dụng có khả năng đọc schema mới nhưng vẫn tương thích với dữ liệu cũ. Bắt đầu ghi `source_channel` cho đơn hàng mới.

**Giai đoạn B — backfill**

```sql
UPDATE orders
SET source_channel = 'legacy'
WHERE order_id > 0
  AND order_id <= 10000
  AND source_channel IS NULL;
```

Lặp theo các khoảng `order_id`, điều tiết tốc độ và lưu checkpoint. Không chạy một lần cho toàn bảng nếu gây tải vượt ngưỡng.

**Giai đoạn C — index**

```sql
ALTER TABLE orders
  ADD INDEX idx_orders_channel_created (source_channel, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
```

Trước khi chạy, dùng `EXPLAIN ALTER TABLE` và xác nhận phiên bản hỗ trợ. Sau khi tạo, so sánh kế hoạch và latency truy vấn báo cáo.

**Giai đoạn D — xác minh và siết constraint**

```sql
SELECT COUNT(*) AS rows_missing_channel
FROM orders
WHERE source_channel IS NULL;
```

Khi không còn hàng thiếu, ứng dụng đã ghi đầy đủ và thao tác chuyển constraint được đánh giá phù hợp, mới thực hiện migration riêng để đổi sang `NOT NULL`. Sau đó tiếp tục theo dõi trước khi dọn logic tương thích cũ.

Đối với cột tiền, kiểm tra giá trị lớn nhất/nhỏ nhất, scale và dữ liệu ngoài phạm vi kiểu đích trước khi sửa kiểu. Chỉ thực hiện native `ALTER` khi thuật toán, mức khóa và thời gian đã được xác minh; nếu không, dùng cột shadow và quy trình backfill tương ứng.

## 12. Checklist trước khi thay đổi bảng lớn

- [ ] Đã xác định mục tiêu và đối tượng ứng dụng phụ thuộc.
- [ ] Đã ghi nhận phiên bản MySQL, storage engine và định nghĩa bảng.
- [ ] Đã khảo sát số hàng, dung lượng data/index, khóa chính, secondary index và foreign key.
- [ ] Đã kiểm tra dữ liệu biên, duplicate, `NULL`, overflow và nguy cơ mất dữ liệu khi đổi kiểu.
- [ ] Đã xác định `ALGORITHM` và `LOCK` được hỗ trợ; đã dùng `EXPLAIN ALTER TABLE` nếu có.
- [ ] Đã kiểm tra metadata lock, transaction dài và `lock_wait_timeout`.
- [ ] Đã đánh giá CPU, I/O, dung lượng tạm, redo/binlog và replication lag.
- [ ] Đã thử trên bản sao production và đo thời gian thực tế.
- [ ] Đã có backup/PITR hoặc shadow table phù hợp với mức rủi ro.
- [ ] Đã xác định batch size, checkpoint và cách điều tiết backfill.
- [ ] Đã chuẩn bị giám sát, ngưỡng dừng, người trực và runbook.
- [ ] Đã có tiêu chí xác minh schema, dữ liệu, index, ứng dụng và replica.
- [ ] Đã xác định cách rollback và thời gian giữ cấu trúc cũ.

## 13. Tự kiểm tra

1. `ALGORITHM=INPLACE` có đồng nghĩa với việc MySQL không rebuild bảng không? Giải thích.
2. `LOCK=NONE` có loại bỏ hoàn toàn metadata lock không? Vì sao?
3. Tại sao `ALGORITHM=INSTANT` tường minh có thể giúp tránh một lần ALTER bất ngờ chuyển sang COPY?
4. Vì sao thêm cột nullable rồi backfill theo lô thường dễ kiểm soát hơn một lần thay đổi lớn?
5. Những rủi ro nào cần kiểm tra trước khi đổi `BIGINT` sang `INT` hoặc giảm precision của `DECIMAL`?
6. Vì sao tạo secondary index bằng online DDL vẫn có thể làm tăng latency và replication lag?
7. Vì sao thay primary key có thể phải xây dựng lại secondary index trong InnoDB?
8. Metadata lock từ transaction dài có thể gây hàng đợi truy vấn như thế nào?
9. Khác biệt giữa `lock_wait_timeout` và `innodb_lock_wait_timeout` là gì?
10. Hãy lập kế hoạch expand-contract để thêm một cột bắt buộc vào bảng có hàng trăm triệu bản ghi, bao gồm backfill, xác minh và rollback.

Thay đổi schema trên bảng lớn cần được xem như một hoạt động vận hành có tải, có khóa và có rủi ro dữ liệu. Hãy xác minh thuật toán, mức khóa và phụ thuộc trước khi thực hiện; triển khai theo từng bước có thể đo lường; sau cùng kiểm tra dữ liệu, truy vấn, replica và ứng dụng trước khi loại bỏ cấu trúc cũ.
