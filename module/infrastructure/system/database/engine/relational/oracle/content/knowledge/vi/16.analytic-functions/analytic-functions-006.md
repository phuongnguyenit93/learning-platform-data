# Khung ROWS/RANGE, khung mặc định và các dòng đồng hạng

Trong Oracle SQL, hàm phân tích (analytic function) có thể tính tổng lũy kế, trung bình trượt, giá trị lớn nhất trong một khoảng, hoặc giá trị đầu/cuối của một cửa sổ dữ liệu mà vẫn giữ nguyên từng hàng chi tiết. Thành phần quyết định **những hàng nào được đưa vào phép tính cho hàng hiện tại** là *window frame* (khung cửa sổ).

Oracle cung cấp hai cách xác định khung thường gặp:

- **`ROWS`**: xác định khung bằng số hàng vật lý trước/sau hàng hiện tại trong thứ tự analytic.
- **`RANGE`**: xác định khung bằng giá trị của khóa sắp xếp; các hàng có cùng khóa sắp xếp (peer rows, hay các dòng đồng hạng) được xử lý cùng nhau.

Một điểm rất dễ gây nhầm là nếu hàm analytic có `ORDER BY` nhưng không ghi rõ frame, Oracle mặc định dùng:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Vì đây là `RANGE`, các dòng đồng hạng với dòng hiện tại cũng nằm trong khung. Do đó, `SUM(...) OVER (ORDER BY ...)` có thể tăng theo từng **nhóm giá trị khóa sắp xếp**, thay vì tăng từng hàng như người viết tưởng tượng.

Bài học giải thích cách chọn `ROWS` hay `RANGE`, cách hoạt động của frame mặc định, peer rows, tính xác định khi có khóa trùng, các khung thời gian và ảnh hưởng của frame tới `LAST_VALUE`.

## 1. Analytic function và window frame

Một hàm aggregate thông thường như `SUM(amount)` thường gom nhiều hàng thành một kết quả. Khi dùng `SUM` dưới dạng analytic:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
)
~~~

Oracle vẫn trả về từng hàng đầu vào. Với mỗi hàng, hàm tính tổng trên tập hàng thuộc partition và window frame tương ứng.

Ba khái niệm cần tách biệt:

1. **Partition**: nhóm hàng độc lập do `PARTITION BY` xác định. Mỗi partition có cửa sổ riêng.
2. **Analytic ordering**: thứ tự logic do `ORDER BY` bên trong `OVER(...)` xác định.
3. **Window frame**: phần hàng được chọn trong partition cho phép tính của hàng hiện tại.

Ví dụ:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
~~~

Với mỗi giao dịch, Oracle tính tổng trên tối đa ba hàng: hai hàng trước và hàng hiện tại theo thứ tự analytic. Khi sang partition khác, cửa sổ bắt đầu lại.

**`ORDER BY` bên trong `OVER` không bảo đảm thứ tự hiển thị cuối cùng.** Nếu client cần kết quả trả ra theo ngày hoặc theo thứ tự frame, câu SELECT ngoài cùng vẫn cần `ORDER BY`.

## 2. Dữ liệu lab có các dòng đồng hạng

Tạo bảng giao dịch trong schema thực hành riêng có quyền `CREATE TABLE` và quota tablespace:

~~~sql
CREATE TABLE lab_window_sales (
    sale_id       NUMBER PRIMARY KEY,
    department_id NUMBER NOT NULL,
    sale_date     DATE NOT NULL,
    amount        NUMBER(12, 2)
);
~~~

Chèn dữ liệu:

~~~sql
INSERT INTO lab_window_sales VALUES
    (1, 10, DATE '2024-01-01', 100);
INSERT INTO lab_window_sales VALUES
    (2, 10, DATE '2024-01-01', 50);
INSERT INTO lab_window_sales VALUES
    (3, 10, DATE '2024-01-02', 200);
INSERT INTO lab_window_sales VALUES
    (4, 10, DATE '2024-01-05', 100);
INSERT INTO lab_window_sales VALUES
    (5, 10, DATE '2024-01-08', 300);
INSERT INTO lab_window_sales VALUES
    (6, 10, DATE '2024-01-08', 100);
INSERT INTO lab_window_sales VALUES
    (7, 20, DATE '2024-01-01', 500);
INSERT INTO lab_window_sales VALUES
    (8, 20, DATE '2024-01-04', 200);
INSERT INTO lab_window_sales VALUES
    (9, 20, DATE '2024-01-10', 100);

COMMIT;
~~~

Quan sát:

| SALE_ID | DEPARTMENT_ID | SALE_DATE | AMOUNT |
| ---: | ---: | --- | ---: |
| 1 | 10 | 2024-01-01 | 100 |
| 2 | 10 | 2024-01-01 | 50 |
| 3 | 10 | 2024-01-02 | 200 |
| 4 | 10 | 2024-01-05 | 100 |
| 5 | 10 | 2024-01-08 | 300 |
| 6 | 10 | 2024-01-08 | 100 |
| 7 | 20 | 2024-01-01 | 500 |
| 8 | 20 | 2024-01-04 | 200 |
| 9 | 20 | 2024-01-10 | 100 |

Trong phòng 10, hai giao dịch có cùng ngày 1/1 và hai giao dịch có cùng ngày 8/1. Nếu chỉ `ORDER BY sale_date`, các giao dịch cùng ngày là **peer rows** vì có cùng giá trị của tất cả biểu thức sắp xếp.

## 3. ROWS: khung theo số hàng vật lý

`ROWS` xác định frame theo vị trí của hàng hiện tại trong thứ tự analytic.

### 3.1. Cú pháp

~~~sql
ROWS BETWEEN frame_start AND frame_end
~~~

Các loại boundary phổ biến:

| Boundary | Ý nghĩa |
| --- | --- |
| `UNBOUNDED PRECEDING` | Bắt đầu từ hàng đầu tiên của partition |
| `n PRECEDING` | Lùi `n` hàng vật lý so với hàng hiện tại |
| `CURRENT ROW` | Chính hàng hiện tại |
| `n FOLLOWING` | Tiến `n` hàng vật lý so với hàng hiện tại |
| `UNBOUNDED FOLLOWING` | Kết thúc ở hàng cuối cùng của partition |

Ví dụ:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

Khung gồm tối đa ba hàng: hai hàng đứng trước và hàng hiện tại. Ở đầu partition, nếu chưa có đủ hai hàng trước, frame chỉ chứa những hàng đang tồn tại.

### 3.2. Tổng lũy kế theo từng hàng

~~~sql
SELECT
    sale_id,
    department_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_sum_rows
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

Kết quả:

| SALE_ID | SALE_DATE | AMOUNT | RUNNING_SUM_ROWS |
| ---: | --- | ---: | ---: |
| 1 | 2024-01-01 | 100 | 100 |
| 2 | 2024-01-01 | 50 | 150 |
| 3 | 2024-01-02 | 200 | 350 |
| 4 | 2024-01-05 | 100 | 450 |
| 5 | 2024-01-08 | 300 | 750 |
| 6 | 2024-01-08 | 100 | 850 |

Frame bắt đầu từ hàng đầu tiên và kết thúc ở hàng hiện tại. Vì `SALE_ID` là khóa duy nhất, thứ tự giữa hai giao dịch cùng ngày được xác định rõ.

### 3.3. Trung bình trượt ba giao dịch

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    AVG(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3_rows
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

Đối với mỗi hàng:

- Hàng đầu tiên: trung bình trên một giao dịch.
- Hàng thứ hai: trung bình trên hai giao dịch.
- Từ hàng thứ ba: trung bình trên hàng hiện tại và hai hàng trước.

Đây là trung bình trên **tối đa ba bản ghi**, không phải trung bình của ba ngày gần nhất. Nếu một ngày có nhiều giao dịch, từng giao dịch vẫn chiếm một vị trí riêng trong frame `ROWS`.

### 3.4. ROWS cần thứ tự xác định khi có khóa trùng

Ví dụ không đủ xác định:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Hai giao dịch ngày 1/1 có cùng `SALE_DATE`. Nếu không có khóa phụ, Oracle không có quy tắc nghiệp vụ nào xác định giao dịch nào đứng trước giao dịch nào trong frame vật lý. Tổng lũy kế gắn với từng `SALE_ID` có thể thay đổi theo thứ tự xử lý hợp lệ.

Hãy bổ sung khóa duy nhất hoặc một tập khóa tạo thứ tự duy nhất:

~~~sql
ORDER BY sale_date, sale_id
~~~

Quy tắc này đặc biệt quan trọng với `ROWS`, vì đổi vị trí hàng có thể làm thay đổi thành viên của frame.

## 4. RANGE: khung theo giá trị khóa sắp xếp

`RANGE` xác định frame dựa trên giá trị logic của biểu thức `ORDER BY`, không phải số vị trí hàng.

### 4.1. Cú pháp

~~~sql
RANGE BETWEEN frame_start AND frame_end
~~~

Ví dụ:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Với thứ tự tăng dần theo `SALE_DATE`, frame chứa các hàng có ngày từ đầu partition đến ngày của hàng hiện tại, **bao gồm tất cả hàng có cùng ngày hiện tại**.

### 4.2. CURRENT ROW trong RANGE bao gồm các dòng đồng hạng

Peer rows là các hàng có cùng giá trị trên **tất cả biểu thức** trong analytic `ORDER BY`.

Ví dụ:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Với hai giao dịch phòng 10 ngày 1/1:

- Giao dịch 1 có amount 100.
- Giao dịch 2 có amount 50.
- Cả hai cùng thuộc peer group ngày 1/1.
- Frame `RANGE ... CURRENT ROW` của mỗi giao dịch chứa cả hai hàng ngày 1/1.
- Vì vậy cả hai hàng nhận tổng lũy kế 150.

Kết quả:

| SALE_ID | SALE_DATE | AMOUNT | RUNNING_SUM_RANGE |
| ---: | --- | ---: | ---: |
| 1 | 2024-01-01 | 100 | 150 |
| 2 | 2024-01-01 | 50 | 150 |
| 3 | 2024-01-02 | 200 | 350 |
| 4 | 2024-01-05 | 100 | 450 |
| 5 | 2024-01-08 | 300 | 850 |
| 6 | 2024-01-08 | 100 | 850 |

Hai hàng đồng ngày nhận cùng một kết quả. Đây là khác biệt cốt lõi giữa frame `RANGE` và `ROWS`.

### 4.3. So sánh ROWS và RANGE trên cùng dữ liệu

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS sum_by_rows,
    SUM(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS sum_by_range
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

| SALE_ID | AMOUNT | SUM_BY_ROWS | SUM_BY_RANGE |
| ---: | ---: | ---: | ---: |
| 1 | 100 | 100 | 150 |
| 2 | 50 | 150 | 150 |
| 3 | 200 | 350 | 350 |
| 4 | 100 | 450 | 450 |
| 5 | 300 | 750 | 850 |
| 6 | 100 | 850 | 850 |

Lưu ý hai biểu thức cố ý có analytic ordering khác nhau:

- `ROWS` dùng `SALE_DATE, SALE_ID` để xác định thứ tự vật lý.
- `RANGE` dùng `SALE_DATE` để coi mọi giao dịch cùng ngày là peers.

Nếu thêm `SALE_ID` vào `ORDER BY` của `RANGE`, các hàng sẽ không còn là peers khi ID khác nhau. Với frame RANGE không có offset, các hàng khác ID có thể nhận các frame khác nhau vì khóa sắp xếp đầy đủ đã khác.

## 5. Khung mặc định của Oracle

Đối với hàm analytic hỗ trợ windowing, khi có `ORDER BY` nhưng bỏ qua `windowing_clause`, Oracle mặc định dùng:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Vì vậy hai câu sau có cùng frame:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
)
~~~

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

### 5.1. Tại sao tổng lũy kế mặc định có thể nhảy theo nhóm?

Nếu `ORDER BY` chỉ dùng `SALE_DATE`, mọi giao dịch cùng ngày là peers. Frame mặc định là RANGE, nên cả peer group được đưa vào cùng lúc. Kết quả của tổng lũy kế có thể nhảy từ 150 lên 350, rồi 450, rồi 850; hai giao dịch cùng ngày luôn nhận cùng tổng.

Nếu mục tiêu là tổng lũy kế **từng giao dịch**, hãy dùng `ROWS` và khóa phụ xác định:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

### 5.2. Không có analytic ORDER BY

Khi không chỉ định `ORDER BY` trong `OVER`, aggregate analytic tính trên toàn bộ partition cho mỗi hàng:

~~~sql
SELECT
    sale_id,
    department_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY department_id
    ) AS department_total
FROM lab_window_sales
ORDER BY department_id, sale_id;
~~~

Mỗi giao dịch phòng 10 nhận tổng 850; mỗi giao dịch phòng 20 nhận tổng 800. Đây là tổng của partition, không phải tổng lũy kế. Nếu cần một kết quả tăng dần theo hàng, phải định nghĩa analytic `ORDER BY` và frame phù hợp.

### 5.3. Khung mặc định không phải lúc nào cũng là điều bạn muốn

Đừng giả định rằng “có ORDER BY thì mỗi hàng chỉ cộng đến chính nó”. Với frame mặc định RANGE, hàng đồng hạng cũng được tính. Hãy viết frame tường minh khi yêu cầu nghiệp vụ phụ thuộc vào:

- Từng bản ghi theo thứ tự duy nhất.
- Tất cả giao dịch trong cùng ngày.
- Một khoảng giá trị số.
- Một khoảng thời gian.
- Toàn bộ partition, bất kể vị trí hàng.

Frame tường minh giúp người đọc hiểu chính xác quy tắc và tránh phụ thuộc vào mặc định.

## 6. Peer rows và các dòng đồng hạng

Hai hoặc nhiều hàng là peers khi chúng có cùng giá trị theo **toàn bộ danh sách analytic ORDER BY**. Ví dụ:

~~~sql
ORDER BY sale_date
~~~

thì hai giao dịch cùng ngày là peers. Nhưng:

~~~sql
ORDER BY sale_date, sale_id
~~~

thì chúng không còn peers nếu `SALE_ID` khác nhau.

### 6.1. Peer group ảnh hưởng RANGE

Với:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

mọi hàng trong peer group hiện tại có cùng frame. Điều đó làm các aggregate như `SUM`, `AVG`, `COUNT`, `MIN` và `MAX` trả cùng kết quả cho những hàng peers nếu biểu thức aggregate giống nhau.

### 6.2. Peer group cũng quan trọng với hàm xếp hạng

Các hàm `RANK` và `DENSE_RANK` dùng analytic ordering để xác định hàng đồng hạng:

~~~sql
SELECT
    sale_id,
    amount,
    RANK() OVER (ORDER BY amount DESC) AS amount_rank,
    DENSE_RANK() OVER (ORDER BY amount DESC) AS amount_dense_rank
FROM lab_window_sales
WHERE department_id = 10
ORDER BY amount DESC, sale_id;
~~~

Hai giao dịch có amount bằng 100 là peers theo `ORDER BY amount DESC`, nên nhận cùng rank. `RANK` để lại khoảng trống sau nhóm đồng hạng; `DENSE_RANK` không để khoảng trống.

**`RANK/DENSE_RANK` không sử dụng window frame ROWS/RANGE.** Khái niệm peers vẫn quan trọng, nhưng không có nghĩa bạn có thể thêm `ROWS BETWEEN ...` vào mọi hàm analytic.

### 6.3. Thêm khóa phụ có thể phá peer group

Nếu thêm khóa duy nhất:

~~~sql
RANK() OVER (ORDER BY amount DESC, sale_id)
~~~

các hàng có amount bằng nhau nhưng `SALE_ID` khác nhau không còn peers. Chúng sẽ nhận rank riêng. Vì vậy chỉ thêm tie-breaker khi nghiệp vụ muốn phá đồng hạng; nếu cần giữ cùng rank theo amount, không đưa khóa phụ vào analytic ordering của RANK.

Bạn vẫn có thể thêm khóa phụ vào **ORDER BY ngoài cùng** để hiển thị các hàng đồng hạng theo thứ tự ổn định:

~~~sql
SELECT
    sale_id,
    amount,
    RANK() OVER (ORDER BY amount DESC) AS amount_rank
FROM lab_window_sales
WHERE department_id = 10
ORDER BY amount DESC, sale_id;
~~~

Thứ tự hiển thị ổn định mà không thay đổi định nghĩa đồng hạng của hàm RANK.

## 7. Frame theo khoảng giá trị số

`RANGE` có thể dùng offset số khi analytic ordering là một biểu thức số:

~~~sql
RANGE BETWEEN 100 PRECEDING AND CURRENT ROW
~~~

Nếu `ORDER BY amount ASC`, frame của hàng hiện tại chứa các hàng có amount trong khoảng từ `amount hiện tại - 100` đến `amount hiện tại`, theo biên bao gồm.

Ví dụ:

~~~sql
SELECT
    sale_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY department_id
        ORDER BY amount
        RANGE BETWEEN 100 PRECEDING AND CURRENT ROW
    ) AS sum_in_amount_band
FROM lab_window_sales
WHERE department_id = 10
ORDER BY amount, sale_id;
~~~

Đây là tổng của các hàng có giá trị amount nằm trong dải logic quanh giá trị hiện tại, không phải tổng của 100 hàng trước. Tất cả hàng có cùng amount với hàng hiện tại cũng thuộc peer group và được tính cùng nhau.

### 7.1. RANGE offset có giới hạn số khóa sắp xếp

Với frame `RANGE` dùng offset như `n PRECEDING`, `n FOLLOWING` hoặc interval, Oracle yêu cầu analytic `ORDER BY` có **một biểu thức sắp xếp**. Lý do là offset phải được áp dụng lên một miền giá trị duy nhất.

Ví dụ hợp lệ:

~~~sql
ORDER BY amount
RANGE BETWEEN 100 PRECEDING AND CURRENT ROW
~~~

Ví dụ không phù hợp với quy tắc offset RANGE:

~~~sql
ORDER BY amount, sale_id
RANGE BETWEEN 100 PRECEDING AND CURRENT ROW
~~~

Nếu cần thứ tự phụ để phân biệt các bản ghi, nhưng vẫn cần một khoảng số theo amount, hãy cân nhắc `RANGE` chỉ theo amount hoặc dùng `ROWS` với ordering đầy đủ tùy ý nghĩa nghiệp vụ. Một số dạng frame RANGE chỉ dùng `UNBOUNDED` và `CURRENT ROW` cho phép nhiều biểu thức sort; hãy đối chiếu cú pháp Oracle đúng release khi kết hợp nhiều khóa.

## 8. Frame theo khoảng thời gian

Một yêu cầu phổ biến là “tổng doanh thu trong bảy ngày gần nhất”. Đây là cửa sổ theo **giá trị thời gian**, nên thường phù hợp với `RANGE` và interval.

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date
        RANGE BETWEEN INTERVAL '7' DAY PRECEDING AND CURRENT ROW
    ) AS amount_last_7_days
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

Khung được xác định theo `SALE_DATE` của hàng hiện tại và khoảng thời gian lùi bảy ngày. Tất cả giao dịch cùng ngày hiện tại đều thuộc cùng peer group và nhận cùng tổng trong frame đó.

### 8.1. RANGE thời gian khác ROWS theo số giao dịch

So sánh:

~~~sql
-- Tối đa bảy bản ghi gần nhất (hàng hiện tại + sáu hàng trước).
ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
~~~

~~~sql
-- Các hàng trong khoảng thời gian bảy ngày tính lùi từ thời điểm hiện tại.
RANGE BETWEEN INTERVAL '7' DAY PRECEDING AND CURRENT ROW
~~~

Nếu một ngày có 100 giao dịch:

- `ROWS` chỉ lấy tối đa bảy giao dịch theo thứ tự hàng.
- `RANGE` có thể lấy cả 100 giao dịch cùng ngày, cộng với các giao dịch ở các ngày nằm trong khoảng.

Nếu một ngày không có giao dịch:

- `ROWS` vẫn đếm số bản ghi thực tế trước đó, không tạo hàng cho ngày bị thiếu.
- `RANGE` cũng không tạo hàng ngày bị thiếu; nó chỉ chọn những hàng có giá trị thời gian nằm trong khoảng.

Muốn báo cáo một hàng cho mọi ngày, kể cả ngày không có giao dịch, cần tạo calendar/date dimension rồi LEFT JOIN dữ liệu tổng hợp vào lịch.

### 8.2. Kiểu dữ liệu của khóa thời gian

Với `DATE` hoặc `TIMESTAMP`, offset RANGE nên được biểu diễn bằng interval phù hợp. Ví dụ `INTERVAL '7' DAY` là khoảng ngày/giờ; `INTERVAL '1' MONTH` là khoảng năm/tháng. Không tùy tiện dùng số nguyên như số ngày khi biểu thức sắp xếp là TIMESTAMP nếu cần ngữ nghĩa thời gian chính xác; hãy chọn interval và kiểm tra kiểu dữ liệu.

## 9. Các frame thường dùng

| Mục tiêu | Frame | Ý nghĩa |
| --- | --- | --- |
| Tổng lũy kế theo từng hàng | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Từ đầu partition đến hàng hiện tại |
| Tổng lũy kế theo giá trị, gom peer rows | `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Từ đầu partition đến giá trị sort hiện tại, gồm mọi peers |
| Trung bình trên ba hàng | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | Hàng hiện tại và tối đa hai hàng trước |
| Cửa sổ đối xứng ba hàng | `ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING` | Hàng trước, hiện tại, hàng sau |
| Toàn bộ partition | `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Mọi hàng trong partition |
| Từ hiện tại đến cuối partition | `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING` | Hàng hiện tại và các hàng sau |
| Khoảng giá trị số | `RANGE BETWEEN 100 PRECEDING AND CURRENT ROW` | Các giá trị sort nằm trong dải 100 đơn vị đến hiện tại |
| Khoảng thời gian | `RANGE BETWEEN INTERVAL '7' DAY PRECEDING AND CURRENT ROW` | Các hàng nằm trong khoảng thời gian lùi bảy ngày |

`ROWS` là lựa chọn tự nhiên khi nghiệp vụ nói về **N bản ghi**. `RANGE` là lựa chọn tự nhiên khi nghiệp vụ nói về **một khoảng giá trị** như số tiền hoặc thời gian.

## 10. LAST_VALUE và bẫy frame mặc định

`LAST_VALUE` là ví dụ nổi tiếng cho thấy frame mặc định ảnh hưởng kết quả như thế nào.

### 10.1. LAST_VALUE không mặc định có nghĩa là hàng cuối partition

Ví dụ:

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
    ) AS last_value_default
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

Do có `ORDER BY` và không ghi frame, Oracle dùng frame mặc định từ `UNBOUNDED PRECEDING` đến `CURRENT ROW` theo `RANGE`. Với ordering có khóa duy nhất ở ví dụ này, hàng cuối trong frame hiện tại chính là hàng hiện tại. Vì vậy `LAST_VALUE` thường trả lại amount của chính hàng đó, không phải amount của giao dịch cuối cùng trong toàn partition.

### 10.2. Lấy giá trị ở hàng cuối partition

Nếu muốn giá trị của hàng cuối cùng theo thứ tự ngày và ID:

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS partition_last_amount
FROM lab_window_sales
WHERE department_id = 10
ORDER BY sale_date, sale_id;
~~~

Frame bao trùm toàn bộ partition nên mọi hàng phòng 10 nhận amount của giao dịch cuối cùng theo `SALE_DATE, SALE_ID`, tức 100 ở dữ liệu lab.

### 10.3. FIRST_VALUE và NTH_VALUE

`FIRST_VALUE` và `NTH_VALUE` cũng chịu ảnh hưởng của frame. Nếu muốn giá trị đầu tiên/toàn partition theo một thứ tự xác định, hãy khai báo rõ frame phù hợp và tie-breaker. Đừng nhầm `FIRST_VALUE`/`LAST_VALUE` với `MIN`/`MAX`: hàm value trả giá trị tại vị trí theo thứ tự, còn MIN/MAX trả giá trị nhỏ nhất/lớn nhất theo phép so sánh.

## 11. Hàm analytic nào dùng window frame?

Không phải hàm analytic nào cũng nhận `ROWS` hoặc `RANGE`.

| Nhóm hàm | Ví dụ | Window frame? |
| --- | --- | --- |
| Aggregate analytic | `SUM`, `AVG`, `COUNT`, `MIN`, `MAX` | Có |
| Value analytic | `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` | Có |
| Ranking | `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE` | Không dùng frame ROWS/RANGE |
| Offset | `LAG`, `LEAD` | Không dùng frame ROWS/RANGE |
| Distribution | `CUME_DIST`, `PERCENT_RANK`, `PERCENTILE_CONT` | Theo cú pháp riêng của từng hàm; không tự thêm frame |

Ví dụ sai:

~~~sql
RANK() OVER (
    ORDER BY amount DESC
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

`RANK` không nhận windowing clause như aggregate analytic. Để xử lý đồng hạng, điều khiển `ORDER BY` của RANK; không cố sửa bằng ROWS/RANGE.

## 12. Quy tắc biên và cách đọc frame

### 12.1. Boundary được tính theo thứ tự analytic

Với:

~~~sql
ROWS BETWEEN 2 PRECEDING AND 1 FOLLOWING
~~~

Oracle lấy tối đa:

- Hai hàng đứng trước.
- Hàng hiện tại.
- Một hàng đứng sau.

Tối đa bốn hàng. Ở đầu/cuối partition, phần vượt ra ngoài partition không tồn tại nên frame nhỏ hơn.

### 12.2. Không thể đặt start sau end

Frame phải có thứ tự biên hợp lệ. Ví dụ `BETWEEN CURRENT ROW AND 2 PRECEDING` không hợp lệ vì điểm kết thúc đứng trước điểm bắt đầu theo thứ tự frame. Hãy kiểm tra chiều của boundary khi kết hợp PRECEDING/FOLLOWING.

### 12.3. UNBOUNDED FOLLOWING và PRECEDING

- `UNBOUNDED PRECEDING` chỉ có thể dùng làm điểm bắt đầu.
- `UNBOUNDED FOLLOWING` chỉ có thể dùng làm điểm kết thúc.
- `CURRENT ROW` có nghĩa khác nhau: với ROWS là hàng vật lý hiện tại; với RANGE là peer group hiện tại.

### 12.4. NULL trong analytic ordering

Nếu khóa sắp xếp có NULL, thứ tự NULL phụ thuộc `NULLS FIRST`/`NULLS LAST` hoặc mặc định ASC/DESC. Các hàng có cùng giá trị sort (kể cả các giá trị NULL theo cùng quy tắc sort) có thể là peers. Với phép tính nhạy cảm với thứ tự, hãy quy định rõ vị trí NULL và khóa phụ cần thiết.

Ví dụ:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date ASC NULLS LAST, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

## 13. Tính xác định và thứ tự kết quả

Có ba thứ tự dễ bị nhầm:

1. **Thứ tự lưu trữ vật lý** của hàng trong bảng: không có cam kết để ứng dụng dựa vào.
2. **Analytic ORDER BY** trong `OVER(...)`: định nghĩa thứ tự dùng cho hàm analytic và frame.
3. **ORDER BY ngoài cùng**: định nghĩa thứ tự hàng trả về cho client.

Ví dụ:

~~~sql
SELECT
    sale_id,
    sale_date,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY sale_date, sale_id
    ) AS row_no
FROM lab_window_sales
WHERE department_id = 10
ORDER BY row_no;
~~~

`ROW_NUMBER` dùng analytic ordering; `ORDER BY row_no` ở ngoài chỉ định cách hiển thị. Nếu bỏ `ORDER BY` ngoài, client không được bảo đảm nhận hàng theo `ROW_NO`.

Với `ROWS`, thứ tự analytic nên là duy nhất nếu kết quả mỗi hàng phải ổn định. Với `RANGE`, peer rows cố ý cùng frame; nếu thêm khóa duy nhất vào analytic ordering, bạn thay đổi định nghĩa peer group.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tổng lũy kế nhảy theo ngày thay vì từng giao dịch | Frame mặc định là RANGE và ngày có peer rows | Dùng ROWS với khóa sắp xếp duy nhất nếu cần từng bản ghi |
| Hai hàng cùng ngày nhận cùng tổng | RANGE CURRENT ROW bao gồm toàn bộ peer group | Đây là hành vi đúng; giữ RANGE nếu muốn gom theo ngày |
| Kết quả ROWS đổi giữa các lần chạy | ORDER BY có khóa trùng, không xác định thứ tự vật lý | Thêm tie-breaker duy nhất như SALE_ID |
| RANGE offset báo lỗi với nhiều cột ORDER BY | RANGE offset yêu cầu một sort expression | Chỉ dùng một khóa logic cho RANGE hoặc đổi sang ROWS theo yêu cầu |
| Trung bình ba hàng bị hiểu thành ba ngày | ROWS đếm bản ghi, không đếm khoảng thời gian | Dùng RANGE interval cho cửa sổ thời gian |
| Trung bình bảy ngày bị hiểu thành bảy giao dịch | Dùng ROWS thay cho RANGE | Chọn frame theo giá trị ngày/interval |
| LAST_VALUE trả giá trị hàng hiện tại | Frame mặc định kết thúc ở CURRENT ROW | Dùng frame đến UNBOUNDED FOLLOWING nếu cần hàng cuối partition |
| RANK báo lỗi khi thêm ROWS | Ranking function không nhận window frame | Dùng ORDER BY và quy tắc peer của RANK |
| Kết quả query không hiển thị theo analytic order | Chỉ có ORDER BY trong OVER | Thêm ORDER BY ngoài cùng |
| Thêm SALE_ID làm mất đồng hạng | Peer group được xác định bởi tất cả khóa ORDER BY | Chỉ thêm tie-breaker vào hàm nếu muốn phá đồng hạng |
| Báo cáo thiếu ngày không có giao dịch | RANGE không tự sinh hàng ngày còn thiếu | Dùng calendar/date dimension rồi LEFT JOIN |

## 15. Bài tập thực hành

Sử dụng `LAB_WINDOW_SALES` ở mục 2. Hãy dự đoán kết quả trước khi chạy.

### Bài 1 — So sánh frame mặc định và RANGE tường minh

Viết hai biểu thức:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
)
~~~

và:

~~~sql
SUM(amount) OVER (
    PARTITION BY department_id
    ORDER BY sale_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Đối chiếu kết quả cho các giao dịch ngày 1/1 và 8/1. Giải thích vì sao mỗi cặp nhận cùng tổng.

### Bài 2 — Tổng lũy kế theo từng hàng

Dùng `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` và `ORDER BY sale_date, sale_id`. Kiểm tra sáu kết quả của phòng 10. Sau đó bỏ `SALE_ID` và giải thích tại sao thứ tự giữa các giao dịch cùng ngày không được bảo đảm.

### Bài 3 — Trung bình trượt ba bản ghi

Dùng `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`. Ghi lại frame của từng `SALE_ID` và tính trung bình. Giải thích vì sao số giao dịch trong frame ở đầu partition nhỏ hơn ba.

### Bài 4 — Cửa sổ theo bảy ngày

Dùng `RANGE BETWEEN INTERVAL '7' DAY PRECEDING AND CURRENT ROW`. Với từng ngày của phòng 10, liệt kê những ngày giao dịch thuộc frame. So sánh với frame `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW`.

### Bài 5 — Dòng đồng hạng và RANK

Chạy `RANK()` và `DENSE_RANK()` theo `AMOUNT DESC`. Quan sát hai giao dịch amount 100. Thêm `SALE_ID` vào analytic ordering rồi giải thích vì sao chúng không còn đồng hạng.

### Bài 6 — LAST_VALUE

Chạy `LAST_VALUE(amount)` với frame mặc định, sau đó với:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

Giải thích vì sao kết quả thứ hai là amount của giao dịch cuối partition trên mọi hàng.

### Bài 7 — Một hàng mỗi ngày

Tạo một CTE aggregate doanh thu theo `DEPARTMENT_ID, SALE_DATE`, sau đó tính tổng lũy kế trên kết quả ngày. So sánh với cách tính trực tiếp trên từng giao dịch bằng RANGE. Xác định khi nào nên tổng hợp trước để mỗi hàng đại diện cho một ngày.

### Bài 8 — Thiết kế KPI

Một dashboard cần hai chỉ số:

- Tổng tiền tăng sau mỗi giao dịch theo thứ tự thời gian.
- Tổng tiền trong bảy ngày gần nhất.

Viết hai analytic expressions tương ứng. Nêu rõ khóa sắp xếp, tie-breaker và frame của mỗi chỉ số.

## 16. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn tất bài thực hành:

~~~sql
DROP TABLE lab_window_sales PURGE;
~~~

`PURGE` bỏ qua recycle bin. Không chạy lệnh này với bảng nghiệp vụ hoặc bảng không thuộc quyền sở hữu của bạn.

## Tổng kết

`ROWS` xác định frame bằng **số hàng vật lý** trước/sau hàng hiện tại; `RANGE` xác định frame bằng **giá trị của khóa sắp xếp** và bao gồm các dòng đồng hạng. Với hàm analytic có `ORDER BY` nhưng không ghi frame, Oracle mặc định dùng `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Đây là lý do tổng lũy kế mặc định có thể cập nhật theo peer group thay vì từng bản ghi.

Chọn `ROWS` khi yêu cầu là N giao dịch hoặc một thứ tự hàng cụ thể; chọn `RANGE` khi yêu cầu là khoảng số hoặc khoảng thời gian. Khi dùng ROWS, bổ sung khóa tie-breaker để kết quả ổn định. Khi dùng RANGE, hiểu rõ peer group và giới hạn offset chỉ có một sort expression. Với `LAST_VALUE`, khai báo frame đến `UNBOUNDED FOLLOWING` nếu cần giá trị cuối partition. Cuối cùng, luôn phân biệt analytic `ORDER BY` với `ORDER BY` ngoài cùng để kết quả được tính đúng và hiển thị đúng thứ tự mong muốn.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — Analytic Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html) — ngữ nghĩa partition, analytic ordering và windowing clause.
- [Oracle Database SQL Language Reference — SELECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — cú pháp ROWS/RANGE và giới hạn frame.
- [Oracle Database SQL Language Reference — SUM (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SUM.html) — SUM ở dạng aggregate và analytic.
- [Oracle Database SQL Language Reference — LAST_VALUE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LAST_VALUE.html) — ảnh hưởng của window frame đến LAST_VALUE.
- [Oracle Database SQL Language Reference — RANK (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/RANK.html) — xử lý các hàng đồng hạng.

Khi dùng release Oracle khác 19c, hãy đối chiếu SQL Language Reference đúng phiên bản, đặc biệt các giới hạn của RANGE offset, kiểu interval và cú pháp windowing clause.
