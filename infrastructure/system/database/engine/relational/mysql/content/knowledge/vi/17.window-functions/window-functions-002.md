# Cấu trúc OVER, PARTITION BY và ORDER BY

Window function (hàm cửa sổ) thực hiện phép tính trên một tập hàng có liên quan tới hàng hiện tại, nhưng vẫn giữ từng hàng trong kết quả. Đây là điểm khác biệt quan trọng so với GROUP BY: GROUP BY gom nhiều hàng thành một hàng cho mỗi nhóm, còn window function bổ sung giá trị tính toán vào từng hàng mà không làm mất chi tiết.

Trong MySQL, mệnh đề OVER xác định cửa sổ mà hàm sẽ quan sát. PARTITION BY chia dữ liệu thành các nhóm độc lập; ORDER BY xác định thứ tự hàng trong mỗi cửa sổ; frame clause (nếu có) giới hạn tập hàng cụ thể được dùng cho một số phép tính.

Bài học thuộc phạm vi DATABASE_MYSQL: làm chủ truy vấn phân tích, xếp hạng, tính tổng lũy kế và so sánh các hàng liên quan; hiểu đúng phạm vi cửa sổ, thứ tự xử lý và ảnh hưởng tới hiệu năng để tổ chức báo cáo và truy vấn dữ liệu quan hệ chính xác.

## 1. Window function và vai trò của OVER

Một window function thường có dạng:

~~~sql
window_function(expression) OVER (
    [PARTITION BY partition_expression [, ...]]
    [ORDER BY order_expression [ASC | DESC] [, ...]]
    [frame_clause]
)
~~~

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| Hàm cửa sổ | Phép tính như ROW_NUMBER, RANK, SUM, AVG, LAG hoặc LEAD |
| OVER | Khai báo cửa sổ dùng để tính toán |
| PARTITION BY | Chia hàng thành các phân vùng độc lập |
| ORDER BY | Xác định thứ tự hàng bên trong cửa sổ |
| Frame clause | Giới hạn các hàng tham gia tính toán quanh hàng hiện tại |

Ví dụ tính tổng doanh thu theo từng nhân viên:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
    ) AS salesperson_total
FROM sales_demo;
~~~

Mỗi hàng vẫn đại diện cho một giao dịch. Cột salesperson_total lặp lại tổng doanh thu của nhân viên tương ứng trên mọi hàng của nhân viên đó.

Mệnh đề OVER là thành phần xác định cách hàm nhìn các hàng liên quan. Nếu bỏ OVER, SUM(amount) là hàm tổng hợp thông thường và thường trả một hàng cho toàn bộ tập dữ liệu (hoặc một hàng cho mỗi nhóm nếu có GROUP BY). Khi dùng SUM(amount) OVER (...), kết quả được tính theo cửa sổ nhưng vẫn gắn với từng hàng.

MySQL hỗ trợ window functions từ dòng MySQL 8.0. Nếu ứng dụng còn chạy MySQL 5.7, các truy vấn dùng OVER, PARTITION BY hoặc window function sẽ không hoạt động; cần nâng cấp hoặc viết lại bằng truy vấn con, self-join hay kỹ thuật khác.

## 2. Dữ liệu mẫu cho các ví dụ

Tạo bảng doanh số:

~~~sql
CREATE TABLE sales_demo (
    sale_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    salesperson_id BIGINT UNSIGNED NOT NULL,
    region VARCHAR(30) NOT NULL,
    sale_date DATE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    KEY idx_sales_person_date (salesperson_id, sale_date, sale_id),
    KEY idx_sales_region_date (region, sale_date)
) ENGINE = InnoDB;

INSERT INTO sales_demo
    (sale_id, salesperson_id, region, sale_date, amount)
VALUES
    (1, 101, 'North', '2025-01-05', 100.00),
    (2, 101, 'North', '2025-01-06', 150.00),
    (3, 101, 'North', '2025-01-06', 150.00),
    (4, 101, 'North', '2025-01-09', 200.00),
    (5, 102, 'South', '2025-01-05',  80.00),
    (6, 102, 'South', '2025-01-07', 120.00),
    (7, 102, 'South', '2025-01-08', 120.00),
    (8, 102, 'South', '2025-01-10', 180.00),
    (9, 103, 'North', '2025-01-06', 150.00);
~~~

Dữ liệu có hai điểm đáng chú ý:

- Nhân viên 101 có hai giao dịch cùng ngày 06/01 và cùng số tiền 150.
- Số tiền 150 cũng xuất hiện ở nhân viên 103.

Những hàng trùng giá trị sắp xếp giúp minh họa sự khác nhau giữa PARTITION BY, ORDER BY và frame RANGE/ROWS.

## 3. PARTITION BY: chia cửa sổ thành các phân vùng

PARTITION BY chia tập hàng thành các phân vùng (partition). Window function được tính riêng trong từng partition và không trộn dữ liệu giữa các partition.

Ví dụ tính tổng doanh thu theo nhân viên:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
    ) AS salesperson_total
FROM sales_demo
ORDER BY salesperson_id, sale_id;
~~~

Kết quả logic:

| sale_id | salesperson_id | amount | salesperson_total |
|---:|---:|---:|---:|
| 1 | 101 | 100 | 600 |
| 2 | 101 | 150 | 600 |
| 3 | 101 | 150 | 600 |
| 4 | 101 | 200 | 600 |
| 5 | 102 | 80 | 500 |
| 6 | 102 | 120 | 500 |
| 7 | 102 | 120 | 500 |
| 8 | 102 | 180 | 500 |
| 9 | 103 | 150 | 150 |

Mỗi salesperson_id tạo một partition. Hàm SUM nhìn toàn bộ hàng trong partition đó và trả cùng một tổng cho mỗi hàng của nhân viên.

### 3.1. Không có PARTITION BY

Nếu bỏ PARTITION BY:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    SUM(amount) OVER () AS grand_total
FROM sales_demo
ORDER BY sale_id;
~~~

Toàn bộ kết quả là một partition duy nhất. Mỗi hàng nhận tổng doanh thu của tất cả giao dịch trong bảng, bằng 1.250.

OVER() rỗng vẫn là một window specification hợp lệ: không chia partition, không sắp xếp và không giới hạn frame tường minh. Với hàm tổng hợp cửa sổ, mỗi hàng có thể nhận tổng trên toàn bộ tập hàng của query block.

### 3.2. PARTITION BY nhiều cột

Có thể chia partition theo nhiều thuộc tính:

~~~sql
SELECT
    sale_id,
    region,
    salesperson_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY region, salesperson_id
    ) AS region_person_total
FROM sales_demo
ORDER BY region, salesperson_id, sale_id;
~~~

Mỗi cặp region và salesperson_id tạo một partition. Thứ tự các biểu thức trong PARTITION BY không làm thay đổi ý nghĩa của nhóm tương đương, nhưng nên sắp xếp theo cách dễ đọc và thống nhất với schema.

### 3.3. PARTITION BY biểu thức

Có thể dùng biểu thức thay cho cột trực tiếp:

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY YEAR(sale_date)
    ) AS year_total
FROM sales_demo;
~~~

Các hàng có cùng năm được đặt trong cùng partition. Nếu biểu thức phức tạp hoặc được dùng nhiều lần, cân nhắc tạo cột sinh (generated column) hay chuẩn bị dữ liệu trước để truy vấn rõ ràng hơn.

### 3.4. NULL trong PARTITION BY

Nếu biểu thức partition có giá trị NULL, các hàng có giá trị NULL tương ứng được xếp vào cùng một partition. Điều này phù hợp với mục tiêu phân vùng, nhưng cần chú ý nếu NULL biểu thị nhiều trạng thái nghiệp vụ khác nhau.

Nếu muốn tách nhóm NULL khỏi một số nhóm cụ thể, có thể dùng biểu thức CASE trong PARTITION BY để gán nhãn phân vùng rõ ràng. Chỉ làm vậy khi quy tắc nhóm thực sự yêu cầu.

## 4. ORDER BY bên trong OVER: thứ tự tính toán

ORDER BY trong OVER xác định thứ tự các hàng trong mỗi partition. Thứ tự này quan trọng với các hàm xếp hạng, hàm lấy hàng trước/sau và phép tổng hợp lũy kế.

Ví dụ đánh số giao dịch theo ngày trong từng nhân viên:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
    ) AS sale_sequence
FROM sales_demo
ORDER BY salesperson_id, sale_sequence;
~~~

Với mỗi salesperson_id, hàng được sắp theo sale_date tăng dần, sau đó sale_id tăng dần. ROW_NUMBER gán số 1, 2, 3... trong từng partition.

### 4.1. ORDER BY nhiều cột

Khi cột đầu tiên có giá trị trùng, cột tiếp theo dùng để phá hòa (tie-breaker).

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY salesperson_id
    ORDER BY sale_date ASC, amount DESC, sale_id ASC
)
~~~

Thứ tự trên có nghĩa:
1. Ngày bán sớm hơn trước.
2. Nếu cùng ngày, số tiền lớn hơn trước.
3. Nếu vẫn trùng, sale_id nhỏ hơn trước.

Nếu ORDER BY không tạo thứ tự duy nhất, các hàng đồng hạng có thể được đánh số theo thứ tự không xác định. Khi cần kết quả lặp lại ổn định, thêm khóa duy nhất hoặc tie-breaker phù hợp.

### 4.2. ASC và DESC

Mặc định ORDER BY dùng ASC. Có thể khai báo rõ:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC, sale_id ASC
    ) AS amount_position
FROM sales_demo;
~~~

Đơn có số tiền cao hơn được xếp trước trong từng nhân viên. sale_id dùng để phân biệt các đơn có cùng amount.

### 4.3. ORDER BY trong OVER không sắp xếp kết quả cuối

Đây là khác biệt rất quan trọng:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC, sale_id
    ) AS amount_position
FROM sales_demo;
~~~

ORDER BY trong OVER chỉ điều khiển cách tính ROW_NUMBER. Nó không bảo đảm thứ tự hàng được trả về cho client.

Muốn kết quả cuối được sắp xếp, phải có ORDER BY ngoài cùng:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC, sale_id
    ) AS amount_position
FROM sales_demo
ORDER BY salesperson_id, amount_position;
~~~

Một truy vấn có thể có cả ORDER BY trong OVER và ORDER BY ngoài cùng. Hai mệnh đề phục vụ hai mục đích khác nhau.

## 5. Phân biệt PARTITION BY với GROUP BY

PARTITION BY và GROUP BY đều chia dữ liệu theo nhóm, nhưng kết quả khác nhau.

### 5.1. GROUP BY gom hàng

~~~sql
SELECT
    salesperson_id,
    SUM(amount) AS total_amount
FROM sales_demo
GROUP BY salesperson_id;
~~~

Kết quả có một hàng cho mỗi salesperson_id. Các giao dịch chi tiết không còn xuất hiện riêng.

### 5.2. PARTITION BY giữ hàng chi tiết

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
    ) AS total_amount
FROM sales_demo;
~~~

Kết quả vẫn có một hàng cho mỗi giao dịch. Tổng theo nhân viên được thêm vào từng hàng.

| Nhu cầu | Cách dùng |
|---|---|
| Một hàng cho mỗi nhóm | GROUP BY |
| Giữ chi tiết từng hàng và thêm số liệu nhóm | Window function với PARTITION BY |
| Lọc nhóm theo giá trị tổng hợp | HAVING hoặc derived table/CTE |
| Lọc hàng theo kết quả window function | Derived table hoặc CTE ở query block ngoài |

### 5.3. Kết hợp GROUP BY và window function

Window function có thể chạy trên kết quả đã được nhóm của query block:

~~~sql
SELECT
    region,
    salesperson_id,
    SUM(amount) AS revenue,
    RANK() OVER (
        PARTITION BY region
        ORDER BY SUM(amount) DESC
    ) AS region_rank
FROM sales_demo
GROUP BY region, salesperson_id
ORDER BY region, region_rank;
~~~

Truy vấn đầu tiên tạo một hàng cho mỗi cặp region và salesperson_id, tính doanh thu. Sau đó RANK xếp hạng các hàng tổng hợp trong từng region.

## 6. Hàm xếp hạng và vai trò của ORDER BY

Ba hàm thường dùng:

- ROW_NUMBER(): đánh số liên tục từng hàng.
- RANK(): các hàng đồng hạng nhận cùng hạng; hạng tiếp theo bị bỏ qua.
- DENSE_RANK(): các hàng đồng hạng nhận cùng hạng; hạng tiếp theo không bị bỏ qua.

Ví dụ xếp hạng số tiền theo nhân viên:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC
    ) AS row_num,
    RANK() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC
    ) AS amount_rank,
    DENSE_RANK() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC
    ) AS dense_amount_rank
FROM sales_demo
ORDER BY salesperson_id, amount DESC, sale_id;
~~~

Với nhân viên 101, các số tiền theo thứ tự là 200, 150, 150, 100:

| amount | ROW_NUMBER | RANK | DENSE_RANK |
|---:|---:|---:|---:|
| 200 | 1 | 1 | 1 |
| 150 | 2 hoặc 3 | 2 | 2 |
| 150 | 2 hoặc 3 | 2 | 2 |
| 100 | 4 | 4 | 3 |

ROW_NUMBER phân biệt từng hàng, nên thứ tự giữa hai hàng amount 150 không xác định nếu không có tie-breaker. RANK và DENSE_RANK coi chúng là đồng hạng vì ORDER BY của hai hàm chỉ xét amount.

Nếu thêm sale_id vào ORDER BY của RANK, hai giao dịch amount 150 sẽ không còn là peer (hàng đồng hạng) vì toàn bộ khóa sắp xếp khác nhau. Chỉ thêm tie-breaker vào ROW_NUMBER nếu mục tiêu là đánh số ổn định; không thêm vào RANK nếu muốn giữ ý nghĩa đồng hạng theo amount.

## 7. ORDER BY và peer rows

Các hàng là peer nếu chúng có cùng giá trị ở tất cả biểu thức ORDER BY của cửa sổ. Peer rows có ý nghĩa với RANK, DENSE_RANK và frame kiểu RANGE.

Ví dụ:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    RANK() OVER (
        PARTITION BY salesperson_id
        ORDER BY amount DESC
    ) AS amount_rank
FROM sales_demo;
~~~

Hai hàng có amount bằng nhau trong cùng partition là peer và nhận cùng rank.

Nếu ORDER BY gồm nhiều biểu thức, các hàng chỉ là peer khi tất cả biểu thức sắp xếp đều bằng nhau theo quy tắc so sánh tương ứng.

Không nhầm peer rows với hai hàng có cùng một cột bất kỳ. Phải xét toàn bộ danh sách ORDER BY trong window specification.

## 8. Frame clause: giới hạn hàng dùng cho phép tính

PARTITION BY xác định nhóm lớn; ORDER BY xác định thứ tự; frame clause xác định tập hàng cụ thể mà một số hàm cửa sổ dùng quanh hàng hiện tại.

Hai loại frame chính:

- ROWS: xác định theo số hàng vật lý trước/sau hàng hiện tại trong thứ tự cửa sổ.
- RANGE: xác định theo giá trị của biểu thức ORDER BY và nhóm peer tương ứng.

Cú pháp tổng quát:

~~~sql
ROWS | RANGE
    BETWEEN frame_start AND frame_end
~~~

Một số ranh giới thường gặp:

| Ranh giới | Ý nghĩa |
|---|---|
| UNBOUNDED PRECEDING | Bắt đầu từ đầu partition |
| n PRECEDING | n hàng hoặc khoảng giá trị trước hàng hiện tại, tùy ROWS/RANGE |
| CURRENT ROW | Hàng hiện tại; với RANGE còn liên quan peer rows |
| n FOLLOWING | n hàng hoặc khoảng giá trị sau hàng hiện tại, tùy ROWS/RANGE |
| UNBOUNDED FOLLOWING | Kết thúc ở cuối partition |

Ví dụ frame từ đầu partition đến hàng hiện tại:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Ví dụ cửa sổ gồm hai hàng trước, hàng hiện tại và hai hàng sau:

~~~sql
ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
~~~

Frame đặc biệt hữu ích cho SUM, AVG, COUNT, FIRST_VALUE, LAST_VALUE và NTH_VALUE. Các hàm xếp hạng như ROW_NUMBER, RANK và DENSE_RANK dựa trên partition/order và không dùng frame theo cách các hàm tổng hợp hoặc value functions sử dụng.

## 9. Frame mặc định và ảnh hưởng của ORDER BY

Khi không khai báo frame tường minh, MySQL áp dụng frame mặc định. Với window có ORDER BY, frame mặc định là:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Nếu window không có ORDER BY, frame mặc định là toàn bộ partition:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

Điều này có thể tạo ra kết quả bất ngờ khi ORDER BY có các giá trị trùng nhau.

### 9.1. Ví dụ tổng lũy kế với frame mặc định RANGE

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date
    ) AS running_total_default
FROM sales_demo
WHERE salesperson_id = 101
ORDER BY sale_date, sale_id;
~~~

Nhân viên 101 có hai giao dịch cùng sale_date 2025-01-06. Vì frame mặc định là RANGE đến CURRENT ROW, cả hai hàng cùng ngày là peer và được tính trong cùng frame. Do đó, cả hai hàng ngày 06/01 có thể nhận cùng tổng lũy kế, bao gồm cả hai giao dịch ngày đó.

Nếu muốn cộng từng hàng theo thứ tự riêng biệt, dùng ROWS và một thứ tự xác định:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total_rows
FROM sales_demo
WHERE salesperson_id = 101
ORDER BY sale_date, sale_id;
~~~

Kết quả lũy kế theo từng giao dịch của nhân viên 101 là 100, 250, 400 và 600.

### 9.2. Vì sao nên khai báo frame rõ ràng?

Frame mặc định có thể đúng với một số báo cáo nhưng không phải lúc nào cũng đúng với ý định nghiệp vụ. Nếu cần tổng lũy kế theo từng hàng, hãy ghi rõ ROWS. Nếu cần cộng toàn bộ peer cùng giá trị ORDER BY, RANGE có thể phù hợp.

Việc khai báo tường minh giúp:
- Người đọc biết chính xác tập hàng được tính.
- Tránh thay đổi kết quả ngoài ý muốn khi bổ sung cột vào ORDER BY.
- Làm rõ cách xử lý hàng có giá trị sắp xếp trùng nhau.
- Giảm phụ thuộc vào frame mặc định.

## 10. ROWS và RANGE khác nhau như thế nào?

Giả sử có các giao dịch theo ngày:

| sale_id | sale_date | amount |
|---:|---|---:|
| 1 | 2025-01-05 | 100 |
| 2 | 2025-01-06 | 150 |
| 3 | 2025-01-06 | 150 |
| 4 | 2025-01-09 | 200 |

Dùng ROWS:

~~~sql
SUM(amount) OVER (
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Mỗi hàng được cộng lần lượt theo thứ tự xác định. Hàng thứ hai có tổng 250, hàng thứ ba có tổng 400.

Dùng RANGE:

~~~sql
SUM(amount) OVER (
    ORDER BY sale_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Các hàng cùng ngày là peer. Hai hàng ngày 06/01 cùng nhìn thấy cả hai giao dịch ngày đó, nên nhận cùng tổng 400.

| Loại frame | Cách xác định | Tác động với hàng đồng hạng |
|---|---|---|
| ROWS | Số vị trí hàng trong thứ tự cửa sổ | Mỗi hàng có vị trí riêng nếu ORDER BY tạo thứ tự xác định |
| RANGE | Giá trị ORDER BY và peer group | Các peer có thể nhận cùng frame |
 
Với ROWS, hãy thêm tie-breaker duy nhất nếu kết quả theo từng hàng cần ổn định. Với RANGE, không thêm cột phân biệt nếu mục tiêu là giữ peer theo giá trị nghiệp vụ đang xét.

## 11. ORDER BY trong OVER với các hàm tổng hợp

Window aggregate cho phép tính tổng, trung bình, đếm, nhỏ nhất và lớn nhất mà vẫn giữ hàng chi tiết.

### 11.1. Tổng toàn partition

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
    ) AS person_total
FROM sales_demo;
~~~

Không có ORDER BY nên frame mặc định bao phủ toàn partition. Mỗi hàng nhận tổng của nhân viên.

### 11.2. Tổng lũy kế

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_demo;
~~~

Mỗi hàng nhận tổng từ đầu partition đến hàng hiện tại.

### 11.3. Trung bình trượt ba giao dịch

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    AVG(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_average_3_sales
FROM sales_demo;
~~~

Frame gồm tối đa ba hàng: hai giao dịch trước và giao dịch hiện tại. Ở đầu partition, frame có ít hơn ba hàng vì không có đủ hàng phía trước.

### 11.4. Đếm hàng trong cửa sổ

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    COUNT(*) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rows_in_window
FROM sales_demo;
~~~

COUNT(*) cho biết số hàng thực tế trong frame. Nếu đếm một cột nullable, COUNT(column) bỏ qua giá trị NULL trong frame.

## 12. FIRST_VALUE, LAST_VALUE và NTH_VALUE

Các hàm value window lấy giá trị từ một vị trí trong frame.

### 12.1. FIRST_VALUE

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    FIRST_VALUE(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS first_sale_amount
FROM sales_demo;
~~~

FIRST_VALUE trả giá trị amount ở hàng đầu tiên của frame. Với frame bắt đầu từ đầu partition, giá trị đầu tiên thường là số tiền của giao dịch sớm nhất theo thứ tự đã khai báo.

### 12.2. LAST_VALUE và bẫy frame mặc định

Một truy vấn dễ gây nhầm:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
    ) AS last_value_default
FROM sales_demo;
~~~

Vì frame mặc định kết thúc tại CURRENT ROW, LAST_VALUE thường trả amount của hàng hiện tại (hoặc hàng cuối của frame hiện tại), chứ không phải giao dịch cuối cùng của toàn partition.

Nếu cần giá trị của hàng cuối toàn partition, hãy mở rộng frame tới UNBOUNDED FOLLOWING:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_sale_amount
FROM sales_demo;
~~~

Đây là một trong những lý do quan trọng để hiểu frame thay vì chỉ nhìn PARTITION BY và ORDER BY.

### 12.3. NTH_VALUE

~~~sql
SELECT
    sale_id,
    salesperson_id,
    amount,
    NTH_VALUE(amount, 2) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS second_sale_amount
FROM sales_demo;
~~~

NTH_VALUE lấy giá trị ở vị trí thứ N trong frame. Vị trí bắt đầu từ 1. Nếu frame không có đủ hàng, kết quả là NULL.

## 13. LAG và LEAD: truy cập hàng trước/sau

LAG và LEAD dùng ORDER BY để xác định hàng trước hoặc sau trong partition.

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    LAG(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
    ) AS previous_amount,
    LEAD(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
    ) AS next_amount
FROM sales_demo
ORDER BY salesperson_id, sale_date, sale_id;
~~~

- LAG(amount) lấy amount của hàng trước.
- LEAD(amount) lấy amount của hàng sau.
- Ở đầu hoặc cuối partition, nếu không có hàng tương ứng, kết quả mặc định là NULL.

Có thể chỉ định offset và giá trị thay thế:

~~~sql
LAG(amount, 1, 0) OVER (
    PARTITION BY salesperson_id
    ORDER BY sale_date, sale_id
)
~~~

Đối số thứ hai là số hàng lùi; đối số thứ ba là giá trị trả về nếu không có hàng trước. Không dùng 0 nếu muốn giữ ý nghĩa “không có giao dịch trước” bằng NULL.

LAG/LEAD phụ thuộc thứ tự trong OVER. Nếu ORDER BY không duy nhất, việc xác định hàng trước/sau có thể không ổn định. Thêm tie-breaker nếu nghiệp vụ yêu cầu thứ tự cụ thể.

## 14. Named window: tái sử dụng cấu hình OVER

Nếu nhiều hàm dùng cùng PARTITION BY và ORDER BY, có thể đặt tên cửa sổ trong mệnh đề WINDOW.

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    ROW_NUMBER() OVER w AS row_num,
    SUM(amount) OVER w AS running_total,
    AVG(amount) OVER w AS running_average
FROM sales_demo
WINDOW w AS (
    PARTITION BY salesperson_id
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY salesperson_id, sale_date, sale_id;
~~~

Cấu hình w được định nghĩa một lần và dùng lại cho nhiều hàm. Điều này giảm lặp và giúp các phép tính chia sẻ cùng quy tắc cửa sổ.

Mệnh đề WINDOW nằm sau FROM/WHERE/GROUP BY/HAVING và trước ORDER BY cuối cùng trong cú pháp SELECT của MySQL.

Named window không phải bảng hay view; nó chỉ là tên cho một window specification trong phạm vi câu SELECT. Không thể tham chiếu tên cửa sổ ở một câu lệnh khác.

## 15. Window function và thứ tự xử lý truy vấn

Window function được tính trên tập hàng đã qua các bước lọc và nhóm của query block. Vì vậy, nó không thể được dùng trực tiếp trong WHERE, GROUP BY hoặc HAVING cùng query block.

Ví dụ không hợp lệ:

~~~sql
SELECT
    sale_id,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
    ) AS row_num
FROM sales_demo
WHERE row_num <= 2;
~~~

Alias row_num chưa có ở thời điểm WHERE được đánh giá, và window function không được phép đặt trực tiếp trong WHERE.

Hãy bọc kết quả bằng derived table:

~~~sql
SELECT
    ranked.sale_id,
    ranked.salesperson_id,
    ranked.sale_date,
    ranked.amount,
    ranked.row_num
FROM (
    SELECT
        sale_id,
        salesperson_id,
        sale_date,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY salesperson_id
            ORDER BY sale_date, sale_id
        ) AS row_num
    FROM sales_demo
) AS ranked
WHERE ranked.row_num <= 2
ORDER BY ranked.salesperson_id, ranked.row_num;
~~~

Hoặc dùng CTE:

~~~sql
WITH ranked_sales AS (
    SELECT
        sale_id,
        salesperson_id,
        sale_date,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY salesperson_id
            ORDER BY sale_date, sale_id
        ) AS row_num
    FROM sales_demo
)
SELECT *
FROM ranked_sales
WHERE row_num <= 2
ORDER BY salesperson_id, row_num;
~~~

Đây là mẫu top-N theo từng nhóm phổ biến: tính rank trong query block trong, sau đó lọc rank ở query block ngoài.

### 15.1. WHERE trước window function

Nếu viết:

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_demo
WHERE sale_date >= '2025-01-07';
~~~

Các hàng trước ngày 07/01 bị loại trước khi window function tính toán. Running total bắt đầu từ hàng đầu tiên còn lại, không bao gồm lịch sử trước ngày đó.

Nếu nghiệp vụ muốn tính lũy kế trên toàn bộ lịch sử rồi chỉ hiển thị từ ngày 07/01, cần tính window ở query block trong và lọc ngày ở ngoài:

~~~sql
WITH all_running_sales AS (
    SELECT
        sale_id,
        salesperson_id,
        sale_date,
        amount,
        SUM(amount) OVER (
            PARTITION BY salesperson_id
            ORDER BY sale_date, sale_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_total
    FROM sales_demo
)
SELECT *
FROM all_running_sales
WHERE sale_date >= '2025-01-07'
ORDER BY salesperson_id, sale_date, sale_id;
~~~

Vị trí của điều kiện lọc làm thay đổi ý nghĩa phân tích. Hãy xác định muốn tính trên toàn bộ lịch sử hay chỉ trên tập dữ liệu đã lọc.

## 16. NULL, kiểu dữ liệu và thứ tự trong cửa sổ

### 16.1. NULL trong ORDER BY

Trong MySQL, khi sắp xếp:
- ASC: NULL được xếp trước giá trị không NULL.
- DESC: NULL được xếp sau giá trị không NULL.

Nếu cần vị trí cụ thể, có thể thêm biểu thức:

~~~sql
ORDER BY
    (event_time IS NULL),
    event_time ASC
~~~

Biểu thức boolean đầu tiên đưa hàng có event_time NULL xuống sau khi sắp xếp tăng dần (FALSE trước TRUE). Hãy dùng cùng nguyên tắc trong ORDER BY của OVER nếu thứ tự xử lý cần như vậy.

### 16.2. NULL trong aggregate window

SUM, AVG, MIN và MAX bỏ qua giá trị NULL theo quy tắc của hàm tổng hợp. COUNT(expression) bỏ qua NULL, còn COUNT(*) đếm hàng trong frame.

Nếu toàn bộ giá trị của frame là NULL, SUM/AVG/MIN/MAX có thể trả NULL. Không tự đổi thành 0 nếu nghiệp vụ cần phân biệt “không có dữ liệu” với “tổng bằng 0”.

### 16.3. Kiểu dữ liệu và độ chính xác

Với dữ liệu tiền, dùng DECIMAL thay vì FLOAT/DOUBLE nếu cần số học thập phân chính xác. Window SUM trên DECIMAL giữ ngữ nghĩa số thập phân theo quy tắc kiểu dữ liệu MySQL.

Nếu ORDER BY trên chuỗi, collation quyết định thứ tự so sánh. Với dữ liệu tiếng Việt, chọn collation đúng với yêu cầu phân biệt hoa/thường, dấu và thứ tự ngôn ngữ.

## 17. Hiệu năng và index cho window function

Window function có thể yêu cầu MySQL sắp xếp hàng theo PARTITION BY và ORDER BY. Với tập dữ liệu lớn, thao tác sắp xếp hoặc lưu kết quả trung gian có thể tốn CPU, bộ nhớ và I/O.

### 17.1. Index theo partition và order

Ví dụ cửa sổ:

~~~sql
SUM(amount) OVER (
    PARTITION BY salesperson_id
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Một index có thứ tự:

~~~sql
CREATE INDEX idx_sales_person_date
ON sales_demo (salesperson_id, sale_date, sale_id);
~~~

có cấu trúc phù hợp với partition key và order key. Index có thể giúp truy cập dữ liệu theo thứ tự hữu ích, nhưng không bảo đảm MySQL luôn loại bỏ mọi bước sort hoặc materialization. Optimizer còn xét filter, cardinality, covering, join và chi phí tổng thể.

### 17.2. Lọc dữ liệu trước khi tính cửa sổ

Nếu chỉ cần phân tích một khoảng thời gian và nghiệp vụ cho phép bỏ lịch sử ngoài khoảng, đặt WHERE trong query block trước window function để giảm số hàng.

~~~sql
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS period_running_total
FROM sales_demo
WHERE sale_date >= '2025-01-01'
  AND sale_date <  '2025-02-01';
~~~

Chỉ làm vậy khi tổng lũy kế cần tính riêng trong khoảng thời gian. Nếu cần tổng lũy kế toàn lịch sử rồi lọc phần hiển thị, hãy dùng CTE/derived table như mục trước.

### 17.3. Không tạo index cho mọi tổ hợp cửa sổ

Một truy vấn có thể dùng nhiều cửa sổ với partition/order khác nhau. Tạo index cho từng tổ hợp có thể làm tăng dung lượng và chi phí INSERT/UPDATE/DELETE.

Hãy:
- Xác định các truy vấn phân tích thường chạy.
- Tìm tổ hợp PARTITION BY/ORDER BY xuất hiện thường xuyên.
- Đánh giá index theo điều kiện WHERE và JOIN trước.
- Dùng EXPLAIN để xem access path, sort và temporary operation.
- Đo bằng dữ liệu gần với production.

### 17.4. Kiểm tra kế hoạch thực thi

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_demo;
~~~

Trên MySQL 8.0, có thể dùng EXPLAIN ANALYZE để đo thực thi thực tế:

~~~sql
EXPLAIN ANALYZE
SELECT
    sale_id,
    salesperson_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_demo;
~~~

EXPLAIN ANALYZE thực thi truy vấn SELECT. Dùng trên môi trường phù hợp, nhất là khi truy vấn quét lượng dữ liệu lớn.

## 18. Các lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ PARTITION BY làm giảm số hàng | Nhầm với GROUP BY | Window function giữ hàng chi tiết |
| Nghĩ ORDER BY trong OVER sắp xếp kết quả cuối | Nhầm thứ tự tính với thứ tự hiển thị | Thêm ORDER BY ngoài cùng |
| ROW_NUMBER thay đổi giữa các lần chạy | ORDER BY không duy nhất | Thêm tie-breaker ổn định |
| RANK không còn đồng hạng | Đưa khóa duy nhất vào ORDER BY của RANK | Chỉ sắp theo tiêu chí dùng để xác định đồng hạng |
| Tổng lũy kế nhảy theo nhóm peer | Frame mặc định RANGE và ORDER BY có giá trị trùng | Dùng ROWS với thứ tự xác định nếu cần từng hàng |
| LAST_VALUE trả giá trị hiện tại | Frame mặc định kết thúc ở CURRENT ROW | Mở frame tới UNBOUNDED FOLLOWING |
| Window alias không dùng được trong WHERE | Window được tính sau WHERE | Bọc trong derived table hoặc CTE |
| Lọc ngày làm tổng lũy kế bắt đầu lại | WHERE loại lịch sử trước khi window tính | Tính window trong query block trong rồi lọc ngoài |
| Truy vấn chậm do sort lớn | Partition/order trên nhiều hàng, thiếu access path phù hợp | Xem EXPLAIN, lọc hợp lệ và đánh giá index |
| Cùng hàm nhưng kết quả khác sau khi thêm ORDER BY | Frame mặc định thay đổi theo window có ORDER BY | Khai báo frame tường minh |
| Dùng MySQL 5.7 báo lỗi OVER | Phiên bản chưa hỗ trợ window function | Nâng cấp hoặc viết lại truy vấn |

## 19. Quy trình thiết kế window specification

Khi viết một window function, hãy trả lời lần lượt:

1. Mỗi hàng đầu ra đại diện cho thực thể nào?
2. Hàm cần nhìn toàn bộ kết quả hay chỉ nhóm liên quan?
3. PARTITION BY gồm những cột nào?
4. Thứ tự tính toán cần tăng hay giảm?
5. Có giá trị ORDER BY trùng nhau không?
6. Có cần tie-breaker để xác định thứ tự duy nhất không?
7. Hàm có cần frame không? Nếu có, dùng ROWS hay RANGE?
8. Frame mặc định có đúng ý nghĩa nghiệp vụ không?
9. Có cần lọc theo kết quả window không? Nếu có, dùng query block ngoài.
10. WHERE đặt trước hay sau window theo mục tiêu tính toán?
11. Có thể tái sử dụng cấu hình bằng named window không?
12. Index và kế hoạch thực thi có đáp ứng quy mô dữ liệu không?

## 20. Bài tập thực hành

### Bài 1: Tổng doanh thu theo nhân viên

Dùng sales_demo để tính SUM(amount) OVER (PARTITION BY salesperson_id). Xác nhận tổng được lặp trên từng hàng và không làm giảm số hàng.

### Bài 2: Tổng toàn bộ bảng

Bỏ PARTITION BY và tính SUM(amount) OVER (). So sánh kết quả với SELECT SUM(amount) thông thường.

### Bài 3: Xếp thứ tự giao dịch

Dùng ROW_NUMBER() OVER (PARTITION BY salesperson_id ORDER BY sale_date, sale_id). Thử bỏ sale_id rồi quan sát vì sao thứ tự của hai giao dịch cùng ngày không được xác định.

### Bài 4: So sánh RANK và DENSE_RANK

Xếp hạng amount giảm dần trong từng nhân viên. Tạo các giá trị amount trùng và so sánh khoảng trống hạng của RANK với DENSE_RANK.

### Bài 5: Tổng lũy kế ROWS và RANGE

Tính SUM(amount) với frame mặc định, với ROWS và với RANGE. Dùng dữ liệu có hai giao dịch cùng ngày để giải thích vì sao kết quả khác nhau.

### Bài 6: Trung bình trượt

Tính AVG(amount) trên ba giao dịch gần nhất trong từng nhân viên bằng ROWS BETWEEN 2 PRECEDING AND CURRENT ROW. Kiểm tra các hàng đầu partition có frame ngắn hơn ba hàng.

### Bài 7: LAST_VALUE

Dùng LAST_VALUE(amount) với frame mặc định và với ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING. Giải thích vì sao cần khai báo frame khi muốn lấy giá trị cuối toàn partition.

### Bài 8: LAG và LEAD

Tính số tiền giao dịch trước và sau trong từng nhân viên. Dùng COALESCE hoặc giá trị mặc định của LAG/LEAD nếu nghiệp vụ yêu cầu hiển thị 0, đồng thời phân biệt trường hợp không có hàng với giá trị thực sự bằng 0.

### Bài 9: Top 2 giao dịch mỗi nhân viên

Tính ROW_NUMBER trong CTE hoặc derived table, sau đó lọc row_num <= 2 ở query ngoài. Thử thêm nhân viên chưa có giao dịch để đánh giá kết quả khi kết hợp LEFT JOIN.

### Bài 10: Kiểm tra hiệu năng

Tạo hoặc bỏ index (salesperson_id, sale_date, sale_id). So sánh EXPLAIN và EXPLAIN ANALYZE cho truy vấn tổng lũy kế. Ghi nhận sort, số hàng và thời gian thực thi.

## 21. Checklist trước khi đưa window function vào ứng dụng

- [ ] Server chạy MySQL 8.0 trở lên.
- [ ] Đã xác định hàm cần dùng và mục tiêu phân tích.
- [ ] PARTITION BY phản ánh đúng nhóm nghiệp vụ.
- [ ] ORDER BY phản ánh đúng thứ tự tính toán.
- [ ] Có tie-breaker nếu cần thứ tự từng hàng ổn định.
- [ ] Đã phân biệt ORDER BY trong OVER với ORDER BY ngoài cùng.
- [ ] Đã phân biệt PARTITION BY với GROUP BY.
- [ ] Đã xác định frame clause và chọn ROWS/RANGE đúng ý nghĩa.
- [ ] Đã kiểm tra frame mặc định khi có hoặc không có ORDER BY.
- [ ] Đã xử lý hàng đồng hạng (peer rows) có chủ đích.
- [ ] Đã hiểu NULL trong partition, order và aggregate.
- [ ] Đã lọc window result ở derived table hoặc CTE.
- [ ] Đã đặt WHERE đúng trước/sau window theo phạm vi lịch sử cần tính.
- [ ] Đã cân nhắc named window nếu nhiều hàm dùng chung specification.
- [ ] Đã xem EXPLAIN và đo trên dữ liệu đại diện.
- [ ] Đã kiểm thử dữ liệu biên: partition rỗng, một hàng, nhiều hàng đồng hạng và NULL.

## 22. Kết luận

OVER xác định cửa sổ mà window function dùng để tính. PARTITION BY chia dữ liệu thành các nhóm độc lập nhưng vẫn giữ từng hàng; ORDER BY xác định thứ tự xử lý trong mỗi nhóm. ORDER BY trong OVER không bảo đảm thứ tự kết quả cuối, vì vậy cần ORDER BY ngoài cùng khi giao diện hoặc báo cáo yêu cầu thứ tự cụ thể.

Frame clause xác định tập hàng cụ thể quanh hàng hiện tại. Frame mặc định có ORDER BY là RANGE từ đầu partition đến CURRENT ROW, nên các peer có thể nhận cùng kết quả lũy kế. Nếu cần tính theo từng hàng, hãy dùng ROWS và thứ tự có tie-breaker. Khi cần lọc kết quả window, hãy dùng derived table hoặc CTE; khi tối ưu, kiểm tra index và kế hoạch thực thi thay vì giả định một window specification luôn được xử lý theo cách cố định.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Window Functions](https://dev.mysql.com/doc/refman/8.4/en/window-functions.html)
- [MySQL 8.4 Reference Manual – Window Function Concepts and Syntax](https://dev.mysql.com/doc/refman/8.4/en/window-functions-usage.html)
- [MySQL 8.4 Reference Manual – Window Function Descriptions](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html)
- [MySQL 8.4 Reference Manual – Window Function Frame Specification](https://dev.mysql.com/doc/refman/8.4/en/window-functions-frames.html)
- [MySQL 8.4 Reference Manual – Named Windows](https://dev.mysql.com/doc/refman/8.4/en/window-named-windows.html)
- [MySQL 8.4 Reference Manual – SELECT Statement](https://dev.mysql.com/doc/refman/8.4/en/select.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – Optimizing Window Functions](https://dev.mysql.com/doc/refman/8.4/en/window-function-optimization.html)

