# Xây dựng bảng dữ kiện bán hàng cùng các chiều phân tích

## Mục tiêu và kết quả đầu ra

Đây là bài **thực hành tổng hợp** thuộc module **DATABASE_DATA_MODELING**, chương **Thực hành tổng hợp**. Bạn sẽ đi từ yêu cầu báo cáo bán hàng đến mô hình **star schema** có bảng dữ kiện (*fact table*), các bảng chiều (*dimension table*), khóa và ràng buộc, quy trình nạp dữ liệu, truy vấn KPI và kiểm thử đối soát. Mục tiêu không chỉ tạo bảng chạy được mà còn **giải thích vì sao dữ liệu đúng về grain, thời điểm, tiền tệ, lịch sử và quyền truy cập**.

Sau bài học, người học phải có thể:

1. Chuyển yêu cầu báo cáo thành **business process, event, grain và số đo**.
2. Thiết kế fact **một dòng hàng của một đơn đã xác nhận**, không vô tình đếm số dòng như số đơn.
3. Thiết kế dimension **ngày, biến thể sản phẩm, khách hàng/nhóm khách, kênh bán và cửa hàng**, xác định chiều nào cần lịch sử **Slowly Changing Dimension Type 2 (SCD2)**.
4. Phân biệt **surrogate dimension key** với **natural/business key** và **degenerate dimension**.
5. Viết DDL PostgreSQL có PK/FK, CHECK, UNIQUE và chỉ mục phù hợp với phạm vi tenant.
6. Xây dựng luồng **stage → validate → resolve as-of dimension → upsert fact → reconcile → publish**, chịu được retry và sự kiện đến muộn.
7. Trả lời KPI theo ngày/sản phẩm/kênh/cửa hàng mà không nhân tiền sau JOIN; xử lý đúng **nhiều tiền tệ, khách guest, đơn hủy và hoàn tiền**.
8. Phát hiện vấn đề **late-arriving dimensions, dimension Type 1/Type 2, quyền truy cập, PII, chất lượng dữ liệu và hiệu năng**.
9. Hoàn thành bộ bài tập và đối chiếu lời giải; chứng minh thiết kế bằng các kiểm tra có thể chạy lại.

> **Phạm vi kỹ thuật:** ví dụ dùng PostgreSQL, phân tích giao dịch bán hàng bằng số tiền đã xác nhận. Đây **không tự động là doanh thu kế toán, tiền đã capture hay doanh số ròng sau hoàn tiền**. Các KPI ấy cần nguồn, sự kiện và quy tắc riêng. Các tên tiền tệ, mốc thời gian và định nghĩa dùng ở đây là hợp đồng bài tập, không phải quy định phổ quát.

## 1. Đề bài: phòng kinh doanh muốn một bộ báo cáo đáng tin

Một doanh nghiệp có cửa hàng vật lý và bán trực tuyến. Hệ thống OLTP ghi nhận:

- **Đơn hàng (Order)** và **dòng đơn (OrderLine)** được xác nhận.
- Sản phẩm có nhiều **biến thể/SKU**; biến thể có thể đổi tên, nhóm danh mục, thương hiệu.
- Khách đăng ký có **phân khúc** (NEW, RETURNING, VIP...) thay đổi theo thời gian. Một số đơn là khách mua không đăng nhập.
- Các kênh gồm WEB, APP, STORE; cửa hàng có khu vực hoạt động.
- Hệ thanh toán gửi sự kiện capture/refund riêng; một đơn có thể thanh toán nhiều lần.
- Các hệ có thời gian khác nhau: lúc xác nhận đơn, lúc sự kiện được nhận, lúc nạp vào kho.

Người dùng muốn:

1. **Giá trị tiền hàng và số lượng bán** theo ngày, danh mục, kênh và khu vực cửa hàng.
2. **Số đơn duy nhất** và số dòng hàng theo từng chiều.
3. **Phân tích lịch sử**: một sản phẩm chuyển từ danh mục A sang B thì báo cáo tháng cũ vẫn dùng danh mục tại lúc mua.
4. Xem **phân khúc người mua tại thời điểm xác nhận**, không lấy nhãn VIP hiện hành cho mọi đơn cũ.
5. Có thể nạp lại dữ liệu sau sự cố mà **không nhân hai lần một dòng**.
6. Không đưa email, số điện thoại hoặc địa chỉ người nhận vào fact thông dụng.
7. Khi có lỗi ánh xạ dimension, không âm thầm bỏ một phần doanh số.

### 1.1. Chốt định nghĩa KPI trước khi vẽ bảng

| KPI | Định nghĩa của bài thực hành | Grain khi tính |
| --- | --- | --- |
| **confirmed_line_count** | Số dòng đơn đã xác nhận trong phạm vi lọc | Một fact row/dòng |
| **confirmed_unit_quantity** | Tổng quantity trên các dòng | Dòng đơn; chỉ cộng khi cùng đơn vị |
| **confirmed_gross_amount** | Tổng quantity × unit_price đã chốt, trước giảm giá phân bổ | Dòng, nhóm cùng currency |
| **allocated_discount_amount** | Tổng giảm giá đã được phân bổ vào các dòng | Dòng |
| **confirmed_net_items_amount** | Gross trừ giảm giá dòng; chưa gồm thuế/phí trong ví dụ | Dòng, nhóm cùng currency |
| **distinct_confirmed_order_count** | Số order_id khác nhau được xác nhận, không phải COUNT(*) trên fact | Đơn, phải xử lý phân nhóm |
| **distinct_registered_buyer_count** | Số buyer nguồn khác nhau nếu có quyền và cơ sở định danh phù hợp | Buyer, cần quản trị liên kết và lịch sử |

Một **Order** có hai dòng sẽ tạo **hai hàng** trong bảng fact đề xuất, nhưng chỉ đóng góp **một** vào số đơn duy nhất. Do đó không được gọi COUNT(*) trên fact là **order_count**.

### 1.2. Dữ liệu minh họa để đối chiếu

Giả sử đơn **O-1001** của tenant 17, được xác nhận ngày 22/11/2026 theo giờ Việt Nam:

| Dòng | Biến thể | Quantity | Giá một đơn vị | Giảm giá dòng | Gross | Net |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | PHONE-BLACK-128 | 2 | 150.000 VND | 20.000 VND | 300.000 VND | 280.000 VND |
| 2 | CASE-BLACK | 1 | 50.000 VND | 5.000 VND | 50.000 VND | 45.000 VND |
| **Tổng đơn** | | **3** | | **25.000 VND** | **350.000 VND** | **325.000 VND** |

Khi báo cáo **mọi mặt hàng của O-1001**:

- **confirmed_line_count = 2**.
- **confirmed_unit_quantity = 3**, do ví dụ cùng dùng đơn vị chiếc.
- **distinct_confirmed_order_count = 1**.
- **confirmed_net_items_amount = 325.000 VND**.

Nếu JOIN fact với một bảng order có header **325.000 VND** rồi SUM header trên hai dòng, bạn nhận **650.000 VND** — một lỗi về **grain** chứ không phải lỗi PostgreSQL.

## 2. Chọn business process và grain trước khi chọn bảng

Có nhiều quá trình kinh doanh liên quan đến “bán hàng”:

| Quá trình | Sự kiện/ảnh chụp phù hợp | Grain ứng viên |
| --- | --- | --- |
| Xác nhận đơn | OrderConfirmed | Một dòng hàng đã xác nhận |
| Capture tiền | PaymentCaptured | Một giao dịch capture |
| Hoàn tiền | RefundSucceeded | Một dòng refund hoặc refund allocation |
| Xuất kho | StockMovement | Một lần chuyển động tồn kho |
| Giao hàng | ShipmentDelivered | Một shipment/attempt |
| Tồn kho cuối ngày | InventoryEOD | Một biến thể × kho × ngày |
| Trạng thái đơn hiện hành | OrderStateProjection | Một đơn tại thời điểm đọc |

Không chọn chung một bảng fact với cột **amount** để trộn tất cả. Mỗi fact cần **grain** và **định nghĩa số đo** rõ.

### 2.1. Grain chính thức cho bài này

> **Một hàng fact_sales_line_confirmed đại diện cho một dòng hàng (line_no) của một đơn (source_order_id) đã được xác nhận trong một tenant. Dòng này giữ quantity, giá và giảm giá tại thời điểm xác nhận; không phải trạng thái dòng hiện hành.**

Định danh nguồn tự nhiên:

~~~text
(tenant_id, source_order_id, source_line_no)
~~~

Với ví dụ này, một dòng chỉ được xác nhận một lần theo hợp đồng nguồn. Nếu doanh nghiệp cho phép **xác nhận lại đơn và thay đổi line sau mỗi lần**, phải bổ sung **confirmation_id, event_version** hoặc chọn grain sự kiện khác; không âm thầm overwrite một dòng đã xác nhận.

**Phân tích trạng thái hủy/hoàn sau đó** nên sử dụng event/fact riêng hoặc quy tắc điều chỉnh có audit. Không xóa giao dịch đã được xác nhận chỉ vì order hiện ở trạng thái CANCELLED, nếu KPI đang hỏi “đã từng xác nhận”.

### 2.2. Vì sao chọn fact ở dòng đơn?

Vì người dùng cần phân tích theo **sản phẩm/biến thể**. Một Order chứa nhiều SKU; fact cấp đơn không thể tự phân bổ tổng tiền theo SKU nếu chưa có quy tắc phân bổ.

Fact cấp dòng cho phép:

- Phân tích tiền và quantity theo sản phẩm, thời gian, kênh.
- Liên kết dimension về thuộc tính sản phẩm tại thời điểm giao dịch.
- Tính tổng cấp đơn **bằng tổng dòng** khi công thức đã được phân bổ rõ.

Nhưng có đánh đổi:

- **Số đơn duy nhất** là measure **không cộng được tự do** trên các nhóm sản phẩm: một đơn mua hai danh mục sẽ đóng góp vào cả hai danh mục.
- Không SUM **header order amount** khi đã join nhiều dòng.
- Nếu cần đơn có **phí vận chuyển, giảm giá cấp đơn, thuế** thì phải phân bổ theo quy tắc đã thống nhất hoặc tạo các fact/measure riêng. Không tự gán phí cho dòng đầu tiên rồi báo rằng đó là doanh thu theo sản phẩm chuẩn.

## 3. Bus matrix: fact cần những dimension nào?

Một **bus matrix** giúp thấy mỗi business process dùng chiều nào. Trong bài thực hành:

| Business process / fact | Ngày | Sản phẩm | Người mua | Kênh | Cửa hàng | Tiền tệ |
| --- | --- | --- | --- | --- | --- | --- |
| Dòng đơn đã xác nhận | confirmed_date | product SCD2 | buyer SCD2 hoặc guest | sales channel | store nullable cho online | currency_code |
| Capture tiền (mở rộng) | captured_date | Có thể không có nếu capture cấp đơn | payer nếu cần/được phép | payment channel | Không phải luôn có | capture currency |
| Hoàn tiền (mở rộng) | refunded_date | SKU nếu refund phân bổ được | buyer/refund actor | source channel | Theo chính sách | refund currency |
| Tồn cuối ngày (mở rộng) | snapshot_date | product/variant | Không áp dụng | Không áp dụng | warehouse dimension | quantity unit |

Trong bài chính, các dimension:

- **dim_date**: ngày xác nhận theo timezone kinh doanh.
- **dim_product_scd2**: **phiên bản** thuộc tính sản phẩm có hiệu lực khi xác nhận.
- **dim_buyer_scd2**: **phiên bản** phân khúc khách có hiệu lực khi xác nhận, không chứa tên/email.
- **dim_channel**: nguồn kênh bán.
- **dim_store**: nơi bán với khu vực, có thể NULL cho đơn online.
- **currency_code**: degenerate code/đơn vị ở fact; có thể thêm dim_currency khi cần tỷ giá và thuộc tính.

**source_order_id** và **source_line_no** nằm ở fact như **degenerate dimension**: dùng để drill-through/đối soát về nguồn mà không phải tạo dim_order chỉ có một ID. Khóa nguồn **không phải surrogate fact key**.

### 3.1. Star schema đích

~~~text
                   dim_date
                (date_key, date)
                       |
                       v
dim_product_scd2 --> fact_sales_line_confirmed <-- dim_channel
(product_key)           |                   (channel_key)
                        |
dim_buyer_scd2 ---------+------------------- dim_store
(buyer_key)                                 (store_key)
                        |
              source_order_id, line_no
                  degenerate IDs
                        |
          quantity, unit_price, discount,
          gross_amount, net_sales_amount,
          currency_code, confirmed_at
~~~

Mỗi chiều phải có **một hàng được tham chiếu bởi fact** tại thời điểm xác định, tránh một fact row nối ra nhiều version của cùng sản phẩm hoặc buyer.

## 4. Nguyên tắc khóa cho warehouse nhiều tenant

Các ví dụ PostgreSQL dùng:

- **tenant_id**: ranh giới tổ chức và quyền.
- **product_key, buyer_key, channel_key, store_key**: **surrogate dimension keys** cấp trong warehouse.
- **source_variant_id, source_buyer_ref, channel_code, store_code**: **natural/business references** đến hệ nguồn.
- **source_order_id, source_line_no**: ID truy vết fact đến sự kiện nguồn.
- **confirmed_date_key**: khóa số nguyên dạng YYYYMMDD trong dim_date để nhóm theo lịch, không thay thế timestamp đầy đủ.

Khóa dạng **BIGINT GENERATED ALWAYS AS IDENTITY** trong bài là mã kỹ thuật do PostgreSQL cấp; không tự suy nó là ID nghiệp vụ hoặc ID được phép phát qua API. Với các chiều có lịch sử, **một natural ID có nhiều surrogate keys**, mỗi key là một phiên bản.

**Không JOIN fact theo natural product ID vào mọi dòng SCD2 nếu thiếu điều kiện thời gian**, vì có thể nhân doanh thu khi sản phẩm có hai phiên bản.

Ở các bảng tenant-scoped, bài dùng composite FK **(tenant_id, dimension_key)** để ngăn fact của tenant A trỏ vào dimension của tenant B. Điều này chỉ bảo vệ tham chiếu; ứng dụng và vai trò đọc vẫn cần **tenant authorization** riêng.

## 5. DDL phần 1 — Dimension ngày

### 5.1. Chốt quy ước ngày báo cáo

Bài sử dụng **ngày kinh doanh Việt Nam, timezone Asia/Ho_Chi_Minh**, lấy từ **confirmed_at TIMESTAMPTZ** do Sales xác nhận. Bản ghi được nạp vào kho hôm sau vẫn thuộc ngày xác nhận, không theo loaded_at.

Với tổ chức bán xuyên nhiều múi giờ, phải xác định ngày theo **store/business unit** và thiết kế dimension/reporting phù hợp; không tự ép tất cả vào timezone Việt Nam khi không có quyết định như trong bài.

### 5.2. Tạo dim_date

~~~sql
CREATE SCHEMA mart;

CREATE TABLE mart.dim_date (
    date_key INTEGER NOT NULL,
    calendar_date DATE NOT NULL,
    calendar_year INTEGER NOT NULL,
    calendar_month INTEGER NOT NULL,
    calendar_quarter INTEGER NOT NULL,
    iso_year INTEGER NOT NULL,
    iso_week INTEGER NOT NULL,
    iso_day_of_week INTEGER NOT NULL,
    month_start_date DATE NOT NULL,

    CONSTRAINT pk_dim_date PRIMARY KEY (date_key),
    CONSTRAINT uq_dim_date_calendar_date UNIQUE (calendar_date),
    CONSTRAINT ck_dim_date_month
        CHECK (calendar_month BETWEEN 1 AND 12),
    CONSTRAINT ck_dim_date_iso_day
        CHECK (iso_day_of_week BETWEEN 1 AND 7)
);
~~~

Nạp lịch ví dụ 2024–2029 bằng PostgreSQL:

~~~sql
INSERT INTO mart.dim_date (
    date_key, calendar_date, calendar_year,
    calendar_month, calendar_quarter,
    iso_year, iso_week, iso_day_of_week, month_start_date
)
SELECT
    to_char(g.d::DATE, 'YYYYMMDD')::INTEGER,
    g.d::DATE,
    EXTRACT(YEAR FROM g.d)::INTEGER,
    EXTRACT(MONTH FROM g.d)::INTEGER,
    EXTRACT(QUARTER FROM g.d)::INTEGER,
    EXTRACT(ISOYEAR FROM g.d)::INTEGER,
    EXTRACT(WEEK FROM g.d)::INTEGER,
    EXTRACT(ISODOW FROM g.d)::INTEGER,
    date_trunc('month', g.d)::DATE
FROM generate_series(
    '2024-01-01'::TIMESTAMP,
    '2029-12-31'::TIMESTAMP,
    INTERVAL '1 day'
) AS g(d)
ON CONFLICT (date_key) DO NOTHING;
~~~

Ở PostgreSQL, **WEEK** tuân cách đánh số tuần ISO và **ISOYEAR** có thể khác calendar_year ở đầu/cuối năm. Vì vậy cột **iso_week** nên đi với **iso_year**, không tự nhóm chỉ theo calendar_year.

Nếu dữ liệu thực có ngày nằm ngoài dải được nạp, ETL phải báo **missing date dimension**, mở rộng dim_date trước khi publish; không gán bừa vào một ngày bất kỳ.

## 6. DDL phần 2 — Dimension sản phẩm SCD Type 2

Yêu cầu quan trọng: sản phẩm **PHONE-BLACK-128** từng thuộc danh mục **ELECTRONICS**, sau đó chuyển sang **SMARTPHONES**. Báo cáo lịch sử phải giữ thuộc tính **có hiệu lực lúc giao dịch**.

### 6.1. Một surrogate key cho mỗi phiên bản

~~~sql
CREATE TABLE mart.dim_product_scd2 (
    tenant_id BIGINT NOT NULL,
    product_key BIGINT GENERATED ALWAYS AS IDENTITY,
    source_variant_id UUID NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category_code TEXT NOT NULL,
    brand_code TEXT,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL,

    CONSTRAINT pk_dim_product_scd2
        PRIMARY KEY (tenant_id, product_key),
    CONSTRAINT uq_dim_product_natural_version
        UNIQUE (tenant_id, source_variant_id, valid_from),
    CONSTRAINT ck_dim_product_effective_range
        CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT ck_dim_product_current_range
        CHECK (is_current = (valid_to IS NULL))
);

CREATE UNIQUE INDEX uq_dim_product_current_natural
ON mart.dim_product_scd2 (tenant_id, source_variant_id)
WHERE valid_to IS NULL;

CREATE INDEX ix_dim_product_resolve_asof
ON mart.dim_product_scd2 (
    tenant_id, source_variant_id, valid_from, valid_to
);
~~~

**Bất biến định nghĩa:**

- Hai bản ghi khác nhau của cùng source_variant_id là **hai phiên bản dimension**, không phải hai SKU.
- Khoảng hiệu lực là **[valid_from, valid_to)**: từ bao gồm, đến loại trừ.
- Hàng hiện hành có valid_to NULL và is_current TRUE.
- Unique partial index chặn **hai hàng current** cùng natural ID trong một tenant.

**Giới hạn:** CHECK và unique current **không tự ngăn hai phiên bản lịch sử chồng lấn**; ví dụ hai hàng [01/01, 01/06) và [01/04, 01/05). Hệ có thể dùng **exclusion constraint với range và phù hợp kiểu index/extension**, hoặc một quy trình SCD2 được serial hóa/kiểm chứng để ngăn overlap. Không nói “đã có SCD2 đúng” chỉ vì thêm is_current.

### 6.2. Ví dụ phiên bản theo thời gian

| product_key | source_variant_id | category_code | valid_from | valid_to |
| ---: | --- | --- | --- | --- |
| 9001 | V-101 | ELECTRONICS | 01/01/2026 | 01/09/2026 |
| 9120 | V-101 | SMARTPHONES | 01/09/2026 | NULL |

Đây là ID minh họa; DDL dùng UUID nguồn và BIGINT surrogate. Một fact xác nhận **ngày 20/08/2026** cần trỏ **9001**. Fact ngày **22/11/2026** cần trỏ **9120**. Khi cùng một biến thể đổi category, **không cập nhật product_key của các fact tháng 8 sang 9120** nếu metric cần thuộc tính lịch sử.

### 6.3. Quy trình cập nhật Type 2

Khi source báo một thay đổi thuộc tính **được theo dõi Type 2** có hiệu lực từ **T**:

1. Xác thực source ID, tenant, thứ tự/version và mốc hiệu lực T.
2. Chốt bản hiện hành cũ với **valid_to = T**, **is_current = FALSE**, nếu T lớn hơn valid_from.
3. Thêm bản mới **valid_from = T**, **valid_to = NULL**, **is_current = TRUE**.
4. Thực hiện trong transaction, khóa hoặc serial hóa thao tác trên cùng natural ID.
5. Kiểm tra không chồng khoảng và chỉ có một current row.
6. Phát sự kiện dimension-ready/checkpoint để ETL fact biết phiên bản áp dụng.

Nếu thay đổi đến muộn với **effective time** nằm **giữa hai version đã tồn tại**, không thể chỉ đóng current và thêm hàng cuối. Phải **chèn/sửa các khoảng lịch sử**, xác minh tất cả khoảng lân cận, và **đánh giá lại fact** trong khoảng bị ảnh hưởng theo chính sách restatement.

**Type 1 hay Type 2 phải chọn theo thuộc tính**. Sửa một lỗi chính tả trong product_name có thể dùng Type 1 nếu nghiệp vụ muốn lịch sử được sửa; thay đổi category để phân tích lịch sử cần Type 2. Không tự áp SCD2 cho mọi trường mà không có lý do và chi phí.

## 7. DDL phần 3 — Dimension người mua có lịch sử, giới hạn định danh

Để phân tích **phân khúc tại thời điểm mua**, bài dùng **dim_buyer_scd2** với source_buyer_ref là mã giả danh có phạm vi sử dụng; dimension **không chứa họ tên, email, số điện thoại hoặc địa chỉ**.

~~~sql
CREATE TABLE mart.dim_buyer_scd2 (
    tenant_id BIGINT NOT NULL,
    buyer_key BIGINT GENERATED ALWAYS AS IDENTITY,
    source_buyer_ref UUID NOT NULL,
    buyer_segment_code TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL,

    CONSTRAINT pk_dim_buyer_scd2
        PRIMARY KEY (tenant_id, buyer_key),
    CONSTRAINT uq_dim_buyer_natural_version
        UNIQUE (tenant_id, source_buyer_ref, valid_from),
    CONSTRAINT ck_dim_buyer_effective_range
        CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT ck_dim_buyer_current_range
        CHECK (is_current = (valid_to IS NULL))
);

CREATE UNIQUE INDEX uq_dim_buyer_current_natural
ON mart.dim_buyer_scd2 (tenant_id, source_buyer_ref)
WHERE valid_to IS NULL;

CREATE INDEX ix_dim_buyer_resolve_asof
ON mart.dim_buyer_scd2 (
    tenant_id, source_buyer_ref, valid_from, valid_to
);
~~~

**Lưu ý về riêng tư:** UUID giả danh vẫn có thể giúp liên kết nhiều đơn của một cá nhân. Dữ liệu này **không tự trở thành ẩn danh**; cần kiểm soát quyền, mục đích, retention và cách ánh xạ danh tính thật ở hệ nguồn. Một báo cáo tổng hợp theo phân khúc thường chỉ cần buyer_segment_code và số liệu, không cần xuất source_buyer_ref.

Nếu người mua chuyển **NEW → VIP** vào tháng 9, fact tháng 8 có buyer_key phiên bản **NEW**, fact tháng 11 có buyer_key **VIP**. Khi bạn tính **COUNT(DISTINCT buyer_key)** xuyên nhiều tháng, cùng một người có thể có **hai surrogate keys**; đó là **số phiên bản người mua**, không phải số người duy nhất.

Muốn tính distinct buyers theo định nghĩa nhất quán cần dùng **natural pseudonymous reference ở quyền thích hợp** hoặc một bảng cầu nối định danh được quản lý. Không tùy tiện JOIN danh tính thật vào báo cáo công cộng.

### 7.1. Đơn khách vãng lai và unmatched buyer

Bài phân biệt:

- **GUEST**: nguồn cho biết không có tài khoản được định danh; buyer_key có thể NULL **có chủ đích**.
- **REGISTERED**: có source_buyer_ref; phải ánh xạ được một **buyer_key tại thời điểm xác nhận** trước khi đưa fact vào dataset chính.
- **PENDING/UNMATCHED**: thông tin nguồn đã có nhưng chiều chưa nạp. Đây **không phải GUEST**; đưa sang hàng chờ/quarantine và xử lý late-arriving dimension.

Có thể dùng một **unknown dimension row** nếu tổ chức có quy tắc, nhưng phải phân biệt **thật sự không biết**, **chưa hội tụ** và **không áp dụng**. Trong bài thực hành dùng NULL cho guest có chủ đích và **chặn record REGISTERED thiếu ánh xạ** trước publish.

## 8. DDL phần 4 — Kênh bán và cửa hàng

Kênh bán có natural ID **channel_code**, ví dụ WEB, APP, STORE; cửa hàng có **store_code**. Hai dimension dưới đây dùng **Type 1** cho mục tiêu bài tập, nghĩa là thông tin được sửa trong dimension có thể cập nhật cách nhóm **lịch sử**. Nếu đổi vùng cửa hàng mà cần báo cáo theo vùng **tại thời điểm bán**, dim_store cũng phải Type 2 hoặc lưu thuộc tính snapshot trong fact theo hợp đồng.

~~~sql
CREATE TABLE mart.dim_channel (
    tenant_id BIGINT NOT NULL,
    channel_key BIGINT GENERATED ALWAYS AS IDENTITY,
    channel_code TEXT NOT NULL,
    channel_name TEXT NOT NULL,

    CONSTRAINT pk_dim_channel
        PRIMARY KEY (tenant_id, channel_key),
    CONSTRAINT uq_dim_channel_code
        UNIQUE (tenant_id, channel_code)
);

CREATE TABLE mart.dim_store (
    tenant_id BIGINT NOT NULL,
    store_key BIGINT GENERATED ALWAYS AS IDENTITY,
    store_code TEXT NOT NULL,
    store_name TEXT NOT NULL,
    region_code TEXT NOT NULL,

    CONSTRAINT pk_dim_store
        PRIMARY KEY (tenant_id, store_key),
    CONSTRAINT uq_dim_store_code
        UNIQUE (tenant_id, store_code)
);
~~~

**Sự phân biệt quan trọng:**

- **channel_code = STORE** không thay thế **store_code**. Một kênh có nhiều cửa hàng.
- Đơn **WEB/APP** có thể không có store_key nếu doanh nghiệp định nghĩa online không gắn cửa hàng.
- Đơn **STORE** phải có store_code hợp lệ trong staging theo luật nguồn; FK nullable ở fact không tự kiểm tra điều kiện có cửa hàng khi channel STORE, nên validator phải làm việc đó.
- **region_code** đang là Type 1; nếu cửa hàng chuyển từ miền Bắc sang miền Nam, báo cáo lịch sử theo khu vực có thể thay đổi. Cần quyết định trước khi dùng nó cho KPI lịch sử.

## 9. DDL phần 5 — Fact dòng đơn đã xác nhận

### 9.1. Định nghĩa fact trước khi viết SQL

| Thành phần | Tên | Ý nghĩa |
| --- | --- | --- |
| Surrogate row key | sales_line_key | ID kỹ thuật của fact row |
| Degenerate business ID | source_order_id, source_line_no | Nhận diện dòng của đơn ở nguồn |
| Dimension time | confirmed_date_key | Ngày kinh doanh Việt Nam |
| Dimension product | product_key | Phiên bản SCD2 tại confirmed_at |
| Dimension buyer | buyer_key | Phiên bản SCD2 hoặc NULL cho GUEST |
| Dimension channel | channel_key | Kênh tại lúc xác nhận |
| Dimension store | store_key | Cửa hàng nếu có |
| Event time | confirmed_at | Timestamp nguồn, giữ đủ độ chính xác |
| Monetary unit | currency_code | Tiền tệ dòng; không cộng khác currency |
| Additive measure | quantity | Số đơn vị, ví dụ này chỉ bán theo chiếc |
| Transactional measures | unit_price_amount, allocated_discount_amount | Giá và giảm giá tại xác nhận |
| Derived measures | gross_sales_amount, net_sales_amount | Dẫn xuất từ quantity, giá, discount |
| Lineage | source_event_id, source_event_version, loaded_at | Idempotency, đối soát và replay |

### 9.2. DDL fact có foreign key và bất biến

~~~sql
CREATE TABLE mart.fact_sales_line_confirmed (
    tenant_id BIGINT NOT NULL,
    sales_line_key BIGINT GENERATED ALWAYS AS IDENTITY,

    source_order_id UUID NOT NULL,
    source_line_no INTEGER NOT NULL,
    source_event_id UUID NOT NULL,
    source_event_version BIGINT NOT NULL,

    confirmed_at TIMESTAMPTZ NOT NULL,
    confirmed_date_key INTEGER NOT NULL,
    product_key BIGINT NOT NULL,
    buyer_key BIGINT,
    buyer_kind_code TEXT NOT NULL,
    channel_key BIGINT NOT NULL,
    store_key BIGINT,

    currency_code CHAR(3) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_amount NUMERIC(18, 2) NOT NULL,
    allocated_discount_amount NUMERIC(18, 2) NOT NULL,

    gross_sales_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (
            quantity * unit_price_amount
        ) STORED,
    net_sales_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (
            quantity * unit_price_amount
            - allocated_discount_amount
        ) STORED,

    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_fact_sales_line_confirmed
        PRIMARY KEY (tenant_id, sales_line_key),
    CONSTRAINT uq_fact_sales_source_line
        UNIQUE (tenant_id, source_order_id, source_line_no),

    CONSTRAINT fk_fact_sales_date
        FOREIGN KEY (confirmed_date_key)
        REFERENCES mart.dim_date(date_key),
    CONSTRAINT fk_fact_sales_product
        FOREIGN KEY (tenant_id, product_key)
        REFERENCES mart.dim_product_scd2(tenant_id, product_key),
    CONSTRAINT fk_fact_sales_buyer
        FOREIGN KEY (tenant_id, buyer_key)
        REFERENCES mart.dim_buyer_scd2(tenant_id, buyer_key),
    CONSTRAINT fk_fact_sales_channel
        FOREIGN KEY (tenant_id, channel_key)
        REFERENCES mart.dim_channel(tenant_id, channel_key),
    CONSTRAINT fk_fact_sales_store
        FOREIGN KEY (tenant_id, store_key)
        REFERENCES mart.dim_store(tenant_id, store_key),

    CONSTRAINT ck_fact_sales_line_no
        CHECK (source_line_no > 0),
    CONSTRAINT ck_fact_sales_version
        CHECK (source_event_version > 0),
    CONSTRAINT ck_fact_sales_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_fact_sales_price
        CHECK (unit_price_amount >= 0),
    CONSTRAINT ck_fact_sales_discount
        CHECK (
            allocated_discount_amount >= 0
            AND allocated_discount_amount
                <= quantity * unit_price_amount
        ),
    CONSTRAINT ck_fact_sales_buyer_kind
        CHECK (
            (buyer_kind_code = 'GUEST' AND buyer_key IS NULL)
            OR
            (buyer_kind_code = 'REGISTERED' AND buyer_key IS NOT NULL)
        )
);
~~~

**Điểm cần nhận ra:**

- Fact có **PK kỹ thuật** và **UNIQUE business grain** để retry không tạo hai hàng cho một dòng nguồn.
- Khóa product/buyer là **version key** đã giải theo thời điểm, không chỉ là mã biến thể hoặc buyer hiện tại.
- Composite FK giữ đúng tenant. Với buyer_key/store_key NULL, PostgreSQL dùng quy tắc FK nullable thông thường; chỉ cho phép buyer null với **GUEST** qua CHECK.
- Gross/net là **generated stored columns** để hai số đo không lệch khỏi quantity, price và discount trong cùng row.
- **source_event_version** phục vụ phát hiện ghi lùi. Nó phải có hợp đồng nguồn về thứ tự cho mỗi dòng; eventId một mình không diễn đạt version.
- currency_code có trong fact để không cộng nhầm VND với USD. Hệ thực cần validation currency hợp lệ, precision và rounding theo từng loại tiền.

Đây là fact **giao dịch đã xác nhận**, không phải bảng giao dịch thanh toán. Không gắn **payment_status hiện hành** lên dòng fact rồi làm nó thay đổi mỗi khi capture/refund có event mới.

### 9.3. Chỉ mục theo truy vấn thực tế

~~~sql
CREATE INDEX ix_fact_sales_tenant_date
ON mart.fact_sales_line_confirmed
   (tenant_id, confirmed_date_key);

CREATE INDEX ix_fact_sales_tenant_product_date
ON mart.fact_sales_line_confirmed
   (tenant_id, product_key, confirmed_date_key);

CREATE INDEX ix_fact_sales_tenant_channel_date
ON mart.fact_sales_line_confirmed
   (tenant_id, channel_key, confirmed_date_key);

CREATE INDEX ix_fact_sales_tenant_buyer
ON mart.fact_sales_line_confirmed
   (tenant_id, buyer_key);
~~~

Không cần giữ mọi index nếu workload không dùng. Mỗi index tăng chi phí nạp/update, dung lượng và bảo trì. Khóa ngoại ở bảng fact **không tự có index tối ưu cho mọi truy vấn**; chọn index dựa trên predicate, selectivity và **EXPLAIN (ANALYZE, BUFFERS)**.

### 9.4. Có nên partition theo ngày/tháng?

Với hàng tỷ dòng, partition theo confirmed_date hoặc confirmed_at có thể hỗ trợ pruning và retention. Nhưng có một quyết định PostgreSQL quan trọng: **unique/primary key trên partitioned table thường phải bao gồm partition key** khi muốn bảo đảm uniqueness trực tiếp ở bảng phân vùng. PK/UNIQUE mẫu ở trên dùng grain không chứa date partition key.

Không được thêm PARTITION BY RANGE một cách máy móc rồi cho rằng UNIQUE(tenant_id, source_order_id, line_no) vẫn được bảo vệ toàn cục. Cần thiết kế lại khóa/partition, bảng registry dedupe hoặc hợp đồng bảo đảm một order chỉ thuộc một partition, và kiểm thử tình huống cập nhật ngày/đến muộn. Bài chính dùng **bảng thường** để tập trung vào đúng grain và ràng buộc.

## 10. Chuỗi dữ liệu đầu vào và các bất biến của ETL

Đường đi đề xuất:

~~~text
Sales source / OrderConfirmed event
                |
                v
  durable inbox / raw landing (event id, version)
                |
                v
      staging đã parse/validate
                |
        +-------+-------+
        |               |
        v               v
   dim product       dim buyer
      SCD2              SCD2
        |               |
        +-------+-------+
                |
         resolve as-of
                |
          +-----+-----+
          |           |
          v           v
    rows hợp lệ   quarantine + lý do
          |
          v
       MERGE/UPSERT fact
          |
          v
 reconcile + publish + monitor
~~~

**Không tính OrderConfirmed chỉ từ OrderUpdated của CDC mà chưa xác định nguồn có thẩm quyền.** Một event nạp lại có thể gửi trùng; một Order có nhiều line dùng chung eventId; một event có thể đến muộn.

### 10.1. Input contract tối thiểu

Một bản ghi staging đã được chuẩn hóa có:

~~~text
tenant_id
source_order_id, source_line_no
source_event_id, source_event_version
source_variant_id
source_buyer_ref (nullable với GUEST)
buyer_kind_code ('GUEST' hoặc 'REGISTERED')
channel_code
store_code (nullable cho online theo luật)
confirmed_at
currency_code
quantity
unit_price_amount
allocated_discount_amount
~~~

**Các điều kiện tiền xử lý:**

- Một dòng source có **quantity > 0**.
- Giá không âm và discount nằm trong [0, quantity × price].
- source_order_id, source_line_no và version có ID/giới hạn hợp lệ.
- Event type thực sự là **OrderConfirmed** hoặc bản sửa có hợp đồng rõ.
- buyer_kind_code phù hợp với sự hiện diện của source_buyer_ref.
- Không còn dòng trùng bất thường trong cùng batch; phải phân giải version và nguồn chuẩn trước.
- Cùng Order phải thống nhất currency_code, confirmed_at, channel theo hợp đồng nếu đây là thuộc tính cấp đơn.
- Loại/test order và currency được xử lý theo chính sách KPI; không tự bỏ ngầm.
- Thời điểm xác nhận phải được xác minh theo timezone/clock của hệ nguồn và chuyển thành TIMESTAMPTZ chuẩn.

### 10.2. Định nghĩa staging đã qua chuẩn hóa

~~~sql
CREATE TABLE mart.stage_confirmed_order_lines (
    tenant_id BIGINT NOT NULL,
    source_order_id UUID NOT NULL,
    source_line_no INTEGER NOT NULL,
    source_event_id UUID NOT NULL,
    source_event_version BIGINT NOT NULL,
    source_variant_id UUID NOT NULL,
    source_buyer_ref UUID,
    buyer_kind_code TEXT NOT NULL,
    channel_code TEXT NOT NULL,
    store_code TEXT,
    confirmed_at TIMESTAMPTZ NOT NULL,
    currency_code CHAR(3) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_amount NUMERIC(18, 2) NOT NULL,
    allocated_discount_amount NUMERIC(18, 2) NOT NULL,

    CONSTRAINT pk_stage_confirmed_line
        PRIMARY KEY (tenant_id, source_order_id, source_line_no),
    CONSTRAINT ck_stage_source_line CHECK (source_line_no > 0),
    CONSTRAINT ck_stage_version CHECK (source_event_version > 0),
    CONSTRAINT ck_stage_quantity CHECK (quantity > 0),
    CONSTRAINT ck_stage_price CHECK (unit_price_amount >= 0),
    CONSTRAINT ck_stage_discount
        CHECK (
            allocated_discount_amount >= 0
            AND allocated_discount_amount
                <= quantity * unit_price_amount
        ),
    CONSTRAINT ck_stage_buyer_presence
        CHECK (
            (buyer_kind_code = 'GUEST'
                AND source_buyer_ref IS NULL)
            OR
            (buyer_kind_code = 'REGISTERED'
                AND source_buyer_ref IS NOT NULL)
        )
);
~~~

**Đây là bảng staging snapshot của phiên bản mới nhất đã được chấp thuận cho mỗi dòng**, không phải raw event log. Các event cũ/trùng phải được quản lý tại ingestion inbox với điều kiện **version mới hơn**, rồi mới đưa vào staging. Một INSERT/UPDATE bình thường vào staging theo natural key không tự bảo vệ chống late event nếu không có logic version trước đó.

Nếu business cho phép **một đơn chưa có source_order_id ổn định** hoặc dòng được đánh số lại sau xác nhận, hợp đồng grain của staging và fact phải sửa; không “sửa” bằng cách lấy ROW_NUMBER() của batch rồi coi đó là line ID vĩnh viễn.

## 11. Thực hành nạp dữ liệu mẫu để kiểm tra bằng tay

Các mã **O-1001, PHONE-BLACK-128** ở phần 1 là nhãn dễ đọc trong tình huống. Trong DDL vật lý, **source_order_id và source_variant_id là UUID**. Đoạn dữ liệu dưới đây dùng UUID tổng hợp có cấu trúc để minh họa; **không dùng các UUID cố định này làm ID sản xuất**.

### 11.1. Nạp các dimension nguồn cần dùng

~~~sql
INSERT INTO mart.dim_channel (
    tenant_id, channel_code, channel_name
)
VALUES
    (17, 'WEB', 'Website'),
    (17, 'STORE', 'Cua hang');

INSERT INTO mart.dim_store (
    tenant_id, store_code, store_name, region_code
)
VALUES
    (17, 'HCM-01', 'Cua hang HCM 01', 'HCM');

INSERT INTO mart.dim_product_scd2 (
    tenant_id, source_variant_id, sku, product_name,
    category_code, brand_code, valid_from, valid_to, is_current
)
VALUES
    (
        17, '10000000-0000-4000-8000-000000000101'::UUID,
        'PHONE-BLACK-128', 'Dien thoai 128 GB',
        'SMARTPHONES', 'BRAND-A',
        '2026-01-01T00:00:00Z'::TIMESTAMPTZ, NULL, TRUE
    ),
    (
        17, '10000000-0000-4000-8000-000000000102'::UUID,
        'CASE-BLACK', 'Op lung mau den',
        'ACCESSORIES', 'BRAND-B',
        '2026-01-01T00:00:00Z'::TIMESTAMPTZ, NULL, TRUE
    );

INSERT INTO mart.dim_buyer_scd2 (
    tenant_id, source_buyer_ref, buyer_segment_code,
    valid_from, valid_to, is_current
)
VALUES (
    17,
    '20000000-0000-4000-8000-000000000201'::UUID,
    'NEW',
    '2026-01-01T00:00:00Z'::TIMESTAMPTZ,
    NULL, TRUE
);
~~~

Những INSERT này dành cho **database học tập trống**; nếu chạy lại trên database đã có dữ liệu, cần cơ chế idempotent dimension load và quản lý Type 2, không tự chèn phiên bản mới trùng interval.

### 11.2. Nạp ba dòng staging

~~~sql
INSERT INTO mart.stage_confirmed_order_lines (
    tenant_id, source_order_id, source_line_no,
    source_event_id, source_event_version,
    source_variant_id, source_buyer_ref, buyer_kind_code,
    channel_code, store_code, confirmed_at,
    currency_code, quantity, unit_price_amount,
    allocated_discount_amount
)
VALUES
    (
        17,
        '00000000-0000-4000-8000-000000001001'::UUID, 1,
        '30000000-0000-4000-8000-000000000301'::UUID, 1,
        '10000000-0000-4000-8000-000000000101'::UUID,
        '20000000-0000-4000-8000-000000000201'::UUID,
        'REGISTERED', 'WEB', NULL,
        '2026-11-22T03:00:00Z'::TIMESTAMPTZ,
        'VND', 2, 150000.00, 20000.00
    ),
    (
        17,
        '00000000-0000-4000-8000-000000001001'::UUID, 2,
        '30000000-0000-4000-8000-000000000301'::UUID, 1,
        '10000000-0000-4000-8000-000000000102'::UUID,
        '20000000-0000-4000-8000-000000000201'::UUID,
        'REGISTERED', 'WEB', NULL,
        '2026-11-22T03:00:00Z'::TIMESTAMPTZ,
        'VND', 1, 50000.00, 5000.00
    ),
    (
        17,
        '00000000-0000-4000-8000-000000001002'::UUID, 1,
        '30000000-0000-4000-8000-000000000302'::UUID, 1,
        '10000000-0000-4000-8000-000000000101'::UUID,
        NULL, 'GUEST', 'STORE', 'HCM-01',
        '2026-11-23T02:00:00Z'::TIMESTAMPTZ,
        'VND', 1, 150000.00, 0.00
    );
~~~

Kiểm tra nhanh staging:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS line_count,
    COUNT(DISTINCT source_order_id) AS order_count,
    SUM(quantity) AS unit_quantity,
    SUM(quantity * unit_price_amount
        - allocated_discount_amount) AS net_amount,
    currency_code
FROM mart.stage_confirmed_order_lines
GROUP BY tenant_id, currency_code;
~~~

Kết quả mong đợi với dữ liệu mẫu:

| tenant_id | line_count | order_count | unit_quantity | net_amount | currency_code |
| ---: | ---: | ---: | ---: | ---: | --- |
| 17 | 3 | 2 | 4 | 475000.00 | VND |

**Đừng chỉnh fact để “khớp” bảng mong đợi nếu staging hoặc source sai.** Lỗi ở source phải được điều tra, có quyết định sửa và audit phù hợp.

## 12. Resolve dimension theo thời điểm: điều kiện nhập fact quan trọng nhất

Để chọn đúng product_key, không JOIN theo **is_current = TRUE**. Phải chọn phiên bản dimension có hiệu lực ở **confirmed_at**:

~~~sql
s.confirmed_at >= d.valid_from
AND (
    d.valid_to IS NULL
    OR s.confirmed_at < d.valid_to
)
~~~

Đây là điều kiện **as-of join**. Nó áp dụng tương tự cho dim_buyer_scd2.

### 12.1. Gate: mỗi dòng phải khớp đúng một phiên bản bắt buộc

Trước nạp fact, xác minh số match:

~~~sql
WITH match_counts AS (
    SELECT
        s.tenant_id,
        s.source_order_id,
        s.source_line_no,
        s.buyer_kind_code,
        s.channel_code,
        s.store_code,

        (
            SELECT COUNT(*)
            FROM mart.dim_date AS d
            WHERE d.calendar_date =
              (s.confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        ) AS date_matches,

        (
            SELECT COUNT(*)
            FROM mart.dim_product_scd2 AS p
            WHERE p.tenant_id = s.tenant_id
              AND p.source_variant_id = s.source_variant_id
              AND s.confirmed_at >= p.valid_from
              AND (p.valid_to IS NULL
                   OR s.confirmed_at < p.valid_to)
        ) AS product_matches,

        (
            SELECT COUNT(*)
            FROM mart.dim_buyer_scd2 AS b
            WHERE b.tenant_id = s.tenant_id
              AND b.source_buyer_ref = s.source_buyer_ref
              AND s.confirmed_at >= b.valid_from
              AND (b.valid_to IS NULL
                   OR s.confirmed_at < b.valid_to)
        ) AS buyer_matches,

        (
            SELECT COUNT(*)
            FROM mart.dim_channel AS c
            WHERE c.tenant_id = s.tenant_id
              AND c.channel_code = s.channel_code
        ) AS channel_matches,

        (
            SELECT COUNT(*)
            FROM mart.dim_store AS st
            WHERE st.tenant_id = s.tenant_id
              AND st.store_code = s.store_code
        ) AS store_matches

    FROM mart.stage_confirmed_order_lines AS s
)
SELECT *
FROM match_counts
WHERE date_matches <> 1
   OR product_matches <> 1
   OR channel_matches <> 1
   OR (
       buyer_kind_code = 'REGISTERED' AND buyer_matches <> 1
   )
   OR (
       buyer_kind_code = 'GUEST' AND buyer_matches <> 0
   )
   OR (
       store_code IS NOT NULL AND store_matches <> 1
   )
   OR (
       channel_code = 'STORE' AND store_code IS NULL
   );
~~~

**Kết quả mong đợi: không có hàng** nếu dimension đã nạp đúng và các quy tắc dữ liệu mẫu được đáp ứng.

Các loại lỗi và cách xử lý:

| Gate thất bại | Ý nghĩa | Quyết định cần làm |
| --- | --- | --- |
| date_matches = 0 | Chưa có ngày trong dim_date | Mở rộng lịch, không tự thay ngày |
| product_matches = 0 | Product đến muộn hoặc khoảng SCD thiếu | Nạp/sửa dimension theo nguồn rồi thử lại |
| product_matches nhiều hơn 1 | Khoảng Type 2 chồng nhau | Sửa dimension; không chọn MIN(product_key) bừa |
| buyer_matches = 0 ở REGISTERED | Buyer dimension chưa sẵn hoặc ID sai | Quarantine, xác minh, nạp dimension |
| buyer_matches nhiều hơn 1 | Buyer SCD2 overlap | Sửa effective ranges |
| channel_matches = 0 | Kênh chưa được định nghĩa | Metadata/owner phê duyệt hoặc chặn |
| store_matches = 0 khi store_code có giá trị | Cửa hàng chưa được ánh xạ | Nạp dim_store hoặc sửa nguồn |
| channel STORE nhưng store_code NULL | Thiếu thông tin cửa hàng bắt buộc theo bài | Giữ bản ghi lỗi, không gán nhầm vùng |
| GUEST có buyer mapping | Nguồn xác định guest không nhất quán | Điều tra bản ghi hoặc rule |

**Không được thêm điều kiện WHERE chỉ để bỏ các hàng không khớp rồi báo job thành công.** Gate phải chặn publish hoặc đưa các bản ghi lỗi vào quarantine với lý do, thời điểm và owner rõ ràng. Những hàng đạt gate mới được nạp. Khi hệ vận hành thật, thực hiện gate và load trên một **snapshot/transaction kiểm soát thay đổi đồng thời**, tránh dimension bị cập nhật giữa hai bước làm kết quả không nhất quán.

### 12.2. Late-arriving dimension khác guest thực sự

Nếu Sales đã xác nhận đơn nhưng buyer segment chưa vào warehouse, đây là **late-arriving dimension**. Không tự đổi buyer_kind từ REGISTERED thành GUEST để bỏ lỗi. Tùy SLA có thể:

- **Giữ fact trong quarantine** đến khi dimension xuất hiện, phù hợp bài thực hành.
- Dùng **inferred/unknown member** với source reference, ghi rõ trạng thái unresolved, sau đó sửa theo chính sách.
- Cho báo cáo tạm thời với **unknown segment** và cảnh báo, nếu nghiệp vụ chấp nhận độ trễ và có cơ chế bù chính xác.

Điều quan trọng là giữ **cùng grain** và **có đường sửa**, không làm doanh số biến mất vì thiếu thuộc tính phân tích.

## 13. Load fact có idempotency và chống ghi lùi version

Sau khi **toàn bộ gate ở phần 12 đạt**, có thể load từ staging bằng as-of join. Đoạn SQL sau giả định quy trình ingestion đã chọn bản staging hợp lệ mới nhất cho mỗi natural line.

~~~sql
INSERT INTO mart.fact_sales_line_confirmed (
    tenant_id,
    source_order_id, source_line_no,
    source_event_id, source_event_version,
    confirmed_at, confirmed_date_key,
    product_key, buyer_key, buyer_kind_code,
    channel_key, store_key,
    currency_code, quantity,
    unit_price_amount, allocated_discount_amount
)
SELECT
    s.tenant_id,
    s.source_order_id, s.source_line_no,
    s.source_event_id, s.source_event_version,
    s.confirmed_at, d.date_key,
    p.product_key, b.buyer_key, s.buyer_kind_code,
    c.channel_key, st.store_key,
    s.currency_code, s.quantity,
    s.unit_price_amount, s.allocated_discount_amount
FROM mart.stage_confirmed_order_lines AS s
JOIN mart.dim_date AS d
  ON d.calendar_date =
     (s.confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
JOIN mart.dim_product_scd2 AS p
  ON p.tenant_id = s.tenant_id
 AND p.source_variant_id = s.source_variant_id
 AND s.confirmed_at >= p.valid_from
 AND (p.valid_to IS NULL
      OR s.confirmed_at < p.valid_to)
LEFT JOIN mart.dim_buyer_scd2 AS b
  ON b.tenant_id = s.tenant_id
 AND b.source_buyer_ref = s.source_buyer_ref
 AND s.confirmed_at >= b.valid_from
 AND (b.valid_to IS NULL
      OR s.confirmed_at < b.valid_to)
JOIN mart.dim_channel AS c
  ON c.tenant_id = s.tenant_id
 AND c.channel_code = s.channel_code
LEFT JOIN mart.dim_store AS st
  ON st.tenant_id = s.tenant_id
 AND st.store_code = s.store_code
ON CONFLICT (tenant_id, source_order_id, source_line_no)
DO UPDATE SET
    source_event_id = EXCLUDED.source_event_id,
    source_event_version = EXCLUDED.source_event_version,
    confirmed_at = EXCLUDED.confirmed_at,
    confirmed_date_key = EXCLUDED.confirmed_date_key,
    product_key = EXCLUDED.product_key,
    buyer_key = EXCLUDED.buyer_key,
    buyer_kind_code = EXCLUDED.buyer_kind_code,
    channel_key = EXCLUDED.channel_key,
    store_key = EXCLUDED.store_key,
    currency_code = EXCLUDED.currency_code,
    quantity = EXCLUDED.quantity,
    unit_price_amount = EXCLUDED.unit_price_amount,
    allocated_discount_amount = EXCLUDED.allocated_discount_amount,
    loaded_at = CURRENT_TIMESTAMP
WHERE
    mart.fact_sales_line_confirmed.source_event_version
        < EXCLUDED.source_event_version;
~~~

**Cách hiểu đoạn nạp:**

- **INSERT** tạo row mới theo grain nguồn.
- **UNIQUE (tenant_id, source_order_id, source_line_no)** và ON CONFLICT chống tạo thêm fact row khi chạy lại.
- **WHERE version mới hơn** không cho một event cũ ghi đè dữ liệu mới.
- Nếu cùng version mà payload khác, lệnh trên **không sửa**. Pipeline phải phát hiện **version collision** bằng data quality check và phân loại là lỗi nguồn, không coi là thành công.
- **Gross/net amount tự tính** bằng generated columns. Không nạp thẳng số tổng từ caller rồi cho phép lệch quantity/discount.
- Nếu thay đổi hợp lệ của một giao dịch đã xác nhận cần chỉnh fact, phải có **hợp đồng correction/version và audit/restatement**; không dùng OrderUpdated tùy ý làm lý do sửa history.
- Việc JOIN dimension không khớp sẽ làm row bị bỏ. **Vì vậy gate trước load và đối soát sau load là bắt buộc**; SQL này không tự chặn missing dimension.

Để dùng trong hệ thật, bao bọc bước **resolve/gate/load/commit** trong một quy trình nhất quán với mức isolation, khóa hoặc version phù hợp. Nếu dimension có thể đổi trong lúc load, cần bảo đảm cùng một ảnh chụp dữ liệu hoặc retry khi có thay đổi, thay vì dựa vào kết quả gate được tính trước rất lâu.

### 13.1. Vì sao không thể chỉ dùng eventId làm UNIQUE fact?

Một sự kiện OrderConfirmed có thể chứa **nhiều order lines** và dùng cùng eventId. Nếu fact UNIQUE(source_event_id), dòng thứ hai cùng đơn sẽ bị coi nhầm là duplicate.

**eventId** dùng chống xử lý trùng event ở inbox; **source_order_id + source_line_no** định danh fact grain. Hai tầng có mục đích khác nhau.

### 13.2. Source event đến muộn và cập nhật SCD Type 2 hồi tố

Một OrderConfirmed xảy ra 10/08 nhưng event chỉ tới warehouse tháng 11. **confirmed_date_key vẫn là ngày 10/08**, và product/buyer dimension phải được resolve theo **10/08**, không theo loaded_at tháng 11.

Nếu một chiều Type 2 bị điều chỉnh hồi tố, fact có thể cần **đánh lại product_key/buyer_key trong khoảng thời gian liên quan** sau khi dimension version được sửa. Việc này phải nằm trong quy trình restatement có nhật ký; một fact trỏ FK tồn tại nhưng **không còn đúng interval** vẫn có thể sai lịch sử.

## 14. Data quality và reconciliation: chứng minh fact không thiếu, không nhân

### 14.1. Tìm những dòng staging chưa có fact hoặc bị nạp lùi version

~~~sql
SELECT
    s.tenant_id,
    s.source_order_id,
    s.source_line_no,
    s.source_event_version,
    f.source_event_version AS fact_version
FROM mart.stage_confirmed_order_lines AS s
LEFT JOIN mart.fact_sales_line_confirmed AS f
  ON f.tenant_id = s.tenant_id
 AND f.source_order_id = s.source_order_id
 AND f.source_line_no = s.source_line_no
WHERE f.sales_line_key IS NULL
   OR f.source_event_version < s.source_event_version;
~~~

Kết quả rỗng nghĩa là **mọi dòng staging được xét** có fact với version bằng hoặc mới hơn. Nó **chưa chứng minh payload giống nhau**, chưa so tiền và chưa kiểm tra as-of key.

### 14.2. Tìm same-version payload mismatch

~~~sql
SELECT
    s.tenant_id,
    s.source_order_id,
    s.source_line_no,
    s.source_event_version
FROM mart.stage_confirmed_order_lines AS s
JOIN mart.fact_sales_line_confirmed AS f
  ON f.tenant_id = s.tenant_id
 AND f.source_order_id = s.source_order_id
 AND f.source_line_no = s.source_line_no
WHERE f.source_event_version = s.source_event_version
  AND ROW(
      f.confirmed_at, f.currency_code,
      f.quantity, f.unit_price_amount,
      f.allocated_discount_amount
  ) IS DISTINCT FROM ROW(
      s.confirmed_at, s.currency_code,
      s.quantity, s.unit_price_amount,
      s.allocated_discount_amount
  );
~~~

Kết quả không rỗng cho thấy nguồn và fact có **cùng version nhưng payload đo lường khác**; cần điều tra trước khi công bố. Ngoài các trường trên, một pipeline production nên so **product/buyer/channel/store mapping và source_event_id** theo hợp đồng; row giống tiền không đủ chứng minh đã gắn đúng chiều.

### 14.3. Đối chiếu tổng tiền staging và fact theo currency

~~~sql
WITH expected AS (
    SELECT
        tenant_id,
        currency_code,
        COUNT(*) AS expected_lines,
        SUM(quantity * unit_price_amount
            - allocated_discount_amount) AS expected_net
    FROM mart.stage_confirmed_order_lines
    GROUP BY tenant_id, currency_code
),
actual AS (
    SELECT
        f.tenant_id,
        f.currency_code,
        COUNT(*) AS actual_lines,
        SUM(f.net_sales_amount) AS actual_net
    FROM mart.fact_sales_line_confirmed AS f
    JOIN mart.stage_confirmed_order_lines AS s
      ON s.tenant_id = f.tenant_id
     AND s.source_order_id = f.source_order_id
     AND s.source_line_no = f.source_line_no
    GROUP BY f.tenant_id, f.currency_code
)
SELECT
    COALESCE(e.tenant_id, a.tenant_id) AS tenant_id,
    COALESCE(e.currency_code, a.currency_code) AS currency_code,
    e.expected_lines, a.actual_lines,
    e.expected_net, a.actual_net
FROM expected AS e
FULL OUTER JOIN actual AS a
  ON a.tenant_id = e.tenant_id
 AND a.currency_code = e.currency_code
WHERE e.expected_lines IS DISTINCT FROM a.actual_lines
   OR e.expected_net IS DISTINCT FROM a.actual_net;
~~~

Kết quả mong đợi trên dữ liệu mẫu: **không có hàng**. Nếu các dòng lỗi mapping bị **INNER JOIN loại bỏ** lúc load, kiểm tra sẽ phát hiện thiếu số dòng hoặc tổng.

**Giới hạn của phép kiểm tra:** so tổng có thể bỏ qua hai sai lệch bù trừ nhau. Cần kết hợp **đối chiếu khóa và payload theo từng dòng**. Nếu fact còn chứa các batch lịch sử khác, việc JOIN lại với stage hiện tại như trên chỉ đo **phạm vi stage**; đừng so COUNT toàn fact với COUNT một batch.

### 14.4. Kiểm tra fact còn trỏ đúng phiên bản chiều

Khi dim_product_scd2 bị chỉnh retroactive, FK vẫn hợp lệ nhưng product_key có thể không còn đúng khoảng:

~~~sql
SELECT
    f.tenant_id,
    f.source_order_id,
    f.source_line_no,
    f.confirmed_at,
    f.product_key,
    p.valid_from,
    p.valid_to
FROM mart.fact_sales_line_confirmed AS f
JOIN mart.dim_product_scd2 AS p
  ON p.tenant_id = f.tenant_id
 AND p.product_key = f.product_key
WHERE NOT (
    f.confirmed_at >= p.valid_from
    AND (p.valid_to IS NULL OR f.confirmed_at < p.valid_to)
);
~~~

Kết quả phải rỗng. Cũng cần kiểm tra **buyer_key**, tương tự, khi buyer là REGISTERED. Việc fact tham chiếu dimension hợp lệ **không tự chứng minh chọn đúng dimension version theo ngày sự kiện**.

### 14.5. Kiểm tra nhất quán trong cùng một Order

Theo hợp đồng staging của bài, tất cả dòng cùng một order có:

- Cùng **confirmed_at**.
- Cùng **currency_code**.
- Cùng **channel_code**.
- Cùng **buyer_kind_code/source_buyer_ref**.
- Cùng **source_event_id** khi phát từ một sự kiện xác nhận đơn.

Kiểm tra ví dụ:

~~~sql
SELECT
    tenant_id,
    source_order_id,
    COUNT(DISTINCT confirmed_at) AS confirmed_at_variants,
    COUNT(DISTINCT currency_code) AS currency_variants,
    COUNT(DISTINCT channel_code) AS channel_variants,
    COUNT(DISTINCT source_event_id) AS event_variants
FROM mart.stage_confirmed_order_lines
GROUP BY tenant_id, source_order_id
HAVING COUNT(DISTINCT confirmed_at) <> 1
    OR COUNT(DISTINCT currency_code) <> 1
    OR COUNT(DISTINCT channel_code) <> 1
    OR COUNT(DISTINCT source_event_id) <> 1;
~~~

Nếu source cho phép một Order được cập nhật bằng nhiều sự kiện **sửa dòng** ở những version khác nhau, điều kiện eventId ở trên không còn phù hợp; phải kiểm tra theo **confirmation transaction/event group**, không áp quy tắc cũ cho mọi mô hình.

### 14.6. Bộ tiêu chí nghiệm thu tối thiểu

| Gate | Ý nghĩa | Mục tiêu |
| --- | --- | --- |
| **missing_date/product/channel** | Không có chiều bắt buộc | 0 |
| **overlapping SCD versions** | Một event khớp nhiều phiên bản | 0 |
| **registered_buyer_unmatched** | Buyer đã xác định nhưng không có chiều | 0 hoặc xử lý theo chính sách có kiểm soát |
| **duplicate_source_line** | Trùng business grain | 0 |
| **stale_event_overwrite** | Fact bị ghi lùi version | 0 |
| **same_version_mismatch** | Cùng version, payload khác | 0 |
| **source_vs_fact_line_diff** | Chênh số dòng trong phạm vi batch | 0 |
| **source_vs_fact_net_diff** | Chênh tiền theo currency | 0 theo precision được duyệt |
| **fact_wrong_scd_interval** | FK đúng hàng nhưng sai thời gian | 0 |
| **unauthorized_dimension_read** | Quyền truy cập sai tenant hoặc người xem | 0 |
| **freshness_lag** | Độ trễ cập nhật fact | Không vượt SLO nghiệp vụ |

Một **job xanh** chưa đủ. Phải có **bằng chứng gate** trước công bố và chỉ số quan sát sau công bố, nhất là khi có late events và dimension thay đổi.

## 15. Viết báo cáo: truy vấn đúng grain và đúng đơn vị

### 15.1. KPI theo ngày, danh mục và kênh

~~~sql
SELECT
    d.calendar_date AS confirmed_business_date,
    p.category_code,
    c.channel_code,
    f.currency_code,

    COUNT(*) AS confirmed_line_count,
    SUM(f.quantity) AS confirmed_unit_quantity,
    SUM(f.gross_sales_amount) AS confirmed_gross_amount,
    SUM(f.allocated_discount_amount) AS discount_amount,
    SUM(f.net_sales_amount) AS confirmed_net_items_amount,

    COUNT(DISTINCT (f.tenant_id, f.source_order_id))
        AS distinct_confirmed_order_count
FROM mart.fact_sales_line_confirmed AS f
JOIN mart.dim_date AS d
  ON d.date_key = f.confirmed_date_key
JOIN mart.dim_product_scd2 AS p
  ON p.tenant_id = f.tenant_id
 AND p.product_key = f.product_key
JOIN mart.dim_channel AS c
  ON c.tenant_id = f.tenant_id
 AND c.channel_key = f.channel_key
WHERE f.tenant_id = $1
  AND d.calendar_date >= $2::DATE
  AND d.calendar_date <  $3::DATE
GROUP BY
    d.calendar_date,
    p.category_code,
    c.channel_code,
    f.currency_code
ORDER BY confirmed_business_date, p.category_code, c.channel_code;
~~~

**Cách đọc:**

- Fact có **một hàng mỗi dòng** nên COUNT(*) đếm line.
- SUM quantity hợp lệ khi mọi dòng là đơn vị chiếc như hợp đồng bài; không tự cộng kg với chiếc nếu hệ hỗ trợ nhiều đơn vị.
- SUM tiền được nhóm theo **currency_code**; không tự cộng VND và USD.
- **COUNT DISTINCT (tenant_id, source_order_id)** đếm đơn duy nhất **trong từng group**.
- Một Order mua cả điện thoại và phụ kiện xuất hiện trong **hai category**, nên **cộng distinct_order_count giữa các category sẽ đếm đơn ấy hai lần**. Muốn tổng số đơn toàn hệ, tính DISTINCT lại trên fact ở grain toàn hệ.
- p.category_code đến từ **dimension version được gắn vào fact theo thời điểm xác nhận**, không phải category hiện hành của variant.

### 15.2. Báo cáo tổng theo ngày, không qua dimension sản phẩm

Nếu người dùng hỏi **“tổng số đơn của ngày 22/11”**, tránh cộng lại các hàng report theo category:

~~~sql
SELECT
    d.calendar_date,
    f.currency_code,
    COUNT(*) AS confirmed_line_count,
    COUNT(DISTINCT (f.tenant_id, f.source_order_id))
        AS distinct_confirmed_order_count,
    SUM(f.net_sales_amount) AS confirmed_net_items_amount
FROM mart.fact_sales_line_confirmed AS f
JOIN mart.dim_date AS d
  ON d.date_key = f.confirmed_date_key
WHERE f.tenant_id = $1
GROUP BY d.calendar_date, f.currency_code
ORDER BY d.calendar_date;
~~~

Kỳ vọng cho dữ liệu ví dụ:

| Ngày | Currency | Dòng | Đơn duy nhất | Net items |
| --- | --- | ---: | ---: | ---: |
| 22/11/2026 | VND | 2 | 1 | 325.000 |
| 23/11/2026 | VND | 1 | 1 | 150.000 |

Tổng cả hai ngày là **3 dòng, 2 đơn và 475.000 VND**. Nếu một đơn có dòng được xác nhận vào những ngày khác nhau — trái với hợp đồng bài — cần làm rõ sự kiện nào đánh dấu xác nhận và grain của fact trước khi dùng truy vấn này.

### 15.3. KPI theo phân khúc lịch sử

~~~sql
SELECT
    COALESCE(b.buyer_segment_code, 'GUEST')
        AS segment_at_confirmation,
    f.currency_code,
    COUNT(DISTINCT (f.tenant_id, f.source_order_id))
        AS distinct_order_count,
    SUM(f.net_sales_amount) AS confirmed_net_items_amount
FROM mart.fact_sales_line_confirmed AS f
LEFT JOIN mart.dim_buyer_scd2 AS b
  ON b.tenant_id = f.tenant_id
 AND b.buyer_key = f.buyer_key
WHERE f.tenant_id = $1
GROUP BY COALESCE(b.buyer_segment_code, 'GUEST'), f.currency_code;
~~~

**Không JOIN theo source_buyer_ref tới hàng is_current = TRUE** nếu metric là phân khúc lúc xác nhận. Điều đó sẽ đánh lại mọi đơn cũ theo VIP/NEW hiện hành và làm sai phân tích cohort lịch sử.

Ở ví dụ bài, **GUEST** được nhận diện từ fact buyer_kind_code; COALESCE bên trên đúng vì CHECK đã chặn REGISTERED có buyer_key NULL. Nếu có thêm trạng thái UNKNOWN hoặc PENDING, cần **một nhãn riêng**, không gộp tất cả vào GUEST.

### 15.4. KPI theo cửa hàng và khu vực

~~~sql
SELECT
    COALESCE(st.region_code, 'ONLINE_NO_STORE') AS store_region,
    c.channel_code,
    f.currency_code,
    SUM(f.net_sales_amount) AS confirmed_net_items_amount
FROM mart.fact_sales_line_confirmed AS f
JOIN mart.dim_channel AS c
  ON c.tenant_id = f.tenant_id
 AND c.channel_key = f.channel_key
LEFT JOIN mart.dim_store AS st
  ON st.tenant_id = f.tenant_id
 AND st.store_key = f.store_key
WHERE f.tenant_id = $1
GROUP BY
    COALESCE(st.region_code, 'ONLINE_NO_STORE'),
    c.channel_code,
    f.currency_code;
~~~

Bài dùng **dim_store Type 1**. Khi cửa hàng được đổi khu vực, báo cáo lịch sử theo region có thể được **restated theo thông tin mới**. Nếu yêu cầu thật là khu vực tại thời điểm bán, hãy chuyển dim_store sang Type 2 và resolve as-of như sản phẩm.

### 15.5. Giá trị trung bình và thứ không cộng được

- **Average line net amount** = SUM(net_sales_amount) / COUNT(line rows).
- **Average order value theo tiền hàng** = SUM(net_sales_amount) / COUNT(DISTINCT order), **trên toàn scope được chọn**.
- **Average unit price** = SUM(gross_sales_amount) / SUM(quantity), không AVG các unit_price không trọng số nếu quantity khác nhau.
- **Distinct order count** không additive giữa các category/channels nếu một Order có thể nằm trong nhiều group.
- **Distinct buyer count** không additive giữa các ngày. Surrogate buyer_key SCD2 cũng không phải “distinct natural buyer”; dùng source_buyer_ref có kiểm soát nếu thực sự cần.

Khi nhóm theo currency, không chia tổng VND + USD cho một số đơn chung rồi gọi đó là average order value bằng tiền. Cần một tỷ giá chuyển đổi có source, mốc và quy tắc; nhiều trường hợp nên giữ riêng từng currency.

## 16. Những lỗi điển hình khi xây star schema bán hàng

| Lỗi | Kết quả sai | Cách sửa |
| --- | --- | --- |
| Fact một hàng Order nhưng group theo SKU | Không phân bổ được tiền đúng | Chọn grain dòng, hoặc có bridge allocation |
| COUNT(*) gọi là order_count | Đếm dòng như đếm đơn | COUNT DISTINCT order ID trong đúng scope |
| JOIN fact với product SCD2 theo natural ID | Một fact ra nhiều version, nhân tiền | JOIN theo surrogate product_key |
| Chọn is_current ở mọi báo cáo lịch sử | Category/segment quá khứ bị thay bằng hiện tại | Resolve as-of khi load fact |
| Chọn dim version từ loaded_at | Event đến muộn gắn sai tháng/nhóm | Dùng confirmed_at authoritative |
| Inner join chiều thiếu, không báo lỗi | Doanh số âm thầm biến mất | Data quality gate/quarantine/reconcile |
| GUEST và REGISTERED unmatched cùng NULL | Không phân biệt nghiệp vụ và lỗi đồng bộ | buyer_kind hoặc unknown member có trạng thái |
| SUM tiền khác currency | Số tiền vô nghĩa | Group currency hoặc FX conversion có contract |
| SUM header order amount sau join line | Nhân tiền theo số dòng | SUM line measure hoặc group order trước |
| SUM distinct order counts qua category | Một đơn thuộc nhiều nhóm bị đếm trùng | Recompute distinct tại scope tổng |
| Ghép payment capture vào sales line trực tiếp | Capture 1:N làm nhân dòng | Fact payment riêng; aggregate trước nếu cần |
| Hủy đơn thì DELETE fact xác nhận | Mất sự thật đã xảy ra | Fact event hủy/điều chỉnh riêng |
| Sao chép tên/email vào dim phổ thông | Rò PII cho consumer analytics | Pseudonym/mục đích và phân quyền |
| SCD2 có hai khoảng chồng nhau | Một event khớp nhiều product_key | Kiểm soát interval, đối soát overlap |
| Unique chỉ trên eventId | Mất dòng thứ hai cùng event OrderConfirmed | UNIQUE ở natural line grain |
| Upsert không kiểm tra version | Sự kiện cũ ghi lùi sự thật | Dùng monotonically increasing version và audit |

## 17. Mở rộng mô hình: hoàn tiền, hủy đơn, khuyến mãi và tỷ giá

Một star schema dùng được lâu dài phải nói rõ **những gì fact hiện tại chưa trả lời**. Fact xác nhận đơn trong bài là **transaction fact về giá trị tiền hàng đã chốt**. Nó không tự có câu trả lời cho **tiền thực thu, hoàn tiền, doanh thu kế toán, chiết khấu của từng chương trình hay số dư tồn kho**.

### 17.1. Fact capture thanh toán có grain khác

Một đơn có thể:

- Capture 50% khi khách đặt.
- Capture 50% còn lại khi giao.
- Có một lần capture thất bại rồi thử lại.
- Có refund một phần sau khi đã capture.

Bảng **fact_payment_capture** nên lấy grain **một capture thực sự được xác nhận** từ hệ Payment, ví dụ:

~~~text
fact_payment_capture:
  tenant_id
  source_capture_id           -- unique theo provider/source scope
  source_order_id             -- degenerate reference
  captured_date_key
  payment_method_key          -- nếu cần và có quyền
  captured_at
  captured_amount
  currency_code
  source_event_id, source_event_version
~~~

**Không JOIN trực tiếp** từng capture vào từng OrderLine rồi SUM cả captured_amount và line_net_amount: với một Order có hai line và hai capture, phép JOIN có thể tạo bốn hàng và nhân số đo cả hai phía. Muốn so “xác nhận” với “thu”, hãy **tổng hợp từng fact về một hàng/Order/currency trước**, sau đó mới JOIN:

~~~text
confirmed_by_order:
  (tenant_id, source_order_id, currency_code)
  SUM(net_sales_amount)

captured_by_order:
  (tenant_id, source_order_id, currency_code)
  SUM(captured_amount)

JOIN ở grain (tenant_id, source_order_id, currency_code)
sau khi từng phía đã aggregate đúng.
~~~

Số tiền của Order và capture có thể khác currency do thanh toán ngoại tệ; nếu vậy không thể chỉ JOIN cùng currency rồi coi phần thiếu là chưa thanh toán. Cần hợp đồng FX/settlement và quy tắc điều chỉnh riêng.

### 17.2. Fact hoàn tiền theo dòng phân bổ

Nếu muốn **giá trị hàng hoàn theo sản phẩm**, một Refund ở cấp Order phải được phân bổ hợp lệ xuống các dòng hoặc ghi từ nghiệp vụ trả hàng. Không tự chia đều số hoàn cho tất cả SKU khi không có quy tắc.

Một fact mở rộng có thể dùng:

~~~sql
CREATE TABLE mart.fact_refund_line (
    tenant_id BIGINT NOT NULL,
    source_refund_line_id UUID NOT NULL,
    source_refund_id UUID NOT NULL,
    source_order_id UUID NOT NULL,
    source_line_no INTEGER NOT NULL,
    refund_date_key INTEGER NOT NULL,
    refunded_at TIMESTAMPTZ NOT NULL,
    currency_code CHAR(3) NOT NULL,
    refunded_quantity INTEGER,
    refunded_amount NUMERIC(18, 2) NOT NULL,

    CONSTRAINT pk_fact_refund_line
        PRIMARY KEY (tenant_id, source_refund_line_id),
    CONSTRAINT fk_fact_refund_date
        FOREIGN KEY (refund_date_key)
        REFERENCES mart.dim_date(date_key),
    CONSTRAINT ck_refund_amount_nonnegative
        CHECK (refunded_amount >= 0),
    CONSTRAINT ck_refund_quantity_positive
        CHECK (refunded_quantity IS NULL OR refunded_quantity > 0)
);
~~~

Bảng này minh họa **grain một dòng refund** có source_refund_line_id duy nhất trong tenant. Nó chưa chứa FK tới fact bán vì fact mẫu có UNIQUE theo dòng nguồn và có PK kỹ thuật; có thể bổ sung quan hệ **(tenant_id, source_order_id, source_line_no)** tới UNIQUE business grain nếu quy trình refund luôn tham chiếu đúng một dòng đơn còn được lưu trong warehouse.

**Refund có thể có currency riêng hoặc chi phí/phí không tương ứng hàng bán**, nên việc tính “confirmed sales – refund” chỉ đúng khi source và chính sách quy đổi/trừ đã được thống nhất. Nếu một refund không phân bổ được về OrderLine, không được tùy chọn product_key để lấp lỗ hổng.

### 17.3. Hủy đơn là sự kiện, không phải xóa quá khứ

Khi một đơn đã xác nhận rồi bị hủy:

- **fact_sales_line_confirmed** giữ sự thật **đã xác nhận**.
- Có thể thêm **fact_order_cancellation** với grain sự kiện hủy hoặc một bảng adjustment theo dòng nếu KPI cần điều chỉnh.
- KPI **net confirmed after cancellations** cần quy tắc rõ: hủy toàn bộ hay một phần, thời điểm trừ theo ngày xác nhận hay ngày hủy, có chia giảm theo product không?
- Không DELETE các dòng khỏi fact xác nhận rồi dùng cùng tên KPI nhưng thay nghĩa theo thời gian.

Nếu doanh nghiệp chọn fact **transactional accumulation** được update thay vì event fact bất biến, phải công bố định nghĩa và quy tắc restatement khác; không trộn hai cách tiếp cận trong một bảng mà không có dấu vết.

### 17.4. Khuyến mãi là quan hệ many-to-many tiềm ẩn fan-out

Một dòng đơn có thể chịu hai chương trình giảm giá. Bảng bridge:

~~~text
bridge_order_line_promotion:
  tenant_id
  source_order_id
  source_line_no
  promotion_key
  allocated_promotion_discount_amount
~~~

Để báo cáo giảm giá theo promotion, **allocated_promotion_discount_amount** phải có hợp đồng phân bổ và đối soát về line_discount. Không JOIN fact_sales_line_confirmed với bridge rồi SUM toàn bộ **net_sales_amount** cho từng promotion và cộng các promotion như thể các hàng không trùng nhau.

Nếu người dùng chỉ cần biết “đơn nào dùng promotion X”, có thể dùng **EXISTS** hoặc một bridge flag. Nếu muốn phân bổ doanh thu cho từng promotion, phải định nghĩa allocation, có thể theo trọng số; không tự suy từ quan hệ N:M.

### 17.5. Nhiều tiền tệ và quy đổi

Fact lưu **currency_code** và **amount theo tiền tệ gốc tại xác nhận**. Nếu cần báo cáo quy đổi sang một currency chung:

- Xác định **fx_rate_source**, ngày/giờ hiệu lực và loại tỷ giá.
- Phân biệt thời điểm order confirmed, captured, settled và refunded.
- Chọn và ghi **tỷ giá áp dụng** theo hợp đồng, tránh tự lấy tỷ giá hôm nay cho đơn quá khứ.
- Lưu/đối soát **amount gốc, currency gốc, rate, amount quy đổi và quy tắc làm tròn** nếu yêu cầu kiểm toán.
- Không cộng VND, USD và EUR khi chưa chuyển về một đơn vị có định nghĩa rõ.

Trong bài thực hành cốt lõi, **giữ báo cáo theo currency gốc** để tránh một lớp nghiệp vụ kế toán chưa được chốt.

## 18. Incremental pipeline: dữ liệu thay đổi và đến muộn thế nào?

Một pipeline thực tế không thể giả định **mọi nguồn và dimension cùng đến đúng thứ tự**.

| Trường hợp | Cách xử lý có kiểm soát |
| --- | --- |
| Event OrderConfirmed đến lặp | Inbox dedupe theo eventId; fact UNIQUE theo natural line grain |
| Event version cũ đến sau | So version nguồn; không cho ghi lùi |
| Event đến muộn nhiều ngày | Dùng **confirmed_at** làm event time và as-of dimension |
| Dimension product/buyer đến muộn | Quarantine hoặc inferred member có trạng thái; reconcile |
| SCD2 thay đổi hồi tố | Sửa khoảng hiệu lực, xác định fact cần restatement, ghi audit |
| Dimension code chưa biết | Chặn publish hoặc mapping có owner, không tự chọn giá trị gần đúng |
| Khách anonymous | buyer_kind GUEST và buyer_key NULL đúng hợp đồng |
| Cửa hàng chưa có trong dim | Đối soát source store_code; không tự chuyển thành ONLINE |
| Nguồn gửi correction | Chấp nhận đúng loại event, version, scope và log sửa |
| Mất kết nối khi nạp | Transaction/retry idempotent, checkpoint và quan sát |
| Xóa/hạn chế thông tin buyer | Quy trình bảo vệ dữ liệu với mapping, projection, cache, backup |
| Rebuild một tháng lịch sử | Nạp lại từ nguồn và metadata version phù hợp; đối chiếu before/after |

### 18.1. Một số watermark khác nhau cần được phân biệt

- **event_time watermark**: đã xử lý đến mốc thời gian nghiệp vụ nào.
- **ingestion watermark**: đã nhận/đọc đến vị trí nào trong nguồn hoặc event stream.
- **dimension freshness watermark**: dimension đã hội tụ đến version nguồn nào.
- **publication watermark**: dữ liệu qua đủ gate và đã được công bố đến kỳ nào.

Nếu chỉ nhìn **MAX(confirmed_at)** trong fact, một sự kiện cực mới có thể được nạp trước khiến hệ tưởng đã xử lý hết các ngày cũ. Cần theo dõi **khoảng trống, lag, checkpoint và late arrival**, không chỉ lấy giá trị timestamp lớn nhất.

### 18.2. Dữ liệu nạp lại phải tôn trọng quyền và metadata thời gian

Khi rebuild fact của tháng 8 vào tháng 11:

1. Đọc **OrderConfirmed** tháng 8 và các correction hợp lệ theo source version.
2. Resolve product/buyer theo **effective time tháng 8**, không theo nhãn hiện hành tháng 11.
3. Áp chính sách xử lý PII, hạn chế/xóa và consent có hiệu lực khi rebuild.
4. Không khôi phục quyền truy cập hoặc mã định danh đã bị thu hồi chỉ vì raw event cũ còn tồn tại.
5. So từng dòng và số đo theo currency, store, channel, category.
6. Công bố lại dashboard khi đã có quyết định **restatement** và audit.

**Idempotency là cần thiết nhưng không đủ**: một pipeline có thể chạy lại không tạo duplicate nhưng vẫn gắn mọi giao dịch lịch sử sang category mới, khiến báo cáo cũ sai.

## 19. Vận hành, hiệu năng và bảo vệ dữ liệu

### 19.1. Phân biệt bảng nguồn, bảng phân tích và bảng công bố

- **Order OLTP:** nguồn có thẩm quyền cho xác nhận đơn, ID, dòng và snapshot giá.
- **Product/Buyer services:** nguồn định nghĩa thuộc tính và lịch sử dimension.
- **Warehouse staging:** nơi chuẩn hóa và validation; không tự là nguồn nghiệp vụ.
- **Dimension SCD2:** mô hình hóa các phiên bản thuộc tính phục vụ as-of analytics.
- **Sales line fact:** dữ kiện dẫn xuất có grain cố định, có lineage.
- **BI semantic layer:** công bố metric đã định nghĩa, giới hạn các phép group/measure và quyền.
- **Search/report cache:** bản sao phục vụ đọc, có freshness và reconciliation.

Một KPI không nên đổi tên từ **confirmed_net_items_amount** sang **revenue** chỉ vì cấp quản lý quen dùng từ “doanh thu”. Mỗi metric cần **owner, công thức, trạng thái lọc, đơn vị, thời điểm và loại trừ**.

### 19.2. Quyền truy cập và dữ liệu cá nhân

Bảng fact không cần họ tên, email, điện thoại hay địa chỉ giao hàng. **source_buyer_ref** trong dimension vẫn là mã có thể liên kết hành vi của cá nhân; cần:

- Chỉ cấp quyền cho consumer theo mục đích và tenant.
- Cho báo cáo phổ thông đọc **các nhóm phân khúc/tổng hợp** nếu không cần tra người.
- Hạn chế xuất **natural IDs, source IDs, pseudonymous buyer refs** khi không cần.
- Kiểm soát nhóm rất nhỏ có thể dẫn đến tái định danh qua ngày, SKU hiếm và cửa hàng nhỏ.
- Quản lý yêu cầu xóa/hạn chế dữ liệu, vòng đời dimension và projection sau khi nguồn thay đổi.
- Giữ việc kiểm tra quyền **theo đối tượng**, không chỉ dựa vào ID khó đoán.
- Không để log/trace/CDC hoặc export âm thầm mang thêm PII vì ứng dụng thay serializer.

Composite FK theo tenant **không thay authorization ở API hoặc database role**. Một người có quyền SELECT toàn fact nhiều tenant vẫn có thể đọc dữ liệu trái phạm vi nếu không có hàng rào khác.

### 19.3. Kiểm tra hiệu năng theo mẫu truy vấn, không theo số index

Một bộ đo tối thiểu:

1. Query net amount theo **ngày × currency**, 30/90/365 ngày.
2. Query theo **category × channel** có độ chọn lọc khác nhau.
3. Query **COUNT DISTINCT order** toàn tenant, theo nhóm và toàn kỳ.
4. Query phân khúc buyer với history SCD2.
5. Nạp batch một triệu dòng, đo write amplification/index space.
6. Resolve as-of product/buyer với dimension có nhiều phiên bản.
7. Late event replay và restatement khi product category đổi hồi tố.
8. Concurrent BI dashboard trong lúc ETL đang chạy.
9. Quyền đọc bằng role hạn chế và kiểm tra không lộ data.
10. Backup/rebuild time và tính đúng sau restore.

Dùng **EXPLAIN (ANALYZE, BUFFERS)**, p95/p99, CPU/I/O, table/index bytes, số bản ghi bị reject và freshness lag. Nếu dùng partition, materialized aggregate hoặc OLAP engine chuyên dụng, ghi rõ **chi phí cập nhật và tính đúng sau rebuild**.

### 19.4. Khi nào tạo aggregate mart?

Nếu dashboard lặp lại truy vấn **ngày × category × channel × currency** trên hàng tỷ line, có thể tạo aggregate:

~~~text
agg_confirmed_sales_daily:
  tenant_id, confirmed_date_key
  category_code_at_confirmation
  channel_key, currency_code
  confirmed_line_count
  confirmed_unit_quantity
  confirmed_gross_amount
  allocated_discount_amount
  confirmed_net_items_amount
  source_watermark
~~~

**Không tự SUM distinct_order_count trên aggregate** khi một Order có nhiều category. Nếu dashboard cần distinct orders ở nhiều cấp tùy ý, có thể phải đọc fact nguồn, dùng cấu trúc riêng hoặc một kỹ thuật distinct có điều kiện và sai số được phê duyệt.

Aggregate là **dữ liệu dẫn xuất**, cần có định nghĩa grain, lineage, idempotent recompute, quyền và SLO. Không coi một bảng tổng hợp là nguồn chuẩn chỉ vì query đọc nhanh.

## 20. Chọn công nghệ: vì sao star schema phù hợp bài này?

| Mô hình | Phù hợp điều gì? | Rủi ro nếu dùng trực tiếp làm báo cáo |
| --- | --- | --- |
| **Relational OLTP** | Ghi đơn, dòng hàng, giữ transaction và FK | JOIN nhiều domain, schema tối ưu cho ghi; trạng thái hiện hành dễ che lịch sử |
| **Document Order** | Đọc nguyên đơn với items[] và snapshot giao dịch | Khi flatten phải bảo đảm grain line; array nhiều loại có thể nhân dữ liệu |
| **Graph** | Quan hệ khách–sản phẩm–đơn–gian lận, traversal | Không tự có fact/measure additive; cần giữ event identity |
| **Time-series** | Chuỗi lượng bán/tồn theo mốc, bucket và sự kiện | Tồn kho snapshot không additive qua thời gian |
| **Star schema/columnar mart** | Tổng hợp theo nhiều chiều, lịch sử Type 2, KPI rõ grain | ETL, dim alignment, late arrival và maintenance |
| **Search index** | Lọc SKU, thuộc tính sản phẩm, trải nghiệm người dùng | Projection stale; không phải nguồn capture/refund/giá đã chốt |

Star schema **không thay thế OLTP**. Nó là mô hình **phục vụ phân tích** dựa trên sự thật giao dịch và các dimension được quản trị, có thể triển khai trên PostgreSQL ở quy mô vừa hoặc trên warehouse columnar khi khối lượng và workload cần.

Một quyết định tốt phải dựa trên **mẫu truy cập, tính tươi, tổng hợp, bảo mật và chi phí vận hành**, không chỉ sở thích công nghệ.

## 21. Bài thực hành tự làm

Hãy dùng DDL và dữ liệu mẫu ở phần 5–13 làm xuất phát điểm. Với mỗi bài, mô tả **grain, truy vấn hoặc DDL, trường hợp biên, dữ liệu mong đợi và cách đối soát**. Không cần chạy trên sản xuất.

### Bài 1 — Xác định grain và chọn số đo

Một Order có ba dòng sản phẩm; một dòng được mua quantity 4. Phòng kinh doanh hỏi “số đơn, số dòng, số chiếc”.

**Yêu cầu:** Hãy viết ba phép tính đúng trên fact_sales_line_confirmed và giải thích vì sao không dùng COUNT(*) cho cả ba KPI.

### Bài 2 — Chứng minh tổng tiền dữ liệu mẫu

Dữ liệu mẫu có ba fact lines: 2 × 150.000 – 20.000, 1 × 50.000 – 5.000, 1 × 150.000 – 0.

**Yêu cầu:** Tính gross, discount, net, line_count, order_count theo currency và nêu giá trị kỳ vọng.

### Bài 3 — SCD2 sản phẩm đổi category

V-101 thuộc ELECTRONICS trước 01/09/2026 và SMARTPHONES từ 01/09/2026. Đơn A xác nhận 20/08, đơn B xác nhận 22/11.

**Yêu cầu:** Mỗi fact trỏ product_key nào? Tại sao JOIN natural ID tới dimension hiện hành sai?

### Bài 4 — SCD2 người mua đổi phân khúc

Một buyer chuyển NEW thành VIP từ 01/10. Có một đơn tháng 8 và một đơn tháng 11.

**Yêu cầu:** Thiết kế truy vấn đếm số đơn theo segment tại lúc bán. Vì sao COUNT DISTINCT(buyer_key) hai tháng có thể đếm cùng người hai lần?

### Bài 5 — Thiếu dimension buyer

Source buyer_ref đã có, buyer_kind REGISTERED, nhưng chưa có dim_buyer_scd2 match confirmed_at.

**Yêu cầu:** Pipeline có được đổi buyer_kind thành GUEST để hoàn thành không? Đề xuất quarantine hoặc inferred-member flow.

### Bài 6 — Một đơn mua hai danh mục

O-1001 mua điện thoại và ốp lưng, mỗi sản phẩm thuộc category khác nhau. Report theo category cho thấy distinct_order_count = 1 ở từng category.

**Yêu cầu:** Tổng số đơn toàn ngày là bao nhiêu? Có thể SUM hai category counts không?

### Bài 7 — Multiple currencies

Một tenant có confirmed_net_items_amount = 325.000 VND và 50 USD trong cùng ngày.

**Yêu cầu:** Thiết kế report đúng; nếu muốn một số tổng hợp bằng VND, cần những trường và chính sách FX nào?

### Bài 8 — Sự kiện trùng và version cũ

Cùng một source_order_id/line_no đã nạp version 3. Broker replay version 2, rồi phát lại version 3 với eventId cũ.

**Yêu cầu:** Fact có bao nhiêu hàng, version cuối là gì? Vai trò khác nhau của eventId và natural line key?

### Bài 9 — Refund không có dòng phân bổ

Payment báo refund 100.000 cho đơn có hai dòng hàng, không có thông tin refund thuộc sản phẩm nào.

**Yêu cầu:** Có nên trừ 50.000 khỏi mỗi dòng hay chọn dòng đầu tiên? Report refund theo product có thể công bố không?

### Bài 10 — Chuyển khu vực cửa hàng

Cửa hàng HCM-01 được đổi region_code theo một sơ đồ vùng vận hành mới vào tháng 12. Báo cáo tháng 11 phải giữ region cũ theo yêu cầu.

**Yêu cầu:** dim_store Type 1 có đủ không? Thiết kế lại grain/version và resolve thế nào?

### Bài 11 — Viết kiểm tra dữ liệu bị bỏ khi load

Một dòng staging có product UUID không tìm được trong dim_product_scd2. Lệnh INSERT...SELECT dùng INNER JOIN.

**Yêu cầu:** Vì sao câu lệnh SQL có thể thành công mà doanh số bị thiếu? Nêu hai kiểm tra chặn publish.

### Bài 12 — Kiểm tra một fact bị gắn sai product version

Fact xác nhận ngày 20/08 nhưng product_key tham chiếu version bắt đầu 01/09. FK vẫn hợp lệ.

**Yêu cầu:** Vì sao FK không chặn? Viết điều kiện SQL phát hiện sai as-of interval.

### Bài 13 — Tổng hợp ngày quá sớm

ETL tạo agg_confirmed_sales_daily ngay khi nhận event 22/11, nhưng vài event confirmed_at 21/11 tới muộn ngày 24/11.

**Yêu cầu:** Aggregate nào phải được cập nhật? Có thể chỉ dựa vào MAX(confirmed_at) không?

### Bài 14 — Cấp quyền cho dashboard

Một báo cáo chỉ cần doanh số theo ngày, channel và category. Dữ liệu dim_buyer có source_buyer_ref có thể liên kết lịch sử mua.

**Yêu cầu:** API/report có cần xuất buyer_ref không? Làm thế nào kiểm tra không lộ thông tin nhạy cảm?

### Bài 15 — Thiết kế fact mới cho số hàng giao

Người dùng muốn “tỷ lệ giao đúng hạn theo hãng vận chuyển” và một Order có thể có nhiều shipments, mỗi shipment có nhiều lần giao thử.

**Yêu cầu:** Chọn fact grain mới, hai dimension liên quan và phân biệt KPI shipment và order.

## 22. Gợi ý lời giải và tiêu chí chấm

### Lời giải 1 — Ba KPI khác grain

- **Số dòng**: COUNT(*) trên fact theo scope.
- **Số chiếc**: SUM(quantity) khi quantity có đơn vị tương thích.
- **Số đơn**: COUNT DISTINCT (tenant_id, source_order_id) tại scope đang xét.

Một dòng quantity 4 vẫn chỉ là **một line**. Nhiều line cùng Order chỉ là **một Order**. Không được SUM các distinct order count từ nhiều category khi cùng Order xuất hiện ở nhiều nhóm.

### Lời giải 2 — Số liệu mẫu

- Gross = **300.000 + 50.000 + 150.000 = 500.000 VND**.
- Discount = **20.000 + 5.000 + 0 = 25.000 VND**.
- Net = **475.000 VND**.
- Quantity = **2 + 1 + 1 = 4 chiếc**.
- Line count = **3**; distinct order count = **2**.

Đúng ba dòng sau nạp; chạy lại cùng version phải cho cùng kết quả.

### Lời giải 3 — Product SCD2

Fact 20/08 chọn **product_key của ELECTRONICS** theo khoảng hiệu lực; fact 22/11 chọn **product_key SMARTPHONES**. Không dùng chỉ natural ID khi JOIN tất cả phiên bản vì có thể sinh hai hàng/fact, và không dùng is_current khi báo lịch sử.

### Lời giải 4 — Buyer SCD2

JOIN fact theo **buyer_key** đã resolve lúc confirmed_at, group by **buyer_segment_code** trong phiên bản chiều ấy. Một người có thể có buyer_key khác nhau trước/sau SCD2, nên COUNT DISTINCT(buyer_key) xuyên thời gian đo **số phiên bản dimension**, không chắc là số người. Nếu thật sự cần distinct buyer qua thời gian, phải dùng mapping natural/pseudonymous được quản trị trong phạm vi quyền.

### Lời giải 5 — Registered unmatched

Không đổi thành GUEST. Có thể quarantine với lý do buyer_dimension_missing, chờ dim_buyer_scd2 xuất hiện rồi retry idempotent. Một phương án inferred member cần đánh dấu unresolved và sửa lại sau; phải có rule, data quality gate và không lộ thông tin định danh.

### Lời giải 6 — Distinct theo category

O-1001 được đếm **1** trong SMARTPHONES và **1** trong ACCESSORIES, nhưng toàn ngày vẫn là **1 Order** cho O-1001. Không cộng 1 + 1 để tuyên bố có 2 đơn. Tính distinct lại trên fact sau khi bỏ chiều category.

### Lời giải 7 — Tiền tệ

Report giữ **currency_code** trong GROUP BY, cho hai dòng VND và USD. Nếu cần tổng quy đổi, cần tỷ giá nguồn, ngày/giờ, loại tỷ giá, currency pair, precision và rounding; có hợp đồng dùng ngày xác nhận hay ngày thanh toán. Không cộng 325.000 và 50 trực tiếp.

### Lời giải 8 — Idempotency

Fact vẫn **một hàng** theo (tenant,order,line), version **3**. Inbox dùng eventId để chống xử lý lại một event; fact dùng natural line key để không nhân dòng khi một OrderConfirmed có nhiều line. Phiên bản cũ không được overwrite version mới.

### Lời giải 9 — Refund

Không tự chia đều hoặc gán dòng đầu tiên. Nếu Refund không có phân bổ đáng tin, có thể báo **refund theo Order/currency**, chưa báo chính xác refund theo product. Cần nguồn nghiệp vụ trả hàng hoặc quy tắc phân bổ có owner/đối soát mới tạo fact refund theo line.

### Lời giải 10 — Store history

Dim_store Type 1 không đủ khi cần giữ vùng lúc bán. Chuyển store sang **SCD2** với surrogate store_key theo phiên bản, valid_from/valid_to và điều kiện không chồng khoảng; resolve **confirmed_at as-of**, rồi gắn store_key tương ứng vào fact. Thay đổi effective time hồi tố cần restatement có audit.

### Lời giải 11 — Missing dimension

INNER JOIN loại dòng unmatched mà INSERT vẫn thành công. Kiểm tra gate **product_matches = 1** trước load và anti-join staging→fact sau load; kiểm tra tổng tiền/line count theo currency để phát hiện số đo biến mất.

### Lời giải 12 — FK không kiểm tra as-of

FK chỉ chứng minh **product_key tồn tại**, không chứng minh phiên bản có hiệu lực ở confirmed_at. Điều kiện cần:

~~~sql
NOT (
    f.confirmed_at >= p.valid_from
    AND (p.valid_to IS NULL OR f.confirmed_at < p.valid_to)
)
~~~

Lọc những fact có điều kiện đó sau JOIN theo product_key để phát hiện sai phiên bản, rồi xác minh nguồn thời gian và quyết định restatement.

### Lời giải 13 — Event muộn

Aggregate của **ngày 21/11** phải được cập nhật/recompute khi late events đến ngày 24/11. MAX(confirmed_at) có thể lớn mà còn thiếu event cũ. Cần ingestion checkpoint, watermark có cơ chế late arrival, cửa sổ cập nhật lại và đối soát từng ngày.

### Lời giải 14 — Quyền dashboard

Dashboard tổng hợp không cần source_buyer_ref. Dùng view/semantic layer chỉ xuất ngày, channel, category, currency và số đo; tenant authorization, attribute allowlist, quyền bảng/source, audit và thử trường hợp nhóm hiếm. Pseudonymous ID vẫn có nguy cơ liên kết, không mặc định vô danh.

### Lời giải 15 — Fact giao hàng

Chọn **fact_shipment_delivery** grain một shipment được giao (hoặc fact_delivery_attempt grain một attempt nếu hỏi số lần thử). Dimension cần **ngày giao** và **carrier**, có thể thêm store/region. Tỷ lệ giao đúng hạn phải xác định cả **tử số, mẫu số, deadline, trạng thái cuối và timezone**. Một Order có nhiều shipment nên **on_time_shipment_count** khác **on_time_order_count**; Order đúng hạn toàn phần thường đòi mọi shipment đạt điều kiện.

## 23. Checklist bài nộp thực hành và thang đánh giá

Một bài nộp đầy đủ nên có:

| Hạng mục | Bằng chứng |
| --- | --- |
| **Định nghĩa nghiệp vụ** | KPI, trạng thái lọc, currency, timezone, ngoại lệ |
| **Grain** | Một hàng fact là gì; natural key đúng |
| **Bus matrix** | Dimension theo mỗi fact/process |
| **Star schema** | Sơ đồ fact ↔ date/product/buyer/channel/store |
| **Dimension design** | Natural/surrogate key, Type 1/Type 2, lịch sử và quyền |
| **Fact DDL** | PK, UNIQUE source grain, FK tenant, CHECK measures |
| **ETL** | Stage contract, as-of resolve, version/idempotent load |
| **Data quality** | Missing/duplicate/overlap/mismatch, net amount reconciliation |
| **Báo cáo** | Ít nhất 3 SQL query với COUNT DISTINCT và currency |
| **Late arrival** | Quarantine/replay/restatement được mô tả |
| **Bảo vệ dữ liệu** | Không phát PII dư thừa, tenant và consumer access |
| **Hiệu năng** | Index dựa trên workload, EXPLAIN và giới hạn partition |
| **Mở rộng** | Tách capture/refund/cancellation khỏi confirmed fact |
| **Khả năng giải thích** | Từ mỗi số KPI có thể truy về source order line và version |

### 23.1. Rubric tham khảo (100 điểm)

| Nhóm | Điểm |
| --- | ---: |
| Grain, business process và KPI đúng | 20 |
| Star schema, dimensions và SCD2 đúng thời gian | 20 |
| DDL với PK/FK/UNIQUE/CHECK theo tenant | 15 |
| ETL, as-of lookup, idempotency và late arrival | 15 |
| Query KPI, chống fan-out và đúng currency | 15 |
| Đối soát, quyền và kế hoạch vận hành | 15 |
| **Tổng** | **100** |

**Không đạt yêu cầu cốt lõi** nếu mô hình có vẻ đầy đủ nhưng sai một trong các bất biến sau: fact bị nhân theo JOIN, dòng nguồn bị bỏ im lặng khi thiếu dimension, báo cáo lịch sử dùng dimension hiện hành, cộng tiền khác currency mà không có hợp đồng, hoặc mở rộng quyền đọc dữ liệu cá nhân không cần thiết.

### 23.2. Tiêu chí nghiệm thu dữ liệu mẫu

Khi thực hiện lần đầu với database trống và ba hàng staging ở phần 11:

- **Số hàng stage:** 3.
- **Số hàng fact sau nạp:** 3.
- **Số order distinct:** 2.
- **Tổng quantity:** 4 chiếc.
- **Gross:** 500.000 VND.
- **Discount:** 25.000 VND.
- **Net:** 475.000 VND.
- **Ngày 22/11/2026:** 2 dòng, 1 đơn, net 325.000 VND.
- **Ngày 23/11/2026:** 1 dòng, 1 đơn, net 150.000 VND.
- **Registered buyer của O-1001:** ánh xạ phân khúc NEW theo version có hiệu lực.
- **Guest của O-1002:** buyer_key NULL có chủ đích, không phải dimension lookup lỗi.
- **Chạy lại load cùng version:** vẫn 3 fact rows và số đo không đổi.
- **Gate của phần 12, 14:** không có lỗi trên dữ liệu mẫu hợp lệ.

Lưu ý: **các DDL/INSERT đã trình bày để thực hành trong môi trường mới**, có giả định rõ về dimension trước khi nạp fact và một tenant mẫu. Với dữ liệu production, không chạy nguyên những thao tác này mà thiếu migration, quản lý role, kiểm thử lock, quota và điều phối pipeline.

## 24. Tổng kết

Thiết kế bảng dữ kiện bán hàng bắt đầu bằng **câu hỏi người dùng cần trả lời**, rồi chọn **business process và grain**. Khi một fact đã là **một dòng đơn được xác nhận**, mọi số đo, khóa, index, metric và phép đối soát phải tôn trọng grain ấy. Nếu làm điều ngược lại — chọn vài bảng trước rồi đặt nhãn KPI sau — kết quả rất dễ sai dù câu SQL chạy thành công.

**Dimension là ngữ cảnh của fact tại thời điểm sự kiện**, không phải một bảng tên gọi hiện hành để JOIN tùy tiện. Product và buyer SCD Type 2 cần **surrogate key theo phiên bản** và resolve **as-of confirmed_at**; phân khúc hoặc category lịch sử không được tự đổi theo thông tin hiện tại.

**Quy trình nạp fact phải có kiểm chứng:** staging được chuẩn hóa, dimension match đúng một bản theo thời gian, bản ghi không hợp lệ có đường xử lý, khóa nguồn ngăn duplicate, version chặn ghi lùi và số đo được đối soát theo currency/grain. Một fact thiếu dữ liệu vì INNER JOIN âm thầm loại hàng không đạt yêu cầu.

**Mỗi chỉ số có ngữ nghĩa riêng.** Giá trị đơn xác nhận không tự đồng nghĩa tiền thu hoặc doanh thu kế toán; COUNT(*) ở fact dòng không là số đơn, distinct order count không cộng tự do giữa danh mục, số tồn cuối kỳ không cộng xuyên ngày và tiền khác currency phải được tách hoặc quy đổi có hợp đồng.

Câu hỏi cuối cùng trước khi công bố dashboard là: **“Từ mỗi con số trên báo cáo, chúng ta có thể chỉ ra sự kiện nguồn, grain, dimension version, tiền tệ, thời gian và phép đối soát đã tạo ra nó hay không?”** Nếu trả lời được bằng dữ liệu và bài kiểm thử chạy lại được, star schema mới thực sự là một mô hình phân tích **rõ nghĩa, dễ tiến hóa và đáng tin cậy**.
