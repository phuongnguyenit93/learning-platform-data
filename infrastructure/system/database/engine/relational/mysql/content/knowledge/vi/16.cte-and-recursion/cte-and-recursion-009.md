# Sinh dãy ngày, bù dữ liệu thiếu kỳ và tổng hợp theo lịch

Trong báo cáo vận hành, doanh thu hoặc hoạt động người dùng, dữ liệu nguồn thường chỉ có những ngày phát sinh giao dịch. Nếu ngày 03 và ngày 06 không có đơn hàng, truy vấn nhóm trực tiếp trên bảng giao dịch sẽ không tạo hàng cho hai ngày đó. Biểu đồ vì vậy có thể bỏ qua ngày không hoạt động thay vì thể hiện rõ giá trị bằng 0. Báo cáo theo tháng cũng gặp vấn đề tương tự khi một tháng chưa có bản ghi.

Một cách giải quyết là tạo trước một dãy kỳ lịch (date series hoặc date spine), sau đó ghép dữ liệu thực tế vào từng kỳ. MySQL 8.0 hỗ trợ recursive common table expression (recursive CTE), cho phép sinh ngày hoặc tháng liên tiếp mà không cần tạo sẵn một bảng lịch. Kết hợp dãy kỳ với LEFT JOIN và hàm tổng hợp, ta có thể trả về đủ các ngày/tháng trong khoảng yêu cầu, kể cả khi không có dữ liệu.

Bài học này hướng dẫn sinh dãy ngày và tháng bằng recursive CTE, bù kỳ thiếu, tổng hợp chỉ tiêu theo lịch, lọc DATETIME thân thiện với index, kiểm soát giới hạn đệ quy và xử lý ranh giới múi giờ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích date spine và lý do cần tạo dãy kỳ độc lập với dữ liệu giao dịch.
- Dùng recursive CTE để sinh ngày liên tiếp trong một khoảng.
- Đặt điều kiện dừng đệ quy và kiểm tra trường hợp ngày bắt đầu lớn hơn ngày kết thúc.
- Ghép dãy ngày với dữ liệu giao dịch bằng LEFT JOIN để giữ ngày không có dữ liệu.
- Tính số giao dịch, tổng tiền, số giao dịch theo trạng thái và các chỉ tiêu khác theo ngày.
- Sinh dãy tháng và tổng hợp theo tháng, kể cả khi tháng không có giao dịch.
- Phân biệt cách nối với cột DATE và DATETIME/TIMESTAMP.
- Tránh đặt điều kiện ở WHERE làm mất các hàng được bổ sung bởi LEFT JOIN.
- Hiểu giới hạn đệ quy và khi nào nên dùng bảng lịch thay cho recursive CTE.
- Tính biên ngày theo múi giờ nghiệp vụ, bao gồm ngày có thay đổi DST.

## 1. Vì sao truy vấn GROUP BY không tự tạo kỳ trống?

Giả sử bảng giao dịch chỉ có dữ liệu vào ngày 01, 02 và 05:

    SELECT
        order_date,
        COUNT(*) AS order_count,
        SUM(amount) AS revenue
    FROM calendar_order_demo
    GROUP BY order_date
    ORDER BY order_date;

Kết quả chỉ có những ngày xuất hiện trong bảng nguồn. GROUP BY gom các hàng hiện có; nó không tự tạo ngày 03, 04 hoặc những ngày nằm trong khoảng nhưng không có hàng.

Nếu biểu đồ cần một điểm cho mọi ngày, kể cả ngày không có giao dịch, cần tạo tập ngày trước rồi LEFT JOIN dữ liệu vào tập đó. Những ngày không tìm được giao dịch sẽ có các cột phía giao dịch là NULL; sau đó có thể dùng COUNT và COALESCE để thể hiện số lượng hoặc tổng tiền bằng 0 theo quy tắc báo cáo.

Quy trình tổng quát:

1. Xác định khoảng ngày hoặc tháng cần báo cáo.
2. Sinh một hàng cho mỗi kỳ trong khoảng đó.
3. Tổng hợp dữ liệu nguồn theo cùng đơn vị thời gian.
4. LEFT JOIN kết quả tổng hợp vào dãy kỳ.
5. Thay NULL bằng 0 cho các chỉ tiêu có quy ước hiển thị là 0.
6. Sắp xếp theo kỳ lịch.

## 2. Chuẩn bị bảng dữ liệu thực hành

Tạo bảng đơn hàng với cột ngày kiểu DATE:

    CREATE TABLE calendar_order_demo (
        order_id BIGINT UNSIGNED NOT NULL,
        customer_id BIGINT UNSIGNED NOT NULL,
        order_status VARCHAR(20) NOT NULL,
        order_date DATE NOT NULL,
        amount DECIMAL(12,2) NOT NULL,
        PRIMARY KEY (order_id),
        KEY idx_calendar_order_date (order_date),
        KEY idx_calendar_order_customer (customer_id)
    ) ENGINE = InnoDB;

    INSERT INTO calendar_order_demo
        (order_id, customer_id, order_status, order_date, amount)
    VALUES
        (101, 1001, 'PAID',      '2025-01-01', 120.00),
        (102, 1002, 'PENDING',   '2025-01-02',  80.00),
        (103, 1001, 'CANCELLED', '2025-01-02',  50.00),
        (104, 1003, 'PAID',      '2025-01-05', 200.00),
        (105, 1004, 'PAID',      '2025-01-05', 150.00),
        (106, 1003, 'REFUNDED',  '2025-01-07',  40.00);

Dữ liệu có đơn vào ngày 01, 02, 05 và 07/01/2025; các ngày còn lại trong tuần không có đơn. Bảng có index trên order_date để các ví dụ lọc theo khoảng ngày có thể dùng range access.

Kiểm tra:

    SELECT order_id, order_status, order_date, amount
    FROM calendar_order_demo
    ORDER BY order_date, order_id;

## 3. Sinh dãy ngày bằng recursive CTE

Recursive CTE gồm hai phần:

- Anchor member tạo hàng đầu tiên.
- Recursive member đọc kết quả đã sinh và tạo hàng tiếp theo.

Hai phần được nối bằng UNION ALL. Điều kiện dừng trong recursive member bảo đảm quá trình sinh ngày kết thúc.

Ví dụ sinh các ngày từ 01 đến 07/01/2025:

    WITH RECURSIVE calendar_days (calendar_date) AS (
        SELECT CAST('2025-01-01' AS DATE)

        UNION ALL

        SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
        FROM calendar_days
        WHERE calendar_date < '2025-01-07'
    )
    SELECT calendar_date
    FROM calendar_days
    ORDER BY calendar_date;

Kết quả có bảy hàng liên tiếp:

| calendar_date |
|---|
| 2025-01-01 |
| 2025-01-02 |
| 2025-01-03 |
| 2025-01-04 |
| 2025-01-05 |
| 2025-01-06 |
| 2025-01-07 |

Anchor trả về ngày bắt đầu. Mỗi vòng lặp cộng một ngày. Khi ngày hiện tại bằng ngày kết thúc, điều kiện WHERE không còn đúng nên recursive member không sinh thêm hàng. Ngày kết thúc vẫn có mặt vì nó đã được tạo ở vòng lặp trước.

### 3.1. Dùng tham số cho khoảng ngày

Trong ứng dụng, ngày bắt đầu và kết thúc nên được bind bằng prepared statement hoặc được đưa vào một CTE tham số. Ví dụ dưới đây dùng CTE params để chỉ khai báo hai mốc một lần:

    WITH RECURSIVE
    params AS (
        SELECT
            CAST('2025-01-01' AS DATE) AS start_date,
            CAST('2025-01-07' AS DATE) AS end_date
    ),
    calendar_days (calendar_date) AS (
        SELECT p.start_date
        FROM params AS p
        WHERE p.start_date <= p.end_date

        UNION ALL

        SELECT DATE_ADD(c.calendar_date, INTERVAL 1 DAY)
        FROM calendar_days AS c
        CROSS JOIN params AS p
        WHERE c.calendar_date < p.end_date
    )
    SELECT calendar_date
    FROM calendar_days
    ORDER BY calendar_date;

Điều kiện p.start_date <= p.end_date được đặt trong anchor. Nếu khoảng không hợp lệ, CTE không tạo hàng nào thay vì trả về riêng ngày bắt đầu. Ứng dụng vẫn nên xác thực start_date và end_date trước khi gửi truy vấn để trả lỗi đầu vào rõ ràng.

Khi dùng prepared statement, thay hai literal trong CTE params bằng hai placeholder và bind kiểu DATE phù hợp:

    params AS (
        SELECT
            CAST(? AS DATE) AS start_date,
            CAST(? AS DATE) AS end_date
    )

Đừng nối chuỗi ngày do người dùng gửi trực tiếp vào câu SQL.

### 3.2. Khoảng ngày bao gồm hai đầu mút

Ví dụ trên dùng quy ước ngày bắt đầu và ngày kết thúc đều được đưa vào dãy. Nếu start_date và end_date cùng là một ngày, CTE trả về đúng một hàng. Nếu ngày kết thúc sau ngày bắt đầu n ngày, dãy có n + 1 hàng.

Nếu API dùng quy ước khoảng nửa mở [start, end), hãy thay điều kiện sinh ngày để không tạo ngày bằng end_date, hoặc chuyển hợp đồng đầu vào thành ngày kết thúc bao gồm trước khi gọi CTE. Điều quan trọng là phải thống nhất hợp đồng khoảng thời gian ở tầng API và SQL.

Với end_date là ngày kết thúc exclusive, điều kiện cần bảo đảm ngày kế tiếp vẫn nhỏ hơn end_date:

    WITH RECURSIVE
    params AS (
        SELECT
            CAST('2025-01-01' AS DATE) AS start_date,
            CAST('2025-01-07' AS DATE) AS end_date
    ),
    calendar_days (calendar_date) AS (
        SELECT p.start_date
        FROM params AS p
        WHERE p.start_date < p.end_date

        UNION ALL

        SELECT DATE_ADD(c.calendar_date, INTERVAL 1 DAY)
        FROM calendar_days AS c
        CROSS JOIN params AS p
        WHERE DATE_ADD(c.calendar_date, INTERVAL 1 DAY) < p.end_date
    )
    SELECT calendar_date
    FROM calendar_days
    ORDER BY calendar_date;

Với khoảng [2025-01-01, 2025-01-07), kết quả chỉ gồm ngày 01 đến hết ngày 06. Nếu hai mốc bằng nhau, dãy rỗng.

## 4. Bù ngày thiếu bằng LEFT JOIN

Sau khi có date spine, tổng hợp dữ liệu giao dịch theo ngày rồi LEFT JOIN vào lịch:

    WITH RECURSIVE
    params AS (
        SELECT
            CAST('2025-01-01' AS DATE) AS start_date,
            CAST('2025-01-07' AS DATE) AS end_date
    ),
    calendar_days (calendar_date) AS (
        SELECT p.start_date
        FROM params AS p
        WHERE p.start_date <= p.end_date

        UNION ALL

        SELECT DATE_ADD(c.calendar_date, INTERVAL 1 DAY)
        FROM calendar_days AS c
        CROSS JOIN params AS p
        WHERE c.calendar_date < p.end_date
    ),
    daily_totals AS (
        SELECT
            o.order_date,
            COUNT(*) AS order_count,
            SUM(o.amount) AS revenue,
            SUM(CASE WHEN o.order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_count
        FROM calendar_order_demo AS o
        JOIN params AS p
            ON o.order_date >= p.start_date
           AND o.order_date <= p.end_date
        GROUP BY o.order_date
    )
    SELECT
        c.calendar_date,
        COALESCE(d.order_count, 0) AS order_count,
        COALESCE(d.revenue, 0.00) AS revenue,
        COALESCE(d.paid_count, 0) AS paid_count
    FROM calendar_days AS c
    LEFT JOIN daily_totals AS d
        ON d.order_date = c.calendar_date
    ORDER BY c.calendar_date;

Kết quả có đủ bảy ngày:

| Ngày | Số đơn | Doanh thu | Đơn PAID |
|---|---:|---:|---:|
| 2025-01-01 | 1 | 120.00 | 1 |
| 2025-01-02 | 2 | 130.00 | 0 |
| 2025-01-03 | 0 | 0.00 | 0 |
| 2025-01-04 | 0 | 0.00 | 0 |
| 2025-01-05 | 2 | 350.00 | 2 |
| 2025-01-06 | 0 | 0.00 | 0 |
| 2025-01-07 | 1 | 40.00 | 0 |

CTE daily_totals chỉ có hàng cho ngày phát sinh giao dịch. LEFT JOIN giữ tất cả hàng từ calendar_days và gắn số liệu nếu tìm được ngày tương ứng. Với ngày không có giao dịch, các cột từ daily_totals là NULL; COALESCE chuyển chúng thành 0 theo định nghĩa báo cáo.

### 4.1. Vì sao phải dùng LEFT JOIN?

Nếu dùng INNER JOIN, chỉ các ngày có dữ liệu ở cả hai phía mới được giữ. Những ngày không có giao dịch sẽ biến mất, tức là không giải quyết được mục tiêu bù kỳ.

LEFT JOIN giữ mọi ngày từ bảng lịch. Hãy đặt bảng lịch ở phía trái:

    FROM calendar_days AS c
    LEFT JOIN daily_totals AS d
        ON d.order_date = c.calendar_date

### 4.2. COUNT(*) khác COUNT(fact_id) sau LEFT JOIN

Nếu nối trực tiếp lịch với bảng giao dịch, một ngày không có đơn vẫn tạo một hàng kết quả với các cột giao dịch là NULL. Vì vậy:

- COUNT(*) đếm hàng đã được mở rộng bởi LEFT JOIN và có thể trả 1 cho ngày trống.
- COUNT(o.order_id) chỉ đếm đơn thực sự vì order_id là NOT NULL.

Ví dụ:

    WITH RECURSIVE calendar_days (calendar_date) AS (
        SELECT CAST('2025-01-01' AS DATE)
        UNION ALL
        SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
        FROM calendar_days
        WHERE calendar_date < '2025-01-03'
    )
    SELECT
        c.calendar_date,
        COUNT(*) AS joined_rows,
        COUNT(o.order_id) AS actual_orders
    FROM calendar_days AS c
    LEFT JOIN calendar_order_demo AS o
        ON o.order_date = c.calendar_date
    GROUP BY c.calendar_date
    ORDER BY c.calendar_date;

Ngày không có đơn có joined_rows bằng 1 nhưng actual_orders bằng 0. Khi đếm bản ghi ở phía phải của outer join, hãy dùng khóa không null của bảng đó.

## 5. Tránh làm mất ngày trống bằng điều kiện WHERE

Một lỗi thường gặp là đặt điều kiện của bảng bên phải vào WHERE sau LEFT JOIN:

    WITH RECURSIVE calendar_days (calendar_date) AS (
        SELECT CAST('2025-01-01' AS DATE)
        UNION ALL
        SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
        FROM calendar_days
        WHERE calendar_date < '2025-01-07'
    )
    SELECT
        c.calendar_date,
        COUNT(o.order_id) AS paid_orders
    FROM calendar_days AS c
    LEFT JOIN calendar_order_demo AS o
        ON o.order_date = c.calendar_date
    WHERE o.order_status = 'PAID'
    GROUP BY c.calendar_date
    ORDER BY c.calendar_date;

Ở ngày không có đơn, o.order_status là NULL. Điều kiện o.order_status = 'PAID' không trả về TRUE nên hàng bị loại; kết quả không còn ngày trống. Về tác dụng, điều kiện này khiến truy vấn mất ý nghĩa giữ hàng của LEFT JOIN.

Nếu chỉ muốn đếm đơn PAID nhưng vẫn giữ mọi ngày, hãy đặt điều kiện trong hàm tổng hợp:

    COUNT(CASE WHEN o.order_status = 'PAID' THEN o.order_id END)

Hoặc đặt điều kiện trạng thái trong ON nếu toàn bộ cột giao dịch được nối chỉ cần các đơn PAID:

    LEFT JOIN calendar_order_demo AS o
        ON o.order_date = c.calendar_date
       AND o.order_status = 'PAID'

Hai cách có ý nghĩa khác nhau khi báo cáo nhiều chỉ tiêu trạng thái. Nếu cần đếm PAID, PENDING và CANCELLED đồng thời, giữ các hàng giao dịch trong JOIN rồi dùng từng CASE riêng.

## 6. Tổng hợp nhiều chỉ tiêu theo ngày

Có thể tính nhiều chỉ tiêu trong cùng CTE daily_totals:

    daily_totals AS (
        SELECT
            order_date,
            COUNT(*) AS all_orders,
            SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
            SUM(CASE WHEN order_status = 'PENDING' THEN 1 ELSE 0 END) AS pending_orders,
            SUM(CASE WHEN order_status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders,
            SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_revenue,
            AVG(CASE WHEN order_status = 'PAID' THEN amount END) AS average_paid_amount
        FROM calendar_order_demo
        WHERE order_date >= '2025-01-01'
          AND order_date <= '2025-01-07'
        GROUP BY order_date
    )

Sau đó LEFT JOIN CTE này với dãy ngày. Với các chỉ tiêu đếm và tổng có quy ước hiển thị 0, dùng COALESCE. Với average_paid_amount, nếu ngày không có đơn PAID thì giá trị tự nhiên là NULL vì không có mẫu để tính trung bình. Nếu giao diện cần hiển thị 0 thay cho NULL, hãy áp dụng COALESCE ở lớp báo cáo theo định nghĩa đã thống nhất.

Không nên mặc định mọi NULL đều phải đổi thành 0. Số giao dịch bằng 0 là một kết quả có nghĩa; trung bình khi không có quan sát thường là không xác định.

## 7. Nối trực tiếp với bảng giao dịch thay vì tổng hợp trước

Với bảng có cột order_date kiểu DATE, có thể nối trực tiếp từng ngày lịch với các đơn:

    WITH RECURSIVE calendar_days (calendar_date) AS (
        SELECT CAST('2025-01-01' AS DATE)
        UNION ALL
        SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
        FROM calendar_days
        WHERE calendar_date < '2025-01-07'
    )
    SELECT
        c.calendar_date,
        COUNT(o.order_id) AS order_count,
        COALESCE(
            SUM(CASE WHEN o.order_status = 'PAID' THEN o.amount ELSE 0 END),
            0.00
        ) AS paid_revenue
    FROM calendar_days AS c
    LEFT JOIN calendar_order_demo AS o
        ON o.order_date = c.calendar_date
    GROUP BY c.calendar_date
    ORDER BY c.calendar_date;

Với mỗi ngày, MySQL tìm các hàng có order_date bằng ngày lịch rồi tính tổng. Index trên order_date có thể hỗ trợ phép nối này.

Hai cách thường dùng:

| Cách làm | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Tổng hợp fact trước rồi LEFT JOIN | Nhiều chỉ tiêu, dữ liệu nguồn lớn, muốn mỗi ngày chỉ còn một hàng trước khi nối | CTE tổng hợp phải lọc đúng khoảng ngày |
| Nối date spine trực tiếp với fact rồi GROUP BY | Truy vấn đơn giản, điều kiện nối theo ngày rõ ràng | Mỗi kỳ có thể thực hiện range/lookup; kiểm tra kế hoạch và số hàng |

Không có một cách luôn nhanh hơn. Hãy dùng EXPLAIN hoặc EXPLAIN ANALYZE trên dữ liệu có quy mô gần thực tế.

## 8. Sinh dãy tháng và bù tháng thiếu

Sinh tháng tương tự sinh ngày, nhưng bước đệ quy cộng một tháng. Nên chuẩn hóa mọi giá trị về ngày đầu tháng để tránh quy tắc cộng tháng từ ngày 29, 30 hoặc 31 tạo kết quả khó đoán.

Ví dụ tạo dãy tháng từ tháng 01 đến tháng 04/2025:

    WITH RECURSIVE months (month_start) AS (
        SELECT CAST('2025-01-01' AS DATE)

        UNION ALL

        SELECT DATE_ADD(month_start, INTERVAL 1 MONTH)
        FROM months
        WHERE month_start < '2025-04-01'
    )
    SELECT month_start
    FROM months
    ORDER BY month_start;

Kết quả là ngày đầu của từng tháng: 01/01, 01/02, 01/03 và 01/04. Các mốc này là khóa đại diện cho kỳ tháng trong báo cáo.

### 8.1. Tổng hợp theo tháng trong khoảng ngày đầu vào

Ví dụ sau sinh đủ các tháng từ tháng chứa start_date đến tháng chứa end_date. Dữ liệu giao dịch chỉ được tính trong khoảng ngày đầu vào, vì vậy tháng đầu và tháng cuối có thể là kỳ một phần:

    WITH RECURSIVE
    params AS (
        SELECT
            CAST('2025-01-15' AS DATE) AS start_date,
            CAST('2025-04-10' AS DATE) AS end_date
    ),
    month_limits AS (
        SELECT
            DATE_SUB(start_date, INTERVAL DAYOFMONTH(start_date) - 1 DAY) AS first_month,
            DATE_SUB(end_date, INTERVAL DAYOFMONTH(end_date) - 1 DAY) AS last_month
        FROM params
        WHERE start_date <= end_date
    ),
    month_spine (month_start) AS (
        SELECT first_month
        FROM month_limits

        UNION ALL

        SELECT DATE_ADD(m.month_start, INTERVAL 1 MONTH)
        FROM month_spine AS m
        CROSS JOIN month_limits AS l
        WHERE m.month_start < l.last_month
    ),
    monthly_totals AS (
        SELECT
            DATE_SUB(o.order_date, INTERVAL DAYOFMONTH(o.order_date) - 1 DAY) AS month_start,
            COUNT(*) AS order_count,
            SUM(o.amount) AS revenue
        FROM calendar_order_demo AS o
        JOIN params AS p
            ON o.order_date >= p.start_date
           AND o.order_date <= p.end_date
        GROUP BY DATE_SUB(o.order_date, INTERVAL DAYOFMONTH(o.order_date) - 1 DAY)
    )
    SELECT
        m.month_start,
        COALESCE(t.order_count, 0) AS order_count,
        COALESCE(t.revenue, 0.00) AS revenue
    FROM month_spine AS m
    LEFT JOIN monthly_totals AS t
        ON t.month_start = m.month_start
    ORDER BY m.month_start;

Ở đây tháng đầu là tháng 01/2025 nhưng chỉ tính từ ngày 15; tháng cuối là tháng 04/2025 nhưng chỉ tính đến ngày 10. Các tháng 02 và 03 được tính trọn tháng. Dãy tháng vẫn xuất hiện kể cả khi một tháng không có giao dịch.

Nếu báo cáo cần toàn bộ tháng trọn vẹn, hãy đặt start_date là ngày đầu tháng và end_date là ngày cuối tháng hoặc định nghĩa end_month riêng. Đừng vô tình trộn báo cáo tháng trọn vẹn với báo cáo theo một khoảng ngày tùy ý.

### 8.2. Tính nhãn tháng để hiển thị

Nên giữ month_start dưới kiểu DATE để join và sắp xếp. Khi cần nhãn hiển thị, có thể định dạng ở select list:

    SELECT
        DATE_FORMAT(month_start, '%Y-%m') AS month_label
    FROM month_spine
    ORDER BY month_start;

Không dùng chuỗi nhãn như '2025-1', '2025-10' làm khóa sắp xếp vì thứ tự từ điển có thể khác thứ tự thời gian nếu định dạng không cố định. Dùng DATE hoặc ngày đầu tháng để sắp xếp, chỉ format ở bước trình bày.

## 9. Làm việc với DATETIME: dùng khoảng nửa mở

Để chạy các ví dụ DATETIME trong phần này, tạo một bảng riêng có index trên cột thời điểm:

    CREATE TABLE calendar_order_datetime_demo (
        order_id BIGINT UNSIGNED NOT NULL,
        created_at DATETIME(6) NOT NULL,
        amount DECIMAL(12,2) NOT NULL,
        PRIMARY KEY (order_id),
        KEY idx_calendar_order_datetime_created (created_at)
    ) ENGINE = InnoDB;

    INSERT INTO calendar_order_datetime_demo
        (order_id, created_at, amount)
    VALUES
        (201, '2025-01-01 00:00:00.000001', 120.00),
        (202, '2025-01-02 10:15:30.123456',  80.00),
        (203, '2025-01-05 23:59:59.999999', 200.00),
        (204, '2025-01-07 12:00:00.500000',  40.00);

    SELECT order_id, created_at, amount
    FROM calendar_order_datetime_demo
    ORDER BY created_at, order_id;

Nếu bảng lưu thời điểm bằng DATETIME(6), không nên nối bằng cách chuyển cột thành DATE trong điều kiện:

    ON DATE(o.created_at) = c.calendar_date

Biểu thức hàm trên cột có thể khiến MySQL không dùng index B-tree trên created_at để định vị trực tiếp vùng thời gian của ngày. Thay vào đó, so sánh cột với hai mốc:

    ON o.created_at >= c.calendar_date
   AND o.created_at < DATE_ADD(c.calendar_date, INTERVAL 1 DAY)

Điều kiện này lấy mọi thời điểm từ nửa đêm ngày hiện tại đến trước nửa đêm ngày kế tiếp. Nó không phụ thuộc cột có FSP 0, 3 hay 6 và giữ cột created_at nguyên bản ở phía trái của phép so sánh.

Ví dụ tổng hợp fact theo ngày trước khi nối:

    WITH RECURSIVE
    params AS (
        SELECT
            CAST('2025-01-01' AS DATE) AS start_date,
            CAST('2025-01-07' AS DATE) AS end_date
    ),
    calendar_days (calendar_date) AS (
        SELECT start_date FROM params WHERE start_date <= end_date
        UNION ALL
        SELECT DATE_ADD(c.calendar_date, INTERVAL 1 DAY)
        FROM calendar_days AS c
        CROSS JOIN params AS p
        WHERE c.calendar_date < p.end_date
    ),
    daily_totals AS (
        SELECT
            DATE(o.created_at) AS calendar_date,
            COUNT(*) AS order_count,
            SUM(o.amount) AS revenue
        FROM calendar_order_datetime_demo AS o
        JOIN params AS p
            ON o.created_at >= p.start_date
           AND o.created_at < DATE_ADD(p.end_date, INTERVAL 1 DAY)
        GROUP BY DATE(o.created_at)
    )
    SELECT
        c.calendar_date,
        COALESCE(d.order_count, 0) AS order_count,
        COALESCE(d.revenue, 0.00) AS revenue
    FROM calendar_days AS c
    LEFT JOIN daily_totals AS d
        ON d.calendar_date = c.calendar_date
    ORDER BY c.calendar_date;

Ở đây DATE(created_at) chỉ xuất hiện trong select list và GROUP BY để tạo khóa ngày của tập đã lọc. Điều kiện WHERE/join với params vẫn là range trên created_at:

    created_at >= start_date
    AND created_at < end_date + INTERVAL 1 DAY

Điều này khác với việc đặt DATE(created_at) trong điều kiện lọc. Hãy xác minh kế hoạch trên schema thực tế bằng EXPLAIN.

### 9.1. Nối trực tiếp theo khoảng thời gian từng ngày

Nếu không cần CTE tổng hợp trước, có thể dùng:

    LEFT JOIN calendar_order_datetime_demo AS o
        ON o.created_at >= c.calendar_date
       AND o.created_at < DATE_ADD(c.calendar_date, INTERVAL 1 DAY)

Index trên created_at có thể hỗ trợ range lookup cho từng ngày. Tuy nhiên, hiệu quả còn phụ thuộc số ngày, số giao dịch mỗi ngày và kế hoạch join. Với dãy dài hoặc nhiều chỉ tiêu, tổng hợp fact trước có thể dễ kiểm soát hơn.

## 10. Quy ước khoảng thời gian và ranh giới ngày

Với cột DATE và API nhận ngày bắt đầu/kết thúc bao gồm hai đầu, điều kiện là:

    order_date >= start_date
    AND order_date <= end_date

Với cột DATETIME/TIMESTAMP, nên biểu diễn khoảng ngày bằng nửa mở:

    created_at >= start_datetime
    AND created_at < next_day_start

Ví dụ lấy ngày 10/01:

    created_at >= '2025-01-10 00:00:00'
    AND created_at <  '2025-01-11 00:00:00'

Không dùng mốc cuối cố định như 23:59:59 hoặc 23:59:59.999999. Những giá trị này phụ thuộc độ chính xác phần giây và có thể bỏ sót dữ liệu nếu kiểu cột hoặc nguồn thời gian có độ chính xác khác.

Với khoảng nhiều ngày từ start_date đến end_date bao gồm cả ngày cuối, mốc kết thúc exclusive là:

    DATE_ADD(end_date, INTERVAL 1 DAY)

Hãy xác định rõ API dùng end inclusive hay end exclusive. Không cộng thêm một ngày nếu đầu vào đã là mốc kết thúc exclusive.

## 11. Múi giờ và ngày có DST

Nếu cột lưu DATETIME theo quy ước UTC, MySQL không tự biết đó là UTC; ứng dụng phải bảo đảm giá trị được ghi và đọc theo cùng hợp đồng. Nếu cột là TIMESTAMP, MySQL chuyển đổi giữa UTC và múi giờ session khi ghi/đọc.

Khi báo cáo theo ngày địa phương, một ngày lịch ở vùng có Daylight Saving Time có thể dài 23 hoặc 25 giờ. Vì vậy, không phải lúc nào cũng có thể lấy start_utc cộng đúng 24 giờ để tạo end_utc.

Quy trình an toàn cho báo cáo theo ngày địa phương:

1. Xác định timezone IANA của báo cáo, ví dụ America/New_York hoặc Asia/Ho_Chi_Minh.
2. Tính nửa đêm địa phương của ngày bắt đầu và nửa đêm địa phương của ngày kế tiếp bằng timezone database có quy tắc DST cập nhật.
3. Chuyển hai mốc đó sang UTC.
4. Dùng khoảng [start_utc, end_utc) để lọc cột lưu UTC.
5. Với mỗi ngày trong date spine địa phương, tính riêng hai biên UTC của ngày đó nếu vùng có DST.

Không nên viết DATE(CONVERT_TZ(created_at, '+00:00', 'America/New_York')) trong điều kiện lọc trên cột lớn nếu muốn tận dụng index trực tiếp. Hãy tính biên UTC trước rồi so sánh cột:

    created_at >= start_utc
    AND created_at < end_utc

Với báo cáo theo từng ngày địa phương ở vùng DST, một bảng lịch có các cột local_date, utc_start và utc_end là cách mô hình hóa rõ ràng. Mỗi ngày có thể có khoảng UTC dài 23, 24 hoặc 25 giờ. Bảng lịch cũng giúp dùng cùng quy tắc timezone cho nhiều báo cáo.

## 12. Giới hạn đệ quy và điều kiện dừng

MySQL giới hạn số vòng lặp recursive CTE bằng biến hệ thống cte_max_recursion_depth. Giá trị mặc định trong MySQL 8.0 là 1000. Dãy dài hơn giới hạn có thể kết thúc bằng lỗi vượt quá độ sâu đệ quy.

Kiểm tra giá trị hiện tại:

    SHOW VARIABLES LIKE 'cte_max_recursion_depth';

Nếu một tác vụ hợp lệ cần sinh nhiều kỳ hơn, có thể điều chỉnh giới hạn cho session:

    SET SESSION cte_max_recursion_depth = 2000;

Chỉ tăng giới hạn khi đã kiểm soát khoảng đầu vào và hiểu chi phí truy vấn. Không đặt giới hạn rất lớn để che một điều kiện dừng sai; CTE thiếu điều kiện kết thúc có thể tiêu tốn CPU và bộ nhớ cho đến khi chạm giới hạn hoặc timeout.

Các kiểm tra cần có:

- start_date không lớn hơn end_date.
- Khoảng ngày có giới hạn tối đa theo nhu cầu báo cáo.
- Recursive member luôn tiến về điều kiện dừng, ví dụ cộng đúng một ngày hoặc một tháng.
- CTE không vô tình dùng bước cộng bằng 0 hoặc bước lùi khi điều kiện dừng lại yêu cầu tiến.
- Người gọi không thể yêu cầu khoảng hàng chục năm nếu API chỉ phục vụ báo cáo theo tuần.

### 12.1. Đếm trước số kỳ cần sinh

Với dãy ngày bao gồm hai đầu, số ngày dự kiến là:

    DATEDIFF(end_date, start_date) + 1

Có thể dùng phép tính này để xác thực giới hạn trước khi chạy recursive CTE. Ví dụ, API có thể chỉ cho phép báo cáo tối đa 366 ngày trong một request.

### 12.2. Khi nào nên dùng bảng lịch?

Recursive CTE phù hợp cho dãy ngắn hoặc truy vấn ad hoc. Nếu hệ thống thường xuyên cần ngày, tuần, tháng, quý, ngày lễ, ngày làm việc, kỳ tài chính hoặc nhiều múi giờ, một bảng calendar dimension thường phù hợp hơn.

Bảng lịch có thể lưu:

- calendar_date và các khóa ngày/tháng/quý/năm.
- day_of_week, week_of_year và cờ cuối tuần.
- is_business_day, holiday_name và lịch nghỉ theo khu vực.
- local_timezone, utc_start và utc_end cho báo cáo theo vùng thời gian.
- Fiscal year, fiscal period và các thuộc tính lịch nghiệp vụ.

Một bảng lịch được tạo và kiểm soát trước giúp truy vấn đơn giản, tái sử dụng tốt, tránh sinh lại dãy mỗi lần và hỗ trợ metadata lịch mà phép cộng ngày đơn thuần không thể biết.

## 13. Các trường hợp biên cần kiểm thử

| Trường hợp | Kết quả cần xác nhận |
|---|---|
| start_date = end_date | Chỉ sinh đúng một ngày |
| start_date > end_date | Không sinh ngày hoặc trả lỗi đầu vào theo hợp đồng API |
| Ngày không có giao dịch | Vẫn có hàng, chỉ tiêu đếm/tổng hiển thị 0 theo quy ước |
| Ngày có giao dịch nhưng không có PAID | all_orders > 0, paid_orders = 0 |
| Khoảng chứa ngày 29/02 năm nhuận | Dãy ngày phải có ngày 29/02 |
| Khoảng qua cuối tháng | Ngày tiếp theo phải sang tháng mới chính xác |
| Khoảng qua cuối năm | Dãy phải chuyển năm chính xác |
| Khoảng dài hơn cte_max_recursion_depth | Trả lỗi giới hạn hoặc dùng bảng lịch/chiến lược khác |
| Cột DATETIME có microsecond gần nửa đêm | Điều kiện nửa mở phải lấy đúng dữ liệu trước ngày kế tiếp |
| Ngày địa phương có DST | Biên UTC phải được tính theo timezone database, không giả định 24 giờ |

Ví dụ kiểm tra năm nhuận:

    WITH RECURSIVE calendar_days (calendar_date) AS (
        SELECT CAST('2024-02-27' AS DATE)
        UNION ALL
        SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
        FROM calendar_days
        WHERE calendar_date < '2024-03-02'
    )
    SELECT calendar_date
    FROM calendar_days
    ORDER BY calendar_date;

Kết quả phải có 27/02, 28/02, 29/02, 01/03 và 02/03.

## 14. Những lỗi thường gặp

- Dùng GROUP BY trên bảng giao dịch rồi kỳ vọng MySQL tự tạo các ngày không có hàng.
- Dùng INNER JOIN thay vì LEFT JOIN khi muốn giữ mọi kỳ trong date spine.
- Đặt điều kiện bảng fact trong WHERE sau LEFT JOIN và vô tình loại các kỳ không có dữ liệu.
- Dùng COUNT(*) để đếm hàng fact sau outer join; cần COUNT(fact_primary_key).
- Dùng COALESCE cho mọi chỉ tiêu mà không phân biệt tổng bằng 0 và trung bình không xác định.
- Thiếu điều kiện dừng hoặc dùng bước đệ quy không tiến về mốc kết thúc.
- Không kiểm tra start_date > end_date, khiến anchor có thể trả về một ngày ngoài ý định.
- Sinh khoảng quá dài và vượt cte_max_recursion_depth.
- Tăng recursion depth rất lớn mà không giới hạn đầu vào.
- Cộng một tháng trực tiếp từ ngày 29, 30 hoặc 31 mà không chuẩn hóa về ngày đầu tháng.
- Dùng DATE(created_at) trong điều kiện lọc thay vì range predicate trên created_at.
- Dùng 23:59:59 hoặc 23:59:59.999999 làm mốc cuối ngày.
- Giả định một ngày ở mọi múi giờ luôn dài 24 giờ.
- Dùng recursive CTE cho lịch sử nhiều năm và nhiều thuộc tính lịch dù một calendar dimension sẽ dễ quản trị hơn.

## 15. Checklist sinh lịch và bù kỳ

- Đã xác định đơn vị kỳ: ngày, tuần, tháng hay kỳ nghiệp vụ.
- Đã xác định rõ khoảng đầu/cuối inclusive hay exclusive.
- Đã xác thực start_date và end_date trước khi sinh dãy.
- Đã có anchor member và recursive member với bước tiến rõ ràng.
- Đã có điều kiện dừng bảo đảm recursive CTE kết thúc.
- Đã đánh giá số kỳ cần sinh so với cte_max_recursion_depth.
- Đã dùng LEFT JOIN để giữ các kỳ không có dữ liệu.
- Đã đặt điều kiện fact trong CTE tổng hợp, ON hoặc CASE theo đúng ý nghĩa, tránh làm mất hàng bên trái.
- Đã dùng COUNT(fact_primary_key) để đếm bản ghi thực tế sau outer join.
- Đã phân biệt 0 với NULL cho từng chỉ tiêu.
- Đã lọc cột DATETIME/TIMESTAMP bằng khoảng nửa mở và giữ cột nguyên bản để tận dụng index.
- Đã tính biên ngày theo timezone nghiệp vụ và DST khi cần.
- Đã cân nhắc calendar dimension cho lịch dài, dùng lặp lại hoặc có ngày làm việc/ngày lễ.
- Đã kiểm thử ngày đầu, ngày cuối, ngày trống, năm nhuận, cuối tháng và khoảng vượt giới hạn.

Recursive CTE cho phép sinh dãy ngày hoặc tháng ngay trong truy vấn. Khi ghép date spine với dữ liệu tổng hợp bằng LEFT JOIN, báo cáo có thể hiển thị đầy đủ kỳ lịch và bù những ngày/tháng không phát sinh giao dịch. Để kết quả đúng và hiệu quả, hãy đặt điều kiện dừng rõ ràng, giới hạn độ dài dãy, xử lý NULL theo ý nghĩa từng chỉ tiêu, lọc DATETIME bằng khoảng nửa mở và tính biên theo múi giờ thực tế. Với báo cáo lặp lại hoặc lịch nghiệp vụ phức tạp, hãy cân nhắc xây dựng calendar dimension dùng chung.
