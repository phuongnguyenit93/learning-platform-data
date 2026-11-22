# Kiểm thử tính đúng của phép nối, tổng hợp và lịch sử theo thời gian

Một truy vấn SQL có thể chạy thành công, trả về dữ liệu có vẻ hợp lý và vẫn **sai về nghiệp vụ**. Khi một đơn hàng có nhiều dòng, một khách hàng có nhiều phiên bản lịch sử, hoặc một khoản thanh toán gồm nhiều sự kiện, phép **JOIN** không đúng khóa có thể nhân bản các hàng fact. Các phép **SUM**, **COUNT** và **COUNT(DISTINCT)** sau đó cho những con số trông hợp lệ nhưng không còn phản ánh điều đã xảy ra. Đối với thời gian, một bản ghi có thể được gán cho phân khúc khách hàng **hiện tại** thay vì phân khúc **tại thời điểm giao dịch**.

**Kiểm chứng thiết kế dữ liệu (design validation)** không dừng ở việc DDL hợp lệ, khóa ngoại tồn tại hay truy vấn trả kết quả. Ta cần kiểm thử **những bất biến về grain, cardinality, định danh, quan hệ, tính cộng được của số đo và ngữ nghĩa thời gian** bằng dữ liệu mẫu có chủ đích, truy vấn đối soát và các ca phản ví dụ.

Bài nằm trong chương **Kiểm chứng thiết kế** của mô-đun **DATABASE_DATA_MODELING**. Mục tiêu là rèn khả năng chuyển yêu cầu nghiệp vụ thành một **hợp đồng dữ liệu có thể kiểm thử**, từ khóa và quan hệ của mô hình quan hệ đến fact/dimension, dữ liệu lịch sử và lược đồ phân tích; đồng thời biết khi nào mô hình document, graph hay một hệ phân tích khác cần những bất biến tương đương.

## 1. Tính đúng là tính đúng ở mức nào?

Một truy vấn có thể “đúng” ở cấp cú pháp nhưng “sai” ở các cấp còn lại.

| Cấp kiểm chứng | Câu hỏi | Phản ví dụ |
| --- | --- | --- |
| **Cú pháp và kiểu** | Câu SQL có chạy và kiểu dữ liệu tương thích không? | SQL chạy, nhưng cột ngày bị ép theo timezone máy chủ |
| **Grain và khóa** | Một hàng biểu diễn điều gì, có bị lặp không? | Một dòng đơn bị nhân hai lần khi JOIN thanh toán |
| **Cardinality phép nối** | Mỗi hàng trái được phép khớp bao nhiêu hàng phải? | JOIN fact với hai phiên bản dimension của cùng khách |
| **Tính đầy đủ** | Có mất hàng do INNER JOIN hoặc bộ lọc không? | Đơn có mã khách chưa ánh xạ bị loại khỏi báo cáo |
| **Số đo và phép tổng** | Có đang cộng đúng loại số đo ở đúng grain không? | Cộng số dư cuối ngày qua nhiều ngày |
| **Thời gian nghiệp vụ** | Phân loại theo giá trị nào, có hiệu lực vào lúc nào? | Giao dịch cũ bị gán vào phòng ban mới |
| **Thời gian hệ thống biết dữ liệu** | Báo cáo as-of có tái hiện được phiên bản từng công bố không? | Dữ liệu đến trễ làm báo cáo quá khứ thay đổi mà không có phiên bản |
| **Độ tin cậy vận hành** | Chạy lại, backfill, đổi schema có còn giữ bất biến? | Consumer nạp trùng một sự kiện khi retry |

Một quy tắc kiểm chứng rất hữu ích:

> **Viết bằng lời một hàng là gì, rồi biến phát biểu đó thành khóa, ràng buộc, truy vấn test và kết quả mong đợi.**

Nếu không nói rõ grain, phép tính sau JOIN dù tối ưu thế nào cũng khó chứng minh đúng.

### 1.1. Ví dụ về cùng một con số nhưng khác cách đếm

Một đơn **O1001** có hai dòng hàng và hai lần thanh toán. Có ít nhất ba phép đếm hợp lệ:

- **Số dòng đơn:** 2.
- **Số đơn duy nhất:** 1.
- **Số sự kiện thanh toán:** 2.

Nếu JOIN dòng đơn với sự kiện thanh toán theo order_id rồi dùng COUNT(*), kết quả có thể thành **4**. Đó không phải số dòng đơn, số đơn, hay số thanh toán; đó là **số cặp dòng–thanh toán tạo ra bởi phép nối**.

### 1.2. Bốn đầu ra cần có trong một bộ kiểm chứng

1. **Data contract:** grain, khóa, nguồn, điều kiện lọc, định nghĩa số đo, timezone và khoảng hiệu lực.
2. **Fixture:** bộ dữ liệu nhỏ có ca bình thường, nhiều–nhiều, biên thời gian, orphan và dữ liệu đến trễ.
3. **Assertion:** truy vấn trả tập sai lệch rỗng hoặc phát lỗi có thông điệp cụ thể.
4. **Reconciliation:** đối chiếu tập khóa, số hàng, số tiền và group giữa nguồn chuẩn với kết quả dẫn xuất.

Một vài test trả PASS trên dữ liệu sạch không đủ; phải có **negative test** chứng tỏ test phát hiện đúng loại lỗi đã được thiết kế để bắt.

## 2. Hợp đồng grain, khóa và số đo trước khi viết JOIN

### 2.1. Mỗi bảng phải có phát biểu grain

Trong ví dụ xuyên suốt, ta dùng ba bảng:

| Bảng | Grain | Khóa | Vai trò |
| --- | --- | --- | --- |
| **fact_order_line** | Một dòng hàng của một đơn đã chốt | line_id | Số lượng, giá trị dòng |
| **payment_event** | Một sự kiện thanh toán đã ghi nhận | payment_id | Số tiền thanh toán |
| **dim_customer_history** | Một phiên bản phân loại khách hàng có hiệu lực trong một khoảng thời gian | customer_sk | Dimension có lịch sử kiểu SCD Type 2 |

Với hệ đa tenant, cặp **(tenant_id, customer_code)** là định danh khách hàng nghiệp vụ trong ví dụ; **customer_sk** là khóa thay thế của một *phiên bản lịch sử*. Hệ thống không được đồng nhất một khách hàng và một phiên bản của khách hàng.

### 2.2. Đặc tả số đo để tránh “đếm gì cũng SUM được”

| Số đo hoặc thuộc tính | Grain gốc | Tổng hợp hợp lệ | Lỗi thường gặp |
| --- | --- | --- | --- |
| **line_amount_vnd** | Một dòng đơn | SUM qua các dòng đủ điều kiện | JOIN tới payment_event gây nhân dòng |
| **quantity** | Một dòng đơn | SUM nếu cùng nghĩa đơn vị/sản phẩm | Cộng nhiều đơn vị đo không quy đổi |
| **paid_vnd** | Một sự kiện thanh toán | SUM trên các event thanh toán hợp lệ | Cộng lại sau JOIN nhiều dòng đơn |
| **số đơn** | Order có ít nhất một dòng hợp lệ | COUNT DISTINCT khóa đơn trong phạm vi | COUNT(*) trên fact cấp dòng |
| **số khách duy nhất** | Khách hàng nghiệp vụ | COUNT DISTINCT đúng khóa tenant–customer | Cộng số khách giữa nhiều ngày có thể trùng |
| **số dư cuối ngày** | Account tại một mốc snapshot | Tổng theo tài khoản ở cùng mốc có thể hợp lệ | SUM số dư qua thời gian |
| **tỷ lệ chuyển đổi** | Tử số/mẫu số theo tập đối tượng | Cộng tử số và mẫu số rồi chia | Trung bình đơn giản tỷ lệ nhóm có cỡ khác |

**Additive measure** như số tiền của các dòng đơn có thể cộng theo những chiều độc lập phù hợp với grain. **Semi-additive measure** như số dư có thể cộng theo một số chiều (tài khoản ở cùng thời điểm), nhưng không cộng theo thời gian. **Non-additive measure** như tỷ lệ thường phải tái tính từ tử số/mẫu số.

### 2.3. Thống nhất tập đủ điều kiện

Hai báo cáo có thể khác nhau nếu một bên lấy **đơn đặt thành công**, một bên lấy **đơn đã thanh toán**, hoặc một bên loại đơn hoàn tiền. Trước khi đối soát, xác nhận:

- Trạng thái giao dịch nào được tính?
- Có bao gồm bản ghi hủy, test hoặc hoàn tiền không?
- Số tiền gốc, tiền sau giảm, hay tiền ròng?
- Ngày đặt, ngày thanh toán hay ngày ghi nhận kế toán?
- Đơn tiền tệ và chính sách quy đổi?
- Mốc dữ liệu đã nhận (**cutoff/watermark**) và phiên bản công thức?

Một đối soát số học giữa hai **định nghĩa nghiệp vụ khác nhau** không chứng minh một thiết kế sai; nó chứng minh ta chưa thống nhất thứ cần so sánh.

## 3. Bộ dữ liệu PostgreSQL tự chứa

Ví dụ dùng PostgreSQL và các bản ghi cố định để minh họa những câu kiểm tra. Các truy vấn dưới đây được trình bày để người học có thể chạy trong **một schema thực hành trống**; chúng không tự thực thi khi đọc bài. Để tránh phụ thuộc vào timezone của phiên SQL, mọi timestamp trong fixture có offset **+07** và báo cáo dùng **Asia/Ho_Chi_Minh** tường minh.

### 3.1. DDL

~~~sql
CREATE TABLE dim_customer_history (
    customer_sk BIGINT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    customer_code TEXT NOT NULL,
    department TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE fact_order_line (
    line_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    customer_code TEXT NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    line_amount_vnd NUMERIC(20, 0) NOT NULL
        CHECK (line_amount_vnd >= 0)
);

CREATE TABLE payment_event (
    payment_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    paid_vnd NUMERIC(20, 0) NOT NULL CHECK (paid_vnd > 0)
);

CREATE INDEX idx_order_line_tenant_order
    ON fact_order_line (tenant_id, order_id);

CREATE INDEX idx_payment_tenant_order
    ON payment_event (tenant_id, order_id);

CREATE INDEX idx_customer_history_lookup
    ON dim_customer_history (
        tenant_id, customer_code, valid_from
    );
~~~

**Giới hạn có chủ ý của DDL:** khóa của bảng **dim_customer_history** đảm bảo từng phiên bản customer_sk là duy nhất và từng khoảng có thứ tự đúng, nhưng **chưa ngăn hai phiên bản cùng customer_code có khoảng hiệu lực chồng nhau**. Đó sẽ là bất biến quan trọng cần kiểm tra; phần sau trình bày ràng buộc tăng cường.

### 3.2. Nạp dimension có thay đổi phòng ban theo thời gian

~~~sql
INSERT INTO dim_customer_history (
    customer_sk, tenant_id, customer_code,
    department, valid_from, valid_to
) VALUES
    (101, 'T01', 'C01', 'North',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     TIMESTAMPTZ '2026-11-20 00:00:00+07'),
    (102, 'T01', 'C01', 'South',
     TIMESTAMPTZ '2026-11-20 00:00:00+07',
     NULL),
    (103, 'T01', 'C02', 'North',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     NULL),
    (104, 'T02', 'C03', 'South',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     NULL);
~~~

Khách **T01/C01** chuyển từ **North** sang **South** đúng đầu ngày **20/11/2026 theo giờ Việt Nam**. Quy ước khoảng hiệu lực:

\[
[\text{valid\_from}, \text{valid\_to})
\]

Nghĩa là **bao gồm điểm bắt đầu, không bao gồm điểm kết thúc**; **valid_to = NULL** nghĩa là chưa có thời điểm kết thúc được ghi nhận.

### 3.3. Nạp sáu dòng hàng thuộc năm đơn

~~~sql
INSERT INTO fact_order_line (
    line_id, tenant_id, order_id, customer_code,
    placed_at, quantity, line_amount_vnd
) VALUES
    ('L01', 'T01', 'O1001', 'C01',
     TIMESTAMPTZ '2026-11-19 10:00:00+07', 1, 100000),
    ('L02', 'T01', 'O1001', 'C01',
     TIMESTAMPTZ '2026-11-19 10:00:00+07', 2, 200000),
    ('L03', 'T01', 'O1002', 'C01',
     TIMESTAMPTZ '2026-11-20 09:00:00+07', 3, 300000),
    ('L04', 'T01', 'O1003', 'C02',
     TIMESTAMPTZ '2026-11-20 12:00:00+07', 1, 150000),
    ('L05', 'T02', 'O1004', 'C03',
     TIMESTAMPTZ '2026-11-21 00:30:00+07', 5, 250000),
    ('L06', 'T01', 'O1005', 'C01',
     TIMESTAMPTZ '2026-11-21 16:00:00+07', 2, 100000);
~~~

### 3.4. Nạp sáu sự kiện thanh toán

~~~sql
INSERT INTO payment_event (
    payment_id, tenant_id, order_id, paid_at, paid_vnd
) VALUES
    ('P01', 'T01', 'O1001',
     TIMESTAMPTZ '2026-11-19 10:05:00+07', 200000),
    ('P02', 'T01', 'O1001',
     TIMESTAMPTZ '2026-11-19 10:06:00+07', 100000),
    ('P03', 'T01', 'O1002',
     TIMESTAMPTZ '2026-11-20 09:05:00+07', 300000),
    ('P04', 'T01', 'O1003',
     TIMESTAMPTZ '2026-11-20 12:05:00+07', 150000),
    ('P05', 'T02', 'O1004',
     TIMESTAMPTZ '2026-11-21 00:35:00+07', 250000),
    ('P06', 'T01', 'O1005',
     TIMESTAMPTZ '2026-11-21 16:05:00+07', 100000);
~~~

Đơn O1001 có **hai dòng hàng và hai sự kiện thanh toán**, được tạo cố ý để thử trường hợp JOIN sinh **tích Descartes trong phạm vi một order**.

### 3.5. Số chuẩn tham chiếu (*oracle*)

| Chỉ số trên dữ liệu nguồn | Kết quả kỳ vọng |
| --- | ---: |
| Dòng đơn hàng | 6 |
| Đơn duy nhất theo (tenant_id, order_id) | 5 |
| Khách nghiệp vụ duy nhất theo (tenant_id, customer_code) | 3 |
| Sự kiện thanh toán | 6 |
| Tổng line_amount_vnd | 1.100.000 |
| Tổng paid_vnd | 1.100.000 |

~~~sql
SELECT COUNT(*) AS lines,
       SUM(line_amount_vnd) AS sales_vnd,
       SUM(quantity) AS units
FROM fact_order_line;
-- lines = 6; sales_vnd = 1100000; units = 14.

SELECT COUNT(*) AS payments, SUM(paid_vnd) AS paid_vnd
FROM payment_event;
-- payments = 6; paid_vnd = 1100000.
~~~

Kết quả nguồn là **oracle của fixture**, không có nghĩa mọi dữ liệu thực tế luôn có tổng bán bằng tổng thanh toán. Trong hệ thực, tiền thanh toán có thể khác vì khoản giữ tiền, thuế, phí, thanh toán một phần, hoàn tiền và trạng thái giao dịch.

## 4. Kiểm thử cardinality và tính đầy đủ của JOIN

### 4.1. Kết quả JOIN phụ thuộc vào quan hệ khóa

| Quan hệ mong đợi | Ví dụ | Phép kiểm chứng |
| --- | --- | --- |
| 1–1 | Một source order ↔ một bản summary order | Mỗi khóa trái có đúng một khớp bên phải |
| N–1 | Nhiều dòng đơn ↔ một phiên bản dimension theo thời điểm | Mỗi line khớp **đúng một** dimension row |
| 1–N | Một đơn ↔ nhiều dòng hàng | Chấp nhận nhân hàng nếu câu hỏi là về **dòng** |
| N–M | Dòng đơn ↔ sự kiện thanh toán cùng đơn | Không cộng measure ở hai grain trực tiếp sau JOIN |
| 0–1 hoặc 0–N | Dữ liệu tùy chọn | Cần chính sách rõ cho hàng không khớp |

Lỗi thường thấy là tự cho rằng một JOIN theo cột trùng tên là **N–1**, trong khi phía dimension có nhiều phiên bản hoặc phía payment có nhiều event.

### 4.2. JOIN sai với SCD: bỏ điều kiện thời gian

~~~sql
-- PHẢN MẪU: đừng dùng để tính doanh thu.
SELECT
    COUNT(*) AS joined_rows,
    SUM(f.line_amount_vnd) AS joined_amount_vnd
FROM fact_order_line AS f
JOIN dim_customer_history AS c
  ON c.tenant_id = f.tenant_id
 AND c.customer_code = f.customer_code;
~~~

Kết quả của fixture là **10 hàng** và **1.800.000 VND**, thay vì 6 hàng và 1.100.000 VND. Bốn dòng của T01/C01 mỗi dòng khớp **hai phiên bản lịch sử**, làm tổng tăng thêm **700.000 VND**.

Đây là lỗi **fanout**: một hàng fact bị nhân thành nhiều hàng vì quan hệ JOIN không duy nhất tại ngữ nghĩa mong muốn.

### 4.3. JOIN đúng theo thời điểm hiệu lực

~~~sql
SELECT
    f.line_id,
    f.tenant_id,
    f.customer_code,
    f.line_amount_vnd,
    c.customer_sk,
    c.department
FROM fact_order_line AS f
JOIN dim_customer_history AS c
  ON c.tenant_id = f.tenant_id
 AND c.customer_code = f.customer_code
 AND f.placed_at >= c.valid_from
 AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
ORDER BY f.line_id;
~~~

Kết quả từng dòng:

| line_id | customer_sk | department | line_amount_vnd |
| --- | ---: | --- | ---: |
| L01 | 101 | North | 100000 |
| L02 | 101 | North | 200000 |
| L03 | 102 | South | 300000 |
| L04 | 103 | North | 150000 |
| L05 | 104 | South | 250000 |
| L06 | 102 | South | 100000 |

Tổng sau JOIN đúng vẫn phải là **1.100.000 VND**. Tuy nhiên, **việc SUM bằng nhau một lần không chứng minh luôn đúng**, vì có thể mất một hàng và nhân một hàng khác có cùng giá trị. Cần test **tính duy nhất theo line_id** và **sự tồn tại của từng match**.

### 4.4. Test “mỗi fact khớp đúng một dimension row”

~~~sql
WITH matches AS (
    SELECT
        f.line_id,
        COUNT(c.customer_sk) AS match_count
    FROM fact_order_line AS f
    LEFT JOIN dim_customer_history AS c
      ON c.tenant_id = f.tenant_id
     AND c.customer_code = f.customer_code
     AND f.placed_at >= c.valid_from
     AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
    GROUP BY f.line_id
)
SELECT line_id, match_count
FROM matches
WHERE match_count <> 1
ORDER BY line_id;
~~~

**Kết quả đúng: tập rỗng.** Nó phân biệt:

- **match_count = 0:** dimension chưa có phiên bản có hiệu lực, dữ liệu bị thiếu hoặc sai mốc.
- **match_count > 1:** các khoảng hiệu lực chồng nhau, join key thiếu hoặc các phiên bản bị trùng.

Test này mạnh hơn một phép SUM đơn lẻ vì kiểm tra ở **đúng grain từng dòng fact**. Nếu khóa line_id chỉ duy nhất trong tenant, phải GROUP BY cả tenant_id và line_id.

### 4.5. Test mất hàng khi dùng INNER JOIN

Trong một nguồn đang nạp theo thời gian, fact có thể đến trước dimension. **INNER JOIN** sẽ loại hẳn dòng chưa ánh xạ, khiến doanh số giảm nhưng không có lỗi SQL.

~~~sql
SELECT
    f.line_id,
    f.tenant_id,
    f.customer_code,
    f.placed_at
FROM fact_order_line AS f
WHERE NOT EXISTS (
    SELECT 1
    FROM dim_customer_history AS c
    WHERE c.tenant_id = f.tenant_id
      AND c.customer_code = f.customer_code
      AND f.placed_at >= c.valid_from
      AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
);
~~~

Trên dữ liệu mẫu, kết quả rỗng. Với dữ liệu thực, **không có match** có thể do mã khách lạ, dimension đến trễ, khoảng hiệu lực bị hở hoặc timestamp sai. Chính sách xử lý tùy nghiệp vụ: **quarantine**, late-arriving dimension, hàng **Unknown** được quản trị rõ hoặc chờ nạp lại. Không được coi hàng biến mất sau INNER JOIN là “hàng không cần tính” nếu nguồn nghiệp vụ yêu cầu nó được tính.

Thử cố ý tạo một dòng chưa có dimension, rồi hoàn tác:

~~~sql
BEGIN;

INSERT INTO fact_order_line (
    line_id, tenant_id, order_id, customer_code,
    placed_at, quantity, line_amount_vnd
) VALUES (
    'L_BAD', 'T01', 'O_BAD', 'C99',
    TIMESTAMPTZ '2026-11-21 12:00:00+07', 1, 90000
);

-- Chạy lại truy vấn NOT EXISTS ở trên:
-- phải tìm thấy L_BAD.

ROLLBACK;
~~~

Đây là **negative test**: ta cố ý tạo lỗi để xác minh phép kiểm chứng thực sự báo lỗi. Nó khác với việc chỉ chạy test trên bộ dữ liệu luôn sạch.

### 4.6. Test khóa JOIN phải đủ phạm vi tenant

Trong hệ đa khách hàng, **customer_code = C01** có thể tồn tại ở hai tenant. Nếu JOIN chỉ bằng customer_code, fact của tenant T01 có thể ghép tới dimension của tenant T02. Vì vậy điều kiện phải có **tenant_id** khi mã khách chỉ duy nhất trong tenant.

Tương tự, phép nối order line ↔ payment event trong ví dụ phải dùng **(tenant_id, order_id)**, không chỉ order_id nếu nghiệp vụ không bảo đảm order_id toàn cục.

Đối với dữ liệu nhạy cảm, JOIN sai tenant vừa làm sai báo cáo vừa có thể tạo đường **rò thông tin giữa khách hàng**. Không chỉ kiểm tra số hàng/tổng; test phải có fixture cố ý sử dụng cùng mã nghiệp vụ ở hai tenant và xác minh kết quả không giao thoa.

## 5. JOIN nhiều fact ở các grain khác nhau: fanout nguy hiểm

### 5.1. Phản ví dụ với dòng đơn và sự kiện thanh toán

~~~sql
-- PHẢN MẪU: hai tập 1-N được JOIN trực tiếp ở cấp order.
SELECT
    COUNT(*) AS joined_rows,
    SUM(l.line_amount_vnd) AS inflated_sales_vnd,
    SUM(p.paid_vnd) AS inflated_payments_vnd
FROM fact_order_line AS l
JOIN payment_event AS p
  ON p.tenant_id = l.tenant_id
 AND p.order_id = l.order_id;
~~~

Fixture trả **8 hàng**, không phải 6; cả tổng dòng hàng và tổng thanh toán đều thành **1.400.000 VND**, sai so với hai tổng nguồn độc lập là **1.100.000 VND**.

Vì sao? Với đơn O1001:

~~~text
Dòng đơn:  L01 = 100.000; L02 = 200.000
Thanh toán: P01 = 200.000; P02 = 100.000

Sau JOIN theo order:
  (L01, P01)
  (L01, P02)
  (L02, P01)
  (L02, P02)

SUM(line_amount) của O1001 = 600.000 (đúng là 300.000)
SUM(paid_vnd) của O1001    = 600.000 (đúng là 300.000)
~~~

Một báo cáo tình cờ vẫn có **sales_vnd = payments_vnd = 1.400.000** sẽ trông “đã cân”, nhưng **cả hai bên đều bị nhân đôi**. Việc hai số sai bằng nhau **không chứng minh mô hình đúng**.

### 5.2. Phương án đúng: tổng hợp mỗi fact về cùng grain rồi mới JOIN

Khi muốn so số tiền dòng hàng và số tiền thanh toán **theo đơn**, hãy đưa cả hai nguồn về **(tenant_id, order_id)**:

~~~sql
WITH line_totals AS (
    SELECT
        tenant_id,
        order_id,
        COUNT(*) AS line_count,
        SUM(line_amount_vnd) AS line_total_vnd
    FROM fact_order_line
    GROUP BY tenant_id, order_id
),
payment_totals AS (
    SELECT
        tenant_id,
        order_id,
        COUNT(*) AS payment_count,
        SUM(paid_vnd) AS paid_total_vnd
    FROM payment_event
    GROUP BY tenant_id, order_id
)
SELECT
    l.tenant_id,
    l.order_id,
    l.line_count,
    l.line_total_vnd,
    COALESCE(p.payment_count, 0) AS payment_count,
    COALESCE(p.paid_total_vnd, 0) AS paid_total_vnd
FROM line_totals AS l
LEFT JOIN payment_totals AS p
  ON p.tenant_id = l.tenant_id
 AND p.order_id = l.order_id
ORDER BY l.tenant_id, l.order_id;
~~~

Kết quả:

| order_id | line_count | line_total_vnd | payment_count | paid_total_vnd |
| --- | ---: | ---: | ---: | ---: |
| O1001 | 2 | 300000 | 2 | 300000 |
| O1002 | 1 | 300000 | 1 | 300000 |
| O1003 | 1 | 150000 | 1 | 150000 |
| O1004 | 1 | 250000 | 1 | 250000 |
| O1005 | 1 | 100000 | 1 | 100000 |

**COALESCE(paid_total_vnd, 0)** chỉ có nghĩa nếu chính sách xác nhận **“chưa có sự kiện thanh toán trong nguồn đã hoàn tất”** được biểu diễn là tổng thanh toán 0. Nếu dữ liệu payment chưa đồng bộ, số 0 có thể gây hiểu nhầm; khi ấy cần trạng thái **chưa biết/chưa đồng bộ** riêng.

### 5.3. Test có thanh toán nhưng không có order

LEFT JOIN từ order tới payment không thể phát hiện **payment-only order**. Kiểm tra riêng:

~~~sql
SELECT DISTINCT p.tenant_id, p.order_id
FROM payment_event AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM fact_order_line AS l
    WHERE l.tenant_id = p.tenant_id
      AND l.order_id = p.order_id
);
~~~

Trên fixture, truy vấn không có kết quả. Nếu có, phải phân biệt **orphan thật**, **dữ liệu đến trễ**, hoặc **thanh toán không gắn với đơn** được nghiệp vụ cho phép. Không ép tất cả orphan thành lỗi không có ngoại lệ.

### 5.4. Test row count trước và sau mỗi phép nối

Khi JOIN loại **N–1** được kỳ vọng, điều kiện cần là:

\[
\text{count(join result)} = \text{count(left input)}
\]

và mỗi khóa trái phải có **đúng một** match. Nhưng khi JOIN 1–N được chủ đích (một đơn ra nhiều dòng), số hàng tăng là đúng. Vì vậy cần kiểm tra **đúng cardinality được hợp đồng cho phép**, không có một quy tắc tổng quát “mọi JOIN phải giữ row count”.

Test hỗ trợ chẩn đoán các phép JOIN nối tiếp:

~~~sql
WITH stage AS (
    SELECT '01_fact' AS stage_name, COUNT(*) AS row_count
    FROM fact_order_line

    UNION ALL

    SELECT '02_temporal_customer', COUNT(*)
    FROM fact_order_line AS l
    JOIN dim_customer_history AS c
      ON c.tenant_id = l.tenant_id
     AND c.customer_code = l.customer_code
     AND l.placed_at >= c.valid_from
     AND (l.placed_at < c.valid_to OR c.valid_to IS NULL)

    UNION ALL

    SELECT '03_naive_payment_join', COUNT(*)
    FROM fact_order_line AS l
    JOIN payment_event AS p
      ON p.tenant_id = l.tenant_id
     AND p.order_id = l.order_id
)
SELECT * FROM stage ORDER BY stage_name;
~~~

Kết quả lần lượt **6**, **6**, **8**. Bảng này là công cụ *debug*, không phải kiểm thử đủ để chứng minh kết quả đúng; vẫn phải kiểm tra **khóa từng dòng** và **số đo**.

### 5.5. Sử dụng EXISTS khi chỉ cần kiểm tra sự tồn tại

Nếu hỏi “những dòng đơn thuộc đơn **đã có ít nhất một thanh toán**”, không cần JOIN từng sự kiện payment:

~~~sql
SELECT
    l.line_id,
    l.tenant_id,
    l.order_id,
    l.line_amount_vnd
FROM fact_order_line AS l
WHERE EXISTS (
    SELECT 1
    FROM payment_event AS p
    WHERE p.tenant_id = l.tenant_id
      AND p.order_id = l.order_id
)
ORDER BY l.line_id;
~~~

**EXISTS** là điều kiện tồn tại, không nhân dòng theo số payment. Nếu câu hỏi là **“đã trả đủ chưa?”**, EXISTS một payment chưa đủ; phải định nghĩa trạng thái thanh toán và so tổng hợp/ledger phù hợp, có xét hoàn tiền và thời gian.

## 6. Kiểm thử tổng hợp và phép đếm đúng grain

### 6.1. Đếm dòng, đơn và khách không thay thế cho nhau

~~~sql
SELECT
    COUNT(*) AS line_count,
    COUNT(DISTINCT (tenant_id, order_id)) AS distinct_orders,
    COUNT(DISTINCT (tenant_id, customer_code))
        AS distinct_customers,
    SUM(line_amount_vnd) AS total_sales_vnd
FROM fact_order_line;
~~~

Kết quả **6 dòng**, **5 đơn**, **3 khách**, **1.100.000 VND**. Đây là ba phép đếm ở **ba grain khác nhau**.

Nếu dashboard cần số khách duy nhất theo **năm**, không thể lấy tổng số khách duy nhất của từng **ngày**:

~~~sql
SELECT
    (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS local_day,
    COUNT(DISTINCT (tenant_id, customer_code))
        AS unique_customers
FROM fact_order_line
GROUP BY 1
ORDER BY 1;
~~~

Số khách theo ngày là **1, 2, 2** và cộng lại thành **5 lượt khách–ngày**, trong khi số khách duy nhất toàn bộ ba ngày chỉ là **3**. Các tập khách **không rời nhau**, nên tổng của các distinct count theo ngày **không phải** distinct count cho cả kỳ.

### 6.2. Tổng doanh số theo ngày địa phương và tenant

~~~sql
SELECT
    tenant_id,
    (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS local_day,
    COUNT(*) AS line_count,
    SUM(line_amount_vnd) AS sales_vnd
FROM fact_order_line
GROUP BY
    tenant_id,
    (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
ORDER BY tenant_id, local_day;
~~~

| tenant_id | local_day | line_count | sales_vnd |
| --- | --- | ---: | ---: |
| T01 | 2026-11-19 | 2 | 300000 |
| T01 | 2026-11-20 | 2 | 450000 |
| T01 | 2026-11-21 | 1 | 100000 |
| T02 | 2026-11-21 | 1 | 250000 |

Tổng của các group là **6 dòng**, **1.100.000 VND**. Khi GROUP BY trên các nhóm **không giao nhau và bao phủ toàn bộ tập nguồn**, **SUM của các SUM** phải khớp SUM nguồn; đây là một bất biến tốt để kiểm thử.

### 6.3. Test đối soát hai chiều, không chỉ so SUM toàn kỳ

Giả sử một bảng báo cáo đã được lưu, grain là **(tenant_id, local_day)**, có cột **sales_vnd**. Tên bảng minh họa **daily_sales_report** không được tạo bởi DDL ở mục 3; truy vấn sau là **mẫu kiểm chứng để áp dụng sau khi tạo bảng báo cáo**, không phải đoạn tiếp tục thực thi liền mạch của fixture.

~~~sql
WITH expected AS (
    SELECT
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS local_day,
        SUM(line_amount_vnd) AS sales_vnd
    FROM fact_order_line
    GROUP BY tenant_id, local_day
),
actual AS (
    SELECT tenant_id, local_day, sales_vnd
    FROM daily_sales_report
)
SELECT
    COALESCE(e.tenant_id, a.tenant_id) AS tenant_id,
    COALESCE(e.local_day, a.local_day) AS local_day,
    e.sales_vnd AS expected_sales_vnd,
    a.sales_vnd AS actual_sales_vnd
FROM expected AS e
FULL OUTER JOIN actual AS a
  ON a.tenant_id = e.tenant_id
 AND a.local_day = e.local_day
WHERE e.tenant_id IS NULL
   OR a.tenant_id IS NULL
   OR e.sales_vnd IS DISTINCT FROM a.sales_vnd
ORDER BY tenant_id, local_day;
~~~

Khi hai tập đúng nhau, kết quả **rỗng**. FULL OUTER JOIN giúp tìm **group chỉ có ở nguồn** hoặc **group chỉ có ở đích**, điều mà INNER JOIN có thể che giấu. Ngoài ra cần test **UNIQUE(tenant_id, local_day)** ở bảng báo cáo; nếu đích có hai hàng cùng group, truy vấn đối chiếu có thể trả nhiều dòng dù các số tiền nhìn có vẻ bằng.

### 6.4. Tỷ lệ phải tính từ tử số và mẫu số

Giả sử:

~~~text
Nhóm A: 90 chuyển đổi / 100 cơ hội = 90%
Nhóm B:  1 chuyển đổi /  10 cơ hội = 10%
~~~

Trung bình đơn giản hai tỷ lệ là **50%**, nhưng tỷ lệ trên toàn bộ cơ hội:

\[
\frac{90 + 1}{100 + 10} \times 100\%
= \frac{91}{110}\times100\%
\approx 82{,}73\%.
\]

**Bài kiểm thử:** nếu hợp đồng chỉ số yêu cầu tỷ lệ của tổng tập cơ hội, tính **SUM(numerator) / NULLIF(SUM(denominator), 0)**, không AVG(rate). Khi mẫu số bằng 0, tỷ lệ thường là **không xác định (NULL)** chứ không tự mặc định thành 0%.

### 6.5. Tổng số dư theo thời gian: phép cộng không hợp lệ

Ví dụ một tài khoản có số dư cuối ngày:

~~~text
Ngày 19/11: 100.000 VND
Ngày 20/11: 120.000 VND
Ngày 21/11:  90.000 VND
~~~

**SUM = 310.000 VND** không phải số dư của tài khoản tại một thời điểm nào. Nếu hỏi số dư cuối kỳ thì chọn **snapshot cuối cùng còn hiệu lực tại mốc báo cáo**, ở đây là **90.000 VND**. Nếu hỏi số dư trung bình ngày thì có thể AVG với định nghĩa trọng số/số ngày rõ. Test phải kiểm tra tính **semi-additive** theo thời gian và các kỳ thiếu snapshot, không chỉ xem câu SQL có chạy.

### 6.6. Dữ liệu đến trễ và phạm vi công bố

Nếu một đơn được tạo ngày 20/11 nhưng chỉ được ingest ngày 23/11, báo cáo ngày 20/11 chạy vào 21/11 có thể khác báo cáo tái tính vào 24/11. Muốn so hai phiên bản cần nêu:

- **event time:** ngày đơn thực sự được đặt.
- **ingestion/knowledge time:** thời điểm hệ thống nhận dữ liệu.
- **cutoff/watermark:** tập đầu vào được phép tính và mức đồng bộ nguồn.
- **report version/run ID:** lần tính nào đã được công bố.

Chênh lệch giữa hai lần tính **không tự động là lỗi JOIN**; có thể do dữ liệu đến trễ hoặc công thức/nguồn tham chiếu thay đổi. Đối soát phải dùng **cùng dữ liệu, cùng version và cùng mốc** mới kết luận mô hình nào sai.

## 7. Kiểm thử lịch sử hiệu lực: SCD Type 2 và AS-OF JOIN

Một dimension lịch sử có thể giữ nhiều hàng cho cùng một khách hàng, mỗi hàng mang thuộc tính đúng trong một **khoảng hiệu lực nghiệp vụ (valid time)**. Để một fact được phân loại chính xác tại thời điểm giao dịch, ba bất biến thường cần kiểm tra:

1. Mỗi fact **có đúng một phiên bản dimension phù hợp**.
2. Các phiên bản của cùng khách **không chồng khoảng hiệu lực**, trừ khi mô hình hỗ trợ chủ đích nhiều quan hệ đồng thời và xác định grain khác.
3. Quy ước **biên thời gian, múi giờ, thời gian bắt đầu/kết thúc** được áp dụng nhất quán.

### 7.1. Biên [from, to) tránh hai hàng cùng có hiệu lực ở một thời điểm

Fixture:

~~~text
T01/C01:
  customer_sk = 101, North, [2026-01-01 00:00 +07, 2026-11-20 00:00 +07)
  customer_sk = 102, South, [2026-11-20 00:00 +07, ∞)
~~~

Tại đúng **2026-11-20 00:00 +07**, bản **North đã kết thúc**, bản **South bắt đầu**. Nếu dùng điều kiện **placed_at BETWEEN valid_from AND valid_to** với hai đầu **đều bao gồm**, thời điểm giao biên có thể ghép hai phiên bản. Dùng:

~~~sql
f.placed_at >= c.valid_from
AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
~~~

để biểu diễn đúng quy ước nửa mở.

Kiểm tra hai phía của biên:

~~~sql
WITH probe_times AS (
    SELECT TIMESTAMPTZ '2026-11-19 23:59:59+07'
               AS probe_at
    UNION ALL
    SELECT TIMESTAMPTZ '2026-11-20 00:00:00+07'
)
SELECT
    p.probe_at,
    c.customer_sk,
    c.department
FROM probe_times AS p
JOIN dim_customer_history AS c
  ON c.tenant_id = 'T01'
 AND c.customer_code = 'C01'
 AND p.probe_at >= c.valid_from
 AND (p.probe_at < c.valid_to OR c.valid_to IS NULL)
ORDER BY p.probe_at;
~~~

Kỳ vọng có **đúng hai hàng**: thời điểm trước biên khớp **101/North**, đúng biên khớp **102/South**. Không được dùng timezone mặc định của session để xác định thời điểm so sánh.

### 7.2. Test khoảng hiệu lực chồng nhau

Hai hàng lịch sử có thể mang customer_sk khác nhau nhưng cùng hiệu lực. PRIMARY KEY(customer_sk) **không phát hiện** lỗi này.

~~~sql
SELECT
    a.tenant_id,
    a.customer_code,
    a.customer_sk AS first_version,
    b.customer_sk AS second_version,
    a.valid_from AS first_from,
    a.valid_to AS first_to,
    b.valid_from AS second_from,
    b.valid_to AS second_to
FROM dim_customer_history AS a
JOIN dim_customer_history AS b
  ON a.tenant_id = b.tenant_id
 AND a.customer_code = b.customer_code
 AND a.customer_sk < b.customer_sk
 AND (a.valid_to IS NULL OR b.valid_from < a.valid_to)
 AND (b.valid_to IS NULL OR a.valid_from < b.valid_to);
~~~

Kết quả trên fixture phải **rỗng**. Điều kiện dùng **<**, không dùng **<=**, nên hai khoảng **chạm biên** mà không chồng lấn không bị báo lỗi.

Để chắc test bắt được lỗi, có thể chạy negative test:

~~~sql
BEGIN;

INSERT INTO dim_customer_history (
    customer_sk, tenant_id, customer_code,
    department, valid_from, valid_to
) VALUES (
    199, 'T01', 'C01', 'TestOverlap',
    TIMESTAMPTZ '2026-11-19 00:00:00+07',
    TIMESTAMPTZ '2026-11-21 00:00:00+07'
);

-- Chạy lại overlap test: phải thấy cặp (101, 199) và (102, 199).
-- Chạy match-count test mục 4.4: một số dòng sẽ có 2 match.

ROLLBACK;
~~~

**Không dùng negative test trên môi trường sản xuất.** Với dữ liệu thật, chạy nó trên database thử nghiệm hoặc một transaction cô lập được cho phép. Một test chỉ trả về tập rỗng trên nguồn sạch có thể là test viết sai; thử lỗi được tạo có chủ đích sẽ tăng độ tin cậy.

### 7.3. Có thể chặn overlap ở database không?

Trong PostgreSQL, có thể dùng **exclusion constraint** với range type khi có quyền tạo extension hỗ trợ phép so bằng trên TEXT:

~~~sql
-- Tùy quyền hệ thống và chính sách extension.
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE dim_customer_history
ADD CONSTRAINT ex_customer_no_overlapping_valid_time
EXCLUDE USING gist (
    tenant_id WITH =,
    customer_code WITH =,
    tstzrange(valid_from, valid_to, '[)') WITH &&
);
~~~

Với **valid_to = NULL**, range không có giới hạn trên. Ràng buộc ngăn **hai khoảng hiệu lực chồng nhau cho cùng tenant/customer_code**, kể cả khi hai transaction cố ghi đồng thời. Nó phù hợp khi nghiệp vụ quy định **chỉ một phiên bản được hiệu lực tại một thời điểm**. Không dùng ràng buộc ấy nếu quan hệ thực sự có nhiều trạng thái song song khác grain.

Lưu ý: chỉ thêm constraint **sau khi đã xử lý dữ liệu lịch sử có overlap**; nếu đã có hàng xung đột, PostgreSQL sẽ từ chối tạo. Nếu không thể dùng extension/constraint trong hạ tầng hiện tại, cần xử lý bằng giao thức ghi có khóa phù hợp và test overlap định kỳ, nhưng việc “đã chạy SELECT thấy không overlap” không tự ngăn hai transaction mới tạo overlap về sau.

### 7.4. Test khoảng trống (*gap*) phải theo chính sách nghiệp vụ

**Không overlap** chưa đồng nghĩa **bao phủ toàn bộ thời gian**. Ví dụ C01 có một khoảng kết thúc ngày 19/11, khoảng tiếp theo chỉ bắt đầu 21/11; một fact ngày 20/11 sẽ không tìm được phiên bản hợp lệ.

Với mọi fact phải có dimension hợp lệ, **match-count = 1** ở mục 4.4 đã phát hiện những khoảng trống ảnh hưởng tới fact thực tế. Nếu mô hình yêu cầu **lịch sử liên tục** của mọi customer_code, kể cả những ngày không có fact, cần thêm test giữa các khoảng liên tiếp:

~~~sql
WITH sequenced AS (
    SELECT
        tenant_id,
        customer_code,
        customer_sk,
        valid_from,
        valid_to,
        LAG(valid_to) OVER (
            PARTITION BY tenant_id, customer_code
            ORDER BY valid_from, customer_sk
        ) AS previous_valid_to,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, customer_code
            ORDER BY valid_from, customer_sk
        ) AS version_index
    FROM dim_customer_history
)
SELECT
    tenant_id,
    customer_code,
    customer_sk,
    previous_valid_to,
    valid_from
FROM sequenced
WHERE version_index > 1
  AND previous_valid_to IS DISTINCT FROM valid_from;
~~~

Kết quả rỗng trên fixture. Truy vấn này báo cả gap lẫn một số dạng overlap giữa bản liền kề, nhưng **không thay thế overlap test** và chỉ phù hợp khi mô hình cam kết **chuỗi phiên bản liền mạch**. Một khách hàng có thể rời dịch vụ rồi quay lại, làm khoảng không hiệu lực là **hợp lệ**; khi đó test nên tập trung vào khoảng mà nghiệp vụ yêu cầu tồn tại.

### 7.5. Truy vấn tổng hợp theo thuộc tính tại thời điểm giao dịch

~~~sql
SELECT
    c.department,
    COUNT(*) AS line_count,
    SUM(f.line_amount_vnd) AS sales_vnd
FROM fact_order_line AS f
JOIN dim_customer_history AS c
  ON c.tenant_id = f.tenant_id
 AND c.customer_code = f.customer_code
 AND f.placed_at >= c.valid_from
 AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
GROUP BY c.department
ORDER BY c.department;
~~~

Kết quả:

| department tại lúc đặt | line_count | sales_vnd |
| --- | ---: | ---: |
| North | 3 | 450000 |
| South | 3 | 650000 |

Hai group cộng lại **6 dòng, 1.100.000 VND**. Nếu dùng dimension **hiện tại** (C01 đang South), toàn bộ lịch sử C01 có thể bị phân loại sang South, làm báo cáo phòng ban quá khứ sai dù **tổng tiền toàn hệ thống vẫn bằng nhau**. Vì vậy test phải so **theo chiều lịch sử**, không chỉ tổng cuối.

### 7.6. Khi fact lưu customer_sk thì kiểm tra thế nào?

Trong mô hình sao, fact thường lưu **customer_sk** được ánh xạ lúc nạp. Khi đó JOIN đơn giản **fact.customer_sk = dim.customer_sk** có thể đảm bảo mỗi fact tìm một dimension row bằng FK/PK.

Tuy vậy, **JOIN một–một không chứng minh customer_sk đã được gán đúng phiên bản lịch sử**. Test cần so với business key và thời điểm:

~~~text
for each fact:
  dim.customer_sk = fact.customer_sk
  dim.tenant_id/customer_code tương ứng fact source identity
  dim.valid_from <= fact.placed_at < dim.valid_to
~~~

Nếu fact đã gán customer_sk = 102 cho L01 (ngày 19/11), PK/FK vẫn hợp lệ nhưng **department sẽ sai**. Việc ghi khóa thay thế không thay thế kiểm chứng ánh xạ theo thời gian.

## 8. Phân biệt valid time, system time và hai cách đặt câu hỏi lịch sử

### 8.1. Hai câu hỏi lịch sử không giống nhau

**Valid time** hỏi: *“Điều gì đúng trong thế giới nghiệp vụ tại thời điểm T?”*

**System/knowledge time** hỏi: *“Tại thời điểm K, hệ thống đã biết/ghi nhận điều gì là đúng cho T?”*

Giả sử ngày **23/11**, nhân viên xác nhận lại rằng khách C01 thật ra đã chuyển bộ phận từ **19/11**, không phải từ **20/11** như dữ liệu đã công bố. Báo cáo mới có thể được sửa hồi tố, nhưng báo cáo người dùng nhìn thấy vào **22/11** vẫn dựa trên thông tin cũ.

| Thời điểm giao dịch cần phân loại | Dữ liệu được biết vào 22/11 | Dữ liệu sau correction ngày 23/11 |
| --- | --- | --- |
| 19/11 10:00 +07 | North | South |
| 20/11 09:00 +07 | South | South |

Nếu chỉ có **valid_from/valid_to hiện hành**, việc sửa lịch sử có thể xóa dấu vết “hệ thống từng tin điều gì”. Muốn tái tạo cả hai lần báo cáo, cần **snapshot/version của dimension theo run** hoặc **bitemporal modeling**.

### 8.2. Mô hình hai trục thời gian (*bitemporal*)

Một bảng lịch sử giàu thông tin có thể lưu:

~~~text
customer_code
department
valid_from, valid_to      -- hiệu lực nghiệp vụ
recorded_from, recorded_to -- khoảng thời gian hệ thống ghi nhận
~~~

Các khoảng đều dùng quy tắc **[from, to)**. Truy vấn “đã biết lúc K rằng điều gì có hiệu lực tại T?” phải lọc **cả hai trục**:

~~~sql
-- Mẫu điều kiện khi có bảng bitemporal_customer.
-- Đây không phải bảng trong fixture mục 3.
SELECT b.department
FROM bitemporal_customer AS b
WHERE b.tenant_id = 'T01'
  AND b.customer_code = 'C01'
  AND b.valid_from <= TIMESTAMPTZ '2026-11-19 10:00:00+07'
  AND (
      b.valid_to > TIMESTAMPTZ '2026-11-19 10:00:00+07'
      OR b.valid_to IS NULL
  )
  AND b.recorded_from <= TIMESTAMPTZ '2026-11-22 12:00:00+07'
  AND (
      b.recorded_to > TIMESTAMPTZ '2026-11-22 12:00:00+07'
      OR b.recorded_to IS NULL
  );
~~~

Đây là **mẫu semantic query**. Để trả đúng một kết quả, bảng bitemporal phải có ràng buộc **không overlap valid-time trong cùng một lát system-time** cho cùng đối tượng; không chỉ đặt PK cho một surrogate key. Với các bản correction hồi tố, cần giữ bản ghi cũ trong lịch sử system-time thay vì ghi đè không dấu vết.

### 8.3. Fact và dimension phải dùng cùng phiên bản góc nhìn

Nếu fact là snapshot **run 9001** được tính từ dimension như đã biết ngày 22/11, không được tái hiện lại báo cáo ấy bằng cách JOIN với dimension đã sửa hồi tố ngày 23/11 rồi kết luận số run 9001 “được tính sai” theo dữ liệu mới. Có hai mục đích:

- **Reproduce:** tái tạo đúng những gì run 9001 đã biết và đã công bố.
- **Restate:** tính lại kết quả lịch sử bằng sự thật/logic được chấp nhận mới hơn, tạo **run 9002** với metadata và delta rõ.

Cả hai đều có giá trị. Các test phải xác định đang xác minh **khả năng tái hiện** hay **tính đúng theo dữ liệu được sửa**, không trộn hai mốc để tự tạo sai lệch.

### 8.4. Dữ liệu đến trễ và cập nhật ngược dòng

Một dòng fact xảy ra ngày 19/11 nhưng được nạp ngày 23/11 có thể cần JOIN với dimension có hiệu lực ngày **19/11**, không phải dimension hiện tại ngày **23/11**. Nếu dimension lịch sử cũng đến trễ, pipeline cần xử lý:

- **late-arriving fact:** fact đến sau kỳ nghiệp vụ.
- **late-arriving dimension:** dimension hoặc phiên bản hiệu lực chưa có khi fact được nạp.
- **retrospective correction:** sửa ngày hiệu lực lịch sử.
- **out-of-order events:** sự kiện tới không đúng thứ tự nguồn.

Khi có correction, các bảng tổng hợp theo department/day có thể cần **backfill/restatement**, kể cả khi amount_vnd của fact không thay đổi. Đó là lý do test lịch sử phải nằm trong **quy trình tiến hóa mô hình**, không chỉ ở một truy vấn đọc.

## 9. Kiểm thử ngày, timezone và biên thời gian

### 9.1. Không dùng session timezone ngầm định

Trong PostgreSQL, **TIMESTAMPTZ** biểu diễn thời điểm tuyệt đối. Kết quả ép kiểu **placed_at::DATE** phụ thuộc vào timezone của session. Nếu báo cáo cần ngày địa phương Việt Nam, hãy viết tường minh:

~~~sql
(placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
~~~

Với dòng **L05**:

~~~text
occurred_at bản địa: 2026-11-21 00:30:00 +07
thời điểm UTC:      2026-11-20 17:30:00 Z
report_day VN:       2026-11-21
report_day UTC:      2026-11-20
~~~

Truy vấn kiểm chứng:

~~~sql
SELECT
    line_id,
    (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS vietnam_day,
    (placed_at AT TIME ZONE 'UTC')::DATE
        AS utc_day
FROM fact_order_line
WHERE line_id = 'L05';
-- L05: vietnam_day = 2026-11-21; utc_day = 2026-11-20.
~~~

Nếu chuyển rule từ UTC sang ngày Việt Nam, doanh số có thể **dịch giữa hai ngày** dù tổng toàn kỳ không đổi. Vì vậy test nên có giao dịch ngay trước/sau nửa đêm địa phương.

### 9.2. Kiểm tra khoảng thời gian [start, end) cho dữ liệu giao dịch

Một báo cáo một ngày thường nên chọn:

~~~sql
SELECT SUM(line_amount_vnd) AS sales_vnd
FROM fact_order_line
WHERE placed_at >= TIMESTAMPTZ '2026-11-20 00:00:00+07'
  AND placed_at <  TIMESTAMPTZ '2026-11-21 00:00:00+07';
-- 450000 VND, gồm L03 và L04.
~~~

Không dùng **BETWEEN** với hai đầu là timestamp đóng khi ghép các khoảng ngày liên tiếp: một sự kiện đúng mốc 00:00 có thể được đếm ở **cả hai khoảng**. Với vùng có DST, khoảng từ nửa đêm này tới nửa đêm kế tiếp theo múi giờ địa phương có thể không luôn dài đúng 24 giờ; cần chuyển đúng **hai mốc lịch địa phương** sang thời điểm tuyệt đối, thay vì mặc định cộng 24 giờ cho mọi ngày trên thế giới.

### 9.3. Những ca biên cần có trong fixture

| Ca thử | Tại sao cần? |
| --- | --- |
| Một sự kiện đúng **valid_from** | Phải thuộc phiên bản mới |
| Một sự kiện đúng **valid_to** của phiên bản cũ | Không thuộc phiên bản cũ nếu quy tắc [from, to) |
| Một sự kiện cách mốc chuyển phiên bản 1 giây | Bắt lỗi nhầm hai đầu khoảng |
| Một giao dịch 00:00 hoặc 23:59:59 theo timezone báo cáo | Bắt lỗi phân nhóm ngày |
| Một fact đến trễ so với ngày nghiệp vụ | Kiểm tra as-of/cutoff/backfill |
| Một correction hiệu lực về quá khứ | Kiểm tra restatement và tính tái hiện |
| Không có dimension trong một khoảng | Bắt lỗi orphan/gap |
| Hai phiên bản lịch sử overlap | Bắt lỗi fanout |

**Một test dữ liệu thời gian chỉ dùng ngày giữa tháng** rất khó phát hiện sai lệch ở biên, nơi nhiều lỗi thực tế xảy ra.

## 10. Từ truy vấn phát hiện sai lệch tới kiểm thử tự động

Để các điều kiện trong bài trở thành regression test, nên quy ước:

- **Kiểm tra dạng truy vấn sai lệch:** thành công khi kết quả **không có hàng**.
- **Kiểm tra số đo bất biến:** thành công khi số thực tế bằng số kỳ vọng đã được phê duyệt.
- **Kiểm tra ngoại lệ:** thành công khi thao tác sai bị chặn hoặc lỗi được phát hiện đúng loại.
- **Kiểm tra hồi quy lịch sử:** thành công khi cùng fixture, version và cutoff tạo cùng tập kết quả.

### 10.1. Bọc assertion vào PostgreSQL DO block

Ví dụ khối kiểm thử sau có thể chạy **sau DDL và INSERT ở mục 3**:

~~~sql
DO $$
DECLARE
    v_line_count BIGINT;
    v_total NUMERIC;
    v_bad_matches BIGINT;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(line_amount_vnd), 0)
    INTO v_line_count, v_total
    FROM fact_order_line;

    IF v_line_count <> 6 OR v_total <> 1100000 THEN
        RAISE EXCEPTION
            'Fixture sai: lines=%, total=% (expected 6, 1100000)',
            v_line_count, v_total;
    END IF;

    WITH match_counts AS (
        SELECT
            f.line_id,
            COUNT(c.customer_sk) AS matches
        FROM fact_order_line AS f
        LEFT JOIN dim_customer_history AS c
          ON c.tenant_id = f.tenant_id
         AND c.customer_code = f.customer_code
         AND f.placed_at >= c.valid_from
         AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
        GROUP BY f.line_id
    )
    SELECT COUNT(*)
    INTO v_bad_matches
    FROM match_counts
    WHERE matches <> 1;

    IF v_bad_matches <> 0 THEN
        RAISE EXCEPTION
            'Temporal JOIN không 1-1 tại grain line: % dòng lỗi',
            v_bad_matches;
    END IF;

    RAISE NOTICE 'PASS: fixture và temporal JOIN đúng grain';
END $$;
~~~

Khối này là một **minh họa assertion** cho fixture, không phải bằng chứng PostgreSQL đã được chạy trong lúc viết tài liệu. Trong hệ CI, lỗi **RAISE EXCEPTION** phải khiến tiến trình kiểm thử trả kết quả thất bại; không được cấu hình runner bỏ qua exit code.

### 10.2. So sánh SQL đầu ra với oracle thay vì chỉ kiểm tra số dòng

Với dữ liệu cố định, có thể dùng **EXCEPT hai chiều** để so tập giá trị:

~~~sql
WITH actual AS (
    SELECT
        c.department,
        COUNT(*)::BIGINT AS line_count,
        SUM(f.line_amount_vnd) AS sales_vnd
    FROM fact_order_line AS f
    JOIN dim_customer_history AS c
      ON c.tenant_id = f.tenant_id
     AND c.customer_code = f.customer_code
     AND f.placed_at >= c.valid_from
     AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
    GROUP BY c.department
),
expected AS (
    SELECT *
    FROM (
        VALUES
            ('North'::TEXT, 3::BIGINT, 450000::NUMERIC),
            ('South'::TEXT, 3::BIGINT, 650000::NUMERIC)
    ) AS x(department, line_count, sales_vnd)
),
differences AS (
    (SELECT * FROM expected EXCEPT SELECT * FROM actual)
    UNION ALL
    (SELECT * FROM actual EXCEPT SELECT * FROM expected)
)
SELECT * FROM differences;
~~~

Kỳ vọng **không có hàng**. **EXCEPT** theo ngữ nghĩa tập loại trùng các bộ giá trị; nó phù hợp khi mỗi group phải duy nhất. Nếu cần so **đa tập (multiset)** có số lần xuất hiện, dùng **EXCEPT ALL** hoặc kiểm tra uniqueness riêng. Một bộ dữ liệu có hai hàng giống nhau không được coi là hợp lệ chỉ vì phép so tập đã loại trùng.

### 10.3. Test số liệu theo nhiều chiều, không chỉ một tổng

Một chương trình test hữu ích có thể kiểm tra đồng thời:

~~~text
source:
  line_count = 6
  distinct_order_count = 5
  sales = 1,100,000
  quantity = 14

historical_join:
  rows = 6
  unmatched = 0
  multiply_matched = 0
  North.sales = 450,000
  South.sales = 650,000

payment:
  payment_events = 6
  paid_sum = 1,100,000
  O1001 has 2 lines and 2 payments

daily:
  T01/19-11 = 300,000
  T01/20-11 = 450,000
  T01/21-11 = 100,000
  T02/21-11 = 250,000
~~~

Những số kỳ vọng chỉ dành cho **fixture trong bài**. Trong hệ thật, oracle có thể là bản xuất đã chốt từ nguồn chuẩn, tập kết quả đã được review hoặc bộ tính độc lập, không phải giá trị được tự động lấy từ cùng truy vấn đang kiểm thử.

### 10.4. Tránh “test cùng lỗi với mã cần kiểm tra”

Nếu pipeline và test cùng gọi một hàm sai để tính ngày, chúng có thể **khớp nhau nhưng đều sai**. Hãy kết hợp:

1. **Expected values cố định do nghiệp vụ phê duyệt** cho vài fixture nhỏ.
2. **Test bất biến độc lập:** grain, match-count, tập khóa, sum nguồn.
3. **Test hành vi biên:** cùng timestamp ở hai phía valid_from/valid_to và nửa đêm.
4. **Kiểm tra từ nguồn khác:** ledger/payment hoặc báo cáo chuyên trách với định nghĩa đã đối chiếu.
5. **Review quy tắc:** liệu SQL thật sự diễn đạt chính xác câu hỏi kinh doanh?

Một test không thể chứng minh đúng tuyệt đối; nó làm tăng khả năng phát hiện lỗi trong **những điều kiện được thiết kế để kiểm tra**.

## 11. Negative test và kiểm thử thuộc tính (*property/metamorphic*)

### 11.1. Bộ lỗi chủ động cần gieo vào fixture thử nghiệm

| Lỗi được gieo | Dấu hiệu kỳ vọng | Test chịu trách nhiệm |
| --- | --- | --- |
| Thêm một hàng dimension overlap C01 | Một số line có **match_count > 1** | Temporal join match-count, overlap |
| Thêm fact khách C99 không có dimension | Một line có **match_count = 0** | Anti-join/left match-count |
| Bỏ tenant_id khỏi JOIN | Dữ liệu có thể khớp khách cùng mã khác tenant | Cross-tenant isolation |
| JOIN line thẳng với hai payment của O1001 | Tổng tăng từ 1,1 lên **1,4 triệu** | Aggregate reconciliation và fanout |
| JOIN fact với mọi phiên bản SCD | Tổng tăng lên **1,8 triệu** | Fanout + as-of |
| Thay ngày VN bằng UTC cho L05 | L05 dịch từ 21/11 sang 20/11 | Day-boundary oracle |
| Dùng BETWEEN bao gồm cả valid_to | Fact đúng biên khớp hai phiên bản | Boundary test |
| Cộng DISTINCT khách theo từng ngày | 5 lượt khách–ngày thay vì 3 khách duy nhất | Distinct-count rule |
| Nhân đôi một payment với ID khác khi retry | Paid sum tăng | Idempotency/source event uniqueness |
| Báo cáo bỏ một group tenant–ngày | Tổng có thể sai hoặc bị bù trừ | FULL OUTER JOIN hoặc EXCEPT hai chiều |
| Sửa dimension lịch sử hồi tố | Group theo phòng ban của quá khứ đổi | Bitemporal/restate regression |

Các thử nghiệm này nên chạy trên môi trường test cô lập và có bước làm sạch sau test, không làm biến đổi dữ liệu vận hành của người dùng.

### 11.2. Metamorphic test: khi đầu vào đổi có kiểm soát, kết quả nào phải giữ?

Với một số truy vấn, khó tạo oracle đầy đủ cho hàng triệu bản ghi, nhưng vẫn xác lập được **quan hệ bất biến khi biến đổi đầu vào**.

**Thuộc tính A — đổi thứ tự các hàng nguồn:** nếu chỉ dùng SUM trên cùng tập dòng, kết quả không được đổi khi thay thứ tự INSERT/đọc. Nếu SQL phụ thuộc “hàng đầu tiên” không có ORDER BY xác định, đây có thể là dấu hiệu thiết kế thiếu quy tắc.

**Thuộc tính B — tách một dòng hàng thành hai dòng hợp lệ:** nếu dòng 300.000 được tách thành hai dòng 100.000 và 200.000 trong **cùng order, cùng tenant và cùng thời điểm phân loại**, tổng tiền phải giữ, nhưng **số dòng sẽ tăng một**. Vì vậy test cần phân biệt chỉ số **line_count** và **sales_vnd**.

**Thuộc tính C — thêm một payment vào cùng đơn:** khi chỉ muốn tổng **line_amount_vnd**, việc thêm sự kiện payment mới **không được làm thay đổi tổng bán**. Nếu tổng bán tăng theo số payment, JOIN đã nhân hàng.

**Thuộc tính D — thêm phiên bản SCD có hiệu lực ở tương lai:** với những fact xảy ra **trước valid_from của phiên bản mới**, phân loại lịch sử phải giữ nguyên, trừ khi nghiệp vụ cố ý sửa hồi tố.

**Thuộc tính E — thêm bản ghi ngoài phạm vi lọc:** số liệu của tenant T01 không được thay đổi khi thêm một giao dịch chỉ thuộc tenant T02, nếu không có quy tắc chia sẻ số liệu xuyên tenant.

**Thuộc tính F — phân hoạch rồi gộp lại đúng:** SUM tổng tiền của những nhóm **rời nhau và bao phủ toàn bộ nguồn** phải bằng SUM nguồn. Đối với COUNT DISTINCT khách, không được dùng phép cộng này nếu khách xuất hiện ở nhiều nhóm.

### 11.3. Một ví dụ test tính không phụ thuộc số payment

Chạy trong transaction để không giữ dữ liệu thử:

~~~sql
BEGIN;

-- Tổng bán nguồn trước khi thêm payment:
SELECT SUM(line_amount_vnd) AS sales_before
FROM fact_order_line;
-- 1100000.

-- Thêm event thanh toán mới cho O1001 trong fixture thử nghiệm.
INSERT INTO payment_event (
    payment_id, tenant_id, order_id, paid_at, paid_vnd
) VALUES (
    'P_TEST', 'T01', 'O1001',
    TIMESTAMPTZ '2026-11-19 10:07:00+07', 10000
);

-- Tổng bán độc lập từ fact line phải vẫn là 1100000.
SELECT SUM(line_amount_vnd) AS sales_after
FROM fact_order_line;

-- Nếu truy vấn bán hàng bị phụ thuộc số payment thì
-- kết quả JOIN sai ở mục 5.1 sẽ thay đổi.

ROLLBACK;
~~~

Mục tiêu không phải nói payment mới chắc chắn hợp lệ trong nghiệp vụ; đây là **biến đổi kiểm thử** để chứng minh phép tính của một metric không phụ thuộc vào quan hệ không liên quan đến grain của nó.

### 11.4. Tại sao kiểm thử ngẫu nhiên vẫn cần các ca biên cố định?

Property-based testing có thể sinh số dòng đơn, số payment, khoảng valid-time, tenant và timestamp khác nhau để kiểm tra các bất biến:

~~~text
For every generated fact line:
  count(as_of_dimension_matches) == 1

For any payment fanout change:
  total_sale_amount == SUM(source_line_amount)

For any pair of customer history rows:
  no overlapping valid-time intervals within the same business key
~~~

Nhưng nếu bộ sinh ngẫu nhiên hiếm khi sinh một sự kiện đúng **2026-11-20 00:00:00+07**, lỗi biên có thể vẫn bị bỏ sót. Hãy **giữ ca biên cố định**, dùng ngẫu nhiên để tăng độ phủ, và lưu **seed + fixture + transform version** khi một test thất bại để có thể tái tạo.

## 12. Kiểm thử khi mô hình và pipeline tiến hóa

### 12.1. Thay đổi schema không được làm thay đổi ngữ nghĩa chỉ số ngoài ý muốn

Giả sử v1 dùng **customer_code** để nối khách hiện hành, v2 thêm **customer_sk** lịch sử. Việc đổi schema có thể được deploy thành công, nhưng các báo cáo cũ có thể đổi phân bố phòng ban.

Một quy trình kiểm chứng nên so:

- **Những chỉ số được cam kết không đổi:** tổng số line, tổng giá trị dòng hàng, định danh đơn nguồn.
- **Những chỉ số được chấp nhận đổi:** báo cáo theo phòng ban tại thời điểm giao dịch có thể thay đổi so với báo cáo phân nhóm khách hiện hành, vì **ngữ nghĩa đã được sửa**.
- **Phạm vi ảnh hưởng:** tenant/ngày/order nào đổi và nguyên nhân?
- **Khả năng replay:** cùng input snapshot và transform version có tạo cùng output không?

Đừng đặt mục tiêu “mọi số trước/sau migration phải giống nhau” nếu migration nhằm sửa một chỉ số vốn đã sai. Cần định nghĩa chính xác **những bất biến nào phải giữ** và **những khác biệt nào được phê duyệt**.

### 12.2. Reconciliation khi backfill lịch sử

Backfill bảng fact có thể chạy theo từng batch. Việc có checkpoint và row count khớp không đủ:

1. **Snapshot nguồn và transform version:** xác định tập dữ liệu đối chiếu.
2. **Phạm vi khóa:** mọi nguồn đủ điều kiện có fact đích, không có fact thừa.
3. **Row-level values:** tiền, tenant, thời điểm, customer identity, phân loại SCD đúng.
4. **Group aggregates:** tổng theo ngày, tenant, department.
5. **Late event/correction:** sau snapshot cần catch-up theo chính sách để công bố dữ liệu hiện hành.
6. **Publish/rollback:** chỉ chuyển dashboard sang phiên bản mới sau khi nghiệm thu và theo dõi so sánh bóng.

Nếu nguồn có ghi mới, **MAX(id)** hoặc thời điểm nạp không tự đảm bảo snapshot đủ; cần snapshot/capture không có khoảng trống, commit position hoặc cơ chế đồng bộ phù hợp.

### 12.3. Kiểm thử kết quả “as-of phiên bản công bố”

Khi đã dùng hệ thống có nhiều lần chạy:

~~~text
run_id = 9001, source_cutoff = 2026-11-22 00:00 +07,
dim_history_version = V1, metric_version = M1

run_id = 9002, source_cutoff = 2026-11-24 00:00 +07,
dim_history_version = V2, metric_version = M1
~~~

Một phép so sánh có thể dùng run 9001 làm **bằng chứng số đã công bố** và run 9002 làm **số được restate**. Test phải giải thích delta: đến trễ, correction hay thay đổi dimension history. Không nên JOIN các bản tổng hợp của hai run mà bỏ run_id rồi kết luận có duplicate.

### 12.4. Test dữ liệu thật, chạy ở phạm vi kiểm soát

Fixture nhỏ giúp giải thích lỗi, nhưng workload thực có thể tạo những quan hệ hiếm gặp:

- Một order có hàng trăm dòng và hàng chục payment.
- Một khách hàng có hàng chục phiên bản SCD và nhiều lần sửa hồi tố.
- Một tenant có ID giống tenant khác ở các hệ nguồn riêng.
- Một payment đến trước order hoặc bị retry trùng ID.
- Một ngày báo cáo có quy tắc timezone khác vì vùng địa lý/DST.
- Một bảng dimension có orphan/gap hoặc chồng khoảng do dữ liệu cũ.

Với dữ liệu production, nên chạy **data quality test có giới hạn tài nguyên**, hoặc trên bản sao/snapshot phù hợp; truy vấn GROUP BY toàn bảng và FULL OUTER JOIN lớn có thể tốn tài nguyên. Chọn partition/sample có mục đích và có lịch kiểm tra toàn diện theo yêu cầu rủi ro.

### 12.5. Test hiệu năng sau khi đã test tính đúng

Mô hình đúng vẫn có thể không đạt SLO:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.department,
    SUM(f.line_amount_vnd)
FROM fact_order_line AS f
JOIN dim_customer_history AS c
  ON c.tenant_id = f.tenant_id
 AND c.customer_code = f.customer_code
 AND f.placed_at >= c.valid_from
 AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
GROUP BY c.department;
~~~

EXPLAIN ANALYZE thực sự chạy SELECT; trong môi trường thật, chỉ dùng khi có quyền và khung tài nguyên phù hợp. Đánh giá chỉ mục (tenant_id, customer_code, valid_from), phân bố thời gian, kích thước lịch sử và khả năng dùng **GiST range index** nếu hệ quản trị hỗ trợ.

**Đừng tối ưu bằng cách bỏ điều kiện thời gian**: nó có thể làm JOIN nhanh hơn nhưng làm sai dữ liệu. Các quyết định dùng materialized view, denormalization hoặc pre-aggregation phải đi kèm test bảo vệ grain và khả năng tái tính.

## 13. Áp dụng nguyên tắc kiểm chứng cho mô hình khác

### 13.1. Relational OLTP

Trong một thiết kế giao dịch chuẩn hóa, **PRIMARY KEY**, **UNIQUE**, **FOREIGN KEY**, **CHECK** và các ràng buộc khoảng thời gian có thể ngăn nhiều lỗi tại lúc ghi. Nhưng chúng không tự bảo vệ phép tổng của một truy vấn sai grain:

- FK từ dòng đơn tới order chỉ xác nhận dòng có cha; nó không nói JOIN nhiều thanh toán có thể nhân dòng.
- UNIQUE(customer_sk) không bảo vệ các khoảng SCD trùng nhau.
- CHECK(amount >= 0) không bảo vệ việc cộng amount hai lần.
- UNIQUE theo order_id có thể sai nếu mã đơn chỉ duy nhất trong tenant.

Tốt nhất kết hợp **ràng buộc schema** để chặn trạng thái bất hợp lệ từ gốc, **assertion truy vấn** để kiểm tra quan hệ và **reconciliation** để xác minh số liệu dẫn xuất.

### 13.2. Star schema và data warehouse

Trong kho phân tích, hãy xác định:

- Fact nào là **transaction fact**, **periodic snapshot** hoặc **accumulating snapshot**?
- Dimension có **surrogate key** một phiên bản hay là bảng lịch sử nhiều phiên bản?
- Measure nào **additive**, **semi-additive** hoặc **non-additive**?
- Có dùng **conformed dimensions** cùng ý nghĩa giữa các fact không?
- Có **bridge table** nhiều–nhiều và cần phân bổ trọng số không?

Nếu một đơn có nhiều tag và dùng bridge **order_tag**, tổng tiền theo tag có thể **cố ý xuất hiện ở nhiều tag**. Khi đó **SUM theo mọi tag** có thể vượt tổng đơn là **đúng theo metric “tag attribution không phân bổ”** nhưng sẽ sai nếu được trình bày như **doanh thu duy nhất không trùng lặp**. Hãy nêu rõ chính sách phân bổ, ví dụ mỗi đơn có ba tag, mỗi tag nhận 1/3 giá trị theo một phiên bản quy tắc; kiểm tra tổng trọng số bằng 1 trong phạm vi đơn.

### 13.3. Document database

Một document đơn hàng có thể chứa:

~~~json
{
  "order_id": "O1001",
  "line_items": [
    {"line_id": "L01", "amount_vnd": 100000},
    {"line_id": "L02", "amount_vnd": 200000}
  ],
  "payments": [
    {"payment_id": "P01", "amount_vnd": 200000},
    {"payment_id": "P02", "amount_vnd": 100000}
  ]
}
~~~

Nếu một pipeline **unwind** cả line_items và payments trước khi cộng tiền, nó có thể sinh **2 × 2 = 4 tổ hợp** tương tự JOIN N–M trong SQL. Việc nhúng dữ liệu vào JSON **không tự loại bỏ fanout**. Phải kiểm thử đúng grain ở từng lần unnest/unwind và không nhân số đo của phần tử bên này theo số phần tử bên kia.

### 13.4. Graph database

Trong graph, một khách hàng có thể được nối tới nhiều nhãn, nhiều tổ chức và nhiều đường đi đến cùng một đơn. Một truy vấn traversal trả **nhiều path** không đồng nghĩa có nhiều **đơn duy nhất**. Nếu metric là số đơn, cần kiểm tra **dedup theo identity của order**; nếu metric là số đường liên kết, đếm path có thể đúng.

Với quan hệ có hiệu lực thời gian trên cạnh, truy vấn graph cũng phải chọn **cạnh có hiệu lực tại thời điểm sự kiện**, không tự dùng cạnh hiện hành. Các bất biến về cardinality, thời gian và tenant isolation vẫn giữ nguyên.

### 13.5. Event-sourced và phân tích streaming

Một dòng trạng thái được sửa nhiều lần không nhất thiết là nhiều giao dịch doanh thu. Consumer có thể nhận retry hoặc các event không đúng thứ tự. Nếu SUM thẳng mọi bản cập nhật:

~~~text
order O1001 version 1: total = 300000
order O1001 version 2: total = 320000
~~~

sẽ tạo sai **620.000** nếu hai bản là **hai snapshot trạng thái**, không phải hai event tài chính độc lập. Cần xác định **snapshot update**, **delta event** hay **fact giao dịch bất biến**, rồi kiểm tra source_event_id/source_version, checkpoint, dedup và sự kiện đến trễ.

Đây là khác biệt bản chất của **grain sự kiện** chứ không phải lỗi SUM thuần túy. Một thiết kế kiểm chứng tốt phải bắt đầu bằng hợp đồng nguồn, không chỉ bằng cách thêm DISTINCT vào truy vấn.

## 14. Bài tập vận dụng

### Bài 1. Đo tác động của JOIN với SCD không có điều kiện thời gian

Đọc lại dữ liệu mẫu mục 3. Khách T01/C01 có **hai phiên bản dimension** và xuất hiện trong bốn dòng fact.

**Yêu cầu:**

1. Sau khi JOIN fact_order_line với dim_customer_history chỉ theo tenant_id/customer_code, có bao nhiêu hàng?
2. Tổng line_amount_vnd sau JOIN là bao nhiêu?
3. Vì sao tổng tăng dù bảng fact không có dòng trùng?
4. Viết điều kiện JOIN đúng để phân loại theo phòng ban **tại lúc đặt**.
5. Số dòng và tổng tiền sau JOIN đúng phải là bao nhiêu?

<details>
<summary>Gợi ý lời giải bài 1</summary>

JOIN thiếu điều kiện thời gian tạo **10 hàng**. Bốn dòng C01 mỗi dòng được nhân hai, làm cộng lại thêm tổng **700.000 VND** và doanh số sai thành **1.800.000 VND**.

Điều kiện đúng:

~~~sql
ON c.tenant_id = f.tenant_id
AND c.customer_code = f.customer_code
AND f.placed_at >= c.valid_from
AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
~~~

Sau JOIN đúng phải có **6 dòng, 1.100.000 VND**; North **450.000**, South **650.000**. Ngoài kiểm tra tổng, phải xác minh **mỗi line_id có đúng một c.customer_sk**.

</details>

### Bài 2. Hai nguồn 1–N và phép nhân hàng

Đơn O1001 có:

~~~text
line_items: L01 = 100000, L02 = 200000
payments:  P01 = 200000, P02 = 100000
~~~

**Yêu cầu:**

1. JOIN hai bảng theo order_id tạo bao nhiêu dòng cho O1001?
2. SUM(line_amount_vnd) và SUM(paid_vnd) trên JOIN của riêng O1001 thành bao nhiêu?
3. Vì sao các tổng đó đều sai dù bằng nhau?
4. Nếu muốn so giá trị hàng hóa với tổng đã thanh toán theo đơn, giải pháp SQL nào đúng grain?

<details>
<summary>Gợi ý lời giải bài 2</summary>

JOIN tạo **2 × 2 = 4** dòng. Nó khiến mỗi dòng bán xuất hiện hai lần và mỗi payment xuất hiện hai lần; cả hai SUM cùng thành **600.000 VND**, dù tổng thật của từng nguồn chỉ **300.000 VND**.

Phải **GROUP BY (tenant_id, order_id)** riêng trên từng fact:

~~~sql
WITH sales AS (
    SELECT tenant_id, order_id, SUM(line_amount_vnd) AS amount
    FROM fact_order_line
    GROUP BY tenant_id, order_id
),
payments AS (
    SELECT tenant_id, order_id, SUM(paid_vnd) AS amount
    FROM payment_event
    GROUP BY tenant_id, order_id
)
SELECT s.tenant_id, s.order_id,
       s.amount AS sales_vnd,
       p.amount AS paid_vnd
FROM sales AS s
LEFT JOIN payments AS p
  ON p.tenant_id = s.tenant_id
 AND p.order_id = s.order_id
WHERE s.order_id = 'O1001'
  AND s.tenant_id = 'T01';
~~~

Kết quả đúng: **sales_vnd = 300000**, **paid_vnd = 300000**.

</details>

### Bài 3. Đếm người duy nhất qua nhiều ngày

Dữ liệu mẫu có số khách duy nhất:

~~~text
19/11: {T01/C01}
20/11: {T01/C01, T01/C02}
21/11: {T01/C01, T02/C03}
~~~

**Yêu cầu:**

1. Tổng COUNT(DISTINCT customer) của từng ngày là bao nhiêu?
2. COUNT DISTINCT trên cả khoảng là bao nhiêu?
3. Sự khác nhau biểu diễn điều gì?
4. Nếu chỉ còn bảng daily_unique_customer_count, có thể tính chính xác số khách duy nhất cả kỳ từ ba số đếm đó không?

<details>
<summary>Gợi ý lời giải bài 3</summary>

Tổng của số khách duy nhất theo ngày là **1 + 2 + 2 = 5 lượt khách–ngày**. Số khách nghiệp vụ khác nhau trên cả kỳ là **3**: T01/C01, T01/C02 và T02/C03.

Nếu chỉ giữ ba con số 1, 2, 2 mà không giữ **định danh khách hoặc cấu trúc tập có thể hợp nhất**, không thể suy ra chính xác số khách khác nhau cả kỳ. Các tập có thể giao nhau với mức độ khác nhau. Cần COUNT DISTINCT trên tập dữ liệu đủ chi tiết hoặc cấu trúc chuyên biệt với độ chính xác/ước lượng được công bố rõ.

</details>

### Bài 4. Kiểm thử biên hiệu lực và biên ngày

Dimension của C01 có:

~~~text
North: valid_to   = 2026-11-20 00:00 +07
South: valid_from = 2026-11-20 00:00 +07
~~~

L05 được đặt lúc **2026-11-21 00:30 +07**.

**Yêu cầu:**

1. Fact C01 đúng thời điểm 20/11 00:00 +07 thuộc North hay South?
2. Vì sao không dùng BETWEEN với hai biên đóng?
3. L05 thuộc ngày nào nếu nhóm theo UTC, ngày nào theo Asia/Ho_Chi_Minh?
4. Khi nào việc cộng một khoảng 24 giờ từ nửa đêm không phù hợp để tính ngày địa phương?

<details>
<summary>Gợi ý lời giải bài 4</summary>

Đúng 20/11 00:00 +07, **South** đã có hiệu lực, North đã kết thúc, vì dùng **[from, to)**. BETWEEN với hai đầu đóng có thể khiến cả hai phiên bản cùng được chọn ở thời điểm giao.

L05 ở **2026-11-20 17:30 UTC**, nên ngày UTC là **20/11** và ngày Việt Nam là **21/11**. Với múi giờ có DST, một ngày lịch có thể dài **23 hoặc 25 giờ**, do đó cần tính mốc đầu/cuối theo timezone địa phương thay vì giả định mọi ngày dài 24 giờ.

</details>

### Bài 5. Overlap, orphan và điều kiện match-count

Một nhóm thêm vào dim_customer_history một hàng **customer_sk = 199**, cùng **T01/C01**, có khoảng:

~~~text
[2026-11-19 00:00 +07, 2026-11-21 00:00 +07)
~~~

Sau đó một fact mới có **tenant T01/customer C99** được nạp nhưng không có dimension tương ứng.

**Yêu cầu:**

1. Những dòng L01–L06 nào có thể khớp nhiều hơn một phiên bản lịch sử?
2. Test nào tìm overlap dimension mà không cần JOIN fact?
3. Test nào phát hiện cả dòng không khớp và dòng khớp nhiều bản?
4. Vì sao PRIMARY KEY(customer_sk) không chặn được overlap?

<details>
<summary>Gợi ý lời giải bài 5</summary>

L01 và L02 ở ngày 19/11 khớp bản North và bản 199; L03 ngày 20/11 khớp bản South và bản 199. L06 ngày 21/11 16:00 không nằm trong khoảng của bản 199. Do đó **L01, L02, L03** có **match_count = 2**.

Test overlap có thể tự JOIN dim_customer_history theo cùng tenant/customer_code, hai customer_sk khác nhau và điều kiện hai khoảng giao nhau. Test **LEFT JOIN fact → SCD rồi GROUP BY line_id, COUNT(customer_sk) <> 1** tìm được cả **0** và **nhiều hơn 1** match.

PRIMARY KEY(customer_sk) chỉ bảo vệ ID từng phiên bản, không bảo vệ **duy nhất theo khóa nghiệp vụ và khoảng thời gian**. Có thể dùng exclusion constraint trên range nếu chính sách hạ tầng cho phép.

</details>

### Bài 6. Correction hồi tố làm thay đổi phân bố, không đổi tổng

Ban đầu hệ thống biết T01/C01 chuyển từ North sang South **ngày 20/11 00:00 +07**. Ngày 23/11 có correction cho rằng ngày chuyển thực tế là **19/11 00:00 +07**.

**Yêu cầu:**

1. Tổng line_amount_vnd của toàn fixture có đổi không?
2. Số tiền theo North và South sau khi restate là bao nhiêu?
3. Muốn tái hiện báo cáo theo dữ liệu đã biết ngày 22/11 thì cần điều kiện/metadata gì?
4. Vì sao chỉ UPDATE trực tiếp valid_from ở dimension hiện hành có thể làm mất khả năng kiểm toán?

<details>
<summary>Gợi ý lời giải bài 6</summary>

Tổng vẫn **1.100.000 VND**, vì không có line hoặc số tiền nào thay đổi. Hai dòng L01 và L02 (tổng **300.000 VND**) chuyển phân loại từ North sang South.

Do đó **North mới = 450.000 − 300.000 = 150.000 VND**, **South mới = 650.000 + 300.000 = 950.000 VND**. Đây là **restatement theo sự thật sửa hồi tố**, không phải cộng thêm doanh thu.

Để tái hiện bản đã công bố ngày 22/11, cần snapshot/phiên bản dimension theo run, hoặc bitemporal history có cả valid-time và recorded/system-time, cùng transform version/cutoff. Nếu sửa đè bản cũ không giữ lịch sử ghi nhận, khó chứng minh vì sao hai phiên bản báo cáo khác nhau.

</details>

### Bài 7. Tổng và số hàng đều bằng, vậy có thể sai không?

Một bảng nguồn có các hàng:

~~~text
id=A, amount=100000
id=B, amount=200000
id=C, amount=300000
~~~

Bảng đích:

~~~text
id=A, amount=150000
id=B, amount=150000
id=C, amount=300000
~~~

**Yêu cầu:** đánh giá các test COUNT(*) và SUM(amount). Đề xuất một test phát hiện sai lệch dù hai test này đều PASS.

**Hướng giải:** cả nguồn và đích có **3 hàng, tổng 600.000 VND** nên COUNT/SUM không phát hiện lỗi. Cần **FULL OUTER JOIN theo id** rồi so amount bằng **IS DISTINCT FROM**, hoặc EXCEPT ALL trên toàn bộ các cột cần đối chiếu. Nên kiểm tra cả **tập khóa** để phát hiện một hàng thiếu và một hàng thừa bù nhau.

### Bài 8. Thiết kế bộ kiểm thử trước khi cho phép cutover

Một data mart mới đã qua kiểm tra row count và doanh thu toàn hệ thống, nhưng chưa kiểm tra khoảng SCD, dữ liệu đến trễ và truy vấn theo tenant. Nhóm muốn chuyển mọi dashboard sang mô hình mới ngay.

**Yêu cầu:** đề xuất tối thiểu sáu điều kiện trước khi cho phép công bố.

**Hướng giải:** cần hợp đồng grain và nguồn/cutoff; kiểm tra khóa/trùng/orphan; match-count SCD = 1, overlap/gap và as-of; đối soát tiền theo tenant/day/department; kiểm tra paid fact không nhân dòng; xử lý late event/correction; so số liệu bằng shadow query; kiểm tra tenant isolation; SLO/performance; có run version, rollback và giám sát sau chuyển. Đếm hàng và tổng toàn kỳ **chưa đủ**.

## 15. Checklist nghiệm thu phép nối, phép tổng hợp và lịch sử

| Nhóm | Câu hỏi cần kiểm chứng | Ví dụ bằng chứng |
| --- | --- | --- |
| **Grain fact** | Một hàng fact là một dòng, một đơn hay một event? | Data contract, PK, kiểm tra duplicate |
| **Khóa nghiệp vụ** | ID có duy nhất theo tenant, hệ nguồn hay toàn cục? | UNIQUE đúng phạm vi, fixture trùng mã khác tenant |
| **Join N–1** | Mỗi fact có đúng một match bên dimension không? | COUNT(dim_key) theo fact key bằng 1 |
| **Join 1–N** | Có chủ đích nhân hàng để đếm quan hệ con không? | Expected multiplicity theo khóa cha |
| **Join N–M** | Các số đo đã được tiền tổng hợp đúng grain chưa? | So nguồn độc lập với tổng sau JOIN |
| **Orphan** | Có hàng không match nhưng bị INNER JOIN che mất? | NOT EXISTS/anti-join |
| **Độ đủ của khóa JOIN** | Có đầy đủ tenant/source/ID/version không? | Cross-tenant negative test |
| **Dimension lịch sử** | Các khoảng hiệu lực có chồng nhau không? | Overlap test hoặc exclusion constraint |
| **Dimension lịch sử** | Fact có nằm trong gap không? | AS-OF match-count bằng 1 |
| **Biên thời gian** | Quy ước [from,to) có thống nhất không? | Fact đúng valid_from/valid_to |
| **Thời điểm báo cáo** | Ngày UTC, ngày địa phương hay ngày ingest? | Fixture quanh 00:00; timezone tường minh |
| **Valid/system time** | Muốn dữ liệu đúng tại T hay dữ liệu hệ thống đã biết tại K? | Run/version, bitemporal/snapshot nếu cần |
| **Additive measure** | SUM có cộng trên những thành phần độc lập, không trùng lặp không? | Tổng nguồn so tổng nhóm |
| **Semi-additive** | Có cộng số dư snapshot qua thời gian không? | Test cuối kỳ/average đúng hợp đồng |
| **Distinct count** | Có cộng distinct count của các nhóm giao nhau không? | COUNT DISTINCT trực tiếp trên tập kỳ |
| **Ratio** | Tỷ lệ được tái tính từ tử/mẫu chưa? | SUM(numerator)/SUM(denominator) |
| **Đối soát** | Có kiểm cả tập khóa và các giá trị, không chỉ count/sum? | FULL OUTER JOIN, EXCEPT ALL khi cần |
| **Dữ liệu đến trễ** | Có biết cutoff, watermark và version input không? | Metadata run và source checkpoint |
| **Sửa hồi tố** | Có tách reproduce với restate không? | So run cũ/mới và giải thích delta |
| **Triển khai** | Những consumer, schema và feature flag đã sẵn sàng chưa? | Shadow read, rollback checklist |
| **Vận hành** | Test lỗi có chủ đích và quan sát lâu dài chưa? | CI assertion, data-quality alert, ownership |

### 15.1. Đề xuất các lớp kiểm thử theo giai đoạn

| Giai đoạn | Kiểm thử ưu tiên | Lý do |
| --- | --- | --- |
| **Khi định nghĩa schema** | Grain, khóa, miền dữ liệu, UNIQUE/FK, không-overlap | Chặn dữ liệu không hợp lệ từ gốc |
| **Trong pull request của SQL/ETL** | Fixture nhỏ, oracle, fanout, as-of, timezone, negative test | Phát hiện lỗi logic trước khi deploy |
| **Khi backfill dữ liệu thật** | Count + key set + value + aggregate theo partition | Tìm sai lệch lịch sử quy mô lớn |
| **Trước cutover** | Shadow query, source/version equivalence, tenant isolation, SLO | Tránh đổi đường đọc khi chưa đạt |
| **Sau công bố** | Freshness, match-count, overlap, late-event diff, reconciliation drift | Phát hiện lệch do nguồn và data evolution |

Nên gắn **owner và quy trình xử lý** cho mỗi loại kiểm tra. Một cảnh báo “JOIN fanout vượt ngưỡng” không có người phụ trách, không xác định group nào sai và không có đường rollback khó trở thành biện pháp bảo vệ thực sự.

### 15.2. Mẫu tiêu chí nghiệm thu cho fixture trong bài

~~~text
CONTRACT:
  fact grain = one order line
  customer business key = tenant_id + customer_code
  historical dimension = valid interval [from, to)
  reporting timezone = Asia/Ho_Chi_Minh

BASELINE:
  order lines = 6
  distinct orders = 5
  distinct customers = 3
  sales total = 1,100,000 VND
  payment events = 6
  paid total = 1,100,000 VND

RELATIONSHIPS:
  missing historical dimension matches = 0
  multiple historical dimension matches = 0
  overlapping customer validity ranges = 0
  payment-only orders = 0 (fixture-specific)

AGGREGATION:
  sales by tenant-local-day:
    T01/19 = 300,000
    T01/20 = 450,000
    T01/21 = 100,000
    T02/21 = 250,000
  sales by event-time department:
    North = 450,000
    South = 650,000

NEGATIVE TEST:
  naive SCD join -> fanout detectable
  naive order-payment join -> fanout detectable
  orphan customer -> missing match detectable
  overlap history -> multiple matches detectable
  UTC/VN day boundary -> different group detectable
~~~

Đây là **các giá trị kỳ vọng để người học tự chạy và kiểm tra**. Việc bài viết có câu SQL không có nghĩa đã thực thi, benchmark hoặc hoàn tất vòng QA chuyên môn. Một bước QA riêng vẫn cần đánh giá toàn diện tính chính xác và độ phù hợp của bài.

## 16. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “SQL chạy là số đã đúng.” | Còn grain, JOIN cardinality, thời gian và định nghĩa số đo. |
| “Có FOREIGN KEY nên JOIN không thể nhân hàng.” | FK không ngăn JOIN hai quan hệ 1–N thành N–M. |
| “Một customer_code chỉ là một khách nên JOIN một lần.” | SCD có nhiều phiên bản cùng business key; cần AS-OF. |
| “Đã có customer_sk trong fact thì không cần kiểm thử lịch sử.” | Khóa thay thế có thể được gán sai thời điểm dù FK hợp lệ. |
| “JOIN N–1 đúng nghĩa luôn giữ số hàng.” | Cần kiểm tra cả 0 match và >1 match; với OUTER JOIN còn các trường hợp null. |
| “Mọi JOIN tăng số hàng đều sai.” | JOIN 1–N có thể cố ý tạo nhiều hàng con; phải xét grain mục tiêu. |
| “Tổng payment bằng tổng sales sau JOIN thì đúng.” | Hai tổng có thể cùng bị nhân đôi. |
| “COUNT(*) là số đơn.” | COUNT(*) đếm hàng kết quả; cần xác định grain. |
| “COUNT DISTINCT luôn sửa được fanout.” | Nó có thể che lỗi và làm mất các lượt hợp lệ, không bảo vệ SUM. |
| “Số hàng bằng nhau nghĩa là không có mất/trùng.” | Có thể mất một hàng và nhân một hàng khác; cần so tập khóa. |
| “SUM toàn kỳ khớp nghĩa là mọi group khớp.” | Có thể hoán đổi giá trị giữa các tenant/ngày/department. |
| “Tỷ lệ từng nhóm cộng hoặc AVG được.” | Thường cần cộng tử số và mẫu số rồi chia theo định nghĩa. |
| “Số dư cuối ngày có thể SUM qua nhiều ngày.” | Số dư là semi-additive theo thời gian. |
| “Khoảng SCD có valid_to thì dùng BETWEEN cho tiện.” | BETWEEN đóng cả hai đầu có thể khớp hai phiên bản tại biên. |
| “Không có overlap thì mọi lúc đều có một dimension.” | Vẫn có gap; cần kiểm tra coverage theo nghiệp vụ. |
| “Ngày DATE lấy từ TIMESTAMPTZ luôn như nhau.” | Ép kiểu ngày phụ thuộc session timezone nếu không ghi rõ. |
| “Báo cáo cũ khác báo cáo mới chắc là một bên sai.” | Có thể khác input cutoff, correction hoặc phiên bản metric. |
| “Valid-time đủ để tái hiện mọi báo cáo đã công bố.” | Correction hồi tố cần knowledge-time/snapshot hoặc bitemporal. |
| “Sửa dữ liệu nguồn thì chỉ cập nhật bảng dimension là xong.” | Các aggregate/materialized view cần restate, đối soát và publish theo version. |
| “Chạy test trên nguồn sạch là đủ.” | Negative test mới chứng minh phép kiểm tra phát hiện lỗi dự kiến. |

## 17. Ghi nhớ

**Tính đúng của phép JOIN** bắt đầu từ **grain và cardinality**. Khi một dòng đơn bị nối với nhiều sự kiện thanh toán hoặc nhiều phiên bản dimension, **SUM và COUNT có thể tăng mà không có lỗi cú pháp**. Hãy kiểm tra số match **theo từng khóa fact**, sử dụng **EXISTS** khi chỉ cần biết sự tồn tại, **tổng hợp từng fact về cùng grain trước khi JOIN**, và đối soát **tập khóa, từng giá trị, các group và tổng nguồn**.

**Tính đúng của phép tổng hợp** phụ thuộc vào định nghĩa số đo. Giá trị dòng hàng có thể SUM trên các dòng độc lập; số khách duy nhất không được cộng qua các nhóm giao nhau; tỷ lệ phải tính từ tử số và mẫu số; số dư snapshot không được cộng qua nhiều thời điểm. Một tổng toàn hệ thống đúng không bảo đảm phân bố theo tenant hoặc bộ phận đúng.

**Tính đúng của lịch sử** đòi hỏi phân biệt **khóa nghiệp vụ** với **khóa phiên bản**, sử dụng khoảng hiệu lực **[valid_from, valid_to)** và **JOIN tại thời điểm giao dịch**, kiểm tra overlap/gap, biên ngày và timezone. Khi có correction hồi tố, cần tách **“điều gì đúng tại thời điểm T”** khỏi **“điều hệ thống biết về T tại thời điểm K”**, giữ version để có thể reproduce hoặc restate đúng mục đích.

Một quy trình kiểm chứng đáng tin cậy là **viết data contract → tạo fixture có phản ví dụ → kiểm tra khóa và match-count → đối soát metric theo grain → thử biên thời gian → kiểm chứng với dữ liệu thật theo cùng snapshot/version → nghiệm thu cutover và giám sát lâu dài**. Đây là cách biến mô hình dữ liệu từ một sơ đồ có vẻ hợp lý thành một thiết kế **có thể chứng minh, kiểm thử và tiến hóa có kiểm soát**.
