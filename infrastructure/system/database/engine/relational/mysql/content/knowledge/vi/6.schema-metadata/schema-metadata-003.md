# Tên đối tượng, backtick và từ khóa dành riêng

Tên database, table, column, index, constraint và alias xuất hiện trong hầu hết câu lệnh SQL. Một tên có thể hợp lệ về mặt ký tự nhưng gây lỗi vì trùng từ khóa; cùng một tên table còn có thể được xử lý khác nhau giữa Windows và Linux do quy tắc phân biệt hoa thường. MySQL dùng dấu backtick để trích dẫn identifier, nhưng việc trích dẫn cần đúng vị trí và không thay thế cho quy ước đặt tên tốt.

Bài học thuộc module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Trong chương **Schema và metadata**, bài này tập trung vào cách đặt tên đối tượng, dùng backtick đúng cách, nhận diện từ khóa dành riêng và kiểm tra metadata để tránh lỗi khi phát triển, migration và triển khai.

## 1. Identifier là gì?

Trong SQL, **identifier** là tên dùng để định danh một đối tượng hoặc thành phần trong câu lệnh. Các loại identifier thường gặp trong MySQL gồm:

| Loại | Ví dụ | Dùng để định danh |
|---|---|---|
| Database / schema | `sales_db` | Một cơ sở dữ liệu. Trong MySQL, `SCHEMA` thường là cách gọi tương đương `DATABASE`. |
| Table | `customers`, `order_items` | Một bảng hoặc view. |
| Column | `customer_id`, `created_at` | Một thuộc tính trong bảng hoặc view. |
| Index | `idx_orders_created_at` | Một cấu trúc hỗ trợ truy cập dữ liệu. |
| Constraint | `fk_orders_customer` | Một ràng buộc như khóa ngoại hoặc CHECK. |
| Alias | `c`, `monthly_total` | Tên tạm dùng trong phạm vi một câu truy vấn. |
| Stored object | `calculate_tax`, `after_order_insert` | Procedure, function, trigger hoặc event. |

Identifier khác với **literal/value**. Trong `WHERE customer_id = 101`, `customer_id` là tên cột còn `101` là giá trị. Trong `WHERE email = 'an@example.com'`, `email` là identifier còn `'an@example.com'` là chuỗi literal.

```sql
SELECT c.customer_id, c.email
FROM sales_db.customers AS c
WHERE c.customer_id = 101;
```

Ở ví dụ trên:

- `sales_db` là tên database.
- `customers` là tên table.
- `c` là alias của table.
- `customer_id` và `email` là tên column.
- `101` là giá trị được so sánh.

Phân biệt identifier và value rất quan trọng khi viết SQL động, dùng prepared statement và xử lý SQL injection.

## 2. Quy tắc đặt tên identifier

### 2.1. Ký tự và giới hạn độ dài

MySQL hỗ trợ identifier không trích dẫn và identifier được trích dẫn. Quy tắc ký tự cụ thể phụ thuộc loại đối tượng và phiên bản, nhưng quy ước an toàn, dễ mang qua nhiều môi trường là:

- Bắt đầu bằng chữ cái ASCII hoặc dấu gạch dưới `_`.
- Dùng chữ cái, chữ số và `_` trong phần còn lại.
- Dùng ASCII không dấu cho tên đối tượng để tránh khác biệt giữa công cụ, filesystem, script triển khai và môi trường terminal.
- Không chứa khoảng trắng, dấu gạch ngang `-`, dấu chấm hoặc ký tự đặc biệt nếu không có lý do rõ ràng.
- Tránh đặt tên trùng từ khóa SQL hoặc tên gây nhầm với hàm và kiểu dữ liệu.

Đa số tên đối tượng phổ biến như database, table, column, index, constraint và routine có giới hạn 64 ký tự. Một số loại tên khác có giới hạn riêng, vì vậy hãy kiểm tra quy định cho đúng loại đối tượng khi đặt tên tự động hoặc sinh schema bằng code.

Các tên sau dễ đọc và thuận tiện cho migration:

```text
customers
order_items
customer_id
created_at
idx_orders_customer_created_at
fk_order_items_order
```

Các tên dưới đây có thể cần trích dẫn hoặc gây khó khăn khi làm việc đa môi trường:

```text
order-items       -- có dấu gạch ngang
customer email    -- có khoảng trắng
select            -- trùng từ khóa dành riêng
TênKháchHàng      -- chữ có dấu, khác biệt công cụ và quy ước
```

Backtick có thể giúp MySQL chấp nhận một số tên khó dùng, nhưng không làm tên đó trở nên dễ bảo trì. Ưu tiên đổi sang tên đơn giản nếu còn quyền thiết kế schema.

### 2.2. Quy ước đặt tên nhất quán

Một quy ước thực tế cho dự án MySQL:

| Thành phần | Quy ước gợi ý | Ví dụ |
|---|---|---|
| Database | `snake_case`, mô tả miền nghiệp vụ | `sales_db` |
| Table | Một quy tắc số ít hoặc số nhiều thống nhất | `customers`, `orders`, `order_items` |
| Column | `snake_case`, thể hiện ý nghĩa | `customer_id`, `created_at` |
| Primary key | `id` hoặc `<entity>_id`, thống nhất toàn dự án | `order_id` |
| Foreign key | Cùng tên với khóa được tham chiếu | `customer_id` |
| Index | Prefix theo mục đích | `idx_orders_customer_created` |
| Unique key | Prefix `uq_` | `uq_customers_email` |
| Foreign key constraint | Prefix `fk_` | `fk_orders_customer` |
| Check constraint | Prefix `chk_` | `chk_order_items_quantity` |

Điều quan trọng nhất là tính nhất quán. Nếu một module dùng `customer_id`, module khác dùng `customerId`, và module thứ ba dùng `cust_no` cho cùng khái niệm, việc join, đọc metadata và sinh code sẽ khó hơn. Hãy thống nhất quy tắc trong schema và migration.

Không nên nhét quá nhiều thông tin vào tên. Ví dụ `idx_orders_customer_created_at_status_total_amount` có thể phản ánh index gồm nhiều cột, nhưng tên quá dài và khó đọc. Chọn tên đủ phân biệt và dễ hiểu; cấu trúc index thật được xem bằng metadata.

## 3. Dấu backtick dùng để làm gì?

### 3.1. Trích dẫn identifier

MySQL dùng dấu backtick `` ` `` để trích dẫn identifier. Dấu này giúp dùng tên có chứa khoảng trắng, dấu gạch ngang hoặc trùng từ khóa dành riêng.

Ví dụ một schema cũ có table tên `order` và column tên `select`:

```sql
CREATE TABLE `order` (
    `order_id` BIGINT UNSIGNED NOT NULL,
    `select`   VARCHAR(100) NOT NULL,
    PRIMARY KEY (`order_id`)
);

INSERT INTO `order` (`order_id`, `select`)
VALUES (1001, 'Đơn hàng đầu tiên');

SELECT `order_id`, `select`
FROM `order`;
```

Không có backtick, `order` và `select` có thể được hiểu là từ khóa trong ngữ cảnh SQL, dẫn đến lỗi cú pháp hoặc diễn giải không như mong muốn.

Backtick bao quanh **tên đối tượng**, không bao quanh giá trị chuỗi. So sánh:

```sql
-- Đúng: identifier dùng backtick, string dùng nháy đơn.
SELECT `customer_id`
FROM `customers`
WHERE `email` = 'an@example.com';

-- Sai mục đích: 'customer_id' là một chuỗi literal, không phải tên cột.
SELECT 'customer_id'
FROM `customers`;
```

Câu lệnh thứ hai vẫn có thể chạy, nhưng nó trả về chuỗi `customer_id` cho mỗi hàng thay vì giá trị trong cột cùng tên.

### 3.2. Trích dẫn tên có dấu cách hoặc ký tự đặc biệt

Backtick cho phép trích dẫn một identifier có ký tự mà dạng không trích dẫn không chấp nhận:

```sql
CREATE TABLE `sales-archive` (
    `row id` BIGINT NOT NULL,
    `net amount` DECIMAL(12, 2) NOT NULL
);

SELECT `row id`, `net amount`
FROM `sales-archive`;
```

Đây là cú pháp hợp lệ, nhưng các tên này thường bất tiện khi viết SQL, ORM mapping, script shell, migration và công cụ BI. Với schema mới, nên chọn `sales_archive`, `row_id` và `net_amount`.

### 3.3. Nếu tên identifier có chứa backtick

Muốn đặt một dấu backtick thực sự bên trong identifier đã trích dẫn, MySQL dùng hai dấu backtick liên tiếp để biểu diễn một dấu backtick trong tên:

```sql
CREATE TABLE `report``archive` (
    `row``id` BIGINT NOT NULL
);
```

Tên table thực tế là `report`archive` (có một dấu backtick ở giữa), còn tên column thực tế là `row`id`. Đây là khả năng của cú pháp trích dẫn, không phải quy ước nên dùng trong schema ứng dụng.

### 3.4. Trích dẫn từng phần của tên đầy đủ

Tên đối tượng có thể được viết theo dạng database, table và column. Khi cần trích dẫn, hãy trích dẫn từng thành phần riêng:

```sql
SELECT `c`.`customer_id`, `c`.`email`
FROM `sales_db`.`customers` AS `c`
WHERE `c`.`customer_id` = 101;
```

Không trích dẫn toàn bộ chuỗi có dấu chấm như thể đó là một tên duy nhất:

```sql
-- Không đúng ý nghĩa qualification:
SELECT * FROM `sales_db.customers`;

-- Đúng:
SELECT * FROM `sales_db`.`customers`;
```

Ở ví dụ sai, MySQL tìm một table có tên literal `sales_db.customers` trong database mặc định, chứ không hiểu `sales_db` là database và `customers` là table.

Nếu database đã được chọn bằng `USE sales_db`, có thể chỉ định table:

```sql
USE `sales_db`;

SELECT `customer_id`, `email`
FROM `customers`;
```

Tên đầy đủ giúp tránh nhầm lẫn khi một server có nhiều database cùng chứa table trùng tên.

## 4. Backtick, nháy đơn và nháy kép

Ba kiểu dấu nháy không thể thay thế tùy tiện cho nhau:

| Cách viết | Ý nghĩa trong MySQL thông thường | Ví dụ |
|---|---|---|
| Backtick `` `...` `` | Trích dẫn identifier | `` `order` ``, `` `customer_id` `` |
| Nháy đơn `'...'` | Chuỗi literal | `'pending'`, `'An'` |
| Nháy kép `"..."` | Thường là chuỗi literal; thay đổi khi bật `ANSI_QUOTES` | `"pending"` |

Khi SQL mode `ANSI_QUOTES` được bật, nháy kép được dùng để trích dẫn identifier và không còn được hiểu là string literal theo cách thông thường. Điều này có thể làm câu SQL cũ thay đổi ý nghĩa giữa các môi trường có SQL mode khác nhau.

Ví dụ:

```sql
-- Cách ổn định, rõ nghĩa trong MySQL:
SELECT `customer_id`
FROM `customers`
WHERE `status` = 'ACTIVE';
```

Với MySQL, hãy dùng backtick cho identifier khi cần trích dẫn và nháy đơn cho string literal. Quy ước này giảm phụ thuộc vào `ANSI_QUOTES`.

## 5. Từ khóa SQL và từ khóa dành riêng

### 5.1. Keyword và reserved keyword

MySQL có các từ khóa được dùng trong cú pháp SQL. Một số từ khóa được đánh dấu là **reserved** (dành riêng), nghĩa là chúng không thể được dùng làm identifier không trích dẫn trong các ngữ cảnh thông thường vì parser cần nhận diện chúng như thành phần cú pháp.

Ví dụ các từ như `SELECT`, `FROM`, `WHERE`, `ORDER`, `GROUP`, `KEY` và `INDEX` có vai trò cú pháp. Nếu đặt table tên `order` hoặc column tên `group`, cần trích dẫn bằng backtick:

```sql
CREATE TABLE `order` (
    `order_id` BIGINT NOT NULL,
    `group`    VARCHAR(50),
    PRIMARY KEY (`order_id`)
);
```

Không phải mọi keyword đều là reserved. Một số từ khóa không dành riêng vẫn có thể được dùng làm identifier không trích dẫn trong một số ngữ cảnh. Tuy nhiên, từ khóa có thể được nâng thành reserved ở phiên bản MySQL mới hơn. Một tên từng chạy được có thể bắt đầu gây lỗi sau khi nâng cấp.

Vì vậy, với schema mới, tránh dùng từ khóa làm tên đối tượng ngay cả khi phiên bản hiện tại cho phép. Nếu phải tương thích với schema cũ, hãy trích dẫn nhất quán và kiểm thử migration trên phiên bản đích.

### 5.2. Tra cứu danh sách keyword trên MySQL 8.0

MySQL 8.0 cung cấp `INFORMATION_SCHEMA.KEYWORDS`, trong đó có thông tin từ khóa và cột `RESERVED` cho biết từ đó có dành riêng hay không:

```sql
SELECT WORD, RESERVED
FROM INFORMATION_SCHEMA.KEYWORDS
WHERE WORD IN ('ORDER', 'GROUP', 'RANK', 'WINDOW', 'KEY')
ORDER BY WORD;
```

Danh sách và trạng thái reserved phụ thuộc phiên bản. Hãy chạy truy vấn trên đúng server mục tiêu thay vì dựa vào một danh sách tìm thấy cho phiên bản khác. Nếu phiên bản đang dùng không cung cấp bảng metadata này, tra cứu tài liệu MySQL tương ứng với phiên bản đó.

Để kiểm tra một từ cụ thể:

```sql
SELECT WORD, RESERVED
FROM INFORMATION_SCHEMA.KEYWORDS
WHERE WORD = UPPER('rank');
```

Nếu từ không xuất hiện hoặc bảng metadata không có trên phiên bản hiện tại, không thể kết luận từ đó chắc chắn được phép dùng; cần đối chiếu tài liệu cú pháp của phiên bản.

### 5.3. Vì sao nâng cấp phiên bản có thể làm tên cũ lỗi?

MySQL bổ sung cú pháp và từ khóa theo thời gian. Một identifier cũ trùng với keyword mới có thể trở nên mơ hồ hoặc không còn hợp lệ nếu không được trích dẫn.

Quy trình nâng cấp nên gồm:

1. Xác định tên database, table, column, routine và alias hiện có.
2. Đối chiếu với danh sách reserved keyword của phiên bản đích.
3. Kiểm tra các câu SQL, view, routine, trigger, event và migration dùng những tên đó.
4. Bổ sung backtick ở đúng vị trí hoặc đổi tên đối tượng theo kế hoạch tương thích.
5. Chạy kiểm thử tích hợp trên phiên bản MySQL đích trước khi nâng cấp production.

Không chỉ kiểm tra tên table. Một column tên `rank` hoặc alias trùng từ khóa cũng có thể làm câu SQL lỗi khi phiên bản thay đổi.

## 6. Phân biệt hoa thường trong tên đối tượng

### 6.1. Tên database và table phụ thuộc hệ điều hành

MySQL lưu database và table trong hệ thống tệp theo cách phụ thuộc nền tảng. Vì vậy, cách so sánh chữ hoa/thường của tên database và table chịu ảnh hưởng bởi hệ điều hành và biến `lower_case_table_names`.

Kiểm tra giá trị hiện tại:

```sql
SELECT @@lower_case_table_names;
```

Ba giá trị có ý nghĩa chính:

| Giá trị | Cách lưu tên | Cách so sánh tên database/table |
|---:|---|---|
| `0` | Lưu theo đúng chữ hoa/thường khai báo | Phân biệt hoa/thường. |
| `1` | Lưu tên ở dạng chữ thường | Không phân biệt hoa/thường. |
| `2` | Lưu theo cách khai báo nhưng chuẩn hóa khi tra cứu | Không phân biệt hoa/thường; cần filesystem không phân biệt hoa/thường. |

Giá trị mặc định phụ thuộc nền tảng và cách khởi tạo data directory. Trên nhiều hệ Unix/Linux, mặc định thường là `0`; Windows thường dùng `1`; macOS thường dùng `2` trên filesystem không phân biệt hoa/thường. Hãy kiểm tra giá trị thực tế thay vì giả định từ tên hệ điều hành.

Ở MySQL 8.0, `lower_case_table_names` được cố định khi khởi tạo data directory và không thể đổi tùy tiện sau khi server đã được khởi tạo. Việc thay đổi không đúng quy trình có thể khiến server không khởi động hoặc không nhận diện đúng dữ liệu. Không dùng việc đổi biến này như một cách sửa nhanh lỗi tên table giữa Windows và Linux.

### 6.2. Tên column và alias

Tên database và table có thể chịu ảnh hưởng của quy tắc filesystem; tên column không phân biệt hoa/thường trong MySQL. Dù vậy, viết tên nhất quán vẫn giúp schema dễ đọc và giảm nhầm lẫn khi chuyển qua ORM hoặc công cụ khác.

Ví dụ nên viết thống nhất:

```sql
SELECT `customer_id`, `created_at`
FROM `orders`;
```

Tránh tạo table cùng tên nhưng khác chữ hoa/thường như `Orders` và `orders`, vì hành vi có thể khác nhau giữa máy lập trình Windows và server Linux. Quy ước dùng chữ thường cho database và table là lựa chọn an toàn, dễ di chuyển.

## 7. Alias và qualification để tránh tên mơ hồ

Khi join nhiều bảng, cùng một column name có thể xuất hiện ở nhiều bảng. Nếu không chỉ rõ nguồn, MySQL có thể báo lỗi column không rõ ràng.

Ví dụ:

```sql
SELECT customer_id, order_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Nếu cả hai bảng đều có `customer_id`, tên không được qualification có thể gây mơ hồ. Cách viết rõ ràng hơn:

```sql
SELECT
    c.customer_id,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Alias ngắn như `c`, `o`, `p` thường thuận tiện cho truy vấn ngắn. Với truy vấn dài hoặc nhiều join, alias có ý nghĩa như `customer`, `sales_order`, `product` có thể dễ đọc hơn.

Alias column cũng giúp tên kết quả rõ ràng:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS order_count,
    SUM(o.total_amount) AS total_revenue
FROM orders AS o
GROUP BY o.customer_id;
```

Alias trong `SELECT` có quy tắc phạm vi riêng; không nên giả định alias có thể được tham chiếu ở mọi mệnh đề. Ví dụ, trong MySQL có thể dùng alias trong `ORDER BY`, `GROUP BY` và `HAVING` ở những ngữ cảnh được hỗ trợ, nhưng không thể dùng alias của select list trong `WHERE` cùng cấp theo cách thông thường vì `WHERE` được xử lý trước khi giá trị select alias được tạo.

## 8. Identifier trong prepared statement và SQL động

### 8.1. Parameter marker chỉ thay thế giá trị

Prepared statement giúp tách SQL khỏi dữ liệu đầu vào:

```sql
PREPARE find_customer FROM
    'SELECT customer_id, email
     FROM customers
     WHERE customer_id = ?';

SET @id = 101;
EXECUTE find_customer USING @id;
DEALLOCATE PREPARE find_customer;
```

Parameter marker `?` đại diện cho giá trị `customer_id`. Nó không đại diện cho tên bảng hoặc tên cột.

Ví dụ sau không làm cho MySQL hiểu `?` là tên table:

```sql
-- Không dùng parameter marker để bind identifier.
SELECT * FROM ?;
```

Nếu muốn chọn table hoặc column động, phần identifier phải được xác định trước khi gửi câu SQL. Đầu vào cần được ánh xạ qua allow-list gồm các tên hợp lệ mà ứng dụng cho phép.

### 8.2. Dùng allow-list cho identifier động trong Java

Ví dụ ứng dụng cho phép sắp xếp đơn hàng theo thời gian tạo hoặc tổng tiền:

```java
String orderBy = switch (sortField) {
    case "created" -> "`created_at`";
    case "amount"  -> "`total_amount`";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String directionSql = switch (direction.toUpperCase(Locale.ROOT)) {
    case "ASC"  -> "ASC";
    case "DESC" -> "DESC";
    default -> throw new IllegalArgumentException("Unsupported sort direction");
};

String sql = "SELECT order_id, created_at, total_amount "
        + "FROM orders ORDER BY " + orderBy + " " + directionSql + " LIMIT ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, limit);
    // Thực thi và đọc kết quả.
}
```

`sortField` và `direction` chỉ được chọn từ những nhánh đã định nghĩa. Giá trị `limit` vẫn được bind bằng parameter marker. Không nối trực tiếp chuỗi do người dùng gửi vào phần identifier hoặc cú pháp SQL.

Backtick không phải biện pháp chống SQL injection nếu identifier vẫn được ghép từ dữ liệu không tin cậy. Một chuỗi được bọc bằng backtick nhưng chứa backtick hoặc cấu trúc bất ngờ vẫn có thể phá vỡ câu lệnh nếu không xử lý đúng. Allow-list là cách phù hợp nhất khi tập identifier được phép là hữu hạn.

### 8.3. Nếu cần tạo identifier từ cấu hình

Nếu hệ thống phải sinh tên table theo cấu hình, hãy kiểm tra tên với quy tắc chặt chẽ trước khi ghép SQL. Một hàm quote identifier cần nhân đôi mọi backtick bên trong tên rồi bọc toàn bộ tên bằng backtick; tuy nhiên, quote đúng cú pháp vẫn không thay thế việc kiểm tra quyền, schema được phép và mục tiêu nghiệp vụ.

Không nhận tên database/table tùy ý từ request HTTP, file upload hoặc message queue rồi đưa thẳng vào SQL. Cấu hình identifier nên đến từ cấu hình nội bộ đã được kiểm soát, hoặc được ánh xạ từ một khóa logic sang tên vật lý được cho phép.

## 9. Kiểm tra tên và metadata trong MySQL

### 9.1. Xem cấu trúc định nghĩa của table

`SHOW CREATE TABLE` trả về câu lệnh định nghĩa table mà MySQL ghi nhận, gồm tên cột, kiểu dữ liệu, index, constraint, engine và các thuộc tính liên quan:

```sql
SHOW CREATE TABLE `sales_db`.`orders`;
```

Đây là cách hữu ích để xác nhận tên thực tế, cách trích dẫn identifier và các constraint sau khi migration chạy.

Các lệnh thường dùng khác:

```sql
SHOW DATABASES;
SHOW TABLES FROM `sales_db`;
SHOW COLUMNS FROM `sales_db`.`orders`;
SHOW INDEX FROM `sales_db`.`orders`;
```

### 9.2. Tìm database và table trong INFORMATION_SCHEMA

`INFORMATION_SCHEMA` cung cấp metadata có cấu trúc để truy vấn bằng SQL:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'sales_db'
ORDER BY TABLE_NAME;
```

Tra cứu column và vị trí:

```sql
SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'sales_db'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Tra cứu index:

```sql
SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'sales_db'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Tên schema/table trong các điều kiện `WHERE` ở đây là **giá trị chuỗi**, vì vậy dùng nháy đơn. Đây là ví dụ trực tiếp để phân biệt cách quote identifier trong câu SQL với cách viết literal trong điều kiện lọc metadata.

### 9.3. Kiểm tra keyword và reserved status

Trên MySQL 8.0:

```sql
SELECT WORD, RESERVED
FROM INFORMATION_SCHEMA.KEYWORDS
WHERE WORD LIKE 'ORDER%'
ORDER BY WORD;
```

Kết quả giúp kiểm tra một từ có phải reserved trong đúng phiên bản server hiện tại. Khi phát triển migration dùng nhiều phiên bản MySQL, cần kiểm tra trên phiên bản thấp nhất và cao nhất mà dự án hỗ trợ.

## 10. Đổi tên đối tượng và tác động đến ứng dụng

Đổi tên table hoặc column có thể ảnh hưởng đến nhiều thành phần hơn câu SQL đang nhìn thấy: view, stored routine, trigger, event, ứng dụng, ORM mapping, báo cáo, migration và job nền.

Ví dụ đổi tên table:

```sql
RENAME TABLE `sales_db`.`order_items_old`
TO `sales_db`.`order_items`;
```

Trước khi đổi tên, hãy tìm các nơi đang tham chiếu đến tên cũ, xác định khả năng tương thích trong thời gian triển khai và kiểm tra các đối tượng phụ thuộc. Với hệ thống cần triển khai không gián đoạn, có thể cần chiến lược nhiều giai đoạn: thêm cấu trúc mới, chuyển ứng dụng, đồng bộ dữ liệu và chỉ xóa cấu trúc cũ sau khi không còn consumer.

Không nên đổi tên chỉ để chuẩn hóa một cách vội vàng trên production. Đầu tiên hãy thống kê metadata và dependency, chuẩn bị migration có thể review, sao lưu phù hợp và kiểm thử rollback hoặc phương án phục hồi.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `You have an error in your SQL syntax` gần tên table | Tên đối tượng trùng reserved keyword hoặc thiếu backtick | Trích dẫn identifier đúng vị trí hoặc đổi tên đối tượng. |
| `Unknown column` dù tên cột nhìn có vẻ đúng | Sai database/table, alias, chính tả hoặc khác chữ hoa/thường ở một thành phần tên | Kiểm tra `DATABASE()`, `SHOW CREATE TABLE`, `INFORMATION_SCHEMA.COLUMNS` và qualification. |
| Chạy được trên Windows nhưng lỗi trên Linux | Tên database/table dùng chữ hoa thường không nhất quán và `lower_case_table_names` khác nhau | Dùng tên chữ thường thống nhất; kiểm tra biến trên từng server. |
| Một câu SQL đổi nghĩa sau khi bật `ANSI_QUOTES` | Nháy kép trước đó được dùng cho string literal | Dùng nháy đơn cho chuỗi và backtick cho identifier. |
| Prepared statement không bind được tên column | Parameter marker chỉ đại diện cho value | Dùng allow-list identifier và ghép phần cấu trúc đã được kiểm soát. |
| Migration lỗi sau khi nâng MySQL | Identifier cũ trùng reserved keyword mới hoặc cú pháp thay đổi | Kiểm tra keyword của phiên bản đích và thử migration trước khi nâng cấp. |
| `Table ... doesn't exist` dù tên có vẻ đúng | Database mặc định không đúng, tên table khác hoa thường hoặc object chưa được tạo | Dùng tên đầy đủ `database.table` và kiểm tra metadata. |

Khi xử lý lỗi tên đối tượng, hãy xác nhận server đang kết nối, database mặc định, tên chính xác trong metadata và phiên bản MySQL trước khi sửa schema.

## 12. Bài tập thực hành

### Bài tập 1: Phân biệt identifier và literal

Tạo table `customers` có các cột `customer_id` và `email`. Chạy:

```sql
SELECT customer_id FROM customers;
SELECT 'customer_id' FROM customers;
```

**Yêu cầu:** giải thích sự khác nhau giữa kết quả hai câu lệnh và xác định phần nào là identifier, phần nào là string literal.

### Bài tập 2: Dùng backtick với reserved keyword

Tạo một table thử nghiệm có tên `order` và column tên `select`. Truy vấn dữ liệu bằng backtick. Sau đó thử bỏ backtick và ghi lại lỗi.

**Yêu cầu:** giải thích vì sao backtick giúp parser nhận diện tên đối tượng.

### Bài tập 3: Kiểm tra keyword theo phiên bản

Trên MySQL 8.0, truy vấn `INFORMATION_SCHEMA.KEYWORDS` cho các từ `ORDER`, `GROUP`, `RANK` và `WINDOW`.

**Yêu cầu:** ghi lại cột `RESERVED` và giải thích vì sao không nên dựa vào kết quả của một phiên bản khác.

### Bài tập 4: Qualification và alias

Join `customers` với `orders`, cả hai đều có `customer_id`. Viết một truy vấn có alias và qualification rõ ràng cho từng column.

**Yêu cầu:** thử bỏ qualification ở một cột trùng tên và quan sát lỗi hoặc sự mơ hồ.

### Bài tập 5: Kiểm tra case sensitivity

Chạy `SELECT @@lower_case_table_names;` trên môi trường phát triển và môi trường kiểm thử. Tạo một table với tên chữ thường và truy vấn bằng biến thể chữ hoa/thường phù hợp với môi trường.

**Yêu cầu:** giải thích vì sao quy ước tên table chữ thường giúp migration dễ di chuyển giữa Windows và Linux.

### Bài tập 6: SQL động an toàn

Viết một phương thức Java cho phép sắp xếp đơn hàng theo `created_at` hoặc `total_amount`, chiều tăng hoặc giảm. Giá trị lọc và `LIMIT` phải được bind bằng `PreparedStatement`.

**Yêu cầu:** dùng allow-list cho identifier và direction; giải thích vì sao không thể bind tên column bằng `?`.

## 13. Checklist đặt tên schema

Trước khi tạo hoặc review một schema, hãy kiểm tra:

- [ ] Tên database, table, column và index mô tả đúng ý nghĩa nghiệp vụ.
- [ ] Quy ước `snake_case`, số ít/số nhiều và tên khóa được áp dụng thống nhất.
- [ ] Tên đối tượng tránh reserved keyword và tên dễ nhầm với cú pháp SQL.
- [ ] Tên không cần khoảng trắng, dấu gạch ngang hoặc ký tự đặc biệt.
- [ ] Độ dài identifier nằm trong giới hạn của loại đối tượng.
- [ ] Database và table dùng chữ thường nhất quán để tránh khác biệt filesystem.
- [ ] Identifier được quote bằng backtick khi cần; string literal dùng nháy đơn.
- [ ] Từng thành phần của tên đầy đủ được quote riêng (`database`.`table`.`column`).
- [ ] SQL động dùng allow-list cho identifier; giá trị dữ liệu được bind bằng prepared statement.
- [ ] Migration và câu SQL được kiểm tra trên đúng phiên bản MySQL mục tiêu.

## 14. Ghi nhớ

Identifier là tên đối tượng; literal là giá trị dữ liệu. MySQL dùng backtick để trích dẫn identifier, trong khi nháy đơn dùng cho chuỗi. Keyword và reserved keyword có thể thay đổi theo phiên bản; vì vậy schema mới nên tránh dùng từ khóa làm tên đối tượng. Tên database và table còn chịu ảnh hưởng của `lower_case_table_names` và filesystem, nên quy ước chữ thường thống nhất giúp triển khai đa nền tảng an toàn hơn.

Khi viết SQL, hãy qualification rõ tên bảng và cột, dùng alias dễ hiểu, kiểm tra metadata bằng `SHOW CREATE TABLE` hoặc `INFORMATION_SCHEMA`, và chỉ tạo SQL động từ identifier đã được cho phép. Những thói quen này giảm lỗi cú pháp, tránh nhầm lẫn giữa đối tượng và dữ liệu, đồng thời giúp schema bền vững khi ứng dụng và phiên bản MySQL phát triển.
