# WITH RECURSIVE hoặc cú pháp tương đương theo hệ quản trị

## 1. Vì sao SQL cần truy vấn đệ quy?

Phần lớn câu truy vấn SQL làm việc với một số bảng xác định trước. Chẳng hạn, muốn tìm **đơn vị trực thuộc** của phòng Kỹ thuật, ta có thể dùng:

~~~sql
SELECT unit_id, unit_name
FROM org_units
WHERE parent_unit_id = 2;
~~~

Câu lệnh này chỉ tìm **con trực tiếp** của đơn vị có mã `2`. Nhưng nếu bài toán hỏi:

> Phòng Kỹ thuật có **toàn bộ những đơn vị cấp dưới** nào, bao gồm cấp con, cấp cháu và các cấp sâu hơn mà ta chưa biết trước?

Ta cần đi từ nút gốc đến các nút con, rồi lấy con của những nút vừa tìm được, cứ tiếp tục cho tới khi không còn nút mới. Đây là **truy vấn đệ quy (recursive query)**.

Một kỹ thuật quan trọng của SQL là **biểu thức bảng chung đệ quy** (*recursive common table expression*, recursive CTE). Trên PostgreSQL, SQLite, MySQL 8+, MariaDB và một số hệ khác, ta thường dùng `WITH RECURSIVE`. SQL Server dùng `WITH` cho recursive CTE mà **không thêm từ khóa `RECURSIVE`**. Oracle có **recursive subquery factoring** với `WITH` và cú pháp phân cấp `CONNECT BY`.

Ví dụ dạng PostgreSQL:

~~~sql
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    -- Anchor: điểm bắt đầu.
    SELECT
        unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    -- Recursive member: mở rộng từ các hàng đã tìm được.
    SELECT
        child.unit_id,
        child.parent_unit_id,
        child.unit_name,
        parent.depth + 1
    FROM org_units AS child
    JOIN unit_tree AS parent
        ON child.parent_unit_id = parent.unit_id
)
SELECT unit_id, unit_name, depth
FROM unit_tree
ORDER BY depth, unit_id;
~~~

Câu truy vấn trên đi xuống cây đơn vị tổ chức từ `unit_id = 2`. Số lượng cấp có thể khác nhau giữa các nhánh; ta không cần viết trước một `JOIN` riêng cho mỗi cấp.

**Mục tiêu bài học:**

1. Hiểu vì sao truy vấn đệ quy cần phần **khởi tạo (anchor)**, phần **đệ quy (recursive member)** và điều kiện kết thúc.
2. Viết truy vấn đi xuống hoặc đi lên cây phân cấp.
3. Hiểu `UNION ALL`, `UNION`, độ sâu, đường dẫn, chu trình và thứ tự kết quả.
4. Chuyển cách viết sang **PostgreSQL, MySQL/MariaDB, SQLite, SQL Server, Oracle**.
5. Nhận biết giới hạn vận hành, hiệu năng và tình huống nên chọn cách khác.

## 2. Dữ liệu mẫu: sơ đồ các đơn vị tổ chức

Ta dùng một bảng tự tham chiếu: mỗi đơn vị có thể có một đơn vị cha.

~~~sql
CREATE TABLE org_units (
    unit_id        INTEGER PRIMARY KEY,
    parent_unit_id INTEGER,
    unit_name      VARCHAR(80) NOT NULL,
    CONSTRAINT fk_org_units_parent
        FOREIGN KEY (parent_unit_id)
        REFERENCES org_units(unit_id)
);
~~~

Hai ý nghĩa cần phân biệt:

- `unit_id` là khóa chính, xác định duy nhất từng đơn vị.
- `parent_unit_id` là khóa ngoại **trỏ về chính bảng `org_units`**. Giá trị `NULL` biểu thị một nút gốc chưa có cha trong mô hình này.

Thêm dữ liệu:

~~~sql
INSERT INTO org_units (
    unit_id, parent_unit_id, unit_name
) VALUES
    (1,  NULL, 'Company'),
    (2,  1,    'Engineering'),
    (3,  1,    'Sales'),
    (4,  2,    'Platform'),
    (5,  2,    'Data'),
    (6,  3,    'Regional'),
    (7,  4,    'Infrastructure'),
    (8,  5,    'BI'),
    (9,  6,    'Retail'),
    (10, 3,    'Customer Success'),
    (11, NULL, 'Partners'),
    (12, 11,   'Alliances');
~~~

Sơ đồ cây:

~~~text
Company (1)
├── Engineering (2)
│   ├── Platform (4)
│   │   └── Infrastructure (7)
│   └── Data (5)
│       └── BI (8)
└── Sales (3)
    ├── Regional (6)
    │   └── Retail (9)
    └── Customer Success (10)

Partners (11)
└── Alliances (12)
~~~

Bảng có **12 đơn vị** và **hai nút gốc** là `1` và `11`. Nhánh `Company` có 10 đơn vị, nhánh `Partners` có 2 đơn vị.

Truy vấn không đệ quy chỉ lấy con trực tiếp của Engineering:

~~~sql
SELECT unit_id, unit_name
FROM org_units
WHERE parent_unit_id = 2
ORDER BY unit_id;
~~~

| unit_id | unit_name |
| ---: | --- |
| 4 | Platform |
| 5 | Data |

Còn hai đơn vị `Infrastructure (7)` và `BI (8)` là **cháu** của Engineering, chưa xuất hiện. Ta cần truy vấn đệ quy để lấy mọi cấp.

## 3. Cấu trúc của một recursive CTE

Mô hình tổng quát:

~~~sql
WITH RECURSIVE ten_cte (cot_1, cot_2, ...) AS (
    -- Phần 1: anchor member
    SELECT ...

    UNION ALL

    -- Phần 2: recursive member
    SELECT ...
    FROM bang_nguon AS x
    JOIN ten_cte AS r
      ON ...
    WHERE <dieu_kien_tiep_tuc_tuy_chon>
)
SELECT ...
FROM ten_cte;
~~~

Trong ví dụ này:

- `WITH RECURSIVE` khai báo CTE có thể **tham chiếu chính nó** ở phần đệ quy.
- `ten_cte` là tên quan hệ tạm **trong phạm vi câu truy vấn**, không phải một bảng được lưu vĩnh viễn.
- Danh sách `(cot_1, cot_2, ...)` nêu tên các cột đầu ra của CTE.
- **Anchor member** tạo những hàng đầu tiên; không cần tham chiếu chính CTE.
- `UNION ALL` kết hợp đầu ra của phần khởi tạo và các lượt mở rộng.
- **Recursive member** dùng các hàng đã có ở lượt trước để tạo hàng mới; thường chứa một `JOIN` với tên CTE.
- Điều kiện dừng được tạo bằng cấu trúc dữ liệu (không còn hàng con khớp), một ràng buộc độ sâu, hoặc logic chống lặp/cycle phù hợp.

Cần phân biệt **điều kiện kết thúc** với việc đặt `LIMIT` ở kết quả cuối. Một `LIMIT` bên ngoài không phải cơ chế an toàn chung để ngăn vòng lặp; có kế hoạch truy vấn phải thực hiện nhiều công việc trước khi có thể trả hàng giới hạn, đặc biệt khi có sắp xếp/tổng hợp.

### 3.1. Ví dụ đệ quy nhỏ nhất: tạo dãy số từ 1 đến 5

Trước khi đi vào cây, xét ví dụ một cột:

~~~sql
WITH RECURSIVE numbers (n) AS (
    SELECT 1               -- Anchor.

    UNION ALL

    SELECT n + 1           -- Recursive member.
    FROM numbers
    WHERE n < 5            -- Điều kiện chỉ sinh giá trị tiếp theo.
)
SELECT n
FROM numbers
ORDER BY n;
~~~

Kết quả:

| n |
| ---: |
| 1 |
| 2 |
| 3 |
| 4 |
| 5 |

Diễn giải theo các vòng lặp **logic**:

| Lượt | Hàng đầu vào của lượt | Hàng tạo ra |
| ---: | --- | --- |
| 0 | Không có | Anchor tạo `1` |
| 1 | `1` | `2`, vì `1 < 5` |
| 2 | `2` | `3` |
| 3 | `3` | `4` |
| 4 | `4` | `5` |
| 5 | `5` | Không có hàng mới, vì `5 < 5` là FALSE |

Đến lượt không tạo được hàng mới, quá trình dừng.

Hai lỗi dễ gặp:

~~~sql
-- Không có điểm dừng hữu hiệu: có thể chạy rất lâu
-- cho đến khi gặp lỗi giới hạn/tiêu thụ tài nguyên.
WITH RECURSIVE numbers (n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1 FROM numbers
)
SELECT n FROM numbers;
~~~

~~~sql
-- Lặp mãi cùng giá trị 1 với UNION ALL.
WITH RECURSIVE numbers (n) AS (
    SELECT 1
    UNION ALL
    SELECT n FROM numbers WHERE n = 1
)
SELECT n FROM numbers;
~~~

**Không chạy các ví dụ không có điểm dừng trên môi trường dùng chung.** Các DBMS có giới hạn mức đệ quy hoặc timeout khác nhau, nhưng một chương trình đúng vẫn phải có logic kết thúc rõ ràng.

### 3.2. Recursive CTE không phải hàm tự gọi của ngôn ngữ lập trình

Từ “đệ quy” không có nghĩa DBMS nhất thiết thực hiện một hàm SQL tự gọi trên call stack cho từng hàng. Các hệ thường dùng một thuật toán lặp với **bảng làm việc (working table)**, xử lý hàng qua từng vòng, rồi thêm các hàng kết quả.

Bộ tối ưu được quyền chọn phương pháp thực thi phù hợp. **Không được suy từ việc đệ quy tạo các cấp lần lượt mà kết luận thứ tự hàng cuối được bảo đảm là duyệt theo chiều rộng hoặc chiều sâu**. Cần `ORDER BY` và khóa thứ tự thích hợp khi muốn kết quả có thứ tự ổn định.

## 4. Truy vấn con cháu của một nút: đi từ cha xuống con

Bắt đầu từ đơn vị Engineering, mã `2`:

~~~sql
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT
        unit_id,
        parent_unit_id,
        unit_name,
        0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT
        child.unit_id,
        child.parent_unit_id,
        child.unit_name,
        parent.depth + 1
    FROM org_units AS child
    JOIN unit_tree AS parent
        ON child.parent_unit_id = parent.unit_id
)
SELECT unit_id, unit_name, depth
FROM unit_tree
ORDER BY depth, unit_id;
~~~

Kết quả:

| unit_id | unit_name | depth |
| ---: | --- | ---: |
| 2 | Engineering | 0 |
| 4 | Platform | 1 |
| 5 | Data | 1 |
| 7 | Infrastructure | 2 |
| 8 | BI | 2 |

**`depth = 0`** được gán cho nút bắt đầu Engineering. Hai đơn vị con trực tiếp có `depth = 1`, hai đơn vị cháu có `depth = 2`. Việc tính cấp là quy ước của truy vấn, không phải một cột có sẵn trong bảng.

Giải thích từng phần:

~~~sql
-- Anchor:
SELECT unit_id, parent_unit_id, unit_name, 0
FROM org_units
WHERE unit_id = 2;
~~~

Trả một hàng Engineering.

~~~sql
-- Recursive member:
SELECT
    child.unit_id,
    child.parent_unit_id,
    child.unit_name,
    parent.depth + 1
FROM org_units AS child
JOIN unit_tree AS parent
    ON child.parent_unit_id = parent.unit_id;
~~~

Mỗi lượt tìm những hàng `child` mà mã cha của chúng bằng `unit_id` của một hàng trong lượt trước. Cột `depth` của con được tăng thêm một.

### 4.1. Loại nút bắt đầu khỏi kết quả

Nếu câu hỏi là **“các đơn vị cấp dưới của Engineering”**, có thể muốn bỏ Engineering ra khỏi kết quả:

~~~sql
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT
        child.unit_id,
        child.parent_unit_id,
        child.unit_name,
        parent.depth + 1
    FROM org_units AS child
    JOIN unit_tree AS parent
        ON child.parent_unit_id = parent.unit_id
)
SELECT unit_id, unit_name, depth
FROM unit_tree
WHERE depth > 0
ORDER BY depth, unit_id;
~~~

Kết quả còn bốn đơn vị `4, 5, 7, 8`. Điều kiện `WHERE depth > 0` ở **truy vấn ngoài** chỉ ẩn anchor ở đầu ra; nó không ngăn anchor tham gia mở rộng cây.

### 4.2. Đếm số đơn vị cấp dưới

Một cách đơn giản:

~~~sql
WITH RECURSIVE unit_tree (unit_id, parent_unit_id) AS (
    SELECT unit_id, parent_unit_id
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT child.unit_id, child.parent_unit_id
    FROM org_units AS child
    JOIN unit_tree AS parent
        ON child.parent_unit_id = parent.unit_id
)
SELECT COUNT(*) - 1 AS descendant_count
FROM unit_tree;
-- 4
~~~

Trừ `1` vì CTE có cả nút Engineering. Công thức này giả định **nút bắt đầu tồn tại**, dữ liệu là một cây không chu trình và mỗi đơn vị được duyệt đúng một lần. Nếu anchor không khớp hàng nào, `COUNT(*) - 1` trở thành `-1`, không có ý nghĩa. Một cách rõ ràng hơn là mang cột `depth` và dùng `COUNT(*) FILTER (WHERE depth > 0)` trong PostgreSQL, hoặc `SUM(CASE WHEN depth > 0 THEN 1 ELSE 0 END)` tùy DBMS.

## 5. Đi ngược cây: tìm chuỗi tổ tiên

Không phải truy vấn đệ quy nào cũng đi từ cha xuống con. Khi đã biết nút BI (`8`), ta có thể tìm **các cấp quản lý phía trên**:

~~~text
BI (8)
  → Data (5)
    → Engineering (2)
      → Company (1)
        → không còn cha
~~~

Truy vấn:

~~~sql
WITH RECURSIVE ancestors (
    unit_id, parent_unit_id, unit_name, distance
) AS (
    SELECT
        unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 8

    UNION ALL

    SELECT
        parent.unit_id,
        parent.parent_unit_id,
        parent.unit_name,
        child.distance + 1
    FROM org_units AS parent
    JOIN ancestors AS child
        ON parent.unit_id = child.parent_unit_id
)
SELECT unit_id, unit_name, distance
FROM ancestors
ORDER BY distance;
~~~

Kết quả:

| unit_id | unit_name | distance |
| ---: | --- | ---: |
| 8 | BI | 0 |
| 5 | Data | 1 |
| 2 | Engineering | 2 |
| 1 | Company | 3 |

Điểm khác biệt ở điều kiện `JOIN`:

- **Đi xuống:** `child.parent_unit_id = tree.unit_id`, tìm con của một nút.
- **Đi lên:** `parent.unit_id = tree.parent_unit_id`, tìm cha của một nút.

Trong dữ liệu mẫu, khi tới Company, `parent_unit_id IS NULL` nên không có hàng cha khớp nữa; truy vấn dừng tự nhiên.

Nếu chỉ muốn tổ tiên mà **không bao gồm BI**, có thể lọc `distance > 0` ở truy vấn ngoài.

### Lưu ý về cây và đồ thị

Bảng với **một cột `parent_unit_id`** mô tả mô hình mỗi nút có **tối đa một cha**. Trong mô hình DAG hoặc đồ thị có nhiều cha, cần **bảng cạnh** riêng như `edges(parent_id, child_id)`; một nút có thể được tìm thấy qua nhiều đường. Khi đó truy vấn đệ quy cần thêm chiến lược xử lý đường đi, chu trình và hàng trùng, thay vì coi mỗi nút có một tổ tiên duy nhất.

## 6. Lấy tất cả cây từ nhiều nút gốc

Có thể sử dụng **nhiều hàng anchor**. Với bảng `org_units`, nút gốc là những đơn vị có `parent_unit_id IS NULL`, gồm Company (`1`) và Partners (`11`).

~~~sql
WITH RECURSIVE forest (
    root_id, unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT
        unit_id AS root_id,
        unit_id,
        parent_unit_id,
        unit_name,
        0
    FROM org_units
    WHERE parent_unit_id IS NULL

    UNION ALL

    SELECT
        parent.root_id,
        child.unit_id,
        child.parent_unit_id,
        child.unit_name,
        parent.depth + 1
    FROM org_units AS child
    JOIN forest AS parent
        ON child.parent_unit_id = parent.unit_id
)
SELECT
    root_id,
    unit_id,
    unit_name,
    depth
FROM forest
ORDER BY root_id, depth, unit_id;
~~~

Cột `root_id` được **mang theo** qua các vòng đệ quy. Nhờ vậy, mỗi đơn vị biết mình thuộc cây nào.

Một ví dụ tính số đơn vị và độ sâu lớn nhất của từng cây:

~~~sql
WITH RECURSIVE forest (
    root_id, unit_id, parent_unit_id, depth
) AS (
    SELECT unit_id, unit_id, parent_unit_id, 0
    FROM org_units
    WHERE parent_unit_id IS NULL

    UNION ALL

    SELECT
        parent.root_id,
        child.unit_id,
        child.parent_unit_id,
        parent.depth + 1
    FROM org_units AS child
    JOIN forest AS parent
        ON child.parent_unit_id = parent.unit_id
)
SELECT
    root_id,
    COUNT(*) AS number_of_units,
    MAX(depth) AS max_depth
FROM forest
GROUP BY root_id
ORDER BY root_id;
~~~

Kết quả:

| root_id | number_of_units | max_depth |
| ---: | ---: | ---: |
| 1 | 10 | 3 |
| 11 | 2 | 1 |

Nếu bảng chứa **chu trình** hoặc các hàng không thuộc bất cứ gốc nào, việc chỉ anchor từ các hàng có `parent_unit_id IS NULL` sẽ không nhất thiết đi đến mọi hàng. Đây là lý do cần quan sát chất lượng dữ liệu và dùng phương pháp chống cycle khi truy vấn trên dữ liệu không tin cậy.

## 7. UNION ALL và UNION trong phần đệ quy

Hai dạng thường thấy:

~~~sql
WITH RECURSIVE t AS (
    <anchor>
    UNION ALL
    <recursive_member>
)
SELECT * FROM t;
~~~

và:

~~~sql
WITH RECURSIVE t AS (
    <anchor>
    UNION
    <recursive_member>
)
SELECT * FROM t;
~~~

### 7.1. UNION ALL: giữ mọi hàng được tạo ra

`UNION ALL` giữ cả các hàng giống nhau, không tự loại trùng. Đây là dạng thường dùng cho cây không có chu trình với khóa định danh rõ ràng vì:

- Không phải trả chi phí loại trùng mặc định theo toàn bộ hàng.
- Cho phép biểu diễn những **đường đi khác nhau** trong đồ thị khi cùng tới một nút.
- Dễ thấy số hàng thật được sinh ra.

Tuy nhiên, nếu dữ liệu có một vòng lặp, `UNION ALL` có thể liên tục sinh cùng các nút (hoặc sinh các hàng có `depth` tăng mãi), gây lỗi giới hạn đệ quy, timeout hoặc tiêu thụ tài nguyên.

### 7.2. UNION: loại hàng trùng theo tất cả cột CTE

`UNION` loại các hàng trùng theo **toàn bộ hàng kết quả của CTE**, không chỉ theo `unit_id`. Trong một số truy vấn đồ thị chỉ có cột mã nút, việc loại trùng có thể khiến truy vấn dừng khi những nút đã xuất hiện không được sinh thêm.

Nhưng `UNION` **không phải cơ chế chống chu trình tổng quát** nếu hàng chứa thêm thông tin thay đổi mỗi lượt:

~~~sql
-- Giả sử bảng có chu trình.
WITH RECURSIVE walk (unit_id, depth) AS (
    SELECT 1, 0
    UNION
    SELECT child.unit_id, walk.depth + 1
    FROM org_units AS child
    JOIN walk
      ON child.parent_unit_id = walk.unit_id
)
SELECT * FROM walk;
~~~

Nếu nút `1` được gặp lại với `depth = 4`, hàng `(1, 4)` **khác** hàng `(1, 0)`; `UNION` sẽ không xem chúng là trùng. Khi tiếp tục đi qua chu trình, `depth` tiếp tục tăng nên truy vấn vẫn có thể không kết thúc.

**Kết luận:** muốn chống cycle, hãy áp dụng một cơ chế phát hiện nút đã đi qua **trên từng đường đi**, một tập visited phù hợp, hoặc tính năng `CYCLE` của DBMS. Không coi `UNION` là giải pháp vạn năng.

## 8. Chu trình (cycle) trong dữ liệu phân cấp

### 8.1. Khóa ngoại không tự cấm vòng lặp

Một FK tự tham chiếu kiểm tra rằng mã cha **tồn tại**. Nó **không tự bảo đảm** sơ đồ là cây không có chu trình.

Một vòng lặp có thể có dạng:

~~~text
A → B → C → A
~~~

Khi đi từ một nút và liên tục tìm con, truy vấn có thể quay trở lại nút đã thấy rồi lặp mãi.

Với dữ liệu mẫu, có thể tạo chu trình **chỉ trong transaction thử nghiệm**, sau đó rollback:

~~~sql
BEGIN;

-- Tạo chu trình trong bảng thử nghiệm:
-- Company (1) có cha là BI (8)
-- trong khi BI nằm dưới Data (5), Engineering (2), Company (1).
UPDATE org_units
SET parent_unit_id = 8
WHERE unit_id = 1;

-- Đừng chạy truy vấn đệ quy UNION ALL không giới hạn ở đây.

ROLLBACK;
~~~

Sau `ROLLBACK`, dữ liệu trở về trạng thái ban đầu nếu DBMS hỗ trợ transaction DML bình thường. **Không sửa cây nghiệp vụ thật chỉ để thử lỗi cycle**. Một số hệ có trigger/ràng buộc riêng có thể đã cấm thao tác tạo chu trình; đó là biện pháp bảo vệ tốt nếu nghiệp vụ cần.

### 8.2. Cách chống cycle bằng mảng đường đi ở PostgreSQL

PostgreSQL có kiểu mảng, cho phép mang danh sách những mã nút đã đi qua:

~~~sql
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, unit_name, depth, visited_ids
) AS (
    SELECT
        unit_id,
        parent_unit_id,
        unit_name,
        0,
        ARRAY[unit_id]
    FROM org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT
        child.unit_id,
        child.parent_unit_id,
        child.unit_name,
        parent.depth + 1,
        parent.visited_ids || child.unit_id
    FROM org_units AS child
    JOIN unit_tree AS parent
        ON child.parent_unit_id = parent.unit_id
    WHERE NOT (
        child.unit_id = ANY(parent.visited_ids)
    )
)
SELECT
    unit_id,
    unit_name,
    depth,
    visited_ids
FROM unit_tree
ORDER BY depth, unit_id;
~~~

Ở mỗi lượt:

1. Anchor tạo `visited_ids = [1]`.
2. Khi đi từ nút cha tới nút con, kiểm tra `child.unit_id` đã có trong `visited_ids` của **đường đi hiện tại** chưa.
3. Nếu chưa có, thêm ID vào mảng bằng `||`.
4. Nếu đã có, không tạo thêm hàng cho nút đó, nhờ vậy không khép một vòng lặp trên cùng đường.

Mẫu này là **đặc thù PostgreSQL**, không nên đưa nguyên `ARRAY[...]` và `ANY(array)` sang SQL Server/MySQL/SQLite. Ngoài ra, trên đồ thị có nhiều đường khác nhau dẫn tới cùng một nút, một nút vẫn có thể xuất hiện qua **những đường đi khác nhau**; cơ chế trên ngăn chu trình *trong một đường*, không tự gom mọi đường thành một nút duy nhất.

### 8.3. PostgreSQL hỗ trợ cú pháp CYCLE

Các phiên bản PostgreSQL có hỗ trợ `CYCLE` cho recursive CTE cho phép khai báo khóa cần theo dõi:

~~~sql
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, unit_name
) AS (
    SELECT unit_id, parent_unit_id, unit_name
    FROM org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT
        child.unit_id,
        child.parent_unit_id,
        child.unit_name
    FROM org_units AS child
    JOIN unit_tree AS parent
        ON child.parent_unit_id = parent.unit_id
)
CYCLE unit_id SET is_cycle USING path
SELECT
    unit_id,
    parent_unit_id,
    unit_name,
    is_cycle
FROM unit_tree
ORDER BY unit_id;
~~~

`CYCLE unit_id` theo dõi việc lặp mã nút dọc đường; DBMS bổ sung các trường đánh dấu chu trình và đường đi. Một hàng khép chu trình có thể được đánh dấu, nhưng **không tiếp tục mở rộng theo nhánh đó**. Nếu chỉ muốn các nút không đánh dấu cycle, lọc ở truy vấn ngoài bằng `WHERE NOT is_cycle`.

Cú pháp `CYCLE`, phiên bản được hỗ trợ và kiểu cột phụ trợ phụ thuộc DBMS. PostgreSQL có tính năng này từ **phiên bản 14**. Oracle cũng có cú pháp `CYCLE` trong recursive subquery factoring nhưng chi tiết khai báo khác. Không giả định SQL Server, MySQL và SQLite có cùng cú pháp.

### 8.4. Giới hạn độ sâu để phòng vệ

Nếu nghiệp vụ khẳng định cây không quá ba tầng dưới nút bắt đầu, thêm điều kiện **trong recursive member**:

~~~sql
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, depth
) AS (
    SELECT unit_id, parent_unit_id, 0
    FROM org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT child.unit_id, child.parent_unit_id, parent.depth + 1
    FROM org_units AS child
    JOIN unit_tree AS parent
      ON child.parent_unit_id = parent.unit_id
    WHERE parent.depth < 3
)
SELECT unit_id, depth
FROM unit_tree
ORDER BY depth, unit_id;
~~~

Nút anchor có `depth = 0`; các mức `1, 2, 3` được phép tạo, còn mức `4` không được mở rộng. Điều này đảm bảo truy vấn không đi vô hạn nếu mỗi vòng tăng `depth` đúng như ví dụ, nhưng có thể **cắt mất dữ liệu hợp lệ** nếu tổ chức có cấp sâu hơn ba. Giới hạn độ sâu là một **biện pháp phòng vệ và quy tắc nghiệp vụ**, không thay thế hoàn toàn việc đảm bảo dữ liệu không có chu trình.

## 9. Thứ tự duyệt: đệ quy không tự bảo đảm DFS hoặc BFS

Cùng một tập các nút có thể được trình bày theo:

- **Breadth-first (BFS):** nút gốc, toàn bộ nút cấp 1, rồi cấp 2, cấp 3.
- **Depth-first (DFS):** đi hết một nhánh xuống sâu, rồi quay lại nhánh kế tiếp.

Dù một DBMS có thể sử dụng thuật toán xử lý theo lượt trông giống BFS, **đừng coi thứ tự hàng không có `ORDER BY` là cam kết BFS**.

### 9.1. Trình bày theo cấp (BFS-like)

Nếu chỉ cần mọi hàng được nhóm theo cấp:

~~~sql
WITH RECURSIVE tree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT
        c.unit_id, c.parent_unit_id, c.unit_name, t.depth + 1
    FROM org_units AS c
    JOIN tree AS t
        ON c.parent_unit_id = t.unit_id
)
SELECT unit_id, unit_name, depth
FROM tree
ORDER BY depth, unit_id;
~~~

Thứ tự này đưa cấp 0 trước cấp 1, cấp 2, cấp 3; trong cùng cấp, sắp theo `unit_id`. Đây là **thứ tự trình bày theo cấp**, không nhất thiết phản ánh một thứ tự thăm nút BFS theo từng nhánh với queue được xác định riêng.

### 9.2. PostgreSQL SEARCH DEPTH FIRST / BREADTH FIRST

Các phiên bản PostgreSQL hỗ trợ `SEARCH` có thể tạo một cột thứ tự duyệt:

~~~sql
WITH RECURSIVE tree (
    unit_id, parent_unit_id, unit_name
) AS (
    SELECT unit_id, parent_unit_id, unit_name
    FROM org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT c.unit_id, c.parent_unit_id, c.unit_name
    FROM org_units AS c
    JOIN tree AS t
        ON c.parent_unit_id = t.unit_id
)
SEARCH DEPTH FIRST BY unit_id SET visit_order
SELECT
    unit_id,
    unit_name
FROM tree
ORDER BY visit_order;
~~~

Thay `DEPTH FIRST` bằng `BREADTH FIRST` nếu cần khóa thứ tự tương ứng. Cột `visit_order` do DBMS tạo; **phải `ORDER BY visit_order`** ở truy vấn cuối nếu muốn dùng nó để sắp kết quả.

Tính năng `SEARCH` không phải cú pháp phổ quát của mọi hệ SQL. Trong một số trường hợp, nếu đã dùng `CYCLE` để xây đường dẫn, có thể dùng đường dẫn đó để sắp depth-first mà không cần khai báo `SEARCH` thêm.

## 10. Cú pháp theo từng hệ quản trị

**Mô hình anchor + recursive member + tập kết quả không thay đổi về bản chất**, nhưng cú pháp khai báo và cách giới hạn đệ quy khác nhau.

### 10.1. PostgreSQL: WITH RECURSIVE

~~~sql
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT
        c.unit_id, c.parent_unit_id, c.unit_name, t.depth + 1
    FROM org_units AS c
    JOIN unit_tree AS t
      ON c.parent_unit_id = t.unit_id
)
SELECT unit_id, unit_name, depth
FROM unit_tree
ORDER BY depth, unit_id;
~~~

PostgreSQL có một số tiện ích mạnh cho truy vấn đệ quy:

- Mảng và so sánh với `ANY` giúp mang đường đi và kiểm tra nút đã xuất hiện.
- `SEARCH`/`CYCLE` từ phiên bản phù hợp giúp hỗ trợ thứ tự và xử lý cycle.
- `EXPLAIN (ANALYZE, BUFFERS)` cho phép xem thực thi.
- Có thể dùng `UNION ALL` hoặc `UNION` tùy ý nghĩa; cần thiết kế điều kiện kết thúc.

Chú ý `WITH RECURSIVE` khai báo khả năng tham chiếu đệ quy; từ khóa này không làm cho một `SELECT` bình thường tự biến thành đệ quy. Phần recursive member phải thật sự tham chiếu CTE để tạo các bước tiếp theo.

### 10.2. SQLite: cũng dùng WITH RECURSIVE

SQLite hỗ trợ recursive CTE với cú pháp tương tự:

~~~sql
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT
        c.unit_id, c.parent_unit_id, c.unit_name, t.depth + 1
    FROM org_units AS c
    JOIN unit_tree AS t
      ON c.parent_unit_id = t.unit_id
)
SELECT unit_id, unit_name, depth
FROM unit_tree
ORDER BY depth, unit_id;
~~~

Một số điểm cần nhớ ở SQLite:

- Cú pháp và khả năng đặt `ORDER BY`/`LIMIT` trong recursive member có quy tắc riêng; không chuyển máy móc từ hệ khác.
- Những truy vấn dùng mảng `ARRAY[...]` hoặc `CYCLE` theo PostgreSQL không chạy nguyên vẹn trên SQLite.
- SQLite có hệ kiểu linh hoạt hơn một số DBMS khác; cần chú ý dữ liệu và tính nhất quán của các cột do hai nhánh tạo.
- Khi thực hành cây, hãy bật **thực thi khóa ngoại** nếu mong ràng buộc FK được áp dụng trong kết nối, ví dụ `PRAGMA foreign_keys = ON` ở phiên phù hợp.

SQLite cũng có thể dùng recursive CTE cho các bài toán số học, sinh chuỗi giá trị, duyệt cấu trúc phân cấp, nhưng không phải giải pháp phù hợp cho mọi đồ thị khổng lồ.

### 10.3. MySQL 8+: WITH RECURSIVE

Trên MySQL phiên bản hỗ trợ recursive CTE (MySQL **8.0+**):

~~~sql
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT
        c.unit_id, c.parent_unit_id, c.unit_name, t.depth + 1
    FROM org_units AS c
    JOIN unit_tree AS t
      ON c.parent_unit_id = t.unit_id
)
SELECT unit_id, unit_name, depth
FROM unit_tree
ORDER BY depth, unit_id;
~~~

MySQL có tham số **`cte_max_recursion_depth`** để giới hạn số vòng đệ quy; giá trị mặc định trong nhiều cấu hình MySQL 8.0 là `1000`. Có thể xem cấu hình:

~~~sql
SHOW VARIABLES LIKE 'cte_max_recursion_depth';
~~~

Giới hạn này giúp phát hiện truy vấn có thể không dừng, nhưng không thay thế điều kiện kết thúc hợp lý. Không nâng giới hạn lên rất lớn để “chữa” vòng lặp do dữ liệu sai.

**Lưu ý về kiểu dữ liệu trong MySQL:** kiểu và độ rộng các cột recursive CTE chủ yếu được suy ra từ **anchor member**. Khi tạo **đường dẫn dạng chuỗi** dài dần, anchor nên `CAST` về độ rộng đủ lớn, nếu không phần đệ quy có thể bị lỗi/truncate tùy chế độ SQL. Ví dụ minh họa hướng viết:

~~~sql
WITH RECURSIVE paths (
    unit_id, parent_unit_id, path_text
) AS (
    SELECT
        unit_id,
        parent_unit_id,
        CAST(unit_id AS CHAR(2000))
    FROM org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT
        c.unit_id,
        c.parent_unit_id,
        CONCAT(p.path_text, '/', c.unit_id)
    FROM org_units AS c
    JOIN paths AS p
      ON c.parent_unit_id = p.unit_id
)
SELECT unit_id, path_text
FROM paths;
~~~

`CHAR(2000)` là độ dài minh họa, không đảm bảo phù hợp mọi cây hay mọi cấu hình/kích thước chuỗi. Khi dữ liệu có thể tạo chu trình, cần thêm chống cycle để đường dẫn không tăng vô hạn.

### 10.4. MariaDB: WITH RECURSIVE, nhưng tham số vận hành khác

MariaDB cũng hỗ trợ `WITH RECURSIVE` ở các phiên bản phù hợp:

~~~sql
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT
        c.unit_id, c.parent_unit_id, c.unit_name, t.depth + 1
    FROM org_units AS c
    JOIN unit_tree AS t
      ON c.parent_unit_id = t.unit_id
)
SELECT unit_id, unit_name, depth
FROM unit_tree
ORDER BY depth, unit_id;
~~~

MariaDB có thiết lập **`max_recursive_iterations`** để giới hạn vòng đệ quy; tên này **khác** với `cte_max_recursion_depth` của MySQL. Hai hệ có nguồn gốc liên quan nhưng không nên coi cấu hình và toàn bộ tính năng là giống nhau.

Tương tự MySQL, cần chú ý việc suy diễn kiểu/độ rộng ở anchor, chu trình và các tính năng hỗ trợ theo phiên bản cụ thể.

### 10.5. SQL Server: WITH, không viết RECURSIVE

Đây là một khác biệt cú pháp rất quan trọng:

~~~sql
;WITH unit_tree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    -- Anchor member
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    -- Recursive member
    SELECT
        c.unit_id, c.parent_unit_id, c.unit_name, t.depth + 1
    FROM org_units AS c
    INNER JOIN unit_tree AS t
      ON c.parent_unit_id = t.unit_id
)
SELECT unit_id, unit_name, depth
FROM unit_tree
ORDER BY depth, unit_id
OPTION (MAXRECURSION 100);
~~~

Trong T-SQL:

- Viết **`WITH`**, không viết `WITH RECURSIVE`.
- Recursive member phải tham chiếu tên CTE và kết nối với anchor bằng toán tử tập hợp theo các quy tắc T-SQL; `UNION ALL` là dạng thông dụng và được yêu cầu khi nối anchor với recursive member trong recursive CTE SQL Server.
- Dấu **`;` trước `WITH`** giúp kết thúc câu lệnh trước trong cùng batch; không phải tên cú pháp đệ quy riêng.
- `OPTION (MAXRECURSION 100)` đặt giới hạn mức đệ quy cho **câu lệnh ngoài**. Trong SQL Server, mặc định thường là **100** nếu không ghi hint, còn `MAXRECURSION 0` có nghĩa bỏ giới hạn do hint này cung cấp.
- SQL Server có giới hạn về các phép toán được phép đặt trực tiếp trong recursive member, như một số dạng outer join, tổng hợp và truy vấn con. Cần kiểm tra tài liệu khi viết biểu thức phức tạp.

Không dùng `MAXRECURSION 0` như cách “sửa” một truy vấn có chu trình. Nếu recursive member không có điều kiện dừng, bỏ giới hạn có thể khiến truy vấn chạy vô hạn hoặc tiêu thụ tài nguyên lớn.

Đối với SQL Server, nếu cần truy vấn sâu hơn mức mặc định, hãy đánh giá dữ liệu, chi phí và ràng buộc an toàn, sau đó mới điều chỉnh hint phù hợp.

### 10.6. Oracle: recursive subquery factoring với WITH

Oracle hỗ trợ truy vấn đệ quy bằng **`WITH`** mà không sử dụng từ khóa `RECURSIVE` ở dạng quen thuộc trong PostgreSQL:

~~~sql
WITH unit_tree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT
        c.unit_id, c.parent_unit_id, c.unit_name, t.depth + 1
    FROM org_units c
    JOIN unit_tree t
      ON c.parent_unit_id = t.unit_id
)
SELECT unit_id, unit_name, depth
FROM unit_tree
ORDER BY depth, unit_id;
~~~

Với **recursive subquery factoring**, Oracle yêu cầu khai báo **danh sách alias cột** cho CTE trong các trường hợp được nêu ở tài liệu. `UNION ALL` nối anchor và recursive member theo cú pháp của Oracle; các hạn chế về biểu thức/khóa tham chiếu cần được tôn trọng.

Oracle có các mệnh đề `SEARCH` và `CYCLE` dành cho recursive subquery factoring để kiểm soát thứ tự và phát hiện chu trình, nhưng cú pháp/định nghĩa cột đánh dấu không nhất thiết giống hoàn toàn PostgreSQL.

### 10.7. Oracle: CONNECT BY là cú pháp phân cấp khác

Một cách **đặc trưng Oracle** là `START WITH ... CONNECT BY`, không cần viết CTE đệ quy:

~~~sql
SELECT
    unit_id,
    parent_unit_id,
    unit_name,
    LEVEL - 1 AS depth
FROM org_units
START WITH unit_id = 2
CONNECT BY NOCYCLE PRIOR unit_id = parent_unit_id
ORDER SIBLINGS BY unit_id;
~~~

Ý nghĩa:

- `START WITH unit_id = 2`: chọn nút bắt đầu Engineering.
- `CONNECT BY PRIOR unit_id = parent_unit_id`: tìm những hàng có `parent_unit_id` bằng `unit_id` của hàng cha trước đó.
- `LEVEL` là giả cột cấp độ của Oracle, **bắt đầu từ 1** tại nút gốc của truy vấn. Vì thế `LEVEL - 1` tương ứng quy ước `depth = 0` ở những ví dụ trước.
- `NOCYCLE` cho phép tiếp tục truy vấn khi phát hiện vòng lặp mà không làm lỗi chu trình theo cách thông thường.
- `ORDER SIBLINGS BY unit_id` sắp thứ tự các nút cùng cha theo `unit_id`, phù hợp khi trình bày cây.

**Không nên chuyển nguyên cú pháp `CONNECT BY` sang PostgreSQL/MySQL/SQL Server**; nó là một tính năng SQL phân cấp của Oracle và một số hệ có hỗ trợ riêng.

Một điểm dễ viết ngược trong Oracle là `PRIOR`. Với hướng đi **cha → con**:

~~~sql
CONNECT BY PRIOR unit_id = parent_unit_id
~~~

Từ `PRIOR` chỉ phía hàng cha của quá trình đi xuống. Nếu đổi sang hướng từ con tới cha, điều kiện phải được suy ra lại theo quan hệ mong muốn, không thay tùy tiện thứ tự tên cột.

### Bảng đối chiếu nhanh

| Hệ quản trị | Khai báo recursive CTE | Cơ chế giới hạn/cycle đáng nhớ |
| --- | --- | --- |
| PostgreSQL | `WITH RECURSIVE` | Đường dẫn mảng; `SEARCH`/`CYCLE` trên phiên bản hỗ trợ |
| SQLite | `WITH RECURSIVE` | Điều kiện dừng trong recursive member; quy tắc riêng về recursive SELECT |
| MySQL 8+ | `WITH RECURSIVE` | `cte_max_recursion_depth`, chú ý kiểu suy ra từ anchor |
| MariaDB | `WITH RECURSIVE` | `max_recursive_iterations`, chú ý độ rộng cột |
| SQL Server | `WITH` | `OPTION (MAXRECURSION n)`; recursive member có một số hạn chế |
| Oracle | `WITH` (recursive subquery factoring) | `SEARCH`/`CYCLE` theo cú pháp Oracle |
| Oracle dạng phân cấp | `START WITH ... CONNECT BY` | `LEVEL`, `NOCYCLE`, `ORDER SIBLINGS BY` |

## 11. Truy vấn đệ quy để sinh dãy ngày

Không phải mọi recursive CTE đều xử lý cây. Có thể dùng nó để sinh các mốc trong một khoảng thời gian, chẳng hạn ngày từ 14/11/2026 đến 18/11/2026.

### 11.1. PostgreSQL: cộng một ngày vào DATE

~~~sql
WITH RECURSIVE calendar_days (day_value) AS (
    SELECT DATE '2026-11-14'

    UNION ALL

    SELECT day_value + 1
    FROM calendar_days
    WHERE day_value < DATE '2026-11-18'
)
SELECT day_value
FROM calendar_days
ORDER BY day_value;
~~~

Kết quả:

| day_value |
| --- |
| 2026-11-14 |
| 2026-11-15 |
| 2026-11-16 |
| 2026-11-17 |
| 2026-11-18 |

Trong PostgreSQL, `DATE + INTEGER` trả `DATE`, nên kiểu dữ liệu của anchor và recursive member khớp nhau. Không tự thay bằng `day_value + INTERVAL '1 day'` mà không xét kiểu: phép cộng interval có thể cho kiểu khác với anchor trong một recursive CTE yêu cầu các nhánh tương thích.

### 11.2. Cú pháp cộng ngày khác nhau giữa các DBMS

| DBMS | Ý tưởng cộng một ngày |
| --- | --- |
| PostgreSQL | `date_value + 1` với kiểu `DATE` |
| MySQL/MariaDB | `DATE_ADD(date_value, INTERVAL 1 DAY)` |
| SQL Server | `DATEADD(DAY, 1, date_value)` |
| Oracle | `date_value + 1` với kiểu DATE |
| SQLite | `date(date_value, '+1 day')`, trả chuỗi ngày theo quy tắc date/time của SQLite |

Nếu một hệ có hàm tạo chuỗi/series chuyên dụng, ví dụ PostgreSQL `generate_series`, nó có thể rõ ràng hoặc hiệu quả hơn recursive CTE cho việc sinh dãy số/ngày. **Truy vấn đệ quy là một kỹ thuật**, không phải bắt buộc phải dùng cho mọi dãy giá trị.

### 11.3. Vì sao truy vấn ngày cần ranh giới rõ?

Với điều kiện `day_value < DATE '2026-11-18'`, phần đệ quy vẫn sinh **ngày 18** khi đang xử lý ngày 17, rồi dừng ở lượt xử lý ngày 18. Đây là ví dụ quen thuộc về kiểm tra điều kiện trên **hàng hiện tại trước khi tạo hàng kế tiếp**.

Nếu muốn kết quả chỉ đến ngày 17, đổi điều kiện hoặc đặt rõ giới hạn phù hợp. Nên tách ý nghĩa “ngày cuối có được bao gồm không?” trong đặc tả nghiệp vụ để tránh lỗi lệch một ngày.

## 12. Cột đường dẫn (path) và biểu diễn cây

### 12.1. Đường dẫn giúp nhìn đúng nhánh

Nếu chỉ `ORDER BY depth, unit_id`, các nút được nhóm theo cấp nhưng có thể không nằm ngay dưới cha khi hiển thị. Muốn hiện cây dạng DFS, có thể mang **đường dẫn**:

~~~text
1                 Company
1 / 2             Engineering
1 / 2 / 4         Platform
1 / 2 / 4 / 7     Infrastructure
1 / 2 / 5         Data
1 / 2 / 5 / 8     BI
1 / 3             Sales
1 / 3 / 6         Regional
1 / 3 / 6 / 9     Retail
1 / 3 / 10        Customer Success
~~~

Trong PostgreSQL, một mảng mã nút có thể vừa là **đường dẫn**, vừa dùng để kiểm tra cycle:

~~~sql
WITH RECURSIVE tree (
    unit_id, parent_unit_id, unit_name, depth, path_ids
) AS (
    SELECT
        unit_id,
        parent_unit_id,
        unit_name,
        0,
        ARRAY[unit_id]
    FROM org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT
        child.unit_id,
        child.parent_unit_id,
        child.unit_name,
        parent.depth + 1,
        parent.path_ids || child.unit_id
    FROM org_units AS child
    JOIN tree AS parent
      ON child.parent_unit_id = parent.unit_id
    WHERE NOT (child.unit_id = ANY(parent.path_ids))
)
SELECT
    unit_id,
    unit_name,
    depth,
    path_ids
FROM tree
ORDER BY path_ids;
~~~

Sắp theo mảng khóa đường dẫn cho một thứ tự theo nhánh dựa trên mã nút. Nếu cần sắp theo **tên đơn vị**, **thứ tự thủ công** hoặc một cột ưu tiên khác, phải thiết kế khóa đường dẫn tương ứng, không chỉ dùng `unit_id`.

### 12.2. Đường dẫn dạng chuỗi cần phân cách không nhập nhằng

Một cách khác là tạo chuỗi `'1/2/4/7'`. Nhưng nếu dùng kiểm tra `LIKE '%2%'` để phát hiện mã `2` trong đường dẫn, có thể nhầm với mã `12` hoặc `20`.

Nếu buộc dùng text, cần ký hiệu phân cách và kiểm tra **toàn bộ mã** như `'/2/'`, đồng thời xử lý kiểu, escape, độ dài tối đa và collation phù hợp. Mảng hoặc cấu trúc đường dẫn chuyên dụng của DBMS thường an toàn hơn một chuỗi ghép tùy ý.

Trong MySQL, một chuỗi path tạo dài dần còn cần cast anchor đủ độ rộng; trong SQL Server, kiểu `VARCHAR(MAX)`/`NVARCHAR(MAX)` hoặc kích thước cụ thể phải được thiết kế khớp cả hai nhánh theo khả năng hỗ trợ.

## 13. Đếm và tổng hợp trong truy vấn đệ quy

Các bài toán phân cấp thường cần:

- Đếm tổng số người/bộ phận cấp dưới của một nút.
- Tìm độ sâu lớn nhất của một nhánh.
- Tính tổng ngân sách hoặc số lượng ở toàn bộ cây con.
- Tìm đơn vị cùng cây với một đơn vị khác.

Điều quan trọng là **phân biệt giai đoạn tạo hàng đệ quy và giai đoạn tổng hợp**. Nhiều DBMS hạn chế sử dụng aggregate hoặc window trực tiếp trong recursive member. Một cách dễ hiểu là **sinh danh sách nút trước, rồi tổng hợp ở truy vấn ngoài**.

Ví dụ đếm độ sâu và số cấp dưới của Engineering:

~~~sql
WITH RECURSIVE subtree (
    unit_id, parent_unit_id, depth
) AS (
    SELECT unit_id, parent_unit_id, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT child.unit_id, child.parent_unit_id, parent.depth + 1
    FROM org_units AS child
    JOIN subtree AS parent
      ON child.parent_unit_id = parent.unit_id
)
SELECT
    COUNT(*) AS units_including_root,
    MAX(depth) AS max_depth
FROM subtree;
-- units_including_root = 5; max_depth = 2
~~~

Trong ví dụ này, đơn vị Engineering tự nó cũng được đếm. Nếu yêu cầu “số đơn vị cấp dưới” thì là `5 - 1 = 4` vì anchor có đúng một hàng và cây không có chu trình.

### 13.1. Đếm nhiều cây cùng lúc

Khi đã mang `root_id` trong CTE như mục 6, có thể `GROUP BY root_id` để đếm từng cây mà không phải viết một truy vấn cho mỗi gốc.

### 13.2. Tổng hợp ở đồ thị có nhiều đường

Nếu một nút có thể tới được qua **nhiều đường khác nhau**, kết quả recursive CTE với `UNION ALL` có thể chứa một nút nhiều lần. Khi đó `SUM(budget)` có thể bị **đếm lặp ngân sách** dù không có chu trình vô hạn.

Trước khi tổng hợp, hãy xác định nghiệp vụ cần:

- **Mỗi nút duy nhất** được tính một lần, hay
- **Mỗi đường đi** được tính một lần, hoặc
- **Mỗi quan hệ cạnh** được tính một lần?

Nếu cần mỗi nút duy nhất, khử trùng theo **khóa nút** ở mức phù hợp trước khi `SUM`, không mặc định `SELECT DISTINCT` trên toàn bộ cột `(node_id, depth, path)` sẽ loại được các lần gặp cùng nút.

## 14. Hiệu năng: điều kiện JOIN và chỉ mục quan trọng hơn cú pháp ngắn

Một truy vấn phân cấp có thể sinh rất nhiều hàng, đặc biệt nếu cây rộng hoặc đồ thị có nhiều đường đi.

### 14.1. Chỉ mục cho cột cha

Trong ví dụ đi từ cha xuống con:

~~~sql
JOIN org_units AS child
  ON child.parent_unit_id = parent.unit_id
~~~

DBMS thường cần tìm **các con của một mã cha** lặp lại nhiều lần. Một chỉ mục trên `parent_unit_id` có thể hữu ích:

~~~sql
CREATE INDEX idx_org_units_parent
    ON org_units (parent_unit_id);
~~~

Khóa chính trên `unit_id` thường đã có chỉ mục riêng theo hành vi của DBMS, hữu ích khi đi ngược từ con lên cha.

**Không phải hệ quản trị nào tự tạo chỉ mục trên cột FK**. Trong PostgreSQL, FK tự tham chiếu `parent_unit_id` không đồng nghĩa DBMS tạo sẵn chỉ mục trên cột này. Trước khi thêm index, hãy cân nhắc số lượng hàng, phân phối cấp con, chi phí ghi và cách truy vấn thực tế.

### 14.2. Cân nhắc mức tăng hàng theo cấp

Nếu mỗi nút có trung bình `b` nút con, số hàng lý thuyết ở cấp `d` của một cây cân đối có thể gần `b^d`. Điều đó tăng rất nhanh khi `b` và `d` lớn. Trên DAG có nhiều đường tới cùng một nút, số **đường đi** thậm chí có thể tăng nhanh hơn số nút phân biệt.

Vì thế cần:

- Chọn anchor đủ hẹp.
- Lọc điều kiện dữ liệu càng đúng ngữ nghĩa càng tốt.
- Có logic dừng và phát hiện cycle.
- Tránh mang các cột văn bản lớn không cần thiết trong mọi vòng.
- Cân nhắc giới hạn độ sâu theo nghiệp vụ.
- Dùng chỉ mục phù hợp, đo trên dữ liệu đại diện.

### 14.3. Dùng EXPLAIN

Trong PostgreSQL:

~~~sql
EXPLAIN
WITH RECURSIVE unit_tree (
    unit_id, parent_unit_id, depth
) AS (
    SELECT unit_id, parent_unit_id, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT c.unit_id, c.parent_unit_id, t.depth + 1
    FROM org_units AS c
    JOIN unit_tree AS t
      ON c.parent_unit_id = t.unit_id
)
SELECT *
FROM unit_tree;
~~~

Kế hoạch có thể hiển thị một bước **Recursive Union** và **WorkTable Scan**, tùy phiên bản/kế hoạch. Có thể dùng `EXPLAIN (ANALYZE, BUFFERS)` để đo thực thi thật nhưng chỉ thực hiện trên truy vấn **đã có điều kiện kết thúc đáng tin cậy**. `ANALYZE` thực sự chạy câu lệnh; đừng dùng nó cho truy vấn đệ quy có khả năng lặp vô hạn.

Với tập dữ liệu mẫu 12 hàng, quét tuần tự có thể nhanh hơn dùng chỉ mục. Không kết luận index “không hiệu quả” chỉ vì DBMS chọn sequential scan trên bảng rất nhỏ.

## 15. Tính đúng đắn khi dữ liệu thay đổi

### 15.1. Đọc dữ liệu trong một lần truy vấn

Recursive CTE là một câu SQL. Cách câu SQL nhìn thấy các thay đổi đồng thời phụ thuộc **mô hình isolation và MVCC/locking** của DBMS.

Không nên giả định rằng mọi hệ quản trị, mọi mức cô lập đều cung cấp cùng một snapshot bất biến cho mọi bước đệ quy. Nếu nghiệp vụ yêu cầu báo cáo chính xác tại một mốc, cần xác định transaction isolation và kiến trúc snapshot phù hợp với DBMS đang dùng.

### 15.2. Thêm, xóa hoặc đổi cha có thể thay đổi cả cây con

Nếu một đơn vị được chuyển từ Engineering sang Sales bằng `UPDATE parent_unit_id`, nó và các hậu duệ có thể chuyển sang nhánh Sales ở lần truy vấn sau.

Khi cập nhật quan hệ cha–con, cần kiểm tra:

- Cha mới có tồn tại không?
- Cha mới có phải **một hậu duệ của nút đang di chuyển** không? Nếu có, cập nhật sẽ tạo chu trình.
- Có giới hạn số tầng hoặc quy tắc về cấp tổ chức không?
- Có ứng dụng nào lưu sẵn đường dẫn/tổng số con cần cập nhật theo không?
- Nhiều cập nhật đồng thời có thể tạo trạng thái không hợp lệ nếu kiểm tra và ghi không được đồng bộ đúng không?

FK chỉ đảm bảo cha tồn tại; không tự ngăn việc **chọn một hậu duệ làm cha mới**. Nếu muốn dữ liệu luôn là cây, cần kiểm tra cycle ở nghiệp vụ hoặc các cơ chế ràng buộc bổ sung có khả năng bảo vệ giao dịch đồng thời.

### 15.3. Đệ quy không đảm bảo dữ liệu mô hình là cây

Một bảng tự tham chiếu chỉ tạo **các liên kết cha–con**, không chứng minh:

- Chỉ có một gốc.
- Mọi nút đều tới được từ gốc mong muốn.
- Không có chu trình.
- Không có các mối quan hệ nghiệp vụ ẩn cần xét.

Trong dữ liệu mẫu có hai gốc; vì vậy truy vấn anchor `WHERE unit_id = 1` không bao gồm Partners (`11`) và Alliances (`12`). Đó là **đúng với điểm bắt đầu đã chọn**, không phải lỗi của recursive CTE.

## 16. Khi nào không nên dùng truy vấn đệ quy?

Recursive CTE đặc biệt phù hợp khi:

- Có cây/đồ thị mà số cấp **không cố định**.
- Cần danh sách **mọi hậu duệ hoặc tổ tiên**.
- Cần duyệt một cấu trúc phụ thuộc từ điểm bắt đầu.
- Muốn xử lý toàn bộ đường đi hoặc gom dữ liệu theo nhánh bằng SQL.

Tuy nhiên, nó không phải giải pháp duy nhất:

| Bài toán | Phương pháp cân nhắc |
| --- | --- |
| Chỉ cần con trực tiếp | `SELECT ... WHERE parent_id = ?`, không cần đệ quy |
| Cây rất lớn, truy vấn hậu duệ cực kỳ thường xuyên | Closure table hoặc materialized path, với chi phí duy trì |
| Chỉ cần sinh dãy số/ngày ở PostgreSQL | `generate_series` |
| Đồ thị phức tạp có đường đi tối ưu, trọng số | Công cụ graph hoặc thuật toán chuyên dụng có thể phù hợp hơn |
| Cây ít thay đổi, hiển thị nhiều | Cache/cấu trúc dẫn xuất theo yêu cầu |
| Chỉ có số cấp cố định rất nhỏ | Một số `JOIN` tường minh có thể đủ, nhưng kém linh hoạt khi tăng cấp |

### Adjacent list, materialized path và closure table

Bảng `org_units(unit_id, parent_unit_id)` là mô hình **adjacency list**: mỗi nút lưu tham chiếu tới cha.

- **Adjacency list:** cập nhật quan hệ tương đối tự nhiên; để tìm tất cả hậu duệ thường dùng recursive CTE.
- **Materialized path:** mỗi nút lưu sẵn đường đi từ gốc; có thể lọc theo tiền tố đường dẫn nhưng phải duy trì khi đổi cha và xử lý phân cách/kiểu dữ liệu.
- **Closure table:** lưu cặp `(ancestor_id, descendant_id, distance)`; truy vấn tổ tiên/hậu duệ nhanh theo khóa nhưng cần cập nhật các cặp khi thay đổi cây.

Chọn mô hình dựa trên tỷ lệ đọc/ghi, độ sâu, độ rộng và yêu cầu nhất quán. **Không vội lưu sẵn mọi kết quả đệ quy** nếu mô hình hiện tại và index đã đáp ứng tốt.

## 17. Những lỗi phổ biến

| Lỗi hoặc hiểu nhầm | Tác động | Cách xử lý |
| --- | --- | --- |
| Không có anchor | Không có tập bắt đầu rõ ràng | Viết phần anchor độc lập trước |
| Quên `UNION ALL`/phần nối hai nhánh | Cú pháp recursive CTE sai | Theo cú pháp hệ quản trị |
| Không tham chiếu CTE ở recursive member | Không thật sự có bước mở rộng đệ quy | `JOIN ten_cte` để tạo hàng tiếp theo |
| Không có điểm dừng hoặc dữ liệu có chu trình | Có thể lặp vô hạn/đụng giới hạn tài nguyên | Điều kiện dừng, cycle detection, giới hạn độ sâu |
| Tưởng `UNION` tự chặn mọi vòng lặp | Hàng có `depth`/`path` mới vẫn phân biệt | Theo dõi nút đã thăm trên đường |
| Quên rằng anchor cũng là hàng kết quả | Đếm cả nút bắt đầu khi chỉ muốn hậu duệ | Lọc `depth > 0` hoặc xác định đúng công thức |
| Đảo điều kiện cha–con | Đi lên thay vì đi xuống, hoặc kết quả không khớp | Xác định rõ cột cha và cột con |
| Giả định recursive CTE trả đúng thứ tự cây | Thứ tự không được bảo đảm | `ORDER BY`/`SEARCH`/khóa path |
| `LIMIT 100` bên ngoài được coi là chống vô hạn | Có thể vẫn thực thi quá nhiều trước khi giới hạn | Chặn mở rộng ở recursive member |
| Sử dụng `WITH RECURSIVE` trên SQL Server | Lỗi cú pháp | Dùng `WITH` và `OPTION (MAXRECURSION n)` |
| Dùng `WITH RECURSIVE` trên Oracle theo cú pháp PostgreSQL | Không tương thích dialect | Dùng Oracle recursive `WITH` hoặc `CONNECT BY` |
| Quên `LEVEL` Oracle bắt đầu ở 1 | Độ sâu lệch 1 | Dùng `LEVEL - 1` khi muốn gốc depth 0 |
| Quên kiểu anchor ở MySQL cho path dài | Lỗi độ rộng hoặc chuỗi bị cắt | `CAST` anchor đủ độ rộng và xác minh |
| Gộp `MAXRECURSION 0` với truy vấn chưa kiểm tra | Gỡ giới hạn phòng vệ | Giữ giới hạn an toàn và kiểm tra cycle |
| Tổng hợp trực tiếp trong recursive member ở hệ cấm | Lỗi cú pháp/ngữ nghĩa theo dialect | Tạo các hàng trước, aggregate ở truy vấn ngoài |
| Đếm mỗi đường đi như mỗi nút | Tổng số hoặc ngân sách bị nhân | Xác định grain và khử trùng đúng khóa |
| Lấy một gốc rồi tưởng đã duyệt cả bảng | Bỏ các cây khác | Nếu cần cả rừng, anchor mọi nút gốc |
| Không có index trên `parent_unit_id` ở bảng lớn | Mỗi bước có thể tốn nhiều lần quét | Cân nhắc index theo hướng duyệt |

## 18. Bài tập thực hành

Sử dụng bảng `org_units` ban đầu ở mục 2. Các bài yêu cầu dự đoán kết quả nên được thực hiện trên dữ liệu **chưa tạo chu trình**. Câu trả lời có tham chiếu một dialect thì dùng đúng DBMS đó.

### Bài 1 — Sinh các số từ 1 đến 10

Viết recursive CTE trên PostgreSQL để sinh một cột `n` có các giá trị từ `1` đến `10`, gồm cả hai đầu.

**Đáp án:**

~~~sql
WITH RECURSIVE numbers (n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM numbers
    WHERE n < 10
)
SELECT n
FROM numbers
ORDER BY n;
~~~

Kết quả có **10 hàng**. Khi đến `n = 10`, recursive member không sinh `11` vì điều kiện `n < 10` sai.

### Bài 2 — Tìm tất cả hậu duệ của Engineering

Đơn vị Engineering có `unit_id = 2`. Hãy viết SQL lấy **chỉ các hậu duệ**, không lấy Engineering, kèm độ sâu.

**Đáp án:**

~~~sql
WITH RECURSIVE subtree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT
        c.unit_id, c.parent_unit_id, c.unit_name, t.depth + 1
    FROM org_units AS c
    JOIN subtree AS t
      ON c.parent_unit_id = t.unit_id
)
SELECT unit_id, unit_name, depth
FROM subtree
WHERE depth > 0
ORDER BY depth, unit_id;
~~~

Kết quả: `4 Platform (1)`, `5 Data (1)`, `7 Infrastructure (2)`, `8 BI (2)`. Có **4 hậu duệ**.

### Bài 3 — Tìm tổ tiên của Retail

Retail có `unit_id = 9`. Hãy tìm đường đi từ Retail lên Company.

**Đáp án:**

~~~sql
WITH RECURSIVE ancestors (
    unit_id, parent_unit_id, unit_name, distance
) AS (
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 9

    UNION ALL

    SELECT
        p.unit_id, p.parent_unit_id, p.unit_name, a.distance + 1
    FROM org_units AS p
    JOIN ancestors AS a
      ON p.unit_id = a.parent_unit_id
)
SELECT unit_id, unit_name, distance
FROM ancestors
ORDER BY distance;
~~~

Kết quả theo thứ tự: Retail (`9`), Regional (`6`), Sales (`3`), Company (`1`), với `distance` từ `0` đến `3`.

### Bài 4 — Hai gốc

Tại sao truy vấn anchor `WHERE unit_id = 1` không lấy `Partners` và `Alliances`? Viết điều kiện anchor để lấy **cả hai cây**.

**Đáp án:** vì `Partners` có `unit_id = 11` và là **nút gốc khác**, không phải hậu duệ của Company. Anchor dùng:

~~~sql
SELECT unit_id, parent_unit_id, unit_name, 0
FROM org_units
WHERE parent_unit_id IS NULL
~~~

Sau đó recursive member tìm các con tương ứng. Với dữ liệu mẫu, tổng cộng có **12 đơn vị** trong hai cây.

### Bài 5 — Giới hạn cấp

Đối với Company (`1`), nếu phần đệ quy có điều kiện `WHERE parent.depth < 2` thì mức sâu nhất nào được trả?

**Đáp án:** anchor ở `depth = 0`; tạo được các mức `1` và `2`, nhưng không tạo mức `3`. Những đơn vị `Infrastructure (7)`, `BI (8)` và `Retail (9)` ở cấp 3 sẽ không xuất hiện. `Customer Success (10)` thuộc cấp 2 và vẫn xuất hiện.

### Bài 6 — Phân biệt UNION và UNION ALL khi có depth

Có ý kiến: “Nếu cây có cycle, chỉ cần đổi `UNION ALL` thành `UNION` là truy vấn luôn dừng.” Đúng hay sai?

**Đáp án:** **sai**. Nếu CTE chứa `(unit_id, depth)`, cùng một `unit_id` đi qua chu trình có thể xuất hiện lại với `depth` mới; hàng vẫn khác nên `UNION` không loại được. Cần phát hiện cycle theo khóa nút trên đường đi, một cơ chế `CYCLE` được hỗ trợ, hoặc chiến lược visited phù hợp.

### Bài 7 — Viết lại cho SQL Server

Chuyển truy vấn tìm cây Engineering sang T-SQL.

**Đáp án:**

~~~sql
;WITH subtree (
    unit_id, parent_unit_id, unit_name, depth
) AS (
    SELECT unit_id, parent_unit_id, unit_name, 0
    FROM org_units
    WHERE unit_id = 2

    UNION ALL

    SELECT
        c.unit_id, c.parent_unit_id, c.unit_name, t.depth + 1
    FROM org_units AS c
    JOIN subtree AS t
      ON c.parent_unit_id = t.unit_id
)
SELECT unit_id, unit_name, depth
FROM subtree
ORDER BY depth, unit_id
OPTION (MAXRECURSION 100);
~~~

Không có từ khóa `RECURSIVE`. Hint `OPTION (MAXRECURSION 100)` là giới hạn theo T-SQL, không phải phần của PostgreSQL.

### Bài 8 — Viết lại cho Oracle CONNECT BY

Dùng `START WITH` và `CONNECT BY` lấy các đơn vị thuộc nhánh Engineering.

**Đáp án:**

~~~sql
SELECT
    unit_id,
    unit_name,
    LEVEL - 1 AS depth
FROM org_units
START WITH unit_id = 2
CONNECT BY NOCYCLE PRIOR unit_id = parent_unit_id
ORDER SIBLINGS BY unit_id;
~~~

`LEVEL - 1` cho Engineering độ sâu `0`. `NOCYCLE` hỗ trợ hạn chế lỗi chu trình trong mô hình phân cấp Oracle.

### Bài 9 — Đề xuất chỉ mục

Với bảng `org_units` vài triệu hàng và truy vấn chủ yếu đi **từ cha xuống con**, nên cân nhắc index nào?

**Gợi ý đáp án:**

~~~sql
CREATE INDEX idx_org_units_parent
    ON org_units (parent_unit_id);
~~~

Điều kiện nối tìm `child.parent_unit_id = parent.unit_id`, vì vậy index theo `parent_unit_id` có thể giúp tìm các con. Cần kiểm tra kế hoạch thật và chi phí ghi, không coi một index là bảo đảm hiệu năng trong mọi tình huống.

### Bài 10 — Vì sao thêm LIMIT cuối chưa đủ để ngăn cycle?

Một truy vấn đệ quy trên cây bị lỗi vòng lặp. Có người đề nghị chỉ thêm:

~~~sql
SELECT *
FROM recursive_result
ORDER BY unit_id
LIMIT 20;
~~~

**Đáp án:** `ORDER BY` có thể cần đọc, sắp xếp hoặc xử lý nhiều hàng trước khi áp dụng `LIMIT`. Điều kiện dừng của recursive member vẫn không được sửa, và truy vấn có thể tiêu thụ tài nguyên/đụng giới hạn đệ quy. Cần ngăn tạo lại nút trong đường đi, giới hạn mức sâu có ý nghĩa và xử lý nguyên nhân cycle.

### Bài 11 — Chọn hướng JOIN

Hai điều kiện sau dùng vào tình huống nào?

~~~sql
-- A
child.parent_unit_id = parent.unit_id

-- B
parent.unit_id = current.parent_unit_id
~~~

**Đáp án:** A thích hợp khi **đi xuống** cây, từ một đơn vị tìm các đơn vị con. B thích hợp khi **đi lên** cây, từ nút hiện tại tìm cha của nó. Tên alias có thể đổi, nhưng chiều kết nối phải đúng với quan hệ thực thể.

### Bài 12 — Truy vấn không trả hàng

Nếu anchor là:

~~~sql
SELECT unit_id, parent_unit_id, unit_name, 0
FROM org_units
WHERE unit_id = 999;
~~~

và không có đơn vị 999, recursive CTE trả bao nhiêu hàng?

**Đáp án:** **0 hàng**. Anchor không sinh hàng nào, recursive member không có dữ liệu đầu vào để mở rộng. Đây là truy vấn hợp lệ với kết quả rỗng, không phải lỗi do thiếu điều kiện dừng.

## 19. Checklist tư duy trước khi viết recursive CTE

Khi gặp một bài toán đệ quy, có thể tự đặt các câu hỏi:

1. **Nút bắt đầu là gì?** Một mã cụ thể, tất cả nút gốc, hay nhiều nút thỏa điều kiện?
2. **Bước di chuyển là gì?** Đi tới con, đi tới cha, hay đi qua một bảng cạnh?
3. **Một hàng CTE cần mang thông tin gì?** ID, parent ID, độ sâu, root ID, đường dẫn, giá trị tích lũy?
4. **Điều kiện kết thúc là gì?** Hết nút kề, đạt mức sâu, đạt mục tiêu, hoặc đã đi qua nút?
5. **Dữ liệu có thể có cycle hoặc nhiều đường dẫn tới một nút không?**
6. **Một hàng kết quả đại diện cho nút hay đường đi?** Điều này ảnh hưởng `UNION ALL`, `DISTINCT` và tổng hợp.
7. **Thứ tự hiển thị cần theo cấp hay theo nhánh?** Có cần `SEARCH`, `path` hay `ORDER BY` riêng?
8. **Dialect nào đang chạy?** PostgreSQL/SQLite/MySQL/MariaDB dùng `WITH RECURSIVE`; SQL Server/Oracle dùng `WITH`; Oracle còn có `CONNECT BY`.
9. **Giới hạn kỹ thuật và chỉ mục phù hợp là gì?** Độ sâu, timeout, index theo chiều duyệt, thống kê và kế hoạch thực thi.
10. **Kết quả có được dùng tiếp để tính tổng hoặc phân quyền không?** Nếu có, tránh đếm lặp nút và xác định rõ quyền truy cập của các cấp.

## 20. Tổng kết

**Recursive CTE** giúp SQL xử lý những quan hệ có **số cấp không biết trước**, nhất là cây tổ chức, phân cấp sản phẩm, phụ thuộc công việc và đường đi trong đồ thị. Một truy vấn đệ quy đáng tin cậy có:

- **Anchor** để tạo hàng bắt đầu.
- **Recursive member** để sinh hàng tiếp theo từ những hàng đã tìm được.
- **Điều kiện kết thúc và bảo vệ chu trình** phù hợp với chất lượng dữ liệu và yêu cầu nghiệp vụ.
- **Cột bổ sung** như `depth`, `root_id`, `path` khi cần đếm, hiển thị hoặc theo dõi đường đi.
- **Thứ tự đầu ra tường minh** khi kết quả cần ổn định.

Cú pháp **khác nhau theo hệ quản trị**: `WITH RECURSIVE` ở PostgreSQL, SQLite, MySQL 8+ và MariaDB; `WITH ... OPTION (MAXRECURSION n)` ở SQL Server; recursive `WITH` hoặc `START WITH ... CONNECT BY` ở Oracle. Vì vậy, luôn kiểm tra đúng **dialect, phiên bản và giới hạn thực thi** trước khi chuyển truy vấn giữa các hệ.

Điểm quan trọng nhất là hiểu **“bắt đầu ở đâu, mở rộng theo cạnh nào và khi nào phải dừng”**. Khi ba điều đó rõ ràng, truy vấn đệ quy trở thành cách diễn đạt tự nhiên và mạnh mẽ để khai thác dữ liệu phân cấp ngay trong SQL.
