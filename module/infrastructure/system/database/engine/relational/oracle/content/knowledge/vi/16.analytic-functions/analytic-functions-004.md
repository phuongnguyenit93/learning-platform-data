# LAG, LEAD và so sánh với dòng trước hoặc dòng sau trong Oracle Database

Trong báo cáo và phân tích dữ liệu, nhiều yêu cầu không chỉ cần biết giá trị của dòng hiện tại mà còn cần so sánh nó với **dòng đứng trước hoặc đứng sau theo một thứ tự xác định**. Ví dụ:

- Doanh thu tháng này tăng hay giảm so với tháng trước?
- Số dư tài khoản thay đổi bao nhiêu so với giao dịch trước?
- Một trạng thái có khác trạng thái liền trước của cùng đơn hàng không?
- Thời gian giữa hai sự kiện liên tiếp là bao lâu?
- Giá trị của kỳ kế tiếp là bao nhiêu?
- Dòng hiện tại có phải bản ghi đầu tiên hoặc cuối cùng của mỗi khách hàng không?

Oracle Database cung cấp hai hàm phân tích **LAG** và **LEAD** để thực hiện các phép so sánh này mà không cần tự nối bảng với chính nó:

- **LAG** lấy giá trị từ một dòng nằm trước dòng hiện tại theo thứ tự trong analytic window.
- **LEAD** lấy giá trị từ một dòng nằm sau dòng hiện tại theo thứ tự đó.

Hai hàm này thuộc nhóm analytic functions (hàm phân tích). Chúng giữ lại các dòng đầu vào và bổ sung giá trị tham chiếu từ dòng lân cận. Muốn dùng chính xác, cần hiểu PARTITION BY, ORDER BY, offset, default, cách xử lý NULL và tính xác định của thứ tự dòng.

## 1. Ý tưởng: nhìn sang dòng trước hoặc dòng sau

Giả sử bảng doanh thu theo tháng:

| MONTH_START | REVENUE |
|---|---:|
| 2026-01-01 | 100 |
| 2026-02-01 | 120 |
| 2026-03-01 | 90 |
| 2026-04-01 | 150 |

Ta muốn thêm cột doanh thu tháng trước và tháng sau:

| MONTH_START | REVENUE | PREVIOUS_REVENUE | NEXT_REVENUE |
|---|---:|---:|---:|
| 2026-01-01 | 100 | NULL | 120 |
| 2026-02-01 | 120 | 100 | 90 |
| 2026-03-01 | 90 | 120 | 150 |
| 2026-04-01 | 150 | 90 | NULL |

LAG tạo PREVIOUS_REVENUE; LEAD tạo NEXT_REVENUE. Dòng đầu không có dòng trước, dòng cuối không có dòng sau nên mặc định kết quả là NULL.

~~~sql
SELECT month_start,
       revenue,
       LAG(revenue) OVER (
           ORDER BY month_start
       ) AS previous_revenue,
       LEAD(revenue) OVER (
           ORDER BY month_start
       ) AS next_revenue
FROM monthly_revenue
ORDER BY month_start;
~~~

Điểm cần nhớ: LAG và LEAD không so sánh theo thứ tự vật lý đang lưu trong bảng. Thứ tự được xác định bởi ORDER BY bên trong OVER.

## 2. Cú pháp LAG và LEAD

### 2.1 Cú pháp Oracle

~~~sql
LAG(value_expr [, offset [, default]])
    [ { RESPECT | IGNORE } NULLS ]
    OVER (
        [PARTITION BY expr [, expr] ...]
        ORDER BY expr [ASC | DESC] [NULLS FIRST | NULLS LAST]
             [, expr ...]
    )
~~~

LEAD có cùng cấu trúc:

~~~sql
LEAD(value_expr [, offset [, default]])
    [ { RESPECT | IGNORE } NULLS ]
    OVER (
        [PARTITION BY expr [, expr] ...]
        ORDER BY expr [ASC | DESC] [NULLS FIRST | NULLS LAST]
             [, expr ...]
    )
~~~

Ý nghĩa các đối số:

| Thành phần | Ý nghĩa |
|---|---|
| value_expr | Biểu thức cần lấy từ dòng khác, ví dụ AMOUNT, STATUS hoặc EVENT_TIME |
| offset | Số vị trí dòng cần lùi (LAG) hoặc tiến (LEAD); mặc định là 1 |
| default | Giá trị trả về nếu không có dòng ở vị trí offset; mặc định là NULL |
| RESPECT NULLS | Giữ NULL như một giá trị của dòng; đây là mặc định |
| IGNORE NULLS | Bỏ qua các giá trị NULL của value_expr khi xác định dòng cần lấy |
| PARTITION BY | Chia dữ liệu thành các nhóm độc lập; hàm bắt đầu lại trong mỗi nhóm |
| ORDER BY | Xác định thứ tự dòng dùng để tìm trước/sau |

LAG/LEAD cần ORDER BY trong analytic clause. Không có một khái niệm “dòng trước” có ý nghĩa nếu chưa xác định thứ tự.

### 2.2 LAG mặc định lấy dòng ngay trước

~~~sql
LAG(revenue) OVER (ORDER BY month_start)
~~~

tương đương:

~~~sql
LAG(revenue, 1, NULL) OVER (ORDER BY month_start)
~~~

Offset mặc định là 1 và default mặc định là NULL.

### 2.3 LEAD mặc định lấy dòng ngay sau

~~~sql
LEAD(revenue) OVER (ORDER BY month_start)
~~~

tương đương:

~~~sql
LEAD(revenue, 1, NULL) OVER (ORDER BY month_start)
~~~

### 2.4 Lấy cách hai dòng

~~~sql
SELECT event_id,
       event_time,
       LAG(amount, 2) OVER (
           ORDER BY event_time, event_id
       ) AS amount_two_rows_before,
       LEAD(amount, 2) OVER (
           ORDER BY event_time, event_id
       ) AS amount_two_rows_after
FROM account_events;
~~~

Offset 2 nghĩa là hai vị trí dòng theo thứ tự, không phải hai ngày hoặc hai tháng. Nếu dữ liệu bị thiếu một ngày, LAG(..., 1) vẫn lấy dòng ngay trước hiện có, chứ không tự tìm ngày lịch liền kề.

### 2.5 Default chỉ dùng khi không có dòng ở vị trí cần lấy

~~~sql
SELECT month_start,
       revenue,
       LAG(revenue, 1, 0) OVER (
           ORDER BY month_start
       ) AS previous_revenue
FROM monthly_revenue;
~~~

Ở dòng đầu tiên, không có dòng trước nên default 0 được trả về. Nhưng nếu dòng trước tồn tại và REVENUE của dòng đó là NULL, với mặc định RESPECT NULLS, kết quả vẫn là NULL. Default không thay thế một giá trị NULL đã tồn tại ở dòng tham chiếu.

Nếu muốn thay cả trường hợp không có dòng trước lẫn trường hợp giá trị tham chiếu là NULL bằng 0, có thể dùng:

~~~sql
NVL(
    LAG(revenue) OVER (ORDER BY month_start),
    0
) AS previous_revenue_or_zero
~~~

Chỉ thay NULL bằng 0 nếu nghiệp vụ coi hai tình huống đó tương đương. Nếu cần phân biệt “không có dòng trước” và “có dòng trước nhưng measure chưa ghi”, hãy giữ NULL và thêm metadata như ROW_NUMBER hoặc cờ riêng.

## 3. ORDER BY quyết định ý nghĩa dòng trước/sau

### 3.1 Thứ tự phải phản ánh nghiệp vụ

Ví dụ:

~~~sql
LAG(amount) OVER (ORDER BY event_time)
~~~

nghĩa là lấy giá trị của dòng có EVENT_TIME đứng ngay trước theo thứ tự tăng dần. Nếu muốn so sánh giao dịch theo thời gian, EVENT_TIME là một khóa sắp xếp hợp lý.

Nếu dùng:

~~~sql
LAG(amount) OVER (ORDER BY amount)
~~~

thì dòng trước là dòng có AMOUNT thấp hơn theo thứ tự số, không nhất thiết là giao dịch xảy ra trước. Câu SQL có thể hợp lệ nhưng ý nghĩa nghiệp vụ khác.

### 3.2 Thêm khóa phụ để thứ tự xác định

Giả sử hai giao dịch có cùng EVENT_TIME:

| EVENT_ID | EVENT_TIME | AMOUNT |
|---:|---|---:|
| 101 | 2026-11-14 10:00:00 | 50 |
| 102 | 2026-11-14 10:00:00 | 70 |

Nếu chỉ viết:

~~~sql
LAG(amount) OVER (ORDER BY event_time)
~~~

Oracle không có cơ sở để bảo đảm thứ tự giữa hai dòng cùng thời điểm. Dòng nào được coi là trước có thể không ổn định giữa các lần thực thi hoặc kế hoạch khác nhau.

Nên thêm khóa phân biệt:

~~~sql
LAG(amount) OVER (
    ORDER BY event_time, event_id
)
~~~

Nếu EVENT_ID là duy nhất, cặp EVENT_TIME, EVENT_ID tạo thứ tự xác định. Quy tắc này đặc biệt quan trọng cho đối soát giao dịch, phát hiện thay đổi và xử lý sự kiện tuần tự.

### 3.3 ORDER BY trong OVER khác ORDER BY cuối câu truy vấn

~~~sql
SELECT event_id,
       event_time,
       LAG(amount) OVER (
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events
ORDER BY event_id DESC;
~~~

Hai ORDER BY có hai mục đích:

- ORDER BY trong OVER xác định dòng mà LAG/LEAD tham chiếu.
- ORDER BY cuối truy vấn sắp xếp cách các dòng được trả về cho client.

Đổi thứ tự hiển thị ở ngoài không làm thay đổi giá trị previous_amount đã được tính theo event_time và event_id.

### 3.4 ASC, DESC và NULLS FIRST/LAST

Với ORDER BY tăng dần, Oracle mặc định NULLS LAST; với giảm dần, mặc định NULLS FIRST. Nếu cột sắp xếp có thể NULL, hãy quyết định rõ vị trí NULL:

~~~sql
LAG(status) OVER (
    PARTITION BY customer_id
    ORDER BY changed_at ASC NULLS LAST, history_id
)
~~~

Trong dữ liệu sự kiện, tốt nhất nên có timestamp không NULL nếu timestamp là trục thời gian chính. Nếu NULL mang nghĩa chưa xác định, việc đưa NULL lên đầu/cuối sẽ ảnh hưởng dòng nào được coi là trước/sau.

## 4. PARTITION BY: bắt đầu lại trong từng nhóm

Nếu bảng chứa nhiều khách hàng, ta thường muốn lấy giao dịch trước của **cùng khách hàng**, không phải giao dịch trước của toàn bộ bảng.

~~~sql
SELECT customer_id,
       event_time,
       amount,
       LAG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events
ORDER BY customer_id, event_time, event_id;
~~~

PARTITION BY chia dữ liệu thành các nhóm độc lập:

~~~text
CUSTOMER 10:  dòng 1 -> dòng 2 -> dòng 3
              LAG     LAG

CUSTOMER 20:  dòng 1 -> dòng 2
              LAG

CUSTOMER 30:  dòng 1
~~~

Ở dòng đầu của mỗi customer, LAG không tìm thấy dòng trước trong partition nên trả NULL (hoặc default). Nó không lấy dòng cuối của customer trước đó.

### 4.1 Nhiều cột trong PARTITION BY

~~~sql
LAG(balance) OVER (
    PARTITION BY account_id, currency_code
    ORDER BY transaction_time, transaction_id
)
~~~

Ví dụ này so sánh số dư trong cùng tài khoản và cùng loại tiền. Nếu bỏ CURRENCY_CODE, dòng USD có thể bị so sánh với dòng EUR của cùng account, dẫn đến kết quả sai nghiệp vụ.

### 4.2 Không có PARTITION BY

~~~sql
LAG(amount) OVER (
    ORDER BY event_time, event_id
)
~~~

Khi không có PARTITION BY, toàn bộ tập dòng sau FROM/WHERE/GROUP BY/HAVING thuộc một partition. Dòng đầu tiên của toàn bộ tập không có giá trị trước.

### 4.3 PARTITION BY không sắp xếp kết quả cuối cùng

PARTITION BY chỉ định nhóm độc lập cho analytic function. Nó không đảm bảo kết quả được trả theo thứ tự partition. Nếu cần hiển thị theo customer rồi theo thời gian, thêm ORDER BY ngoài:

~~~sql
ORDER BY customer_id, event_time, event_id
~~~

## 5. So sánh LAG và LEAD

| Tiêu chí | LAG | LEAD |
|---|---|---|
| Hướng tham chiếu | Về phía dòng trước | Về phía dòng sau |
| Offset mặc định | 1 | 1 |
| Default khi không có dòng | NULL | NULL |
| PARTITION BY | Hỗ trợ | Hỗ trợ |
| ORDER BY | Xác định thứ tự | Xác định thứ tự |
| NULL handling | RESPECT/IGNORE NULLS | RESPECT/IGNORE NULLS |
| Ví dụ | Doanh thu kỳ trước | Doanh thu kỳ sau |

Hai hàm có cùng cách khai báo; khác nhau ở hướng lấy giá trị. Nếu ORDER BY ASC theo thời gian:

- LAG lấy sự kiện thời gian trước.
- LEAD lấy sự kiện thời gian sau.

Nếu ORDER BY DESC, ý nghĩa “trước/sau” theo thứ tự analytic bị đảo so với trục thời gian tăng dần. Hãy kiểm tra chiều sort trước khi đặt tên alias như PREVIOUS_EVENT hoặc NEXT_EVENT.

## 6. So sánh giá trị hiện tại với dòng trước

### 6.1 Tính chênh lệch tuyệt đối

~~~sql
SELECT customer_id,
       event_time,
       amount,
       amount - LAG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY event_time, event_id
       ) AS change_from_previous
FROM account_events
ORDER BY customer_id, event_time, event_id;
~~~

Nếu amount hiện tại là 150 và dòng trước là 120, chênh lệch bằng 30. Nếu dòng đầu partition hoặc giá trị trước NULL, kết quả phép trừ là NULL.

### 6.2 Tính tỷ lệ phần trăm thay đổi

~~~sql
WITH compared AS (
    SELECT customer_id,
           event_time,
           event_id,
           amount,
           LAG(amount) OVER (
               PARTITION BY customer_id
               ORDER BY event_time, event_id
           ) AS previous_amount
    FROM account_events
)
SELECT customer_id,
       event_time,
       amount,
       previous_amount,
       amount - previous_amount AS amount_change,
       CASE
         WHEN previous_amount IS NULL OR previous_amount = 0
           THEN NULL
         ELSE ROUND(
             (amount - previous_amount) / previous_amount * 100,
             2
         )
       END AS percent_change
FROM compared
ORDER BY customer_id, event_time, event_id;
~~~

Công thức:

\[
\text{Percent change} =
\frac{\text{Current} - \text{Previous}}{\text{Previous}}\times 100
\]

Nếu giá trị trước bằng 0, phần trăm thay đổi không xác định theo công thức này; ví dụ trả NULL. Nếu nghiệp vụ cần hiển thị “mới phát sinh”, “không có cơ sở so sánh” hoặc một quy ước khác, hãy dùng CASE để biểu diễn rõ.

Ví dụ giả định AMOUNT không NULL. Nếu AMOUNT có thể NULL, cần phân biệt:

- Không có dòng trước.
- Có dòng trước nhưng amount NULL.
- Có dòng trước với amount bằng 0.

Không gộp các tình huống đó thành một tỷ lệ phần trăm mặc định nếu ý nghĩa khác nhau.

### 6.3 Phân loại tăng, giảm hoặc không đổi

~~~sql
WITH compared AS (
    SELECT product_id,
           sale_date,
           sale_id,
           quantity,
           LAG(quantity) OVER (
               PARTITION BY product_id
               ORDER BY sale_date, sale_id
           ) AS previous_quantity
    FROM product_sales
)
SELECT product_id,
       sale_date,
       quantity,
       previous_quantity,
       CASE
         WHEN previous_quantity IS NULL THEN 'NO PRIOR VALUE'
         WHEN quantity > previous_quantity THEN 'INCREASED'
         WHEN quantity < previous_quantity THEN 'DECREASED'
         ELSE 'UNCHANGED'
       END AS trend
FROM compared
ORDER BY product_id, sale_date, sale_id;
~~~

Ở ví dụ này, NULL được dùng làm dấu hiệu không có giá trị trước. Nếu quantity trong bảng có thể NULL, điều kiện đầu tiên chưa đủ để nhận diện dòng đầu. Có thể thêm ROW_NUMBER để phân biệt dòng đầu với dòng trước có quantity NULL.

### 6.4 Dùng ROW_NUMBER để nhận diện dòng đầu chắc chắn

~~~sql
WITH compared AS (
    SELECT product_id,
           sale_date,
           sale_id,
           quantity,
           ROW_NUMBER() OVER (
               PARTITION BY product_id
               ORDER BY sale_date, sale_id
           ) AS row_num,
           LAG(quantity) OVER (
               PARTITION BY product_id
               ORDER BY sale_date, sale_id
           ) AS previous_quantity
    FROM product_sales
)
SELECT product_id,
       sale_date,
       quantity,
       previous_quantity,
       CASE
         WHEN row_num = 1 THEN 'FIRST ROW'
         WHEN previous_quantity IS NULL THEN 'PREVIOUS VALUE IS NULL'
         WHEN quantity = previous_quantity
              OR (quantity IS NULL AND previous_quantity IS NULL)
           THEN 'UNCHANGED'
         ELSE 'CHANGED'
       END AS change_status
FROM compared
ORDER BY product_id, sale_date, sale_id;
~~~

ROW_NUMBER xác định vị trí dòng trong partition. Nó không bị nhầm giữa “không có dòng trước” và “dòng trước có giá trị NULL”.

## 7. Dùng LEAD để xem trước dòng kế tiếp

### 7.1 So sánh với kỳ tiếp theo

~~~sql
SELECT region,
       month_start,
       revenue,
       LEAD(revenue) OVER (
           PARTITION BY region
           ORDER BY month_start
       ) AS next_month_revenue
FROM monthly_revenue
ORDER BY region, month_start;
~~~

Ví dụ này giúp nhìn doanh thu hiện tại so với tháng sau, hỗ trợ lập kế hoạch và phân tích xu hướng.

### 7.2 Tính khoảng cách đến sự kiện kế tiếp

Với cột EVENT_TIME kiểu DATE:

~~~sql
SELECT account_id,
       event_id,
       event_time,
       LEAD(event_time) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS next_event_time,
       LEAD(event_time) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) - event_time AS days_until_next_event
FROM account_events
ORDER BY account_id, event_time, event_id;
~~~

DATE trừ DATE trong Oracle trả về NUMBER biểu diễn số ngày, có thể gồm phần lẻ. Nếu cột là TIMESTAMP, phép trừ trả về INTERVAL DAY TO SECOND; kiểu kết quả khác nên cách định dạng hoặc tính đơn vị cũng khác.

### 7.3 Tìm khoảng trống lớn giữa hai sự kiện

~~~sql
WITH event_gaps AS (
    SELECT account_id,
           event_id,
           event_time,
           LEAD(event_time) OVER (
               PARTITION BY account_id
               ORDER BY event_time, event_id
           ) AS next_event_time
    FROM account_events
)
SELECT account_id,
       event_id,
       event_time,
       next_event_time,
       next_event_time - event_time AS gap_in_days
FROM event_gaps
WHERE next_event_time - event_time > 7
ORDER BY account_id, event_time, event_id;
~~~

Ví dụ tìm sự kiện có khoảng cách hơn 7 ngày đến sự kiện kế tiếp. Dòng cuối của mỗi partition không có next_event_time nên phép so sánh WHERE là UNKNOWN và không được trả về.

Nếu cần tính chính xác theo giờ, phút hoặc múi giờ, hãy chọn kiểu dữ liệu thời gian phù hợp và định nghĩa rõ đơn vị của khoảng cách.

## 8. Offset và default trong tình huống thực tế

### 8.1 Lấy giá trị cách hai dòng

~~~sql
SELECT product_id,
       sale_date,
       quantity,
       LAG(quantity, 2) OVER (
           PARTITION BY product_id
           ORDER BY sale_date, sale_id
       ) AS quantity_two_sales_ago
FROM product_sales;
~~~

Đây là giá trị của giao dịch thứ hai trước trong chuỗi đã sắp xếp, không phải giá trị đúng hai ngày trước.

### 8.2 Lấy giá trị sau ba dòng

~~~sql
SELECT event_id,
       LEAD(status, 3, 'NO LATER STATUS') OVER (
           PARTITION BY order_id
           ORDER BY changed_at, history_id
       ) AS status_three_changes_later
FROM order_status_history;
~~~

Default được dùng khi không tồn tại dòng thứ ba phía sau trong partition. Giá trị default phải tương thích kiểu với value_expr. Trong ví dụ, STATUS là chuỗi nên default cũng là chuỗi.

### 8.3 Default không thay NULL của dòng tham chiếu

~~~sql
SELECT event_id,
       status,
       LAG(status, 1, 'NO PREVIOUS ROW') OVER (
           PARTITION BY order_id
           ORDER BY changed_at, history_id
       ) AS previous_status
FROM order_status_history;
~~~

Nếu dòng trước tồn tại nhưng STATUS của nó là NULL, PREVIOUS_STATUS vẫn là NULL với RESPECT NULLS. Chuỗi 'NO PREVIOUS ROW' chỉ xuất hiện khi không có dòng trước.

### 8.4 Default và NVL giải quyết hai trường hợp khác nhau

| Cách viết | Khi không có dòng trước | Khi dòng trước có giá trị NULL |
|---|---|---|
| LAG(x) | NULL | NULL |
| LAG(x, 1, 0) | 0 | NULL |
| NVL(LAG(x), 0) | 0 | 0 |
| LAG(x) IGNORE NULLS | Tìm dòng có x khác NULL trước đó; nếu không có thì NULL | Bỏ qua dòng có x NULL |

Chọn biểu thức theo semantics cần có, không chỉ theo mong muốn tránh NULL trên màn hình.

## 9. RESPECT NULLS và IGNORE NULLS

Mặc định Oracle dùng RESPECT NULLS. Khi đó NULL là một giá trị của dòng và được tính vào offset.

### 9.1 RESPECT NULLS

~~~sql
SELECT event_id,
       reading,
       LAG(reading) RESPECT NULLS OVER (
           ORDER BY event_id
       ) AS previous_reading
FROM sensor_readings;
~~~

Nếu dòng ngay trước có READING NULL, kết quả previous_reading là NULL. Dòng NULL đó vẫn chiếm một vị trí trong thứ tự.

Có thể bỏ từ khóa RESPECT NULLS vì đây là mặc định:

~~~sql
LAG(reading) OVER (ORDER BY event_id)
~~~

### 9.2 IGNORE NULLS

~~~sql
SELECT event_id,
       reading,
       LAG(reading) IGNORE NULLS OVER (
           ORDER BY event_id
       ) AS previous_known_reading
FROM sensor_readings;
~~~

IGNORE NULLS bỏ qua các giá trị NULL của value_expr khi tìm giá trị offset. Nếu dòng ngay trước có READING NULL, Oracle tiếp tục tìm lùi để lấy giá trị READING không NULL gần nhất.

Ví dụ:

| EVENT_ID | READING | LAG RESPECT NULLS | LAG IGNORE NULLS |
|---:|---:|---:|---:|
| 1 | 10 | NULL | NULL |
| 2 | NULL | 10 | 10 |
| 3 | 15 | NULL | 10 |
| 4 | NULL | 15 | 15 |
| 5 | 20 | NULL | 15 |

Ở EVENT_ID 3, dòng trước là EVENT_ID 2 với READING NULL. RESPECT trả NULL; IGNORE tìm ngược đến EVENT_ID 1 và trả 10.

### 9.3 IGNORE NULLS không xóa dòng khỏi kết quả

IGNORE NULLS chỉ thay đổi cách LAG/LEAD tìm value_expr. Các dòng có reading NULL vẫn xuất hiện trong result set nếu truy vấn ngoài không lọc chúng. Nó không tương đương WHERE reading IS NOT NULL.

### 9.4 LEAD IGNORE NULLS

~~~sql
SELECT event_id,
       reading,
       LEAD(reading) IGNORE NULLS OVER (
           ORDER BY event_id
       ) AS next_known_reading
FROM sensor_readings;
~~~

Oracle bỏ qua các giá trị reading NULL phía sau để tìm giá trị không NULL kế tiếp.

### 9.5 Khi nào dùng IGNORE NULLS?

Có thể dùng khi:

- Một chuỗi trạng thái chỉ ghi giá trị khi có thay đổi, các dòng trung gian NULL cần bỏ qua.
- Dữ liệu đo có các lần ghi không có giá trị nhưng vẫn muốn so sánh với lần đo đã biết trước.
- Báo cáo cần giá trị quan sát gần nhất khác NULL.

Không dùng nếu NULL có ý nghĩa nghiệp vụ cần giữ lại, ví dụ “đã xóa giá trị”, “không áp dụng” hoặc “chưa xác định” mà bản thân việc NULL xuất hiện là một sự kiện cần phân tích.

## 10. LAG/LEAD sau khi tổng hợp

LAG và LEAD có thể áp dụng trên kết quả đã GROUP BY. Đây là mẫu phổ biến cho báo cáo tháng/quý:

~~~sql
WITH monthly AS (
    SELECT region,
           TRUNC(sale_date, 'MM') AS month_start,
           SUM(amount) AS monthly_revenue
    FROM sales
    GROUP BY region, TRUNC(sale_date, 'MM')
)
SELECT region,
       month_start,
       monthly_revenue,
       LAG(monthly_revenue) OVER (
           PARTITION BY region
           ORDER BY month_start
       ) AS previous_month_revenue,
       monthly_revenue
         - LAG(monthly_revenue) OVER (
             PARTITION BY region
             ORDER BY month_start
           ) AS change_from_previous_month
FROM monthly
ORDER BY region, month_start;
~~~

Quy trình logic:

1. GROUP BY tính doanh thu theo REGION và tháng.
2. CTE monthly tạo một dòng cho mỗi khu vực/tháng có dữ liệu.
3. LAG so sánh mỗi tổng tháng với tổng tháng trước trong cùng REGION.

Nếu một khu vực không có giao dịch trong tháng 2, CTE có thể không có dòng tháng 2. LAG của tháng 3 sẽ lấy tháng có dữ liệu đứng trước, có thể là tháng 1. Nó không tự tạo tháng trống và không mặc định tháng trước là tháng lịch liền kề.

Nếu báo cáo cần đủ mọi tháng kể cả tháng không có doanh thu, phải tạo calendar/month dimension và LEFT JOIN dữ liệu tổng hợp vào đó trước khi áp dụng LAG. Khi ấy có thể dùng NVL để biểu diễn tháng không phát sinh là 0 nếu nghiệp vụ xác nhận.

## 11. LAG/LEAD và việc lọc kết quả

Oracle không cho phép dùng analytic function trực tiếp trong WHERE của cùng query block, vì analytic functions được tính sau WHERE, GROUP BY và HAVING.

Không hợp lệ:

~~~sql
SELECT event_id,
       event_time,
       amount,
       LAG(amount) OVER (
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events
WHERE amount > LAG(amount) OVER (
    ORDER BY event_time, event_id
);
~~~

Cách đúng là tính analytic value trong inline view hoặc CTE rồi lọc ở query block bên ngoài:

~~~sql
WITH compared AS (
    SELECT event_id,
           event_time,
           amount,
           LAG(amount) OVER (
               ORDER BY event_time, event_id
           ) AS previous_amount
    FROM account_events
)
SELECT event_id,
       event_time,
       amount,
       previous_amount
FROM compared
WHERE amount > previous_amount
ORDER BY event_time, event_id;
~~~

Ví dụ này lấy các dòng có amount lớn hơn dòng trước. Dòng đầu không có previous_amount nên điều kiện so sánh là UNKNOWN và bị loại.

### 11.1 Lọc theo dòng đầu

~~~sql
WITH numbered AS (
    SELECT customer_id,
           event_id,
           event_time,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY event_time, event_id
           ) AS rn
    FROM account_events
)
SELECT *
FROM numbered
WHERE rn = 1;
~~~

ROW_NUMBER giúp chọn dòng đầu của mỗi partition. Có thể kết hợp LAG để phân tích nhưng không cần suy luận dòng đầu từ một giá trị có thể NULL.

### 11.2 Lọc các dòng có thay đổi trạng thái

~~~sql
WITH history AS (
    SELECT order_id,
           history_id,
           changed_at,
           status,
           LAG(status) OVER (
               PARTITION BY order_id
               ORDER BY changed_at, history_id
           ) AS previous_status,
           ROW_NUMBER() OVER (
               PARTITION BY order_id
               ORDER BY changed_at, history_id
           ) AS rn
    FROM order_status_history
)
SELECT order_id,
       history_id,
       changed_at,
       previous_status,
       status
FROM history
WHERE rn > 1
  AND (
       status <> previous_status
       OR (status IS NULL AND previous_status IS NOT NULL)
       OR (status IS NOT NULL AND previous_status IS NULL)
  )
ORDER BY order_id, changed_at, history_id;
~~~

Điều kiện này giữ các dòng mà trạng thái khác dòng trước, kể cả một bên NULL. Nếu cả hai cùng NULL thì không xem là thay đổi. Cần dùng ROW_NUMBER để loại dòng đầu vì nó không có trạng thái trước.

## 12. LAG/LEAD so với self join và scalar subquery

Trước analytic functions, có thể tìm dòng trước bằng self join, ví dụ dùng ROW_NUMBER:

~~~sql
WITH numbered AS (
    SELECT account_id,
           event_id,
           event_time,
           amount,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY event_time, event_id
           ) AS rn
    FROM account_events
)
SELECT current_row.account_id,
       current_row.event_id,
       current_row.amount,
       previous_row.amount AS previous_amount
FROM numbered current_row
LEFT JOIN numbered previous_row
  ON previous_row.account_id = current_row.account_id
 AND previous_row.rn = current_row.rn - 1;
~~~

Đây là cách làm được nhưng dài hơn LAG:

~~~sql
SELECT account_id,
       event_id,
       amount,
       LAG(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events;
~~~

| Tiêu chí | LAG/LEAD | Self join |
|---|---|---|
| Lấy dòng trước/sau theo thứ tự | Cú pháp trực tiếp | Cần tạo khóa thứ tự hoặc điều kiện quan hệ |
| Giữ mọi dòng hiện tại | Có | Cần outer join nếu muốn giữ dòng không có cặp |
| Nhiều offset | Có thể gọi LAG/LEAD với offset khác nhau | Có thể cần thêm join |
| So sánh theo quan hệ không tuần tự | Không phải mục đích chính | Linh hoạt hơn |
| Lấy nhiều cột từ dòng trước | Có thể gọi LAG cho từng cột | Join một lần có thể thuận tiện hơn |

LAG/LEAD phù hợp khi khái niệm trước/sau được xác định bằng một thứ tự. Self join phù hợp hơn khi quan hệ giữa hai dòng được xác định bằng khóa hoặc quy tắc phức tạp không đơn thuần là vị trí liền kề.

## 13. Các trường hợp ứng dụng

### 13.1 So sánh số dư tài khoản

~~~sql
SELECT account_id,
       transaction_id,
       transaction_time,
       balance_after,
       LAG(balance_after) OVER (
           PARTITION BY account_id
           ORDER BY transaction_time, transaction_id
       ) AS previous_balance,
       balance_after
         - LAG(balance_after) OVER (
             PARTITION BY account_id
             ORDER BY transaction_time, transaction_id
           ) AS balance_change
FROM account_transactions
ORDER BY account_id, transaction_time, transaction_id;
~~~

Thứ tự cần có khóa phân biệt nếu nhiều giao dịch cùng timestamp. Nếu BALANCE_AFTER là số dư sau giao dịch, chênh lệch giữa hai dòng liên tiếp có thể giúp kiểm tra biến động; cần lưu ý giao dịch đầu tiên không có số dư trước trong tập đang truy vấn.

### 13.2 Phát hiện khoảng thời gian bất thường

~~~sql
WITH gaps AS (
    SELECT device_id,
           reading_id,
           reading_time,
           LAG(reading_time) OVER (
               PARTITION BY device_id
               ORDER BY reading_time, reading_id
           ) AS previous_reading_time
    FROM device_readings
)
SELECT device_id,
       reading_id,
       previous_reading_time,
       reading_time,
       reading_time - previous_reading_time AS gap_days
FROM gaps
WHERE previous_reading_time IS NOT NULL
  AND reading_time - previous_reading_time > 1
ORDER BY device_id, reading_time, reading_id;
~~~

Ví dụ tìm khoảng cách trên một ngày giữa hai lần đo DATE. Với TIMESTAMP, hiệu là INTERVAL; điều kiện so sánh nên dùng interval literal hoặc chuyển đổi phù hợp.

### 13.3 Phát hiện trạng thái chuyển đổi

~~~sql
WITH status_changes AS (
    SELECT order_id,
           history_id,
           changed_at,
           status,
           LAG(status) OVER (
               PARTITION BY order_id
               ORDER BY changed_at, history_id
           ) AS previous_status
    FROM order_status_history
)
SELECT order_id,
       history_id,
       changed_at,
       previous_status,
       status
FROM status_changes
WHERE previous_status <> status
ORDER BY order_id, changed_at, history_id;
~~~

Đây là ví dụ ngắn khi STATUS không NULL. Nếu STATUS nullable, phép so sánh <> không bắt được trường hợp một bên NULL; hãy dùng điều kiện null-safe như phần trước.

### 13.4 Tìm mức giá trước và sau

~~~sql
SELECT product_id,
       effective_from,
       price,
       LAG(price) OVER (
           PARTITION BY product_id
           ORDER BY effective_from, price_history_id
       ) AS previous_price,
       LEAD(price) OVER (
           PARTITION BY product_id
           ORDER BY effective_from, price_history_id
       ) AS next_price
FROM product_price_history
ORDER BY product_id, effective_from, price_history_id;
~~~

Ví dụ giúp đọc lịch sử giá. Nếu hai bản ghi có cùng EFFECTIVE_FROM, cần một quy tắc nghiệp vụ để quyết định thứ tự và giá nào có hiệu lực.

### 13.5 So sánh với ngày làm việc liền trước

LAG lấy dòng trước hiện có, không tự hiểu lịch làm việc. Nếu cần so sánh với ngày làm việc trước đó kể cả ngày không có giao dịch, hãy join với calendar dimension có đủ ngày làm việc, sau đó áp dụng LAG trên tập calendar đã chuẩn hóa.

## 14. Kiểu dữ liệu, NULL và các lưu ý kỹ thuật

### 14.1 value_expr phải là biểu thức hợp lệ

value_expr có thể là cột hoặc biểu thức tương thích:

~~~sql
LAG(amount * exchange_rate) OVER (
    PARTITION BY account_id
    ORDER BY event_time, event_id
)
~~~

Không lồng trực tiếp một analytic function khác bên trong value_expr của LAG/LEAD. Nếu cần lấy kết quả của một analytic function khác, tính nó trong inline view/CTE rồi áp dụng LAG ở query block bên ngoài.

### 14.2 Default cần tương thích kiểu

~~~sql
LAG(amount, 1, 0) OVER (ORDER BY event_time)
~~~

phù hợp khi AMOUNT là kiểu số và default là số. Nếu value_expr là DATE, dùng một giá trị DATE phù hợp; nếu là VARCHAR2, dùng literal chuỗi tương thích. Oracle áp dụng quy tắc chuyển kiểu cho đối số, nhưng nên viết rõ kiểu để tránh lỗi hoặc implicit conversion không mong muốn.

### 14.3 LAG trên DATE và TIMESTAMP

LAG có thể lấy giá trị DATE hoặc TIMESTAMP từ dòng trước. Bản thân LAG không tính khoảng cách thời gian; phép trừ sau đó mới quyết định kiểu kết quả:

- DATE - DATE: NUMBER, đơn vị ngày.
- TIMESTAMP - TIMESTAMP: INTERVAL DAY TO SECOND.

Nếu cần đổi ra giờ/phút, xử lý theo kiểu dữ liệu cụ thể, không giả định cả hai phép trừ trả NUMBER.

### 14.4 Không có window frame trong cú pháp LAG/LEAD

LAG và LEAD dùng offset theo vị trí dòng trong partition và có cú pháp OVER với PARTITION BY/ORDER BY. Không thêm mệnh đề ROWS BETWEEN như khi viết một số analytic aggregate; đó không phải phần cú pháp của LAG/LEAD.

## 15. Hiệu năng và execution plan

### 15.1 Sắp xếp là một phần của bài toán

Để xác định dòng trước/sau, Oracle cần xử lý thứ tự analytic. Với dữ liệu lớn, việc phân vùng và sắp xếp có thể tiêu tốn CPU, PGA hoặc TEMP tùy plan và kích thước tập dòng.

### 15.2 Index có thể hỗ trợ nhưng không bảo đảm bỏ được sort

Ví dụ truy vấn:

~~~sql
SELECT account_id,
       event_time,
       event_id,
       LAG(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events;
~~~

Một index theo thứ tự:

~~~sql
CREATE INDEX idx_account_events_order
ON account_events (account_id, event_time, event_id);
~~~

có thể hữu ích cho truy cập theo partition và thứ tự. Tuy nhiên Oracle vẫn có thể chọn sort hoặc access path khác tùy điều kiện lọc, cardinality, clustering factor và các thao tác khác. Không tạo index chỉ dựa vào một câu truy vấn minh họa.

### 15.3 Giảm dữ liệu đầu vào khi đúng semantics

Nếu chỉ phân tích một năm, có thể lọc trong query block nguồn trước khi áp dụng LAG:

~~~sql
WITH source_rows AS (
    SELECT account_id,
           event_id,
           event_time,
           amount
    FROM account_events
    WHERE event_time >= DATE '2026-01-01'
      AND event_time <  DATE '2027-01-01'
)
SELECT account_id,
       event_time,
       amount,
       LAG(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM source_rows;
~~~

Nhưng cần xác định yêu cầu: dòng đầu năm có cần so sánh với dòng cuối năm trước hay không? Nếu có, lọc năm trước khi tính LAG sẽ loại mất dòng tham chiếu. Khi đó phải đưa thêm dòng lịch sử cần thiết vào nguồn analytic rồi lọc kết quả sau khi tính.

Đây là điểm quan trọng: lọc sớm có thể giảm dữ liệu, nhưng cũng có thể thay đổi ý nghĩa “dòng trước”.

### 15.4 Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT account_id,
       event_time,
       amount,
       LAG(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN cho biết kế hoạch dự kiến. Khi tuning, xem actual execution plan, cardinality, sort/window operations, I/O, CPU và TEMP trên dữ liệu đại diện. Không kết luận hiệu năng chỉ từ số lần gọi LAG trong SELECT list.

## 16. Bài lab: LAG và LEAD với lịch sử giao dịch

Các lệnh trong phần này dành cho schema thực hành riêng có quyền tạo bảng và quota phù hợp. Không chạy DDL/DML thử nghiệm trên schema production. Oracle DDL như CREATE TABLE có implicit commit.

### 16.1 Tạo bảng

~~~sql
CREATE TABLE lab_account_events (
    event_id    NUMBER PRIMARY KEY,
    account_id  NUMBER NOT NULL,
    event_time  DATE NOT NULL,
    amount      NUMBER(12,2),
    status      VARCHAR2(20)
);
~~~

### 16.2 Nạp dữ liệu

~~~sql
INSERT INTO lab_account_events VALUES
    (1, 10, DATE '2026-11-01', 100, 'OPEN');
INSERT INTO lab_account_events VALUES
    (2, 10, DATE '2026-11-03', 120, 'OPEN');
INSERT INTO lab_account_events VALUES
    (3, 10, DATE '2026-11-03', 90, 'HOLD');
INSERT INTO lab_account_events VALUES
    (4, 10, DATE '2026-11-08', NULL, 'HOLD');
INSERT INTO lab_account_events VALUES
    (5, 10, DATE '2026-11-12', 150, 'CLOSED');
INSERT INTO lab_account_events VALUES
    (6, 20, DATE '2026-11-02', 50, 'OPEN');
INSERT INTO lab_account_events VALUES
    (7, 20, DATE '2026-11-05', 75, 'OPEN');
INSERT INTO lab_account_events VALUES
    (8, 20, DATE '2026-11-10', 60, 'HOLD');
COMMIT;
~~~

Account 10 có hai sự kiện cùng ngày để thể hiện vai trò của EVENT_ID trong tie-breaker; có một AMOUNT NULL để thử RESPECT/IGNORE NULLS. Account 20 tạo partition độc lập.

### 16.3 Xem dòng trước và dòng sau

~~~sql
SELECT account_id,
       event_id,
       event_time,
       amount,
       LAG(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_amount,
       LEAD(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS next_amount
FROM lab_account_events
ORDER BY account_id, event_time, event_id;
~~~

Kiểm tra:

- Event 1 của account 10 không có dòng trước trong partition.
- Event 3 lấy event 2 làm dòng trước dù cùng EVENT_TIME, vì EVENT_ID là khóa phụ.
- Event 4 có AMOUNT NULL; event 5 với RESPECT NULLS sẽ nhận previous_amount NULL.
- Event 6 là dòng đầu của account 20; nó không lấy event 5 của account 10.

### 16.4 So sánh RESPECT và IGNORE NULLS

~~~sql
SELECT account_id,
       event_id,
       amount,
       LAG(amount) RESPECT NULLS OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_respecting_null,
       LAG(amount) IGNORE NULLS OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_known_amount
FROM lab_account_events
ORDER BY account_id, event_time, event_id;
~~~

Ở event 5 của account 10:

- PREVIOUS_RESPECTING_NULL là NULL vì event 4 ngay trước có amount NULL.
- PREVIOUS_KNOWN_AMOUNT là 90 vì event 3 là giá trị amount không NULL gần nhất trước đó.

### 16.5 Tính chênh lệch

~~~sql
WITH compared AS (
    SELECT account_id,
           event_id,
           event_time,
           amount,
           LAG(amount) OVER (
               PARTITION BY account_id
               ORDER BY event_time, event_id
           ) AS previous_amount
    FROM lab_account_events
)
SELECT account_id,
       event_id,
       amount,
       previous_amount,
       amount - previous_amount AS amount_change
FROM compared
ORDER BY account_id, event_time, event_id;
~~~

Chênh lệch của event 2 account 10 là 20. Event 3 là -30 so với event 2. Event 5 cho NULL vì amount trước đó (event 4) là NULL theo RESPECT NULLS.

### 16.6 Lọc dòng tăng so với dòng trước

~~~sql
WITH compared AS (
    SELECT account_id,
           event_id,
           event_time,
           amount,
           LAG(amount) OVER (
               PARTITION BY account_id
               ORDER BY event_time, event_id
           ) AS previous_amount
    FROM lab_account_events
)
SELECT account_id,
       event_id,
       event_time,
       amount,
       previous_amount
FROM compared
WHERE amount > previous_amount
ORDER BY account_id, event_time, event_id;
~~~

Kết quả chỉ gồm các dòng có amount lớn hơn amount của dòng trước và cả hai giá trị so sánh đều xác định.

### 16.7 Nhận diện dòng đầu mỗi tài khoản

~~~sql
SELECT account_id,
       event_id,
       event_time,
       ROW_NUMBER() OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS row_num
FROM lab_account_events
ORDER BY account_id, event_time, event_id;
~~~

Lọc ROW_NUM=1 ở query block ngoài để lấy dòng đầu mỗi tài khoản.

### 16.8 Dọn bảng lab

Chỉ xóa bảng do bạn tạo trong schema lab khi đã xác nhận không còn cần dữ liệu. Không đưa DROP TABLE vào script có thể chạy nhầm production; DDL có implicit commit và không thể trông chờ ROLLBACK để khôi phục.

## 17. Lỗi và ngộ nhận thường gặp

| Lỗi/ngộ nhận | Thực tế | Cách xử lý |
|---|---|---|
| LAG luôn lấy dòng trước theo thứ tự lưu vật lý | LAG dùng ORDER BY trong OVER | Khai báo thứ tự nghiệp vụ rõ |
| Không cần ORDER BY | Không xác định được dòng trước/sau có ý nghĩa | Luôn dùng analytic ORDER BY |
| Chỉ ORDER BY timestamp là đủ | Nhiều dòng có thể trùng timestamp | Thêm khóa phụ duy nhất |
| PARTITION BY chỉ sắp xếp | Nó chia các nhóm độc lập và reset offset | Chọn đúng khóa nhóm |
| ORDER BY cuối câu truy vấn điều khiển LAG | ORDER BY ngoài chỉ sắp kết quả trả về | Đặt ORDER BY trong OVER |
| Offset 2 nghĩa là hai ngày trước | Offset đếm vị trí dòng | Dùng calendar/date logic nếu cần ngày lịch |
| Default thay mọi NULL | Default chỉ dùng khi không có dòng ở offset | Dùng NVL nếu muốn thay cả NULL của dòng tham chiếu |
| IGNORE NULLS xóa dòng NULL khỏi kết quả | Nó chỉ bỏ qua giá trị NULL khi tìm offset | Không nhầm với WHERE IS NOT NULL |
| LEAD luôn là ngày tương lai | Nó là dòng sau theo thứ tự OVER | Kiểm tra ASC/DESC |
| LAG có thể dùng trực tiếp trong WHERE cùng query block | Analytic function được tính sau WHERE | Dùng CTE/inline view |
| LAG trên tháng luôn lấy tháng lịch trước | Nó lấy dòng trước hiện có | Dùng calendar dimension nếu cần đủ tháng |
| Correlated/self join luôn nhanh hơn analytic | Optimizer và shape dữ liệu quyết định | Xem plan và runtime |
| LAG NULL nghĩa là dòng đầu | Có thể dòng trước tồn tại nhưng value_expr NULL | Dùng ROW_NUMBER để phân biệt |
| LAG/LEAD chấp nhận window frame như SUM | Cú pháp LAG/LEAD không có windowing clause | Chỉ dùng PARTITION BY/ORDER BY |

## 18. Checklist trước khi đưa vào báo cáo hoặc ứng dụng

- Xác định chính xác “trước” và “sau” theo thời gian, số thứ tự, phiên bản hay khóa nghiệp vụ.
- Dùng PARTITION BY để ngăn so sánh chéo giữa khách hàng, tài khoản, sản phẩm hoặc nhóm khác nhau.
- Bổ sung tie-breaker để ORDER BY xác định duy nhất khi có giá trị trùng.
- Xác định NULL nên được tôn trọng hay bỏ qua; RESPECT NULLS là mặc định.
- Phân biệt không có dòng tham chiếu với dòng tham chiếu có value_expr NULL.
- Chọn offset theo số vị trí dòng, không nhầm với số ngày/tháng.
- Nếu cần đủ các kỳ lịch, tạo calendar dimension hoặc chuỗi kỳ đầy đủ trước khi tính LAG/LEAD.
- Nếu cần lọc theo kết quả analytic, dùng inline view hoặc CTE.
- Khi lọc dữ liệu đầu vào, kiểm tra xem có làm mất dòng lịch sử cần dùng để so sánh hay không.
- Xem kiểu dữ liệu của default, value_expr và phép tính sau LAG/LEAD.
- Kiểm tra execution plan và workload thực tế trước khi thêm index.

## 19. Bài tập tự luyện

**Câu 1 — Dòng trước.** Một partition có các giá trị 10, 20, 15 theo thứ tự. Kết quả LAG(x) lần lượt là gì?

Gợi ý: NULL, 10, 20.

**Câu 2 — Dòng sau.** Với cùng dữ liệu, LEAD(x) lần lượt là gì?

Gợi ý: 20, 15, NULL.

**Câu 3 — Offset.** LAG(x, 2) ở dòng thứ tư lấy giá trị nào?

Gợi ý: Giá trị ở dòng thứ hai trong cùng partition, vì offset đếm vị trí dòng.

**Câu 4 — Partition.** Nếu có hai tài khoản, vì sao dòng đầu tài khoản thứ hai không lấy giá trị cuối của tài khoản thứ nhất?

Gợi ý: PARTITION BY chia chuỗi độc lập và offset được reset trong mỗi partition.

**Câu 5 — Tie-breaker.** Hai sự kiện cùng EVENT_TIME; cần thêm gì để thứ tự ổn định?

Gợi ý: Một khóa phụ duy nhất như EVENT_ID, nếu đó là quy tắc thứ tự nghiệp vụ phù hợp.

**Câu 6 — Default.** So sánh LAG(amount,1,0) và NVL(LAG(amount),0) khi dòng trước tồn tại nhưng AMOUNT NULL.

Gợi ý: Cách thứ nhất trả NULL; cách thứ hai trả 0.

**Câu 7 — NULL handling.** Dòng hiện tại có giá trị 30, dòng trước có giá trị NULL, dòng trước nữa có 20. LAG(value) RESPECT NULLS và IGNORE NULLS trả gì?

Gợi ý: RESPECT trả NULL; IGNORE trả 20.

**Câu 8 — Lọc.** Vì sao không thể đặt LAG trực tiếp trong WHERE cùng query block?

Gợi ý: Analytic function được tính sau WHERE; hãy tính trong CTE rồi lọc ở ngoài.

**Câu 9 — Tháng trống.** Dữ liệu có tháng 1 và tháng 3 nhưng không có tháng 2. LAG của tháng 3 trả tháng nào?

Gợi ý: Tháng 1 vì đó là dòng trước hiện có. Muốn so với tháng 2 phải tạo calendar đầy đủ trước.

**Câu 10 — Kiểu thời gian.** DATE trừ DATE và TIMESTAMP trừ TIMESTAMP khác nhau thế nào trong Oracle?

Gợi ý: DATE trả NUMBER theo đơn vị ngày; TIMESTAMP trả INTERVAL DAY TO SECOND.

## 20. Tổng kết

**LAG** và **LEAD** là các analytic functions giúp lấy giá trị từ dòng trước hoặc dòng sau theo một thứ tự đã xác định:

- LAG lấy giá trị lùi về trước; LEAD lấy giá trị tiến về sau.
- Offset mặc định là 1; default mặc định là NULL và chỉ dùng khi không có dòng ở vị trí yêu cầu.
- PARTITION BY chia dữ liệu thành các nhóm độc lập; ORDER BY trong OVER xác định thứ tự tham chiếu.
- RESPECT NULLS là mặc định; IGNORE NULLS bỏ qua giá trị NULL của biểu thức khi tìm offset.
- ORDER BY cần tie-breaker nếu khóa sắp xếp có thể trùng, để kết quả ổn định.
- LAG/LEAD giữ các dòng hiện tại; chúng không tổng hợp hay tự tạo những ngày/tháng còn thiếu.
- Muốn lọc kết quả analytic, tính trong CTE hoặc inline view rồi lọc ở query block bên ngoài.

Khi cần so sánh doanh thu kỳ trước, phát hiện thay đổi trạng thái, đo khoảng cách sự kiện hoặc phân tích lịch sử theo từng tài khoản, LAG và LEAD thường giúp SQL ngắn gọn và thể hiện đúng ý định hơn self join. Điều quan trọng nhất là định nghĩa đúng partition, thứ tự, cách xử lý NULL và ý nghĩa của offset trước khi sử dụng kết quả trong báo cáo hoặc nghiệp vụ.
