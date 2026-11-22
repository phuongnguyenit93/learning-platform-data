# Báo cáo doanh thu không cộng lặp chi tiết đơn hàng

> **Module:** Database SQL  
> **Chương:** Thực hành tổng hợp  
> **Bài học:** Báo cáo doanh thu không cộng lặp chi tiết đơn hàng

Một báo cáo doanh thu có thể cho ra con số lớn gấp hai, gấp ba hoặc gấp nhiều lần thực tế dù câu SQL không báo lỗi. Nguyên nhân thường là **JOIN làm nhân số dòng trước khi SUM**.

Một đơn hàng có một dòng ở bảng đơn hàng, nhiều dòng ở bảng chi tiết, nhiều lần thanh toán và có thể nhiều lần hoàn tiền. Khi nối tất cả bảng con vào cùng một truy vấn, mỗi chi tiết có thể kết hợp với mọi lần thanh toán và mọi lần hoàn tiền của đơn. Tổng tiền ở bảng cha bị lặp; tổng chi tiết cũng có thể bị lặp; tổng thanh toán và hoàn tiền cũng bị nhân theo số dòng của các bảng khác.

Muốn báo cáo đúng, phải xác định **grain (mức chi tiết của một dòng dữ liệu)**, hiểu quan hệ một-một/một-nhiều/nhiều-nhiều, và tổng hợp mỗi nguồn về đúng mức trước khi kết hợp. Không thể sửa mọi trường hợp bằng DISTINCT.

Bài học này xây dựng một báo cáo mẫu có đơn hàng, chi tiết, thanh toán và hoàn tiền; chứng minh lỗi cộng lặp bằng dữ liệu cụ thể; sau đó viết truy vấn an toàn cho tổng doanh thu theo đơn, khách hàng, sản phẩm và tháng. Bài cũng chỉ ra cách đối soát, xử lý trạng thái, giảm giá, thuế, phí vận chuyển, tiền tệ, ngày ghi nhận và kiểm thử trên nhiều hệ quản trị.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định grain của bảng đơn hàng, chi tiết, thanh toán và hoàn tiền.
2. Giải thích vì sao JOIN nhiều quan hệ một-nhiều làm tăng số dòng.
3. Tính số lần một giá trị ở bảng cha bị lặp sau JOIN.
4. Phân biệt doanh thu theo dòng hàng, doanh thu theo đơn, tiền thu và tiền hoàn.
5. Nhận biết vì sao COUNT(DISTINCT order_id) có thể sửa số đơn nhưng không sửa SUM(order_total).
6. Giải thích vì sao SUM(DISTINCT order_total) không phải cách sửa đúng.
7. Tổng hợp bảng chi tiết về một dòng mỗi đơn trước khi nối với bảng cha.
8. Tổng hợp thanh toán và hoàn tiền độc lập trước khi JOIN.
9. Dùng EXISTS khi chỉ cần kiểm tra có dòng con.
10. Báo cáo doanh thu theo khách hàng, sản phẩm, ngày và tháng mà không nhân số.
11. Phân biệt tổng tiền hàng, giảm giá, thuế, phí vận chuyển và tổng phải trả.
12. Xử lý nhiều lần thanh toán, payment attempt, partial capture và refund.
13. Lọc đúng trạng thái đơn hàng và thời điểm ghi nhận doanh thu.
14. Xử lý tiền tệ khác nhau mà không cộng trực tiếp các currency.
15. Dùng NULL, COALESCE và LEFT JOIN có chủ đích.
16. Đối soát tổng header với tổng line và các khoản thanh toán.
17. Kiểm tra các trường hợp đơn không có chi tiết, không có thanh toán hoặc có nhiều refund.
18. Dùng CTE/derived table và index để truy vấn dễ hiểu, hiệu quả.
19. Kiểm thử bằng fixture có kết quả kỳ vọng rõ ràng.
20. Phát hiện fan-out do bảng phụ như tag, promotion, shipment và audit.

## 2. Bắt đầu từ định nghĩa doanh thu

“Doanh thu” không phải lúc nào cũng bằng tổng tiền đơn hàng hoặc tổng tiền thanh toán. Trước khi viết SQL, cần trả lời báo cáo đang đo gì.

Một số chỉ tiêu thường bị nhầm:

| Chỉ tiêu | Ý nghĩa | Nguồn dữ liệu thường gặp |
|---|---|---|
| Gross merchandise sales | Giá trị hàng trước giảm giá | Chi tiết đơn |
| Net merchandise sales | Giá trị hàng sau giảm giá | Chi tiết đơn |
| Order total | Tổng khách phải trả, có thể gồm thuế/phí | Header đơn hàng |
| Captured payments | Tiền đã capture/thu thành công | Giao dịch thanh toán |
| Refunded amount | Tiền đã hoàn thành công | Giao dịch hoàn tiền |
| Net cash collected | Tiền đã thu trừ tiền đã hoàn | Payment/refund ledger |
| Recognized revenue | Doanh thu ghi nhận theo chính sách kế toán | Sự kiện giao hàng/hoàn thành/ghi nhận |
| Outstanding balance | Số còn phải thu | Phải thu, payment và credit adjustments |

Một báo cáo bán hàng có thể dùng net merchandise sales; báo cáo dòng tiền dùng captured payments trừ refunds; báo cáo kế toán dùng recognized revenue theo chính sách ghi nhận. Ba số có thể khác nhau mà không có lỗi dữ liệu.

### 2.1. Định nghĩa metric trong bài thực hành

Để các ví dụ có kết quả kiểm chứng được, bài này dùng hợp đồng sau:

**Net merchandise revenue** = tổng tiền hàng sau giảm giá dòng hàng của các đơn đã hoàn thành, trừ các khoản hoàn tiền được phân bổ cho hàng hóa.

- Không bao gồm thuế.
- Không bao gồm phí vận chuyển.
- Chỉ tính đơn có trạng thái COMPLETED.
- Ngày báo cáo dựa trên recognized_at của đơn.
- Mỗi đơn thuộc một currency_code; chỉ cộng trong cùng currency.
- Refund chỉ được trừ khi trạng thái đã APPROVED/COMPLETED theo chính sách mẫu.
- Chiết khấu cấp đơn phải được phân bổ vào dòng hàng trước khi tính chỉ tiêu theo sản phẩm, hoặc được trừ riêng ở cấp đơn. Không trừ hai lần.

Đây là định nghĩa minh họa. Hệ thống thật phải thống nhất với kế toán về thời điểm ghi nhận, hoàn tiền, thuế, phí và chính sách đổi trả.

### 2.2. Viết định nghĩa trước khi viết SQL

Một metric tốt nên có:
- Tên và mục đích.
- Grain của kết quả: mỗi đơn, mỗi khách, mỗi sản phẩm, mỗi ngày hay mỗi tháng.
- Các bảng nguồn.
- Trạng thái được bao gồm/loại trừ.
- Quy tắc giảm giá, thuế, shipping, refund.
- Currency và timezone.
- Ngày dùng để nhóm.
- Quy tắc xử lý NULL và dữ liệu lỗi.
- Cách đối soát với báo cáo chuẩn.

Nếu chưa xác định những điều này, hai câu SQL khác nhau có thể đều “đúng cú pháp” nhưng đo hai thứ khác nhau.

## 3. Grain: đơn vị của một dòng dữ liệu

Grain trả lời câu hỏi: **một hàng trong bảng đại diện cho điều gì?**

Trong ví dụ:

| Bảng | Grain | Quan hệ với order |
|---|---|---|
| sales_order | Một hàng cho một đơn | 1 |
| sales_order_line | Một hàng cho một dòng sản phẩm trong đơn | N |
| payment | Một hàng cho một giao dịch thanh toán | N |
| refund | Một hàng cho một yêu cầu/giao dịch hoàn tiền | N |
| refund_line | Một hàng cho phần hoàn tiền gắn với một dòng hàng | N |
| shipment | Một hàng cho một kiện/lần giao | N |
| order_tag | Một hàng cho một tag gắn với đơn | N |

Khóa order_id xuất hiện ở nhiều hàng trong bảng con. Đây là điều bình thường.

### 3.1. Bảng cha và bảng con

Một đơn có thể có:
- 1 hàng sales_order.
- 3 hàng sales_order_line.
- 2 hàng payment.
- 1 hàng refund.
- 2 hàng shipment.

JOIN các bảng này theo order_id không còn trả một hàng cho mỗi đơn. Nó trả tổ hợp các hàng con phù hợp.

### 3.2. Grain của kết quả cũng phải rõ

Ví dụ:
- Báo cáo tổng doanh thu toàn hệ thống: một hàng cho mỗi currency hoặc một hàng tổng.
- Báo cáo theo khách hàng: một hàng cho mỗi customer và currency.
- Báo cáo theo sản phẩm: một hàng cho mỗi product và currency.
- Báo cáo chi tiết đơn: một hàng cho mỗi order.
- Báo cáo theo ngày: một hàng cho mỗi business_date và currency.

Nếu query kết hợp cột ở nhiều grain, phải xác định metric nào được tính ở grain nào và có cần phân bổ hay không.

## 4. Schema thực hành

DDL dưới đây dùng kiểu dữ liệu phổ biến. Cú pháp identity/auto-increment có thể cần điều chỉnh theo DBMS; phần quan trọng của ví dụ là khóa ngoại và grain.

~~~sql
CREATE TABLE sales_order (
    order_id BIGINT PRIMARY KEY,
    customer_id VARCHAR(30) NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    ordered_at TIMESTAMP NOT NULL,
    recognized_at TIMESTAMP,
    currency_code CHAR(3) NOT NULL,
    subtotal_gross DECIMAL(14,2) NOT NULL,
    discount_total DECIMAL(14,2) NOT NULL,
    tax_total DECIMAL(14,2) NOT NULL,
    shipping_total DECIMAL(14,2) NOT NULL,
    order_total DECIMAL(14,2) NOT NULL
);

CREATE TABLE sales_order_line (
    line_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id VARCHAR(30) NOT NULL,
    quantity DECIMAL(12,3) NOT NULL,
    unit_price DECIMAL(14,2) NOT NULL,
    line_discount DECIMAL(14,2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES sales_order(order_id)
);

CREATE TABLE payment (
    payment_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    payment_status VARCHAR(20) NOT NULL,
    payment_type VARCHAR(20) NOT NULL,
    amount DECIMAL(14,2) NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    FOREIGN KEY (order_id) REFERENCES sales_order(order_id)
);

CREATE TABLE refund (
    refund_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    refund_status VARCHAR(20) NOT NULL,
    refund_total DECIMAL(14,2) NOT NULL,
    refunded_at TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES sales_order(order_id)
);

CREATE TABLE refund_line (
    refund_line_id BIGINT PRIMARY KEY,
    refund_id BIGINT NOT NULL,
    line_id BIGINT NOT NULL,
    refund_amount DECIMAL(14,2) NOT NULL,
    FOREIGN KEY (refund_id) REFERENCES refund(refund_id),
    FOREIGN KEY (line_id) REFERENCES sales_order_line(line_id)
);
~~~

### 4.1. Ý nghĩa các cột tiền

Trong bài:
- line_gross = quantity × unit_price.
- line_discount là phần giảm giá đã phân bổ cho dòng hàng.
- line_net = line_gross − line_discount.
- subtotal_gross ở header = tổng line_gross.
- discount_total = tổng line_discount.
- net merchandise = subtotal_gross − discount_total.
- order_total = net merchandise + tax_total + shipping_total.

Nếu hệ thống có discount cấp đơn, hãy phân bổ vào line_discount hoặc lưu riêng rồi trừ ở cấp đơn. Đừng vừa trừ trong line vừa trừ discount_total lần nữa.

### 4.2. Không dùng FLOAT cho tiền

Dùng DECIMAL/NUMERIC với precision/scale được chọn theo nghiệp vụ. FLOAT/REAL là số dấu phẩy động nhị phân, có thể tạo sai số khi cộng/trừ tiền. Trong Java, dùng BigDecimal với quy tắc scale/rounding rõ.

### 4.3. Ràng buộc nghiệp vụ

Có thể bổ sung:
- quantity > 0.
- unit_price >= 0.
- line_discount >= 0.
- refund_amount >= 0.
- order_total = subtotal_gross - discount_total + tax_total + shipping_total.
- Tổng refund không vượt giới hạn được phép.
- Status chỉ nhận giá trị hợp lệ.

Cú pháp CHECK, computed column và cách xử lý NULL khác nhau giữa DBMS. Ràng buộc nên được hiện thực theo dialect và vẫn có test.

## 5. Fixture mẫu và số đúng cần ra

Nạp ba đơn:

~~~sql
INSERT INTO sales_order (
    order_id, customer_id, order_status,
    ordered_at, recognized_at, currency_code,
    subtotal_gross, discount_total, tax_total,
    shipping_total, order_total
) VALUES
(100, 'C01', 'COMPLETED',
 '2026-10-03 09:00:00', '2026-10-03 10:00:00', 'VND',
 100000, 10000, 9000, 5000, 104000),
(101, 'C01', 'COMPLETED',
 '2026-10-03 11:00:00', '2026-10-03 12:00:00', 'VND',
 50000, 0, 5000, 0, 55000),
(102, 'C02', 'CANCELLED',
 '2026-10-03 13:00:00', NULL, 'VND',
 20000, 0, 0, 0, 20000);
~~~

Chi tiết:

~~~sql
INSERT INTO sales_order_line (
    line_id, order_id, product_id,
    quantity, unit_price, line_discount
) VALUES
(1001, 100, 'P-A', 2, 30000, 6000),
(1002, 100, 'P-B', 1, 40000, 4000),
(1011, 101, 'P-C', 1, 50000, 0),
(1021, 102, 'P-A', 1, 20000, 0);
~~~

Thanh toán:

~~~sql
INSERT INTO payment (
    payment_id, order_id, payment_status,
    payment_type, amount, occurred_at
) VALUES
(5001, 100, 'CAPTURED', 'CARD', 60000, '2026-10-03 09:05:00'),
(5002, 100, 'CAPTURED', 'CARD', 44000, '2026-10-03 09:10:00'),
(5011, 101, 'CAPTURED', 'BANK', 55000, '2026-10-03 11:05:00');
~~~

Hoàn tiền:

~~~sql
INSERT INTO refund (
    refund_id, order_id, refund_status, refund_total, refunded_at
) VALUES
(7001, 100, 'APPROVED', 10000, '2026-10-04 08:00:00');

INSERT INTO refund_line (
    refund_line_id, refund_id, line_id, refund_amount
) VALUES
(7101, 7001, 1001, 10000);
~~~

### 5.1. Tính line revenue

| Order | Line | Gross | Discount | Net |
|---:|---:|---:|---:|---:|
| 100 | 1001 / P-A | 60.000 | 6.000 | 54.000 |
| 100 | 1002 / P-B | 40.000 | 4.000 | 36.000 |
| 101 | 1011 / P-C | 50.000 | 0 | 50.000 |
| 102 | 1021 / P-A | 20.000 | 0 | 20.000 |

Đơn 102 bị hủy, không thuộc metric doanh thu đã định nghĩa.

### 5.2. Số đúng theo hợp đồng mẫu

| Chỉ tiêu | Tính toán | Kết quả |
|---|---|---:|
| Net merchandise đơn 100 | 54.000 + 36.000 | 90.000 |
| Net merchandise đơn 101 | 50.000 | 50.000 |
| Merchandise trước refund | 90.000 + 50.000 | 140.000 |
| Merchandise refund đã duyệt | 10.000 | 10.000 |
| Net merchandise revenue | 140.000 − 10.000 | **130.000** |
| Order total đơn hoàn thành | 104.000 + 55.000 | 159.000 |
| Captured payment | 60.000 + 44.000 + 55.000 | 159.000 |
| Net cash sau refund | 159.000 − 10.000 | 149.000 |

Các con số 130.000, 159.000 và 149.000 đo ba chỉ tiêu khác nhau. Không chọn một con số rồi gắn nhãn “doanh thu” mà chưa xác định metric.

## 6. JOIN làm nhân dòng như thế nào?

Đơn 100 có:
- 2 dòng hàng.
- 2 lần thanh toán.
- 1 lần hoàn tiền.

Nếu JOIN cả ba bảng con theo order_id, số tổ hợp là:

~~~text
2 lines × 2 payments × 1 refund = 4 rows
~~~

Một bảng kết quả rút gọn:

| Order | Line | Line net | Payment | Payment amount | Refund |
|---:|---:|---:|---:|---:|---:|
| 100 | 1001 | 54.000 | 5001 | 60.000 | 7001 |
| 100 | 1001 | 54.000 | 5002 | 44.000 | 7001 |
| 100 | 1002 | 36.000 | 5001 | 60.000 | 7001 |
| 100 | 1002 | 36.000 | 5002 | 44.000 | 7001 |

Bốn dòng này không phải bốn đơn hàng. Chúng là bốn tổ hợp line × payment.

### 6.1. Fan-out và công thức tổng quát

Với một đơn có:
- L dòng chi tiết.
- P dòng thanh toán.
- R dòng hoàn tiền.

Nếu tất cả được LEFT JOIN độc lập theo order_id và các tập con không rỗng, số dòng kết quả cho đơn đó có thể là:

~~~text
L × P × R
~~~

Nếu một tập con rỗng và dùng LEFT JOIN, nó vẫn tạo một nhánh NULL như một dòng, nên số dòng có thể là:

~~~text
max(1,L) × max(1,P) × max(1,R)
~~~

Đây là lý do một bảng cha bị lặp nhiều lần sau JOIN.

### 6.2. Tổng tiền sai cụ thể

Với đơn 100:
- SUM(order_total) trong kết quả join = 104.000 × 4 = 416.000.
- SUM(line_net) = (54.000 + 36.000) × 2 payments = 180.000.
- SUM(payment.amount) = (60.000 + 44.000) × 2 lines = 208.000.
- SUM(refund_total) = 10.000 × 4 = 40.000.

Các tổng đều bị nhân bởi cardinality của những bảng con khác.

## 7. Truy vấn sai thường gặp

~~~sql
SELECT
    SUM(o.order_total) AS order_total,
    SUM(l.quantity * l.unit_price - l.line_discount) AS line_revenue,
    SUM(p.amount) AS captured_amount,
    SUM(r.refund_total) AS refund_amount
FROM sales_order o
LEFT JOIN sales_order_line l
    ON l.order_id = o.order_id
LEFT JOIN payment p
    ON p.order_id = o.order_id
   AND p.payment_status = 'CAPTURED'
LEFT JOIN refund r
    ON r.order_id = o.order_id
   AND r.refund_status = 'APPROVED'
WHERE o.order_status = 'COMPLETED';
~~~

Với fixture, truy vấn này cho các tổng sai:
- order_total = 471.000 thay vì 159.000.
- line_revenue = 230.000 thay vì 140.000.
- captured_amount = 263.000 thay vì 159.000.
- refund_amount = 40.000 thay vì 10.000.

Phần sai đến từ:
- Đơn 100 bị nhân bốn lần.
- Đơn 101 có một line và một payment nên có một dòng.
- Các bảng con nhân lẫn nhau ở đơn 100.

### 7.1. COUNT(DISTINCT) không sửa SUM

Cách sau:

~~~sql
SELECT
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(o.order_total) AS order_total
FROM ...
~~~

có thể trả đúng số đơn nhưng tổng tiền vẫn bị lặp.

COUNT(DISTINCT order_id) chỉ đếm mỗi khóa đơn một lần trong phép đếm đó. Nó không thay đổi số dòng mà SUM nhìn thấy.

### 7.2. SUM(DISTINCT order_total) cũng sai

Giả sử hai đơn khác nhau đều có order_total = 55.000. SUM(DISTINCT order_total) chỉ cộng 55.000 một lần, dù có hai đơn.

DISTINCT áp dụng lên **giá trị biểu thức**, không phải ý nghĩa “mỗi order một lần”. Hai đơn có cùng số tiền là hai giao dịch riêng biệt.

Tương tự, SUM(DISTINCT line_net) có thể bỏ mất hai dòng hàng hợp lệ có cùng số tiền.

### 7.3. SELECT DISTINCT ở ngoài cũng không tự sửa được

SELECT DISTINCT có thể loại các hàng trùng trên toàn bộ cột select, nhưng nếu mỗi dòng có payment_id hoặc line_id khác nhau thì chúng không trùng. Nếu chỉ select order_total rồi DISTINCT, lại có thể gộp hai đơn khác nhau cùng tổng tiền.

Hãy sửa grain trước khi tổng hợp, không dùng DISTINCT để che fan-out.

## 8. Cách đúng: tổng hợp bảng con trước khi JOIN

Tạo mỗi CTE chỉ có **tối đa một hàng cho mỗi order_id**.

~~~sql
WITH line_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - line_discount) AS merchandise_net
    FROM sales_order_line
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS captured_amount
    FROM payment
    WHERE payment_status = 'CAPTURED'
    GROUP BY order_id
),
refund_totals AS (
    SELECT
        r.order_id,
        SUM(r.refund_total) AS refunded_amount
    FROM refund r
    WHERE r.refund_status = 'APPROVED'
    GROUP BY r.order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.currency_code,
    o.order_total,
    COALESCE(lt.merchandise_net, 0) AS merchandise_net,
    COALESCE(pt.captured_amount, 0) AS captured_amount,
    COALESCE(rt.refunded_amount, 0) AS refunded_amount
FROM sales_order o
LEFT JOIN line_totals lt
    ON lt.order_id = o.order_id
LEFT JOIN payment_totals pt
    ON pt.order_id = o.order_id
LEFT JOIN refund_totals rt
    ON rt.order_id = o.order_id
WHERE o.order_status = 'COMPLETED';
~~~

Bây giờ:
- line_totals: một hàng/order.
- payment_totals: một hàng/order.
- refund_totals: một hàng/order.
- sales_order: một hàng/order.

Mỗi JOIN là quan hệ 1:0..1 theo order_id. Nó không nhân số đơn.

### 8.1. Vì sao pre-aggregation hiệu quả?

Ta chuyển:

~~~text
order 1 ── N lines
       ├── N payments
       └── N refunds
~~~

thành:

~~~text
order 1 ── 0..1 line_totals
       ├── 0..1 payment_totals
       └── 0..1 refund_totals
~~~

Kết quả sau JOIN vẫn giữ một hàng cho mỗi order.

### 8.2. Điều kiện quan trọng

CTE/derived table phải thực sự GROUP BY đúng khóa. Nếu group theo order_id và payment_status, một order có nhiều status có thể vẫn có nhiều dòng và fan-out trở lại.

Ví dụ không đủ an toàn:

~~~sql
SELECT order_id, payment_status, SUM(amount)
FROM payment
GROUP BY order_id, payment_status;
~~~

Nếu JOIN chỉ bằng order_id, một đơn có thể khớp nhiều dòng payment_totals. Muốn giữ một hàng/order, hãy lọc status trước hoặc tổng hợp status thành các cột trên cùng một hàng.

## 9. Báo cáo tổng net merchandise revenue

Theo định nghĩa ở mục 2, ta cần tổng line net của đơn hoàn thành trừ merchandise refunds đã duyệt.

Refund ở cấp header có thể gồm shipping/tax/merchandise. Vì vậy, để tính đúng **merchandise refund**, hãy dùng refund_line được phân bổ cho line hàng.

~~~sql
WITH line_totals AS (
    SELECT
        l.order_id,
        SUM(l.quantity * l.unit_price - l.line_discount) AS merchandise_net
    FROM sales_order_line l
    GROUP BY l.order_id
),
merchandise_refunds AS (
    SELECT
        r.order_id,
        SUM(rl.refund_amount) AS merchandise_refunded
    FROM refund r
    JOIN refund_line rl
        ON rl.refund_id = r.refund_id
    WHERE r.refund_status = 'APPROVED'
    GROUP BY r.order_id
)
SELECT
    o.currency_code,
    SUM(
        COALESCE(lt.merchandise_net, 0)
        - COALESCE(mr.merchandise_refunded, 0)
    ) AS net_merchandise_revenue
FROM sales_order o
LEFT JOIN line_totals lt
    ON lt.order_id = o.order_id
LEFT JOIN merchandise_refunds mr
    ON mr.order_id = o.order_id
WHERE o.order_status = 'COMPLETED'
GROUP BY o.currency_code;
~~~

Kết quả fixture:

| currency_code | net_merchandise_revenue |
|---|---:|
| VND | 130.000 |

Mỗi CTE có tối đa một hàng/order, nên tổng cuối không bị nhân.

### 9.1. Điều gì nếu refund không được phân bổ vào dòng hàng?

Nếu chỉ có refund header với refund_total, bạn biết tổng tiền hoàn theo đơn nhưng không biết chính xác sản phẩm nào bị trả. Không thể phân bổ refund chính xác theo product nếu không có mapping refund_line hoặc allocation policy.

Có thể báo net revenue ở cấp order/customer; muốn báo theo product thì cần dữ liệu phân bổ theo line hoặc quy tắc phân bổ được kế toán chấp nhận.

### 9.2. Refund đang chờ duyệt

Nếu chỉ tính refund đã APPROVED, hãy lọc trạng thái trước khi aggregate. Không cộng mọi yêu cầu refund đã tạo nhưng bị từ chối hoặc còn pending.

## 10. Báo cáo order-level không JOIN chi tiết khi không cần

Nếu cần tổng order_total theo khách hàng, chỉ cần bảng sales_order:

~~~sql
SELECT
    customer_id,
    currency_code,
    COUNT(*) AS order_count,
    SUM(order_total) AS order_total
FROM sales_order
WHERE order_status = 'COMPLETED'
GROUP BY customer_id, currency_code;
~~~

Không JOIN sales_order_line nếu query không cần thuộc tính ở line.

Nếu muốn chỉ lấy đơn có ít nhất một line, dùng EXISTS:

~~~sql
SELECT
    o.customer_id,
    o.currency_code,
    COUNT(*) AS order_count,
    SUM(o.order_total) AS order_total
FROM sales_order o
WHERE o.order_status = 'COMPLETED'
  AND EXISTS (
      SELECT 1
      FROM sales_order_line l
      WHERE l.order_id = o.order_id
  )
GROUP BY o.customer_id, o.currency_code;
~~~

EXISTS chỉ kiểm tra sự tồn tại, không tạo một hàng cho mỗi line.

### 10.1. Dùng DISTINCT order IDs như một tập trung gian

Có thể tạo tập order IDs thỏa điều kiện từ bảng con:

~~~sql
WITH eligible_orders AS (
    SELECT DISTINCT order_id
    FROM sales_order_line
    WHERE product_id = 'P-A'
)
SELECT
    o.customer_id,
    SUM(o.order_total) AS order_total
FROM sales_order o
JOIN eligible_orders e
    ON e.order_id = o.order_id
GROUP BY o.customer_id;
~~~

Ở đây DISTINCT được dùng đúng mục đích: tạo tập khóa duy nhất trước khi JOIN. Nó không được dùng để sửa SUM sau khi đã fan-out.

## 11. Báo cáo doanh thu theo khách hàng

Khi tính net merchandise revenue theo customer, tổng hợp line và refund ở order grain trước:

~~~sql
WITH line_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - line_discount) AS merchandise_net
    FROM sales_order_line
    GROUP BY order_id
),
refund_totals AS (
    SELECT
        r.order_id,
        SUM(rl.refund_amount) AS merchandise_refunded
    FROM refund r
    JOIN refund_line rl
        ON rl.refund_id = r.refund_id
    WHERE r.refund_status = 'APPROVED'
    GROUP BY r.order_id
),
order_revenue AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.currency_code,
        COALESCE(lt.merchandise_net, 0)
          - COALESCE(rt.merchandise_refunded, 0) AS net_revenue
    FROM sales_order o
    LEFT JOIN line_totals lt
        ON lt.order_id = o.order_id
    LEFT JOIN refund_totals rt
        ON rt.order_id = o.order_id
    WHERE o.order_status = 'COMPLETED'
)
SELECT
    customer_id,
    currency_code,
    SUM(net_revenue) AS net_merchandise_revenue
FROM order_revenue
GROUP BY customer_id, currency_code;
~~~

Kết quả:
- C01: 130.000 VND.
- C02: không có đơn hoàn thành nên không xuất hiện trong báo cáo này.

Nếu cần hiển thị cả khách chưa có doanh thu, bắt đầu từ bảng customer rồi LEFT JOIN một CTE đã aggregate theo customer; đừng JOIN raw order lines vào customer rồi SUM header totals.

## 12. Báo cáo theo sản phẩm

Báo cáo theo sản phẩm có grain khác: một dòng cho mỗi product/currency.

Ta có thể tính line net ở line grain vì mỗi dòng hàng chỉ xuất hiện một lần nếu chỉ JOIN các bảng một-một hoặc many-to-one phù hợp.

~~~sql
SELECT
    l.product_id,
    o.currency_code,
    SUM(l.quantity * l.unit_price - l.line_discount) AS merchandise_net
FROM sales_order o
JOIN sales_order_line l
    ON l.order_id = o.order_id
WHERE o.order_status = 'COMPLETED'
GROUP BY l.product_id, o.currency_code;
~~~

Kết quả trước refund:
- P-A: 54.000 VND.
- P-B: 36.000 VND.
- P-C: 50.000 VND.

Đây là **gross-after-discount line revenue trước returns/refunds**. Đơn 102 bị loại vì CANCELLED.

### 12.1. Trừ refund theo sản phẩm

Muốn tính net product revenue sau refund, cần phân bổ refund vào từng line. CTE refund_by_line:

~~~sql
WITH refund_by_line AS (
    SELECT
        rl.line_id,
        SUM(rl.refund_amount) AS refunded_amount
    FROM refund r
    JOIN refund_line rl
        ON rl.refund_id = r.refund_id
    WHERE r.refund_status = 'APPROVED'
    GROUP BY rl.line_id
)
SELECT
    l.product_id,
    o.currency_code,
    SUM(
        l.quantity * l.unit_price
        - l.line_discount
        - COALESCE(rbl.refunded_amount, 0)
    ) AS net_merchandise_revenue
FROM sales_order o
JOIN sales_order_line l
    ON l.order_id = o.order_id
LEFT JOIN refund_by_line rbl
    ON rbl.line_id = l.line_id
WHERE o.order_status = 'COMPLETED'
GROUP BY l.product_id, o.currency_code;
~~~

Kết quả:
- P-A: 44.000 VND (54.000 − 10.000).
- P-B: 36.000 VND.
- P-C: 50.000 VND.

Mỗi line chỉ JOIN với tối đa một hàng refund_by_line do đã GROUP BY line_id.

### 12.2. Không JOIN raw payment vào báo cáo product

Nếu thêm payment trực tiếp vào query product, mỗi line có thể lặp theo số payment. Product revenue sẽ bị nhân. Nếu cần hiển thị payment metrics, aggregate payment theo order hoặc báo ở query/section riêng.

## 13. Báo cáo theo tháng hoặc ngày ghi nhận

Giả sử báo cáo theo recognized_at. Hãy xác định timezone báo cáo và tính biên start/end trước. Sau đó lọc order ở header grain:

~~~sql
WITH line_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price - line_discount) AS merchandise_net
    FROM sales_order_line
    GROUP BY order_id
),
refund_totals AS (
    SELECT
        r.order_id,
        SUM(rl.refund_amount) AS merchandise_refunded
    FROM refund r
    JOIN refund_line rl
        ON rl.refund_id = r.refund_id
    WHERE r.refund_status = 'APPROVED'
    GROUP BY r.order_id
),
order_revenue AS (
    SELECT
        o.order_id,
        o.currency_code,
        o.recognized_at,
        COALESCE(lt.merchandise_net, 0)
          - COALESCE(rt.merchandise_refunded, 0) AS net_revenue
    FROM sales_order o
    LEFT JOIN line_totals lt
        ON lt.order_id = o.order_id
    LEFT JOIN refund_totals rt
        ON rt.order_id = o.order_id
    WHERE o.order_status = 'COMPLETED'
      AND o.recognized_at >= :start_instant
      AND o.recognized_at < :end_instant
)
SELECT
    currency_code,
    SUM(net_revenue) AS net_revenue
FROM order_revenue
GROUP BY currency_code;
~~~

Nếu cần nhóm theo tháng, có thể group theo month bucket sau khi lọc đúng khoảng. Hàm lấy tháng khác nhau giữa DBMS; không dùng một cú pháp date_trunc cho mọi hệ.

### 13.1. Không dùng ngày đặt đơn nếu metric dựa trên ngày ghi nhận

Một đơn đặt 31/12 nhưng giao/ghi nhận 02/01 có thể thuộc kỳ doanh thu tháng 1 theo chính sách. Nếu query dùng ordered_at thay recognized_at, báo cáo lệch kỳ.

### 13.2. Refund theo ngày refund hay ngày doanh thu?

Hai báo cáo khác nhau:
- Doanh thu thuần theo ngày ghi nhận: phân bổ refund vào kỳ doanh thu gốc hoặc kỳ điều chỉnh theo chính sách.
- Tiền hoàn theo ngày hoàn: nhóm refund theo refunded_at.

Không gộp hai timeline vào một chỉ tiêu nếu chưa định nghĩa accounting policy.

## 14. Payment: nhiều giao dịch không phải nhiều doanh thu

Một đơn có thể có:
- Authorization.
- Capture.
- Partial capture.
- Retry sau lỗi.
- Void.
- Chargeback.
- Refund.
- Settlement adjustment.

Không SUM tất cả payment.amount rồi gọi là tiền đã thu.

Ví dụ:
- AUTHORIZED 104.000: chỉ giữ tiền, chưa chắc đã thu.
- CAPTURED 60.000.
- CAPTURED 44.000.
- FAILED 104.000 từ lần thử cũ.
- VOIDED 104.000.

Chỉ cộng trạng thái và loại giao dịch theo định nghĩa cash collection. Nếu payment table lưu event ledger, cần biết mỗi hàng là attempt, state transition hay transaction cuối cùng; không cộng lặp nhiều trạng thái của cùng một payment.

### 14.1. Một dòng payment có thể cập nhật trạng thái hay append event?

Nếu bảng lưu một hàng/payment và status được cập nhật, lọc status hiện tại có thể đủ.

Nếu bảng lưu event append-only:
- CREATED.
- AUTHORIZED.
- CAPTURED.
- REVERSED.

thì cộng tất cả event amount sẽ nhân tiền. Cần chọn event cuối, trạng thái cuối hoặc ledger entries có dấu +/- theo mô hình kế toán.

### 14.2. Tách cash report khỏi revenue report

Cash report có thể là:

~~~sql
WITH captured AS (
    SELECT order_id, SUM(amount) AS captured_amount
    FROM payment
    WHERE payment_status = 'CAPTURED'
    GROUP BY order_id
),
refunded AS (
    SELECT order_id, SUM(refund_total) AS refunded_amount
    FROM refund
    WHERE refund_status = 'APPROVED'
    GROUP BY order_id
)
SELECT
    o.currency_code,
    SUM(COALESCE(c.captured_amount, 0)) AS captured,
    SUM(COALESCE(r.refunded_amount, 0)) AS refunded,
    SUM(COALESCE(c.captured_amount, 0)
      - COALESCE(r.refunded_amount, 0)) AS net_cash
FROM sales_order o
LEFT JOIN captured c ON c.order_id = o.order_id
LEFT JOIN refunded r ON r.order_id = o.order_id
GROUP BY o.currency_code;
~~~

Không JOIN raw lines vào báo cáo cash nếu không cần thuộc tính line.

## 15. Discount, tax và shipping: tránh trừ/cộng hai lần

Một order total thường có thể được tính:

~~~text
subtotal_gross
- discount_total
+ tax_total
+ shipping_total
= order_total
~~~

Nhưng hệ thống thực tế có thể có:
- Discount ở line.
- Coupon cấp đơn.
- Store credit.
- Gift card.
- Tax inclusive hoặc exclusive.
- Shipping discount.
- Shipping tax.
- Tip.
- Surcharge.
- Rounding adjustment.

### 15.1. Discount cấp đơn

Nếu discount 10.000 được lưu ở header và line_discount chưa phân bổ:
- Net merchandise ở line = tổng gross line.
- Trừ order discount một lần ở order grain.
- Không trừ discount_total ở header rồi lại trừ nó ở từng line.

Nếu báo cáo theo product, phải có allocation rule, ví dụ phân bổ theo tỷ trọng gross line và xử lý rounding remainder. Không thể biết chính xác product nào được giảm bao nhiêu nếu dữ liệu không lưu phân bổ.

### 15.2. Tax

Tax thường không được coi là merchandise revenue trong metric mẫu. Nếu order_total đã gồm tax mà báo cáo doanh thu lại cộng order_total, có thể đang cộng tax vào doanh thu.

Tax có thể nhiều dòng theo jurisdiction/rate. Nếu join bảng tax_line vào order_line, lại tạo fan-out. Aggregate tax theo order hoặc line trước khi join.

### 15.3. Shipping

Shipping là phí thu của khách, có thể là revenue/contra-expense tùy accounting policy. Đừng tự động cộng shipping_total vào merchandise revenue.

### 15.4. Rounding

Nếu discount phân bổ theo tỷ lệ, tổng từng line có thể lệch 0,01 so với order discount do rounding. Cần quy tắc:
- Precision nội bộ.
- Scale khi lưu.
- Rounding mode.
- Dòng nhận phần dư.
- Đối soát header và lines.

## 16. Khi JOIN bảng phụ như tag, shipment, promotion

Fan-out không chỉ xảy ra với payments.

Ví dụ một order có:
- 2 lines.
- 3 tags.
- 2 shipments.

JOIN cả ba bảng có thể tạo 2×3×2 = 12 dòng. Nếu SUM line net sau join, doanh thu bị nhân 6 lần.

Các bảng thường tạo fan-out:
- Product categories nhiều cấp.
- Tags.
- Promotion usage.
- Shipment packages.
- Audit events.
- Status history.
- Notes/attachments.
- Multiple addresses.
- Order-to-campaign mapping.

Trước khi JOIN, hỏi:
1. Bảng này có bao nhiêu hàng cho mỗi khóa hiện tại?
2. Join key có UNIQUE ở phía được kỳ vọng one-to-one không?
3. Tôi cần dữ liệu con hay chỉ cần biết có tồn tại?
4. Nếu cần số liệu, tôi đã aggregate đúng grain chưa?
5. Nếu là many-to-many, metric có cần phân bổ không?

## 17. Dùng EXISTS thay vì JOIN khi chỉ kiểm tra điều kiện

Muốn đếm tổng order_total của đơn có ít nhất một shipment:

~~~sql
SELECT SUM(o.order_total) AS shipped_order_total
FROM sales_order o
WHERE o.order_status = 'COMPLETED'
  AND EXISTS (
      SELECT 1
      FROM shipment s
      WHERE s.order_id = o.order_id
        AND s.shipment_status = 'SHIPPED'
  );
~~~

Nếu một đơn có ba shipment, EXISTS vẫn giữ đơn đó một lần.

Cách JOIN trực tiếp:

~~~sql
SELECT SUM(o.order_total)
FROM sales_order o
JOIN shipment s ON s.order_id = o.order_id
WHERE s.shipment_status = 'SHIPPED';
~~~

sẽ cộng order_total một lần cho mỗi shipment khớp.

### 17.1. NOT EXISTS

Muốn tìm đơn chưa có refund:

~~~sql
SELECT o.order_id, o.order_total
FROM sales_order o
WHERE NOT EXISTS (
    SELECT 1
    FROM refund r
    WHERE r.order_id = o.order_id
      AND r.refund_status = 'APPROVED'
);
~~~

Không cần LEFT JOIN rồi GROUP BY/HAVING nếu mục đích chỉ là kiểm tra không có hàng con.

## 18. LEFT JOIN và NULL

LEFT JOIN giữ hàng cha dù không có hàng con. Các cột phía bảng con sẽ là NULL.

Ví dụ order chưa có payment:

~~~sql
SELECT
    o.order_id,
    COALESCE(p.captured_amount, 0) AS captured_amount
FROM sales_order o
LEFT JOIN (
    SELECT order_id, SUM(amount) AS captured_amount
    FROM payment
    WHERE payment_status = 'CAPTURED'
    GROUP BY order_id
) p ON p.order_id = o.order_id;
~~~

### 18.1. Đặt điều kiện ở ON hay WHERE

Hai câu không tương đương:

~~~sql
SELECT o.order_id, p.amount
FROM sales_order o
LEFT JOIN payment p
    ON p.order_id = o.order_id
   AND p.payment_status = 'CAPTURED';
~~~

và:

~~~sql
SELECT o.order_id, p.amount
FROM sales_order o
LEFT JOIN payment p
    ON p.order_id = o.order_id
WHERE p.payment_status = 'CAPTURED';
~~~

Ở câu thứ hai, WHERE loại các hàng có p.payment_status NULL, khiến LEFT JOIN hoạt động giống INNER JOIN với điều kiện đó. Nếu muốn giữ đơn chưa thanh toán, lọc payment trong ON hoặc subquery/CTE trước khi JOIN.

### 18.2. COALESCE không sửa fan-out

COALESCE(NULL,0) chỉ thay NULL bằng 0. Nó không làm giảm số dòng hoặc khử phép nhân do JOIN.

### 18.3. COUNT(*) và COUNT(child_id)

Sau LEFT JOIN:
- COUNT(*) đếm cả hàng cha không có con (hàng mở rộng NULL vẫn tồn tại).
- COUNT(child_id) bỏ qua NULL, nên đếm hàng con có thật.

Nếu có nhiều bảng con cùng JOIN, COUNT(child_id) vẫn có thể bị lặp theo bảng con còn lại.

## 19. Tổng hợp nhiều bảng con theo cùng một grain

Một mẫu dễ bảo trì:

~~~sql
WITH
line_by_order AS (
    SELECT order_id,
           SUM(quantity * unit_price - line_discount) AS line_net
    FROM sales_order_line
    GROUP BY order_id
),
payment_by_order AS (
    SELECT order_id,
           SUM(amount) AS captured
    FROM payment
    WHERE payment_status = 'CAPTURED'
    GROUP BY order_id
),
refund_by_order AS (
    SELECT order_id,
           SUM(refund_total) AS refunded
    FROM refund
    WHERE refund_status = 'APPROVED'
    GROUP BY order_id
),
shipment_by_order AS (
    SELECT order_id,
           COUNT(*) AS shipment_count
    FROM shipment
    WHERE shipment_status = 'SHIPPED'
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.currency_code,
    o.order_total,
    COALESCE(l.line_net, 0) AS line_net,
    COALESCE(p.captured, 0) AS captured,
    COALESCE(r.refunded, 0) AS refunded,
    COALESCE(s.shipment_count, 0) AS shipment_count
FROM sales_order o
LEFT JOIN line_by_order l ON l.order_id = o.order_id
LEFT JOIN payment_by_order p ON p.order_id = o.order_id
LEFT JOIN refund_by_order r ON r.order_id = o.order_id
LEFT JOIN shipment_by_order s ON s.order_id = o.order_id;
~~~

Mỗi CTE có grain rõ: một hàng/order. Kết quả final cũng một hàng/order.

Nếu cần thêm cột vào CTE, bảo đảm GROUP BY không làm nó trở thành nhiều hàng/order. Nếu cần payment method breakdown, có thể dùng conditional aggregation để giữ một hàng/order.

## 20. Conditional aggregation

Muốn báo cáo số tiền captured theo CARD và BANK:

~~~sql
SELECT
    order_id,
    SUM(CASE WHEN payment_type = 'CARD'
             THEN amount ELSE 0 END) AS card_captured,
    SUM(CASE WHEN payment_type = 'BANK'
             THEN amount ELSE 0 END) AS bank_captured
FROM payment
WHERE payment_status = 'CAPTURED'
GROUP BY order_id;
~~~

Một hàng/order, nhiều metric ở các cột.

Có thể nối CTE này với sales_order mà không tạo thêm fan-out.

Nếu dùng FILTER (WHERE ...) của PostgreSQL hoặc cú pháp riêng của DBMS, cần dialect adapter; CASE WHEN thường dễ chuyển hơn.

## 21. Window functions có thể giúp gì và không giúp gì?

Window function tính trên các hàng hiện có nhưng **không tự giảm số hàng**.

Ví dụ:

~~~sql
SELECT
    o.order_id,
    o.order_total,
    SUM(o.order_total) OVER (PARTITION BY o.order_id) AS repeated_total
FROM sales_order o
JOIN sales_order_line l
    ON l.order_id = o.order_id;
~~~

Với đơn có hai line, order_total vẫn xuất hiện trên hai hàng. Window SUM theo partition còn nhân nó lên hai lần trong mỗi hàng. Nếu sau đó SUM tiếp repeated_total, lỗi lớn hơn.

### 21.1. ROW_NUMBER để chọn một đại diện

Có thể dùng ROW_NUMBER để đánh số hàng trong mỗi order và chọn rn=1 trước khi cộng header totals, nhưng cần rất cẩn thận:
- Partition/order by phải xác định ổn định.
- Không được có thêm bảng con khác nhân dòng sau bước đó.
- Cần phân biệt metric ở header grain và line grain.
- Cách này không thay thế pre-aggregation dễ đọc.

### 21.2. Window cho running totals

Window rất hữu ích sau khi đã tạo một dòng mỗi ngày hoặc mỗi khách:

~~~sql
WITH daily_revenue AS (
    SELECT business_date, currency_code, SUM(net_revenue) AS revenue
    FROM order_revenue_by_order
    GROUP BY business_date, currency_code
)
SELECT
    business_date,
    currency_code,
    revenue,
    SUM(revenue) OVER (
        PARTITION BY currency_code
        ORDER BY business_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM daily_revenue;
~~~

Window ở đây chạy trên grain ngày/currency đã đúng, không phải raw join nhiều bảng con.

## 22. Nhiều currency: không cộng VND với USD

Nếu bảng chứa nhiều currency, GROUP BY currency_code:

~~~sql
SELECT currency_code, SUM(order_total)
FROM sales_order
WHERE order_status = 'COMPLETED'
GROUP BY currency_code;
~~~

Không cộng trực tiếp các giá trị khác currency thành một tổng không có ý nghĩa.

Nếu cần quy đổi:
- Lưu exchange rate.
- Chốt nguồn tỷ giá.
- Chốt thời điểm áp dụng (order time, invoice time, recognition date).
- Chốt base currency.
- Chốt rounding.
- Xác định rate khi refund khác ngày bán.
- Lưu amount_original, currency_original và amount_reporting/base currency nếu cần audit.

Không JOIN bảng tỷ giá có nhiều dòng/ngày vào đơn mà không chọn đúng một rate; nếu mỗi order khớp nhiều rate, lại tạo fan-out.

## 23. Báo cáo có cả header total và product rows

Một câu hỏi khó: muốn mỗi dòng sản phẩm có cột order_total để hiển thị, rồi ở cuối báo cáo SUM order_total.

Nếu một order có 3 products, order_total xuất hiện 3 lần. Có ba lựa chọn:

1. Báo cáo line-level chỉ có line metrics; tổng order-level đặt ở báo cáo riêng.
2. Phân bổ order_total vào line theo quy tắc rõ ràng, ví dụ tỷ trọng line net; tổng phân bổ bằng order_total.
3. Hiển thị order_total lặp trên các line nhưng đánh dấu rõ đó là informational repeated value và không SUM ở tầng báo cáo.

Không thể vừa lặp nguyên header total trên mỗi product line vừa cộng cột đó như tổng đơn.

### 23.1. Ví dụ phân bổ theo tỷ trọng

Đơn 100:
- Line P-A net 54.000.
- Line P-B net 36.000.
- Merchandise net 90.000.
- Order total 104.000.

Nếu cần phân bổ order_total theo tỷ trọng line net:
- P-A: 104.000 × 54.000/90.000 = 62.400.
- P-B: 104.000 × 36.000/90.000 = 41.600.

Tổng = 104.000.

Đây là allocation phục vụ báo cáo, không có nghĩa P-A thực sự tạo ra 62.400 merchandise revenue; phần chênh có thể chứa tax/shipping. Tên metric phải nói rõ “allocated order total”.

### 23.2. Rounding remainder

Nếu phân bổ ra nhiều dòng có số lẻ, rounding từng dòng có thể làm tổng lệch. Cần phân bổ phần dư cho một dòng theo quy tắc xác định và kiểm thử tổng phân bổ = tổng nguồn.

## 24. Đối soát header với line totals

Một bước quan trọng là tìm đơn có header subtotal không khớp chi tiết.

~~~sql
WITH line_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS gross_from_lines,
        SUM(line_discount) AS discount_from_lines,
        SUM(quantity * unit_price - line_discount) AS net_from_lines,
        COUNT(*) AS line_count
    FROM sales_order_line
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.subtotal_gross,
    o.discount_total,
    COALESCE(lt.gross_from_lines, 0) AS gross_from_lines,
    COALESCE(lt.discount_from_lines, 0) AS discount_from_lines,
    COALESCE(lt.net_from_lines, 0) AS net_from_lines,
    COALESCE(lt.line_count, 0) AS line_count
FROM sales_order o
LEFT JOIN line_totals lt
    ON lt.order_id = o.order_id
WHERE o.subtotal_gross <> COALESCE(lt.gross_from_lines, 0)
   OR o.discount_total <> COALESCE(lt.discount_from_lines, 0);
~~~

Nếu schema cho phép NULL ở monetary fields, cần xác định NULL là unknown hay zero trước khi dùng COALESCE. Không tự động coi NULL là 0 nếu dữ liệu chưa hoàn chỉnh.

### 24.1. Sai lệch có thể hợp lệ

Header có thể bao gồm:
- Order-level coupon chưa phân bổ.
- Rounding.
- Bundle discount.
- Manual adjustment.
- Shipping/tax.
- Sản phẩm tặng giá 0.
- Snapshot giá tại thời điểm mua.

Do đó, query đối soát cần biết business contract; không phải mọi chênh lệch đều là lỗi kỹ thuật.

## 25. Đối soát order total với payment

Có thể tổng hợp captured payment theo order:

~~~sql
WITH payment_totals AS (
    SELECT
        order_id,
        SUM(CASE WHEN payment_status = 'CAPTURED'
                 THEN amount ELSE 0 END) AS captured_total
    FROM payment
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.order_total,
    COALESCE(p.captured_total, 0) AS captured_total,
    o.order_total - COALESCE(p.captured_total, 0) AS balance_difference
FROM sales_order o
LEFT JOIN payment_totals p
    ON p.order_id = o.order_id
WHERE o.order_status = 'COMPLETED';
~~~

Chênh lệch có thể do:
- Chưa thu đủ.
- Thanh toán thừa.
- Store credit/gift card.
- Partial capture.
- Payment pending.
- Chargeback/void.
- Refund được ghi riêng.

Không đặt giả định order_total luôn bằng tổng payment rows trong mọi thời điểm.

## 26. Anti-pattern: GROUP BY sai grain

Ví dụ:

~~~sql
SELECT
    o.customer_id,
    o.order_id,
    SUM(o.order_total) AS total
FROM sales_order o
JOIN sales_order_line l ON l.order_id = o.order_id
GROUP BY o.customer_id, o.order_id;
~~~

Vẫn sai vì mỗi order_total bị lặp theo số line trước khi GROUP BY. Grouping không tự xóa duplicate.

Đúng nếu chỉ cần order total:

~~~sql
SELECT customer_id, order_id, order_total
FROM sales_order;
~~~

Hoặc tổng hợp ở order grain rồi group customer:

~~~sql
SELECT customer_id, SUM(order_total)
FROM sales_order
WHERE order_status = 'COMPLETED'
GROUP BY customer_id;
~~~

### 26.1. GROUP BY tất cả cột header

GROUP BY o.order_id, o.order_total, ... vẫn không sửa SUM header total nếu JOIN con có nhiều hàng; SUM sẽ cộng nhiều bản sao trong từng group.

Nếu chỉ muốn lấy header fields sau aggregate, hãy aggregate bảng con trước rồi JOIN.

## 27. Index và hiệu năng

Pre-aggregation không chỉ đúng mà thường giúp query planner xử lý tập dữ liệu có cấu trúc hơn. Các index hữu ích tùy workload:

- sales_order(order_status, recognized_at, currency_code).
- sales_order_line(order_id).
- sales_order_line(line_id) là PK và refund_line(line_id) để lookup.
- payment(order_id, payment_status).
- refund(order_id, refund_status).
- refund_line(refund_id, line_id).

Thứ tự cột index phụ thuộc filter, selectivity, join và DBMS. Không tạo tất cả index chỉ vì thấy tên trong ví dụ.

### 27.1. Filter trước khi aggregate

Nếu báo cáo chỉ lấy đơn trong một kỳ, có thể lọc order IDs trước rồi aggregate line/payment/refund cho các order đó. Điều này giảm lượng dữ liệu cần quét khi bảng lớn.

Một mẫu:

~~~sql
WITH eligible_orders AS (
    SELECT order_id, customer_id, currency_code
    FROM sales_order
    WHERE order_status = 'COMPLETED'
      AND recognized_at >= :start_at
      AND recognized_at < :end_at
),
line_totals AS (
    SELECT
        l.order_id,
        SUM(l.quantity * l.unit_price - l.line_discount) AS line_net
    FROM sales_order_line l
    JOIN eligible_orders e ON e.order_id = l.order_id
    GROUP BY l.order_id
)
SELECT ...
~~~

CTE không nhất thiết luôn materialize; optimizer của DBMS có thể inline/rewrite. Đọc execution plan thay vì giả định CTE luôn là temporary table.

### 27.2. Kiểm tra EXPLAIN

Tìm:
- Full table scan ngoài ý muốn.
- Join cardinality estimate sai.
- Hash join/sort spill.
- Aggregate sau fan-out với lượng dòng lớn.
- Index range scan phù hợp.
- Partition pruning.
- Row count ước lượng so với thực tế.

Tùy DBMS, dùng EXPLAIN, EXPLAIN ANALYZE, Actual Execution Plan hoặc công cụ tương đương. Chạy trên dữ liệu gần production.

## 28. CTE hay derived table?

Cả hai cách đều có thể pre-aggregate.

CTE:

~~~sql
WITH line_totals AS (
    SELECT order_id, SUM(quantity * unit_price - line_discount) AS line_net
    FROM sales_order_line
    GROUP BY order_id
)
SELECT ...
~~~

Derived table:

~~~sql
SELECT ...
FROM sales_order o
LEFT JOIN (
    SELECT order_id,
           SUM(quantity * unit_price - line_discount) AS line_net
    FROM sales_order_line
    GROUP BY order_id
) lt
    ON lt.order_id = o.order_id;
~~~

Chọn cách giúp người đọc nhìn rõ grain. CTE hữu ích khi có nhiều nguồn aggregate hoặc cần tái sử dụng trong cùng statement. Derived table gọn cho một phép tổng hợp đơn.

## 29. Cú pháp đa DBMS

Các ví dụ CTE, GROUP BY, SUM, CASE, EXISTS và LEFT JOIN trong bài thường có trên PostgreSQL, MySQL hiện đại, SQL Server, Oracle và SQLite hiện đại. Nhưng cần chú ý:

- MySQL cần phiên bản hỗ trợ CTE (8.0+).
- SQLite cần runtime hỗ trợ CTE/window features tương ứng.
- Oracle có thể yêu cầu kiểu NUMBER/VARCHAR2 và quy tắc alias/CTE riêng.
- SQL Server dùng kiểu datetime2/decimal và tên schema thường có dbo.
- Identity/auto-increment DDL khác nhau.
- Date bucket functions khác nhau.
- Placeholder bind khác theo JDBC/driver, không đặt trực tiếp :name vào PreparedStatement nếu driver không hỗ trợ named parameters.

### 29.1. Không dùng SELECT alias trong GROUP BY một cách mù quáng

Một số DBMS cho phép GROUP BY alias, một số hạn chế hoặc có quy tắc khác. Để portable, lặp biểu thức hoặc tạo CTE/subquery trước rồi group theo cột đã đặt tên.

### 29.2. Boolean/status

Ví dụ dùng order_status VARCHAR để dễ đọc. Nếu DBMS/schema dùng ENUM, native boolean hoặc integer flag, điều chỉnh predicate theo kiểu thật; đừng so chuỗi nếu cột là boolean/numeric.

## 30. Báo cáo ngày: lọc đúng khoảng và đúng timezone

Khi nhóm doanh thu theo ngày, xác định ngày là:
- Ngày đặt hàng.
- Ngày hoàn thành.
- Ngày ghi nhận doanh thu.
- Ngày capture payment.
- Ngày refund.

Chọn một cột timestamp phù hợp với metric. Tính start/end theo timezone báo cáo rồi lọc khoảng nửa mở:

~~~sql
WHERE recognized_at >= :start_instant
  AND recognized_at < :end_instant
~~~

Không dùng BETWEEN với end-of-day 23:59:59.999 vì precision cột khác nhau và dễ đếm trùng nửa đêm.

Nếu cột là timestamp không timezone nhưng quy ước UTC, bind và đọc theo UTC nhất quán. Nếu cột có timezone semantics, kiểm tra session timezone/driver.

### 30.1. Group by ngày

Có thể tạo CTE order_revenue_by_order trước, rồi nhóm theo business date do ứng dụng tính hoặc biểu thức DBMS được chỉ định timezone rõ ràng. Không để session timezone ngầm quyết định ngày báo cáo.

### 30.2. Refund khác kỳ

Nếu đơn ghi nhận tháng 10 nhưng refund xảy ra tháng 11:
- Báo cáo doanh thu tháng 10 theo net lifetime có thể trừ refund về đơn gốc.
- Báo cáo adjustment tháng 11 có thể ghi refund vào tháng 11.
- Cash report ghi theo ngày tiền hoàn.

Đây là policy kế toán; SQL chỉ thực thi policy đã được xác định.

## 31. Các trường hợp biên cần có trong fixture

Ít nhất hãy thêm:
1. Đơn có 1 line, 1 payment, 0 refund.
2. Đơn có nhiều line, nhiều payment, nhiều refund.
3. Đơn có line nhưng chưa thanh toán.
4. Đơn có payment attempt thất bại và một capture thành công.
5. Đơn bị hủy.
6. Đơn hoàn toàn bộ.
7. Đơn hoàn một phần.
8. Đơn có shipping/tax refund nhưng không hoàn hàng.
9. Đơn có discount cấp đơn chưa phân bổ.
10. Hai đơn có order_total bằng nhau.
11. Hai line có line_net bằng nhau.
12. Một đơn không có line do dữ liệu lỗi.
13. Refund pending/rejected.
14. Payment authorized/voided/chargeback.
15. Đơn ở currency khác.
16. Đơn sát biên ngày báo cáo.
17. Một product xuất hiện ở nhiều order.
18. Một order có nhiều shipment/tag/promotion.

Fixture phải có expected result cho từng metric, không chỉ kiểm tra query chạy thành công.

## 32. Quy trình debug khi tổng doanh thu tăng bất thường

Khi báo cáo cao gấp đôi hoặc nhiều hơn:

**Bước 1 — Kiểm tra grain.** Đếm số hàng của từng bảng theo order_id.

~~~sql
SELECT order_id, COUNT(*) AS line_count
FROM sales_order_line
GROUP BY order_id;
~~~

Lặp với payment, refund, shipment.

**Bước 2 — Đếm sau từng JOIN.** So tổng số hàng và số distinct order_id trước/sau mỗi JOIN.

**Bước 3 — Tìm order có fan-out lớn.** So row count của joined result theo order_id.

**Bước 4 — Tính hệ số nhân.** Với mỗi order, so số rows join với số lines/payments/refunds thực tế.

**Bước 5 — Đối soát từng metric.** So line totals với header, captured với payment ledger, refund với refund ledger.

**Bước 6 — Tách truy vấn.** Aggregate từng nguồn ở grain cần thiết rồi JOIN.

**Bước 7 — Kiểm tra status/time/currency.** Đảm bảo cùng metric definition.

**Bước 8 — Chạy fixture concurrency và production-like data.** Đọc execution plan, không chỉ so tổng một mẫu nhỏ.

### 32.1. Truy vấn tìm fan-out

~~~sql
SELECT
    order_id,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT line_id) AS distinct_lines,
    COUNT(DISTINCT payment_id) AS distinct_payments
FROM joined_order_result
GROUP BY order_id;
~~~

joined_order_result là CTE/view truy vấn đang nghi ngờ. Nếu joined_rows lớn hơn nhiều so với từng distinct child count, có thể đang có tích Descartes giữa các quan hệ con.

## 33. Bài tập thực hành có đáp án

Các bài tập dựa trên fixture ở mục 5 và metric đã định nghĩa. Khi làm trên schema riêng, hãy ghi rõ grain và expected totals.

### Bài 1 — Grain của header

Một hàng sales_order đại diện cho điều gì?

<details>
<summary>Đáp án</summary>

Một đơn hàng. Vì vậy order_total ở grain order, mỗi order_id chỉ nên đóng góp một lần vào tổng order-level.

</details>

### Bài 2 — Grain của line

Một đơn có 4 sản phẩm khác nhau. Bảng sales_order_line có bao nhiêu hàng?

<details>
<summary>Đáp án</summary>

Bốn hàng nếu mỗi sản phẩm được biểu diễn một dòng; số lượng sản phẩm không làm thay đổi grain.

</details>

### Bài 3 — Fan-out đơn giản

Một order có 3 lines và 2 payments. JOIN hai bảng con theo order_id tạo bao nhiêu tổ hợp?

<details>
<summary>Đáp án</summary>

3 × 2 = 6 rows nếu cả hai tập đều có các hàng đó.

</details>

### Bài 4 — Header total bị nhân

Order total là 100.000, có 3 lines và 2 payments. SUM(order_total) sau JOIN thô là bao nhiêu?

<details>
<summary>Đáp án</summary>

600.000 vì giá trị header lặp 6 lần. Tổng đúng ở order grain là 100.000.

</details>

### Bài 5 — Line total bị nhân

Tổng line net là 90.000, order có 2 payments. JOIN lines với payments rồi SUM line net cho kết quả bao nhiêu?

<details>
<summary>Đáp án</summary>

180.000, vì mỗi line xuất hiện một lần cho mỗi payment. Tổng line đúng là 90.000.

</details>

### Bài 6 — COUNT DISTINCT

COUNT(DISTINCT order_id) có sửa SUM(order_total) bị lặp không?

<details>
<summary>Đáp án</summary>

Không. DISTINCT chỉ áp dụng cho phép đếm đó; SUM vẫn nhìn thấy mọi hàng sau JOIN.

</details>

### Bài 7 — SUM DISTINCT

Hai đơn khác nhau cùng order_total 50.000. SUM(DISTINCT order_total) cho bao nhiêu?

<details>
<summary>Đáp án</summary>

50.000 thay vì 100.000. Nó gộp hai giá trị bằng nhau dù thuộc hai đơn riêng.

</details>

### Bài 8 — Dữ liệu mẫu

Net merchandise của order 100 trước refund là bao nhiêu?

<details>
<summary>Đáp án</summary>

54.000 + 36.000 = 90.000.

</details>

### Bài 9 — Net revenue toàn bộ

Hai đơn COMPLETED có line net 90.000 và 50.000; merchandise refund đã duyệt 10.000. Net merchandise revenue là bao nhiêu?

<details>
<summary>Đáp án</summary>

90.000 + 50.000 − 10.000 = 130.000.

</details>

### Bài 10 — Order total

Order total của hai đơn hoàn thành trong fixture là bao nhiêu?

<details>
<summary>Đáp án</summary>

104.000 + 55.000 = 159.000.

</details>

### Bài 11 — Net cash

Captured payments là 159.000 và refund là 10.000. Net cash là bao nhiêu?

<details>
<summary>Đáp án</summary>

149.000. Đây là cash metric, không phải net merchandise revenue.

</details>

### Bài 12 — Đơn bị hủy

Order 102 có line net 20.000 nhưng status CANCELLED. Nó có được tính vào metric mẫu không?

<details>
<summary>Đáp án</summary>

Không, vì metric quy định chỉ lấy COMPLETED. Cần dùng đúng trạng thái nghiệp vụ.

</details>

### Bài 13 — Pre-aggregation

Muốn JOIN payment với order mà vẫn một hàng/order, phải GROUP BY theo khóa nào?

<details>
<summary>Đáp án</summary>

order_id, sau khi lọc đúng payment statuses. CTE kết quả tối đa một hàng cho mỗi order_id.

</details>

### Bài 14 — GROUP BY sai

CTE payment GROUP BY order_id, payment_status rồi JOIN chỉ theo order_id có an toàn không?

<details>
<summary>Đáp án</summary>

Không chắc. Một order có nhiều payment_status sẽ có nhiều hàng CTE, tiếp tục fan-out. Phải lọc status hoặc pivot/conditional aggregate về một hàng/order.

</details>

### Bài 15 — EXISTS

Chỉ cần biết một order có shipment hay không. Nên dùng JOIN hay EXISTS?

<details>
<summary>Đáp án</summary>

EXISTS, vì nó kiểm tra sự tồn tại mà không nhân order theo số shipment.

</details>

### Bài 16 — LEFT JOIN filter

Vì sao WHERE payment_status='CAPTURED' sau LEFT JOIN có thể loại order chưa thanh toán?

<details>
<summary>Đáp án</summary>

Với order không có payment, payment_status là NULL; điều kiện WHERE không true nên hàng bị loại. Đưa filter vào ON hoặc aggregate payment trước.

</details>

### Bài 17 — COALESCE

COALESCE(NULL,0) có khử duplicate rows không?

<details>
<summary>Đáp án</summary>

Không. Nó chỉ thay NULL bằng 0.

</details>

### Bài 18 — COUNT(*) sau LEFT JOIN

Một order không có payment vẫn có thể được COUNT(*) là 1 sau LEFT JOIN không?

<details>
<summary>Đáp án</summary>

Có. LEFT JOIN giữ hàng order với các cột payment NULL. COUNT(payment_id) mới bỏ hàng NULL đó.

</details>

### Bài 19 — Product revenue trước refund

P-A có line net 54.000 ở order hoàn thành và 20.000 ở order hủy. Product revenue theo metric mẫu trước refund là bao nhiêu?

<details>
<summary>Đáp án</summary>

54.000. Dòng của order CANCELLED bị loại.

</details>

### Bài 20 — Product revenue sau refund

Refund 10.000 được phân bổ vào line P-A. Net revenue P-A là bao nhiêu?

<details>
<summary>Đáp án</summary>

44.000.

</details>

### Bài 21 — Refund không gắn line

Nếu chỉ có refund header, có thể biết sản phẩm nào bị hoàn chính xác không?

<details>
<summary>Đáp án</summary>

Không, trừ khi có allocation rule hoặc refund_line mapping. Có thể báo refund ở order/customer grain.

</details>

### Bài 22 — Payment attempt

Một đơn có AUTHORIZED 100.000, CAPTURED 100.000 và FAILED 100.000. Có được SUM cả ba thành 300.000 không?

<details>
<summary>Đáp án</summary>

Không. Chỉ cộng event phù hợp với metric, ví dụ capture thành công; cần hiểu payment table là trạng thái hay event ledger.

</details>

### Bài 23 — Tax

Order total gồm merchandise 90.000, tax 9.000, shipping 5.000. Metric net merchandise revenue nên là bao nhiêu trước refund?

<details>
<summary>Đáp án</summary>

90.000. Tax và shipping bị loại theo định nghĩa metric mẫu.

</details>

### Bài 24 — Discount cấp đơn

Nếu discount_total chỉ lưu ở header và chưa phân bổ vào lines, báo cáo theo product nên làm gì?

<details>
<summary>Đáp án</summary>

Dùng allocation rule có tài liệu, hoặc chỉ báo line gross/net trước order discount và trừ discount ở order grain. Không trừ discount hai lần.

</details>

### Bài 25 — Currency

Có thể cộng 100 USD và 2.000.000 VND thành một số doanh thu không?

<details>
<summary>Đáp án</summary>

Không. Group theo currency hoặc quy đổi bằng exchange rate có nguồn, thời điểm và rounding policy rõ.

</details>

### Bài 26 — Recognition date

Đơn đặt 31/12 nhưng ghi nhận 02/01. Báo cáo theo ngày ghi nhận nên thuộc ngày nào?

<details>
<summary>Đáp án</summary>

02/01, vì metric chọn recognized_at, không phải ordered_at.

</details>

### Bài 27 — Refund kỳ sau

Refund phát sinh tháng sau đơn gốc. Có thể tự quyết định trừ vào tháng gốc hay tháng refund không?

<details>
<summary>Đáp án</summary>

Không. Phải theo accounting policy; báo cáo revenue, adjustment và cash có thể dùng các ngày khác nhau.

</details>

### Bài 28 — Shipment fan-out

Một đơn có 2 lines và 3 shipments. JOIN raw lines với shipments tạo bao nhiêu rows?

<details>
<summary>Đáp án</summary>

6 rows nếu mỗi line kết hợp với mỗi shipment qua order_id.

</details>

### Bài 29 — Hai bảng con

Một đơn có 2 lines, 2 payments, 3 tags. Số rows sau JOIN cả ba?

<details>
<summary>Đáp án</summary>

2 × 2 × 3 = 12 rows nếu các quan hệ độc lập theo order_id.

</details>

### Bài 30 — Grain của CTE

CTE line_totals GROUP BY order_id có grain gì?

<details>
<summary>Đáp án</summary>

Một hàng mỗi order_id có ít nhất một line. Khi LEFT JOIN vào orders, order không có line sẽ có NULL ở CTE.

</details>

### Bài 31 — Window function

SUM(order_total) OVER(PARTITION BY order_id) sau JOIN lines có tự sửa fan-out không?

<details>
<summary>Đáp án</summary>

Không. Window function không giảm số hàng; nó tính trên các hàng đã bị nhân.

</details>

### Bài 32 — Header và product rows

Một order_total 100.000 xuất hiện trên ba product lines. Có thể cộng cột order_total ở report line-level không?

<details>
<summary>Đáp án</summary>

Không. Nó bị lặp ba lần. Tách báo cáo hoặc phân bổ order total theo quy tắc có kiểm soát.

</details>

### Bài 33 — Allocation

Line A chiếm 60% net merchandise, line B 40%; order total 100.000. Phân bổ theo tỷ trọng là bao nhiêu?

<details>
<summary>Đáp án</summary>

A = 60.000; B = 40.000. Tổng phân bổ bằng 100.000. Đây là allocated order total, không phải line merchandise revenue.

</details>

### Bài 34 — Rounding allocation

Nếu phân bổ ra các dòng có số lẻ, tổng có thể lệch do rounding không?

<details>
<summary>Đáp án</summary>

Có. Cần quy tắc xử lý phần dư và kiểm tra tổng phân bổ khớp nguồn.

</details>

### Bài 35 — Header-line reconciliation

Tại sao cần so subtotal_gross với SUM(quantity*unit_price)?

<details>
<summary>Đáp án</summary>

Để phát hiện line thiếu/trùng, snapshot giá khác, discount/coupon chưa phân bổ hoặc rounding. Cần hiểu business rules trước khi kết luận lỗi.

</details>

### Bài 36 — GROUP BY header

GROUP BY order_id, order_total sau JOIN lines có làm order_total chỉ được cộng một lần không?

<details>
<summary>Đáp án</summary>

Không. SUM vẫn cộng một bản sao cho mỗi line trong group. Phải aggregate lines trước hoặc không JOIN.

</details>

### Bài 37 — Filter payment

Nếu chỉ cần tổng order_total của đơn có payment CAPTURED, dùng EXISTS hay JOIN raw payment?

<details>
<summary>Đáp án</summary>

EXISTS để kiểm tra có capture, tránh nhân order theo số payment.

</details>

### Bài 38 — Index

Index nào thường hữu ích cho aggregate lines theo order_id?

<details>
<summary>Đáp án</summary>

Index trên sales_order_line(order_id), ngoài primary key của line. Cần xem query plan/workload trước khi quyết định.

</details>

### Bài 39 — Query date

Vì sao lọc recognized_at theo >= start và < end tốt hơn BETWEEN end-of-day?

<details>
<summary>Đáp án</summary>

Không phải đoán precision cuối ngày, không đếm trùng midnight và dễ dùng range index.

</details>

### Bài 40 — NULL monetary

Một subtotal NULL có luôn đồng nghĩa subtotal bằng 0 không?

<details>
<summary>Đáp án</summary>

Không. NULL có thể là chưa tính/chưa biết. Chỉ COALESCE thành 0 khi contract nói missing amount được coi là zero.

</details>

### Bài 41 — Partial payment

Order total 100.000 nhưng captured mới 60.000. Doanh thu merchandise có bắt buộc chỉ ghi nhận 60.000 không?

<details>
<summary>Đáp án</summary>

Không mặc định. Revenue recognition và cash collection là hai metric khác nhau; policy kế toán quyết định ghi nhận.

</details>

### Bài 42 — Refund pending

Refund 10.000 đang PENDING có được trừ vào net revenue mẫu không?

<details>
<summary>Đáp án</summary>

Không. Metric mẫu chỉ trừ refund APPROVED. Có thể có metric riêng về requested refunds.

</details>

### Bài 43 — DISTINCT order IDs

Khi nào SELECT DISTINCT order_id từ bảng con là hợp lý?

<details>
<summary>Đáp án</summary>

Khi tạo tập khóa duy nhất của các order thỏa điều kiện để JOIN về header hoặc lọc, trước khi cộng order-level measures.

</details>

### Bài 44 — Test fixture

Vì sao cần hai đơn có cùng order_total trong fixture?

<details>
<summary>Đáp án</summary>

Để phát hiện giải pháp sai SUM(DISTINCT order_total), vốn gộp các giá trị bằng nhau của hai đơn riêng.

</details>

### Bài 45 — Tổng hợp

Viết chiến lược để báo cáo net merchandise revenue theo customer khi có lines và refunds.

<details>
<summary>Đáp án</summary>

1. Lọc orders theo status và recognition period.
2. Aggregate line net về một hàng/order.
3. Aggregate approved merchandise refund theo order (hoặc refund line).
4. JOIN các CTE 1:0..1 vào order header.
5. Tính net revenue ở order grain.
6. GROUP BY customer_id và currency_code.
7. Đối soát tổng kết quả với tổng line net trừ refund của cùng tập orders.

</details>

## 34. Checklist trước khi phát hành báo cáo doanh thu

- [ ] Định nghĩa rõ metric: merchandise, order total, cash hay recognized revenue.
- [ ] Xác định grain của mỗi bảng nguồn.
- [ ] Xác định grain của kết quả.
- [ ] Kiểm tra cardinality của mọi JOIN.
- [ ] Không JOIN nhiều bảng one-to-many raw rồi SUM các measures.
- [ ] Aggregate mỗi bảng con về grain phù hợp trước khi JOIN.
- [ ] Dùng EXISTS nếu chỉ cần kiểm tra sự tồn tại.
- [ ] Không dùng COUNT(DISTINCT) để giả vờ sửa SUM.
- [ ] Không dùng SUM(DISTINCT amount) để khử duplicate.
- [ ] Lọc đúng order status và payment/refund status.
- [ ] Phân biệt ordered_at, recognized_at, captured_at và refunded_at.
- [ ] Xác định discount đã được phân bổ hay chưa.
- [ ] Tách tax/shipping khỏi merchandise theo metric.
- [ ] Phân nhóm currency hoặc quy đổi theo policy.
- [ ] Xử lý NULL theo contract.
- [ ] Đối soát header với line totals.
- [ ] Đối soát payment/refund với ledger.
- [ ] Có fixture 1:N, N:M, duplicate amounts và missing child rows.
- [ ] Test đơn nhiều lines × payments × refunds.
- [ ] Test refund một phần/toàn bộ/pending/rejected.
- [ ] Test nhiều shipment/tag/promotion.
- [ ] Test biên ngày/timezone nếu nhóm theo ngày.
- [ ] Kiểm tra execution plan và index.
- [ ] Chạy trên DBMS/driver và dữ liệu gần production.

## 35. Tổng kết cần ghi nhớ

1. **JOIN có thể nhân dòng trước khi SUM.** SQL vẫn chạy hợp lệ nhưng số tiền sai.
2. Luôn xác định **grain**: một hàng là một đơn, một line, một payment hay một refund.
3. Với một order có L lines, P payments và R refunds, JOIN raw có thể tạo L×P×R tổ hợp.
4. Header measures như order_total phải được cộng ở order grain, mỗi order một lần.
5. Line measures phải được cộng ở line grain; không JOIN thêm payment raw làm lặp line.
6. Payment và refund là các nguồn một-nhiều độc lập; aggregate từng nguồn riêng.
7. **Pre-aggregate về một hàng mỗi order rồi mới JOIN** là mẫu cơ bản, dễ kiểm tra.
8. COUNT(DISTINCT order_id) chỉ sửa order count; không sửa SUM bị lặp.
9. SUM(DISTINCT order_total) sai khi hai đơn khác nhau có cùng tổng tiền.
10. SELECT DISTINCT sau JOIN không thay thế việc sửa grain.
11. EXISTS phù hợp khi chỉ cần biết có dòng con.
12. LEFT JOIN giữ đơn không có con; filter ở WHERE có thể vô tình loại các đơn đó.
13. COALESCE xử lý NULL, không xử lý fan-out.
14. Doanh thu hàng hóa, order total, tiền capture, tiền refund và net cash là những metric khác nhau.
15. Discount, tax, shipping và refund cần quy tắc phân bổ/ghi nhận rõ; tránh trừ hoặc cộng hai lần.
16. Muốn báo cáo refund theo product, cần mapping refund về line hoặc allocation policy.
17. Không cộng các currency khác nhau khi chưa quy đổi theo exchange-rate policy.
18. Dùng ngày ghi nhận hay ngày đặt hàng tùy định nghĩa metric; refund có thể thuộc kỳ khác.
19. Window function không tự giảm số hàng và không chữa fan-out.
20. Đối soát header-line và payment-refund giúp tìm dữ liệu lệch.
21. Dùng fixture có nhiều lines, payments, refunds và hai đơn cùng amount để phát hiện lỗi.
22. Kiểm tra execution plan và index sau khi đã đúng logic.
23. Hãy hỏi: **“Mỗi hàng trong kết quả đại diện cho cái gì, và mỗi số tiền đang được cộng đúng một lần ở grain nào?”**

### Tài liệu tham khảo nên tra cứu

- **PostgreSQL Documentation:** Table Expressions; Joins; Aggregate Functions; WITH Queries; EXISTS; Window Functions; EXPLAIN.
- **MySQL Reference Manual:** JOIN; Aggregate Functions; Common Table Expressions; Subqueries with EXISTS; EXPLAIN; DECIMAL.
- **Microsoft Learn — SQL Server:** FROM/JOIN; GROUP BY; Aggregate Functions; Common Table Expressions; EXISTS; Execution Plans; decimal and numeric.
- **Oracle Database SQL Language Reference:** SELECT; Joins; GROUP BY; Aggregate Functions; Subquery Factoring; EXISTS; Analytic Functions.
- **SQLite Documentation:** SELECT; Aggregate Functions; WITH Clause; EXPLAIN QUERY PLAN; Datatypes.
- **JDBC/Java Documentation:** PreparedStatement; BigDecimal; temporal binding and transaction handling.
- **Dimensional modeling references:** Fact table grain, additive/semi-additive measures, bridge tables and allocation rules.

**Thông điệp cuối cùng:** Muốn báo cáo doanh thu đúng, hãy xác định metric và grain trước, tổng hợp từng bảng con về đúng mức rồi mới JOIN. Không chữa fan-out bằng DISTINCT. Hãy kiểm chứng bằng fixture có nhiều chi tiết, nhiều thanh toán, hoàn tiền và các đơn có cùng giá trị; khi mỗi số tiền chỉ được cộng một lần theo đúng định nghĩa nghiệp vụ, báo cáo mới đáng tin cậy.
