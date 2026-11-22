# CASE, IF và lựa chọn nhánh biểu thức

Trong truy vấn MySQL, đôi khi giá trị cần trả về phụ thuộc vào điều kiện của từng hàng. Ví dụ, hiển thị nhãn “Đã thanh toán” khi đơn hàng có trạng thái PAID, phân nhóm đơn hàng theo tổng tiền, hoặc tính một khoản phí khác nhau theo loại khách hàng. Biểu thức lựa chọn nhánh giúp thực hiện việc này ngay trong SQL.

MySQL cung cấp hai cách thường dùng:

- CASE là biểu thức có thể chọn giữa nhiều nhánh điều kiện, hỗ trợ cả dạng so sánh một biểu thức với nhiều giá trị và dạng kiểm tra nhiều điều kiện độc lập.
- IF() là hàm MySQL chọn một trong hai kết quả dựa trên một biểu thức điều kiện.

Cả hai trả về một giá trị, vì vậy có thể dùng trong SELECT, ORDER BY, GROUP BY, HAVING, UPDATE và nhiều vị trí chấp nhận biểu thức SQL. Hiểu cách chúng xử lý NULL, thứ tự nhánh và kiểu dữ liệu kết quả giúp truy vấn dễ đọc, đúng nghiệp vụ và ổn định khi tích hợp ứng dụng.

## 1. Chuẩn bị dữ liệu thực hành

Dùng bảng đơn hàng sau:

~~~sql
CREATE TABLE orders_case_demo (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    discount_rate DECIMAL(5, 4) NULL,
    shipped_at DATETIME NULL,
    KEY idx_status (status),
    KEY idx_customer_type (customer_type)
) ENGINE = InnoDB;

INSERT INTO orders_case_demo
    (order_id, customer_id, customer_type, status,
     total_amount, discount_rate, shipped_at)
VALUES
    (2001, 10, 'REGULAR', 'NEW',       120.00, NULL,    NULL),
    (2002, 11, 'VIP',     'PAID',      850.00, 0.0500, NULL),
    (2003, 10, 'REGULAR', 'SHIPPED',   450.00, 0.0000, '2025-03-12 14:20:00'),
    (2004, 12, 'VIP',     'CANCELLED',  75.00, NULL,    NULL),
    (2005, 13, 'BUSINESS','PAID',     1200.00, 0.1000, NULL),
    (2006, 14, 'REGULAR', 'NEW',       300.00, NULL,    NULL),
    (2007, 15, 'BUSINESS','SHIPPED',   620.00, 0.0800, '2025-04-02 11:10:00');
~~~

Các ví dụ sử dụng dữ liệu này để minh họa lựa chọn nhánh. Trong hệ thống thật, hãy thay tên bảng, cột và điều kiện theo schema và quy tắc nghiệp vụ.

## 2. CASE là biểu thức lựa chọn nhánh

CASE đánh giá các nhánh theo thứ tự từ trên xuống. Khi tìm thấy nhánh WHEN có điều kiện đúng, biểu thức trả về kết quả THEN tương ứng và không xét các nhánh WHEN phía sau.

Có hai dạng chính:

1. Simple CASE: so sánh một biểu thức với từng giá trị WHEN.
2. Searched CASE: đánh giá các điều kiện độc lập trong từng WHEN.

Cú pháp tổng quát:

~~~sql
CASE expression
    WHEN value1 THEN result1
    WHEN value2 THEN result2
    ELSE default_result
END
~~~

Dạng tìm kiếm:

~~~sql
CASE
    WHEN condition1 THEN result1
    WHEN condition2 THEN result2
    ELSE default_result
END
~~~

ELSE là tùy chọn. Nếu không có nhánh nào khớp và không khai báo ELSE, kết quả CASE là NULL.

## 3. Simple CASE: so sánh một biểu thức với nhiều giá trị

Simple CASE phù hợp khi một cột hoặc biểu thức được so sánh với nhiều giá trị cụ thể.

Ví dụ chuyển mã trạng thái thành nhãn tiếng Việt:

~~~sql
SELECT
    order_id,
    status,
    CASE status
        WHEN 'NEW' THEN 'Mới tạo'
        WHEN 'PAID' THEN 'Đã thanh toán'
        WHEN 'SHIPPED' THEN 'Đang giao'
        WHEN 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Không xác định'
    END AS status_label
FROM orders_case_demo
ORDER BY order_id;
~~~

Biểu thức CASE xét status lần lượt:

- Nếu status bằng NEW, trả về Mới tạo.
- Nếu bằng PAID, trả về Đã thanh toán.
- Nếu bằng SHIPPED, trả về Đang giao.
- Nếu bằng CANCELLED, trả về Đã hủy.
- Nếu không khớp các giá trị trên, trả về Không xác định.

Dạng này gọn khi tất cả nhánh đều kiểm tra cùng một biểu thức.

### 3.1. So sánh theo collation

Simple CASE dùng quy tắc so sánh của biểu thức và các giá trị WHEN. Với chuỗi, collation có thể làm cho các cách viết hoa/thường hoặc dấu khác nhau được xem là bằng nhau.

Ví dụ nếu cột status dùng collation không phân biệt hoa/thường, giá trị 'paid' có thể khớp WHEN 'PAID'. Nếu nghiệp vụ yêu cầu so sánh chính xác, hãy xác định collation của cột hoặc chỉ định collation phù hợp cho biểu thức.

Không giả định Simple CASE luôn so sánh byte chính xác.

### 3.2. Không dùng WHEN NULL để kiểm tra NULL

Một lỗi thường gặp:

~~~sql
SELECT
    CASE discount_rate
        WHEN NULL THEN 'Chưa áp dụng'
        ELSE 'Có giá trị'
    END AS discount_status
FROM orders_case_demo;
~~~

Nhánh WHEN NULL không khớp với giá trị NULL vì phép so sánh bằng NULL cho kết quả UNKNOWN. Simple CASE về bản chất so sánh biểu thức với từng giá trị WHEN.

Nếu cần kiểm tra NULL, dùng searched CASE:

~~~sql
SELECT
    CASE
        WHEN discount_rate IS NULL THEN 'Chưa áp dụng'
        ELSE 'Đã có tỷ lệ'
    END AS discount_status
FROM orders_case_demo;
~~~

Đây là quy tắc quan trọng khi dữ liệu có thuộc tính tùy chọn.

## 4. Searched CASE: kiểm tra nhiều điều kiện

Searched CASE phù hợp khi mỗi nhánh có điều kiện khác nhau, gồm phép so sánh, khoảng giá trị, IN, LIKE hoặc kiểm tra NULL.

Ví dụ phân nhóm đơn hàng theo giá trị:

~~~sql
SELECT
    order_id,
    total_amount,
    CASE
        WHEN total_amount >= 1000 THEN 'Giá trị cao'
        WHEN total_amount >= 500 THEN 'Giá trị trung bình'
        WHEN total_amount >= 200 THEN 'Giá trị thấp'
        ELSE 'Giá trị rất thấp'
    END AS amount_group
FROM orders_case_demo
ORDER BY total_amount DESC;
~~~

### 4.1. Thứ tự WHEN ảnh hưởng kết quả

CASE trả về kết quả của nhánh WHEN đầu tiên đúng. Vì vậy, nếu các điều kiện có thể chồng lấn, phải đặt điều kiện cụ thể hoặc ngưỡng cao hơn trước.

Ví dụ sai:

~~~sql
CASE
    WHEN total_amount >= 200 THEN 'Từ 200 trở lên'
    WHEN total_amount >= 1000 THEN 'Từ 1000 trở lên'
    ELSE 'Dưới 200'
END
~~~

Đơn hàng 1200 thỏa điều kiện đầu tiên nên không bao giờ tới nhánh thứ hai. Kết quả bị phân loại sai.

Cách đúng:

~~~sql
CASE
    WHEN total_amount >= 1000 THEN 'Từ 1000 trở lên'
    WHEN total_amount >= 200 THEN 'Từ 200 đến dưới 1000'
    ELSE 'Dưới 200'
END
~~~

Hãy đọc CASE từ trên xuống và tự hỏi một hàng có thể thỏa nhiều điều kiện hay không.

### 4.2. Kết hợp nhiều toán tử trong WHEN

Có thể dùng IN, BETWEEN và LIKE trong điều kiện:

~~~sql
SELECT
    order_id,
    status,
    total_amount,
    CASE
        WHEN status IN ('CANCELLED') THEN 'Không tính doanh thu'
        WHEN status IN ('PAID', 'SHIPPED')
             AND total_amount BETWEEN 500 AND 1000
            THEN 'Đơn có giá trị mục tiêu'
        WHEN status = 'NEW' THEN 'Đang chờ xử lý'
        ELSE 'Cần xem xét'
    END AS order_category
FROM orders_case_demo;
~~~

Các điều kiện trong WHEN phải tạo ra giá trị logic. Chỉ kết quả TRUE mới chọn nhánh; FALSE và UNKNOWN không chọn nhánh đó.

### 4.3. CASE không thay thế WHERE

CASE thường được dùng để tạo giá trị đầu ra. Nếu mục tiêu là loại hàng khỏi kết quả, hãy dùng WHERE.

Ví dụ:

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN 'Đã thanh toán'
        ELSE 'Khác'
    END AS status_label
FROM orders_case_demo;
~~~

Truy vấn vẫn trả mọi hàng, chỉ thay đổi nhãn hiển thị.

Nếu chỉ muốn lấy đơn đã thanh toán, viết:

~~~sql
SELECT order_id, status, total_amount
FROM orders_case_demo
WHERE status = 'PAID';
~~~

Không nên dùng CASE để che giấu một điều kiện lọc đơn giản. Viết trực tiếp predicate thường rõ hơn và giúp optimizer dễ nhận diện điều kiện truy cập index.

## 5. NULL và logic ba giá trị trong CASE

Trong SQL, biểu thức điều kiện có thể trả TRUE, FALSE hoặc UNKNOWN. CASE chỉ chọn nhánh WHEN khi điều kiện là TRUE.

Ví dụ:

~~~sql
SELECT
    CASE
        WHEN NULL = 1 THEN 'TRUE'
        WHEN NULL <> 1 THEN 'FALSE'
        ELSE 'UNKNOWN hoặc không khớp'
    END AS null_branch;
~~~

Hai phép so sánh với NULL đều trả UNKNOWN, nên CASE đi tới ELSE.

### 5.1. Kiểm tra NULL đúng cách

~~~sql
SELECT
    order_id,
    CASE
        WHEN shipped_at IS NULL THEN 'Chưa giao'
        WHEN shipped_at IS NOT NULL THEN 'Đã có thời điểm giao'
    END AS shipping_state
FROM orders_case_demo;
~~~

Dùng IS NULL và IS NOT NULL để kiểm tra sự hiện diện của giá trị.

### 5.2. Không có ELSE thì kết quả là NULL

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN 'Đã thanh toán'
        WHEN status = 'SHIPPED' THEN 'Đang giao'
    END AS payment_or_shipping_label
FROM orders_case_demo;
~~~

Các hàng NEW và CANCELLED không khớp nhánh nào nên nhận NULL. Nếu API cần một nhãn mặc định, hãy thêm ELSE:

~~~sql
CASE
    WHEN status = 'PAID' THEN 'Đã thanh toán'
    WHEN status = 'SHIPPED' THEN 'Đang giao'
    ELSE 'Chưa hoàn tất'
END
~~~

Không nên dựa vào NULL mặc định nếu nghiệp vụ muốn hiển thị một trạng thái rõ ràng.

### 5.3. CASE với giá trị có thể NULL trong phép so sánh

Giả sử discount_rate có thể NULL. Biểu thức:

~~~sql
CASE
    WHEN discount_rate = 0 THEN 'Không giảm giá'
    WHEN discount_rate > 0 THEN 'Có giảm giá'
    ELSE 'Chưa xác định'
END
~~~

sẽ đưa hàng có discount_rate NULL vào ELSE vì các phép so sánh trả UNKNOWN. Nếu muốn phân biệt rõ dữ liệu chưa xác định với trường hợp khác, viết nhánh IS NULL trước:

~~~sql
CASE
    WHEN discount_rate IS NULL THEN 'Chưa xác định'
    WHEN discount_rate = 0 THEN 'Không giảm giá'
    WHEN discount_rate > 0 THEN 'Có giảm giá'
    ELSE 'Giá trị không hợp lệ'
END
~~~

### 5.4. NULL trong Simple CASE và Searched CASE

So sánh hai dạng:

~~~sql
-- Không bắt được NULL:
CASE discount_rate
    WHEN NULL THEN 'Chưa có'
    ELSE 'Đã có'
END

-- Bắt được NULL:
CASE
    WHEN discount_rate IS NULL THEN 'Chưa có'
    ELSE 'Đã có'
END
~~~

Khi cần xử lý NULL, searched CASE gần như luôn là lựa chọn rõ ràng hơn.

## 6. IF(): lựa chọn giữa hai nhánh

IF() là hàm điều kiện riêng của MySQL:

~~~sql
IF(condition, value_if_true, value_if_false)
~~~

Nếu condition khác 0 và không NULL, IF() trả về đối số thứ hai. Nếu condition bằng 0 hoặc NULL, IF() trả về đối số thứ ba.

Ví dụ:

~~~sql
SELECT
    order_id,
    total_amount,
    IF(total_amount >= 500, 'Đơn lớn', 'Đơn thường') AS amount_label
FROM orders_case_demo;
~~~

IF() phù hợp với điều kiện nhị phân đơn giản, khi chỉ có hai kết quả.

### 6.1. IF() xử lý NULL như thế nào?

~~~sql
SELECT
    IF(1, 'Đúng', 'Sai') AS true_case,
    IF(0, 'Đúng', 'Sai') AS false_case,
    IF(NULL, 'Đúng', 'Sai') AS null_case,
    IF(-1, 'Đúng', 'Sai') AS negative_case;
~~~

Kết quả:

- 1 được xem là TRUE.
- 0 được xem là FALSE.
- NULL đi vào nhánh thứ ba.
- Số âm khác 0 được xem là TRUE.

Điều kiện của IF() được đánh giá theo quy tắc giá trị số/logic của MySQL. Không truyền chuỗi tùy ý như 'yes' hoặc 'no' để biểu thị điều kiện. Hãy dùng predicate rõ ràng như status = 'PAID', quantity > 0 hoặc flag = 1.

### 6.2. IF() với kiểm tra NULL

~~~sql
SELECT
    order_id,
    IF(shipped_at IS NULL, 'Chưa giao', 'Đã giao') AS shipping_state
FROM orders_case_demo;
~~~

Ở đây điều kiện IS NULL trả TRUE hoặc FALSE rõ ràng, nên IF() phù hợp.

### 6.3. IF() với phép tính

Ví dụ tính số tiền sau giảm giá:

~~~sql
SELECT
    order_id,
    total_amount,
    IF(
        discount_rate IS NULL,
        total_amount,
        total_amount * (1 - discount_rate)
    ) AS net_amount
FROM orders_case_demo;
~~~

Nếu chưa có discount_rate, giữ nguyên tổng tiền. Nếu có tỷ lệ giảm, tính số tiền sau giảm.

Khi nghiệp vụ có nhiều mức giảm hoặc điều kiện phức tạp, CASE thường dễ đọc và mở rộng hơn.

## 7. CASE và IF(): chọn cách nào?

| Tiêu chí | CASE | IF() |
|---|---|---|
| Số nhánh | Nhiều nhánh | Hai nhánh |
| Điều kiện | Simple CASE hoặc nhiều predicate | Một biểu thức điều kiện |
| Tính chuẩn SQL | CASE là biểu thức chuẩn SQL | IF() là hàm riêng của MySQL |
| Đọc logic nhiều mức | Thường rõ ràng hơn | Dễ lồng nhiều IF khó đọc |
| Xử lý NULL | WHEN chỉ khớp khi điều kiện TRUE | Condition NULL đi vào nhánh false |
| Dùng trong SELECT/UPDATE/ORDER BY | Có | Có |
| Mở rộng thêm nhánh | Dễ thêm WHEN | Phải lồng IF hoặc đổi sang CASE |

Quy tắc thực tế:

- Dùng IF() cho lựa chọn đúng/sai đơn giản.
- Dùng CASE khi có từ ba nhánh trở lên hoặc điều kiện cần biểu đạt rõ.
- Dùng CASE searched khi cần kiểm tra NULL, khoảng số, nhiều cột hoặc nhiều predicate.
- Dùng Simple CASE khi so sánh một cột với nhiều giá trị cụ thể.

CASE thường là lựa chọn tốt hơn khi cần tính di động giữa các hệ quản trị cơ sở dữ liệu.

## 8. CASE và IF() trong SELECT

Có thể tạo nhãn, nhóm hoặc giá trị dẫn xuất trong danh sách SELECT:

~~~sql
SELECT
    order_id,
    customer_type,
    total_amount,
    CASE customer_type
        WHEN 'VIP' THEN 'Khách ưu tiên'
        WHEN 'BUSINESS' THEN 'Khách doanh nghiệp'
        ELSE 'Khách phổ thông'
    END AS customer_segment,
    IF(total_amount >= 1000, 'Cao', 'Thông thường') AS amount_level
FROM orders_case_demo
ORDER BY order_id;
~~~

Mỗi biểu thức trả về một giá trị cho từng hàng. Alias giúp đặt tên cho kết quả để client hoặc báo cáo sử dụng.

### 8.1. Giữ kiểu dữ liệu nhánh nhất quán

Các nhánh THEN và ELSE nên trả về kiểu dữ liệu cùng nhóm. Ví dụ, nếu kết quả là nhãn, hãy dùng chuỗi ở mọi nhánh:

~~~sql
CASE
    WHEN total_amount >= 1000 THEN 'HIGH'
    WHEN total_amount >= 500 THEN 'MEDIUM'
    ELSE 'LOW'
END AS amount_level
~~~

Nếu trộn số và chuỗi:

~~~sql
CASE
    WHEN status = 'PAID' THEN 1
    ELSE 'Chưa thanh toán'
END
~~~

MySQL phải xác định một kiểu kết quả chung theo quy tắc tổng hợp kiểu dữ liệu. Kết quả có thể không có kiểu mà ứng dụng mong muốn. Nên dùng nhánh cùng kiểu hoặc CAST tường minh:

~~~sql
CASE
    WHEN status = 'PAID' THEN CAST(1 AS CHAR)
    ELSE 'Chưa thanh toán'
END AS payment_label
~~~

Nếu API cần số, hãy trả số ở mọi nhánh và dùng NULL hoặc mã số có ý nghĩa cho trường hợp còn lại.

### 8.2. Collation của kết quả chuỗi

Khi các nhánh trả về chuỗi có character set/collation khác nhau, MySQL phải tổng hợp collation cho biểu thức kết quả. Nếu không thể phối hợp, truy vấn có thể báo lỗi mix collation hoặc tạo kết quả không theo quy tắc dự định.

Nếu cần, chuyển đổi hoặc chỉ định collation rõ ràng ở các nhánh:

~~~sql
CASE
    WHEN status = 'PAID'
        THEN _utf8mb4'Đã thanh toán' COLLATE utf8mb4_0900_ai_ci
    ELSE _utf8mb4'Chưa thanh toán' COLLATE utf8mb4_0900_ai_ci
END AS status_label
~~~

Hãy dùng collation có sẵn trên phiên bản server và nhất quán với dữ liệu cần so sánh.

## 9. Dùng CASE trong ORDER BY để sắp xếp tùy chỉnh

ORDER BY mặc định sắp xếp theo giá trị cột. CASE cho phép định nghĩa thứ tự nghiệp vụ riêng.

Ví dụ muốn đơn NEW xuất hiện trước, tiếp theo PAID, SHIPPED và CANCELLED:

~~~sql
SELECT order_id, status, created_at
FROM orders_case_demo
ORDER BY
    CASE status
        WHEN 'NEW' THEN 1
        WHEN 'PAID' THEN 2
        WHEN 'SHIPPED' THEN 3
        WHEN 'CANCELLED' THEN 4
        ELSE 99
    END,
    created_at DESC;
~~~

CASE trả về một số thứ tự ưu tiên. created_at là tiêu chí phụ để sắp xếp trong cùng nhóm.

Nếu không có ELSE, trạng thái không được liệt kê trả NULL và có thể xuất hiện ở đầu hoặc cuối tùy chiều sắp xếp. Dùng ELSE để xác định vị trí của giá trị chưa biết.

### 9.1. Sắp xếp NULL ở vị trí mong muốn

Ví dụ đưa các hàng chưa giao xuống cuối:

~~~sql
SELECT order_id, shipped_at
FROM orders_case_demo
ORDER BY
    CASE WHEN shipped_at IS NULL THEN 1 ELSE 0 END,
    shipped_at;
~~~

Biểu thức trả 0 cho hàng đã giao và 1 cho hàng chưa giao, do đó các hàng có thời điểm giao được xếp trước.

## 10. Dùng CASE trong GROUP BY và tổng hợp có điều kiện

CASE rất hữu ích khi muốn phân nhóm hoặc tính nhiều chỉ số trong cùng một lần quét dữ liệu.

### 10.1. GROUP BY theo nhóm dẫn xuất

~~~sql
SELECT
    CASE
        WHEN total_amount >= 1000 THEN 'HIGH'
        WHEN total_amount >= 500 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS amount_group,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue
FROM orders_case_demo
GROUP BY
    CASE
        WHEN total_amount >= 1000 THEN 'HIGH'
        WHEN total_amount >= 500 THEN 'MEDIUM'
        ELSE 'LOW'
    END
ORDER BY amount_group;
~~~

Có thể dùng biểu thức CASE trong GROUP BY. Để tránh lặp logic dài, có thể đặt biểu thức trong derived table hoặc CTE rồi nhóm theo alias ở truy vấn ngoài.

### 10.2. Conditional aggregation với SUM(CASE...)

Ví dụ tính doanh thu theo trạng thái:

~~~sql
SELECT
    SUM(CASE WHEN status = 'PAID'
             THEN total_amount ELSE 0 END) AS paid_total,
    SUM(CASE WHEN status = 'SHIPPED'
             THEN total_amount ELSE 0 END) AS shipped_total,
    SUM(CASE WHEN status = 'CANCELLED'
             THEN total_amount ELSE 0 END) AS cancelled_total
FROM orders_case_demo;
~~~

Mỗi biểu thức chỉ cộng total_amount khi điều kiện đúng, còn lại cộng 0. Đây là kỹ thuật conditional aggregation, thường dùng để tạo báo cáo nhiều cột từ một tập hàng.

### 10.3. Đếm có điều kiện

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
    COUNT(CASE WHEN status = 'SHIPPED' THEN 1 END) AS shipped_orders,
    COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) AS cancelled_orders
FROM orders_case_demo;
~~~

COUNT(expression) bỏ qua NULL. CASE không có ELSE trả NULL khi điều kiện không khớp, nên chỉ các hàng đúng điều kiện được đếm.

Có thể dùng SUM:

~~~sql
SELECT
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders
FROM orders_case_demo;
~~~

Cả hai cách đều hữu ích; hãy chọn cách rõ nghĩa với người đọc.

### 10.4. IF() trong tổng hợp

Vì IF() trả về một trong hai nhánh, có thể viết:

~~~sql
SELECT
    SUM(IF(status = 'PAID', total_amount, 0)) AS paid_total,
    SUM(IF(status = 'SHIPPED', total_amount, 0)) AS shipped_total
FROM orders_case_demo;
~~~

Cách này ngắn khi chỉ có hai khả năng. Nếu báo cáo có nhiều trạng thái hoặc logic phức tạp, CASE thường dễ mở rộng hơn.

## 11. Dùng CASE và IF() trong UPDATE

Biểu thức nhánh có thể cập nhật nhiều hàng theo quy tắc khác nhau trong một câu lệnh.

Ví dụ đặt mức ưu tiên theo tổng tiền:

~~~sql
UPDATE orders_case_demo
SET customer_type = CASE
    WHEN total_amount >= 1000 THEN 'BUSINESS'
    WHEN total_amount >= 500 THEN 'VIP'
    ELSE 'REGULAR'
END;
~~~

Ví dụ bật tỷ lệ giảm giá mặc định nếu chưa có:

~~~sql
UPDATE orders_case_demo
SET discount_rate = IF(
    customer_type = 'VIP',
    0.0500,
    0.0000
)
WHERE discount_rate IS NULL;
~~~

Cẩn thận với UPDATE không có WHERE: tất cả hàng trong bảng sẽ bị tác động. Trước khi chạy, nên thử cùng điều kiện bằng SELECT để xem chính xác các hàng và giá trị mới:

~~~sql
SELECT
    order_id,
    customer_type,
    discount_rate,
    IF(customer_type = 'VIP', 0.0500, 0.0000) AS new_discount_rate
FROM orders_case_demo
WHERE discount_rate IS NULL;
~~~

Sau khi xác minh, mới chạy UPDATE trong transaction hoặc quy trình migration phù hợp.

## 12. CASE để tránh phép tính không hợp lệ

CASE có thể chọn một kết quả thay thế khi điều kiện làm phép tính không hợp lệ.

Ví dụ tính tỷ lệ hoàn thành:

~~~sql
SELECT
    completed_count,
    total_count,
    CASE
        WHEN total_count IS NULL OR total_count = 0 THEN NULL
        ELSE completed_count / total_count
    END AS completion_ratio
FROM task_summary;
~~~

Nếu total_count là NULL hoặc 0, kết quả là NULL. Nếu có mẫu số hợp lệ, phép chia được thực hiện.

Nếu muốn trả về 0 thay cho NULL:

~~~sql
CASE
    WHEN total_count IS NULL OR total_count = 0 THEN 0
    ELSE completed_count / total_count
END
~~~

Chỉ dùng 0 nếu nghiệp vụ thực sự coi trường hợp không có mẫu số là tỷ lệ 0. Có hệ thống cần NULL để phân biệt “không tính được” với “đã tính và bằng 0”.

### 12.1. IF() cho phép tính hai nhánh

~~~sql
SELECT
    IF(total_count > 0,
       completed_count / total_count,
       NULL) AS completion_ratio
FROM task_summary;
~~~

Nếu total_count là NULL, điều kiện total_count > 0 là UNKNOWN; IF() chọn nhánh thứ ba. Trong ví dụ, nhánh đó là NULL nên kết quả vẫn an toàn.

### 12.2. Đừng dùng CASE để che lỗi dữ liệu

CASE không thay thế việc xác thực dữ liệu. Nếu một cột đáng lẽ luôn dương nhưng lại có 0 hoặc NULL, hãy xem xét NOT NULL, CHECK constraint và quy trình ghi dữ liệu. CASE phù hợp để biểu diễn cách xử lý nghiệp vụ, không nên biến mọi lỗi dữ liệu thành một giá trị mặc định khiến sự cố bị che khuất.

## 13. CASE lồng nhau và cách giữ biểu thức dễ đọc

Có thể lồng CASE khi một nhánh cần thêm điều kiện con:

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'CANCELLED' THEN 'Không hợp lệ'
        WHEN status = 'PAID' THEN
            CASE
                WHEN total_amount >= 1000 THEN 'Đã thanh toán - giá trị cao'
                ELSE 'Đã thanh toán'
            END
        ELSE 'Chưa hoàn tất'
    END AS order_summary
FROM orders_case_demo;
~~~

Tuy nhiên, nhiều tầng CASE lồng nhau làm truy vấn khó đọc và kiểm thử. Khi logic phức tạp, có thể:

- Tách thành nhiều cột dẫn xuất trong CTE.
- Tạo derived table để đặt tên kết quả trung gian.
- Đưa quy tắc nghiệp vụ vào bảng cấu hình nếu giá trị có thể thay đổi thường xuyên.
- Dùng stored function chỉ khi thật sự cần tái sử dụng logic phía server và đã đánh giá chi phí.

Ví dụ dùng CTE để tách bước phân nhóm:

~~~sql
WITH classified_orders AS (
    SELECT
        order_id,
        status,
        total_amount,
        CASE
            WHEN total_amount >= 1000 THEN 'HIGH'
            WHEN total_amount >= 500 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS amount_group
    FROM orders_case_demo
)
SELECT
    amount_group,
    COUNT(*) AS order_count
FROM classified_orders
GROUP BY amount_group
ORDER BY amount_group;
~~~

CTE giúp tên amount_group có thể được dùng ở truy vấn ngoài và tránh lặp biểu thức CASE.

## 14. Phân biệt CASE expression với CASE statement và IF statement

Trong MySQL stored programs (procedure, function, trigger), có các câu lệnh điều khiển luồng riêng. Chúng không giống biểu thức CASE và hàm IF() dùng trong câu lệnh SQL.

### 14.1. CASE expression

CASE expression trả về một giá trị:

~~~sql
SELECT
    CASE
        WHEN total_amount >= 1000 THEN 'HIGH'
        ELSE 'NORMAL'
    END AS amount_level
FROM orders_case_demo;
~~~

Nó có thể xuất hiện trong SELECT, ORDER BY, UPDATE hoặc biểu thức khác.

### 14.2. CASE statement trong stored program

CASE statement điều khiển luồng thực thi các câu lệnh:

~~~sql
CASE order_status
    WHEN 'NEW' THEN
        SET message_text = 'Đơn mới';
    WHEN 'PAID' THEN
        SET message_text = 'Đã thanh toán';
    ELSE
        SET message_text = 'Trạng thái khác';
END CASE;
~~~

CASE statement dùng END CASE và thực thi câu lệnh trong nhánh. CASE expression dùng END và trả về một giá trị.

### 14.3. IF() function và IF statement

IF() function dùng trong biểu thức SQL:

~~~sql
SELECT IF(total_amount >= 500, 'Lớn', 'Nhỏ')
FROM orders_case_demo;
~~~

IF statement trong stored program dùng THEN, ELSE và END IF:

~~~sql
IF total_amount >= 500 THEN
    SET message_text = 'Đơn lớn';
ELSE
    SET message_text = 'Đơn thường';
END IF;
~~~

Không dùng cú pháp END IF trong SELECT. Ngược lại, không dùng IF() function thay cho câu lệnh điều khiển nhiều bước trong stored program.

## 15. Phân biệt IF() với IFNULL() và COALESCE()

Các hàm có tên gần nhau nhưng mục đích khác nhau:

| Hàm | Mục đích | Ví dụ |
|---|---|---|
| IF(condition, a, b) | Chọn nhánh theo điều kiện | IF(quantity > 0, 'Còn hàng', 'Hết hàng') |
| IFNULL(value, fallback) | Thay giá trị NULL bằng fallback | IFNULL(note, 'Không có ghi chú') |
| COALESCE(a, b, c, ...) | Trả về đối số đầu tiên không NULL | COALESCE(phone, email, 'Chưa có liên hệ') |
| NULLIF(a, b) | Trả NULL nếu a bằng b; ngược lại trả a | numerator / NULLIF(denominator, 0) |

Ví dụ:

~~~sql
SELECT
    order_id,
    IF(shipped_at IS NULL, 'Chưa giao', 'Đã giao') AS status_by_condition,
    IFNULL(discount_rate, 0) AS discount_default,
    COALESCE(
        CAST(discount_rate AS CHAR),
        'Chưa xác định'
    ) AS discount_text
FROM orders_case_demo;
~~~

IF() trả nhánh theo điều kiện. IFNULL và COALESCE chỉ kiểm tra sự hiện diện của NULL; chúng không thay thế logic nhiều điều kiện của CASE.

Nếu muốn tránh phép chia cho 0, NULLIF thường ngắn gọn:

~~~sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM calculation;
~~~

Khi denominator bằng 0, NULLIF trả NULL và kết quả phép chia là NULL. Hãy xác định cách ứng dụng hiển thị giá trị đó.

## 16. Kiểu dữ liệu của kết quả CASE và IF()

MySQL xác định kiểu dữ liệu của biểu thức kết quả dựa trên các nhánh THEN/ELSE hoặc các đối số kết quả của IF(). Vì vậy, các nhánh không được chọn trong một hàng vẫn có thể ảnh hưởng tới metadata kiểu kết quả của toàn biểu thức.

Ví dụ:

~~~sql
SELECT
    CASE
        WHEN status = 'PAID' THEN 1
        ELSE 0
    END AS paid_flag,
    IF(status = 'PAID', 1, 0) AS paid_flag_if
FROM orders_case_demo;
~~~

Cả hai biểu thức đều trả số nguyên 1 hoặc 0.

Nếu trả số thập phân, hãy giữ kiểu số nhất quán:

~~~sql
CASE
    WHEN customer_type = 'VIP' THEN CAST(0.05 AS DECIMAL(5, 4))
    WHEN customer_type = 'BUSINESS' THEN CAST(0.10 AS DECIMAL(5, 4))
    ELSE CAST(0.00 AS DECIMAL(5, 4))
END AS discount_rate
~~~

Nếu trả chuỗi, giữ các nhánh cùng character set/collation khi có thể. Khi cần API ổn định, hãy CAST tường minh và kiểm tra metadata của ResultSet thay vì dựa vào suy đoán.

### 16.1. NULL trong các nhánh kết quả

Một nhánh có thể trả NULL:

~~~sql
CASE
    WHEN status = 'PAID' THEN total_amount
    ELSE NULL
END AS paid_amount
~~~

Kết quả có thể mang kiểu số với khả năng NULL. Nếu dùng trong SUM, AVG hoặc phép tính khác, hãy nhớ hàm tổng hợp thường bỏ qua NULL.

Không thay NULL bằng 0 nếu điều đó làm mất ý nghĩa “không áp dụng” hoặc “chưa xác định”.

## 17. CASE và IF() ảnh hưởng đến index như thế nào?

CASE và IF() thường rất hữu ích trong danh sách SELECT hoặc ORDER BY. Nhưng nếu bọc cột được index trong biểu thức ở WHERE, optimizer có thể không sử dụng index theo cách trực tiếp.

Ví dụ:

~~~sql
EXPLAIN
SELECT order_id
FROM orders_case_demo
WHERE CASE
    WHEN status = 'PAID' THEN 1
    ELSE 0
END = 1;
~~~

Nếu chỉ muốn lọc PAID, điều kiện trực tiếp rõ ràng hơn:

~~~sql
EXPLAIN
SELECT order_id
FROM orders_case_demo
WHERE status = 'PAID';
~~~

Tương tự, tránh:

~~~sql
WHERE IF(status = 'PAID', 1, 0) = 1
~~~

khi có thể viết:

~~~sql
WHERE status = 'PAID'
~~~

CASE trong ORDER BY có thể yêu cầu tính biểu thức cho các hàng được sắp xếp và thường không thể tận dụng index thông thường để tạo thứ tự tùy chỉnh. Nếu thứ tự nghiệp vụ này được sử dụng thường xuyên trên tập dữ liệu lớn, hãy đánh giá generated column được index hoặc bảng mã ưu tiên, nhưng chỉ sau khi đo bằng EXPLAIN và workload thật.

Không có quy tắc rằng mọi CASE đều làm truy vấn chậm. Tác động phụ thuộc vị trí biểu thức, số hàng, index và kế hoạch optimizer.

## 18. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| WHEN NULL không khớp | Simple CASE dùng phép so sánh bằng, NULL tạo UNKNOWN | Dùng searched CASE với IS NULL |
| Không có ELSE trả NULL | Không nhánh nào khớp | Thêm ELSE nếu cần giá trị mặc định |
| Phân loại sai ngưỡng | Điều kiện rộng đứng trước điều kiện hẹp | Đặt nhánh ưu tiên trước, từ ngưỡng cao xuống thấp |
| IF(NULL, a, b) trả b | NULL được xem là điều kiện không đúng | Viết điều kiện NULL rõ ràng nếu nghiệp vụ cần nhánh riêng |
| Dùng chuỗi làm điều kiện IF | MySQL có thể chuyển chuỗi sang số | Dùng predicate boolean như x > 0 |
| Trộn kiểu số và chuỗi trong THEN/ELSE | MySQL phải tổng hợp kiểu kết quả | Dùng cùng kiểu hoặc CAST tường minh |
| Lặp CASE dài trong GROUP BY | Logic khó bảo trì và dễ lệch | Dùng CTE hoặc derived table |
| CASE trong WHERE làm khó dùng index | Biểu thức che cột gốc | Viết predicate trực tiếp nếu có thể |
| Nhầm CASE expression với CASE statement | Cùng tên nhưng khác ngữ cảnh | Expression dùng END; statement dùng END CASE |
| Nhầm IF() với IF statement | Một bên là hàm, một bên là điều khiển stored program | Dùng đúng cú pháp theo ngữ cảnh |

## 19. Quy trình thiết kế biểu thức lựa chọn nhánh

Khi viết CASE hoặc IF(), hãy làm theo thứ tự:

1. Xác định đầu ra là số, chuỗi, ngày giờ hay NULL.
2. Liệt kê đầy đủ các trường hợp nghiệp vụ.
3. Xác định trường hợp nào có thể NULL.
4. Chọn Simple CASE nếu so sánh một biểu thức với nhiều giá trị; chọn Searched CASE nếu mỗi nhánh có predicate riêng.
5. Dùng IF() khi chỉ có hai nhánh đơn giản.
6. Sắp xếp WHEN theo thứ tự ưu tiên, đặc biệt với khoảng giá trị chồng lấn.
7. Quyết định ELSE rõ ràng; không để NULL mặc định nếu không mong muốn.
8. Giữ kiểu dữ liệu và collation kết quả nhất quán.
9. Kiểm tra biểu thức với dữ liệu biên: NULL, 0, giá trị âm, ngưỡng bằng đúng và trạng thái không biết.
10. Nếu biểu thức nằm trong WHERE hoặc ORDER BY, kiểm tra EXPLAIN và đo hiệu năng.

## 20. Bài tập thực hành

### Bài 1: Nhãn trạng thái với Simple CASE

Dùng bảng orders_case_demo, chuyển các mã NEW, PAID, SHIPPED và CANCELLED thành nhãn tiếng Việt. Thêm ELSE cho trạng thái chưa biết.

Kết quả cần có: truy vấn hiển thị order_id, status và status_label.

### Bài 2: Phân loại tổng tiền với Searched CASE

Phân loại đơn hàng thành:
- HIGH: từ 1.000 trở lên.
- MEDIUM: từ 500 đến dưới 1.000.
- LOW: dưới 500.

Thử thay đổi thứ tự WHEN và giải thích vì sao điều kiện ngưỡng rộng có thể làm nhánh phía sau không bao giờ được chọn.

### Bài 3: Kiểm tra NULL

Viết hai biểu thức:
- Simple CASE thử dùng WHEN NULL.
- Searched CASE dùng IS NULL.

Chạy với discount_rate NULL và ghi lại kết quả. Giải thích logic UNKNOWN.

### Bài 4: IF() và CASE

Viết cùng một logic phân loại đơn hàng chỉ có hai kết quả bằng IF() và CASE. So sánh độ dài, khả năng mở rộng và cách xử lý điều kiện NULL.

### Bài 5: Conditional aggregation

Tính số đơn và tổng tiền theo trạng thái PAID, SHIPPED, CANCELLED trong một truy vấn dùng SUM(CASE...) và COUNT(CASE...). Đối chiếu với các truy vấn GROUP BY status.

### Bài 6: Sắp xếp tùy chỉnh

Sắp xếp NEW trước PAID, SHIPPED, CANCELLED bằng CASE trong ORDER BY. Thêm created_at làm tiêu chí phụ và xác định vị trí trạng thái không biết.

### Bài 7: Tính tỷ lệ an toàn

Tạo bảng tổng hợp có completed_count và total_count. Viết CASE để trả NULL hoặc 0 khi total_count bằng 0 hoặc NULL. Giải thích sự khác nhau về ý nghĩa nghiệp vụ.

### Bài 8: Kiểm tra kế hoạch thực thi

So sánh EXPLAIN của điều kiện status = 'PAID' và biểu thức CASE trong WHERE. Ghi lại access type, key và rows ước tính. Giải thích khi nào nên giữ CASE ở phần SELECT và dùng predicate trực tiếp trong WHERE.

## 21. Checklist trước khi đưa biểu thức vào ứng dụng

- [ ] Đã chọn CASE hay IF() theo số nhánh và độ phức tạp.
- [ ] Đã phân biệt Simple CASE và Searched CASE.
- [ ] Đã kiểm tra NULL bằng IS NULL/IS NOT NULL.
- [ ] Đã nhớ WHEN chỉ chọn nhánh khi điều kiện TRUE.
- [ ] Đã sắp xếp điều kiện theo thứ tự ưu tiên.
- [ ] Đã khai báo ELSE khi cần kết quả mặc định.
- [ ] Đã giữ kiểu dữ liệu và collation kết quả nhất quán.
- [ ] Đã kiểm thử NULL, 0, giá trị âm và đúng ngưỡng.
- [ ] Đã phân biệt IF() function với IF statement trong stored program.
- [ ] Đã tránh dùng CASE/IF không cần thiết trong WHERE.
- [ ] Đã kiểm tra EXPLAIN nếu biểu thức ảnh hưởng tới lọc hoặc sắp xếp.
- [ ] Đã xác minh kết quả bằng dữ liệu đại diện và dữ liệu biên.

## 22. Kết luận

CASE và IF() giúp biểu diễn logic lựa chọn nhánh ngay trong SQL. CASE phù hợp với nhiều nhánh, điều kiện phức tạp và mã SQL cần tính di động; IF() gọn cho lựa chọn hai nhánh trong MySQL. Simple CASE so sánh một biểu thức với các giá trị, còn Searched CASE đánh giá từng predicate.

Khi sử dụng, hãy nhớ CASE chỉ chọn WHEN có kết quả TRUE; UNKNOWN do NULL không được xem là đúng. Simple CASE không bắt NULL bằng WHEN NULL, nên dùng IS NULL trong Searched CASE. Giữ các nhánh trả về kiểu dữ liệu nhất quán, đặt điều kiện theo thứ tự ưu tiên và dùng predicate trực tiếp trong WHERE khi có thể. Những nguyên tắc này giúp biểu thức dễ hiểu, kết quả ổn định và thuận lợi cho optimizer.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Flow Control Functions](https://dev.mysql.com/doc/refman/8.4/en/flow-control-functions.html)
- [MySQL 8.4 Reference Manual – CASE Operator](https://dev.mysql.com/doc/refman/8.4/en/flow-control-functions.html#operator_case)
- [MySQL 8.4 Reference Manual – IF() Function](https://dev.mysql.com/doc/refman/8.4/en/flow-control-functions.html#function_if)
- [MySQL 8.4 Reference Manual – IFNULL() Function](https://dev.mysql.com/doc/refman/8.4/en/flow-control-functions.html#function_ifnull)
- [MySQL 8.4 Reference Manual – COALESCE() Function](https://dev.mysql.com/doc/refman/8.4/en/comparison-operators.html#function_coalesce)
- [MySQL 8.4 Reference Manual – NULL Values](https://dev.mysql.com/doc/refman/8.4/en/working-with-null.html)
- [MySQL 8.4 Reference Manual – Type Conversion in Expression Evaluation](https://dev.mysql.com/doc/refman/8.4/en/type-conversion.html)
- [MySQL 8.4 Reference Manual – Stored Program Flow Control](https://dev.mysql.com/doc/refman/8.4/en/flow-control-statements.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)

