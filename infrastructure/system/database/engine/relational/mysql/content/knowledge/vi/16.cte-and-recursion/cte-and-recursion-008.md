# Giới hạn cte_max_recursion_depth và kiểm soát chi phí

CTE đệ quy giúp MySQL xử lý dữ liệu có quan hệ lặp lại như cây phòng ban, danh mục cha-con, sơ đồ phụ thuộc, đồ thị và chuỗi ngày. Tuy nhiên, một truy vấn đệ quy có thể chạy quá sâu, lặp vô hạn do chu trình hoặc tạo ra số hàng tăng rất nhanh khi mỗi nút có nhiều nút con. MySQL cung cấp biến `cte_max_recursion_depth` để giới hạn số vòng đệ quy, nhưng giới hạn độ sâu không đồng nghĩa giới hạn tổng số hàng hoặc tổng chi phí truy vấn.

Trong module `DATABASE_MYSQL`, cần kết hợp giới hạn của server với điều kiện dừng ngay trong CTE, kiểm soát chu trình, giới hạn số hàng khi phiên bản hỗ trợ, timeout và kiểm tra kế hoạch thực thi. Mục tiêu là để truy vấn có giới hạn rõ ràng, có thể dự đoán và có cách xác minh khi dữ liệu phát triển.

## 1. Cấu trúc của recursive CTE

Recursive CTE có hai phần:

- **Anchor member:** truy vấn khởi đầu, tạo ra hàng hoặc các hàng đầu tiên.
- **Recursive member:** truy vấn tham chiếu lại chính CTE để tạo lớp dữ liệu tiếp theo.

Hai phần được nối bằng `UNION ALL` hoặc `UNION DISTINCT`. MySQL lặp recursive member trên tập hàng vừa được tạo cho đến khi vòng lặp không sinh thêm hàng hoặc chạm giới hạn.

Ví dụ tạo dãy số từ 1 đến 5:

```sql
WITH RECURSIVE number_series (n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM number_series
    WHERE n < 5
)
SELECT n
FROM number_series
ORDER BY n;
```

Anchor tạo số 1. Mỗi vòng recursive member tạo số tiếp theo; khi `n = 5`, điều kiện `n < 5` không còn đúng và truy vấn dừng. Kết quả có năm hàng.

Một truy vấn đệ quy cần có điều kiện dừng được thiết kế có chủ đích. Nếu recursive member luôn sinh hàng mới mà không có điều kiện kết thúc, truy vấn chỉ dừng khi đạt giới hạn recursion của server hoặc giới hạn tài nguyên khác.

## 2. Phân biệt độ sâu với số hàng

Độ sâu là số cấp hoặc số vòng lặp mà truy vấn đi qua. Số hàng là tổng số kết quả được sinh ra ở mọi cấp. Hai đại lượng này khác nhau.

Với một chuỗi tuyến tính, mỗi vòng chỉ sinh một hàng:

```text
1 -> 2 -> 3 -> 4 -> 5
```

Độ sâu 5 chỉ tạo khoảng 5 hàng. Nhưng với cây có hệ số phân nhánh lớn:

```text
             Root
       /      |      \
      A       B       C
    / | \   / | \   / | \
   ...     ...     ...
```

mỗi cấp có thể sinh nhiều hàng. Nếu mỗi nút có trung bình `b` nút con và đi sâu `d` cấp, số hàng gần đúng có thể là:

\[
N = 1 + b + b^2 + \dots + b^d
\]

Ví dụ, với `b = 20` và `d = 4`, số hàng lý thuyết đã là 168.421. Truy vấn chỉ đi bốn cấp nhưng có thể tạo lượng dữ liệu lớn.

Vì vậy, `cte_max_recursion_depth` chỉ giới hạn chiều sâu/vòng lặp. Nó không đặt trần trực tiếp cho tổng số hàng được tạo ở mỗi vòng. Muốn kiểm soát chi phí cần thêm giới hạn theo nghiệp vụ và theo số hàng.

## 3. `cte_max_recursion_depth` là gì?

`cte_max_recursion_depth` là system variable của MySQL dùng để giới hạn số vòng đệ quy của recursive CTE. Trong MySQL 8.0, giá trị mặc định là `1000`. Nếu truy vấn vượt quá giới hạn, MySQL hủy truy vấn và trả lỗi thay vì tiếp tục đệ quy không giới hạn.

Kiểm tra giá trị:

```sql
SELECT
    @@GLOBAL.cte_max_recursion_depth AS global_limit,
    @@SESSION.cte_max_recursion_depth AS session_limit;

SHOW VARIABLES LIKE 'cte_max_recursion_depth';
```

Biến có phạm vi GLOBAL và SESSION, có thể thay đổi động. Thay đổi SESSION chỉ ảnh hưởng connection hiện tại; thay đổi GLOBAL là giá trị mặc định cho các session mới và không tự thay đổi session đã mở.

### Đặt giới hạn cho session hiện tại

Nếu một tác vụ hợp lệ cần đi sâu hơn mặc định, có thể tăng giới hạn trong connection dành riêng cho tác vụ:

```sql
SET SESSION cte_max_recursion_depth = 2000;

SELECT @@SESSION.cte_max_recursion_depth;
```

Chỉ tăng sau khi đã xác minh dữ liệu, điều kiện dừng và chi phí. Tăng từ 1.000 lên 100.000 không sửa được chu trình sai hoặc truy vấn có fan-out quá lớn; nó chỉ cho truy vấn tiếp tục lâu hơn trước khi chạm giới hạn.

### Đặt giới hạn GLOBAL

Tài khoản có quyền quản trị phù hợp có thể đặt giá trị global:

```sql
SET GLOBAL cte_max_recursion_depth = 1500;
```

Giá trị này áp dụng làm mặc định cho session mở sau đó. Kiểm tra lại trên connection mới và kiểm tra session đang chạy riêng. Với production, nên quản lý giá trị qua quy trình cấu hình có version control và đánh giá tác động trước khi thay đổi toàn server.

### Khôi phục giá trị session

Trong script kiểm thử, lưu giá trị cũ và khôi phục sau khi chạy:

```sql
SET @saved_recursion_depth = @@SESSION.cte_max_recursion_depth;

SET SESSION cte_max_recursion_depth = 2000;

-- Chạy recursive CTE tại đây.

SET SESSION cte_max_recursion_depth = @saved_recursion_depth;
```

Nếu dùng connection pool, không để một request tăng giới hạn rồi trả connection về pool mà không reset. Session variable có thể còn hiệu lực cho request tiếp theo nếu pool không khôi phục trạng thái đó.

## 4. Hiểu đúng giới hạn và lỗi vượt recursion depth

Khi recursive CTE vượt `cte_max_recursion_depth`, MySQL dừng statement và báo lỗi recursion depth. Đây là cơ chế bảo vệ, không phải thông báo rằng dữ liệu chắc chắn có chu trình. Truy vấn có thể vượt giới hạn vì:

- Dữ liệu có chiều sâu hợp lệ lớn hơn cấu hình.
- Điều kiện dừng bị thiếu hoặc sai.
- Khóa nối recursive member không đúng, khiến truy vấn đi qua nhiều hàng ngoài dự kiến.
- Dữ liệu chứa chu trình.
- Anchor bắt đầu từ phạm vi quá rộng và truy vấn đi qua nhiều cấp.

Khi gặp lỗi, không nên lập tức tăng giới hạn. Trước tiên hãy xác định độ sâu tối đa thực tế, số hàng ở từng cấp và khả năng tồn tại chu trình.

Để quan sát độ sâu, thêm cột `depth` vào CTE:

```sql
WITH RECURSIVE number_series (n, depth) AS (
    SELECT 1, 0

    UNION ALL

    SELECT n + 1, depth + 1
    FROM number_series
    WHERE n < 10
)
SELECT MAX(depth) AS deepest_level,
       COUNT(*) AS generated_rows
FROM number_series;
```

Với dãy tuyến tính này, `depth` bắt đầu từ 0 và tăng một ở mỗi vòng. Cách đánh số này giúp tránh nhầm lẫn giữa giá trị bắt đầu, số hàng và số vòng lặp. Trong cây, anchor có depth 0; con trực tiếp có depth 1.

## 5. Giới hạn độ sâu ngay trong recursive member

Không nên chỉ dựa vào system variable. Hãy đặt một giới hạn theo nghiệp vụ trong chính truy vấn:

```sql
WITH RECURSIVE number_series (n, depth) AS (
    SELECT 1, 0

    UNION ALL

    SELECT n + 1, depth + 1
    FROM number_series
    WHERE n < 100
      AND depth < 99
)
SELECT n, depth
FROM number_series
ORDER BY depth;
```

Điều kiện `depth < 99` bảo đảm không sinh cấp tiếp theo sau độ sâu 99. `n < 100` là điều kiện nghiệp vụ của dãy số; hai điều kiện phục vụ mục đích khác nhau. Trong truy vấn thật, nên giữ điều kiện kết thúc theo dữ liệu và thêm điều kiện giới hạn an toàn.

Nếu anchor bắt đầu ở depth 0 và điều kiện là `depth < 20`, hàng con cuối cùng có depth 20. Hãy thống nhất cách đếm cấp trong ứng dụng và trong báo cáo để không có lỗi off-by-one.

## 6. Kiểm soát cây phân cấp bằng depth, anchor và index

Ví dụ cây tổ chức:

```sql
CREATE TABLE org_units (
    id BIGINT UNSIGNED NOT NULL,
    parent_id BIGINT UNSIGNED NULL,
    unit_name VARCHAR(100) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    KEY idx_org_units_parent_id (parent_id)
) ENGINE=InnoDB;

INSERT INTO org_units (id, parent_id, unit_name)
VALUES
    (1, NULL, 'Head Office'),
    (2, 1, 'Engineering'),
    (3, 1, 'Operations'),
    (4, 2, 'Platform'),
    (5, 2, 'Application'),
    (6, 4, 'Database');
```

Truy vấn lấy cây bắt đầu từ đơn vị 1, giới hạn tối đa 20 cấp:

```sql
WITH RECURSIVE org_tree (id, parent_id, unit_name, depth) AS (
    SELECT id, parent_id, unit_name, 0
    FROM org_units
    WHERE id = 1

    UNION ALL

    SELECT child.id,
           child.parent_id,
           child.unit_name,
           tree.depth + 1
    FROM org_units AS child
    JOIN org_tree AS tree
      ON child.parent_id = tree.id
    WHERE tree.depth < 20
)
SELECT id, parent_id, unit_name, depth
FROM org_tree
ORDER BY depth, parent_id, id;
```

Các điểm kiểm soát:

- Anchor giới hạn đúng root bằng `WHERE id = 1`.
- Recursive member chỉ tìm các con của nút hiện tại.
- `idx_org_units_parent_id` hỗ trợ tra cứu các hàng con theo `parent_id`.
- `tree.depth < 20` chặn độ sâu nghiệp vụ.
- Truy vấn chỉ chọn các cột cần thiết, tránh mang payload không dùng qua mọi vòng lặp.

Nếu bỏ điều kiện root và bắt đầu từ toàn bộ bảng, số nhánh được mở rộng có thể lớn hơn nhiều. Anchor càng rộng, chi phí ban đầu càng cao.

## 7. Phát hiện và ngăn chu trình trong cây/đồ thị

Một cây hợp lệ không có chu trình. Nhưng dữ liệu quan hệ có thể bị lỗi, ví dụ:

```text
1 -> 2 -> 4 -> 1
```

Nếu recursive CTE dùng `UNION ALL` và chỉ nối theo parent/child, truy vấn có thể đi vòng lặp cho đến khi chạm `cte_max_recursion_depth`. Điều kiện depth chỉ giới hạn thiệt hại; nó không giải thích hoặc sửa dữ liệu chu trình.

### Theo dõi đường đi bằng path

Với ID số nguyên, có thể lưu đường đi dưới dạng chuỗi có dấu phân cách:

```sql
WITH RECURSIVE org_tree (id, parent_id, unit_name, depth, path) AS (
    SELECT
        id,
        parent_id,
        unit_name,
        0,
        CAST(CONCAT('/', id, '/') AS CHAR(2048))
    FROM org_units
    WHERE id = 1

    UNION ALL

    SELECT
        child.id,
        child.parent_id,
        child.unit_name,
        tree.depth + 1,
        CONCAT(tree.path, child.id, '/')
    FROM org_units AS child
    JOIN org_tree AS tree
      ON child.parent_id = tree.id
    WHERE tree.depth < 20
      AND LOCATE(CONCAT('/', child.id, '/'), tree.path) = 0
)
SELECT id, parent_id, unit_name, depth, path
FROM org_tree
ORDER BY path;
```

`LOCATE()` kiểm tra ID con đã xuất hiện trong đường đi hiện tại hay chưa. Dấu `/` tránh nhầm ID `12` với ID `112`. Anchor CAST `path` thành `CHAR(2048)` vì kiểu và độ dài cột recursive CTE được xác định từ phần anchor; phải cấp đủ độ dài cho đường đi lớn nhất dự kiến.

Mẫu này giả định ID là số hoặc chuỗi không chứa dấu phân cách `/`. Nếu ID có thể chứa ký tự phân cách, cần encode/escape trước khi nối path hoặc dùng cấu trúc biểu diễn khác.

### Phát hiện chu trình và phân biệt đường đi với nút

Path ở trên ngăn một nút xuất hiện lặp lại trong cùng một đường đi. Nhưng nếu dữ liệu là DAG và cùng một nút có thể được tiếp cận qua hai nhánh khác nhau, nút đó vẫn có thể xuất hiện nhiều lần theo hai path hợp lệ. Điều này khác với chu trình.

Nếu mục tiêu chỉ là tìm tập nút có thể đi tới, không cần depth hoặc path, có thể dùng `UNION DISTINCT` và chỉ chọn ID:

```sql
CREATE TABLE graph_edges (
    from_node_id BIGINT UNSIGNED NOT NULL,
    to_node_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (from_node_id, to_node_id)
) ENGINE=InnoDB;

INSERT INTO graph_edges (from_node_id, to_node_id)
VALUES (1, 2), (2, 3), (3, 1), (2, 4);
```

Fixture có chu trình `1 -> 2 -> 3 -> 1` và một nhánh tới nút 4. Truy vấn sau tìm tập node reachable từ node 1:

```sql
WITH RECURSIVE reachable (node_id) AS (
    SELECT CAST(1 AS UNSIGNED)

    UNION DISTINCT

    SELECT edge.to_node_id
    FROM graph_edges AS edge
    JOIN reachable AS current_node
      ON edge.from_node_id = current_node.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
```

`UNION DISTINCT` loại các hàng trùng theo toàn bộ danh sách cột CTE. Vì CTE chỉ chứa `node_id`, mỗi node chỉ được đưa vào tập một lần, giúp truy vấn kết thúc trên đồ thị hữu hạn ngay cả khi có chu trình. Nếu thêm `depth` hoặc `path`, cùng một node ở depth/path khác nhau sẽ là hàng khác và không còn được loại chỉ dựa trên node ID.

Không dùng `UNION DISTINCT` như giải pháp chung cho mọi cây. Việc loại trùng có chi phí lưu và so sánh hàng; đồng thời có thể làm mất thông tin đường đi nếu báo cáo cần phân biệt nhiều đường hợp lệ.

## 8. Giới hạn số hàng: depth không đủ

Một CTE có thể chỉ đi ba cấp nhưng mỗi cấp sinh hàng chục nghìn con. Để bảo vệ tài nguyên, cần nghĩ riêng về:

- Số hàng được sinh ở mỗi vòng.
- Tổng số hàng của CTE.
- Số byte của các cột được mang qua đệ quy.
- Chi phí JOIN để tìm nút kế tiếp.
- Chi phí loại trùng, sắp xếp và materialize kết quả.

### LIMIT trong recursive member trên MySQL 8.0.19+

Từ MySQL 8.0.19, recursive member có thể chứa `LIMIT` để giới hạn số hàng recursive CTE tạo ra:

```sql
SET @saved_recursion_depth = @@SESSION.cte_max_recursion_depth;
SET SESSION cte_max_recursion_depth = 20000;

WITH RECURSIVE number_series (n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM number_series
    LIMIT 10000
)
SELECT n
FROM number_series;

SET SESSION cte_max_recursion_depth = @saved_recursion_depth;
```

Trong ví dụ, recursion depth được nâng cao hơn row cap để `LIMIT` là lớp chặn đang được minh họa; script khôi phục giá trị cũ sau truy vấn. Đây là chặn số hàng được tạo, hữu ích khi cần bảo vệ trước trường hợp truy vấn không dừng. Hãy xác minh phiên bản trước khi dùng; MySQL cũ hơn 8.0.19 không hỗ trợ `LIMIT` ở recursive member.

Giới hạn số hàng không thay thế điều kiện dừng nghiệp vụ. Ví dụ dãy số nên dừng theo `n < 100`; `LIMIT` chỉ là lớp bảo vệ phụ. Nếu chạm LIMIT, kết quả có thể bị cắt cụt và không phải kết quả đầy đủ. Ứng dụng cần biết giới hạn có thể đã được kích hoạt để không coi kết quả một phần là toàn bộ dữ liệu.

### Vì sao LIMIT ở truy vấn ngoài không luôn là hàng rào an toàn?

Ví dụ:

```sql
SET @saved_recursion_depth = @@SESSION.cte_max_recursion_depth;
SET SESSION cte_max_recursion_depth = 20000;

WITH RECURSIVE number_series (n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1 FROM number_series
    WHERE n < 10000
)
SELECT n
FROM number_series
ORDER BY n DESC
LIMIT 100;

SET SESSION cte_max_recursion_depth = @saved_recursion_depth;
```

Trong ví dụ, `ORDER BY n DESC` cần sắp xếp kết quả trước khi lấy 100 hàng cuối, nên server phải tạo và xử lý tập kết quả lớn hơn 100. Không nên dựa vào LIMIT ngoài để bảo đảm recursive member chỉ tạo 100 hàng. Khi có `ORDER BY`, aggregate, join hoặc cách thực thi cần materialize, server có thể phải tạo nhiều hoặc toàn bộ kết quả trước khi áp dụng LIMIT. Dùng giới hạn trong recursive member (nếu phiên bản hỗ trợ), điều kiện dừng rõ ràng và timeout để bảo vệ truy vấn.

## 9. Giới hạn thời gian thực thi

`cte_max_recursion_depth` và giới hạn hàng không kiểm soát trực tiếp thời gian chạy. Một truy vấn có độ sâu nhỏ vẫn có thể chậm nếu mỗi vòng JOIN quét bảng lớn hoặc xử lý nhiều cột.

MySQL hỗ trợ `max_execution_time` cho các câu SELECT chỉ đọc, tính bằng mili giây. Có thể đặt ở session:

```sql
SET SESSION max_execution_time = 3000;
```

Hoặc dùng optimizer hint cho một SELECT:

```sql
WITH RECURSIVE number_series (n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM number_series
    WHERE n < 1000000
)
SELECT /*+ MAX_EXECUTION_TIME(3000) */ n
FROM number_series;
```

Hint yêu cầu server dừng câu SELECT nếu vượt thời gian cho phép. `3000` là 3.000 mili giây. Timeout là lớp bảo vệ tài nguyên, không phải cách sửa truy vấn sai. Khi timeout xảy ra, ghi nhận query, thời gian, tham số, số hàng và kế hoạch thực thi để điều tra.

`max_execution_time` mặc định bằng 0 nghĩa là không áp dụng giới hạn theo biến này. Phạm vi và khả năng áp dụng cần được kiểm tra theo phiên bản; nó không phải timeout chung cho mọi loại statement.

## 10. Kiểm soát chi phí bằng cách thu hẹp dữ liệu

Một recursive CTE hiệu quả thường bắt đầu từ một tập anchor nhỏ và chỉ mang các cột cần thiết qua mỗi vòng:

1. Chọn root cụ thể hoặc một tập root có giới hạn.
2. Lọc tenant, trạng thái hoặc phạm vi dữ liệu ngay tại anchor nếu đúng ngữ nghĩa.
3. Đặt điều kiện trên bảng con trong recursive member để tránh mở rộng nhánh không cần thiết.
4. Chọn ID, parent ID, depth và các cột báo cáo thực sự cần; không dùng `SELECT *`.
5. Tạo index trên cột dùng để tìm hàng kế tiếp.
6. Giới hạn depth và số hàng theo yêu cầu nghiệp vụ.
7. Chỉ sắp xếp ở truy vấn ngoài cùng nếu cần thứ tự hiển thị.

Ví dụ chỉ duyệt các đơn vị đang hoạt động:

```sql
WITH RECURSIVE active_tree (id, parent_id, unit_name, depth) AS (
    SELECT id, parent_id, unit_name, 0
    FROM org_units
    WHERE id = 1
      AND is_active = 1

    UNION ALL

    SELECT child.id,
           child.parent_id,
           child.unit_name,
           parent.depth + 1
    FROM org_units AS child
    JOIN active_tree AS parent
      ON child.parent_id = parent.id
    WHERE child.is_active = 1
      AND parent.depth < 15
)
SELECT id, parent_id, unit_name, depth
FROM active_tree;
```

Nếu truy vấn thường lọc theo `is_active` và tìm con theo `parent_id`, hãy đánh giá index ghép `(parent_id, is_active)` thay vì tạo nhiều index rời rạc một cách máy móc. Chọn index dựa trên điều kiện thực tế và `EXPLAIN`.

## 11. Index cho recursive member

Với mô hình adjacency list, recursive member thường có điều kiện:

```sql
ON child.parent_id = parent.id
```

Index trên `parent_id` giúp MySQL tìm các hàng con thay vì quét toàn bảng ở mỗi vòng. Với schema đa tenant có thêm cột `tenant_id`, nếu điều kiện còn phải giới hạn tenant:

```sql
ON child.tenant_id = parent.tenant_id
AND child.parent_id = parent.id
```

index ghép có thể là:

```sql
CREATE INDEX idx_org_tenant_parent
ON org_units (tenant_id, parent_id);
```

Thứ tự cột index cần khớp với điều kiện tra cứu và các truy vấn khác. Nếu dữ liệu nhiều tenant, lọc tenant ngay từ anchor và giữ điều kiện tenant trong recursive join để tránh nối nhầm giữa các tenant.

Không chỉ xem anchor có dùng primary key hay không; phần tốn chi phí thường lặp lại ở recursive member. Hãy kiểm tra access path cho cả bảng con và số hàng ước lượng mỗi lần lặp.

## 12. Dùng EXPLAIN và EXPLAIN ANALYZE

`EXPLAIN` cho biết kế hoạch mà optimizer dự kiến sử dụng. Với recursive CTE, cần quan sát phần recursive union/iteration, bảng được truy cập trong recursive member, index được chọn và số hàng ước lượng.

```sql
EXPLAIN
WITH RECURSIVE org_tree (id, parent_id, unit_name, depth) AS (
    SELECT id, parent_id, unit_name, 0
    FROM org_units
    WHERE id = 1

    UNION ALL

    SELECT child.id,
           child.parent_id,
           child.unit_name,
           tree.depth + 1
    FROM org_units AS child
    JOIN org_tree AS tree
      ON child.parent_id = tree.id
    WHERE tree.depth < 20
)
SELECT id, parent_id, unit_name, depth
FROM org_tree;
```

Trên MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` thực thi truy vấn và báo số liệu thực tế của các iterator:

```sql
EXPLAIN ANALYZE
WITH RECURSIVE org_tree (id, parent_id, unit_name, depth) AS (
    SELECT id, parent_id, unit_name, 0
    FROM org_units
    WHERE id = 1

    UNION ALL

    SELECT child.id,
           child.parent_id,
           child.unit_name,
           tree.depth + 1
    FROM org_units AS child
    JOIN org_tree AS tree
      ON child.parent_id = tree.id
    WHERE tree.depth < 20
)
SELECT id, parent_id, unit_name, depth
FROM org_tree;
```

`EXPLAIN ANALYZE` chạy truy vấn thật, vì vậy có thể tiêu tốn CPU, I/O và bộ nhớ như truy vấn gốc. Dùng trên staging hoặc tập dữ liệu giới hạn khi chưa biết chi phí.

Các dấu hiệu cần chú ý:

- Table scan lặp lại trên bảng lớn trong recursive member.
- Số hàng thực tế mỗi vòng cao hơn nhiều so với dự đoán.
- Số vòng lặp lớn hơn dự kiến.
- Temporary table hoặc materialization lớn.
- Thời gian tăng mạnh theo độ sâu hoặc số root.
- Chênh lệch lớn giữa estimated rows và actual rows.

## 13. Materialization và bộ nhớ tạm

Recursive CTE của MySQL được materialize để giữ kết quả phục vụ các vòng lặp. Khi kết quả lớn, server có thể cần vùng nhớ tạm và có thể sử dụng temporary storage trên đĩa tùy kích thước và cấu hình. Điều này làm cho việc chọn cột và giới hạn số hàng đặc biệt quan trọng.

Không đưa các cột BLOB/TEXT lớn, JSON payload hoặc mô tả dài vào CTE nếu recursive member chỉ cần ID để tìm con. Có thể chỉ mang khóa và depth trong CTE, sau đó JOIN lại bảng gốc ở truy vấn cuối để lấy nội dung hiển thị.

Ví dụ chỉ đệ quy qua ID:

```sql
WITH RECURSIVE descendants (id, depth) AS (
    SELECT id, 0
    FROM org_units
    WHERE id = 1

    UNION ALL

    SELECT child.id, parent.depth + 1
    FROM org_units AS child
    JOIN descendants AS parent
      ON child.parent_id = parent.id
    WHERE parent.depth < 20
)
SELECT unit.id,
       unit.parent_id,
       unit.unit_name,
       descendants.depth
FROM descendants
JOIN org_units AS unit
  ON unit.id = descendants.id;
```

CTE chỉ giữ ID và depth; tên đơn vị được lấy ở bước cuối. Với dữ liệu lớn, giảm kích thước hàng materialize có thể giảm chi phí đáng kể.

## 14. Giới hạn phiên bản và cú pháp liên quan

Các mốc phiên bản cần nhớ:

| Tính năng | Phiên bản MySQL |
|---|---|
| Recursive CTE | MySQL 8.0.1 trở lên. |
| `cte_max_recursion_depth` | Có trong MySQL 8.0; mặc định 1000. |
| `EXPLAIN ANALYZE` | MySQL 8.0.18 trở lên. |
| `LIMIT` trong recursive member | MySQL 8.0.19 trở lên. |

Trước khi triển khai truy vấn, kiểm tra phiên bản:

```sql
SELECT VERSION();
```

Nếu hệ thống chạy MySQL 5.7 hoặc cũ hơn, recursive CTE không được hỗ trợ. Cần dùng stored procedure có vòng lặp, bảng tạm hoặc xử lý cây ở ứng dụng. Nếu triển khai trên nhiều phiên bản 8.0 khác nhau, tránh dùng `LIMIT` trong recursive member hoặc tính năng mới hơn khi có node chưa được nâng cấp.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Tăng `cte_max_recursion_depth` ngay khi gặp lỗi | Truy vấn sai hoặc có chu trình chạy lâu hơn | Kiểm tra điều kiện dừng, cycle và số hàng từng cấp trước. |
| Nghĩ depth limit là row limit | Một vài cấp có thể sinh hàng triệu kết quả | Thêm giới hạn số hàng và kiểm soát fan-out. |
| Bỏ điều kiện dừng trong recursive member | Truy vấn tiếp tục tới giới hạn server | Thiết kế predicate dừng rõ ràng theo dữ liệu. |
| Chỉ dùng depth để xử lý cycle | Chu trình vẫn được duyệt lặp cho tới khi chạm giới hạn | Dùng path-based cycle detection hoặc `UNION DISTINCT` trên tập ID. |
| Dùng `UNION DISTINCT` nhưng vẫn chọn depth/path | Cùng node ở depth/path khác nhau không bị loại | Hiểu DISTINCT áp dụng trên toàn bộ hàng CTE; chỉ chọn ID nếu mục tiêu là tập node. |
| Anchor quá rộng | Mở rộng quá nhiều cây ngay từ đầu | Chọn root/tenant/phạm vi cụ thể. |
| Recursive member thiếu index trên parent key | Quét bảng lặp lại qua từng vòng | Tạo và kiểm tra index phù hợp. |
| Dùng `SELECT *` trong CTE | Tăng kích thước dữ liệu materialize | Chỉ mang cột cần thiết qua đệ quy. |
| Chỉ đặt LIMIT ở SELECT ngoài | Server có thể phải tạo nhiều kết quả trước khi cắt | Dùng predicate, recursive LIMIT nếu được hỗ trợ và timeout. |
| Không reset session variable trong connection pool | Request sau kế thừa giới hạn hoặc trạng thái khác | Khôi phục session state hoặc khởi tạo connection có kiểm soát. |
| Dùng EXPLAIN ANALYZE trên truy vấn chưa giới hạn ở production | Chính thao tác kiểm tra có thể tiêu tốn tài nguyên lớn | Thử trên staging hoặc dữ liệu giới hạn. |

## 16. Quy trình kiểm soát chi phí trước khi chạy production

Trước khi đưa recursive CTE vào tác vụ báo cáo hoặc API, hãy kiểm tra theo thứ tự:

1. **Xác định mục tiêu:** cần toàn bộ hậu duệ, đường đi, tập nút có thể tới hay chỉ một cấp con?
2. **Xác định anchor:** root, tenant và trạng thái nào được phép tham gia?
3. **Định nghĩa depth:** anchor là cấp 0 hay cấp 1; độ sâu nghiệp vụ tối đa là bao nhiêu?
4. **Định nghĩa điều kiện dừng:** khi nào recursive member không được sinh thêm hàng?
5. **Kiểm tra cycle:** dữ liệu có bảo đảm là cây hay có thể là đồ thị tổng quát?
6. **Đánh giá fan-out:** số con trung bình và lớn nhất của một nút là bao nhiêu?
7. **Đặt row/time budget:** giới hạn số hàng, thời gian và số cấp phù hợp.
8. **Tạo index:** index trên cột nối recursive và cột lọc.
9. **Đo kế hoạch:** `EXPLAIN`, sau đó `EXPLAIN ANALYZE` trên môi trường an toàn.
10. **Kiểm tra kết quả:** số hàng, depth lớn nhất, node lặp và trường hợp dữ liệu lỗi.
11. **Quản lý session:** đặt và khôi phục `cte_max_recursion_depth`, `max_execution_time` qua connection pool.
12. **Theo dõi sau triển khai:** thời gian chạy, số hàng, timeout, lỗi recursion depth và tăng trưởng dữ liệu.

Một truy vấn hoàn tất mà không lỗi chưa chắc đã đúng nghiệp vụ. Nếu chạm row cap và trả kết quả một phần, ứng dụng cần báo rõ trạng thái bị giới hạn thay vì hiển thị như kết quả đầy đủ.

## 17. Bài tập thực hành

### Bài tập A — Quan sát giới hạn recursion

1. Kiểm tra `@@SESSION.cte_max_recursion_depth`.
2. Chạy dãy số có 10 phần tử.
3. Chạy truy vấn có độ sâu vượt một giới hạn session nhỏ mà bạn đặt trong connection thử nghiệm.
4. Ghi lại lỗi và giá trị giới hạn.
5. Tăng giới hạn có chủ đích rồi chạy lại, sau đó khôi phục giá trị cũ.

### Bài tập B — Đo depth và fan-out

1. Tạo cây có ít nhất ba cấp và nhiều nút con.
2. Thêm `depth` vào recursive CTE.
3. Thống kê số hàng theo depth bằng truy vấn ngoài.
4. Tăng số con mỗi nút và quan sát tốc độ tăng số hàng.
5. Giải thích vì sao giới hạn depth không đủ kiểm soát tổng số hàng.

### Bài tập C — Phát hiện chu trình

1. Tạo quan hệ cha-con có một chu trình thử nghiệm.
2. Chạy truy vấn `UNION ALL` có depth cap nhỏ.
3. Bổ sung path và `LOCATE()` để ngăn lặp node trong cùng đường đi.
4. Chạy truy vấn reachability chỉ chọn ID với `UNION DISTINCT`.
5. So sánh ngữ nghĩa path traversal với tập node reachable.

### Bài tập D — Giới hạn số hàng và thời gian

1. Trên MySQL 8.0.19+, thử `LIMIT` trong recursive member.
2. So sánh với chỉ dùng LIMIT ở SELECT ngoài.
3. Đặt `max_execution_time` hoặc hint `MAX_EXECUTION_TIME`.
4. Quan sát cách truy vấn bị giới hạn và xác định kết quả có đầy đủ không.
5. Viết quy tắc ứng dụng khi row cap hoặc timeout bị kích hoạt.

### Bài tập E — Đọc kế hoạch và tối ưu

1. Chạy `EXPLAIN` cho truy vấn duyệt cây.
2. Bỏ index `parent_id` trong schema thử nghiệm và so sánh kế hoạch.
3. Tạo lại index và chạy `EXPLAIN ANALYZE`.
4. So sánh việc mang `SELECT *` với chỉ mang ID/depth.
5. Đề xuất budget depth, rows và thời gian dựa trên số liệu đo.

Bạn hoàn thành bài khi có thể giải thích giới hạn `cte_max_recursion_depth`, phân biệt depth với số hàng, ngăn chu trình, kiểm soát fan-out, đặt row/time budget và dùng `EXPLAIN` để đánh giá chi phí recursive CTE.

## 18. Nguyên tắc cần ghi nhớ

- Recursive CTE gồm anchor member và recursive member; luôn thiết kế điều kiện dừng rõ ràng.
- `cte_max_recursion_depth` mặc định là 1000 trong MySQL 8.0 và giới hạn số vòng đệ quy, không phải tổng số hàng.
- Thay đổi SESSION chỉ ảnh hưởng connection hiện tại; thay đổi GLOBAL làm mặc định cho session mới.
- Không tăng recursion limit trước khi kiểm tra depth, fan-out, điều kiện dừng và chu trình.
- Giới hạn depth theo nghiệp vụ ngay trong recursive member.
- Dùng path-based cycle detection khi cần theo dõi đường đi; dùng `UNION DISTINCT` trên ID khi mục tiêu chỉ là tập node reachable.
- `UNION DISTINCT` so sánh toàn bộ hàng CTE; thêm depth/path có thể khiến cùng node không còn được xem là duplicate.
- Trên MySQL 8.0.19+, có thể giới hạn hàng bằng `LIMIT` trong recursive member; kết quả chạm giới hạn có thể là một phần.
- Dùng `max_execution_time` hoặc `MAX_EXECUTION_TIME` để đặt budget thời gian cho SELECT.
- Thu hẹp anchor, lọc nhánh, chọn ít cột và tạo index cho khóa nối recursive.
- Recursive CTE được materialize; dữ liệu lớn và cột rộng làm tăng chi phí bộ nhớ/temp storage.
- Dùng `EXPLAIN` và `EXPLAIN ANALYZE` có kiểm soát để xác minh số hàng, vòng lặp và access path.
- Reset session variables trong connection pool và theo dõi truy vấn sau triển khai.

Khi kết hợp giới hạn recursion, điều kiện dừng, kiểm soát chu trình, row/time budget và index phù hợp, bạn có thể chạy recursive CTE có giới hạn tài nguyên rõ ràng. Điều này giúp các truy vấn cây và đồ thị an toàn hơn khi dữ liệu tăng trưởng hoặc xuất hiện bất thường.
