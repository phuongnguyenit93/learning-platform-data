# MyISAM, cơ chế khóa và giới hạn về giao dịch

MySQL có thể lưu dữ liệu bằng nhiều storage engine. Storage engine quyết định cách bảng được lưu trữ, cách truy cập dữ liệu, cơ chế khóa, khả năng phục hồi và việc hỗ trợ transaction. **MyISAM** là một engine lâu đời của MySQL, từng được dùng rộng rãi cho các bảng đọc nhiều và ít cập nhật. Điểm cần hiểu rõ nhất khi làm việc với MyISAM là engine này dùng khóa ở cấp bảng và không hỗ trợ transaction.

Điều đó ảnh hưởng trực tiếp đến cách nhiều kết nối cùng đọc/ghi, cách ứng dụng xử lý lỗi giữa chừng và mức độ an toàn của dữ liệu khi máy chủ gặp sự cố. MyISAM vẫn có thể xuất hiện trong hệ thống cũ hoặc một số workload đặc thù, nhưng với ứng dụng mới cần transaction, khóa ngoại và khả năng phục hồi tốt, InnoDB thường là lựa chọn phù hợp hơn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của storage engine và nhận biết bảng MyISAM trong MySQL.
- Mô tả cách MyISAM sử dụng khóa bảng khi đọc và ghi.
- Phân tích ảnh hưởng của khóa bảng đến các kết nối đồng thời và thời gian chờ.
- Giải thích vì sao `COMMIT` và `ROLLBACK` không cung cấp tính nguyên tử cho dữ liệu MyISAM.
- Nhận biết giới hạn của MyISAM về khóa ngoại, phục hồi sau sự cố và các thao tác nhiều bảng.
- Kiểm tra engine của bảng hiện có và đưa ra quyết định khi duy trì hoặc chuyển đổi bảng MyISAM.

## 1. Storage engine nằm ở đâu trong MySQL?

MySQL Server tiếp nhận câu lệnh SQL, kiểm tra quyền, phân tích cú pháp và tối ưu truy vấn. Khi cần đọc hoặc ghi dữ liệu của một bảng, máy chủ làm việc với storage engine mà bảng đó sử dụng. Vì vậy, hai bảng trong cùng một database có thể dùng hai engine khác nhau và có hành vi khác nhau về khóa, transaction hoặc lưu trữ.

Một số engine thường gặp:

| Engine | Đặc điểm chính | Trường hợp thường gặp |
|---|---|---|
| InnoDB | Transaction, khóa hàng kết hợp khóa chỉ mục, khóa ngoại, phục hồi sau sự cố | Hầu hết ứng dụng giao dịch và hệ thống mới |
| MyISAM | Không có transaction, khóa bảng, chỉ mục tách biệt với dữ liệu | Hệ thống cũ, bảng đọc nhiều hoặc workload đặc thù đã được đánh giá |
| MEMORY | Dữ liệu bảng lưu trong bộ nhớ; dữ liệu mất khi máy chủ khởi động lại | Dữ liệu tạm hoặc tra cứu ngắn hạn khi chấp nhận mất dữ liệu |
| CSV | Lưu dữ liệu dạng văn bản CSV với khả năng truy cập qua SQL hạn chế | Trao đổi dữ liệu hoặc trường hợp tích hợp đặc thù |

Không nên chọn engine chỉ dựa trên tên hoặc giả định rằng một engine luôn nhanh hơn. Cần đối chiếu workload, tính nhất quán, concurrency, dung lượng, sao lưu và khả năng phục hồi. Bài này tập trung vào MyISAM và những hệ quả của thiết kế khóa bảng.

## 2. MyISAM lưu trữ và phục vụ dữ liệu như thế nào?

MyISAM lưu dữ liệu hàng và chỉ mục trong các cấu trúc tách biệt. Trên hệ thống file truyền thống, bạn thường thấy file dữ liệu `.MYD` và file chỉ mục `.MYI` tương ứng với bảng. Metadata bảng được quản lý bởi MySQL; chi tiết file phụ thuộc phiên bản và cách triển khai.

MyISAM hỗ trợ khóa chính, khóa duy nhất và nhiều loại index như B-tree; engine cũng có hỗ trợ FULLTEXT và SPATIAL trong các trường hợp phù hợp. Tuy nhiên, có index không có nghĩa là engine hỗ trợ khóa hàng hoặc transaction. Index giúp tìm hàng nhanh hơn, còn khóa bảng quyết định cách các kết nối đồng thời được phép đọc và ghi.

Kiểm tra engine của các bảng trong database hiện tại:

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

`TABLE_ROWS` phụ thuộc storage engine: với MyISAM, số hàng thường được lưu và báo chính xác; với InnoDB, đây thường là giá trị ước lượng. Nếu cần một cách kiểm tra thống nhất giữa nhiều engine hoặc cần xác minh dữ liệu thực tế, dùng `SELECT COUNT(*)` và cân nhắc chi phí truy vấn.

Kiểm tra riêng một bảng:

```sql
SHOW TABLE STATUS LIKE 'myisam_inventory';
SHOW CREATE TABLE myisam_inventory;
```

Trong kết quả, trường `Engine` cho biết storage engine đang sử dụng. `SHOW CREATE TABLE` cho biết engine và các định nghĩa cột, index, constraint mà MySQL hiển thị.

## 3. Tạo bảng MyISAM để quan sát

Thực hành trong database sandbox. Ví dụ sau tạo một bảng tồn kho đơn giản:

```sql
CREATE TABLE myisam_inventory (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(120) NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_myisam_inventory_sku (sku),
    KEY idx_myisam_inventory_quantity (quantity)
) ENGINE = MyISAM
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

INSERT INTO myisam_inventory (sku, product_name, quantity)
VALUES
    ('KB-001', 'Bàn phím', 20),
    ('MS-001', 'Chuột', 35),
    ('MN-001', 'Màn hình', 8);

SHOW CREATE TABLE myisam_inventory;
SELECT * FROM myisam_inventory ORDER BY product_id;
```

Định nghĩa `ENGINE = MyISAM` yêu cầu MySQL tạo bảng bằng engine này. Nếu engine không có sẵn hoặc bị vô hiệu hóa trong bản phân phối đang dùng, thao tác tạo bảng sẽ thất bại. Hãy kiểm tra engine được hỗ trợ thay vì giả định mọi máy chủ đều có cấu hình giống nhau.

MyISAM có thể lưu index và thực thi một số ràng buộc ở tầng máy chủ, chẳng hạn `PRIMARY KEY` và `UNIQUE`. Tuy nhiên, engine không cung cấp cơ chế thực thi khóa ngoại như InnoDB. Không thiết kế ứng dụng dựa trên giả định MyISAM sẽ bảo đảm quan hệ tham chiếu giữa các bảng.

## 4. Cơ chế khóa bảng của MyISAM

MyISAM sử dụng table-level locking: đơn vị khóa là toàn bộ bảng. Khi một câu lệnh cần đọc hoặc ghi bảng, MySQL lấy khóa phù hợp để điều phối truy cập của các kết nối.

| Loại khóa | Kết nối đang giữ khóa | Kết nối khác |
|---|---|---|
| Read lock | Có thể đọc bảng | Có thể cùng đọc; yêu cầu ghi phải chờ |
| Write lock | Có thể đọc và ghi bảng | Yêu cầu đọc hoặc ghi phải chờ cho đến khi khóa được nhả |

Một truy vấn `SELECT` thông thường lấy khóa đọc trong thời gian cần thiết. Các câu lệnh thay đổi dữ liệu như `INSERT`, `UPDATE` và `DELETE` cần khóa ghi. Với MyISAM, khóa ghi áp dụng cho bảng, kể cả khi câu `UPDATE` chỉ thay đổi một hàng. Đây là khác biệt quan trọng so với InnoDB, nơi khóa hàng và khóa chỉ mục cho phép nhiều thao tác độc lập trên các hàng khác nhau diễn ra đồng thời trong nhiều tình huống.

### 4.1. Nhiều lượt đọc có thể chạy đồng thời

Khi các kết nối chỉ đọc bảng MyISAM, chúng có thể cùng giữ read lock. Ví dụ, nhiều người dùng mở trang danh mục sản phẩm có thể đọc cùng một bảng mà không phải lần lượt chờ nhau chỉ vì có truy vấn đọc khác.

### 4.2. Ghi có thể chặn cả bảng

Khi một kết nối giữ write lock, các kết nối khác không thể đọc hoặc ghi bảng cho đến khi khóa được giải phóng. Nếu câu `UPDATE` mất nhiều thời gian, các request đọc danh mục cũng có thể phải chờ, dù chúng chỉ cần những hàng không liên quan đến hàng đang cập nhật.

Ví dụ minh họa:

```sql
UPDATE myisam_inventory
SET quantity = quantity - 1
WHERE sku = 'KB-001';
```

Điều kiện `WHERE` xác định hàng cần thay đổi, nhưng không làm phạm vi khóa của MyISAM thu nhỏ thành một hàng. Engine vẫn dùng khóa ghi ở cấp bảng.

### 4.3. Concurrent insert là trường hợp có điều kiện

MyISAM có thể cho phép một số thao tác chèn ở cuối file dữ liệu diễn ra đồng thời với truy vấn đọc, tùy tình trạng bảng và cấu hình. Khả năng này thường được gọi là concurrent insert. Nếu bảng có vùng trống do hàng bị xóa hoặc thao tác không đáp ứng điều kiện, việc chèn có thể phải chờ khóa đọc được giải phóng.

Không nên xem concurrent insert là row-level locking hoặc giả định mọi lệnh `INSERT` đều chạy song song với `SELECT`. Khi thiết kế tải ghi đồng thời, cần kiểm thử đúng dạng dữ liệu và chuỗi thao tác thực tế.

## 5. Quan sát khóa tường minh bằng hai session

MySQL cung cấp `LOCK TABLES` và `UNLOCK TABLES` để một session chủ động khóa bảng. Các ví dụ sau cần hai kết nối riêng, gọi là **Session A** và **Session B**. Hãy dùng bảng sandbox `myisam_inventory` vừa tạo.

### 5.1. Read lock

Trong Session A:

```sql
LOCK TABLES myisam_inventory READ;

SELECT *
FROM myisam_inventory
ORDER BY product_id;
```

Trong lúc Session A giữ read lock, thử câu lệnh sau ở Session B:

```sql
SELECT *
FROM myisam_inventory;

UPDATE myisam_inventory
SET quantity = quantity + 1
WHERE sku = 'KB-001';
```

Truy vấn đọc ở Session B có thể thực hiện; câu lệnh ghi phải chờ cho đến khi Session A nhả read lock. Quay lại Session A và chạy:

```sql
UNLOCK TABLES;
```

Sau khi khóa được nhả, câu `UPDATE` đang chờ ở Session B có thể tiếp tục. Hãy xác nhận bằng một truy vấn `SELECT` mới.

### 5.2. Write lock

Trong Session A:

```sql
LOCK TABLES myisam_inventory WRITE;

UPDATE myisam_inventory
SET quantity = quantity + 5
WHERE sku = 'MS-001';
```

Trong Session B, thử đọc hoặc ghi:

```sql
SELECT * FROM myisam_inventory;

UPDATE myisam_inventory
SET quantity = quantity - 1
WHERE sku = 'MS-001';
```

Các câu lệnh ở Session B phải chờ write lock được nhả. Session A có thể đọc và ghi bảng đang khóa. Sau khi kiểm tra xong, giải phóng khóa ở Session A:

```sql
UNLOCK TABLES;
```

**Lưu ý khi thực hành:** không để một session giữ khóa rồi quên giải phóng. Nếu Session A còn giữ khóa, các kết nối khác có thể bị treo chờ và gây ra hiện tượng dịch vụ chậm. Trong bài thực hành, chủ động nhả khóa ngay sau khi quan sát xong; nếu cần dừng thử nghiệm, đóng kết nối giữ khóa cũng sẽ kết thúc trạng thái khóa gắn với session đó.

`LOCK TABLES` là cơ chế điều phối truy cập bảng, không phải transaction. Không dùng nó để thay thế `COMMIT`/`ROLLBACK`, và cần kiểm tra quy tắc implicit commit của lệnh khóa trong phiên bản MySQL đang chạy trước khi kết hợp với transaction của engine khác.

## 6. MyISAM không hỗ trợ transaction

Transaction gom nhiều thao tác dữ liệu thành một đơn vị logic. Với engine hỗ trợ transaction như InnoDB, ứng dụng có thể xác nhận bằng `COMMIT` hoặc hủy các thay đổi chưa commit bằng `ROLLBACK`. MyISAM không có khả năng transaction như vậy.

Các thao tác ghi trên bảng MyISAM được thực hiện theo cơ chế non-transactional. Khi câu lệnh thành công, thay đổi được áp dụng trực tiếp; nếu câu lệnh sau đó thất bại, MySQL không thể dùng `ROLLBACK` để hoàn tác các thay đổi MyISAM đã thực hiện.

### 6.1. Thử nghiệm rollback trên MyISAM

Trong database sandbox, chạy:

```sql
START TRANSACTION;

UPDATE myisam_inventory
SET quantity = quantity + 10
WHERE sku = 'KB-001';

SELECT sku, quantity
FROM myisam_inventory
WHERE sku = 'KB-001';

ROLLBACK;

SELECT sku, quantity
FROM myisam_inventory
WHERE sku = 'KB-001';
```

Giá trị `quantity` sau `ROLLBACK` vẫn giữ phần tăng thêm 10. `START TRANSACTION` không biến một bảng MyISAM thành bảng transactional. Hãy ghi lại số lượng ban đầu nếu muốn khôi phục thủ công sau bài tập.

### 6.2. Vì sao điều này nguy hiểm với nghiệp vụ nhiều bước?

Giả sử một thao tác thanh toán cần:

1. Tạo bản ghi đơn hàng.
2. Trừ số lượng tồn kho.
3. Ghi nhận thanh toán.
4. Cập nhật trạng thái đơn hàng.

Nếu các bảng đều dùng InnoDB, ứng dụng có thể gom những thay đổi liên quan vào một transaction và rollback khi một bước thất bại, miễn là mọi thao tác thuộc cùng transaction và không có tác động ngoài transaction.

Nếu các bảng dùng MyISAM, thao tác thứ nhất và thứ hai có thể đã được ghi khi bước thứ ba thất bại. Ứng dụng phải tự xây dựng logic bù trừ hoặc sửa chữa dữ liệu, nhưng logic bù trừ cũng có thể thất bại và cần được thiết kế, kiểm toán riêng. Không thể dựa vào `ROLLBACK` để đưa toàn bộ nghiệp vụ về trạng thái ban đầu.

## 7. Không trộn MyISAM và InnoDB trong một transaction nghiệp vụ

MySQL cho phép một database có nhiều engine, thậm chí một câu lệnh hoặc transaction có thể chạm đến nhiều bảng khác engine. Tuy nhiên, tính nguyên tử chỉ được bảo đảm cho phần dữ liệu thuộc engine transactional và trong phạm vi transaction đó. Thay đổi trên bảng MyISAM không được rollback cùng với InnoDB.

Ví dụ minh họa trong sandbox:

```sql
CREATE TABLE transaction_demo_innodb (
    id INT NOT NULL PRIMARY KEY,
    amount INT NOT NULL
) ENGINE = InnoDB;

CREATE TABLE transaction_demo_myisam (
    id INT NOT NULL PRIMARY KEY,
    amount INT NOT NULL
) ENGINE = MyISAM;

INSERT INTO transaction_demo_innodb VALUES (1, 100);
INSERT INTO transaction_demo_myisam VALUES (1, 100);

START TRANSACTION;

UPDATE transaction_demo_innodb
SET amount = amount + 50
WHERE id = 1;

UPDATE transaction_demo_myisam
SET amount = amount + 50
WHERE id = 1;

ROLLBACK;

SELECT * FROM transaction_demo_innodb;
SELECT * FROM transaction_demo_myisam;
```

Sau `ROLLBACK`, bảng InnoDB trở về `amount = 100`; bảng MyISAM vẫn có `amount = 150`. Ví dụ cho thấy một transaction chứa bảng MyISAM không tạo ra tính nguyên tử cho tất cả bảng.

Khi thiết kế nghiệp vụ cần nhiều bảng thay đổi nhất quán, hãy dùng cùng một engine transactional phù hợp, thường là InnoDB, cho tất cả bảng tham gia. Nếu một hệ thống cũ bắt buộc có tích hợp ngoài transaction, phải thiết kế quy trình bù trừ, idempotency, đối soát và ghi nhận lỗi riêng.

## 8. Giới hạn về khóa ngoại và tính toàn vẹn dữ liệu

MyISAM không thực thi foreign key constraint. Một bảng MyISAM có thể lưu cột mang tên `customer_id`, nhưng engine không bảo đảm giá trị đó phải tồn tại trong bảng khách hàng. Ứng dụng có thể vô tình ghi tham chiếu không hợp lệ nếu chỉ dựa vào engine để kiểm soát.

Ví dụ, giả sử có bảng đơn hàng MyISAM:

```sql
CREATE TABLE myisam_order_reference (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_total DECIMAL(12,2) NOT NULL,
    KEY idx_myisam_order_customer (customer_id)
) ENGINE = MyISAM;
```

Index trên `customer_id` chỉ hỗ trợ truy vấn. Nó không xác nhận khách hàng có tồn tại. Muốn bảo đảm quan hệ tham chiếu, cần kiểm tra ở tầng ứng dụng và có quy trình đồng bộ/đối soát, hoặc chuyển bảng sang engine hỗ trợ foreign key như InnoDB.

Ngay cả khi ứng dụng kiểm tra khách hàng trước khi insert, nhiều request đồng thời vẫn có thể tạo race condition giữa bước kiểm tra và bước ghi. Ràng buộc foreign key của engine transactional là cách bảo vệ ở tầng database tốt hơn cho quan hệ dữ liệu.

## 9. Khả năng phục hồi và bảo trì

Vì MyISAM không có transaction log và cơ chế phục hồi crash-safe như InnoDB, sự cố máy chủ hoặc hệ điều hành có thể khiến bảng bị đánh dấu hỏng hoặc chỉ mục không còn nhất quán với dữ liệu. MyISAM có công cụ kiểm tra và sửa chữa bảng, nhưng sửa chữa không thay thế được bản sao lưu và không bảo đảm khôi phục được mọi thay đổi gần nhất.

Một số lệnh kiểm tra/bảo trì:

```sql
CHECK TABLE myisam_inventory;

-- Chỉ chạy khi đã đánh giá tình trạng bảng và có bản sao lưu phù hợp
REPAIR TABLE myisam_inventory;

ANALYZE TABLE myisam_inventory;
```

- `CHECK TABLE` kiểm tra bảng và báo các vấn đề phát hiện được.
- `REPAIR TABLE` cố gắng sửa bảng MyISAM bị lỗi. Đây là thao tác bảo trì có thể kéo dài và có rủi ro; hãy sao lưu trước khi thực hiện trên dữ liệu cần giữ.
- `ANALYZE TABLE` cập nhật thống kê chỉ mục để bộ tối ưu truy vấn có thông tin tốt hơn.

Với MyISAM, cần có lịch sao lưu phù hợp, quy trình kiểm tra bản sao và kế hoạch phục hồi đã diễn tập. Khi sao chép file dữ liệu ở cấp filesystem, phải bảo đảm bảng ở trạng thái nhất quán và tuân thủ quy trình sao lưu của MySQL; không tùy tiện copy file đang được ghi.

## 10. So sánh MyISAM và InnoDB

| Tiêu chí | MyISAM | InnoDB |
|---|---|---|
| Transaction | Không hỗ trợ | Có hỗ trợ `COMMIT` và `ROLLBACK` |
| Granularity khóa dữ liệu | Khóa bảng | Chủ yếu khóa hàng và khóa chỉ mục; vẫn có metadata/table locks trong các tình huống nhất định |
| Đọc đồng thời | Nhiều reader có thể cùng đọc | Hỗ trợ đọc đồng thời tốt, gồm consistent reads |
| Ghi đồng thời | Ghi có thể chặn truy cập toàn bảng | Nhiều transaction có thể sửa các hàng khác nhau đồng thời |
| Foreign key | Không thực thi | Hỗ trợ |
| Phục hồi crash | Có thể cần kiểm tra/sửa bảng | Có cơ chế crash recovery dựa trên redo/undo log |
| Phù hợp với | Bảng cũ, đọc nhiều, ít cập nhật và không cần transaction | Ứng dụng giao dịch, dữ liệu quan hệ và hệ thống mới |

InnoDB vẫn có thể gặp tranh chấp khóa, deadlock hoặc chờ metadata lock. Khóa hàng không có nghĩa mọi thao tác luôn độc lập. Tuy nhiên, cơ chế transaction và khóa chi tiết hơn của InnoDB thường phù hợp hơn cho ứng dụng có nhiều thao tác ghi đồng thời.

## 11. Khi nào cần giữ hoặc chuyển đổi MyISAM?

Không nên chuyển engine chỉ vì nhìn thấy `ENGINE=MyISAM`. Trước hết, cần xác định bảng đang phục vụ chức năng gì, có bao nhiêu thao tác ghi, có cần transaction hoặc foreign key không, và các ứng dụng có phụ thuộc vào hành vi hiện tại hay không.

MyISAM có thể được giữ tạm thời khi:

- Bảng thuộc hệ thống cũ và đang hoạt động ổn định, có quy trình sao lưu/kiểm tra phù hợp.
- Dữ liệu gần như chỉ đọc, ít cập nhật và nhóm đã đo đạc tác động của table lock.
- Một tính năng đặc thù của MyISAM đang được sử dụng và có kế hoạch thay thế rõ ràng.

Nên ưu tiên kế hoạch chuyển sang InnoDB khi:

- Ứng dụng cần `COMMIT`/`ROLLBACK` cho nhiều thay đổi liên quan.
- Nhiều kết nối ghi đồng thời và table lock gây thời gian chờ đáng kể.
- Cần foreign key để bảo vệ quan hệ dữ liệu.
- Yêu cầu phục hồi sau crash, tính sẵn sàng và độ tin cậy dữ liệu cao hơn.
- Bảng tham gia vào nghiệp vụ thanh toán, tồn kho, đơn hàng hoặc các luồng cần tính nguyên tử.

Trước khi chuyển đổi, hãy kiểm tra dung lượng đĩa, kiểu dữ liệu, index, ràng buộc, câu truy vấn, ứng dụng phụ thuộc, thời gian khóa bảng và cửa sổ triển khai. Ví dụ cú pháp chuyển engine:

```sql
ALTER TABLE myisam_inventory ENGINE = InnoDB;
```

Lệnh này có thể cần dựng lại bảng, tạo tải I/O đáng kể và giữ khóa trong một khoảng thời gian tùy kích thước dữ liệu, phiên bản và cách triển khai. Cần thử trên bản sao dữ liệu gần production, sao lưu trước, đo thời gian, kiểm tra ứng dụng sau chuyển đổi và chuẩn bị kế hoạch quay lại phù hợp. Không chạy lệnh trên bảng production chỉ để thử nghiệm.

## 12. Checklist khi vận hành bảng MyISAM

- Đã xác định bảng thực sự dùng MyISAM qua `SHOW TABLE STATUS` hoặc `information_schema.tables`.
- Đã biết mọi thao tác ghi có thể khóa toàn bảng và làm các truy vấn khác phải chờ.
- Đã đo thời gian giữ khóa và thời gian chờ dưới tải gần thực tế.
- Đã xác minh ứng dụng không dựa vào `ROLLBACK` để hoàn tác dữ liệu MyISAM.
- Đã kiểm tra các quan hệ tham chiếu bằng logic ứng dụng hoặc quy trình đối soát vì MyISAM không thực thi foreign key.
- Đã có sao lưu, kiểm tra tính khôi phục và runbook kiểm tra/sửa bảng.
- Đã cân nhắc ảnh hưởng khi trộn MyISAM với InnoDB trong một luồng nghiệp vụ.
- Đã có lý do kỹ thuật cụ thể để giữ MyISAM hoặc kế hoạch chuyển đổi được thử nghiệm.

MyISAM minh họa rõ rằng storage engine ảnh hưởng trực tiếp đến tính đồng thời và tính toàn vẹn của dữ liệu. Khóa bảng khiến thao tác ghi có thể chặn cả bảng; việc không hỗ trợ transaction khiến thay đổi không thể được rollback; việc không thực thi foreign key và khả năng phục hồi hạn chế đòi hỏi quy trình kiểm soát bổ sung. Hiểu những giới hạn này giúp bạn nhận diện rủi ro trong hệ thống cũ và chọn engine phù hợp cho từng workload MySQL.
