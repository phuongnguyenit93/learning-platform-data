# Kiểm thử cây rỗng, nhiều gốc, nút mồ côi và dữ liệu có vòng trong SQL đệ quy

Truy vấn đệ quy thường được dùng để duyệt cây danh mục, cơ cấu phòng ban, thư mục, bình luận theo cấp, cấu trúc sản phẩm hoặc những dữ liệu phân cấp khác. Khi thử với một cây “đẹp” gồm một gốc và vài cấp con, câu `WITH RECURSIVE` có thể cho kết quả đúng. Nhưng dữ liệu thực tế không phải lúc nào cũng tạo thành một cây chuẩn: bảng có thể **rỗng**, có **nhiều gốc**, chứa **nút mồ côi** (*orphan node*), hoặc có **vòng tham chiếu** (*cycle*) khiến quá trình duyệt lặp mãi.

Bài học này hướng dẫn thiết kế bộ dữ liệu thử, xác định kết quả mong đợi và viết các truy vấn SQL để phát hiện những tình huống ấy. Trọng tâm không chỉ là làm sao câu SQL **không lỗi**, mà còn là làm sao biết nó **không bỏ sót dữ liệu**, **không đếm nhầm nút**, **không nhầm nút mồ côi với nút thuộc vòng** và **không dựa vào giới hạn đệ quy để che dữ liệu không hợp lệ**.

Các ví dụ chạy được theo cú pháp **PostgreSQL**, dùng mảng `INTEGER[]` để theo dõi đường đi. Cuối bài trình bày cách thích nghi với PostgreSQL `CYCLE`, SQL Server, MySQL/MariaDB, SQLite và Oracle. Nếu quản lý quan hệ nhiều-cha/nhiều-con bằng bảng cạnh, bạn sẽ cần điều chỉnh một số giả định quan trọng của mô hình cây một cha.

## 1. Trước khi kiểm thử: định nghĩa cấu trúc cây

Mô hình **adjacency list** lưu mỗi nút trong một hàng và dùng `parent_id` trỏ đến nút cha:

```sql
-- Hình dạng đơn giản của một hàng
node_id    INTEGER
parent_id  INTEGER   -- NULL nếu là gốc
node_name  TEXT
```

Ví dụ một cây hợp lệ:

```text
1  Root
├── 2  Section A
│   └── 4  Item
└── 3  Section B
```

Dữ liệu:

| node_id | parent_id | node_name |
|---:|---:|---|
| 1 | `NULL` | Root |
| 2 | 1 | Section A |
| 3 | 1 | Section B |
| 4 | 2 | Item |

Với mô hình này, một hàng chỉ có **một `parent_id`**, nên mỗi nút có nhiều nhất **một cha trực tiếp**. Nếu hệ thống định nghĩa một **cây duy nhất, không rỗng**, một cấu trúc hợp lệ thường cần:

- Có **chính xác một gốc**, nghĩa là một hàng có `parent_id IS NULL`.
- Mọi nút khác có một cha tồn tại trong đúng phạm vi cây.
- Không có chu trình trên quan hệ cha–con.
- Mọi nút đều đi tới được từ gốc khi duyệt theo chiều cha → con.

Nếu nghiệp vụ cho phép **rừng cây** (*forest*), có thể có **nhiều gốc** và mỗi gốc là đầu của một thành phần hợp lệ. Nếu nghiệp vụ cho phép cây rỗng, **không có hàng nào** là một trạng thái hợp lệ; khi đó “phải có một gốc” chỉ áp dụng cho cây **không rỗng**.

### 1.1. Bốn tình huống biên cần phân biệt

| Tình huống | Hình thái dữ liệu | Rủi ro khi truy vấn |
|---|---|---|
| **Cây rỗng** | Không có hàng nút | Nhầm không có nút với lỗi; `COUNT(*)` trên `LEFT JOIN` cho số sai |
| **Nhiều gốc** | Có nhiều hàng `parent_id IS NULL` | Duyệt chỉ một gốc và bỏ mất những nhánh còn lại |
| **Nút mồ côi** | `parent_id` khác `NULL` nhưng không tìm được hàng cha | Duyệt từ gốc bỏ sót nút đó và có thể cả hậu duệ |
| **Dữ liệu có vòng** | Theo `parent_id` một lúc nào đó quay về nút đã gặp | Đệ quy không dừng, bị giới hạn độ sâu hoặc sinh nhiều kết quả lặp |

Đối với cây một cha, một thành phần có vòng thường **không nối về được một gốc hợp lệ**. Vì vậy câu `WITH RECURSIVE` chỉ bắt đầu từ gốc có thể **không bao giờ đụng vòng**, nhưng cũng **không bao giờ thấy các nút trong thành phần ấy**. Đây là lý do phải có cả kiểm tra **khả năng đi tới từ gốc** và kiểm tra **vòng trên toàn bộ nút**.

### 1.2. “Mồ côi trực tiếp” và “không đi tới được” không giống nhau

Giả sử:

```text
20 (parent_id = 99)   -- không có nút 99
└── 21 (parent_id = 20)
```

- Nút **20** là **mồ côi trực tiếp**: cha tham chiếu tới 99 nhưng 99 không tồn tại.
- Nút **21** không mồ côi trực tiếp vì nút cha 20 vẫn tồn tại. Nhưng 21 **không đi tới được từ gốc** nếu gốc không nối với 20.

Tương tự, nút thuộc một vòng có thể có cha tồn tại đầy đủ, không có orphan trực tiếp, nhưng vẫn không đi tới được từ gốc. Một bộ kiểm thử chỉ kiểm tra khóa ngoại thiếu cha sẽ không phát hiện được vòng.

## 2. Tạo bộ dữ liệu thử độc lập cho từng tình huống

Để chạy nhiều ca kiểm thử mà không phải xóa bảng sau mỗi lần, ta thêm cột `scenario` biểu thị tên tình huống. **Khóa nút là cặp `(scenario, node_id)`**, không phải chỉ `node_id`.

Bảng kiểm thử cố ý **không có khóa ngoại từ `parent_id` sang nút cha**, để có thể chèn các trường hợp dữ liệu hỏng. Đây là **fixture kiểm thử**, không phải khuyến nghị bỏ ràng buộc cha–con trong bảng sản xuất.

```sql
-- PostgreSQL: tạo bảng tạm phục vụ ví dụ.
CREATE TEMP TABLE demo_tree_nodes (
    scenario TEXT NOT NULL,
    node_id INTEGER NOT NULL,
    parent_id INTEGER,
    node_name TEXT NOT NULL,
    PRIMARY KEY (scenario, node_id)
);

INSERT INTO demo_tree_nodes
    (scenario, node_id, parent_id, node_name)
VALUES
    -- Cây hợp lệ: một gốc, ba nút dưới gốc.
    ('normal', 1, NULL, 'Root'),
    ('normal', 2, 1,    'Section A'),
    ('normal', 3, 1,    'Section B'),
    ('normal', 4, 2,    'Item'),

    -- Rừng: hai gốc không phụ thuộc nhau.
    ('multiple_roots', 1,  NULL, 'Root A'),
    ('multiple_roots', 2,  1,    'Child A'),
    ('multiple_roots', 10, NULL, 'Root B'),
    ('multiple_roots', 11, 10,   'Child B'),

    -- Hai cha không tồn tại, một hậu duệ của orphan.
    ('orphan', 1,  NULL, 'Root'),
    ('orphan', 2,  1,    'Valid child'),
    ('orphan', 20, 99,   'Orphan A'),
    ('orphan', 21, 20,   'Child of orphan A'),
    ('orphan', 30, 100,  'Orphan B'),

    -- Một chu trình ba nút; một nhánh dẫn vào chu trình;
    -- một chu trình tự trỏ; thêm cây hợp lệ độc lập.
    ('cycle', 1,  NULL, 'Root'),
    ('cycle', 2,  1,    'Reachable child'),
    ('cycle', 10, 11,   'Cycle A'),
    ('cycle', 11, 12,   'Cycle B'),
    ('cycle', 12, 10,   'Cycle C'),
    ('cycle', 13, 10,   'Leads to cycle'),
    ('cycle', 20, 20,   'Self cycle');
```

**Tình huống `empty` không chèn bất kỳ nút nào.** Nó được nhận diện bằng tên tình huống trong các truy vấn kiểm tra tổng hợp bên dưới, chứ không cần thêm một hàng giả vào bảng cây.

### 2.1. Bảng kết quả mong đợi

| scenario | Số nút | Số gốc | Mồ côi trực tiếp | Không tới được từ gốc |
|---|---:|---:|---:|---:|
| `empty` | 0 | 0 | 0 | 0 |
| `normal` | 4 | 1 | 0 | 0 |
| `multiple_roots` | 4 | 2 | 0 | 0 |
| `orphan` | 5 | 1 | 2 | 3 |
| `cycle` | 7 | 1 | 0 | 5 |

Các hàng “không tới được” của `orphan` là **20, 21, 30**. Của `cycle` là **10, 11, 12, 13, 20**. Nút 13 không thuộc vòng ba nút, nhưng nếu cứ lần theo cha của nó thì sẽ bước vào vòng.

**Cảnh báo về diễn giải bảng:** `empty` có 0 gốc vì nó hoàn toàn không có nút. Nếu ứng dụng cho phép rỗng, đây là kết quả hợp lệ; nếu hợp đồng yêu cầu ít nhất một nút, đây là thất bại nghiệp vụ. Kiểm thử cần phân biệt hai chính sách.

## 3. Truy vấn đệ quy cơ bản: duyệt tất cả gốc

Để duyệt theo chiều **cha → con**, ta dùng hai phần:

- **Anchor**: chọn tất cả hàng có `parent_id IS NULL`.
- **Recursive member**: lấy các nút con có `parent_id = node_id` của hàng đã duyệt.

Truy vấn PostgreSQL:

```sql
WITH RECURSIVE walk AS (
    SELECT
        n.scenario,
        n.node_id,
        n.parent_id,
        n.node_name,
        0 AS depth,
        ARRAY[n.node_id]::INTEGER[] AS path
    FROM demo_tree_nodes AS n
    WHERE n.scenario = 'normal'
      AND n.parent_id IS NULL

    UNION ALL

    SELECT
        child.scenario,
        child.node_id,
        child.parent_id,
        child.node_name,
        parent.depth + 1,
        parent.path || child.node_id
    FROM walk AS parent
    JOIN demo_tree_nodes AS child
      ON child.scenario = parent.scenario
     AND child.parent_id = parent.node_id
    WHERE NOT (child.node_id = ANY(parent.path))
)
SELECT node_id, parent_id, node_name, depth, path
FROM walk
ORDER BY path;
```

Kết quả với `normal`:

| node_id | parent_id | depth | path |
|---:|---:|---:|---|
| 1 | `NULL` | 0 | `{1}` |
| 2 | 1 | 1 | `{1,2}` |
| 4 | 2 | 2 | `{1,2,4}` |
| 3 | 1 | 1 | `{1,3}` |

`path` lưu những ID đã đi qua trong nhánh hiện tại. Điều kiện `NOT (child.node_id = ANY(parent.path))` ngăn thêm một nút nếu nó **đã nằm trên đường đi ấy**, qua đó tránh đi vòng vô hạn khi dữ liệu/quan hệ có chu trình.

### 3.1. Tại sao kiểm tra cả scenario khi JOIN?

Bởi vì ID 1, 2 xuất hiện ở nhiều tình huống. Nếu chỉ viết:

```sql
-- SAI trong bảng fixture có nhiều phạm vi trùng node_id:
JOIN demo_tree_nodes AS child
  ON child.parent_id = parent.node_id
```

thì từ nút 1 của `normal` có thể vô tình kéo cả nút 2 từ `orphan` hoặc `cycle` vào kết quả. Điều kiện:

```sql
child.scenario = parent.scenario
AND child.parent_id = parent.node_id
```

đảm bảo truy vấn không “đi xuyên” giữa các cây. Trong hệ thống đa tenant, quy tắc tương tự áp dụng cho `tenant_id`, `organization_id` hay `tree_id`: **phạm vi khóa phải hiện diện trong phép JOIN**.

### 3.2. Vì sao dùng UNION ALL?

`UNION ALL` giữ các hàng mỗi vòng đệ quy tạo ra và tránh bước khử trùng của `UNION`. Với cây đúng một cha và anchor đúng, mỗi nút có một đường duyệt từ gốc. Vì vậy `UNION ALL` là lựa chọn thường gặp.

**`UNION` không phải thuốc chữa vòng vạn năng.** Nếu CTE thêm cột `depth` hoặc `path`, việc đi lại một nút tạo hàng **khác về depth/path**, nên `UNION` vẫn có thể thấy các hàng khác nhau và tiếp tục lặp. Hãy dùng kiểm tra đã thăm, tính năng `CYCLE` hoặc chiến lược khống chế lặp phù hợp.

### 3.3. Sắp xếp không đồng nghĩa thứ tự đánh giá đệ quy

`ORDER BY path` ở ngoài giúp trình bày nhánh cây dễ đọc; nó không cam kết engine đã xử lý các hàng vật lý theo thứ tự depth-first. PostgreSQL có những cơ chế như `SEARCH DEPTH FIRST` để tạo cột thứ tự trong các phiên bản phù hợp, nhưng **thứ tự trình bày cuối vẫn cần `ORDER BY`** trên khóa thứ tự mong muốn.

## 4. Kiểm thử cây rỗng: “không có dữ liệu” phải có kết quả mong đợi

Trong fixture, không có hàng nào có `scenario = 'empty'`. Thử truy vấn duyệt:

```sql
WITH RECURSIVE walk AS (
    SELECT scenario, node_id, parent_id
    FROM demo_tree_nodes
    WHERE scenario = 'empty'
      AND parent_id IS NULL

    UNION ALL

    SELECT c.scenario, c.node_id, c.parent_id
    FROM walk AS p
    JOIN demo_tree_nodes AS c
      ON c.scenario = p.scenario
     AND c.parent_id = p.node_id
)
SELECT node_id
FROM walk;
```

**Kết quả đúng là 0 hàng**, không có lỗi và không có bước đệ quy tạo nút. Phần anchor không có hàng nên recursive member cũng không có điểm xuất phát.

### 4.1. COUNT(*) và COUNT(cột) trên tập rỗng

```sql
SELECT COUNT(*) AS node_count
FROM demo_tree_nodes
WHERE scenario = 'empty';
-- 0
```

Nếu cần một dòng kết quả ngay cả khi không có nút, dùng phép tổng hợp này. Nhưng cần cẩn thận khi kiểm tra qua bảng tình huống và `LEFT JOIN`:

```sql
-- PostgreSQL: một hàng tên tình huống, không có nút khớp.
SELECT
    s.scenario,
    COUNT(*) AS joined_rows,
    COUNT(n.node_id) AS real_nodes
FROM (VALUES ('empty')) AS s(scenario)
LEFT JOIN demo_tree_nodes AS n
  ON n.scenario = s.scenario
GROUP BY s.scenario;
```

Kết quả:

| scenario | joined_rows | real_nodes |
|---|---:|---:|
| empty | 1 | 0 |

Vì `LEFT JOIN` vẫn tạo một hàng bên trái với các cột `n` là `NULL`, `COUNT(*)` trả **1**. Để đếm các nút thật, dùng `COUNT(n.node_id)` với cột khóa chính bên phải không thể `NULL`.

Đừng đánh dấu cây rỗng là có một nút chỉ vì thấy một hàng trong kết quả `LEFT JOIN`.

### 4.2. Cây rỗng có cần một gốc không?

Định nghĩa kiểm thử phải theo hợp đồng:

- **Cho phép cây rỗng:** 0 nút và 0 gốc được chấp nhận.
- **Yêu cầu cây không rỗng:** 0 nút bị từ chối hoặc được xử lý ở bước khởi tạo.
- **Bắt buộc một gốc khi có nút:** với `node_count > 0`, phải có đúng 1 gốc.

Không nên chỉ viết `root_count = 1` cho mọi tình huống nếu ứng dụng thực sự cho phép cây rỗng. Khi đó bài kiểm tra sẽ báo lỗi giả cho một trạng thái bình thường.

### 4.3. API nên dùng [] hay null?

Nếu API trả danh sách các nút gốc, cây rỗng thường có thể biểu diễn:

```json
{"roots": []}
```

Nếu cần báo rõ “cây chưa tồn tại”, có thể dùng một trường trạng thái hoặc mã lỗi nghiệp vụ riêng. SQL trả 0 hàng không tự quyết định JSON phải là `[]` hay `null`; đó là hợp đồng tầng ứng dụng. Không thêm nút giả chỉ để tránh tập rỗng trong dữ liệu.

## 5. Kiểm thử nhiều gốc: truy vấn không được bỏ mất cả nhánh

Fixture `multiple_roots`:

```text
1  Root A           10 Root B
└── 2 Child A       └── 11 Child B
```

Truy vấn chọn mọi gốc:

```sql
SELECT node_id, node_name
FROM demo_tree_nodes
WHERE scenario = 'multiple_roots'
  AND parent_id IS NULL
ORDER BY node_id;
-- 1 Root A; 10 Root B.
```

Khi đổi điều kiện `scenario = 'normal'` trong truy vấn đệ quy ở phần 3 thành `scenario = 'multiple_roots'`, anchor lấy **cả hai gốc**, và kết quả sẽ có **bốn nút**.

### 5.1. Lỗi thường gặp: chỉ lấy gốc đầu tiên

```sql
-- Ví dụ SAI nếu nghiệp vụ cho phép nhiều gốc.
SELECT node_id
FROM demo_tree_nodes
WHERE scenario = 'multiple_roots'
  AND parent_id IS NULL
ORDER BY node_id
LIMIT 1;
```

Truy vấn trên chỉ chọn nút 1. Nếu dùng nó làm anchor duy nhất, toàn bộ nhánh `10 → 11` bị bỏ sót mà không báo lỗi.

**Không sửa dữ liệu nhiều gốc bằng cách tự chọn một gốc ngẫu nhiên.** Nếu hệ thống cho phép forest, anchor phải lấy tất cả gốc. Nếu hệ thống bắt buộc một cây duy nhất, nhiều gốc là **dữ liệu sai hợp đồng** và cần được phát hiện.

### 5.2. Kiểm đếm số gốc đúng

```sql
SELECT
    COUNT(*) AS root_count
FROM demo_tree_nodes
WHERE scenario = 'multiple_roots'
  AND parent_id IS NULL;
-- 2
```

Đừng dùng `COUNT(parent_id)` để đếm gốc: `COUNT(column)` bỏ qua `NULL`, nên nó trả **0** nếu tất cả hàng được lọc đều có `parent_id IS NULL`.

Với bảng có nhiều gốc, việc chọn `MIN(node_id)` cũng chỉ trả một mã gốc; nó **không biến cấu trúc thành cây hợp lệ**.

### 5.3. Phân biệt forest và dữ liệu lỗi

| Quy tắc nghiệp vụ | Hai gốc 1 và 10 | Hành động phù hợp |
|---|---|---|
| Danh mục cho phép nhiều danh mục cấp cao nhất | Hợp lệ | Duyệt cả hai gốc |
| Mỗi tổ chức phải có một sơ đồ cơ cấu duy nhất | Có thể không hợp lệ | Báo lỗi dữ liệu hoặc yêu cầu chọn một cây cụ thể |
| Mỗi tenant có một gốc | Tùy cách phân nhóm | Kiểm tra số gốc **theo tenant** |
| Cho phép nhiều cây riêng trong một bảng | Hợp lệ nếu có định danh cây/forest rõ | Dùng đúng `tree_id`/`scenario` trong JOIN |

Một câu SQL trả đủ nút chưa chứng minh dữ liệu đáp ứng yêu cầu một gốc. **Kiểm thử kết quả truy vấn** và **kiểm thử tính hợp lệ của mô hình dữ liệu** cần các tiêu chí riêng.

## 6. Kiểm thử nút mồ côi trực tiếp

Nút mồ côi trực tiếp có `parent_id IS NOT NULL` nhưng **không tồn tại nút cha** trong đúng phạm vi. Truy vấn tự nối bảng giúp phát hiện:

```sql
SELECT
    child.node_id,
    child.node_name,
    child.parent_id AS missing_parent_id
FROM demo_tree_nodes AS child
WHERE child.scenario = 'orphan'
  AND child.parent_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM demo_tree_nodes AS parent
      WHERE parent.scenario = child.scenario
        AND parent.node_id = child.parent_id
  )
ORDER BY child.node_id;
```

Kết quả:

| node_id | node_name | missing_parent_id |
|---:|---|---:|
| 20 | Orphan A | 99 |
| 30 | Orphan B | 100 |

Nút 21 **không xuất hiện** vì cha trực tiếp của nó là 20, và hàng 20 vẫn tồn tại. Nhưng 21 vẫn ở trong thành phần không có đường về gốc.

### 6.1. Vì sao kiểm tra cha phải cùng phạm vi?

Nếu bảng chứa nhiều tenant hoặc nhiều cây, một nút có `parent_id = 99` chỉ hợp lệ khi **nút 99 của đúng tenant/cây ấy** tồn tại. Một nút 99 ở tenant khác không được coi là cha hợp lệ.

`NOT EXISTS` thường phù hợp cho kiểm tra tồn tại vì không làm nhân bản hàng và không có bẫy `NOT IN` khi tập có `NULL`. Có thể viết tương đương bằng `LEFT JOIN ... WHERE parent.node_id IS NULL`, nhưng phải nối đúng khóa và phân biệt cột khóa thật với các thuộc tính có thể `NULL`.

### 6.2. Không dùng NOT IN một cách tùy tiện

Một cách viết dễ gây rủi ro ở các cấu trúc dữ liệu khác:

```sql
-- Tránh thay thế máy móc bằng NOT IN nếu tập bên phải
-- có thể chứa NULL hoặc phạm vi không được kiểm soát.
WHERE child.parent_id NOT IN (
    SELECT parent.node_id
    FROM demo_tree_nodes AS parent
);
```

Khi truy vấn con của `NOT IN` có `NULL`, logic ba giá trị có thể làm kết quả khó dự đoán hoặc rỗng. Dữ liệu mẫu dùng `node_id` là khóa chính `NOT NULL` nên không gặp `NULL` ở chính cột đó, nhưng `NOT EXISTS` vẫn bộc lộ rõ **điều kiện khớp cả phạm vi và ID**.

### 6.3. Khóa ngoại trong bảng thật thường ngăn được orphan trực tiếp

Nếu `(scenario, parent_id)` là khóa ngoại tham chiếu `(scenario, node_id)`, DBMS thường từ chối chèn một nút có `parent_id = 99` khi nút 99 không tồn tại (với ràng buộc đang được kiểm tra).

Chính vì thế, **bảng fixture cố ý không đặt FK**: nếu thêm FK ngay từ đầu, chúng ta không thể tái hiện lỗi orphan trực tiếp để kiểm thử bộ phát hiện.

Nhưng FK **không đủ để bảo đảm cây không có vòng**, vì một chu trình có thể gồm toàn các nút tồn tại hợp lệ. Phần sau sẽ phân biệt hai loại kiểm tra ấy.

## 7. Không thể chỉ tìm orphan trực tiếp: cần tìm nút không đi tới được

Để biết một nút có thuộc cây bắt đầu từ một gốc hợp lệ không, ta có thể:

1. Duyệt từ **tất cả gốc**.
2. Lấy tập các ID đã duyệt được.
3. So sánh với **toàn bộ nút** của tình huống.
4. Những ID còn lại là **không đi tới được từ gốc**.

Ví dụ PostgreSQL với `orphan`:

```sql
WITH RECURSIVE reachable AS (
    SELECT
        n.scenario,
        n.node_id,
        ARRAY[n.node_id]::INTEGER[] AS path
    FROM demo_tree_nodes AS n
    WHERE n.scenario = 'orphan'
      AND n.parent_id IS NULL

    UNION ALL

    SELECT
        c.scenario,
        c.node_id,
        r.path || c.node_id
    FROM reachable AS r
    JOIN demo_tree_nodes AS c
      ON c.scenario = r.scenario
     AND c.parent_id = r.node_id
    WHERE NOT (c.node_id = ANY(r.path))
)
SELECT
    n.node_id,
    n.parent_id,
    n.node_name
FROM demo_tree_nodes AS n
WHERE n.scenario = 'orphan'
  AND NOT EXISTS (
      SELECT 1
      FROM reachable AS r
      WHERE r.scenario = n.scenario
        AND r.node_id = n.node_id
  )
ORDER BY n.node_id;
```

**Kết quả:** nút **20, 21, 30**. Đây là tập “không đi tới được”, **không phải chỉ orphan trực tiếp**.

### 7.1. Kiểm tra orphan và unreachable trả lời hai câu hỏi khác nhau

- `orphan_count = 2`: có hai hàng **trỏ trực tiếp tới một cha không tồn tại**.
- `unreachable_count = 3`: có ba hàng **không thể duyệt tới từ bất kỳ gốc hợp lệ nào**.

Nếu một chương trình chỉ xuất danh sách bắt đầu từ root 1, màn hình có thể “trông ổn” với hai nút 1,2, nhưng vẫn âm thầm **mất ba nút còn lại**. Bộ kiểm thử phải so tổng số nút nguồn với số nút đi tới được, chứ không chỉ kiểm tra rằng truy vấn có trả vài hàng.

### 7.2. Một nút không đi tới được chưa chắc là orphan trực tiếp

Với `cycle`, tất cả các liên kết trong vòng đều chỉ tới những nút **có tồn tại**. Vì vậy số orphan trực tiếp bằng **0**. Nhưng vẫn có **5 nút không đi tới được** từ gốc. Không được suy từ `unreachable_count > 0` rằng tất cả hàng còn lại đều là orphan trực tiếp.

Để chẩn đoán chính xác, kết hợp **phát hiện orphan**, **đếm gốc**, **duyệt reachable**, và **tìm cycle**.

## 8. Dữ liệu có vòng: khác biệt giữa cây và đồ thị

Trong `cycle` có cấu trúc:

```text
Phần cây hợp lệ:         Một vòng ba nút:

1 Root                  10 → cha 11
└── 2 Child             11 → cha 12
                        12 → cha 10

Nút dẫn tới vòng:       Tự trỏ:
13 → cha 10             20 → cha 20
```

Khi theo chiều **nút → cha**:

```text
10 → 11 → 12 → 10 → 11 → 12 → ...
13 → 10 → 11 → 12 → 10 → ...
20 → 20 → 20 → ...
```

Những đường này không tự dừng nếu cứ tiếp tục JOIN lên cha.

### 8.1. Điểm dễ bỏ sót: duyệt từ root không nhất thiết thấy vòng

Nếu dùng anchor `WHERE parent_id IS NULL` và duyệt **cha → con**, kết quả `cycle` chỉ có **1 và 2**. Nó không đi tới vòng 10–11–12 hoặc nút 20.

Trong mô hình mỗi nút **chỉ có một parent_id**, một nút nằm trong vòng đã “dành” quan hệ cha cho nút khác của vòng. Nó không thể đồng thời trỏ tới một cha bên ngoài vòng để nối thành chuỗi bắt đầu từ root. Vì thế một thành phần có vòng **không có đường parent chain kết thúc ở root**, và duyệt từ gốc bỏ qua thành phần đó.

**Hệ quả kiểm thử:** điều kiện bảo vệ vòng bên trong root traversal là hữu ích, nhưng **không đủ chứng minh toàn bảng không có vòng**. Cần thuật toán bắt đầu từ **mọi nút** hoặc một cơ chế phát hiện chu trình toàn cục.

Với đồ thị tổng quát dùng **bảng cạnh nhiều-cha**, một nhánh từ root có thể thật sự đi vào chu trình. Khi ấy phải dùng đường đi và phát hiện thăm lại trên từng nhánh để dừng đệ quy.

## 9. Phát hiện vòng toàn cục bằng cách đi lên cha

Một cách trực quan cho mô hình `parent_id` là **lấy từng nút làm điểm xuất phát**, liên tục tìm cha trực tiếp, và ghi đường đi. Khi cha sắp đi tới đã xuất hiện trong `path`, ta đánh dấu vòng rồi **không mở rộng nhánh đó thêm**.

```sql
-- PostgreSQL: phát hiện mọi điểm xuất phát có parent-chain đi vào vòng.
WITH RECURSIVE parent_walk AS (
    SELECT
        n.scenario,
        n.node_id AS start_id,
        n.node_id AS current_id,
        n.parent_id AS next_parent_id,
        ARRAY[n.node_id]::INTEGER[] AS path,
        FALSE AS cycle_found
    FROM demo_tree_nodes AS n
    WHERE n.scenario = 'cycle'

    UNION ALL

    SELECT
        w.scenario,
        w.start_id,
        p.node_id AS current_id,
        p.parent_id AS next_parent_id,
        w.path || p.node_id AS path,
        p.node_id = ANY(w.path) AS cycle_found
    FROM parent_walk AS w
    JOIN demo_tree_nodes AS p
      ON p.scenario = w.scenario
     AND p.node_id = w.next_parent_id
    WHERE NOT w.cycle_found
)
SELECT start_id, path AS repeated_path
FROM parent_walk
WHERE cycle_found
ORDER BY start_id;
```

**Kết quả có các `start_id`: 10, 11, 12, 13, 20.**

Một số đường đi minh họa:

| start_id | repeated_path | Ý nghĩa |
|---:|---|---|
| 10 | `{10,11,12,10}` | Đi qua vòng rồi gặp lại 10 |
| 11 | `{11,12,10,11}` | Đi qua vòng rồi gặp lại 11 |
| 12 | `{12,10,11,12}` | Đi qua vòng rồi gặp lại 12 |
| 13 | `{13,10,11,12,10}` | Từ 13 bước **vào** vòng 10–11–12 |
| 20 | `{20,20}` | Vòng tự trỏ một nút |

### 9.1. Vì sao truy vấn dừng?

Câu `WHERE NOT w.cycle_found` chỉ cho phép mở rộng các hàng **chưa phát hiện vòng**. Ở lần bước tới nút đã nằm trong `path`, hàng mới được tạo với `cycle_found = TRUE` và được giữ để báo cáo đường đi; **lượt sau nó không được mở rộng nữa**.

Đường đi cũng kết thúc khi:

- `next_parent_id IS NULL`: đã gặp gốc.
- Cha không tồn tại: phép `JOIN` không sinh thêm hàng, đây là kết thúc kiểu orphan.
- Đã gặp lại nút cũ: `cycle_found` chuyển thành `TRUE`, không đệ quy tiếp.

Vì fixture có số nút hữu hạn và một cha mỗi nút, truy vấn dừng trên các trường hợp mẫu khi theo dõi path đúng.

### 9.2. “Đi tới một vòng” khác “là nút nằm trong vòng”

Kết quả có `start_id = 13`, nhưng 13 **không phải thành viên** của vòng ba nút. Nó chỉ có đường đi tới 10, rồi từ 10 tiếp tục lặp.

Do đó:

- Truy vấn trên liệt kê **mọi nút mà parent chain chạm một vòng**.
- Nó **không trực tiếp là tập ID của các nút nằm trong chu trình**.
- Nếu muốn liệt kê **thành viên thực sự của từng chu trình**, phải xác định đoạn path bắt đầu tại lần xuất hiện đầu tiên của nút bị lặp rồi loại phần dẫn vào, hoặc dùng thuật toán phân rã thành phần mạnh/liên thông theo thiết kế thích hợp.

Trong fixture này, các nút **thực sự nằm trong vòng** là **10, 11, 12 và 20**, còn **13** chỉ dẫn vào vòng. Việc phân biệt giúp báo lỗi và sửa dữ liệu đúng: cắt một cạnh trong vòng có thể giải quyết một thành phần, nhưng sửa parent của 13 không tự chữa được chu trình 10–11–12.

### 9.3. Tìm vòng tự trỏ trước bằng kiểm tra đơn giản

```sql
SELECT scenario, node_id, parent_id
FROM demo_tree_nodes
WHERE parent_id = node_id
ORDER BY scenario, node_id;
```

Kết quả có `cycle / 20 / 20`. Đây là kiểm tra nhanh một **chu trình độ dài 1**. Nó **không phát hiện vòng nhiều nút** như 10–11–12; cần kiểm tra đệ quy hoặc cấu trúc ràng buộc/thuật toán khác.

## 10. PostgreSQL 14+: dùng cú pháp CYCLE thay đường đi tự viết

PostgreSQL từ **14** hỗ trợ mệnh đề `CYCLE` cho truy vấn đệ quy. DBMS tự duy trì trạng thái phát hiện lặp và cột đường đi theo danh sách cột nhận dạng mà ta chọn.

Ví dụ đi lên cha từ mọi nút của tình huống `cycle`:

```sql
-- PostgreSQL 14+.
WITH RECURSIVE ascend(start_id, node_id, parent_id) AS (
    SELECT
        node_id AS start_id,
        node_id,
        parent_id
    FROM demo_tree_nodes
    WHERE scenario = 'cycle'

    UNION ALL

    SELECT
        w.start_id,
        p.node_id,
        p.parent_id
    FROM ascend AS w
    JOIN demo_tree_nodes AS p
      ON p.scenario = 'cycle'
     AND p.node_id = w.parent_id
)
CYCLE node_id SET is_cycle USING cycle_path
SELECT DISTINCT start_id
FROM ascend
WHERE is_cycle
ORDER BY start_id;
```

Kết quả là các `start_id` **10, 11, 12, 13, 20**. `CYCLE node_id` hướng dẫn DBMS kiểm tra **sự lặp lại của `node_id` trên đường đệ quy**. `is_cycle` là cột đánh dấu chu trình và `cycle_path` là cột đường đi do cơ chế `CYCLE` tạo ra.

### 10.1. CYCLE có giải quyết mọi vấn đề dữ liệu không?

Không. Mệnh đề này giúp **phát hiện và chặn mở rộng vòng trên những nhánh được duyệt**, nhưng không tự:

- Xác định hợp đồng có cho phép cây rỗng hay nhiều gốc.
- Phát hiện cha không tồn tại nếu không có truy vấn riêng.
- Biến một đồ thị nhiều-cha thành cây.
- Bảo đảm mọi nút được đi qua nếu anchor chỉ chọn một root.
- Sửa dữ liệu hỏng hay thêm ràng buộc chống vòng cho các lệnh ghi sau này.

Nếu dùng `CYCLE` trên truy vấn chỉ bắt đầu từ gốc trong mô hình một cha, các thành phần có vòng không kết nối tới gốc vẫn có thể **không được thăm**. Muốn kiểm tra toàn cục, phải chọn anchor/chiều duyệt bao phủ các thành phần liên quan, như cách đi lên từ **mọi nút**.

### 10.2. Chọn đúng danh tính khi có nhiều phạm vi

Với bảng nhiều tenant, chu trình cần được xác định trên **khóa nút đầy đủ**. Nếu ID chỉ duy nhất trong từng `tenant_id`, cách JOIN và tiêu chí `CYCLE` phải nhất quán với phạm vi đó. Trong ví dụ CYCLE truy vấn đã giới hạn cố định `scenario = 'cycle'`; ở truy vấn nhiều scenario cùng lúc, cần mang cả `scenario` vào CTE và xem xét kiểm tra tập khóa phù hợp để tránh đánh dấu nhầm ID trùng giữa các phạm vi.

## 11. Một báo cáo chẩn đoán tổng hợp cho toàn bộ fixture

Ta cần một truy vấn hiển thị **tình huống rỗng** cùng các tình huống có nút. Vì `empty` không có hàng trong `demo_tree_nodes`, tạo một danh sách tên tình huống rồi tính chỉ số cho từng tên.

Đầu tiên dùng `WITH RECURSIVE` duyệt từ **mọi gốc của mọi scenario**; sau đó đếm:

```sql
WITH RECURSIVE reachable AS (
    SELECT
        n.scenario,
        n.node_id,
        ARRAY[n.node_id]::INTEGER[] AS path
    FROM demo_tree_nodes AS n
    WHERE n.parent_id IS NULL

    UNION ALL

    SELECT
        c.scenario,
        c.node_id,
        r.path || c.node_id
    FROM reachable AS r
    JOIN demo_tree_nodes AS c
      ON c.scenario = r.scenario
     AND c.parent_id = r.node_id
    WHERE NOT (c.node_id = ANY(r.path))
),
scenarios(scenario) AS (
    VALUES
        ('empty'),
        ('normal'),
        ('multiple_roots'),
        ('orphan'),
        ('cycle')
)
SELECT
    s.scenario,

    (SELECT COUNT(*)
     FROM demo_tree_nodes AS n
     WHERE n.scenario = s.scenario) AS node_count,

    (SELECT COUNT(*)
     FROM demo_tree_nodes AS n
     WHERE n.scenario = s.scenario
       AND n.parent_id IS NULL) AS root_count,

    (SELECT COUNT(*)
     FROM demo_tree_nodes AS n
     WHERE n.scenario = s.scenario
       AND n.parent_id IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM demo_tree_nodes AS p
           WHERE p.scenario = n.scenario
             AND p.node_id = n.parent_id
       )) AS direct_orphan_count,

    (SELECT COUNT(*)
     FROM demo_tree_nodes AS n
     WHERE n.scenario = s.scenario
       AND NOT EXISTS (
           SELECT 1
           FROM reachable AS r
           WHERE r.scenario = n.scenario
             AND r.node_id = n.node_id
       )) AS unreachable_count
FROM scenarios AS s
ORDER BY s.scenario;
```

Kết quả dự kiến:

| scenario | node_count | root_count | direct_orphan_count | unreachable_count |
|---|---:|---:|---:|---:|
| cycle | 7 | 1 | 0 | 5 |
| empty | 0 | 0 | 0 | 0 |
| multiple_roots | 4 | 2 | 0 | 0 |
| normal | 4 | 1 | 0 | 0 |
| orphan | 5 | 1 | 2 | 3 |

Báo cáo này phục vụ **phát hiện hình thái** và xác định tập bị bỏ sót. Nó **chưa chứng minh mọi nút không tới được đều nằm trong vòng**; phải kết hợp với truy vấn phát hiện cycle từ phần 9 hoặc 10.

### 11.1. Biến các chỉ số thành kết quả kiểm thử

Một chính sách **forest được phép rỗng** có thể chấp nhận:

- `empty`: 0 nút, 0 gốc.
- `normal`: 4 nút, 1 gốc, toàn bộ tới được.
- `multiple_roots`: 4 nút, 2 gốc, toàn bộ tới được.
- `orphan`: **không hợp lệ** vì có cha thiếu và nút không tới được.
- `cycle`: **không hợp lệ** vì có vòng và nút không tới được.

Một chính sách **cây không rỗng và chỉ có một gốc** sẽ còn từ chối cả `empty` và `multiple_roots`. Vì vậy, “PASS/FAIL” không nên cố định chỉ dựa trên một con số khi chưa ghi rõ quy tắc nghiệp vụ.

### 11.2. Kiểm tra đầy đủ nút tới được

Trong mô hình một cha, nếu tất cả nút đều tới được từ anchor là mọi gốc, ta có:

```text
node_count = reachable_unique_node_count
```

Nếu có orphan hoặc thành phần vòng tách khỏi gốc, số nút tới được có thể nhỏ hơn tổng số. Với một mô hình đồ thị nhiều đường đi tới cùng nút, cần đếm **DISTINCT node identity**, không đếm mọi hàng đường đi, vì một nút có thể xuất hiện qua nhiều đường hợp lệ.

Không thể sử dụng một phép so sánh tổng số đơn lẻ để phân biệt orphan với vòng: cả hai đều có thể làm số nút tới được nhỏ đi.

## 12. Kiểm thử không chỉ nhìn “query có chạy thành công”

Một bộ kiểm thử tốt có các **assertion** cụ thể:

| Ca kiểm thử | Điều cần khẳng định |
|---|---|
| Cây rỗng | Truy vấn đệ quy trả 0 nút; bộ đếm trả 0; API diễn đạt rỗng đúng hợp đồng |
| Một cây hợp lệ | Mọi nút đi tới được, một gốc, không orphan, không vòng; độ sâu đúng |
| Nhiều gốc | Anchor không cắt mất gốc; đủ mọi nhánh; xác định hợp đồng cho phép hay cấm forest |
| Orphan trực tiếp | Bắt đúng hàng có cha thiếu, đúng ID cha thiếu; không nhầm hậu duệ thành orphan trực tiếp |
| Hậu duệ orphan | Phát hiện không tới được dù cha trực tiếp của nó có tồn tại |
| Chu trình ba nút | Truy vấn chẩn đoán dừng và nêu được đường đi lặp |
| Tự trỏ | Phát hiện vòng dài 1 ngay cả khi chỉ có một hàng liên quan |
| Nút dẫn vào vòng | Báo “parent chain dẫn đến vòng”, không tự coi đó là thành viên của vòng |
| Nhiều cây/tenant chung bảng | JOIN không ghép nhầm nút cùng ID ở các phạm vi khác nhau |
| Chuỗi phân cấp dài | Không vượt giới hạn đệ quy tài nguyên, có cơ chế xử lý chiều sâu bất thường |

### 12.1. Kết quả trả về cần có thứ tự xác định khi so sánh

Nếu muốn kiểm thử các ID đã duyệt:

```sql
WITH RECURSIVE walk AS (
    SELECT scenario, node_id, parent_id
    FROM demo_tree_nodes
    WHERE scenario = 'multiple_roots'
      AND parent_id IS NULL

    UNION ALL

    SELECT c.scenario, c.node_id, c.parent_id
    FROM walk AS w
    JOIN demo_tree_nodes AS c
      ON c.scenario = w.scenario
     AND c.parent_id = w.node_id
)
SELECT node_id
FROM walk
ORDER BY node_id;
-- 1, 2, 10, 11
```

**`ORDER BY` ở SELECT ngoài cùng** đảm bảo thứ tự ID khi đem kết quả đi so sánh. Không dựa vào thứ tự mà vòng lặp đệ quy tình cờ phát ra. Ngoài ra, với dữ liệu có thể có cycle, phiên bản sản xuất của truy vấn nên có kiểm tra path hoặc cơ chế `CYCLE`; ví dụ ngắn này chỉ dùng trên fixture `multiple_roots` không có vòng.

### 12.2. Một truy vấn kiểm thử chỉ ra lỗi dữ liệu, không tự sửa lỗi

Ví dụ SQL tìm orphan:

```sql
SELECT child.node_id
FROM demo_tree_nodes AS child
WHERE child.scenario = 'orphan'
  AND child.parent_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM demo_tree_nodes AS parent
      WHERE parent.scenario = child.scenario
        AND parent.node_id = child.parent_id
  );
```

Nó chỉ liệt kê lỗi. Không tự động:

- Đặt `parent_id = NULL` cho tất cả orphan.
- Xóa toàn bộ nút và hậu duệ.
- Nối orphan vào một root bất kỳ.
- Chọn bừa một cạnh của chu trình để cắt.

Mỗi phương án thay đổi **cấu trúc phân cấp và dữ liệu nghiệp vụ**. Quy trình sửa phải có quy tắc đã được phê duyệt, bản sao/ghi nhận lịch sử khi cần, và kiểm tra lại tính toàn vẹn sau thay đổi.

## 13. Giới hạn đệ quy là cơ chế an toàn, không phải máy dò vòng

Khi một truy vấn đệ quy không có điều kiện dừng đúng, nó có thể tạo kết quả vô tận về mặt logic. Các DBMS thường có cơ chế giới hạn vòng đệ quy, tài nguyên hoặc yêu cầu người viết đặt điều kiện dừng.

### 13.1. Giới hạn độ sâu thủ công

Có thể đặt một ngưỡng trong recursive member:

```sql
-- PostgreSQL: giới hạn 20 cạnh đi lên mỗi điểm xuất phát.
WITH RECURSIVE up_walk AS (
    SELECT
        node_id AS start_id,
        node_id AS current_id,
        parent_id,
        0 AS depth
    FROM demo_tree_nodes
    WHERE scenario = 'cycle'

    UNION ALL

    SELECT
        w.start_id,
        p.node_id,
        p.parent_id,
        w.depth + 1
    FROM up_walk AS w
    JOIN demo_tree_nodes AS p
      ON p.scenario = 'cycle'
     AND p.node_id = w.parent_id
    WHERE w.depth < 20
)
SELECT start_id, MAX(depth) AS greatest_depth_seen
FROM up_walk
GROUP BY start_id
ORDER BY start_id;
```

Giới hạn `depth < 20` sẽ làm truy vấn dừng theo số bước, **nhưng không cho biết một nhánh dừng vì đã tới root, vì mất cha hay vì bị cắt do đạt ngưỡng**. Trong vòng 10–11–12, các bước cứ lặp lại đến khi chạm ngưỡng.

**Không xem “query không treo” là bằng chứng dữ liệu không có vòng.** Nếu chỉ áp giới hạn độ sâu rồi lấy kết quả, bạn có thể vô tình trả cây thiếu nút mà không báo trạng thái bị cắt.

### 13.2. Theo dõi trạng thái kết thúc

Thiết kế chẩn đoán tốt nên phân biệt các trạng thái:

- **REACHED_ROOT**: gặp `parent_id IS NULL`.
- **MISSING_PARENT**: `parent_id` khác `NULL` nhưng không có hàng cha.
- **CYCLE**: chuẩn bị bước tới nút đã xuất hiện trong đường đi.
- **DEPTH_LIMIT**: đạt ngưỡng bảo vệ trước khi xác định kết thúc thực.
- **ERROR**: câu SQL/DBMS có lỗi thực thi hoặc bị giới hạn tài nguyên.

Một nhánh bị `DEPTH_LIMIT` không nên tự động được báo là `CYCLE`. Cây hợp lệ nhưng rất sâu cũng có thể đạt ngưỡng. Việc tách trạng thái giúp vận hành biết cần tăng giới hạn, điều tra dữ liệu hay sửa cấu trúc.

### 13.3. UNION không thay được kiểm tra path

Nếu recursive CTE chỉ có cột `node_id` và dùng `UNION` khử trùng, một số truy vấn vòng đơn giản có thể dừng khi không phát sinh ID mới. Nhưng nếu thêm `depth` hoặc `path`, các hàng đi lại một nút sẽ có giá trị khác nhau và `UNION` có thể tiếp tục sinh hàng.

Vì vậy nên dùng giải pháp nhận diện **nút đã có trên đường đi** hoặc tính năng **`CYCLE`** mà DBMS hỗ trợ; `UNION` chỉ là toán tử tập hợp, không tự bảo đảm giải quyết mọi dạng đệ quy vòng.

## 14. Ràng buộc dữ liệu: phòng ngừa khác phát hiện

Fixture được tạo không có FK để tái hiện dữ liệu lỗi. Trong bảng thực tế, nên cân nhắc ràng buộc cơ sở dữ liệu để giảm nguy cơ phát sinh lỗi.

### 14.1. FK ghép phòng ngừa cha không tồn tại

Ví dụ PostgreSQL với nhiều cây có thể dùng:

```sql
CREATE TABLE tree_nodes (
    tree_id BIGINT NOT NULL,
    node_id BIGINT NOT NULL,
    parent_id BIGINT,
    title TEXT NOT NULL,

    PRIMARY KEY (tree_id, node_id),

    CONSTRAINT fk_parent_same_tree
        FOREIGN KEY (tree_id, parent_id)
        REFERENCES tree_nodes(tree_id, node_id),

    CONSTRAINT ck_not_own_parent
        CHECK (parent_id IS NULL OR parent_id <> node_id)
);
```

Ở đây:

- PK `(tree_id, node_id)` bảo đảm ID duy nhất **trong từng cây**.
- FK `(tree_id, parent_id)` yêu cầu nút cha thuộc **cùng tree_id** khi `parent_id` có giá trị.
- Một gốc có `parent_id NULL` được phép vì ràng buộc FK kiểu mặc định cho cặp chứa `NULL` không bắt buộc tìm hàng cha.
- `CHECK` ngăn **vòng tự trỏ**, ví dụ `parent_id = node_id`.

Đây là thiết kế phòng ngừa tốt hơn so với chỉ định kỳ quét bảng để tìm orphan.

### 14.2. FK và CHECK không ngăn mọi chu trình

Một vòng nhiều nút như:

```text
10 → 11 → 12 → 10
```

có thể có tất cả cha tồn tại. FK được thỏa; từng hàng cũng có `parent_id <> node_id` nên `CHECK` không phát hiện.

Ngay cả khi có ràng buộc FK, một vòng có thể phát sinh qua các thao tác `UPDATE` hợp lệ khi mọi nút đã tồn tại. Ví dụ trong một bảng hiện có hai nút 10 (gốc) và 11 (con của 10), sửa parent của 10 thành 11 sẽ tạo vòng 10–11 mà cả hai FK đều có thể tiếp tục hợp lệ.

Ngăn chu trình nhiều nút cần **kiểm tra quan hệ tổ tiên** ở lúc thay đổi parent, bằng thủ tục/trigger hay một cơ chế thiết kế phù hợp. Khi có nhiều giao dịch sửa cây đồng thời, cũng phải xét **khóa, mức cô lập và an toàn giao dịch**: chỉ kiểm tra ở ứng dụng rồi cập nhật không đồng bộ có thể để hai giao dịch cùng tạo vòng.

### 14.3. Ràng buộc nhiều nhất một gốc

Nếu nghiệp vụ yêu cầu **không quá một gốc mỗi tree_id**, PostgreSQL có thể dùng chỉ mục duy nhất có điều kiện:

```sql
CREATE UNIQUE INDEX uq_one_root_per_tree
ON tree_nodes (tree_id)
WHERE parent_id IS NULL;
```

Nó chặn **hai hàng cùng tree_id đều có parent_id NULL**. Nhưng nó chỉ bảo đảm **tối đa một gốc**, **không bảo đảm phải có ít nhất một gốc**. Một cây hoàn toàn có vòng mà không có root vẫn có thể vượt qua điều kiện này.

Muốn bảo đảm **chính xác một gốc** đối với mỗi cây bắt buộc không rỗng, cần bổ sung quy tắc về tồn tại và kết nối (có thể qua bảng đại diện cây, giao dịch/trigger hoặc kiểm tra toàn bộ thành phần). Nếu nghiệp vụ cho phép forest, không áp chỉ mục một gốc theo `tree_id` cho phạm vi ấy.

### 14.4. Không phải mọi ràng buộc đều thích hợp với CHECK

Một `CHECK` thông thường xét điều kiện **trên hàng đang thay đổi**; nó không phải cơ chế phù hợp để chạy truy vấn đệ quy nhiều hàng rồi khẳng định “không có ancestor trùng”. Các ràng buộc phụ thuộc nhiều hàng thường cần cơ chế dành riêng, trigger hoặc thiết kế lại mô hình. Ngoài ra, khi xóa nút cha cần xác định chính sách `ON DELETE` phù hợp: `RESTRICT`/`NO ACTION`, `CASCADE` hoặc `SET NULL` có hệ quả khác nhau cho cấu trúc gốc và orphan.

## 15. Khi dùng đồ thị nhiều-cha: cần đổi giả định kiểm thử

Không phải hệ thống phân cấp nào cũng có một cột `parent_id` duy nhất. Ví dụ bảng cạnh:

```sql
-- Minh họa mô hình quan hệ nhiều cạnh.
CREATE TABLE graph_edges (
    parent_id INTEGER NOT NULL,
    child_id INTEGER NOT NULL,
    PRIMARY KEY (parent_id, child_id)
);
```

Một nút có thể có nhiều cha, hoặc có nhiều đường từ các gốc khác nhau. Khi đó:

- Một nút có thể đi tới được qua **nhiều đường** và xuất hiện nhiều lần trong CTE.
- Vòng có thể **nằm trong nhánh đi được từ gốc**, không nhất thiết tách khỏi gốc như mô hình một-parent.
- `COUNT(*)` trên toàn bộ đường đi không bằng số nút duy nhất.
- Cần path guard **theo từng đường** nếu muốn liệt kê đường đi mà không mở rộng cycle.
- Nếu chỉ muốn tập nút reachable, có thể dùng `DISTINCT` theo khóa nút hoặc thuật toán visited-set phù hợp.

Ví dụ một cạnh 1→2, 1→3, 2→4, 3→4 tạo hai đường khác nhau tới nút 4 dù không có vòng. Nếu báo cáo “số nút” mà đếm các hàng đường đi, nút 4 có thể bị đếm hai lần. Đây là **sự khác biệt giữa cây và đồ thị có nhiều đường**, không phải lỗi của `WITH RECURSIVE`.

Với adjacency list một-cha trong fixture chính, mỗi nút thuộc một đường cha duy nhất nếu cấu trúc hợp lệ, nên không gặp hiện tượng này khi duyệt từ tất cả root.

## 16. Khác biệt giữa các hệ quản trị

Cú pháp chung của truy vấn đệ quy khá quen thuộc nhưng **khả năng phát hiện vòng, kiểu mảng path và giới hạn độ sâu không portable hoàn toàn**.

| Hệ quản trị | Cách viết/cơ chế | Điều cần nhớ khi kiểm thử vòng |
|---|---|---|
| **PostgreSQL** | `WITH RECURSIVE`; mảng `ARRAY[...]`; `CYCLE` từ 14 | Dùng path hoặc `CYCLE`; không dựa vào root-only traversal để kiểm chứng toàn bảng |
| **SQL Server** | Recursive CTE qua `WITH name AS (...)`, không dùng từ khóa `RECURSIVE` | `OPTION (MAXRECURSION n)` là giới hạn bảo vệ, không thay kiểm tra chu trình |
| **MySQL 8.0+** | `WITH RECURSIVE`; giới hạn theo `cte_max_recursion_depth` | Cần điều kiện dừng/path; giới hạn bị chạm có thể báo lỗi thay vì chứng minh dữ liệu có vòng |
| **MariaDB** | `WITH RECURSIVE`; cơ chế/giới hạn như `max_recursive_iterations` tùy phiên bản | Không mặc nhiên giống MySQL; kiểm tra phiên bản |
| **SQLite** | `WITH RECURSIVE`; có thể dùng chuỗi/JSON để biểu diễn đường đi | Không có kiểu mảng `INTEGER[]` như PostgreSQL; `UNION` không tự giải quyết mọi vòng |
| **Oracle** | Recursive subquery factoring, `CYCLE` trong các phiên bản hỗ trợ | Cú pháp khác PostgreSQL; có cơ chế phát hiện cycle riêng, xem tài liệu đúng bản |

### 16.1. SQL Server: MAXRECURSION là “cầu chì”

Ví dụ T-SQL:

```sql
-- SQL Server, giả sử dbo.nodes(node_id, parent_id) tồn tại.
;WITH tree_walk AS (
    SELECT node_id, parent_id, 0 AS depth
    FROM dbo.nodes
    WHERE parent_id IS NULL

    UNION ALL

    SELECT c.node_id, c.parent_id, w.depth + 1
    FROM dbo.nodes AS c
    JOIN tree_walk AS w ON c.parent_id = w.node_id
)
SELECT node_id, depth
FROM tree_walk
OPTION (MAXRECURSION 100);
```

Giới hạn giúp truy vấn không chạy đệ quy vô hạn mà không có kiểm soát. Nhưng **cây hợp lệ sâu hơn 100 cấp cũng có thể chạm giới hạn**, và **một vòng ở thành phần không được anchor chạm tới vẫn bị bỏ sót**. Khi cần phát hiện vòng thực sự, phải thêm kiểm tra path/visited hoặc thuật toán phát hiện cycle trong cú pháp SQL Server phù hợp.

### 16.2. MySQL: giới hạn số vòng không đồng nghĩa phát hiện lỗi cấu trúc

MySQL 8.0+ có biến cấu hình liên quan tới giới hạn độ sâu đệ quy, thường là `cte_max_recursion_depth`. Có thể dùng `WITH RECURSIVE`, nhưng PostgreSQL `ARRAY[n.node_id]::INTEGER[]` không phải cú pháp mảng của MySQL.

Một cách chuyển ý tưởng là biểu diễn path bằng chuỗi có dấu phân định chặt chẽ hoặc cấu trúc JSON để kiểm tra ID đã xuất hiện. Nếu dùng chuỗi, phải tránh so khớp nhầm ID **1** với **11**, giới hạn độ dài chuỗi và lỗi cắt chuỗi. Nếu dùng JSON, phải kiểm tra chính xác hàm và kiểu dữ liệu ở phiên bản đang triển khai.

### 16.3. SQLite: có recursive CTE nhưng không có mảng PostgreSQL

SQLite hỗ trợ `WITH RECURSIVE` nhưng không cung cấp kiểu `INTEGER[]` theo cú pháp PostgreSQL. Với cây nhỏ, có thể theo dõi path bằng chuỗi dạng `'|1|2|4|'` và kiểm tra ID có đủ dấu phân cách, hoặc dùng hàm JSON sẵn có. Cả hai đều có điểm cần đánh giá về chuyển kiểu, giới hạn kích thước và hiệu năng.

Không dùng kiểm tra chuỗi kiểu `path LIKE '%1%'` vì nó có thể khớp cả nút 11; dữ liệu lớn còn có thể gây chuỗi path dài, nên cần bộ giới hạn và cấu trúc phù hợp.

### 16.4. PostgreSQL và Oracle có CYCLE nhưng cần đúng phạm vi

`CYCLE` giúp xử lý lặp trong chính nhánh đệ quy được thực hiện, chứ không tự quét các thành phần không được anchor chọn. Với bảng một-parent, muốn phát hiện vòng toàn cục hãy bắt đầu từ **mọi nút** theo chiều lên cha hoặc dùng thuật toán khác bao phủ toàn bộ dữ liệu.

Oracle có cú pháp recursive factoring và `CYCLE` riêng; không sao chép nguyên cú pháp `CYCLE node_id SET is_cycle USING cycle_path` của PostgreSQL sang Oracle mà không tra tài liệu DBMS đích.

## 17. Hiệu năng và an toàn khi kiểm thử dữ liệu lớn

Phát hiện vòng từ **mọi nút** có thể tốn công việc đáng kể khi bảng rất lớn, đặc biệt nếu mỗi nút nằm trên chuỗi tổ tiên dài. Bộ dữ liệu học chỉ vài chục hàng; hệ thống thật có thể có hàng triệu nút.

### 17.1. Chỉ mục hữu ích

Với mô hình một cha, những chỉ mục thường đáng cân nhắc:

```sql
-- Trong bảng sản xuất tree_nodes đã có PK(tree_id, node_id).
CREATE INDEX idx_tree_nodes_parent
ON tree_nodes (tree_id, parent_id);
```

- `(tree_id, node_id)` hỗ trợ tra cha theo định danh.
- `(tree_id, parent_id)` hỗ trợ tìm các con trực tiếp của một nút.
- Truy vấn phát hiện orphan dùng điều kiện tra cha theo khóa duy nhất.
- Truy vấn đệ quy theo chiều cha → con thường hưởng lợi từ khả năng tìm nhanh children.

Chỉ mục không chứng minh dữ liệu đúng; nó chỉ giúp giảm chi phí truy xuất trong những kế hoạch phù hợp.

### 17.2. Độ dài path và chi phí bộ nhớ

Mảng `path` của mỗi nhánh tăng theo độ sâu. Nếu bạn bắt đầu truy vấn “đi lên cha” **từ mọi nút**, tổng số phần tử path đã xử lý có thể lớn hơn rất nhiều số nút. Trong cây chuỗi dài, việc lặp lại đường đi cho từng nút có thể tốn bộ nhớ và CPU.

Các phương án trên dữ liệu lớn:

- Kiểm tra FK và lỗi đơn giản (self-cycle) trước.
- Phân vùng kiểm thử theo `tree_id`/tenant hoặc batch.
- Với việc kiểm tra định kỳ, dùng chiến lược visited-state/đánh dấu trạng thái đã phân loại để tránh duyệt lặp quá nhiều khi môi trường cho phép.
- Dùng cơ chế `CYCLE`/giới hạn đệ quy đúng DBMS để tránh vô hạn.
- Đặt giới hạn tài nguyên, timeout và cơ chế báo lỗi khi vượt ngân sách.
- Không chạy thử truy vấn quét toàn bộ bảng quá lớn trên môi trường sản xuất mà chưa đánh giá chi phí.

### 17.3. Tập dữ liệu thay đổi giữa lúc kiểm tra và lúc sửa

Một kết quả “không có vòng” chỉ mô tả **trạng thái dữ liệu mà truy vấn đã nhìn thấy**. Nếu các giao dịch khác vẫn có thể sửa `parent_id` sau đó, cây có thể thay đổi trước khi bạn sửa/ghi mới.

Với thao tác reparent, quy trình kiểm tra “nút cha mới không phải hậu duệ của nút hiện tại” cần chạy theo một chiến lược giao dịch phù hợp, có khóa hoặc cô lập chống những thay đổi đồng thời liên quan. Không chỉ dựa vào một báo cáo kiểm tra trước đó rồi tin rằng dữ liệu luôn giữ nguyên.

## 18. Lựa chọn tiêu chí PASS/FAIL theo hợp đồng hệ thống

Có thể tách các điều kiện hợp lệ thành một ma trận:

| Điều kiện | Tree bắt buộc một gốc | Forest cho phép rỗng |
|---|---|---|
| Không có nút | FAIL nếu luôn cần một cây tồn tại | PASS |
| Có đúng một gốc khi không rỗng | Bắt buộc | Không bắt buộc |
| Có nhiều gốc | FAIL | PASS nếu từng thành phần hợp lệ |
| Có orphan trực tiếp | FAIL | FAIL |
| Có nút không đi tới từ bất kỳ gốc nào | FAIL | FAIL |
| Có vòng | FAIL | FAIL |
| Có nút rất sâu nhưng hợp lệ | Tùy giới hạn nghiệp vụ | Tùy giới hạn nghiệp vụ |
| Có nhiều tenant với ID trùng | PASS nếu khóa theo tenant đúng | PASS nếu khóa theo tenant đúng |

Một chương trình kiểm thử có thể kiểm tra theo thứ tự:

1. Đếm số nút và số gốc.
2. So với chính sách rỗng/một gốc/nhiều gốc.
3. Kiểm tra orphan trực tiếp.
4. Duyệt reachable từ mọi gốc và kiểm tra phần còn lại.
5. Kiểm tra cycle toàn cục.
6. Phân loại lỗi theo ID và đường tham chiếu.
7. Kiểm tra chiều sâu tối đa và các giới hạn nghiệp vụ.
8. Chỉ báo PASS khi mọi ràng buộc **áp dụng cho mô hình** đều đúng.

Điều quan trọng là **đừng chỉ dựa trên một điều kiện** như “có ít nhất một root” để kết luận toàn bộ cấu trúc hợp lệ. Fixture `cycle` có một root và không có orphan trực tiếp nhưng vẫn hỏng.

## 19. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách tránh |
|---|---|---|
| Chỉ kiểm tra một cây hợp lệ đơn giản | Bỏ sót trường hợp rỗng, orphan, forest, vòng | Có fixture riêng cho từng lớp dữ liệu |
| Dùng `COUNT(*)` sau `LEFT JOIN` để đếm nút thật | Hàng bên trái không khớp vẫn được đếm | `COUNT(child.node_id)` hoặc đếm trực tiếp từ bảng nút |
| Dùng `COUNT(parent_id)` để đếm gốc | `COUNT` bỏ `NULL`, root bị đếm thành 0 | `COUNT(*) WHERE parent_id IS NULL` |
| Anchor chỉ lấy `LIMIT 1` gốc | Bỏ toàn bộ các cây khác trong forest | Anchor mọi root hoặc báo vi phạm hợp đồng một gốc |
| Chỉ tìm orphan trực tiếp | Không thấy hậu duệ orphan hoặc thành phần vòng | So thêm reachable với toàn bộ nút |
| Chỉ duyệt từ root để “phát hiện mọi vòng” | Vòng trong cây một-parent có thể không kết nối tới root | Kiểm tra đi lên từ mọi nút hoặc dùng thuật toán toàn cục |
| Đếm start_id có đường vào vòng là số nút thuộc vòng | Nhầm nút dẫn vào vòng với thành viên của vòng | Tách đoạn lặp trong path để xác định thành viên |
| Dùng `UNION` thay cho path guard | Khi có `depth`/`path`, vòng vẫn tạo hàng mới | Kiểm tra visited node hoặc dùng `CYCLE` |
| Dùng giới hạn depth và coi bị cắt là cycle | Cây rất sâu cũng bị cắt | Phân biệt `DEPTH_LIMIT` và `CYCLE` |
| JOIN chỉ theo node_id trong bảng đa tenant | Dẫn sang cây/tenant khác có cùng ID | Dùng đầy đủ khóa phạm vi |
| Chỉ có FK rồi cho rằng không thể có vòng | FK không phát hiện chu trình nhiều nút | Kiểm tra tổ tiên khi reparent; ràng buộc phù hợp |
| Dùng `CHECK(parent_id <> node_id)` và cho rằng đủ | Chỉ ngăn vòng tự trỏ | Kiểm tra vòng nhiều nút |
| Dùng `ORDER BY` nội bộ rồi tin thứ tự kết quả | SQL không bảo đảm thứ tự đầu ra nếu thiếu sort cuối | `ORDER BY` ở SELECT cuối |
| Tự sửa orphan bằng cách đặt parent NULL | Biến nút thành gốc mới, thay đổi nghiệp vụ | Có quy trình khôi phục dữ liệu được xác nhận |
| Không thử nút dẫn vào vòng | Có thể gán nhầm mọi nguồn phát hiện là thành viên vòng | Báo cả path và loại tình huống |
| Không kiểm tra đồng thời khi sửa cha | Hai thay đổi hợp lệ riêng có thể tạo vòng khi ghép | Dùng giao dịch và khóa/cô lập đúng |

## 20. Bài tập tự luyện kèm đáp án

### Bài 1. Cây rỗng

**Câu hỏi:** Trong `demo_tree_nodes` không có hàng `scenario = 'empty'`. Truy vấn `WITH RECURSIVE` bắt đầu bằng `parent_id IS NULL` trên scenario đó trả bao nhiêu hàng? Còn `SELECT COUNT(*) FROM demo_tree_nodes WHERE scenario = 'empty'` trả gì?

**Đáp án:** Truy vấn đệ quy trả **0 hàng**; truy vấn `COUNT(*)` trả **một hàng có giá trị 0**. Đó là hai hình dạng kết quả khác nhau. Nếu cây rỗng được phép, cả hai đều phù hợp.

### Bài 2. Phát hiện nhiều gốc

**Yêu cầu:** liệt kê gốc của `multiple_roots`.

**Đáp án:**

```sql
SELECT node_id
FROM demo_tree_nodes
WHERE scenario = 'multiple_roots'
  AND parent_id IS NULL
ORDER BY node_id;
-- 1, 10
```

Nếu chỉ lấy root 1 thì sẽ bỏ cả nhánh 10–11. Nếu chính sách chỉ cho một gốc, phải báo tình trạng có hai root, không tự chọn một root.

### Bài 3. Orphan trực tiếp

**Yêu cầu:** viết truy vấn tìm nút tham chiếu cha không tồn tại trong `orphan`.

**Đáp án:**

```sql
SELECT n.node_id, n.parent_id
FROM demo_tree_nodes AS n
WHERE n.scenario = 'orphan'
  AND n.parent_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM demo_tree_nodes AS p
      WHERE p.scenario = n.scenario
        AND p.node_id = n.parent_id
  )
ORDER BY n.node_id;
-- 20 → 99; 30 → 100.
```

Nút 21 không bị liệt kê vì có cha trực tiếp là 20.

### Bài 4. Tại sao unreachable nhiều hơn orphan?

**Câu hỏi:** Vì sao `orphan` có 2 nút mồ côi trực tiếp nhưng 3 nút không tới được từ root?

**Đáp án:** Nút 20 trỏ cha không tồn tại; nút 21 có cha 20 (tồn tại) nhưng cả thành phần 20→21 không nối về root; nút 30 trỏ cha 100 không tồn tại. Do đó 20,21,30 đều không reachable, trong khi chỉ 20 và 30 mồ côi trực tiếp.

### Bài 5. Tự trỏ và vòng nhiều nút

**Câu hỏi:** `WHERE node_id = parent_id` phát hiện được những vòng nào trong `cycle`?

**Đáp án:** chỉ phát hiện **nút 20** tự trỏ. Nó không phát hiện vòng **10→11→12→10**. Cần truy vết tổ tiên hoặc `CYCLE` cho các vòng dài hơn một cạnh.

### Bài 6. Truy vấn root-only không thấy vòng

**Câu hỏi:** Tại sao duyệt từ mọi hàng `parent_id IS NULL` của `cycle` chỉ thấy ID 1,2 dù có vòng?

**Đáp án:** Trong mô hình một cha, các nút ở vòng có quan hệ cha dẫn vào chính vòng và không tạo đường nối về gốc. Chỉ root 1 và child 2 thuộc thành phần có gốc; các nút 10,11,12,13,20 thuộc thành phần không có đường về gốc. Muốn phát hiện vòng, bắt đầu kiểm tra theo chiều cha **từ mọi nút**.

### Bài 7. Điểm bắt đầu và thành viên vòng

**Câu hỏi:** Truy vấn `parent_walk` trả `start_id = 13` và đường `{13,10,11,12,10}`. Có phải 13 là một nút trong vòng không?

**Đáp án:** không. Đoạn lặp là **10→11→12→10**; nút 13 là đường dẫn vào vòng. Khi báo lỗi nên phân biệt `LEADS_TO_CYCLE` và `MEMBER_OF_CYCLE` nếu hệ thống cần xử lý khác nhau.

### Bài 8. Ràng buộc FK và chu trình

**Câu hỏi:** Một bảng có FK tự tham chiếu hợp lệ và CHECK `parent_id <> node_id`. Nó có thể chứa vòng ba nút không?

**Đáp án:** có. FK chỉ bảo đảm cha tồn tại; CHECK trên một hàng chỉ cấm tự trỏ. Các nút 10,11,12 đều có cha tồn tại và không tự trỏ, nhưng tạo một chu trình. Cần kiểm tra tổ tiên/tránh vòng khi thay đổi cấu trúc.

### Bài 9. Giới hạn đệ quy

**Câu hỏi:** Truy vấn đi lên cha bị cắt ở depth 100. Có được kết luận dữ liệu chứa vòng không?

**Đáp án:** không. Chuỗi hợp lệ dài hơn 100 cấp cũng bị cắt. Kết quả `DEPTH_LIMIT` là **chưa xác định được kết thúc thật**; phải truy vết đúng hoặc sử dụng phát hiện visited/CYCLE, đồng thời kiểm soát tài nguyên.

### Bài 10. Tổng hợp fixture

**Yêu cầu:** nêu số nút, gốc, orphan trực tiếp và nút không tới được cho `normal`, `multiple_roots`, `orphan`, `cycle` và `empty`.

**Đáp án:**

| scenario | nodes | roots | direct orphans | unreachable |
|---|---:|---:|---:|---:|
| normal | 4 | 1 | 0 | 0 |
| multiple_roots | 4 | 2 | 0 | 0 |
| orphan | 5 | 1 | 2 | 3 |
| cycle | 7 | 1 | 0 | 5 |
| empty | 0 | 0 | 0 | 0 |

Nếu hợp đồng cho phép forest rỗng, `empty` và `multiple_roots` có thể PASS; nếu hợp đồng yêu cầu một gốc và cây không rỗng, chỉ `normal` PASS trong các tình huống này.

## Kết luận

Kiểm thử truy vấn đệ quy phải xem **cả kết quả hiển thị lẫn cấu trúc nguồn**. Cây rỗng cần trả tập rỗng đúng hợp đồng; nhiều gốc cần được duyệt đủ hoặc báo lỗi theo chính sách; nút mồ côi trực tiếp cần phát hiện bằng kiểm tra cha tồn tại; các nút không tới được cần được xác định bằng cách so toàn bảng với tập duyệt từ gốc. Vòng tham chiếu cần **truy vết có path/visited-set hoặc `CYCLE`**, không chỉ dựa vào giới hạn độ sâu.

Đặc biệt, trong mô hình adjacency list **mỗi nút một cha**, những thành phần có vòng thường **không thể đi tới từ bất kỳ gốc nào**. Một root traversal kết thúc bình thường **không chứng minh dữ liệu không có vòng**. Hãy kết hợp đếm gốc, kiểm tra orphan, kiểm tra unreachable và dò cycle **từ mọi nút** khi cần bảo đảm toàn bộ dữ liệu đúng.

Ràng buộc PK/FK và CHECK giúp phòng tránh nhiều lỗi, nhưng FK không thay thế kiểm tra chu trình nhiều nút. Khi áp dụng trên hệ thống thực, cần thêm quy tắc phân quyền/phạm vi cây, kế hoạch thực thi thích hợp và an toàn giao dịch khi đổi cha. Một bộ kiểm thử có dữ liệu biên được định nghĩa rõ sẽ giúp truy vấn đệ quy không chỉ chạy được trên cây mẫu, mà còn đáng tin cậy khi dữ liệu không hoàn hảo.

