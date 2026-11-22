# IN, NOT IN và bẫy NULL trong truy vấn con

Khi cần tìm khách hàng đã từng đặt hàng, ta có thể dùng `IN` với một truy vấn con để kiểm tra `customer_id` có xuất hiện trong tập đơn hàng hay không. Khi cần tìm khách hàng chưa từng đặt hàng, `NOT IN` có vẻ là lựa chọn đối xứng. Nhưng nếu truy vấn con trả về chỉ một giá trị `NULL`, `NOT IN` có thể không trả về khách hàng nào dù nhiều khách hàng chưa từng đặt đơn.

Nguyên nhân nằm ở logic ba giá trị của SQL: `TRUE`, `FALSE` và `UNKNOWN`. Trong SQL, `NULL` biểu thị giá trị chưa biết hoặc không có; phép so sánh với `NULL` thường không cho kết quả `TRUE` hay `FALSE` mà là `UNKNOWN`. Bài học này thuộc module **DATABASE_MYSQL**, tập trung vào ngữ nghĩa của `IN`, `NOT IN`, cách `NULL` lan truyền trong truy vấn con và những cách viết anti-join an toàn.

## 1. IN kiểm tra sự tồn tại trong một tập giá trị

`IN` kiểm tra biểu thức bên trái có bằng một giá trị nào trong danh sách hoặc tập kết quả bên phải hay không.

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id IN (101, 205, 309);
```

Truy vấn trả về khách hàng có ID thuộc danh sách. Có thể dùng truy vấn con để tạo tập giá trị động:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id IN (
    SELECT customer_id
    FROM orders
    WHERE status = 'PAID'
);
```

Ý nghĩa: lấy khách hàng có `customer_id` xuất hiện trong ít nhất một đơn hàng đã thanh toán. Các giá trị trùng lặp trong kết quả truy vấn con không làm thay đổi kết quả membership; `IN` chỉ cần biết có ít nhất một giá trị khớp.

Truy vấn con dùng với `IN` phải trả về một cột nếu so sánh một biểu thức đơn. MySQL cũng hỗ trợ so sánh tuple nhiều cột trong những trường hợp phù hợp, nhưng ví dụ cơ bản thường dùng một cột.

## 2. NOT IN là phủ định của IN

`NOT IN` kiểm tra biểu thức bên trái không bằng bất kỳ giá trị nào trong tập bên phải:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM orders
);
```

Mục đích thường là tìm khách hàng chưa có đơn hàng. Nếu `orders.customer_id` luôn `NOT NULL`, truy vấn này có thể thể hiện đúng ý định. Nhưng nếu cột đó cho phép `NULL`, cần xem xét kỹ ngữ nghĩa trước khi dùng.

Về logic, `IN` tương đương phép so sánh bằng với ít nhất một phần tử (`= ANY`); `NOT IN` tương đương khác mọi phần tử (`<> ALL`). Do đó, kết quả phụ thuộc cả vào việc có giá trị khớp lẫn việc tập bên phải có chứa `NULL` hay không.

## 3. SQL có ba giá trị logic

Trong SQL, biểu thức điều kiện không chỉ có `TRUE` và `FALSE`. Khi một phép so sánh không thể kết luận vì có `NULL`, kết quả là `UNKNOWN`.

Ví dụ:

```sql
SELECT
    10 = 10 AS is_equal,
    10 = 20 AS is_not_equal,
    10 = NULL AS compare_with_null,
    NULL = NULL AS compare_two_nulls;
```

Kết quả lần lượt là `1`, `0`, `NULL`, `NULL` trong cách hiển thị của MySQL. `NULL = NULL` không phải `TRUE`: hai giá trị đều chưa biết không có nghĩa chúng bằng nhau.

Trong mệnh đề `WHERE`, chỉ những hàng có điều kiện là `TRUE` được giữ lại. Cả `FALSE` và `UNKNOWN` đều bị loại:

```sql
SELECT customer_id
FROM customers
WHERE customer_id = NULL;
```

Truy vấn không trả hàng nào, kể cả khi cột có `NULL`. Muốn kiểm tra giá trị rỗng, phải viết:

```sql
SELECT customer_id
FROM customers
WHERE customer_id IS NULL;
```

Đây là nền tảng để hiểu vì sao một `NULL` trong truy vấn con có thể làm thay đổi kết quả `NOT IN`.

## 4. Bẫy NULL trong NOT IN

Giả sử `orders.customer_id` có một số hàng mang giá trị `NULL`. Khi chạy:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM orders
);
```

Với một khách hàng không có ID nào khớp trong tập đơn hàng, MySQL phải đánh giá liệu ID đó có khác mọi giá trị trong tập hay không. Khi tập có `NULL`, phép so sánh với giá trị `NULL` là `UNKNOWN`; vì thế toàn bộ điều kiện `NOT IN` có thể trở thành `UNKNOWN` thay vì `TRUE`.

Kết quả là những khách hàng chưa từng đặt đơn cũng bị loại khỏi kết quả. Đây là lỗi logic thường gặp: câu SQL hợp lệ và không báo lỗi, nhưng trả về tập kết quả rỗng hoặc thiếu dữ liệu.

### Ví dụ có thể tự chạy

Tạo dữ liệu thử nghiệm:

```sql
CREATE TEMPORARY TABLE demo_customers (
    customer_id INT PRIMARY KEY,
    full_name VARCHAR(50) NOT NULL
);

CREATE TEMPORARY TABLE demo_orders (
    order_id INT PRIMARY KEY,
    customer_id INT NULL
);

INSERT INTO demo_customers VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi');

INSERT INTO demo_orders VALUES
    (101, 1),
    (102, NULL);
```

Kiểm tra `NOT IN`:

```sql
SELECT customer_id, full_name
FROM demo_customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM demo_orders
);
```

Truy vấn không trả về `Binh` và `Chi`, dù hai khách hàng này không có đơn hàng khớp. Tập truy vấn con chứa `NULL` nên điều kiện của các ID không khớp bị đánh giá là `UNKNOWN`.

Nếu loại `NULL` khỏi tập con:

```sql
SELECT customer_id, full_name
FROM demo_customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM demo_orders
    WHERE customer_id IS NOT NULL
);
```

Kết quả lúc này gồm khách hàng `Binh` và `Chi`. Đây là cách sửa hợp lệ nếu ta đã xác định rõ `NULL` trong `orders.customer_id` không đại diện cho một khách hàng cần so khớp.

## 5. Bảng chân trị đơn giản cho IN và NOT IN

Giả sử biểu thức bên trái là `2` và xét các tập giá trị bên phải:

| Tập bên phải | `2 IN (tập)` | `2 NOT IN (tập)` | Giải thích |
|---|---|---|---|
| `(1, 3)` | `FALSE` | `TRUE` | Không có giá trị khớp và không có NULL |
| `(1, 2, 3)` | `TRUE` | `FALSE` | Có giá trị khớp |
| `(1, NULL, 3)` | `UNKNOWN` | `UNKNOWN` | Không khớp nhưng có phần tử chưa biết |
| `(2, NULL)` | `TRUE` | `FALSE` | Có giá trị khớp; kết quả IN đã xác định là TRUE |
| Tập rỗng | `FALSE` | `TRUE` | Không tồn tại phần tử nào để khớp hoặc phủ định |

Nếu biểu thức bên trái là `NULL` và tập bên phải không rỗng, phép so sánh membership thường là `UNKNOWN`; nếu tập bên phải rỗng, `IN` là `FALSE` và `NOT IN` là `TRUE` theo quy tắc logic của lượng từ trên tập rỗng.

Hai điểm quan trọng:

- Chỉ một `NULL` trong tập bên phải cũng đủ làm phép `NOT IN` của một giá trị không khớp trở thành `UNKNOWN`.
- Nếu có một giá trị khớp, `IN` là `TRUE` và `NOT IN` là `FALSE`, kể cả khi tập còn chứa `NULL`.

## 6. NOT EXISTS thường là lựa chọn an toàn cho anti-join

Nếu yêu cầu nghiệp vụ là “lấy các hàng ở bảng cha mà không tồn tại hàng liên quan ở bảng con”, `NOT EXISTS` thường diễn đạt trực tiếp và tránh bẫy `NULL` ở tập kết quả con.

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

MySQL kiểm tra từng khách hàng và giữ lại khách hàng nếu truy vấn con không tìm thấy đơn hàng nào thỏa điều kiện liên kết. Một hàng `orders.customer_id IS NULL` không làm phép so sánh `o.customer_id = c.customer_id` trở thành `TRUE`, nên nó không ngăn các khách hàng không liên quan xuất hiện.

`EXISTS` chỉ quan tâm truy vấn con có trả ít nhất một hàng hay không. Vì vậy, `SELECT 1` là đủ; không cần lấy các cột thật từ bảng con.

### Lưu ý khi cột ngoài có thể NULL

Nếu `c.customer_id` là khóa chính `NOT NULL`, ví dụ trên không gặp trường hợp khóa ngoài là `NULL`. Nếu biểu thức bên ngoài có thể `NULL`, `NOT EXISTS` với phép so sánh `=` sẽ xem không có dòng nào bằng `NULL`, nên hàng ngoài đó có thể được giữ lại.

Nếu nghiệp vụ muốn loại các hàng ngoài có khóa `NULL`, hãy nói rõ:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.customer_id = c.customer_id
  );
```

Nếu nghiệp vụ muốn `NULL` ở hai phía được xem là cùng một giá trị, MySQL có toán tử so sánh null-safe `<=>`:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM child_rows AS ch
    WHERE ch.reference_code <=> parent_rows.reference_code
)
```

Chỉ dùng `<=>` khi quy tắc nghiệp vụ thật sự coi hai giá trị `NULL` là tương đương. Với khóa ngoại thông thường, `NULL` thường biểu thị chưa có liên kết chứ không phải một khóa có thể ghép với `NULL` ở bảng cha.

## 7. Anti-join bằng LEFT JOIN ... IS NULL

Một cách viết khác để tìm hàng cha không có hàng con là `LEFT JOIN`, sau đó lọc những hàng không tìm được bản ghi con:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

`order_id` là khóa chính và không thể `NULL`, nên `o.order_id IS NULL` biểu thị không có hàng `orders` khớp. Hãy chọn một cột phía bảng con được bảo đảm `NOT NULL` làm dấu hiệu không khớp; không nên kiểm tra một cột con vốn cho phép `NULL` vì có thể nhầm hàng khớp có giá trị NULL với hàng không khớp.

`NOT EXISTS` và `LEFT JOIN ... IS NULL` thường biểu diễn cùng một anti-join nếu điều kiện nối và cột kiểm tra được chọn đúng. Optimizer có thể biến đổi chúng thành kế hoạch tương tự. Chọn cách viết dễ đọc, sau đó dùng `EXPLAIN` để kiểm tra hiệu năng trên dữ liệu thực tế.

## 8. Khi nào có thể dùng NOT IN an toàn?

`NOT IN` không phải lúc nào cũng sai. Nó phù hợp nếu cả hai điều kiện sau được bảo đảm:

1. Tập truy vấn con không thể chứa `NULL`.
2. Biểu thức bên trái không thể `NULL`, hoặc nghiệp vụ đã xác định rõ cách xử lý giá trị `NULL` bên ngoài.

Ví dụ, nếu `orders.customer_id` được khai báo `NOT NULL` và `customers.customer_id` là khóa chính `NOT NULL`, truy vấn sau có ngữ nghĩa rõ:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
```

Nếu cột con nullable nhưng muốn tiếp tục dùng `NOT IN`, có thể lọc NULL ở truy vấn con:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT o.customer_id
      FROM orders AS o
      WHERE o.customer_id IS NOT NULL
  );
```

Điều kiện `c.customer_id IS NOT NULL` chỉ cần nếu cột ngoài có thể NULL và nghiệp vụ không muốn giữ những hàng đó. Với khóa chính `NOT NULL`, điều kiện này dư thừa nhưng có thể giúp người đọc hiểu ý định.

Không chỉ kiểm tra dữ liệu hiện tại. Nếu schema cho phép `NULL`, một bản ghi mới trong tương lai có thể làm truy vấn `NOT IN` đổi kết quả. Ràng buộc `NOT NULL` là bảo đảm bền vững hơn một giả định dựa trên dữ liệu đang có.

## 9. IN, EXISTS và hiệu năng

`IN` phù hợp khi muốn kiểm tra một giá trị có thuộc tập kết quả hay không:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.status = 'PAID'
);
```

`EXISTS` phù hợp khi câu hỏi là có ít nhất một hàng liên quan:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Hai truy vấn trên có thể được optimizer chuyển thành semijoin hoặc một chiến lược tương đương. Không nên khẳng định `EXISTS` luôn nhanh hơn `IN` hoặc ngược lại. Hiệu năng phụ thuộc index, số dòng, độ chọn lọc, phiên bản và kế hoạch thực thi.

Với anti-join, so sánh `NOT EXISTS` và `NOT IN` chỉ sau khi xác nhận nullability và ý nghĩa nghiệp vụ. `NOT EXISTS` thường dễ giữ đúng ý định hơn khi cột truy vấn con nullable.

Các index thường hữu ích cho ví dụ:

```sql
CREATE INDEX idx_orders_customer_status
    ON orders (customer_id, status);
```

Thứ tự cột index cần dựa trên các điều kiện truy vấn thực tế. Với truy vấn lọc status trước và nối theo customer, index `(status, customer_id)` có thể phù hợp hơn. Hãy kiểm tra `EXPLAIN` thay vì tạo index theo công thức cố định.

## 10. Kiểm tra kiểu dữ liệu và collation trong truy vấn con

Hai phía của phép so sánh nên có kiểu dữ liệu tương thích. Nếu một bên là số và bên kia là chuỗi, MySQL có thể thực hiện implicit conversion. Với mã định danh dạng chuỗi, điều này có thể làm mất số 0 đầu hoặc khiến kết quả so sánh khác ý nghĩa mong muốn.

Ví dụ không nên dùng:

```sql
SELECT c.customer_code
FROM customers AS c
WHERE c.customer_code IN (
    SELECT o.customer_id
    FROM orders AS o
);
```

Nếu `customer_code` là `VARCHAR` còn `customer_id` là số nguyên, hãy xem lại mô hình dữ liệu. Mã định danh văn bản nên được so sánh với giá trị văn bản cùng quy tắc chuẩn hóa; ID số nên dùng kiểu số ở cả hai phía.

Với chuỗi, character set và collation ảnh hưởng đến phép so sánh. Ví dụ collation không phân biệt hoa/thường có thể xem `ABC` và `abc` là bằng nhau. Hãy chọn collation phù hợp với quy tắc nghiệp vụ của mã hoặc tên.

Tránh bọc cột được đánh index trong `CAST()` hoặc hàm chuyển đổi ở điều kiện nối nếu có thể. Ưu tiên chuẩn hóa kiểu dữ liệu ở schema hoặc chuyển tham số đầu vào sang kiểu của cột để optimizer có thể sử dụng index hiệu quả.

## 11. Đọc kế hoạch thực thi

Với truy vấn `IN`, `EXISTS` hoặc `NOT EXISTS`, dùng `EXPLAIN` để xem MySQL truy cập bảng nào, chọn index nào và ước lượng số hàng:

```sql
EXPLAIN
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Kiểm tra:

- Bảng `orders` có dùng index theo `customer_id` không.
- Ước lượng số dòng cần đọc có hợp lý không.
- Truy vấn con được chuyển thành anti-join hoặc chiến lược nào.
- Có phép quét toàn bảng không cần thiết hay không.

Trên MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` thực thi truy vấn và hiển thị số dòng/thời gian thực tế. Chỉ chạy trên môi trường phù hợp, vì đây là truy vấn thực sự được thực hiện chứ không chỉ mô tả kế hoạch.

## 12. Checklist tránh bẫy NULL

Trước khi dùng `NOT IN` với truy vấn con, hãy kiểm tra:

1. Cột được trả về từ truy vấn con có cho phép `NULL` không?
2. Truy vấn con có thể sinh `NULL` qua `LEFT JOIN`, biểu thức hoặc `UNION` không?
3. Biểu thức ở phía ngoài có thể `NULL` không?
4. Nếu có `NULL`, nghiệp vụ muốn xem nó là “không có liên kết”, “không xác định” hay một giá trị có thể so khớp?
5. Có thể diễn đạt ý định bằng `NOT EXISTS` rõ ràng hơn không?
6. Nếu dùng `LEFT JOIN ... IS NULL`, cột kiểm tra ở bảng con có chắc chắn `NOT NULL` không?
7. Hai phía có cùng kiểu dữ liệu, signedness, character set và collation phù hợp không?
8. Index và kế hoạch thực thi có đáp ứng khối lượng dữ liệu không?

## 13. Bài tập thực hành

Sử dụng hai bảng `demo_customers` và `demo_orders` ở phần ví dụ:

1. Chạy `IN` để tìm khách hàng có đơn hàng; thêm một hàng con có `customer_id = NULL` và quan sát kết quả.
2. Chạy `NOT IN` để tìm khách hàng chưa có đơn; quan sát cách một `NULL` trong truy vấn con làm kết quả thay đổi.
3. Thay `NOT IN` bằng `NOT EXISTS`; giải thích vì sao hàng con có `NULL` không làm mất khách hàng chưa có đơn.
4. Viết lại bằng `LEFT JOIN ... IS NULL`, dùng khóa chính `order_id` để kiểm tra hàng không khớp.
5. Thử thêm `WHERE customer_id IS NOT NULL` vào truy vấn con của `NOT IN` và so sánh kết quả.
6. Thử một biểu thức ngoài có giá trị `NULL`; giải thích khác biệt giữa `NOT IN` và `NOT EXISTS` khi khóa ngoài nullable.
7. So sánh `EXPLAIN` của `IN`, `EXISTS` và `NOT EXISTS` sau khi tạo index phù hợp.
8. Thử tập con rỗng và ghi lại kết quả của `IN` và `NOT IN`.

Bạn hoàn thành bài khi giải thích được vì sao `NOT IN` có thể trả kết quả rỗng chỉ vì truy vấn con chứa `NULL`, biết khi nào lọc `NULL`, khi nào dùng `NOT EXISTS` hoặc anti-join, và có thể chứng minh kết quả đúng bằng dữ liệu thử nghiệm. Hãy quyết định cách xử lý `NULL` theo ý nghĩa nghiệp vụ thay vì chỉ sửa câu SQL để hết lỗi.
