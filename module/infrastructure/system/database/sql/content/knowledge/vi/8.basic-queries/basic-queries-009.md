# Hiển thị nhãn cột và định dạng kết quả ở lớp phù hợp

## 1. Đặt tên cột khác với định dạng giá trị

Một câu truy vấn `SELECT` có thể trả về giá, ngày tháng, số lượng và các thông tin nghiệp vụ. Người dùng cuối thường muốn nhìn thấy **“Tên sản phẩm”**, **“Đơn giá”**, **“Ngày nhập kho”** thay vì các tên kỹ thuật `product_name`, `unit_price`, `stocked_on`; đồng thời muốn thấy `890.000 ₫` thay vì `890000.00` hay `01/11/2026` thay vì `2026-11-01`.

Hai yêu cầu này cần được phân biệt:

1. **Nhãn cột (column label):** tên xuất hiện ở đầu cột kết quả, thường được đặt trong SQL bằng bí danh `AS`. Đây là **metadata của cột kết quả**.
2. **Định dạng giá trị (value formatting):** cách một giá trị được trình bày như chuỗi có dấu phân cách hàng nghìn, ký hiệu tiền tệ, định dạng ngày, màu sắc hoặc văn bản theo ngôn ngữ. Đây chủ yếu là trách nhiệm của **lớp trình bày** (UI, báo cáo, xuất file).

Ví dụ:

~~~sql
SELECT
    product_name AS "Tên sản phẩm",
    unit_price AS "Đơn giá (VND)"
FROM products;
~~~

Nếu hệ SQL hỗ trợ định danh có dấu tiếng Việt và dấu ngoặc kép theo chuẩn, kết quả mang tên cột dễ đọc; nhưng `unit_price` **vẫn là kiểu số**. Chỉ thay nhãn không tự thêm dấu phân tách, ký hiệu `₫` hoặc chuyển số sang chuỗi.

Phân chia trách nhiệm hợp lý giúp:

- Bảo toàn khả năng **tính toán, so sánh, tổng hợp và sắp xếp theo giá trị thực**.
- Hỗ trợ nhiều ngôn ngữ và quy ước vùng (`vi-VN`, `en-US`, …) mà không cần viết lại SQL.
- Tạo giao diện API ổn định để các ứng dụng đọc dữ liệu có kiểu xác định.
- Hạn chế logic trình bày bị lặp hoặc gắn cứng vào cơ sở dữ liệu.

Bài học này tập trung vào **nhãn cột trong `SELECT`, kiểu của giá trị kết quả, và lựa chọn lớp phù hợp để định dạng đầu ra**.

## 2. Dữ liệu mẫu xuyên suốt

Các câu SQL dùng cú pháp cơ bản, với typed date literal như PostgreSQL và SQL tiêu chuẩn. Một số hệ quản trị (DBMS) có cách ghi literal ngày hoặc khai báo kiểu khác; phần về tính khả chuyển sẽ nêu những điểm cần điều chỉnh.

~~~sql
CREATE TABLE products (
    product_id     INTEGER PRIMARY KEY,
    product_name   VARCHAR(100) NOT NULL,
    unit_price     DECIMAL(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    stocked_on     DATE NOT NULL,
    category_code  VARCHAR(30) NOT NULL,
    note           VARCHAR(100)
);

INSERT INTO products (
    product_id, product_name, unit_price, stock_quantity,
    stocked_on, category_code, note
)
VALUES
    (101, 'Sổ tay',  45000.00, 12, DATE '2026-10-15', 'STATIONERY', NULL),
    (102, 'Bàn phím', 890000.00, 3, DATE '2026-11-01', 'ELECTRONICS', 'Bảo hành 12 tháng'),
    (103, 'Chuột',   255000.00, 0, DATE '2026-09-30', 'ELECTRONICS', NULL),
    (104, 'Cáp USB', 120000.00, 8, DATE '2026-11-03', 'ELECTRONICS', 'USB-C');
~~~

Dữ liệu này có ba kiểu cần chú ý:

- `unit_price` dùng `DECIMAL(12, 2)`: giá trị số chính xác theo số chữ số thập phân khai báo, phù hợp cho ví dụ về tiền.
- `stocked_on` dùng `DATE`: biểu diễn **ngày lịch**; bản thân nó không mang giờ hoặc múi giờ.
- `note` cho phép `NULL`: thiếu ghi chú khác với một chuỗi ghi chú cụ thể.

Truy vấn nền tảng:

~~~sql
SELECT
    product_id,
    product_name,
    unit_price,
    stock_quantity,
    stocked_on,
    category_code,
    note
FROM products
ORDER BY product_id;
~~~

Kết quả (biểu diễn các ô thiếu bằng chữ `NULL` cho dễ đọc):

| product_id | product_name | unit_price | stock_quantity | stocked_on | category_code | note |
| ---: | --- | ---: | ---: | --- | --- | --- |
| 101 | Sổ tay | 45000.00 | 12 | 2026-10-15 | STATIONERY | NULL |
| 102 | Bàn phím | 890000.00 | 3 | 2026-11-01 | ELECTRONICS | Bảo hành 12 tháng |
| 103 | Chuột | 255000.00 | 0 | 2026-09-30 | ELECTRONICS | NULL |
| 104 | Cáp USB | 120000.00 | 8 | 2026-11-03 | ELECTRONICS | USB-C |

Thứ tự hàng được bảo đảm bởi `ORDER BY product_id`, không phải vì cách bảng lưu các hàng. Cách SQL client hiển thị số, ngày và `NULL` có thể khác bảng minh họa; chúng vẫn là các giá trị có kiểu tương ứng trong kết quả.

## 3. Đặt nhãn cột bằng AS

### 3.1. Cú pháp và ý nghĩa của alias

Trong danh sách `SELECT`, dùng `AS` để đặt bí danh cho cột hoặc biểu thức:

~~~sql
SELECT
    product_id AS id,
    product_name AS name,
    unit_price AS price
FROM products
ORDER BY product_id;
~~~

| id | name | price |
| ---: | --- | ---: |
| 101 | Sổ tay | 45000.00 |
| 102 | Bàn phím | 890000.00 |
| 103 | Chuột | 255000.00 |
| 104 | Cáp USB | 120000.00 |

`id`, `name` và `price` là **nhãn cột của truy vấn**. Bảng `products` vẫn có tên cột gốc là `product_id`, `product_name` và `unit_price`. Bí danh không sửa định nghĩa bảng và không tạo cột mới trong cơ sở dữ liệu.

Nhiều hệ SQL cho phép bỏ `AS` ở vị trí này:

~~~sql
SELECT product_name name
FROM products;
~~~

Dù vậy, `AS` thường rõ nghĩa và dễ đọc hơn, nhất là khi có biểu thức phức tạp hoặc tên alias gần giống từ khóa.

### 3.2. Đặt nhãn cho cột được tính từ biểu thức

Danh sách `SELECT` có thể chứa biểu thức; nên đặt alias rõ ràng để consumer không phải dùng tên biểu thức do DBMS tự sinh:

~~~sql
SELECT
    product_id,
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM products
ORDER BY product_id;
~~~

| product_id | product_name | inventory_value |
| ---: | --- | ---: |
| 101 | Sổ tay | 540000.00 |
| 102 | Bàn phím | 2670000.00 |
| 103 | Chuột | 0.00 |
| 104 | Cáp USB | 960000.00 |

`inventory_value` vẫn là **giá trị số**, vì biểu thức đầu vào dùng phép nhân số học. Đây là một phép biến đổi có ý nghĩa nghiệp vụ có thể thực hiện hợp lý trong SQL. Việc hiển thị thành `2.670.000 ₫` ở màn hình là bước trình bày riêng.

Nếu chỉ viết `SELECT unit_price * stock_quantity FROM products`, nhiều DBMS đặt tên cột kết quả theo quy tắc riêng như biểu thức nguồn hoặc một tên tự tạo. Alias giúp đầu ra dễ truy cập và ổn định hơn.

### 3.3. Nhãn thân thiện để xem trực tiếp và tên ổn định để máy đọc

Khi chạy báo cáo thủ công cho người Việt, có thể sử dụng nhãn có dấu và khoảng trắng:

~~~sql
SELECT
    product_name AS "Tên sản phẩm",
    unit_price AS "Đơn giá",
    stocked_on AS "Ngày nhập kho"
FROM products
ORDER BY product_id;
~~~

Dấu ngoặc kép bao quanh **định danh** theo SQL tiêu chuẩn và PostgreSQL. Chúng không phải dấu nháy đơn của literal chuỗi. Các DBMS như MySQL và SQL Server có cú pháp trích dẫn định danh hoặc cấu hình khác nhau.

Đối với SQL dùng trong ứng dụng, API, ETL hoặc một view được nhiều hệ thống tham chiếu, nhãn kỹ thuật ổn định thường phù hợp hơn:

~~~sql
SELECT
    product_id,
    product_name,
    unit_price,
    stocked_on
FROM products
ORDER BY product_id;
~~~

Sau đó ứng dụng ánh xạ:

| Tên dữ liệu ổn định | Nhãn tiếng Việt trên màn hình | Nhãn tiếng Anh trên màn hình |
| --- | --- | --- |
| `product_name` | Tên sản phẩm | Product name |
| `unit_price` | Đơn giá | Unit price |
| `stocked_on` | Ngày nhập kho | Stocked on |
| `stock_quantity` | Số lượng tồn | Stock quantity |

Một thay đổi ngôn ngữ của màn hình không đòi hỏi thay tên cột trong database hoặc thay hợp đồng dữ liệu gửi từ server.

### 3.4. Phạm vi sử dụng alias

`ORDER BY` thường có thể dùng alias đã đặt trong `SELECT`:

~~~sql
SELECT
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM products
ORDER BY inventory_value DESC, product_name;
~~~

Nhưng trong SQL thông dụng, alias đó **không khả dụng ngay trong `WHERE` cùng cấp truy vấn**:

~~~sql
-- Không di động, nhiều DBMS sẽ báo lỗi:
SELECT
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM products
WHERE inventory_value > 1000000;
~~~

Để lọc, có thể lặp lại biểu thức:

~~~sql
SELECT
    product_name,
    unit_price * stock_quantity AS inventory_value
FROM products
WHERE unit_price * stock_quantity > 1000000
ORDER BY inventory_value DESC;
~~~

Hoặc tính ở một truy vấn con/CTE rồi lọc ở cấp bên ngoài. Phạm vi alias tại `GROUP BY` và `HAVING` cũng khác giữa các hệ; không nên suy ra mọi mệnh đề đều dùng alias theo một quy tắc.

## 4. Kết quả SQL có nhãn và có kiểu dữ liệu

Một result set không chỉ gồm các chuỗi được hiển thị. Nó còn chứa **metadata cột**: số lượng cột, nhãn, kiểu dữ liệu và các thông tin khác mà driver cung cấp. Ví dụ:

~~~sql
SELECT
    product_name AS name,
    unit_price AS price,
    stocked_on AS imported_on,
    unit_price * stock_quantity AS stock_value
FROM products
ORDER BY product_id;
~~~

Nhãn đầu ra là `name`, `price`, `imported_on`, `stock_value`. Về kiểu:

| Cột kết quả | Ý nghĩa | Kiểu giá trị cần bảo toàn |
| --- | --- | --- |
| `name` | Tên sản phẩm | Chuỗi |
| `price` | Đơn giá | Giá trị số thập phân |
| `imported_on` | Ngày nhập kho | Ngày lịch |
| `stock_value` | Giá trị hàng tồn | Giá trị số được tính |
 
Đổi alias từ `unit_price` sang `price` **không làm kiểu số biến thành chuỗi**. Ngược lại, một hàm định dạng trả về văn bản có thể làm mất kiểu số/ngày ở đầu ra:

~~~sql
-- Minh họa PostgreSQL: TO_CHAR trả văn bản đã định dạng.
SELECT
    product_name,
    TO_CHAR(stocked_on, 'DD/MM/YYYY') AS stocked_on_text
FROM products
ORDER BY product_id;
~~~

Ở đây `stocked_on_text` là văn bản (ví dụ `01/11/2026`), khác với cột `stocked_on` gốc có kiểu `DATE`. Tên alias có chữ `date` hay `text` không quyết định kiểu; **biểu thức** mới quyết định kiểu dữ liệu kết quả.

Điều này ảnh hưởng trực tiếp đến khả năng lọc, sắp xếp, tính toán, chuyển múi giờ và ánh xạ về các kiểu trong Java hoặc ứng dụng web.

## 5. Nên định dạng ở lớp nào?

Cách phân chia phổ biến:

~~~text
             CƠ SỞ DỮ LIỆU
    products.unit_price: DECIMAL(12,2)
    products.stocked_on: DATE
                   |
                   v
              SQL / VIEW
      SELECT cột cần thiết, biểu thức
      nghiệp vụ, alias ổn định
                   |
                   v
           SERVICE / API / DTO
      Giá trị có kiểu, mã danh mục,
      quy tắc nghiệp vụ, timezone
                   |
                   v
          UI / BÁO CÁO / EXPORT
      Nhãn theo ngôn ngữ, định dạng
      tiền, ngày, NULL, đơn vị, màu
                   |
                   v
         Người dùng đọc kết quả
~~~

| Lớp | Nên chịu trách nhiệm | Ví dụ |
| --- | --- | --- |
| Schema/database | Lưu dữ liệu với kiểu, ràng buộc và ý nghĩa thống nhất | `unit_price DECIMAL(12,2)`, `stocked_on DATE` |
| SQL truy vấn | Chọn cột, lọc, nối, tổng hợp, tạo giá trị tính toán, đặt alias | `unit_price * stock_quantity AS inventory_value` |
| Service / API | Xác định dữ liệu trả về, mapping DTO, đơn vị tiền, quy tắc nghiệp vụ và hợp đồng với client | `unitPrice`, `currencyCode = "VND"` |
| UI / báo cáo | Đổi nhãn theo ngôn ngữ; định dạng tiền, ngày, tỷ lệ, đơn vị; xử lý thông báo thiếu dữ liệu | “Đơn giá”, “890.000 ₫”, “01/11/2026” |
| Luồng export | Định dạng phù hợp **đích đến**: file cho người xem hoặc dữ liệu máy đọc | Excel có ô số và định dạng tiền; CSV báo cáo có tiêu đề theo locale |

Cách chia trên là **nguyên tắc thiết kế**, không phải lệnh cấm sử dụng hàm định dạng trong SQL. Một truy vấn báo cáo cố định, đầu ra chỉ để người xem hoặc một file xuất theo đặc tả, có thể định dạng ngay tại SQL khi quy ước đã rõ. Điều cần tránh là trộn dữ liệu nguồn với văn bản trình bày trong một giao diện dùng chung cho nhiều mục đích.

## 6. Định dạng số và tiền tệ

### 6.1. Giữ giá trị số để còn tính toán chính xác

Truy vấn:

~~~sql
SELECT
    product_name,
    unit_price,
    stock_quantity,
    unit_price * stock_quantity AS inventory_value
FROM products
ORDER BY unit_price DESC;
~~~

Nó trả giá trị số có thể cộng, lọc và sắp xếp:

~~~sql
SELECT
    SUM(unit_price * stock_quantity) AS total_inventory_value
FROM products;
-- 4.170.000,00 theo giá trị số; cách client hiển thị có thể khác.
~~~

Tổng trên là **4.170.000** (540.000 + 2.670.000 + 0 + 960.000); bản chất kết quả vẫn là số, không phải chuỗi có dấu chấm phân cách.

Một lời gọi như:

~~~sql
-- Không nên dùng cho luồng tính toán tiếp nếu đây là bước định dạng:
SELECT CAST(unit_price AS VARCHAR(32)) AS unit_price_text
FROM products;
~~~

đã chuyển giá sang **chuỗi ký tự**. Nếu sắp xếp `ORDER BY unit_price_text` thì thứ tự thường là thứ tự từ điển của chuỗi, không phải thứ tự số.

Chẳng hạn `'120000.00'` có thể được xếp trước `'45000.00'` khi so sánh như văn bản, dù `120000 > 45000`. Vì vậy muốn sắp theo giá, dùng:

~~~sql
SELECT product_name, unit_price
FROM products
ORDER BY unit_price ASC, product_id ASC;
~~~

Bộ lọc cũng phải dùng cột số:

~~~sql
SELECT product_name, unit_price
FROM products
WHERE unit_price >= 200000
ORDER BY unit_price DESC;
~~~

Đừng chuyển giá thành chuỗi trước rồi áp dụng `>` hoặc `<` trên chuỗi.

### 6.2. Đơn vị tiền và locale thuộc thông tin ngữ cảnh

Một giá `890000.00` chưa đủ để biết cần in `890.000 ₫` hay `$890,000.00`. Cần biết ít nhất:

- **Mã tiền tệ**, thường là mã ISO 4217 như `VND`, `USD`.
- **Locale của người xem**, ví dụ `vi-VN` hoặc `en-US`.
- **Quy tắc làm tròn**, số chữ số thập phân và đơn vị tiền nhỏ nhất mà nghiệp vụ chấp nhận.

Nếu tất cả giá đều là VND, hợp đồng API hoặc cấu hình miền nghiệp vụ cần nói rõ điều đó. Với hệ đa tiền tệ, nên có `currency_code` đi cùng số tiền để không đánh mất đơn vị.

Trên Java, có thể dùng `NumberFormat` để hiển thị theo locale:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("vi-VN");
NumberFormat currencyFormatter = NumberFormat.getCurrencyInstance(locale);
currencyFormatter.setCurrency(Currency.getInstance("VND"));

BigDecimal price = new BigDecimal("890000.00");
String label = currencyFormatter.format(price);

// Ví dụ cách hiển thị theo locale:
// "890.000 ₫" (ký hiệu/khoảng trắng có thể tùy môi trường).
~~~

Giá trị `price` vẫn là `BigDecimal`; `label` mới là chuỗi dành cho trình bày. Phần lớn phép tính tiền ở tầng nghiệp vụ nên tiếp tục dùng kiểu số chính xác như `BigDecimal`, không lấy chuỗi `label` để làm phép toán ngược.

Trong giao diện JavaScript:

~~~javascript
const formatter = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND"
});

const displayPrice = formatter.format(890000);
// Ví dụ: "890.000 ₫"
~~~

Ví dụ JavaScript sử dụng số nằm trong miền biểu diễn an toàn của `Number` để minh họa phần **hiển thị**. Với giá trị tiền lớn hoặc cần chính xác thập phân tuyệt đối, không tự động chuyển mọi `DECIMAL` từ database sang JavaScript `Number` để làm tính toán; hãy dùng hợp đồng giá trị số phù hợp, kiểu decimal chuyên dụng hoặc đơn vị tiền nhỏ nhất theo thiết kế đã chọn.

### 6.3. Làm tròn: phân biệt số học và cách in ra

Đôi khi tính toán cần làm tròn theo quy tắc nghiệp vụ, khi đó việc tính trong SQL có thể phù hợp:

~~~sql
SELECT
    product_name,
    ROUND(unit_price * 0.90, 2) AS discounted_price
FROM products
ORDER BY product_id;
~~~

`discounted_price` vẫn là giá trị số trên các DBMS hỗ trợ dạng `ROUND` này. Nó khác với cách một UI in `890000` thành `890.000 ₫`. Việc **làm tròn giá trị** có thể ảnh hưởng đến tổng tiền, thuế hoặc đối soát; cần thống nhất quy tắc nghiệp vụ. Việc **định dạng số chữ số hiển thị** không được âm thầm sửa giá trị tính toán bên dưới.

## 7. Định dạng ngày và thời gian

### 7.1. DATE là ngày lịch, không phải chuỗi “dd/MM/yyyy”

Với cột `stocked_on DATE`, SQL giữ thông tin ngày như một kiểu dữ liệu:

~~~sql
SELECT
    product_name,
    stocked_on
FROM products
ORDER BY stocked_on ASC, product_id ASC;
~~~

Ngày được sắp **theo trình tự lịch**. Ví dụ dữ liệu mẫu theo thời gian là:

1. Chuột — 2026-09-30
2. Sổ tay — 2026-10-15
3. Bàn phím — 2026-11-01
4. Cáp USB — 2026-11-03

Một cách trình bày ở Việt Nam có thể là `30/09/2026`, `15/10/2026`, `01/11/2026`, `03/11/2026`. Nếu chuyển ngày thành chuỗi `dd/MM/yyyy` rồi **sắp theo chuỗi**, kết quả có thể sai trình tự lịch: `01/11/2026` sẽ đứng trước `30/09/2026` khi so theo ký tự.

Trong Java, dùng kiểu ngày và formatter:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalDate stockedOn = LocalDate.of(2026, 11, 1);
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.forLanguageTag("vi-VN"));

String displayDate = stockedOn.format(formatter);
// "01/11/2026"
~~~

Lớp truy vấn trả `DATE`, service ánh xạ thành `LocalDate` và lớp trình bày tạo chuỗi `displayDate`. Với API, dạng ngày ISO `2026-11-01` thường phù hợp làm hợp đồng máy đọc hơn vì ít gây hiểu nhầm giữa ngày và tháng.

### 7.2. DATE, TIMESTAMP và múi giờ là các khái niệm khác nhau

- `DATE` biểu diễn ngày trên lịch, không chỉ ra một thời điểm tuyệt đối.
- `TIME` biểu diễn giờ trong ngày, với chi tiết timezone phụ thuộc kiểu cụ thể.
- `TIMESTAMP`/`DATETIME` có thể biểu diễn ngày giờ **không kèm múi giờ** tùy DBMS.
- Kiểu thời điểm có thông tin múi giờ như PostgreSQL `TIMESTAMPTZ` cần được diễn giải theo quy tắc DBMS; cách lưu và hiển thị có thể khác giữa các hệ.

Đối với sự kiện “đơn hàng được tạo lúc nào”, nhiều hệ nên lưu một **thời điểm** nhất quán rồi hiển thị theo múi giờ của người dùng. Đối với “ngày sinh” hoặc “ngày nhập kho” chỉ có ngày, không nên tự chuyển thành một timestamp rồi vô tình làm lệch ngày khi trình bày ở múi giờ khác.

Nếu UI nhận ngày dạng `YYYY-MM-DD`, hãy xử lý nó như **calendar date**. Đừng tùy tiện dùng `new Date(dateString)` rồi hiển thị theo múi giờ máy người dùng mà chưa hiểu quy tắc parse/ngữ nghĩa UTC; một số cách chuyển đổi khiến ngày hiển thị trước hoặc sau một ngày ở vùng giờ khác.

### 7.3. Định dạng bằng SQL chỉ nên là bước có mục đích

PostgreSQL hỗ trợ hàm:

~~~sql
SELECT
    product_name AS "Sản phẩm",
    TO_CHAR(stocked_on, 'DD/MM/YYYY') AS "Ngày nhập"
FROM products
ORDER BY stocked_on, product_id;
~~~

Đây là cách hữu ích cho **báo cáo một lần dành cho người đọc**. Nhưng `"Ngày nhập"` ở đây là **chuỗi**, và `TO_CHAR` không phải hàm có cùng cú pháp ở mọi hệ SQL.

Nếu kết quả được gửi cho API hoặc đưa sang công đoạn lọc theo ngày, ưu tiên trả cột `stocked_on` có kiểu `DATE`. UI mới format thành `01/11/2026` hoặc `Nov 1, 2026` theo ngôn ngữ người xem.

## 8. Nhãn trạng thái, mã nghiệp vụ và NULL

### 8.1. Mã trạng thái ổn định, văn bản hiển thị theo ngôn ngữ

Giả sử một ứng dụng cần hiển thị sản phẩm còn hàng và hết hàng. SQL có thể tính **mã trạng thái có ý nghĩa nghiệp vụ**:

~~~sql
SELECT
    product_id,
    product_name,
    CASE
        WHEN stock_quantity = 0 THEN 'OUT_OF_STOCK'
        ELSE 'AVAILABLE'
    END AS availability_code
FROM products
ORDER BY product_id;
~~~

| product_id | product_name | availability_code |
| ---: | --- | --- |
| 101 | Sổ tay | AVAILABLE |
| 102 | Bàn phím | AVAILABLE |
| 103 | Chuột | OUT_OF_STOCK |
| 104 | Cáp USB | AVAILABLE |

API có thể công bố `availabilityCode` và UI ánh xạ:

| Mã | Tiếng Việt | Tiếng Anh |
| --- | --- | --- |
| `AVAILABLE` | Còn hàng | In stock |
| `OUT_OF_STOCK` | Hết hàng | Out of stock |

Với một ứng dụng chỉ dùng tiếng Việt, có thể trả câu chữ trực tiếp từ `CASE` trong một báo cáo. Nhưng với nhiều ngôn ngữ hoặc nhiều consumer, mã ổn định thường giảm việc gắn cứng ngôn ngữ hiển thị trong SQL.

Điều kiện `stock_quantity = 0` ở đây là ví dụ. Trong hệ thật, “còn bán”, “còn hàng” hay “có thể đặt” có thể cần thêm tồn kho được giữ chỗ, trạng thái đăng bán và chính sách nghiệp vụ; không tự suy từ một cột nếu định nghĩa chưa đủ.

### 8.2. Hiển thị giá trị NULL

~~~sql
SELECT product_id, product_name, note
FROM products
ORDER BY product_id;
~~~

Ở sản phẩm 101 và 103, `note IS NULL`. Có thể muốn hiển thị trên màn hình là **“Chưa có ghi chú”**, nhưng không nên lưu cụm này vào database để thay thế mọi `NULL`. Khi thật sự thiếu thông tin, để `NULL` giữ ý nghĩa thiếu dữ liệu.

Trong truy vấn báo cáo, `COALESCE` có thể phù hợp:

~~~sql
SELECT
    product_name AS "Tên sản phẩm",
    COALESCE(note, 'Chưa có ghi chú') AS "Ghi chú"
FROM products
ORDER BY product_id;
~~~

Kết quả là giá trị văn bản đã được thay thế. Tuy nhiên, nếu API trả về `note` dạng chuỗi thay thế như vậy, consumer sẽ không còn phân biệt được một ghi chú **thật sự có nội dung** “Chưa có ghi chú” với một giá trị **NULL**. Với API dùng chung, giữ `note: null` và đặt placeholder trên UI thường minh bạch hơn.

Nếu nghiệp vụ định nghĩa `NULL` tương đương với một giá trị mặc định cụ thể, dùng `COALESCE` ở SQL có thể là quyết định đúng. Cần phân biệt rõ **quy tắc giá trị nghiệp vụ** và **văn bản hiển thị**.

## 9. Một API nên trả nhãn hiển thị hay dữ liệu có kiểu?

Giả sử UI cần hiển thị sản phẩm 102. Có hai kiểu giao diện trả dữ liệu:

**Giao diện đã định dạng sẵn cho một màn hình cố định:**

~~~json
{
  "tenSanPham": "Bàn phím",
  "donGia": "890.000 ₫",
  "ngayNhap": "01/11/2026"
}
~~~

Dữ liệu này dễ đưa lên màn hình tiếng Việt, nhưng trường `donGia` đã là chuỗi; người dùng tiếng Anh hoặc tác vụ tính tổng cần tháo định dạng, xử lý locale và phục hồi giá trị số. Việc thay nhãn khiến tên thuộc tính trong giao diện thay đổi.

**Giao diện dữ liệu có hợp đồng rõ ràng:**

~~~json
{
  "productId": 102,
  "productName": "Bàn phím",
  "unitPrice": "890000.00",
  "currencyCode": "VND",
  "stockedOn": "2026-11-01",
  "stockQuantity": 3,
  "note": "Bảo hành 12 tháng"
}
~~~

Ở ví dụ thứ hai, `unitPrice` được biểu diễn dạng chuỗi thập phân **theo hợp đồng API này** nhằm bảo toàn chính xác giá trị decimal khi qua các nền tảng có xử lý số khác nhau. Một API khác có thể chọn JSON number hoặc minor units (`integer`) với hợp đồng rõ ràng. JSON tự thân không có kiểu `DECIMAL` hoặc `DATE` riêng; vì vậy **schema API** phải ghi rõ kiểu ý nghĩa và cách parse những trường này.

Từ dữ liệu thứ hai, mỗi client có thể chọn:

- Nhãn `unitPrice` là “Đơn giá” hay “Unit price”.
- Dạng tiền là `890.000 ₫`, cách viết theo locale khác, hoặc dạng số thuần cho hệ thống máy đọc.
- Ngày là `01/11/2026` hay `11/01/2026` tùy quy ước của người dùng.
- Chú thích `NULL` hiển thị trống, dấu gạch ngang hay “Chưa có ghi chú”.

**Không có quy tắc rằng mọi API đều phải trả số dưới dạng chuỗi.** Điều quan trọng là hợp đồng nhất quán, bảo toàn ý nghĩa kiểu dữ liệu, có thông tin đơn vị và không ép UI/parser đoán từ một chuỗi đã format.

## 10. Đọc nhãn cột từ JDBC ResultSet

Khi dùng Java/JDBC, `ResultSet` giúp đọc dữ liệu theo hàng, còn `ResultSetMetaData` mô tả cột kết quả. Ví dụ:

~~~java
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.Connection;
import java.math.BigDecimal;

String sql = """
    SELECT
        product_id AS id,
        product_name AS name,
        unit_price AS price
    FROM products
    ORDER BY product_id
    """;

try (PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet rs = statement.executeQuery()) {

    ResultSetMetaData metadata = rs.getMetaData();

    for (int column = 1; column <= metadata.getColumnCount(); column++) {
        System.out.println(metadata.getColumnLabel(column));
    }
    // Các nhãn: id, name, price

    while (rs.next()) {
        int id = rs.getInt("id");
        String name = rs.getString("name");
        BigDecimal price = rs.getBigDecimal("price");

        System.out.println(id + " - " + name + " - " + price);
    }
}
~~~

Ở đoạn trên:

- `getColumnLabel(index)` trả **nhãn được đề xuất cho việc hiển thị** của cột, thường là alias `AS` nếu có.
- `getColumnName(index)` liên quan tên cột, nhưng cách ánh xạ alias/tên gốc có thể phụ thuộc driver và biểu thức; không nên dựa vào nó để suy ra tên cột vật lý cho mọi query.
- `getBigDecimal("price")` vẫn đọc **số thập phân**, không phải chuỗi tiền tệ đã format.
- Tên alias là một phần giao diện kết quả nếu code dùng `getString("name")` hoặc `getBigDecimal("price")`. Đổi alias trong SQL có thể làm mapper thất bại dù dữ liệu trong bảng không đổi.

Nếu chương trình cần xuất bảng có header tiếng Việt, có thể ánh xạ từ những key ổn định `id`, `name`, `price` sang nhãn trình bày thay vì đổi SQL theo từng ngôn ngữ. Tầng Java/JDBC cũng có thể định dạng giá bằng `NumberFormat` hoặc ngày bằng `DateTimeFormatter` tại điểm tạo báo cáo cho người đọc.

## 11. Định dạng trong SQL khi nào là hợp lý?

Việc định dạng ngay tại database có thể phù hợp khi **đầu ra cuối cùng vốn là chuỗi dành cho người đọc**, ví dụ:

- Báo cáo ad hoc chạy trực tiếp bằng SQL client.
- View chuyên dùng cho báo cáo có hợp đồng ngôn ngữ, đơn vị và định dạng cố định.
- Một luồng xuất văn bản theo đặc tả định dạng đã được thống nhất với hệ nhận.
- Mẫu tổng hợp được DBMS tạo và tiêu thụ hoàn toàn trong phạm vi cùng một dialect.

Ví dụ PostgreSQL cho một báo cáo chỉ xem bằng mắt:

~~~sql
SELECT
    product_name AS "Sản phẩm",
    TO_CHAR(stocked_on, 'DD/MM/YYYY') AS "Ngày nhập",
    TO_CHAR(unit_price, 'FM999G999G990') AS "Đơn giá (VND)"
FROM products
ORDER BY stocked_on ASC, product_id ASC;
~~~

`TO_CHAR` trả **chuỗi**; các ký hiệu định dạng số như `G` có thể phụ thuộc thiết lập locale của session/database. Khi thiết kế báo cáo dùng chung, cần ghi rõ locale, thứ tự sắp xếp và mục đích đầu ra. Tránh lấy kết quả `"Đơn giá (VND)"` đã format rồi tính `SUM` hoặc `AVG` trong bước tiếp theo.

Nếu viết SQL cho ứng dụng đa ngôn ngữ, cách tiếp cận thường phù hợp hơn là:

~~~sql
SELECT
    product_id,
    product_name,
    unit_price,
    stocked_on,
    unit_price * stock_quantity AS inventory_value
FROM products
ORDER BY product_id;
~~~

Sau đó UI/report engine mới quyết định cách hiển thị.

### Excel, CSV và file máy đọc

Đối với **Excel**, nên giữ ô tiền là dữ liệu số, ô ngày là dữ liệu ngày và áp dụng **cell number format**; điều đó cho phép người dùng tiếp tục tính tổng, lọc và sắp xếp theo kiểu đúng.

Đối với **CSV**, mọi ô thường được ghi ra dưới dạng văn bản. Nếu file phục vụ máy đọc, nên ưu tiên hợp đồng định dạng nhất quán như:

~~~csv
product_id,product_name,unit_price,currency_code,stocked_on
102,Bàn phím,890000.00,VND,2026-11-01
~~~

Nếu CSV là báo cáo cho một nhóm người dùng và đặc tả quy định tiếng Việt, các tiêu đề có thể là “Mã sản phẩm”, “Đơn giá (VND)”, “Ngày nhập kho”, kèm số/ngày đã format. Khi đó cần lưu ý việc dấu phẩy, dấu chấm, dấu phân cách trường, dấu ngoặc kép và mã hóa UTF-8 có thể bị các công cụ nhập CSV diễn giải khác nhau. Không trộn hai hợp đồng “cho người đọc” và “cho máy xử lý” mà không nêu rõ.

## 12. Tính khả chuyển và những điểm hay nhầm

### 12.1. Dấu trích dẫn định danh và alias

| Hệ quản trị | Ví dụ đặt nhãn chứa dấu cách | Ghi chú |
| --- | --- | --- |
| SQL tiêu chuẩn / PostgreSQL | `AS "Tên sản phẩm"` | Dùng dấu ngoặc kép cho identifier |
| MySQL / MariaDB | `AS \`Tên sản phẩm\`` | MySQL dùng backtick; chế độ SQL có thể cho phép dấu ngoặc kép |
| SQL Server | `AS [Tên sản phẩm]` | Hỗ trợ dấu ngoặc vuông; dấu ngoặc kép phụ thuộc cấu hình `QUOTED_IDENTIFIER` |
| SQLite | `AS "Tên sản phẩm"` | Hỗ trợ dấu ngoặc kép cho identifier |

Dấu nháy đơn `'Tên sản phẩm'` thường là **literal chuỗi**, không phải cách trích dẫn định danh tiêu chuẩn. Để tránh phải trích dẫn mọi nơi, alias ổn định trong SQL ứng dụng thường dùng `snake_case` hoặc tên không dấu rõ nghĩa.

### 12.2. Hàm format số và ngày phụ thuộc dialect

| Nhu cầu | Ví dụ hàm/cách làm | Lưu ý |
| --- | --- | --- |
| Định dạng ngày ở PostgreSQL | `TO_CHAR(date_value, 'DD/MM/YYYY')` | Kết quả là text |
| Định dạng ở SQL Server | `FORMAT(value, format, culture)` hoặc `CONVERT` với style | Cú pháp, văn hóa và chi phí hàm riêng |
| Định dạng ở MySQL | `DATE_FORMAT(date_value, format)`, `FORMAT(number, decimals)` | Cú pháp mẫu, locale và dạng trả về riêng |
| Định dạng ở SQLite | `strftime(format, date_value)` | Quy tắc biểu diễn ngày giờ phụ thuộc các hàm date/time |
| Trình bày ở Java / web | `NumberFormat`, `DateTimeFormatter`, `Intl.NumberFormat` | Tách khỏi dialect SQL, phụ thuộc locale của người dùng |

Hàm có tên gần giống nhau ở hai hệ không có nghĩa tham số và kết quả giống nhau. Nếu mục tiêu là tính khả chuyển và nhiều locale, nên đưa định dạng ra khỏi SQL. Nếu một báo cáo cần dùng hàm của một DBMS cụ thể, hãy ghi rõ dialect và phiên bản.

### 12.3. Collation, timezone và thứ tự

Định dạng không đồng nhất với **quy tắc so sánh**. Thứ tự chuỗi theo `ORDER BY product_name` có thể khác giữa các collation; đổi nhãn hiển thị sang tiếng Việt không làm thay đổi collation database. Nếu cần thứ tự theo ngôn ngữ người dùng, phải thiết kế rõ việc sắp xếp thực hiện ở DB (collation phù hợp) hay tại UI, đặc biệt với phân trang do server thực hiện.

Tương tự, thời điểm có timezone cần được chuyển theo vùng giờ trước khi in dạng ngày giờ. Ví dụ cùng một instant có thể là cuối ngày ở quốc gia này và đầu ngày hôm sau ở quốc gia khác. Không dùng một chuỗi định dạng cố định tại database rồi mặc định đó là giờ địa phương của mọi người dùng.

## 13. Các lỗi thường gặp và cách tránh

| Cách làm | Vấn đề | Hướng phù hợp |
| --- | --- | --- |
| `SELECT unit_price AS "890.000 ₫"` | Alias là **tên cột**, không phải phép format số | Dùng alias có ý nghĩa như `unit_price`; format giá trị ở UI |
| `CAST(unit_price AS VARCHAR)` rồi `ORDER BY` kết quả | Sắp xếp theo văn bản có thể sai thứ tự số | Sắp theo `unit_price` kiểu số |
| Trả `TO_CHAR(stocked_on, ...)` cho mọi API | Mất kiểu ngày và gắn chặt một định dạng | Trả ngày theo hợp đồng máy đọc; UI format |
| Dùng nhãn “Đơn giá” làm key JSON chung | Khó đổi ngôn ngữ, phá consumer khi đổi nhãn | Dùng tên key ổn định; label ở UI |
| Chuyển `DECIMAL` thành `FLOAT` để dễ format | Có thể mất chính xác khi tính toán tiền | Giữ decimal hoặc chiến lược tiền đã quy định |
| Ghi `'Chưa có ghi chú'` thay `NULL` | Mất phân biệt dữ liệu thiếu và chuỗi thật | Lưu `NULL`; UI đặt placeholder |
| `SELECT *` rồi sử dụng cột theo vị trí | Schema thay đổi có thể phá mapping | Chọn cột và alias cụ thể |
| Tính tổng bằng cách cộng chuỗi đã chứa ký hiệu tiền | Phải parse lại và dễ sai locale | Tính trên số có kiểu trước, format cuối |
| Sắp xếp ngày đã chuyển thành `DD/MM/YYYY` | Thứ tự từ điển không phải thứ tự lịch | Sắp theo kiểu `DATE`/timestamp |
| Dùng `AS "Tên sản phẩm"` nhưng mapper đọc `product_name` | Tên cột kết quả đã thay đổi | Đồng bộ mapping hoặc giữ alias ổn định |
| Dùng tên nhãn UI thay mã trạng thái SQL | Văn bản phụ thuộc ngôn ngữ và khó dùng logic | Trả mã ổn định, UI dịch thành nhãn |
| Ép mọi ngày thành timestamp UTC | Ngày lịch có thể bị lệch khi chuyển múi giờ | Phân biệt `DATE` với thời điểm tuyệt đối |

## 14. Bài tập thực hành

Sử dụng bảng `products` ở mục 2. Hãy giữ dữ liệu mẫu ban đầu.

### Bài 1 — Phân biệt nhãn và giá trị

Truy vấn sau thay đổi gì trong bảng?

~~~sql
SELECT
    product_name AS "Tên sản phẩm",
    unit_price AS "Đơn giá"
FROM products
ORDER BY product_id;
~~~

**Đáp án:** không thay đổi cấu trúc hay dữ liệu bảng. Nó chỉ đổi **nhãn hai cột kết quả**; `unit_price` vẫn là số. Không thể suy ra truy vấn đã thêm dấu phân cách nghìn hoặc ký hiệu tiền.

### Bài 2 — Tạo nhãn cho biểu thức có thể tính toán

Lấy tên sản phẩm, giá gốc, số lượng và giá trị tồn kho, dùng alias `inventory_value`. Sắp theo giá trị tồn kho giảm dần, nếu bằng nhau thì theo `product_id` tăng dần.

~~~sql
SELECT
    product_name,
    unit_price,
    stock_quantity,
    unit_price * stock_quantity AS inventory_value
FROM products
ORDER BY inventory_value DESC, product_id;
~~~

Kết quả theo tên lần lượt: **Bàn phím, Cáp USB, Sổ tay, Chuột**. Các giá trị tồn kho tương ứng là 2.670.000, 960.000, 540.000 và 0 (vẫn là giá trị số ở kết quả SQL).

### Bài 3 — Chọn lớp định dạng

Một sản phẩm có `unit_price = 890000.00`, `stocked_on = DATE '2026-11-01'`. Một ứng dụng có UI tiếng Việt, UI tiếng Anh và một API dành cho đối tác. Nên chọn cách nào?

A. Dùng `TO_CHAR`/hàm format trong mọi truy vấn và trả chuỗi tiếng Việt cho cả ba nơi.

B. Trả dữ liệu có kiểu và hợp đồng rõ ràng từ backend; để mỗi UI định dạng theo locale, còn API đối tác nhận dữ liệu máy đọc.

**Đáp án:** B thường phù hợp hơn. A chỉ hợp lý cho một báo cáo cố định mà đầu ra đã được quy định là văn bản tiếng Việt.

### Bài 4 — Phân biệt số và chuỗi khi sắp xếp

Giải thích vì sao hai truy vấn có thể trả hàng theo thứ tự khác nhau:

~~~sql
-- Sắp xếp theo số:
SELECT product_name, unit_price
FROM products
ORDER BY unit_price ASC;

-- Sắp xếp theo chữ:
SELECT
    product_name,
    CAST(unit_price AS VARCHAR(32)) AS price_text
FROM products
ORDER BY price_text ASC;
~~~

**Đáp án:** thứ nhất so sánh giá kiểu số; thứ hai so sánh chuỗi theo quy tắc text/collation. Ví dụ chuỗi `'120000.00'` có thể đứng trước `'45000.00'`, trái với thứ tự giá trị số. Để hiển thị đúng và sắp theo giá, giữ cột số làm khóa sắp xếp.

### Bài 5 — Thiết kế nhãn theo nhiều ngôn ngữ

Một API trả:

~~~json
{
  "productName": "Chuột",
  "unitPrice": "255000.00",
  "currencyCode": "VND",
  "stockedOn": "2026-09-30",
  "note": null
}
~~~

Hãy đề xuất nhãn tiếng Việt và tiếng Anh cho hai trường `productName`, `unitPrice`; cho biết nên hiển thị `note = null` như thế nào.

**Gợi ý:** UI tiếng Việt: “Tên sản phẩm”, “Đơn giá”; tiếng Anh: “Product name”, “Unit price”. Trường `note` có thể được để trống hoặc hiển thị “Chưa có ghi chú”/“No note”, nhưng API vẫn trả `null` theo hợp đồng thay vì lưu văn bản đó vào database.

### Bài 6 — Kết quả JDBC

Cho:

~~~sql
SELECT product_name AS name, unit_price AS price
FROM products
WHERE product_id = 102;
~~~

Trong JDBC, hai tên dùng để đọc kết quả là gì, và kiểu Java nào phù hợp để đọc giá không mất chính xác thập phân?

**Đáp án:** truy cập `rs.getString("name")` và `rs.getBigDecimal("price")`. `BigDecimal` phù hợp cho giá tiền ví dụ; việc đổi alias thành `"Tên sản phẩm"` hoặc `"Đơn giá"` sẽ đổi tên cột được driver nhìn thấy và có thể yêu cầu cập nhật mapper.

## 15. Ghi nhớ

**`AS` giúp đặt nhãn cho cột kết quả, không quyết định cách trình bày các giá trị.** Cột `DECIMAL` nên giữ tính chất số để cộng, lọc và sắp xếp; cột `DATE` nên giữ ý nghĩa ngày để so sánh thời gian. Việc biến số thành tiền có ký hiệu, ngày thành dạng theo vùng và mã trạng thái thành chữ tiếng Việt/tiếng Anh thường thuộc **lớp trình bày**. SQL vẫn có thể tính các biểu thức nghiệp vụ, đặt alias ổn định và tạo báo cáo văn bản khi đó là đầu ra cuối cùng được yêu cầu.

Khi thiết kế `SELECT`, hãy tự hỏi: **đang đặt tên dữ liệu, đang tính giá trị nghiệp vụ, hay đang trình bày cho người đọc?** Câu trả lời quyết định nên dùng alias trong SQL, phép tính có kiểu ở database/service, hay formatter ở UI và báo cáo.
