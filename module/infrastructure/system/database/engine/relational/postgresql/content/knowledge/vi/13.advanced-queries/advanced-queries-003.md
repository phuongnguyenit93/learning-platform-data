# CTE đệ quy cho cây và đồ thị trong PostgreSQL

Trong hệ thống quản lý nhân sự, một phòng ban có thể thuộc phòng ban khác; trong thương mại điện tử, một danh mục sản phẩm có thể chứa nhiều danh mục con; trong hệ thống phân quyền, một vai trò có thể kế thừa từ các vai trò khác; trong vận tải, một điểm có thể có nhiều tuyến đi đến các điểm khác. Những cấu trúc này không chỉ là những hàng dữ liệu độc lập mà còn là **cây** (*tree*) hoặc **đồ thị** (*graph*).

PostgreSQL hỗ trợ **common table expression (CTE) đệ quy** với cú pháp `WITH RECURSIVE`. Nhờ đó, ta có thể bắt đầu từ một hoặc nhiều nút, đi theo liên kết giữa các hàng, tiếp tục qua nhiều cấp rồi tổng hợp kết quả bằng SQL. Một CTE đệ quy thường thay thế cho việc application phải lặp đi lặp lại nhiều câu `SELECT` để đi từ cha xuống con hoặc từ con lên cha.

Bài học tập trung vào:

- Cấu trúc **anchor term**, **recursive term**, `UNION ALL`/`UNION` và cơ chế tập làm việc.
- Duyệt cây từ gốc xuống lá, tìm tổ tiên, hậu duệ, đường dẫn (*breadcrumb*), cấp sâu và các nút lá.
- Khác biệt giữa **cây** và **đồ thị có nhiều đường đi hoặc chu trình**.
- Cách tránh vòng lặp bằng mảng đường đi hoặc cú pháp `CYCLE` của PostgreSQL.
- Sắp thứ tự kết quả theo chiều rộng (**BFS**) và chiều sâu (**DFS**) bằng đường dẫn hoặc `SEARCH`.
- Các giới hạn về tài nguyên, hiệu năng, tính đúng của kết quả và bài tập thực hành.

Các ví dụ dùng một schema riêng `cte_lab_164` và SQL dành cho PostgreSQL hiện đại. Tính năng `SEARCH`/`CYCLE` được giới thiệu từ **PostgreSQL 14**; các ví dụ dùng đường dẫn dạng mảng vẫn là lựa chọn phù hợp khi cần hỗ trợ những phiên bản cũ hơn.

## 1. Hiểu cây, đồ thị, nút và cạnh

Một **nút** (*node/vertex*) là đối tượng, chẳng hạn phòng ban, tài khoản hoặc điểm giao thông. Một **cạnh** (*edge*) thể hiện quan hệ từ nút này tới nút khác, chẳng hạn “phòng ban A quản lý phòng ban B”.

### 1.1. Cây: mỗi nút con có một cha

Trong một cây có gốc:

- **Root (gốc):** không có cha.
- **Parent (cha):** nút có một hoặc nhiều con.
- **Child (con):** nút thuộc một cha.
- **Leaf (lá):** nút không có con.
- **Ancestor (tổ tiên):** các nút ở phía trên một nút.
- **Descendant (hậu duệ):** các nút ở phía dưới một nút.
- **Depth (độ sâu):** số cạnh từ gốc hoặc nút bắt đầu tới nút hiện tại.

~~~text
Công ty (1)                        depth = 0
├── Kỹ thuật (2)                   depth = 1
│   ├── Nền tảng (4)                depth = 2
│   │   ├── API (6)                 depth = 3
│   │   └── Hạ tầng (7)             depth = 3
│   └── Dữ liệu (5)                 depth = 2
│       └── Phân tích (8)           depth = 3
└── Kinh doanh (3)                  depth = 1
    ├── Doanh nghiệp (9)            depth = 2
    └── Bán lẻ (10)                 depth = 2
~~~

Nếu mỗi nút chỉ có tối đa một cha, không có chu trình và mọi nút đều nối được với gốc, đó là một cây. Nếu có **nhiều gốc**, tập hợp nhiều cây thường gọi là **rừng** (*forest*).

### 1.2. Đồ thị: một nút có thể nhận nhiều cạnh và xuất hiện chu trình

Một đồ thị có hướng có thể có:

~~~text
A --> B --> D --> E
|     |     |     |
|     |     +-----+
|     |           |
|     +---- H     v
v                B
C --> D
|
+--> F --> G --> H
~~~

Đường từ `A` tới `D` có thể đi qua `B` hoặc `C`; đó là **nhiều đường đi đến cùng một nút**. Các cạnh `B → D → E → B` tạo thành một **chu trình**. Một truy vấn đệ quy đi theo cạnh mà không kiểm soát điểm đã đi qua có thể lặp vô hạn về mặt logic hoặc chạy cho đến khi bị giới hạn tài nguyên/timeout.

### 1.3. Đường đi khác tập nút có thể tới

Hai câu hỏi thường bị nhầm:

1. **Reachability (khả năng đi tới):** từ A có thể tới được **những nút nào**?
2. **Path enumeration (liệt kê đường đi):** từ A tới H có **những đường nào**, qua các nút nào, độ dài bao nhiêu?

Câu hỏi thứ nhất thường cần **khử trùng nút**. Câu hỏi thứ hai cần **giữ các đường đi khác nhau**, kể cả khi chúng kết thúc ở cùng một nút. Cách chọn `UNION`, `UNION ALL` và trạng thái trong CTE phụ thuộc trực tiếp vào mục tiêu này.

## 2. Ôn lại CTE thông thường trước khi dùng RECURSIVE

CTE là kết quả trung gian có tên, được định nghĩa trong cùng một câu SQL bằng `WITH`:

~~~sql
WITH paid_orders AS (
    SELECT order_id, customer_id, net_amount
    FROM some_orders
    WHERE status = 'PAID'
)
SELECT
    customer_id,
    COUNT(*) AS paid_count,
    SUM(net_amount) AS paid_amount
FROM paid_orders
GROUP BY customer_id;
~~~

`some_orders` trong ví dụ chỉ là bảng giả định. CTE này **không đệ quy**: nó không tự tham chiếu tên `paid_orders` bên trong phần định nghĩa.

CTE đệ quy khác ở chỗ phần truy vấn có thể **tham chiếu kết quả đã tìm ở bước trước** để tiếp tục đi thêm một cấp.

~~~sql
WITH RECURSIVE cte_name AS (
    -- 1. Anchor: hàng khởi đầu
    SELECT ...

    UNION ALL

    -- 2. Recursive term: dùng cte_name để tìm hàng tiếp theo
    SELECT ...
    FROM some_table AS next_node
    JOIN cte_name AS previous_step
      ON ...
)
SELECT *
FROM cte_name;
~~~

`WITH RECURSIVE` không chỉ dành cho cây và đồ thị; nó còn có thể sinh chuỗi số, dãy ngày hoặc truy vấn các quan hệ phụ thuộc nhiều cấp. Tuy nhiên, cây/đồ thị là nơi khả năng này đặc biệt có ích.

## 3. Anchor, recursive term và UNION ALL hoạt động thế nào?

Một truy vấn đệ quy PostgreSQL thường có dạng:

~~~sql
WITH RECURSIVE walk AS (
    SELECT ...        -- anchor
    UNION ALL
    SELECT ...        -- recursive term tham chiếu walk
)
SELECT ... FROM walk;
~~~

Các phần:

| Thành phần | Vai trò |
| --- | --- |
| `WITH RECURSIVE` | Cho phép định nghĩa CTE theo dạng truy vấn đệ quy |
| Anchor (phần không đệ quy) | Tạo các hàng bắt đầu |
| `UNION ALL` hoặc `UNION` | Kết hợp kết quả khởi đầu và kết quả đi thêm cấp |
| Recursive term | Dùng kết quả của vòng trước để tìm hàng mới |
| Điều kiện liên kết | Quyết định “từ nút hiện tại sẽ đi đến nút nào” |
| Điều kiện dừng | Không còn nút mới, gặp giới hạn hoặc bị ngăn chu trình |
| SELECT ngoài | Lọc, sắp xếp và trình bày toàn bộ kết quả |

PostgreSQL **đánh giá truy vấn đệ quy theo quy trình lặp**, dù cú pháp và mô hình tư duy là đệ quy. Ở mỗi vòng, nó xử lý một **working table** chứa các hàng vừa phát hiện ở vòng trước, tạo thêm hàng mới, rồi tiếp tục đến khi working table rỗng.

### 3.1. Ví dụ ngắn: sinh các số từ 1 tới 5

~~~sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1                 -- anchor
    UNION ALL
    SELECT n + 1             -- recursive term
    FROM numbers
    WHERE n < 5             -- điều kiện dừng
)
SELECT n
FROM numbers
ORDER BY n;
~~~

Kết quả:

~~~text
n
-
1
2
3
4
5
~~~

Cách diễn tiến:

| Vòng | Working table đầu vào | Hàng mới |
| --- | --- | --- |
| Anchor | Chưa có | 1 |
| 1 | 1 | 2 |
| 2 | 2 | 3 |
| 3 | 3 | 4 |
| 4 | 4 | 5 |
| 5 | 5 | Không có, dừng |

Nếu bỏ `WHERE n < 5`, truy vấn sẽ tiếp tục sinh số theo công thức đệ quy và **không có điểm dừng logic**. PostgreSQL không tự đặt một mức đệ quy nhỏ cố định kiểu “100 cấp” để đảm bảo câu SQL luôn an toàn. Vì vậy, điều kiện dừng và kiểm soát chu trình là trách nhiệm thiết kế truy vấn.

### 3.2. Kiểu cột phải thống nhất giữa hai nhánh

Mỗi cột mà anchor trả ra phải tương thích về kiểu với cột tương ứng của recursive term. Ví dụ:

~~~sql
WITH RECURSIVE steps(depth, label) AS (
    SELECT 0::integer, 'Bắt đầu'::text
    UNION ALL
    SELECT depth + 1, ('Bước ' || (depth + 1)::text)
    FROM steps
    WHERE depth < 3
)
SELECT depth, label
FROM steps
ORDER BY depth;
~~~

Ép kiểu `0::integer` và `'Bắt đầu'::text` giúp định nghĩa kiểu cột rõ ràng. Khi dùng mảng đường đi, mảng trong anchor và phép nối phần tử ở recursive term cũng phải cùng loại (ví dụ `bigint[]`).

### 3.3. Vì sao thường dùng UNION ALL?

`UNION ALL` giữ **mọi hàng**, kể cả hàng trùng. Nó thường ít tốn chi phí hơn `UNION` vì không cần loại trùng ở từng vòng, và thích hợp cho **cây đã đảm bảo không có chu trình**, nơi mỗi nút chỉ nhận một đường đi từ gốc.

`UNION` khử trùng theo **toàn bộ các cột được trả về**; nó có thể hữu ích trong bài toán chỉ cần tập nút đã đi tới, nhưng **không tự động chặn mọi chu trình** khi có cột `depth` hoặc `path` thay đổi qua mỗi vòng. Phần đồ thị sẽ giải thích cụ thể.

## 4. Tạo dữ liệu cây phòng ban

Ta dùng bảng **adjacency list**, trong đó mỗi nút lưu ID của cha:

~~~text
node_id | node_name | parent_id
--------+-----------+----------
1       | Công ty   | NULL
2       | Kỹ thuật  | 1
4       | Nền tảng  | 2
6       | API       | 4
...
~~~

Đây là một mô hình lưu trữ phổ biến cho cây: dễ thêm nút, đổi tên và biểu diễn khóa ngoại cha–con. Đổi lại, việc truy vấn toàn bộ hậu duệ hay tổ tiên không còn là phép join một cấp, nên `WITH RECURSIVE` rất hữu ích.

### 4.1. Tạo schema, bảng và ràng buộc

Chỉ chạy phần DDL dưới đây trên **database lab**, nơi bạn có quyền tạo đối tượng mới:

~~~sql
CREATE SCHEMA cte_lab_164;

CREATE TABLE cte_lab_164.org_nodes (
    node_id BIGINT PRIMARY KEY,
    parent_id BIGINT NULL,
    node_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_org_parent
        FOREIGN KEY (parent_id)
        REFERENCES cte_lab_164.org_nodes(node_id)
        ON DELETE RESTRICT,

    CONSTRAINT org_not_own_parent
        CHECK (parent_id IS NULL OR parent_id <> node_id)
);

CREATE INDEX idx_org_nodes_parent
    ON cte_lab_164.org_nodes(parent_id);
~~~

Các chi tiết:

- `node_id` là khóa chính của nút.
- `parent_id` tham chiếu `node_id` của **chính bảng này**.
- `NULL` của `parent_id` biểu thị một nút gốc.
- `ON DELETE RESTRICT` ngăn xóa một nút cha đang có con tham chiếu.
- `CHECK (parent_id <> node_id)` cấm **một nút tự trỏ trực tiếp tới chính nó**.
- Index trên `parent_id` có thể giúp bước tìm tất cả con của một nút.

**Lưu ý quan trọng:** `FOREIGN KEY` cùng với `CHECK (parent_id <> node_id)` **không chứng minh cây không có chu trình dài hơn một cạnh**. Ví dụ A trỏ B, B trỏ C, C trỏ A vẫn có thể thỏa từng FK. Việc cấm cycle có thể cần kiểm tra nghiệp vụ trong transaction, trigger/quy trình cập nhật an toàn hoặc cấu trúc dữ liệu khác.

### 4.2. Nạp dữ liệu theo thứ tự cha trước con

~~~sql
INSERT INTO cte_lab_164.org_nodes
    (node_id, parent_id, node_name, sort_order)
VALUES
    (1, NULL, 'Công ty', 1),
    (11, NULL, 'Hỗ trợ', 2);

INSERT INTO cte_lab_164.org_nodes
    (node_id, parent_id, node_name, sort_order)
VALUES
    (2, 1, 'Kỹ thuật', 1),
    (3, 1, 'Kinh doanh', 2),
    (12, 11, 'Hỗ trợ cấp 1', 1),
    (13, 11, 'Hỗ trợ cấp 2', 2);

INSERT INTO cte_lab_164.org_nodes
    (node_id, parent_id, node_name, sort_order)
VALUES
    (4, 2, 'Nền tảng', 1),
    (5, 2, 'Dữ liệu', 2),
    (9, 3, 'Doanh nghiệp', 1),
    (10, 3, 'Bán lẻ', 2);

INSERT INTO cte_lab_164.org_nodes
    (node_id, parent_id, node_name, sort_order)
VALUES
    (6, 4, 'API', 1),
    (7, 4, 'Hạ tầng', 2),
    (8, 5, 'Phân tích', 1);
~~~

Bộ dữ liệu có **13 nút** thuộc hai cây: gốc `1` (*Công ty*) và gốc `11` (*Hỗ trợ*). Trong cây `Công ty` có 10 nút: `1` đến `10`.

~~~mermaid
flowchart TB
    A["1 · Công ty"] --> B["2 · Kỹ thuật"]
    A --> C["3 · Kinh doanh"]
    B --> D["4 · Nền tảng"]
    B --> E["5 · Dữ liệu"]
    D --> F["6 · API"]
    D --> G["7 · Hạ tầng"]
    E --> H["8 · Phân tích"]
    C --> I["9 · Doanh nghiệp"]
    C --> J["10 · Bán lẻ"]
    K["11 · Hỗ trợ"] --> L["12 · Hỗ trợ cấp 1"]
    K --> M["13 · Hỗ trợ cấp 2"]
~~~

### 4.3. Xem bảng ở dạng không đệ quy

~~~sql
SELECT
    node_id,
    parent_id,
    node_name,
    sort_order
FROM cte_lab_164.org_nodes
ORDER BY node_id;
~~~

Ở dữ liệu bảng, mỗi hàng chỉ biết **cha trực tiếp**. Để biết đường `Công ty → Kỹ thuật → Dữ liệu → Phân tích`, ta cần duyệt quan hệ nhiều cấp.

## 5. Từ gốc đi xuống: lấy toàn bộ cây con

Truy vấn căn bản nhất: từ nút `1`, tìm tất cả hậu duệ ở mọi cấp.

~~~sql
WITH RECURSIVE subtree AS (
    -- Anchor: nút bắt đầu.
    SELECT
        n.node_id,
        n.parent_id,
        n.node_name,
        0::integer AS depth
    FROM cte_lab_164.org_nodes AS n
    WHERE n.node_id = 1

    UNION ALL

    -- Recursive: tìm con của những nút đã tìm được.
    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        parent_step.depth + 1 AS depth
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS parent_step
        ON child.parent_id = parent_step.node_id
)
SELECT
    node_id,
    parent_id,
    node_name,
    depth
FROM subtree
ORDER BY depth, node_id;
~~~

Kết quả được sắp theo cấp:

| Depth | Các nút |
| ---: | --- |
| 0 | 1 — Công ty |
| 1 | 2 — Kỹ thuật; 3 — Kinh doanh |
| 2 | 4 — Nền tảng; 5 — Dữ liệu; 9 — Doanh nghiệp; 10 — Bán lẻ |
| 3 | 6 — API; 7 — Hạ tầng; 8 — Phân tích |

Truy vấn trả **10 hàng**, bao gồm chính nút bắt đầu `1`. Nếu yêu cầu chỉ lấy **hậu duệ không gồm chính nó**, thêm:

~~~sql
-- Áp dụng vào SELECT ngoài:
WHERE depth > 0
~~~

và số hàng là **9**.

### 5.1. Vì sao JOIN đúng hướng?

~~~sql
JOIN subtree AS parent_step
    ON child.parent_id = parent_step.node_id
~~~

Ở đây `parent_step.node_id` là nút đang xét; PostgreSQL tìm `child.parent_id` trỏ về nút đó. Đó là hướng **cha → con**.

Nếu viết ngược lại:

~~~sql
-- Hướng lên cha, không phải xuống con:
JOIN subtree AS current_step
    ON parent.node_id = current_step.parent_id
~~~

thì truy vấn đi về phía **tổ tiên**, phù hợp một mục tiêu khác.

### 5.2. Bắt đầu từ một nhánh bất kỳ

Chỉ cần đổi anchor:

~~~sql
WHERE n.node_id = 2
~~~

thì subtree của `Kỹ thuật` gồm `2, 4, 5, 6, 7, 8`, tổng cộng **6 nút**. Nút `Kinh doanh` và hai nhánh hỗ trợ không được chọn.

Với truy vấn nhiều tham số, nên dùng biến bind từ ứng dụng cho ID gốc thay vì nối chuỗi SQL. Ví dụ ở Java/JDBC:

~~~java
String sql = """
    WITH RECURSIVE subtree AS (
        SELECT node_id, parent_id, node_name, 0 AS depth
        FROM cte_lab_164.org_nodes
        WHERE node_id = ?
        UNION ALL
        SELECT n.node_id, n.parent_id, n.node_name, t.depth + 1
        FROM cte_lab_164.org_nodes AS n
        JOIN subtree AS t
          ON n.parent_id = t.node_id
    )
    SELECT node_id, parent_id, node_name, depth
    FROM subtree
    ORDER BY depth, node_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 2L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(
                rs.getLong("node_id") + " | " +
                rs.getInt("depth") + " | " +
                rs.getString("node_name")
            );
        }
    }
}
~~~

Đoạn Java giả định `connection` đã là một JDBC `Connection` hợp lệ, dùng Java hỗ trợ text block. Dùng bind parameter giúp tách dữ liệu khỏi câu SQL; việc kiểm soát quyền truy cập nhánh cây vẫn là trách nhiệm của ứng dụng/database.

## 6. Đọc từng vòng đệ quy theo mô hình working table

Ở truy vấn subtree từ `node_id = 1`:

| Vòng | Đầu vào | Tìm được nút con |
| --- | --- | --- |
| Anchor | Chưa có | 1 |
| 1 | 1 | 2, 3 |
| 2 | 2, 3 | 4, 5, 9, 10 |
| 3 | 4, 5, 9, 10 | 6, 7, 8 |
| 4 | 6, 7, 8 | Không có |

Khi không tìm được hàng mới, truy vấn kết thúc. PostgreSQL triển khai recursive evaluation theo vòng và thường tạo đầu ra trong quá trình này theo dạng **breadth-first**, nhưng **không nên dựa vào thứ tự trả hàng tự nhiên như một hợp đồng thứ tự ổn định**. Khi cần hiển thị theo độ sâu hoặc đường đi, phải có `ORDER BY` ngoài cùng.

### 6.1. Một bản ghi có thể xuất hiện bao nhiêu lần?

Trong **cây hợp lệ**, khi đi xuống từ một gốc, mỗi nút có đúng một đường đi đến nó, nên `UNION ALL` không làm nhân bản cùng nút do nhiều cha.

Trong **đồ thị**, một nút có thể được tìm bằng nhiều đường; với `UNION ALL`, mỗi đường tạo một hàng kết quả riêng. Nếu đồ thị có chu trình và không có điều kiện dừng, việc lặp lại có thể tiếp diễn mãi.

### 6.2. Không có cơ chế đệ quy sâu 100 tầng tự động

PostgreSQL không có lựa chọn phổ biến tương đương biến cấu hình `MAXRECURSION 100` của một số hệ quản trị khác. Cần tự thiết kế dừng bằng:

- Cấu trúc cây **bảo đảm không chu trình**;
- Tập nút đã thăm hoặc đường đi hiện tại;
- Điều kiện `depth < :max_depth` nếu nghiệp vụ chấp nhận giới hạn;
- `statement_timeout` hoặc giới hạn ứng dụng như một lớp bảo vệ vận hành.

**Giới hạn số cấp không chứng minh dữ liệu không có chu trình**; nó chỉ chặn truy vấn đi sâu hơn số cấp cho phép.

## 7. Từ lá đi lên: tìm toàn bộ tổ tiên

Giả sử đang ở nút `8 — Phân tích` và muốn biết chuỗi quản lý tới gốc.

~~~sql
WITH RECURSIVE ancestors AS (
    -- Anchor: nút hiện tại.
    SELECT
        n.node_id,
        n.parent_id,
        n.node_name,
        0::integer AS distance_to_start
    FROM cte_lab_164.org_nodes AS n
    WHERE n.node_id = 8

    UNION ALL

    -- Tìm cha của nút hiện tại.
    SELECT
        parent.node_id,
        parent.parent_id,
        parent.node_name,
        a.distance_to_start + 1
    FROM cte_lab_164.org_nodes AS parent
    JOIN ancestors AS a
        ON parent.node_id = a.parent_id
)
SELECT
    node_id,
    node_name,
    distance_to_start
FROM ancestors
ORDER BY distance_to_start DESC;
~~~

Kết quả từ gốc tới nút:

| Nút | Tên | Khoảng cách tới 8 |
| ---: | --- | ---: |
| 1 | Công ty | 3 |
| 2 | Kỹ thuật | 2 |
| 5 | Dữ liệu | 1 |
| 8 | Phân tích | 0 |

Ở đây `distance_to_start` đo **số cạnh đi lên từ nút ban đầu**, nên gốc có giá trị lớn nhất. Nếu cần cấp tính từ gốc, có thể đảo lại thứ tự hoặc lấy giá trị sâu nhất trừ khoảng cách.

### 7.1. Chỉ lấy tổ tiên, không gồm nút hiện tại

Trong truy vấn ngoài:

~~~sql
WHERE distance_to_start > 0
~~~

Kết quả gồm `1, 2, 5`.

### 7.2. Khi nút bắt đầu là gốc

Nếu anchor là `1` hoặc `11`, không có cha. CTE vẫn trả **một hàng anchor với distance = 0**, rồi dừng ngay.

### 7.3. Vì sao truy vấn khác với tìm hậu duệ?

Truy vấn xuống cây join `child.parent_id = current.node_id`. Truy vấn lên cây join `parent.node_id = current.parent_id`. Dù bảng giống nhau, **đổi hướng cạnh có thể thay đổi hoàn toàn tập kết quả và điều kiện dừng**.

## 8. Tạo breadcrumb và đường dẫn đầy đủ

Một ứng dụng phân cấp thường muốn hiển thị:

~~~text
Công ty / Kỹ thuật / Dữ liệu / Phân tích
~~~

CTE có thể mang thêm cột **đường đi** (*path*) bằng mảng PostgreSQL.

### 8.1. Đường đi bằng mảng tên

~~~sql
WITH RECURSIVE ancestors AS (
    SELECT
        n.node_id,
        n.parent_id,
        ARRAY[n.node_name]::text[] AS name_path,
        0::integer AS level_up
    FROM cte_lab_164.org_nodes AS n
    WHERE n.node_id = 8

    UNION ALL

    SELECT
        parent.node_id,
        parent.parent_id,
        ARRAY[parent.node_name]::text[] || a.name_path,
        a.level_up + 1
    FROM cte_lab_164.org_nodes AS parent
    JOIN ancestors AS a
        ON parent.node_id = a.parent_id
)
SELECT
    node_id AS root_id,
    array_to_string(name_path, ' / ') AS breadcrumb
FROM ancestors
WHERE parent_id IS NULL;
~~~

Trong bài lab, kết quả:

~~~text
root_id = 1
breadcrumb = Công ty / Kỹ thuật / Dữ liệu / Phân tích
~~~

Ở anchor, mảng có một tên `['Phân tích']`. Mỗi vòng đi lên, biểu thức:

~~~sql
ARRAY[parent.node_name]::text[] || a.name_path
~~~

**đưa tên cha vào đầu mảng**, nên khi tới gốc, chuỗi tự có thứ tự gốc → lá.

### 8.2. Đường đi bằng ID ổn định hơn tên

Tên nút có thể trùng hoặc bị đổi; ID được thiết kế ổn định hơn. Khi cần nhận diện một nhánh chính xác, giữ thêm:

~~~sql
ARRAY[n.node_id]::bigint[] AS path_ids
~~~

Trong recursive term:

~~~sql
parent_step.path_ids || child.node_id AS path_ids
~~~

Ví dụ với nút 8: `{1,2,5,8}`. Mảng ID đặc biệt hữu ích để:

- Phát hiện nút đã nằm trên đường đi;
- Sắp xếp kết quả theo thứ tự cây;
- Xây breadcrumb tên bằng cách join hoặc ánh xạ ID về tên;
- Ghi log đường đi để điều tra dữ liệu.

Không nên coi mảng path được sinh từ một truy vấn nhất thời là khóa nghiệp vụ cố định nếu cây có thể được tái cấu trúc; khi đổi cha, path của cả subtree sẽ thay đổi.

## 9. Mang path và depth khi đi xuống cây

Phiên bản subtree đầy đủ hơn:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT
        n.node_id,
        n.parent_id,
        n.node_name,
        0::integer AS depth,
        ARRAY[n.node_id]::bigint[] AS path_ids,
        ARRAY[n.node_name]::text[] AS path_names
    FROM cte_lab_164.org_nodes AS n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        parent_step.depth + 1,
        parent_step.path_ids || child.node_id,
        parent_step.path_names || child.node_name
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS parent_step
        ON child.parent_id = parent_step.node_id
)
SELECT
    node_id,
    depth,
    path_ids,
    array_to_string(path_names, ' / ') AS breadcrumb
FROM subtree
ORDER BY path_ids;
~~~

Với cây có các ID tăng như bộ lab, `ORDER BY path_ids` sắp hàng theo **đường dẫn ID** (thứ tự từ điển của mảng). Điều này thường thể hiện dạng **depth-first** trong kết quả: bắt đầu từ nút 1, đi sâu vào nhánh 2 trước khi sang nhánh 3.

### 9.1. Đường đi làm tăng chi phí

Nếu cây sâu hàng nghìn cấp, mỗi hàng mang theo một mảng ngày càng dài. Tổng bộ nhớ, băng thông và phép nối mảng có thể đáng kể. Chỉ mang `path_ids` hoặc `path_names` khi thực sự cần; nếu chỉ muốn đếm hậu duệ, truy vấn dùng hai cột ID và depth có thể rẻ hơn.

### 9.2. Dùng ID để bảo vệ khỏi chu trình

Nếu muốn thêm điều kiện tránh lặp chính nút đã nằm trên đường đi:

~~~sql
WHERE NOT child.node_id = ANY(parent_step.path_ids)
~~~

trong recursive term. Điều kiện này phát huy tác dụng khi dữ liệu có chu trình và tránh một đường đi lặp lại nút đã thăm trên **chính đường đó**.

Nó **không đồng nghĩa duy nhất mỗi nút trong toàn bộ đồ thị**: nếu cùng nút được đến bằng hai đường khác nhau không có lặp nội bộ, nó vẫn có thể xuất hiện hai hàng, mỗi hàng có `path_ids` riêng.

## 10. Lấy nhiều cây từ tất cả gốc

Bộ dữ liệu có hai gốc `1` và `11`. Thay vì chỉ chọn một gốc, anchor lấy tất cả các hàng có `parent_id IS NULL`:

~~~sql
WITH RECURSIVE forest AS (
    SELECT
        n.node_id,
        n.parent_id,
        n.node_name,
        n.node_id AS root_id,
        0::integer AS depth,
        ARRAY[n.node_id]::bigint[] AS path_ids
    FROM cte_lab_164.org_nodes AS n
    WHERE n.parent_id IS NULL

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        f.root_id,
        f.depth + 1,
        f.path_ids || child.node_id
    FROM cte_lab_164.org_nodes AS child
    JOIN forest AS f
        ON child.parent_id = f.node_id
    WHERE NOT child.node_id = ANY(f.path_ids)
)
SELECT
    root_id,
    node_id,
    node_name,
    depth
FROM forest
ORDER BY root_id, path_ids;
~~~

`root_id` được gắn ở anchor rồi **truyền nguyên** xuống mọi nút con. Vì thế mỗi hàng cho biết mình thuộc cây nào. Trong bộ dữ liệu hợp lệ:

- `root_id = 1` có **10 nút**.
- `root_id = 11` có **3 nút**.

### 10.1. Thống kê số nút và độ sâu mỗi cây

~~~sql
WITH RECURSIVE forest AS (
    SELECT
        node_id,
        parent_id,
        node_id AS root_id,
        0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        f.root_id,
        f.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN forest AS f
        ON child.parent_id = f.node_id
)
SELECT
    root_id,
    COUNT(*) AS total_nodes,
    MAX(depth) AS max_depth
FROM forest
GROUP BY root_id
ORDER BY root_id;
~~~

Kết quả:

| root_id | total_nodes | max_depth |
| ---: | ---: | ---: |
| 1 | 10 | 3 |
| 11 | 3 | 1 |

Ở đây giả định quan hệ cha–con tạo forest hợp lệ. Nếu tồn tại một **chu trình tách rời không có nút gốc**, truy vấn bắt đầu ở `parent_id IS NULL` có thể **không bao giờ đi đến thành phần chu trình đó**. Vì vậy, **truy vấn forest không thay thế công cụ kiểm chứng cây hợp lệ**.

## 11. Tìm nút lá và đếm số hậu duệ

### 11.1. Nút lá trong một cây con

Một nút là **lá** nếu không có nút nào nhận nó làm cha:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT node_id, parent_id, node_name
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT child.node_id, child.parent_id, child.node_name
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT
    s.node_id,
    s.node_name
FROM subtree AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM cte_lab_164.org_nodes AS child
    WHERE child.parent_id = s.node_id
)
ORDER BY s.node_id;
~~~

Trong cây `Công ty`, lá là `6, 7, 8, 9, 10` — tổng **5 nút**.

**Phân biệt hai định nghĩa:** “không có con trong toàn bộ bảng” và “không có con trong một tập kết quả đã được lọc”. Truy vấn trên kiểm tra con trong **bảng gốc**, nên một nút có con nhưng bị lọc khỏi subtree theo điều kiện riêng vẫn không bị coi là lá. Nếu nghiệp vụ định nghĩa “lá trong tập con đang hiển thị”, cần kiểm tra trên tập con tương ứng.

### 11.2. Đếm hậu duệ của một nút

~~~sql
WITH RECURSIVE subtree AS (
    SELECT node_id, parent_id, 0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE node_id = 2

    UNION ALL

    SELECT child.node_id, child.parent_id, s.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT
    COUNT(*) AS nodes_including_start,
    COUNT(*) FILTER (WHERE depth > 0) AS descendants_only,
    MAX(depth) AS deepest_relative_level
FROM subtree;
~~~

Với `Kỹ thuật`:

- `nodes_including_start = 6`.
- `descendants_only = 5`.
- `deepest_relative_level = 2`.

Độ sâu tương đối `2` ở đây tính từ nút `2`, không phải từ gốc toàn hệ thống.

### 11.3. Đếm hậu duệ cho **mọi nút**

Nếu muốn mỗi nút có một số đếm hậu duệ, có thể khởi đầu từ **tất cả nút** và truyền một cột `ancestor_id` theo nhánh:

~~~sql
WITH RECURSIVE reach AS (
    SELECT
        n.node_id AS ancestor_id,
        n.node_id AS descendant_id,
        ARRAY[n.node_id]::bigint[] AS path_ids
    FROM cte_lab_164.org_nodes AS n

    UNION ALL

    SELECT
        r.ancestor_id,
        child.node_id AS descendant_id,
        r.path_ids || child.node_id
    FROM reach AS r
    JOIN cte_lab_164.org_nodes AS child
        ON child.parent_id = r.descendant_id
    WHERE NOT child.node_id = ANY(r.path_ids)
)
SELECT
    ancestor_id,
    COUNT(*) - 1 AS descendants_count
FROM reach
GROUP BY ancestor_id
ORDER BY ancestor_id;
~~~

Mỗi anchor bắt đầu bằng một hàng tự đại diện cho nút đó. Vì vậy, `COUNT(*) - 1` loại chính nút tổ tiên khỏi tổng.

Ví dụ:

| ancestor_id | descendants_count |
| ---: | ---: |
| 1 | 9 |
| 2 | 5 |
| 4 | 2 |
| 5 | 1 |
| 6 | 0 |
| 11 | 2 |

**Chi phí:** truy vấn từ mọi nút có thể tạo số hàng cỡ tổng số cặp **tổ tiên–hậu duệ**. Trong cây dạng chuỗi sâu `N` cấp, số cặp có thể tăng theo **O(N²)**. Với cây lớn, nếu báo cáo thường xuyên, cần cân nhắc cache, bảng closure, số liệu tiền tính sẵn hoặc cách lưu trữ khác, thay vì tính lại cho mọi nút ở mỗi request.

## 12. Tính cấp của nút và tìm đường đi ngắn trong cây

Trong một cây hợp lệ, từ gốc tới mỗi nút chỉ có một đường. Vì thế `depth` sinh từ truy vấn đệ quy **chính là số cạnh ngắn nhất và duy nhất** từ gốc tới nút.

~~~sql
WITH RECURSIVE levels AS (
    SELECT
        node_id,
        parent_id,
        0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        levels.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN levels
        ON child.parent_id = levels.node_id
)
SELECT
    node_id,
    depth
FROM levels
WHERE node_id = 8;
-- node_id = 8, depth = 3
~~~

Trong **đồ thị có nhiều đường đi**, depth của một hàng chỉ là **độ dài của đường đi đã tạo ra hàng đó**; không mặc định là khoảng cách ngắn nhất tới nút. Cần mô hình traversal và khử trùng phù hợp, hoặc thuật toán đường đi ngắn nhất khi có trọng số.

### 12.1. Giới hạn cấp bằng điều kiện nghiệp vụ

Ví dụ chỉ hiển thị tối đa hai cấp dưới nút 1:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT
        node_id,
        parent_id,
        node_name,
        0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        s.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
    WHERE s.depth < 2
)
SELECT *
FROM subtree
ORDER BY depth, node_id;
~~~

Kết quả chứa cấp `0`, `1` và `2`, không có cấp `3`. Điều kiện `s.depth < 2` nằm trong recursive term, nên không chỉ ẩn hàng cuối mà còn **ngăn tạo ra các hàng sâu hơn**.

**Không nhầm giới hạn truy vấn với kiểm tra an toàn:** nếu dữ liệu có chu trình, kết quả giới hạn depth có thể dừng nhưng **chu trình vẫn tồn tại trong database**.

## 13. SEARCH BREADTH FIRST và SEARCH DEPTH FIRST (PostgreSQL 14+)

PostgreSQL 14 bổ sung cú pháp SQL tiêu chuẩn `SEARCH` để tạo **cột sắp thứ tự duyệt**. Tính năng này không yêu cầu tự xây mảng path chỉ để `ORDER BY`.

Hai kiểu cần phân biệt:

- **Breadth-first search (BFS):** ưu tiên các nút cùng cấp trước khi xuống cấp sâu hơn.
- **Depth-first search (DFS):** đi sâu theo một nhánh trước khi sang nhánh khác.

### 13.1. SEARCH BREADTH FIRST

~~~sql
WITH RECURSIVE walk(node_id, parent_id, node_name) AS (
    SELECT
        n.node_id,
        n.parent_id,
        n.node_name
    FROM cte_lab_164.org_nodes AS n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name
    FROM cte_lab_164.org_nodes AS child
    JOIN walk AS w
        ON child.parent_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
SELECT
    node_id,
    node_name,
    bfs_order
FROM walk
ORDER BY bfs_order;
~~~

PostgreSQL sinh thêm cột `bfs_order` để sắp thứ tự. `BY node_id` là khóa dùng để phân biệt thứ tự các nút ở phạm vi cần sắp. Kết quả được trình bày theo cấp (và khóa đã nêu) khi `ORDER BY bfs_order`.

### 13.2. SEARCH DEPTH FIRST

~~~sql
WITH RECURSIVE walk(node_id, parent_id, node_name) AS (
    SELECT
        node_id,
        parent_id,
        node_name
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name
    FROM cte_lab_164.org_nodes AS child
    JOIN walk AS w
        ON child.parent_id = w.node_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
SELECT
    node_id,
    node_name,
    dfs_order
FROM walk
ORDER BY dfs_order;
~~~

`dfs_order` là cột thứ tự dựa trên đường đi được tạo bởi `SEARCH DEPTH FIRST`. Truy vấn ngoài sắp theo nó để có kết quả dạng DFS.

### 13.3. SEARCH có biến thuật toán thực thi thành DFS không?

**Không nên hiểu `SEARCH DEPTH FIRST` là PostgreSQL buộc thực thi các bước theo một stack DFS.** Theo tài liệu, `SEARCH` mở rộng truy vấn bằng cột phục vụ **sắp thứ tự kết quả**; việc đánh giá recursive CTE bên dưới vẫn dùng cơ chế lặp/working table của PostgreSQL.

Vì vậy:

1. `SEARCH` không tự ngăn chu trình.
2. `SEARCH` không tự làm truy vấn dừng.
3. Kết quả hiển thị theo BFS/DFS cần `ORDER BY` cột `SET`.
4. `SEARCH` có thể tăng chi phí vì cần lưu và sắp dữ liệu đường đi/thứ tự.

Nếu cần BFS/DFS trong phiên bản cũ hơn PostgreSQL 14, có thể sắp `ORDER BY depth, node_id` hoặc `ORDER BY path_ids` theo yêu cầu, nhưng cần hiểu rằng thứ tự theo ID chỉ là một **quy ước sắp xếp**, không tự thay thứ tự con theo thuộc tính nghiệp vụ `sort_order`.

## 14. Đồ thị có hướng: lưu nút và cạnh

Để thấy rõ khác biệt giữa cây và đồ thị, ta tạo hai bảng:

~~~sql
CREATE TABLE cte_lab_164.graph_nodes (
    node_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE cte_lab_164.graph_edges (
    from_id TEXT NOT NULL
        REFERENCES cte_lab_164.graph_nodes(node_id),
    to_id TEXT NOT NULL
        REFERENCES cte_lab_164.graph_nodes(node_id),
    weight INTEGER NOT NULL DEFAULT 1
        CHECK (weight > 0),

    CONSTRAINT graph_edges_pk
        PRIMARY KEY (from_id, to_id)
);

CREATE INDEX idx_graph_edges_to
    ON cte_lab_164.graph_edges(to_id);
~~~

`from_id → to_id` biểu diễn **cạnh có hướng**. Khóa chính ghép `(from_id, to_id)` tránh lưu trùng cùng một cạnh có hướng. Nếu đồ thị **vô hướng**, thường cần quy ước lưu/khai triển hai hướng hoặc dùng biểu diễn riêng; không tự động suy ra cạnh `B → A` từ `A → B`.

### 14.1. Seed nút và cạnh

~~~sql
INSERT INTO cte_lab_164.graph_nodes
    (node_id, display_name)
VALUES
    ('A', 'Bắt đầu'),
    ('B', 'Trạm B'),
    ('C', 'Trạm C'),
    ('D', 'Trạm D'),
    ('E', 'Trạm E'),
    ('F', 'Trạm F'),
    ('G', 'Trạm G'),
    ('H', 'Đích H');

INSERT INTO cte_lab_164.graph_edges
    (from_id, to_id, weight)
VALUES
    ('A', 'B', 2),
    ('A', 'C', 3),
    ('B', 'D', 2),
    ('B', 'H', 8),
    ('C', 'D', 1),
    ('C', 'F', 2),
    ('D', 'E', 1),
    ('E', 'B', 1),
    ('F', 'G', 2),
    ('G', 'H', 2);
~~~

Đồ thị có nhiều đường tới `D`, `H` và một chu trình:

~~~text
B -> D -> E -> B
~~~

Một số đường đơn (*simple path*, không lặp nút) từ A tới H:

~~~text
A -> B -> H
A -> C -> F -> G -> H
A -> C -> D -> E -> B -> H
~~~

Trong bài này, `weight` là **chi phí dương của cạnh** để minh họa tổng trọng số. Các truy vấn dùng BFS/depth không tự giải bài toán **đường đi có tổng weight nhỏ nhất** trong đồ thị bất kỳ.

## 15. Duyệt đồ thị với UNION ALL: tại sao cần chống chu trình?

Truy vấn ngây thơ:

~~~sql
-- CẢNH BÁO: không chạy trực tiếp trên graph_edges có cycle.
-- Truy vấn thiếu cơ chế chống chu trình:
--
-- WITH RECURSIVE walk AS (
--     SELECT 'A'::text AS node_id
--     UNION ALL
--     SELECT e.to_id
--     FROM walk AS w
--     JOIN cte_lab_164.graph_edges AS e
--       ON e.from_id = w.node_id
-- )
-- SELECT * FROM walk;
~~~

Khi đi tới `B`, truy vấn có thể sang `D`, sang `E` rồi quay lại `B`, tạo `B, D, E, B, D, E,...`. Vì `UNION ALL` không loại trùng, working table tiếp tục có hàng mới.

### 15.1. Cách đơn giản cho reachability: UNION chỉ giữ node_id

Nếu mục tiêu là **những nút nào có thể tới từ A**, không cần biết từng đường đi hay cấp sâu, có thể dùng `UNION`:

~~~sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 'A'::text

    UNION

    SELECT e.to_id
    FROM reachable AS r
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
~~~

Kết quả: **A, B, C, D, E, F, G, H** — tám nút duy nhất.

`UNION` loại trùng trên **toàn bộ hàng CTE**, và ở đây hàng chỉ có một cột `node_id`. Khi gặp lại `B`, nó không tạo thành một giá trị mới trong kết quả, nên không cần mở rộng vô hạn theo cùng nút đó.

**Đây là một trường hợp cụ thể `UNION` có thể đóng vai trò khử vòng lặp hiệu quả:** chỉ cần tập nút đã tới, và trạng thái recursive không chứa thông tin làm thay đổi bản ghi khi quay lại nút.

### 15.2. Vì sao UNION không tự giải quyết khi thêm depth?

~~~sql
-- CẢNH BÁO: không chạy truy vấn sau trên graph có cycle.
--
-- WITH RECURSIVE walk(node_id, depth) AS (
--     SELECT 'A'::text, 0::integer
--     UNION
--     SELECT e.to_id, w.depth + 1
--     FROM walk AS w
--     JOIN cte_lab_164.graph_edges AS e
--       ON e.from_id = w.node_id
-- )
-- SELECT * FROM walk;
~~~

Hàng `('B', 1)` **khác** hàng `('B', 4)` vì giá trị depth khác. `UNION` khử trùng theo cả hai cột, nên một chu trình tạo ra các hàng mới với depth ngày càng tăng.

Tương tự, nếu CTE lưu `path`, cùng nút ở cuối những path khác nhau vẫn là **các hàng khác nhau**. Cần cơ chế chống chu trình rõ ràng cho loại truy vấn này.

## 16. Chống chu trình bằng mảng path

Một mẫu thực dụng là lưu **tập nút của đường đi đang xét** dưới dạng mảng. Trước khi đi theo cạnh mới, kiểm tra nút đích chưa nằm trong mảng đó.

~~~sql
WITH RECURSIVE paths AS (
    SELECT
        'A'::text AS node_id,
        0::integer AS depth,
        ARRAY['A']::text[] AS path_ids

    UNION ALL

    SELECT
        e.to_id AS node_id,
        p.depth + 1,
        p.path_ids || e.to_id
    FROM paths AS p
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = p.node_id
    WHERE NOT e.to_id = ANY(p.path_ids)
)
SELECT
    node_id,
    depth,
    array_to_string(path_ids, ' -> ') AS route
FROM paths
ORDER BY depth, route;
~~~

**Giải thích:**

1. Anchor tạo đường đi ban đầu `{A}`.
2. Mỗi vòng lấy cạnh đi ra từ nút cuối hiện tại.
3. `e.to_id = ANY(p.path_ids)` kiểm tra nút đích đã có trên **đường đi đó** chưa.
4. `NOT ...` chỉ cho phép nối một nút chưa xuất hiện, nên không thể đi `B → D → E → B` trên cùng đường.

Vì đồ thị có 8 nút, một **simple path** chỉ chứa tối đa 8 nút. Điều này bảo đảm tập đường đi không mở rộng vô hạn bằng chu trình khi graph hữu hạn.

### 16.1. Đường đi có thể tới cùng một nút qua nhiều nhánh

`A → B → D` và `A → C → D` đều hợp lệ vì `D` chưa xuất hiện **trên từng đường đi riêng**. Kết quả có thể có hai hàng `node_id = 'D'` với hai `path_ids` khác nhau.

Đây là điểm khác giữa:

- **Path-local visited set:** ngăn một nút xuất hiện lặp lại **trong cùng đường đi**.
- **Global visited set:** xử lý mỗi nút một lần, cần cho một số bài toán reachability/BFS tối ưu.

CTE đệ quy với mảng path như trên là cách liệt kê các đường đơn, **không có global visited set chung để chặn mọi đường trùng nút cuối**.

### 16.2. Chi phí liệt kê đường đi có thể rất lớn

Mặc dù không còn vòng lặp vô hạn, số **simple paths** giữa hai nút của một đồ thị nhiều nhánh có thể tăng rất nhanh, thậm chí theo hàm mũ ở nhiều lớp đồ thị. Vì vậy:

~~~sql
WHERE NOT e.to_id = ANY(p.path_ids)
~~~

giải quyết **tính dừng**, nhưng **không đảm bảo truy vấn rẻ**. Với đồ thị lớn, cần giới hạn độ sâu, phạm vi nút, quyền truy cập hoặc áp dụng thuật toán/bộ nhớ chuyên dụng.

## 17. Liệt kê đường đi từ A tới H

Từ mẫu path, chỉ lấy các hàng kết thúc ở `H`:

~~~sql
WITH RECURSIVE paths AS (
    SELECT
        'A'::text AS node_id,
        ARRAY['A']::text[] AS path_ids,
        0::integer AS hops

    UNION ALL

    SELECT
        e.to_id,
        p.path_ids || e.to_id,
        p.hops + 1
    FROM paths AS p
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = p.node_id
    WHERE NOT e.to_id = ANY(p.path_ids)
)
SELECT
    hops,
    array_to_string(path_ids, ' -> ') AS route
FROM paths
WHERE node_id = 'H'
ORDER BY hops, route;
~~~

Một số đường sẽ có:

| Hops | Đường |
| ---: | --- |
| 2 | A → B → H |
| 4 | A → C → F → G → H |
| 5 | A → C → D → E → B → H |

Trong dữ liệu lab, đây là các đường đơn tới H. Truy vấn giữ **mọi đường đi**, nên `ORDER BY hops` chỉ sắp kết quả theo số cạnh, không làm phần đệ quy dừng ngay khi tìm thấy đường ngắn đầu tiên.

### 17.1. Ngăn mở rộng sau khi tới đích

Trong recursive term, có thể thêm:

~~~sql
AND p.node_id <> 'H'
~~~

để **không mở rộng tiếp các đường đã tới H**. Đây là phép cắt nhánh hữu ích khi mục tiêu chỉ là đường từ A tới H. Không nhầm nó với việc ngăn những đường khác còn đang đi đến H.

### 17.2. Chọn một đường ít cạnh nhất

~~~sql
WITH RECURSIVE paths AS (
    SELECT
        'A'::text AS node_id,
        ARRAY['A']::text[] AS path_ids,
        0::integer AS hops

    UNION ALL

    SELECT
        e.to_id,
        p.path_ids || e.to_id,
        p.hops + 1
    FROM paths AS p
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = p.node_id
    WHERE NOT e.to_id = ANY(p.path_ids)
      AND p.node_id <> 'H'
)
SELECT
    hops,
    array_to_string(path_ids, ' -> ') AS route
FROM paths
WHERE node_id = 'H'
ORDER BY hops, path_ids
LIMIT 1;
~~~

Với graph lab, đường ít cạnh nhất là **A → B → H**, gồm **2 cạnh**. Tuy nhiên, câu SQL dạng này vẫn có thể phải xây/duyệt rất nhiều đường trước khi sort/limit. Đây **không phải một triển khai BFS toàn cục tối ưu** để tìm đường ngắn nhất trên đồ thị rất lớn.

## 18. Trọng số cạnh và đường đi có chi phí nhỏ nhất

Không phải cạnh nào cũng có cùng chi phí. Trong bảng `graph_edges`, cột `weight` biểu diễn chi phí dương.

### 18.1. Cộng trọng số dọc một đường

~~~sql
WITH RECURSIVE routes AS (
    SELECT
        'A'::text AS node_id,
        ARRAY['A']::text[] AS path_ids,
        0::integer AS hops,
        0::bigint AS total_weight

    UNION ALL

    SELECT
        e.to_id,
        r.path_ids || e.to_id,
        r.hops + 1,
        r.total_weight + e.weight::bigint
    FROM routes AS r
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = r.node_id
    WHERE NOT e.to_id = ANY(r.path_ids)
      AND r.node_id <> 'H'
)
SELECT
    hops,
    total_weight,
    array_to_string(path_ids, ' -> ') AS route
FROM routes
WHERE node_id = 'H'
ORDER BY total_weight, hops, route;
~~~

Với seed:

| Đường | Hops | Tổng weight |
| --- | ---: | ---: |
| A → B → H | 2 | 10 |
| A → C → F → G → H | 4 | 9 |
| A → C → D → E → B → H | 5 | 14 |

**Đường có ít cạnh nhất (2)** không nhất thiết có **tổng trọng số nhỏ nhất (9)**. Khi routing theo khoảng cách, thời gian hoặc chi phí, phải xác định metric cần tối ưu.

### 18.2. Truy vấn CTE trên là liệt kê rồi chọn, không phải Dijkstra

Việc liệt kê simple paths và sắp theo `total_weight` có thể cho kết quả đúng trên một đồ thị **nhỏ và hữu hạn**, nhưng chi phí tính toán có thể rất cao trên đồ thị lớn. Nó **không phải thuật toán Dijkstra/A\*** được cài đặt tối ưu với priority queue và global distance map.

Nếu cần đường đi ngắn nhất theo trọng số trên đồ thị lớn, cân nhắc thư viện/engine đồ thị, thuật toán chuyên dụng hoặc mô hình dữ liệu phục vụ mục tiêu đó. Không dùng một query recursive không giới hạn để tối ưu routing quy mô lớn chỉ vì trên graph 8 nút nó chạy nhanh.

### 18.3. Không áp dụng kết luận cho cạnh có trọng số âm

Ví dụ lab quy định `weight > 0`. Khi có trọng số âm, một số thuật toán đường đi ngắn không còn áp dụng như trong trường hợp tất cả trọng số dương; chu trình trọng số âm làm bài toán tối ưu có các vấn đề đặc biệt. Cần chọn thuật toán theo điều kiện toán học của dữ liệu.

## 19. PostgreSQL CYCLE: phát hiện vòng lặp bằng cú pháp chuẩn (14+)

Từ PostgreSQL 14, `WITH RECURSIVE` có thêm mệnh đề `CYCLE`:

~~~sql
CYCLE column_name SET is_cycle USING cycle_path
~~~

PostgreSQL tạo hai cột bổ sung:

- **`is_cycle`:** đánh dấu hàng đi vào một chu trình theo các cột được chỉ định.
- **`cycle_path`:** đường đi phục vụ nhận diện chu trình.

Ví dụ trên graph:

~~~sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 'A'::text

    UNION ALL

    SELECT e.to_id
    FROM walk AS w
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    is_cycle,
    cycle_path
FROM walk
ORDER BY cycle_path;
~~~

Mệnh đề `CYCLE` giúp truy vấn **không tiếp tục mở rộng một đường sau khi đã phát hiện vòng** theo khóa được chỉ định. Hàng đánh dấu chu trình có thể xuất hiện trong kết quả, nên nếu chỉ muốn các bước chưa đi vào vòng, thêm:

~~~sql
WHERE NOT is_cycle
~~~

ở truy vấn ngoài.

### 19.1. CYCLE là path-local, không tự khử mọi đường tới cùng một nút

Trong graph lab, `D` có thể được tìm qua hai đường `A → B → D` và `A → C → D`. Cả hai **không tạo chu trình trên đường tương ứng**, nên có thể có nhiều hàng `D`. `CYCLE` phát hiện **việc quay lại một nút đã có trong path**, không biến kết quả thành danh sách reachable nodes duy nhất.

Nếu chỉ cần tập các nút, truy vấn `UNION` chỉ lưu `node_id` ở mục 15.1 thường ngắn và phù hợp hơn.

### 19.2. Dùng nhiều cột làm khóa phát hiện chu trình

Trong một số đồ thị, một nút/quan hệ được định danh bằng **tổ hợp cột**, chẳng hạn `(tenant_id, node_id)`. PostgreSQL cho phép liệt kê các cột trong `CYCLE` tương ứng với khóa cần theo dõi. Phải chọn **định danh đủ mạnh**, vì chỉ theo dõi một cột không duy nhất có thể đánh dấu sai chu trình hoặc nhầm nút của tenant khác.

### 19.3. CYCLE không sửa dữ liệu nguồn

`CYCLE` chỉ thay đổi hành vi của **truy vấn đệ quy**. Nó không thêm constraint vào bảng, không tự sửa những cạnh sai và không đảm bảo mọi lần `INSERT`/`UPDATE` sau này giữ dữ liệu không chu trình.

Trong bảng cây tự tham chiếu, muốn **ngăn việc chuyển một nút vào chính subtree của nó** cần kiểm tra/cập nhật an toàn ở tầng database/application. Truy vấn `CYCLE` hữu ích để nhận diện và xử lý khi đọc, chứ không phải một ràng buộc tự động trên mọi DML.

## 20. SEARCH và CYCLE dùng cùng nhau

Có thể kết hợp `SEARCH` để tạo khóa thứ tự và `CYCLE` để phát hiện vòng:

~~~sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 'A'::text

    UNION ALL

    SELECT e.to_id
    FROM walk AS w
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    bfs_order,
    is_cycle,
    cycle_path
FROM walk
ORDER BY bfs_order, cycle_path;
~~~

Ở đây:

1. `SEARCH BREADTH FIRST` tạo cột thứ tự hiển thị.
2. `CYCLE` bổ sung dữ liệu đánh dấu chu trình và path.
3. `ORDER BY` ngoài cùng xác định thứ tự kết quả.

Trong trường hợp sắp **depth-first** và cũng cần phát hiện cycle, `SEARCH DEPTH FIRST` và `CYCLE` có thể tạo thông tin đường đi có phần trùng lặp, gây chi phí không cần thiết. Nếu `cycle_path` đã phục vụ thứ tự mong muốn, có thể sắp dựa trên nó mà không cần tính riêng một thứ tự DFS — cần đối chiếu kiểu và mục tiêu hiển thị thực tế.

### 20.1. Đừng coi SEARCH/CYCLE là cú pháp của mọi PostgreSQL

`SEARCH` và `CYCLE` được hỗ trợ từ **PostgreSQL 14**. Nếu server ở phiên bản cũ hơn, câu lệnh có thể lỗi cú pháp. Lúc đó dùng mảng `path_ids` với `NOT node_id = ANY(path_ids)`, hoặc một phương án khử trùng/điều kiện dừng tương thích phiên bản đang vận hành.

## 21. Bảo vệ khỏi cycle trong bảng cây bị sửa sai

Trong dữ liệu cây do người dùng có thể đổi cha, một lỗi cập nhật thường gặp là:

~~~text
1 -> 2 -> 5 -> 8
           ^
           |
           8 lại được gán thành cha của 2
~~~

Nếu gán `2.parent_id = 8`, một chu trình `2 → 5 → 8 → 2` được tạo trong quan hệ con → cha. Điều này có thể **không vi phạm khóa ngoại**, bởi mọi ID đều tồn tại.

### 21.1. Kiểm tra trước khi chuyển nhánh

Ý tưởng: trước khi gán nút `2` vào cha mới `8`, hãy kiểm tra **cha mới có đang nằm trong subtree của nút 2 hay không**.

~~~sql
WITH RECURSIVE descendants AS (
    SELECT
        node_id,
        parent_id,
        ARRAY[node_id]::bigint[] AS path_ids
    FROM cte_lab_164.org_nodes
    WHERE node_id = 2

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        d.path_ids || child.node_id
    FROM cte_lab_164.org_nodes AS child
    JOIN descendants AS d
        ON child.parent_id = d.node_id
    WHERE NOT child.node_id = ANY(d.path_ids)
)
SELECT EXISTS (
    SELECT 1
    FROM descendants
    WHERE node_id = 8
) AS proposed_parent_is_in_subtree;
-- true: không nên chuyển 2 vào dưới 8.
~~~

Nếu kết quả `TRUE`, phép cập nhật đó sẽ tạo chu trình trong cây hợp lệ ban đầu.

**Cảnh báo về concurrency:** một câu `SELECT EXISTS` trước `UPDATE` trong hai transaction song song có thể không đủ đảm bảo bất biến nếu dữ liệu thay đổi giữa kiểm tra và ghi. Hệ thống yêu cầu cây luôn không chu trình cần thiết kế transaction/locking hoặc cơ chế thực thi tập trung/trigger phù hợp, rồi kiểm thử với cập nhật đồng thời.

### 21.2. Kiểm tra cycle từ mọi nút, không chỉ từ root

Một chu trình có thể không còn liên hệ với nút có `parent_id IS NULL`; truy vấn forest bắt đầu từ root sẽ **bỏ sót thành phần này**. Để kiểm tra mọi chuỗi cha, có thể bắt đầu từ **mỗi nút** và đi lên, giữ path:

~~~sql
WITH RECURSIVE parent_walk AS (
    SELECT
        n.node_id AS start_id,
        n.node_id AS current_id,
        n.parent_id,
        ARRAY[n.node_id]::bigint[] AS path_ids,
        FALSE AS cycle_found
    FROM cte_lab_164.org_nodes AS n

    UNION ALL

    SELECT
        w.start_id,
        parent.node_id,
        parent.parent_id,
        w.path_ids || parent.node_id,
        parent.node_id = ANY(w.path_ids)
    FROM parent_walk AS w
    JOIN cte_lab_164.org_nodes AS parent
        ON parent.node_id = w.parent_id
    WHERE NOT w.cycle_found
)
SELECT DISTINCT
    start_id
FROM parent_walk
WHERE cycle_found
ORDER BY start_id;
~~~

Với schema lab đang hợp lệ, kết quả **0 hàng**. Nếu dữ liệu có chu trình cha–con, có thể thấy những nút có chuỗi cha dẫn vào chu trình.

Truy vấn này thực hiện duyệt từ **mọi nút**, nên trên cây lớn có thể tốn kém. Nó minh họa một hướng kiểm tra, không phải cam kết đây là phương án kiểm toán rẻ nhất cho mọi hệ thống.

### 21.3. FK không thay bất biến cây

`FOREIGN KEY (parent_id) REFERENCES org_nodes(node_id)` chỉ đảm bảo **cha được tham chiếu tồn tại**. Nó không đảm bảo:

- Có đúng một gốc duy nhất;
- Mọi nút nối được với một gốc;
- Không có chu trình;
- Không vượt độ sâu tối đa;
- Một nút không được chuyển sang nhánh bị cấm theo nghiệp vụ.

Cần bổ sung quy tắc/kiểm tra tương ứng khi ứng dụng đòi hỏi những bất biến này.

## 22. Kết hợp tính tổng hợp trên subtree

Một bài toán thực tế là tính **doanh thu của một phòng ban và tất cả cấp con**, hoặc tổng chi phí của một cấu trúc phụ thuộc.

Tạo bảng chỉ số mẫu:

~~~sql
CREATE TABLE cte_lab_164.node_budget (
    node_id BIGINT PRIMARY KEY
        REFERENCES cte_lab_164.org_nodes(node_id),
    monthly_budget NUMERIC(14, 2) NOT NULL
        CHECK (monthly_budget >= 0)
);

INSERT INTO cte_lab_164.node_budget
    (node_id, monthly_budget)
VALUES
    (1,  1000000),
    (2,   500000),
    (3,   300000),
    (4,   250000),
    (5,   150000),
    (6,   100000),
    (7,   120000),
    (8,    80000),
    (9,    60000),
    (10,   70000),
    (11,  200000),
    (12,   40000),
    (13,   50000);
~~~

### 22.1. Tính tổng ngân sách của nhánh Kỹ thuật

~~~sql
WITH RECURSIVE subtree AS (
    SELECT node_id, parent_id
    FROM cte_lab_164.org_nodes
    WHERE node_id = 2

    UNION ALL

    SELECT child.node_id, child.parent_id
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT
    COUNT(*) AS node_count,
    SUM(b.monthly_budget) AS total_monthly_budget
FROM subtree AS s
JOIN cte_lab_164.node_budget AS b
    ON b.node_id = s.node_id;
~~~

Các nút nhánh Kỹ thuật là `2, 4, 5, 6, 7, 8`. Tổng ngân sách:

~~~text
500000 + 250000 + 150000 + 100000 + 120000 + 80000
= 1200000
~~~

Kết quả: **6 nút, tổng 1.200.000**.

### 22.2. NULL và quan hệ join

Nếu `node_budget` chỉ lưu **một số nút**, dùng `JOIN` sẽ bỏ các nút chưa có ngân sách. Nếu muốn giữ mọi nút trong subtree:

~~~sql
SELECT
    COUNT(*) AS all_nodes,
    COUNT(b.node_id) AS nodes_with_budget,
    SUM(b.monthly_budget) AS sum_known_budget
FROM subtree AS s
LEFT JOIN cte_lab_164.node_budget AS b
    ON b.node_id = s.node_id;
~~~

Đây là phần **chỉ dẫn biểu thức** đặt ở SELECT ngoài một CTE `subtree`; không chạy độc lập nếu chưa định nghĩa CTE trong cùng câu SQL.

`COUNT(*)` và `COUNT(b.node_id)` có thể khác nhau. Đừng tự coi ngân sách chưa biết là 0 trong báo cáo tài chính nếu chưa có quy tắc dữ liệu.

### 22.3. Đếm trùng trong đồ thị

Trong một cây, mỗi nút chỉ thuộc một đường từ gốc, nên `SUM(budget)` trên subtree là cách tính tự nhiên. Trong đồ thị có nhiều đường tới cùng nút, kết quả recursion có thể có **nhiều hàng cho một node_id**, dẫn tới cộng ngân sách của nút đó nhiều lần.

Nếu bài toán yêu cầu tổng chỉ tính **mỗi nút reachable một lần**, cần tách tập nút duy nhất rồi join số liệu:

~~~sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 'A'::text
    UNION
    SELECT e.to_id
    FROM reachable AS r
    JOIN cte_lab_164.graph_edges AS e
        ON e.from_id = r.node_id
)
SELECT COUNT(*) AS distinct_reachable_nodes
FROM reachable;
-- 8
~~~

Nguyên tắc này đặc biệt quan trọng khi aggregate **cost, quyền, độ phủ hoặc số người dùng** trên đồ thị có nhiều cạnh vào cùng một nút.

## 23. Cắt nhánh (pruning) và điều kiện lọc trong recursive term

Để giảm công việc, hãy đặt điều kiện chặn mở rộng trong **recursive term** khi nó đúng với nghiệp vụ.

### 23.1. Chỉ duyệt tối đa ba cấp

~~~sql
WITH RECURSIVE limited AS (
    SELECT
        node_id, parent_id, node_name, 0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        l.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN limited AS l
        ON child.parent_id = l.node_id
    WHERE l.depth < 3
)
SELECT *
FROM limited
ORDER BY depth, node_id;
~~~

Điều kiện giới hạn độ sâu ngăn tạo cấp 4 trở lên.

### 23.2. Chỉ duyệt các nút còn hoạt động

~~~sql
WITH RECURSIVE active_tree AS (
    SELECT
        node_id, parent_id, node_name
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1
      AND is_active

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name
    FROM cte_lab_164.org_nodes AS child
    JOIN active_tree AS t
        ON child.parent_id = t.node_id
    WHERE child.is_active
)
SELECT *
FROM active_tree;
~~~

Nếu một nút giữa cây bị `is_active = FALSE`, truy vấn này **không đi qua nút đó**, nên cũng **không tìm tới những hậu duệ bên dưới**, ngay cả khi hậu duệ có `is_active = TRUE`. Đây là một **quyết định nghiệp vụ**; nếu mục tiêu là “tìm mọi hậu duệ active kể cả bên dưới cha inactive”, phải đi qua nút inactive nhưng lọc chúng ở SELECT ngoài.

### 23.3. Lọc kết quả ngoài cùng không phải luôn giảm số vòng

So sánh:

~~~sql
-- Trường hợp A: chỉ loại cấp sâu ở cuối (vẫn có thể duyệt sâu).
SELECT * FROM subtree WHERE depth <= 3;
~~~

với điều kiện trong recursive term:

~~~sql
WHERE previous_step.depth < 3
~~~

Trường hợp thứ hai chủ động **không tạo cấp 4**, thường phù hợp hơn nếu chỉ cần tối đa ba cấp. Các điều kiện đưa vào recursion phải đảm bảo không vô tình bỏ mất các nút cần thiết để đi tới mục tiêu.

## 24. LIMIT, ORDER BY và nguy cơ hiểu sai tính dừng

Một cách debug được tài liệu PostgreSQL nhắc đến là đặt `LIMIT` ở SELECT ngoài khi thử CTE có nguy cơ lặp. Trong một số trường hợp, PostgreSQL chỉ lấy số hàng mà parent query yêu cầu, nên có thể **không tính tiếp mọi hàng đệ quy**.

Tuy nhiên, **không dùng `LIMIT` ngoài cùng như cơ chế chống chu trình chính thức**:

- `ORDER BY` hoặc `JOIN` ở truy vấn cha có thể cần lấy **toàn bộ kết quả** trước khi giới hạn.
- Planner, cách sử dụng CTE và thay đổi query có thể khiến hành vi khác.
- `LIMIT 10` không chứng minh kết quả đã được duyệt đủ, chỉ cho biết bạn yêu cầu hiển thị tối đa 10 hàng.
- Một graph nhiều nhánh vẫn có thể tạo lượng dữ liệu rất lớn trước khi lọc/sắp.

Mẫu an toàn hơn khi thực hành graph là **có điều kiện path tránh cycle ngay trong recursive term**, giới hạn depth nếu phù hợp, thử trên dataset nhỏ và dùng timeout vận hành.

### 24.1. Timeout trong một transaction lab

~~~sql
BEGIN;

SET LOCAL statement_timeout = '5s';

-- Chạy một truy vấn recursive có giới hạn và đã hiểu dữ liệu.
SELECT COUNT(*) FROM cte_lab_164.org_nodes;

ROLLBACK;
~~~

`SET LOCAL` chỉ có hiệu lực trong transaction hiện tại. Ví dụ trên minh họa cách đặt giới hạn thời gian cho một thao tác lab; nó **không thay thế** việc viết truy vấn có điểm dừng đúng, và không nên dùng để “chữa” dữ liệu hoặc thuật toán sai.

## 25. EXPLAIN và hiệu năng của recursive CTE

### 25.1. Quan sát Recursive Union và WorkTable Scan

~~~sql
EXPLAIN
WITH RECURSIVE subtree AS (
    SELECT
        node_id, parent_id, 0::integer AS depth
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        s.depth + 1
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT *
FROM subtree;
~~~

Một kế hoạch có thể hiển thị những thành phần như:

- **Recursive Union:** kết hợp anchor và bước đệ quy theo cơ chế recursive evaluation.
- **WorkTable Scan:** đọc các hàng của working table ở bước hiện tại.
- **Index Scan/Hash Join/Seq Scan:** các cách planner tìm nút con trong bảng gốc.
- **CTE Scan:** đọc kết quả recursive CTE ở truy vấn ngoài.

Hình dạng cụ thể của plan thay đổi theo thống kê, số hàng, phiên bản và index. `EXPLAIN` chỉ cho **ước tính kế hoạch**, không xác nhận thời gian thực.

### 25.2. Các index quan trọng

Với adjacency list:

~~~sql
CREATE INDEX idx_org_nodes_parent
ON cte_lab_164.org_nodes(parent_id);
~~~

Index này đã được tạo ở mục 4.1 nên **không chạy lệnh tạo lại** nếu index đã tồn tại. Nó giúp PostgreSQL tìm con theo `child.parent_id = current.node_id` trong nhiều tình huống.

Với đồ thị:

- Index bắt đầu bằng `from_id` hỗ trợ tìm các cạnh đi ra. Bảng `graph_edges` đã có **primary key `(from_id, to_id)`**, tạo index thích hợp cho nhiều truy vấn lọc bằng `from_id`.
- Index `to_id` hữu ích nếu thường tìm **các nút đi tới một nút**, tức truy vấn ngược chiều cạnh.
- Không tự tạo index trùng với primary key chỉ vì thấy join trên cột đó.

### 25.3. Chi phí phụ thuộc số cạnh được mở rộng

Một cây với `N` nút có số cạnh gần `N-1` trong mỗi thành phần có gốc. Truy vấn đi đúng một lần qua mỗi nút có thể khá hợp lý khi index tốt và không cần lưu path quá dài.

Một graph có hàng triệu cạnh hoặc nhiều đường đi trùng nút thì khác:

- `UNION ALL` không khử trùng có thể mở rộng rất nhiều đường.
- `UNION` cần duy trì tập giá trị đã gặp để loại trùng.
- Mảng `path_ids` dài làm tăng bộ nhớ và chi phí kiểm tra `ANY`.
- `SEARCH` và `ORDER BY` có thể cần sort lớn.
- Tổng hợp mọi cặp tổ tiên–hậu duệ có thể tạo nhiều hàng hơn số nút.

Không có công thức “CTE đệ quy luôn nhanh/chậm” chung cho mọi mô hình. Cần xác định **kích thước cây/graph, phân bố nhánh, độ sâu, mục tiêu truy vấn và yêu cầu latency**.

### 25.4. Cân nhắc kết cấu lưu trữ khi đọc cây rất thường xuyên

| Mô hình | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Adjacency list (`parent_id`) | Dễ ghi, dễ đổi cha, dữ liệu gọn | Truy vấn tổ tiên/hậu duệ nhiều cấp cần recursion |
| Materialized path | Truy vấn theo path có thể thuận tiện | Đổi cha phải cập nhật path các nút con |
| Closure table (ancestor, descendant, depth) | Truy vấn tổ tiên/hậu duệ nhanh khi có index | Tốn số hàng và chi phí bảo trì quan hệ |
| Nested sets | Một số truy vấn subtree thuận tiện | Cập nhật cấu trúc có thể phức tạp |
| Graph-oriented storage/engine | Phù hợp cho đường đi/phân tích graph chuyên sâu | Tăng thành phần hệ thống và chi phí vận hành |

`WITH RECURSIVE` giải quyết tốt nhiều trường hợp trên mô hình adjacency list, nhưng không thay thế việc chọn cấu trúc vật lý phù hợp khi workload là truy vấn đồ thị quy mô lớn.

### 25.5. EXPLAIN ANALYZE chạy truy vấn thật

~~~sql
-- Chỉ sử dụng trên môi trường an toàn và truy vấn có điểm dừng:
EXPLAIN (ANALYZE, BUFFERS)
WITH RECURSIVE subtree AS (
    SELECT node_id, parent_id
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1
    UNION ALL
    SELECT child.node_id, child.parent_id
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT COUNT(*) FROM subtree;
~~~

`EXPLAIN (ANALYZE, BUFFERS)` **thực thi câu truy vấn** để đo số hàng thực tế, thời gian và I/O/buffer khi được hỗ trợ. Tránh chạy trên production nếu chưa đánh giá chi phí, đặc biệt với recursive graph có nhiều đường hoặc vòng lặp chưa được kiểm soát.

## 26. Một số giới hạn SQL và lưu ý thiết kế recursive term

### 26.1. CTE recursive phải duy trì đúng cấu trúc cột

Các nhánh anchor và recursive cần trả **cùng số cột** với kiểu tương thích. Ví dụ nếu anchor có:

~~~sql
SELECT 0::integer AS depth, ARRAY[1]::bigint[] AS path
~~~

thì recursive term phải trả kiểu tương ứng:

~~~sql
SELECT depth + 1, path || child.node_id
~~~

Với một cột path `bigint[]`, nối một giá trị text tùy tiện không đúng kiểu sẽ lỗi.

### 26.2. Không tùy ý dùng aggregate/window trong recursive term

PostgreSQL áp đặt những hạn chế cú pháp đối với recursive reference và recursive term. Không thể viết mọi cấu trúc như `GROUP BY`, aggregate hoặc window trực tiếp vào phần tự tham chiếu theo cách tùy ý.

Một mẫu thường an toàn hơn là:

1. Trong recursion, chỉ giữ thông tin cần đi theo cạnh.
2. Sau khi hoàn tất recursion, dùng truy vấn ngoài để `GROUP BY`, `COUNT`, `SUM` hoặc `ROW_NUMBER` theo yêu cầu.

Ví dụ:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT node_id, parent_id
    FROM cte_lab_164.org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT child.node_id, child.parent_id
    FROM cte_lab_164.org_nodes AS child
    JOIN subtree AS s
        ON child.parent_id = s.node_id
)
SELECT COUNT(*) AS subtree_size
FROM subtree;
~~~

### 26.3. CTE recursive không phải cache lâu dài

Kết quả recursive CTE được tính trong phạm vi **câu truy vấn hiện tại**. Nó không tự trở thành một bảng cache được cập nhật khi quan hệ cha–con đổi. Nếu cần dùng đi dùng lại cùng cấu trúc, phải thiết kế cache/materialized view/closure table cùng chiến lược đồng bộ phù hợp.

### 26.4. Kết quả thay đổi khi DDL/DML thay đổi

Khi cây được cập nhật, một truy vấn đọc ở snapshot khác có thể thấy quan hệ khác. Với thao tác nghiệp vụ “di chuyển cả subtree” cần transaction, locking và quy tắc chống cycle phù hợp, không chỉ dựa vào một lần duyệt rồi cập nhật rời rạc.

### 26.5. Bảo mật và phân quyền cây

Nếu hệ thống giới hạn mỗi người dùng chỉ thấy những phòng ban được phân quyền, truy vấn đệ quy phải xét **phạm vi được phép**. Việc một nút nằm trong subtree không đồng nghĩa user được phép đọc mọi bản ghi ở đó.

Đặc biệt, nên xác định:

- Có cho phép **đi xuyên qua nút không được xem** để tới hậu duệ được xem không?
- Có cho phép suy ra rằng một nút bị ẩn tồn tại qua depth/path không?
- Các quan hệ tenant có được cách ly không?
- Quy tắc RLS, view và role nào đang áp dụng?

Đây là **chính sách bảo mật**, không thể giải quyết đơn thuần bằng `WITH RECURSIVE`. Phải kiểm tra cả SQL và mô hình quyền.

## 27. Bài tập thực hành

Các bài tập dưới đây dùng schema `cte_lab_164` đã tạo trong bài. Một số yêu cầu truy vấn tự viết; gợi ý giúp người học xác định anchor và hướng join.

### Bài 1 — Duyệt cây từ gốc

Viết CTE đệ quy bắt đầu từ `node_id=1`, trả `node_id`, `parent_id`, `node_name`, `depth` và sắp `ORDER BY depth, node_id`.

**Đáp án kiểm tra:** **10 hàng**, độ sâu lớn nhất **3**.

### Bài 2 — Subtree của Kỹ thuật

Đổi anchor sang `node_id=2`. Đếm số nút gồm nút bắt đầu và số hậu duệ không gồm nút bắt đầu.

**Kỳ vọng:** gồm **6 nút**, **5 hậu duệ**.

### Bài 3 — Tổ tiên của Phân tích

Từ nút `8`, truy ngược `parent_id` lên gốc bằng recursive term. Hiển thị từ gốc xuống:

~~~text
Công ty → Kỹ thuật → Dữ liệu → Phân tích
~~~

**Gợi ý:** join `parent.node_id = current.parent_id`.

### Bài 4 — Breadcrumb

Tạo đường dẫn bằng mảng `text[]`, dùng `array_to_string(path, ' / ')`. Tại sao cần **prepend tên cha** khi đi từ lá lên, trong khi khi đi từ gốc xuống thì nên append tên con?

### Bài 5 — Rừng nhiều gốc

Anchor tất cả nút `parent_id IS NULL`; truyền `root_id` xuống. Tổng hợp số nút và độ sâu theo gốc.

**Đáp án:** `root_id=1` có 10 nút, max depth 3; `root_id=11` có 3 nút, max depth 1.

### Bài 6 — Nút lá

Tìm tất cả lá trong subtree của `Công ty` bằng `NOT EXISTS`. Nếu cần lá trong **tập hiển thị** chứ không phải trong bảng đầy đủ, hãy mô tả cách thay đổi điều kiện.

**Đáp án:** `6, 7, 8, 9, 10`.

### Bài 7 — Giới hạn độ sâu

Sửa CTE chỉ đi tối đa hai cấp dưới nút `1`. Giải thích khác biệt giữa đặt `WHERE s.depth < 2` trong recursive term và đặt `WHERE depth <= 2` ở SELECT ngoài.

### Bài 8 — Tìm reachable nodes

Trên `graph_edges`, dùng `WITH RECURSIVE reachable(node_id)` và `UNION` (không lưu depth/path) để liệt kê tất cả nút có thể đến từ `A`.

**Đáp án:** `A, B, C, D, E, F, G, H`.

### Bài 9 — Vì sao UNION có thể không dừng khi thêm depth?

Viết mô tả, **không chạy truy vấn không có cơ chế chống chu trình**, về các hàng `('B',1)` và `('B',4)` xuất hiện qua chu trình `B→D→E→B`. Tại sao chúng không bị `UNION` coi là trùng?

### Bài 10 — Path-local cycle detection

Viết CTE có `path_ids TEXT[]` và điều kiện:

~~~sql
WHERE NOT e.to_id = ANY(p.path_ids)
~~~

Liệt kê các simple paths từ `A` tới `H`. **Kỳ vọng:** có đường `A→B→H` và đường `A→C→F→G→H`.

### Bài 11 — Shortest hops và least weight

Tính số cạnh và tổng `weight` cho các đường đơn `A→H`. So sánh:

- Ít cạnh nhất: `A→B→H` với **2 cạnh**.
- Tổng weight nhỏ hơn: `A→C→F→G→H` với **weight 9**.

Giải thích vì sao ít cạnh nhất không đồng nghĩa chi phí nhỏ nhất.

### Bài 12 — SEARCH BREADTH FIRST

Trên PostgreSQL 14+, dùng `SEARCH BREADTH FIRST BY node_id SET bfs_order` với cây `Công ty`, rồi `ORDER BY bfs_order`. So sánh cách hiển thị với `ORDER BY depth, node_id`.

### Bài 13 — SEARCH DEPTH FIRST

Tương tự bài 12 nhưng dùng `SEARCH DEPTH FIRST`. Giải thích vì sao `SEARCH` giúp tạo thứ tự hiển thị mà **không biến engine thành một thuật toán DFS tùy biến**.

### Bài 14 — CYCLE

Trên PostgreSQL 14+, áp dụng:

~~~sql
CYCLE node_id SET is_cycle USING cycle_path
~~~

cho traversal từ `A`. Tìm một đường có chu trình và quan sát `is_cycle`. Khi lọc `WHERE NOT is_cycle`, đường tới cùng nút qua hai nhánh khác nhau có tự biến thành một hàng duy nhất không?

**Đáp án:** không; `CYCLE` kiểm soát vòng trên path, không khử trùng mọi đường đi đến cùng một nút.

### Bài 15 — Kiểm tra di chuyển subtree

Trước khi đặt `node 2` dưới `node 8`, chạy truy vấn tìm subtree của `node 2` và xem node 8 có nằm trong đó không.

**Đáp án:** có, nên thao tác tạo chu trình và phải bị từ chối bởi quy tắc bảo toàn cây. Vì sao chỉ dùng `FOREIGN KEY` chưa đủ ngăn thay đổi này?

### Bài 16 — Tổng ngân sách subtree

Từ `node_id=2`, đi xuống tất cả nút con rồi join `node_budget` để tính tổng.

**Đáp án:** **1.200.000** trên **6 nút**.

Nếu một nút thiếu dòng ngân sách, `JOIN` và `LEFT JOIN` khác nhau ra sao? Khi nào nên dùng `COUNT(b.node_id)` kèm `COUNT(*)` để báo độ đầy đủ?

### Bài 17 — Đếm hậu duệ cho mọi nút

Cho mỗi node làm anchor và giữ `ancestor_id`. Viết aggregate đếm số hậu duệ không gồm chính nút. Giải thích vì sao truy vấn này có thể tạo số hàng **O(N²)** trên cây dài dạng chuỗi.

### Bài 18 — Lọc nút inactive

Giả sử một nút trung gian bị `is_active=FALSE` nhưng con của nó vẫn active. So sánh:

1. Chỉ duyệt qua các nút active.
2. Duyệt qua mọi nút, rồi lọc nút active ở cuối.

Hai cách có cho cùng tập kết quả không? Mô hình nghiệp vụ nào cần mỗi cách?

### Bài 19 — Phân quyền subtree

Một người dùng chỉ được nhìn các nút thuộc `tenant_id=5`. Hãy mô tả cách bảo đảm traversal không rò rỉ nút của tenant khác. Có thể chỉ dựa vào đường đi hoặc `WHERE root_id=...` để cấp quyền không?

**Gợi ý:** cần kiểm soát tenant/role/RLS, quyền đọc object và chính sách về việc có cho phép đi qua nút ẩn.

### Bài 20 — Chọn mô hình lưu trữ

So sánh adjacency list, closure table và materialized path cho ba workload:

- Thường xuyên đổi cha, ít truy vấn toàn subtree.
- Hiển thị cây hàng nghìn lần mỗi phút, ít đổi cấu trúc.
- Đồ thị nhiều chu trình, nhiều đường đi, tìm tuyến chi phí nhỏ nhất.

Với mỗi workload, nêu giải pháp khởi đầu, rủi ro hiệu năng và cách kiểm chứng bằng dữ liệu thực tế.

## 28. Checklist tư duy khi viết một recursive CTE mới

1. **Đầu vào là cây hay đồ thị?** Có nhiều cha hoặc chu trình không?
2. **Anchor là gì?** Một nút, một gốc, tất cả gốc hay mọi nút?
3. **Đi theo cạnh nào?** Cha → con, con → cha hay from → to?
4. **Đơn vị kết quả là gì?** Nút duy nhất, mỗi đường đi, cặp tổ tiên–hậu duệ hay tập reachable?
5. **Những cột nào phải truyền giữa các vòng?** ID, depth, path, root, weight, metadata?
6. **Truy vấn dừng bằng cách nào?** Không còn cạnh, visited, `CYCLE` hay depth limit?
7. **`UNION` và `UNION ALL` có phù hợp mục tiêu?** Khử trùng cả hàng hay cần giữ mỗi path?
8. **BFS/DFS là thứ tự hiển thị hay là thuật toán cần trạng thái toàn cục?** Có `ORDER BY` rõ ràng chưa?
9. **Có nguy cơ bùng nổ số đường?** Cần cắt nhánh, giới hạn hoặc đổi thuật toán không?
10. **Có index cho hướng join không?** `parent_id`, `from_id`, `to_id`?
11. **Có cần tổng hợp đúng cấp?** Tránh đếm/cộng trùng nút khi graph có nhiều đường.
12. **Có quy tắc quyền và tính nhất quán dữ liệu?** Không để truy vấn duyệt lộ dữ liệu bị ẩn hoặc đọc cây sai do cập nhật không kiểm soát.

## 29. Tài liệu PostgreSQL chính thức

Những tài liệu sau mô tả cú pháp, ngữ nghĩa và cách triển khai recursive query:

- [PostgreSQL — WITH Queries: Recursive Queries](https://www.postgresql.org/docs/current/queries-with.html#QUERIES-WITH-RECURSIVE): anchor/recursive term, working table, `UNION`/`UNION ALL`, search order và cycle detection.
- [PostgreSQL — SELECT](https://www.postgresql.org/docs/current/sql-select.html): cú pháp `WITH RECURSIVE`, `SEARCH`, `CYCLE` và các mệnh đề ngoài cùng.
- [PostgreSQL — Arrays](https://www.postgresql.org/docs/current/arrays.html): tạo mảng, nối phần tử và sử dụng mảng để lưu đường đi.
- [PostgreSQL — Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html): `array_to_string` và các thao tác trên mảng.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): xem kế hoạch thực thi.
- [PostgreSQL — WITH / CTE Materialization](https://www.postgresql.org/docs/current/queries-with.html): hành vi tính toán và giới hạn tối ưu với CTE.

`/docs/current/` trỏ tới tài liệu của phiên bản ổn định hiện hành. Nếu server chạy PostgreSQL 13 hoặc một bản cụ thể khác, hãy xem tài liệu đúng **major version**, đặc biệt trước khi sử dụng `SEARCH` và `CYCLE`.

## 30. Tổng kết

**`WITH RECURSIVE` cho phép PostgreSQL truy vấn quan hệ nhiều cấp ngay trong SQL.** Một truy vấn gồm **anchor** tạo các nút bắt đầu, **recursive term** đi theo cạnh để tạo nút tiếp theo, và `UNION ALL`/`UNION` kết hợp kết quả qua các vòng cho đến khi không có hàng mới. Với cây hợp lệ, mẫu `JOIN child.parent_id = current.node_id` giúp tìm hậu duệ; đổi hướng join giúp tìm tổ tiên, đường đi và breadcrumb.

Với đồ thị, bài toán phức tạp hơn vì **một nút có thể được tới bằng nhiều đường và có thể có chu trình**. `UNION` khử trùng theo toàn bộ hàng phù hợp khi chỉ cần tập nút reachable; `UNION ALL` với **mảng path** giúp liệt kê các đường đơn nhưng phải kiểm tra nút đích chưa có trong đường. Từ PostgreSQL 14, `SEARCH` giúp tạo thứ tự hiển thị BFS/DFS, còn `CYCLE` giúp nhận biết và dừng mở rộng đường đi có vòng.

Một truy vấn đệ quy đúng phải trả lời rõ **đang tìm nút hay tìm đường, tính depth hay tính trọng số, có loại trùng hay không và điều kiện dừng là gì**. Cuối cùng, hãy quan sát hiệu năng, đặt index theo hướng traversal, kiểm soát quyền, và không quên rằng FK tự tham chiếu **không tự ngăn mọi chu trình**. Hiểu những nguyên tắc này sẽ giúp dùng PostgreSQL để giải quyết bài toán phân cấp và đồ thị một cách đáng tin cậy, thay vì chỉ thử cho đến khi query có kết quả.
