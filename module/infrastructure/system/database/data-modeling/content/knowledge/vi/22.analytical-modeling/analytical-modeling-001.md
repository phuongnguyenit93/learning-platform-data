# Phân biệt nhu cầu giao dịch OLTP với nhu cầu phân tích OLAP

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **OLTP** (*Online Transaction Processing*) và **OLAP** (*Online Analytical Processing*) dựa trên **mục tiêu nghiệp vụ, loại truy vấn, mức nhất quán và đặc điểm tải**, thay vì chỉ dựa vào tên cơ sở dữ liệu.
- Chuyển một yêu cầu như "đặt hàng không được bán vượt tồn" thành mô hình giao dịch, và yêu cầu như "doanh thu theo danh mục trong 12 tháng" thành mô hình phân tích với **hạt dữ liệu (grain), fact, dimension và metric** rõ ràng.
- Giải thích vì sao chuẩn hóa, khóa, ràng buộc, chỉ mục và transaction thường phục vụ OLTP, trong khi bảng sự kiện, mô hình sao, lưu trữ cột, phân vùng và tổng hợp phục vụ nhiều kiểu OLAP.
- Nhận biết các bẫy đo lường: đếm trùng khi JOIN, nhầm thời điểm ghi nhận, tính giá theo danh mục hiện tại thay cho giá tại giao dịch, trộn trạng thái và cập nhật chậm.
- Thiết kế đường chuyển dữ liệu từ hệ thống vận hành sang phân tích bằng batch/CDC với kiểm tra chất lượng, idempotency, xử lý sự kiện đến muộn và quản lý lịch sử.
- Lựa chọn kiến trúc phù hợp khi chỉ có một database, cần read replica, data warehouse, mô hình gần thời gian thực hoặc cách tiếp cận lai (*HTAP*).

Trong module **DATABASE_DATA_MODELING**, cùng một nghiệp vụ có thể cần **hai cách nhìn dữ liệu khác nhau**. Hệ thống bán hàng phải chấp nhận hoặc từ chối một đơn thật chính xác ngay lúc khách nhấn "Đặt hàng". Bộ phận kinh doanh lại muốn xem xu hướng số đơn, số khách và giá trị bán hàng theo thời gian, danh mục hoặc kênh. Hai nhu cầu đó không nhất thiết được đáp ứng tối ưu bằng cùng một lược đồ, cùng tập chỉ mục và cùng chiến lược truy vấn. Đây là ý nghĩa của việc phân biệt **OLTP** với **OLAP** trong chương **Mô hình phân tích**.

## 1. Bắt đầu từ câu hỏi nghiệp vụ, không từ sản phẩm database

Giả sử một nhà bán lẻ có website nhận hàng nghìn lệnh giỏ hàng, đặt hàng, giữ tồn kho và hoàn tiền. Ban điều hành đồng thời hỏi:

- **"Khách A có đặt được hai chiếc sản phẩm P ngay bây giờ không?"** Phải kiểm tra số lượng và giữ hàng nguyên tử, sau đó ghi đơn và phản hồi.
- **"Trong 90 ngày gần đây, doanh số đã thanh toán tăng bao nhiêu so với 90 ngày trước, chia theo danh mục tại thời điểm bán?"** Phải đọc rất nhiều giao dịch, nhóm theo ngày, danh mục, so sánh các giai đoạn và bảo vệ ý nghĩa KPI.
- **"Đến 9 giờ sáng hôm nay, còn bao nhiêu sản phẩm có nguy cơ hết hàng?"** Có thể là bài toán vận hành gần thời gian thực; cần xác định người dùng cần số liệu chính xác đến mức nào và độ trễ cho phép.

Hai câu đầu tiêu biểu cho hai loại xử lý:

- **OLTP:** thực hiện những **thay đổi nghiệp vụ cụ thể**, thường đọc/ghi ít bản ghi, yêu cầu transaction và ràng buộc để trạng thái vận hành không bị sai.
- **OLAP:** trả lời những **câu hỏi tổng hợp, so sánh, phân đoạn và phân tích lịch sử**, thường đọc nhiều dòng/cột trong thời gian dài, chủ yếu theo kiểu read-heavy.

OLTP/OLAP là **cách mô tả workload và mục tiêu xử lý**, không phải nhãn vĩnh viễn của PostgreSQL, MySQL, một document database hay một data warehouse. Một PostgreSQL vẫn chạy được truy vấn tổng hợp; một warehouse có thể nạp dữ liệu thường xuyên. Vấn đề là workload chính, khả năng giữ bất biến và chi phí khi những workload cùng chạy.

## 2. Bảng so sánh những khác biệt quyết định

| Khía cạnh | OLTP — giao dịch vận hành | OLAP — truy vấn phân tích |
| --- | --- | --- |
| Câu hỏi điển hình | "Đơn này được xác nhận chưa?", "Còn đủ tồn không?" | "Doanh số theo tháng, vùng, danh mục thay đổi thế nào?" |
| Tác vụ chính | INSERT/UPDATE/DELETE có kiểm soát; đọc điểm, đọc phạm vi hẹp | Lọc, JOIN, GROUP BY, window function, tổng hợp trên nhiều bản ghi |
| Đối tượng quan tâm | Một đơn, tài khoản, lượt giữ hàng, phiên thanh toán | Một tập giao dịch, phân khúc, chuỗi thời gian, phân bố |
| Đường ghi | Nhiều giao dịch ngắn, cạnh tranh đồng thời | Nạp theo batch, micro-batch, stream/CDC; sửa lịch sử theo chính sách |
| Tính nhất quán | Bất biến phải đúng khi giao dịch commit | Số liệu thường có **độ trễ xác định**; cần đúng về ngữ nghĩa và khả năng đối soát |
| Quy mô dữ liệu một truy vấn | Thường nhỏ và có điều kiện theo khóa | Có thể rất lớn, qua nhiều ngày/tháng/năm |
| Mục tiêu hiệu năng | Phản hồi lệnh nhanh, thông lượng ghi, xung đột thấp | Đọc và tổng hợp nhanh, nhiều người dùng chạy báo cáo |
| Thiết kế dữ liệu thường gặp | Thực thể nghiệp vụ, chuẩn hóa phù hợp, khóa ngoại, constraint | Fact/dimension, star schema, bảng rộng, aggregate table, cột |
| Chỉ mục/chiến lược truy cập | PK, UNIQUE, B-tree theo đường truy vấn và điều kiện ghi | Partition pruning, scan theo cột, compression, clustering/sort key, materialized aggregate |
| Lịch sử | Trạng thái hiện tại và lịch sử cần cho vận hành/audit | Lịch sử dài, snapshot, sự kiện, chiều thay đổi theo thời gian |
| Rủi ro chính | Lost update, write skew, deadlock, ghi nửa chừng, vi phạm bất biến | Đếm trùng, định nghĩa KPI mơ hồ, dữ liệu trễ, sai hạt hoặc sai lịch sử |

Đừng diễn giải "OLAP chấp nhận dữ liệu sai" từ cột nhất quán. **Kết quả phân tích vẫn phải chính xác đối với dữ liệu, thời điểm chốt và định nghĩa KPI mà nó công bố.** Điều có thể khác OLTP là độ trễ từ lúc giao dịch commit đến lúc bản sao phân tích hiển thị nó.

## 3. Ví dụ OLTP: ghi một đơn hàng đúng trong cạnh tranh

Hệ thống vận hành lưu Order và OrderLine. Một đơn có nhiều dòng; khách chỉ được xác nhận đơn khi giữ được hàng theo chính sách. Một lược đồ quan hệ minh họa:

~~~sql
CREATE SCHEMA IF NOT EXISTS shop;

CREATE TABLE shop.orders (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'RESERVED', 'PAID', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, order_id),
    CHECK (status <> 'PAID' OR paid_at IS NOT NULL)
);

CREATE TABLE shop.order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES shop.orders (tenant_id, order_id)
);

CREATE TABLE shop.stock_balance (
    tenant_id UUID NOT NULL,
    warehouse_id UUID NOT NULL,
    product_id UUID NOT NULL,
    available_quantity INTEGER NOT NULL CHECK (available_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, warehouse_id, product_id)
);

CREATE INDEX orders_by_customer
    ON shop.orders (tenant_id, customer_id, created_at DESC);
~~~

**Ý nghĩa các cấu trúc:**

- Khóa ghép theo tenant bảo vệ phạm vi định danh; các đường ghi phải kiểm tra quyền tenant ngoài việc có ID hợp lệ.
- Khóa ngoại đảm bảo dòng hàng thuộc một đơn tồn tại, nhưng **không tự** đảm bảo việc giữ kho hoặc thanh toán thành công.
- CHECK kiểm tra ràng buộc cục bộ như quantity dương, trạng thái thuộc tập cho phép.
- Chỉ mục theo khách phục vụ truy vấn "đơn của khách này trong thời gian gần đây". Không nên tạo chỉ mục cho mọi cách GROUP BY của ban giám đốc trên cùng database vận hành.
- Giá đã mua được lưu trên dòng đơn: đổi giá Catalog hôm nay không làm thay đổi số tiền đã cam kết của đơn hôm qua.

### Một thao tác giữ tồn kho phải có điểm phân xử

Với một dòng cần giữ hai đơn vị hàng, có thể dùng một UPDATE có điều kiện trong transaction:

~~~sql
BEGIN;

UPDATE shop.stock_balance
SET available_quantity = available_quantity - :quantity,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND warehouse_id = :warehouse_id
  AND product_id = :product_id
  AND :quantity > 0
  AND available_quantity >= :quantity
RETURNING available_quantity;

-- Nếu không có đúng một hàng được cập nhật:
-- ROLLBACK, báo hết hàng/không có bản ghi; không ghi giữ chỗ thành công.
-- Nếu có nhiều dòng, lặp theo thứ tự khóa ổn định trong cùng transaction.
-- Ghi quyền giữ, cập nhật trạng thái đơn và outbox trong cùng transaction
-- khi tất cả dữ liệu nằm trong cùng database và chính sách yêu cầu.

COMMIT;
~~~

Hai request cùng xin số hàng cuối cùng không được đơn giản SELECT available_quantity rồi tự trừ trong bộ nhớ. Với PostgreSQL, UPDATE có điều kiện trên **cùng hàng tồn kho** bảo vệ kiểm tra và giảm số lượng nguyên tử trong phạm vi giao dịch. Nếu kho là một service/database riêng, Order không thể tự coi UPDATE của mình là giao dịch phân tán; cần quyền giữ từ nguồn có thẩm quyền và trạng thái trung gian.

**Điểm mấu chốt OLTP:** trạng thái sau COMMIT phải tuân thủ bất biến. Tốc độ đếm toàn bộ 100 triệu dòng đơn không phải ưu tiên số một trong đường ghi giữ hàng.

## 4. Ví dụ OLAP: doanh số cần tập dữ liệu và ngữ nghĩa khác

Giả sử quản lý hỏi: **"Trong tháng 10, tổng giá trị hàng đã bán được thanh toán theo danh mục sản phẩm là bao nhiêu?"** Truy vấn có thể cần:

1. Lấy các đơn đạt trạng thái phù hợp theo **ngày thanh toán**.
2. Chọn từng dòng hàng và **đơn giá tại thời điểm bán**.
3. Gắn danh mục sản phẩm đúng **thời điểm nghiệp vụ yêu cầu**, không mặc định dùng danh mục mới nhất.
4. Nhóm theo danh mục và tính tổng doanh số.
5. Loại các bản ghi trùng do nạp lại hoặc do JOIN sang bảng thanh toán nhiều dòng.

Một truy vấn trực tiếp trên OLTP có thể trông như sau (giả định danh mục hiện hành được lưu ở bảng Catalog trong cùng database):

~~~sql
SELECT p.category_name,
       SUM(l.quantity::BIGINT * l.unit_price_vnd) AS paid_sales_vnd
FROM shop.orders AS o
JOIN shop.order_line AS l
  ON l.tenant_id = o.tenant_id AND l.order_id = o.order_id
JOIN shop.product AS p
  ON p.tenant_id = l.tenant_id AND p.product_id = l.product_id
WHERE o.status = 'PAID'
  AND o.paid_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND o.paid_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY p.category_name;
~~~

**shop.product là một bảng giả định để minh họa, không có DDL ở trên.** Truy vấn có nhiều giới hạn:

- Nếu một đơn đã PAID rồi hoàn tiền, SUM trên dòng đơn không tự trừ số hoàn.
- Nếu product.category_name bị đổi sau khi bán, các giao dịch cũ có thể bị gán sang danh mục **hiện hành** thay vì danh mục **lúc bán**.
- Nếu JOIN sang bảng payment có nhiều payment attempt cho mỗi đơn, dòng doanh số có thể bị **nhân bản**.
- Nếu một lượng lớn đơn được quét cùng lúc, báo cáo có thể cạnh tranh CPU, cache, I/O và tài nguyên với đường ghi OLTP, dù cơ chế MVCC hạn chế chặn đọc/ghi ở nhiều tình huống.

Bản thân SQL không sai: nó trả lời một **định nghĩa cụ thể** là "giá trị dòng của các đơn hiện còn trạng thái PAID, nhóm theo danh mục sản phẩm hiện tại". Nhưng định nghĩa đó **có thể không phải** KPI mà ban điều hành đang hỏi. Chuyển sang OLAP trước tiên là **chọn đúng mô hình đo lường**, sau đó mới tối ưu tốc độ.

## 5. Grain: quyết định quan trọng nhất trước khi dựng bảng fact

**Grain** là một câu đầy đủ mô tả **một hàng trong bảng fact đại diện cho điều gì**. Chọn grain trước khi liệt kê measure, dimension và chỉ mục.

Một vài lựa chọn:

| Grain ứng viên | Một hàng là gì? | Phù hợp cho | Không nên suy ra |
| --- | --- | --- | --- |
| Một Order | Một đơn được tạo/được thanh toán | Số đơn, tổng theo đơn, tỷ lệ chuyển đổi theo đơn | Số sản phẩm từng danh mục nếu không có chi tiết |
| Một OrderLine lúc thanh toán | Một dòng hàng thuộc một đơn khi hoàn tất thanh toán theo quy ước | Số lượng bán, giá trị bán theo sản phẩm | Mỗi hàng là một đơn độc lập |
| Một PaymentAttempt | Một lần thử thanh toán | Tỷ lệ thành công theo phương thức/cổng | Mỗi attempt là một lần mua mới |
| Một RefundLine hoàn tất | Một dòng tiền hoàn đã hoàn tất cho dòng hàng | Giá trị hoàn, số lượng trả theo sản phẩm | Là giao dịch bán dương |
| Một InventorySnapshot theo ngày | Trạng thái tồn của một sản phẩm trong kho tại cuối ngày | Tồn theo thời điểm, xu hướng và ngày hết hàng | SUM tồn qua các ngày là tồn tại một thời điểm |

Ví dụ này chọn hai fact cơ bản:

- **fact_paid_order_line**: mỗi hàng biểu diễn **một dòng OrderLine được ghi nhận bán một lần khi đơn được thanh toán toàn bộ**. Chúng ta giả định mỗi đơn được thanh toán một lần cho đủ toàn bộ đơn; không xét split payment, partial capture hoặc bán theo nhiều đợt. Khóa nghiệp vụ là (tenantId, orderId, lineNo).
- **fact_completed_refund_line**: mỗi hàng biểu diễn **một dòng hoàn tiền đã hoàn tất** cho một dòng bán cụ thể, có refundLineId riêng. Một dòng bán có thể có nhiều lần hoàn theo chính sách.

Grain được công bố giúp trả lời việc SUM cái gì, COUNT cái gì, và phép JOIN nào sẽ tạo nhiều bản sao.

### Additive, semi-additive và non-additive measures

| Measure | Tính chất | Cách sử dụng |
| --- | --- | --- |
| Số lượng bán (dòng bán) | Thường **additive** theo sản phẩm/thời gian nếu cùng định nghĩa | SUM(quantity) |
| Giá trị bán VND (dòng bán) | Additive trong cùng tiền tệ và quy tắc ghi nhận | SUM(gross_amount_vnd) |
| Tồn cuối ngày | **Semi-additive**: cộng theo sản phẩm/kho tại cùng ngày, không cộng qua ngày để ra tồn hiện tại | Lấy snapshot tại thời điểm phù hợp |
| Giá trung bình/đơn | **Non-additive**: không SUM hoặc lấy trung bình các tỷ lệ tùy tiện | SUM(amount) / COUNT(DISTINCT order_id) |
| Tỷ lệ thanh toán thành công | Non-additive | SUM(successful_attempts) / SUM(total_attempts), tránh AVG tỷ lệ con thiếu trọng số |
| Số khách duy nhất | Không thể cộng các COUNT DISTINCT của nhiều tháng để ra số khách cả quý | COUNT(DISTINCT customer_id) trên tập phù hợp |

Không có "một measure doanh thu" dùng đúng mọi hoàn cảnh. Kế toán có thể ghi nhận doanh thu theo ngày giao hàng, ngày nghiệm thu, phân bổ nghĩa vụ thực hiện hoặc quy tắc khác. Bài này dùng **giá trị hàng đã thanh toán**, không tự đồng nhất nó với doanh thu kế toán.

## 6. Mô hình sao: fact và dimension phục vụ phân tích

Một **star schema** điển hình đặt fact ở trung tâm và dimension xung quanh. Fact ghi sự kiện đo lường tại grain đã chọn; dimension cung cấp ngữ cảnh để lọc/nhóm:

~~~mermaid
flowchart TB
    F["fact_paid_order_line<br/>1 dòng bán khi đơn đã PAID"]
    D1["dim_product<br/>tên, danh mục theo thời điểm"]
    D2["dim_date<br/>ngày, tháng, quý, năm"]
    D3["dim_channel<br/>web, mobile, cửa hàng"]
    D4["dim_customer<br/>phân khúc có quyền truy cập"]
    F -->|"product_key"| D1
    F -->|"paid_date_key"| D2
    F -->|"channel_key"| D3
    F -->|"customer_key"| D4
~~~

Điểm khác so với sơ đồ ERD cho xử lý giao dịch:

- Fact có thể cố ý lưu các **khóa dimension thay thế** (*surrogate keys*) để giữ phiên bản mô tả lịch sử.
- Dữ liệu mô tả thường được nhóm trong dimension, **không nhất thiết chuẩn hóa sâu** thành nhiều bảng nhỏ.
- Các khóa nghiệp vụ như orderId, lineNo có thể vẫn nằm trong fact như **degenerate dimensions** để truy vết và đếm đơn, thay vì tạo dim_order chỉ để chứa ID.
- Fact thường lớn hơn dimension; truy vấn đọc nhiều fact nhưng chỉ những cột cần thiết. Lưu trữ dạng cột, phân vùng và tổ chức dữ liệu theo workload có thể hữu ích.

### Ví dụ dữ liệu cụ thể

Một đơn O-101 có hai dòng:

| Dòng bán | Sản phẩm | Số lượng | Đơn giá lúc bán | Thành tiền |
| --- | --- | ---: | ---: | ---: |
| (O-101, 1) | Áo thun | 2 | 100.000 VND | 200.000 VND |
| (O-101, 2) | Mũ | 1 | 50.000 VND | 50.000 VND |

Sau khi đơn được thanh toán, fact có **hai hàng**, không phải một. Tổng giá trị bán là 250.000 VND, nhưng **số đơn = 1**, không phải 2. Nếu sau đó hoàn 100.000 VND cho một áo, fact hoàn có dòng âm/tách biệt theo quy tắc đã công bố, không xóa giao dịch bán lịch sử rồi coi chưa từng xảy ra.

Với một fact mà một hàng là OrderLine, COUNT(*) trả về **số dòng bán**; để đếm **số đơn**, dùng COUNT(DISTINCT order_id) trong phạm vi tenant phù hợp hoặc bảng fact riêng ở grain đơn.

## 7. Ví dụ lược đồ OLAP bằng PostgreSQL

Để người học có thể đọc cú pháp SQL quen thuộc, ví dụ sau dùng PostgreSQL làm **công cụ minh họa**. Trong thực tế, warehouse có thể dùng hệ quản trị chuyên phân tích với loại khóa, kiểu dữ liệu, chỉ mục và cách phân vùng khác. Không nên coi cấu hình PostgreSQL ở đây là tối ưu cho mọi warehouse.

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.dim_product (
    product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL,
    category_name TEXT NOT NULL,
    product_name TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    UNIQUE (tenant_id, product_id, valid_from)
);

CREATE TABLE mart.fact_paid_order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    product_key BIGINT NOT NULL REFERENCES mart.dim_product(product_key),
    customer_id UUID NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    paid_date DATE NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    gross_amount_vnd BIGINT NOT NULL CHECK (gross_amount_vnd >= 0),
    load_batch_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no)
);

CREATE TABLE mart.fact_completed_refund_line (
    tenant_id UUID NOT NULL,
    refund_line_id UUID NOT NULL,
    order_id UUID NOT NULL,
    order_line_no INTEGER NOT NULL,
    product_key BIGINT NOT NULL REFERENCES mart.dim_product(product_key),
    refunded_at TIMESTAMPTZ NOT NULL,
    refunded_date DATE NOT NULL,
    refunded_quantity INTEGER NOT NULL CHECK (refunded_quantity > 0),
    refund_amount_vnd BIGINT NOT NULL CHECK (refund_amount_vnd >= 0),
    load_batch_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, refund_line_id)
);

CREATE INDEX fact_sales_by_date_product
    ON mart.fact_paid_order_line (tenant_id, paid_date, product_key);

CREATE INDEX fact_refund_by_date_product
    ON mart.fact_completed_refund_line (tenant_id, refunded_date, product_key);
~~~

**Các lựa chọn cần hiểu:**

- fact_paid_order_line giữ **khóa nghiệp vụ** (tenantId, orderId, lineNo) để retry nạp không tạo thêm một dòng bán. Nếu một đơn có thể được thanh toán từng phần, grain này phải **được thiết kế lại**; không cố dùng khóa cũ khi yêu cầu đã thay.
- product_key là khóa thay thế chỉ tới **phiên bản dimension đã chọn**. Cột product_id của nguồn vẫn còn trong dim_product để truy vết.
- paid_date/refunded_date là ngày theo **múi giờ báo cáo đã thống nhất**. Nếu có nhiều tenant với múi giờ riêng, pipeline cần dùng timezone của từng tenant vào đúng thời điểm và ghi chính sách chuyển đổi. Không âm thầm ép ngày UTC thành ngày kinh doanh địa phương.
- gross_amount_vnd và refund_amount_vnd là số nguyên VND, không trộn các loại tiền; tên gross ở đây nghĩa là **giá trị dòng hàng đã thanh toán theo quy ước bài học**, chưa tính thuế/phí vận chuyển/chiết khấu phức tạp.
- FK ở ví dụ minh họa giúp phát hiện product_key chưa tồn tại; nhiều warehouse chuyên dụng không thực thi FK như OLTP, nên chất lượng dữ liệu phải được kiểm tra trong pipeline.
- Hai chỉ mục là lựa chọn hợp lý cho các truy vấn mẫu nhưng có thể không phải lựa chọn tối ưu trên lưu trữ cột. Partitioning/clustering cần dựa vào khối lượng và mẫu truy vấn thực tế.

### SCD Type 2: danh mục sản phẩm thay đổi theo thời gian

Giả sử ngày 01/10 sản phẩm P thuộc danh mục "Phụ kiện", đến 15/10 được chuyển sang "Thiết bị". Nếu yêu cầu phân tích là **"theo danh mục tại thời điểm bán"**, dim_product cần giữ lịch sử:

| product_key | product_id | category_name | valid_from | valid_to |
| ---: | --- | --- | --- | --- |
| 101 | P | Phụ kiện | 2026-01-01 00:00+07 | 2026-10-15 00:00+07 |
| 205 | P | Thiết bị | 2026-10-15 00:00+07 | NULL |

Pipeline ánh xạ dòng bán lúc 10/10 đến product_key=101, dòng bán lúc 20/10 đến product_key=205. Khoảng hiệu lực sử dụng quy ước **[valid_from, valid_to)**: gồm đầu, không gồm cuối. Phải bảo đảm không có **hai phiên bản chồng khoảng** cho cùng (tenantId, productId); UNIQUE trên (tenantId, productId, valid_from) ở trên **chưa đủ** để ngăn chồng khoảng. Có thể kiểm tra trong ETL hoặc dùng constraint phạm vi phù hợp khi hệ quản trị hỗ trợ.

Nếu nghiệp vụ muốn **toàn bộ giao dịch lịch sử được phân loại theo danh mục hiện nay**, một truy vấn/dimension khác có thể phù hợp. Đây là **hai câu hỏi hợp lệ nhưng cho kết quả khác nhau**. Người thiết kế phải ghi rõ chọn cách nào.

## 8. Viết truy vấn OLAP đúng grain, đúng thời điểm

**Yêu cầu A:** giá trị hàng đã thanh toán theo danh mục **tại thời điểm bán**, trong tháng 10/2026, cho một tenant:

~~~sql
SELECT p.category_name,
       SUM(f.quantity) AS items_sold,
       SUM(f.gross_amount_vnd) AS paid_sales_vnd,
       COUNT(DISTINCT f.order_id) AS distinct_orders_in_category
FROM mart.fact_paid_order_line AS f
JOIN mart.dim_product AS p
  ON p.product_key = f.product_key
 AND p.tenant_id = f.tenant_id
WHERE f.tenant_id = :tenant_id
  AND f.paid_date >= DATE '2026-10-01'
  AND f.paid_date <  DATE '2026-11-01'
GROUP BY p.category_name
ORDER BY paid_sales_vnd DESC;
~~~

**Lưu ý:** distinct_orders_in_category là số đơn **có ít nhất một sản phẩm trong danh mục đó**; một đơn mua hai danh mục được tính vào cả hai nhóm. Không được SUM các số đếm này để kết luận tổng số đơn duy nhất toàn tháng.

**Yêu cầu B:** "giá trị hàng đã thanh toán trừ số tiền hoàn tất phát sinh theo từng ngày". Đây là **dòng giá trị bán và hoàn theo ngày sự kiện**, **không phải** chỉ tiêu doanh thu kế toán:

~~~sql
WITH daily_movements AS (
    SELECT tenant_id,
           paid_date AS business_date,
           SUM(gross_amount_vnd) AS amount_vnd
    FROM mart.fact_paid_order_line
    WHERE tenant_id = :tenant_id
      AND paid_date >= DATE '2026-10-01'
      AND paid_date <  DATE '2026-11-01'
    GROUP BY tenant_id, paid_date

    UNION ALL

    SELECT tenant_id,
           refunded_date AS business_date,
           -SUM(refund_amount_vnd) AS amount_vnd
    FROM mart.fact_completed_refund_line
    WHERE tenant_id = :tenant_id
      AND refunded_date >= DATE '2026-10-01'
      AND refunded_date <  DATE '2026-11-01'
    GROUP BY tenant_id, refunded_date
)
SELECT business_date,
       SUM(amount_vnd) AS net_paid_minus_refunded_vnd
FROM daily_movements
GROUP BY business_date
ORDER BY business_date;
~~~

Trong ví dụ này, khoản bán ngày 31/10 và hoàn ngày 02/11 được ghi ở **hai ngày khác nhau**. Nếu câu hỏi lại là "giá trị ròng cuối cùng của các đơn phát sinh trong tháng 10", cần **cohort theo ngày bán** và nối khoản hoàn với dòng bán gốc — đây là metric khác, không thể sửa bằng cách đổi tên cột. Ngoài ra, truy vấn chỉ trả về **những ngày có phát sinh**; muốn hiển thị cả ngày không có giao dịch, JOIN với dim_date hoặc chuỗi ngày đầy đủ rồi COALESCE về 0.

### Các lỗi GROUP BY thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| JOIN fact bán với mọi payment attempt của đơn | Một dòng bán nhân lên nhiều lần | Tạo fact theo grain có chủ đích; tổng hợp/khử trùng lặp nguồn trước |
| COUNT(*) trên fact dòng hàng rồi đặt tên "số đơn" | Đếm số dòng, không đếm đơn | COUNT(DISTINCT order_id) theo phạm vi hoặc fact_order |
| SUM DISTINCT(amount) để sửa đếm trùng | Các giao dịch khác nhau có cùng amount bị gộp sai | Chọn đúng khóa/grain và xử lý phép JOIN |
| JOIN dimension SCD2 bằng productId không có thời điểm | Một fact ghép nhiều phiên bản sản phẩm | Liên kết fact với product_key đúng phiên bản |
| Dùng giá hiện tại để tính giá trị bán quá khứ | Lịch sử đổi nghĩa khi Catalog sửa giá | Dùng snapshot giá ở giao dịch |
| SUM tồn kho cuối ngày qua cả tháng | Cộng những snapshot lặp qua thời gian | Lấy giá trị cuối kỳ, bình quân ngày có định nghĩa, hoặc metric phù hợp |
| AVG của tỷ lệ theo ngày không trọng số | Tỷ lệ tổng sai nếu mẫu số khác nhau | Cộng tử số/mẫu số trước, rồi chia |

## 9. Kiến trúc đưa dữ liệu từ OLTP sang OLAP

Một kiến trúc thông dụng tách đường ghi có thẩm quyền khỏi đường phân tích:

~~~mermaid
flowchart LR
    U["Ứng dụng đặt hàng"] --> T[("OLTP DB<br/>Orders, Stock, Payments")]
    T --> X["Batch/CDC<br/>extract"]
    X --> Q["Raw/Staging<br/>đối soát và dedup"]
    Q --> M["Transform<br/>grains, SCD, metrics"]
    M --> W[("OLAP Store<br/>facts + dimensions")]
    W --> B["Dashboard / BI / SQL"]
    W --> A["Data quality & reconciliation"]
    A -.->|"đối chiếu chênh lệch"| Q
~~~

**Không có quy tắc chỉ được dùng một đường vận chuyển.** Các phương án gồm:

- **Batch ETL/ELT:** trích xuất và xử lý theo giờ/ngày, dễ vận hành nếu độ tươi dữ liệu không cần quá cao.
- **CDC (Change Data Capture):** đọc dòng thay đổi đã commit từ log hoặc cơ chế tương đương, hỗ trợ gần thời gian thực; cần hiểu định dạng, transaction boundary, thứ tự và thao tác xóa.
- **Outbox/domain events:** cung cấp các sự thật nghiệp vụ như OrderPaid, RefundCompleted thay vì chỉ row-level UPDATE; hợp đồng rõ nhưng phải đảm bảo không bỏ sót nghiệp vụ cần phân tích.
- **Read replica:** giảm tải một số truy vấn đọc khỏi máy ghi OLTP nhưng thường vẫn giữ cùng lược đồ/hình thức lưu trữ; có replication lag và không tự giải quyết star schema, lịch sử dimension hay metric.
- **Materialized view/summary table trong cùng DB:** tốt cho quy mô và SLA phù hợp; cần xử lý refresh, cập nhật và cạnh tranh tài nguyên.

Việc kết hợp batch snapshot ban đầu với CDC sau đó cần một **điểm cắt nhất quán**. Nếu snapshot toàn bộ bảng và đồng thời đọc log mà không có high-watermark hoặc giao thức chuyển tiếp, pipeline có thể làm mất hoặc nhân đôi những thay đổi nằm đúng ranh giới hai pha.

## 10. Độ tươi dữ liệu, tính nhất quán và ngưỡng chấp nhận

Một yêu cầu báo cáo phải nói rõ **dữ liệu mới đến thời điểm nào**, không chỉ nói "real-time":

| Nhu cầu | Ví dụ SLA về độ tươi (minh họa) | Kiến trúc ứng viên |
| --- | --- | --- |
| Đóng sổ tháng | Chốt chính thức theo kỳ, có đối soát và phê duyệt | Batch versioned, snapshot/bản chốt |
| Dashboard điều hành | Trễ khoảng 15–60 phút nếu được chấp nhận | Micro-batch hoặc CDC |
| Theo dõi chiến dịch | Trễ vài giây/phút, cần ghi rõ mức chấp nhận | Stream/CDC với projection và monitoring |
| Kiểm tra số dư dùng để xác nhận giao dịch | Phải đúng tại điểm cấp quyền, không dựa bản sao trễ | OLTP/source of truth và command nguyên tử |

Các khoảng trễ trong bảng là **ví dụ** để hỏi lại người sở hữu nghiệp vụ, không phải tiêu chuẩn bắt buộc. Độ tươi là thời gian giữa sự kiện nguồn và việc số liệu sẵn có trong dashboard; **độ đúng** là liệu khi nói "dữ liệu đến 10:00" thì tập dữ liệu thực sự bao phủ chính xác phạm vi đó.

Một dashboard rất nhanh nhưng âm thầm thiếu giao dịch vừa đến, thiếu bản hoàn tiền hoặc dùng định nghĩa metric sai **không đáng tin hơn** dashboard trễ 15 phút nhưng có watermark và đối soát rõ ràng.

### Event time, processing time và business date

- **Event time:** khi nghiệp vụ thực sự xảy ra (ví dụ paid_at).
- **Processing time:** khi pipeline nhận và xử lý bản ghi.
- **Business date:** ngày phân loại theo lịch/múi giờ/phạm vi báo cáo.

Một giao dịch trả tiền lúc 23:59 theo giờ Việt Nam nhưng được CDC đưa tới warehouse lúc 00:05 ngày sau vẫn thuộc **ngày thanh toán trước** nếu KPI nhóm theo paid_at. Nếu giao dịch được đồng bộ muộn hơn sau khi báo cáo đã phát hành, hệ thống cần chính sách **sửa kết quả kỳ cũ** hoặc đóng băng theo kỳ và ghi điều chỉnh.

## 11. Kiểm soát chất lượng và idempotency trong pipeline

Một ETL/CDC chạy lại là chuyện bình thường. Không được để mỗi lần chạy lại làm doanh số tăng thêm vì nhân đôi dòng.

### Các kiểm tra cần có

| Tầng | Kiểm tra | Hậu quả nếu bỏ qua |
| --- | --- | --- |
| Raw ingestion | Có source ID, sequence/LSN/offset, không mất log, schema hợp lệ | Thiếu dữ liệu hoặc không tái hiện được |
| Staging | Khử bản sao theo khóa và version; hiểu tombstone/delete | Dòng bị đếm hai lần hoặc không xóa/cập nhật đúng |
| Transform | Grain rõ, snapshot giá, mapping dimension SCD, timezone | Nhóm sai danh mục hoặc sai ngày |
| Fact load | UNIQUE/merge theo khóa grain; retry không tạo dòng mới | SUM doanh số tăng khi pipeline retry |
| Serving | Watermark, snapshot/version, data lineage | Người xem tưởng dữ liệu đã đầy đủ khi chưa |
| Reconciliation | Tổng và số lượng theo kỳ/tenant đối chiếu với nguồn đã chốt | Chênh lệch kéo dài mà không được phát hiện |

**Idempotency** tại OLAP có thể được bảo vệ bởi khóa tự nhiên và thao tác UPSERT/MERGE với phiên bản, nhưng không nên mặc định mọi fact là insert-only. Đơn hàng bị hủy, hoàn tiền, cập nhật lịch sử hoặc sửa lỗi sau chốt có thể tạo thay đổi hợp lệ; phải chọn giữa cập nhật fact, ghi **dòng điều chỉnh** hoặc xây lại một phân vùng/kỳ theo chính sách metric.

### Sự kiện đến muộn và dimension đến muộn

Ví dụ sự kiện OrderPaid đến warehouse trước thông tin ProductVersion tại thời điểm bán:

- **Cách 1:** tạm đưa fact vào staging, chờ dimension đúng phiên bản; có giới hạn thời gian và cảnh báo.
- **Cách 2:** gắn vào một dimension "unknown/late arriving", rồi cập nhật lại khóa khi dữ liệu nguồn đến; không để báo cáo chính thức hiểu "unknown" như một danh mục thật.
- **Cách 3:** tạo placeholder dimension có nguồn/giá trị rõ và cập nhật sau, nếu kiến trúc warehouse cho phép.

Khi event trễ so với ngày nghiệp vụ, chỉ thay đổi bản ghi của **kỳ liên quan** theo quy tắc, không lấy ngày ingest thay cho ngày sự kiện. Một watermark hoặc "data complete through" phải cho biết phạm vi đã được xử lý đến đâu; không thể chỉ dùng thời điểm batch mới nhất mà bỏ qua nguồn chậm.

### Kiểm thử đối soát

Giả định sau khi chốt ngày D, OLTP có 10.000 dòng bán đã PAID; warehouse phải có **10.000 khóa dòng bán duy nhất** cho ngày đó trong cùng phạm vi và cùng phiên bản quy tắc. Tiếp theo đối chiếu SUM(gross_amount_vnd), số đơn, số lượng, phân bố trạng thái và số refund theo ngày. Nếu có chênh lệch, phải phân loại do độ trễ, thiếu sự kiện, mapping lỗi, chính sách điều chỉnh hay logic metric — không chỉ sửa dashboard để số trông khớp.

## 12. Hiệu năng: tối ưu đúng loại truy vấn

### OLTP: tối ưu đường ghi và truy vấn điểm

- Dùng PK/UNIQUE/FK/CHECK bảo vệ danh tính, toàn vẹn và quy tắc cục bộ.
- Thiết kế chỉ mục theo đường truy vấn nóng, như tìm Order theo orderId hoặc Customer theo tenant.
- Giữ transaction ngắn; tránh truy vấn nhóm hàng triệu dòng, gửi email hoặc gọi HTTP bên ngoài trong khi đang giữ khóa.
- Dùng optimistic locking hoặc UPDATE có điều kiện cho dữ liệu cạnh tranh; kiểm tra số hàng được cập nhật.
- Theo dõi p95/p99 độ trễ, deadlock, lock wait, transaction rollback và thông lượng ghi.

### OLAP: tối ưu quét, lọc và tổng hợp

- Giữ **grain** cố định, measure rõ ý nghĩa và dimension phù hợp câu hỏi.
- Đặt dữ liệu thường lọc chung gần nhau bằng partition/clustering/sort key theo công nghệ cụ thể; tránh phân vùng quá nhỏ gây tăng metadata/chi phí vận hành.
- Ưu tiên đọc đúng cột cần thiết khi engine lưu trữ cột hỗ trợ pruning và compression.
- Có thể làm bảng tổng hợp theo ngày/danh mục nếu dashboard gọi liên tục; phải biết cách refresh khi late data/điều chỉnh xuất hiện.
- Kiểm tra query plan, scan volume, memory spill, độ trễ truy vấn, chi phí vận hành và mức phân phối tải.

**Phân biệt loại workload không có nghĩa mọi OLAP query đều là full table scan** hay mọi OLTP query đều đọc đúng một hàng. Một hệ OLTP có thể tìm danh sách hàng trăm đơn, và một OLAP cũng có thể tra một chỉ tiêu tổng hợp đã materialize rất nhanh. Đặc điểm quyết định vẫn là **mục tiêu và cách dữ liệu được tổ chức/khai thác chủ đạo**.

## 13. Có phải luôn cần hai database?

Không. Một dự án mới với vài nghìn đơn/ngày và một báo cáo theo ngày có thể bắt đầu bằng:

1. Các bảng OLTP được thiết kế đúng transaction và bất biến.
2. Vài truy vấn tổng hợp được kiểm soát, chạy ngoài giờ cao điểm nếu cần.
3. Materialized view hoặc bảng tổng hợp có lịch refresh và kiểm tra chênh lệch.
4. Tách workload khi dữ liệu, người dùng hoặc yêu cầu độ tươi khiến hệ thống bị ảnh hưởng.

Đối chiếu các phương án:

| Phương án | Khi có thể phù hợp | Chi phí và giới hạn |
| --- | --- | --- |
| **Cùng OLTP DB** | Dataset nhỏ, báo cáo ít, kỳ vọng latency hợp lý | Tranh CPU/I/O với giao dịch, khó giữ lịch sử dimension đúng |
| **Read replica** | Nhiều truy vấn đọc trực tiếp theo cùng schema | Replica lag, schema vẫn thiên OLTP, chưa phải data warehouse |
| **Materialized view / bảng summary** | KPI ổn định, số chiều hữu hạn | Refresh và điều chỉnh late data, chi phí lưu trữ thêm |
| **Warehouse/lakehouse độc lập** | Nhiều nguồn, dữ liệu lớn, lịch sử dài, nhiều chiều phân tích | Pipeline, governance, chất lượng, chi phí và độ trễ |
| **HTAP (hybrid transactional/analytical processing)** | Cần giao dịch và phân tích gần nhau, sản phẩm có hỗ trợ phù hợp | Không tự xóa bỏ trade-off isolation, tài nguyên hay mô hình metric |

**Không chọn công nghệ chỉ vì sơ đồ có nhãn OLTP hoặc OLAP.** Lấy yêu cầu về tính đúng, độ tươi, thời gian phản hồi, chi phí và cách vận hành làm đầu vào. Có hệ thống cần warehouse lớn; có hệ thống chỉ cần bảng tổng hợp đúng cách.

## 14. Tránh nhầm lẫn về quyền sở hữu và nguồn dữ liệu

Một fact phân tích là **bản diễn giải dữ liệu đã xảy ra** chứ không mặc nhiên là nguồn cho phép một command vận hành. Các aggregate OLTP vẫn chịu trách nhiệm bất biến:

- Inventory kiểm soát không cấp vượt tồn tại điểm giữ hàng.
- Payment kiểm soát trạng thái thanh toán và idempotency của lệnh thu tiền.
- Order kiểm soát trạng thái đơn và snapshot giá đã cam kết.
- Warehouse làm rõ dữ liệu nào đã được nạp, thuộc khoảng thời gian nào và metric nào được tính.

Khi doanh nghiệp muốn dùng phân tích để quyết định có cấp khuyến mại cho khách, warehouse có thể tính **điểm phân khúc** và công bố kết quả có phiên bản. Nhưng tại lúc phát voucher hoặc trừ hạn mức, hệ thống giao dịch vẫn cần cơ chế kiểm tra quyền, hạn mức và trạng thái hiện hành thích hợp. Sự kiện "CustomerQualified" dựa trên phân tích không tự là quyền cấp không giới hạn.

### Quyền truy cập và dữ liệu cá nhân

Hệ phân tích thường tập hợp nhiều nguồn nên rủi ro lộ dữ liệu cũng tăng:

- Không sao chép email/số điện thoại/địa chỉ đầy đủ nếu chỉ cần customerId và phân khúc.
- Áp dụng phân quyền theo tenant, chi nhánh, phòng ban hoặc mức nhạy cảm tương ứng.
- Dùng pseudonymization/ẩn danh khi mục đích phân tích cho phép; tuân thủ chính sách xóa và thời hạn lưu.
- Ghi rõ nguồn dữ liệu, cách biến đổi, phiên bản metric và ai được quyền công bố báo cáo.
- Kiểm tra việc dữ liệu đã xóa/sửa theo nguồn có được phản ánh trong bản sao và các bản tổng hợp có liên quan hay không.

Một bảng fact truy vấn nhanh nhưng không bảo vệ phạm vi truy cập hoặc không giải thích được nguồn gốc chưa phải mô hình phân tích đạt yêu cầu.

## 15. Quy trình chuyển yêu cầu thành quyết định OLTP/OLAP

Khi nhận một yêu cầu dữ liệu mới, hãy theo trình tự:

1. **Ghi câu hỏi nguyên văn:** đây là quyết định trên một đối tượng ngay bây giờ hay so sánh một tập dữ liệu lịch sử?
2. **Xác định hành động:** command thay đổi trạng thái, truy vấn điểm, cảnh báo vận hành, dashboard phân tích hay chốt số kế toán?
3. **Nêu cam kết:** bất biến sau commit, độ tươi cho phép, phạm vi lịch sử, thời gian phản hồi và số lượng truy vấn đồng thời.
4. **Nếu có thay đổi nghiệp vụ:** xác định aggregate/root có quyền, khóa, constraint, isolation và idempotency.
5. **Nếu có phân tích:** xác định **grain**, fact, dimension, snapshot/SCD, định nghĩa measure, ngày nghiệp vụ và quy tắc lọc trạng thái.
6. **Xác định nguồn:** bảng giao dịch, domain event, thanh toán, hoàn tiền; điều gì xảy ra khi nguồn thay đổi hoặc thiếu?
7. **Chọn cách cung cấp:** truy vấn trực tiếp, replica, summary, batch ETL, CDC, warehouse hay HTAP dựa trên yêu cầu thực tế.
8. **Thiết kế kiểm chứng:** test transaction/race cho OLTP; test đếm trùng, đối soát, late data và KPI cho OLAP.
9. **Công bố hợp đồng:** giải thích "số liệu đến khi nào", quy tắc tính, người sở hữu metric, nguồn và phiên bản.

### Bảng chuyển một yêu cầu thành thiết kế

| Đề bài | Phân loại chính | Mô hình/cơ chế gợi ý |
| --- | --- | --- |
| "Đặt thêm 3 sản phẩm nếu kho còn" | OLTP | Command giữ hàng, UPDATE có điều kiện, transaction |
| "Hiện trạng thanh toán của đơn X" | OLTP/read vận hành | Order/Payment source of truth, đọc theo khóa |
| "Giá trị đã bán theo nhóm sản phẩm mỗi tuần" | OLAP | Fact ở grain dòng bán, dim sản phẩm phiên bản, calendar |
| "Tỷ lệ khách mua lại theo quý" | OLAP | Customer/order fact, định nghĩa cohort và cửa sổ |
| "Cảnh báo gian lận trước khi chấp nhận giao dịch" | Quyết định vận hành dùng dữ liệu phân tích | Điểm/rule có nguồn và độ tươi xác định; command vẫn cần kiểm soát nhất quán |
| "Dòng tiền hoàn theo ngày trong báo cáo điều hành" | OLAP | Fact hoàn, ngày hoàn tất, quy tắc tiền tệ và đối soát |

## 16. Bài tập thực hành: nền tảng học trực tuyến

**Bối cảnh:** Một nền tảng bán khóa học online có Course, Student, Enrollment, Payment và Refund. Mỗi lớp giới hạn 50 chỗ. Học viên đăng ký, giữ chỗ 10 phút, thanh toán rồi được xác nhận. Bộ phận đào tạo muốn xem số đăng ký, tỷ lệ chuyển đổi từ giữ chỗ sang xác nhận và doanh số theo giảng viên trong 6 tháng. Một khóa học có thể được chuyển sang giảng viên khác sau khi đã mở bán.

### Yêu cầu

1. Phân loại những câu hỏi nào là OLTP và OLAP: giữ chỗ cuối cùng; tra trạng thái đăng ký; tỷ lệ chuyển đổi theo tuần; doanh số theo giảng viên; hoàn tiền cho một học viên.
2. Viết **hai bất biến** phải được bảo vệ trong transaction khi giữ/xác nhận chỗ. Chỉ ra ai sở hữu và cách xử lý hai request lấy chỗ cuối.
3. Thiết kế grain cho fact đăng ký, fact thanh toán và fact hoàn. Có thể dùng **một bảng fact** cho cả ba mà không nhầm measure không?
4. Khi giảng viên phụ trách Course thay đổi, báo cáo "theo giảng viên lúc bán" khác "theo giảng viên hiện tại" ra sao? Đề xuất giải pháp snapshot hoặc dimension SCD2.
5. Một học viên thanh toán bằng hai payment attempts, lần đầu thất bại và lần sau thành công. Nếu JOIN Enrollment với cả hai attempts rồi SUM giá khóa học, kết quả bị gì?
6. Giả sử ETL chạy mỗi giờ. Báo cáo lúc 10:05 có thể thiếu thanh toán lúc 10:01 không? Cần công bố watermark/độ tươi như thế nào?
7. Đề xuất một phép đối soát số đơn/giá trị thanh toán và một phép thử idempotency khi chạy lại pipeline.

### Một hướng giải

- **OLTP:** giữ chỗ, thay trạng thái đăng ký, kiểm tra Payment/Refund và tra một Enrollment hiện hành. **OLAP:** tỷ lệ chuyển đổi theo tuần, doanh số theo giảng viên, số lần giữ chỗ theo phân khúc.
- Giới hạn 50 chỗ cần được cấp bởi một nguồn chỗ có thẩm quyền; cùng học viên không có hai Enrollment hoạt động nếu chính sách cấm. Dùng UPDATE có điều kiện/khóa hoặc giao thức đặt giữ nguyên tử, không đọc số chỗ từ dashboard trễ.
- Có thể có fact_enrollment_event ở grain **một sự kiện chuyển trạng thái**, fact_successful_payment ở grain **một khoản thanh toán thành công**, fact_completed_refund ở grain **một khoản hoàn hoàn tất**. Nếu chọn fact tích hợp, mỗi hàng phải mang eventType và measure có ý nghĩa rõ, tránh cộng một PaymentAttempt thất bại như doanh số.
- Báo cáo "giảng viên lúc bán" cần snapshot hoặc dimension có hiệu lực theo thời gian; "giảng viên hiện tại" có thể JOIN sang danh sách hiện hành, nhưng hai kết quả không nên bị coi là cùng KPI.
- JOIN với nhiều attempts sẽ nhân số tiền nếu không giới hạn/tổng hợp theo grain phù hợp. Chỉ thanh toán thành công theo hợp đồng ghi nhận mới đi vào measure giá trị đã thanh toán.
- Nếu ETL chạy theo giờ, bảng đến 10:05 có thể chỉ chứa dữ liệu đã xử lý đến mốc trước đó. Nên hiển thị "data complete through" và kiểm tra sự kiện đến muộn.
- Retry cùng batch không được làm tăng số bản ghi theo khóa nghiệp vụ. Đối soát COUNT(DISTINCT paymentId) và SUM(amount) giữa nguồn thanh toán đã chốt với warehouse trong cùng tenant, cùng khoảng thời gian/tiền tệ và cùng chính sách trạng thái.

**Thử thách mở rộng:** Tạo hai dashboard, một hiển thị "số người đang giữ chỗ ngay lúc này" và một hiển thị "tỷ lệ chuyển đổi giữ chỗ → xác nhận trong 30 ngày". Vì sao dashboard đầu có thể cần đọc nguồn vận hành hoặc projection rất tươi, trong khi dashboard thứ hai cần dữ liệu lịch sử sự kiện và định nghĩa cohort chặt chẽ?

## 17. Checklist kiểm tra mô hình dữ liệu

- Yêu cầu là một **command phải bảo vệ bất biến** hay **truy vấn/metric tổng hợp**? Có cả hai thành phần không?
- Hệ giao dịch có khóa, transaction, quyền ghi, idempotency và concurrency control theo bất biến không?
- KPI phân tích có định nghĩa **grain, measure, dimension, thời điểm sự kiện và trạng thái hợp lệ** không?
- Giá, tiền tệ, danh mục, khách hàng và các thuộc tính biến đổi theo thời gian cần snapshot hoặc SCD như thế nào?
- Có nguy cơ JOIN nhân bản hàng, dùng COUNT(*) sai grain hoặc cộng tỷ lệ/snapshot sai cách không?
- Nếu nhiều nguồn tham gia, có quy tắc **đồng bộ, retry, late data, khử trùng lặp và đối soát** không?
- Mức độ tươi, watermark, SLA truy vấn và tác động lên hệ giao dịch có được nêu bằng số đo không?
- Chỉ mục, phân vùng, materialized view, cột và lịch sử đã được chọn theo workload thực tế chưa?
- Báo cáo có bảo vệ quyền truy cập, phạm vi tenant, dữ liệu cá nhân và giải thích được nguồn gốc số liệu không?
- Kiến trúc một DB, replica, warehouse hoặc HTAP đã được lựa chọn từ yêu cầu, không chỉ vì xu hướng công nghệ chưa?

**Kết luận:** **OLTP** tối ưu cho việc thực hiện và bảo vệ các thay đổi nghiệp vụ có thẩm quyền; **OLAP** tối ưu cho việc diễn giải, tổng hợp và so sánh dữ liệu theo những câu hỏi có định nghĩa đo lường rõ ràng. Hai cách xử lý có thể cùng tồn tại trong một công nghệ hoặc được tách thành những hệ thống khác nhau. Nền tảng của quyết định không phải tên sản phẩm, mà là **bất biến và transaction ở đường ghi**, **grain và metric ở đường phân tích**, cùng độ tươi, chất lượng, tính truy vết và chi phí vận hành mà doanh nghiệp thực sự yêu cầu.
