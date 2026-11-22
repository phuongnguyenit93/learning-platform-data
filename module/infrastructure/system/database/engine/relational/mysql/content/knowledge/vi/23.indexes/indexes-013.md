# Ảnh hưởng của collation, chuyển kiểu và hàm bao quanh cột

Một cột đã có index nhưng truy vấn vẫn quét nhiều hàng có thể do cách viết điều kiện `WHERE`. MySQL cần so sánh giá trị theo đúng character set, collation và kiểu dữ liệu. Nếu điều kiện buộc engine chuyển đổi từng giá trị của cột hoặc tính hàm trên cột trước khi so sánh, thứ tự trong B-tree có thể không còn dùng trực tiếp cho phép tìm kiếm đó.

Điều kiện có thể dùng index thường được gọi là *sargable predicate*. Mục tiêu là viết phép so sánh sao cho MySQL định vị được vùng cần đọc bằng chính thứ tự của index. Khi cần một quy tắc so sánh khác hoặc một biểu thức tính toán, có thể thiết kế collation của cột, functional index hoặc generated column để index phản ánh đúng cách truy vấn.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích character set và collation ảnh hưởng đến so sánh, sắp xếp và unique index như thế nào.
- Nhận biết chuyển kiểu ngầm định có thể làm điều kiện trên cột mất khả năng dùng index.
- Phân biệt điều kiện lọc trực tiếp trên cột với điều kiện bọc cột bằng hàm hoặc biểu thức.
- Viết lại truy vấn ngày giờ, chuỗi và kiểu số để tận dụng B-tree index.
- Dùng functional index hoặc generated column khi nghiệp vụ thực sự cần tìm kiếm theo biểu thức.
- Kiểm tra lựa chọn index bằng `EXPLAIN` và xác minh kiểu so sánh thực tế.

Các ví dụ giả định MySQL 8.0 trở lên và InnoDB. Kế hoạch tối ưu cụ thể vẫn phụ thuộc dữ liệu, thống kê và phiên bản server.

## 1. Vì sao cách viết WHERE quyết định khả năng dùng index?

B-tree index lưu khóa theo một thứ tự xác định. Khi điều kiện tương thích với thứ tự đó, MySQL có thể tìm vị trí bắt đầu rồi đọc một vùng nhỏ của index. Ví dụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(255) CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs NOT NULL,
    created_at DATETIME NOT NULL,
    KEY ix_customers_email (email),
    KEY ix_customers_created_at (created_at)
) ENGINE = InnoDB;
```

Điều kiện sau so sánh trực tiếp giá trị của cột:

```sql
SELECT customer_id
FROM customers
WHERE email = 'lan@example.com';
```

Nếu kiểu và collation tương thích với index, MySQL có thể dùng phép tra cứu điểm (`ref` hoặc `const`, tùy ngữ cảnh) để tìm email.

Ngược lại, điều kiện sau yêu cầu tính hàm cho từng giá trị:

```sql
SELECT customer_id
FROM customers
WHERE LOWER(email) = 'lan@example.com';
```

Index thông thường trên `email` lưu giá trị `email`, không lưu kết quả `LOWER(email)`. MySQL không thể mặc nhiên coi thứ tự của `email` giống thứ tự của `LOWER(email)`, vì vậy truy vấn có thể phải tính hàm cho nhiều hàng rồi lọc. Có thể khắc phục bằng cách đổi quy tắc so sánh, viết lại điều kiện hoặc tạo index cho biểu thức nếu đó là nhu cầu thường xuyên.

## 2. Character set và collation

**Character set** xác định cách biểu diễn ký tự thành byte. **Collation** xác định cách so sánh và sắp xếp chuỗi thuộc character set đó. Hai chuỗi có thể có byte khác nhau nhưng được xem là bằng nhau theo collation.

Một số hậu tố collation thường gặp:

| Hậu tố | Ý nghĩa |
|---|---|
| `_ci` | Case-insensitive: không phân biệt chữ hoa và chữ thường |
| `_cs` | Case-sensitive: phân biệt chữ hoa và chữ thường |
| `_ai` | Accent-insensitive: không phân biệt dấu/diacritics |
| `_as` | Accent-sensitive: phân biệt dấu/diacritics |
| `_bin` | So sánh theo giá trị mã ký tự nhị phân của character set |

Ví dụ, với collation không phân biệt hoa thường và dấu như `utf8mb4_0900_ai_ci`, các chuỗi như `Lan`, `LAN` và những biến thể dấu có thể được xem là tương đương theo quy tắc collation. Với collation phân biệt hoa thường và dấu như `utf8mb4_0900_as_cs`, phép so sánh chặt chẽ hơn.

### Collation quyết định thứ tự của index

Index trên cột chuỗi được xây dựng theo collation của cột tại thời điểm tạo index. Collation vì vậy ảnh hưởng đến:

- Kết quả của `=`, `<>`, `ORDER BY`, `GROUP BY` và nhiều phép so sánh chuỗi.
- Việc một unique index có cho phép hai chuỗi khác byte nhưng được collation xem là bằng nhau hay không.
- Phạm vi giá trị mà một truy vấn prefix hoặc range có thể tìm trong B-tree.

Ví dụ, nếu `email` dùng collation không phân biệt hoa thường, unique index trên `email` có thể từ chối hai giá trị chỉ khác chữ hoa/chữ thường. Đây là quy tắc dữ liệu, không chỉ là một tùy chọn hiển thị. Hãy chọn collation dựa trên ý nghĩa nghiệp vụ của dữ liệu trước khi tạo unique index.

### PAD SPACE và NO PAD

Collation còn có thuộc tính xử lý dấu cách ở cuối chuỗi. Với collation kiểu `PAD SPACE`, dấu cách cuối có thể bị bỏ qua khi so sánh chuỗi không nhị phân. Với `NO PAD`, dấu cách cuối có ý nghĩa trong so sánh. Ví dụ, `utf8mb4_0900_ai_ci` thuộc nhóm `NO PAD`; nhiều collation cũ có quy tắc `PAD SPACE`.

Khác biệt này có thể làm thay đổi kết quả so sánh và ràng buộc `UNIQUE`. Khi nâng cấp collation hoặc chuyển từ collation cũ sang collation UCA 9.0, hãy kiểm tra dữ liệu có các giá trị khác nhau chỉ bởi dấu cách cuối hoặc cách viết hoa/thường hay không.

### Literal và cột có collation khác nhau

Khi so sánh cột với literal, MySQL áp dụng quy tắc coercibility để xác định collation dùng cho phép so sánh. Thông thường, collation tường minh của cột có độ ưu tiên cao hơn collation của literal, nên:

```sql
SELECT customer_id
FROM customers
WHERE email = 'Lan@example.com';
```

sẽ tuân theo collation của `email`. Collation kết nối (`collation_connection`) có thể ảnh hưởng cách literal được tạo, nhưng không nên giả định nó luôn ghi đè collation của cột.

Nếu hai cột có character set/collation không tương thích, MySQL có thể phải chuyển đổi một phía hoặc báo lỗi `Illegal mix of collations`. Đặc biệt với phép nối hai bảng, nên thiết kế các cột khóa nối cùng character set và collation để phép so sánh rõ ràng và index có thể được sử dụng hiệu quả.

Kiểm tra cấu hình và collation của cột:

```sql
SHOW FULL COLUMNS FROM customers;
SHOW CREATE TABLE customers;

SELECT CHARSET(email),
       COLLATION(email),
       COERCIBILITY(email)
FROM customers
LIMIT 1;

SHOW VARIABLES LIKE 'collation%';
```

### Dùng COLLATE có chủ đích

Có thể chỉ định collation cho một biểu thức:

```sql
SELECT customer_id
FROM customers
WHERE email COLLATE utf8mb4_0900_as_cs =
      'Lan@example.com' COLLATE utf8mb4_0900_as_cs;
```

Điều này thay đổi quy tắc so sánh cho câu truy vấn. Tuy nhiên, nếu index trên `email` được sắp xếp theo collation khác, áp dụng `COLLATE` vào cột có thể khiến index đó không còn phù hợp cho tra cứu điểm hoặc range theo thứ tự mới. MySQL vẫn có thể chọn một đường truy cập khác hoặc quét index, nhưng không nên giả định sẽ có index lookup hiệu quả.

Nếu một quy tắc collation khác được dùng thường xuyên, cân nhắc khai báo collation đó ngay trên cột và tạo index tương ứng, hoặc tạo một generated column/functional index với biểu thức và collation phù hợp. Luôn xác nhận bằng `EXPLAIN`.

Lưu ý: collation có hậu tố `_bin` là một quy tắc so sánh chuỗi; nó không giống việc đổi kiểu cột thành `BINARY` hoặc `VARBINARY`, vốn lưu và so sánh dữ liệu dưới dạng byte.

## 3. Chuyển kiểu ngầm định có thể làm mất index lookup

Khi hai vế so sánh khác kiểu, MySQL có thể chuyển đổi một hoặc cả hai vế theo quy tắc chuyển kiểu. Nếu phép chuyển đổi được thực hiện trên cột có index, thứ tự B-tree ban đầu có thể không còn giúp định vị giá trị.

### So sánh cột chuỗi với số

Giả sử bảng lưu mã sản phẩm dưới dạng chuỗi vì mã có thể chứa số 0 ở đầu hoặc ký tự chữ:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    product_code VARCHAR(30) NOT NULL,
    KEY ix_products_code (product_code)
) ENGINE = InnoDB;
```

Truy vấn sau so sánh `VARCHAR` với một số:

```sql
SELECT product_id
FROM products
WHERE product_code = 123;
```

Trong phép so sánh chuỗi với số, MySQL có thể chuyển giá trị chuỗi sang dạng số để so sánh. Những chuỗi như `'123'`, `'0123'`, `' 123'` hoặc `'123x'` có thể có hành vi chuyển đổi số khác với so sánh chuỗi thuần. Vì nhiều chuỗi có thể chuyển thành cùng một giá trị số, MySQL không thể luôn dùng index chuỗi như một phép tra cứu bằng duy nhất.

Nếu `product_code` là mã dạng chuỗi, hãy truyền tham số dạng chuỗi:

```sql
SELECT product_id
FROM products
WHERE product_code = '123';
```

Điều này giữ nguyên ý nghĩa của mã và giúp index trên `product_code` có thể được dùng trực tiếp. Không chuyển mã định danh thành số chỉ vì phần lớn giá trị hiện tại trông giống số.

### Cột số so sánh với chuỗi

Với cột số, truyền tham số đúng kiểu vẫn là lựa chọn rõ ràng nhất:

```sql
SELECT product_id
FROM products
WHERE product_id = 123;
```

MySQL thường có thể chuyển literal chuỗi như `'123'` sang kiểu số của cột và vẫn dùng index trên cột số, nhưng hành vi cụ thể cần được xác nhận bằng `EXPLAIN`. Đừng dựa vào chuyển kiểu ngầm định cho dữ liệu không hợp lệ hoặc có định dạng không chuẩn.

### Cột ngày giờ và literal

So sánh cột `DATETIME` với một literal ngày giờ hợp lệ thường cho phép MySQL chuyển literal sang kiểu ngày giờ và dùng index:

```sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-02 00:00:00';
```

Với truy vấn từ ứng dụng, nên bind tham số theo kiểu ngày giờ phù hợp và dùng định dạng rõ ràng. Tránh truyền chuỗi ngày không hợp lệ hoặc phụ thuộc vào cách diễn giải định dạng theo `sql_mode`.

Với `TIMESTAMP`, cần tính đến múi giờ session vì MySQL chuyển đổi giữa múi giờ session và UTC khi lưu/đọc. Hãy tạo ranh giới thời gian theo cùng quy ước múi giờ với dữ liệu mà ứng dụng đang truy vấn.

### Chuyển kiểu tường minh

`CAST()` hoặc `CONVERT()` trên tham số thường dễ tối ưu hơn việc bọc cột:

```sql
-- Có thể làm mất khả năng index lookup trên product_code:
SELECT product_id
FROM products
WHERE CAST(product_code AS UNSIGNED) = 123;

-- Giữ phép so sánh chuỗi nếu product_code là mã định danh:
SELECT product_id
FROM products
WHERE product_code = CAST(123 AS CHAR);
```

Chọn cách viết theo ý nghĩa dữ liệu. Nếu mã sản phẩm là chuỗi, không nên ép cột thành số để tìm kiếm. Nếu cột thực sự là số, lưu bằng kiểu số và truyền tham số số.

## 4. Hàm bao quanh cột làm điều kiện khó dùng B-tree

Một index thông thường lưu giá trị của cột theo thứ tự. Khi viết hàm trên cột, MySQL phải đánh giá biểu thức đó trước khi biết giá trị có thỏa điều kiện hay không. Các mẫu thường gặp:

```sql
WHERE LOWER(email) = 'lan@example.com'
WHERE DATE(created_at) = '2026-11-19'
WHERE YEAR(created_at) = 2026
WHERE CAST(customer_id AS CHAR) = '100'
WHERE COALESCE(status, '') = 'ACTIVE'
WHERE amount + 10 > 100
```

Những điều kiện này thường không thể dùng index thường trên cột làm một phép tra cứu range trực tiếp. Có thể viết lại nhiều trường hợp để phép tính nằm ở phía hằng số hoặc chuyển thành khoảng trên cột.

### DATE() và YEAR() trên cột ngày giờ

Giả sử có index:

```sql
CREATE INDEX ix_orders_created_at ON orders (created_at);
```

Điều kiện:

```sql
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-11-19';
```

đang tính `DATE()` trên từng giá trị `created_at`. Hãy chuyển thành khoảng nửa mở:

```sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00';
```

Khoảng `[đầu ngày, đầu ngày kế tiếp)` bao gồm mọi thời điểm trong ngày, không cần đoán phần microsecond cuối ngày và có thể dùng range scan trên index `created_at`.

Tương tự, thay `YEAR(created_at) = 2026` bằng khoảng thời gian:

```sql
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2027-01-01 00:00:00'
```

Nếu cột là `TIMESTAMP`, hãy tính hai mốc theo múi giờ nghiệp vụ rồi bind giá trị tương ứng với session; không tự cộng 24 giờ theo UTC khi ngày địa phương có thay đổi giờ mùa hè.

### LOWER() và UPPER() trên chuỗi

Nếu cột email dùng collation không phân biệt hoa thường phù hợp với quy tắc nghiệp vụ, có thể so sánh trực tiếp:

```sql
SELECT customer_id
FROM customers
WHERE email = 'lan@example.com';
```

Không cần `LOWER(email)` chỉ để làm phép so sánh không phân biệt hoa thường nếu collation của cột đã cung cấp chính xác ngữ nghĩa đó. Nếu nghiệp vụ yêu cầu chuẩn hóa chuỗi riêng, có thể lưu cột chuẩn hóa hoặc tạo functional index.

### COALESCE(), IFNULL() và biểu thức số

Điều kiện:

```sql
WHERE COALESCE(status, '') = 'ACTIVE'
```

có thể viết lại thành:

```sql
WHERE status = 'ACTIVE'
```

Hai điều kiện tương đương nếu `NULL` không được xem là `ACTIVE`. Nếu cần chọn cả `NULL` và `ACTIVE`, hãy viết rõ:

```sql
WHERE status = 'ACTIVE'
   OR status IS NULL
```

Với biểu thức số, thay `amount + 10 > 100` bằng `amount > 90` nếu kiểu dữ liệu và quy tắc làm tròn khiến phép biến đổi tương đương. Tránh biến đổi đại số làm thay đổi ý nghĩa với `NULL`, số thực, overflow hoặc phép chia.

## 5. LIKE, tiền tố và collation

Với B-tree index trên chuỗi, điều kiện tìm theo tiền tố có thể tận dụng index:

```sql
SELECT customer_id
FROM customers
WHERE email LIKE 'lan%';
```

MySQL có thể chuyển prefix thành một khoảng index phù hợp với collation. Collation quyết định cách phân biệt hoa thường và dấu trong phép `LIKE`.

Điều kiện có wildcard ở đầu:

```sql
WHERE email LIKE '%@example.com'
```

thường không thể dùng B-tree index để định vị điểm bắt đầu vì không có tiền tố cố định. Nếu tìm kiếm hậu tố là nhu cầu thường xuyên, cân nhắc lưu một cột đảo chuỗi hoặc dùng giải pháp tìm kiếm phù hợp, nhưng cần xác định rõ ngữ nghĩa và chi phí ghi.

Không thay `LIKE` bằng `LOWER(column) LIKE ...` một cách mặc định. Trước tiên hãy chọn collation phù hợp; nếu phải tìm theo biểu thức chuẩn hóa, hãy cân nhắc index cho chính biểu thức đó.

## 6. Functional index và generated column

Nếu truy vấn theo biểu thức là yêu cầu thường xuyên và không thể viết lại thành điều kiện trên cột gốc, có thể tạo index cho biểu thức.

### Functional index

MySQL hỗ trợ functional key parts từ phiên bản 8.0.13:

```sql
CREATE INDEX ix_customers_lower_email
ON customers ((LOWER(email)));
```

Truy vấn cần dùng biểu thức tương ứng:

```sql
SELECT customer_id
FROM customers
WHERE LOWER(email) = 'lan@example.com';
```

Biểu thức truy vấn cần khớp với biểu thức của functional index để optimizer nhận diện và sử dụng. Kiểu kết quả, collation và cách viết biểu thức đều có ý nghĩa. Hãy kiểm tra `EXPLAIN`; không giả định rằng mọi biến thể tương đương về toán học đều được optimizer ánh xạ vào cùng index.

Functional index tiêu tốn dung lượng và làm tăng chi phí `INSERT`, `UPDATE`, `DELETE` vì giá trị index phải được tính và duy trì. Biểu thức cũng phải tuân theo các giới hạn của functional key part, chẳng hạn không dùng hàm không xác định hoặc tham chiếu dữ liệu ngoài hàng.

### Generated column có index

Có thể biểu diễn biểu thức thành generated column để tên và kiểu dữ liệu rõ ràng hơn:

```sql
ALTER TABLE customers
ADD COLUMN email_normalized VARCHAR(255)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    GENERATED ALWAYS AS (LOWER(email)) STORED,
ADD INDEX ix_customers_email_normalized (email_normalized);
```

Truy vấn theo cột sinh:

```sql
SELECT customer_id
FROM customers
WHERE email_normalized = 'lan@example.com';
```

Generated column có thể là `VIRTUAL` hoặc `STORED`. `VIRTUAL` tính giá trị khi đọc, còn `STORED` lưu giá trị trong hàng; khi index generated column, InnoDB vẫn duy trì dữ liệu index cho biểu thức. Chọn kiểu dựa trên workload và giới hạn của biểu thức.

Không nhất thiết phải tạo generated column nếu collation gốc đã đáp ứng yêu cầu. Trước khi thêm, cân nhắc index mới có tạo ra quy tắc dữ liệu khác với index cũ hay không, đặc biệt khi dùng `UNIQUE`.

## 7. Kiểm tra bằng EXPLAIN

Không thể kết luận index có được dùng chỉ bằng cách nhìn câu SQL. Hãy so sánh kế hoạch của các dạng điều kiện:

```sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE email = 'lan@example.com';

EXPLAIN
SELECT customer_id
FROM customers
WHERE LOWER(email) = 'lan@example.com';
```

Các cột nên xem:

| Cột | Ý nghĩa |
|---|---|
| `type` | Kiểu truy cập, ví dụ `const`, `ref`, `range`, `index`, `ALL` |
| `possible_keys` | Các index optimizer có thể cân nhắc |
| `key` | Index thực tế được chọn |
| `key_len` | Độ dài phần index được sử dụng |
| `rows` | Số hàng ước lượng cần đọc |
| `filtered` | Tỷ lệ hàng ước lượng còn lại sau điều kiện lọc |
| `Extra` | Thông tin bổ sung như `Using where`, `Using index` |

`type = ALL` thường là full table scan; `type = index` có thể là full index scan, không đồng nghĩa với tra cứu hiệu quả. Ngược lại, optimizer có thể chủ động chọn scan khi bảng nhỏ hoặc điều kiện trả về tỷ lệ lớn hàng. Mục tiêu không phải ép mọi truy vấn dùng index mà là giảm tổng chi phí thực thi.

Nếu vừa tạo functional index hoặc generated column, chạy `EXPLAIN` lại với câu truy vấn đúng biểu thức. Khi dữ liệu thay đổi nhiều, cập nhật thống kê bằng `ANALYZE TABLE` nếu cần và đánh giá lại kế hoạch.

## 8. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Index chuỗi không được dùng khi so sánh với số | MySQL phải chuyển giá trị cột chuỗi sang số | Dùng literal/parameter chuỗi hoặc sửa kiểu dữ liệu nếu cột thực sự là số |
| `LOWER(column)` làm truy vấn quét nhiều hàng | Index thường lưu giá trị gốc, không lưu kết quả hàm | Dùng collation phù hợp, functional index hoặc generated column |
| `DATE(datetime_column)` không dùng range index như mong muốn | Hàm được áp dụng lên từng giá trị cột | Viết điều kiện khoảng nửa mở trên cột gốc |
| So sánh hai cột báo lỗi collation | Character set/collation không tương thích | Chuẩn hóa schema hoặc chuyển đổi có chủ đích; kiểm tra index sau thay đổi |
| Unique index từ chối chuỗi nhìn có vẻ khác | Collation xem các giá trị là bằng nhau hoặc quy tắc PAD SPACE | Kiểm tra collation, dấu và khoảng trắng cuối trước khi thay đổi dữ liệu |
| `LIKE '%text'` quét nhiều hàng | Wildcard đứng đầu không tạo được prefix range | Thiết kế cách tìm kiếm khác hoặc dùng search index phù hợp |
| Đã có functional index nhưng optimizer không chọn | Biểu thức khác nhau, kiểu/collation khác hoặc scan rẻ hơn | So sánh biểu thức và đọc `EXPLAIN`, kiểm tra thống kê |

## 9. Quy trình viết lại truy vấn

Khi truy vấn không dùng index như kỳ vọng, thực hiện theo thứ tự:

1. Xác định kiểu dữ liệu, character set, collation và index của cột bằng `SHOW CREATE TABLE`.
2. Kiểm tra kiểu dữ liệu của literal hoặc parameter mà ứng dụng bind.
3. Tìm hàm, phép toán, `CAST`, `CONVERT` hoặc `COLLATE` đang áp dụng lên cột.
4. Xác định collation và quy tắc chuyển kiểu mong muốn theo nghiệp vụ; không đổi ngữ nghĩa chỉ để ép dùng index.
5. Viết lại điều kiện thành phép so sánh trực tiếp hoặc khoảng trên cột nếu tương đương.
6. Nếu biểu thức là yêu cầu cố định, cân nhắc functional index hoặc generated column.
7. Chạy `EXPLAIN`, so sánh `key`, `type`, `rows` và xác minh kết quả trả về vẫn đúng.

## 10. Bài thực hành

Với các bảng `customers(customer_id, email, created_at)` và `products(product_id, product_code)`, giả sử có index trên `email`, `created_at` và `product_code`.

1. So sánh kết quả `email = 'Lan@example.com'` khi cột dùng collation `_ai_ci` và `_as_cs`. Giải thích tác động đến unique index.
2. Chạy `EXPLAIN` cho `product_code = 123` và `product_code = '123'`. Quan sát khác biệt về index lookup và giải thích vì sao mã định danh nên được so sánh như chuỗi.
3. Chạy `EXPLAIN` cho `DATE(created_at) = '2026-11-19'`, sau đó viết lại thành khoảng từ đầu ngày đến đầu ngày kế tiếp. So sánh kế hoạch.
4. Tạo functional index trên `LOWER(email)`, rồi kiểm tra truy vấn `LOWER(email) = 'lan@example.com'`.
5. Thử `LIKE 'lan%'` và `LIKE '%lan'`. Giải thích ảnh hưởng của vị trí wildcard.
6. Kiểm tra `CHARSET()`, `COLLATION()` và `COERCIBILITY()` của một cột chuỗi và literal. Nêu cách xử lý khi hai cột nối có collation khác nhau.

## Ghi nhớ

- Index chuỗi được sắp xếp theo collation của cột; collation ảnh hưởng kết quả so sánh và tính duy nhất.
- Chuyển kiểu ngầm định trên cột có index có thể làm MySQL không dùng được phép tra cứu điểm hoặc range như mong muốn.
- Hàm hoặc biểu thức bọc quanh cột thường làm điều kiện mất tính sargable với index thông thường.
- Ưu tiên so sánh cột trực tiếp với parameter đúng kiểu và đúng ngữ nghĩa.
- Viết điều kiện ngày giờ thành khoảng nửa mở; dùng functional index hoặc generated column khi phải tìm theo biểu thức.
- Luôn xác nhận bằng `EXPLAIN` và kiểm tra kết quả để bảo đảm tối ưu không làm thay đổi ý nghĩa nghiệp vụ.
