# Đối chiếu hai tập dữ liệu để tìm hàng thêm, thiếu hoặc thay đổi

Một công việc quen thuộc trong quản trị dữ liệu là **đối chiếu hai phiên bản**: danh sách sản phẩm hôm qua và hôm nay, dữ liệu nguồn và dữ liệu đã nhập vào kho, hoặc hai kết quả báo cáo trước và sau khi điều chỉnh. Câu hỏi không chỉ là “hai bảng có giống nhau không?”, mà thường gồm ba phần:

- **Hàng thêm:** có trong tập **sau**, không có trong tập **trước**.
- **Hàng thiếu (bị loại khỏi tập mới):** có trong tập **trước**, không còn trong tập **sau**.
- **Hàng thay đổi:** tồn tại trong **cả hai tập theo cùng một khóa**, nhưng một hoặc nhiều thuộc tính không còn giống nhau.

Trong SQL, các phép toán tập hợp như `EXCEPT`, `INTERSECT` và `UNION` là công cụ trực tiếp để tìm **chênh lệch giữa các tập hàng**. Tuy nhiên, khi mục tiêu là phân loại **bản ghi có cùng định danh nhưng dữ liệu đã đổi**, chúng ta còn cần so khớp theo khóa, thường bằng `JOIN` và một phép so sánh an toàn với `NULL`.

Bài học thuộc **Database SQL → Phép toán tập hợp**. Các ví dụ dùng **PostgreSQL** để có cú pháp và kết quả thống nhất; những điểm khác biệt ở MySQL, SQL Server, SQLite và Oracle được trình bày riêng.

## 1. Xác định đúng “tập trước”, “tập sau” và đối tượng cần so

Giả sử một ứng dụng lưu hai ảnh chụp (*snapshot*) của danh mục sản phẩm:

~~~text
                 THOI DIEM TRUOC                  THOI DIEM SAU

               snapshot_before                  snapshot_after
                /      |     \                   /      |     \
           P01, P02, P03, ...              P01, P02, P03, ...
                       |                              |
                       +-------- DOI CHIEU ----------+
                                    |
                         +----------+----------+
                         |          |          |
                      ADDED      REMOVED     CHANGED
                    (co moi)    (khong con) (cung khoa,
                                            khac thuoc tinh)
~~~

Trước khi viết SQL, cần trả lời ba câu hỏi nghiệp vụ:

1. **Chiều so sánh là gì?** Nếu lấy `after EXCEPT before` thì kết quả là hàng chỉ có ở **sau**, không phải hàng đã biến mất.
2. **Khóa nhận dạng bản ghi là gì?** Ví dụ `sku` là mã sản phẩm ổn định. Nếu cùng `sku` có giá khác nhau, đó là **một sản phẩm đã đổi giá**, không phải hai sản phẩm khác nhau.
3. **Thuộc tính nào cần so?** Có thể chỉ so giá và tồn kho; hoặc so cả tên, trạng thái, danh mục. Hai tập được gọi là “giống nhau” theo **các cột đã chọn**, không nhất thiết theo mọi cột vật lý.

Một công thức tổng quát:

| Phân loại | Điều kiện theo khóa `K` và các thuộc tính `A` |
| --- | --- |
| **ADDED** | `K` xuất hiện ở `after` nhưng không có ở `before` |
| **REMOVED** | `K` xuất hiện ở `before` nhưng không có ở `after` |
| **CHANGED** | `K` có ở cả hai; ít nhất một giá trị trong `A` khác nhau |
| **UNCHANGED** | `K` có ở cả hai; mọi giá trị được so trong `A` đều tương đương |

Định nghĩa **CHANGED** dựa trên **khóa** là khác biệt lớn nhất so với phép `EXCEPT` áp dụng lên **toàn bộ hàng**.

## 2. Chuẩn bị hai bảng mẫu có dữ liệu thêm, thiếu, thay đổi

Chạy phần khởi tạo sau **một lần** trên database PostgreSQL thực hành chưa có các bảng cùng tên. Không chạy trên bảng sản xuất. Dữ liệu được cố ý giữ đơn giản để các chênh lệch dễ nhận ra.

~~~sql
CREATE TABLE lab_set210_before (
    sku VARCHAR(12) PRIMARY KEY,
    product_name VARCHAR(80) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    stock_count INTEGER CHECK (stock_count >= 0),
    product_status VARCHAR(12) NOT NULL
        CHECK (product_status IN ('ACTIVE', 'INACTIVE'))
);

CREATE TABLE lab_set210_after (
    sku VARCHAR(12) PRIMARY KEY,
    product_name VARCHAR(80) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    stock_count INTEGER CHECK (stock_count >= 0),
    product_status VARCHAR(12) NOT NULL
        CHECK (product_status IN ('ACTIVE', 'INACTIVE'))
);

INSERT INTO lab_set210_before
    (sku, product_name, unit_price, stock_count, product_status)
VALUES
    ('P01', 'So tay',        120.00,  5,    'ACTIVE'),
    ('P02', 'But',            10.00, 10,    'ACTIVE'),
    ('P03', 'Ba lo',         350.00,  2,    'ACTIVE'),
    ('P04', 'Chuot',         200.00, NULL,  'ACTIVE'),
    ('P05', 'Giay note',      45.00,  3,    'ACTIVE'),
    ('P06', 'Ban phim',      280.00,  4,    'ACTIVE');

INSERT INTO lab_set210_after
    (sku, product_name, unit_price, stock_count, product_status)
VALUES
    ('P01', 'So tay',        120.00,  5,    'ACTIVE'),
    ('P02', 'But',            12.00, 10,    'ACTIVE'),
    ('P03', 'Ba lo',         350.00,  0,    'INACTIVE'),
    ('P04', 'Chuot',         200.00, NULL,  'ACTIVE'),
    ('P06', 'Ban phim',      280.00,  4,    'ACTIVE'),
    ('P07', 'Tai nghe',      400.00,  5,    'ACTIVE'),
    ('P08', 'Sac du phong',  250.00, NULL,  'ACTIVE');
~~~

`sku` được khai báo `PRIMARY KEY` ở **mỗi bảng**: trong một snapshot, mỗi mã sản phẩm xuất hiện tối đa một lần và không `NULL`. Quy tắc này giúp việc ghép hàng theo khóa không tạo nhiều cặp kết quả ngoài ý muốn.

Xem dữ liệu:

~~~sql
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_before
ORDER BY sku;

SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_after
ORDER BY sku;
~~~

| sku | Trước: giá | Trước: tồn | Trước: trạng thái | Sau: giá | Sau: tồn | Sau: trạng thái |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| P01 | 120.00 | 5 | ACTIVE | 120.00 | 5 | ACTIVE |
| P02 | 10.00 | 10 | ACTIVE | 12.00 | 10 | ACTIVE |
| P03 | 350.00 | 2 | ACTIVE | 350.00 | 0 | INACTIVE |
| P04 | 200.00 | `NULL` | ACTIVE | 200.00 | `NULL` | ACTIVE |
| P05 | 45.00 | 3 | ACTIVE | — | — | — |
| P06 | 280.00 | 4 | ACTIVE | 280.00 | 4 | ACTIVE |
| P07 | — | — | — | 400.00 | 5 | ACTIVE |
| P08 | — | — | — | 250.00 | `NULL` | ACTIVE |

Dấu **—** trong bảng mô tả nghĩa là **không có hàng** ở snapshot đó, không phải một hàng có toàn bộ cột bằng `NULL`.

Theo dữ liệu mẫu, phân loại mong muốn là:

| Trạng thái | Mã sản phẩm | Số mã |
| --- | --- | ---: |
| **ADDED** | P07, P08 | 2 |
| **REMOVED** | P05 | 1 |
| **CHANGED** | P02, P03 | 2 |
| **UNCHANGED** | P01, P04, P06 | 3 |

Những câu lệnh phía dưới sẽ tự tính các nhóm này từ dữ liệu, thay vì viết cứng danh sách mã.

## 3. EXCEPT: hiệu giữa hai tập hàng

Trong PostgreSQL, `EXCEPT` trả về những hàng của truy vấn **bên trái** mà không xuất hiện trong truy vấn **bên phải**:

~~~sql
SELECT cot_1, cot_2 FROM tap_A
EXCEPT
SELECT cot_1, cot_2 FROM tap_B;
~~~

Có thể đọc thành **A trừ B**. Thứ tự hai tập là một phần của ý nghĩa:

\[
A \setminus B \ne B \setminus A
\]

trong trường hợp tổng quát.

### 3.1. Tìm toàn bộ hàng chỉ xuất hiện ở snapshot sau

~~~sql
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_after
EXCEPT
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_before
ORDER BY sku;
~~~

Kết quả gồm **4 hàng**:

| sku | unit_price | stock_count | product_status | Giải thích |
| --- | ---: | ---: | --- | --- |
| P02 | 12.00 | 10 | ACTIVE | Khác hàng cũ vì giá đã đổi |
| P03 | 350.00 | 0 | INACTIVE | Khác hàng cũ vì tồn và trạng thái đã đổi |
| P07 | 400.00 | 5 | ACTIVE | Mã chỉ có trong snapshot sau |
| P08 | 250.00 | `NULL` | ACTIVE | Mã chỉ có trong snapshot sau |

**Chú ý:** kết quả `after EXCEPT before` theo **toàn bộ cột** không chỉ gồm **hàng mới theo khóa**. Nó còn chứa **phiên bản mới của những hàng đã thay đổi** như P02 và P03. `EXCEPT` chỉ biết hàng có giống hệt theo danh sách cột hay không, **không tự ghép hai phiên bản có cùng `sku`**.

### 3.2. Đảo chiều: những hàng chỉ có trong snapshot trước

~~~sql
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_before
EXCEPT
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_after
ORDER BY sku;
~~~

Kết quả là **3 hàng**: P02 với giá **10.00**, P03 với tồn **2** và trạng thái ACTIVE, cùng P05 (mã đã biến mất).

Do đó:

~~~text
AFTER EXCEPT BEFORE (so toan bo cot) = P02-moi, P03-moi, P07, P08
BEFORE EXCEPT AFTER (so toan bo cot) = P02-cu,  P03-cu,  P05
~~~

Hai chiều `EXCEPT` giúp nhận diện **những phiên bản hàng không có đối tác giống hệt**. Nhưng nếu yêu cầu là “thêm, thiếu, thay đổi theo sản phẩm”, ta cần xét **khóa trước** rồi mới so thuộc tính.

### 3.3. EXCEPT mặc định xử lý như tập hợp: loại hàng trùng

Trong PostgreSQL, `EXCEPT` không có `ALL` loại trùng các hàng kết quả. Nếu bảng nguồn có cùng hàng xuất hiện nhiều lần, kết quả `EXCEPT` thông thường không phản ánh chênh lệch **số lần xuất hiện** của từng hàng.

Ta sẽ thực hành trường hợp `EXCEPT ALL` ở mục 11.

## 4. EXCEPT theo khóa: tìm mã thực sự được thêm hoặc thiếu

Khi `sku` là khóa nhận dạng sản phẩm, chỉ chọn cột khóa trong phép hiệu để phân biệt **xuất hiện** và **biến mất**.

### 4.1. ADDED: mã có ở sau nhưng không có ở trước

~~~sql
SELECT sku
FROM lab_set210_after
EXCEPT
SELECT sku
FROM lab_set210_before
ORDER BY sku;
~~~

Kết quả:

| sku |
| --- |
| P07 |
| P08 |

Ở đây P02 và P03 **không xuất hiện**, vì các mã này đã có ở snapshot trước. Việc giá hoặc tồn kho thay đổi không ảnh hưởng câu hỏi **khóa có tồn tại hay không**.

### 4.2. REMOVED: mã có ở trước nhưng không còn ở sau

~~~sql
SELECT sku
FROM lab_set210_before
EXCEPT
SELECT sku
FROM lab_set210_after
ORDER BY sku;
~~~

Kết quả chỉ có:

| sku |
| --- |
| P05 |

Trong ngữ cảnh hai snapshot, “REMOVED” nghĩa là **không thấy mã này trong tập sau**. Không nhất thiết chứng minh sản phẩm đã bị xóa khỏi mọi bảng nguồn: nó có thể bị loại do bộ lọc, khác phạm vi ngày, thiếu dữ liệu đầu vào hoặc quy tắc trích xuất thay đổi. Cần xác định hai tập có cùng phạm vi trước khi diễn giải chênh lệch là biến động thật.

### 4.3. INTERSECT: những khóa tồn tại trong cả hai tập

`INTERSECT` lấy phần giao, tức các hàng xuất hiện ở cả hai phía:

~~~sql
SELECT sku
FROM lab_set210_before
INTERSECT
SELECT sku
FROM lab_set210_after
ORDER BY sku;
~~~

Kết quả gồm **P01, P02, P03, P04, P06**.

| Phép toán trên danh sách khóa | Kết quả mẫu | Ý nghĩa |
| --- | --- | --- |
| `after EXCEPT before` | P07, P08 | Mã được thêm |
| `before EXCEPT after` | P05 | Mã bị thiếu ở sau |
| `before INTERSECT after` | P01, P02, P03, P04, P06 | Mã có trong cả hai, **chưa biết có đổi thuộc tính không** |

**Giao của danh sách khóa không đồng nghĩa “hàng không đổi”.** P02 và P03 vẫn thuộc phần giao khóa dù dữ liệu của chúng đã đổi.

## 5. INTERSECT trên toàn bộ hàng: tìm hàng hoàn toàn giống nhau

Nếu mục tiêu là những hàng **giống hệt theo các cột được chọn**, có thể dùng `INTERSECT` trên toàn bộ bản ghi:

~~~sql
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_before
INTERSECT
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_after
ORDER BY sku;
~~~

Kết quả:

| sku | product_name | unit_price | stock_count | product_status |
| --- | --- | ---: | ---: | --- |
| P01 | So tay | 120.00 | 5 | ACTIVE |
| P04 | Chuot | 200.00 | `NULL` | ACTIVE |
| P06 | Ban phim | 280.00 | 4 | ACTIVE |

Đây chính là ba hàng **UNCHANGED** theo **toàn bộ năm cột** trong bài thực hành.

Điểm đáng chú ý: P04 có `stock_count = NULL` ở cả hai bảng, nhưng hàng đó vẫn xuất hiện trong `INTERSECT`. Trong các phép toán tập hợp của SQL, các hàng được so theo ngữ nghĩa trùng lặp của tập kết quả; hai giá trị `NULL` ở vị trí tương ứng được xử lý như **không tạo khác biệt** cho mục đích nhận diện hàng trùng. Điều này **khác** biểu thức so sánh thông thường `NULL = NULL`, vốn cho kết quả `UNKNOWN`.

Ví dụ độc lập:

~~~sql
-- PostgreSQL: khong co hang nao, vi hai hang NULL duoc xem la trung
-- trong ngu nghia EXCEPT.
SELECT NULL::integer
EXCEPT
SELECT NULL::integer;
~~~

Không nên dựa vào `a = b` để kiểm tra hai giá trị nullable có giống nhau không. Phần tiếp theo dùng cách so sánh tường minh an toàn với `NULL`.

## 6. Ghép theo khóa để tìm CHANGED: cùng mã nhưng khác thuộc tính

Để tìm các hàng **CHANGED**, ta cần có cả bản ghi trước và sau trên **cùng một dòng so sánh**. Sử dụng `INNER JOIN` theo khóa:

~~~sql
SELECT
    b.sku,
    b.product_name AS old_name,
    a.product_name AS new_name,
    b.unit_price AS old_price,
    a.unit_price AS new_price,
    b.stock_count AS old_stock,
    a.stock_count AS new_stock,
    b.product_status AS old_status,
    a.product_status AS new_status
FROM lab_set210_before AS b
JOIN lab_set210_after AS a
    ON a.sku = b.sku
WHERE b.product_name IS DISTINCT FROM a.product_name
   OR b.unit_price IS DISTINCT FROM a.unit_price
   OR b.stock_count IS DISTINCT FROM a.stock_count
   OR b.product_status IS DISTINCT FROM a.product_status
ORDER BY b.sku;
~~~

Kết quả chỉ có **P02 và P03**:

| sku | old_price | new_price | old_stock | new_stock | old_status | new_status |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| P02 | 10.00 | 12.00 | 10 | 10 | ACTIVE | ACTIVE |
| P03 | 350.00 | 350.00 | 2 | 0 | ACTIVE | INACTIVE |

Hai mã này xuất hiện ở **cả hai bảng**, nhưng có ít nhất một thuộc tính khác nhau. P04 không lọt vào kết quả vì cùng có giá 200, tồn `NULL` và trạng thái ACTIVE ở hai thời điểm.

### 6.1. Vì sao dùng IS DISTINCT FROM thay cho <>?

Với hai giá trị **khác `NULL`**, biểu thức `x IS DISTINCT FROM y` có ý nghĩa gần với `x <> y`. Nhưng với `NULL`, hai cách so sánh khác nhau:

| `x` | `y` | `x <> y` | `x IS DISTINCT FROM y` |
| --- | --- | --- | --- |
| 10 | 12 | TRUE | TRUE |
| 10 | 10 | FALSE | FALSE |
| `NULL` | `NULL` | UNKNOWN | FALSE |
| `NULL` | 0 | UNKNOWN | TRUE |
| 0 | `NULL` | UNKNOWN | TRUE |

Trong PostgreSQL, `IS DISTINCT FROM` trả **TRUE/FALSE**, kể cả khi có `NULL`:

- Cả hai cùng `NULL` → **không khác**.
- Một bên `NULL`, bên kia có giá trị → **khác**.
- Hai giá trị không `NULL` và bằng nhau → **không khác**.
- Hai giá trị không `NULL` và không bằng nhau → **khác**.

Nếu chỉ viết:

~~~sql
-- De bo sot truong hop mot ben NULL, mot ben co gia tri.
WHERE b.stock_count <> a.stock_count
~~~

thì một thay đổi như “`NULL` → 0” hoặc “5 → `NULL`” sẽ không được nhận diện bằng điều kiện đó, vì kết quả phép so sánh là UNKNOWN. `IS DISTINCT FROM` giải quyết trực tiếp bài toán đối chiếu cột có thể thiếu dữ liệu.

### 6.2. Rút gọn bằng so sánh hàng trong PostgreSQL

PostgreSQL cho phép dùng biểu thức `ROW(...)` với `IS DISTINCT FROM`:

~~~sql
SELECT b.sku
FROM lab_set210_before AS b
JOIN lab_set210_after AS a
    ON a.sku = b.sku
WHERE ROW(
        b.product_name,
        b.unit_price,
        b.stock_count,
        b.product_status
    ) IS DISTINCT FROM ROW(
        a.product_name,
        a.unit_price,
        a.stock_count,
        a.product_status
    )
ORDER BY b.sku;
~~~

Kết quả vẫn là **P02, P03**. Cách này phù hợp khi muốn so **cùng một bộ thuộc tính** theo đúng thứ tự ở hai phía, nhưng câu SQL liệt kê từng `IS DISTINCT FROM` có thể dễ kiểm tra và dễ điều chỉnh khi cần thêm/bớt cột.

Không thay một phép so giá trị có cấu trúc rõ bằng cách tùy tiện chuyển toàn bộ hàng thành chuỗi, ghép dấu phân cách hoặc băm dữ liệu mà chưa định nghĩa cách chuẩn hóa `NULL`, kiểu dữ liệu, định dạng thời gian và xung đột dấu phân cách.

## 7. FULL OUTER JOIN: phân loại cả bốn trạng thái trong một truy vấn

`FULL OUTER JOIN` giữ:

- Những hàng có **khóa khớp** ở cả hai phía.
- Những hàng chỉ có ở bảng **trước**, với các cột phía sau là `NULL`.
- Những hàng chỉ có ở bảng **sau**, với các cột phía trước là `NULL`.

Nhờ đó, ta có thể đặt nhãn **ADDED**, **REMOVED**, **CHANGED** hoặc **UNCHANGED** trong cùng một `CASE`.

~~~sql
SELECT
    COALESCE(b.sku, a.sku) AS sku,
    CASE
        WHEN b.sku IS NULL THEN 'ADDED'
        WHEN a.sku IS NULL THEN 'REMOVED'
        WHEN b.product_name IS DISTINCT FROM a.product_name
          OR b.unit_price IS DISTINCT FROM a.unit_price
          OR b.stock_count IS DISTINCT FROM a.stock_count
          OR b.product_status IS DISTINCT FROM a.product_status
            THEN 'CHANGED'
        ELSE 'UNCHANGED'
    END AS change_type,
    b.unit_price AS old_price,
    a.unit_price AS new_price,
    b.stock_count AS old_stock,
    a.stock_count AS new_stock
FROM lab_set210_before AS b
FULL OUTER JOIN lab_set210_after AS a
    ON a.sku = b.sku
ORDER BY sku;
~~~

Kết quả phân loại:

| sku | change_type | old_price | new_price | old_stock | new_stock |
| --- | --- | ---: | ---: | ---: | ---: |
| P01 | UNCHANGED | 120.00 | 120.00 | 5 | 5 |
| P02 | CHANGED | 10.00 | 12.00 | 10 | 10 |
| P03 | CHANGED | 350.00 | 350.00 | 2 | 0 |
| P04 | UNCHANGED | 200.00 | 200.00 | `NULL` | `NULL` |
| P05 | REMOVED | 45.00 | `NULL` | 3 | `NULL` |
| P06 | UNCHANGED | 280.00 | 280.00 | 4 | 4 |
| P07 | ADDED | `NULL` | 400.00 | `NULL` | 5 |
| P08 | ADDED | `NULL` | 250.00 | `NULL` | `NULL` |

Để đọc đúng `CASE`:

1. `b.sku IS NULL` nghĩa là **không có hàng trước** cho mã ở phía sau → ADDED.
2. `a.sku IS NULL` nghĩa là **không có hàng sau** cho mã ở phía trước → REMOVED.
3. Nếu cả hai khóa đều có mặt, so bốn thuộc tính để quyết định CHANGED.
4. Nếu không có thuộc tính khác biệt, kết luận UNCHANGED.

`sku` ở cả hai bảng được khai báo **`PRIMARY KEY NOT NULL`** (khóa chính không nhận `NULL`). Vì vậy, dùng `b.sku IS NULL` hoặc `a.sku IS NULL` sau `FULL JOIN` là một dấu hiệu đáng tin cậy rằng **hàng bên tương ứng không khớp**. Với cột dùng làm dấu hiệu mà bản thân nó được phép `NULL`, không thể suy luận như vậy một cách máy móc.

`COALESCE(b.sku, a.sku)` lấy khóa từ phía có hàng, do đó có thể hiển thị mã P05, P07 hoặc P08 ngay cả khi phía còn lại không tồn tại.

### 7.1. Chỉ lấy ba loại biến động, không lấy UNCHANGED

Muốn tạo một bản danh sách thay đổi, có thể đặt truy vấn phân loại thành CTE:

~~~sql
WITH comparison AS (
    SELECT
        COALESCE(b.sku, a.sku) AS sku,
        CASE
            WHEN b.sku IS NULL THEN 'ADDED'
            WHEN a.sku IS NULL THEN 'REMOVED'
            WHEN ROW(
                b.product_name, b.unit_price, b.stock_count, b.product_status
            ) IS DISTINCT FROM ROW(
                a.product_name, a.unit_price, a.stock_count, a.product_status
            ) THEN 'CHANGED'
            ELSE 'UNCHANGED'
        END AS change_type,
        b.unit_price AS old_price,
        a.unit_price AS new_price
    FROM lab_set210_before AS b
    FULL OUTER JOIN lab_set210_after AS a
        ON a.sku = b.sku
)
SELECT sku, change_type, old_price, new_price
FROM comparison
WHERE change_type <> 'UNCHANGED'
ORDER BY sku;
~~~

Kết quả có **P02, P03, P05, P07, P08**, gồm 2 CHANGED, 1 REMOVED và 2 ADDED. Ở cấp truy vấn ngoài, `change_type` là **cột đã được tính trong CTE**, nên có thể lọc bằng `WHERE` mà không cần lặp biểu thức `CASE`.

### 7.2. Đếm nhanh số hàng thuộc mỗi trạng thái

~~~sql
WITH comparison AS (
    SELECT
        CASE
            WHEN b.sku IS NULL THEN 'ADDED'
            WHEN a.sku IS NULL THEN 'REMOVED'
            WHEN b.product_name IS DISTINCT FROM a.product_name
              OR b.unit_price IS DISTINCT FROM a.unit_price
              OR b.stock_count IS DISTINCT FROM a.stock_count
              OR b.product_status IS DISTINCT FROM a.product_status
                THEN 'CHANGED'
            ELSE 'UNCHANGED'
        END AS change_type
    FROM lab_set210_before AS b
    FULL OUTER JOIN lab_set210_after AS a
        ON a.sku = b.sku
)
SELECT change_type, COUNT(*) AS product_count
FROM comparison
GROUP BY change_type
ORDER BY change_type;
~~~

| change_type | product_count |
| --- | ---: |
| ADDED | 2 |
| CHANGED | 2 |
| REMOVED | 1 |
| UNCHANGED | 3 |

Với mỗi snapshot có khóa duy nhất và không `NULL`, tổng số mã trong **hợp của hai tập khóa** là **8**. Bốn nhóm phân loại cũng phải bao phủ đúng **8 mã**. Bảng trước có **6 mã** (= 1 REMOVED + 2 CHANGED + 3 UNCHANGED), bảng sau có **7 mã** (= 2 ADDED + 2 CHANGED + 3 UNCHANGED).

## 8. Muốn biết cụ thể cột nào đã thay đổi

Một nhãn CHANGED có thể chưa đủ để người vận hành hiểu điều gì xảy ra. Khi đối chiếu dữ liệu phục vụ kiểm kê hoặc nhập liệu, thường cần kèm cả **giá trị cũ, giá trị mới và tên những cột khác biệt**.

~~~sql
SELECT
    b.sku,
    CONCAT_WS(', ',
        CASE WHEN b.product_name IS DISTINCT FROM a.product_name
            THEN 'product_name' END,
        CASE WHEN b.unit_price IS DISTINCT FROM a.unit_price
            THEN 'unit_price' END,
        CASE WHEN b.stock_count IS DISTINCT FROM a.stock_count
            THEN 'stock_count' END,
        CASE WHEN b.product_status IS DISTINCT FROM a.product_status
            THEN 'product_status' END
    ) AS changed_columns,
    b.unit_price AS old_price,
    a.unit_price AS new_price,
    b.stock_count AS old_stock,
    a.stock_count AS new_stock,
    b.product_status AS old_status,
    a.product_status AS new_status
FROM lab_set210_before AS b
JOIN lab_set210_after AS a
    ON a.sku = b.sku
WHERE b.product_name IS DISTINCT FROM a.product_name
   OR b.unit_price IS DISTINCT FROM a.unit_price
   OR b.stock_count IS DISTINCT FROM a.stock_count
   OR b.product_status IS DISTINCT FROM a.product_status
ORDER BY b.sku;
~~~

Kết quả:

| sku | changed_columns | Diễn giải |
| --- | --- | --- |
| P02 | unit_price | Giá từ 10.00 thành 12.00 |
| P03 | stock_count, product_status | Tồn kho từ 2 thành 0; ACTIVE thành INACTIVE |

Hàm `CONCAT_WS` của PostgreSQL ghép những phần khác `NULL`, thêm dấu phân cách `', '` giữa chúng. Các nhánh `CASE WHEN ... THEN ... END` không khớp trả `NULL`, nên không đưa tên cột không đổi vào chuỗi.

Đây là một **cách trình bày báo cáo**, không nhất thiết là cấu trúc tối ưu để đưa vào hệ thống kiểm toán dài hạn. Khi cần lưu vết chính xác, có thể tạo **một dòng cho mỗi cột đổi** hoặc lưu cặp giá trị trước/sau trong cấu trúc được thiết kế rõ ràng.

## 9. Dùng NOT EXISTS và LEFT JOIN để tìm hàng thêm, thiếu

Phép `EXCEPT` trên khóa ngắn gọn, nhưng không phải cách duy nhất để kiểm tra **mã không tồn tại ở tập còn lại**. Hai lựa chọn thường thấy là `NOT EXISTS` và phép nối ngoài.

### 9.1. ADDED bằng NOT EXISTS

~~~sql
SELECT a.sku, a.product_name
FROM lab_set210_after AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_set210_before AS b
    WHERE b.sku = a.sku
)
ORDER BY a.sku;
~~~

Kết quả: **P07, P08**.

Về mặt ý nghĩa, `NOT EXISTS` hỏi: “Có phải **không có hàng** nào bên trước mang cùng `sku` này?”. Nó đặc biệt hữu ích khi điều kiện khớp gồm **nhiều cột** hoặc cần thêm điều kiện nghiệp vụ.

### 9.2. REMOVED bằng LEFT JOIN

~~~sql
SELECT b.sku, b.product_name
FROM lab_set210_before AS b
LEFT JOIN lab_set210_after AS a
    ON a.sku = b.sku
WHERE a.sku IS NULL
ORDER BY b.sku;
~~~

Kết quả: **P05**.

Vì `a.sku` là khóa không `NULL` khi tồn tại hàng thật, `a.sku IS NULL` sau `LEFT JOIN` chứng minh không tìm thấy hàng tương ứng ở snapshot sau.

### 9.3. Vì sao NOT IN có thể gây nhầm với NULL?

Trên hai bảng mẫu, `sku` là khóa chính không `NULL`, nên biểu thức `NOT IN (SELECT sku ...)` có thể cho kết quả tương đương trong điều kiện này. Nhưng nếu phía danh sách chứa `NULL`, `NOT IN` có thể tạo kết quả **UNKNOWN** và loại những hàng tưởng như “không thuộc danh sách”.

Ví dụ độc lập:

~~~sql
SELECT
    'P99'::text NOT IN (
        SELECT 'P01'::text
        UNION ALL
        SELECT NULL::text
    ) AS not_in_result;
~~~

Kết quả `not_in_result` là **`NULL`** (UNKNOWN), không phải TRUE. Vì vậy đối với bài toán “không có hàng liên quan”, `NOT EXISTS` thường diễn đạt rõ hơn và ít rủi ro hơn với danh sách có giá trị thiếu.

## 10. Kết hợp UNION ALL để tạo danh sách chênh lệch có nhãn

`UNION ALL` ghép các kết quả **theo chiều dọc** và **giữ nguyên số lần xuất hiện** của hàng. Ta có thể dùng nó để gộp các tập ADDED, REMOVED và CHANGED thành một danh sách báo cáo.

~~~sql
WITH added AS (
    SELECT a.sku, 'ADDED'::text AS change_type
    FROM lab_set210_after AS a
    WHERE NOT EXISTS (
        SELECT 1
        FROM lab_set210_before AS b
        WHERE b.sku = a.sku
    )
),
removed AS (
    SELECT b.sku, 'REMOVED'::text AS change_type
    FROM lab_set210_before AS b
    WHERE NOT EXISTS (
        SELECT 1
        FROM lab_set210_after AS a
        WHERE a.sku = b.sku
    )
),
changed AS (
    SELECT b.sku, 'CHANGED'::text AS change_type
    FROM lab_set210_before AS b
    JOIN lab_set210_after AS a
        ON a.sku = b.sku
    WHERE ROW(
        b.product_name, b.unit_price, b.stock_count, b.product_status
    ) IS DISTINCT FROM ROW(
        a.product_name, a.unit_price, a.stock_count, a.product_status
    )
)
SELECT sku, change_type FROM added
UNION ALL
SELECT sku, change_type FROM removed
UNION ALL
SELECT sku, change_type FROM changed
ORDER BY sku;
~~~

Kết quả:

| sku | change_type |
| --- | --- |
| P02 | CHANGED |
| P03 | CHANGED |
| P05 | REMOVED |
| P07 | ADDED |
| P08 | ADDED |

Các truy vấn con trong ba CTE xác định các tập **không giao nhau về khóa** nếu điều kiện đúng và khóa trong snapshot duy nhất. Vì thế `UNION ALL` là lựa chọn rõ nghĩa: **ghép các nhóm biến động**, không cần tự loại trùng. Dùng `UNION` cũng có thể cho đúng danh sách mẫu, nhưng nó thêm bước loại hàng trùng và có thể che lỗi logic nếu các nhánh lẽ ra loại trừ nhau.

`ORDER BY sku` đặt ở **cuối phép hợp** để sắp xếp kết quả chung. Không nên giả định thứ tự đọc của từng nhánh hoặc thứ tự liệt kê trong `UNION ALL` là thứ tự đầu ra được bảo đảm.

## 11. Phân biệt phép toán tập hợp DISTINCT và ALL khi có hàng trùng

Hai bảng `lab_set210_before` và `lab_set210_after` có khóa chính nên không chứa hai sản phẩm cùng mã. Nhưng dữ liệu lấy từ **file CSV**, **log**, **kết quả JOIN**, **bảng staging** hoặc **báo cáo chưa loại trùng** có thể có nhiều hàng giống hệt nhau.

Trong trường hợp đó, cần phân biệt:

- **Tập hợp (*set*):** chỉ quan tâm một hàng **có xuất hiện hay không**.
- **Đa tập (*multiset/bag*):** quan tâm cả **hàng xuất hiện bao nhiêu lần**.

### 11.1. EXCEPT và EXCEPT ALL không giống nhau

Ví dụ hai tập không lưu thành bảng:

~~~sql
WITH
old_rows(code) AS (
    VALUES ('A'), ('A'), ('B')
),
new_rows(code) AS (
    VALUES ('A'), ('B')
)
SELECT code FROM old_rows
EXCEPT
SELECT code FROM new_rows;
~~~

Kết quả **không có hàng** vì xét như **tập giá trị phân biệt**, cả trước và sau đều gồm `A` và `B`.

Nhưng nếu yêu cầu “phát hiện có **một lần xuất hiện của A bị thiếu**”, dùng PostgreSQL `EXCEPT ALL`:

~~~sql
WITH
old_rows(code) AS (
    VALUES ('A'), ('A'), ('B')
),
new_rows(code) AS (
    VALUES ('A'), ('B')
)
SELECT code FROM old_rows
EXCEPT ALL
SELECT code FROM new_rows;
~~~

Kết quả:

| code |
| --- |
| A |

`EXCEPT ALL` giữ lại phần chênh lệch **số lần xuất hiện**: A có 2 lần trước và 1 lần sau nên còn 1 lần trong hiệu; B có một lần mỗi phía nên không còn.

| Phép toán | Cách xử lý trùng lặp |
| --- | --- |
| `UNION` | Hợp hai tập rồi loại hàng trùng |
| `UNION ALL` | Ghép hai đầu vào, giữ mọi lần xuất hiện |
| `INTERSECT` | Lấy giao, mỗi hàng phân biệt tối đa một lần |
| `INTERSECT ALL` | Lấy giao theo số lần xuất hiện nhỏ hơn ở hai phía |
| `EXCEPT` | Lấy hiệu của các hàng phân biệt |
| `EXCEPT ALL` | Lấy hiệu theo số lần xuất hiện còn dư |

Trong PostgreSQL, các biến thể `ALL` trên được hỗ trợ. Khả năng hỗ trợ `EXCEPT ALL` và `INTERSECT ALL` có thể khác giữa các SQL dialect và phiên bản; đừng áp dụng nguyên xi nếu hệ quản trị đích không có chúng.

### 11.2. “Một hàng thay đổi” khó xác định nếu không có khóa

Giả sử trước có hai hàng cùng tên `A`, sau có một hàng `A` và một hàng `B`. Phép toán tập hợp có thể chỉ ra **một A bớt đi, một B thêm vào**, nhưng không thể chứng minh A nào đã được **sửa thành B** nếu dữ liệu không có khóa định danh từng bản ghi.

Để gọi một bản ghi là **CHANGED**, cần có **khóa nghiệp vụ ổn định**, khóa kỹ thuật hoặc quy tắc đối chiếu rõ ràng. Khi dữ liệu không có khóa đáng tin cậy, chỉ nên kết luận về **chênh lệch các giá trị hoặc số lần xuất hiện**, không tự khẳng định quan hệ một–một giữa các hàng trước và sau.

## 12. Các điều kiện để đối chiếu đúng

### 12.1. Hai SELECT trong phép toán tập hợp phải tương thích

Với `UNION`, `INTERSECT` và `EXCEPT`, hai phía cần có **cùng số cột** và các cột ở vị trí tương ứng phải có **kiểu dữ liệu có thể kết hợp/so sánh** theo quy tắc của hệ quản trị.

Ví dụ phù hợp:

~~~sql
SELECT sku, unit_price, stock_count
FROM lab_set210_before
EXCEPT
SELECT sku, unit_price, stock_count
FROM lab_set210_after;
~~~

Ví dụ sai ý nghĩa:

~~~sql
-- Dung so cot nhung dat sai thu tu, kieu du lieu khong tuong thich.
SELECT sku, unit_price, stock_count
FROM lab_set210_before
EXCEPT
SELECT unit_price, sku, stock_count
FROM lab_set210_after;
~~~

SQL **so cột theo vị trí**, không tự căn theo tên cột. Nếu cố so một cột mã chuỗi với một cột số ở vị trí tương ứng, hệ quản trị có thể báo lỗi kiểu. Ngay cả khi các kiểu tương thích, so sai vị trí vẫn tạo chênh lệch vô nghĩa.

Nên liệt kê cột **rõ ràng**, với cùng thứ tự, thay vì dùng `SELECT *`. Nếu schema nguồn thêm một cột, `SELECT *` có thể làm thay đổi phạm vi đối chiếu, làm hỏng câu truy vấn hoặc đánh dấu hàng “thay đổi” vì thuộc tính mà nghiệp vụ không cần xét.

### 12.2. Phải chọn cùng phạm vi dữ liệu

Hai snapshot cần cùng ý nghĩa về:

- Thời điểm chụp dữ liệu và **mốc cập nhật đã hoàn tất**.
- Bộ lọc trạng thái, đơn vị kinh doanh, tenant, vùng hoặc khoảng thời gian.
- Các quyền nhìn thấy hàng (ví dụ chính sách phân quyền theo hàng).
- Quy tắc loại bản ghi xóa mềm, dữ liệu lưu trữ và trạng thái đang chờ xử lý.

Nếu bên trước chứa **mọi sản phẩm** còn bên sau chỉ chứa **sản phẩm ACTIVE**, các mã INACTIVE sẽ bị báo thiếu dù chúng không thực sự bị xóa. Điều kiện lọc không tương đương tạo **sai lệch giả**.

### 12.3. Chuẩn hóa dữ liệu trước khi so nếu nghiệp vụ yêu cầu

Hai giá trị có thể khác về biểu diễn nhưng được xem là tương đương theo nghiệp vụ:

| Dữ liệu nguồn | Dữ liệu đích | Câu hỏi cần làm rõ |
| --- | --- | --- |
| `'But'` | `'but'` | Tên sản phẩm có phân biệt chữ hoa/chữ thường không? |
| `'But '` | `'But'` | Khoảng trắng cuối có ý nghĩa hay chỉ là lỗi nhập liệu? |
| `12.0` | `12.00` | Đối chiếu **giá trị số** hay chuỗi được định dạng? |
| `NULL` | `''` | Thiếu dữ liệu và chuỗi rỗng có được coi là một không? |
| Một mốc thời gian UTC | Cùng thời điểm ở múi giờ khác | Có đang so **thời điểm** hay chuỗi hiển thị? |

Ví dụ muốn so tên không phân biệt khoảng trắng hai đầu và chữ hoa/thường trong PostgreSQL, có thể chuẩn hóa ở **cả hai phía**:

~~~sql
SELECT sku, LOWER(BTRIM(product_name)) AS normalized_name
FROM lab_set210_before
EXCEPT
SELECT sku, LOWER(BTRIM(product_name)) AS normalized_name
FROM lab_set210_after;
~~~

Việc chuẩn hóa phải được **quy định trước**, vì nó có thể xóa mất một chênh lệch mà hệ thống thực sự muốn theo dõi. Không tự chuẩn hóa `NULL` thành 0, hoặc hai mã sản phẩm khác nhau thành cùng một giá trị, nếu không có yêu cầu rõ ràng.

### 12.4. Phải có khóa ổn định và đủ thành phần

Ví dụ của bài sử dụng `sku` duy nhất trong toàn database thực hành. Trong hệ thống có nhiều doanh nghiệp (*tenant*) cùng dùng mã `P01`, khóa thật có thể là **`(tenant_id, sku)`**. Khi đó:

~~~sql
-- Vi du minh hoa voi hai bang gia dinh co khoa (tenant_id, sku).
SELECT ...
FROM inventory_before AS b
FULL OUTER JOIN inventory_after AS a
    ON a.tenant_id = b.tenant_id
   AND a.sku = b.sku;
~~~

Nếu chỉ nối bằng `sku`, sản phẩm P01 của tenant A có thể ghép với P01 của tenant B, khiến biến động giả, hàng bị nhân đôi hoặc thuộc tính bị quy cho sai chủ sở hữu.

Ngược lại, nếu **khóa định danh được đổi** giữa hai snapshot, đối chiếu theo khóa cũ/mới sẽ cho một hàng REMOVED và một hàng ADDED, **không tự biết đó là một hàng được đổi mã**. Muốn nhận diện “đổi khóa” cần một **định danh bất biến khác** hoặc bảng ánh xạ được nghiệp vụ xác thực.

## 13. Lập báo cáo đối chiếu: từ kết quả tới quyết định

Một báo cáo thường cần cả **kết quả chi tiết** lẫn **số lượng**:

~~~text
So sanh snapshot truoc va snapshot sau

Before keys: 6                After keys: 7
Union keys:  8

ADDED:       2  (P07, P08)
REMOVED:     1  (P05)
CHANGED:     2  (P02, P03)
UNCHANGED:   3  (P01, P04, P06)
~~~

Các con số này nhất quán theo khóa:

~~~text
Before = REMOVED + CHANGED + UNCHANGED = 1 + 2 + 3 = 6
After  = ADDED   + CHANGED + UNCHANGED = 2 + 2 + 3 = 7
Union  = ADDED   + REMOVED + CHANGED + UNCHANGED = 8
~~~

Đây là cách hiểu logic của dữ liệu mẫu, không phải cơ chế kiểm tra kỹ thuật của STEP hay một hành động tự cập nhật database.

### 13.1. Phân biệt báo cáo chênh lệch với đồng bộ dữ liệu

Truy vấn `SELECT` chỉ **đọc và chỉ ra biến động**. Nó không tự `INSERT` các mã ADDED, không tự `DELETE` mã REMOVED và không tự `UPDATE` các hàng CHANGED. Để **đồng bộ** hai bảng thật cần thêm quyết định:

- Snapshot nào là **nguồn sự thật**?
- REMOVED có nghĩa phải **xóa vật lý**, **xóa mềm**, hay chỉ tạm thời thiếu khi nhập liệu?
- CHANGED cần cập nhật những cột nào? Có cần giữ lịch sử hoặc ghi log?
- Hàng đích có khóa ngoại, trigger, ràng buộc hoặc giao dịch đồng thời cần được bảo vệ không?

Vì các quyết định này có thể ảnh hưởng dữ liệu thật, bài học tập trung vào **phát hiện và phân loại**, không cung cấp lệnh xóa/cập nhật hàng loạt để chạy thiếu kiểm soát. Việc phát hiện ra REMOVED **không tự động là lý do để xóa**.

### 13.2. Tính nhất quán theo thời điểm

Nếu bảng trước và bảng sau đang **được ghi liên tục**, việc đọc chúng tại những thời điểm không nhất quán có thể tạo ra chênh lệch giả. Với PostgreSQL, cơ chế MVCC và mức cô lập giao dịch như `REPEATABLE READ` có thể giúp một quy trình đọc nhiều truy vấn trên một snapshot nhất quán trong giao dịch, tùy thiết kế thu thập dữ liệu.

Đối chiếu giữa **hai database hoặc hai hệ thống khác nhau** còn cần kiểm soát thời điểm xuất dữ liệu và mốc xử lý của mỗi nguồn; một transaction trong một database không tự đảm bảo hai hệ thống hoàn toàn đồng bộ.

## 14. Hiệu năng khi so hai tập lớn

Đối chiếu vài hàng có thể thực hiện trực tiếp. Nhưng với hàng triệu bản ghi, `EXCEPT`, `INTERSECT`, `JOIN` và các phép sắp xếp có thể tiêu tốn bộ nhớ, CPU và không gian tạm.

Những lựa chọn cần cân nhắc:

1. **Giới hạn đúng các cột cần so.** So toàn bộ hàng với các cột mô tả dài không cần thiết có thể tạo nhiều dữ liệu trung gian hơn.
2. **Có khóa đối chiếu đáng tin cậy.** Khóa chính hoặc chỉ mục duy nhất giúp nối theo mã rõ ràng và ngăn nhân hàng do khóa trùng.
3. **Tận dụng ranh giới dữ liệu đã được chia hợp lý.** Với hệ thống lớn, có thể đối chiếu riêng theo tenant, phân vùng thời gian hoặc phạm vi phù hợp mà vẫn bảo đảm không bỏ lọt hàng.
4. **Đánh giá kế hoạch truy vấn.** PostgreSQL có thể dùng hash join, merge join, hash/sort set operation tùy số liệu thống kê và kích thước bảng.
5. **Không kết luận tốc độ chỉ từ một bài test nhỏ.** Tập vài hàng của bài chỉ dùng để học đúng ngữ nghĩa.
6. **Không dùng hàm băm như sự thay thế tuyệt đối cho so sánh giá trị.** Nếu dùng hash để lọc ứng viên khác biệt, phải có cách xử lý va chạm hash, chuẩn hóa kiểu và `NULL`, và quy tắc nghiệp vụ rõ ràng.

Ví dụ xem kế hoạch đối chiếu khóa:

~~~sql
EXPLAIN
SELECT a.sku
FROM lab_set210_after AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_set210_before AS b
    WHERE b.sku = a.sku
);
~~~

`EXPLAIN` của PostgreSQL hiển thị kế hoạch dự kiến, không cập nhật dữ liệu. Hai bảng mẫu đều có chỉ mục khóa chính trên `sku`, nhưng bộ tối ưu vẫn có thể chọn quét bảng khi dữ liệu nhỏ. Không cần tự tạo thêm chỉ mục trùng với khóa chính chỉ để chạy các ví dụ.

## 15. Khác biệt giữa các hệ quản trị SQL

Ý tưởng **hiệu – giao – hợp** của tập hàng và **ghép theo khóa** là phổ biến, nhưng **tên toán tử** và **mức hỗ trợ JOIN** không hoàn toàn giống nhau:

| Hệ quản trị | Hiệu hai tập | Giao hai tập | Ghép hai phía để phân loại |
| --- | --- | --- | --- |
| **PostgreSQL** | `EXCEPT`, `EXCEPT ALL` | `INTERSECT`, `INTERSECT ALL` | `FULL OUTER JOIN`, `IS DISTINCT FROM` |
| **SQL Server** | `EXCEPT` | `INTERSECT` | `FULL OUTER JOIN`; cú pháp so NULL-safe tùy phiên bản, có `IS DISTINCT FROM` trên các phiên bản mới phù hợp |
| **SQLite** | `EXCEPT` | `INTERSECT` | Không có `FULL OUTER JOIN` ở các bản cũ; bản mới hỗ trợ, cần kiểm tra phiên bản; `IS DISTINCT FROM` có ngữ nghĩa tương đương với so sánh NULL-safe phù hợp |
| **MySQL** | `EXCEPT` ở các phiên bản hỗ trợ tương ứng | `INTERSECT` ở các phiên bản hỗ trợ tương ứng | Thông thường không có `FULL OUTER JOIN` trực tiếp; có thể dùng các nhánh `LEFT JOIN` kết hợp `UNION ALL`; toán tử so bằng NULL-safe `<=>` |
| **Oracle Database** | `MINUS` theo cú pháp truyền thống; phiên bản hiện đại có thể hỗ trợ thêm tên tương đương | `INTERSECT` | `FULL OUTER JOIN` và các cách so sánh `NULL` phụ thuộc phiên bản/chức năng |

Không nên lấy một truy vấn có `EXCEPT ALL`, `FULL OUTER JOIN` và `IS DISTINCT FROM` của PostgreSQL rồi kỳ vọng chạy nguyên vẹn ở mọi hệ quản trị. Khi triển khai, cần tra cứu **phiên bản SQL dialect đang dùng** để xác nhận cú pháp.

### 15.1. Nếu hệ quản trị không hỗ trợ FULL OUTER JOIN

Có thể phân loại bằng **ba nhánh**: ADDED (bảng sau không có khóa ở trước), REMOVED (bảng trước không có khóa ở sau), CHANGED (INNER JOIN theo khóa và so thuộc tính). Sau đó **`UNION ALL`** các nhánh như mục 10.

Cách này không phụ thuộc vào một lệnh `FULL OUTER JOIN` duy nhất, nhưng vẫn cần viết **phép so giá trị có xử lý `NULL`** theo cú pháp hệ quản trị đó. Ví dụ MySQL có toán tử `<=>` cho so sánh bằng NULL-safe: với dữ liệu nullable, có thể biểu diễn khác biệt bằng `NOT (b.stock_count <=> a.stock_count)`.

### 15.2. Nếu không muốn viết EXCEPT

`NOT EXISTS` như ở mục 9 có thể biểu đạt hiệu của **các khóa**:

~~~sql
SELECT a.sku
FROM lab_set210_after AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_set210_before AS b
    WHERE b.sku = a.sku
);
~~~

Nó đặc biệt phù hợp khi chỉ tìm hàng **chưa có khóa tương ứng** và cần nối trên khóa ghép. Tuy nhiên, `NOT EXISTS` theo khóa **không phát hiện thay đổi thuộc tính** của các khóa đã tồn tại; vẫn cần phần so sánh CHANGED riêng.

## 16. Lỗi thường gặp khi đối chiếu hai tập dữ liệu

| Cách làm hoặc nhận định | Vấn đề | Cách phù hợp |
| --- | --- | --- |
| Gọi mọi hàng của `after EXCEPT before` là “bản ghi mới” | Hàng cùng khóa nhưng giá, trạng thái hoặc tồn kho đổi cũng xuất hiện | So **khóa** trước, rồi so thuộc tính của khóa chung |
| Chỉ dùng `before INTERSECT after` theo khóa để kết luận “không thay đổi” | Khóa vẫn tồn tại dù thuộc tính đổi | So đủ các thuộc tính cần theo dõi |
| Đảo chiều `EXCEPT` | “Chỉ có ở trước” khác “chỉ có ở sau” | Đặt tên before/after và xác định chiều so |
| Dùng `SELECT *` ở hai bảng có thứ tự cột khác nhau | Phép toán tập hợp so cột theo vị trí | Liệt kê cột, giữ đúng thứ tự và kiểu |
| Dùng `<>` để so các cột có thể NULL | Thay đổi `NULL ↔ giá trị` có thể bị bỏ sót | Dùng `IS DISTINCT FROM` hoặc cách NULL-safe tương đương |
| Dùng `COALESCE(stock, 0)` để so NULL với 0 | Gộp “chưa biết tồn” với “tồn bằng 0”, có thể xóa mất biến động thật | Giữ khác biệt bằng so sánh NULL-safe |
| Dùng `EXCEPT` khi cần biết số hàng giống nhau bị thừa/thiếu | `EXCEPT` loại trùng | `EXCEPT ALL` nếu hỗ trợ, hoặc tổng hợp số lần xuất hiện |
| Cùng mã xuất hiện nhiều lần ở một snapshot | `FULL JOIN` có thể nhân bản nhiều cặp và tạo kết luận sai | Dùng khóa duy nhất, kiểm tra trùng và quy tắc ghép |
| Nối chỉ bằng `sku` trong hệ thống đa tenant | Ghép nhầm các sản phẩm trùng mã ở tenant khác | Nối bằng toàn bộ khóa `(tenant_id, sku)` |
| Dùng `DISTINCT` để “sửa” số hàng JOIN bị nhân | Che dấu vấn đề quan hệ hoặc dữ liệu trùng | Xác định độ hạt, khóa và bội số trước |
| Đối chiếu hai snapshot khác phạm vi lọc | Tạo hàng ADDED/REMOVED giả | Chuẩn hóa cùng bộ lọc và mốc thời gian |
| Gọi thay đổi SKU là CHANGED mà không có ID bất biến | Khóa cũ mất, khóa mới xuất hiện, không đủ dữ liệu xác nhận cùng đối tượng | Dùng ID ổn định hoặc bảng ánh xạ được xác thực |
| Tự động DELETE khi thấy REMOVED | “Vắng mặt ở tập sau” chưa chắc là xóa hợp lệ | Kiểm chứng quy tắc đồng bộ và ảnh hưởng dữ liệu trước khi ghi |
| Giả định kết quả `EXCEPT` luôn được sắp sẵn | Phép tập hợp không cam kết thứ tự đầu ra | Đặt `ORDER BY` ở truy vấn cuối |

## 17. Bài tập thực hành có đáp án

Các bài dùng hai bảng `lab_set210_before` và `lab_set210_after` được tạo tại mục 2. Chúng chỉ sử dụng các câu `SELECT` hoặc CTE đọc dữ liệu. Hãy thử phân loại thủ công trước, sau đó chạy truy vấn để đối chiếu.

### Bài 1 — Tìm sản phẩm thêm mới bằng EXCEPT

**Yêu cầu:** lấy các mã chỉ xuất hiện trong snapshot sau.

**Đáp án:**

~~~sql
SELECT sku FROM lab_set210_after
EXCEPT
SELECT sku FROM lab_set210_before
ORDER BY sku;
~~~

Kết quả: **P07, P08**. Đây là `after EXCEPT before` trên **cột khóa**, không phải trên toàn bộ hàng.

### Bài 2 — Tìm sản phẩm bị thiếu ở snapshot sau

**Yêu cầu:** lấy mã sản phẩm có trước nhưng không còn sau.

**Đáp án:**

~~~sql
SELECT sku FROM lab_set210_before
EXCEPT
SELECT sku FROM lab_set210_after
ORDER BY sku;
~~~

Kết quả: **P05**. Đảo vị trí hai truy vấn sẽ tạo câu hỏi ngược lại.

### Bài 3 — Tìm khóa chung

**Yêu cầu:** dùng phép giao để lấy các mã tồn tại cả trước và sau.

**Đáp án:**

~~~sql
SELECT sku FROM lab_set210_before
INTERSECT
SELECT sku FROM lab_set210_after
ORDER BY sku;
~~~

Kết quả: **P01, P02, P03, P04, P06**. Trong đó P02 và P03 **vẫn đã thay đổi thuộc tính**, nên không thể gọi cả năm mã là UNCHANGED.

### Bài 4 — Tìm hàng hoàn toàn không đổi

**Yêu cầu:** tìm những hàng mà **cả năm cột** có cùng giá trị ở hai snapshot.

**Đáp án:**

~~~sql
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_before
INTERSECT
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_after
ORDER BY sku;
~~~

Kết quả: **P01, P04, P06**. P04 có `stock_count = NULL` ở cả hai bảng, vẫn thuộc phần giao của các hàng.

### Bài 5 — Vì sao EXCEPT toàn bộ hàng trả cả bản ghi đổi giá?

Chạy:

~~~sql
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_after
EXCEPT
SELECT sku, product_name, unit_price, stock_count, product_status
FROM lab_set210_before
ORDER BY sku;
~~~

**Câu hỏi:** tại sao kết quả có **P02** và **P03**, dù hai mã này đã tồn tại từ trước?

**Đáp án:** phép `EXCEPT` đang so **cả hàng**, gồm giá, tồn và trạng thái. P02 có giá khác, P03 có tồn/trạng thái khác, nên phiên bản hàng phía sau không giống phiên bản hàng phía trước. Muốn chỉ nhận mã ADDED, áp dụng `EXCEPT` trên **`sku`**.

### Bài 6 — Tìm CHANGED bằng so sánh NULL-safe

**Yêu cầu:** chỉ lấy sản phẩm có ở cả hai snapshot và ít nhất một trong bốn thuộc tính thay đổi.

**Đáp án:**

~~~sql
SELECT b.sku
FROM lab_set210_before AS b
JOIN lab_set210_after AS a
    ON a.sku = b.sku
WHERE b.product_name IS DISTINCT FROM a.product_name
   OR b.unit_price IS DISTINCT FROM a.unit_price
   OR b.stock_count IS DISTINCT FROM a.stock_count
   OR b.product_status IS DISTINCT FROM a.product_status
ORDER BY b.sku;
~~~

Kết quả: **P02, P03**.

### Bài 7 — Phân biệt NULL và 0 trong đối chiếu

Giả sử ở một snapshot mới khác, sản phẩm P04 có `stock_count = 0` thay vì `NULL` như bảng trước. Khi đó:

~~~sql
SELECT
    NULL::integer <> 0 AS ordinary_compare,
    NULL::integer IS DISTINCT FROM 0 AS safe_compare,
    NULL::integer IS DISTINCT FROM NULL::integer AS both_missing;
~~~

**Đáp án:** `ordinary_compare = NULL` (UNKNOWN), `safe_compare = TRUE` và `both_missing = FALSE`. Một giá trị thiếu và một giá trị bằng 0 phải được phân biệt nếu hệ thống không có quy tắc coi chúng tương đương.

### Bài 8 — Phân loại trong một câu FULL OUTER JOIN

**Yêu cầu:** hiển thị mỗi `sku` một dòng với nhãn ADDED, REMOVED, CHANGED hoặc UNCHANGED.

**Đáp án:**

~~~sql
SELECT
    COALESCE(b.sku, a.sku) AS sku,
    CASE
        WHEN b.sku IS NULL THEN 'ADDED'
        WHEN a.sku IS NULL THEN 'REMOVED'
        WHEN ROW(
            b.product_name, b.unit_price, b.stock_count, b.product_status
        ) IS DISTINCT FROM ROW(
            a.product_name, a.unit_price, a.stock_count, a.product_status
        ) THEN 'CHANGED'
        ELSE 'UNCHANGED'
    END AS change_type
FROM lab_set210_before AS b
FULL OUTER JOIN lab_set210_after AS a
    ON a.sku = b.sku
ORDER BY sku;
~~~

Kết quả theo thứ tự mã: **P01 UNCHANGED, P02 CHANGED, P03 CHANGED, P04 UNCHANGED, P05 REMOVED, P06 UNCHANGED, P07 ADDED, P08 ADDED**.

### Bài 9 — Đếm mỗi trạng thái

**Yêu cầu:** từ truy vấn bài 8, tạo bảng đếm số mã theo `change_type`.

**Đáp án:**

~~~sql
WITH changes AS (
    SELECT
        CASE
            WHEN b.sku IS NULL THEN 'ADDED'
            WHEN a.sku IS NULL THEN 'REMOVED'
            WHEN ROW(
                b.product_name, b.unit_price, b.stock_count, b.product_status
            ) IS DISTINCT FROM ROW(
                a.product_name, a.unit_price, a.stock_count, a.product_status
            ) THEN 'CHANGED'
            ELSE 'UNCHANGED'
        END AS change_type
    FROM lab_set210_before AS b
    FULL OUTER JOIN lab_set210_after AS a
        ON a.sku = b.sku
)
SELECT change_type, COUNT(*) AS item_count
FROM changes
GROUP BY change_type
ORDER BY change_type;
~~~

Kết quả: **ADDED 2, CHANGED 2, REMOVED 1, UNCHANGED 3**.

### Bài 10 — Khác biệt giữa EXCEPT và EXCEPT ALL

Hai tập có số lần xuất hiện:

~~~text
Before: A, A, B, C
After:  A, B, C
~~~

**Câu hỏi:** `before EXCEPT after` trả gì? `before EXCEPT ALL after` trả gì?

**Đáp án:** `EXCEPT` thông thường trả **không hàng** vì cả hai tập có cùng các giá trị phân biệt A, B, C. `EXCEPT ALL` trả **một A**, vì trước có hai A nhưng sau chỉ một.

### Bài 11 — Chỉ phát hiện thay đổi giá, bỏ qua tồn và trạng thái

**Yêu cầu:** lấy mã có ở cả hai snapshot nhưng `unit_price` thay đổi. Các thuộc tính khác không được ảnh hưởng kết quả.

**Đáp án:**

~~~sql
SELECT
    b.sku,
    b.unit_price AS old_price,
    a.unit_price AS new_price
FROM lab_set210_before AS b
JOIN lab_set210_after AS a
    ON a.sku = b.sku
WHERE b.unit_price IS DISTINCT FROM a.unit_price
ORDER BY b.sku;
~~~

Kết quả chỉ có **P02**, giá **10.00 → 12.00**. P03 không xuất hiện vì giá vẫn là 350.00, dù các cột khác đã thay đổi. Bài toán cho thấy danh sách cột được so chính là **định nghĩa nghiệp vụ của CHANGED**.

### Bài 12 — Giải thích trường hợp đổi khóa

Giả sử sản phẩm P05 không bị loại khỏi kinh doanh mà chỉ **đổi mã từ P05 sang P09** trong snapshot sau. Nếu so theo `sku`, kết quả sẽ phân loại thế nào?

**Đáp án:** mã **P05** được xếp **REMOVED** và **P09** được xếp **ADDED**. Chỉ riêng hai bảng với `sku` làm khóa **không đủ thông tin** để kết luận hai mã là cùng một thực thể được đổi mã. Cần thêm ID bất biến, bảng ánh xạ hoặc một quy tắc được kiểm chứng để nhận diện thao tác đổi khóa.

## 18. Ghi nhớ

| Bạn muốn biết | Cách tiếp cận tiêu biểu | Điểm cần nhớ |
| --- | --- | --- |
| Mã chỉ có ở sau | `SELECT key FROM after EXCEPT SELECT key FROM before` | Chiều `after - before` |
| Mã chỉ có ở trước | `SELECT key FROM before EXCEPT SELECT key FROM after` | Chiều `before - after` |
| Mã hiện diện cả hai phía | `INTERSECT` trên khóa | Chưa kết luận được thuộc tính có giống nhau |
| Hàng hoàn toàn giống nhau | `INTERSECT` trên **cùng danh sách cột** | Trùng theo giá trị và cột được chọn |
| Cùng khóa nhưng thuộc tính đổi | `INNER JOIN` theo khóa + `IS DISTINCT FROM` | So giá trị an toàn với `NULL` |
| Toàn bộ ADDED/REMOVED/CHANGED/UNCHANGED | `FULL OUTER JOIN` + `CASE` | Khóa dùng để nhận diện hàng thiếu phải đáng tin cậy |
| Không có FULL OUTER JOIN | Ba nhánh ADDED/REMOVED/CHANGED + `UNION ALL` | Giữ thống nhất logic khóa và so sánh |
| Số lần xuất hiện của hàng trùng thay đổi | `EXCEPT ALL` nếu hệ hỗ trợ | `EXCEPT` thường loại hàng trùng |
| Tìm hàng không có khóa tương ứng | `NOT EXISTS` | Thường rõ nghĩa hơn `NOT IN` khi có `NULL` |

Khi đối chiếu hai tập dữ liệu, hãy luôn tách hai câu hỏi: **“Khóa nào có hoặc không có ở mỗi phía?”** và **“Với những khóa chung, giá trị nào đã đổi?”**. Phép `EXCEPT` và `INTERSECT` giúp giải quyết vấn đề **hiệu và giao của tập hàng**; `JOIN` theo khóa với so sánh NULL-safe giúp xác định **sự thay đổi của cùng một thực thể**. Chọn đúng phạm vi, khóa và chiều so sánh sẽ giúp bạn phát hiện biến động đáng tin cậy mà không nhầm một hàng đổi giá với một sản phẩm hoàn toàn mới.
