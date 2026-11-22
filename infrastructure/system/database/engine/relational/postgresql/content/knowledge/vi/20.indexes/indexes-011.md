# Operator class, collation và thứ tự sắp xếp trong chỉ mục PostgreSQL

Một chỉ mục B-tree trên cột `title` có thể rất hữu ích cho `WHERE title = 'ABC'` và `ORDER BY title`, nhưng lại không nhất thiết được sử dụng cho `WHERE title LIKE 'ABC%'` khi database dùng một locale không phải `C`. Một chỉ mục GIN trên `jsonb` có thể hỗ trợ tìm JSON chứa cặp khóa–giá trị, nhưng một truy vấn kiểm tra sự tồn tại của key có thể cần **operator class khác**. Và hai chỉ mục có cùng các cột nhưng khác `ASC`/`DESC`/`NULLS FIRST` có thể phục vụ những kiểu sắp xếp hỗn hợp khác nhau.

Để chọn chỉ mục đúng trong PostgreSQL, cần hiểu ba khái niệm liên quan nhưng khác vai trò:

- **Operator class (opclass):** xác định tập toán tử và các hàm hỗ trợ mà một phương thức chỉ mục có thể dùng cho một kiểu dữ liệu. Ví dụ `text_ops`, `text_pattern_ops`, `jsonb_ops` và `jsonb_path_ops`.
- **Collation:** xác định quy tắc so sánh/sắp xếp một số kiểu chuỗi văn bản. Ví dụ quy tắc `"C"` khác quy tắc ngôn ngữ do hệ điều hành hoặc ICU cung cấp.
- **Thứ tự sắp xếp trong chỉ mục:** với B-tree, các khóa có thể được lưu/duyệt theo `ASC` hoặc `DESC`, và giá trị null được đặt `NULLS FIRST` hoặc `NULLS LAST`. Trong chỉ mục ghép, hướng của từng cột quyết định những `ORDER BY` được hỗ trợ trực tiếp.

Điểm then chốt: **cùng một cột có thể cần loại index khác nhau cho phép bằng, tìm tiền tố, sắp xếp theo ngôn ngữ, tìm JSON hoặc tìm chuỗi con**. Không có “một B-tree cho mọi toán tử”.

Bài học xây dựng dữ liệu lab, giới thiệu cơ chế chọn toán tử, ngữ nghĩa collation, index ordering và composite indexes; sau đó áp dụng vào `EXPLAIN`, xem catalog, thiết kế index và bài tập có đáp án. Các ví dụ hướng đến PostgreSQL hiện đại; những tính năng liên quan ICU/extension phụ thuộc build, phiên bản và quyền của môi trường thực hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích được vai trò riêng của **index access method**, **operator class**, **collation** và **thứ tự khóa**.
2. Đọc định nghĩa chỉ mục có `text_pattern_ops`, `COLLATE "C"`, `DESC NULLS LAST` hoặc `USING GIN (... jsonb_path_ops)`.
3. Phân biệt B-tree mặc định với B-tree chuyên tìm tiền tố, GIN JSONB và trigram.
4. Biết khi nào một `ORDER BY` có thể khai thác thứ tự B-tree thay vì cần `Sort`.
5. Chọn chỉ mục ghép có hướng và vị trí `NULL` phù hợp truy vấn `ORDER BY ... LIMIT`.
6. Nhận ra rủi ro khi thay collation, nâng cấp ICU/libc hoặc giả định chuỗi tiếng Việt có thứ tự cố định.
7. Kiểm tra opclass/collation hiện có qua catalog và đọc `EXPLAIN (ANALYZE, BUFFERS)`.

## 2. Mô hình một chỉ mục: nhiều quyết định khác nhau

Xét:

~~~sql
CREATE INDEX idx_example
ON example_table (
    title COLLATE "C" text_pattern_ops ASC NULLS LAST
);
~~~

Định nghĩa này kết hợp:

| Thành phần | Trong ví dụ | Trả lời câu hỏi |
| --- | --- | --- |
| Phương thức truy cập | `btree`, mặc định khi không viết `USING` | Chỉ mục được tổ chức/tìm kiếm thế nào? |
| Cột/biểu thức | `title` | Lấy giá trị nào làm khóa? |
| Collation | `"C"` | Chuỗi được so sánh theo quy tắc nào? |
| Operator class | `text_pattern_ops` | Những toán tử nào có thể dùng cấu trúc chỉ mục? |
| Thứ tự | `ASC` | B-tree giữ thứ tự tăng hay giảm theo khóa? |
| NULL placement | `NULLS LAST` | Trong chiều quét đã xác định, null đứng đầu hay cuối? |

**Đừng nhầm opclass với collation.** Operator class nối toán tử SQL với khả năng chỉ mục; collation định nghĩa quy tắc so sánh văn bản; `ASC`/`DESC` xác định chiều duyệt khóa. Một index còn có thể mang `WHERE` predicate (partial index), `INCLUDE` columns hoặc biểu thức.

### 2.1. Index không tự bảo đảm planner luôn chọn Index Scan

Một chỉ mục **có khả năng hỗ trợ** truy vấn khác với việc nó **thực tế được sử dụng**. Planner cân nhắc:

- Quy mô bảng và số hàng dự kiến trả.
- Tính chọn lọc của điều kiện lọc.
- Sắp xếp có thể được cung cấp bởi index hay cần `Sort`.
- Chi phí truy cập heap, random I/O và cache.
- Thống kê, correlation, parallelism và những phép join khác.

Vì thế, trên bảng có 10 dòng, `Seq Scan` thường hoàn toàn hợp lý dù có index đúng.

## 3. Chuẩn bị dữ liệu thực hành

Chỉ tạo schema trong database lab. Các thao tác dưới đây không dành cho bảng sản xuất.

### 3.1. Tạo bảng

~~~sql
CREATE SCHEMA idx_lab;

CREATE TABLE idx_lab.items (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL,
    title text NOT NULL,
    category text NOT NULL,
    price numeric(12, 2),
    created_at timestamptz NOT NULL,
    attrs jsonb NOT NULL DEFAULT '{}'::jsonb
);
~~~

`price` có thể null để quan sát `NULLS FIRST`/`NULLS LAST`. Cột `title` chứa cả dấu tiếng Việt, chuỗi không dấu và chữ hoa/thường.

### 3.2. Thêm dữ liệu

~~~sql
INSERT INTO idx_lab.items
    (sku, title, category, price, created_at, attrs)
VALUES
    ('CF-001', 'Cà phê rang', 'drink', 79000,
      '2026-02-01 09:00:00+07',
      '{"color":"brown","stock":15,"tags":["coffee"]}'),
    ('CF-002', 'Ca phe sua', 'drink', 45000,
      '2026-02-02 09:00:00+07',
      '{"color":"white","stock":30,"tags":["coffee","milk"]}'),
    ('CF-003', 'cà phê hòa tan', 'drink', 32000,
      '2026-02-03 09:00:00+07',
      '{"color":"brown","stock":20,"tags":["coffee"]}'),
    ('TE-001', 'Trà sen', 'drink', 55000,
      '2026-02-04 09:00:00+07',
      '{"color":"green","stock":10,"tags":["tea"]}'),
    ('BK-001', 'Sách SQL', 'book', 170000,
      '2026-02-05 09:00:00+07',
      '{"lang":"vi","stock":8,"tags":["database"]}'),
    ('BK-002', 'Sach PostgreSQL', 'book', 210000,
      '2026-02-06 09:00:00+07',
      '{"lang":"vi","stock":6,"tags":["database"]}'),
    ('BK-003', 'Index cơ bản', 'book', 125000,
      '2026-02-07 09:00:00+07',
      '{"lang":"vi","stock":12,"tags":["database"]}'),
    ('OF-001', 'Bút mực', 'office', 12000,
      '2026-02-08 09:00:00+07',
      '{"color":"blue","stock":100,"tags":["pen"]}'),
    ('OF-002', 'Bìa hồ sơ', 'office', NULL,
      '2026-02-09 09:00:00+07',
      '{"color":"red","tags":["folder"]}'),
    ('OF-003', 'Giấy ghi chú', 'office', 22000,
      '2026-02-10 09:00:00+07',
      '{"color":"yellow","stock":40,"tags":["paper"]}');
~~~

### 3.3. Kiểm tra

~~~sql
SELECT
    item_id, sku, title, category, price
FROM idx_lab.items
ORDER BY item_id;
~~~

Có 10 sản phẩm; `OF-002` thiếu giá. Kết quả sắp xếp theo `title` có thể khác nhau nếu collation mặc định khác nhau, vì thế các ví dụ **không giả định thứ tự tiếng Việt cố định**.

## 4. Index access method trước, operator class sau

Một chỉ mục PostgreSQL có **phương thức truy cập** (*access method*).

| Access method | Hình dung công dụng | Khả năng liên quan |
| --- | --- | --- |
| `btree` | Tìm bằng, khoảng, duyệt khóa có thứ tự | `=`, `<`, `<=`, `>`, `>=`, `ORDER BY` |
| `hash` | Tra cứu bằng theo toán tử phù hợp | Không cung cấp thứ tự hữu ích cho `ORDER BY` |
| `GIN` | Một giá trị có nhiều thành phần tìm kiếm, ví dụ JSONB, array, token/trigram | Toán tử phụ thuộc GIN operator class |
| `GiST` | Khung index tổng quát cho nhiều loại dữ liệu/hình học/range | Operator class quyết định tìm kiếm và một số ordered scans chuyên biệt |
| `SP-GiST` | Phân hoạch không gian tìm kiếm theo cấu trúc phù hợp | Phụ thuộc kiểu và operator class |
| `BRIN` | Tóm tắt những dải block của bảng | Tốt với dữ liệu có tính tương quan vật lý trong nhiều trường hợp |

Ví dụ:

~~~sql
CREATE INDEX idx_items_price
ON idx_lab.items USING btree (price);

CREATE INDEX idx_items_attrs_gin
ON idx_lab.items USING gin (attrs);
~~~

`USING btree` có thể bỏ vì B-tree là mặc định. Nhưng `USING gin` phải được nêu nếu muốn GIN.

### 4.1. Operator class nằm trong phương thức truy cập

Một operator class nói rằng, với **access method cụ thể**, những toán tử và support functions nào được sử dụng để xử lý một kiểu khóa.

Ví dụ, `text_pattern_ops` dành cho B-tree; `jsonb_path_ops` dành cho GIN; `gin_trgm_ops` từ extension `pg_trgm` là operator class cho GIN.

Không thể hoán đổi chúng tùy ý chỉ vì tất cả đều là “index của text hoặc JSON”.

### 4.2. Mặc định khi không chỉ rõ opclass

~~~sql
CREATE INDEX idx_items_title_default
ON idx_lab.items (title);
~~~

PostgreSQL chọn operator class mặc định thích hợp cho **kiểu text + access method B-tree** (thông thường là `text_ops`). Đây là lựa chọn phục vụ so sánh B-tree thông dụng theo collation có hiệu lực.

Nếu mục tiêu là một kiểu toán tử khác, cần xem opclass tương ứng thay vì mặc định rằng index thường dùng được.

## 5. Operator class và operator family

**Operator class** gom các toán tử và support functions cho một kiểu khóa và một access method. **Operator family** cho phép các opclass/toán tử liên quan cùng một nhóm có thể xử lý so sánh giữa nhiều kiểu tương thích.

Ví dụ thực tế: chỉ mục số nguyên đôi khi có thể được planner dùng trong biểu thức so sánh với một giá trị số nguyên thuộc kiểu khác, nhờ những toán tử/cross-type semantics được hỗ trợ. Điều này không có nghĩa **mọi cast** hoặc mọi phép so sánh đều dùng được index.

### 5.1. Toán tử SQL không đồng nghĩa một toán tử index

~~~sql
WHERE title = 'Sách SQL'
WHERE title < 'T'
WHERE title LIKE 'Sa%'
WHERE title ILIKE '%sql%'
~~~

Bốn điều kiện cùng nhắc đến `title` nhưng có thể cần **cơ chế index khác nhau**. PostgreSQL phải có toán tử hoặc cơ chế chuyển đổi điều kiện được opclass hỗ trợ và các điều kiện phụ về collation.

### 5.2. Xem danh sách opclass qua catalog

~~~sql
SELECT
    am.amname AS access_method,
    opc.opcname AS operator_class,
    opc.opcintype::regtype AS input_type,
    opc.opcdefault AS is_default
FROM pg_opclass AS opc
JOIN pg_am AS am
    ON am.oid = opc.opcmethod
WHERE opc.opcname IN (
    'text_ops',
    'text_pattern_ops',
    'varchar_pattern_ops',
    'jsonb_ops',
    'jsonb_path_ops',
    'gin_trgm_ops'
)
ORDER BY am.amname, opc.opcname, opc.opcintype::regtype::text;
~~~

Kết quả phụ thuộc extension đã cài và phiên bản PostgreSQL. Nếu chưa cài `pg_trgm` thì `gin_trgm_ops` không xuất hiện; `jsonb_ops` có thể có các định nghĩa ứng với access method khác nhau.

### 5.3. Không tự sửa hệ thống catalog

Các catalog `pg_opclass`, `pg_am` và `pg_amop` có ích để **đọc metadata**. Không chỉnh sửa trực tiếp catalog hệ thống để thêm toán tử cho index. Operator class mới là đối tượng nâng cao dành cho extension/developer có hiểu rõ access method và ngữ nghĩa so sánh.

## 6. B-tree mặc định và phép so sánh

~~~sql
CREATE INDEX idx_items_price_asc
ON idx_lab.items (price);
~~~

Các truy vấn có thể được index hỗ trợ tùy selectivity:

~~~sql
SELECT item_id, price
FROM idx_lab.items
WHERE price = 79000;

SELECT item_id, price
FROM idx_lab.items
WHERE price >= 50000 AND price < 150000;

SELECT item_id, price
FROM idx_lab.items
ORDER BY price ASC NULLS LAST
LIMIT 5;
~~~

Vì `price` có kiểu numeric, không có collation chuỗi; toán tử so sánh hoạt động theo ngữ nghĩa số.

### 6.1. Sắp xếp giá theo text có thể sai

~~~sql
SELECT
    item_id,
    price,
    price::text AS price_string
FROM idx_lab.items
ORDER BY price::text;
~~~

Thứ tự của `'12000'`, `'79000'`, `'170000'` theo **chuỗi** không trùng thứ tự số. Chỉ mục B-tree trên `price numeric` cũng không tự trở thành index của biểu thức `price::text`.

Khi cần sort theo giá tiền, **`ORDER BY price`** là biểu thức đúng hơn; chỉ format text ở bước trình bày.

### 6.2. Thay biểu thức là thay điều kiện khớp index

~~~sql
WHERE price + 1000 > 50000
~~~

khác với:

~~~sql
WHERE price > 49000
~~~

về khả năng planner dùng index trên **cột gốc**, dù hai biểu thức có thể tương đương trong miền giá phù hợp. PostgreSQL không nhất thiết biến đổi mọi hàm/biểu thức thành một index range. Hãy viết điều kiện đơn giản trên cột nếu có thể.

## 7. Collation là gì?

**Collation** là quy tắc so sánh và sắp thứ tự dữ liệu dạng chuỗi có thể collate. Nó ảnh hưởng các phép như:

~~~sql
ORDER BY title
WHERE title < 'M'
WHERE title = 'cafe'
~~~

theo cách phụ thuộc kiểu, toán tử và collation.

Ví dụ văn bản:

~~~text
Ca phe sua
Cà phê rang
cà phê hòa tan
Sách SQL
Sach PostgreSQL
~~~

Quy tắc thứ tự theo byte hoặc mã điểm không nhất thiết giống thứ tự tự nhiên của tiếng Việt. Hệ thống có thể chọn provider `libc`/ICU và locale để đáp ứng nhu cầu ngôn ngữ.

### 7.1. Xem cấu hình database

~~~sql
SHOW lc_collate;
SHOW lc_ctype;
~~~

Đây là thông tin locale nền của database. **Collation thực sự có hiệu lực đối với một cột/biểu thức** còn phụ thuộc vào collation của chính cột và mệnh đề `COLLATE` tường minh.

### 7.2. Xem collations có trong PostgreSQL

~~~sql
SELECT
    collname,
    collprovider,
    collisdeterministic,
    collversion
FROM pg_collation
WHERE collname IN ('C', 'POSIX')
ORDER BY collname;
~~~

Những cột về provider/deterministic/version có trên PostgreSQL hiện đại; catalog và tùy chọn có thể khác giữa phiên bản.

### 7.3. COLLATE trong SELECT

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title COLLATE "C", item_id;
~~~

`"C"` là một collation sẵn có, dùng thứ tự so sánh dạng C/byte-oriented, **không phải “đúng chuẩn tiếng Việt”**. Nó hữu ích khi yêu cầu thứ tự ổn định theo kiểu máy hoặc so sánh theo quy tắc C.

So sánh với:

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title, item_id;
~~~

Truy vấn thứ hai dùng collation hiệu lực mặc định của biểu thức `title`; hai thứ tự **có thể khác**.

## 8. Collation ở cấp cột và ở cấp biểu thức

Collation có thể được khai báo khi tạo cột:

~~~sql
CREATE TABLE idx_lab.labels (
    label_id integer PRIMARY KEY,
    name_c text COLLATE "C" NOT NULL,
    note text
);
~~~

Cột `name_c` dùng `"C"` làm collation khai báo.

Không cần sửa cột hiện hữu chỉ để thử collation:

~~~sql
SELECT
    title,
    title COLLATE "C" AS title_c
FROM idx_lab.items
ORDER BY title COLLATE "C";
~~~

### 8.1. COLLATE không chuyển encoding

~~~sql
SELECT title COLLATE "C"
FROM idx_lab.items;
~~~

Biểu thức này **không thay đổi byte dữ liệu lưu trong title**, không chuyển UTF-8 sang encoding khác, không loại dấu và không tự lowercase. Nó chỉ chỉ định cách so sánh/sắp xếp của biểu thức khi phù hợp.

### 8.2. COLLATE chỉ áp dụng cho kiểu hỗ trợ collation

Không gắn `COLLATE` tùy ý lên `integer` hoặc `numeric`:

~~~sql
-- Không phải cú pháp có nghĩa cho numeric:
SELECT price COLLATE "C"
FROM idx_lab.items;
~~~

Collation dành cho những kiểu có hỗ trợ so sánh theo quy tắc chuỗi như `text`, `varchar` và những loại phù hợp khác.

### 8.3. So sánh dùng collation tường minh

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE title COLLATE "C" >= 'A'
  AND title COLLATE "C" < 'N'
ORDER BY title COLLATE "C";
~~~

Trong truy vấn trên, cả điều kiện khoảng và thứ tự đều yêu cầu ngữ nghĩa `"C"`. Nếu chỉ mục hiện có dùng collation khác, không mặc nhiên khai thác được thứ tự và ranh giới so sánh từ chỉ mục ấy.

## 9. Collation và B-tree index phải tương thích

Giả sử có:

~~~sql
CREATE INDEX IF NOT EXISTS idx_items_title_default
ON idx_lab.items (title);
~~~

Truy vấn:

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title
LIMIT 10;
~~~

có thể sử dụng thứ tự của chỉ mục này nếu planner đánh giá có lợi.

Nhưng:

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title COLLATE "C"
LIMIT 10;
~~~

cần thứ tự theo **`"C"`**. Nếu collation mặc định của `title` không phải `"C"`, index mặc định không đảm bảo cùng thứ tự.

### 9.1. Tạo index với collation riêng

~~~sql
CREATE INDEX idx_items_title_c
ON idx_lab.items (title COLLATE "C");
~~~

Sau đó:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, title
FROM idx_lab.items
ORDER BY title COLLATE "C"
LIMIT 5;
~~~

Planner **có thể** cân nhắc index mới. Trên bảng 10 hàng, một `Seq Scan + Sort` vẫn có thể rẻ hơn.

### 9.2. Không coi hai collation là thay thế được

Nếu index dùng collation `"C"`, không khẳng định nó đáp ứng được mọi `ORDER BY title` theo collation ngôn ngữ khác.

Quy tắc: **ngữ nghĩa so sánh/sắp xếp của query và index phải tương thích**. Tính tương thích không chỉ được xác định bởi tên cột giống nhau.

## 10. Operator class mặc định text_ops

Với B-tree trên cột `text`:

~~~sql
CREATE INDEX idx_items_title_normal
ON idx_lab.items (title);
~~~

Định nghĩa dùng operator class mặc định (thường `text_ops`) và collation hiệu lực của cột.

Nó phù hợp với:

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE title = 'Sách SQL';
~~~

và các phép so sánh B-tree/`ORDER BY` có ngữ nghĩa tương thích.

### 10.1. Không phải LIKE nào cũng dùng index thường

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE title LIKE 'Ca%';
~~~

`LIKE 'Ca%'` là tìm **tiền tố**. Dưới một số collation không phải `C`, B-tree `text_ops` thông thường có thể **không đủ để PostgreSQL biến LIKE thành khoảng khóa phù hợp**.

Đó là một ứng dụng điển hình của `text_pattern_ops`.

### 10.2. Thứ tự text_ops theo collation

Nếu mục tiêu chính là `ORDER BY title` theo locale ngôn ngữ, index B-tree mặc định với collation đúng thường phù hợp hơn `text_pattern_ops`. Hai opclass giải quyết những bài toán khác nhau.

## 11. text_pattern_ops và LIKE 'prefix%'

~~~sql
CREATE INDEX idx_items_title_prefix
ON idx_lab.items (title text_pattern_ops);
~~~

`text_pattern_ops` là B-tree opclass hỗ trợ so sánh pattern-oriented theo ký tự thay vì dựa trên toàn bộ quy tắc thứ tự ngôn ngữ của collation mặc định. Nó được thiết kế hữu ích cho **tìm tiền tố bằng LIKE** khi locale thông thường khiến phép tối ưu trên B-tree mặc định khó áp dụng.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, title
FROM idx_lab.items
WHERE title LIKE 'Ca%';
~~~

Planner có thể chuyển phần tiền tố cố định thành điều kiện phạm vi tương ứng và vẫn kiểm tra điều kiện `LIKE` để bảo đảm kết quả.

### 11.1. Opclass pattern theo kiểu cột

| Kiểu cột | B-tree pattern opclass thường dùng |
| --- | --- |
| `text` | `text_pattern_ops` |
| `varchar` | `varchar_pattern_ops` |
| `char(n)` / `bpchar` | `bpchar_pattern_ops` |

Không chọn `text_pattern_ops` chỉ vì “nhìn thấy dữ liệu dạng chữ” khi kiểu thực tế khác và không hỗ trợ định nghĩa đó theo cách mong muốn.

### 11.2. Điều kiện có tiền tố cố định

~~~sql
WHERE title LIKE 'Ca%'
~~~

có một phần bắt đầu cố định: `Ca`.

Ngược lại:

~~~sql
WHERE title LIKE '%phe%'
~~~

bắt đầu bằng wildcard. B-tree thông thường hoặc `text_pattern_ops` **không thể dùng một khoảng tiền tố cố định** giống `LIKE 'Ca%'`.

### 11.3. Equality và range không giống nhau

`text_pattern_ops` có thể hỗ trợ phép bằng trong những bối cảnh phù hợp, nhưng **không thay thế đầy đủ** index thường cho các truy vấn phạm vi văn bản:

~~~sql
WHERE title > 'M'
ORDER BY title
~~~

được hiểu theo collation yêu cầu. Nếu workload cần cả tìm tiền tố và so sánh/sort theo locale, có thể cần **hai index chuyên biệt** hoặc cách thiết kế khác, cân nhắc chi phí ghi và dung lượng.

### 11.4. C collation có trường hợp đặc biệt

Khi collation hiệu lực là `C`, B-tree thông thường có thể phục vụ tìm tiền tố `LIKE 'abc%'` mà không cần `text_pattern_ops` riêng. Đây là lý do **phải biết collation thực tế** trước khi tạo thêm index theo hướng dẫn máy móc.

## 12. Kết hợp COLLATE "C" và pattern_ops

Cú pháp:

~~~sql
CREATE INDEX idx_items_title_c_pattern
ON idx_lab.items (
    title COLLATE "C" text_pattern_ops
);
~~~

Một chỉ mục gồm khóa `title`, collation `"C"` và opclass B-tree pattern.

### 12.1. Khi nào có ích?

Khi ứng dụng cố ý muốn quy tắc so sánh dạng `"C"` và tìm tiền tố, có thể thiết kế các expression/index key nhất quán theo quy tắc đó.

Tuy vậy, trên `C` collation, B-tree mặc định vốn đã có khả năng tốt cho prefix LIKE trong nhiều tình huống, nên **không tự coi thêm pattern_ops là cải thiện bắt buộc**. Cần xem query thực tế và EXPLAIN.

### 12.2. Không mặc định index đáp ứng mọi ORDER BY

Index dùng `text_pattern_ops` được tối ưu cho semantics pattern; nó không tự thay cho index B-tree `text_ops` phục vụ `ORDER BY title` với collation ngôn ngữ khác.

Quan trọng hơn tên index là **toán tử, collation và cách comparator của opclass**.

## 13. Tìm kiếm không phân biệt hoa/thường

`ILIKE` thường được dùng khi muốn so khớp text không phân biệt hoa/thường:

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE title ILIKE 'ca%';
~~~

Không suy rằng một index B-tree thường trên `title` luôn hỗ trợ tốt mọi `ILIKE`. Trong nhiều workload, một lựa chọn có thể là **chuẩn hóa biểu thức bằng `lower`**:

~~~sql
CREATE INDEX idx_items_lower_title_prefix
ON idx_lab.items (
    (lower(title)) text_pattern_ops
);
~~~

Query phải dùng biểu thức phù hợp:

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE lower(title) LIKE 'ca%';
~~~

### 13.1. Kết quả case-folding phụ thuộc locale

`lower`/`upper` có quy tắc ngôn ngữ/collation liên quan. Không khẳng định chúng đồng nhất mọi biến thể Unicode, dấu tiếng Việt hoặc tất cả quy tắc case-folding trên mọi ngôn ngữ.

### 13.2. Truy vấn và index phải khớp biểu thức

~~~sql
WHERE lower(title) LIKE 'ca%'
~~~

có khả năng khớp index trên `lower(title)`.

Nhưng:

~~~sql
WHERE title ILIKE 'ca%'
~~~

không tự chuyển thành một điều kiện trên expression index `lower(title)` ở mọi phiên bản/cách thực thi. Hãy đo plan của **SQL ứng dụng thực sự gửi**.

### 13.3. Đừng chuẩn hóa dữ liệu mất dấu một cách tùy tiện

Nếu nghiệp vụ cần tìm kiếm tiếng Việt không phân biệt dấu, điều đó là **yêu cầu khác** với không phân biệt chữ hoa. Có thể cần ICU collation, normalization, unaccent hoặc search index chuyên dụng, với đánh đổi về độ đúng, khả năng index và phiên bản. Không tự bỏ dấu trong dữ liệu nguồn nếu mất thông tin là không chấp nhận được.

## 14. Trigram cho LIKE '%substring%'

Extension `pg_trgm` cung cấp operator classes dùng cho tìm kiếm dựa trên trigram, hữu ích với một số truy vấn `LIKE`, `ILIKE`, regex và similarity.

Trong lab, nếu có quyền cài extension:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_items_title_trgm
ON idx_lab.items
USING gin (title gin_trgm_ops);
~~~

Sau đó:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, title
FROM idx_lab.items
WHERE title ILIKE '%phe%';
~~~

GIN trigram index **có thể** hỗ trợ tìm chuỗi con không có tiền tố cố định, điều B-tree prefix index không làm giống được.

### 14.1. Trigram không phải phép màu

Chi phí và khả năng dùng index phụ thuộc:

- Pattern có đủ trigram có thể trích ra không.
- Độ dài từ khóa, wildcard và ký tự đặc biệt.
- Số lượng hàng, tỷ lệ khớp, ngôn ngữ dữ liệu.
- GIN maintenance, dung lượng và tần suất cập nhật.

Với pattern quá ngắn hoặc không trích được trigram hữu ích, planner có thể không được lợi từ index. **GIN trigram không cung cấp thứ tự B-tree để đáp ứng `ORDER BY title`**.

### 14.2. Prefix vs substring

| Truy vấn chính | Hướng index thường xem xét |
| --- | --- |
| `title = 'Sách SQL'` | B-tree text mặc định |
| `title LIKE 'Ca%'` | B-tree thích hợp theo collation, có thể `text_pattern_ops` |
| `lower(title) LIKE 'ca%'` | Expression B-tree `lower(title) text_pattern_ops` |
| `title ILIKE '%sql%'` | GIN/GiST trigram khi dữ liệu và pattern phù hợp |
| `ORDER BY title COLLATE "C"` | B-tree với collation tương thích |

Một hệ thống có thể dùng nhiều kỹ thuật khác nhau tùy **query pattern**, nhưng đừng tạo tất cả index chỉ vì chúng tồn tại.

## 15. JSONB operator class: jsonb_ops và jsonb_path_ops

Đối với `jsonb`, GIN là một lựa chọn phổ biến:

~~~sql
CREATE INDEX idx_items_attrs_ops
ON idx_lab.items
USING gin (attrs jsonb_ops);
~~~

`jsonb_ops` là GIN operator class mặc định phổ biến cho `jsonb`. Nó hỗ trợ nhiều toán tử JSONB:

~~~sql
SELECT sku
FROM idx_lab.items
WHERE attrs @> '{"color":"brown"}'::jsonb;

SELECT sku
FROM idx_lab.items
WHERE attrs ? 'stock';
~~~

### 15.1. jsonb_path_ops

~~~sql
CREATE INDEX idx_items_attrs_path
ON idx_lab.items
USING gin (attrs jsonb_path_ops);
~~~

`jsonb_path_ops` tập trung vào một tập operator JSONB nhỏ hơn, thường có thể tạo index gọn và hiệu quả cho các truy vấn containment/JSON path phù hợp, tùy cấu trúc dữ liệu.

~~~sql
SELECT sku
FROM idx_lab.items
WHERE attrs @> '{"color":"brown"}'::jsonb;
~~~

có thể dùng một GIN index thích hợp với `jsonb_path_ops`.

Nhưng:

~~~sql
SELECT sku
FROM idx_lab.items
WHERE attrs ? 'stock';
~~~

**không được hỗ trợ bởi `jsonb_path_ops` theo cùng cách với `jsonb_ops`**, vì toán tử existence `?` không nằm trong tập chiến lược mà opclass này cung cấp.

### 15.2. Bảng chọn nhanh

| Nhu cầu | `jsonb_ops` | `jsonb_path_ops` |
| --- | --- | --- |
| Containment `@>` | Có | Có |
| JSON path matching `@?`/`@@` ở phiên bản hỗ trợ | Có | Có |
| Key existence `?`, `?|`, `?&` | Có | Không |
| Phạm vi toán tử được index hỗ trợ | Rộng hơn | Hẹp hơn |
| Kích thước và tính chọn lọc | Tùy workload | Có thể gọn/hiệu quả hơn cho containment phù hợp |

Đừng quyết định opclass chỉ dựa trên dung lượng index. Nếu ứng dụng sử dụng `attrs ? 'stock'` rất thường xuyên, chọn `jsonb_path_ops` đơn lẻ có thể gây bất lợi dù một truy vấn `@>` riêng chạy nhanh.

### 15.3. Hai GIN index cùng cột có chi phí

Các ví dụ đã tạo hai index để **minh họa sự khác nhau**. Trên production, mỗi GIN index thêm chi phí ghi, VACUUM, lưu trữ và bảo trì. Nên giữ bộ index **đúng toán tử mà workload cần**, không sao chép tất cả ví dụ.

### 15.4. GIN không thay ORDER BY

~~~sql
WHERE attrs @> '{"color":"brown"}'
ORDER BY created_at DESC
LIMIT 10
~~~

GIN có thể giúp tìm item chứa JSON phù hợp, nhưng **không tự cung cấp thứ tự created_at** cho query. Planner có thể phải sort kết quả hoặc phối hợp cách truy cập khác.

## 16. ASC, DESC và NULLS trong B-tree

Mặc định của một khóa B-tree khi không chỉ định:

~~~sql
CREATE INDEX idx_items_price_default
ON idx_lab.items (price);
~~~

tương đương ý định sắp thứ tự:

~~~sql
CREATE INDEX idx_items_price_explicit
ON idx_lab.items (price ASC NULLS LAST);
~~~

Hai lệnh trên tạo **hai index riêng** nếu chạy cả hai; chúng được viết để so sánh cú pháp, không phải khuyên tạo trùng.

### 16.1. Mặc định của ORDER BY

Trong PostgreSQL:

| ORDER BY | Null placement mặc định |
| --- | --- |
| `ORDER BY price ASC` | `NULLS LAST` |
| `ORDER BY price DESC` | `NULLS FIRST` |
| `ORDER BY price ASC NULLS FIRST` | Tường minh null lên đầu |
| `ORDER BY price DESC NULLS LAST` | Tường minh null xuống cuối |

Vì có `price = NULL` cho item `OF-002`, truy vấn:

~~~sql
SELECT sku, price
FROM idx_lab.items
ORDER BY price DESC NULLS LAST;
~~~

sẽ giữ item có giá null **ở cuối**.

### 16.2. Scan B-tree theo hai chiều

B-tree có thể được duyệt **forward** hoặc **backward**:

~~~text
Index: price ASC NULLS LAST

Forward scan  -> price ASC NULLS LAST
Backward scan -> price DESC NULLS FIRST
~~~

Vì vậy, để phục vụ `ORDER BY price DESC` mặc định, **không nhất thiết cần tạo một index DESC khác** trên một cột đơn.

Tuy nhiên:

~~~sql
ORDER BY price DESC NULLS LAST
~~~

không tương đương chiều quét ngược của `ASC NULLS LAST` về vị trí null. Nếu thứ tự null quan trọng, có thể cần index khai báo hướng/null phù hợp, hoặc bước sort khác.

### 16.3. Index DESC NULLS LAST

~~~sql
CREATE INDEX idx_items_price_desc_last
ON idx_lab.items (price DESC NULLS LAST);
~~~

Index này có hướng forward phù hợp:

~~~sql
SELECT sku, price
FROM idx_lab.items
ORDER BY price DESC NULLS LAST
LIMIT 5;
~~~

Planner có thể lấy những hàng đầu của index thay vì đọc/sort toàn bảng, nhất là khi dữ liệu lớn và `LIMIT` nhỏ.

## 17. Chỉ mục ghép và ORDER BY nhiều cột

Một B-tree index:

~~~sql
CREATE INDEX idx_items_category_price
ON idx_lab.items (
    category ASC,
    price DESC NULLS LAST,
    item_id ASC
);
~~~

có thể phục vụ thứ tự:

~~~sql
SELECT item_id, category, price
FROM idx_lab.items
ORDER BY
    category ASC,
    price DESC NULLS LAST,
    item_id ASC;
~~~

Index có thứ tự **hỗn hợp**: category tăng, giá giảm, ID tăng.

### 17.1. Quét ngược đảo tất cả thành phần

Nếu index lưu:

~~~text
category ASC,
price DESC NULLS LAST,
item_id ASC
~~~

thì chiều quét ngược cho thứ tự đối ứng:

~~~text
category DESC,
price ASC NULLS FIRST,
item_id DESC
~~~

Không thể dùng một thao tác **đảo toàn bộ scan** để lấy một tổ hợp bất kỳ như:

~~~sql
ORDER BY category ASC, price ASC
~~~

nếu index không có hướng phù hợp. Planner có thể vẫn dùng một phần thứ tự rồi sort/incremental sort tùy trường hợp.

### 17.2. Khi có điều kiện bằng trên cột đầu

~~~sql
SELECT sku, title, price
FROM idx_lab.items
WHERE category = 'book'
ORDER BY price DESC NULLS LAST, item_id ASC
LIMIT 3;
~~~

Vì `category` được cố định bằng điều kiện `= 'book'`, phần index còn lại có thứ tự `price DESC NULLS LAST, item_id ASC` hữu ích cho query.

Đây là mẫu quan trọng cho trang “Top N sản phẩm theo giá trong một danh mục”.

### 17.3. Khóa phá hòa cho phân trang

Nếu hai item cùng `price`, chỉ:

~~~sql
ORDER BY price DESC
~~~

không cho thứ tự xác định giữa chúng. Thêm `item_id`:

~~~sql
ORDER BY price DESC NULLS LAST, item_id ASC
~~~

giúp phân trang ổn định trong cùng một snapshot và hỗ trợ truy vết cursor.

Tuy vậy, khi dữ liệu **được chèn/xóa/thay đổi đồng thời**, kể cả `ORDER BY` xác định cũng không tự khiến OFFSET pagination tránh được dịch chuyển hàng giữa những request.

## 18. Quy tắc cột đầu của index ghép

Index B-tree trên:

~~~sql
(category, price DESC, item_id)
~~~

có thứ tự từ trái sang phải. Nếu truy vấn dùng:

~~~sql
WHERE category = 'book'
ORDER BY price DESC, item_id
~~~

thì điều kiện trên cột đầu giúp khai thác các cột tiếp theo.

Nếu query chỉ:

~~~sql
ORDER BY price DESC
~~~

trên **toàn bộ bảng nhiều category**, index trên `(category, price)` **không đảm bảo thứ tự giá toàn cục** vì giá được nhóm theo category trước. Có thể vẫn dùng index cho mục đích khác, nhưng không thể coi thứ tự từ index là `ORDER BY price` toàn cục.

### 18.1. Không biến “leftmost prefix” thành luật cấm tuyệt đối

PostgreSQL có nhiều chiến lược, bao gồm index scanning, bitmap scans, incremental sort, và trên những phiên bản/điều kiện nhất định có thể khai thác skip scan. Một query bỏ cột dẫn đầu vẫn có thể dùng index trong một số trường hợp.

Nguyên tắc thiết kế chính xác hơn: **điều kiện trên các cột đầu và thứ tự truy vấn có tác động lớn tới hiệu quả và khả năng cung cấp đúng ORDER BY**; phải đọc plan thực tế.

### 18.2. Index dành cho filter và index dành cho sort

Có truy vấn rất chọn lọc theo `sku`:

~~~sql
WHERE sku = 'BK-001'
~~~

Khi trả một hàng, index tìm `sku` có ích; không cần index hướng `DESC` phức tạp.

Nhưng bảng danh sách:

~~~sql
WHERE category = 'book'
ORDER BY price DESC NULLS LAST
LIMIT 20
~~~

có thể hưởng lợi từ **index tổ hợp filter + order**. Chọn index theo **toàn query pattern**, không theo từng cột riêng lẻ.

## 19. LIMIT, top-N và chi phí Sort

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, title, price
FROM idx_lab.items
WHERE category = 'drink'
ORDER BY price DESC NULLS LAST, item_id
LIMIT 3;
~~~

Nếu planner dùng index có thứ tự phù hợp, nó có thể dừng sau khi đã tìm đủ những hàng cần cho `LIMIT`, tùy bộ lọc và cách thực thi. Nếu không có index phù hợp, planner có thể chọn `Sort` (trong đó có thể có chiến lược top-N sort) hoặc một hướng khác.

### 19.1. LIMIT không đảm bảo index nhanh

Nếu `WHERE` ít chọn lọc hoặc index cần đọc nhiều hàng rồi kiểm tra điều kiện, lợi ích có thể giảm. Nếu bảng chỉ có 10 hàng, đọc tất cả rồi sort thường rất rẻ.

### 19.2. Incremental Sort

Khi đầu vào đã sắp theo **một tiền tố** của `ORDER BY`, planner có thể sử dụng `Incremental Sort` trong những phiên bản/tình huống phù hợp thay vì sort lại toàn bộ tập hàng theo mọi khóa.

Một phần index được khớp không đồng nghĩa mọi cột sort đều miễn phí. Xem kế hoạch để biết có `Sort`/`Incremental Sort` hay không.

## 20. ORDER BY trên biểu thức và expression index

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY lower(title);
~~~

Nếu có index chỉ trên `title`, không mặc nhiên đáp ứng thứ tự của `lower(title)`.

Có thể tạo expression index:

~~~sql
CREATE INDEX idx_items_lower_title
ON idx_lab.items (lower(title));
~~~

Sau đó:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, title
FROM idx_lab.items
ORDER BY lower(title)
LIMIT 5;
~~~

### 20.1. Expression và collation phải tương thích

Nếu query yêu cầu:

~~~sql
ORDER BY lower(title) COLLATE "C"
~~~

có thể tạo:

~~~sql
CREATE INDEX idx_items_lower_title_c
ON idx_lab.items (
    (lower(title)) COLLATE "C"
);
~~~

Đừng suy một index `lower(title)` có collation mặc định khác tự bảo đảm thứ tự `"C"`.

### 20.2. Expression index cũng có chi phí ghi

Mỗi lần `INSERT`/`UPDATE` ảnh hưởng biểu thức khóa, PostgreSQL cần duy trì index tương ứng. Ngoài ra, expression index yêu cầu biểu thức dùng những hàm/biểu thức thỏa điều kiện về tính bất biến (*immutability*) của index.

Không được tùy tiện đưa một hàm phụ thuộc session/timezone hay trạng thái biến đổi vào expression index và kỳ vọng PostgreSQL chấp nhận.

## 21. INCLUDE columns không quyết định sort

PostgreSQL B-tree có thể chứa **non-key columns** để phục vụ một số index-only scans:

~~~sql
CREATE INDEX idx_items_category_price_covering
ON idx_lab.items (
    category,
    price DESC NULLS LAST,
    item_id
)
INCLUDE (sku, title);
~~~

`category`, `price`, `item_id` là **key columns** ảnh hưởng thứ tự/khả năng tìm kiếm.

`sku` và `title` trong `INCLUDE` chỉ là **cột dữ liệu đính kèm**, không đóng vai trò phần tiếp theo của `ORDER BY` và không được dùng như key predicate theo cách tương đương.

### 21.1. Index-only scan không chỉ phụ thuộc INCLUDE

Muốn một query dùng `Index Only Scan`, còn phụ thuộc:

- Những cột cần đọc có sẵn trong index.
- Access method hỗ trợ kiểu scan đó.
- Trạng thái visibility map/heap và MVCC cho phép tránh hoặc giảm truy cập heap.
- Chi phí thực tế theo planner.

**Index covering không bảo đảm mọi query trở thành Index Only Scan.**

### 21.2. Đừng INCLUDE quá nhiều cột

Cột payload tăng dung lượng index và chi phí ghi; giá trị lớn có thể vượt giới hạn entry, gây lỗi khi index creation/maintenance. Chỉ INCLUDE những cột có lợi ích thực tế rõ ràng.

## 22. Collation deterministic và nondeterministic

Trong PostgreSQL hiện đại, các collation có thể có tính chất **deterministic** hoặc **nondeterministic**. Một ICU collation nondeterministic có thể được dùng để so sánh chuỗi theo những quy tắc tương đương mà byte khác nhau vẫn được coi như bằng nhau.

Ví dụ mục tiêu nghiệp vụ:

- Không phân biệt chữ hoa/thường.
- Không phân biệt dấu ở mức độ được chọn.
- Xử lý một số cách biểu diễn Unicode tương đương.

Không nên tự khẳng định một collation bất kỳ giải quyết đồng thời **cả ba**. Phải kiểm tra locale/strength/normalization và quy tắc ứng dụng.

### 22.1. ICU collation tùy chọn

Nếu PostgreSQL được build với ICU và user có quyền:

~~~sql
CREATE COLLATION idx_lab.name_ci (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);
~~~

Mẫu locale trên hướng tới so sánh bỏ qua khác biệt chữ hoa/thường ở mức strength tương ứng, nhưng vẫn có thể phân biệt dấu. Tính năng phụ thuộc phiên bản ICU/PostgreSQL; **không coi ví dụ tùy chọn là bước bắt buộc trong mọi lab**.

### 22.2. Sử dụng collation

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title COLLATE idx_lab.name_ci, item_id;
~~~

Và nếu có nhu cầu truy vấn/collation ấy thường xuyên:

~~~sql
CREATE INDEX idx_items_title_ci
ON idx_lab.items (title COLLATE idx_lab.name_ci);
~~~

### 22.3. Tác động tới UNIQUE và so sánh bằng

Một **unique B-tree index** trên text dùng nondeterministic collation có thể coi những chuỗi mà collation đánh giá là tương đương là **trùng khóa**, dù biểu diễn byte khác nhau.

Điều này có thể hữu ích cho tên/ngữ nghĩa không phân biệt chữ, nhưng cần chính sách thống nhất từ lúc import tới lúc kiểm tra uniqueness. Đừng áp dụng thay đổi collation lên bảng hiện có mà chưa phân tích những giá trị có thể trở thành trùng.

### 22.4. Pattern matching có giới hạn tùy phiên bản

Một số phiên bản PostgreSQL có hạn chế hoặc khác biệt về hỗ trợ `LIKE`/regex với **nondeterministic collation**. Không tự suy rằng mọi toán tử pattern và mọi opclass sẽ dùng được giống collation deterministic.

Nếu ứng dụng cần cả equality case-insensitive và tìm substring, hãy **kiểm tra chính xác phiên bản và plan**; có thể cần expression index, trigram, normalization hoặc chiến lược search riêng.

## 23. Collation version và nâng cấp ICU/libc

Quy tắc sắp xếp phụ thuộc phiên bản thư viện collation (ICU hoặc libc) có thể thay đổi khi nâng cấp hệ điều hành, PostgreSQL hoặc ICU. Nếu một B-tree index được xây theo quy tắc cũ nhưng quy tắc comparator đã đổi, thứ tự index có thể không còn phù hợp với phép so sánh mới.

Hậu quả tiềm ẩn:

- Kết quả `ORDER BY` hoặc tìm kiếm dựa vào index không còn đúng theo quy tắc mới.
- Unique index có thể có hành vi bất nhất với khái niệm “trùng” mới.
- Một số query/index có thể cần xây dựng lại.

### 23.1. Kiểm tra catalog version

~~~sql
SELECT
    collname,
    collprovider,
    collversion,
    pg_collation_actual_version(oid) AS actual_version
FROM pg_collation
WHERE collname = 'name_ci'
   OR collname = 'C'
ORDER BY collname;
~~~

Tên collation có thể trùng giữa các schema; nếu kiểm tra trong hệ thống thật, cần lọc theo `collnamespace`/schema chính xác. Có collation không có version hữu ích (null) và kết quả phụ thuộc provider.

### 23.2. REINDEX rồi mới refresh metadata

Nếu quy tắc collation đã đổi, cần **đánh giá và xây dựng lại những index phụ thuộc**, chẳng hạn dùng `REINDEX` theo quy trình vận hành phù hợp. Chỉ:

~~~sql
ALTER COLLATION idx_lab.name_ci REFRESH VERSION;
~~~

**không tự xây lại index**; nó cập nhật metadata version sau khi các điều kiện tương thích đã được xử lý.

Đừng chạy lệnh refresh chỉ để xóa cảnh báo mà bỏ qua index cần rebuild. Với database default collation, có thêm cơ chế theo dõi/refresh ở mức database tùy phiên bản, cần áp dụng theo tài liệu và quy trình nâng cấp thực tế.

### 23.3. REINDEX có ảnh hưởng vận hành

`REINDEX` thông thường có thể giữ khóa ảnh hưởng truy cập; `REINDEX CONCURRENTLY` có đặc tính và giới hạn riêng. Trước khi chạy trên production, xác định thứ tự, phạm vi, dung lượng đĩa, khả năng tạm dừng và kế hoạch phục hồi.

## 24. Dùng pg_indexes xem định nghĩa thực tế

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'idx_lab'
  AND tablename = 'items'
ORDER BY indexname;
~~~

`indexdef` giúp đọc lại `USING gin`, `COLLATE`, opclass tường minh, biểu thức `lower(title)`, thứ tự `DESC NULLS LAST` và `INCLUDE` nếu có.

### 24.1. Đừng chỉ đoán theo tên index

Tên như `idx_items_title_prefix` **không chứng minh** index dùng `text_pattern_ops` nếu schema có thể đã thay đổi. Định nghĩa thật nằm trong catalog, không nằm trong convention đặt tên.

### 24.2. pg_get_indexdef

~~~sql
SELECT
    idx.indexrelid::regclass AS index_name,
    pg_get_indexdef(idx.indexrelid) AS definition
FROM pg_index AS idx
WHERE idx.indrelid = 'idx_lab.items'::regclass
ORDER BY idx.indexrelid::regclass::text;
~~~

Hàm `pg_get_indexdef` trả câu định nghĩa index từ metadata. Nó hữu ích khi cần so sánh hai index gần giống nhau về cột nhưng khác opclass hoặc collation.

## 25. Xem opclass/collation của từng key

Với PostgreSQL hiện đại, `pg_index` lưu các OID opclass và collation của các **key columns**. Có thể đọc metadata:

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    pos.key_position + 1 AS key_number,
    pg_get_indexdef(
        i.indexrelid,
        pos.key_position + 1,
        true
    ) AS key_definition,
    opc.opcname AS operator_class,
    coll.collname AS collation_name
FROM pg_index AS i
CROSS JOIN LATERAL
    generate_series(0, i.indnkeyatts - 1)
    AS pos(key_position)
JOIN pg_opclass AS opc
    ON opc.oid = i.indclass[pos.key_position]
LEFT JOIN pg_collation AS coll
    ON coll.oid = i.indcollation[pos.key_position]
WHERE i.indrelid = 'idx_lab.items'::regclass
ORDER BY i.indexrelid::regclass::text, pos.key_position;
~~~

Ý nghĩa:

- `indnkeyatts` là số **key columns**, không kể `INCLUDE` payload columns.
- `indclass` chứa OID opclass cho khóa.
- `indcollation` chứa collation cho khóa có hỗ trợ collation; khóa numeric có thể không có OID collation.
- `pg_get_indexdef(..., key_number, true)` hiển thị biểu thức khóa.

### 25.1. Vì sao không lấy INCLUDE trong cùng vòng lặp?

`INCLUDE` columns có thể nằm trong tổng số thuộc tính index nhưng **không phải search/sort keys** và không có vai trò opclass giống key columns. Nếu muốn phân tích thứ tự/opclass, dùng `indnkeyatts` thay vì nhầm với toàn bộ `indnatts`.

## 26. Đọc EXPLAIN để xác minh index có phù hợp

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, price
FROM idx_lab.items
WHERE category = 'book'
ORDER BY price DESC NULLS LAST, item_id
LIMIT 3;
~~~

Trong plan có thể gặp:

| Dấu hiệu | Ý nghĩa |
| --- | --- |
| `Index Scan using ...` | Planner đang dùng index để tìm/duyệt |
| `Index Only Scan` | Có khả năng trả dữ liệu từ index với quy tắc MVCC |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Dùng index để tìm vị trí hàng, thường không giữ thứ tự B-tree đầu ra |
| `Seq Scan` | Đọc tuần tự bảng |
| `Sort` | Có bước sắp xếp riêng |
| `Incremental Sort` | Tận dụng tiền tố đã có thứ tự khi phù hợp |
| `Index Cond` | Điều kiện có thể được index xử lý |
| `Filter` | Điều kiện kiểm tra sau bước lấy hàng tương ứng |
| `Buffers` | Số block/buffer hit/read/dirtied/written theo node |

### 26.1. Index dùng để filter chưa chắc dùng để order

Một truy vấn dùng GIN `attrs @> ...` có thể sử dụng index tìm hàng, rồi `Sort` theo `created_at`. Đừng diễn giải “dùng index” là “không có sort”.

### 26.2. Index scan có thể duyệt ngược

Trong plan, một `Index Scan Backward` cho thấy PostgreSQL dùng chiều ngược của B-tree khi thích hợp. Đây là bằng chứng trực tiếp rằng không phải cứ `ORDER BY DESC` là cần index khai báo DESC.

### 26.3. Đừng ép planner để kết luận hiệu năng production

Có thể dùng một số tham số planner trong thí nghiệm để khảo sát lựa chọn, nhưng việc tắt `enable_seqscan` không phải cách tối ưu chính thức. Khi dữ liệu nhỏ, `Seq Scan` có thể rẻ; đánh giá trên tập dữ liệu đại diện với thống kê thực tế.

## 27. Thêm dữ liệu lớn hơn để xem plan

Lab 10 hàng thường quá nhỏ để planner cần index. Nếu muốn có ví dụ lớn hơn, có thể chủ động thêm **10.000 item giả** trong database thử nghiệm:

~~~sql
INSERT INTO idx_lab.items (
    sku, title, category, price, created_at, attrs
)
SELECT
    'AUTO-' || lpad(g::text, 6, '0'),
    'Item ' || g::text,
    CASE
        WHEN g % 3 = 0 THEN 'book'
        WHEN g % 3 = 1 THEN 'drink'
        ELSE 'office'
    END,
    CASE
        WHEN g % 20 = 0 THEN NULL
        ELSE (10000 + (g % 500) * 100)::numeric(12,2)
    END,
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
        + (g * INTERVAL '1 minute'),
    jsonb_build_object(
        'source', 'generated',
        'group', g % 5
    )
FROM generate_series(1, 10000) AS s(g);

ANALYZE idx_lab.items;
~~~

**Chỉ chạy nếu muốn quan sát plan trên dữ liệu lớn hơn.** Những truy vấn thống kê đếm 10 item ban đầu sẽ không còn trả số cũ sau khi chạy đoạn này.

### 27.1. So sánh hai truy vấn sau khi tăng dữ liệu

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, price
FROM idx_lab.items
WHERE category = 'book'
ORDER BY price DESC NULLS LAST, item_id
LIMIT 10;
~~~

và:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, price
FROM idx_lab.items
WHERE category = 'book'
ORDER BY price ASC NULLS FIRST, item_id
LIMIT 10;
~~~

Index có thứ tự `(category ASC, price DESC NULLS LAST, item_id ASC)` không bảo đảm hỗ trợ đầy đủ cả **hai kiểu sắp xếp** bằng cùng hướng quét. So sánh `Sort`, `Index Scan` và tổng thời gian.

### 27.2. Dữ liệu giả không thay workload thực

Dữ liệu được sinh đều và có phân bố đơn giản. Kết luận production phải dựa trên kích thước, phân bố, tần suất và query thực, không từ vài chục mili giây lab.

## 28. Kết hợp WHERE, ORDER BY, LIMIT và collation

Một truy vấn ví dụ:

~~~sql
SELECT sku, title, price
FROM idx_lab.items
WHERE category = 'book'
  AND price >= 100000
ORDER BY price DESC NULLS LAST, item_id
LIMIT 20;
~~~

Phân tích theo thứ tự:

1. `category = 'book'` là equality filter trên cột đầu.
2. `price >= 100000` là điều kiện range trên khóa giá.
3. `ORDER BY price DESC NULLS LAST, item_id` yêu cầu kết quả theo giá giảm, ID tăng.
4. `LIMIT 20` có thể khiến index ordered scan có lợi.

Nếu query khác:

~~~sql
SELECT sku, title
FROM idx_lab.items
WHERE lower(title) LIKE 'sa%'
ORDER BY title COLLATE "C"
LIMIT 20;
~~~

thì ta có **hai mục tiêu**:

- Tìm tiền tố trên biểu thức `lower(title)`.
- Sắp theo `title COLLATE "C"`, một khóa khác.

Một index đơn lẻ trên `lower(title) text_pattern_ops` có thể giúp lọc, nhưng **không mặc nhiên đáp ứng order trên title gốc**. Có thể cần sort, hoặc thiết kế query/index khác.

## 29. Những sai lầm thường gặp

### Lỗi 1. Nghĩ opclass và collation là một

`text_pattern_ops` xác định cách index hỗ trợ toán tử pattern; `"C"` xác định collation. Chúng là hai thành phần khác nhau của khóa chỉ mục.

### Lỗi 2. Tạo B-tree mặc định rồi kỳ vọng LIKE nào cũng nhanh

`LIKE 'abc%'` khác `LIKE '%abc%'`. Prefix có thể dùng B-tree pattern; substring thường cần trigram hoặc một search strategy khác.

### Lỗi 3. Bỏ qua locale khi dùng LIKE prefix

Ở locale không phải C, B-tree mặc định có thể không hỗ trợ pattern prefix như kỳ vọng; hãy cân nhắc `text_pattern_ops` và EXPLAIN.

### Lỗi 4. Dùng text_pattern_ops cho mọi ORDER BY

Pattern ordering không thay thế hoàn toàn locale-aware B-tree ordering. Nếu cần sort đúng theo collation ngôn ngữ, phải có index phù hợp.

### Lỗi 5. Dùng ILIKE nhưng chỉ có expression index lower(title)

Planner không nhất thiết biến `title ILIKE ...` thành `lower(title) LIKE ...` để dùng index ấy. Viết biểu thức tương ứng với index hoặc chọn trigram.

### Lỗi 6. Coi lower() là bỏ dấu

Chuyển hoa/thường khác bỏ dấu tiếng Việt; hai mục tiêu cần xử lý riêng.

### Lỗi 7. Giả định ORDER BY title giống nhau trên mọi máy

Collation và phiên bản thư viện ảnh hưởng so sánh. Không hardcode kết quả sắp xếp tiếng Việt nếu môi trường chưa xác định.

### Lỗi 8. Sử dụng index khác collation với query

`ORDER BY title COLLATE "C"` không nhất thiết dùng được index có collation ngôn ngữ khác.

### Lỗi 9. Tưởng DESC luôn cần index DESC mới

B-tree có thể quét ngược. Với một khóa `ASC NULLS LAST`, quét ngược cho `DESC NULLS FIRST`.

### Lỗi 10. Quên NULLS FIRST/LAST

`DESC` mặc định đặt null lên đầu; truy vấn `DESC NULLS LAST` có khác biệt thực tế, đặc biệt với cột nullable.

### Lỗi 11. Nghĩ index ghép sắp được mọi tổ hợp

Index `(category ASC, price DESC)` không bảo đảm `ORDER BY price DESC` **toàn bảng** vì category đứng trước.

### Lỗi 12. Không dùng khóa phá hòa

Nếu nhiều item đồng giá, `ORDER BY price DESC` chưa đủ cho một thứ tự toàn phần. Thêm ID ổn định khi cần.

### Lỗi 13. INCLUDE ảnh hưởng thứ tự

`INCLUDE (title)` không biến title thành khóa sort. Chỉ key columns và cấu hình của chúng quyết định thứ tự index.

### Lỗi 14. Chọn jsonb_path_ops cho truy vấn ?

`jsonb_path_ops` không index key existence `?` theo cách `jsonb_ops` làm. Chọn opclass theo toán tử thực tế.

### Lỗi 15. Nghĩ GIN JSONB giúp ORDER BY

GIN xử lý các toán tử tìm kiếm phù hợp, không thay B-tree cho thứ tự sắp xếp thông dụng.

### Lỗi 16. Tạo nhiều index giống nhau vì EXPLAIN ở lab chọn Seq Scan

Bảng nhỏ có thể scan tuần tự rẻ hơn. Không dùng kết quả từ 10 dòng để kết luận thiếu opclass hoặc index sai.

### Lỗi 17. Đổi collation rồi chỉ REFRESH VERSION

`ALTER COLLATION ... REFRESH VERSION` không xây lại index. Phải xử lý các index phụ thuộc khi comparator thay đổi.

### Lỗi 18. Giả định nondeterministic collation hỗ trợ mọi LIKE/regex

Hỗ trợ toán tử pattern thay đổi theo phiên bản và loại collation. Phải kiểm tra môi trường cụ thể.

### Lỗi 19. Cast cột trong WHERE/ORDER BY mà quên index biểu thức

`price::text` hay `lower(title)` không phải cùng key với cột gốc cho mọi phép tìm/sort. Viết query đơn giản hoặc tạo index biểu thức thích hợp.

### Lỗi 20. Dùng REINDEX CONCURRENTLY trong transaction script tùy tiện

Các thao tác concurrent index maintenance có giới hạn môi trường transaction và ảnh hưởng vận hành riêng. Đọc chính sách của lệnh và lên kế hoạch migration.

## 30. Bài tập thực hành

Các bài tập dựa trên schema `idx_lab`. Những bài thêm index chỉ thực hiện trong database lab. Nếu đã chèn 10.000 dòng ở phần 27, hãy đánh giá theo tập dữ liệu sau khi bổ sung.

### Bài 1. Giải thích thành phần index

Trong `CREATE INDEX ... ON t (title COLLATE "C" text_pattern_ops DESC NULLS LAST)`, hãy chỉ ra access method, collation, opclass, direction và null placement.

### Bài 2. Mặc định

Nếu viết `CREATE INDEX ix ON t(title)` cho cột `text`, PostgreSQL thường chọn access method và opclass nào?

### Bài 3. Equality

Viết truy vấn tìm chính xác `sku = 'BK-001'` và một B-tree index phù hợp.

### Bài 4. Prefix search

Viết index và truy vấn tìm `title LIKE 'Ca%'` trong database có collation không phải C. Vì sao `text_pattern_ops` có thể hữu ích?

### Bài 5. Substring

`title ILIKE '%sql%'` có prefix cố định không? Có thể thử access method/opclass nào?

### Bài 6. Case-insensitive prefix

Viết expression index cho `lower(title) LIKE 'ca%'` và truy vấn tương ứng.

### Bài 7. Collation C

Viết `ORDER BY title COLLATE "C"`. Nó có bảo đảm thứ tự tiếng Việt tự nhiên không?

### Bài 8. Collation mismatch

Index trên `title` theo collation A có mặc nhiên đáp ứng `ORDER BY title COLLATE B` không?

### Bài 9. DESC đơn cột

Vì sao index `price ASC NULLS LAST` có thể dùng cho `ORDER BY price DESC` mặc định mà không tạo thêm index?

### Bài 10. DESC NULLS LAST

Vì sao `ORDER BY price DESC NULLS LAST` khác `ORDER BY price DESC` khi có null? Viết định nghĩa index trực tiếp phù hợp.

### Bài 11. Index ghép

Tạo index trên `category ASC, price DESC NULLS LAST, item_id ASC` và query lọc `category='book'` sắp theo giá giảm.

### Bài 12. Đảo chiều

Nếu quét ngược index ở bài 11, thứ tự tương ứng của ba khóa là gì?

### Bài 13. Sort toàn bảng

Tại sao index `(category, price)` không đảm bảo `ORDER BY price` toàn bảng?

### Bài 14. Tie-breaker

Vì sao một query phân trang theo `price DESC` có thể thiếu ổn định nếu không thêm `item_id`?

### Bài 15. Include

`INCLUDE (sku,title)` có giúp `ORDER BY title` đúng thứ tự index nếu title không là key không?

### Bài 16. JSON containment

Viết GIN index dùng `jsonb_path_ops` và query lọc `attrs @> '{"color":"brown"}'`.

### Bài 17. JSON key existence

Nếu ứng dụng chủ yếu dùng `attrs ? 'stock'`, nên cân nhắc `jsonb_ops` hay `jsonb_path_ops`?

### Bài 18. GIN + ORDER BY

GIN index trên attrs có tự trả kết quả theo `created_at DESC` không? Cần bước gì nữa?

### Bài 19. ICU nondeterministic

Nondeterministic collation có thể ảnh hưởng thế nào tới equality và UNIQUE? Vì sao phải xem phiên bản khi dùng LIKE?

### Bài 20. Collation version

Đổi phiên bản ICU/libc có thể gây rủi ro gì đối với B-tree? `ALTER COLLATION ... REFRESH VERSION` có tự REINDEX không?

### Bài 21. Catalog

Viết query xem `pg_indexes` và `pg_opclass` để xác định index đang dùng opclass gì.

### Bài 22. EXPLAIN

Nếu plan có `Bitmap Index Scan` và sau đó `Sort`, điều đó nói gì về khả năng filter/order của index được chọn?

### Bài 23. Prefix vs locale sorting

Một trang vừa tìm `title LIKE 'Ca%'` vừa `ORDER BY title` theo locale tiếng Việt. Có chắc một index pattern_ops duy nhất giải quyết tối ưu cả hai không?

### Bài 24. Chọn index theo workload

Cho ba nhóm query: (a) lọc category, top 20 price DESC NULLS LAST; (b) substring ILIKE trên title; (c) JSON key existence. Đề xuất các index có thể thử và cách xác minh.

## 31. Gợi ý đáp án

### Bài 1–2. Cấu trúc

Không có `USING` thì access method mặc định là B-tree. `COLLATE "C"` là collation; `text_pattern_ops` là opclass; `DESC` và `NULLS LAST` là direction/null placement. Chỉ mục B-tree text không nêu opclass thường dùng `text_ops`.

### Bài 3. Equality

~~~sql
CREATE INDEX idx_items_sku
ON idx_lab.items (sku);

SELECT item_id, sku, title
FROM idx_lab.items
WHERE sku = 'BK-001';
~~~

Với tìm chính xác bằng, B-tree mặc định là lựa chọn phổ biến. Nếu SKU bắt buộc duy nhất theo nghiệp vụ, nên cân nhắc `UNIQUE` constraint/index chứ không chỉ index thường.

### Bài 4. Prefix

~~~sql
CREATE INDEX idx_items_title_pattern
ON idx_lab.items (title text_pattern_ops);

SELECT sku, title
FROM idx_lab.items
WHERE title LIKE 'Ca%';
~~~

`text_pattern_ops` giúp B-tree hỗ trợ tiền tố theo ký tự ở nhiều locale không phải C.

### Bài 5. Substring

`'%sql%'` không có prefix cố định. Có thể thử `pg_trgm` và GIN `gin_trgm_ops`:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_items_title_search
ON idx_lab.items USING gin (title gin_trgm_ops);
~~~

Phải cân nhắc quyền cài extension và phân bố pattern/data.

### Bài 6. LOWER expression

~~~sql
CREATE INDEX idx_items_title_lower_pattern
ON idx_lab.items ((lower(title)) text_pattern_ops);

SELECT sku, title
FROM idx_lab.items
WHERE lower(title) LIKE 'ca%';
~~~

### Bài 7–8. Collation

~~~sql
SELECT sku, title
FROM idx_lab.items
ORDER BY title COLLATE "C", item_id;
~~~

`"C"` là thứ tự dạng C, không bảo đảm giống cách xếp từ điển tiếng Việt. Index theo collation A không tự cung cấp thứ tự collation B khi comparator khác.

### Bài 9–10. Hướng scan và null

B-tree có thể quét ngược `ASC NULLS LAST` để cho `DESC NULLS FIRST`, chính là default của `ORDER BY DESC`.

Nhưng `DESC NULLS LAST` yêu cầu null cuối:

~~~sql
CREATE INDEX idx_items_price_desc_last_answer
ON idx_lab.items (price DESC NULLS LAST);
~~~

### Bài 11. Index lọc và sắp

~~~sql
CREATE INDEX idx_items_cat_price_answer
ON idx_lab.items (
    category ASC,
    price DESC NULLS LAST,
    item_id ASC
);

SELECT sku, price
FROM idx_lab.items
WHERE category = 'book'
ORDER BY price DESC NULLS LAST, item_id ASC
LIMIT 20;
~~~

### Bài 12. Quét ngược

Thứ tự: `category DESC`, `price ASC NULLS FIRST`, `item_id DESC`.

### Bài 13–14. Thứ tự ghép và tie-breaker

Index `(category,price)` được nhóm trước theo category, nên không có thứ tự price toàn cục. Thêm `item_id` vào `ORDER BY` làm thứ tự xác định khi nhiều item cùng giá; không tự giải quyết toàn bộ vấn đề thay đổi dữ liệu giữa các trang.

### Bài 15. INCLUDE

Không. `INCLUDE` chứa dữ liệu payload cho một số covering scans, không quyết định thứ tự B-tree.

### Bài 16. JSON containment

~~~sql
CREATE INDEX idx_items_attrs_path_answer
ON idx_lab.items USING gin (attrs jsonb_path_ops);

SELECT sku
FROM idx_lab.items
WHERE attrs @> '{"color":"brown"}'::jsonb;
~~~

### Bài 17. JSON existence

Chọn hướng `jsonb_ops` vì nó hỗ trợ toán tử key existence `?`; `jsonb_path_ops` không cung cấp cùng tập toán tử này.

### Bài 18. GIN và sort

GIN hỗ trợ tìm hàng theo operator phù hợp, không trả dữ liệu theo `created_at DESC` như B-tree ordered scan. Planner có thể thêm `Sort` hoặc dùng một chiến lược truy cập khác.

### Bài 19–20. ICU

Nondeterministic collation có thể coi các chuỗi byte khác nhau tương đương theo chính sách được chọn, ảnh hưởng `=` và `UNIQUE`. Hỗ trợ pattern phụ thuộc phiên bản/cấu hình. Khi ICU/libc thay đổi quy tắc, index phụ thuộc collation có thể cần `REINDEX`; `REFRESH VERSION` chỉ cập nhật metadata, không xây lại index.

### Bài 21. Catalog

~~~sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'idx_lab'
ORDER BY indexname;

SELECT
    am.amname, opc.opcname, opc.opcdefault
FROM pg_opclass AS opc
JOIN pg_am AS am ON am.oid = opc.opcmethod
WHERE opc.opcname IN (
    'text_ops',
    'text_pattern_ops',
    'jsonb_ops',
    'jsonb_path_ops'
)
ORDER BY am.amname, opc.opcname;
~~~

Để biết opclass của từng key cụ thể, kết hợp `pg_index.indclass` và `pg_opclass` hoặc xem `pg_get_indexdef`.

### Bài 22. Bitmap và Sort

Bitmap scan dùng index để tìm tập row locations theo điều kiện, nhưng không duy trì thứ tự B-tree thành output sẵn sàng cho `ORDER BY`; `Sort` xử lý nhu cầu sắp xếp tiếp theo.

### Bài 23. Prefix và thứ tự ngôn ngữ

Không chắc. Pattern opclass ưu tiên tìm tiền tố theo ký tự, trong khi `ORDER BY title` theo locale cần thứ tự collation tương thích. Có thể cần index khác, sort hoặc thiết kế query điều chỉnh theo workload.

### Bài 24. Đề xuất index

~~~sql
-- (a) Equality filter + top-N price:
CREATE INDEX idx_items_cat_price_top
ON idx_lab.items (
    category,
    price DESC NULLS LAST,
    item_id
);

-- (b) Substring search, sau khi có pg_trgm:
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_items_title_substring
ON idx_lab.items USING gin (title gin_trgm_ops);

-- (c) JSON key existence:
CREATE INDEX idx_items_attrs_key
ON idx_lab.items USING gin (attrs jsonb_ops);
~~~

Sau đó xem `EXPLAIN (ANALYZE, BUFFERS)` trên truy vấn và dữ liệu đại diện; kiểm tra `Index Cond`, `Sort`, buffers, số hàng và chi phí ghi. Ba index có thể cần điều chỉnh hoặc bỏ bớt nếu workload không chứng minh lợi ích.

## 32. Bảng tra cứu nhanh

| Mục tiêu | Hướng thiết kế |
| --- | --- |
| Bằng và so sánh range numeric | B-tree mặc định |
| `ORDER BY text` theo locale | B-tree với collation đúng |
| Sort theo `"C"` | Index key `COLLATE "C"` khi cần |
| `LIKE 'prefix%'` ở locale không phải C | B-tree `text_pattern_ops`/biến thể kiểu |
| `lower(text) LIKE 'prefix%'` | Expression B-tree với pattern opclass |
| `ILIKE '%substring%'` | `pg_trgm` + GIN/GiST opclass khi phù hợp |
| JSONB containment `@>` | GIN `jsonb_ops` hoặc `jsonb_path_ops` |
| JSONB key existence `?` | GIN `jsonb_ops` |
| `ORDER BY price DESC` mặc định | Có thể backward scan B-tree ASC |
| `ORDER BY price DESC NULLS LAST` | Chú ý thứ tự null, cân nhắc B-tree tương ứng |
| Category filter và top-N price | Composite B-tree `(category,price DESC...,id)` |
| Sắp xếp nhiều khóa hỗn hợp | Định nghĩa hướng ASC/DESC trên từng key |
| Covering query | `INCLUDE` thích hợp, không dùng làm sort key |
| Xem index definitions | `pg_indexes` / `pg_get_indexdef` |
| Xem opclasses | `pg_opclass` + `pg_am` |
| Xem collation | `pg_collation` |
| Kiểm tra plan | `EXPLAIN (ANALYZE, BUFFERS)` |
| Đổi quy tắc collation do upgrade | Đánh giá/rebuild index phụ thuộc, rồi refresh version theo quy trình |

## 33. Checklist trước khi tạo chỉ mục

1. **Truy vấn thật dùng toán tử gì?** `=`, `LIKE 'a%'`, `ILIKE '%a%'`, `@>`, `?` hay `ORDER BY`?
2. **Access method nào có cấu trúc phù hợp?** B-tree, GIN, GiST, BRIN...?
3. **Operator class mặc định có hỗ trợ operator cần thiết?** Hay cần `text_pattern_ops`/`jsonb_path_ops`?
4. **Collation của cột và truy vấn là gì?** Có khác `"C"` hay khác nhau giữa môi trường?
5. **Có yêu cầu không phân biệt hoa/dấu?** Đã xác định ngữ nghĩa và phiên bản ICU chưa?
6. **ORDER BY dùng hướng nào và null đặt đâu?** `ASC`/`DESC`/`NULLS FIRST/LAST`?
7. **Các cột trong composite index đúng thứ tự không?** Cột lọc bằng và cột order có khớp?
8. **Có tie-breaker để phân trang ổn định không?** Ví dụ `item_id`.
9. **Biểu thức query có giống index key không?** `lower(title)` không đồng nhất với `title`.
10. **GIN index có bị kỳ vọng cung cấp thứ tự?** Nếu có, thiết kế đang nhầm mục đích.
11. **Có index trùng hoặc gần trùng không?** Mỗi index tăng storage và write amplification.
12. **Đã ANALYZE và EXPLAIN trên dữ liệu đại diện?** Không suy từ bảng 10 hàng.
13. **Có kiểm soát collation version khi nâng cấp?** Reindex các index phụ thuộc theo quy trình.
14. **Migration index có cần CONCURRENTLY không?** Hiểu giới hạn transaction và khóa trước khi chạy.

## 34. Tổng kết

Muốn hiểu một chỉ mục PostgreSQL, không chỉ nhìn **tên cột**. Cần xét đồng thời **access method, operator class, collation, thứ tự và cách biểu diễn khóa**.

**Operator class** quyết định PostgreSQL có thể dùng index cho **những toán tử nào**: B-tree text mặc định hữu ích cho so sánh thông dụng, `text_pattern_ops` cho prefix matching trong một số locale, GIN `jsonb_ops` có tập JSON operators rộng hơn `jsonb_path_ops`, còn trigram hỗ trợ một số kiểu tìm chuỗi con.

**Collation** quyết định quy tắc so sánh/sort văn bản. Một index trên `title COLLATE "C"` không mặc nhiên đáp ứng mọi `ORDER BY title` theo collation ngôn ngữ. Việc nâng cấp ICU/libc có thể làm quy tắc thay đổi, nên cần quản lý **collation version và REINDEX**, không chỉ refresh metadata.

**Thứ tự B-tree** cho phép forward/backward scans, nhưng `ASC`/`DESC` và `NULLS FIRST`/`NULLS LAST` phải phù hợp. Với index ghép, thứ tự hỗn hợp trên các cột là quyết định thiết kế quan trọng cho `WHERE ... ORDER BY ... LIMIT`.

Quy tắc thực hành: **bắt đầu từ những câu truy vấn có thật, xác định toán tử và collation, chọn opclass + cấu trúc order phù hợp, rồi kiểm chứng bằng EXPLAIN trên dữ liệu đại diện**. Đó là cách tạo ít index hơn nhưng đúng mục đích hơn, tránh tối ưu nhầm và giữ hệ thống PostgreSQL dễ vận hành.
