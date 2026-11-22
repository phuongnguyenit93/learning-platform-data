# ASC, DESC và sắp xếp theo biểu thức

Một danh sách đơn hàng thường phải được trình bày theo thứ tự dễ hiểu: **mới nhất trước**, **giá trị cao nhất trước**, **tên khách hàng theo chữ cái**, hoặc **đơn cần xử lý trước**. Khi danh sách có nhiều trang, thứ tự còn quyết định bản ghi nào xuất hiện ở từng trang. Trong SQL, công cụ chính để giải quyết những yêu cầu này là mệnh đề **`ORDER BY`**, kết hợp với hai hướng sắp xếp **`ASC`** và **`DESC`**.

`ORDER BY` không chỉ sắp xếp theo một cột nguyên dạng. Ta còn có thể sắp xếp bằng **nhiều cột**, **biểu thức tính toán**, **bí danh cột**, **biểu thức `CASE`**, **hàm xử lý văn bản** và **giá trị tổng hợp**. Lựa chọn khóa sắp xếp đúng đặc biệt quan trọng khi có những hàng bằng nhau, cột chứa `NULL` hoặc ứng dụng phân trang.

Bài này dùng SQL với ví dụ trên **PostgreSQL**, đồng thời chỉ rõ những điểm có thể khác giữa các hệ quản trị. Bạn sẽ biết cách chọn thứ tự phù hợp với nghiệp vụ, dự đoán kết quả và tạo danh sách có thứ tự ổn định.

## 1. ORDER BY làm gì trong truy vấn?

Trong một câu `SELECT`, `WHERE` quyết định **hàng nào được giữ**, còn `ORDER BY` quyết định **thứ tự các hàng trong kết quả**.

```sql
SELECT cot_1, cot_2
FROM ten_bang
WHERE dieu_kien
ORDER BY cot_1 ASC, cot_2 DESC;
```

Ý nghĩa:

- `ORDER BY` bắt đầu danh sách tiêu chí sắp xếp.
- `ASC` (*ascending*) là **tăng dần**; nếu không ghi hướng thì SQL mặc định là `ASC`.
- `DESC` (*descending*) là **giảm dần**.
- Nhiều tiêu chí được phân cách bằng dấu phẩy; tiêu chí tiếp theo được dùng để phân định thứ tự khi tiêu chí trước **bằng nhau**.

Ví dụ tổng quát:

```sql
ORDER BY created_on DESC, order_id ASC
```

Cách đọc: “ngày tạo mới nhất trước; nếu hai đơn cùng ngày thì mã đơn nhỏ hơn trước”.

**Không có `ORDER BY` thì SQL không bảo đảm thứ tự các hàng được trả về.** Dữ liệu có thể tình cờ xuất hiện theo khóa chính hoặc thứ tự chèn, nhưng kết quả ấy có thể thay đổi khi DBMS đổi kế hoạch truy vấn, bổ sung chỉ mục hoặc có dữ liệu mới. Để hiển thị một danh sách theo thứ tự nhất định, hãy yêu cầu `ORDER BY` rõ ràng.

## 2. Tạo bảng dữ liệu mẫu

Thực hành với bảng `sales_orders` trong **cơ sở dữ liệu học tập riêng**. Bảng có ngày đặt, trạng thái, thông tin khách hàng, số lượng, đơn giá, chiết khấu và điểm đánh giá. Dữ liệu được cố định để có thể tính kết quả bằng tay.

```sql
CREATE TABLE sales_orders (
    order_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0
        CHECK (discount_amount >= 0),
    created_on DATE NOT NULL,
    rating NUMERIC(2, 1) CHECK (rating BETWEEN 0 AND 5)
);

INSERT INTO sales_orders
    (order_id, customer_name, status, unit_price, quantity,
     discount_amount, created_on, rating)
VALUES
    (101, 'An',   'PAID',      150000, 2, 20000, DATE '2025-02-01', 5.0),
    (102, 'Binh', 'NEW',       300000, 1,     0, DATE '2025-02-02', NULL),
    (103, 'Chi',  'PAID',      100000, 3,     0, DATE '2025-02-02', 4.0),
    (104, 'An',   'PAID',      200000, 1,     0, DATE '2025-02-04', NULL),
    (105, 'Dung', 'CANCELLED', 150000, 2,     0, DATE '2025-02-04', 3.0),
    (106, 'Binh', 'PAID',      250000, 1, 50000, DATE '2025-02-05', 5.0),
    (107, 'Chi',  'NEW',       200000, 1,     0, DATE '2025-02-06', NULL),
    (108, 'Em',   'PAID',       50000, 2,     0, DATE '2025-02-06', 4.0);
```

Xem dữ liệu theo mã đơn để dễ đối chiếu:

```sql
SELECT order_id, customer_name, status,
       unit_price, quantity, discount_amount, created_on, rating
FROM sales_orders
ORDER BY order_id;
```

| Mã đơn | Khách | Trạng thái | Đơn giá | Số lượng | Giảm giá | Ngày tạo | Đánh giá |
|---:|---|---|---:|---:|---:|---|---:|
| 101 | An | PAID | 150.000 | 2 | 20.000 | 2025-02-01 | 5.0 |
| 102 | Binh | NEW | 300.000 | 1 | 0 | 2025-02-02 | `NULL` |
| 103 | Chi | PAID | 100.000 | 3 | 0 | 2025-02-02 | 4.0 |
| 104 | An | PAID | 200.000 | 1 | 0 | 2025-02-04 | `NULL` |
| 105 | Dung | CANCELLED | 150.000 | 2 | 0 | 2025-02-04 | 3.0 |
| 106 | Binh | PAID | 250.000 | 1 | 50.000 | 2025-02-05 | 5.0 |
| 107 | Chi | NEW | 200.000 | 1 | 0 | 2025-02-06 | `NULL` |
| 108 | Em | PAID | 50.000 | 2 | 0 | 2025-02-06 | 4.0 |

Trong các ví dụ bên dưới, “giá trị đơn” được tính bằng:

```text
order_amount = unit_price * quantity - discount_amount
```

Giá trị lần lượt của các đơn 101 đến 108 là **280.000; 300.000; 300.000; 200.000; 300.000; 200.000; 200.000; 100.000**. Đây là dữ liệu minh họa cho phép sắp xếp, không phải mô hình thanh toán đầy đủ; đơn đã hủy vẫn có thể có giá trị ghi nhận nhưng không được tính là doanh thu thực nhận.

## 3. Sắp xếp tăng dần bằng ASC

**`ASC`** đưa các giá trị nhỏ hơn lên trước trong thứ tự áp dụng cho kiểu dữ liệu. Với số là nhỏ đến lớn; với ngày là cũ đến mới; với chuỗi là theo thứ tự đối chiếu ký tự của DBMS.

Ví dụ, xem đơn theo ngày tạo **cũ nhất trước**:

```sql
SELECT order_id, created_on
FROM sales_orders
ORDER BY created_on ASC, order_id ASC;
```

| order_id | created_on |
|---:|---|
| 101 | 2025-02-01 |
| 102 | 2025-02-02 |
| 103 | 2025-02-02 |
| 104 | 2025-02-04 |
| 105 | 2025-02-04 |
| 106 | 2025-02-05 |
| 107 | 2025-02-06 |
| 108 | 2025-02-06 |

Khi dùng `ORDER BY created_on ASC` mà không có khóa phụ, **hai đơn cùng ngày không có thứ tự được bảo đảm**. Ở ví dụ này, `order_id ASC` làm rõ cách phân định những ngày bằng nhau.

Mặc định có thể bỏ chữ `ASC`:

```sql
-- Hai cách dưới đây có cùng hướng sắp xếp:
ORDER BY created_on ASC, order_id ASC

-- Hoặc:
ORDER BY created_on, order_id
```

Hai dòng `ORDER BY` trên là **hai lựa chọn minh họa riêng biệt**, không viết nối liên tiếp trong cùng một câu `SELECT`.

### Sắp xếp số theo ASC

```sql
SELECT order_id, quantity
FROM sales_orders
ORDER BY quantity ASC, order_id ASC;
```

Những đơn có số lượng **1** sẽ xuất hiện trước, rồi đến số lượng **2**, cuối cùng số lượng **3**. Trong mỗi nhóm cùng số lượng, `order_id ASC` quyết định thứ tự.

## 4. Sắp xếp giảm dần bằng DESC

**`DESC`** đặt giá trị lớn hơn trước: giá tiền cao nhất, ngày mới nhất, số lượng lớn nhất hoặc thứ tự chữ cái đảo ngược.

Ví dụ yêu cầu thường gặp: **đơn mới nhất trước**.

```sql
SELECT order_id, created_on
FROM sales_orders
ORDER BY created_on DESC, order_id DESC;
```

Kết quả theo ID: **108, 107, 106, 105, 104, 103, 102, 101**.

Vì các đơn 107 và 108 cùng ngày 6/2, khóa phụ `order_id DESC` đặt **108** trước **107**. Nếu có nhu cầu “đơn có ID nhỏ hơn trước trong cùng ngày”, hãy đổi riêng khóa phụ thành `order_id ASC`.

Hai hướng có thể xuất hiện cùng truy vấn:

```sql
SELECT order_id, customer_name, created_on
FROM sales_orders
ORDER BY customer_name ASC, created_on DESC, order_id DESC;
```

Cách đọc: theo **tên khách A → Z**, trong mỗi khách lấy **đơn mới nhất trước**, nếu vẫn bằng nhau thì **ID lớn hơn trước**.

Kết quả trên các tên đã lưu trong bộ dữ liệu mẫu có thứ tự theo nhóm: **An** (104, 101), **Binh** (106, 102), **Chi** (107, 103), **Dung** (105), **Em** (108).

## 5. Nhiều khóa sắp xếp và thứ tự ổn định

`ORDER BY` xét các khóa từ trái sang phải:

1. Khóa thứ nhất phân nhóm thứ tự chính.
2. Khi hai hàng bằng nhau ở khóa thứ nhất, xét khóa thứ hai.
3. Nếu vẫn bằng nhau, xét tiếp khóa thứ ba, thứ tư, v.v.

Ví dụ:

```sql
SELECT order_id, status, created_on
FROM sales_orders
ORDER BY status ASC, created_on DESC, order_id ASC;
```

Hướng `ASC` và `DESC` chỉ áp dụng **cho khóa ngay trước nó**. Khi không chỉ rõ thứ tự cuối cùng cho các hàng có cùng tất cả khóa, DBMS không phải giữ chúng ở thứ tự chèn hay thứ tự khóa chính.

### Khóa phân định duy nhất

Trong hệ thống thực tế, nhiều hàng có thể có cùng `created_on`, `status`, số tiền hoặc điểm đánh giá. Nếu giao diện phân trang, nên thêm một khóa **duy nhất và ổn định**, thường là khóa chính:

```sql
ORDER BY created_on DESC, order_id DESC
```

Vì `order_id` là `PRIMARY KEY`, hai hàng khác nhau không thể bằng nhau ở **cả hai khóa**. Do đó, với **cùng một tập dữ liệu và cùng quy tắc so sánh**, thứ tự được xác định rõ ràng. Điều này quan trọng để tránh một hàng di chuyển tùy ý giữa các trang chỉ vì có nhiều đơn cùng ngày.

Lưu ý: **thứ tự xác định không có nghĩa tập dữ liệu luôn bất biến**. Nếu có người thêm, xóa hoặc cập nhật đơn giữa hai lần tải trang, phân trang vẫn có thể thay đổi; phần sau sẽ giải thích cách xử lý.

## 6. Sắp xếp theo biểu thức số học

Không phải lúc nào dữ liệu cần sắp xếp cũng đã được lưu sẵn trong một cột. Với bảng mẫu, giá trị đơn hàng phải được **tính**:

```sql
SELECT
    order_id,
    unit_price,
    quantity,
    discount_amount,
    unit_price * quantity - discount_amount AS order_amount
FROM sales_orders
ORDER BY unit_price * quantity - discount_amount DESC,
         order_id ASC;
```

Kết quả:

| order_id | order_amount |
|---:|---:|
| 102 | 300000.00 |
| 103 | 300000.00 |
| 105 | 300000.00 |
| 101 | 280000.00 |
| 104 | 200000.00 |
| 106 | 200000.00 |
| 107 | 200000.00 |
| 108 | 100000.00 |

DBMS tính biểu thức `unit_price * quantity - discount_amount` cho mỗi hàng trong tập kết quả liên quan, rồi sắp xếp theo giá trị đó. Với ba đơn cùng giá trị 300.000, khóa phụ `order_id ASC` đặt 102, 103, 105 theo thứ tự xác định.

### 6.1. Dùng bí danh trong ORDER BY

Ta có thể đặt tên cho biểu thức bằng `AS` để câu SQL dễ đọc:

```sql
SELECT
    order_id,
    unit_price * quantity - discount_amount AS order_amount
FROM sales_orders
ORDER BY order_amount DESC, order_id ASC;
```

Kết quả giống truy vấn ngay trên. Trong `ORDER BY` của cùng một `SELECT`, tên đầu ra `order_amount` có thể được dùng làm **bí danh** sắp xếp. Điều này giảm lặp lại biểu thức dài.

Tuy nhiên, bí danh ở `SELECT` **thường không dùng trực tiếp trong `WHERE` cùng cấp**:

```sql
-- Không viết như sau trong PostgreSQL:
-- SELECT unit_price * quantity - discount_amount AS order_amount
-- FROM sales_orders
-- WHERE order_amount >= 200000;
```

Để lọc theo giá trị tính được, có hai cách rõ ràng.

**Lặp biểu thức trong WHERE:**

```sql
SELECT order_id,
       unit_price * quantity - discount_amount AS order_amount
FROM sales_orders
WHERE unit_price * quantity - discount_amount >= 200000
ORDER BY order_amount DESC, order_id ASC;
```

**Hoặc tính trước bằng CTE (`WITH`):**

```sql
WITH order_values AS (
    SELECT
        order_id,
        unit_price * quantity - discount_amount AS order_amount
    FROM sales_orders
)
SELECT order_id, order_amount
FROM order_values
WHERE order_amount >= 200000
ORDER BY order_amount DESC, order_id ASC;
```

Cả hai cách trên trả về **102, 103, 105, 101, 104, 106, 107**. Đơn 108 có giá trị 100.000 nên bị lọc.

### 6.2. Thay đổi biểu thức có thể đổi thứ tự

`ORDER BY unit_price DESC` xếp theo **đơn giá**, không phải tổng giá trị đơn. Đơn 102 (đơn giá 300.000) sẽ được đưa lên cao, trong khi đơn 103 (đơn giá 100.000 nhưng số lượng 3) không nhất thiết xếp gần nó dù có cùng tổng giá trị 300.000.

Tương tự:

- `ORDER BY quantity DESC` xếp theo số lượng, không phải số tiền.
- `ORDER BY unit_price * quantity DESC` xếp theo giá trước giảm giá.
- `ORDER BY unit_price * quantity - discount_amount DESC` xếp theo giá sau giảm giá.

Biểu thức sắp xếp phải khớp **đại lượng mà người dùng đang muốn xếp hạng**. Nếu một phép tính có thể trả `NULL` (vì một toán hạng `NULL`), cần quy định cách xử lý `NULL` thay vì giả định phép tính luôn có kết quả số.

## 7. Sắp xếp theo biểu thức CASE: ưu tiên nghiệp vụ

Sắp xếp văn bản theo thứ tự chữ cái có thể không tương ứng với thứ tự xử lý nghiệp vụ. Chẳng hạn, bộ phận vận hành muốn:

1. Đơn đã thanh toán (`PAID`) xuất hiện trước.
2. Tiếp theo là đơn mới (`NEW`).
3. Cuối cùng là đơn đã hủy (`CANCELLED`).

Nếu chỉ `ORDER BY status ASC`, DBMS sẽ dùng thứ tự văn bản của các trạng thái, không biết “mức ưu tiên” ta đặt ra. Để sắp xếp theo thứ tự tùy chỉnh, dùng **`CASE`**:

```sql
SELECT order_id, status, created_on
FROM sales_orders
ORDER BY
    CASE status
        WHEN 'PAID' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'CANCELLED' THEN 3
        ELSE 4
    END ASC,
    created_on DESC,
    order_id ASC;
```

Kết quả theo ID: **108, 106, 104, 103, 101, 107, 102, 105**.

Giải thích:

- `CASE` biến mỗi trạng thái thành một **khóa thứ tự số**.
- `PAID` nhận 1 nên đứng trước `NEW` (2) và `CANCELLED` (3).
- Trong cùng mức ưu tiên, `created_on DESC` đặt ngày mới trước.
- Nếu cùng ngày, `order_id ASC` xác định thứ tự cuối.
- `ELSE 4` cho thứ tự dự phòng nếu hệ thống sau này cho phép trạng thái khác; trên bảng mẫu, `CHECK` đang giới hạn ba trạng thái.

**`CASE` trong `ORDER BY` chỉ quyết định thứ tự hiển thị; nó không sửa giá trị `status` trong bảng.** Nếu chính sách ưu tiên thay đổi, ta điều chỉnh biểu thức hoặc sử dụng bảng cấu hình mức ưu tiên trong thiết kế lớn hơn.

Trong các truy vấn báo cáo, có thể dùng `CASE` để đẩy những dòng “Cần xử lý” lên đầu, sắp xếp trạng thái theo vòng đời công việc, hoặc ưu tiên một loại kết quả phù hợp yêu cầu người dùng.

## 8. Sắp xếp theo hàm văn bản, ngày và biểu thức khác

`ORDER BY` cho phép sử dụng nhiều hàm mà DBMS hỗ trợ.

### 8.1. Sắp xếp theo LOWER(customer_name)

```sql
SELECT order_id, customer_name
FROM sales_orders
ORDER BY LOWER(customer_name) ASC, order_id ASC;
```

Hàm `LOWER` chuyển chuỗi thành chữ thường trong phép tính khóa sắp xếp. Nó có thể hữu ích khi muốn giảm ảnh hưởng của chữ hoa/chữ thường, nhưng **không bảo đảm thứ tự hoàn toàn giống nhau trên mọi hệ quản trị hoặc mọi collation**. Việc so sánh dấu tiếng Việt, thứ tự chữ và chuẩn hóa Unicode vẫn phụ thuộc DBMS/collation.

Trên bộ tên mẫu, các nhóm được sắp thành **An, Binh, Chi, Dung, Em**; trong cùng một tên, ID tăng dần. Giá trị `customer_name` được lưu trong bảng **không bị thay đổi** do `LOWER` chỉ xuất hiện ở biểu thức truy vấn.

### 8.2. Sắp xếp theo độ dài chuỗi

Ví dụ:

```sql
SELECT order_id, customer_name
FROM sales_orders
ORDER BY LENGTH(customer_name) DESC,
         LOWER(customer_name) ASC,
         order_id ASC;
```

Truy vấn ưu tiên tên có độ dài lớn hơn; nếu bằng độ dài, dùng tên chữ thường; nếu vẫn bằng thì dùng ID. Cú pháp và cách đếm ký tự ở các DBMS có thể khác nhau, đặc biệt với ký tự Unicode và kiểu dữ liệu đặc thù.

### 8.3. Sắp xếp theo thành phần ngày

Ví dụ PostgreSQL, ưu tiên các đơn theo **tháng trong năm**, rồi theo ngày:

```sql
SELECT order_id, created_on
FROM sales_orders
ORDER BY EXTRACT(MONTH FROM created_on) ASC,
         created_on ASC,
         order_id ASC;
```

`EXTRACT(MONTH FROM created_on)` lấy giá trị tháng. Đây **không phải** thứ tự thời gian đầy đủ nếu dữ liệu có nhiều năm: đơn tháng 1/2026 có thể đứng trước đơn tháng 12/2025 khi chỉ xếp theo số tháng. Nếu mục tiêu là cũ nhất đến mới nhất, `ORDER BY created_on ASC` trực tiếp mới rõ ràng.

### 8.4. Có thể sắp xếp theo cột không hiển thị

Trong truy vấn `SELECT` thông thường, có thể chọn ít cột nhưng sắp xếp theo cột khác:

```sql
SELECT order_id, customer_name
FROM sales_orders
ORDER BY created_on DESC, order_id DESC;
```

`created_on` dùng để xếp thứ tự dù không được hiển thị. Tuy nhiên, các truy vấn dùng `DISTINCT`, `UNION` hoặc cấu trúc tập hợp có thể áp đặt quy tắc riêng lên biểu thức `ORDER BY`; với chúng, cần kiểm tra cú pháp của DBMS và vị trí sắp xếp tương ứng.

## 9. NULL xuất hiện ở đâu trong thứ tự?

`NULL` biểu thị giá trị thiếu hoặc chưa biết. Trong bảng mẫu, đơn 102, 104 và 107 có `rating = NULL`. Khi `ORDER BY rating`, cần cân nhắc **những đơn chưa được đánh giá sẽ đứng đầu hay cuối**.

PostgreSQL hỗ trợ:

```sql
SELECT order_id, rating
FROM sales_orders
ORDER BY rating DESC NULLS LAST, order_id ASC;
```

Kết quả:

| order_id | rating |
|---:|---:|
| 101 | 5.0 |
| 106 | 5.0 |
| 103 | 4.0 |
| 108 | 4.0 |
| 105 | 3.0 |
| 102 | `NULL` |
| 104 | `NULL` |
| 107 | `NULL` |

- `DESC` đặt điểm cao trước.
- `NULLS LAST` đẩy các điểm chưa có về cuối.
- `order_id ASC` cố định thứ tự trong những hàng có cùng điểm hoặc cùng `NULL`.

Trong **PostgreSQL**, khi không ghi rõ, `ASC` mặc định xem `NULL` nằm **cuối**, còn `DESC` mặc định xem `NULL` nằm **đầu**. Những DBMS khác có thể sử dụng quy tắc khác; **không nên dựa vào mặc định** nếu vị trí `NULL` ảnh hưởng kết quả nghiệp vụ hoặc giao diện.

### 9.1. Dùng CASE để điều khiển NULL theo cách dễ chuyển hệ

Khi DBMS không hỗ trợ trực tiếp cú pháp `NULLS LAST` hoặc cần viết rõ ý định:

```sql
SELECT order_id, rating
FROM sales_orders
ORDER BY
    CASE WHEN rating IS NULL THEN 1 ELSE 0 END ASC,
    rating DESC,
    order_id ASC;
```

Khóa thứ nhất là 0 đối với hàng đã có điểm và 1 đối với hàng chưa có điểm, nên mọi `NULL` được đưa xuống cuối. Khóa thứ hai sắp xếp điểm đã biết từ cao đến thấp. Khóa ID bảo đảm thứ tự xác định. Truy vấn cho cùng thứ tự với ví dụ `DESC NULLS LAST` trên.

### 9.2. COALESCE thay thế NULL theo quy tắc riêng

Có thể viết:

```sql
SELECT order_id, rating
FROM sales_orders
ORDER BY COALESCE(rating, 0) DESC, order_id ASC;
```

`COALESCE(rating, 0)` tạo khóa sắp xếp bằng 0 khi `rating` thiếu. Với dữ liệu mẫu, vì các điểm đã biết đều lớn hơn 0, thứ tự gần giống ví dụ trên. Nhưng về **ngữ nghĩa**, “chưa có điểm” khác “đã được chấm 0 điểm”. Nếu xuất hiện hàng có `rating = 0`, cách viết `COALESCE` sẽ xếp nó cùng mức với hàng thiếu điểm. Dùng `CASE` hoặc `NULLS FIRST/LAST` khi cần giữ hai loại đó tách biệt.

## 10. Sắp xếp kết quả GROUP BY theo giá trị tổng hợp

`ORDER BY` không chỉ dùng cho từng hàng chi tiết. Sau `GROUP BY`, ta có thể xếp các **nhóm** theo `COUNT`, `SUM` hoặc `AVG`.

Ví dụ tổng giá trị đơn của từng khách:

```sql
SELECT
    customer_name,
    COUNT(*) AS order_count,
    SUM(unit_price * quantity - discount_amount) AS total_value
FROM sales_orders
GROUP BY customer_name
ORDER BY total_value DESC, customer_name ASC;
```

| customer_name | order_count | total_value |
|---|---:|---:|
| Binh | 2 | 500000.00 |
| Chi | 2 | 500000.00 |
| An | 2 | 480000.00 |
| Dung | 1 | 300000.00 |
| Em | 1 | 100000.00 |

Hai khách có tổng 500.000 được phân định theo tên tăng dần. `total_value` là **bí danh của `SUM(...)`** và có thể được dùng trong `ORDER BY`. Truy vấn này tính **mọi đơn trong bảng**, kể cả đơn đã hủy. Nếu yêu cầu là “xếp hạng theo doanh thu đã thanh toán”, cần lọc trạng thái trước khi nhóm:

```sql
SELECT
    customer_name,
    SUM(unit_price * quantity - discount_amount) AS paid_value
FROM sales_orders
WHERE status = 'PAID'
GROUP BY customer_name
ORDER BY paid_value DESC, customer_name ASC;
```

Kết quả sẽ gồm **An: 480.000**, **Chi: 300.000**, **Binh: 200.000**, **Em: 100.000**. Dung không có đơn `PAID` nên không xuất hiện.

Phân biệt vai trò:

- `WHERE` lọc **hàng** trước khi tạo nhóm.
- `GROUP BY` gom hàng và tính tổng hợp.
- `HAVING` (nếu có) lọc **nhóm** dựa trên điều kiện.
- `ORDER BY` sắp xếp các nhóm cuối cùng.

Ví dụ tìm khách có ít nhất hai đơn rồi xếp theo số lượng giảm dần:

```sql
SELECT customer_name, COUNT(*) AS order_count
FROM sales_orders
GROUP BY customer_name
HAVING COUNT(*) >= 2
ORDER BY order_count DESC, customer_name ASC;
```

Kết quả gồm **An, Binh, Chi**, mỗi người 2 đơn. Thứ tự tên phân định các nhóm bằng số lượng.

## 11. ORDER BY là nền tảng của phân trang

Khi bảng lớn, giao diện thường chỉ hiển thị 10 hoặc 20 hàng một lần. Nếu không có thứ tự xác định, một hàng có thể xuất hiện trên nhiều trang hoặc bị bỏ sót ngay cả khi dữ liệu không đổi, vì DBMS được phép trả hàng theo các thứ tự khác nhau.

### 11.1. LIMIT và OFFSET

Trong PostgreSQL, MySQL và SQLite, cách phân trang phổ biến là:

```sql
SELECT order_id, customer_name, created_on
FROM sales_orders
ORDER BY created_on DESC, order_id DESC
LIMIT 3 OFFSET 0;
```

Đây là **trang 1**, ba đơn mới nhất theo thứ tự đã định: **108, 107, 106**.

Trang 2:

```sql
SELECT order_id, customer_name, created_on
FROM sales_orders
ORDER BY created_on DESC, order_id DESC
LIMIT 3 OFFSET 3;
```

Kết quả: **105, 104, 103**.

Trang 3:

```sql
SELECT order_id, customer_name, created_on
FROM sales_orders
ORDER BY created_on DESC, order_id DESC
LIMIT 3 OFFSET 6;
```

Kết quả: **102, 101**.

Ý nghĩa của cú pháp:

- `LIMIT 3`: lấy tối đa ba hàng trong kết quả đã được sắp xếp.
- `OFFSET 3`: bỏ qua ba hàng đầu, rồi bắt đầu lấy.
- Nếu kích thước trang là `page_size` và đánh số trang bắt đầu từ 1, `OFFSET = (page_number - 1) * page_size`.

Chẳng hạn, trang 2 với kích thước 3 có `OFFSET = (2 - 1) * 3 = 3`.

**Các DBMS có cú pháp phân trang khác nhau.** Ví dụ SQL tiêu chuẩn và SQL Server hỗ trợ dạng `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` ở các phiên bản thích hợp:

```sql
SELECT order_id, created_on
FROM sales_orders
ORDER BY created_on DESC, order_id DESC
OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY;
```

Thứ tự diễn giải là **lọc → tạo kết quả → sắp xếp → lấy trang** (khái quát). Việc SQL sắp xếp ở bước nào về mặt vật lý do bộ tối ưu quyết định; ứng dụng chỉ cần phụ thuộc **thứ tự kết quả mà `ORDER BY` cam kết**.

### 11.2. Vì sao khóa phụ quan trọng trong phân trang?

Giả sử viết:

```sql
ORDER BY created_on DESC
LIMIT 3 OFFSET 0
```

Ngày 6/2 có hai đơn (107, 108), ngày 4/2 cũng có hai đơn (104, 105), ngày 2/2 cũng có hai đơn (102, 103). Nếu chỉ sắp theo ngày, thứ tự **trong cùng một ngày** không được xác định. Các lần truy vấn khác nhau có thể đặt các hàng cùng ngày theo thứ tự khác nhau.

Thêm:

```sql
ORDER BY created_on DESC, order_id DESC
```

`order_id` là duy nhất, nên có một thứ tự tổng thể xác định cho **cùng một trạng thái dữ liệu**, giúp việc chia trang ổn định hơn.

### 11.3. Dữ liệu thay đổi giữa hai lần tải trang

Ngay cả khi có khóa phân định duy nhất, `OFFSET` vẫn có một vấn đề: nếu có đơn mới xuất hiện ở đầu danh sách giữa lúc tải trang 1 và trang 2, vị trí của các hàng cũ sẽ dịch xuống. Khi đó trang 2 có thể **lặp lại một hàng ở trang 1**. Nếu một hàng ở đầu danh sách bị xóa, một hàng có thể bị **bỏ qua**.

Ví dụ ở trạng thái ban đầu, trang 1 là **108, 107, 106**. Giả sử sau đó có đơn mới với ngày muộn hơn mọi đơn mẫu. Danh sách thay đổi và `OFFSET 3` có thể bắt đầu ở **106**, làm đơn này xuất hiện lại ở trang 2.

Đây là tác động của **dữ liệu thay đổi giữa các truy vấn**, không phải lỗi của `ASC` hay `DESC`.

### 11.4. Phân trang theo khóa (keyset/cursor pagination)

Thay vì nói “bỏ qua ba hàng”, có thể nói “lấy những đơn **đứng sau khóa cuối của trang trước**”.

Với thứ tự:

```sql
ORDER BY created_on DESC, order_id DESC
```

Trang 1 kết thúc ở đơn **106**, có `created_on = DATE '2025-02-05'`. Trang tiếp theo có thể dùng điều kiện:

```sql
SELECT order_id, customer_name, created_on
FROM sales_orders
WHERE created_on < DATE '2025-02-05'
   OR (created_on = DATE '2025-02-05' AND order_id < 106)
ORDER BY created_on DESC, order_id DESC
LIMIT 3;
```

Kết quả: **105, 104, 103**, đúng các hàng tiếp theo theo thứ tự đã chọn.

Tại sao cần hai vế?

- `created_on < DATE '2025-02-05'` lấy mọi đơn có ngày **cũ hơn** ngày của khóa cuối trang trước.
- `created_on = DATE '2025-02-05' AND order_id < 106` lấy các đơn **cùng ngày nhưng có ID nhỏ hơn** 106, nếu có.

Đây là ví dụ về **keyset pagination**, thường có ích với danh sách rất dài và dữ liệu liên tục được thêm ở đầu. Keyset hạn chế việc các bản ghi cũ bị dồn vị trí do những bản ghi mới **đứng trước con trỏ**. Tuy vậy, nếu một hàng bị sửa khóa sắp xếp hoặc biến mất, hoặc nếu có cập nhật giữa các lần gọi, kết quả vẫn có thể thay đổi; khi cần **ảnh chụp dữ liệu chính xác tuyệt đối**, còn phải xem xét snapshot/transaction và yêu cầu nhất quán của ứng dụng.

**Khi phân trang theo nhiều khóa, cursor phải ghi đủ các khóa dùng trong `ORDER BY`.** Nếu bỏ `order_id` khỏi điều kiện tiếp trang, những đơn có cùng ngày với hàng cuối trang trước có thể bị bỏ sót. Nếu sắp theo biểu thức, cursor cần phản ánh **giá trị biểu thức và quy tắc `NULL`** mà truy vấn dùng.

## 12. Chi phí thực thi và chỉ mục

Việc sắp xếp có thể tiêu tốn CPU, bộ nhớ và đôi khi cần vùng lưu trữ tạm khi số hàng lớn. DBMS có bộ tối ưu để chọn kế hoạch phù hợp; không nên mặc định mọi `ORDER BY` đều phải quét và sắp toàn bộ bảng hoặc mọi chỉ mục đều được sử dụng.

### 12.1. Chỉ mục có thể hỗ trợ thứ tự

Trên PostgreSQL, một chỉ mục phù hợp với yêu cầu sắp xếp thường xuyên có thể hữu ích:

```sql
CREATE INDEX idx_sales_orders_created_id
ON sales_orders (created_on DESC, order_id DESC);
```

Chỉ mục này phù hợp về thứ tự khóa với:

```sql
SELECT order_id, created_on
FROM sales_orders
ORDER BY created_on DESC, order_id DESC
LIMIT 20;
```

Tuy nhiên, DBMS có thể chọn một kế hoạch khác dựa trên số lượng bản ghi, `WHERE`, thống kê và chi phí truy cập. Chỉ mục cũng làm tăng chi phí ghi và chiếm dung lượng; không cần tạo chỉ mục chỉ để tối ưu bảng mẫu tám hàng.

### 12.2. Biểu thức sắp xếp có thể cần hỗ trợ riêng

Chỉ mục trên `customer_name` không nhất thiết hỗ trợ trực tiếp một truy vấn sắp xếp bằng `LOWER(customer_name)`. PostgreSQL hỗ trợ chỉ mục biểu thức:

```sql
CREATE INDEX idx_sales_orders_lower_customer
ON sales_orders (LOWER(customer_name), order_id);
```

Đó là một lựa chọn khi các truy vấn theo `LOWER(customer_name)` xảy ra thường xuyên và bộ tối ưu có thể hưởng lợi. Điều kiện lọc, collation và thứ tự khóa đều ảnh hưởng khả năng sử dụng chỉ mục.

### 12.3. Kiểm tra kế hoạch trước khi tối ưu

PostgreSQL có `EXPLAIN` để xem kế hoạch:

```sql
EXPLAIN
SELECT order_id, created_on
FROM sales_orders
ORDER BY created_on DESC, order_id DESC
LIMIT 20;
```

Chỉ xem `EXPLAIN` chưa chứng minh truy vấn chạy nhanh hay chậm trong sản xuất. Khi tối ưu thật, cần dữ liệu đại diện, số liệu thời gian thực thi và lượng tài nguyên. `EXPLAIN ANALYZE` thực thi câu truy vấn để đo đạc, nên cần dùng thận trọng với các câu lệnh thay đổi dữ liệu và môi trường thật.

### 12.4. OFFSET lớn có thể tốn kém

Với `LIMIT 20 OFFSET 100000`, DBMS có thể vẫn phải tìm/đi qua nhiều hàng trước khi trả trang cần lấy, dù có chỉ mục. Nếu giao diện chủ yếu là “trang sau” trên dòng thời gian hoặc feed, keyset pagination thường đáng cân nhắc. Nếu người dùng cần nhảy đến số trang bất kỳ, `LIMIT/OFFSET` vẫn có thể phù hợp; chọn cách dựa trên yêu cầu thực tế.

## 13. Lỗi thường gặp khi sắp xếp

**“Không cần ORDER BY vì dữ liệu đang xuất hiện đúng thứ tự.”** Thứ tự ngẫu nhiên hoặc thứ tự do kế hoạch thực thi tạo ra không có bảo đảm. Chỉ `ORDER BY` mới mô tả thứ tự đầu ra mong muốn.

**“ASC/DESC áp dụng cho mọi cột phía sau.”** Mỗi từ khóa hướng gắn với **biểu thức ngay trước nó**. `ORDER BY a DESC, b ASC` không giống `ORDER BY a DESC, b DESC`.

**“Sắp theo ngày là đủ để phân trang ổn định.”** Nhiều hàng có cùng ngày; thêm khóa duy nhất như `order_id` để phân định thứ tự.

**“ORDER BY price DESC và ORDER BY price * quantity DESC như nhau.”** Một bên là đơn giá, một bên là giá trước giảm giá của toàn đơn; phải dùng đại lượng đúng nghiệp vụ.

**“Bí danh ở SELECT dùng ở mọi nơi.”** Bí danh đầu ra thường dùng được trong `ORDER BY`, nhưng không dùng trực tiếp trong `WHERE` cùng cấp của PostgreSQL. Hãy lặp biểu thức hoặc dùng CTE/bảng dẫn xuất khi cần.

**“NULL được sắp cuối ở mọi DBMS.”** Quy tắc mặc định khác nhau; xác định rõ bằng `NULLS LAST` nơi hỗ trợ hoặc `CASE` để kiểm soát vị trí.

**“LOWER luôn giải quyết mọi khác biệt khi sắp tên tiếng Việt.”** `LOWER` xử lý chữ hoa/thường theo quy tắc của DBMS, nhưng collation vẫn quyết định cách đối chiếu chữ và dấu. Những ứng dụng cần thứ tự ngôn ngữ cụ thể phải cấu hình và kiểm tra phù hợp.

**“LIMIT/OFFSET luôn không bỏ sót hàng.”** Khi bảng thay đổi giữa các lần tải, các hàng có thể dịch vị trí. Khóa phân định duy nhất và keyset pagination giảm những vấn đề khác nhau, nhưng không thay thế hoàn toàn kiểm soát tính nhất quán.

**“Có chỉ mục là ORDER BY chắc chắn rất nhanh.”** Hiệu năng phụ thuộc điều kiện lọc, thứ tự khóa, cardinality, kế hoạch truy vấn và lượng dữ liệu; cần đo thực tế trước khi kết luận.

## 14. Bài tập tự thực hành

Dùng bảng `sales_orders` ở mục 2. Hãy dự đoán **thứ tự `order_id`** trước khi chạy.

### Bài 1 — ASC và DESC

```sql
SELECT order_id, created_on
FROM sales_orders
ORDER BY created_on DESC, order_id ASC;
```

**Đáp án:** **107, 108, 106, 104, 105, 102, 103, 101**. Ngày 6/2 đứng trước ngày 5/2; trong cùng ngày 6/2, ID 107 nhỏ hơn 108 nên đứng trước.

### Bài 2 — Khóa phụ và giá trị bằng nhau

```sql
SELECT order_id,
       unit_price * quantity - discount_amount AS order_amount
FROM sales_orders
ORDER BY order_amount DESC, order_id DESC;
```

**Đáp án:** **105, 103, 102, 101, 107, 106, 104, 108**. Trong nhóm 300.000, ID giảm dần là 105, 103, 102; trong nhóm 200.000, ID giảm dần là 107, 106, 104.

### Bài 3 — Ưu tiên trạng thái

Viết truy vấn hiển thị **NEW trước, PAID sau, CANCELLED cuối**; trong cùng trạng thái, đơn mới hơn trước, nếu cùng ngày thì ID lớn hơn trước.

Gợi ý:

```sql
SELECT order_id, status, created_on
FROM sales_orders
ORDER BY
    CASE status
        WHEN 'NEW' THEN 1
        WHEN 'PAID' THEN 2
        WHEN 'CANCELLED' THEN 3
        ELSE 4
    END,
    created_on DESC,
    order_id DESC;
```

**Đáp án theo ID:** **107, 102, 108, 106, 104, 103, 101, 105**.

### Bài 4 — Đưa điểm chưa biết xuống cuối

Yêu cầu: xếp điểm đánh giá từ cao xuống thấp; đơn chưa có điểm xuống cuối; nếu cùng điểm thì ID nhỏ hơn trước.

```sql
SELECT order_id, rating
FROM sales_orders
ORDER BY rating DESC NULLS LAST, order_id ASC;
```

**Đáp án theo ID:** **101, 106, 103, 108, 105, 102, 104, 107**. Hãy tự viết lại bằng `CASE WHEN rating IS NULL THEN 1 ELSE 0 END` để nhận cùng kết quả.

### Bài 5 — Tạo trang kết quả ổn định

Với `ORDER BY created_on DESC, order_id DESC` và mỗi trang chứa **3 đơn**, hãy viết câu SQL cho **trang 2** theo hai cách:

1. `LIMIT 3 OFFSET 3`.
2. Keyset pagination, dùng khóa cuối trang 1 là `(created_on = DATE '2025-02-05', order_id = 106)`.

**Đáp án:** cả hai trả **105, 104, 103** nếu dữ liệu chưa đổi. Hãy giải thích vì sao keyset có thể giảm lỗi lặp trang khi một đơn mới được chèn trước vị trí con trỏ.

### Bài 6 — Sắp xếp nhóm sau khi lọc

Viết truy vấn đếm số **đơn đã thanh toán của từng khách**, sắp xếp số lượng giảm dần và tên khách tăng dần.

```sql
SELECT customer_name, COUNT(*) AS paid_order_count
FROM sales_orders
WHERE status = 'PAID'
GROUP BY customer_name
ORDER BY paid_order_count DESC, customer_name ASC;
```

**Đáp án:** **An: 2; Binh: 1; Chi: 1; Em: 1**. Dung không có đơn đã thanh toán. `customer_name ASC` phân định ba khách có cùng số lượng 1.

## Kết luận

**`ORDER BY`** quy định thứ tự kết quả truy vấn. **`ASC`** sắp tăng dần, **`DESC`** sắp giảm dần, và mỗi khóa trong danh sách có thể chọn hướng độc lập. Bằng cách dùng **nhiều khóa**, nhất là một khóa duy nhất ở cuối, ta tạo được thứ tự xác định khi các hàng có cùng ngày, giá trị hoặc trạng thái.

SQL còn cho phép sắp xếp theo **biểu thức tính toán**, **bí danh**, **`CASE`**, **hàm văn bản/ngày** và **giá trị tổng hợp**. Cần xử lý `NULL` rõ ràng và chọn khóa phản ánh đúng ý nghĩa nghiệp vụ. Khi phân trang, hãy đặt thứ tự ổn định trước `LIMIT/OFFSET`, đồng thời cân nhắc **keyset pagination** cho danh sách dài hoặc thường xuyên thay đổi. Những nguyên tắc đó giúp kết quả SQL dễ dự đoán, dễ kiểm chứng và phục vụ giao diện sử dụng thực tế.
