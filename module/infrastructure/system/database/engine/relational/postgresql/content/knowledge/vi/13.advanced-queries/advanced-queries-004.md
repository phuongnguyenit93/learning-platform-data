# Phát hiện chu trình và điều khiển thứ tự duyệt trong PostgreSQL

Một hệ thống có thể lưu cấu trúc phòng ban, cây danh mục, quan hệ phụ thuộc giữa tác vụ, danh sách thành phần sản phẩm hoặc mạng lưới liên kết giữa các đối tượng. Khi cần tìm tất cả cấp con hay những đối tượng có thể đi tới từ một điểm xuất phát, PostgreSQL hỗ trợ **truy vấn đệ quy** bằng `WITH RECURSIVE`. Tuy nhiên, dữ liệu thực tế không phải lúc nào cũng là một cây: một đối tượng có thể dẫn về chính nó, hoặc có nhiều đường đi đến cùng một đỉnh.

Ví dụ trong đồ thị quan hệ:

```text
1 ──► 2 ──► 4 ──► 5 ──► 6
│            ▲       │
└──► 3 ──────┘       └──► 2
     │
     └──► 7 ──► 8 ──► 8
```

- Đường `2 → 4 → 5 → 2` là một **chu trình**.
- Cạnh `8 → 8` là **self-loop** (chu trình dài một cạnh).
- Đỉnh `4` có thể đi tới từ cả `1 → 2 → 4` và `1 → 3 → 4`. **Có nhiều đường tới một đỉnh không nhất thiết là chu trình**.
- Nếu cứ mở rộng quan hệ theo `UNION ALL` mà không kiểm soát, truy vấn có thể tiếp tục sinh các đường `2 → 4 → 5 → 2 → 4 → ...` không dừng.
- Nếu chỉ nhận kết quả đúng nhưng không sắp xếp, một danh sách có thể xuất hiện theo thứ tự khó dự đoán. Với ứng dụng hiển thị cây, thường cần phân biệt **duyệt theo chiều rộng** (*breadth-first search – BFS*) và **duyệt theo chiều sâu** (*depth-first search – DFS*).

Bài học thuộc chương **Truy vấn nâng cao** của module *Database Engine Relational PostgreSQL*. Bạn sẽ học:

- Cấu trúc truy vấn `WITH RECURSIVE`, điều kiện dừng và ý nghĩa của `Recursive Union`.
- Cách lưu **đường đi hiện tại** vào mảng và phát hiện đỉnh lặp bằng `ANY`.
- Cú pháp chuẩn SQL **`CYCLE ... SET ... USING ...`** từ PostgreSQL 14.
- Cú pháp **`SEARCH BREADTH FIRST`** và **`SEARCH DEPTH FIRST`** để tạo khóa sắp xếp.
- Vì sao `SEARCH` không buộc engine thực thi theo thứ tự BFS/DFS và vì sao kết quả cần `ORDER BY`.
- Khác biệt giữa **chu trình trên đường hiện tại**, **đỉnh được đi tới qua nhiều đường**, và **loại trùng toàn cục** bằng `UNION`.
- Giới hạn độ sâu, tránh bùng nổ số đường đi, chọn chỉ mục, kiểm tra bằng `EXPLAIN`, và thiết kế truy vấn trên dữ liệu phân cấp có nhiều tenant.

> **Yêu cầu phiên bản:** `WITH RECURSIVE` có từ những phiên bản PostgreSQL cũ, còn cú pháp `SEARCH` và `CYCLE` được PostgreSQL hỗ trợ từ **PostgreSQL 14**. Với PostgreSQL 13 hoặc cũ hơn, dùng kỹ thuật giữ đường đi bằng mảng như các ví dụ thủ công trong bài. Kiểm tra server trước bằng `SHOW server_version;`.

## 1. Cây, đồ thị, đường đi và chu trình

### 1.1. Các khái niệm nền tảng

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Đỉnh** (*vertex/node*) | Một thực thể được liên kết | Nhân viên, danh mục, công việc |
| **Cạnh** (*edge*) | Quan hệ từ một đỉnh sang đỉnh khác | Công việc A phụ thuộc B |
| **Đồ thị có hướng** | Mỗi cạnh có đầu và cuối | `A → B` không tự động có `B → A` |
| **Đường đi** (*path*) | Dãy đỉnh liên tiếp theo cạnh | `1 → 2 → 4 → 5` |
| **Độ sâu** (*depth*) | Số cạnh đã đi từ điểm xuất phát | Gốc 1 ở độ sâu 0; 4 qua 2 ở độ sâu 2 |
| **Chu trình** (*cycle*) | Đường đi trở lại một đỉnh đã gặp trên chính đường đi đó | `2 → 4 → 5 → 2` |
| **Self-loop** | Cạnh từ một đỉnh đến chính nó | `8 → 8` |
| **Cây** (*tree*) | Cấu trúc phân cấp không có chu trình, mỗi đỉnh khác gốc có đúng một cha trong cây | Cây thư mục lý tưởng |
| **DAG** | Đồ thị có hướng không chu trình | Nhiều tác vụ phụ thuộc chung một tác vụ |

Đồ thị có thể có nhiều đường đi đến một đỉnh mà vẫn **không có chu trình**. Ví dụ, `1 → 2 → 4` và `1 → 3 → 4` cùng đi tới 4 nhưng không làm đường đi quay lại đỉnh đã xuất hiện trước đó.

### 1.2. Hai cách hiểu “đã thăm” khác nhau

Khi duyệt đồ thị, phải biết yêu cầu là:

1. **Liệt kê tất cả các đường đi hợp lệ từ gốc**: một đỉnh có thể xuất hiện nhiều lần nếu đến qua những đường khác nhau; chỉ cấm lặp **trên cùng một đường đi** để tránh chu trình.
2. **Liệt kê mỗi đỉnh có thể đi tới đúng một lần**: có thể dùng cơ chế loại trùng toàn cục, chẳng hạn `UNION` khi trạng thái đệ quy chỉ chứa định danh đỉnh, và không cần giữ mọi đường đi.
3. **Phát hiện chính xác cạnh nào khép chu trình**: cần giữ đường đi hoặc sử dụng `CYCLE` để đánh dấu hàng gây lặp.

Đừng dùng một truy vấn “chống lặp” cho cả ba mục tiêu khi chúng có ý nghĩa khác nhau.

### 1.3. BFS và DFS là hai kiểu thứ tự

**BFS – duyệt theo chiều rộng:** thăm các đỉnh ở độ sâu 0, rồi đến độ sâu 1, 2, 3...

```text
Gốc 1
  ├─ 2
  │  └─ 4
  │     └─ 5
  └─ 3
     └─ 7
        └─ 8

BFS theo từng tầng: 1 | 2,3 | 4,7 | 5,8 | 6
```

**DFS – duyệt theo chiều sâu:** theo một nhánh xuống sâu rồi mới chuyển sang nhánh khác. Một thứ tự DFS với các nhánh chọn theo ID tăng dần có thể là:

```text
1 → 2 → 4 → 5 → 6
    (quay lại nhánh khác)
1 → 3 → 4 → 5 → 6
1 → 3 → 7 → 8
```

Trong **đồ thị có nhiều đường**, cùng một đỉnh như 4 hoặc 5 có thể xuất hiện trong nhiều bản ghi *đường đi*. Hai danh sách trên chỉ minh họa ý tưởng duyệt, **không** phải dự đoán đầy đủ mọi hàng của một truy vấn trên đồ thị mẫu khi giữ tất cả đường.

**Điểm quan trọng:** “thứ tự duyệt” khi trình bày dữ liệu ở SQL thường có nghĩa **sắp xếp các hàng kết quả theo khóa BFS/DFS**. Nó không có nghĩa có thể dùng `ORDER BY` để ép PostgreSQL chạy các vòng đệ quy theo thứ tự vật lý của một thuật toán imperative.

## 2. Tạo dữ liệu đồ thị trong PostgreSQL

Các ví dụ sử dụng schema riêng và hai bảng: một bảng đỉnh, một bảng cạnh có hướng.

### 2.1. Tạo schema và bảng

```sql
SHOW server_version;

CREATE SCHEMA IF NOT EXISTS graph_lab;

CREATE TABLE graph_lab.nodes (
    node_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE graph_lab.edges (
    from_id INTEGER NOT NULL
        REFERENCES graph_lab.nodes(node_id),
    to_id INTEGER NOT NULL
        REFERENCES graph_lab.nodes(node_id),
    PRIMARY KEY (from_id, to_id)
);
```

Ràng buộc `PRIMARY KEY (from_id, to_id)` ngăn lưu **cùng một cạnh có hướng hai lần**, nhưng **không ngăn chu trình**. Các cạnh `2 → 4`, `4 → 5`, `5 → 2` có những cặp khóa khác nhau nên vẫn hợp lệ.

Chúng ta cũng cố ý **không cấm self-loop** bằng `CHECK (from_id <> to_id)`, để có thể quan sát `8 → 8`.

### 2.2. Chèn đỉnh và cạnh

```sql
INSERT INTO graph_lab.nodes (node_id, label)
VALUES
    (1, 'Root'),
    (2, 'Catalog A'),
    (3, 'Catalog B'),
    (4, 'Shared component'),
    (5, 'Dependency'),
    (6, 'Leaf'),
    (7, 'Branch C'),
    (8, 'Self-loop');

INSERT INTO graph_lab.edges (from_id, to_id)
VALUES
    (1, 2),
    (1, 3),
    (2, 4),
    (3, 4),
    (3, 7),
    (4, 5),
    (5, 2), -- Chu trình 2 -> 4 -> 5 -> 2
    (5, 6),
    (7, 8),
    (8, 8); -- Chu trình tự trỏ
```

Hình dung:

```text
          +-----------------------+
          |                       |
          v                       |
1 --> 2 --> 4 --> 5 --> 6        |
|           ^     |               |
v           |     +---------------+
3 ----------+
|
+--> 7 --> 8 --+
            ^   |
            +---+
```

Các hàng minh họa:

| from_id | to_id | Ý nghĩa |
|---:|---:|---|
| 1 | 2 | Nhánh A từ gốc |
| 1 | 3 | Nhánh B từ gốc |
| 2 | 4 | Đi tới thành phần chung |
| 3 | 4 | Một đường khác cũng tới 4 |
| 4 | 5 | Tiếp tục phụ thuộc |
| 5 | 2 | Khép chu trình qua 2 |
| 7 | 8 | Đi tới 8 |
| 8 | 8 | Self-loop |

### 2.3. Chọn gốc và hướng quan hệ

Trong ví dụ, cạnh `from_id → to_id` diễn đạt **đi từ nguồn sang đích**. Truy vấn tìm đỉnh **có thể đi tới từ node 1** sẽ JOIN theo:

```sql
ON e.from_id = w.node_id
```

Nếu cần đi **ngược** từ một đỉnh để tìm các đỉnh dẫn tới nó, phải dùng:

```sql
ON e.to_id = w.node_id
```

Đây là một quyết định về ý nghĩa đồ thị. Viết sai chiều có thể trả không có hàng hoặc trả tập phụ thuộc ngược với yêu cầu nghiệp vụ.

## 3. WITH RECURSIVE hoạt động như thế nào?

Một CTE đệ quy (*recursive common table expression*) có hai phần chính:

1. **Anchor/non-recursive term:** tạo những hàng xuất phát.
2. **Recursive term:** tham chiếu CTE đang định nghĩa để sinh lớp kết quả tiếp theo.

Hai phần được ghép bằng `UNION` hoặc `UNION ALL`.

### 3.1. Ví dụ đếm số đơn giản

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM numbers
    WHERE n < 5
)
SELECT n
FROM numbers
ORDER BY n;
```

Kết quả: `1, 2, 3, 4, 5`.

Diễn giải:

| Vòng mở rộng | Hàng vừa có | Hàng mới sinh |
|---|---|---|
| Anchor | 1 | 2 |
| Vòng sau | 2 | 3 |
| Vòng sau | 3 | 4 |
| Vòng sau | 4 | 5 |
| Vòng sau | 5 | Không có vì `n < 5` sai |

Truy vấn kết thúc khi recursive term **không sinh được hàng mới**. Điều kiện `WHERE n < 5` kiểm soát độ dài ở ví dụ này.

### 3.2. Cơ chế làm việc theo tầng của PostgreSQL

Một cách hình dung phù hợp với tài liệu PostgreSQL:

```text
Anchor -> working table
             |
             v
       Recursive term
             |
             v
    intermediate table
             |
             +--> đưa hàng mới ra kết quả
             |
             +--> trở thành working table vòng tiếp
                       |
                       v
                 lặp đến khi rỗng
```

PostgreSQL đánh giá recursive CTE theo cách **lặp qua các lớp hàng trung gian**. Vì vậy, khi không sắp xếp, kết quả thường có vẻ giống duyệt theo chiều rộng. Nhưng **không nên dựa vào thứ tự quan sát ấy**: thứ tự giữa các hàng trong một lớp không được bảo đảm, và việc xử lý/optimizer có thể ảnh hưởng cách dữ liệu được trả.

Muốn thứ tự kết quả có thể kiểm chứng, cần tạo **khóa thứ tự** và dùng `ORDER BY` ở SELECT cuối.

### 3.3. Mẫu khung truy vấn đồ thị

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER AS node_id, 0 AS depth

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
    WHERE w.depth < 5
)
SELECT node_id, depth
FROM walk
ORDER BY depth, node_id;
```

Đây là một ví dụ **có giới hạn độ sâu**, nên sẽ dừng dù đồ thị có chu trình. Tuy nhiên, nó **không loại chu trình**, và mỗi đường đi vẫn có thể sinh hàng mới cho cùng `node_id`. Giới hạn độ sâu chỉ cắt bỏ kết quả sâu hơn, có thể bỏ sót những đường cần thiết.

**Không bỏ điều kiện `w.depth < 5` trong truy vấn này trên đồ thị có chu trình**, nếu vẫn dùng `UNION ALL` và không có biện pháp phát hiện lặp. `depth` liên tục tăng nên cùng đỉnh có thể xuất hiện mãi ở các độ sâu khác nhau.

## 4. Vì sao UNION ALL có thể chạy mãi?

Giả sử recursive CTE giữ cả `node_id` lẫn `depth`:

```sql
-- KHÔNG CHẠY trên graph_lab vì có chu trình và không có điều kiện dừng:
-- WITH RECURSIVE walk(node_id, depth) AS (
--     SELECT 1, 0
--     UNION ALL
--     SELECT e.to_id, w.depth + 1
--     FROM walk AS w
--     JOIN graph_lab.edges AS e
--       ON e.from_id = w.node_id
-- )
-- SELECT * FROM walk;
```

Đường `1 → 2 → 4 → 5 → 2 → 4 ...` liên tục tạo ra:

```text
(2,1), (4,2), (5,3), (2,4), (4,5), (5,6), ...
```

Vì `depth` thay đổi, **mỗi hàng là một cặp mới**, dù `node_id` đã gặp lại. Khi dùng `UNION ALL`, PostgreSQL không loại trùng.

### 4.1. Đổi sang UNION có tự sửa không?

Nếu giữ **cả depth**:

```sql
-- Vẫn không phải giải pháp an toàn nếu bỏ giới hạn dừng:
-- WITH RECURSIVE walk(node_id, depth) AS (
--   SELECT 1, 0
--   UNION
--   SELECT e.to_id, w.depth + 1
--   FROM walk w JOIN graph_lab.edges e ON e.from_id=w.node_id
-- )
-- SELECT * FROM walk;
```

`UNION` loại các **hàng trùng trên toàn bộ danh sách cột**, nhưng `(2,1)` và `(2,4)` không trùng vì khác depth. Do đó, **chuyển `UNION ALL` thành `UNION` không tự giải quyết mọi truy vấn đệ quy có chu trình**.

### 4.2. Khi chỉ cần mỗi đỉnh một lần, UNION có thể đủ

Nếu câu hỏi chỉ là “từ 1 có thể tới các đỉnh nào”, không cần độ sâu hoặc mọi đường đi:

```sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1::INTEGER

    UNION

    SELECT e.to_id
    FROM reachable AS r
    JOIN graph_lab.edges AS e
        ON e.from_id = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
```

Kết quả: các đỉnh `1, 2, 3, 4, 5, 6, 7, 8`, mỗi đỉnh **một lần**.

Ở đây mỗi hàng chỉ có **`node_id`** nên `UNION` loại một đỉnh đã xuất hiện trong các bước trước. Trên đồ thị hữu hạn, việc mở rộng sẽ dừng khi không còn đỉnh mới.

**Đổi lại:** truy vấn không giữ được **tất cả đường đi** tới một đỉnh, không biết đâu là cạnh khép chu trình, và không thể đơn giản thêm `depth`/`path` rồi trông chờ quy tắc loại trùng cũ giữ nguyên.

| Mục tiêu | Chiến lược thích hợp |
|---|---|
| Tập các đỉnh có thể tới, không cần đường | `UNION` chỉ trên ID hoặc trạng thái có thể loại trùng |
| Tất cả đường đi không lặp đỉnh | `UNION ALL` + path-local cycle check |
| Đánh dấu đường khép chu trình | `CYCLE` hoặc tự tính `is_cycle` |
| Trình bày theo BFS/DFS | `SEARCH` hoặc khóa `depth/path`, rồi `ORDER BY` |

## 5. Phát hiện chu trình thủ công bằng mảng path

Một giải pháp rõ ràng là mang theo **đường đi hiện tại** trong mỗi hàng của recursive CTE.

### 5.1. Giữ mảng các đỉnh đã đi qua

Với ID kiểu `INTEGER`:

```sql
WITH RECURSIVE walk(node_id, depth, path) AS (
    SELECT
        1::INTEGER AS node_id,
        0::INTEGER AS depth,
        ARRAY[1]::INTEGER[] AS path

    UNION ALL

    SELECT
        e.to_id AS node_id,
        w.depth + 1 AS depth,
        w.path || e.to_id AS path
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT
    node_id,
    depth,
    path
FROM walk
ORDER BY path;
```

Các thành phần:

- `ARRAY[1]::INTEGER[]`: đường ban đầu chỉ có gốc 1.
- `w.path || e.to_id`: thêm đỉnh tiếp theo vào **cuối mảng đường đi**.
- `e.to_id = ANY(w.path)`: kiểm tra đỉnh tiếp theo **đã tồn tại trên đường đi hiện tại chưa**.
- `NOT (...)`: chỉ mở rộng nếu đỉnh mới **chưa xuất hiện** trên đường hiện tại.
- `ORDER BY path`: sắp các đường theo thứ tự từ điển của mảng (với ID nguyên trong lab), tạo cách hiển thị giống DFS theo nhánh.

Ví dụ những đường hợp lệ:

```text
{1}
{1,2}
{1,2,4}
{1,2,4,5}
{1,2,4,5,6}
{1,3}
{1,3,4}
{1,3,4,5}
{1,3,4,5,2}
{1,3,4,5,6}
{1,3,7}
{1,3,7,8}
```

Các dòng là **ví dụ đường đi**, không phải sự đảm bảo `SELECT` sẽ xuất theo đúng thứ tự này nếu bỏ `ORDER BY`. Đường `1 → 3 → 4 → 5 → 2` được phép vì đỉnh 2 **chưa có trong chính đường đi đó**, dù 2 đã xuất hiện ở một nhánh khác.

Từ `1 → 2 → 4 → 5`, cạnh tiếp theo `5 → 2` bị chặn vì 2 đã có trong path. Từ `1 → 3 → 7 → 8`, cạnh `8 → 8` bị chặn vì 8 đã có.

### 5.2. Đếm đường đi khác đếm đỉnh

Do đỉnh `4` xuất hiện trong cả `{1,2,4}` và `{1,3,4}`:

```sql
WITH RECURSIVE walk(node_id, path) AS (
    SELECT 1::INTEGER, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_id, w.path || e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT
    COUNT(*) AS total_path_rows,
    COUNT(DISTINCT node_id) AS unique_reachable_nodes
FROM walk;
```

`COUNT(*)` đếm các hàng đại diện cho **cặp đỉnh cuối/đường đi**; `COUNT(DISTINCT node_id)` đếm những đỉnh cuối **khác nhau**.

Đừng coi `COUNT(*)` ở một truy vấn giữ path là “số nhân viên/danh mục duy nhất”, vì một thực thể có thể được tiếp cận từ nhiều nhánh khác nhau.

### 5.3. Vì sao kiểm tra trên path, không kiểm tra đã thấy toàn cục?

Đường `1 → 2 → 4` và `1 → 3 → 4` không phải một chu trình. Nếu mục tiêu là **liệt kê phụ thuộc theo từng nhánh**, cần giữ cả hai đường. Một tập “visited global” có thể bỏ đường thứ hai, làm mất thông tin về nhiều cha/đường dẫn.

Cycle detection theo path trả lời: **“đỉnh tiếp theo có lặp lại trong chính chuỗi đỉnh đang duyệt không?”**. Đây là quy tắc khác với **“đỉnh đó có xuất hiện trong bất kỳ nhánh nào trước đây không?”**.

### 5.4. Điều kiện NOT (... = ANY(...)) và NULL

Ví dụ dùng `node_id NOT NULL` nhờ primary key. Nếu khóa đỉnh có thể `NULL` hoặc biểu thức key tổng hợp có thành phần NULL, phép `= ANY(array)` có thể cho kết quả unknown và `NOT` không hoạt động như mong đợi.

Đối với đồ thị thật, nên chọn **định danh đỉnh không NULL, ổn định**, hoặc có chiến lược so sánh NULL-safe rõ ràng. Không sao chép mẫu mảng integer vào một khóa nullable phức tạp mà không kiểm tra lại.

## 6. Muốn thấy cạnh khép chu trình: tự sinh is_cycle

Ở mục trước, cạnh khép vòng bị lọc **trước khi tạo hàng mới**, nên kết quả chỉ có các đường không lặp đỉnh. Nếu cần **báo cáo chu trình đã phát hiện**, hãy sinh cả hàng đóng vòng, gắn `is_cycle = true`, rồi **không mở rộng những hàng đã đánh dấu**.

```sql
WITH RECURSIVE walk(node_id, depth, path, is_cycle) AS (
    SELECT
        1::INTEGER,
        0::INTEGER,
        ARRAY[1]::INTEGER[],
        FALSE

    UNION ALL

    SELECT
        e.to_id,
        w.depth + 1,
        w.path || e.to_id,
        e.to_id = ANY(w.path) AS is_cycle
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
    WHERE NOT w.is_cycle
)
SELECT node_id, depth, path, is_cycle
FROM walk
ORDER BY path;
```

Ý nghĩa:

1. Ở mỗi bước, kiểm tra **đỉnh sắp thêm** có nằm trong `w.path` không.
2. Nếu đã có, hàng mới vẫn được tạo với `is_cycle=true`, và `path` chứa **đỉnh xuất hiện lần thứ hai**.
3. Vòng đệ quy tiếp theo chỉ mở rộng `WHERE NOT w.is_cycle`, nên hàng đóng chu trình **không bị dùng để phát triển đường mới**.

Những hàng có thể quan sát:

```text
path = {1,2,4,5,2}     is_cycle = true
path = {1,3,4,5,2,4}   is_cycle = true
path = {1,3,7,8,8}     is_cycle = true
```

Ở đường `{1,3,4,5,2,4}`, cạnh `2 → 4` đóng chu trình **4 → 5 → 2 → 4**; đỉnh 2 chưa có ở phần trước của đường này nên được thêm hợp lệ trước đó.

### 6.1. Liệt kê chỉ các chu trình

```sql
WITH RECURSIVE walk(node_id, path, is_cycle) AS (
    SELECT 1::INTEGER, ARRAY[1]::INTEGER[], FALSE
    UNION ALL
    SELECT
        e.to_id,
        w.path || e.to_id,
        e.to_id = ANY(w.path)
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
    WHERE NOT w.is_cycle
)
SELECT node_id, path
FROM walk
WHERE is_cycle
ORDER BY path;
```

Lệnh trả các **đường đi từ gốc đã chạm chu trình**. Nếu chỉ cần **phần vòng** không bao gồm tiền tố từ gốc, có thể xử lý path để cắt từ vị trí xuất hiện đầu của đỉnh bị lặp. Với đồ thị lớn và nhiều đường, một chu trình có thể xuất hiện qua nhiều đường đi khác nhau; cần chuẩn hóa/loại trùng chu trình ở bước báo cáo nếu muốn đếm **chu trình phân biệt**.

### 6.2. Giới hạn độ sâu như lớp bảo vệ bổ sung

Có thể thêm:

```sql
WHERE NOT w.is_cycle
  AND w.depth < 30
```

Giới hạn này là một **điều kiện sản phẩm/tài nguyên**: những đường sâu hơn 30 cạnh sẽ không được mở rộng. Nó không thay thế phát hiện chu trình, và **có thể bỏ sót** đỉnh/chu trình chỉ xuất hiện ở độ sâu lớn hơn.

Với đồ thị hữu hạn, chặn lặp đỉnh trên mỗi path giúp các đường sinh ra có độ dài hữu hạn. Tuy nhiên, **số đường đơn giản vẫn có thể rất lớn**, đặc biệt trong DAG có nhiều nhánh hội tụ. Cần cả giới hạn khối lượng dữ liệu, thời gian truy vấn và thiết kế mục tiêu phù hợp.

## 7. CYCLE trong PostgreSQL 14+: phát hiện chu trình tự động

PostgreSQL 14 trở lên có cú pháp `CYCLE` đi kèm recursive CTE, giúp khỏi phải tự viết mảng path và điều kiện so sánh ở mỗi bước.

### 7.1. Cú pháp cơ bản

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    depth,
    is_cycle,
    cycle_path
FROM walk
ORDER BY cycle_path;
```

Cú pháp trọng tâm:

```sql
CYCLE node_id SET is_cycle USING cycle_path
```

PostgreSQL tự duy trì thông tin tương đương:

- **`cycle_path`:** đường đi của các giá trị khóa được khai báo sau `CYCLE`.
- **`is_cycle`:** đánh dấu một hàng nếu giá trị khóa xuất hiện lại trên đường đi đang mở rộng.
- Cơ chế tránh tiếp tục mở rộng từ các hàng đã đóng chu trình.

Với một khóa đơn `INTEGER`, path là một mảng tương ứng các giá trị khóa. Khi theo dõi nhiều cột, path có thể chứa những giá trị ghép.

### 7.2. Điều gì xuất hiện trong kết quả?

Truy vấn vẫn **có thể trả hàng khép chu trình** với `is_cycle=true`, ví dụ một đường kết thúc bằng ID 2 lặp lại. Điểm quan trọng là **không tiếp tục tạo vô hạn các bước sau hàng đó**.

Nếu chỉ muốn các đường không có chu trình trong kết quả cuối:

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::INTEGER
    UNION ALL
    SELECT e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT node_id, cycle_path
FROM walk
WHERE NOT is_cycle
ORDER BY cycle_path;
```

Nếu cần điều tra cạnh bị lỗi, **đừng lọc mất `is_cycle=true`**; hãy trả lại path hoặc thêm cột liên quan để vận hành biết đường đã đóng vòng.

### 7.3. CYCLE chọn khóa nào?

`CYCLE node_id` kiểm tra **node_id có lặp trên chính path**. Với hệ thống multi-tenant, một ID có thể chỉ duy nhất **trong phạm vi tenant**, ví dụ hai tenant đều có đối tượng ID 17.

Khi ấy:

```sql
-- Minh họa khái niệm với các cột tenant_id, node_id
-- thực sự hiện diện trong recursive CTE:
-- CYCLE tenant_id, node_id SET is_cycle USING cycle_path
```

Kiểm tra cặp `(tenant_id, node_id)` sẽ khác kiểm tra riêng `node_id`. Nhưng muốn an toàn multi-tenant còn phải **JOIN cạnh theo tenant_id** và **lọc đúng phạm vi quyền**; chỉ thay khóa trong `CYCLE` không tự tạo tenant isolation.

### 7.4. CYCLE có tự tìm tất cả chu trình trên đồ thị không?

Không. Nó phát hiện những chu trình **mà truy vấn thực sự đi tới từ anchor**. Nếu một thành phần đồ thị không nối được từ gốc 1, chu trình bên trong thành phần đó **không xuất hiện** trong kết quả duyệt từ 1.

Muốn kiểm tra toàn bộ đồ thị, cần chiến lược khởi đầu từ nhiều node hoặc thuật toán chuyên biệt. Việc lấy **mọi node làm anchor** có thể phát triển rất nhiều đường và phát hiện cùng một chu trình nhiều lần, nên phải đánh giá độ phức tạp trước khi dùng trong production.

### 7.5. Phân biệt CYCLE và ràng buộc dữ liệu

`CYCLE` là cơ chế **trong truy vấn đọc/duyệt**, không phải ràng buộc ngăn người dùng thêm cạnh gây vòng.

Ví dụ:

```sql
INSERT INTO graph_lab.edges (from_id, to_id)
VALUES (6, 1);
```

Lệnh này có thể được chấp nhận nếu không vi phạm PK/FK, dù nó tạo thêm chu trình trong đồ thị. Một truy vấn `CYCLE` sau đó có thể **phát hiện** đường gây vòng, nhưng không hoàn tác thao tác INSERT.

Nếu nghiệp vụ yêu cầu **không bao giờ được tạo chu trình**, cần thiết kế validation tại thời điểm ghi với cơ chế khóa/đồng thời phù hợp hoặc mô hình dữ liệu bảo vệ bất biến. Không thay việc bảo vệ dữ liệu bằng một truy vấn báo cáo chạy định kỳ.

Để các ví dụ còn lại dùng bộ dữ liệu ban đầu, **không thực thi INSERT (6,1)** trừ khi chủ động thử và khôi phục dữ liệu lab.

## 8. SEARCH BREADTH FIRST: tạo khóa thứ tự theo chiều rộng

PostgreSQL 14+ hỗ trợ `SEARCH` trong recursive CTE. Ví dụ vừa đánh dấu chu trình vừa tạo thứ tự BFS:

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    depth,
    bfs_order,
    is_cycle,
    cycle_path
FROM walk
ORDER BY bfs_order, cycle_path;
```

Đọc phần:

```sql
SEARCH BREADTH FIRST BY node_id SET bfs_order
```

- `SEARCH` yêu cầu tạo thêm **cột thứ tự tính toán** cho truy vấn đệ quy.
- `BREADTH FIRST` diễn đạt sắp xếp theo **tầng/độ sâu**, sau đó theo những khóa ghi sau `BY`.
- `BY node_id` quy định khóa dùng để phân biệt thứ tự trong từng tầng, theo ngữ nghĩa hỗ trợ của PostgreSQL.
- `SET bfs_order` tạo cột `bfs_order` để **SELECT bên ngoài dùng `ORDER BY`**.

**Không nên giả định `bfs_order` là một số thứ tự nguyên tăng 1, 2, 3...**. Đây là kiểu dữ liệu thứ tự do PostgreSQL sinh ra, phục vụ việc so sánh và sắp xếp. Khi gửi kết quả ra API, có thể dùng `depth` và các khóa nghiệp vụ thay vì dựa vào dạng chữ nội bộ của cột này.

### 8.1. Vì sao ORDER BY bfs_order chưa chắc là toàn bộ thứ tự duy nhất?

Trong đồ thị mẫu, node 4 có thể xuất hiện qua hai đường ở **cùng độ sâu**:

```text
1 → 2 → 4
1 → 3 → 4
```

Nếu khóa tìm kiếm BFS chỉ gồm `node_id`, hai hàng cùng độ sâu và cùng `node_id` có thể có **khóa bfs_order tương đương**. Vì bài lab có thêm `CYCLE` với `cycle_path`, ví dụ sắp:

```sql
ORDER BY bfs_order, cycle_path
```

để phân định hai đường đi cùng đỉnh. Không nên dựa vào thứ tự tie tình cờ trong kết quả khi yêu cầu pagination/export ổn định.

### 8.2. Có thể tự sắp BFS nếu không dùng SEARCH

Với PostgreSQL 13 hoặc khi muốn kiểm soát trực tiếp:

```sql
WITH RECURSIVE walk(node_id, depth, path) AS (
    SELECT 1::INTEGER, 0::INTEGER, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_id, w.depth + 1, w.path || e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT node_id, depth, path
FROM walk
ORDER BY depth ASC, path ASC;
```

Ở đây `depth` tạo các tầng BFS; `path` làm khóa ổn định trong cùng tầng và phân biệt nhiều đường đến một node. Đây là **thứ tự trình bày BFS-like**, không phải lệnh bắt executor phải chạy từng node bằng queue giống code thủ tục.

### 8.3. BFS có tự tìm đường ngắn nhất không?

Nếu mọi cạnh đều có trọng số như nhau và bài toán là **số bước ít nhất** từ một gốc, BFS là hướng tiếp cận có liên quan. Nhưng truy vấn `SEARCH BREADTH FIRST` **chỉ tạo cột thứ tự**, không tự trả mỗi node đúng một lần hay tự giải quyết mọi bài toán shortest path.

Trên đồ thị có nhiều đường đến cùng đỉnh, cần thêm quy tắc chọn **độ sâu nhỏ nhất** theo node, ví dụ sau khi duyệt an toàn:

```sql
WITH RECURSIVE walk(node_id, depth, path) AS (
    SELECT 1::INTEGER, 0::INTEGER, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_id, w.depth + 1, w.path || e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT
    node_id,
    MIN(depth) AS min_hops
FROM walk
GROUP BY node_id
ORDER BY min_hops, node_id;
```

Kết quả là **số cạnh nhỏ nhất** trong những đường không lặp node từ gốc 1 tới từng node. Tuy nhiên, việc liệt kê mọi đường đơn giản có thể bùng nổ theo kích thước đồ thị; không coi truy vấn này là thuật toán shortest path tối ưu cho mạng rất lớn. Với trọng số cạnh không đều, `MIN(depth)` **không** phải tổng chi phí đường đi nhỏ nhất.

## 9. SEARCH DEPTH FIRST: tạo khóa thứ tự theo chiều sâu

Để sắp theo cách duyệt DFS:

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    depth,
    dfs_order,
    is_cycle,
    cycle_path
FROM walk
ORDER BY dfs_order;
```

`SEARCH DEPTH FIRST BY node_id SET dfs_order` sinh **khóa thứ tự có cấu trúc đường đi**. Khi `ORDER BY dfs_order`, các hàng được trình bày theo thứ tự ưu tiên đi sâu từng nhánh, theo thứ tự khóa được khai báo.

### 9.1. CYCLE path cũng có thể dùng làm khóa DFS

Khi chỉ cần **DFS và phát hiện chu trình theo cùng khóa node_id**, việc khai báo đồng thời:

```sql
SEARCH DEPTH FIRST BY node_id SET dfs_order
CYCLE node_id SET is_cycle USING cycle_path
```

có thể tạo ra hai dạng thông tin đường đi gần như tương ứng, gây chi phí dư. Trong nhiều trường hợp, chỉ dùng:

```sql
CYCLE node_id SET is_cycle USING cycle_path
```

rồi:

```sql
ORDER BY cycle_path
```

là đủ để có **thứ tự trình bày kiểu DFS** cùng với cơ chế chống chu trình.

Ngược lại, kết hợp **`SEARCH BREADTH FIRST` + `CYCLE`** có ý nghĩa rõ hơn vì một bên tạo khóa **độ sâu/tầng**, bên kia quản lý **đường đi và lặp đỉnh**.

### 9.2. Tự sắp DFS bằng mảng path

Nếu cần tương thích PostgreSQL 13 trở xuống:

```sql
WITH RECURSIVE walk(node_id, path) AS (
    SELECT 1::INTEGER, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_id, w.path || e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT
    node_id,
    array_length(path, 1) - 1 AS depth,
    path
FROM walk
ORDER BY path;
```

Mảng path chứa ID các đỉnh theo thứ tự đi qua. `ORDER BY path` so sánh từ phần tử đầu tiên, phù hợp để liệt kê các nhánh theo thứ tự ID.

**Lưu ý:** Sắp theo đường đi ID không nhất thiết giống duyệt theo tên hiển thị `label`. Nếu nghiệp vụ muốn sắp các con theo `label`, cần định nghĩa khóa sort phù hợp hoặc dùng `SEARCH ... BY label` với dữ liệu và điều kiện JOIN đã được thiết kế để có nhãn ở mỗi bước.

## 10. SEARCH không có nghĩa thay đổi thứ tự thực thi đệ quy

Đây là điểm dễ bị hiểu nhầm nhất của bài học.

### 10.1. Phân biệt ba thứ tự

| Thứ tự | Quyết định bởi | Có phải API cam kết? |
|---|---|---|
| **Thứ tự executor đánh giá các vòng đệ quy** | Cơ chế đánh giá recursive CTE và kế hoạch PostgreSQL | Không nên dựa vào để trình bày |
| **Khóa thứ tự được tính** | `SEARCH BREADTH FIRST/DEPTH FIRST BY ... SET ...` hoặc `depth/path` tự xây | Có thể dùng để sắp kết quả |
| **Thứ tự hàng trả cho client** | `ORDER BY` ở câu SELECT cuối phù hợp | Đây mới là nơi khai báo thứ tự đầu ra |

Vì vậy, viết:

```sql
WITH RECURSIVE ...
SEARCH DEPTH FIRST BY node_id SET dfs_order
SELECT * FROM walk;
```

**không phải bảo đảm** client thấy thứ tự DFS nếu không ghi:

```sql
ORDER BY dfs_order;
```

`SEARCH` tạo ra **cột để sắp xếp**, không tự coi kết quả là đã sắp xếp.

### 10.2. ORDER BY trong recursive term có thay SEARCH không?

Không nên dựa vào `ORDER BY` trong nhánh đệ quy để “điều khiển” chính xác thứ tự đi thăm từng node của mọi vòng. Optimizer và ngữ nghĩa quan hệ có thể làm kết quả khác kỳ vọng. Đối với yêu cầu xuất cây theo BFS/DFS, hãy **tạo khóa truy vết rõ ràng** và dùng `ORDER BY` ở truy vấn đọc cuối cùng.

### 10.3. Muốn thứ tự hoàn toàn xác định thì giải quyết tie

Trong một cây với các node có khóa sibling duy nhất, `SEARCH ... BY sibling_order, node_id` có thể tạo thứ tự hữu ích. Với **đồ thị** có nhiều đường đến cùng node, các hàng cùng node và tầng có thể cần **path** như khóa phụ.

Nếu hai hàng có tất cả khóa `ORDER BY` bằng nhau, SQL không cam kết hàng nào đứng trước. Với phân trang, xuất file hoặc kiểm tra kết quả lặp lại, phải nghĩ đến khóa phân định duy nhất của chính **hàng kết quả** (thường bao gồm đường đi, không chỉ node_id).

## 11. SEARCH và CYCLE kết hợp: mẫu báo cáo đầy đủ

Một mẫu hữu ích khi người vận hành muốn xem đồ thị từ gốc theo **tầng**, biết đường đi và biết hàng nào gây chu trình:

```sql
WITH RECURSIVE dependency_walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM dependency_walk AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
CYCLE node_id SET is_cycle USING path
SELECT
    node_id,
    depth,
    is_cycle,
    path,
    bfs_order
FROM dependency_walk
ORDER BY bfs_order, path;
```

Diễn giải:

1. Anchor bắt đầu từ node 1 ở depth 0.
2. Recursive term đọc các cạnh đi ra từ node hiện tại.
3. `SEARCH BREADTH FIRST` tạo khóa có thể sắp theo tầng.
4. `CYCLE node_id` phát hiện node đã xuất hiện trong đường đang xét và không mở rộng tiếp hàng gây vòng.
5. `SELECT` cuối chủ động `ORDER BY bfs_order, path`.

**Không đồng nhất** `depth` với `bfs_order`: depth chỉ là **số cạnh từ gốc**, còn bfs_order là **khóa thứ tự kết hợp độ sâu và biểu thức BY** do PostgreSQL sinh ra.

### 11.1. Báo cáo các cạnh đóng chu trình

Vì recursive CTE dùng `node_id` là đỉnh cuối, để biết cạnh nào làm vòng có thể giữ thêm **đỉnh trước đó**:

```sql
WITH RECURSIVE walk(node_id, parent_id, depth) AS (
    SELECT
        1::INTEGER AS node_id,
        NULL::INTEGER AS parent_id,
        0::INTEGER AS depth

    UNION ALL

    SELECT
        e.to_id AS node_id,
        w.node_id AS parent_id,
        w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT
    parent_id AS from_id,
    node_id AS to_id,
    depth,
    path
FROM walk
WHERE is_cycle
ORDER BY path;
```

Kết quả có những cạnh khép chu trình như `5 → 2`, `2 → 4` trên một đường khác, và `8 → 8`. Một chu trình có thể bị phát hiện tại những cạnh khác nhau tùy đường xuất phát/đường đã đi qua.

### 11.2. Tìm tất cả node nhưng không hiển thị hàng gây vòng

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::INTEGER
    UNION ALL
    SELECT e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT DISTINCT node_id
FROM walk
WHERE NOT is_cycle
ORDER BY node_id;
```

Truy vấn trả các node có thể tới đúng một lần, nhưng **bên trong vẫn phải tạo nhiều đường** trước khi `DISTINCT` loại trùng ngoài. Nếu mục tiêu chỉ là reachability và hiệu năng ở đồ thị lớn, cách `UNION` chỉ lưu `node_id` ở mục 4 có thể phù hợp hơn nhiều.

## 12. Lựa chọn khóa chu trình đúng với nghiệp vụ

Định nghĩa “quay lại cùng đỉnh” tùy mô hình.

### 12.1. ID toàn cục hay ID theo tenant?

Nếu `node_id` duy nhất toàn hệ thống, `CYCLE node_id` là đủ. Nếu dữ liệu tổ chức theo `tenant_id` và `local_id` chỉ duy nhất trong tenant, khóa định danh đúng là **cặp `(tenant_id, local_id)`**.

Ví dụ một recursive CTE đang giữ cả `tenant_id` và `local_id`:

```sql
-- Phần cuối của recursive CTE với hai cột định danh:
-- CYCLE tenant_id, local_id SET is_cycle USING path
```

Nhưng **trước đó** join cũng phải dùng tenant:

```sql
-- Ví dụ điều kiện JOIN đúng với mô hình multi-tenant:
-- ON e.tenant_id = w.tenant_id
-- AND e.from_local_id = w.local_id
```

Nếu quên điều kiện tenant ở JOIN, một node ID 12 của tenant khác có thể bị nối sai vào đường hiện tại, dẫn đến vừa sai báo cáo vừa có rủi ro lộ dữ liệu.

### 12.2. Node có thuộc tính đổi theo thời gian

Không dùng `label`, `status` hoặc `display_name` làm khóa nhận diện chu trình nếu hai node hợp lệ có thể trùng tên hoặc tên có thể thay đổi. Hãy dùng khóa định danh **ổn định**.

Nếu mô hình cố tình xem hai phiên bản của cùng một thực thể là **hai node phân biệt**, cần đưa version identifier vào khóa. Nếu không, `CYCLE id` sẽ coi việc trở lại cùng ID là một lần lặp dù phiên bản dữ liệu khác.

### 12.3. Chu trình cạnh và chu trình đỉnh

Phần lớn đồ thị phụ thuộc muốn phát hiện **lặp đỉnh**: một node đã có trên path. Một số bài toán đặc biệt muốn cho phép quay lại đỉnh nhưng không cho lặp **cùng cạnh**. Hai ngữ nghĩa này khác nhau.

Với bài toán trail (không lặp cạnh), phải lưu danh sách **định danh cạnh** trong path hoặc thiết kế truy vấn riêng; `CYCLE node_id` sẽ cắt đường sớm hơn quy tắc không lặp cạnh.

## 13. Cây tổ chức: dễ kiểm tra nhưng có bẫy

Một mô hình phân cấp phổ biến dùng cột `parent_id`:

```sql
CREATE TABLE graph_lab.categories (
    category_id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES graph_lab.categories(category_id),
    name TEXT NOT NULL
);

INSERT INTO graph_lab.categories
    (category_id, parent_id, name)
VALUES
    (10, NULL, 'All products'),
    (20, 10, 'Electronics'),
    (30, 10, 'Home'),
    (40, 20, 'Computers'),
    (50, 40, 'Laptops');
```

### 13.1. Truy vấn cây phân cấp

```sql
WITH RECURSIVE category_tree(
    category_id, parent_id, name, depth
) AS (
    SELECT
        c.category_id,
        c.parent_id,
        c.name,
        0::INTEGER
    FROM graph_lab.categories AS c
    WHERE c.category_id = 10

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.name,
        t.depth + 1
    FROM category_tree AS t
    JOIN graph_lab.categories AS c
        ON c.parent_id = t.category_id
)
SEARCH DEPTH FIRST BY category_id SET dfs_order
CYCLE category_id SET is_cycle USING path
SELECT
    category_id,
    parent_id,
    name,
    depth,
    is_cycle,
    path
FROM category_tree
ORDER BY dfs_order;
```

Kết quả đi từ danh mục 10 qua các danh mục con, được sắp theo khóa DFS. Với mô hình đúng, không có hàng `is_cycle=true`.

### 13.2. Tại sao FOREIGN KEY không cấm mọi chu trình?

`parent_id REFERENCES categories(category_id)` chỉ yêu cầu **cha tồn tại**. Nó không đảm bảo cấu trúc luôn là cây.

Ví dụ, nếu cập nhật parent của gốc 10 thành node 50:

```sql
-- Minh họa thao tác CÓ THỂ TẠO CHU TRÌNH; không chạy trong lab:
-- UPDATE graph_lab.categories
-- SET parent_id = 50
-- WHERE category_id = 10;
```

Các FK vẫn hợp lệ vì node 50 tồn tại, nhưng hình thành vòng:

```text
10 → 20 → 40 → 50 → 10
```

Một truy vấn duyệt **từ các node có parent_id IS NULL** có thể **không tìm thấy** thành phần chu trình nếu sau cập nhật không còn root đúng nghĩa. Khi phát hiện dữ liệu phân cấp hỏng, phải chọn anchor/chiến lược kiểm tra thích hợp thay vì tin rằng “không thấy chu trình từ root” đồng nghĩa toàn bảng không có chu trình.

### 13.3. Ngăn cập nhật tạo chu trình cần giải quyết đồng thời

Trước khi gán `parent_id=new_parent`, một ứng dụng có thể kiểm tra node dự định làm cha **không phải hậu duệ** của node đang di chuyển. Tuy nhiên, hai transaction đồng thời có thể cùng kiểm tra dữ liệu cũ rồi đưa ra hai cập nhật tạo vòng.

Muốn bảo đảm tính bất biến “không chu trình” ở production, cần thiết kế:

- Phạm vi khóa/serialization cho thay đổi quan hệ.
- Transaction và mức cô lập phù hợp.
- Kiểm tra recursive ancestry trong bối cảnh dữ liệu nhất quán.
- Xử lý retry/lỗi concurrency.
- Cơ chế kiểm tra và khôi phục nếu phát hiện dữ liệu bất thường.

Một trigger với `SELECT EXISTS` đơn giản **không mặc nhiên an toàn trước race condition**. `SEARCH` và `CYCLE` phục vụ đọc/quan sát, không thay thế chiến lược quản lý cập nhật.

## 14. Độ sâu, đường đi và hiển thị cấu trúc cây

Một số giao diện cần hiển thị:

```text
All products
  Electronics
    Computers
      Laptops
  Home
```

Ta có thể dùng `depth` để tạo độ thụt lề, và path/SEARCH để xác định thứ tự:

```sql
WITH RECURSIVE t(category_id, parent_id, name, depth) AS (
    SELECT
        category_id, parent_id, name, 0::INTEGER
    FROM graph_lab.categories
    WHERE category_id = 10

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.name,
        t.depth + 1
    FROM t
    JOIN graph_lab.categories AS c
        ON c.parent_id = t.category_id
)
SEARCH DEPTH FIRST BY category_id SET traversal_order
CYCLE category_id SET is_cycle USING path
SELECT
    repeat('  ', depth) || name AS tree_line,
    category_id,
    depth,
    is_cycle
FROM t
WHERE NOT is_cycle
ORDER BY traversal_order;
```

**Lưu ý:** Dấu cách hiển thị thụt lề chỉ là định dạng; ứng dụng nên nhận riêng `category_id`, `parent_id` và `depth` nếu cần tương tác cây. Không parse số dấu cách để suy ra quan hệ cha–con.

### 14.1. Giới hạn độ sâu chỉ để hiển thị

Một UI có thể chỉ muốn tải ba cấp:

```sql
WITH RECURSIVE t(category_id, depth) AS (
    SELECT 10::INTEGER, 0::INTEGER
    UNION ALL
    SELECT c.category_id, t.depth + 1
    FROM t
    JOIN graph_lab.categories AS c
        ON c.parent_id = t.category_id
    WHERE t.depth < 2
)
CYCLE category_id SET is_cycle USING path
SELECT category_id, depth, is_cycle
FROM t
ORDER BY path;
```

Điều kiện `t.depth < 2` tạo gốc depth 0, con depth 1 và cháu depth 2. Nó **không chứng minh cây thực tế sâu tối đa hai cấp**, chỉ là cắt dữ liệu theo nhu cầu hiển thị.

## 15. Phát hiện chu trình trong toàn bộ đồ thị: phạm vi và chi phí

Khi kiểm tra chất lượng dữ liệu, câu hỏi có thể là:

> “Trong bảng cạnh có tồn tại bất kỳ chu trình nào hay không, kể cả ở thành phần không nối với node 1?”

Duyệt từ một anchor đơn không đủ để trả lời phủ định trên toàn bộ đồ thị.

### 15.1. Mỗi đỉnh làm một anchor

Trong bài lab nhỏ, có thể bắt đầu từ tất cả các node:

```sql
WITH RECURSIVE walks(start_node, node_id) AS (
    SELECT
        n.node_id AS start_node,
        n.node_id AS node_id
    FROM graph_lab.nodes AS n

    UNION ALL

    SELECT
        w.start_node,
        e.to_id
    FROM walks AS w
    JOIN graph_lab.edges AS e
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT DISTINCT
    start_node,
    node_id AS repeated_node,
    path
FROM walks
WHERE is_cycle
ORDER BY start_node, path;
```

**Vì mọi node là anchor**, chu trình `8 → 8` vẫn được phát hiện ngay cả nếu nhánh đi tới 8 bị tách khỏi node 1 trong dữ liệu khác. Tuy nhiên:

- Một chu trình có thể được tìm thấy từ nhiều start_node.
- Một chu trình có thể được báo ở nhiều điểm đóng vòng.
- Số hàng trung gian có thể tăng rất mạnh trong đồ thị nhiều đường.
- `DISTINCT` trên `start_node, node_id, path` chỉ loại **những hàng giống hệt**, không tự chuẩn hóa hai cách bắt đầu/đi qua cùng một chu trình thành một đối tượng chu trình duy nhất.

Vì vậy, truy vấn này thích hợp để **minh họa kiểm tra trên bộ dữ liệu nhỏ**, không phải một thuật toán liệt kê mọi chu trình tối ưu cho đồ thị production rất lớn.

### 15.2. Chỉ cần biết có chu trình hay không

Với quy mô nhỏ, có thể bọc truy vấn:

```sql
WITH RECURSIVE walks(start_node, node_id) AS (
    SELECT node_id, node_id FROM graph_lab.nodes
    UNION ALL
    SELECT w.start_node, e.to_id
    FROM walks AS w
    JOIN graph_lab.edges AS e
      ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT EXISTS (
    SELECT 1
    FROM walks
    WHERE is_cycle
) AS has_any_cycle;
```

Kết quả trên dữ liệu lab là `true`. Nhưng **`EXISTS` không bảo đảm kế hoạch sẽ bỏ mọi công việc tốn kém** trong mọi ngữ cảnh; độ phức tạp của việc mở rộng đường đi vẫn cần được cân nhắc.

Trong đồ thị cực lớn, thuật toán chuyên biệt hoặc bảng closure/kiểm tra incremental theo yêu cầu hệ thống có thể phù hợp hơn.

## 16. Giới hạn an toàn và xử lý truy vấn chạy quá lâu

Một lỗi trong recursive CTE có thể tiêu thụ nhiều CPU, bộ nhớ và I/O. Không nên chỉ dựa vào việc “truy vấn demo chạy nhanh” để đưa vào hệ thống thật.

### 16.1. Ba lớp bảo vệ

| Biện pháp | Tác dụng | Giới hạn |
|---|---|---|
| **Phát hiện chu trình** (`CYCLE` hoặc path check) | Ngăn mở rộng vô hạn do lặp đỉnh trên path | Số đường đơn giản vẫn có thể bùng nổ |
| **Giới hạn độ sâu** (`depth < N`) | Giới hạn đường đi dài hơn N | Có thể bỏ sót kết quả hợp lệ |
| **Timeout/ngân sách thực thi** | Ngừng truy vấn quá lâu | Không sửa bản chất thuật toán và có thể hủy câu lệnh |

Ngoài ra, cần giới hạn dữ liệu đầu vào bằng tenant, loại cạnh, khoảng thời gian hoặc một danh sách gốc rõ ràng nếu yêu cầu nghiệp vụ cho phép.

### 16.2. statement_timeout cho phiên thử nghiệm

Với quyền thay đổi tham số trong phiên:

```sql
-- Ví dụ dành cho phiên thực hành, không đặt như mức chuẩn cho mọi hệ.
SET statement_timeout = '5s';

-- Chạy truy vấn WITH RECURSIVE đã có CYCLE hoặc giới hạn độ sâu.

RESET statement_timeout;
```

Nếu truy vấn vượt thời gian, PostgreSQL có thể hủy statement. Nếu đang nằm trong transaction đã bị lỗi, cần xử lý transaction trước khi tiếp tục. Không dùng timeout để hợp thức hóa một truy vấn thiếu kiểm soát chu trình.

### 16.3. Vì sao LIMIT ngoài cùng không phải bộ ngắt chu trình đáng tin?

Trong một số truy vấn PostgreSQL, CTE có thể được đọc theo nhu cầu nên:

```sql
-- Ví dụ KHÔNG AN TOÀN làm chiến lược dừng:
-- WITH RECURSIVE walk AS (...)
-- SELECT * FROM walk LIMIT 10;
```

có thể tình cờ trả mười hàng trước khi sinh hết kết quả. Nhưng nếu thêm `ORDER BY`, `JOIN` hoặc xử lý đòi đọc toàn bộ tập kết quả, PostgreSQL có thể phải đánh giá nhiều hơn hoặc toàn bộ CTE trước khi trả mười hàng.

**Không dùng `LIMIT` ngoài cùng như biện pháp đảm bảo chấm dứt recursion trên production.** Hãy kiểm soát chu trình/độ sâu ngay trong định nghĩa đệ quy.

### 16.4. Đường đi dài và chi phí của mảng path

Khi mỗi hàng giữ cả path, thao tác `path || node_id` tạo dãy đường ngày càng dài. Trên nhiều đường đi, hệ thống có thể phải giữ và so sánh rất nhiều mảng path:

- Tốn bộ nhớ và CPU.
- Tốn chi phí sắp xếp khi `ORDER BY path`.
- Có thể tạo tập kết quả lớn dù số node không lớn.
- Có thể ảnh hưởng tệp tạm và I/O.

Nếu chỉ cần tập node đi tới, `UNION` với cột `node_id` có thể tiết kiệm đáng kể hơn so với liệt kê mọi path. Nếu cần đường đi ngắn nhất, nên xem xét thuật toán chuyên biệt thay vì sinh tất cả đường.

## 17. Chỉ mục và kế hoạch thực thi

### 17.1. Index ở phía cạnh dùng để mở rộng

Truy vấn đệ quy thường làm:

```sql
JOIN graph_lab.edges AS e
  ON e.from_id = w.node_id
```

Khóa chính `PRIMARY KEY (from_id, to_id)` trong bảng lab đã tạo index B-tree với `from_id` là **cột dẫn đầu**, thường hữu ích cho việc tìm các cạnh đi ra từ một node.

Nếu ứng dụng còn hay duyệt ngược:

```sql
JOIN graph_lab.edges AS e
  ON e.to_id = w.node_id
```

có thể cân nhắc index riêng:

```sql
CREATE INDEX edges_to_id_idx
ON graph_lab.edges (to_id);
```

Tuy nhiên, index có chi phí dung lượng/ghi; trên đồ thị lab chỉ mười cạnh, planner có thể chọn sequential scan. Không coi điều đó là bằng chứng index vô ích cho dữ liệu thực.

### 17.2. EXPLAIN trên recursive CTE

```sql
EXPLAIN
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER
    UNION ALL
    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT node_id, depth, is_cycle
FROM walk
ORDER BY path;
```

Kế hoạch có thể chứa:

- `Recursive Union`: nút tổng hợp việc đánh giá đệ quy.
- `WorkTable Scan`: đọc hàng của working table trong bước lặp.
- `Index Scan`/`Hash Join`/`Nested Loop`/`Seq Scan` trên bảng cạnh, tùy số liệu.
- `Sort`: sắp xếp kết quả theo path hoặc search-order.

Kế hoạch cụ thể thay đổi theo thống kê, kích thước dữ liệu, index và phiên bản. Không suy từ tên `Recursive Union` rằng truy vấn đã chắc chắn chống chu trình; phải xem **điều kiện dừng**, `CYCLE` hoặc path logic.

### 17.3. EXPLAIN ANALYZE cần truy vấn an toàn

```sql
EXPLAIN (ANALYZE, BUFFERS)
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::INTEGER
    UNION ALL
    SELECT e.to_id
    FROM walk AS w
    JOIN graph_lab.edges AS e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT COUNT(*)
FROM walk;
```

`EXPLAIN ANALYZE` **thực thi câu lệnh**. Trên ví dụ có `CYCLE` và dữ liệu nhỏ, điều này phù hợp để thực hành; với query không bảo đảm dừng, không chạy `ANALYZE` chỉ để xem kế hoạch.

Các số liệu cần chú ý:

- Tổng số hàng/đường được sinh.
- Số vòng lặp của `WorkTable Scan`.
- Ước lượng hàng so với hàng thực tế.
- Có sort/ghi file tạm hay không.
- Thời gian trên mỗi vòng, lượng dữ liệu mở rộng qua JOIN.

### 17.4. Tối ưu theo yêu cầu thực, không theo một mẹo chung

Hãy hỏi:

- Có cần **mọi path** hay chỉ **mỗi node một lần**?
- Có cần chu trình **được đánh dấu** hay chỉ cần loại đường gây vòng?
- Có cần **thứ tự BFS/DFS** hay chỉ cần danh sách ID?
- Có thể lọc tenant/loại cạnh **trước và trong recursion** không?
- Có cần duyệt **ngược** hay **xuôi**?
- Có thể giới hạn chiều sâu một cách hợp lệ theo yêu cầu không?

Sự khác biệt về bài toán thường ảnh hưởng hiệu năng nhiều hơn việc chỉ tạo thêm một index hoặc đổi `ORDER BY`.

## 18. Đệ quy dưới MVCC và khi dữ liệu thay đổi đồng thời

Một câu truy vấn `WITH RECURSIVE` đơn lẻ tại isolation `READ COMMITTED` thông thường quan sát dữ liệu theo snapshot của statement. Nếu một giao dịch khác đang sửa cạnh, truy vấn thường không “nhảy” qua nhiều trạng thái đã commit vào giữa cùng một statement như một vòng lặp application gửi nhiều SELECT riêng.

Tuy nhiên:

- Hai **câu SELECT riêng** có thể thấy hai snapshot khác nhau.
- Một báo cáo chu trình chạy trước một cập nhật không chứng minh sau cập nhật đồ thị vẫn không có vòng.
- Một quy trình validate-then-update đơn giản có thể bị race condition nếu các cập nhật đồng thời không được phối hợp.
- Trên replica, dữ liệu có thể trễ so với primary; kiểm tra chu trình trên replica không tự bảo vệ thao tác ghi primary.

Khi mục tiêu là **bất biến dữ liệu**, cần đặt trọng tâm ở cơ chế ghi giao dịch/khóa/concurrency, không chỉ ở truy vấn duyệt.

## 19. Những sai lầm thường gặp

**1. “WITH RECURSIVE tự dừng khi thấy node cũ.”** Sai. Với `UNION ALL` không có điều kiện dừng, một chu trình có thể tạo hàng mãi.

**2. “Chỉ đổi UNION ALL thành UNION là giải quyết mọi chu trình.”** Sai nếu row state có `depth`, `path` hoặc cột thay đổi mỗi vòng.

**3. “Một node xuất hiện trong hai đường đi nghĩa là có chu trình.”** Không. DAG có thể có nhiều đường đến một node mà không có vòng.

**4. “CYCLE loại mọi hàng có liên quan tới chu trình khỏi kết quả.”** Không. Hàng **khép vòng** có thể vẫn xuất hiện với `is_cycle=true`, nhưng không tiếp tục được mở rộng.

**5. “WHERE NOT is_cycle ở SELECT cuối mới ngăn chạy vô hạn.”** Không phải vậy. Cơ chế `CYCLE` hoặc điều kiện ở recursive term phải kiểm soát mở rộng; lọc kết quả cuối chỉ quyết định **hiển thị**.

**6. “SEARCH DEPTH FIRST tự buộc PostgreSQL thực thi đệ quy kiểu DFS.”** Không. Nó tạo cột **sort order**; cần `ORDER BY` để trình bày DFS.

**7. “Truy vấn đệ quy không có ORDER BY vẫn luôn trả BFS.”** Không có bảo đảm thứ tự đầu ra, nhất là trong một tầng.

**8. “BFS trả mỗi node đúng một lần.”** Không tự động. Nếu giữ path và có hai đường đến cùng node, kết quả có thể chứa nhiều hàng cho node đó.

**9. “CYCLE luôn kiểm tra toàn bộ đồ thị.”** Không. Nó kiểm tra các đường từ anchor được chọn; thành phần không reachable không được duyệt.

**10. “PRIMARY KEY trên bảng edges ngăn chu trình.”** Không. Nó chỉ ngăn trùng cùng cặp cạnh theo thiết kế bảng.

**11. “FOREIGN KEY parent_id tạo ra cấu trúc cây hợp lệ.”** Không. FK đảm bảo cha tồn tại, không đảm bảo không có vòng.

**12. “Đặt LIMIT 10 ngoài recursive CTE là cơ chế dừng an toàn.”** Không. Sort/join/aggregate ở ngoài có thể buộc đánh giá nhiều hoặc toàn bộ recursion.

**13. “Giới hạn depth 5 phát hiện được mọi chu trình.”** Không. Chu trình sâu hơn sẽ bị cắt trước khi tới.

**14. “CYCLE id là đủ trong mọi hệ thống multi-tenant.”** Không nếu ID chỉ duy nhất trong một tenant; cần khóa và JOIN đúng phạm vi.

**15. “ORDER BY depth, node_id luôn phân biệt mọi hàng trong đồ thị.”** Không khi một node có nhiều path cùng depth.

**16. “Path là một ID toàn cục của node.”** Không. Path là **dãy đỉnh theo một lần mở rộng**; cùng node có thể có nhiều path.

**17. “Bật SEARCH giúp thuật toán shortest path.”** Không. `SEARCH` tạo khóa sort; bài toán đường ngắn nhất cần thêm logic và cân nhắc độ phức tạp.

**18. “Sắp theo path array lúc nào cũng đồng nghĩa sắp theo nhãn.”** Không. Nếu path chứa ID, nó sắp theo ID.

**19. “Cứ thêm tất cả node làm anchor là tối ưu nhất để tìm vòng.”** Không. Số path có thể tăng cực lớn và một chu trình bị báo nhiều lần.

**20. “Truy vấn phát hiện không có vòng đảm bảo transaction khác không tạo vòng sau đó.”** Không. Kiểm tra và ghi cần giao thức đồng thời phù hợp.

**21. “ORDER BY ở recursive term có thể thay cho ORDER BY cuối.”** Không nên dựa vào điều đó để đảm bảo thứ tự trả về.

**22. “COUNT(*) trên walk là số node duy nhất.”** Sai khi query sinh nhiều path đến cùng đỉnh.

**23. “Mọi khóa có NULL đều phù hợp với = ANY(path).”** Không. Ngữ nghĩa ba giá trị cần được xử lý riêng.

**24. “Thêm path không có chi phí.”** Không. Path dài và nhiều nhánh gây tăng bộ nhớ, CPU và chi phí sort.

## 20. Bài tập thực hành có đáp án

### Bài 1 — Xác định chu trình

Với các cạnh:

```text
1 -> 2
1 -> 3
2 -> 4
3 -> 4
4 -> 5
5 -> 2
```

**Hỏi:** những trường hợp nào là chu trình, trường hợp nào chỉ là nhiều đường tới cùng node?

**Đáp án:** `2 → 4 → 5 → 2` là chu trình. `1 → 2 → 4` và `1 → 3 → 4` chỉ cho thấy hai đường tới 4, **không tự tạo vòng**.

### Bài 2 — Vì sao UNION với depth vẫn không dừng?

```sql
WITH RECURSIVE w(node_id, depth) AS (
    SELECT 2, 0
    UNION
    SELECT e.to_id, w.depth + 1
    FROM w JOIN graph_lab.edges e ON e.from_id = w.node_id
)
SELECT * FROM w;
```

**Đáp án:** Trong chu trình `2 → 4 → 5 → 2`, node 2 được trả lại với `depth=3`, khác hàng `(2,0)`. `UNION` loại trùng **theo toàn bộ row**, nên không ngăn sinh các hàng mới ở độ sâu tăng dần. **Không chạy truy vấn này nguyên dạng** trên đồ thị có chu trình.

### Bài 3 — Lấy danh sách node reachable đúng một lần

**Yêu cầu:** từ node 1, chỉ cần tập định danh node, không cần path.

**Đáp án:**

```sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1::INTEGER
    UNION
    SELECT e.to_id
    FROM reachable r
    JOIN graph_lab.edges e ON e.from_id = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
```

Kết quả `1,2,3,4,5,6,7,8`.

### Bài 4 — Loại đường đi khép chu trình

**Yêu cầu:** từ node 1, giữ path mảng integer, không thêm node đã xuất hiện.

**Đáp án:**

```sql
WITH RECURSIVE walk(node_id, path) AS (
    SELECT 1::INTEGER, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_id, w.path || e.to_id
    FROM walk w
    JOIN graph_lab.edges e ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.path))
)
SELECT node_id, path
FROM walk
ORDER BY path;
```

Một node vẫn có thể xuất hiện trong hai hàng khác nhau nếu hai path khác nhau dẫn tới node đó; chỉ chặn lặp **trên từng path**.

### Bài 5 — Đánh dấu vòng mà vẫn xem cạnh đóng vòng

**Yêu cầu:** xem đường đi có chu trình và không mở rộng thêm sau khi khép vòng.

**Đáp án PostgreSQL 14+:**

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::INTEGER
    UNION ALL
    SELECT e.to_id
    FROM walk w JOIN graph_lab.edges e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT node_id, path
FROM walk
WHERE is_cycle
ORDER BY path;
```

Các hàng có `is_cycle=true` đánh dấu những lần node lặp trong đường đi đang duyệt. Chúng không bị tiếp tục mở rộng.

### Bài 6 — Thứ tự BFS

**Yêu cầu:** PostgreSQL 14+, lấy mọi hàng walk và hiển thị theo chiều rộng.

**Đáp án:**

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER
    UNION ALL
    SELECT e.to_id, w.depth + 1
    FROM walk w JOIN graph_lab.edges e ON e.from_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
CYCLE node_id SET is_cycle USING path
SELECT node_id, depth, is_cycle, path
FROM walk
ORDER BY bfs_order, path;
```

`SEARCH` tạo khóa thứ tự; `ORDER BY` cuối thực sự sắp xếp kết quả.

### Bài 7 — Thứ tự DFS

**Yêu cầu:** có thể dùng chính path do `CYCLE` sinh ra để trình bày DFS-like không?

**Đáp án:** Có. Dùng:

```sql
WITH RECURSIVE walk(node_id) AS (
    SELECT 1::INTEGER
    UNION ALL
    SELECT e.to_id
    FROM walk w JOIN graph_lab.edges e ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING path
SELECT node_id, path, is_cycle
FROM walk
ORDER BY path;
```

Sắp path tương ứng đi sâu theo từng nhánh với khóa node_id, không bắt buộc dùng cả `SEARCH DEPTH FIRST` khi đã có path.

### Bài 8 — Có thật chỉ 8 hàng kết quả không?

Một query `UNION ALL` giữ path đã kiểm soát cycle được chạy từ node 1 trên đồ thị 8 đỉnh.

**Hỏi:** `COUNT(*)` có bắt buộc bằng 8 không?

**Đáp án:** Không. Một node như 4 được đi tới theo nhiều path; kết quả giữ đường đi có thể có **nhiều hàng hơn số node**. Dùng `COUNT(DISTINCT node_id)` để đếm node cuối khác nhau, hoặc dùng truy vấn `UNION` chỉ có node_id nếu không cần path.

### Bài 9 — Gốc không thấy vòng

**Tình huống:** có chu trình trong một thành phần đồ thị không có đường từ gốc 1 tới đó. Chạy `CYCLE` bắt đầu từ node 1 không thấy `is_cycle=true`.

**Đáp án:** Không thể kết luận toàn đồ thị không có chu trình; chỉ chứng minh truy vấn **không phát hiện chu trình trong những đường đi được mở rộng từ gốc 1**. Cần duyệt các thành phần còn lại hoặc dùng phương án kiểm tra toàn đồ thị.

### Bài 10 — Không thể chỉ dùng FOREIGN KEY để cấm vòng

Một bảng nhân viên có `manager_id REFERENCES employees(id)`, nhưng A làm quản lý B và B làm quản lý A.

**Đáp án:** FK chỉ đảm bảo người quản lý được tham chiếu tồn tại. Cặp A↔B vẫn có thể hợp lệ về FK nhưng tạo chu trình. Cần kiểm tra quan hệ tổ tiên/hậu duệ với concurrency control khi cập nhật.

### Bài 11 — So sánh hai cú pháp

```sql
SEARCH BREADTH FIRST BY node_id SET seq
```

và:

```sql
SEARCH DEPTH FIRST BY node_id SET seq
```

**Đáp án:** Cả hai **tạo khóa thứ tự**, khác nhau ở cách khóa biểu diễn ưu tiên theo tầng hay theo nhánh sâu. Cả hai cần `ORDER BY seq` (và tie-breaker nếu cần) ở truy vấn cuối để bảo đảm cách trình bày.

### Bài 12 — Multi-tenant

**Tình huống:** cùng node ID 9 có thể xuất hiện ở hai tenant khác nhau.

**Đáp án:** Không nên chỉ dùng `CYCLE node_id` nếu hai bản ghi của hai tenant là thực thể khác nhau trong cùng truy vấn. Cân nhắc `CYCLE tenant_id, node_id` và JOIN các cạnh theo `tenant_id`. Thêm bộ lọc và kiểm soát quyền tenant; `CYCLE` không thay thế authorization.

### Bài 13 — Giới hạn depth có thay cycle detection không?

```sql
WHERE w.depth < 4
```

**Đáp án:** Giới hạn này ngăn sinh những đường sâu hơn mức đặt nhưng có thể bỏ sót một chu trình chỉ xuất hiện sau bước 4. Để truy vấn an toàn và có ý nghĩa, dùng thêm `CYCLE`/path check; depth cap là giới hạn tài nguyên/sản phẩm, không tự chứng minh đồ thị không có vòng.

### Bài 14 — Tối ưu hướng JOIN

**Yêu cầu:** truy vấn thường xuyên tìm các node đi tới từ node A bằng `edges.from_id = current_node`. Bảng có `PRIMARY KEY (from_id,to_id)`.

**Đáp án:** Khóa chính đã tạo B-tree index với cột đầu `from_id`, có thể hỗ trợ look-up cạnh đi ra. Nếu còn cần truy vấn ngược trên `to_id`, cân nhắc một index riêng cho `to_id` sau khi đo workload.

### Bài 15 — Tại sao kiểm tra trước INSERT chưa đủ?

Hai transaction cùng kiểm tra “nếu thêm cạnh này thì không có vòng” và đều nhận kết quả an toàn trên snapshot riêng trước khi mỗi transaction thêm một cạnh.

**Đáp án:** Hai thay đổi có thể kết hợp tạo vòng dù từng phép kiểm tra trước đó thấy an toàn. Cần transaction/concurrency protocol thích hợp (khóa/serialization/retry) nếu muốn đảm bảo bất biến không có cycle.

## 21. Quy trình chọn giải pháp cho đồ thị trong PostgreSQL

Trước khi viết truy vấn đệ quy ở dự án thật:

1. **Xác định mô hình quan hệ:** cây một cha, DAG, đồ thị có hướng, hay quan hệ hai chiều?
2. **Xác định chiều cạnh:** từ phụ thuộc tới phụ thuộc hay từ cha tới con? JOIN theo `from_id` hay `to_id`?
3. **Xác định phạm vi truy cập:** tenant, tổ chức, loại cạnh, trạng thái, thời điểm.
4. **Xác định kết quả:** mỗi node một lần, mỗi path một lần, danh sách cạnh gây vòng, hay chỉ boolean có vòng?
5. **Chọn anchor:** một root, nhiều root hay toàn bộ node; kết quả phủ được những thành phần nào?
6. **Chọn khóa định danh chu trình:** ID đơn, ID kết hợp tenant hoặc key nhiều cột; ưu tiên không NULL và ổn định.
7. **Kiểm soát recursion:** `CYCLE` từ PostgreSQL 14+, mảng path cho bản cũ, hoặc `UNION` chỉ ID khi mục tiêu reachability.
8. **Chọn thứ tự hiển thị:** BFS hay DFS; dùng `SEARCH`/`depth`/`path` và `ORDER BY` cuối.
9. **Kiểm soát khối lượng:** depth cap có chủ đích, lọc cạnh phù hợp, timeout, dự trù số path và kích thước kết quả.
10. **Tối ưu JOIN:** chỉ mục `edges(from_id)` hoặc `edges(to_id)` tùy hướng, thống kê và `EXPLAIN`.
11. **Đánh giá đồng thời:** truy vấn đọc phát hiện cycle không tự ngăn transaction ghi tạo cycle; cần bảo vệ invariant ở đường ghi.
12. **Thử các trường hợp biên:** self-loop, chu trình nhiều cạnh, DAG có nhiều cha, thành phần tách rời, root không tồn tại, node không có cạnh, nhiều tenant, dữ liệu lớn.
13. **Kiểm tra phiên bản:** dùng `SEARCH/CYCLE` chỉ trên PostgreSQL 14+, giải pháp mảng path khi cần tương thích cũ.
14. **Phân biệt kết quả kỹ thuật với nghiệp vụ:** đường đi “có thể tới” không mặc định là đường ngắn nhất, không mặc định là phụ thuộc hợp lệ hay được phép truy cập.

## 22. Tổng kết

Trong PostgreSQL, **`WITH RECURSIVE`** là công cụ để duyệt những cấu trúc phân cấp và đồ thị, nhưng nó **không tự chống chu trình** hay bảo đảm thứ tự đầu ra cho ứng dụng.

Những điểm cần ghi nhớ:

- **`UNION ALL`** giữ tất cả hàng được sinh; trên đồ thị có vòng phải có điều kiện dừng hoặc cycle control. **`UNION`** chỉ loại hàng trùng theo toàn bộ cột, nên phù hợp khi trạng thái chỉ chứa ID node nhưng không tự giải quyết các trạng thái có depth/path luôn thay đổi.
- **Mảng path + `ANY`** giúp nhận diện một đỉnh đã gặp trên **chính đường đi đang xét**, giữ được các đường khác nhau tới cùng node mà không lặp vô hạn.
- **`CYCLE node_id SET is_cycle USING path`** trên PostgreSQL 14+ tự đánh dấu hàng khép chu trình, cung cấp path và ngăn tiếp tục mở rộng nhánh gây vòng.
- **`SEARCH BREADTH FIRST` và `SEARCH DEPTH FIRST`** sinh **khóa sắp xếp** tương ứng BFS/DFS; muốn kết quả hiển thị đúng thứ tự phải dùng **`ORDER BY`** ở SELECT cuối.
- **Cycle detection theo path không đồng nghĩa loại trùng node toàn cục**, không tự phát hiện mọi chu trình ở thành phần không reachable và không tự ngăn INSERT/UPDATE tạo chu trình.
- **Độ sâu, số path, quyền tenant, chỉ mục và snapshot** là những yếu tố vận hành quan trọng. Một đồ thị không có vòng vẫn có thể tạo số đường đi rất lớn.

**Nguyên tắc cuối cùng:** trước khi chọn `SEARCH`, `CYCLE` hay `UNION`, hãy xác định rõ **đang duyệt từ đâu, cần mỗi đỉnh hay mỗi đường đi, chu trình được định nghĩa theo khóa nào, và muốn hiển thị theo tầng hay theo nhánh**. Khi bốn điều này được xác định, truy vấn đệ quy mới vừa đúng nghĩa vừa có thể kiểm soát được.

### Tài liệu PostgreSQL để tra cứu

- [WITH Queries, Recursive Queries, Search Order và Cycle Detection](https://www.postgresql.org/docs/current/queries-with.html).
- [SELECT và cú pháp WITH](https://www.postgresql.org/docs/current/sql-select.html).
- [Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html).
- [Row and Array Comparisons: ANY / ALL](https://www.postgresql.org/docs/current/functions-comparisons.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
