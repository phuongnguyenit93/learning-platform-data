# Phân biệt hàm tổng hợp và hàm cửa sổ

Bài học thuộc chương **Hàm cửa sổ** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Hàm tổng hợp và hàm cửa sổ đều có thể tính tổng, trung bình, số lượng hoặc thứ hạng, nhưng chúng tạo ra kết quả ở những mức chi tiết khác nhau.

Sau bài này, bạn có thể phân biệt cách `GROUP BY` thu gọn hàng với `OVER()` giữ lại từng hàng, hiểu `PARTITION BY`, `ORDER BY` và window frame, sử dụng các hàm như `ROW_NUMBER()`, `RANK()`, `LAG()` và `LEAD()`, đồng thời lọc kết quả cửa sổ qua CTE hoặc truy vấn con.

## 1. Hai cách tổng hợp, hai dạng kết quả

Hàm tổng hợp như `SUM()`, `AVG()`, `COUNT()`, `MIN()` và `MAX()` thường được dùng cùng `GROUP BY`. MySQL gom các hàng có cùng khóa nhóm thành một nhóm và trả về một hàng cho mỗi nhóm.

Ví dụ:

~~~sql
SELECT
    salesperson,
    SUM(amount) AS sales_total
FROM sales
GROUP BY salesperson;
~~~

Nếu bảng có 100.000 giao dịch của 20 nhân viên bán hàng, kết quả chỉ có tối đa 20 hàng, mỗi hàng đại diện cho một nhân viên.

Hàm cửa sổ cũng có thể dùng hàm tổng hợp, nhưng đặt hàm trong mệnh đề `OVER()`:

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
    ) AS salesperson_total
FROM sales;
~~~

Truy vấn này vẫn trả một hàng cho mỗi giao dịch. Cột `salesperson_total` là tổng của nhân viên tương ứng và được lặp trên các hàng của nhân viên đó.

| Đặc điểm | Hàm tổng hợp với GROUP BY | Hàm cửa sổ với OVER |
|---|---|---|
| Đơn vị xử lý | Nhóm hàng | Cửa sổ hàng liên quan đến hàng hiện tại |
| Số hàng kết quả | Thường giảm còn một hàng mỗi nhóm | Giữ số hàng của tập kết quả sau FROM/WHERE/GROUP BY/HAVING |
| Có thể chia nhóm | GROUP BY | PARTITION BY |
| Có thứ tự bên trong phép tính | Không phải chức năng cốt lõi của GROUP BY | ORDER BY trong OVER |
| Có thể tính lũy kế hoặc cửa sổ trượt | Không trực tiếp trên từng hàng đã thu gọn | Có, thông qua window frame |
| Ví dụ điển hình | Tổng doanh thu mỗi nhân viên | Tổng doanh thu nhân viên hiển thị trên từng giao dịch |

Điểm cốt lõi: `GROUP BY` tạo một hàng đại diện cho mỗi nhóm; `OVER()` tính toán trên một tập hàng liên quan nhưng vẫn giữ hàng hiện tại trong tập kết quả mà hàm cửa sổ nhận được. Nếu truy vấn đã GROUP BY, các hàng đó là hàng đã được nhóm.

## 2. Bộ dữ liệu dùng trong bài

Ta dùng bảng `sales` với mỗi hàng đại diện cho một giao dịch bán hàng.

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `sale_id` | INT | Mã giao dịch duy nhất |
| `salesperson` | VARCHAR(50) | Nhân viên bán hàng |
| `sale_date` | DATE | Ngày giao dịch |
| `amount` | DECIMAL(12,2) | Giá trị giao dịch |

Tạo bảng và dữ liệu mẫu:

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_window_functions_lab;
USE mysql_window_functions_lab;

CREATE TABLE sales (
    sale_id INT NOT NULL PRIMARY KEY,
    salesperson VARCHAR(50) NOT NULL,
    sale_date DATE NOT NULL,
    amount DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;

INSERT INTO sales (sale_id, salesperson, sale_date, amount)
VALUES
    (1, 'An',   '2026-01-01', 100.00),
    (2, 'An',   '2026-01-02', 150.00),
    (3, 'An',   '2026-01-02',  50.00),
    (4, 'Binh', '2026-01-01', 200.00),
    (5, 'Binh', '2026-01-03', 100.00);
~~~

Tổng đúng theo nhân viên:

| Nhân viên | Số giao dịch | Tổng doanh thu |
|---|---:|---:|
| An | 3 | 300.00 |
| Binh | 2 | 300.00 |

Dữ liệu có hai giao dịch của An cùng ngày 02-01-2026. Điều này hữu ích để quan sát sự khác nhau giữa `ROWS` và `RANGE` trong window frame.

## 3. Cú pháp hàm cửa sổ

Cấu trúc tổng quát:

~~~sql
window_function(expression)
OVER (
    [PARTITION BY partition_expression [, ...]]
    [ORDER BY sort_expression [ASC | DESC] [, ...]]
    [frame_clause]
)
~~~

Các phần chính:

- **Hàm cửa sổ:** hàm tổng hợp như SUM/AVG/COUNT hoặc hàm chuyên dụng như ROW_NUMBER/RANK/LAG.
- **PARTITION BY:** chia tập hàng thành các phân vùng độc lập. Hàm được tính riêng trong từng phân vùng.
- **ORDER BY:** xác định thứ tự hàng dùng trong phép tính cửa sổ.
- **Window frame:** chọn phạm vi hàng cụ thể quanh hàng hiện tại trong phân vùng. Frame chủ yếu có ý nghĩa với hàm tổng hợp cửa sổ và một số hàm giá trị.

Không phải hàm cửa sổ nào cũng cần đủ các phần. Ví dụ, tổng toàn bộ tập kết quả chỉ cần:

~~~sql
SUM(amount) OVER ()
~~~

Tổng theo từng nhân viên chỉ cần PARTITION BY:

~~~sql
SUM(amount) OVER (
    PARTITION BY salesperson
)
~~~

Tổng lũy kế cần thêm ORDER BY và frame:

~~~sql
SUM(amount) OVER (
    PARTITION BY salesperson
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

## 4. PARTITION BY: chia cửa sổ thành các phân vùng

`PARTITION BY` chia các hàng thành các nhóm độc lập cho hàm cửa sổ. Nó không làm giảm số hàng kết quả như GROUP BY.

Ví dụ:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
    ) AS salesperson_total,
    AVG(amount) OVER (
        PARTITION BY salesperson
    ) AS salesperson_average,
    COUNT(*) OVER (
        PARTITION BY salesperson
    ) AS salesperson_sale_count
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

Kết quả:

| sale_id | salesperson | amount | salesperson_total | salesperson_average | salesperson_sale_count |
|---:|---|---:|---:|---:|---:|
| 1 | An | 100.00 | 300.00 | 100.00 | 3 |
| 2 | An | 150.00 | 300.00 | 100.00 | 3 |
| 3 | An | 50.00 | 300.00 | 100.00 | 3 |
| 4 | Binh | 200.00 | 300.00 | 150.00 | 2 |
| 5 | Binh | 100.00 | 300.00 | 150.00 | 2 |

Mỗi nhân viên là một phân vùng:

- An có ba hàng, tổng là 300.
- Binh có hai hàng, tổng là 300.
- Tổng và trung bình được lặp trên từng hàng thuộc phân vùng.

Nếu bỏ `PARTITION BY`, toàn bộ tập hàng trở thành một phân vùng:

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    SUM(amount) OVER () AS grand_total
FROM sales;
~~~

Mỗi hàng sẽ có `grand_total = 600.00`.

### Nhiều cột trong PARTITION BY

Có thể chia theo nhiều chiều:

~~~sql
SUM(amount) OVER (
    PARTITION BY salesperson, YEAR(sale_date)
)
~~~

Mỗi phân vùng tương ứng với một tổ hợp nhân viên và năm. Hãy chọn các cột phân vùng theo đúng câu hỏi nghiệp vụ, ví dụ tổng doanh thu theo nhân viên trong từng năm.

## 5. ORDER BY trong OVER và ORDER BY cuối truy vấn

Có hai vị trí ORDER BY với hai mục đích khác nhau:

- `ORDER BY` trong `OVER(...)` quyết định thứ tự mà hàm cửa sổ sử dụng để tính.
- `ORDER BY` ở cuối SELECT quyết định thứ tự hiển thị các hàng trong kết quả.

Ví dụ:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
    ) AS sale_sequence
FROM sales
ORDER BY amount DESC, sale_id;
~~~

Hàm ROW_NUMBER đánh số giao dịch theo ngày và mã giao dịch trong từng nhân viên. Kết quả cuối lại được hiển thị theo số tiền giảm dần.

Nếu không có ORDER BY ở cuối truy vấn, MySQL không bảo đảm thứ tự hàng trả về, kể cả khi OVER đã có ORDER BY.

### Dùng khóa phụ để xử lý giá trị bằng nhau

Nếu chỉ viết:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY salesperson
    ORDER BY sale_date
)
~~~

hai giao dịch của An cùng ngày có thể nhận thứ tự không ổn định giữa các lần thực thi. Hãy thêm cột phân biệt, thường là khóa chính:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY salesperson
    ORDER BY sale_date, sale_id
)
~~~

Quy tắc này đặc biệt quan trọng khi đánh số thứ tự, phân trang, chọn hàng đầu tiên/cuối cùng hoặc tính lũy kế.

## 6. Hàm tổng hợp có thể trở thành hàm cửa sổ

Các hàm tổng hợp quen thuộc có thể được dùng với OVER:

| Hàm | Không có OVER | Có OVER |
|---|---|---|
| `SUM()` | Tổng một nhóm hoặc toàn bộ tập | Tổng trên phân vùng/frame cho từng hàng |
| `AVG()` | Trung bình một nhóm hoặc toàn bộ tập | Trung bình trên phân vùng/frame cho từng hàng |
| `COUNT()` | Số hàng trong nhóm hoặc tập | Số hàng trong phân vùng/frame cho từng hàng |
| `MIN()` | Giá trị nhỏ nhất của nhóm/tập | Giá trị nhỏ nhất trên phân vùng/frame |
| `MAX()` | Giá trị lớn nhất của nhóm/tập | Giá trị lớn nhất trên phân vùng/frame |

Ví dụ so sánh:

~~~sql
-- Một hàng cho mỗi nhân viên
SELECT
    salesperson,
    SUM(amount) AS total_amount
FROM sales
GROUP BY salesperson;
~~~

~~~sql
-- Một hàng cho mỗi giao dịch, kèm tổng của nhân viên
SELECT
    sale_id,
    salesperson,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
    ) AS total_amount
FROM sales;
~~~

Có thể kết hợp cả hai dạng trong cùng một câu lệnh nhiều tầng. Ví dụ, trước tiên tính doanh thu theo nhân viên bằng GROUP BY, sau đó dùng hàm cửa sổ để tính tổng doanh thu toàn công ty trên các hàng đã nhóm:

~~~sql
WITH salesperson_totals AS (
    SELECT
        salesperson,
        SUM(amount) AS salesperson_total
    FROM sales
    GROUP BY salesperson
)
SELECT
    salesperson,
    salesperson_total,
    SUM(salesperson_total) OVER () AS company_total,
    salesperson_total
        / NULLIF(SUM(salesperson_total) OVER (), 0) AS revenue_share
FROM salesperson_totals;
~~~

Kết quả có hai hàng, một hàng cho mỗi nhân viên, cùng tổng doanh thu công ty và tỷ trọng của nhân viên đó.

## 7. Window frame: chọn những hàng tham gia phép tính

Một phân vùng có thể chứa nhiều hàng, nhưng đôi khi hàm chỉ cần nhìn một phần của phân vùng quanh hàng hiện tại. Phần đó gọi là **window frame**.

Frame được xác định bằng `ROWS` hoặc `RANGE` cùng điểm bắt đầu và kết thúc.

Một số mốc thường dùng:

| Mốc | Ý nghĩa |
|---|---|
| `UNBOUNDED PRECEDING` | Từ đầu phân vùng |
| `n PRECEDING` | Lùi n hàng hoặc giá trị theo frame |
| `CURRENT ROW` | Hàng hiện tại và các peer tương ứng tùy loại frame |
| `n FOLLOWING` | Tiến n hàng hoặc giá trị theo frame |
| `UNBOUNDED FOLLOWING` | Đến cuối phân vùng |

Ví dụ frame từ đầu phân vùng đến hàng hiện tại:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Ví dụ cửa sổ gồm hàng hiện tại và hai hàng đứng trước:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

Ví dụ toàn bộ phân vùng:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

### ROWS và RANGE khác nhau thế nào?

- `ROWS` xác định frame theo vị trí hàng trong thứ tự cửa sổ.
- `RANGE` xác định frame theo giá trị của biểu thức ORDER BY và nhóm các hàng peer có cùng giá trị sắp xếp.

Với dữ liệu mẫu, An có hai giao dịch cùng ngày 02-01-2026. Nếu dùng RANGE và chỉ ORDER BY sale_date, hai giao dịch cùng ngày là peer và có thể nhận cùng kết quả tổng lũy kế. Nếu dùng ROWS với thứ tự có khóa phụ sale_id, mỗi giao dịch được tính lần lượt.

### Tổng lũy kế dùng ROWS

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

Kết quả:

| sale_id | salesperson | sale_date | amount | running_total |
|---:|---|---|---:|---:|
| 1 | An | 2026-01-01 | 100.00 | 100.00 |
| 2 | An | 2026-01-02 | 150.00 | 250.00 |
| 3 | An | 2026-01-02 | 50.00 | 300.00 |
| 4 | Binh | 2026-01-01 | 200.00 | 200.00 |
| 5 | Binh | 2026-01-03 | 100.00 | 300.00 |

### Khác biệt với RANGE mặc định

Khi có ORDER BY nhưng không ghi frame, MySQL dùng frame mặc định tương đương:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Khi không có ORDER BY trong định nghĩa cửa sổ, frame mặc định bao trùm toàn bộ phân vùng. Do đó, `SUM(amount) OVER (PARTITION BY salesperson)` trả tổng của mọi hàng thuộc nhân viên đó.

Với frame mặc định có ORDER BY, các hàng peer có cùng giá trị ORDER BY cùng được tính đến. Với dữ liệu mẫu, truy vấn:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date
    ) AS default_running_total
FROM sales
WHERE salesperson = 'An'
ORDER BY sale_date, sale_id;
~~~

có thể cho kết quả:

| sale_id | sale_date | amount | default_running_total |
|---:|---|---:|---:|
| 1 | 2026-01-01 | 100.00 | 100.00 |
| 2 | 2026-01-02 | 150.00 | 300.00 |
| 3 | 2026-01-02 | 50.00 | 300.00 |

Hai giao dịch cùng ngày được cộng chung vì cùng là peer theo `ORDER BY sale_date`.

Khi cần tổng lũy kế từng hàng, hãy khai báo rõ `ROWS` và thêm khóa phụ duy nhất vào ORDER BY. Điều này làm rõ cả frame lẫn thứ tự xử lý.

## 8. Cửa sổ trượt: trung bình của một số hàng gần nhất

Window frame có thể giới hạn phép tính vào một số hàng trước và sau hàng hiện tại.

Ví dụ tính trung bình giao dịch hiện tại và giao dịch ngay trước đó của cùng nhân viên:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    AVG(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS moving_average_2_sales
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

Với An:

- Giao dịch 1: trung bình của 100 là 100.
- Giao dịch 2: trung bình của 100 và 150 là 125.
- Giao dịch 3: trung bình của 150 và 50 là 100.

Với Binh:

- Giao dịch 4: 200.
- Giao dịch 5: trung bình của 200 và 100 là 150.

Frame `ROWS BETWEEN 1 PRECEDING AND CURRENT ROW` có tối đa hai hàng. Ở đầu phân vùng, nếu không đủ hàng phía trước, frame chỉ chứa những hàng hiện có.

Đây là mẫu hữu ích cho trung bình trượt, tổng trượt, số giao dịch gần đây và nhiều phép tính theo chuỗi thời gian.

## 9. Các hàm cửa sổ chuyên dụng

Không phải hàm cửa sổ nào cũng là hàm tổng hợp. MySQL có các hàm chuyên dụng để đánh số, xếp hạng, chia nhóm hoặc truy cập hàng lân cận.

### ROW_NUMBER(): đánh số từng hàng

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson
        ORDER BY amount DESC, sale_id
    ) AS row_num
FROM sales
ORDER BY salesperson, row_num;
~~~

ROW_NUMBER gán số thứ tự duy nhất trong từng phân vùng. Nếu hai hàng có cùng giá trị ORDER BY, hãy thêm khóa phụ để thứ tự ổn định.

### RANK() và DENSE_RANK(): xếp hạng có đồng hạng

Ba hàm thường được so sánh:

| Hàm | Khi có hai hàng đồng hạng |
|---|---|
| `ROW_NUMBER()` | Vẫn cấp số khác nhau cho từng hàng |
| `RANK()` | Cùng hạng và bỏ qua số hạng kế tiếp |
| `DENSE_RANK()` | Cùng hạng nhưng không bỏ số hạng kế tiếp |

Ví dụ:

~~~sql
WITH ranked_sales AS (
    SELECT
        sale_id,
        salesperson,
        amount,
        RANK() OVER (ORDER BY amount DESC) AS amount_rank,
        DENSE_RANK() OVER (ORDER BY amount DESC) AS dense_amount_rank,
        ROW_NUMBER() OVER (
            ORDER BY amount DESC, sale_id
        ) AS row_num
    FROM sales
)
SELECT *
FROM ranked_sales
ORDER BY amount_rank, sale_id;
~~~

Nếu hai giao dịch cùng có amount 100:

- RANK có thể trả các hạng 3 và 3, hạng tiếp theo là 5.
- DENSE_RANK trả các hạng 3 và 3, hạng tiếp theo là 4.
- ROW_NUMBER vẫn cấp số khác nhau theo thứ tự đã xác định.

Không thêm khóa phụ vào ORDER BY của RANK nếu muốn các giá trị amount bằng nhau được đồng hạng. Nếu thêm `sale_id`, các hàng sẽ không còn peer theo toàn bộ danh sách sắp xếp.

### NTILE(): chia hàng thành các nhóm gần bằng nhau

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    NTILE(3) OVER (
        ORDER BY amount DESC, sale_id
    ) AS sales_bucket
FROM sales;
~~~

NTILE(3) chia các hàng thành ba nhóm theo thứ tự. Nếu số hàng không chia hết cho số nhóm, các nhóm đầu có thể có thêm một hàng. Đây là cách tạo phân vị đơn giản, nhưng cần xác định rõ phạm vi phân vùng nếu muốn chia riêng theo từng nhân viên.

### LAG() và LEAD(): đọc hàng trước và sau

`LAG()` lấy giá trị ở hàng trước trong thứ tự cửa sổ; `LEAD()` lấy giá trị ở hàng sau.

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    LAG(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
    ) AS previous_amount,
    LEAD(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
    ) AS next_amount
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

Có thể chỉ định độ lệch và giá trị mặc định:

~~~sql
LAG(amount, 1, 0) OVER (
    PARTITION BY salesperson
    ORDER BY sale_date, sale_id
)
~~~

Nếu không có hàng trước, biểu thức trên trả 0. Nếu không chỉ định giá trị mặc định, kết quả thường là NULL.

Dùng LAG/LEAD để tính:

- Chênh lệch doanh thu so với giao dịch trước.
- So sánh số dư cuối kỳ với kỳ trước.
- Phát hiện thay đổi trạng thái.
- Đối chiếu dữ liệu theo chuỗi thời gian.

Ví dụ chênh lệch với giao dịch trước:

~~~sql
WITH sales_with_previous AS (
    SELECT
        sale_id,
        salesperson,
        sale_date,
        amount,
        LAG(amount) OVER (
            PARTITION BY salesperson
            ORDER BY sale_date, sale_id
        ) AS previous_amount
    FROM sales
)
SELECT
    sale_id,
    salesperson,
    amount,
    previous_amount,
    amount - previous_amount AS amount_change
FROM sales_with_previous
ORDER BY salesperson, sale_date, sale_id;
~~~

Hàng đầu tiên của mỗi nhân viên có `previous_amount = NULL`, vì không có giao dịch trước.

### FIRST_VALUE() và LAST_VALUE()

`FIRST_VALUE()` lấy giá trị ở hàng đầu tiên của frame; `LAST_VALUE()` lấy giá trị ở hàng cuối cùng của frame.

Ví dụ lấy giao dịch đầu tiên và cuối cùng trong toàn bộ phân vùng:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    FIRST_VALUE(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_sale_amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_sale_amount
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

Lưu ý quan trọng: nếu dùng LAST_VALUE với frame mặc định kết thúc ở CURRENT ROW, giá trị cuối của frame thường chính là hàng hiện tại. Vì vậy, khi muốn giá trị cuối toàn phân vùng, hãy mở rộng frame đến `UNBOUNDED FOLLOWING`.

## 10. Named window: tái sử dụng định nghĩa cửa sổ

Nếu nhiều hàm sử dụng cùng PARTITION BY và ORDER BY, có thể đặt tên cửa sổ bằng mệnh đề WINDOW:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER w AS running_total,
    AVG(amount) OVER w AS running_average,
    COUNT(*) OVER (
        PARTITION BY salesperson
    ) AS salesperson_count
FROM sales
WINDOW w AS (
    PARTITION BY salesperson
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY salesperson, sale_date, sale_id;
~~~

Named window giúp tránh lặp lại định nghĩa và giảm khả năng các hàm vô tình dùng thứ tự hoặc phân vùng khác nhau.

Trong cú pháp SELECT của MySQL, mệnh đề WINDOW nằm sau HAVING (nếu có) và trước ORDER BY.

## 11. Kết hợp GROUP BY và hàm cửa sổ

Hàm cửa sổ có thể hoạt động trên tập hàng đã được GROUP BY tạo ra. Điều này hữu ích khi cần báo cáo theo nhóm, sau đó so sánh nhóm với tổng hoặc xếp hạng nhóm.

Ví dụ, tính tổng theo nhân viên rồi xếp hạng:

~~~sql
WITH salesperson_totals AS (
    SELECT
        salesperson,
        SUM(amount) AS total_amount
    FROM sales
    GROUP BY salesperson
)
SELECT
    salesperson,
    total_amount,
    RANK() OVER (
        ORDER BY total_amount DESC
    ) AS revenue_rank,
    SUM(total_amount) OVER () AS company_total
FROM salesperson_totals
ORDER BY revenue_rank, salesperson;
~~~

Kết quả chỉ có một hàng cho mỗi nhân viên. CTE tạo dữ liệu đã tổng hợp; hàm cửa sổ tính thứ hạng và tổng công ty trên các hàng đó.

Có thể hiểu thành hai tầng:

1. GROUP BY xác định grain báo cáo và tạo số liệu mỗi nhân viên.
2. Window function tính thêm chỉ số so sánh giữa các hàng báo cáo.

Không nên đưa các cột chi tiết chưa được nhóm vào SELECT nếu chúng không hợp lệ theo quy tắc GROUP BY và SQL mode.

## 12. Vì sao không thể lọc trực tiếp bằng hàm cửa sổ trong WHERE?

Hàm cửa sổ được tính sau các bước FROM, WHERE, GROUP BY và HAVING của truy vấn. Vì vậy, alias hoặc biểu thức cửa sổ chưa sẵn sàng khi WHERE được đánh giá.

Truy vấn sau không hợp lệ:

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson
        ORDER BY amount DESC, sale_id
    ) AS row_num
FROM sales
WHERE row_num = 1;
~~~

Muốn lấy giao dịch có số tiền cao nhất của mỗi nhân viên, hãy bọc truy vấn cửa sổ trong CTE:

~~~sql
WITH ranked_sales AS (
    SELECT
        sale_id,
        salesperson,
        sale_date,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY salesperson
            ORDER BY amount DESC, sale_id
        ) AS row_num
    FROM sales
)
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount
FROM ranked_sales
WHERE row_num = 1
ORDER BY salesperson;
~~~

Hoặc dùng derived table:

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount
FROM (
    SELECT
        sale_id,
        salesperson,
        sale_date,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY salesperson
            ORDER BY amount DESC, sale_id
        ) AS row_num
    FROM sales
) AS ranked_sales
WHERE row_num = 1;
~~~

Đây là mẫu thường dùng để:

- Lấy top 1 hoặc top N mỗi nhóm.
- Lấy bản ghi mới nhất mỗi khách hàng.
- Loại bản ghi trùng theo quy tắc ưu tiên.
- Lọc các hàng có thứ hạng hoặc tổng lũy kế thỏa điều kiện.

MySQL không cung cấp mệnh đề QUALIFY trong cú pháp SELECT thông thường; hãy dùng CTE hoặc truy vấn con để lọc kết quả cửa sổ.

## 13. Những giới hạn và lưu ý của MySQL

Một số điểm cần nhớ khi dùng hàm cửa sổ trong MySQL:

- Window functions có trong MySQL từ phiên bản 8.0. Hãy kiểm tra phiên bản server nếu truy vấn chạy trên hệ thống cũ.
- Hàm cửa sổ được phép trong danh sách SELECT và ORDER BY; không dùng trực tiếp trong WHERE, GROUP BY, HAVING hoặc ON.
- Không lồng trực tiếp một hàm cửa sổ bên trong một hàm cửa sổ khác.
- MySQL không hỗ trợ từ khóa DISTINCT cho các hàm tổng hợp được dùng dưới dạng window function, ví dụ `COUNT(DISTINCT customer_id) OVER (...)`.
- ORDER BY trong OVER không thay thế ORDER BY cuối truy vấn.
- Nếu thứ tự không duy nhất, kết quả của ROW_NUMBER và các phép tính phụ thuộc thứ tự có thể không ổn định.
- Window frame mặc định có thể ảnh hưởng kết quả khi ORDER BY chứa các giá trị trùng nhau.
- Một hàm cửa sổ có thể cần sắp xếp hoặc lưu tạm nhiều hàng; không mặc định rằng nó luôn nhanh hơn GROUP BY hay truy vấn con.

Nếu cần đếm số khách hàng khác nhau trong một phân vùng, hãy cân nhắc tổng hợp trước theo khóa khách hàng, dùng truy vấn con/CTE hoặc một thiết kế khác phù hợp. Không viết cú pháp DISTINCT OVER mà MySQL không hỗ trợ.

## 14. Kiểm tra hiệu năng

Hàm cửa sổ có thể yêu cầu MySQL sắp xếp dữ liệu theo PARTITION BY và ORDER BY. Với bảng lớn, chi phí sort, bộ nhớ và temporary table có thể đáng kể.

Các bước kiểm tra:

1. Chỉ chọn cột cần thiết trong truy vấn.
2. Giới hạn dữ liệu đầu vào bằng WHERE trước khi tính cửa sổ nếu điều đó đúng nghiệp vụ.
3. Chọn PARTITION BY và ORDER BY rõ ràng, tránh sắp xếp dư thừa.
4. Cân nhắc index phù hợp với cột lọc, phân vùng và sắp xếp.
5. Dùng EXPLAIN để xem kế hoạch.
6. Trên phiên bản hỗ trợ, dùng EXPLAIN ANALYZE để quan sát thời gian và số hàng thực tế.
7. So sánh với GROUP BY hoặc truy vấn con trên cùng dữ liệu và cùng điều kiện.

Ví dụ:

~~~sql
EXPLAIN
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales
WHERE sale_date >= '2026-01-01';
~~~

Index có thể cân nhắc cho truy vấn trên:

~~~sql
CREATE INDEX idx_sales_date_person
ON sales (sale_date, salesperson, sale_id);
~~~

Hoặc với truy vấn chủ yếu phân vùng theo nhân viên và sắp xếp theo ngày:

~~~sql
CREATE INDEX idx_sales_person_date
ON sales (salesperson, sale_date, sale_id);
~~~

Không có một thứ tự index tối ưu cho mọi truy vấn. Index phù hợp phụ thuộc điều kiện lọc, thứ tự truy cập, độ chọn lọc và kế hoạch của optimizer. Hãy kiểm tra EXPLAIN và đo trên dữ liệu đại diện trước khi giữ index.

## 15. Bài thực hành tổng hợp

Dùng database lab đã tạo ở phần 2.

### Bước 1: so sánh GROUP BY và OVER

Chạy:

~~~sql
SELECT
    salesperson,
    SUM(amount) AS total_amount
FROM sales
GROUP BY salesperson;
~~~

Sau đó chạy:

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
    ) AS total_amount
FROM sales
ORDER BY salesperson, sale_id;
~~~

Ghi lại số hàng của hai kết quả và giải thích vì sao một truy vấn có hai hàng, truy vấn còn lại có năm hàng.

### Bước 2: tính tổng lũy kế

~~~sql
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales
ORDER BY salesperson, sale_date, sale_id;
~~~

Kiểm tra tổng lũy kế của An lần lượt là 100, 250 và 300.

### Bước 3: so sánh ROWS và RANGE

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS range_total,
    SUM(amount) OVER (
        PARTITION BY salesperson
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS rows_total
FROM sales
WHERE salesperson = 'An'
ORDER BY sale_date, sale_id;
~~~

Giải thích vì sao hai giao dịch cùng ngày có thể có cùng `range_total`, nhưng `rows_total` khác nhau.

### Bước 4: xếp hạng giao dịch

~~~sql
SELECT
    sale_id,
    salesperson,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY salesperson
        ORDER BY amount DESC, sale_id
    ) AS row_num,
    RANK() OVER (
        PARTITION BY salesperson
        ORDER BY amount DESC
    ) AS amount_rank,
    DENSE_RANK() OVER (
        PARTITION BY salesperson
        ORDER BY amount DESC
    ) AS dense_amount_rank
FROM sales
ORDER BY salesperson, amount_rank, sale_id;
~~~

So sánh ba cột thứ hạng và giải thích trường hợp đồng hạng.

### Bước 5: so sánh với giao dịch trước

~~~sql
WITH sales_delta AS (
    SELECT
        sale_id,
        salesperson,
        sale_date,
        amount,
        LAG(amount) OVER (
            PARTITION BY salesperson
            ORDER BY sale_date, sale_id
        ) AS previous_amount
    FROM sales
)
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount,
    previous_amount,
    amount - previous_amount AS amount_change
FROM sales_delta
ORDER BY salesperson, sale_date, sale_id;
~~~

Xác định giao dịch đầu tiên của mỗi nhân viên và giải thích vì sao không có giá trị trước đó.

### Bước 6: lấy giao dịch lớn nhất mỗi nhân viên

~~~sql
WITH ranked_sales AS (
    SELECT
        sale_id,
        salesperson,
        sale_date,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY salesperson
            ORDER BY amount DESC, sale_id
        ) AS row_num
    FROM sales
)
SELECT
    sale_id,
    salesperson,
    sale_date,
    amount
FROM ranked_sales
WHERE row_num = 1
ORDER BY salesperson;
~~~

Thử thay ROW_NUMBER bằng RANK nếu muốn trả tất cả giao dịch đồng hạng cao nhất.

### Bước 7: dọn dẹp

~~~sql
DROP DATABASE mysql_window_functions_lab;
~~~

Chỉ chạy trên database lab vừa tạo. Lệnh này xóa toàn bộ bảng và dữ liệu thực hành.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Kết quả chỉ còn một hàng mỗi nhóm | Dùng GROUP BY nên các hàng đã được thu gọn | Dùng hàm cửa sổ nếu cần giữ chi tiết từng hàng |
| Tổng lũy kế tăng theo nhiều hàng cùng ngày | Frame mặc định RANGE gộp các peer | Dùng ROWS và thêm khóa phụ duy nhất vào ORDER BY |
| ROW_NUMBER thay đổi giữa các lần chạy | ORDER BY không xác định thứ tự duy nhất | Thêm primary key hoặc cột phân biệt |
| Alias cửa sổ không dùng được trong WHERE | Window function được tính sau WHERE | Bọc truy vấn bằng CTE hoặc derived table |
| LAST_VALUE trả giá trị hàng hiện tại | Frame mặc định kết thúc tại CURRENT ROW | Dùng frame đến UNBOUNDED FOLLOWING nếu cần cuối phân vùng |
| RANK bỏ qua số hạng | Có nhiều hàng đồng hạng | Dùng DENSE_RANK nếu muốn hạng liên tục |
| COUNT(DISTINCT ...) OVER báo lỗi | MySQL không hỗ trợ DISTINCT trong window aggregate | Tổng hợp riêng hoặc dùng truy vấn con phù hợp |
| Tổng cửa sổ lặp trên mọi hàng | Không có PARTITION BY hoặc frame bao trùm phân vùng | Kiểm tra phạm vi cửa sổ mong muốn |
| Truy vấn chậm khi thêm OVER | Cần sort hoặc xử lý frame trên tập hàng lớn | Lọc phù hợp, xem index và EXPLAIN |
| Thứ tự hiển thị không đúng như trong OVER | ORDER BY trong OVER chỉ điều khiển phép tính | Thêm ORDER BY ở cuối SELECT |

## 17. Checklist trước khi dùng hàm cửa sổ

- [ ] Đã xác định cần một hàng mỗi nhóm hay giữ từng hàng chi tiết.
- [ ] Đã chọn GROUP BY hay OVER theo grain kết quả.
- [ ] Đã xác định PARTITION BY có cần thiết hay không.
- [ ] Đã khai báo ORDER BY trong OVER khi phép tính phụ thuộc thứ tự.
- [ ] Đã thêm khóa phụ để xử lý giá trị ORDER BY trùng nhau.
- [ ] Đã chọn ROWS hoặc RANGE đúng với ý nghĩa frame.
- [ ] Đã kiểm tra frame mặc định khi dùng ORDER BY.
- [ ] Đã phân biệt ORDER BY trong OVER với ORDER BY cuối truy vấn.
- [ ] Đã dùng CTE hoặc derived table nếu cần lọc kết quả cửa sổ.
- [ ] Đã kiểm tra hành vi NULL của hàm tổng hợp và LAG/LEAD.
- [ ] Đã tránh DISTINCT trong window aggregate trên MySQL.
- [ ] Đã xem xét chi phí sort, temporary table và index.
- [ ] Đã kiểm thử với dữ liệu có giá trị trùng, phân vùng rỗng hoặc chỉ một hàng.

## 18. Nguyên tắc cần ghi nhớ

1. Hàm tổng hợp với GROUP BY thu gọn hàng về grain nhóm.
2. Hàm cửa sổ với OVER tính trên các hàng liên quan nhưng giữ từng hàng đầu vào của bước SELECT.
3. PARTITION BY chia cửa sổ thành các phân vùng độc lập.
4. ORDER BY trong OVER xác định thứ tự tính, không bảo đảm thứ tự hiển thị.
5. Window frame xác định những hàng tham gia phép tính quanh hàng hiện tại.
6. ROWS làm việc theo vị trí hàng; RANGE xét giá trị và peer theo ORDER BY.
7. Khi cần tổng lũy kế từng hàng, khai báo ROWS và thứ tự có tính duy nhất.
8. ROW_NUMBER đánh số riêng từng hàng; RANK và DENSE_RANK xử lý đồng hạng khác nhau.
9. LAG/LEAD truy cập hàng trước/sau mà không cần self-join.
10. Dùng CTE hoặc truy vấn con để lọc kết quả hàm cửa sổ.
11. MySQL không hỗ trợ DISTINCT trong window aggregate.
12. Kiểm tra kế hoạch thực thi và hiệu năng trên dữ liệu đại diện.

## Tài liệu tham khảo chính thức

Các cú pháp và hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [Window Function Concepts and Syntax](https://dev.mysql.com/doc/refman/9.7/en/window-functions-usage.html): cú pháp OVER, PARTITION BY, ORDER BY và frame.
2. [Window Function Descriptions](https://dev.mysql.com/doc/refman/9.7/en/window-function-descriptions.html): ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD, FIRST_VALUE và các hàm chuyên dụng.
3. [Window Function Frame Specification](https://dev.mysql.com/doc/refman/9.7/en/window-functions-frames.html): ROWS, RANGE, frame mặc định và peer rows.
4. [Aggregate Functions](https://dev.mysql.com/doc/refman/9.7/en/aggregate-functions.html): cách các hàm tổng hợp hoạt động và cách dùng dưới dạng window function.
5. [SELECT Statement](https://dev.mysql.com/doc/refman/9.7/en/select.html): vị trí của WINDOW, ORDER BY và các mệnh đề truy vấn.
6. [Common Table Expressions](https://dev.mysql.com/doc/refman/9.7/en/with.html): dùng CTE để xử lý kết quả hàm cửa sổ ở truy vấn ngoài.
7. [EXPLAIN Statement](https://dev.mysql.com/doc/refman/9.7/en/explain.html): kiểm tra kế hoạch thực thi và hiệu năng truy vấn.

