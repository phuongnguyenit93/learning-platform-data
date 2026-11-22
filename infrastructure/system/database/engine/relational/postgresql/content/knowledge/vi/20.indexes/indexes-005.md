# GiST, SP-GiST và các kiểu dữ liệu phù hợp trong PostgreSQL

## 1. Khi B-tree không còn đủ để trả lời câu hỏi

Trong phần lớn ứng dụng, chỉ mục B-tree rất hiệu quả cho tìm kiếm bằng, so sánh thứ tự và sắp xếp các giá trị thông thường. Nhưng nhiều bài toán không đặt câu hỏi “giá trị bằng bao nhiêu?”:

- Điểm nào nằm trong một **hình chữ nhật** trên bản đồ?
- Đối tượng nào ở **gần tọa độ** được chỉ định nhất?
- Khoảng thời gian đặt phòng nào **giao nhau** với khoảng thời gian mới?
- Dải địa chỉ IP nào **bao chứa hoặc nằm trong** một mạng con?
- Chuỗi nào **gần giống** một từ khóa bị gõ sai?
- Những tài liệu nào thỏa **truy vấn tìm kiếm văn bản**?

PostgreSQL cung cấp các **index access methods** mở rộng được; trong đó **GiST** và **SP-GiST** là hai công cụ quan trọng khi kiểu dữ liệu hoặc toán tử truy vấn có cấu trúc không gian, phân vùng hay quan hệ chứa/giao nhau.

Điểm mấu chốt: **không chỉ kiểu dữ liệu, mà cặp _kiểu dữ liệu + toán tử + operator class + mẫu truy vấn_ mới quyết định chỉ mục có thể giúp hay không**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích GiST (*Generalized Search Tree*) và SP-GiST (*Space-Partitioned GiST*) ở mức khái niệm.
2. Phân biệt cấu trúc cây dùng vùng bao/phép tổng hợp với cây chia không gian, ví dụ quadtree, k-d tree và radix tree.
3. Chọn phương pháp chỉ mục phù hợp cho `point`, `box`, `polygon`, `circle`, `range`, `inet/cidr` và `text` theo operator class.
4. Xây truy vấn **chứa điểm**, **giao nhau**, **chứa khoảng**, **mạng con** và **KNN (k-nearest neighbors)**.
5. Biết khi nào phải dùng extension `pg_trgm`, `btree_gist` hoặc `PostGIS`.
6. Hiểu **lossy index**, `Recheck Cond`, `Rows Removed by Index Recheck` và các giới hạn của index-only scan.
7. Đọc `EXPLAIN (ANALYZE, BUFFERS)`, đối chiếu kích thước chỉ mục và tác động ghi dữ liệu.
8. Nhận diện các phản ví dụ: B-tree thường tốt hơn cho equality, GIN hợp với JSONB/array/full-text trong nhiều trường hợp, và SP-GiST không phải bản nâng cấp mặc định của GiST.
9. Triển khai thử nghiệm bằng SQL có thể tái lập và thực hiện bài tập có lời giải.

> **Phạm vi:** cú pháp cốt lõi tập trung vào PostgreSQL hiện đại; một số operator class và extension khác nhau theo phiên bản/cấu hình. Chỉ tạo dữ liệu và index trong database thực hành có quyền. Trên production, tạo index lớn phải tính chi phí khóa, I/O, WAL, đĩa và replication.

---

## 2. Phân biệt access method, operator class và toán tử

Một câu tạo index:

~~~sql
CREATE INDEX idx_places_location_gist
ON index_lab.places
USING gist (location);
~~~

gồm nhiều quyết định:

| Thành phần | Trong ví dụ | Vai trò |
|---|---|---|
| Relation | `index_lab.places` | Nơi dữ liệu được lưu |
| Cột | `location` | Giá trị được lập chỉ mục |
| Access method | `USING gist` | Cơ chế cấu trúc và tìm kiếm của index |
| Operator class | Mặc định cho kiểu `point` khi có | Quy định những toán tử/chiến lược được hỗ trợ |
| Truy vấn | `location <@ box ...`, `ORDER BY location <-> point ...` | Phải dùng operator được opclass hỗ trợ để index có thể phát huy tác dụng |

Đổi `USING gist` thành `USING spgist` **không bảo đảm tất cả toán tử được hỗ trợ như cũ**. Cùng một kiểu `point` có thể có nhiều operator class SP-GiST; `text` dùng SP-GiST không tự hỗ trợ trigram fuzzy search.

### 2.1. Access method không phải phép tăng tốc mọi WHERE

Ví dụ `btree` mặc định được PostgreSQL chọn khi không ghi `USING`:

~~~sql
CREATE INDEX idx_customer_id
ON some_schema.orders (customer_id);
~~~

B-tree thường phù hợp `customer_id = 123`, `customer_id BETWEEN 100 AND 200` và tìm kiếm theo thứ tự. Chuyển cột integer này sang GiST hoặc SP-GiST không có lý do nếu query chỉ lọc equality thông thường.

### 2.2. Operator class đóng vai trò hợp đồng giữa toán tử và index

Giả sử truy vấn dùng:

~~~sql
WHERE active_period && daterange(
    DATE '2026-04-10', DATE '2026-04-12', '[)'
)
~~~

Toán tử `&&` diễn đạt **hai khoảng giao nhau**. Một range operator class GiST hoặc SP-GiST có thể hỗ trợ lập chỉ mục cho operator này. Nhưng một B-tree trên `active_period` không tự đem lại chiến lược tìm tất cả khoảng giao nhau giống như range index.

### 2.3. Kiểm tra hỗ trợ trên database hiện tại

~~~sql
SELECT
    am.amname AS index_method,
    opc.opcname AS operator_class,
    opc.opcintype::regtype AS indexed_type,
    opc.opcdefault AS is_default
FROM pg_opclass AS opc
JOIN pg_am AS am ON am.oid = opc.opcmethod
WHERE am.amname IN ('gist', 'spgist')
ORDER BY am.amname, opc.opcname, indexed_type::text;
~~~

Kết quả phụ thuộc phiên bản và extension đã cài. Không “đoán” một opclass có tên `xyz_ops` tồn tại chỉ từ tên kiểu dữ liệu.

Để xem những toán tử mà từng operator family công bố:

~~~sql
SELECT
    am.amname AS access_method,
    opc.opcname AS operator_class,
    a.amopstrategy AS strategy_number,
    a.amopopr::regoperator AS indexable_operator
FROM pg_opclass AS opc
JOIN pg_am AS am
  ON am.oid = opc.opcmethod
JOIN pg_amop AS a
  ON a.amopfamily = opc.opcfamily
WHERE am.amname IN ('gist', 'spgist')
  AND opc.opcname IN ('point_ops', 'quad_point_ops',
                      'kd_point_ops', 'range_ops')
ORDER BY access_method, operator_class, strategy_number;
~~~

`pg_amop` là catalog về **operator family**, nên kết quả có thể bao gồm toán tử cho nhiều biến thể kiểu đầu vào trong cùng family. Để kiểm tra cú pháp và semantics chính xác, đối chiếu toán tử của đúng kiểu đối số trong tài liệu và `pg_operator`.

---

## 3. GiST: Generalized Search Tree

### 3.1. Ý tưởng của GiST

GiST là hạ tầng **cây tìm kiếm cân bằng, mở rộng được**. Nó không phải một thuật toán chỉ biết xử lý point hay một biến thể B-tree cố định; cấu trúc tree được kết hợp với operator class để biểu diễn chiến lược tìm kiếm phù hợp dữ liệu.

Với đối tượng hình học, một trực giác hữu ích là **các nút nội bộ chứa vùng bao (bounding regions)** đại diện cho những đối tượng con:

~~~text
                    [Vùng bao toàn bộ]
                      /           \
              [Vùng bao A]       [Vùng bao B]
                /     \             /    \
             đối tượng ...        đối tượng ...
~~~

Khi hỏi “đối tượng nào giao với hình H?”, một vùng bao chắc chắn không giao H có thể được **bỏ qua cả nhánh**.

Tuy nhiên, GiST không bắt buộc dùng đúng bounding rectangle cho mọi data type. Operator class có thể triển khai nhiều mô hình khác nhau, bao gồm range, text signature và cấu trúc do extension định nghĩa.

### 3.2. Vai trò của support functions

Ở mức phát triển operator class, GiST dựa vào các hàm support như:

| Nhóm hàm | Ý nghĩa khái quát |
|---|---|
| `consistent` | Xác định một index entry có thể chứa kết quả thỏa toán tử truy vấn không |
| `union` | Tạo mô tả tổng hợp cho nhóm entry |
| `penalty` | Ước tính chi phí mở rộng nhánh khi chèn entry mới |
| `picksplit` | Phân chia entry khi page cần split |
| `same` | Kiểm tra sự tương đồng của các key tổng hợp |
| `compress` / `decompress` | Tùy opclass, chuyển đổi biểu diễn lưu trữ |
| `distance` | Hỗ trợ order-by-distance/KNN khi operator class cung cấp |

Người dùng SQL **không cần tự viết support functions** để dùng operator class sẵn có. Những hàm này giải thích vì sao một access method GiST có thể hỗ trợ nhiều dữ liệu khác nhau.

### 3.3. GiST đặc biệt phù hợp dạng câu hỏi nào?

- Không gian 2D: điểm, hộp, polygon, circle, quan hệ giao/bao.
- Khoảng thời gian và khoảng số: overlap, contains, adjacency.
- Tìm kiếm k hàng gần nhất qua toán tử khoảng cách opclass hỗ trợ.
- Text similarity/trigram khi có `pg_trgm`.
- Full-text search với `tsvector_ops` cho một số chiến lược.
- Chỉ mục kết hợp cho **exclusion constraints**, kể cả kết hợp thuộc tính scalar qua `btree_gist`.

### 3.4. Chỉ mục GiST có thể là lossy

Giả sử index lưu vùng bao lớn hơn hình polygon thật. Một entry vùng bao giao vùng tìm kiếm chỉ có nghĩa **có khả năng** giao; đối tượng thực bên trong có thể không giao.

PostgreSQL có cơ chế **recheck** trên heap khi opclass thông báo kết quả chưa đủ chính xác. Không nên cho rằng GiST cố ý trả “kết quả sai”; index đưa ra **candidate**, executor xác minh điều kiện chính xác trước khi trả kết quả SQL.

~~~text
GiST: lọc candidate theo key tóm tắt
                  |
                  v
             Heap recheck
                  |
                  v
           Kết quả đúng predicate
~~~

Mức độ lossy phụ thuộc operator class, operator và dữ liệu; **không phải mọi scan GiST đều có recheck cùng mức**.

---

## 4. SP-GiST: Space-Partitioned GiST

### 4.1. Ý tưởng phân chia không gian

SP-GiST là hạ tầng cho các **cây phân vùng không gian** trên đĩa, thường có dạng:

- **Quadtree**: chia không gian hai chiều theo các vùng/góc phần tư.
- **k-d tree**: tách không gian theo các chiều khác nhau.
- **Radix tree/trie**: phân nhánh theo prefix/chữ cái.
- Những cấu trúc phân hoạch khác do operator class cụ thể cung cấp.

~~~text
                     [Không gian 2D]
                      /   |   |   \
                    NW   NE  SW   SE
                    |            /  \
                [điểm]         ... [điểm]
~~~

Ví dụ phân tách không gian thành những phân vùng theo quy tắc của opclass; một truy vấn có thể **đi vào một số nhánh phù hợp** thay vì quét toàn bộ các điểm.

### 4.2. “SP-GiST” không phải “GiST nhưng nhanh hơn”

GiST thường dựa vào **đại diện tóm tắt/vùng bao** và cân bằng cây. SP-GiST dựa vào **phép phân hoạch không gian**, có thể không cân bằng theo cùng nghĩa, và dùng tổ chức trên đĩa phù hợp.

SP-GiST có thể phù hợp hơn với một số kiểu phân bố dữ liệu, đặc biệt nếu partition strategy giúp loại nhánh hiệu quả. Nhưng cũng có thể:

- Không có operator class cho data type mong muốn.
- Chỉ hỗ trợ tập operator khác GiST.
- Tốn dung lượng hoặc chi phí insert khác.
- Kém phù hợp hơn GiST khi dữ liệu chồng lấn/cấu trúc khác chiến lược chia.
- Không tốt hơn B-tree cho equality hoặc sort thông thường.

**Quyết định qua EXPLAIN và benchmark trên workload thực**, không bằng tên thuật toán.

### 4.3. Hai opclass point mặc định và tùy chọn

Với kiểu `point`, PostgreSQL cung cấp:

- `quad_point_ops` — operator class SP-GiST mặc định cho `point`.
- `kd_point_ops` — chiến lược phân chia theo kiểu k-d tree.

Hai opclass hỗ trợ cùng nhóm toán tử cơ bản cho point trong bản PostgreSQL hiện đại, bao gồm `<@ (point,box)` và `<-> (point,point)` phục vụ tìm kiếm lân cận.

Ví dụ:

~~~sql
CREATE INDEX idx_points_quad
ON index_lab.places USING spgist (location quad_point_ops);

CREATE INDEX idx_points_kd
ON index_lab.places USING spgist (location kd_point_ops);
~~~

Đây là **hai index thử nghiệm thay thế** để so sánh; production thường không cần giữ cả hai nếu cùng phục vụ một workload mà không có lợi ích rõ.

### 4.4. SP-GiST có thể hỗ trợ lossy

SP-GiST không bảo đảm mọi operator class là index exact không cần recheck. Biểu diễn leaf có thể đầy đủ hoặc tóm tắt; executor sẽ recheck khi cơ chế yêu cầu. Vì vậy **không khẳng định “SP-GiST không bao giờ lossy”**.

---

## 5. So sánh GiST và SP-GiST theo cách chọn thực tế

| Tiêu chí | GiST | SP-GiST |
|---|---|---|
| Hạ tầng | Generalized Search Tree | Space-Partitioned GiST |
| Trực giác | Cây key tổng hợp/vùng bao, các nhánh có thể chồng lấn | Cây phân chia không gian/prefix thành nhánh |
| Cấu trúc | Balanced tree framework | Non-balanced partitioned tree framework |
| Hình học | Point, box, polygon, circle qua opclass phù hợp | Point, box, polygon qua opclass sẵn có |
| Range | Có `range_ops` | Có `range_ops` |
| Multirange | Có `multirange_ops` trong PostgreSQL hiện đại | Không mặc định giả định có opclass multirange tương ứng |
| Địa chỉ mạng | `inet_ops` hỗ trợ qua explicit opclass | Có `inet_ops` |
| Text | Có opclass cho full-text `tsvector` và extension `pg_trgm` | Có `text_ops` cho các toán tử text/prefix phù hợp |
| KNN | Có với opclass cung cấp distance ordering | Có với một số opclass hỗ trợ, như point |
| Exclusion constraint | Phổ biến, hỗ trợ kết hợp qua `btree_gist` | Phụ thuộc tập operator/opclass hỗ trợ; GiST là lựa chọn chuẩn trong ví dụ |
| Mở rộng | Support functions của GiST | Support functions phân vùng của SP-GiST |
| “Nhanh nhất” | Không thể kết luận trước | Không thể kết luận trước |

**Chú ý:** GiST hỗ trợ `circle_ops` và `tsvector_ops` trong core PostgreSQL, nhưng không nên chuyển tất cả những trường hợp đó sang SP-GiST. Danh sách hỗ trợ thực tế do operator classes và phiên bản quyết định.

---

## 6. Kiểu dữ liệu và toán tử: bảng định hướng

| Data type / bài toán | Ví dụ predicate | Chỉ mục ứng viên | Lưu ý |
|---|---|---|---|
| `point` trong `box` | `location <@ box ...` | GiST, SP-GiST point opclasses | Tìm vùng địa lý mặt phẳng |
| `point` nearest neighbors | `ORDER BY location <-> point ... LIMIT 10` | GiST, SP-GiST point | Cần distance-ordering opclass |
| `box`, `polygon` giao nhau | `area && query_area` | GiST, SP-GiST theo kiểu | Có thể lossy/recheck |
| `circle` | Giao/bao hình tròn với toán tử phù hợp | GiST core | Không mặc định SP-GiST circle |
| `daterange` / `tsrange` / `tstzrange` | `period && requested_period` | GiST, SP-GiST range | Xem bounds [), rỗng, infinity |
| `int4range` / `numrange` | `range_col @> element` | GiST, SP-GiST range | Sắp xếp B-tree không thay overlap |
| `multirange` | `periods && query_range` | GiST multirange_ops | Kiểm tra phiên bản |
| `inet` / `cidr` | `address <<= network` | SP-GiST inet_ops hoặc GiST inet_ops | GiST inet_ops cần chỉ định tường minh |
| `text` prefix | `name ^@ 'pre'` | SP-GiST text_ops | Không tự hiểu là ILIKE/fuzzy |
| `text` fuzzy / trigram | `name % 'search'` hoặc `LIKE '%term%'` | GiST gist_trgm_ops, GIN gin_trgm_ops | Cần extension pg_trgm |
| `tsvector` full-text | `search_vector @@ tsquery` | GiST tsvector_ops hoặc GIN | GIN thường được xem xét nhiều cho FTS |
| `geometry` trong PostGIS | `ST_Intersects` / `ST_DWithin` | GiST/PostGIS opclass và tùy khả năng SP-GiST | Geometry là kiểu của extension, không phải built-in point |

Một index hỗ trợ **toán tử cụ thể**, không tự động tối ưu mọi biểu thức gọi hàm tùy ý. Query sai hình thức, cast/collation không tương thích hoặc predicate không dùng operator của opclass có thể khiến planner bỏ qua index.

---

## 7. Bài thực hành: xây bộ dữ liệu địa điểm

Tạo một schema độc lập. Dữ liệu điểm được hiểu là **tọa độ mặt phẳng**, không phải kinh/vĩ độ thực tế:

~~~sql
CREATE SCHEMA IF NOT EXISTS index_lab;

CREATE TABLE index_lab.places (
    place_id BIGINT PRIMARY KEY,
    place_name TEXT NOT NULL,
    location POINT NOT NULL,
    category TEXT NOT NULL
);

INSERT INTO index_lab.places
    (place_id, place_name, location, category)
VALUES
    (1, 'Cafe A',  point '(1,1)',  'cafe'),
    (2, 'Cafe B',  point '(2,3)',  'cafe'),
    (3, 'Park C',  point '(4,4)',  'park'),
    (4, 'Shop D',  point '(8,2)',  'shop'),
    (5, 'Office E',point '(11,8)', 'office'),
    (6, 'Park F',  point '(3,7)',  'park'),
    (7, 'Cafe G',  point '(6,6)',  'cafe'),
    (8, 'Shop H',  point '(-2,3)', 'shop'),
    (9, 'Office I',point '(0,-1)', 'office'),
    (10,'Park J',  point '(9,9)',  'park');

SELECT
    place_id, place_name, location, category
FROM index_lab.places
ORDER BY place_id;
~~~

> Chỉ INSERT một lần vào bảng lab trống. Nếu bảng đã tồn tại và có dữ liệu, dùng database/schema lab mới hoặc dọn dữ liệu theo quy trình kiểm soát; không chạy `DROP TABLE CASCADE` trên bảng không thuộc quyền sở hữu.

### 7.1. Thao tác toán học cơ bản

Khoảng cách Euclid giữa điểm A và B:

\[
d(A,B)=\sqrt{(x_A-x_B)^2+(y_A-y_B)^2}
\]

Trong PostgreSQL, `<->` cho `point` có thể tính khoảng cách Euclid trên tọa độ phẳng:

~~~sql
SELECT
    place_id,
    place_name,
    location,
    location <-> point '(2,2)' AS distance_to_target
FROM index_lab.places
ORDER BY distance_to_target, place_id;
~~~

Với dữ liệu thật là kinh/vĩ độ Trái Đất, **không** mặc định dùng khoảng cách Euclid trên độ kinh/vĩ; cần hệ quy chiếu, phép đo phù hợp và thường dùng PostGIS/geography/geometry trong CRS thích hợp.

### 7.2. Query điểm nằm trong hình hộp

~~~sql
SELECT
    place_id, place_name, location
FROM index_lab.places
WHERE location <@ box '((0,0),(5,5))'
ORDER BY place_id;
~~~

Toán tử `<@` trong ngữ cảnh `point, box` nghĩa là **điểm nằm trong hộp**. Query dự kiến trả các điểm trong vùng tọa độ x từ 0 đến 5 và y từ 0 đến 5.

Đọc kỹ thứ tự kiểu đối số: `point <@ box` khác câu hỏi “box chứa polygon” hoặc “range chứa timestamp”. **Một biểu tượng toán tử có thể có overload theo type.**

---

## 8. GiST trên kiểu point

### 8.1. Tạo index

~~~sql
CREATE INDEX idx_places_location_gist
ON index_lab.places
USING gist (location);
~~~

Với `point`, GiST có `point_ops` built-in phù hợp để hỗ trợ những toán tử không gian/định vị có trong operator class.

### 8.2. Dùng với predicate vùng

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT place_id, place_name, location
FROM index_lab.places
WHERE location <@ box '((0,0),(5,5))';
~~~

Khi bảng đủ lớn và điều kiện đủ chọn lọc, planner có thể dùng index scan/bitmap scan. Nhưng bảng 10 hàng thường quá nhỏ: `Seq Scan` có thể rẻ hơn, và đó không phải bằng chứng GiST bị lỗi.

### 8.3. KNN với ORDER BY trực tiếp

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    place_id, place_name, location,
    location <-> point '(2,2)' AS distance
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 5;
~~~

Khi optimizer sử dụng GiST nearest-neighbor, kế hoạch có thể chứa dạng:

~~~text
Index Scan using idx_places_location_gist ...
  Order By: (location <-> '(2,2)'::point)
~~~

Dòng này chỉ là **dạng minh họa**, không phải kế hoạch được bảo đảm. Để đảm bảo thứ tự hiển thị ổn định khi có điểm cùng khoảng cách, có thể thêm khóa phụ `place_id` ở ORDER BY ngoài, nhưng phải kiểm tra kế hoạch vì planner có thể cần bước sắp xếp bổ sung.

### 8.4. Vì sao ORDER BY distance không luôn là KNN index scan?

~~~sql
SELECT ...
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 5;
~~~

Có cơ hội tận dụng distance-ordering operator class. Tuy nhiên:

- `ORDER BY sqrt(pow(...))` không phải cùng operator expression để planner tự nhận KNN.
- Tham số nằm trong một cấu trúc không được planner coi là pseudoconstant có thể ảnh hưởng index ordering.
- Dataset quá nhỏ hoặc LIMIT gần số hàng có thể khiến sort toàn bộ rẻ hơn.
- Operator class của index phải hỗ trợ toán tử `<->` với đúng kiểu.
- Các điều kiện lọc và phép join có thể thay đổi access path tối ưu.

Thực hành tốt là **đọc EXPLAIN**, không chỉ nhìn thấy chữ `<->` trong SQL và kết luận đã dùng index.

---

## 9. SP-GiST trên point: quadtree và k-d tree

### 9.1. SP-GiST mặc định cho point

~~~sql
CREATE INDEX idx_places_location_spgist_quad
ON index_lab.places
USING spgist (location);
~~~

Với PostgreSQL hiện đại, `quad_point_ops` là operator class SP-GiST mặc định cho `point`.

Tương đương tường minh:

~~~sql
CREATE INDEX idx_places_location_spgist_quad_explicit
ON index_lab.places
USING spgist (location quad_point_ops);
~~~

**Không cần giữ cả hai index quad** trên cùng cột; hai lệnh được đưa ra để chỉ rõ cú pháp. Nếu đã tạo một index quad, lệnh còn lại chỉ nên xem là ví dụ chứ không nhất thiết thực thi.

### 9.2. Một biến thể k-d tree

~~~sql
CREATE INDEX idx_places_location_spgist_kd
ON index_lab.places
USING spgist (location kd_point_ops);
~~~

Hai operator classes point của SP-GiST là ứng viên để so sánh theo:

- Phân bố tọa độ.
- Tỷ lệ dữ liệu trùng lặp/cluster.
- Selectivity của vùng tìm kiếm.
- Tần suất cập nhật và insert.
- Kết quả KNN/region query.
- Kích thước index và số buffer đọc.

Không tuyên bố `kd_point_ops` luôn nhanh hơn `quad_point_ops` hoặc ngược lại.

### 9.3. Region query và KNN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT place_id, place_name
FROM index_lab.places
WHERE location <@ box '((0,0),(5,5))';
~~~

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT place_id, place_name
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 3;
~~~

Cả GiST point và SP-GiST `quad_point_ops`/`kd_point_ops` đều có thể hỗ trợ những truy vấn này, nhưng **planner chọn một index hoặc Seq Scan dựa trên chi phí**. Khi nhiều index cùng phục vụ một query, bạn không thể suy ra “đang benchmark SP-GiST” chỉ từ việc đã tạo SP-GiST; phải đọc dòng `Index Scan using ...` của kế hoạch.

### 9.4. Thử không ép production

Trong lab có thể tạo dữ liệu đủ lớn, `ANALYZE` và so sánh hai cấu hình index **trong môi trường riêng**. Không nên bật `enable_seqscan=off` ở hệ thống thật để cưỡng ép dùng GiST/SP-GiST: điều đó làm sai góc nhìn về hiệu quả của planner. Nếu dùng tạm để minh họa plan, đặt trong transaction hoặc session lab và khôi phục trạng thái ngay.

---

## 10. Box, polygon, circle: “hình học” không phải một loại chung

PostgreSQL core có các geometric types như `point`, `box`, `polygon`, `circle`. Chúng không giống `geometry`/`geography` của extension PostGIS.

### 10.1. GiST cho box

~~~sql
CREATE TABLE index_lab.regions (
    region_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    bounds BOX NOT NULL
);

INSERT INTO index_lab.regions(region_id, name, bounds)
VALUES
    (1, 'Center', box '((0,0),(5,5))'),
    (2, 'East',   box '((4,1),(9,7))'),
    (3, 'North',  box '((1,6),(6,10))'),
    (4, 'Remote', box '((20,20),(25,25))');

CREATE INDEX idx_regions_bounds_gist
ON index_lab.regions USING gist(bounds);
~~~

Tìm các region giao vùng truy vấn:

~~~sql
SELECT region_id, name, bounds
FROM index_lab.regions
WHERE bounds && box '((3,3),(7,8))'
ORDER BY region_id;
~~~

`&&` là toán tử **overlap** trong ngữ cảnh `box, box`. Để hiểu chính xác “overlap” với ranh giới chạm cạnh, cần đối chiếu semantics của kiểu hình học và toán tử tương ứng; không áp tùy tiện quy tắc khoảng thời gian dạng `[)` cho hình hộp.

### 10.2. SP-GiST cho box và polygon

~~~sql
CREATE INDEX idx_regions_bounds_spgist
ON index_lab.regions USING spgist(bounds);
~~~

Trong PostgreSQL hiện đại, built-in `box_ops` và `poly_ops` của SP-GiST hỗ trợ những toán tử quan hệ không gian như `&&`, `@>`, `<@` và có distance-ordering cho một số cặp kiểu.

### 10.3. Native circle

GiST có built-in operator class `circle_ops`. Ví dụ:

~~~sql
CREATE TABLE index_lab.coverage_areas (
    area_id INTEGER PRIMARY KEY,
    coverage CIRCLE NOT NULL
);

INSERT INTO index_lab.coverage_areas(area_id, coverage)
VALUES
    (1, circle '<(2,2),3>'),
    (2, circle '<(10,10),2>');

CREATE INDEX idx_coverage_circle_gist
ON index_lab.coverage_areas USING gist (coverage);
~~~

Mục tiêu là query quan hệ circle bằng những toán tử mà `circle_ops` hỗ trợ. **Không mặc định `USING spgist(coverage)` sẽ chạy**, vì không phải mọi operator class GiST đều có bản tương đương SP-GiST.

### 10.4. Polygon thực tế và false positives

Với vùng không lồi hoặc đa giác phức tạp, bounding approximation có thể chọn nhiều candidate hơn số đối tượng thực sự thỏa điều kiện. Executor có thể recheck. Khi diễn giải truy vấn hình học:

- Phân biệt bounding-box intersection với geometric intersection chính xác.
- Đọc toán tử được dùng trong WHERE.
- Đọc `Recheck Cond` và `Rows Removed by Index Recheck` trong EXPLAIN nếu xuất hiện.
- Không coi chỉ số có cùng hai ký tự `&&` trên mọi extension có semantics hoàn toàn giống nhau.

---

## 11. Range types: các kiểu dữ liệu phù hợp cho overlap và containment

Nhiều bài toán về lịch và đặt chỗ nên dùng **range type** thay vì lưu hai timestamp mà không biểu diễn rõ quy tắc khoảng.

PostgreSQL có các range types built-in như:

- `int4range`, `int8range`.
- `numrange`.
- `daterange`.
- `tsrange` cho timestamp không múi giờ.
- `tstzrange` cho timestamptz.

### 11.1. Các toán tử range phổ biến

| Toán tử | Ý nghĩa ví dụ |
|---|---|
| `a && b` | Hai range **giao nhau** |
| `a @> b` | Range a **chứa** phần tử hoặc range b |
| `a <@ b` | Range a **nằm trong** range b |
| `a -|- b` | Hai range **liền kề** không giao nhau |
| `a = b` | Hai range bằng nhau theo semantics của kiểu |
| `lower(a)` / `upper(a)` | Lấy cận dưới/trên khi có |
| `isempty(a)` | Kiểm tra range rỗng |

### 11.2. Bounds [) và tính đúng đắn lịch đặt phòng

Range:

~~~sql
SELECT daterange(
    DATE '2026-04-10',
    DATE '2026-04-13',
    '[)'
) AS booking_days;
~~~

`[)` nghĩa là **bao gồm cận đầu và loại trừ cận cuối**; đây là quy ước hữu ích cho lịch đặt chỗ: checkout ngày 13/04 không chiếm ngày 13/04.

Ví dụ:

~~~sql
SELECT
    daterange(DATE '2026-04-10', DATE '2026-04-13', '[)')
    &&
    daterange(DATE '2026-04-13', DATE '2026-04-15', '[)')
    AS overlaps;
~~~

Kết quả là **false** trong trường hợp hai khoảng liền kề này. Nếu sử dụng bounds khác hoặc timestamp nghiệp vụ khác, kết quả có thể khác; phải định nghĩa đúng “chạm ranh giới” trong quy tắc đặt lịch.

### 11.3. Tạo bảng lịch đặt phòng

~~~sql
CREATE TABLE index_lab.reservations (
    reservation_id BIGINT PRIMARY KEY,
    room_id INTEGER NOT NULL,
    guest_name TEXT NOT NULL,
    stay DATERANGE NOT NULL,
    CHECK (NOT isempty(stay))
);

INSERT INTO index_lab.reservations
    (reservation_id, room_id, guest_name, stay)
VALUES
    (1, 101, 'Guest A',
        daterange(DATE '2026-04-01', DATE '2026-04-04', '[)')),
    (2, 101, 'Guest B',
        daterange(DATE '2026-04-05', DATE '2026-04-08', '[)')),
    (3, 102, 'Guest C',
        daterange(DATE '2026-04-02', DATE '2026-04-07', '[)')),
    (4, 102, 'Guest D',
        daterange(DATE '2026-04-09', DATE '2026-04-11', '[)'));
~~~

### 11.4. GiST index cho range

~~~sql
CREATE INDEX idx_reservations_stay_gist
ON index_lab.reservations USING gist (stay);
~~~

Truy vấn có overlap:

~~~sql
SELECT
    reservation_id, room_id, guest_name, stay
FROM index_lab.reservations
WHERE stay && daterange(
    DATE '2026-04-03',
    DATE '2026-04-06',
    '[)'
)
ORDER BY room_id, reservation_id;
~~~

GiST `range_ops` có thể hỗ trợ `&&` và `@>` cùng các toán tử range khác. Query kết quả phụ thuộc mọi phòng; muốn kiểm tra **một phòng** thì thêm `WHERE room_id=...`. Nếu bảng lớn và lọc room_id cùng range, cân nhắc thiết kế index kết hợp/constraint thích hợp.

### 11.5. SP-GiST index cho range

~~~sql
CREATE INDEX idx_reservations_stay_spgist
ON index_lab.reservations USING spgist (stay);
~~~

SP-GiST cũng có `range_ops` cho **range types** trong PostgreSQL hiện đại. Kiểu predicate `stay && requested_range` có thể được hỗ trợ bởi cả hai.

Một chỉ mục SP-GiST range không tự biến dữ liệu thành unique hoặc đảm bảo không trùng lịch đặt phòng; **nó chỉ giúp truy vấn nhanh hơn** khi planner chọn sử dụng.

### 11.6. Containment

~~~sql
SELECT reservation_id, room_id, stay
FROM index_lab.reservations
WHERE stay @> DATE '2026-04-03'
ORDER BY room_id, reservation_id;
~~~

`stay @> DATE` hỏi “đơn đặt phòng này bao trùm ngày 03/04 không?”. GiST và SP-GiST range opclasses đều có thể hỗ trợ phép chứa element với đúng kiểu đối số.

---

## 12. Multirange: không mặc định SP-GiST hỗ trợ giống range

Multirange biểu diễn một tập các khoảng rời nhau theo cùng miền giá trị, hữu ích cho lịch làm việc không liên tục, phân đoạn giá hoặc danh sách cửa sổ thời gian.

Trong PostgreSQL hiện đại:

~~~sql
SELECT datemultirange(
    daterange(DATE '2026-04-01', DATE '2026-04-03', '[)'),
    daterange(DATE '2026-04-07', DATE '2026-04-09', '[)')
) AS available_periods;
~~~

GiST có built-in `multirange_ops` cho các toán tử phù hợp với multirange. Ví dụ:

~~~sql
CREATE TABLE index_lab.availability (
    employee_id INTEGER PRIMARY KEY,
    available_days DATEMULTIRANGE NOT NULL
);

INSERT INTO index_lab.availability(employee_id, available_days)
VALUES (
    1,
    datemultirange(
        daterange(DATE '2026-04-01', DATE '2026-04-03', '[)'),
        daterange(DATE '2026-04-07', DATE '2026-04-09', '[)')
    )
);

CREATE INDEX idx_availability_gist
ON index_lab.availability USING gist (available_days);
~~~

Tìm lịch có ít nhất một phần giao với một range:

~~~sql
SELECT employee_id, available_days
FROM index_lab.availability
WHERE available_days &&
      daterange(DATE '2026-04-08', DATE '2026-04-10', '[)');
~~~

**Không suy từ việc SP-GiST có `range_ops` rằng nó mặc định hỗ trợ trực tiếp `datemultirange`**. Kiểm tra `pg_opclass` và bảng built-in operator classes của phiên bản đang dùng; khi không có opclass thích hợp, `CREATE INDEX ... USING spgist (available_days)` sẽ không hợp lệ.

---

## 13. Mạng IP: inet, cidr và phép chứa subnet

### 13.1. Không coi địa chỉ IP như text bất kỳ

PostgreSQL có các kiểu `inet` và `cidr` để biểu diễn địa chỉ và tiền tố mạng. Với kiểu này, các phép toán như “mạng A nằm trong mạng B” có semantics chuyên biệt; nếu lưu IP dưới dạng `text` rồi dùng `LIKE '10.%'`, truy vấn không diễn đạt đúng logic CIDR và dễ sai.

Một số toán tử thường gặp:

| Toán tử | Ý nghĩa với mạng |
|---|---|
| `a << b` | a nằm trong mạng b, **strictly contained** |
| `a <<= b` | a nằm trong hoặc bằng mạng b |
| `a >> b` | a chứa b theo nghĩa strict |
| `a >>= b` | a chứa hoặc bằng b |
| `a && b` | Mạng có vùng địa chỉ giao nhau |

### 13.2. Tạo bảng IP lab

~~~sql
CREATE TABLE index_lab.network_rules (
    rule_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    network INET NOT NULL
);

INSERT INTO index_lab.network_rules(rule_id, label, network)
VALUES
    (1, 'Office subnet',  inet '10.10.0.0/16'),
    (2, 'VPN subnet',     inet '10.20.0.0/16'),
    (3, 'Office host A',  inet '10.10.2.15'),
    (4, 'Office host B',  inet '10.10.8.99'),
    (5, 'Public host',    inet '203.0.113.8'),
    (6, 'Private range',  inet '192.168.0.0/16');

SELECT rule_id, label, network
FROM index_lab.network_rules
ORDER BY rule_id;
~~~

### 13.3. SP-GiST inet_ops

~~~sql
CREATE INDEX idx_network_rules_spgist
ON index_lab.network_rules USING spgist (network inet_ops);
~~~

Tìm các giá trị mạng/host nằm bên trong một mạng con:

~~~sql
SELECT rule_id, label, network
FROM index_lab.network_rules
WHERE network <<= inet '10.10.0.0/16'
ORDER BY rule_id;
~~~

Kỳ vọng theo dữ liệu mẫu gồm mạng văn phòng và hai host văn phòng. `<<=` là operator mà SP-GiST `inet_ops` hỗ trợ, nhưng bảng nhỏ có thể vẫn được seq scan.

### 13.4. GiST inet_ops phải được chọn tường minh

Trong bộ core operator classes của PostgreSQL, `inet_ops` của GiST **không phải default class cho `inet`/`cidr`**. Chỉ định opclass:

~~~sql
CREATE INDEX idx_network_rules_gist
ON index_lab.network_rules USING gist (network inet_ops);
~~~

Đây là ví dụ hữu ích cho bài học: **chọn access method không đủ nếu opclass mặc định của type không thích hợp**.

### 13.5. Cùng kiểu dữ liệu, nhiều lựa chọn index

Với IP được so sánh equality, B-tree có thể đã phù hợp. GiST/SP-GiST nên được cân nhắc nếu query phổ biến là quan hệ **subnet containment/overlap**; đánh giá selectivity, kích thước bảng và tốc độ cập nhật.

Đừng lưu địa chỉ và subnet không chuẩn hóa, hoặc truyền các chuỗi input chưa được xác minh vào SQL ghép chuỗi; dùng prepared statements/cast kiểu `inet` và xử lý lỗi định dạng phù hợp.

---

## 14. SP-GiST trên text: prefix và các toán tử phù hợp

### 14.1. text_ops của SP-GiST không phải trigram index

SP-GiST `text_ops` hỗ trợ các phép so sánh văn bản theo operator class và toán tử prefix `^@`:

~~~sql
CREATE TABLE index_lab.keywords (
    keyword_id BIGINT PRIMARY KEY,
    term TEXT NOT NULL
);

INSERT INTO index_lab.keywords(keyword_id, term)
VALUES
    (1, 'postgres'),
    (2, 'postgresql'),
    (3, 'postgis'),
    (4, 'postcard'),
    (5, 'index'),
    (6, 'instant'),
    (7, 'spgist'),
    (8, 'spatial');

CREATE INDEX idx_keywords_spgist_text
ON index_lab.keywords USING spgist (term text_ops);
~~~

Tìm những chuỗi bắt đầu bằng prefix:

~~~sql
SELECT keyword_id, term
FROM index_lab.keywords
WHERE term ^@ 'post'
ORDER BY term;
~~~

`^@` là phép kiểm tra “starts with” (phân biệt chữ hoa/thường theo semantics của toán tử). Nó là câu hỏi **prefix**, không phải fuzzy similarity.

### 14.2. Prefix khác ILIKE và tìm chuỗi con

| Predicate | Ý nghĩa | Opclass thường cân nhắc |
|---|---|---|
| `term ^@ 'post'` | Bắt đầu bằng `post` | SP-GiST `text_ops` |
| `term LIKE 'post%'` | Pattern tiền tố | B-tree với pattern opclass/collation phù hợp; pg_trgm khi cần |
| `term ILIKE '%post%'` | Chuỗi con không phân biệt hoa thường | `pg_trgm` GiST/GIN |
| `term % 'postgre'` | Trigram similarity (cần pg_trgm) | `gist_trgm_ops` hoặc `gin_trgm_ops` |
| `term = 'postgres'` | Equality | B-tree thường là lựa chọn chuẩn |

**Không khẳng định** `SP-GiST text_ops` sẽ tăng tốc mọi `LIKE`, `ILIKE` hay regex. Tập toán tử hỗ trợ được khai báo chính xác trong operator class.

### 14.3. Radix/prefix partitioning

Với text, SP-GiST có thể dùng chiến lược phân nhánh theo tiền tố/chuỗi, giống trực giác trie:

~~~text
root
 ├── "pos"
 │     ├── "tgres"
 │     ├── "tgresql"
 │     ├── "tcard"
 │     └── "tgis"
 ├── "in"
 │     ├── "dex"
 │     └── "stant"
 └── "sp"
       ├── "gist"
       └── "atial"
~~~

Sơ đồ chỉ minh họa cơ chế chia nhánh, **không phải bản vẽ chính xác của page/node do SP-GiST sinh ra**. Việc phân bố chuỗi và độ dài prefix có thể ảnh hưởng hiệu quả.

---

## 15. pg_trgm: GiST cho tìm kiếm chuỗi gần giống

### 15.1. Vì sao cần extension?

PostgreSQL core GiST không có sẵn opclass fuzzy-string `gist_trgm_ops` chỉ vì cột là text. Extension `pg_trgm` bổ sung các toán tử/hàm và opclass cho trigram similarity.

Trong môi trường có quyền phù hợp:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
~~~

Việc cài extension cần quyền đối với database và tuân thủ chính sách quản trị; PostgreSQL đã có sẵn `pg_trgm` trong bộ module được cung cấp, nhưng **không phải database nào cũng đã bật nó**.

### 15.2. Lập chỉ mục GiST trigram

~~~sql
CREATE INDEX idx_keywords_gist_trgm
ON index_lab.keywords
USING gist (term gist_trgm_ops);
~~~

Có thể tùy chỉnh kích thước chữ ký đối với opclass này, ví dụ:

~~~sql
CREATE INDEX idx_keywords_gist_trgm_sig32
ON index_lab.keywords
USING gist (term gist_trgm_ops(siglen=32));
~~~

**Hai lệnh là hai biến thể thử nghiệm**. Không mặc định giữ cả hai index trong production nếu chỉ phục vụ cùng workload. Chữ ký dài hơn thường làm index lớn hơn nhưng giảm false positives/recheck trong nhiều trường hợp.

### 15.3. Similarity với toán tử %

~~~sql
SELECT
    keyword_id,
    term,
    similarity(term, 'postgress') AS score
FROM index_lab.keywords
WHERE term % 'postgress'
ORDER BY score DESC, term;
~~~

`%` trong ngữ cảnh `pg_trgm` kiểm tra liệu similarity có vượt ngưỡng cấu hình `pg_trgm.similarity_threshold`. Kết quả phụ thuộc threshold và ngôn ngữ/dữ liệu, không bảo đảm một số lượng hàng cố định cho mọi môi trường.

Có thể thay đổi threshold **trong phạm vi session lab** khi cần thực hành:

~~~sql
SET pg_trgm.similarity_threshold = 0.3;
~~~

Không thay ngưỡng trên toàn database production chỉ để “cải thiện một truy vấn” mà chưa đánh giá ảnh hưởng của các truy vấn khác.

### 15.4. KNN theo khoảng cách trigram: GiST nổi bật

`pg_trgm` cung cấp `<->` cho **text–text**, nghĩa là khoảng cách dựa trên similarity; nó **không giống** khoảng cách Euclid `point–point` dù cùng ký hiệu.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    keyword_id,
    term,
    term <-> 'postgress' AS trigram_distance
FROM index_lab.keywords
ORDER BY term <-> 'postgress'
LIMIT 5;
~~~

GiST trigram có thể hỗ trợ chiến lược **KNN distance ordering** khi planner thấy phù hợp. Điểm khác biệt đáng nhớ: `GIN gin_trgm_ops` có thể hỗ trợ lọc similarity/pattern rất tốt, nhưng **không hỗ trợ cùng kiểu KNN order-by-distance trực tiếp** như GiST trigram.

### 15.5. LIKE '%...%' và trigrams

~~~sql
SELECT keyword_id, term
FROM index_lab.keywords
WHERE term ILIKE '%post%';
~~~

Index trigram GiST/GIN có thể hữu ích cho dạng substring search, nhưng nếu pattern quá ngắn hoặc không trích xuất được trigram hữu ích thì quá trình tìm kiếm có thể suy biến thành quét nhiều phần của index. Không chỉ thấy ký tự `%` rồi tin chắc index rất nhanh.

### 15.6. GiST và GIN cho text

| Nhu cầu | GiST trigram | GIN trigram |
|---|---|---|
| Tìm `LIKE/ILIKE/regex` có trigram hiệu quả | Có thể tốt | Có thể tốt |
| Similarity filter `%` | Hỗ trợ | Hỗ trợ |
| Top-k gần đúng theo `ORDER BY term <-> q LIMIT k` | **Có lợi thế KNN** | Không dùng cùng chiến lược KNN distance |
| Kích thước và chi phí update | Phụ thuộc signature/đặc điểm dữ liệu | Phụ thuộc inverted postings/fastupdate |
| "Luôn nhanh hơn" | Không | Không |

GiST trigram dùng signature có tính gần đúng, do đó **index recheck** là một chi tiết quan trọng. GIN có đặc điểm inverted index, và không phải lựa chọn tốt nhất cho mọi pattern/khối lượng ghi.

---

## 16. Full-text search: tsvector GiST và khi nào GIN thích hợp hơn

PostgreSQL full-text search dùng `tsvector` và `tsquery`. Có thể tạo:

~~~sql
CREATE TABLE index_lab.articles (
    article_id BIGINT PRIMARY KEY,
    body TEXT NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', body)
    ) STORED
);

INSERT INTO index_lab.articles(article_id, body)
VALUES
    (1, 'PostgreSQL GiST indexing'),
    (2, 'SP-GiST spatial partitioning'),
    (3, 'Generalized search trees and query plans'),
    (4, 'Database transactions and isolation');

CREATE INDEX idx_articles_gist_fts
ON index_lab.articles USING gist (search_vector);
~~~

Query:

~~~sql
SELECT article_id, body
FROM index_lab.articles
WHERE search_vector @@ to_tsquery('simple', 'indexing');
~~~

GiST có core `tsvector_ops` cho operator `@@`, với biểu diễn có thể mang tính chữ ký/lossy. Nhưng trong nhiều workload full-text search, **GIN** là ứng viên phổ biến cần benchmark:

~~~sql
CREATE INDEX idx_articles_gin_fts
ON index_lab.articles USING gin (search_vector);
~~~

Không xem GiST hay SP-GiST là cách duy nhất cho “text search”. SP-GiST `text_ops` cho prefix và GiST `tsvector_ops`/GIN `tsvector_ops` cho full-text phục vụ những kiểu predicate khác nhau.

### 16.1. Không nhầm "search text" với "search tsvector"

- `body ILIKE '%term%'`: substring theo string.
- `body % 'term'`: trigram similarity (cần pg_trgm).
- `search_vector @@ query`: full-text tokens/linguistic matching.
- `body ^@ 'prefix'`: starts-with theo text operator.

Chọn index dựa vào semantics mà sản phẩm cần, không vì cả bốn đều được gọi chung là “tìm kiếm”.

---

## 17. PostGIS: geometry và geography là kiểu do extension cung cấp

### 17.1. Native point không tự là PostGIS geometry

PostgreSQL core `point`/`box` là hệ hình học phẳng đơn giản. PostGIS mở rộng với:

- `geometry`: đối tượng hình học có SRID, nhiều kiểu shape và spatial operators.
- `geography`: thao tác trên trái đất với đơn vị/semantics thích hợp (tùy hàm/toán tử).
- Các toán tử/chiến lược GiST/khả năng SP-GiST tùy kiểu, version PostGIS/PostgreSQL.

Trên database có quyền và đã cài extension ở server:

~~~sql
CREATE EXTENSION IF NOT EXISTS postgis;
~~~

**Không bắt buộc cài PostGIS** cho các bài thực hành native point/range/inet trong phần trước. Nếu không được cấp quyền hoặc extension không tồn tại trên server, sử dụng lab core như bình thường.

### 17.2. Ví dụ PostGIS minh họa

~~~sql
-- Chỉ chạy khi extension postgis đã được bật.
CREATE TABLE index_lab.geo_places (
    place_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    geom geometry(Point, 4326) NOT NULL
);

CREATE INDEX idx_geo_places_gist
ON index_lab.geo_places USING gist (geom);
~~~

Ví dụ tìm trong bán kính:

~~~sql
SELECT place_id, name
FROM index_lab.geo_places
WHERE ST_DWithin(
    geom,
    ST_SetSRID(ST_MakePoint(106.7, 10.8), 4326),
    0.01
);
~~~

**Cực kỳ quan trọng:** `geometry(Point,4326)` dùng tọa độ kinh/vĩ **đơn vị độ**. Ngưỡng `0.01` trong ví dụ cũng là **độ**, **không phải 10 mét hoặc 1 km**. Nếu cần khoảng cách mét, dùng `geography` hoặc phép biến đổi sang hệ tọa độ metric phù hợp và hiểu quy tắc tính distance.

### 17.3. Spatial index hỗ trợ điều kiện nào?

PostGIS có nhiều hàm như `ST_Intersects`, `ST_Contains`, `ST_DWithin` và toán tử bounding box. Việc query có thể tận dụng index phụ thuộc:

- Operator class của kiểu geometry/geography.
- Cách hàm được implement, có index-aware hay không.
- SRID của hai đối tượng và phép transform.
- Predicate, constant expression, cast.
- Kích thước dữ liệu, filter và statistics.

Không tự viết `ST_Distance(geom, query) < radius` rồi giả định chắc chắn tương đương index-assisted `ST_DWithin` ở mức plan. Khi mục tiêu là lọc khoảng cách, ưu tiên hình thức hàm index-aware và xác minh EXPLAIN trên môi trường cụ thể.

### 17.4. GiST so với SP-GiST cho PostGIS

Một số phiên bản PostGIS cung cấp hỗ trợ SP-GiST cho một số kiểu/chiến lược hình học. Nhưng **không kết luận** mọi toán tử PostGIS được hỗ trợ giống nhau bởi cả GiST và SP-GiST.

Kiểm tra operator classes đang được cài trong database:

~~~sql
SELECT
    am.amname,
    opc.opcname,
    opc.opcintype::regtype AS data_type
FROM pg_opclass AS opc
JOIN pg_am AS am
  ON am.oid = opc.opcmethod
WHERE am.amname IN ('gist', 'spgist')
  AND opc.opcname LIKE '%geometry%'
ORDER BY am.amname, opc.opcname;
~~~

So sánh các query thực (spatial predicate, distance ordering, độ chọn lọc, đối tượng phức tạp) trước khi chọn.

---

## 18. btree_gist và exclusion constraint chống đặt lịch trùng

### 18.1. Chỉ mục tăng tốc không tự bảo đảm tính duy nhất của khoảng

Nếu hai phiên đồng thời đặt cùng phòng và khoảng trùng, việc chỉ có:

~~~sql
CREATE INDEX idx_reservations_stay_gist
ON index_lab.reservations USING gist (stay);
~~~

không tự ngăn insert trùng lịch. Đây là một **index phục vụ truy vấn**, không phải constraint loại trừ.

### 18.2. EXCLUDE dùng GiST

PostgreSQL có exclusion constraints để biểu đạt quy tắc:

> Không tồn tại hai hàng mà **room_id bằng nhau** và **stay giao nhau**.

GiST là phương pháp rất phù hợp. Tuy nhiên kiểu integer `room_id` không tự có opclass GiST equality mặc định như B-tree. Extension `btree_gist` cung cấp những B-tree-like GiST operator classes cho nhiều kiểu scalar.

~~~sql
-- Cần quyền và extension btree_gist có sẵn trên server.
CREATE EXTENSION IF NOT EXISTS btree_gist;
~~~

Sau đó:

~~~sql
ALTER TABLE index_lab.reservations
ADD CONSTRAINT no_overlapping_stays_for_room
EXCLUDE USING gist (
    room_id WITH =,
    stay WITH &&
);
~~~

Constraint yêu cầu rằng với **bất kỳ hai hàng khác nhau**, không thể đồng thời có `room_id = room_id` và `stay && stay` đều true. PostgreSQL xây index hỗ trợ constraint và phối hợp cả với các giao dịch ghi đồng thời; một simple SELECT kiểm tra trùng trước INSERT **không có bảo đảm tương đương**.

### 18.3. Ví dụ vi phạm

Nếu `reservation_id=1` đang giữ phòng 101 trong `[2026-04-01,2026-04-04)`, lệnh:

~~~sql
INSERT INTO index_lab.reservations
    (reservation_id, room_id, guest_name, stay)
VALUES (
    100, 101, 'Conflicting booking',
    daterange(DATE '2026-04-02', DATE '2026-04-03', '[)')
);
~~~

sẽ không được chấp nhận khi constraint tồn tại, vì cùng phòng và khoảng giao nhau. Lỗi thuộc nhóm **exclusion violation** (SQLSTATE `23P01`).

### 18.4. Hai đặt chỗ liền nhau

~~~sql
INSERT INTO index_lab.reservations
    (reservation_id, room_id, guest_name, stay)
VALUES (
    101, 101, 'Adjacent booking',
    daterange(DATE '2026-04-04', DATE '2026-04-05', '[)')
);
~~~

Với bounds `[)`, khoảng mới tiếp giáp (không overlap) đặt chỗ 1 và không giao các khoảng còn lại của phòng 101 trong lab, nên hợp lệ **nếu các điều kiện/constraint khác đều thỏa**.

### 18.5. Hai lưu ý bổ sung

- Nếu room_id hoặc stay **NULL**, logic exclusion với kết quả UNKNOWN có thể không ngăn các cặp trùng theo cách bạn mong đợi. Dùng `NOT NULL` trên các thuộc tính nghiệp vụ bắt buộc.
- `btree_gist` **không tạo ra index UNIQUE B-tree thông thường**; extension giúp một số phép so sánh scalar dùng trong GiST, phù hợp exclusion. Đừng thay unique constraint đơn giản bằng exclusion chỉ vì đã cài extension.

---

## 19. GiST không phải GIN và SP-GiST không phải BRIN

### 19.1. B-tree

Phù hợp equality, range theo thứ tự, ORDER BY thông thường và UNIQUE/PRIMARY KEY trong nhiều ứng dụng.

### 19.2. GIN (Generalized Inverted Index)

Thường phù hợp các giá trị chứa **nhiều thành phần**:

- Arrays với overlap/containment.
- JSONB với những operator classes/queries phù hợp.
- Full-text tokens.
- Trigram index theo inverted postings.

GiST cũng có một số opclasses text/spatial hữu ích, nhưng không mặc định là lựa chọn thay GIN cho JSONB/array.

### 19.3. BRIN (Block Range Index)

Lưu tóm tắt vùng block; có lợi cho những bảng cực lớn khi dữ liệu vật lý **tương quan** với giá trị (ví dụ timestamp theo thứ tự insert). BRIN thường nhỏ nhưng có thể cần recheck nhiều hơn. Không dùng GiST/SP-GiST chỉ vì cột là timestamp; nếu query dạng `created_at >= ...` và dữ liệu append-only, B-tree hoặc BRIN cũng có thể phù hợp hơn.

### 19.4. Bảng lựa chọn nhanh

| Workload chủ đạo | Ứng viên đầu tiên nên xem xét |
|---|---|
| `customer_id = ?` | B-tree |
| `created_at BETWEEN ...` | B-tree, hoặc BRIN với dữ liệu tương quan và cực lớn |
| `jsonb_col @> '{"k":...}'` | GIN JSONB opclass phù hợp |
| `tags && ARRAY[...]` | GIN array opclass |
| `geometry ST_Intersects` | PostGIS GiST và opclass phù hợp |
| `point <@ box` | GiST hoặc SP-GiST point |
| `point ORDER BY point <-> q LIMIT 10` | GiST/SP-GiST point KNN |
| `daterange && daterange` | GiST/SP-GiST range |
| `inet <<= subnet` | SP-GiST/GiST inet_ops |
| `text ^@ prefix` | SP-GiST text_ops, benchmark B-tree prefix strategy |
| `text ILIKE '%keyword%'` | pg_trgm GiST/GIN |
| `text ORDER BY text <-> q LIMIT 10` | GiST pg_trgm KNN |
| `tsvector @@ tsquery` | GIN thường là lựa chọn đầu tiên; GiST cũng hỗ trợ |

Một ứng dụng có nhiều workload có thể cần **nhiều index bổ sung cho các predicate khác nhau**, nhưng mỗi index tăng chi phí ghi, VACUUM và dung lượng đĩa. Phải loại bỏ index trùng vai trò khi không có lợi ích rõ.

---

## 20. KNN: vì sao ORDER BY <-> là một trường hợp đặc biệt?

### 20.1. Top-k thay vì lọc tất cả rồi sort

Một query KNN điển hình:

~~~sql
SELECT place_id, place_name, location
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 5;
~~~

Trong kế hoạch phù hợp, index hỗ trợ **trả dần các candidate theo khoảng cách** để tìm top-k mà không cần tính khoảng cách mọi row rồi sort toàn bảng.

GiST và SP-GiST đều có thể hỗ trợ KNN, nhưng **không phải mọi operator class** cho cả hai phương pháp đều có distance ordering.

### 20.2. Không đồng nhất toán tử <-> ở mọi kiểu

| Toán tử | Ngữ cảnh | Ý nghĩa |
|---|---|---|
| `point <-> point` | Hình học core | Khoảng cách phẳng |
| `text <-> text` với `pg_trgm` | Trigram | Khoảng cách theo similarity |
| Một toán tử distance của extension | Tùy extension/opclass | Phải đọc tài liệu của chính opclass |

Trùng ký hiệu không đồng nghĩa cùng đơn vị, độ chính xác hoặc cách sắp xếp.

### 20.3. KNN trên kết quả JOIN

Với nhiều điểm mục tiêu khác nhau, có thể dùng `LATERAL` để mỗi target tìm vài điểm gần nhất:

~~~sql
WITH targets(target_id, q) AS (
    VALUES
        (1, point '(2,2)'),
        (2, point '(9,9)')
)
SELECT
    t.target_id,
    p.place_id,
    p.place_name,
    p.location <-> t.q AS distance
FROM targets AS t
CROSS JOIN LATERAL (
    SELECT place_id, place_name, location
    FROM index_lab.places AS p
    ORDER BY p.location <-> t.q
    LIMIT 3
) AS p
ORDER BY t.target_id, distance, p.place_id;
~~~

Query này là ví dụ truy vấn SQL có correlated parameter. Việc index KNN có được planner sử dụng hay không còn phụ thuộc kế hoạch/kiểu, và lab 10 hàng thường seq scan+sort rẻ hơn.

### 20.4. Tìm nearest trước rồi lọc có thể đổi kết quả

So sánh:

~~~sql
-- Lấy 3 cafe gần điểm q nhất:
SELECT place_id, place_name, location
FROM index_lab.places
WHERE category = 'cafe'
ORDER BY location <-> point '(2,2)'
LIMIT 3;
~~~

với:

~~~sql
-- Lấy 3 địa điểm gần nhất bất kể category,
-- rồi chỉ giữ cafe trong ba địa điểm đó:
SELECT *
FROM (
    SELECT place_id, place_name, category, location
    FROM index_lab.places
    ORDER BY location <-> point '(2,2)'
    LIMIT 3
) AS nearest_any
WHERE category = 'cafe';
~~~

Hai yêu cầu **khác nhau về nghiệp vụ**. Query thứ hai có thể trả ít hơn ba cafe dù còn cafe gần thứ tư. Đặt điều kiện WHERE **trước** LIMIT khi muốn top-k thỏa filter.

---

## 21. Lossy, exact và Recheck Cond trong EXPLAIN

### 21.1. Khi nào phải recheck?

Một số index lưu key tóm tắt, ví dụ:

- Bounding box bao polygon.
- Chữ ký trigram trong GiST pg_trgm.
- Dữ liệu nén/tổng hợp của một opclass.

Index có thể chỉ xác định “có khả năng khớp”. Khi opclass yêu cầu, executor kiểm tra lại predicate trên hàng thật để bỏ false positives.

### 21.2. Đọc plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT region_id, name
FROM index_lab.regions
WHERE bounds && box '((3,3),(7,8))';
~~~

Trong plan có thể thấy:

~~~text
Bitmap Heap Scan on regions
  Recheck Cond: (bounds && ...)
  Rows Removed by Index Recheck: ...
  -> Bitmap Index Scan on idx_regions_bounds_gist
       Index Cond: (bounds && ...)
~~~

**Đây là hình thức minh họa**, không phải kết quả chắc chắn. Lý do:

- Planner có thể chọn Seq Scan hoặc Index Scan.
- `Recheck Cond` trên Bitmap Heap Scan không tự chứng minh index operator class luôn lossy; bitmap heap scan có các điều kiện recheck riêng, đặc biệt khi bitmap page trở thành lossy do bộ nhớ.
- `Rows Removed by Index Recheck` khác 0 chỉ khi có candidate bị loại ở bước recheck.
- Một query với opclass exact có thể không có false positives.

### 21.3. Index-only scan có giới hạn

Không phải mọi GiST/SP-GiST index đều có khả năng **trả nguyên bản indexed value** để phục vụ index-only scan. Điều đó phụ thuộc opclass, cách lưu key, phiên bản và visibility map của bảng. Thêm `INCLUDE` không bảo đảm mọi truy vấn GiST/SP-GiST trở thành index-only scan.

### 21.4. False positives không đồng nghĩa kết quả sai

PostgreSQL không công bố candidate chưa được kiểm chứng như một row thỏa predicate chỉ vì index tóm tắt đánh dấu “có thể đúng”. Recheck là thành phần của **cơ chế bảo đảm kết quả chính xác**.

---

## 22. Vì sao PostgreSQL không chọn chỉ mục đã tạo?

### 22.1. Bảng quá nhỏ

Với 10 row, đọc cả heap có thể nhanh hơn đi qua index, fetch heap và lọc.

### 22.2. Predicate không khớp opclass

Ví dụ SP-GiST `text_ops` có hỗ trợ prefix operator `^@` nhưng không tự hỗ trợ mọi toán tử trigram. Một điều kiện chứa hàm tùy ý có thể không được biến đổi thành index qual.

### 22.3. Cast, expression hoặc collation

~~~sql
WHERE lower(term) = 'postgres'
~~~

không nhất thiết dùng index trên `term` nguyên bản. Nếu workload cần expression, cân nhắc index theo biểu thức và operator class phù hợp, ví dụ B-tree `lower(term)` khi mục tiêu equality sau chuẩn hóa. Đừng tự dùng GiST vì thấy có function trong WHERE.

### 22.4. Selectivity thấp

Một vùng query bao phủ hầu hết điểm hoặc range overlap gần như mọi lịch đặt có thể khiến Seq Scan hợp lý hơn.

### 22.5. Giới hạn ORDER BY

KNN index scan cần biểu thức order-by distance phù hợp operator class, thường với một đối tượng query được coi là cố định trong ngữ cảnh index scan. ORDER BY do biểu thức tùy ý tính sau có thể buộc sort.

### 22.6. Dữ liệu thống kê chưa được cập nhật

Sau bulk load lớn, chạy:

~~~sql
ANALYZE index_lab.places;
ANALYZE index_lab.reservations;
ANALYZE index_lab.keywords;
~~~

Đọc EXPLAIN; `ANALYZE` cập nhật thống kê, không tạo/ép planner dùng index.

### 22.7. Chi phí đọc/ghi và cấu hình

Planner tính cả heap access, random I/O, selectivity, số hàng, LIMIT và các tham số chi phí. Khi query có nhiều index ứng viên, nó có thể chọn một index khác. Muốn so sánh công bằng, cần biết **index nào thật sự được dùng** trong kế hoạch.

---

## 23. Thực hành EXPLAIN, thống kê và kích thước index

### 23.1. Quan sát kế hoạch mà không thực thi

~~~sql
EXPLAIN
SELECT place_id, place_name
FROM index_lab.places
WHERE location <@ box '((0,0),(5,5))';
~~~

`EXPLAIN` không có `ANALYZE` chỉ lập kế hoạch, không thực thi SELECT để đo runtime.

### 23.2. EXPLAIN ANALYZE có thực thi

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT place_id, place_name
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 5;
~~~

Với SELECT lab, thao tác này thích hợp để học. Nhưng nếu gắn `ANALYZE` vào DML như INSERT/UPDATE/DELETE, câu lệnh sẽ **thực sự thay đổi dữ liệu** trừ khi được rollback trong transaction lab. Không chạy thử trên production khi thiếu quyền và kế hoạch.

### 23.3. Kiểm tra các index hiện có

~~~sql
SELECT
    schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'index_lab'
ORDER BY tablename, indexname;
~~~

### 23.4. Tìm index opclass và access method qua catalog

~~~sql
SELECT
    i.relname AS index_name,
    am.amname AS access_method,
    t.relname AS table_name,
    pg_get_indexdef(i.oid) AS index_definition
FROM pg_class AS i
JOIN pg_index AS ix ON ix.indexrelid = i.oid
JOIN pg_class AS t ON t.oid = ix.indrelid
JOIN pg_am AS am ON am.oid = i.relam
JOIN pg_namespace AS n ON n.oid = t.relnamespace
WHERE n.nspname = 'index_lab'
ORDER BY table_name, index_name;
~~~

### 23.5. Kích thước index

~~~sql
SELECT
    c.relname AS index_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS index_size,
    pg_relation_size(c.oid) AS bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'index_lab'
  AND c.relkind IN ('i', 'I')
ORDER BY bytes DESC, index_name;
~~~

Một index có thể lớn hơn index khác nhưng query nhanh hơn, hoặc ngược lại. Không chọn chỉ vì dung lượng nhỏ mà bỏ qua build time, update cost và latency.

### 23.6. Thống kê sử dụng index

~~~sql
SELECT
    schemaname, relname, indexrelname,
    idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'index_lab'
ORDER BY relname, indexrelname;
~~~

Các con số là **counters thống kê**, phụ thuộc thời điểm reset và workload. `idx_scan = 0` ngay sau khi tạo index trong lab không chứng minh index vô dụng về dài hạn; planner có thể chưa có query thích hợp hoặc bảng quá nhỏ.

---

## 24. Tạo index trên bảng lớn: khóa và vận hành

### 24.1. CREATE INDEX thường

~~~sql
CREATE INDEX idx_large_points_gist
ON index_lab.places USING gist (location);
~~~

Cú pháp ví dụ; nếu đã có index cùng tên, không chạy lại. `CREATE INDEX` thường trên bảng lớn có thể **chặn DML** trên bảng trong lúc xây index. Một câu CREATE chạy nhanh ở lab không phản ánh tác động production.

### 24.2. CREATE INDEX CONCURRENTLY

Trên bảng lớn đang nhận ghi, có thể cân nhắc:

~~~sql
CREATE INDEX CONCURRENTLY idx_places_location_gist_online
ON index_lab.places USING gist (location);
~~~

Tính chất:

- Giảm chặn INSERT/UPDATE/DELETE thông thường so với build thường.
- Có thể chờ transaction/snapshot trước hoặc sau các lượt scan.
- Tạo tải I/O/CPU/WAL.
- **Không chạy trong transaction block tường minh**.
- Nếu lỗi hoặc cancel có thể để lại index INVALID; cần xem catalog và quy trình cleanup.

### 24.3. Chẩn đoán invalid index

~~~sql
SELECT
    idx.relname AS index_name,
    ix.indisvalid,
    ix.indisready,
    pg_get_indexdef(ix.indexrelid) AS definition
FROM pg_index AS ix
JOIN pg_class AS idx ON idx.oid = ix.indexrelid
JOIN pg_class AS tbl ON tbl.oid = ix.indrelid
JOIN pg_namespace AS n ON n.oid = tbl.relnamespace
WHERE n.nspname = 'index_lab';
~~~

`indisvalid=false` có nghĩa không được planner sử dụng như một index hợp lệ theo quy tắc hiện hành. Không giả định “CREATE INDEX CONCURRENTLY trả timeout nhưng tên vẫn còn ⇒ index đã sẵn sàng”.

### 24.4. Bảo trì và write overhead

GiST/SP-GiST đều có chi phí:

- Chèn entry khi INSERT.
- Điều chỉnh index khi UPDATE/delete row versions.
- WAL và disk.
- VACUUM/autovacuum maintenance.
- Rebuild/reindex khi cần theo tình trạng vận hành.

Nếu tạo ba index point trên cùng cột chỉ để “thử mọi lựa chọn”, mỗi insert của bảng thực có thể phải duy trì cả ba. Trong production, nên giữ **tập index tối thiểu có lợi ích được đo**.

### 24.5. REINDEX và REINDEX CONCURRENTLY

Khi index bị bloat/hư hại hoặc có lý do tái xây, có `REINDEX`, và tùy phiên bản/loại index có `REINDEX CONCURRENTLY` để giảm chặn ghi. Những lệnh này có chi phí và giới hạn transaction block riêng; không dùng nó như cách chữa mọi truy vấn chậm mà chưa xem EXPLAIN/statistics.

---

## 25. Benchmark GiST so với SP-GiST đúng cách

### 25.1. Các chỉ số cần đo

| Nhóm | Chỉ số | Vì sao quan trọng |
|---|---|---|
| Query | p50/p95/p99 latency theo predicate | Một số truy vấn hiếm có thể rất chậm |
| Planner | `Index Scan`, `Bitmap Heap Scan`, `Seq Scan` | Biết index có được dùng không |
| I/O | shared hit/read, buffers, WAL | Nhìn chi phí cache và storage |
| Data | số rows, độ chọn lọc, phân bố point/range | Thay đổi hiệu quả partition/bounding |
| Storage | kích thước index, dead tuples | Chi phí lâu dài |
| Write | INSERT/UPDATE throughput | Index có tăng write amplification không |
| Build | create index time/disk | Khả năng triển khai |
| Maintenance | VACUUM/REINDEX overhead | Tính bền vững khi vận hành |

### 25.2. Một quy trình đo đơn giản

1. Chuẩn bị dữ liệu đại diện, trong **database riêng**.
2. Tạo **một** cấu hình index cần kiểm thử tại một thời điểm, hoặc so sánh trên các bản sao dữ liệu tương đương.
3. `ANALYZE` bảng.
4. Chạy query thật, lưu plan/latency/buffers.
5. Dùng nhiều query với độ chọn lọc khác nhau: vùng nhỏ, vùng lớn, dữ liệu cluster, KNN top-5/top-100.
6. Đo khả năng ghi dữ liệu và update.
7. Lặp lại cho cấu hình index khác, giữ thiết lập phần cứng/cached data tương đối công bằng.
8. Kết luận theo **workload cụ thể**, không theo số đo chỉ một query.

### 25.3. Tránh kết luận sai khi nhiều index cùng tồn tại

Nếu vừa tạo GiST và SP-GiST trên cùng cột, planner có thể chọn một trong hai, hoặc không dùng index. Một bài benchmark cần xác nhận `Index Scan using idx...` trên mỗi lần đo; nếu cần phân lập, dùng bản sao dataset riêng hoặc xử lý index test trong lab với quyền phù hợp.

### 25.4. Cache và thứ tự chạy benchmark

Query đầu có thể chậm do đọc disk, query sau nhanh do cache. Không chọn index thắng chỉ vì nó được chạy **sau**. Cần lặp nhiều vòng, hoán đổi thứ tự và đo cả cold/warm behavior khi có thể kiểm soát.

### 25.5. Tránh force planner trong production

`SET enable_seqscan = off` hoặc thay đổi `random_page_cost` chỉ để thấy index scan không chứng minh kế hoạch đó có tổng chi phí tốt hơn. Nếu dùng debug setting trong lab, giải thích nó như một thí nghiệm cấu trúc plan, không phải cấu hình vận hành mặc định.

---

## 26. Các lỗi và ngộ nhận thường gặp

| Ngộ nhận / sai lầm | Vì sao sai | Cách tiếp cận phù hợp |
|---|---|---|
| “GiST là một index chỉ dành cho geometry” | GiST là framework extensible | Xem operator class cho range, inet, text và extension |
| “SP-GiST chắc chắn nhanh hơn GiST” | Cấu trúc phân vùng khác, không có bảo đảm chung | Benchmark đúng query và phân bố dữ liệu |
| “Cứ `USING gist` là mọi kiểu đều index được” | Cần operator class cho đúng kiểu | Xem `pg_opclass` |
| “GiST và SP-GiST hỗ trợ giống nhau mọi operator” | Opclass và method khác | Kiểm tra operator family/opclass |
| “Nếu cột là TEXT thì dùng SP-GiST cho ILIKE '%x%'” | `text_ops` không mặc định là trigram | Dùng `pg_trgm` GiST/GIN nếu cần |
| “KNN chỉ cần ORDER BY hàm distance bất kỳ” | Planner cần distance-ordering operator phù hợp | Dùng `<->` đúng type/opclass, xem EXPLAIN |
| “Mọi KNN trả khoảng cách mét” | Đơn vị theo data type/operator | Point core là tọa độ phẳng; dùng đúng CRS |
| “Có GiST thì không cần GIN cho full-text” | Access patterns và cấu trúc khác | So GiST/GIN theo workload |
| “Range overlap có thể thay bằng B-tree trên start_time” | Chỉ lọc start có thể bỏ sót range dài giao nhau | Dùng range type và `&&` khi phù hợp |
| “Hai interval chạm đầu mút luôn overlap” | Bound flags quyết định semantics | Quy ước `[)`, thử range operators |
| “SP-GiST range ⇒ hỗ trợ multirange như nhau” | Range và multirange có opclass khác | Kiểm tra; GiST multirange_ops khi có |
| “GiST inet mặc định cho inet” | GiST inet_ops không phải default | Viết `USING gist (network inet_ops)` |
| “SP-GiST không bao giờ lossy” | Tùy opclass và biểu diễn leaf | Đọc recheck/explain |
| “Lossy index trả sai dữ liệu cho client” | Executor recheck điều kiện | Giải thích candidate + recheck |
| “Bitmap Recheck Cond ⇒ mọi index query đều lossy” | Recheck có nhiều nguyên nhân, gồm lossy bitmap pages | Đọc cả Rows Removed by Index Recheck |
| “Index-only scan chỉ cần INCLUDE” | Opclass có thể không trả đủ giá trị, visibility map còn quan trọng | Kiểm tra khả năng opclass và plan |
| “Index đã tạo thì mọi query luôn dùng” | Planner quyết định theo cost/selectivity | ANALYZE và EXPLAIN |
| “Index point luôn thay PostGIS” | Geospatial trên trái đất cần CRS/semantics | Dùng extension đúng metric |
| “GiST trên cột range cấm lịch đặt trùng” | Index tìm kiếm không tự là constraint | EXCLUDE USING gist với operator thích hợp |
| “btree_gist tương đương UNIQUE B-tree” | Hỗ trợ scalar operators trong GiST, không tự tạo unique B-tree | Dùng UNIQUE/PK hoặc EXCLUDE đúng nghiệp vụ |
| “GiST và SP-GiST đều không tốn ghi” | Mỗi index phải được duy trì qua DML | Cân nhắc write amplification |
| “CREATE INDEX CONCURRENTLY không ảnh hưởng production” | Có I/O, WAL, wait, invalid state | Monitor và maintenance plan |
| “Có index trùng tên tức là VALID” | Build concurrent có thể để lại invalid | Kiểm tra `pg_index.indisvalid` |
| “Dữ liệu nhỏ planner dùng Seq Scan là lỗi” | Seq Scan có thể rẻ nhất | Đo trên tập đại diện |
| “FORCE index bằng enable_seqscan=off là tối ưu” | Chỉ thay đổi choice, không đảm bảo nhanh | Đánh giá plan tự nhiên |
| “Thêm đủ GiST, SP-GiST, GIN thì query nào cũng nhanh” | Chi phí index/maintenance lớn | Giữ các index có lợi ích đo được |

---

## 27. Quy trình chọn GiST hay SP-GiST

Một sơ đồ định hướng:

~~~mermaid
flowchart TD
    A["Mô tả đúng predicate và kiểu dữ liệu"] --> B{"Truy vấn chính?"}
    B -- "Equality/range trên scalar" --> C["B-tree; BRIN nếu dữ liệu cực lớn tương quan"]
    B -- "JSONB, array, full-text" --> D["GIN theo operator class"]
    B -- "Geometric/range/inet/prefix/nearest" --> E["Tìm opclass GiST/SP-GiST hỗ trợ operator"]
    B -- "Fuzzy text" --> F["pg_trgm: GiST vs GIN"]
    E --> G{"Cả GiST và SP-GiST hỗ trợ không?"}
    G -- "Chỉ một" --> H["Dùng method có opclass phù hợp"]
    G -- "Cả hai" --> I["Benchmark đúng phân bố/query"]
    I --> J{"KNN top-k là trọng tâm?"}
    J -- "Có" --> K["Kiểm tra Ordering Operators và Index Scan Order By"]
    J -- "Không" --> L["So Index Cond, recheck, buffers"]
    K --> M["Đánh giá latency, ghi, kích thước, build"]
    L --> M
    F --> M
    H --> M
    C --> M
    D --> M
    M --> N["Chọn và duy trì index tối thiểu có ích"]
~~~

### 27.1. Mẫu suy luận trước khi tạo index

Ví dụ business yêu cầu “tìm những phòng đã đặt giao nhau trong ngày 20/04”:

1. Dữ liệu là khoảng ngày ⇒ `daterange`.
2. Predicate là overlap ⇒ `&&`.
3. GiST/SP-GiST có range ops ⇒ cả hai là ứng viên.
4. Nếu cần **chặn đặt trùng khi ghi**, chỉ index chưa đủ ⇒ **exclusion constraint** phù hợp (GiST là phương pháp phổ biến).
5. Nếu lọc theo `room_id`, cân nhắc index/constraint kết hợp.
6. Kiểm tra tính đúng của bound `[)` và NULL.
7. Đo plan và ảnh hưởng insert/update.

Ví dụ khác: “top 10 tên gần giống 'postgress'”:

1. Kiểu text và metric trigram similarity.
2. Cần extension `pg_trgm`.
3. Cần KNN `ORDER BY term <-> query LIMIT 10`.
4. GiST `gist_trgm_ops` phù hợp với KNN top-k hơn GIN trong trường hợp này.
5. Kiểm tra threshold và trigram length; benchmark thực tế.

---

## 28. Bài tập thực hành

Bài tập sử dụng các bảng `index_lab.places`, `regions`, `reservations`, `network_rules`, `keywords` và những phần optional đã tạo trước đó. Mục tiêu là hiểu logic/SQL; **không chạy đồng loạt tất cả CREATE INDEX nếu bạn chỉ muốn thử chọn một phương án**.

### Bài 1 — GiST và SP-GiST là gì?

Giải thích hai access methods và điểm khác nhau cơ bản giữa “cây vùng bao” với “cây phân hoạch không gian”.

### Bài 2 — Operator class

Vì sao `CREATE INDEX ... USING spgist (col)` có thể không hợp lệ đối với một kiểu dữ liệu, dù PostgreSQL có access method SP-GiST?

### Bài 3 — Catalog

Viết SQL liệt kê opclasses của `gist` và `spgist`, kèm kiểu đầu vào và dấu hiệu default. Vì sao phải xem danh sách trên **database hiện tại**?

### Bài 4 — Point GiST

Tạo GiST index trên `index_lab.places.location` và viết query tìm điểm nằm trong hộp `((0,0),(5,5))`.

### Bài 5 — Point SP-GiST

Viết SQL tạo hai index point khác nhau bằng `quad_point_ops` và `kd_point_ops`. Có nên mặc định giữ cả hai ở production không?

### Bài 6 — KNN

Viết câu tìm ba địa điểm gần `point '(2,2)'` nhất. Toán tử nào cho planner cơ hội dùng KNN index scan?

### Bài 7 — ORDER BY sai hình thức

Vì sao biểu thức `ORDER BY sqrt(pow(x-2,2)+pow(y-2,2))` trên các cột tự tạo không tự tương đương KNN scan của một GiST point index?

### Bài 8 — Tọa độ

Vì sao khoảng cách giữa `point '(106.7,10.8)'` và `point '(106.8,10.9)'` trên dữ liệu kinh/vĩ độ không được tự diễn giải là mét?

### Bài 9 — Box overlap

Tạo GiST index trên `regions.bounds` và viết predicate tìm các hộp giao `box '((3,3),(7,8))'`.

### Bài 10 — Circle

GiST core hỗ trợ `circle` không? Có thể tự giả định SP-GiST cũng có default opclass circle không?

### Bài 11 — Range overlap

Với `daterange`, viết predicate tìm reservation giao khoảng `[2026-04-03,2026-04-06)`.

### Bài 12 — Bound [)

Hai đặt chỗ `[2026-04-01,2026-04-04)` và `[2026-04-04,2026-04-05)` có overlap không? Vì sao bound quan trọng?

### Bài 13 — Range containment

Tìm reservations chứa ngày `2026-04-03` bằng một operator range, không tự so sánh hai cột start/end.

### Bài 14 — SP-GiST range

Viết lệnh tạo SP-GiST index cho `reservations.stay`. Nó có tự cấm đặt phòng trùng không?

### Bài 15 — Multirange

Phân biệt GiST `multirange_ops` với SP-GiST `range_ops`. Có được mặc định dùng SP-GiST trực tiếp cho `datemultirange` không?

### Bài 16 — Mạng con

Viết câu tìm các giá trị `network_rules.network` nằm trong `10.10.0.0/16`, bao gồm bằng. Toán tử nào phù hợp?

### Bài 17 — inet_ops

Giải thích cú pháp tạo index GiST cho cột `network INET` và lý do phải viết `inet_ops`.

### Bài 18 — Prefix text

Viết SQL tạo SP-GiST text_ops cho `keywords.term` và tìm những keyword bắt đầu bằng `post`.

### Bài 19 — Prefix khác fuzzy

Vì sao `term ^@ 'post'` không đồng nghĩa `term % 'postgre'` của `pg_trgm`?

### Bài 20 — Trigram similarity

Viết SQL bật `pg_trgm` và tạo GiST trigram index. Truy vấn tìm keyword tương tự `postgress` bằng `%`.

### Bài 21 — KNN trigram

Viết câu tìm năm keyword có trigram distance nhỏ nhất với `postgress`. GiST và GIN khác nhau ra sao về KNN distance ordering?

### Bài 22 — Pattern quá ngắn

Một `ILIKE '%a%'` có luôn tận dụng trigram index hiệu quả không? Vì sao?

### Bài 23 — Full-text

Viết câu tạo GiST index trên `articles.search_vector` và truy vấn `@@ to_tsquery(...)`. Khi nào nên so GIN?

### Bài 24 — PostGIS

Phân biệt `point` core và `geometry(Point,4326)` của PostGIS. Ngưỡng `ST_DWithin(geom, q, 0.01)` ở SRID 4326 có mặc định là mét không?

### Bài 25 — Exclusion constraint

Sau khi bật `btree_gist`, viết constraint không cho hai reservation cùng `room_id` có `stay` overlap. Một GiST index đơn cột `stay` có thay thế constraint này không?

### Bài 26 — Los​sy và recheck

Giải thích cơ chế candidate/recheck và cách đọc `Recheck Cond` với `Rows Removed by Index Recheck` trong `EXPLAIN`.

### Bài 27 — Planner chọn Seq Scan

Bảng places chỉ có 10 dòng; query sử dụng Seq Scan dù index GiST đã tồn tại. Có nhất thiết là lỗi không? Nêu bốn lý do planner không dùng index.

### Bài 28 — Giám sát index

Viết query xem `pg_indexes` và một query đọc `pg_index.indisvalid` sau `CREATE INDEX CONCURRENTLY`.

### Bài 29 — Dung lượng

Viết SQL xem kích thước của các index trong schema `index_lab` và giải thích tại sao index nhỏ nhất chưa chắc tối ưu nhất.

### Bài 30 — Cost of writes

Vì sao không nên tự tạo cả GiST, SP-GiST quad, SP-GiST kd, GIN và B-tree trên cùng một cột chỉ “cho chắc”?

### Bài 31 — Query top-k theo category

Viết câu tìm hai `cafe` gần `point '(2,2)'` nhất. Vì sao nên đặt `WHERE category='cafe'` trước `LIMIT`?

### Bài 32 — Xung đột lịch

Hai client đồng thời kiểm tra “room 101 chưa trùng” rồi INSERT. Vì sao check-then-insert không khóa/constraint vẫn có race? Giải pháp?

### Bài 33 — Indexing network

Với hàng triệu dải CIDR, query phổ biến là `network <<= q` và `network && q`. Bạn chọn loại index nào để thử đầu tiên, và cần đo những gì?

### Bài 34 — Loại bỏ index dư thừa

Một bảng có GiST point và SP-GiST point cùng phục vụ predicate giống nhau. Trình bày quy trình xác định có thể bỏ một index hay không.

### Bài 35 — Tổng hợp lựa chọn

Chọn một hoặc hai ứng viên index thích hợp cho từng tình huống:

1. Tra cứu `user_id = 42`.
2. Tìm quãng thời gian giao nhau.
3. Tìm top-10 cửa hàng gần vị trí trên mặt phẳng.
4. Tìm nội dung `ILIKE '%word%'`.
5. Tìm từ gần đúng theo trigram distance.
6. Lọc JSONB chứa object.
7. Tìm các IP nằm trong subnet.
8. Tìm text bắt đầu bằng prefix.
9. Full-text query theo `tsvector @@ tsquery`.
10. Lọc timestamp trên bảng log hàng tỷ row append-only.

---

## 29. Gợi ý lời giải

### Bài 1 — Cấu trúc

GiST là hạ tầng cây tìm kiếm cân bằng với keys tổng hợp như vùng bao, tùy operator class. SP-GiST hỗ trợ cây phân vùng không gian/prefix như quadtree, k-d tree, radix tree và không yêu cầu cân bằng theo mô hình GiST. Không có phương pháp nhanh nhất cho mọi dataset.

### Bài 2 — Opclass

Access method chỉ cung cấp framework. Nếu thiếu opclass cho type/semantics, PostgreSQL không biết cách chuyển giá trị thành key/index strategy. Phải có opclass phù hợp và tập toán tử được đăng ký.

### Bài 3 — Catalog

~~~sql
SELECT
    a.amname,
    o.opcname,
    o.opcintype::regtype AS input_type,
    o.opcdefault AS is_default
FROM pg_opclass AS o
JOIN pg_am AS a ON a.oid = o.opcmethod
WHERE a.amname IN ('gist', 'spgist')
ORDER BY a.amname, o.opcname;
~~~

Danh sách phụ thuộc phiên bản và extension trong database; không đoán theo môi trường của người khác.

### Bài 4 — GiST point

~~~sql
CREATE INDEX idx_places_location_gist
ON index_lab.places USING gist(location);

SELECT place_id, place_name, location
FROM index_lab.places
WHERE location <@ box '((0,0),(5,5))'
ORDER BY place_id;
~~~

Nếu index đã có, không chạy lại CREATE cùng tên; câu này là mẫu thực hành.

### Bài 5 — SP-GiST point

~~~sql
CREATE INDEX idx_places_quad
ON index_lab.places USING spgist(location quad_point_ops);

CREATE INDEX idx_places_kd
ON index_lab.places USING spgist(location kd_point_ops);
~~~

Không mặc định giữ cả hai; đo plan, query latency, index size và chi phí ghi. Trong production nên giữ tập index có lợi ích rõ.

### Bài 6 — KNN

~~~sql
SELECT place_id, place_name, location,
       location <-> point '(2,2)' AS distance
FROM index_lab.places
ORDER BY location <-> point '(2,2)'
LIMIT 3;
~~~

`<->` là distance operator của point opclasses hỗ trợ KNN. Planner có thể dùng index theo `Order By` khi lợi thế hơn scan+sort.

### Bài 7 — Order-by-distance expression

Index GiST point có distance-ordering operator cụ thể. Biểu thức sqrt/pow tự viết không tự được planner nhận như cùng một opclass ordering operator. Nếu muốn KNN index-assisted, dùng `<->` đúng kiểu/index và kiểm tra plan.

### Bài 8 — Đơn vị

Core point dùng hệ tọa độ phẳng. Nếu input là kinh/vĩ độ (độ), khoảng cách Euclid trên độ không thể coi là mét. Dùng PostGIS geography hoặc geometry trong CRS metric phù hợp và hàm distance tương ứng.

### Bài 9 — Box overlap

~~~sql
CREATE INDEX idx_regions_bounds_gist
ON index_lab.regions USING gist(bounds);

SELECT region_id, name
FROM index_lab.regions
WHERE bounds && box '((3,3),(7,8))';
~~~

`&&` cho box biểu diễn overlap theo semantics hình học.

### Bài 10 — Circle

GiST built-in có `circle_ops`; SP-GiST không có nghĩa phải hỗ trợ mọi opclass của GiST. Kiểm tra `pg_opclass` trước khi tạo index khác method.

### Bài 11 — Range overlap

~~~sql
SELECT reservation_id, room_id, stay
FROM index_lab.reservations
WHERE stay && daterange(
    DATE '2026-04-03',
    DATE '2026-04-06',
    '[)'
)
ORDER BY reservation_id;
~~~

### Bài 12 — Half-open bounds

Không overlap: ngày 04/04 là cận trên bị **loại trừ** của khoảng đầu, còn là cận dưới **bao gồm** của khoảng sau. `[)` phù hợp cho lịch check-in/check-out không chiếm ngày ra.

### Bài 13 — Contains element

~~~sql
SELECT reservation_id, room_id, guest_name
FROM index_lab.reservations
WHERE stay @> DATE '2026-04-03';
~~~

### Bài 14 — SP-GiST range

~~~sql
CREATE INDEX idx_reservations_stay_spgist
ON index_lab.reservations USING spgist(stay);
~~~

Index giúp query range overlap/contains khi planner dùng; không tự kiểm soát việc hai client đặt trùng. Cần constraint/transaction strategy.

### Bài 15 — Range khác multirange

GiST có built-in opclass cho multirange ở các PostgreSQL hiện đại. SP-GiST có range_ops cho các **range types**, không mặc định có opclass cho mọi multirange. Kiểm tra operator class trước khi dùng.

### Bài 16 — IP trong subnet

~~~sql
SELECT rule_id, label, network
FROM index_lab.network_rules
WHERE network <<= inet '10.10.0.0/16';
~~~

`<<=` nghĩa là contained by or equal, bao gồm chính subnet bằng nhau.

### Bài 17 — inet_ops

~~~sql
CREATE INDEX idx_network_rules_gist
ON index_lab.network_rules USING gist(network inet_ops);
~~~

`inet_ops` GiST không là default cho `inet`/`cidr`, nên cần chỉ định tường minh.

### Bài 18 — Prefix text

~~~sql
CREATE INDEX idx_keywords_spgist_text
ON index_lab.keywords USING spgist(term text_ops);

SELECT term
FROM index_lab.keywords
WHERE term ^@ 'post'
ORDER BY term;
~~~

`^@` là starts-with operator, không phải fuzzy matching.

### Bài 19 — Prefix và similarity

Prefix hỏi có bắt đầu chính xác bằng chuỗi không; trigram similarity hỏi độ gần nhau dựa vào các nhóm ba ký tự theo threshold và metric. Một chuỗi có thể gần giống dù không cùng prefix.

### Bài 20 — pg_trgm

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_keywords_gist_trgm
ON index_lab.keywords USING gist (term gist_trgm_ops);

SELECT term, similarity(term,'postgress') AS score
FROM index_lab.keywords
WHERE term % 'postgress'
ORDER BY score DESC, term;
~~~

Chỉ tạo nếu extension được phép; threshold ảnh hưởng tập kết quả.

### Bài 21 — KNN trigram

~~~sql
SELECT term, term <-> 'postgress' AS distance
FROM index_lab.keywords
ORDER BY term <-> 'postgress'
LIMIT 5;
~~~

GiST `gist_trgm_ops` có thể hỗ trợ KNN ordering. GIN `gin_trgm_ops` phù hợp cho nhiều lọc trigram nhưng không cho cùng loại distance-ordered KNN index scan.

### Bài 22 — Pattern ngắn

Không bảo đảm hiệu quả. Pattern không có trigram hữu ích có thể khiến hệ thống phải quét nhiều index entries. Đo EXPLAIN; với một ký tự, trigram index có thể không hiệu quả.

### Bài 23 — Full-text

~~~sql
CREATE INDEX idx_articles_gist_fts
ON index_lab.articles USING gist(search_vector);

SELECT article_id, body
FROM index_lab.articles
WHERE search_vector @@ to_tsquery('simple', 'indexing');
~~~

GIN có thể phù hợp hơn nhiều workload full-text; so độ chọn lọc, update cost và latency. Đừng trộn FTS với `ILIKE`.

### Bài 24 — PostGIS

Core `point` là hình học phẳng; `geometry(Point,4326)` có SRID xác định. Với geometry ở SRID 4326, khoảng cách theo hàm geometry là đơn vị **độ**, không tự là mét. Chuyển sang geography hoặc hệ metric phù hợp nếu cần mét.

### Bài 25 — Exclusion

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE index_lab.reservations
ADD CONSTRAINT no_overlapping_stays_for_room
EXCLUDE USING gist(room_id WITH =, stay WITH &&);
~~~

Một GiST index riêng trên stay chỉ giúp tìm các range giao nhau, **không ngăn race hoặc tạo ràng buộc ghi**. Exclusion constraint mới kiểm tra từng cặp row để chặn trường hợp cùng phòng, overlap.

### Bài 26 — Recheck

Index lossy lưu biểu diễn tóm tắt, đưa ra các hàng có **khả năng** khớp. PostgreSQL kiểm tra lại predicate chính xác trên heap khi cần. Trong EXPLAIN:

- `Index Cond` / `Recheck Cond` cho biết filter từ index và điều kiện kiểm tra.
- `Rows Removed by Index Recheck` là số candidate bị loại ở bước recheck.
- Chỉ thấy `Recheck Cond` không chứng minh index luôn lossy; có thể do bitmap heap scan và bitmap-page conditions.

### Bài 27 — Seq Scan

Không nhất thiết lỗi. Có thể do: bảng quá nhỏ, predicate không chọn lọc, index không hỗ trợ operator, query expression/cast khác cột index, LIMIT lớn, statistics/chi phí I/O khiến scan+sort rẻ hơn.

### Bài 28 — Index metadata

~~~sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'index_lab'
ORDER BY tablename, indexname;
~~~

~~~sql
SELECT
    idx.relname AS index_name,
    ix.indisvalid,
    ix.indisready
FROM pg_index AS ix
JOIN pg_class AS idx ON idx.oid = ix.indexrelid
JOIN pg_class AS tbl ON tbl.oid = ix.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'index_lab';
~~~

Tên tồn tại không đủ: index concurrent lỗi có thể để lại `indisvalid=false`.

### Bài 29 — Kích thước index

~~~sql
SELECT
    idx.relname AS index_name,
    pg_size_pretty(pg_relation_size(idx.oid)) AS size_pretty,
    pg_relation_size(idx.oid) AS size_bytes
FROM pg_class AS idx
JOIN pg_namespace AS ns ON ns.oid = idx.relnamespace
WHERE ns.nspname = 'index_lab'
  AND idx.relkind IN ('i','I')
ORDER BY size_bytes DESC;
~~~

Index lớn hơn có thể đọc ít heap pages hơn hoặc hỗ trợ ORDER BY tốt hơn; chọn theo chi phí tổng, không chỉ size.

### Bài 30 — Nhiều index dư thừa

Mỗi insert/update/delete phải bảo trì các index liên quan, tạo thêm I/O/WAL/dung lượng và có thể giảm throughput ghi. Index dư còn làm tăng chi phí VACUUM/reindex/deploy. Chọn theo queries thực.

### Bài 31 — Top-k cafe

~~~sql
SELECT place_id, place_name, location
FROM index_lab.places
WHERE category = 'cafe'
ORDER BY location <-> point '(2,2)'
LIMIT 2;
~~~

Lọc category trước LIMIT để đảm bảo hai kết quả đầu thuộc cafe; query top-k tất cả rồi lọc cafe có semantics khác và có thể thiếu cafe.

### Bài 32 — Check-then-insert race

Hai client có thể đồng thời thấy “chưa trùng” trước khi bên nào commit INSERT, dẫn đến trùng lịch nếu không có constraint/locking phù hợp. Exclusion constraint GiST trên `(room_id WITH =, stay WITH &&)` và transaction xử lý lỗi `23P01` là một hướng chặt chẽ.

### Bài 33 — CIDR workload

Thử SP-GiST `inet_ops` và GiST `inet_ops`, đối chiếu thêm B-tree nếu equality đáng kể. Đo p95 latency, buffers, index size, updates, độ chọn lọc subnet, dữ liệu host vs network, quy mô và planner choices.

### Bài 34 — Loại bỏ index

1. Xác định các query đang dùng index nào qua EXPLAIN.
2. Thống kê workload đầy đủ, không chỉ một query.
3. Benchmark với mỗi cấu hình trên dữ liệu đại diện.
4. So insert/update, disk, VACUUM và build time.
5. Nếu quyết định bỏ, dùng migration có phương án phục hồi; không drop trực tiếp index đang phục vụ workload chưa đo.

### Bài 35 — Bảng lựa chọn

| Tình huống | Ứng viên |
|---|---|
| 1. `user_id = 42` | B-tree |
| 2. Khoảng thời gian giao nhau | GiST/SP-GiST `range_ops` |
| 3. Top-10 cửa hàng gần điểm | GiST hoặc SP-GiST point KNN; PostGIS nếu địa lý thực |
| 4. `ILIKE '%word%'` | `pg_trgm` GiST/GIN |
| 5. Trigram distance top-k | GiST `gist_trgm_ops` |
| 6. JSONB containment | GIN JSONB opclass |
| 7. Địa chỉ thuộc subnet | SP-GiST/GiST `inet_ops` |
| 8. Text starts-with | SP-GiST `text_ops` với `^@` hoặc B-tree prefix strategy |
| 9. `tsvector @@ tsquery` | GIN thường được xem xét đầu; GiST cũng hỗ trợ |
| 10. Timestamp log append-only | BRIN hoặc B-tree tùy correlation, selectivity |

---

## 30. Checklist chọn và triển khai chỉ mục

### Trước khi chọn

- [ ] Ghi cụ thể kiểu dữ liệu và **toán tử** trong query.
- [ ] Phân biệt kết quả đúng theo nghiệp vụ: khoảng có [), tọa độ phẳng vs trái đất, prefix vs similarity.
- [ ] Xem opclass thực tế trong `pg_opclass` theo version/extension.
- [ ] Xác định KNN có cần `<->` và top-k không.
- [ ] Đánh giá B-tree, GIN, BRIN trước khi chọn GiST/SP-GiST theo quán tính.
- [ ] Với ràng buộc không giao nhau, cân nhắc **EXCLUDE**, không chỉ index phục vụ SELECT.
- [ ] Phân tích dữ liệu trùng, NULL, skew, density và selectivity.

### Khi thử nghiệm

- [ ] Dùng dataset đại diện, không chỉ lab 10 hàng.
- [ ] `ANALYZE` trước khi đo.
- [ ] Xem `Index Scan`/`Index Cond`/`Order By`/`Recheck Cond`.
- [ ] So latency, buffers, size, chi phí ghi và build time.
- [ ] Không dựa vào một lần chạy cache-warm hoặc kế hoạch bị force.
- [ ] Không tạo nhiều index trùng mục đích mà thiếu lý do.

### Khi triển khai thật

- [ ] Xác định bảng có cần ghi liên tục khi build không.
- [ ] Nếu dùng `CREATE INDEX CONCURRENTLY`, chạy ngoài transaction block.
- [ ] Giám sát tiến độ, disk, WAL, replication và backend chờ.
- [ ] Xử lý trường hợp invalid index trước retry.
- [ ] Xác minh opclass/definition/index VALID sau deploy.
- [ ] Xem lại các truy vấn quan trọng và ảnh hưởng đến write throughput.

---

## 31. Tài liệu chính thống nên tham khảo

Để xác nhận operator classes theo đúng phiên bản PostgreSQL đang sử dụng:

- [PostgreSQL — Index Types](https://www.postgresql.org/docs/current/indexes-types.html): tổng quan B-tree, GiST, SP-GiST, GIN và BRIN.
- [PostgreSQL — GiST Indexes](https://www.postgresql.org/docs/current/gist.html): operator classes built-in, support functions và kỹ thuật distance ordering.
- [PostgreSQL — SP-GiST Indexes](https://www.postgresql.org/docs/current/spgist.html): quadtree/k-d tree/radix tree, các opclass hỗ trợ và KNN.
- [PostgreSQL — pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html): similarity, các toán tử, opclasses GiST/GIN và KNN trigram.
- [PostgreSQL — Range Types](https://www.postgresql.org/docs/current/rangetypes.html): bounds, overlap, containment và exclusion constraints.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): `USING`, operator classes, concurrent builds và hạn chế transaction.
- [PostgreSQL — btree_gist](https://www.postgresql.org/docs/current/btree-gist.html): B-tree-like operators trên GiST để dùng với exclusion.
- [PostGIS Documentation](https://postgis.net/documentation/): semantics của geometry/geography, CRS, spatial operators và chỉ mục.

Khi tài liệu `/current/` đã nâng lên phiên bản mới, đối chiếu thêm trang `/docs/<major>/...` của chính PostgreSQL đang chạy. Không sử dụng ví dụ operator class của một extension như thể nó là built-in được bật sẵn trong mọi database.

---

## 32. Tổng kết

**GiST và SP-GiST không phải hai cách viết khác nhau để tạo “index không gian”. Chúng là hai hạ tầng chỉ mục có cấu trúc và chiến lược phân nhánh khác nhau, được kết hợp với operator classes để giải những predicate chuyên biệt.**

- **GiST — Generalized Search Tree:** phù hợp nhiều kiểu dữ liệu và chiến lược như hình học, range/multirange, mạng, trigram, full-text và exclusion constraint qua opclasses/extension. Nó có thể dùng key tổng hợp và cần recheck khi representation lossy.
- **SP-GiST — Space-Partitioned GiST:** hỗ trợ cấu trúc phân vùng không gian/prefix như quadtree, k-d tree, radix tree; có built-in opclasses cho point, box, polygon, range, inet và text phù hợp.
- **Kiểu dữ liệu phù hợp không đồng nghĩa mọi toán tử phù hợp.** Phải đối chiếu data type, operator và operator class trên phiên bản PostgreSQL đang dùng.
- **KNN:** `ORDER BY indexed_value <-> query LIMIT k` có thể dùng index-assisted nearest-neighbor khi opclass hỗ trợ distance ordering; `<->` của point và trigram mang **semantics/đơn vị khác nhau**.
- **Khoảng thời gian:** dùng range và `&&`/`@>` để biểu diễn overlap/contains. Để **ngăn đặt trùng**, cần exclusion constraint/transaction semantics, không chỉ một index.
- **Text:** SP-GiST `text_ops` là ứng viên cho prefix; fuzzy/trigram cần `pg_trgm`, còn full-text `tsvector@@tsquery` thường so GiST với GIN.
- **Địa lý thực:** core `point` là tọa độ phẳng; PostGIS geometry/geography và CRS phù hợp là điều cần thiết khi câu hỏi dùng khoảng cách địa lý thực.
- **Hiệu năng:** không thể đoán bằng tên access method. `EXPLAIN (ANALYZE, BUFFERS)`, statistics, index size, dữ liệu đại diện và ảnh hưởng ghi mới là căn cứ chọn.
- **Triển khai:** index lớn cần xem locking, `CONCURRENTLY`, trạng thái INVALID, WAL, disk và replication.

Quy trình nên ghi nhớ: **xác định câu hỏi nghiệp vụ → chọn kiểu dữ liệu biểu diễn chính xác → kiểm tra toán tử và operator class → tạo một index ứng viên → đo EXPLAIN cùng workload thực → cân nhắc chi phí ghi/bảo trì → chỉ giữ cấu hình mang lại lợi ích đã kiểm chứng**.
