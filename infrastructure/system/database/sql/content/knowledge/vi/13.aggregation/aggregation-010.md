# ROLLUP cho tổng phụ theo cấp trong SQL

Khi xem một báo cáo doanh thu, người đọc thường cần **nhiều mức tổng hợp trong cùng một kết quả**: doanh thu của từng ngành hàng, tổng của từng khu vực, rồi tổng toàn công ty. Nếu chỉ sử dụng **GROUP BY thông thường**, truy vấn thường trả về một mức nhóm, chẳng hạn **(khu vực, ngành hàng)**. Để có thêm tổng phụ, ta phải viết nhiều truy vấn và ghép kết quả, hoặc sử dụng một khả năng tổng hợp đặc biệt của SQL: **ROLLUP**.

**ROLLUP** mở rộng GROUP BY bằng cách tạo thêm những **tập nhóm theo các tiền tố của danh sách cột**, từ mức chi tiết đến tổng cộng. Chẳng hạn, **ROLLUP(region, category)** tạo doanh thu theo từng cặp **(region, category)**, tổng theo **region** và **tổng toàn bộ**. Đây là công cụ tiện lợi khi dữ liệu cần trình bày theo cấu trúc cấp bậc.

Bài học thuộc chương **Tổng hợp dữ liệu** của module **Database SQL**. Các ví dụ thực hành dùng **PostgreSQL 15+** và một bảng tạm để chạy độc lập; phần cuối đối chiếu khả năng sử dụng trên **MySQL 8.0, SQL Server, Oracle** và **SQLite**.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **GROUP BY** và **GROUP BY ROLLUP**.
2. Viết **ROLLUP(region, category)** để có số liệu theo ngành hàng, tổng khu vực và tổng toàn bộ.
3. Dự đoán chính xác các cấp mà **ROLLUP(a, b, c)** tạo ra, cũng như tác động khi đổi thứ tự cột.
4. Dùng **GROUPING()** để phân biệt **NULL thật trong dữ liệu** với **NULL do hệ quản trị chèn vào hàng tổng phụ**.
5. Tạo **nhãn cấp tổng hợp**, sắp xếp tổng phụ và chỉ lấy mức tổng hợp mong muốn.
6. Kết hợp **SUM, COUNT, AVG, COUNT(DISTINCT ...)** mà không cộng đúp số liệu.
7. Phân biệt **ROLLUP**, **CUBE** và **GROUPING SETS**.
8. Chuyển cách viết sang phương ngữ khác hoặc mô phỏng bằng **UNION ALL** khi cần.

## 2. Bài toán: báo cáo doanh thu theo hai cấp

Giả sử hệ thống ghi từng lần bán hàng gồm:

- **region**: khu vực kinh doanh, gồm **Bac**, **Nam** và **Trung**.
- **category**: ngành hàng, gồm **Dien tu**, **Van phong** hoặc **NULL** nếu chưa phân loại.
- **sold_on**: ngày giao dịch.
- **amount_vnd**: doanh thu giao dịch, tính bằng đồng Việt Nam.

Nếu chỉ muốn doanh thu cho mỗi **(region, category)**, ta viết:

~~~sql
SELECT region, category, SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY region, category;
~~~

Nhưng báo cáo quản lý còn cần:

~~~text
Toàn công ty: 13.700.000 VND
  Bắc:         7.300.000 VND
    Điện tử:   6.000.000 VND
    Văn phòng: 1.200.000 VND
    Chưa phân loại: 100.000 VND
  Nam:         5.100.000 VND
    Điện tử:   4.000.000 VND
    Văn phòng: 1.100.000 VND
  Trung:       1.300.000 VND
    Điện tử:     800.000 VND
    Văn phòng:   500.000 VND
~~~

Những dòng **Bắc/Nam/Trung** là **tổng phụ theo khu vực** (*subtotals*). Dòng **Toàn công ty** là **tổng chung** (*grand total*). ROLLUP tạo được cả ba mức trong một truy vấn.

## 3. Tạo dữ liệu mẫu độc lập trên PostgreSQL

Ví dụ sử dụng bảng tạm **rollup_demo_sales**, không phụ thuộc bảng nào trong bài học khác. Hãy chạy toàn bộ đoạn sau trong một phiên PostgreSQL:

~~~sql
CREATE TEMP TABLE rollup_demo_sales (
    sale_id      INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL,
    region       TEXT NOT NULL,
    category     TEXT,
    sold_on      DATE NOT NULL,
    amount_vnd   NUMERIC(14, 2) NOT NULL
        CHECK (amount_vnd >= 0)
);

INSERT INTO rollup_demo_sales
    (sale_id, customer_id, region, category, sold_on, amount_vnd)
VALUES
    ( 1, 10, 'Bac',   'Dien tu',   '2026-01-05', 2000000),
    ( 2, 11, 'Bac',   'Dien tu',   '2026-01-20', 1000000),
    ( 3, 10, 'Bac',   'Dien tu',   '2026-02-03', 3000000),
    ( 4, 12, 'Bac',   'Van phong', '2026-01-08',  500000),
    ( 5, 10, 'Bac',   'Van phong', '2026-02-16',  700000),
    ( 6, 13, 'Bac',   NULL,        '2026-02-10',  100000),
    ( 7, 20, 'Nam',   'Dien tu',   '2026-01-05', 1500000),
    ( 8, 21, 'Nam',   'Dien tu',   '2026-02-10', 2500000),
    ( 9, 20, 'Nam',   'Van phong', '2026-01-17',  400000),
    (10, 22, 'Nam',   'Van phong', '2026-02-19',  600000),
    (11, 20, 'Nam',   'Van phong', '2026-02-23',  100000),
    (12, 30, 'Trung', 'Dien tu',   '2026-01-09',  800000),
    (13, 31, 'Trung', 'Van phong', '2026-02-03',  200000),
    (14, 30, 'Trung', 'Van phong', '2026-01-21',  300000);
~~~

Bảng có **14 giao dịch**. Khách hàng có thể có nhiều giao dịch; giao dịch số **6** có category = NULL để minh họa sự khác biệt giữa **NULL thật** và **NULL hiển thị ở dòng tổng phụ**.

Kiểm tra nguồn đầu vào:

~~~sql
SELECT
    COUNT(*) AS sale_count,
    SUM(amount_vnd) AS total_revenue_vnd
FROM rollup_demo_sales;
~~~

Kết quả dự kiến:

| sale_count | total_revenue_vnd |
| ---: | ---: |
| 14 | 13700000.00 |

Đây là **tổng nguồn** để đối chiếu khi đọc các cấp tổng hợp.

> Bảng tạm tồn tại trong phiên kết nối hiện tại. Nếu mở phiên mới, cần tạo lại dữ liệu. Nếu chạy CREATE TEMP TABLE lần hai trong cùng phiên, PostgreSQL sẽ báo tên bảng đã tồn tại; có thể mở phiên mới hoặc xóa riêng bảng tạm của bài rồi tạo lại.

## 4. GROUP BY thông thường chỉ sinh nhóm chi tiết

Chạy:

~~~sql
SELECT
    region,
    category,
    COUNT(*) AS sale_count,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY region, category
ORDER BY region, category NULLS LAST;
~~~

Kết quả gồm **7 nhóm**:

| region | category | sale_count | revenue_vnd |
| --- | --- | ---: | ---: |
| Bac | Dien tu | 3 | 6000000 |
| Bac | Van phong | 2 | 1200000 |
| Bac | NULL | 1 | 100000 |
| Nam | Dien tu | 2 | 4000000 |
| Nam | Van phong | 3 | 1100000 |
| Trung | Dien tu | 1 | 800000 |
| Trung | Van phong | 2 | 500000 |

Mỗi dòng mô tả **một tổ hợp region và category**. Chưa có dòng doanh thu riêng cho cả khu vực Bắc hay cả công ty.

Lưu ý: GROUP BY xem những hàng có cùng category NULL là **một nhóm**. Trong dữ liệu mẫu, Bắc có một giao dịch chưa phân loại ngành hàng; nếu có thêm giao dịch cùng khu vực và category NULL, chúng sẽ được gộp vào cùng nhóm.

## 5. ROLLUP(region, category): thêm hai cấp tổng

Thay GROUP BY bằng:

~~~sql
SELECT
    region,
    category,
    COUNT(*) AS sale_count,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY ROLLUP (region, category);
~~~

PostgreSQL mở rộng danh sách nhóm thành ba tập nhóm:

~~~text
ROLLUP(region, category)

  1. GROUP BY region, category  -- chi tiết từng ngành trong khu vực
  2. GROUP BY region            -- tổng phụ từng khu vực
  3. GROUP BY ()                -- tổng chung toàn bộ dữ liệu
~~~

Số cấp bằng **số biểu thức trong ROLLUP + 1**; với hai biểu thức, có ba cấp. Các dòng của cấp cao hơn không phải một phép tính trên những hàng kết quả đã tổng hợp ở cấp thấp; chúng được tính từ **tập dữ liệu đầu vào thuộc nhóm tương ứng**.

Muốn nhìn rõ từng cấp, dùng thêm hàm **GROUPING** và thứ tự sắp xếp:

~~~sql
SELECT
    region,
    category,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category,
    COUNT(*) AS sale_count,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY ROLLUP (region, category)
ORDER BY
    GROUPING(region),
    region,
    GROUPING(category),
    category NULLS LAST;
~~~

Kết quả minh họa:

| region | category | g_region | g_category | sale_count | revenue_vnd |
| --- | --- | ---: | ---: | ---: | ---: |
| Bac | Dien tu | 0 | 0 | 3 | 6000000 |
| Bac | Van phong | 0 | 0 | 2 | 1200000 |
| Bac | NULL | 0 | 0 | 1 | 100000 |
| Bac | NULL | 0 | 1 | 6 | 7300000 |
| Nam | Dien tu | 0 | 0 | 2 | 4000000 |
| Nam | Van phong | 0 | 0 | 3 | 1100000 |
| Nam | NULL | 0 | 1 | 5 | 5100000 |
| Trung | Dien tu | 0 | 0 | 1 | 800000 |
| Trung | Van phong | 0 | 0 | 2 | 500000 |
| Trung | NULL | 0 | 1 | 3 | 1300000 |
| NULL | NULL | 1 | 1 | 14 | 13700000 |

Từ **7 nhóm chi tiết**, ROLLUP tạo thêm **3 tổng phụ khu vực** và **1 tổng chung**, tức **11 dòng kết quả**. Giá trị **revenue_vnd = 13700000** của dòng cuối trùng với tổng từ bảng nguồn.

**Rất quan trọng:** hai dòng của khu vực Bac đều có **category = NULL**, nhưng mang ý nghĩa khác nhau:

- **(g_region=0, g_category=0):** category NULL **thực sự tồn tại trong dữ liệu**, tổng doanh thu **100.000**.
- **(g_region=0, g_category=1):** category bị **lược khỏi tập nhóm** để thể hiện **tổng cả khu vực Bắc**, doanh thu **7.300.000**.

Không thể phân biệt chính xác hai trường hợp chỉ bằng biểu thức **category IS NULL**.

## 6. GROUPING(): nhận diện dòng chi tiết và dòng tổng

Trong PostgreSQL, **GROUPING(expression)** trả:

- **0** nếu biểu thức **có mặt** trong tập nhóm của dòng kết quả hiện tại;
- **1** nếu biểu thức **đã bị lược bỏ** khi tạo dòng tổng phụ/tổng chung.

Nó **không kiểm tra giá trị có NULL thật hay không**. Một nhóm có category NULL trong dữ liệu nguồn vẫn nhận **GROUPING(category) = 0** nếu category đang là một khóa nhóm của dòng ấy.

### 6.1. Đặt nhãn cho đúng loại dòng

~~~sql
SELECT
    CASE
        WHEN GROUPING(region) = 1 THEN 'Tat ca khu vuc'
        ELSE region
    END AS region_label,
    CASE
        WHEN GROUPING(region) = 1 THEN 'Tong toan bo'
        WHEN GROUPING(category) = 1 THEN 'Tong khu vuc'
        WHEN category IS NULL THEN 'Chua phan loai'
        ELSE category
    END AS category_label,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY ROLLUP (region, category)
ORDER BY GROUPING(region), region,
         GROUPING(category), category NULLS LAST;
~~~

Khi đọc kết quả:

- Giao dịch category NULL thật được hiển thị **Chua phan loai**.
- Dòng tổng của từng region được hiển thị **Tong khu vuc**.
- Dòng toàn bộ có region_label là **Tat ca khu vuc** và category_label là **Tong toan bo**.

Nếu muốn dùng nhãn có dấu tiếng Việt như “Tất cả khu vực”, “Tổng khu vực”, bạn chỉ cần thay **chuỗi hiển thị**, không đổi dữ liệu nguồn hoặc điều kiện GROUPING.

### 6.2. GROUPING với nhiều tham số: mặt nạ bit

PostgreSQL cho phép gọi **GROUPING(region, category)**. Kết quả là một **mặt nạ bit**: biểu thức **cuối cùng** có trọng số **1**, biểu thức trước đó có trọng số **2**, v.v.

~~~sql
SELECT
    region,
    category,
    GROUPING(region, category) AS grouping_mask,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY ROLLUP (region, category)
ORDER BY GROUPING(region), region,
         GROUPING(category), category NULLS LAST;
~~~

| Loại dòng | GROUPING(region) | GROUPING(category) | GROUPING(region, category) |
| --- | ---: | ---: | ---: |
| Chi tiết region + category | 0 | 0 | **0** |
| Tổng một region | 0 | 1 | **1** |
| Tổng toàn bộ | 1 | 1 | **3** |

Các giá trị mặt nạ này giúp phân loại cấp tổng hợp mà không phải đoán từ NULL. **GROUPING** của PostgreSQL đảm nhiệm vai trò gần giống hàm **GROUPING_ID** trên một số hệ quản trị khác; không nên giả định tên hàm GROUPING_ID có sẵn ở mọi phương ngữ.

### 6.3. Không dùng COALESCE để phán đoán tổng phụ

Ví dụ:

~~~sql
SELECT
    region,
    COALESCE(category, 'Tong') AS category_label,
    SUM(amount_vnd)
FROM rollup_demo_sales
GROUP BY ROLLUP(region, category);
~~~

Với dữ liệu mẫu, truy vấn này sẽ gắn nhãn **'Tong'** cho cả **nhóm category NULL thật của Bắc** và **dòng tổng phụ Bắc**. Nhãn sai khiến người đọc tưởng 100.000 đồng là một dòng tổng.

Cách đúng là **ưu tiên GROUPING(category)** trước khi xử lý NULL thật:

~~~sql
CASE
    WHEN GROUPING(category) = 1 THEN 'Tong khu vuc'
    WHEN category IS NULL THEN 'Chua phan loai'
    ELSE category
END
~~~

## 7. Thứ tự cột trong ROLLUP quyết định cấp tổng

**ROLLUP(region, category)** và **ROLLUP(category, region)** không tương đương.

| Cú pháp | Các tập nhóm sinh ra |
| --- | --- |
| ROLLUP(region, category) | (region, category), (region), () |
| ROLLUP(category, region) | (category, region), (category), () |

Trường hợp thứ nhất cho tổng của **từng khu vực**. Trường hợp thứ hai cho tổng của **từng ngành hàng trên toàn bộ các khu vực**.

Ví dụ:

~~~sql
SELECT
    region,
    category,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY ROLLUP(category, region)
ORDER BY GROUPING(category), category NULLS LAST,
         GROUPING(region), region;
~~~

Truy vấn này có các dòng tổng phụ theo **Dien tu**, **Van phong** và một nhóm category NULL của dữ liệu nguồn, bên cạnh dòng tổng toàn bộ. Tổng doanh thu theo ngành:

| category | Doanh thu toàn bộ khu vực |
| --- | ---: |
| Dien tu | 10800000 |
| Van phong | 2800000 |
| Chua phan loai | 100000 |
| **Tổng chung** | **13700000** |

Các giá trị trên tính từ **6.000.000 + 4.000.000 + 800.000** cho Dien tu và **1.200.000 + 1.100.000 + 500.000** cho Van phong.

**Kết luận:** đặt cột mô tả **cấp lớn hơn** ở trước, rồi đến cột mô tả **cấp chi tiết hơn**, khi muốn tạo tổng phụ theo phân cấp đó. ROLLUP không tự biết khu vực và ngành hàng có ý nghĩa nào; chính **thứ tự biểu thức** tạo nên đường tổng phụ.

## 8. ROLLUP trên ba cấp: khu vực → ngành hàng → tháng

Trong dữ liệu mẫu, có thể mở rộng báo cáo thành:

~~~text
Toàn bộ
  └── Khu vực
        └── Ngành hàng
              └── Tháng
~~~

Ví dụ, mọi giao dịch cùng **region, category và tháng** được gom thành một nhóm chi tiết. Khi cuộn lên (*roll up*), SQL lần lượt bỏ tháng, bỏ ngành hàng, rồi bỏ khu vực.

### 8.1. Chuẩn hóa khóa tháng trong CTE

Với PostgreSQL, **DATE_TRUNC('month', sold_on)** lấy đầu tháng. Ép về DATE để có khóa tháng rõ ràng:

~~~sql
WITH sales_by_month AS (
    SELECT
        region,
        category,
        DATE_TRUNC('month', sold_on)::DATE AS month_start,
        amount_vnd
    FROM rollup_demo_sales
)
SELECT
    region,
    category,
    month_start,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category,
    GROUPING(month_start) AS g_month,
    GROUPING(region, category, month_start) AS grouping_mask,
    COUNT(*) AS sale_count,
    SUM(amount_vnd) AS revenue_vnd
FROM sales_by_month
GROUP BY ROLLUP (region, category, month_start)
ORDER BY
    GROUPING(region), region,
    GROUPING(category), category NULLS LAST,
    GROUPING(month_start), month_start NULLS LAST;
~~~

**ROLLUP(region, category, month_start)** tương đương bốn tập nhóm:

~~~text
(region, category, month_start)  -- doanh thu từng tháng/ngành/khu vực
(region, category)               -- tổng ngành trong khu vực
(region)                         -- tổng khu vực
()                               -- tổng toàn bộ
~~~

Các mặt nạ tương ứng khi gọi **GROUPING(region, category, month_start)**:

| Cấp | Các khóa còn lại | g_region | g_category | g_month | mask |
| --- | --- | ---: | ---: | ---: | ---: |
| Chi tiết tháng | region, category, month_start | 0 | 0 | 0 | **0** |
| Tổng ngành trong khu vực | region, category | 0 | 0 | 1 | **1** |
| Tổng khu vực | region | 0 | 1 | 1 | **3** |
| Tổng toàn bộ | không còn khóa | 1 | 1 | 1 | **7** |

Ở dữ liệu mẫu, có **12 tổ hợp (region, category, month_start)** khác nhau, **7 tổ hợp (region, category)**, **3 khu vực** và **1 tổng chung**: tổng cộng **23 dòng kết quả**. Các tổng phụ lặp lại giá trị doanh thu của dữ liệu theo **những cấp khác nhau**, không phải 23 giao dịch nguồn.

### 8.2. ROLLUP không tự tạo mọi kiểu tổng phụ

Truy vấn ba cấp trên **không tạo riêng doanh thu theo (region, month_start) bỏ category**, cũng không tạo **tổng doanh thu từng tháng của toàn công ty** theo (month_start). Lý do: các tập nhóm của ROLLUP chỉ là **các tiền tố** của danh sách, không phải mọi tổ hợp cột.

Nếu muốn có tổng theo từng tháng của toàn bộ công ty, một truy vấn riêng đơn giản là:

~~~sql
SELECT
    DATE_TRUNC('month', sold_on)::DATE AS month_start,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY DATE_TRUNC('month', sold_on)::DATE
ORDER BY month_start;
~~~

Kết quả:

| month_start | revenue_vnd |
| --- | ---: |
| 2026-01-01 | 6500000 |
| 2026-02-01 | 7200000 |

Nếu cần **cả tháng và những cấp ROLLUP khác trong cùng một kết quả**, phần **GROUPING SETS** bên dưới là công cụ phù hợp.

### 8.3. ROLLUP theo nhóm cột ghép

Trong PostgreSQL, có thể xem **(region, category)** như **một đơn vị nhóm** khi mô tả các mức cần tổng hợp. Chẳng hạn:

~~~sql
WITH sales_by_month AS (
    SELECT
        region,
        category,
        DATE_TRUNC('month', sold_on)::DATE AS month_start,
        amount_vnd
    FROM rollup_demo_sales
)
SELECT
    region, category, month_start,
    SUM(amount_vnd) AS revenue_vnd
FROM sales_by_month
GROUP BY ROLLUP ((region, category), month_start);
~~~

Biểu thức này sinh các mức:

~~~text
(region, category, month_start)
(region, category)
()
~~~

Nó **bỏ qua riêng cấp (region)** bởi vì region và category được cuộn lên như **một nhóm ghép**. Đây là tùy chọn hữu ích nếu cấu trúc báo cáo không cần mọi mức nằm giữa, nhưng cách hỗ trợ cú pháp nhóm ghép có thể khác giữa các phương ngữ.

## 9. Lọc dữ liệu trước ROLLUP và lọc cấp tổng hợp sau ROLLUP

Hai nhu cầu lọc này rất khác nhau:

- **WHERE** chọn những **hàng giao dịch nguồn** sẽ tham gia tính tổng.
- **HAVING** hoặc một truy vấn ngoài sẽ chọn những **nhóm kết quả** cần hiển thị.

### 9.1. WHERE giới hạn tập dữ liệu được tổng hợp

Chẳng hạn chỉ báo cáo giao dịch trong **tháng 02/2026**:

~~~sql
SELECT
    region,
    category,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on < DATE '2026-03-01'
GROUP BY ROLLUP (region, category)
ORDER BY GROUPING(region), region,
         GROUPING(category), category NULLS LAST;
~~~

Lúc này tổng chung của ROLLUP là **7.200.000 VND**, không phải **13.700.000 VND**, vì WHERE đã loại các giao dịch tháng 01 trước bước nhóm.

Tổng theo khu vực tháng 02:

| region | revenue_vnd |
| --- | ---: |
| Bac | 3800000 |
| Nam | 3200000 |
| Trung | 200000 |
| **Toàn bộ** | **7200000** |

Nếu WHERE chỉ chọn **region = 'Bac'**, dòng tổng chung do ROLLUP sinh ra cũng chỉ là tổng **trong tập Bắc đã được lọc**, không phải tổng của toàn công ty. **"Grand total" luôn là tổng của đầu vào hiện tại sau các bộ lọc nguồn.**

### 9.2. Chỉ lấy các dòng tổng khu vực

Có thể đưa kết quả ROLLUP vào CTE, rồi lọc bằng cờ GROUPING:

~~~sql
WITH report AS (
    SELECT
        region,
        category,
        GROUPING(region) AS g_region,
        GROUPING(category) AS g_category,
        SUM(amount_vnd) AS revenue_vnd
    FROM rollup_demo_sales
    GROUP BY ROLLUP (region, category)
)
SELECT region, revenue_vnd
FROM report
WHERE g_region = 0
  AND g_category = 1
ORDER BY region;
~~~

Kết quả chỉ gồm:

| region | revenue_vnd |
| --- | ---: |
| Bac | 7300000 |
| Nam | 5100000 |
| Trung | 1300000 |

Không thể thay bộ lọc cờ bằng **WHERE category IS NULL** trên bảng nguồn: điều kiện ấy sẽ chỉ giữ các giao dịch **chưa có category**, chứ không chọn những dòng tổng phụ đã được tính.

### 9.3. HAVING lọc các nhóm sau khi tổng hợp

Trong PostgreSQL có thể viết:

~~~sql
SELECT
    region,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY ROLLUP(region, category)
HAVING GROUPING(region) = 0
   AND GROUPING(category) = 1
ORDER BY region;
~~~

Kết quả giống CTE ở trên. **HAVING** chạy theo ngữ nghĩa trên các nhóm đã tạo, nên có thể dựa vào **SUM**, **COUNT** hoặc **GROUPING**.

Nếu dùng:

~~~sql
HAVING SUM(amount_vnd) >= 1000000
~~~

SQL sẽ giữ các dòng **ở bất kỳ cấp nào** có tổng đạt ngưỡng. Một số nhóm chi tiết nhỏ sẽ biến mất, nhưng tổng khu vực vẫn tính trên **toàn bộ dữ liệu của khu vực**, không phải chỉ các nhóm chi tiết còn hiển thị. Vì vậy, tổng phụ **không nhất thiết bằng tổng của những dòng chi tiết đang nhìn thấy sau HAVING**.

## 10. Sắp xếp các cấp tổng hợp cho dễ đọc

**ROLLUP không tự đảm bảo thứ tự hàng.** Khi không có ORDER BY, không nên dự đoán rằng hệ quản trị sẽ luôn in dòng chi tiết trước, tổng phụ ngay sau, rồi tổng toàn bộ ở cuối.

Câu truy vấn sau sắp theo khu vực, ngành hàng rồi đưa dòng tổng phụ sau các nhóm chi tiết:

~~~sql
SELECT
    region,
    category,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY ROLLUP(region, category)
ORDER BY
    GROUPING(region),
    region,
    GROUPING(category),
    category NULLS LAST;
~~~

Giải thích thứ tự:

1. **GROUPING(region) = 0** trước, nên các khu vực thật xuất hiện trước tổng toàn bộ có cờ 1.
2. **region** sắp các khu vực.
3. **GROUPING(category) = 0** trước, nên các ngành hàng chi tiết xuất hiện trước dòng tổng khu vực có cờ 1.
4. **category NULLS LAST** đặt category NULL thật ở cuối các chi tiết của khu vực, nhưng vẫn **trước** dòng tổng phụ nhờ cờ GROUPING.

Không nên viết chỉ:

~~~sql
ORDER BY region, category;
~~~

rồi giả định NULL ở tổng phụ sẽ luôn nằm đúng vị trí muốn hiển thị trên mọi hệ. Thứ tự mặc định của NULL và cách sắp chữ phụ thuộc phương ngữ/collation. **GROUPING là dấu hiệu đáng tin cậy hơn** để đặt tổng phụ.

Trong báo cáo có nhiều cấp, bạn cũng có thể xây dựng một cột **level_code** hoặc mặt nạ bit GROUPING để phía ứng dụng render chữ đậm, thụt lề và phân biệt loại dòng mà không phải đoán theo giá trị NULL.

## 11. SUM, COUNT, AVG và số lượng khách hàng khác nhau

ROLLUP dùng được với nhiều hàm tổng hợp. Tuy nhiên, **không phải chỉ tiêu nào cũng cộng được trực tiếp giữa các cấp**.

### 11.1. SUM và COUNT(*) là chỉ tiêu cộng được theo các nhóm rời nhau

~~~sql
SELECT
    region,
    category,
    GROUPING(region, category) AS level_mask,
    COUNT(*) AS sale_count,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY ROLLUP(region, category);
~~~

Ở cấp region Bac, **sale_count = 6**, **revenue_vnd = 7.300.000**. Vì các nhóm category trong một khu vực không chồng lấn về **giao dịch**, có thể cộng số lượng và tiền của các nhóm chi tiết để đối chiếu tổng khu vực.

Nhưng nếu đem cộng **tất cả dòng** của kết quả ROLLUP lại, mỗi giao dịch đã có mặt ở **ba cấp**: chi tiết ngành, tổng khu vực và tổng toàn bộ. Lúc này tổng cộng doanh thu qua mọi dòng trở thành:

\[
3 \times 13\,700\,000 = 41\,100\,000\text{ VND}.
\]

Con số **41.100.000** không phải doanh thu thực. Đây là lỗi **cộng đúp tổng phụ** (thực chất là cộng cùng giao dịch ba lần) khi xuất kết quả ROLLUP sang một bảng báo cáo khác.

### 11.2. AVG không được tính bằng trung bình đơn giản của các AVG nhóm

~~~sql
SELECT
    region,
    category,
    COUNT(*) AS sale_count,
    AVG(amount_vnd) AS avg_sale_vnd
FROM rollup_demo_sales
GROUP BY ROLLUP(region, category)
ORDER BY GROUPING(region), region,
         GROUPING(category), category NULLS LAST;
~~~

Đối với khu vực Bac:

- Điện tử: **6.000.000 / 3 = 2.000.000** một giao dịch.
- Văn phòng: **1.200.000 / 2 = 600.000** một giao dịch.
- Chưa phân loại: **100.000 / 1 = 100.000** một giao dịch.
- **AVG của toàn khu vực Bac = 7.300.000 / 6 ≈ 1.216.666,67**.

Nếu chỉ lấy trung bình không trọng số của ba AVG ngành hàng, kết quả là **900.000**, không đúng AVG giao dịch của cả khu vực. ROLLUP tính AVG đúng theo **tất cả hàng của cấp tương ứng**; việc lấy trung bình các giá trị trung bình phải xét số lượng của từng nhóm.

### 11.3. COUNT(DISTINCT customer_id) không có tính cộng đơn giản

~~~sql
SELECT
    region,
    category,
    GROUPING(region, category) AS level_mask,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM rollup_demo_sales
GROUP BY ROLLUP(region, category)
ORDER BY GROUPING(region), region,
         GROUPING(category), category NULLS LAST;
~~~

Ở khu vực Bac:

- Điện tử có **2** khách khác nhau: 10 và 11.
- Văn phòng có **2** khách khác nhau: 12 và 10.
- Chưa phân loại có **1** khách: 13.
- Cộng các số theo ngành được **5**, nhưng toàn khu vực Bac chỉ có **4 khách duy nhất**: 10, 11, 12, 13.

Khách **10** có giao dịch ở hai ngành hàng nên bị đếm hai lần nếu cộng các số **COUNT DISTINCT** của từng ngành. ROLLUP có thể tính trực tiếp **COUNT(DISTINCT customer_id)** ở cấp region để nhận giá trị đúng của cấp ấy.

**Tóm lại:** **SUM và COUNT(*) trên các nhóm giao dịch rời nhau** có thể đối chiếu qua phép cộng. **AVG và COUNT(DISTINCT)** cần tính trực tiếp ở cấp mục tiêu hoặc sử dụng phương pháp tổng hợp đúng, không lấy tổng cơ học các chỉ tiêu con.

## 12. ROLLUP, GROUPING SETS và CUBE

Trong PostgreSQL, ROLLUP là một cách viết ngắn cho một số **GROUPING SETS** xác định. Nắm được mối quan hệ này giúp chọn đúng công cụ khi báo cáo phức tạp hơn.

### 12.1. ROLLUP tương đương GROUPING SETS theo tiền tố

~~~sql
SELECT region, category, SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY ROLLUP(region, category);
~~~

Tương đương:

~~~sql
SELECT region, category, SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY GROUPING SETS (
    (region, category),
    (region),
    ()
);
~~~

Ở đây, **()** nghĩa là một tập nhóm rỗng: tạo dòng tổng từ toàn bộ hàng nguồn phù hợp với WHERE, không phân chia theo cột nào.

### 12.2. GROUPING SETS chọn các mức tùy ý

Giả sử cần cả doanh thu theo khu vực/ngành hàng và **tổng theo ngành trên toàn quốc**, nhưng không cần tổng khu vực. Có thể viết:

~~~sql
SELECT
    region,
    category,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category,
    SUM(amount_vnd) AS revenue_vnd
FROM rollup_demo_sales
GROUP BY GROUPING SETS (
    (region, category),
    (category),
    ()
);
~~~

Các mức được tạo chính xác là **(region, category)**, **(category)** và **()**. Ta không bị giới hạn ở tiền tố của một danh sách như ROLLUP.

Với ba chiều, có thể yêu cầu thêm **doanh thu từng tháng toàn công ty**:

~~~sql
WITH sales_by_month AS (
    SELECT
        region,
        category,
        DATE_TRUNC('month', sold_on)::DATE AS month_start,
        amount_vnd
    FROM rollup_demo_sales
)
SELECT
    region,
    category,
    month_start,
    GROUPING(region, category, month_start) AS level_mask,
    SUM(amount_vnd) AS revenue_vnd
FROM sales_by_month
GROUP BY GROUPING SETS (
    (region, category, month_start),
    (region, category),
    (region),
    (month_start),
    ()
);
~~~

Ngoài các cấp của ROLLUP ba chiều, truy vấn có thêm **(month_start)** cho tổng từng tháng toàn công ty.

### 12.3. CUBE tạo mọi tổ hợp nhóm

**CUBE(region, category)** trong PostgreSQL sinh:

~~~text
(region, category)
(region)
(category)
()
~~~

Nó có thêm cấp **(category)** so với **ROLLUP(region, category)**. Với **n chiều độc lập**, CUBE có thể sinh tới **2^n tập nhóm**, còn ROLLUP đơn giản trên n chiều sinh **n + 1 tập nhóm**.

| Nhu cầu | Cấu trúc phù hợp |
| --- | --- |
| Đi từ chi tiết đến tổng theo thứ tự cấp bậc | **ROLLUP** |
| Lấy mọi tổ hợp nhóm theo các chiều | **CUBE** |
| Chọn những cấp không theo một chuỗi tiền tố cố định | **GROUPING SETS** |

**Chọn ít cấp cần thiết nhất** để tránh tạo rất nhiều hàng tổng hợp không dùng tới. Với dữ liệu nhiều chiều, CUBE có thể làm số nhóm và khối lượng tính toán tăng mạnh.

## 13. Tính đa phương ngữ: không phải SQL nào cũng viết ROLLUP giống nhau

Khái niệm tổng phụ có mặt ở nhiều RDBMS, nhưng **cú pháp và tính năng kèm theo** khác nhau.

| Hệ quản trị | Cú pháp tổng phụ tiêu biểu | Nhận diện dòng tổng | Ghi chú |
| --- | --- | --- | --- |
| **PostgreSQL 15+** | GROUP BY ROLLUP(region, category) | GROUPING(region), GROUPING(category), GROUPING(region, category) | Hỗ trợ GROUPING SETS và CUBE |
| **SQL Server** | GROUP BY ROLLUP(region, category) | GROUPING, GROUPING_ID | Có GROUPING SETS, CUBE; cú pháp quản lý kết quả khác PostgreSQL ở chi tiết |
| **Oracle Database** | GROUP BY ROLLUP(region, category) | GROUPING, GROUPING_ID | Có thể dùng cùng các cấu trúc tổng hợp mở rộng |
| **MySQL 8.0** | GROUP BY region, category WITH ROLLUP | GROUPING(...) ở các phiên bản 8.0 hỗ trợ | Cú pháp WITH ROLLUP đặc trưng; có khác biệt về ORDER BY và GROUPING SETS |
| **SQLite** | Không có GROUP BY ROLLUP tích hợp như PostgreSQL | Tạo cột mức tổng hợp thủ công | Có thể mô phỏng bằng nhiều GROUP BY ghép UNION ALL |

Trong MySQL 8.0, ví dụ tương đương được viết:

~~~sql
-- Cú pháp MySQL, không phải PostgreSQL:
SELECT
    region,
    category,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category,
    SUM(amount_vnd) AS revenue_vnd
FROM sales
GROUP BY region, category WITH ROLLUP;
~~~

**MySQL không dùng nguyên văn GROUP BY ROLLUP(region, category) trong cách viết tiêu biểu trên.** Cũng không nên dựa vào thứ tự dòng của WITH ROLLUP nếu không quy định rõ cách hiển thị. Phạm vi hỗ trợ hàm GROUPING và những hạn chế ORDER BY có thể khác theo phiên bản MySQL 8.0; khi chuyển truy vấn, cần đối chiếu tài liệu phiên bản sử dụng.

Ví dụ SQL Server:

~~~sql
-- Cú pháp SQL Server:
SELECT
    region,
    category,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category,
    SUM(amount_vnd) AS revenue_vnd
FROM dbo.sales
GROUP BY ROLLUP(region, category);
~~~

SQL Server còn cung cấp **GROUPING_ID(...)** để lấy mã mức nhóm. Trong PostgreSQL, **GROUPING(region, category)** trả mặt nạ tương đương cho tình huống này; việc đổi tên hàm cần được kiểm tra khi chuyển phương ngữ.

### 13.1. Mô phỏng ROLLUP bằng UNION ALL khi hệ không hỗ trợ

Trên SQLite, hoặc khi muốn hiểu rõ cách ROLLUP ghép các cấp, có thể viết ba truy vấn GROUP BY rồi nối bằng **UNION ALL**:

~~~sql
-- Ý tưởng chạy trên SQLite với bảng sales đã có:
SELECT
    region,
    category,
    'detail' AS level_code,
    SUM(amount_vnd) AS revenue_vnd
FROM sales
GROUP BY region, category

UNION ALL

SELECT
    region,
    NULL AS category,
    'region_total' AS level_code,
    SUM(amount_vnd) AS revenue_vnd
FROM sales
GROUP BY region

UNION ALL

SELECT
    NULL AS region,
    NULL AS category,
    'grand_total' AS level_code,
    SUM(amount_vnd) AS revenue_vnd
FROM sales;
~~~

**UNION ALL** giữ các dòng ở tất cả cấp, kể cả khi chúng có cùng giá trị hiển thị ở region/category. Cột **level_code** đảm nhận vai trò giúp phân biệt nhóm chi tiết với tổng phụ, tương tự ý nghĩa của các cờ GROUPING.

Tùy hệ, cần chú ý kiểu dữ liệu của các cột NULL, cách sắp xếp kết quả UNION ALL và định dạng số. Nếu có điều kiện WHERE lọc giao dịch, phải áp dụng **cùng điều kiện nguồn** cho cả ba nhánh; nếu không, số liệu của các cấp sẽ không còn tương ứng.

Mô phỏng bằng UNION ALL cho phép thêm hoặc bỏ cấp tùy nhu cầu, nhưng có thể khiến bảng nguồn được đọc nhiều lần và lặp logic tổng hợp. Khi hệ có ROLLUP trực tiếp, dùng tính năng tích hợp thường ngắn gọn hơn và để bộ tối ưu có thêm lựa chọn.

## 14. ROLLUP và các bẫy vận hành báo cáo

### 14.1. Cộng đúp dòng tổng phụ

Nếu kết quả gồm detail + region subtotal + grand total, **không chạy một SUM khác trên tất cả các dòng báo cáo** rồi coi đó là doanh thu thật. Chọn một cấp xác định bằng **GROUPING** hoặc tính trực tiếp từ bảng nguồn.

Nếu xuất kết quả ROLLUP ra CSV hoặc đưa vào công cụ BI, hãy thêm **level_code/grouping_mask** để phía tiêu thụ biết dòng nào là detail, subtotal hay grand total.

### 14.2. Nhầm NULL thật với NULL tổng phụ

Trường hợp category NULL thật trong dữ liệu mẫu tạo **một dòng chi tiết**. Dòng tổng khu vực cũng có category NULL. **Chỉ GROUPING(category)** mới cho biết category có bị lược khỏi khóa nhóm hay không.

### 14.3. Nghĩ ROLLUP là mọi tổ hợp cột

**ROLLUP(region, category, month_start)** không tạo các tổng theo tháng toàn công ty, theo (region, month_start) hay theo category toàn công ty. Nếu cần những tập nhóm đó, sử dụng **GROUPING SETS/CUBE** hoặc truy vấn phù hợp.

### 14.4. Đổi thứ tự cột mà không xem lại cấp tổng

**ROLLUP(region, category)** cho tổng khu vực; **ROLLUP(category, region)** cho tổng ngành hàng. Cả hai đều có thể hợp lệ nhưng diễn đạt **câu hỏi kinh doanh khác nhau**.

### 14.5. Tin vào thứ tự mặc định

Không có ORDER BY thì thứ tự các nhóm không được SQL bảo đảm. Để tổng phụ nằm gần chi tiết theo đúng cách, sắp bằng **GROUPING()**, các cột nhóm và quy tắc NULL thích hợp.

### 14.6. Dùng HAVING làm biến mất chi tiết rồi cho rằng tổng phụ đã đổi

HAVING trên SUM hoặc COUNT có thể loại một vài **dòng nhóm** nhưng không làm lại tổng cấp cha từ những dòng chi tiết còn hiển thị. **WHERE** mới thay đổi tập giao dịch tham gia tổng hợp.

### 14.7. Cộng AVG hoặc COUNT DISTINCT giữa các nhóm

AVG phải được tính theo số hàng gốc hoặc trọng số phù hợp. COUNT(DISTINCT customer_id) ở hai ngành có thể cùng đếm một khách hàng, nên tổng của các chỉ tiêu con có thể khác kết quả ở cấp cha.

### 14.8. Mất dấu vết bộ lọc báo cáo

Một dòng ghi “Tổng toàn bộ” không nói lên rằng số liệu đó có bao gồm tất cả các năm, chi nhánh hay trạng thái đơn không. Hãy ghi lại **khoảng thời gian, đơn vị tiền, điều kiện WHERE, quy ước ghi nhận doanh thu và phiên bản quy tắc** khi xuất báo cáo.

### 14.9. ROLLUP trên nhiều chiều có thể tạo nhiều nhóm

Dù ROLLUP chỉ có n+1 cấp, mỗi cấp vẫn có thể chứa **rất nhiều tổ hợp giá trị khác nhau**. Trên bảng lớn, tính nhiều SUM/COUNT DISTINCT và các nhóm chi tiết có thể tốn tài nguyên. Nên chọn đúng cấp cần báo cáo và xem kế hoạch thực thi nếu cần tối ưu.

## 15. Một báo cáo hoàn chỉnh có nhãn và thứ tự

Truy vấn dưới đây là ví dụ dễ dùng cho một bảng báo cáo khu vực/ngành hàng:

~~~sql
WITH rollup_report AS (
    SELECT
        region,
        category,
        GROUPING(region) AS g_region,
        GROUPING(category) AS g_category,
        GROUPING(region, category) AS level_mask,
        COUNT(*) AS sale_count,
        SUM(amount_vnd) AS revenue_vnd
    FROM rollup_demo_sales
    GROUP BY ROLLUP(region, category)
)
SELECT
    CASE
        WHEN g_region = 1 THEN 'Tat ca khu vuc'
        ELSE region
    END AS region_label,
    CASE
        WHEN level_mask = 3 THEN 'Tong toan bo'
        WHEN level_mask = 1 THEN 'Tong khu vuc'
        WHEN category IS NULL THEN 'Chua phan loai'
        ELSE category
    END AS category_label,
    CASE level_mask
        WHEN 0 THEN 'DETAIL'
        WHEN 1 THEN 'REGION_SUBTOTAL'
        WHEN 3 THEN 'GRAND_TOTAL'
    END AS row_level,
    sale_count,
    revenue_vnd
FROM rollup_report
ORDER BY
    g_region,
    region,
    g_category,
    category NULLS LAST;
~~~

Cột **row_level** có giá trị ổn định để phía ứng dụng nhận biết loại dòng. Đây là một **nhãn kỹ thuật**, không phải dữ liệu giao dịch; có thể dùng để tô đậm tổng phụ, thêm đường kẻ giữa các vùng hoặc ẩn các dòng cấp không cần thiết.

Với dữ liệu mẫu, bảng báo cáo này có **11 dòng** và một dòng **GRAND_TOTAL** bằng **13.700.000 VND**. Đừng tính doanh thu thực bằng tổng của tất cả 11 dòng sau khi đã có các tổng phụ.

## 16. Bài tập thực hành

Sử dụng bảng tạm **rollup_demo_sales** đã tạo ở phần 3:

1. Viết GROUP BY region, category để liệt kê tổng tiền theo từng cặp; xác định số dòng kết quả.
2. Thay bằng **GROUP BY ROLLUP(region, category)**. Dự đoán số dòng và chỉ ra các tổng khu vực/tổng toàn bộ.
3. Thêm **GROUPING(region)**, **GROUPING(category)** và **GROUPING(region, category)** vào SELECT. Xác định dòng nào là chi tiết, dòng nào là tổng phụ và dòng nào là tổng chung.
4. Giải thích vì sao khu vực Bac có **hai dòng category NULL** nhưng không cùng ý nghĩa.
5. Dùng CASE kết hợp GROUPING để gắn ba nhãn **Chua phan loai**, **Tong khu vuc**, **Tong toan bo**.
6. Chỉ lấy **dòng tổng khu vực** bằng CTE và các cờ GROUPING, không dùng category IS NULL để phán đoán.
7. Đổi thứ tự thành **ROLLUP(category, region)**. Tính doanh thu tổng theo ngành hàng và giải thích tại sao các tổng này khác tổng khu vực.
8. Dùng một CTE chuẩn hóa **month_start**, rồi viết **ROLLUP(region, category, month_start)**. Liệt kê bốn cấp nhóm và các giá trị mặt nạ tương ứng.
9. Thêm tập nhóm **(month_start)** vào báo cáo bằng GROUPING SETS và xác định tổng tháng 01, tháng 02.
10. Lọc dữ liệu nguồn chỉ còn tháng 02 bằng WHERE. Tổng chung của ROLLUP phải là bao nhiêu?
11. Viết hai truy vấn: một truy vấn dùng **HAVING GROUPING(category)=1** để chọn các tổng theo khu vực và toàn bộ, một truy vấn lọc thêm GROUPING(region)=0 để chỉ giữ tổng khu vực.
12. Sắp xếp kết quả để mỗi khu vực có các ngành hàng chi tiết trước, tổng khu vực sau và tổng toàn bộ cuối cùng.
13. Tính AVG(amount_vnd) ở mỗi cấp ROLLUP. Vì sao **AVG của khu vực Bac** không bằng trung bình đơn giản của AVG ba nhóm ngành?
14. Tính COUNT(DISTINCT customer_id) ở các cấp. Vì sao cộng số khách duy nhất theo ngành của Bac cho kết quả khác số khách duy nhất của cả Bac?
15. So sánh ROLLUP(region, category) với **CUBE(region, category)**. CUBE có thêm loại tổng nào?
16. Viết **GROUPING SETS((region, category), (region), ())** và so sánh tập dòng với ROLLUP hai cấp.
17. Mô phỏng ROLLUP hai cấp bằng **ba SELECT ... GROUP BY** ghép **UNION ALL** và thêm level_code. Kiểm tra tổng nguồn vẫn là 13.700.000, không phải tổng của mọi dòng ROLLUP.
18. Giải thích cú pháp tổng phụ tương đương trên **MySQL 8.0** và cách viết trên **SQLite** khi không có ROLLUP tích hợp.

### Câu hỏi tự kiểm tra

**Câu 1:** ROLLUP(region, category) tạo bao nhiêu cấp nhóm?

**Đáp án:** **Ba cấp**: (region, category), (region), ().

**Câu 2:** Dòng có category NULL và GROUPING(category) = 0 có phải dòng tổng phụ không?

**Đáp án:** **Không.** Category vẫn là khóa nhóm, nhưng giá trị dữ liệu thật của nhóm đó là NULL.

**Câu 3:** GROUPING(region, category) = 3 có nghĩa gì với ROLLUP(region, category)?

**Đáp án:** Cả region và category đều bị lược khỏi nhóm, tức **dòng tổng toàn bộ**.

**Câu 4:** ROLLUP(region, category, month_start) có tạo tổng theo (region, month_start) không?

**Đáp án:** **Không.** Các tập nhóm chỉ là các tiền tố: (region, category, month_start), (region, category), (region), ().

**Câu 5:** Nếu WHERE chỉ giữ giao dịch tháng 02, grand total của ROLLUP là tổng cả hai tháng hay chỉ tháng 02?

**Đáp án:** **Chỉ tháng 02**, vì WHERE lọc dữ liệu nguồn trước khi nhóm.

**Câu 6:** Có được lấy SUM của tất cả dòng ROLLUP để ra tổng doanh thu không?

**Đáp án:** **Không.** Nhiều dòng đã là tổng phụ hoặc tổng chung của cùng tập giao dịch, nên cộng lại sẽ đếm nhiều lần.

**Câu 7:** COUNT(DISTINCT customer_id) ở cấp khu vực có bằng tổng COUNT DISTINCT của các ngành trong khu vực không?

**Đáp án:** **Không nhất thiết.** Một khách có thể mua ở nhiều ngành hàng nên bị đếm lặp khi cộng kết quả từ các ngành.

## 17. Ghi nhớ cốt lõi

**ROLLUP tạo tổng phụ theo những cấp liên tiếp từ trái sang phải trong danh sách GROUP BY.** Với **ROLLUP(a, b, c)**, các tập nhóm là **(a,b,c) → (a,b) → (a) → ()**. Thứ tự biểu thức quyết định đang tổng hợp theo cấp nào, và dòng tổng chung chỉ phản ánh **tập dữ liệu đã qua WHERE**.

**GROUPING() là chìa khóa để đọc đúng báo cáo ROLLUP**: nó phân biệt NULL thật trong dữ liệu với NULL do cột bị lược ở một cấp tổng. Khi xuất kết quả, nên có nhãn cấp hoặc mặt nạ GROUPING để tránh cộng đúp tổng phụ và sắp xếp báo cáo sai.

Khi cần **mọi tổ hợp chiều**, xem xét **CUBE**; khi cần **một vài tập nhóm cụ thể**, dùng **GROUPING SETS**. Khi đổi hệ quản trị, nhớ rằng cú pháp như **WITH ROLLUP** của MySQL và khả năng hỗ trợ ROLLUP của SQLite khác PostgreSQL. Cuối cùng, hãy phân biệt **chỉ tiêu cộng được** như SUM theo các nhóm giao dịch rời nhau với **chỉ tiêu không cộng đơn giản** như AVG hoặc COUNT DISTINCT.
