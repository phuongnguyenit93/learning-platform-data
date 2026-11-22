# Phụ thuộc hàm, ANY_VALUE và ý nghĩa tính đúng của kết quả

Khi viết truy vấn thống kê, ta thường nhóm nhiều dòng bằng `GROUP BY` rồi tính `COUNT()`, `SUM()` hoặc `MAX()`. Vấn đề xuất hiện khi câu `SELECT` còn lấy thêm một cột không nằm trong `GROUP BY` và cũng không được tổng hợp. MySQL cần biết giá trị nào đại diện cho mỗi nhóm. Nếu không có quy tắc xác định, kết quả có thể phụ thuộc vào dòng mà máy chủ tình cờ chọn.

MySQL dùng SQL mode `ONLY_FULL_GROUP_BY` để kiểm tra trường hợp này. Tuy nhiên, không phải cột nào không xuất hiện trong `GROUP BY` cũng bị từ chối: nếu cột đó phụ thuộc hàm vào khóa nhóm, MySQL có thể chứng minh rằng mỗi nhóm chỉ có một giá trị hợp lệ. Hàm `ANY_VALUE()` cho phép chấp nhận một giá trị bất kỳ khi người viết truy vấn thực sự không cần chọn một giá trị cụ thể. Hiểu ba khái niệm này giúp kết quả thống kê trong **DATABASE_MYSQL** đúng về mặt nghiệp vụ, không chỉ chạy mà không báo lỗi.

## 1. Ngữ nghĩa của `GROUP BY`

`GROUP BY` chia các dòng đầu vào thành các nhóm theo giá trị của một hoặc nhiều biểu thức. Mỗi nhóm tạo ra một dòng kết quả. Vì một nhóm có thể chứa nhiều dòng nguồn, những biểu thức được chọn phải có một giá trị xác định cho cả nhóm.

Ví dụ, bảng `orders` có nhiều đơn hàng của cùng một khách hàng:

```sql
SELECT customer_id, COUNT(*) AS order_count, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
```

Truy vấn hợp lệ vì `customer_id` là khóa nhóm và `COUNT()`/`SUM()` tính ra một giá trị cho từng nhóm. Kết quả có đúng một dòng cho mỗi `customer_id`.

Giả sử ta bổ sung `order_id`:

```sql
SELECT customer_id, order_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
```

Một khách hàng có thể có nhiều `order_id`. `customer_id` không xác định duy nhất `order_id`, và `order_id` cũng không được tổng hợp. MySQL không có căn cứ để chọn đơn hàng nào đại diện cho khách hàng đó. Với `ONLY_FULL_GROUP_BY`, truy vấn thường bị từ chối bằng lỗi 1055.

Không thể sửa ý nghĩa của truy vấn bằng cách thêm `ORDER BY order_id`:

```sql
SELECT customer_id, order_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id
ORDER BY order_id DESC;
```

`ORDER BY` sắp xếp các dòng kết quả sau khi nhóm đã được hình thành. Nó không quy định dòng nguồn nào được chọn làm `order_id` cho mỗi nhóm.

## 2. `ONLY_FULL_GROUP_BY` kiểm tra điều gì?

`ONLY_FULL_GROUP_BY` là một thành phần của biến `sql_mode`. Khi được bật, MySQL từ chối truy vấn tổng hợp nếu phần `SELECT`, `HAVING` hoặc `ORDER BY` tham chiếu một cột không được nhóm và cũng không được chứng minh là phụ thuộc hàm vào các cột nhóm, trừ trường hợp được bọc trong `ANY_VALUE()` hoặc được xử lý theo quy tắc hợp lệ khác.

Kiểm tra SQL mode của server và session:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;

SELECT FIND_IN_SET('ONLY_FULL_GROUP_BY', @@SESSION.sql_mode) > 0
    AS only_full_group_by_enabled;
```

SQL mode cấp `GLOBAL` là mặc định cho session mới; `SESSION` quyết định hành vi của kết nối hiện tại. Một ứng dụng dùng connection pool có thể tiếp tục dùng các session đã được tạo với cấu hình cũ sau khi giá trị global thay đổi.

`ONLY_FULL_GROUP_BY` được bật mặc định trong các bản MySQL hiện đại, bao gồm MySQL 5.7.5 trở lên và MySQL 8.0. Không nên tắt chế độ này chỉ để truy vấn cũ chạy được. Hãy kiểm tra truy vấn và xác định giá trị nào thực sự đại diện cho mỗi nhóm.

Ví dụ lỗi thường gặp:

```sql
SELECT customer_id, order_id, SUM(total_amount)
FROM orders
GROUP BY customer_id;
```

Thông báo lỗi 1055 cho biết `order_id` không nằm trong `GROUP BY`, không được tổng hợp và không phụ thuộc hàm vào khóa nhóm theo cách MySQL nhận diện. Đây là dấu hiệu truy vấn chưa xác định rõ giá trị `order_id` cần trả về.

## 3. Phụ thuộc hàm là gì?

Trong mô hình quan hệ, một tập thuộc tính `X` xác định tập thuộc tính `Y` (viết `X -> Y`) nếu mỗi giá trị `X` chỉ có thể đi cùng một giá trị `Y` trong mọi trạng thái dữ liệu hợp lệ theo các ràng buộc của schema.

Ví dụ bảng khách hàng:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(255) NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
);
```

Các ràng buộc cho biết:

- `customer_id` là khóa chính, nên `customer_id -> email, customer_name`.
- `email` là `UNIQUE NOT NULL`, nên `email -> customer_id, customer_name`.

Nếu `customer_id` được dùng làm khóa nhóm, tên khách hàng là duy nhất trong mỗi nhóm. Ta không cần thêm `customer_name` vào `GROUP BY` chỉ để hợp thức hóa truy vấn:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    SUM(o.total_amount) AS revenue
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
```

MySQL có thể nhận ra `c.customer_name` phụ thuộc hàm vào khóa chính `c.customer_id`. Mỗi nhóm khách hàng chỉ có một tên khách hàng, dù có nhiều đơn hàng được nối vào nhóm đó.

Điểm cốt yếu là phụ thuộc hàm phải được bảo đảm bởi cấu trúc và ràng buộc dữ liệu, không chỉ đúng tình cờ trong vài dòng hiện tại. Nếu hôm nay mỗi thành phố có một tên vùng nhưng schema không bảo đảm điều đó, không thể dựa vào dữ liệu mẫu để khẳng định `city -> region`.

## 4. MySQL nhận diện phụ thuộc hàm từ khóa như thế nào?

Trong các phiên bản MySQL hiện đại, `ONLY_FULL_GROUP_BY` có thể nhận diện một số phụ thuộc hàm phổ biến, đặc biệt là phụ thuộc được bảo đảm bởi khóa chính hoặc khóa `UNIQUE NOT NULL`.

### Khóa chính

Nếu `GROUP BY` chứa toàn bộ khóa chính của một bảng, các cột còn lại của chính bảng đó được xác định duy nhất:

```sql
SELECT customer_id, customer_name, email
FROM customers
GROUP BY customer_id;
```

Vì `customer_id` là khóa chính, mỗi nhóm có tối đa một dòng khách hàng. Các cột `customer_name` và `email` có giá trị duy nhất trong nhóm.

### Khóa `UNIQUE NOT NULL`

Một khóa duy nhất không cho phép `NULL` cũng có thể chứng minh phụ thuộc hàm:

```sql
SELECT email, customer_id, customer_name
FROM customers
GROUP BY email;
```

Ở ví dụ schema trên, `email` là `UNIQUE NOT NULL`, nên mỗi email xác định một khách hàng.

Nếu khóa `UNIQUE` cho phép `NULL`, cần cẩn thận: MySQL cho phép nhiều dòng có `NULL` trong một unique index. Do đó, cột nullable đó không luôn xác định duy nhất một dòng cho nhóm `NULL`; không nên xem nó như khóa duy nhất không null khi suy luận phụ thuộc hàm.

### Khóa ghép

Nếu unique key gồm nhiều cột, cần có đủ các thành phần của khóa để xác định dòng. Ví dụ:

```sql
CREATE TABLE course_enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    UNIQUE KEY uq_student_course (student_id, course_id)
);
```

Hai cột `(student_id, course_id)` cùng nhau xác định một dòng. Chỉ nhóm theo `student_id` thì chưa xác định `course_id` hoặc `status`; nhóm theo cả hai thành phần của unique key thì có thể xác định chúng.

```sql
SELECT student_id, course_id, enrolled_at, status
FROM course_enrollments
GROUP BY student_id, course_id;
```

### Phụ thuộc qua phép JOIN

MySQL cũng có thể nhận diện phụ thuộc hàm qua một số điều kiện nối. Ví dụ `orders.customer_id` tham chiếu đến `customers.customer_id`, và `customers.customer_id` là khóa chính. Khi nhóm theo khóa chính khách hàng, `customers.customer_name` vẫn là duy nhất cho nhóm đó.

Tuy nhiên, khả năng suy luận phụ thuộc hàm của MySQL có giới hạn theo cấu trúc truy vấn, biểu thức, outer join và phiên bản. Nếu một truy vấn phức tạp bị từ chối, hãy kiểm tra lại ràng buộc khóa và đơn giản hóa truy vấn hoặc tổng hợp ở subquery trước khi join. Không nên tắt `ONLY_FULL_GROUP_BY` để che một giả định dữ liệu chưa được bảo đảm.

## 5. `ANY_VALUE()` làm gì?

`ANY_VALUE(expr)` yêu cầu MySQL chấp nhận một giá trị bất kỳ của biểu thức trong nhóm mà không áp dụng kiểm tra `ONLY_FULL_GROUP_BY` cho biểu thức đó. Tên hàm mô tả chính xác cam kết của nó: *bất kỳ giá trị nào*.

Ví dụ, nếu báo cáo chỉ cần một nhãn bất kỳ để hiển thị tham khảo:

```sql
SELECT
    customer_id,
    ANY_VALUE(order_note) AS sample_note,
    COUNT(*) AS order_count
FROM orders
GROUP BY customer_id;
```

Truy vấn có thể chạy với `ONLY_FULL_GROUP_BY` vì `ANY_VALUE(order_note)` nói rõ rằng ứng dụng chấp nhận một ghi chú bất kỳ trong nhóm. Giá trị được chọn không có bảo đảm là ghi chú mới nhất, cũ nhất, dài nhất hoặc thuộc một đơn hàng cụ thể.

`ANY_VALUE()` không phải hàm tổng hợp như `SUM()`, `MIN()` hay `MAX()`. Nó không tính ra một đại lượng tổng hợp; nó chỉ loại bỏ yêu cầu chứng minh biểu thức có một giá trị duy nhất cho nhóm.

### Khi nào dùng được?

Chỉ dùng `ANY_VALUE()` khi mọi giá trị trong nhóm đều có thể chấp nhận được đối với mục đích truy vấn, hoặc khi nghiệp vụ thật sự không quan tâm giá trị cụ thể nào được trả về.

Nếu cột được kỳ vọng có cùng giá trị trong mọi dòng của nhóm, hãy ưu tiên mô hình hóa kỳ vọng đó bằng khóa, constraint hoặc phép tổng hợp có ý nghĩa. `ANY_VALUE()` không kiểm tra rằng các dòng trong nhóm có cùng giá trị.

### Khi nào không được dùng?

Không dùng `ANY_VALUE()` để giả vờ lấy cột từ dòng có giá trị `MAX()` hoặc `MIN()`:

```sql
-- KHÔNG bảo đảm order_id thuộc đơn hàng có amount lớn nhất
SELECT
    customer_id,
    ANY_VALUE(order_id) AS order_id,
    MAX(total_amount) AS max_amount
FROM orders
GROUP BY customer_id;
```

`MAX(total_amount)` tìm số tiền lớn nhất trong nhóm. `ANY_VALUE(order_id)` có thể trả về mã của một đơn hàng khác. Hai biểu thức không có quan hệ ghép cặp theo dòng nguồn.

Tương tự, không thể dùng `ANY_VALUE(created_at)` rồi kết luận đó là thời điểm mới nhất. Nếu cần mới nhất, phải dùng `MAX(created_at)`; nếu cần toàn bộ bản ghi mới nhất, phải chọn dòng theo thứ tự xác định.

## 6. Chọn đúng cách khi cần một dòng đại diện

Trước khi viết truy vấn, hãy xác định mục tiêu:

- Cần một giá trị tổng hợp: dùng `SUM`, `COUNT`, `MIN`, `MAX`, `AVG` hoặc hàm phù hợp.
- Cần một thuộc tính được xác định duy nhất bởi khóa nhóm: dựa vào khóa chính/unique key và để MySQL kiểm tra phụ thuộc hàm.
- Cần một giá trị bất kỳ và thực sự không quan tâm dòng nào: có thể dùng `ANY_VALUE()`.
- Cần bản ghi mới nhất, lớn nhất hoặc theo ưu tiên cụ thể: phải chọn dòng bằng thứ tự có quy tắc và tie-breaker.

### Cách 1: Dùng `ROW_NUMBER()` để chọn một dòng xác định

MySQL 8.0 hỗ trợ window function. Ví dụ, lấy đơn hàng có số tiền cao nhất của từng khách hàng; nếu bằng tiền, chọn đơn tạo gần đây hơn, sau đó dùng `order_id` làm tie-breaker:

```sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC,
                     created_at DESC,
                     order_id DESC
        ) AS row_num
    FROM orders
)
SELECT order_id, customer_id, total_amount, created_at
FROM ranked_orders
WHERE row_num = 1;
```

`ROW_NUMBER()` đánh số từng dòng trong mỗi nhóm. `row_num = 1` lấy đúng một dòng theo thứ tự đã định nghĩa. `order_id` cuối cùng giúp thứ tự vẫn xác định khi số tiền và thời điểm bằng nhau, giả sử `order_id` là duy nhất.

Nếu muốn lấy tất cả đơn hàng đồng hạng có số tiền cao nhất, dùng `RANK()` hoặc `DENSE_RANK()` với thứ tự chỉ theo `total_amount`, rồi lọc hạng bằng 1. Không thêm tie-breaker vào `ORDER BY` của `RANK()` nếu muốn giữ các dòng đồng hạng theo số tiền.

### Cách 2: JOIN với kết quả tổng hợp

Nếu chỉ cần tất cả các đơn hàng có số tiền cao nhất của từng khách hàng, có thể tính `MAX()` rồi join ngược:

```sql
WITH max_amount AS (
    SELECT customer_id, MAX(total_amount) AS max_total
    FROM orders
    GROUP BY customer_id
)
SELECT o.order_id, o.customer_id, o.total_amount, o.created_at
FROM orders AS o
JOIN max_amount AS m
  ON m.customer_id = o.customer_id
 AND m.max_total = o.total_amount;
```

Cách này trả về nhiều dòng nếu một khách hàng có nhiều đơn cùng số tiền lớn nhất. Đây là kết quả đúng nếu nghiệp vụ muốn giữ tất cả trường hợp đồng hạng. Nếu cần đúng một dòng, hãy bổ sung quy tắc tie-breaker hoặc dùng `ROW_NUMBER()`.

### Cách 3: Chỉ lấy giá trị tổng hợp nếu không cần dòng nguồn

Nếu báo cáo chỉ cần số tiền lớn nhất, không cần `order_id`, hãy truy vấn trực tiếp:

```sql
SELECT customer_id, MAX(total_amount) AS max_total
FROM orders
GROUP BY customer_id;
```

Đừng lấy thêm các cột không cần thiết. Truy vấn càng thể hiện đúng yêu cầu, kết quả càng dễ kiểm chứng.

## 7. Vì sao tắt `ONLY_FULL_GROUP_BY` không làm truy vấn đúng hơn?

Khi tắt `ONLY_FULL_GROUP_BY`, MySQL có thể chấp nhận truy vấn chọn cột không được nhóm hoặc tổng hợp. Nếu một nhóm có nhiều giá trị khác nhau, máy chủ được tự do chọn một giá trị trong nhóm. Việc chọn đó không được bảo đảm ổn định qua lần chạy, kế hoạch thực thi, index, phiên bản hoặc thay đổi dữ liệu.

Ví dụ:

```sql
SELECT customer_id, order_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
```

Nếu chế độ kiểm tra bị tắt, `order_id` được trả về có thể là một đơn hàng bất kỳ của khách hàng. Nó không mặc nhiên là đơn đầu tiên, đơn cuối cùng hoặc đơn có số tiền cao nhất.

Ngay cả khi truy vấn có:

```sql
ORDER BY order_id DESC
```

thì `ORDER BY` vẫn chỉ sắp xếp kết quả nhóm; nó không quyết định dòng nguồn đại diện. Nếu nghiệp vụ cần dòng cuối cùng, phải xác định dòng đó trong từng nhóm bằng window function hoặc truy vấn con có thứ tự và điều kiện rõ ràng.

Tắt mode có thể khiến lỗi logic khó phát hiện hơn vì câu SQL vẫn trả dữ liệu. Báo cáo doanh thu, trạng thái đơn, thông tin khách hàng hoặc số liệu đối soát có thể sai mà không có lỗi kỹ thuật.

## 8. Cách kiểm tra và làm rõ truy vấn hiện có

Khi gặp lỗi 1055 hoặc kết quả nhóm không đáng tin cậy, thực hiện lần lượt:

1. Xác định mỗi dòng kết quả đại diện cho một nhóm theo khóa nào.
2. Liệt kê các cột trong `SELECT`, `HAVING`, `ORDER BY` không nằm trong `GROUP BY` và không nằm trong hàm tổng hợp.
3. Với mỗi cột, chứng minh nó được xác định bởi khóa nhóm thông qua `PRIMARY KEY`, `UNIQUE NOT NULL` hoặc quan hệ khóa đã khai báo.
4. Nếu cần một dòng đại diện, viết rõ tiêu chí chọn dòng và quy tắc xử lý khi hòa.
5. Chỉ dùng `ANY_VALUE()` nếu giá trị bất kỳ thật sự đáp ứng yêu cầu nghiệp vụ.
6. Kiểm tra `ONLY_FULL_GROUP_BY` ở session mà ứng dụng thực sự sử dụng.
7. Thử với dữ liệu có nhiều dòng trong một nhóm, nhiều giá trị khác nhau và các trường hợp hòa; không chỉ kiểm tra nhóm có một dòng.

Có thể xem cấu trúc khóa của bảng bằng:

```sql
SHOW CREATE TABLE customers;
SHOW INDEX FROM customers;
```

Đây là căn cứ để xác định schema có bảo đảm phụ thuộc hàm hay không. Dữ liệu hiện tại tình cờ không có bản ghi trùng không thay thế được một constraint.

## 9. Bài tập thực hành

Giả sử có hai bảng `customers` và `orders`, trong đó `customers.customer_id` là khóa chính, còn `orders.order_id` là khóa chính và `orders.customer_id` tham chiếu khách hàng.

1. Viết truy vấn đếm số đơn hàng và tính doanh thu theo khách hàng.
2. Bổ sung `customers.customer_name` vào `SELECT`, chỉ nhóm theo `customer_id`; giải thích vì sao MySQL có thể chấp nhận nhờ phụ thuộc hàm từ khóa chính.
3. Bổ sung `orders.order_id` vào truy vấn nhóm; giải thích vì sao cột này không phụ thuộc hàm vào `customer_id`.
4. Dùng `ANY_VALUE(orders.order_id)` để làm truy vấn chạy, sau đó giải thích vì sao kết quả không đảm bảo là đơn hàng có doanh thu cao nhất.
5. Dùng `ROW_NUMBER()` để lấy đơn có `total_amount` cao nhất của mỗi khách hàng, có tie-breaker ổn định.
6. Dùng CTE với `MAX(total_amount)` rồi join ngược để lấy tất cả đơn đồng hạng; so sánh với kết quả `ROW_NUMBER()`.
7. Kiểm tra `@@SESSION.sql_mode` và xác minh truy vấn hợp lệ khi `ONLY_FULL_GROUP_BY` được bật.

Bạn hoàn thành bài khi phân biệt được một giá trị được xác định bởi khóa nhóm với một giá trị bất kỳ, giải thích được vai trò của `ONLY_FULL_GROUP_BY`, và chọn đúng giữa aggregate, `ANY_VALUE()`, phụ thuộc hàm hoặc truy vấn chọn dòng có thứ tự. Mục tiêu là bảo đảm mỗi giá trị trong báo cáo có ý nghĩa rõ ràng và có thể giải thích được.
