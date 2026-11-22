# Hint, FORCE/USE/IGNORE INDEX và điều kiện cú pháp theo phiên bản

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vì sao cần index hint và khi nào nên giữ quyết định cho optimizer.
- Phân biệt USE INDEX, FORCE INDEX và IGNORE INDEX.
- Viết đúng cú pháp INDEX/KEY, tên index, alias và các phạm vi FOR JOIN, FOR ORDER BY, FOR GROUP BY.
- Hiểu cách MySQL kết hợp nhiều index hint, xử lý danh sách rỗng và báo lỗi khi trộn USE với FORCE.
- Dùng optimizer hint dạng comment như JOIN_INDEX, ORDER_INDEX, GROUP_INDEX, INDEX và các biến thể NO_*.
- Phân biệt ngữ nghĩa của optimizer index hint mới với USE INDEX truyền thống.
- Nắm các mốc hỗ trợ từ MySQL 8.0.20 và trạng thái tương thích trong MySQL 8.4, 9.7.
- Kiểm tra hint bằng EXPLAIN, SHOW WARNINGS và EXPLAIN ANALYZE.
- Đánh giá tác động của hint trên dữ liệu đại diện và tránh giữ một kế hoạch bị ép khi dữ liệu thay đổi.

Optimizer của MySQL chọn index dựa trên điều kiện truy vấn, thống kê và chi phí ước lượng. Trong phần lớn trường hợp, nên để optimizer tự chọn. Khi EXPLAIN cho thấy nó chọn một index không phù hợp hoặc một index cụ thể làm kế hoạch ổn định hơn trong một workload đã đo, ta có thể dùng hint để giới hạn lựa chọn.

Có hai nhóm cú pháp thường gặp:

1. Index hint truyền thống đặt sau tên bảng, chẳng hạn USE INDEX, FORCE INDEX và IGNORE INDEX.
2. Optimizer hint đặt trong comment đặc biệt sau từ khóa SELECT, UPDATE, INSERT, REPLACE hoặc DELETE, chẳng hạn JOIN_INDEX và NO_ORDER_INDEX.

Hai nhóm có phạm vi và mức ưu tiên khác nhau. Cần hiểu rõ sự khác biệt trước khi đưa hint vào ứng dụng.

## 1. Khi nào nên dùng index hint?

Index hint là chỉ dẫn cho optimizer về tập index có thể hoặc không thể được sử dụng. Nó không tạo index mới và không sửa cấu trúc dữ liệu.

Một hint có thể hữu ích khi:

- EXPLAIN cho thấy optimizer chọn index có độ chọn lọc thấp trong khi có index khác phù hợp hơn.
- Thống kê chưa phản ánh đúng phân bố dữ liệu và cần thử một access path khác.
- Một truy vấn có nhiều index cạnh tranh, cần giới hạn lựa chọn để kiểm chứng giả thuyết.
- Cần kiểm tra tác động của việc loại một index khỏi kế hoạch.
- Cần tách ảnh hưởng của index dùng để tìm hàng khỏi index dùng cho ORDER BY hoặc GROUP BY.

Không nên thêm hint chỉ vì thấy type = ALL hoặc vì nghĩ rằng dùng index luôn nhanh hơn. Một table scan có thể rẻ hơn khi bảng nhỏ hoặc truy vấn cần phần lớn hàng. Hint không thay thế việc kiểm tra thống kê, điều kiện lọc, kiểu dữ liệu, thứ tự cột trong composite index và số hàng thực tế.

Quy trình hợp lý là:

1. Chạy EXPLAIN và ghi lại kế hoạch hiện tại.
2. Xác định index nào có thể phục vụ đúng điều kiện.
3. Thử hint trong môi trường kiểm thử.
4. So sánh access type, key, rows, Extra và thời gian thực tế.
5. Kiểm tra với nhiều giá trị tham số và phân bố dữ liệu.
6. Chỉ giữ hint nếu cải thiện ổn định và có lý do rõ ràng.

## 2. Chuẩn bị bảng thực hành

Các ví dụ dùng bảng đơn hàng InnoDB với nhiều index có mục đích khác nhau.

~~~sql
CREATE TABLE sales_order_hint_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    ordered_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    region_code VARCHAR(12) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_customer_status (customer_id, order_status),
    KEY idx_status (order_status),
    KEY idx_ordered_at (ordered_at),
    KEY idx_total_amount (total_amount),
    KEY idx_region_ordered (region_code, ordered_at)
) ENGINE = InnoDB;

CREATE TABLE customer_hint_demo (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;
~~~

Nạp một ít dữ liệu:

~~~sql
INSERT INTO sales_order_hint_demo (
    order_id,
    customer_id,
    order_status,
    ordered_at,
    total_amount,
    region_code
)
VALUES
    (7001, 101, 'PAID',      '2026-02-01 09:15:00', 1250000.00, 'NORTH'),
    (7002, 101, 'PAID',      '2026-02-03 11:30:00', 2400000.00, 'NORTH'),
    (7003, 102, 'PENDING',   '2026-02-08 14:00:00',  890000.00, 'SOUTH'),
    (7004, 103, 'PAID',      '2026-02-15 16:45:00', 3400000.00, 'NORTH'),
    (7005, 101, 'CANCELLED', '2026-02-18 10:20:00',  450000.00, 'NORTH'),
    (7006, 104, 'PAID',      '2026-03-02 08:10:00', 5100000.00, 'CENTRAL'),
    (7007, 102, 'PENDING',   '2026-03-05 13:25:00',  760000.00, 'SOUTH'),
    (7008, 103, 'PAID',      '2026-03-10 17:05:00', 1750000.00, 'NORTH'),
    (7009, 105, 'PAID',      '2026-03-14 10:00:00',  980000.00, 'EAST'),
    (7010, 106, 'PENDING',   '2026-03-20 12:30:00', 2150000.00, 'EAST');

INSERT INTO customer_hint_demo (customer_id, customer_name)
VALUES
    (101, 'Nguyen An'),
    (102, 'Tran Binh'),
    (103, 'Le Chi'),
    (104, 'Pham Dung');
~~~

Kiểm tra index name:

~~~sql
SHOW INDEX FROM sales_order_hint_demo;
~~~

Tên index được truyền vào hint, không phải tên cột. Khóa chính được tham chiếu bằng tên PRIMARY. Các ví dụ có thể cho kế hoạch khác nhau tùy số lượng dữ liệu, thống kê, phiên bản và cấu hình; bảng nhỏ thường khiến optimizer chọn table scan.

## 3. Cú pháp index hint truyền thống

Index hint được đặt ngay sau tên bảng và alias trong table reference.

Cú pháp tổng quát:

~~~text
tbl_name [[AS] alias] [index_hint_list]

index_hint_list:
    index_hint [index_hint] ...

index_hint:
    USE {INDEX|KEY}
      [FOR {JOIN|ORDER BY|GROUP BY}] (index_list)
  | {IGNORE|FORCE} {INDEX|KEY}
      [FOR {JOIN|ORDER BY|GROUP BY}] (index_list)

index_list:
    index_name [, index_name] ...
~~~

INDEX và KEY là hai cách viết tương đương trong cú pháp này.

Ví dụ:

~~~sql
SELECT
    o.order_id,
    o.total_amount
FROM sales_order_hint_demo AS o
USE INDEX (idx_customer_status)
WHERE o.customer_id = 101;
~~~

Hint gắn với table reference sales_order_hint_demo, alias o. Khi dùng alias, hãy giữ nhất quán alias trong câu truy vấn. Với optimizer hint dạng comment, tên bảng được tham chiếu trong hint cũng phải là alias đang xuất hiện trong query block.

### 3.1. Tên index, không phải tên cột

Giả sử có index:

~~~text
KEY idx_customer_status (customer_id, order_status)
~~~

Tên hợp lệ trong hint là idx_customer_status:

~~~sql
SELECT *
FROM sales_order_hint_demo
USE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

Cách viết sau sai vì customer_id là tên cột, không phải tên index:

~~~sql
SELECT *
FROM sales_order_hint_demo
USE INDEX (customer_id)
WHERE customer_id = 101;
~~~

Để tham chiếu PRIMARY KEY, dùng PRIMARY:

~~~sql
SELECT *
FROM sales_order_hint_demo
FORCE INDEX (PRIMARY)
WHERE order_id = 7001;
~~~

MySQL cho phép dùng một prefix không mơ hồ của tên index, nhưng nên ghi đầy đủ tên để tránh xung đột khi schema có thêm index.

## 4. USE INDEX: giới hạn tập index được cân nhắc

USE INDEX cho MySQL biết chỉ cân nhắc các index được liệt kê để tìm hàng trong bảng. Các index không nằm trong danh sách bị loại khỏi tập ứng viên của phạm vi tương ứng.

Ví dụ:

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    order_status
FROM sales_order_hint_demo AS o
USE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

USE INDEX không bắt buộc MySQL phải dùng một index trong danh sách bằng mọi giá. Optimizer vẫn có thể chọn table scan nếu đánh giá scan rẻ hơn hoặc index không áp dụng được cho điều kiện.

Điểm cần nhớ:

- Chỉ các index được nêu mới được cân nhắc cho phạm vi của hint.
- Table scan vẫn có thể được chọn.
- Có thể nêu nhiều index trong danh sách.
- USE INDEX phù hợp để giới hạn lựa chọn, không phải ép index mạnh nhất.

### 4.1. USE INDEX với danh sách rỗng

Cú pháp USE INDEX () hợp lệ và có nghĩa là không sử dụng index cho phạm vi đó:

~~~sql
EXPLAIN
SELECT *
FROM sales_order_hint_demo AS o
USE INDEX ()
WHERE customer_id = 101;
~~~

Đây là cách tạo một phép thử đối chứng với table scan. Chỉ dùng trên bảng nhỏ hoặc môi trường kiểm thử; không áp dụng tùy tiện cho bảng lớn.

Danh sách rỗng không hợp lệ với FORCE INDEX hoặc IGNORE INDEX. Hai loại hint đó bắt buộc có ít nhất một tên index.

## 5. FORCE INDEX: làm table scan bị đánh giá rất đắt

FORCE INDEX gần giống USE INDEX, nhưng bổ sung giả định rằng table scan rất tốn kém. MySQL chỉ dùng table scan nếu không có cách dùng một trong các index được chỉ định để tìm hàng.

Ví dụ:

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    order_status
FROM sales_order_hint_demo AS o
FORCE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

So sánh với USE INDEX:

| Đặc điểm | USE INDEX | FORCE INDEX |
|---|---|---|
| Giới hạn index được cân nhắc | Có | Có |
| Table scan vẫn là lựa chọn | Có, theo cost | Chỉ khi không có cách dùng index được nêu |
| Mức tác động | Giới hạn tập ứng viên | Mạnh hơn, làm scan có cost rất cao |
| Có bảo đảm index luôn được dùng | Không | Không, nếu index không áp dụng được |

FORCE INDEX không làm cho một index trở nên phù hợp với mọi điều kiện. Ví dụ, nếu index chỉ có customer_id nhưng truy vấn lọc theo một cột không nằm trong index và không có access path dùng được, MySQL vẫn có thể phải quét bảng.

Không nên hiểu FORCE INDEX là lệnh bắt storage engine đọc một index bất kể điều kiện truy vấn.

## 6. IGNORE INDEX: loại index khỏi lựa chọn

IGNORE INDEX yêu cầu MySQL không cân nhắc các index được chỉ định trong phạm vi hint.

Ví dụ:

~~~sql
EXPLAIN
SELECT
    order_id,
    order_status,
    total_amount
FROM sales_order_hint_demo AS o
IGNORE INDEX (idx_status)
WHERE order_status = 'PAID';
~~~

MySQL có thể cân nhắc index khác, index merge nếu phù hợp, hoặc table scan. IGNORE INDEX không chỉ định index thay thế.

Dùng IGNORE INDEX khi có bằng chứng một index đang khiến optimizer chọn kế hoạch kém. Hãy kiểm tra lại sau khi dữ liệu hoặc thống kê thay đổi vì index bị bỏ qua hôm nay có thể hữu ích cho workload ngày mai.

### 6.1. So sánh ba hint bằng cùng một truy vấn

~~~sql
EXPLAIN
SELECT *
FROM sales_order_hint_demo
USE INDEX (idx_status)
WHERE order_status = 'PAID';

EXPLAIN
SELECT *
FROM sales_order_hint_demo
FORCE INDEX (idx_status)
WHERE order_status = 'PAID';

EXPLAIN
SELECT *
FROM sales_order_hint_demo
IGNORE INDEX (idx_status)
WHERE order_status = 'PAID';
~~~

Ghi lại type, possible_keys, key, rows và Extra. Trên bảng nhỏ, optimizer có thể vẫn chọn scan với USE INDEX; FORCE INDEX làm scan bị đánh giá đắt hơn; IGNORE INDEX loại idx_status khỏi lựa chọn.

Không có output cố định cho mọi máy chủ vì kế hoạch phụ thuộc dữ liệu và cost model.

## 7. Phạm vi FOR JOIN, FOR ORDER BY và FOR GROUP BY

Một index có thể giúp tìm hàng, sắp xếp hoặc nhóm dữ liệu. Ba giai đoạn này có thể cần các index khác nhau.

### 7.1. FOR JOIN

FOR JOIN ảnh hưởng đến index được cân nhắc khi tìm hàng và xử lý join. Nếu bỏ FOR clause, hint áp dụng cho tất cả các phần của câu lệnh.

Ví dụ:

~~~sql
EXPLAIN
SELECT
    order_id,
    order_status
FROM sales_order_hint_demo AS o
USE INDEX FOR JOIN (idx_customer_status)
WHERE customer_id = 101;
~~~

FOR JOIN là phạm vi nên ghi rõ khi chỉ muốn kiểm soát index dùng để tìm hàng và xử lý JOIN. Nếu bỏ FOR clause, hint áp dụng cho cả JOIN, ORDER BY và GROUP BY.

### 7.2. FOR ORDER BY

FOR ORDER BY ảnh hưởng đến index dùng cho việc sắp xếp.

~~~sql
EXPLAIN
SELECT
    order_id,
    ordered_at,
    total_amount
FROM sales_order_hint_demo AS o
USE INDEX FOR ORDER BY (idx_ordered_at)
ORDER BY ordered_at DESC
LIMIT 5;
~~~

Hint này tác động đến lựa chọn index phục vụ ORDER BY. Nó không đồng nghĩa với việc index được ép dùng để tìm hàng theo WHERE.

### 7.3. FOR GROUP BY

FOR GROUP BY ảnh hưởng đến index được dùng trong xử lý GROUP BY.

~~~sql
EXPLAIN
SELECT
    order_status,
    COUNT(*) AS order_count
FROM sales_order_hint_demo AS o
USE INDEX FOR GROUP BY (idx_status)
GROUP BY order_status;
~~~

Nếu index không phù hợp với điều kiện hoặc cách nhóm, MySQL vẫn có thể cần một phương án khác. Hãy xem EXPLAIN để biết hint có tạo ra thay đổi thực tế không.

### 7.4. Không có FOR clause nghĩa là mọi phạm vi

Ví dụ:

~~~sql
SELECT *
FROM sales_order_hint_demo
IGNORE INDEX (idx_status)
WHERE order_status = 'PAID'
ORDER BY ordered_at;
~~~

IGNORE INDEX không có FOR clause tương đương với việc loại idx_status cho JOIN, ORDER BY và GROUP BY.

Nếu chỉ muốn bỏ một index trong giai đoạn sắp xếp, hãy ghi rõ:

~~~sql
SELECT *
FROM sales_order_hint_demo
IGNORE INDEX FOR ORDER BY (idx_status)
WHERE order_status = 'PAID'
ORDER BY ordered_at;
~~~

Chọn đúng phạm vi giúp tránh tác động ngoài ý muốn lên phần tìm hàng hoặc nhóm dữ liệu.

### 7.5. Ngoại lệ với FULLTEXT

Index hint có cách áp dụng riêng cho tìm kiếm FULLTEXT:

- Với `IN NATURAL LANGUAGE MODE`, index hint bị bỏ qua âm thầm; ví dụ IGNORE INDEX không ngăn MySQL dùng FULLTEXT index.
- Với `IN BOOLEAN MODE`, hint có `FOR ORDER BY` hoặc `FOR GROUP BY` bị bỏ qua âm thầm.
- Với boolean mode, hint có `FOR JOIN` hoặc không có FOR được áp dụng cho mọi giai đoạn xử lý truy vấn, kể cả tìm hàng, lấy dữ liệu, nhóm và sắp xếp.

Đây là ngoại lệ so với cách các phạm vi JOIN/ORDER BY/GROUP BY hoạt động trong truy vấn thông thường. Nếu truy vấn có `MATCH(...) AGAINST(... IN BOOLEAN MODE)`, hãy kiểm tra kết quả EXPLAIN thay vì suy luận tác dụng chỉ từ vị trí FOR clause.

## 8. Kết hợp nhiều index hint

MySQL cho phép chỉ định nhiều index hint trên cùng table reference. Các hint được thu thập theo loại và phạm vi.

Ví dụ:

~~~sql
SELECT
    order_id,
    customer_id,
    order_status,
    ordered_at
FROM sales_order_hint_demo AS o
USE INDEX FOR JOIN (idx_customer_status)
USE INDEX FOR ORDER BY (idx_ordered_at)
WHERE customer_id = 101
ORDER BY ordered_at DESC;
~~~

Ở đây:

- idx_customer_status được giới hạn cho việc tìm hàng và join.
- idx_ordered_at được giới hạn cho ORDER BY.

Một số quy tắc cú pháp quan trọng:

- Có thể nêu cùng một index nhiều lần; điều này không tự động gây lỗi.
- Các danh sách cùng loại và cùng phạm vi được hợp nhất.
- IGNORE INDEX được áp dụng sau USE INDEX hoặc FORCE INDEX.
- Không có FOR clause thì hint áp dụng cho mọi phạm vi.
- Trộn USE INDEX và FORCE INDEX trên cùng table reference là lỗi cú pháp theo quy tắc index hint.

Ví dụ sai:

~~~sql
SELECT *
FROM sales_order_hint_demo
USE INDEX FOR JOIN (idx_customer_status)
FORCE INDEX FOR JOIN (idx_ordered_at)
WHERE customer_id = 101;
~~~

Nếu cần thay đổi cường độ hint, hãy chọn một loại hint thống nhất cho table reference thay vì kết hợp USE và FORCE.

### 8.1. IGNORE được áp dụng sau USE hoặc FORCE

~~~sql
SELECT *
FROM sales_order_hint_demo
USE INDEX (idx_customer_status, idx_status)
IGNORE INDEX (idx_status)
WHERE customer_id = 101;
~~~

Danh sách cuối cùng còn idx_customer_status. idx_status đã bị loại bởi IGNORE INDEX.

### 8.2. Danh sách index phải có ý nghĩa với truy vấn

Việc liệt kê một index không làm index đó tự động hỗ trợ điều kiện không phù hợp. Ví dụ, index (customer_id, order_status) có thể hỗ trợ điều kiện customer_id hoặc customer_id kết hợp order_status theo leftmost prefix. Nó không tự nhiên trở thành access path tốt cho điều kiện chỉ lọc order_status.

Trước khi ép index, hãy kiểm tra định nghĩa bằng SHOW INDEX và đối chiếu thứ tự cột.

## 9. Optimizer index hints dạng comment từ MySQL 8.0.20

Từ MySQL 8.0.20, MySQL hỗ trợ nhóm optimizer hint ở cấp index. Nhóm này được thiết kế để thay thế dần FORCE INDEX và IGNORE INDEX tương ứng.

Các hint chính:

| Optimizer hint | Phạm vi | Tương đương index hint truyền thống |
|---|---|---|
| JOIN_INDEX | Tìm hàng và join | FORCE INDEX FOR JOIN |
| NO_JOIN_INDEX | Loại index khi tìm hàng/join | IGNORE INDEX FOR JOIN |
| ORDER_INDEX | Sắp xếp | FORCE INDEX FOR ORDER BY |
| NO_ORDER_INDEX | Loại index cho sắp xếp | IGNORE INDEX FOR ORDER BY |
| GROUP_INDEX | Grouping | FORCE INDEX FOR GROUP BY |
| NO_GROUP_INDEX | Loại index cho grouping | IGNORE INDEX FOR GROUP BY |
| INDEX | Tất cả phạm vi | FORCE INDEX |
| NO_INDEX | Loại index ở tất cả phạm vi | IGNORE INDEX |

Cú pháp tổng quát:

~~~sql
SELECT /*+ JOIN_INDEX(table_alias index_name) */
    ...
FROM table_name AS table_alias;
~~~

Optimizer hint phải đặt trong comment đặc biệt bắt đầu bằng /*+ và nằm ngay sau từ khóa câu lệnh hoặc ở đầu query block.

### 9.1. JOIN_INDEX và NO_JOIN_INDEX

JOIN_INDEX giới hạn index được dùng cho mọi access method trong phạm vi JOIN, chẳng hạn ref, range hoặc index_merge.

~~~sql
EXPLAIN
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id,
    o.customer_id,
    o.order_status
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

Loại một index khỏi phạm vi JOIN:

~~~sql
EXPLAIN
SELECT /*+ NO_JOIN_INDEX(o idx_status) */
    o.order_id,
    o.order_status
FROM sales_order_hint_demo AS o
WHERE o.order_status = 'PAID';
~~~

Tên o trong hint phải khớp alias của bảng trong query block.

### 9.2. ORDER_INDEX và GROUP_INDEX

ORDER_INDEX tác động đến index dùng để sắp xếp:

~~~sql
EXPLAIN
SELECT /*+ ORDER_INDEX(o idx_ordered_at) */
    o.order_id,
    o.ordered_at
FROM sales_order_hint_demo AS o
ORDER BY o.ordered_at DESC
LIMIT 5;
~~~

GROUP_INDEX tác động đến index scan cho GROUP BY:

~~~sql
EXPLAIN
SELECT /*+ GROUP_INDEX(o idx_status) */
    o.order_status,
    COUNT(*) AS order_count
FROM sales_order_hint_demo AS o
GROUP BY o.order_status;
~~~

Các hint này tương đương FORCE INDEX theo phạm vi tương ứng, không tương đương USE INDEX.

### 9.3. INDEX và NO_INDEX

INDEX là tổ hợp JOIN_INDEX, GROUP_INDEX và ORDER_INDEX. Nó tác động đến tất cả phạm vi.

~~~sql
EXPLAIN
SELECT /*+ INDEX(o idx_customer_status) */
    o.order_id,
    o.customer_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

NO_INDEX loại index khỏi mọi phạm vi:

~~~sql
EXPLAIN
SELECT /*+ NO_INDEX(o idx_status) */
    o.order_id,
    o.order_status
FROM sales_order_hint_demo AS o
WHERE o.order_status = 'PAID';
~~~

Đừng nhầm INDEX với USE INDEX. INDEX có ngữ nghĩa giống FORCE INDEX: table scan chỉ được chọn nếu không có cách dùng index được nêu để tìm hàng.

### 9.4. Vì sao optimizer hint mới không có USE INDEX tương đương trực tiếp?

JOIN_INDEX, ORDER_INDEX, GROUP_INDEX và INDEX có ngữ nghĩa giống FORCE INDEX. Các biến thể NO_* tương đương IGNORE INDEX.

Do đó, không có một optimizer hint duy nhất mang đúng ngữ nghĩa giới hạn tập index nhưng vẫn để table scan cạnh tranh như USE INDEX.

Để mô phỏng USE INDEX, cần loại các index khác bằng NO_* và để lại index mong muốn. Ví dụ, nếu muốn chỉ cho phép idx_ordered_at trong phạm vi ORDER BY, phải liệt kê các index còn lại cần loại:

~~~sql
SELECT /*+ NO_ORDER_INDEX(
    o PRIMARY,
    idx_customer_status,
    idx_status,
    idx_total_amount,
    idx_region_ordered
) */
    o.order_id,
    o.ordered_at
FROM sales_order_hint_demo AS o
ORDER BY o.ordered_at DESC;
~~~

Cách này cần cập nhật khi schema thêm hoặc xóa index. Nếu mục tiêu là đơn giản giới hạn danh sách ứng viên và cho phép table scan cạnh tranh, USE INDEX truyền thống diễn đạt trực tiếp hơn.

## 10. Query block, alias và vị trí optimizer hint

Optimizer hint có thể nhắm tới một bảng trong query block hiện tại hoặc một query block được đặt tên.

Ví dụ đơn giản:

~~~sql
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

Nếu bảng có alias o, dùng o trong hint. Dùng tên bảng gốc thay alias có thể làm hint không được áp dụng như mong muốn.

Với truy vấn lồng nhau, có thể đặt tên query block bằng QB_NAME:

~~~sql
SELECT /*+ QB_NAME(main_qb) */
    o.order_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id IN (
    SELECT /*+ QB_NAME(customer_qb) */
        x.customer_id
    FROM sales_order_hint_demo AS x
    WHERE x.region_code = 'NORTH'
);
~~~

Sau đó một hint có thể tham chiếu query block:

~~~sql
SELECT /*+ QB_NAME(main_qb)
           JOIN_INDEX(@main_qb o idx_customer_status) */
    o.order_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

Cú pháp query block hữu ích khi có subquery, derived table, CTE hoặc nhiều bảng cùng tên alias trong các query block khác nhau.

### 10.1. Vị trí comment hint

Với SELECT:

~~~sql
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

Với UPDATE:

~~~sql
UPDATE /*+ JOIN_INDEX(o idx_customer_status) */
    sales_order_hint_demo AS o
SET order_status = 'PAID'
WHERE o.customer_id = 101;
~~~

Optimizer hint phải nằm sau từ khóa câu lệnh tương ứng. Comment thông thường /* ... */ không có dấu cộng không được parser xem là optimizer hint.

Không đặt optimizer hint ở vị trí tùy ý giữa biểu thức SELECT hoặc sau WHERE rồi kỳ vọng nó có hiệu lực.

## 11. Thứ tự ưu tiên giữa index hint và optimizer hint

Index hint truyền thống và optimizer hint có thể cùng xuất hiện, nhưng không phải lúc nào chúng cũng có tác dụng độc lập.

Các quy tắc quan trọng trong MySQL 8.4:

- Nếu một statement có ít nhất một index-level optimizer hint (JOIN_INDEX, GROUP_INDEX, ORDER_INDEX, INDEX hoặc biến thể NO_*), các index hint truyền thống USE INDEX, FORCE INDEX và IGNORE INDEX trong cùng statement bị bỏ qua. Đây là quy tắc tương thích được nêu trong Release Notes MySQL 8.0.20.
- Trong nhóm optimizer hint, các index-level hint có ưu tiên cao hơn các optimizer hint khác, kể cả index-level optimizer hint khác; các hint còn lại chỉ tác động trên tập index được index-level hint cho phép.
- Khi không có index-level optimizer hint ghi đè, USE INDEX, FORCE INDEX và IGNORE INDEX có ưu tiên cao hơn INDEX_MERGE và NO_INDEX_MERGE optimizer hint.
- Hint không áp dụng được cho truy vấn có thể bị bỏ qua; việc viết hint không bảo đảm optimizer sẽ tạo được access path đó.

Không nên trộn nhiều cơ chế điều khiển chỉ để ép một kế hoạch. Nếu một câu truy vấn chứa nhiều hint mâu thuẫn, hãy xem SHOW WARNINGS và EXPLAIN để xác nhận hint nào được sử dụng; đặc biệt, đừng kỳ vọng index hint truyền thống vẫn có hiệu lực khi cùng statement đã có index-level optimizer hint.

## 12. Khác biệt cú pháp theo phiên bản MySQL

### 12.1. Trước MySQL 8.0.20

Các index hint truyền thống USE INDEX, FORCE INDEX và IGNORE INDEX đã có trong các phiên bản MySQL cũ, bao gồm MySQL 5.7 và các bản 8.0 trước 8.0.20.

Trong các phiên bản này, không dùng JOIN_INDEX, ORDER_INDEX, GROUP_INDEX hoặc INDEX optimizer hint vì nhóm index-level optimizer hint mới chưa được hỗ trợ.

### 12.2. MySQL 8.0.20

MySQL 8.0.20 bổ sung:

- JOIN_INDEX và NO_JOIN_INDEX.
- GROUP_INDEX và NO_GROUP_INDEX.
- ORDER_INDEX và NO_ORDER_INDEX.
- INDEX và NO_INDEX.

Các hint mới được thiết kế để thay thế FORCE INDEX và IGNORE INDEX tương ứng. Tài liệu MySQL 8.0.20 nói rằng các index hint truyền thống dự kiến sẽ bị deprecated trong một phiên bản tương lai và sau đó có thể bị loại bỏ.

Điểm quan trọng: 8.0.20 là mốc bổ sung optimizer hint mới, không phải mốc xóa cú pháp USE/FORCE/IGNORE INDEX.

### 12.3. MySQL 8.4 và 9.7

Tài liệu MySQL 8.4 và 9.7 vẫn mô tả và hỗ trợ cú pháp USE INDEX, FORCE INDEX và IGNORE INDEX. Cùng lúc, tài liệu khuyến nghị chuyển dần sang JOIN_INDEX, GROUP_INDEX, ORDER_INDEX, INDEX và các biến thể NO_*.

Không nên ghi rằng USE/FORCE/IGNORE INDEX đã bị loại bỏ trong 8.4 hoặc 9.7. Tài liệu hiện tại nói chúng được kỳ vọng sẽ deprecated trong một phiên bản tương lai, rồi có thể bị loại bỏ sau đó.

Nếu ứng dụng hỗ trợ nhiều phiên bản, cần kiểm tra phiên bản server nhỏ nhất trước khi đưa index-level optimizer hint mới vào SQL. Một câu SQL dùng JOIN_INDEX có thể không chạy trên server cũ hơn 8.0.20.

### 12.4. Bảng tóm tắt tương thích

| Phiên bản | USE/FORCE/IGNORE INDEX | JOIN_INDEX, ORDER_INDEX, GROUP_INDEX, INDEX |
|---|---|---|
| MySQL 5.7 | Có | Không |
| MySQL 8.0 trước 8.0.20 | Có | Chưa có nhóm hint mới |
| MySQL 8.0.20 trở lên | Có | Có |
| MySQL 8.4 | Có, vẫn được tài liệu hóa | Có, được khuyến nghị thay thế dần |
| MySQL 9.7 | Có, vẫn được tài liệu hóa | Có, được khuyến nghị thay thế dần |

Khi triển khai trên môi trường hỗn hợp, hãy chọn cú pháp tương thích với phiên bản thấp nhất hoặc tách câu SQL theo phiên bản server.

## 13. Các giới hạn theo loại câu lệnh

Index hint truyền thống:

- Dùng được trong SELECT.
- Dùng được trong UPDATE.
- Dùng được với cú pháp multi-table DELETE.
- Không dùng được với single-table DELETE theo cú pháp index hint truyền thống.

Ví dụ multi-table DELETE:

~~~sql
EXPLAIN DELETE o
FROM sales_order_hint_demo AS o
IGNORE INDEX FOR JOIN (idx_status)
JOIN customer_hint_demo AS c
    ON c.customer_id = o.customer_id
WHERE o.order_status = 'CANCELLED';
~~~

Câu lệnh này minh họa vị trí index hint trong multi-table DELETE và dùng EXPLAIN để kiểm tra kế hoạch mà chưa xóa hàng. Nếu bỏ EXPLAIN để thực thi DELETE, các đơn CANCELLED thuộc khách hàng có trong customer_hint_demo sẽ bị xóa; chỉ chạy trên database thực hành sau khi xác nhận phạm vi dữ liệu.

Index-level optimizer hint mới được tài liệu hóa là hỗ trợ cả single-table và multi-table DELETE. Vì vậy, nếu cần hint cho single-table DELETE, hãy kiểm tra khả năng tương thích của JOIN_INDEX/NO_JOIN_INDEX hoặc INDEX/NO_INDEX trên phiên bản mục tiêu.

## 14. Kiểm tra hint có được sử dụng hay không

Không được giả định hint có tác dụng chỉ vì câu SQL chạy thành công.

### 14.1. Dùng EXPLAIN

~~~sql
EXPLAIN
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id,
    o.customer_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

Kiểm tra:

- type: access type có thay đổi không?
- possible_keys: index nào được cân nhắc?
- key: index nào được chọn?
- key_len: bao nhiêu phần của index được dùng?
- rows: số hàng ước lượng thay đổi thế nào?
- Extra: có Using index, Using where hoặc Using filesort không?

Với TREE:

~~~sql
EXPLAIN FORMAT=TREE
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id,
    o.customer_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

### 14.2. Dùng SHOW WARNINGS

Có thể kiểm tra thông tin hint ngay sau EXPLAIN:

~~~sql
EXPLAIN
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;

SHOW WARNINGS;
~~~

Extended EXPLAIN output có thể cho biết optimizer hint nào được dùng. Hint bị bỏ qua không xuất hiện trong phần mở rộng này. Hint trùng hoặc xung đột có thể tạo warning.

Nếu hint không xuất hiện hoặc không làm thay đổi kế hoạch, kiểm tra:

- Tên bảng/alias trong hint có đúng không?
- Tên index có tồn tại không?
- Hint có hỗ trợ ở phiên bản server hiện tại không?
- Query block có đúng không?
- Index có áp dụng được cho điều kiện không?
- Một hint có ưu tiên cao hơn đang ghi đè hint khác không?

### 14.3. Dùng EXPLAIN ANALYZE để đo thực tế

EXPLAIN chỉ cho biết kế hoạch và ước lượng. Để đo thời gian và số hàng thực tế, dùng EXPLAIN ANALYZE trên SELECT có chi phí chấp nhận được:

~~~sql
EXPLAIN ANALYZE
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id,
    o.total_amount
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

So sánh actual rows, loops và thời gian trước/sau hint. Không dùng EXPLAIN ANALYZE một cách tùy tiện cho truy vấn nặng trên production vì lệnh thực sự chạy SELECT.

## 15. Thực hành so sánh USE, FORCE, IGNORE và optimizer hint

### Lab 1: Ghi nhận kế hoạch mặc định

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    order_status
FROM sales_order_hint_demo
WHERE customer_id = 101;
~~~

Ghi lại type, key, rows và Extra. Đây là baseline để so sánh.

### Lab 2: Giới hạn index bằng USE INDEX

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    order_status
FROM sales_order_hint_demo
USE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

So sánh với baseline. Xác định table scan còn được phép hay không.

### Lab 3: Ép cost của table scan bằng FORCE INDEX

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    order_status
FROM sales_order_hint_demo
FORCE INDEX (idx_customer_status)
WHERE customer_id = 101;
~~~

So sánh key và type với USE INDEX. Giải thích vì sao FORCE INDEX có thể làm optimizer chọn index ngay cả khi bảng nhỏ.

### Lab 4: Loại một index bằng IGNORE INDEX

~~~sql
EXPLAIN
SELECT
    order_id,
    order_status,
    total_amount
FROM sales_order_hint_demo
IGNORE INDEX (idx_status)
WHERE order_status = 'PAID';
~~~

Kiểm tra optimizer chọn index khác hay table scan.

### Lab 5: Chỉ điều khiển ORDER BY

~~~sql
EXPLAIN
SELECT
    order_id,
    ordered_at
FROM sales_order_hint_demo
USE INDEX FOR ORDER BY (idx_ordered_at)
ORDER BY ordered_at DESC
LIMIT 5;
~~~

Giải thích vì sao FOR ORDER BY không đồng nghĩa với việc ép index cho WHERE.

### Lab 6: Chỉ điều khiển GROUP BY

~~~sql
EXPLAIN
SELECT
    order_status,
    COUNT(*)
FROM sales_order_hint_demo
USE INDEX FOR GROUP BY (idx_status)
GROUP BY order_status;
~~~

Quan sát kế hoạch và Extra. Kiểm tra liệu index có giúp xử lý nhóm hiệu quả hơn không.

### Lab 7: Dùng optimizer hint mới

~~~sql
EXPLAIN
SELECT /*+ JOIN_INDEX(o idx_customer_status) */
    o.order_id,
    o.customer_id
FROM sales_order_hint_demo AS o
WHERE o.customer_id = 101;
~~~

So sánh với FORCE INDEX FOR JOIN.

### Lab 8: Loại index bằng NO_JOIN_INDEX

~~~sql
EXPLAIN
SELECT /*+ NO_JOIN_INDEX(o idx_status) */
    o.order_id,
    o.order_status
FROM sales_order_hint_demo AS o
WHERE o.order_status = 'PAID';
~~~

Xác định index bị loại và kế hoạch thay thế.

### Lab 9: Kiểm tra phiên bản

~~~sql
SELECT VERSION() AS mysql_version;
~~~

Chạy câu SQL dùng JOIN_INDEX trên MySQL 8.0.20 trở lên. Nếu cần hỗ trợ 8.0.19 hoặc cũ hơn, chuyển sang index hint truyền thống tương thích.

### Lab 10: So sánh thời gian thực tế

Chọn truy vấn có đủ dữ liệu đại diện. Đo baseline và kế hoạch có hint bằng EXPLAIN ANALYZE. Ghi lại actual rows, loops, thời gian và kết quả trả về. Chỉ giữ hint nếu cải thiện có thể lặp lại.

## 16. Các lỗi thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| USE INDEX bắt buộc phải dùng index | Table scan vẫn có thể được chọn | Dùng FORCE nếu có lý do rõ ràng để làm scan đắt hơn |
| FORCE INDEX luôn dùng index | Index không áp dụng được thì scan vẫn có thể xảy ra | Kiểm tra điều kiện và index definition |
| IGNORE INDEX chọn index thay thế | Nó chỉ loại index được nêu | Để optimizer chọn phần còn lại hoặc dùng hint khác |
| FOR JOIN điều khiển cả ORDER BY | Nó tác động đến tìm hàng và join | Dùng FOR ORDER BY riêng |
| Không ghi FOR thì chỉ áp dụng cho WHERE | Không có FOR áp dụng mọi phạm vi | Chỉ rõ phạm vi nếu cần |
| INDEX optimizer hint tương đương USE INDEX | INDEX tương đương FORCE INDEX | Dùng NO_* để mô phỏng việc loại các index không mong muốn |
| Có thể bỏ danh sách cho mọi loại hint | Chỉ USE INDEX cho phép danh sách rỗng | FORCE và IGNORE cần index_list |
| Hint dùng tên cột | Hint dùng tên index | Kiểm tra bằng SHOW INDEX |
| Alias không quan trọng | Optimizer hint phải tham chiếu đúng alias | Dùng alias hiện diện trong query block |
| Hints mới chạy trên mọi MySQL 8.0 | Nhóm index-level optimizer hint bắt đầu từ 8.0.20 | Kiểm tra phiên bản nhỏ nhất |
| Hint có hiệu lực vì câu SQL không lỗi | Hint có thể bị bỏ qua hoặc không áp dụng | Kiểm tra EXPLAIN và SHOW WARNINGS |
| Ép index luôn làm truy vấn nhanh hơn | Index có thể kém chọn lọc hoặc cần nhiều lookup | Đo với dữ liệu và tham số đại diện |

## 17. Quy trình đưa hint vào ứng dụng

Trước khi giữ một hint trong code:

1. Ghi nhận truy vấn gốc, tham số và phiên bản MySQL.
2. Chạy EXPLAIN và lưu kế hoạch baseline.
3. Xác nhận index được đề xuất tồn tại và phù hợp với thứ tự cột.
4. Thử USE INDEX, FORCE INDEX hoặc IGNORE INDEX với phạm vi nhỏ nhất cần thiết.
5. Nếu server từ 8.0.20 trở lên, cân nhắc optimizer index hint mới tương ứng.
6. Kiểm tra alias, query block và precedence.
7. Chạy EXPLAIN lại để xác nhận kế hoạch đã đổi đúng dự kiến.
8. Dùng EXPLAIN ANALYZE hoặc benchmark workload để đo actual rows và thời gian.
9. Kiểm tra nhiều giá trị tham số, kể cả giá trị phổ biến và hiếm.
10. Ghi chú lý do, phiên bản tối thiểu và điều kiện cần xem xét lại hint.
11. Theo dõi sau khi dữ liệu, index hoặc phiên bản MySQL thay đổi.

Sơ đồ quyết định:

~~~mermaid
flowchart TD
    A[Truy vấn có kế hoạch chưa phù hợp] --> B[EXPLAIN baseline]
    B --> C{Có index phù hợp?}
    C -->|Không| D[Thiết kế hoặc sửa index trước]
    C -->|Có| E{Muốn giới hạn tập index?}
    E -->|Có| F[USE INDEX]
    E -->|Muốn làm scan đắt hơn| G[FORCE INDEX]
    E -->|Muốn loại index| H[IGNORE INDEX]
    F --> I[EXPLAIN và đo]
    G --> I
    H --> I
    D --> I
    I --> J{MySQL từ 8.0.20?}
    J -->|Có| K[Cân nhắc JOIN_INDEX / ORDER_INDEX / GROUP_INDEX / INDEX]
    J -->|Không| L[Giữ cú pháp tương thích]
    K --> M[SHOW WARNINGS và EXPLAIN ANALYZE]
    L --> M
    M --> N[Chỉ giữ hint khi cải thiện ổn định]
~~~

## Kết luận

USE INDEX giới hạn tập index được cân nhắc nhưng vẫn cho phép table scan. FORCE INDEX cũng giới hạn tập index nhưng làm table scan bị đánh giá rất đắt. IGNORE INDEX loại các index được nêu khỏi lựa chọn. FOR JOIN, FOR ORDER BY và FOR GROUP BY giúp giới hạn tác động vào đúng giai đoạn của truy vấn.

Từ MySQL 8.0.20, các optimizer index hint JOIN_INDEX, ORDER_INDEX, GROUP_INDEX, INDEX và các biến thể NO_* cung cấp cách điều khiển mới. Chúng tương đương FORCE/IGNORE theo phạm vi, không tương đương trực tiếp USE INDEX. MySQL 8.4 và 9.7 vẫn hỗ trợ cú pháp truyền thống, nhưng tài liệu định hướng chuyển dần sang nhóm hint mới.

Hãy dùng hint như một công cụ kiểm chứng và kiểm soát có chủ đích. EXPLAIN xác nhận kế hoạch, SHOW WARNINGS giúp kiểm tra hint được nhận diện, còn EXPLAIN ANALYZE và benchmark xác nhận tác động thực tế. Một hint chỉ nên được giữ lại khi có bằng chứng rằng nó cải thiện workload ổn định qua dữ liệu và phiên bản mục tiêu.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Index Hints: https://dev.mysql.com/doc/refman/8.4/en/index-hints.html
- MySQL 8.4 Reference Manual — Optimizer Hints: https://dev.mysql.com/doc/refman/8.4/en/optimizer-hints.html
- MySQL 8.0 Reference Manual — Index Hints: https://dev.mysql.com/doc/refman/8.0/en/index-hints.html
- MySQL 8.0 Reference Manual — Optimizer Hints: https://dev.mysql.com/doc/refman/8.0/en/optimizer-hints.html
- MySQL 8.0.20 Release Notes: https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-20.html
- MySQL 9.7 Reference Manual — Index Hints: https://dev.mysql.com/doc/refman/9.7/en/index-hints.html
- MySQL 9.7 Reference Manual — Optimizer Hints: https://dev.mysql.com/doc/refman/9.7/en/optimizer-hints.html
- MySQL 8.4 Reference Manual — Invisible Indexes: https://dev.mysql.com/doc/refman/8.4/en/invisible-indexes.html

