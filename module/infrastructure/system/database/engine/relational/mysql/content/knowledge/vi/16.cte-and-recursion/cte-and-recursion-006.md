# Truy vấn cây tổ chức, đường dẫn và độ sâu

Cây tổ chức là dữ liệu phân cấp: mỗi đơn vị có thể có một đơn vị cha và nhiều đơn vị con. Trong mô hình adjacency list, bảng lưu quan hệ này bằng một cột tự tham chiếu như `parent_unit_id`. Một self join có thể lấy cha trực tiếp, nhưng khi cần toàn bộ cấp dưới, đường dẫn từ gốc tới một nút hoặc độ sâu không cố định, truy vấn đệ quy là cách phù hợp.

MySQL 8.0 hỗ trợ recursive common table expression (recursive CTE) qua `WITH RECURSIVE`. CTE bắt đầu từ một hoặc nhiều hàng gốc (anchor member), sau đó lặp truy vấn thành viên đệ quy (recursive member) để tìm các hàng tiếp theo. Kỹ thuật này giúp truy vấn cây tổ chức, danh mục nhiều cấp, cấu trúc thư mục và quan hệ cha-con mà không cần biết trước số cấp.

Trong module `DATABASE_MYSQL`, cần hiểu cả cấu trúc cây lẫn cardinality, index, giới hạn đệ quy và chu trình. Một khóa ngoại tự tham chiếu chỉ bảo đảm hàng cha tồn tại; nó không tự ngăn một chu trình như A là cha của B và B lại là cha của A.

## Mục tiêu

Sau bài này, bạn có thể:

- Mô hình hóa cây tổ chức bằng adjacency list và khóa ngoại tự tham chiếu.
- Viết recursive CTE với anchor member và recursive member.
- Truy vấn toàn bộ cây, một nhánh con hoặc đường đi ngược lên tổ tiên.
- Tạo đường dẫn từ gốc tới nút và tính độ sâu của mỗi nút.
- Sắp xếp kết quả theo thứ tự cây thay vì chỉ theo tên hoặc ID.
- Phát hiện và ngăn chu trình trong quá trình duyệt.
- Hiểu `cte_max_recursion_depth`, giới hạn kiểu dữ liệu và chi phí thực thi.
- Dùng index và `EXPLAIN` để kiểm tra truy vấn cây.

## 1. Cấu trúc cây tổ chức

Trong adjacency list, mỗi hàng đại diện một đơn vị tổ chức. `parent_unit_id` trỏ tới `unit_id` của cha trực tiếp; nút gốc có `parent_unit_id IS NULL`.

```sql
CREATE TABLE org_unit (
    unit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    unit_name VARCHAR(120) NOT NULL,
    parent_unit_id BIGINT UNSIGNED NULL,
    sort_order INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (unit_id),
    KEY idx_org_parent_sort (parent_unit_id, sort_order, unit_id),
    CONSTRAINT fk_org_unit_parent
        FOREIGN KEY (parent_unit_id)
        REFERENCES org_unit (unit_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Ý nghĩa các cột:

- `unit_id`: định danh duy nhất của đơn vị.
- `unit_name`: tên đơn vị.
- `parent_unit_id`: ID của cha trực tiếp; `NULL` nếu là gốc.
- `sort_order`: thứ tự hiển thị giữa các đơn vị cùng cha.
- `idx_org_parent_sort`: hỗ trợ tìm các nút con theo cha và thứ tự hiển thị.

Khóa ngoại tự tham chiếu ngăn một hàng trỏ tới một `parent_unit_id` không tồn tại. `ON DELETE RESTRICT` ngăn xóa một đơn vị khi vẫn có đơn vị con tham chiếu tới nó. Quy tắc này buộc ứng dụng xử lý cây con trước khi xóa nút cha.

### 1.1. Dữ liệu mẫu

Chèn các nút theo thứ tự cha trước, con sau:

```sql
INSERT INTO org_unit
    (unit_id, unit_name, parent_unit_id, sort_order)
VALUES
    (1, 'Executive', NULL, 0),
    (2, 'Engineering', 1, 10),
    (3, 'Product', 1, 20),
    (4, 'Platform', 2, 10),
    (5, 'API', 4, 10),
    (6, 'Web', 4, 20),
    (7, 'People', 1, 30),
    (8, 'Recruitment', 7, 10),
    (9, 'HR Operations', 7, 20);
```

Cây sau khi nạp dữ liệu:

```text
Executive (1)
├── Engineering (2)
│   └── Platform (4)
│       ├── API (5)
│       └── Web (6)
├── Product (3)
└── People (7)
    ├── Recruitment (8)
    └── HR Operations (9)
```

`sort_order` xác định thứ tự các nút cùng cha. ID không nhất thiết phản ánh thứ tự hiển thị hoặc vị trí trong cây; không nên dựa vào ID tăng dần để sắp xếp cấu trúc phân cấp.

## 2. Recursive CTE hoạt động như thế nào?

Cấu trúc tổng quát:

```sql
WITH RECURSIVE cte_name (column_list) AS (
    -- Anchor member: tạo tập hàng bắt đầu.
    SELECT ...

    UNION ALL

    -- Recursive member: tìm hàng tiếp theo từ kết quả trước.
    SELECT ...
    FROM base_table AS child
    JOIN cte_name AS previous_level
      ON ...
)
SELECT ...
FROM cte_name;
```

Quá trình gồm các bước:

1. MySQL chạy anchor member để tạo hàng ban đầu.
2. Recursive member dùng tập hàng hiện có của CTE để tìm thế hệ tiếp theo.
3. Các hàng mới được thêm vào kết quả CTE.
4. Recursive member tiếp tục chạy cho tới khi không tạo thêm hàng hoặc chạm giới hạn đệ quy.
5. Truy vấn bên ngoài đọc kết quả cuối cùng.

Trong cây tổ chức, anchor thường là nút gốc hoặc nút mà người dùng chọn. Recursive member tìm các hàng có `parent_unit_id` bằng `unit_id` của cấp trước.

### 2.1. Anchor member và recursive member

Với cây tổ chức:

- Anchor member chọn `Executive` làm gốc.
- Lần lặp đầu tìm `Engineering`, `Product`, `People`.
- Lần tiếp theo tìm `Platform`, `Recruitment`, `HR Operations`.
- Lần tiếp theo tìm `API`, `Web`.
- Khi không còn nút con, recursion kết thúc.

`UNION ALL` thường được dùng để giữ các hàng được sinh ra ở mỗi vòng lặp mà không phải loại trùng. Nếu dữ liệu cây bảo đảm mỗi nút chỉ có một cha, một nút chỉ được tiếp cận qua một đường từ gốc. Nếu dữ liệu có thể chứa nhiều đường hoặc chu trình, cần thiết kế kiểm soát riêng.

### 2.2. Kiểu dữ liệu của cột CTE

MySQL suy ra kiểu dữ liệu của các cột recursive CTE từ phần anchor member. Nếu cột đường dẫn chỉ được suy ra từ một chuỗi ngắn ở anchor, các giá trị dài hơn được nối ở những vòng lặp sau có thể bị cắt hoặc gây lỗi tùy kiểu và cấu hình.

Vì vậy, khi tạo đường dẫn, hãy `CAST()` ở anchor sang độ dài đủ lớn và giữ kiểu tương thích ở recursive member. Bài này giới hạn ví dụ ở độ sâu 20 và dùng cột đường dẫn 4096 ký tự; hệ thống thực tế cần tính theo độ dài tên, số cấp và giới hạn lưu trữ của schema.

## 3. Truy vấn toàn bộ cây, tính depth và tạo path

Truy vấn sau bắt đầu từ mọi nút gốc, duyệt xuống các cấp con, đồng thời tạo:

- `depth`: độ sâu, gốc là 0.
- `id_path`: mảng JSON chứa ID theo thứ tự từ gốc tới nút hiện tại, dùng để phát hiện chu trình.
- `name_path`: đường dẫn tên để hiển thị.
- `sort_path`: đường dẫn sắp xếp để giữ thứ tự cây.

```sql
WITH RECURSIVE org_tree AS (
    SELECT
        unit_id,
        unit_name,
        parent_unit_id,
        sort_order,
        0 AS depth,
        JSON_ARRAY(unit_id) AS id_path,
        CAST(unit_name AS CHAR(4096)) AS name_path,
        CAST(
            CONCAT(
                LPAD(sort_order, 10, '0'), ':',
                LPAD(unit_id, 20, '0')
            ) AS CHAR(1024)
        ) AS sort_path
    FROM org_unit
    WHERE parent_unit_id IS NULL

    UNION ALL

    SELECT
        child.unit_id,
        child.unit_name,
        child.parent_unit_id,
        child.sort_order,
        tree.depth + 1,
        JSON_ARRAY_APPEND(tree.id_path, '$', child.unit_id),
        CAST(CONCAT(tree.name_path, ' / ', child.unit_name) AS CHAR(4096)),
        CAST(
            CONCAT(
                tree.sort_path, '/',
                LPAD(child.sort_order, 10, '0'), ':',
                LPAD(child.unit_id, 20, '0')
            ) AS CHAR(1024)
        )
    FROM org_unit AS child
    JOIN org_tree AS tree
        ON child.parent_unit_id = tree.unit_id
    WHERE tree.depth < 20
      AND JSON_CONTAINS(tree.id_path, CAST(child.unit_id AS JSON)) = 0
)
SELECT
    unit_id,
    unit_name,
    parent_unit_id,
    depth,
    name_path
FROM org_tree
ORDER BY sort_path;
```

Kết quả có dạng:

| unit_id | unit_name | parent_unit_id | depth | name_path |
|---:|---|---:|---:|---|
| 1 | Executive | `NULL` | 0 | Executive |
| 2 | Engineering | 1 | 1 | Executive / Engineering |
| 4 | Platform | 2 | 2 | Executive / Engineering / Platform |
| 5 | API | 4 | 3 | Executive / Engineering / Platform / API |
| 6 | Web | 4 | 3 | Executive / Engineering / Platform / Web |
| 3 | Product | 1 | 1 | Executive / Product |
| 7 | People | 1 | 1 | Executive / People |
| 8 | Recruitment | 7 | 2 | Executive / People / Recruitment |
| 9 | HR Operations | 7 | 2 | Executive / People / HR Operations |

Thứ tự thực tế được điều khiển bởi `sort_path`, không phải thứ tự vật lý của hàng hoặc ID. `LPAD()` đưa `sort_order` và `unit_id` về độ rộng cố định để phép sắp xếp chuỗi theo thứ tự từ điển phản ánh thứ tự số. Ví dụ giả định `sort_order` không âm và `unit_id` là `BIGINT UNSIGNED`.

### 3.1. Ý nghĩa của depth

Quy ước trong bài:

| Nút | Depth |
|---|---:|
| Nút gốc | 0 |
| Con trực tiếp của gốc | 1 |
| Cháu của gốc | 2 |
| Chắt của gốc | 3 |

Nếu giao diện muốn đánh số cấp bắt đầu từ 1, có thể hiển thị `depth + 1` dưới dạng `level`. Nên thống nhất quy ước ở API và báo cáo để không nhầm giữa depth và level.

### 3.2. Ý nghĩa của name_path và sort_path

`name_path` là chuỗi phục vụ hiển thị. Nếu tên đơn vị có thể chứa dấu `/`, chuỗi này không còn phù hợp để tách ngược thành các thành phần; khi cần dữ liệu máy đọc, hãy dùng mảng JSON hoặc các cột ID riêng.

`sort_path` nối thứ tự của từng nút trên đường từ gốc. Sắp xếp theo toàn bộ path giúp nút cha đứng trước con và các nhánh được giữ theo `sort_order`. `unit_id` được thêm vào từng segment để tạo thứ tự ổn định khi hai nút cùng cha có cùng `sort_order`.

## 4. Truy vấn một nhánh con theo nút được chọn

Nếu người dùng mở một đơn vị cụ thể, chỉ cần lấy cây con của đơn vị đó. Thay điều kiện anchor `parent_unit_id IS NULL` bằng ID được chọn:

```sql
WITH RECURSIVE org_subtree AS (
    SELECT
        unit_id,
        unit_name,
        parent_unit_id,
        sort_order,
        0 AS depth,
        JSON_ARRAY(unit_id) AS id_path,
        CAST(unit_name AS CHAR(4096)) AS name_path,
        CAST(
            CONCAT(LPAD(sort_order, 10, '0'), ':', LPAD(unit_id, 20, '0'))
            AS CHAR(1024)
        ) AS sort_path
    FROM org_unit
    WHERE unit_id = 2

    UNION ALL

    SELECT
        child.unit_id,
        child.unit_name,
        child.parent_unit_id,
        child.sort_order,
        parent.depth + 1,
        JSON_ARRAY_APPEND(parent.id_path, '$', child.unit_id),
        CAST(CONCAT(parent.name_path, ' / ', child.unit_name) AS CHAR(4096)),
        CAST(
            CONCAT(
                parent.sort_path, '/',
                LPAD(child.sort_order, 10, '0'), ':',
                LPAD(child.unit_id, 20, '0')
            ) AS CHAR(1024)
        )
    FROM org_unit AS child
    JOIN org_subtree AS parent
        ON child.parent_unit_id = parent.unit_id
    WHERE parent.depth < 20
      AND JSON_CONTAINS(parent.id_path, CAST(child.unit_id AS JSON)) = 0
)
SELECT unit_id, unit_name, parent_unit_id, depth, name_path
FROM org_subtree
ORDER BY sort_path;
```

Với `unit_id = 2`, kết quả gồm `Engineering`, `Platform`, `API` và `Web`; `Engineering` là hàng anchor có depth 0. Nếu chỉ muốn các hậu duệ, trong **cùng câu lệnh CTE ở trên**, thay phần `SELECT` cuối bằng:

```sql
SELECT unit_id, unit_name, parent_unit_id, depth, name_path
FROM org_subtree
WHERE depth > 0
ORDER BY sort_path;
```

Đây là phần truy vấn ngoài thay thế, không phải câu lệnh độc lập vì phạm vi của CTE kết thúc sau statement. Điều kiện lọc ở truy vấn ngoài giữ nguyên việc duyệt cây; nó chỉ ẩn nút bắt đầu khỏi kết quả cuối cùng.

## 5. Truy vấn đường đi từ một nút lên gốc

Để tìm quản lý, cấp trên hoặc đường dẫn tổ tiên của một đơn vị, anchor tại nút cần tra rồi đệ quy theo hướng ngược lại: từ `parent_unit_id` tìm hàng cha.

```sql
WITH RECURSIVE ancestors AS (
    SELECT
        unit_id,
        unit_name,
        parent_unit_id,
        0 AS distance,
        JSON_ARRAY(unit_id) AS id_path
    FROM org_unit
    WHERE unit_id = 8

    UNION ALL

    SELECT
        parent.unit_id,
        parent.unit_name,
        parent.parent_unit_id,
        current_node.distance + 1,
        JSON_ARRAY_APPEND(current_node.id_path, '$', parent.unit_id)
    FROM org_unit AS parent
    JOIN ancestors AS current_node
        ON parent.unit_id = current_node.parent_unit_id
    WHERE current_node.distance < 20
      AND JSON_CONTAINS(current_node.id_path, CAST(parent.unit_id AS JSON)) = 0
)
SELECT unit_id, unit_name, parent_unit_id, distance
FROM ancestors
ORDER BY distance DESC;
```

Với đơn vị `Recruitment` (ID 8), CTE lần lượt tìm:

1. Recruitment, distance 0.
2. People, distance 1.
3. Executive, distance 2.

Sắp xếp `distance DESC` cho kết quả từ gốc tới nút được chọn. Nếu muốn hiển thị từ nút hiện tại lên trên, dùng `ORDER BY distance ASC`.

### 5.1. Lấy riêng quản lý trực tiếp

Nếu chỉ cần cha trực tiếp, không cần recursive CTE:

```sql
SELECT
    child.unit_id,
    child.unit_name,
    parent.unit_id AS parent_id,
    parent.unit_name AS parent_name
FROM org_unit AS child
LEFT JOIN org_unit AS parent
    ON parent.unit_id = child.parent_unit_id
WHERE child.unit_id = 8;
```

Self join đơn giản hơn và ít chi phí hơn khi nhu cầu chỉ có một cấp. Dùng recursive CTE khi cần nhiều cấp không cố định.

## 6. Tìm đường dẫn của một nút trong toàn bộ cây

Có thể dùng CTE duyệt từ gốc rồi lọc nút cần tìm ở truy vấn ngoài. Cách này phù hợp khi cần biết đường dẫn hiển thị và độ sâu của một nút:

```sql
WITH RECURSIVE org_tree AS (
    SELECT
        unit_id,
        unit_name,
        parent_unit_id,
        sort_order,
        0 AS depth,
        JSON_ARRAY(unit_id) AS id_path,
        CAST(unit_name AS CHAR(4096)) AS name_path,
        CAST(
            CONCAT(LPAD(sort_order, 10, '0'), ':', LPAD(unit_id, 20, '0'))
            AS CHAR(1024)
        ) AS sort_path
    FROM org_unit
    WHERE parent_unit_id IS NULL

    UNION ALL

    SELECT
        child.unit_id,
        child.unit_name,
        child.parent_unit_id,
        child.sort_order,
        tree.depth + 1,
        JSON_ARRAY_APPEND(tree.id_path, '$', child.unit_id),
        CAST(CONCAT(tree.name_path, ' / ', child.unit_name) AS CHAR(4096)),
        CAST(
            CONCAT(
                tree.sort_path, '/',
                LPAD(child.sort_order, 10, '0'), ':',
                LPAD(child.unit_id, 20, '0')
            ) AS CHAR(1024)
        )
    FROM org_unit AS child
    JOIN org_tree AS tree
        ON child.parent_unit_id = tree.unit_id
    WHERE tree.depth < 20
      AND JSON_CONTAINS(tree.id_path, CAST(child.unit_id AS JSON)) = 0
)
SELECT unit_id, unit_name, depth, name_path
FROM org_tree
WHERE unit_id = 5;
```

Kết quả cho API có thể gồm `unit_id`, `depth` và `name_path`; giao diện không cần tự truy vấn từng cấp cha để dựng breadcrumb. Với bảng lớn, nếu chỉ cần đường đi của một nút, truy vấn ngược lên tổ tiên ở phần trước có thể duyệt ít nhánh hơn so với duyệt toàn bộ cây từ gốc.

## 7. Phát hiện và ngăn chu trình

Một bảng tự tham chiếu có thể có khóa ngoại hợp lệ nhưng vẫn chứa chu trình. Ví dụ:

```text
A.parent = B
B.parent = C
C.parent = A
```

Mỗi `parent_unit_id` đều trỏ tới một hàng tồn tại, nhưng không có nút gốc trong chu trình. Khóa ngoại không kiểm tra tính chất “không có vòng lặp”.

### 7.1. Vì sao UNION DISTINCT không đủ?

Có thể nghĩ rằng đổi `UNION ALL` thành `UNION DISTINCT` sẽ tự loại vòng lặp. Điều này không đáng tin cậy nếu CTE có các cột thay đổi theo mỗi vòng như `depth` hoặc `path`:

- Lần đầu một nút có `depth = 1`.
- Khi đi vòng lại, cùng ID có `depth = 4` và path khác.
- Toàn bộ hàng khác nhau nên `UNION DISTINCT` vẫn giữ chúng.

Khử trùng lặp toàn bộ hàng không tương đương phát hiện một ID đã xuất hiện trong đường đi hiện tại. Cần theo dõi các ID đã đi qua.

### 7.2. Dùng JSON path để ngăn lặp ID trên cùng đường đi

Trong ví dụ recursive CTE, `id_path` là mảng JSON chứa các ID từ anchor tới nút hiện tại:

```sql
JSON_ARRAY(unit_id) AS id_path
```

Mỗi vòng lặp nối ID con vào mảng:

```sql
JSON_ARRAY_APPEND(tree.id_path, '$', child.unit_id)
```

Trước khi đi tiếp, kiểm tra ID con chưa có trong path:

```sql
JSON_CONTAINS(tree.id_path, CAST(child.unit_id AS JSON)) = 0
```

Nếu ID đã xuất hiện, nhánh đó không được mở rộng thêm. Đây là bảo vệ cho đường đi đang duyệt; nó không tự sửa dữ liệu nguồn hoặc báo cáo mọi chu trình trong các thành phần không được chạm tới từ anchor.

### 7.3. Kiểm tra dữ liệu chu trình và orphan

Khóa ngoại InnoDB thường ngăn orphan khi được bật và dữ liệu được ghi bình thường. Tuy nhiên, import có thể được thực hiện khi tắt `foreign_key_checks`, hoặc hệ thống cũ có dữ liệu không được kiểm tra. Có thể tìm hàng không có cha:

```sql
SELECT child.unit_id, child.unit_name, child.parent_unit_id
FROM org_unit AS child
LEFT JOIN org_unit AS parent
    ON parent.unit_id = child.parent_unit_id
WHERE child.parent_unit_id IS NOT NULL
  AND parent.unit_id IS NULL;
```

Để phát hiện chu trình, có thể duyệt tổ tiên từ từng nút với path guard và tìm đường quay lại ID ban đầu. Đây là phép kiểm tra có thể tốn kém trên bảng lớn; thực hiện trong quy trình kiểm tra dữ liệu có giới hạn, không chạy tùy tiện trên production.

Ví dụ kiểm tra đường tổ tiên của một nút cụ thể: ghi nhận trạng thái khi hàng cha kế tiếp đã xuất hiện trong `id_path`, rồi dừng mở rộng nhánh đó:

```sql
WITH RECURSIVE ancestor_walk AS (
    SELECT
        unit_id AS start_id,
        unit_id,
        parent_unit_id,
        0 AS depth,
        JSON_ARRAY(unit_id) AS id_path,
        0 AS cycle_detected
    FROM org_unit
    WHERE unit_id = 1

    UNION ALL

    SELECT
        walk.start_id,
        parent.unit_id,
        parent.parent_unit_id,
        walk.depth + 1,
        JSON_ARRAY_APPEND(walk.id_path, '$', parent.unit_id),
        JSON_CONTAINS(walk.id_path, CAST(parent.unit_id AS JSON))
    FROM org_unit AS parent
    JOIN ancestor_walk AS walk
        ON parent.unit_id = walk.parent_unit_id
    WHERE walk.depth < 20
      AND walk.cycle_detected = 0
)
SELECT start_id, unit_id, parent_unit_id, depth, id_path
FROM ancestor_walk
WHERE cycle_detected = 1;
```

Nếu truy vấn trả hàng, `unit_id` ở hàng đó là ID bị gặp lại trên đường đi. Ví dụ đặt anchor tại `Executive` sau khi thử tạo vòng `Executive -> Platform -> Engineering -> Executive` sẽ phát hiện ID `1` lặp lại. Để kiểm tra toàn bảng, có thể chạy logic tương tự cho từng `start_id`, nhưng chi phí có thể lớn theo số nút và độ sâu; nên thực hiện theo batch hoặc trong tác vụ kiểm tra dữ liệu có giới hạn.

### 7.4. Ngăn chu trình khi ghi dữ liệu

Trước khi chuyển một nút sang cha mới, hãy xác nhận cha mới không phải chính nó và không nằm trong cây con của nút đó. Ví dụ, không được chuyển `Engineering` xuống dưới `Platform`, vì `Platform` đã là hậu duệ của `Engineering`.

Một quy trình ứng dụng có thể:

1. Bắt đầu transaction.
2. Khóa hoặc kiểm soát đồng thời các hàng liên quan theo chiến lược phù hợp.
3. Duyệt cây con của nút đang di chuyển và xác nhận cha mới không nằm trong cây con đó.
4. Cập nhật `parent_unit_id`.
5. Commit; rollback nếu phát hiện chu trình hoặc có xung đột.

Chỉ kiểm tra bằng một câu `SELECT` rồi cập nhật sau đó có thể gặp race condition nếu hai transaction đồng thời di chuyển hai nhánh theo hướng tạo chu trình. Với hệ thống nhiều người chỉnh sửa cây, cần thiết kế khóa/tuần tự hóa cập nhật hoặc một cơ chế điều phối ở tầng ứng dụng; khóa ngoại tự tham chiếu đơn thuần không đủ.

## 8. Giới hạn đệ quy và kiểm soát chi phí

MySQL giới hạn số vòng lặp recursive CTE bằng biến `cte_max_recursion_depth`. Giá trị mặc định thường là 1000. Kiểm tra:

```sql
SELECT @@SESSION.cte_max_recursion_depth;
```

Có thể đặt giới hạn riêng cho session:

```sql
SET SESSION cte_max_recursion_depth = 100;
```

Đặt giới hạn phù hợp với chiều sâu tối đa của dữ liệu. Không tăng giới hạn chỉ để che một chu trình hoặc dữ liệu sai. `WHERE tree.depth < 20` trong ví dụ là giới hạn nghiệp vụ rõ ràng; nó dừng duyệt sâu hơn 20 cạnh kể từ anchor.

### 8.1. Giới hạn độ dài đường dẫn

`name_path` và `sort_path` được `CAST()` với độ dài cố định ở anchor. Nếu cây sâu hơn dự kiến hoặc tên đơn vị dài hơn, đường dẫn có thể vượt giới hạn. Hãy:

- Tính độ dài tối đa dựa trên số cấp và độ dài tên.
- Đặt depth guard phù hợp.
- Kiểm tra warning/lỗi về truncation trên phiên bản đang dùng.
- Dùng JSON array cho đường dẫn dữ liệu máy đọc thay vì một chuỗi phân cách.
- Không lưu path hiển thị vào cột vật lý nếu có thể dựng lại từ quan hệ cha-con.

Đường dẫn được tạo trong CTE chỉ phục vụ truy vấn. Nếu lưu sẵn đường dẫn vào bảng, mỗi lần di chuyển nút có thể cần cập nhật toàn bộ hậu duệ; phải cân nhắc chi phí đồng bộ và tính nhất quán.

### 8.2. Recursive CTE có thể tốn tài nguyên

Mỗi vòng lặp cần tìm các hàng con từ tập hiện tại. Index trên `parent_unit_id` giúp truy xuất con của mỗi nút hiệu quả hơn. Nếu không có index, MySQL có thể phải quét nhiều hàng lặp lại.

Các yếu tố làm truy vấn nặng:

- Nút có số con rất lớn.
- Cây sâu hoặc có nhiều gốc.
- Path JSON/chuỗi ngày càng dài ở mỗi vòng lặp.
- Truy vấn yêu cầu sort toàn bộ cây theo `sort_path`.
- Nhiều người gọi cùng lúc và kết quả được materialize lớn.

Hãy giới hạn anchor theo nút người dùng yêu cầu, chỉ chọn các cột cần thiết và tránh duyệt toàn bộ cây khi chỉ cần một nhánh.

## 9. Index và EXPLAIN cho truy vấn cây

Index sau được khai báo trong bảng:

```sql
KEY idx_org_parent_sort (parent_unit_id, sort_order, unit_id)
```

Nó hỗ trợ tìm các hàng có `parent_unit_id` bằng ID nút hiện tại. Các cột sau giúp thứ tự con và ID có sẵn trong index. InnoDB cũng cần index cho cột khóa ngoại; khai báo index ghép bắt đầu bằng `parent_unit_id` đáp ứng nhu cầu này.

Kiểm tra kế hoạch:

```sql
EXPLAIN FORMAT=TREE
WITH RECURSIVE org_tree AS (
    SELECT unit_id, unit_name, parent_unit_id, 0 AS depth
    FROM org_unit
    WHERE unit_id = 1

    UNION ALL

    SELECT child.unit_id, child.unit_name, child.parent_unit_id, tree.depth + 1
    FROM org_unit AS child
    JOIN org_tree AS tree
        ON child.parent_unit_id = tree.unit_id
    WHERE tree.depth < 20
)
SELECT * FROM org_tree;
```

Kiểm tra access path cho anchor theo primary key và cho recursive member theo index `parent_unit_id`. `EXPLAIN ANALYZE` trên MySQL 8.0.18 trở lên có thể cho biết số hàng và thời gian thực tế; lệnh này chạy truy vấn, nên chỉ dùng với truy vấn đọc có phạm vi được kiểm soát.

Không phải mọi truy vấn đều cần thêm index. Nếu bảng nhỏ, optimizer có thể chọn table scan. Index làm tăng chi phí ghi và dung lượng; hãy dựa trên workload và kế hoạch thực thi thực tế.

## 10. Tổng hợp theo độ sâu hoặc theo nhánh

Sau khi tạo CTE, có thể tổng hợp số đơn vị theo cấp:

```sql
WITH RECURSIVE org_tree AS (
    SELECT unit_id, unit_name, parent_unit_id, 0 AS depth
    FROM org_unit
    WHERE parent_unit_id IS NULL

    UNION ALL

    SELECT child.unit_id, child.unit_name, child.parent_unit_id, tree.depth + 1
    FROM org_unit AS child
    JOIN org_tree AS tree
        ON child.parent_unit_id = tree.unit_id
    WHERE tree.depth < 20
)
SELECT depth, COUNT(*) AS unit_count
FROM org_tree
GROUP BY depth
ORDER BY depth;
```

Aggregate được đặt ở truy vấn ngoài, sau khi recursive CTE tạo tập cây. Recursive member trong MySQL có các hạn chế về aggregate, `GROUP BY`, window function và một số cấu trúc truy vấn; vì vậy, hãy giữ phần đệ quy tập trung vào việc tìm hàng kế tiếp, rồi tổng hợp ở bên ngoài.

Nếu cần đếm số hậu duệ của từng nút, có thể bắt đầu một CTE riêng cho từng gốc cần thống kê hoặc dùng một truy vấn đệ quy có thêm `root_id` để giữ nút bắt đầu. Hãy cân nhắc số hàng trung gian vì việc tạo một đường đi cho mọi nút có thể tăng rất nhanh trong cây rộng/sâu.

## 11. Sửa đổi cây tổ chức

### 11.1. Thêm một nút con

Thêm đơn vị `Data Engineering` dưới `Engineering`:

```sql
INSERT INTO org_unit (unit_name, parent_unit_id, sort_order)
VALUES ('Data Engineering', 2, 30);
```

Khóa ngoại xác nhận `parent_unit_id = 2` tồn tại. Index `idx_org_parent_sort` giúp truy vấn sau tìm các con trực tiếp:

```sql
SELECT unit_id, unit_name, sort_order
FROM org_unit
WHERE parent_unit_id = 2
ORDER BY sort_order, unit_id;
```

### 11.2. Di chuyển một nút sang nhánh khác

Ví dụ chuyển `Web` sang `Product`:

```sql
UPDATE org_unit
SET parent_unit_id = 3
WHERE unit_id = 6;
```

Khóa ngoại bảo đảm `Product` tồn tại, nhưng không ngăn việc tạo chu trình. Trước khi cập nhật trong ứng dụng thật, phải kiểm tra cha mới không nằm trong cây con của `Web`, và phải kiểm soát race condition giữa các thao tác di chuyển đồng thời.

### 11.3. Xóa một nhánh

Với `ON DELETE RESTRICT`, không thể xóa một nút cha khi còn con. Có thể xóa từ lá lên gốc theo thứ tự, hoặc xây dựng quy trình xóa nhánh có kiểm soát. Không đổi sang `ON DELETE CASCADE` chỉ để đơn giản hóa thao tác nếu cây có dữ liệu lịch sử hoặc quyền sở hữu riêng.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Recursive CTE lặp quá lâu hoặc chạm giới hạn | Có chu trình, depth lớn hoặc anchor quá rộng | Kiểm tra dữ liệu, thêm path guard và depth guard |
| Chỉ thấy một cấp con | Dùng self join thường thay vì recursive CTE | Dùng `WITH RECURSIVE` nếu số cấp không cố định |
| Một số đơn vị không xuất hiện khi duyệt từ gốc | Nút nằm trong thành phần không có root, có orphan hoặc chu trình | Kiểm tra `parent_unit_id`, foreign key và dữ liệu nhập |
| Path bị cắt hoặc lỗi kiểu dữ liệu | Anchor suy ra chuỗi quá ngắn | `CAST()` path ở anchor sang độ dài đủ lớn và kiểm tra depth |
| Thứ tự cây sai | Chỉ `ORDER BY unit_id` hoặc `unit_name` | Tạo `sort_path` từ sort_order của từng cấp |
| Cùng một nút xuất hiện nhiều lần | Dữ liệu không còn là cây một-cha, hoặc recursive relation sinh nhiều đường | Kiểm tra cardinality, khóa và quy tắc mô hình |
| Xóa cha bị lỗi khóa ngoại | Có hàng con đang tham chiếu | Xử lý cây con trước hoặc áp dụng chính sách xóa phù hợp |
| Cập nhật parent tạo chu trình | Foreign key chỉ kiểm tra cha tồn tại | Kiểm tra cây con và tuần tự hóa cập nhật |
| Truy vấn toàn cây chậm | Anchor rộng, thiếu index parent hoặc path lớn | Duyệt nhánh cần thiết, thêm index phù hợp, xem `EXPLAIN` |

## 13. Bài thực hành

Thực hiện trong database lab riêng với bảng `org_unit`:

1. Tạo bảng self-referencing và nạp cây mẫu theo thứ tự cha trước, con sau.
2. Viết recursive CTE bắt đầu từ mọi gốc; trả về ID, tên, parent ID và depth.
3. Thêm `name_path` để hiển thị breadcrumb từ gốc tới từng đơn vị.
4. Tạo `sort_path` từ `sort_order` và ID; xác nhận các nhánh được hiển thị đúng thứ tự cây.
5. Truy vấn subtree của `Engineering` và chỉ trả hậu duệ bằng `depth > 0`.
6. Truy vấn ancestors của `Recruitment`; sắp xếp để hiển thị từ `Executive` tới nút hiện tại.
7. Đếm số đơn vị ở mỗi depth bằng aggregate ngoài recursive CTE.
8. Thử tạo một chu trình trong bảng lab bằng cách đổi parent của `Executive` thành `Platform`; quan sát vì sao foreign key không ngăn được chu trình. Sau đó rollback hoặc khôi phục dữ liệu đúng.
9. Thêm `id_path` JSON và điều kiện `JSON_CONTAINS` để dừng nhánh khi ID đã xuất hiện.
10. Đặt `cte_max_recursion_depth` ở session thấp trong lab; quan sát giới hạn và khôi phục giá trị sau bài thử.
11. Chạy truy vấn orphan bằng `LEFT JOIN`; giải thích vì sao dữ liệu bình thường có FK vẫn có thể cần kiểm tra sau import đặc biệt.
12. Chạy `EXPLAIN FORMAT=TREE` cho anchor và recursive member; xác nhận index trên `parent_unit_id` được cân nhắc.
13. Viết quy trình di chuyển một đơn vị sang cha mới, bao gồm kiểm tra chu trình và xử lý hai yêu cầu cập nhật đồng thời.

Bạn hoàn thành bài khi truy vấn được cây ở độ sâu không cố định, dựng được đường dẫn và depth, dự đoán được giới hạn đệ quy và giải thích được vì sao khóa ngoại tự tham chiếu chưa đủ để bảo đảm cấu trúc luôn là cây hợp lệ.

## 14. Nguyên tắc cần ghi nhớ

- Adjacency list lưu cha trực tiếp bằng `parent_unit_id`; nút gốc có parent `NULL`.
- Khóa ngoại tự tham chiếu bảo đảm cha tồn tại nhưng không tự ngăn chu trình.
- Recursive CTE gồm anchor member và recursive member; `WITH RECURSIVE` lặp cho tới khi không còn hàng mới hoặc chạm giới hạn.
- `depth = 0` là nút bắt đầu; mỗi cấp con tăng depth thêm 1.
- Dùng `JSON_ARRAY`/`JSON_ARRAY_APPEND` để theo dõi ID trên đường đi và `JSON_CONTAINS` để ngăn lặp ID.
- `UNION DISTINCT` không thay thế cycle detection nếu các cột depth/path thay đổi qua từng vòng.
- Dùng `CAST()` ở anchor để cấp đủ độ dài cho path; tính theo depth và kích thước tên tối đa.
- Dùng `sort_path` nếu cần giữ thứ tự cây; ID hoặc tên đơn lẻ không nhất thiết phản ánh thứ tự anh em.
- `cte_max_recursion_depth` giới hạn vòng lặp; không tăng giới hạn để che chu trình hoặc dữ liệu sai.
- Index bắt đầu bằng `parent_unit_id` hỗ trợ tìm các nút con; xác nhận bằng `EXPLAIN`.
- Chỉ duyệt subtree cần thiết thay vì toàn cây nếu ứng dụng chỉ mở một nhánh.
- Khi di chuyển nút, kiểm tra cha mới không nằm trong cây con và kiểm soát cập nhật đồng thời.
