# Recursive subquery factoring, SEARCH và CYCLE

Nhiều dữ liệu trong hệ thống có cấu trúc **cha – con** hoặc **đồ thị liên kết**: nhân viên thuộc cấp quản lý, danh mục có danh mục cha, thư mục chứa thư mục con, sản phẩm có thành phần, hoặc một nút có thể nối tới nhiều nút khác. Khi cần truy vấn nhiều cấp, viết một câu JOIN cố định cho từng cấp sẽ nhanh chóng trở nên dài và khó bảo trì.

Oracle Database hỗ trợ **recursive subquery factoring** trong mệnh đề `WITH`. Một query block có thể tham chiếu lại chính tên của nó để mở rộng kết quả qua nhiều vòng. Hai thành phần đặc biệt giúp điều khiển cách đọc kết quả và bảo vệ phép đệ quy là:

- **`SEARCH`**: yêu cầu Oracle tạo cột thứ tự để biểu diễn cách duyệt theo chiều sâu (**depth-first**) hoặc chiều rộng (**breadth-first**).
- **`CYCLE`**: chỉ định các cột dùng để phát hiện một đường đi quay lại tổ tiên, đánh dấu hàng gây chu trình và dừng mở rộng từ hàng đó.

Bài học trình bày cú pháp Oracle, hai thành phần anchor/recursive, cách tạo đường đi, thứ tự duyệt, nhận diện chu trình, và cách áp dụng vào cây phân cấp lẫn đồ thị có nhiều đường đi.

## 1. Recursive subquery factoring là gì?

**Subquery factoring** cho phép đặt tên cho một query block bằng `WITH`. Tên đó có thể được tham chiếu ở phần SELECT bên ngoài hoặc ở query block tiếp theo. Khi query block được đặt tên tham chiếu lại chính nó trong định nghĩa, đó là **recursive subquery factoring**.

Ví dụ khái niệm:

```sql
WITH hierarchy AS (
    -- Anchor: bắt đầu từ một hoặc nhiều nút gốc
    SELECT ...

    UNION ALL

    -- Recursive member: tìm các nút tiếp theo từ kết quả trước
    SELECT ...
    FROM hierarchy ...
)
SELECT *
FROM hierarchy;
```

Mỗi vòng đệ quy sử dụng các hàng đã được tạo ở vòng trước để tìm thêm hàng. Quá trình kết thúc khi recursive member không tạo thêm hàng nào. Điều kiện nối và dữ liệu phải được thiết kế để việc mở rộng có điểm dừng; với đồ thị có chu trình, cần chiến lược phát hiện chu trình phù hợp.

Oracle dùng cú pháp `WITH`, **không cần từ khóa `RECURSIVE`** như một số hệ quản trị cơ sở dữ liệu khác.

## 2. Hai phần bắt buộc: anchor member và recursive member

Một recursive subquery factoring có hai query block:

1. **Anchor member**: query đầu tiên, xác định điểm bắt đầu. Nó không tham chiếu tên recursive query.
2. **Recursive member**: query tiếp theo, tham chiếu tên recursive query đúng một lần để tạo bước tiếp theo.

Hai phần được nối bằng `UNION ALL`.

### 2.1. Cú pháp tổng quát

```sql
WITH query_name (
    column_1,
    column_2,
    ...
) AS (
    -- Anchor member
    SELECT ...
    FROM ...
    WHERE start_condition

    UNION ALL

    -- Recursive member
    SELECT ...
    FROM query_name q
    JOIN source_table s
      ON recursive_condition
)
SELECT ...
FROM query_name;
```

Danh sách alias sau tên query là bắt buộc trong recursive subquery factoring. Số cột và thứ tự cột của alias list phải khớp với danh sách SELECT của anchor và recursive member; các kiểu dữ liệu tương ứng phải tương thích.

### 2.2. Cách một vòng đệ quy hoạt động

```text
Vòng 0: Anchor tạo nút 1
             |
             v
Vòng 1: Từ nút 1 tìm các nút con 2, 3
             |
             v
Vòng 2: Từ các nút 2, 3 tìm nút con
             |
             v
Vòng 3: Từ các nút mới tiếp tục tìm nút con
             |
             v
        Không còn hàng mới
             |
             v
        Kết thúc đệ quy
```

Đây là mô hình tư duy về các thế hệ kết quả. Oracle Optimizer quyết định cách thực thi vật lý; không nên hiểu sơ đồ này là cam kết rằng database luôn ghi hoặc xử lý từng hàng theo đúng thứ tự hiển thị trong sơ đồ.

### 2.3. Vì sao phải dùng UNION ALL?

Oracle yêu cầu nối anchor member với recursive member bằng `UNION ALL`. Không thay bằng `UNION` chỉ để “loại hàng trùng”.

- `UNION ALL` giữ các hàng do từng vòng sinh ra.
- `UNION` loại trùng và không phải toán tử được phép thay thế trong vị trí kết hợp anchor với recursive member theo cú pháp recursive subquery factoring của Oracle.
- Nếu đồ thị có nhiều đường đi tới cùng một nút, cùng `NODE_ID` có thể xuất hiện nhiều lần trong kết quả vì mỗi hàng đại diện cho một đường đi khác nhau.

Nếu yêu cầu nghiệp vụ chỉ muốn một hàng trên mỗi nút, cần xác định rõ cách chọn đường đi hoặc tổng hợp ở query bên ngoài; không thể dựa vào việc đổi `UNION ALL` thành `UNION`.

## 3. Tạo dữ liệu lab dạng đồ thị

Để quan sát cả nhánh cây, nhiều đường đi và chu trình, ta dùng hai bảng:

- `LAB_ORG_NODES`: danh sách nút.
- `LAB_ORG_EDGES`: các cạnh có hướng từ nút cha sang nút con.

Mô hình cạnh giúp biểu diễn đồ thị tổng quát, trong đó một nút có thể được đi tới từ nhiều nút cha. Nó cũng giúp tạo một chu trình kiểm thử mà không phải thay đổi cấu trúc nhân viên/phòng ban.

### 3.1. Tạo bảng

Chạy trong schema thực hành do bạn sở hữu:

```sql
CREATE TABLE lab_org_nodes (
    node_id   NUMBER PRIMARY KEY,
    node_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE lab_org_edges (
    parent_id NUMBER NOT NULL,
    child_id  NUMBER NOT NULL,
    CONSTRAINT pk_lab_org_edges
        PRIMARY KEY (parent_id, child_id),
    CONSTRAINT fk_lab_edge_parent
        FOREIGN KEY (parent_id)
        REFERENCES lab_org_nodes (node_id),
    CONSTRAINT fk_lab_edge_child
        FOREIGN KEY (child_id)
        REFERENCES lab_org_nodes (node_id),
    CONSTRAINT ck_lab_edge_not_self
        CHECK (parent_id <> child_id)
);
```

Ràng buộc `CHECK` chỉ ngăn một cạnh tự nối trực tiếp `n -> n`; nó không ngăn chu trình dài hơn như `1 -> 2 -> 3 -> 1`. `CYCLE` sẽ xử lý loại chu trình đó trong truy vấn.

### 3.2. Chèn nút

```sql
INSERT INTO lab_org_nodes VALUES (1, 'Root');
INSERT INTO lab_org_nodes VALUES (2, 'Platform');
INSERT INTO lab_org_nodes VALUES (3, 'Business');
INSERT INTO lab_org_nodes VALUES (4, 'Shared Service');
INSERT INTO lab_org_nodes VALUES (5, 'Delivery');
INSERT INTO lab_org_nodes VALUES (6, 'Operations');
INSERT INTO lab_org_nodes VALUES (7, 'Risk');

COMMIT;
```

### 3.3. Chèn các cạnh ban đầu

```sql
INSERT INTO lab_org_edges VALUES (1, 2);
INSERT INTO lab_org_edges VALUES (1, 3);
INSERT INTO lab_org_edges VALUES (2, 4);
INSERT INTO lab_org_edges VALUES (3, 4);
INSERT INTO lab_org_edges VALUES (4, 5);
INSERT INTO lab_org_edges VALUES (4, 6);
INSERT INTO lab_org_edges VALUES (6, 7);

COMMIT;
```

Đồ thị ban đầu:

```text
                 1 Root
                /      \
          2 Platform   3 Business
                \      /
              4 Shared Service
                /       \
          5 Delivery   6 Operations
                           |
                         7 Risk
```

Nút `4` có hai đường đi từ nút gốc: `1 -> 2 -> 4` và `1 -> 3 -> 4`. Đây là đồ thị có nhiều đường đi tới một nút, nhưng **chưa có chu trình**. Việc nút 4 xuất hiện hai lần trong quá trình duyệt không có nghĩa là đã gặp cycle.

## 4. Viết recursive query đầu tiên

Ta muốn đi từ nút gốc `1`, trả về nút, tên, độ sâu và đường đi.

```sql
WITH org_walk (
    node_id,
    node_name,
    depth_no,
    path_txt
) AS (
    -- Anchor member: bắt đầu tại Root.
    SELECT
        n.node_id,
        n.node_name,
        0 AS depth_no,
        CAST(TO_CHAR(n.node_id) AS VARCHAR2(4000)) AS path_txt
    FROM lab_org_nodes n
    WHERE n.node_id = 1

    UNION ALL

    -- Recursive member: đi từ nút hiện tại tới nút con.
    SELECT
        child.node_id,
        child.node_name,
        parent.depth_no + 1,
        CAST(
            parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
            AS VARCHAR2(4000)
        )
    FROM org_walk parent
    JOIN lab_org_edges edge
      ON edge.parent_id = parent.node_id
    JOIN lab_org_nodes child
      ON child.node_id = edge.child_id
)
SELECT
    node_id,
    node_name,
    depth_no,
    path_txt
FROM org_walk
ORDER BY depth_no, node_id, path_txt;
```

### 4.1. Đọc từng phần

**Alias list**:

```sql
org_walk (node_id, node_name, depth_no, path_txt)
```

Định nghĩa tên bốn cột mà query bên ngoài và recursive member có thể tham chiếu.

**Anchor member**:

```sql
SELECT n.node_id, n.node_name, 0, CAST(...)
FROM lab_org_nodes n
WHERE n.node_id = 1
```

Chỉ tạo một hàng bắt đầu tại Root. Anchor không được tham chiếu `ORG_WALK`.

**Recursive member**:

```sql
FROM org_walk parent
JOIN lab_org_edges edge
  ON edge.parent_id = parent.node_id
JOIN lab_org_nodes child
  ON child.node_id = edge.child_id
```

Với mỗi hàng hiện tại, tìm các cạnh có `PARENT_ID` bằng `NODE_ID` của hàng đó, rồi lấy thông tin nút con.

**Độ sâu**:

```sql
parent.depth_no + 1
```

Anchor bắt đầu ở độ sâu 0; mỗi cạnh đi thêm một bước thì tăng 1.

**Đường đi**:

```sql
parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
```

Mỗi vòng nối thêm ID nút mới vào chuỗi đường đi. `CAST` giúp hai nhánh có kiểu dữ liệu ký tự tương thích và dành dung lượng cho path minh họa. Đây vẫn là `VARCHAR2(4000)` trong SQL; với đường đi rất dài, cần thiết kế cách lưu/biểu diễn khác và xem xét giới hạn kiểu dữ liệu.

### 4.2. Kết quả có thể có nhiều hàng cho cùng NODE_ID

Nút Shared Service (4) được đi tới qua hai đường:

```text
1 -> 2 -> 4
1 -> 3 -> 4
```

Do `UNION ALL` giữ cả hai đường, kết quả có hai hàng `NODE_ID = 4`, với `PATH_TXT` khác nhau. Các nút 5, 6 và 7 cũng có thể được tạo từ mỗi đường đi tới nút 4. Đây là hành vi đúng khi câu hỏi là **liệt kê các đường đi**, không phải danh sách nút duy nhất.

## 5. SEARCH: chọn thứ tự duyệt chiều sâu hoặc chiều rộng

`SEARCH` là phần mở rộng của recursive subquery factoring để chỉ định cách tạo thứ tự cho các hàng. Oracle cung cấp:

- `SEARCH DEPTH FIRST BY ... SET ordering_column`
- `SEARCH BREADTH FIRST BY ... SET ordering_column`

Các cột sau `BY` phải thuộc alias list của recursive query. `SET` khai báo tên cột thứ tự do Oracle tự thêm vào query name.

**SEARCH tạo cột thứ tự; nó không tự bảo đảm thứ tự hàng trả ra cho client.** Muốn thấy đúng thứ tự đã khai báo, query bên ngoài phải `ORDER BY` cột được tạo bởi `SET`.

### 5.1. DEPTH FIRST: đi sâu một nhánh trước

```sql
WITH org_walk (
    node_id,
    node_name,
    depth_no,
    path_txt
) AS (
    SELECT
        n.node_id,
        n.node_name,
        0,
        CAST(TO_CHAR(n.node_id) AS VARCHAR2(4000))
    FROM lab_org_nodes n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.node_name,
        parent.depth_no + 1,
        CAST(
            parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
            AS VARCHAR2(4000)
        )
    FROM org_walk parent
    JOIN lab_org_edges edge
      ON edge.parent_id = parent.node_id
    JOIN lab_org_nodes child
      ON child.node_id = edge.child_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
SELECT
    node_id,
    node_name,
    depth_no,
    path_txt,
    dfs_order
FROM org_walk
ORDER BY dfs_order;
```

`DEPTH FIRST` ưu tiên đi tiếp xuống các nút con trước khi quay lại xét các nhánh anh em. `BY node_id` quy định thứ tự các nút cùng cấp/anh em theo ID tăng dần. Nếu muốn thứ tự khác, có thể dùng một hoặc nhiều cột phù hợp, cùng chỉ định ASC/DESC và quy tắc NULL khi cột cho phép NULL.

### 5.2. BREADTH FIRST: xử lý từng tầng trước

```sql
WITH org_walk (
    node_id,
    node_name,
    depth_no,
    path_txt
) AS (
    SELECT
        n.node_id,
        n.node_name,
        0,
        CAST(TO_CHAR(n.node_id) AS VARCHAR2(4000))
    FROM lab_org_nodes n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.node_name,
        parent.depth_no + 1,
        CAST(
            parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
            AS VARCHAR2(4000)
        )
    FROM org_walk parent
    JOIN lab_org_edges edge
      ON edge.parent_id = parent.node_id
    JOIN lab_org_nodes child
      ON child.node_id = edge.child_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
SELECT
    node_id,
    node_name,
    depth_no,
    path_txt,
    bfs_order
FROM org_walk
ORDER BY bfs_order;
```

`BREADTH FIRST` đưa các hàng cùng mức sâu trước khi mở rộng các mức sâu hơn. Với đồ thị lab, hình dung theo tầng:

| Độ sâu | Các lần gặp nút |
| ---: | --- |
| 0 | 1 |
| 1 | 2, 3 |
| 2 | 4 qua 2; 4 qua 3 |
| 3 | 5, 6 qua mỗi đường tới 4 |
| 4 | 7 qua nhánh 6 |

Do nút 4 có hai đường đi, nó xuất hiện hai lần ở tầng 2. `SEARCH BREADTH FIRST` không loại bỏ các đường đi trùng nút; nó chỉ tạo thứ tự để hàng theo độ sâu được sắp trước hàng sâu hơn.

### 5.3. SEARCH không thay thế ORDER BY

Ví dụ:

```sql
SEARCH DEPTH FIRST BY node_id SET dfs_order
SELECT node_id, node_name
FROM org_walk
ORDER BY dfs_order;
```

Nếu bỏ `ORDER BY dfs_order`, Oracle không cam kết client nhận kết quả theo thứ tự depth-first. Một execution plan hoặc lần chạy tình cờ trả hàng theo thứ tự mong muốn không phải hợp đồng SQL.

Tên cột do `SET` tạo:

- Được Oracle tự thêm vào danh sách cột của query name.
- Có thể được query bên ngoài tham chiếu trong `SELECT` hoặc `ORDER BY`.
- Phải khác tên các cột đã khai báo trong alias list.
- Phải khác tên cycle mark column nếu cùng dùng `CYCLE`.

## 6. CYCLE: phát hiện đường đi quay lại tổ tiên

Trong đồ thị, một **cycle** xuất hiện khi đường đi quay lại một nút đã có trong chính đường đi tổ tiên hiện tại. Ví dụ:

```text
1 -> 2 -> 4 -> 5 -> 1
```

Nút 1 được gặp lại khi nó đã là tổ tiên của đường đi. Nếu tiếp tục mở rộng không kiểm soát, truy vấn có thể lặp vô hạn hoặc chạm giới hạn đệ quy/tài nguyên.

`CYCLE` cho phép chỉ định cột dùng để nhận diện chu trình và cột đánh dấu kết quả:

```sql
CYCLE cycle_column [, cycle_column ...]
SET cycle_mark_column TO 'Y'
DEFAULT 'N'
```

Trong cú pháp Oracle:

- Các cột sau `CYCLE` phải nằm trong alias list của query name.
- Nếu phát hiện hàng tạo cycle, cột đánh dấu của hàng đó nhận `cycle_value`.
- Oracle **vẫn trả hàng gây cycle** với dấu đánh dấu tương ứng, nhưng không tiếp tục tìm hàng con từ hàng đó.
- Các nhánh không tạo cycle vẫn tiếp tục được mở rộng.
- Nếu không phát hiện cycle, cột đánh dấu nhận `no_cycle_value`.
- Hai giá trị đánh dấu phải là chuỗi ký tự một byte; ví dụ `'Y'` và `'N'`.

### 6.1. Thêm một cạnh tạo chu trình

Trong lab, thêm cạnh từ Delivery (5) trở lại Root (1):

```sql
INSERT INTO lab_org_edges VALUES (5, 1);
COMMIT;
```

Đồ thị lúc này có đường đi:

```text
1 Root
  -> 2 Platform
     -> 4 Shared Service
        -> 5 Delivery
           -> 1 Root   (quay lại tổ tiên)
```

Ràng buộc khóa ngoại vẫn hợp lệ vì cả hai nút 5 và 1 tồn tại. `CHECK (parent_id <> child_id)` không ngăn được chu trình nhiều cạnh; đó là mục đích của phần thực hành `CYCLE`.

### 6.2. Dùng CYCLE node_id

```sql
WITH org_walk (
    node_id,
    node_name,
    depth_no,
    path_txt
) AS (
    SELECT
        n.node_id,
        n.node_name,
        0,
        CAST(TO_CHAR(n.node_id) AS VARCHAR2(4000))
    FROM lab_org_nodes n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.node_name,
        parent.depth_no + 1,
        CAST(
            parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
            AS VARCHAR2(4000)
        )
    FROM org_walk parent
    JOIN lab_org_edges edge
      ON edge.parent_id = parent.node_id
    JOIN lab_org_nodes child
      ON child.node_id = edge.child_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
SELECT
    node_id,
    node_name,
    depth_no,
    path_txt,
    cycle_flag
FROM org_walk
ORDER BY dfs_order;
```

Khi đường đi `1 -> 2 -> 4 -> 5 -> 1` quay về nút 1, hàng lặp có `CYCLE_FLAG = 'Y'`. Oracle giữ hàng này để có thể quan sát chu trình, rồi ngừng mở rộng từ hàng gây cycle. Những nhánh khác như `4 -> 6 -> 7` vẫn được duyệt.

### 6.3. Hàng cycle vẫn nằm trong kết quả

Một nhầm lẫn phổ biến là nghĩ `CYCLE` tự xóa hàng lặp. Thực tế, nó **đánh dấu** hàng gây cycle. Nếu báo cáo chỉ muốn các hàng không bị đánh dấu:

```sql
WITH org_walk (
    node_id,
    node_name,
    depth_no,
    path_txt
) AS (
    SELECT
        n.node_id,
        n.node_name,
        0,
        CAST(TO_CHAR(n.node_id) AS VARCHAR2(4000))
    FROM lab_org_nodes n
    WHERE n.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.node_name,
        parent.depth_no + 1,
        CAST(
            parent.path_txt || ' -> ' || TO_CHAR(child.node_id)
            AS VARCHAR2(4000)
        )
    FROM org_walk parent
    JOIN lab_org_edges edge
      ON edge.parent_id = parent.node_id
    JOIN lab_org_nodes child
      ON child.node_id = edge.child_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
SELECT node_id, node_name, depth_no, path_txt
FROM org_walk
WHERE cycle_flag = 'N'
ORDER BY dfs_order;
```

Lọc `cycle_flag = 'N'` ở query bên ngoài chỉ ẩn các hàng đã đánh dấu trong kết quả. Nó không thay đổi quy tắc phát hiện cycle và không phải cách thay thế cho việc thiết kế khóa chu trình.

### 6.4. Cycle là theo đường đi, không phải trùng nút toàn cục

Trong đồ thị ban đầu, nút 4 được tới qua hai nhánh:

```text
1 -> 2 -> 4
1 -> 3 -> 4
```

Nút 4 xuất hiện ở hai hàng khác nhau, nhưng **không phải cycle**: trong mỗi đường đi riêng, nút 4 chưa xuất hiện trước đó trong danh sách tổ tiên của chính đường đó.

`CYCLE node_id` so sánh với các hàng tổ tiên của đường đi hiện tại. Nó không có nghĩa “nếu NODE_ID từng xuất hiện ở bất kỳ nơi nào trong toàn bộ kết quả thì đánh dấu hàng sau là cycle”.

Điểm này quan trọng khi duyệt DAG (directed acyclic graph) có nhiều đường tới cùng nút. Một nút có thể được thăm nhiều lần theo nhiều đường hợp lệ mà không tạo chu trình.

## 7. Chọn cột nào trong CYCLE?

Danh sách cột sau `CYCLE` xác định **định nghĩa một trạng thái lặp**. Không phải lúc nào chỉ `NODE_ID` cũng đủ.

### 7.1. CYCLE node_id cho đồ thị nút

Với đồ thị trong lab, một nút lặp trên cùng đường đi có nghĩa đã quay lại chính nút đó:

```sql
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
```

Đây là lựa chọn phù hợp khi trạng thái cần phát hiện cycle được định nghĩa chỉ bằng node identity.

### 7.2. CYCLE theo khóa ghép

Giả sử truy vấn không chỉ duyệt nút mà còn mang theo một trạng thái nghiệp vụ, ví dụ `NODE_ID + ACCESS_MODE`. Cùng một node có thể xuất hiện với các chế độ truy cập khác nhau. Nếu trạng thái `(node_id, access_mode)` mới là định danh của một bước trong thuật toán, có thể cần:

```sql
CYCLE node_id, access_mode
SET cycle_flag TO 'Y' DEFAULT 'N'
```

Các cột phải nằm trong alias list. Chọn khóa quá rộng có thể khiến một vòng quay lại node không được nhận diện nếu các thuộc tính khác thay đổi theo từng vòng. Chọn khóa quá hẹp có thể đánh dấu một trạng thái là cycle dù nghiệp vụ cho phép cùng node xuất hiện ở các trạng thái khác nhau.

Hãy trả lời câu hỏi: **“Một trạng thái được coi là đã quay lại khi những thuộc tính nào giống với một tổ tiên?”** rồi mới quyết định danh sách CYCLE.

### 7.3. CYCLE không thay thế quy tắc giới hạn nghiệp vụ

`CYCLE` ngăn tiếp tục mở rộng một đường đi khi phát hiện lặp theo khóa đã chọn. Nó không thay thế:

- Giới hạn độ sâu nếu nghiệp vụ chỉ cho phép tối đa N cấp.
- Quyền truy cập hoặc phạm vi tenant.
- Điều kiện lọc dữ liệu không hợp lệ.
- Kiểm tra dữ liệu đầu vào.
- Quy tắc loại bỏ đường đi không được phép.

Nếu cần giới hạn độ sâu, có thể đưa `WHERE parent.depth_no < :max_depth` vào recursive member. Hãy kiểm tra giới hạn đó có làm mất dữ liệu hợp lệ hay không. Nếu có cycle, vẫn nên dùng CYCLE để thể hiện rõ quy tắc phát hiện chu trình.

## 8. Khi không khai báo CYCLE

Oracle có cơ chế phát hiện cycle mặc định cho recursive subquery factoring. Nếu phát hiện chu trình và không có `CYCLE` clause, truy vấn có thể kết thúc với lỗi:

```text
ORA-32044: cycle detected while executing recursive WITH query
```

Quy tắc phát hiện mặc định dựa trên các cột trong alias list của recursive query được tham chiếu trong `WHERE` của recursive member. Khi cần xác định rõ khóa dùng để nhận diện trạng thái lặp, hãy khai báo `CYCLE` tường minh thay vì phụ thuộc vào quy tắc mặc định.

Đừng xóa CYCLE để “sửa” ORA-32044 mà không kiểm tra dữ liệu. Lỗi thường cho biết có một đường đi quay lại trạng thái tổ tiên theo tiêu chí cycle của query.

## 9. SEARCH và CYCLE có thể dùng cùng nhau

Một recursive query thường cần cả hai:

```sql
WITH graph_walk (node_id, depth_no) AS (
    SELECT node_id, 0
    FROM lab_org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT e.child_id, w.depth_no + 1
    FROM graph_walk w
    JOIN lab_org_edges e
      ON e.parent_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET traversal_order
CYCLE node_id SET is_cycle TO 'Y' DEFAULT 'N'
SELECT
    node_id,
    depth_no,
    is_cycle,
    traversal_order
FROM graph_walk
ORDER BY traversal_order;
```

Ở đây:

- `SEARCH BREADTH FIRST` tạo `TRAVERSAL_ORDER` để sắp hàng theo chiều rộng.
- `CYCLE node_id` đánh dấu hàng quay lại nút tổ tiên.
- `IS_CYCLE` được Oracle tự thêm vào cột của query name.
- `TRAVERSAL_ORDER` cũng được tự thêm vào cột của query name.
- Hai tên cột sinh tự động phải khác nhau và không được trùng tên alias list.

Nếu muốn xem cycle trước rồi mới lọc, giữ `IS_CYCLE` trong SELECT. Nếu muốn chỉ lấy hàng bình thường, lọc `IS_CYCLE = 'N'` ở query ngoài.

## 10. Giới hạn của recursive member trong Oracle

Recursive member có một số hạn chế cú pháp quan trọng. Theo SQL Language Reference của Oracle 19c:

- Phải tham chiếu query name **đúng một lần** trong FROM clause.
- Phải được nối với anchor bằng `UNION ALL`.
- Không được dùng `DISTINCT` hoặc `GROUP BY` trong recursive member.
- Không được dùng aggregate function trong recursive member; analytic functions được phép trong select list.
- Không được có subquery tham chiếu query name.
- Không được dùng outer join có query name ở vị trí bảng bên phải của outer join.
- Cột alias list và các SELECT list phải khớp số lượng, thứ tự và kiểu tương thích.

Vì vậy, nếu cần tổng hợp kết quả sau khi duyệt, hãy aggregate ở query block bên ngoài:

```sql
WITH org_walk (node_id, depth_no) AS (
    SELECT node_id, 0
    FROM lab_org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT e.child_id, w.depth_no + 1
    FROM org_walk w
    JOIN lab_org_edges e
      ON e.parent_id = w.node_id
)
SEARCH BREADTH FIRST BY node_id SET bfs_order
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
SELECT
    depth_no,
    COUNT(*) AS visited_rows
FROM org_walk
WHERE cycle_flag = 'N'
GROUP BY depth_no
ORDER BY depth_no;
```

`GROUP BY` nằm ở query ngoài, không nằm trong recursive member. Query bên ngoài nhận tập hàng đã được đệ quy tạo ra rồi mới tổng hợp.

## 11. Recursive subquery factoring và CONNECT BY

Oracle có cú pháp phân cấp truyền thống `START WITH ... CONNECT BY`, thường gặp trong các hệ thống cũ:

```sql
SELECT
    employee_id,
    manager_id,
    LEVEL AS depth_no
FROM employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
```

Ví dụ này minh họa cấu trúc quen thuộc trên một bảng `EMPLOYEES` có `EMPLOYEE_ID` và `MANAGER_ID`. Với mô hình cạnh `LAB_ORG_EDGES`, cần xây dựng nguồn hàng tương ứng trước khi dùng `CONNECT BY`. Recursive subquery factoring dùng `WITH` để thể hiện rõ anchor và recursive member, phù hợp khi muốn mang theo nhiều trạng thái như path, chi phí tích lũy hoặc dữ liệu qua mỗi bước.

| Khả năng | Recursive subquery factoring | CONNECT BY |
| --- | --- | --- |
| Điểm bắt đầu | Anchor member | `START WITH` |
| Bước mở rộng | Recursive member + `UNION ALL` | `CONNECT BY PRIOR` |
| Độ sâu | Tự mang cột depth hoặc tính trong query | `LEVEL` |
| Thứ tự duyệt | `SEARCH DEPTH/BREADTH FIRST` tạo ordering column | `ORDER SIBLINGS BY` cho anh em |
| Xử lý cycle | `CYCLE` mark column | `NOCYCLE`, `CONNECT_BY_ISCYCLE` |
| Trạng thái tích lũy | Có thể mang cột path/cost/state trong CTE | Có các pseudocolumn/hàm phân cấp riêng |
| Cấu trúc | Dạng CTE với query block tường minh | Cú pháp phân cấp riêng của Oracle |

Không cần chuyển mọi truy vấn CONNECT BY sang recursive WITH. Hãy dùng cấu trúc phù hợp với độ phức tạp, yêu cầu phiên bản và khả năng bảo trì của hệ thống.

## 12. Ứng dụng thực tế

### 12.1. Cây tổ chức nhân viên

Mỗi nhân viên có `MANAGER_ID`; anchor bắt đầu từ CEO có manager NULL, recursive member tìm nhân viên có manager là người ở hàng trước. `SEARCH DEPTH FIRST` có thể hiển thị một nhánh quản lý trọn vẹn; `CYCLE employee_id` giúp phát hiện dữ liệu quản lý bị vòng.

### 12.2. Danh mục nhiều cấp

Danh mục sản phẩm có `CATEGORY_ID` và `PARENT_CATEGORY_ID`. Có thể bắt đầu từ một danh mục cấp cao, đệ quy tìm các danh mục con, mang theo `DEPTH_NO` và path để tạo breadcrumb. Cycle detection giúp phát hiện cấu hình cha-con không hợp lệ.

### 12.3. Phụ thuộc công việc

Một công việc có thể phụ thuộc vào nhiều công việc khác. Đồ thị dependency có thể có nhiều đường đi; `SEARCH` giúp sắp thứ tự duyệt, `CYCLE` phát hiện vòng phụ thuộc khiến không thể lập lịch topo hợp lệ. Tuy nhiên, `SEARCH` không tự tính thứ tự triển khai hợp lệ theo mọi quy tắc nghiệp vụ; cần mô hình và thuật toán phù hợp.

### 12.4. Đồ thị quyền truy cập

Một vai trò có thể kế thừa nhiều vai trò khác. CTE đệ quy có thể mở rộng các quyền kế thừa, nhưng khóa cycle có thể cần gồm cả role và context/tenant nếu trạng thái quyền phụ thuộc ngữ cảnh. Không dùng `CYCLE role_id` một cách máy móc khi cùng role trong hai context là hai trạng thái nghiệp vụ khác nhau.

## 13. Hiệu năng và kiểm soát số hàng

Đệ quy có thể mở rộng rất nhanh. Một nút có nhiều con và các cấp sau tiếp tục phân nhánh sẽ tạo số đường đi lớn, đặc biệt với đồ thị nhiều-nhiều.

Các nguyên tắc thiết kế:

1. **Bắt đầu từ đúng root**: anchor quá rộng có thể làm số hàng tăng mạnh ngay từ vòng đầu.
2. **Có index cho cạnh mở rộng**: truy vấn recursive thường tìm cạnh theo `PARENT_ID`; cân nhắc index phù hợp trên `LAB_ORG_EDGES(PARENT_ID)`. Primary key `(PARENT_ID, CHILD_ID)` trong lab đã hỗ trợ prefix này.
3. **Mang theo cột cần thiết**: không đưa các payload lớn vào mỗi vòng nếu không cần.
4. **Đặt giới hạn độ sâu khi có yêu cầu nghiệp vụ**: `WHERE parent.depth_no < :max_depth` trong recursive member.
5. **Xác định cycle key đúng**: khóa quá rộng có thể bỏ sót chu trình theo nghĩa nghiệp vụ; khóa quá hẹp có thể đánh dấu nhầm.
6. **Phân biệt node với path**: cùng node có thể xuất hiện qua nhiều path. Nếu chỉ cần node duy nhất, cần một bước chọn/aggregate ngoài CTE.
7. **Xem execution plan và số hàng thực tế**: không dự đoán hiệu năng chỉ từ độ sâu nhìn thấy của dữ liệu.

Có thể xem kế hoạch dự kiến:

```sql
EXPLAIN PLAN FOR
WITH org_walk (node_id, depth_no) AS (
    SELECT node_id, 0
    FROM lab_org_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT e.child_id, w.depth_no + 1
    FROM org_walk w
    JOIN lab_org_edges e
      ON e.parent_id = w.node_id
)
SEARCH DEPTH FIRST BY node_id SET dfs_order
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
SELECT node_id, depth_no, cycle_flag
FROM org_walk
ORDER BY dfs_order;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` là kế hoạch dự kiến. Với workload thật, DBA có thể cần cursor plan, runtime statistics, logical I/O và số hàng từng bước để xác định recursive expansion có tạo cardinality lớn hay không.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Lỗi khi khai báo recursive WITH | Thiếu alias list hoặc số cột hai nhánh không khớp | Khai báo alias list, đối chiếu từng cột anchor/recursive |
| Query không dừng | Điều kiện recursive member tiếp tục sinh hàng | Kiểm tra join, điều kiện dừng và cycle key |
| ORA-32044 | Oracle phát hiện cycle khi không có CYCLE clause | Xác định chu trình, khai báo CYCLE phù hợp hoặc sửa dữ liệu/điều kiện |
| Hàng cùng NODE_ID xuất hiện nhiều lần | Nút được tới qua nhiều đường hợp lệ | Xác định cần liệt kê path hay node duy nhất |
| SEARCH khai báo nhưng kết quả không theo thứ tự mong muốn | Không ORDER BY ordering column | Sắp xếp query ngoài bằng cột SET |
| DEPTH FIRST/BREADTH FIRST không loại hàng lặp | SEARCH chỉ tạo thứ tự, không phát hiện cycle | Dùng CYCLE để đánh dấu đường đi quay lại tổ tiên |
| CYCLE đánh dấu một hàng không mong đợi | Chọn cycle key quá rộng hoặc quá hẹp | Xác định định nghĩa trạng thái lặp của nghiệp vụ |
| Cycle row vẫn hiển thị | CYCLE đánh dấu chứ không tự loại hàng | Lọc cycle mark ở query ngoài nếu báo cáo không cần hàng đó |
| Dùng DISTINCT trong recursive member | Recursive member không cho phép DISTINCT | Xử lý loại trùng ở query ngoài theo quy tắc nghiệp vụ |
| Đặt GROUP BY trong recursive member | Recursive member không cho phép GROUP BY/aggregate | Tổng hợp ở query block bên ngoài |
| Dùng outer join với recursive query name ở phía phải | Vi phạm giới hạn recursive member | Viết lại phép mở rộng bằng inner join hoặc tổ chức query block khác |
| Path bị lỗi/đụng giới hạn độ dài | Chuỗi path tăng theo mỗi cấp | CAST kiểu phù hợp, giới hạn độ sâu hoặc dùng thiết kế lưu path khác |
| Nhầm SEARCH với thứ tự thực thi vật lý | Cột ordering là cơ chế sắp kết quả | Dùng ORDER BY ordering column; phân biệt execution plan |

## 15. Bài tập thực hành

Sử dụng `LAB_ORG_NODES` và `LAB_ORG_EDGES` trong mục 3.

### Bài 1 — Duyệt cây từ root

Viết recursive CTE bắt đầu từ node 1, trả về `NODE_ID`, `NODE_NAME`, `DEPTH_NO`. Không cần path. Giải thích anchor member và recursive member tạo ra từng tầng như thế nào.

### Bài 2 — Thêm đường đi

Chạy truy vấn với `UNION ALL` và `SEARCH DEPTH FIRST BY node_id SET dfs_order`. Xác định vì sao node 4 xuất hiện hai lần. Đổi thành `BREADTH FIRST`, so sánh thứ tự theo tầng.

### Bài 3 — Tạo path

Thêm `PATH_TXT` bắt đầu từ ID root và nối ID con ở mỗi vòng. Trả về path cho hai lần đi tới node 4. Giải thích tại sao cùng node có thể có hai path.

### Bài 4 — Tạo cycle

Chèn cạnh `5 -> 1`, chạy recursive CTE có:

```sql
CYCLE node_id SET cycle_flag TO 'Y' DEFAULT 'N'
```

Tìm hàng được đánh dấu Y và giải thích vì sao recursive member không tiếp tục mở rộng từ hàng đó.

### Bài 5 — Phân biệt cycle với nhiều đường đi

Trước khi chèn cạnh cycle, node 4 xuất hiện hai lần. Giải thích vì sao `CYCLE node_id` không đánh dấu lần đi thứ hai tới node 4 là cycle. Sau đó so sánh với đường đi `1 -> 2 -> 4 -> 5 -> 1`.

### Bài 6 — Chỉ lấy hàng không cycle

Dùng query ngoài `WHERE cycle_flag = 'N'`. So sánh kết quả với truy vấn vẫn giữ cả hàng cycle để phục vụ chẩn đoán.

### Bài 7 — Giới hạn độ sâu

Thêm bind `:max_depth` và điều kiện trong recursive member:

```sql
WHERE parent.depth_no < :max_depth
```

Chạy với độ sâu 1, 2, 3. Ghi rõ giới hạn này cắt những nhánh nào và vì sao nó không thay thế cycle detection.

### Bài 8 — Thiết kế cycle key ghép

Giả sử một node có thể được duyệt theo hai trạng thái `READ` và `WRITE`. Thiết kế alias list có `NODE_ID` và `ACCESS_MODE`, rồi giải thích khi nào `CYCLE NODE_ID` là đủ và khi nào cần `CYCLE NODE_ID, ACCESS_MODE`.

## 16. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi đã hoàn thành bài tập:

```sql
DROP TABLE lab_org_edges PURGE;
DROP TABLE lab_org_nodes PURGE;
```

Xóa bảng cạnh trước bảng nút vì có foreign key tham chiếu. Nếu bạn đã tạo thêm bảng khác trong bài thực hành, xóa đúng những bảng đó theo thứ tự phụ thuộc. `PURGE` bỏ qua recycle bin; không dùng với bảng của người khác hoặc dữ liệu cần khôi phục.

## Tổng kết

Recursive subquery factoring dùng một query block `WITH` tự tham chiếu để mở rộng dữ liệu nhiều cấp. **Anchor member** tạo điểm bắt đầu; **recursive member** tạo bước kế tiếp và được nối với anchor bằng `UNION ALL`. Alias list định nghĩa các cột của query; hai nhánh phải trả số cột và kiểu tương thích.

`SEARCH DEPTH FIRST` và `SEARCH BREADTH FIRST` tạo cột thứ tự cho cách duyệt; muốn kết quả hiển thị theo thứ tự đó phải `ORDER BY` cột do `SET` khai báo. `CYCLE` xác định các cột nhận diện trạng thái lặp trên đường đi, đánh dấu hàng gây cycle và ngừng mở rộng từ hàng đó, trong khi các nhánh không cycle vẫn tiếp tục. Cycle là quan hệ với **tổ tiên trên cùng đường đi**, không phải chỉ là một node xuất hiện nhiều lần trong toàn bộ kết quả.

Khi thiết kế truy vấn phân cấp hoặc đồ thị, hãy xác định root, grain của một hàng, ý nghĩa path, cycle key và thứ tự duyệt trước khi viết SQL. Kết hợp các quy tắc này với kiểm soát độ sâu, index cạnh và execution plan để recursive query vừa đúng nghiệp vụ vừa có thể vận hành ổn định.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — SELECT, Recursive Subquery Factoring (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — anchor/recursive member, giới hạn recursive member, SEARCH và CYCLE.
- [Oracle Database SQL Language Reference — SELECT (26ai)](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/SELECT.html) — đối chiếu cú pháp recursive subquery factoring trên release mới hơn.
- [Oracle Database Error Messages (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/ORA-32000.html) — tra lỗi ORA-32044 khi phát hiện cycle trong recursive WITH query.
- [Oracle Database SQL Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — optimizer, execution plan và phân tích hiệu năng.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu SQL Language Reference đúng phiên bản, nhất là giới hạn recursive member, cycle detection và các quy tắc của SEARCH/CYCLE.
