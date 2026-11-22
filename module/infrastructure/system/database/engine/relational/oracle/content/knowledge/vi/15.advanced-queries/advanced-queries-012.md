# Thiết kế truy vấn báo cáo có tổng phụ, xếp hạng và dữ liệu thời gian trong Oracle

Một báo cáo bán hàng thường phải trả lời nhiều câu hỏi cùng lúc: doanh thu theo khu vực, tổng phụ theo từng khu vực, tổng toàn công ty, ba sản phẩm bán chạy nhất mỗi tháng, mức tăng trưởng so với tháng trước và doanh thu lũy kế từ đầu năm. Nếu viết mỗi chỉ số thành một truy vấn riêng, ứng dụng phải ghép nhiều tập kết quả và có nguy cơ các con số không cùng phạm vi dữ liệu. Oracle SQL cung cấp các công cụ để xây dựng báo cáo nhiều cấp: GROUPING SETS/ROLLUP/CUBE tạo các mức tổng hợp, analytic functions tính xếp hạng và chỉ số theo cửa sổ, còn truy vấn thời gian xác định kỳ báo cáo và xử lý những kỳ không có giao dịch.

Điều quan trọng là thiết kế đúng **grain** (mức chi tiết) của từng bước. Ta phải biết một dòng dữ liệu nguồn đại diện cho giao dịch hay dòng hàng; một dòng tổng hợp đại diện cho tháng, khu vực hay cặp tháng/khu vực; và một dòng xếp hạng đại diện cho sản phẩm trong một tháng hay sản phẩm trong toàn bộ báo cáo. Khi grain rõ ràng, ta mới kết hợp tổng phụ, ranking và time series mà không đếm trùng hoặc xếp hạng nhầm các dòng tổng.

Bài học thuộc nhóm **Truy vấn nâng cao** của Database Engine Relational Oracle. Các ví dụ dùng cú pháp Oracle Database 19c, tập trung vào báo cáo bán hàng nhưng có thể áp dụng cho tài chính, tồn kho, vận hành và phân tích sự kiện.

Sau bài này, bạn có thể:

- Thiết kế báo cáo nhiều cấp bằng GROUPING SETS, ROLLUP và CUBE.
- Phân biệt dòng chi tiết, tổng phụ và tổng toàn bộ bằng GROUPING/GROUPING_ID.
- Dùng ROW_NUMBER, RANK, DENSE_RANK để xếp hạng và lấy top-N trong từng nhóm.
- Kết hợp tổng hợp theo tháng với ranking mà không đưa dòng subtotal vào thứ hạng.
- Tạo chuỗi tháng liên tục, bổ sung kỳ không có giao dịch và tính tổng lũy kế/trung bình trượt.
- So sánh kỳ hiện tại với kỳ trước bằng LAG/LEAD.
- Xử lý biên thời gian, kiểu DATE/TIMESTAMP và múi giờ theo lịch nghiệp vụ.
- Đọc execution plan, đánh giá index, cardinality và chi phí của báo cáo.

> **Phạm vi ví dụ:** Các bảng thực hành có hậu tố _LAB và chỉ nên được tạo trong schema/PDB lab do bạn quản lý. Các câu truy vấn giả định Oracle Database 19c. Nếu dùng phiên bản khác, hãy kiểm tra cú pháp và tính năng tương ứng. Không chạy DDL hoặc báo cáo quét dữ liệu lớn trên schema production khi chưa có kế hoạch vận hành.

## 1. Bắt đầu từ grain của báo cáo

Trước khi viết SQL, hãy trả lời: **mỗi dòng đầu ra đại diện cho điều gì?**

| Grain | Một dòng đại diện cho | Khóa nhận diện điển hình |
| --- | --- | --- |
| Dữ liệu giao dịch | Một đơn hàng hoặc một dòng hàng trong đơn | SALE_ID hoặc ORDER_ID, LINE_ID |
| Tổng hợp tháng/khu vực | Doanh thu một khu vực trong một tháng | MONTH_START, REGION |
| Tổng hợp tháng/khu vực/sản phẩm | Doanh thu một sản phẩm ở một khu vực trong một tháng | MONTH_START, REGION, PRODUCT_ID |
| Xếp hạng sản phẩm | Vị trí của sản phẩm trong một nhóm báo cáo | MONTH_START, REGION, PRODUCT_ID cộng rank |
| Tổng phụ khu vực | Tổng doanh thu của tất cả sản phẩm trong khu vực/kỳ | MONTH_START, REGION |
| Tổng toàn kỳ | Tổng doanh thu của toàn bộ khu vực/sản phẩm trong kỳ | MONTH_START hoặc một dòng grand total |

Các phép tổng hợp và analytic function hoạt động trên grain khác nhau:

~~~text
GIAO DICH / DONG HANG
        |
        | GROUP BY thang, khu vuc, san pham
        v
TONG HOP DETAIL: 1 dong / thang / khu vuc / san pham
        |
        +------------------------------+
        |                              |
        | analytic ranking             | GROUPING SETS / ROLLUP
        v                              v
XEP HANG SAN PHAM                 TONG PHU / GRAND TOTAL
        |                              |
        +---------------+--------------+
                        v
                 BAO CAO HIEN THI
~~~

Không nên áp dụng ranking trực tiếp lên bảng giao dịch nếu yêu cầu là xếp hạng sản phẩm theo doanh thu tháng: trước tiên phải cộng doanh thu của từng sản phẩm trong tháng, sau đó mới xếp hạng các tổng đó.

## 2. Chuẩn bị dữ liệu thực hành

### 2.1. Tạo bảng lab

Bảng sau lưu một dòng cho mỗi giao dịch sản phẩm:

~~~sql
CREATE TABLE report_sales_lab (
    sale_id      NUMBER PRIMARY KEY,
    sold_at      DATE NOT NULL,
    region       VARCHAR2(20 CHAR) NOT NULL,
    product_id   NUMBER NOT NULL,
    product_name VARCHAR2(40 CHAR) NOT NULL,
    channel      VARCHAR2(15 CHAR) NOT NULL,
    quantity     NUMBER(8,2) NOT NULL,
    unit_price   NUMBER(10,2) NOT NULL,
    status       VARCHAR2(12 CHAR) NOT NULL
);
~~~

Trong ví dụ, doanh thu dòng được tính bằng quantity nhân unit_price. Đây là mô hình đơn giản để học SQL; hệ thống thực tế có thể cần chiết khấu, thuế, tiền tệ, hoàn hàng và quy tắc ghi nhận doanh thu riêng.

### 2.2. Thêm dữ liệu qua nhiều tháng và khu vực

~~~sql
INSERT ALL
  INTO report_sales_lab VALUES
    (1, DATE '2026-01-03', 'North', 101, 'Laptop', 'Online', 2, 1000, 'PAID')
  INTO report_sales_lab VALUES
    (2, DATE '2026-01-05', 'North', 102, 'Mouse', 'Store', 10, 25, 'PAID')
  INTO report_sales_lab VALUES
    (3, DATE '2026-01-12', 'North', 103, 'Keyboard', 'Online', 5, 50, 'PAID')
  INTO report_sales_lab VALUES
    (4, DATE '2026-01-20', 'South', 101, 'Laptop', 'Store', 1, 1000, 'PAID')
  INTO report_sales_lab VALUES
    (5, DATE '2026-01-24', 'South', 102, 'Mouse', 'Online', 8, 25, 'PAID')
  INTO report_sales_lab VALUES
    (6, DATE '2026-02-02', 'North', 101, 'Laptop', 'Online', 1, 1000, 'PAID')
  INTO report_sales_lab VALUES
    (7, DATE '2026-02-08', 'North', 102, 'Mouse', 'Store', 20, 25, 'PAID')
  INTO report_sales_lab VALUES
    (8, DATE '2026-02-18', 'South', 103, 'Keyboard', 'Online', 10, 50, 'PAID')
  INTO report_sales_lab VALUES
    (9, DATE '2026-03-04', 'North', 103, 'Keyboard', 'Store', 8, 50, 'PAID')
  INTO report_sales_lab VALUES
    (10, DATE '2026-03-09', 'South', 101, 'Laptop', 'Online', 2, 1000, 'PAID')
  INTO report_sales_lab VALUES
    (11, DATE '2026-03-16', 'South', 102, 'Mouse', 'Store', 12, 25, 'PAID')
  INTO report_sales_lab VALUES
    (12, DATE '2026-03-25', 'North', 101, 'Laptop', 'Store', 1, 1000, 'PENDING')
  INTO report_sales_lab VALUES
    (13, DATE '2026-04-02', 'North', 102, 'Mouse', 'Online', 15, 25, 'PAID')
  INTO report_sales_lab VALUES
    (14, DATE '2026-04-11', 'South', 103, 'Keyboard', 'Store', 12, 50, 'PAID')
  INTO report_sales_lab VALUES
    (15, DATE '2026-04-19', 'South', 101, 'Laptop', 'Online', 1, 1000, 'PAID')
  INTO report_sales_lab VALUES
    (16, DATE '2026-06-06', 'North', 101, 'Laptop', 'Online', 1, 1000, 'PAID')
SELECT 1 FROM dual;

COMMIT;
~~~

Tháng 5 không có giao dịch. Dữ liệu này giúp ta thấy khác biệt giữa “tháng không có dòng trong bảng” và “tháng có doanh thu bằng 0”. Một giao dịch PENDING cũng được đưa vào để minh họa việc lọc trạng thái trước khi tổng hợp.

Kiểm tra nguồn:

~~~sql
SELECT sale_id, sold_at, region, product_name,
       quantity, unit_price, status
FROM report_sales_lab
ORDER BY sold_at, sale_id;
~~~

### 2.3. Xác định phạm vi thời gian và trạng thái

Trong các ví dụ báo cáo PAID, dùng khoảng nửa mở:

~~~sql
WHERE status = 'PAID'
  AND sold_at >= DATE '2026-01-01'
  AND sold_at <  DATE '2026-07-01'
~~~

Khoảng lớn hơn hoặc bằng đầu kỳ và nhỏ hơn đầu kỳ kế tiếp bao gồm mọi thời điểm trong tháng cuối, kể cả phần giây nếu cột là TIMESTAMP được thay vào ví dụ tương ứng. Tránh dùng BETWEEN với thời điểm cuối là nửa đêm đầu ngày cuối kỳ, vì có thể bỏ sót các giao dịch xảy ra sau thời điểm đó trong ngày.

## 3. Báo cáo tổng phụ bằng ROLLUP

### 3.1. GROUP BY ROLLUP tạo các cấp tổng hợp

Giả sử cần doanh thu theo từng khu vực và sản phẩm, kèm tổng phụ của mỗi khu vực và tổng toàn công ty:

~~~sql
SELECT
    region,
    product_name,
    SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(region, product_name)
ORDER BY region, product_name;
~~~

Với ROLLUP(region, product_name), Oracle tạo các grouping sets tương đương:

~~~sql
GROUPING SETS (
    (region, product_name),
    (region),
    ()
)
~~~

Kết quả gồm:

1. Chi tiết doanh thu mỗi cặp khu vực/sản phẩm.
2. Tổng phụ doanh thu của mỗi khu vực (product_name được tổng hợp).
3. Tổng toàn bộ (cả region và product_name được tổng hợp).

ROLLUP hữu ích khi các cấp tổng hợp có thứ tự phân cấp: chi tiết → tổng theo cha → grand total.

### 3.2. Thứ tự cột trong ROLLUP rất quan trọng

~~~sql
GROUP BY ROLLUP(region, product_name)
~~~

tạo detail (region, product_name), subtotal (region) và grand total ().

Trong khi:

~~~sql
GROUP BY ROLLUP(product_name, region)
~~~

tạo detail (product_name, region), subtotal (product_name) và grand total. Tổng phụ giờ là theo sản phẩm, không phải theo khu vực.

ROLLUP không tạo mọi tổ hợp con. Thứ tự đối số quyết định chuỗi mức tổng hợp được tạo ra.

### 3.3. Nhận biết dòng tổng phụ bằng GROUPING

Trong dữ liệu nguồn, PRODUCT_NAME có thể NULL thật. Khi ROLLUP tạo subtotal, Oracle cũng hiển thị NULL ở cột đã được tổng hợp. Vì vậy không thể chỉ nhìn NULL rồi kết luận đó là subtotal.

Dùng GROUPING(expression):

~~~sql
SELECT
    region,
    product_name,
    GROUPING(region) AS g_region,
    GROUPING(product_name) AS g_product,
    SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(region, product_name)
ORDER BY GROUPING(region), region,
         GROUPING(product_name), product_name;
~~~

GROUPING(expr) trả:

- 0: biểu thức đang giữ giá trị từ nhóm chi tiết (kể cả khi giá trị nguồn thực sự NULL).
- 1: biểu thức đã bị loại khỏi grouping set và NULL được sinh ra để biểu diễn mức tổng hợp.

Vì vậy ta có thể phân biệt NULL thật với NULL do subtotal.

### 3.4. Đặt nhãn cho subtotal và grand total

~~~sql
SELECT
    CASE
        WHEN GROUPING(region) = 1 THEN 'ALL REGIONS'
        ELSE region
    END AS region_label,
    CASE
        WHEN GROUPING(product_name) = 1 THEN 'SUBTOTAL / ALL PRODUCTS'
        ELSE NVL(product_name, '(unknown product)')
    END AS product_label,
    SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(region, product_name)
ORDER BY GROUPING(region), region,
         GROUPING(product_name), product_name;
~~~

Ở dòng grand total, GROUPING(region)=1 nên nhãn khu vực là ALL REGIONS. Ở dòng subtotal khu vực, GROUPING(product_name)=1; ở dòng chi tiết có sản phẩm NULL thật, GROUPING(product_name)=0 và nhãn sẽ là unknown product.

Không dùng NVL(product_name, 'TOTAL') một mình để nhận diện subtotal, vì nó có thể gộp NULL thật với NULL do tổng hợp.

## 4. GROUPING_ID: mã hóa mức tổng hợp

### 4.1. GROUPING_ID cho nhiều cột

Với ROLLUP(region, product_name), ta có thể viết:

~~~sql
SELECT
    region,
    product_name,
    GROUPING_ID(region, product_name) AS grouping_level,
    SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(region, product_name)
ORDER BY grouping_level, region, product_name;
~~~

Với thứ tự đối số GROUPING_ID(region, product_name), bit của biểu thức cuối cùng là bit thấp nhất:

| Grouping set | GROUPING(region) | GROUPING(product_name) | GROUPING_ID |
| --- | ---: | ---: | ---: |
| (region, product_name) | 0 | 0 | 0 |
| (region) | 0 | 1 | 1 |
| () | 1 | 1 | 3 |

Giá trị GROUPING_ID là mã hữu ích để phân biệt detail/subtotal/grand total và sắp xếp các cấp báo cáo. Khi thay đổi thứ tự đối số, ý nghĩa bit cũng thay đổi; hãy giữ cùng thứ tự trong biểu thức và tài liệu báo cáo.

### 4.2. Dùng GROUPING_ID để lọc một cấp

Ví dụ chỉ lấy tổng phụ khu vực:

~~~sql
SELECT region, SUM(quantity * unit_price) AS region_revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(region, product_name)
HAVING GROUPING_ID(region, product_name) = 1
ORDER BY region;
~~~

Trong thực tế, nếu chỉ cần tổng theo khu vực, câu GROUP BY region đơn giản hơn. GROUPING_ID hữu ích khi cùng một truy vấn cần nhiều cấp và bạn muốn lọc/định danh một cấp cụ thể.

## 5. GROUPING SETS: chọn chính xác những cấp cần báo cáo

ROLLUP tạo chuỗi phân cấp. Nếu báo cáo cần những tổ hợp riêng lẻ, dùng GROUPING SETS:

~~~sql
SELECT
    region,
    channel,
    product_name,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(region, channel, product_name) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY GROUPING SETS (
    (region, channel, product_name),
    (region, channel),
    (region),
    ()
)
ORDER BY grouping_level, region, channel, product_name;
~~~

Truy vấn tạo chi tiết khu vực/kênh/sản phẩm, tổng phụ khu vực/kênh, tổng phụ khu vực và grand total. Khác với ROLLUP, GROUPING SETS cho phép chọn chính xác các cấp, không bắt buộc tạo mọi cấp theo một chuỗi tiền tố.

### 5.1. Một truy vấn cho nhiều báo cáo tổng hợp

Ví dụ cần doanh thu theo khu vực, theo kênh, theo khu vực/kênh và tổng toàn bộ:

~~~sql
SELECT
    region,
    channel,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(region, channel) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY GROUPING SETS (
    (region, channel),
    (region),
    (channel),
    ()
);
~~~

Không có ROLLUP đơn giản nào tạo đúng bốn cấp này mà không sinh thêm cấp không cần thiết; GROUPING SETS mô tả rõ tập yêu cầu.

### 5.2. GROUP BY thường và GROUPING SETS

Nếu viết bốn truy vấn riêng bằng UNION ALL, có thể lặp lại cùng phép lọc và aggregate. GROUPING SETS thường dễ bảo trì hơn cho các cấp tổng hợp này. Tuy nhiên, không nên khẳng định một câu GROUPING SETS luôn nhanh hơn nhiều query UNION ALL; optimizer và dữ liệu quyết định kế hoạch, còn UNION ALL có thể cần thiết khi từng nhánh có logic khác nhau.

## 6. CUBE: tổng hợp mọi tổ hợp chiều

### 6.1. CUBE tạo lưới tổng hợp

~~~sql
SELECT
    region,
    channel,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(region, channel) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY CUBE(region, channel);
~~~

Với hai chiều, CUBE tương đương GROUPING SETS của (region, channel), (region), (channel) và (). Nó tạo doanh thu theo từng cặp khu vực/kênh, theo khu vực, theo kênh và tổng toàn bộ.

### 6.2. Số grouping sets tăng theo cấp số mũ

Với n biểu thức trong CUBE, số grouping sets lý thuyết là 2^n:

| Số chiều | Số grouping sets |
| ---: | ---: |
| 2 | 4 |
| 3 | 8 |
| 4 | 16 |
| 5 | 32 |
| 8 | 256 |

CUBE hữu ích cho phân tích nhiều chiều nhưng có thể tạo lượng kết quả lớn. Chỉ dùng khi báo cáo thực sự cần mọi tổ hợp. Nếu chỉ cần vài cấp, GROUPING SETS thường mô tả chính xác hơn và tránh các cấp thừa.

### 6.3. ROLLUP, CUBE và GROUPING SETS

| Cú pháp | Mục tiêu | Hình thức grouping sets |
| --- | --- | --- |
| ROLLUP(a,b,c) | Detail, subtotal theo tiền tố, grand total | (a,b,c), (a,b), (a), () |
| CUBE(a,b) | Mọi tổ hợp chiều | (a,b), (a), (b), () |
| GROUPING SETS((a,b),(a),()) | Các cấp do người viết chọn | Đúng các tập được liệt kê |

Đối với báo cáo phân cấp khu vực → kênh → sản phẩm, ROLLUP thường tự nhiên. Đối với phân tích mọi tổ hợp khu vực/kênh, CUBE phù hợp. Đối với một bộ chỉ số báo cáo được xác định trước, GROUPING SETS thường rõ ràng nhất.

## 7. Xếp hạng bằng analytic functions

### 7.1. Ba hàm xếp hạng thường dùng

Giả sử doanh thu sản phẩm trong một tháng là:

| Sản phẩm | Revenue |
| --- | ---: |
| Laptop | 5.000 |
| Mouse | 2.000 |
| Keyboard | 2.000 |
| Monitor | 1.000 |

| Hàm | Kết quả thứ hạng | Khi nào dùng |
| --- | --- | --- |
| ROW_NUMBER() | 1, 2, 3, 4 | Cần số thứ tự duy nhất và đúng N dòng |
| RANK() | 1, 2, 2, 4 | Đồng hạng chia sẻ rank, vị trí sau có khoảng nhảy |
| DENSE_RANK() | 1, 2, 2, 3 | Đồng hạng chia sẻ rank, vị trí sau không nhảy |

~~~sql
SELECT
    product_name,
    revenue,
    ROW_NUMBER() OVER (ORDER BY revenue DESC) AS row_num,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    DENSE_RANK() OVER (ORDER BY revenue DESC) AS dense_rank
FROM (
    SELECT product_name,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY product_name
);
~~~

### 7.2. ORDER BY trong analytic function quyết định rank

ORDER BY revenue DESC xếp doanh thu cao trước. Nếu thêm một cột duy nhất vào analytic order của ROW_NUMBER, thứ tự dòng trở nên xác định hơn khi doanh thu bằng nhau. Nhưng với RANK/DENSE_RANK, thêm product_name có nghĩa các sản phẩm có doanh thu bằng nhau nhưng tên khác nhau không còn đồng hạng theo toàn bộ tuple sắp xếp.

Nếu mục tiêu là giữ đồng hạng theo doanh thu, chỉ dùng ORDER BY revenue DESC bên trong RANK/DENSE_RANK; dùng ORDER BY ngoài để sắp xếp hiển thị ổn định:

~~~sql
SELECT product_name, revenue, revenue_rank
FROM (
    SELECT
        product_name,
        revenue,
        RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
    FROM (
        SELECT product_name,
               SUM(quantity * unit_price) AS revenue
        FROM report_sales_lab
        WHERE status = 'PAID'
        GROUP BY product_name
    )
)
ORDER BY revenue DESC, product_name;
~~~

### 7.3. PARTITION BY: xếp hạng riêng trong từng nhóm

Yêu cầu: xếp hạng sản phẩm trong từng khu vực:

~~~sql
WITH product_revenue AS (
    SELECT
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY region, product_id, product_name
)
SELECT
    region,
    product_name,
    revenue,
    RANK() OVER (
        PARTITION BY region
        ORDER BY revenue DESC
    ) AS region_rank
FROM product_revenue
ORDER BY region, region_rank, product_name;
~~~

PARTITION BY region chia tập tổng hợp thành các partition độc lập. Rank bắt đầu lại từ 1 trong mỗi khu vực. Không có PARTITION BY, toàn bộ sản phẩm ở mọi khu vực sẽ được xếp chung một bảng xếp hạng.

### 7.4. Top-N mỗi nhóm

Top 2 sản phẩm theo doanh thu trong mỗi khu vực, đúng tối đa hai dòng:

~~~sql
WITH product_revenue AS (
    SELECT region, product_id, product_name,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY region, product_id, product_name
),
ranked AS (
    SELECT p.*,
           ROW_NUMBER() OVER (
               PARTITION BY region
               ORDER BY revenue DESC, product_id
           ) AS rn
    FROM product_revenue p
)
SELECT region, product_id, product_name, revenue
FROM ranked
WHERE rn <= 2
ORDER BY region, rn;
~~~

ROW_NUMBER bảo đảm tối đa hai dòng mỗi khu vực; product_id là tie-breaker giả định duy nhất trong nhóm. Nếu muốn lấy tất cả sản phẩm đồng hạng ở vị trí thứ hai, dùng RANK:

~~~sql
RANK() OVER (
    PARTITION BY region
    ORDER BY revenue DESC
) AS revenue_rank
~~~

và lọc revenue_rank <= 2. Kết quả có thể nhiều hơn hai sản phẩm mỗi khu vực khi có ties.

### 7.5. Top-N theo tháng và khu vực

~~~sql
WITH monthly_product AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at <  DATE '2026-07-01'
    GROUP BY
        TRUNC(sold_at, 'MM'),
        region,
        product_id,
        product_name
),
ranked AS (
    SELECT
        m.*,
        DENSE_RANK() OVER (
            PARTITION BY month_start, region
            ORDER BY revenue DESC
        ) AS revenue_rank
    FROM monthly_product m
)
SELECT month_start, region, product_name, revenue, revenue_rank
FROM ranked
WHERE revenue_rank <= 3
ORDER BY month_start, region, revenue_rank, product_name;
~~~

Mỗi partition là một cặp tháng/khu vực. Ranking chỉ diễn ra sau khi doanh thu đã được tổng hợp ở grain tháng/khu vực/sản phẩm.

## 8. Kết hợp tổng phụ và ranking đúng cấp

Một báo cáo có thể cần top sản phẩm mỗi khu vực, tổng phụ doanh thu khu vực và tổng toàn bộ. Không nên đưa trực tiếp các dòng ROLLUP vào ranking rồi để subtotal cạnh tranh với sản phẩm. Hãy tạo detail và ranking riêng, tạo subtotal riêng, rồi kết hợp:

~~~sql
WITH detail AS (
    SELECT
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY region, product_id, product_name
),
ranked_detail AS (
    SELECT
        d.*,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY revenue DESC, product_id
        ) AS rn
    FROM detail d
),
subtotals AS (
    SELECT
        region,
        CAST(NULL AS NUMBER) AS product_id,
        CAST(NULL AS VARCHAR2(40)) AS product_name,
        SUM(quantity * unit_price) AS revenue,
        CAST(NULL AS NUMBER) AS rn,
        GROUPING_ID(region) AS grouping_level
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY ROLLUP(region)
)
SELECT
    region,
    product_name,
    revenue,
    rn AS product_rank,
    0 AS grouping_level,
    'TOP PRODUCT' AS row_type
FROM ranked_detail
WHERE rn <= 3
UNION ALL
SELECT
    region,
    product_name,
    revenue,
    rn,
    grouping_level,
    CASE WHEN grouping_level = 1
         THEN 'GRAND TOTAL'
         ELSE 'REGION SUBTOTAL'
    END
FROM subtotals
ORDER BY grouping_level, region, product_rank;
~~~

Ví dụ trên minh họa tách hai cấp logic; khi triển khai báo cáo thực tế, cần chuẩn hóa datatype của các cột UNION ALL, thêm cột tháng nếu báo cáo theo tháng, và dùng nhãn/ordering phù hợp. UNION ALL giữ tất cả các dòng, kể cả subtotal có giá trị trùng với detail; đây thường là điều mong muốn trong báo cáo phân cấp. Nếu dùng UNION, Oracle phải loại trùng và có thể làm mất hoặc thay đổi dòng báo cáo.

Một cách khác là dùng GROUPING SETS trong cùng query, sau đó áp analytic chỉ cho các dòng detail trong một query block riêng. Nguyên tắc vẫn là **ranking phải chạy ở grain sản phẩm**, subtotal phải được nhận diện riêng.

## 9. Báo cáo theo tháng: nhóm thời gian đúng cách

### 9.1. Nhóm theo tháng bằng TRUNC

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    SUM(quantity * unit_price) AS revenue,
    COUNT(*) AS sale_count
FROM report_sales_lab
WHERE status = 'PAID'
  AND sold_at >= DATE '2026-01-01'
  AND sold_at <  DATE '2026-07-01'
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY month_start;
~~~

TRUNC(date_value, 'MM') đưa ngày về ngày đầu tháng. Đây là khóa DATE thuận tiện để sắp xếp, nối calendar và tính khoảng cách giữa các tháng.

Không nên chỉ nhóm theo TO_CHAR(sold_at, 'MON'): tháng 1 của nhiều năm có thể bị gộp, và tên tháng có thể phụ thuộc NLS language. Nếu cần nhãn, hãy định dạng khóa DATE sau khi đã nhóm.

### 9.2. Lọc thời gian bằng range predicate

Nên:

~~~sql
WHERE sold_at >= DATE '2026-01-01'
  AND sold_at <  DATE '2026-07-01'
~~~

Thận trọng với:

~~~sql
WHERE TO_CHAR(sold_at, 'YYYY-MM') = '2026-01'
~~~

Việc bọc cột bằng hàm trong điều kiện có thể làm index thông thường trên SOLD_AT khó được sử dụng trực tiếp, trừ khi có function-based index phù hợp và optimizer chọn nó. Range predicate cũng diễn đạt rõ biên thời gian và không phụ thuộc định dạng chuỗi.

### 9.3. Nhóm theo tháng và khu vực

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    region,
    SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY TRUNC(sold_at, 'MM'), region
ORDER BY month_start, region;
~~~

Khóa nhóm là cặp tháng/khu vực. Một dòng kết quả đại diện doanh thu của một khu vực trong một tháng.

## 10. Chuỗi thời gian liên tục và tháng không có giao dịch

### 10.1. GROUP BY chỉ trả những kỳ có dữ liệu

Với dữ liệu lab, tháng 5 không có giao dịch nên truy vấn GROUP BY tháng ở phần trước không trả dòng tháng 5. Điều này đúng với semantics GROUP BY: không có dòng nguồn thì không có nhóm.

Nhưng báo cáo xu hướng thường muốn thấy đủ tháng 1 đến tháng 6, với tháng 5 có doanh thu 0. Ta cần tạo một **calendar series** rồi LEFT JOIN số liệu tổng hợp vào đó.

### 10.2. Tạo chuỗi tháng bằng CONNECT BY

~~~sql
WITH months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 6
),
monthly_sales AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        SUM(quantity * unit_price) AS revenue,
        COUNT(*) AS sale_count
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at <  DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
)
SELECT
    m.month_start,
    NVL(s.revenue, 0) AS revenue,
    NVL(s.sale_count, 0) AS sale_count
FROM months m
LEFT JOIN monthly_sales s
    ON s.month_start = m.month_start
ORDER BY m.month_start;
~~~

Kết quả có đủ sáu tháng; tháng 5 nhận doanh thu 0 và số giao dịch 0. Chuỗi tháng là phía được bảo toàn, số liệu tổng hợp là phía được ghép.

### 10.3. Sinh số tháng động

Nếu tham số đầu vào là tháng bắt đầu và tháng kết thúc (đầu tháng, bao gồm start và không bao gồm end), có thể tính số kỳ:

~~~sql
WITH params AS (
    SELECT DATE '2026-01-01' AS start_month,
           DATE '2026-07-01' AS end_month
    FROM dual
),
months AS (
    SELECT ADD_MONTHS(p.start_month, LEVEL - 1) AS month_start
    FROM params p
    CONNECT BY LEVEL <= MONTHS_BETWEEN(p.end_month, p.start_month)
)
SELECT month_start
FROM months
ORDER BY month_start;
~~~

Mẫu này giả định start_month và end_month đều là ngày đầu tháng, end_month lớn hơn hoặc bằng start_month và số tháng là số nguyên. Ứng dụng nên kiểm tra tham số trước khi gửi SQL.

### 10.4. Calendar dimension trong hệ thống thực tế

Với báo cáo nhiều năm, ngày làm việc, kỳ tài chính, ngày lễ hoặc tuần đặc thù, nên cân nhắc bảng dimension thời gian:

| month_start | month_end_exclusive | fiscal_year | fiscal_period | is_working_day |
| --- | --- | --- | --- | --- |
| 2026-01-01 | 2026-02-01 | 2026 | 1 | ... |
| 2026-02-01 | 2026-03-01 | 2026 | 2 | ... |

Calendar dimension có thể chứa cả ngày, tuần, tháng, quý, năm tài chính và ngày nghỉ. Nó giúp nhiều báo cáo dùng cùng một định nghĩa kỳ thay vì tự sinh chuỗi ngày bằng CONNECT BY ở từng nơi.

## 11. Running total: tổng lũy kế theo thời gian

### 11.1. Tổng lũy kế từ đầu chuỗi

Sau khi đã có một dòng mỗi tháng:

~~~sql
WITH monthly_sales AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at <  DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
)
SELECT
    month_start,
    revenue,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM monthly_sales
ORDER BY month_start;
~~~

SUM(...) OVER(...) là analytic aggregate: nó giữ từng dòng tháng và thêm một cột tổng lũy kế. Khác với GROUP BY, analytic function không gộp các dòng tháng thành một dòng duy nhất.

### 11.2. Chạy lũy kế theo từng khu vực

~~~sql
WITH monthly_region AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY TRUNC(sold_at, 'MM'), region
)
SELECT
    month_start,
    region,
    revenue,
    SUM(revenue) OVER (
        PARTITION BY region
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS region_running_revenue
FROM monthly_region
ORDER BY region, month_start;
~~~

PARTITION BY region khởi động lại tổng lũy kế cho từng khu vực. Nếu không có PARTITION BY, tất cả khu vực sẽ cộng chung theo thời gian.

### 11.3. Vì sao cần điền tháng thiếu trước khi tính lũy kế?

Nếu một tháng không có giao dịch, GROUP BY không sinh dòng tháng đó. Tổng lũy kế vẫn có thể đúng ở các tháng có giao dịch, nhưng biểu đồ sẽ thiếu điểm tháng 5 và không thể hiển thị chuỗi tháng liên tục.

Để báo cáo có đủ kỳ, tạo calendar series và LEFT JOIN trước, dùng NVL(revenue,0), rồi tính analytic running total trên chuỗi đã hoàn chỉnh. Điều này cũng làm ROWS BETWEEN 2 PRECEDING AND CURRENT ROW thực sự đại diện cho ba tháng liên tiếp.

## 12. Rolling window: tổng và trung bình trượt

### 12.1. Trung bình trượt ba tháng

~~~sql
WITH months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 6
),
monthly_sales AS (
    SELECT TRUNC(sold_at, 'MM') AS month_start,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
),
series AS (
    SELECT m.month_start, NVL(s.revenue, 0) AS revenue
    FROM months m
    LEFT JOIN monthly_sales s
        ON s.month_start = m.month_start
)
SELECT
    month_start,
    revenue,
    AVG(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_avg_3_months,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_sum_3_months
FROM series
ORDER BY month_start;
~~~

ROWS BETWEEN 2 PRECEDING AND CURRENT ROW lấy tối đa ba dòng: dòng hiện tại và hai dòng trước. Vì series đã có đủ một dòng cho mỗi tháng, cửa sổ ba dòng tương ứng ba tháng liên tiếp.

### 12.2. ROWS khác RANGE

Trong analytic window:

- ROWS xác định cửa sổ theo số dòng trong thứ tự analytic.
- RANGE xác định cửa sổ theo giá trị sort và khoảng logic; cách xử lý peer rows (các dòng cùng giá trị sort) có thể khác.

Nếu dữ liệu chỉ có một dòng mỗi tháng, ROWS ba dòng là ba tháng khi không thiếu tháng. Nếu có nhiều giao dịch mỗi ngày hoặc nhiều dòng cùng ngày, ROWS BETWEEN 2 PRECEDING không có nghĩa là ba ngày hay ba tháng. Phải tổng hợp về grain thời gian mong muốn hoặc dùng RANGE với biểu thức/kiểu dữ liệu phù hợp.

### 12.3. Cửa sổ có ít hơn ba kỳ ở đầu chuỗi

Tháng đầu chỉ có dòng hiện tại; tháng thứ hai có tối đa hai dòng; từ tháng thứ ba mới có đủ ba dòng. AVG tính trên số giá trị có trong frame hiện tại, không tự giả định các kỳ trước chuỗi có doanh thu 0. Nếu cần cửa sổ đầy đủ ba tháng, có thể đánh dấu COUNT(*) OVER(...) và chỉ công bố rolling average khi đủ ba kỳ.

## 13. So sánh tháng trước bằng LAG và LEAD

### 13.1. LAG lấy giá trị của kỳ trước

~~~sql
WITH monthly_sales AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY TRUNC(sold_at, 'MM')
)
SELECT
    month_start,
    revenue,
    LAG(revenue) OVER (ORDER BY month_start) AS previous_month_revenue
FROM monthly_sales
ORDER BY month_start;
~~~

LAG đọc giá trị ở dòng trước trong thứ tự analytic. Nếu chuỗi GROUP BY thiếu tháng 5, dòng tháng 6 sẽ lấy giá trị của kỳ có giao dịch trước đó (tháng 4), không phải tự hiểu là tháng 5 có doanh thu 0.

### 13.2. Tính mức tăng tuyệt đối và phần trăm

~~~sql
WITH monthly_sales AS (
    SELECT TRUNC(sold_at, 'MM') AS month_start,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY TRUNC(sold_at, 'MM')
),
comparison AS (
    SELECT
        month_start,
        revenue,
        LAG(revenue) OVER (ORDER BY month_start) AS previous_revenue
    FROM monthly_sales
)
SELECT
    month_start,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS change_amount,
    ROUND(
        100 * (revenue - previous_revenue)
        / NULLIF(previous_revenue, 0),
        2
    ) AS change_percent
FROM comparison
ORDER BY month_start;
~~~

NULLIF(previous_revenue,0) tránh chia cho 0. Nếu kỳ trước không có doanh thu hoặc không có dòng kỳ trước, phần trăm tăng trưởng không xác định và kết quả là NULL; không tự thay bằng 0% nếu nghiệp vụ không định nghĩa như vậy.

### 13.3. Điền kỳ thiếu trước khi dùng LAG

Nếu muốn tháng 6 so với tháng 5 có doanh thu 0, phải dùng calendar series:

~~~sql
WITH months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 6
),
monthly_sales AS (
    SELECT TRUNC(sold_at, 'MM') AS month_start,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
),
series AS (
    SELECT m.month_start, NVL(s.revenue, 0) AS revenue
    FROM months m
    LEFT JOIN monthly_sales s
        ON s.month_start = m.month_start
),
comparison AS (
    SELECT
        month_start,
        revenue,
        LAG(revenue) OVER (ORDER BY month_start) AS previous_revenue
    FROM series
)
SELECT
    month_start,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS change_amount
FROM comparison
ORDER BY month_start;
~~~

Tháng 5 xuất hiện với revenue 0; tháng 6 so sánh với 0. Nếu muốn phần trăm tăng trưởng từ 0 lên số dương, cần một quy ước nghiệp vụ riêng vì phép chia cho 0 không xác định.

### 13.4. LEAD xem kỳ tiếp theo

~~~sql
SELECT
    month_start,
    revenue,
    LEAD(revenue) OVER (ORDER BY month_start) AS next_month_revenue
FROM monthly_series
ORDER BY month_start;
~~~

LEAD thường hữu ích khi cần đối chiếu kỳ hiện tại với kỳ kế tiếp, xác định kỳ có doanh thu giảm, hoặc tạo cặp quan sát liên tiếp. LAG và LEAD không tự tạo các kỳ bị thiếu; chúng chỉ dịch chuyển trên những dòng đang có trong partition.

## 14. Báo cáo kết hợp tháng, khu vực và tổng phụ

### 14.1. Tổng phụ theo từng tháng

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    region,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(TRUNC(sold_at, 'MM'), region) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY ROLLUP(TRUNC(sold_at, 'MM'), region)
ORDER BY month_start, GROUPING(region), region;
~~~

Với ROLLUP(month_start, region), kết quả có detail tháng/khu vực, subtotal tháng (region đã tổng hợp) và grand total toàn bộ. Nếu muốn tổng phụ khu vực qua tất cả tháng thay vì subtotal theo tháng, cần thêm grouping set (region) riêng; ROLLUP theo thứ tự hiện tại không tạo nó.

### 14.2. Các cấp báo cáo chính xác bằng GROUPING SETS

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    region,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(TRUNC(sold_at, 'MM'), region) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY GROUPING SETS (
    (TRUNC(sold_at, 'MM'), region),
    (TRUNC(sold_at, 'MM')),
    (region),
    ()
)
ORDER BY grouping_level, month_start, region;
~~~

Báo cáo có bốn cấp: tháng/khu vực, tổng theo tháng, tổng theo khu vực và grand total. Cần dùng GROUPING_ID để phân biệt NULL do dữ liệu với NULL do cấp tổng hợp.

### 14.3. Không xếp hạng subtotal như một sản phẩm

Khi cần top sản phẩm trong mỗi tháng và tổng phụ tháng, hãy tạo hai tập riêng:

1. CTE detail theo tháng/sản phẩm rồi analytic ranking.
2. CTE subtotal theo tháng hoặc GROUPING SETS riêng.

Sau đó UNION ALL hai nhánh với cột row_type hoặc grouping_level. Nếu ranking trên kết quả đã có subtotal, tổng tháng có thể đứng đầu và đẩy sản phẩm ra khỏi top-N, dù báo cáo muốn xếp hạng sản phẩm.

## 15. Xếp hạng và tổng lũy kế trên chuỗi tháng

Một báo cáo có thể cần doanh thu từng tháng, thứ hạng tháng trong năm và tổng lũy kế:

~~~sql
WITH months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 6
),
monthly_sales AS (
    SELECT TRUNC(sold_at, 'MM') AS month_start,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
),
series AS (
    SELECT m.month_start, NVL(s.revenue, 0) AS revenue
    FROM months m
    LEFT JOIN monthly_sales s
        ON s.month_start = m.month_start
)
SELECT
    month_start,
    revenue,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue,
    LAG(revenue) OVER (ORDER BY month_start) AS previous_revenue
FROM series
ORDER BY month_start;
~~~

Các analytic functions cùng làm việc trên chuỗi sáu tháng đã hoàn chỉnh. Ranking theo doanh thu có thể có ties; running total và LAG theo thứ tự thời gian. Nếu muốn rank riêng trong từng năm, thêm PARTITION BY calendar_year vào hàm rank.

## 16. Thời gian, DATE/TIMESTAMP và múi giờ báo cáo

### 16.1. Dùng biên thời gian tường minh

Với cột DATE:

~~~sql
WHERE sold_at >= DATE '2026-01-01'
  AND sold_at <  DATE '2026-02-01'
~~~

Với cột TIMESTAMP:

~~~sql
WHERE event_time >= TIMESTAMP '2026-01-01 00:00:00'
  AND event_time <  TIMESTAMP '2026-02-01 00:00:00'
~~~

Với cột TIMESTAMP WITH TIME ZONE, hãy xác định kỳ báo cáo theo múi giờ nghiệp vụ. Ví dụ biên tháng 1 theo offset +07:00:

~~~sql
WHERE event_time >= TO_TIMESTAMP_TZ(
          '2026-01-01 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
  AND event_time < TO_TIMESTAMP_TZ(
          '2026-02-01 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
~~~

Nếu nghiệp vụ dùng timezone region có DST, hãy tính biên theo region đó thay vì cộng một offset cố định cho mọi tháng. Cột TIMESTAMP WITH TIME ZONE biểu diễn instant có thông tin timezone/offset; một kỳ lịch địa phương phải được chuyển thành hai instant biên đúng timezone.

### 16.2. Chuyển về ngày địa phương trước khi nhóm

Nếu EVENT_TIME là TIMESTAMP WITH TIME ZONE và báo cáo theo ngày tại Ho Chi Minh City:

~~~sql
SELECT
    TRUNC(
        CAST(event_time AT TIME ZONE 'Asia/Ho_Chi_Minh' AS DATE)
    ) AS local_day,
    COUNT(*) AS event_count
FROM app_events
GROUP BY TRUNC(
    CAST(event_time AT TIME ZONE 'Asia/Ho_Chi_Minh' AS DATE)
)
ORDER BY local_day;
~~~

Biểu thức đưa instant về timezone địa phương rồi chuyển thành DATE để lấy ngày. Nếu báo cáo theo timezone khác, thay region cho phù hợp. Trên bảng lớn, hãy cân nhắc cách lọc theo instant range và cách tổ chức cột/biểu thức để tránh tính toán lặp không cần thiết.

### 16.3. Đừng chuyển cột thời gian thành chuỗi để lọc

Không nên dùng:

~~~sql
WHERE TO_CHAR(sold_at, 'YYYY-MM') = '2026-01'
~~~

cho lọc kỳ chính nếu có thể dùng range predicate. Hàm trên cột có thể cản index range access và phụ thuộc format. TO_CHAR phù hợp cho nhãn hiển thị sau khi dữ liệu đã được lọc/tổng hợp.

## 17. Hiệu năng của báo cáo tổng hợp và analytic

### 17.1. Lọc trước khi tổng hợp

Nếu báo cáo chỉ cần PAID trong sáu tháng, hãy đưa predicate phù hợp vào nguồn trước GROUP BY:

~~~sql
WHERE status = 'PAID'
  AND sold_at >= :start_date
  AND sold_at <  :end_date
~~~

Việc giảm số dòng đầu vào có thể giảm chi phí aggregate, sort và analytic. Optimizer có thể đẩy predicate qua một số query block, nhưng viết rõ điều kiện tại nguồn giúp người đọc hiểu phạm vi dữ liệu và thường tạo cơ hội tối ưu tốt.

### 17.2. Index theo filter và thời gian

Một index như:

~~~sql
CREATE INDEX ix_report_sales_status_date
ON report_sales_lab(status, sold_at);
~~~

có thể hỗ trợ truy vấn lọc theo status và khoảng ngày tùy selectivity/workload. Nhưng nếu báo cáo đọc phần lớn bảng, full table scan và hash/group aggregate có thể hiệu quả hơn. Index cũng tăng chi phí DML và storage.

Không tạo index chỉ vì thấy cột xuất hiện trong WHERE. Cần xem tỷ lệ dòng thỏa điều kiện, thứ tự cột trong index, số cột cần đọc, clustering factor, execution plan và tần suất báo cáo so với tải ghi.

### 17.3. GROUP BY và analytic đều có thể cần sort/hash

GROUP BY, ORDER BY, RANK, ROW_NUMBER, LAG và window frame có thể cần xử lý dữ liệu trung gian, sort hoặc bộ nhớ. Nếu dữ liệu lớn hơn vùng nhớ được cấp, operation có thể spill ra TEMP. Không thể nhìn số dòng SQL rồi suy ra lượng tài nguyên.

### 17.4. Tránh lặp aggregate giống nhau

Nếu cần nhiều chỉ số từ cùng grain, tạo một CTE aggregate rồi dùng lại:

~~~sql
WITH monthly_region AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        COUNT(*) AS sale_count,
        SUM(quantity * unit_price) AS revenue,
        SUM(quantity) AS units
    FROM report_sales_lab
    WHERE status = 'PAID'
    GROUP BY TRUNC(sold_at, 'MM'), region
)
SELECT
    month_start,
    region,
    sale_count,
    revenue,
    units,
    SUM(revenue) OVER (
        PARTITION BY region
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM monthly_region;
~~~

CTE giúp tái sử dụng logic và thể hiện pipeline. Tuy nhiên, Oracle có thể inline/merge CTE; không mặc định mỗi CTE luôn materialize. Nếu cần materialization, hãy hiểu hint/tính năng và đánh giá theo plan, không thêm hint chỉ theo cảm tính.

### 17.5. Kiểm tra execution plan và actual rows

Xem kế hoạch ước lượng:

~~~sql
EXPLAIN PLAN FOR
SELECT region, SUM(quantity * unit_price)
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY region;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Để thu thập thống kê thực thi:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       region, SUM(quantity * unit_price) AS revenue
FROM report_sales_lab
WHERE status = 'PAID'
GROUP BY region;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Các thông tin nên xem:

| Chỉ số | Ý nghĩa |
| --- | --- |
| E-Rows | Số hàng optimizer ước lượng |
| A-Rows | Số hàng thực tế ở operation khi có runtime statistics |
| Starts | Số lần operation được chạy |
| Buffers | Logical I/O |
| A-Time | Thời gian operation được ghi nhận |
| TempSpc | Dung lượng TEMP được ước lượng/sử dụng tùy dạng output và operation |
| Predicate Information | Điều kiện access/filter |

Nếu E-Rows lệch xa A-Rows, hãy kiểm tra thống kê, histogram, skew dữ liệu, tương quan cột và bind values. Không kết luận chỉ từ COST; cost là ước lượng nội bộ của optimizer, không phải mili giây.

## 18. Các lỗi thiết kế báo cáo thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tổng doanh thu bị nhân đôi | JOIN hai bảng detail độc lập làm nhân số dòng | Xác định grain và tổng hợp từng nguồn trước khi JOIN |
| Subtotal bị xếp hạng như sản phẩm | Analytic ranking chạy trên cả dòng subtotal | Tách detail ranking và subtotal thành query block/nhánh riêng |
| NULL bị gắn nhãn TOTAL sai | Dùng NVL để nhận biết subtotal | Dùng GROUPING/GROUPING_ID |
| Tháng 5 biến mất | Không có giao dịch nên GROUP BY không tạo nhóm | Tạo calendar series rồi LEFT JOIN |
| LAG tháng 6 trả tháng 4 | Chuỗi dữ liệu thiếu tháng 5 | Điền kỳ thiếu trước khi dùng LAG |
| Rolling 3 rows không phải 3 tháng | Grain có nhiều dòng/tháng hoặc thiếu tháng | Tổng hợp một dòng/tháng và tạo series liên tục |
| Top 3 trả hơn 3 dòng | Dùng RANK/DENSE_RANK và có ties | Dùng ROW_NUMBER nếu cần đúng tối đa 3 dòng |
| Top 3 chỉ trả 3 dòng nhưng cắt đồng hạng | Dùng ROW_NUMBER | Dùng RANK/DENSE_RANK nếu muốn giữ ties |
| Tháng cùng tên nhiều năm bị gộp | Chỉ nhóm theo MON hoặc MONTH | Dùng TRUNC(date,'MM') hoặc cả năm và tháng |
| Mất giao dịch cuối ngày | Dùng BETWEEN với biên cuối ở 00:00 | Dùng điều kiện lớn hơn/bằng start và nhỏ hơn next_period |
| Tăng trưởng phần trăm lỗi chia 0 | Kỳ trước có doanh thu 0 | Dùng NULLIF và quy ước nghiệp vụ cho trường hợp không xác định |
| Báo cáo chạy chậm sau khi thêm ranking | Sort/window trên tập quá lớn hoặc thiếu lọc | Giảm dữ liệu trước aggregate, kiểm tra plan/TEMP |

## 19. Bài thực hành tổng hợp: báo cáo tháng có tổng phụ, top sản phẩm và lũy kế

Các bước dưới đây kết hợp các kỹ thuật chính. Bảng REPORT_SALES_LAB phải được tạo và nạp dữ liệu ở Mục 2.

### Bước 1 — Tổng hợp theo tháng, khu vực, sản phẩm

~~~sql
WITH monthly_product AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue,
        SUM(quantity) AS units_sold
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY
        TRUNC(sold_at, 'MM'),
        region,
        product_id,
        product_name
)
SELECT *
FROM monthly_product
ORDER BY month_start, region, revenue DESC;
~~~

Mỗi dòng đại diện một sản phẩm trong một khu vực trong một tháng.

### Bước 2 — Xếp hạng sản phẩm trong từng tháng/khu vực

~~~sql
WITH monthly_product AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY
        TRUNC(sold_at, 'MM'),
        region,
        product_id,
        product_name
),
ranked AS (
    SELECT m.*,
           DENSE_RANK() OVER (
               PARTITION BY month_start, region
               ORDER BY revenue DESC
           ) AS revenue_rank
    FROM monthly_product m
)
SELECT *
FROM ranked
WHERE revenue_rank <= 3
ORDER BY month_start, region, revenue_rank, product_name;
~~~

Đây là top 3 rank, nên có thể hơn ba dòng nếu đồng hạng.

### Bước 3 — Tạo tổng phụ theo tháng và khu vực

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    region,
    SUM(quantity * unit_price) AS revenue,
    GROUPING_ID(TRUNC(sold_at, 'MM'), region) AS grouping_level
FROM report_sales_lab
WHERE status = 'PAID'
  AND sold_at >= DATE '2026-01-01'
  AND sold_at < DATE '2026-07-01'
GROUP BY GROUPING SETS (
    (TRUNC(sold_at, 'MM'), region),
    (TRUNC(sold_at, 'MM')),
    (region),
    ()
)
ORDER BY grouping_level, month_start, region;
~~~

Kết quả có detail theo tháng/khu vực, tổng theo tháng, tổng theo khu vực và grand total.

### Bước 4 — Tạo chuỗi tháng và chỉ số lũy kế

~~~sql
WITH months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 6
),
monthly_sales AS (
    SELECT TRUNC(sold_at, 'MM') AS month_start,
           SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM')
),
series AS (
    SELECT m.month_start, NVL(s.revenue, 0) AS revenue
    FROM months m
    LEFT JOIN monthly_sales s
        ON s.month_start = m.month_start
)
SELECT
    month_start,
    revenue,
    SUM(revenue) OVER (
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue,
    LAG(revenue) OVER (ORDER BY month_start) AS previous_revenue,
    revenue - LAG(revenue) OVER (ORDER BY month_start) AS change_amount
FROM series
ORDER BY month_start;
~~~

Tháng 5 có mặt với doanh thu 0. Tổng lũy kế không bị đứt đoạn; LAG của tháng 6 là tháng 5.

### Bước 5 — Tổng hợp toàn bộ thành báo cáo có top-N và subtotal

Mẫu sau tạo hai tập kết quả riêng: top sản phẩm và subtotal. Nó dùng cùng khoảng thời gian và cùng điều kiện PAID:

~~~sql
WITH monthly_product AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        product_id,
        product_name,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY
        TRUNC(sold_at, 'MM'),
        region,
        product_id,
        product_name
),
ranked_product AS (
    SELECT
        m.*,
        ROW_NUMBER() OVER (
            PARTITION BY month_start, region
            ORDER BY revenue DESC, product_id
        ) AS rn
    FROM monthly_product m
),
monthly_region_total AS (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        region,
        SUM(quantity * unit_price) AS revenue
    FROM report_sales_lab
    WHERE status = 'PAID'
      AND sold_at >= DATE '2026-01-01'
      AND sold_at < DATE '2026-07-01'
    GROUP BY TRUNC(sold_at, 'MM'), region
)
SELECT
    month_start,
    region,
    product_name AS label,
    revenue,
    rn AS rank_no,
    'TOP_PRODUCT' AS row_type
FROM ranked_product
WHERE rn <= 3
UNION ALL
SELECT
    month_start,
    region,
    'REGION SUBTOTAL' AS label,
    revenue,
    CAST(NULL AS NUMBER) AS rank_no,
    'SUBTOTAL' AS row_type
FROM monthly_region_total
ORDER BY month_start, region, row_type, rank_no;
~~~

Đây là báo cáo minh họa: mỗi tháng/khu vực có tối đa ba dòng sản phẩm và một dòng tổng phụ. Vì dùng ROW_NUMBER, top sản phẩm có tối đa ba dòng; nếu muốn giữ ties, đổi sang RANK và chấp nhận số dòng có thể vượt ba.

Trong báo cáo thực tế, nên bổ sung GROUPING_ID hoặc cột ROW_TYPE rõ ràng, định nghĩa thứ tự subtotal/detail theo yêu cầu giao diện, và bảo đảm các nhánh UNION ALL có cùng datatype/ý nghĩa cột.

### Bước 6 — Dọn bảng lab (tùy chọn)

~~~sql
-- Chi chay neu chac chan day la bang lab cua ban va khong can du lieu nua.
DROP TABLE report_sales_lab PURGE;
~~~

PURGE bỏ qua recycle bin. Không chạy bước này nếu muốn giữ dữ liệu để tiếp tục thực hành.

## 20. Câu hỏi tự kiểm tra

1. Vì sao phải xác định grain trước khi viết báo cáo?
2. ROLLUP(region, product) tạo những grouping sets nào?
3. ROLLUP(region, product) và ROLLUP(product, region) khác nhau thế nào?
4. Khi nào dùng GROUPING thay vì kiểm tra cột subtotal IS NULL?
5. Với GROUPING_ID(region, product), giá trị nào biểu diễn detail, subtotal region và grand total?
6. GROUPING SETS khác ROLLUP ở khả năng chọn cấp tổng hợp nào?
7. Vì sao CUBE có thể tạo quá nhiều dòng khi số chiều tăng?
8. ROW_NUMBER, RANK, DENSE_RANK xử lý ties khác nhau ra sao?
9. Muốn top 3 sản phẩm mỗi khu vực, PARTITION BY cần chứa cột nào?
10. Vì sao phải aggregate doanh thu sản phẩm trước khi xếp hạng sản phẩm?
11. Tại sao không nên rank trực tiếp tập có cả subtotal và detail?
12. Vì sao GROUP BY tháng không trả tháng không có giao dịch?
13. Calendar series và LEFT JOIN giải quyết vấn đề gì?
14. ROWS BETWEEN 2 PRECEDING AND CURRENT ROW có chắc chắn là ba tháng không?
15. Vì sao phải điền tháng thiếu trước khi dùng LAG nếu muốn so tháng liền kề theo lịch?
16. NULLIF(previous_revenue,0) giải quyết trường hợp nào?
17. Vì sao dùng điều kiện lớn hơn/bằng start và nhỏ hơn next_period thay vì BETWEEN với thời điểm cuối ngày?
18. Tại sao không nên dùng TO_CHAR(cột ngày) trong predicate chính khi có thể dùng range?
19. Một báo cáo có nhiều cấp tổng hợp và ranking nên tách query block như thế nào?
20. Khi so sánh hiệu năng, vì sao cần xem A-Rows, Buffers và actual plan thay vì chỉ COST?

**Gợi ý trả lời:**

1. Để biết mỗi dòng đầu ra đại diện cho đối tượng nào và tránh nhân/giảm số dòng.
2. (region, product), (region), ().
3. Cấp subtotal lần lượt theo region hoặc theo product.
4. Để phân biệt NULL thật trong nguồn với NULL do grouping set loại cột.
5. 0, 1 và 3 theo thứ tự đối số đó.
6. GROUPING SETS cho phép liệt kê đúng các tổ hợp cần; ROLLUP tạo chuỗi tiền tố.
7. CUBE có 2^n grouping sets.
8. ROW_NUMBER luôn duy nhất; RANK chia sẻ rank và có khoảng nhảy; DENSE_RANK chia sẻ rank không nhảy.
9. Các chiều xác định partition, ví dụ region; nếu xếp riêng theo tháng/khu vực thì cả month_start và region.
10. Ranking phải xếp tổng doanh thu ở grain sản phẩm, không phải từng giao dịch.
11. Grand total/subtotal có thể đứng đầu và cạnh tranh vị trí với sản phẩm.
12. Không có dòng nguồn thì không có nhóm.
13. Tạo dòng cho mọi kỳ và gán 0/NULL theo quy ước cho kỳ thiếu.
14. Chỉ khi dữ liệu đã có một dòng cho mỗi tháng và thứ tự phù hợp.
15. LAG đọc dòng trước đang có, không tự biết kỳ lịch bị thiếu.
16. Tránh chia cho 0; phần trăm trong trường hợp đó là không xác định.
17. Bao phủ mọi thời điểm trong kỳ, kể cả fractional seconds.
18. Hàm trên cột có thể cản index range access và phụ thuộc format/NLS.
19. Aggregate detail trước, rank trên detail; subtotal tạo riêng bằng GROUPING SETS/ROLLUP rồi kết hợp.
20. COST là ước lượng; actual rows và buffer/time phản ánh lần chạy thực tế hơn.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): GROUP BY, ROLLUP, CUBE, GROUPING SETS và analytic clause.
- [Oracle Database SQL Language Reference — GROUPING](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GROUPING.html): phân biệt NULL thật và NULL do tổng hợp.
- [Oracle Database SQL Language Reference — GROUPING_ID](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GROUPING_ID.html): mã hóa các cấp grouping.
- [Oracle Database SQL Language Reference — ROW_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROW_NUMBER.html): đánh số dòng theo thứ tự analytic.
- [Oracle Database SQL Language Reference — RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/RANK.html): xếp hạng và ties.
- [Oracle Database SQL Language Reference — LAG](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LAG.html): truy cập giá trị ở dòng trước trong partition.
- [Oracle Database SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): cú pháp partition, order và window frame.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): execution plan, optimizer, index và thống kê.
