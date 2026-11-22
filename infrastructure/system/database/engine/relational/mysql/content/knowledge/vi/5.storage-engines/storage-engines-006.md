# TempTable và phân biệt bảng tạm nội bộ với bảng tạm người dùng

Trong MySQL, cụm từ “bảng tạm” có thể chỉ hai cơ chế khác nhau. Máy chủ có thể tự tạo *internal temporary table* khi tối ưu và thực thi một truy vấn. Người lập trình cũng có thể chủ động tạo *user-created temporary table* bằng câu lệnh `CREATE TEMPORARY TABLE`. Cả hai đều phục vụ dữ liệu tạm thời, nhưng quyền kiểm soát, vòng đời, cách quan sát và storage engine của chúng khác nhau.

TempTable là storage engine MySQL dùng cho một số bảng tạm nội bộ trong bộ nhớ. Nó là chi tiết triển khai của máy chủ, không phải tên engine mà ứng dụng chọn để tạo bảng tạm của riêng mình. Bảng tạm do người dùng tạo là một đối tượng SQL thuộc session hiện tại; bạn có thể đặt tên, tạo index, ghi dữ liệu, truy vấn và chủ động xóa nó.

Bài học này thuộc module `DATABASE_MYSQL`, bao gồm thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền và vận hành cơ sở dữ liệu quan hệ. Hiểu hai loại bảng tạm giúp bạn đọc `EXPLAIN`, điều tra chi phí truy vấn và quản lý dữ liệu trung gian đúng vòng đời.

Sau bài học, bạn có thể:

- Phân biệt internal temporary table với bảng tạo bằng `CREATE TEMPORARY TABLE`.
- Giải thích TempTable được dùng ở đâu trong quá trình thực thi truy vấn.
- Nhận biết một số tình huống optimizer có thể materialize dữ liệu vào bảng tạm nội bộ.
- Kiểm tra cấu hình và số liệu liên quan đến bảng tạm nội bộ.
- Tạo, sử dụng, kiểm tra phạm vi session và xóa bảng tạm của người dùng.
- Tránh nhầm lẫn giữa bảng tạm trong bộ nhớ, bảng tạm trên đĩa và bảng tạm nội bộ của optimizer.

## 1. Hai khái niệm cùng tên nhưng khác vai trò

| Tiêu chí | Bảng tạm nội bộ (internal temporary table) | Bảng tạm do người dùng tạo (user-created temporary table) |
| --- | --- | --- |
| Ai tạo? | MySQL Server/optimizer tự tạo khi cần xử lý truy vấn | Ứng dụng hoặc người dùng chạy `CREATE TEMPORARY TABLE` |
| Mục đích | Materialize dữ liệu trung gian để thực hiện một phần kế hoạch truy vấn | Lưu dữ liệu trung gian do ứng dụng chủ động quản lý qua nhiều câu SQL |
| Tên bảng | Nội bộ, không phải tên đối tượng SQL do người dùng đặt | Do người tạo đặt tên |
| Phạm vi | Do máy chủ quản lý theo quá trình thực thi hoặc materialization | Chỉ session tạo bảng nhìn thấy bảng đó |
| Cách xóa | Máy chủ tự quản lý vòng đời | `DROP TEMPORARY TABLE` hoặc kết thúc session |
| Engine | TempTable cho bảng nội bộ trong bộ nhớ; có thể chuyển sang InnoDB trên đĩa | Dùng engine hỗ trợ được chỉ định trong DDL, ví dụ InnoDB hoặc MEMORY |
| Quan sát | Có thể nhận biết gián tiếp qua `EXPLAIN` và status counters | Có thể truy vấn trực tiếp trong session tạo bảng; không được liệt kê như bảng thường trong `SHOW TABLES` |

Điểm cần nhớ: **TempTable là engine phục vụ một loại bảng tạm nội bộ; `CREATE TEMPORARY TABLE` là câu lệnh tạo bảng tạm thuộc session.** Không dùng hai thuật ngữ này thay thế cho nhau.

## 2. Internal temporary table được tạo khi nào?

MySQL có thể cần lưu kết quả trung gian trong lúc thực hiện một truy vấn. Thay vì tính lại hoặc truyền toàn bộ dữ liệu trực tiếp qua từng bước, optimizer có thể materialize một phần kết quả vào bảng tạm nội bộ rồi tiếp tục đọc từ đó.

Một số tình huống có thể cần internal temporary table:

- Xử lý một số dạng `UNION`, đặc biệt khi cần loại bỏ hàng trùng lặp như `UNION DISTINCT`.
- Materialize derived table hoặc common table expression (CTE) khi optimizer chọn chiến lược materialization thay vì merge.
- Một số truy vấn `GROUP BY`, `DISTINCT` hoặc `ORDER BY` không thể được giải quyết trực tiếp bằng index phù hợp.
- Một số phép tính trên window function hoặc truy vấn phức tạp cần lưu kết quả trung gian.
- Một số chiến lược thực thi khác yêu cầu lưu tập kết quả để sử dụng ở bước sau.

Đây là các trường hợp *có thể* dùng bảng tạm, không phải quy tắc rằng cứ xuất hiện `GROUP BY`, `DISTINCT`, `ORDER BY` hoặc CTE là MySQL luôn tạo bảng tạm. Optimizer có thể dùng index, merge derived table, thay đổi thứ tự xử lý hoặc chọn một chiến lược khác tùy cấu trúc truy vấn, thống kê, dữ liệu và phiên bản máy chủ.

Ví dụ truy vấn tổng hợp:

```sql
CREATE TABLE sales_demo (
    sale_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    sold_at DATETIME NOT NULL,
    PRIMARY KEY (sale_id),
    KEY idx_sales_customer (customer_id)
) ENGINE = InnoDB;

INSERT INTO sales_demo (customer_id, amount, sold_at) VALUES
(1, 120.00, '2026-01-05 10:00:00'),
(1, 80.00,  '2026-01-07 11:00:00'),
(2, 250.00, '2026-01-08 09:30:00'),
(3, 60.00,  '2026-01-10 14:15:00'),
(2, 90.00,  '2026-01-11 16:20:00');

EXPLAIN
SELECT customer_id, SUM(amount) AS total_amount
FROM sales_demo
GROUP BY customer_id
ORDER BY total_amount DESC;
```

Truy vấn nhóm dữ liệu theo khách hàng, tính tổng và sắp xếp theo giá trị tổng. Tùy kế hoạch thực thi, MySQL có thể cần một cấu trúc trung gian để nhóm hoặc sắp xếp kết quả. Đọc phần `Extra` của `EXPLAIN` để tìm thông tin như `Using temporary` hoặc `Using filesort`; không suy ra ngay rằng dữ liệu đã được ghi xuống đĩa.

## 3. TempTable trong MySQL

Trong MySQL 8.4, engine `TempTable` là lựa chọn mặc định cho các internal temporary table trong bộ nhớ. Trước MySQL 8.0.16, engine `MEMORY` được dùng mặc định cho loại bảng tạm nội bộ này. Cấu hình hiện tại có thể được kiểm tra trực tiếp thay vì suy đoán theo phiên bản.

TempTable được thiết kế cho dữ liệu trung gian của máy chủ. Nó hỗ trợ định dạng hàng có độ dài biến đổi và các kiểu dữ liệu như `VARCHAR`, `VARBINARY`, `TEXT` và `BLOB` trong các bảng tạm nội bộ. Điều này khác với engine MEMORY truyền thống, vốn có các giới hạn về kiểu dữ liệu và tổ chức hàng.

### 3.1. Từ bộ nhớ tới lưu trữ trên đĩa

Không phải mọi internal temporary table đều nằm hoàn toàn trong RAM trong suốt quá trình truy vấn. MySQL quản lý mức sử dụng bộ nhớ theo các giới hạn cấu hình. Khi vượt ngưỡng, dữ liệu có thể được chuyển qua vùng memory-mapped file; nếu giới hạn của vùng này cũng đạt tới, internal temporary table có thể được chuyển sang dạng trên đĩa dùng InnoDB.

```text
Truy vấn cần dữ liệu trung gian
              |
              v
      Internal temporary table
              |
              v
      TempTable trong RAM
              |
       vượt giới hạn RAM
              v
    Memory-mapped file (nếu cho phép)
              |
   vượt giới hạn mmap / mmap tắt
              v
      Internal InnoDB trên đĩa
```

Sơ đồ mô tả đường đi khái quát. Chi tiết chuyển đổi phụ thuộc các biến cấu hình, phiên bản và loại truy vấn. Việc một truy vấn có internal temporary table không đồng nghĩa nó chắc chắn gây I/O đĩa; ngược lại, truy vấn có thể tốn bộ nhớ hoặc I/O đáng kể dù không thấy một dòng log đơn giản báo “temporary table”.

### 3.2. MEMORY và TempTable khác nhau ra sao?

`MEMORY` là storage engine có thể được dùng để tạo bảng người dùng bằng `ENGINE=MEMORY`. Nó lưu các hàng trong RAM và có những giới hạn riêng, chẳng hạn không hỗ trợ các kiểu `BLOB` và `TEXT` như InnoDB; cấu trúc hàng có đặc tính độ dài cố định. Nội dung bảng mất khi máy chủ khởi động lại.

`TempTable` được dùng cho internal temporary table do MySQL quản lý. Ứng dụng không nên coi nó là engine thông thường để khai báo trong `CREATE TABLE` hoặc `CREATE TEMPORARY TABLE`. Khi cần bảng tạm do mình quản lý, hãy chọn một engine được hỗ trợ cho bảng người dùng như InnoDB hoặc MEMORY.

## 4. Cấu hình internal temporary table

Các biến dưới đây giúp điều khiển việc MySQL tạo và lưu trữ bảng tạm nội bộ. Tên và giá trị hiện hành nên được xác minh trên máy chủ cụ thể.

```sql
SHOW VARIABLES LIKE 'internal_tmp_mem_storage_engine';
SHOW VARIABLES LIKE 'temptable_max_ram';
SHOW VARIABLES LIKE 'temptable_max_mmap';
SHOW VARIABLES LIKE 'tmp_table_size';
SHOW VARIABLES LIKE 'max_heap_table_size';
SHOW VARIABLES LIKE 'tmpdir';
```

| Biến | Vai trò tổng quát |
| --- | --- |
| `internal_tmp_mem_storage_engine` | Chọn engine cho internal temporary table trong bộ nhớ; MySQL 8.4 thường mặc định `TempTable`, có thể cấu hình `MEMORY` |
| `temptable_max_ram` | Giới hạn lượng RAM mà TempTable engine sử dụng trước khi cần cơ chế lưu trữ khác |
| `temptable_max_mmap` | Giới hạn vùng memory-mapped file mà TempTable có thể sử dụng trước khi chuyển sang internal temporary table trên đĩa |
| `tmp_table_size` | Giới hạn kích thước của một số internal in-memory temporary table; ý nghĩa chi tiết phụ thuộc engine và phiên bản |
| `max_heap_table_size` | Giới hạn kích thước bảng dùng engine MEMORY; khi chọn MEMORY cho internal temporary table, cần xét cùng `tmp_table_size` |
| `tmpdir` | Thư mục tạm của máy chủ, được dùng cho một số tệp tạm và hoạt động liên quan |

`temptable_max_ram` và `temptable_max_mmap` kiểm soát các ngưỡng tài nguyên của TempTable. Khi bộ nhớ RAM đã đạt giới hạn, TempTable có thể sử dụng vùng memory-mapped file nếu còn dung lượng cho phép. Khi vùng đó đạt giới hạn hoặc bị tắt, dữ liệu internal temporary table có thể được chuyển sang InnoDB trên đĩa.

Không nên tăng mọi giới hạn lên mức lớn chỉ để loại bỏ thông báo `Using temporary`. Tăng ngưỡng có thể làm nhiều session đồng thời tiêu thụ RAM hoặc dung lượng tạm lớn hơn, gây áp lực lên máy chủ. Trước khi thay đổi, hãy đo tải thực tế, xem số session đồng thời, bộ nhớ khả dụng, vị trí thư mục tạm và dung lượng đĩa.

## 5. Quan sát internal temporary table

### 5.1. Đọc EXPLAIN

Chạy `EXPLAIN` cho truy vấn cần phân tích:

```sql
EXPLAIN
SELECT customer_id, SUM(amount) AS total_amount
FROM sales_demo
GROUP BY customer_id
ORDER BY total_amount DESC;
```

Trong định dạng truyền thống, cột `Extra` có thể hiển thị `Using temporary` khi kế hoạch dùng internal temporary table. `Using filesort` cho biết MySQL cần một bước sắp xếp không được giải quyết trực tiếp bằng thứ tự index; tên này không có nghĩa mọi trường hợp đều ghi ra file trên đĩa.

`Using temporary` không cho biết riêng bảng tạm đang nằm trong RAM, memory-mapped file hay InnoDB trên đĩa. Nó cũng không tự chứng minh truy vấn chậm. Hãy xem số hàng ước lượng, loại truy cập, index, thời gian thực thi và lượng dữ liệu được xử lý.

Có thể dùng `EXPLAIN FORMAT=JSON` để xem cấu trúc kế hoạch chi tiết hơn:

```sql
EXPLAIN FORMAT=JSON
SELECT customer_id, SUM(amount) AS total_amount
FROM sales_demo
GROUP BY customer_id
ORDER BY total_amount DESC;
```

`EXPLAIN ANALYZE` thực thi truy vấn đọc rồi báo thời gian và số hàng thực tế ở các iterator. Chỉ chạy khi có thể chấp nhận việc truy vấn thực sự được thực thi và tải mà nó tạo ra; tránh chạy truy vấn đọc rất nặng trên production nếu chưa đánh giá tác động.

### 5.2. Theo dõi status counters

MySQL cung cấp các bộ đếm liên quan đến internal temporary table:

```sql
SHOW SESSION STATUS LIKE 'Created_tmp%';
```

Các tên thường quan tâm:

- `Created_tmp_tables`: số internal temporary table được tạo trong phạm vi đo.
- `Created_tmp_disk_tables`: số internal temporary table trên đĩa được tạo trong phạm vi đo.

Bạn có thể đọc bộ đếm trước và sau một truy vấn để quan sát chênh lệch trong session hiện tại. Nếu cần số liệu toàn máy chủ, dùng `SHOW GLOBAL STATUS`, nhưng cần lưu ý số liệu global có thể chịu ảnh hưởng từ nhiều session và truy vấn khác.

Các bộ đếm không kể hết mọi cách TempTable sử dụng tài nguyên. Đặc biệt, vùng memory-mapped file của TempTable không nhất thiết được phản ánh giống một internal temporary table trên đĩa trong `Created_tmp_disk_tables`. Vì vậy, không dùng một counter đơn lẻ để kết luận chính xác lượng RAM hoặc disk I/O do truy vấn gây ra.

### 5.3. Hướng tối ưu khi thấy Using temporary

Khi một truy vấn cần bảng tạm nội bộ, hãy xem xét:

1. Index có hỗ trợ điều kiện lọc, thứ tự nhóm hoặc thứ tự sắp xếp không?
2. Có thể giảm số hàng trước khi nhóm hoặc sắp xếp không?
3. Có đang chọn nhiều cột không cần thiết khiến dữ liệu trung gian lớn hơn không?
4. Derived table hoặc CTE có thể được merge thay vì materialize không, và việc merge có thực sự giúp truy vấn không?
5. Số hàng và độ rộng hàng trung gian có vượt xa nhu cầu đầu ra không?
6. Có nhiều session đồng thời cùng tạo bảng tạm khiến RAM hoặc thư mục tạm bị áp lực không?

Ví dụ, index tổng hợp có thể giúp một số truy vấn lọc và nhóm theo `customer_id`, nhưng không có một index chung tối ưu cho mọi tổ hợp `WHERE`, `GROUP BY` và `ORDER BY`. Hãy thử thay đổi trên dữ liệu đại diện, chạy lại `EXPLAIN` và đo thời gian thực tế trước khi kết luận.

## 6. Bảng tạm do người dùng tạo

Khi ứng dụng cần giữ một tập dữ liệu trung gian qua nhiều câu SQL trong cùng session, bạn có thể tạo bảng tạm tường minh:

```sql
CREATE TEMPORARY TABLE tmp_customer_totals (
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

INSERT INTO tmp_customer_totals (customer_id, total_amount)
SELECT customer_id, SUM(amount)
FROM sales_demo
GROUP BY customer_id;

SELECT customer_id, total_amount
FROM tmp_customer_totals
ORDER BY total_amount DESC;

DROP TEMPORARY TABLE tmp_customer_totals;
```

Khác với internal temporary table, bạn chủ động điều khiển tên, schema, thời điểm tạo và xóa bảng. Bạn cũng có thể tham chiếu bảng trong các câu SQL tiếp theo của cùng session.

### 6.1. Phạm vi session và vòng đời

Bảng tạm người dùng chỉ hiển thị trong session đã tạo nó. Một kết nối khác không thể truy vấn bảng đó, kể cả khi dùng cùng username và database. Khi session kết thúc, MySQL tự xóa các bảng tạm thuộc session đó.

Ví dụ, mở hai kết nối:

**Session A:**

```sql
CREATE TEMPORARY TABLE tmp_session_demo (
    id INT PRIMARY KEY,
    note VARCHAR(100)
) ENGINE = InnoDB;

INSERT INTO tmp_session_demo VALUES (1, 'Chi thay trong session A');
SELECT * FROM tmp_session_demo;
```

**Session B:**

```sql
SELECT * FROM tmp_session_demo;
```

Session B nhận lỗi không tìm thấy bảng vì bảng chỉ tồn tại trong session A. Khi đóng session A, bảng tạm được tự động xóa.

### 6.2. Bảng tạm có thể che khuất bảng thường cùng tên

MySQL cho phép một session tạo temporary table trùng tên với một bảng thường. Trong session đó, tên bảng trỏ tới bảng tạm và che khuất bảng thường cùng tên cho tới khi bảng tạm bị xóa hoặc session kết thúc.

Điều này có thể hữu ích trong một số quy trình thử nghiệm, nhưng cũng dễ gây nhầm lẫn khi debug. Trước khi tạo bảng tạm, hãy dùng tên có tiền tố dễ nhận diện như `tmp_` và tránh trùng tên với bảng nghiệp vụ.

### 6.3. Chọn engine cho bảng tạm người dùng

Bạn có thể chọn engine tường minh trong DDL:

```sql
CREATE TEMPORARY TABLE tmp_memory_lookup (
    lookup_key VARCHAR(64) NOT NULL,
    lookup_value VARCHAR(255) NOT NULL,
    PRIMARY KEY (lookup_key)
) ENGINE = MEMORY;

CREATE TEMPORARY TABLE tmp_innodb_stage (
    row_id BIGINT NOT NULL,
    payload TEXT,
    PRIMARY KEY (row_id)
) ENGINE = InnoDB;
```

`MEMORY` giữ dữ liệu trong RAM và không giữ nội dung qua lần restart máy chủ. Với một bảng MEMORY thông thường, định nghĩa bảng có thể còn trong khi hàng dữ liệu bị mất; với bảng MEMORY tạm của người dùng, đối tượng còn bị xóa khi session kết thúc. InnoDB phù hợp hơn khi cần kiểu dữ liệu như `TEXT`, dữ liệu trung gian lớn hơn hoặc tính năng transactional. Bảng tạm người dùng dùng engine đã chọn cho DDL của chính nó; đừng suy luận engine của bảng chỉ từ chữ `TEMPORARY`.

### 6.4. Quyền và một số giới hạn

Để tạo bảng tạm, tài khoản cần quyền `CREATE TEMPORARY TABLES` trên database phù hợp. Có thể kiểm tra quyền:

```sql
SHOW GRANTS FOR CURRENT_USER();
```

Một số điểm cần nhớ:

- Bảng tạm người dùng không hỗ trợ foreign key constraint như bảng InnoDB thông thường.
- MySQL có giới hạn khi cùng một câu truy vấn tham chiếu một temporary table nhiều lần; trường hợp này có thể gặp lỗi `Can't reopen table`.
- `CREATE TEMPORARY TABLE` và `DROP TEMPORARY TABLE` không gây implicit commit giống các lệnh DDL tạo/xóa bảng thường, nhưng bản thân thao tác tạo/xóa bảng tạm không được rollback để phục hồi trạng thái trước đó.
- Bảng tạm được gắn với kết nối, không gắn với một request HTTP hay một transaction của ứng dụng.

Nếu ứng dụng dùng connection pool, kết nối vật lý có thể được trả về pool thay vì đóng thật. Temporary table có thể tiếp tục tồn tại khi một request khác nhận lại chính connection đó. Hãy chủ động `DROP TEMPORARY TABLE` trong khối cleanup hoặc bảo đảm mỗi lần mượn connection có quy trình khởi tạo và dọn dẹp rõ ràng.

## 7. So sánh qua tình huống thực tế

Giả sử một báo cáo cần tính tổng doanh thu theo khách hàng. Có hai cách tiếp cận:

**Cách A: để optimizer tự tạo cấu trúc trung gian.**

```sql
SELECT customer_id, SUM(amount) AS total_amount
FROM sales_demo
GROUP BY customer_id
ORDER BY total_amount DESC;
```

Bạn chỉ gửi một câu truy vấn. Nếu kế hoạch cần materialization, MySQL tự tạo internal temporary table, quản lý engine và giải phóng tài nguyên khi hoàn tất. Ứng dụng không biết tên bảng nội bộ và không thể trực tiếp truy vấn nó.

**Cách B: ứng dụng tạo bảng tạm rõ ràng.**

```sql
CREATE TEMPORARY TABLE tmp_report_totals (
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

INSERT INTO tmp_report_totals
SELECT customer_id, SUM(amount)
FROM sales_demo
GROUP BY customer_id;

SELECT * FROM tmp_report_totals ORDER BY total_amount DESC;
```

Ứng dụng có thể sử dụng kết quả trung gian ở nhiều câu lệnh, bổ sung index hoặc join với dữ liệu khác, nhưng phải quản lý tên và vòng đời bảng. Bảng tạm người dùng có thể tiêu tốn tài nguyên và không tự động làm truy vấn nhanh hơn. Cần đo và chọn cách phù hợp với yêu cầu xử lý.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| Thấy `Using temporary` nghĩa là MySQL đã ghi ra đĩa | Nó chỉ cho biết kế hoạch có dùng internal temporary table; nơi lưu có thể là RAM, memory-mapped file hoặc InnoDB trên đĩa |
| `TempTable` là engine để khai báo trong `CREATE TEMPORARY TABLE` | TempTable phục vụ internal temporary table; bảng do người dùng tạo cần chọn engine hỗ trợ cho DDL người dùng |
| `CREATE TEMPORARY TABLE` được optimizer tự sinh | Đây là câu lệnh do ứng dụng hoặc người dùng chủ động chạy |
| Bảng tạm người dùng nhìn thấy từ mọi kết nối | Nó chỉ hiển thị trong session tạo bảng |
| Đóng transaction sẽ xóa temporary table | Vòng đời bảng gắn với session; transaction commit/rollback không tự xóa nó |
| `Created_tmp_disk_tables` phản ánh toàn bộ dữ liệu TempTable đã rời RAM | Counter có giới hạn trong cách ghi nhận, đặc biệt với memory-mapped file; cần thêm chỉ số và quan sát tài nguyên |
| Mọi `GROUP BY` đều tạo internal temporary table | Optimizer có thể dùng index hoặc chiến lược khác; cần kiểm tra kế hoạch thực tế |

## 9. Bài tập thực hành

1. Chạy truy vấn tổng hợp ở phần 2 và xem `EXPLAIN`. Ghi lại `Using temporary` và `Using filesort` nếu xuất hiện.
2. Trước và sau truy vấn, kiểm tra `SHOW SESSION STATUS LIKE 'Created_tmp%';`. So sánh chênh lệch và giải thích giới hạn của bộ đếm.
3. Kiểm tra `internal_tmp_mem_storage_engine`, `temptable_max_ram`, `temptable_max_mmap` và `tmp_table_size` trên máy chủ. Ghi lại giá trị hiện tại, không thay đổi cấu hình nếu chưa có mục tiêu đo lường.
4. Tạo `tmp_customer_totals` bằng InnoDB, nạp kết quả tổng hợp và truy vấn nó bằng một câu SQL khác.
5. Mở hai session để chứng minh session B không nhìn thấy bảng tạm được tạo trong session A.
6. Tạo temporary table trùng tên với một bảng thường trong database lab. Quan sát bảng nào được tham chiếu trong session tạo temporary table, sau đó drop temporary table và kiểm tra lại.
7. Dùng một connection pool hoặc mô phỏng việc tái sử dụng kết nối. Kiểm tra vì sao temporary table chưa được xóa có thể ảnh hưởng request sau.
8. Viết nhận xét ngắn so sánh khi nào nên để optimizer dùng internal temporary table và khi nào ứng dụng cần tạo bảng tạm người dùng.

## 10. Tiêu chí hoàn thành

Bạn hoàn thành bài khi giải thích được TempTable là engine phục vụ internal temporary table của MySQL, phân biệt được nó với bảng do `CREATE TEMPORARY TABLE` tạo ra, đọc được dấu hiệu bảng tạm trong `EXPLAIN` và status counters, hiểu đường đi từ RAM sang vùng lưu trữ tạm, đồng thời tạo và quản lý được bảng tạm theo phạm vi session. Bạn cũng cần biết cách dọn bảng tạm khi dùng connection pool và tránh kết luận sai rằng `Using temporary` luôn đồng nghĩa với ghi đĩa.
