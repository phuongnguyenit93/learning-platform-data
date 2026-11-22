# Mô hình đường dẫn vật chất hóa, tập lồng nhau và bảng bao đóng

Trong một hệ thống phân loại sản phẩm, cơ cấu phòng ban, diễn đàn hoặc cây thư mục, một bản ghi thường có **cha**, **con**, **tổ tiên** và **hậu duệ**. Những quan hệ đó hình thành **cây phân cấp (hierarchy)**. Thiết kế dữ liệu cần trả lời cả hai câu hỏi: *làm sao biểu diễn đúng cây?* và *làm sao truy vấn, cập nhật cây hiệu quả?*

Bài này so sánh ba kỹ thuật lưu quan hệ tổ tiên–hậu duệ trong cơ sở dữ liệu quan hệ:

- **Đường dẫn vật chất hóa (materialized path):** lưu một đường dẫn từ gốc đến từng nút.
- **Tập lồng nhau (nested sets):** đánh số biên trái và phải cho mỗi nút để biểu diễn khoảng bao chứa.
- **Bảng bao đóng (closure table):** lưu từng cặp tổ tiên–hậu duệ cùng khoảng cách.

Ba cách đều nhằm làm rõ các truy vấn phân cấp, nhưng khác đáng kể ở chi phí lưu trữ, thêm nút, di chuyển nhánh, truy vấn đường lên và kiểm soát tính nhất quán. Đây là nội dung của chương **Kế thừa và phân cấp** trong module **DATABASE_DATA_MODELING**: chuyển yêu cầu nghiệp vụ thành cấu trúc dữ liệu, khóa, ràng buộc và chỉ mục phù hợp, có thể kiểm chứng và tiến hóa.

> **Phạm vi:** Những kỹ thuật dưới đây chủ yếu xét **cây** hoặc **rừng cây** (mỗi nút có nhiều nhất một cha). Chúng không đồng nghĩa với kế thừa kiểu thực thể IS-A. Một Product có thể là DigitalProduct theo quan hệ IS-A, còn một Category có Category cha là quan hệ phân cấp các **bản ghi cùng loại**. Nếu một nút có thể có nhiều cha, dữ liệu là **đồ thị có hướng**, thường là DAG, và phải xem xét lại các giả định về đường đi, độ sâu và tổ tiên.

## 1. Bài toán mẫu và các truy vấn thường gặp

Giả sử danh mục sản phẩm có cấu trúc:

~~~text
1  Sản phẩm
├── 2  Điện tử
│   ├── 4  Điện thoại
│   │   └── 6  Android
│   └── 5  Laptop
└── 3  Thời trang
~~~

Trong ví dụ này:

- **Cha trực tiếp** của Điện thoại là Điện tử.
- **Tổ tiên** của Android là Điện thoại, Điện tử và Sản phẩm.
- **Hậu duệ** của Điện tử là Điện thoại, Laptop và Android.
- **Cây con** của Điện tử gồm chính Điện tử và tất cả hậu duệ.
- **Độ sâu** của nút được tính từ gốc: Sản phẩm ở độ sâu 0, Android ở độ sâu 3.

Các tình huống nghiệp vụ quan trọng là: hiển thị toàn bộ cây con; dựng breadcrumb từ gốc tới nút; lấy con trực tiếp; đếm số nút trong nhánh; chuyển một danh mục sang cha mới; chặn chu trình; xóa hoặc lưu trữ cả nhánh; tìm các nút cùng một cây.

Một thiết kế tốt cần làm rõ:

1. **Bội số:** mỗi nút có đúng một cha, không có cha nếu là gốc, hay được phép nhiều cha?
2. **Cách quản lý gốc:** có một gốc chung hay nhiều cây trong cùng hệ thống?
3. **Thao tác nổi trội:** đọc cây con nhiều hơn di chuyển nút, hay chỉnh sửa cấu trúc liên tục?
4. **Giới hạn:** cây có bao nhiêu nút, sâu bao nhiêu tầng và có bao nhiêu người cập nhật đồng thời?
5. **Ngữ nghĩa xóa:** xóa nhánh, đưa các con lên cấp trên, chặn xóa hay đánh dấu ngừng sử dụng?
6. **Phạm vi phân tách:** cây thuộc tổ chức, tenant hoặc phiên bản danh mục nào?

### Mốc đối chiếu: danh sách kề (adjacency list)

Phương án nền tảng lưu **khóa cha** trên từng hàng. Nó tối giản dữ liệu trùng lặp, đồng thời là một nguồn sự thật phù hợp để duy trì thêm cấu trúc đã vật chất hóa.

~~~sql
-- PostgreSQL
CREATE TABLE categories (
    category_id BIGINT PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_id   BIGINT REFERENCES categories(category_id),
    CHECK (parent_id IS NULL OR parent_id <> category_id)
);

INSERT INTO categories (category_id, name, parent_id) VALUES
    (1, 'Sản phẩm', NULL),
    (2, 'Điện tử', 1),
    (3, 'Thời trang', 1),
    (4, 'Điện thoại', 2),
    (5, 'Laptop', 2),
    (6, 'Android', 4);
~~~

Các khóa ngoại bảo đảm cha tồn tại; **CHECK** chỉ ngăn tự làm cha trực tiếp, chưa ngăn chu trình dài hơn như A → B → C → A. Muốn ngăn chu trình phải kiểm tra cả chuỗi tổ tiên hoặc cưỡng chế bằng quy trình ghi.

Truy vấn hậu duệ bằng CTE đệ quy:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT category_id, name, parent_id, 0 AS relative_depth
    FROM categories
    WHERE category_id = 2

    UNION ALL

    SELECT child.category_id, child.name, child.parent_id,
           subtree.relative_depth + 1
    FROM categories AS child
    JOIN subtree ON child.parent_id = subtree.category_id
)
SELECT category_id, name, relative_depth
FROM subtree
ORDER BY relative_depth, category_id;
~~~

Kết quả gồm Điện tử (0), Điện thoại và Laptop (1), Android (2). **Danh sách kề** khá thuận tiện để thêm, sửa cha trực tiếp, nhưng việc lấy toàn bộ nhánh cần đệ quy. Ba mô hình dưới đây chủ động lưu thêm thông tin để tăng hiệu quả cho từng kiểu truy vấn.

## 2. Đường dẫn vật chất hóa (materialized path)

### 2.1. Cách lưu trữ

Mỗi nút lưu **toàn bộ chuỗi định danh từ gốc đến chính nó**, ví dụ:

| category_id | name | parent_id | path |
| ---: | --- | ---: | --- |
| 1 | Sản phẩm | NULL | /1/ |
| 2 | Điện tử | 1 | /1/2/ |
| 3 | Thời trang | 1 | /1/3/ |
| 4 | Điện thoại | 2 | /1/2/4/ |
| 5 | Laptop | 2 | /1/2/5/ |
| 6 | Android | 4 | /1/2/4/6/ |

Quy ước có dấu **/** ở đầu và cuối từng đường dẫn giúp nhận diện ranh giới ID: tìm tiền tố **/1/2/** sẽ không nhầm với **/1/20/**. Đường dẫn chứa định danh ổn định thay vì tên hiển thị để đổi tên danh mục không phải viết lại toàn nhánh.

Ví dụ lược đồ riêng cho kỹ thuật này:

~~~sql
CREATE TABLE path_categories (
    category_id BIGINT PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_id   BIGINT REFERENCES path_categories(category_id),
    path        TEXT NOT NULL UNIQUE,
    CONSTRAINT path_has_delimiters CHECK (
        left(path, 1) = '/' AND right(path, 1) = '/'
    ),
    CHECK (parent_id IS NULL OR parent_id <> category_id)
);

INSERT INTO path_categories
    (category_id, name, parent_id, path)
VALUES
    (1, 'Sản phẩm', NULL, '/1/'),
    (2, 'Điện tử', 1, '/1/2/'),
    (3, 'Thời trang', 1, '/1/3/'),
    (4, 'Điện thoại', 2, '/1/2/4/'),
    (5, 'Laptop', 2, '/1/2/5/'),
    (6, 'Android', 4, '/1/2/4/6/');
~~~

Đây là lược đồ **minh họa**. Điều kiện dấu phân cách, UNIQUE và FK **chưa kiểm chứng** path thực sự bằng đường dẫn của parent_id nối category_id, không ngăn đường dẫn giả hoặc chu trình. Trong hệ thống thật phải bảo đảm bất biến đó bằng logic ghi có giao dịch, trigger thích hợp hoặc cách biểu diễn hạn chế hơn.

### 2.2. Truy vấn với tiền tố

Toàn bộ cây con của Điện tử, **bao gồm nút Điện tử**:

~~~sql
SELECT category_id, name, path
FROM path_categories
WHERE path LIKE '/1/2/%'
ORDER BY path;
~~~

Tiền tố đã chứa dấu phân cách nên nút ID 20 dưới gốc không bị khớp sai. Nếu cần tìm hậu duệ mà **loại nút gốc của cây con**, bổ sung **category_id <> 2**.

Tìm breadcrumb tới Android, gồm cả Android:

~~~sql
SELECT ancestor.category_id, ancestor.name
FROM path_categories AS ancestor
JOIN path_categories AS target
  ON target.category_id = 6
WHERE target.path LIKE ancestor.path || '%'
ORDER BY length(ancestor.path), ancestor.category_id;
~~~

Giả định các thành phần path chỉ gồm ID số và dấu phân cách, nên không chứa ký tự đại diện **%** hoặc **_** của LIKE. Nếu đường dẫn chứa nhãn tùy ý, phải mã hóa hoặc escape ký tự đặc biệt. Truy vấn breadcrumb kiểu so tiền tố giữa hai hàng có thể không sử dụng chỉ mục hiệu quả như truy vấn tiền tố hằng.

Truy vấn con **trực tiếp** vẫn dễ nhất bằng **parent_id = 2**. Không cần dùng LIKE nếu chỉ muốn một tầng.

### 2.3. Thêm nút và chuyển nhánh

Thêm Tablet làm con Điện tử: đọc path của cha, nối ID mới theo quy ước, thêm cả parent_id và path **trong cùng giao dịch**. Trường hợp đơn giản:

~~~sql
INSERT INTO path_categories (category_id, name, parent_id, path)
SELECT 7, 'Tablet', p.category_id,
       p.path || '7/'
FROM path_categories AS p
WHERE p.category_id = 2;
~~~

Trước khi thêm cần chắc ID mới chưa tồn tại và có cơ chế ngăn thao tác chuyển nhánh đồng thời làm đường dẫn cha thay đổi. Trong hệ thống thực tế, thao tác di chuyển thường cần khóa hoặc tuần tự hóa ở phạm vi cây.

**Chuyển cả nhánh Điện thoại từ Điện tử sang Thời trang** nghĩa là đổi tiền tố:

~~~text
Trước:
  /1/2/4/        Điện thoại
  /1/2/4/6/      Android

Sau:
  /1/3/4/        Điện thoại
  /1/3/4/6/      Android
~~~

Một minh họa cập nhật, **chỉ đúng khi tiền tố cũ/mới đã được xác nhận**, đích không nằm trong nhánh nguồn và giao dịch có cơ chế khóa phù hợp:

~~~sql
BEGIN;

UPDATE path_categories
SET path = '/1/3/4/' ||
           substr(path, length('/1/2/4/') + 1),
    parent_id = CASE WHEN category_id = 4 THEN 3 ELSE parent_id END
WHERE path LIKE '/1/2/4/%';

COMMIT;
~~~

Câu lệnh cập nhật **mọi nút trong cây con**; chỉ nút gốc của nhánh được đổi parent_id, còn parent_id của Android vẫn là 4. Không thể chỉ đổi đường dẫn ở nút Điện thoại vì hậu duệ sẽ giữ dữ liệu sai. Khi chuyển nhánh lớn, chi phí ghi và số hàng bị khóa tăng theo **kích thước cây con**.

### 2.4. Chỉ mục và kiểu đường dẫn chuyên dụng

Với PostgreSQL, chỉ mục B-tree theo tiền tố có thể dùng kiểu toán tử:

~~~sql
CREATE INDEX idx_path_categories_prefix
ON path_categories (path text_pattern_ops);

CREATE INDEX idx_path_categories_parent
ON path_categories (parent_id);
~~~

Chỉ mục **text_pattern_ops** hữu ích cho LIKE tiền tố cố định dưới nhiều cấu hình collation; hệ quản trị vẫn tự quyết định dùng index hay quét bảng theo thống kê, tỷ lệ hàng khớp và hình dạng truy vấn.

Nếu có thể dùng extension **ltree** của PostgreSQL, có thể lưu đường dẫn dưới dạng nhãn **n1.n2.n4**, dùng toán tử **<@** (đường dẫn bên trái là hậu duệ hoặc chính nó của đường dẫn bên phải) và chỉ mục GiST để truy vấn phân cấp. Cần kiểm tra hỗ trợ extension, quy ước nhãn và kế hoạch index trước khi chọn.

**Phù hợp khi:** cây không thay đổi thường xuyên, đọc cây con/breadcrumb nhiều, muốn lược đồ dễ hiểu và chấp nhận cập nhật toàn nhánh lúc chuyển vị trí.

## 3. Tập lồng nhau (nested sets)

### 3.1. Ý tưởng đánh số khoảng

Mô hình **nested sets** duyệt cây theo chiều sâu rồi gán mỗi nút hai số: **lft** (biên trái), **rgt** (biên phải). Khoảng của nút cha **chứa hoàn toàn** khoảng của mọi hậu duệ.

Một cách đánh số cho cây mẫu:

~~~text
Sản phẩm       [1,12]
├── Điện tử    [2, 9]
│   ├── Điện thoại [3,6]
│   │   └── Android [4,5]
│   └── Laptop     [7,8]
└── Thời trang     [10,11]
~~~

| category_id | name | lft | rgt |
| ---: | --- | ---: | ---: |
| 1 | Sản phẩm | 1 | 12 |
| 2 | Điện tử | 2 | 9 |
| 4 | Điện thoại | 3 | 6 |
| 6 | Android | 4 | 5 |
| 5 | Laptop | 7 | 8 |
| 3 | Thời trang | 10 | 11 |

Các quan hệ quan trọng:

- Nút **A** là tổ tiên của **B** nếu **A.lft < B.lft** và **A.rgt > B.rgt**.
- **Lá** có **rgt = lft + 1**, trong quy ước duyệt liên tiếp ở đây.
- **Số nút trong cây con** gồm chính nút đó là **(rgt − lft + 1) / 2**, nếu dùng đánh số liên tục, mỗi nút đúng một cặp biên.
- Các khoảng của hai nhánh khác nhau phải **rời nhau**, còn khoảng cha/con phải **bao chứa hoàn toàn**; không được chồng lấn một phần.

Trong nested sets chuẩn, các giá trị biên là **tọa độ cấu trúc**, không phải ID của thực thể. Thêm hoặc chuyển một nút có thể làm nhiều giá trị biên thay đổi.

### 3.2. Lược đồ và truy vấn

~~~sql
CREATE TABLE nested_categories (
    category_id BIGINT PRIMARY KEY,
    name        TEXT NOT NULL,
    lft         INTEGER NOT NULL UNIQUE,
    rgt         INTEGER NOT NULL UNIQUE,
    CHECK (lft > 0),
    CHECK (lft < rgt)
);

INSERT INTO nested_categories (category_id, name, lft, rgt) VALUES
    (1, 'Sản phẩm', 1, 12),
    (2, 'Điện tử', 2, 9),
    (4, 'Điện thoại', 3, 6),
    (6, 'Android', 4, 5),
    (5, 'Laptop', 7, 8),
    (3, 'Thời trang', 10, 11);
~~~

Lấy toàn bộ cây con của Điện tử, gồm chính nó:

~~~sql
SELECT child.category_id, child.name, child.lft, child.rgt
FROM nested_categories AS parent
JOIN nested_categories AS child
  ON child.lft >= parent.lft AND child.rgt <= parent.rgt
WHERE parent.category_id = 2
ORDER BY child.lft;
~~~

Lấy các tổ tiên của Android, gồm chính Android:

~~~sql
SELECT ancestor.category_id, ancestor.name
FROM nested_categories AS target
JOIN nested_categories AS ancestor
  ON ancestor.lft <= target.lft AND ancestor.rgt >= target.rgt
WHERE target.category_id = 6
ORDER BY ancestor.lft;
~~~

Đếm nút trong nhánh:

~~~sql
SELECT category_id, name,
       (rgt - lft + 1) / 2 AS subtree_node_count
FROM nested_categories
WHERE category_id = 2;
-- Kết quả trong ví dụ: 4 nút (Điện tử, Điện thoại, Android, Laptop).
~~~

Các phép so sánh khoảng làm truy vấn tổ tiên và hậu duệ không cần duyệt đệ quy. Tuy nhiên, nested sets **không tự lưu cha trực tiếp**. Nếu thao tác hiển thị con một cấp diễn ra thường xuyên, cân nhắc lưu thêm parent_id và đảm bảo nó đồng bộ với khoảng, hoặc dùng truy vấn suy ra cha gần nhất từ các khoảng bao chứa.

### 3.3. Vì sao chỉnh sửa cây tốn kém?

Khi thêm nút vào giữa thứ tự duyệt, cần **mở khoảng trống cho hai biên mới**, thường là dịch những giá trị lft/rgt ở phía sau vị trí chèn. Khi xóa hoặc chuyển cả nhánh, phải **đóng khoảng cũ**, **mở khoảng mới** và tính lại biên của các nút liên quan.

Ngay cả khi chỉ thêm một nút lá, có thể phải cập nhật **nhiều hàng không nằm trong nhánh lá**. Chuyển một cây con lớn có thể gây nhiều thao tác ghi và xung đột khóa, đặc biệt nếu hệ thống có nhiều người sửa danh mục đồng thời.

**Không nên** thử chuyển nhánh bằng cách chỉ thay lft/rgt của nút gốc. Điều đó sẽ phá vỡ quy tắc bao chứa hậu duệ.

Các ràng buộc **CHECK(lft < rgt)** và **UNIQUE** trong DDL trên chỉ bắt lỗi cục bộ và biên trùng. Chúng **không tự đảm bảo** các khoảng hợp thành một cây nested sets hợp lệ: vẫn có thể tồn tại hai khoảng giao nhau một phần hoặc số biên bị hổng. Cần cơ chế ghi tập trung, kiểm tra toàn cây và giao dịch có kiểm soát cạnh tranh.

### 3.4. Chỉ mục

~~~sql
CREATE INDEX idx_nested_categories_lft
ON nested_categories (lft);

CREATE INDEX idx_nested_categories_rgt
ON nested_categories (rgt);
~~~

Các cột lft/rgt đã có UNIQUE ở ví dụ, vì vậy PostgreSQL **đã tạo chỉ mục duy nhất** trên từng cột; hai CREATE INDEX trên là **thừa** nếu giữ nguyên DDL. Đoạn trên chỉ nhằm minh họa hai hướng truy vấn khoảng trong trường hợp chọn một sơ đồ khác chưa có chỉ mục. Khi thiết kế thật, **không tạo trùng chỉ mục**; kiểm tra bộ chỉ mục hiện có và EXPLAIN của truy vấn mục tiêu.

Nếu có nhiều cây độc lập, thường cần thêm **tree_id** và quản lý biên trong phạm vi từng cây; các truy vấn phải lọc đúng tree_id. Không thể so sánh lft/rgt của hai cây như thể chúng cùng nằm trong một thứ tự đánh số nếu mô hình không quy định như vậy.

**Phù hợp khi:** cây tương đối tĩnh, lượng đọc lớn, thường lấy trọn cây con, cần tính số nút/duyệt theo thứ tự và có thể chấp nhận chi phí cập nhật nhiều hàng.

## 4. Bảng bao đóng (closure table)

### 4.1. Lưu từng cặp tổ tiên–hậu duệ

**Closure table** lưu tất cả cặp **(ancestor_id, descendant_id)** tồn tại trong cây, cùng **depth** là số cạnh từ tổ tiên đến hậu duệ. Quy ước phổ biến bao gồm **cặp tự thân** có depth = 0.

Với cây mẫu, một số hàng bao đóng là:

| ancestor_id | descendant_id | depth | Ý nghĩa |
| ---: | ---: | ---: | --- |
| 1 | 1 | 0 | Sản phẩm là chính nó |
| 1 | 2 | 1 | Sản phẩm là cha Điện tử |
| 1 | 4 | 2 | Sản phẩm cách Điện thoại hai cạnh |
| 1 | 6 | 3 | Sản phẩm cách Android ba cạnh |
| 2 | 4 | 1 | Điện tử là cha Điện thoại |
| 2 | 6 | 2 | Điện tử là ông/bà của Android |
| 4 | 6 | 1 | Điện thoại là cha Android |
| 6 | 6 | 0 | Android là chính nó |

Trong cây mẫu có 6 nút và **15 hàng closure** khi lưu cả tự thân. Số hàng tăng theo tổng số tổ tiên của mọi nút cộng số nút, nên cây **dạng dây dài** có thể cần O(N²) hàng, còn cây cân bằng thường nhỏ hơn đáng kể, xấp xỉ O(N log N).

### 4.2. Lược đồ: danh sách kề làm nguồn cùng closure làm chỉ mục tổ tiên

~~~sql
CREATE TABLE hier_nodes (
    node_id   BIGINT PRIMARY KEY,
    name      TEXT NOT NULL,
    parent_id BIGINT REFERENCES hier_nodes(node_id),
    CHECK (parent_id IS NULL OR parent_id <> node_id)
);

CREATE TABLE hier_closure (
    ancestor_id   BIGINT NOT NULL REFERENCES hier_nodes(node_id) ON DELETE CASCADE,
    descendant_id BIGINT NOT NULL REFERENCES hier_nodes(node_id) ON DELETE CASCADE,
    depth         INTEGER NOT NULL CHECK (depth >= 0),
    PRIMARY KEY (ancestor_id, descendant_id),
    CONSTRAINT valid_closure_depth CHECK (
        (ancestor_id = descendant_id AND depth = 0)
        OR
        (ancestor_id <> descendant_id AND depth > 0)
    )
);

INSERT INTO hier_nodes (node_id, name, parent_id) VALUES
    (1, 'Sản phẩm', NULL),
    (2, 'Điện tử', 1),
    (3, 'Thời trang', 1),
    (4, 'Điện thoại', 2),
    (5, 'Laptop', 2),
    (6, 'Android', 4);
~~~

Ví dụ xây dựng bảng closure ban đầu từ parent_id bằng CTE đệ quy:

~~~sql
WITH RECURSIVE paths AS (
    SELECT node_id AS ancestor_id,
           node_id AS descendant_id,
           0 AS depth
    FROM hier_nodes

    UNION ALL

    SELECT p.ancestor_id, child.node_id, p.depth + 1
    FROM paths AS p
    JOIN hier_nodes AS child
      ON child.parent_id = p.descendant_id
)
INSERT INTO hier_closure (ancestor_id, descendant_id, depth)
SELECT ancestor_id, descendant_id, depth
FROM paths;
~~~

CTE này giả định dữ liệu đầu vào **đã là cây hợp lệ, không chu trình** và bảng closure ban đầu trống. Nếu chạy lại mà chưa xử lý dữ liệu cũ sẽ vi phạm PRIMARY KEY. Nếu parent_id chứa chu trình, quá trình đệ quy có thể không kết thúc; trước khi dựng lại closure phải có bước phát hiện chu trình và cách xử lý dữ liệu lỗi.

Một số hệ thống không lưu parent_id để giảm trùng lặp: quan hệ **cha trực tiếp** được xác định bằng các hàng closure có depth = 1. Tuy nhiên, giữ parent_id làm dữ liệu chuẩn và closure như cấu trúc dẫn xuất thường giúp thao tác chỉnh sửa dễ hiểu hơn, với điều kiện luôn cập nhật nhất quán.

### 4.3. Truy vấn hậu duệ, tổ tiên, con trực tiếp

Cây con của Điện tử, gồm nút Điện tử:

~~~sql
SELECT d.node_id, d.name, c.depth AS relative_depth
FROM hier_closure AS c
JOIN hier_nodes AS d ON d.node_id = c.descendant_id
WHERE c.ancestor_id = 2
ORDER BY c.depth, d.node_id;
~~~

Các tổ tiên của Android, từ gốc tới chính Android:

~~~sql
SELECT a.node_id, a.name, c.depth AS distance_to_android
FROM hier_closure AS c
JOIN hier_nodes AS a ON a.node_id = c.ancestor_id
WHERE c.descendant_id = 6
ORDER BY c.depth DESC;
~~~

Con trực tiếp của Điện tử:

~~~sql
SELECT n.node_id, n.name
FROM hier_closure AS c
JOIN hier_nodes AS n ON n.node_id = c.descendant_id
WHERE c.ancestor_id = 2
  AND c.depth = 1
ORDER BY n.node_id;
~~~

Đếm số hậu duệ **không gồm nút gốc**:

~~~sql
SELECT COUNT(*) AS descendant_count
FROM hier_closure
WHERE ancestor_id = 2 AND depth > 0;
-- Kết quả: 3.
~~~

### 4.4. Thêm nút mới

Giả sử thêm Tablet ID 7 dưới Điện tử ID 2. Khi closure hiện có đầy đủ, ta thêm hàng tự thân và toàn bộ quan hệ từ các tổ tiên của 2 tới nút 7:

~~~sql
BEGIN;

INSERT INTO hier_nodes (node_id, name, parent_id)
VALUES (7, 'Tablet', 2);

INSERT INTO hier_closure (ancestor_id, descendant_id, depth)
SELECT ancestor_id, 7, depth + 1
FROM hier_closure
WHERE descendant_id = 2

UNION ALL

SELECT 7, 7, 0;

COMMIT;
~~~

Vì các tổ tiên của 2 gồm Sản phẩm (depth 1) và chính Điện tử (depth 0), closure mới có cặp (1,7,2), (2,7,1), (7,7,0). Thao tác cần giao dịch, cùng cơ chế đồng bộ khi có giao dịch khác đang di chuyển nhánh.

Nếu thêm nút gốc mới, chỉ cần thêm bản ghi nút có parent_id NULL và cặp closure tự thân depth 0. Nếu ứng dụng có nhiều tenant/cây, mọi phép thêm và tìm tổ tiên phải giới hạn trong đúng miền.

### 4.5. Chuyển một cây con bằng công thức

Giả sử chuyển toàn bộ cây con gốc tại nút **X** sang làm con của nút **P**. Với closure, không chỉ thay hàng liên quan X: phải thay tất cả quan hệ **từ tổ tiên bên ngoài nhánh đến mọi nút trong nhánh**.

Thuật toán khái niệm trong **một giao dịch**:

1. Kiểm tra X tồn tại, P tồn tại, **P không nằm trong cây con của X**, và thao tác hợp lệ trong phạm vi tenant/cây. Nếu P nằm dưới X, việc gắn X vào P sẽ tạo chu trình.
2. Xác định **D**, tập các hậu duệ của X, **bao gồm X**; giữ nguyên mọi quan hệ tổ tiên–hậu duệ **nội bộ D**.
3. Xóa các hàng closure mà **descendant thuộc D** và **ancestor là tổ tiên cũ của X nhưng nằm ngoài D**.
4. Với **mỗi tổ tiên A của P (kể cả P)** và **mỗi D trong cây con của X**, thêm cặp A → D có độ sâu: **depth(A, P) + 1 + depth(X, D)**.
5. Cập nhật **parent_id của X thành P**; kiểm tra bất biến và commit khi toàn bộ thay đổi thành công.

Chi phí tạo các cặp mới vào khoảng **số tổ tiên mới × số nút trong nhánh di chuyển**. Tính nhất quán đồng thời không được bảo đảm chỉ nhờ trình tự các câu SQL; cần khóa các phần có liên quan hoặc chính sách giao dịch đủ mạnh. Đừng trộn đọc dữ liệu closure trước/sau khi chỉnh sửa khi có giao dịch chuyển nhánh khác diễn ra đồng thời.

**Khóa ngoại, CHECK và PRIMARY KEY không tự đảm bảo bảng closure chứa đủ mọi cặp tổ tiên–hậu duệ, có đúng depth hoặc không có chu trình.** Hệ thống cần kiểm soát cơ chế duy trì và có truy vấn đối chiếu định kỳ với nguồn parent_id.

### 4.6. Chỉ mục

Khóa chính **(ancestor_id, descendant_id)** phục vụ truy vấn cây con theo ancestor_id. Để truy vấn tổ tiên của một nút, cần cân nhắc chỉ mục đảo:

~~~sql
CREATE INDEX idx_hier_closure_by_descendant
ON hier_closure (descendant_id, depth, ancestor_id);

CREATE INDEX idx_hier_closure_by_ancestor_depth
ON hier_closure (ancestor_id, depth, descendant_id);

CREATE INDEX idx_hier_nodes_parent
ON hier_nodes (parent_id);
~~~

Chỉ mục thứ hai tăng tốc lọc **depth = 1** cho con trực tiếp, nhưng cũng tăng chi phí ghi vì closure có thể có rất nhiều hàng. Chọn chỉ mục bằng thống kê truy vấn và EXPLAIN, đặc biệt với cây lớn.

**Phù hợp khi:** cần truy vấn tổ tiên, hậu duệ và khoảng cách linh hoạt; có thể giữ thêm bảng quan hệ tổ tiên; số lần thay đổi cấu trúc không quá dày đặc so với lưu lượng đọc.

## 5. So sánh thiết kế và chi phí

| Tiêu chí | Materialized path | Nested sets | Closure table |
| --- | --- | --- | --- |
| Dữ liệu bổ sung | Một chuỗi path trên mỗi nút | Hai biên lft/rgt trên mỗi nút | Một hàng cho mỗi cặp tổ tiên–hậu duệ |
| Lấy toàn bộ cây con | So tiền tố đường dẫn | Kiểm tra khoảng bao chứa | Lọc ancestor_id |
| Lấy tổ tiên/breadcrumb | So tiền tố hoặc tách path | Khoảng chứa nút | Lọc descendant_id |
| Lấy con trực tiếp | Dùng parent_id, hoặc tách path | Cần suy từ khoảng hoặc giữ parent_id | depth = 1 |
| Thêm lá | Thường thêm 1 hàng, tính path | Có thể dịch nhiều biên | Thêm nút + số tổ tiên + 1 cặp |
| Chuyển nhánh | Viết lại path của toàn cây con | Dịch/tính lại nhiều khoảng, có thể ảnh hưởng toàn cây | Xóa/thêm quan hệ giữa tổ tiên và cây con |
| Dung lượng tăng | Phụ thuộc tổng độ dài đường dẫn | O(N) hàng | O(N × độ sâu trung bình) cặp |
| Kiểm soát nhất quán | Path phải khớp cha và định danh | Biên không được cắt chéo, thứ tự hợp lệ | Closure phải đầy đủ, đúng depth và không chu trình |
| Điểm mạnh | Đơn giản, dễ debug, tiền tố thuận tiện | Truy vấn cây con tĩnh và đếm nhanh | Truy vấn đường lên, đường xuống, độ sâu linh hoạt |
| Điểm yếu | Chuyển nhánh lớn cập nhật nhiều hàng | Chỉnh sửa cấu trúc khó và nặng | Lưu nhiều hàng, duy trì phức tạp |

Với **N** nút, các mô hình path và nested sets lưu thêm thông tin trên khoảng **N hàng nút**, nhưng path có độ dài tăng theo độ sâu. Closure lưu số hàng bằng tổng số tổ tiên (kể cả tự thân) của mọi nút: có thể gần N với cây nông, gần N log N trong nhiều cây cân bằng và **N(N+1)/2** với cây dây dài. Đó là **ước lượng về kích thước cấu trúc**, không phải dự báo thời gian truy vấn tuyệt đối; chỉ mục, phân phối dữ liệu và engine quyết định hiệu suất thực tế.

### Cách lựa chọn theo nhu cầu

- **Danh mục sản phẩm được xem nhiều, ít tái cấu trúc:** materialized path là lựa chọn dễ triển khai; nested sets cũng đáng cân nhắc khi truy vấn theo khoảng và đếm nhánh nổi trội.
- **Cây phân quyền/tổ chức cần cả tổ tiên, hậu duệ và khoảng cách:** closure table có truy vấn rõ ràng; cần kiểm soát khối lượng cặp và các thao tác di chuyển.
- **Cây thay đổi liên tục và độ sâu không quá lớn:** adjacency list với **WITH RECURSIVE** có thể là phương án đầu tiên tốt hơn, trước khi thêm cấu trúc dẫn xuất.
- **Rất nhiều nút với độ sâu lớn:** đánh giá độ dài path, lượng hàng closure, số biên bị cập nhật ở nested sets, khóa và hiệu suất khi viết đồng thời.

Một hệ thống có thể **kết hợp adjacency list với materialized path hoặc closure table**: parent_id là thông tin cha trực tiếp, cấu trúc vật chất hóa phục vụ truy vấn nhanh. Nhưng mọi cấu trúc bổ sung trở thành **bất biến phải duy trì**; dữ liệu dư thừa có kiểm soát là sự đánh đổi để đổi lấy hiệu năng đọc.

## 6. Ràng buộc toàn vẹn và xử lý đồng thời

### 6.1. Những bất biến bắt buộc

Cho một cây hợp lệ:

1. Mỗi nút có một **định danh duy nhất**.
2. Một nút có nhiều nhất **một cha**; nút gốc không có cha.
3. Cha của một nút phải tồn tại và thuộc **cùng miền/tenant/cây** nếu hệ thống có phân vùng nghiệp vụ.
4. Không có **chu trình**: không thể đi từ một nút theo cạnh cha trở lại chính nút đó.
5. Không có cây con tự tách rời, trừ khi nghiệp vụ cho phép nhiều gốc.
6. Mỗi cấu trúc dẫn xuất phải thống nhất với quan hệ cha trực tiếp.

Kiểm tra **parent_id <> category_id** mới chỉ chặn chu trình độ dài 1. Chu trình độ dài 2 hoặc hơn vẫn cần kiểm tra tính đến tổ tiên. Trong materialized path, một lần cập nhật prefix sai có thể làm mọi path hậu duệ không đúng; trong nested sets, hai khoảng cắt nhau một phần là sai; trong closure table, thiếu hàng A → D khiến truy vấn tổ tiên không đầy đủ.

### 6.2. Kiểm tra trước khi chuyển nhánh

Trước khi chuyển X xuống dưới P, xác nhận **P không là X và không là hậu duệ của X**.

- Với **materialized path**, kiểm tra path(P) **không bắt đầu bằng** path(X), dùng so khớp an toàn theo ranh giới thành phần.
- Với **nested sets**, kiểm tra P không nằm trong khoảng [lft(X), rgt(X)].
- Với **closure table**, kiểm tra **không tồn tại** cặp (ancestor_id = X, descendant_id = P).

Ví dụ với closure table:

~~~sql
-- Nếu trả về hàng, không được chuyển nút X=2 xuống dưới P=6.
SELECT 1
FROM hier_closure
WHERE ancestor_id = 2
  AND descendant_id = 6;
~~~

Việc kiểm tra phải diễn ra **trong cùng giao dịch có cơ chế đồng bộ** với thao tác di chuyển, vì hai giao dịch có thể thay đổi cây đồng thời sau khi mỗi giao dịch đều đã kiểm tra thành công. Có thể khóa đối tượng cha, khóa theo cây/tenant hoặc sử dụng chiến lược tuần tự hóa phù hợp; mức cô lập và cách khôi phục sau xung đột cần được quyết định cụ thể.

### 6.3. Không trộn dữ liệu từ nhiều cây hoặc tenant

Nếu một hệ thống đa khách hàng có nhiều cây phân loại, phải đưa **tenant_id** hoặc **tree_id** vào quy tắc định danh và quan hệ. Ví dụ, dữ liệu closure nên dùng khóa và FK ghép để cấm ancestor thuộc tenant A nhưng descendant thuộc tenant B.

Nếu nested sets sử dụng biên lft/rgt lặp lại giữa nhiều cây, các truy vấn phải lọc đúng tree_id; chỉ UNIQUE(lft) toàn bảng không phù hợp với cách đánh số **riêng từng cây**. Đối với materialized path, quy ước path phải chứa định danh miền hoặc các ID trên toàn hệ thống phải là duy nhất để tránh cùng đường dẫn ở hai cây khác nhau.

### 6.4. Xóa, lưu trữ và thay đổi lịch sử

Quyết định **xóa cả cây con**, **chuyển con lên cha cũ** hoặc **không cho xóa nút còn con** phụ thuộc nghiệp vụ. Với danh mục từng được gắn vào sản phẩm/đơn hàng, xóa vật lý có thể làm mất tính toàn vẹn tham chiếu hoặc lịch sử; trạng thái **inactive/archived** thường là lựa chọn cần cân nhắc.

Nếu cần xem cây **tại thời điểm quá khứ**, một path hiện tại, một cặp lft/rgt hiện tại hoặc closure hiện tại không đủ. Cần mô hình thời gian hiệu lực, lịch sử đổi parent và cách dựng trạng thái phân cấp theo thời điểm. Đừng giả sử chỉ thêm cột created_at là lưu được lịch sử chuyển nhánh.

## 7. Truy vấn kiểm chứng tính đúng đắn

Khi lưu song song adjacency list và closure table, một số kiểm tra dữ liệu rất hữu ích.

### 7.1. Thiếu cặp tự thân

~~~sql
SELECT n.node_id
FROM hier_nodes AS n
LEFT JOIN hier_closure AS c
  ON c.ancestor_id = n.node_id
 AND c.descendant_id = n.node_id
 AND c.depth = 0
WHERE c.ancestor_id IS NULL;
~~~

Kết quả phải rỗng nếu mọi nút đều có closure tự thân.

### 7.2. Thiếu quan hệ cha trực tiếp

~~~sql
SELECT n.node_id, n.parent_id
FROM hier_nodes AS n
WHERE n.parent_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM hier_closure AS c
      WHERE c.ancestor_id = n.parent_id
        AND c.descendant_id = n.node_id
        AND c.depth = 1
  );
~~~

Kết quả phải rỗng. Tuy nhiên, **hai kiểm tra này chưa chứng minh bảng closure đã đầy đủ**: vẫn có thể thiếu các cặp ở độ sâu lớn hoặc có cặp dư. Muốn kiểm chứng toàn bộ, xây lại tập cặp kỳ vọng từ parent_id bằng CTE đệ quy trên dữ liệu đã được kiểm tra không có chu trình, rồi so sánh hai chiều bằng **EXCEPT**; nếu có bất kỳ khác biệt, cấu trúc dẫn xuất chưa nhất quán.

### 7.3. Kiểm tra nested sets

Với quy ước đánh số liên tiếp trong **một cây duy nhất**:

- Mỗi nút có lft < rgt và mỗi biên là duy nhất.
- Tổng cộng có **2N giá trị biên**, đúng tập số nguyên từ **1 đến 2N**.
- Với hai nút bất kỳ, khoảng của chúng phải rời nhau hoặc bao chứa hoàn toàn; không được giao nhau kiểu cắt chéo.
- Các cặp tổ tiên phải phù hợp với quan hệ parent_id, nếu có lưu song song.

Đếm đủ 2N và kiểm tra UNIQUE là **chưa đủ** để kết luận các khoảng lồng đúng; cần kiểm tra cấu trúc bao chứa.

### 7.4. Kiểm tra materialized path

Với mỗi nút:

- Path bắt đầu từ ID gốc và kết thúc bằng **ID của nút** cùng dấu phân cách.
- Path của cha là **tiền tố trực tiếp** của path nút con.
- Số thành phần trên path phản ánh đúng số cạnh từ gốc.
- Không có path của hai nút khác nhau trùng nhau; không có ID lặp trên một path nếu đó là cây.
- Mọi nút trong cùng phạm vi tenant/cây dùng cùng một quy tắc mã hóa và dấu phân cách.

Việc chọn ID số ổn định làm thành phần path giúp so sánh đơn giản hơn path chứa tên danh mục. Nếu cần URL thân thiện, có thể sinh slug hiển thị riêng; không nên dùng tên dễ đổi làm đường dẫn chuẩn duy nhất.

## 8. Khi dùng document database, đồ thị và kho dữ liệu phân tích

Bản chất quan hệ tổ tiên–hậu duệ không đổi khi chuyển công nghệ, nhưng cấu trúc lưu trữ được lựa chọn lại theo cách đọc và ghi:

| Kiến trúc | Cách thể hiện | Chi phí/giới hạn cần xét |
| --- | --- | --- |
| **Quan hệ (RDBMS)** | parent_id, path, nested sets hoặc closure | Ràng buộc PK/FK, truy vấn CTE, chỉ mục và cập nhật giao dịch |
| **Document** | Mỗi category document chứa parentId, ancestorIds hoặc path; có thể nhúng cây con | Di chuyển nhánh có thể cần cập nhật nhiều document; kích thước document, đồng bộ dữ liệu và truy vấn prefix |
| **Đồ thị** | Node Category với cạnh PARENT_OF hoặc CHILD_OF | Truy vấn duyệt đường đi thuận tiện; giới hạn nhiều cha, chu trình và quyền truy cập vẫn phải được kiểm soát |
| **Phân tích (warehouse)** | Hierarchy dimension, path/cấp, bảng bridge tổ tiên–hậu duệ | Tính đúng khi tổng hợp qua nhiều cấp, cập nhật chậm chiều phân cấp, lịch sử thay đổi cây |

### Document: lưu ancestorIds có kiểm soát

Một document Android có thể chứa:

~~~json
{
  "categoryId": 6,
  "name": "Android",
  "parentId": 4,
  "ancestorIds": [1, 2, 4],
  "path": "/1/2/4/6/"
}
~~~

**ancestorIds** giúp tìm các nút thuộc cây con theo phép kiểm tra phần tử mảng; **path** giúp hiển thị/so khớp tiền tố. Nhưng khi di chuyển Điện thoại, tất cả document hậu duệ vẫn phải cập nhật ancestorIds/path. Nếu chỉ cập nhật parentId mà quên hai trường dẫn xuất, kết quả truy vấn phân cấp sẽ khác nhau tùy trường sử dụng.

### Đồ thị: khi nào tree không đủ?

Nếu một chủ đề thuộc **nhiều chuyên mục cha** hoặc một tài nguyên được phân loại theo nhiều taxonomy, có thể là một **DAG**. Khi đó:

- Materialized path có thể cần **nhiều path cho cùng một nút**.
- Nested sets kiểu cây **không biểu diễn tự nhiên** một nút có nhiều cha cùng lúc.
- Closure table có thể lưu quan hệ **reachability** cho DAG, nhưng cặp tổ tiên–hậu duệ có thể có **nhiều đường đi và nhiều độ dài khác nhau**. Khóa (ancestor_id, descendant_id) với một depth duy nhất không đủ mô tả tất cả các đường nếu không xác định depth là **ngắn nhất**, **dài nhất** hay chính sách khác.

Với DAG thực sự, nên xét biểu diễn cạnh trực tiếp kèm truy vấn đồ thị/đệ quy, hoặc mở rộng closure để lưu ngữ nghĩa đường đi phù hợp. Tránh vô tình biến nhiều cha thành một cha chỉ vì chọn mô hình cây.

### Phân tích: tránh đếm trùng

Một sản phẩm gắn vào category Android sẽ đồng thời nằm dưới Điện thoại, Điện tử và Sản phẩm. Khi JOIN doanh thu sản phẩm với closure table, **một dòng fact có thể xuất hiện ở nhiều tổ tiên**. Điều đó đúng khi muốn báo cáo doanh thu **riêng cho từng cấp**, nhưng sai nếu lại cộng các cấp với nhau như những nhóm rời nhau.

Phải xác định rõ **grain (mức hạt)** của fact và cấp tổng hợp; nếu dữ liệu cho phép nhiều category cha, còn phải quyết định doanh thu được phân bổ, được đếm nhiều lần có chủ đích hay lọc theo taxonomy duy nhất.

## 9. Chọn mô hình qua tình huống thực tế

### Tình huống A: danh mục sản phẩm ít khi sắp xếp lại

**Yêu cầu:** Hàng trăm nghìn category, truy vấn cây con và breadcrumb thường xuyên, chỉnh sửa cấu trúc hiếm; có cache đọc.

**Phân tích:** Materialized path là phương án dễ hiểu và đáng thử trước. Nếu cần đọc cây con với điều kiện khoảng trên lượng lớn bản ghi, nested sets có thể được benchmark. Cần đo kích thước path, chi phí cập nhật hàng loạt và kế hoạch index trên dữ liệu đại diện.

### Tình huống B: cấu trúc phân quyền thay đổi thường xuyên

**Yêu cầu:** Bộ phận chuyển nhóm theo từng đợt, cần kiểm tra “nút A có là tổ tiên của B không?”, cần lịch sử quyền theo tổ chức.

**Phân tích:** Adjacency list kết hợp CTE đệ quy có thể đủ tốt nếu cây không sâu. Nếu cần lượng truy vấn tổ tiên lớn, cân nhắc closure table nhưng tính thêm chi phí tái tạo cặp khi chuyển nhánh. Quyền theo lịch sử còn cần mô hình thời gian hiệu lực và chính sách quyền riêng; closure hiện hành không đủ thay thế lịch sử.

### Tình huống C: cây thư mục có hàng triệu nút, nhiều lần chuyển nhánh

**Yêu cầu:** Cây rất lớn, người dùng liên tục di chuyển thư mục và đổi cha.

**Phân tích:** Nested sets với đánh số dày đặc thường gây nhiều ghi khi sửa cây. Materialized path buộc viết lại đường dẫn của nhiều hậu duệ. Closure table cũng cần viết lại nhiều quan hệ. Hãy đo khả năng chịu tải và cân nhắc dùng adjacency list làm chuẩn, tối ưu truy vấn theo nhu cầu; có thể cache đường dẫn hoặc duy trì cấu trúc đọc bất đồng bộ nếu nghiệp vụ cho phép độ trễ đồng bộ và có cơ chế nhận biết dữ liệu chưa cập nhật.

### Tình huống D: sản phẩm có thể nằm trong nhiều nhánh taxonomy

**Yêu cầu:** Một danh mục con có nhiều cha hợp lệ và có thể có nhiều đường đi về gốc.

**Phân tích:** Đây không còn là cây thông thường. Phải mô hình hóa các cạnh cha–con dạng nhiều–nhiều hoặc DAG với ràng buộc không chu trình. Không áp dụng trực tiếp một path duy nhất hay một cặp lft/rgt; closure nếu dùng cần định nghĩa rõ tính reachability và độ sâu.

## 10. Quy trình quyết định và kiểm thử

Khi thiết kế một phân cấp mới, nên làm tuần tự:

1. **Xác định bản chất quan hệ:** cây, rừng cây, DAG hay hệ phân cấp nhiều chiều?
2. **Xác định định danh:** ID của nút có ổn định khi đổi tên, đổi cha hoặc chuyển tenant không?
3. **Ghi các truy vấn chủ yếu:** cây con, đường tới gốc, con trực tiếp, chiều sâu, kiểm tra tổ tiên, tổng hợp doanh thu theo danh mục.
4. **Đo đặc điểm dữ liệu:** số nút, độ sâu trung bình/tối đa, tỷ lệ nhánh nhỏ/lớn, số lần di chuyển mỗi ngày.
5. **Chọn nguồn sự thật:** parent_id/cạnh trực tiếp; quyết định thêm path, interval hoặc closure vì lợi ích đọc nào.
6. **Thiết kế ràng buộc:** PK/FK, một cha, không chu trình, cách biểu diễn gốc, giới hạn cây/tenant, dữ liệu dẫn xuất nhất quán.
7. **Thiết kế thao tác cấu trúc:** thêm lá, đổi cha, chuyển nhánh, xóa hoặc lưu trữ; giao dịch và khóa để tránh cập nhật cạnh tranh sai.
8. **Tạo chỉ mục theo truy vấn:** thử EXPLAIN trên dữ liệu đại diện; tránh chỉ mục trùng hoặc quá nhiều chỉ mục làm chậm ghi.
9. **Thiết lập kiểm chứng:** đối chiếu path/closure/interval với cạnh trực tiếp; giám sát lỗi và khả năng xây lại dữ liệu dẫn xuất.
10. **Thử tình huống biên:** cây một nút, cây dây sâu, cây rất rộng, nhiều gốc, di chuyển nút tới hậu duệ, hai giao dịch chuyển nhánh đồng thời.

### Bài tự kiểm tra có gợi ý

**Câu 1.** Path của Điện thoại là **/1/2/4/**; path Android là **/1/2/4/6/**. Chuyển Điện thoại sang làm con Thời trang (path **/1/3/**) thì path của hai nút thay đổi thế nào?

**Gợi ý:** Điện thoại thành **/1/3/4/**; Android thành **/1/3/4/6/**. Nút con giữ quan hệ cha trực tiếp là Điện thoại nhưng thay toàn bộ tiền tố tổ tiên cũ.

**Câu 2.** Trong nested sets, Điện tử có khoảng [2,9]. Có bao nhiêu nút trong cây con? Android [4,5] có nằm trong cây con này không?

**Gợi ý:** **(9 − 2 + 1)/2 = 4** nút; [4,5] nằm hoàn toàn trong [2,9] nên Android là hậu duệ của Điện tử.

**Câu 3.** Closure có (2,6,2) và (4,6,1). Hai hàng đó cho biết điều gì? Để lấy **con trực tiếp** của 2, lọc theo điều kiện nào?

**Gợi ý:** Android (6) cách Điện tử (2) hai cạnh và cách Điện thoại (4) một cạnh; lọc **ancestor_id = 2 AND depth = 1** để lấy con trực tiếp.

**Câu 4.** Bảng closure có đầy đủ các cặp tự thân và cặp cha trực tiếp. Có đủ để kết luận toàn bộ closure đúng không?

**Gợi ý:** **Chưa.** Có thể thiếu các cặp tổ tiên xa, có cặp sai hoặc depth sai. Phải đối chiếu toàn bộ tập reachability với cây nguồn và kiểm tra không chu trình.

**Câu 5.** Một Category có thể thuộc hai Category cha. Nên áp dụng trực tiếp nested sets kiểu cây không?

**Gợi ý:** Không. Quy tắc “mỗi nút có tối đa một cha” đã thay đổi. Hãy xác định DAG, biểu diễn cạnh nhiều–nhiều và kiểm tra không chu trình; các phương pháp lưu tổ tiên cần thiết kế lại cho nhiều đường đi.

## 11. Điều cần ghi nhớ

**Materialized path** lưu đường đi và thuận tiện cho so tiền tố; **nested sets** lưu khoảng bao chứa và thuận tiện cho cây tương đối tĩnh; **closure table** lưu cặp tổ tiên–hậu duệ với độ sâu và thuận tiện cho các truy vấn phân cấp linh hoạt. Mô hình nào cũng có chi phí khi thay đổi cấu trúc và đều cần bảo vệ tính nhất quán. Hãy chọn dựa trên **mô hình nghiệp vụ thực sự là cây hay đồ thị**, tần suất đọc/ghi, độ sâu, phạm vi tenant và khả năng kiểm chứng dữ liệu, thay vì chọn chỉ vì một truy vấn mẫu chạy ngắn hơn.
