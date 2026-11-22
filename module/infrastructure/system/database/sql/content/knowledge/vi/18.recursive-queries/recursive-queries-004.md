# Tạo đường dẫn phân cấp và truy vấn tổ tiên, hậu duệ

Nhiều hệ thống lưu dữ liệu theo **cấu trúc phân cấp**: danh mục sản phẩm có danh mục cha và danh mục con, phòng ban nằm trong cơ cấu tổ chức, thư mục nằm trong thư mục khác, hoặc một công việc được chia thành nhiều công việc nhỏ. Khi người dùng chọn một danh mục, ứng dụng thường cần hiển thị **toàn bộ các danh mục con ở mọi cấp**, xác định **chuỗi tổ tiên** để tạo breadcrumb, hoặc tạo một **đường dẫn đầy đủ** từ gốc đến nút hiện tại.

Nếu dữ liệu chỉ có hai cấp, một phép `JOIN` có thể đủ. Nhưng khi số cấp **không cố định**, chuỗi `JOIN` viết tay sẽ khó mở rộng. SQL có **truy vấn đệ quy**, thường được viết bằng `WITH RECURSIVE` hoặc cơ chế tương đương theo phương ngữ, để lần theo liên kết cha–con từng bước cho đến khi không còn nút nào cần duyệt.

Bài này trình bày cách:

- Biểu diễn cây phân cấp trong bảng quan hệ bằng mô hình **adjacency list**.
- Viết CTE đệ quy để lấy **toàn bộ cây**, **cây con**, **hậu duệ** và **tổ tiên**.
- Tạo **đường dẫn tên** và **đường dẫn ID** từ gốc đến nút.
- Phân biệt cấp độ (*depth*), số bước tới tổ tiên (*hops*), nút lá và gốc.
- Sắp thứ tự duyệt cây; xử lý vòng lặp, dữ liệu bất thường và giới hạn độ sâu.
- Tổng hợp số liệu của một nhánh, tìm tổ tiên chung và đối chiếu cú pháp PostgreSQL, MySQL, SQL Server, SQLite, Oracle.

Các ví dụ hoàn chỉnh chính sử dụng **PostgreSQL**. Cú pháp mảng, `ARRAY_APPEND`, `STRING_AGG`, `SEARCH`/`CYCLE` và hàm xử lý đường dẫn là đặc thù hoặc có khác biệt giữa các DBMS; phần cuối cung cấp các dạng viết lại phù hợp.

## 1. Khái niệm gốc, cha, con, tổ tiên, hậu duệ và đường dẫn

Xét một cây danh mục:

```text
Cửa hàng [1]
├── Điện tử [2]
│   ├── Máy tính [4]
│   │   ├── Laptop [6]
│   │   │   └── Laptop gaming [12]
│   │   └── Linh kiện [7]
│   ├── Điện thoại [5]
│   │   ├── Android [10]
│   │   └── iOS [11]
│   └── Phụ kiện [13]
│       └── Sạc [14]
└── Sách [3]
    ├── Tiểu thuyết [8]
    ├── Kỹ năng [9]
    └── Sách lập trình [15]
        ├── SQL [16]
        └── Java [17]
```

Các thuật ngữ:

| Thuật ngữ | Ý nghĩa | Ví dụ trong cây |
|---|---|---|
| **Nút (node)** | Một phần tử của cây | Danh mục `Máy tính [4]` |
| **Nút gốc (root)** | Nút không có cha | `Cửa hàng [1]` |
| **Cha trực tiếp (parent)** | Nút nằm ngay trên một nút | Cha của `Laptop [6]` là `Máy tính [4]` |
| **Con trực tiếp (child)** | Nút nằm ngay dưới một nút | Các con của `Điện tử [2]` là `4, 5, 13` |
| **Tổ tiên (ancestor)** | Cha, cha của cha... đến gốc | Tổ tiên của `Laptop gaming [12]`: `6, 4, 2, 1` |
| **Hậu duệ (descendant)** | Con, cháu, các cấp sâu hơn | Hậu duệ của `Điện tử [2]`: `4, 5, 6, 7, 10, 11, 12, 13, 14` |
| **Nút lá (leaf)** | Nút không có con | `Linh kiện [7]`, `SQL [16]` |
| **Độ sâu (depth)** | Số cạnh đi từ gốc hoặc gốc cây con tới nút | `Laptop gaming [12]` có độ sâu `4` so với gốc 1 |
| **Đường dẫn (path)** | Chuỗi nút từ gốc đến nút đích | `1 → 2 → 4 → 6 → 12` |

Theo quy ước phổ biến, **tổ tiên/hậu duệ không bao gồm chính nút đang xét**. Nhưng nhiều truy vấn CTE đệ quy sẽ bắt đầu từ **nút đó** để thuận tiện; khi ấy kết quả là *cây con bao gồm gốc cây con*, còn muốn chỉ hậu duệ thì thêm điều kiện loại hàng neo. Bài này sẽ ghi rõ hai trường hợp.

### 1.1. Đường dẫn ID và đường dẫn tên phục vụ mục đích khác nhau

Đối với `Laptop gaming [12]`:

```text
Đường dẫn ID:
1 / 2 / 4 / 6 / 12

Đường dẫn tên:
Cửa hàng / Điện tử / Máy tính / Laptop / Laptop gaming
```

**Đường dẫn ID** dựa trên khóa ổn định, hữu ích cho kiểm tra quan hệ, phát hiện chu trình và sắp xếp theo cấu trúc. **Đường dẫn tên** thích hợp để hiển thị breadcrumb cho người dùng nhưng có thể thay đổi khi đổi tên danh mục. Hai danh mục ở các nhánh khác nhau có thể **trùng tên**; không nên dùng chuỗi tên làm danh tính duy nhất.

## 2. Mô hình adjacency list: mỗi hàng lưu ID của cha

Cách lưu cây đơn giản trong bảng quan hệ là đặt cột `parent_id` trỏ tới `category_id` của một hàng khác trong **cùng bảng**:

```sql
-- PostgreSQL
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY CHECK (category_id > 0),
    parent_id INTEGER REFERENCES categories(category_id),
    category_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    CHECK (parent_id IS NULL OR parent_id <> category_id)
);
```

Ý nghĩa:

- `category_id` là khóa định danh duy nhất của danh mục.
- `parent_id` chứa khóa của **cha trực tiếp**; `NULL` biểu thị nút không có cha.
- `category_name` chứa nhãn hiển thị.
- `sort_order` chứa thứ tự mong muốn giữa những nút cùng cha, không dùng làm khóa quan hệ.
- Ràng buộc khóa ngoại ngăn `parent_id` trỏ tới một ID **không tồn tại** trong trạng thái dữ liệu hợp lệ.
- `CHECK (parent_id <> category_id)` ngăn một nút tự chọn chính mình làm cha trực tiếp, nhưng **không đủ để ngăn vòng nhiều nút** như A → B → C → A.

Mô hình này còn gọi là **adjacency list**. Nó rất thuận tiện cho thao tác lấy cha trực tiếp hoặc con trực tiếp, nhưng muốn đi qua một số cấp không biết trước phải dùng **truy vấn đệ quy** hoặc cấu trúc phụ trợ.

### 2.1. Nạp một cây ví dụ cố định

```sql
INSERT INTO categories
    (category_id, parent_id, category_name, sort_order)
VALUES
    (1,  NULL, 'Cửa hàng',      10),
    (2,  1,    'Điện tử',       10),
    (3,  1,    'Sách',          20),
    (4,  2,    'Máy tính',      10),
    (5,  2,    'Điện thoại',    20),
    (6,  4,    'Laptop',        10),
    (7,  4,    'Linh kiện',     20),
    (8,  3,    'Tiểu thuyết',   10),
    (9,  3,    'Kỹ năng',       20),
    (10, 5,    'Android',       10),
    (11, 5,    'iOS',           20),
    (12, 6,    'Laptop gaming', 10),
    (13, 2,    'Phụ kiện',      30),
    (14, 13,   'Sạc',           10),
    (15, 3,    'Sách lập trình',30),
    (16, 15,   'SQL',           10),
    (17, 15,   'Java',          20);
```

Kiểm tra dữ liệu nguồn:

```sql
SELECT category_id, parent_id, category_name, sort_order
FROM categories
ORDER BY category_id;
```

| ID | parent_id | Tên danh mục | sort_order |
|---:|---:|---|---:|
| 1 | `NULL` | Cửa hàng | 10 |
| 2 | 1 | Điện tử | 10 |
| 3 | 1 | Sách | 20 |
| 4 | 2 | Máy tính | 10 |
| 5 | 2 | Điện thoại | 20 |
| 6 | 4 | Laptop | 10 |
| 7 | 4 | Linh kiện | 20 |
| 8 | 3 | Tiểu thuyết | 10 |
| 9 | 3 | Kỹ năng | 20 |
| 10 | 5 | Android | 10 |
| 11 | 5 | iOS | 20 |
| 12 | 6 | Laptop gaming | 10 |
| 13 | 2 | Phụ kiện | 30 |
| 14 | 13 | Sạc | 10 |
| 15 | 3 | Sách lập trình | 30 |
| 16 | 15 | SQL | 10 |
| 17 | 15 | Java | 20 |

Toàn bộ ví dụ truy vấn sau dựa trên **17 nút này**. Có một gốc duy nhất (`1`), và cấu trúc tạo thành một cây hợp lệ, không có chu trình.

### 2.2. Truy vấn một cấp không cần đệ quy

Cha trực tiếp của nút 12:

```sql
SELECT parent.category_id, parent.category_name
FROM categories AS child
JOIN categories AS parent
    ON parent.category_id = child.parent_id
WHERE child.category_id = 12;
-- 6 | Laptop
```

Các con trực tiếp của Điện tử:

```sql
SELECT category_id, category_name
FROM categories
WHERE parent_id = 2
ORDER BY sort_order, category_id;
```

Kết quả **4 Máy tính, 5 Điện thoại, 13 Phụ kiện**. Đây mới chỉ là **một cấp**; chưa có Laptop gaming, Android hoặc Sạc. Khi muốn mọi cấp, chuyển sang CTE đệ quy.

## 3. Cấu trúc WITH RECURSIVE: điểm neo và bước đệ quy

Mẫu cơ bản của PostgreSQL:

```sql
WITH RECURSIVE ten_cte AS (
    -- Phần neo (anchor): các hàng khởi đầu.
    SELECT ...
    FROM ...
    WHERE ...

    UNION ALL

    -- Phần đệ quy (recursive member): tìm bước tiếp theo.
    SELECT ...
    FROM bang_con AS c
    JOIN ten_cte AS t
        ON c.parent_id = t.category_id
)
SELECT ...
FROM ten_cte;
```

Hai thành phần:

1. **Phần neo** trả các nút xuất phát, ví dụ nút gốc `category_id = 1` hoặc nút bất kỳ `category_id = 2`.
2. **Phần đệ quy** lấy những nút liên hệ với kết quả vừa tìm, ví dụ những hàng có `parent_id` bằng `category_id` của nút đang duyệt.

`UNION ALL` nối kết quả các bước mà không loại trùng. Cơ chế đánh giá CTE đệ quy được DBMS thực hiện theo thuật toán lặp/tập làm việc; bạn không cần và cũng không nên mặc định SQL sẽ thực thi đúng thứ tự vật lý giống hàm đệ quy Java.

### 3.1. Một ví dụ nhỏ: chỉ lấy ID hậu duệ của nút 2

```sql
WITH RECURSIVE subtree AS (
    SELECT category_id, parent_id, 0 AS depth
    FROM categories
    WHERE category_id = 2

    UNION ALL

    SELECT c.category_id, c.parent_id, s.depth + 1
    FROM categories AS c
    JOIN subtree AS s
        ON c.parent_id = s.category_id
)
SELECT category_id, parent_id, depth
FROM subtree
ORDER BY depth, category_id;
```

Kết quả theo mức:

| depth | category_id | parent_id |
|---:|---:|---:|
| 0 | 2 | 1 |
| 1 | 4 | 2 |
| 1 | 5 | 2 |
| 1 | 13 | 2 |
| 2 | 6 | 4 |
| 2 | 7 | 4 |
| 2 | 10 | 5 |
| 2 | 11 | 5 |
| 2 | 14 | 13 |
| 3 | 12 | 6 |

Tổng có **10 hàng**: nút bắt đầu 2 và **9 hậu duệ**. `depth = 0` là chính nút neo; `depth = 1` là con trực tiếp; `depth = 2` là cháu; v.v.

Khi duyệt từ cha xuống con, điều kiện quan hệ là:

```sql
ON c.parent_id = s.category_id
```

Nếu viết nhầm chiều, truy vấn có thể đi lên tổ tiên hoặc không tìm thấy hàng đúng. Đối với một cây, **hướng nối** chính là hướng duyệt.

**Bản đơn giản này giả định dữ liệu không có chu trình.** Ở phần sau, ta thêm danh sách ID đã đi qua để tránh lặp vô hạn nếu dữ liệu bị lỗi.

## 4. Duyệt toàn bộ cây và tạo đường dẫn từ gốc

Một nhu cầu điển hình là lấy **toàn bộ danh mục với độ sâu và đường dẫn đầy đủ**, chẳng hạn để xây dựng breadcrumb, điều hướng hoặc xuất cấu trúc cây.

### 4.1. Lưu path dưới dạng mảng ID và mảng tên

Trong PostgreSQL, mảng là cách tiện lợi để tích lũy đường dẫn qua từng bước:

```sql
WITH RECURSIVE tree AS (
    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        0 AS depth,
        ARRAY[c.category_id] AS path_ids,
        ARRAY[c.category_name]::TEXT[] AS path_names
    FROM categories AS c
    WHERE c.parent_id IS NULL

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        t.depth + 1,
        ARRAY_APPEND(t.path_ids, c.category_id),
        ARRAY_APPEND(t.path_names, c.category_name)
    FROM categories AS c
    JOIN tree AS t
        ON c.parent_id = t.category_id
    WHERE NOT c.category_id = ANY(t.path_ids)
)
SELECT
    category_id,
    parent_id,
    depth,
    REPEAT('  ', depth) || category_name AS indented_name,
    path_ids,
    ARRAY_TO_STRING(path_names, ' / ') AS full_path
FROM tree
ORDER BY path_ids;
```

Giải thích từng cột:

- `depth`: số cạnh từ gốc tới nút; gốc có depth 0.
- `path_ids`: mảng ID trên đường từ gốc đến nút hiện tại.
- `path_names`: mảng tên tương ứng, phục vụ trình bày.
- `ARRAY_APPEND(t.path_ids, c.category_id)`: thêm ID nút con vào đường dẫn của cha.
- `ARRAY_TO_STRING(path_names, ' / ')`: tạo chuỗi đường dẫn dễ đọc.
- `REPEAT('  ', depth)`: thụt đầu dòng để thể hiện cấp trong bảng kết quả.
- `WHERE NOT c.category_id = ANY(t.path_ids)`: không đi tiếp tới ID đã có trong đường dẫn hiện tại, giúp chặn chu trình **trên đường đang xét**.

Một số hàng đáng chú ý:

| category_id | depth | path_ids | full_path |
|---:|---:|---|---|
| 1 | 0 | `{1}` | Cửa hàng |
| 2 | 1 | `{1,2}` | Cửa hàng / Điện tử |
| 4 | 2 | `{1,2,4}` | Cửa hàng / Điện tử / Máy tính |
| 6 | 3 | `{1,2,4,6}` | Cửa hàng / Điện tử / Máy tính / Laptop |
| 12 | 4 | `{1,2,4,6,12}` | Cửa hàng / Điện tử / Máy tính / Laptop / Laptop gaming |
| 14 | 3 | `{1,2,13,14}` | Cửa hàng / Điện tử / Phụ kiện / Sạc |
| 16 | 3 | `{1,3,15,16}` | Cửa hàng / Sách / Sách lập trình / SQL |

Vì dữ liệu mẫu có một gốc và không có chu trình, truy vấn trả **17 hàng**. Mỗi hàng thể hiện một nút, kèm đường đi từ gốc đến nó.

### 4.2. Vì sao lại dùng mảng ID thay vì chỉ nối tên?

Nếu chỉ nối văn bản:

```sql
t.full_path || ' / ' || c.category_name
```

ta cũng tạo được đường dẫn hiển thị. Nhưng có một số hạn chế:

- Hai nhánh có thể chứa **nút trùng tên**, ví dụ cả hai có thư mục “Tài liệu”.
- Tên có thể chứa chính dấu phân cách `/`, làm việc phân tích ngược trở nên nhập nhằng nếu không escape.
- Đổi tên danh mục sẽ đổi đường dẫn tên, dù khóa định danh không đổi.
- Kiểm tra vòng lặp bằng chuỗi tên có thể sai; phải kiểm tra **ID**.

Mảng ID biểu diễn danh tính của từng bước; mảng tên dành cho giao diện. Nếu cần lưu một khóa đường dẫn ở dạng chuỗi, nên sử dụng delimiter, cơ chế escape và quy tắc nhận diện ranh giới ID rõ ràng.

### 4.3. Tại sao ORDER BY path_ids tạo thứ tự theo nhánh?

Trên PostgreSQL, các mảng số nguyên có thể được so sánh theo thứ tự các phần tử. Vì đường dẫn cha là **tiền tố** của đường dẫn con, `ORDER BY path_ids` trong ví dụ này làm các nút cùng nhánh xuất hiện gần nhau theo thứ tự kiểu **depth-first** theo ID:

```text
1
1 / 2
1 / 2 / 4
1 / 2 / 4 / 6
1 / 2 / 4 / 6 / 12
1 / 2 / 4 / 7
1 / 2 / 5
...
1 / 3
1 / 3 / 8
...
```

Điều đó là **thứ tự đầu ra do `ORDER BY` quy định**, không khẳng định PostgreSQL đã thực thi các bước đệ quy theo đúng depth-first. Không có `ORDER BY`, thứ tự hàng của kết quả CTE đệ quy **không được bảo đảm**.

## 5. Chỉ lấy một cây con và hậu duệ của nút bất kỳ

Nhu cầu phổ biến: khi người dùng mở “Điện tử”, lấy **tất cả các danh mục nằm dưới Điện tử**, không chỉ ba con trực tiếp.

### 5.1. Cây con bao gồm nút bắt đầu

```sql
WITH RECURSIVE subtree AS (
    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        0 AS relative_depth,
        ARRAY[c.category_id] AS path_ids
    FROM categories AS c
    WHERE c.category_id = 2

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        s.relative_depth + 1,
        ARRAY_APPEND(s.path_ids, c.category_id)
    FROM categories AS c
    JOIN subtree AS s ON c.parent_id = s.category_id
    WHERE NOT c.category_id = ANY(s.path_ids)
)
SELECT
    category_id,
    category_name,
    relative_depth,
    path_ids
FROM subtree
ORDER BY path_ids;
```

Kết quả theo thứ tự ID nhánh: **2, 4, 6, 12, 7, 5, 10, 11, 13, 14**. Nút `2` có `relative_depth = 0` và là **gốc cây con**; những nút còn lại có độ sâu lớn hơn 0.

### 5.2. Chỉ lấy hậu duệ, không lấy nút xuất phát

Giữ nguyên CTE, đổi truy vấn cuối:

```sql
SELECT category_id, category_name, relative_depth
FROM subtree
WHERE relative_depth > 0
ORDER BY path_ids;
```

Kết quả gồm **9 hậu duệ**: **4, 6, 12, 7, 5, 10, 11, 13, 14** theo thứ tự đường dẫn. `relative_depth` bây giờ chính là **số cạnh từ nút 2** đến hậu duệ.

Đôi khi nghiệp vụ muốn tính cả nút xuất phát trong tập “descendants or self”. Hãy gọi rõ **“cây con bao gồm nút gốc”** hoặc **“hậu duệ không bao gồm chính nút”** để tránh lỗi đếm hoặc lọc nhầm.

### 5.3. Giới hạn số cấp duyệt

Giả sử giao diện chỉ mở tối đa **hai cấp con** từ Điện tử. Thêm điều kiện vào **phần đệ quy**:

```sql
WITH RECURSIVE subtree AS (
    SELECT category_id, parent_id, category_name, 0 AS relative_depth
    FROM categories
    WHERE category_id = 2

    UNION ALL

    SELECT c.category_id, c.parent_id, c.category_name,
           s.relative_depth + 1
    FROM categories AS c
    JOIN subtree AS s ON c.parent_id = s.category_id
    WHERE s.relative_depth < 2
)
SELECT category_id, category_name, relative_depth
FROM subtree
ORDER BY relative_depth, category_id;
```

Kết quả có **9 hàng**:

- Depth 0: `2`.
- Depth 1: `4, 5, 13`.
- Depth 2: `6, 7, 10, 11, 14`.

Nút `12` (Laptop gaming) ở depth 3 so với Điện tử không xuất hiện. Đặt giới hạn trong phần đệ quy giúp tránh sinh các cấp sâu hơn, trong khi chỉ lọc `WHERE relative_depth <= 2` ở truy vấn ngoài có thể vẫn khiến DBMS phải duyệt sâu trước khi loại kết quả.

**Đây là giới hạn duyệt theo nghiệp vụ, không phải giải pháp thay thế hoàn chỉnh cho kiểm tra chu trình.** Một chu trình ở các nút sâu vẫn là dữ liệu bất thường; ứng dụng nên ngăn lỗi đó và dùng cơ chế phát hiện phù hợp.

### 5.4. Tìm nút lá trong cây con

Một nút là lá nếu **không có con trực tiếp**:

```sql
WITH RECURSIVE subtree AS (
    SELECT category_id, parent_id, category_name,
           ARRAY[category_id] AS path_ids
    FROM categories
    WHERE category_id = 2

    UNION ALL

    SELECT c.category_id, c.parent_id, c.category_name,
           ARRAY_APPEND(s.path_ids, c.category_id)
    FROM categories AS c
    JOIN subtree AS s ON c.parent_id = s.category_id
    WHERE NOT c.category_id = ANY(s.path_ids)
)
SELECT s.category_id, s.category_name
FROM subtree AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM categories AS child
    WHERE child.parent_id = s.category_id
)
ORDER BY s.path_ids;
```

Kết quả: **12 Laptop gaming, 7 Linh kiện, 10 Android, 11 iOS, 14 Sạc** theo thứ tự đường dẫn. Một nút có **hậu duệ nhiều cấp** thì chắc chắn có ít nhất một con trực tiếp, nên kiểm tra `NOT EXISTS (con trực tiếp)` là đủ để xác định lá.

Khi dùng truy vấn đã **giới hạn số cấp**, cần phân biệt “lá thật của cây” và “nút đang ở mép giới hạn hiển thị”: một nút ở depth 2 có thể vẫn có con ở depth 3. Truy vấn trên kiểm tra bảng `categories` gốc, nên không nhầm nút ở mép hiển thị thành lá thật.

## 6. Truy vấn tổ tiên: đi ngược từ con lên cha

Muốn tạo breadcrumb cho `Laptop gaming [12]`, ta cần đi **từ nút hiện tại lên cha, rồi cha của cha**, cho tới gốc.

Điều kiện nối khi **đi lên** khác lúc đi xuống:

```sql
ON parent.category_id = current.parent_id
```

### 6.1. Lấy toàn bộ chuỗi tổ tiên

```sql
WITH RECURSIVE ancestors AS (
    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        0 AS hops,
        ARRAY[c.category_id] AS visited_ids
    FROM categories AS c
    WHERE c.category_id = 12

    UNION ALL

    SELECT
        parent.category_id,
        parent.parent_id,
        parent.category_name,
        a.hops + 1,
        ARRAY_APPEND(a.visited_ids, parent.category_id)
    FROM ancestors AS a
    JOIN categories AS parent
        ON parent.category_id = a.parent_id
    WHERE NOT parent.category_id = ANY(a.visited_ids)
)
SELECT
    category_id,
    category_name,
    hops
FROM ancestors
WHERE hops > 0
ORDER BY hops DESC;
```

Kết quả:

| category_id | category_name | hops |
|---:|---|---:|
| 1 | Cửa hàng | 4 |
| 2 | Điện tử | 3 |
| 4 | Máy tính | 2 |
| 6 | Laptop | 1 |

`hops` là số cạnh **đi lên từ nút 12**. Cha trực tiếp có `hops = 1`; gốc ở xa nhất có `hops = 4`. Truy vấn neo có `hops = 0` ứng với chính nút 12; điều kiện `WHERE hops > 0` loại nút đó để kết quả chỉ còn **tổ tiên**.

`ORDER BY hops DESC` đưa gốc lên đầu, phù hợp thứ tự hiển thị breadcrumb. Nếu muốn người gần nhất trước, dùng `ORDER BY hops ASC`.

### 6.2. Tạo breadcrumb bằng STRING_AGG

Giữ nguyên CTE `ancestors` ở trên, nhưng **không loại hàng `hops = 0`**, vì breadcrumb thường bao gồm cả nút hiện tại:

```sql
WITH RECURSIVE ancestors AS (
    SELECT
        category_id, parent_id, category_name,
        0 AS hops,
        ARRAY[category_id] AS visited_ids
    FROM categories
    WHERE category_id = 12

    UNION ALL

    SELECT
        p.category_id, p.parent_id, p.category_name,
        a.hops + 1,
        ARRAY_APPEND(a.visited_ids, p.category_id)
    FROM ancestors AS a
    JOIN categories AS p ON p.category_id = a.parent_id
    WHERE NOT p.category_id = ANY(a.visited_ids)
)
SELECT
    STRING_AGG(category_name, ' / ' ORDER BY hops DESC) AS breadcrumb
FROM ancestors;
```

Kết quả:

```text
Cửa hàng / Điện tử / Máy tính / Laptop / Laptop gaming
```

**Vì sao phải sắp xếp ngay trong `STRING_AGG`?** Truy vấn đệ quy bắt đầu ở nút 12 rồi đi lên gốc; nếu chỉ nối chuỗi theo thứ tự hàng tình cờ, ta có thể nhận đường dẫn **con → cha**, trái với cách breadcrumb thông thường. `STRING_AGG(... ORDER BY hops DESC)` yêu cầu thứ tự rõ ràng khi tạo chuỗi.

### 6.3. Tổ tiên trực tiếp khác với tất cả tổ tiên

Nếu chỉ cần cha trực tiếp, **không cần CTE đệ quy**:

```sql
SELECT p.category_id, p.category_name
FROM categories AS child
JOIN categories AS p
    ON p.category_id = child.parent_id
WHERE child.category_id = 12;
-- 6 | Laptop
```

CTE đệ quy chỉ thật sự hữu ích khi yêu cầu “lấy **mọi** tổ tiên” hoặc “tạo đường dẫn đầy đủ”, vì số cấp không biết trước.

## 7. Đường dẫn từ gốc và đường dẫn tương đối khác nhau

Cùng một nút, có thể tạo nhiều dạng path:

| Nút | Đường từ gốc tuyệt đối | Đường tương đối khi bắt đầu tại Điện tử |
|---|---|---|
| `Máy tính [4]` | `1 / 2 / 4` | `2 / 4` |
| `Laptop [6]` | `1 / 2 / 4 / 6` | `2 / 4 / 6` |
| `Laptop gaming [12]` | `1 / 2 / 4 / 6 / 12` | `2 / 4 / 6 / 12` |

Nếu CTE bắt đầu từ `category_id = 1`, `path_ids` là đường dẫn **từ gốc toàn cây**. Nếu bắt đầu từ `category_id = 2`, `path_ids` chỉ mô tả đường dẫn **trong cây con**, trừ khi bạn đã lấy đường từ gốc đến 2 và nối vào.

**Ví dụ:** CTE ở mục 5 neo tại 2 nên đường dẫn của nút 12 là `{2,4,6,12}`, không phải `{1,2,4,6,12}`. Điều này **không sai**; nó biểu diễn một phạm vi khác. Khi lưu đường dẫn hoặc trả dữ liệu qua API, cần quy ước rõ đường dẫn **tuyệt đối** hay **tương đối**.

### 7.1. Lấy đường dẫn cho đúng một nút theo cách đi từ gốc

Một cách là duyệt toàn cây và lọc nút cần lấy ở ngoài:

```sql
WITH RECURSIVE tree AS (
    SELECT
        category_id, parent_id, category_name,
        ARRAY[category_id] AS path_ids,
        ARRAY[category_name]::TEXT[] AS path_names
    FROM categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        c.category_id, c.parent_id, c.category_name,
        ARRAY_APPEND(t.path_ids, c.category_id),
        ARRAY_APPEND(t.path_names, c.category_name)
    FROM categories AS c
    JOIN tree AS t ON c.parent_id = t.category_id
    WHERE NOT c.category_id = ANY(t.path_ids)
)
SELECT
    path_ids,
    ARRAY_TO_STRING(path_names, ' / ') AS full_path
FROM tree
WHERE category_id = 12;
```

Kết quả: `{1,2,4,6,12}` và đường dẫn tên đã nêu.

Tuy nhiên, nếu cây rất lớn và chỉ cần một breadcrumb, **truy vấn đi lên từ nút đích như mục 6** thường tránh phải duyệt toàn bộ các nhánh không liên quan. Cách chọn phụ thuộc chỉ mục, kích thước dữ liệu và mô hình sử dụng.

## 8. Sắp xếp cây theo thứ tự anh em

Không phải lúc nào ID nhỏ hơn cũng được hiển thị trước. Ví dụ quản trị viên có thể đặt `sort_order` để điều chỉnh thứ tự danh mục trong menu.

Trong bộ dữ liệu mẫu, các con của `Điện tử [2]` là:

| category_id | category_name | sort_order |
|---:|---|---:|
| 4 | Máy tính | 10 |
| 5 | Điện thoại | 20 |
| 13 | Phụ kiện | 30 |

Để có thứ tự **theo toàn bộ đường dẫn của các khóa sắp xếp**, cần tích lũy một *sort path* qua từng cấp. PostgreSQL có thể dùng mảng chuỗi khóa được chuẩn hóa:

```sql
WITH RECURSIVE sorted_tree AS (
    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        ARRAY[
            LPAD(c.sort_order::TEXT, 6, '0')
            || ':'
            || LPAD(c.category_id::TEXT, 8, '0')
        ] AS sort_path
    FROM categories AS c
    WHERE c.parent_id IS NULL

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        ARRAY_APPEND(
            t.sort_path,
            LPAD(c.sort_order::TEXT, 6, '0')
            || ':'
            || LPAD(c.category_id::TEXT, 8, '0')
        )
    FROM categories AS c
    JOIN sorted_tree AS t ON c.parent_id = t.category_id
)
SELECT category_id, category_name, sort_path
FROM sorted_tree
ORDER BY sort_path;
```

Giải thích:

- `LPAD(sort_order::TEXT, 6, '0')` tạo phần thứ tự có độ rộng cố định, ví dụ `000010`, `000020`.
- Ghép thêm `category_id` tạo **khóa phụ** nếu hai anh em có cùng `sort_order`.
- Mỗi cấp bổ sung một phần tử trong mảng `sort_path`.
- `ORDER BY sort_path` xếp theo vị trí của **mọi tổ tiên**, nên từng nhánh nằm cùng nhau.

Trong ví dụ, `sort_order` được ràng buộc không âm. Cách dùng `LPAD` độ rộng cố định giả định giá trị không vượt quá số chữ số đã chọn; trong sản xuất, cần thiết kế giới hạn hoặc biểu diễn sort key đủ lớn để tránh cắt mất thông tin. Đây là **một kỹ thuật minh họa**, không phải bắt buộc mọi hệ thống phải lưu đường dẫn sắp xếp dưới dạng chuỗi.

### 8.1. SEARCH DEPTH FIRST và BREADTH FIRST trên PostgreSQL

PostgreSQL 14 trở lên hỗ trợ cú pháp `SEARCH` của truy vấn đệ quy để tạo cột dùng cho thứ tự duyệt:

```sql
WITH RECURSIVE tree(category_id, parent_id, category_name, depth) AS (
    SELECT category_id, parent_id, category_name, 0
    FROM categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT c.category_id, c.parent_id, c.category_name, t.depth + 1
    FROM categories AS c
    JOIN tree AS t ON c.parent_id = t.category_id
)
SEARCH DEPTH FIRST BY category_id SET traversal_order
SELECT category_id, category_name, depth
FROM tree
ORDER BY traversal_order;
```

`SEARCH DEPTH FIRST` tạo khóa thứ tự kiểu duyệt **đi sâu theo nhánh**; có thể thay bằng `SEARCH BREADTH FIRST` nếu muốn các nút được hiển thị **theo từng tầng**. `SEARCH` cung cấp cột `traversal_order` để **sắp xếp kết quả**; không được suy diễn rằng cơ sở dữ liệu bắt buộc thực thi nội bộ theo đúng chiến lược đó.

Nếu DBMS không hỗ trợ `SEARCH`, có thể tạo `path_ids` để sắp theo nhánh hoặc sắp `ORDER BY depth, ...` để hiển thị theo tầng. Trong mọi trường hợp, muốn kết quả ổn định cần có **`ORDER BY` cuối** với các khóa phân định phù hợp.

## 9. Tìm tổ tiên chung gần nhất của hai nút

Trong ứng dụng có thể cần tìm **tổ tiên chung gần nhất** (*lowest common ancestor*, LCA), ví dụ xác định nhóm chung của hai danh mục.

Với `Laptop gaming [12]` và `Sạc [14]`:

```text
12 → 6 → 4 → 2 → 1
14 → 13 → 2 → 1
```

Các tổ tiên chung là **2 và 1**; tổ tiên chung **gần nhất** là **2 — Điện tử**.

Có thể viết hai chuỗi đi lên rồi tìm nút chung:

```sql
WITH RECURSIVE
up_a AS (
    SELECT category_id, parent_id, 0 AS hops
    FROM categories
    WHERE category_id = 12

    UNION ALL

    SELECT p.category_id, p.parent_id, a.hops + 1
    FROM up_a AS a
    JOIN categories AS p ON p.category_id = a.parent_id
),
up_b AS (
    SELECT category_id, parent_id, 0 AS hops
    FROM categories
    WHERE category_id = 14

    UNION ALL

    SELECT p.category_id, p.parent_id, b.hops + 1
    FROM up_b AS b
    JOIN categories AS p ON p.category_id = b.parent_id
)
SELECT c.category_id, c.category_name
FROM up_a AS a
JOIN up_b AS b USING (category_id)
JOIN categories AS c USING (category_id)
ORDER BY a.hops ASC
LIMIT 1;
```

Kết quả: **2 — Điện tử**. Vì cây có **một cha mỗi nút** và không có chu trình, các tổ tiên của nút 12 là một chuỗi duy nhất. Trong các tổ tiên chung, nút có số bước `a.hops` **nhỏ nhất** tính từ 12 là tổ tiên chung sâu nhất.

**Lưu ý:** ví dụ này giả định cây hợp lệ. Trong một đồ thị có nhiều cha, có thể có nhiều đường đi và nhiều ứng viên tổ tiên chung, khiến khái niệm “gần nhất” cần định nghĩa khác. Khi phải hỗ trợ cấu trúc đồ thị tổng quát, cần mô hình và thuật toán phù hợp.

## 10. Tính tổng số liệu trên toàn bộ cây con

Một câu hỏi quản trị thường gặp: **“Doanh thu của nhóm Điện tử, bao gồm mọi danh mục con, là bao nhiêu?”** Nếu số liệu gắn ở các nút lá hoặc từng danh mục, ta cần lấy **cả cây con** rồi tổng hợp.

### 10.1. Tạo số liệu doanh thu trực tiếp theo danh mục

Trong database học tập, tạo bảng minh họa:

```sql
CREATE TABLE category_sales (
    category_id INTEGER PRIMARY KEY REFERENCES categories(category_id),
    direct_revenue NUMERIC(12, 2) NOT NULL CHECK (direct_revenue >= 0)
);

INSERT INTO category_sales (category_id, direct_revenue)
VALUES
    (7,   50000.00),
    (8,  120000.00),
    (9,   60000.00),
    (10,  80000.00),
    (11, 100000.00),
    (12, 200000.00),
    (14,  30000.00),
    (16,  70000.00),
    (17,  90000.00);
```

`direct_revenue` là doanh thu **ghi trực tiếp ở đúng danh mục**. Bảng này có **tối đa một hàng mỗi category_id**, giúp tránh nhân tiền khi nối với danh mục. Những danh mục không có bản ghi `category_sales` được xem là có doanh thu trực tiếp 0 **theo quy ước của bài tập**.

### 10.2. Tổng doanh thu trong nhánh Điện tử

```sql
WITH RECURSIVE subtree AS (
    SELECT
        category_id,
        parent_id,
        ARRAY[category_id] AS visited_ids
    FROM categories
    WHERE category_id = 2

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        ARRAY_APPEND(s.visited_ids, c.category_id)
    FROM categories AS c
    JOIN subtree AS s ON c.parent_id = s.category_id
    WHERE NOT c.category_id = ANY(s.visited_ids)
)
SELECT
    COALESCE(SUM(cs.direct_revenue), 0) AS electronics_revenue
FROM subtree AS s
LEFT JOIN category_sales AS cs
    ON cs.category_id = s.category_id;
```

Kết quả: **460.000**.

Các danh mục đóng góp trực tiếp vào nhánh Điện tử:

| Danh mục | ID | Doanh thu |
|---|---:|---:|
| Laptop gaming | 12 | 200.000 |
| Linh kiện | 7 | 50.000 |
| Android | 10 | 80.000 |
| iOS | 11 | 100.000 |
| Sạc | 14 | 30.000 |
| **Tổng** | | **460.000** |

Chìa khóa là `subtree` trả **mỗi danh mục trong nhánh đúng một lần** khi dữ liệu là cây hợp lệ. `category_sales` cũng có khóa chính `category_id`, nên phép nối không làm lặp doanh thu.

**Không được cộng lại những tổng đã bao gồm con** nếu dữ liệu nguồn đã lưu doanh thu lũy kế ở các nút cha. Ở bài này `direct_revenue` là số liệu trực tiếp, không phải “doanh thu toàn bộ nhánh” đã được cộng trước. Khi tính số liệu phân cấp, phải phân biệt **số liệu trực tiếp của nút** với **số liệu lũy kế của cây con** để không đếm hai lần.

### 10.3. Tổng số hậu duệ và số lá

Trên nhánh Điện tử, muốn đếm số hậu duệ và số lá trong cùng một tập:

```sql
WITH RECURSIVE subtree AS (
    SELECT category_id, parent_id, 0 AS depth
    FROM categories
    WHERE category_id = 2

    UNION ALL

    SELECT c.category_id, c.parent_id, s.depth + 1
    FROM categories AS c
    JOIN subtree AS s ON c.parent_id = s.category_id
)
SELECT
    COUNT(*) FILTER (WHERE depth > 0) AS descendants_count,
    COUNT(*) FILTER (
        WHERE NOT EXISTS (
            SELECT 1
            FROM categories AS child
            WHERE child.parent_id = subtree.category_id
        )
    ) AS leaf_count
FROM subtree;
```

Ý tưởng kết quả là **9 hậu duệ và 5 nút lá**. Tuy nhiên, một số DBMS và cấu trúc `FILTER`/subquery trong biểu thức tổng hợp có hạn chế cú pháp. Để dễ chuyển phương ngữ và làm rõ phép tính, có thể tách cờ lá ở một CTE thứ hai:

```sql
WITH RECURSIVE subtree AS (
    SELECT category_id, parent_id, 0 AS depth
    FROM categories WHERE category_id = 2
    UNION ALL
    SELECT c.category_id, c.parent_id, s.depth + 1
    FROM categories c
    JOIN subtree s ON c.parent_id = s.category_id
),
marked AS (
    SELECT
        s.category_id,
        s.depth,
        CASE WHEN EXISTS (
            SELECT 1 FROM categories AS child
            WHERE child.parent_id = s.category_id
        ) THEN 0 ELSE 1 END AS is_leaf
    FROM subtree AS s
)
SELECT
    SUM(CASE WHEN depth > 0 THEN 1 ELSE 0 END) AS descendants_count,
    SUM(is_leaf) AS leaf_count
FROM marked;
```

Kết quả: **descendants_count = 9**, **leaf_count = 5**. Với truy vấn đệ quy bất kỳ trên dữ liệu có thể chứa chu trình, cần bổ sung điều kiện tránh duyệt lại như đã trình bày trước đó.

## 11. Phát hiện và phòng tránh chu trình

CTE đệ quy giả định liên kết dữ liệu hình thành một cấu trúc có điểm dừng. Nhưng trong thực tế, lỗi cập nhật cha có thể tạo **vòng lặp**:

```text
A.parent = B
B.parent = C
C.parent = A
```

Nếu cứ lần theo cha–con mà không phát hiện vòng, một bước đệ quy sẽ lại sinh ra nút đã gặp. Đối với truy vấn tích lũy `depth` hay `path`, ngay cả đổi `UNION ALL` thành `UNION` cũng **không đủ** để phá chu trình, vì mỗi lần quay lại cùng ID có thể mang `depth` hoặc `path` khác.

### 11.1. Chặn lặp bằng danh sách ID đã đi qua

Trong những ví dụ PostgreSQL trước, ta đã dùng:

```sql
WHERE NOT c.category_id = ANY(t.path_ids)
```

Ý nghĩa: chỉ bước tiếp tới danh mục `c` nếu ID của nó **chưa có** trong đường dẫn hiện tại. Điều kiện này ngăn một nhánh lặp lại nút cũ, giúp truy vấn không duyệt vô hạn theo chu trình đó.

Đây là kiểm tra **trên từng đường dẫn**, không phải một tập “đã thăm toàn cục” độc lập với đường đi. Trong dữ liệu là **đồ thị có nhiều cha**, cùng một nút có thể xuất hiện theo nhiều đường khác nhau và phải xác định có muốn khử trùng theo nút hay giữ các đường đi khác nhau. Mô hình bài này có **một parent_id duy nhất cho mỗi danh mục**, nên trong một cây hợp lệ mỗi nút chỉ có một đường từ gốc.

### 11.2. CYCLE clause của PostgreSQL 14+

PostgreSQL 14 trở lên có cú pháp `CYCLE` để yêu cầu DBMS tạo cờ phát hiện chu trình và đường dẫn:

```sql
WITH RECURSIVE walk(category_id, parent_id, category_name, depth) AS (
    SELECT category_id, parent_id, category_name, 0
    FROM categories
    WHERE category_id = 2

    UNION ALL

    SELECT c.category_id, c.parent_id, c.category_name, w.depth + 1
    FROM categories AS c
    JOIN walk AS w ON c.parent_id = w.category_id
)
CYCLE category_id SET is_cycle USING cycle_path
SELECT category_id, category_name, depth, is_cycle
FROM walk
ORDER BY depth, category_id;
```

`CYCLE` giúp đánh dấu những hàng dẫn tới chu trình và ngăn tiếp tục triển khai đường lặp theo quy tắc của PostgreSQL. Trong dữ liệu mẫu hợp lệ, `is_cycle` đều là `FALSE`.

Nếu cần tự kiểm soát chi tiết thứ tự và cách lưu đường dẫn trên PostgreSQL cũ hơn, dùng cách mang `path_ids` trong CTE như phần trước. Không sao chép nguyên cú pháp `CYCLE` của PostgreSQL sang hệ khác nếu chưa kiểm tra phiên bản và khả năng hỗ trợ.

### 11.3. Không nhìn thấy nút từ gốc không có nghĩa dữ liệu không tồn tại

Một truy vấn:

```sql
WITH RECURSIVE tree AS (
    SELECT category_id, parent_id
    FROM categories
    WHERE parent_id IS NULL
    UNION ALL
    SELECT c.category_id, c.parent_id
    FROM categories c
    JOIN tree t ON c.parent_id = t.category_id
)
SELECT * FROM tree;
```

chỉ duyệt được những nút **có đường đi từ gốc**. Nếu dữ liệu có một **chu trình tách rời không chứa nút gốc**, không nút nào trong chu trình đó được truy vấn trên tìm thấy. Nếu hệ thống cho phép nhiều cây độc lập, phải xác định rõ danh sách gốc và yêu cầu nghiệp vụ thay vì mặc định chỉ có một cây duy nhất.

Ràng buộc khóa ngoại giúp ngăn parent_id trỏ tới hàng không tồn tại khi được bật và áp dụng hợp lệ, nhưng không đảm bảo **không có chu trình nhiều nút**. Nếu cần dữ liệu luôn là một cây/forest hợp lệ, ứng dụng hoặc database phải kiểm tra khi **đổi cha**.

### 11.4. Kiểm tra một thao tác đổi cha có tạo chu trình không

Giả sử định chuyển `Điện tử [2]` thành con của `Laptop gaming [12]`. Đây là thao tác **không hợp lệ** vì nút 12 vốn nằm bên trong cây con của nút 2: kết quả sẽ tạo vòng 2 → ... → 12 → 2.

Trước khi sửa dữ liệu, có thể truy vấn:

```sql
WITH RECURSIVE subtree AS (
    SELECT category_id, parent_id
    FROM categories
    WHERE category_id = 2
    UNION ALL
    SELECT c.category_id, c.parent_id
    FROM categories c
    JOIN subtree s ON c.parent_id = s.category_id
)
SELECT NOT EXISTS (
    SELECT 1
    FROM subtree
    WHERE category_id = 12
) AS safe_to_move;
```

Kết quả: **`FALSE`**, vì 12 nằm trong cây con của 2.

Đây chỉ là **bước kiểm tra logic**. Khi có nhiều giao dịch đồng thời sửa quan hệ cha–con, kiểm tra trước rồi `UPDATE` sau có thể gặp tình trạng dữ liệu thay đổi ở giữa. Muốn ngăn chu trình chắc chắn ở hệ thống thật cần thiết kế giao dịch, khóa hoặc cơ chế ràng buộc phù hợp để kiểm tra và thay đổi diễn ra nhất quán.

## 12. Hiệu năng truy vấn phân cấp

Với cây nhỏ vài chục nút, CTE đệ quy thường chạy đơn giản. Với cây hàng triệu nút hoặc giao diện phải mở nhánh thường xuyên, cần xem xét chỉ mục, giới hạn phạm vi duyệt và cách tổ chức số liệu.

### 12.1. Chỉ mục trên parent_id

Điều kiện đi xuống cây thường là:

```sql
ON c.parent_id = t.category_id
```

Một chỉ mục trên `parent_id` có thể giúp DBMS tìm con của mỗi nút:

```sql
CREATE INDEX idx_categories_parent
ON categories (parent_id);
```

Với menu muốn sắp con theo thứ tự riêng, có thể cân nhắc chỉ mục ghép:

```sql
CREATE INDEX idx_categories_parent_sort
ON categories (parent_id, sort_order, category_id);
```

Hai chỉ mục trên là ví dụ lựa chọn; không nhất thiết tạo cả hai trong mọi hệ thống vì chỉ mục ghép có thể phục vụ cả một số truy vấn chỉ lọc `parent_id`. Chỉ mục có chi phí ghi và lưu trữ; nên dựa trên kế hoạch và dữ liệu thực tế để quyết định.

Khi đi **lên tổ tiên**, điều kiện `parent.category_id = current.parent_id` thường có thể sử dụng khóa chính/unique index của `category_id`.

### 12.2. Chỉ duyệt nhánh cần thiết

Nếu chỉ hỏi hậu duệ của danh mục 2, hãy đặt:

```sql
WHERE category_id = 2
```

trong **phần neo**, không duyệt toàn bộ các gốc rồi mới dùng `WHERE category_id = 2` ở cuối. Trong truy vấn từ gốc, việc lọc ở cuối chỉ giữ chính nút 2, **không tự giữ toàn bộ hậu duệ của nó** nếu mục tiêu là lấy cây con.

Nếu giao diện chỉ cần hai cấp, dùng giới hạn `relative_depth` trong phần đệ quy. Nếu chỉ cần một breadcrumb, truy vấn đi lên từ nút đích thường tránh đọc các nhánh khác.

### 12.3. Tránh nối path bằng thao tác nặng khi không cần

Không phải mọi truy vấn hậu duệ đều cần `path_names`, `path_ids` và chuỗi hiển thị. Nếu chỉ cần danh sách ID để lọc sản phẩm, có thể dùng CTE với `category_id`, `parent_id` và một cơ chế kiểm soát chu trình phù hợp. Nếu cần hiển thị breadcrumb, hãy tạo đường dẫn tên ở đúng tầng hệ thống đang cần, không nhất thiết lưu trùng một chuỗi dài trên mọi bản ghi vĩnh viễn.

Ở những cây rất sâu, việc tích lũy mảng/chuỗi đường dẫn ở từng bước có chi phí. Khi yêu cầu phát hiện chu trình, cần cân bằng giữa an toàn và hiệu năng, dựa trên bảo đảm dữ liệu và cơ chế DBMS.

### 12.4. Kiểm tra kế hoạch thực thi

Trên PostgreSQL:

```sql
EXPLAIN
WITH RECURSIVE subtree AS (
    SELECT category_id, parent_id
    FROM categories
    WHERE category_id = 2
    UNION ALL
    SELECT c.category_id, c.parent_id
    FROM categories AS c
    JOIN subtree AS s
        ON c.parent_id = s.category_id
)
SELECT COUNT(*)
FROM subtree;
```

`EXPLAIN` cho biết DBMS dự định thực hiện truy vấn thế nào. `EXPLAIN ANALYZE` còn thực thi và đo thực tế; dùng thận trọng trên các lệnh thay đổi dữ liệu. Với truy vấn đệ quy, chi phí phụ thuộc số nút ở nhánh, độ sâu, fan-out (số con mỗi nút), chỉ mục và điều kiện dừng.

### 12.5. Giới hạn độ sâu không thay thế bảo vệ dữ liệu

Một số DBMS có giới hạn số vòng đệ quy mặc định. Ví dụ SQL Server thường giới hạn 100 cấp theo cấu hình `MAXRECURSION` nếu không ghi rõ, còn MySQL có giới hạn dựa trên `cte_max_recursion_depth`. Khi truy vấn vượt giới hạn, DBMS có thể báo lỗi.

Tăng giới hạn có thể cần thiết cho cây sâu hợp lệ, nhưng **không nên tăng vô hạn để che một chu trình**. Phải tìm nguyên nhân dữ liệu bất thường và áp dụng cách kiểm soát đường đi/chu trình phù hợp.

## 13. Mô hình thay thế: materialized path và closure table

Adjacency list không phải mô hình duy nhất cho dữ liệu phân cấp.

| Mô hình | Ý tưởng | Thuận lợi | Điểm cần lưu ý |
|---|---|---|---|
| **Adjacency list** | Mỗi nút lưu `parent_id` | Đơn giản; đổi cha trực tiếp dễ mô tả | Cần đệ quy để lấy mọi tổ tiên/hậu duệ |
| **Materialized path** | Lưu đường từ gốc tới nút, ví dụ `/1/2/4/6/12/` | Tìm nhánh theo đường dẫn có thể thuận tiện | Đổi cha có thể phải cập nhật đường dẫn của mọi hậu duệ |
| **Closure table** | Lưu cặp `(ancestor_id, descendant_id, distance)` | Truy vấn tổ tiên/hậu duệ bằng JOIN đơn giản | Nhiều dòng phụ trợ; thêm/di chuyển cây phải cập nhật quan hệ bao đóng |
| **Nested sets** | Lưu khoảng `left_bound/right_bound` theo thứ tự duyệt | Một số truy vấn cây con bằng điều kiện khoảng | Thay đổi cấu trúc có thể phải đánh lại nhiều giá trị |

Với ứng dụng nhỏ đến vừa, bắt đầu bằng adjacency list thường dễ quản lý. Nếu truy vấn toàn cây liên tục và cấu trúc ít thay đổi, có thể cân nhắc lưu đường dẫn hoặc closure table như dữ liệu dẫn xuất.

### 13.1. Cẩn thận khi tìm bằng tiền tố đường dẫn

Nếu lưu chuỗi ID kiểu `/1/2/`, một truy vấn tìm hậu duệ bằng:

```sql
WHERE path_text LIKE '/1/2/%'
```

chỉ có thể đúng khi mỗi ID được phân tách **rõ ràng bằng delimiter**. Nếu lưu đường như `1/2` không có ranh giới đầy đủ, so sánh tiền tố có thể nhầm `2` với `20`. Đồng thời phải cân nhắc escaping, ký tự đặc biệt và giới hạn độ dài.

PostgreSQL có extension `ltree` chuyên cho đường dẫn phân cấp, nhưng nó là **tính năng bổ sung** với cú pháp, phép toán và chỉ mục riêng; không nên giả định có sẵn ở mọi database hoặc mọi DBMS. Bài học ưu tiên mô hình SQL bảng cha–con và CTE đệ quy để hiểu nguyên lý chung.

### 13.2. Closure table: cặp tổ tiên–hậu duệ có khoảng cách

Một closure table có thể có cấu trúc:

```sql
CREATE TABLE category_closure (
    ancestor_id INTEGER NOT NULL REFERENCES categories(category_id),
    descendant_id INTEGER NOT NULL REFERENCES categories(category_id),
    distance INTEGER NOT NULL CHECK (distance >= 0),
    PRIMARY KEY (ancestor_id, descendant_id)
);
```

Theo quy ước phổ biến, mỗi nút có một hàng tự thân với `distance = 0`. Ví dụ:

| ancestor_id | descendant_id | distance |
|---:|---:|---:|
| 2 | 2 | 0 |
| 2 | 4 | 1 |
| 2 | 6 | 2 |
| 2 | 12 | 3 |
| 1 | 12 | 4 |

Khi bảng closure được cập nhật chính xác, truy vấn toàn bộ hậu duệ của 2 rất ngắn:

```sql
SELECT c.category_id, c.category_name, cc.distance
FROM category_closure AS cc
JOIN categories AS c ON c.category_id = cc.descendant_id
WHERE cc.ancestor_id = 2
  AND cc.distance > 0
ORDER BY cc.distance, c.category_id;
```

Nhược điểm là phải duy trì bảng closure mỗi khi thêm/xóa/di chuyển một nút. Việc tạo và duy trì closure table nằm ngoài phạm vi thực hành chính; nó được giới thiệu để thấy **đường dẫn và quan hệ tổ tiên–hậu duệ có thể được tính lúc truy vấn hoặc lưu dẫn xuất**.

## 14. Khác biệt phương ngữ SQL

Không phải DBMS nào cũng dùng cùng cú pháp `WITH RECURSIVE`, mảng hay hàm đường dẫn.

| DBMS | Khai báo đệ quy thông dụng | Tạo đường dẫn | Lưu ý |
|---|---|---|---|
| **PostgreSQL** | `WITH RECURSIVE` | Mảng `ARRAY`, `ARRAY_APPEND`, `ARRAY_TO_STRING`, nối chuỗi | Có `SEARCH`/`CYCLE` ở phiên bản phù hợp |
| **MySQL 8.0+** | `WITH RECURSIVE` | `CONCAT`, `CAST` kiểu chuỗi đủ dài; có thể dùng JSON | Có giới hạn vòng lặp mặc định; kiểu cột CTE thường suy ra từ phần neo |
| **SQL Server** | `WITH` (tự nhận diện CTE đệ quy) | `CAST`/`CONVERT` sang `VARCHAR(MAX)` hoặc `NVARCHAR(MAX)`, nối chuỗi | `MAXRECURSION`; kiểu dữ liệu phần neo và phần đệ quy phải tương thích |
| **SQLite** | `WITH RECURSIVE` | `||` nối chuỗi, `printf` định dạng, thường dùng path dạng chuỗi | Không có mảng SQL như PostgreSQL; cần tự phòng vòng lặp |
| **Oracle Database** | Recursive subquery factoring bằng `WITH`; hoặc `CONNECT BY` | `SYS_CONNECT_BY_PATH`, `LISTAGG`, nối chuỗi | Có `START WITH ... CONNECT BY PRIOR` và quy tắc riêng của `CYCLE` |

### 14.1. MySQL 8.0+: CTE đệ quy nối đường dẫn tên

Ví dụ lấy cây con từ nút 2:

```sql
-- MySQL 8.0+
WITH RECURSIVE subtree AS (
    SELECT
        category_id,
        parent_id,
        category_name,
        0 AS depth,
        CAST(category_name AS CHAR(1000)) AS path_text
    FROM categories
    WHERE category_id = 2

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        s.depth + 1,
        CONCAT(s.path_text, ' / ', c.category_name)
    FROM categories AS c
    JOIN subtree AS s ON c.parent_id = s.category_id
)
SELECT category_id, depth, path_text
FROM subtree
ORDER BY depth, category_id;
```

**Vì sao `CAST(... AS CHAR(1000))` ở phần neo?** Ở MySQL, kiểu/độ dài cột đầu ra của CTE đệ quy thường được suy ra từ **phần neo**. Nếu phần neo chỉ chứa tên ngắn “Điện tử”, nối thêm nhiều tên có thể vượt độ dài đã suy ra và gây lỗi/truncation tùy chế độ. Việc ép kiểu sang độ dài đủ lớn giúp CTE nhận một cột đường dẫn phù hợp hơn.

Ví dụ này giả định dữ liệu không có chu trình. Khi xử lý dữ liệu chưa được bảo đảm, cần thêm cơ chế đánh dấu ID đã đi qua, có thể sử dụng JSON hoặc chuỗi ID có delimiter rõ ràng, và kiểm soát giới hạn đệ quy. Không dùng mỗi `LIMIT` cuối truy vấn để thay thế kiểm tra chu trình.

### 14.2. SQL Server: CTE đệ quy không viết từ khóa RECURSIVE

Ví dụ trả về ID và độ sâu:

```sql
-- SQL Server
;WITH subtree AS (
    SELECT category_id, parent_id, 0 AS depth
    FROM dbo.categories
    WHERE category_id = 2

    UNION ALL

    SELECT c.category_id, c.parent_id, s.depth + 1
    FROM dbo.categories AS c
    JOIN subtree AS s ON c.parent_id = s.category_id
)
SELECT category_id, depth
FROM subtree
ORDER BY depth, category_id
OPTION (MAXRECURSION 1000);
```

Điểm khác:

- SQL Server dùng `WITH` cho CTE đệ quy; không thêm từ khóa `RECURSIVE` trong cú pháp thông thường.
- Dấu `;` trước `WITH` kết thúc câu lệnh trước đó trong một batch nếu cần.
- `OPTION (MAXRECURSION 1000)` đặt giới hạn đệ quy cho câu truy vấn; mặc định thông dụng là 100 nếu không chỉ định. `MAXRECURSION 0` có nghĩa không dùng giới hạn này nhưng **không an toàn với dữ liệu có chu trình**.
- Các cột trong phần neo và phần đệ quy cần có kiểu dữ liệu tương thích chặt chẽ. Nếu tích lũy path dạng chuỗi, thường phải ép kiểu phần neo sang `NVARCHAR(MAX)`/`VARCHAR(MAX)` phù hợp; nếu không, biểu thức nối dài hơn có thể gây lỗi kiểu.

Để truy vấn **tổ tiên**, chỉ cần đổi điều kiện nối từ `c.parent_id = s.category_id` sang `parent.category_id = s.parent_id` và bắt đầu từ ID nút đích.

### 14.3. SQLite: WITH RECURSIVE và toán tử nối chuỗi

SQLite không có kiểu mảng SQL như `INTEGER[]` của PostgreSQL, nhưng có thể dùng chuỗi đường dẫn:

```sql
-- SQLite
WITH RECURSIVE subtree AS (
    SELECT
        category_id,
        parent_id,
        category_name,
        0 AS depth,
        '/' || category_id || '/' AS path_ids
    FROM categories
    WHERE category_id = 2

    UNION ALL

    SELECT
        c.category_id,
        c.parent_id,
        c.category_name,
        s.depth + 1,
        s.path_ids || c.category_id || '/'
    FROM categories AS c
    JOIN subtree AS s ON c.parent_id = s.category_id
    WHERE instr(s.path_ids, '/' || c.category_id || '/') = 0
)
SELECT category_id, depth, path_ids
FROM subtree
ORDER BY depth, category_id;
```

Chuỗi `/2/4/6/12/` có delimiter ở hai phía của từng ID. Điều kiện `instr(s.path_ids, '/' || c.category_id || '/') = 0` giúp kiểm tra ID con **chưa xuất hiện nguyên vẹn** trong đường dẫn; nếu chỉ tìm chuỗi `'2'` thì có thể nhầm ID 2 với ID 12 hoặc 20.

Đây là cách minh họa trên ID nguyên dương như bảng mẫu. Với giá trị định danh phức tạp hoặc dữ liệu rất sâu, cần cân nhắc cơ chế path và hiệu năng thích hợp. `ORDER BY depth, category_id` ở đây sắp theo **tầng**, không theo nhánh depth-first.

### 14.4. Oracle: START WITH ... CONNECT BY PRIOR

Oracle Database có cú pháp phân cấp truyền thống:

```sql
-- Oracle Database
SELECT
    category_id,
    parent_id,
    category_name,
    LEVEL - 1 AS depth,
    SYS_CONNECT_BY_PATH(category_name, ' / ') AS path_text
FROM categories
START WITH category_id = 2
CONNECT BY PRIOR category_id = parent_id
ORDER SIBLINGS BY category_id;
```

Ý nghĩa:

- `START WITH category_id = 2`: nút bắt đầu (tương tự phần neo).
- `CONNECT BY PRIOR category_id = parent_id`: đi từ cha hiện tại tới nút con.
- `LEVEL`: cấp trong câu truy vấn phân cấp của Oracle, nút bắt đầu có `LEVEL = 1`, nên `LEVEL - 1` tương đương depth bắt đầu từ 0.
- `SYS_CONNECT_BY_PATH` tạo chuỗi đường dẫn từ nút bắt đầu tới nút hiện tại; ví dụ có dấu phân cách ` / ` ở đầu chuỗi.
- `ORDER SIBLINGS BY` sắp thứ tự các nút cùng cha mà vẫn giữ cấu trúc nhánh.

Nếu muốn đi lên tổ tiên, đổi hướng `CONNECT BY PRIOR` phù hợp: từ nút hiện tại dùng `parent_id` để tìm nút có `category_id` trùng parent. Oracle còn hỗ trợ recursive subquery factoring với `WITH` và các tính năng `SEARCH`/`CYCLE` theo cú pháp riêng của Oracle. Không áp dụng nguyên cú pháp mảng PostgreSQL vào Oracle.

### 14.5. Cùng ý tưởng, cú pháp và giới hạn khác nhau

Khi chuyển một truy vấn đệ quy sang hệ khác, phải kiểm tra:

1. **Cách khai báo CTE đệ quy**: `WITH RECURSIVE` hay `WITH`.
2. **Kiểu dữ liệu của cột path**: mảng, chuỗi, JSON hay kiểu đường dẫn chuyên biệt.
3. **Cách nối chuỗi**: `||`, `CONCAT`, toán tử `+` hoặc hàm riêng.
4. **Độ dài tối đa** của chuỗi/path và quy tắc suy ra kiểu ở phần neo.
5. **Giới hạn số cấp đệ quy**, cú pháp `SEARCH`/`CYCLE` hoặc giải pháp chống vòng lặp.
6. **Hỗ trợ ORDER BY và cách tạo thứ tự duyệt**: thứ tự thực thi đệ quy không tự là thứ tự hiển thị.

Không giả định rằng chỉ cần thay `WITH RECURSIVE` thành `WITH` là đủ để port một truy vấn dài sang DBMS khác.

## 15. Những lỗi thường gặp

### Lỗi 1 — Dùng JOIN một cấp rồi tưởng đã lấy toàn bộ hậu duệ

`WHERE parent_id = 2` chỉ lấy **con trực tiếp** `4, 5, 13`; nó không tìm Laptop gaming hoặc Sạc ở nhiều cấp sâu hơn. Muốn mọi cấp, dùng CTE đệ quy hoặc mô hình lưu đường dẫn thích hợp.

### Lỗi 2 — Nối sai chiều khi đi lên hoặc đi xuống

Đi xuống: `child.parent_id = current.category_id`. Đi lên: `parent.category_id = current.parent_id`. Đổi nhầm chiều khiến kết quả không còn là tập tổ tiên/hậu duệ mong muốn.

### Lỗi 3 — Không làm rõ có tính cả nút bắt đầu không

CTE neo tại `category_id = 2` thường trả chính nút 2 với `depth = 0`. Nếu yêu cầu là **chỉ hậu duệ**, phải loại `depth = 0`. Nếu yêu cầu là **cây con**, giữ nút gốc cây con.

### Lỗi 4 — Dùng tên thay ID để xác định nút

Tên có thể trùng hoặc thay đổi. Nên dùng `category_id` làm khóa và kiểm tra chu trình, còn tên chỉ phục vụ hiển thị path.

### Lỗi 5 — Nghĩ UNION thay UNION ALL luôn chặn được vòng lặp

Nếu bước đệ quy sinh thêm `depth` hoặc `path` khác mỗi lần, các hàng quay lại cùng ID vẫn **khác nhau trên toàn bộ danh sách cột**, nên `UNION` không bảo đảm dừng. Phải kiểm tra nút đã đi qua hoặc dùng `CYCLE`/quy tắc dữ liệu phù hợp.

### Lỗi 6 — Dựa vào thứ tự ngẫu nhiên của CTE đệ quy

Không có `ORDER BY` cuối, thứ tự đầu ra không được bảo đảm. `ORDER BY depth` chỉ cho thứ tự theo tầng; `ORDER BY path_ids` cho thứ tự theo nhánh trên PostgreSQL khi dùng mảng đường dẫn.

### Lỗi 7 — Nhầm độ sâu từ gốc với số bước từ nút bất kỳ

Nút 12 có độ sâu **4** tính từ gốc 1, nhưng là hậu duệ cách nút 2 **3** cạnh. `depth` phụ thuộc **điểm neo** của truy vấn; khi hiển thị API, cần ghi rõ gốc tham chiếu.

### Lỗi 8 — Nối đường dẫn bằng chuỗi ID mà không có delimiter

Tìm ID 2 trong `'1/12/...'` bằng tìm chuỗi `'2'` có thể cho kết quả sai. Nên dùng mảng số nguyên hoặc chuỗi với delimiters, ví dụ `/1/2/4/`, để không nhầm `2` với `12` hoặc `20`.

### Lỗi 9 — Chỉ kiểm tra parent_id <> category_id rồi nghĩ cây không thể có vòng

Điều kiện đó ngăn **chu trình một nút**, nhưng không ngăn vòng dài hơn. Cần kiểm tra khi di chuyển nhánh, nhất là trong hệ thống có nhiều giao dịch đồng thời.

### Lỗi 10 — Tưởng truy vấn từ gốc kiểm tra được mọi nút lỗi

Những chu trình hoặc nhánh bất thường không kết nối với bất kỳ gốc nào có thể **không xuất hiện** trong truy vấn bắt đầu từ gốc. Khi kiểm tra chất lượng dữ liệu phân cấp, cần có phương án kiểm tra toàn bộ bảng, không chỉ tập nút reachable.

### Lỗi 11 — Cộng lặp số liệu đã tổng hợp ở các nút cha

Nếu cột `total_revenue` ở cha đã bao gồm doanh thu con, việc `SUM` mọi nút trong cây con sẽ **đếm trùng**. Hãy biết cột nào là **giá trị trực tiếp** của nút và cột nào đã là **giá trị lũy kế**.

### Lỗi 12 — Không tính tới ảnh hưởng của đổi cha

Chuyển một nút sang cha khác thay đổi đường dẫn, độ sâu và tổ tiên của **toàn bộ hậu duệ**. Nếu hệ thống lưu materialized path hoặc closure table, cần cập nhật dữ liệu dẫn xuất nhất quán.

### Lỗi 13 — Dùng LIMIT để “chữa” truy vấn đệ quy vô hạn

`LIMIT` ở truy vấn ngoài không phải cơ chế bảo vệ đầy đủ; DBMS có thể vẫn cần duyệt nhiều hàng để sắp xếp hoặc tổng hợp. Đừng coi một câu truy vấn trả được vài hàng là bằng chứng dữ liệu không có chu trình.

### Lỗi 14 — Sao chép path ARRAY từ PostgreSQL sang SQL Server hoặc SQLite

Kiểu mảng `INTEGER[]` và `ARRAY_APPEND` của PostgreSQL không có cú pháp tương đương nguyên văn ở mọi DBMS. Cần dùng chuỗi/JSON/kiểu khác và chú ý kích thước, quy tắc escape và hiệu năng.

## 16. Bài tập thực hành

Sử dụng bảng `categories` gồm 17 nút ở mục 2. Hãy dự đoán kết quả trước khi chạy truy vấn.

### Bài 1 — Con trực tiếp và hậu duệ

Viết hai truy vấn:

1. Con trực tiếp của `Điện tử [2]`.
2. Mọi hậu duệ của `Điện tử [2]`, không bao gồm 2.

**Đáp án:** con trực tiếp là **4, 5, 13**; hậu duệ là **4, 5, 6, 7, 10, 11, 12, 13, 14** (9 nút, thứ tự hiển thị tùy `ORDER BY`).

### Bài 2 — Tạo path cho Laptop gaming

Dùng CTE bắt đầu ở gốc 1 rồi tích lũy `path_ids` và `path_names` để lấy nút 12.

**Đáp án:** `path_ids = {1,2,4,6,12}`, đường tên **Cửa hàng / Điện tử / Máy tính / Laptop / Laptop gaming**, depth từ gốc là **4**.

### Bài 3 — Truy vấn tổ tiên

Viết CTE đi lên từ nút 12, trả tổ tiên theo thứ tự **gốc trước** và hiển thị số bước `hops`.

**Đáp án:** `1` (hops 4), `2` (3), `4` (2), `6` (1). Nếu thêm cả nút 12 thì nó có hops 0.

### Bài 4 — Tìm đường từ Sạc tới gốc

Dùng CTE đi lên từ `Sạc [14]`, sau đó `STRING_AGG(category_name, ' / ' ORDER BY hops DESC)` để tạo breadcrumb.

**Đáp án:** **Cửa hàng / Điện tử / Phụ kiện / Sạc**. Đường dẫn ID từ gốc là **`1 / 2 / 13 / 14`**.

### Bài 5 — Giới hạn hai cấp

Từ nút 2, chỉ lấy cây con ở `relative_depth <= 2` bằng điều kiện trong phần đệ quy.

**Đáp án:** 9 nút gồm `2` (0), `4, 5, 13` (1) và `6, 7, 10, 11, 14` (2). `Laptop gaming [12]` ở cấp 3 so với nút 2 bị loại.

### Bài 6 — Nút lá của toàn cây

Viết:

```sql
SELECT c.category_id, c.category_name
FROM categories AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM categories AS child
    WHERE child.parent_id = c.category_id
)
ORDER BY c.category_id;
```

**Đáp án:** các lá là **7, 8, 9, 10, 11, 12, 14, 16, 17**. Tại sao một nút có tên “Laptop” không nhất thiết là lá? Vì nó còn có nút con 12.

### Bài 7 — Đếm hậu duệ của một nhánh

Viết CTE duyệt từ `category_id = 3` (Sách) và đếm các hàng `depth > 0`.

**Đáp án:** nhánh Sách có hậu duệ **8, 9, 15, 16, 17**, tổng **5** hậu duệ, hoặc **6** nút nếu tính cả 3.

### Bài 8 — Tổ tiên chung gần nhất

Tìm tổ tiên chung gần nhất của:

1. `Laptop gaming [12]` và `Sạc [14]`.
2. `Laptop gaming [12]` và `SQL [16]`.

**Đáp án:** cặp 1 có tổ tiên chung gần nhất **2 — Điện tử**; cặp 2 có tổ tiên chung gần nhất **1 — Cửa hàng**.

### Bài 9 — Tổng doanh thu cây con

Dùng `category_sales` ở mục 10. Tính tổng doanh thu của nhánh **Sách [3]**.

**Đáp án:** **340.000**, gồm Tiểu thuyết 120.000, Kỹ năng 60.000, SQL 70.000 và Java 90.000. Phân biệt doanh thu trực tiếp ở danh mục với doanh thu đã cộng toàn nhánh.

### Bài 10 — Di chuyển nhánh có hợp lệ?

Một người định:

```sql
-- Đừng chạy lệnh sau khi chưa kiểm tra:
-- UPDATE categories SET parent_id = 12 WHERE category_id = 2;
```

Hãy giải thích vì sao thay đổi này tạo chu trình. **Đáp án:** 12 đã là hậu duệ của 2 theo đường `2 → 4 → 6 → 12`; gắn cha của 2 thành 12 tạo vòng `2 → 4 → 6 → 12 → 2`. Trước khi đổi cha, cần kiểm tra cha mới **không phải chính nút hoặc bất kỳ hậu duệ nào** của nút cần chuyển.

### Bài 11 — Chuyển cú pháp sang SQL Server

Chuyển CTE hậu duệ của nút 2 từ PostgreSQL sang SQL Server bằng `;WITH subtree AS (...)` và `OPTION (MAXRECURSION 1000)`.

**Đáp án định hướng:** giữ phần neo `WHERE category_id = 2` và bước nối `c.parent_id = s.category_id`, nhưng bỏ từ khóa `RECURSIVE`; dùng `MAXRECURSION` phù hợp. Nếu cần path, chọn kiểu chuỗi đủ lớn và ép kiểu tương thích trong phần neo.

### Bài 12 — Phân biệt breadcrumb và cây con

Ứng dụng có hai màn hình:

- Màn A: người dùng mở chi tiết **SQL [16]**, chỉ cần đường dẫn từ gốc.
- Màn B: người dùng mở **Sách [3]**, cần toàn bộ các danh mục bên dưới để dựng menu.

Nên neo CTE ở đâu và duyệt theo hướng nào?

**Đáp án:** màn A thường neo ở **16** và đi **lên cha** để tạo breadcrumb, giúp tránh duyệt các nhánh không liên quan. Màn B neo ở **3** và đi **xuống con** để lấy cây con, có thể loại hàng depth 0 nếu menu chỉ cần hậu duệ.

## 17. Bảng ghi nhớ nhanh

| Yêu cầu | Điểm neo | Điều kiện đệ quy | Gợi ý đầu ra |
|---|---|---|---|
| Toàn bộ cây | Nút `parent_id IS NULL` | `child.parent_id = current.category_id` | ID, depth, full_path |
| Một cây con | Nút được chọn | Đi xuống con | Bao gồm nút neo, depth 0 |
| Chỉ hậu duệ | Nút được chọn | Đi xuống con | Lọc `depth > 0` |
| Chỉ con trực tiếp | Không cần đệ quy | `WHERE parent_id = target_id` | Một cấp |
| Tổ tiên | Nút được chọn | `parent.category_id = current.parent_id` | Lọc `hops > 0` |
| Breadcrumb | Nút đích | Đi lên cha | Ghép tên theo hops giảm dần |
| Nút lá | Danh sách nút cần xét | `NOT EXISTS` con trực tiếp | Nút không có con |
| Tổ tiên chung gần nhất | Hai nút đích | Đi lên từ cả hai | Lấy nút chung gần nhất |
| Tổng số liệu cây con | Nút gốc nhánh | Đi xuống + JOIN số liệu trực tiếp | `SUM` trên các nút được duyệt |
| Duyệt an toàn với chu trình | Nút xuất phát | Kiểm tra ID chưa có trong path | `path_ids` hoặc `CYCLE` |
| Hiển thị nhánh theo thứ tự | Gốc/cây con | Tích lũy sort path | `ORDER BY` cuối truy vấn |

## Kết luận

**Truy vấn đệ quy** cho phép xử lý dữ liệu phân cấp có số tầng không cố định bằng một câu SQL thay vì phải nối bảng thủ công cho từng cấp. Trong mô hình **adjacency list**, mỗi nút lưu `parent_id`; CTE đệ quy bắt đầu từ **phần neo**, sau đó tiếp tục **đi xuống các nút con** hoặc **đi lên các nút cha** tùy câu hỏi:

- Đi **xuống** để tìm cây con và hậu duệ, đếm nút, tìm lá hoặc tổng hợp số liệu cả nhánh.
- Đi **lên** để tìm tổ tiên và tạo breadcrumb từ gốc tới nút hiện tại.
- Tích lũy **`path_ids`** để nhận diện các bước đã đi qua, hỗ trợ thứ tự theo nhánh và phòng chu trình; dùng **`path_names`** để hiển thị đường dẫn thân thiện.
- Phân biệt **độ sâu từ gốc toàn cây** với **độ sâu tương đối của cây con**, và luôn nói rõ có bao gồm nút xuất phát trong kết quả không.
- Dùng **`ORDER BY`** để bảo đảm thứ tự đầu ra, **chỉ mục `parent_id`** để hỗ trợ tìm con và cơ chế phát hiện chu trình để tránh dữ liệu lỗi.

Khi chuyển sang DBMS khác, hãy giữ nguyên **ý nghĩa phần neo, hướng nối, điều kiện dừng và nội dung đường dẫn** nhưng điều chỉnh cú pháp `WITH RECURSIVE`, kiểu path và cách quản lý giới hạn độ sâu phù hợp phương ngữ. Chỉ cần nắm chắc hai câu hỏi **“tôi đang đi lên hay đi xuống?”** và **“mỗi bước đã đi qua những ID nào?”**, bạn có thể xây dựng nhiều truy vấn tổ tiên, hậu duệ và đường dẫn phân cấp một cách chính xác, dễ đọc và có thể mở rộng.
