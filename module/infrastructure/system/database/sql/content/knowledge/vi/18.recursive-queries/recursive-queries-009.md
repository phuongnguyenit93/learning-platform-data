# Thứ tự duyệt và sắp xếp kết quả đệ quy

Khi dùng truy vấn đệ quy để đi qua cơ cấu tổ chức, danh mục nhiều cấp hoặc cây thư mục, câu hỏi thường không chỉ là **“lấy được những nút nào?”**. Người đọc còn muốn biết **“nút nào xuất hiện trước?”**:

- Xem lần lượt **từng cấp từ trên xuống**: gốc, toàn bộ con trực tiếp, rồi tới cháu. Đó là cách quan sát theo **chiều rộng** (*breadth-first search*, BFS).
- Xem **trọn một nhánh trước khi chuyển nhánh khác**: gốc, con thứ nhất, các hậu duệ của con đó, rồi con kế tiếp. Đó là cách quan sát theo **chiều sâu** (*depth-first search*, DFS).
- Trong mỗi cấp hoặc mỗi nhánh, ưu tiên một **thứ tự nghiệp vụ**, chẳng hạn `sibling_order`, thay vì dựa vào mã ID hoặc thứ tự các hàng tình cờ được trả về.

SQL có thể tạo các hàng của một cây bằng `WITH RECURSIVE`, nhưng **việc sinh ra những hàng đó không đồng nghĩa thứ tự hiển thị đã được bảo đảm**. Cần biểu diễn tiêu chí thứ tự trong dữ liệu truy vấn và sử dụng `ORDER BY` ở kết quả cuối. PostgreSQL còn cung cấp cú pháp `SEARCH BREADTH FIRST` và `SEARCH DEPTH FIRST` để tạo cột thứ tự một cách trực tiếp.

Bài học thuộc **Database SQL → Truy vấn đệ quy**, sử dụng PostgreSQL để thực hành. Trọng tâm là phân biệt **thứ tự xử lý đệ quy** với **thứ tự kết quả**, cách tạo khóa sắp xếp, và những giới hạn quan trọng khi cây có nhánh sâu, khóa trùng hoặc chu trình.

## 1. Từ một cây đến hai cách duyệt khác nhau

Giả sử ta có cây đơn vị sau. Các nhãn `(1)`, `(2)`, `(3)` ở cùng một cấp là **thứ tự giữa các nút anh em**, không phải mã ID:

~~~text
Cong ty
|-- (1) Kinh doanh
|   |-- (1) Noi dia
|   |   |-- (1) HCM
|   |   +-- (2) Ha Noi
|   +-- (2) Quoc te
|-- (2) Ky thuat
|   |-- (1) Backend
|   |   |-- (1) API
|   |   +-- (2) Du lieu
|   +-- (2) Frontend
+-- (3) Van hanh
    +-- (1) Ho tro
~~~

Cùng 13 nút trong cây có thể được liệt kê theo hai thứ tự:

| Thứ tự duyệt | Các nút theo thứ tự |
| --- | --- |
| **Theo chiều rộng (BFS)** | Công ty → Kinh doanh → Kỹ thuật → Vận hành → Nội địa → Quốc tế → Backend → Frontend → Hỗ trợ → HCM → Hà Nội → API → Dữ liệu |
| **Theo chiều sâu (DFS, kiểu tiền thứ tự)** | Công ty → Kinh doanh → Nội địa → HCM → Hà Nội → Quốc tế → Kỹ thuật → Backend → API → Dữ liệu → Frontend → Vận hành → Hỗ trợ |

Ở **BFS**, mọi nút cấp 1 đứng trước nút cấp 2. Ở **DFS**, nút HCM có thể xuất hiện trước Kỹ thuật mặc dù HCM ở cấp 3 còn Kỹ thuật ở cấp 1, vì DFS đi sâu vào nhánh Kinh doanh trước.

Đây là **hai yêu cầu sắp xếp khác nhau**, không phải hai tập dữ liệu khác nhau. Trong cả hai trường hợp, tập nút cuối cùng vẫn gồm đúng 13 nút của cây.

## 2. Tạo bảng phân cấp và dữ liệu mẫu

Trong database **PostgreSQL thực hành riêng**, hãy tạo bảng sau một lần, khi chưa có đối tượng `lab_rec230_units`. Mọi câu `SELECT` phía sau chỉ đọc dữ liệu.

~~~sql
CREATE TABLE lab_rec230_units (
    node_id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES lab_rec230_units(node_id),
    node_name VARCHAR(80) NOT NULL,
    sibling_order INTEGER NOT NULL CHECK (sibling_order > 0),
    UNIQUE (parent_id, sibling_order)
);
~~~

Ý nghĩa các cột:

| Cột | Vai trò |
| --- | --- |
| `node_id` | Khóa định danh **duy nhất** của đơn vị |
| `parent_id` | Khóa ngoại tham chiếu **nút cha**; `NULL` nghĩa là nút gốc |
| `node_name` | Tên hiển thị của đơn vị |
| `sibling_order` | Vị trí của nút **trong danh sách con của cùng một cha** |

Ràng buộc `UNIQUE (parent_id, sibling_order)` trong PostgreSQL ngăn hai nút con của **cùng một cha không-NULL** có cùng thứ tự. Với các gốc có `parent_id IS NULL`, tính duy nhất không được bảo đảm tương tự bởi ràng buộc `UNIQUE` mặc định vì PostgreSQL xem các `NULL` là khác nhau cho mục đích duy nhất; trong bài này chỉ dùng **một gốc**.

Chú ý: **`node_id` không được thiết kế theo thứ tự muốn hiển thị**. Ví dụ Kinh doanh có ID 20 nhưng đứng trước Kỹ thuật có ID 10. Điều này giúp thấy rõ rằng `ORDER BY node_id` không thay thế `ORDER BY sibling_order`.

~~~sql
INSERT INTO lab_rec230_units
    (node_id, parent_id, node_name, sibling_order)
VALUES
    (  1, NULL, 'Cong ty',     1),
    ( 20,    1, 'Kinh doanh',  1),
    ( 10,    1, 'Ky thuat',    2),
    ( 30,    1, 'Van hanh',    3),
    ( 60,   20, 'Noi dia',     1),
    ( 40,   20, 'Quoc te',     2),
    ( 70,   10, 'Backend',     1),
    ( 50,   10, 'Frontend',    2),
    ( 80,   30, 'Ho tro',      1),
    (110,   60, 'HCM',         1),
    ( 90,   60, 'Ha Noi',      2),
    (120,   70, 'API',         1),
    (100,   70, 'Du lieu',     2);
~~~

Các hàng được chèn theo thứ tự phù hợp với khóa ngoại để cha đã tồn tại trước khi con tham chiếu đến. Thứ tự viết câu `INSERT` **không phải là thứ tự đọc được bảo đảm** về sau.

Kiểm tra danh sách theo mã:

~~~sql
SELECT node_id, parent_id, node_name, sibling_order
FROM lab_rec230_units
ORDER BY node_id;
~~~

| node_id | parent_id | node_name | sibling_order |
| ---: | ---: | --- | ---: |
| 1 | `NULL` | Cong ty | 1 |
| 10 | 1 | Ky thuat | 2 |
| 20 | 1 | Kinh doanh | 1 |
| 30 | 1 | Van hanh | 3 |
| 40 | 20 | Quoc te | 2 |
| 50 | 10 | Frontend | 2 |
| 60 | 20 | Noi dia | 1 |
| 70 | 10 | Backend | 1 |
| 80 | 30 | Ho tro | 1 |
| 90 | 60 | Ha Noi | 2 |
| 100 | 70 | Du lieu | 2 |
| 110 | 60 | HCM | 1 |
| 120 | 70 | API | 1 |

Đây là thứ tự **theo ID**, chưa phải BFS hay DFS theo `sibling_order`.

## 3. WITH RECURSIVE: tạo tập hàng của cây

Truy vấn đệ quy thường có hai phần:

1. **Phần neo** (*anchor term*): xác định nút xuất phát, ví dụ gốc có `node_id = 1`.
2. **Phần đệ quy** (*recursive term*): từ các nút đã tìm thấy, lấy con có `parent_id` bằng `node_id` của nút hiện tại.

~~~sql
WITH RECURSIVE unit_walk (
    node_id, parent_id, node_name, sibling_order, depth
) AS (
    SELECT
        u.node_id,
        u.parent_id,
        u.node_name,
        u.sibling_order,
        0 AS depth
    FROM lab_rec230_units AS u
    WHERE u.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        child.sibling_order,
        walk.depth + 1
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT node_id, node_name, parent_id, sibling_order, depth
FROM unit_walk;
~~~

Ở truy vấn này:

- `unit_walk` là tên CTE đệ quy, không phải bảng mới lưu trong database.
- Phần neo sinh ra hàng gốc `Cong ty` với `depth = 0`.
- Mỗi lần nối `child.parent_id = walk.node_id` mở rộng sang các con.
- `depth + 1` lưu **cấp tính từ gốc**, không phải thứ tự đến lượt duyệt.
- `UNION ALL` giữ các hàng sinh ra, không tự loại trùng.

Với dữ liệu mẫu không có chu trình và mỗi nút có tối đa một cha, truy vấn thu được **13 nút**.

**Nhưng truy vấn chưa có `ORDER BY` ở cấp cuối. Không được dựa vào thứ tự thực tế mà SQL Editor hiển thị để kết luận các nút đã được sắp BFS hay DFS.**

### 3.1. Thứ tự thực thi nội bộ khác thứ tự trả kết quả

PostgreSQL triển khai xử lý CTE đệ quy theo những tập hàng làm việc kế tiếp; tài liệu PostgreSQL ghi nhận thuật toán thực thi hiện tại thường sinh ra đầu ra theo **thứ tự chiều rộng**. Tuy nhiên, **đó là đặc điểm triển khai, không phải cách yêu cầu thứ tự kết quả đáng tin cậy**. Thứ tự giữa các hàng ở cùng cấp cũng không được bảo đảm chỉ nhờ cách viết CTE.

Thêm `ORDER BY` trong phần `SELECT` cuối cùng là cách biểu đạt rõ **thứ tự mà người dùng cần nhận**. Thậm chí khi CTE có vẻ đang trả ra đúng thứ tự trong một lần thử, thay đổi kế hoạch thực thi, phép nối hoặc truy vấn bao ngoài có thể làm thứ tự ấy không còn phù hợp.

## 4. BFS: sắp theo độ sâu rồi theo thứ tự trong từng cấp

Đối với BFS, ta muốn:

~~~text
depth = 0: Cong ty
depth = 1: Kinh doanh, Ky thuat, Van hanh
depth = 2: Noi dia, Quoc te, Backend, Frontend, Ho tro
depth = 3: HCM, Ha Noi, API, Du lieu
~~~

Điều kiện quan trọng nhất là **`depth ASC`**. Tuy nhiên, `depth` một mình chỉ phân nhóm theo cấp; chưa quyết định thứ tự **giữa những nút cùng cấp**.

### 4.1. BFS đơn giản: depth rồi ID

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT
        node_id, parent_id, node_name,
        sibling_order, 0 AS depth
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id, child.parent_id, child.node_name,
        child.sibling_order, walk.depth + 1
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT node_id, node_name, depth
FROM unit_walk
ORDER BY depth ASC, node_id ASC;
~~~

Truy vấn trên **đúng về thứ tự theo cấp**, đồng thời xác định thứ tự bằng mã ID trong mỗi cấp. Nhưng kết quả ở `depth = 1` là **Kỹ thuật (10), Kinh doanh (20), Vận hành (30)**, khác yêu cầu nghiệp vụ **Kinh doanh trước Kỹ thuật**.

Đây là điểm dễ nhầm: **BFS chỉ quy định ưu tiên cấp nông trước cấp sâu; không tự quy định thứ tự anh em**. Quy tắc thứ tự anh em phải được xác định riêng.

### 4.2. Vì sao ORDER BY depth, sibling_order chưa đủ cho thứ tự nhánh?

Xét cách viết:

~~~sql
ORDER BY depth ASC, sibling_order ASC, node_id ASC
~~~

Tại `depth = 2`, các đơn vị Nội địa, Backend và Hỗ trợ đều có `sibling_order = 1` vì chúng thuộc **các cha khác nhau**. Truy vấn này sẽ gom những nút có thứ tự 1 ở mọi nhánh trước những nút thứ tự 2; nó có thể **xen kẽ con của các cha**, không còn đúng yêu cầu “đọc lần lượt các nhóm con theo thứ tự cha”.

Nếu cần BFS mà **các con của cha đứng trước cũng được giữ liền nhau**, phải mã hóa không chỉ thứ tự của chính nút, mà cả **chuỗi thứ tự các tổ tiên của nút**. Ta dùng **đường dẫn sắp xếp** ở mục sau.

## 5. Tạo đường dẫn sắp xếp từ gốc xuống từng nút

Trong PostgreSQL, mảng `INTEGER[]` có thể lưu chuỗi `sibling_order` từ gốc tới nút hiện tại.

Ví dụ:

| Nút | `sort_path` | Ý nghĩa |
| --- | --- | --- |
| Cong ty | `{1}` | Gốc |
| Kinh doanh | `{1,1}` | Con thứ 1 của gốc |
| Ky thuat | `{1,2}` | Con thứ 2 của gốc |
| Noi dia | `{1,1,1}` | Con thứ 1 của Kinh doanh |
| Quoc te | `{1,1,2}` | Con thứ 2 của Kinh doanh |
| HCM | `{1,1,1,1}` | Con thứ 1 của Nội địa |
| Ha Noi | `{1,1,1,2}` | Con thứ 2 của Nội địa |
| Backend | `{1,2,1}` | Con thứ 1 của Kỹ thuật |

Ta bổ sung cột `sort_path` vào CTE đệ quy:

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT
        u.node_id,
        u.parent_id,
        u.node_name,
        u.sibling_order,
        0 AS depth,
        ARRAY[u.sibling_order]::integer[] AS sort_path
    FROM lab_rec230_units AS u
    WHERE u.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        child.sibling_order,
        walk.depth + 1,
        walk.sort_path || child.sibling_order
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT
    node_id,
    node_name,
    depth,
    sort_path
FROM unit_walk
ORDER BY sort_path;
~~~

Phần quan trọng:

- `ARRAY[u.sibling_order]::integer[]` tạo mảng đường dẫn cho gốc.
- `walk.sort_path || child.sibling_order` nối thêm thứ tự của con vào cuối mảng đường dẫn của cha.
- Các mảng được **so theo phần tử từ trái sang phải** trong thứ tự mảng của PostgreSQL; khi một mảng là tiền tố của mảng kia, mảng ngắn hơn đứng trước.
- Vì mỗi nhóm con trong dữ liệu mẫu có thứ tự riêng **không trùng**, đường dẫn xác định duy nhất vị trí của một nút trong cây xuất phát từ gốc 1.

Ví dụ: `{1,1}` (Kinh doanh) đứng trước `{1,1,1}` (Nội địa), và **toàn bộ** đường dẫn bắt đầu bằng `{1,1,...}` đứng trước đường dẫn `{1,2}` (Kỹ thuật). Đó chính là cách tạo **thứ tự chiều sâu theo nhánh**.

Lưu ý cho dữ liệu thực: nếu nhiều nút anh em có cùng `sibling_order`, hai đường dẫn có thể hòa hoặc tạo thứ tự không mong muốn. Cần ràng buộc thứ tự anh em duy nhất, hoặc bổ sung khóa định danh ổn định vào **mỗi đoạn của đường dẫn**. Chỉ thêm `ORDER BY node_id` ở cuối không luôn diễn đạt đúng quy tắc duyệt nếu các nhánh đã có đường dẫn trùng nhau.

## 6. DFS: dùng ORDER BY sort_path

Truy vấn ở mục 5 với:

~~~sql
ORDER BY sort_path ASC
~~~

trả **DFS kiểu tiền thứ tự** (*depth-first preorder*): gặp cha trước rồi đi sâu hết nhánh con đầu tiên trước khi chuyển sang nhánh kế tiếp.

Kết quả mẫu theo `node_id`:

| Vị trí | node_id | node_name | depth | sort_path |
| ---: | ---: | --- | ---: | --- |
| 1 | 1 | Cong ty | 0 | `{1}` |
| 2 | 20 | Kinh doanh | 1 | `{1,1}` |
| 3 | 60 | Noi dia | 2 | `{1,1,1}` |
| 4 | 110 | HCM | 3 | `{1,1,1,1}` |
| 5 | 90 | Ha Noi | 3 | `{1,1,1,2}` |
| 6 | 40 | Quoc te | 2 | `{1,1,2}` |
| 7 | 10 | Ky thuat | 1 | `{1,2}` |
| 8 | 70 | Backend | 2 | `{1,2,1}` |
| 9 | 120 | API | 3 | `{1,2,1,1}` |
| 10 | 100 | Du lieu | 3 | `{1,2,1,2}` |
| 11 | 50 | Frontend | 2 | `{1,2,2}` |
| 12 | 30 | Van hanh | 1 | `{1,3}` |
| 13 | 80 | Ho tro | 2 | `{1,3,1}` |

Cách viết này phù hợp khi muốn:

- Hiển thị cây có thụt đầu dòng.
- Xuất cấu trúc phân cấp theo nhánh.
- Hiển thị một menu mà các mục con nằm ngay sau mục cha.
- Tạo thứ tự trình bày các đơn vị theo quy tắc anh em của từng cấp.

### 6.1. Nếu xếp theo đường dẫn ID thì sao?

Một biến thể thường gặp là dùng `ARRAY[node_id]` và nối thêm `child.node_id`. Kết quả vẫn có tính chất **đường dẫn đệ quy**, nhưng các nhánh được xếp theo **giá trị ID**, không theo `sibling_order`.

Trong dữ liệu mẫu, Kỹ thuật có ID 10 và Kinh doanh có ID 20. Nếu đường dẫn dựa trên `node_id` thì Kỹ thuật có thể đứng trước Kinh doanh, dù `sibling_order` yêu cầu điều ngược lại.

Đường dẫn cần phản ánh **thứ tự nghiệp vụ muốn dùng**, không chỉ một chuỗi khóa tùy ý. Mã ID có thể dùng làm yếu tố phân định cuối khi các tiêu chí nghiệp vụ bằng nhau.

## 7. BFS giữ đúng thứ tự nhánh: ORDER BY depth, sort_path

Đã có hai thông tin:

- `depth`: nút ở **cấp nào**.
- `sort_path`: vị trí của nút trong **cấu trúc thứ tự từ gốc**.

Với BFS theo cấp nhưng vẫn giữ thứ tự nhánh, dùng:

~~~sql
ORDER BY depth ASC, sort_path ASC
~~~

Truy vấn hoàn chỉnh:

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT
        u.node_id,
        u.parent_id,
        u.node_name,
        u.sibling_order,
        0 AS depth,
        ARRAY[u.sibling_order]::integer[] AS sort_path
    FROM lab_rec230_units AS u
    WHERE u.node_id = 1

    UNION ALL

    SELECT
        child.node_id,
        child.parent_id,
        child.node_name,
        child.sibling_order,
        walk.depth + 1,
        walk.sort_path || child.sibling_order
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT node_id, node_name, depth, sort_path
FROM unit_walk
ORDER BY depth ASC, sort_path ASC;
~~~

Kết quả theo mã ID:

~~~text
1,
20, 10, 30,
60, 40, 70, 50, 80,
110, 90, 120, 100
~~~

Giải thích:

1. Tất cả nút cấp 0 trước cấp 1; tất cả cấp 1 trước cấp 2; tương tự tới cấp 3.
2. Ở cấp 1, đường dẫn `{1,1}` của Kinh doanh trước `{1,2}` của Kỹ thuật và `{1,3}` của Vận hành.
3. Ở cấp 2, Nội địa và Quốc tế (thuộc Kinh doanh) đứng trước Backend và Frontend (thuộc Kỹ thuật), rồi mới đến Hỗ trợ (thuộc Vận hành).
4. Ở cấp 3, HCM, Hà Nội xuất hiện trước API và Dữ liệu do nhánh Kinh doanh đứng trước nhánh Kỹ thuật.

| Mệnh đề cuối | Thứ tự được xác định |
| --- | --- |
| `ORDER BY depth` | Cấp nông trước cấp sâu; **không bảo đảm trong cùng cấp** |
| `ORDER BY depth, node_id` | Cấp nông trước; trong cấp xếp theo **ID** |
| `ORDER BY depth, sibling_order, node_id` | Cấp nông trước; trong cấp xếp theo **số thứ tự của chính nút**, có thể xen kẽ các cha |
| `ORDER BY depth, sort_path` | Cấp nông trước; trong cấp giữ **thứ tự nhánh từ gốc** |
| `ORDER BY sort_path` | DFS kiểu cha trước con, theo **từng nhánh** |

Điều khác biệt giữa BFS và DFS trong hai truy vấn cuối **chỉ là khóa `ORDER BY`**. Tập hàng do CTE đệ quy tạo ra không thay đổi.

## 8. PostgreSQL SEARCH BREADTH FIRST và SEARCH DEPTH FIRST

Từ **PostgreSQL 14**, cú pháp SQL `SEARCH` được hỗ trợ cho CTE đệ quy. Nó có thể tạo **cột thứ tự duyệt** mà không cần tự viết phép nối mảng trong phần đệ quy.

Mẫu cú pháp:

~~~sql
WITH RECURSIVE ten_cte(...) AS (
    -- Phan neo
    ...
    UNION ALL
    -- Phan de quy
    ...
)
SEARCH DEPTH FIRST BY cot_thu_tu SET sort_column
SELECT ...
FROM ten_cte
ORDER BY sort_column;
~~~

**Quan trọng:** `SEARCH` xây dựng **khóa sắp xếp** cho một thứ tự duyệt, không tự thay thế lời yêu cầu `ORDER BY` ở truy vấn cuối. Muốn đầu ra có thứ tự, hãy **`ORDER BY` cột được tạo bởi `SEARCH`**.

### 8.1. SEARCH DEPTH FIRST

~~~sql
WITH RECURSIVE unit_walk (
    node_id, parent_id, node_name, sibling_order, depth
) AS (
    SELECT
        node_id, parent_id, node_name,
        sibling_order, 0 AS depth
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id, child.parent_id, child.node_name,
        child.sibling_order, walk.depth + 1
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SEARCH DEPTH FIRST BY sibling_order, node_id SET dfs_order
SELECT node_id, node_name, depth
FROM unit_walk
ORDER BY dfs_order;
~~~

Kết quả theo ID là:

~~~text
1, 20, 60, 110, 90, 40, 10, 70, 120, 100, 50, 30, 80
~~~

`SEARCH DEPTH FIRST BY sibling_order, node_id SET dfs_order` tạo một khóa có thông tin đường đi. Khi sắp theo khóa đó, các nhánh được duyệt từ gốc xuống trước khi chuyển sang nhánh kế tiếp. `node_id` được dùng như yếu tố **phân định** cùng với thứ tự anh em, hữu ích khi mô hình dữ liệu không đảm bảo thứ tự anh em duy nhất.

Không cần hiển thị `dfs_order` cho người dùng cuối: chỉ dùng nó trong `ORDER BY` là đủ. Nếu muốn quan sát cấu trúc khóa ở PostgreSQL, có thể thêm `dfs_order` vào danh sách `SELECT`, nhưng không nên phụ thuộc vào cách hiển thị văn bản của kiểu dữ liệu này để làm giao diện bền vững qua các hệ quản trị.

### 8.2. SEARCH BREADTH FIRST

Thay một từ khóa:

~~~sql
WITH RECURSIVE unit_walk (
    node_id, parent_id, node_name, sibling_order, depth
) AS (
    SELECT
        node_id, parent_id, node_name,
        sibling_order, 0 AS depth
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id, child.parent_id, child.node_name,
        child.sibling_order, walk.depth + 1
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SEARCH BREADTH FIRST BY sibling_order, node_id SET bfs_order
SELECT node_id, node_name, depth
FROM unit_walk
ORDER BY bfs_order;
~~~

Ở mức **độ sâu**, kết quả đúng theo BFS: gốc trước, rồi cấp 1, cấp 2, cấp 3. Nhưng với PostgreSQL, khóa thứ tự BFS do `SEARCH` tạo dựa trên **cấp** và các cột trong `BY` của **nút đó**. Khi nhiều cha ở cùng cấp có con cùng `sibling_order`, thứ tự giữa những con ấy có thể được phân định bằng `node_id` và **xen kẽ nhánh cha**.

Với dữ liệu mẫu, các nút **cấp 2** khi dùng `SEARCH BREADTH FIRST BY sibling_order, node_id` được xếp theo:

~~~text
Noi dia (order 1, ID 60)
Backend (order 1, ID 70)
Ho tro (order 1, ID 80)
Quoc te (order 2, ID 40)
Frontend (order 2, ID 50)
~~~

Đây vẫn là **BFS hợp lệ**, vì tất cả các nút cấp 2 đều đứng sau cấp 1 và trước cấp 3. Nếu yêu cầu giao diện là **các con của từng cha phải đi liền nhau theo thứ tự cha**, hãy ưu tiên cách tự tạo `sort_path` và `ORDER BY depth, sort_path` ở mục 7.

### 8.3. Chọn SEARCH hay tự tạo đường dẫn?

| Cách | Ưu điểm | Điều cần cân nhắc |
| --- | --- | --- |
| `SEARCH DEPTH FIRST BY ... SET ...` | Cú pháp ngắn, mô tả rõ DFS | Cần hệ quản trị/phiên bản hỗ trợ; nhớ sắp theo cột tạo ra |
| `SEARCH BREADTH FIRST BY ... SET ...` | Cú pháp ngắn, phân cấp theo chiều rộng | Thứ tự cùng cấp dựa trên các cột `BY`, không tự biểu diễn mọi quy tắc nhóm con theo cha |
| Mảng `sort_path` + `ORDER BY sort_path` | Tùy biến đường đi, thuận tiện cho hiển thị cây | Tốn thêm dữ liệu đường dẫn; phải kiểm soát trùng thứ tự và chu trình |
| `depth` + `sort_path` + `ORDER BY depth, sort_path` | BFS rõ thứ tự cấp và cấu trúc nhánh | Cần tạo cả độ sâu và đường dẫn |

`SEARCH` là cách **tạo khóa thứ tự** theo chuẩn được PostgreSQL hỗ trợ, nhưng không phải mọi SQL dialect có cùng cú pháp. Ví dụ dùng mảng `INTEGER[]` cũng mang tính PostgreSQL; phần ý tưởng vẫn có thể được biểu diễn bằng chuỗi đường dẫn hoặc cơ chế phù hợp ở hệ khác.

## 9. Trình bày cây với thụt dòng

Khi đã có thứ tự DFS, có thể kết hợp `depth` để trình bày độ sâu của mỗi nút. Trong PostgreSQL, `REPEAT('  ', depth)` tạo hai khoảng trắng cho mỗi cấp.

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT
        node_id, parent_id, node_name, sibling_order,
        0 AS depth,
        ARRAY[sibling_order]::integer[] AS sort_path
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id, child.parent_id, child.node_name,
        child.sibling_order,
        walk.depth + 1,
        walk.sort_path || child.sibling_order
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT
    node_id,
    REPEAT('  ', depth) || node_name AS display_name,
    depth
FROM unit_walk
ORDER BY sort_path;
~~~

Kết quả `display_name` (khoảng trắng đầu dòng mang ý nghĩa mức):

~~~text
Cong ty
  Kinh doanh
    Noi dia
      HCM
      Ha Noi
    Quoc te
  Ky thuat
    Backend
      API
      Du lieu
    Frontend
  Van hanh
    Ho tro
~~~

**Phần thụt dòng chỉ là cách hiển thị.** Nó không tạo quan hệ cha–con trong dữ liệu; quan hệ vẫn do `parent_id` xác định. Nếu sử dụng `ORDER BY depth, sort_path` trong truy vấn này, các nút cùng cấp sẽ đứng thành từng nhóm cấp và kết quả không còn giống hình cây DFS có con nằm sát cha.

### 9.1. Đánh số thứ tự kết quả theo DFS

Khi cần số thứ tự 1, 2, 3, ..., có thể sử dụng hàm cửa sổ:

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT
        node_id, parent_id, node_name, sibling_order,
        0 AS depth, ARRAY[sibling_order]::integer[] AS sort_path
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id, child.parent_id, child.node_name, child.sibling_order,
        walk.depth + 1, walk.sort_path || child.sibling_order
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT
    ROW_NUMBER() OVER (ORDER BY sort_path) AS display_position,
    node_id,
    node_name,
    depth
FROM unit_walk
ORDER BY display_position;
~~~

`ROW_NUMBER() OVER (ORDER BY sort_path)` đánh số theo thứ tự DFS đã định nghĩa. Không nên nhầm con số này với `node_id`: vị trí hiển thị có thể đổi khi cấu trúc cây hoặc `sibling_order` thay đổi, còn ID nên là định danh ổn định.

## 10. Lọc dữ liệu ở đâu sẽ thay đổi phạm vi duyệt?

Với CTE đệ quy, cần phân biệt **lọc trong phần đệ quy** và **lọc ở SELECT cuối**.

### 10.1. Lọc ở cuối: đã sinh cây rồi mới chọn hàng hiển thị

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT node_id, parent_id, node_name, sibling_order, 0 AS depth
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT child.node_id, child.parent_id, child.node_name,
           child.sibling_order, walk.depth + 1
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT node_id, node_name, depth
FROM unit_walk
WHERE depth = 2
ORDER BY sibling_order, node_id;
~~~

Truy vấn này **đi qua cây theo logic đệ quy**, rồi chỉ hiển thị các nút cấp 2. Kết quả có **5 nút**: Nội địa, Quốc tế, Backend, Frontend, Hỗ trợ, được sắp theo `sibling_order, node_id` như yêu cầu cuối, không phải theo trình tự nhánh.

### 10.2. Giới hạn độ sâu trong phần đệ quy

Muốn **không mở rộng quá cấp 2**, thêm điều kiện trên hàng cha đang được mở rộng:

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT node_id, parent_id, node_name, sibling_order, 0 AS depth
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT child.node_id, child.parent_id, child.node_name,
           child.sibling_order, walk.depth + 1
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
    WHERE walk.depth < 2
)
SELECT node_id, node_name, depth
FROM unit_walk
ORDER BY depth, node_id;
~~~

Phần neo cấp 0 được lấy; từ cấp 0 tạo cấp 1; từ cấp 1 tạo cấp 2; **không mở rộng cấp 2 thành cấp 3**. Kết quả gồm **9 nút** ở cấp 0–2.

Điều kiện `WHERE walk.depth < 2` nằm trong **recursive term**: nó kiểm soát **mức mở rộng**, không chỉ giới hạn các hàng cuối cùng được hiển thị. Trái lại, điều kiện `WHERE depth <= 2` ở truy vấn cuối thông thường chỉ lọc **kết quả đã sinh ra**.

### 10.3. Lọc tên ở recursive term có thể cắt cả một nhánh

Nếu phần đệ quy thêm:

~~~sql
WHERE child.node_name <> 'Kinh doanh'
~~~

thì nút Kinh doanh sẽ không đi vào `unit_walk` và các con/cháu của nó **cũng không có đường được đi tiếp từ gốc**. Trong khi đó, đặt `WHERE node_name <> 'Kinh doanh'` ở truy vấn **ngoài** chỉ bỏ hàng Kinh doanh khỏi hiển thị; các con/cháu của Kinh doanh đã được sinh và vẫn có thể xuất hiện.

Điều này đặc biệt quan trọng với hệ thống phân quyền: ẩn một nút khỏi giao diện **khác** với cấm đi vào cả nhánh của nút đó. Quy tắc nghiệp vụ cần chỉ rõ có được nhìn thấy các hậu duệ của một nút không được phép xem hay không.

## 11. Chu trình và tính kết thúc: sắp xếp không giải quyết vòng lặp

Một truy vấn đệ quy dựa trên sơ đồ **cây** giả định không có chu trình (*cycle*). Nhưng dữ liệu quan hệ không phải lúc nào cũng là cây đúng chuẩn: có thể xuất hiện đồ thị cạnh A → B → C → A, lỗi dữ liệu khi cập nhật liên kết, hoặc mô hình cho phép một nút có nhiều cha.

Nếu dùng `UNION ALL` mà không kiểm soát chu trình, đệ quy có thể **tiếp tục sinh thêm hàng** rất lâu. `ORDER BY` ở ngoài **không cắt chu trình**; nó chỉ xác định thứ tự trình bày của kết quả nếu kết quả có thể được tạo ra.

### 11.1. Ví dụ đồ thị nhỏ có chu trình

Ta tạo cạnh trong một CTE tạm, không cần sửa bảng `lab_rec230_units`:

~~~text
1 --> 2 --> 3
^           |
|-----------|

2 --> 4
~~~

Các cạnh là 1 → 2, 2 → 3, 3 → 1 và 2 → 4. Từ nút 1 có một nhánh khép vòng.

PostgreSQL 14 trở lên hỗ trợ `CYCLE` để đánh dấu và chặn việc mở rộng các đường đã quay lại nút từng đi qua:

~~~sql
WITH RECURSIVE
edges(from_id, to_id) AS (
    VALUES (1, 2), (2, 3), (3, 1), (2, 4)
),
graph_walk(node_id, depth) AS (
    SELECT 1 AS node_id, 0 AS depth

    UNION ALL

    SELECT e.to_id, w.depth + 1
    FROM graph_walk AS w
    JOIN edges AS e
        ON e.from_id = w.node_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT node_id, depth, is_cycle
FROM graph_walk
ORDER BY depth, node_id;
~~~

Với dữ liệu này, có thể thấy nút 1 được gặp lại trên nhánh 1 → 2 → 3 → 1 và được đánh dấu `is_cycle = TRUE`. Cú pháp `CYCLE` thêm các cột kiểm tra đường đi cho CTE và ngăn tiếp tục mở rộng từ hàng đã đánh dấu chu trình.

`CYCLE` giải quyết **tính kết thúc và nhận diện đường lặp**, còn `SEARCH` hoặc `ORDER BY` giải quyết **thứ tự trình bày**. Hai nhiệm vụ khác nhau; không được thay một nhiệm vụ bằng nhiệm vụ còn lại.

### 11.2. Kiểm tra đường đã đi qua bằng mảng thủ công

Khi muốn viết rõ logic tránh thăm lại một nút **trên cùng một đường đi**, có thể giữ mảng `visited_ids`:

~~~sql
WITH RECURSIVE
edges(from_id, to_id) AS (
    VALUES (1, 2), (2, 3), (3, 1), (2, 4)
),
graph_walk(node_id, depth, visited_ids) AS (
    SELECT 1, 0, ARRAY[1]::integer[]

    UNION ALL

    SELECT
        e.to_id,
        w.depth + 1,
        w.visited_ids || e.to_id
    FROM graph_walk AS w
    JOIN edges AS e
        ON e.from_id = w.node_id
    WHERE NOT (e.to_id = ANY(w.visited_ids))
)
SELECT node_id, depth, visited_ids
FROM graph_walk
ORDER BY depth, visited_ids;
~~~

Kết quả đi tới các nút 1, 2, 3, 4, nhưng **không mở rộng quay lại 1** từ nút 3. `ANY(w.visited_ids)` kiểm tra nút đích đã có trên đường đi hiện tại hay chưa.

Với **đồ thị có nhiều đường tới cùng một nút**, một nút vẫn có thể được tìm thấy nhiều lần qua các đường **khác nhau**, dù mỗi đường không có chu trình. Do đó “tránh lặp trong một đường đi” và “mỗi nút xuất hiện đúng một lần trên toàn bộ kết quả” là **hai yêu cầu khác nhau**. Nếu cần kết quả một hàng trên mỗi nút, phải quy định cách chọn đường ưu tiên hoặc tổng hợp/loại trùng phù hợp.

### 11.3. UNION không phải cách chữa mọi chu trình

Đổi `UNION ALL` thành `UNION` có thể ngăn một số vòng lặp nếu CTE chỉ sinh những hàng thực sự **giống hệt** và không tạo giá trị mới. Nhưng khi CTE có cột `depth` tăng liên tục hoặc `sort_path` kéo dài, mỗi vòng lặp có thể tạo **một hàng khác**, nên `UNION` vẫn không bảo đảm kết thúc.

Không dùng `LIMIT` ở truy vấn ngoài làm biện pháp an toàn chính cho đệ quy sai. Khi có `ORDER BY` hoặc thao tác bao ngoài khác, hệ quản trị có thể cần tạo một lượng dữ liệu lớn hoặc toàn bộ kết quả trước khi trả các hàng đầu. Hãy kiểm soát chu trình và giới hạn mở rộng **ngay trong logic đệ quy** khi cần.

## 12. Kết quả nhiều gốc và lựa chọn nút bắt đầu

Bài thực hành chỉ có một gốc `node_id = 1`, nhưng dữ liệu thật có thể có nhiều cây độc lập. Nếu phần neo chọn:

~~~sql
WHERE parent_id IS NULL
~~~

thay vì `WHERE node_id = 1`, truy vấn sẽ bắt đầu từ **mọi gốc**. Khi đó, để sắp DFS hoặc BFS theo cây, phải có **thứ tự giữa các gốc** và cách phân biệt đường dẫn của mỗi gốc.

Ví dụ tư duy:

~~~text
Root A                     Root B
|-- A1                     |-- B1
+-- A2                     +-- B2
~~~

Nếu cả hai gốc cùng có `sibling_order = 1`, đường dẫn mảng `{1}` của chúng sẽ trùng nhau. Trong trường hợp nhiều gốc, có thể:

- Gán thứ tự gốc **duy nhất** theo nghiệp vụ và dùng nó làm phần tử đầu của đường dẫn.
- Hoặc lưu riêng `root_id` cùng một khóa thứ tự gốc và dùng thêm nó trong `ORDER BY`.
- Hoặc dùng `SEARCH ... BY` với những cột phân định phù hợp, đồng thời hiểu quy tắc sắp theo cấp hay theo nhánh.

Ví dụ cấu trúc khóa sắp xếp khi cần hiển thị **cây A trọn vẹn, rồi cây B trọn vẹn** có thể là `ORDER BY root_sort, sort_path`. Nếu cần **BFS trên toàn bộ rừng** (tất cả gốc, rồi tất cả con của các gốc), có thể là `ORDER BY depth, root_sort, sort_path`. Hai lựa chọn này khác nhau về ngữ nghĩa.

Không nên viết một mảng đường dẫn chỉ chứa `sibling_order` rồi giả định nó đủ phân định mọi hàng khi có nhiều gốc hoặc giá trị thứ tự bị trùng.

## 13. Sắp xếp và phân trang kết quả đệ quy

Giả sử giao diện chỉ hiển thị năm đơn vị đầu tiên theo DFS:

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT
        node_id, parent_id, node_name, sibling_order,
        0 AS depth,
        ARRAY[sibling_order]::integer[] AS sort_path
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id, child.parent_id, child.node_name,
        child.sibling_order, walk.depth + 1,
        walk.sort_path || child.sibling_order
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT node_id, node_name, depth
FROM unit_walk
ORDER BY sort_path
LIMIT 5 OFFSET 0;
~~~

Kết quả: **Công ty, Kinh doanh, Nội địa, HCM, Hà Nội**.

Trang kế tiếp với `LIMIT 5 OFFSET 5` trả: **Quốc tế, Kỹ thuật, Backend, API, Dữ liệu**. Các trang dựa trên **thứ tự DFS được xác định bằng đường dẫn**.

Vấn đề cần lưu ý:

- `LIMIT 5` **không có `ORDER BY`** không định nghĩa “năm nút đầu tiên” theo BFS hay DFS.
- `ORDER BY sort_path` chỉ ổn định nếu thứ tự đường dẫn đủ để **phân định những hàng khác nhau**.
- Khi thêm, xóa hoặc chuyển nhánh trong lúc người dùng xem nhiều trang, các vị trí có thể dịch chuyển; `OFFSET` có thể khiến trang sau lặp hoặc bỏ sót hàng. Tùy yêu cầu, có thể cần snapshot nhất quán, cơ chế phân trang theo khóa thích hợp hoặc giải pháp lưu trữ thứ tự.
- Sắp xếp toàn bộ kết quả trước `LIMIT` có thể tốn chi phí trên cây lớn. Không nên dùng `LIMIT` như một thay thế cho kiểm soát độ sâu hay chu trình.

Với giao diện cây tương tác, đôi khi phù hợp hơn là **chỉ lấy con trực tiếp của một nút khi người dùng mở rộng nút đó**, thay vì duyệt toàn bộ cây chỉ để hiển thị vài hàng đầu. Cách này cũng cần giữ `ORDER BY sibling_order, node_id` cho danh sách con trực tiếp.

## 14. Thứ tự trong phép tổng hợp không được suy ra từ thứ tự CTE

Không chỉ kết quả `SELECT`: nếu gom tên nút thành chuỗi hoặc mảng, thứ tự bên trong `STRING_AGG`/`ARRAY_AGG` cũng cần được chỉ định.

Ví dụ liệt kê **các con trực tiếp của từng cha** theo `sibling_order`:

~~~sql
SELECT
    parent_id,
    STRING_AGG(
        node_name,
        ', ' ORDER BY sibling_order, node_id
    ) AS child_names
FROM lab_rec230_units
WHERE parent_id IS NOT NULL
GROUP BY parent_id
ORDER BY parent_id;
~~~

Một số kết quả:

| parent_id | child_names |
| ---: | --- |
| 1 | Kinh doanh, Ky thuat, Van hanh |
| 10 | Backend, Frontend |
| 20 | Noi dia, Quoc te |
| 60 | HCM, Ha Noi |
| 70 | API, Du lieu |

`ORDER BY sibling_order, node_id` **bên trong `STRING_AGG`** xác định thứ tự các tên trong chuỗi của từng nhóm. `ORDER BY parent_id` **ở cuối** xác định thứ tự **các hàng nhóm**. Hai thứ tự có phạm vi khác nhau.

Không dựa vào việc bảng hoặc CTE đầu vào tình cờ có thứ tự đã sắp để mong `STRING_AGG` hay `ARRAY_AGG` luôn giữ thứ tự đó. Nếu thứ tự của các phần tử trong giá trị tổng hợp có ý nghĩa, hãy viết **`ORDER BY` trong chính hàm tổng hợp** ở hệ hỗ trợ.

## 15. Hiệu năng và giới hạn trong truy vấn phân cấp lớn

Một truy vấn đệ quy có thể phải tạo rất nhiều hàng; việc sắp xếp còn cần so sánh khóa, đường dẫn hoặc cột do `SEARCH` sinh ra.

### 15.1. Chỉ mục trên khóa tìm con

Trong ví dụ, `node_id` là khóa chính nên PostgreSQL tạo chỉ mục phục vụ tìm nút theo ID. Phần đệ quy lại thường xuyên tìm các hàng con bằng:

~~~sql
child.parent_id = walk.node_id
~~~

Khóa ngoại **không nhất thiết được PostgreSQL tự tạo chỉ mục** trên cột `parent_id`. Với bảng đủ lớn, một chỉ mục như sau **có thể** hữu ích:

~~~sql
-- Lenh DDL minh hoa: chi chay khi can trong database thuc hanh.
CREATE INDEX lab_rec230_parent_sort_idx
ON lab_rec230_units (parent_id, sibling_order, node_id);
~~~

Chỉ mục này có thể hỗ trợ tra cứu con của một cha và một số thao tác liên quan thứ tự con. Tuy nhiên, nó là **thay đổi cấu trúc thật**, tốn không gian và chi phí duy trì; bộ tối ưu có thể không dùng với bảng chỉ 13 hàng.

### 15.2. Độ sâu và kích thước đường dẫn

Khi tạo `sort_path` bằng mảng, mỗi cấp mở rộng sẽ thêm một phần tử vào đường dẫn. Cây càng sâu thì đường dẫn càng dài. Việc sao chép mảng và sắp xếp nhiều mảng dài có thể tốn tài nguyên.

Giải pháp tùy bài toán:

- Nếu chỉ cần danh sách **cấp 0, 1, 2**, giới hạn đệ quy ở cấp cần dùng.
- Nếu chỉ cần con trực tiếp của một nút, truy vấn thường `WHERE parent_id = ... ORDER BY sibling_order` có thể đơn giản hơn CTE đệ quy.
- Nếu truy vấn cây rất thường xuyên và khối lượng lớn, có thể cân nhắc mô hình đường dẫn lưu sẵn, bảng closure, cơ chế riêng của hệ quản trị hoặc vật hóa kết quả, với chi phí cập nhật và nhất quán đi kèm.
- Nếu kết quả chỉ phục vụ báo cáo theo từng đợt, có thể tạo snapshot và sắp xếp trên snapshot nhất quán thay vì duyệt lại trong lúc dữ liệu liên tục thay đổi.

### 15.3. Xem kế hoạch PostgreSQL

~~~sql
EXPLAIN
WITH RECURSIVE unit_walk AS (
    SELECT node_id, parent_id, 0 AS depth
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT child.node_id, child.parent_id, walk.depth + 1
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT node_id, depth
FROM unit_walk
ORDER BY depth, node_id;
~~~

`EXPLAIN` cung cấp kế hoạch dự kiến; trong PostgreSQL thường có thao tác liên quan `Recursive Union` hoặc quét bảng làm việc (*work table*) tùy cách trình bày kế hoạch. Nó không thay đổi quy tắc rằng **thứ tự đầu ra được yêu cầu bởi `ORDER BY`**. Kế hoạch thực tế còn phụ thuộc kích thước dữ liệu và thống kê.

## 16. Khác biệt giữa các hệ quản trị SQL

Không phải SQL dialect nào cũng hỗ trợ `SEARCH`, `CYCLE` hoặc kiểu mảng `INTEGER[]` như PostgreSQL. Vì vậy cần tách **ý tưởng duyệt** và **cú pháp đặc thù**:

| Hệ quản trị | Truy vấn đệ quy | Thứ tự BFS/DFS | Ghi chú |
| --- | --- | --- | --- |
| **PostgreSQL 14+** | `WITH RECURSIVE` | `SEARCH BREADTH FIRST`, `SEARCH DEPTH FIRST`; hoặc tự tạo đường dẫn | Có `CYCLE` và kiểu mảng, cần `ORDER BY` ở cuối |
| **PostgreSQL cũ hơn** | `WITH RECURSIVE` | Tự tạo `depth` và `path`, sắp `ORDER BY` | `SEARCH`/`CYCLE` chưa có ở các bản trước 14 |
| **MySQL 8.0+** | `WITH RECURSIVE` | Tự tạo cấp/đường dẫn theo kiểu và hàm phù hợp | Không dùng nguyên cú pháp mảng PostgreSQL hay `SEARCH`; có giới hạn số bước đệ quy qua cấu hình |
| **SQL Server** | CTE đệ quy với `WITH ... AS (...)` | Dùng cột cấp và khóa đường dẫn phù hợp, `ORDER BY` cuối | Không dùng `SEARCH` PostgreSQL; mặc định có giới hạn đệ quy 100, có `OPTION (MAXRECURSION n)` |
| **SQLite** | `WITH RECURSIVE` | Có thể ảnh hưởng thứ tự mở rộng qua `ORDER BY` trong recursive-select; vẫn cần xác định thứ tự đầu ra | Không có mảng kiểu PostgreSQL; dùng đường dẫn văn bản hoặc cấu trúc khác |
| **Oracle Database** | Cú pháp truy vấn phân cấp và recursive subquery factoring | Có cú pháp `SEARCH` trong ngữ cảnh được hỗ trợ; cũng có `CONNECT BY` truyền thống | Khác nhau về cách khai báo CTE, cơ chế cycle và cú pháp phân cấp |

Trong SQL Server, ví dụ giới hạn độ sâu kiểu:

~~~sql
-- Minh hoa T-SQL, gia dinh co bang dbo.units.
WITH unit_walk AS (
    SELECT node_id, parent_id, 0 AS depth
    FROM dbo.units
    WHERE node_id = 1

    UNION ALL

    SELECT child.node_id, child.parent_id, walk.depth + 1
    FROM dbo.units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
    WHERE walk.depth < 10
)
SELECT node_id, depth
FROM unit_walk
ORDER BY depth, node_id
OPTION (MAXRECURSION 100);
~~~

Đây là **cú pháp T-SQL minh họa**, không chạy trực tiếp trên PostgreSQL của bài học và không chứng minh nó đáp ứng mọi yêu cầu BFS/DFS theo thứ tự nhánh. Giới hạn độ sâu chỉ là một rào chắn bổ sung; nếu cây thật có nhiều hơn 10 cấp, điều kiện `walk.depth < 10` sẽ **cố tình bỏ các cấp sâu hơn**.

## 17. Các lỗi thường gặp khi sắp kết quả đệ quy

| Hiện tượng hoặc cách viết | Vì sao có vấn đề | Hướng xử lý |
| --- | --- | --- |
| CTE đệ quy không có `ORDER BY` nhưng mặc định kết quả là BFS | Thứ tự vật lý thực thi không phải cam kết đầu ra | Dùng `ORDER BY` cuối với khóa rõ nghĩa |
| `ORDER BY node_id` để hiển thị cây | ID không nhất thiết là thứ tự anh em; làm mất cấu trúc nhánh | Dùng `sibling_order` kết hợp đường dẫn |
| `ORDER BY depth` mà cho rằng thứ tự cùng cấp ổn định | Các hàng cùng depth hòa khóa | Bổ sung khóa phụ có thứ tự xác định |
| `ORDER BY depth, sibling_order` để giữ nhóm con theo cha | Những nút khác cha có cùng số thứ tự, bị xen kẽ | Dùng `ORDER BY depth, sort_path` |
| `ORDER BY sort_path` nhưng mong tất cả cấp 1 trước cấp 2 | `sort_path` cho DFS, nên một nhánh sâu có thể đứng trước nút cấp 1 khác | BFS dùng `ORDER BY depth, sort_path` |
| Có `SEARCH DEPTH FIRST` nhưng không `ORDER BY dfs_order` | `SEARCH` tạo khóa, chưa yêu cầu sắp đầu ra theo khóa đó | Thêm `ORDER BY dfs_order` |
| Coi `SEARCH BREADTH FIRST BY sibling_order` là nhóm con theo toàn bộ đường tổ tiên | BFS SEARCH theo khóa trong `BY` của nút/cấp, không tự mang mọi quy tắc nhánh | Dùng `depth, sort_path` nếu muốn giữ trật tự cha |
| Dùng mảng `sort_path` khi anh em trùng `sibling_order` | Đường dẫn có thể hòa, không xác định nhánh | Bảo đảm thứ tự duy nhất hoặc thêm khóa ổn định vào mỗi đoạn |
| Dữ liệu có chu trình nhưng chỉ dùng `UNION ALL` | Có thể sinh vô hạn các đường lặp | Dùng `CYCLE`/mảng visited/giới hạn phù hợp |
| Dùng `UNION` để chắc chắn chặn chu trình có cột `depth` | Mỗi lần lặp tạo hàng mới do độ sâu thay đổi | Kiểm soát nút đã đi qua, không chỉ loại hàng trùng |
| Dùng `LIMIT` thay kiểm tra chu trình | `ORDER BY` và các thao tác khác có thể vẫn cần xử lý tập lớn | Kiểm soát tính kết thúc trong recursive term |
| Thêm điều kiện lọc vào phần đệ quy mà không xét hậu duệ | Loại một nút có thể đồng thời chặn cả nhánh của nó | Phân biệt lọc **trong lúc mở rộng** và lọc **kết quả cuối** |
| Phân trang với `OFFSET` mà không có khóa thứ tự duy nhất | Các trang có thể lặp hoặc thiếu hàng | Thứ tự xác định, cân nhắc snapshot và thay đổi dữ liệu |
| Đưa `ORDER BY` cuối vào trong một hàm tổng hợp mà không viết ORDER BY của hàm | Thứ tự các phần tử được tổng hợp có thể không được bảo đảm | Dùng `STRING_AGG(x, ... ORDER BY ...)`/`ARRAY_AGG(x ORDER BY ...)` |

## 18. Bài tập thực hành có đáp án

Các bài tập dùng bảng `lab_rec230_units` gồm 13 nút của mục 2. Hãy tự dự đoán **thứ tự ID**, không chỉ số hàng, trước khi xem đáp án.

### Bài 1 — Tìm số nút ở mỗi cấp

**Yêu cầu:** duyệt từ gốc ID 1 và đếm số nút ở mỗi `depth`.

**Đáp án:**

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT node_id, parent_id, 0 AS depth
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT child.node_id, child.parent_id, walk.depth + 1
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT depth, COUNT(*) AS node_count
FROM unit_walk
GROUP BY depth
ORDER BY depth;
~~~

Kết quả: **cấp 0 có 1 nút, cấp 1 có 3 nút, cấp 2 có 5 nút, cấp 3 có 4 nút**. Tổng 13 nút.

### Bài 2 — BFS theo cấp rồi theo ID

**Yêu cầu:** xếp nút cấp nông trước, nếu cùng cấp thì ID nhỏ trước. Cách này có đúng thứ tự anh em Kinh doanh trước Kỹ thuật không?

**Đáp án:** dùng `ORDER BY depth, node_id` trên CTE đệ quy ở mục 3. Ở cấp 1, thứ tự là **10 (Kỹ thuật), 20 (Kinh doanh), 30 (Vận hành)**. Vì vậy **không** đúng thứ tự anh em theo `sibling_order` đã định nghĩa, dù vẫn là một thứ tự theo chiều rộng.

### Bài 3 — DFS theo thứ tự anh em

**Yêu cầu:** lấy toàn bộ cây theo thứ tự DFS kiểu cha trước con. Đảm bảo Kinh doanh đứng trước Kỹ thuật.

**Đáp án:**

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT
        node_id, parent_id, node_name,
        0 AS depth,
        ARRAY[sibling_order]::integer[] AS sort_path
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id, child.parent_id, child.node_name,
        walk.depth + 1,
        walk.sort_path || child.sibling_order
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SELECT node_id, node_name, depth
FROM unit_walk
ORDER BY sort_path;
~~~

Thứ tự ID: **1, 20, 60, 110, 90, 40, 10, 70, 120, 100, 50, 30, 80**.

### Bài 4 — BFS nhưng vẫn giữ nhóm con theo thứ tự cha

**Yêu cầu:** các cấp nông trước; trong cùng cấp, con thuộc nhánh Kinh doanh đứng trước con thuộc Kỹ thuật, rồi tới Vận hành.

**Đáp án:** dùng **cùng CTE có `depth` và `sort_path` của bài 3**, nhưng đổi mệnh đề cuối thành:

~~~sql
ORDER BY depth ASC, sort_path ASC;
~~~

Thứ tự ID: **1, 20, 10, 30, 60, 40, 70, 50, 80, 110, 90, 120, 100**. Khóa `depth` đặt trước bảo đảm chiều rộng; `sort_path` phân định thứ tự nhánh.

### Bài 5 — SEARCH DEPTH FIRST của PostgreSQL

**Yêu cầu:** dùng `SEARCH` thay vì tự xây mảng `sort_path` để trả thứ tự DFS theo thứ tự anh em.

**Đáp án:**

~~~sql
WITH RECURSIVE unit_walk (
    node_id, parent_id, node_name, sibling_order
) AS (
    SELECT node_id, parent_id, node_name, sibling_order
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT
        child.node_id, child.parent_id,
        child.node_name, child.sibling_order
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
)
SEARCH DEPTH FIRST BY sibling_order, node_id SET dfs_order
SELECT node_id, node_name
FROM unit_walk
ORDER BY dfs_order;
~~~

Thứ tự ID trùng bài 3. `SEARCH` tạo `dfs_order` và ta **sắp theo cột đó** ở truy vấn ngoài. Cú pháp này cần PostgreSQL 14 trở lên.

### Bài 6 — Vì sao BFS với SEARCH có thể xen kẽ nhánh?

**Câu hỏi:** với `SEARCH BREADTH FIRST BY sibling_order, node_id SET bfs_order`, ở cấp 2 thì Nội địa, Quốc tế có nhất thiết đứng liền nhau không?

**Đáp án:** **không**. Ở cùng cấp 2, khóa BFS ưu tiên `sibling_order` của từng nút: Nội địa (1), Backend (1), Hỗ trợ (1), rồi Quốc tế (2), Frontend (2) theo ID phân định trong mỗi nhóm cùng thứ tự. Vì vậy các con của Kinh doanh có thể bị xen với con của các cha khác. Khi cần giữ nhóm cha, dùng `ORDER BY depth, sort_path`.

### Bài 7 — Giới hạn cây ở cấp 2

**Yêu cầu:** chỉ tạo các nút có `depth <= 2`, không mở rộng tới cấp 3.

**Đáp án:**

~~~sql
WITH RECURSIVE unit_walk AS (
    SELECT node_id, parent_id, 0 AS depth
    FROM lab_rec230_units
    WHERE node_id = 1

    UNION ALL

    SELECT child.node_id, child.parent_id, walk.depth + 1
    FROM lab_rec230_units AS child
    JOIN unit_walk AS walk
        ON child.parent_id = walk.node_id
    WHERE walk.depth < 2
)
SELECT node_id, depth
FROM unit_walk
ORDER BY depth, node_id;
~~~

Có **9 nút**: 1 gốc + 3 nút cấp 1 + 5 nút cấp 2. Điều kiện `walk.depth < 2` được đánh giá khi xét có mở rộng con từ nút hiện tại hay không.

### Bài 8 — Đánh số thứ tự trong kết quả DFS

**Yêu cầu:** thêm cột `position` bắt đầu từ 1 theo thứ tự DFS cho các nút của cây.

**Đáp án:** dùng CTE `unit_walk` có `sort_path` như bài 3 và:

~~~sql
SELECT
    ROW_NUMBER() OVER (ORDER BY sort_path) AS position,
    node_id,
    node_name
FROM unit_walk
ORDER BY position;
~~~

Kết quả đầu: vị trí 1 là Công ty, vị trí 2 Kinh doanh, vị trí 3 Nội địa, vị trí 4 HCM. `position` là **thứ tự trình bày**, không nên dùng thay khóa `node_id`.

### Bài 9 — Lấy trang thứ hai của danh sách DFS

**Yêu cầu:** mỗi trang 5 nút, lấy trang 2 theo DFS của dữ liệu cố định.

**Đáp án:** dùng CTE `unit_walk` có `sort_path` như bài 3, với:

~~~sql
SELECT node_id, node_name
FROM unit_walk
ORDER BY sort_path
LIMIT 5 OFFSET 5;
~~~

Kết quả các ID **40, 10, 70, 120, 100** (Quốc tế, Kỹ thuật, Backend, API, Dữ liệu). Không được bỏ `ORDER BY sort_path` nếu muốn các trang có ý nghĩa “tiếp theo theo DFS”.

### Bài 10 — Tìm và ngăn vòng lặp trong đồ thị

**Yêu cầu:** đồ thị có các cạnh `1→2`, `2→3`, `3→1` và `2→4`. Vì sao `UNION ALL` đơn thuần có thể không dừng? Viết cách tránh thăm lại nút trên cùng đường.

**Đáp án:** nếu không ghi nhớ đường đã đi qua, chuỗi `1 → 2 → 3 → 1 → 2 → ...` tiếp tục sinh hàng. Có thể sử dụng `CYCLE node_id SET is_cycle USING cycle_path` của PostgreSQL 14+ như mục 11, hoặc mảng `visited_ids` và điều kiện:

~~~sql
WHERE NOT (e.to_id = ANY(w.visited_ids))
~~~

trong recursive term. `ORDER BY` không ngăn vòng lặp vì nó không thay đổi quy tắc mở rộng cạnh.

### Bài 11 — Đổi thứ tự anh em nhưng giữ nguyên ID

**Yêu cầu:** nếu nghiệp vụ đổi Kỹ thuật thành vị trí số 1 và Kinh doanh thành vị trí số 2, thứ tự nào sẽ thay đổi? Có cần đổi `node_id` không?

**Đáp án:** thứ tự DFS và BFS dựa trên `sort_path` phải **đổi theo vị trí anh em mới**; Kỹ thuật và toàn bộ nhánh của nó sẽ đứng trước Kinh doanh trong DFS. Với BFS, cả hai vẫn thuộc cấp 1 nhưng thứ tự giữa hai nhánh sẽ đảo. **Không cần và không nên đổi `node_id` chỉ để sắp xếp.** Cần cập nhật giá trị `sibling_order` đúng cách và tôn trọng ràng buộc duy nhất, chẳng hạn thao tác trong giao dịch với chiến lược tránh va chạm giá trị trung gian nếu thực sự cập nhật dữ liệu.

## 19. Ghi nhớ

| Mục tiêu | Cách tiếp cận trong PostgreSQL |
| --- | --- |
| Lấy các nút thuộc cây | `WITH RECURSIVE` với phần neo và phần đệ quy |
| Biết nút ở cấp nào | Tạo `depth`, gốc bằng 0, con bằng `depth + 1` |
| BFS theo cấp, chưa yêu cầu nhóm theo cha | `ORDER BY depth, ...` với khóa phân định phù hợp |
| BFS theo cấp **và** giữ thứ tự nhánh cha | Tạo `sort_path` rồi `ORDER BY depth, sort_path` |
| DFS kiểu cha trước con theo thứ tự anh em | Tạo `sort_path` rồi `ORDER BY sort_path` |
| DFS bằng cú pháp hỗ trợ sẵn | `SEARCH DEPTH FIRST BY ... SET dfs_order`, sau đó `ORDER BY dfs_order` |
| BFS bằng cú pháp hỗ trợ sẵn | `SEARCH BREADTH FIRST BY ... SET bfs_order`, sau đó `ORDER BY bfs_order` |
| Hiển thị cây thụt cấp | `REPEAT('  ', depth) || node_name` kết hợp thứ tự DFS |
| Ngăn mở rộng quá sâu | Điều kiện giới hạn `depth` trong **recursive term** |
| Phát hiện/chặn chu trình | `CYCLE` hoặc theo dõi các nút đã gặp trên từng đường |
| Phân trang có thứ tự | `ORDER BY` xác định trước `LIMIT/OFFSET`, chú ý thay đổi dữ liệu |

Điểm quan trọng nhất là tách hai khái niệm: **truy vấn đệ quy xác định những nút nào được tìm thấy**, còn **khóa sắp xếp xác định chúng xuất hiện theo thứ tự nào**. Muốn BFS, ưu tiên `depth`; muốn DFS, ưu tiên **đường dẫn từ gốc**. Nếu yêu cầu còn bao gồm thứ tự anh em hoặc thứ tự các nhánh cha, hãy đưa quy tắc đó vào chính đường dẫn hoặc cột `SEARCH` phù hợp. Nhờ vậy bạn có thể tạo kết quả phân cấp rõ ràng, lặp lại được trên một trạng thái dữ liệu cố định và không phụ thuộc vào thứ tự ngẫu nhiên của quá trình thực thi SQL.
