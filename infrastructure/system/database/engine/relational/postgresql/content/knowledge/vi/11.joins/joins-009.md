# UNION, UNION ALL, INTERSECT và EXCEPT trong PostgreSQL

## 1. Bốn phép toán để kết hợp kết quả truy vấn

Khi làm việc với nhiều nguồn dữ liệu, một hệ thống thường phải trả lời các câu hỏi khác nhau:

- Những mã sản phẩm **xuất hiện ở ít nhất một nguồn** là gì?
- Những mã nào **có ở cả hai nguồn**?
- Nguồn A có những mã nào **chưa tồn tại ở nguồn B**?
- Nếu một mã xuất hiện hai lần ở A và ba lần ở B, phần chung hay phần dư là bao nhiêu?
- Có thể gộp nhật ký sự kiện của hai hệ thống mà **không làm mất những sự kiện có nội dung giống nhau** không?

PostgreSQL hỗ trợ các phép toán tập hợp trên **kết quả của những truy vấn có cấu trúc tương thích**:

| Toán tử | Ý nghĩa | Xử lý dòng trùng |
|---|---|---|
| `UNION` | Các dòng xuất hiện ở một hoặc cả hai vế | Loại trùng |
| `UNION ALL` | Tất cả dòng từ hai vế | Giữ mọi lần xuất hiện |
| `INTERSECT` | Dòng chung giữa hai vế | Loại trùng |
| `INTERSECT ALL` | Dòng chung theo số lần xuất hiện | Giữ số lần tối thiểu |
| `EXCEPT` | Dòng có ở trái nhưng không có ở phải | Loại trùng |
| `EXCEPT ALL` | Dòng còn dư ở trái sau khi trừ số lần ở phải | Giữ số lần dư |

Điểm cốt lõi: các phép toán này so **toàn bộ các cột được chọn, theo vị trí**, không tự tìm ra khóa chính hay khóa nghiệp vụ. Nếu chỉ chọn `code`, ta đang so mã. Nếu chọn `code, category, qty`, ta đang so bộ ba.

Mục tiêu bài học:

1. Hiểu **tập hợp** và **đa tập** trong SQL.
2. Viết đúng `UNION`, `UNION ALL`, `INTERSECT`, `EXCEPT` và các biến thể `ALL`.
3. Giải thích cách xử lý `NULL`, dữ liệu trùng và kiểu dữ liệu.
4. Sử dụng dấu ngoặc, `ORDER BY` và `LIMIT` với đúng phạm vi.
5. Phân biệt phép toán tập hợp với `JOIN`, `NOT EXISTS`, `NOT IN`.
6. Ứng dụng tìm chênh lệch và đối soát dữ liệu hai chiều.
7. Đọc `EXPLAIN`, biết khi nào nên tối ưu hóa.

> Các lệnh tạo và nạp dữ liệu trong bài chỉ chạy ở database thực hành có quyền phù hợp, không thực hiện trên production khi chưa có quy trình.

---

## 2. Tập hợp so với đa tập

### 2.1. Tập hợp không chứa phần tử lặp

Trong lý thuyết tập hợp:

~~~text
A = {A, B, C}
B = {B, C, D}

A hợp B  = {A, B, C, D}
A giao B = {B, C}
A trừ B  = {A}
~~~

Với SQL, một phần tử là **một dòng kết quả** gồm các cột được SELECT. Hai dòng có cùng tất cả giá trị tương ứng mới là các dòng trùng cho mục đích khử trùng.

### 2.2. Đa tập giữ số lần xuất hiện

SQL thường trả nhiều dòng có nội dung giống hệt:

~~~text
Nguồn A: [A, B, B, C]
Nguồn B: [B, B, B, D]
~~~

Ở đây B xuất hiện hai lần ở A và ba lần ở B. `UNION ALL` giữ **năm** B; `UNION` chỉ giữ **một**; `INTERSECT ALL` giữ **hai** B; `INTERSECT` chỉ giữ **một**.

### 2.3. Công thức multiplicity

Gọi `a(x)` là số lần dòng x xuất hiện ở kết quả trái và `b(x)` là số lần ở kết quả phải.

| Phép toán | Số lần xuất hiện của x |
|---|---|
| `UNION ALL` | `a(x) + b(x)` |
| `UNION` | 1 nếu một trong hai bên có x, ngược lại 0 |
| `INTERSECT ALL` | `min(a(x), b(x))` |
| `INTERSECT` | 1 nếu cả hai bên có x, ngược lại 0 |
| `EXCEPT ALL` | `max(a(x) - b(x), 0)` |
| `EXCEPT` | 1 nếu trái có x và phải không có, ngược lại 0 |

Lưu ý: `EXCEPT` **có hướng**. Kết quả A trừ B có thể hoàn toàn khác B trừ A.

---

## 3. Chuẩn bị dữ liệu thực hành

Tạo schema riêng để không tác động bảng khác:

~~~sql
CREATE SCHEMA IF NOT EXISTS setops_lab;

CREATE TABLE setops_lab.source_a (
    seq INTEGER PRIMARY KEY,
    code TEXT,
    category TEXT,
    qty INTEGER
);

CREATE TABLE setops_lab.source_b (
    seq INTEGER PRIMARY KEY,
    code TEXT,
    category TEXT,
    qty INTEGER
);
~~~

`seq` là ID riêng trong mỗi nguồn. `code` là mã dùng để so sánh. Hai bảng cố ý không có `UNIQUE(code)` vì một mã có thể xuất hiện nhiều lần.

Nguồn A:

~~~sql
INSERT INTO setops_lab.source_a (seq, code, category, qty) VALUES
    (1, 'A', 'hardware', 10),
    (2, 'B', 'software', 20),
    (3, 'B', 'software', 20),
    (4, 'C', 'hardware', 30),
    (5, 'D', NULL, NULL),
    (6, NULL, 'unknown', NULL),
    (7, 'E', 'service', 0);
~~~

Nguồn B:

~~~sql
INSERT INTO setops_lab.source_b (seq, code, category, qty) VALUES
    (101, 'B', 'software', 20),
    (102, 'B', 'software', 20),
    (103, 'B', 'software', 20),
    (104, 'C', 'hardware', 30),
    (105, 'F', 'hardware', 40),
    (106, 'D', NULL, NULL),
    (107, NULL, 'unknown', NULL),
    (108, NULL, 'unknown', NULL),
    (109, 'G', 'service', 50);
~~~

Kiểm tra số dòng:

~~~sql
SELECT 'A'::text AS source_name, COUNT(*) AS row_count
FROM setops_lab.source_a
UNION ALL
SELECT 'B'::text AS source_name, COUNT(*) AS row_count
FROM setops_lab.source_b
ORDER BY source_name;
~~~

Kết quả là **7 dòng ở A**, **9 dòng ở B**. Nếu đã chạy INSERT một lần, không chạy lại trên cùng bảng vì sẽ vi phạm `seq PRIMARY KEY`.

### 3.1. Tần suất code ở hai nguồn

~~~sql
SELECT code, COUNT(*) AS frequency
FROM setops_lab.source_a
GROUP BY code
ORDER BY code NULLS LAST;
~~~

Nguồn A có A:1, B:2, C:1, D:1, E:1, NULL:1.

~~~sql
SELECT code, COUNT(*) AS frequency
FROM setops_lab.source_b
GROUP BY code
ORDER BY code NULLS LAST;
~~~

Nguồn B có B:3, C:1, D:1, F:1, G:1, NULL:2.

Tần suất này là cơ sở để kiểm chứng những phép toán có `ALL`.

---

## 4. UNION: hợp và loại trùng

~~~sql
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b
ORDER BY code ASC NULLS LAST;
~~~

Kết quả:

~~~text
A
B
C
D
E
F
G
NULL
~~~

Có **8 dòng phân biệt**. B xuất hiện ở cả hai nguồn và nhiều lần nhưng chỉ được giữ một B.

### 4.1. UNION mặc định là DISTINCT

`UNION` và `UNION DISTINCT` có semantics giống nhau: loại trùng. PostgreSQL không bảo đảm thứ tự nếu thiếu `ORDER BY` cuối; việc kết quả ngẫu nhiên theo chữ cái không phải cam kết SQL.

### 4.2. Loại trùng trên toàn dòng

Hai dòng `(B,software,20)` và `(B,software,25)` khác nhau nếu chọn ba cột; nhưng chúng là cùng mã nếu chỉ chọn `code`.

~~~sql
SELECT code, category, qty
FROM setops_lab.source_a
UNION
SELECT code, category, qty
FROM setops_lab.source_b
ORDER BY code NULLS LAST, category NULLS LAST, qty NULLS LAST;
~~~

Định nghĩa **dòng trùng** phụ thuộc tập cột được SELECT. Đừng chọn thêm `seq` hoặc `updated_at` một cách vô thức khi chỉ cần danh sách mã duy nhất.

### 4.3. Khác biệt giữa trùng nghiệp vụ và trùng kỹ thuật

Các chuỗi `'abc'`, `'ABC'`, `'abc '` có thể được xem là cùng mã trong một nghiệp vụ nhưng không tự động bị đồng nhất trong mọi môi trường PostgreSQL.

Nếu quy tắc mã không phân biệt hoa/thường và khoảng trắng:

~~~sql
SELECT upper(btrim(code)) AS normalized_code
FROM setops_lab.source_a
UNION
SELECT upper(btrim(code)) AS normalized_code
FROM setops_lab.source_b
ORDER BY normalized_code NULLS LAST;
~~~

Chỉ dùng phép chuẩn hóa khi đã xác nhận nghiệp vụ, collation và Unicode phù hợp.

---

## 5. UNION ALL: gộp nhưng giữ nguyên dòng

~~~sql
SELECT code FROM setops_lab.source_a
UNION ALL
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

Có **16 dòng**, bằng 7 + 9. Tần suất:

| code | Số lần trong UNION ALL |
|---|---:|
| A | 1 |
| B | 5 |
| C | 2 |
| D | 2 |
| E | 1 |
| F | 1 |
| G | 1 |
| NULL | 3 |

### 5.1. Trường hợp nên dùng

- Hợp nhất nhật ký sự kiện, giao dịch, bản ghi được xử lý độc lập.
- Kết hợp dữ liệu từ các phân đoạn hoặc nguồn đã có quy tắc ID riêng.
- Tạo tập trung gian để `GROUP BY` đếm tần suất.
- Giữ các bản ghi trùng có ý nghĩa, không làm mất một giao dịch hợp lệ.

Ví dụ khi tồn tại hai bảng đơn hàng thực tế:

~~~sql
SELECT 'web'::text AS channel, order_id, amount
FROM web_orders
UNION ALL
SELECT 'store'::text AS channel, order_id, amount
FROM store_orders;
~~~

Đây là SQL minh họa, không phải bảng đã tạo trong lab. Nhãn `channel` giúp biết đơn hàng xuất phát từ đâu.

### 5.2. Vì sao UNION ALL thường rẻ hơn?

`UNION ALL` không cần bước khử dòng trùng; PostgreSQL có thể nối đầu ra các nhánh qua `Append` hoặc một kế hoạch phù hợp. `UNION` có thể cần `HashAggregate` hay `Sort/Unique` để khử trùng.

Nhưng **chọn đúng semantics trước khi tối ưu**. Nếu API yêu cầu mã duy nhất, đổi sang UNION ALL chỉ để tăng tốc là thay đổi kết quả.

### 5.3. Giữ dấu vết nguồn

~~~sql
SELECT
    'A'::text AS source_name,
    seq AS source_seq,
    code, category, qty
FROM setops_lab.source_a
UNION ALL
SELECT
    'B'::text AS source_name,
    seq AS source_seq,
    code, category, qty
FROM setops_lab.source_b
ORDER BY source_name, source_seq;
~~~

Nếu seq chỉ unique trong từng nguồn thì cặp `(source_name,source_seq)` mới phân biệt đúng nguồn gốc dòng.

---

## 6. INTERSECT: phần giao

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

Kết quả có **4 giá trị phân biệt**:

~~~text
B
C
D
NULL
~~~

### 6.1. Tình huống áp dụng

- SKU có mặt ở **cả hai kho**.
- Khách hàng có trong **cả CRM và hệ thống billing**.
- Các quyền được cấp trong **hai tập phân quyền**.
- Các dòng giống nhau giữa hai bản dữ liệu theo cột được so.

`INTERSECT` mặc định loại trùng; số lần xuất hiện B ở mỗi nguồn không làm B lặp lại trong kết quả.

### 6.2. INTERSECT ALL: giao đa tập

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT ALL
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

Công thức số lần:

~~~text
min(count_A(x), count_B(x))
~~~

Kết quả:

~~~text
B
B
C
D
NULL
~~~

Tổng **5 dòng**, vì B có min(2,3)=2, C=1, D=1, NULL có min(1,2)=1.

### 6.3. Không nhầm INTERSECT với INNER JOIN

A có hai B, B có ba B:

- `INTERSECT` → **1 B**.
- `INTERSECT ALL` → **2 B**.
- `INNER JOIN` theo code → có thể tạo **6 cặp B**.

JOIN ghép mọi cặp phù hợp; INTERSECT ALL lấy số lần chung **nhỏ nhất**, không nhân số tổ hợp.

---

## 7. EXCEPT: phần chỉ có ở vế trái

### 7.1. A trừ B

~~~sql
SELECT code FROM setops_lab.source_a
EXCEPT
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

Kết quả: **A, E**.

### 7.2. B trừ A

~~~sql
SELECT code FROM setops_lab.source_b
EXCEPT
SELECT code FROM setops_lab.source_a
ORDER BY code NULLS LAST;
~~~

Kết quả: **F, G**.

Phép hiệu **không giao hoán**. `A EXCEPT B` là "A có, B không có"; `B EXCEPT A` là "B có, A không có".

### 7.3. EXCEPT ALL trừ số lần

~~~sql
SELECT code FROM setops_lab.source_b
EXCEPT ALL
SELECT code FROM setops_lab.source_a
ORDER BY code NULLS LAST;
~~~

Áp dụng `max(count_B(x)-count_A(x),0)`, kết quả:

~~~text
B
F
G
NULL
~~~

Có **4 dòng**: B dư một lần (3 so với 2), F/G mỗi mã dư một, NULL dư một lần (2 so với 1).

Chiều A trừ B:

~~~sql
SELECT code FROM setops_lab.source_a
EXCEPT ALL
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

chỉ còn **A và E**.

### 7.4. Khi nào cần EXCEPT ALL?

Trong đối soát, hai tệp có thể chứa **cùng tập giá trị** nhưng số lần lặp khác nhau. Ví dụ:

~~~text
File 1: [B, B, C]
File 2: [B, B, B, C]
~~~

`EXCEPT` hai chiều đều rỗng vì tập phân biệt giống nhau. Nhưng `File 2 EXCEPT ALL File 1` trả **một B** dư.

`EXCEPT ALL` hữu ích khi mỗi lần xuất hiện tương ứng một sự kiện có ý nghĩa, hoặc khi cần phát hiện dữ liệu bị nạp lặp.

### 7.5. EXCEPT không tự phát hiện UPDATE theo ID

Nếu cùng customer ID nhưng email thay đổi, phép EXCEPT trên cả ID và email có thể trả một dòng chỉ ở snapshot cũ và một dòng chỉ ở snapshot mới. Nó không tự kết luận hai dòng là **cùng khách được sửa**. Muốn phân loại INSERT/UPDATE/DELETE cần kết hợp khóa nghiệp vụ và so thuộc tính, thường bằng FULL JOIN.

---

## 8. NULL trong các phép toán tập hợp

### 8.1. NULL được xem là trùng khi khử trùng

~~~sql
SELECT NULL::integer AS value
UNION
SELECT NULL::integer AS value;
~~~

Kết quả: **1 dòng NULL**.

~~~sql
SELECT NULL::integer AS value
UNION ALL
SELECT NULL::integer AS value;
~~~

Kết quả: **2 dòng NULL**.

~~~sql
SELECT NULL::integer AS value
INTERSECT
SELECT NULL::integer AS value;
~~~

Kết quả: **1 dòng NULL**.

~~~sql
SELECT NULL::integer AS value
EXCEPT
SELECT NULL::integer AS value;
~~~

Kết quả: **0 dòng**.

Trong khử trùng/giao/hiệu tập hợp, hai giá trị NULL ở cùng vị trí được xem là **không phân biệt** cho mục đích so dòng.

### 8.2. Nhưng NULL = NULL không phải TRUE

~~~sql
SELECT NULL::integer = NULL::integer AS comparison_result;
~~~

Kết quả là NULL (UNKNOWN). Quy tắc của biểu thức `=` khác quy tắc so trùng trong set operations. Không được hiểu rằng PostgreSQL đã thay đổi logic ba giá trị.

### 8.3. NULL ở nhiều cột

~~~sql
SELECT 'D'::text AS code, NULL::integer AS qty
UNION
SELECT 'D'::text AS code, NULL::integer AS qty;
~~~

Chỉ có một bộ `('D',NULL)`.

~~~sql
SELECT 'D'::text AS code, NULL::integer AS qty
UNION
SELECT 'D'::text AS code, 0::integer AS qty;
~~~

Lại có **hai bộ**: `('D',NULL)` và `('D',0)`. NULL không phải 0.

### 8.4. IS NOT DISTINCT FROM ở điều kiện JOIN

Khi cần so NULL-safe trong điều kiện:

~~~sql
a.code IS NOT DISTINCT FROM b.code
~~~

cho TRUE khi cả hai cùng NULL hoặc có giá trị tương đương. Điều này hữu ích cho NOT EXISTS và JOIN, nhưng không biến phép JOIN thành INTERSECT ALL.

---

## 9. Quy tắc số cột, vị trí và kiểu dữ liệu

### 9.1. Hai nhánh phải có cùng số cột

Hợp lệ:

~~~sql
SELECT code, category FROM setops_lab.source_a
UNION ALL
SELECT code, category FROM setops_lab.source_b;
~~~

Sai:

~~~sql
SELECT code FROM setops_lab.source_a
UNION ALL
SELECT code, category FROM setops_lab.source_b;
~~~

PostgreSQL báo lỗi vì hai kết quả không có cùng số cột. Quy tắc này cũng áp dụng cho INTERSECT và EXCEPT.

### 9.2. Cột ghép theo vị trí, không theo tên

~~~sql
SELECT code, category FROM setops_lab.source_a
UNION ALL
SELECT category, code FROM setops_lab.source_b;
~~~

Vì hai cột đều TEXT, query có thể chạy, nhưng phần kết quả của B bị **đảo ngữ nghĩa**. PostgreSQL không tự căn theo tên cột; phải đặt cùng thứ tự biểu thức ở các nhánh.

### 9.3. Kiểu tương ứng phải có kiểu chung

~~~sql
SELECT 1::integer AS value
UNION ALL
SELECT 2.5::numeric AS value;
~~~

PostgreSQL có thể phân giải một kiểu số chung. Nhưng kiểu INTEGER và DATE không có kiểu chung hợp lý:

~~~sql
-- Ví dụ cố ý không hợp lệ:
SELECT 1::integer AS value
UNION
SELECT DATE '2026-01-01' AS value;
~~~

Không nên ép tất cả sang TEXT để "chạy qua", vì so ngày/số như chuỗi có thể làm kết quả sai. Hãy chốt kiểu dữ liệu theo ý nghĩa nghiệp vụ.

### 9.4. NULL literal nên có kiểu tường minh khi cần

~~~sql
SELECT code, NULL::integer AS qty
FROM setops_lab.source_a
UNION ALL
SELECT code, qty
FROM setops_lab.source_b;
~~~

`NULL::integer` giúp PostgreSQL suy ra kiểu cột placeholder rõ ràng, đặc biệt trong các phép toán lồng nhau.

### 9.5. Tên cột đầu ra lấy theo nhánh đầu

~~~sql
SELECT code AS product_code FROM setops_lab.source_a
UNION ALL
SELECT code AS sku FROM setops_lab.source_b
ORDER BY product_code;
~~~

Tên kết quả là `product_code`, không phải `sku` do nhánh hai khai báo.

---

## 10. Tránh SELECT * khi chỉ muốn so business key

~~~sql
SELECT * FROM setops_lab.source_a
UNION
SELECT * FROM setops_lab.source_b;
~~~

Hai bảng lab có cùng bốn cột nên truy vấn có thể chạy. Nhưng hai dòng:

~~~text
A: (seq=2, code=B, category=software, qty=20)
B: (seq=101, code=B, category=software, qty=20)
~~~

**không trùng nhau**, vì seq khác. Nếu chỉ cần mã sản phẩm chung/hợp, đừng đưa seq riêng nguồn vào phép so trùng.

`SELECT *` còn rủi ro nếu một bảng được thêm cột hoặc đổi thứ tự cột, khiến set operation lỗi hoặc ghép sai ý nghĩa. Nên liệt kê cột cụ thể và thống nhất projection giữa các nguồn.

---

## 11. Thứ tự ưu tiên: INTERSECT trước UNION/EXCEPT

Trong PostgreSQL:

1. `INTERSECT` có độ ưu tiên **cao hơn** `UNION` và `EXCEPT`.
2. `UNION` và `EXCEPT` có cùng mức ưu tiên, kết hợp **từ trái sang phải**.
3. Dùng **ngoặc** để biểu diễn rõ cách kết hợp khi có nhiều phép toán.

Ví dụ:

~~~sql
SELECT 1 AS n
UNION
SELECT 1 AS n
INTERSECT
SELECT 2 AS n;
~~~

Tương đương:

~~~text
{1} UNION ({1} INTERSECT {2})
= {1}
~~~

Kết quả **1 dòng n=1**.

Nhưng:

~~~sql
(
    SELECT 1 AS n
    UNION
    SELECT 1 AS n
)
INTERSECT
SELECT 2 AS n;
~~~

trả **0 dòng**.

Với UNION và EXCEPT:

~~~sql
SELECT 'x'::text AS item
UNION
SELECT 'y'::text AS item
EXCEPT
SELECT 'x'::text AS item;
~~~

được hiểu là `({x} UNION {y}) EXCEPT {x}`, trả **y**.

Nhưng:

~~~sql
SELECT 'x'::text AS item
UNION
(
    SELECT 'y'::text AS item
    EXCEPT
    SELECT 'x'::text AS item
);
~~~

trả **x và y**. Dấu ngoặc có thể thay đổi kết quả chứ không chỉ là trang trí.

Nếu trộn `UNION ALL` với `EXCEPT` mặc định, nhớ phép EXCEPT ở ngoài vẫn thực hiện semantics DISTINCT; nếu cần trừ **tần suất**, hãy dùng `EXCEPT ALL`.

---

## 12. ORDER BY và LIMIT với set operations

### 12.1. ORDER BY cuối sắp toàn kết quả

~~~sql
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b
ORDER BY code ASC NULLS LAST;
~~~

ORDER BY này sắp **kết quả cuối** sau phép hợp. Không có ORDER BY thì SQL không đảm bảo thứ tự.

### 12.2. ORDER BY trực tiếp sau set operation có giới hạn

PostgreSQL cho phép tham chiếu **tên cột đầu ra hoặc số thứ tự cột** ở ORDER BY của kết quả UNION/INTERSECT/EXCEPT:

~~~sql
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b
ORDER BY 1 DESC NULLS LAST;
~~~

Nếu cần biểu thức mới `lower(code)`, bọc trong subquery:

~~~sql
SELECT code
FROM (
    SELECT code FROM setops_lab.source_a
    UNION
    SELECT code FROM setops_lab.source_b
) AS merged
ORDER BY lower(code) ASC NULLS LAST, code ASC NULLS LAST;
~~~

### 12.3. LIMIT riêng từng nhánh cần ngoặc

Muốn lấy 3 dòng có seq lớn nhất từ mỗi nguồn:

~~~sql
(
    SELECT seq, code FROM setops_lab.source_a
    ORDER BY seq DESC
    LIMIT 3
)
UNION ALL
(
    SELECT seq, code FROM setops_lab.source_b
    ORDER BY seq DESC
    LIMIT 3
)
ORDER BY seq DESC;
~~~

Câu trên trả tối đa **6 dòng**.

Trong khi:

~~~sql
SELECT seq, code FROM setops_lab.source_a
UNION ALL
SELECT seq, code FROM setops_lab.source_b
ORDER BY seq DESC
LIMIT 3;
~~~

chỉ lấy **3 dòng có seq lớn nhất trên toàn hai nguồn**.

ORDER BY trong nhánh có LIMIT chọn subset; ORDER BY ngoài quyết định **thứ tự hiển thị cuối**. Không dùng LIMIT ngoài khi thiếu ORDER BY nếu cần phân trang ổn định.

---

## 13. Dùng CTE để đặt tên các tập dữ liệu

### 13.1. CTE giúp tách bước chuẩn bị và so sánh

~~~sql
WITH
a_codes AS (
    SELECT code
    FROM setops_lab.source_a
    WHERE code IS NOT NULL
),
b_codes AS (
    SELECT code
    FROM setops_lab.source_b
    WHERE code IS NOT NULL
)
SELECT code FROM a_codes
EXCEPT
SELECT code FROM b_codes
ORDER BY code;
~~~

Câu này tìm những **mã không NULL chỉ có ở A**, trả A và E.

Ưu điểm của CTE:

- Mỗi nguồn có một tên dễ hiểu.
- Có thể chuẩn hóa/lọc dữ liệu trước khi so sánh.
- Ít lặp các truy vấn con phức tạp.
- Dễ kiểm tra từng bước trong một pipeline dữ liệu.

CTE không có nghĩa PostgreSQL luôn materialize toàn bộ kết quả vào bộ nhớ/tệp riêng. Planner có thể tối ưu hóa/inlining CTE tùy phiên bản và điều kiện. Hãy dùng `EXPLAIN` thay vì giả định cách chạy.

### 13.2. Chuẩn hóa dữ liệu đồng nhất ở cả hai phía

~~~sql
WITH
a_codes AS (
    SELECT NULLIF(upper(btrim(code)), '') AS code
    FROM setops_lab.source_a
),
b_codes AS (
    SELECT NULLIF(upper(btrim(code)), '') AS code
    FROM setops_lab.source_b
)
SELECT code FROM a_codes
INTERSECT
SELECT code FROM b_codes
ORDER BY code NULLS LAST;
~~~

`btrim` xóa khoảng trắng hai đầu, `upper` đổi chữ hoa, `NULLIF(..., '')` biến chuỗi rỗng thành NULL. **Đây chỉ là một chính sách ví dụ**. Nếu chuỗi rỗng có nghĩa riêng, hoặc mã phân biệt hoa/thường, không được tùy ý thay đổi.

### 13.3. Sai khác đối xứng: dòng chỉ ở một phía

Sai khác đối xứng:

~~~text
(A EXCEPT B) UNION (B EXCEPT A)
~~~

Muốn có nhãn nguồn:

~~~sql
WITH
only_a AS (
    SELECT code FROM setops_lab.source_a
    EXCEPT
    SELECT code FROM setops_lab.source_b
),
only_b AS (
    SELECT code FROM setops_lab.source_b
    EXCEPT
    SELECT code FROM setops_lab.source_a
)
SELECT 'only_in_A'::text AS side, code FROM only_a
UNION ALL
SELECT 'only_in_B'::text AS side, code FROM only_b
ORDER BY side, code NULLS LAST;
~~~

Kết quả:

| side | code |
|---|---|
| only_in_A | A |
| only_in_A | E |
| only_in_B | F |
| only_in_B | G |

Nhãn được thêm **sau** phép EXCEPT. Nếu đưa nhãn khác nhau vào trước rồi mới so bằng UNION/INTERSECT, toàn bộ dòng khác nhau vì cột nhãn cũng tham gia so trùng.

---

## 14. Phân biệt set operations và JOIN

### 14.1. UNION là ghép dòng theo chiều dọc

~~~sql
SELECT code, category FROM setops_lab.source_a
UNION ALL
SELECT code, category FROM setops_lab.source_b;
~~~

Kết quả có hai cột như mỗi vế, các dòng từ hai nguồn cùng nằm trong một quan hệ kết quả.

### 14.2. JOIN ghép cột theo điều kiện

~~~sql
SELECT
    a.seq AS seq_a,
    b.seq AS seq_b,
    a.code,
    a.qty AS qty_a,
    b.qty AS qty_b
FROM setops_lab.source_a AS a
JOIN setops_lab.source_b AS b
  ON a.code = b.code
ORDER BY a.code, a.seq, b.seq;
~~~

JOIN trả cả cột từ A và B, tạo **mọi cặp dòng** thỏa điều kiện. Với code B xuất hiện 2 lần ở A và 3 lần ở B, INNER JOIN có thể tạo **6 cặp B**.

So với:

| Phép toán theo code | Số lần B |
|---|---:|
| `UNION ALL` | 5 |
| `UNION` | 1 |
| `INTERSECT ALL` | 2 |
| `INTERSECT` | 1 |
| `INNER JOIN` | 6 cặp |

Các số trên thuộc **những ngữ nghĩa khác nhau**, không nên thay toán tử chỉ vì một truy vấn trông ngắn hơn.

### 14.3. Khi nào JOIN phù hợp hơn?

- Lấy tên khách từ bảng khách hàng để bổ sung vào một giao dịch.
- Đặt `qty_a` và `qty_b` cạnh nhau cho cùng business key.
- So sánh thuộc tính của hai phiên bản một thực thể.
- Phân loại bản ghi mới, thay đổi, bị xóa.

Khi mục tiêu là **tập mã chung hoặc tập mã thiếu**, INTERSECT/EXCEPT thường diễn đạt trực tiếp hơn.

---

## 15. EXCEPT so với NOT EXISTS và NOT IN

### 15.1. EXCEPT chỉ trả những dòng phân biệt

~~~sql
SELECT code FROM setops_lab.source_a
EXCEPT
SELECT code FROM setops_lab.source_b;
~~~

Trả A và E, mỗi mã một lần.

### 15.2. NOT EXISTS giữ được thông tin từng dòng nguồn

Nếu muốn trả **mỗi dòng A** không có mã tương ứng ở B:

~~~sql
SELECT a.seq, a.code, a.category, a.qty
FROM setops_lab.source_a AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM setops_lab.source_b AS b
    WHERE b.code IS NOT DISTINCT FROM a.code
)
ORDER BY a.seq;
~~~

Câu này giữ seq và các cột của A. Nếu mã thiếu ở B xuất hiện ba lần ở A, kết quả có thể giữ cả ba dòng.

`IS NOT DISTINCT FROM` coi hai NULL là tương đương trong điều kiện so, gần với cách set operations xử lý trùng ở cột đó.

### 15.3. NOT IN và bẫy NULL

~~~sql
SELECT code
FROM setops_lab.source_a
WHERE code NOT IN (
    SELECT code FROM setops_lab.source_b
);
~~~

Vì B chứa một hoặc nhiều NULL, điều kiện `NOT IN` có thể trả **UNKNOWN** thay vì TRUE khi mã của A không khớp giá trị không NULL nào ở B.

Ví dụ:

~~~sql
SELECT 'A'::text NOT IN (
    SELECT code FROM setops_lab.source_b
) AS result_value;
~~~

Kết quả có thể là NULL (UNKNOWN), không phải TRUE. Nếu muốn tính hiệu của hai tập cột nullable, `EXCEPT` thường rõ và an toàn hơn.

### 15.4. LEFT JOIN anti-join cần marker chắc chắn không NULL

~~~sql
SELECT a.seq, a.code
FROM setops_lab.source_a AS a
LEFT JOIN setops_lab.source_b AS b
  ON b.code IS NOT DISTINCT FROM a.code
WHERE b.seq IS NULL
ORDER BY a.seq;
~~~

Ở đây `b.seq` là PK và không thể NULL của một dòng B có thật; `b.seq IS NULL` chứng minh không có dòng B nào match.

Đừng tự dùng `b.code IS NULL` làm marker khi code nullable và điều kiện ON có thể ghép hai NULL. Đó sẽ là cách dễ gắn nhầm một hàng đã match thành "không match".

---

## 16. So sánh một cột hoặc nhiều cột

Giao chỉ theo code:

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

Kết quả: B, C, D, NULL.

Giao theo ba cột:

~~~sql
SELECT code, category, qty
FROM setops_lab.source_a
INTERSECT
SELECT code, category, qty
FROM setops_lab.source_b
ORDER BY code NULLS LAST, category NULLS LAST, qty NULLS LAST;
~~~

Kết quả gồm bốn bộ:

~~~text
(B, software, 20)
(C, hardware, 30)
(D, NULL, NULL)
(NULL, unknown, NULL)
~~~

Nếu một phía đổi qty của B từ 20 thành 25, **giao theo code** vẫn có B nhưng **giao theo bộ ba** có thể không còn bộ B đó.

Trước khi viết truy vấn, hãy xác định:

- Đang so **sự tồn tại của mã** hay **nội dung chi tiết**?
- Có cần so timestamp, version, trạng thái không?
- Có nên bỏ các cột ID nội bộ khác nhau giữa nguồn?
- Các giá trị NULL có cùng ý nghĩa ở hai nơi không?
- Có phải giữ số lần xuất hiện trùng hay không?

---

## 17. Đối soát hai bản dữ liệu

Giả sử có hai bảng snapshot cùng cấu trúc:

~~~text
snapshot_old(customer_id, email, status)
snapshot_new(customer_id, email, status)
~~~

Đây là tên bảng **minh họa**, chưa tạo trong lab.

### 17.1. Kiểm tra tập các bộ có giống nhau không

~~~sql
(
    SELECT customer_id, email, status FROM snapshot_old
    EXCEPT
    SELECT customer_id, email, status FROM snapshot_new
)
UNION ALL
(
    SELECT customer_id, email, status FROM snapshot_new
    EXCEPT
    SELECT customer_id, email, status FROM snapshot_old
);
~~~

Nếu rỗng, hai phía có cùng **tập các bộ phân biệt** theo những cột được chọn trong snapshot đang so. Không kết luận số bản ghi lặp đã bằng nhau.

### 17.2. Kiểm tra đa tập gồm cả số lần lặp

~~~sql
(
    SELECT customer_id, email, status FROM snapshot_old
    EXCEPT ALL
    SELECT customer_id, email, status FROM snapshot_new
)
UNION ALL
(
    SELECT customer_id, email, status FROM snapshot_new
    EXCEPT ALL
    SELECT customer_id, email, status FROM snapshot_old
);
~~~

Nếu kết quả rỗng, hai phía có **cùng multiplicity của mỗi bộ** thuộc các cột đang so ở mốc dữ liệu đó.

### 17.3. Nếu muốn phân loại INSERT/UPDATE/DELETE

Chỉ dùng EXCEPT không phân biệt bản ghi được sửa với hai bộ khác nhau. Khi `customer_id` là khóa không NULL, duy nhất trong hai snapshot:

~~~sql
SELECT
    COALESCE(o.customer_id, n.customer_id) AS customer_id,
    CASE
        WHEN o.customer_id IS NULL THEN 'INSERT'
        WHEN n.customer_id IS NULL THEN 'DELETE'
        WHEN o.email IS DISTINCT FROM n.email
          OR o.status IS DISTINCT FROM n.status THEN 'UPDATE'
        ELSE 'UNCHANGED'
    END AS change_type
FROM snapshot_old AS o
FULL OUTER JOIN snapshot_new AS n
  ON o.customer_id = n.customer_id;
~~~

Đây là ví dụ khi cần **gán trạng thái thay đổi theo khóa**, thay vì chỉ lấy hai tập bộ khác biệt.

### 17.4. Hai nguồn phải ở cùng mốc dữ liệu

Trong hệ thống đang chạy, một bên có thể nhận thêm sự kiện trong khi bên kia chưa đồng bộ. Vì thế:

1. Thống nhất snapshot, watermark hoặc thời điểm chốt dữ liệu.
2. Thống nhất phạm vi bản ghi, điều kiện lọc và chính sách xóa mềm.
3. Xác định cột business key, cột nội dung và cột audit.
4. Kiểm tra chuẩn hóa ký tự, kiểu dữ liệu, timezone, collation.
5. Quyết định đối soát tập hay đa tập.
6. So số dòng, số mã phân biệt, kết quả EXCEPT hai chiều và các aggregate.
7. Lưu kết quả với quyền truy cập phù hợp; không lộ dữ liệu cá nhân khi xuất báo cáo.

Một lần đối soát rỗng chỉ mô tả trạng thái trong **phạm vi được so**, không chứng minh hai hệ thống mãi mãi đồng bộ.

---

## 18. Gộp trước, rồi GROUP BY để biết số lượng mỗi nguồn

`UNION ALL` kết hợp `GROUP BY` rất hữu ích khi cần đếm tần suất thay vì chỉ biết một mã có/không.

~~~sql
WITH combined AS (
    SELECT 'A'::text AS source_name, code
    FROM setops_lab.source_a
    UNION ALL
    SELECT 'B'::text AS source_name, code
    FROM setops_lab.source_b
)
SELECT
    code,
    COUNT(*) FILTER (WHERE source_name = 'A') AS count_a,
    COUNT(*) FILTER (WHERE source_name = 'B') AS count_b
FROM combined
GROUP BY code
ORDER BY code NULLS LAST;
~~~

Kết quả:

| code | count_a | count_b |
|---|---:|---:|
| A | 1 | 0 |
| B | 2 | 3 |
| C | 1 | 1 |
| D | 1 | 1 |
| E | 1 | 0 |
| F | 0 | 1 |
| G | 0 | 1 |
| NULL | 1 | 2 |

Muốn tính chênh lệch có dấu và phân loại:

~~~sql
WITH combined AS (
    SELECT 'A'::text AS source_name, code
    FROM setops_lab.source_a
    UNION ALL
    SELECT 'B'::text AS source_name, code
    FROM setops_lab.source_b
),
counts AS (
    SELECT
        code,
        COUNT(*) FILTER (WHERE source_name = 'A') AS count_a,
        COUNT(*) FILTER (WHERE source_name = 'B') AS count_b
    FROM combined
    GROUP BY code
)
SELECT
    code,
    count_a,
    count_b,
    count_a - count_b AS signed_difference,
    CASE
        WHEN count_a > 0 AND count_b = 0 THEN 'only_A'
        WHEN count_b > 0 AND count_a = 0 THEN 'only_B'
        WHEN count_a = count_b THEN 'same_count'
        ELSE 'different_count'
    END AS comparison_status
FROM counts
ORDER BY code NULLS LAST;
~~~

`signed_difference` có thể âm, bằng 0 hoặc dương. Ngược lại, `EXCEPT ALL` chỉ trả **số lần dư không âm** của một vế theo hướng trừ đang chọn.

---

## 19. Hiệu năng: EXPLAIN và chi phí loại trùng

### 19.1. UNION cần xử lý các dòng trùng

~~~sql
EXPLAIN
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b;
~~~

Tùy kế hoạch, PostgreSQL có thể sử dụng:

- `Append` để kết hợp input từ các nhánh.
- `HashAggregate` để lấy các bộ phân biệt.
- `Sort` và `Unique` để sắp rồi loại trùng.
- Những node/chiến lược khác theo phiên bản, thống kê và parallelism.

`UNION ALL` có thể tránh giai đoạn loại trùng nên thường nhẹ hơn trong bài toán **cần giữ mọi dòng**. Nhưng không thể đổi `UNION` sang `UNION ALL` nếu chức năng yêu cầu uniqueness.

### 19.2. INTERSECT/EXCEPT có các node chuyên biệt

~~~sql
EXPLAIN
SELECT code FROM setops_lab.source_a
EXCEPT ALL
SELECT code FROM setops_lab.source_b;
~~~

Có thể gặp `HashSetOp` hoặc `SetOp` kết hợp các bước đọc/sort, tùy kế hoạch. Hãy đọc:

- Số hàng từng nhánh.
- Row width: mỗi dòng rộng bao nhiêu.
- Có lọc theo WHERE trước khi xử lý tập không.
- Có dùng sort/hash, tệp tạm và I/O lớn không.
- Ước lượng rows so với actual rows.
- Có index/parallelism phù hợp không.

### 19.3. EXPLAIN ANALYZE thực thi truy vấn

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b;
~~~

`ANALYZE` khiến PostgreSQL **chạy thật** truy vấn để đo thời gian và đọc/ghi buffer. Trên bảng lab vài dòng thì thuận tiện. Với hàng triệu dòng production, cần đánh giá tải và quyền trước khi chạy.

### 19.4. Index hỗ trợ lọc, không bảo đảm khử trùng miễn phí

~~~sql
CREATE INDEX ix_source_a_code ON setops_lab.source_a (code);
CREATE INDEX ix_source_b_code ON setops_lab.source_b (code);
~~~

Hai index trên chỉ là **thí nghiệm lab**. Chúng có thể giúp filter:

~~~sql
SELECT code
FROM setops_lab.source_a
WHERE code = 'B';
~~~

Nhưng phép `UNION` trên **toàn bảng** có thể vẫn phải đọc nhiều dòng và hash/sort để khử trùng. Index cũng có chi phí ghi và lưu trữ, nên không tự thêm lên production khi thiếu số liệu workload.

### 19.5. Filter trước khi UNION

~~~sql
SELECT code
FROM setops_lab.source_a
WHERE category = 'hardware'
UNION
SELECT code
FROM setops_lab.source_b
WHERE category = 'hardware'
ORDER BY code;
~~~

Đẩy điều kiện lọc thích hợp vào từng nhánh có thể giảm dữ liệu phải kết hợp. Tuy nhiên không phải mọi phép di chuyển bộ lọc qua `EXCEPT`, `INTERSECT ALL` hay nhánh có LIMIT đều giữ nguyên ngữ nghĩa.

### 19.6. Memory và temp I/O

Sort/hash trên nhiều dòng rộng có thể tốn RAM hoặc spill xuống file tạm. Nên điều tra:

1. Có cần chọn nhiều cột đến vậy không?
2. Có đang khử trùng một tập sự kiện cần giữ nguyên không?
3. Điều kiện WHERE có thể giảm khối lượng không?
4. Có phải chuẩn hóa dữ liệu bằng biểu thức tốn CPU không?
5. Có index hoặc plan khác phù hợp không?
6. Có nhiều truy vấn tương tự chạy đồng thời không?

Không tự tăng `work_mem` toàn server ngay khi thấy sort chậm; tổng nhu cầu RAM của nhiều phép sort/hash trên các truy vấn đồng thời có thể rất lớn.

---

## 20. UNION và UNION ALL trong recursive CTE

PostgreSQL hỗ trợ `WITH RECURSIVE` kết hợp phần khởi đầu (anchor) và phần đệ quy:

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

Kết quả:

~~~text
1
2
3
4
5
~~~

### 20.1. UNION ALL và chu trình

Nếu dữ liệu là đồ thị:

~~~text
A → B
B → C
C → A
~~~

recursive term có thể tiếp tục quay lại A nếu không có cơ chế chặn chu trình. `UNION ALL` giữ mọi dòng sinh ra, nên những đường đi lặp có thể khiến truy vấn không dừng.

`UNION` loại **các dòng trùng toàn bộ**, đôi khi tránh việc thăm lại cùng node nếu kết quả chỉ gồm node ID. Nhưng nếu kết quả gồm `(node_id, depth)` thì:

~~~text
(A,0)
(A,3)
(A,6)
~~~

vẫn là ba dòng khác nhau, nên `UNION` **không tự bảo đảm dừng**.

Cần quy tắc kết thúc: giới hạn độ sâu, theo dõi visited nodes hoặc dùng cú pháp `CYCLE` khi phiên bản PostgreSQL hỗ trợ. Không coi `LIMIT` ngoài cùng là biện pháp an toàn duy nhất, nhất là khi truy vấn còn sort/aggregate toàn bộ dữ liệu đệ quy.

---

## 21. Kiểu dữ liệu và collation khi so trùng

### 21.1. Một số kiểu không có equality thích hợp

Phép `UNION`/`INTERSECT`/`EXCEPT` cần khả năng xác định khi nào dòng bằng nhau cho mục đích khử trùng. Kiểu `json` trong PostgreSQL không có toán tử equality tổng quát thường cần cho việc đó:

~~~sql
-- Ví dụ có thể lỗi do kiểu json không hỗ trợ equality thích hợp.
SELECT '{"a":1}'::json AS payload
UNION
SELECT '{"a":1}'::json AS payload;
~~~

Nếu muốn so giá trị JSON theo semantics của `jsonb` và nghiệp vụ cho phép:

~~~sql
SELECT '{"a":1}'::jsonb AS payload
UNION
SELECT '{"a":1}'::jsonb AS payload;
~~~

`UNION ALL` không cần bước khử trùng, nên có thể dùng với một số kiểu mà phép UNION DISTINCT không hỗ trợ, miễn hai vế giải quyết được kiểu dữ liệu chung hợp lệ.

### 21.2. Collation và Unicode

Các quy tắc so sánh `TEXT` có thể phụ thuộc collation, đặc biệt với ICU nondeterministic collations. Vì vậy không tự khẳng định mọi môi trường sẽ phân biệt cùng cách đối với:

~~~text
abc
ABC
á
a
abc với khoảng trắng cuối
~~~

Khi đối soát hai nguồn, phải chọn quy tắc chuẩn hóa/collation thống nhất và test dữ liệu có dấu, chữ hoa/thường, khoảng trắng.

### 21.3. Ngày giờ, số và biểu diễn TEXT

Hai chuỗi thời gian khác múi giờ có thể mô tả cùng một mốc nếu được chuyển đúng sang `TIMESTAMPTZ`. Tương tự, chuỗi `'1.0'` và `'1.00'` có thể là hai chuỗi khác nhau nhưng cùng giá trị `NUMERIC`.

Hãy quyết định cần so **giá trị thực** hay **biểu diễn gốc**. Không cast ngẫu nhiên chỉ để một phép UNION không báo lỗi.

---

## 22. Những lỗi và ngộ nhận thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Dùng UNION khi cần mọi giao dịch | Có thể mất giao dịch trùng nội dung | Dùng UNION ALL và giữ ID sự kiện |
| Dùng UNION ALL cho danh sách mã duy nhất | Trả mã trùng nhiều lần | Dùng UNION hoặc DISTINCT phù hợp |
| Chọn SELECT * để đối soát code | ID, timestamp thay đổi định nghĩa trùng | Chọn đúng cột so |
| Đảo thứ tự cột giữa hai nhánh | Có thể chạy nhưng ghép sai dữ liệu | Căn cột theo vị trí và ngữ nghĩa |
| Bỏ qua kiểu dữ liệu | Lỗi hoặc so sánh sai | Chọn common type đúng nghiệp vụ |
| Cho rằng NULL = NULL là TRUE | Sai logic ba giá trị | Phân biệt set operations và predicate |
| Coi INTERSECT là JOIN | Sai multiplicity, nhiều-nhiều | Chọn phép toán theo đầu ra mong muốn |
| Đảo nhầm hai vế EXCEPT | Kết quả thiếu khác hướng | Ghi rõ "only in A/B" |
| Dùng EXCEPT khi cần đếm trùng | Bỏ qua chênh số lần | Dùng EXCEPT ALL |
| Dùng NOT IN với bảng nullable | UNKNOWN làm bỏ các hàng cần tìm | Dùng EXCEPT hoặc NOT EXISTS |
| Không dùng ngoặc khi trộn toán tử | Sai thứ tự thực thi | Viết ngoặc/CTE |
| ORDER BY trong nhánh nhưng bỏ ORDER BY ngoài | Thứ tự cuối không có đảm bảo | Sắp ở tầng kết quả cuối |
| ORDER BY biểu thức trực tiếp sau UNION | Có thể không hợp lệ | Bọc trong subquery |
| Thêm nhãn nguồn trước UNION rồi mong code trùng | Nhãn khác khiến cả dòng khác | So code trước, gắn nhãn sau |
| Đối soát ở hai mốc thời gian | Báo chênh giả do lag/ghi mới | Dùng snapshot/watermark |
| Coi INDEX khử trùng miễn phí | Đánh giá sai chi phí | Đọc EXPLAIN và đo thực tế |
| Dùng UNION thay UNION ALL để chống vòng lặp đệ quy | Vẫn lặp nếu depth thay đổi | Có điều kiện dừng/cycle detection |
| Chỉ so COUNT(*) | Hai tập cùng số dòng vẫn khác | EXCEPT hai chiều, cần thì EXCEPT ALL |

---

## 23. Sơ đồ chọn toán tử

~~~mermaid
flowchart TD
    A["Cần kết hợp hai kết quả SQL"] --> B{"Muốn ghép cột theo một điều kiện?"}
    B -- "Có" --> C["JOIN hoặc so sánh theo khóa"]
    B -- "Không" --> D{"Muốn hợp, giao hay hiệu?"}
    D -- "Hợp" --> E{"Giữ mọi lần xuất hiện?"}
    E -- "Có" --> F["UNION ALL"]
    E -- "Không" --> G["UNION"]
    D -- "Giao" --> H{"Cần multiplicity?"}
    H -- "Có" --> I["INTERSECT ALL"]
    H -- "Không" --> J["INTERSECT"]
    D -- "Hiệu" --> K{"Cần multiplicity?"}
    K -- "Có" --> L["EXCEPT ALL đúng hướng"]
    K -- "Không" --> M["EXCEPT đúng hướng"]
~~~

Trước khi viết truy vấn, trả lời lần lượt:

1. Một dòng kết quả đại diện cho đối tượng/sự kiện nào?
2. Muốn so **cột nào** để xác định hai dòng trùng?
3. Có cần giữ số lần xuất hiện không?
4. Với phép hiệu, hướng nào là nguồn cần kiểm tra?
5. Hai vế có cùng số cột và kiểu dữ liệu tương thích không?
6. NULL, chuỗi rỗng, collation, timezone có ý nghĩa giống nhau không?
7. Có cần dấu ngoặc, LIMIT riêng nhánh và ORDER BY cuối không?
8. Truy vấn có đủ nhỏ/an toàn để đo trong môi trường hiện tại không?

---

## 24. Bài tập thực hành

Các bài dùng `setops_lab.source_a` và `setops_lab.source_b`, trừ khi đề bài nêu rõ dữ liệu giả định khác.

### Bài 1 — UNION

Viết truy vấn lấy các code phân biệt xuất hiện ở ít nhất một nguồn, sắp code tăng dần và NULL cuối. Có bao nhiêu dòng?

### Bài 2 — UNION ALL

Viết truy vấn gộp code nhưng giữ mọi lần xuất hiện. B xuất hiện mấy lần, NULL mấy lần, tổng cộng bao nhiêu dòng?

### Bài 3 — INTERSECT

Tìm những code xuất hiện ở cả A và B. Giải thích tại sao NULL nằm trong kết quả.

### Bài 4 — INTERSECT ALL

Viết truy vấn lấy giao đa tập. Có mấy B và tổng kết quả bao nhiêu dòng?

### Bài 5 — A trừ B

Tìm code chỉ có ở nguồn A.

### Bài 6 — B trừ A

So sánh `EXCEPT` và `EXCEPT ALL` khi lấy phần của B còn thiếu ở A. Vì sao B và NULL có trong ALL nhưng không có trong DISTINCT?

### Bài 7 — So một cột và ba cột

Viết `INTERSECT` trên `code`, rồi trên `code,category,qty`. Nêu tình huống hai cách cho kết quả khác.

### Bài 8 — Ghép cột theo vị trí

Nếu A chọn `(code,category)` còn B chọn `(category,code)`, query UNION ALL có thể chạy không? Vì sao có thể sai?

### Bài 9 — SELECT *

Tại sao hai dòng có cùng code B, category software, qty 20 nhưng khác seq không bị loại trùng khi chọn cả seq?

### Bài 10 — NULL

Dự đoán số dòng kết quả:

~~~sql
SELECT NULL::text UNION SELECT NULL::text;
SELECT NULL::text UNION ALL SELECT NULL::text;
SELECT NULL::text INTERSECT SELECT NULL::text;
SELECT NULL::text EXCEPT SELECT NULL::text;
~~~

### Bài 11 — Thứ tự ưu tiên

Giải thích kết quả của:

~~~sql
SELECT 1 AS n
UNION
SELECT 1 AS n
INTERSECT
SELECT 2 AS n;
~~~

So với:

~~~sql
(SELECT 1 AS n UNION SELECT 1 AS n)
INTERSECT
SELECT 2 AS n;
~~~

### Bài 12 — Sai khác đối xứng

Viết SQL trả `side,code` với `only_in_A`: A/E và `only_in_B`: F/G.

### Bài 13 — Đếm theo nguồn

Dùng `UNION ALL` và `GROUP BY` để trả code, `count_a`, `count_b` và chênh lệch có dấu.

### Bài 14 — Duplicate trong snapshot

Nguồn A có dòng X hai lần, B có X ba lần. Vì sao EXCEPT hai chiều có thể rỗng? EXCEPT ALL nào trả một X?

### Bài 15 — ORDER BY lower(code)

Viết truy vấn UNION hai nguồn, sắp `lower(code)` và để NULL cuối đúng cú pháp PostgreSQL.

### Bài 16 — LIMIT mỗi nhánh

Lấy ba dòng seq lớn nhất từ A và ba dòng seq lớn nhất từ B, sau đó UNION ALL và sắp seq giảm dần.

### Bài 17 — NOT IN và NULL

Vì sao `code NOT IN (SELECT code FROM B)` có thể không trả A/E? Viết một cách tìm tập thiếu đáng tin hơn.

### Bài 18 — INTERSECT so với JOIN

A có B hai lần, B có B ba lần. Dự đoán số lần B của UNION ALL, INTERSECT, INTERSECT ALL và số tổ hợp của INNER JOIN.

### Bài 19 — Gắn nguồn

Viết SQL gộp seq, code, qty với cột `source_name`, tránh nhầm seq của A và B là một ID toàn cục.

### Bài 20 — EXPLAIN

Một phép UNION lớn có node Sort/Unique. Nó đang làm gì? Nếu nghiệp vụ muốn giữ mọi sự kiện, nên cân nhắc toán tử nào?

### Bài 21 — Recursive CTE

Vì sao UNION không chắc chắn chặn vòng lặp khi mỗi lần thăm node có depth khác?

### Bài 22 — Đối soát production

Liệt kê ít nhất sáu yếu tố cần thống nhất trước khi chạy EXCEPT hai chiều để xác nhận hai nguồn đồng bộ.

---

## 25. Gợi ý lời giải

### Bài 1

~~~sql
SELECT code FROM setops_lab.source_a
UNION
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

**8 dòng:** A, B, C, D, E, F, G, NULL.

### Bài 2

~~~sql
SELECT code FROM setops_lab.source_a
UNION ALL
SELECT code FROM setops_lab.source_b;
~~~

Tổng **16 dòng**, B xuất hiện **5 lần**, NULL **3 lần**.

### Bài 3

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

**B, C, D, NULL**. NULL ở cùng vị trí được coi là trùng khi thực hiện set operation.

### Bài 4

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT ALL
SELECT code FROM setops_lab.source_b
ORDER BY code NULLS LAST;
~~~

B xuất hiện **2 lần**, tổng **5 dòng**: B, B, C, D, NULL.

### Bài 5

~~~sql
SELECT code FROM setops_lab.source_a
EXCEPT
SELECT code FROM setops_lab.source_b
ORDER BY code;
~~~

Kết quả **A, E**.

### Bài 6

~~~sql
SELECT code FROM setops_lab.source_b
EXCEPT
SELECT code FROM setops_lab.source_a;
~~~

Kết quả **F, G**.

~~~sql
SELECT code FROM setops_lab.source_b
EXCEPT ALL
SELECT code FROM setops_lab.source_a
ORDER BY code NULLS LAST;
~~~

Kết quả **B, F, G, NULL**. B và NULL có số lần ở B nhiều hơn A đúng một lần, nhưng đều xuất hiện ít nhất một lần ở cả hai nguồn nên bị loại khỏi `EXCEPT` DISTINCT.

### Bài 7

~~~sql
SELECT code FROM setops_lab.source_a
INTERSECT
SELECT code FROM setops_lab.source_b;
~~~

so mã. Còn:

~~~sql
SELECT code, category, qty FROM setops_lab.source_a
INTERSECT
SELECT code, category, qty FROM setops_lab.source_b;
~~~

so bộ ba. Nếu một bên có (B,software,20), bên kia chỉ có (B,software,25) thì B là mã chung nhưng hai bộ ba không trùng.

### Bài 8

Có thể chạy nếu kiểu các vị trí tương thích, nhưng PostgreSQL **không ghép theo tên**. Cần giữ cùng thứ tự code, category ở cả hai vế.

### Bài 9

`UNION` so toàn bộ cột được chọn. Hai seq khác nhau làm hai dòng khác nhau dù ba cột còn lại giống. Chỉ chọn code nếu muốn loại trùng theo mã.

### Bài 10

`UNION`: **1 NULL**. `UNION ALL`: **2 NULL**. `INTERSECT`: **1 NULL**. `EXCEPT`: **0 dòng**. Không suy ra `NULL = NULL` là TRUE trong predicate.

### Bài 11

`INTERSECT` có ưu tiên cao hơn, nên query đầu là `{1} UNION ({1} INTERSECT {2})`, trả **1**. Query có ngoặc là `({1} UNION {1}) INTERSECT {2}`, không trả dòng.

### Bài 12

~~~sql
WITH
only_a AS (
    SELECT code FROM setops_lab.source_a
    EXCEPT
    SELECT code FROM setops_lab.source_b
),
only_b AS (
    SELECT code FROM setops_lab.source_b
    EXCEPT
    SELECT code FROM setops_lab.source_a
)
SELECT 'only_in_A'::text AS side, code FROM only_a
UNION ALL
SELECT 'only_in_B'::text AS side, code FROM only_b
ORDER BY side, code NULLS LAST;
~~~

### Bài 13

~~~sql
WITH all_codes AS (
    SELECT 'A'::text AS src, code FROM setops_lab.source_a
    UNION ALL
    SELECT 'B'::text AS src, code FROM setops_lab.source_b
)
SELECT
    code,
    COUNT(*) FILTER (WHERE src = 'A') AS count_a,
    COUNT(*) FILTER (WHERE src = 'B') AS count_b,
    COUNT(*) FILTER (WHERE src = 'A')
        - COUNT(*) FILTER (WHERE src = 'B') AS difference
FROM all_codes
GROUP BY code
ORDER BY code NULLS LAST;
~~~

### Bài 14

`EXCEPT` mặc định khử trùng, nên hai bên có cùng tập {X} dù số lần khác. `B EXCEPT ALL A` trả **một X** thừa.

### Bài 15

~~~sql
SELECT code
FROM (
    SELECT code FROM setops_lab.source_a
    UNION
    SELECT code FROM setops_lab.source_b
) AS merged
ORDER BY lower(code) NULLS LAST, code NULLS LAST;
~~~

### Bài 16

~~~sql
(
    SELECT seq, code FROM setops_lab.source_a
    ORDER BY seq DESC LIMIT 3
)
UNION ALL
(
    SELECT seq, code FROM setops_lab.source_b
    ORDER BY seq DESC LIMIT 3
)
ORDER BY seq DESC;
~~~

Ngoặc xác định LIMIT riêng trong từng nguồn.

### Bài 17

B có NULL, khiến `NOT IN` có thể cho UNKNOWN ở những mã không match. Dùng:

~~~sql
SELECT code FROM setops_lab.source_a
EXCEPT
SELECT code FROM setops_lab.source_b;
~~~

Hoặc `NOT EXISTS` với `IS NOT DISTINCT FROM` nếu cần giữ từng dòng gốc.

### Bài 18

`UNION ALL` có **5 B**, `INTERSECT` có **1 B**, `INTERSECT ALL` có **2 B**, INNER JOIN theo B có thể tạo **6 cặp B**.

### Bài 19

~~~sql
SELECT 'A'::text AS source_name, seq AS source_seq, code, qty
FROM setops_lab.source_a
UNION ALL
SELECT 'B'::text AS source_name, seq AS source_seq, code, qty
FROM setops_lab.source_b
ORDER BY source_name, source_seq;
~~~

### Bài 20

Sort/Unique phục vụ **khử trùng** của UNION. Nếu nghiệp vụ cần mọi sự kiện, `UNION ALL` có thể đúng và tránh khử trùng. Cần đo số dòng, row width, memory/temp I/O và workload thực tế.

### Bài 21

Cùng node nhưng depth khác tạo dòng khác, không bị UNION loại. Cần giới hạn độ sâu, theo dõi visited nodes hoặc phát hiện cycle.

### Bài 22

Cần chốt: cùng **snapshot/watermark**, cùng phạm vi dữ liệu, cùng cách hiểu business key và cột cần so, kiểu dữ liệu/collation/timezone, cách xử lý NULL, chính sách dữ liệu trùng, quyền truy cập, phương pháp kiểm tra số dòng và chênh lệch hai chiều.

---

## 26. Kết luận

`UNION`, `UNION ALL`, `INTERSECT` và `EXCEPT` là các phép toán kết hợp **dòng của hai kết quả truy vấn** theo những cột tương ứng, không giống `JOIN` ghép cột theo điều kiện.

- **UNION:** hợp, loại trùng.
- **UNION ALL:** hợp, giữ số lần xuất hiện với công thức `a(x)+b(x)`.
- **INTERSECT:** giao, loại trùng.
- **INTERSECT ALL:** giao đa tập, lấy `min(a(x),b(x))` lần.
- **EXCEPT:** hiệu trái trừ phải, loại trùng.
- **EXCEPT ALL:** hiệu đa tập, lấy `max(a(x)-b(x),0)` lần.

Mỗi phép toán so **toàn bộ các cột được SELECT theo vị trí**. PostgreSQL xử lý hai NULL ở cùng vị trí như tương đương khi khử trùng tập hợp, dù biểu thức `NULL = NULL` không phải TRUE. Các cột phải có số lượng và kiểu dữ liệu tương thích; nên chọn chúng theo **ngữ nghĩa đối soát** thay vì dùng `SELECT *`.

Khi viết nhiều phép toán, nhớ `INTERSECT` có ưu tiên cao hơn `UNION`/`EXCEPT`; dấu ngoặc giúp thể hiện ý định chính xác. Muốn kết quả có thứ tự, thêm `ORDER BY` cuối; muốn `LIMIT` riêng nhánh, dùng ngoặc. Việc dùng `UNION ALL` có thể tiết kiệm chi phí loại trùng, nhưng chỉ khi **giữ mọi dòng là đúng yêu cầu nghiệp vụ**.

Cách tiếp cận bền vững: **xác định ý nghĩa một dòng → chọn cột so → chọn tập hay đa tập → chọn phép hợp/giao/hiệu và hướng trừ → kiểm tra NULL, kiểu và thứ tự → đối soát kết quả hai chiều → đo kế hoạch trên dữ liệu đại diện**.
