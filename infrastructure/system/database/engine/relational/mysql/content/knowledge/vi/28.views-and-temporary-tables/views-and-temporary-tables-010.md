# Bảng tạm nội bộ, TempTable/MEMORY và điều kiện tràn ra đĩa

Trong lúc thực thi một câu SQL, MySQL đôi khi cần lưu kết quả trung gian để sắp xếp, nhóm, loại trùng hoặc materialize một derived table/CTE. Những cấu trúc này được gọi là **internal temporary tables** (bảng tạm nội bộ). Chúng do optimizer và server tạo, quản lý rồi thu hồi trong quá trình thực thi; ứng dụng không cần tự tạo hoặc xóa chúng.

MySQL có thể giữ bảng tạm nội bộ trong RAM bằng storage engine `TempTable` hoặc `MEMORY`. Khi kết quả vượt giới hạn phù hợp, MySQL có thể chuyển sang vùng lưu trữ tạm trên đĩa, thường dùng InnoDB. Với `TempTable`, còn có cơ chế memory-mapped files nằm giữa RAM và InnoDB khi ngân sách RAM toàn cục đạt ngưỡng. Vì vậy, thấy một truy vấn tạo bảng tạm không đồng nghĩa ngay lập tức với việc nó đã ghi ra đĩa; cần hiểu engine, giới hạn và số liệu thực tế.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt bảng tạm nội bộ với bảng `TEMPORARY` do ứng dụng tạo.
- Nhận biết các thao tác SQL có thể khiến MySQL materialize kết quả trung gian.
- So sánh `TempTable` và `MEMORY` khi lưu bảng tạm trong RAM.
- Giải thích các ngưỡng `tmp_table_size`, `temptable_max_ram` và `temptable_max_mmap`.
- Mô tả các bước chuyển từ RAM sang memory-mapped files hoặc InnoDB temporary tablespace.
- Theo dõi số lượng bảng tạm, dung lượng TempTable và dấu hiệu tràn ra đĩa.
- Giảm nhu cầu materialize bằng index, lọc sớm và giảm dữ liệu trung gian.

Các ví dụ giả định MySQL 8.0 trở lên. Một số giới hạn và hành vi thay đổi theo phiên bản; đặc biệt `tmp_table_size` bắt đầu áp dụng như giới hạn theo từng bảng tạm nội bộ của engine `TempTable` từ MySQL 8.0.28. `temptable_max_mmap` có từ 8.0.23; `temptable_use_mmap` bị deprecated từ 8.0.26. Hãy kiểm tra biến thực tế trên đúng phiên bản đang vận hành.

## 1. Bảng tạm nội bộ khác bảng TEMPORARY như thế nào?

Hai loại bảng tạm có mục đích và vòng đời khác nhau:

| Đặc điểm | Bảng tạm nội bộ (internal) | Bảng `TEMPORARY` do ứng dụng tạo |
|---|---|---|
| Ai tạo? | MySQL optimizer/server trong lúc thực thi | Ứng dụng hoặc người dùng bằng `CREATE TEMPORARY TABLE` |
| Tên bảng | Nội bộ, không được truy cập trực tiếp bằng SQL thông thường | Có tên do người tạo đặt |
| Mục đích | Lưu kết quả trung gian cho sort, grouping, materialization... | Lưu dữ liệu trung gian do logic ứng dụng điều khiển |
| Engine | Do MySQL chọn theo cấu hình và kế hoạch | Có thể chỉ định engine, ví dụ `InnoDB` hoặc `MEMORY` |
| Vòng đời | Thường chỉ tồn tại trong quá trình thực thi hoặc phạm vi nội bộ của câu lệnh | Tồn tại trong session cho đến khi drop hoặc session kết thúc |
| Theo dõi | Status counters, Performance Schema và execution plan | Metadata session, câu lệnh và công cụ giám sát bảng |

Ví dụ bảng tạm do ứng dụng tạo:

```sql
CREATE TEMPORARY TABLE selected_customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    priority TINYINT NOT NULL
) ENGINE = InnoDB;

INSERT INTO selected_customers (customer_id, priority)
VALUES (101, 1), (205, 2), (309, 3);

SELECT c.customer_id, c.email
FROM customers AS c
JOIN selected_customers AS s
  ON s.customer_id = c.customer_id;

DROP TEMPORARY TABLE selected_customers;
```

Bảng `selected_customers` có thể được truy cập bằng SQL trong chính session đã tạo nó; session khác không nhìn thấy bảng này. Nếu session kết thúc, MySQL tự xóa bảng tạm đó. Đây là đối tượng do ứng dụng chủ động quản lý, khác với bảng tạm nội bộ mà optimizer tự tạo.

Với bảng `TEMPORARY` dùng `MEMORY` do ứng dụng tạo, khi đạt `max_heap_table_size`, thao tác ghi thường báo lỗi vì bảng đã đầy; MySQL không tự chuyển bảng người dùng đó sang InnoDB. Cơ chế tự chuyển sang InnoDB được mô tả ở đây áp dụng cho internal temporary tables.

## 2. Khi nào MySQL tạo bảng tạm nội bộ?

Optimizer có thể tạo bảng tạm nội bộ khi cần giữ một tập kết quả trung gian mà không thể xử lý trực tiếp bằng một lần quét index hoặc pipeline đơn giản. Các tình huống thường gặp gồm:

- `GROUP BY` khi thứ tự index không đáp ứng cách nhóm cần thiết.
- `DISTINCT` để loại bỏ các hàng trùng.
- `ORDER BY` khi không thể lấy thứ tự trực tiếp từ index hoặc phải sắp xếp kết quả trung gian.
- `UNION` (đặc biệt khi cần loại trùng) và một số dạng xử lý nhiều query block.
- Materialization của derived table, view hoặc CTE không thể merge.
- Một số subquery cần materialize kết quả.
- Hàm cửa sổ và các phép xử lý cần lưu hoặc sắp xếp tập hàng.

Không phải cứ xuất hiện `GROUP BY`, `ORDER BY` hay `DISTINCT` là chắc chắn có bảng tạm. Nếu index phù hợp cung cấp thứ tự hoặc nhóm cần thiết, optimizer có thể tránh tạo bảng tạm. Ngược lại, một truy vấn nhìn đơn giản vẫn có thể materialize do cách kết hợp join, biểu thức và query block.

Các ví dụ về đơn hàng trong bài giả định bảng InnoDB sau:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    KEY ix_orders_created_customer (created_at, customer_id)
) ENGINE = InnoDB;
```

Ví dụ cần tổng hợp đơn hàng theo khách hàng:

```sql
SELECT customer_id,
       SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC;
```

MySQL phải tính tổng theo nhóm rồi sắp xếp theo giá trị aggregate `revenue`. Giá trị này chưa tồn tại trong index của bảng nguồn, nên thường cần một bước lưu hoặc xử lý kết quả nhóm trước khi sắp xếp. Kế hoạch cụ thể cần được xác nhận bằng `EXPLAIN`.

## 3. TempTable và MEMORY

MySQL hỗ trợ hai engine có thể dùng để tạo internal temporary table trong RAM: `TempTable` và `MEMORY`. Biến `internal_tmp_mem_storage_engine` điều khiển lựa chọn này. Trong MySQL 8.0 hiện đại, `TempTable` là lựa chọn mặc định.

| Đặc điểm | TempTable | MEMORY |
|---|---|---|
| Vai trò | Engine nội bộ dành cho temporary tables | Engine bộ nhớ có thể dùng cho temporary tables |
| Kiểu dữ liệu | Hỗ trợ kiểu độ dài biến đổi và các kiểu lớn như `BLOB`/`TEXT` trong các phiên bản hiện đại | Có giới hạn kiểu dữ liệu; không hỗ trợ `BLOB`/`TEXT` như TempTable |
| Cách lưu hàng | Biểu diễn linh hoạt, phù hợp dữ liệu độ dài biến đổi | Hàng dùng biểu diễn có độ dài cố định, có thể lãng phí bộ nhớ với cột biến độ dài |
| Giới hạn | Dùng giới hạn theo từng bảng và ngân sách TempTable toàn cục; có thể chuyển sang mmap/InnoDB | Chịu giới hạn kích thước của bảng MEMORY và giới hạn cấu hình liên quan |
| Khi vượt giới hạn | Có thể chuyển sang lưu trữ tạm trên đĩa theo cấu hình/phiên bản | Internal temporary table có thể được chuyển sang InnoDB trên đĩa |

### TempTable

`TempTable` được thiết kế cho internal temporary tables và là lựa chọn mặc định từ MySQL 8.0.16. Engine này xử lý tốt dữ liệu độ dài biến đổi như `VARCHAR` và `VARBINARY`, đồng thời hỗ trợ các kiểu BLOB/TEXT từ MySQL 8.0.13. Nó cấp phát bộ nhớ theo các block và có thể dùng memory-mapped files khi ngân sách RAM toàn cục đạt ngưỡng.

Việc hỗ trợ kiểu dữ liệu rộng hơn giúp MySQL không phải chuyển bảng tạm sang đĩa chỉ vì kết quả có cột `TEXT`/`BLOB`, như các giới hạn của `MEMORY` trước đây. Dù vậy, kích thước kết quả, số lượng session đồng thời và ngưỡng cấu hình vẫn có thể khiến TempTable chuyển sang vùng lưu trữ khác.

### MEMORY

`MEMORY` lưu hàng trong RAM và dùng cấu trúc index như HASH hoặc BTREE tùy khai báo. Engine này có các giới hạn kiểu dữ liệu và biểu diễn hàng khác TempTable. Với internal temporary tables dùng MEMORY, `tmp_table_size` và `max_heap_table_size` có vai trò trong việc giới hạn kích thước; giới hạn hiệu lực là giá trị nhỏ hơn trong hai biến.

Hàng MEMORY dùng vùng lưu cố định theo định nghĩa cột, nên cột chuỗi có chiều dài khai báo lớn có thể làm tiêu tốn bộ nhớ đáng kể dù giá trị thực tế ngắn. Không nên chọn MEMORY chỉ vì tên engine có chữ “memory”; hãy đánh giá kích thước hàng, kiểu dữ liệu và hành vi khi vượt giới hạn.

### Kiểm tra engine nội bộ hiện tại

```sql
SHOW VARIABLES LIKE 'internal_tmp_mem_storage_engine';
SHOW VARIABLES LIKE 'default_storage_engine';
```

`default_storage_engine` điều khiển engine mặc định cho bảng do người dùng tạo; nó không thay thế `internal_tmp_mem_storage_engine` khi kiểm tra engine của internal temporary tables.

## 4. Các ngưỡng quyết định RAM và spill

Không có một biến duy nhất điều khiển toàn bộ bộ nhớ của mọi bảng tạm. Cần phân biệt giới hạn theo từng bảng với ngân sách tài nguyên chung của TempTable.

| Biến | Phạm vi/ý nghĩa | Vai trò khi vượt ngưỡng |
|---|---|---|
| `tmp_table_size` | Giới hạn kích thước của một internal in-memory temporary table; áp dụng cho TempTable từ MySQL 8.0.28 | Khi bảng tạm vượt giới hạn theo phiên bản, MySQL có thể chuyển bảng đó sang InnoDB trên đĩa |
| `temptable_max_ram` | Ngân sách RAM tối đa mà TempTable engine được phép sử dụng trên server | Khi đạt ngưỡng, các cấp phát mới dùng memory-mapped files nếu được cấu hình và còn ngân sách mmap |
| `temptable_max_mmap` | Ngân sách tối đa cho các file được memory-map mà TempTable sử dụng | Khi đạt ngưỡng, các cấp phát mới dùng InnoDB cho internal on-disk temporary tables |
| `max_heap_table_size` | Giới hạn kích thước bảng MEMORY; có liên quan đến internal temp table dùng MEMORY | Bảng MEMORY có thể được chuyển sang InnoDB khi vượt giới hạn hiệu lực |
| `internal_tmp_mem_storage_engine` | Chọn engine nội bộ trong RAM: `TempTable` hoặc `MEMORY` | Ảnh hưởng kiểu lưu trữ và cơ chế giới hạn được áp dụng |

`tmp_table_size` và `temptable_max_ram` không có cùng phạm vi. Một bảng tạm riêng lẻ có thể vượt giới hạn của nó trước khi toàn bộ ngân sách TempTable của server được dùng hết. Ngược lại, nhiều bảng tạm nhỏ từ nhiều session có thể cùng làm ngân sách TempTable toàn cục đạt ngưỡng.

`max_heap_table_size` không áp dụng cho bảng tạm dùng `TempTable`; nó chỉ tham gia giới hạn khi engine nội bộ được chọn là `MEMORY`. Với `TempTable`, ngân sách RAM toàn cục `temptable_max_ram` cũng không bao gồm toàn bộ block bộ nhớ thread-local mà mỗi thread sử dụng, nên không nên xem giá trị này là trần tuyệt đối của mọi byte liên quan đến TempTable.

### Kiểm tra giá trị cấu hình

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'internal_tmp_mem_storage_engine',
    'tmp_table_size',
    'max_heap_table_size',
    'temptable_max_ram',
    'temptable_max_mmap',
    'tmpdir'
);
```

Không giả định giá trị mặc định giống nhau giữa các phiên bản hoặc môi trường. Hãy lưu lại giá trị thực tế, phạm vi GLOBAL/SESSION và trạng thái dynamic trước khi thay đổi.

Trên các phiên bản còn hỗ trợ `temptable_use_mmap`, biến này điều khiển việc dùng mmap khi ngân sách RAM TempTable đạt ngưỡng; biến đã deprecated từ MySQL 8.0.26. `temptable_max_mmap = 0` vô hiệu hóa cấp phát mmap và khiến TempTable dùng InnoDB khi vượt ngân sách RAM. Ưu tiên kiểm tra và cấu hình `temptable_max_mmap` theo tài liệu phiên bản đang chạy thay vì xây automation mới dựa trên biến deprecated.

## 5. Hành trình từ RAM đến đĩa

Với TempTable, có thể hình dung quá trình như sau:

```text
                   Query cần kết quả trung gian
                              |
                              v
                       TempTable trong RAM
                         /           \\
       vượt tmp_table_size           đạt temptable_max_ram toàn cục
                  |                             |
                  v                             v
        InnoDB on-disk temp table       Memory-mapped files (tmpdir)
        (temporary tablespace)                    |
                                     đạt temptable_max_mmap
                                                |
                                                v
                                      InnoDB on-disk temp table
                                      (temporary tablespace)
```

Đây là mô hình khái quát cho MySQL 8.0.28 trở lên: vượt `tmp_table_size` có thể khiến một bảng TempTable riêng lẻ được chuyển sang InnoDB; đạt ngân sách RAM toàn cục `temptable_max_ram` khiến các cấp phát mới dùng mmap nếu còn ngân sách `temptable_max_mmap`; khi ngân sách mmap hết, các cấp phát mới dùng InnoDB cho internal on-disk temporary tables. TempTable không di chuyển dữ liệu đã ghi từ RAM sang file mmap; một bảng có thể có phần dữ liệu nằm trong RAM và phần dữ liệu mới nằm trong file tạm. Trên phiên bản cũ hơn, giới hạn theo từng bảng khác; không giả định `tmp_table_size` áp dụng theo cùng cách. Khi mmap bị vô hiệu hóa hoặc giới hạn mmap bằng 0, TempTable có thể dùng InnoDB ngay khi không còn ngân sách RAM.

### Memory-mapped files không giống InnoDB temp tablespace

Memory-mapped file là file được ánh xạ vào không gian địa chỉ của process; hệ điều hành quản lý việc nạp/ghi các trang file. TempTable dùng cơ chế này như một tầng lưu trữ tạm khi RAM đã đạt ngưỡng. Các file mmap thường nằm trong thư mục `tmpdir`.

MySQL tạo file mmap trong `tmpdir`, mở file rồi xóa tên file ngay; vì vậy file có thể không hiện trong danh sách thư mục dù dung lượng vẫn đang được hệ điều hành giữ cho đến khi TempTable đóng file hoặc tiến trình `mysqld` dừng. Đừng chỉ dựa vào việc liệt kê tên file để kết luận `tmpdir` không bị TempTable sử dụng.

Internal temporary table dùng InnoDB trên đĩa được lưu trong InnoDB temporary tablespace do engine quản lý. Tùy phiên bản và cấu hình, có thể có global temporary tablespace và session temporary tablespaces. Không nên giả định mọi internal temp table trên đĩa đều là file trong `tmpdir`.

Từ MySQL 8.0.16, InnoDB là engine được dùng cho internal temporary tables trên đĩa; trước đó, phiên bản cũ còn có cấu hình engine tạm trên đĩa khác. Trong MySQL 8.0, InnoDB on-disk internal temporary tables được tạo trong session temporary tablespaces nằm trong data directory theo mặc định.

`tmpdir` vẫn quan trọng cho memory-mapped files và các hoạt động tạm khác. Cần bảo đảm filesystem có dung lượng, quyền truy cập và hiệu năng phù hợp. Với InnoDB temporary tablespace, theo dõi dung lượng và quy tắc quản lý file riêng của InnoDB.

## 6. Điều gì xảy ra khi bảng tạm tràn ra đĩa?

Khi internal temporary table không còn được giữ hoàn toàn trong RAM, MySQL có thể phải ghi và đọc dữ liệu trung gian từ vùng lưu trữ tạm. Điều này tăng I/O và thường làm truy vấn chậm hơn, đặc biệt khi bảng tạm lớn hoặc bị đọc/ghi nhiều lần.

Chi phí có thể gồm:

- Ghi các hàng trung gian xuống file hoặc InnoDB temporary tablespace.
- Đọc lại dữ liệu để sort, group, join hoặc materialize query block.
- Tạo index trên bảng tạm nếu optimizer cần.
- Tranh chấp I/O với workload chính trên cùng thiết bị.
- Tăng dung lượng sử dụng trong `tmpdir` hoặc InnoDB temporary tablespace.

Spill ra đĩa không tự động đồng nghĩa truy vấn có vấn đề. Một phép sort lớn hoặc aggregate hợp lý đôi khi cần lưu trung gian và vẫn có hiệu năng chấp nhận được. Cần đo thời gian, số hàng, dung lượng và mức độ lặp lại trước khi tối ưu.

Ngược lại, một truy vấn tạo nhiều bảng tạm nhỏ nhưng chạy hàng nghìn lần mỗi phút cũng có thể tạo tải đáng kể. Đánh giá cả tần suất lẫn kích thước.

## 7. Nhận biết bảng tạm trong execution plan

Chạy `EXPLAIN` để xem optimizer dự kiến thực hiện truy vấn:

```sql
EXPLAIN
SELECT customer_id,
       SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC;
```

Trong định dạng tabular, cột `Extra` có thể hiển thị `Using temporary`. Đây là dấu hiệu MySQL dự kiến dùng bảng tạm nội bộ cho một phần kế hoạch. Tuy nhiên:

- `Using temporary` không cho biết bảng tạm đang ở RAM, mmap hay InnoDB trên đĩa.
- Nó không cho biết kích thước bảng tạm hoặc thời gian I/O.
- Không phải mọi internal temporary table đều được thể hiện bằng cùng một dòng `Extra` trong mọi định dạng plan.
- `Using filesort` là cơ chế sắp xếp riêng; không đồng nghĩa chắc chắn với việc bảng tạm đã tràn ra đĩa.

Với `EXPLAIN FORMAT=TREE`, có thể thấy node materialize hoặc aggregate/sort cụ thể hơn tùy truy vấn. Từ MySQL 8.0.18, `EXPLAIN ANALYZE` thực thi truy vấn và cung cấp số hàng thực tế, số vòng lặp và thời gian của các node:

```sql
EXPLAIN ANALYZE
SELECT customer_id,
       SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC;
```

`EXPLAIN ANALYZE` thực sự chạy câu `SELECT`; hãy dùng trên môi trường phù hợp và cân nhắc tải truy vấn trước khi chạy production.

## 8. Theo dõi số lượng bảng tạm

Các status counter hữu ích:

```sql
SHOW GLOBAL STATUS LIKE 'Created_tmp%';
```

| Counter | Ý nghĩa |
|---|---|
| `Created_tmp_tables` | Số internal temporary table được tạo |
| `Created_tmp_disk_tables` | Số internal temporary table được tạo trên đĩa theo cách được counter ghi nhận |
| `Created_tmp_files` | Số file tạm do mysqld tạo |

Các counter là số tích lũy kể từ khi server khởi động hoặc reset status. Hãy lấy hai mẫu theo thời gian để tính delta và so sánh với số request hoặc số câu SQL trong cùng khoảng.

**Giới hạn cần nhớ:** `Created_tmp_disk_tables` không đếm các internal temporary table trên memory-mapped files. Vì vậy, counter này có thể thấp hơn số bảng tạm đã dùng vùng lưu trữ ngoài RAM. Không thể dùng riêng tỷ lệ `Created_tmp_disk_tables / Created_tmp_tables` để kết luận chính xác tỷ lệ spill ra đĩa của TempTable.

### Theo dõi bộ nhớ TempTable trong Performance Schema

Nếu các memory instrument được bật, có thể xem mức sử dụng hiện tại và mức cao nhất:

```sql
SELECT EVENT_NAME,
       CURRENT_NUMBER_OF_BYTES_USED,
       HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
WHERE EVENT_NAME LIKE 'memory/temptable/%';
```

Các instrument thường gặp gồm `memory/temptable/physical_ram` và `memory/temptable/physical_disk`. Tên instrument và khả năng thu thập phụ thuộc phiên bản, cấu hình Performance Schema và việc instrument có được bật hay không. Nếu truy vấn không trả dữ liệu, kiểm tra `performance_schema.setup_instruments` và quyền truy cập trước khi kết luận engine không dùng TempTable.

### Theo dõi dung lượng vùng lưu trữ

- Kiểm tra filesystem chứa `tmpdir` để phát hiện mmap files chiếm dung lượng.
- Theo dõi InnoDB temporary tablespace và dung lượng file tạm của InnoDB.
- Theo dõi I/O latency, disk utilization và thời gian truy vấn trong cùng khoảng có spill.
- Đối chiếu số liệu server với query digest để tìm câu SQL tạo nhiều bảng tạm nhất.

## 9. Cấu hình và thử nghiệm có kiểm soát

Kiểm tra trước khi thay đổi:

```sql
SHOW VARIABLES LIKE 'internal_tmp_mem_storage_engine';
SHOW VARIABLES LIKE 'tmp_table_size';
SHOW VARIABLES LIKE 'max_heap_table_size';
SHOW VARIABLES LIKE 'temptable_max_ram';
SHOW VARIABLES LIKE 'temptable_max_mmap';
SHOW VARIABLES LIKE 'tmpdir';
```

Có thể thử engine nội bộ trong session thử nghiệm:

```sql
SET SESSION internal_tmp_mem_storage_engine = 'TempTable';
```

Hoặc so sánh với `MEMORY` nếu phiên bản và quyền cho phép:

```sql
SET SESSION internal_tmp_mem_storage_engine = 'MEMORY';
```

Không dùng kết quả từ một session nhỏ để suy ra hành vi của toàn server. `temptable_max_ram` và `temptable_max_mmap` là ngân sách cấp server; thay đổi chúng ảnh hưởng các session đồng thời. Trước khi chỉnh global value, phải tính tổng RAM dành cho buffer pool, connection, sort/join buffers, TempTable và các tiến trình khác.

Từ MySQL 8.0.27, thay đổi `internal_tmp_mem_storage_engine` ở phạm vi session cần quyền `SESSION_VARIABLES_ADMIN` hoặc `SYSTEM_VARIABLES_ADMIN`. Nếu câu lệnh `SET SESSION` bị từ chối, kiểm tra quyền và chính sách quản trị trước khi thử nghiệm; không nâng quyền của tài khoản ứng dụng chỉ để chạy benchmark.

`tmp_table_size` và `max_heap_table_size` có thể có phạm vi session/global tùy biến; kiểm tra `SHOW VARIABLES` và tài liệu đúng phiên bản. Với MySQL 8.0.28 trở lên, `tmp_table_size` là giới hạn theo từng bảng TempTable nội bộ. Trên phiên bản cũ hơn, không giả định biến này giới hạn riêng từng TempTable theo cùng cách.

Không tăng mọi giới hạn lên mức rất lớn chỉ để giảm `Created_tmp_disk_tables`. Nhiều session đồng thời có thể cùng tạo bảng tạm lớn, khiến RAM bị tiêu thụ ngoài dự kiến. Hãy thử nghiệm với concurrency gần production và theo dõi cả RAM lẫn dung lượng đĩa.

## 10. Giảm nhu cầu tạo hoặc materialize bảng tạm

Tối ưu tốt thường bắt đầu từ hình dạng truy vấn và index, không phải chỉ tăng ngưỡng bộ nhớ.

### Lọc sớm và chọn ít cột

Chỉ lấy cột cần thiết và áp dụng điều kiện càng sớm càng tốt:

```sql
-- Kết quả trung gian lớn không cần thiết:
SELECT *
FROM orders
WHERE created_at >= '2026-01-01';

-- Chọn đúng cột cho báo cáo:
SELECT customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01';
```

Ít cột hơn giúp giảm kích thước hàng trung gian, nhất là khi có cột chuỗi lớn hoặc JSON/TEXT.

### Thiết kế index cho filter, group và order

Nếu truy vấn thường lọc theo `status` và nhóm theo `customer_id`, index ghép phù hợp có thể giảm số hàng phải đọc:

```sql
CREATE INDEX ix_orders_status_customer
ON orders (status, customer_id);
```

Index không phải lúc nào cũng loại bỏ được bảng tạm, đặc biệt khi sắp xếp theo aggregate như `SUM(amount)`. Hãy xác nhận bằng `EXPLAIN` và số liệu thực tế.

### Tránh materialize dữ liệu lớn không cần thiết

Nếu derived table chỉ là phép chiếu/lọc đơn giản, để optimizer merge có thể tránh tạo bảng trung gian. Với CTE hoặc derived table được dùng nhiều lần, materialization đôi khi lại tiết kiệm hơn việc tính lại. Cần cân bằng số lần sử dụng, kích thước kết quả và index nội bộ.

### Giảm độ rộng của GROUP BY/DISTINCT

Chỉ group hoặc distinct trên những cột cần thiết. `SELECT DISTINCT` trên nhiều cột lớn làm tăng kích thước khóa trung gian và chi phí loại trùng. Nếu nghiệp vụ chỉ cần một định danh, không đưa thêm cột không cần thiết vào danh sách distinct.

### Phân trang và xử lý theo lô

Với báo cáo rất lớn, cân nhắc xử lý theo khoảng khóa hoặc khoảng thời gian thay vì tạo một kết quả trung gian khổng lồ trong một statement. Chia batch cần giữ đúng semantics và yêu cầu snapshot của nghiệp vụ.

## 11. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| `Using temporary` nghĩa là đã ghi ra đĩa | Nó chỉ báo có bảng tạm; bảng có thể nằm trong RAM |
| `Created_tmp_disk_tables = 0` nghĩa là không spill | Counter không đếm đầy đủ các bảng tạm dùng memory-mapped files |
| Tăng `tmp_table_size` luôn giải quyết vấn đề | Ngân sách TempTable toàn cục, mmap, InnoDB temp tablespace và concurrency vẫn có thể là giới hạn |
| TempTable và MEMORY giống nhau | Khác về kiểu dữ liệu, biểu diễn hàng và cơ chế quản lý dung lượng |
| Mọi `ORDER BY` đều tạo bảng tạm | Index có thể cung cấp thứ tự; filesort và temporary table là các khái niệm khác nhau |
| Bảng tạm nội bộ giống `CREATE TEMPORARY TABLE` | Một loại do server tạo, loại kia do ứng dụng tạo và quản lý theo session |
| Spill ra đĩa luôn là lỗi | Spill có thể là lựa chọn hợp lý cho truy vấn lớn; cần đánh giá latency và tài nguyên |

## 12. Quy trình điều tra truy vấn tạo nhiều bảng tạm

1. Xác định query digest và endpoint tạo truy vấn; đo số lần chạy, p95/p99 và tổng thời gian.
2. Chạy `EXPLAIN` để tìm `Using temporary`, materialization, grouping hoặc sorting.
3. Dùng `EXPLAIN ANALYZE` trong môi trường phù hợp để xem số hàng thực tế và thời gian từng node.
4. Lấy delta `Created_tmp_tables`, `Created_tmp_disk_tables`, `Created_tmp_files` trong cùng khoảng workload.
5. Đọc Performance Schema memory instrument của TempTable nếu có; kiểm tra `tmpdir` và InnoDB temporary tablespace.
6. Xem giá trị `internal_tmp_mem_storage_engine`, `tmp_table_size`, `temptable_max_ram`, `temptable_max_mmap` và `max_heap_table_size`.
7. Kiểm tra query có thể lọc sớm, giảm cột, tận dụng index hoặc tránh materialize không cần thiết không.
8. Thử thay đổi từng yếu tố trên môi trường thử nghiệm; đo lại latency, RAM, I/O và concurrency.
9. Chỉ thay đổi global configuration khi đã ước lượng ngân sách tài nguyên cho toàn server và có kế hoạch rollback.

## 13. Bài thực hành

Giả sử có bảng `orders(order_id, customer_id, status, total_amount, created_at)` dùng InnoDB.

1. Chạy truy vấn `GROUP BY customer_id` và `ORDER BY SUM(total_amount) DESC`. Dùng `EXPLAIN` để xem optimizer có cần bảng tạm hoặc sort không.
2. So sánh truy vấn `SELECT *` với truy vấn chỉ lấy `customer_id` và `total_amount`. Giải thích ảnh hưởng của độ rộng hàng trung gian.
3. Kiểm tra `internal_tmp_mem_storage_engine`, `tmp_table_size`, `temptable_max_ram` và `temptable_max_mmap` trên server thử nghiệm.
4. Chạy workload tạo kết quả nhóm lớn, lấy delta các counter `Created_tmp%` trước và sau. Giải thích vì sao `Created_tmp_disk_tables` không phản ánh mọi memory-mapped temp table.
5. Nếu Performance Schema có instrument TempTable, đọc `CURRENT_NUMBER_OF_BYTES_USED` và `HIGH_NUMBER_OF_BYTES_USED`.
6. Thử engine `MEMORY` và `TempTable` trong session riêng; so sánh hành vi với cột chuỗi dài hoặc kiểu `TEXT` trên đúng phiên bản MySQL đang dùng.
7. Tạo index phù hợp cho điều kiện lọc/nhóm, chạy lại `EXPLAIN` và so sánh số hàng đọc, thời gian và tài nguyên.
8. Viết runbook ngắn để xử lý khi `tmpdir` gần đầy hoặc InnoDB temporary tablespace tăng bất thường.

## Ghi nhớ

- Internal temporary table là kết quả trung gian do MySQL tạo; khác với bảng `TEMPORARY` do ứng dụng tạo.
- `TempTable` là engine nội bộ mặc định trong MySQL 8.0 hiện đại; `MEMORY` có giới hạn kiểu dữ liệu và cách lưu hàng khác.
- Phân biệt giới hạn từng bảng `tmp_table_size` với ngân sách TempTable toàn server `temptable_max_ram` và `temptable_max_mmap`.
- TempTable có thể chuyển từ RAM sang memory-mapped files rồi InnoDB temporary tablespace; đường đi phụ thuộc phiên bản và cấu hình.
- `Using temporary` không chứng minh đã spill ra đĩa; `Created_tmp_disk_tables` cũng không đếm các bảng tạm dùng mmap.
- Theo dõi Performance Schema, status counters, filesystem và InnoDB temporary tablespace cùng lúc.
- Giảm dữ liệu trung gian bằng lọc sớm, chọn ít cột, index phù hợp và kiểm soát materialization trước khi tăng giới hạn bộ nhớ.
