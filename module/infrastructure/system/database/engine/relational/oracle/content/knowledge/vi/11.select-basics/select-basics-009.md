# OFFSET, FETCH FIRST, WITH TIES và phân trang trong Oracle Database

Khi một bảng có hàng triệu bản ghi, ứng dụng thường không tải tất cả kết quả vào một lần. Thay vào đó, giao diện hiển thị từng trang: trang đầu 20 đơn hàng, trang kế tiếp 20 đơn hàng tiếp theo. Oracle hỗ trợ cú pháp **row limiting clause** với `OFFSET` và `FETCH FIRST/NEXT` để giới hạn kết quả truy vấn; tùy chọn `WITH TIES` giúp giữ lại toàn bộ các hàng đồng hạng tại ranh giới cuối. Nếu cần tương thích với phiên bản cũ, có thể dùng `ROWNUM` hoặc hàm phân tích `ROW_NUMBER()`.

Tuy nhiên, phân trang chỉ đúng khi bạn hiểu thứ tự sắp xếp. Một truy vấn có `FETCH FIRST 20 ROWS ONLY` nhưng không có `ORDER BY` không đảm bảo luôn trả cùng 20 hàng. Ngay cả khi có `ORDER BY`, nếu cột sắp xếp không duy nhất, các hàng đồng hạng có thể đổi vị trí giữa các lần chạy. Với dữ liệu thay đổi liên tục, `OFFSET` lớn còn có thể làm database phải đọc và bỏ qua rất nhiều hàng trước khi trả trang cần thiết.

Bài học thuộc nhóm **SELECT cơ bản** trong Oracle Database. Chúng ta sẽ học cú pháp, ý nghĩa của từng thành phần, cách xử lý ties, cách đếm tổng số hàng, phân trang bằng offset và keyset, cùng các lựa chọn thay thế cho hệ thống legacy.

Sau bài này, bạn có thể:

- Dùng `FETCH FIRST n ROWS ONLY` và `OFFSET n ROWS FETCH NEXT m ROWS ONLY`.
- Phân biệt `ONLY` với `WITH TIES` và hiểu ties được xác định theo toàn bộ `ORDER BY`.
- Thiết kế thứ tự sắp xếp ổn định bằng khóa duy nhất làm tie-breaker khi cần.
- Tạo trang kết quả có tổng số hàng bằng `COUNT(*) OVER()`.
- Chọn giữa offset pagination và keyset/seek pagination theo yêu cầu giao diện.
- Dùng `ROWNUM` hoặc `ROW_NUMBER()` khi làm việc với phiên bản Oracle cũ.
- Nhận diện ảnh hưởng của dữ liệu thay đổi giữa các request, NULL, index, bind variables và hiệu năng.

> **Phạm vi phiên bản:** `OFFSET ... FETCH` và `FETCH FIRST ... WITH TIES` là cú pháp row limiting clause được giới thiệu trong Oracle Database 12c Release 1 (12.1). Các ví dụ dùng SQL Oracle hiện đại; nếu triển khai trên 11g hoặc hệ thống tương thích cũ hơn, xem phần `ROWNUM`/`ROW_NUMBER()`. SQL lab chỉ dùng bảng do bạn tạo trong schema thực hành.

## 1. Tại sao cần giới hạn và phân trang kết quả?

Giả sử bảng `ORDERS` có 2 triệu đơn hàng. Giao diện cần hiển thị 25 đơn hàng mỗi trang, mới nhất trước. Thay vì tải 2 triệu hàng rồi cắt ở ứng dụng, ta yêu cầu database trả phần cần thiết:

~~~sql
SELECT order_id, customer_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 0 ROWS
FETCH NEXT 25 ROWS ONLY;
~~~

Truy vấn trên yêu cầu bỏ qua 0 hàng đầu tiên và lấy tối đa 25 hàng kế tiếp theo thứ tự đã sắp xếp.

Các thuật ngữ:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Result set** | Tập hàng do câu SELECT tạo ra sau khi áp dụng các điều kiện và phép xử lý truy vấn |
| **ORDER BY** | Xác định thứ tự hàng trước khi giới hạn |
| **OFFSET** | Số hàng đầu tiên trong thứ tự kết quả sẽ bị bỏ qua |
| **FETCH FIRST/NEXT** | Số hàng tối đa được lấy tiếp theo |
| **ONLY** | Dừng ở số lượng được yêu cầu |
| **WITH TIES** | Lấy thêm các hàng có giá trị sắp xếp đồng hạng với hàng cuối của phần fetch |
| **Pagination** | Chia kết quả thành các phần/trang để ứng dụng tải theo nhu cầu |

Một trang không phải là một phần cố định của bảng. Nó là **một lát cắt của kết quả truy vấn tại một thời điểm**, với bộ lọc, thứ tự sắp xếp và trạng thái dữ liệu cụ thể.

### 1.1. Luồng xử lý khái niệm

~~~text
FROM / JOIN
    |
    v
WHERE
    |
    v
GROUP BY / HAVING (neu co)
    |
    v
SELECT expressions
    |
    v
ORDER BY
    |
    v
OFFSET: bo qua N hang
    |
    v
FETCH: lay toi da M hang
    |
    +--> ONLY: dung tai M
    |
    +--> WITH TIES: lay them cac hang dong hang voi hang cuoi
~~~

Đây là mô hình dễ hiểu để đọc SQL, không phải mô tả đầy đủ thứ tự thực thi vật lý của optimizer. Oracle có thể chọn execution plan khác nhau nhưng phải bảo đảm ngữ nghĩa kết quả của câu lệnh.

## 2. `FETCH FIRST ... ROWS ONLY`

### 2.1. Lấy N hàng đầu tiên

Cú pháp đơn giản:

~~~sql
SELECT order_id, total_amount
FROM orders
ORDER BY total_amount DESC
FETCH FIRST 5 ROWS ONLY;
~~~

Oracle sắp xếp theo `TOTAL_AMOUNT` giảm dần rồi trả tối đa 5 hàng. Từ khóa `FIRST` và `NEXT` đều có thể dùng trong row limiting clause:

~~~sql
-- Hai cach viet tuong duong khi khong co OFFSET:
SELECT order_id
FROM orders
ORDER BY order_id
FETCH FIRST 10 ROWS ONLY;

SELECT order_id
FROM orders
ORDER BY order_id
FETCH NEXT 10 ROWS ONLY;
~~~

`FIRST` thường được đọc tự nhiên khi lấy các hàng đầu; `NEXT` thường được dùng sau `OFFSET` khi lấy phần tiếp theo. Chúng không biểu thị hai cơ chế phân trang khác nhau.

### 2.2. Không có ORDER BY thì không có thứ tự nghiệp vụ bảo đảm

~~~sql
SELECT order_id, total_amount
FROM orders
FETCH FIRST 5 ROWS ONLY;
~~~

Câu lệnh có thể chạy, nhưng không bảo đảm 5 hàng nào sẽ được trả về ổn định. Oracle không cam kết thứ tự hàng nếu không có `ORDER BY`. Thứ tự có thể thay đổi do execution plan, index, parallel execution, thay đổi dữ liệu hoặc các yếu tố vận hành khác.

Ngay cả khi bảng được tạo với khóa chính, điều đó **không có nghĩa SELECT tự động trả theo thứ tự khóa chính**. Nếu muốn đơn hàng có ID nhỏ nhất:

~~~sql
SELECT order_id, total_amount
FROM orders
ORDER BY order_id
FETCH FIRST 5 ROWS ONLY;
~~~

### 2.3. Lấy một hàng

~~~sql
SELECT employee_id, last_name, salary
FROM employees
ORDER BY salary DESC, employee_id
FETCH FIRST 1 ROW ONLY;
~~~

Kết quả là một nhân viên có mức lương cao nhất; nếu nhiều người cùng lương, `EMPLOYEE_ID` làm thứ tự phụ để chọn đúng một hàng theo quy tắc xác định.

Trong Oracle, câu lệnh sau cũng hợp lệ:

~~~sql
SELECT employee_id, last_name
FROM employees
ORDER BY employee_id
FETCH FIRST ROW ONLY;
~~~

Khi bỏ số lượng, Oracle mặc định lấy một hàng. Trong code ứng dụng, viết rõ `FETCH FIRST 1 ROW ONLY` có thể dễ đọc hơn.

### 2.4. Lấy theo tỷ lệ phần trăm

Oracle còn hỗ trợ `PERCENT`:

~~~sql
SELECT employee_id, salary
FROM employees
ORDER BY salary DESC
FETCH FIRST 10 PERCENT ROWS ONLY;
~~~

Truy vấn yêu cầu lấy khoảng 10% số hàng của kết quả đã sắp xếp, theo quy tắc làm tròn/số lượng của Oracle. Đây là giới hạn theo tỷ lệ của result set, không phải phân trang thông thường có số hàng cố định. Nếu dùng `PERCENT`, số hàng trả về có thể thay đổi khi tổng số hàng thỏa điều kiện thay đổi.

Với giao diện có trang 1, 2, 3..., `FETCH NEXT :page_size ROWS ONLY` thường phù hợp hơn `PERCENT`.

## 3. `OFFSET ... FETCH NEXT ... ROWS ONLY`

### 3.1. Cú pháp phân trang theo số hàng

Mẫu tổng quát:

~~~sql
SELECT select_list
FROM table_name
WHERE condition
ORDER BY sort_expression
OFFSET offset_rows ROWS
FETCH NEXT fetch_rows ROWS ONLY;
~~~

Trong đó:

- `offset_rows` là số hàng cần bỏ qua trong thứ tự kết quả.
- `fetch_rows` là số hàng tối đa cần lấy sau khi bỏ qua.
- `ROWS` có thể viết `ROW` khi số lượng là một; dùng `ROWS` nhất quán giúp dễ đọc.
- `OFFSET 0 ROWS` có nghĩa bắt đầu từ hàng đầu tiên.
- `FETCH NEXT 20 ROWS ONLY` lấy tối đa 20 hàng tiếp theo.

Ví dụ trang đầu và trang thứ hai với kích thước trang 20:

~~~sql
-- Trang 1: bo qua 0, lay 20.
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;

-- Trang 2: bo qua 20, lay 20.
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 20 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Trang thứ ba dùng `OFFSET 40 ROWS`; trang thứ tư dùng `OFFSET 60 ROWS`.

### 3.2. Tính offset từ số trang

Nếu đánh số trang bắt đầu từ 1:

\[
\text{offset} = (\text{page number} - 1) \times \text{page size}
\]

Ví dụ kích thước trang 25:

| Trang | Offset | Fetch |
| ---: | ---: | ---: |
| 1 | 0 | 25 |
| 2 | 25 | 25 |
| 3 | 50 | 25 |
| 4 | 75 | 25 |
| 5 | 100 | 25 |

Ứng dụng nên kiểm tra `page_number` và `page_size`:

- Trang thường bắt đầu từ 1, không nhận 0 hoặc số âm nếu API quy ước như vậy.
- Kích thước trang cần có giới hạn tối đa để tránh request tải quá nhiều dữ liệu.
- Tính offset bằng kiểu số đủ lớn, tránh tràn số khi người dùng yêu cầu trang rất xa.
- Không nối trực tiếp giá trị người dùng vào SQL; dùng bind variable nếu driver và câu SQL hỗ trợ.

### 3.3. Bind variables cho offset và page size

Ví dụ trong SQL*Plus hoặc công cụ hỗ trợ bind:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
OFFSET :offset_rows ROWS
FETCH NEXT :page_size ROWS ONLY;
~~~

Các giá trị `:status`, `:offset_rows` và `:page_size` là bind variables. Trong JDBC, đặt giá trị bằng `PreparedStatement` thay vì ghép chuỗi:

~~~java
String sql = """
    SELECT order_id, created_at, total_amount
    FROM orders
    WHERE status = ?
    ORDER BY created_at DESC, order_id DESC
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, status);
    ps.setInt(2, offset);
    ps.setInt(3, pageSize);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // map row
        }
    }
}
~~~

Đây là ví dụ với Oracle JDBC hiện đại hỗ trợ row limiting clause và bind tại vị trí tương ứng. Hãy kiểm thử driver/ORM đang dùng. Bind variable bảo vệ giá trị và hỗ trợ tái sử dụng cursor; nó **không thay thế validation nghiệp vụ**: ứng dụng vẫn phải giới hạn offset/page size và từ chối giá trị âm hoặc quá lớn theo API.

### 3.4. Không có hàng nào nếu offset vượt quá kết quả

Giả sử truy vấn chỉ có 73 hàng thỏa điều kiện và page size là 20:

| Trang | Offset | Số hàng thực tế |
| ---: | ---: | ---: |
| 1 | 0 | 20 |
| 2 | 20 | 20 |
| 3 | 40 | 20 |
| 4 | 60 | 13 |
| 5 | 80 | 0 |

Không có lỗi khi trang 5 trả rỗng; đó là kết quả tự nhiên của giới hạn. Giao diện nên dựa vào tổng số hàng hoặc kiểm tra trang rỗng để xử lý nút Next/Previous.

## 4. `WITH TIES`: giữ lại các hàng đồng hạng

### 4.1. Vấn đề khi dùng ONLY

Giả sử xếp hạng nhân viên theo lương:

| Employee | Salary |
| --- | ---: |
| An | 90.000 |
| Bình | 85.000 |
| Chi | 85.000 |
| Dũng | 80.000 |

Truy vấn:

~~~sql
SELECT employee_name, salary
FROM employees
ORDER BY salary DESC
FETCH FIRST 2 ROWS ONLY;
~~~

Chỉ trả hai hàng. Nếu số hàng thứ hai có nhiều người cùng lương, một người đồng hạng có thể bị loại khỏi kết quả vì giới hạn dừng ở hai hàng.

### 4.2. Dùng WITH TIES

~~~sql
SELECT employee_name, salary
FROM employees
ORDER BY salary DESC
FETCH FIRST 2 ROWS WITH TIES;
~~~

Kết quả gồm:

| Employee | Salary |
| --- | ---: |
| An | 90.000 |
| Bình | 85.000 |
| Chi | 85.000 |

Mặc dù yêu cầu 2 hàng, Oracle trả 3 hàng vì `CHI` có cùng giá trị sắp xếp với hàng cuối cùng được lấy. Số hàng thực tế có thể **lớn hơn** số lượng yêu cầu.

`WITH TIES` chỉ có ý nghĩa khi có `ORDER BY`; nó mở rộng phần fetch để bao gồm tất cả các hàng đồng hạng với ranh giới cuối theo **các biểu thức sắp xếp**. Không có `ORDER BY` thì không có tiêu chí xác định ties.

### 4.3. Ties được xác định theo toàn bộ ORDER BY

Đây là điểm rất quan trọng. Xét:

~~~sql
SELECT employee_id, employee_name, salary
FROM employees
ORDER BY salary DESC, employee_id
FETCH FIRST 2 ROWS WITH TIES;
~~~

Nếu `EMPLOYEE_ID` là duy nhất, hai hàng có cùng `SALARY` nhưng khác `EMPLOYEE_ID` **không đồng hạng theo toàn bộ ORDER BY**. Vì vậy câu truy vấn có thể chỉ trả đúng 2 hàng.

Nếu mục tiêu là lấy tất cả nhân viên cùng mức lương tại ranh giới, chỉ sắp xếp theo `SALARY`:

~~~sql
ORDER BY salary DESC
FETCH FIRST 2 ROWS WITH TIES;
~~~

Nếu muốn kết quả ties vẫn có thứ tự trình bày ổn định, có thể bọc truy vấn:

~~~sql
SELECT employee_id, employee_name, salary
FROM (
    SELECT employee_id, employee_name, salary
    FROM employees
    ORDER BY salary DESC
    FETCH FIRST 2 ROWS WITH TIES
)
ORDER BY salary DESC, employee_id;
~~~

Truy vấn trong cùng chọn **nhóm đồng hạng theo salary**; truy vấn ngoài chỉ sắp xếp các hàng đã chọn theo employee_id để hiển thị ổn định. Cách này giữ đúng ý nghĩa ties mà không đưa khóa duy nhất vào tiêu chí xác định ties bên trong.

### 4.4. `WITH TIES` không phải “thêm vài hàng ngẫu nhiên”

Oracle không đơn giản tăng page size một cách tùy ý. Nó lấy thêm **tất cả hàng có giá trị ORDER BY tương đương với hàng cuối của phần fetch**. Ví dụ fetch 10, nếu hàng thứ 10 có cùng giá trị sort với 40 hàng kế tiếp, kết quả có thể lên tới 50 hàng.

Tùy chọn này hữu ích cho:

- Lấy top N mức lương mà không cắt một nhóm nhân viên cùng lương.
- Lấy top N sản phẩm theo doanh số và giữ tất cả sản phẩm đồng hạng tại ngưỡng.
- Bảng xếp hạng, điểm thi hoặc danh sách kết quả có tiêu chí đồng hạng.

Không phù hợp nếu API bắt buộc trả đúng số lượng cố định và kích thước payload không được vượt giới hạn.

### 4.5. NULL và nhiều biểu thức sắp xếp

Nếu cột sắp xếp có NULL, Oracle áp dụng thứ tự NULL theo quy tắc của `ORDER BY`; để kết quả dễ dự đoán, nên viết rõ `NULLS FIRST` hoặc `NULLS LAST`:

~~~sql
SELECT product_id, rating
FROM products
ORDER BY rating DESC NULLS LAST
FETCH FIRST 10 ROWS WITH TIES;
~~~

Khi có nhiều biểu thức:

~~~sql
ORDER BY category_id, score DESC
FETCH FIRST 10 ROWS WITH TIES;
~~~

Hai hàng chỉ đồng hạng nếu các biểu thức sắp xếp tạo ra cùng giá trị theo quy tắc so sánh tương ứng. Một giá trị `SCORE` giống nhau nhưng `CATEGORY_ID` khác nhau không phải ties theo toàn bộ thứ tự này.

## 5. Phân biệt top-N, top-N theo nhóm và phân trang

Những yêu cầu nghe giống nhau nhưng khác ngữ nghĩa:

| Yêu cầu | Cách tiếp cận |
| --- | --- |
| Lấy đúng tối đa 10 hàng đầu | `FETCH FIRST 10 ROWS ONLY` |
| Lấy 10 hàng đầu và giữ nhóm đồng hạng tại ranh giới | `FETCH FIRST 10 ROWS WITH TIES` |
| Lấy trang thứ 3, 20 hàng/trang | `OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY` |
| Lấy 3 nhân viên lương cao nhất **trong mỗi phòng ban** | `ROW_NUMBER()`/`RANK()`/`DENSE_RANK()` với `PARTITION BY` |
| Lấy top 3 mức lương khác nhau | `DENSE_RANK()` theo salary |

`WITH TIES` trong row limiting clause áp dụng cho **ranh giới của toàn result set**, không tự phân nhóm theo phòng ban. Muốn top-N cho từng nhóm, dùng analytic function:

~~~sql
SELECT department_id, employee_id, salary
FROM (
    SELECT
        department_id,
        employee_id,
        salary,
        RANK() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC
        ) AS salary_rank
    FROM employees
)
WHERE salary_rank <= 3
ORDER BY department_id, salary DESC, employee_id;
~~~

Ở đây `RANK()` cho phép nhiều nhân viên cùng mức lương chia sẻ thứ hạng; `salary_rank <= 3` có thể trả hơn ba hàng trong mỗi phòng ban nếu có ties. Nếu muốn đúng tối đa 3 hàng mỗi phòng ban, dùng `ROW_NUMBER()` với thứ tự có tie-breaker duy nhất.

## 6. Phân trang cần ORDER BY ổn định

### 6.1. Thứ tự không duy nhất gây kết quả không ổn định

Ví dụ:

~~~sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Nếu nhiều đơn hàng có cùng `CREATED_AT`, thứ tự tương đối giữa chúng không được xác định bởi câu truy vấn. Khi chạy trang 1 và trang 2 ở hai thời điểm khác nhau, các hàng đồng thời gian có thể xuất hiện ở trang khác nhau hoặc bị lặp/bỏ sót khi thứ tự vật lý/plan thay đổi.

Giải pháp thường là thêm khóa duy nhất làm tie-breaker:

~~~sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Nếu `ORDER_ID` là duy nhất, cặp (`CREATED_AT`, `ORDER_ID`) xác định thứ tự toàn phần. Hàng nào có cùng thời gian sẽ được sắp tiếp theo ID, giúp phân trang có thứ tự ổn định hơn.

### 6.2. NULLS FIRST/LAST và thứ tự nghiệp vụ

Nếu sort column cho phép NULL, xác định vị trí mong muốn:

~~~sql
SELECT task_id, due_date
FROM tasks
ORDER BY due_date ASC NULLS LAST, task_id ASC
FETCH FIRST 25 ROWS ONLY;
~~~

Thứ tự tường minh giúp người đọc và ứng dụng hiểu những hàng chưa có hạn chót được đặt ở đâu. Với phân trang, khóa phụ duy nhất vẫn quan trọng để xác định thứ tự giữa các hàng cùng ngày hoặc cùng NULL.

### 6.3. ORDER BY phải khớp yêu cầu sản phẩm

Một màn hình có thể yêu cầu:

- Mới nhất trước: `created_at DESC, id DESC`.
- Tên tăng dần: `name ASC, id ASC`.
- Ưu tiên trạng thái: dùng `CASE` trong `ORDER BY` rồi thêm khóa duy nhất.
- Điểm cao nhất: `score DESC`; nếu cần giữ đồng hạng, dùng `WITH TIES` thay vì thêm khóa duy nhất vào tiêu chí ties.

Không dùng một `ORDER BY id` mặc định cho mọi màn hình nếu nghiệp vụ cần thứ tự khác. Cũng không dùng một thứ tự chỉ có tính thẩm mỹ mà thiếu tie-breaker trong phân trang nhiều request.

## 7. OFFSET pagination: ưu điểm và giới hạn hiệu năng

### 7.1. Ưu điểm

`OFFSET/FETCH` dễ hiểu và dễ tích hợp:

- Người dùng có thể nhảy đến trang 1, 2, 10, 100.
- API nhận page number và page size đơn giản.
- SQL ngắn, rõ hơn một số mẫu lồng `ROWNUM` cũ.
- Phù hợp với tập kết quả vừa phải, báo cáo nội bộ hoặc màn hình có nhu cầu nhảy trang.

### 7.2. Nhược điểm khi offset lớn

Giả sử muốn lấy 20 hàng ở trang 50.000:

~~~sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 999980 ROWS
FETCH NEXT 20 ROWS ONLY;
~~~

Database có thể phải đi qua rất nhiều hàng đầu tiên theo thứ tự phù hợp rồi mới bỏ qua gần một triệu hàng. Optimizer có thể tận dụng index, stopkey hoặc kế hoạch phù hợp, nhưng **OFFSET lớn thường làm công việc tăng theo số hàng bị bỏ qua**. Không thể khẳng định mỗi truy vấn sẽ đọc đúng 1.000.000 hàng, vì execution plan và index quyết định cách thực thi; tuy nhiên offset sâu thường không hiệu quả như seek pagination.

### 7.3. Index phù hợp với ORDER BY

Nếu màn hình thường lọc theo trạng thái và sắp xếp theo ngày/ID:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
OFFSET :offset_rows ROWS FETCH NEXT :page_size ROWS ONLY;
~~~

Một index được thiết kế phù hợp có thể giúp Oracle tìm và duyệt dữ liệu theo điều kiện lọc/thứ tự:

~~~sql
-- Chi la vi du thiet ke index; can xem workload va execution plan truoc khi tao.
CREATE INDEX ix_orders_status_created_id
ON orders (status, created_at DESC, order_id DESC);
~~~

Index không tự bảo đảm mọi query pagination đều nhanh. Cần kiểm tra:

- Selectivity của `STATUS` và số lượng giá trị khác nhau.
- Tỷ lệ hàng được trả về, cột cần đọc, clustering factor.
- Execution plan thực tế và thống kê optimizer.
- Chi phí duy trì index khi insert/update/delete.
- Khả năng index phục vụ cả filter lẫn sort trong thứ tự cụ thể.

Đừng tạo index chỉ dựa trên một ví dụ SQL mà chưa xem workload.

## 8. Keyset/seek pagination: tiếp tục từ hàng cuối đã xem

Khi người dùng chủ yếu nhấn **Next** để xem tiếp, thay vì yêu cầu trang bất kỳ, keyset pagination thường hiệu quả hơn offset sâu.

### 8.1. Ý tưởng

Giả sử thứ tự:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Sau khi trang đầu trả 20 hàng, ứng dụng giữ lại cặp giá trị của hàng cuối:

~~~text
last_created_at = 2026-11-14 10:30:00
last_order_id   = 8451
~~~

Trang kế tiếp chỉ lấy những hàng **đứng sau** cặp khóa đó trong thứ tự giảm dần:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :status
  AND (
        created_at < :last_created_at
        OR (
            created_at = :last_created_at
            AND order_id < :last_order_id
        )
      )
ORDER BY created_at DESC, order_id DESC
FETCH NEXT :page_size ROWS ONLY;
~~~

Vì `ORDER_ID` duy nhất, điều kiện xác định chính xác hàng đứng sau ranh giới trang trước. Database không cần đếm/bỏ qua toàn bộ các hàng từ đầu; nó có thể dùng index bắt đầu từ khóa tiếp theo nếu có access path phù hợp.

### 8.2. Keyset với khóa tăng dần

Nếu chỉ sắp xếp theo khóa tăng dần:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders
WHERE order_id > :last_order_id
ORDER BY order_id
FETCH NEXT :page_size ROWS ONLY;
~~~

Đây là mẫu đơn giản nhất. Nó phù hợp khi:

- Thứ tự trang dựa trên một khóa có tính thứ tự và ổn định.
- Người dùng chủ yếu đi tiếp/lùi theo cursor.
- Ứng dụng lưu được giá trị cuối cùng đã thấy.

Nếu cho phép sort động theo nhiều cột, ứng dụng phải tạo điều kiện seek đúng với từng thứ tự và chiều sort. Không thể chỉ thay `ORDER BY` mà giữ nguyên điều kiện `WHERE`.

### 8.3. Keyset với nhiều cột và NULL

Khi sort theo `created_at DESC, order_id DESC` và `created_at` có thể NULL, điều kiện seek phải mô phỏng đúng thứ tự `NULLS FIRST/LAST`. So sánh `<` với NULL không trả TRUE/FALSE theo cách đơn giản mà trả UNKNOWN; do đó truy vấn ở mục 8.1 giả định `CREATED_AT IS NOT NULL` hoặc có ràng buộc tương ứng.

Nếu cột nullable, hãy:

1. Xác định thứ tự NULL rõ ràng trong `ORDER BY`.
2. Xây dựng điều kiện seek riêng cho nhóm NULL và non-NULL.
3. Thêm khóa duy nhất làm tie-breaker.
4. Kiểm thử ranh giới khi hàng cuối trang có NULL.

Trong nhiều hệ thống, chọn cột sort không NULL (ví dụ `created_at NOT NULL`) giúp pagination đơn giản hơn.

### 8.4. So sánh offset và keyset

| Tiêu chí | OFFSET/FETCH | Keyset/seek |
| --- | --- | --- |
| Đi thẳng đến trang bất kỳ | Dễ, tính offset từ số trang | Khó hơn; thường phải có cursor/đi tuần tự |
| Trang sâu | Có thể tốn chi phí bỏ qua nhiều hàng | Thường hiệu quả hơn với index/seek phù hợp |
| Thay đổi dữ liệu giữa request | Có thể lặp/bỏ sót hàng do offset dịch chuyển | Ít bị dịch chuyển do insert trước cursor, nhưng vẫn cần hiểu thay đổi sort key/delete |
| API | Page number + size | Cursor token chứa giá trị khóa cuối |
| Sort động | Dễ xây SQL nhưng phải kiểm soát thứ tự | Cần điều kiện seek tương ứng từng kiểu sort |
| Phù hợp | Back-office, báo cáo, nhảy trang | Feed, danh sách cuộn liên tục, dữ liệu lớn |

Keyset không tự tạo snapshot bất biến. Nếu hàng được cập nhật cột sort, bị xóa hoặc quyền/filter thay đổi giữa các request, kết quả vẫn có thể khác. Nếu nghiệp vụ yêu cầu mọi trang phản ánh **cùng một snapshot dữ liệu**, cần chiến lược consistency riêng, chẳng hạn dùng cùng snapshot/SCN trong phạm vi hỗ trợ và thiết kế thời gian tồn tại transaction phù hợp; không giữ một transaction mở tùy tiện qua nhiều request web.

## 9. Dữ liệu thay đổi giữa các trang: vì sao có thể lặp hoặc mất hàng?

Giả sử trang đầu lấy 3 hàng:

| Vị trí | ID | Created |
| ---: | ---: | --- |
| 1 | 105 | 10:05 |
| 2 | 104 | 10:04 |
| 3 | 103 | 10:03 |

Sau đó có đơn hàng mới ID 106, giờ 10:06 được insert. Khi trang hai chạy lại với `OFFSET 3`:

| Vị trí mới | ID | Created |
| ---: | ---: | --- |
| 1 | 106 | 10:06 |
| 2 | 105 | 10:05 |
| 3 | 104 | 10:04 |
| 4 | 103 | 10:03 |
| 5 | 102 | 10:02 |

Offset 3 bỏ qua 106, 105, 104 rồi trả 103 và 102; ID 103 **bị lặp** ở trang hai dù trang đầu đã có nó. Nếu có xóa hoặc thay đổi sort key, một số hàng có thể bị bỏ qua.

### 9.1. Các cách xử lý theo yêu cầu

- Nếu giao diện chấp nhận dữ liệu thay đổi giữa các trang, giải thích rằng pagination phản ánh trạng thái mới nhất tại mỗi request.
- Nếu cần Next liên tục trên tập dữ liệu biến động, ưu tiên keyset cursor theo sort key ổn định.
- Nếu cần một snapshot nhất quán cho báo cáo, thiết kế snapshot/SCN hoặc materialized result theo nghiệp vụ; không chỉ tăng page size.
- Nếu cần nhảy trang tùy ý và consistency mạnh, cân nhắc giữ một tập kết quả/snapshot có định danh hoặc giải pháp báo cáo chuyên biệt.

Không có một lựa chọn phân trang phù hợp tất cả hệ thống. Hãy chọn dựa trên **độ lớn dữ liệu, kiểu điều hướng, độ biến động và yêu cầu nhất quán**.

## 10. Đếm tổng số hàng khi phân trang

### 10.1. Dùng COUNT(*) OVER()

Một màn hình thường muốn hiển thị “trang 2 / 18, tổng 436 đơn hàng”. Có thể thêm analytic count:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount,
    COUNT(*) OVER () AS total_rows
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
OFFSET :offset_rows ROWS
FETCH NEXT :page_size ROWS ONLY;
~~~

`COUNT(*) OVER()` đếm số hàng **sau điều kiện lọc** trong result set trước khi áp dụng phần row limiting, rồi lặp tổng số trên từng hàng được trả về.

Lưu ý:

- Nếu trang có hàng, cột `TOTAL_ROWS` cho biết tổng số hàng thỏa `WHERE`, không phải số hàng của trang.
- Nếu offset vượt kết quả và trang rỗng, truy vấn không có dòng nào để mang `TOTAL_ROWS`; ứng dụng không thể đọc tổng từ row đó.
- Analytic count có thể khiến Oracle phải xử lý lượng dữ liệu đáng kể để tính tổng, ngay cả khi page size nhỏ.

### 10.2. COUNT riêng và query trang riêng

Một cách khác:

~~~sql
SELECT COUNT(*) AS total_rows
FROM orders
WHERE status = :status;

SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
OFFSET :offset_rows ROWS
FETCH NEXT :page_size ROWS ONLY;
~~~

Ưu điểm là luôn lấy được count kể cả trang rỗng; nhược điểm là hai query có thể quan sát dữ liệu ở **hai thời điểm khác nhau** nếu dữ liệu thay đổi giữa chúng. Nếu cần count và page nhất quán, phải cân nhắc transaction isolation/snapshot và chi phí.

### 10.3. Có nhất thiết phải đếm tổng không?

Nhiều API hiện đại chỉ trả:

- danh sách hàng của trang;
- cursor/trang tiếp theo;
- cờ `has_more` nếu query lấy dư một hàng;
- không tính tổng toàn bộ vì count có thể tốn tài nguyên.

Ví dụ fetch `page_size + 1`:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE status = :status
ORDER BY created_at DESC, order_id DESC
OFFSET :offset_rows ROWS
FETCH NEXT :fetch_size ROWS ONLY;
~~~

Nếu yêu cầu trang có 20 hàng, đặt `:fetch_size = 21`. Ứng dụng trả tối đa 20 hàng; nếu có hàng thứ 21 thì `has_more = true`. Cách này tránh count tổng nhưng không tự giải quyết offset sâu hoặc dữ liệu thay đổi.

## 11. OFFSET/FETCH và WITH TIES trong các truy vấn có JOIN/GROUP BY

### 11.1. Giới hạn sau khi JOIN

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.created_at
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY o.created_at DESC, o.order_id DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Ở đây fetch giới hạn **các hàng của result set sau JOIN**, không phải 20 customer. Nếu một customer có 10 đơn hàng, customer đó có thể xuất hiện nhiều dòng.

Nếu mục tiêu là 20 khách hàng rồi lấy toàn bộ đơn hàng của họ, phải xác định 20 customer trước (ví dụ CTE/subquery), sau đó JOIN lại. Không đặt `FETCH` tùy ý ở query ngoài rồi kỳ vọng nó giới hạn từng bảng nguồn.

### 11.2. Giới hạn sau GROUP BY

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id
ORDER BY revenue DESC
FETCH FIRST 10 ROWS WITH TIES;
~~~

Kết quả là top 10 **nhóm khách hàng** theo doanh thu, giữ các nhóm đồng hạng ở ranh giới. Row limiting clause áp dụng lên các hàng đã tổng hợp, không giới hạn số order nguồn được đọc.

### 11.3. Giới hạn trong subquery

~~~sql
WITH top_customers AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
    ORDER BY SUM(total_amount) DESC
    FETCH FIRST 10 ROWS WITH TIES
)
SELECT c.customer_name, t.revenue
FROM top_customers t
JOIN customers c
    ON c.customer_id = t.customer_id
ORDER BY t.revenue DESC, c.customer_id;
~~~

Truy vấn con chọn nhóm top theo revenue; truy vấn ngoài nối tên và sắp xếp để trình bày. Tương tự ví dụ trước, thứ tự ngoài có tie-breaker không làm thay đổi nhóm ties đã chọn bên trong.

## 12. Phân trang trên Oracle phiên bản cũ: `ROWNUM` và `ROW_NUMBER()`

Row limiting clause được hỗ trợ từ Oracle 12c. Nếu ứng dụng phải chạy trên Oracle 11g hoặc cần hiểu code legacy, hai kỹ thuật phổ biến là `ROWNUM` và analytic `ROW_NUMBER()`.

### 12.1. Giới hạn N hàng bằng ROWNUM

~~~sql
SELECT order_id, created_at
FROM orders
WHERE ROWNUM <= 10;
~~~

`ROWNUM` là pseudocolumn Oracle gán cho các hàng khi chúng được chọn trong một query block. Nó **không phải số thứ tự cố định của hàng trong bảng**.

Lỗi thường gặp:

~~~sql
-- KHONG dap ung y dinh lay 10 don hang moi nhat:
SELECT order_id, created_at
FROM orders
WHERE ROWNUM <= 10
ORDER BY created_at DESC;
~~~

Vì `ROWNUM` được áp dụng trong query block trước khi kết quả cuối cùng được sắp xếp theo `ORDER BY` trong cách viết này, truy vấn có thể lấy 10 hàng trước rồi mới sắp xếp chúng; nó không bảo đảm lấy 10 hàng mới nhất toàn bảng.

Đúng hơn là sắp xếp ở subquery rồi giới hạn bên ngoài:

~~~sql
SELECT order_id, created_at
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC, order_id DESC
)
WHERE ROWNUM <= 10;
~~~

### 12.2. OFFSET pagination bằng ROWNUM lồng

Muốn lấy hàng từ vị trí `:offset + 1` đến `:offset + :page_size`:

~~~sql
SELECT order_id, created_at, total_amount
FROM (
    SELECT sorted_rows.*, ROWNUM AS rn
    FROM (
        SELECT order_id, created_at, total_amount
        FROM orders
        ORDER BY created_at DESC, order_id DESC
    ) sorted_rows
    WHERE ROWNUM <= :offset_rows + :page_size
)
WHERE rn > :offset_rows
ORDER BY rn;
~~~

Lớp trong cùng sắp xếp kết quả; lớp giữa gán `ROWNUM` và dừng ở giới hạn cuối; lớp ngoài bỏ những hàng có `RN <= offset`. Đây là mẫu legacy thường gặp, nhưng cần đọc kỹ các tầng để không đặt `ROWNUM` sai vị trí.

### 12.3. Dùng ROW_NUMBER() OVER(...)

Một cách tổng quát:

~~~sql
SELECT order_id, created_at, total_amount
FROM (
    SELECT
        order_id,
        created_at,
        total_amount,
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM orders
)
WHERE rn BETWEEN :first_row AND :last_row
ORDER BY rn;
~~~

Nếu page size là 20 và page number là 3:

~~~text
first_row = (3 - 1) * 20 + 1 = 41
last_row  = 3 * 20 = 60
~~~

`ROW_NUMBER()` đánh số từng hàng theo thứ tự của analytic `ORDER BY`. Thứ tự phải đủ xác định; nếu hai hàng đồng hạng, hãy thêm tie-breaker duy nhất để số thứ tự không tùy thuộc thứ tự nội bộ.

### 12.4. Phân biệt ROW_NUMBER, RANK và DENSE_RANK

| Hàm | Cách xử lý ties | Ví dụ thứ hạng khi điểm là 100, 90, 90, 80 |
| --- | --- | --- |
| `ROW_NUMBER()` | Mỗi hàng một số duy nhất | 1, 2, 3, 4 |
| `RANK()` | Hàng đồng hạng cùng rank, rank sau có khoảng nhảy | 1, 2, 2, 4 |
| `DENSE_RANK()` | Hàng đồng hạng cùng rank, không bỏ số | 1, 2, 2, 3 |

Muốn phân trang theo **số hàng cố định**, thường dùng `ROW_NUMBER()`. Muốn top N rank và giữ đồng hạng, dùng `RANK()`/`DENSE_RANK()` hoặc `FETCH ... WITH TIES` tùy ngữ nghĩa yêu cầu.

## 13. Những giới hạn và lưu ý của row limiting clause

### 13.1. Thứ tự cú pháp

Row limiting clause nằm sau `ORDER BY`:

~~~sql
SELECT ...
FROM ...
WHERE ...
GROUP BY ...
HAVING ...
ORDER BY ...
OFFSET ... ROWS
FETCH NEXT ... ROWS ONLY;
~~~

Không đặt `OFFSET/FETCH` trước `WHERE` hoặc giữa `FROM` và `ORDER BY`. Nếu dùng subquery, hãy xác định rõ phần giới hạn áp dụng cho query block nào.

### 13.2. Alias cột và tên trùng

Trong truy vấn có các cột trùng tên do join, row limiting clause có thể làm lộ một số hạn chế về tên cột/alias và việc tham chiếu từ inline view. Hãy đặt alias duy nhất, rõ ràng:

~~~sql
SELECT
    c.customer_id AS customer_id,
    o.order_id AS order_id,
    o.created_at AS order_created_at
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
ORDER BY o.created_at DESC, o.order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Tránh trả hai cột cùng tên không phân biệt, nhất là khi dùng `SELECT *` qua join hoặc bọc truy vấn có row limiting clause. Dùng danh sách cột và alias rõ giúp tránh lỗi kiểu `ORA-00918` trong các trường hợp bị giới hạn tên cột trùng.

### 13.3. Kết hợp FOR UPDATE

Row limiting clause có những hạn chế khi kết hợp với một số cú pháp SQL, trong đó có `FOR UPDATE`. Nếu cần chọn hàng để khóa/cập nhật, hãy kiểm tra quy tắc phiên bản cụ thể và thiết kế truy vấn phù hợp; không mặc định có thể thêm `FOR UPDATE` vào cuối bất kỳ câu `OFFSET/FETCH` nào.

### 13.4. Không dùng FETCH để thay thế điều kiện lọc

~~~sql
-- Lay 10 hang dau trong tap da loc:
SELECT order_id, total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 10 ROWS ONLY;
~~~

`WHERE` xác định **hàng nào đủ điều kiện**; `FETCH` chỉ giới hạn số hàng trong kết quả. Nếu muốn top 10 đơn hàng đã thanh toán, phải lọc `STATUS` trước khi lấy top 10. Không lấy 10 hàng toàn bảng rồi lọc trạng thái ở ứng dụng, vì kết quả nghiệp vụ sẽ sai.

### 13.5. FETCH không bảo đảm execution plan cụ thể

Oracle optimizer có thể dùng index, sort, stopkey hoặc các kỹ thuật khác tùy thống kê và query. `FETCH FIRST 10 ROWS ONLY` biểu thị **ngữ nghĩa kết quả**, không phải lời hứa rằng database luôn chỉ đọc 10 row từ storage. Nếu cần tối ưu:

- Xem execution plan của câu SQL thực tế.
- Kiểm tra predicate, order-by, index và số hàng ước lượng/thực tế.
- Dùng bind variables và giới hạn page size.
- Thử với dữ liệu có phân bố giống production.
- Đánh giá lại khi thay đổi filter hoặc sort.

## 14. Bài thực hành: tạo bảng và phân trang

Các bước sau tạo một bảng lab độc lập, gồm ngày tạo và giá trị có ties. Chỉ chạy trong schema bạn sở hữu; nếu bảng cùng tên đã tồn tại, chọn tên khác thay vì xóa dữ liệu có sẵn.

### Bước 1 — Tạo bảng mẫu

~~~sql
CREATE TABLE pagination_lab (
    item_id     NUMBER PRIMARY KEY,
    item_name   VARCHAR2(60 CHAR) NOT NULL,
    category    VARCHAR2(20 CHAR) NOT NULL,
    score       NUMBER(6,2) NOT NULL,
    created_at  TIMESTAMP NOT NULL
);
~~~

### Bước 2 — Thêm dữ liệu có ties

~~~sql
INSERT ALL
    INTO pagination_lab VALUES
        (1, 'Alpha', 'A', 99, TIMESTAMP '2026-11-14 10:00:00')
    INTO pagination_lab VALUES
        (2, 'Beta', 'A', 95, TIMESTAMP '2026-11-14 10:01:00')
    INTO pagination_lab VALUES
        (3, 'Gamma', 'A', 95, TIMESTAMP '2026-11-14 10:02:00')
    INTO pagination_lab VALUES
        (4, 'Delta', 'A', 90, TIMESTAMP '2026-11-14 10:03:00')
    INTO pagination_lab VALUES
        (5, 'Epsilon', 'B', 90, TIMESTAMP '2026-11-14 10:04:00')
    INTO pagination_lab VALUES
        (6, 'Zeta', 'B', 85, TIMESTAMP '2026-11-14 10:05:00')
    INTO pagination_lab VALUES
        (7, 'Eta', 'B', 85, TIMESTAMP '2026-11-14 10:06:00')
    INTO pagination_lab VALUES
        (8, 'Theta', 'B', 80, TIMESTAMP '2026-11-14 10:07:00')
SELECT 1 FROM dual;

COMMIT;
~~~

Trong tập dữ liệu, có hai cặp hàng đồng hạng theo `SCORE`: 95 và 85; hai hàng khác nhau có thể có cùng điểm.

### Bước 3 — Lấy 3 hàng đầu với ONLY

~~~sql
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY score DESC
FETCH FIRST 3 ROWS ONLY;
~~~

Kết quả có tối đa 3 hàng. Hàng thứ ba thuộc nhóm score 95; nếu không thêm tie-breaker, thứ tự giữa Beta và Gamma không được bảo đảm.

### Bước 4 — Lấy 3 hàng đầu với WITH TIES

~~~sql
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY score DESC
FETCH FIRST 3 ROWS WITH TIES;
~~~

Kết quả có 3 hàng: Alpha, Beta và Gamma. Thử thay số lượng thành 2:

~~~sql
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY score DESC
FETCH FIRST 2 ROWS WITH TIES;
~~~

Kết quả gồm **3 hàng** vì hai hàng Beta và Gamma cùng score 95 ở ranh giới. Thử `FETCH FIRST 4 ROWS WITH TIES`: hàng thứ tư có score 90; vì chỉ có một hàng score 90 trong bảng, kết quả là 4 hàng.

### Bước 5 — Thêm tie-breaker và quan sát thay đổi

~~~sql
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY score DESC, item_id
FETCH FIRST 2 ROWS WITH TIES;
~~~

Vì `ITEM_ID` là duy nhất, kết quả sẽ chỉ có 2 hàng. Đây là hành vi đúng nếu bạn muốn thứ tự toàn phần và lấy chính xác hai hàng; nó **không giữ nhóm cùng điểm** nữa. Để vừa chọn ties theo score vừa trình bày ổn định, dùng inline view như Mục 4.3.

### Bước 6 — Phân trang hai hàng mỗi trang

~~~sql
-- Trang 1:
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY item_id
OFFSET 0 ROWS FETCH NEXT 2 ROWS ONLY;

-- Trang 2:
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY item_id
OFFSET 2 ROWS FETCH NEXT 2 ROWS ONLY;

-- Trang 3:
SELECT item_id, item_name, score
FROM pagination_lab
ORDER BY item_id
OFFSET 4 ROWS FETCH NEXT 2 ROWS ONLY;
~~~

Vì `ITEM_ID` là khóa chính, thứ tự trang ổn định trong dữ liệu không đổi. Thử thay `OFFSET 4` thành `OFFSET 20` để quan sát result set rỗng.

### Bước 7 — Tính tổng số hàng

~~~sql
SELECT
    item_id,
    item_name,
    COUNT(*) OVER () AS total_rows
FROM pagination_lab
ORDER BY item_id
OFFSET 2 ROWS FETCH NEXT 2 ROWS ONLY;
~~~

Mỗi hàng trả về mang `TOTAL_ROWS = 8`. Nếu đổi offset thành 20, không có hàng nào để hiển thị total.

### Bước 8 — Thử keyset pagination

Giả sử trang đầu theo `ITEM_ID` tăng dần lấy hai hàng và hàng cuối có `ITEM_ID=2`. Trang tiếp theo:

~~~sql
SELECT item_id, item_name, score
FROM pagination_lab
WHERE item_id > 2
ORDER BY item_id
FETCH NEXT 2 ROWS ONLY;
~~~

Kết quả là hai hàng có ID tiếp theo, không cần bỏ qua các hàng từ đầu.

### Bước 9 — Dọn bảng lab nếu không cần

~~~sql
-- Chi chay neu chac chan day la bang lab cua ban.
DROP TABLE pagination_lab PURGE;
~~~

`PURGE` bỏ qua recycle bin; sau khi drop/purge không trông đợi Flashback Drop để khôi phục bảng. Có thể giữ bảng để tiếp tục thực hành `ROW_NUMBER()` và execution plan.

## 15. Câu hỏi ôn tập

1. Vì sao `FETCH FIRST 20 ROWS ONLY` không bảo đảm cùng 20 hàng nếu không có `ORDER BY`?
2. `OFFSET 20 ROWS FETCH NEXT 20 ROWS ONLY` tương ứng trang thứ mấy khi page size là 20 và trang bắt đầu từ 1?
3. Sự khác nhau giữa `ONLY` và `WITH TIES` là gì?
4. Với `ORDER BY salary DESC`, nếu hàng thứ 10 có 5 nhân viên cùng mức lương, `FETCH FIRST 10 ROWS WITH TIES` có thể trả bao nhiêu hàng?
5. Nếu thêm `employee_id` duy nhất vào `ORDER BY salary DESC, employee_id`, các nhân viên cùng lương có còn ties theo toàn bộ thứ tự không?
6. Làm thế nào vừa giữ ties theo score vừa sắp xếp kết quả ổn định theo ID?
7. `WITH TIES` có thay thế được `RANK() OVER (PARTITION BY department_id ...)` để lấy top 3 từng phòng ban không?
8. Vì sao OFFSET lớn có thể chậm dù page size chỉ là 20?
9. Keyset pagination cần giữ lại thông tin nào từ trang trước?
10. Vì sao điều kiện seek nhiều cột cần mô phỏng đúng chiều ASC/DESC và xử lý NULL?
11. `COUNT(*) OVER()` có trả total rows trong kết quả nếu trang rỗng không?
12. Vì sao query count riêng và query page riêng có thể cho số liệu không khớp khi dữ liệu thay đổi?
13. Trong `ROWNUM` pagination, vì sao cần sắp xếp ở subquery trước khi gán ROWNUM?
14. `ROW_NUMBER()` khác `RANK()` ở cách xử lý ties thế nào?
15. `OFFSET/FETCH` có bảo đảm database chỉ đọc đúng số hàng fetch không?

**Gợi ý trả lời:**

1. Oracle không bảo đảm thứ tự hàng nếu thiếu ORDER BY.
2. Trang 2.
3. ONLY dừng ở số lượng; WITH TIES thêm toàn bộ hàng đồng hạng với hàng cuối theo ORDER BY.
4. Có thể trả 14 hàng nếu 5 hàng ở nhóm cuối được tính gồm hàng thứ 10 và 4 hàng ties sau nó.
5. Không nếu ID duy nhất, vì toàn bộ tuple sort khác nhau.
6. Chọn ties trong subquery chỉ ORDER BY score; outer query sắp xếp thêm ID.
7. Không; WITH TIES giới hạn toàn result set, không partition theo nhóm.
8. Database có thể phải duyệt/bỏ qua nhiều hàng trước vị trí cần lấy.
9. Khóa sort của hàng cuối (và các giá trị cần thiết để tạo điều kiện seek).
10. Vì NULL không so sánh như giá trị thông thường và điều kiện phải khớp đúng thứ tự kết quả.
11. Không, không có dòng nào mang analytic count.
12. Hai câu lệnh có thể nhìn thấy trạng thái dữ liệu khác nhau.
13. Nếu gán ROWNUM trước khi sắp xếp, có thể lấy N hàng tùy ý rồi mới sort.
14. ROW_NUMBER luôn cấp số duy nhất; RANK chia sẻ rank cho ties và bỏ số sau nhóm.
15. Không; FETCH quy định kết quả, execution plan quyết định lượng công việc vật lý.

## Tài liệu Oracle tham khảo

- [Oracle SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): cú pháp row_limiting_clause, OFFSET, FETCH FIRST/NEXT, ONLY và WITH TIES.
- [Oracle Database SQL Language Reference — ROWNUM Pseudocolumn](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html): hành vi và hạn chế của ROWNUM.
- [Oracle Database SQL Language Reference — ROW_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROW_NUMBER.html): đánh số hàng theo analytic order.
- [Oracle Database SQL Language Reference — RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/RANK.html): thứ hạng và xử lý hàng đồng hạng.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): đọc execution plan, index và tối ưu truy vấn.
