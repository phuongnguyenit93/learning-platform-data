# Chọn mô hình vật lý và chỉ mục từ các truy vấn thực tế

Một ERD có thể hoàn toàn đúng về thực thể và quan hệ nhưng vẫn tạo ra một hệ thống chậm, tốn dung lượng và khó vận hành nếu lựa chọn mô hình vật lý chỉ dựa trên cảm tính. Một index “đúng tên cột” chưa chắc giúp truy vấn dùng LIMIT và ORDER BY; một bảng được chuẩn hóa tốt chưa chắc phù hợp để tính tổng doanh thu trên hàng trăm triệu dòng trong mỗi lượt mở dashboard. Ngược lại, thêm index cho mọi cột sẽ làm các lệnh ghi, VACUUM, backup và migration đắt hơn.

Bài thực hành tổng hợp này thuộc module **DATABASE_DATA_MODELING** và chương **Thực hành tổng hợp**. Nhiệm vụ là **đọc truy vấn và tải sử dụng thực tế, xác định grain và ràng buộc, rồi chọn bảng, khóa, chỉ mục, phân vùng và mô hình đọc phù hợp**. Chúng ta sẽ làm trên ca hệ bán hàng đa tenant, kết hợp truy vấn tìm đơn hàng, danh sách phân trang, hàng chờ xử lý, tìm sản phẩm, báo cáo doanh thu, chuỗi sự kiện, dữ liệu JSONB và cập nhật tồn kho.

Mục tiêu sau bài học:

1. Chuyển một danh sách truy vấn thành **workload matrix** có độ thường xuyên, độ chọn lọc, số dòng, SLA và thứ tự ưu tiên.
2. Đề xuất mô hình vật lý **không phá vỡ bất biến nghiệp vụ**: grain, PK/FK/UNIQUE, tenant isolation và vòng đời.
3. Chọn và giải thích **B-tree đơn/cột ghép, partial, covering INCLUDE, expression, GIN và BRIN** theo đúng predicate, join, sort và range.
4. Biết khi nào nên **tái sử dụng index sẵn có**, khi nào dùng keyset pagination, partition hoặc bảng tổng hợp dẫn xuất.
5. Dựng thí nghiệm với **EXPLAIN (ANALYZE, BUFFERS)**, dữ liệu đại diện và chỉ số ghi để chứng minh đề xuất.
6. Nêu rõ đánh đổi về **chi phí ghi, contention, dung lượng, bảo mật, migration và khả năng tiến hóa**.
7. Hoàn thành bài tập thiết kế có lời giải, chứ không chỉ sao chép một tập lệnh CREATE INDEX.

> **Nguyên tắc:** Bắt đầu từ câu hỏi “truy vấn nào, trong phạm vi nào, trên bao nhiêu dòng, cần trả gì và trong bao lâu?”, không bắt đầu từ “bảng này có những cột nào để tạo index?”.

## 1. Đề bài: hệ bán hàng đa tenant đang tăng trưởng

Một nền tảng bán hàng phục vụ nhiều cửa hàng (tenant). Dữ liệu thao tác chính:

- **Customer:** một khách hàng trong một tenant.
- **Product:** một sản phẩm trong một tenant, có SKU, danh mục và trạng thái bán.
- **SalesOrder:** một đơn hàng, có trạng thái, người mua, thời điểm tạo và thời điểm thanh toán.
- **OrderLine:** một dòng hàng trong một đơn, có số lượng và giá đơn vị tại thời điểm bán.
- **StockBalance:** số lượng hiện có và đã giữ theo tenant, kho và SKU/sản phẩm.
- **DeviceEvent:** bản ghi cảm biến từ thiết bị kho, có timestamp và loại metric.
- **Order metadata:** thuộc tính nguồn tùy biến, trong đó một số trường ít dùng để lọc có thể là JSONB.

### 1.1. Giả định về quy mô — không phải số đo production

| Đại lượng | Giả định cho bài | Tác động thiết kế |
| --- | ---: | --- |
| Tổng số tenant | 2.000 | Hầu hết truy vấn cần tenant_id |
| Customer | 2 triệu hàng | Tra cứu bằng ID/email |
| Product | 500.000 hàng | SKU, category, availability |
| SalesOrder | 20 triệu hàng | Lookup, recent list, trạng thái |
| OrderLine | 60 triệu hàng | 3 dòng/Order trung bình |
| Order mới | 100.000/ngày | Index làm tăng chi phí INSERT |
| DeviceEvent | 800.000/ngày | Dữ liệu append nhiều, truy vấn theo khoảng |
| Tenant lớn nhất | 30% Orders | Skew, hot tenant và hotspot |
| Thời gian lưu Order | Theo chính sách được duyệt | Ảnh hưởng phân vùng/archive |
| Refund/partial capture | Chưa thuộc phạm vi v1 | KPI doanh thu cần ghi rõ giới hạn |

Các giá trị trên được **giả định để luyện tư duy thiết kế**, không phải benchmark hay cam kết SLO. Khi làm dự án thật, thay chúng bằng dữ liệu thu từ workload, kích thước thực, tăng trưởng và thống kê theo tenant.

### 1.2. Những bất biến không được đánh đổi để lấy tốc độ

- Order và mọi Line/Customer/Product được tham chiếu phải **thuộc cùng tenant**.
- Mỗi Order có một khóa kỹ thuật (tenant_id, order_id) và mã hiển thị duy nhất trong tenant.
- Mỗi Line xác định bởi (tenant_id, order_id, line_no); hai Line cùng Product có thể hợp lệ.
- Unit price của Line là **giá đã chốt bằng VND nguyên đồng**; không cập nhật lịch sử bằng giá Product hiện hành.
- Cùng (tenant_id, source_system, source_order_ref) khi reference có mặt không tạo hai đơn nhập từ cùng nguồn.
- Khi giữ hàng, reserved không vượt on_hand tại StockBalance owner; index không thay transaction.
- Dữ liệu của tenant A không được lộ qua query, cache, export hay read model cho tenant B.

Chọn index phải giữ nguyên các bất biến này. Không đổi composite FK thành FK một cột chỉ vì JOIN trên một cột có vẻ ngắn hơn; không bỏ UNIQUE vì nó gây write overhead nếu đó là ràng buộc nghiệp vụ bắt buộc.

## 2. Workload matrix — đầu vào bắt buộc trước khi thiết kế

Nhóm sản phẩm đưa ra các câu hỏi chính. Các mục tiêu p95 dưới đây cũng chỉ là giả định để xây phép thử.

| Mã | Truy vấn hoặc command | Tần suất tương đối | Kích thước kết quả | Mục tiêu minh họa |
| --- | --- | --- | --- | --- |
| Q1 | Mở một Order và các Line theo ID | Rất cao | 1 Order, vài Line | p95 < 80 ms |
| Q2 | 50 Order mới nhất của một Customer | Rất cao | 50 hàng/trang | p95 < 150 ms |
| Q3 | 100 Order PENDING cũ nhất để xử lý | Cao | 100 hàng | p95 < 150 ms |
| Q4 | Các Order PAID theo khoảng thời gian | Trung bình | Trang 100 hàng | p95 < 300 ms |
| Q5 | Tìm Order bằng reference từ đối tác | Cao | 0..1 hàng | p95 < 100 ms |
| Q6 | Danh sách Product active của một Category | Cao | 30 hàng/trang | p95 < 150 ms |
| Q7 | Top Product bán chạy trong kỳ | Trung bình | 10–100 nhóm | Dashboard < 2 s hoặc mart |
| Q8 | Đọc 500 điểm gần nhất của một Device | Cao | 500 hàng | p95 < 200 ms |
| Q9 | Lọc Order theo metadata linh hoạt | Thấp | Hàng/trang | p95 < 700 ms |
| Q10 | ReserveStock với đồng thời cao | Cao, có hot SKU | 1 balance | Không oversell; p95 theo SLA |
| Q11 | Nhân viên tra đơn theo order_code | Cao | 0..1 Order | p95 < 100 ms |
| Q12 | Báo cáo tồn cuối ngày qua 12 tháng | Thấp | 12–365 ngày | Warehouse/OLAP đúng grain |

**Tần suất cao chưa đủ để được ưu tiên:** Q10 là đường ghi bảo vệ hàng hóa, có thể ưu tiên cao hơn một query đọc dù số lần gọi ít hơn. Query báo cáo chạy vài lần/ngày nhưng quét toàn bộ dữ liệu và làm nghẽn OLTP cũng có thể cần tách sang mô hình đọc riêng.

### 2.1. Checklist thu thập thông tin cho từng query

Đừng chỉ ghi câu SQL. Với mỗi Qx, ghi thêm:

1. **Filter:** điều kiện bằng, IN, range, LIKE, JSON containment, search?
2. **Join:** join key, số quan hệ 1–N, có nguy cơ nhân hàng?
3. **Sort/limit:** ORDER BY nào, LIMIT bao nhiêu, OFFSET sâu đến đâu?
4. **Projection:** cần cột gì? Có SELECT * hay có thể thu hẹp?
5. **Cardinality:** bao nhiêu hàng khớp với tenant lớn nhất, không chỉ trung bình?
6. **Skew:** một Customer có thể có 1 triệu Order không? Một SKU có phải hot key không?
7. **Freshness:** phải đọc dữ liệu ngay sau khi ghi hay replica chậm có chấp nhận?
8. **Security:** scope tenant nằm trong predicate và được kiểm soát ở đâu?
9. **SLO và budget:** p95/p99, rows read, buffers, write overhead, disk?
10. **Nguồn đo:** log ứng dụng, query statistics, kế hoạch EXPLAIN, tracing?

Nếu thiếu những câu trả lời này, chọn index mới chỉ là giả thuyết. **Index là một phương án kiểm thử**, không phải kết quả nghiệm thu.

## 3. Lược đồ quan hệ đề xuất cho phần OLTP

Ta dùng PostgreSQL với khóa ghép theo tenant. Để dễ theo dõi, khóa ID trong ví dụ được ứng dụng cấp; việc cấp ID duy nhất theo tenant là trách nhiệm riêng của hệ thống.

### 3.1. Customer và Product

~~~sql
CREATE TABLE customers (
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    email_normalized TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    archived_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, email_normalized)
);

CREATE TABLE products (
    tenant_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (tenant_id, product_id),
    UNIQUE (tenant_id, sku)
);
~~~

**Mỗi bảng đã có B-tree từ PK và UNIQUE.** Đó là các index cần đưa vào inventory trước khi đề xuất index khác. Ví dụ tìm Product theo (tenant_id,sku) có thể dùng unique index hiện có; tạo một index thứ hai y hệt là dư thừa.

Trong thực tế, email_normalized chỉ được xem là khóa duy nhất nếu chính sách chuẩn hóa email và hành vi tài khoản được thống nhất. Không coi lower(email) là giải pháp chung cho mọi trường hợp địa chỉ email.

### 3.2. SalesOrder, OrderLine và StockBalance

~~~sql
CREATE TABLE sales_orders (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    order_code TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT','PENDING','PAID','CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMPTZ,
    total_amount_vnd BIGINT NOT NULL CHECK (total_amount_vnd >= 0),
    source_system TEXT NOT NULL DEFAULT 'INTERNAL',
    source_order_ref TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (tenant_id, order_id),
    UNIQUE (tenant_id, order_code),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id)
        ON DELETE RESTRICT,
    CHECK (status <> 'PAID' OR paid_at IS NOT NULL)
);

CREATE TABLE order_lines (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_orders(tenant_id, order_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products(tenant_id, product_id)
        ON DELETE RESTRICT
);

CREATE TABLE stock_balances (
    tenant_id BIGINT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    on_hand INTEGER NOT NULL CHECK (on_hand >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    PRIMARY KEY (tenant_id, warehouse_id, product_id),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products(tenant_id, product_id),
    CHECK (reserved <= on_hand)
);
~~~

**Lưu ý về phạm vi:**

- Một Order có 0..N Line trong khi còn DRAFT; mô hình có thể cần 1..N khi trạng thái xác nhận theo quy tắc nghiệp vụ riêng. FK Line → Order **không tự buộc Order phải có Line**.
- Cột total_amount_vnd là tổng đã lưu; nếu nghiệp vụ yêu cầu nó luôn khớp SUM(Line), cần một đường ghi thống nhất và phép đối soát. CHECK không kiểm tra được tổng xuyên hàng.
- Một Order PAID có paid_at, nhưng chỉ riêng status không tạo ledger hoàn chỉnh cho refund, chargeback hoặc thanh toán nhiều lần.
- StockBalance chỉ lưu **một kho × một sản phẩm × một tenant**, không phải tổng tồn của toàn công ty.

### 3.3. Bản ghi time-series cho truy vấn Q8

~~~sql
CREATE TABLE device_events (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    event_id UUID NOT NULL,
    metric_code TEXT NOT NULL,
    value_num NUMERIC(18, 5) NOT NULL,
    PRIMARY KEY (tenant_id, device_id, observed_at, event_id)
);
~~~

Khóa bảo vệ **một event theo tenant/device/thời điểm/ID**, không đảm bảo event_id độc nhất trên mọi timestamp. Nếu nguồn sửa observed_at và phát lại cùng event_id, cần thêm **quy tắc dedup theo source event** khi nghiệp vụ yêu cầu exactly-once effects. NUMERIC được chọn để minh họa đo có độ chính xác cố định; nếu thiết bị dùng số đo thực có thể chấp nhận sai số floating-point, cần so chi phí/độ chính xác của DOUBLE PRECISION theo yêu cầu đo.

### 3.4. Sơ đồ mối liên hệ

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ SALES_ORDERS : places
    SALES_ORDERS ||--o{ ORDER_LINES : contains
    PRODUCTS ||--o{ ORDER_LINES : sold_as
    PRODUCTS ||--o{ STOCK_BALANCES : stocked_in
~~~

Đường nối diễn đạt quan hệ; việc chọn **index truy cập** vẫn phải căn cứ từ predicate, sort và workload. Không phải mỗi đường FK đều đòi một index mới trùng PK; cần xem chiều tìm kiếm cụ thể.

## 4. Q1 — Mở Order và tất cả Line bằng định danh

API đọc chi tiết:

~~~sql
SELECT tenant_id, order_id, order_code, customer_id,
       status, total_amount_vnd, created_at
FROM sales_orders
WHERE tenant_id = 11 AND order_id = 600001;

SELECT line_no, product_id, quantity, unit_price_vnd
FROM order_lines
WHERE tenant_id = 11 AND order_id = 600001
ORDER BY line_no;
~~~

### 4.1. Chọn index

- SalesOrder đã có **PRIMARY KEY (tenant_id, order_id)**.
- OrderLine đã có **PRIMARY KEY (tenant_id, order_id, line_no)**.

Với tenant_id và order_id cố định, index OrderLine đi đúng phần tiền tố khóa, sau đó các hàng có thứ tự theo line_no. **Không cần CREATE INDEX (order_id)** để phục vụ query này; index chỉ có order_id còn bỏ qua tenant scope.

### 4.2. Điểm cần xác minh

- Truy vấn thực sự có điều kiện tenant_id do lớp authorization đặt.
- Số Line mỗi Order theo phân bố thực; nếu có Order với hàng trăm nghìn Line, endpoint có cần phân trang?
- Nếu JOIN Product để lấy tên hiện hành, có đang vô tình thay **snapshot tên lúc bán** không?
- Nếu OrderLine thuộc shard khác SalesOrder, FK trong DDL trên không tự hoạt động như khi hai bảng cùng một PostgreSQL database.

**Quyết định Q1:** dùng hai PK sẵn có; không thêm index. Đây cũng là một đáp án quan trọng trong thiết kế vật lý: **lý do không tạo index**.

## 5. Q2 — 50 Order mới nhất của Customer: index ghép và keyset

Đường truy cập cần tenant, customer, sort theo thời điểm rồi ID:

~~~sql
SELECT order_id, status, total_amount_vnd, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND customer_id = 9001
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Khóa chính (tenant_id,order_id) không thuận lợi cho việc lấy **50 Order mới nhất của một Customer**: không chứa customer_id trước phần sort. Tạo index:

~~~sql
CREATE INDEX idx_orders_customer_recent
ON sales_orders (
    tenant_id,
    customer_id,
    created_at DESC,
    order_id DESC
)
INCLUDE (status, total_amount_vnd);
~~~

### 5.1. Giải thích thứ tự các cột

1. tenant_id và customer_id là **equality predicates**.
2. created_at và order_id phục vụ **ORDER BY DESC** và pagination.
3. order_id là tie-breaker ổn định khi nhiều Order có cùng created_at.
4. status và total_amount_vnd chỉ dùng trả kết quả, để trong **INCLUDE** thay vì thêm vào phần khóa sắp xếp.

B-tree có thể phục vụ nhiều trường hợp qua tiền tố bên trái, nhưng không suy luận index trên (tenant_id, customer_id, created_at) sẽ tối ưu mọi WHERE có created_at mà **thiếu customer_id**. Thứ tự cột cần phù hợp từng query quan trọng.

### 5.2. OFFSET sâu và keyset pagination

Trang đầu có thể dùng LIMIT 50. Với trang rất sâu:

~~~sql
SELECT order_id, status, total_amount_vnd, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND customer_id = 9001
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 100000;
~~~

Dù có index phù hợp, OFFSET 100000 thường vẫn phải đi qua lượng lớn hàng trước khi trả 50 hàng. Trong feed hoặc lịch sử dài, nên dùng **keyset pagination** với khóa cuối của trang trước:

~~~sql
SELECT order_id, status, total_amount_vnd, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND customer_id = 9001
  AND (created_at, order_id) <
      ('2026-11-20 00:00:00+00'::TIMESTAMPTZ, 600000)
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Cặp so sánh **<** phù hợp vì cả created_at và order_id cùng sort giảm. Nếu sort hai chiều khác nhau hoặc có NULL, cần logic cursor tương ứng; không áp công thức này một cách máy móc.

Keyset tránh công quét/bỏ qua nhiều hàng, nhưng **không tự đảm bảo snapshot nhất quán giữa các trang** khi dữ liệu mới được thêm/sửa. Nếu nghiệp vụ yêu cầu một danh sách bất biến trong cả phiên, cần xác định cutoff, isolation hoặc snapshot/ordering policy.

### 5.3. INCLUDE không chắc tạo Index Only Scan

PostgreSQL có thể dùng index-only scan khi truy vấn chỉ cần cột đã có trong index **và** các trang heap đủ điều kiện qua visibility map. Bảng thường xuyên UPDATE có thể vẫn cần heap fetch. INCLUDE làm index lớn hơn, tăng chi phí ghi và bảo trì. **Không chấp nhận INCLUDE chỉ vì thấy từ “covering” hấp dẫn**; phải đo index size, heap fetches, latency và workload cập nhật.

**Quyết định Q2:** thử index ghép theo (tenant_id, customer_id, created_at DESC, order_id DESC); INCLUDE chỉ giữ nếu đo lợi ích vượt chi phí.

## 6. Q3 — Order PENDING cũ nhất: partial index và truy vấn hàng chờ

Nhân viên xử lý từng đợt Order PENDING theo nguyên tắc FIFO:

~~~sql
SELECT order_id, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND status = 'PENDING'
ORDER BY created_at ASC, order_id ASC
LIMIT 100;
~~~

Nếu chỉ một tỷ lệ nhỏ Order đang PENDING, index cho mọi trạng thái có thể tốn dung lượng và chi phí cập nhật không cần thiết. Đề xuất:

~~~sql
CREATE INDEX idx_orders_pending_fifo
ON sales_orders (tenant_id, created_at ASC, order_id ASC)
WHERE status = 'PENDING';
~~~

### 6.1. Vì sao partial index có lợi?

- Chỉ chứa các Order thỏa **status = 'PENDING'**.
- Thứ tự theo tenant và thời điểm tạo phù hợp FIFO.
- Khi Order chuyển từ PENDING sang PAID/CANCELLED, entry có thể được loại khỏi partial index.
- Query **phải đủ điều kiện để optimizer chứng minh nó khớp predicate**; prepared statement có status parameter và generic plan không chắc sử dụng partial index nếu giá trị chưa biết.

Nếu PENDING chiếm phần lớn bảng, hoặc nhiều query cần các trạng thái khác nhau, có thể so phương án index tổng quát:

~~~sql
CREATE INDEX idx_orders_status_fifo_candidate
ON sales_orders (tenant_id, status, created_at ASC, order_id ASC);
~~~

Đây là **ứng viên thay thế**, không tạo đồng thời cả hai mà chưa đo. Chọn một dựa trên phân bố status, chi phí ghi và query thực.

### 6.2. Đọc danh sách không đồng nghĩa claim công việc

Nếu nhiều worker xử lý hàng chờ, SELECT danh sách rồi UPDATE sau có thể khiến **hai worker chọn cùng Order**. Với hàng chờ có thể chấp nhận bỏ qua hàng đang bị khóa, **FOR UPDATE SKIP LOCKED** có thể hỗ trợ tranh chấp. Ví dụ sau chỉ minh họa khóa chọn hàng, **chưa thực hiện claim**:

~~~sql
BEGIN;

SELECT tenant_id, order_id
FROM sales_orders
WHERE tenant_id = 11
  AND status = 'PENDING'
ORDER BY created_at ASC, order_id ASC
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- Kết thúc phép thử: giải phóng khóa, không sửa trạng thái.
ROLLBACK;
~~~

Đoạn mã trên **cố ý ROLLBACK** để minh họa khóa, không giả mạo một transition nghiệp vụ hợp lệ. Khi triển khai thật, cần bổ sung trạng thái **PROCESSING** và thời hạn lease/owner tương ứng, hoặc dùng bảng jobs riêng; thao tác chọn và đánh dấu đã claim phải được thực hiện trong **cùng transaction**. SKIP LOCKED có thể trả một góc nhìn không nhất quán, phù hợp hàng chờ có tranh chấp, **không** nên dùng làm cách truy vấn báo cáo tổng quát.

**Quyết định Q3:** index partial phù hợp khi PENDING hiếm và predicate cố định; cơ chế claim phải được thiết kế ở tầng giao dịch/state machine, không suy ra từ index.

## 7. Q4 — Order PAID theo khoảng thời gian: range và sort

Bộ phận vận hành xem những Order thanh toán trong tuần:

~~~sql
SELECT order_id, customer_id, paid_at, total_amount_vnd
FROM sales_orders
WHERE tenant_id = 11
  AND status = 'PAID'
  AND paid_at >= '2026-11-01 00:00:00+00'::TIMESTAMPTZ
  AND paid_at <  '2026-11-08 00:00:00+00'::TIMESTAMPTZ
ORDER BY paid_at DESC, order_id DESC
LIMIT 100;
~~~

Đề xuất khi status PAID là predicate cố định và các truy vấn khác không cần toàn bộ status:

~~~sql
CREATE INDEX idx_orders_paid_recent
ON sales_orders (tenant_id, paid_at DESC, order_id DESC)
WHERE status = 'PAID';
~~~

**Tại sao half-open range?** Điều kiện từ đầu ngày bao gồm đến đầu ngày kết thúc **không bao gồm** tránh sai ở ranh giới độ chính xác timestamp và dễ ghép những kỳ liền kề. Khoảng theo UTC ở ví dụ cần được ánh xạ từ **ngày nghiệp vụ** theo timezone được duyệt; không mặc định mọi cửa hàng dùng ngày UTC.

### 7.1. Khác biệt Q2 và Q4

- Q2 có equality theo **customer_id**, sort theo **created_at**.
- Q4 không lọc customer, chỉ lọc tenant, paid status và range **paid_at**.
- Một index ghép Q2 không thể mặc định thay thế Q4 dù cả hai đọc SalesOrder.

Nếu workload Q4 rất thấp và trả dữ liệu từ replica/analytics, có thể không cần index riêng trên OLTP. Nếu Q4 là API vận hành có SLA chặt, index riêng có thể đáng chi phí.

### 7.2. Range predicate ảnh hưởng các cột tiếp theo

Với B-tree ghép, equality ở tiền tố thường hạn chế scan mạnh, sau đó range trên paid_at. Những cột nằm **sau cột range** không mặc định làm tập dữ liệu phải đọc nhỏ hơn theo cách giống equality ở tiền tố; order_id ở đây chủ yếu giúp ordering/tie-break. Thay thứ tự sang (tenant_id, order_id, paid_at) sẽ bất lợi nếu không có filter order_id.

**Quyết định Q4:** thử partial B-tree theo tenant + paid_at + order_id, so với index tổng quát và đo chi phí chuyển trạng thái.

## 8. Q5 và Q11 — Tra cứu định danh: UNIQUE đang là index

Đối tác gọi lại bằng source reference:

~~~sql
SELECT order_id, status
FROM sales_orders
WHERE tenant_id = 11
  AND source_system = 'PARTNER_A'
  AND source_order_ref = 'EXT-90001';
~~~

Tạo uniqueness đúng scope:

~~~sql
CREATE UNIQUE INDEX ux_orders_external_source
ON sales_orders (
    tenant_id, source_system, source_order_ref
)
WHERE source_order_ref IS NOT NULL;
~~~

**Ý nghĩa:** một reference có mặt là duy nhất **trong cùng tenant và source_system**. NULL có thể xuất hiện nhiều lần cho đơn nội bộ. Việc chống retry còn phải so **payload của cùng reference**; nếu ID giống nhưng nội dung khác, đó là conflict cần xử lý, không được âm thầm trả thành công cho một đơn sai.

Query Q11 theo mã đơn:

~~~sql
SELECT order_id, customer_id, status
FROM sales_orders
WHERE tenant_id = 11 AND order_code = 'O-1001';
~~~

Đã có **UNIQUE(tenant_id,order_code)** trong CREATE TABLE, nên **không thêm index khác** trên hai cột đó.

### 8.1. Khi nào partial unique gây trở ngại?

Partial unique index ở Q5 không thể dùng như một FK target thông thường thông qua UNIQUE constraint gắn index partial. Nếu một bảng khác cần tham chiếu Order bằng source reference, nên cân nhắc tham chiếu **PK(tenant_id,order_id)** hoặc thiết kế registry/mapping authoritative riêng. Không sửa khóa tham chiếu vì “dùng lại index có sẵn” khi điều đó phá ngữ nghĩa.

### 8.2. Expression index chỉ khi query thật dùng expression

Nếu mã tìm kiếm cần không phân biệt hoa/thường, một phương án là chuẩn hóa giá trị tại write path và lưu cột normalized có UNIQUE. Nếu yêu cầu truy vấn theo LOWER(order_code), có thể dùng expression index matching expression, nhưng phải xét collation, policy và liệu hai mã chỉ khác chữ hoa có được phép tồn tại không.

**Không** tạo sẵn index cho LOWER, UPPER, substring và mọi biến thể tên cột khi chưa có truy vấn và hợp đồng normalization cụ thể.

**Quyết định Q5/Q11:** index phục vụ uniqueness cũng đồng thời phục vụ lookup; tránh index dư thừa, nhưng không hạ thấp quy tắc idempotency hay phạm vi tenant.

## 9. Q6 — Product active trong danh mục: partial index và tiền tố

Ứng dụng hiển thị 30 sản phẩm đang bán của một Category:

~~~sql
SELECT product_id, sku, product_name
FROM products
WHERE tenant_id = 11
  AND category_id = 501
  AND is_active = TRUE
ORDER BY product_id ASC
LIMIT 30;
~~~

Đề xuất khi danh sách active chiếm tỷ lệ vừa phải và query này thường xuyên:

~~~sql
CREATE INDEX idx_products_active_category
ON products (tenant_id, category_id, product_id)
WHERE is_active = TRUE;
~~~

Index đưa các Product hợp lệ vào đúng nhóm tenant/category và đúng thứ tự product_id. Nếu Category có nhiều Product, API có thể dùng keyset theo product_id:

~~~sql
SELECT product_id, sku, product_name
FROM products
WHERE tenant_id = 11
  AND category_id = 501
  AND is_active = TRUE
  AND product_id > 70000
ORDER BY product_id ASC
LIMIT 30;
~~~

Một index thay thế khi **cả active và inactive được truy vấn thường xuyên** có thể là:

~~~sql
-- Ứng viên so sánh; chưa tạo cùng index partial nếu không có lý do.
CREATE INDEX idx_products_category_status_candidate
ON products (tenant_id, category_id, is_active, product_id);
~~~

### 9.1. Cột boolean có nên index riêng?

Index chỉ gồm **is_active** thường có độ chọn lọc thấp nếu phần lớn Product đang active. Tuy vậy, một partial index **chỉ chứa active** và có tiền tố tenant/category có thể vẫn hữu ích cho truy vấn cụ thể. Đánh giá theo số hàng của từng Category và tenant, **không kết luận chỉ từ kiểu BOOLEAN**.

### 9.2. Tìm Product bằng SKU

~~~sql
SELECT product_id, product_name
FROM products
WHERE tenant_id = 11 AND sku = 'SKU-2026-A';
~~~

Đã có UNIQUE(tenant_id,sku), không cần index thứ hai.

### 9.3. Tìm theo một phần tên Product

~~~sql
SELECT product_id, product_name
FROM products
WHERE tenant_id = 11
  AND product_name ILIKE '%tai nghe%';
~~~

B-tree thông thường không phải lời giải tốt cho wildcard ở **đầu chuỗi**. PostgreSQL có thể dùng extension **pg_trgm** và GIN/GiST trigram index khi phù hợp, nhưng phải xem quyền cài extension, ngôn ngữ tìm kiếm, tỷ lệ cập nhật, độ dài từ khóa và mức ưu tiên của search.

~~~sql
-- Chỉ là phương án thử trên môi trường được phép cài extension:
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_products_name_trgm_candidate
ON products USING GIN (product_name gin_trgm_ops);
~~~

Index này có thể lớn và chưa trực tiếp giới hạn tenant_id trong key. Nếu search là tính năng cốt lõi với nhiều tenant và yêu cầu ranking/ngôn ngữ, cần thử thiết kế search index/service riêng. Không tạo index trigram chỉ vì một query hiếm xuất hiện trong backlog.

**Quyết định Q6:** partial B-tree cho category active nếu kết quả đo hỗ trợ; tra SKU dùng UNIQUE sẵn có; fuzzy search là **nhánh yêu cầu riêng**, không ép vào một B-tree tổng quát.

## 10. Q7 — Top Product bán chạy: khi index không đủ

Truy vấn nghiệp vụ:

> Trong tenant 11, tìm 10 Product có **giá trị dòng hàng của những Order PAID** cao nhất trong tuần.

Giả định v1 chưa có refund và giá trị đang tính là **gross line amount**, không phải net revenue sau giảm giá/thuế/hoàn tiền.

~~~sql
SELECT l.product_id,
       SUM(l.quantity::NUMERIC * l.unit_price_vnd)
           AS gross_line_amount_vnd,
       SUM(l.quantity) AS units_sold
FROM sales_orders AS o
JOIN order_lines AS l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
WHERE o.tenant_id = 11
  AND o.status = 'PAID'
  AND o.paid_at >= '2026-11-01 00:00:00+00'::TIMESTAMPTZ
  AND o.paid_at <  '2026-11-08 00:00:00+00'::TIMESTAMPTZ
GROUP BY l.product_id
ORDER BY gross_line_amount_vnd DESC
LIMIT 10;
~~~

### 10.1. Các index sẵn có hỗ trợ được phần nào?

- Index **idx_orders_paid_recent** có thể giúp tìm Order PAID theo khoảng paid_at.
- PK **order_lines(tenant_id,order_id,line_no)** giúp tra các Line của từng Order.
- Nhưng để tính top Product, truy vấn phải **đọc các Line liên quan rồi GROUP BY Product và tính SUM**. Không thể kỳ vọng index đơn thuần trên product_id trả ngay top theo SUM của cả tuần.
- Nếu có hàng triệu Line trong kỳ, việc đi qua từng Order có thể tạo nhiều random lookups; optimizer có thể chọn scan/hash join khác dựa trên thống kê.

### 10.2. Vì sao không lập index trên tổng tiền tính toán?

Gross line amount của một **Line** có thể tính từ quantity × unit_price. Nhưng **top Product trong một khoảng ngày** là tổng của **nhiều Line**, lại phụ thuộc trạng thái/paid_at của Order. Một expression index trên quantity * unit_price ở bảng Line **không tự biến tổng theo Product/kỳ thành kết quả đã có sẵn**.

Đây là bài toán chọn **mô hình đọc**, không chỉ thêm index.

### 10.3. Nếu Dashboard cần dưới hai giây trên dữ liệu lớn

Có thể tạo bảng tổng hợp theo ngày với grain:

> Một hàng = một tenant × business_sale_date × product_id.

~~~sql
CREATE TABLE product_sales_daily (
    tenant_id BIGINT NOT NULL,
    business_sale_date DATE NOT NULL,
    product_id BIGINT NOT NULL,
    gross_line_amount_vnd NUMERIC(24, 0) NOT NULL DEFAULT 0,
    units_sold BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, business_sale_date, product_id)
);
~~~

Truy vấn đọc:

~~~sql
SELECT product_id,
       SUM(gross_line_amount_vnd) AS gross_line_amount_vnd,
       SUM(units_sold) AS units_sold
FROM product_sales_daily
WHERE tenant_id = 11
  AND business_sale_date >= DATE '2026-11-01'
  AND business_sale_date <  DATE '2026-11-08'
GROUP BY product_id
ORDER BY gross_line_amount_vnd DESC
LIMIT 10;
~~~

PK theo (tenant_id, business_sale_date, product_id) hỗ trợ cắt tập ngày của tenant. Query vẫn cần tổng hợp và sort theo tổng, nhưng chỉ đọc **một hàng/ngày/Product** thay cho mọi Line. Nếu trả dashboard realtime với lượng ghi lớn, có thể dùng materialized view/projection trong warehouse/OLAP, có **freshness SLA** và cơ chế correction.

### 10.4. Chuyển số liệu đúng quan trọng hơn tốc độ

Không được cộng một Line hai lần khi event replay. Khi Order bị cancel/refund, phải quyết định delta nào được ghi vào bảng tổng hợp và gắn **idempotency** cho event. Nếu Product đổi Category, kết quả as-sold và as-current có thể khác nhau; cần mô hình version/snapshot phù hợp.

Nếu yêu cầu **doanh thu ròng**, phải xác định giảm giá, tax, refund, phí, shipping và kỳ ghi nhận, không dùng gross sum rồi đặt tên net_revenue.

**Quyết định Q7:** từ truy vấn thực tế nhận ra nhu cầu bảng đọc tổng hợp hoặc OLAP; không thêm bừa các B-tree lên OrderLine rồi hứa top query sẽ đạt SLA.

## 11. Q8 — 500 mẫu gần nhất của Device: B-tree, BRIN và phân vùng

Truy vấn chuỗi thời gian:

~~~sql
SELECT observed_at, event_id, metric_code, value_num
FROM device_events
WHERE tenant_id = 11
  AND device_id = 8008
  AND observed_at >= '2026-11-20 00:00:00+00'::TIMESTAMPTZ
ORDER BY observed_at DESC, event_id DESC
LIMIT 500;
~~~

Đã có PK **(tenant_id, device_id, observed_at, event_id)**. PostgreSQL dùng B-tree cho PK, có thể **scan ngược** trên hai cột observed_at/event_id khi hai tiền tố tenant và device cố định. Vì vậy index khác với cùng cột nhưng DESC **có thể hoàn toàn dư thừa**.

### 11.1. Khi có filter metric_code thường xuyên

~~~sql
SELECT observed_at, event_id, value_num
FROM device_events
WHERE tenant_id = 11
  AND device_id = 8008
  AND metric_code = 'temperature'
  AND observed_at >= '2026-11-20 00:00:00+00'::TIMESTAMPTZ
ORDER BY observed_at DESC, event_id DESC
LIMIT 500;
~~~

PK cũ tìm theo device/time rồi lọc metric_code. Nếu một device có rất nhiều metric code và query chỉ chọn một loại, phương án thử:

~~~sql
CREATE INDEX idx_events_device_metric_recent
ON device_events (
    tenant_id, device_id, metric_code,
    observed_at DESC, event_id DESC
);
~~~

Index mới đáng giá khi giảm số hàng phải đọc đủ lớn; nếu một device chỉ có một metric hoặc query metric-specific hiếm, chi phí index có thể lớn hơn lợi ích.

### 11.2. BRIN dành cho scan thời gian với tương quan vật lý

Một job đọc **mọi event của một ngày trên tất cả device** có kiểu truy cập khác:

~~~sql
SELECT tenant_id, device_id, observed_at, metric_code, value_num
FROM device_events
WHERE observed_at >= '2026-11-20 00:00:00+00'::TIMESTAMPTZ
  AND observed_at <  '2026-11-21 00:00:00+00'::TIMESTAMPTZ;
~~~

Nếu event được chèn gần theo thứ tự observed_at và bảng rất lớn, **BRIN** trên observed_at có thể nhỏ hơn B-tree và giúp bỏ qua các vùng block ngoài khoảng:

~~~sql
CREATE INDEX idx_events_time_brin_candidate
ON device_events USING BRIN (observed_at)
WITH (pages_per_range = 64);
~~~

BRIN dựa vào **tương quan của dữ liệu với vị trí vật lý**, không cung cấp thứ tự từng device như B-tree. Late event, backfill ngược ngày hoặc ghi nhiều device/tenant trộn ngẫu nhiên có thể làm khoảng min/max rộng, tăng số block cần đọc; phải đo hiệu quả thực.

### 11.3. Khi nào partition theo thời gian?

Nếu cần xóa/archive dữ liệu theo tháng, scan theo khoảng ngày và dữ liệu tăng đều, có thể cân nhắc **RANGE partition by observed_at**. Một prototype riêng:

~~~sql
CREATE TABLE device_events_partitioned (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    event_id UUID NOT NULL,
    metric_code TEXT NOT NULL,
    value_num NUMERIC(18,5) NOT NULL,
    PRIMARY KEY (tenant_id, device_id, observed_at, event_id)
) PARTITION BY RANGE (observed_at);

CREATE TABLE device_events_2026_11
PARTITION OF device_events_partitioned
FOR VALUES FROM ('2026-11-01 00:00:00+00')
           TO   ('2026-12-01 00:00:00+00');

CREATE TABLE device_events_2026_12
PARTITION OF device_events_partitioned
FOR VALUES FROM ('2026-12-01 00:00:00+00')
           TO   ('2027-01-01 00:00:00+00');
~~~

PK chứa **observed_at** là partition key, phù hợp quy tắc UNIQUE/PK của bảng PostgreSQL partitioned. Nhưng không bảo đảm event_id duy nhất **bất kể timestamp**. Nếu cần event ID duy nhất toàn nguồn, phải có registry/dedup theo đúng source key hoặc hệ hỗ trợ uniqueness toàn cục. Không được đưa tính đúng vào rủi ro chỉ để có partition dễ xóa.

Một partition đơn lẻ cho tháng 11 **không tự chứa mọi event**: cần tạo đủ partition cho phạm vi dữ liệu hoặc default partition/chính sách xử lý timestamp ngoài dải. Phải xét late events, event time sai và khả năng partition cũ đã archive.

### 11.4. Đừng shard theo timestamp nếu quyết định cục bộ theo device

Nếu ghi/thao tác bắt buộc một chuỗi của device có invariant liên quan toàn chuỗi, shard theo ngày có thể đẩy các phần của cùng device sang nhiều owner. Có thể partition vật lý theo tháng **trong một DB** mà vẫn giữ logic owner theo device; nếu phân tán thật, thiết kế shard key và giao thức phải được đánh giá riêng.

**Quyết định Q8:** đọc recent series trước tiên dùng PK hiện có; thêm metric-specific index khi cần; BRIN/time partition chỉ để giải quyết **những query/retention khác** và đã kiểm chứng trên dữ liệu lớn.

## 12. Q9 — Lọc metadata JSONB: GIN hay cột typed?

Một số đối tác gửi metadata riêng. API tra các đơn mang sales_channel = affiliate:

~~~sql
SELECT order_id, created_at, total_amount_vnd
FROM sales_orders
WHERE tenant_id = 11
  AND metadata @> '{"sales_channel":"affiliate"}'::JSONB
ORDER BY created_at DESC
LIMIT 50;
~~~

### 12.1. GIN cho containment JSONB

Nếu filter containment linh hoạt và đủ phổ biến, PostgreSQL có thể dùng GIN:

~~~sql
CREATE INDEX idx_orders_metadata_containment_candidate
ON sales_orders USING GIN (metadata jsonb_path_ops);
~~~

**jsonb_path_ops** là một operator class phục vụ một số kiểu tra cứu JSONB như containment @>; không coi nó hỗ trợ mọi toán tử JSON giống nhau. Nếu ứng dụng thường tra **key tồn tại** qua toán tử ? hoặc yêu cầu đa dạng, phải xem operator class phù hợp (ví dụ jsonb_ops) và đo lại index size/plan.

Một GIN trên metadata **không thay tenant filter hay authorization**. Query phải vẫn kiểm tra tenant_id, và optimizer có thể kết hợp nhiều index hoặc chọn cách khác nếu containment không chọn lọc.

### 12.2. Nếu chỉ có một trường thường được tìm

Nếu sales_channel là một chiều nghiệp vụ ổn định, quan trọng cho query và báo cáo, nên cân nhắc **đưa thành cột typed**:

~~~sql
ALTER TABLE sales_orders
ADD COLUMN sales_channel TEXT;

-- Sau khi định nghĩa, backfill và writer tương thích:
CREATE INDEX idx_orders_channel_recent_candidate
ON sales_orders (tenant_id, sales_channel, created_at DESC, order_id DESC);
~~~

Việc thêm cột ở ví dụ là **phương án thiết kế**, chưa bao gồm migration dữ liệu thật. Để áp dụng production cần expand/backfill/validate/contract, quy tắc đồng bộ JSON và cột mới, xử lý NULL/UNKNOWN và writer cũ.

### 12.3. Khi không cần index JSONB

Nếu Q9 rất hiếm và số lượng Order được hạn chế trước bằng tenant + khoảng thời gian nhỏ, scan/filter trên một tập con có thể rẻ hơn GIN lớn. Không phải cứ có JSONB là mặc định tạo GIN. Đặc biệt với JSONB được cập nhật thường xuyên, chi phí cập nhật index có thể đáng kể.

**Quyết định Q9:** đo tính linh hoạt, cardinality của predicate và write overhead; GIN cho containment đa dạng, typed + B-tree cho chiều cố định quan trọng, hoặc chưa tạo index nếu chưa có lợi ích đo được.

## 13. Q10 — ReserveStock: index không chữa được race condition

Command ReserveStock cho tenant 11, warehouse 7, Product 101, quantity 2:

~~~sql
UPDATE stock_balances
SET reserved = reserved + 2
WHERE tenant_id = 11
  AND warehouse_id = 7
  AND product_id = 101
  AND on_hand - reserved >= 2
RETURNING on_hand, reserved;
~~~

PK **(tenant_id,warehouse_id,product_id)** đã giúp tìm đúng **một balance row**. Thêm index riêng trên reserved hoặc on_hand thường không giúp update này: điều kiện quan trọng phải được kiểm tra **trên hàng hiện tại sau khi lấy quyền cập nhật**, không tìm toàn bảng theo reserved.

### 13.1. Cách giải thích tính đúng

Nếu hai request cùng giữ hai chiếc cuối, cả hai không được “SELECT còn 2” rồi tự ghi số mới dựa trên bản đọc cũ. Conditional UPDATE trong transaction của một StockBalance owner cho phép chỉ lệnh hợp lệ cập nhật được hàng; request còn lại phải nhận **0 hàng RETURNING** và bị từ chối hoặc retry theo chính sách.

Tuy nhiên, chỉ một UPDATE balance **chưa đủ để chống duplicate operation_id**. Trong thiết kế hoàn chỉnh:

1. Tạo StockReservation có UNIQUE(tenant_id,operation_id).
2. Chỉ khi reservation là lệnh mới, thực hiện conditional UPDATE.
3. Nếu cập nhật không đủ hàng, rollback reservation mới.
4. Nếu đã có operation_id, kiểm tra payload và trả kết quả idempotent, không cộng reserved lần nữa.
5. Commit/rollback reservation và balance trong cùng transaction hoặc thiết kế protocol tương đương.

### 13.2. Hot row là vấn đề mô hình, không phải thiếu index

Khi hàng nghìn request cùng sửa một balance của SKU rất nóng, B-tree lookup đã nhanh nhưng các transaction vẫn phải **tranh khóa cùng một hàng**. Thêm index có thể làm update đắt hơn mà không tăng khả năng đồng thời của invariant.

Các phương án cần xem ở tầng mô hình/nghiệp vụ:

- Chia tồn theo warehouse nếu từng kho có hàng độc lập.
- Phân bổ quyền giữ hàng trước theo escrow/quota với tổng quyền không vượt hàng có thật.
- Dùng queue/serialization theo SKU khi SLA và business cho phép.
- Tách read model để giảm áp lực đọc lên owner.
- Giảm số cập nhật phụ không cần thiết trong transaction chính.

**Không tự chia một pool tồn chung thành nhiều shard cùng được quyền bán** nếu không có giao thức phân quyền an toàn. Đây là ví dụ điển hình nơi **tính đúng đứng trước throughput**.

**Quyết định Q10:** PK là index đủ cho lookup; cải thiện contention bằng thiết kế owner/quyền ghi, không bằng index trên số lượng.

## 14. Quy tắc kỹ thuật B-tree cần dùng khi chấm bài

Các quy tắc sau là điểm xuất phát để thiết kế ứng viên, **không phải thay thế optimizer hoặc benchmark**.

### 14.1. Equality, range, sort và tie-breaker

Với truy vấn:

~~~sql
SELECT order_id, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND customer_id = 9001
  AND created_at >= '2026-11-01'::TIMESTAMPTZ
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Index (tenant_id, customer_id, created_at DESC, order_id DESC) phù hợp vì equality thu hẹp tiền tố rồi range/order theo thời gian. Một index (created_at, tenant_id, customer_id) có thể khiến hệ phải đi qua nhiều tenant chỉ để tìm 50 Order của một Customer, đặc biệt khi có skew.

### 14.2. Index ghép không thay mọi index đơn

Một index (tenant_id, customer_id, created_at) thường thuận lợi cho query lọc tenant+customer, nhưng **không mặc định hiệu quả** cho query chỉ lọc tenant+created_at. PostgreSQL có thể chọn nhiều kế hoạch khác nhau, nhưng không được suy ra cột thứ ba có hiệu quả như cột thứ hai khi bỏ qua tiền tố.

### 14.3. Scan ngược và chiều sort hỗn hợp

B-tree có thể được scan ngược: PK ASC theo (tenant,device,time,event_id) có thể phục vụ order DESC trên **cả time và event_id** khi hai cột tiền tố bằng nhau. Nếu ORDER BY theo **time DESC, event_id ASC**, không thể chỉ đảo toàn bộ chiều scan để khớp cả hai; cần xét index có chiều sort hỗn hợp hoặc chấp nhận sort/incremental sort dựa trên plan thực.

### 14.4. INCLUDE và index-only scan

INCLUDE không tham gia tính toán thứ tự/range của key, chỉ giữ cột trả kết quả. Nó làm index lớn hơn và không luôn tạo Index Only Scan trên bảng UPDATE thường xuyên, vì PostgreSQL còn cần kiểm tra visibility map. Nếu SELECT * cần nhiều cột ngoài index, INCLUDE vài cột thường không biến truy vấn đó thành index-only.

### 14.5. Partial index là ràng buộc giữa query và predicate

Nếu index có WHERE status='PENDING', query phải chứng minh điều đó ở lúc lập plan. Những truy vấn dùng status parameter với generic plan có thể không tận dụng partial index dù giá trị runtime là PENDING. Cần thử **chính câu SQL và kiểu plan** của ứng dụng, không chỉ câu SQL viết tay trong console.

### 14.6. Index FK phía con không phải lúc nào cũng tự có

PK/UNIQUE phía cha cung cấp cấu trúc tra cứu FK, nhưng index trên **các cột FK phía con** không mặc định được tạo trong PostgreSQL. Khi xóa/sửa parent hoặc query theo parent, index con có thể quan trọng. Với OrderLine, PK (tenant_id,order_id,line_no) đã có tiền tố khóa tham chiếu Order nên không cần index riêng (tenant_id,order_id). Nhưng truy vấn tìm Line **theo Product** có thể cần (tenant_id,product_id,order_id), nếu workload thật đủ lớn.

### 14.7. Không quên tính đúng trước tốc độ

Một UNIQUE có thể phục vụ lookup nhưng không được bỏ nếu nghiệp vụ cần chống trùng. Một FK không được thay bằng “đọc thử cho nhanh”. Partial uniqueness khi business cho phép NULL/soft delete cần làm rõ scope và trạng thái trước khi viết DDL.

## 15. Bảng tổng hợp quyết định index từ từng truy vấn

| Truy vấn | Ứng viên đầu tiên | Vì sao | Điều phải đo |
| --- | --- | --- | --- |
| Q1 Order by tenant + ID | PK(tenant,order) | Equality trên PK | Heap reads và network |
| Q1 Lines of Order | PK(tenant,order,line_no) | Prefix + order | Lines/Order skew |
| Q2 recent Customer orders | (tenant,customer,created_at DESC,order_id DESC), INCLUDE chọn lọc | Equality + order + LIMIT | Sort, buffers, index size |
| Q3 pending FIFO | Partial (tenant,created_at,order_id) WHERE PENDING | Ít entry, đúng thứ tự | Pending ratio, status churn |
| Q4 paid recent | Partial (tenant,paid_at DESC,order_id DESC) WHERE PAID | Date range + order | Ngày nóng, UPDATE overhead |
| Q5 external ref | Unique (tenant,source,ref) WHERE ref IS NOT NULL | Idempotent business key | Duplicate/conflict, NULL |
| Q6 active category | Partial (tenant,category,product_id) WHERE active | Category paging | Active ratio, hot categories |
| Q6 lookup SKU | UNIQUE(tenant,sku) có sẵn | Identity lookup | Redundant indexes |
| Q7 top Product by period | Mart daily per tenant/date/product | GROUP BY + SUM rất nhiều Line | Freshness và correction |
| Q8 recent device events | PK(tenant,device,time,event_id) | Backward B-tree scan | Device skew, metric filter |
| Q8 all-device time range | BRIN(time) hoặc time partition | Append/range/retention | Correlation, late data |
| Q9 metadata containment | GIN JSONB, hoặc typed field B-tree | Predicate thực tế | Size, selectivity, writes |
| Q10 reserve stock | PK(tenant,warehouse,product) | Atomic one-row update | Lock contention |
| Q11 lookup order_code | UNIQUE(tenant,order_code) có sẵn | Equality lookup | Không thêm index trùng |
| Q12 inventory closing snapshot | FactInventoryDaily/columnar | Semi-additive by time | Chọn cuối kỳ, không SUM |

Đây là **danh sách ứng viên sau phân tích logic**, chưa phải danh sách lệnh phải chạy tất cả. Nhiều ứng viên có điều kiện, một số dùng index đã có, một số thay **mô hình đọc** thay vì index.

## 16. Khi nào chọn partition, BRIN, GIN hoặc mô hình phân tích?

### 16.1. Partition giải quyết quản trị và pruning, không thay mọi index

Partition theo tháng có ích nếu phần lớn query/retention sử dụng ngày và có hàng tỷ event. Partition theo tenant có thể giúp định tuyến/đồng vị trí một số giao dịch, nhưng sẽ phải xét skew: tenant lớn nhất chiếm 30% Orders có thể làm một partition/shard nóng.

**Không tách một bảng nhỏ thành hàng nghìn partition** chỉ vì có 2.000 tenant; số partition, metadata, planning overhead và maintenance cũng có chi phí. Chọn partition key từ **query, quản trị dữ liệu và bất biến**, không chỉ từ thuộc tính dễ chia.

Trong PostgreSQL, PRIMARY KEY/UNIQUE trên bảng partitioned có các hạn chế liên quan partition key. Nếu bảng partition theo created_at nhưng business key duy nhất là source_event_id không phụ thuộc ngày, phải có thiết kế registry/dedup khác; không tuyên bố uniqueness toàn cục khi chỉ dùng index từng partition.

### 16.2. BRIN phù hợp khi dữ liệu tương quan vật lý

BRIN thường nhỏ cho bảng append theo thời gian, lọc khoảng rộng và có tương quan giữa timestamp với vị trí block. Nếu dữ liệu tới muộn và sửa lịch sử nhiều, BRIN có thể ít hiệu quả; kiểm tra số heap blocks được đọc và mức recheck, không chỉ nhìn dung lượng index.

### 16.3. GIN cho cấu trúc hoặc tìm kiếm có toán tử hỗ trợ

GIN hữu ích cho containment JSONB, array hoặc tìm kiếm văn bản khi operator class thích hợp. Đổi lại, có chi phí cập nhật, dung lượng và khi query chứa tenant filter cần kiểm tra kết hợp các điều kiện. Một trường nghiệp vụ quan trọng, có schema ổn định có thể xứng đáng có cột typed và B-tree thay vì chôn sâu trong JSONB.

### 16.4. OLTP khác OLAP

**OLTP** cần commit đúng, lookup theo khóa, update từng aggregate và độ trễ nhỏ. **OLAP** cần scan và aggregate nhiều fact, nén dạng cột, partition theo ngày và dimension version.

Không cố biến một bảng Orders được tối ưu cho INSERT/UPDATE thành một fact mart bao phủ mọi truy vấn BI bằng 20 index. Cũng không đưa quyết định reserve hàng sang dashboard có độ trễ để giảm tải OLTP. Cần **source of truth** và **read model** với freshness SLA riêng.

### 16.5. Document và graph là các phương án có điều kiện

- **Document:** nhúng Line vào Order có thể tăng hiệu quả đọc Order trọn khối nếu Line có vòng đời cùng Order, nhưng phải đo kích thước document, write contention, truy vấn Product xuyên document và bảo vệ FK logic tới Customer/Product.
- **Graph:** hợp lý khi truy vấn chủ yếu duyệt nhiều bước như quan hệ sở hữu/phân quyền/phụ thuộc, chứ không chỉ vì có một vài FK. Cần đánh giá node/edge grain, tính không chu trình và bội số đường đi; B-tree trên Order vẫn thường hợp lý cho đọc theo ID.
- **Analytical column store:** phù hợp SUM/GROUP BY hàng trăm triệu dòng, nhưng phải có ETL/CDC, đối soát, version và đặc tả khi dữ liệu đến muộn.

**Chọn công nghệ phải gắn với mẫu truy vấn và invariant**, không chọn theo sở thích hoặc chỉ vì một sơ đồ có nhiều đường nối.

## 17. Đọc EXPLAIN: biến index thành giả thuyết có thể bác bỏ

Một lựa chọn vật lý chỉ nên được chấp nhận khi có bằng chứng phù hợp với workload. Trong PostgreSQL, **EXPLAIN** hiển thị kế hoạch của optimizer, còn **EXPLAIN ANALYZE** thực thi câu lệnh và ghi lại số đo của lần thực thi đó.

Ví dụ kiểm tra Q2:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, total_amount_vnd, created_at
FROM sales_orders
WHERE tenant_id = 11
  AND customer_id = 9001
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

### 17.1. Đọc những phần nào trong kế hoạch?

| Tín hiệu | Cách diễn giải | Câu hỏi cần hỏi tiếp |
| --- | --- | --- |
| **Seq Scan** | Quét tuần tự bảng hoặc partition | Bảng nhỏ nên quét rẻ, hay thiếu index phù hợp? |
| **Index Scan** | Đi theo index, có thể đọc heap | Số hàng được đọc và heap random I/O ra sao? |
| **Index Only Scan** | Có thể lấy cột từ index; vẫn có heap fetch | Visibility map đủ tốt chưa? |
| **Bitmap Index/Heap Scan** | Thu thập tập vị trí rồi đọc heap | Predicate có đủ chọn lọc? |
| **Sort / Incremental Sort** | Có thao tác sắp xếp bổ sung | Index có khớp ORDER BY và direction không? |
| **Hash Join / Nested Loop / Merge Join** | Các chiến lược join | Join key, fan-out và tập con có được giảm trước? |
| **estimated rows vs actual rows** | Khả năng ước lượng cardinality | Stats có cũ, skew/quan hệ cột bị bỏ sót? |
| **shared hit/read, temp read/write** | Bộ đệm và I/O | Có spill ra disk hoặc đọc quá nhiều blocks? |
| **loops và Rows Removed by Filter** | Số lần thực thi và số hàng loại | Có scan rộng rồi filter sau không? |
| **Planning Time / Execution Time** | Thời gian của một lần thử | Có đại diện cho p95 production không? |

Ví dụ **diễn giải giả định**, không phải output đã chạy:

~~~text
Trước index Q2:
  Sort -> Seq Scan on sales_orders
  Filter tenant_id/customer_id
  Nhiều rows bị loại, phải sort rồi LIMIT.

Sau index Q2:
  Limit -> Index Scan using idx_orders_customer_recent
  Index Cond: tenant_id=11 AND customer_id=9001
  Ít hoặc không cần sort, dừng gần LIMIT 50.

Cần xác minh:
  Actual rows, buffers, latency, index size,
  heap fetches, sự thay đổi khi tenant rất lớn.
~~~

Nếu optimizer vẫn dùng Seq Scan trên bảng thử 20 hàng, đó có thể là kế hoạch đúng. Không ép index chỉ vì đã tạo một index mới.

### 17.2. Kế hoạch tốt trên trung bình có thể sai với tenant nóng

Tỷ lệ trung bình của 20 triệu Order / 2.000 tenant không phản ánh tenant lớn chiếm 30%. Một query Q2 của Customer bình thường có 20 Order khác Customer doanh nghiệp có 500.000 Order. Phải thử:

- Tenant nhỏ, trung bình, lớn nhất.
- Customer ít và rất nhiều Order.
- PENDING hiếm so với PENDING chiếm tỷ lệ cao.
- Recent time range so với quét lịch sử dài.
- Khi index mới vừa tạo và sau khi dữ liệu thay đổi theo thời gian.

Dùng dữ liệu **giữ được skew và tương quan thực tế**, không chỉ random đều 20 triệu hàng.

### 17.3. Statistics và plan cache

Sau khi nạp dữ liệu đại diện, có thể cập nhật thống kê để optimizer biết phân bố mới:

~~~sql
ANALYZE sales_orders;
ANALYZE order_lines;
ANALYZE products;
ANALYZE device_events;
~~~

Không chạy ANALYZE bừa trong giờ cao điểm nếu nó ảnh hưởng tài nguyên; đây là bước của kế hoạch benchmark. Những cột có tương quan như tenant_id/status/customer_id có thể khiến estimate sai nếu thống kê không thể hiện đủ, cần xem phân bố và kế hoạch thực tế.

Prepared statements có thể sử dụng **custom plan hoặc generic plan**. Một partial index có status='PENDING' có thể không được chứng minh phù hợp nếu câu query lập plan với status = $1 chưa biết giá trị. Benchmark bằng **câu lệnh ứng dụng thật**, với bind parameters và chế độ plan thực tế; không dựa hoàn toàn vào SQL được thay literal thủ công trong console.

### 17.4. Đo index size và tần suất sử dụng

~~~sql
-- Ví dụ sau chỉ chạy khi index đã được tạo trong môi trường thử.
SELECT pg_size_pretty(
    pg_relation_size('idx_orders_customer_recent'::REGCLASS)
) AS index_size;

-- Thống kê chỉ mang tính quan sát trong khoảng hệ đã ghi nhận;
-- không phải bằng chứng tuyệt đối một index không cần thiết.
SELECT relname, indexrelname,
       idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE relname IN ('sales_orders','order_lines','products')
ORDER BY relname, indexrelname;
~~~

**idx_scan = 0** có thể vì khoảng quan sát ngắn, thống kê vừa reset hoặc nghiệp vụ hiếm chưa chạy; không tự DROP index. Với **UNIQUE/PK**, index còn bảo vệ constraint dù lượt đọc chủ động rất thấp.

Extension pg_stat_statements, nếu được cấu hình và cấp quyền, có thể cung cấp dữ liệu query workload; nó không luôn bật sẵn. Cần xem query log/APM và dấu vết truy cập trước khi kết luận một index thật sự không dùng.

## 18. Thiết kế thí nghiệm so sánh phương án

Chọn index bằng phép đo cần so **lợi ích đọc** với **chi phí ghi, lưu trữ, vận hành và thay đổi dữ liệu**.

### 18.1. Quy trình A/B trong môi trường thử

1. **Chốt SQL và dữ liệu đầu vào:** các truy vấn Q1–Q12, tenant distribution, lịch cập nhật trạng thái, date ranges.
2. **Đo baseline:** plan, actual rows, buffers, p50/p95/p99, số rows scanned/sorted.
3. **Chỉ thêm một nhóm index ứng viên** theo một giả thuyết. Không tạo toàn bộ index trong một lần rồi không biết cái nào có ích.
4. **ANALYZE khi thích hợp**, chạy lại query với nhiều giá trị bind và tenant nóng.
5. **Đo đường ghi:** INSERT Order, UPDATE status, UPDATE metadata, ReserveStock; xem WAL, index growth và CPU.
6. **Thử độ ổn định:** chạy khi dữ liệu lớn hơn, query cùng lúc, cache nóng/lạnh và kế hoạch không ổn định.
7. **Giữ, chỉnh hoặc loại index:** ghi quyết định bằng bằng chứng, không chỉ câu “query nhanh hơn”.
8. **Thử rollback triển khai:** index không đạt phải có cách bỏ an toàn mà không xóa index phục vụ constraint.

### 18.2. Mẫu bảng kết quả thí nghiệm

| Metric | Baseline | Ứng viên A | Ứng viên B | Nhận xét |
| --- | --- | --- | --- | --- |
| Q2 p95 (ms) | Chưa đo | Chưa đo | Chưa đo | Mục tiêu giả định < 150 |
| Q2 Buffers read | Chưa đo | Chưa đo | Chưa đo | So cùng dữ liệu/cách chạy |
| Q3 p95 (ms) | Chưa đo | Chưa đo | Chưa đo | Partial vs general |
| Order INSERT p95 | Chưa đo | Chưa đo | Chưa đo | Write overhead |
| Status UPDATE p95 | Chưa đo | Chưa đo | Chưa đo | Partial index churn |
| Database/index size | Chưa đo | Chưa đo | Chưa đo | Tổng dung lượng |
| WAL/replication lag | Chưa đo | Chưa đo | Chưa đo | Chi phí vận hành |

**Chưa đo phải ghi “Chưa đo”.** Không tự điền số giả như thể đã chạy EXPLAIN/benchmark; các ngưỡng của bài là giả định học tập.

### 18.3. Tổng chi phí sở hữu mới là thước đo

Một index tăng tốc query từ 200 ms xuống 20 ms nhưng làm 100.000 INSERT/ngày, nhiều UPDATE và replica lag tăng mạnh có thể không đáng giữ nếu query đó chỉ chạy ba lần/tuần.

Ngược lại, một UNIQUE index tăng chi phí ghi nhưng là **điều kiện chống duplicate tiền/đơn** không thể bị bỏ chỉ để tối ưu throughput. Tối ưu index không được phá invariant.

### 18.4. Thử dữ liệu lệch và biến động

Một index phù hợp tuần này có thể mất tác dụng nếu:

- 90% Order chuyển từ PENDING sang PAID mỗi giờ, khiến partial index churn lớn.
- Tenant mới có số Order gấp hàng trăm lần median.
- Product category trở nên rất đông, pagination chuyển sang trang sâu.
- Metadata trở thành bộ lọc chính và GIN tăng kích thước.
- Device event đến muộn nhiều, làm BRIN min/max rộng.
- Báo cáo đổi từ gross line amount sang net after refunds, cần mô hình fact khác.

Thiết kế cần có **review triggers**, không mặc định một index bất biến qua mọi vòng đời sản phẩm.

## 19. Chi phí ghi, contention và những index dư thừa

### 19.1. Mỗi index cũng là cấu trúc phải bảo trì

Một INSERT vào SalesOrder có thể cần cập nhật:

- PK(tenant_id,order_id).
- UNIQUE(tenant_id,order_code).
- Partial UNIQUE external reference nếu có reference.
- Index recent Customer.
- Index PENDING FIFO nếu tạo trạng thái PENDING.
- Index PAID khi status và paid_at thỏa predicate.
- Index JSONB nếu có.
- Những index khác được thêm.

Mỗi index có chi phí I/O, WAL, cache, vacuum, backup và đôi khi lock/độ trễ. **Không có “index miễn phí”**; việc tạo 10 index để cứu 2 query có thể là tối ưu cục bộ nhưng làm write path tổng thể tệ hơn.

### 19.2. UPDATE trạng thái ảnh hưởng partial indexes

Khi Order chuyển PENDING → PAID:

- Entry tại idx_orders_pending_fifo không còn thuộc predicate.
- Entry tại idx_orders_paid_recent có thể được thêm.
- Những index khác có thể cần bảo trì tùy cột cập nhật.
- Tỷ lệ chuyển trạng thái cao có thể gây bloat/overhead.

Không được coi partial index luôn nhỏ và rẻ trong mọi workload; phải đo **tỷ lệ hàng thuộc predicate và tốc độ thay đổi thành viên**.

### 19.3. Cột INCLUDE ít cập nhật hay nhiều cập nhật?

Nếu total_amount_vnd thường xuyên được điều chỉnh trong DRAFT, INCLUDE(total_amount_vnd) ở index Q2 có thể làm thêm công việc mỗi lần update. Một phương án ít cột hơn:

~~~sql
-- Ứng viên tối giản cần so với INCLUDE.
CREATE INDEX idx_orders_customer_recent_min_candidate
ON sales_orders (
    tenant_id, customer_id, created_at DESC, order_id DESC
);
~~~

Không mặc định giữ cả **idx_orders_customer_recent** và **_min_candidate** cùng lúc. Chọn một sau benchmark về heap fetch, write p95, index size và thay đổi giá.

### 19.4. Index trùng tiền tố và giới hạn của việc bỏ bớt

Một index (tenant_id,customer_id,created_at) có thể hỗ trợ một số query chỉ lọc tenant+customer, nên index (tenant_id,customer_id) có thể dư thừa. Nhưng cần xét:

- Index ngắn có thể nhỏ hơn, giúp query lookup đơn giản và caching.
- Các phiên bản SQL khác có ORDER BY/INCLUDE khác.
- Index UNIQUE không tương đương nonunique nếu cần bảo vệ constraint.
- FK phía con và đường UPDATE/DELETE parent có thể cần một index phục vụ riêng.

Không suy ra “index A là tiền tố của B nên chắc chắn xóa A” mà chưa đo và chưa kiểm tra ràng buộc.

### 19.5. Hot row không được chữa bằng secondary index

ReserveStock cập nhật đúng một StockBalance row, nhưng nhiều transaction vẫn tranh lock tại row đó. Thêm index trên reserved hay on_hand thường **không làm số lượng hot-key commits song song tăng lên**; đôi khi còn tăng chi phí UPDATE.

Nếu bất biến tồn kho phải đúng, chiến lược vật lý phải được chọn cùng với **owner, escrow/partition theo nguồn hàng, transaction và idempotency**. Chỉ số p95 phải được đo dưới contention thực.

## 20. Triển khai index trên bảng lớn mà không phá hệ thống

Một chỉ mục được thiết kế đúng nhưng triển khai thiếu kiểm soát cũng có thể làm gián đoạn ứng dụng.

### 20.1. Tạo index thông thường hay CONCURRENTLY?

Trong PostgreSQL, CREATE INDEX thông thường có thể chặn một số thao tác ghi trong thời gian build. CREATE INDEX CONCURRENTLY là lựa chọn cần cân nhắc cho bảng đang nhận traffic, đổi lại có quy trình build phức tạp hơn và vẫn dùng I/O/CPU, không đồng nghĩa “không có tác động”.

~~~sql
-- Ví dụ ứng viên triển khai riêng trên hệ thống đang hoạt động:
-- KHÔNG chạy trong transaction block PostgreSQL.
CREATE INDEX CONCURRENTLY idx_orders_customer_recent_live
ON sales_orders (
    tenant_id, customer_id, created_at DESC, order_id DESC
);
~~~

Câu trên là **phương án thay thế** cho index Q2 trong ví dụ, không được tạo thêm khi idx_orders_customer_recent đã tồn tại và phục vụ đầy đủ cùng mục đích. Khi triển khai thật phải chọn tên và phiên bản chỉ mục phù hợp để tránh trùng.

**CREATE INDEX CONCURRENTLY không được đặt bên trong BEGIN/COMMIT**. Nếu build thất bại vì duplicate với UNIQUE hoặc lỗi vận hành khác, có thể để lại index chưa hợp lệ; phải kiểm tra trạng thái catalog và có kế hoạch cleanup/retry. Không coi việc trả lỗi từ DDL là toàn hệ tự quay về sạch sẽ.

### 20.2. Migration có nhiều bước

Một lộ trình:

1. Thu thập workload thực, snapshot/backup và baseline trước triển khai.
2. Thử index trên staging với dữ liệu cùng phân bố và đủ quy mô.
3. Ước lượng disk/WAL, replication lag và cửa sổ vận hành.
4. Build index theo kỹ thuật phù hợp (CONCURRENTLY khi cần và được hỗ trợ).
5. Kiểm tra index hợp lệ, chạy ANALYZE khi phù hợp.
6. Đo lại query plans với bind parameters và nhiều tenant.
7. Theo dõi INSERT/UPDATE/replication sau rollout, không chỉ read latency.
8. Giữ một khoảng quan sát trước khi xóa index cũ có thể còn cần.
9. Ghi runbook nếu build dừng, disk đầy, replica lag hoặc index invalid.
10. Cập nhật ADR và quyết định khi nào phải review lại.

Nếu phải **thay shard key hoặc partition key**, đó không còn là một CREATE INDEX đơn giản: cần backfill, routing, fencing, đối soát và tránh hai owner cùng được ghi.

### 20.3. DROP index cũng cần an toàn

Có thể nghiên cứu DROP INDEX CONCURRENTLY để giảm gián đoạn khi bỏ index thông thường trên PostgreSQL đang hoạt động, nhưng nó có giới hạn và **không được đặt trong transaction block**. Không được drop index phục vụ UNIQUE/PK như một index dư thừa mà chưa xét constraint; cần review bằng chứng rằng nó không còn bảo vệ nghiệp vụ.

### 20.4. An toàn vận hành

Cần ghi rõ người chịu trách nhiệm, thời điểm, timeout, disk budget và cách dừng. Index mới có thể làm **replica tụt lag**, tăng WAL và gây chậm viết dù query thử nhanh hơn. SLO gồm cả dữ liệu cập nhật, không chỉ phản hồi của SELECT.

## 21. Bài thực hành thiết kế hoàn chỉnh theo hai vòng

Thay vì học thuộc danh sách index, hãy làm từng vòng.

### 21.1. Vòng A — thiết kế tối thiểu

Với workload ở phần 2, đề xuất chỉ thêm những gì chưa được PK/UNIQUE bảo vệ:

| Quyết định | Trạng thái ban đầu | Giải thích |
| --- | --- | --- |
| PK Order/Line/Product/Stock | Giữ | Identity và lookup Q1/Q10 |
| UNIQUE OrderCode/ProductSKU | Giữ | Business key Q11/Q6 |
| idx_orders_customer_recent | Thử thêm | Q2 rất thường xuyên |
| idx_orders_pending_fifo | Thử thêm | Q3 FIFO khi PENDING hiếm |
| idx_orders_paid_recent | Thử thêm | Q4 và là ứng viên hỗ trợ Q7 |
| ux_orders_external_source | Thêm nếu invariant đã được duyệt | Q5 uniqueness/dedup |
| idx_products_active_category | Thử thêm | Q6 browse active |
| idx_events_device_metric_recent | Chưa thêm | Q8 không filter metric ở query chính |
| idx_orders_metadata_containment | Chưa thêm | Q9 ít dùng, cần đo |
| BRIN/time partition | Đánh giá riêng | Q8 retention/time scan khác recent device |
| product_sales_daily | Thiết kế prototype projection | Q7 dashboard tổng hợp lớn |

Vòng A ưu tiên **ít index, đúng invariant và query quan trọng**. “Chưa thêm” là một quyết định có lý do, không phải bỏ sót.

### 21.2. Vòng B — điều chỉnh theo kết quả đo

Giả sử **chưa có kết quả đo** và một lần review đặt các giả thuyết sau:

- Q2 vẫn phải sort: kiểm tra index direction/predicate và SQL thật.
- Q3 generic prepared plan không dùng partial: thử literal predicate hoặc so index tổng quát.
- Q4 ghi nhiều trạng thái: xem chi phí partial index churn.
- Q7 quá nhiều Line: chuyển sang daily aggregate và ghi rõ freshness.
- Q8 có filter metric_code nhiều: thử index có metric_code trước thời gian.
- Q9 trở thành query trọng yếu: thử GIN hoặc typed sales_channel.
- Q10 có lock wait lớn: xem lại owner/escrow; không thêm index vô mục tiêu.

Không được điền kết quả “đã cải thiện x lần” cho các giả thuyết chưa được đo.

### 21.3. Cách trình bày lựa chọn trong design review

Mỗi index/projection đề xuất nên có một mục ngắn:

~~~text
Candidate:
  idx_orders_customer_recent

Supports:
  Q2, 50 Order mới nhất của một Customer trong một tenant.

Query shape:
  Equality tenant_id + customer_id;
  ORDER BY created_at DESC, order_id DESC;
  LIMIT 50; keyset pagination.

DDL:
  B-tree (tenant_id, customer_id, created_at DESC, order_id DESC)
  INCLUDE(status,total_amount_vnd) nếu có bằng chứng.

Expected benefit:
  Đọc ít hàng hơn, tránh sort rộng.

Expected cost:
  Index storage/WAL, INSERT và UPDATE overhead.

Test:
  EXPLAIN (ANALYZE, BUFFERS) trên tenant nhỏ/lớn,
  p95/p99, heap fetches, insert/update p95.

Decision status:
  PROPOSED — chưa đo; không tự gán PASS.
~~~

Đây là cách biến “em nghĩ index này tốt” thành một **giả thuyết có thể chứng minh hoặc bác bỏ**.

## 22. Bài tập tự luyện kèm hướng dẫn giải

### Bài 1. Index thừa cho Order detail

**Đề:** Order có PK(tenant_id,order_id). Một đồng nghiệp đề xuất CREATE INDEX(order_id) chỉ để đọc một Order theo cả tenant và ID. Nên đồng ý không?

**Gợi ý giải:** Không mặc định. PK ghép đã phục vụ equality theo cả hai cột, giữ scope tenant và identity. Index(order_id) làm thêm write cost mà chưa có query được chứng minh cần.

### Bài 2. Recent orders và thứ tự khóa

**Đề:** Q2 lọc tenant_id, customer_id, sort created_at DESC và order_id DESC. Chọn giữa A=(created_at,tenant_id,customer_id) và B=(tenant_id,customer_id,created_at DESC,order_id DESC).

**Gợi ý giải:** B phù hợp hơn với equality prefix, sau đó sort/limit. A có thể phải đi qua nhiều tenant/customer theo thời gian. Chốt bằng plan và workload thật.

### Bài 3. OFFSET sâu

**Đề:** Khách có 500.000 Order, yêu cầu trang 3.000 với LIMIT 50. Có thể chỉ thêm INCLUDE rồi giải quyết?

**Gợi ý giải:** Không. OFFSET sâu vẫn phải bỏ qua nhiều hàng. Dùng keyset cursor (created_at,order_id) theo sort ổn định; xét snapshot/cutoff khi có dữ liệu mới.

### Bài 4. Partial hay index status chung?

**Đề:** Chỉ 2% Order có PENDING, query FIFO luôn ghi status='PENDING'. Chọn index gì?

**Gợi ý giải:** Thử partial (tenant_id,created_at,order_id) WHERE status='PENDING'. Nếu query prepared generic parameter hoặc status thường thay đổi nhanh, cần benchmark và cân nhắc index (tenant_id,status,created_at,order_id) tổng quát.

### Bài 5. Source reference và uniqueness

**Đề:** Hai đối tác cùng phát reference X-100 nhưng độc lập. Một đối tác gửi lại cùng reference hai lần. Khóa duy nhất nên có cột nào?

**Gợi ý giải:** Theo giả định bài, (tenant_id, source_system, source_order_ref) khi reference không NULL. Với retry cùng ID phải kiểm tra payload; cùng ID khác payload là conflict. Không UNIQUE(reference) toàn hệ.

### Bài 6. Active Product và category

**Đề:** Product active chiếm 20%, API truy vấn chỉ active của category 501 theo product_id. Index đơn trên is_active có tối ưu chưa?

**Gợi ý giải:** Cần xét (tenant_id,category_id,product_id) WHERE is_active; index boolean đơn không đáp ứng tốt equality tenant/category và order. Đo theo các category đông nhất.

### Bài 7. Tìm tên chứa chuỗi bất kỳ

**Đề:** Q6 thay thành product_name ILIKE '%tai nghe%'. Có thể dùng B-tree(product_name) thông thường và đảm bảo tốt?

**Gợi ý giải:** Không cho wildcard đầu chuỗi. Có thể thử pg_trgm GIN/GiST nếu extension được phép, hoặc search service; kiểm tra ngôn ngữ, selectivity và write cost.

### Bài 8. Top Product theo kỳ

**Đề:** Chỉ mục trên order_lines(product_id,unit_price_vnd) có tự trả top 10 Product có tổng doanh thu trong tháng không?

**Gợi ý giải:** Không. Tổng theo Product phải group các Line đã bán trong tháng và gắn ngày/thanh toán từ Order. Với dữ liệu lớn, thử fact/aggregate daily có grain và freshness rõ; index hỗ trợ join/filter nhưng không thay SUM.

### Bài 9. Đọc recent DeviceEvent

**Đề:** PK(tenant_id,device_id,observed_at,event_id). Query theo tenant+device, ORDER BY observed_at DESC,event_id DESC LIMIT 500. Có nhất thiết cần index DESC riêng không?

**Gợi ý giải:** Không. PostgreSQL có thể scan ngược B-tree với hai cột hậu tố cùng hướng DESC. Đo plan trước khi tạo index trùng.

### Bài 10. BRIN trong dữ liệu đến muộn

**Đề:** DeviceEvent ghi ngược các tháng cũ liên tục; BRIN(observed_at) vẫn luôn tốt chứ?

**Gợi ý giải:** Không. BRIN hiệu quả khi thời gian tương quan với vị trí block; late data/backfill có thể mở rộng min/max, tăng block recheck. Cần đo và so với B-tree/partition.

### Bài 11. JSONB filter chủ đạo

**Đề:** sales_channel trở thành filter của 70% truy vấn Order. Giữ trong metadata và một GIN chung là lựa chọn mặc định tốt nhất?

**Gợi ý giải:** Không. Thử promoted typed column + B-tree theo tenant/channel/time; cần migration/dual-write và so GIN vs typed index bằng workload thật.

### Bài 12. Hot stock row

**Đề:** Một SKU hot có p99 update rất cao dù PK lookup rất nhanh. Tạo index(reserved) có giải quyết không?

**Gợi ý giải:** Không chữa tranh khóa trên cùng row. Cần xem concurrency, owner, escrow/quota nếu business cho phép và chi phí mỗi transaction. PK đã đủ tìm hàng.

### Bài 13. JOIN làm nhân số

**Đề:** Một Order có 4 Line và 3 PaymentAttempt. JOIN cả hai rồi SUM amount_attempt tạo bao nhiêu hàng và sai gì?

**Gợi ý giải:** Có thể tạo 4×3=12 hàng, mỗi Attempt bị nhân bốn lần. Tổng hợp hai tập con theo (tenant_id,order_id) trước khi JOIN, phân biệt attempt thành công và callback trùng.

### Bài 14. Tenant lớn và chiến lược partition

**Đề:** 30% Orders thuộc một tenant, nhóm định chia 2.000 hash partition mỗi tenant một partition. Có chắc cân bằng và dễ quản trị?

**Gợi ý giải:** Không. Tenant nóng vẫn nóng; nhiều partition gây planning/metadata/maintenance overhead. Cần đo skew, query scope, routing, partition count và phương án chia hot tenant khi cần mà không phá transaction/uniqueness.

### Bài 15. INCLUDE và cập nhật thường xuyên

**Đề:** Index Q2 INCLUDE total_amount_vnd nhưng Order DRAFT sửa total_amount liên tục, index-only scan rất ít. Nên giữ INCLUDE?

**Gợi ý giải:** Chỉ khi benefit đo được vượt cost. So với index nhỏ không INCLUDE, đo heap fetches, write p95, size và cache; có thể bỏ INCLUDE.

### Bài 16. Sai thống kê và plan

**Đề:** Một query chạy rất nhanh với tenant nhỏ nhưng rất chậm với tenant lớn. Đã có index nhưng có thể đánh dấu PASS?

**Gợi ý giải:** Chưa. Benchmark theo skew/hot tenant, xem estimated vs actual rows, plan cache và statistics. Cần chọn threshold theo workload, không lấy trung bình che tail latency.

### Bài 17. Tạo index trực tiếp trên production

**Đề:** Một index mới cần build trên 20 triệu Order. Team muốn đặt CREATE INDEX CONCURRENTLY trong transaction migration BEGIN/COMMIT. Có hợp lệ?

**Gợi ý giải:** Không với PostgreSQL. Cần tách DDL riêng, lên ngân sách disk/WAL/replication, có runbook kiểm tra invalid index và rollback/forward-fix.

### Bài 18. Unique event ID qua time partition

**Đề:** Event partition theo tháng, PK có observed_at. Cùng event_id nhưng timestamp bị sửa sang tháng sau có được ngăn?

**Gợi ý giải:** Không nếu khóa unique chứa timestamp. Cần dedup theo ID nguồn độc lập thời gian tại owner/registry hoặc công nghệ hỗ trợ ràng buộc toàn cục tương ứng.

### Bài 19. Snapshot inventory trong warehouse

**Đề:** Tồn cuối ngày 20 chiếc và bản correction còn 18 chiếc. Dashboard cộng 20+18 ra 38 để báo “tồn” có đúng không?

**Gợi ý giải:** Không. Đây là hai phiên bản của cùng snapshot grain. Chọn bản hợp lệ theo cutoff/version; khi tổng hợp thời gian cần phép tính phù hợp, không SUM giá trị trạng thái như transaction delta.

### Bài 20. Nhiều index có tên khác nhưng cùng key

**Đề:** PK(tenant_id,order_id) và một index mới (tenant_id,order_id) chỉ khác tên. Team bảo “index riêng đọc nhanh hơn PK”. Nên làm gì?

**Gợi ý giải:** Cần bác bỏ giả thuyết bằng plan và inventory index. Cùng key/order, PK đã có B-tree phục vụ lookup. Index trùng thường chỉ tăng disk/write cost; không tạo nếu không có yêu cầu/cơ chế khác được chứng minh.

## 23. Thang chấm bài thiết kế vật lý

Một bản nộp có thể được đánh giá theo thang **100 điểm** dưới đây; đây là thang học tập minh họa, không phải chính sách công ty.

| Nhóm | Điểm tối đa | Thế nào là đạt |
| --- | ---: | --- |
| Hiểu query và workload | 20 | Có Q1–Q12, filter/sort/limit/joins, skew, SLO |
| Grain và bất biến | 15 | Khóa/tenant/đơn vị/vòng đời đúng, không phá FK/UNIQUE |
| Chọn index B-tree/partial/covering | 20 | Thứ tự key đúng, sử dụng index sẵn có, tránh trùng |
| Chọn BRIN/GIN/partition/OLAP | 15 | Đúng kiểu truy vấn, hiểu giới hạn |
| Bằng chứng EXPLAIN và benchmark | 15 | Có plan/rows/buffers, đa tenant và write cost |
| Rollout và vận hành | 10 | Index build, retry, WAL, rollback, monitoring |
| Giải thích đánh đổi | 5 | Nêu vì sao **không** tạo một số index |

**Điểm loại trừ quan trọng:** dù điểm tổng cao, bài vẫn **không đạt** nếu đề xuất bỏ isolation tenant, bỏ uniqueness cần thiết hoặc dùng cache trễ để đưa ra quyết định oversell. Bất biến P0 không được bù bằng tối ưu p95.

### 23.1. Một lời giải đạt chất lượng review

Người học phải nộp:

1. Workload matrix với tần suất và dữ liệu giả định đã ghi nhãn.
2. DDL mô hình vật lý hoặc sơ đồ physical entities và scope khóa.
3. Từng index proposal có query owner, DDL, expected benefit và cost.
4. Danh sách index **không cần thêm** vì PK/UNIQUE sẵn có.
5. Giải thích query nào cần projection/warehouse thay vì thêm index.
6. Kịch bản EXPLAIN/benchmark với số đo thực hoặc đánh dấu **NOT RUN**.
7. Những invariant, quyền truy cập, lịch sử và migration risks phải bảo vệ.
8. Quyết định cuối GO/TEST MORE/REJECT kèm điều kiện và người chịu trách nhiệm.

## 24. Checklist trước khi triển khai lựa chọn vật lý

- [ ] Đã định nghĩa **một hàng** của từng bảng/fact, khóa, bội số và scope tenant/source.
- [ ] Các câu SQL thực tế có WHERE/JOIN/ORDER BY/LIMIT và bind patterns rõ.
- [ ] Đã đo ước lượng số hàng/tần suất, data skew, hot keys và SLO.
- [ ] Đã lập inventory PK/UNIQUE/index sẵn có; không tạo index trùng vô lý.
- [ ] Thứ tự cột B-tree đúng equality/range/order; chiều sort và tie-breaker đúng.
- [ ] Index partial có predicate phù hợp với cách query được lập plan.
- [ ] INCLUDE được chứng minh đáng chi phí ghi/index-only, không thêm theo cảm tính.
- [ ] GIN/BRIN/partition được dùng cho workload thực sự phù hợp và thử với late/skew data.
- [ ] Q7/Q12 có measure grain, additive rules và nguồn sự thật rõ; không SUM snapshot tùy ý.
- [ ] Những query dài hoặc dashboard đã được cân nhắc tách read model có SLA freshness.
- [ ] Stock/Payment/Order invariants vẫn có owner, transaction và idempotency phù hợp.
- [ ] Truy vấn/caching/index không làm lộ tenant khác; có negative authorization tests.
- [ ] EXPLAIN/ANALYZE trên dữ liệu đại diện được lưu, ghi rõ test thật hay chỉ giả thuyết.
- [ ] Read p95/p99 được so với INSERT/UPDATE p95, WAL, replica lag và index size.
- [ ] Có kế hoạch migration, CREATE INDEX CONCURRENTLY khi phù hợp, cleanup invalid index và rollback.
- [ ] Có kế hoạch theo dõi stats và review lại khi workload/schema/scale thay đổi.
- [ ] Chưa có số đo thì đánh dấu **PROPOSED/NOT RUN**, không tuyên bố production SLO đã đạt.

## 25. Ghi nhớ

- **Chọn mô hình vật lý từ truy vấn thật**, không từ danh sách tên cột.
- **PK/UNIQUE cũng tạo index:** nhiều query định danh đã có đường truy cập; index bổ sung có thể dư thừa.
- **Index ghép phải khớp equality, range, sort và tie-breaker**; keyset pagination tránh chi phí OFFSET sâu.
- **Partial index** tốt khi predicate cố định và tập con nhỏ, nhưng status churn/generic prepared plan có thể làm lợi ích khác dự kiến.
- **INCLUDE** có thể giảm heap fetch nhưng làm index lớn hơn; index-only scan còn phụ thuộc visibility.
- **BRIN** dựa vào tương quan vật lý, **GIN** dựa vào toán tử/operator class, **partition** phục vụ pruning và vận hành — không thay mọi B-tree hoặc ràng buộc.
- **Top aggregate trên hàng triệu Line là bài toán mô hình đọc**: dùng grain và mart đúng, không chỉ thêm index lên cột SUM.
- **Hot row tồn kho là bài toán concurrency/ownership**, không phải thiếu index.
- **Một bản kế hoạch EXPLAIN không phải bằng chứng đã chạy**; chỉ tuyên bố đạt p95 khi đo với workload đại diện.
- **Tối ưu là cân bằng toàn hệ**: query latency, write throughput, disk/WAL, migration, bảo mật và khả năng tiến hóa.

Một lựa chọn vật lý tốt không phải lựa chọn tạo nhiều index nhất hoặc tạo ra một EXPLAIN đẹp nhất trong phòng thử. Đó là lựa chọn **giải thích được từ từng truy vấn, bảo vệ đúng bất biến, đo được lợi ích và chi phí, và có thể điều chỉnh an toàn khi dữ liệu và nghiệp vụ thay đổi**.




