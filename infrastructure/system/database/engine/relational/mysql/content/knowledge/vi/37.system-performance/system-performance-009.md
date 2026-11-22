# Temporary table nội bộ, giới hạn RAM và dữ liệu tràn đĩa

Trong quá trình thực thi một câu SQL, MySQL có thể cần lưu kết quả trung gian trước khi trả dữ liệu cho client. Ví dụ, server phải gom nhóm hàng, loại bản ghi trùng, sắp xếp một tập kết quả hoặc vật chất hóa một derived table. Khi đó optimizer có thể tạo **internal temporary table** (bảng tạm nội bộ). Bảng này là cấu trúc làm việc của một statement, không phải bảng mà ứng dụng chủ động tạo bằng CREATE TEMPORARY TABLE.

Internal temporary table có thể được giữ trong RAM hoặc chuyển sang vùng lưu trữ tạm trên đĩa. Chuyển sang đĩa là cơ chế bảo vệ bộ nhớ và cho phép xử lý tập trung gian lớn hơn ngân sách RAM; tuy nhiên, nó làm tăng I/O và có thể kéo dài thời gian truy vấn. Muốn tối ưu đúng, cần xác định statement nào tạo bảng tạm, engine nào đang lưu bảng, ngưỡng RAM nào tác động, đường tràn đĩa nằm ở đâu và chi phí thực tế ra sao.

Bài học đặt trong phạm vi DATABASE_MYSQL: làm chủ hiệu năng truy vấn và vận hành MySQL, đọc kế hoạch thực thi, quản lý tài nguyên và xử lý tình huống cơ sở dữ liệu chịu tải cao.

## 1. Mục tiêu và phạm vi

Sau bài học, bạn có thể:

- Phân biệt bảng tạm nội bộ với bảng tạm do ứng dụng tạo.
- Nhận biết các thao tác SQL thường cần materialization hoặc bảng tạm.
- Giải thích vai trò của TempTable, MEMORY, InnoDB và các giới hạn liên quan.
- Phân biệt giới hạn RAM toàn cục với giới hạn kích thước của từng bảng tạm.
- Mô tả đường chuyển từ RAM sang memory-mapped file và sau đó sang InnoDB on-disk internal temporary table.
- Theo dõi bảng tạm qua EXPLAIN, Performance Schema, sys schema và status counters.
- Tìm vị trí file tạm, kiểm tra dung lượng và I/O của filesystem.
- Ước lượng ảnh hưởng của concurrency khi nhiều truy vấn cùng tạo bảng tạm.
- Chọn thay đổi SQL, index hoặc cấu hình dựa trên số liệu đo được.

Bài tập trung vào internal temporary tables do optimizer và executor tạo trong lúc chạy statement. Bảng tạm tường minh như CREATE TEMPORARY TABLE được nhắc đến để làm rõ ranh giới và tránh áp dụng nhầm cấu hình.

## 2. Bảng tạm nội bộ hình thành khi nào?

Optimizer có thể tạo một cấu trúc trung gian khi kết quả cần được gom, sắp xếp, khử trùng lặp hoặc lưu lại để nhiều bước thực thi cùng sử dụng. Một số trường hợp thường gặp:

- GROUP BY cần gom nhóm mà thứ tự truy cập theo index không đáp ứng được.
- DISTINCT phải loại bỏ các hàng trùng nhau.
- ORDER BY cần sắp xếp tập kết quả mà index không thể cung cấp thứ tự phù hợp.
- UNION cần kết hợp và khử trùng lặp kết quả.
- Derived table hoặc common table expression (CTE) được materialize thay vì merge vào truy vấn ngoài.
- Một số subquery được materialize để optimizer thực hiện phép nối hoặc phép kiểm tra membership.
- Window function cần giữ hoặc sắp xếp dữ liệu theo partition/order của cửa sổ.
- Một số phép toán kết hợp GROUP BY, DISTINCT, ORDER BY hoặc biểu thức phức tạp tạo ra nhiều giai đoạn xử lý trung gian.

Không phải mọi câu SELECT có các từ khóa trên đều chắc chắn tạo internal temporary table. Optimizer có thể dùng index, merge derived table, thực hiện streaming hoặc chọn chiến lược khác. Ngược lại, một truy vấn không có từ khóa TEMPORARY vẫn có thể cần bảng tạm nội bộ.

### 2.1. Ví dụ GROUP BY và ORDER BY

Giả sử bảng orders có nhiều đơn hàng theo customer_id:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

MySQL phải tính tổng theo customer_id rồi sắp xếp các nhóm theo biểu thức revenue. Index có thể giúp lọc theo created_at hoặc hỗ trợ thứ tự theo customer_id, nhưng không thể trực tiếp cung cấp thứ tự theo SUM(total_amount) trước khi tổng hợp. Executor có thể cần cấu trúc trung gian cho nhóm và bước sắp xếp.

Nếu ứng dụng chỉ cần tổng doanh thu theo customer_id mà không cần thứ tự theo tổng, bỏ ORDER BY có thể giảm một bước sort. Nếu cần top 20 theo doanh thu, vẫn phải xếp hạng các nhóm; cần đo chi phí và xem có thể giảm số hàng đầu vào trước khi tổng hợp hay không.

### 2.2. Ví dụ DISTINCT

~~~sql
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID';
~~~

Nếu index phù hợp cho điều kiện và cột customer_id, optimizer có thể đọc các giá trị theo thứ tự và loại trùng hiệu quả. Nếu không có đường truy cập phù hợp, server có thể phải tạo cấu trúc trung gian để khử trùng lặp.

### 2.3. Ví dụ UNION

~~~sql
SELECT customer_id FROM online_orders
UNION
SELECT customer_id FROM store_orders;
~~~

UNION mặc định loại bỏ các hàng trùng nhau, nên cần bước xử lý tập kết quả. UNION ALL giữ cả hàng trùng và có thể cho phép xử lý đơn giản hơn hoặc streaming trong nhiều trường hợp:

~~~sql
SELECT customer_id FROM online_orders
UNION ALL
SELECT customer_id FROM store_orders;
~~~

Chỉ đổi UNION thành UNION ALL khi logic nghiệp vụ cho phép trùng lặp. Không thay đổi ngữ nghĩa để tránh một bảng tạm.

### 2.4. Derived table và CTE

~~~sql
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, revenue
FROM customer_totals
WHERE revenue > 1000000;
~~~

Optimizer có thể merge một derived table/CTE vào truy vấn ngoài hoặc materialize nó. Với materialization, kết quả trung gian được lưu để bước sau đọc. Materialization không mặc nhiên là lỗi: nó có thể tránh tính toán lặp lại hoặc tạo một tập dữ liệu nhỏ hữu ích. Cần xem kế hoạch thực thi để biết lựa chọn nào đã xảy ra.

## 3. Phân biệt internal temporary table và CREATE TEMPORARY TABLE

Hai khái niệm này khác nhau về mục đích, vòng đời và cơ chế quản lý.

| Tiêu chí | Internal temporary table | CREATE TEMPORARY TABLE |
|---|---|---|
| Ai tạo | Optimizer/executor của MySQL | Ứng dụng hoặc người dùng |
| Mục đích | Lưu kết quả trung gian của statement | Lưu dữ liệu làm việc do ứng dụng chủ động quản lý |
| Tên bảng | Nội bộ, không được truy cập trực tiếp bằng tên SQL | Có tên do client đặt |
| Vòng đời | Thường gắn với statement hoặc quá trình materialization trong statement | Tồn tại trong session cho đến khi DROP hoặc session kết thúc |
| Engine | Do cấu hình và lựa chọn nội bộ của MySQL quyết định | Có thể chỉ định engine trong DDL |
| Theo dõi | EXPLAIN, Performance Schema, status counters | DDL, metadata và công cụ quan sát bảng/engine |

Ví dụ bảng tạm tường minh:

~~~sql
CREATE TEMPORARY TABLE session_customer_totals (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    revenue DECIMAL(18, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO session_customer_totals (customer_id, revenue)
SELECT customer_id, SUM(total_amount)
FROM orders
GROUP BY customer_id;

SELECT customer_id, revenue
FROM session_customer_totals
ORDER BY revenue DESC;

DROP TEMPORARY TABLE session_customer_totals;
~~~

Bảng này có tên và vòng đời do session quản lý. Các giới hạn dành cho internal TempTable không tự động biến bảng tạm tường minh thành một internal temporary table. Nếu chỉ định ENGINE=MEMORY, giới hạn max_heap_table_size có liên quan đến bảng MEMORY; nếu chỉ định InnoDB, dữ liệu được quản lý theo cơ chế InnoDB.

Một truy vấn có thể vừa dùng bảng tạm tường minh vừa phát sinh internal temporary table cho ORDER BY, GROUP BY hoặc một thao tác khác. Khi điều tra, cần phân biệt nguồn phát sinh của từng cấu trúc.

## 4. Các engine lưu internal temporary table

### 4.1. TempTable

Trong MySQL 8.0, TempTable là engine được dùng mặc định cho internal in-memory temporary tables từ MySQL 8.0.16. Engine này được thiết kế cho kết quả trung gian và hỗ trợ các kiểu dữ liệu có độ dài thay đổi. Nó có thể lưu BLOB/TEXT trong các trường hợp mà MEMORY không hỗ trợ.

TempTable quản lý vùng RAM dùng chung và có thể dùng memory-mapped files khi cấu hình cho phép. Khi các giới hạn tương ứng bị chạm tới, MySQL chuyển sang cơ chế lưu trữ tạm trên đĩa bằng InnoDB. Cách chuyển đổi cụ thể phụ thuộc phiên bản và các giới hạn đang có hiệu lực.

Các biến cần nhận diện:

- internal_tmp_mem_storage_engine: chọn engine cho internal in-memory temporary tables, thường là TempTable hoặc MEMORY.
- temptable_max_ram: giới hạn RAM dành cho TempTable ở cấp server.
- temptable_max_mmap: giới hạn dung lượng memory-mapped files mà TempTable được phép sử dụng, trên các phiên bản hỗ trợ biến này.
- tmp_table_size: giới hạn kích thước một internal in-memory temporary table trong các phiên bản áp dụng biến này cho TempTable.
- tmpdir: vị trí filesystem được dùng cho các file tạm, bao gồm vùng memory-mapped file của TempTable.

Không giả định giá trị mặc định giống nhau giữa mọi phiên bản MySQL. Trước khi điều chỉnh, hãy đọc giá trị runtime và tài liệu đúng phiên bản đang chạy.

### 4.2. MEMORY

MEMORY lưu dữ liệu của bảng trong RAM. Với internal temporary tables, engine này có thể được chọn qua internal_tmp_mem_storage_engine. MEMORY có các giới hạn kiểu dữ liệu và biểu diễn hàng khác TempTable; ví dụ BLOB/TEXT không được hỗ trợ như trong TempTable.

Khi cấu hình internal temporary table dùng MEMORY, giới hạn kích thước thường chịu ảnh hưởng bởi tmp_table_size và max_heap_table_size; giới hạn hiệu lực là mức thấp hơn trong hai giá trị. Khi vượt giới hạn hoặc gặp kiểu dữ liệu không được hỗ trợ, MySQL có thể chuyển cấu trúc nội bộ sang on-disk internal temporary table.

Không nhầm MEMORY với TempTable. Tăng max_heap_table_size có thể có ý nghĩa cho MEMORY, nhưng không phải cách duy nhất để mở rộng ngân sách RAM của TempTable.

### 4.3. InnoDB cho internal temporary table trên đĩa

Khi bảng tạm nội bộ không thể tiếp tục được giữ trong vùng in-memory/mmap theo cấu hình, MySQL có thể dùng InnoDB cho on-disk internal temporary table. InnoDB cung cấp cơ chế lưu trữ tạm, quản lý trang và I/O trên đĩa.

Một internal temporary table trên đĩa vẫn là cấu trúc nội bộ. Nó không phải bảng nghiệp vụ lâu dài và không nên được truy vấn bằng cách đoán tên file hoặc tên bảng vật lý.

Tài liệu MySQL cũ có thể đề cập biến internal_tmp_disk_storage_engine hoặc engine khác. Biến internal_tmp_disk_storage_engine đã bị loại bỏ trong MySQL 8.0.16; đừng áp dụng hướng dẫn cũ cho phiên bản mới mà chưa xác minh.

## 5. Đường đi từ RAM tới đĩa

Với cấu hình TempTable, cần phân biệt ba tầng:

1. **RAM của TempTable:** vùng bộ nhớ mà engine dùng để lưu các internal temporary tables.
2. **Memory-mapped files:** vùng file được ánh xạ vào không gian địa chỉ tiến trình, có thể dùng làm tầng mở rộng khi RAM TempTable đạt giới hạn và mmap được hỗ trợ/bật.
3. **InnoDB on-disk internal temporary tables:** cơ chế lưu trữ tạm của InnoDB khi các giới hạn trước đó không còn cho phép TempTable tiếp tục giữ dữ liệu ở RAM hoặc mmap.

Sơ đồ khái quát:

~~~text
SQL statement cần kết quả trung gian
                |
                v
      Internal temporary table
                |
                v
       TempTable hoặc MEMORY
                |
        +-------+--------+
        |                |
        v                v
   Còn trong RAM     Chạm giới hạn RAM
        |                |
        |                v
        |        TempTable mmap khả dụng?
        |                |
        |          +-----+-----+
        |          |           |
        |          v           v
        |        Có            Không
        |          |           |
        |          v           |
        |    Memory-mapped     |
        |       files          |
        |          |           |
        |          v           v
        |       Chạm giới hạn mmap
        |                |
        +----------------+
                         |
                         v
             InnoDB on-disk temporary
                         |
                         v
                  Statement kết thúc
~~~

Sơ đồ mô tả đường đi phổ biến của TempTable; lựa chọn thực tế phụ thuộc phiên bản, engine và cấu hình. MEMORY có quy tắc giới hạn riêng. Một số phiên bản mới đã thay đổi hoặc loại bỏ biến điều khiển mmap cũ, vì vậy cần đọc phần tương thích phiên bản trước khi áp dụng.

### 5.1. RAM và mmap không giống nhau

Memory-mapped file vẫn là file trên filesystem, dù nội dung được ánh xạ vào không gian địa chỉ và hệ điều hành có thể quản lý page cache. Nó không tương đương với một bảng InnoDB thông thường, và cũng không nên coi dung lượng mmap là RAM miễn phí.

Nếu mmap tăng, filesystem chứa tmpdir có thể đầy hoặc chịu áp lực I/O. Hệ điều hành có thể phải quản lý nhiều trang file ánh xạ; điều này ảnh hưởng đến page cache và bộ nhớ khả dụng cho các workload khác.

### 5.2. Khi nào chuyển sang InnoDB?

Khi giới hạn RAM TempTable đạt tới và vùng mmap không khả dụng hoặc đã chạm giới hạn, MySQL có thể chuyển sang on-disk internal temporary tables của InnoDB. Với cấu hình MEMORY, vượt giới hạn bảng hoặc kiểu dữ liệu không hỗ trợ cũng có thể dẫn đến chuyển đổi.

Không phải mọi lần spill đều là sự cố. Truy vấn phân tích lớn có thể cần materialization và lượng dữ liệu trung gian đáng kể. Câu hỏi vận hành là spill có xảy ra thường xuyên, có tạo độ trễ đáng kể, có làm đầy filesystem hoặc làm tranh chấp I/O với workload chính hay không.

## 6. Các giới hạn RAM quan trọng

### 6.1. temptable_max_ram: ngân sách dùng chung

temptable_max_ram giới hạn lượng RAM TempTable có thể sử dụng ở cấp server. Đây là ngân sách toàn cục được chia sẻ bởi các statement đồng thời, không phải quota độc lập mà mỗi connection đều được cấp trọn vẹn.

Nếu một truy vấn đơn lẻ tạo bảng trung gian lớn, hoặc nhiều truy vấn cùng tạo bảng tạm, tổng nhu cầu có thể chạm ngân sách. Khi đó TempTable phải dùng tầng lưu trữ tiếp theo theo cấu hình.

Ví dụ, hai mươi truy vấn báo cáo chạy đồng thời đều cần materialize dữ liệu. Dù từng truy vấn không quá lớn, tổng RAM TempTable có thể đạt ngưỡng nhanh hơn dự kiến. Do đó, không đánh giá biến này chỉ bằng một truy vấn chạy đơn lẻ trên máy thử nghiệm.

### 6.2. tmp_table_size: giới hạn cho từng bảng tạm

tmp_table_size là giới hạn kích thước cho internal in-memory temporary table trong các phiên bản có áp dụng biến này cho TempTable. Từ MySQL 8.0.28, biến này được áp dụng như giới hạn cho từng bảng TempTable nội bộ; khi bảng vượt giới hạn, MySQL có thể chuyển bảng đó sang on-disk internal temporary table.

Ở các bản MySQL cũ hơn, quan hệ giữa tmp_table_size và TempTable khác. Không dùng kết quả quan sát trên 8.0.28+ để suy ra hành vi của 8.0.27 hoặc các phiên bản trước.

Giới hạn từng bảng và ngân sách toàn cục giải quyết hai vấn đề khác nhau:

- tmp_table_size hạn chế một internal in-memory table.
- temptable_max_ram hạn chế lượng RAM TempTable dùng chung trên server.

Tăng một biến không đồng nghĩa tăng biến còn lại. Cần kiểm tra cả hai và xem phiên bản có áp dụng chúng như thế nào.

### 6.3. max_heap_table_size

max_heap_table_size liên quan trực tiếp đến bảng MEMORY. Khi internal_tmp_mem_storage_engine được đặt là MEMORY, giới hạn kích thước internal in-memory temporary table thường là giá trị nhỏ hơn giữa tmp_table_size và max_heap_table_size.

Biến này cũng ảnh hưởng tới bảng MEMORY do người dùng tạo. Tuy nhiên, nó không phải biến thay thế cho temptable_max_ram khi engine nội bộ là TempTable.

### 6.4. internal_tmp_mem_storage_engine

Biến này chọn engine dùng cho internal in-memory temporary tables. Trên MySQL 8.0, các giá trị cần quan tâm là TempTable và MEMORY. TempTable là lựa chọn mặc định từ MySQL 8.0.16.

Đổi sang MEMORY có thể thay đổi mức tiêu thụ RAM, cách biểu diễn hàng và khả năng hỗ trợ kiểu dữ liệu. Một truy vấn có BLOB/TEXT hoặc cấu trúc dữ liệu không phù hợp có thể buộc MySQL sử dụng on-disk table. Đừng chuyển engine chỉ vì muốn tránh mmap hoặc vì một status counter tăng.

### 6.5. temptable_max_mmap và temptable_use_mmap

temptable_max_mmap đặt giới hạn dung lượng memory-mapped files mà TempTable được phép dùng trên các phiên bản hỗ trợ biến này. Khi giới hạn đạt tới, các lần cấp phát tiếp theo có thể chuyển sang on-disk internal temporary tables của InnoDB.

temptable_use_mmap từng điều khiển việc TempTable có dùng memory-mapped files hay không. Biến này đã bị deprecated từ MySQL 8.0.26; khả năng hiện diện và cách điều khiển phụ thuộc phiên bản. Với MySQL 8.4 trở lên, hãy kiểm tra danh sách system variables của đúng bản phát hành trước khi sử dụng biến cũ này.

Không cấu hình temptable_max_mmap lớn chỉ để giảm Created_tmp_disk_tables. Mmap vẫn tiêu thụ dung lượng filesystem và có thể tăng I/O. Mục tiêu là cân bằng RAM, filesystem và chi phí truy vấn.

## 7. Đọc cấu hình runtime trước khi thay đổi

Bắt đầu bằng việc xem phiên bản và các biến hiện có:

~~~sql
SELECT VERSION() AS mysql_version;

SHOW GLOBAL VARIABLES LIKE 'internal_tmp_mem_storage_engine';
SHOW GLOBAL VARIABLES LIKE 'tmp_table_size';
SHOW GLOBAL VARIABLES LIKE 'max_heap_table_size';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_ram';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_mmap';
SHOW GLOBAL VARIABLES LIKE 'temptable_use_mmap';
SHOW GLOBAL VARIABLES LIKE 'tmpdir';
~~~

Một số biến có thể không tồn tại trong phiên bản đang chạy hoặc đã bị deprecated/removed. Lệnh SHOW VARIABLES LIKE sẽ trả về không có hàng khi biến không hiện diện; điều đó không có nghĩa truy vấn SQL bị lỗi.

Kiểm tra giá trị theo session khi biến có SESSION scope:

~~~sql
SELECT
    @@GLOBAL.tmp_table_size AS global_tmp_table_size,
    @@SESSION.tmp_table_size AS session_tmp_table_size,
    @@GLOBAL.max_heap_table_size AS global_max_heap_table_size,
    @@SESSION.max_heap_table_size AS session_max_heap_table_size;
~~~

Các biến global-only như temptable_max_ram không có @@SESSION tương ứng. Hãy xem scope trong tài liệu biến hệ thống trước khi truy vấn.

Nếu ứng dụng dùng connection pool, session variable có thể được thiết lập riêng trên connection. Thay đổi global không nhất thiết cập nhật giá trị session đã được giữ trong những connection đang tồn tại. Sau khi điều chỉnh, cần kiểm tra giá trị thực tế trên các session mới và cũ.

## 8. Đọc kế hoạch thực thi để tìm bảng tạm

### 8.1. EXPLAIN

Chạy EXPLAIN cho câu SELECT đang được điều tra:

~~~sql
EXPLAIN
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

Trong định dạng truyền thống, cột Extra có thể hiển thị Using temporary khi kế hoạch cần internal temporary table. Using filesort cho biết server cần bước sắp xếp bổ sung; từ filesort không có nghĩa chắc chắn thao tác được ghi ra đĩa. Tên filesort mô tả thuật toán sort của MySQL, không khẳng định mọi dữ liệu sort đều nằm trên filesystem.

EXPLAIN là mô tả kế hoạch dự kiến. Nó không cung cấp đầy đủ dung lượng bảng tạm hoặc số byte đã spill ở lần thực thi thực tế. Một số materialization trong derived table hoặc CTE có thể không được thể hiện bằng một dấu hiệu Using temporary đơn giản trong hàng bạn đang nhìn. Cần đọc toàn bộ cây kế hoạch.

### 8.2. EXPLAIN FORMAT=TREE và EXPLAIN ANALYZE

~~~sql
EXPLAIN FORMAT=TREE
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id;
~~~

TREE giúp nhìn rõ các iterator và bước materialization. Với MySQL hỗ trợ EXPLAIN ANALYZE, có thể đo thời gian và số hàng thực tế:

~~~sql
EXPLAIN ANALYZE
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id;
~~~

EXPLAIN ANALYZE thực thi câu truy vấn để thu thập số liệu thực tế. Chỉ chạy trên câu lệnh SELECT đã đánh giá an toàn, với điều kiện tải và giới hạn phù hợp; không coi nó là lệnh chỉ đọc kế hoạch như EXPLAIN thông thường.

### 8.3. Đọc dấu hiệu đúng ngữ cảnh

| Dấu hiệu | Ý nghĩa | Cần kiểm tra tiếp |
|---|---|---|
| Using temporary | Có bước cần internal temporary table trong kế hoạch | Loại thao tác, số hàng trung gian, engine và mức sử dụng RAM |
| Using filesort | Có bước sort ngoài thứ tự index | Số hàng sort, độ rộng hàng, sort_merge_passes và index |
| Materialize | Kết quả trung gian được vật chất hóa | Vì sao không merge/stream, kích thước kết quả và số lần đọc |
| Using temporary; Using filesort | Có cả cấu trúc trung gian và sort | Xác định bước nào chiếm thời gian và I/O |
| Không có Using temporary | Kế hoạch không chỉ ra dấu hiệu này | Vẫn kiểm tra runtime, digest và các bước materialization khác |

Không đặt mục tiêu loại bỏ mọi bảng tạm. Một bảng tạm nhỏ trong RAM có thể rẻ hơn việc thực hiện lại phép tính nhiều lần hoặc chọn một kế hoạch join kém hơn.

## 9. Theo dõi qua status counters

MySQL cung cấp hai status counter thường được dùng:

- Created_tmp_tables: số internal temporary tables được tạo.
- Created_tmp_disk_tables: số internal temporary tables được tạo trên đĩa theo cách counter ghi nhận.

Xem giá trị global:

~~~sql
SHOW GLOBAL STATUS LIKE 'Created_tmp%';
~~~

Xem giá trị của session hiện tại:

~~~sql
SHOW SESSION STATUS LIKE 'Created_tmp%';
~~~

Status counters là số tích lũy trong phạm vi tương ứng. Để đo workload, lấy mẫu ở hai thời điểm và tính delta trong khoảng đo. Một giá trị global lớn sau nhiều ngày uptime không chứng minh hệ thống đang có vấn đề ngay lúc này.

Một điểm cần nhớ với TempTable: Created_tmp_disk_tables không phản ánh đầy đủ các internal temporary tables dùng memory-mapped files. Do đó, counter thấp không chứng minh rằng không có dữ liệu tạm được ghi ra filesystem. Hãy kết hợp Performance Schema memory instruments và giám sát filesystem.

### 9.1. Tính tỷ lệ từ delta

Trong một cửa sổ đo, ghi lại:

~~~text
T0: Created_tmp_tables = 120000
    Created_tmp_disk_tables = 18000

T1: Created_tmp_tables = 125000
    Created_tmp_disk_tables = 19000

Delta tables      = 5000
Delta disk tables = 1000
Tỷ lệ disk / tables theo counter = 20%
~~~

Đây chỉ là tỷ lệ tham khảo từ hai counter. Nó không bao gồm đầy đủ mmap spill và không cho biết bảng tạm lớn hay nhỏ. Không dùng một tỷ lệ duy nhất làm tiêu chí kết luận hiệu năng.

### 9.2. Global và session counter

Session counters hữu ích khi chạy một truy vấn thử nghiệm trên một connection riêng và lấy chênh lệch trước/sau. Global counters hữu ích khi quan sát toàn server nhưng bị ảnh hưởng bởi mọi workload đồng thời.

Khi đo bằng session counter, bảo đảm câu truy vấn thử nghiệm và các câu kiểm tra được chạy trên cùng connection. Khi đo global, ghi lại thời gian, tải hệ thống và các sự kiện deployment để tránh quy kết nhầm cho một truy vấn.

## 10. Theo dõi statement trong Performance Schema

### 10.1. Xếp hạng digest tạo bảng tạm

performance_schema.events_statements_summary_by_digest tổng hợp các statement theo digest. Có thể tìm những nhóm truy vấn tạo nhiều temporary tables:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_CREATED_TMP_TABLES,
    SUM_CREATED_TMP_DISK_TABLES,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_SORT_MERGE_PASSES
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_CREATED_TMP_DISK_TABLES DESC,
         SUM_CREATED_TMP_TABLES DESC
LIMIT 20;
~~~

Các cột tổng hợp cho biết xu hướng theo nhóm statement kể từ lần thống kê được khởi tạo hoặc reset. DIGEST_TEXT là dạng SQL đã chuẩn hóa, phù hợp để nhóm câu truy vấn có cấu trúc giống nhau.

Một digest có nhiều bảng tạm chưa chắc là ứng viên tối ưu tốt nhất. Hãy kết hợp COUNT_STAR, số hàng đã quét, số hàng trả về, thời gian tổng và mức độ quan trọng nghiệp vụ. Một câu lệnh chạy một triệu lần với bảng tạm nhỏ có thể quan trọng hơn một báo cáo chạy một lần với bảng tạm lớn.

### 10.2. Xem event của từng statement

~~~sql
SELECT
    THREAD_ID,
    EVENT_ID,
    SQL_TEXT,
    CREATED_TMP_TABLES,
    CREATED_TMP_DISK_TABLES,
    SORT_MERGE_PASSES,
    ROWS_EXAMINED,
    ROWS_SENT,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS elapsed_seconds
FROM performance_schema.events_statements_history_long
WHERE CREATED_TMP_TABLES > 0
   OR CREATED_TMP_DISK_TABLES > 0
ORDER BY TIMER_WAIT DESC
LIMIT 50;
~~~

Bảng history_long là vùng lưu trữ hữu hạn. Event có thể bị ghi đè khi workload tiếp tục chạy. Nếu cần điều tra, thu thập dữ liệu sớm và chuyển số liệu quan trọng sang hệ thống quan sát bền vững.

Nếu cần nối statement với connection, ánh xạ THREAD_ID sang PROCESSLIST_ID trong performance_schema.threads khi thread còn tồn tại. Không nhầm THREAD_ID với CONNECTION_ID().

### 10.3. Kiểm tra memory instruments của TempTable

Có thể xem mức sử dụng bộ nhớ qua bảng tổng hợp memory:

~~~sql
SELECT
    EVENT_NAME,
    CURRENT_NUMBER_OF_BYTES_USED,
    HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
WHERE EVENT_NAME LIKE 'memory/temptable/%'
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC;
~~~

Tùy phiên bản và cấu hình instrument, các event TempTable có thể bao gồm memory/temptable/physical_ram và memory/temptable/physical_disk. Một số instrument cần được bật trước khi dữ liệu được thu thập.

Kiểm tra instrument:

~~~sql
SELECT NAME, ENABLED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'memory/temptable/%'
ORDER BY NAME;
~~~

Nếu instrument bị tắt, số liệu có thể không đầy đủ. Bật instrumentation cần có quyền phù hợp và đánh giá overhead. Không thay đổi hàng loạt setup_instruments trên production chỉ để kiểm tra một câu truy vấn.

### 10.4. sys schema

sys schema cung cấp các view tổng hợp từ Performance Schema để giúp đọc workload. Có thể bắt đầu bằng các view liên quan đến statement analysis hoặc temporary tables nếu chúng hiện diện trong bản phân phối MySQL đang dùng.

~~~sql
SHOW FULL TABLES FROM sys LIKE '%temp%';
SHOW FULL TABLES FROM sys LIKE '%statement%';
~~~

Tên và cột của view có thể thay đổi theo phiên bản. Trước khi đưa view vào runbook tự động, kiểm tra định nghĩa view và quyền truy cập trên server thực tế.

## 11. Xác định nơi dữ liệu tạm được ghi

### 11.1. tmpdir

tmpdir chỉ định thư mục hoặc danh sách thư mục mà MySQL sử dụng cho một số file tạm, bao gồm memory-mapped files của TempTable. Đọc cấu hình:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'tmpdir';
~~~

Kiểm tra trên máy chủ:

- Filesystem chứa tmpdir còn bao nhiêu dung lượng.
- Inode còn đủ hay không trên filesystem có giới hạn inode.
- Quyền sở hữu và quyền ghi của user chạy mysqld.
- Dung lượng tăng trong lúc chạy báo cáo hoặc batch.
- I/O latency và queue depth của thiết bị chứa tmpdir.
- Chính sách dọn dẹp và khả năng phục hồi sau khi mysqld dừng bất thường.

Không xóa thủ công file đang được mysqld sử dụng. File tạm có thể đang được process giữ mở hoặc ánh xạ vào bộ nhớ. Dọn file khi server đang chạy có thể gây hỏng tác vụ hoặc không giải phóng dung lượng như mong đợi.

### 11.2. InnoDB temporary tablespaces

On-disk internal temporary tables dùng cơ chế temporary tablespace của InnoDB. Vị trí và cách quản lý phụ thuộc phiên bản và cấu hình InnoDB; không phải mọi file tạm đều nằm trong tmpdir.

Kiểm tra các biến liên quan nếu có:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_temp%';
SHOW GLOBAL VARIABLES LIKE 'innodb_data_home_dir';
~~~

Trên máy chủ, xác định thư mục thực tế và theo dõi dung lượng file temporary tablespace, tốc độ tăng, I/O và khả năng mở rộng filesystem. Không suy ra vị trí chỉ từ tên file hoặc giả định mọi phiên bản đều dùng một file duy nhất.

### 11.3. Phân biệt dung lượng file và RAM

Một file mmap lớn không đồng nghĩa toàn bộ dung lượng file đang chiếm RAM vật lý. Ngược lại, dung lượng mmap tăng vẫn có thể tạo áp lực lên page cache và filesystem. Cần đọc đồng thời:

- Memory instruments của TempTable.
- Dung lượng và I/O của tmpdir.
- Dung lượng InnoDB temporary tablespace.
- Memory available, swap và page cache của hệ điều hành.
- CPU, I/O wait và thời gian statement.

Không dùng một chỉ số filesystem để kết luận lượng RAM TempTable đang sử dụng.

## 12. Vì sao bảng tạm tràn đĩa và tác động tới hiệu năng?

Các nguyên nhân phổ biến:

1. **Tập trung gian lớn:** truy vấn đọc nhiều hàng trước khi GROUP BY, DISTINCT hoặc sort.
2. **Hàng trung gian rộng:** SELECT nhiều cột, chứa chuỗi lớn hoặc dữ liệu không cần thiết.
3. **Thiếu index phù hợp:** server phải đọc nhiều hàng và sắp xếp/nhóm trong một bước riêng.
4. **Materialization:** derived table hoặc CTE được lưu lại với số hàng lớn.
5. **Giới hạn cấu hình thấp:** tmp_table_size hoặc ngân sách TempTable không đủ cho workload.
6. **Concurrency cao:** nhiều truy vấn cùng sử dụng vùng RAM TempTable.
7. **Filesystem bị hạn chế:** mmap hoặc InnoDB temporary tablespace không còn đủ dung lượng hoặc chịu I/O cao.
8. **Kiểu dữ liệu/engine:** MEMORY không hỗ trợ một số kiểu dữ liệu, khiến server phải dùng đường on-disk.

Khi spill xảy ra, MySQL phải đọc/ghi dữ liệu trung gian qua storage. Tác động có thể bao gồm:

- Thời gian truy vấn tăng do I/O và chi phí quản lý trang.
- Tranh chấp I/O với redo, data file, binary log hoặc workload khác.
- Dung lượng filesystem giảm, tăng nguy cơ hết chỗ.
- Nhiều truy vấn đồng thời kéo dài thời gian hoàn tất và giữ tài nguyên lâu hơn.
- Tăng thời gian giữ transaction hoặc connection nếu ứng dụng xử lý kết quả chậm.

Spill không tự động đồng nghĩa truy vấn lỗi hoặc server thiếu RAM. Cần đo thời gian, số hàng, kích thước trung gian, mức độ đồng thời và tác động tới workload chính.

## 13. Tối ưu SQL để giảm bảng tạm và lượng dữ liệu trung gian

### 13.1. Giảm hàng đầu vào sớm

Đẩy điều kiện lọc có thể áp dụng an toàn về gần nguồn dữ liệu:

~~~sql
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
GROUP BY customer_id;
~~~

Nếu có index phù hợp với status và created_at, MySQL có thể giảm số hàng cần đọc trước khi tổng hợp. Thứ tự cột index phải dựa trên selectivity, điều kiện truy vấn và workload tổng thể; không tạo index chỉ vì một câu SQL đơn lẻ.

### 13.2. Chỉ lấy cột cần dùng

Tránh SELECT * trong truy vấn tạo tập trung gian:

~~~sql
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id;
~~~

Nếu tập trung gian chứa nhiều VARCHAR/TEXT hoặc cột rộng mà bước sau không dùng, chi phí lưu trữ, sao chép và sort sẽ tăng. Giảm độ rộng hàng thường có lợi ngay cả khi số hàng không đổi.

### 13.3. Thiết kế index cho GROUP BY và ORDER BY

Index có thể giúp server đọc dữ liệu theo thứ tự hữu ích và giảm bước sort hoặc temporary table trong một số kế hoạch. Ví dụ:

~~~sql
CREATE INDEX idx_orders_status_created_customer
ON orders (status, created_at, customer_id);
~~~

Index trên chỉ là ví dụ minh họa. Điều kiện status equality, khoảng created_at và cách nhóm theo customer_id có thể khiến optimizer chỉ tận dụng một phần thứ tự index. Kiểm tra EXPLAIN, cardinality, số hàng thực tế và chi phí ghi của index trước khi triển khai.

Không phải lúc nào index cũng loại bỏ được temporary table. Nếu cần ORDER BY SUM(total_amount), giá trị tổng chỉ có sau khi GROUP BY nên vẫn có thể cần sort.

### 13.4. Loại bỏ DISTINCT hoặc UNION không cần thiết

DISTINCT và UNION có thể tốn chi phí khử trùng lặp. Nếu khóa hoặc ràng buộc dữ liệu đã đảm bảo không có hàng trùng, xem xét bỏ DISTINCT. Nếu logic chấp nhận trùng, UNION ALL có thể giảm bước loại trùng.

Phải chứng minh tính đúng đắn từ dữ liệu và yêu cầu nghiệp vụ. Không bỏ DISTINCT chỉ để làm EXPLAIN đẹp hơn.

### 13.5. Đánh giá materialization của CTE và derived table

CTE có thể được merge hoặc materialize tùy cấu trúc và quyết định optimizer. Materialization có thể có lợi khi kết quả được dùng nhiều lần; cũng có thể tốn bộ nhớ nếu kết quả lớn.

~~~sql
WITH recent_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE created_at >= '2026-01-01'
)
SELECT customer_id, SUM(total_amount)
FROM recent_orders
GROUP BY customer_id;
~~~

Đảm bảo điều kiện lọc nằm ở đúng cấp để giảm kích thước tập dữ liệu. Dùng EXPLAIN FORMAT=TREE để xem CTE được merge hay materialize. Không ép optimizer bằng hint nếu chưa đo được lợi ích.

### 13.6. Giảm số lần materialize

Nếu cùng một phép tính được thực hiện lặp lại trong nhiều subquery hoặc CTE, xem xét cấu trúc lại truy vấn để tái sử dụng kết quả khi điều đó có lợi. Ngược lại, một materialization dùng một lần nhưng rất lớn có thể nên được thay bằng chiến lược join hoặc truy vấn khác.

Cân nhắc trade-off giữa tính toán lại, materialize một lần, số hàng trung gian và concurrency. Không có quy tắc rằng merge luôn tốt hơn materialize.

### 13.7. Giới hạn dữ liệu trước khi sort

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 9021
ORDER BY created_at DESC
LIMIT 50;
~~~

Index (customer_id, created_at) có thể hỗ trợ lọc và thứ tự nếu hướng sắp xếp phù hợp. Khi truy vấn có thể đọc đúng 50 hàng từ index, server không cần sort toàn bộ lịch sử của customer.

Ngược lại, LIMIT sau GROUP BY hoặc ORDER BY trên biểu thức tổng hợp không nhất thiết giảm số hàng cần tổng hợp. Hãy đọc kế hoạch và số hàng thực tế.

## 14. Điều chỉnh cấu hình theo ngân sách hệ thống

### 14.1. Không tăng mọi giới hạn cùng lúc

Một cấu hình thử nghiệm có thể thay đổi một biến tại một thời điểm, ghi lại baseline, chạy cùng workload và so sánh. Ví dụ:

~~~sql
SET GLOBAL temptable_max_ram = 1073741824;
~~~

Giá trị trên chỉ là minh họa cách biểu diễn byte; không phải khuyến nghị mặc định cho production. Trước khi đặt giá trị, đọc giá trị hiện tại, scope, giới hạn hợp lệ và dung lượng RAM thực tế.

Với biến session như tmp_table_size, thử nghiệm có kiểm soát có thể thực hiện trên connection riêng:

~~~sql
SET SESSION tmp_table_size = 67108864;
~~~

Thay đổi session chỉ ảnh hưởng connection đó. Nếu connection pool có nhiều session đang tồn tại, phải xác định nơi cấu hình được áp dụng và cách khởi tạo connection mới.

### 14.2. Lập ngân sách bộ nhớ

Khi lập kế hoạch, không chỉ cộng một con số cho TempTable. Cần dành RAM cho:

- Buffer pool của InnoDB.
- Connection/thread overhead.
- Sort buffer, join buffer và các buffer theo operation/session.
- TempTable RAM.
- Table cache, metadata, Performance Schema và các thành phần server.
- Hệ điều hành, page cache, agent giám sát và tiến trình khác.

temptable_max_ram là ngân sách dùng chung của TempTable, còn tmp_table_size có thể giới hạn từng bảng. Nhiều statement có thể đồng thời giữ nhiều bảng trung gian; một statement cũng có thể tạo nhiều cấu trúc trung gian. Vì vậy, dùng workload đại diện để đo đỉnh sử dụng và giữ khoảng dự phòng cho burst.

Không đặt temptable_max_ram bằng toàn bộ RAM còn trống theo một phép trừ đơn giản. Server cần bộ nhớ cho các workload khác và hệ điều hành; mmap cũng tạo áp lực lên filesystem và page cache.

### 14.3. Cân bằng RAM, mmap và InnoDB

- Tăng ngân sách RAM có thể giảm số lần phải dùng mmap hoặc InnoDB, nhưng tăng nguy cơ áp lực bộ nhớ khi concurrency cao.
- Tăng giới hạn mmap có thể cho phép TempTable lưu thêm dữ liệu trong file ánh xạ, nhưng filesystem có thể đầy và I/O tăng.
- Giới hạn từng bảng thấp có thể khiến bảng lớn spill sớm, dù ngân sách RAM toàn cục còn trống.
- Dùng MEMORY thay TempTable có thể thay đổi hành vi và hạn chế kiểu dữ liệu; không phải lựa chọn mặc định để giảm spill.

Chọn giá trị theo peak concurrency và kích thước tập trung gian thực tế. Đánh giá cả latency p95/p99, throughput, memory pressure và filesystem I/O.

### 14.4. Cấu hình bền vững và rollback

Nếu thay đổi biến global để thử nghiệm, ghi lại giá trị cũ và phạm vi tác động. SET GLOBAL có thể không tồn tại sau restart. SET PERSIST có thể lưu giá trị qua restart trên các phiên bản hỗ trợ; SET PERSIST_ONLY áp dụng khi khởi động kế tiếp. Quyền cần thiết và hành vi biến phụ thuộc phiên bản.

Không dùng SET PERSIST chỉ vì một lần thử thành công. Trước khi lưu bền vững, chạy đủ workload đại diện, xem tác động trên nhiều node và có kế hoạch rollback. Nếu thay đổi bằng file cấu hình, lưu bản cũ và xác minh giá trị runtime sau khi khởi động lại.

## 15. Kịch bản điều tra: báo cáo làm filesystem tạm tăng nhanh

Giả sử trong giờ cao điểm, filesystem chứa tmpdir tăng nhanh và một số báo cáo chậm hơn bình thường. Quy trình điều tra:

1. **Ghi nhận thời điểm và instance.** Xác định node, phiên bản MySQL, thời gian bắt đầu tăng dung lượng và workload đang chạy.
2. **Kiểm tra filesystem.** Đọc dung lượng còn lại, inode, I/O latency và tốc độ tăng file trong tmpdir. Xác minh quyền ghi và mount point.
3. **Đọc biến runtime.** Kiểm tra internal_tmp_mem_storage_engine, temptable_max_ram, temptable_max_mmap, tmp_table_size, tmpdir và biến hiện có theo phiên bản.
4. **Lấy status delta.** Chụp Created_tmp_tables và Created_tmp_disk_tables ở đầu/cuối cửa sổ. Nhớ rằng counter disk không phản ánh đầy đủ mmap files.
5. **Xếp hạng digest.** Dùng events_statements_summary_by_digest để tìm nhóm statement tạo nhiều temporary tables hoặc disk tables.
6. **Đọc execution plan.** Chọn một digest tiêu biểu, lấy SQL mẫu và chạy EXPLAIN; dùng EXPLAIN ANALYZE trên bản sao hoặc cửa sổ thử nghiệm an toàn để đo số hàng và iterator.
7. **Đọc memory instruments.** Kiểm tra memory/temptable nếu instrument được bật; so sánh RAM hiện tại, high-water mark và dung lượng filesystem.
8. **Kiểm tra concurrency.** Xác định số báo cáo chạy đồng thời, connection pool, lịch batch và các truy vấn ad hoc.
9. **Thử thay đổi SQL trước.** Giảm số hàng/độ rộng trung gian, kiểm tra index và materialization. Đo lại trên cùng dữ liệu.
10. **Chỉ sau đó thử cấu hình.** Thay một giới hạn có kiểm soát, ghi lại giá trị cũ, đo latency, memory, I/O và filesystem; rollback nếu tác động xấu.
11. **Đặt ngưỡng cảnh báo.** Cảnh báo dung lượng tmpdir, InnoDB temporary tablespace, I/O wait và tỷ lệ statement có temporary table.
12. **Ghi runbook.** Lưu câu SQL, digest, execution plan, biến runtime, cửa sổ đo, thay đổi và kết quả.

Không xóa file tạm bằng tay để giải phóng dung lượng khi mysqld còn chạy. Nếu filesystem sắp đầy, giảm hoặc dừng workload gây tăng trưởng theo runbook, bảo vệ server và xử lý theo quy trình vận hành của nhóm DBA.

## 16. Những sai lầm thường gặp

| Sai lầm | Vì sao không đúng | Cách xử lý |
|---|---|---|
| Thấy Using temporary là kết luận bảng đã spill ra đĩa | Dấu hiệu chỉ cho biết cần internal temporary table | Đo engine, counters, memory và filesystem |
| Thấy Created_tmp_disk_tables không tăng nên kết luận không có spill | mmap files không được phản ánh đầy đủ trong counter này | Kiểm tra TempTable memory instruments và tmpdir |
| Tăng tmp_table_size để giải quyết mọi vấn đề TempTable | Giới hạn RAM toàn cục và giới hạn từng bảng khác nhau; phiên bản có hành vi khác | Kiểm tra tmp_table_size và temptable_max_ram theo phiên bản |
| Tăng max_heap_table_size dù engine là TempTable | Biến này chủ yếu liên quan đến MEMORY | Xác minh internal_tmp_mem_storage_engine |
| Chuyển internal_tmp_mem_storage_engine sang MEMORY để tiết kiệm RAM | MEMORY có giới hạn kiểu dữ liệu và hành vi khác; có thể spill sớm | So sánh workload và kế hoạch thực thi |
| Tăng temptable_max_mmap mà không kiểm tra disk | Mmap vẫn tiêu thụ filesystem và có thể làm đầy tmpdir | Theo dõi dung lượng, inode và I/O |
| Coi mọi temporary table là bảng CREATE TEMPORARY TABLE | Hai loại có vòng đời và cơ chế quản lý khác nhau | Phân biệt internal và user-created |
| Chỉ xem một truy vấn đơn lẻ | Workload đồng thời mới tạo ra áp lực toàn cục | Đo concurrency thực tế |
| Tối ưu để xóa mọi bảng tạm | Có thể làm truy vấn tính toán lặp hoặc dùng kế hoạch join tệ hơn | Tối ưu theo latency và throughput tổng thể |
| Xóa file tmp khi server đang chạy | File có thể đang được sử dụng hoặc ánh xạ | Dùng runbook và cơ chế quản lý của MySQL |

## 17. Checklist vận hành

- [ ] Đã phân biệt internal temporary table với CREATE TEMPORARY TABLE.
- [ ] Đã biết engine internal_tmp_mem_storage_engine đang sử dụng.
- [ ] Đã đọc các giới hạn RAM và mmap hiện có theo đúng phiên bản.
- [ ] Đã kiểm tra tmp_table_size, temptable_max_ram và max_heap_table_size đúng phạm vi áp dụng.
- [ ] Đã xác minh biến temptable_use_mmap còn được hỗ trợ hay đã deprecated/removed.
- [ ] Đã đọc EXPLAIN hoặc EXPLAIN FORMAT=TREE của truy vấn tạo bảng tạm.
- [ ] Đã đo status counter bằng delta trong cửa sổ có kiểm soát.
- [ ] Đã kiểm tra statement digest và event history trong Performance Schema.
- [ ] Đã kiểm tra memory/temptable instruments nếu có.
- [ ] Đã theo dõi tmpdir, InnoDB temporary tablespace, filesystem và I/O.
- [ ] Đã đo workload với concurrency đại diện.
- [ ] Đã thử giảm hàng và độ rộng dữ liệu trung gian trước khi tăng cấu hình.
- [ ] Mọi thay đổi biến có giá trị cũ, lý do, phạm vi và kế hoạch rollback.
- [ ] Không xóa thủ công file tạm khi mysqld đang sử dụng.
- [ ] Có cảnh báo và runbook cho tình huống filesystem tạm gần đầy.

## 18. Bài tập thực hành

### Bài 1: Nhận diện internal temporary table

Tạo một truy vấn GROUP BY kết hợp ORDER BY trên biểu thức tổng hợp. Chạy EXPLAIN và ghi lại Using temporary, Using filesort hoặc các node materialization nếu xuất hiện. Thử thêm index phù hợp và so sánh kế hoạch.

Kết quả cần có: giải thích bước nào tạo kết quả trung gian và liệu index có thay đổi kế hoạch hay không.

### Bài 2: Đo status counter theo session

Trên một connection riêng, chụp SHOW SESSION STATUS LIKE 'Created_tmp%'. Chạy một truy vấn có DISTINCT hoặc GROUP BY trên tập dữ liệu thử nghiệm, sau đó chụp counter lần nữa và tính delta.

Kết quả cần có: delta của Created_tmp_tables và Created_tmp_disk_tables, kèm lưu ý rằng counter không thể hiện đầy đủ mmap usage.

### Bài 3: Tìm digest tạo nhiều bảng tạm

Truy vấn events_statements_summary_by_digest, sắp xếp theo SUM_CREATED_TMP_TABLES và SUM_CREATED_TMP_DISK_TABLES. Chọn một digest có COUNT_STAR lớn, lấy SQL mẫu và xem execution plan.

Kết quả cần có: digest, số lần chạy, số bảng tạm, số hàng quét, thời gian tổng và đề xuất tối ưu.

### Bài 4: Theo dõi TempTable memory

Kiểm tra memory instruments có tên memory/temptable. Nếu được bật, đọc CURRENT_NUMBER_OF_BYTES_USED và HIGH_NUMBER_OF_BYTES_USED trong memory_summary_global_by_event_name. Chạy workload thử nghiệm rồi quan sát thay đổi.

Kết quả cần có: số liệu trước/sau và giải thích giới hạn của số liệu instrument.

### Bài 5: Mô phỏng spill và đánh giá concurrency

Trên môi trường thử nghiệm có dữ liệu đủ lớn, chạy truy vấn tạo tập trung gian có kiểm soát. So sánh chạy đơn lẻ và nhiều session đồng thời. Theo dõi latency, TempTable memory, status counters và dung lượng filesystem.

Kết quả cần có: ảnh hưởng của concurrency tới ngân sách RAM dùng chung và mức sử dụng disk. Không chạy thử nghiệm gây áp lực trên production.

## 19. Tài liệu cần tra cứu

Khi triển khai, đối chiếu MySQL Reference Manual đúng phiên bản cho các nội dung:

- Internal Temporary Tables.
- TempTable Storage Engine.
- Internal Temporary Table Use in MySQL.
- System Variables: internal_tmp_mem_storage_engine, tmp_table_size, max_heap_table_size, temptable_max_ram, temptable_max_mmap, temptable_use_mmap và tmpdir.
- Status Variables: Created_tmp_tables và Created_tmp_disk_tables.
- Performance Schema statement event tables và memory summary tables.
- EXPLAIN Output, EXPLAIN FORMAT=TREE và EXPLAIN ANALYZE.
- InnoDB Temporary Tablespaces.

Các thay đổi giữa MySQL 8.0.x, 8.4 và các nhánh mới có thể ảnh hưởng đến engine mặc định, giới hạn từng bảng và biến mmap. Luôn kiểm tra @@version, SHOW VARIABLES và tài liệu phát hành của server đang chạy trước khi áp dụng cấu hình hoặc runbook.

