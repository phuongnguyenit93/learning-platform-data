# DATE_ADD, DATE_SUB, TIMESTAMPDIFF và xử lý cuối tháng

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Cộng hoặc trừ ngày giờ bằng DATE_ADD và DATE_SUB với các đơn vị phù hợp.
- Tính khoảng cách thời gian bằng TIMESTAMPDIFF và phân biệt nó với DATEDIFF.
- Hiểu cách MySQL điều chỉnh ngày khi cộng hoặc trừ tháng qua các tháng có số ngày khác nhau.
- Xây dựng lịch thanh toán, hạn dùng và chu kỳ định kỳ mà không bị trôi ngày ngoài ý muốn.
- Xác định đầu tháng, cuối tháng và khoảng thời gian tháng bằng LAST_DAY cùng phép tính ngày.
- Viết điều kiện lọc theo khoảng ngày có thể tận dụng index.
- Kiểm soát timezone, độ chính xác và dữ liệu ngày giờ không hợp lệ.

Các phép tính ngày giờ tưởng đơn giản nhưng có nhiều quy tắc dễ gây sai lệch nghiệp vụ. Cộng một tháng vào ngày 31 không phải lúc nào cũng tạo ra ngày 31 của tháng kế tiếp. Tính số tháng giữa hai ngày cũng không giống lấy số ngày chia cho 30. Bài học này giải thích các hàm MySQL thường dùng và cách áp dụng chúng vào lịch định kỳ, hạn thanh toán, báo cáo theo tháng và truy vấn thời gian.

## 1. DATE_ADD và DATE_SUB

### 1.1. Cú pháp cơ bản

DATE_ADD cộng một khoảng thời gian vào giá trị ngày giờ; DATE_SUB trừ một khoảng thời gian:

~~~sql
DATE_ADD(date_expression, INTERVAL value unit)
DATE_SUB(date_expression, INTERVAL value unit)
~~~

Trong đó:

- date_expression là giá trị DATE, DATETIME, TIMESTAMP hoặc biểu thức ngày giờ hợp lệ.
- value là số lượng đơn vị cần cộng hoặc trừ.
- unit là đơn vị thời gian, ví dụ DAY, WEEK, MONTH, YEAR, HOUR hoặc MINUTE.

Ví dụ:

~~~sql
SELECT
    DATE_ADD('2024-05-10', INTERVAL 7 DAY) AS after_seven_days,
    DATE_SUB('2024-05-10', INTERVAL 7 DAY) AS before_seven_days,
    DATE_ADD('2024-05-10 09:30:00', INTERVAL 2 HOUR) AS after_two_hours,
    DATE_SUB('2024-05-10 09:30:00', INTERVAL 15 MINUTE) AS before_fifteen_minutes;
~~~

Kết quả lần lượt là ngày 17-05-2024, ngày 03-05-2024, 11:30 cùng ngày và 09:15 cùng ngày.

DATE_ADD và DATE_SUB trả về một giá trị ngày giờ mới; chúng không sửa trực tiếp cột trong bảng. Muốn lưu kết quả, dùng UPDATE hoặc INSERT có chủ đích.

Kiểu kết quả phụ thuộc đối số đầu và đơn vị. Chẳng hạn, DATE cộng DAY vẫn cho kết quả dạng DATE; khi cộng HOUR vào DATE, kết quả cần biểu diễn cả phần giờ nên là DATETIME. Nếu ứng dụng phụ thuộc kiểu dữ liệu trả về, hãy kiểm tra bằng truy vấn thử trên phiên bản MySQL mục tiêu.

### 1.2. Các đơn vị thường dùng

| Unit | Ý nghĩa | Ví dụ |
|---|---|---|
| MICROSECOND | Micro giây | INTERVAL 500000 MICROSECOND |
| SECOND | Giây | INTERVAL 30 SECOND |
| MINUTE | Phút | INTERVAL 15 MINUTE |
| HOUR | Giờ | INTERVAL 2 HOUR |
| DAY | Ngày | INTERVAL 7 DAY |
| WEEK | Tuần | INTERVAL 2 WEEK |
| MONTH | Tháng lịch | INTERVAL 1 MONTH |
| QUARTER | Quý lịch, 3 tháng | INTERVAL 1 QUARTER |
| YEAR | Năm lịch | INTERVAL 1 YEAR |

MySQL còn hỗ trợ các đơn vị ghép như DAY_HOUR, DAY_MINUTE, DAY_SECOND, HOUR_MINUTE, HOUR_SECOND, MINUTE_SECOND và YEAR_MONTH. Với đơn vị ghép, cách viết value có định dạng riêng. Ví dụ:

~~~sql
SELECT
    DATE_ADD('2024-01-01 08:00:00',
             INTERVAL '1 02:30:00' DAY_SECOND) AS result_datetime,
    DATE_ADD('2024-01-01',
             INTERVAL '1-2' YEAR_MONTH) AS result_year_month;
~~~

Giá trị INTERVAL ghép phải theo đúng định dạng của unit. Khi logic nghiệp vụ chỉ cần cộng một đơn vị, hãy ưu tiên cú pháp đơn giản như INTERVAL 3 DAY hoặc INTERVAL 2 MONTH để dễ đọc và kiểm tra.

### 1.3. Cộng/trừ vào cột trong bảng

Giả sử đơn hàng có thời điểm tạo và hạn thanh toán:

~~~sql
CREATE TABLE invoice (
    invoice_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL,
    due_at DATETIME NOT NULL,
    paid_at DATETIME NULL,
    PRIMARY KEY (invoice_id),
    KEY idx_invoice_due_at (due_at)
) ENGINE = InnoDB;
~~~

Đặt hạn thanh toán sau 14 ngày:

~~~sql
INSERT INTO invoice (created_at, due_at)
VALUES (
    CURRENT_TIMESTAMP,
    DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 14 DAY)
);
~~~

Gia hạn một hóa đơn thêm 3 ngày:

~~~sql
UPDATE invoice
SET due_at = DATE_ADD(due_at, INTERVAL 3 DAY)
WHERE invoice_id = 1001;
~~~

Điều kiện WHERE cần xác định đúng bản ghi. Nếu nghiệp vụ có quy tắc không được gia hạn quá hạn tối đa, phải kiểm tra quy tắc đó trong cùng transaction hoặc trong logic cập nhật phù hợp.

### 1.4. DATE_ADD không phải phép cộng số học thông thường

Không nên thay DATE_ADD bằng cách cộng một số nguyên vào chuỗi ngày. Ví dụ, cộng 30 vào một biểu thức ngày không có nghĩa là cộng 30 ngày theo lịch. Dùng INTERVAL giúp MySQL hiểu đơn vị lịch và xử lý chuyển tháng, năm nhuận.

Cũng cần phân biệt:

- INTERVAL 1 MONTH là một tháng lịch, không phải 30 ngày.
- INTERVAL 1 YEAR là một năm lịch, không phải 365 ngày.
- INTERVAL 1 DAY là một ngày lịch; trong ngữ cảnh timezone và DST, một ngày lịch có thể không tương đương đúng 24 giờ thực.

## 2. Quy tắc cộng và trừ tháng

### 2.1. Tháng đích không có ngày tương ứng

Khi cộng tháng, nếu ngày trong tháng nguồn không tồn tại ở tháng đích, MySQL điều chỉnh về ngày cuối cùng của tháng đích.

Ví dụ:

~~~sql
SELECT
    DATE_ADD('2024-01-31', INTERVAL 1 MONTH) AS leap_year_result,
    DATE_ADD('2023-01-31', INTERVAL 1 MONTH) AS normal_year_result,
    DATE_SUB('2024-03-31', INTERVAL 1 MONTH) AS subtract_month_result,
    DATE_ADD('2024-01-30', INTERVAL 1 MONTH) AS january_thirtieth_result;
~~~

Kết quả:

| Phép tính | Kết quả |
|---|---|
| 31-01-2024 + 1 MONTH | 29-02-2024 |
| 31-01-2023 + 1 MONTH | 28-02-2023 |
| 31-03-2024 - 1 MONTH | 29-02-2024 |
| 30-01-2024 + 1 MONTH | 29-02-2024 |

Đây là điều chỉnh theo lịch. MySQL không tạo ngày 31-02 rồi tự chuyển sang tháng 3; kết quả được chốt ở ngày cuối hợp lệ của tháng đích.

### 2.2. Năm nhuận

Một năm Gregorian là năm nhuận nếu chia hết cho 4, ngoại trừ năm tròn thế kỷ không chia hết cho 400. Vì vậy:

- 2024 là năm nhuận: tháng 2 có 29 ngày.
- 2023 không phải năm nhuận: tháng 2 có 28 ngày.
- 2000 là năm nhuận.
- 1900 không phải năm nhuận.

Có thể dùng LAST_DAY để xác nhận số ngày cuối tháng:

~~~sql
SELECT
    LAST_DAY('2024-02-01') AS leap_february,
    LAST_DAY('2023-02-01') AS normal_february;
~~~

### 2.3. Cộng tháng liên tiếp có thể làm ngày bị trôi

Một lỗi phổ biến là lấy ngày đến hạn vừa tính được làm mốc cho kỳ tiếp theo. Khi mốc ban đầu là ngày cuối tháng, việc cộng từng tháng có thể làm ngày bị trôi.

~~~sql
SELECT
    DATE_ADD(
        DATE_ADD('2023-01-31', INTERVAL 1 MONTH),
        INTERVAL 1 MONTH
    ) AS repeated_addition,
    DATE_ADD('2023-01-31', INTERVAL 2 MONTH) AS anchored_addition;
~~~

Kết quả:

| Cách tính | Kết quả |
|---|---|
| 31-01 + 1 tháng = 28-02; sau đó + 1 tháng | 28-03-2023 |
| Tính trực tiếp 31-01 + 2 tháng từ mốc ban đầu | 31-03-2023 |

Lần cộng thứ nhất đã tạo ra ngày 28-02. Khi cộng tiếp từ ngày 28, MySQL không biết nghiệp vụ ban đầu muốn duy trì ngày 31 hoặc ngày cuối tháng; nó chỉ cộng một tháng từ giá trị hiện tại.

**Quy tắc thiết kế:** lưu ngày neo (anchor date) hoặc quy tắc lịch gốc. Tính kỳ thứ n trực tiếp từ mốc ban đầu, không liên tục cộng từ kết quả kỳ trước nếu muốn giữ ngày neo.

### 2.4. Hai quy tắc lịch định kỳ khác nhau

Nghiệp vụ có thể muốn một trong hai cách:

**Giữ cùng ngày trong tháng, nếu không tồn tại thì chốt vào ngày cuối tháng.**

~~~sql
SELECT DATE_ADD('2023-01-31', INTERVAL 2 MONTH) AS due_date;
~~~

Kết quả là 31-03-2023. Với kỳ tháng 2, kết quả được chốt thành 28-02-2023.

**Luôn đến hạn vào ngày cuối tháng.**

~~~sql
SELECT
    LAST_DAY(DATE_ADD('2023-01-01', INTERVAL 1 MONTH)) AS february_due,
    LAST_DAY(DATE_ADD('2023-01-01', INTERVAL 2 MONTH)) AS march_due;
~~~

Kết quả là 28-02-2023 và 31-03-2023.

Hai quy tắc không giống nhau đối với một ngày neo không phải cuối tháng. Ví dụ, ngày neo 30-01 có thể tạo kỳ tiếp theo 28-02 rồi 30-03 nếu giữ ngày neo; quy tắc cuối tháng sẽ tạo 28-02 rồi 31-03. Hãy ghi rõ quy tắc trong nghiệp vụ thay vì suy luận từ một ví dụ.

## 3. LAST_DAY và các mốc đầu/cuối tháng

### 3.1. Lấy ngày cuối tháng

LAST_DAY(date) trả về ngày cuối cùng của tháng chứa date:

~~~sql
SELECT
    LAST_DAY('2024-01-10') AS january_end,
    LAST_DAY('2024-02-10') AS february_end,
    LAST_DAY('2024-04-10') AS april_end;
~~~

Kết quả là 31-01-2024, 29-02-2024 và 30-04-2024.

Nếu đầu vào NULL hoặc không phải ngày hợp lệ, kết quả có thể là NULL hoặc phát cảnh báo tùy biểu thức và SQL mode. Hãy xác thực dữ liệu đầu vào trước khi dùng trong lịch nghiệp vụ.

### 3.2. Lấy ngày đầu tháng

Có thể trừ số ngày đã đi qua trong tháng, trừ một ngày:

~~~sql
SELECT
    DATE_SUB(
        DATE('2024-05-19'),
        INTERVAL DAYOFMONTH('2024-05-19') - 1 DAY
    ) AS month_start;
~~~

Kết quả là 01-05-2024.

Với cột ngày giờ, biểu thức tổng quát:

~~~sql
DATE_SUB(
    DATE(date_expression),
    INTERVAL DAYOFMONTH(date_expression) - 1 DAY
)
~~~

### 3.3. Lấy ngày đầu tháng kế tiếp

Từ ngày cuối tháng cộng một ngày:

~~~sql
SELECT
    DATE_ADD(LAST_DAY('2024-02-12'), INTERVAL 1 DAY)
        AS next_month_start;
~~~

Kết quả là 01-03-2024.

Có thể lấy mốc đầu tháng hiện tại bằng công thức này:

~~~sql
SET @month_start =
    DATE_SUB(CURDATE(), INTERVAL DAYOFMONTH(CURDATE()) - 1 DAY);

SET @next_month_start =
    DATE_ADD(@month_start, INTERVAL 1 MONTH);

SELECT @month_start, @next_month_start;
~~~

Hai mốc này rất hữu ích để lọc dữ liệu theo tháng.

## 4. TIMESTAMPDIFF: tính khoảng cách giữa hai thời điểm

### 4.1. Cú pháp và chiều tính

TIMESTAMPDIFF nhận đơn vị, thời điểm bắt đầu và thời điểm kết thúc:

~~~sql
TIMESTAMPDIFF(unit, datetime_expr1, datetime_expr2)
~~~

Giá trị trả về là số nguyên đơn vị thời gian từ datetime_expr1 đến datetime_expr2, tức là thời điểm thứ hai trừ thời điểm thứ nhất.

~~~sql
SELECT
    TIMESTAMPDIFF(DAY, '2024-05-01', '2024-05-10') AS forward_days,
    TIMESTAMPDIFF(DAY, '2024-05-10', '2024-05-01') AS backward_days;
~~~

Kết quả là 9 và -9. Thứ tự hai đối số rất quan trọng. Nếu đảo chỗ, dấu của kết quả đổi.

### 4.2. Các đơn vị được hỗ trợ

TIMESTAMPDIFF hỗ trợ các đơn vị:

- MICROSECOND
- SECOND
- MINUTE
- HOUR
- DAY
- WEEK
- MONTH
- QUARTER
- YEAR

Ví dụ:

~~~sql
SELECT
    TIMESTAMPDIFF(HOUR,
        '2024-05-01 08:00:00',
        '2024-05-01 13:45:00') AS elapsed_hours,
    TIMESTAMPDIFF(MINUTE,
        '2024-05-01 08:00:00',
        '2024-05-01 13:45:00') AS elapsed_minutes,
    TIMESTAMPDIFF(SECOND,
        '2024-05-01 08:00:00',
        '2024-05-01 13:45:00') AS elapsed_seconds;
~~~

Các kết quả là số nguyên theo đơn vị yêu cầu. Phần lẻ của đơn vị bị bỏ đi; ví dụ 5 giờ 45 phút cho kết quả 5 khi tính HOUR.

### 4.3. TIMESTAMPDIFF không trả về phân số tháng/năm

Với MONTH và YEAR, kết quả biểu diễn số đơn vị lịch hoàn chỉnh theo quy tắc của MySQL, không phải số ngày chia cho 30 hoặc 365.

~~~sql
SELECT
    TIMESTAMPDIFF(MONTH, '2024-01-31', '2024-02-29')
        AS completed_months_1,
    TIMESTAMPDIFF(MONTH, '2024-01-31', '2024-03-31')
        AS completed_months_2,
    TIMESTAMPDIFF(YEAR, '2020-06-15', '2024-06-14')
        AS completed_years_before_anniversary,
    TIMESTAMPDIFF(YEAR, '2020-06-15', '2024-06-15')
        AS completed_years_on_anniversary;
~~~

Kết quả lần lượt là 0, 2, 3 và 4. Từ 31-01 đến 29-02 chưa đủ một tháng trọn vẹn theo phép tính tháng của TIMESTAMPDIFF, dù đã đi qua một ranh giới tháng trên lịch.

Nếu nghiệp vụ cần số tháng lịch đã đi qua, số kỳ hóa đơn, hoặc số tháng tính theo ngày cuối tháng, hãy định nghĩa quy tắc riêng và kiểm tra bằng ví dụ biên. Đừng dùng TIMESTAMPDIFF(MONTH) như bộ đếm số lần đổi tháng trên lịch.

### 4.4. Phân biệt TIMESTAMPDIFF và DATEDIFF

DATEDIFF(expr1, expr2) trả về số ngày lịch của phần DATE(expr1) trừ DATE(expr2) theo thứ tự đối số: expr1 - expr2. Trong thực tế thường dùng DATEDIFF(end_date, start_date) để nhận số ngày từ start đến end. Hàm bỏ qua phần giờ.

TIMESTAMPDIFF(DAY, start, end) tính số ngày nguyên theo khoảng cách giữa hai giá trị ngày giờ và có xét phần thời gian trong ngày.

~~~sql
SELECT
    DATEDIFF(
        '2024-01-02 01:00:00',
        '2024-01-01 23:00:00'
    ) AS calendar_day_difference,
    TIMESTAMPDIFF(
        DAY,
        '2024-01-01 23:00:00',
        '2024-01-02 01:00:00'
    ) AS full_day_difference,
    TIMESTAMPDIFF(
        HOUR,
        '2024-01-01 23:00:00',
        '2024-01-02 01:00:00'
    ) AS full_hour_difference;
~~~

Kết quả là 1 ngày lịch, 0 ngày trọn vẹn và 2 giờ. Chọn hàm theo câu hỏi nghiệp vụ:

| Câu hỏi | Hàm phù hợp |
|---|---|
| Hai ngày cách nhau bao nhiêu ngày lịch, bỏ qua giờ? | DATEDIFF(end_date, start_date) |
| Đã trôi qua bao nhiêu giờ/phút/giây nguyên? | TIMESTAMPDIFF |
| Đã đủ bao nhiêu tháng hoặc năm theo quy tắc lịch của MySQL? | TIMESTAMPDIFF(MONTH/YEAR, start, end) |
| Muốn cộng một tháng lịch vào mốc? | DATE_ADD(..., INTERVAL 1 MONTH) |

## 5. Ứng dụng thực tế

### 5.1. Tính tuổi theo năm hoàn chỉnh

Với ngày sinh lưu trong cột DATE:

~~~sql
SELECT
    customer_id,
    birth_date,
    TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) AS age_years
FROM customer;
~~~

TIMESTAMPDIFF(YEAR, ...) trả về số năm hoàn chỉnh theo quy tắc lịch. Nếu nghiệp vụ có quy ước riêng về sinh nhật ngày 29-02 trong năm không nhuận, hãy xác định rõ ngày được xem là ngày kỷ niệm và kiểm thử trường hợp đó.

### 5.2. Tính thời gian xử lý ticket

~~~sql
SELECT
    ticket_id,
    created_at,
    closed_at,
    TIMESTAMPDIFF(MINUTE, created_at, closed_at) AS processing_minutes
FROM support_ticket
WHERE closed_at IS NOT NULL;
~~~

Nếu ticket chưa đóng, closed_at là NULL và phép tính trả về NULL. Không nên tự thay NULL bằng NOW() trong mọi báo cáo nếu mục tiêu là chỉ đo ticket đã đóng. Với báo cáo thời gian đang mở, có thể dùng COALESCE hoặc biểu thức riêng, nhưng phải đặt tên chỉ số rõ ràng.

### 5.3. Tính ngày hết hạn

~~~sql
SELECT
    subscription_id,
    started_on,
    DATE_ADD(started_on, INTERVAL 1 YEAR) AS expires_on
FROM subscription;
~~~

Nếu ngày bắt đầu là 29-02 của năm nhuận, ngày hết hạn sau một năm được điều chỉnh theo lịch tháng 2 của năm đích. Nghiệp vụ cần xác định ngày hết hạn là ngày tương ứng được clamp, ngày cuối tháng hay thời điểm kết thúc ngày. Đây là quyết định sản phẩm, không chỉ là quyết định SQL.

### 5.4. Báo cáo doanh thu theo tháng

Giả sử bảng payment có cột paid_at kiểu DATETIME và index:

~~~sql
CREATE INDEX idx_payment_paid_at
ON payment (paid_at);
~~~

Lọc một tháng bằng khoảng nửa mở:

~~~sql
SELECT
    SUM(amount) AS monthly_revenue
FROM payment
WHERE paid_at >= '2024-02-01 00:00:00'
  AND paid_at <  '2024-03-01 00:00:00';
~~~

Điều kiện gồm mọi thời điểm từ đầu tháng 2 đến trước đầu tháng 3. Cách này không cần đoán thời điểm cuối ngày như 23:59:59.999999 và có thể tận dụng index trên paid_at.

Tính động đầu tháng và đầu tháng kế tiếp:

~~~sql
SET @month_start =
    DATE_SUB(CURDATE(), INTERVAL DAYOFMONTH(CURDATE()) - 1 DAY);

SET @next_month_start =
    DATE_ADD(@month_start, INTERVAL 1 MONTH);

SELECT SUM(amount) AS monthly_revenue
FROM payment
WHERE paid_at >= @month_start
  AND paid_at < @next_month_start;
~~~

Tránh viết:

~~~sql
WHERE DATE(paid_at) BETWEEN '2024-02-01' AND '2024-02-29'
~~~

Khi bọc cột index trong hàm DATE(), optimizer thường không thể dùng range access thông thường trên index paid_at theo cách hiệu quả như điều kiện khoảng. Hãy đặt phép tính ở phía hằng số/biến và giữ cột ở dạng nguyên bản trong điều kiện.

## 6. Cuối tháng trong nghiệp vụ định kỳ

### 6.1. Hóa đơn đến hạn vào ngày cuối tháng

Một số hợp đồng quy định hóa đơn đến hạn vào ngày cuối mỗi tháng. Dùng LAST_DAY:

~~~sql
SELECT
    DATE('2024-01-15') AS anchor_date,
    LAST_DAY(DATE('2024-01-15')) AS first_due_date,
    LAST_DAY(DATE_ADD('2024-01-15', INTERVAL 1 MONTH))
        AS next_due_date;
~~~

Cách tính này lấy ngày cuối của tháng chứa ngày neo và tháng kế tiếp. Nếu muốn tháng thứ n tính từ mốc ban đầu, hãy tính trực tiếp từ anchor:

~~~sql
SELECT
    LAST_DAY(DATE_ADD('2024-01-01', INTERVAL 1 MONTH)) AS period_1,
    LAST_DAY(DATE_ADD('2024-01-01', INTERVAL 2 MONTH)) AS period_2,
    LAST_DAY(DATE_ADD('2024-01-01', INTERVAL 3 MONTH)) AS period_3;
~~~

### 6.2. Hạn vào ngày cố định, nhưng chốt cuối tháng nếu thiếu ngày

Ví dụ hợp đồng bắt đầu ngày 30 hoặc 31 và mỗi tháng muốn giữ cùng số ngày; nếu tháng đích không có ngày đó thì dùng ngày cuối tháng. Có thể tính từ ngày neo ban đầu:

~~~sql
SELECT
    DATE_ADD('2024-01-30', INTERVAL 1 MONTH) AS period_1,
    DATE_ADD('2024-01-30', INTERVAL 2 MONTH) AS period_2,
    DATE_ADD('2024-01-30', INTERVAL 3 MONTH) AS period_3;
~~~

Kết quả là 29-02, 30-03 và 30-04. Nếu neo là 31-01-2024, các kỳ tương ứng là 29-02, 31-03 và 30-04. Mỗi kỳ được tính từ cùng ngày neo, tránh trôi từ ngày đã bị điều chỉnh của kỳ trước.

### 6.3. Đếm ngày còn lại đến hạn

~~~sql
SELECT
    invoice_id,
    due_at,
    TIMESTAMPDIFF(DAY, CURRENT_TIMESTAMP, due_at) AS whole_days_remaining
FROM invoice
WHERE due_at >= CURRENT_TIMESTAMP;
~~~

Giá trị là số ngày nguyên còn lại theo thời điểm hiện tại. Nếu cần phân loại chính xác theo ngày lịch của người dùng, hãy chuyển về timezone nghiệp vụ và dùng quy tắc ngày lịch tương ứng. Không nhầm “còn 1 ngày lịch” với “còn đủ 24 giờ”.

## 7. DATE, DATETIME, TIMESTAMP và timezone

### 7.1. Chọn kiểu dữ liệu đúng câu hỏi

| Kiểu | Ý nghĩa thường dùng | Lưu ý |
|---|---|---|
| DATE | Một ngày lịch, không có giờ | Sinh nhật, ngày phát hành, ngày nghỉ |
| DATETIME | Ngày và giờ theo quy ước ứng dụng | Không tự chuyển đổi theo timezone khi lưu/đọc |
| TIMESTAMP | Một thời điểm; MySQL chuyển đổi giữa session time zone và UTC khi lưu/đọc | Phù hợp instant khi kiểm soát timezone kết nối |
| TIME | Thời gian trong ngày hoặc khoảng thời gian theo ngữ nghĩa MySQL | Không thay thế ngày giờ đầy đủ |

NOW() trả về thời điểm theo session time_zone. UTC_TIMESTAMP() trả về thời điểm UTC. CURRENT_DATE()/CURDATE() trả về ngày hiện tại theo timezone session. Nếu các kết nối dùng timezone khác nhau, kết quả các hàm hiện thời có thể khác ngày hoặc giờ.

### 7.2. DATETIME không tự đổi timezone; TIMESTAMP có chuyển đổi

DATETIME lưu các thành phần ngày giờ như được gửi đến. MySQL không tự biết đó là UTC hay giờ địa phương. TIMESTAMP được chuyển từ session time_zone sang UTC khi lưu và chuyển từ UTC sang session time_zone khi đọc.

Ví dụ kiểm tra timezone:

~~~sql
SELECT
    @@session.time_zone AS session_time_zone,
    @@global.time_zone AS global_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now,
    CURDATE() AS session_date;
~~~

Một ứng dụng nên thống nhất timezone của kết nối, thường chọn UTC cho các luồng lưu instant. Khi hiển thị cho người dùng, chuyển sang timezone địa phương ở lớp ứng dụng hoặc dùng CONVERT_TZ với timezone tables đã được nạp và cập nhật.

### 7.3. Daylight Saving Time (DST)

Ở các timezone có DST, ngày địa phương có thể dài 23 hoặc 25 giờ khi đồng hồ chuyển mùa. Điều này cần được tính đến khi làm việc với TIMESTAMP theo session time_zone có DST hoặc khi chuyển đổi thời điểm UTC sang giờ địa phương. DATETIME tự nó không mang timezone và phép tính trên DATETIME chỉ thao tác với các thành phần ngày giờ đã lưu. Do đó:

- Một ngày lịch không phải lúc nào cũng bằng 24 giờ thực.
- Cộng 1 DAY theo lịch có thể khác cộng 24 HOUR về thời điểm tuyệt đối khi xử lý instant trong timezone có DST.
- Một số giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần khi đồng hồ đổi giờ.

Nếu nghiệp vụ dùng ngày giờ địa phương, hãy lưu timezone định danh (ví dụ vùng IANA) bên cạnh quy tắc hoặc cấu hình người dùng. Kiểm thử các ngày chuyển DST. Không dùng độ lệch cố định như +07:00 thay cho timezone có quy tắc thay đổi nếu hệ thống phải phục vụ nhiều vùng.

Với lịch vận hành, ngày nghỉ hoặc ngày đến hạn theo lịch địa phương, xác định rõ phép tính là theo ngày lịch hay theo thời lượng thực. Đây là hai yêu cầu khác nhau.

## 8. NULL, dữ liệu không hợp lệ và độ chính xác

### 8.1. NULL truyền qua phép tính

Nếu một đối số ngày giờ là NULL, DATE_ADD, DATE_SUB, TIMESTAMPDIFF thường trả về NULL. Điều này hữu ích để biểu diễn “chưa có ngày kết thúc”, nhưng cần được tính đến trong điều kiện lọc và báo cáo.

~~~sql
SELECT
    TIMESTAMPDIFF(DAY, created_at, closed_at) AS elapsed_days
FROM support_ticket;
~~~

Ticket chưa đóng có closed_at NULL nên elapsed_days là NULL, không phải 0. Nếu thay bằng COALESCE(closed_at, NOW()), hãy chắc rằng chỉ số đang đo “thời gian đã trôi qua đến hiện tại” và tên cột phản ánh đúng điều đó.

### 8.2. Ngày bằng 0 và ngày không hợp lệ

Tránh dùng các giá trị như 0000-00-00 hoặc ngày không tồn tại. Hành vi chấp nhận, cảnh báo hoặc từ chối phụ thuộc phiên bản và SQL mode. Dùng strict SQL mode, kiểm tra dữ liệu nhập và không giả định mọi chuỗi ngày đều tự chuyển thành ngày hợp lệ.

Có thể kiểm tra dữ liệu lỗi trước khi chuyển đổi cột chuỗi sang DATE/DATETIME. STR_TO_DATE có thể trả về NULL hoặc cảnh báo với đầu vào không hợp lệ tùy phiên bản và mode; hãy kiểm tra kết quả và SHOW WARNINGS ngay sau thao tác.

### 8.3. Độ chính xác phần giây

DATETIME và TIMESTAMP hỗ trợ fractional seconds precision từ 0 đến 6. Nếu cột có microsecond, hãy cân nhắc độ chính xác của biểu thức và dữ liệu đầu vào.

~~~sql
SELECT
    TIMESTAMPDIFF(
        MICROSECOND,
        '2024-05-01 10:00:00.000000',
        '2024-05-01 10:00:00.250000'
    ) AS elapsed_microseconds;
~~~

Kết quả là 250000. Khi lọc khoảng thời gian, dùng mốc nửa mở thường an toàn hơn tự tạo mốc cuối ngày với số chữ số phần giây cố định.

## 9. Hiệu năng và khả năng dùng index

Một truy vấn thời gian thường lọc theo cột DATE, DATETIME hoặc TIMESTAMP. Nếu cột có index, hãy giữ cột ở dạng nguyên bản trong điều kiện range:

~~~sql
SELECT invoice_id, due_at
FROM invoice
WHERE due_at >= CURRENT_TIMESTAMP
  AND due_at < DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 7 DAY);
~~~

Có thể kiểm tra kế hoạch:

~~~sql
EXPLAIN
SELECT invoice_id, due_at
FROM invoice
WHERE due_at >= '2024-05-01 00:00:00'
  AND due_at <  '2024-06-01 00:00:00';
~~~

Tránh bọc cột bằng DATE(), YEAR(), MONTH() hoặc TIMESTAMPDIFF() trong WHERE nếu muốn range scan trên index thông thường. Ví dụ, thay vì:

~~~sql
WHERE YEAR(created_at) = 2024
  AND MONTH(created_at) = 5
~~~

hãy dùng:

~~~sql
WHERE created_at >= '2024-05-01 00:00:00'
  AND created_at <  '2024-06-01 00:00:00'
~~~

Điều kiện nửa mở cũng tránh vấn đề độ chính xác ở cuối ngày và hoạt động tốt cho cả DATETIME(0) lẫn DATETIME(6).

Nếu phải lọc thường xuyên theo ngày lịch từ cột DATETIME/TIMESTAMP và không thể đổi truy vấn, có thể cân nhắc generated column hoặc functional index trên phiên bản hỗ trợ. Tuy nhiên, hãy kiểm tra chi phí lưu trữ, cập nhật và tính tương thích trước khi thêm.

## 10. Quy trình chọn phép tính

Trước khi viết SQL, xác định câu hỏi:

| Yêu cầu nghiệp vụ | Cách tính |
|---|---|
| Cộng 10 ngày vào ngày tạo | DATE_ADD(created_at, INTERVAL 10 DAY) |
| Trừ 2 tháng lịch | DATE_SUB(value, INTERVAL 2 MONTH) |
| Lấy cuối tháng | LAST_DAY(value) |
| Lấy đầu tháng | DATE_SUB(DATE(value), INTERVAL DAYOFMONTH(value) - 1 DAY) |
| Lấy đầu tháng kế tiếp | DATE_ADD(LAST_DAY(value), INTERVAL 1 DAY) |
| Số ngày lịch giữa hai ngày | DATEDIFF(end_date, start_date) |
| Số giờ nguyên đã trôi qua | TIMESTAMPDIFF(HOUR, start_at, end_at) |
| Số tháng/năm hoàn chỉnh | TIMESTAMPDIFF(MONTH/YEAR, start_at, end_at) |
| Lọc mọi thời điểm trong một tháng | created_at >= month_start AND created_at < next_month_start |
| Lịch định kỳ vào ngày cuối tháng | LAST_DAY(DATE_ADD(anchor_month, INTERVAL n MONTH)) |
| Lịch định kỳ giữ ngày neo | DATE_ADD(anchor_date, INTERVAL n MONTH) |

Đặc biệt, hãy xác định rõ “một tháng” nghĩa là tháng lịch, 30 ngày, hay một kỳ hoàn chỉnh giữa hai mốc. Các khái niệm này không thể thay thế cho nhau.

## 11. Bài tập thực hành

### Bài 1: Thử DATE_ADD và DATE_SUB

Chạy các phép cộng/trừ 7 DAY, 2 WEEK, 1 MONTH, 1 QUARTER và 1 YEAR. Thử cả DATE lẫn DATETIME để quan sát kiểu kết quả.

### Bài 2: Kiểm tra cuối tháng và năm nhuận

Tính ngày sau 1 MONTH từ 28, 29, 30 và 31 tháng 1 trong cả năm nhuận lẫn năm thường. So sánh với LAST_DAY.

### Bài 3: Phát hiện ngày bị trôi

So sánh cộng liên tiếp hai lần INTERVAL 1 MONTH với cộng trực tiếp INTERVAL 2 MONTH từ cùng ngày neo 31-01. Giải thích vì sao kết quả khác nhau.

### Bài 4: Tính khoảng cách

Tính TIMESTAMPDIFF(DAY), HOUR, MINUTE, MONTH và YEAR cho hai mốc có giờ khác nhau. So sánh với DATEDIFF và giải thích phần thời gian bị bỏ qua hoặc bị cắt.

### Bài 5: Báo cáo theo tháng có index

Tạo index trên payment.paid_at. Viết truy vấn lấy doanh thu một tháng bằng khoảng nửa mở. Dùng EXPLAIN so sánh với truy vấn có YEAR(paid_at) và MONTH(paid_at) trong WHERE.

### Bài 6: Thiết kế lịch thanh toán

Thiết kế lịch cho khách hàng đăng ký ngày 29, 30 hoặc 31. Viết hai phương án: giữ ngày neo và luôn đến hạn cuối tháng. Ghi rõ kết quả trong tháng 2, tháng 3 và năm nhuận.

### Bài 7: Kiểm tra timezone

Đặt session time_zone ở UTC và một timezone địa phương có DST trên môi trường test. So sánh NOW(), UTC_TIMESTAMP(), phép cộng 1 DAY và 24 HOUR quanh thời điểm chuyển DST. Ghi lại khác biệt và khôi phục timezone ban đầu.

## Kết luận

DATE_ADD và DATE_SUB thực hiện phép tính theo đơn vị lịch hoặc thời lượng mà INTERVAL chỉ định. TIMESTAMPDIFF trả về số nguyên đơn vị giữa hai mốc và không thay thế cho phép đếm ranh giới tháng hoặc ngày lịch. LAST_DAY cùng các mốc đầu tháng giúp xử lý chu kỳ và báo cáo cuối tháng rõ ràng.

Với lịch định kỳ, hãy giữ ngày neo và xác định rõ quy tắc cuối tháng để tránh ngày bị trôi. Với truy vấn theo tháng, dùng khoảng nửa mở để giữ khả năng tận dụng index. Cuối cùng, thống nhất timezone và kiểm thử năm nhuận, DST, NULL cùng độ chính xác phần giây để kết quả SQL khớp với quy tắc nghiệp vụ.

