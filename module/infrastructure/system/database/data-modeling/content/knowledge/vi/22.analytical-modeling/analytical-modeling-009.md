# Khi nào chọn mô hình chiều, Data Vault hoặc cách kết hợp

## 1. Bài toán lựa chọn: tối ưu cho người hỏi hay cho lịch sử nguồn?

Giả sử một doanh nghiệp bán hàng có ba nguồn: hệ thống thương mại điện tử quản lý đơn, CRM quản lý khách hàng và cổng thanh toán xác nhận thu/hoàn. Đội kinh doanh muốn xem **doanh thu ròng theo ngày, nhóm sản phẩm và kênh bán**. Đội quản trị dữ liệu cần biết **trường nào đến từ nguồn nào, giá trị đã thay đổi ra sao và có thể tái xử lý khi quy tắc hợp nhất khách hàng thay đổi không**. Đội vận hành lại cần nạp dữ liệu từ một nguồn ERP mới mà không làm hỏng báo cáo đang hoạt động.

Các mục tiêu đó không hoàn toàn giống nhau:

- **Mô hình chiều (dimensional modeling)** tổ chức dữ liệu theo **fact** và **dimension**, thường dưới dạng **star schema**, để người phân tích dễ hiểu và truy vấn hiệu quả. Đây là lựa chọn tự nhiên cho lớp dữ liệu phục vụ BI.
- **Data Vault** tổ chức lịch sử tích hợp nhiều nguồn thành **Hub** (định danh nghiệp vụ), **Link** (quan hệ) và **Satellite** (thuộc tính/lịch sử), nhằm bảo tồn truy xuất nguồn gốc, tách phần ổn định khỏi phần biến đổi và hỗ trợ nạp tăng dần.
- **Mô hình kết hợp** dùng Data Vault hoặc một lớp lịch sử tích hợp khác để giữ lịch sử nguồn, rồi xuất **dimensional marts** để người dùng phân tích nhanh, thống nhất chỉ số.

**Không có đáp án “Data Vault tốt hơn star schema” hoặc ngược lại trong mọi trường hợp.** Trước tiên phải chỉ rõ *đường đọc*, *lịch sử cần giữ*, *số lượng và tính biến động của nguồn*, *mức độ quản trị dữ liệu* và *năng lực vận hành*. Quyết định mô hình hóa phải dẫn tới khóa, ràng buộc, đơn vị đo, cách cập nhật, chỉ mục/vật lý và phép kiểm chứng được.

## 2. Nhìn đúng vai trò các lớp dữ liệu

Một kiến trúc phân tích thường có nhiều lớp chứ không chỉ một database:

~~~mermaid
flowchart LR
    E["E-commerce"] --> I["Landing / staging / CDC"]
    C["CRM"] --> I
    P["Payment"] --> I
    I --> V["Raw Vault hoặc lớp lịch sử nguồn"]
    V --> B["Business Vault / quy tắc hợp nhất"]
    B --> M["Dimensional marts: facts + dimensions"]
    M --> BI["Dashboard / SQL / semantic layer"]
~~~

Sơ đồ là **một phương án kết hợp**, không phải quy định mọi hệ thống phải triển khai đủ các lớp. Với nguồn ít, định nghĩa ổn định và yêu cầu BI đơn giản, hoàn toàn có thể đi từ staging đến dimensional mart mà không thêm Data Vault.

| Lớp | Nhiệm vụ chính | Dữ liệu phải giải thích được |
| --- | --- | --- |
| **Landing/staging** | Nhận dữ liệu, kiểm tra định dạng, metadata lần nạp, CDC hoặc snapshot nguồn. | Hàng/file nào đến từ nguồn nào, vào batch nào, lỗi nào bị cách ly. |
| **Raw Vault** (nếu chọn) | Lưu khóa nghiệp vụ, quan hệ và lịch sử thuộc tính với nguồn gốc rõ; hạn chế áp đặt logic tính KPI. | Nguồn, thời điểm nạp, chuỗi thay đổi; bản ghi nào tạo nên dữ liệu. |
| **Business Vault** (nếu chọn) | Áp dụng quy tắc chuẩn hóa/hợp nhất có kiểm soát, dựng point-in-time, bridge hoặc dữ liệu dẫn xuất. | Phiên bản quy tắc, căn cứ chọn dữ liệu, cách tái tính toán. |
| **Dimensional mart** | Cung cấp fact/dimension theo ngữ nghĩa nghiệp vụ và hiệu năng truy vấn. | Hạt dữ liệu, phép đo, chiều phân tích, định nghĩa KPI và thời gian. |
| **Semantic/BI** | Đặt tên measure, phân quyền, metric và hiển thị. | Người dùng hiểu “doanh thu”, “đơn thành công” theo cùng quy tắc. |

**Một điều kiện tối thiểu:** mỗi lớp phải có hợp đồng nguồn và cách kiểm chứng. Thêm nhiều lớp không tự nâng chất lượng dữ liệu; nếu không có owner, metadata và đối soát, kiến trúc chỉ có thêm độ trễ và chi phí.

## 3. Mô hình chiều: bắt đầu bằng hạt dữ liệu (grain)

Trong dimensional modeling, quyết định quan trọng nhất thường là **grain của fact**: *một dòng fact đại diện cho sự việc hoặc đối tượng đo nào?* Nếu grain mơ hồ, các phép SUM và JOIN rất dễ nhân đôi kết quả.

Ví dụ nhu cầu “doanh số theo sản phẩm và ngày”, có thể chọn:

> **Mỗi dòng `fact_order_line` là một dòng hàng trong một đơn tại lúc đơn được chấp nhận**, được định danh bằng `(tenant_id, order_id, line_id)`.

Từ grain này mới quyết định các chiều và measure:

| Thành phần | Ví dụ | Lưu ý thiết kế |
| --- | --- | --- |
| **Fact business key** | `tenant_id, order_id, line_id` | Dùng chống nạp trùng theo định danh của nguồn có thẩm quyền. |
| **Dimension keys** | `order_date_key`, `customer_sk`, `product_sk`, `channel_sk` | Khóa ngoại đến phiên bản chiều đã chọn đúng tại mốc nghiệp vụ. |
| **Measure** | `quantity`, `gross_minor`, `discount_minor`, `net_minor` | Định nghĩa đơn vị, dấu, quy tắc cộng và trường hợp hủy/hoàn. |
| **Degenerate dimension** | `order_id` | Dùng truy vết đơn mà không nhất thiết có `dim_order` riêng. |
| **Nguồn/kỹ thuật** | `source_system`, `source_record_id`, `loaded_at` | Hỗ trợ đối soát; không biến metadata kỹ thuật thành KPI. |

**Grain không thể là “một dòng tùy theo dữ liệu đang có”.** Nếu trong cùng fact vừa chứa đơn hàng (order header), vừa chứa dòng hàng (order line), vừa chứa lần hoàn tiền (refund), một đơn có ba dòng và hai giao dịch có thể tạo tích Descartes khi JOIN, khiến doanh thu bị nhân lên.

### Các dạng fact thường gặp

| Dạng fact | Grain thường thấy | Khi phù hợp |
| --- | --- | --- |
| **Transaction fact** | Một dòng hàng đã chấp nhận, một giao dịch thu/hoàn. | Lưu các phát sinh có thể cộng gộp, chi tiết phân tích. |
| **Periodic snapshot fact** | Một sản phẩm tại một kho **mỗi ngày**, một tài khoản **mỗi tháng**. | Theo dõi tồn kho/số dư qua các kỳ đều đặn; không nhầm số dư với dòng tiền. |
| **Accumulating snapshot fact** | Một hồ sơ xử lý có nhiều mốc từ mở đến đóng. | Đo thời gian giữa bước, pipeline có tiến trình dự kiến. |

Tên “snapshot” ở periodic/accumulating fact là **cách tổ chức đo lường phân tích**, không phải aggregate snapshot trong event sourcing và không thay thế backup.

### Tính cộng được của measure

- **Additive:** `quantity`, số tiền giao dịch cùng tiền tệ; có thể cộng qua các chiều phù hợp.
- **Semi-additive:** số dư cuối ngày, lượng tồn kho; cộng theo kho được nhưng **không** cộng số dư của các ngày như thể là dòng chảy.
- **Non-additive:** tỷ lệ chuyển đổi, đơn giá, trung bình; cần tính từ tử số và mẫu số phù hợp, không SUM hoặc AVG mù quáng các tỷ lệ nhóm.

Ví dụ `refund_rate = SUM(refunded_minor) / NULLIF(SUM(captured_minor), 0)` theo một định nghĩa được phê duyệt; không dùng `AVG(refund_rate)` của từng cửa hàng nếu kích thước mỗi cửa hàng khác nhau.

## 4. Ví dụ star schema: đơn hàng và chuyển động thanh toán

Một bản thiết kế PostgreSQL nhỏ cho thấy grain, khóa thay thế (surrogate keys), foreign key, CHECK và chỉ mục; mô hình sản phẩm thực tế có thể có nhiều chiều và nhiều loại fact hơn.

~~~sql
CREATE TABLE dim_customer (
    customer_sk       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         UUID NOT NULL,
    customer_bk       VARCHAR(100) NOT NULL,
    customer_segment  VARCHAR(40) NOT NULL,
    valid_from        TIMESTAMPTZ NOT NULL,
    valid_to          TIMESTAMPTZ,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    UNIQUE (tenant_id, customer_bk, valid_from)
);

-- Chỉ một phiên bản chiều còn mở cho mỗi business key.
CREATE UNIQUE INDEX ux_dim_customer_current
    ON dim_customer (tenant_id, customer_bk)
    WHERE valid_to IS NULL;

CREATE TABLE dim_product (
    product_sk        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         UUID NOT NULL,
    product_bk        VARCHAR(100) NOT NULL,
    category_name     VARCHAR(100) NOT NULL,
    UNIQUE (tenant_id, product_bk)
);

CREATE TABLE fact_order_line (
    tenant_id         UUID NOT NULL,
    order_id          VARCHAR(100) NOT NULL,
    line_id           VARCHAR(100) NOT NULL,
    order_date        DATE NOT NULL,
    customer_sk       BIGINT NOT NULL REFERENCES dim_customer(customer_sk),
    product_sk        BIGINT NOT NULL REFERENCES dim_product(product_sk),
    quantity          NUMERIC(18, 3) NOT NULL CHECK (quantity > 0),
    gross_minor       BIGINT NOT NULL CHECK (gross_minor >= 0),
    discount_minor    BIGINT NOT NULL CHECK (discount_minor >= 0),
    net_minor         BIGINT NOT NULL CHECK (net_minor >= 0),
    currency          CHAR(3) NOT NULL,
    source_system     VARCHAR(60) NOT NULL,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id, line_id),
    CHECK (discount_minor <= gross_minor),
    CHECK (net_minor = gross_minor - discount_minor)
);

CREATE INDEX ix_fact_order_line_date_product
    ON fact_order_line (order_date, product_sk);

CREATE TABLE fact_payment_movement (
    tenant_id          UUID NOT NULL,
    payment_movement_id VARCHAR(120) NOT NULL,
    order_id           VARCHAR(100) NOT NULL,
    movement_date      DATE NOT NULL,
    movement_type      VARCHAR(20) NOT NULL
                       CHECK (movement_type IN ('CAPTURE', 'REFUND')),
    amount_minor       BIGINT NOT NULL CHECK (amount_minor > 0),
    currency           CHAR(3) NOT NULL,
    provider_reference VARCHAR(120) NOT NULL,
    loaded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, payment_movement_id)
);
~~~

Giải thích những giới hạn của ví dụ:

1. `dim_customer` là một dạng **Slowly Changing Dimension Type 2 (SCD2)**; `customer_sk` xác định *phiên bản* cụ thể. Chỉ mục unique current ngăn hai hàng đang mở, nhưng **không tự ngăn mọi khoảng lịch sử chồng lấn**: hệ thống ghi hoặc exclusion constraint phải bảo vệ thêm khi cần.
2. `dim_product` ở ví dụ giữ thuộc tính hiện hành (kiểu gần Type 1); nếu phân loại sản phẩm thay đổi và báo cáo cần giữ nhóm tại thời điểm bán, cần SCD2 hoặc gắn giá trị lịch sử vào fact theo chính sách.
3. `fact_order_line` lưu doanh số ở hạt dòng hàng; đổi/trả hàng có thể cần fact điều chỉnh riêng hoặc cách biểu diễn sự kiện âm/dương được định nghĩa. Không âm thầm sửa fact lịch sử nếu báo cáo yêu cầu đối chiếu phát sinh.
4. `fact_payment_movement` giữ từng giao dịch **thu hoặc hoàn đã được nguồn xác nhận**, không gom chung vào grain dòng hàng. `amount_minor` là số dương; loại chuyển động quyết định dấu khi tính dòng tiền.
5. Trên hệ đa tenant, các surrogate key ở ví dụ là duy nhất toàn bảng, nhưng foreign key đơn giản chưa buộc fact và dimension thuộc cùng tenant. Cần kiểm tra nhất quán tenant trong ETL, hoặc dùng ràng buộc tổ hợp `(tenant_id, *_sk)` nếu đó là yêu cầu cách ly nghiêm ngặt.
6. Chỉ mục là gợi ý từ workload minh họa. Với kho dữ liệu cột, partition, clustering hoặc materialized aggregate có thể quan trọng hơn chỉ mục kiểu OLTP. Phải đo truy vấn thật.

### Truy vấn doanh số theo ngày và danh mục

~~~sql
SELECT f.order_date, p.category_name, f.currency,
       SUM(f.quantity) AS units_sold,
       SUM(f.net_minor) AS booked_net_minor
FROM fact_order_line f
JOIN dim_product p ON p.product_sk = f.product_sk
WHERE f.order_date >= DATE '2026-11-01'
  AND f.order_date <  DATE '2026-12-01'
GROUP BY f.order_date, p.category_name, f.currency;
~~~

`booked_net_minor` ở đây là **giá trị dòng hàng sau chiết khấu tại thời điểm đặt**, chưa phải doanh thu kế toán được ghi nhận và cũng chưa trừ refund. Muốn gọi là “doanh thu”, cần xác nhận chính sách về hủy, giao hàng, thuế, hoàn tiền và thời điểm công nhận.

### Truy vấn dòng tiền: không JOIN trực tiếp hai fact khác grain

~~~sql
SELECT movement_date, currency,
       SUM(CASE WHEN movement_type = 'CAPTURE'
                THEN amount_minor ELSE 0 END) AS captured_minor,
       SUM(CASE WHEN movement_type = 'REFUND'
                THEN amount_minor ELSE 0 END) AS refunded_minor,
       SUM(CASE WHEN movement_type = 'CAPTURE'
                THEN amount_minor ELSE -amount_minor END) AS net_cash_minor
FROM fact_payment_movement
GROUP BY movement_date, currency;
~~~

Tổng chỉ cộng cùng tiền tệ. Không dùng cùng tên `net` cho “tiền thu ròng” và “giá trị đơn hàng sau giảm giá”; chúng đo **hai quá trình khác nhau**.

## 5. SCD và phân tích “tại thời điểm xảy ra”

Một câu hỏi khó của star schema: khách thuộc phân khúc **VIP hay STANDARD khi đặt đơn**, hay thuộc phân khúc **hiện tại**?

Ví dụ:

| customer_sk | customer_bk | segment | valid_from | valid_to |
| ---: | --- | --- | --- | --- |
| 101 | CUS-42 | STANDARD | 2026-01-01 | 2026-07-01 |
| 205 | CUS-42 | VIP | 2026-07-01 | Không giới hạn |

Nếu đơn đặt vào 2026-05-10, fact phải tham chiếu `customer_sk = 101` khi yêu cầu “phân khúc tại thời điểm bán”. Nếu người xem muốn phân loại lại toàn bộ lịch sử theo phân khúc **hiện tại**, có thể xây semantic view hoặc một phép phân tích khác có định nghĩa rõ, không âm thầm thay khóa fact và làm sai ý nghĩa lịch sử.

Lookup phiên bản:

~~~sql
SELECT customer_sk
FROM dim_customer
WHERE tenant_id = :tenant_id
  AND customer_bk = :customer_bk
  AND valid_from <= :business_time
  AND (valid_to IS NULL OR :business_time < valid_to);
~~~

Quy ước khoảng nửa mở `[valid_from, valid_to)` tránh chọn hai phiên bản tại đúng điểm giao. Tuy nhiên, với điều chỉnh hồi tố, cần phân biệt **business effective time** và **thời điểm hệ thống biết giá trị**. SCD2 đơn giản với một trục valid-time không tự trả lời mọi câu hỏi bitemporal.

### Sự kiện đến trước dimension, sự kiện đến muộn

- **Early-arriving fact/late dimension:** fact đến trước dữ liệu khách hàng. Có thể dùng một thành viên chiều “unknown” được **phân biệt theo chính sách tenant/business key**, hoặc một inferred member để bổ sung thuộc tính sau; không gán mọi khách chưa biết thành một khách thật.
- **Late-arriving fact:** đơn được ghi nhận muộn nhưng có ngày nghiệp vụ cũ. Chọn `customer_sk` theo mốc sự kiện được phê duyệt, không theo ngày ETL nhận dữ liệu.
- **Retroactive correction:** sửa phân khúc có hiệu lực từ tháng trước có thể buộc cập nhật cách gắn dimension hoặc tính lại mart theo định nghĩa. Giữ lineage và kế hoạch restatement.

SCD2 được chọn khi người dùng **cần truy vấn lịch sử thuộc tính**, không phải cứ thay đổi thuộc tính nào cũng tạo SCD2. Với tên hiển thị sửa lỗi chính tả, Type 1 có thể phù hợp hơn; với phân khúc có tác động đến báo cáo quá khứ, Type 2 có thể cần thiết.

## 6. Data Vault: tách định danh, quan hệ và lịch sử thuộc tính

Data Vault tổ chức dữ liệu tích hợp theo một số khái niệm:

| Thành phần | Chứa gì? | Ví dụ |
| --- | --- | --- |
| **Hub** | Business key ổn định của một khái niệm nghiệp vụ; metadata nạp/nguồn. | `HUB_CUSTOMER` với `customer_bk`. |
| **Link** | Quan hệ giữa các hub, hoặc một giao dịch/hiệp hội được định danh theo quy tắc riêng. | `LINK_ORDER_CUSTOMER` nối order và customer. |
| **Satellite** | Thuộc tính có thể thay đổi theo thời gian, kèm metadata lịch sử và nguồn. | `SAT_CUSTOMER_CRM` giữ segment/tên theo lần nhận dữ liệu. |
| **Raw Vault** | Hệ hub/link/satellite phản ánh dữ liệu nguồn, giữ lineage và historization theo quy tắc nạp. | Nạp CRM/ERP mà không gắn trực tiếp toàn bộ logic KPI. |
| **Business Vault** | Thành phần dẫn xuất theo quy tắc nghiệp vụ có version, các cấu trúc hỗ trợ truy vấn lịch sử. | Kết quả hợp nhất danh tính, PIT, bridge, giá trị chuẩn. |

**Hub không phải dimension, Link không phải JOIN table dùng cho BI, Satellite không phải fact.** Các cấu trúc này hỗ trợ tích hợp và tái tạo dữ liệu nguồn; người dùng BI thường không nên phải tự nối hàng chục satellite, xử lý “latest row” và chọn thời điểm hợp lệ trong mọi dashboard.

### Ví dụ nhận diện customer từ nhiều nguồn

CRM có `customer_id = CUS-42`, hệ đơn có `buyer_id = U-908`. Hai giá trị có thể chỉ cùng một người, nhưng **không được tự coi giống nhau** vì hai hệ dùng tên trường tương tự. Có thể:

1. Giữ hai business key ở hai namespace nguồn khác nhau.
2. Lưu quan hệ mapping/cross-reference có bằng chứng trong Business Vault hoặc một miền master data.
3. Khi được xác nhận cùng thực thể, công bố `canonical_customer_id` theo quy tắc hợp nhất có version.
4. Cung cấp conformed dimension cho báo cáo, với cơ chế xử lý khi mapping bị sửa hoặc không xác định.

Nếu business key thật sự được quản trị thống nhất qua nhiều nguồn, có thể dùng chung hub cho khái niệm đó. **Ranh giới business key và namespace** phải do nghiệp vụ xác định, không chỉ lấy một chuỗi rồi băm.

## 7. Thiết kế vật lý Data Vault minh họa bằng PostgreSQL

Ví dụ đơn giản dùng khóa băm `CHAR(64)` là chuỗi hex SHA-256 của biểu diễn business key **đã chuẩn hóa và phân namespace có chủ đích**. Đây là một lựa chọn thường gặp của Data Vault 2.0, **không phải yêu cầu mọi triển khai Data Vault phải dùng khóa băm**; có thể dùng khóa khác nếu đáp ứng tính ổn định và khả năng tích hợp.

~~~sql
CREATE TABLE hub_customer (
    customer_hk    CHAR(64) PRIMARY KEY,
    tenant_id      UUID NOT NULL,
    customer_bk    VARCHAR(120) NOT NULL,
    load_dts       TIMESTAMPTZ NOT NULL,
    record_source  VARCHAR(80) NOT NULL,
    UNIQUE (tenant_id, customer_bk)
);

CREATE TABLE hub_order (
    order_hk       CHAR(64) PRIMARY KEY,
    tenant_id      UUID NOT NULL,
    order_bk       VARCHAR(120) NOT NULL,
    load_dts       TIMESTAMPTZ NOT NULL,
    record_source  VARCHAR(80) NOT NULL,
    UNIQUE (tenant_id, order_bk)
);

CREATE TABLE link_order_customer (
    order_customer_hk CHAR(64) PRIMARY KEY,
    order_hk          CHAR(64) NOT NULL REFERENCES hub_order(order_hk),
    customer_hk       CHAR(64) NOT NULL REFERENCES hub_customer(customer_hk),
    load_dts          TIMESTAMPTZ NOT NULL,
    record_source     VARCHAR(80) NOT NULL,
    UNIQUE (order_hk, customer_hk)
);

CREATE TABLE sat_customer_crm (
    customer_hk     CHAR(64) NOT NULL
                    REFERENCES hub_customer(customer_hk),
    load_dts        TIMESTAMPTZ NOT NULL,
    record_source   VARCHAR(80) NOT NULL,
    hashdiff        CHAR(64) NOT NULL,
    customer_name   TEXT,
    segment         VARCHAR(40),
    source_updated_at TIMESTAMPTZ,
    PRIMARY KEY (customer_hk, load_dts)
);

CREATE INDEX ix_sat_customer_crm_latest
    ON sat_customer_crm (customer_hk, load_dts DESC);
~~~

**Các giả định phải ghi ngay cạnh DDL:**

- `sat_customer_crm` biểu diễn **một dòng thuộc tính CRM cho mỗi customer tại mỗi mốc nạp**, với `load_dts` phân biệt được các phiên bản trong cùng hub. Nếu có hai thay đổi trong cùng microsecond hoặc nạp song song tạo trùng timestamp, cần batch sequence/ID khác hoặc khóa hỗ trợ để không mất lịch sử. `PRIMARY KEY(customer_hk, load_dts)` chỉ đủ theo hợp đồng ingest đã nêu.
- Satellite này lấy dữ liệu từ **một nguồn CRM logic**. Nếu nhiều nguồn cùng cung cấp segment với ý nghĩa hoặc tần suất khác nhau, cân nhắc satellite tách theo nguồn/ngữ nghĩa; không ghi đè thuộc tính của nguồn này bằng nguồn khác trong Raw Vault.
- `record_source` ghi nơi bản ghi được lấy/diễn giải; `load_dts` là **thời điểm nạp** đã quy định. Không mặc nhiên xem đó là lúc sự việc nghiệp vụ xảy ra.
- `source_updated_at` nếu có là mốc do nguồn cung cấp; nó có thể cũ hơn `load_dts`, khác múi giờ hoặc không đáng tin hoàn toàn. Phải kiểm tra hợp đồng và lưu metadata nhận dữ liệu.
- Link cho biết **một quan hệ đã được ghi nhận**; chỉ có Link không nói quan hệ đang còn hiệu lực hay từ lúc nào. Thông tin thay đổi/trạng thái của quan hệ cần satellite hoặc nguồn sự kiện và quy tắc tương ứng.
- Ràng buộc DDL chưa thể hiện đầy đủ cách xóa/đính chính, phụ thuộc child-key hoặc “một order chỉ thuộc một customer”. Những bất biến đó phải được thiết kế theo nghiệp vụ và kiểm tra nguồn.

### Khóa băm: không phải phép thuật giải quyết master data

Có thể định nghĩa một thuật toán ổn định như:

~~~text
customer_hk = SHA256(
    encode_canonical(tenant_id, customer_bk_namespace, customer_bk)
)

order_customer_hk = SHA256(
    encode_canonical(order_hk, customer_hk)
)
~~~

`encode_canonical` phải xác định chính xác ký tự Unicode, chuẩn hóa khoảng trắng/case **chỉ nếu nghiệp vụ cho phép**, thứ tự, length-prefix hoặc biểu diễn tránh va chạm khi nối chuỗi, charset và cách biểu diễn NULL. Hai pipeline phải dùng **cùng quy ước** thì mới tạo cùng khóa.

Nếu `CUS-42` ở hai tenant là hai người khác nhau thì tenant phải thuộc không gian định danh. Nếu một nguồn dùng mã đơn chỉ duy nhất *trong chính nguồn*, namespace nguồn phải tham gia business key hoặc phải có ánh xạ được xác minh. Nhưng nếu cùng business entity có một business key thật sự chung trên các nguồn, tự thêm `record_source` vào hash hub sẽ tạo **hai hub khác nhau**, làm mất ý nghĩa tích hợp. Cần phân biệt `business_key_namespace` với metadata `record_source` theo định nghĩa nghiệp vụ.

Khóa băm có xác suất collision rất nhỏ khi chọn thuật toán phù hợp, nhưng không thay kiểm soát trùng business key và đối chiếu dữ liệu gốc. **Hashdiff** trên thuộc tính satellite là cơ chế **phát hiện thay đổi** theo quy tắc chuẩn hóa, không phải chữ ký bảo mật hay bằng chứng pháp lý về sự thật. Hãy kiểm tra cả nội dung khi nghi ngờ collision hoặc sai chuẩn hóa.

## 8. Nạp Raw Vault: giữ lịch sử và nguồn gốc như thế nào?

Một pipeline Raw Vault điển hình:

1. Nhận dữ liệu theo **batch/CDC/snapshot**, lưu định danh nguồn, ID bản ghi, mốc trích xuất và ID lần nạp.
2. Kiểm tra định dạng cơ bản, business key thiếu/không hợp lệ, trùng lặp trong batch và chính sách cách ly bản ghi lỗi.
3. Chuẩn hóa **khóa kỹ thuật phục vụ tích hợp** theo hợp đồng đã duyệt, không tự hòa trộn hai khách khi chưa có bằng chứng.
4. Insert Hub nếu business key chưa có, không cập nhật tên khách trong Hub.
5. Insert Link nếu quan hệ chưa được ghi; kiểm tra độ đầy đủ/đúng namespace của hub tham chiếu.
6. Với Satellite, tính `hashdiff` trên nhóm thuộc tính theo hợp đồng; chỉ ghi phiên bản mới khi có thay đổi **có ý nghĩa theo chính sách nạp**.
7. Lưu `load_dts`, `record_source` và metadata cần thiết để đối chiếu; không phá lịch sử đã giữ khi nhận một trạng thái mới.
8. Đối chiếu số bản ghi nguồn, business keys, thay đổi, lỗi và sự kiện xóa/điều chỉnh.

Ví dụ dòng CRM:

~~~text
Batch 1, 2026-06-01: CUS-42, segment=STANDARD
Batch 2, 2026-07-10: CUS-42, segment=VIP
Batch 3, 2026-07-11: CUS-42, segment=VIP (không đổi)
~~~

Với một satellite lưu phiên bản khi hashdiff thay đổi, hai dòng phiên bản cần được ghi tại Batch 1 và Batch 2; Batch 3 không tạo một bản thuộc tính giống hệt nếu quy tắc là chỉ ghi khi có thay đổi. **Không suy rằng segment bắt đầu có hiệu lực chính xác vào ngày nạp**: đây chỉ là hai mốc hệ thống quan sát được, trừ khi nguồn cung cấp `effective_from` có thẩm quyền và được mô hình hóa riêng.

### CDC delete, late arrivals và replay

- Một **DELETE ở nguồn** không nên tự động xóa tất cả Hub/Link/Satellite trong Raw Vault nếu kiến trúc đã cam kết giữ lịch sử. Cần mô hình hóa trạng thái record-tracking/deletion theo hợp đồng nguồn và chính sách retention.
- Event hoặc CDC đến **muộn/sai thứ tự** phải được so sánh theo vị trí CDC/transaction log nếu cần tái dựng thứ tự nguồn, không chỉ theo giờ máy ingest.
- Nạp lại một batch phải **idempotent**: không tự tạo phiên bản satellite trùng khi retry. Dedupe dựa trên nguồn + định danh bản ghi/vị trí thay đổi hoặc cơ chế tương đương, không chỉ so hashdiff toàn dữ liệu.
- Nếu dữ liệu nguồn là snapshot hằng ngày, việc “không xuất hiện” có thể có nghĩa đã xóa, không được trích xuất, lỗi phân trang hoặc scope lọc đổi. Không suy ra “bị xóa” khi chưa có chính sách snapshot-completeness.
- Quy tắc đồng nhất Hash Key/Hashdiff phải được kiểm thử giữa các luồng nạp và khi thay đổi code; sai chuẩn hóa làm lịch sử bị nhân đôi.

Lịch sử append-only của Data Vault giúp phân tích nguồn nhưng **không tự làm dữ liệu đúng**: khi nguồn gửi sai số tiền, cần nguồn xác nhận/correction, không chỉ dựa vào fact “đã có phiên bản mới”.

## 9. Business Vault: biến lịch sử nguồn thành định nghĩa kinh doanh

Raw Vault giữ các sự thật **đã quan sát từ nguồn** và quan hệ theo quy tắc nạp. Nhưng dashboard thường cần câu hỏi phức tạp hơn:

- Hai customer ID từ CRM và e-commerce có cùng một khách thực không?
- Doanh số được công nhận ở bước nào: tạo đơn, giao hàng, capture hay lập hóa đơn?
- Khi nguồn CRM và ERP bất đồng tên/địa chỉ, nguồn nào được ưu tiên?
- Muốn xem thông tin **hệ thống biết vào ngày X** hay thông tin **được công nhận có hiệu lực ở ngày X**?

Đó là nơi cần lớp **Business Vault**, pipeline biến đổi được quản trị hoặc semantic transformation có version. Các đối tượng thường gặp:

| Đối tượng dẫn xuất | Tác dụng | Rủi ro nếu không quản trị |
| --- | --- | --- |
| **Master/canonical customer mapping** | Hợp nhất định danh có bằng chứng và thời điểm hiệu lực. | Gộp hai người khác nhau hoặc làm biến mất nguồn gốc. |
| **Business rule satellite** | Lưu thuộc tính dẫn xuất theo chính sách/vòng đời. | Khó biết số liệu được tính theo công thức nào. |
| **PIT (Point-In-Time) table** | Liệt kê phiên bản satellite thích hợp ở một mốc đọc, giảm nhiều phép tìm latest row. | PIT sai khi xử lý dữ liệu đến muộn hoặc định nghĩa thời gian sai. |
| **Bridge table** | Tổ chức đường nối nhiều link/hub hoặc phân cấp cần truy vấn thường xuyên. | Nhân bản quan hệ, double count nếu grain không rõ. |
| **Reference/standardization** | Ánh xạ mã trạng thái, ngành hàng, đơn vị, tiền tệ. | Áp quy tắc hiện tại cho quá khứ mà không có version. |

Ví dụ một PIT theo ngày có thể chứa:

~~~text
pit_customer_daily
(customer_hk, snapshot_date, sat_crm_load_dts, sat_erp_load_dts)
~~~

Khi trả lời “CRM và ERP **được kho dữ liệu biết** điều gì tại cuối ngày?”, dùng mốc `load_dts` theo thỏa thuận. Khi trả lời “khách có phân khúc **hiệu lực nghiệp vụ** nào tại ngày đó?”, cần `effective_at`/valid-time từ nguồn hoặc logic phê duyệt và có thể cần bitemporal. PIT không biến ingestion time thành business time.

**Business Vault không bắt buộc phải là một database khác.** Đó là phân chia trách nhiệm, lớp dữ liệu và hợp đồng transform. Với kiến trúc nhỏ, cùng mục đích có thể được thực hiện trong SQL/dbt/ELT được version hóa; không nhất thiết dựng đầy đủ thuật ngữ và cấu trúc Data Vault.

## 10. Bảng so sánh để quyết định theo yêu cầu

| Tiêu chí | Mô hình chiều trực tiếp | Data Vault làm lớp tích hợp | Kết hợp Vault → marts |
| --- | --- | --- | --- |
| **Ưu tiên thiết kế** | Câu hỏi BI, grain, metric và truy vấn dễ hiểu. | Khóa nghiệp vụ, quan hệ, lịch sử nguồn, lineage. | Vừa bảo tồn nguồn vừa công bố mô hình BI dễ dùng. |
| **Nguồn dữ liệu** | Ít hoặc đủ ổn định để chuẩn hóa trực tiếp. | Nhiều nguồn có schema và nhịp thay đổi độc lập. | Nhiều nguồn và nhiều nhóm BI/metric cùng cần. |
| **Lịch sử** | SCD2, fact theo thời gian, audit/landing theo nhu cầu. | Satellite historization, nguồn và thời gian nạp rõ. | Lịch sử nguồn ở Vault, lịch sử báo cáo được chọn ở marts. |
| **Đổi yêu cầu báo cáo** | Thay marts và có thể backfill từ staging/history. | Có nền lịch sử để tái xử lý, nhưng phải xây read model. | Rebuild mart mới từ nguồn lịch sử đủ và quy tắc version hóa. |
| **Người dùng SQL/BI trực tiếp** | Dễ hơn; JOIN fact/dimension phù hợp. | Khó hơn; nhiều bảng và thời điểm. | Người dùng đọc marts, không phải Vault thô. |
| **Chi phí lưu/ELT** | Thường ít lớp, đơn giản hơn trong phạm vi nhỏ. | Nhiều bảng, metadata, pipeline và kiểm thử. | Tốn thêm lớp nhưng giảm lặp tích hợp nếu dùng lại nhiều marts. |
| **Nạp thay đổi nguồn** | Có thể cần sửa mapping và backfill mart. | Tách biến động thuộc tính vào satellite/nguồn. | Nguồn mới nạp Vault; sau đó công bố qua metric chuẩn. |
| **Kiểm toán nguồn** | Khả thi nếu staging/audit/lineage đủ tốt. | Thường là ưu tiên thiết kế. | Giữ lineage xuống tầng báo cáo nếu đã triển khai mapping. |
| **Rủi ro chính** | Chọn sai grain, SCD hoặc mất lịch sử nguồn phục vụ restatement. | Overengineering, băm khóa sai, lịch sử nạp bị hiểu là thời gian nghiệp vụ. | Chi phí, độ trễ và sai lệch giữa định nghĩa mart và Vault. |

Data Vault không tự bảo đảm **hiệu năng truy vấn dashboard**; mô hình chiều không đồng nghĩa **không có lineage hoặc lịch sử**. Sự khác biệt là điều gì được coi là **đối tượng thiết kế chính** và chi phí kiểm soát thay đổi được đặt ở lớp nào.

## 11. Ba tình huống lựa chọn thực tế

### Tình huống A — Một nguồn, báo cáo ổn định: chọn mô hình chiều trực tiếp

Một cửa hàng có một ứng dụng quản lý bán hàng, các bảng đơn và sản phẩm đã được chuẩn hóa, dữ liệu được lưu đủ theo chính sách. Đội BI cần doanh số theo ngày/sản phẩm, tồn kho và số đơn hủy. Số lượng nguồn ít; không yêu cầu tái dựng lịch sử thuộc tính ngoài SCD2 của phân khúc và danh mục.

**Thiết kế hợp lý:** landing/staging có checkpoint và lineage tối thiểu, transform sang `fact_order_line`, `fact_payment_movement`, `dim_customer`, `dim_product` và những dimension cần thiết. Định nghĩa KPI trong semantic layer. **Không cần Data Vault chỉ để giải quyết một phép JOIN.**

Phải bảo đảm kiểm tra uniqueness grain, dữ liệu muộn, khóa dimension tại thời điểm bán và dữ liệu nguồn đủ cho rebuild. Nếu chỉ snapshot bảng order hiện tại mỗi ngày, không thể khẳng định phục hồi mọi chi tiết giao dịch quá khứ đã bị ghi đè.

### Tình huống B — Tập đoàn đa nguồn, nhiều thay đổi: cân nhắc Data Vault

Doanh nghiệp có nhiều ERP, CRM khu vực, hệ thanh toán độc lập và các hệ thống được sáp nhập. Business key trùng tên nhưng khác ý nghĩa; schema các nguồn thay đổi liên tục; kiểm toán cần biết “nguồn A gửi gì vào ngày X” và có thể tái chạy quy tắc hợp nhất.

**Thiết kế hợp lý:** Raw Vault để phân tách business keys, quan hệ và lịch sử nguồn; Business Vault cho hợp nhất ID và quy tắc ưu tiên có version. Sau đó dựng marts theo nhóm sử dụng. Đầu tư thêm vào metadata nguồn, monitoring, điều phối nạp và kiểm thử hashing.

Điểm mấu chốt là **tính truy nguyên và khả năng tái tích hợp**, không phải giả định Data Vault tự giảm chi phí query hay làm hết tranh cãi về “khách hàng duy nhất”.

### Tình huống C — Doanh nghiệp tăng trưởng: chọn kết hợp có phạm vi

Công ty thương mại điện tử ban đầu xây star schema trực tiếp từ e-commerce, nhưng nay thêm ERP, CRM và payment; bộ phận tài chính yêu cầu lưu lịch sử được đối soát và nhiều báo cáo có cùng định nghĩa.

**Thiết kế hợp lý:** giữ marts đã có để không làm gián đoạn BI; bổ sung lớp lịch sử tích hợp cho các miền có nhu cầu cao (Order, Customer, Payment), rồi thay dần nguồn đầu vào của marts. Có thể chỉ triển khai Data Vault cho các miền phức tạp; những nguồn tham chiếu đơn giản vẫn được chuẩn hóa trực tiếp nếu kiểm soát lineage đầy đủ.

Đừng tạo một “Big Bang migration” chỉ để tất cả bảng có Hub/Link/Satellite. Chọn từng bounded context, đo giá trị của lịch sử và chi phí bổ sung.

## 12. Cách ghép Data Vault với star schema mà không làm mất ngữ nghĩa

Trong mô hình kết hợp, một đối tượng ở Vault có thể được chuyển thành nhiều dimension/fact, nhưng quá trình này phải được ghi thành **hợp đồng chuyển đổi**.

~~~mermaid
flowchart TD
    RAW["Raw Vault: HUB_ORDER, HUB_CUSTOMER, LINK_ORDER_CUSTOMER, SAT_*"] --> RULES["Business rules: canonical IDs, thời điểm, trạng thái"]
    RULES --> DIM["dim_customer SCD2 + dim_product"]
    RULES --> FACT["fact_order_line"]
    RULES --> CASH["fact_payment_movement"]
    DIM --> KPI["Semantic layer: booked sales, cash flow"]
    FACT --> KPI
    CASH --> KPI
~~~

### Một đường chuyển đổi mẫu

1. **Hub Order** xác định đơn, business key và namespace; **Link Order–Customer** nêu quan hệ được ghi nhận.
2. **Satellite Order/Order Line** lưu trạng thái và các thuộc tính được nguồn gửi; nếu có nhiều lần sửa, cần định nghĩa đâu là giao dịch phát sinh, đâu là phiên bản/correction.
3. **Business rule** xác định lúc một dòng được tính là đơn hàng đặt thành công; chọn quantity, currency, giá, chiết khấu theo mốc và quy tắc chấp nhận.
4. **Conformed Customer Dimension** gắn `customer_sk` với business key đã hợp nhất và phiên bản SCD2 tại mốc giao dịch.
5. **Fact Order Line** có đúng một hàng theo `(tenant_id, order_id, line_id)` theo định nghĩa nghiệp vụ đã chốt. Nếu các dòng đơn bị sửa nhiều lần và báo cáo cần mọi lần thay đổi, cần mô hình fact khác hoặc history riêng.
6. **Payment Movement Fact** lấy từ giao dịch capture/refund **đã được nguồn có thẩm quyền xác nhận**, không tự coi `RefundRequested` là tiền đã hoàn.
7. Mỗi hàng mart giữ tối thiểu metadata lineage hoặc có đường truy ngược tới record/Hub/Link/Satellite và phiên bản rule đã tạo nó.

### Nếu khách thuộc hai nguồn thì sao?

Hợp nhất khách không chỉ là JOIN `customer_bk` bằng chuỗi. Có thể cần bảng mapping có:

~~~text
(source_system, source_customer_bk, canonical_customer_bk,
 valid_from, valid_to, mapping_rule_version, evidence_id)
~~~

Một mapping được điều chỉnh hồi tố có thể ảnh hưởng nhiều dòng fact lịch sử. Hệ thống phải chọn chính sách: **giữ chiều tại thời điểm báo cáo cũ** hoặc **restatement báo cáo** theo mapping mới, có mốc/version công bố rõ.

### Nói rõ “as-of” là thời gian nào

- `event_time` / `business_effective_time`: lúc sự việc có hiệu lực theo nghiệp vụ.
- `source_updated_at`: lúc hệ nguồn cho biết nó đã sửa bản ghi.
- `load_dts`: lúc dữ liệu được đưa vào Vault.
- `mart_loaded_at`: lúc bảng phân tích được cập nhật.

Khi chọn một satellite “mới nhất”, không được mặc định chọn `MAX(load_dts)` là sự thật **có hiệu lực** tại ngày bán. Nếu một bản correction đến muộn, thứ tự ingest và thứ tự nghiệp vụ có thể khác nhau. Mô hình cần phân biệt thời gian hợp lệ và thời gian ghi nhận, đôi khi theo hướng bitemporal.

## 13. Tránh lỗi đếm trùng ở cả hai mô hình

Trong star schema, nối hai fact khác grain là nguồn lỗi phổ biến. Trong Data Vault, nối Hub → nhiều Link → nhiều Satellite version cũng có thể làm nhân số hàng.

### Ví dụ nguy cơ fan-out

Một order có hai dòng hàng và ba lần thay đổi CRM segment. Nếu lấy tất cả version của `SAT_CUSTOMER_CRM` rồi JOIN trực tiếp với hai dòng hàng, kết quả có thể thành **sáu hàng**. `SUM(net_minor)` bị nhân ba dù đơn chỉ có hai dòng.

Cách giải quyết:

1. Xác định grain đích (một dòng/order line ở mốc bán).
2. Chọn **một** phiên bản customer satellite phù hợp theo chính sách thời gian đã định nghĩa.
3. Gắn một `customer_sk` thích hợp cho mỗi dòng fact.
4. Kiểm tra số hàng trước và sau JOIN; kiểm tra uniqueness theo grain.
5. Nếu quan hệ thật sự nhiều-nhiều (nhiều nhân viên cùng đóng góp doanh số), dùng bridge/allocation rule để tránh phân bổ doanh số 100% cho từng người rồi SUM như tổng toàn hệ thống.

Trong Data Vault, PIT/bridge giúp giảm lặp logic “chọn phiên bản và nối quan hệ” nhưng không tự sửa được **grain hoặc business rule sai**.

### Kiểm chứng SQL đơn giản

~~~sql
-- Mỗi grain chỉ xuất hiện một lần trong mart.
SELECT tenant_id, order_id, line_id, COUNT(*) AS n
FROM fact_order_line
GROUP BY tenant_id, order_id, line_id
HAVING COUNT(*) > 1;

-- So sánh tổng giá trị trước/sau một phép JOIN phải cùng grain.
SELECT currency, SUM(net_minor) AS booked_net_minor
FROM fact_order_line
GROUP BY currency;
~~~

Câu thứ nhất phải trả **0 dòng** nếu fact theo grain đã định. Câu thứ hai cho tổng cơ sở để đối chiếu sau khi thêm dimension; cần bảo đảm JOIN không làm mất hàng hoặc nhân hàng.

## 14. Thay đổi nguồn, backfill và khả năng tái tạo

Bài toán nạp mới hoặc tái xử lý thường quan trọng hơn sơ đồ chỉ nhìn vào một thời điểm.

| Tình huống | Mô hình chiều trực tiếp cần gì? | Data Vault/kết hợp cần gì? |
| --- | --- | --- |
| Nguồn thêm trường tùy chọn | Điều chỉnh staging/transform; bổ sung dimension/measure khi có nghĩa. | Tách thuộc tính vào Satellite hoặc phiên bản mới; marts chỉ đổi khi cần. |
| Nguồn đổi business key | Mapping ổn định, kiểm tra trùng và backfill keys trong dims/facts. | Xác định namespace, mapping Hub và Link; không tái băm tùy tiện. |
| Correction hồi tố | Re-evaluate SCD2/fact bị ảnh hưởng và công bố restatement. | Giữ lịch sử nạp, quy tắc chọn hiệu lực trong Business Vault, rebuild mart. |
| Nguồn ngừng gửi | Chính sách dữ liệu thiếu/late, không âm thầm coi NULL/0 là sự thật. | Giữ trạng thái nguồn đã quan sát, đánh dấu freshness và giới hạn. |
| Nạp lại batch | Upsert/idempotency theo grain và batch/source ID. | Dedupe business key, link và satellite changes theo hợp đồng. |
| Yêu cầu xóa dữ liệu | Xử lý fact/dim, staging, exports, cache, backup theo policy. | Thêm Hub/Link/Sat, PIT/Bridge, marts và lineage vào phạm vi kiểm soát. |

**Data Vault giữ được lịch sử đã nhận**, không thể tự khôi phục sự kiện mà nguồn chưa bao giờ cung cấp. Nếu CRM chỉ xuất snapshot cuối ngày và thay đổi ba lần trong ngày, kho lưu không thể biết ba lần chuyển nếu không có log nguồn khác. Tương tự, một star schema với CDC/ảnh lịch sử đủ chi tiết có thể đáp ứng nhiều yêu cầu replay mà không cần Data Vault.

### Rebuild mart an toàn

1. Định nghĩa contract của mart v2: grain, dimensions, measure, đơn vị, thời gian và chính sách late-arrival.
2. Chọn nguồn lịch sử và **mốc dữ liệu an toàn** theo cơ chế commit/cursor được bảo đảm; không tự coi ID sequence cấp trước commit là watermark chắc chắn.
3. Xây mart v2 song song với mart đang phục vụ; nạp lịch sử và theo kịp phần cập nhật mới.
4. Kiểm chứng số bản ghi theo grain, tổng tiền theo tiền tệ, dữ liệu thiếu chiều, đối chiếu nguồn và những ca correction/refund.
5. Chuyển read path/semantic layer sang v2 có kiểm soát; giữ phương án rollback cho đến khi ổn định.
6. Ghi version quy tắc và mốc chuyển đổi để người dùng hiểu tại sao số liệu được restate.

## 15. Chi phí và năng lực vận hành: điều kiện chặn trước khi chọn

Kiến trúc Data Vault có thể đặc biệt hữu ích khi có nhiều nguồn và lịch sử dài, nhưng chi phí không chỉ là dung lượng thêm:

- **Số bảng và pipeline:** Hub/Link/Satellite, PIT/bridge, marts, kiểm tra khóa, monitoring.
- **Chi phí tính toán:** hash, dedup, historization, xây lại PIT, chuyển đổi sang dimension/fact, JOIN nhiều bước.
- **Chi phí chuyên môn:** quản trị business key, source identity, chuẩn hóa, version của rule và naming convention.
- **Độ trễ dữ liệu:** thêm lớp không tự bảo đảm SLA thời gian thực; cần đo tần suất nạp và lag qua từng lớp.
- **Chi phí chất lượng:** đối soát dữ liệu không đúng grain, không đúng thời gian, sai mapping khách và các trường thiếu.
- **Bảo mật/quyền riêng tư:** nhiều bản dẫn xuất có thể làm tăng bề mặt truy cập và yêu cầu xử lý xóa.

Ngược lại, star schema trực tiếp có thể tăng chi phí khi doanh nghiệp thêm nhiều nguồn: logic tích hợp và SCD bị lặp ở nhiều mart; việc thay đổi định nghĩa doanh thu có thể phải sửa nhiều pipeline. Quyết định nên so sánh **tổng chi phí thay đổi trong khoảng thời gian dự kiến**, không chỉ số bảng tuần đầu.

### Những phép đo nên có

| Chỉ tiêu | Cách quan sát |
| --- | --- |
| Freshness | Thời gian từ nguồn commit/xác nhận đến lúc mart phục vụ báo cáo. |
| Chất lượng grain | Số key fact trùng; số JOIN fan-out; tỷ lệ orphan/unknown dimension. |
| Lineage | Tỷ lệ hàng mart truy ngược được đến nguồn và rule version. |
| Nạp & retry | Số batch fail/retry, sai lệch record count, thay đổi bất thường hashdiff. |
| Khả năng backfill | Thời gian, chi phí và độ chính xác rebuild một kỳ lịch sử. |
| Tài nguyên | CPU, scan bytes, storage, index/partition maintenance, số pipeline. |
| Tác động người dùng | P95/P99 query BI theo workload, mức thay đổi KPI sau restatement. |

Đánh giá thử nghiệm cần dùng **cùng dataset, cùng định nghĩa KPI và truy vấn**, gồm cả ca nguồn đến muộn, sửa dữ liệu, nhiều tiền tệ và thay đổi business key. Chỉ đo “SELECT COUNT(*)” không phản ánh giá trị của mô hình.

## 16. Chất lượng, quyền riêng tư và trách nhiệm dữ liệu

Một mô hình có lineage tốt nhưng cho phép báo cáo lộ PII hoặc cộng tiền sai vẫn là mô hình chưa đạt yêu cầu.

### Kiểm tra chất lượng theo tầng

**Staging:**
- Nguồn/cursor/batch ID hợp lệ; không mất hoặc nhân bản dữ liệu do retry.
- Có cách ly record lỗi schema và xử lý timestamp/tiền tệ.
- Snapshot nguồn được xác nhận đầy đủ trước khi suy rằng bản ghi đã bị xóa.

**Raw Vault:**
- Hub business key duy nhất trong phạm vi đúng; khóa băm ổn định và có phương án đối chiếu.
- Link tham chiếu hub hợp lệ, không tạo quan hệ chỉ vì trùng mã ở hai nguồn.
- Satellite theo dõi thay đổi thật, metadata nguồn và thời điểm nạp đầy đủ.
- CDC/correction/record-tracking tuân thủ quy tắc historization.

**Marts:**
- Fact đúng grain, không có bản ghi trùng; dimension key đúng thời điểm.
- KPI được tính từ giao dịch có nguồn xác nhận; không trộn capture với refund request.
- Không cộng chéo các tiền tệ hoặc cộng số dư qua thời gian.
- Lineage từ mart về nguồn và logic mapping có thể kiểm tra.

### Quyền riêng tư và retention

Nếu khách yêu cầu erasure hoặc pháp luật/chính sách giới hạn lưu giữ, việc có Raw Vault append-only **không miễn trừ nghĩa vụ xử lý dữ liệu**. Cần đánh giá mọi nơi giữ dữ liệu: landing, hub, satellite, link, PIT, bridge, dimension, fact, semantic caches, export, backup.

- Giảm sao chép trực tiếp tên/email/số điện thoại vào mọi lớp; dùng định danh thay thế và kiểm soát liên kết khi phù hợp.
- Phân quyền riêng giữa Raw Vault chi tiết và marts công bố; áp dụng row/column security hoặc phân tách vật lý theo yêu cầu.
- Xây cơ chế retention/ẩn danh/xóa có kiểm chứng, kể cả dữ liệu dẫn xuất và bản sao lưu theo chính sách.
- Không coi hash business key là dữ liệu đã được ẩn danh tuyệt đối; khóa băm vẫn có thể liên kết/tra ngược trong một số bối cảnh.
- Hạn chế dữ liệu nhạy cảm trong `record_source`/metadata; hashdiff là thay đổi kỹ thuật, không thay bằng chứng quyền truy cập.
- Khi xóa/ẩn danh làm giảm khả năng tái tạo lịch sử, cần ghi rõ phạm vi và điều kiện rebuild còn được cam kết.

## 17. Quy trình ra quyết định và ví dụ ADR

Một cách quyết định có trách nhiệm là viết **Architecture Decision Record (ADR)** theo từng miền thay vì yêu cầu toàn doanh nghiệp chọn một kiểu mô hình.

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Dashboard cần trả lời những gì, ở grain nào? | Danh mục KPI, mẫu SQL, hình thức drill-down và SLO. |
| Có bao nhiêu nguồn, cùng một business key có nghĩa gì? | Source inventory, mẫu ID, quy tắc nhận diện và mapping. |
| Lịch sử cần giữ/đối soát đến mức nào? | Audit requirement, mẫu dữ liệu đến muộn/correction, thời hạn lưu. |
| Mức biến động schema và quan hệ? | Dữ liệu thay đổi 6–12 tháng hoặc kịch bản roadmap có căn cứ. |
| Có cần tái tạo marts theo định nghĩa mới? | Ca KPI restatement và thử nghiệm backfill. |
| Năng lực đội ngũ? | Tooling, quản trị metadata, thời gian hỗ trợ và kinh nghiệm hashing/SCD. |
| Rủi ro nào không chấp nhận? | PII/tenant isolation, đối soát tài chính, sai KPI, độ trễ, chi phí. |

**Ví dụ ADR rút gọn:** “Trong 6 tháng đầu, một e-commerce và một payment provider là hai nguồn chính; dashboard yêu cầu booked sales, gross captured, refunds và net cash theo ngày; giao dịch lịch sử đã lưu đủ và có CDC. Chọn staging có lưu raw/lineage và star schema trực tiếp để giảm chi phí. Không dựng Raw Vault toàn miền ở giai đoạn này. Đánh giá lại khi có từ ba hệ nghiệp vụ độc lập, xuất hiện xung đột business keys hoặc cần tích hợp lịch sử từ M&A.”

Một ADR khác có thể chọn: “Nhiều CRM/ERP độc lập, mapping khách thay đổi và báo cáo tài chính cần tái tính nhiều năm. Dùng Raw Vault + Business Vault cho Customer/Order/Payment; cung cấp dimensional marts cho BI. Chấp nhận thêm chi phí với điều kiện có kiểm chứng lineage, rule version và SLO nạp.”

Điều quan trọng là **điều kiện đánh giá lại** và **thước đo kiểm chứng**, không phải lời hứa “linh hoạt” chung chung.

## 18. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chọn Data Vault chỉ vì nhiều bảng nguồn | Tăng bảng/pipeline nhưng không phục vụ nhu cầu lịch sử. | Chứng minh giá trị tích hợp, lineage, thay đổi nguồn trước. |
| Cho người dùng BI tự nối Raw Vault | SQL dài, sai “latest row”, fan-out và KPI không nhất quán. | Cung cấp marts/semantic layer có contract. |
| Chọn star schema nhưng không xác định fact grain | SUM bị nhân hoặc trộn giao dịch khác đơn vị. | Viết grain trước khi vẽ FK; kiểm tra uniqueness. |
| Coi `order_status = PAID` là dòng tiền thực | Bỏ qua partial capture/refund và provider status. | Fact movement theo giao dịch đã xác nhận. |
| Dùng `load_dts` làm ngày nghiệp vụ | Báo cáo sai khi dữ liệu đến muộn. | Tách valid/event time và ingestion time. |
| Băm business key không nhất quán giữa nguồn | Hai thực thể hợp nhất sai hoặc bị tách đôi. | Định nghĩa namespace và canonical encoding có test. |
| Hashdiff thay mọi kiểm tra chất lượng | Dữ liệu rác vẫn được lịch sử hóa. | Validation, lineage, quarantine và đối chiếu nguồn. |
| Không historize relationship đúng nhu cầu | Link cũ bị hiểu là quan hệ đang hiệu lực. | Satellite/record-tracking với mốc và policy. |
| Join fact với nhiều satellite versions | Nhân số dòng và doanh số. | PIT/lookup as-of và grain check. |
| Dùng `current customer segment` cho mọi lịch sử | KPI quá khứ bị restate không công bố. | SCD2 hoặc metric “phân nhóm hiện tại” rõ nghĩa. |
| Không giữ raw đủ để backfill | KPI mới không tái tạo được. | Retention và dữ liệu nguồn đủ theo cam kết. |
| Có nhiều lớp nhưng không có owner | Sai lệch giữa Raw Vault, Business Vault và marts. | Contract, data ownership, monitoring và kiểm thử. |
| Cho rằng append-only không bị yêu cầu xóa | Rủi ro riêng tư/tuân thủ. | Retention, minimization, erasure và giám sát phạm vi bản sao. |

## 19. Bài tập thực hành: chọn kiến trúc cho nền tảng đa kênh

**Bối cảnh:** doanh nghiệp bán sản phẩm qua website, sàn thương mại điện tử và cửa hàng. Dữ liệu đến từ e-commerce, POS, CRM và hai provider thanh toán. ID khách khác nhau giữa các kênh; đơn có nhiều dòng, một số thanh toán nhiều lần và hoàn một phần. CRM có thể đổi phân khúc khách hồi tố. Đội tài chính cần đối soát dòng tiền; đội marketing cần doanh số theo phân khúc tại thời điểm bán và theo phân khúc hiện tại.

### Yêu cầu

1. **Liệt kê nguồn và business keys:** phân biệt `order_id` theo kênh, `customer_id` của CRM/POS, `payment_reference` của provider. Những khóa nào cần namespace, những khóa nào có thể hợp nhất có bằng chứng?
2. **Viết grain:** định nghĩa `fact_order_line`, `fact_payment_movement` và một periodic inventory snapshot nếu cần. Chỉ ra measure nào cộng được theo ngày và measure nào không.
3. **Thiết kế dimensional mart:** nêu `dim_customer` SCD2, `dim_product`, `dim_channel`, `dim_date`, khóa surrogate và unique; mô tả lookup chiều tại thời điểm bán.
4. **Thiết kế Raw Vault tối thiểu:** chọn Hub Order/Customer/Product/Payment, Link tương ứng và Satellite theo nguồn; quy định `load_dts`, `record_source`, business key hashing và hashdiff.
5. **Business Vault:** định nghĩa mapping định danh khách đa nguồn, PIT cho chọn phiên bản lịch sử khi cần và các rule phiên bản hóa cho KPI.
6. **So sánh phương án:** star schema trực tiếp, Raw/Business Vault rồi star, hoặc kết hợp theo miền. Nêu điều kiện và chi phí khiến bạn chọn từng phương án.
7. **Lỗi fan-out:** một đơn có 3 dòng, một khách có 4 phiên bản satellite. Chứng minh tại sao JOIN tất cả phiên bản làm nhân dữ liệu; sửa bằng as-of selection và kiểm tra row count.
8. **Dữ liệu đến muộn:** giao dịch refund ngày 05/11 được nạp ngày 09/11. Nêu ngày nhóm báo cáo và xử lý lại chỉ số đã công bố.
9. **Correction hồi tố:** phân khúc khách của tháng 8 được sửa vào tháng 11. Phân biệt báo cáo “biết lúc tháng 8” và báo cáo được restate theo thông tin mới.
10. **Tái tạo và bảo mật:** nêu những bảng/đường dẫn bị ảnh hưởng khi phải rebuild một mart hoặc khi có yêu cầu xử lý PII.
11. **SQL kiểm chứng:** viết câu truy vấn đếm grain trùng, đối chiếu `CAPTURE - REFUND` theo tiền tệ và kiểm tra dimension as-of không chọn hai phiên bản.
12. **ADR:** chọn một kiến trúc với bằng chứng, SLO, owner, mốc đánh giá lại, khả năng rollback và giới hạn lịch sử được cam kết.

### Bảng kiểm tự đánh giá

| Tiêu chí | Dấu hiệu đạt |
| --- | --- |
| **Nguồn sự thật** | Có bản đồ source→landing→integration→mart; lineage truy được đến nguồn. |
| **Grain** | Một fact row có ý nghĩa rõ, unique theo hạt; JOIN không nhân tiền. |
| **Khóa** | Business key và surrogate/hash key dùng đúng vai trò; không gộp nhầm namespace. |
| **Lịch sử** | SCD2 và Satellite xử lý thay đổi theo đúng mốc thời gian đã định nghĩa. |
| **KPI** | Booked sales khác gross captured/net cash; không cộng chéo loại tiền. |
| **Tích hợp** | CDC/late data, dedup và correction có chính sách. |
| **Hiệu năng** | SLO và chi phí ELT/BI được đo bằng workload tương đồng. |
| **Vận hành** | Rebuild, kiểm chứng, quyền riêng tư và rollback được thiết kế có chủ đích. |

**Kết luận:** mô hình chiều nên được ưu tiên khi mục tiêu chính là **khai thác và hiểu dữ liệu phân tích ở grain rõ ràng**; Data Vault đáng cân nhắc khi thách thức chính là **hợp nhất nhiều nguồn thay đổi, giữ lịch sử và truy nguyên biến đổi**; mô hình kết hợp phù hợp khi doanh nghiệp **cần cả hai** và có đủ năng lực quản trị các lớp. Không chọn theo trào lưu. Hãy bắt đầu từ câu hỏi nghiệp vụ, định nghĩa khóa/quan hệ/thời gian/measure và đối soát bằng phép kiểm chứng thực tế; từ đó chọn cấu trúc vật lý và đường phục vụ truy vấn có chi phí hợp lý.
