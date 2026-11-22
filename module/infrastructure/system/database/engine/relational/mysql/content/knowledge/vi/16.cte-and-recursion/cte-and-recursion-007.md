# Phát hiện chu trình và điều kiện dừng đệ quy

Một danh mục sản phẩm thường được tổ chức thành cây: danh mục cha chứa danh mục con, mỗi danh mục có thể có nhiều cấp. Một hệ thống phụ thuộc dịch vụ lại biểu diễn quan hệ dạng đồ thị: dịch vụ A cần B, B cần C, còn C có thể vô tình phụ thuộc ngược lại A. Nếu dữ liệu chứa một chu trình, truy vấn đệ quy có thể lặp qua cùng các nút, tạo quá nhiều hàng hoặc chạy đến giới hạn đệ quy của MySQL.

Recursive CTE giúp duyệt cây và đồ thị ngay trong SQL. Để truy vấn kết thúc đúng, cần thiết kế đồng thời ba lớp bảo vệ: phát hiện nút đã xuất hiện trên đường đi hiện tại, đặt điều kiện dừng theo độ sâu hoặc nghiệp vụ, và cấu hình giới hạn tài nguyên của server. Giới hạn độ sâu bảo vệ hệ thống khỏi truy vấn chạy quá lâu; nó không thay thế việc phát hiện chu trình và không chứng minh dữ liệu không có chu trình.

## 1. Chu trình là gì và vì sao cần phát hiện?

Trong đồ thị có hướng, một chu trình (cycle) là đường đi bắt đầu tại một nút và quay trở lại chính nút đó qua một hoặc nhiều cạnh.

Ví dụ:

```text
A -> B -> C -> A
```

Đây là chu trình gồm ba nút. Một cạnh tự trỏ cũng là chu trình:

```text
A -> A
```

Trong cấu trúc cây, mỗi nút thường có tối đa một parent. Cây hợp lệ không được có chu trình; nếu A là ancestor của B thì B không thể trở thành ancestor của A.

Chu trình có thể gây ra các vấn đề:

- Truy vấn recursive CTE tiếp tục sinh hàng mãi cho đến khi chạm giới hạn đệ quy.
- Một đường dẫn hiển thị breadcrumb có thể lặp tên danh mục.
- Phân cấp quyền hoặc cấu hình kế thừa có thể quay vòng.
- Tính toán dependency hoặc thứ tự triển khai không tìm được thứ tự hợp lệ.
- Một truy vấn duyệt đồ thị có thể tạo số lượng đường đi tăng rất nhanh.

Không phải mọi lần một nút xuất hiện ở nhiều hàng đều là chu trình. Ví dụ đồ thị hình thoi `A -> B -> D` và `A -> C -> D` có hai đường đi cùng tới D nhưng không có đường nào quay lại nút đã đi qua trên chính đường đó. Phát hiện chu trình phải theo dõi đường đi hiện tại, không chỉ đếm số lần một nút xuất hiện trong toàn bộ kết quả.

## 2. Cấu trúc recursive CTE trong MySQL

Recursive CTE được hỗ trợ trong MySQL 8.0. Cấu trúc tổng quát:

```sql
WITH RECURSIVE cte_name (column_list) AS (
    -- Anchor member: tạo các hàng bắt đầu.
    anchor_query

    UNION ALL

    -- Recursive member: dùng hàng đã sinh để tạo bước kế tiếp.
    recursive_query
)
SELECT ...
FROM cte_name;
```

CTE đệ quy có hai phần:

1. **Anchor member** chạy trước, tạo tập hàng ban đầu. Anchor không tham chiếu chính CTE.
2. **Recursive member** đọc các hàng đã có trong CTE để sinh thêm hàng ở vòng kế tiếp.

MySQL tiếp tục lặp recursive member cho đến khi vòng tiếp theo không sinh thêm hàng. Đây là cơ chế kết thúc tự nhiên. Tuy nhiên, nếu mỗi vòng luôn sinh ra hàng mới, chẳng hạn đi quanh một chu trình, truy vấn không tự dừng. Khi đó cần điều kiện dừng rõ ràng.

### 2.1. Ví dụ đệ quy đơn giản có điều kiện dừng

Sinh dãy số từ 1 đến 5:

```sql
WITH RECURSIVE numbers (n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n < 5
)
SELECT n
FROM numbers;
```

Anchor tạo `1`. Mỗi vòng tiếp theo cộng thêm 1. Khi `n = 5`, điều kiện `n < 5` sai, recursive member không tạo hàng mới và truy vấn kết thúc.

Điều kiện `WHERE n < 5` là giới hạn nghiệp vụ của ví dụ. Trong truy vấn cây/đồ thị, điều kiện dừng thường gồm cả `depth < max_depth` và kiểm tra nút kế tiếp chưa xuất hiện trên path.

### 2.2. CTE không đệ quy và CTE đệ quy khác nhau

CTE thông thường chỉ tạo một tập kết quả tạm để câu truy vấn tham chiếu. Recursive CTE tự tham chiếu trong recursive member. Khi có nhiều CTE, cần đặt CTE phụ thuộc trước CTE sử dụng nó; CTE đệ quy phải được khai báo với `WITH RECURSIVE`.

Trong recursive member, giữ phép mở rộng đơn giản: nối hàng hiện tại với bảng cạnh hoặc bảng cha-con, tính depth/path và áp dụng điều kiện dừng. Các phép tổng hợp, `GROUP BY` hoặc window function nên thực hiện ở truy vấn bên ngoài sau khi quá trình duyệt kết thúc. MySQL có các giới hạn riêng đối với recursive member; không nên giả định mọi cấu trúc SELECT thông thường đều có thể đặt nguyên vẹn vào phần đệ quy.

## 3. Điều kiện dừng có những lớp nào?

Một recursive CTE an toàn thường dùng nhiều điều kiện bổ sung nhau:

| Lớp bảo vệ | Mục đích | Ví dụ |
|---|---|---|
| Điều kiện nghiệp vụ | Chỉ đi qua cạnh hoặc hàng hợp lệ | Chỉ duyệt node đang `ACTIVE` |
| Cycle guard | Không mở rộng đường đi nếu nút kế tiếp đã có trong path | `FIND_IN_SET(next_id, path) = 0` |
| Depth guard | Giới hạn số bước tối đa | `depth < 100` |
| Server recursion limit | Ngăn một CTE vượt quá số vòng được cấu hình | `cte_max_recursion_depth` |
| Execution time limit | Giới hạn thời gian chạy SELECT | `max_execution_time` hoặc optimizer hint phù hợp |

Cycle guard bảo đảm một đường đi không quay lại nút đã đi qua. Depth guard giới hạn phạm vi công việc kể cả khi dữ liệu không có chu trình. Server limit và timeout là lớp bảo vệ tài nguyên cuối cùng.

Không nên chỉ tăng `cte_max_recursion_depth` để làm truy vấn lỗi chạy tiếp. Nếu nguyên nhân là chu trình, tăng giới hạn chỉ khiến server làm thêm nhiều vòng trước khi dừng.

## 4. Thiết kế dữ liệu cây và đồ thị

### 4.1. Cây danh mục dùng parent_id

Mô hình adjacency list lưu parent trực tiếp trên mỗi nút:

```sql
CREATE TABLE categories (
    id BIGINT UNSIGNED NOT NULL,
    parent_id BIGINT UNSIGNED NULL,
    category_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_categories_parent (parent_id),
    CONSTRAINT fk_categories_parent
        FOREIGN KEY (parent_id) REFERENCES categories (id)
) ENGINE=InnoDB;
```

`parent_id IS NULL` biểu thị nút gốc. Foreign key bảo đảm parent được tham chiếu tồn tại, nhưng không ngăn một chu trình. Ví dụ A có parent B, B có parent C và C có parent A vẫn thỏa foreign key vì cả ba ID đều tồn tại.

### 4.2. Đồ thị tổng quát dùng bảng cạnh

Với quan hệ nhiều-nhiều hoặc dependency, dùng bảng cạnh:

```sql
CREATE TABLE graph_nodes (
    id BIGINT UNSIGNED NOT NULL,
    node_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE graph_edges (
    from_id BIGINT UNSIGNED NOT NULL,
    to_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (from_id, to_id),
    KEY idx_edges_to_from (to_id, from_id),
    CONSTRAINT fk_edges_from
        FOREIGN KEY (from_id) REFERENCES graph_nodes (id),
    CONSTRAINT fk_edges_to
        FOREIGN KEY (to_id) REFERENCES graph_nodes (id)
) ENGINE=InnoDB;
```

Một hàng `(from_id, to_id)` biểu diễn cạnh có hướng từ `from_id` sang `to_id`. Primary key ghép ngăn cạnh trùng lặp cùng hướng; index bắt đầu bằng `to_id` hỗ trợ duyệt cạnh ngược. Foreign key bảo vệ sự tồn tại của hai đầu cạnh, nhưng cũng không cấm chu trình.

## 5. Theo dõi đường đi bằng path chuỗi

Một cách dễ hiểu để phát hiện chu trình là lưu danh sách ID đã đi qua trong một chuỗi, ví dụ `,10,20,30,`. Khi chuẩn bị đi đến ID `20`, tìm token `,20,` trong path. Nếu đã có, cạnh mới quay về một nút trên chính đường đi hiện tại và tạo chu trình.

Với ID số, `FIND_IN_SET()` hoặc `LOCATE()` có thể dùng để kiểm tra. Dùng dấu phân cách ở hai đầu token để tránh nhầm ID `12` với `112`.

### 5.1. Duyệt cây từ một nút và chặn chu trình

Ví dụ lấy các hậu duệ từ danh mục `10`:

```sql
WITH RECURSIVE category_walk (
    root_id,
    node_id,
    path,
    depth,
    cycle_found
) AS (
    SELECT
        c.id,
        c.id,
        CAST(CONCAT(',', c.id, ',') AS CHAR(4096)),
        0,
        0
    FROM categories AS c
    WHERE c.id = 10

    UNION ALL

    SELECT
        w.root_id,
        child.id,
        CONCAT(w.path, child.id, ','),
        w.depth + 1,
        LOCATE(CONCAT(',', child.id, ','), w.path) > 0
    FROM category_walk AS w
    INNER JOIN categories AS child
        ON child.parent_id = w.node_id
    WHERE w.cycle_found = 0
      AND w.depth < 100
)
SELECT
    root_id,
    node_id,
    path,
    depth,
    cycle_found
FROM category_walk
ORDER BY depth, node_id;
```

Anchor bắt đầu tại danh mục `10`. Recursive member tìm các hàng có `parent_id` bằng nút hiện tại. Trước khi tiếp tục, truy vấn kiểm tra `child.id` đã xuất hiện trong path chưa. Nếu có, hàng đó được đánh dấu `cycle_found = 1`; điều kiện `w.cycle_found = 0` ngăn mở rộng tiếp từ hàng đã phát hiện chu trình.

`depth < 100` là giới hạn bổ sung. Nếu cây sâu hơn 100 cấp, truy vấn dừng ở cấp đó dù không có chu trình. Hãy xem depth guard là giới hạn phạm vi, không phải kết luận cây hợp lệ.

### 5.2. Vì sao path phải có dấu phân cách?

Nếu path chỉ là `1,12,112`, tìm chuỗi `12` bằng `LOCATE()` có thể khớp nhầm một phần ID `112`. Biểu diễn `,1,12,112,` và tìm `,12,` giúp khớp đúng token.

Đối với ID số nguyên, cách này đơn giản. Không dùng trực tiếp nếu ID là chuỗi có thể chứa dấu phẩy; khi đó delimiter có thể xuất hiện trong chính ID. Có thể mã hóa token, chọn delimiter không thể xuất hiện hoặc dùng JSON array.

### 5.3. Độ dài cột path trong recursive CTE

MySQL xác định kiểu và độ dài cột của recursive CTE từ phần anchor member. Vì vậy, nếu anchor tạo `path` quá ngắn, các vòng đệ quy có thể bị lỗi độ dài dữ liệu hoặc không chứa đủ đường đi theo thiết kế.

Trong ví dụ, `CAST(... AS CHAR(4096))` dành dung lượng cho path và giới hạn độ sâu ở 100. Với ID `BIGINT UNSIGNED` tối đa 20 chữ số, 101 ID cùng dấu phẩy cần khoảng hơn 2.100 ký tự, nằm trong giới hạn 4.096. Nếu thay đổi kiểu ID hoặc depth, phải tính lại độ dài cần thiết. Không chọn `CHAR(4096)` như một con số cố định cho mọi hệ thống.

## 6. Duyệt đồ thị có hướng và phát hiện chu trình

Với bảng `graph_edges`, recursive CTE có thể duyệt các cạnh từ một nút bắt đầu. Ví dụ kiểm tra các đường đi xuất phát từ node `1`:

```sql
WITH RECURSIVE graph_walk (
    start_id,
    node_id,
    path,
    depth,
    cycle_found
) AS (
    SELECT
        n.id,
        n.id,
        CAST(CONCAT(',', n.id, ',') AS CHAR(4096)),
        0,
        0
    FROM graph_nodes AS n
    WHERE n.id = 1

    UNION ALL

    SELECT
        w.start_id,
        e.to_id,
        CONCAT(w.path, e.to_id, ','),
        w.depth + 1,
        LOCATE(CONCAT(',', e.to_id, ','), w.path) > 0
    FROM graph_walk AS w
    INNER JOIN graph_edges AS e
        ON e.from_id = w.node_id
    WHERE w.cycle_found = 0
      AND w.depth < 100
)
SELECT
    start_id,
    node_id AS repeated_node,
    path AS cycle_path,
    depth
FROM graph_walk
WHERE cycle_found = 1;
```

Khi một cạnh dẫn đến nút đã có trong path, truy vấn phát ra hàng đánh dấu chu trình. Ví dụ path `,1,2,3,1,` cho biết đường đi `1 -> 2 -> 3 -> 1` quay về node `1`.

Truy vấn trên chỉ phát hiện chu trình có thể đi tới từ node bắt đầu `1`. Muốn khảo sát toàn bộ đồ thị, có thể dùng mọi node làm anchor:

```sql
-- Thay phần anchor bằng SELECT n.id ... FROM graph_nodes AS n
-- để bắt đầu một lượt duyệt từ mỗi node.
```

Bắt đầu từ mọi node có thể tạo nhiều kết quả trùng cho cùng một chu trình, vì cùng chu trình có thể được phát hiện từ từng node nằm trên chu trình hoặc từ các node dẫn tới chu trình. Đây là kết quả bình thường của cách duyệt theo từng start node. Nếu cần danh sách chu trình duy nhất, cần chuẩn hóa cách biểu diễn chu trình (ví dụ xoay về ID nhỏ nhất làm đầu) và loại trùng ở bước xử lý riêng.

## 7. Phát hiện chu trình trong bảng parent_id

Với adjacency list, có thể đi ngược từ mỗi node lên parent. Nếu parent kế tiếp đã xuất hiện trong path, chu trình được phát hiện.

```sql
WITH RECURSIVE parent_walk (
    start_id,
    node_id,
    path,
    depth,
    cycle_found
) AS (
    SELECT
        c.id,
        c.id,
        CAST(CONCAT(',', c.id, ',') AS CHAR(4096)),
        0,
        0
    FROM categories AS c

    UNION ALL

    SELECT
        w.start_id,
        c.parent_id,
        CONCAT(w.path, c.parent_id, ','),
        w.depth + 1,
        LOCATE(CONCAT(',', c.parent_id, ','), w.path) > 0
    FROM parent_walk AS w
    INNER JOIN categories AS c
        ON c.id = w.node_id
    WHERE c.parent_id IS NOT NULL
      AND w.cycle_found = 0
      AND w.depth < 100
)
SELECT
    start_id,
    node_id AS repeated_parent_id,
    path AS cycle_path,
    depth
FROM parent_walk
WHERE cycle_found = 1;
```

Anchor bắt đầu từ mọi danh mục. Mỗi vòng lấy parent của node hiện tại. Khi parent đã xuất hiện trong path, truy vấn ghi nhận đường đi lặp. Vì anchor bắt đầu từ mọi node, một chu trình có thể được báo nhiều lần với các `start_id` khác nhau.

Nếu chỉ cần kiểm tra một danh mục cụ thể, thêm điều kiện `WHERE c.id = ...` ở anchor để giảm phạm vi duyệt. Nếu bảng lớn, không nên bắt đầu từ mọi node trong giờ cao điểm mà chưa ước lượng số đường đi và chi phí.

## 8. Dùng JSON array để theo dõi path

Nếu ID không phải số nguyên đơn giản hoặc muốn tránh vấn đề delimiter, có thể lưu path dưới dạng JSON array. `JSON_ARRAY()` tạo path ban đầu; `JSON_ARRAY_APPEND()` thêm node mới; `JSON_CONTAINS()` kiểm tra node đã xuất hiện.

Ví dụ trên đồ thị:

```sql
WITH RECURSIVE graph_walk (
    start_id,
    node_id,
    path,
    depth,
    cycle_found
) AS (
    SELECT
        n.id,
        n.id,
        JSON_ARRAY(n.id),
        0,
        0
    FROM graph_nodes AS n
    WHERE n.id = 1

    UNION ALL

    SELECT
        w.start_id,
        e.to_id,
        JSON_ARRAY_APPEND(w.path, '$', e.to_id),
        w.depth + 1,
        JSON_CONTAINS(w.path, JSON_ARRAY(e.to_id), '$')
    FROM graph_walk AS w
    INNER JOIN graph_edges AS e
        ON e.from_id = w.node_id
    WHERE w.cycle_found = 0
      AND w.depth < 100
)
SELECT
    start_id,
    node_id AS repeated_node,
    path,
    depth
FROM graph_walk
WHERE cycle_found = 1;
```

`JSON_CONTAINS(path, JSON_ARRAY(e.to_id), '$')` trả về giá trị đúng khi ID đích đã nằm trong array ở root. JSON so sánh kiểu dữ liệu; số `1` và chuỗi `"1"` không phải cùng một giá trị. Hãy bảo đảm kiểu ID trong path và giá trị đem kiểm tra thống nhất.

JSON path dễ biểu diễn ID chuỗi có dấu phân cách, nhưng mỗi vòng phải tạo và kiểm tra tài liệu JSON. Với đồ thị lớn hoặc path dài, chi phí bộ nhớ và CPU có thể đáng kể. Chọn string path hoặc JSON path theo kiểu ID, độ sâu và quy mô dữ liệu; luôn đo bằng dữ liệu đại diện.

## 9. Vì sao UNION DISTINCT không thay thế cycle guard?

Một số người nghĩ có thể dùng `UNION DISTINCT` thay cho `UNION ALL` để MySQL tự loại các node đã thấy. Cách này chỉ loại hàng trùng hoàn toàn theo tất cả cột trong CTE.

Ví dụ nếu CTE chỉ chứa `node_id`, `UNION DISTINCT` có thể ngăn một ID lặp lại trong kết quả. Nhưng khi CTE còn có `path` hoặc `depth`, cùng một node được đến qua đường khác sẽ tạo hàng khác:

| node_id | depth | path |
|---:|---:|---|
| 3 | 2 | `1,2,3` |
| 3 | 2 | `1,4,3` |
| 1 | 3 | `1,2,3,1` |

Các hàng có `node_id` giống nhau nhưng path khác nhau không phải hàng trùng hoàn toàn. `UNION DISTINCT` vẫn giữ chúng và không tự phát hiện chu trình theo đường đi.

Với truy vấn cần lưu path, dùng `UNION ALL` kết hợp cycle guard rõ ràng. Chỉ dùng `UNION DISTINCT` khi ngữ nghĩa truy vấn thực sự muốn loại hàng trùng trên toàn bộ tập cột và đã chứng minh được điều đó đủ để kết thúc.

## 10. Giới hạn độ sâu bằng cte_max_recursion_depth

MySQL cung cấp system variable `cte_max_recursion_depth` để giới hạn số vòng đệ quy của CTE. Giá trị mặc định thường là `1000`.

Kiểm tra:

```sql
SELECT @@SESSION.cte_max_recursion_depth;
SELECT @@GLOBAL.cte_max_recursion_depth;
```

Có thể đặt giới hạn riêng cho session:

```sql
SET SESSION cte_max_recursion_depth = 200;
```

Giới hạn này áp dụng cho recursive CTE chạy trong session. Nếu truy vấn vượt quá, MySQL hủy truy vấn và trả lỗi thay vì tiếp tục đệ quy vô hạn.

Không tăng giới hạn chỉ để bỏ qua lỗi. Trước hết, kiểm tra:

- Có chu trình trong dữ liệu không?
- Recursive member có điều kiện dừng đúng không?
- Có join thiếu điều kiện làm số hàng tăng theo cấp số nhân không?
- Độ sâu thực tế của cây có vượt giới hạn nghiệp vụ không?
- Có thể giới hạn anchor vào một root hoặc một nhánh nhỏ hơn không?

Chỉ tăng `cte_max_recursion_depth` khi độ sâu lớn là yêu cầu hợp lệ, truy vấn có cycle guard và đã đo tài nguyên. Tránh đặt giá trị quá lớn hoặc bỏ giới hạn mà không có cơ chế kiểm soát khác.

## 11. Depth guard và server limit không có cùng ý nghĩa

Depth guard trong truy vấn là điều kiện nghiệp vụ:

```sql
WHERE w.depth < 100
```

Nó giới hạn số cạnh được đi qua trong đường đi. Server limit `cte_max_recursion_depth` giới hạn số vòng recursive member mà server cho phép.

Hai giá trị này không nhất thiết bằng nhau. Cần đặt depth guard đủ thấp để phù hợp bài toán, đồng thời giữ server limit như lớp bảo vệ độc lập. Nếu depth guard cắt một nhánh ở cấp 100, truy vấn có thể kết thúc bình thường nhưng chưa khám phá hết nhánh đó.

Muốn phân biệt “không còn nút tiếp theo” với “đã chạm giới hạn độ sâu”, có thể lấy các hàng ở depth tối đa nhưng vẫn còn cạnh tiếp theo để báo trạng thái chưa duyệt hết. Ví dụ:

```sql
SELECT w.node_id, w.path, w.depth
FROM category_walk AS w
WHERE w.depth = 100
  AND EXISTS (
      SELECT 1
      FROM categories AS child
      WHERE child.parent_id = w.node_id
  );
```

Đặt truy vấn này trong cùng câu `WITH RECURSIVE` với CTE `category_walk` tương ứng. Các hàng trả về là nhánh còn khả năng mở rộng nhưng đã chạm depth guard; chúng cần được xem là chưa duyệt đầy đủ, không phải kết quả chứng minh không có chu trình.

## 12. Điều kiện dừng theo trạng thái nghiệp vụ

Không phải lúc nào cũng cần duyệt mọi cạnh. Có thể dừng theo thuộc tính của node hoặc quan hệ:

```sql
WITH RECURSIVE active_tree (id, parent_id, depth) AS (
    SELECT id, parent_id, 0
    FROM categories
    WHERE id = 10
      AND is_active = 1

    UNION ALL

    SELECT child.id, child.parent_id, parent.depth + 1
    FROM active_tree AS parent
    INNER JOIN categories AS child
        ON child.parent_id = parent.id
    WHERE child.is_active = 1
      AND parent.depth < 50
)
SELECT *
FROM active_tree;
```

Ví dụ chỉ mở rộng qua danh mục đang active và giới hạn 50 cấp. Tuy nhiên, điều kiện trạng thái không tự phát hiện chu trình. Nếu dữ liệu có thể bị lỗi, vẫn cần path/cycle guard.

Đôi khi recursive member dừng tự nhiên vì không tìm thấy hàng con. Điều này chỉ đúng khi dữ liệu không có chu trình hoặc cycle guard đã loại đường đi lặp. Không dùng “thường thì cây không có cycle” làm điều kiện an toàn.

## 13. Kiểm tra trước khi thay đổi parent_id

Một thao tác chuyển danh mục có thể tạo chu trình nếu đặt node làm con của chính hậu duệ của nó.

Ví dụ muốn chuyển node `10` xuống dưới node `35`. Trước khi cập nhật, phải kiểm tra `35` có đang nằm trong subtree của `10` không. Nếu có, thao tác sẽ tạo vòng.

```sql
WITH RECURSIVE subtree (node_id, path, depth) AS (
    SELECT
        c.id,
        CAST(CONCAT(',', c.id, ',') AS CHAR(4096)),
        0
    FROM categories AS c
    WHERE c.id = 10

    UNION ALL

    SELECT
        child.id,
        CONCAT(s.path, child.id, ','),
        s.depth + 1
    FROM subtree AS s
    INNER JOIN categories AS child
        ON child.parent_id = s.node_id
    WHERE s.depth < 100
      AND LOCATE(CONCAT(',', child.id, ','), s.path) = 0
)
SELECT EXISTS (
    SELECT 1
    FROM subtree
    WHERE node_id = 35
) AS would_create_cycle;
```

Nếu `would_create_cycle = 1`, không thực hiện cập nhật `parent_id = 35` cho node `10`. Nếu kết quả bằng `0`, điều đó chỉ xác nhận trong phạm vi đã duyệt; nếu subtree chạm depth guard, cần kiểm tra thêm để tránh kết luận sai.

Trong môi trường có nhiều request cùng thay đổi cây, kiểm tra rồi cập nhật bằng hai thao tác tách rời có thể bị race condition: hai transaction đồng thời đều thấy cấu trúc cũ hợp lệ, sau đó tạo quan hệ khiến chu trình xuất hiện. Hãy serialize các thay đổi cấu trúc theo cây hoặc khóa một hàng điều phối/root phù hợp trong transaction, kiểm tra lại sau khi lấy khóa rồi mới cập nhật. CTE kiểm tra là một phần của quy trình, không tự tạo constraint chống chu trình.

## 14. Phân biệt chu trình với nhiều đường đi

Đồ thị có thể có nhiều đường đi đến cùng một node mà không có chu trình:

```text
      B
    /   \
A         D
    \   /
      C
```

Hai đường `A -> B -> D` và `A -> C -> D` cùng đến D. Nếu path của nhánh thứ nhất là `A,B,D` và nhánh thứ hai là `A,C,D`, D chưa xuất hiện trong path riêng của từng nhánh trước khi được thêm vào. Đây không phải chu trình.

Cycle guard theo path kiểm tra node tiếp theo có xuất hiện trong chính đường đi hiện tại hay không. Không dùng một biến visited toàn cục theo cách tùy tiện để kết luận chu trình trong mọi loại đồ thị; visited toàn cục phù hợp với một số bài toán reachability, nhưng có thể làm mất thông tin đường đi cần thiết để chứng minh cycle.

## 15. Hiệu năng và nguy cơ bùng nổ số đường đi

Recursive CTE trên cây thường có số hàng tăng theo số node được duyệt. Trên đồ thị phân nhánh, số đường đi có thể tăng rất nhanh. Ví dụ mỗi node có trung bình 3 cạnh ra và độ sâu 10 có thể tạo lượng đường đi lớn hơn nhiều so với số node thực tế.

Các biện pháp kiểm soát:

- Giới hạn anchor vào root hoặc tập node cần điều tra.
- Tạo index trên cột dùng để mở rộng cạnh: `categories(parent_id)` hoặc `graph_edges(from_id, to_id)`.
- Dùng cycle guard để không đi lặp trên cùng path.
- Dùng depth guard phù hợp với nghiệp vụ.
- Chọn cột cần thiết trong CTE; tránh mang theo payload lớn ở mọi vòng.
- Đo bằng dữ liệu đại diện và đọc `EXPLAIN`.
- Đặt giới hạn thời gian và recursion depth ở mức vận hành phù hợp.
- Với đồ thị lớn, cân nhắc xử lý bằng thuật toán graph chuyên dụng hoặc pipeline ngoài database.

Ví dụ kiểm tra kế hoạch:

```sql
EXPLAIN FORMAT=TREE
WITH RECURSIVE category_walk (id, depth) AS (
    SELECT id, 0
    FROM categories
    WHERE id = 10

    UNION ALL

    SELECT child.id, parent.depth + 1
    FROM category_walk AS parent
    JOIN categories AS child
        ON child.parent_id = parent.id
    WHERE parent.depth < 50
)
SELECT *
FROM category_walk;
```

Kế hoạch cần cho thấy cách MySQL truy cập bảng con theo `parent_id`. Nếu mỗi vòng quét toàn bộ bảng categories, kiểm tra index và kiểu dữ liệu của điều kiện nối.

## 16. Các giới hạn cần nhớ của recursive member trong MySQL

Recursive member không phải một SELECT tùy ý. MySQL giới hạn một số cấu trúc trong phần đệ quy để kiểm soát cách thực thi. Những điểm thực hành quan trọng:

- Tham chiếu recursive CTE một lần trong `FROM` của recursive member.
- Không đặt recursive reference trong subquery.
- Không dùng aggregate function, window function, `GROUP BY`, `ORDER BY` hoặc `DISTINCT` trong recursive member theo các giới hạn của MySQL.
- Tránh đặt recursive table ở phía nullable của outer join.
- Thực hiện tổng hợp, xếp hạng hoặc sắp xếp sau khi CTE đã tạo xong tập hàng.

Nếu cần xếp hạng các đường đi hoặc gom các chu trình trùng, hãy để recursive CTE sinh dữ liệu cần thiết trước, sau đó dùng một CTE không đệ quy hoặc truy vấn ngoài để `GROUP BY`, window function và `ORDER BY`.

## 17. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Recursive CTE chạy đến recursion limit | Có chu trình hoặc điều kiện dừng không đủ | Thêm path-based cycle guard và kiểm tra dữ liệu |
| Tăng `cte_max_recursion_depth` nhưng truy vấn vẫn chạy lâu | Chỉ tăng ngưỡng, chưa xử lý nguyên nhân | Kiểm tra chu trình, fan-out và depth guard |
| Path bị lỗi độ dài | Kiểu cột CTE được suy ra từ anchor quá ngắn | `CAST` path với dung lượng tính theo ID và depth |
| ID `12` bị nhầm với `112` | Tìm token không có delimiter | Bao token bằng dấu phân cách hoặc dùng JSON array |
| `UNION DISTINCT` không dừng chu trình | Các hàng khác path/depth nên không trùng hoàn toàn | Dùng `UNION ALL` cùng cycle guard rõ ràng |
| Đồ thị DAG bị coi là có cycle | Nhầm node xuất hiện ở nhiều nhánh với node lặp trên cùng path | Theo dõi path riêng của từng đường đi |
| Một chu trình xuất hiện nhiều lần trong báo cáo | Duyệt từ nhiều start node hoặc nhiều điểm trong cùng cycle | Chuẩn hóa/canonicalize chu trình ở bước sau |
| Truy vấn tạo quá nhiều hàng | Đồ thị phân nhánh, nhiều đường đi | Giới hạn anchor/depth, lọc cạnh và cân nhắc thuật toán khác |
| Foreign key vẫn cho phép tạo cycle | FK chỉ kiểm tra parent tồn tại, không kiểm tra quan hệ không vòng | Kiểm tra trước thay đổi và serialize thao tác sửa cây |
| CTE kết thúc ở depth cap nhưng tưởng dữ liệu hợp lệ | Depth guard cắt nhánh chưa duyệt | Báo nhánh chạm giới hạn và kiểm tra riêng |

## 18. Checklist thiết kế recursive CTE an toàn

- Anchor member bắt đầu từ node hoặc root nào? Phạm vi có quá rộng không?
- Recursive member nối theo đúng cạnh hoặc quan hệ parent-child chưa?
- Path có lưu đủ thông tin để phát hiện node lặp trên cùng đường đi không?
- Kiểu path có đủ dài theo độ sâu tối đa và kích thước ID không?
- ID có chứa delimiter khiến kiểm tra chuỗi bị nhầm không?
- Có cycle guard trước khi tiếp tục mở rộng từ hàng đã phát hiện chu trình không?
- Depth guard có phản ánh giới hạn nghiệp vụ không?
- Kết quả có phân biệt “không còn hàng tiếp theo” với “đã chạm giới hạn” không?
- `cte_max_recursion_depth` và timeout có bảo vệ server không?
- Index có hỗ trợ cột mở rộng cạnh/parent không?
- Đã phân biệt chu trình với nhiều đường đi hợp lệ trong DAG chưa?
- Có nguy cơ nhiều start node tạo kết quả chu trình trùng lặp không?
- Các thao tác thay đổi cây có được serialize để tránh race condition không?
- Đã đo số hàng, độ sâu và thời gian trên dữ liệu đại diện chưa?

## Kết luận

Phát hiện chu trình trong recursive CTE cần theo dõi path của từng đường đi và kiểm tra node kế tiếp trước khi mở rộng. Với ID số, path chuỗi có delimiter là cách đơn giản; với ID phức tạp, JSON array giúp kiểm tra membership rõ ràng hơn. Điều kiện `depth < max_depth` giới hạn phạm vi, còn `cte_max_recursion_depth` và timeout bảo vệ tài nguyên server. Các lớp này bổ trợ nhau: depth cap không chứng minh dữ liệu không có cycle, foreign key không ngăn chu trình, và `UNION DISTINCT` không thay thế path-based cycle guard khi hàng còn chứa path/depth. Thiết kế anchor hẹp, index đúng cột mở rộng, kiểm tra trước thao tác thay đổi parent và kiểm soát cập nhật đồng thời giúp truy vấn cây/đồ thị an toàn hơn.
