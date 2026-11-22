# Đo truy vấn đọc, chi phí ghi và dung lượng trên dữ liệu đại diện

## 1. Kiểm chứng thiết kế dữ liệu bằng đo lường, không bằng cảm giác

Một mô hình dữ liệu có thể đúng về **thực thể, quan hệ và ràng buộc** nhưng vẫn không đáp ứng được hệ thống thật: trang chi tiết đơn đọc chậm, mỗi lần cập nhật phải duy trì quá nhiều chỉ mục, hoặc kho lưu trữ phình nhanh hơn ngân sách. Ngược lại, một lược đồ nhìn có vẻ nhiều JOIN chưa chắc chậm nếu dữ liệu, chỉ mục và truy vấn thực tế được tổ chức hợp lý.

**Kiểm chứng thiết kế bằng benchmark** là đặt các phương án trên **cùng khối lượng, phân phối và cách sử dụng dữ liệu đại diện**, đo đồng thời:

- **Đọc:** độ trễ từ phía người dùng và ở database, throughput, số hàng/quãng dữ liệu quét, I/O, khả năng sử dụng index, tỉ lệ truy vấn vượt SLO.
- **Ghi:** transaction/giây, thời gian commit, chi phí cập nhật index, WAL, lock contention, dead tuples, autovacuum, replication lag và ảnh hưởng lên truy vấn đọc.
- **Dung lượng:** dung lượng dữ liệu chính, index, TOAST, WAL, dữ liệu dẫn xuất, partition, bản sao, backup và tốc độ tăng theo thời gian.
- **Tính đúng:** cùng một dữ liệu phải sinh cùng kết quả nghiệp vụ; không “tối ưu” bằng cách làm mất bản ghi, bỏ ràng buộc, đọc sai mốc hoặc đếm trùng.
- **Khả năng vận hành:** mức phụ thuộc vào cache, skew của tenant, dữ liệu đến muộn, lỗi node, backfill và thời gian khôi phục.

Bài toán không phải “thực hiện `EXPLAIN` rồi chọn phương án có cost nhỏ nhất”. Cần có **mô hình khối lượng công việc (workload)**, mục tiêu chấp nhận, dataset tái tạo được, cách đo rõ ràng và quyết định có bằng chứng.

### Ví dụ xuyên suốt

Một nền tảng bán hàng đa tenant cần lưu **Order**, **OrderLine** và **PaymentMovement**. Đội phát triển đang cân nhắc:

- **A — Chuẩn hóa:** bảng đơn và dòng hàng riêng, chỉ mục cơ bản.
- **B — Chuẩn hóa có chỉ mục theo đường đọc chủ đạo:** thêm chỉ mục tổng hợp/covering index thích hợp.
- **C — B cộng thêm dữ liệu tổng hợp theo ngày:** phục vụ báo cáo nhanh hơn nhưng phát sinh chi phí cập nhật và độ trễ.

Ba phương án **chỉ so sánh công bằng** khi cùng định nghĩa grain, số tiền, trạng thái nghiệp vụ, dữ liệu nguồn và chính sách nhất quán; nếu C trả số liệu trễ ba phút, mức trễ đó phải nằm trong điều kiện chấp nhận.

## 2. Chốt yêu cầu bằng workload, bất biến và giới hạn

Trước khi tạo hàng triệu dòng thử nghiệm, hãy viết một bảng mục tiêu:

| Nhóm | Ví dụ điều kiện nghiệm thu *minh họa* | Cần đo ở đâu? |
| --- | --- | --- |
| Đọc đơn theo ID (Q1) | P95 ≤ 80 ms ở 300 yêu cầu/giây; P99 theo SLO riêng. | End-to-end từ client, gồm header và lines. |
| Danh sách đơn gần đây của tenant (Q2) | P95 ≤ 150 ms ở mức tải chuẩn; tối đa 50 dòng/trang. | Client latency + kế hoạch SQL. |
| Báo cáo tổng doanh số ngày (Q3) | P95 ≤ 2.000 ms; dữ liệu chậm tối đa 5 phút nếu dùng mart. | Query, freshness và đối soát. |
| Tạo đơn 3 dòng hàng (W1) | P95 commit ≤ 120 ms ở 120 transaction/giây. | Client, DB transaction, WAL và lock. |
| Cập nhật trạng thái (W2) | Không làm sai state machine; đáp ứng mục tiêu ghi. | Transaction kết quả đúng và chi phí duy trì index. |
| Dung lượng | Bản chính + index nằm trong ngân sách được phê duyệt ở năm thứ hai. | Số byte thực đo và dự báo tăng trưởng. |
| Tính đúng | Không trùng business key, không nhân tổng tiền, không lẫn tenant. | PK/FK/CHECK và phép đối soát. |

**Những ngưỡng trên chỉ là đề bài giả định, không phải kết quả đã benchmark hoặc khuyến nghị SLO phổ quát.** Trong dự án thật, con số phải xuất phát từ trải nghiệm người dùng, ngân sách, tỷ lệ lưu lượng đỉnh và thỏa thuận nghiệp vụ.

Một workload không chỉ nói “80% read, 20% write”; phải có **hình dạng yêu cầu**:

- Q1 đọc một đơn theo `(tenant_id, order_id)`, kèm 1–N dòng.
- Q2 lọc tenant và khoảng thời gian, sắp xếp gần nhất, lấy trang đầu.
- Q3 tổng hợp theo ngày và tiền tệ, có thể quét hàng triệu dòng.
- W1 tạo đơn và các dòng trong một transaction.
- W2 đổi trạng thái khi thỏa quy tắc phiên bản.
- W3 nhận payment movement có idempotency; có trường hợp callback lặp và đến muộn.

Nếu workload thực tế gồm 70% truy vấn theo tenant nhưng bài test chỉ chạy query toàn hệ thống, kết luận sẽ không có giá trị.

## 3. Dữ liệu đại diện nghĩa là đại diện **phân phối**, không chỉ số hàng

Một tập 100.000 dòng được sinh bằng random đều có thể khác căn bản dữ liệu thật gồm khách rất lớn, dữ liệu tập trung vào một vài ngày và một số sản phẩm bán chạy.

Ví dụ giả định môi trường sản xuất sau hai năm:

| Thuộc tính | Mục tiêu dữ liệu thử nghiệm | Tại sao quan trọng? |
| --- | --- | --- |
| Tenant | 200 tenant, nhưng **2 tenant lớn** chứa 35% số đơn. | Kiểm tra hot tenant, skew khi index/shard. |
| Đơn hàng | 6 triệu `orders`. | Kiểm tra scale và thống kê planner. |
| Dòng hàng | 18 triệu `order_lines`; đa số 1–5 dòng, một số đơn hàng chục dòng. | JOIN cardinality, fan-out, cache. |
| Payment movements | 7,2 triệu; có đơn chưa capture, thu nhiều lần, hoàn một phần. | Đúng grain và index theo order. |
| Thời gian | 24 tháng; đỉnh ngày khuyến mại cao hơn ngày bình thường nhiều lần. | Partition pruning, hotspot thời gian. |
| Trạng thái | `PLACED`, `CANCELLED`, `FULFILLED` không đều. | Predicate selectivity và update pattern. |
| Currency | Nhiều mã, phân bố theo tenant/khu vực. | Kiểm tra GROUP BY, không cộng chéo tiền tệ. |
| Kích thước text | Tên/mã có phân phối độ dài và một số bản ghi rất dài. | Heap/TOAST, scan bytes, serialization. |
| Đọc nóng | Khoảng thời gian gần đây được đọc nhiều hơn lịch sử. | Page cache, index locality, warm/cold. |

Đây là **tình huống giả lập**, không phải số liệu của một hệ thống cụ thể. Giá trị thực cần được đo từ thống kê an toàn của nguồn nghiệp vụ và kế hoạch tăng trưởng.

### Phải giữ tương quan giữa các thuộc tính

Random độc lập có thể khiến “mỗi tenant có mọi loại tiền”, “mọi trạng thái phân bố đều trên mọi thời kỳ” hoặc “mỗi đơn có ba dòng đúng như nhau”, dẫn đến planner và I/O vận hành khác thực tế.

Một bộ dữ liệu đại diện nên giữ các **tương quan có ý nghĩa**:

- Tenant lớn có nhiều đơn, nhiều cập nhật đồng thời và nhiều payment callbacks.
- Ngày khuyến mại có nhiều order lines, trạng thái chờ và truy vấn báo cáo.
- Một số sản phẩm bán chạy xuất hiện lặp lại ở nhiều đơn.
- Đơn mới được đọc/sửa nhiều; đơn cũ chủ yếu dùng cho báo cáo/kiểm toán.
- Callback payment có thể đến muộn, trùng, hoặc nhiều movement trên một order.
- Mã vùng, tiền tệ và nguồn được phân bố theo hợp đồng thực.

Nếu thay đổi phân phối làm thay đổi selectivity của predicate, cùng một chỉ mục có thể từ rất tốt trở thành kém hiệu quả.

## 4. Lấy mẫu, tổng hợp thống kê hay sinh dữ liệu: phương án nào đáng tin?

Có ba cách phổ biến, có thể kết hợp:

| Cách tạo dataset | Lợi ích | Hạn chế |
| --- | --- | --- |
| **Bản sao dữ liệu thực được xử lý bảo mật hợp lệ** | Giữ skew, tương quan, độ dài và ngoại lệ thực. | Rủi ro riêng tư; cần quyền, masking và kiểm soát dữ liệu dẫn xuất. |
| **Sinh dữ liệu từ thống kê tổng hợp** | Có thể tạo quy mô lớn, tái lập và không lấy PII thực. | Dễ bỏ sót mối liên hệ và giá trị hiếm ảnh hưởng kế hoạch. |
| **Lấy mẫu phân tầng** theo tenant, thời gian, trạng thái, kích cỡ | Bảo toàn các nhóm quan trọng trong tập nhỏ hơn. | Mẫu nhỏ không tái hiện I/O, cache, số trang/index của quy mô lớn. |

**Không dùng một mẫu 1% rồi suy thời gian truy vấn tăng tuyến tính 100 lần.** Khi bảng vừa vượt RAM, số trang index tăng, cache miss thay đổi và planner chọn phương án JOIN khác. Với quyết định dung lượng và hiệu năng production, cần bài test **ở quy mô gần yêu cầu**, hoặc có mô hình dự báo được hiệu chỉnh bằng điểm đo ở nhiều quy mô.

### Ma trận trường hợp đại diện

Tạo tập kiểm thử gồm:

- Tenant lớn nhất, tenant vừa và tenant rất nhỏ.
- Khoảng thời gian mới 24 giờ, 30 ngày và toàn lịch sử.
- Order 1 dòng, 5 dòng, 100 dòng; order không có payment và order có nhiều refund.
- Thời điểm đỉnh tải và ngày bình thường.
- Khóa có selectivity rất cao và predicate phổ biến có selectivity thấp.
- Giá trị NULL, enum ít gặp, product mã dài, bản ghi đã xóa mềm nếu chính sách cho phép.
- Phép cập nhật cùng hot key và nhiều key không tranh chấp.

**Dữ liệu đại diện phải đúng bất biến.** Không tạo 18 triệu dòng hàng trỏ tới order không tồn tại rồi coi mọi JOIN chậm là do mô hình quan hệ. Nếu muốn test dữ liệu hỏng, tách thành bộ **negative tests** có mục đích riêng.

## 5. Định danh, grain và tính đúng là nền cho benchmark

Giả sử:

- `orders` có grain **một đơn theo (tenant_id, order_id)**.
- `order_lines` có grain **một dòng hàng theo (tenant_id, order_id, line_no)**.
- `payment_movements` có grain **một movement đã được provider xác nhận theo (tenant_id, movement_id)**.

Một Order có thể có 3 OrderLine và 2 PaymentMovement. JOIN hai bảng con trực tiếp qua Order sẽ tạo 6 hàng. Dù index rất tốt và query chỉ mất 20 ms, `SUM(line_net_minor)` hay `SUM(amount_minor)` sau JOIN như vậy vẫn **sai nghiệp vụ**.

**Điều kiện tiên quyết khi đo:** mọi phương án phải trả kết quả tương đương theo cùng hợp đồng, không “đạt latency” bằng cách bỏ dữ liệu, nới giới hạn tenant hoặc nhầm `RefundRequested` thành `RefundConfirmed`.

### Định nghĩa kết quả chuẩn (oracle)

Có thể giữ một tập **golden fixtures** với:

1. Một đơn không có payment confirmed.
2. Một đơn nhiều dòng, nhiều lần capture và refund một phần.
3. Một order bị hủy sau khi đặt, theo chính sách báo cáo.
4. Dữ liệu đến muộn được chốt đúng ngày sự kiện.
5. Tenant khác có cùng mã ngoài theo namespace được phép.
6. Một bản ghi payment callback lặp có cùng transaction ID.

Với mỗi case, xác định **đúng số hàng, số tiền, currency, thời gian và trạng thái**, trước khi so latency. Kết quả đúng là tiêu chí **gating**: phương án sai không được chọn dù nhanh hơn.

## 6. Lược đồ chuẩn hóa làm mốc đo PostgreSQL

Ví dụ sau giữ Order, Line và Movement thành ba bảng có grain riêng. Tên `bench` nhấn mạnh đây là **lược đồ thử nghiệm**, không phải khuyến nghị chạy migration trực tiếp trên production.

~~~sql
CREATE SCHEMA IF NOT EXISTS bench;

CREATE TABLE bench.orders (
    tenant_id           UUID NOT NULL,
    order_id            UUID NOT NULL,
    customer_id         UUID NOT NULL,
    placed_at           TIMESTAMPTZ NOT NULL,
    order_status        VARCHAR(24) NOT NULL
                        CHECK (order_status IN
                            ('PLACED', 'CANCELLED', 'FULFILLED')),
    booked_total_minor  BIGINT NOT NULL
                        CHECK (booked_total_minor >= 0),
    currency_code       CHAR(3) NOT NULL,
    row_version         BIGINT NOT NULL DEFAULT 1
                        CHECK (row_version > 0),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE bench.order_lines (
    tenant_id           UUID NOT NULL,
    order_id            UUID NOT NULL,
    line_no             INTEGER NOT NULL CHECK (line_no > 0),
    product_id          UUID NOT NULL,
    quantity            NUMERIC(18,3) NOT NULL CHECK (quantity > 0),
    line_net_minor      BIGINT NOT NULL CHECK (line_net_minor >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES bench.orders (tenant_id, order_id)
);

CREATE TABLE bench.payment_movements (
    tenant_id           UUID NOT NULL,
    movement_id         UUID NOT NULL,
    order_id            UUID NOT NULL,
    provider_name       VARCHAR(60) NOT NULL,
    provider_reference  VARCHAR(120) NOT NULL,
    movement_type       VARCHAR(12) NOT NULL
                        CHECK (movement_type IN ('CAPTURE', 'REFUND')),
    amount_minor        BIGINT NOT NULL CHECK (amount_minor > 0),
    currency_code       CHAR(3) NOT NULL,
    confirmed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, movement_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES bench.orders (tenant_id, order_id),
    UNIQUE (tenant_id, provider_name, provider_reference)
);
~~~

**Giới hạn của ví dụ:**

- `booked_total_minor` biểu diễn giá trị đã chốt khi đặt theo chính sách thử nghiệm; nó **khác net cash**. Nếu có phí vận chuyển/thuế/discount ngoài dòng hàng, không tự coi tổng dòng hàng bằng tổng order.
- Payment movement chỉ được ghi khi đã có xác nhận từ nguồn có thẩm quyền. Nếu provider reference không duy nhất ở phạm vi `tenant + provider` thì UNIQUE phải thêm merchant/account namespace.
- `row_version` hỗ trợ optimistic concurrency ở Order, nhưng không bảo vệ toàn bộ state machine nếu ứng dụng không kiểm tra chuyển tiếp.
- FK tổ hợp bảo vệ tenant scope trong cùng DB; `customer_id`, `product_id` có thể là external references của những service khác.
- Đây là schema cơ sở để so phương án index, denormalization và partition, không mô hình hóa mọi nghĩa vụ kế toán/retention.

### Sau khi nạp dữ liệu thử

Thống kê planner cần phản ánh dataset:

~~~sql
-- Chạy trong môi trường thử nghiệm sau bulk load.
ANALYZE bench.orders;
ANALYZE bench.order_lines;
ANALYZE bench.payment_movements;
~~~

Thống kê cũ có thể khiến `EXPLAIN` cho kế hoạch sai; điều này là lỗi **môi trường đo**, không nhất thiết là lỗi của phương án mô hình. Phải ghi nhận phiên bản PostgreSQL, kiểu storage, thống kê và cấu hình trước khi đối chiếu các kết quả.

## 7. Xây danh mục truy vấn đọc: không benchmark một SELECT duy nhất

Một workload đọc nên liệt kê các query shape, tần suất, kích thước kết quả, điều kiện và kỳ vọng độ mới.

| ID | Truy vấn | Input quan trọng | Vấn đề có thể gặp |
| --- | --- | --- | --- |
| **Q1** | Đọc một Order và các Line theo PK. | Tenant, Order ID, số dòng. | N+1 queries, network round trips, hàng lớn. |
| **Q2** | 50 đơn gần nhất theo tenant. | Tenant nóng/lạnh, khoảng ngày, cursor. | Sort nhiều dòng, thiếu index, OFFSET lớn. |
| **Q3** | Doanh số đã đặt theo ngày và currency. | 1 ngày/30 ngày/2 năm. | Scan lớn, JOIN/aggregate, spill, cache. |
| **Q4** | Tổng thu/hoàn đã xác nhận của một Order. | Movement count, provider, currency. | Nối sai grain, thiếu index theo order. |
| **Q5** | Top sản phẩm bán chạy trong kỳ. | Filter date, nhóm sản phẩm, nhiều tenant. | High-cardinality GROUP BY, hot keys, shuffle. |
| **Q6** | Tra đơn gần nhất của khách. | Tenant, customer_id, thời gian. | Secondary index theo customer, skew. |

Cần đo cả **trường hợp phổ biến và trường hợp đuôi**: tenant lớn, đơn hàng trăm dòng, mốc thời gian không có dữ liệu, callback nhiều movement. Đừng gộp Q1 và Q3 thành một “latency trung bình của database”; mục tiêu của chúng khác nhau.

### Q1 — Chi tiết một đơn

~~~sql
SELECT tenant_id, order_id, customer_id,
       placed_at, order_status, booked_total_minor, currency_code
FROM bench.orders
WHERE tenant_id = :tenant_id AND order_id = :order_id;

SELECT line_no, product_id, quantity, line_net_minor
FROM bench.order_lines
WHERE tenant_id = :tenant_id AND order_id = :order_id
ORDER BY line_no;
~~~

Đây là **hai query** trong một request. End-to-end latency phải gồm cả hai và serialization/connection. Nếu cần ảnh chụp nhất quán giữa header và lines khi đang có ghi, phải chọn isolation/session policy thích hợp; hai SELECT ở READ COMMITTED có thể quan sát hai snapshot khác nhau.

### Q2 — Trang danh sách đơn gần nhất

~~~sql
SELECT order_id, placed_at, order_status,
       booked_total_minor, currency_code
FROM bench.orders
WHERE tenant_id = :tenant_id
  AND placed_at >= :from_at
ORDER BY placed_at DESC, order_id DESC
LIMIT 50;
~~~

Khóa sắp xếp có `order_id` làm tie-breaker khi nhiều đơn có cùng thời điểm. Nếu phân trang sâu, thử **keyset pagination** bằng cả `placed_at` và `order_id` thay cho OFFSET lớn.

### Q3 — Tổng giá trị dòng hàng đã đặt theo ngày

~~~sql
SELECT (o.placed_at AT TIME ZONE 'UTC')::date AS day_utc,
       o.currency_code,
       SUM(l.line_net_minor) AS booked_line_minor
FROM bench.orders o
JOIN bench.order_lines l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
WHERE o.tenant_id = :tenant_id
  AND o.placed_at >= :from_at
  AND o.placed_at <  :to_at
GROUP BY (o.placed_at AT TIME ZONE 'UTC')::date, o.currency_code
ORDER BY day_utc, o.currency_code;
~~~

Ví dụ cố ý nhóm theo **ngày UTC** bằng `AT TIME ZONE 'UTC'`; nếu báo cáo theo **ngày kinh doanh địa phương**, phải thay bằng timezone/cutoff đã được duyệt và giữ cùng quy tắc giữa các phương án. Đây là **tổng giá trị dòng hàng**; không tự đồng nghĩa `booked_total_minor` của Order nếu Order có phí/thuế ngoài line. Cũng **không** phải net cash. Để thử Q3 công bằng, các phương án phải giữ đúng cùng định nghĩa này, cùng phạm vi tenant, calendar và currency.

Các dấu `:tenant_id`, `:from_at`… là **tham số minh họa** cho ứng dụng/benchmark driver; chúng không phải biến SQL có thể chạy nguyên văn trong mọi giao diện PostgreSQL.

## 8. Phân tích kế hoạch: đọc EXPLAIN (ANALYZE, BUFFERS) thế nào?

Ví dụ kế hoạch kiểm tra Q2:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT order_id, placed_at, order_status,
       booked_total_minor, currency_code
FROM bench.orders
WHERE tenant_id = :tenant_id
  AND placed_at >= :from_at
ORDER BY placed_at DESC, order_id DESC
LIMIT 50;
~~~

**Khi đọc kết quả, không chỉ nhìn “Execution Time”.** Ghi lại:

| Quan sát | Câu hỏi cần trả lời |
| --- | --- |
| `Seq Scan` / `Index Scan` / `Bitmap Scan` | Plan truy cập bao nhiêu dữ liệu, vì sao chọn đường đó? |
| `actual rows` và `loops` | Có đọc nhân nhiều lần, bị N+1 hoặc JOIN fan-out không? |
| `estimated rows` so với `actual rows` | Statistics có sai selectivity/skew không? |
| `Rows Removed by Filter` | Bao nhiêu hàng đọc nhưng bị loại? |
| `Sort Method`, `Memory`, `Disk` | ORDER BY/GROUP BY có spill xuống disk không? |
| `shared hit/read` | Trang từ cache PostgreSQL hay cần đọc qua storage? |
| `temp read/written` | Hash join, sort hay aggregate có dùng tệp tạm không? |
| `Planning Time`, `Execution Time` | Optimizer và executor tốn bao nhiêu thời gian? |
| `Settings` | Có setting khác nhau giữa hai lần đo không? |

Trong PostgreSQL, `BUFFERS shared hit` nói về **shared buffer cache của database**, còn `shared read` có thể được đáp ứng từ OS page cache, không phải lúc nào cũng là I/O vật lý từ thiết bị. Muốn kết luận về disk cần thêm số liệu hệ điều hành/storage và điều kiện cache rõ ràng.

**EXPLAIN ANALYZE thực sự chạy câu SQL.** Với INSERT/UPDATE/DELETE hoặc function có side effect, chỉ dùng trên môi trường thử nghiệm, có kiểm soát transaction và các tác động ngoài DB. Kể cả rollback SQL, sequence, trigger side effect ngoài DB hoặc log bên ngoài có thể không quay lại như tưởng. Đừng dùng trên production chỉ để “xem kế hoạch”.

### Thời gian server khác thời gian người dùng

Thời gian ghi trong `EXPLAIN ANALYZE` chủ yếu phản ánh thực thi trong engine và có overhead của việc đo. Nó không tự bao gồm đầy đủ: network round trip, queue ở connection pool, decode/serialize JSON, ứng dụng xử lý kết quả hoặc thời gian chờ dịch vụ khác.

Cần hai lớp đo:

- **Query plan instrumentation:** hiểu *vì sao* một SQL chậm.
- **Workload driver/client tracing:** biết *người dùng có đạt SLO hay không* khi nhiều yêu cầu đồng thời.

Không thay thế lớp thứ hai bằng ảnh chụp một `EXPLAIN` chạy lúc hệ thống nhàn rỗi.

## 9. So sánh chỉ mục: lợi ích đọc phải trả bằng ghi và dung lượng

Với Q2, phương án B có thể thêm:

~~~sql
CREATE INDEX ix_orders_tenant_recent
ON bench.orders (tenant_id, placed_at DESC, order_id DESC)
INCLUDE (order_status, booked_total_minor, currency_code);
~~~

Chỉ mục này có thể hỗ trợ tenant filter + thứ tự gần nhất và giảm việc truy cập heap ở một số workload. Nhưng hiệu quả **index-only scan** phụ thuộc cả **visibility map** và việc PostgreSQL có thể xác nhận row visibility; bảng bị cập nhật liên tục có thể vẫn cần heap fetches.

### Cần đo gì trước và sau khi thêm index?

| Lợi ích mong đợi | Chi phí phải đo |
| --- | --- |
| Q2 ít sort/scan hơn. | Index bytes, WAL và CPU khi INSERT. |
| Truy vấn lấy 50 đơn nhanh hơn. | Cập nhật `order_status` có thể phải duy trì INCLUDE index. |
| Truy vấn đuôi tốt hơn. | Cache pressure: nhiều index hơn làm giảm chỗ cho dữ liệu nóng. |
| Ít heap fetches ở điều kiện phù hợp. | Vacuum/visibility map và ảnh hưởng tới index-only scan. |

**Một index không miễn phí**. Nếu `order_status` được cập nhật nhiều và nằm trong phần INCLUDE, bản cập nhật có thể mất khả năng HOT update tùy điều kiện PostgreSQL, làm phát sinh ghi index/heap và WAL nhiều hơn. Một phương án không INCLUDE trạng thái có thể đọc nhiều heap hơn nhưng ghi nhẹ hơn.

Đừng đo chỉ Q2 rồi tuyên bố B tốt hơn A. Phải chạy **cùng hỗn hợp đọc/ghi**, đặc biệt các cập nhật cột được index, và đo thêm dung lượng.

### BRIN, B-tree và lựa chọn khác

- **B-tree** thường hợp với tra cứu chọn lọc, thứ tự và phạm vi theo khóa phù hợp.
- **BRIN** có thể rất gọn với dữ liệu append theo thời gian tương quan vật lý; nó thường là chỉ mục mất mát, cần lọc lại hàng và có thể không tốt cho tenant nhỏ rải đều.
- **Partition pruning** có thể giảm số bảng con cần quét, nhưng không thay thế thiết kế index trong mỗi partition.
- **Materialized summary** giảm đọc lớn ở Q3 nhưng có thêm pipeline, lag, correction và chi phí lưu.

Chỉ chọn qua **workload thật**, không qua danh sách quy tắc “bảng lớn phải có BRIN” hoặc “mọi FK đều cần index”.

## 10. Đo độ trễ bằng phân phối, không dùng mỗi giá trị trung bình

Một kết quả như “latency trung bình 40 ms” có thể che 5% request kéo dài vài giây. Cần ít nhất:

- `P50`: request ở giữa phân phối.
- `P95` và `P99`: phần đuôi ảnh hưởng trải nghiệm, timeout và tải cao.
- **Tỷ lệ vượt SLO** theo từng query shape và từng nhóm tenant.
- **Throughput**: request/giây và transaction/giây đạt khi vẫn giữ latency được chấp nhận.
- **Lỗi, timeout, retry**: không được bỏ request lỗi khỏi mẫu để latency trông đẹp.
- **Kích thước kết quả** và số hàng scan: phân biệt query nhanh vì trả ít hơn.

### Thiết kế tải đồng thời

| Mô hình driver | Thích hợp cho | Rủi ro |
| --- | --- | --- |
| **Closed-loop:** N client gửi request mới sau khi request trước kết thúc. | Đo tải ứng dụng với số client cố định. | Khi hệ chậm, tốc độ gửi giảm; có thể che mức tải người dùng yêu cầu. |
| **Open-loop / arrival-rate:** gửi theo lịch lưu lượng mục tiêu. | Kiểm tra SLA dưới tốc độ đến độc lập với độ trễ. | Nếu vượt năng lực, queue tăng; cần giới hạn an toàn và ghi đủ lỗi. |
| **Burst / peak:** dồn lưu lượng vào một khoảng. | Kiểm tra ngày khuyến mại, thundering herd, connection limit. | Không thay thế kết quả steady-state; phải báo tải đỉnh cụ thể. |

Cần tránh **coordinated omission**: nếu driver chờ hệ trả chậm rồi mới phát yêu cầu tiếp theo và chỉ ghi những yêu cầu đã hoàn tất, các khoảng chờ không được phản ánh trung thực. Ghi thời điểm yêu cầu *đáng lẽ phải bắt đầu* khi dùng mô hình arrival rate, theo dõi queue, timeout và requests chưa hoàn tất.

### Không lấy percentile bằng trung bình các percentile

P95 của từng phút rồi lấy AVG không phải P95 của toàn bộ request. Nên lưu **histogram hoặc raw samples đủ độ phân giải** theo query shape/concurrency để tính percentile trên tất cả mẫu phù hợp. Báo cáo số lượng request, thời gian đo, lỗi và cách lấy percentile.

## 11. Cache nóng/lạnh và planner statistics có thể đảo kết luận

Hai lần benchmark giống hệt SQL vẫn có thể ra số khác nhau vì:

- Phần lớn trang nằm trong PostgreSQL shared buffers hoặc OS page cache.
- Index vừa được tạo, `ANALYZE` mới chạy hoặc vacuum vừa dọn dữ liệu.
- Một lần query khởi động JIT/cached plan; lần sau đã warm.
- Một lần test có autovacuum/checkpoint chạy; lần còn lại không.
- Hot tenants được gọi liên tục ở lần đo thứ hai.
- Connection pool, prepared statements và parallel query settings khác nhau.

Nên công bố rõ hai chế độ:

1. **Warm-cache/steady-state:** nạp workload đủ thời gian warmup rồi đo trong khoảng ổn định; phù hợp tải thường xuyên.
2. **Cold-ish hoặc cache pressure:** tạo áp lực dữ liệu lớn hơn bộ nhớ, mô phỏng restart hoặc quét lịch sử; cần thực hiện an toàn trong môi trường kiểm thử, không tùy tiện xóa cache hệ điều hành trên máy dùng chung.

Không tuyên bố “cold cache” tuyệt đối nếu chưa chứng minh trạng thái cache, storage và máy host. Mục tiêu là **điều kiện tái lập**, không phải một thuật ngữ nghe nghiêm ngặt.

### Chuẩn hóa môi trường so sánh

Giữ nhất quán: phiên bản DB, tài nguyên CPU/RAM/storage, cấu hình pool, autovacuum, WAL durability, planner settings, dữ liệu/seed, query parameters và tỷ lệ đọc/ghi. Nếu một phương án bật async commit còn phương án kia đợi durable commit, đó là **khác mức bảo đảm**, không thể dùng để kết luận cấu trúc dữ liệu nhanh hơn.

## 12. Benchmark ghi: đơn hàng và các dòng phải commit atomically

Một transaction tạo đơn trong cùng PostgreSQL:

~~~sql
BEGIN;

INSERT INTO bench.orders (
    tenant_id, order_id, customer_id,
    placed_at, order_status, booked_total_minor,
    currency_code
) VALUES (
    :tenant_id, :order_id, :customer_id,
    :placed_at, 'PLACED', :booked_total_minor,
    :currency_code
);

INSERT INTO bench.order_lines (
    tenant_id, order_id, line_no,
    product_id, quantity, line_net_minor
)
VALUES
    (:tenant_id, :order_id, 1,
     :product_1, :quantity_1, :line_amount_1),
    (:tenant_id, :order_id, 2,
     :product_2, :quantity_2, :line_amount_2);

COMMIT;
~~~

Đây là ví dụ hai dòng, workload W1 có thể thay đổi từ 1 đến hàng trăm dòng để phản ánh phân phối thực. Test phải xác nhận tổng đơn, currency, FK và các invariant trước khi tính throughput. Nếu một transaction thất bại vì UNIQUE/FK thì không được đếm như một đơn thành công.

### Ghi không chỉ là INSERT

| Kiểu ghi | Tải cần mô phỏng | Tác động vật lý |
| --- | --- | --- |
| **INSERT order + lines** | Nhiều PK/FK, nhiều dòng, một commit. | Heap pages, PK/secondary indexes, WAL, commit. |
| **UPDATE status** | Đơn đang xử lý, có optimistic lock. | MVCC tuple mới, index maintenance, dead tuples. |
| **INSERT payment movement** | Idempotency, unique provider ref, callback lặp. | Uniqueness checks, lock/chờ khi cùng khóa. |
| **DELETE/soft delete** | Retention hoặc vòng đời theo policy. | Bloat, index dead entries, vacuum, ảnh hưởng query filter. |
| **Bulk load/backfill** | Dữ liệu lịch sử theo batch. | WAL, checkpoint, replica lag, stats và index maintenance. |
| **Concurrent hot-key update** | Nhiều request trên một stock/counter/key. | Lock wait, serialization/retry, contention. |

Khi so schema, **giữ cùng quy tắc commit và cùng ràng buộc nghiệp vụ**. Bỏ FK và unique để chạy write benchmark nhanh hơn không phải lựa chọn tương đương nếu production cần chúng.

## 13. Mô hình UPDATE, MVCC, HOT và bloat trong PostgreSQL

PostgreSQL dùng MVCC: một `UPDATE` thường tạo phiên bản tuple mới, phiên bản cũ chờ được dọn theo quy tắc visibility/vacuum. Vì vậy chi phí cập nhật không chỉ là “ghi lại 10 byte trạng thái”.

Ví dụ bảo vệ lost update bằng `row_version`:

~~~sql
UPDATE bench.orders
SET order_status = :new_status,
    row_version = row_version + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND row_version = :expected_version
  AND order_status = :expected_status
RETURNING row_version;
~~~

Nếu trả **0 hàng**, đó có thể là version conflict, sai trạng thái hoặc không tìm thấy đơn; ứng dụng phải phân loại và quyết định retry/điều tra. Câu lệnh này chỉ bảo vệ cập nhật có điều kiện, **không tự định nghĩa toàn bộ state machine**.

### HOT update và index

HOT (Heap-Only Tuple) update có thể giảm chi phí index maintenance khi các điều kiện của PostgreSQL thỏa, trong đó thông thường không thay đổi các cột được index và có đủ chỗ trên heap page. Nếu thêm `order_status` vào một index INCLUDE, các cập nhật status có thể mất lợi ích HOT.

Khi so phương án A và B:

- Đo tỷ lệ HOT updates khi cùng workload W2.
- Đo WAL bytes và tốc độ tăng dead tuples.
- Đo lock wait/transaction time và autovacuum impact.
- Đo dung lượng sau một chu kỳ ghi **dài đủ** để thấy bloat, không chỉ ngay sau bulk load.

**Không tắt autovacuum để “ổn định” benchmark rồi áp kết luận vào production.** Nếu cố định cấu hình cho một thí nghiệm đặc biệt, hãy báo rõ thay đổi đó làm giảm tính đại diện của môi trường.

## 14. Đo chi phí ghi bằng WAL, thống kê và độ trễ end-to-end

PostgreSQL cung cấp thống kê để quan sát, nhưng nhiều bộ đếm là **tích lũy**, không phải số cho riêng một truy vấn. Đo bằng snapshot trước/sau cùng khoảng test và tách hoạt động khác trong môi trường thử.

~~~sql
-- Các cột ví dụ từ pg_stat_user_tables.
SELECT relname,
       n_tup_ins, n_tup_upd, n_tup_del,
       n_tup_hot_upd, n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'bench'
ORDER BY relname;
~~~

`n_dead_tup` là **ước lượng** tại thời điểm thống kê, không phải bộ đếm chính xác mọi dead tuple; `n_tup_ins/upd/del` phản ánh hoạt động đã quan sát, có thể chịu trễ cập nhật thống kê. Không so các giá trị tích lũy từ hai run nếu không lấy delta hoặc dùng test environment tái lập.

~~~sql
-- Có trên các phiên bản PostgreSQL hỗ trợ pg_stat_wal.
SELECT wal_records, wal_fpi, wal_bytes
FROM pg_stat_wal;
~~~

`wal_bytes` là **WAL sinh bởi instance trong khoảng đo**, không phải trực tiếp số byte disk cuối cùng sau nén/retention và không tự chỉ thuộc `bench.orders` nếu có transaction khác. Ghi start/end, chênh lệch và các tác vụ nền có thể ảnh hưởng. Đối với replication, đo thêm replica lag và khả năng bắt kịp nếu ứng dụng cần read replica.

### Một bảng đo ghi đầy đủ

| Metric | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| Successful transactions | Tx/s | Thông lượng thao tác **commit thành công**. |
| Commit P50/P95/P99 | ms | Độ trễ hoàn tất giao dịch từ client. |
| Abort/conflict/retry rate | %/số lượng | Giá trả cho cạnh tranh và idempotency. |
| WAL bytes per committed order | Byte/đơn | Chi phí log của workload; đo bằng delta sau khi cô lập. |
| CPU và disk write bandwidth | CPU%, MiB/s | Nút thắt tài nguyên. |
| Lock wait | ms, số lần | Thao tác tranh cùng hàng/khóa. |
| Dead tuples / vacuum work | Ước lượng, thời gian | Chi phí dài hạn của UPDATE/DELETE. |
| Index bytes growth | MiB/GiB | Write amplification do chỉ mục bổ sung. |
| Replica freshness | ms/s | Bản sao đọc chậm đến đâu sau tải ghi. |

Không lấy `INSERT ... RETURNING` thành công thay cho **durable commit** trong benchmark W1 nếu hệ sử dụng transaction. Kết quả trả trước commit có thể không đại diện cho thời gian người dùng phải chờ để xác nhận.

## 15. Dung lượng thực: heap, index, TOAST và tổng dung lượng

Đo số hàng hoặc dung lượng CSV không đủ dự báo storage database. Ngoài payload, PostgreSQL còn có tuple/header, page layout, visibility metadata, index, TOAST cho giá trị lớn, free space và các biến động do update/vacuum.

~~~sql
SELECT
    'bench.orders' AS relation_name,
    pg_size_pretty(
        pg_relation_size('bench.orders'::regclass)
    ) AS main_fork,
    pg_size_pretty(
        pg_table_size('bench.orders'::regclass)
    ) AS table_including_toast,
    pg_size_pretty(
        pg_indexes_size('bench.orders'::regclass)
    ) AS indexes,
    pg_size_pretty(
        pg_total_relation_size('bench.orders'::regclass)
    ) AS total_relation;
~~~

Các hàm không có cùng phạm vi:

- `pg_relation_size` (mặc định main fork): dung lượng phần quan hệ chính, không phải toàn bộ chi phí bảng.
- `pg_table_size`: dung lượng bảng gồm các phần liên quan như TOAST và metadata storage theo định nghĩa hàm, chưa tính các index riêng của bảng.
- `pg_indexes_size`: dung lượng chỉ mục liên quan.
- `pg_total_relation_size`: tổng bảng + index theo phạm vi quan hệ được hỏi.

Khi so A/B/C, tính **tổng các bảng liên quan**: orders, lines, movements, secondary indexes, rollup tables, materialized views và những bản sao đọc thuộc thiết kế.

### Theo dõi tỷ trọng index

~~~sql
SELECT c.relname,
       pg_size_pretty(pg_table_size(c.oid)) AS table_bytes,
       pg_size_pretty(pg_indexes_size(c.oid)) AS index_bytes,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_bytes
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'bench'
  AND c.relkind IN ('r', 'm')
ORDER BY pg_total_relation_size(c.oid) DESC;
~~~

Kết quả cho phép nhận diện index nào khiến storage tăng mạnh, nhưng chưa cho biết index có đáng giữ hay không; phải nối với **query frequency, latency và chi phí ghi**.

### Dung lượng theo thời gian

Đo ít nhất tại ba mốc:

1. **Sau bulk load** và ANALYZE.
2. **Sau steady-state write/update/delete** với số transaction đại diện, đã chạy maintenance bình thường.
3. **Sau retention/archive/rebuild hoặc vacuum** theo quy trình thực.

Đối với partitioned table, `pg_total_relation_size` gọi trên **bảng cha phân vùng** có thể không bao gồm tổng các partition con. Phải cộng leaf partitions và các index/rollup liên quan; không công bố bảng partition cha “chỉ vài KB” là dung lượng toàn dữ liệu.

## 16. Dự báo dung lượng: data, index, WAL, replica và backup là các ngân sách khác nhau

Một bài kiểm chứng dung lượng nên có công thức rõ, ví dụ:

~~~text
Data + Index sau 24 tháng
    ≈ current_physical_bytes
      + measured_monthly_growth_bytes × 24
      + safety_margin_for_skew_and_bloat

Operational capacity
    = primary_data_and_indexes
      + headroom_for_maintenance_and_migration
      + retained_WAL_and_temp_working_space
      + separately_budgeted_replica_and_backup_storage
~~~

Không áp một tỷ lệ “index luôn bằng 20% bảng” cho mọi mô hình. Hãy đo **byte/row theo từng loại entity và từng index** ở quy mô đại diện, cộng chi phí từ số bản ghi, độ dài text, update pattern, retention và compression.

Các khoản cần xét riêng:

| Khoản | Cách ước tính | Không được quên |
| --- | --- | --- |
| **Primary heap/index** | Dung lượng thật sau tải đủ lớn. | Bloat, TOAST, FSM/VM, index tùy query. |
| **WAL** | WAL bytes/transaction và policy lưu. | Peak traffic, replication/archive backlog. |
| **Replica** | Số replica × cấu trúc dữ liệu tương ứng. | Không chỉ là chi phí CPU; storage và network. |
| **Backup/snapshot** | Full/incremental theo policy và biến động. | Giữ nhiều phiên bản, khả năng restore. |
| **Temp files** | Sort/hash/spill của query lớn. | Peak Q3, concurrent reports. |
| **Materialized aggregate** | Kích thước mart + index + refresh staging. | Thời gian/cost rebuild. |
| **Migration headroom** | Kho dự phòng copy/index online. | Expand–contract có thể giữ hai cấu trúc đồng thời. |
| **Retention/erasure** | Lịch lưu, purge/archive và legal hold. | Xóa nguồn không tự xóa bản sao/downstream. |

**Phân biệt storage capacity và throughput của storage.** Hai cấu trúc có thể chiếm cùng 1 TiB nhưng một cấu trúc ghi WAL/index nhiều gấp đôi khiến IOPS và latency không đạt SLO.

## 17. Thử phân vùng và phân tán mà không làm sai ràng buộc

Partitioning theo tháng có thể giảm phạm vi quét cho Q3 hoặc giúp retention theo kỳ. Nhưng mỗi chiến lược có đánh đổi:

- **Range theo `placed_at`:** truy vấn ngày/tháng có thể pruning tốt; tìm theo `order_id` mà không biết ngày có thể phải tìm nhiều partition.
- **Hash theo `tenant_id`:** giảm phạm vi dữ liệu tenant nếu engine/router hỗ trợ; tenant lớn vẫn có thể là hotspot.
- **Sharding nhiều DB:** tăng chi phí routing, JOIN xuyên shard, transaction/ràng buộc toàn cục, coordination và failover.
- **Cùng PostgreSQL DB với nhiều partition:** transaction giữa partition vẫn nằm trong **một database**, không mặc định là 2PC xuyên cluster.

### Bẫy PK/UNIQUE của PostgreSQL partitioned table

Với declarative partitioning, PK/UNIQUE trên bảng cha phải chứa cột partition key theo quy tắc PostgreSQL. Ví dụ một bảng chia theo `placed_at`:

~~~sql
CREATE TABLE bench.orders_by_month (
    tenant_id    UUID NOT NULL,
    order_id     UUID NOT NULL,
    placed_at    TIMESTAMPTZ NOT NULL,
    status       VARCHAR(24) NOT NULL,
    PRIMARY KEY (tenant_id, placed_at, order_id)
) PARTITION BY RANGE (placed_at);
~~~

PK này **không tự bảo đảm** `(tenant_id, order_id)` duy nhất trên tất cả các tháng. Nếu Order ID là business key bất biến theo tenant, cần thiết kế ID registry/định tuyến/unique ownership khác hoặc chọn partition key phù hợp hơn. **Không được đổi tính duy nhất của nghiệp vụ chỉ để benchmark partition thành công.**

### Cần đo gì khi thử partition?

| Truy vấn/thao tác | Chỉ số |
| --- | --- |
| Q2 một tenant, 30 ngày | Số partition được chạm, startup/plan time, P95. |
| Q3 1 tháng và 24 tháng | Pruning, rows/bytes scanned, temp spill. |
| Q1 tra theo Order ID | Fan-out qua partitions hay directory lookup. |
| W1 đơn mới | Hot partition, lock/index write, WAL. |
| Backfill dữ liệu cũ | Partition cũ bị cập nhật, maintenance và replica lag. |
| Retention | Thời gian archive/drop partition và nghĩa vụ dữ liệu khác. |

Nếu là distributed SQL/MPP, đo thêm **network bytes shuffled, coordinator wait và tail latency**. Query toàn hệ thống có thể bị shard chậm nhất chi phối; kết luận từ một single-node PostgreSQL partition experiment **không tự suy** sang sharding nhiều node.

## 18. Ghi lại điều kiện benchmark để có thể tái tạo

Một báo cáo đo tối thiểu cần **hợp đồng thử nghiệm**, không chỉ bảng thời gian.

~~~yaml
benchmark_id: order-model-2026-11
purpose: compare-index-and-summary
environment:
  database_engine: PostgreSQL
  version: "ghi phiên bản thực đang dùng"
  cpu_ram_storage: "ghi cấu hình thực"
  config_hash: "hash cấu hình đã được lưu có kiểm soát"
dataset:
  generation_version: v3
  seed: "cố định trong test generator"
  orders: 6000000
  order_lines: 18000000
  payment_movements: 7200000
  skew_profile: "2 tenant lớn chiếm 35% orders"
workload:
  read_write_mix: "theo phân phối request đã đo"
  warmup: "ghi khoảng warmup"
  measurement_window: "ghi khoảng đo"
  arrival_rate_and_concurrency: "ghi mức tải thực"
  consistency: "same guarantees across alternatives"
acceptance:
  read_p95_ms: "theo từng query ID"
  write_commit_p95_ms: "theo từng transaction ID"
  correctness: "golden fixtures + reconciliation"
  storage_budget: "primary/index/WAL/backup tách riêng"
~~~

Đây là **mẫu metadata**, không phải file cấu hình của một bộ benchmark cụ thể. Khi chạy thật phải điền giá trị đo hoặc mục tiêu đã phê duyệt, không để placeholder rồi công bố như kết quả thực.

### Luồng kiểm chứng có thể lặp lại

~~~mermaid
flowchart LR
    SRC["Thống kê nguồn + yêu cầu nghiệp vụ"] --> DATA["Dataset đại diện, seed và skew"]
    SRC --> WORK["Workload + SLO + correctness oracle"]
    DATA --> A["Phương án A / B / C cùng môi trường"]
    WORK --> A
    A --> MEASURE["Đọc, ghi, dung lượng, độ trễ, lỗi"]
    MEASURE --> VERIFY{"Kết quả nghiệp vụ và SLO đạt?"}
    VERIFY -->|Không| REVISE["Điều chỉnh mô hình hoặc workload"]
    REVISE --> A
    VERIFY -->|Có| ADR["ADR: lựa chọn, đánh đổi, điều kiện đánh giá lại"]
~~~

Sơ đồ nhấn mạnh **tính đúng là cửa kiểm tra bắt buộc**. Kết quả đo không hợp lệ nếu phương án trả sai số tiền hoặc bỏ hàng dù latency thấp.

### Quy tắc đối chiếu A/B/C

1. Cùng dataset snapshot/seed, cùng tenant skew và distribution.
2. Cùng loại request, parameter mix, payload và số dòng kết quả.
3. Cùng CPU/RAM/disk, version DB, WAL durability, pool, connection count.
4. Cùng warmup, thời gian đo, steady-state và chính sách maintenance.
5. Thứ tự thử **luân phiên** hoặc lặp nhiều lần để giảm ảnh hưởng thời gian/caching.
6. Đo cả đọc **trong lúc ghi**; không chỉ thử đọc riêng rồi ghi riêng nếu production mixed.
7. Kiểm tra kết quả đúng **trước và sau mỗi run**; nếu sai không đưa latency vào bảng xếp hạng hợp lệ.
8. Ghi confidence/độ biến thiên khi có nhiều run; không chọn vì một lần nhanh hơn vài mili giây do nhiễu.

## 19. Dụng cụ đo PostgreSQL: một số số liệu hỗ trợ điều tra

Ngoài `EXPLAIN`, một số công cụ thống kê có ích:

### pg_stat_statements (nếu đã bật)

~~~sql
-- Cần extension và cấu hình phù hợp; không mặc định luôn có sẵn.
SELECT queryid, calls, rows,
       mean_exec_time, total_exec_time,
       shared_blks_hit, shared_blks_read,
       temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Giá trị này giúp xác định query shape tốn tổng thời gian, nhưng `mean_exec_time` không phải P95 của client, `calls` có thể tích lũy từ trước và query được normalize/gộp theo công cụ. Nên ghi snapshot counters theo khoảng đo và lọc đúng query family. Không reset thống kê production chỉ để bài test.

### Theo dõi wait state hiện tại

~~~sql
SELECT wait_event_type, wait_event, COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Đây là **ảnh chụp trạng thái tại một thời điểm**, không phải tổng thời lượng lock wait. Để phân tích quá trình test, cần lấy mẫu theo thời gian, tracing hoặc metrics giám sát phù hợp.

### EXPLAIN WAL ở bản PostgreSQL hỗ trợ

~~~sql
-- Chạy trong môi trường thử nghiệm trên DML đã kiểm soát!
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE bench.orders
SET order_status = 'FULFILLED',
    row_version = row_version + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND order_status = 'PLACED';
~~~

Ví dụ này dùng để quan sát **một lần cập nhật thử nghiệm**; nó sẽ **thực thi UPDATE**. Không áp trực tiếp lên dữ liệu thật. Nếu chỉ muốn đọc plan mà không ghi, dùng `EXPLAIN` không có `ANALYZE`, nhưng khi đó không có các số runtime thật.

**Nguyên tắc chung:** hệ quản trị cung cấp số liệu thực thi, tài nguyên và statistics; công cụ tải cung cấp latency/throughput; đối soát nghiệp vụ cung cấp tính đúng. Cả ba cần xuất hiện trong báo cáo quyết định.

## 20. Minh họa so sánh ba phương án (số liệu giả định)

Bảng sau là **số liệu minh họa được đặt ra để hướng dẫn cách diễn giải**, không phải kết quả benchmark đã chạy và không khẳng định hiệu năng thực của PostgreSQL.

| Metric (điều kiện tải như nhau) | A: PK cơ bản | B: thêm index Q2 | C: B + daily summary |
| --- | ---: | ---: | ---: |
| Q1 đọc chi tiết P95 | 35 ms | 37 ms | 38 ms |
| Q2 danh sách gần nhất P95 | 620 ms | 90 ms | 92 ms |
| Q3 báo cáo 30 ngày P95 | 2.400 ms | 2.200 ms | 180 ms |
| W1 tạo đơn commit P95 | 45 ms | 61 ms | 74 ms |
| W2 đổi trạng thái P95 | 28 ms | 46 ms | 49 ms |
| Write throughput đạt trước khi vượt SLO | 3.200 tx/s | 2.800 tx/s | 2.500 tx/s |
| Primary data + indexes + summary | 820 GiB | 1.050 GiB | 1.140 GiB |
| Độ mới Q3 | Query trực tiếp | Query trực tiếp | Tối đa 3 phút theo giả định |

Có thể diễn giải như sau:

- **A** ghi nhẹ và chiếm ít chỗ hơn nhưng Q2 vượt mục tiêu P95 150 ms.
- **B** cải thiện rõ Q2, nhưng phải trả phí index/WAL/update và dung lượng. Q3 vẫn cần tối ưu.
- **C** có thể đáp ứng Q3 P95 2.000 ms với điều kiện **chấp nhận độ trễ 3 phút và cơ chế correction/rebuild**. Không được so C như thể dữ liệu hoàn toàn realtime nếu nghiệp vụ đòi dữ liệu tức thời.
- Nếu write throughput yêu cầu trên 2.500 tx/s, C trong bảng minh họa có thể không đạt dù đọc nhanh.
- Nếu ngân sách storage là 1.000 GiB cho chính dataset này, B/C cần thêm phương án tối ưu hoặc điều chỉnh ngân sách; không thể chọn chỉ theo Q2.

**Một quyết định hợp lý có thể kết hợp:** dùng B cho OLTP, nhưng chuyển Q3 sang warehouse/read replica chuyên dụng có contract và watermark, để không làm W1/W2 chậm bởi việc cập nhật summary cùng luồng ghi. Phải đo phương án mới chứ không suy rằng chi phí biến mất; nó được **chuyển sang pipeline, storage và độ trễ khác**.

### Chỉ số tổng hợp không thay các ngưỡng

Không nên tính “điểm hiệu năng = 0,4 × read + 0,3 × write + 0,3 × storage” khi một phương án **vi phạm bất biến** hoặc SLO cứng. Trước tiên loại phương án sai/nguy hiểm, sau đó phân tích Pareto giữa latency, throughput, chi phí và độ phức tạp vận hành.

## 21. Kiểm chứng dữ liệu và báo cáo sau tối ưu

Mỗi thay đổi vật lý phải bảo toàn ngữ nghĩa. Ví dụ kiểm tra:

~~~sql
-- Không có dòng hàng mồ côi (FK bình thường đã bảo vệ).
SELECT l.tenant_id, l.order_id, l.line_no
FROM bench.order_lines l
LEFT JOIN bench.orders o
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
WHERE o.order_id IS NULL;

-- Không nhân payment movement ở cùng grain.
SELECT tenant_id, movement_id, COUNT(*) AS n
FROM bench.payment_movements
GROUP BY tenant_id, movement_id
HAVING COUNT(*) > 1;

-- Tổng tiền capture/refund theo currency.
SELECT tenant_id, currency_code,
       SUM(CASE WHEN movement_type = 'CAPTURE'
                THEN amount_minor ELSE 0 END) AS captured_minor,
       SUM(CASE WHEN movement_type = 'REFUND'
                THEN amount_minor ELSE 0 END) AS refunded_minor
FROM bench.payment_movements
GROUP BY tenant_id, currency_code;
~~~

Hai query đầu có thể trả rỗng vì PK/FK đã chặn lỗi trong cùng database; chúng vẫn là phép kiểm tra hữu ích khi so dữ liệu xuất sang mart, staging hoặc shard khác không có cùng constraint.

### Golden fixture và checksum

Ngoài row counts, nên kiểm tra:

- Tập business key và số dòng theo tenant/ngày.
- Tổng `booked_total_minor` và `line_net_minor` theo định nghĩa khác nhau, ghi rõ vì sao có thể khác.
- Tổng `CAPTURE` và `REFUND` theo currency và mốc xác nhận.
- Số đơn có nhiều payment movements, số khách không có payment và số trường hợp đã hủy.
- Tỷ lệ missing references, kết quả của dữ liệu đến muộn, correction hoặc soft delete.
- Phiên bản quy tắc metric và mốc dữ liệu nhất quán khi đối chiếu.

Checksum chỉ có ý nghĩa nếu định nghĩa được **hàm chuẩn hóa và cùng tập hàng**. Hai tổng bằng nhau không chứng minh từng dòng đúng; có thể có một dòng tăng và một dòng giảm triệt tiêu nhau. Đối với dữ liệu quan trọng, so từng key/record hoặc hash theo partition/key sau chuẩn hóa.

## 22. Benchmark bền vững: chạy tải dài, đỉnh và lỗi

Một mô hình có thể đạt SLO trong 10 phút nhưng không đạt sau một ngày vì bloat, checkpoint, WAL backlog hoặc queue tích tụ. Phân biệt:

| Kiểu test | Tình huống | Điều cần đánh giá |
| --- | --- | --- |
| **Baseline** | Mức tải bình thường, warm cache. | Latency/throughput và plan ổn định. |
| **Peak/burst** | Khuyến mại hoặc hàng loạt callback. | Queue, P99, connection exhaustion, hot tenant. |
| **Soak test** | Nhiều giờ với mixed writes/reads. | Bloat, autovacuum, disk growth, memory leak/lag. |
| **Cold/cache pressure** | Restart hoặc quét khối dữ liệu lớn. | Phụ thuộc RAM, đọc disk và thời gian phục hồi. |
| **Backfill/retention** | Nạp lịch sử, tạo index, drop/archive partition. | WAL, lock, replica lag, headroom. |
| **Failure/recovery** | Một replica trễ, network timeout, process restart. | Idempotency, failover, consistency, mất dữ liệu. |
| **Scale sensitivity** | 1×, 2×, 4× dữ liệu/tải. | Điểm gãy của query plan và capacity. |

Không cố tình tạo lỗi có hại trong production để benchmark. Các kịch bản failover hoặc corruption đều phải có môi trường cô lập, backup/runbook và giới hạn quyền phù hợp.

### Đo tail latency dưới tải đồng thời

Báo cáo cần nêu chính xác concurrency/arrival rate. Một query Q2 10 ms khi không có hoạt động khác có thể tăng mạnh khi 100 worker W2 tranh cập nhật Order và checkpoint. Số “10 ms” không thể được dùng thay cho P95 ở workload thật.

## 23. Một mẫu báo cáo benchmark đủ để ra quyết định

Một báo cáo có cấu trúc:

1. **Mục tiêu:** quyết định giữa A/B/C, workload và SLO nào là bắt buộc.
2. **Môi trường:** DB version, server, storage, cấu hình, dữ liệu/seed, chính sách cache, replication và thứ tự chạy.
3. **Dataset:** số hàng từng bảng, skew/hot tenant, phân phối thời gian, số dòng/đơn, tỉ lệ trạng thái/NULL, PII đã xử lý theo policy.
4. **Phương án:** DDL/index/partition/denormalization và bất biến giữ nguyên.
5. **Cách đo:** driver, warmup, run duration, concurrency/arrival rate, retry/errors, percentiles, stats snapshots.
6. **Tính đúng:** golden fixtures, đối soát row keys, amount/currency/time, các trường hợp late/correction.
7. **Kết quả đọc:** Q1..Qn P50/P95/P99, throughput, plan, rows/buffers/bytes, cache, timeout.
8. **Kết quả ghi:** commit latency, transaction success, WAL/tx, HOT/bloat, lock/replica lag.
9. **Dung lượng:** heap/index/TOAST/summary, WAL/backups/headroom, dự báo theo kỳ.
10. **Rủi ro:** schema evolution, retention, hot shard, query không có shard key, khả năng rebuild.
11. **Quyết định:** chọn phương án và điều kiện cần triển khai; vì sao không chọn phương án khác.
12. **Điều kiện đánh giá lại:** khi data/tải tăng, SLO đổi, có query mới hoặc metric drift.

**Đừng chỉ báo “B nhanh hơn A 7 lần”.** Phải nêu *query nào*, mức tải nào, trên dataset nào, đúng kết quả nào, đổi lấy bao nhiêu tài nguyên và phạm vi áp dụng.

## 24. Những lỗi kiểm chứng thường gặp

| Sai lầm | Vì sao kết luận sai? | Cách khắc phục |
| --- | --- | --- |
| Sinh 100.000 hàng đều rồi suy cho 100 triệu. | Cache, planner và skew khác. | Dataset nhiều quy mô, phân phối đại diện. |
| Chỉ test truy vấn một tenant nhỏ. | Bỏ hot tenant và long-tail. | Weighted workload + phân nhóm tenant. |
| Chỉ đo SELECT, không chạy update. | Không thấy index write amplification, HOT/bloat. | Mixed read/write, soak test. |
| Lấy `EXPLAIN cost` làm milliseconds. | Cost là mô hình optimizer, không phải thời gian thực. | EXPLAIN ANALYZE + client latency. |
| Dùng một lần đo P50 rồi kết luận đạt SLO. | Không nhìn P95/P99 và timeout. | Histogram, percentiles, số request/error. |
| Đếm mỗi request thành công. | Che retry, timeout, queue. | Báo failure rate và request không hoàn tất. |
| Thêm index rồi so data chỉ trên warm cache khác nhau. | Cache/maintenance làm nhiễu. | Cùng warmup, luân phiên nhiều run. |
| Dùng 2 schema khác nhau về ràng buộc. | Phương án nhanh hơn có thể thiếu kiểm tra bất biến. | Giữ contract, PK/FK/unique và correctness gating. |
| SUM sau JOIN hai fact 1:N. | Đếm trùng tiền nhưng query vẫn nhanh. | Kiểm tra grain, aggregate trước JOIN. |
| Tính dung lượng chỉ bằng kích thước CSV. | Bỏ index/TOAST/WAL/bloat/replica. | Đo physical bytes và tổng chi phí vận hành. |
| Coi pg_stat counters là số cho riêng một query. | Số liệu tích lũy và hoạt động nền. | Snapshot delta, môi trường cô lập. |
| Ngắt autovacuum để test nhanh. | Không đại diện chi phí dài hạn. | Production-like maintenance và soak. |
| Đọc số liệu cũ từ replica rồi coi như nhất quán ngay. | Sai độ mới và source cutoff. | Chốt watermark/lag và reconciliation. |
| Test materialized mart mà giấu độ trễ cập nhật. | So hai mức nhất quán khác nhau. | Công bố freshness và chi phí refresh. |
| Test trên bản sao chứa PII không được phép. | Rủi ro bảo mật/tuân thủ. | Dữ liệu tổng hợp/ẩn danh có kiểm chứng, quyền tối thiểu. |
| Chọn index chỉ vì query cá biệt nhanh. | Làm chậm phần lớn workload hoặc tăng cost quá mức. | Đánh giá Pareto theo tần suất, chi phí và SLO. |

## 25. Bài tập thực hành: đánh giá thiết kế cho nền tảng bán vé

**Bối cảnh:** hệ thống bán vé có 150 tenant và nhiều buổi biểu diễn. Một `booking` gồm nhiều `ticket_line`; một `payment_attempt` có thể tạo nhiều movement capture/refund. Buổi bán vé lớn khiến 1% tenant chiếm 45% tải. Người dùng tra booking theo ID, xem 50 booking mới nhất và đội vận hành xem số vé bán theo giờ. Có các lệnh hủy/hoàn tiền đến muộn.

### Nhiệm vụ

1. **Chọn grain và khóa:** mô tả `booking`, `ticket_line`, `payment_movement`; nguồn có quyền xác nhận ghế và kết quả thanh toán. Xác định unique/FK theo tenant.
2. **Lập data profile:** đề xuất bảng số tenant, số booking, số dòng/booking, skew, thời gian, tỉ lệ trạng thái và movement. Phân biệt dữ liệu giả lập với thống kê thực.
3. **Lập SLO:** chọn ngưỡng P95/P99 cho tra booking, danh sách mới nhất, báo cáo giờ và transaction đặt vé; ghi concurrency, tốc độ đến và error budget.
4. **Tạo ba phương án:** A chuẩn hóa cơ bản, B index theo `tenant_id + placed_at`, C B cộng materialized hourly rollup. Chỉ rõ quyền sở hữu và độ mới của rollup.
5. **Chọn query workload:** ít nhất bốn query shape và ba kiểu transaction; thêm các tenant nóng/lạnh và số dòng cực trị.
6. **Viết SQL:** tạo schema thử có PK/FK/CHECK; truy vấn tra booking; truy vấn mới nhất với tie-breaker; tổng vé theo giờ không nhân bản do JOIN payment.
7. **EXPLAIN:** nêu trường cần ghi từ `EXPLAIN (ANALYZE, BUFFERS)` để phân tích sort, join fan-out, ước lượng sai và temp spill.
8. **Đọc/ghi hỗn hợp:** thiết kế một kịch bản open-loop tải 100, 300, 600 yêu cầu/giây và kịch bản burst; giải thích coordinated omission.
9. **Chi phí index:** đo thay đổi của P95 đọc, WAL/transaction, HOT updates, lock wait và index bytes.
10. **Dung lượng:** dùng `pg_table_size`, `pg_indexes_size` và `pg_total_relation_size`; dự báo 12–24 tháng có WAL/replica/backup/headroom.
11. **Partitioning:** thử chia theo tháng; phân tích PK/UNIQUE khi khóa business là `(tenant_id, booking_id)` và truy vấn không biết tháng.
12. **Correctness:** golden fixtures cho booking 3 dòng, 2 lần capture, 1 lần refund; chứng minh JOIN không nhân tiền; kiểm tra currency và callback trùng.
13. **Freshness:** so kết quả hourly rollup với nguồn giao dịch ở cùng watermark; xử lý cancellation/refund muộn và restatement.
14. **Độ bền:** thiết kế soak test, cold-ish cache, hot tenant, autovacuum, failover của replica và index rebuild.
15. **Báo cáo:** viết bảng A/B/C với P50/P95/P99, throughput, WAL per booking, storage, correctness và degree of confidence.
16. **ADR:** chọn phương án đáp ứng ràng buộc bắt buộc, chỉ rõ trade-off, mốc đánh giá lại và giới hạn chưa kiểm chứng.

### Bảng kiểm tự đánh giá

| Tiêu chí | Biểu hiện đạt |
| --- | --- |
| **Dữ liệu đại diện** | Có scale, skew, tương quan, hot/cold, dữ liệu ngoại lệ và nguồn/seed. |
| **Workload rõ** | Query shapes, tần suất, kích cỡ result, transaction semantics và concurrency. |
| **Đo đọc đúng** | Client P95/P99 + EXPLAIN/Buffers/plan, không chỉ server mean. |
| **Đo ghi đúng** | Thành công/abort/retry, commit latency, WAL, lock, HOT và bloat. |
| **Đo storage đủ** | Heap, indexes, TOAST/summary, WAL, replica, backup, headroom. |
| **Tính đúng** | Không nhân fact, không trộn currency, không bỏ PK/FK để tăng tốc. |
| **So sánh công bằng** | Cùng data/engine/config/semantics, cùng load và freshness được công bố. |
| **Vận hành** | Có soak/peak/failure, lag và phương án recovery. |
| **Quyết định** | Loại phương án vi phạm SLO/correctness, giải thích Pareto và đánh đổi. |

**Kết luận:** kiểm chứng mô hình dữ liệu cần đo **trên dữ liệu và workload có cấu trúc đại diện**, không phải chỉ tạo thật nhiều hàng hoặc chạy một truy vấn may mắn. Đọc phải được đánh giá bằng latency phân phối, kế hoạch và I/O; ghi phải tính cả transaction, index, WAL, lock, bloat và độ bền; dung lượng phải tính cả dữ liệu, chỉ mục, lịch sử và bản sao. Quan trọng hơn cả, những phương án được so sánh phải cùng **grain, khóa, định nghĩa số đo, quy tắc nhất quán và mức đúng nghiệp vụ**. Chỉ khi ghi rõ điều kiện đo, kiểm chứng kết quả và phân tích đánh đổi, một lựa chọn mô hình quan hệ, document, phân tán hay phân tích mới có cơ sở để đưa vào vận hành.
