# CTE đệ quy, hàm cửa sổ và các mệnh đề mở rộng trong SQL đa hệ quản trị

SQL có những công cụ chuyên biệt cho các bài toán vượt ra ngoài lọc hàng và GROUP BY. **CTE đệ quy** giúp lần theo cây phân cấp và quan hệ nhiều cấp; **hàm cửa sổ** tính hạng, giá trị trước/sau, tổng lũy kế hoặc trung bình trượt mà vẫn giữ từng hàng; các **mệnh đề mở rộng** như SEARCH/CYCLE, FILTER, QUALIFY, GROUPING SETS, ROLLUP, CUBE, PIVOT, LATERAL/APPLY và FETCH WITH TIES giúp diễn đạt truy vấn phân tích rõ ràng hơn.

Bài học thuộc **Database SQL → SQL đa hệ quản trị → CTE đệ quy, hàm cửa sổ và các mệnh đề mở rộng**. Các ví dụ tập trung vào PostgreSQL, MySQL, SQL Server, Oracle và SQLite. Những hệ này có nhiều khái niệm tương tự nhưng cú pháp, giới hạn và thứ tự xử lý không hoàn toàn giống nhau.

Mục tiêu là hiểu bản chất từng công cụ, biết khi nào dùng, biết cách chuyển đổi sang dialect khác và tránh những lỗi như đệ quy không dừng, xếp hạng không xác định, frame mặc định sai, hoặc dùng một extension chỉ có ở một DBMS.

## 1. CTE thường và CTE đệ quy

CTE (*Common Table Expression*) là kết quả truy vấn được đặt tên trong mệnh đề `WITH`, có phạm vi trong câu lệnh chứa nó.

~~~sql
WITH don_hang_hop_le AS (
    SELECT id, khach_hang_id, tong_tien
    FROM don_hang
    WHERE trang_thai = 'DA_XAC_NHAN'
)
SELECT *
FROM don_hang_hop_le
WHERE tong_tien > 1000000;
~~~

CTE thường không tự tham chiếu chính nó. CTE đệ quy có một phần truy vấn tham chiếu lại tên CTE để tạo vòng tiếp theo.

~~~sql
WITH RECURSIVE day_so(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM day_so
    WHERE n < 5
)
SELECT n
FROM day_so
ORDER BY n;
~~~

Kết quả là các số 1 đến 5.

| Loại | Đặc điểm |
| --- | --- |
| CTE thường | Đặt tên cho truy vấn trung gian, không tự tham chiếu |
| CTE đệ quy | Có anchor và recursive member; recursive member tham chiếu CTE |
| Temporary table | Đối tượng lưu trữ có vòng đời riêng theo DBMS/session |
| View | Đối tượng schema được định nghĩa lâu dài |

CTE không mặc nhiên là bảng tạm. Optimizer có thể inline, merge hoặc materialize tùy DBMS, phiên bản, cấu trúc truy vấn và plan.

### 1.1. Cú pháp khác nhau

- PostgreSQL, MySQL và SQLite dùng `WITH RECURSIVE`.
- SQL Server dùng `WITH` và không viết từ khóa `RECURSIVE`.
- Oracle recursive subquery factoring dùng `WITH`, không viết `RECURSIVE`; Oracle còn có cú pháp phân cấp riêng.

## 2. Mô hình thực thi của recursive CTE

Recursive CTE thường gồm:

1. **Anchor member:** tạo tập hàng ban đầu.
2. **Recursive member:** đọc tập hàng ở vòng trước và sinh hàng mới.
3. **Điều kiện dừng:** khi recursive member không còn sinh hàng mới, quá trình kết thúc.

~~~sql
WITH RECURSIVE ten_cte(cot_1, cot_2) AS (
    SELECT gia_tri_ban_dau, ...

    UNION ALL

    SELECT gia_tri_tiep_theo, ...
    FROM bang_nguon AS b
    JOIN ten_cte AS c
      ON dieu_kien_lien_ket
)
SELECT *
FROM ten_cte;
~~~

Ví dụ đếm:

~~~sql
WITH RECURSIVE dem(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM dem
    WHERE n < 5
)
SELECT n FROM dem ORDER BY n;
~~~

Diễn tiến: anchor sinh 1; vòng tiếp theo sinh 2; rồi 3, 4, 5; ở hàng 5 điều kiện `n < 5` sai nên không còn hàng mới.

### 2.1. Điều kiện dừng là yêu cầu thiết kế

~~~sql
-- KHÔNG chạy: không có điều kiện dừng.
WITH RECURSIVE dem(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1 FROM dem
)
SELECT n FROM dem;
~~~

Truy vấn có thể chạy đến khi chạm giới hạn recursion, timeout hoặc tài nguyên. Không dùng giới hạn mặc định của server thay cho điều kiện kết thúc nghiệp vụ.

### 2.2. UNION ALL và UNION

`UNION ALL` giữ mọi hàng được sinh, kể cả trùng. `UNION` loại hàng trùng theo toàn bộ danh sách cột của phép hợp.

`UNION` không phải cách phát hiện cycle đáng tin cậy nếu CTE có depth hoặc path. Cùng một node có thể xuất hiện với path khác nhau nên hàng không trùng hoàn toàn. Cần theo dõi node đã thăm hoặc dùng cú pháp CYCLE của DBMS có hỗ trợ.

## 3. Dữ liệu cây phân cấp thực hành

Mỗi nhân viên có tối đa một quản lý trực tiếp. Nhân viên cấp cao nhất có manager_id là NULL.

~~~sql
CREATE TABLE nhan_vien (
    id INTEGER PRIMARY KEY,
    manager_id INTEGER NULL,
    ho_ten VARCHAR(100) NOT NULL,
    phong_ban VARCHAR(50) NOT NULL,
    luong DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (manager_id) REFERENCES nhan_vien(id)
);

INSERT INTO nhan_vien
    (id, manager_id, ho_ten, phong_ban, luong)
VALUES
    (1, NULL, 'Lan',   'Dieu hanh', 50000000),
    (2, 1,    'Minh',  'Ky thuat',  35000000),
    (3, 1,    'Hoa',   'Kinh doanh',32000000),
    (4, 2,    'Nam',   'Ky thuat',  25000000),
    (5, 2,    'Linh',  'Ky thuat',  24000000),
    (6, 3,    'An',    'Kinh doanh',22000000),
    (7, 4,    'Binh',  'Ky thuat',  18000000);
~~~

Cấu trúc:

~~~text
Lan (1)
├── Minh (2)
│   ├── Nam (4)
│   │   └── Binh (7)
│   └── Linh (5)
└── Hoa (3)
    └── An (6)
~~~

Khóa ngoại bảo đảm manager_id tham chiếu một nhân viên có tồn tại, nhưng **không tự cấm chu trình**. Ví dụ dữ liệu vẫn có thể bị thay đổi thành A quản lý B, B quản lý C, C quản lý A nếu không có quy tắc bổ sung.

## 4. Duyệt cây bằng recursive CTE

Ví dụ PostgreSQL:

~~~sql
WITH RECURSIVE cay_nhan_vien AS (
    SELECT
        id,
        manager_id,
        ho_ten,
        phong_ban,
        0 AS cap,
        ARRAY[id] AS duong_di
    FROM nhan_vien
    WHERE manager_id IS NULL

    UNION ALL

    SELECT
        nv.id,
        nv.manager_id,
        nv.ho_ten,
        nv.phong_ban,
        c.cap + 1,
        c.duong_di || nv.id
    FROM nhan_vien AS nv
    JOIN cay_nhan_vien AS c
      ON nv.manager_id = c.id
)
SELECT id, manager_id, ho_ten, phong_ban, cap, duong_di
FROM cay_nhan_vien
ORDER BY duong_di;
~~~

Anchor lấy root. Recursive member lấy các nhân viên có manager_id bằng id của hàng ở vòng trước. Cột `cap` lưu độ sâu; `duong_di` lưu path bằng array integer.

### 4.1. Bắt đầu từ một node bất kỳ

~~~sql
WITH RECURSIVE cap_duoi AS (
    SELECT id, manager_id, ho_ten, 0 AS cap
    FROM nhan_vien
    WHERE id = 2

    UNION ALL

    SELECT nv.id, nv.manager_id, nv.ho_ten, c.cap + 1
    FROM nhan_vien AS nv
    JOIN cap_duoi AS c
      ON nv.manager_id = c.id
)
SELECT *
FROM cap_duoi
ORDER BY cap, id;
~~~

Kết quả gồm Minh ở cấp 0, Nam và Linh ở cấp 1, Binh ở cấp 2.

### 4.2. Lọc kết quả hay cắt nhánh?

Hai vị trí đặt điều kiện có ý nghĩa khác nhau:

- Lọc trong SELECT cuối: vẫn duyệt cây, chỉ ẩn hàng không khớp khỏi kết quả.
- Lọc trong recursive member: node không khớp không được mở rộng; các node con bên dưới nó có thể không được tìm thấy.

Ví dụ muốn chỉ hiển thị nhân viên phòng Kỹ thuật nhưng vẫn đi xuyên qua quản lý thuộc phòng khác, hãy duyệt toàn cây rồi lọc ở SELECT cuối. Nếu lọc ngay trong recursive member, nhánh con có thể bị cắt.

### 4.3. Nhiều root và node mồ côi

Anchor có thể lấy nhiều root bằng điều kiện `manager_id IS NULL`. Nếu một node không có đường đi từ root do dữ liệu lỗi hoặc do một chu trình riêng, truy vấn bắt đầu từ root sẽ không nhìn thấy nó. Muốn phát hiện dữ liệu bất thường, cần truy vấn kiểm tra riêng các node chưa được duyệt.

## 5. Phát hiện chu trình

Chu trình có thể khiến recursive CTE sinh lặp vô hạn hoặc tới giới hạn. Cần đánh dấu các node đã xuất hiện trên đường đi hiện tại.

### 5.1. PostgreSQL với array path

~~~sql
WITH RECURSIVE cay AS (
    SELECT
        id,
        manager_id,
        ho_ten,
        ARRAY[id] AS path,
        false AS co_chu_trinh
    FROM nhan_vien
    WHERE id = 1

    UNION ALL

    SELECT
        nv.id,
        nv.manager_id,
        nv.ho_ten,
        c.path || nv.id,
        nv.id = ANY(c.path)
    FROM nhan_vien AS nv
    JOIN cay AS c ON nv.manager_id = c.id
    WHERE NOT c.co_chu_trinh
)
SELECT *
FROM cay;
~~~

Điều kiện kiểm tra xem id con đã có trong path hay chưa. Hàng được đánh dấu cycle không được mở rộng tiếp. Nếu cần báo lỗi, có thể giữ hàng đánh dấu trong kết quả và xử lý riêng.

### 5.2. SQL Server dùng chuỗi path

~~~sql
WITH cay AS (
    SELECT
        id,
        manager_id,
        ho_ten,
        0 AS cap,
        CAST('/' + CAST(id AS varchar(20)) + '/' AS varchar(max)) AS path
    FROM dbo.NhanVien
    WHERE id = 1

    UNION ALL

    SELECT
        nv.id,
        nv.manager_id,
        nv.ho_ten,
        c.cap + 1,
        CAST(c.path + CAST(nv.id AS varchar(20)) + '/' AS varchar(max))
    FROM dbo.NhanVien AS nv
    JOIN cay AS c ON nv.manager_id = c.id
    WHERE CHARINDEX(
        '/' + CAST(nv.id AS varchar(20)) + '/',
        c.path
    ) = 0
)
SELECT *
FROM cay
OPTION (MAXRECURSION 100);
~~~

Dấu phân cách tránh nhầm ID 1 với ID 11. Dùng varchar(max) để path không bị giới hạn ngắn. MAXRECURSION là giới hạn bảo vệ, không thay thế kiểm tra cycle.

### 5.3. MySQL dùng LOCATE

~~~sql
WITH RECURSIVE cay(id, manager_id, ho_ten, cap, path) AS (
    SELECT
        id,
        manager_id,
        ho_ten,
        0,
        CAST(CONCAT('/', id, '/') AS CHAR(4000))
    FROM nhan_vien
    WHERE id = 1

    UNION ALL

    SELECT
        nv.id,
        nv.manager_id,
        nv.ho_ten,
        c.cap + 1,
        CONCAT(c.path, nv.id, '/')
    FROM nhan_vien AS nv
    JOIN cay AS c ON nv.manager_id = c.id
    WHERE LOCATE(CONCAT('/', nv.id, '/'), c.path) = 0
      AND c.cap < 100
)
SELECT *
FROM cay;
~~~

MySQL suy ra kiểu cột recursive CTE từ phần anchor trong những trường hợp quan trọng. CAST path ở anchor đủ dài để tránh lỗi/truncation khi nối thêm ID.

### 5.4. ID chuỗi và ký tự phân cách

Nếu ID có thể chứa ký tự phân cách, chuỗi path phải escape hoặc encode an toàn. Không dùng chuỗi path ngây thơ cho khóa tùy ý. Với graph lớn, dùng bảng visited, staging theo vòng hoặc thuật toán graph chuyên biệt có thể hiệu quả hơn.

## 6. SEARCH và CYCLE

PostgreSQL và Oracle hỗ trợ cú pháp mở rộng để khai báo thứ tự duyệt và đánh dấu chu trình.

### 6.1. PostgreSQL SEARCH

~~~sql
WITH RECURSIVE cay(id, manager_id, ho_ten) AS (
    SELECT id, manager_id, ho_ten
    FROM nhan_vien
    WHERE manager_id IS NULL

    UNION ALL

    SELECT nv.id, nv.manager_id, nv.ho_ten
    FROM nhan_vien AS nv
    JOIN cay AS c ON nv.manager_id = c.id
)
SEARCH DEPTH FIRST BY id SET thu_tu
SELECT id, manager_id, ho_ten
FROM cay
ORDER BY thu_tu;
~~~

`SEARCH DEPTH FIRST` hoặc `SEARCH BREADTH FIRST` tạo cột thứ tự để sắp xếp kết quả. Vẫn cần ORDER BY ở SELECT cuối để bảo đảm thứ tự đầu ra.

### 6.2. PostgreSQL CYCLE

~~~sql
WITH RECURSIVE cay(id, manager_id, ho_ten) AS (
    SELECT id, manager_id, ho_ten
    FROM nhan_vien
    WHERE id = 1

    UNION ALL

    SELECT nv.id, nv.manager_id, nv.ho_ten
    FROM nhan_vien AS nv
    JOIN cay AS c ON nv.manager_id = c.id
)
CYCLE id SET co_chu_trinh USING duong_di
SELECT id, manager_id, ho_ten, co_chu_trinh, duong_di
FROM cay;
~~~

CYCLE khai báo khóa cần theo dõi, cột đánh dấu chu trình và cột lưu đường đi. Tính năng có trong các phiên bản PostgreSQL hiện đại; kiểm tra phiên bản triển khai.

### 6.3. Oracle SEARCH và CYCLE

~~~sql
WITH cay(id, manager_id, ho_ten) AS (
    SELECT id, manager_id, ho_ten
    FROM nhan_vien
    WHERE manager_id IS NULL

    UNION ALL

    SELECT nv.id, nv.manager_id, nv.ho_ten
    FROM nhan_vien nv
    JOIN cay c ON nv.manager_id = c.id
)
SEARCH DEPTH FIRST BY id SET thu_tu
CYCLE id SET chu_trinh TO 'Y' DEFAULT 'N'
SELECT id, manager_id, ho_ten, chu_trinh
FROM cay
ORDER BY thu_tu;
~~~

Oracle không dùng từ khóa RECURSIVE sau WITH. Các cột đánh dấu phải dùng kiểu tương thích với giá trị Y/N đã khai báo.

SQL Server và MySQL không có cùng cú pháp SEARCH/CYCLE như PostgreSQL/Oracle trong các phiên bản phổ biến; thường phải tự theo dõi path và giới hạn recursion.

## 7. Oracle CONNECT BY

Oracle có cú pháp phân cấp truyền thống:

~~~sql
SELECT
    id,
    manager_id,
    ho_ten,
    LEVEL AS cap,
    SYS_CONNECT_BY_PATH(ho_ten, ' / ') AS duong_di
FROM nhan_vien
START WITH manager_id IS NULL
CONNECT BY PRIOR id = manager_id
ORDER SIBLINGS BY ho_ten;
~~~

- `START WITH` xác định root.
- `CONNECT BY PRIOR id = manager_id` nối cha với con.
- `LEVEL` cho biết cấp, root bắt đầu ở 1.
- `SYS_CONNECT_BY_PATH` tạo biểu diễn đường đi.
- `ORDER SIBLINGS BY` sắp xếp anh em cùng cha mà vẫn giữ cấu trúc phân cấp.

Có thể dùng `NOCYCLE` và `CONNECT_BY_ISCYCLE` để xử lý dữ liệu có chu trình theo cú pháp Oracle. CONNECT BY là extension Oracle-specific; recursive CTE thường dễ chuyển đổi hơn khi ứng dụng hỗ trợ nhiều DBMS.

## 8. Graph traversal và sự bùng nổ số đường đi

Cây có một cha cho mỗi node; graph có thể có nhiều đường đi tới cùng node.

~~~text
A ──→ C
│     ↑
└──→ B ──→ D
~~~

Phải xác định bài toán muốn:

- Liệt kê mọi đường đi;
- Tìm tập node có thể tới được;
- Tìm đường ngắn nhất;
- Phát hiện chu trình;
- Đếm số đường.

Recursive CTE mang path có thể liệt kê đường đi:

~~~sql
WITH RECURSIVE duong_di(node, path) AS (
    SELECT 1, ARRAY[1]

    UNION ALL

    SELECT c.den_node, d.path || c.den_node
    FROM canh AS c
    JOIN duong_di AS d ON c.tu_node = d.node
    WHERE NOT c.den_node = ANY(d.path)
)
SELECT node, path
FROM duong_di;
~~~

Nếu graph có nhiều nhánh, số path có thể tăng rất nhanh. UNION không tự tìm đường ngắn nhất; nếu path/depth khác nhau, hàng vẫn khác. Với graph lớn, cân nhắc BFS/Dijkstra hoặc xử lý chuyên biệt.

## 9. Giới hạn recursive CTE theo DBMS

| DBMS | Cú pháp | Giới hạn và lưu ý |
| --- | --- | --- |
| PostgreSQL | WITH RECURSIVE | Điều kiện dừng, timeout và tài nguyên; SEARCH/CYCLE ở phiên bản hiện đại |
| MySQL 8.0+ | WITH RECURSIVE | cte_max_recursion_depth; CAST kiểu path ở anchor |
| SQL Server | WITH, không có RECURSIVE | OPTION (MAXRECURSION n); recursive member bị hạn chế cú pháp |
| Oracle | WITH recursive factoring | Không viết RECURSIVE; SEARCH/CYCLE; có CONNECT BY |
| SQLite | WITH RECURSIVE | Recursive SELECT có giới hạn; không đặt aggregate/window function trong recursive member |

SQL Server ví dụ:

~~~sql
WITH cay AS (
    SELECT ...
    UNION ALL
    SELECT ...
)
SELECT *
FROM cay
OPTION (MAXRECURSION 1000);
~~~

`MAXRECURSION 0` bỏ giới hạn mặc định của SQL Server; không có nghĩa truy vấn an toàn.

MySQL có biến `cte_max_recursion_depth`. Chỉ tăng giới hạn khi đã xác nhận điều kiện dừng và dữ liệu thực tế.

SQLite có quy tắc riêng cho recursive SELECT. Aggregate và window functions không được đặt trong recursive SELECT. ORDER BY trong recursive member có thể ảnh hưởng thứ tự xử lý queue nội bộ, nhưng vẫn cần ORDER BY cuối nếu muốn bảo đảm thứ tự kết quả.

## 10. CTE materialization và optimizer

CTE không nhất thiết được lưu thành bảng vật lý.

### 10.1. PostgreSQL

~~~sql
WITH tong AS MATERIALIZED (
    SELECT customer_id, SUM(amount) AS total
    FROM orders
    GROUP BY customer_id
)
SELECT *
FROM tong;
~~~

PostgreSQL hỗ trợ `MATERIALIZED` và `NOT MATERIALIZED` trong phiên bản hiện đại. Materialization có thể tránh tính lại nhưng cũng có thể ngăn predicate pushdown hoặc tạo kết quả trung gian lớn.

### 10.2. SQL Server

CTE không được định nghĩa là bảng vật lý. Optimizer thường mở rộng CTE vào truy vấn; tham chiếu nhiều lần có thể khiến biểu thức được thực hiện lại tùy execution plan. Nếu cần lưu và tái sử dụng kết quả, xem xét temporary table.

### 10.3. MySQL, Oracle và SQLite

MySQL có thể merge hoặc materialize CTE; optimizer hints có thể điều khiển một số trường hợp. Oracle có thể inline/materialize theo plan và hints. SQLite hỗ trợ MATERIALIZED/NOT MATERIALIZED trong phiên bản phù hợp. Dùng EXPLAIN/plan để xác nhận hành vi thật.

## 11. Hàm cửa sổ là gì?

Hàm cửa sổ tính trên tập hàng liên quan nhưng **không gom các hàng thành một hàng tổng hợp** như GROUP BY.

Tạo dữ liệu:

~~~sql
CREATE TABLE doanh_thu (
    id INTEGER PRIMARY KEY,
    nhan_vien VARCHAR(50) NOT NULL,
    khu_vuc VARCHAR(30) NOT NULL,
    ngay_ban DATE NOT NULL,
    so_tien DECIMAL(12,2) NOT NULL
);

INSERT INTO doanh_thu
    (id, nhan_vien, khu_vuc, ngay_ban, so_tien)
VALUES
    (1, 'An',   'Bac', '2026-01-01', 100),
    (2, 'Binh', 'Bac', '2026-01-01', 200),
    (3, 'An',   'Bac', '2026-01-02', 150),
    (4, 'Chi',  'Nam', '2026-01-01', 300),
    (5, 'Dung', 'Nam', '2026-01-02', 120),
    (6, 'Binh', 'Bac', '2026-01-03', 250);
~~~

GROUP BY:

~~~sql
SELECT khu_vuc, SUM(so_tien) AS tong
FROM doanh_thu
GROUP BY khu_vuc;
~~~

Kết quả chỉ còn một hàng cho mỗi khu vực.

Window:

~~~sql
SELECT
    id,
    nhan_vien,
    khu_vuc,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY khu_vuc
    ) AS tong_khu_vuc
FROM doanh_thu
ORDER BY id;
~~~

Mỗi đơn vẫn có một hàng, đồng thời hiển thị tổng khu vực.

### 11.1. Cấu trúc OVER

~~~sql
function_name(expression) OVER (
    [PARTITION BY expression, ...]
    [ORDER BY expression, ...]
    [frame_clause]
)
~~~

- PARTITION BY chia tập thành các nhóm độc lập.
- ORDER BY xác định thứ tự trong partition.
- Frame giới hạn các hàng được hàm aggregate/value xét quanh hàng hiện tại.

ORDER BY trong OVER không thay thế ORDER BY cuối của câu SELECT.

## 12. Ranking functions

| Hàm | Ý nghĩa |
| --- | --- |
| ROW_NUMBER | Số thứ tự duy nhất từng hàng |
| RANK | Các giá trị bằng nhau cùng hạng; hạng sau bị nhảy |
| DENSE_RANK | Các giá trị bằng nhau cùng hạng; không nhảy số |
| NTILE(n) | Chia hàng thành n nhóm gần bằng nhau |
| PERCENT_RANK | Hạng tương đối |
| CUME_DIST | Tỷ lệ hàng có thứ tự nhỏ hơn hoặc bằng hàng hiện tại |

~~~sql
SELECT
    nhan_vien,
    khu_vuc,
    so_tien,
    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC, id
    ) AS row_num,
    RANK() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC
    ) AS rank_num,
    DENSE_RANK() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC
    ) AS dense_rank_num
FROM doanh_thu
ORDER BY khu_vuc, so_tien DESC, id;
~~~

Nếu cần đúng N hàng, dùng ROW_NUMBER và tie-break duy nhất. Nếu muốn giữ tất cả hàng đồng hạng, dùng RANK hoặc DENSE_RANK theo định nghĩa nghiệp vụ.

| Giá trị | ROW_NUMBER | RANK | DENSE_RANK |
| ---: | ---: | ---: | ---: |
| 300 | 1 | 1 | 1 |
| 250 | 2 | 2 | 2 |
| 250 | 3 | 2 | 2 |
| 200 | 4 | 4 | 3 |

ROW_NUMBER không có tie-break có thể cho thứ tự không xác định giữa các hàng đồng giá trị.

## 13. LAG, LEAD và value functions

`LAG` đọc giá trị từ hàng trước; `LEAD` đọc từ hàng sau theo thứ tự window.

~~~sql
SELECT
    nhan_vien,
    ngay_ban,
    so_tien,
    LAG(so_tien, 1, 0) OVER (
        PARTITION BY nhan_vien
        ORDER BY ngay_ban, id
    ) AS don_truoc,
    LEAD(so_tien) OVER (
        PARTITION BY nhan_vien
        ORDER BY ngay_ban, id
    ) AS don_sau
FROM doanh_thu;
~~~

Cú pháp thường gặp:

~~~sql
LAG(expression [, offset [, default]]) OVER (...)
LEAD(expression [, offset [, default]]) OVER (...)
~~~

Default thường dùng khi không có hàng tương ứng; nếu hàng trước có giá trị SQL NULL, kết quả vẫn là NULL, không tự thay bằng default.

`FIRST_VALUE`, `LAST_VALUE` và `NTH_VALUE` đọc giá trị ở vị trí trong frame. LAST_VALUE thường gây bất ngờ nếu frame mặc định chỉ kết thúc ở hàng hiện tại/peers. Muốn giá trị cuối toàn partition:

~~~sql
LAST_VALUE(so_tien) OVER (
    PARTITION BY nhan_vien
    ORDER BY ngay_ban, id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
~~~

## 14. Aggregate functions dưới dạng window

SUM, AVG, COUNT, MIN, MAX có thể dùng OVER:

~~~sql
SELECT
    id,
    nhan_vien,
    so_tien,
    COUNT(*) OVER (
        PARTITION BY nhan_vien
    ) AS so_don,
    SUM(so_tien) OVER (
        PARTITION BY nhan_vien
    ) AS tong,
    AVG(so_tien) OVER (
        PARTITION BY nhan_vien
    ) AS trung_binh
FROM doanh_thu;
~~~

Ví dụ tổng lũy kế theo nhân viên:

~~~sql
SELECT
    nhan_vien,
    ngay_ban,
    id,
    so_tien,
    SUM(so_tien) OVER (
        PARTITION BY nhan_vien
        ORDER BY ngay_ban, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke
FROM doanh_thu
ORDER BY nhan_vien, ngay_ban, id;
~~~

Thêm id vào ORDER BY để có thứ tự hàng xác định khi ngày trùng nhau.

## 15. Window frame: ROWS, RANGE, GROUPS

Frame xác định tập hàng mà hàm cửa sổ dùng.

### 15.1. ROWS

Đếm theo vị trí hàng:

~~~sql
AVG(so_tien) OVER (
    PARTITION BY nhan_vien
    ORDER BY ngay_ban, id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
~~~

Mỗi hàng tính trung bình chính nó và tối đa hai hàng đứng trước.

### 15.2. RANGE

Xác định theo giá trị sort key và peers. Các hàng có cùng giá trị ORDER BY có thể nằm trong cùng frame.

~~~sql
SUM(so_tien) OVER (
    ORDER BY ngay_ban
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Hai đơn cùng ngày có thể nhận cùng tổng lũy kế vì chúng là peers theo ngày.

### 15.3. GROUPS

Đếm theo nhóm peers, không theo từng hàng hoặc khoảng giá trị:

~~~sql
SUM(so_tien) OVER (
    ORDER BY ngay_ban
    GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
)
~~~

Cú pháp GROUPS không được mọi DBMS hỗ trợ. PostgreSQL và SQLite có hỗ trợ trong phiên bản phù hợp; không giả định MySQL hoặc SQL Server có cú pháp tương đương.

| Frame | Đếm theo | Ví dụ |
| --- | --- | --- |
| ROWS | Vị trí hàng | 3 giao dịch gần nhất |
| RANGE | Giá trị ORDER BY và peers | Tổng theo khoảng ngày |
| GROUPS | Nhóm peers | Nhóm ngày hiện tại và một nhóm trước |

### 15.4. Frame mặc định

Với ORDER BY trong window, nhiều DBMS dùng mặc định tương đương `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Các peers có thể cùng nhận kết quả. Nếu muốn running total từng hàng, thường nên khai báo rõ `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.

Không dựa vào default khi tính tiền lũy kế, số dư, chuỗi sự kiện hoặc các phép tính có sort key trùng.

## 16. Frame boundaries và EXCLUDE

Các biên thường gặp:

- UNBOUNDED PRECEDING: đầu partition.
- n PRECEDING: n hàng/nhóm trước.
- CURRENT ROW: hàng hiện tại hoặc peers tùy loại frame.
- n FOLLOWING: n hàng/nhóm sau.
- UNBOUNDED FOLLOWING: cuối partition.

Một số DBMS hỗ trợ EXCLUDE:

- EXCLUDE CURRENT ROW: bỏ hàng hiện tại.
- EXCLUDE GROUP: bỏ nhóm peers hiện tại.
- EXCLUDE TIES: bỏ peers khác nhưng giữ hàng hiện tại.
- EXCLUDE NO OTHERS: không loại thêm hàng nào.

~~~sql
AVG(so_tien) OVER (
    PARTITION BY khu_vuc
    ORDER BY ngay_ban
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    EXCLUDE CURRENT ROW
)
~~~

EXCLUDE có hỗ trợ khác nhau theo DBMS/phiên bản. Nếu không hỗ trợ, có thể dùng self-join hoặc correlated subquery; nếu dùng tổng trừ hàng hiện tại, phải xử lý NULL và số lượng hàng đúng.

## 17. Named WINDOW và FILTER

### 17.1. Named WINDOW

Một số DBMS cho đặt tên window để tái sử dụng:

~~~sql
SELECT
    id,
    nhan_vien,
    ngay_ban,
    so_tien,
    SUM(so_tien) OVER w AS tong_luy_ke,
    AVG(so_tien) OVER w AS tb_luy_ke
FROM doanh_thu
WINDOW w AS (
    PARTITION BY nhan_vien
    ORDER BY ngay_ban, id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
~~~

Named WINDOW có trong PostgreSQL, MySQL và SQLite; hỗ trợ/kế thừa window ở các DBMS khác khác nhau. SQL Server không có mệnh đề WINDOW cùng cú pháp thông dụng; có thể lặp OVER hoặc tách CTE.

### 17.2. FILTER

Một số DBMS hỗ trợ FILTER cho aggregate:

~~~sql
SELECT
    id,
    khu_vuc,
    SUM(so_tien) FILTER (
        WHERE so_tien >= 200
    ) OVER (
        PARTITION BY khu_vuc
    ) AS tong_don_lon
FROM doanh_thu;
~~~

Nếu không hỗ trợ, dùng CASE:

~~~sql
SELECT
    id,
    khu_vuc,
    SUM(
        CASE WHEN so_tien >= 200 THEN so_tien ELSE 0 END
    ) OVER (
        PARTITION BY khu_vuc
    ) AS tong_don_lon
FROM doanh_thu;
~~~

Đối với COUNT, `COUNT(CASE WHEN dieu_kien THEN 1 END)` đếm hàng thỏa điều kiện. Tránh `COUNT(CASE WHEN ... THEN 1 ELSE 0 END)` vì số 0 vẫn là non-NULL và bị đếm.

## 18. QUALIFY và lọc kết quả window

Window function thường được tính sau WHERE/GROUP BY/HAVING theo thứ tự xử lý logic. Vì vậy không thể lọc trực tiếp alias window trong WHERE cùng cấp ở nhiều DBMS.

Cách portable:

~~~sql
WITH xep_hang AS (
    SELECT
        id,
        nhan_vien,
        khu_vuc,
        so_tien,
        ROW_NUMBER() OVER (
            PARTITION BY khu_vuc
            ORDER BY so_tien DESC, id
        ) AS rn
    FROM doanh_thu
)
SELECT *
FROM xep_hang
WHERE rn = 1;
~~~

Một số hệ có `QUALIFY`:

~~~sql
SELECT
    id,
    nhan_vien,
    khu_vuc,
    so_tien,
    ROW_NUMBER() OVER (
        PARTITION BY khu_vuc
        ORDER BY so_tien DESC, id
    ) AS rn
FROM doanh_thu
QUALIFY rn = 1;
~~~

QUALIFY có ở Snowflake, BigQuery, Teradata và một số DBMS/phiên bản mới khác. PostgreSQL, MySQL và SQL Server truyền thống không có cú pháp này. CTE/subquery là phương án portable.

## 19. Top-N trong mỗi nhóm

Lấy tối đa ba hàng mỗi khu vực:

~~~sql
WITH x AS (
    SELECT
        id,
        nhan_vien,
        khu_vuc,
        so_tien,
        ROW_NUMBER() OVER (
            PARTITION BY khu_vuc
            ORDER BY so_tien DESC, id
        ) AS rn
    FROM doanh_thu
)
SELECT *
FROM x
WHERE rn <= 3
ORDER BY khu_vuc, rn;
~~~

- ROW_NUMBER <= N: tối đa N hàng.
- RANK <= N: giữ ties, có thể trả nhiều hơn N hàng.
- DENSE_RANK <= N: lấy N mức giá trị/hạng đầu, có thể nhiều hàng ở mỗi mức.

Phải xác định “top 3” nghĩa là ba hàng hay ba mức xếp hạng.

## 20. GROUPING SETS, ROLLUP và CUBE

Các mệnh đề này tạo nhiều cấp tổng hợp trong một truy vấn.

### 20.1. ROLLUP

`ROLLUP(a,b,c)` tạo các nhóm theo chuỗi tiền tố:

- (a,b,c)
- (a,b)
- (a)
- ()

~~~sql
SELECT
    khu_vuc,
    nhan_vien,
    SUM(so_tien) AS tong,
    GROUPING(khu_vuc) AS g_khu_vuc,
    GROUPING(nhan_vien) AS g_nhan_vien
FROM doanh_thu
GROUP BY ROLLUP (khu_vuc, nhan_vien);
~~~

Có tổng từng nhân viên trong khu vực, tổng từng khu vực và tổng toàn bộ.

### 20.2. CUBE

`CUBE(a,b)` tạo mọi tổ hợp: (a,b), (a), (b), ().

~~~sql
SELECT khu_vuc, nhan_vien, SUM(so_tien) AS tong
FROM doanh_thu
GROUP BY CUBE (khu_vuc, nhan_vien);
~~~

Với n chiều, CUBE có thể tạo tới 2^n grouping sets. Cẩn thận khi số chiều lớn.

### 20.3. GROUPING SETS

Chọn đúng các nhóm cần thiết:

~~~sql
SELECT khu_vuc, nhan_vien, SUM(so_tien) AS tong
FROM doanh_thu
GROUP BY GROUPING SETS (
    (khu_vuc, nhan_vien),
    (khu_vuc),
    ()
);
~~~

### 20.4. Phân biệt NULL subtotal và NULL dữ liệu

Subtotal có thể dùng NULL để biểu diễn chiều đã được tổng hợp. Nếu dữ liệu gốc cũng chứa NULL, dùng `GROUPING` hoặc `GROUPING_ID` (theo DBMS) để phân biệt.

### 20.5. Hỗ trợ theo DBMS

| DBMS | ROLLUP | CUBE | GROUPING SETS |
| --- | --- | --- | --- |
| PostgreSQL | Có | Có | Có |
| SQL Server | Có | Có | Có |
| Oracle | Có | Có | Có |
| MySQL | Có, cú pháp WITH ROLLUP | Không có cú pháp native tương đương phổ biến | Không có cú pháp native tương đương phổ biến |
| SQLite | Không native | Không native | Không native |

MySQL:

~~~sql
SELECT khu_vuc, nhan_vien, SUM(so_tien)
FROM doanh_thu
GROUP BY khu_vuc, nhan_vien WITH ROLLUP;
~~~

SQLite có thể mô phỏng bằng nhiều SELECT và UNION ALL, nhưng phải tự gắn nhãn subtotal và bảo đảm kiểu dữ liệu tương thích.

## 21. PIVOT và UNPIVOT

PIVOT chuyển giá trị của một cột thành cột đầu ra. UNPIVOT chuyển nhiều cột thành các hàng.

### 21.1. Conditional aggregation portable

~~~sql
SELECT
    khu_vuc,
    SUM(CASE WHEN quy = 'Q1' THEN doanh_thu ELSE 0 END) AS q1,
    SUM(CASE WHEN quy = 'Q2' THEN doanh_thu ELSE 0 END) AS q2
FROM doanh_thu_quy
GROUP BY khu_vuc;
~~~

Đây là cách dễ chuyển đổi giữa các DBMS. Dùng NULL thay 0 nếu muốn phân biệt không có dữ liệu với tổng bằng 0.

### 21.2. SQL Server PIVOT

~~~sql
SELECT khu_vuc, [Q1], [Q2]
FROM (
    SELECT khu_vuc, quy, doanh_thu
    FROM dbo.DoanhThuQuy
) AS src
PIVOT (
    SUM(doanh_thu)
    FOR quy IN ([Q1], [Q2])
) AS p;
~~~

### 21.3. Oracle PIVOT

~~~sql
SELECT *
FROM doanh_thu_quy
PIVOT (
    SUM(doanh_thu)
    FOR quy IN (
        'Q1' AS Q1,
        'Q2' AS Q2
    )
);
~~~

Cú pháp PIVOT của Oracle và SQL Server khác nhau. Danh sách pivot columns thường cố định; nếu cần pivot động, phải sinh SQL động và whitelist identifier.

### 21.4. SQL Server UNPIVOT

~~~sql
SELECT khu_vuc, quy, doanh_thu
FROM dbo.BangBaoCao
UNPIVOT (
    doanh_thu FOR quy IN ([Q1], [Q2], [Q3], [Q4])
) AS u;
~~~

UNPIVOT không nhất thiết phục hồi nguyên trạng mọi NULL hoặc metadata. Kiểm tra kiểu dữ liệu và cách xử lý NULL theo DBMS.

## 22. LATERAL và APPLY

LATERAL cho phép một FROM item tham chiếu cột của FROM item đứng trước. SQL Server có `CROSS APPLY` và `OUTER APPLY`.

PostgreSQL:

~~~sql
SELECT
    kh.id,
    kh.ten,
    don.id AS don_moi_nhat,
    don.tao_luc
FROM khach_hang AS kh
LEFT JOIN LATERAL (
    SELECT d.id, d.tao_luc
    FROM don_hang AS d
    WHERE d.khach_hang_id = kh.id
    ORDER BY d.tao_luc DESC, d.id DESC
    LIMIT 1
) AS don ON true;
~~~

SQL Server:

~~~sql
SELECT
    kh.Id,
    kh.Ten,
    don.Id AS DonMoiNhat,
    don.TaoLuc
FROM dbo.KhachHang AS kh
OUTER APPLY (
    SELECT TOP (1) d.Id, d.TaoLuc
    FROM dbo.DonHang AS d
    WHERE d.KhachHangId = kh.Id
    ORDER BY d.TaoLuc DESC, d.Id DESC
) AS don;
~~~

- CROSS APPLY gần với inner lateral: chỉ giữ hàng ngoài có kết quả.
- OUTER APPLY gần với left lateral: giữ hàng ngoài dù subquery không có hàng.

MySQL 8.0.14+ hỗ trợ LATERAL derived table trong các vị trí phù hợp. Oracle có LATERAL/APPLY theo phiên bản. SQLite không có cú pháp LATERAL tổng quát phổ biến; có thể dùng correlated subquery hoặc window CTE.

Phương án dùng window:

~~~sql
WITH x AS (
    SELECT
        d.*,
        ROW_NUMBER() OVER (
            PARTITION BY khach_hang_id
            ORDER BY tao_luc DESC, id DESC
        ) AS rn
    FROM don_hang AS d
)
SELECT kh.id, kh.ten, x.id AS don_moi_nhat
FROM khach_hang AS kh
LEFT JOIN x
  ON x.khach_hang_id = kh.id
 AND x.rn = 1;
~~~

## 23. FETCH FIRST, TOP và WITH TIES

PostgreSQL/Oracle:

~~~sql
SELECT *
FROM doanh_thu
ORDER BY so_tien DESC
FETCH FIRST 3 ROWS ONLY;
~~~

Giữ các hàng đồng hạng với hàng cuối:

~~~sql
SELECT *
FROM doanh_thu
ORDER BY so_tien DESC
FETCH FIRST 3 ROWS WITH TIES;
~~~

SQL Server:

~~~sql
SELECT TOP (3) WITH TIES *
FROM dbo.DoanhThu
ORDER BY SoTien DESC;
~~~

MySQL và SQLite thường dùng LIMIT, không có WITH TIES tương đương trong cú pháp thông dụng:

~~~sql
SELECT *
FROM doanh_thu
ORDER BY so_tien DESC
LIMIT 3;
~~~

Mô phỏng ties bằng RANK:

~~~sql
WITH x AS (
    SELECT d.*,
           RANK() OVER (ORDER BY so_tien DESC) AS r
    FROM doanh_thu AS d
)
SELECT *
FROM x
WHERE r <= 3
ORDER BY so_tien DESC;
~~~

Nếu muốn chính xác ba hàng, thêm khóa duy nhất vào ORDER BY của ROW_NUMBER. Nếu muốn giữ ties theo số tiền, không thêm id vào ORDER BY của RANK vì sẽ phá nhóm đồng hạng.

## 24. DISTINCT ON của PostgreSQL

PostgreSQL có extension `DISTINCT ON` để lấy một hàng đại diện mỗi nhóm:

~~~sql
SELECT DISTINCT ON (nhan_vien)
    nhan_vien,
    ngay_ban,
    so_tien
FROM doanh_thu
ORDER BY nhan_vien, ngay_ban DESC, id DESC;
~~~

Cách portable hơn:

~~~sql
WITH x AS (
    SELECT
        d.*,
        ROW_NUMBER() OVER (
            PARTITION BY nhan_vien
            ORDER BY ngay_ban DESC, id DESC
        ) AS rn
    FROM doanh_thu AS d
)
SELECT nhan_vien, ngay_ban, so_tien
FROM x
WHERE rn = 1;
~~~

## 25. NULLS FIRST và NULLS LAST

Một số DBMS hỗ trợ:

~~~sql
SELECT *
FROM nhan_vien
ORDER BY manager_id NULLS FIRST, id;
~~~

PostgreSQL và Oracle có cú pháp này. SQL Server và MySQL truyền thống không dùng cùng cú pháp. Có thể mô phỏng portable:

~~~sql
SELECT *
FROM nhan_vien
ORDER BY
    CASE WHEN manager_id IS NULL THEN 0 ELSE 1 END,
    manager_id,
    id;
~~~

Nếu dùng trong window function, biểu thức tương ứng phải nằm trong ORDER BY của OVER.

## 26. Kết hợp recursive CTE và window function

Một cách dễ hiểu là để recursive CTE xác định node/depth, sau đó CTE thường áp dụng window:

~~~sql
WITH RECURSIVE cay AS (
    SELECT id, manager_id, ho_ten, 0 AS cap
    FROM nhan_vien
    WHERE manager_id IS NULL

    UNION ALL

    SELECT nv.id, nv.manager_id, nv.ho_ten, c.cap + 1
    FROM nhan_vien nv
    JOIN cay c ON nv.manager_id = c.id
),
xep_so AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY cap
            ORDER BY id
        ) AS stt_trong_cap
    FROM cay
)
SELECT *
FROM xep_so
ORDER BY cap, stt_trong_cap;
~~~

Recursive member trong nhiều DBMS không cho aggregate/window functions. Tách hai tầng giúp dễ chuyển đổi: đệ quy tìm node, window tính hạng trên kết quả.

## 27. Kết hợp tổng hợp và window

Tính doanh thu mỗi nhân viên, hạng trong khu vực và tổng khu vực:

~~~sql
WITH tong_nhan_vien AS (
    SELECT khu_vuc, nhan_vien, SUM(so_tien) AS tong
    FROM doanh_thu
    GROUP BY khu_vuc, nhan_vien
),
xep_hang AS (
    SELECT
        khu_vuc,
        nhan_vien,
        tong,
        RANK() OVER (
            PARTITION BY khu_vuc
            ORDER BY tong DESC
        ) AS hang
    FROM tong_nhan_vien
)
SELECT
    khu_vuc,
    nhan_vien,
    tong,
    hang,
    SUM(tong) OVER (
        PARTITION BY khu_vuc
    ) AS tong_khu_vuc
FROM xep_hang
ORDER BY khu_vuc, hang, nhan_vien;
~~~

CTE đầu tiên tổng hợp; CTE thứ hai xếp hạng; SELECT cuối thêm tổng khu vực mà không làm mất từng nhân viên.

## 28. Bảng so sánh đa hệ quản trị

| Tính năng | PostgreSQL | MySQL 8 | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| CTE thường | Có | Có | Có | Có | Có |
| Recursive CTE | WITH RECURSIVE | WITH RECURSIVE | WITH | WITH factoring | WITH RECURSIVE |
| SEARCH/CYCLE | Có, bản hiện đại | Không cùng cú pháp | Không | Có | Không |
| Hierarchy riêng | CTE | CTE | CTE | CONNECT BY | CTE |
| Window functions | Có | Có | Có | Có | Có từ 3.25 |
| ROWS/RANGE | Có | Có | Có | Có | Có |
| GROUPS/EXCLUDE | Có theo version | Không cùng hỗ trợ | Không cùng hỗ trợ | Theo version | Có theo version |
| FILTER aggregate | Có | Không cùng cú pháp | Không | Theo version | Có |
| Named WINDOW | Có | Có | Không theo cú pháp thông dụng | Hỗ trợ theo cú pháp riêng | Có |
| QUALIFY | Không | Không | Không | Bản mới phù hợp | Không |
| ROLLUP | Có | Có | Có | Có | Không native |
| CUBE/GROUPING SETS | Có | Không native phổ biến | Có | Có | Không native |
| PIVOT/UNPIVOT | Không cùng cú pháp native | Không native | Có | Có | Không native |
| LATERAL/APPLY | LATERAL | LATERAL theo version | APPLY | LATERAL/APPLY | Không tổng quát |
| FETCH/TOP WITH TIES | FETCH | Không tương đương | TOP | FETCH | Không, mô phỏng |
| DISTINCT ON | Có | Không | Không | Không | Không |

Đây là bản đồ khái quát; luôn kiểm tra phiên bản và giới hạn cú pháp của môi trường thực tế.

## 29. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Recursive CTE thiếu điều kiện dừng | Đệ quy kéo dài hoặc vô hạn | Điều kiện dừng và cycle guard |
| Nghĩ UNION luôn ngăn cycle | Path/depth khác nhau vẫn được giữ | Theo dõi visited node |
| Không CAST path trong MySQL | Lỗi độ dài hoặc truncation | CAST anchor đủ dài |
| Bỏ MAXRECURSION SQL Server | Truy vấn vượt giới hạn | Đặt limit, vẫn kiểm tra cycle |
| Dựa vào thứ tự sinh CTE | Output không ổn định | ORDER BY cuối |
| Lọc trong recursive member khi chỉ muốn lọc output | Cắt nhánh con | Lọc sau recursive CTE |
| Duyệt mọi path graph lớn | Bùng nổ số hàng | Visited set/giới hạn/thuật toán phù hợp |
| Nhầm GROUP BY với window | Mất chi tiết từng hàng | Dùng OVER khi cần giữ hàng |
| ROW_NUMBER thiếu tie-break | Chọn hàng không xác định | Thêm khóa duy nhất |
| Dùng RANK khi muốn đúng N hàng | Có thể trả hơn N | ROW_NUMBER |
| Dùng ROW_NUMBER khi cần giữ ties | Mất hàng đồng hạng | RANK/DENSE_RANK |
| LAST_VALUE với frame mặc định | Không lấy cuối partition | UNBOUNDED FOLLOWING |
| Không chỉ rõ ROWS/RANGE | Peer rows làm tổng lũy kế bất ngờ | Khai báo frame |
| Nghĩ ORDER BY trong OVER sắp xếp output | Output không đảm bảo | ORDER BY ngoài cùng |
| Dùng window alias trong WHERE | Lỗi/alias chưa tồn tại | CTE/subquery/QUALIFY |
| FILTER không được hỗ trợ | Query không chạy | CASE WHEN |
| CUBE nhiều chiều | Quá nhiều grouping sets | Chọn GROUPING SETS |
| Nhầm NULL subtotal với NULL gốc | Báo cáo sai | GROUPING |
| PIVOT động không whitelist | Injection qua identifier | Whitelist tên cột |
| Dùng FETCH WITH TIES ở DBMS không hỗ trợ | Syntax error | TOP/RANK |
| Dùng DISTINCT ON ngoài PostgreSQL | Không portable | ROW_NUMBER |
| Dùng LATERAL không được hỗ trợ | Query lỗi | APPLY/correlated subquery/window CTE |
| Nghĩ CTE luôn materialize | Ước lượng hiệu năng sai | Xem execution plan |
| Đặt window trong recursive member | Không hỗ trợ ở nhiều DBMS | Tách tầng |
| Chỉ test cây một root | Bỏ sót nhiều root/orphan/cycle | Test dữ liệu biên |

## 30. Chọn công cụ theo bài toán

| Bài toán | Công cụ |
| --- | --- |
| Duyệt cây quản lý/danh mục | Recursive CTE hoặc Oracle CONNECT BY |
| Duyệt graph | Recursive CTE có path/visited; thuật toán graph nếu lớn |
| Xếp hạng trong nhóm | ROW_NUMBER/RANK/DENSE_RANK |
| Top-N mỗi nhóm | ROW_NUMBER + CTE |
| So sánh hàng trước/sau | LAG/LEAD |
| Tổng lũy kế | SUM OVER với frame tường minh |
| Trung bình trượt | AVG OVER ROWS |
| Giá trị đầu/cuối partition | FIRST_VALUE/LAST_VALUE với frame phù hợp |
| Nhiều cấp subtotal | ROLLUP/GROUPING SETS |
| Mọi tổ hợp chiều | CUBE nếu số chiều nhỏ |
| Hàng thành cột | PIVOT hoặc conditional aggregation |
| Một hàng mới nhất mỗi cha | LATERAL/APPLY hoặc ROW_NUMBER |
| Lọc kết quả window | QUALIFY hoặc CTE/subquery |
| Top-N giữ ties | FETCH/TOP WITH TIES hoặc RANK |
| Một hàng đại diện nhóm trong PostgreSQL | DISTINCT ON hoặc ROW_NUMBER |

## 31. Bài tập thực hành có lời giải

Các bài 1–10 dùng bảng nhan_vien; các bài còn lại dùng doanh_thu ở mục 11. Chạy trên database thử nghiệm.

### Bài 1. Đếm từ 1 đến 10

~~~sql
WITH RECURSIVE day_so(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1 FROM day_so WHERE n < 10
)
SELECT n FROM day_so ORDER BY n;
~~~

**Đáp án:** 10 hàng từ 1 đến 10. Điều kiện dừng là n < 10.

### Bài 2. Lấy toàn bộ cấp dưới của Minh

~~~sql
WITH RECURSIVE cap_duoi AS (
    SELECT id, manager_id, ho_ten, 0 AS cap
    FROM nhan_vien WHERE id = 2
    UNION ALL
    SELECT nv.id, nv.manager_id, nv.ho_ten, c.cap + 1
    FROM nhan_vien nv
    JOIN cap_duoi c ON nv.manager_id = c.id
)
SELECT * FROM cap_duoi ORDER BY cap, id;
~~~

**Đáp án:** Minh, Nam, Linh, Binh.

### Bài 3. Vì sao UNION không luôn chặn cycle?

**Đáp án:** UNION so sánh toàn bộ cột. Cùng node với path hoặc depth khác nhau vẫn là hàng khác. Cần visited/path hoặc CYCLE.

### Bài 4. Thứ tự depth-first

**Đáp án:** Dựng path rồi ORDER BY path ở SELECT cuối; PostgreSQL/Oracle cũng có SEARCH DEPTH FIRST ở phiên bản hỗ trợ.

### Bài 5. SQL Server giới hạn recursion

**Đáp án:** Dùng `OPTION (MAXRECURSION n)`. Đây là giới hạn bảo vệ, không thay điều kiện dừng.

### Bài 6. MySQL path string

**Đáp án:** CAST path ở anchor thành CHAR đủ dài, nối ID ở recursive member và dùng LOCATE với dấu phân cách để phát hiện node đã xuất hiện.

### Bài 7. Oracle hierarchy

**Đáp án:** START WITH chọn root, CONNECT BY PRIOR nối cha-con, LEVEL cho độ sâu. Dùng NOCYCLE khi cần bảo vệ truy vấn khỏi cycle.

### Bài 8. CTE có phải bảng tạm?

**Đáp án:** Không. CTE có phạm vi câu lệnh; optimizer có thể inline hoặc materialize tùy DBMS.

### Bài 9. Lọc output hay prune?

**Đáp án:** Lọc ở SELECT cuối giữ quá trình duyệt toàn cây; lọc trong recursive member có thể cắt luôn các nhánh bên dưới node không khớp.

### Bài 10. Graph có nhiều đường đi

**Đáp án:** Mang path trong recursive CTE và ngăn node lặp trên cùng path. Với graph lớn cần giới hạn hoặc thuật toán chuyên biệt.

### Bài 11. Tổng khu vực nhưng giữ từng đơn

~~~sql
SELECT id, khu_vuc, so_tien,
       SUM(so_tien) OVER (PARTITION BY khu_vuc) AS tong_vung
FROM doanh_thu;
~~~

**Đáp án:** Mỗi đơn vẫn xuất hiện, tổng khu vực được lặp trên từng hàng.

### Bài 12. Running total theo nhân viên

~~~sql
SELECT
    nhan_vien, ngay_ban, id, so_tien,
    SUM(so_tien) OVER (
        PARTITION BY nhan_vien
        ORDER BY ngay_ban, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS luy_ke
FROM doanh_thu;
~~~

**Đáp án:** Cộng từ hàng đầu của nhân viên đến hàng hiện tại.

### Bài 13. Hạng doanh thu trong khu vực

~~~sql
SELECT nhan_vien, khu_vuc, so_tien,
       DENSE_RANK() OVER (
           PARTITION BY khu_vuc ORDER BY so_tien DESC
       ) AS hang
FROM doanh_thu;
~~~

**Đáp án:** Mỗi khu vực xếp hạng riêng; đồng doanh thu cùng hạng và không nhảy số.

### Bài 14. Đọc doanh thu hàng trước

~~~sql
SELECT nhan_vien, ngay_ban, so_tien,
       LAG(so_tien) OVER (
           PARTITION BY nhan_vien ORDER BY ngay_ban, id
       ) AS don_truoc
FROM doanh_thu;
~~~

**Đáp án:** Hàng đầu mỗi nhân viên có SQL NULL vì không có hàng trước.

### Bài 15. LAST_VALUE lấy cuối partition

**Đáp án:** Dùng frame `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`; frame mặc định có thể kết thúc ở hàng hiện tại/peers.

### Bài 16. ROWS và RANGE

**Đáp án:** ROWS đếm vị trí hàng; RANGE xét giá trị ORDER BY và peers. Các đơn cùng ngày có thể nhận cùng tổng trong RANGE.

### Bài 17. Top 2 mỗi khu vực

~~~sql
WITH x AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY khu_vuc
               ORDER BY so_tien DESC, id
           ) AS rn
    FROM doanh_thu
)
SELECT * FROM x WHERE rn <= 2;
~~~

**Đáp án:** Tối đa hai hàng mỗi khu vực; dùng RANK nếu muốn giữ ties.

### Bài 18. Tổng đơn từ 200 trở lên

~~~sql
SELECT id,
       SUM(CASE WHEN so_tien >= 200 THEN so_tien ELSE 0 END)
           OVER (PARTITION BY khu_vuc) AS tong_don_lon
FROM doanh_thu;
~~~

**Đáp án:** CASE là cách thay FILTER tương thích rộng.

### Bài 19. Subtotal theo khu vực/nhân viên

~~~sql
SELECT khu_vuc, nhan_vien, SUM(so_tien)
FROM doanh_thu
GROUP BY ROLLUP (khu_vuc, nhan_vien);
~~~

**Đáp án:** Tổng theo cặp, tổng khu vực và tổng toàn bộ.

### Bài 20. Chỉ định nhóm tổng hợp

~~~sql
SELECT khu_vuc, nhan_vien, SUM(so_tien)
FROM doanh_thu
GROUP BY GROUPING SETS (
    (khu_vuc, nhan_vien), (khu_vuc), ()
);
~~~

**Đáp án:** Chỉ tạo ba cấp được liệt kê.

### Bài 21. Pivot không dùng extension

~~~sql
SELECT khu_vuc,
       SUM(CASE WHEN quy = 'Q1' THEN doanh_thu ELSE 0 END) AS q1,
       SUM(CASE WHEN quy = 'Q2' THEN doanh_thu ELSE 0 END) AS q2
FROM doanh_thu_quy
GROUP BY khu_vuc;
~~~

**Đáp án:** Conditional aggregation chuyển giá trị quý thành cột.

### Bài 22. Lấy đơn mới nhất mỗi khách

**Đáp án:** PostgreSQL dùng LEFT JOIN LATERAL; SQL Server dùng OUTER APPLY; phương án portable dùng ROW_NUMBER PARTITION BY khách hàng và LEFT JOIN.

### Bài 23. Top 3 giữ ties

**Đáp án:** PostgreSQL/Oracle dùng FETCH FIRST 3 ROWS WITH TIES; SQL Server dùng TOP (3) WITH TIES; DBMS khác có thể dùng RANK() <= 3.

### Bài 24. DISTINCT ON

**Câu hỏi:** Có thể dùng DISTINCT ON của PostgreSQL trong SQL Server không?

**Đáp án:** Không. Dùng ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) rồi lọc rn=1.

### Bài 25. NULLS LAST

**Đáp án:** Nếu DBMS không hỗ trợ cú pháp NULLS LAST, dùng ORDER BY CASE WHEN cot IS NULL THEN 1 ELSE 0 END, cot.

## 32. Checklist khi triển khai SQL nâng cao

1. DBMS và phiên bản nào đang chạy?
2. Recursive CTE có cú pháp WITH RECURSIVE hay không?
3. Anchor và recursive member có số cột/kiểu tương thích?
4. Có điều kiện dừng và cycle guard?
5. Dữ liệu có nhiều root, orphan, cycle hoặc graph nhiều path?
6. Cần node, mọi path hay đường ngắn nhất?
7. Có giới hạn recursion và timeout?
8. Thứ tự đầu ra có ORDER BY cuối?
9. CTE inline hay materialize theo plan?
10. Window partition có đúng nhóm nghiệp vụ?
11. ORDER BY có tie-break khi cần?
12. Frame ROWS/RANGE/GROUPS đã chọn đúng?
13. Có phụ thuộc frame mặc định?
14. LAST_VALUE/FIRST_VALUE có frame mong muốn?
15. NULL và peers được xử lý ra sao?
16. Cần đúng N hàng hay N mức hạng?
17. Lọc window bằng QUALIFY hay CTE/subquery?
18. FILTER có hỗ trợ hay cần CASE?
19. ROLLUP/CUBE/GROUPING SETS có sẵn?
20. Subtotal NULL có phân biệt với NULL dữ liệu?
21. PIVOT động có whitelist identifier?
22. LATERAL/APPLY có hỗ trợ?
23. FETCH WITH TIES/TOP/LIMIT có đúng semantics?
24. Execution plan có sort/spool/temp lớn?
25. Index hỗ trợ join recursion, partition và order?
26. Đã test ties, NULL, empty partition, cycle, nhiều root?
27. Có test riêng cho từng dialect?
28. Dynamic ORDER BY/PIVOT có nguy cơ SQL injection?
29. Có fallback portable khi extension không tồn tại?
30. Có đo trên dữ liệu gần production?

## 33. Tài liệu tham khảo chính thức

Đối chiếu theo đúng phiên bản DBMS:

- **PostgreSQL:** [WITH Queries](https://www.postgresql.org/docs/current/queries-with.html), [Window Functions](https://www.postgresql.org/docs/current/functions-window.html), [SELECT](https://www.postgresql.org/docs/current/sql-select.html), [Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html).
- **MySQL:** [WITH / CTE](https://dev.mysql.com/doc/refman/8.4/en/with.html), [Window Function Descriptions](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html), [Window Function Usage](https://dev.mysql.com/doc/refman/8.4/en/window-functions-usage.html), [GROUP BY Modifiers](https://dev.mysql.com/doc/refman/8.4/en/group-by-modifiers.html).
- **SQL Server:** [CTE](https://learn.microsoft.com/en-us/sql/t-sql/queries/with-common-table-expression-transact-sql), [OVER Clause](https://learn.microsoft.com/en-us/sql/t-sql/queries/select-over-clause-transact-sql), [PIVOT and UNPIVOT](https://learn.microsoft.com/en-us/sql/t-sql/queries/from-using-pivot-and-unpivot).
- **Oracle:** [SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/SELECT.html), [Hierarchical Queries](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/Hierarchical-Queries.html), [Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/Analytic-Functions.html).
- **SQLite:** [WITH Clause](https://www.sqlite.org/lang_with.html), [Window Functions](https://www.sqlite.org/windowfunctions.html), [SELECT](https://www.sqlite.org/lang_select.html).

## 34. Kết luận

- **CTE đệ quy** mở rộng tập kết quả qua từng vòng, phù hợp với cây phân cấp, quan hệ nhiều cấp và một số dạng graph traversal. Cần điều kiện dừng, cycle guard và giới hạn tài nguyên.
- **Hàm cửa sổ** tính hạng, giá trị trước/sau, tổng lũy kế, trung bình trượt và tổng theo partition mà vẫn giữ chi tiết từng hàng. Phải hiểu peers và frame, nhất là ROWS/RANGE/GROUPS.
- **Mệnh đề mở rộng** như SEARCH/CYCLE, FILTER, QUALIFY, GROUPING SETS, ROLLUP/CUBE, PIVOT, LATERAL/APPLY, FETCH WITH TIES và DISTINCT ON giúp truy vấn ngắn gọn nhưng không phải đều portable.
- **SQL đa hệ quản trị** đòi hỏi phân biệt cú pháp, kiểu dữ liệu, giới hạn recursion, frame support và cách optimizer thực thi.

Trước khi đưa truy vấn vào ứng dụng, hãy xác định **tập hàng nào được sinh, mỗi hàng thuộc partition nào, frame chứa những hàng nào, và DBMS đang dùng hỗ trợ chính xác cú pháp đó hay không**. Đây là nền tảng để truy vấn vừa đúng vừa vận hành ổn định.
