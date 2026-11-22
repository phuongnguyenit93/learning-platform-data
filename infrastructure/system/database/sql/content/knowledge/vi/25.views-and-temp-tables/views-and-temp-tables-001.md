# CREATE VIEW và vai trò đóng gói truy vấn

Trong một hệ thống bán hàng, trang chi tiết đơn cần biết tổng tiền theo từng dòng sản phẩm; dashboard cần doanh thu ngày; bộ phận vận hành cần xem đơn chưa hoàn thành; còn API muốn trả một dòng cho mỗi đơn. Nếu tất cả nơi này đều viết lại JOIN, GROUP BY và SUM, cùng một khái niệm “tổng tiền đơn hàng” rất dễ bị tính không nhất quán.

**VIEW** (*khung nhìn*) cho phép đặt tên cho một truy vấn đã được lưu trong cơ sở dữ liệu. Sau khi dùng **CREATE VIEW**, ứng dụng có thể SELECT từ view như từ một quan hệ, thay vì lặp lại câu SQL dài. View thường giúp **đóng gói truy vấn, tái sử dụng logic, đặt giao diện dữ liệu và kiểm soát phạm vi truy cập**.

Ví dụ ý tưởng:

~~~sql
CREATE VIEW v_order_totals AS
SELECT
    order_id,
    SUM(quantity * unit_price) AS order_total
FROM order_items
GROUP BY order_id;

SELECT order_id, order_total
FROM v_order_totals;
~~~

Trong ví dụ này, v_order_totals là tên của một định nghĩa truy vấn. **View thường không lưu các hàng kết quả thành một bản sao dữ liệu vật lý độc lập**: khi được đọc, nó phản ánh dữ liệu nguồn theo snapshot giao dịch và kế hoạch thực thi của hệ quản trị.

Bài học **“CREATE VIEW và vai trò đóng gói truy vấn”**, thuộc chương **View và bảng trung gian** của module **Database SQL**, dùng **PostgreSQL 15 trở lên** cho phần thực hành tự chứa. Phần cuối đối chiếu **MySQL, SQL Server, SQLite và Oracle Database**, đồng thời phân biệt ordinary view với **CTE, TEMP TABLE và materialized view**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích VIEW lưu **định nghĩa SELECT** chứ không mặc định lưu bảng kết quả.
2. Tạo view bằng **CREATE VIEW** hoặc **CREATE TEMP VIEW** trong PostgreSQL.
3. SELECT, JOIN, WHERE, GROUP BY và ORDER BY trên view.
4. Đóng gói công thức tổng tiền theo đúng **grain: một hàng trên mỗi order_id**.
5. Tạo một view trên view khác và hiểu phụ thuộc giữa các đối tượng.
6. Mô tả hành vi khi dữ liệu bảng nguồn thay đổi, gồm ảnh hưởng của transaction và snapshot.
7. Dùng **CREATE OR REPLACE VIEW** trong giới hạn thay đổi schema được phép.
8. Phân biệt **view tự động updatable**, view tổng hợp chỉ đọc và **WITH CHECK OPTION**.
9. Hiểu nguyên tắc phân quyền với view, **security_invoker**, RLS và các giới hạn bảo mật.
10. Không nhầm VIEW với cache; biết khi nào cân nhắc materialized view hoặc bảng tạm.
11. Đánh giá ưu/nhược điểm của VIEW so với CTE và lựa chọn cú pháp theo phương ngữ.

## 2. VIEW là gì?

Mẫu cú pháp:

~~~sql
CREATE VIEW view_name AS
SELECT column_a, column_b, ...
FROM source_table
WHERE ...;
~~~

Sau khi định nghĩa thành công:

~~~sql
SELECT column_a, column_b
FROM view_name;
~~~

Ở PostgreSQL, view là một **đối tượng schema** có tên, cột và định nghĩa truy vấn. Bộ tối ưu có thể mở rộng hoặc biến đổi truy vấn view khi tạo kế hoạch thực thi. Không nên hình dung view luôn được chạy trước thành một bảng tạm rồi SELECT bên ngoài mới chạy sau: đó chỉ là một phép diễn giải logic, không phải mô hình thực thi bắt buộc.

~~~text
        API / dashboard / báo cáo
                    |
                    v
        SELECT FROM reporting_view
                    |
                    v
         +--------------------+
         | CREATE VIEW ... AS |
         | SELECT + JOIN +    |
         | GROUP BY + CASE    |
         +--------------------+
                    |
          đánh giá theo dữ liệu nguồn
                    |
        +-----------+------------+
        |           |            |
        v           v            v
      orders     customers    order_items
~~~

Định nghĩa view có thể chứa phép nối, lọc, tổng hợp, biểu thức CASE, hàm cửa sổ hoặc CTE trong phạm vi cú pháp RDBMS hỗ trợ.

### 2.1. VIEW thường khác bảng vật lý

| Câu hỏi | Ordinary VIEW | Bảng thường |
| --- | --- | --- |
| Có tên trong database? | Có | Có |
| Có định nghĩa cột? | Có | Có |
| Có lưu độc lập các hàng kết quả của SELECT? | Không | Có |
| Dữ liệu nguồn đổi, lần đọc sau có thể thấy kết quả mới? | Có, theo snapshot | Bảng khác không tự đổi trừ khi được ghi |
| Có thể gán chỉ mục trực tiếp như bảng vật lý PostgreSQL? | Không | Có |
| Có thể SELECT/JOIN với đối tượng khác? | Có | Có |
| Có thể INSERT/UPDATE/DELETE? | Một số view đơn giản có thể, phụ thuộc hệ | Theo quyền và ràng buộc của bảng |

**Một view thường là giao diện truy vấn được lưu, không phải một bản sao kết quả được cache.** Nếu cần lưu kết quả, dùng cơ chế khác như materialized view hoặc bảng tổng hợp.

## 3. Tại sao dùng VIEW để đóng gói logic?

Giả sử công thức tổng tiền đơn hàng:

\[
\text{order\_total} = \sum_{\text{line của đơn}}
\left(\text{quantity} \times \text{unit\_price\_at\_order}\right).
\]

Ba API khác nhau có thể viết lại công thức rồi dần lệch nhau:

- API A lấy **giá trên dòng đơn**, chính xác tại thời điểm đặt hàng.
- API B lấy **giá hiện tại từ danh mục sản phẩm**, làm doanh thu lịch sử thay đổi khi chỉnh bảng giá.
- API C JOIN đơn hàng với cả dòng hàng lẫn thanh toán, khiến một dòng hàng bị nhân bản nhiều lần trước SUM.

Một view được thiết kế tốt đưa công thức và **grain** vào một nơi có tên:

~~~text
lab_v_order_overview
  - Mỗi order_id xuất hiện một lần.
  - Tổng tiền = SUM(quantity × unit_price_vnd từ dòng đơn).
  - Đơn không có dòng vẫn xuất hiện nếu chính sách muốn giữ.
  - Trạng thái đơn được giữ để báo cáo ngoài lựa chọn PAID.
~~~

Lợi ích:

1. **Tái sử dụng:** nhiều consumer dùng một công thức.
2. **Dễ đọc:** SELECT ngoài tập trung vào câu hỏi kinh doanh, không vào JOIN dài.
3. **Khả năng bảo trì:** đổi logic tính toán tập trung hơn.
4. **Hợp đồng dữ liệu:** tên, kiểu và ý nghĩa cột có thể được chuẩn hóa.
5. **Phân quyền:** có thể cấp SELECT view thay vì trao quyền rộng trên mọi bảng nguồn, với các điều kiện bảo mật cần xét riêng.

Nhưng nếu view được định nghĩa **sai**, mọi consumer cũng sẽ cùng dùng sai. Đóng gói **không thay thế** việc thiết kế khóa, grain và quy tắc nghiệp vụ.

## 4. Chuẩn bị dữ liệu thực hành

Ta dùng bốn bảng tạm PostgreSQL: khách hàng, sản phẩm, đơn hàng và chi tiết đơn. Bộ dữ liệu gồm **4 khách**, **4 sản phẩm**, **6 đơn** và **10 dòng hàng**. Các đơn thuộc hai tenant, có trạng thái PAID, DRAFT và CANCELLED.

### 4.1. Tạo bảng nguồn

~~~sql
CREATE TEMP TABLE lab_view_customers (
    customer_id   INTEGER PRIMARY KEY,
    tenant_id     INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    email         TEXT
);

CREATE TEMP TABLE lab_view_products (
    product_id     INTEGER PRIMARY KEY,
    product_name   TEXT NOT NULL,
    list_price_vnd NUMERIC(12,2) NOT NULL
        CHECK (list_price_vnd >= 0)
);

CREATE TEMP TABLE lab_view_orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lab_view_customers(customer_id),
    order_at    TIMESTAMPTZ NOT NULL,
    status      TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELLED'))
);

CREATE TEMP TABLE lab_view_order_items (
    order_id       INTEGER NOT NULL
        REFERENCES lab_view_orders(order_id),
    line_no        INTEGER NOT NULL CHECK (line_no > 0),
    product_id     INTEGER NOT NULL
        REFERENCES lab_view_products(product_id),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd NUMERIC(12,2) NOT NULL
        CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Phân biệt **list_price_vnd** là giá tham khảo hiện tại, còn **unit_price_vnd ở dòng đơn** là giá đã ghi nhận tại lúc giao dịch. Với báo cáo giá trị đơn, phần sau cố ý dùng cột giá tại dòng đơn.

### 4.2. Thêm dữ liệu

~~~sql
INSERT INTO lab_view_customers
    (customer_id, tenant_id, customer_name, email)
VALUES
    (1, 10, 'An',   'an@example.test'),
    (2, 10, 'Binh', 'binh@example.test'),
    (3, 20, 'Chi',  'chi@example.test'),
    (4, 20, 'Dung', 'dung@example.test');

INSERT INTO lab_view_products
    (product_id, product_name, list_price_vnd)
VALUES
    (101, 'So tay', 40000),
    (102, 'But bi', 10000),
    (103, 'Chuot', 250000),
    (104, 'USB', 90000);

INSERT INTO lab_view_orders
    (order_id, customer_id, order_at, status)
VALUES
    (1001, 1, '2026-10-01 09:00:00+00', 'PAID'),
    (1002, 1, '2026-10-02 10:00:00+00', 'PAID'),
    (1003, 2, '2026-10-02 11:00:00+00', 'DRAFT'),
    (1004, 3, '2026-10-03 08:00:00+00', 'PAID'),
    (1005, 4, '2026-10-04 12:00:00+00', 'CANCELLED'),
    (1006, 2, '2026-10-05 14:00:00+00', 'PAID');

INSERT INTO lab_view_order_items
    (order_id, line_no, product_id, quantity, unit_price_vnd)
VALUES
    (1001, 1, 101, 2, 40000),
    (1001, 2, 102, 3, 10000),
    (1002, 1, 103, 1, 250000),
    (1002, 2, 104, 1, 90000),
    (1004, 1, 104, 2, 90000),
    (1004, 2, 102, 2, 10000),
    (1005, 1, 101, 1, 40000),
    (1006, 1, 101, 1, 40000),
    (1006, 2, 102, 1, 10000),
    (1006, 3, 104, 1, 90000);
~~~

Đơn **1003** không có dòng hàng để kiểm tra LEFT JOIN; đơn **1005** đã bị hủy; đơn **1001** có hai dòng với tổng 110.000 VND. Dữ liệu sử dụng dấu +00 để xác định thời điểm theo UTC.

Kiểm tra số hàng:

~~~sql
SELECT
    (SELECT COUNT(*) FROM lab_view_customers) AS customers,
    (SELECT COUNT(*) FROM lab_view_products) AS products,
    (SELECT COUNT(*) FROM lab_view_orders) AS orders,
    (SELECT COUNT(*) FROM lab_view_order_items) AS order_lines;
~~~

| customers | products | orders | order_lines |
| ---: | ---: | ---: | ---: |
| 4 | 4 | 6 | 10 |

> Bảng TEMP chỉ tồn tại trong phiên PostgreSQL hiện tại. Chạy lại CREATE TEMP TABLE trong cùng phiên khi bảng đã tồn tại có thể báo lỗi; mở phiên mới hoặc chỉ dọn những bảng của bài trước khi thực hiện lại.

## 5. Từ SELECT dài thành CREATE VIEW

Mục tiêu: tạo view tên **lab_v_order_overview** có đúng **một hàng cho mỗi order_id**, gồm tenant, khách hàng, thời gian, trạng thái, số dòng hàng, tổng số lượng và tổng tiền.

### 5.1. Tính trước chi tiết ở grain đơn hàng

~~~sql
SELECT
    order_id,
    COUNT(*) AS line_count,
    SUM(quantity) AS unit_count,
    SUM(quantity * unit_price_vnd) AS order_total_vnd
FROM lab_view_order_items
GROUP BY order_id
ORDER BY order_id;
~~~

Kết quả này gồm một hàng/order_id **chỉ cho các đơn có chi tiết**. Đơn 1003 chưa có chi tiết nên không có ở bước này.

### 5.2. Đóng gói toàn bộ truy vấn vào view

~~~sql
CREATE TEMP VIEW lab_v_order_overview AS
SELECT
    o.order_id,
    c.tenant_id,
    o.customer_id,
    c.customer_name,
    o.order_at,
    o.status,
    COALESCE(i.line_count, 0::BIGINT) AS line_count,
    COALESCE(i.unit_count, 0::BIGINT) AS unit_count,
    COALESCE(i.order_total_vnd, 0::NUMERIC) AS order_total_vnd
FROM lab_view_orders AS o
JOIN lab_view_customers AS c
    ON c.customer_id = o.customer_id
LEFT JOIN (
    SELECT
        order_id,
        COUNT(*) AS line_count,
        SUM(quantity) AS unit_count,
        SUM(quantity * unit_price_vnd) AS order_total_vnd
    FROM lab_view_order_items
    GROUP BY order_id
) AS i
    ON i.order_id = o.order_id;
~~~

Từng phần:

1. **orders** là bảng gốc: mỗi đơn được biểu diễn đúng một lần.
2. **JOIN customers** bổ sung tên và tenant; dữ liệu mẫu có FK customer_id hợp lệ và NOT NULL.
3. Tập **i** đã GROUP BY order_id, nên không nhân dòng khi nối vào orders.
4. **LEFT JOIN** giữ đơn 1003 chưa có dòng hàng.
5. **COALESCE** diễn đạt quy ước của bài: đơn chưa có chi tiết có count và tổng tiền bằng 0.

**CREATE TEMP VIEW** tạo view sống trong phiên. Vì view tham chiếu bảng TEMP, nó không phải một view permanent dùng giữa nhiều connection. Đối với view phục vụ ứng dụng thật, cần bảng nguồn và view ở schema permanent thích hợp.

### 5.3. Đọc view

~~~sql
SELECT
    order_id,
    customer_name,
    status,
    line_count,
    unit_count,
    order_total_vnd
FROM lab_v_order_overview
ORDER BY order_id;
~~~

| order_id | customer_name | status | line_count | unit_count | order_total_vnd |
| ---: | --- | --- | ---: | ---: | ---: |
| 1001 | An | PAID | 2 | 5 | 110000 |
| 1002 | An | PAID | 2 | 2 | 340000 |
| 1003 | Binh | DRAFT | 0 | 0 | 0 |
| 1004 | Chi | PAID | 2 | 4 | 200000 |
| 1005 | Dung | CANCELLED | 1 | 1 | 40000 |
| 1006 | Binh | PAID | 3 | 3 | 140000 |

Ta có **6 hàng kết quả**, đúng số đơn. Đơn 1005 vẫn có tổng giá trị dòng hàng 40.000 nhưng **không phải doanh thu đã thanh toán**, vì trạng thái là CANCELLED.

### 5.4. Phân biệt line_count và unit_count

Đơn 1001 có:

~~~text
line 1: 2 So tay
line 2: 3 But bi
~~~

Vì vậy **line_count = 2**, còn **unit_count = 5**. Tên cột view cần đủ rõ để các báo cáo bên ngoài không lấy nhầm số dòng làm số lượng sản phẩm.

## 6. Truy vấn VIEW như một bảng đọc

Sau khi view tồn tại, API chỉ cần:

~~~sql
SELECT order_id, customer_name, order_total_vnd
FROM lab_v_order_overview
WHERE status = 'PAID'
ORDER BY order_id;
~~~

Để tính doanh thu đã thanh toán:

~~~sql
SELECT
    COUNT(*) AS paid_order_count,
    SUM(order_total_vnd) AS paid_revenue_vnd
FROM lab_v_order_overview
WHERE status = 'PAID';
~~~

Kết quả là **4 đơn và 790.000 VND**:

~~~text
1001: 110.000
1002: 340.000
1004: 200.000
1006: 140.000
----------------
Tổng: 790.000 VND
~~~

Theo tenant:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(order_total_vnd) AS paid_revenue_vnd
FROM lab_v_order_overview
WHERE status = 'PAID'
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

| tenant_id | paid_orders | paid_revenue_vnd |
| ---: | ---: | ---: |
| 10 | 3 | 590000 |
| 20 | 1 | 200000 |

**Không coi lab_v_order_overview tự động cô lập dữ liệu theo tenant**. Đây chỉ là view có cột tenant_id; người dùng được phép SELECT tất cả hàng của view thì có thể xem cả hai tenant, trừ khi có một cơ chế bảo mật khác giới hạn.

## 7. VIEW có thể dựa trên VIEW khác

Ta muốn đóng gói doanh thu PAID theo **tenant và ngày UTC**. Thay vì viết lại SUM từ order_items, ta sử dụng view vừa tạo:

~~~sql
CREATE TEMP VIEW lab_v_paid_sales_by_day AS
SELECT
    tenant_id,
    (order_at AT TIME ZONE 'UTC')::DATE AS sale_date_utc,
    COUNT(*) AS paid_order_count,
    SUM(order_total_vnd) AS gross_sales_vnd
FROM lab_v_order_overview
WHERE status = 'PAID'
GROUP BY
    tenant_id,
    (order_at AT TIME ZONE 'UTC')::DATE;
~~~

Đọc:

~~~sql
SELECT tenant_id, sale_date_utc, paid_order_count, gross_sales_vnd
FROM lab_v_paid_sales_by_day
ORDER BY tenant_id, sale_date_utc;
~~~

| tenant_id | sale_date_utc | paid_order_count | gross_sales_vnd |
| ---: | --- | ---: | ---: |
| 10 | 2026-10-01 | 1 | 110000 |
| 10 | 2026-10-02 | 1 | 340000 |
| 10 | 2026-10-05 | 1 | 140000 |
| 20 | 2026-10-03 | 1 | 200000 |

Hai view có trách nhiệm riêng:

- **lab_v_order_overview:** một dòng mỗi đơn, bao gồm tổng tiền theo dòng hàng.
- **lab_v_paid_sales_by_day:** một dòng mỗi cặp (tenant_id, sale_date_utc), chỉ tính đơn PAID.

### 7.1. Vì sao đặt tên sale_date_utc?

**TIMESTAMPTZ** là thời điểm thực; việc chuyển sang DATE phụ thuộc múi giờ được chọn. Biểu thức:

~~~sql
(order_at AT TIME ZONE 'UTC')::DATE
~~~

xác định rõ ngày báo cáo theo UTC. Nếu báo cáo cần ngày theo Việt Nam, phải dùng một quy tắc khác:

~~~sql
(order_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
~~~

Hai cách có thể chia các đơn gần nửa đêm vào các ngày khác nhau. View đóng gói quy tắc ấy, nên **tên cột phải truyền đạt múi giờ đã chọn**.

### 7.2. Phụ thuộc giữa các view

~~~text
lab_view_customers ──┐
lab_view_orders ─────┼──► lab_v_order_overview
lab_view_order_items ┘             |
                                  v
                      lab_v_paid_sales_by_day
                                  |
                                  v
                              Dashboard
~~~

Lợi ích là tái sử dụng, nhưng đổi định nghĩa hoặc tên cột của view dưới có thể ảnh hưởng view trên. Tạo quá nhiều tầng view có thể làm việc truy vết logic và hiểu kế hoạch thực thi phức tạp.

## 8. Khi bảng gốc đổi, view thường có đổi theo không?

**Có thể thấy dữ liệu mới khi SELECT lại** theo ngữ nghĩa snapshot của transaction. View thường không có thao tác REFRESH riêng.

Thí nghiệm:

~~~sql
BEGIN;

INSERT INTO lab_view_order_items
    (order_id, line_no, product_id, quantity, unit_price_vnd)
VALUES
    (1001, 3, 104, 1, 90000);

SELECT order_id, line_count, unit_count, order_total_vnd
FROM lab_v_order_overview
WHERE order_id = 1001;

ROLLBACK;
~~~

Trong transaction, tổng đơn 1001 là **200.000**, line_count = 3, unit_count = 6. Sau ROLLBACK:

~~~sql
SELECT order_id, order_total_vnd
FROM lab_v_order_overview
WHERE order_id = 1001;
~~~

Kết quả lại là **110.000**. Ta không gọi CREATE VIEW lần nữa; định nghĩa vẫn nguyên, chỉ có dữ liệu nguồn mà SELECT nhìn thấy đã thay đổi.

### 8.1. View không tự tạo một snapshot cố định cho cả báo cáo

Ở PostgreSQL, READ COMMITTED thường dùng snapshot theo câu lệnh; các isolation level khác có quy tắc riêng. Hai SELECT tại hai thời điểm có thể nhìn thấy dữ liệu khác nhau nếu transaction khác đã COMMIT thay đổi.

Khi cần nhiều truy vấn báo cáo nhìn cùng một ảnh chụp, phải xét **transaction boundary và mức cô lập**, không giả định dùng chung VIEW là đủ.

## 9. VIEW thường không phải cache

Một ngộ nhận phổ biến:

~~~text
CREATE VIEW v_big_report AS SELECT ... JOIN ... GROUP BY ...;
~~~

sẽ lưu sẵn mọi hàng kết quả và lần đọc sau chắc chắn nhanh. Với ordinary view, điều này **không đúng**.

Hệ quản trị có thể mở rộng định nghĩa view, chọn cách join/aggregate, đẩy điều kiện lọc xuống bảng nguồn khi an toàn và sử dụng chỉ mục của bảng. Nhưng cũng có thể phải tính lại phép JOIN hoặc GROUP BY khi có SELECT mới.

**Tái sử dụng logic** không đồng nghĩa **tái sử dụng kết quả tính toán**.

| Đối tượng | Lưu định nghĩa truy vấn | Lưu kết quả thành hàng vật lý | Dữ liệu mới có tự phản ánh? |
| --- | --- | --- | --- |
| Ordinary VIEW | Có | Không | Theo bảng nguồn và snapshot |
| MATERIALIZED VIEW | Có | Có | Không, cần refresh/cơ chế làm mới |
| TEMP TABLE tạo từ SELECT | Không lưu truy vấn như một view | Có | Không tự động |
| CTE trong WITH | Chỉ định nghĩa trong một câu SQL | Tùy kế hoạch thực thi | Không là đối tượng lâu dài |

Một hệ quản trị có thể cache kế hoạch truy vấn hoặc những trang dữ liệu theo cơ chế riêng, nhưng đó **không phải** lời hứa rằng CREATE VIEW cache kết quả SELECT.

## 10. Thiết kế hợp đồng dữ liệu cho VIEW

Khi nhiều API hoặc báo cáo dựa vào một view, cần mô tả nó như một **hợp đồng dữ liệu (data contract)**.

Ví dụ cho lab_v_order_overview:

| Thuộc tính | Hợp đồng |
| --- | --- |
| Grain | Mỗi order_id đúng một hàng |
| Khóa logic | order_id |
| Nguồn | orders, customers, order_items |
| Tổng tiền | SUM(quantity * unit_price_vnd) của chi tiết đơn |
| Đơn không có chi tiết | line_count, unit_count, order_total_vnd bằng 0 |
| Status | Giữ DRAFT/PAID/CANCELLED từ orders |
| tenant_id | Lấy từ khách của đơn |
| order_at | TIMESTAMPTZ; view chưa gán ngày địa phương |
| Vai trò | Giao diện đọc tổng quan đơn |

Đối với lab_v_paid_sales_by_day, grain là **(tenant_id, sale_date_utc)**, và chỉ những đơn status = PAID mới được tính.

### 10.1. Đặt tên rõ đơn vị đo

Tên **order_total_vnd** nói rõ đơn vị VND. Tên **unit_count** giúp phân biệt với **line_count**. Tên **sale_date_utc** cho biết ngày theo UTC. Không nên đặt tên quá chung như **total** hoặc **date** khi có nhiều cách hiểu.

### 10.2. Cẩn thận với SELECT *

Khi tạo view làm giao diện ổn định:

~~~sql
CREATE TEMP VIEW lab_v_customer_public AS
SELECT
    customer_id,
    tenant_id,
    customer_name
FROM lab_view_customers;
~~~

Ta cố ý **không đưa email** vào view public. Liệt kê cột tường minh giúp dễ review bảo mật và tương thích.

Trong PostgreSQL, SELECT * trong định nghĩa CREATE VIEW được mở rộng tại thời điểm tạo, nên thêm cột vào bảng gốc **không nhất thiết tự xuất hiện** trong view cũ. Nhưng SELECT * vẫn làm hợp đồng cột khó nhận biết và có thể đưa các cột không mong muốn vào thời điểm tạo hoặc thay view.

## 11. CREATE OR REPLACE VIEW

PostgreSQL hỗ trợ sửa định nghĩa view mà vẫn giữ tên:

~~~sql
CREATE OR REPLACE VIEW view_name AS
SELECT ...;
~~~

Với view tạm đã tạo:

~~~sql
CREATE OR REPLACE TEMP VIEW lab_v_customer_public AS
SELECT
    customer_id,
    tenant_id,
    customer_name,
    UPPER(customer_name) AS customer_name_upper
FROM lab_view_customers;
~~~

Ở đây ba cột cũ được giữ nguyên **tên, thứ tự, kiểu**, và cột mới được **thêm ở cuối**.

### 11.1. Giới hạn thay đổi cột của PostgreSQL

Đối với PostgreSQL, CREATE OR REPLACE VIEW không cho tùy ý đổi tên/kiểu/thứ tự hoặc bỏ các cột đã công bố. Danh sách cột cũ phải giữ nguyên, nhưng có thể **thêm cột ở cuối**. Khi cần đổi tên cột, có thể dùng cơ chế **ALTER VIEW ... RENAME COLUMN**; khi thay đổi kiểu hoặc xóa cột cần một migration xử lý phụ thuộc.

Đừng coi CREATE OR REPLACE là cách tránh mọi thay đổi phá vỡ hợp đồng schema.

### 11.2. Thay đổi logic nhưng giữ kiểu cũng có rủi ro

Nếu order_total_vnd trước đây tính giá trị **trước chiết khấu**, nhưng sau này sửa view thành **sau chiết khấu** mà không đổi tên, API vẫn chạy được nhưng ý nghĩa số đã thay đổi.

Khi sửa logic view dùng chung cần quản lý:

- Công thức cũ và mới.
- Những báo cáo, API, view khác phụ thuộc.
- Quy tắc về phiên bản, ngày áp dụng.
- Kiểm chứng kết quả tại bước kiểm thử triển khai phù hợp.

## 12. Phụ thuộc schema và DROP VIEW

View có thể phụ thuộc vào bảng nguồn và view khác:

~~~text
lab_v_order_overview
       |
       v
lab_v_paid_sales_by_day
~~~

Nếu gửi:

~~~sql
DROP VIEW lab_v_order_overview;
~~~

PostgreSQL có thể **từ chối** vì lab_v_paid_sales_by_day vẫn phụ thuộc vào view này. Có cú pháp **DROP VIEW ... CASCADE**, nhưng có thể xóa cả các đối tượng phụ thuộc:

~~~sql
-- Cảnh báo: không chạy tùy tiện.
-- DROP VIEW lab_v_order_overview CASCADE;
~~~

**Không dùng CASCADE chỉ để câu migration chạy được**. Hãy xem những đối tượng phụ thuộc và có phương án chuyển đổi.

### 12.1. Giữ phiên bản view khi thay đổi contract lớn

Một cách triển khai:

~~~text
reporting.v_order_overview_v1
reporting.v_order_overview_v2
~~~

Consumer mới chuyển sang v2; consumer cũ có thời gian chuyển đổi; sau đó mới xóa v1. Việc version theo tên không bắt buộc trong mọi dự án nhưng hữu ích khi thay đổi phá vỡ schema hoặc ý nghĩa dữ liệu.

### 12.2. View là code được triển khai

Định nghĩa CREATE VIEW nên nằm trong **migration hoặc repository**, không chỉ tồn tại dưới dạng một lệnh gõ tay trong database production. Ngoài SQL, có thể lưu mô tả grain, người sở hữu, quyền truy cập, mức dữ liệu nhạy cảm và quy tắc thay đổi.

## 13. Xem định nghĩa VIEW trong PostgreSQL

Tra catalog:

~~~sql
SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE viewname IN (
    'lab_v_order_overview',
    'lab_v_paid_sales_by_day'
)
ORDER BY schemaname, viewname;
~~~

Hoặc:

~~~sql
SELECT
    pg_get_viewdef('lab_v_order_overview'::REGCLASS, TRUE)
        AS view_definition;
~~~

SQL được trả về có thể được PostgreSQL chuẩn hóa khác đoạn tạo ban đầu (dấu ngoặc, alias, định dạng). Catalog cho biết định nghĩa thực tế; file migration giúp quản lý lịch sử thay đổi.

Xem cột:

~~~sql
SELECT
    column_name,
    data_type,
    ordinal_position
FROM information_schema.columns
WHERE table_name = 'lab_v_order_overview'
ORDER BY ordinal_position;
~~~

Với đối tượng TEMP, schema thực tế có thể mang tên **pg_temp_N**; trong môi trường nhiều schema hoặc nhiều view trùng tên, lọc thêm schema đúng để không tra nhầm.

## 14. JOIN giữa VIEW và bảng khác

View có thể tham gia JOIN như một quan hệ:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(v.order_id) AS paid_order_count,
    COALESCE(SUM(v.order_total_vnd), 0::NUMERIC) AS paid_amount_vnd
FROM lab_view_customers AS c
LEFT JOIN lab_v_order_overview AS v
    ON v.customer_id = c.customer_id
   AND v.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

| customer_id | customer_name | paid_order_count | paid_amount_vnd |
| ---: | --- | ---: | ---: |
| 1 | An | 2 | 450000 |
| 2 | Binh | 1 | 140000 |
| 3 | Chi | 1 | 200000 |
| 4 | Dung | 0 | 0 |

Khách **Dung** chỉ có đơn CANCELLED, nhưng vẫn xuất hiện với 0 đơn PAID vì điều kiện v.status = 'PAID' nằm trong **ON của LEFT JOIN**.

Nếu đặt:

~~~sql
WHERE v.status = 'PAID'
~~~

ở SELECT cuối, các hàng không khớp sẽ bị lọc bỏ theo ngữ nghĩa SQL. **VIEW không làm thay đổi quy tắc JOIN, WHERE và NULL**; người dùng view vẫn phải hiểu SQL cơ bản.

## 15. Bẫy fanout: JOIN nhiều quan hệ một-nhiều

Giả sử một đơn có hai dòng hàng và hai lần thanh toán:

~~~text
orders(1001)
  ├── order_items: 2 dòng
  └── payments:    2 dòng
~~~

Nếu JOIN orders với order_items rồi JOIN tiếp payments theo order_id, tập trung gian có thể có **2 × 2 = 4 hàng**:

~~~text
item 1 + payment 1
item 1 + payment 2
item 2 + payment 1
item 2 + payment 2
~~~

Khi SUM(quantity * unit_price_vnd) trên kết quả JOIN, mỗi dòng hàng được cộng hai lần, tạo sai tổng tiền.

**Giải pháp:** tính từng nhánh trước về một hàng trên order_id:

~~~text
order_items ── GROUP BY order_id ──► item_totals
payments    ── GROUP BY order_id ──► payment_totals

orders LEFT JOIN item_totals
       LEFT JOIN payment_totals
       → vẫn một hàng cho mỗi order_id
~~~

lab_v_order_overview đã tổng hợp dòng hàng trước khi JOIN. Nếu bổ sung thông tin thanh toán, phải kiểm tra **grain của từng nguồn** thay vì nối trực tiếp tùy ý.

**Một view có tên chuẩn không bảo đảm phép JOIN bên trong đúng.** Grain và khả năng nhân hàng là thuộc tính quan trọng phải được thiết kế/ghi chú.

## 16. VIEW và quyền truy cập

Một vai trò báo cáo có thể chỉ cần order_id, ngày và tổng tiền, nhưng không cần email, địa chỉ hay các trường nhạy cảm trong bảng nguồn.

Trong một schema production giả định:

~~~text
core.customers
core.orders
core.order_items
reporting.v_paid_orders
~~~

Ta có thể cấp quyền đọc vào view đã chuẩn bị:

~~~sql
-- Mẫu cho schema/role đã tồn tại; không chạy trên bảng TEMP của bài.
GRANT USAGE ON SCHEMA reporting TO report_reader;
GRANT SELECT ON reporting.v_paid_orders TO report_reader;
~~~

Việc này hỗ trợ **nguyên tắc quyền tối thiểu**, nhưng cần hiểu cách RDBMS kiểm tra quyền trên bảng nền.

### 16.1. View không tự trở thành ranh giới bảo mật hoàn chỉnh

Trước khi dùng view để giới hạn dữ liệu, phải kiểm tra:

1. Ai được SELECT view?
2. Ai được đọc bảng nguồn trực tiếp?
3. Quyền nguồn được xét theo **view owner** hay **caller**?
4. Có RLS theo hàng/tenant không?
5. View có vô tình đưa ra các cột nhạy cảm không?
6. Có đường truy cập khác từ ứng dụng hoặc quyền schema rộng không?

Một view có WHERE tenant_id = 10 chỉ giới hạn theo tenant 10 cố định. Nó không tự xác định tenant của mỗi người gọi và càng không thay thế chính sách quyền được thiết kế đầy đủ.

## 17. PostgreSQL security_invoker và RLS

PostgreSQL 15+ hỗ trợ tùy chọn:

~~~sql
-- Ví dụ với schema permanent core/reporting giả định.
CREATE VIEW reporting.v_orders_invoker
WITH (security_invoker = true) AS
SELECT
    order_id,
    customer_id,
    order_at,
    status
FROM core.orders;
~~~

Khi **security_invoker = true**, quyền truy cập bảng nền được xét theo người đang truy vấn view. Theo hành vi thông thường khi không bật, việc kiểm tra quyền trên quan hệ nền dựa trên **owner của view**.

Sự khác biệt này quan trọng với RLS:

- RLS policy nào áp dụng phụ thuộc vai trò thực tế được sử dụng để đọc bảng nền.
- View owner có thể có quyền hoặc thuộc trường hợp được miễn/bypass RLS theo quy tắc PostgreSQL.
- security_invoker yêu cầu người gọi có quyền phù hợp trên những bảng nền, không tự biến một người thiếu quyền nguồn thành người có quyền.
- Ngay cả khi view chỉ cho một số cột, người gọi có quyền đọc rộng trên bảng nguồn vẫn có thể đọc qua đường khác.

**Không nên chỉ thử SELECT dưới tài khoản administrator rồi kết luận view an toàn cho mọi role.** Kiểm tra bằng vai trò ứng dụng và chính sách RLS thực tế.

### 17.1. security_barrier

PostgreSQL cũng có:

~~~sql
-- Ví dụ ý tưởng, bảng reporting.order_fact chưa được tạo trong bài.
CREATE VIEW reporting.v_visible_orders
WITH (security_barrier = true) AS
SELECT order_id, tenant_id, order_total_vnd
FROM reporting.order_fact
WHERE is_visible IS TRUE;
~~~

**security_barrier** liên quan cách giới hạn một số phép đẩy điều kiện có thể gây lộ thông tin trong trường hợp view được dùng như một lớp lọc bảo mật. Tùy chọn này **không thay thế GRANT/RLS** và có thể ảnh hưởng tối ưu hóa kế hoạch. Không bật hoặc tắt chỉ vì tên gọi mà chưa hiểu chính sách bảo mật và chi phí truy vấn.

## 18. VIEW có thể UPDATE không?

Khả năng ghi qua view **khác nhau theo định nghĩa view và hệ quản trị**.

### 18.1. View tổng hợp không tự biết phải sửa dòng nào

lab_v_order_overview JOIN nhiều bảng và dùng GROUP BY. Nếu muốn sửa:

~~~sql
-- Không dùng làm ví dụ UPDATE hợp lệ:
UPDATE lab_v_order_overview
SET order_total_vnd = 500000
WHERE order_id = 1001;
~~~

PostgreSQL không thể tự suy luận phải sửa quantity hay unit_price của dòng hàng nào để đạt tổng 500000. Loại view này chủ yếu là **giao diện đọc**.

### 18.2. Simple view của PostgreSQL có thể updatable

~~~sql
CREATE TEMP VIEW lab_v_customer_names AS
SELECT
    customer_id,
    tenant_id,
    customer_name
FROM lab_view_customers;
~~~

Đây là view SELECT cột trực tiếp từ **một bảng**, không JOIN hoặc aggregate. Thử:

~~~sql
BEGIN;

UPDATE lab_v_customer_names
SET customer_name = 'An Nguyen'
WHERE customer_id = 1;

SELECT customer_id, customer_name
FROM lab_view_customers
WHERE customer_id = 1;

ROLLBACK;
~~~

Trong transaction, bảng nguồn có tên mới, sau ROLLBACK trả về tên cũ. PostgreSQL có các quy tắc cụ thể cho **automatically updatable views**: một SELECT đơn giản từ một quan hệ, không có những cấu trúc như GROUP BY, DISTINCT, aggregate hoặc set operations ở những vị trí hạn chế.

**Không phải mọi view đều chỉ đọc.** Nếu mục tiêu là báo cáo, chỉ GRANT SELECT thay vì cấp quyền ghi ngoài ý muốn.

### 18.3. Ràng buộc bảng nguồn vẫn có hiệu lực

INSERT/UPDATE qua view được phép vẫn phải thỏa PRIMARY KEY, CHECK, FK và NOT NULL của bảng nền. View không mở lối đi tắt để ghi dữ liệu vi phạm ràng buộc.

## 19. WITH CHECK OPTION

Giả sử ta muốn một view chỉ hiển thị khách tenant 10 và không cho UPDATE/INSERT qua view khiến hàng **không còn thỏa điều kiện**.

~~~sql
CREATE TEMP VIEW lab_v_tenant10_customers AS
SELECT
    customer_id,
    tenant_id,
    customer_name
FROM lab_view_customers
WHERE tenant_id = 10
WITH LOCAL CHECK OPTION;
~~~

Thử INSERT hợp lệ:

~~~sql
BEGIN;

INSERT INTO lab_v_tenant10_customers
    (customer_id, tenant_id, customer_name)
VALUES (9, 10, 'Khach thu');

SELECT customer_id, tenant_id, customer_name
FROM lab_view_customers
WHERE customer_id = 9;

ROLLBACK;
~~~

Hàng tenant 10 thỏa điều kiện view. Nhưng:

~~~sql
-- Cố ý gây lỗi; không chạy cùng một script ghi thật.
INSERT INTO lab_v_tenant10_customers
    (customer_id, tenant_id, customer_name)
VALUES (10, 20, 'Khach sai tenant');
~~~

sẽ bị chặn theo CHECK OPTION do tenant_id = 20 không thuộc tập hàng của view.

**LOCAL** và **CASCADED CHECK OPTION** khác nhau về phạm vi kiểm tra khi có view xếp tầng, theo quy tắc PostgreSQL và những giới hạn như INSTEAD OF triggers/rules. CHECK OPTION không thay thế **RLS**, vì một người có quyền ghi trực tiếp bảng nền có thể không đi qua view này.

Nếu chạy câu cố ý lỗi trong transaction PostgreSQL tường minh, cần ROLLBACK hoặc ROLLBACK TO SAVEPOINT hợp lệ trước khi tiếp tục.

## 20. VIEW nên được dùng để đọc hay ghi?

Một ranh giới dễ kiểm soát:

~~~text
Reporting views    → SELECT và tổng hợp đã được định nghĩa
Service nghiệp vụ → INSERT/UPDATE/DELETE trong transaction rõ ràng
Base tables        → PRIMARY KEY/FK/CHECK/UNIQUE bảo vệ dữ liệu
~~~

Nếu sửa đơn đã thanh toán, nghiệp vụ có thể cần kiểm tra trạng thái, tính tồn kho, chiết khấu, ghi audit và phát sự kiện. Một UPDATE trực tiếp cột tính toán của view không mô tả đầy đủ những yêu cầu đó.

Một số RDBMS hỗ trợ **INSTEAD OF triggers** hoặc các cơ chế khác để định nghĩa thao tác ghi qua view phức tạp. Đây là thiết kế nâng cao, không phải hành vi mặc định của CREATE VIEW.

## 21. Hiệu năng: WHERE và chỉ mục trên bảng nguồn

Một truy vấn:

~~~sql
SELECT order_id, order_total_vnd
FROM lab_v_order_overview
WHERE order_id = 1001;
~~~

không nhất thiết phải tính toàn bộ mọi đơn rồi mới lọc. PostgreSQL có thể mở rộng định nghĩa view và **đẩy điều kiện lọc vào bảng nguồn** khi ngữ nghĩa cho phép.

Tuy nhiên, những thành phần như GROUP BY, DISTINCT, LIMIT, hàm cửa sổ hoặc security_barrier có thể ảnh hưởng phạm vi tối ưu hóa. View nhiều tầng cũng có thể khiến việc điều tra kế hoạch khó hơn.

### 21.1. EXPLAIN

~~~sql
EXPLAIN
SELECT order_id, order_total_vnd
FROM lab_v_order_overview
WHERE tenant_id = 10
  AND status = 'PAID';
~~~

Kế hoạch có thể cho thấy scan, JOIN, aggregate và các cách truy cập bảng nguồn; không nhất thiết tồn tại một bước “đọc hàng vật lý của view thường”.

Để đo số liệu chạy thật:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM lab_v_order_overview
WHERE status = 'PAID';
~~~

EXPLAIN ANALYZE **thực thi** truy vấn. Nếu dùng với INSERT/UPDATE/DELETE có thể gây thay đổi dữ liệu, cần môi trường kiểm soát và transaction phù hợp.

### 21.2. Chỉ mục nên đặt ở đâu?

Với view thường, có thể tạo chỉ mục trên bảng nguồn:

~~~sql
CREATE INDEX idx_lab_view_orders_status_time
ON lab_view_orders(status, order_at);
~~~

PRIMARY KEY(order_id, line_no) của lab_view_order_items đã tạo chỉ mục theo thứ tự khóa bắt đầu từ order_id. Trước khi thêm index riêng trên order_id, nên kiểm tra index hiện có có đủ hay không để tránh trùng lặp và tăng chi phí ghi.

Ở bộ dữ liệu chỉ vài hàng, PostgreSQL có thể dùng Seq Scan vì rẻ hơn Index Scan; tạo index không bảo đảm sẽ dùng.

## 22. MATERIALIZED VIEW: khi cần lưu kết quả

**Materialized view** là đối tượng lưu kết quả truy vấn vật lý. Trên PostgreSQL, nó phù hợp hơn khi báo cáo cần đọc lặp lại kết quả GROUP BY rất lớn mà độ trễ cập nhật được chấp nhận.

Ví dụ thiết kế trên schema permanent **giả định**:

~~~sql
-- Ví dụ kiến trúc, yêu cầu reporting.v_paid_sales_by_day tồn tại.
CREATE MATERIALIZED VIEW reporting.mv_daily_revenue AS
SELECT
    tenant_id,
    sale_date_utc,
    SUM(gross_sales_vnd) AS total_revenue_vnd
FROM reporting.v_paid_sales_by_day
GROUP BY tenant_id, sale_date_utc
WITH NO DATA;
~~~

**WITH NO DATA** tạo materialized view chưa được nạp kết quả. PostgreSQL yêu cầu làm mới để materialized view có dữ liệu trước khi truy vấn thông thường:

~~~sql
REFRESH MATERIALIZED VIEW reporting.mv_daily_revenue;
~~~

**Không chạy các câu này trên bộ TEMP ở phần 4** vì schema reporting và view permanent tương ứng chưa được tạo. Mục đích là minh họa hình thức khác với CREATE VIEW.

| Tiêu chí | Ordinary VIEW | MATERIALIZED VIEW |
| --- | --- | --- |
| Lưu truy vấn | Có | Có |
| Lưu kết quả vật lý | Không | Có |
| Tự phản ánh dữ liệu nguồn mới ở lần SELECT kế tiếp | Có, theo snapshot | Không; phụ thuộc refresh |
| Có thể tạo index trên kết quả | Không theo cơ chế ordinary view | Có |
| Chi phí mỗi lần SELECT | Có thể phải tính lại | Có thể thấp hơn do đã lưu |
| Rủi ro | Đọc chậm khi logic nặng | Đọc dữ liệu cũ giữa các lần refresh |

PostgreSQL có **REFRESH MATERIALIZED VIEW CONCURRENTLY** với những điều kiện, nổi bật là yêu cầu unique index phù hợp và trạng thái dữ liệu đã được nạp. Nó không phải công tắc có thể dùng cho mọi materialized view mà không kiểm tra điều kiện.

## 23. VIEW so với CTE

CTE đặt tên cho một bước trong **một câu SQL**:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price_vnd) AS amount_vnd
    FROM lab_view_order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(t.amount_vnd, 0::NUMERIC) AS amount_vnd
FROM lab_view_orders AS o
LEFT JOIN item_totals AS t
    ON t.order_id = o.order_id
ORDER BY o.order_id;
~~~

CTE giúp chia truy vấn phức tạp thành các bước có tên, nhưng định nghĩa ấy thường chỉ tồn tại trong phạm vi câu SQL đang viết.

VIEW hữu ích khi nhiều câu SQL, API hoặc báo cáo cần dùng chung công thức và quyền truy cập. CTE hữu ích khi cần tổ chức một truy vấn cụ thể mà không tạo thêm đối tượng schema.

**CTE không mặc định là bảng tạm được materialize trong mọi phiên bản/hệ quản trị.** Bộ tối ưu có thể xử lý tùy kế hoạch và ngữ nghĩa của RDBMS.

### 23.1. Có thể phối hợp CTE với VIEW

Một CREATE VIEW có thể chứa CTE:

~~~sql
CREATE TEMP VIEW lab_v_order_totals_via_cte AS
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price_vnd) AS total_vnd
    FROM lab_view_order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.total_vnd, 0::NUMERIC) AS total_vnd
FROM lab_view_orders AS o
LEFT JOIN item_totals AS i
    ON i.order_id = o.order_id;
~~~

Ở đây CTE tổ chức logic **bên trong định nghĩa view**, còn view cho phép tái sử dụng truy vấn kết quả ở nhiều câu SELECT.

## 24. VIEW so với TEMP TABLE và bảng trung gian

Tạo bảng snapshot từ SELECT:

~~~sql
CREATE TEMP TABLE lab_paid_snapshot AS
SELECT order_id, order_total_vnd
FROM lab_v_order_overview
WHERE status = 'PAID';
~~~

**lab_paid_snapshot** chứa bốn hàng được chụp tại thời điểm tạo. Nếu dữ liệu đơn hàng thay đổi về sau:

- SELECT từ **lab_v_order_overview** có thể phản ánh thay đổi.
- **lab_paid_snapshot** giữ giá trị cũ cho đến khi được cập nhật/nạp lại bằng DML.

| Nhu cầu | Đối tượng phù hợp |
| --- | --- |
| Tái sử dụng SELECT ở nhiều màn hình | Ordinary view |
| Chia một câu truy vấn dài thành bước có tên | CTE |
| Lưu kết quả trung gian trong một phiên xử lý | TEMP TABLE |
| Cache báo cáo tổng hợp lớn giữa các lần đọc | MATERIALIZED VIEW hoặc bảng tổng hợp |
| Cần dữ liệu nền mới nhất theo snapshot đọc | Ordinary view |

### 24.1. TEMP VIEW không phải TEMP TABLE

**TEMP** nói về **vòng đời đối tượng trong session**, không nói rằng view đã lưu kết quả. TEMP VIEW vẫn là định nghĩa SELECT, còn TEMP TABLE chứa hàng dữ liệu.

Trong PostgreSQL, view tham chiếu bảng TEMP phải thuộc phạm vi tạm của session; CREATE TEMP VIEW được dùng tường minh trong bài để giữ các đối tượng nhất quán.

Không thiết kế một view permanent dùng giữa nhiều connection mà phụ thuộc vào TEMP TABLE sẽ biến mất khi connection đóng.

## 25. VIEW không nhận tham số như hàm

Ta có thể tạo một view đơn giản:

~~~sql
CREATE TEMP VIEW lab_v_paid_orders AS
SELECT
    order_id,
    tenant_id,
    customer_id,
    order_total_vnd
FROM lab_v_order_overview
WHERE status = 'PAID';
~~~

Để lấy đơn của tenant 10:

~~~sql
SELECT *
FROM lab_v_paid_orders
WHERE tenant_id = 10
ORDER BY order_id;
~~~

Không gọi ordinary view bằng cú pháp **lab_v_paid_orders(10)** như một hàm có tham số.

Trong PostgreSQL có thể dùng prepared statement:

~~~sql
PREPARE lab_paid_by_tenant (INTEGER) AS
SELECT order_id, customer_id, order_total_vnd
FROM lab_v_paid_orders
WHERE tenant_id = $1
ORDER BY order_id;

EXECUTE lab_paid_by_tenant(10);
DEALLOCATE lab_paid_by_tenant;
~~~

Với JDBC, ứng dụng thường dùng **PreparedStatement** và bind giá trị vào placeholder **?**. Không nối dữ liệu người dùng trực tiếp vào chuỗi SQL để tạo WHERE, vì dễ gây SQL injection.

Nếu cần một đối tượng cơ sở dữ liệu thật sự nhận tham số, có thể cân nhắc **hàm trả bảng (table-valued function)** theo ngữ nghĩa của hệ thay vì ordinary view.

## 26. ORDER BY và LIMIT khi đọc VIEW

Không nên dựa vào thứ tự ngầm định:

~~~sql
SELECT order_id, order_total_vnd
FROM lab_v_order_overview
ORDER BY order_total_vnd DESC, order_id;
~~~

**ORDER BY ở câu SELECT cuối** là cách yêu cầu thứ tự có thể dựa vào. Ngay cả khi một phương ngữ cho phép ORDER BY trong định nghĩa view, điều ấy không thay thế việc quy định thứ tự ở nơi tiêu thụ, nhất là khi view được JOIN, tổng hợp hoặc lọc tiếp.

### 26.1. Top 10 toàn hệ khác top 10 theo tenant

Hai bài toán:

1. Lấy **10 đơn cao nhất toàn hệ**, sau đó chỉ hiển thị đơn tenant 10.
2. Chỉ lấy đơn **tenant 10 trước**, rồi chọn **10 đơn cao nhất của tenant 10**.

có thể trả kết quả rất khác nhau. View có ORDER BY/LIMIT bên trong đôi khi đã cố định **thứ tự áp dụng phép chọn**, không đơn giản là thêm trang trí cho kết quả.

Với view tổng quan như lab_v_order_overview, nên để người tiêu thụ quyết định ORDER BY/LIMIT theo yêu cầu cụ thể.

## 27. Schema evolution: thêm, đổi hoặc bỏ cột

### 27.1. Thêm cột vào bảng nguồn

Nếu thêm **phone_number** vào lab_view_customers, view lab_v_customer_public đã liệt kê cột tường minh sẽ không tự đưa số điện thoại ra giao diện. Đây là lợi thế cho hợp đồng dữ liệu ổn định.

### 27.2. Đổi tên cột hoặc kiểu

Đổi tên, xóa hay đổi kiểu cột nguồn có thể bị chặn bởi dependency hoặc yêu cầu thay đổi view tương ứng. Hành vi chính xác phụ thuộc DDL và RDBMS. Không tự tin rằng một câu ALTER TABLE sẽ cập nhật mọi view và ứng dụng theo đúng ý định.

### 27.3. Đổi tên VIEW

~~~sql
-- Thao tác migration minh họa; có thể làm hỏng ví dụ dùng tên cũ.
ALTER VIEW lab_v_paid_orders
RENAME TO lab_v_paid_orders_for_reports;
~~~

Sau đổi tên, câu SQL gọi tên cũ cần được cập nhật. Không thực hiện lệnh này khi còn muốn chạy những bài tập tiếp tục dùng lab_v_paid_orders, trừ khi mục đích là luyện migration.

### 27.4. DDL và giao dịch

PostgreSQL hỗ trợ transactional DDL trong nhiều trường hợp:

~~~sql
BEGIN;

CREATE TEMP VIEW lab_v_trial AS
SELECT order_id, status
FROM lab_view_orders;

SELECT COUNT(*) FROM lab_v_trial;
ROLLBACK;
~~~

View lab_v_trial được tạo trong transaction và sẽ biến mất sau ROLLBACK nếu trước đó chưa có. Tuy nhiên, **MySQL và Oracle có những DDL implicit COMMIT**, nên không port giả định transactional DDL của PostgreSQL sang mọi hệ quản trị.

## 28. Khác biệt theo phương ngữ SQL

| Chủ đề | PostgreSQL | MySQL 8.0 | SQL Server | SQLite | Oracle Database |
| --- | --- | --- | --- | --- | --- |
| Ordinary view | CREATE VIEW | CREATE VIEW | CREATE VIEW | CREATE VIEW | CREATE VIEW |
| Sửa định nghĩa | CREATE OR REPLACE VIEW, giới hạn cột cũ | CREATE OR REPLACE VIEW | ALTER VIEW / CREATE OR ALTER VIEW ở bản hỗ trợ | Thường DROP rồi CREATE lại | CREATE OR REPLACE VIEW |
| TEMP VIEW giống PostgreSQL? | Có | Không dùng nguyên văn cú pháp | Không cùng cú pháp | CREATE TEMP VIEW | Cơ chế đối tượng tạm khác |
| View đơn giản tự cập nhật được? | Có điều kiện | Có điều kiện | Có điều kiện | Mặc định read-only; có thể dùng INSTEAD OF trigger | Có điều kiện |
| Materialized/indexed view | CREATE MATERIALIZED VIEW | Không có native materialized view tương đương phổ biến | Indexed view theo nhiều yêu cầu | Không có native materialized view | Có materialized view |
| CHECK OPTION | Có | Có | Có | Không cùng chức năng native | Có |

### 28.1. PostgreSQL

~~~sql
-- Cú pháp cơ bản:
CREATE VIEW v_example AS
SELECT col_a, col_b
FROM some_table;
~~~

PostgreSQL có thêm **CREATE TEMP VIEW**, **CREATE OR REPLACE VIEW**, **security_invoker** từ phiên bản 15, **security_barrier** và **WITH CHECK OPTION** trong phạm vi hỗ trợ.

### 28.2. MySQL 8.0

~~~sql
-- MySQL, bảng customers giả định tồn tại.
CREATE OR REPLACE VIEW v_customer_names AS
SELECT customer_id, customer_name
FROM customers;
~~~

MySQL có những khái niệm **ALGORITHM = MERGE/TEMPTABLE/UNDEFINED**, **SQL SECURITY DEFINER/INVOKER**, CHECK OPTION và quy tắc về updatability. **ALGORITHM = TEMPTABLE** không tự tạo một materialized view lâu dài; đó là cách xử lý view ở MySQL, không phải cơ chế snapshot cache tự refresh.

Đừng nhầm từ **MERGE** trong ALGORITHM CREATE VIEW của MySQL với câu lệnh **MERGE INTO** của một số hệ.

### 28.3. SQL Server

~~~sql
-- SQL Server, bảng dbo.orders giả định tồn tại.
CREATE OR ALTER VIEW dbo.v_paid_orders
AS
SELECT order_id, customer_id, ordered_at
FROM dbo.orders
WHERE status = 'PAID';
~~~

SQL Server có các yêu cầu batch nhất định đối với CREATE/ALTER VIEW, cùng tính năng **SCHEMABINDING** và **indexed views** với điều kiện chặt chẽ về định nghĩa, kiểu biểu thức và SET options.

**Indexed view không phải bản sao cú pháp CREATE MATERIALIZED VIEW của PostgreSQL.** Chỉ nên dùng khi hiểu chi phí duy trì index khi dữ liệu nguồn thay đổi.

### 28.4. SQLite

~~~sql
-- SQLite, bảng orders giả định tồn tại.
CREATE VIEW v_paid_orders AS
SELECT order_id, customer_id, ordered_at
FROM orders
WHERE status = 'PAID';
~~~

SQLite không dùng cùng cú pháp **CREATE OR REPLACE VIEW** phổ biến ở PostgreSQL/MySQL/Oracle. Khi cần sửa định nghĩa, thường dùng **DROP VIEW và CREATE VIEW** trong một migration có kiểm soát.

View SQLite mặc định **read-only**, nhưng có thể dùng **INSTEAD OF trigger** để định nghĩa tác động ghi qua view theo nhu cầu.

### 28.5. Oracle Database

~~~sql
-- Oracle, bảng orders giả định tồn tại.
CREATE OR REPLACE VIEW v_paid_orders AS
SELECT order_id, customer_id, ordered_at
FROM orders
WHERE status = 'PAID';
~~~

Oracle hỗ trợ materialized view, cơ chế updatability và CHECK OPTION theo quy tắc Oracle. Quyền để tạo view trên bảng nguồn có thể yêu cầu **quyền trực tiếp**, thay vì chỉ quyền thông qua role, nên phải xét chính sách GRANT khi triển khai.

**Khi chuyển hệ quản trị, đừng chỉ thay từ khóa CREATE VIEW.** Cần đối chiếu khả năng cập nhật, quyền, quy tắc NULL, DDL/transaction và cơ chế tối ưu của hệ đang dùng.

## 29. Quy trình thiết kế một VIEW dùng trong sản phẩm

Giả sử phòng tài chính yêu cầu: “Danh sách đơn PAID mỗi tenant, mỗi đơn một dòng, có ngày và tổng tiền”.

Một trình tự có ích:

1. **Xác định grain:** một hàng cho mỗi order_id.
2. **Xác định nguồn chuẩn:** orders, customers, order_items, không lấy giá danh mục hiện tại nếu doanh thu cần giá khi bán.
3. **Đặt công thức chính xác:** SUM(quantity * unit_price_vnd), xử lý đơn thiếu chi tiết.
4. **Tách lớp:** view tổng đơn chung và view PAID theo nhu cầu nếu có tái sử dụng thực.
5. **Đặt contract:** tên cột, kiểu, đơn vị tiền, quy tắc múi giờ, điều kiện PAID, xử lý NULL.
6. **Phân quyền:** role nào thấy tenant nào, PII nào được xuất, RLS hay lớp dịch vụ nào đảm bảo.
7. **Đặt migration:** quản lý owner, GRANT, dependency và phiên bản view.
8. **Quan sát hiệu năng:** EXPLAIN với điều kiện truy vấn thật, chỉ mục nguồn, chi phí sắp xếp/tổng hợp.
9. **Đổi sang vật hóa khi cần:** chỉ khi yêu cầu về độ trễ và dữ liệu cũ cho phép.

Một view tốt không nhất thiết dài hoặc nhiều tầng. Mục tiêu là **đóng gói được một khái niệm rõ ràng**, không phải đưa mọi SELECT vào view.

## 30. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ CREATE VIEW sao chép dữ liệu | Kỳ vọng sai về cache và REFRESH | Phân biệt ordinary với materialized view |
| Nghĩ view luôn nhanh hơn SELECT gốc | GROUP BY/JOIN vẫn có thể tốn tài nguyên | Dùng EXPLAIN |
| View tổng đơn JOIN đồng thời nhiều bảng con 1-n | Fanout làm nhân tiền | Pre-aggregate theo order_id |
| Không ghi grain | Người dùng SUM/COUNT sai cấp | Mô tả một hàng tượng trưng cho gì |
| Lấy giá hiện tại từ products để tính đơn cũ | Báo cáo lịch sử biến đổi khi đổi bảng giá | Dùng giá trên dòng đơn |
| Gọi mọi tổng đơn là revenue | Tính cả DRAFT/CANCELLED | Tách order_total khỏi doanh thu PAID |
| INNER JOIN chi tiết làm mất đơn trống | Không thấy đơn DRAFT | LEFT JOIN theo chính sách |
| Quên COALESCE | Tổng đơn trống nhận NULL | Dùng COALESCE khi nghiệp vụ chọn 0 |
| Dùng SELECT * trong view public | Hợp đồng khó quản lý, có thể lộ cột | Chọn cột tường minh |
| VIEW nhiều tầng không rõ trách nhiệm | Khó debug/performance | Chia lớp có ý nghĩa, không quá sâu |
| Đổi kiểu cột qua CREATE OR REPLACE VIEW PostgreSQL | Lỗi tương thích schema | Migration đúng cách |
| DROP VIEW CASCADE tùy tiện | Xóa view phụ thuộc | Rà dependency trước |
| Tin WHERE tenant_id trên view đủ bảo mật | Có thể lộ dữ liệu qua quyền khác | GRANT/RLS và kiểm soát role |
| Bật security_invoker mà thiếu quyền bảng nền | SELECT thất bại | Thiết kế quyền caller phù hợp |
| Dùng CHECK OPTION thay RLS | Không ngăn đường ghi qua bảng nền | Hiểu phạm vi CHECK OPTION |
| UPDATE view tổng hợp | Không ánh xạ được dòng dữ liệu cần sửa | DML bảng nguồn theo nghiệp vụ |
| Nhầm TEMP VIEW với TEMP TABLE | Tưởng đã lưu snapshot | TEMP VIEW vẫn là định nghĩa truy vấn |
| Dùng materialized view chưa refresh cho báo cáo realtime | Dữ liệu trễ | Lịch refresh hoặc ordinary view |
| INDEX ordinary view như bảng | Không có lưu trữ hàng vật lý riêng | Index bảng nguồn |
| VIEW trên bảng TEMP nhưng mong các session khác dùng | TEMP chỉ theo session | Dùng bảng và view permanent |
| Không ORDER BY ở SELECT ngoài | Thứ tự đầu ra không chắc chắn | ORDER BY tại nơi đọc |
| Port CREATE OR REPLACE trực tiếp sang SQLite | Sai cú pháp | DROP/CREATE theo migration |
| Đặt LIMIT trong view và lọc tenant ở ngoài | Top N toàn hệ không bằng top N theo tenant | Xác định thứ tự lọc và chọn |

## 31. Bài tập thực hành

Các bài dùng bộ bảng **lab_view_*** và các view đã tạo. Khi thay đổi dữ liệu, nên dùng **BEGIN ... ROLLBACK** để giữ tập ban đầu.

1. Tạo bốn bảng nguồn, nhập dữ liệu và kiểm tra tổng 4 khách, 4 sản phẩm, 6 đơn, 10 dòng.
2. Viết SELECT tổng tiền từng order_id từ lab_view_order_items. Vì sao đơn 1003 không xuất hiện?
3. Dùng LEFT JOIN từ orders sang tập items đã GROUP BY để giữ đơn 1003.
4. Tạo lab_v_order_overview theo ví dụ và kiểm tra **một hàng/order_id**.
5. Tính line_count, unit_count và order_total_vnd của đơn 1001. Vì sao line_count khác unit_count?
6. Truy vấn tất cả đơn PAID qua view và tính tổng **790.000 VND**.
7. GROUP BY tenant_id từ view để thấy tenant 10 doanh thu 590.000, tenant 20 doanh thu 200.000.
8. Tạo view doanh thu PAID theo ngày UTC, dựa vào view tổng đơn.
9. Đổi ngày báo cáo sang Asia/Ho_Chi_Minh. Tại sao việc chọn timezone phải rõ ràng?
10. Trong BEGIN, thêm dòng số 3 cho đơn 1001 với giá 90.000; đọc view để thấy 200.000, rồi ROLLBACK.
11. Vì sao không cần CREATE OR REPLACE VIEW sau INSERT/ROLLBACK ở bài 10?
12. Tính số đơn PAID theo mỗi khách bằng LEFT JOIN customers với view tổng đơn, giữ khách không có đơn PAID.
13. Chuyển điều kiện status='PAID' từ ON sang WHERE ở bài 12 và giải thích khách Dung biến mất.
14. Giả sử một đơn có hai dòng item và hai payment. Nếu JOIN trực tiếp ba bảng, có bao nhiêu hàng trung gian?
15. Thiết kế cách tổng hợp payments riêng theo order_id trước khi JOIN với item_totals.
16. Tạo lab_v_customer_public chỉ có customer_id, tenant_id, customer_name; giải thích vì sao không dùng SELECT *.
17. Thay view trên bằng CREATE OR REPLACE TEMP VIEW và thêm customer_name_upper ở cuối.
18. Giải thích giới hạn giữ tên/thứ tự/kiểu cột cũ của CREATE OR REPLACE VIEW PostgreSQL.
19. Dùng pg_get_viewdef xem định nghĩa lab_v_order_overview.
20. Dùng EXPLAIN cho SELECT từ view lọc order_id = 1001; những bảng nguồn nào có thể xuất hiện?
21. Tạo index trên orders(status,order_at). Vì sao bộ tối ưu có thể không dùng chỉ mục với dữ liệu nhỏ?
22. Tạo TEMP TABLE lab_paid_snapshot AS SELECT từ view PAID; sửa dữ liệu nguồn tạm và so sánh snapshot với view.
23. Tạo lab_v_customer_names rồi UPDATE tên khách qua view trong BEGIN; đọc bảng nguồn và ROLLBACK.
24. Tạo lab_v_tenant10_customers WITH CHECK OPTION; dự đoán INSERT tenant 10 và tenant 20.
25. Vì sao CHECK OPTION không chặn một người có quyền ghi trực tiếp bảng nguồn?
26. So sánh security_invoker = true với view mặc định của PostgreSQL khi xét quyền bảng nền.
27. Một hệ đa tenant nên kết hợp view với quyền/RLS thế nào để tránh rò rỉ hàng?
28. Nếu đổi công thức order_total_vnd, những view và báo cáo phụ thuộc cần được đánh giá?
29. Tạo prepared statement lọc lab_v_paid_orders theo tenant_id và chạy với hai giá trị.
30. So sánh ordinary view, CTE, temp table và materialized view về vòng đời và lưu dữ liệu.
31. Vì sao CREATE MATERIALIZED VIEW không tự bảo đảm dữ liệu mới nhất?
32. Mô tả tác động của DROP VIEW ... CASCADE khi view khác còn phụ thuộc.
33. So sánh cách sửa định nghĩa view ở PostgreSQL và SQLite.
34. Phân biệt indexed view trong SQL Server với ordinary view và materialized view PostgreSQL.

### Câu hỏi tự kiểm tra

**Câu 1.** CREATE VIEW có tạo ngay một bảng mới chứa toàn bộ kết quả không?

**Đáp án:** **Không** với ordinary view. Nó lưu định nghĩa SELECT; materialized view là đối tượng riêng có dữ liệu kết quả vật lý.

**Câu 2.** Khi INSERT thêm dòng hàng vào orders detail rồi COMMIT, SELECT từ view tổng đơn có thể thấy tổng mới không?

**Đáp án:** **Có**, theo snapshot của SELECT. Không cần gọi REFRESH với ordinary view.

**Câu 3.** Một view mỗi đơn một hàng nên làm gì khi cần JOIN cả items và payments đều là 1-n?

**Đáp án:** Tổng hợp từng nhánh về một hàng/order_id trước khi JOIN, tránh fanout.

**Câu 4.** CREATE VIEW có tự tăng tốc mọi SELECT vì đã cache kết quả không?

**Đáp án:** **Không.** Hệ có thể vẫn phải JOIN, SUM, GROUP BY; cần EXPLAIN và chỉ mục nguồn.

**Câu 5.** Tổng tiền đơn CANCELLED có mặc định là doanh thu đã thanh toán?

**Đáp án:** **Không.** Bài quy định doanh thu PAID chỉ từ những đơn status = 'PAID'.

**Câu 6.** PostgreSQL CREATE OR REPLACE VIEW có cho tùy ý xóa/đổi kiểu cột cũ?

**Đáp án:** **Không.** Cột cũ phải giữ tên, thứ tự, kiểu; có thể thêm cột ở cuối. Thay đổi khác cần migration thích hợp.

**Câu 7.** View có tenant_id có tự bảo đảm mỗi người chỉ thấy tenant của mình?

**Đáp án:** **Không.** Cần quyền truy cập, role, RLS hoặc lớp lọc tenant đáng tin cậy.

**Câu 8.** Mọi view đều tự động cập nhật được bằng UPDATE?

**Đáp án:** **Không.** PostgreSQL có thể cập nhật một số simple view; view JOIN/tổng hợp thường không tự động updatable.

**Câu 9.** WITH CHECK OPTION có thay thế ràng buộc hoặc RLS bảng nguồn không?

**Đáp án:** **Không.** Nó kiểm tra DML qua view trong phạm vi áp dụng; quyền bảng nền và RLS là lớp khác.

**Câu 10.** TEMP VIEW có phải một TEMP TABLE chứa snapshot không?

**Đáp án:** **Không.** TEMP VIEW vẫn là định nghĩa SELECT, chỉ vòng đời của đối tượng là tạm trong session.

**Câu 11.** Ordinary view có nhận tham số như một hàm không?

**Đáp án:** **Không.** Lọc trong SELECT sử dụng view hoặc dùng PreparedStatement; nếu cần đối tượng nhận tham số, cân nhắc hàm trả bảng.

**Câu 12.** SELECT từ view không có ORDER BY ngoài có bảo đảm thứ tự ổn định không?

**Đáp án:** **Không.** Hãy đặt ORDER BY ở câu truy vấn cuối khi thứ tự quan trọng.

## 32. Ghi nhớ cốt lõi

**CREATE VIEW đóng gói một truy vấn thành đối tượng có tên** để nhiều câu SELECT, API và báo cáo cùng sử dụng một logic. Khi thiết kế view, phải xác định **grain, khóa logic, công thức, ý nghĩa cột, đơn vị, xử lý NULL và điều kiện lọc**.

**Ordinary view không tự cache kết quả.** Khi bảng nguồn thay đổi, view thường phản ánh dữ liệu nguồn theo snapshot của lần đọc; nếu cần lưu kết quả tính sẵn, đánh giá materialized view hoặc bảng tổng hợp. Đừng bỏ qua EXPLAIN, chỉ mục nguồn và bẫy fanout khi JOIN nhiều nhánh 1-n.

**View cũng không tự bảo đảm bảo mật hoặc khả năng cập nhật.** Cần xem quyền GRANT, owner, RLS/security_invoker, khả năng updatable và WITH CHECK OPTION theo phương ngữ. Với view tổng hợp, thao tác ghi thường phải đi qua logic nghiệp vụ ở bảng nguồn.

Phân biệt ngắn gọn:

~~~text
CTE               → tên của bước truy vấn trong một câu SQL
Ordinary VIEW     → tên của SELECT dùng lại, đọc từ dữ liệu nguồn
TEMP TABLE        → lưu snapshot trung gian trong phiên
MATERIALIZED VIEW → lưu kết quả truy vấn để đọc, cần cơ chế làm mới
~~~

Cuối cùng, **quản lý CREATE VIEW như quản lý một giao diện dữ liệu chính thức**: có migration, xem xét dependency, không phá vỡ hợp đồng cột tùy ý và đánh giá ảnh hưởng khi đổi công thức đã được nhiều consumer sử dụng.
