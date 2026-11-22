# Chỉ mục

## Chi phí bảo trì khi INSERT/UPDATE/DELETE và tránh tạo dư thừa

Index giúp MySQL tìm hàng, nối bảng và sắp xếp dữ liệu nhanh hơn, nhưng mỗi index cũng là một cấu trúc B-tree phải được duy trì khi dữ liệu thay đổi. Một lệnh `INSERT` có thể phải thêm entry vào clustered index và tất cả secondary index; `UPDATE` có thể phải thay đổi entry nếu cột khóa bị sửa; `DELETE` phải đánh dấu/xóa entry tương ứng và để InnoDB purge phiên bản cũ khi an toàn. Vì vậy, index không miễn phí: càng nhiều index, chi phí ghi, dung lượng lưu trữ, buffer pool và công việc bảo trì càng lớn.

Mục tiêu thiết kế là giữ các index có lợi ích đo được cho truy vấn, đồng thời loại bỏ index trùng lặp hoặc ít giá trị. Điều này cần dựa trên workload thực tế, ràng buộc khóa ngoại, kế hoạch thực thi và số liệu sử dụng index; không nên xóa một index chỉ vì tên hoặc định nghĩa của nó trông giống index khác.

### 1. Mỗi index là một B-tree cần được duy trì

InnoDB lưu dữ liệu bảng trong clustered index. Mỗi secondary index có B-tree riêng, với leaf entry chứa các cột index và khóa chính để định vị hàng trong clustered index. Khi dữ liệu thay đổi, InnoDB phải giữ tất cả cấu trúc liên quan nhất quán.

Ví dụ:

```sql
CREATE TABLE orders (
    id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_customer (customer_id),
    KEY idx_status (status),
    KEY idx_created (created_at)
) ENGINE = InnoDB;
```

Một hàng mới không chỉ được ghi vào clustered index theo `id`. InnoDB còn phải tạo entry trong `idx_customer`, `idx_status` và `idx_created`. Khi số index tăng, mỗi lần insert có thể gây thêm tìm kiếm vị trí, sửa page, ghi redo/undo và có thể phát sinh page split.

Các index cũng tiêu thụ page trong buffer pool và dung lượng tablespace. Index càng lớn thì working set càng lớn; một workload ghi có thể đẩy page hữu ích khác khỏi buffer pool và làm tăng I/O. Chi phí không chỉ nằm ở thời gian thực hiện câu lệnh ghi.

### 2. Chi phí của INSERT

Với mỗi hàng được chèn vào InnoDB:

1. InnoDB chèn record vào leaf page của clustered index theo thứ tự khóa chính.
2. Với mỗi secondary index, InnoDB tạo entry gồm giá trị key part và khóa chính.
3. Các page liên quan được sửa trong buffer pool và sinh redo/undo cần thiết.
4. Nếu page không đủ chỗ, B-tree có thể phải tổ chức lại page hoặc split page.
5. Khi commit, các log cần thiết được xử lý theo chính sách durability; dirty data page có thể được flush sau.

Nếu một bảng có 1 clustered index và 8 secondary index, một insert có thể tác động đến tối đa 9 cấu trúc index. Đây không có nghĩa luôn có đúng 9 lần ghi đĩa: nhiều thay đổi có thể nằm trong buffer pool, group commit và cơ chế ghi nền gom I/O. Nhưng mọi index liên quan vẫn cần được cập nhật logic.

Insert theo thứ tự tăng của khóa clustered thường có locality tốt hơn so với khóa ngẫu nhiên, vì các hàng mới thường đi vào vùng cuối B-tree. Khóa ngẫu nhiên có thể làm insert phân tán trên nhiều page, tăng page split và page read. Secondary index cũng có phân bố ghi riêng theo giá trị của nó.

### 3. Chi phí của UPDATE

Không phải mọi `UPDATE` đều làm thay đổi tất cả secondary index. InnoDB chỉ cần cập nhật các index bị ảnh hưởng bởi giá trị khóa thay đổi, cùng clustered record và các cấu trúc liên quan.

| Loại UPDATE | Công việc index thường cần thiết |
| --- | --- |
| Sửa cột không thuộc bất kỳ index nào, không đổi primary key | Sửa clustered record; secondary index không chứa cột đó thường không cần thay entry |
| Sửa cột thuộc secondary index | Thay entry cũ bằng entry mới trong index đó; clustered record cũng thay đổi |
| Sửa primary key | Thay vị trí clustered record và cập nhật khóa định vị trong các secondary index |
| Sửa nhiều cột thuộc nhiều index | Cập nhật tất cả index có key part bị ảnh hưởng |

Ví dụ:

```sql
-- total không thuộc index nào trong ví dụ đầu.
UPDATE orders
SET total = total + 10
WHERE id = 1001;

-- status thuộc idx_status nên entry secondary index cần thay đổi.
UPDATE orders
SET status = 'shipped'
WHERE id = 1001;
```

Một cập nhật cột không được index hóa vẫn phải sửa clustered record và tạo log; nó không miễn phí. Nhưng thường không phải sửa từng secondary index. Ngược lại, nếu cột được index hóa thay đổi, InnoDB phải bảo đảm thứ tự B-tree và vị trí entry đúng với giá trị mới.

Primary key đặc biệt quan trọng vì giá trị khóa chính được lưu trong các secondary index để định vị clustered record. Thay đổi primary key có thể kéo theo việc thay đổi entry ở mọi secondary index. Đây là một lý do nên chọn primary key ổn định, không thường xuyên thay đổi.

### 4. Chi phí của DELETE và purge

Khi xóa một hàng, InnoDB đánh dấu record trong clustered index và các secondary index tương ứng là đã xóa. Undo log giữ thông tin cần thiết cho rollback và consistent read. Sau khi không còn transaction/read view nào cần phiên bản cũ, purge thread có thể loại bỏ các entry đã xóa và tái sử dụng không gian.

Do đó, `DELETE` không đồng nghĩa với việc tất cả byte của hàng và index lập tức biến mất khỏi file. Một transaction dài có thể giữ read view cũ, làm purge không thể dọn một số phiên bản. Khi xóa hàng loạt, cần theo dõi history list length, undo tablespace, thời gian transaction và I/O của purge.

Mỗi secondary index bổ sung cũng có entry cần được xử lý khi delete. Nếu bảng có nhiều index rộng, thao tác xóa có thể tạo thêm công việc undo/redo, page modification và purge.

### 5. Index rộng làm tăng chi phí ở nhiều nơi

Kích thước index phụ thuộc số hàng, kiểu dữ liệu, độ rộng key part, khóa chính được đính kèm, cấu trúc page và mức lấp đầy. Một index rộng làm tăng:

- Dung lượng tablespace và chi phí backup/restore.
- Số page cần giữ trong buffer pool để workload có cache hit tốt.
- Số byte phải ghi và đọc khi insert/update/delete.
- Chi phí rebuild index và thời gian DDL.
- Khả năng page split, page read và I/O ngẫu nhiên khi workload phân tán.

Ví dụ, một secondary index trên `VARCHAR(200)` có thể lớn hơn đáng kể so với index trên một `INT`, nhất là khi có nhiều hàng và charset dùng nhiều byte cho mỗi ký tự. Nếu primary key là chuỗi dài, giá trị khóa chính được lưu kèm trong secondary index cũng làm mỗi entry rộng hơn.

Không nên thêm tất cả cột truy vấn vào một covering index một cách máy móc. Covering index có thể giảm lookup clustered record cho một truy vấn đọc, nhưng index rộng làm tăng chi phí ghi cho mọi hàng và có thể chiếm nhiều buffer pool. Hãy so sánh lợi ích đọc với số lần ghi và số hàng thực tế.

### 6. Index trùng lặp và index dư thừa

Hai khái niệm thường gặp:

- **Index trùng lặp (duplicate):** hai index có cùng tập key part, cùng thứ tự và cùng hướng, khác tên hoặc khác một số thuộc tính không làm thay đổi mục đích truy cập.
- **Index dư thừa (redundant):** một index có thể được thay thế cho phần lớn nhu cầu truy cập của index khác vì nó là leftmost prefix tương thích. Ví dụ index `(customer_id, created_at)` có thể phục vụ lookup theo `customer_id`, nên index riêng `(customer_id)` có thể dư thừa.

Ví dụ:

```sql
CREATE TABLE customer_order (
    id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    KEY idx_customer (customer_id),
    KEY idx_customer_created (customer_id, created_at),
    KEY idx_status (status)
) ENGINE = InnoDB;
```

`idx_customer_created` có thể được dùng cho truy vấn chỉ lọc `customer_id` nhờ leftmost prefix. Vì vậy `idx_customer` là ứng viên cần xem xét để loại bỏ. Tuy nhiên, index ngắn hơn có thể nhỏ hơn, cache tốt hơn hoặc được dùng hiệu quả hơn cho workload cụ thể; cần so sánh kế hoạch và số liệu trước khi xóa.

Một index không nhất thiết dư thừa chỉ vì các cột của nó xuất hiện trong index khác. Thứ tự key part, hướng ASC/DESC, prefix length, collation, kiểu index và điều kiện truy vấn đều ảnh hưởng khả năng thay thế.

### 7. Vì sao leftmost prefix không phải quy tắc xóa index tự động?

Với index `(a, b)`, MySQL thường có thể dùng phần đầu `(a)` để tìm kiếm. Nhưng index `(a, b)` không tương đương index `(b)` vì không sắp xếp toàn cục theo `b`. Tương tự, index `(a, b, c)` có thể phục vụ truy vấn theo `(a)` hoặc `(a, b)`, nhưng không tự động thay thế index `(a, c)` cho mọi truy vấn.

Ví dụ:

```sql
-- Có thể dùng leftmost prefix của (customer_id, created_at).
SELECT *
FROM customer_order
WHERE customer_id = 42;

-- Không thể dùng thứ tự toàn cục theo created_at từ index (customer_id, created_at)
-- nếu customer_id không được cố định.
SELECT *
FROM customer_order
ORDER BY created_at DESC;
```

Index `(customer_id, created_at)` có thứ tự theo `customer_id` trước. Các hàng thuộc nhiều khách hàng không được xếp toàn cục theo `created_at` chỉ bằng cách quét index đó.

Ngoài ra, index có prefix length, ví dụ `name(20)`, chỉ lưu một phần giá trị chuỗi; nó không nhất thiết thay thế index đầy đủ cho mọi phép so sánh hoặc sắp xếp. Index unique, index có hướng giảm dần, functional index và index phục vụ foreign key cũng cần đánh giá riêng.

### 8. Foreign key và index hỗ trợ

InnoDB yêu cầu cột được tham chiếu trong foreign key có index phù hợp; với bảng con, MySQL có thể tự tạo index trên các cột foreign key nếu chưa có index phù hợp. Nếu sau đó tạo index khác có cùng cột dẫn đầu và đáp ứng ràng buộc, cần kiểm tra index do MySQL tạo còn cần thiết hay không trước khi loại bỏ.

Ví dụ:

```sql
CREATE TABLE customers (
    id BIGINT NOT NULL PRIMARY KEY,
    name VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE orders (
    id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE = InnoDB;
```

Index trên `orders.customer_id` hỗ trợ kiểm tra và tìm các hàng con khi thao tác trên hàng cha, đồng thời hỗ trợ join từ orders sang customers. Không được xóa index duy nhất đang đáp ứng yêu cầu foreign key nếu chưa có index thay thế tương thích; MySQL có thể từ chối thao tác hoặc tự tạo lại index cần thiết tùy trường hợp.

### 9. Tìm index dư thừa bằng metadata

Bắt đầu bằng cách liệt kê index và key part:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    COLLATION,
    INDEX_TYPE
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

Kiểm tra các index cùng bảng có cùng chuỗi key part hay index ngắn là prefix của index dài. Xem thêm `SHOW CREATE TABLE` để xác nhận unique constraint, foreign key và thuộc tính khác:

```sql
SHOW CREATE TABLE orders;
SHOW INDEX FROM orders;
```

MySQL Shell và sys schema có các công cụ/view hỗ trợ phân tích index. Nếu hệ thống có `sys.schema_redundant_indexes`, có thể xem danh sách ứng viên:

```sql
SELECT *
FROM sys.schema_redundant_indexes
WHERE table_schema = DATABASE();
```

View này đưa ra gợi ý dựa trên cấu trúc index, không phải lệnh tự động xóa. Phải xác nhận các khác biệt về unique, foreign key, prefix, collation, direction, workload và khả năng tương thích phiên bản.

### 10. Kiểm tra index có thực sự được sử dụng không

`sys.schema_index_statistics` tổng hợp số lần truy cập index theo Performance Schema khi instrumentation và dữ liệu thống kê sẵn có:

```sql
SELECT
    table_schema,
    table_name,
    index_name,
    rows_selected,
    rows_inserted,
    rows_updated,
    rows_deleted
FROM sys.schema_index_statistics
WHERE table_schema = DATABASE()
ORDER BY table_name, index_name;
```

Tên view/cột và dữ liệu có thể khác theo phiên bản. Các bộ đếm thường tính từ lúc server khởi động hoặc từ khi thống kê được reset; restart, reset hoặc thay đổi instrumentation có thể làm mất lịch sử. Một index có số lần đọc thấp trong cửa sổ quan sát ngắn chưa chắc vô dụng: nó có thể phục vụ truy vấn cuối tháng, báo cáo hiếm, migration, constraint hoặc tác vụ khẩn cấp.

Kết hợp nhiều nguồn:

- `performance_schema` và `sys` để xem hoạt động truy cập trong khoảng thời gian đã quan sát.
- Slow query log và digest để biết truy vấn tốn thời gian hoặc chạy thường xuyên.
- `EXPLAIN` để xem optimizer chọn index nào cho truy vấn cụ thể.
- Thống kê nghiệp vụ để xác định truy vấn theo mùa, cuối kỳ, backup, audit hoặc xử lý batch.
- Metadata foreign key/unique để bảo đảm index không đang thực hiện vai trò ràng buộc.

### 11. Invisible index để thử nghiệm trước khi xóa

MySQL 8.0 hỗ trợ invisible index. Index vẫn được duy trì khi dữ liệu thay đổi, nhưng optimizer mặc định không chọn nó cho kế hoạch truy vấn. Vì vậy, có thể dùng invisible index để kiểm tra ảnh hưởng của việc loại index khỏi lựa chọn của optimizer trước khi xóa vật lý.

Ví dụ:

```sql
ALTER TABLE customer_order
ALTER INDEX idx_customer INVISIBLE;
```

Sau đó chạy workload kiểm thử, theo dõi slow query, latency và kế hoạch thực thi. Có thể buộc session thử nghiệm xem xét invisible index bằng cách bật:

```sql
SET SESSION optimizer_switch = 'use_invisible_indexes=on';
```

Nếu phát hiện truy vấn quan trọng bị chậm, khôi phục khả năng sử dụng index:

```sql
ALTER TABLE customer_order
ALTER INDEX idx_customer VISIBLE;
```

Nếu đã xác nhận index không còn cần thiết và đáp ứng mọi ràng buộc, mới cân nhắc xóa:

```sql
ALTER TABLE customer_order
DROP INDEX idx_customer;
```

Invisible index **không loại bỏ chi phí ghi hoặc dung lượng**: InnoDB vẫn cập nhật và lưu index đó. Nó chỉ giúp thử tác động tới optimizer. Sau khi drop mới loại bỏ chi phí duy trì index. Thay đổi visibility là DDL, cần xem xét metadata lock và hành vi trên phiên bản đang chạy.

### 12. Quy trình loại bỏ index an toàn

1. **Chụp trạng thái hiện tại:** lưu `SHOW CREATE TABLE`, danh sách index, foreign key và các truy vấn quan trọng.
2. **Quan sát đủ chu kỳ workload:** bao gồm giờ cao điểm, batch, báo cáo cuối kỳ và tác vụ định kỳ.
3. **Xác định ứng viên:** index duplicate hoặc redundant theo key part, nhưng đánh dấu mọi khác biệt về unique, prefix, hướng và collation.
4. **Kiểm tra phụ thuộc:** xác nhận foreign key, unique constraint, truy vấn `ORDER BY`, `GROUP BY`, join và các câu DML có dùng index.
5. **Thử invisible:** chuyển index thành invisible trong môi trường phù hợp, đo latency và theo dõi lỗi/kế hoạch xấu.
6. **Khôi phục nếu cần:** đặt lại visible ngay nếu có truy vấn quan trọng bị ảnh hưởng.
7. **Drop có kế hoạch:** sau khi xác nhận, xóa index trong cửa sổ phù hợp; đánh giá metadata lock, I/O và replication.
8. **Đo lại:** so sánh tốc độ ghi, dung lượng index, buffer pool, query latency và kế hoạch thực thi sau thay đổi.

Không xóa nhiều index cùng lúc nếu chưa có khả năng xác định index nào gây ra hồi quy. Thay đổi từng ứng viên giúp dễ quy nguyên nhân và rollback.

### 13. Ví dụ đánh giá bộ index cho một workload

Giả sử hệ thống có các truy vấn chính:

```sql
-- Q1: tìm đơn hàng của khách hàng theo thời gian mới nhất.
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;

-- Q2: lọc đơn hàng theo trạng thái.
SELECT id, created_at
FROM orders
WHERE status = 'pending';

-- Q3: tra cứu đơn hàng bằng primary key.
SELECT *
FROM orders
WHERE id = 1001;
```

Một bộ index ban đầu có thể là:

```sql
PRIMARY KEY (id)
KEY idx_customer (customer_id)
KEY idx_customer_created (customer_id, created_at)
KEY idx_status (status)
```

`idx_customer` là ứng viên redundant vì `idx_customer_created` có leftmost prefix `customer_id`. Q1 có thể dùng index dài và Q2 dùng `idx_status`; Q3 dùng clustered primary key. Trước khi drop `idx_customer`, kiểm tra xem index ngắn có được dùng vì kích thước nhỏ hơn, có ràng buộc hoặc workload khác hay không. Sau đó thử invisible, so sánh `EXPLAIN` và latency rồi mới quyết định.

Nếu Q1 cần sắp xếp mới nhất trước, có thể xem xét hướng index:

```sql
CREATE INDEX idx_customer_created_desc
ON orders (customer_id ASC, created_at DESC);
```

Nhưng không nên tạo cả `(customer_id)` và `(customer_id, created_at)` và `(customer_id, created_at DESC)` nếu chưa xác định index nào cần thiết. Mỗi index bổ sung sẽ được duy trì cho mọi thay đổi liên quan.

### 14. Khi nào nên giữ index tưởng như ít dùng?

Một index có số lần đọc thấp vẫn có thể cần thiết:

- Là index unique bảo vệ tính duy nhất của dữ liệu.
- Hỗ trợ foreign key hoặc kiểm tra referential integrity.
- Phục vụ truy vấn hiếm nhưng có yêu cầu thời gian phản hồi nghiêm ngặt.
- Được dùng trong batch, báo cáo, migration, đối soát hoặc sự cố vận hành.
- Chỉ được sử dụng khi dữ liệu có phân bố đặc biệt hoặc khi một điều kiện filter xuất hiện.

Không dùng số lần `rows_selected` bằng 0 trong một khoảng ngắn làm bằng chứng đủ để xóa. Thống kê sử dụng index phải được thu thập trong một chu kỳ đại diện và đối chiếu với yêu cầu nghiệp vụ.

### 15. Checklist thiết kế index có trách nhiệm

1. Mỗi index phải gắn với một truy vấn, một constraint hoặc một yêu cầu vận hành cụ thể.
2. Đánh giá chi phí INSERT/UPDATE/DELETE trước khi thêm index.
3. Ưu tiên primary key ngắn, ổn định vì nó xuất hiện trong secondary index.
4. Kiểm tra leftmost prefix, duplicate và redundant index trước khi tạo index mới.
5. Xem xét index width, prefix length, collation và hướng ASC/DESC.
6. Không mở rộng covering index nếu lợi ích đọc không bù chi phí ghi và bộ nhớ.
7. Đánh giá foreign key và unique constraint trước khi xóa index.
8. Quan sát index đủ chu kỳ workload và dùng invisible index để thử tác động khi phù hợp.
9. Thay đổi từng index, đo lại query latency, write throughput, I/O và dung lượng.
10. Ghi lại lý do giữ/xóa index để lần bảo trì sau không tạo lại index dư thừa.

Index tốt là index giúp workload đạt yêu cầu với tổng chi phí hợp lý. Số lượng index ít không tự động tốt, và số lượng index nhiều cũng không bảo đảm truy vấn nhanh. Thiết kế cần cân bằng tốc độ đọc, tốc độ ghi, dung lượng, ràng buộc dữ liệu và khả năng vận hành; việc đo workload và thử invisible index giúp loại bỏ index dư thừa có kiểm soát.
