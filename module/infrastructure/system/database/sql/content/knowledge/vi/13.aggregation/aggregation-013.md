# Tổng hợp chuỗi, mảng hoặc JSON theo hệ quản trị trong SQL

Các hàm tổng hợp quen thuộc như `COUNT`, `SUM`, `AVG` biến nhiều hàng thành một giá trị số. Nhưng khi xây dựng báo cáo, API hoặc dữ liệu xuất ra, ta thường muốn **gom nhiều giá trị thành một danh sách**:

- Một chuỗi tên sản phẩm: `Mouse, Keyboard, Gift wrap`.
- Một mảng có kiểu phần tử: `{Mouse,Keyboard,Gift wrap}` trong biểu diễn mảng PostgreSQL.
- Một mảng JSON: `[{"product":"Mouse","quantity":2}, ...]`.
- Một đối tượng JSON ánh xạ mã dòng hàng đến chi tiết: `{"1":{"product":"Mouse","quantity":2}, ...}`.

SQL và các hệ quản trị cung cấp nhiều hàm cho yêu cầu này: `STRING_AGG`, `LISTAGG`, `GROUP_CONCAT`, `ARRAY_AGG`, `JSON_AGG`, `JSONB_AGG`, `JSON_ARRAYAGG`, `JSON_OBJECTAGG` và các biến thể. **Tên hàm, thứ tự phần tử, cách xử lý `NULL`, giới hạn kích thước và kiểu kết quả khác nhau theo DBMS**.

Bài học giải thích nguyên lý *tổng hợp thành tập hợp* (collection aggregation), cách áp dụng với `GROUP BY`, sắp xếp và loại trùng trong tập, lựa chọn chuỗi/mảng/JSON, và cách chuyển cùng một yêu cầu qua PostgreSQL, MySQL/MariaDB, SQL Server, Oracle và SQLite.

> Ví dụ chạy đầy đủ chủ yếu dùng **PostgreSQL**. Các ví dụ phương ngữ khác minh họa ý tưởng SQL tương ứng; cần điều chỉnh DDL, tên bảng và cú pháp cho đúng phiên bản/edition khi triển khai. Không giả định mọi hàm cùng tên có cùng hành vi.

## 1. Từ nhiều dòng thành một giá trị: ý nghĩa của tổng hợp

Xét bảng dòng hàng của một đơn bán:

| sale_id | line_no | product_name | quantity |
|---:|---:|---|---:|
| 1001 | 1 | Mouse | 2 |
| 1001 | 2 | Keyboard | 1 |
| 1001 | 3 | Gift wrap | 1 |
| 1002 | 1 | SQL Book | 1 |
| 1002 | 2 | Mouse | 1 |
| 1002 | 3 | Mouse | 1 |

Một dòng kết quả theo mỗi `sale_id` có thể có các kiểu dữ liệu sau:

| Kiểu tổng hợp | Giá trị minh họa cho đơn 1002 | Dùng khi nào? |
|---|---|---|
| Chuỗi | `SQL Book, Mouse, Mouse` | Tiêu đề, báo cáo văn bản, CSV hiển thị đơn giản |
| Mảng SQL | `ARRAY['SQL Book','Mouse','Mouse']` | Xử lý danh sách cùng kiểu trong hệ hỗ trợ mảng |
| Mảng JSON | `["SQL Book","Mouse","Mouse"]` | API, cấu trúc danh sách trao đổi giữa hệ thống |
| Mảng đối tượng JSON | `[{"line":1,"product":"SQL Book"}, ...]` | Xuất chi tiết gồm nhiều trường mỗi phần tử |
| Đối tượng JSON | `{"1":"SQL Book","2":"Mouse","3":"Mouse"}` | Tra cứu theo khóa duy nhất, không dùng thứ tự phần tử làm ngữ nghĩa |

**Tổng hợp không đồng nghĩa chuẩn hóa dữ liệu.** Bảng quan hệ gốc vẫn có một dòng mỗi sản phẩm; danh sách chỉ là một **cách biểu diễn kết quả truy vấn**. Đừng vội thay bảng con bằng một cột JSON/chuỗi chỉ vì API cuối cùng cần JSON.

### Các quyết định cần làm rõ

Trước khi chọn hàm, cần trả lời:

1. **Nhóm theo gì?** Mỗi đơn hàng, mỗi khách, mỗi danh mục hay toàn bảng?
2. **Thứ tự phần tử thế nào?** Theo số dòng hàng, tên, ngày tạo hay không cần thứ tự?
3. **Giữ trùng hay loại trùng?** Hai dòng “Mouse” có thể là hai chi tiết bán hàng hợp lệ.
4. **`NULL` được xử lý ra sao?** Bỏ qua, tạo phần tử `null`, hay thay bằng nhãn?
5. **Cần dữ liệu có kiểu hay chỉ để trình bày?** Chuỗi có dấu phân cách không bảo toàn cấu trúc như JSON.
6. **Trường hợp không có hàng con trả về gì?** `NULL`, chuỗi rỗng, mảng rỗng hay `[]`?
7. **Khối lượng mỗi nhóm có thể lớn đến đâu?** Chuỗi/JSON rất lớn có thể làm tăng chi phí bộ nhớ và truyền tải.

## 2. Dữ liệu mẫu có thể tái tạo

Dùng hai bảng để thấy sự khác biệt giữa đơn hàng **có dòng hàng** và đơn **không có dòng hàng**. Ví dụ PostgreSQL:

```sql
CREATE TEMP TABLE demo_sales (
    sale_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TEMP TABLE demo_sale_lines (
    sale_id INTEGER NOT NULL
        REFERENCES demo_sales(sale_id),
    line_no INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (sale_id, line_no)
);

INSERT INTO demo_sales (sale_id, customer_name)
VALUES
    (1001, 'An'),
    (1002, 'Bình'),
    (1003, 'Chi');

INSERT INTO demo_sale_lines
    (sale_id, line_no, product_name, category, quantity, unit_price)
VALUES
    (1001, 1, 'Mouse',     'electronics', 2, 350),
    (1001, 2, 'Keyboard',  'electronics', 1, 900),
    (1001, 3, 'Gift wrap', NULL,          1,  20),
    (1002, 1, 'SQL Book',  'books',       1, 250),
    (1002, 2, 'Mouse',     'electronics', 1, 350),
    (1002, 3, 'Mouse',     'electronics', 1, 350);
```

Bảng `demo_sales` có đơn **1003 chưa có dòng hàng**. Hai dòng `Mouse` của đơn 1002 là hai **dòng khác nhau** (`line_no` = 2 và 3), dù tên giống nhau. Một dòng của đơn 1001 có `category IS NULL` để minh họa cách các hàm xử lý giá trị thiếu.

Truy vấn số học thông thường làm mốc:

```sql
SELECT
    sale_id,
    COUNT(*) AS line_count,
    SUM(quantity * unit_price) AS total_amount
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Kết quả:

| sale_id | line_count | total_amount |
|---:|---:|---:|
| 1001 | 3 | 1620 |
| 1002 | 3 | 950 |

Không có hàng cho 1003, vì chưa có dòng con trong `demo_sale_lines`. Nếu muốn vẫn trả về 1003, cần bắt đầu từ bảng cha bằng `LEFT JOIN` hoặc dùng truy vấn con tương quan.

## 3. Tổng hợp chuỗi: `STRING_AGG`, `LISTAGG`, `GROUP_CONCAT`

Tổng hợp chuỗi nối nhiều giá trị văn bản thành **một chuỗi**, thường có dấu phân cách.

### 3.1. PostgreSQL: `STRING_AGG`

Cú pháp phổ biến:

```sql
STRING_AGG(value_expression, delimiter ORDER BY sort_expression)
```

Ví dụ danh sách tên sản phẩm của từng đơn, **theo đúng số dòng hàng**:

```sql
SELECT
    sale_id,
    STRING_AGG(product_name, ', ' ORDER BY line_no)
        AS product_list
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Kết quả:

| sale_id | product_list |
|---:|---|
| 1001 | Mouse, Keyboard, Gift wrap |
| 1002 | SQL Book, Mouse, Mouse |

`ORDER BY line_no` **nằm bên trong lời gọi tổng hợp**. Nó quyết định thứ tự **các giá trị được nối**. Nếu chỉ thêm `ORDER BY sale_id` ở cuối, ta mới sắp **các dòng nhóm** trong kết quả chứ không đảm bảo thứ tự tên bên trong `product_list`.

Đây là phân biệt quan trọng:

```sql
-- Sắp chuỗi phần tử: ORDER BY bên trong STRING_AGG.
STRING_AGG(product_name, ', ' ORDER BY line_no)

-- Sắp các nhóm sau tổng hợp: ORDER BY của SELECT.
ORDER BY sale_id
```

Có thể viết cả hai trong cùng truy vấn, như ví dụ đầy đủ phía trên.

### 3.2. Dấu phân cách là một phần của quy tắc xuất dữ liệu

```sql
SELECT sale_id,
       STRING_AGG(product_name, ' | ' ORDER BY line_no)
           AS product_list
FROM demo_sale_lines
GROUP BY sale_id;
```

Đơn 1001 sẽ có chuỗi `Mouse | Keyboard | Gift wrap`. Dấu phân cách không tạo kiểu danh sách có cấu trúc; nếu tên sản phẩm cũng chứa ký tự `|` hay dấu phẩy, việc tách chuỗi trở lại thành các phần tử có thể **không xác định đúng**.

Ví dụ, nếu tên sản phẩm thực tế là `"Tea, Green"`, dùng dấu phẩy để nối sẽ tạo chuỗi dễ hiểu nhầm:

```text
Tea, Green, Mouse
```

Một ứng dụng không thể biết chắc đó là hai sản phẩm hay ba sản phẩm nếu thiếu quy tắc escape/quote. Nếu cần truyền dữ liệu cấu trúc giữa hệ thống, nên ưu tiên **JSON array** hoặc giao thức serialization có quy tắc escape rõ ràng, thay vì xem chuỗi ghép dấu phẩy là dữ liệu có thể giải mã an toàn.

### 3.3. Xử lý `NULL` trong STRING_AGG

PostgreSQL `STRING_AGG` bỏ qua **các giá trị đầu vào `NULL`**. Ví dụ:

```sql
SELECT
    sale_id,
    STRING_AGG(category, ', ' ORDER BY line_no)
        AS category_list
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Đơn 1001 có `electronics, electronics`; dòng `Gift wrap` với `category NULL` bị bỏ qua. Dòng đó **không tạo dấu phân cách trống** ở cuối.

Nếu muốn hiển thị một nhãn cho giá trị thiếu:

```sql
SELECT
    sale_id,
    STRING_AGG(
        COALESCE(category, '(unclassified)'),
        ', ' ORDER BY line_no
    ) AS category_list
FROM demo_sale_lines
GROUP BY sale_id;
```

Đơn 1001 khi đó trở thành `electronics, electronics, (unclassified)`. Nhãn `(unclassified)` là quyết định trình bày; nó **không biến `NULL` của dữ liệu gốc thành một danh mục thật**.

**Phân biệt `NULL` với chuỗi rỗng:** `''` là một giá trị chuỗi có độ dài zero trên PostgreSQL. `STRING_AGG` có thể nối nó và vẫn chèn dấu phân cách theo quy tắc; chỉ giá trị SQL `NULL` mới bị bỏ qua. Oracle có quy tắc riêng với chuỗi rỗng, nên không nên sao chép giả định này sang mọi hệ.

### 3.4. Loại giá trị lặp bằng DISTINCT

Nếu muốn **danh mục khác nhau** thay vì mọi dòng chi tiết, có thể dùng:

```sql
SELECT
    sale_id,
    STRING_AGG(DISTINCT category, ', ' ORDER BY category)
        AS unique_categories
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Kết quả:

| sale_id | unique_categories |
|---:|---|
| 1001 | electronics |
| 1002 | books, electronics |

Ở đơn 1001, `category NULL` bị bỏ qua và hai `electronics` được gộp thành một. Ở đơn 1002, `Mouse` lặp nhưng danh mục `electronics` chỉ xuất hiện một lần trong chuỗi.

**Đừng áp dụng `DISTINCT` một cách máy móc.** Nếu báo cáo đơn hàng cần hiện hai dòng “Mouse” riêng biệt, loại trùng theo tên sản phẩm sẽ mất thông tin. Khi một phần tử đại diện một bản ghi có ID riêng, thường nên tổng hợp **đối tượng chứa ID/số thứ tự** thay vì chỉ tên.

Trong PostgreSQL, khi dùng `DISTINCT` và `ORDER BY` trong cùng lời gọi tổng hợp, có những giới hạn cú pháp: các biểu thức sắp xếp phải phù hợp với tập biểu thức được `DISTINCT` xét. Nếu cần loại trùng theo một khóa nhưng sắp theo khóa khác, hãy xử lý lựa chọn dòng trong truy vấn con trước rồi mới tổng hợp.

## 4. Tổng hợp mảng SQL bằng ARRAY_AGG

Mảng SQL có **kiểu phần tử** rõ ràng, ví dụ `TEXT[]`, `INTEGER[]` hoặc `UUID[]` trong PostgreSQL. `ARRAY_AGG` thu các giá trị thành một mảng, giúp giữ cấu trúc danh sách thay vì ghép thành chuỗi.

```sql
SELECT
    sale_id,
    ARRAY_AGG(product_name ORDER BY line_no)
        AS products
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Kết quả logic:

```text
sale_id=1001 → ['Mouse', 'Keyboard', 'Gift wrap']
sale_id=1002 → ['SQL Book', 'Mouse', 'Mouse']
```

PostgreSQL thường hiển thị mảng `TEXT[]` bằng cú pháp dấu ngoặc nhọn; biểu diễn văn bản cụ thể còn phụ thuộc ký tự trong phần tử. Ở tầng ứng dụng, đó vẫn là **một giá trị mảng có kiểu**, không phải một chuỗi CSV.

### 4.1. ARRAY_AGG và NULL khác STRING_AGG

Trong PostgreSQL, `ARRAY_AGG` **giữ giá trị SQL `NULL` thành phần tử `NULL`** nếu đầu vào của nó là `NULL`.

```sql
SELECT
    sale_id,
    ARRAY_AGG(category ORDER BY line_no) AS categories
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Đối với đơn 1001, mảng tương ứng có ba vị trí:

```text
['electronics', 'electronics', NULL]
```

Như vậy:

| Đầu vào | `STRING_AGG(category, ', ')` | `ARRAY_AGG(category)` |
|---|---|---|
| electronics, electronics, `NULL` | `electronics, electronics` | `['electronics','electronics',NULL]` |
| chỉ toàn `NULL` | SQL `NULL` | Mảng chứa các phần tử `NULL` tương ứng |
| không có dòng nào để tổng hợp | SQL `NULL` | SQL `NULL` |

Muốn bỏ phần tử `NULL` trong `ARRAY_AGG`, dùng `FILTER` trên DBMS hỗ trợ, hoặc lọc trước trong truy vấn con:

```sql
SELECT
    sale_id,
    ARRAY_AGG(category ORDER BY line_no)
        FILTER (WHERE category IS NOT NULL) AS categories
FROM demo_sale_lines
GROUP BY sale_id;
```

Trong nhóm có dòng, nhưng tất cả `category` đều `NULL`, bộ tổng hợp sau khi lọc không còn phần tử; PostgreSQL `ARRAY_AGG` trả SQL `NULL`, **không tự trả mảng rỗng**. Cần sử dụng `COALESCE` nếu hợp đồng đầu ra muốn mảng rỗng.

### 4.2. DISTINCT trong ARRAY_AGG

```sql
SELECT
    sale_id,
    ARRAY_AGG(DISTINCT category ORDER BY category)
        FILTER (WHERE category IS NOT NULL) AS category_set
FROM demo_sale_lines
GROUP BY sale_id;
```

Kết quả logic: đơn 1001 là mảng `['electronics']`; đơn 1002 là `['books','electronics']`. Đây là “một mảng các danh mục khác nhau”, không phải mảng chi tiết theo thứ tự dòng hàng.

Mảng SQL chỉ thuận lợi khi DBMS và driver hỗ trợ. MySQL/SQL Server/SQLite trong các cách dùng phổ biến **không có cột `TEXT[]` tương đương PostgreSQL**. Nếu muốn API nhận một danh sách, JSON array thường là định dạng phổ quát hơn so với đưa mảng SQL chuyên biệt qua nhiều hệ quản trị.

## 5. Tổng hợp JSON: từ một hàng con thành một phần tử có cấu trúc

Chuỗi ghép tốt cho hiển thị; mảng SQL tốt cho phần tử đồng kiểu; **JSON** phù hợp khi mỗi phần tử có nhiều trường và kết quả được đưa tới API.

### 5.1. PostgreSQL: `JSON_AGG` và `JSONB_AGG`

`JSON_AGG` và `JSONB_AGG` thu các biểu thức thành **mảng JSON**. `JSONB_AGG` trả kiểu `JSONB`, một dạng biểu diễn JSON được PostgreSQL xử lý và lập chỉ mục chuyên biệt.

Tổng hợp tên sản phẩm:

```sql
SELECT
    sale_id,
    JSONB_AGG(product_name ORDER BY line_no)
        AS product_names
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Kết quả logic:

```json
["Mouse", "Keyboard", "Gift wrap"]
```

cho đơn 1001, và:

```json
["SQL Book", "Mouse", "Mouse"]
```

cho đơn 1002.

Tuy nhiên, mảng chỉ có tên không đủ để phân biệt dòng lặp. Với API đơn hàng, thường cần một **mảng đối tượng**.

### 5.2. Kết hợp `JSONB_BUILD_OBJECT` và `JSONB_AGG`

```sql
SELECT
    sale_id,
    JSONB_AGG(
        JSONB_BUILD_OBJECT(
            'lineNo', line_no,
            'product', product_name,
            'category', category,
            'quantity', quantity,
            'unitPrice', unit_price
        )
        ORDER BY line_no
    ) AS items
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Đơn 1001 có cấu trúc logic tương đương:

```json
[
  {
    "lineNo": 1,
    "product": "Mouse",
    "category": "electronics",
    "quantity": 2,
    "unitPrice": 350
  },
  {
    "lineNo": 2,
    "product": "Keyboard",
    "category": "electronics",
    "quantity": 1,
    "unitPrice": 900
  },
  {
    "lineNo": 3,
    "product": "Gift wrap",
    "category": null,
    "quantity": 1,
    "unitPrice": 20
  }
]
```

Ở ví dụ này, trường `category` có JSON `null` vì đầu vào SQL `NULL` được đưa vào bộ xây đối tượng. Một phần tử JSON có thể mang chuỗi, số, boolean, đối tượng lồng nhau hoặc `null`; ngược lại, ghép chuỗi bằng dấu phân cách không bảo toàn những loại dữ liệu ấy.

**Lưu ý về JSONB:** `JSONB` không cam kết giữ nguyên thứ tự khóa bên trong **đối tượng JSON**, nhưng thứ tự **phần tử của mảng JSON** được xây qua `ORDER BY line_no` có ý nghĩa. Ứng dụng không nên dựa vào thứ tự khóa `"lineNo", "product", ...` trong mỗi đối tượng.

### 5.3. `JSON_AGG`, `JSONB_AGG` và kiểu trả về

Trong PostgreSQL:

| Hàm | Kết quả | Đặc trưng |
|---|---|---|
| `JSON_AGG(expr)` | JSON array kiểu `JSON` | Phù hợp biểu diễn JSON thông thường |
| `JSONB_AGG(expr)` | JSON array kiểu `JSONB` | Có ngữ nghĩa và công cụ thao tác `JSONB` |
| `JSON_BUILD_OBJECT(k,v,...)` | JSON object kiểu `JSON` | Xây đối tượng từ các cặp khóa–giá trị |
| `JSONB_BUILD_OBJECT(k,v,...)` | JSON object kiểu `JSONB` | Xây đối tượng `JSONB` |
| `JSON_OBJECT_AGG(key,value)` | JSON object kiểu `JSON` | Gom nhiều hàng thành thuộc tính của một đối tượng |
| `JSONB_OBJECT_AGG(key,value)` | JSON object kiểu `JSONB` | Gom nhiều hàng thành thuộc tính của một đối tượng `JSONB` |

Không nên chọn `JSONB` chỉ vì tên nghe tối ưu hơn. Nếu chỉ xuất JSON ra client mà không cần xử lý/tra cứu nội dung dưới dạng `JSONB` ở DB, hiệu năng phụ thuộc số lượng, kích thước dữ liệu và mục đích sử dụng. Việc xây JSON ngay trong DB cũng có chi phí CPU/bộ nhớ, phải đánh giá trong bối cảnh tải thực tế.

## 6. JSON_OBJECT_AGG: gom thành đối tượng thay vì mảng

Mảng JSON là một **danh sách**, còn đối tượng JSON chứa các **thuộc tính được định danh bằng khóa chuỗi**. Khi nghiệp vụ cần truy cập phần tử bằng một khóa duy nhất, `JSON_OBJECT_AGG` hoặc `JSONB_OBJECT_AGG` có thể phù hợp.

Ví dụ, trong phạm vi mỗi đơn hàng, `line_no` là duy nhất:

```sql
SELECT
    sale_id,
    JSONB_OBJECT_AGG(
        line_no::TEXT,
        JSONB_BUILD_OBJECT(
            'product', product_name,
            'quantity', quantity
        )
        ORDER BY line_no
    ) AS lines_by_number
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Đối với đơn 1002, đối tượng logic:

```json
{
  "1": {"product": "SQL Book", "quantity": 1},
  "2": {"product": "Mouse", "quantity": 1},
  "3": {"product": "Mouse", "quantity": 1}
}
```

Những lưu ý thiết kế:

- **Khóa JSON là chuỗi**. `line_no::TEXT` làm việc này tường minh ở PostgreSQL.
- Khóa trong đối tượng không có thứ tự nghiệp vụ bảo đảm. Muốn hiển thị theo thứ tự dòng, **mảng đối tượng** với `ORDER BY line_no` dễ phù hợp hơn.
- **Không để khóa trùng** nếu muốn mỗi bản ghi có vị trí xác định. Với nhiều bản ghi trùng khóa, các DBMS và dạng JSON/JSONB có thể có quy tắc khác nhau (chọn giá trị sau cùng, báo lỗi hoặc biểu diễn khóa trùng). Không nên dựa vào thứ tự ngẫu nhiên để quyết định giá trị nào được giữ.
- PostgreSQL `JSONB_OBJECT_AGG` không chấp nhận khóa đầu vào SQL `NULL`. Cần kiểm tra/lọc dữ liệu khóa hoặc bảo đảm nó `NOT NULL`.
- JSON object phù hợp cho truy cập theo khóa **duy nhất**, không phải để lưu các mục có thể cùng khóa và vẫn cần giữ cả hai. Nếu khóa có thể lặp, dùng mảng và đặt khóa trong mỗi đối tượng.

### 6.1. Có nên dùng tên sản phẩm làm khóa?

Truy vấn sau tuy hợp lệ về ý tưởng, nhưng **không phù hợp với dữ liệu mẫu**:

```sql
SELECT sale_id,
       JSONB_OBJECT_AGG(product_name, quantity) AS quantity_by_product
FROM demo_sale_lines
GROUP BY sale_id;
```

Đơn 1002 có **hai dòng cùng tên `Mouse`**. Đối tượng JSON không thể biểu diễn hai thuộc tính có cùng tên theo một cách duy nhất và đáng tin cậy ở mọi hệ. Với `JSONB`, các khóa trùng không được giữ thành hai thuộc tính độc lập. Nếu muốn tổng số lượng theo sản phẩm, hãy **tổng hợp số lượng trước**, rồi mới xây JSON:

```sql
WITH by_product AS (
    SELECT sale_id, product_name, SUM(quantity) AS total_quantity
    FROM demo_sale_lines
    GROUP BY sale_id, product_name
)
SELECT
    sale_id,
    JSONB_OBJECT_AGG(product_name, total_quantity)
        AS quantity_by_product
FROM by_product
GROUP BY sale_id
ORDER BY sale_id;
```

Đơn 1002 khi đó có khóa `"Mouse"` với tổng số lượng `2`, cùng `"SQL Book": 1`. Nếu hai sản phẩm thực sự khác nhau nhưng có cùng tên, **khóa sản phẩm duy nhất như `product_id`/`sku` mới là lựa chọn tốt hơn**.

## 7. Thứ tự phần tử: ORDER BY bên trong hàm tổng hợp

Trong SQL, **không có `ORDER BY` thì thứ tự các hàng nói chung không được bảo đảm**. Điều này ảnh hưởng trực tiếp tới những hàm tổng hợp tạo danh sách.

### 7.1. Sắp thứ tự các phần tử

Trong PostgreSQL:

```sql
SELECT
    sale_id,
    STRING_AGG(product_name, ', ' ORDER BY line_no) AS names,
    ARRAY_AGG(product_name ORDER BY line_no) AS name_array,
    JSONB_AGG(product_name ORDER BY line_no) AS json_names
FROM demo_sale_lines
GROUP BY sale_id;
```

Cả ba biểu thức đều thể hiện rõ thứ tự theo `line_no`.

Nếu không có `ORDER BY` trong lời gọi, thứ tự có thể thay đổi theo kế hoạch thực thi, chỉ mục hoặc các bước JOIN/sắp xếp trước đó. Việc một truy vấn thử nghiệm thường trả “đúng thứ tự chèn” **không phải một bảo đảm của SQL**.

### 7.2. ORDER BY ngoài cùng không thay thế ORDER BY trong aggregate

```sql
SELECT
    sale_id,
    JSONB_AGG(product_name) AS names
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id DESC;
```

Truy vấn này chỉ đảm bảo nhóm đơn 1002 xuất hiện trước 1001. Nó không bảo đảm phần tử bên trong `names` theo `line_no`. Nếu cần cả hai:

```sql
SELECT
    sale_id,
    JSONB_AGG(product_name ORDER BY line_no) AS names
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id DESC;
```

### 7.3. Thêm khóa phân định khi thứ tự chưa duy nhất

Nếu sắp phần tử theo `product_name` nhưng có hai dòng `Mouse`, thứ tự giữa hai dòng cùng tên không rõ ràng. Nếu JSON chứa `quantity` và các thuộc tính khác, cần thêm khóa phụ:

```sql
SELECT
    sale_id,
    JSONB_AGG(
        JSONB_BUILD_OBJECT('line', line_no, 'product', product_name)
        ORDER BY product_name, line_no
    ) AS items_by_product_name
FROM demo_sale_lines
GROUP BY sale_id;
```

Dùng `ORDER BY product_name, line_no` để tạo thứ tự có thể dự đoán trong mỗi đơn. Với ứng dụng có phân trang hoặc so sánh JSON trả về, điều này giúp tránh thay đổi thứ tự không cần thiết.

### 7.4. Thứ tự chuỗi phụ thuộc collation

Sắp `product_name` là so sánh văn bản. Chữ hoa/thường, dấu tiếng Việt và quy tắc phân loại chuỗi có thể khác nhau theo collation và DBMS. Nếu cần quy tắc hiển thị nhất quán qua nhiều môi trường, cần xác định collation hoặc chuẩn hóa khóa sắp xếp ở một tầng phù hợp. **Thứ tự tự nhiên theo tên** không nhất thiết giống nhau giữa hai cơ sở dữ liệu.

## 8. NULL, tập rỗng và giá trị mặc định

Một API thường muốn:

```json
{"saleId": 1003, "items": []}
```

thay vì:

```json
{"saleId": 1003, "items": null}
```

Nhưng PostgreSQL `ARRAY_AGG` và `JSONB_AGG` **trả SQL `NULL` khi không có dòng đầu vào**. Cần xử lý trường hợp đơn hàng không có chi tiết.

### 8.1. Bẫy LEFT JOIN: một hàng “rỗng” không có nghĩa không có hàng

Ví dụ:

```sql
SELECT
    s.sale_id,
    JSONB_AGG(
        JSONB_BUILD_OBJECT(
            'product', l.product_name,
            'quantity', l.quantity
        )
    ) AS items
FROM demo_sales AS s
LEFT JOIN demo_sale_lines AS l ON l.sale_id = s.sale_id
GROUP BY s.sale_id
ORDER BY s.sale_id;
```

Với đơn `1003` không có chi tiết, `LEFT JOIN` vẫn tạo **một hàng nối với các cột bên `l` là `NULL`**. Biểu thức `JSONB_BUILD_OBJECT(...)` tạo đối tượng có các giá trị JSON `null`, nên `JSONB_AGG` có thể tạo mảng **chứa một đối tượng rỗng về thông tin**, thay vì `[]`.

Một biến thể như `JSONB_AGG(l.product_name)` cũng có thể tạo mảng `[null]` cho đơn không có chi tiết, chứ không phải `[]`. Vì vậy, **chỉ dùng `COALESCE` ở ngoài mà không loại hàng giả do LEFT JOIN sinh ra là chưa đủ**.

### 8.2. FILTER + COALESCE để ra mảng rỗng

PostgreSQL hỗ trợ `FILTER (WHERE ...)` để chỉ đưa các hàng chi tiết thật vào bộ tổng hợp:

```sql
SELECT
    s.sale_id,
    s.customer_name,
    COALESCE(
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'lineNo', l.line_no,
                'product', l.product_name,
                'quantity', l.quantity
            )
            ORDER BY l.line_no
        ) FILTER (WHERE l.line_no IS NOT NULL),
        '[]'::JSONB
    ) AS items
FROM demo_sales AS s
LEFT JOIN demo_sale_lines AS l ON l.sale_id = s.sale_id
GROUP BY s.sale_id, s.customer_name
ORDER BY s.sale_id;
```

Kết quả logic:

| sale_id | items |
|---:|---|
| 1001 | Mảng có 3 đối tượng dòng hàng |
| 1002 | Mảng có 3 đối tượng dòng hàng |
| 1003 | `[]` |

Giải thích:

1. `LEFT JOIN` giữ đơn 1003 dù chưa có dòng hàng.
2. `FILTER (WHERE l.line_no IS NOT NULL)` không đưa hàng giả `NULL` vào `JSONB_AGG`.
3. Khi không có phần tử, `JSONB_AGG` trả SQL `NULL`.
4. `COALESCE(..., '[]'::JSONB)` biến trường hợp đó thành mảng JSON rỗng theo hợp đồng API.

Tương tự với mảng SQL:

```sql
SELECT
    s.sale_id,
    COALESCE(
        ARRAY_AGG(l.product_name ORDER BY l.line_no)
            FILTER (WHERE l.line_no IS NOT NULL),
        ARRAY[]::TEXT[]
    ) AS product_array
FROM demo_sales AS s
LEFT JOIN demo_sale_lines AS l ON l.sale_id = s.sale_id
GROUP BY s.sale_id
ORDER BY s.sale_id;
```

Đối với `STRING_AGG`, thường chỉ cần `COALESCE(STRING_AGG(...), '')` nếu ứng dụng cố ý muốn chuỗi rỗng; tuy nhiên nó không phân biệt “không có hàng” với “danh sách có dữ liệu là chuỗi rỗng”. Chọn giá trị mặc định dựa vào hợp đồng dữ liệu, không phải theo thói quen.

### 8.3. Một cách khác: truy vấn con tương quan

Không nhất thiết dùng `LEFT JOIN` nếu muốn trả đúng một mảng con cho mỗi cha:

```sql
SELECT
    s.sale_id,
    s.customer_name,
    COALESCE(
        (
            SELECT JSONB_AGG(
                JSONB_BUILD_OBJECT(
                    'lineNo', l.line_no,
                    'product', l.product_name,
                    'quantity', l.quantity
                )
                ORDER BY l.line_no
            )
            FROM demo_sale_lines AS l
            WHERE l.sale_id = s.sale_id
        ),
        '[]'::JSONB
    ) AS items
FROM demo_sales AS s
ORDER BY s.sale_id;
```

Với đơn 1003, truy vấn con không có dòng đầu vào, nên tổng hợp trả `NULL` và `COALESCE` tạo `[]`. Cách này cũng tránh tình huống JOIN sang nhiều bảng con làm nhân số dòng trước khi tổng hợp.

Hiệu năng giữa truy vấn con tương quan, `LEFT JOIN`/`GROUP BY` hoặc `LATERAL` phụ thuộc DBMS, chỉ mục, lượng dữ liệu và kế hoạch thực thi. Chọn cách diễn đạt dễ hiểu và đo trên dữ liệu đại diện.

## 9. DISTINCT, lọc riêng từng tập và tổng hợp nhiều biểu thức

### 9.1. Không loại trùng khi bản ghi lặp có ý nghĩa

Trong đơn 1002, hai dòng `Mouse` có thể là hai lần bán riêng, hai chương trình khuyến mãi hoặc hai dòng được nhập khác nhau. `JSONB_AGG(product_name ORDER BY line_no)` giữ cả hai. Nếu dùng `DISTINCT`, kết quả thành một `Mouse`, mất thông tin.

Thay vì:

```sql
JSONB_AGG(DISTINCT product_name)
```

nếu API cần thể hiện **từng dòng**, hãy tổng hợp đối tượng có `line_no`:

```sql
JSONB_AGG(
    JSONB_BUILD_OBJECT('lineNo', line_no, 'product', product_name)
    ORDER BY line_no
)
```

Định nghĩa “trùng” phải dựa trên **khóa nghiệp vụ hoặc khóa dòng**, không chỉ dựa trên tên hiển thị.

### 9.2. Tổng hợp các tập con khác nhau trong cùng truy vấn

Ví dụ cần danh sách tất cả sản phẩm, danh sách riêng các dòng thuộc danh mục `electronics`, và số dòng:

```sql
SELECT
    sale_id,
    COUNT(*) AS line_count,
    STRING_AGG(product_name, ', ' ORDER BY line_no) AS all_names,
    JSONB_AGG(product_name ORDER BY line_no)
        FILTER (WHERE category = 'electronics')
        AS electronics_names
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Đơn 1001 có ba dòng, trong đó hai dòng điện tử; đơn 1002 có ba dòng, trong đó hai dòng Mouse. Nếu một nhóm không có phần tử `electronics`, cột JSON tổng hợp sau lọc sẽ là SQL `NULL`, có thể `COALESCE` về `[]` khi xuất API.

`FILTER` hỗ trợ rõ trên PostgreSQL và một số DBMS khác, nhưng không nên coi nó được mọi phiên bản MySQL/SQL Server hỗ trợ. Với phương ngữ không có `FILTER`, có thể chuyển sang `CASE` bên trong aggregate hoặc tổng hợp trong truy vấn con đã lọc, nhưng cần hiểu cách aggregate xử lý `NULL`.

Ví dụ:

```sql
-- Với STRING_AGG, NULL bị bỏ qua nên CASE có thể lọc giá trị.
STRING_AGG(
    CASE WHEN category = 'electronics' THEN product_name END,
    ', ' ORDER BY line_no
)
```

Với `ARRAY_AGG`/`JSONB_AGG` của PostgreSQL, **không thể mặc định** dùng `CASE ELSE NULL` để loại phần tử vì những aggregate này vẫn có thể tạo phần tử `NULL`. Dùng `FILTER` hoặc lọc đầu vào **trước** khi tổng hợp sẽ đúng mục đích hơn.

## 10. Tổng hợp nhiều bảng con: tránh “nhân bản do JOIN”

Giả sử một đơn có 3 dòng hàng và 2 ghi chú. Nếu nối cả `sale_lines` và `sale_notes` trực tiếp vào bảng đơn, có thể tạo **3 × 2 = 6 hàng trung gian** cho một đơn, gây nhân đôi nội dung trước khi tổng hợp.

Ví dụ cấu trúc dữ liệu:

```text
demo_sales
  ├── demo_sale_lines (1 đơn → nhiều dòng)
  └── demo_sale_notes (1 đơn → nhiều ghi chú)
```

Một truy vấn kiểu:

```sql
-- Ví dụ MINH HỌA BẪY JOIN, demo_sale_notes là bảng giả định.
SELECT
    s.sale_id,
    JSONB_AGG(l.product_name) AS products,
    JSONB_AGG(n.note_text) AS notes
FROM demo_sales AS s
LEFT JOIN demo_sale_lines AS l ON l.sale_id = s.sale_id
LEFT JOIN demo_sale_notes AS n ON n.sale_id = s.sale_id
GROUP BY s.sale_id;
```

có nguy cơ lặp sản phẩm 2 lần và ghi chú 3 lần. `DISTINCT` đôi khi che bớt trùng, nhưng **có thể xóa cả những bản ghi khác nhau nhưng có giá trị hiển thị giống nhau**. Không xem `DISTINCT` là giải pháp mặc định cho “JOIN explosion”.

Thiết kế tốt hơn là **tổng hợp từng bảng con trước**, sau đó nối kết quả “một dòng mỗi cha”:

```sql
-- PostgreSQL; giả sử demo_sale_notes(sale_id, note_id, note_text) tồn tại.
WITH products_per_sale AS (
    SELECT
        sale_id,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'line', line_no,
                'product', product_name
            ) ORDER BY line_no
        ) AS products
    FROM demo_sale_lines
    GROUP BY sale_id
),
notes_per_sale AS (
    SELECT
        sale_id,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'id', note_id,
                'text', note_text
            ) ORDER BY note_id
        ) AS notes
    FROM demo_sale_notes
    GROUP BY sale_id
)
SELECT
    s.sale_id,
    COALESCE(p.products, '[]'::JSONB) AS products,
    COALESCE(n.notes, '[]'::JSONB) AS notes
FROM demo_sales AS s
LEFT JOIN products_per_sale AS p ON p.sale_id = s.sale_id
LEFT JOIN notes_per_sale AS n ON n.sale_id = s.sale_id
ORDER BY s.sale_id;
```

Mỗi CTE tạo tối đa **một hàng cho một `sale_id`**, nên kết quả không nhân chéo hai tập chi tiết. Nếu cần điều kiện lọc cho từng mảng, đặt trong đúng CTE hoặc truy vấn con của tập dữ liệu đó.

## 11. So sánh các hàm theo hệ quản trị

| Hệ quản trị | Tổng hợp chuỗi | Tổng hợp mảng SQL | Tổng hợp JSON thường gặp |
|---|---|---|---|
| **PostgreSQL** | `STRING_AGG(value, delimiter ORDER BY ...)` | `ARRAY_AGG(value ORDER BY ...)` | `JSON_AGG`, `JSONB_AGG`, `JSON_OBJECT_AGG`, `JSONB_OBJECT_AGG`, các biến thể theo phiên bản |
| **MySQL** | `GROUP_CONCAT(... ORDER BY ... SEPARATOR ...)` | Không có `ARRAY_AGG` kiểu `TEXT[]` như PostgreSQL | `JSON_ARRAYAGG`, `JSON_OBJECTAGG` |
| **MariaDB** | `GROUP_CONCAT` | Không có mảng SQL gốc như PostgreSQL | `JSON_ARRAYAGG`, `JSON_OBJECTAGG` ở các phiên bản phù hợp |
| **SQL Server** | `STRING_AGG` và `WITHIN GROUP` cho thứ tự | Không có kiểu mảng SQL gốc tương đương `TEXT[]` | `FOR JSON PATH` để xuất JSON; các hàm tổng hợp JSON chuyên dụng phụ thuộc phiên bản/edition |
| **Oracle Database** | `LISTAGG(... ) WITHIN GROUP (ORDER BY ...)` | Có các collection types (`VARRAY`/nested table) và cơ chế tổng hợp riêng, không giống `TEXT[]` PostgreSQL | `JSON_ARRAYAGG`, `JSON_OBJECTAGG` ở phiên bản hỗ trợ |
| **SQLite** | `GROUP_CONCAT`; `STRING_AGG` là tên thay thế trong các phiên bản hiện đại | Không có cột mảng SQL gốc | `JSON_GROUP_ARRAY`, `JSON_GROUP_OBJECT` qua chức năng JSON |

Bảng nêu **họ hàm thường dùng**, không bảo đảm mỗi chức năng có mặt trên mọi phiên bản. SQL/JSON và aggregate đã phát triển qua các bản phát hành. Đặc biệt SQL Server có các bổ sung JSON thế hệ mới ở những phiên bản/edition gần đây; cần kiểm tra tài liệu đúng môi trường trước khi chọn cách triển khai.

### 11.1. PostgreSQL: cú pháp ORDER BY trong aggregate

```sql
SELECT
    sale_id,
    STRING_AGG(product_name, ', ' ORDER BY line_no) AS names,
    ARRAY_AGG(product_name ORDER BY line_no) AS name_array,
    JSONB_AGG(
        JSONB_BUILD_OBJECT('product', product_name, 'qty', quantity)
        ORDER BY line_no
    ) AS items_json
FROM demo_sale_lines
GROUP BY sale_id;
```

PostgreSQL cho phép đặt `ORDER BY` trực tiếp trong nhiều hàm tổng hợp. Khi cần loại phần tử `NULL`, `FILTER` giúp lọc riêng tập đưa vào hàm. Khi cần `JSONB`, dùng các hàm `JSONB_*` tương ứng thay vì chỉ ép chuỗi JSON thủ công.

### 11.2. MySQL: `GROUP_CONCAT`

MySQL dùng cú pháp điển hình:

```sql
-- MySQL, giả sử sale_lines có cùng các cột như bảng ví dụ.
SELECT
    sale_id,
    GROUP_CONCAT(
        product_name
        ORDER BY line_no
        SEPARATOR ', '
    ) AS product_names
FROM sale_lines
GROUP BY sale_id;
```

Nếu muốn loại tên lặp:

```sql
SELECT sale_id,
       GROUP_CONCAT(
           DISTINCT product_name
           ORDER BY product_name
           SEPARATOR ', '
       ) AS distinct_names
FROM sale_lines
GROUP BY sale_id;
```

**Cảnh báo độ dài:** kết quả `GROUP_CONCAT` chịu giới hạn bởi cấu hình `group_concat_max_len` và các giới hạn liên quan. Khi danh sách rất dài, kết quả có thể **bị cắt ngắn** theo chính sách MySQL, kèm cảnh báo. Không dùng `GROUP_CONCAT` để xuất dữ liệu đầy đủ cho giao dịch quan trọng mà chưa kiểm soát giới hạn và cảnh báo.

Nếu cần JSON:

```sql
-- MySQL hỗ trợ các hàm này trong các phiên bản phù hợp.
SELECT
    sale_id,
    JSON_ARRAYAGG(product_name) AS product_names_json
FROM sale_lines
GROUP BY sale_id;
```

**Không mặc định phần tử trong `JSON_ARRAYAGG` của MySQL có thứ tự xác định** chỉ vì bảng có `line_no` hoặc bên ngoài `SELECT` có `ORDER BY sale_id`. Khả năng sắp xếp trực tiếp trong JSON aggregate khác theo sản phẩm/phiên bản. Khi thứ tự phần tử quan trọng, cần lựa chọn cú pháp/chiến lược được DBMS đang chạy bảo đảm, hoặc xây danh sách có thứ tự ở một tầng được kiểm soát.

### 11.3. MariaDB: phân biệt với MySQL dù tên hàm giống nhau

MariaDB có `GROUP_CONCAT` và ở các phiên bản phù hợp có `JSON_ARRAYAGG`, `JSON_OBJECTAGG`. Một số khả năng như cú pháp `ORDER BY`, `LIMIT` trong JSON aggregation và mức giới hạn có thể khác với MySQL:

```sql
-- MariaDB ở phiên bản hỗ trợ ORDER BY trong JSON_ARRAYAGG.
SELECT
    sale_id,
    JSON_ARRAYAGG(product_name ORDER BY line_no)
        AS names_json
FROM sale_lines
GROUP BY sale_id;
```

Câu trên **không nên sao chép sang MySQL mà không kiểm tra hỗ trợ**. Dù MySQL và MariaDB cùng nguồn gốc, hai sản phẩm đã phân kỳ về chức năng và phiên bản.

Với cả hai, khi xuất nhiều phần tử, kiểm tra giới hạn độ dài, cách báo lỗi/cảnh báo và chính sách xử lý `NULL`.

### 11.4. SQL Server: `STRING_AGG` và thứ tự `WITHIN GROUP`

```sql
-- SQL Server, giả sử dbo.sale_lines có cột tương ứng.
SELECT
    sale_id,
    STRING_AGG(
        CAST(product_name AS NVARCHAR(MAX)),
        N', '
    ) WITHIN GROUP (ORDER BY line_no) AS product_names
FROM dbo.sale_lines
GROUP BY sale_id;
```

SQL Server dùng `WITHIN GROUP (ORDER BY ...)` để chỉ định thứ tự nối; cú pháp aggregate có thứ tự yêu cầu khả năng hỗ trợ/compatibility level phù hợp. `CAST(... AS NVARCHAR(MAX))` trong ví dụ giúp kiểu kết quả hỗ trợ chuỗi dài thay vì vô tình bị giới hạn bởi kiểu văn bản đầu vào có độ dài cố định.

`STRING_AGG` của SQL Server bỏ qua giá trị `NULL` khi nối. Nếu cần nhãn thay thế, có thể dùng `ISNULL(expression, replacement)` hoặc `COALESCE` theo kiểu dữ liệu phù hợp.

Để xuất JSON lồng nhau theo hướng phổ biến trong các phiên bản SQL Server, có thể dùng `FOR JSON PATH`:

```sql
-- SQL Server; bảng dbo.sales và dbo.sale_lines là giả định.
SELECT
    s.sale_id,
    s.customer_name,
    JSON_QUERY(
        (
            SELECT
                l.line_no AS lineNo,
                l.product_name AS product,
                l.quantity AS quantity
            FROM dbo.sale_lines AS l
            WHERE l.sale_id = s.sale_id
            ORDER BY l.line_no
            FOR JSON PATH
        )
    ) AS items
FROM dbo.sales AS s
ORDER BY s.sale_id;
```

`FOR JSON PATH` trả biểu diễn JSON; trong bối cảnh xuất JSON lồng nhau, `JSON_QUERY` thường giúp DBMS hiểu chuỗi đó là JSON thay vì một chuỗi cần escape. Với yêu cầu API trả kết quả là một tài liệu JSON duy nhất, cách tổ chức truy vấn ngoài và `FOR JSON PATH` cần được thiết kế thống nhất. Các hàm `JSON_ARRAYAGG`/`JSON_OBJECTAGG` có trong những môi trường SQL Server mới phù hợp, nhưng cần kiểm tra chính xác phiên bản/edition trước khi dùng.

### 11.5. Oracle Database: `LISTAGG` và `JSON_ARRAYAGG`

Oracle thường dùng `LISTAGG` cho chuỗi:

```sql
-- Oracle, giả sử SALE_LINES có các cột tương ứng.
SELECT
    sale_id,
    LISTAGG(product_name, ', ')
        WITHIN GROUP (ORDER BY line_no) AS product_names
FROM sale_lines
GROUP BY sale_id;
```

`WITHIN GROUP` quy định thứ tự ghép. Với những nhóm có chuỗi kết quả rất dài, Oracle có giới hạn kích thước theo kiểu trả về và cấu hình; `LISTAGG` ở các phiên bản hỗ trợ có cơ chế xử lý **overflow** (báo lỗi hoặc truncate theo lựa chọn). Không bỏ qua điều kiện overflow khi dùng cho dữ liệu lớn.

Oracle hỗ trợ JSON aggregate trên các phiên bản thích hợp:

```sql
-- Oracle: minh họa tổng hợp mảng JSON từ giá trị chuỗi.
SELECT
    sale_id,
    JSON_ARRAYAGG(product_name ORDER BY line_no)
        AS product_names_json
FROM sale_lines
GROUP BY sale_id;
```

`JSON_ARRAYAGG` của Oracle có các tùy chọn riêng về giá trị `NULL`, định dạng trả về và kiểu dữ liệu. Khi JSON có thể rất lớn, có thể cần quy định `RETURNING` với kiểu phù hợp theo phiên bản, thay vì mặc định một giá trị chuỗi ngắn. Oracle còn có các collection types riêng; không coi chúng giống kiểu mảng PostgreSQL một-một.

### 11.6. SQLite: `GROUP_CONCAT`, `JSON_GROUP_ARRAY`, `JSON_GROUP_OBJECT`

```sql
-- SQLite: chỉ minh họa hàm; bảng sale_lines phải được tạo trước.
SELECT
    sale_id,
    GROUP_CONCAT(product_name, ', ') AS product_names,
    JSON_GROUP_ARRAY(product_name) AS product_names_json
FROM sale_lines
GROUP BY sale_id;
```

SQLite hỗ trợ các hàm JSON như `json_group_array` và `json_group_object` trong những bản dựng có chức năng JSON tương ứng. Tên `string_agg(X,Y)` cũng được dùng như tên thay thế cho `group_concat(X,Y)` trong các phiên bản hiện đại.

**Thứ tự phần tử cần được chỉ định theo cú pháp phiên bản hỗ trợ.** SQLite từ 3.44.0 hỗ trợ `ORDER BY` nằm trong lời gọi nhiều aggregate; ví dụ:

```sql
-- SQLite 3.44.0 trở lên.
SELECT
    sale_id,
    GROUP_CONCAT(product_name, ', ' ORDER BY line_no)
        AS names
FROM sale_lines
GROUP BY sale_id;
```

Với SQLite cũ hơn, việc sắp xếp đầu vào qua truy vấn con có thể cần cấu trúc truy vấn cẩn thận và kiểm tra kế hoạch thực thi; không coi `ORDER BY` ngoài truy vấn tổng hợp là quy tắc sắp phần tử. Nếu cần thứ tự mảng chắc chắn trong API, hãy dùng đúng phiên bản/cách làm được SQLite hỗ trợ và thử trong môi trường thực tế.

## 12. Tổng hợp JSON object theo phương ngữ

Dữ liệu gồm các cặp `(key,value)` có thể được đưa vào JSON object. Nhưng cách đặt tên hàm và cú pháp tham số khác nhau:

| DBMS | Hàm/cú pháp tiêu biểu | Chú ý |
|---|---|---|
| PostgreSQL | `JSONB_OBJECT_AGG(key, value)`, `JSON_OBJECT_AGG(key, value)` | Khóa phải không `NULL`; kiểm soát khóa trùng |
| MySQL | `JSON_OBJECTAGG(key, value)` | Khóa `NULL` không hợp lệ; giá trị khóa trùng và thứ tự thực thi có thể ảnh hưởng kết quả |
| MariaDB | `JSON_OBJECTAGG(key, value)` | Phiên bản/biểu diễn JSON và hành vi khóa trùng cần kiểm tra |
| Oracle | `JSON_OBJECTAGG(KEY key_expr VALUE value_expr)` | Tùy chọn xử lý `NULL`, khóa trùng và kiểu trả về |
| SQLite | `JSON_GROUP_OBJECT(key, value)` | Định dạng kết quả và khóa trùng tùy hàm/phiên bản |
| SQL Server | `FOR JSON PATH` hoặc hàm JSON mới theo phiên bản | Không giả định mọi bản có aggregate JSON object cùng tên |

Một ví dụ MySQL:

```sql
SELECT
    sale_id,
    JSON_OBJECTAGG(CAST(line_no AS CHAR), product_name)
        AS product_by_line
FROM sale_lines
GROUP BY sale_id;
```

Khóa `line_no` trong ví dụ được chuyển thành chuỗi. Vì `(sale_id, line_no)` là khóa chính của bảng dòng hàng, trong phạm vi từng đơn không có khóa `line_no` trùng nhau. Nếu dùng `product_name` làm khóa thì đơn 1002 có hai dòng Mouse, dễ gặp hành vi ghi đè/nhập nhằng.

**Đối tượng JSON không phải mảng có thứ tự.** Dù có tùy chọn `ORDER BY` để xác định cách xử lý khi trùng khóa ở một số DBMS, không được suy từ thứ tự xây dựng sang thứ tự hiển thị thuộc tính của JSON object. Khi thứ tự là yêu cầu chính, dùng JSON array có trường sắp xếp tường minh.

## 13. Những khác biệt SQL tiêu chuẩn và phương ngữ

SQL có các ý tưởng chuẩn hóa như `ARRAY_AGG`, `LISTAGG` và SQL/JSON aggregate, nhưng **khả năng triển khai thực tế khác nhau nhiều**. Chỉ dựa vào tên hàm không đủ để gọi một câu lệnh là “portable SQL”.

### 13.1. Phương án gần với chuẩn cho chuỗi: LISTAGG

Cú pháp `LISTAGG(value, delimiter) WITHIN GROUP (ORDER BY key)` được dùng trong Oracle và một số sản phẩm khác:

```sql
SELECT
    sale_id,
    LISTAGG(product_name, ', ')
        WITHIN GROUP (ORDER BY line_no) AS names
FROM sale_lines
GROUP BY sale_id;
```

Trong PostgreSQL, cách thông dụng vẫn là `STRING_AGG(product_name, ', ' ORDER BY line_no)`; trong MySQL/MariaDB là `GROUP_CONCAT(... ORDER BY ... SEPARATOR ...)`; SQL Server dùng `STRING_AGG(...) WITHIN GROUP (ORDER BY ...)`. Vậy khi xây dựng ứng dụng đa DBMS, thường phải có **lớp chọn câu SQL theo dialect** hoặc tổng hợp danh sách ở tầng ứng dụng.

### 13.2. JSON_ARRAYAGG không nhất thiết là JSON_AGG

Một số sản phẩm cung cấp `JSON_ARRAYAGG`; PostgreSQL có `JSON_AGG`/`JSONB_AGG` và các chức năng SQL/JSON mới theo phiên bản. Không tự thay mọi tên hàm bằng một tên chuẩn mà chưa kiểm tra:

- Kiểu dữ liệu JSON trả về là gì?
- Có giữ SQL `NULL` thành JSON `null` không?
- Có tùy chọn bỏ giá trị `NULL` không?
- Có thể sắp phần tử bên trong aggregate bằng `ORDER BY` không?
- Có giới hạn dung lượng hay kiểu trả về mặc định?
- Khi không có đầu vào thì trả `NULL` hay một mảng rỗng theo hợp đồng của hàm?

Ví dụ JSON object cũng có vấn đề **khóa trùng và khóa `NULL`** khác nhau. Khi cần dữ liệu nhất quán giữa nhiều hệ quản trị, có thể tạo ra các hàng có cấu trúc chuẩn ở DB rồi dùng thư viện JSON của ứng dụng để serialize, đặc biệt nếu quy tắc giữa dialects không đồng nhất.

## 14. Độ dài, bộ nhớ và hiệu năng

Tổng hợp nhiều giá trị thành một chuỗi hoặc JSON có thể biến một nhóm nhỏ trong báo cáo thành **một giá trị rất lớn**. Cần tính đến:

- **Số phần tử mỗi nhóm**: một đơn có 5 dòng khác hoàn toàn một người dùng có hàng triệu sự kiện.
- **Độ dài từng phần tử**: mô tả văn bản hoặc JSON nhiều trường có thể lớn.
- **Sắp xếp trong aggregate**: `ORDER BY` có thể cần sắp nhiều phần tử trong mỗi nhóm.
- **Loại trùng**: `DISTINCT` có chi phí so sánh/khử trùng, tùy kế hoạch.
- **Dung lượng kết quả**: cả DBMS, driver và API đều phải xử lý một giá trị lớn.
- **Thời gian truyền**: một mảng JSON lớn có thể chiếm phần đáng kể băng thông của một phản hồi API.
- **Giới hạn hàm**: ví dụ MySQL `group_concat_max_len` và xử lý overflow của Oracle `LISTAGG`.
- **Chỉ mục và JOIN**: cần truy xuất hàng con theo khóa cha và sắp theo `line_no` nhanh; chỉ mục như `(sale_id, line_no)` thường hữu ích nếu phù hợp truy vấn.

Trong ví dụ, `demo_sale_lines` có khóa chính `(sale_id, line_no)`, là cấu trúc chỉ mục hữu ích cho việc lấy các dòng của một đơn theo thứ tự `line_no` ở PostgreSQL. Tuy vậy, việc aggregate có dùng được thứ tự từ chỉ mục hay vẫn sắp xếp riêng phụ thuộc bộ tối ưu và kế hoạch truy vấn. Kiểm tra bằng `EXPLAIN`/`EXPLAIN ANALYZE` trên dữ liệu đại diện thay vì kết luận từ bảng mẫu sáu dòng.

### 14.1. Đừng kéo cả lịch sử vào một giá trị duy nhất

Giả sử một khách hàng có 2 triệu sự kiện. `JSON_AGG` toàn bộ sự kiện của khách trong một dòng có thể gây áp lực bộ nhớ, I/O và response size. Các phương án khác:

1. Trả **danh sách trang** từ bảng sự kiện, không phải một mảng chứa cả lịch sử.
2. Tổng hợp **theo khoảng thời gian** hoặc theo batch có giới hạn.
3. Chỉ đưa các trường cần thiết vào JSON object.
4. Xử lý stream/serialization ở tầng ứng dụng nếu API cần truyền nhiều dữ liệu.
5. Nếu mục đích chỉ là tìm kiếm hoặc thống kê, hãy trả chỉ tiêu tổng hợp thích hợp thay vì toàn bộ chi tiết.

Tổng hợp danh sách có giá trị nhất khi số phần tử mỗi nhóm có giới hạn và hợp đồng kết quả yêu cầu thực sự một collection.

### 14.2. JSON xuất ra không tự bảo đảm bảo mật

JSON object trong SQL không tự lọc dữ liệu nhạy cảm. Nếu truy vấn lấy toàn bộ cột từ bảng con và tổng hợp thành JSON, API có thể vô tình để lộ trường không cần thiết. Chỉ chọn các thuộc tính được phép xuất, áp điều kiện quyền truy cập trước khi tổng hợp và không coi cấu trúc JSON là thay thế cho kiểm soát phân quyền.

## 15. Chọn chuỗi, mảng hay JSON theo tình huống

| Yêu cầu | Kiểu tổng hợp thường phù hợp | Lý do |
|---|---|---|
| Hiển thị một dòng “tên sản phẩm” trên báo cáo đơn giản | Chuỗi bằng `STRING_AGG`/`LISTAGG`/`GROUP_CONCAT` | Gọn, đọc trực tiếp |
| API cần danh sách tên sản phẩm | JSON array | Bảo toàn ranh giới phần tử và escape đúng |
| PostgreSQL cần dùng kết quả trong toán tử/hàm mảng SQL | `ARRAY_AGG` | Có kiểu phần tử đồng nhất, thao tác mảng riêng |
| API cần dòng hàng nhiều trường | JSON array của các object | Mỗi phần tử gồm ID/số thứ tự, giá, số lượng |
| Tra cứu một phần tử theo mã duy nhất | JSON object aggregation | Truy cập theo khóa, không dựa vào thứ tự |
| Bảng chi tiết cần JOIN/lọc/khóa ngoại thường xuyên | Giữ bảng quan hệ, tổng hợp khi truy vấn | Đảm bảo tính toàn vẹn và khả năng truy vấn |
| Nhiều phần tử, cần phân trang | Không gom tất cả; trả theo trang | Giảm bộ nhớ, kích thước response |
| Dữ liệu cần xuất chuẩn giữa nhiều DBMS | Chọn SQL theo dialect hoặc serialize ở ứng dụng | Tránh khác biệt hàm và kiểu trả về |

### Những câu hỏi giúp chọn hàm

**Bước 1 — Kết quả để hiển thị hay để xử lý tiếp?** Nếu chỉ là nhãn trên bảng điều khiển, chuỗi có dấu phân cách có thể đủ. Nếu client phải parse, JSON array đáng tin cậy hơn.

**Bước 2 — Cần duy trì thứ tự không?** Nếu có, chọn một khóa sắp có ý nghĩa (`line_no`, `created_at` và khóa phân định), sau đó dùng cú pháp aggregate hỗ trợ sắp xếp của đúng DBMS.

**Bước 3 — Mục nào là `NULL`?** Quy định rõ phần tử thiếu có bị loại không; API cần `[]` hay `null` khi không có dữ liệu?

**Bước 4 — Các khóa object có thực sự duy nhất?** Nếu không, dùng mảng và đưa khóa vào từng object, hoặc tổng hợp tiền xử lý để tạo khóa duy nhất.

**Bước 5 — Nhóm lớn tới đâu?** Nếu kết quả có nguy cơ rất lớn, cân nhắc phân trang/trả hàng chi tiết thay vì ghép tất cả vào một giá trị.

## 16. Ví dụ hoàn chỉnh: một bản ghi bán hàng với mảng JSON chi tiết

Truy vấn sau kết hợp bảng cha, tổng giá trị và mảng JSON dòng hàng; đơn không có dòng hàng vẫn xuất hiện với `total_amount = 0` và `items = []`. PostgreSQL:

```sql
SELECT
    s.sale_id,
    s.customer_name,
    COALESCE(SUM(l.quantity * l.unit_price), 0)
        AS total_amount,
    COALESCE(
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'lineNo', l.line_no,
                'product', l.product_name,
                'quantity', l.quantity,
                'unitPrice', l.unit_price
            )
            ORDER BY l.line_no
        ) FILTER (WHERE l.line_no IS NOT NULL),
        '[]'::JSONB
    ) AS items
FROM demo_sales AS s
LEFT JOIN demo_sale_lines AS l
  ON l.sale_id = s.sale_id
GROUP BY s.sale_id, s.customer_name
ORDER BY s.sale_id;
```

Kết quả về mặt ý nghĩa:

| sale_id | customer_name | total_amount | items |
|---:|---|---:|---|
| 1001 | An | 1620 | Ba đối tượng dòng hàng, thứ tự 1–3 |
| 1002 | Bình | 950 | Ba đối tượng, trong đó có hai dòng Mouse riêng |
| 1003 | Chi | 0 | `[]` |

Đây là mô hình có thể dùng cho một API “đọc đơn bán”. Lợi ích:

- **Một dòng cho mỗi đơn** nhờ `GROUP BY` theo bảng cha.
- **Thứ tự dòng hàng xác định** nhờ `ORDER BY l.line_no` trong `JSONB_AGG`.
- **Không tạo phần tử giả cho đơn rỗng** nhờ `FILTER`.
- **Kết quả rỗng rõ ngữ nghĩa** nhờ `COALESCE(..., '[]'::JSONB)`.
- **Giá trị số vẫn là số** trong JSON, không bị nối thành chuỗi theo định dạng người dùng.

Khi mở rộng truy vấn để lấy thêm các tập con như giao dịch thanh toán, ghi chú hoặc vận chuyển, cần nhớ nguy cơ nhân hàng do nhiều `LEFT JOIN`. Hãy tổng hợp riêng từng bảng con trước khi ghép chúng vào kết quả cấp đơn.

## 17. Lỗi phổ biến và cách tránh

| Sai lầm | Hệ quả | Cách phù hợp |
|---|---|---|
| Dùng `ORDER BY` ngoài `SELECT` để điều khiển thứ tự phần tử | Chỉ sắp các nhóm, phần tử có thể đảo | Đặt thứ tự trong aggregate hoặc dùng cú pháp tương ứng DBMS |
| Nối chuỗi rồi xem như CSV/JSON có cấu trúc | Dấu phân cách trong dữ liệu phá khả năng parse | Dùng JSON array/serializer có escape rõ ràng |
| Dùng `DISTINCT` để chữa nhân hàng do JOIN | Có thể mất dữ liệu lặp hợp lệ | Tổng hợp từng bảng con trước khi JOIN |
| Dùng `ARRAY_AGG` rồi cho rằng nó bỏ `NULL` như `STRING_AGG` | Mảng có phần tử `NULL` ngoài dự định | Dùng `FILTER` hoặc lọc đầu vào |
| `LEFT JOIN` cha–con rồi `JSON_AGG` không lọc hàng giả | Đơn rỗng thành `[null]` hoặc mảng chứa object null | `FILTER (WHERE child_pk IS NOT NULL)`, kết hợp `COALESCE` |
| Kỳ vọng aggregate không có hàng trả mảng rỗng ở mọi DBMS | API lúc nhận `NULL`, lúc nhận `[]` | Kiểm soát rõ bằng `COALESCE`/cú pháp sản phẩm |
| Dùng tên sản phẩm làm khóa JSON object | Tên trùng làm mất/ghi đè giá trị | Dùng khóa duy nhất hoặc tổng hợp trước |
| Cho rằng mảng SQL và mảng JSON giống nhau | Nhầm kiểu, toán tử và driver | Chọn loại dữ liệu theo mục đích và DBMS |
| Dùng `GROUP_CONCAT` cho danh sách vô hạn | Có thể bị truncate hoặc quá lớn | Kiểm soát giới hạn, phân trang hoặc đổi thiết kế |
| Sao chép `STRING_AGG` PostgreSQL sang MySQL | Lỗi cú pháp | Dùng `GROUP_CONCAT` hoặc lớp SQL theo dialect |
| Sao chép `JSON_ARRAYAGG(... ORDER BY ...)` giữa MySQL và MariaDB | Hỗ trợ/cú pháp khác phiên bản | Kiểm tra tài liệu phiên bản |
| Tổng hợp nhiều tập con sau khi JOIN đồng thời | Nhân chéo hàng trước tổng hợp | CTE/truy vấn con tổng hợp từng tập |
| Dùng JSON object khi cần thứ tự hiển thị | Thứ tự thuộc tính object không đáng tin cậy | Dùng JSON array với `ORDER BY` |
| Trả nhiều cột nhạy cảm trong JSON | API có thể lộ thông tin ngoài nhu cầu | Áp lọc quyền và chỉ chọn trường cần xuất |

## 18. Bài tập tự luyện

### Bài 1. Danh sách tên sản phẩm có thứ tự

**Yêu cầu:** trên PostgreSQL, một dòng cho mỗi `sale_id` với chuỗi tên sản phẩm nối bằng `' | '`, đúng theo `line_no`.

**Đáp án:**

```sql
SELECT
    sale_id,
    STRING_AGG(product_name, ' | ' ORDER BY line_no) AS names
FROM demo_sale_lines
GROUP BY sale_id
ORDER BY sale_id;
```

Đơn 1001: `Mouse | Keyboard | Gift wrap`. Đơn 1002: `SQL Book | Mouse | Mouse`.

### Bài 2. Mảng danh mục không trùng, bỏ NULL

**Yêu cầu:** PostgreSQL, trả mảng các danh mục **khác nhau**, loại `NULL` và sắp theo tên danh mục.

**Đáp án:**

```sql
SELECT
    sale_id,
    ARRAY_AGG(DISTINCT category ORDER BY category)
        FILTER (WHERE category IS NOT NULL) AS categories
FROM demo_sale_lines
GROUP BY sale_id;
```

Đơn 1001: `['electronics']`. Đơn 1002: `['books','electronics']`.

### Bài 3. JSON cho đơn rỗng

**Yêu cầu:** trả cả đơn `1003` dù chưa có dòng hàng, với `items = []`, không phải một phần tử có các trường `null`.

**Đáp án:**

```sql
SELECT
    s.sale_id,
    COALESCE(
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'lineNo', l.line_no,
                'product', l.product_name
            )
            ORDER BY l.line_no
        ) FILTER (WHERE l.line_no IS NOT NULL),
        '[]'::JSONB
    ) AS items
FROM demo_sales s
LEFT JOIN demo_sale_lines l ON l.sale_id = s.sale_id
GROUP BY s.sale_id
ORDER BY s.sale_id;
```

`FILTER` loại hàng giả của `LEFT JOIN`, sau đó `COALESCE` chọn mảng rỗng.

### Bài 4. Chọn aggregate phù hợp

**Tình huống:** API cần trả một danh sách mã sản phẩm để client duyệt từng mã, trong khi mã có thể chứa dấu phẩy.

**Đáp án:** nên dùng JSON array (hoặc mảng SQL nếu client và DBMS cùng hỗ trợ rõ), **không dùng chuỗi ghép dấu phẩy chưa escape**. JSON bảo toàn ranh giới phần tử và cơ chế escape các ký tự đặc biệt.

### Bài 5. Chuyển STRING_AGG sang MySQL

**Yêu cầu:** viết tương đương với `STRING_AGG(product_name, ', ' ORDER BY line_no)` trên MySQL.

**Đáp án:**

```sql
SELECT
    sale_id,
    GROUP_CONCAT(product_name ORDER BY line_no SEPARATOR ', ') AS names
FROM sale_lines
GROUP BY sale_id;
```

Cần xem `group_concat_max_len` nếu danh sách có thể dài, và không suy rằng `GROUP_CONCAT` trả dữ liệu không bị giới hạn.

### Bài 6. Đếm số phần tử đúng trong mảng JSON

**Tình huống:** một đơn có ba dòng hàng, trong đó một dòng có `category = NULL`. Nếu tổng hợp `JSONB_AGG(category ORDER BY line_no)` trong PostgreSQL, có bao nhiêu phần tử?

**Đáp án:** **ba phần tử**, trong đó một phần tử JSON là `null`. `STRING_AGG(category, ', ' ORDER BY line_no)` lại bỏ đầu vào `NULL`. Muốn JSON chỉ chứa danh mục đã biết, cần lọc đầu vào trước hoặc dùng `FILTER`.

### Bài 7. Vì sao JSON_OBJECT_AGG bị mất thông tin?

**Tình huống:** đơn 1002 có hai dòng `Mouse`. Lập JSON object bằng `product_name` làm khóa và `quantity` làm giá trị.

**Đáp án:** khóa `Mouse` bị lặp; tùy DBMS và kiểu JSON, một giá trị có thể ghi đè giá trị kia hoặc xảy ra hành vi khác, nên object không còn biểu diễn **hai dòng riêng biệt**. Dùng JSON array các object với `line_no`, hoặc nhóm theo định danh sản phẩm và cộng số lượng trước nếu muốn báo cáo tổng theo sản phẩm.

### Bài 8. JOIN hai quan hệ một-nhiều

**Tình huống:** một đơn có 3 dòng hàng và 2 ghi chú. Truy vấn `LEFT JOIN` cả hai bảng con rồi `JSONB_AGG` mỗi bên trả bao nhiêu đầu vào nếu không xử lý riêng?

**Đáp án:** tối đa **6 hàng trung gian** cho đơn đó trong ví dụ, khiến thông tin dòng hàng và ghi chú bị lặp. Giải pháp là tổng hợp mỗi bảng con theo `sale_id` trong truy vấn con/CTE trước khi nối với bảng cha.

## Kết luận

Tổng hợp thành chuỗi, mảng hoặc JSON cùng giải quyết bài toán **gom nhiều giá trị thành một kết quả theo nhóm**, nhưng chúng không tương đương:

- **Chuỗi** (`STRING_AGG`, `LISTAGG`, `GROUP_CONCAT`) thuận tiện để hiển thị, nhưng dấu phân cách không tự bảo toàn cấu trúc.
- **Mảng SQL** (`ARRAY_AGG`) giữ các phần tử có kiểu và hỗ trợ thao tác mảng chuyên biệt ở DBMS tương ứng.
- **JSON array/object** (`JSON_AGG`, `JSONB_AGG`, `JSON_ARRAYAGG`, `JSON_OBJECTAGG` và biến thể) phù hợp xuất dữ liệu cấu trúc, nhưng phải quản lý khóa trùng, `NULL`, thứ tự phần tử và kiểu kết quả.

Khi viết truy vấn, hãy chỉ định **nhóm, thứ tự, xử lý giá trị thiếu, chính sách trùng và trường hợp tập rỗng**. Khi chuyển DBMS, phải kiểm tra đúng tên hàm, cú pháp `ORDER BY`/`DISTINCT`, giới hạn dung lượng và kiểu trả về. Nếu kết quả cần chứa nhiều tập con một-nhiều, **tổng hợp từng tập trước khi JOIN** để tránh nhân bản hàng. Những nguyên tắc này giúp truy vấn tổng hợp giữ được tính chính xác và tạo dữ liệu đầu ra đáng tin cậy cho báo cáo, ứng dụng và API.

