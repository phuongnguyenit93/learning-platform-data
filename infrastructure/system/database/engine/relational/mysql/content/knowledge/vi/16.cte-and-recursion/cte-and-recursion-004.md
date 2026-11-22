# WITH RECURSIVE: phần khởi tạo và phần đệ quy

CTE đệ quy (recursive common table expression) cho phép một truy vấn tham chiếu lại chính kết quả trung gian của nó để xử lý dữ liệu có cấu trúc lặp hoặc quan hệ phân cấp. Các bài toán thường gặp gồm sinh dãy số, tạo lịch ngày, duyệt cây phòng ban, lần theo danh mục cha-con, tìm cấp quản lý và khám phá các nút trong đồ thị.

Trong MySQL, CTE đệ quy được khai báo bằng `WITH RECURSIVE` và gồm hai phần cốt lõi: phần khởi tạo (*anchor member*) tạo ra các hàng ban đầu; phần đệ quy (*recursive member*) dùng các hàng đã có để tìm hoặc sinh ra hàng tiếp theo. Hai phần được nối bằng `UNION ALL` hoặc `UNION DISTINCT`. Quá trình lặp kết thúc khi phần đệ quy không tạo thêm hàng mới hoặc chạm giới hạn đệ quy.

Bài học này thuộc module `DATABASE_MYSQL`, nơi bạn thực hành thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi và tối ưu truy vấn. Mục tiêu là hiểu rõ vai trò của anchor và recursive member, thiết kế điều kiện dừng an toàn và sử dụng CTE đệ quy để truy vấn dữ liệu phân cấp mà không phải viết số lượng câu JOIN cố định.

Sau bài học, bạn có thể:

- Nhận diện phần khởi tạo và phần đệ quy trong một `WITH RECURSIVE`.
- Giải thích cách các vòng lặp tạo ra kết quả và điều kiện kết thúc.
- Chọn `UNION ALL` hoặc `UNION DISTINCT` theo ngữ nghĩa dữ liệu.
- Khai báo tên cột và kiểm soát kiểu dữ liệu của kết quả đệ quy bằng `CAST()`.
- Sinh dãy số và dãy ngày trong một khoảng xác định.
- Duyệt cây cha-con bằng adjacency list.
- Theo dõi đường đi và ngăn lặp vô hạn khi dữ liệu có chu trình.
- Kiểm soát `cte_max_recursion_depth` và đánh giá kế hoạch thực thi.

## 1. Cấu trúc của WITH RECURSIVE

Cú pháp tổng quát:

```sql
WITH RECURSIVE cte_name (column_1, column_2, ...) AS (
    -- Anchor member: tạo hàng ban đầu
    SELECT ...

    UNION ALL

    -- Recursive member: tạo hàng tiếp theo từ kết quả CTE
    SELECT ...
    FROM cte_name
    JOIN ...
    WHERE stop_condition
)
SELECT ...
FROM cte_name;
```

Một CTE đệ quy có ba thành phần:

1. **Tên CTE và danh sách cột:** `cte_name` là tên tập kết quả trung gian. Danh sách cột trong ngoặc là tùy chọn, nhưng nên khai báo tường minh để dễ đọc và tránh nhầm thứ tự cột.
2. **Anchor member:** truy vấn không tham chiếu chính CTE. Nó xác định điểm bắt đầu, ví dụ số 1, ngày đầu tiên hoặc các nút gốc có `parent_id IS NULL`.
3. **Recursive member:** truy vấn tham chiếu CTE để tạo thế hệ hàng tiếp theo. Nó phải có logic tiến triển và điều kiện dừng phù hợp.

Anchor và recursive member phải trả cùng số cột theo cùng thứ tự. Kiểu dữ liệu kết quả của mỗi cột được xác định từ phần không đệ quy (anchor); phần đệ quy phải tạo ra giá trị tương thích với kiểu đó.

## 2. Cách quá trình đệ quy hoạt động

Có thể hình dung CTE đệ quy theo các vòng:

1. MySQL chạy anchor member để tạo tập hàng ban đầu.
2. Recursive member chạy dựa trên các hàng của vòng hiện tại để tạo tập hàng kế tiếp.
3. Các hàng mới được thêm vào kết quả CTE.
4. MySQL tiếp tục lặp với tập hàng mới.
5. Khi recursive member không tạo thêm hàng, quá trình dừng.

Sơ đồ khái niệm:

```text
              Anchor member
                    |
                    v
              Hàng ban đầu
                    |
                    v
             Recursive member
                    |
                    v
              Hàng thế hệ mới
                    |
                    v
          Còn hàng mới để mở rộng?
               /          \
             Có            Không
             |               |
             +---- lặp       v
                         Kết thúc
```

Đây là mô hình logic để hiểu kết quả. Optimizer và cách MySQL quản lý tập trung gian là chi tiết thực thi; không nên giả định thứ tự hàng được sinh ra cũng là thứ tự hàng cuối cùng được trả về.

### 2.1. Anchor member là điểm bắt đầu

Anchor xác định những hàng đầu tiên của truy vấn. Nó không được tham chiếu CTE đang được định nghĩa. Tùy bài toán, anchor có thể là:

- Một giá trị cố định như `SELECT 1`.
- Một ngày bắt đầu như `SELECT CAST('2026-11-19' AS DATE)`.
- Một hoặc nhiều nút gốc trong bảng cây.
- Một hàng cụ thể được truyền vào bằng điều kiện lọc.

Nếu anchor không trả hàng nào, CTE không có dữ liệu để mở rộng và kết quả cuối cùng cũng rỗng.

### 2.2. Recursive member mở rộng kết quả

Recursive member tham chiếu tên CTE trong `FROM`, sau đó kết hợp hàng hiện tại với dữ liệu nguồn để tìm hàng kế tiếp. Với cây phòng ban, hàng hiện tại là một phòng ban; recursive member tìm các phòng ban có `parent_id` bằng ID của phòng ban hiện tại.

Recursive member cần có điều kiện giới hạn miền mở rộng. Nếu điều kiện không bao giờ dừng và dữ liệu có thể lặp, truy vấn có thể chạy đến giới hạn `cte_max_recursion_depth` rồi báo lỗi.

### 2.3. Điều kiện dừng là một phần của thiết kế

Một truy vấn an toàn phải trả lời được: “Khi nào không cần sinh thêm hàng?”

Ví dụ:

- Dãy số: dừng khi `n` đạt giá trị tối đa.
- Dãy ngày: dừng khi ngày hiện tại đạt ngày cuối.
- Cây: dừng khi không còn nút con.
- Duyệt đồ thị: dừng khi không còn nút mới và không đi lại nút đã có trong đường đi.

Không dựa duy nhất vào giới hạn recursion của máy chủ để thay cho điều kiện dừng nghiệp vụ.

## 3. Ví dụ đầu tiên: sinh dãy số

Sinh các số từ 1 đến 10:

```sql
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
```

Kết quả:

| n |
| ---: |
| 1 |
| 2 |
| 3 |
| 4 |
| 5 |
| 6 |
| 7 |
| 8 |
| 9 |
| 10 |

Phân tích:

- Anchor `SELECT 1` tạo hàng đầu tiên có `n = 1`.
- Recursive member đọc hàng `n` hiện tại và tạo `n + 1`.
- Điều kiện `WHERE n < 10` chỉ cho phép sinh hàng tiếp theo khi số hiện tại nhỏ hơn 10.
- Khi `n = 10`, recursive member không trả thêm hàng, nên truy vấn kết thúc.
- `ORDER BY n` ở truy vấn ngoài cùng bảo đảm thứ tự kết quả.

Nếu bỏ `WHERE n < 10`, truy vấn không có điều kiện dừng theo dữ liệu và sẽ tiếp tục cho đến khi chạm giới hạn recursion hoặc giới hạn tài nguyên khác.

### 3.1. Thay đổi giá trị bắt đầu và kết thúc

Có thể dùng tham số ứng dụng hoặc biến session để đặt giới hạn. Ví dụ với biến session:

```sql
SET @start_value = 5;
SET @end_value = 12;

WITH RECURSIVE numbers (n) AS (
    SELECT @start_value

    UNION ALL

    SELECT n + 1
    FROM numbers
    WHERE n < @end_value
)
SELECT n
FROM numbers
ORDER BY n;
```

Khi viết trong ứng dụng, nên truyền giá trị bằng parameter của `PreparedStatement` theo cú pháp phù hợp; không ghép trực tiếp dữ liệu người dùng vào SQL. Các biến session ở đây chỉ nhằm minh họa cách thay đổi đầu vào trong MySQL client.

### 3.2. Dãy giảm dần

Anchor và điều kiện dừng có thể tạo dãy giảm:

```sql
WITH RECURSIVE countdown (n) AS (
    SELECT 5

    UNION ALL

    SELECT n - 1
    FROM countdown
    WHERE n > 1
)
SELECT n
FROM countdown
ORDER BY n DESC;
```

Kết quả là 5, 4, 3, 2, 1. Hãy bảo đảm phép biến đổi tiến gần điều kiện dừng; nếu viết nhầm `n < 1`, dãy có thể không kết thúc như dự kiến.

## 4. Sinh dãy ngày bằng CTE đệ quy

Một ứng dụng thường cần tạo các ngày liên tục để lập báo cáo, kể cả ngày không có giao dịch. CTE đệ quy có thể sinh dãy ngày mà không cần bảng lịch riêng.

```sql
WITH RECURSIVE calendar_days (calendar_date) AS (
    SELECT CAST('2026-11-19' AS DATE)

    UNION ALL

    SELECT calendar_date + INTERVAL 1 DAY
    FROM calendar_days
    WHERE calendar_date < CAST('2026-11-25' AS DATE)
)
SELECT calendar_date
FROM calendar_days
ORDER BY calendar_date;
```

Kết quả gồm bảy ngày từ 19/11/2026 đến 25/11/2026. Anchor tạo ngày đầu tiên; recursive member cộng một ngày; điều kiện dừng so sánh với ngày cuối.

### 4.1. Kết hợp calendar với dữ liệu giao dịch

Giả sử bảng `daily_sales` có tổng tiền theo ngày. Có thể dùng calendar làm phía được bảo toàn để hiển thị ngày không có giao dịch:

```sql
WITH RECURSIVE calendar_days (calendar_date) AS (
    SELECT CAST('2026-11-19' AS DATE)

    UNION ALL

    SELECT calendar_date + INTERVAL 1 DAY
    FROM calendar_days
    WHERE calendar_date < CAST('2026-11-25' AS DATE)
)
SELECT
    c.calendar_date,
    COALESCE(SUM(s.amount), 0.00) AS daily_total
FROM calendar_days AS c
LEFT JOIN daily_sales AS s
    ON s.sale_date = c.calendar_date
GROUP BY c.calendar_date
ORDER BY c.calendar_date;
```

`LEFT JOIN` giữ tất cả ngày trong calendar. Ngày không có giao dịch có `SUM(s.amount) = NULL`, sau đó `COALESCE()` chuyển thành 0 để hiển thị. Nếu nghiệp vụ cần phân biệt “không có giao dịch” với “có giao dịch tổng bằng 0”, hãy trả thêm `COUNT(s.sale_id)`.

Với báo cáo dài hạn, nhiều người dùng hoặc nhiều truy vấn lịch, một bảng calendar vật lý có thể phù hợp hơn vì tránh phải sinh lại dãy ngày cho mỗi truy vấn và có thể chứa thêm thông tin như tuần, quý, ngày lễ. CTE là lựa chọn tiện cho khoảng nhỏ và truy vấn linh hoạt.

## 5. CTE đệ quy để duyệt cây cha-con

Một cách lưu cây phổ biến là adjacency list: mỗi hàng lưu ID của chính nó và ID của nút cha. Nút gốc có `parent_id IS NULL`.

Tạo bảng mẫu:

```sql
DROP TEMPORARY TABLE IF EXISTS org_nodes;

CREATE TEMPORARY TABLE org_nodes (
    node_id INT UNSIGNED NOT NULL,
    parent_id INT UNSIGNED NULL,
    node_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (node_id),
    KEY idx_org_nodes_parent (parent_id)
) ENGINE = InnoDB;

INSERT INTO org_nodes (node_id, parent_id, node_name) VALUES
(1, NULL, 'CEO'),
(2, 1,    'Engineering'),
(3, 1,    'Product'),
(4, 2,    'Backend'),
(5, 2,    'Data'),
(6, 3,    'Design'),
(7, 5,    'Database');
```

Cấu trúc cây:

```text
1 CEO
├── 2 Engineering
│   ├── 4 Backend
│   └── 5 Data
│       └── 7 Database
└── 3 Product
    └── 6 Design
```

### 5.1. Anchor là nút gốc, recursive member là nút con

```sql
WITH RECURSIVE org_tree (
    node_id,
    parent_id,
    node_name,
    depth
) AS (
    -- Anchor: bắt đầu từ nút gốc
    SELECT
        node_id,
        parent_id,
        node_name,
        0 AS depth
    FROM org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    -- Recursive member: tìm các nút có cha là nút hiện tại
    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        parent.depth + 1
    FROM org_nodes AS child
    JOIN org_tree AS parent
        ON child.parent_id = parent.node_id
    WHERE parent.depth < 20
)
SELECT node_id, parent_id, node_name, depth
FROM org_tree
ORDER BY depth, node_id;
```

Kết quả có bảy nút. `depth = 0` là CEO; các nút con trực tiếp có depth 1; Backend, Data và Design có depth 2; Database có depth 3. Điều kiện `parent.depth < 20` là giới hạn bảo vệ độ sâu trong ví dụ; dữ liệu cây hợp lệ cũng tự kết thúc khi không còn nút con.

Điểm quan trọng của phép join đệ quy:

```sql
ON child.parent_id = parent.node_id
```

`parent` là tập kết quả CTE của vòng hiện tại; `child` là bảng nguồn chứa các nút con. Mỗi vòng tìm các hàng mà `parent_id` trỏ tới ID vừa được mở rộng.

### 5.2. Duyệt một nhánh con thay vì toàn bộ cây

Nếu chỉ muốn lấy cây con bắt đầu từ node 2, anchor chọn node đó:

```sql
WITH RECURSIVE subtree (node_id, parent_id, node_name, depth) AS (
    SELECT node_id, parent_id, node_name, 0
    FROM org_nodes
    WHERE node_id = 2

    UNION ALL

    SELECT child.node_id, child.parent_id, child.node_name, parent.depth + 1
    FROM org_nodes AS child
    JOIN subtree AS parent
        ON child.parent_id = parent.node_id
    WHERE parent.depth < 20
)
SELECT node_id, parent_id, node_name, depth
FROM subtree
ORDER BY depth, node_id;
```

Kết quả gồm Engineering, Backend, Data và Database. Anchor có thể là một nút bất kỳ, không nhất thiết là root; recursive member vẫn mở rộng các hậu duệ của nó.

### 5.3. Đường đi từ root tới từng nút

Để hiển thị đường đi, thêm một cột path. Cần chú ý kiểu dữ liệu của anchor vì MySQL suy ra kiểu cột CTE từ phần không đệ quy. Nếu anchor chỉ tạo chuỗi ngắn, phần đệ quy nối thêm nội dung có thể vượt độ dài đã suy ra.

```sql
WITH RECURSIVE org_tree (
    node_id,
    parent_id,
    node_name,
    depth,
    id_path
) AS (
    SELECT
        node_id,
        parent_id,
        node_name,
        0,
        CAST(node_id AS CHAR(1000))
    FROM org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        parent.depth + 1,
        CONCAT(parent.id_path, ',', child.node_id)
    FROM org_nodes AS child
    JOIN org_tree AS parent
        ON child.parent_id = parent.node_id
    WHERE parent.depth < 20
)
SELECT node_id, node_name, depth, id_path
FROM org_tree
ORDER BY depth, node_id;
```

`id_path` của node Database là `1,2,5,7`. `CAST(... AS CHAR(1000))` cấp độ dài chuỗi đủ rộng cho phần đệ quy trong ví dụ. Hãy chọn giới hạn dựa trên độ sâu và độ dài ID thực tế; không coi 1000 là một giá trị đúng cho mọi hệ thống.

## 6. Kiểm soát chu trình trong dữ liệu cây/đồ thị

Một cây đúng nghĩa không có chu trình. Tuy nhiên, dữ liệu có thể bị lỗi do import, migration hoặc cập nhật sai. Ví dụ, node 2 có thể trỏ tới node 5 trong khi node 5 lại trỏ về node 2. Khi đó recursive member có thể tiếp tục đi qua các hàng đã gặp.

### 6.1. UNION DISTINCT không phải lúc nào cũng chặn được chu trình

`UNION DISTINCT` loại các hàng trùng theo toàn bộ danh sách cột CTE. Nhưng nếu CTE có `depth` hoặc `path`, cùng một `node_id` được thăm lại ở độ sâu khác hoặc với đường đi khác sẽ là một hàng khác nhau. Vì vậy, đổi `UNION ALL` thành `UNION DISTINCT` không phải giải pháp cycle detection tổng quát.

Ví dụ về ý tưởng: hàng `(node_id = 2, depth = 1)` khác hàng `(node_id = 2, depth = 3)`, nên DISTINCT không xem chúng là trùng.

### 6.2. Theo dõi các ID đã đi qua

Với ID số nguyên không chứa dấu phẩy, có thể giữ đường đi dạng chuỗi phân tách bằng dấu phẩy và dùng `FIND_IN_SET()` để tránh đi lại một ID đã có trên cùng đường đi:

```sql
WITH RECURSIVE org_tree (
    node_id,
    parent_id,
    node_name,
    depth,
    id_path
) AS (
    SELECT
        node_id,
        parent_id,
        node_name,
        0,
        CAST(node_id AS CHAR(1000))
    FROM org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        parent.depth + 1,
        CONCAT(parent.id_path, ',', child.node_id)
    FROM org_nodes AS child
    JOIN org_tree AS parent
        ON child.parent_id = parent.node_id
    WHERE parent.depth < 20
      AND FIND_IN_SET(CAST(child.node_id AS CHAR), parent.id_path) = 0
)
SELECT node_id, node_name, depth, id_path
FROM org_tree
ORDER BY depth, node_id;
```

Điều kiện `FIND_IN_SET(...) = 0` chỉ mở rộng tới một node chưa xuất hiện trong đường đi hiện tại. Cách này phù hợp với ID số nguyên đơn giản; nếu khóa là chuỗi có thể chứa dấu phân cách, phải mã hóa/escape rõ ràng hoặc dùng cấu trúc path khác.

Cycle guard theo path ngăn lặp trên cùng nhánh, nhưng một node có thể xuất hiện nhiều lần nếu đồ thị có nhiều đường khác nhau đi tới node đó. Nếu bài toán yêu cầu mỗi node chỉ xuất hiện một lần trên toàn bộ kết quả, cần thiết kế thêm quy tắc loại trùng hoặc thay đổi mô hình truy vấn; `UNION DISTINCT` chỉ đủ khi toàn bộ hàng được tạo ra giống nhau.

### 6.3. Giới hạn độ sâu vẫn cần thiết

Ngay cả khi có cycle guard, vẫn nên đặt giới hạn độ sâu hợp lý để bảo vệ truy vấn khỏi dữ liệu bất thường hoặc cây quá sâu so với nghiệp vụ. Trong ví dụ, `parent.depth < 20` cho phép tạo con đến depth 20 rồi dừng mở rộng tiếp.

Đối với đồ thị có nhiều nhánh, số đường đi có thể tăng rất nhanh dù độ sâu không lớn. Giới hạn depth không thay thế việc đánh giá số hàng có thể sinh ra và giới hạn thời gian/tài nguyên truy vấn.

## 7. UNION ALL và UNION DISTINCT trong CTE đệ quy

Hai phần anchor và recursive member được nối bằng toán tử tập hợp:

| Toán tử | Hành vi | Khi nào cân nhắc |
| --- | --- | --- |
| `UNION ALL` | Giữ mọi hàng được sinh ra, kể cả hàng trùng | Sinh dãy, duyệt cây, giữ từng đường đi hoặc cần hiệu năng tốt khi trùng là hợp lệ |
| `UNION DISTINCT` hoặc `UNION` | Loại các hàng trùng theo toàn bộ cột kết quả | Khi kết quả cần loại các hàng hoàn toàn giống nhau |

Trong MySQL, `UNION` không ghi `ALL` mặc định là `DISTINCT`. Hãy ghi rõ toán tử để người đọc thấy ý định.

Ví dụ với đồ thị có thể có nhiều đường đi tới cùng node, `UNION ALL` giữ từng đường đi. Nếu chỉ chọn `node_id` và muốn danh sách node duy nhất, `UNION DISTINCT` có thể loại các node trùng. Nhưng nếu CTE còn có `depth` hoặc `path`, các hàng cùng node có thể khác nhau và vẫn tồn tại.

`UNION DISTINCT` có thể cần công việc loại trùng và bộ nhớ bổ sung. Đừng dùng DISTINCT để che lỗi dữ liệu hoặc thay thế cycle guard mà không hiểu các cột được so sánh.

## 8. Kiểu dữ liệu trong anchor và recursive member

Đây là một đặc điểm rất quan trọng của MySQL recursive CTE: kiểu dữ liệu của các cột CTE được xác định từ phần không đệ quy. Giá trị do recursive member sinh ra được chuyển về kiểu đã suy ra từ anchor.

Ví dụ dễ gặp lỗi độ dài chuỗi:

```sql
WITH RECURSIVE paths (path_value) AS (
    SELECT 'A'

    UNION ALL

    SELECT CONCAT(path_value, 'B')
    FROM paths
    WHERE CHAR_LENGTH(path_value) < 5
)
SELECT path_value
FROM paths;
```

Anchor chỉ tạo chuỗi ngắn `'A'`. Phần đệ quy nối thêm ký tự, nhưng kiểu/độ dài cột kết quả đã được xác định từ anchor. Tùy SQL mode và phiên bản, truy vấn có thể báo lỗi khi giá trị vượt độ dài hoặc phát sinh hành vi chuyển đổi không mong muốn.

Hãy cấp kiểu và độ dài đủ rộng ngay tại anchor:

```sql
WITH RECURSIVE paths (path_value) AS (
    SELECT CAST('A' AS CHAR(100))

    UNION ALL

    SELECT CONCAT(path_value, 'B')
    FROM paths
    WHERE CHAR_LENGTH(path_value) < 5
)
SELECT path_value
FROM paths
ORDER BY CHAR_LENGTH(path_value);
```

Kết quả lần lượt là `A`, `AB`, `ABB`, `ABBB`, `ABBBB`. Anchor cấp trước độ dài 100 để chứa các giá trị tiếp theo.

### 8.1. CAST cho số và độ chính xác

Với số nguyên, anchor cần chọn kiểu đủ lớn cho toàn bộ miền sinh ra. Với số thập phân, cần xác định precision và scale đủ chứa kết quả. Ví dụ:

```sql
WITH RECURSIVE amounts (n, amount) AS (
    SELECT
        1,
        CAST(0.10 AS DECIMAL(12, 2))

    UNION ALL

    SELECT n + 1, amount + 0.10
    FROM amounts
    WHERE n < 5
)
SELECT n, amount
FROM amounts
ORDER BY n;
```

Không dùng số thực `FLOAT`/`DOUBLE` nếu phép tính cần chính xác thập phân. Hãy dùng `DECIMAL` và chọn precision/scale theo giới hạn nghiệp vụ.

### 8.2. Kiểu NULL và collation

Nếu anchor trả `NULL` không có kiểu rõ ràng, kiểu suy ra có thể không phù hợp với giá trị recursive member. Hãy dùng `CAST(NULL AS ...)` để khai báo kiểu dự định. Với chuỗi nhiều charset/collation, bảo đảm các nhánh `UNION` có thể chuyển đổi nhất quán và kiểm tra collation của kết quả.

Ví dụ:

```sql
WITH RECURSIVE labels (label, depth) AS (
    SELECT CAST(NULL AS CHAR(100)), 0

    UNION ALL

    SELECT CONCAT(COALESCE(label, ''), 'child'), depth + 1
    FROM labels
    WHERE depth < 2
)
SELECT label, depth
FROM labels;
```

Ví dụ này minh họa cách khai báo kiểu cho NULL; trong thực tế, hãy thiết kế anchor có ý nghĩa nghiệp vụ và điều kiện dừng rõ ràng, tránh sinh các nhãn rỗng không cần thiết.

## 9. Giới hạn của recursive member trong MySQL

Recursive member không phải một truy vấn SELECT tùy ý. MySQL áp dụng các giới hạn để bảo đảm quá trình đệ quy có thể được xử lý:

- Recursive CTE phải tham chiếu chính nó trong recursive member.
- Bảng CTE đệ quy chỉ được tham chiếu một lần trong mỗi recursive query block và phải xuất hiện trong `FROM`.
- Không đặt tham chiếu CTE đệ quy trong subquery của recursive member.
- Không đặt bảng CTE đệ quy ở phía phải của `LEFT JOIN` trong recursive member.
- Recursive member không được chứa aggregate function, window function, `GROUP BY`, `ORDER BY` hoặc `DISTINCT`.
- Các nhánh anchor và recursive member phải trả cùng số cột, theo đúng thứ tự.

Nếu cần aggregate hoặc sắp xếp, hãy thực hiện ở truy vấn ngoài cùng sau khi CTE đã tạo tập kết quả. Ví dụ, duyệt cây trước rồi mới `GROUP BY depth` ở SELECT ngoài.

MySQL 8.0.19 trở lên cho phép `LIMIT` trong recursive member để giới hạn số hàng được sinh ra trong một số trường hợp. Tuy nhiên, không nên dựa vào LIMIT như cách duy nhất để mô tả điều kiện dừng nghiệp vụ; ưu tiên điều kiện logic rõ ràng trong recursive member và kiểm tra khả năng tương thích phiên bản.

## 10. Giới hạn recursion của MySQL

MySQL kiểm soát độ sâu bằng system variable `cte_max_recursion_depth`. Giá trị mặc định là `1000`. Khi truy vấn vượt giới hạn này, MySQL dừng và trả lỗi thay vì tiếp tục đệ quy vô hạn.

Kiểm tra cấu hình:

```sql
SELECT @@session.cte_max_recursion_depth;
SELECT @@global.cte_max_recursion_depth;
```

Có thể đặt giới hạn riêng cho session:

```sql
SET SESSION cte_max_recursion_depth = 2000;
```

Chỉ tăng giới hạn khi nghiệp vụ thực sự cần độ sâu lớn hơn và đã kiểm tra số hàng sinh ra, thời gian chạy, bộ nhớ và tác động lên máy chủ. Tăng giới hạn không sửa được chu trình hoặc điều kiện dừng sai; nó chỉ cho truy vấn chạy lâu hơn trước khi bị chặn.

Một số biện pháp bảo vệ:

- Đặt điều kiện dừng nghiệp vụ trong recursive member.
- Đặt giới hạn depth riêng nếu dữ liệu có cấu trúc cây.
- Theo dõi chu trình hoặc đường đi lặp lại trong dữ liệu đồ thị.
- Giới hạn khoảng ngày/số lượng phần tử đầu vào.
- Dùng `EXPLAIN` và thử trên dữ liệu đại diện trước khi chạy truy vấn nặng.
- Không tăng `cte_max_recursion_depth` toàn cục chỉ để làm một truy vấn lỗi chạy qua.

## 11. Duyệt cây theo chiều sâu và sắp xếp kết quả

CTE tạo ra tập kết quả, nhưng không bảo đảm thứ tự trả về nếu truy vấn ngoài cùng không có `ORDER BY`. Thứ tự anchor/recursive member hoặc thứ tự hàng trong bảng không phải cam kết thứ tự hiển thị.

Ví dụ:

```sql
WITH RECURSIVE org_tree (node_id, parent_id, node_name, depth) AS (
    SELECT node_id, parent_id, node_name, 0
    FROM org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT child.node_id, child.parent_id, child.node_name, parent.depth + 1
    FROM org_nodes AS child
    JOIN org_tree AS parent
        ON child.parent_id = parent.node_id
)
SELECT node_id, parent_id, node_name, depth
FROM org_tree
ORDER BY depth, node_id;
```

`ORDER BY depth, node_id` tạo thứ tự ổn định theo cấp rồi ID. Đây là thứ tự theo tầng, không phải thứ tự duyệt depth-first theo từng nhánh. Nếu giao diện cần hiển thị cây theo thứ tự trước-sau, hãy tạo cột sort path với các thành phần ID được đệm độ dài cố định rồi sắp xếp theo sort path.

Ví dụ ý tưởng sort path cho ID số nguyên:

```sql
CONCAT(parent.sort_path, '.', LPAD(child.node_id, 10, '0'))
```

Khi dùng sort path, anchor phải CAST sang chuỗi đủ dài giống nguyên tắc ở phần 8. Không sắp xếp path số nguyên dưới dạng chuỗi không đệm nếu ID có độ dài khác nhau, vì thứ tự từ điển có thể đặt `10` trước `2`.

## 12. CTE đệ quy cho đồ thị có nhiều đường đi

Adjacency list có thể biểu diễn cây, nhưng cũng có thể biểu diễn đồ thị nếu một nút có nhiều cạnh đi vào. Khi đó một node có thể được tiếp cận từ nhiều đường khác nhau.

Ví dụ bảng cạnh:

```sql
CREATE TEMPORARY TABLE graph_edges (
    from_node INT NOT NULL,
    to_node INT NOT NULL,
    PRIMARY KEY (from_node, to_node),
    KEY idx_graph_edges_to (to_node)
) ENGINE = InnoDB;

INSERT INTO graph_edges (from_node, to_node) VALUES
(1, 2),
(1, 3),
(2, 4),
(3, 4),
(4, 5);
```

Node 4 có thể đến từ node 2 hoặc node 3. Truy vấn giữ mọi đường đi:

```sql
WITH RECURSIVE paths (node_id, depth, node_path) AS (
    SELECT 1, 0, CAST('1' AS CHAR(1000))

    UNION ALL

    SELECT
        e.to_node,
        p.depth + 1,
        CONCAT(p.node_path, ',', e.to_node)
    FROM graph_edges AS e
    JOIN paths AS p
        ON e.from_node = p.node_id
    WHERE p.depth < 10
      AND FIND_IN_SET(CAST(e.to_node AS CHAR), p.node_path) = 0
)
SELECT node_id, depth, node_path
FROM paths
ORDER BY depth, node_path;
```

Node 4 xuất hiện hai lần với hai path khác nhau: `1,2,4` và `1,3,4`. Đây là kết quả đúng nếu câu hỏi là “có những đường đi nào?”. Nếu câu hỏi là “những node nào có thể đến được từ node 1?”, cần loại trùng theo `node_id` ở truy vấn ngoài hoặc thiết kế truy vấn phù hợp với mục tiêu reachability.

Đồ thị có nhiều đường đi có thể làm số hàng trung gian tăng theo cấp số nhân. Hãy đặt giới hạn depth, cycle guard và đánh giá cardinality trước khi chạy trên dữ liệu lớn.

## 13. Kiểm tra CTE bằng EXPLAIN

Có thể dùng `EXPLAIN` trước câu lệnh có CTE để xem kế hoạch truy vấn:

```sql
EXPLAIN
WITH RECURSIVE org_tree (node_id, parent_id, node_name, depth) AS (
    SELECT node_id, parent_id, node_name, 0
    FROM org_nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT child.node_id, child.parent_id, child.node_name, parent.depth + 1
    FROM org_nodes AS child
    JOIN org_tree AS parent
        ON child.parent_id = parent.node_id
    WHERE parent.depth < 20
)
SELECT node_id, parent_id, node_name, depth
FROM org_tree;
```

Quan sát:

- Cách MySQL truy cập bảng nguồn ở anchor và recursive member.
- Index trên `parent_id` có được sử dụng để tìm nút con hay không.
- Số hàng ước lượng và số lần lặp có thể phát sinh.
- Chi phí materialization/tập trung gian nếu được hiển thị trong plan.

`EXPLAIN ANALYZE` thực thi truy vấn thật. Chỉ dùng khi có thể chấp nhận tải phát sinh, đặc biệt với đồ thị có nhiều nhánh hoặc giới hạn depth lớn.

Một vài hướng tối ưu:

- Tạo index trên cột nối từ bảng nguồn sang CTE, ví dụ `org_nodes(parent_id)`.
- Lọc anchor càng cụ thể càng tốt nếu chỉ cần một subtree.
- Chỉ đưa các cột cần thiết vào CTE; path dài hoặc payload lớn làm tăng kích thước hàng trung gian.
- Giới hạn độ sâu và số lượng đầu vào theo yêu cầu nghiệp vụ.
- Tránh `UNION DISTINCT` nếu không cần loại trùng, vì deduplication có chi phí.
- Với truy vấn cây chạy thường xuyên và cây lớn, cân nhắc mô hình lưu trữ phù hợp như closure table hoặc materialized path thay vì tính lại mọi lần.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Anchor không tạo điểm bắt đầu đúng | CTE rỗng hoặc duyệt sai nhánh | Xác định rõ root/seed rows |
| Recursive member không tham chiếu CTE đúng cách | Không mở rộng được thế hệ tiếp theo | Join bảng nguồn với CTE hiện tại |
| Thiếu điều kiện dừng | Đệ quy tới giới hạn máy chủ hoặc tiêu tốn tài nguyên | Đặt predicate dừng theo nghiệp vụ |
| Anchor trả kiểu chuỗi quá ngắn | Giá trị recursive bị lỗi hoặc cắt | CAST độ dài đủ rộng trong anchor |
| Dùng kiểu số không đủ miền | Tràn hoặc mất độ chính xác | Chọn kiểu đủ lớn và CAST tường minh |
| Nghĩ UNION DISTINCT luôn chống cycle | Hàng có depth/path khác vẫn được xem là khác | Dùng cycle guard theo ID đã đi qua |
| Không có ORDER BY cuối | Thứ tự kết quả không được bảo đảm | Sắp xếp ở SELECT ngoài cùng |
| Dùng CTE đệ quy cho đồ thị nhiều đường mà không giới hạn | Số hàng trung gian tăng rất nhanh | Giới hạn depth, path và đầu vào |
| Tăng recursion depth để che lỗi | Truy vấn lỗi chạy lâu hơn, tải cao hơn | Sửa điều kiện dừng và dữ liệu |
| Aggregate trong recursive member | Vi phạm giới hạn cú pháp | Aggregate ở truy vấn ngoài cùng |

## 15. Bài tập thực hành

1. Viết CTE đệ quy sinh dãy từ 1 đến 100. Thử thay điều kiện dừng thành `n <= 100` và giải thích vì sao kết quả vượt quá 100 nếu viết sai vị trí.
2. Sinh dãy giảm từ 20 về 0. Xác định anchor, recursive member và điều kiện dừng.
3. Sinh các ngày từ đầu tháng đến cuối tháng 11/2026. Kết hợp `LEFT JOIN` với bảng giao dịch để hiển thị ngày không có giao dịch.
4. Tạo bảng adjacency list cho sơ đồ tổ chức. Duyệt toàn bộ cây từ root và chỉ duyệt subtree bắt đầu ở một node giữa cây.
5. Thêm cột `id_path` và `depth`. Giải thích vì sao anchor phải CAST độ dài chuỗi đủ lớn.
6. Tạo dữ liệu có chu trình trong một bảng lab riêng. Chạy truy vấn không cycle guard trong giới hạn recursion thấp, sau đó thêm `FIND_IN_SET()` để ngăn quay lại node trong cùng path.
7. So sánh `UNION ALL` và `UNION DISTINCT` khi CTE chỉ chứa `node_id`, rồi thêm `depth` và `path`; quan sát khả năng loại trùng thay đổi ra sao.
8. Tạo đồ thị có hai đường khác nhau tới cùng một node. Liệt kê mọi path rồi tạo truy vấn chỉ lấy danh sách node duy nhất.
9. Thử một recursive member có `GROUP BY` hoặc aggregate trong môi trường lab, đọc lỗi và viết lại bằng aggregate ở truy vấn ngoài.
10. Chạy `EXPLAIN` cho truy vấn duyệt cây trước và sau khi thêm index trên `parent_id`. Ghi nhận khác biệt kế hoạch và giới hạn của dữ liệu lab nhỏ.

## 16. Checklist trước khi đưa recursive CTE vào production

- [ ] Anchor xác định đúng seed rows và có kiểu dữ liệu phù hợp.
- [ ] Anchor và recursive member trả cùng số cột, đúng thứ tự.
- [ ] Kiểu cột được suy ra từ anchor đủ rộng cho mọi vòng đệ quy.
- [ ] Recursive member tham chiếu CTE đúng vị trí và chỉ một lần theo giới hạn MySQL.
- [ ] Có điều kiện dừng rõ ràng và có thể chứng minh được.
- [ ] Có cycle guard nếu dữ liệu có thể chứa chu trình.
- [ ] Đã xác định cần giữ mọi đường đi hay chỉ cần mỗi node một lần.
- [ ] `UNION ALL`/`UNION DISTINCT` được chọn theo ngữ nghĩa, không dùng như mẹo chữa lỗi.
- [ ] Độ sâu và số hàng sinh ra nằm trong giới hạn tài nguyên.
- [ ] `cte_max_recursion_depth` được kiểm tra, không tăng tùy tiện.
- [ ] Index trên cột nối của bảng nguồn đã được đánh giá.
- [ ] Thứ tự kết quả được khai báo ở SELECT ngoài cùng nếu cần.
- [ ] Kế hoạch được kiểm tra bằng `EXPLAIN` và thử với dữ liệu đại diện.

## 17. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể giải thích rõ anchor member và recursive member, viết được CTE đệ quy có điều kiện dừng, sinh dãy số/ngày, duyệt cây từ root hoặc một node bất kỳ, kiểm soát kiểu dữ liệu bằng `CAST()`, phát hiện và ngăn chu trình theo đường đi, phân biệt `UNION ALL` với `UNION DISTINCT`, đồng thời kiểm soát độ sâu và đánh giá truy vấn bằng `EXPLAIN`.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — WITH (Common Table Expressions)](https://dev.mysql.com/doc/refman/8.4/en/with.html)
- [MySQL 8.4 Reference Manual — Recursive CTEs](https://dev.mysql.com/doc/refman/8.4/en/with.html#common-table-expressions-recursive)
- [MySQL 8.4 Reference Manual — Server System Variables (`cte_max_recursion_depth`)](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
