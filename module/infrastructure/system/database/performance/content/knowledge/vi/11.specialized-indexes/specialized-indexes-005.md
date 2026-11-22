# GIN, GiST và các kiểu truy vấn chuyên biệt trong PostgreSQL

## Mục tiêu bài học

B-tree là lựa chọn mặc định phù hợp cho nhiều truy vấn so sánh, sắp xếp và tra cứu theo khóa. Tuy nhiên, dữ liệu thực tế thường có cấu trúc phức tạp hơn: một cột chứa mảng nhiều giá trị, JSONB, văn bản cần tìm kiếm theo từ, khoảng thời gian cần kiểm tra giao nhau, hoặc tọa độ cần tìm điểm gần nhất. Những truy vấn này có ngữ nghĩa toán tử riêng và không phải lúc nào B-tree cũng biểu diễn được đường truy cập hiệu quả.

Trong chương **Chỉ mục chuyên biệt** của module **DATABASE_PERFORMANCE**, bài học này trình bày hai access method quan trọng của PostgreSQL là GIN (Generalized Inverted Index) và GiST (Generalized Search Tree). Nội dung tập trung vào cấu trúc, operator class, kiểu truy vấn phù hợp, giới hạn recheck và chi phí bảo trì. Module DATABASE_PERFORMANCE rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; do đó, việc chọn GIN hay GiST phải dựa trên toán tử thực tế, kế hoạch thực thi và tỷ lệ đọc/ghi của workload.

Sau bài học, bạn có thể:

- Giải thích cách GIN và GiST tổ chức dữ liệu chỉ mục ở mức khái quát.
- Chọn access method và operator class phù hợp với truy vấn mảng, JSONB, full-text, trigram, range và tìm kiếm lân cận.
- Hiểu vì sao một số kế hoạch cần kiểm tra lại điều kiện trên heap (recheck).
- Đọc `EXPLAIN (ANALYZE, BUFFERS)` để đánh giá hiệu quả của chỉ mục chuyên biệt.
- Nhận diện chi phí ghi, kích thước chỉ mục, pending list và công việc bảo trì.
- Thiết kế phép thử trước/sau để xác nhận chỉ mục có cải thiện toàn workload.

## 1. Vì sao cần chỉ mục chuyên biệt?

Một chỉ mục B-tree tổ chức khóa theo thứ tự, nên rất phù hợp với các phép so sánh như `=`, `<`, `<=`, `>`, `>=`, tra cứu theo tiền tố có điều kiện phù hợp và `ORDER BY`. Nhưng một số truy vấn không hỏi “giá trị này bằng bao nhiêu?” mà hỏi những câu hỏi khác:

- Mảng có chứa một phần tử hoặc một tập phần tử không?
- JSONB có chứa cấu trúc con hoặc có một khóa nhất định không?
- Văn bản có chứa các lexeme của truy vấn tìm kiếm không?
- Hai khoảng thời gian có giao nhau không?
- Hình học nào nằm trong vùng, hoặc điểm nào gần một tọa độ nhất?
- Chuỗi nào tương tự chuỗi tìm kiếm theo độ tương đồng trigram?

GIN và GiST cung cấp các cấu trúc chỉ mục có thể hỗ trợ những phép toán này. Chúng không thay thế B-tree cho mọi truy vấn. Chọn sai access method có thể làm chỉ mục lớn, cập nhật chậm hoặc khiến bộ tối ưu không thể dùng chỉ mục cho toán tử đang viết.

### 1.1. Access method và operator class

Trong PostgreSQL, `USING` xác định access method, còn operator class mô tả cách kiểu dữ liệu và toán tử được biểu diễn trong access method đó. Ví dụ:

```sql
CREATE INDEX idx_articles_search
ON articles USING GIN (search_vector);

CREATE INDEX idx_bookings_period
ON bookings USING GIST (during);
```

Khi không chỉ rõ operator class, PostgreSQL dùng operator class mặc định của kiểu dữ liệu cho access method tương ứng. Có thể chỉ rõ operator class khi cần một bộ toán tử khác, ví dụ `jsonb_path_ops`, `gin_trgm_ops` hoặc `gist_trgm_ops`.

Điểm quan trọng là chỉ mục hỗ trợ **một tập toán tử nhất định**. Việc một cột có GIN hoặc GiST không có nghĩa mọi điều kiện trên cột đều dùng được chỉ mục. Hãy đối chiếu toán tử trong `WHERE` hoặc `ORDER BY` với operator class và xác nhận bằng kế hoạch thực thi.

## 2. GIN — Generalized Inverted Index

### 2.1. Ý tưởng cấu trúc

GIN phù hợp với giá trị chứa nhiều thành phần, ví dụ mảng, JSONB hoặc vector tìm kiếm toàn văn. Thay vì lưu một mục chỉ mục cho toàn bộ giá trị phức hợp, GIN tách giá trị thành các khóa (key) và liên kết mỗi khóa với các vị trí dòng chứa khóa đó.

Ví dụ, nếu một tài liệu có các từ `database`, `index` và `performance`, GIN có thể lưu quan hệ từ mỗi lexeme đến các dòng tài liệu chứa lexeme đó. Khi truy vấn yêu cầu các từ cụ thể, engine tra các danh sách vị trí tương ứng và kết hợp chúng theo ngữ nghĩa toán tử.

Một mục GIN có thể trỏ đến một posting list chứa nhiều TID (tuple identifier). Khi danh sách đủ lớn, PostgreSQL có thể tổ chức thành posting tree. Thiết kế này giúp tra cứu các thành phần hiệu quả, nhưng chỉ mục có thể lớn và việc cập nhật một giá trị phức hợp có thể tạo nhiều thay đổi chỉ mục.

### 2.2. Các kiểu dữ liệu và truy vấn phù hợp

GIN thường được dùng cho:

- **Array:** kiểm tra chứa phần tử, chứa tập phần tử hoặc giao nhau.
- **JSONB:** kiểm tra cấu trúc con, khóa tồn tại và biểu thức JSONPath tùy operator class.
- **Full-text search (`tsvector`):** tìm các từ hoặc lexeme trong tài liệu.
- **Trigram (`pg_trgm`):** tìm chuỗi gần giống hoặc tìm mẫu `LIKE`/`ILIKE` phù hợp.

#### Ví dụ A — Tìm kiếm trong mảng

Giả sử bảng `products` lưu nhãn sản phẩm trong cột `tags text[]`:

```sql
CREATE INDEX idx_products_tags_gin
ON products USING GIN (tags);
```

Các truy vấn thường dùng:

```sql
-- Sản phẩm có chứa nhãn postgres
SELECT product_id, name
FROM products
WHERE tags @> ARRAY['postgres'];

-- Sản phẩm có ít nhất một nhãn trong tập đưa vào
SELECT product_id, name
FROM products
WHERE tags && ARRAY['postgres', 'database'];
```

Với array operator class mặc định, GIN hỗ trợ các phép toán như `@>`, `<@`, `&&` và `=`. Việc chọn truy vấn vẫn phụ thuộc độ chọn lọc và kích thước dữ liệu. Nếu điều kiện trả về phần lớn bảng, sequential scan có thể rẻ hơn.

#### Ví dụ B — Tìm cấu trúc trong JSONB

Giả sử cột `attributes` lưu đặc tính sản phẩm:

```sql
CREATE INDEX idx_products_attributes_gin
ON products USING GIN (attributes jsonb_path_ops);
```

Truy vấn containment:

```sql
SELECT product_id, name
FROM products
WHERE attributes @> '{"brand":"Acme","spec":{"wifi":true}}'::jsonb;
```

`jsonb_path_ops` thường tạo chỉ mục nhỏ hơn và hiệu quả cho các truy vấn containment phù hợp, nhưng hỗ trợ ít toán tử hơn operator class mặc định `jsonb_ops`. Cụ thể, `jsonb_path_ops` hỗ trợ `@>`, `@?` và `@@`; nó không hỗ trợ các toán tử kiểm tra tồn tại khóa như `?`, `?|` và `?&`.

Nếu workload cần kiểm tra khóa tồn tại:

```sql
CREATE INDEX idx_products_attributes_ops
ON products USING GIN (attributes jsonb_ops);

SELECT product_id
FROM products
WHERE attributes ? 'brand';
```

`jsonb_ops` linh hoạt hơn với các toán tử tồn tại khóa và containment, nhưng thường có cấu trúc chỉ mục lớn hơn. Không tạo đồng thời hai chỉ mục chỉ vì muốn có mọi toán tử; hãy chọn theo tập truy vấn thực sự được sử dụng và đo chi phí ghi.

#### Ví dụ C — Tìm kiếm toàn văn

Với nội dung bài viết, có thể tạo chỉ mục GIN trên biểu thức `to_tsvector`:

```sql
CREATE INDEX idx_articles_body_fts
ON articles USING GIN (
    to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(body, ''))
);
```

Truy vấn cần dùng biểu thức tương ứng và cấu hình tìm kiếm phù hợp:

```sql
SELECT article_id, title
FROM articles
WHERE to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(body, ''))
      @@ plainto_tsquery('simple', 'database performance');
```

GIN lưu lexeme và vị trí dòng, nên phù hợp với việc tìm tài liệu có các từ truy vấn. Cấu hình `'simple'` trong ví dụ không thực hiện stemming theo ngôn ngữ như một số cấu hình khác. Hãy chọn text search configuration theo ngôn ngữ nội dung, quy tắc chuẩn hóa và yêu cầu tìm kiếm. Biểu thức truy vấn phải khớp với biểu thức index để planner có thể tận dụng chỉ mục biểu thức.

### 2.3. Pending list và fastupdate

GIN có thể dùng cơ chế `fastupdate` để giảm chi phí cập nhật đồng bộ vào cấu trúc chính. Thay đổi mới được đưa vào một pending list; truy vấn phải xét cả phần chỉ mục chính lẫn pending list. Khi pending list đạt ngưỡng, PostgreSQL có thể chuyển các mục sang cấu trúc chính.

Lợi ích là giảm chi phí một số thao tác ghi, nhưng việc dọn pending list có thể tạo ra đợt công việc lớn và làm độ trễ ghi biến động. Autovacuum hoặc cơ chế dọn dẹp nền có vai trò quan trọng trong việc kiểm soát pending list. Các tham số như `gin_pending_list_limit` và tùy chọn `fastupdate` cần được điều chỉnh theo workload, phiên bản và khả năng vận hành.

Các điểm cần theo dõi:

- Kích thước và tốc độ tăng của pending list.
- Thời gian ghi khi pending list được dọn.
- Tần suất autovacuum và khả năng hoàn tất công việc bảo trì.
- Kích thước GIN index và lượng WAL sinh ra.
- Độ trễ p95/p99 của `INSERT`, `UPDATE` và truy vấn tìm kiếm.

Với tải nạp dữ liệu lớn theo lô, có thể cân nhắc nạp dữ liệu trước rồi tạo GIN index sau nếu quy trình triển khai cho phép. Việc tạo chỉ mục có chi phí I/O và CPU lớn, cần được lập kế hoạch phù hợp.

## 3. GiST — Generalized Search Tree

### 3.1. Ý tưởng cấu trúc

GiST là một framework cây tìm kiếm tổng quát. Thay vì buộc mọi kiểu dữ liệu vào thứ tự tuyến tính như B-tree, GiST cho phép operator class định nghĩa cách biểu diễn vùng hoặc thuộc tính bao phủ, cách kiểm tra điều kiện, cách kết hợp node và cách chia node khi cây đầy.

Ở mức khái quát, GiST có các node nội bộ đại diện cho vùng bao phủ các giá trị con. Khi tìm kiếm, engine dùng toán tử và hàm `consistent` của operator class để quyết định nhánh nào có thể chứa kết quả. Khi chèn dữ liệu, các hàm như `penalty`, `union` và `picksplit` giúp chọn nhánh, cập nhật vùng bao phủ và chia node.

Do đây là framework tổng quát, ý nghĩa của “vùng” phụ thuộc kiểu dữ liệu. Với range, vùng có thể đại diện khoảng; với dữ liệu hình học, có thể là bounding box; với trigram, operator class có thể tổ chức chữ ký để hỗ trợ tìm kiếm gần đúng.

### 3.2. Các kiểu truy vấn phù hợp

GiST thường được dùng cho:

- Range và kiểm tra giao nhau, chứa hoặc nằm trong khoảng.
- Dữ liệu hình học và truy vấn không gian.
- Tìm kiếm lân cận (K-nearest neighbors, KNN) khi operator class hỗ trợ khoảng cách.
- Trigram similarity với `pg_trgm`.
- Một số loại full-text search, network hoặc dữ liệu chuyên biệt khác tùy operator class.

#### Ví dụ A — Tìm khoảng thời gian giao nhau

Giả sử bảng `bookings` có cột `during tstzrange` biểu diễn thời gian bắt đầu và kết thúc:

```sql
CREATE INDEX idx_bookings_during_gist
ON bookings USING GIST (during);
```

Tìm các lịch đặt giao với khoảng thời gian yêu cầu:

```sql
SELECT booking_id, during
FROM bookings
WHERE during && tstzrange($1, $2, '[)');
```

Toán tử `&&` kiểm tra hai range có giao nhau. Ký hiệu `'[)'` biểu diễn khoảng đóng ở đầu và mở ở cuối, giúp các lịch đặt liền kề nhau không bị xem là chồng lấn ở điểm biên. Các toán tử range khác như `@>` và `<@` có thể kiểm tra chứa hoặc được chứa; chỉ mục cần operator class hỗ trợ toán tử tương ứng.

#### Ví dụ B — Ngăn hai lịch đặt cùng phòng bị chồng lấn

GiST còn có thể được dùng trong exclusion constraint. Khi kết hợp kiểu scalar với range, extension `btree_gist` cung cấp operator class GiST cho nhiều kiểu dữ liệu vốn thường dùng B-tree:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_reservations (
    reservation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id bigint NOT NULL,
    during tstzrange NOT NULL,
    EXCLUDE USING GIST (
        room_id WITH =,
        during WITH &&
    )
);
```

Ràng buộc này không cho phép hai dòng có cùng `room_id` và khoảng `during` giao nhau. Nó minh họa việc GiST không chỉ tăng tốc đọc mà còn hỗ trợ biểu diễn ràng buộc dữ liệu. Cần kiểm tra khả năng cài extension, quyền triển khai và chi phí duy trì ràng buộc trong môi trường thực tế.

#### Ví dụ C — Tìm điểm gần nhất

PostgreSQL có kiểu hình học tích hợp `point`. Có thể tạo GiST index:

```sql
CREATE INDEX idx_places_location_gist
ON places USING GIST (location);
```

Tìm 10 địa điểm gần điểm tham chiếu nhất:

```sql
SELECT place_id,
       location,
       location <-> point(10, 20) AS distance
FROM places
ORDER BY location <-> point(10, 20)
LIMIT 10;
```

Toán tử `<->` biểu diễn khoảng cách cho kiểu dữ liệu và operator class hỗ trợ KNN. Khi dùng PostGIS, mô hình dữ liệu thường là `geometry` hoặc `geography` với GiST index và các hàm không gian như `ST_DWithin`; cần xem tài liệu PostGIS về hệ tọa độ, đơn vị khoảng cách và điều kiện dùng index.

### 3.3. Recheck và kết quả gần đúng

Một số operator class GiST dùng biểu diễn bao phủ hoặc chữ ký gần đúng. Chỉ mục có thể trả về các dòng ứng viên mà điều kiện chính xác vẫn phải được kiểm tra trên dữ liệu gốc. Vì vậy, kế hoạch có thể chứa `Recheck Cond` hoặc bộ đếm `Rows Removed by Index Recheck`.

Recheck không tự động có nghĩa chỉ mục kém. Nó là một phần của cách một số operator class cân bằng kích thước chỉ mục và độ chính xác. Cần đánh giá số ứng viên bị loại, số heap block đọc và thời gian thực tế. Nếu tỷ lệ false positive quá cao với workload quan trọng, hãy xem operator class, độ chọn lọc, biểu diễn dữ liệu hoặc cách viết truy vấn.

## 4. So sánh GIN và GiST

| Tiêu chí | GIN | GiST |
|---|---|---|
| Mô hình | Chỉ mục đảo: khóa thành phần ánh xạ tới các TID | Cây tìm kiếm tổng quát với vùng hoặc chữ ký bao phủ |
| Dữ liệu phù hợp | Giá trị có nhiều thành phần như array, JSONB, tsvector, trigram | Range, hình học, KNN, trigram và nhiều kiểu chuyên biệt |
| Mẫu truy vấn | Thành phần có tồn tại/được chứa trong giá trị không? | Giá trị có giao, nằm trong vùng hoặc gần đối tượng nào? |
| Đọc | Thường hiệu quả cho tra cứu thành phần và containment | Hiệu quả theo khả năng cắt nhánh của operator class |
| Ghi | Thường đắt hơn do một giá trị có thể tạo nhiều mục chỉ mục; có pending list | Chi phí phụ thuộc việc cập nhật cây, chia node và độ phức tạp operator class |
| Recheck | Có thể cần tùy operator class và toán tử | Có thể cần khi biểu diễn gần đúng hoặc lossy |
| Tìm lân cận | Không phải lựa chọn chung cho KNN | Có thể hỗ trợ KNN qua toán tử khoảng cách `<->` |

Đây là khuynh hướng, không phải quy tắc tuyệt đối. Với `pg_trgm`, cả GIN và GiST đều có thể hỗ trợ tìm kiếm tương đồng, nhưng GiST có thể hỗ trợ truy vấn sắp xếp theo khoảng cách trigram để lấy các kết quả gần nhất; GIN thường phù hợp cho lọc ứng viên. Hãy chọn theo dạng truy vấn và đo trên dữ liệu thực.

## 5. pg_trgm cho tìm kiếm chuỗi gần giống

Extension `pg_trgm` chia chuỗi thành các trigram (nhóm ba ký tự liên tiếp theo quy tắc của extension), giúp tìm chuỗi tương tự ngay cả khi người dùng gõ sai hoặc tên có biến thể.

Kích hoạt extension và tạo GIN index:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_customers_name_trgm_gin
ON customers USING GIN (name gin_trgm_ops);
```

Truy vấn tìm chuỗi con:

```sql
SELECT customer_id, name
FROM customers
WHERE name ILIKE '%nguyen%';
```

Với tìm kiếm top kết quả gần nhất theo khoảng cách trigram, GiST có thể phù hợp:

```sql
CREATE INDEX idx_customers_name_trgm_gist
ON customers USING GIST (name gist_trgm_ops);

SELECT customer_id,
       name,
       name <-> 'nguyen' AS distance
FROM customers
ORDER BY name <-> 'nguyen'
LIMIT 10;
```

GIN và GiST trigram có cách tối ưu khác nhau. Mẫu `LIKE`/`ILIKE` cần đủ ký tự cố định để trích trigram có ích; chuỗi tìm kiếm quá ngắn hoặc mẫu chỉ có wildcard có thể khiến chỉ mục không hiệu quả. Kết quả tương đồng cũng cần được đánh giá theo ngôn ngữ, cách chuẩn hóa dấu, chữ hoa/thường và dữ liệu thực tế.

## 6. Recheck, bitmap scan và cách đọc kế hoạch

Khi xem kế hoạch, cần phân biệt hai khái niệm:

- **Recheck do operator class:** chỉ mục trả về ứng viên và executor kiểm tra lại điều kiện chính xác trên tuple.
- **Lossy bitmap page:** bitmap heap scan chỉ giữ thông tin ở mức trang do giới hạn bộ nhớ, nên phải kiểm tra lại các tuple trên trang đó. Điều này có thể xảy ra với nhiều access method, không riêng GIN hoặc GiST.

Một kế hoạch có thể trông như sau (số liệu chỉ minh họa):

```text
Bitmap Heap Scan on products
  Recheck Cond: (attributes @> '{"brand":"Acme"}'::jsonb)
  Rows Removed by Index Recheck: 12
  Heap Blocks: exact=80 lossy=4
  -> Bitmap Index Scan on idx_products_attributes_gin
       Index Cond: (attributes @> '{"brand":"Acme"}'::jsonb)
```

Khi phân tích `EXPLAIN (ANALYZE, BUFFERS)`, chú ý:

| Chỉ số | Ý nghĩa |
|---|---|
| `Index Cond` | Điều kiện được đưa vào access method để tìm ứng viên |
| `Recheck Cond` | Điều kiện executor kiểm tra lại trên tuple khi cần |
| `Rows Removed by Index Recheck` | Số dòng ứng viên bị loại sau bước kiểm tra lại |
| `Heap Blocks: exact/lossy` | Số trang bitmap heap scan giữ chính xác hoặc ở dạng lossy |
| `Buffers: shared hit/read` | Trang lấy từ shared buffers hoặc được đọc vào buffer trong lần đo |
| `actual rows` và `loops` | Số dòng thực tế và số lần node thực thi |
| `Planning Time` / `Execution Time` | Chi phí lập kế hoạch và thời gian thực thi theo output PostgreSQL |

Không nên chỉ nhìn việc có `Bitmap Index Scan` để kết luận truy vấn nhanh. Nếu chỉ mục tạo ra quá nhiều ứng viên, heap scan và recheck có thể chiếm phần lớn thời gian. Cũng cần xem `Rows Removed by Index Recheck` trong bối cảnh số dòng đầu vào; một số ít dòng bị loại không nhất thiết là vấn đề.

## 7. Thiết kế và bảo trì chỉ mục chuyên biệt

### 7.1. Bắt đầu từ toán tử và workload

Trước khi tạo chỉ mục, hãy viết rõ câu hỏi truy vấn và toán tử được dùng. Ví dụ:

| Dữ liệu | Câu hỏi | Toán tử/cơ chế có thể phù hợp |
|---|---|---|
| `text[]` | Mảng chứa một phần tử/tập phần tử hoặc giao nhau? | GIN array operator class với `@>`, `<@`, `&&` |
| `jsonb` | Có chứa cấu trúc con hoặc tồn tại khóa? | GIN `jsonb_path_ops` hoặc `jsonb_ops` tùy toán tử |
| `tsvector` | Có khớp truy vấn full-text? | GIN hoặc GiST text search operator class; GIN thường là lựa chọn phổ biến cho tìm kiếm chính xác |
| `tstzrange` | Hai khoảng có giao nhau hoặc chứa nhau? | GiST range operator class |
| `point`/geometry | Nằm trong vùng hoặc gần nhất? | GiST với operator class hỗ trợ toán tử hình học/KNN |
| `text` | Chuỗi con hoặc tương đồng trigram? | `pg_trgm` với GIN cho lọc, GiST khi cần KNN distance |

Xác minh toán tử được hỗ trợ trong tài liệu của phiên bản PostgreSQL đang dùng. Sau đó chạy `EXPLAIN` để xác nhận planner có thể sử dụng index.

### 7.2. Cân nhắc chi phí ghi và dung lượng

Chỉ mục chuyên biệt thường phải duy trì nhiều thông tin hơn B-tree đơn giản. Một JSONB document hoặc văn bản dài có thể tạo ra nhiều khóa GIN. Một chỉ mục GiST cần cập nhật cấu trúc cây khi dữ liệu thay đổi. Hãy xem:

- Tỷ lệ đọc/ghi và số lần cập nhật các cột được lập chỉ mục.
- Kích thước chỉ mục so với bảng và khả năng nằm trong cache.
- WAL sinh ra, I/O và CPU trong quá trình ghi.
- Thời gian tạo chỉ mục, vacuum và reindex.
- Khả năng tăng độ trễ ghi khi GIN pending list được dọn.
- Số ứng viên và tỷ lệ recheck của truy vấn.

Không tạo nhiều chỉ mục chuyên biệt chồng lặp cho các biểu thức tương tự nếu chưa chứng minh có workload cần thiết. Mỗi chỉ mục mới đều có chi phí lưu trữ và bảo trì.

### 7.3. Chỉ mục biểu thức và partial index

Nếu truy vấn thường xuyên áp dụng hàm lên cột, chỉ mục biểu thức có thể giúp bộ tối ưu tìm đường truy cập phù hợp. Ví dụ full-text search ở trên dùng `to_tsvector(...)`. Cần bảo đảm biểu thức truy vấn khớp với biểu thức chỉ mục và dùng cùng text search configuration.

Partial index có thể giảm kích thước khi workload chỉ truy vấn một nhóm dòng ổn định, ví dụ tài liệu chưa lưu trữ hoặc bản ghi đang hoạt động. Nhưng predicate truy vấn phải được planner chứng minh phù hợp với predicate của index. Tham số hóa và biểu thức phức tạp đôi khi làm việc chứng minh khó hơn; xác nhận bằng `EXPLAIN` thay vì giả định.

### 7.4. Tạo chỉ mục trên bảng đang hoạt động

Với bảng lớn, `CREATE INDEX CONCURRENTLY` có thể giảm mức chặn ghi so với tạo index thông thường, nhưng vẫn tiêu thụ I/O/CPU, cần nhiều giai đoạn quét và có thể chờ transaction lâu. Lệnh này không chạy được bên trong transaction block. Nếu tạo thất bại, có thể để lại index invalid cần được kiểm tra và xử lý theo quy trình triển khai.

Không coi `CONCURRENTLY` là miễn phí hoặc không ảnh hưởng hệ thống. Hãy kiểm tra tải, dung lượng đĩa, replication lag và thời gian triển khai trước khi chạy trên production.

## 8. Quy trình kiểm chứng GIN/GiST

Áp dụng quy trình sau để xác định chỉ mục có thực sự giải quyết vấn đề:

**Bước 1 — Chọn truy vấn mục tiêu.** Dùng thống kê workload để chọn truy vấn có độ trễ, tần suất hoặc tổng thời gian đáng kể. Ghi lại câu SQL, toán tử, giá trị tham số và số dòng kết quả.

**Bước 2 — Lưu baseline.** Thu thập `EXPLAIN (ANALYZE, BUFFERS)`, thời gian p50/p95/p99, CPU, I/O, số dòng thực tế, số buffer, wait events và thông lượng đọc/ghi.

**Bước 3 — Chọn operator class.** Xác định toán tử có hỗ trợ bởi GIN/GiST và operator class phù hợp. Với JSONB, phân biệt `jsonb_ops` và `jsonb_path_ops`; với trigram, cân nhắc `gin_trgm_ops` và `gist_trgm_ops`.

**Bước 4 — Tạo chỉ mục trong môi trường thử nghiệm.** Dùng dữ liệu có phân bố, kích thước và tỷ lệ cập nhật gần production. Đo cả thời gian tạo, kích thước và lượng WAL.

**Bước 5 — Kiểm tra kế hoạch mới.** Xác nhận index scan hoặc bitmap index scan được chọn. Đọc `Index Cond`, `Recheck Cond`, actual rows, rows removed, heap blocks và buffers.

**Bước 6 — Thử các trường hợp đại diện.** Dùng giá trị có độ chọn lọc cao/thấp, văn bản ngắn/dài, JSONB có cấu trúc phổ biến/hiếm, range rộng/hẹp và tải đọc/ghi đồng thời.

**Bước 7 — Đo chi phí vận hành.** Theo dõi latency ghi, WAL, pending list GIN, autovacuum, kích thước index và tác động tới truy vấn khác.

**Bước 8 — So sánh và quyết định.** Chỉ giữ chỉ mục nếu lợi ích truy vấn mục tiêu lớn hơn chi phí lưu trữ, ghi và bảo trì trên toàn workload.

## 9. Những nhầm lẫn thường gặp

- **“GIN luôn nhanh hơn GiST.”** Mỗi access method phù hợp một dạng toán tử và dữ liệu khác nhau. GiST có thể hỗ trợ KNN mà GIN không phải lựa chọn phù hợp.
- **“GiST chỉ dùng cho dữ liệu hình học.”** GiST là framework tổng quát, được dùng cho range, trigram, full-text và các operator class khác.
- **“GIN chỉ lưu toàn bộ giá trị gốc.”** GIN lập chỉ mục các khóa thành phần và liên kết tới vị trí dòng; cách biểu diễn phụ thuộc operator class.
- **“Có index là planner chắc chắn dùng.”** Nếu toán tử không được hỗ trợ, predicate không khớp hoặc sequential scan rẻ hơn, planner có thể bỏ qua index.
- **“Recheck nghĩa là index sai.”** Recheck là một phần hợp lệ của các operator class hoặc bitmap lossy; cần đo tỷ lệ ứng viên bị loại và chi phí heap.
- **“GIN ghi nhanh như B-tree.”** Một giá trị phức hợp có thể tạo nhiều khóa chỉ mục; pending list giảm một số chi phí nhưng cần được dọn.
- **“Tạo thêm index không ảnh hưởng ghi.”** GIN/GiST làm tăng dung lượng, WAL và công việc duy trì khi dữ liệu thay đổi.
- **“Tìm kiếm trigram hoạt động hiệu quả với mọi chuỗi.”** Mẫu quá ngắn hoặc thiếu trigram hữu ích có thể không tận dụng index tốt.
- **“Cost trong EXPLAIN là thời gian mili giây.”** Cost là ước lượng của optimizer; cần dùng `ANALYZE`, buffers và phép đo tải thực tế để đánh giá.

## 10. Checklist chọn chỉ mục chuyên biệt

- [ ] Đã xác định truy vấn quan trọng và toán tử thực tế được dùng.
- [ ] Đã kiểm tra operator class hỗ trợ toán tử và kiểu dữ liệu.
- [ ] Đã so sánh GIN/GiST với B-tree hoặc sequential scan khi phù hợp.
- [ ] Đã chọn `jsonb_ops` hay `jsonb_path_ops` theo tập toán tử JSONB.
- [ ] Đã kiểm tra biểu thức của full-text index khớp với biểu thức truy vấn.
- [ ] Đã đánh giá GIN pending list, `fastupdate` và công việc autovacuum nếu có.
- [ ] Đã đọc `Index Cond`, `Recheck Cond`, `Rows Removed by Index Recheck` và `Heap Blocks`.
- [ ] Đã đo p50/p95/p99, buffers, CPU, I/O, WAL và độ trễ ghi.
- [ ] Đã thử với nhiều giá trị tham số và mức chọn lọc đại diện.
- [ ] Đã xác nhận lợi ích toàn workload lớn hơn chi phí lưu trữ và bảo trì.

## Kết luận

GIN phù hợp với dữ liệu có nhiều thành phần cần tìm theo khóa đảo như array, JSONB, full-text và trigram. GiST cung cấp cây tìm kiếm tổng quát cho range, hình học, KNN, trigram và các kiểu truy vấn được operator class hỗ trợ. Việc lựa chọn phụ thuộc vào toán tử, kiểu dữ liệu, độ chọn lọc và nhu cầu sắp xếp theo khoảng cách.

Khi tối ưu, hãy kiểm tra operator class, hiểu cơ chế recheck, đọc kế hoạch thực thi và đo chi phí ghi cùng bảo trì. Một chỉ mục chuyên biệt chỉ có giá trị khi nó cải thiện truy vấn mục tiêu mà không làm suy giảm đáng kể workload còn lại. Quyết định cuối cùng cần được xác nhận bằng dữ liệu đại diện và phép đo trước/sau thay đổi.
