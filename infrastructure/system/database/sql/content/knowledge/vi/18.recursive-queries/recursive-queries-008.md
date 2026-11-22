# Giới hạn độ sâu, kiểu cột và kích thước kết quả

**Truy vấn đệ quy** trong SQL thường được sử dụng để duyệt cấu trúc phân cấp như phòng ban, danh mục sản phẩm, chuỗi quản lý, sơ đồ phụ thuộc hoặc các cạnh của một đồ thị. Cú pháp **WITH RECURSIVE** cho phép kết quả ở bước trước được dùng để tìm các hàng ở bước sau, cho đến khi không còn hàng nào cần mở rộng.

Chính khả năng tiếp tục mở rộng này khiến truy vấn đệ quy khác các truy vấn thông thường về **tài nguyên và độ an toàn**. Một câu SQL có thể chạy hợp lệ nhưng sinh hàng triệu kết quả vì phân nhánh; có thể lặp mãi khi gặp chu trình; hoặc thất bại do kiểu dữ liệu của cột dẫn xuất không đủ chỗ chứa đường dẫn ngày càng dài.

Bài học tập trung vào ba câu hỏi:

1. **Giới hạn độ sâu:** làm thế nào dừng sau một số cấp xác định, tránh sai lệch một cấp và nhận biết kết quả bị cắt?
2. **Kiểu cột:** kiểu dữ liệu của cột trong phần gốc và phần đệ quy cần tương thích ra sao, và xử lý chuỗi đường dẫn, số cấp, mảng các nút đã thăm thế nào?
3. **Kích thước kết quả:** vì sao giới hạn độ sâu chưa đủ để kiểm soát số dòng, và những chiến lược nào giúp tránh kết quả bùng nổ?

Bài học thuộc chương **Truy vấn đệ quy** của module **Database SQL**. Phần thực hành chính dùng **PostgreSQL 15 trở lên**, với hai bộ dữ liệu tạm độc lập. Phần đối chiếu đề cập **SQL Server**, **MySQL 8.0**, **SQLite** và **Oracle Database**; các hệ có cú pháp và cơ chế giới hạn khác nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cách **anchor member** và **recursive member** phối hợp trong một CTE đệ quy.
2. Viết điều kiện **WHERE w.depth < max_depth** tại đúng vị trí để giới hạn độ sâu.
3. Phân biệt **số bước mở rộng** với **số cấp được hiển thị**, tránh lỗi vượt giới hạn một cấp.
4. Phát hiện và tránh **chu trình** bằng mảng đường đi hoặc tính năng **CYCLE** của PostgreSQL.
5. Chọn kiểu dữ liệu phù hợp cho cột **depth**, **path_text**, **path_ids**, mã định danh và tổng số dẫn xuất.
6. Hiểu khác biệt giữa **LIMIT ở SELECT ngoài** và **điều kiện dừng trong recursive member**.
7. Ước lượng mức bùng nổ số hàng khi mỗi nút có nhiều nhánh.
8. Dùng chiến lược lọc, chỉ mục, thời gian chạy, số lượng kết quả và thiết kế truy vấn để kiểm soát chi phí.
9. Đổi cú pháp giới hạn đệ quy giữa PostgreSQL, SQL Server, MySQL và SQLite mà không nhầm các tham số đặc thù.

## 2. Nhắc lại cơ chế WITH RECURSIVE

Một CTE đệ quy thông thường gồm hai phần:

~~~sql
WITH RECURSIVE walk AS (
    -- Phần gốc (anchor): những hàng bắt đầu.
    SELECT ...

    UNION ALL

    -- Phần đệ quy: tìm hàng mới từ các hàng đã có.
    SELECT ...
    FROM some_table AS next_node
    JOIN walk AS previous_step
        ON ...
    WHERE ...
)
SELECT ...
FROM walk;
~~~

**Anchor** chọn hàng khởi đầu; **recursive member** dùng kết quả trung gian để tạo ra hàng mới. Với PostgreSQL, cách hiểu thực thi theo từng vòng là:

~~~text
Anchor: tạo tập hàng ban đầu
       │
       ▼
Working set: các hàng vừa có ở vòng hiện tại
       │
       ▼
Recursive member: mở rộng sang những hàng kế tiếp
       │
       ├── Có hàng mới? ──► đưa chúng vào vòng kế
       │
       └── Không còn hàng mới ──► dừng
                                  │
                                  ▼
                         Kết quả các vòng
~~~

Khi dùng **UNION ALL**, các hàng phát sinh không bị loại trùng tự động. Truy vấn có thể sinh lại một nút nhiều lần vì có nhiều đường đi tới nút đó, hoặc vì một chu trình dẫn trở lại nút cũ.

**Điều kiện dừng là một phần của thiết kế**, không chỉ là một tùy chọn tối ưu hiệu năng. Với dữ liệu có chu trình, recursive member không có biện pháp hạn chế có thể liên tục tạo thêm hàng và không đạt trạng thái “không còn hàng mới”.

### Ví dụ tối giản: đếm từ 1 đến 5

~~~sql
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
~~~

Kết quả là **1, 2, 3, 4, 5**. Khi n = 5, điều kiện **n < 5** là FALSE, nên không sinh n = 6. Phần WHERE trong recursive member **chặn việc sinh hàng tiếp theo**; nó không chỉ ẩn hàng số 6 khỏi kết quả.

## 3. Dữ liệu thực hành: cây đơn vị tổ chức

Tạo bảng tạm **demo_org_units**. Mỗi đơn vị có mã **unit_id**, mã đơn vị cha **parent_id** và tên **unit_name**. Một đơn vị gốc có parent_id = NULL.

~~~sql
CREATE TEMP TABLE demo_org_units (
    unit_id   INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES demo_org_units(unit_id),
    unit_name TEXT NOT NULL,
    CHECK (unit_id IS DISTINCT FROM parent_id)
);

INSERT INTO demo_org_units (unit_id, parent_id, unit_name)
VALUES
    ( 1, NULL, 'Cong ty'),
    ( 2,    1, 'Kinh doanh'),
    ( 3,    1, 'Ky thuat'),
    ( 4,    2, 'Kenh online'),
    ( 5,    2, 'Kenh offline'),
    ( 6,    3, 'Nen tang'),
    ( 7,    4, 'Doi so lieu'),
    ( 8,    7, 'Pipeline'),
    ( 9, NULL, 'Van phong dai dien'),
    (10,    9, 'Hanh chinh');
~~~

Sơ đồ cây:

~~~text
1 Cong ty                         9 Van phong dai dien
├── 2 Kinh doanh                  └── 10 Hanh chinh
│   ├── 4 Kenh online
│   │   └── 7 Doi so lieu
│   │       └── 8 Pipeline
│   └── 5 Kenh offline
└── 3 Ky thuat
    └── 6 Nen tang
~~~

Trong sơ đồ, **1 và 9** là hai gốc độc lập. Mỗi hàng có tối đa **một cha**, nhưng một hàng cha có thể có **nhiều con**.

Kiểm tra dữ liệu:

~~~sql
SELECT unit_id, parent_id, unit_name
FROM demo_org_units
ORDER BY unit_id;
~~~

> Bảng tạm chỉ tồn tại trong phiên kết nối hiện tại. Nếu cần chạy lại CREATE TEMP TABLE ở cùng phiên, hãy dùng phiên mới hoặc xóa riêng bảng tạm của bài. Không thay đổi những bảng nghiệp vụ đang dùng.

## 4. Tính độ sâu: gốc = 0, con trực tiếp = 1

Ta quy ước:

- Đơn vị bắt đầu (gốc của phép duyệt) có **depth = 0**.
- Con trực tiếp của gốc có **depth = 1**.
- Cháu có **depth = 2**, và cứ tiếp tục.

Truy vấn:

~~~sql
WITH RECURSIVE org_walk (
    unit_id, parent_id, unit_name, depth
) AS (
    SELECT
        u.unit_id,
        u.parent_id,
        u.unit_name,
        0 AS depth
    FROM demo_org_units AS u
    WHERE u.unit_id = 1

    UNION ALL

    SELECT
        c.unit_id,
        c.parent_id,
        c.unit_name,
        w.depth + 1
    FROM demo_org_units AS c
    JOIN org_walk AS w
        ON c.parent_id = w.unit_id
)
SELECT unit_id, parent_id, unit_name, depth
FROM org_walk
ORDER BY depth, unit_id;
~~~

Với dữ liệu **cây không có chu trình** này, truy vấn trả **8 hàng** dưới đơn vị gốc 1:

| unit_id | unit_name | depth |
| ---: | --- | ---: |
| 1 | Cong ty | 0 |
| 2 | Kinh doanh | 1 |
| 3 | Ky thuat | 1 |
| 4 | Kenh online | 2 |
| 5 | Kenh offline | 2 |
| 6 | Nen tang | 2 |
| 7 | Doi so lieu | 3 |
| 8 | Pipeline | 4 |

Đơn vị 9 và 10 không xuất hiện vì chúng thuộc một cây khác và truy vấn bắt đầu từ **unit_id = 1**.

**Lưu ý về độ sâu:** depth là một **giá trị do câu SQL tự tính**, không phải một cột bắt buộc có sẵn trong bảng. Một số dự án đặt gốc = 1 thay vì 0. Hai quy ước đều có thể dùng, nhưng phải thống nhất khi viết điều kiện giới hạn và diễn giải báo cáo.

## 5. Giới hạn độ sâu ngay trong recursive member

Muốn chỉ hiển thị **gốc cùng các hậu duệ sâu tối đa 2 cạnh**, viết:

~~~sql
WITH RECURSIVE org_walk(unit_id, parent_id, unit_name, depth) AS (
    SELECT
        unit_id, parent_id, unit_name, 0 AS depth
    FROM demo_org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT
        c.unit_id,
        c.parent_id,
        c.unit_name,
        w.depth + 1
    FROM demo_org_units AS c
    JOIN org_walk AS w
        ON c.parent_id = w.unit_id
    WHERE w.depth < 2
)
SELECT unit_id, unit_name, depth
FROM org_walk
ORDER BY depth, unit_id;
~~~

Kết quả gồm **6 hàng** ở các mức 0, 1, 2:

~~~text
depth 0: 1
depth 1: 2, 3
depth 2: 4, 5, 6
~~~

Không có hàng depth 3 vì recursive member **không được mở rộng từ một hàng đã ở depth = 2**.

### 5.1. Vì sao WHERE w.depth < 2 vẫn sinh được depth = 2?

Ở recursive member, điều kiện được kiểm tra trên **hàng cha w**, trước khi biểu thức **w.depth + 1** tạo hàng con.

| depth của hàng cha | w.depth < 2 | Có sinh con? | depth của con nếu sinh |
| ---: | --- | --- | ---: |
| 0 | TRUE | Có | 1 |
| 1 | TRUE | Có | 2 |
| 2 | FALSE | Không | — |

Do đó, với quy ước gốc 0, công thức phổ biến là:

~~~sql
WHERE w.depth < max_depth
~~~

để kết quả có **depth tối đa bằng max_depth**.

### 5.2. Bẫy vượt một cấp

Nếu viết:

~~~sql
WHERE w.depth <= 2
~~~

thì ngay cả hàng có depth = 2 cũng được mở rộng, có thể sinh **depth = 3**. Với dữ liệu ví dụ, đơn vị 7 sẽ xuất hiện. Đây là lỗi **off-by-one** rất thường gặp khi độ sâu là dữ liệu tự tăng trong recursive member.

Nếu muốn quy ước **gốc là cấp 1**, hãy bắt đầu depth = 1 và điều chỉnh giới hạn sao cho nhất quán. Ví dụ cấp tối đa 3 với gốc = 1 cũng dùng **WHERE w.depth < 3**, nhưng ý nghĩa số lượng cạnh được duyệt chỉ là 2.

### 5.3. Giới hạn trong recursive member khác lọc sau khi đệ quy

Hai cách sau không có cùng ý nghĩa về tài nguyên:

~~~sql
-- Cách A: giới hạn khi sinh hàng, phù hợp để chặn độ sâu.
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1, 0
    UNION ALL
    SELECT c.unit_id, w.depth + 1
    FROM demo_org_units AS c
    JOIN walk AS w ON c.parent_id = w.node_id
    WHERE w.depth < 2
)
SELECT * FROM walk;
~~~

~~~sql
-- Cách B: chỉ lọc kết quả sau khi phép đệ quy đã được định nghĩa.
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1, 0
    UNION ALL
    SELECT c.unit_id, w.depth + 1
    FROM demo_org_units AS c
    JOIN walk AS w ON c.parent_id = w.node_id
)
SELECT *
FROM walk
WHERE depth <= 2;
~~~

Cách B **không đặt điều kiện dừng trong phần đệ quy**. Bộ tối ưu có thể xử lý một số điều kiện theo kế hoạch riêng, nhưng ta **không nên coi WHERE ở SELECT cuối là giới hạn an toàn cho số vòng đệ quy**. Đặc biệt với đồ thị có chu trình, một điều kiện chỉ ẩn dòng ngoài cùng không đủ bảo đảm truy vấn dừng.

**Quy tắc thực hành:** điều kiện giới hạn độ sâu phải nằm **trong nhánh tạo hàng tiếp theo**.

## 6. Truy vấn kết quả có bị cắt không?

Giới hạn độ sâu không chỉ là quyết định kỹ thuật; nó còn thay đổi **ý nghĩa báo cáo**. Nếu giới hạn ở depth = 2, người đọc có thể nghĩ danh sách chỉ có 6 đơn vị, trong khi thực tế cây dưới gốc 1 có thêm đơn vị 7 và 8.

Có thể đánh dấu những hàng ở **ranh giới giới hạn** mà vẫn còn con:

~~~sql
WITH RECURSIVE org_walk(unit_id, parent_id, depth) AS (
    SELECT unit_id, parent_id, 0 AS depth
    FROM demo_org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT c.unit_id, c.parent_id, w.depth + 1
    FROM demo_org_units AS c
    JOIN org_walk AS w ON c.parent_id = w.unit_id
    WHERE w.depth < 2
)
SELECT
    w.unit_id,
    w.depth,
    EXISTS (
        SELECT 1
        FROM demo_org_units AS c
        WHERE c.parent_id = w.unit_id
    ) AS has_children,
    CASE
        WHEN w.depth = 2
         AND EXISTS (
             SELECT 1
             FROM demo_org_units AS c
             WHERE c.parent_id = w.unit_id
         )
        THEN 'Con nhanh chua duoc mo rong'
        ELSE NULL
    END AS depth_warning
FROM org_walk AS w
ORDER BY w.depth, w.unit_id;
~~~

Ở depth = 2, **đơn vị 4** có con là đơn vị 7, nên nhận cảnh báo chưa mở rộng hết. Đơn vị 5 và 6 không có con nên không nhận cảnh báo.

Nếu hiển thị kết quả cho người dùng, nên phân biệt:

- **Không có hậu duệ:** cây đã kết thúc thật.
- **Còn hậu duệ nhưng bị giới hạn độ sâu:** kết quả chỉ là **một lát cắt** của cây.
- **Bị dừng vì giới hạn thời gian hoặc lỗi:** kết quả không nên âm thầm được xem như một cây đầy đủ.

Trong bộ dữ liệu cây cha-con, EXISTS kiểm tra “có con trực tiếp trong bảng” là đủ cho cảnh báo trên. Với một đồ thị có nhiều cạnh và điều kiện lọc phức tạp, khái niệm “còn nút có thể mở rộng” cần kiểm tra **đúng tập cạnh đủ điều kiện**, không chỉ có một cạnh bất kỳ.

## 7. Một cây có nhiều gốc: giới hạn theo từng đường đi

Nếu muốn duyệt **tất cả các đơn vị gốc**:

~~~sql
WITH RECURSIVE org_walk (
    root_id, unit_id, parent_id, unit_name, depth
) AS (
    SELECT
        u.unit_id AS root_id,
        u.unit_id,
        u.parent_id,
        u.unit_name,
        0 AS depth
    FROM demo_org_units AS u
    WHERE u.parent_id IS NULL

    UNION ALL

    SELECT
        w.root_id,
        c.unit_id,
        c.parent_id,
        c.unit_name,
        w.depth + 1
    FROM org_walk AS w
    JOIN demo_org_units AS c
        ON c.parent_id = w.unit_id
    WHERE w.depth < 2
)
SELECT root_id, unit_id, unit_name, depth
FROM org_walk
ORDER BY root_id, depth, unit_id;
~~~

Kết quả có:

- Gốc 1: các đơn vị **1, 2, 3, 4, 5, 6** (depth 0–2).
- Gốc 9: các đơn vị **9, 10** (depth 0–1).

Cột **root_id** giúp giữ thông tin “đơn vị này thuộc cây nào”. Khi có nhiều gốc, điều kiện **w.depth < 2** áp dụng riêng trên từng đường đi khởi đầu từ mỗi gốc, chứ không có một bộ đếm vòng chung cho toàn bộ câu lệnh.

Đối với một **đồ thị tổng quát**, cùng một nút có thể được đi tới từ nhiều gốc hoặc nhiều nhánh. Khi đó kết quả có thể chứa nhiều hàng cùng node_id với root_id/path khác nhau; điều này có thể là chủ ý hoặc là nguyên nhân tạo kết quả rất lớn.

## 8. Chu trình: lý do giới hạn độ sâu chưa phải lời giải đầy đủ

Một **chu trình** (*cycle*) xuất hiện khi có đường đi quay lại nút đã nằm trên chính đường ấy:

~~~text
2 ──► 4 ──► 2 ──► 4 ──► ...
~~~

Nếu recursive member chỉ duyệt cạnh tiếp theo bằng UNION ALL, hai nút này có thể tiếp tục tạo hàng ở mọi cấp. Điều kiện giới hạn depth sẽ chặn sau một số bước, nhưng vẫn có thể tạo **nhiều bản sao của đường đi vòng** và không phản ánh đúng tập nút có thể duyệt.

### 8.1. Tạo đồ thị mẫu có chu trình và nhiều đường đi

Ta dùng bảng cạnh riêng **demo_graph_edges**, không sửa cây đơn vị tổ chức:

~~~sql
CREATE TEMP TABLE demo_graph_edges (
    from_id INTEGER NOT NULL,
    to_id   INTEGER NOT NULL,
    PRIMARY KEY (from_id, to_id)
);

INSERT INTO demo_graph_edges(from_id, to_id)
VALUES
    (1, 2),
    (1, 3),
    (2, 4),
    (3, 4),
    (3, 6),
    (4, 2),
    (4, 5);
~~~

Sơ đồ:

~~~text
    1
   / \
  2   3 ───► 6
  │   │
  ▼   ▼
  4 ◄─┘
  │ \
  │  └──► 5
  └──► 2  (quay về nút 2, tạo chu trình 2 → 4 → 2)
~~~

Hai đường **1 → 2 → 4** và **1 → 3 → 4** đều đi tới nút 4. Ngoài ra, cạnh 4 → 2 tạo chu trình cùng cạnh 2 → 4.

### 8.2. Có giới hạn depth nhưng vẫn đi vòng

~~~sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1, 0

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN demo_graph_edges AS e
        ON e.from_id = w.node_id
    WHERE w.depth < 5
)
SELECT node_id, depth
FROM walk
ORDER BY depth, node_id;
~~~

Câu này dừng nhờ **depth < 5**, nhưng có thể tạo những đường lặp như **1 → 2 → 4 → 2 → 4**. Việc “dừng” không đồng nghĩa các hàng đều thuộc đường đi hợp lệ theo yêu cầu “không lặp nút trong một đường”.

Nếu không có depth cap hoặc cơ chế chống chu trình, đường 2 ↔ 4 có thể khiến truy vấn sinh hàng không dừng. **Không nên thử câu đệ quy không giới hạn trên dữ liệu đã biết có chu trình**, đặc biệt trong môi trường chia sẻ.

## 9. Chống chu trình bằng danh sách nút đã thăm của đường hiện tại

Trong PostgreSQL, có thể lưu **mảng INTEGER[]** mô tả những node_id trên đường đi. Trước khi thêm nút kế tiếp, kiểm tra nó **chưa xuất hiện trong mảng**.

~~~sql
WITH RECURSIVE paths(node_id, depth, path_ids) AS (
    SELECT
        1 AS node_id,
        0 AS depth,
        ARRAY[1]::INTEGER[] AS path_ids

    UNION ALL

    SELECT
        e.to_id,
        p.depth + 1,
        p.path_ids || e.to_id
    FROM paths AS p
    JOIN demo_graph_edges AS e
        ON e.from_id = p.node_id
    WHERE p.depth < 5
      AND NOT (e.to_id = ANY(p.path_ids))
)
SELECT node_id, depth, path_ids
FROM paths
ORDER BY depth, path_ids;
~~~

Giải thích:

1. Anchor bắt đầu tại node_id = 1, depth = 0, path_ids = **{1}**.
2. Mỗi lần mở rộng, nối to_id vào cuối path_ids.
3. Biểu thức **e.to_id = ANY(p.path_ids)** kiểm tra nút kế tiếp đã có trên đường đi chưa.
4. **NOT (...)** chỉ cho phép mở rộng nếu nút kế tiếp **chưa xuất hiện**.
5. Điều kiện **p.depth < 5** vẫn tồn tại như một **ngân sách độ sâu riêng**.

Như vậy, đường **1 → 2 → 4 → 2** bị chặn tại bước định quay lại 2. Tuy nhiên, nút 4 vẫn có thể xuất hiện theo **hai đường hợp lệ khác nhau**:

~~~text
1 → 2 → 4
1 → 3 → 4
~~~

**Chống chu trình trên một đường đi không đồng nghĩa chỉ trả mỗi node_id đúng một lần trong toàn kết quả.** Nếu nghiệp vụ chỉ muốn tập nút có thể tới được, thay vì liệt kê mọi đường đi, cách biểu diễn và chiến lược loại trùng sẽ khác.

### 9.1. Vì sao không chỉ dùng NOT EXISTS trên kết quả CTE để biết “đã thăm”?

Trong PostgreSQL, recursive member có những quy tắc cụ thể về cách tham chiếu CTE đệ quy; không thể đơn giản dùng một tập “mọi nút đã thăm của tất cả vòng” như một biến toàn cục có thể cập nhật tùy ý. Mảng **path_ids** là trạng thái của **từng đường đi**, giúp kiểm tra chu trình cục bộ.

Nếu cần loại trùng theo **node_id trên toàn bộ đồ thị**, một cách đơn giản cho bài toán **chỉ tìm tập nút đến được** là **UNION** trên một cột node_id, như phần 11. Với đồ thị lớn, có thể cần chiến lược duyệt, bảng trạng thái hoặc xử lý ở ứng dụng phù hợp hơn.

### 9.2. Mảng đường đi cũng có chi phí

Mỗi hàng kết quả mang theo một mảng dài theo số nút của đường đó. Ở độ sâu lớn, mảng có thể tốn đáng kể bộ nhớ và chi phí sao chép. Do đó:

- Chỉ lưu **định danh cần thiết** để phát hiện chu trình.
- Đặt **giới hạn độ sâu hợp lý** dù đã chặn chu trình.
- Không xuất path_ids cho mọi hàng nếu ứng dụng chỉ cần node_id.
- Cân nhắc mức độ phân nhánh và số đường đi hợp lệ, không chỉ chiều dài mỗi đường.

## 10. CYCLE của PostgreSQL: phát hiện chu trình bằng cú pháp tích hợp

PostgreSQL **14 trở lên** hỗ trợ mệnh đề **CYCLE** cho CTE đệ quy. Nó có thể tự xây dựng thông tin đường đi và một cờ đánh dấu hàng đóng chu trình.

~~~sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1, 0

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN demo_graph_edges AS e
        ON e.from_id = w.node_id
    WHERE w.depth < 5
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT
    node_id,
    depth,
    is_cycle
FROM walk
ORDER BY depth, node_id, is_cycle;
~~~

Mệnh đề **CYCLE node_id SET is_cycle USING cycle_path** yêu cầu PostgreSQL theo dõi chu trình theo node_id. Hàng kết thúc một đường vòng được gắn cờ **is_cycle**; PostgreSQL không tiếp tục mở rộng từ hàng đã bị đánh dấu là tạo chu trình.

Nếu chỉ muốn các hàng **chưa đóng chu trình**, có thể lọc ở SELECT ngoài:

~~~sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1, 0
    UNION ALL
    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN demo_graph_edges AS e
        ON e.from_id = w.node_id
    WHERE w.depth < 5
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT node_id, depth
FROM walk
WHERE NOT is_cycle
ORDER BY depth, node_id;
~~~

**Hai giới hạn vẫn có vai trò khác nhau:**

- **CYCLE** ngăn một đường đi tiếp tục quay vòng qua nút đã có trên chính đường.
- **depth < 5** giới hạn **chiều dài đường đi**, kể cả khi đồ thị không có chu trình.

Với đồ thị nhiều nhánh, CYCLE không bảo đảm mỗi nút chỉ có một hàng trong đầu ra: nút 4 có thể được tìm thấy qua hai đường hợp lệ. Không nên coi CYCLE là một bộ lọc DISTINCT toàn cục.

### 10.1. Khi khóa chu trình gồm nhiều cột

Nếu một nút được định danh bằng **(tenant_id, node_id)** thay vì chỉ node_id, phải dùng **đủ các thành phần định danh** trong kiểm tra chu trình. Nếu chỉ theo node_id, một node_id giống nhau ở hai tenant khác nhau có thể bị nhận nhầm là cùng nút. Ngược lại, nếu thêm trường thay đổi theo mỗi bước như depth vào khóa chu trình, cùng một nút quay lại ở depth khác có thể không còn được nhận diện là trùng.

Vì vậy, cách chọn cột của CYCLE phải phản ánh **danh tính thực của nút trong đồ thị**.

## 11. UNION khác UNION ALL trong truy vấn đệ quy

**UNION ALL** giữ mọi hàng phát sinh. **UNION** loại những hàng trùng hoàn toàn theo **tất cả cột của CTE** khi tổng hợp các vòng kết quả.

Trong bài toán chỉ cần **danh sách node_id có thể đi tới**, một CTE với **duy nhất node_id** có thể dùng UNION:

~~~sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1

    UNION

    SELECT e.to_id
    FROM reachable AS r
    JOIN demo_graph_edges AS e
        ON e.from_id = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
~~~

Kết quả là các nút **1, 2, 3, 4, 5, 6**, mỗi nút một lần. Do chỉ có một cột node_id và đồ thị hữu hạn, việc UNION loại trùng giúp truy vấn dừng khi không còn node_id mới.

Nhưng nếu thêm depth vào kết quả:

~~~sql
-- Minh họa rủi ro; không nên chạy không giới hạn trên đồ thị có chu trình.
WITH RECURSIVE reachable(node_id, depth) AS (
    SELECT 1, 0

    UNION

    SELECT e.to_id, r.depth + 1
    FROM reachable AS r
    JOIN demo_graph_edges AS e
        ON e.from_id = r.node_id
)
SELECT * FROM reachable;
~~~

thì các hàng **(2,1)**, **(2,3)**, **(2,5)** khác nhau vì depth khác nhau. UNION **không còn giúp loại chu trình một cách đáng tin cậy**; quá trình có thể tiếp tục sinh hàng với depth tăng mãi.

**Bài học:** UNION không phải “bật công tắc chống vòng lặp” cho mọi CTE đệ quy. Nó chỉ loại các **hàng giống nhau theo toàn bộ danh sách cột**. Khi còn path, depth hoặc thông tin thay đổi mỗi bước, cần cơ chế dừng phù hợp khác.

## 12. Kiểu cột của CTE đệ quy được xác định thế nào?

Trong CTE đệ quy, cả hai vế của UNION ALL phải có **cùng số cột tương ứng** và các kiểu dữ liệu ở từng vị trí phải được hệ quản trị chấp nhận.

Ví dụ:

~~~sql
WITH RECURSIVE numbers(n, depth) AS (
    SELECT
        1::INTEGER,
        0::INTEGER

    UNION ALL

    SELECT
        n + 1,
        depth + 1
    FROM numbers
    WHERE depth < 5
)
SELECT n, depth
FROM numbers
ORDER BY depth;
~~~

Ở đây:

- Anchor trả **hai cột số nguyên**.
- Recursive member cũng trả **hai cột số nguyên**.
- Tên n và depth có thể được khai báo trong danh sách cột sau tên CTE.

Không hợp lệ về cấu trúc nếu anchor trả hai cột nhưng recursive member trả ba cột. Nếu hai vế có các kiểu không tương thích, câu lệnh cũng có thể lỗi ngay ở giai đoạn phân tích.

### 12.1. Chọn kiểu depth có giới hạn và mục đích rõ

Với cây thông thường, **INTEGER** thường đủ vì độ sâu hợp lệ được giới hạn rất nhỏ so với miền số nguyên. Có thể chọn **BIGINT** nếu thiết kế yêu cầu bộ đếm lớn:

~~~sql
WITH RECURSIVE numbers(n, depth) AS (
    SELECT
        1::BIGINT,
        0::BIGINT

    UNION ALL

    SELECT n + 1, depth + 1
    FROM numbers
    WHERE depth < 10
)
SELECT * FROM numbers
ORDER BY depth;
~~~

**BIGINT không giải quyết vấn đề đệ quy vô hạn.** Nó chỉ làm tăng miền giá trị có thể biểu diễn trước khi tràn số. Nếu bỏ điều kiện dừng, một CTE có thể tiêu tốn rất nhiều tài nguyên từ lâu trước khi chạm tới giới hạn BIGINT.

### 12.2. Kiểu số tổng hợp có thể cần độ chính xác khác khóa

Một CTE tính tổng trọng số dọc đường đi có thể có cột **running_total**. Không nên dùng một kiểu số nguyên quá nhỏ nếu trọng số cộng dồn có thể lớn, hoặc đổi toàn bộ sang FLOAT khi cần tính tiền chính xác:

~~~sql
WITH RECURSIVE steps(depth, running_amount) AS (
    SELECT
        0::INTEGER,
        0::NUMERIC(18, 2)

    UNION ALL

    SELECT
        depth + 1,
        running_amount + 250000::NUMERIC(18, 2)
    FROM steps
    WHERE depth < 5
)
SELECT depth, running_amount
FROM steps
ORDER BY depth;
~~~

Kết quả tăng từ 0 tới **1.250.000** sau 5 bước, giữ kiểu NUMERIC chính xác cho giá trị tiền. Trong hệ thống thật, cần chọn **precision và scale** theo miền dữ liệu và phép tính, không chỉ theo ví dụ.

### 12.3. NULL ở anchor cần kiểu tường minh khi có thể

Giả sử muốn thêm cột ghi chú hoặc đường dẫn ban đầu chưa biết:

~~~sql
SELECT
    unit_id,
    NULL::TEXT AS note_text
FROM demo_org_units
WHERE unit_id = 1;
~~~

**NULL::TEXT** nói rõ kết quả là NULL **của kiểu TEXT**. Trong truy vấn UNION và CTE đệ quy, việc ép kiểu tường minh giúp tránh suy luận kiểu không mong muốn; mức độ bắt buộc và quy tắc suy luận khác nhau theo phương ngữ.

## 13. Kiểu đường dẫn chuỗi: tránh tràn độ dài và nối sai

Một nhu cầu phổ biến là hiển thị **đường dẫn từ gốc đến nút**:

~~~text
Cong ty / Kinh doanh / Kenh online / Doi so lieu / Pipeline
~~~

Với PostgreSQL, có thể dùng kiểu **TEXT** ngay ở anchor:

~~~sql
WITH RECURSIVE org_paths (
    unit_id, parent_id, depth, path_text
) AS (
    SELECT
        unit_id,
        parent_id,
        0 AS depth,
        unit_name::TEXT AS path_text
    FROM demo_org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT
        c.unit_id,
        c.parent_id,
        p.depth + 1,
        p.path_text || ' / ' || c.unit_name
    FROM demo_org_units AS c
    JOIN org_paths AS p ON c.parent_id = p.unit_id
    WHERE p.depth < 4
)
SELECT unit_id, depth, path_text
FROM org_paths
ORDER BY depth, unit_id;
~~~

Đối với unit_id = 8, đường dẫn cuối là:

~~~text
Cong ty / Kinh doanh / Kenh online / Doi so lieu / Pipeline
~~~

Trong PostgreSQL, **TEXT** không có một giới hạn nhỏ cố định như VARCHAR(20); tuy vậy, dữ liệu chuỗi rất dài vẫn tiêu thụ bộ nhớ, dung lượng lưu trữ tạm, truyền qua mạng và công xử lý. Không nên cho rằng “TEXT không khai báo độ dài” đồng nghĩa **kích thước kết quả vô hạn và miễn phí**.

### 13.1. VARCHAR(n) quá ngắn có thể làm hỏng đệ quy

Nếu anchor tạo một giá trị kiểu VARCHAR có độ dài giới hạn quá ngắn, phần đệ quy có thể phải ghép thêm tên mới vượt giới hạn. Hệ quản trị có thể báo lỗi độ dài/kiểu, hoặc trong một số chế độ/phiên bản có hành vi cắt chuỗi cần tránh.

Ví dụ PostgreSQL chủ động ép chuỗi về kiểu có giới hạn:

~~~sql
-- Chỉ minh họa ý tưởng, không khuyến khích giới hạn 20 ký tự cho đường dẫn.
SELECT CAST('Cong ty / Kinh doanh / Kenh online' AS VARCHAR(20));
~~~

Với PostgreSQL, một phép **CAST tường minh sang VARCHAR(20)** có thể cắt phần dư theo quy tắc ép kiểu tường minh; hành vi ở một biểu thức gán vào cột VARCHAR(20) có thể là lỗi. Không dựa vào ép kiểu cắt dữ liệu để “giải quyết” vấn đề đường dẫn dài.

**Cách chọn kiểu nên bắt nguồn từ kích thước lớn nhất dự kiến** của chuỗi và chính sách khi vượt hạn mức. Đường dẫn phục vụ hiển thị có thể cần một giới hạn ứng dụng khác với đường dẫn dùng làm khóa nội bộ.

### 13.2. Kiểu TEXT của PostgreSQL và kiểu chuỗi của hệ khác

- **PostgreSQL:** TEXT hoặc VARCHAR không giới hạn độ dài khai báo thường thuận tiện cho path_text.
- **MySQL:** kiểu cột CTE đệ quy được **suy luận từ phần anchor**; thường cần CAST anchor sang độ dài đủ lớn trước khi dùng CONCAT trong recursive member.
- **SQL Server:** anchor và recursive member phải trả kiểu cột tương ứng **khớp chặt chẽ**, gồm những thuộc tính chuỗi như độ dài/kiểu Unicode trong những tình huống liên quan. Hãy CAST tường minh cùng kiểu.
- **SQLite:** cơ chế kiểu linh hoạt hơn, nhưng dữ liệu chuỗi vẫn chịu giới hạn kích thước và tài nguyên thực tế.

### 13.3. Đường dẫn dạng mảng tốt cho kiểm tra chu trình, dạng chuỗi tốt cho hiển thị

**path_text** biểu diễn một đường dẫn dễ đọc, nhưng không phải lựa chọn chắc chắn để phát hiện đã thăm node_id:

~~~text
1 / 12
11 / 2
~~~

Nếu kiểm tra bằng những phép tìm chuỗi đơn giản, mã nút có thể là một phần của mã nút khác hoặc ký tự phân cách có thể xuất hiện trong dữ liệu.

Với PostgreSQL, **ARRAY[unit_id]::INTEGER[]** và phép **= ANY(path_ids)** là cách rõ ràng hơn để xác định một mã nút đã có trên đường hiện tại. Khi cần xuất giao diện, có thể giữ cả **path_ids** và **path_text**, nhưng phải hiểu việc mang theo cả hai cột làm tăng kích thước mỗi hàng.

## 14. Giới hạn kiểu cột theo phương ngữ: ví dụ MySQL và SQL Server

Điểm này rất quan trọng khi chuyển cùng một truy vấn đệ quy giữa các hệ quản trị.

### 14.1. MySQL 8.0: anchor quyết định kiểu cột đầu ra

Trong MySQL, **kiểu cột của recursive CTE được suy luận dựa trên phần không đệ quy (anchor)**. Nếu anchor chỉ tạo chuỗi ngắn mà recursive member nối thêm nhiều tên, giá trị sau có thể vượt độ dài được suy luận.

Ví dụ dành cho **MySQL 8.0**, giả định bảng org_units có unit_id, parent_id, unit_name:

~~~sql
WITH RECURSIVE org_paths AS (
    SELECT
        unit_id,
        parent_id,
        0 AS depth,
        CAST(unit_name AS CHAR(500)) AS path_text
    FROM org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT
        c.unit_id,
        c.parent_id,
        p.depth + 1,
        CONCAT(p.path_text, ' / ', c.unit_name)
    FROM org_units AS c
    JOIN org_paths AS p ON c.parent_id = p.unit_id
    WHERE p.depth < 10
)
SELECT unit_id, depth, path_text
FROM org_paths;
~~~

**CAST(unit_name AS CHAR(500))** ở anchor giúp khai báo khoảng chứa dài hơn cho chuỗi đường dẫn. Giá trị 500 chỉ là ví dụ; cần chọn theo độ dài tên và mức sâu dự kiến. Nếu đường dẫn vượt độ dài đã chọn, truy vấn có thể lỗi cắt dữ liệu hoặc bị ảnh hưởng bởi chế độ xử lý, nên **CAST không thay thế giới hạn depth và kiểm soát chiều dài chuỗi**.

Không dùng cú pháp PostgreSQL **unit_name::TEXT** nguyên văn trên MySQL; cú pháp CAST khác.

### 14.2. SQL Server: kiểu anchor và recursive member cần khớp

Trong SQL Server, CTE đệ quy không dùng từ khóa **RECURSIVE** như PostgreSQL:

~~~sql
;WITH org_paths(unit_id, parent_id, depth, path_text) AS (
    SELECT
        unit_id,
        parent_id,
        CAST(0 AS INT),
        CAST(unit_name AS NVARCHAR(500))
    FROM dbo.org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT
        c.unit_id,
        c.parent_id,
        p.depth + 1,
        CAST(
            p.path_text + N' / ' + c.unit_name
            AS NVARCHAR(500)
        )
    FROM dbo.org_units AS c
    JOIN org_paths AS p ON c.parent_id = p.unit_id
    WHERE p.depth < 10
)
SELECT unit_id, depth, path_text
FROM org_paths
OPTION (MAXRECURSION 100);
~~~

Điểm cần nhớ:

- **NVARCHAR(500)** được khai báo nhất quán ở cả hai vế, phù hợp nếu cần chứa văn bản Unicode.
- SQL Server dùng **+** cho phép nối chuỗi trong ví dụ này, không phải toán tử **||** theo cách quen thuộc của PostgreSQL.
- **OPTION (MAXRECURSION 100)** là giới hạn thực thi đặc thù của SQL Server, đặt tại **câu lệnh SELECT ngoài cùng**, không chèn vào trong định nghĩa CTE.
- Bộ dữ liệu org_units là bảng giả định **dbo.org_units** của SQL Server; không chạy trực tiếp mẫu này trên bảng tạm PostgreSQL của phần 3.

SQL Server có thể báo lỗi khi kiểu dữ liệu của cột tương ứng trong anchor và recursive member không giống nhau; việc CAST nhất quán giúp tránh các lỗi độ dài và Unicode.

## 15. Giới hạn số vòng đệ quy của hệ quản trị không thay thế điều kiện nghiệp vụ

Có hai loại giới hạn cần phân biệt:

1. **Giới hạn độ sâu/ngữ nghĩa do người viết SQL chọn:** ví dụ chỉ duyệt từ gốc đến tối đa depth 4, bằng **WHERE w.depth < 4**.
2. **Giới hạn bảo vệ ở hệ quản trị:** ví dụ SQL Server dừng khi vượt **MAXRECURSION**, MySQL có biến hệ thống liên quan đến độ sâu đệ quy.

Một truy vấn có thể bị hệ quản trị ngắt ở mức giới hạn kỹ thuật dù dữ liệu thực sự vẫn còn nhiều cấp. Điều đó **không nên được hiểu là báo cáo đầy đủ**. Giới hạn bảo vệ giúp giảm rủi ro vận hành; giới hạn nghiệp vụ mới quyết định **phạm vi dữ liệu chủ đích**.

### 15.1. PostgreSQL

PostgreSQL không có cùng cú pháp **OPTION (MAXRECURSION n)** của SQL Server. Vì vậy, người viết thường dùng:

~~~sql
WHERE w.depth < 10
~~~

trong recursive member, kết hợp **CYCLE/kiểm tra path**, và có thể dùng giới hạn thời gian thực thi của phiên/giao dịch như **statement_timeout** để bảo vệ tài nguyên.

Ví dụ thực hiện truy vấn an toàn trong một giao dịch thực hành:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '5s';

WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1, 0
    UNION ALL
    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN demo_graph_edges AS e ON e.from_id = w.node_id
    WHERE w.depth < 5
)
SELECT COUNT(*) AS result_rows
FROM walk;

COMMIT;
~~~

**SET LOCAL** chỉ có hiệu lực trong giao dịch hiện tại. Nếu câu lệnh bị timeout, giao dịch có thể chuyển sang trạng thái lỗi và cần **ROLLBACK** thay vì COMMIT để kết thúc sạch. Thời gian 5 giây là ví dụ, không phải giá trị mặc định nên dùng trong mọi hệ.

**statement_timeout ngăn truy vấn chạy quá lâu theo cấu hình**, nhưng không thay thế việc viết điều kiện dừng có thể chứng minh đúng về nghiệp vụ.

### 15.2. SQL Server: MAXRECURSION

SQL Server thường có giới hạn mặc định **100 mức đệ quy** cho câu truy vấn đệ quy. Có thể dùng query hint:

~~~sql
OPTION (MAXRECURSION 200)
~~~

giới hạn tối đa **200** mức đệ quy theo cơ chế SQL Server. Phạm vi giá trị khi khai báo tùy chọn là **0 tới 32767**; **0** có nghĩa **không áp giới hạn MAXRECURSION**, không phải “không cho phép đệ quy”.

Ví dụ công thức:

~~~sql
;WITH n(x) AS (
    SELECT 1
    UNION ALL
    SELECT x + 1 FROM n WHERE x < 150
)
SELECT MAX(x) AS max_x
FROM n
OPTION (MAXRECURSION 200);
~~~

Kết quả là **150** vì câu lệnh có điều kiện dừng nghiệp vụ trước mức 200. Nếu đặt MAXRECURSION quá thấp, hệ quản trị có thể hủy câu lệnh khi đạt hạn mức. **Không dùng MAXRECURSION 0 chỉ để né lỗi** mà chưa hiểu vì sao truy vấn cần nhiều cấp hoặc có chu trình.

### 15.3. MySQL 8.0: cte_max_recursion_depth

MySQL 8.0 có biến **cte_max_recursion_depth**, thường mặc định là **1000**, dùng để giới hạn số vòng mở rộng đệ quy. Trong một phiên được phép thay đổi cấu hình:

~~~sql
-- MySQL 8.0, không chạy trong PostgreSQL:
SET SESSION cte_max_recursion_depth = 2000;
~~~

Giới hạn này là **cơ chế bảo vệ**, không phải một quy tắc yêu cầu báo cáo phải trả 2000 cấp. Nếu một đường phân cấp hợp lệ chỉ cần tối đa 8 cấp, vẫn nên viết **WHERE depth < 8** theo quy ước gốc và cấp cần hiển thị.

Nâng cte_max_recursion_depth lên rất lớn có thể cho phép một truy vấn lỗi sinh nhiều hàng hoặc dùng nhiều bộ nhớ hơn. Cần cân nhắc cùng giới hạn thời gian chạy và độ lớn kết quả.

### 15.4. SQLite

SQLite hỗ trợ WITH RECURSIVE nhưng không có cú pháp tương đương **OPTION (MAXRECURSION ...)** của SQL Server. Với bài toán chuyển đổi, có thể dùng điều kiện trong recursive member:

~~~sql
WITH RECURSIVE numbers(n, depth) AS (
    SELECT 1, 0
    UNION ALL
    SELECT n + 1, depth + 1
    FROM numbers
    WHERE depth < 10
)
SELECT *
FROM numbers
ORDER BY depth;
~~~

SQLite cũng có cú pháp **LIMIT trong recursive SELECT** với ngữ nghĩa giới hạn số hàng có thể thêm vào bảng đệ quy theo tài liệu SQLite; đây là **tính năng riêng**, không nên đem cú pháp LIMIT ở vị trí đó áp dụng nguyên văn cho mọi RDBMS.

Khi triển khai trên SQLite, vẫn cần kiểm soát chu trình, độ sâu và quy mô dữ liệu thay vì mặc định rằng hệ có một hạn mức đệ quy giống MySQL.

## 16. Kích thước kết quả có thể tăng theo cấp số nhân

Giới hạn depth giúp **chặn chiều dài đường đi**, nhưng **không nhất thiết chặn số hàng ở mức nhỏ**. Giả sử mỗi nút có trung bình **b** nút con và ta duyệt tới độ sâu **d** từ một gốc.

Nếu là cây phân nhánh đều và không lọc bớt, số nút tối đa trong mô hình lý tưởng là:

\[
N(d)=1+b+b^2+\cdots+b^d.
\]

Với **b > 1**, công thức tổng cấp số nhân:

\[
N(d)=\frac{b^{d+1}-1}{b-1}.
\]

Ví dụ, nếu mỗi nút có **3 con**:

| Độ sâu tối đa d (gốc = 0) | Số hàng từ một gốc nếu mỗi nút có 3 con |
| ---: | ---: |
| 0 | 1 |
| 1 | 4 |
| 2 | 13 |
| 3 | 40 |
| 5 | 364 |
| 8 | 9841 |
| 10 | 88573 |
| 12 | 797161 |
| 15 | 21523360 |

**Chỉ tăng d từ 10 lên 15** trong cây ba nhánh có thể tăng kết quả từ gần 89 nghìn lên **hơn 21 triệu hàng**. Điều kiện **depth < 15** có giới hạn rõ ràng nhưng vẫn có thể tiêu tốn nhiều tài nguyên.

Đây là **ước lượng cho cây phân nhánh đều**. Với đồ thị có nhiều đường tới một nút, UNION ALL có thể tạo nhiều hàng đường đi khác nhau; với điều kiện lọc hoặc nhiều nhánh cụt, kết quả thực tế có thể ít hơn.

### 16.1. Thí nghiệm phân nhánh an toàn ở depth = 5

Đoạn sau tạo ba nhánh A, B, C ở mỗi mức. Giới hạn 5 làm thí nghiệm kết thúc nhanh:

~~~sql
WITH RECURSIVE branching(depth, route) AS (
    SELECT
        0 AS depth,
        ''::TEXT AS route

    UNION ALL

    SELECT
        b.depth + 1,
        b.route || x.symbol
    FROM branching AS b
    CROSS JOIN (
        VALUES ('A'::TEXT), ('B'::TEXT), ('C'::TEXT)
    ) AS x(symbol)
    WHERE b.depth < 5
)
SELECT depth, COUNT(*) AS rows_at_depth
FROM branching
GROUP BY depth
ORDER BY depth;
~~~

Kết quả:

| depth | rows_at_depth |
| ---: | ---: |
| 0 | 1 |
| 1 | 3 |
| 2 | 9 |
| 3 | 27 |
| 4 | 81 |
| 5 | 243 |

Tổng cộng có **364 hàng**, dù truy vấn chỉ duyệt **5 cạnh từ gốc**.

### 16.2. Lý do JOIN không đúng làm bùng nổ hàng

Một recursive member thiếu điều kiện JOIN có thể tạo **CROSS JOIN** không chủ đích. Ví dụ, nếu mỗi vòng một hàng đang có được ghép với **tất cả hàng của một bảng**, số dòng có thể tăng rất nhanh.

~~~sql
-- Ví dụ có chủ ý phân nhánh, không dùng làm mẫu nối cây.
FROM branching AS b
CROSS JOIN some_options AS o
~~~

Với cây cha-con, điều kiện liên kết đúng là:

~~~sql
JOIN demo_org_units AS c
    ON c.parent_id = w.unit_id
~~~

Nếu đổi nhầm thành điều kiện luôn đúng hoặc bỏ ON, truy vấn có thể biến một cây nhỏ thành nhiều tổ hợp không có ý nghĩa.

### 16.3. Độ rộng hàng cũng quan trọng

Số hàng là một vế của bài toán kích thước; vế còn lại là **kích thước mỗi hàng**. Một bản ghi chỉ có node_id và depth nhỏ hơn nhiều so với hàng chứa:

- Nhiều cột mô tả dài.
- Một **path_text** ghép tên từ gốc đến nút.
- Một **path_ids** lưu toàn bộ đường đi.
- Nhiều trường JSON hoặc dữ liệu văn bản.

Trong mô hình phân nhánh, việc mỗi hàng mang theo đường đi ngày càng dài có thể khiến tổng lượng dữ liệu cần giữ/xuất **lớn hơn đáng kể** so với chỉ đếm số hàng.

## 17. LIMIT ở SELECT ngoài không phải giới hạn an toàn cho đệ quy

Câu truy vấn sau trông như chỉ cần 20 hàng:

~~~sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1, 0
    UNION ALL
    SELECT e.to_id, w.depth + 1
    FROM walk AS w
    JOIN demo_graph_edges AS e
        ON e.from_id = w.node_id
)
SELECT node_id, depth
FROM walk
LIMIT 20;
~~~

Trong PostgreSQL, một truy vấn ngoài **đơn giản** đôi khi có thể dừng yêu cầu thêm hàng khi đã lấy đủ 20. Tuy nhiên, đây **không phải biện pháp an toàn đáng tin cậy** để chặn một recursive CTE có thể vô hạn.

Ví dụ khi cần:

~~~sql
SELECT node_id, depth
FROM walk
ORDER BY depth DESC
LIMIT 20;
~~~

để biết 20 hàng có depth lớn nhất, hệ quản trị có thể phải **tạo hoặc xét toàn bộ kết quả** trước khi sắp xếp và chọn. Nếu tập đệ quy không có điều kiện dừng, truy vấn có thể không hoàn tất. Tương tự, JOIN hoặc phép tổng hợp ở truy vấn ngoài có thể khiến việc đọc một phần trở nên không khả thi.

**Phân biệt ba khái niệm:**

| Cơ chế | Hạn chế điều gì? | Có thay thế điều kiện dừng không? |
| --- | --- | --- |
| **WHERE w.depth < n** trong recursive member | Không tạo đường sâu hơn n theo quy ước gốc 0 | Là điều kiện dừng theo độ sâu |
| **Phát hiện chu trình** | Không cho đường đi quay lại nút đã thăm | Giải quyết một lớp lặp vòng, không giới hạn phân nhánh |
| **LIMIT n** ở SELECT ngoài | Giới hạn số dòng **trả ra cho người dùng** | **Không bảo đảm** dừng việc sinh toàn bộ tập đệ quy |

Nếu yêu cầu là “chỉ hiển thị 20 kết quả đầu tiên”, vẫn cần xác định **tiêu chí thứ tự**, **độ sâu cần duyệt** và **cơ chế chống chu trình**. LIMIT là một ràng buộc đầu ra, không phải lời giải tổng quát cho một recursion bị lỗi.

## 18. Giới hạn số hàng phát sinh khác giới hạn độ sâu

Một ngân sách kết quả thực tế có thể bao gồm:

- **max_depth:** số cạnh tối đa trên một đường đi.
- **max_rows:** số hàng kết quả hoặc số nút được phép gửi về ứng dụng.
- **max_time:** thời gian chạy tối đa.
- **max_path_length:** độ dài chuỗi/array đường đi cho phép.
- **max_roots:** số nút khởi đầu được phép phân tích trong một lần.

Trong SQL thuần, **max_depth** tương đối dễ đưa vào recursive member. Nhưng một **max_rows toàn cục chính xác** cho mọi đường và mọi vòng thường không thể thay bằng biểu thức **WHERE depth < n**, vì số nhánh ở mỗi cấp khác nhau.

### 18.1. Đếm trước khi trả một báo cáo lớn

Nếu đã có một truy vấn đệ quy **có điều kiện dừng an toàn**, ta có thể kiểm tra số hàng theo cấp:

~~~sql
WITH RECURSIVE org_walk(unit_id, depth) AS (
    SELECT unit_id, 0
    FROM demo_org_units
    WHERE unit_id = 1
    UNION ALL
    SELECT c.unit_id, w.depth + 1
    FROM demo_org_units AS c
    JOIN org_walk AS w ON c.parent_id = w.unit_id
    WHERE w.depth < 4
)
SELECT depth, COUNT(*) AS rows_at_depth
FROM org_walk
GROUP BY depth
ORDER BY depth;
~~~

Kết quả:

| depth | rows_at_depth |
| ---: | ---: |
| 0 | 1 |
| 1 | 2 |
| 2 | 3 |
| 3 | 1 |
| 4 | 1 |

Tổng cộng **8 hàng**, đúng với cây dưới root 1. Đây là cách quan sát **hình dạng phân nhánh** của dữ liệu.

**Nhưng đếm vẫn phải tạo và xử lý tập cần đếm.** Một truy vấn COUNT(*) bên ngoài không ngăn bản thân CTE sinh quá nhiều hàng. Nếu tập có nguy cơ rất lớn, cần đặt giới hạn từ đầu hoặc dùng phương pháp duyệt theo lô và hạn mức ứng dụng.

### 18.2. Lọc từ anchor để giảm số gốc

Thay vì bắt đầu từ **mọi nút gốc** rồi cuối cùng mới chọn một thành phố/khu vực, hãy chọn **đúng gốc cần xem** ngay tại anchor khi nghiệp vụ cho phép:

~~~sql
SELECT unit_id, parent_id, 0 AS depth
FROM demo_org_units
WHERE unit_id = 1
~~~

Giới hạn số gốc giảm tập khởi tạo của đệ quy. Nhưng nếu một gốc có hàng triệu hậu duệ, điều đó vẫn chưa đủ; phải xét thêm **depth, phân nhánh và chi phí trên mỗi hàng**.

### 18.3. Lọc cạnh hợp lệ trong recursive member

Nếu đồ thị có cột **is_active**, **edge_type** hoặc **tenant_id**, cần đặt điều kiện đúng ngay khi mở rộng:

~~~sql
-- Mẫu minh họa, bảng cạnh giả định có thêm các cột tương ứng.
JOIN graph_edges AS e
    ON e.from_id = w.node_id
   AND e.is_active IS TRUE
   AND e.edge_type = 'hierarchy'
~~~

Điều này không chỉ giảm số hàng: nó xác định **đường đi nào có ý nghĩa nghiệp vụ**. Không thể lấy một kết quả đã đi qua các cạnh không hợp lệ rồi chỉ lọc bỏ một số hàng ở SELECT cuối mà chắc chắn thu được cùng tập đường đi.

### 18.4. Phân trang và duyệt theo lô

Với kết quả có thể rất lớn, một ứng dụng thường **không tải toàn bộ cây nhiều triệu hàng về giao diện một lần**. Có thể:

- Chỉ tải con trực tiếp của một nút khi người dùng mở nhánh.
- Lấy cây đến độ sâu vừa phải rồi có nút **“Xem thêm cấp”**.
- Tính kết quả theo từng gốc hoặc nhóm gốc.
- Sử dụng cursor/phân trang đầu ra khi phù hợp, nhưng phải có **thứ tự ổn định** và giới hạn bên trong truy vấn nếu cần an toàn đệ quy.
- Nếu phải duyệt toàn đồ thị rất lớn, cân nhắc công việc xử lý theo lô với tập đã thăm và giới hạn tài nguyên được quản lý riêng.

**Phân trang kết quả SQL** không tự ngăn việc truy vấn phải xử lý rất nhiều hàng trước khi trả một trang, đặc biệt khi có ORDER BY phức tạp, GROUP BY hoặc DISTINCT trên toàn tập đệ quy.

## 19. Chi phí của đường đi và thứ tự duyệt

Khi bổ sung path_text hoặc path_ids, mỗi lần đệ quy cần xây dựng thêm dữ liệu:

~~~sql
p.path_text || ' / ' || c.unit_name
p.path_ids || c.unit_id
~~~

Độ dài đường đi tăng theo số cấp. Nếu có hàng trăm nghìn hàng kết quả, việc lặp lại tiền tố đường dẫn từ gốc ở nhiều hàng có thể tiêu tốn đáng kể tài nguyên.

### 19.1. Chỉ mang những cột thật sự cần qua đệ quy

Nếu mục đích là **tìm node_id và depth**, chỉ cần:

~~~sql
WITH RECURSIVE org_walk(unit_id, depth) AS (
    SELECT unit_id, 0
    FROM demo_org_units
    WHERE unit_id = 1

    UNION ALL

    SELECT c.unit_id, w.depth + 1
    FROM demo_org_units AS c
    JOIN org_walk AS w ON c.parent_id = w.unit_id
    WHERE w.depth < 4
)
SELECT w.unit_id, u.unit_name, w.depth
FROM org_walk AS w
JOIN demo_org_units AS u ON u.unit_id = w.unit_id
ORDER BY w.depth, w.unit_id;
~~~

**unit_name** được lấy ở SELECT cuối bằng JOIN, thay vì phải mang theo tên dài trên mỗi bước. Đây chỉ là một lựa chọn thiết kế: nếu cần chính tên để xây dựng path_text thì phải giữ/tham chiếu nó trong bước đệ quy tương ứng.

### 19.2. Thứ tự hàng không được bảo đảm nếu thiếu ORDER BY

Một CTE đệ quy có thể được hệ quản trị đánh giá theo cơ chế từng vòng, nhưng **không nên coi thứ tự hàng đầu ra ngầm định là hợp đồng của SQL**. Để hiển thị theo độ sâu, viết:

~~~sql
ORDER BY depth, unit_id
~~~

Để hiển thị theo đường đi, có thể sắp theo một khóa path đã thiết kế. PostgreSQL còn hỗ trợ **SEARCH DEPTH FIRST / BREADTH FIRST** từ các phiên bản mới để tạo cột thứ tự phục vụ ORDER BY. Nhưng **SEARCH mô tả khóa sắp xếp của kết quả**, không thay thế điều kiện dừng, giới hạn bộ nhớ hoặc chống chu trình.

### 19.3. Sắp xếp toàn bộ tập cũng tốn tài nguyên

Khi kết quả có rất nhiều hàng, **ORDER BY path_text** có thể đòi hỏi sắp xếp lượng chuỗi lớn. Nếu ứng dụng chỉ cần hiển thị từng nhánh, thiết kế truy vấn theo từng nhánh có thể hiệu quả hơn việc xây đường dẫn cho toàn cây rồi sắp xếp.

Chọn cách duyệt và trình bày dựa trên câu hỏi cụ thể: **cần một danh sách tất cả nút**, **cần đường đi ngắn nhất**, **cần mọi đường hợp lệ**, hay **chỉ cần một vài cấp**? Những bài toán này có độ lớn kết quả rất khác nhau.

## 20. Chỉ mục và kế hoạch thực thi

Trong cây cha-con, recursive member thường có điều kiện:

~~~sql
JOIN demo_org_units AS c
    ON c.parent_id = w.unit_id
~~~

Vì vậy, chỉ mục trên **parent_id** có thể hữu ích:

~~~sql
CREATE INDEX idx_demo_org_units_parent
ON demo_org_units(parent_id);
~~~

Ở bảng chỉ có 10 dòng, PostgreSQL có thể chọn quét bảng vì rẻ hơn đi qua chỉ mục. Trên bảng rất lớn, chỉ mục theo parent_id thường là lựa chọn đáng xem xét cho phép “tìm mọi con của một cha”.

Với bảng cạnh:

~~~sql
CREATE INDEX idx_demo_graph_edges_from
ON demo_graph_edges(from_id);
~~~

Trong bộ dữ liệu này, **PRIMARY KEY(from_id, to_id)** đã tạo chỉ mục B-tree bắt đầu bằng from_id, nên chỉ mục riêng trên from_id có thể là **dư thừa**. Trên hệ thống thật, hãy xem các chỉ mục hiện có trước khi thêm mới; thêm chỉ mục dư sẽ tăng chi phí lưu trữ và ghi.

### 20.1. EXPLAIN

~~~sql
EXPLAIN
WITH RECURSIVE org_walk(unit_id, depth) AS (
    SELECT unit_id, 0
    FROM demo_org_units
    WHERE unit_id = 1
    UNION ALL
    SELECT c.unit_id, w.depth + 1
    FROM demo_org_units AS c
    JOIN org_walk AS w ON c.parent_id = w.unit_id
    WHERE w.depth < 4
)
SELECT COUNT(*)
FROM org_walk;
~~~

Trong PostgreSQL, kế hoạch có thể bao gồm thành phần **Recursive Union** và **WorkTable Scan**, cùng các phép đọc bảng hoặc chỉ mục. **EXPLAIN** cho kế hoạch dự kiến; **EXPLAIN (ANALYZE, BUFFERS)** còn thực thi truy vấn để đo số liệu thật, nên chỉ dùng có kiểm soát khi truy vấn có nguy cơ phát sinh nhiều hàng.

Điều nên xem xét không chỉ là thời gian chạy:

- Tổng số hàng và số vòng được xử lý.
- Số hàng sinh ra ở mỗi vòng so với dự kiến.
- JOIN nào gây phân nhánh lớn.
- Có tràn bộ nhớ/sort sang tài nguyên tạm không.
- Truy vấn có mang theo path dài quá nhu cầu không.
- Điều kiện giới hạn depth và chu trình đã nằm trong recursive member chưa.

Một truy vấn đệ quy **trả đúng 10 hàng nhưng phải tạo hàng triệu hàng trung gian** vẫn có thể không phù hợp cho môi trường sản xuất.

## 21. Những lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Kết quả vượt một cấp | Dùng **w.depth <= max_depth** rồi sinh **w.depth+1** | Với gốc = 0, dùng **w.depth < max_depth** |
| Query chỉ in vài hàng nhưng vẫn treo | LIMIT ở SELECT ngoài không chặn toàn bộ phép mở rộng | Đặt điều kiện dừng trong recursive member |
| Truy vấn không hoàn tất khi dữ liệu có vòng | UNION ALL sinh lại nút qua chu trình | Theo dõi path hoặc dùng **CYCLE** |
| Dùng UNION nhưng chu trình vẫn chạy | Hàng có depth/path mới nên không trùng toàn bộ | Chặn theo node đã thăm, không chỉ dựa vào UNION |
| Có depth cap nhưng hàng triệu dòng | Mỗi nút có nhiều con, số nhánh tăng nhanh | Hạn chế gốc/cạnh/độ sâu và cân nhắc ngân sách số hàng |
| Cột đường dẫn bị lỗi độ dài | Anchor suy luận chuỗi quá ngắn hoặc VARCHAR giới hạn | CAST kiểu phù hợp; cân nhắc TEXT/NVARCHAR dài hơn |
| CTE báo lỗi kiểu cột giữa hai vế | Số cột/kiểu dữ liệu không tương thích | Khai báo cùng số cột và CAST tường minh |
| NULL ở anchor bị suy luận kiểu không mong muốn | NULL không có kiểu cụ thể ở vị trí nhạy cảm | Dùng NULL::TEXT/CAST(NULL AS ...) theo phương ngữ |
| Đếm node khác nhau ít hơn số hàng | Một node có nhiều đường đi đến hoặc có vòng | Phân biệt “mọi đường đi” và “tập nút” |
| CYCLE vẫn có node trùng đầu ra | CYCLE chặn vòng trên từng đường, không loại mọi đường khác | Dùng chiến lược de-dup theo yêu cầu nghiệp vụ |
| Kết quả ngắn nhưng thiếu hậu duệ | Giới hạn depth cắt cây hợp lệ | Thêm cờ phát hiện còn con tại ranh giới |
| Không có thứ tự ổn định | Không có ORDER BY ở SELECT ngoài | Đặt ORDER BY phù hợp |
| Kích thước output quá lớn do path_text | Mỗi hàng chứa đường dẫn dài | Chỉ lưu path khi cần, hạn chế độ sâu |
| Nâng MAXRECURSION/cte_max_recursion_depth lên rất cao | Né lỗi thay vì hiểu độ sâu thật | Xác minh dữ liệu và điều kiện dừng trước |
| Dùng cú pháp SQL Server trên PostgreSQL | OPTION (MAXRECURSION) không phải cú pháp PostgreSQL | Dùng điều kiện depth và cơ chế PostgreSQL |
| Chỉ xét độ sâu mà không xét thời gian | Phân nhánh lớn ngay ở vài cấp đầu | Kết hợp thời gian, kích thước và phạm vi đầu vào |

## 22. Đối chiếu nhanh các phương ngữ

| Chủ đề | PostgreSQL 15+ | SQL Server | MySQL 8.0 | SQLite |
| --- | --- | --- | --- | --- |
| Khai báo đệ quy | **WITH RECURSIVE** | **WITH**; không viết RECURSIVE | **WITH RECURSIVE** | **WITH RECURSIVE** |
| Giới hạn độ sâu trong truy vấn | WHERE depth < n | WHERE depth < n | WHERE depth < n | WHERE depth < n |
| Bảo vệ giới hạn vòng đặc thù | Không có OPTION(MAXRECURSION) | **OPTION (MAXRECURSION n)**; mặc định 100 | **cte_max_recursion_depth**; thường mặc định 1000 | Không dùng cùng cú pháp MAXRECURSION |
| Kiểu cột path | TEXT, VARCHAR; CAST theo PostgreSQL | NVARCHAR/VARCHAR; anchor/recursive cần khớp kiểu | Anchor quyết định kiểu; CAST đủ dài | Kiểu động nhưng vẫn có giới hạn tài nguyên |
| Phát hiện chu trình tích hợp | **CYCLE** ở PostgreSQL 14+ | Không dùng nguyên văn mệnh đề CYCLE của PostgreSQL | Cần giải pháp đường đi/điều kiện thích hợp | Cần giải pháp đường đi/điều kiện thích hợp |
| LIMIT ở SELECT ngoài | Có, không bảo đảm giới hạn đệ quy | TOP/FETCH, không thay điều kiện dừng | LIMIT, không thay điều kiện dừng | LIMIT, không thay điều kiện dừng |

**Oracle Database** cũng hỗ trợ các kỹ thuật truy vấn phân cấp và subquery factoring đệ quy, với những cơ chế như **CONNECT BY**, **NOCYCLE** và **CYCLE** tùy cách truy vấn. Không nên thay từ khóa giữa các hệ một cách cơ học; hãy xác định đúng phiên bản, loại cú pháp đệ quy và quy tắc giới hạn của hệ đang chạy.

### Không đánh đồng độ sâu tối đa với số hàng tối đa

Một bộ cấu hình máy chủ như **MAXRECURSION 100** hoặc **cte_max_recursion_depth 1000** **không có nghĩa truy vấn chỉ trả tối đa 100 hay 1000 hàng**. Một vòng đệ quy có thể tạo **nhiều hàng** từ nhiều nút của vòng trước. Đây là khác biệt quan trọng nhất khi tính kích thước kết quả.

## 23. Mẫu truy vấn tổng hợp: giới hạn cấp, chống chu trình, kiểm soát đầu ra

Một mẫu PostgreSQL cho đồ thị **demo_graph_edges**:

~~~sql
WITH RECURSIVE paths(node_id, depth, path_ids) AS (
    -- Bắt đầu từ một node rõ ràng.
    SELECT
        1 AS node_id,
        0 AS depth,
        ARRAY[1]::INTEGER[] AS path_ids

    UNION ALL

    SELECT
        e.to_id,
        p.depth + 1,
        p.path_ids || e.to_id
    FROM paths AS p
    JOIN demo_graph_edges AS e
        ON e.from_id = p.node_id
    WHERE p.depth < 4
      AND NOT (e.to_id = ANY(p.path_ids))
)
SELECT
    node_id,
    depth
FROM paths
ORDER BY depth, node_id
LIMIT 100;
~~~

Ba cơ chế trên làm ba nhiệm vụ **khác nhau**:

1. **p.depth < 4** không sinh đường đi sâu hơn depth 4.
2. **NOT (e.to_id = ANY(p.path_ids))** ngăn quay lại một nút đã nằm trên đường hiện tại.
3. **LIMIT 100** giới hạn hàng **trình bày** sau khi dữ liệu đã được bảo vệ bởi hai điều kiện đầu; nó không phải cơ chế ngăn sinh mọi đường trong một đồ thị rộng.

Nếu nghiệp vụ chỉ cần **danh sách nút duy nhất**, không cần mọi đường đi, có thể đổi thành chiến lược duyệt node_id với UNION theo phần 11. Nếu cần **đường đi ngắn nhất**, đó là bài toán khác: có thể cần thuật toán tìm kiếm phù hợp, xử lý nhiều đường đến cùng nút và lựa chọn đúng chi phí/độ dài, không chỉ lấy một hàng bất kỳ.

### Một mẫu cho cây tổ chức có đường dẫn hiển thị

~~~sql
WITH RECURSIVE org_tree(
    unit_id, depth, path_ids, path_text
) AS (
    SELECT
        u.unit_id,
        0,
        ARRAY[u.unit_id]::INTEGER[],
        u.unit_name::TEXT
    FROM demo_org_units AS u
    WHERE u.unit_id = 1

    UNION ALL

    SELECT
        c.unit_id,
        t.depth + 1,
        t.path_ids || c.unit_id,
        t.path_text || ' / ' || c.unit_name
    FROM org_tree AS t
    JOIN demo_org_units AS c
        ON c.parent_id = t.unit_id
    WHERE t.depth < 4
      AND NOT (c.unit_id = ANY(t.path_ids))
)
SELECT
    unit_id,
    depth,
    path_text
FROM org_tree
ORDER BY depth, unit_id;
~~~

Mẫu này có giới hạn, đường dẫn, chống vòng trên mỗi đường và thứ tự hiển thị. Trên **cây thật** có một parent hợp lệ cho mỗi nút, kiểm tra chu trình có thể là lớp bảo vệ bổ sung; nó đặc biệt quan trọng với dữ liệu đồ thị hoặc dữ liệu cha-con bị nhập sai.

## 24. Bài tập thực hành

Dùng hai bảng tạm **demo_org_units** và **demo_graph_edges** đã tạo trong bài.

1. Viết WITH RECURSIVE bắt đầu từ unit_id 1, gốc depth 0, không giới hạn độ sâu. Đếm tổng số đơn vị của cây này.
2. Thêm **WHERE w.depth < 2** vào recursive member. Liệt kê các unit_id được trả về và giải thích vì sao unit_id 7 không xuất hiện.
3. Đổi sang **WHERE w.depth <= 2**. So sánh với bài 2 và chỉ ra lỗi vượt một cấp.
4. Duyệt toàn bộ gốc parent_id IS NULL và giữ root_id. Với max_depth 2, cây gốc 1 và gốc 9 có bao nhiêu hàng?
5. Với depth cap 2, viết cột has_children và cảnh báo nút ở ranh giới vẫn còn con. Nút nào nhận cảnh báo?
6. Chạy truy vấn tạo path_text từ unit_name. In đường dẫn tới unit_id 8 và giải thích tại sao cần TEXT thay vì cố giới hạn VARCHAR(20).
7. Viết một CTE dùng **ARRAY[unit_id]** để lưu path_ids. Kiểm tra nút kế tiếp chưa có trong mảng trước khi mở rộng.
8. Dùng demo_graph_edges, chạy truy vấn có **depth < 4** nhưng chưa kiểm tra chu trình. Tìm một đường lặp qua 2 và 4.
9. Thêm kiểm tra **NOT (e.to_id = ANY(path_ids))**. Giải thích tại sao node_id 4 vẫn có thể xuất hiện qua hai đường khác nhau.
10. Viết lại bài 9 với **CYCLE node_id SET is_cycle USING cycle_path** của PostgreSQL 15. Lọc để chỉ giữ hàng không đóng chu trình.
11. Dùng **UNION** trong CTE chỉ có một cột node_id để tìm tập nút có thể tới từ 1. Dự đoán số nút duy nhất.
12. Thêm depth vào CTE bài 11. Giải thích vì sao UNION không còn là lớp bảo vệ chu trình đủ tin cậy.
13. Dùng CTE phân nhánh ba lựa chọn **A/B/C** tới depth = 5. Đếm số hàng theo depth và cộng tổng 364.
14. Tính số hàng lý tưởng của một cây có b = 2 và d = 8; giải thích vì sao độ sâu 8 vẫn có thể tạo rất nhiều hàng.
15. Viết một truy vấn LIMIT 10 ở SELECT ngoài nhưng vẫn có điều kiện dừng trong recursive member. Giải thích tác dụng riêng của hai giới hạn.
16. Đọc cột depth của recursive member và kiểm tra kiểu INTEGER. Thử khai báo kiểu BIGINT ở anchor và recursive member.
17. Viết path_text với CAST kiểu phù hợp trên PostgreSQL. Chuyển phần CAST của anchor sang cú pháp **MySQL CHAR(500)**.
18. Viết một ví dụ SQL Server dùng WITH, hai vế trả **NVARCHAR(500)**, điều kiện depth < 10 và **OPTION (MAXRECURSION 100)**.
19. Giải thích vì sao **MAXRECURSION 100** không bảo đảm tối đa 100 hàng khi mỗi nút có nhiều con.
20. Dùng EXPLAIN cho CTE duyệt demo_org_units và xác định vị trí **Recursive Union**, **WorkTable Scan** nếu kế hoạch có các thành phần đó.
21. Thiết kế một truy vấn trả các nút cùng depth và cờ **còn con chưa mở rộng**, để ứng dụng có thể hiển thị “Xem thêm”.
22. So sánh chi phí của hai kết quả: chỉ **(node_id, depth)** và **(node_id, depth, path_text, path_ids)** khi đồ thị có rất nhiều đường đi.

### Câu hỏi tự kiểm tra

**Câu 1.** Gốc có depth 0. Nếu muốn trả đến depth 3, recursive member nên dùng w.depth < 3 hay w.depth <= 3?

**Đáp án:** **w.depth < 3**, vì con sinh ra có depth = w.depth + 1.

**Câu 2.** Depth cap = 3 có chắc chắn tạo tối đa bốn hàng không?

**Đáp án:** **Không.** Nó giới hạn số cấp trên một đường; mỗi cấp có thể có rất nhiều nút.

**Câu 3.** SELECT cuối có LIMIT 20 có bảo đảm một recursive CTE lỗi chu trình không chạy mãi không?

**Đáp án:** **Không đáng tin cậy.** Bộ tối ưu có thể phải tạo toàn bộ tập đệ quy vì ORDER BY, JOIN hoặc phép tính khác. Cần điều kiện dừng và chống chu trình trong quá trình đệ quy.

**Câu 4.** Dùng UNION thay UNION ALL có luôn ngăn được vòng lặp?

**Đáp án:** **Không.** UNION loại trùng theo **toàn bộ hàng**. Nếu depth hoặc path đổi mỗi lần quay lại nút, các hàng không trùng nhau.

**Câu 5.** CYCLE trong PostgreSQL có tự loại mọi node_id trùng nhau ở các đường đi hợp lệ khác nhau không?

**Đáp án:** **Không.** CYCLE phát hiện nút lặp **trên một đường đi**; cùng nút vẫn có thể được tìm qua các nhánh khác nhau.

**Câu 6.** MySQL có thể gặp lỗi độ dài path_text dù PostgreSQL với TEXT chạy được, vì sao?

**Đáp án:** Recursive CTE của MySQL suy luận kiểu cột từ anchor. Nếu anchor có độ dài chuỗi không đủ cho các vòng nối thêm, giá trị đệ quy có thể vượt độ dài đã xác định. Cần CAST phù hợp và giới hạn độ dài thực tế.

**Câu 7.** MAXRECURSION 0 trong SQL Server có phải dừng ngay ở cấp 0 không?

**Đáp án:** **Không.** Nó **bỏ giới hạn MAXRECURSION** của cơ chế ấy; càng cần điều kiện dừng đáng tin cậy.

**Câu 8.** Nếu kết quả giới hạn depth = 2 không có unit_id 7, có được kết luận đơn vị 4 không có con không?

**Đáp án:** **Không.** Đơn vị 4 nằm ở ranh giới depth 2 và có con là 7 ở depth 3. Cần kiểm tra còn con hoặc thông báo kết quả đã bị cắt cấp.

## 25. Ghi nhớ cốt lõi

Một truy vấn đệ quy đáng tin cậy cần kiểm soát **ba khía cạnh đồng thời**:

- **Độ sâu:** đặt điều kiện dừng trong recursive member. Với gốc depth 0 và bước tiếp theo tăng 1, **WHERE depth < max_depth** giúp không sinh hàng sâu hơn mức quy định.
- **Kiểu dữ liệu:** anchor và recursive member phải trả các cột tương thích. Khai báo rõ kiểu cho depth, giá trị cộng dồn và đường dẫn; đặc biệt chú ý **độ dài chuỗi** của MySQL và **kiểu khớp chặt** của SQL Server.
- **Kích thước kết quả:** dù depth nhỏ, kết quả có thể tăng theo cấp số nhân khi mỗi nút có nhiều con. **LIMIT ở SELECT cuối không thay thế giới hạn đệ quy**, và **chống chu trình không đồng nghĩa giới hạn mọi đường hợp lệ**.

**CYCLE hoặc kiểm tra path đã thăm** giúp ngăn đường đi quay lại nút cũ. **UNION** có thể loại trùng hàng, nhưng chỉ hữu ích để dừng chu trình khi toàn bộ hàng thật sự lặp lại. Khi báo cáo bị giới hạn độ sâu, hãy nhận diện **những nhánh còn con nhưng chưa được mở rộng** để không trình bày một kết quả cắt ngắn như dữ liệu đầy đủ.

Cuối cùng, mỗi RDBMS có cơ chế bảo vệ khác nhau: **MAXRECURSION** trên SQL Server, **cte_max_recursion_depth** trên MySQL, và các giới hạn truy vấn/tài nguyên trên PostgreSQL hoặc SQLite. Những cơ chế đó là **lớp phòng vệ vận hành**; một câu truy vấn đúng vẫn phải có **quy tắc dừng, xử lý kiểu và phạm vi kết quả phù hợp với nghiệp vụ**.
