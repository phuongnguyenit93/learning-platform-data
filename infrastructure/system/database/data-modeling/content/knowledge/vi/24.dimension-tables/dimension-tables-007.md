# Định danh giao dịch làm chiều suy biến (degenerate dimension)

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, một mô hình dữ liệu tốt phải chuyển câu hỏi nghiệp vụ thành cấu trúc rõ nghĩa, có khóa, ràng buộc và khả năng kiểm chứng. Với mô hình phân tích, ta thường tách **bảng dữ kiện** (*fact table*) chứa sự kiện/số đo và **bảng chiều** (*dimension table*) chứa ngữ cảnh mô tả. Tuy nhiên, không phải thuộc tính dùng để lọc hoặc nhóm dữ liệu đều cần một bảng chiều riêng.

**Chiều suy biến** (*degenerate dimension*, viết tắt **DD**) là trường hợp quan trọng: **một định danh giao dịch hoặc tài liệu nghiệp vụ được giữ trực tiếp trong bảng fact để lọc, nhóm, đếm hoặc truy vết, dù không có bảng dimension riêng chỉ chứa định danh ấy**.

Sau bài học, bạn có thể:

1. Giải thích chiều suy biến, nhận diện `order_number`, `invoice_number`, `ticket_number` và các định danh giao dịch tương tự.
2. Phân biệt **định danh giao dịch** với **khóa của một dòng fact**, **surrogate key**, **khóa ngoại tới dimension** và **dimension thật sự có thuộc tính mô tả**.
3. Quyết định khi nào giữ định danh ngay trong fact, khi nào cần fact ở cấp chứng từ hoặc một dimension có ý nghĩa riêng.
4. Thiết kế star schema và câu SQL để **drill-through**, `COUNT(DISTINCT)`, tổng hợp tiền mà không nhân bản dữ liệu.
5. Xử lý định danh chỉ duy nhất theo tenant/cửa hàng/năm, định danh đổi theo thời gian, sự kiện nạp trùng và thông tin nhạy cảm.
6. Đánh giá ảnh hưởng vật lý đến chỉ mục, phân vùng, dung lượng, quyền truy cập và khả năng mở rộng.

## 1. Tình huống mở đầu: số đơn hàng nằm ở đâu trong star schema?

Giả sử doanh nghiệp muốn trả lời:

- Tổng giá trị hàng đã đặt theo tháng và danh mục sản phẩm?
- Một đơn hàng có những dòng nào?
- Có bao nhiêu **đơn hàng** (khác với bao nhiêu **dòng hàng**) trong kỳ?
- Khi khách báo “đơn `ORD-101` sai giá”, có thể tìm ngay các dòng fact để đối soát?

Quy trình nghiệp vụ là **xác nhận đơn hàng**. Một đơn có nhiều dòng sản phẩm, do đó chọn grain:

~~~text
fact_order_lines:
    MỘT DÒNG = một dòng hàng (order_number, line_no)
    của một đơn được xác nhận, trong phạm vi tenant xác định.
~~~

Bảng fact minh họa:

| tenant_id | order_number | line_no | date_key | product_key | quantity | booked_amount |
|---|---|---:|---|---:|---:|---:|
| T01 | ORD-101 | 1 | 2026-11-01 | 501 | 2 | 200.000 |
| T01 | ORD-101 | 2 | 2026-11-01 | 502 | 1 | 50.000 |
| T01 | ORD-102 | 1 | 2026-11-02 | 501 | 1 | 80.000 |
| T02 | ORD-101 | 1 | 2026-11-02 | 503 | 1 | 70.000 |

Giả định các số tiền ở cùng đơn vị VND và `order_number` **chỉ duy nhất trong một tenant**. Như vậy:

- Có **4 dòng fact**.
- Có **3 đơn hàng phân biệt theo `(tenant_id, order_number)`**.
- Tổng `booked_amount` là **400.000 VND**.
- Đơn `ORD-101` của `T01` có **2 dòng hàng**; cũng có `ORD-101` thuộc `T02` nhưng đó là **đơn khác**.

Trong cấu trúc này, `date_key` và `product_key` có thể tham chiếu các dimension mô tả ngày và sản phẩm. Còn `order_number` được **giữ trực tiếp trong fact** để xác định và truy vết chứng từ. Nếu không có thuộc tính mô tả độc lập nào cần đặt ở bảng `dim_order`, `order_number` chính là một **degenerate dimension**.

## 2. Định nghĩa và bản chất của degenerate dimension

Một chiều suy biến có các đặc điểm:

1. **Có ngữ nghĩa định danh nghiệp vụ**: mã đơn, số hóa đơn, số yêu cầu hỗ trợ, mã phiếu vận chuyển, mã giao dịch.
2. **Có giá trị phân tích**: dùng để lọc, nhóm, drill-through, đếm chứng từ và đối soát hệ thống nguồn.
3. **Nằm trong fact**: không cần tạo một dimension chỉ để lưu một dòng `(order_key, order_number)` rồi JOIN lại.
4. **Thường có độ phân biệt cao** (*high cardinality*): mỗi chứng từ có mã riêng trong phạm vi của nó.
5. **Không nhất thiết là khóa duy nhất của một dòng fact**: số đơn có thể lặp trên nhiều dòng hàng; số hóa đơn lặp trên nhiều dòng hóa đơn.

Nói ngắn gọn:

> **Chiều suy biến là thuộc tính mang tính dimension về vai trò lọc/nhóm/truy vết, nhưng được lưu ngay trong bảng fact vì không cần bảng dimension mô tả độc lập.**

Thuật ngữ *degenerate* **không có nghĩa dữ liệu kém chất lượng**. Nó mô tả một mẫu thiết kế có chủ đích trong mô hình chiều (*dimensional modeling*).

### Ví dụ phổ biến

| Quy trình / fact | Định danh có thể là DD | Grain của fact | Công dụng |
|---|---|---|---|
| Dòng đơn hàng | `order_number` | Một dòng hàng của một đơn | Tra cứu đơn, đếm đơn phân biệt |
| Dòng hóa đơn | `invoice_number` | Một dòng hóa đơn | Drill-through từ báo cáo tới hóa đơn |
| Giao dịch thanh toán | `payment_transaction_id` | Một sự kiện thanh toán | Đối soát và chống nạp trùng |
| Yêu cầu hỗ trợ | `ticket_number` | Một sự kiện hoặc trạng thái ticket theo grain đã chọn | Tra cứu toàn bộ sự kiện của một ticket |
| Dòng bưu gửi | `shipment_number` | Một kiện hoặc một dòng vận chuyển | Nhóm các dòng thuộc cùng bưu gửi |
| Dòng biên lai | `receipt_number` | Một dòng hàng trên biên lai | Phân tích giỏ hàng, kiểm tra biên lai |

**Cần xác nhận phạm vi định danh:** `receipt_number = 0001` có thể xuất hiện ở nhiều cửa hàng hoặc nhiều năm. Trong trường hợp đó, **mã đầy đủ** dùng để truy vết là một tổ hợp như `(store_id, fiscal_year, receipt_number)`, không phải `receipt_number` đơn lẻ.

## 3. Degenerate dimension khác gì dimension thông thường?

Một **dimension thông thường** có thể chứa:

~~~text
dim_product(
    product_key,
    product_id,
    product_name,
    category_name,
    brand_name
)
~~~

`product_key` trong fact tham chiếu một bản ghi mô tả sản phẩm. Những thuộc tính `category_name`, `brand_name` được dùng phân tích theo cấp nhóm và đôi khi cần lịch sử phiên bản (*SCD Type 2*).

Nếu ta tạo:

~~~text
dim_order(
    order_key,
    order_number
)
~~~

chỉ để thay `order_number` trong fact bằng `order_key`, ta đã thêm **một bảng và một phép JOIN** nhưng chưa nhận được thuộc tính mô tả nghiệp vụ nào. Trong trường hợp này, giữ `order_number` trực tiếp trong fact là lựa chọn đơn giản, dễ drill-through.

### So sánh

| Tiêu chí | Dimension mô tả | Degenerate dimension |
|---|---|---|
| Ví dụ | Sản phẩm, khách hàng, cửa hàng, ngày | Mã đơn, số hóa đơn, số ticket |
| Nằm ở đâu? | Bảng `dim_*` riêng | Cột trực tiếp ở `fact_*` |
| Vai trò | Thuộc tính phân tích, phân cấp, mô tả | Định danh, nhóm chứng từ, truy vết |
| Khóa trong fact | Thường là khóa ngoại `product_key`, `customer_key` | Giá trị định danh như `order_number` |
| Lịch sử thuộc tính | Có thể cần Type 1/Type 2 | Bản thân mã giao dịch thường được giữ bất biến; lịch sử mô tả thuộc đối tượng/quy trình khác |
| Cardinality | Từ nhỏ đến lớn | Thường rất cao |
| Có cần bảng riêng? | Có khi thực sự có thông tin chiều cần quản trị | Không, nếu định danh đứng một mình và không có lý do khác để tách |

**Không có quy tắc “định danh dài thì phải làm dimension”.** Việc tách bảng phải có lý do về ngữ nghĩa, ràng buộc hoặc workload thực tế.

## 4. Phân biệt ba loại khóa rất dễ nhầm

Trong thiết kế dữ liệu, các khái niệm sau có thể xuất hiện cùng lúc:

| Khái niệm | Ví dụ | Câu hỏi nó giải quyết |
|---|---|---|
| **Business document ID / DD** | `order_number = 'ORD-101'` | Đây là đơn nào trong nghiệp vụ? |
| **Khóa nghiệp vụ của dòng fact** | `(tenant_id, order_number, line_no)` | Dòng fact này có duy nhất theo grain không? |
| **Surrogate key của dimension** | `product_key = 501` | Fact tham chiếu tới bản ghi/phiên bản dimension nào? |
| **Surrogate key của fact (tùy chọn)** | `fact_row_key = 1000123` | Có cần ID kỹ thuật riêng cho thao tác nạp, lưu hoặc tham chiếu không? |
| **Khóa nguồn OLTP** | `orders.id = 87342` | Nguồn giao dịch nhận diện bản ghi bằng gì? |

Các khóa này **có thể trùng giá trị hoặc được ánh xạ với nhau**, nhưng không nên mặc nhiên coi chúng cùng một vai trò.

### Ví dụ: một order number xuất hiện nhiều lần là đúng

~~~text
(T01, ORD-101, line_no=1, product=P1)
(T01, ORD-101, line_no=2, product=P2)
~~~

Do grain là **dòng hàng**, `(T01,ORD-101)` lặp hai lần là **hợp lệ**. Quy tắc:

~~~text
(tenant_id, order_number, line_no) → thông tin dòng hàng tại xác nhận
~~~

có thể đúng, còn:

~~~text
(tenant_id, order_number) → product_key
~~~

thường **sai** vì một đơn có nhiều sản phẩm.

Không đặt `UNIQUE(tenant_id,order_number)` trên fact cấp dòng hàng. Điều đó chặn đơn có nhiều dòng. Ngược lại, **phải kiểm soát** `(tenant_id,order_number,line_no)` không trùng khi grain yêu cầu.

### DD không phải surrogate key

Một `order_number` do nguồn nghiệp vụ cấp có thể có cấu trúc như `HN-2026-000123`. Nó là một **business identifier**, không phải khóa thay thế tự sinh trong kho phân tích. Nếu fact còn có `fact_row_key` tự tăng, **hai cột cùng có thể tồn tại**: `fact_row_key` dùng kỹ thuật; `order_number` dùng nghiệp vụ và drill-through.

**Không dùng surrogate key để che vấn đề duplicate nghiệp vụ.** Có thêm `fact_row_key` vẫn phải kiểm tra một dòng nguồn có bị nạp hai lần không.

## 5. Thiết kế thực hành: đơn hàng, dòng hàng và các dimension thật

Giả sử công ty có nhiều tenant và một số `order_number` được sử dụng trùng nhau giữa tenant. Báo cáo ưu tiên:

- Giá trị hàng được đặt theo ngày, sản phẩm và phân khúc khách.
- Đếm số đơn theo tenant.
- Tìm các dòng của một đơn khi đối soát với nguồn.
- Đối chiếu tổng tiền mỗi đơn với dữ liệu cấp đơn.

### 5.1. Câu khai báo grain

~~~text
fact_order_lines:
    Một dòng cho một (tenant_id, order_number, line_no)
    tại thời điểm đơn đã xác nhận thành công.
~~~

`tenant_id` và `order_number` cùng tạo thành **định danh chứng từ trong phạm vi nghiệp vụ**. Nếu một nguồn tái sử dụng số đơn theo năm hoặc cửa hàng, phải đưa thêm `store_id`, `fiscal_year` hay khóa toàn cục khác theo quy tắc đã xác nhận.

### 5.2. Sơ đồ star schema

~~~mermaid
flowchart LR
    D["dim_date"] --> F["fact_order_lines"]
    C["dim_customer"] --> F
    P["dim_product"] --> F
    F --> O["DD: tenant_id + order_number"]
    F --> M["Measures: quantity, booked_amount"]
~~~

Trên hình, **`order_number` không nối tới `dim_order`**. Nó vẫn là cột dùng để drill-through và nhóm theo đơn. `date_key`, `customer_key`, `product_key` là các khóa tham chiếu tới **dimension mô tả**.

### 5.3. DDL PostgreSQL minh họa

Ví dụ đơn giản giả định:

- Một `order_number` không đổi sau khi đơn được xác nhận.
- `(tenant_id,order_number,line_no)` là khóa nghiệp vụ bất biến của sự kiện xác nhận dòng hàng.
- Đơn giá và chiết khấu trên dòng đã được chốt; tiền cùng một đồng tiền báo cáo trong các truy vấn cộng tiền.
- Lịch sử dimension phức tạp hơn (SCD Type 2) nếu cần sẽ được thiết kế riêng.

~~~sql
CREATE TABLE dim_date (
    date_key DATE PRIMARY KEY
);

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,
    product_code VARCHAR(40) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    category_name VARCHAR(100) NOT NULL
);

CREATE TABLE dim_customer (
    customer_key BIGINT PRIMARY KEY,
    customer_code VARCHAR(40) NOT NULL,
    customer_segment VARCHAR(100)
);

CREATE TABLE fact_order_lines (
    tenant_id VARCHAR(30) NOT NULL,
    order_number VARCHAR(60) NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),

    confirmed_date DATE NOT NULL REFERENCES dim_date(date_key),
    customer_key BIGINT NOT NULL REFERENCES dim_customer(customer_key),
    product_key BIGINT NOT NULL REFERENCES dim_product(product_key),

    quantity NUMERIC(18,3) NOT NULL CHECK (quantity > 0),
    unit_price_at_order NUMERIC(18,2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    line_discount_amount NUMERIC(18,2) NOT NULL
        CHECK (line_discount_amount >= 0),
    booked_amount NUMERIC(18,2) NOT NULL,

    PRIMARY KEY (tenant_id, order_number, line_no),
    CHECK (line_discount_amount <= quantity * unit_price_at_order),
    CHECK (
        booked_amount =
            quantity * unit_price_at_order - line_discount_amount
    )
);
~~~

Đây là **DDL minh họa cho một phạm vi đơn giản**. Khi dùng tiền nhiều loại, cần thêm `currency_code` và chính sách quy đổi; khi có điều chỉnh giá sau xác nhận, phải quyết định cập nhật snapshot hay ghi **sự kiện điều chỉnh riêng**. Việc dùng khóa ghép có ảnh hưởng đến kích thước chỉ mục; hãy đo trên hệ quản trị và workload cụ thể.

**Điểm cốt lõi:** không có `dim_order` chỉ chứa số đơn. Điều này **không** loại bỏ việc giữ bảng `orders` ở hệ OLTP hoặc `fact_orders` trong kho phân tích nếu có KPI thực sự ở cấp đơn.

## 6. Truy vấn DD: drill-through, tổng hợp và đếm chứng từ

### 6.1. Drill-through từ một KPI về dòng chứng từ

Giả sử dashboard báo giá trị hàng đặt bất thường của một đơn:

~~~sql
SELECT
    f.tenant_id,
    f.order_number,
    f.line_no,
    f.confirmed_date,
    p.product_code,
    p.product_name,
    f.quantity,
    f.unit_price_at_order,
    f.line_discount_amount,
    f.booked_amount
FROM fact_order_lines AS f
JOIN dim_product AS p
  ON p.product_key = f.product_key
WHERE f.tenant_id = 'T01'
  AND f.order_number = 'ORD-101'
ORDER BY f.line_no;
~~~

Ở đây người phân tích không cần JOIN thêm `dim_order` chỉ để biết số đơn. DD giúp **đi từ tổng hợp cấp tháng/kênh xuống định danh chứng từ**, rồi xem từng dòng.

Khi cần mở trang nguồn nghiệp vụ, ứng dụng có thể dùng bộ định danh đã xác nhận để tìm `orders`; không tự nối chuỗi URL từ dữ liệu chưa được xác thực hoặc giả định định danh nguồn luôn trùng mã hiển thị.

### 6.2. Tổng tiền theo đơn

~~~sql
SELECT
    tenant_id,
    order_number,
    SUM(booked_amount) AS booked_merchandise_amount,
    COUNT(*) AS line_count
FROM fact_order_lines
GROUP BY tenant_id, order_number
ORDER BY tenant_id, order_number;
~~~

Với dữ liệu ví dụ:

| tenant_id | order_number | booked_merchandise_amount | line_count |
|---|---|---:|---:|
| T01 | ORD-101 | 250.000 | 2 |
| T01 | ORD-102 | 80.000 | 1 |
| T02 | ORD-101 | 70.000 | 1 |

Nếu chỉ `GROUP BY order_number`, hai đơn `ORD-101` thuộc tenant khác nhau sẽ **bị gộp nhầm thành một**. DD phải chứa hoặc đi cùng **đầy đủ phạm vi định danh**.

### 6.3. Đếm số đơn, không đếm dòng

~~~sql
-- Đếm số dòng hàng:
SELECT COUNT(*) AS order_line_count
FROM fact_order_lines;

-- Đếm số đơn phân biệt trên mọi tenant (SQL tương đối di động):
WITH distinct_orders AS (
    SELECT DISTINCT tenant_id, order_number
    FROM fact_order_lines
)
SELECT COUNT(*) AS order_count
FROM distinct_orders;
~~~

Với 4 dòng minh họa, kết quả lần lượt là **4 dòng hàng** và **3 đơn hàng**.

Trong PostgreSQL, có thể dùng:

~~~sql
SELECT COUNT(DISTINCT (tenant_id, order_number)) AS order_count
FROM fact_order_lines;
~~~

Nếu hệ DBMS không hỗ trợ cú pháp DISTINCT cho một cặp như PostgreSQL, dùng cách `SELECT DISTINCT ...` trong CTE ở trên. **Không nối hai mã bằng chuỗi** không có escape rồi lấy `COUNT(DISTINCT)`; ví dụ `'A' || 'BC'` và `'AB' || 'C'` có thể cùng ra `'ABC'`.

### 6.4. Đếm theo thời gian và danh mục có bẫy

~~~sql
SELECT
    f.confirmed_date,
    p.category_name,
    COUNT(DISTINCT (f.tenant_id, f.order_number))
        AS orders_with_category,
    SUM(f.booked_amount) AS booked_amount
FROM fact_order_lines AS f
JOIN dim_product AS p
  ON p.product_key = f.product_key
GROUP BY f.confirmed_date, p.category_name;
~~~

`orders_with_category` nghĩa là **số đơn có ít nhất một dòng thuộc danh mục đó**. Nếu một đơn có cả “Sách” và “Phụ kiện”, nó được đếm trong **cả hai danh mục**. Vì vậy không được cộng các `orders_with_category` để lấy số đơn toàn công ty nếu các danh mục có thể cùng xuất hiện trong một đơn.

`booked_amount` có thể cộng theo danh mục **nếu mỗi dòng fact được gắn đúng một danh mục theo phiên bản dimension đã chọn**, cùng đơn vị tiền và không có JOIN nhân dòng. Với SCD Type 2, fact phải tham chiếu đúng phiên bản sản phẩm tại thời điểm giao dịch.

### 6.5. Đếm đơn không thể hiện trong fact có dòng hàng

Một fact dòng hàng **không chứa đơn chưa có dòng**. Nếu nghiệp vụ cần đếm **mọi đơn đã tạo**, kể cả đơn nháp hoặc đơn không có mặt hàng, `COUNT(DISTINCT order_number)` từ fact dòng hàng **không đủ**.

Khi đó có thể cần `fact_orders` ở grain **một đơn**, hoặc dữ liệu đơn từ nguồn với trạng thái phù hợp. Không được thay đổi định nghĩa “số đơn” chỉ vì fact dòng hàng là bảng đang có.

## 7. Khi nào cần fact cấp đơn hoặc dimension cấp đơn?

Đây là quyết định quan trọng. **Không cần dimension chỉ chứa số đơn** không có nghĩa tất cả thông tin cấp đơn phải đặt trên từng dòng hàng.

### Trường hợp A — Chỉ cần mã chứng từ để tra cứu

Nếu `order_number` được dùng để tìm dòng hàng, đếm số đơn và đối soát, nhưng **không có thuộc tính mô tả độc lập cần JOIN**, giữ nó làm DD trong `fact_order_lines` là hợp lý.

~~~text
fact_order_lines(
    tenant_id, order_number, line_no,
    date_key, product_key, customer_key,
    quantity, booked_amount
)
~~~

### Trường hợp B — Có số đo ở cấp đơn

Ví dụ tổng phí vận chuyển, chiết khấu toàn đơn hoặc số kiện giao thuộc **mức hạt đơn**:

~~~text
fact_orders(
    tenant_id, order_number,
    confirmed_date_key, customer_key, channel_key,
    order_shipping_fee, order_level_discount
)
~~~

Grain của `fact_orders`: **một đơn đã được xác nhận** trong phạm vi tenant, hoặc một đơn ở mốc xử lý khác theo định nghĩa đã chọn.

Trong `fact_order_lines`, grain vẫn là **một dòng hàng**. Không chép `order_shipping_fee` toàn đơn lên **mọi dòng** rồi `SUM`; đơn ba dòng với phí 30.000 sẽ bị tính thành 90.000 nếu cộng trực tiếp.

Nếu cần phân bổ phí cho từng sản phẩm, phải có quy tắc phân bổ rõ, đặt tên `allocated_shipping_fee` và kiểm tra:

\[
\sum_{\text{dòng của một đơn}}
\text{allocated\_shipping\_fee}
=\text{order\_shipping\_fee}.
\]

### Trường hợp C — Có thuộc tính mô tả nghiệp vụ cấp chứng từ

Nếu đơn có `order_type`, `sales_channel`, `promotion_group`, nhóm phê duyệt hoặc phân cấp mô tả cần dùng nhất quán, có nhiều lựa chọn:

- Nếu thuộc tính **phụ thuộc vào sự kiện cấp đơn**, xem xét đưa vào **fact cấp đơn**.
- Nếu thuộc tính ít và ổn định, có thể giữ một số thuộc tính như `order_type_key`, `channel_key` **trực tiếp trong fact dòng hàng** khi phụ thuộc cấp đơn đã được xác nhận, đồng thời cân nhắc chi phí lặp.
- Nếu có một **đối tượng đơn hàng** có tập mô tả đủ phong phú, vòng đời riêng và cần chia sẻ giữa nhiều fact, có thể cân nhắc một `dim_order` thực sự; nhưng phải đánh giá cardinality cao và chi phí ETL/JOIN.
- Nếu `status` thay đổi nhiều lần, cần chọn **trạng thái hiện hành**, **sự kiện trạng thái** hoặc **accumulating snapshot** theo câu hỏi. Không biến một dimension chỉ có số đơn thành nơi gộp mọi phiên bản trạng thái một cách thiếu grain.

**Không có quy tắc “cứ có thêm hai thuộc tính thì bắt buộc tạo `dim_order`”.** Chọn cấu trúc theo sự kiện nghiệp vụ, thuộc tính dùng để phân tích, lịch sử và workload.

### Bảng quyết định nhanh

| Câu hỏi | Nếu câu trả lời là “có” | Lựa chọn thường phù hợp |
|---|---|---|
| Chỉ cần mã để lọc, nhóm, drill-through? | Không cần thêm thuộc tính mô tả riêng | **DD trực tiếp trong fact** |
| Có số đo thật ở mức một đơn? | Số đo không thuộc một dòng hàng | **Fact cấp đơn** |
| Có bộ thuộc tính mô tả dùng chung và lịch sử riêng? | Cần quản trị nhiều thuộc tính của đơn | Cân nhắc **dimension cấp đơn** có lý do |
| Có nhiều lần trạng thái thay đổi cần đếm? | Một đơn có nhiều event | **Fact sự kiện trạng thái** |
| Cần theo dõi ngày đóng gói/giao/hoàn? | Nhiều mốc trong quy trình | **Accumulating snapshot** theo đúng grain |
| Muốn nhanh hơn khi tra mã? | Vấn đề có thể ở chỉ mục | Đo, tạo **index** trước khi thêm bảng không cần thiết |

## 8. Một định danh có thể có vai trò khác nhau trong các fact

**Cùng `order_number` không làm mọi bảng có cùng grain**.

~~~text
fact_order_lines:
    một dòng cho (tenant_id, order_number, line_no)

fact_payment_transactions:
    một dòng cho payment_transaction_id
    (mỗi giao dịch có thể gắn order_number)

fact_shipments:
    một dòng cho shipment_id
    (một đơn có thể có nhiều shipment)

fact_return_lines:
    một dòng cho return_id + return_line_no
    (một dòng hoàn có thể tham chiếu order_number/line_no)
~~~

Trong `fact_order_lines`, `order_number` là DD để nhóm dòng hàng. Trong `fact_payment_transactions`, nó có thể là **thuộc tính liên kết/giao dịch cha** được giữ trực tiếp để tra cứu đơn, nhưng khóa của fact thanh toán vẫn là `payment_transaction_id`. `shipment_number` có thể cũng là DD của fact vận chuyển.

### Bẫy JOIN nhiều fact trên cùng DD

Giả sử đơn `T01/ORD-101` có:

- **3 dòng hàng**.
- **2 giao dịch thanh toán**.
- **2 kiện hàng**.

Nếu JOIN cả ba fact chi tiết theo `(tenant_id,order_number)`, có thể có:

\[
3\times2\times2=12\text{ dòng}.
\]

Lúc đó:

- Mỗi dòng hàng bị lặp \(2\times2=4\) lần.
- Mỗi giao dịch thanh toán bị lặp \(3\times2=6\) lần.
- Mỗi kiện hàng bị lặp \(3\times2=6\) lần.

**Kết quả số tiền/số kiện có thể bị nhân lên**, dù DD dùng để JOIN là hoàn toàn hợp lệ.

### Cách xử lý đúng: tổng hợp về cùng một grain

~~~sql
WITH lines_by_order AS (
    SELECT tenant_id, order_number,
           SUM(booked_amount) AS booked_amount
    FROM fact_order_lines
    GROUP BY tenant_id, order_number
),
payments_by_order AS (
    SELECT tenant_id, order_number,
           SUM(payment_amount) AS captured_amount
    FROM fact_payment_transactions
    WHERE transaction_type = 'CAPTURE'
    GROUP BY tenant_id, order_number
)
SELECT
    l.tenant_id,
    l.order_number,
    l.booked_amount,
    p.captured_amount
FROM lines_by_order AS l
LEFT JOIN payments_by_order AS p
  ON p.tenant_id = l.tenant_id
 AND p.order_number = l.order_number;
~~~

Bảng `fact_payment_transactions` và các cột `payment_amount`, `transaction_type` trong truy vấn là **giả định bổ sung**, không có trong DDL `fact_order_lines` phía trên. Cần xử lý refund, reversal, currency và nhiều payment cho một đơn theo chính sách KPI; không tự kết luận `booked_amount = captured_amount`.

**DD hỗ trợ liên kết và drill-across, nhưng không thay thế yêu cầu xác định grain tương thích trước khi JOIN.**

## 9. Tính duy nhất, phạm vi và vòng đời của định danh

### 9.1. Mã chỉ duy nhất trong một tenant

Giả sử:

~~~text
tenant T01, order_number ORD-101
tenant T02, order_number ORD-101
~~~

Hai mã hiển thị giống nhau không tạo thành cùng một đơn. Khóa đầy đủ là:

~~~text
(tenant_id, order_number)
~~~

Nếu hệ thống chỉ tạo số đơn duy nhất theo `(store_id,fiscal_year)`, phải bổ sung **đúng phạm vi đó**. Phân tích đa quốc gia còn có thể cần namespace của hệ nguồn khi nhiều hệ dùng các chuỗi ID giống nhau.

**Không suy tính duy nhất từ vài dòng mẫu.** Cần yêu cầu nghiệp vụ và cơ chế sinh mã được xác nhận.

### 9.2. Mã hiển thị có thể thay đổi

Không phải mọi `order_number` là bất biến. Một số hệ thống:

- Đặt mã tạm khi tạo đơn và cấp số chính thức khi xác nhận.
- Đánh lại số hóa đơn khi đóng kỳ hoặc theo cơ sở phát hành.
- Cho phép chỉnh mã ngoài hệ thống theo quy trình sửa lỗi.
- Hợp nhất nguồn làm thay đổi namespace của mã.

Với mô hình phân tích, phải xác định **định danh ổn định để deduplicate và liên kết**, bên cạnh **mã hiển thị lịch sử** nếu cần. Có thể giữ:

~~~text
source_system
stable_order_id
order_number_at_confirmation
tenant_id
~~~

`stable_order_id` có thể là khóa nguồn bất biến, còn `order_number_at_confirmation` là DD hiển thị tại mốc sự kiện. Nhưng lựa chọn này phải dựa trên định nghĩa nguồn, không tự sáng tạo một mã “ổn định” mà không có cơ chế bảo đảm.

### 9.3. Một đơn có nhiều số hóa đơn hoặc nhiều phiếu giao

Một đơn có thể sinh:

~~~text
ORD-101
    ├── INV-001
    ├── INV-002
    └── SHIP-054, SHIP-055
~~~

Không được gán một `invoice_number` cho toàn bộ đơn khi nghiệp vụ cho phép nhiều hóa đơn. Thay vào đó, mỗi loại chứng từ có **grains riêng**:

~~~text
fact_invoice_lines(invoice_id, invoice_line_no, ...)
fact_shipments(shipment_id, ...)
fact_order_lines(order_id, line_no, ...)
~~~

Quan hệ giữa các chứng từ có thể cần **bảng liên kết** hoặc fact ở grain phù hợp. DD là một **mã để truy vết**, không phải lời hứa rằng mọi quan hệ nghiệp vụ là một-một.

## 10. Degenerate dimension có phải thuộc tính SCD không?

Thông thường một DD là **định danh giao dịch ở thời điểm xảy ra sự kiện**, không có các thuộc tính mô tả riêng cần phiên bản hóa. Vì thế:

- Không tạo các dòng `dim_order` Type 2 **chỉ để thay đổi chính số đơn** nếu điều đó không đem lại giá trị nghiệp vụ.
- Nếu cần lưu **lịch sử trạng thái của đơn**, chọn mô hình phù hợp: event fact hoặc accumulating snapshot theo grain.
- Nếu cần biết **khách hàng hay danh mục sản phẩm tại thời điểm xác nhận**, phải gắn fact với **phiên bản dimension đúng thời điểm** hoặc snapshot thuộc tính có kiểm soát.
- Nếu mã được thay đổi, cần định nghĩa việc giữ **mã gốc**, mã hiện tại và ánh xạ, không mặc định `UPDATE` toàn bộ dữ liệu lịch sử.

Ví dụ: `dim_product` SCD Type 2 có nhiều `product_key` cho một `product_code` qua các thời kỳ. Fact dòng hàng có:

~~~text
order_number = ORD-101             -- DD, định danh chứng từ
product_key  = 205                 -- FK tới phiên bản sản phẩm lúc đặt
~~~

Hai vai trò khác nhau: DD giúp tìm chứng từ, `product_key` giúp giải thích thông tin sản phẩm theo phiên bản đã chọn.

**Lưu ý:** nếu mã giao dịch chứa thông tin cá nhân hoặc có thể suy ra danh tính, cần chính sách phân quyền và retention phù hợp; việc nó là DD không miễn trừ yêu cầu bảo vệ dữ liệu.

## 11. Hiệu năng và thiết kế vật lý cho DD có cardinality cao

DD thường có nhiều giá trị khác nhau, vì mỗi đơn/hóa đơn/ticket có mã riêng. Điều này ảnh hưởng đáng kể đến chỉ mục và cách lưu.

### 11.1. Chỉ mục cho truy vấn drill-through

Với bảng `fact_order_lines`, khóa chính ghép `(tenant_id,order_number,line_no)` có thể hỗ trợ truy vấn:

~~~sql
WHERE tenant_id = 'T01'
  AND order_number = 'ORD-101'
~~~

vì hai cột là **tiền tố khóa** trong chỉ mục B-tree thông thường của PostgreSQL. Không phải mọi DBMS/tổ chức lưu trữ hoạt động y hệt; cần đo với engine được dùng.

Nếu yêu cầu tra đơn theo `order_number` **mà không có tenant**, có thể khó tận dụng chỉ mục theo tenant trước; nhưng việc bỏ tenant trong truy vấn còn có thể **sai ngữ nghĩa hoặc quyền truy cập**. Trước khi thêm chỉ mục khác, phải xác nhận mục đích và quyền xem xuyên tenant.

### 11.2. Chọn cách biểu diễn định danh

| Lựa chọn | Lợi ích | Đánh đổi |
|---|---|---|
| Giữ mã chứng từ dạng chuỗi | Dễ đối soát với nguồn, dễ hiển thị | Chuỗi dài có thể làm index/fact lớn |
| Giữ khóa nguồn số ổn định kèm mã hiển thị | Nối/đối soát với nguồn theo ID ổn định | Cần quản lý namespace và ánh xạ đúng |
| Sinh khóa kỹ thuật cho từng dòng fact | Dễ tham chiếu nội bộ trong vài pipeline | Không thay thế grain và khóa nghiệp vụ |
| Mã hóa/token hóa ID cho phạm vi truy cập khác | Có thể giảm lộ định danh gốc | Khả năng nối/giải mã và quản trị khóa phức tạp |

Không nên tạo một `dim_order` chỉ vì nghĩ rằng “JOIN số nguyên chắc chắn nhanh hơn lưu chuỗi” mà chưa đo **tổng chi phí** của bảng dimension, phép JOIN, bộ nhớ, số dòng và truy vấn cần hỗ trợ.

### 11.3. Partition và clustered storage

Nếu fact có khối lượng rất lớn, phân vùng theo ngày giao dịch có thể có lợi cho truy vấn theo kỳ và retention. Nhưng:

- `order_number` có thể xuất hiện ở nhiều partition nếu nguồn có **sửa dòng/đến muộn**; cần xác định chính xác grain và sự kiện được phân vùng.
- Tính duy nhất **toàn bảng phân vùng** không được mọi hệ quản trị hỗ trợ theo cùng cách. Ví dụ PostgreSQL yêu cầu khóa duy nhất/khóa chính trên bảng phân vùng bao gồm khóa phân vùng trong các trường hợp thông thường; không được chỉ thêm date vào PK rồi mặc nhiên xem hai dòng cùng business grain khác date là hợp lệ.
- Nếu thực sự cần bất biến `(tenant_id,order_number,line_no)` duy nhất trên mọi partition, phải chọn chiến lược thực thi phù hợp: khóa phân vùng tương thích, registry duy nhất, xử lý nạp có kiểm soát hoặc cơ chế DBMS hỗ trợ.
- Tối ưu clustering/index chỉ nên làm **sau khi** đo workload: truy vấn theo ngày, theo khách, theo mã đơn, và quy mô các partition.

### 11.4. High cardinality có ảnh hưởng tới BI

Một chiều với hàng chục triệu số đơn không thích hợp làm **slicer hiển thị danh sách đầy đủ** cho người dùng. DD thường phù hợp với:

- Ô tìm kiếm mã chứng từ.
- Drill-through từ số liệu tổng hợp.
- Nhóm hoặc đếm distinct khi cần.
- Công cụ tra soát chi tiết theo ID.

Tránh dựng dimension giả chỉ để có một menu thả xuống chứa hàng triệu mã đơn. Giao diện nên tìm kiếm có giới hạn, lọc theo phạm vi và kiểm soát quyền.

## 12. Quyền truy cập và bảo vệ định danh giao dịch

Một mã giao dịch đôi khi chứa thông tin tổ chức, cửa hàng, ngày phát hành hoặc chuỗi có thể dùng để tra cứu hồ sơ cá nhân. Đặt DD trực tiếp trong fact giúp truy vết thuận tiện nhưng cũng làm **định danh có mặt ở nhiều dòng**.

Các yêu cầu thực tế:

- **Giới hạn tenant** khi xem và tìm kiếm đơn; không để bộ lọc tùy ý vượt phạm vi được phép.
- **Không hiển thị đủ định danh nhạy cảm** cho nhóm chỉ cần dashboard tổng hợp.
- Hạn chế xuất dữ liệu chi tiết nếu không có mục đích được phê duyệt.
- Kiểm soát quyền và nhật ký truy cập tới drill-through.
- Quy định retention và purge cho fact và các bản xuất báo cáo có chứa DD.
- Nếu cần dùng token hoặc hash, phải phân biệt **ẩn danh hóa thật** với giả danh hóa có thể nối lại. Hash đơn giản của ID có cấu trúc/dễ đoán chưa chắc bảo vệ tốt.

DD là lựa chọn **mô hình hóa**, không phải một ràng buộc bảo mật. Cần thêm kiểm soát truy cập ở tầng DBMS, semantic layer, ứng dụng và pipeline tùy hệ thống.

## 13. Kiểm thử chất lượng dữ liệu và đối soát

### 13.1. Một fact row phải duy nhất tại grain đã khai báo

~~~sql
SELECT
    tenant_id,
    order_number,
    line_no,
    COUNT(*) AS occurrences
FROM fact_order_lines
GROUP BY tenant_id, order_number, line_no
HAVING COUNT(*) > 1;
~~~

Với DDL có khóa chính đang được thực thi, truy vấn thông thường không trả dòng nào. Nhưng ở bảng staging hoặc một số hệ phân tích **không cưỡng chế UNIQUE**, phải kiểm tra trước khi nạp.

### 13.2. Không để cùng một đơn có mâu thuẫn thuộc tính cấp đơn

Theo quy tắc nghiệp vụ, tất cả dòng của một đơn đã xác nhận phải có cùng ngày xác nhận và cùng khách:

~~~sql
SELECT
    tenant_id,
    order_number,
    COUNT(DISTINCT confirmed_date) AS confirmed_dates,
    COUNT(DISTINCT customer_key) AS customer_versions
FROM fact_order_lines
GROUP BY tenant_id, order_number
HAVING COUNT(DISTINCT confirmed_date) > 1
    OR COUNT(DISTINCT customer_key) > 1;
~~~

Đây là phép thử hợp lệ **khi nghiệp vụ xác nhận** một đơn chỉ có một ngày xác nhận và một khách/phiên bản khách tương ứng tại mốc đó. Nếu `customer_key` bị gán sai phiên bản trong ETL, có thể có mâu thuẫn cần điều tra.

Truy vấn không phát hiện mọi lỗi: `COUNT(DISTINCT)` bỏ qua NULL, và một đơn có thể bị thiếu toàn bộ dòng. Do đó cần ràng buộc `NOT NULL`, kiểm tra nguồn và đối soát cấp đơn.

### 13.3. Kiểm tra số liệu theo chứng từ

~~~sql
WITH fact_totals AS (
    SELECT
        tenant_id,
        order_number,
        COUNT(*) AS fact_lines,
        SUM(booked_amount) AS fact_booked_amount
    FROM fact_order_lines
    GROUP BY tenant_id, order_number
),
source_totals AS (
    SELECT
        tenant_id,
        order_number,
        COUNT(*) AS source_lines,
        SUM(quantity * unit_price_at_order - line_discount_amount)
            AS source_booked_amount
    FROM staging_confirmed_order_lines
    GROUP BY tenant_id, order_number
)
SELECT
    COALESCE(s.tenant_id, f.tenant_id) AS tenant_id,
    COALESCE(s.order_number, f.order_number) AS order_number,
    s.source_lines,
    f.fact_lines,
    s.source_booked_amount,
    f.fact_booked_amount
FROM source_totals AS s
FULL OUTER JOIN fact_totals AS f
  ON f.tenant_id = s.tenant_id
 AND f.order_number = s.order_number
WHERE s.source_lines IS DISTINCT FROM f.fact_lines
   OR s.source_booked_amount IS DISTINCT FROM f.fact_booked_amount;
~~~

`staging_confirmed_order_lines` và các cột tương ứng là **đầu vào giả định**; trước khi dùng cần đảm bảo cùng phạm vi, tiền tệ, trạng thái xác nhận, công thức, quy tắc làm tròn và thời điểm chốt. Mẫu `IS DISTINCT FROM` là cú pháp PostgreSQL và xử lý so sánh có NULL rõ ràng.

Truy vấn này giúp tìm sai khác cấp **mã chứng từ đầy đủ**. Việc đối soát chỉ bằng tổng tiền toàn tháng có thể bỏ sót hai lỗi **bù trừ nhau**.

### 13.4. Nạp lại dữ liệu phải idempotent

Một sự kiện xác nhận dòng hàng có thể được gửi lại. Pipeline cần bảo đảm:

~~~text
natural grain key =
    (tenant_id, order_number, line_no)
~~~

và dùng chiến lược nạp phù hợp:

- **Upsert** khi nguồn biểu diễn trạng thái cùng dòng có thể cập nhật, với quy tắc chọn phiên bản mới nhất hợp lệ.
- **Insert idempotent** khi nguồn là sự kiện bất biến, tránh ghi lặp bản sao của cùng sự kiện.
- **Ghi sự kiện điều chỉnh riêng** nếu cần giữ lịch sử thay đổi sau xác nhận.
- **Quarantine** khi hai bản ghi cùng business grain nhưng nội dung mâu thuẫn mà chưa có quy tắc phân giải.

Chỉ dùng `ON CONFLICT DO NOTHING` mà không kiểm tra nội dung khác nhau có thể **che lỗi dữ liệu**. Nếu business key thực tế gồm cả phiên bản hoặc nguồn phát, phải chốt lại grain trước khi áp dụng quy tắc nạp.

## 14. Liên hệ với mô hình quan hệ, document, đồ thị và phân tích

| Kiểu mô hình | Vai trò định danh giao dịch | Điểm cần lưu ý |
|---|---|---|
| **OLTP quan hệ** | Khóa chính của `orders`, `invoices`; khóa ngoại ở dòng chi tiết | Cần toàn vẹn tham chiếu và xử lý vòng đời chứng từ |
| **Star schema phân tích** | DD như `order_number` nằm trực tiếp trong fact cấp dòng | Không cần `dim_order` chỉ có ID; đếm distinct đúng phạm vi |
| **Document** | `order_number` là metadata của document đơn có mảng dòng hàng | Khi flatten sang fact cấp dòng, mang mã đơn xuống từng dòng và kiểm tra grain |
| **Đồ thị** | ID của node sự kiện/đơn hoặc thuộc tính của quan hệ | Nhiều đường đi đến cùng đơn không đồng nghĩa có nhiều đơn |
| **Kho cột / data lake** | ID chứng từ được lưu trong parquet/columnar fact để drill-through | High cardinality ảnh hưởng nén, partition, clustering và distinct count |

Trong OLTP, `orders` là một **thực thể có ý nghĩa quản lý**, không bị xóa chỉ vì báo cáo dùng DD. Mục đích của DD là **tránh một bảng dimension dư thừa trong mô hình phân tích**, không phải xóa thực thể đơn khỏi toàn hệ thống.

Trong document, một đơn hàng với mảng `items[]` có thể được đọc như một đối tượng hoàn chỉnh; khi chuyển sang bảng fact dòng hàng, `order_number` có thể được lặp có chủ đích trên từng item để tra cứu. Đó không nhất thiết là vi phạm chuẩn hóa của kho phân tích, nhưng cần tránh lặp **tổng tiền cấp đơn** lên từng item rồi cộng sai.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách sửa |
|---|---|---|
| “Degenerate dimension là dữ liệu lỗi” | *Degenerate* chỉ một mẫu thiết kế | Hiểu đúng là định danh nghiệp vụ nằm trong fact |
| “Mọi dimension phải có bảng riêng” | ID giao dịch có thể không có thuộc tính mô tả để tách | Giữ DD trực tiếp trong fact |
| “`order_number` là PK của fact dòng hàng” | Một đơn có nhiều dòng | Khóa phải bao gồm `line_no` và phạm vi cần thiết |
| “Mã đơn duy nhất trên toàn công ty” khi chỉ duy nhất trong tenant | Gộp nhầm đơn từ nhiều tenant | Dùng đầy đủ `(tenant_id,order_number)` |
| “Có DD thì không cần fact cấp đơn” | Có KPI/số đo ở cấp đơn | Thiết kế fact cấp đơn riêng nếu có lý do |
| “Phải tạo `dim_order` để JOIN nhanh” | Một bảng ID-only có thể chỉ tăng độ phức tạp | Đo, đánh chỉ mục và xem workload trước |
| “Có cùng DD thì JOIN trực tiếp hai fact được” | Dễ tạo fanout nhiều-nhiều | Tổng hợp về grain chung trước khi JOIN |
| “`COUNT(*)` là số đơn” trong fact dòng hàng | Đếm dòng hàng, không đếm chứng từ | `COUNT(DISTINCT)` trên ID đầy đủ |
| “Đếm số đơn theo danh mục rồi cộng giữa các danh mục” | Một đơn có nhiều danh mục | Distinct trên toàn phạm vi cần hỏi |
| “DD phải có lịch sử SCD2” | Bản thân định danh thường không có tập thuộc tính cần version | Lịch sử thuộc dimension mô tả/fact sự kiện phù hợp |
| “Thêm fact surrogate key là giải quyết duplicate” | Khóa kỹ thuật không thay thế grain nghiệp vụ | Kiểm tra natural grain key |
| “Có thể bỏ tenant khi tìm theo mã đơn” | Sai phạm vi định danh và có thể sai phân quyền | Filter bằng namespace hợp lệ |
| “Giữ DD trong fact bảo đảm mọi truy vấn được phép” | DD có thể nhạy cảm | Phân quyền, masking/tokenization và retention |
| “Sửa lỗi bằng `SUM(DISTINCT amount)`” | Hai dòng thật có thể có cùng số tiền | Sửa grain/JOIN, không distinct trên measure |

## 16. Bài luyện tập có lời giải

### Bài 1 — Nhận diện degenerate dimension

`fact_invoice_lines(invoice_number, line_no, product_key, date_key, quantity, line_amount)` chứa số hóa đơn nhưng không có `dim_invoice`. `invoice_number` có thể là DD không?

**Lời giải:** **Có**, nếu nó là định danh chứng từ nghiệp vụ dùng tra cứu/nhóm/drill-through và không có bảng chiều mô tả riêng. Cần xác nhận phạm vi số hóa đơn duy nhất. Nếu hóa đơn có nhiều dòng, `invoice_number` **không** là khóa duy nhất của fact dòng.

### Bài 2 — Đếm đơn và dòng

Một fact có 4 dòng: `(T01,O1,1)`, `(T01,O1,2)`, `(T01,O2,1)`, `(T02,O1,1)`. Có bao nhiêu dòng và bao nhiêu đơn phân biệt?

**Lời giải:** **4 dòng** và **3 đơn** theo `(tenant_id,order_number)`: `(T01,O1)`, `(T01,O2)`, `(T02,O1)`. `COUNT(DISTINCT order_number)` đơn lẻ chỉ thấy hai mã `O1,O2` và **đếm sai**.

### Bài 3 — Có nên tạo `dim_order`?

Một nhóm đề xuất `dim_order(order_key,order_number)` không có thuộc tính mô tả nào khác chỉ để “chuẩn hóa dimension”.

**Lời giải:** Thường **không cần** trong star schema nếu fact có thể giữ `order_number` để drill-through/đếm. Tạo bảng ID-only tăng ETL và phép JOIN mà chưa có giá trị phân tích. Nếu có nhu cầu liên kết, quyền, cardinality hoặc lưu lịch sử phức tạp đã được chứng minh, đánh giá riêng thay vì áp dụng quy tắc tuyệt đối.

### Bài 4 — Khóa của fact

Một đơn chứa ba dòng sản phẩm. Nếu đặt `PRIMARY KEY(order_number)` trên `fact_order_lines`, điều gì xảy ra?

**Lời giải:** Hệ thống không cho ghi quá một dòng cho cùng mã đơn. Khóa cần phản ánh grain như `(tenant_id,order_number,line_no)`, hoặc một ID dòng ổn định đi kèm ràng buộc duy nhất nghiệp vụ.

### Bài 5 — Đếm đơn theo sản phẩm

Đơn `O1` có hai sản phẩm P1 và P2, đơn `O2` chỉ có P1. Báo cáo `orders_with_product` cho P1 là 2 và P2 là 1. Có được cộng thành 3 đơn không?

**Lời giải:** Không. Có **2 đơn phân biệt**. `O1` xuất hiện ở cả hai nhóm; cộng `COUNT(DISTINCT)` của nhóm chồng nhau sẽ đếm trùng.

### Bài 6 — DD và số tiền cấp đơn

Một đơn ba dòng có phí giao hàng toàn đơn 30.000. Nếu sao chép `shipping_fee=30.000` vào mỗi dòng fact và cộng, kết quả là gì? Nên thiết kế ra sao?

**Lời giải:** Tổng sai là **90.000**. Có thể giữ phí ở `fact_orders` cấp đơn hoặc phân bổ xuống từng dòng với quy tắc và phép kiểm tra tổng phân bổ bằng 30.000. DD không biến số tiền cấp đơn thành measure cấp dòng.

### Bài 7 — JOIN giữa hai quy trình

Một đơn có ba dòng hàng và hai lần thanh toán. JOIN `fact_order_lines` với `fact_payments` theo mã đơn tạo bao nhiêu dòng, và vì sao không được SUM tiền trực tiếp?

**Lời giải:** Có \(3\times2=6\) dòng. Các dòng hàng bị lặp hai lần; các lần thanh toán bị lặp ba lần. Tổng hợp từng fact về **grain cấp đơn** trước khi JOIN, rồi mới so số tiền đặt và đã thanh toán.

### Bài 8 — Hai phạm vi số hóa đơn

Hai cửa hàng đều dùng hóa đơn `0001` mỗi năm. Bạn cần lưu gì để đối soát chính xác?

**Lời giải:** Xác nhận phạm vi định danh và lưu đủ `(store_id,fiscal_year,invoice_number)` hoặc một mã toàn cục đã được bảo đảm. Không chỉ giữ `invoice_number='0001'` rồi đếm distinct xuyên cửa hàng/năm.

### Bài 9 — Định danh đổi khi xác nhận

Đơn nháp có mã `TMP-1`, sau xác nhận được cấp `INV-2026-001`. Hệ thống muốn xem lịch sử từ nháp tới xác nhận. Có nên dùng `INV-2026-001` làm định danh ổn định duy nhất cho mọi sự kiện trước đó?

**Lời giải:** Không mặc nhiên. Cần có **stable source/order ID** hoặc ánh xạ được xác nhận giữa hai mã, giữ mã tại thời điểm giao dịch nếu cần audit. DD hiển thị và ID bất biến có vai trò khác nhau.

### Bài 10 — Dimension SCD2 và DD

Sản phẩm SP01 chuyển danh mục từ “Sách” sang “Quà tặng”. Một dòng đơn cũ cần giữ danh mục tại lúc mua. Nên cập nhật mã đơn hay dimension?

**Lời giải:** `order_number` là DD và không liên quan trực tiếp đến phân loại sản phẩm. Fact phải dùng `product_key` trỏ đúng phiên bản `dim_product` tại lúc mua (SCD2) hoặc snapshot mô tả được kiểm soát. Không sửa `order_number` để giải quyết lịch sử danh mục.

### Bài 11 — Khả năng tìm kiếm và high cardinality

Fact có 100 triệu `order_number` khác nhau. Người dùng muốn một danh sách thả xuống chứa toàn bộ mã để chọn.

**Lời giải:** Đây là giao diện không phù hợp với DD high cardinality. Dùng **tìm kiếm có điều kiện, lọc theo tenant/ngày, giới hạn kết quả và drill-through**. Đo index/partition phù hợp, đừng tạo dimension một trăm triệu dòng chỉ để có dropdown.

### Bài 12 — Một fact row có surrogate key

`fact_order_lines` có thêm `fact_row_key` tự sinh. ETL ghi hai dòng có `fact_row_key` khác nhau nhưng cùng `(tenant_id,order_number,line_no)`. Điều này đã hợp lệ chưa?

**Lời giải:** **Chưa** nếu grain quy định duy nhất một dòng cho bộ ba đó. Surrogate key chỉ bảo đảm hai bản ghi kỹ thuật có ID khác nhau; nó không chứng minh có hai sự kiện nghiệp vụ hợp lệ. Cần kiểm tra nguồn, deduplicate và xử lý bản ghi mâu thuẫn.

## 17. Checklist khi dùng định danh giao dịch làm chiều suy biến

- [ ] Đã viết rõ **câu khai báo grain** của fact.
- [ ] Đã xác nhận mã dùng làm DD là **định danh nghiệp vụ**, không chỉ một chuỗi tình cờ có vẻ duy nhất.
- [ ] Đã xác định **namespace**: tenant, cửa hàng, năm, hệ nguồn hoặc mã toàn cục.
- [ ] Đã phân biệt DD với **khóa nghiệp vụ của dòng fact**, surrogate key và FK tới dimension.
- [ ] Đã xác định có cần bảng dimension mô tả **thực sự** hay chỉ cần giữ ID trực tiếp trong fact.
- [ ] Đã kiểm tra số đo cấp đơn không bị **lặp trên mỗi dòng** và bị SUM nhiều lần.
- [ ] Đã thiết kế **fact cấp đơn/điều chỉnh/trạng thái** khi có KPI ở grain khác.
- [ ] Đã kiểm tra **COUNT(DISTINCT)** đúng phạm vi và tránh cộng distinct từ các nhóm chồng nhau.
- [ ] Đã kiểm tra JOIN nhiều fact không tạo **fanout**; nếu cần, tổng hợp từng fact trước.
- [ ] Đã phân biệt **mã hiển thị** với định danh nguồn ổn định và chính sách đổi mã.
- [ ] Đã xử lý bản ghi nạp lại, duplicate, late events và quy tắc cập nhật sau xác nhận.
- [ ] Đã đo tác động của DD high cardinality lên index, lưu trữ, tìm kiếm và BI.
- [ ] Đã kiểm tra quyền xem theo tenant, tính nhạy cảm của định danh và retention.
- [ ] Đã có truy vấn drill-through và quy trình đối soát theo **mã chứng từ đầy đủ**.

**Ghi nhớ:** **Degenerate dimension** là định danh giao dịch được **lưu ngay trong bảng fact** để truy vết, lọc, nhóm và đếm chứng từ, **không cần bảng dimension chỉ chứa mã**. Cách thiết kế này đơn giản hóa star schema nhưng **không thay đổi grain**: một mã đơn có thể đi cùng nhiều dòng fact, nhiều thanh toán hoặc nhiều kiện hàng. Muốn số liệu chính xác, hãy kiểm tra **khóa nghiệp vụ đầy đủ, số đo đúng cấp, cardinality của JOIN và vòng đời của mã** trước khi tối ưu vật lý.
