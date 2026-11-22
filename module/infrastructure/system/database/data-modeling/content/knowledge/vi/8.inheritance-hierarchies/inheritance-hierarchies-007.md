# So sánh chi phí đọc tổ tiên, đọc cây con, di chuyển và cập nhật nút

Một cây phân cấp có thể được biểu diễn dưới nhiều cấu trúc dữ liệu vật lý. Cùng một yêu cầu “hiển thị tất cả phòng ban trực thuộc”, “tìm đường từ danh mục sản phẩm lên gốc” hay “chuyển nhóm A sang trực thuộc nhóm B” có thể dẫn tới lượng đọc, lượng ghi và mức độ khóa dữ liệu rất khác nhau.

Trong module **DATABASE_DATA_MODELING**, mục tiêu của việc so sánh chi phí là chọn lược đồ phù hợp với quy tắc nghiệp vụ, kiểu truy vấn và tần suất cập nhật, đồng thời giữ được các bất biến: cha tồn tại, đúng phạm vi sở hữu, mỗi nút tối đa một cha và không có chu trình. Bài này tập trung vào chương **Kế thừa và phân cấp**, cụ thể là cây quan hệ cha–con giữa các bản ghi; đây là một bài toán khác với kế thừa loại thực thể (*supertype/subtype*).

Ta sẽ so sánh bốn mô hình quan hệ phổ biến: **adjacency list**, **materialized path**, **closure table** và **nested sets**. Sau đó mở rộng góc nhìn sang document, graph và phân tích lịch sử. Các ví dụ SQL sử dụng PostgreSQL 15+; con số độ phức tạp là mô hình ước lượng để ra quyết định, không phải cam kết thời gian chạy của mọi hệ quản trị.

## 1. Bắt đầu từ tác vụ thực tế, không bắt đầu từ cấu trúc bảng

Xét cây danh mục của một doanh nghiệp:

```text
Tất cả (1)
├── Điện tử (2)
│   ├── Điện thoại (3)
│   │   └── Android (7)
│   └── Laptop (4)
└── Thời trang (5)
    └── Giày (6)
```

Bốn thao tác cần khảo sát:

1. **Đọc tổ tiên của “Android”**: trả về “Điện thoại → Điện tử → Tất cả”, thường để dựng breadcrumb hoặc kiểm tra quyền được thừa hưởng.
2. **Đọc cây con của “Điện tử”**: trả về 2, 3, 4 và 7; thường để lọc toàn bộ sản phẩm thuộc một nhánh.
3. **Di chuyển nhánh “Điện tử” dưới “Giày”**: đổi vị trí của 2 và toàn bộ hậu duệ 3, 4, 7 mà không tạo vòng.
4. **Cập nhật nút “Điện thoại”**: đổi tên hiển thị, trạng thái hoặc thuộc tính nghiệp vụ; phân biệt thao tác này với đổi quan hệ cha–con.

Đọc tổ tiên và đọc cây con đều có thể trả về nhiều dòng. Điểm khác biệt giữa các mô hình thường nằm ở **cách tìm những dòng ấy**, số bước truy vấn và số dòng/chỉ mục phải sửa khi cấu trúc cây thay đổi.

### Ký hiệu dùng để so sánh

| Ký hiệu | Ý nghĩa |
|---|---|
| \(N\) | Tổng số nút của một cây hoặc một phạm vi tenant đang xét |
| \(h\) | Độ sâu của nút từ gốc; gần bằng số tổ tiên của nó |
| \(s\) | Số nút trong cây con bị tác động, **kể cả nút gốc cây con** |
| \(a_o\) | Số tổ tiên ngoài cây con tại vị trí cũ của nút được chuyển |
| \(a_n\) | Số tổ tiên tại vị trí mới, tính cả cha mới |
| \(b\) | Số con trung bình của một nút trong cây cân đối, khi có thể xấp xỉ |
| \(R\) / \(W\) | Số thao tác đọc / ghi trong cùng một khoảng đo |

Chẳng hạn, nhánh “Điện tử” có \(s=4\). Nút “Android” có \(h=3\) nếu gốc ở độ sâu 0. Một cây dạng dây chuyền có thể có \(h \approx N-1\); một cây cân đối có hệ số phân nhánh \(b>1\) thường có độ sâu cỡ \(\log_b N\).

Trong bảng chi phí, **\(O(\cdot)\)** mô tả xu hướng số thao tác hoặc số bản ghi cần xử lý theo mô hình thuật toán. Chi phí thực còn có I/O, kích thước hàng, bộ đệm, chỉ mục, phương án thực thi, ghi WAL, tranh chấp khóa và mức đồng thời. Các thuật toán không thể đọc ít hơn số dòng mà câu trả lời yêu cầu xuất ra: trả về \(s\) nút luôn có một chi phí tối thiểu tương ứng với \(s\) kết quả.

## 2. Bốn cách biểu diễn cùng một cây

### 2.1. Danh sách kề (adjacency list)

Mỗi nút lưu khóa của **cha trực tiếp**:

| `node_id` | `parent_id` | `name` |
|---:|---:|---|
| 1 | `NULL` | Tất cả |
| 2 | 1 | Điện tử |
| 3 | 2 | Điện thoại |
| 4 | 2 | Laptop |
| 5 | 1 | Thời trang |
| 6 | 5 | Giày |
| 7 | 3 | Android |

Ưu điểm là chỉ cần một dòng để biểu diễn một nút và một trường `parent_id` để định vị nó. Truy vấn cha trực tiếp là một phép tra cứu; tìm nhiều cấp cần **recursive CTE** hoặc đệ quy ở ứng dụng. Di chuyển nhánh chỉ sửa `parent_id` của nút gốc nhánh **về mặt biểu diễn**, nhưng vẫn phải kiểm tra không tạo chu trình.

### 2.2. Đường đi được lưu sẵn (materialized path)

Mỗi nút lưu đường đi từ gốc đến chính nó. Để tránh ảnh hưởng bởi việc đổi tên, đường đi nên xây từ **ID ổn định**, có ký hiệu phân tách rõ ràng:

| `node_id` | `path` |
|---:|---|
| 1 | `/1/` |
| 2 | `/1/2/` |
| 3 | `/1/2/3/` |
| 4 | `/1/2/4/` |
| 5 | `/1/5/` |
| 6 | `/1/5/6/` |
| 7 | `/1/2/3/7/` |

Một hậu duệ của 2 có đường đi bắt đầu bằng `/1/2/`. Có thể tìm nhánh bằng phép so khớp tiền tố khi chỉ mục và kiểu dữ liệu hỗ trợ. Ngược lại, di chuyển 2 sang dưới 6 buộc cập nhật đường đi của **cả bốn nút** 2, 3, 4, 7.

Phải chuẩn hóa cách mã hóa đoạn đường dẫn: dùng dấu phân tách để `/1/2/` không trùng tiền tố với `/1/20/`; dùng ID có thể thoát ký tự hoặc mã hóa chuẩn; kiểm tra giới hạn chiều dài và không chấp nhận người dùng ghi `path` tùy ý. PostgreSQL có thể dùng `ltree` khi phù hợp, nhưng đó là extension có ngữ nghĩa và chỉ mục riêng, không mặc định tương đương `TEXT`.

### 2.3. Bảng quan hệ đóng bắc cầu (closure table)

Bên cạnh bảng nút, lưu thêm một dòng cho **mỗi cặp tổ tiên–hậu duệ**, thường gồm cả cặp nút với chính nó ở `depth = 0`:

| `ancestor_id` | `descendant_id` | `depth` |
|---:|---:|---:|
| 1 | 1 | 0 |
| 1 | 2 | 1 |
| 1 | 3 | 2 |
| 1 | 7 | 3 |
| 2 | 2 | 0 |
| 2 | 3 | 1 |
| 2 | 4 | 1 |
| 2 | 7 | 2 |
| 3 | 3 | 0 |
| 3 | 7 | 1 |
| 7 | 7 | 0 |

Bảng trên chỉ là **một phần minh họa**; bảng đầy đủ phải có cặp tương ứng cho mọi nút, kể cả 4, 5 và 6. Khi có chỉ mục theo `ancestor_id` và `descendant_id`, tìm tổ tiên hoặc hậu duệ không cần tự đệ quy quan hệ cha trực tiếp ở thời điểm đọc. Đánh đổi là nhiều dòng phụ và cập nhật phức tạp hơn khi đổi nhánh.

### 2.4. Tập khoảng lồng nhau (nested sets)

Mỗi nút nhận cặp `lft`, `rgt` từ phép duyệt cây theo thứ tự, sao cho khoảng của cha **bao trùm** toàn bộ khoảng của con:

| `node_id` | `lft` | `rgt` |
|---:|---:|---:|
| 1 | 1 | 14 |
| 2 | 2 | 9 |
| 3 | 3 | 6 |
| 7 | 4 | 5 |
| 4 | 7 | 8 |
| 5 | 10 | 13 |
| 6 | 11 | 12 |

Ở dạng đánh số liên tục chuẩn, nút lá có `rgt = lft + 1`. Tất cả hậu duệ của nút 2 nằm trong khoảng `(2, 9)`. Truy vấn theo khoảng thuận tiện cho **đọc cả nhánh**, nhưng thêm hoặc di chuyển nhánh có thể phải đánh số lại nhiều nút không thuộc nhánh đó. Nếu dùng giá trị có khoảng trống, hành vi cập nhật có thể khác; bảng chi phí ở đây giả định **nested sets cổ điển với thứ tự liên tục**.

Nested sets thường giữ thêm `parent_id` hoặc một cấu trúc liên kết phụ nếu cần tìm cha trực tiếp thường xuyên. Khi giữ hai biểu diễn song song, phải cập nhật chúng nhất quán trong cùng transaction.

## 3. Bảng so sánh chi phí theo thao tác

Giả định các khóa và chỉ mục phù hợp đã được tạo, không có dữ liệu bất thường; chi phí trả về kết quả và cập nhật chỉ mục được nói rõ bên dưới.

| Mô hình | Đọc tổ tiên | Đọc cây con | Di chuyển nhánh | Đổi tên/thuộc tính thông thường |
|---|---|---|---|---|
| **Adjacency list** | Đi theo \(h\) cha; khoảng \(h\) lần tìm khóa | Duyệt \(s\) nút qua chỉ mục `parent_id` | **1 dòng cấu trúc** + duyệt/kiểm tra tránh chu trình, có thể \(O(s)\) | **1 dòng** |
| **Materialized path** | Tách khoảng \(h\) đoạn đường đi, rồi tra tên từng nút nếu cần | Quét tiền tố; gần \(O(\log N+s)\) khi chỉ mục tận dụng được | Ghi lại `path` cho **\(s\) dòng** và chỉ mục liên quan | **1 dòng** nếu path theo ID ổn định |
| **Closure table** | Đọc khoảng \(h\) dòng closure qua chỉ mục | Đọc khoảng \(s\) dòng closure qua chỉ mục | Xóa/thêm quan hệ tổ tiên ngoài nhánh, khoảng \(O((a_o+a_n)s)\) dòng phụ | **1 dòng nút**, không sửa closure |
| **Nested sets** | Lọc các khoảng bao chứa; thường khó có chi phí \(O(h)\) bảo đảm | Quét một dải khoảng, gần \(O(\log N+s)\) nếu chỉ mục và kế hoạch phù hợp | Có thể đánh số lại \(O(N)\) nút/khoảng | **1 dòng** |

Đây là mô hình **chi phí hàng và bước xử lý**, không phải thời gian chạy đo thực tế. Ví dụ, một thao tác của adjacency list “đi theo \(h\) cha” có thể thực hiện khoảng \(h\) lần tìm qua B-tree, tổng chi phí lý thuyết cỡ \(O(h\log N)\). Closure table có thể đọc \(h\) dòng theo một dải chỉ mục, với công tìm ban đầu và chi phí xuất dữ liệu. Nested sets dùng điều kiện hai chiều `lft < x AND rgt > y`; một B-tree riêng có thể vẫn phải xét nhiều dòng trước khi lọc đúng \(h\) tổ tiên, nên không hứa hẹn \(O(h)\) chỉ từ số dòng kết quả.

### 3.1. So sánh dung lượng lưu trữ

| Mô hình | Dữ liệu cấu trúc bổ sung | Điểm cần nhớ |
|---|---|---|
| Adjacency list | Một `parent_id`/nút, tổng \(O(N)\) | Nhẹ, ít chỉ mục chuyên biệt |
| Materialized path | Đường đi của từng nút, tổng độ dài tăng theo \(\sum \text{depth}(node)\) | Cây sâu làm path dài; sửa nhánh tạo ghi nhiều dòng |
| Closure table | Khoảng \(N+\sum \text{depth}(node)\) dòng nếu tính cả tự tham chiếu | Cây dây chuyền có thể đạt \(O(N^2)\) dòng closure |
| Nested sets | Hai số `lft`/`rgt` cho mỗi nút, \(O(N)\) | Ghi ít cột nhưng thay đổi cấu trúc có thể cập nhật hàng loạt |

Nếu \(N=100{,}000\) và độ sâu trung bình khoảng 6, closure table có thể chứa khoảng \(100{,}000\times(6+1)=700{,}000\) dòng, **chỉ là ước lượng theo giả định ấy**; kích thước thật còn phụ thuộc phân phối độ sâu, kiểu cột và chỉ mục. Cây dây chuyền cùng \(N\) sẽ tốn nhiều hơn rất đáng kể.

## 4. Xây dựng một lược đồ nguồn có thể kiểm chứng

Dù chọn cấu trúc nào, mô hình quan hệ vẫn cần xác định **danh tính nút, phạm vi tenant, quan hệ cha và bất biến không chu trình**. Với adjacency list làm nguồn dữ liệu, PostgreSQL có thể dùng:

```sql
CREATE TABLE category_nodes (
    tenant_id BIGINT NOT NULL,
    node_id BIGINT NOT NULL,
    parent_id BIGINT,
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT pk_category_nodes
        PRIMARY KEY (tenant_id, node_id),

    CONSTRAINT fk_category_nodes_parent
        FOREIGN KEY (tenant_id, parent_id)
        REFERENCES category_nodes (tenant_id, node_id)
        ON DELETE RESTRICT,

    CONSTRAINT ck_node_not_own_parent
        CHECK (parent_id IS NULL OR parent_id <> node_id),

    CONSTRAINT ck_node_slug
        CHECK (btrim(slug) <> ''),

    CONSTRAINT ck_node_display_name
        CHECK (btrim(display_name) <> ''),

    CONSTRAINT uq_sibling_slug
        UNIQUE NULLS NOT DISTINCT (tenant_id, parent_id, slug)
);
```

Bảng này cho phép nhiều gốc với `slug` khác nhau trong cùng tenant. Nếu nghiệp vụ yêu cầu **tối đa một gốc/tenant**, cần thêm unique index từng phần trên `tenant_id WHERE parent_id IS NULL`. Muốn bảo đảm **mỗi tenant có ít nhất một gốc**, còn cần cơ chế tạo/xóa phù hợp; ràng buộc unique không bảo đảm tồn tại.

`UNIQUE (tenant_id, parent_id, slug) NULLS NOT DISTINCT` của PostgreSQL 15+ đã tạo chỉ mục có tiền tố `(tenant_id, parent_id)`, có thể phục vụ đọc con trực tiếp. Không nhất thiết cần thêm chỉ mục trùng tiền tố. Trong hệ khác, cú pháp xử lý `NULL` và unique có thể khác.

Khóa ngoại ghép ngăn nút của tenant 42 nhận cha thuộc tenant 43. `CHECK` ngăn nút là cha trực tiếp của chính nó. **Không ràng buộc nào trong số này tự ngăn vòng nhiều nút**, ví dụ A → B → C → A; cần cơ chế bổ sung trên đường cập nhật cây.

### Dữ liệu mẫu

```sql
INSERT INTO category_nodes
    (tenant_id, node_id, parent_id, slug, display_name)
VALUES (42, 1, NULL, 'all', 'Tất cả');

INSERT INTO category_nodes
    (tenant_id, node_id, parent_id, slug, display_name)
VALUES
    (42, 2, 1, 'electronics', 'Điện tử'),
    (42, 5, 1, 'fashion', 'Thời trang');

INSERT INTO category_nodes
    (tenant_id, node_id, parent_id, slug, display_name)
VALUES
    (42, 3, 2, 'phones', 'Điện thoại'),
    (42, 4, 2, 'laptops', 'Laptop'),
    (42, 6, 5, 'shoes', 'Giày');

INSERT INTO category_nodes
    (tenant_id, node_id, parent_id, slug, display_name)
VALUES (42, 7, 3, 'android', 'Android');
```

Các truy vấn tiếp theo đọc trên dữ liệu mẫu ở trạng thái **trước khi di chuyển**.

## 5. Chi phí đọc tổ tiên

Đọc tổ tiên thường phục vụ breadcrumb, phân quyền kế thừa hoặc xác định vị trí nút trong cây.

### 5.1. Adjacency list: đi từng cạnh lên gốc

```sql
WITH RECURSIVE ancestors AS (
    SELECT n.tenant_id, n.node_id, n.parent_id,
           n.display_name, 0 AS distance_to_target,
           ARRAY[n.node_id]::BIGINT[] AS visited
    FROM category_nodes AS n
    WHERE n.tenant_id = 42 AND n.node_id = 7

    UNION ALL

    SELECT p.tenant_id, p.node_id, p.parent_id,
           p.display_name, a.distance_to_target + 1,
           a.visited || p.node_id
    FROM ancestors AS a
    JOIN category_nodes AS p
      ON p.tenant_id = a.tenant_id
     AND p.node_id = a.parent_id
    WHERE NOT (p.node_id = ANY(a.visited))
)
SELECT node_id, display_name, distance_to_target
FROM ancestors
ORDER BY distance_to_target DESC;
```

Kết quả gồm các nút 1, 2, 3, 7 theo thứ tự từ gốc đến nút đích. Cột `visited` phòng vệ vòng lặp khi dữ liệu đã bị lỗi; không chứng minh hệ thống đã ngăn mọi chu trình ngay lúc ghi.

Trong cây sâu \(h\), cần lần lượt biết cha của cha, nên có \(h\) bước phụ thuộc nhau. Chỉ mục khóa chính giúp tìm mỗi cha nhanh nhưng không thể song song hóa hoàn toàn các bước chưa biết ID tiếp theo. Với breadcrumb độ sâu 3–6, chi phí này thường nhỏ; với phân cấp sâu hàng nghìn cấp và tần suất đọc lớn, cần đo thực tế.

### 5.2. Materialized path: đường đi chứa sẵn danh tính tổ tiên

Với `path = '/1/2/3/7/'`, chuỗi đã chứa các ID cần dùng để dựng thứ tự tổ tiên. Nếu UI chỉ cần đường ID, có thể phân đoạn đường đi tại ứng dụng mà không phải recursive CTE.

Nếu UI cần **tên hiện tại**, vẫn phải lấy dữ liệu của các nút 1, 2, 3, 7, có thể bằng truy vấn theo tập ID và sắp lại theo thứ tự path. Không nên lưu tên danh mục trong path định danh: nếu lưu `/Tất cả/Điện tử/...` thì đổi tên “Điện tử” buộc viết lại đường đi của toàn bộ hậu duệ.

Chi phí nhận đường đi là một lần đọc dòng nút, cộng chi phí xử lý chuỗi có chiều dài tỷ lệ với \(h\); chi phí đọc thuộc tính tổ tiên tăng theo số nút cần hiển thị.

### 5.3. Closure table: tổ tiên là các dòng đã vật lý hóa

Lược đồ phụ có thể dùng:

```sql
CREATE TABLE category_closure (
    tenant_id BIGINT NOT NULL,
    ancestor_id BIGINT NOT NULL,
    descendant_id BIGINT NOT NULL,
    depth INTEGER NOT NULL,

    CONSTRAINT pk_category_closure
        PRIMARY KEY (tenant_id, ancestor_id, descendant_id),

    CONSTRAINT fk_closure_ancestor
        FOREIGN KEY (tenant_id, ancestor_id)
        REFERENCES category_nodes (tenant_id, node_id),

    CONSTRAINT fk_closure_descendant
        FOREIGN KEY (tenant_id, descendant_id)
        REFERENCES category_nodes (tenant_id, node_id),

    CONSTRAINT ck_closure_depth CHECK (depth >= 0),
    CONSTRAINT ck_closure_self_depth
        CHECK (
          (ancestor_id = descendant_id AND depth = 0)
          OR (ancestor_id <> descendant_id AND depth > 0)
        )
);

CREATE INDEX ix_closure_descendant
    ON category_closure (tenant_id, descendant_id, depth);
```

Bảng closure phải được **khởi tạo** từ cây nguồn và được **duy trì trong cùng transaction** với các thao tác thay đổi quan hệ cha–con. Hai khóa ngoại chỉ bảo đảm hai đầu cạnh tồn tại; chúng không chứng minh bảng closure đã có **đầy đủ và chính xác** mọi đường đi.

Truy vấn tổ tiên của nút 7:

```sql
SELECT c.ancestor_id, n.display_name, c.depth
FROM category_closure AS c
JOIN category_nodes AS n
  ON n.tenant_id = c.tenant_id
 AND n.node_id = c.ancestor_id
WHERE c.tenant_id = 42
  AND c.descendant_id = 7
ORDER BY c.depth DESC;
```

Với chỉ mục `(tenant_id, descendant_id, depth)`, những dòng liên quan tới một hậu duệ có thể được tìm tập trung. Để hiển thị tên, vẫn cần join sang bảng nút. Ưu điểm lớn là không phải tìm cha của cha ở mỗi tầng.

### 5.4. Nested sets: lọc các khoảng bao chứa

Giả sử bảng nút có thêm `lft` và `rgt` đã được duy trì nhất quán, truy vấn tổ tiên dựa trên quan hệ:

```sql
SELECT ancestor.node_id, ancestor.display_name
FROM category_nodes AS target
JOIN category_nodes AS ancestor
  ON ancestor.tenant_id = target.tenant_id
 AND ancestor.lft < target.lft
 AND ancestor.rgt > target.rgt
WHERE target.tenant_id = 42
  AND target.node_id = 7
ORDER BY ancestor.lft;
```

Đoạn SQL là **mẫu truy vấn cho biến thể nested sets**; bảng `category_nodes` ở phần 4 chưa khai báo `lft`/`rgt`, nên cần bổ sung hai cột và cơ chế gán khoảng trước khi chạy.

Điều kiện hai phía có thể khó tận dụng triệt để một B-tree thông thường. Số tổ tiên trả về chỉ là \(h\), nhưng engine có thể xem nhiều hàng hơn \(h\). Do đó, nested sets đặc biệt hấp dẫn khi **đọc hậu duệ theo một khoảng**, còn chi phí đọc tổ tiên phải dựa trên `EXPLAIN` và phân bố dữ liệu thực.

## 6. Chi phí đọc toàn bộ cây con

Giả sử cần xem tất cả danh mục con của “Điện tử” trong một trang quản trị và tính số sản phẩm của mỗi danh mục.

### 6.1. Adjacency list: duyệt theo `parent_id`

```sql
WITH RECURSIVE subtree AS (
    SELECT n.tenant_id, n.node_id, n.parent_id,
           n.display_name, 0 AS relative_depth,
           ARRAY[n.node_id]::BIGINT[] AS visited
    FROM category_nodes AS n
    WHERE n.tenant_id = 42 AND n.node_id = 2

    UNION ALL

    SELECT child.tenant_id, child.node_id, child.parent_id,
           child.display_name, t.relative_depth + 1,
           t.visited || child.node_id
    FROM subtree AS t
    JOIN category_nodes AS child
      ON child.tenant_id = t.tenant_id
     AND child.parent_id = t.node_id
    WHERE NOT (child.node_id = ANY(t.visited))
)
SELECT node_id, display_name, relative_depth
FROM subtree
ORDER BY relative_depth, node_id;
```

Truy vấn trả về 2, 3, 4, 7. Nếu ứng dụng chỉ muốn **hậu duệ thực sự** mà không muốn nút bắt đầu, thêm điều kiện `relative_depth > 0` ở kết quả cuối.

Mỗi nút duyệt được cần tìm con theo `parent_id`. Chỉ mục có tiền tố `(tenant_id, parent_id)` giúp giảm số hàng không liên quan phải xét. Tính theo số nút phát hiện là khoảng \(s\) lần mở rộng, nhưng truy vấn còn cần làm việc với chỉ mục, mảng phòng vệ chu trình, sắp xếp và dữ liệu thực tế.

### 6.2. Materialized path: đọc theo tiền tố

Với đường đi của nút 2 là `/1/2/`, ta lấy các dòng có path bắt đầu bằng đúng chuỗi đó.

```sql
-- Minh họa cho biến thể bảng category_paths(tenant_id, node_id, path).
SELECT node_id, path
FROM category_paths
WHERE tenant_id = 42
  AND path LIKE '/1/2/%'
ORDER BY path;
```

Đây là truy vấn **minh họa**, cần tạo bảng/cột `category_paths` và chỉ mục phù hợp trước khi chạy. Trong PostgreSQL, chỉ mục B-tree cho `LIKE 'prefix%'` có thể cần `text_pattern_ops` khi collation không cho phép tối ưu tiền tố mặc định; với tham số động, kế hoạch còn phụ thuộc việc planner có biết tiền tố khi lập kế hoạch hay không. Dùng `ltree` và GiST/GiN thích hợp là hướng khác. Không nên giả định mọi biểu thức `LIKE path_of_parent || '%'` đều được tối ưu như một phép quét khoảng.

Lợi thế chính: hậu duệ nằm trong một vùng có thể truy cập theo tiền tố; sau đó kết quả vẫn phải đọc \(s\) nút. Với nhánh rất lớn, phân trang và giới hạn dữ liệu đưa về UI vẫn cần thiết.

### 6.3. Closure table: đọc theo `ancestor_id`

```sql
SELECT n.node_id, n.display_name, c.depth
FROM category_closure AS c
JOIN category_nodes AS n
  ON n.tenant_id = c.tenant_id
 AND n.node_id = c.descendant_id
WHERE c.tenant_id = 42
  AND c.ancestor_id = 2
ORDER BY c.depth, n.node_id;
```

Khóa chính `(tenant_id, ancestor_id, descendant_id)` hỗ trợ tìm các cặp có cùng tổ tiên. Truy vấn đọc khoảng \(s\) dòng closure liên quan; khi cần tên, thực hiện thêm join tới \(s\) dòng nút. Có thể có chi phí sắp xếp nếu chỉ mục không khớp `ORDER BY`.

Closure table đặc biệt hữu ích khi cùng một ứng dụng thường xuyên hỏi “toàn bộ hậu duệ”, “mọi tổ tiên”, “khoảng cách cấp bậc”, hay kiểm tra “A có là tổ tiên của B không?” bằng một phép tìm cặp khóa.

### 6.4. Nested sets: quét khoảng vị trí

Nếu nút 2 có `lft = 2` và `rgt = 9`:

```sql
SELECT child.node_id, child.display_name, child.lft, child.rgt
FROM category_nodes AS child
WHERE child.tenant_id = 42
  AND child.lft BETWEEN 2 AND 9
ORDER BY child.lft;
```

Với các khoảng nested sets hợp lệ, phép quét này trả toàn bộ cây con tính cả nút 2. Chỉ mục `(tenant_id, lft)` có thể giúp duyệt dải liên tiếp hiệu quả. Đây là ưu thế truyền thống của nested sets trong workload **đọc nhánh nhiều, sửa cây hiếm**.

Tuy nhiên, nếu cần lấy các nút ở **đúng một cấp**, hoặc quan hệ cha trực tiếp của mỗi dòng, nested sets có thể cần truy vấn bổ sung hoặc lưu riêng `parent_id`. Không đánh giá một mô hình chỉ dựa trên một loại truy vấn.

## 7. Di chuyển nhánh: chi phí ghi khác nhau ở đâu?

Giả sử chuyển nút 2 “Điện tử” thành con của nút 6 “Giày”:

```text
Trước:  Tất cả → Điện tử → (Điện thoại → Android, Laptop)
        Tất cả → Thời trang → Giày

Sau:    Tất cả → Thời trang → Giày → Điện tử
                                       ├── Điện thoại → Android
                                       └── Laptop
```

Nhánh chuyển có \(s=4\). Bất biến bắt buộc: **cha mới không được là chính nút chuyển hoặc một hậu duệ của nó**; cha mới phải tồn tại và thuộc cùng tenant. Nếu tên định danh duy nhất theo cha, phải kiểm tra cả va chạm tên/`slug` sau khi chuyển.

### 7.1. Adjacency list: một lần cập nhật cấu trúc, kèm kiểm tra

Về biểu diễn, sau khi kiểm tra hợp lệ:

```sql
UPDATE category_nodes
SET parent_id = 6
WHERE tenant_id = 42 AND node_id = 2;
```

Chỉ một dòng thay `parent_id`; những dòng 3, 4, 7 vẫn trỏ tới cha trực tiếp cũ và tự nhiên theo nhánh sang vị trí mới. Nhưng **không được** coi lệnh trên là một API chuyển nhánh an toàn nếu chưa thực hiện kiểm tra chu trình và đồng bộ.

Một mẫu giao dịch tập trung dưới isolation `READ COMMITTED`, giả định **mọi thao tác đổi quan hệ cha–con của tenant này đều lấy cùng advisory lock**:

```sql
BEGIN;

-- Khóa minh họa riêng cho cây tenant 42.
-- Mọi code path sửa cấu trúc cây này phải dùng đúng quy ước khóa.
SELECT pg_advisory_xact_lock(9007, 42);

WITH RECURSIVE subtree AS (
    SELECT n.node_id, n.parent_id,
           ARRAY[n.node_id]::BIGINT[] AS visited
    FROM category_nodes AS n
    WHERE n.tenant_id = 42 AND n.node_id = 2

    UNION ALL

    SELECT c.node_id, c.parent_id, t.visited || c.node_id
    FROM subtree AS t
    JOIN category_nodes AS c
      ON c.tenant_id = 42 AND c.parent_id = t.node_id
    WHERE NOT (c.node_id = ANY(t.visited))
)
UPDATE category_nodes AS moved
SET parent_id = 6
WHERE moved.tenant_id = 42
  AND moved.node_id = 2
  AND EXISTS (
      SELECT 1 FROM category_nodes AS new_parent
      WHERE new_parent.tenant_id = 42 AND new_parent.node_id = 6
  )
  AND NOT EXISTS (
      SELECT 1 FROM subtree WHERE node_id = 6
  )
RETURNING moved.node_id, moved.parent_id;

COMMIT;
```

Ứng dụng cần xác nhận `UPDATE` trả về **đúng một dòng** và giải thích khi nó trả 0 dòng (không có nút, cha không tồn tại hoặc có nguy cơ tạo chu trình). Nếu xảy ra lỗi unique/FK, transaction phải rollback. Khóa advisory theo tenant chỉ an toàn với những luồng cùng tuân thủ quy ước; nên tập trung thay đổi cấu trúc vào một service/stored procedure và giới hạn quyền ghi trực tiếp. Với tenant ID ngoài phạm vi số nguyên 32-bit của mẫu khóa hai tham số, phải thiết kế khóa phù hợp để tránh va chạm.

Chi phí có hai phần rất khác nhau:

- **Ghi cấu trúc:** một dòng `parent_id`, kèm thay đổi chỉ mục có liên quan.
- **Xác thực chuyển nhánh:** có thể duyệt \(s\) nút nếu tìm toàn bộ cây con hoặc \(h\) cha nếu kiểm tra theo đường tổ tiên của cha mới, kèm khóa và đồng bộ cạnh tranh.

Vì vậy, phát biểu “move của adjacency list là \(O(1)\)” chỉ đúng cho số **dòng cần thay đổi cấu trúc**, không đúng cho toàn bộ thao tác an toàn ở hệ thống nhiều giao dịch.

### 7.2. Materialized path: viết lại mọi đường đi trong cây con

Đường cũ của 2: `/1/2/`; đường mới: `/1/5/6/2/`. Các dòng có tiền tố cũ được đổi tiền tố:

```text
/1/2/       → /1/5/6/2/
/1/2/3/     → /1/5/6/2/3/
/1/2/4/     → /1/5/6/2/4/
/1/2/3/7/   → /1/5/6/2/3/7/
```

Với \(s\) nút trong cây con, phải cập nhật khoảng \(s\) đường đi và các mục chỉ mục liên quan. Cần kiểm tra đường của cha mới không nằm trong cây con chuyển, giữ đúng tenant và chạy cập nhật nhất quán trong transaction. Nếu chỉ sửa `path` của nút 2, các hậu duệ sẽ mang đường đi cũ và cấu trúc bị mâu thuẫn.

Khi nhiều giao dịch cùng đổi cha hoặc thêm nút dưới nhánh đang chuyển, phải đồng bộ các thao tác đó. Cách dựng path bằng việc đọc cha rồi ghi con ngoài transaction có thể tạo path sai.

### 7.3. Closure table: xóa các cặp tổ tiên cũ và thêm cặp mới

Khi di chuyển cây con \(S\) của nút 2, các quan hệ **nội bộ** trong \(S\) không đổi: 2 vẫn là tổ tiên của 3, 4, 7 và 3 vẫn là tổ tiên của 7.

Những quan hệ cần cập nhật là các cặp nối **tổ tiên bên ngoài nhánh** với mọi nút trong \(S\):

1. Xóa cặp giữa các tổ tiên cũ bên ngoài \(S\) và mỗi hậu duệ của 2.
2. Thêm cặp giữa cha mới cùng mọi tổ tiên của cha mới và mỗi hậu duệ của 2.
3. Tính lại `depth` của mỗi cặp mới bằng khoảng cách đến cha mới + 1 + khoảng cách từ gốc nhánh đến hậu duệ.

Khi số tổ tiên cũ là \(a_o\), tổ tiên mới tính cả cha là \(a_n\), số dòng closure bị xóa/thêm có độ lớn cỡ:

\[
a_o s + a_n s = (a_o+a_n)s.
\]

Đó là chi phí **ghi các dòng quan hệ**, chưa tính duyệt để lập tập, kiểm tra chu trình, duy trì chỉ mục, WAL và khóa. Nếu các đường cũ và mới chia sẻ tổ tiên, triển khai có thể tối ưu một phần thao tác không cần đổi; biểu thức trên là cách ước lượng dễ hiểu khi xóa và dựng lại toàn bộ quan hệ bên ngoài nhánh.

Một thao tác chuyển nhánh trên cây sâu, với \(s\) lớn, có thể cập nhật số dòng phụ lớn hơn nhiều so với \(s\). Đổi lại, các truy vấn tổ tiên/hậu duệ sau đó đọc nhanh mà không tái xây quan hệ từ parent.

### 7.4. Nested sets: dịch chuyển các khoảng đánh số

Trong cách đánh số liên tục, chuyển một đoạn cây sang vị trí khác làm thay đổi cả khoảng của cây con lẫn vị trí của nhiều nút nằm giữa nơi cũ và nơi mới. Số dòng có thể bị cập nhật cỡ \(N\) trong trường hợp xấu; một vài thuật toán còn dùng nhiều pha dịch chỉ số và cần khóa/transaction cẩn thận để tránh va chạm unique tạm thời.

Với cây nhỏ, thao tác ấy có thể chấp nhận được. Với \(N\) lớn, hàng loạt cập nhật `lft` và `rgt` có thể tạo ghi WAL lớn, khóa kéo dài, tranh chấp và áp lực duy trì chỉ mục. Nếu workload thường chuyển nhánh, nested sets cổ điển thường ít thuận lợi.

## 8. Cập nhật nút: cần tách thuộc tính với vị trí

Câu “cập nhật nút” trong backlog có thể chỉ nhiều thao tác với chi phí hoàn toàn khác nhau.

| Thao tác | Adjacency list | Materialized path | Closure table | Nested sets |
|---|---|---|---|---|
| Đổi `display_name` khi path dùng ID | Sửa 1 dòng | Sửa 1 dòng | Sửa 1 dòng nút | Sửa 1 dòng |
| Đổi `slug` khi `slug` không có trong path | Sửa 1 dòng + kiểm tra unique | Sửa 1 dòng + kiểm tra unique | Sửa 1 dòng + kiểm tra unique | Sửa 1 dòng + kiểm tra unique |
| Đổi tên khi path chứa **tên** | Sửa 1 dòng | Có thể phải sửa path của \(s\) nút | Sửa 1 dòng | Sửa 1 dòng |
| Đổi `parent_id` / chuyển nhánh | Kiểm tra + sửa cha của 1 nút | Kiểm tra + cập nhật path của \(s\) nút | Kiểm tra + sửa khoảng \((a_o+a_n)s\) quan hệ | Kiểm tra + có thể đánh số lại \(O(N)\) nút |
| Thêm nút lá | 1 dòng + kiểm tra FK | 1 dòng, path dựa vào cha | 1 dòng nút + khoảng \(h+1\) dòng closure | Thường phải dịch chuyển nhiều khoảng, có thể \(O(N)\) |
| Xóa nút lá | 1 dòng nếu không bị FK khác chặn | 1 dòng nếu đã xử lý phụ thuộc | 1 dòng nút + xóa khoảng \(h+1\) closure | Thường dịch khoảng, có thể \(O(N)\) |

Trong bảng trên, “1 dòng” chỉ là **khối lượng ghi cấu trúc**; thao tác còn có kiểm tra quyền, FK, unique constraint, index và trigger. Nếu cây được dùng để kế thừa quyền, một lần đổi trạng thái `is_active` hoặc quyền của cha **có thể làm thay đổi ngữ nghĩa của cả nhánh**, dù vật lý chỉ sửa một dòng. Cache quyền/breadcrumb/count phải được làm mới theo hợp đồng nhất quán.

**Quy tắc thiết kế:** không gộp “đổi tên”, “đổi trạng thái” và “đổi cha” vào một chỉ số `update_node_cost`. Hãy đo chúng riêng, vì tần suất và rủi ro hoàn toàn khác.

## 9. Chọn theo dạng cây và tỷ lệ đọc/ghi

Chi phí phụ thuộc hình dạng cây và nơi đặt hoạt động nóng (*hotspot*).

### Trường hợp A: cây sâu, ít con

Ví dụ các cấp phê duyệt liên tục tạo chuỗi 800 nút. Đọc tổ tiên của nút cuối phải trả tới 799 dòng; bản thân kết quả đã lớn. Adjacency list phải đi nhiều bước phụ thuộc nhau. Closure table có thể truy vấn các tổ tiên bằng dải chỉ mục, nhưng lưu số cặp tổ tiên–hậu duệ rất lớn (trong chuỗi \(N\) nút là \(N(N+1)/2\) cặp tính cả tự thân). Nested sets không có lượng lưu phụ lớn nhưng thao tác chèn/chuyển vị trí có thể rất đắt.

Đối với loại cây này, cần hỏi vì sao độ sâu lớn và có cần thực sự xuất tất cả tổ tiên mỗi lần không; có thể lưu cache hoặc giới hạn mức hiển thị, nhưng phải có chiến lược vô hiệu hóa cache khi đổi cây.

### Trường hợp B: cây rộng, nông

Ví dụ một gốc có hàng chục nghìn danh mục con trực tiếp. Đọc tổ tiên của từng lá rất rẻ với adjacency list vì chỉ một bước lên gốc. Đọc **toàn bộ** cây vẫn phải trả rất nhiều dòng, dù dùng closure hay nested sets. Vấn đề chính có thể là phân trang, lọc và khối lượng trả về mạng, hơn là cần một cấu trúc mới.

### Trường hợp C: thường xuyên di chuyển nhánh lớn

Ví dụ đội vận hành liên tục tái tổ chức danh mục: mỗi ngày chuyển hàng trăm nhánh, mỗi nhánh gồm nhiều nghìn nút. Adjacency list có lợi thế chỉ thay một liên kết cha (sau khi chống chu trình); materialized path phải cập nhật \(s\) đường; closure table phải duy trì nhiều cặp; nested sets có thể đánh lại vị trí trên vùng lớn. Với workload này, nên ưu tiên thiết kế đường ghi và an toàn cạnh tranh.

### Trường hợp D: nhiều truy vấn tổ tiên/hậu duệ, ít thay đổi cây

Ví dụ cây danh mục chuẩn được chỉnh sửa mỗi quý nhưng dùng để lọc báo cáo liên tục. Closure table hoặc materialized path có thể giảm số bước đệ quy lúc đọc. Nested sets cũng có thể hiệu quả nếu phần lớn là đọc cây con theo khoảng. Tuy vậy, cần tính thêm dung lượng phụ, chi phí build lại khi cập nhật và khả năng báo cáo theo phiên bản lịch sử.

## 10. Ước lượng tác động từ workload cụ thể

Giả sử một tenant có:

- \(N=100{,}000\) nút;
- độ sâu trung bình khoảng 6;
- mỗi ngày có 50.000 truy vấn tổ tiên, 20.000 truy vấn cây con;
- 100 thao tác chuyển nhánh, mỗi nhánh chuyển có \(s=1{,}500\) nút;
- khoảng \(a_o=5\) tổ tiên cũ và \(a_n=7\) tổ tiên ở vị trí mới.

Theo **số dòng cấu trúc phải sửa** khi chuyển một nhánh, ước lượng minh họa là:

| Mô hình | Số dòng ghi cấu trúc cho một lần chuyển |
|---|---:|
| Adjacency list | 1 dòng `parent_id`, cộng chi phí kiểm tra |
| Materialized path | Khoảng 1.500 dòng `path` |
| Closure table | Khoảng \((5+7)\times1{,}500 = 18{,}000\) dòng xóa/thêm quan hệ |
| Nested sets cổ điển | Phụ thuộc vị trí di chuyển; trường hợp xấu có thể gần 100.000 nút bị điều chỉnh khoảng |

Đây **không phải benchmark độ trễ**. Một lần ghi 18.000 dòng ngắn theo batch có thể nhanh hơn hoặc chậm hơn một lần truy vấn đệ quy 1.500 nút tùy hệ thống. Nếu phần lớn truy vấn hậu duệ trả về hai nút thay vì 1.500 nút, hiệu ứng tối ưu cũng khác.

Để ra quyết định, cần ước lượng **chi phí tổng theo chu kỳ**:

\[
C_{\text{workload}}
\approx R_a C_a + R_s C_s + W_m C_m + W_u C_u
+ C_{\text{storage}} + C_{\text{operations}}
\]

Trong đó \(R_a\), \(R_s\) là số lượt đọc tổ tiên/cây con; \(W_m\), \(W_u\) là số lượt di chuyển/cập nhật nút; \(C\) đại diện chi phí đo được hoặc ước lượng từng thao tác. Phương trình là **khung so sánh**, không thể cộng trực tiếp mili giây, byte lưu trữ và độ rủi ro nếu chưa chuẩn hóa trọng số hoặc tiêu chí đánh giá. Có thể đặt giới hạn riêng cho p95 đọc, thời gian khóa khi move, dung lượng và vận hành thay vì ép tất cả về một điểm số.

## 11. Thiết kế benchmark để kiểm chứng lựa chọn

Một phép đo hữu ích phải dùng **cùng dữ liệu logic** và cùng câu hỏi nghiệp vụ cho mọi mô hình.

### 11.1. Chuẩn bị dữ liệu

Tạo ít nhất ba dạng cây:

1. **Cân đối:** nhiều cấp với hệ số phân nhánh vừa phải; số nút đại diện cho production.
2. **Sâu:** mỗi nút thường có một con; kiểm tra giới hạn recursive CTE, đường đi dài, số closure rows.
3. **Rộng:** gốc có rất nhiều con; kiểm tra selectivity của chỉ mục, phân trang và số dòng thực sự trả.

Dữ liệu phải phân biệt tenant và kích thước nhánh; đo cả cây con 1 nút, 100 nút, 1.000 nút và các nhánh lớn tương ứng với sản phẩm.

### 11.2. Tách nhóm truy vấn và nhóm ghi

| Nhóm đo | Ca cần chạy |
|---|---|
| Đọc tổ tiên | Nút gần gốc, nút lá sâu, nút thường truy cập |
| Đọc cây con | Nút lá, nhánh vừa, nhánh lớn, gốc |
| Di chuyển | Di chuyển lá; nhánh vừa; nhánh lớn; chuyển trong cùng cây; thao tác bị từ chối vì chu trình |
| Cập nhật thuộc tính | Đổi tên, đổi trạng thái, cập nhật thuộc tính không làm đổi vị trí |
| Đồng thời | Nhiều người cùng di chuyển các nhánh giao nhau; cập nhật con trong lúc cha đang chuyển |
| Lịch sử | Truy vấn cây hiện tại so với cây tại thời điểm giao dịch quá khứ, nếu nghiệp vụ yêu cầu |

Với PostgreSQL, đo kế hoạch thực thi bằng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.node_id
FROM category_nodes AS c
WHERE c.tenant_id = 42
  AND c.parent_id = 2;
```

Lệnh minh họa trên chỉ đo **con trực tiếp**, không đại diện cho toàn bộ cây con. Để đo truy vấn tổ tiên/cây con nhiều cấp, đặt câu `WITH RECURSIVE` thực tế sau `EXPLAIN (ANALYZE, BUFFERS)`. Với lệnh ghi, dùng transaction thử nghiệm có rollback và kiểm tra tác động tới trigger, chỉ mục, WAL hoặc công cụ đo tương ứng.

Cần ghi lại: p50/p95/p99 độ trễ, số hàng đọc thực tế, số buffer hit/read, số dòng và byte cập nhật, WAL, thời gian giữ khóa, số lần chờ khóa/deadlock, CPU, dung lượng chỉ mục và chi phí phục hồi từ lỗi. Làm nóng bộ đệm và thứ tự chạy thử có thể làm lệch kết quả; nên lặp đủ vòng và thay đổi thứ tự các phương án khi so sánh.

### 11.3. Đánh giá kế hoạch truy vấn

Một chỉ mục được tạo không có nghĩa planner sẽ dùng nó. Ví dụ:

- `LIKE` trên path phụ thuộc kiểu dữ liệu, collation, operator class và việc biết tiền tố.
- Closure table có hai hướng tra cứu chính: `ancestor_id` và `descendant_id`; một chỉ mục có thứ tự cột không phù hợp có thể khiến một hướng tốn chi phí.
- Adjacency list cần chỉ mục hỗ trợ `(tenant_id, parent_id)` và khóa chính của nút.
- Nested sets thường cần chỉ mục phù hợp theo `lft`; tìm tổ tiên bằng hai bất đẳng thức có thể vẫn phải đọc nhiều hàng.

Chỉ thay đổi thiết kế sau khi biết **nút thắt thực tế**: tìm kiếm chỉ mục, số dòng trả về, mạng, khóa hay duy trì cấu trúc phụ.

## 12. Cạnh tranh, tính toàn vẹn và chi phí vận hành

Một mô hình đọc nhanh có thể phải trả giá bằng việc duy trì nhiều dữ liệu suy ra. Đối với cây, bất biến quan trọng nhất thường là:

- Nút tồn tại và thuộc một tenant xác định.
- Cha tồn tại cùng tenant; mỗi nút có tối đa một cha.
- Không có nút tự làm cha và không có chu trình dài.
- Quan hệ cha–con trong bản chính thức không mâu thuẫn với path/closure/khoảng nested sets.
- Di chuyển nhánh không làm dữ liệu phụ cập nhật **một nửa** rồi được các request khác đọc như trạng thái hoàn chỉnh.

### Cạnh tranh khi hai nhánh bị chuyển đồng thời

Giả sử giao dịch T1 kiểm tra “A không nằm dưới B” và T2 kiểm tra “B không nằm dưới A”, cả hai đều đọc cây cũ và đều thành công. Nếu chúng lần lượt đặt A dưới B và B dưới A mà không có đồng bộ, sẽ tạo vòng.

Vì vậy, ngay cả adjacency list với một dòng đổi cha cũng cần đường ghi tập trung, khóa/cô lập phù hợp và xử lý lỗi giao dịch. Với materialized path và closure table, còn phải khóa/phối hợp các hàng phụ thuộc để hai lần ghi không dựng một cấu trúc suy ra sai lệch.

Nếu lưu **hai nguồn biểu diễn** (ví dụ `parent_id` và `path`), hãy định nghĩa đâu là nguồn chân lý, đâu là dữ liệu suy ra, ai được phép sửa và cơ chế đồng bộ trong một transaction. Một job chạy sau vài phút để sửa path có thể được chấp nhận cho cache tìm kiếm eventual consistency, nhưng không phù hợp nếu API đã hứa rằng danh mục chuyển vị trí sẽ hiển thị nhất quán ngay sau commit.

### Xóa và thay đổi phạm vi sở hữu

Xóa một nút có con cũng là cập nhật cấu trúc cây. Với `ON DELETE RESTRICT`, cần xử lý con trước; với `CASCADE`, có thể xóa cả nhánh, kèm dữ liệu phụ thuộc. Materialized path và closure table cần chính sách xóa các bản ghi suy ra; nested sets cần đánh lại khoảng nếu giữ đánh số liên tục.

Chuyển nút sang tenant khác không chỉ thay `tenant_id`: quan hệ FK, quyền truy cập, khóa duy nhất và cấu trúc phụ đều có thể bị ảnh hưởng. Thông thường nên định nghĩa thao tác “copy/migrate giữa tenant” riêng, không coi như đổi cha thông thường.

## 13. Mở rộng so sánh: document, graph và hệ phân tích

### 13.1. Document

Nếu cả cây con thường được đọc cùng nhau, có thể nhúng nhiều nút vào một document. Một lần đọc document cho được cả nhánh mà không cần join, nhưng document lớn và thao tác chuyển nhánh giữa hai document có thể trở nên đắt, đặc biệt khi cần giao dịch xuyên document.

Nếu mỗi nút là một document với `parentId`, bài toán trở lại gần adjacency list. Việc cưỡng chế cha tồn tại và không chu trình phụ thuộc vào khả năng của engine cùng logic ứng dụng.

### 13.2. Graph

Cơ sở dữ liệu đồ thị lưu nút và cạnh quan hệ cha–con; truy vấn tổ tiên/hậu duệ là phép duyệt cạnh nhiều bước. Với quan hệ đa cha, nhiều loại cạnh và truy vấn đường đi phức tạp, graph có thể mô tả tự nhiên hơn cấu trúc một `parent_id`.

Tuy nhiên, “dùng graph” **không tự giải quyết** chu trình, phân quyền hay giao dịch chuyển nhánh. Chi phí đọc phụ thuộc số đỉnh/cạnh được duyệt, cách lập chỉ mục và engine; chi phí ghi có thể chỉ thay một cạnh nhưng vẫn cần kiểm tra bất biến DAG/cây.

### 13.3. Phân tích và lịch sử cây

Một doanh nghiệp chuyển bộ phận “Nền tảng” từ “Công nghệ” sang “Vận hành” vào ngày 01/07. Nếu báo cáo doanh thu tháng 06 phải dựa theo cấu trúc **tại tháng 06**, thì chỉ lưu `parent_id` hiện tại hoặc cập nhật path/closure hiện tại là **không đủ**.

Cần thiết kế lịch sử hiệu lực: ví dụ `valid_from`/`valid_to` của quan hệ cha–con, snapshot theo kỳ hoặc bảng version của phân cấp. Truy vấn “tổ tiên tại thời điểm T” khác với truy vấn “tổ tiên hiện tại”; không nên áp cùng bảng chi phí nếu phải duyệt nhiều phiên bản. Trong data warehouse, lựa chọn snapshot/bridge table với khóa phiên bản có thể hợp lý hơn việc sao chép nested sets hiện hành.

Chọn cấu trúc cần xét cả **cây hiện tại** và **cây theo thời gian**, nhất là khi dữ liệu được dùng cho báo cáo, kiểm toán hoặc phân bổ chỉ tiêu.

## 14. Ma trận quyết định nhanh

| Điều kiện nghiệp vụ nổi trội | Mô hình nên ưu tiên đánh giá | Lý do chính |
|---|---|---|
| Thêm/sửa/chuyển nhánh thường xuyên; độ sâu vừa phải | **Adjacency list** | Ít dòng cấu trúc cần ghi; mô hình dễ hiểu, dễ khóa ngoại |
| Đọc đường đi/đọc nhánh theo tiền tố nhiều; chuyển nhánh ít | **Materialized path** | Thuận tiện cho tra cứu nhánh bằng tiền tố khi có chỉ mục phù hợp |
| Truy vấn tổ tiên/hậu duệ/khoảng cách rất thường xuyên; cây ít đổi | **Closure table** | Dữ liệu tổ tiên–hậu duệ đã được vật lý hóa và có chỉ mục theo hai chiều |
| Phần lớn đọc cả nhánh theo thứ tự; cây ổn định | **Nested sets** | Truy vấn dải `lft`/`rgt` thuận tiện |
| Nhiều cha hoặc đường đi quan hệ phức tạp | **Edge table / graph** | Biểu diễn được quan hệ tổng quát hơn cây một cha |
| Chủ yếu đọc toàn bộ cây con nhỏ như một tài liệu | **Document lồng nhau**, nếu kích thước và ranh giới giao dịch phù hợp | Lợi ích về tính cục bộ của dữ liệu |

Đây là **điểm khởi đầu để thử nghiệm**, không phải quy tắc lựa chọn tuyệt đối. Một ứng dụng có thể dùng adjacency list làm nguồn chân lý, closure table cho truy vấn đọc thường xuyên hoặc một cache đường đi; nhưng cấu trúc phụ chỉ có giá trị nếu duy trì được tính nhất quán và có cơ chế tái xây khi bị lỗi.

## 15. Bài tập thực hành: đề xuất cấu trúc cho cây phòng ban

Một hệ thống quản trị nhân sự có 80.000 phòng ban và nhóm làm việc của nhiều doanh nghiệp. Mỗi nhóm có đúng một cấp trên; mỗi doanh nghiệp có một cây độc lập. Yêu cầu ban đầu:

- Trung bình 12.000 lần/ngày dựng breadcrumb của một nhóm.
- Trung bình 50.000 lần/ngày lấy mọi nhóm con để tính quyền truy cập.
- Khoảng 200 lần/ngày đổi nhóm lên cấp trên khác.
- Một số nhánh chuyển có hơn 2.000 nút.
- Báo cáo tháng trước phải giữ nguyên cấu trúc đã có ở tháng trước.

Hãy thực hiện:

1. Định nghĩa \(N,h,s,a_o,a_n\) và ước lượng chúng từ dữ liệu thực, thay vì lấy một con số trung bình cho toàn bộ cây.
2. Chọn mô hình nguồn chân lý và giải thích nó bảo vệ khóa, tenant, cha và không chu trình bằng cơ chế nào.
3. So sánh lượng đọc/ghi dự kiến của adjacency list, materialized path, closure table và nested sets cho ba tác vụ: breadcrumb, liệt kê nhóm con, chuyển nhánh.
4. Xác định đường ghi cần khóa hoặc isolation nào để hai người quản trị không đồng thời tạo chu trình.
5. Thiết kế benchmark p95 và tiêu chí chấp nhận: ví dụ đọc cây con đúng kết quả trong giới hạn độ trễ, không có transaction move gây khóa quá lâu.
6. Đề xuất cách lưu lịch sử quan hệ cha–con để báo cáo theo cây của tháng trước; giải thích vì sao bảng cây hiện hành chưa đủ.
7. Phân tích xem có cần cache/closure table làm cấu trúc phụ hay không; nếu có, chỉ ra cách cập nhật và tái xây khi gặp sai lệch.

**Tiêu chí đánh giá:** lựa chọn phải nêu rõ các giả định về dạng cây và tần suất thao tác, phân biệt số dòng cấu trúc phải ghi với tổng thời gian giao dịch, và chỉ rõ cách cưỡng chế không chu trình khi hai lần chuyển nhánh diễn ra đồng thời.

## 16. Những điều cần ghi nhớ

- **Đọc tổ tiên** thường tỷ lệ với độ sâu \(h\); **đọc cây con** ít nhất phải xử lý số kết quả \(s\). Chỉ mục và cấu trúc lưu quyết định số bước tìm tới những kết quả ấy.
- **Adjacency list** nhẹ và rẻ về số dòng sửa khi di chuyển, nhưng kiểm tra chu trình và đồng bộ không phải chi phí bằng 0.
- **Materialized path** giúp truy vấn tiền tố nhưng việc chuyển nhánh phải viết lại đường dẫn của mọi hậu duệ.
- **Closure table** tăng tốc đọc quan hệ tổ tiên/hậu duệ bằng dữ liệu đã vật lý hóa, đổi lại dung lượng khoảng \(N+\sum depth\) và chi phí cập nhật cặp quan hệ.
- **Nested sets** mạnh ở truy vấn dải cây con, nhưng cấu trúc đánh số liên tục khiến cập nhật vị trí có thể ảnh hưởng rất nhiều nút.
- **Đổi tên/thuộc tính** và **đổi cha** là hai workload khác nhau; nên đo riêng.
- Chọn cấu trúc bằng dữ liệu thực, chỉ số độ trễ/khóa/dung lượng và yêu cầu toàn vẹn, đồng thời xét nhu cầu lưu **lịch sử cây theo thời gian**.
