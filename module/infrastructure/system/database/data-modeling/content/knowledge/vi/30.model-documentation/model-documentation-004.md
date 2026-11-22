# Tài liệu hóa độ hạt, nguồn dữ liệu và thời điểm có hiệu lực

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, mô hình dữ liệu không chỉ cần đúng về thực thể, quan hệ, ràng buộc, chuẩn hóa, khóa và chỉ mục. Mô hình còn phải **đủ rõ để người khác hiểu, tích hợp, truy vấn và kiểm chứng** mà không phải đoán ý nghĩa từ tên bảng. Với dữ liệu phục vụ báo cáo, sự kiện và tích hợp, ba câu hỏi đặc biệt quan trọng là:

1. **Độ hạt (*grain*):** chính xác một dòng, một document hoặc một sự kiện đại diện cho điều gì?
2. **Nguồn dữ liệu (*source/provenance*):** thông tin đến từ hệ nào, quy tắc biến đổi gì và ai chịu trách nhiệm về ý nghĩa của nó?
3. **Thời điểm có hiệu lực (*effective time*):** sự thật này áp dụng cho khoảng thời gian nghiệp vụ nào, và hệ thống biết/lưu nó từ khi nào?

Nếu thiếu một trong ba, cùng một mô hình vẫn có thể sinh báo cáo **đếm trùng, lấy sai giá trị lịch sử hoặc kết luận nhầm dữ liệu đến muộn**.

Sau bài này, bạn có thể:

- Viết một **grain statement** kiểm chứng được, chỉ ra khóa duy nhất và phạm vi định danh.
- Lập **data dictionary**, bảng nguồn–đích (*source-to-target mapping*), quyền sở hữu và đường đi dữ liệu (*lineage*).
- Phân biệt **business effective time**, **event time**, **recorded/system time**, **ingestion time**, **snapshot time** và **ngày kinh doanh**.
- Mô tả lịch sử dimension SCD Type 2 và khi nào cần mô hình **hai trục thời gian** (*bitemporal*).
- Viết phép thử SQL cho unique grain, nguồn tham chiếu, trùng event, khoảng hiệu lực chồng lấn, as-of join và đối soát.
- Duy trì tài liệu như một phần của quá trình tiến hóa mô hình, API/event contract và chất lượng dữ liệu.

## 1. Ba trục tài liệu: một “hợp đồng về ý nghĩa”

Đừng mô tả bảng chỉ bằng danh sách cột:

~~~text
fact_order_lines:
    order_id VARCHAR
    line_no INTEGER
    customer_key BIGINT
    amount NUMERIC
    date_key INTEGER
~~~

Đoạn trên **chưa trả lời được**:

- Một dòng là một dòng hàng **hiện hành**, một dòng lúc **xác nhận đơn**, hay một **phiên bản điều chỉnh**?
- `order_id` có duy nhất toàn hệ thống hay chỉ trong một tenant?
- `amount` là giá trị hàng đặt, đã thu, đã hoàn hay doanh thu ghi nhận?
- `customer_key` liên kết với **thông tin khách hiện tại** hay **phiên bản tại lúc mua**?
- `date_key` là ngày tạo, xác nhận, thanh toán hay nạp vào kho?
- Dữ liệu được lấy từ bảng giao dịch, event, import thủ công hay kết quả biến đổi?

Một mô tả đúng phải gắn cả **độ hạt, nguồn và thời gian** vào cùng hợp đồng.

~~~mermaid
flowchart TD
    Q["Câu hỏi nghiệp vụ"] --> G["Grain: một bản ghi là gì?"]
    Q --> S["Source: ai sở hữu sự thật?"]
    Q --> T["Time: sự thật có hiệu lực lúc nào?"]
    G --> M["Tài liệu mô hình và ràng buộc"]
    S --> M
    T --> M
    M --> D["Schema / API / Event / Data mart"]
    D --> V["SQL tests, lineage, đối soát"]
~~~

**Tài liệu mô hình** không thay thế schema vật lý. Nó giải thích **tại sao** khóa, quan hệ, timestamp và phép biến đổi được chọn như vậy, để schema và truy vấn có thể được kiểm chứng.

## 2. Grain: phải viết thành một câu chính xác

**Độ hạt** là lời khẳng định:

> **Một bản ghi trong mô hình X biểu diễn đúng một [đơn vị nghiệp vụ] trong phạm vi [khóa/nguồn/tenant], tại [sự kiện hoặc mốc thời gian] theo [quy tắc phiên bản].**

Ví dụ:

| Mô hình | Grain statement | Khóa nghiệp vụ minh họa |
|---|---|---|
| `fact_confirmed_order_lines` | Một dòng hàng của một đơn **tại lần xác nhận hợp lệ** | `(source_system, tenant_id, order_id, line_no)` |
| `fact_payment_transactions` | Một giao dịch thanh toán được ghi nhận bởi payment provider | `(provider, payment_transaction_id)` |
| `fact_inventory_daily` | Một sản phẩm ở một kho tại **mốc chốt tồn cuối ngày kinh doanh** | `(snapshot_business_date, warehouse_id, product_id)` |
| `fact_order_status_events` | Một lần thay đổi trạng thái của một đơn | `(source_system, event_id)` hoặc sequence được nguồn bảo đảm |
| `dim_customer_segment_history` | Một **phiên bản phân khúc khách hàng có hiệu lực** trong một khoảng thời gian | `customer_segment_key` và quy tắc khoảng không chồng lấn |
| Document đơn hàng | Một đơn **hiện hành** với các dòng hàng được nhúng | ID đơn ổn định trong phạm vi được xác nhận |

Chú ý: các khóa trên là **giả định cần được xác nhận với hệ nguồn**. Nếu một đơn được phép xác nhận nhiều lần, grain “tại lần xác nhận” phải có thêm `confirmation_id` hoặc phiên bản sự kiện thích hợp; không tự chọn `order_id + line_no` rồi làm mất các lần xác nhận khác.

### 2.1. Grain khác với primary key kỹ thuật

Một bảng có `fact_row_id BIGSERIAL PRIMARY KEY` **không chứng minh** nó đúng grain. Hai dòng có `fact_row_id` khác nhau có thể vẫn cùng biểu diễn một sự kiện bị nạp hai lần.

Ví dụ:

~~~text
fact_row_id=1001, tenant=T01, order=O7, line=1
fact_row_id=1002, tenant=T01, order=O7, line=1
~~~

Nếu định nghĩa “mỗi dòng hàng tại lần xác nhận chỉ một bản ghi”, thì hai dòng trên **vi phạm grain** trừ khi có một phiên bản/chuyển trạng thái bổ sung đã được công bố. Tài liệu phải ghi:

- **Business key** phản ánh danh tính ở mức nghiệp vụ.
- **Surrogate key** dùng để tham chiếu hoặc quản lý phiên bản vật lý.
- **Bất biến duy nhất** được DB cưỡng chế hay kiểm tra tại pipeline.
- **Quy tắc duplicate/replay** khi nhận lại cùng một sự kiện.

### 2.2. Grain khác với mức tổng hợp đang hiển thị

Nếu bảng fact ở mức dòng hàng và báo cáo theo tháng:

~~~sql
SELECT DATE_TRUNC('month', confirmed_at) AS month_start,
       SUM(booked_amount) AS total_booked
FROM fact_confirmed_order_lines
GROUP BY DATE_TRUNC('month', confirmed_at);
~~~

thì grain **của bảng** vẫn là một dòng hàng; grain **của kết quả truy vấn** là một tháng. Phải tài liệu hóa cả hai khi xây materialized view hoặc API phân tích:

~~~text
Base fact grain: one confirmed order line
Aggregate grain: one business month × currency
Measure: sum(booked_amount) over eligible lines
~~~

Nếu nhiều loại tiền cùng tồn tại, thiếu `currency` hoặc quy tắc chuyển đổi trong aggregate có thể khiến **tổng tiền vô nghĩa** dù bản thân SQL chạy được.

### 2.3. Grain quyết định những câu hỏi không thể trả lời

Nếu có fact **cấp dòng hàng**, có thể tính `SUM(booked_amount)` theo sản phẩm. Nhưng `COUNT(*)` là **số dòng**, không phải số đơn; số đơn có thể cần `COUNT(DISTINCT (tenant_id, order_id))`.

Nếu chỉ có **snapshot tồn cuối ngày**, không thể suy chính xác số lần nhập/xuất trong ngày nếu không có fact giao dịch. Hai snapshot có chênh lệch bằng 0 vẫn có thể xảy ra nhiều nhập và xuất bù trừ.

Nếu chỉ có **trạng thái hiện tại** của khách, không thể tự suy lại phân khúc của khách vào tháng trước khi hệ chưa từng giữ lịch sử.

Tài liệu tốt nêu **phạm vi không hỗ trợ** thay vì để người dùng nghĩ mô hình trả lời được mọi câu hỏi.

## 3. Ghi rõ loại fact và phép tổng hợp được phép

Một cột số cần có **aggregation semantics**:

| Measure | Grain nguồn | Tính cộng | Cảnh báo |
|---|---|---|---|
| `booked_amount` | Dòng hàng tại xác nhận | Additive khi cùng tiền tệ, dòng không trùng | Không đồng nghĩa `paid_amount` hoặc doanh thu kế toán |
| `on_hand_units` | Kho × sản phẩm × ngày chốt | Semi-additive: cộng theo kho/sản phẩm cùng mốc; **không cộng qua ngày** | Cuối tháng phải chọn snapshot chốt phù hợp |
| `account_balance` | Tài khoản × mốc chốt | Semi-additive theo thời gian | Tính trung bình/số dư cuối kỳ cần quy tắc riêng |
| `conversion_rate` | Theo tập phiên đủ điều kiện | Non-additive | Phải tính lại từ tử số/mẫu số |
| `distinct_customers` | Theo tập khách trong kỳ | Không cộng nếu các nhóm chồng nhau | Không cộng `COUNT(DISTINCT)` theo ngày thành tháng |

**Một trường tiền không thể cộng xuyên các chiều** khi hai nhóm chồng nhau hoặc JOIN một-nhiều làm nhân dòng. Cần ghi các dimension được phép nhóm, đơn vị đo, tiền tệ và **cách xử lý đơn vị không tương thích**.

## 4. Nguồn dữ liệu: phân biệt “nằm ở đâu” và “ai sở hữu sự thật”

**Source of truth** là hệ/miền chịu trách nhiệm xác lập một sự thật nghiệp vụ, không đơn giản là nơi vừa đọc được bản sao mới nhất.

Ví dụ:

~~~text
Orders Service / OLTP
    ├── orders
    └── order_items
          |
          | Transactional outbox / CDC đã được chuẩn hóa
          v
Raw event storage
          |
          | Deduplicate, validate, resolve dimensions
          v
Staging / canonical confirmed lines
          |
          | Type conversion, effective-time lookup
          v
fact_confirmed_order_lines
          |
          v
Data mart / dashboard
~~~

Một dashboard lấy số từ `fact_confirmed_order_lines`, nhưng **dashboard không phải nguồn chân lý** của sự kiện xác nhận đơn. Tương tự, object storage có thể giữ bản raw event nhưng không tự quyết nghĩa của “đã xác nhận”.

### 4.1. Những câu hỏi bắt buộc cho mỗi nguồn

| Thuộc tính | Câu hỏi phải trả lời |
|---|---|
| **Business owner** | Miền nghiệp vụ nào định nghĩa sự kiện/trạng thái? |
| **Technical owner** | Nhóm nào vận hành bảng, topic, API hoặc pipeline? |
| **Source location** | DB/schema/table, topic, endpoint, collection hoặc file cụ thể là gì? |
| **Source grain** | Một bản ghi nguồn biểu diễn một đơn, một dòng, một lần thay đổi hay một snapshot? |
| **Key và namespace** | ID duy nhất theo tenant, store, provider hay toàn cục? |
| **Capture mechanism** | Batch, CDC, API pull, outbox, file import hay nhập thủ công? |
| **Availability / lag** | Dữ liệu có thể trễ bao lâu? Có SLA/SLO nào? |
| **Change semantics** | Insert, update, delete, upsert, tombstone, correction được biểu diễn ra sao? |
| **Data quality** | Nguồn có chặn NULL, duplicate, sai FK, sai trạng thái không? |
| **Retention/replay** | Có thể dựng lại lịch sử bao xa? |
| **Security** | Trường nhạy cảm, quyền đọc, mục đích sử dụng, hạn giữ? |

Tài liệu chỉ ghi “source: Kafka” không đủ: Kafka là **cơ chế truyền/lưu**, không mô tả **người sở hữu ý nghĩa**, loại event, cách định danh hoặc sự thật tại thời điểm nào.

### 4.2. Truy vết từ đích về nguồn (*lineage*)

Ghi đủ các chặng:

~~~text
fact_confirmed_order_lines.booked_amount
    <- staging_confirmed_lines.booked_amount
    <- quantity * unit_price_at_confirmation - line_discount
    <- Orders order_item snapshot at confirmation
~~~

Với mỗi phép biến đổi, cần biết:

- **Công thức** và đơn vị đo.
- **Bộ lọc**: chỉ đơn xác nhận hợp lệ, có tính đơn hủy sau đó hay không?
- **Cách khử trùng**: theo `event_id`, theo phiên bản dòng hay theo business key?
- **Quy tắc null và ngoại lệ**.
- **Mốc thời gian** áp dụng khi lấy dữ liệu chiều lịch sử.
- **Phiên bản quy tắc** và người phê duyệt.

Một cột có nguồn qua nhiều bảng cần ghi rõ **JOIN key, cardinality và grain sau JOIN**. Nếu JOIN sang payment và shipment cùng lúc, rất dễ nhân giá trị dòng hàng:

\[
3\text{ dòng hàng}\times2\text{ payment}\times2\text{ shipment}
=12\text{ dòng nối}.
\]

Không phải cứ `SUM(DISTINCT amount)` là sửa được: hai dòng hàng thật có thể cùng số tiền. Tài liệu lineage phải chỉ ra cách tổng hợp hai fact về grain tương thích **trước khi JOIN**.

## 5. Thời gian: sáu khái niệm không thể đánh đồng

Một thiết kế có thể chứa nhiều cột có đuôi `_at` và `_date`, nhưng mỗi cột đại diện cho một loại thời gian:

| Loại thời gian | Câu hỏi | Ví dụ |
|---|---|---|
| **Business effective time / valid time** | Giá trị hoặc quan hệ **đúng trong nghiệp vụ** từ lúc nào đến lúc nào? | Khách thuộc phân khúc VIP từ 01/06 |
| **Event time** | Sự kiện thực sự **xảy ra** khi nào? | Đơn được xác nhận lúc 09:15 |
| **Recorded/system time** | Hệ thống **biết/lưu** sự thật đó từ lúc nào? | Sửa thông tin phân khúc được ghi ngày 03/07 |
| **Ingestion/processing time** | Pipeline nhận/xử lý dữ liệu khi nào? | Event đến kho dữ liệu lúc 09:20 |
| **Snapshot/as-of time** | Ảnh chụp trạng thái phản ánh mốc nào? | Tồn cuối ngày kinh doanh 30/11 |
| **Business date / reporting period** | Kỳ báo cáo theo lịch và múi giờ nào? | Ngày 22/11 tại Asia/Ho_Chi_Minh |

**Không phải mọi hệ đều cần cả sáu.** Nhưng phải nói rõ các cột hiện có thuộc loại nào; `created_at` không luôn là event time, `updated_at` không luôn là lúc một sự thật có hiệu lực, và `ingested_at` không được tự dùng thay mốc nghiệp vụ.

### 5.1. Event time và ingestion time

Ví dụ một đơn xác nhận:

~~~text
confirmed_at (event time) = 2026-10-31T23:58:00Z
ingested_at  (pipeline)   = 2026-11-01T00:07:00Z
~~~

Nếu KPI là **số đơn xác nhận theo tháng UTC**, đơn thuộc **tháng 10**, không phải tháng 11. Nếu KPI theo ngày kinh doanh của Việt Nam, hai mốc phải được quy đổi theo timezone nghiệp vụ trước khi phân nhóm.

Event đến trễ cần quy tắc **watermark, thời hạn cập nhật kỳ đã chốt và backfill**, không phải đổi event time thành ingestion time để dễ truy vấn.

### 5.2. Ngày kinh doanh và múi giờ

Một timestamp tuyệt đối UTC có thể được nhóm theo ngày khác nhau tại các vùng:

~~~text
2026-11-21T18:30:00Z
  = 2026-11-22 01:30 tại Asia/Ho_Chi_Minh
~~~

Vì vậy cần tài liệu hóa:

- Lưu thời điểm tuyệt đối theo UTC hoặc `TIMESTAMPTZ` có offset rõ.
- **Timezone của báo cáo**: theo tenant/cửa hàng, hay một múi giờ thống nhất?
- Thời gian đóng ngày/kỳ: nửa đêm địa phương hay giờ chốt đặc thù.
- Cách xử lý lịch có DST tại những khu vực áp dụng; **ngày địa phương không luôn dài 24 giờ**.

Ví dụ PostgreSQL:

~~~sql
SELECT
    (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS confirmed_business_date,
    COUNT(*) AS confirmed_lines
FROM fact_confirmed_order_lines
GROUP BY (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
~~~

**Chú ý:** truy vấn này đếm **dòng hàng**, không đếm số đơn, vì grain của fact là dòng hàng. Muốn số đơn cần distinct theo khóa đơn hoặc fact cấp đơn phù hợp. Câu SQL chỉ minh họa cách đổi timezone, không có nghĩa mọi tenant đều dùng giờ Việt Nam.

## 6. “Thời điểm có hiệu lực” cần khoảng thời gian và quy ước biên

Giả sử phân khúc khách hàng thay đổi:

| customer_id | segment | valid_from (UTC) | valid_to (UTC) |
|---|---|---|---|
| C17 | STANDARD | 2026-01-01T00:00Z | 2026-06-01T00:00Z |
| C17 | VIP | 2026-06-01T00:00Z | null (vô hạn) |

Ta chọn khoảng **nửa mở**:

\[
[\text{valid\_from},\ \text{valid\_to})
\]

nghĩa là **bao gồm đầu, loại trừ cuối**. Với quy ước này:

- Sự kiện lúc `2026-05-31T23:59:59Z` thuộc `STANDARD`.
- Sự kiện đúng `2026-06-01T00:00:00Z` thuộc `VIP`.
- Hai khoảng kề nhau không bị chồng lấn tại ranh giới.
- `valid_to IS NULL` có thể quy định là **còn hiệu lực không có mốc kết thúc đã biết**, không phải một giá trị 0 hoặc ngày 1970.

Tài liệu phải ghi rõ **độ chính xác thời gian** (ngày, giây, microsecond), timezone và biên mở/đóng. Nếu hệ nguồn chỉ biết “có hiệu lực từ ngày 01/06 theo giờ cửa hàng”, không được tự chuyển thành `2026-06-01T00:00Z` mà chưa biết timezone cửa hàng.

### 6.1. Bất biến của một thuộc tính lịch sử

Với mỗi `(tenant_id, customer_id)`, nếu hệ chỉ cho phép một phân khúc ở một thời điểm:

1. `valid_from < valid_to` cho khoảng có điểm cuối.
2. **Không có hai khoảng hiệu lực chồng lấn** cho cùng khách.
3. Một thời điểm nghiệp vụ phải ánh xạ tới **0 hoặc 1 phiên bản**; 0 là dữ liệu lịch sử thiếu hoặc nằm ngoài phạm vi, cần xử lý theo chính sách.
4. Có thể có **khoảng trống hiệu lực** nếu nghiệp vụ cho phép; không tự nối liền để che dữ liệu thiếu.
5. Nếu lịch sử được **sửa hồi tố**, phải xác định có tái phân loại các fact và báo cáo cũ không.

### 6.2. SCD Type 2: giữ phiên bản thay vì ghi đè

Ở mô hình dimension Type 1, đổi `segment=STANDARD` thành `VIP` có thể làm mất thông tin tháng trước. Nếu báo cáo yêu cầu “phân khúc **tại thời điểm mua**”, cần lịch sử như **SCD Type 2** (*Slowly Changing Dimension Type 2*) hoặc một bản snapshot đáng tin cậy.

Với SCD Type 2:

- `customer_id`: business key của khách.
- `customer_segment_key`: surrogate key của **một phiên bản**.
- `valid_from/valid_to`: khoảng hiệu lực nghiệp vụ hoặc khoảng hiệu lực phiên bản đã **được định nghĩa rõ**.
- Fact phát sinh tại `confirmed_at` phải gắn với **đúng phiên bản** phù hợp thời điểm.

Tài liệu cần phân biệt **“bản ghi được tạo hôm nay”** với **“bản ghi có hiệu lực từ tháng trước”**; nếu hai khái niệm có thể khác nhau, một cột `updated_at` không thay thế được `valid_from`.

## 7. Ví dụ PostgreSQL: chứng minh phiên bản dimension đúng thời điểm

Đoạn SQL sau minh họa **lịch sử phân khúc của khách trong phạm vi tenant**. Đây là mô hình đơn giản hóa, không tự bao quát mọi quy tắc phân khúc hoặc sửa hồi tố.

### 7.1. Lược đồ lịch sử

~~~sql
CREATE TABLE dim_customer_segment_history (
    customer_segment_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    segment_code TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (valid_to IS NULL OR valid_from < valid_to)
);

-- Chặn nhiều hơn một khoảng "đang mở" cho cùng khách.
CREATE UNIQUE INDEX ux_customer_segment_open
    ON dim_customer_segment_history (tenant_id, customer_id)
    WHERE valid_to IS NULL;

CREATE INDEX ix_customer_segment_asof
    ON dim_customer_segment_history
       (tenant_id, customer_id, valid_from);
~~~

**Giới hạn bắt buộc nêu trong tài liệu:**

- `ux_customer_segment_open` chỉ chặn **hai dòng có `valid_to IS NULL`** cùng khóa; nó **không** ngăn mọi khoảng có `valid_to` cụ thể bị chồng lấn. Cần kiểm tra riêng hoặc áp dụng exclusion constraint phù hợp nếu hệ quản trị và yêu cầu cho phép.
- `recorded_at` ở đây là **thời điểm dòng phiên bản được ghi**, **không đủ** để tái dựng lịch sử “hệ đã biết gì tại thời điểm trước đó” khi có sửa/xóa bản ghi. Muốn bitemporal đúng nghĩa cần mô hình hai trục thời gian ở phần sau.
- Nếu `customer_id` chỉ duy nhất theo một hệ nguồn, khóa phải bổ sung `source_system` hoặc định danh toàn cục đã được bảo đảm; không tự giả định hai nguồn dùng ID giống nhau là cùng khách.
- Index hữu ích hay không phụ thuộc số lượng dữ liệu, cardinality và kế hoạch truy vấn thực tế.

### 7.2. As-of join: nối dòng hàng vào phiên bản phù hợp

Giả sử `staging_confirmed_order_lines` là nguồn đã chuẩn hóa với:

~~~text
source_system, tenant_id, order_id, line_no,
customer_id, confirmed_at, quantity,
unit_price, line_discount_amount, currency_code
~~~

Nó có grain **một dòng hàng được xác nhận** theo phạm vi định danh đã nêu.

~~~sql
SELECT
    s.source_system,
    s.tenant_id,
    s.order_id,
    s.line_no,
    s.confirmed_at,
    d.customer_segment_key,
    d.segment_code AS segment_at_confirmation,
    s.quantity * s.unit_price - s.line_discount_amount
        AS booked_amount,
    s.currency_code
FROM staging_confirmed_order_lines AS s
LEFT JOIN dim_customer_segment_history AS d
  ON d.tenant_id = s.tenant_id
 AND d.customer_id = s.customer_id
 AND d.valid_from <= s.confirmed_at
 AND (d.valid_to IS NULL OR s.confirmed_at < d.valid_to);
~~~

Một khách hiện nay thuộc `VIP` nhưng lúc mua thuộc `STANDARD` phải được ánh xạ theo **`confirmed_at`**, nếu KPI yêu cầu phân khúc tại thời điểm mua.

**Rủi ro quan trọng:** `LEFT JOIN` có thể trả **0 hoặc nhiều hơn 1 phiên bản** cho cùng dòng nguồn. Nếu lịch sử thiếu, `customer_segment_key` là NULL; nếu các khoảng chồng lấn, một dòng hàng có thể bị nhân lên và làm **tăng sai doanh thu**. Trước khi nạp fact, cần kiểm tra số bản ghi khớp đúng **1** (hoặc có quy tắc unknown member được phê duyệt).

### 7.3. Kiểm tra số phiên bản chiều khớp cho từng fact

~~~sql
SELECT
    s.source_system,
    s.tenant_id,
    s.order_id,
    s.line_no,
    COUNT(d.customer_segment_key) AS matching_versions
FROM staging_confirmed_order_lines AS s
LEFT JOIN dim_customer_segment_history AS d
  ON d.tenant_id = s.tenant_id
 AND d.customer_id = s.customer_id
 AND d.valid_from <= s.confirmed_at
 AND (d.valid_to IS NULL OR s.confirmed_at < d.valid_to)
GROUP BY
    s.source_system, s.tenant_id, s.order_id, s.line_no
HAVING COUNT(d.customer_segment_key) <> 1;
~~~

Kết quả:

- `matching_versions = 0`: thiếu chiều hoặc chưa có phiên bản phù hợp tại thời điểm sự kiện.
- `matching_versions > 1`: lịch sử chồng lấn hoặc dữ liệu dimension bị trùng.

Đoạn kiểm tra giả định **staging đã được deduplicate theo grain**. Nếu chính staging có hai dòng cùng business key, `GROUP BY` có thể gộp chúng và tạo số khớp gây hiểu nhầm; do đó **unique-grain test phải chạy trước**.

### 7.4. Kiểm tra khoảng hiệu lực chồng lấn

~~~sql
SELECT
    a.tenant_id,
    a.customer_id,
    a.customer_segment_key AS version_a,
    b.customer_segment_key AS version_b,
    a.valid_from AS a_from,
    a.valid_to AS a_to,
    b.valid_from AS b_from,
    b.valid_to AS b_to
FROM dim_customer_segment_history AS a
JOIN dim_customer_segment_history AS b
  ON a.tenant_id = b.tenant_id
 AND a.customer_id = b.customer_id
 AND a.customer_segment_key < b.customer_segment_key
 AND a.valid_from < COALESCE(b.valid_to, 'infinity'::timestamptz)
 AND b.valid_from < COALESCE(a.valid_to, 'infinity'::timestamptz);
~~~

Với khoảng nửa mở, hai khoảng **giao nhau** khi đầu khoảng này nhỏ hơn cuối khoảng kia và ngược lại. `NULL` được quy ước là vô hạn ở vế cuối. Truy vấn chỉ trả những cặp bị chồng lấn theo quy tắc một lịch sử hiệu lực tuyến tính.

**Không dùng một truy vấn phát hiện chồng lấn làm giải pháp duy nhất cho concurrency.** Trong hệ ghi đồng thời, cần transaction isolation/locking hoặc constraint cơ sở dữ liệu phù hợp để **ngăn** hai cập nhật tạo khoảng chồng lấn chứ không chỉ phát hiện sau.

### 7.5. Lược đồ fact và hợp đồng thời gian

~~~sql
CREATE TABLE fact_confirmed_order_lines (
    source_system TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),

    confirmed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    customer_id TEXT NOT NULL,
    customer_segment_key BIGINT
        REFERENCES dim_customer_segment_history(customer_segment_key),

    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18,2) NOT NULL,
    line_discount_amount NUMERIC(18,2) NOT NULL,
    booked_amount NUMERIC(18,2) NOT NULL,
    currency_code CHAR(3) NOT NULL,

    PRIMARY KEY (source_system, tenant_id, order_id, line_no),
    CHECK (
        booked_amount = quantity * unit_price - line_discount_amount
    )
);
~~~

Ở ví dụ:

- Grain fact: một dòng `(source_system,tenant_id,order_id,line_no)` tại xác nhận hợp lệ.
- `confirmed_at`: **event time** phục vụ báo cáo ngày/tháng xác nhận.
- `ingested_at`: **pipeline arrival time** để đo độ trễ, không dùng thay `confirmed_at`.
- `customer_segment_key`: khóa của phiên bản chiều **tại thời điểm xác nhận**; nullable để minh họa quy trình xử lý chiều tới muộn, nhưng báo cáo sản xuất phải có chính sách chặn/quarantine/unknown rõ ràng.
- `booked_amount`: giá trị hàng sau giảm cấp dòng, chưa gồm thuế/phí giao trong ví dụ.
- `currency_code`: **phải nhóm theo tiền tệ** hoặc quy đổi đúng trước khi `SUM` giữa các tiền tệ.

Nếu nguồn điều chỉnh một dòng đã xác nhận, mô hình phải xác định **ghi thêm sự kiện điều chỉnh** hay **tái lập phiên bản**. Không xóa bản ghi sự kiện lịch sử rồi gọi đó là “dữ liệu tại lúc xác nhận” nếu nghiệp vụ yêu cầu audit.

## 8. Bitemporal: “đúng từ khi nào?” khác “chúng ta biết từ khi nào?”

**Valid time** mô tả khoảng thời gian mà sự thật có hiệu lực trong nghiệp vụ. **System/recorded time** mô tả khoảng mà hệ ghi nhận **phiên bản tri thức ấy** là đang được lưu/biết.

### 8.1. Tình huống sửa hồi tố

Giả sử ban đầu hệ biết:

~~~text
Từ 01/01: khách C17 thuộc STANDARD.
Ngày 03/07, bộ phận nghiệp vụ xác nhận:
    khách C17 thực ra đã thuộc VIP từ 15/05.
~~~

Nếu ta cập nhật trực tiếp hàng `STANDARD` thành khoảng kết thúc 15/05 và tạo hàng `VIP` hiệu lực từ 15/05, báo cáo chạy **ngày 04/07** có thể phân loại lại giao dịch tháng 6 thành VIP. Nhưng nếu người kiểm toán hỏi:

> “Vào **ngày 30/06**, hệ thống đã biết phân khúc nào của C17?”

thì **một lịch sử valid-time sau khi bị cập nhật** có thể không trả lời được. Cần giữ lịch sử **các phiên bản tri thức**.

### 8.2. Hai khoảng thời gian

Một bản ghi bitemporal có thể được mô tả:

~~~text
tenant_id
customer_id
segment_code

valid_from, valid_to       -- Sự thật có hiệu lực trong nghiệp vụ
system_from, system_to     -- Hệ biết/ghi nhận phiên bản này khi nào
~~~

Với cả hai trục, dùng khoảng nửa mở `[from,to)`. Khi sửa hồi tố:

- Các bản ghi tri thức cũ được **đóng `system_to`**, vẫn còn để kiểm toán.
- Các bản ghi tri thức mới được mở **`system_from`** và có `valid_from/valid_to` phản ánh thời gian hiệu lực được xác nhận.
- Truy vấn có thể chọn cả **thời điểm nghiệp vụ cần hỏi** và **thời điểm hệ đã biết**.

Mô hình truy vấn khái niệm:

~~~sql
SELECT segment_code
FROM customer_segment_bitemporal
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id
  AND valid_from <= :business_as_of
  AND (valid_to IS NULL OR :business_as_of < valid_to)
  AND system_from <= :known_as_of
  AND (system_to IS NULL OR :known_as_of < system_to);
~~~

Bảng `customer_segment_bitemporal` và tham số là **mô hình minh họa**, không phải bảng đã tạo trong DDL trước. Việc xây bitemporal chính xác cần **bất biến không chồng lấn cho cùng cặp valid-time và system-time**, quy tắc correction, transaction, kiểm chứng audit và cơ chế ghi system time được kiểm soát.

**Không khẳng định chỉ thêm `recorded_at` là đã có bitemporal.** Một timestamp lúc ghi không lưu được đầy đủ lịch sử những phiên bản trước **đã bị thay thế từ khi nào đến khi nào**.

### 8.3. Báo cáo lịch sử theo hai cách đều có thể hợp lệ

Hai câu hỏi khác nhau:

1. **Restated view:** “Theo thông tin đúng mới được sửa hồi tố, doanh số tháng 6 theo phân khúc nào?”
2. **As-known-at view:** “Vào lúc chốt báo cáo 30/06, hệ đã phân loại doanh số tháng 6 theo phân khúc nào?”

Tài liệu phải nêu rõ **phương pháp công bố báo cáo**: có restate số kỳ cũ không, ai phê duyệt việc sửa hồi tố, và lưu được những phiên bản kết quả đã phát hành hay không.

## 9. Source-to-target mapping: mô tả biến đổi ở cấp field

Một bảng mapping nên có ít nhất:

| Trường đích | Nguồn | Quy tắc | Thời gian sử dụng | Kiểm thử |
|---|---|---|---|---|
| `source_system` | Metadata của connector đã xác thực | ID namespace chuẩn | Tại ingest | Không rỗng, thuộc registry nguồn |
| `tenant_id` | Orders `tenant_id` | Giữ namespace, không đoán từ order ID | Tại event | Phân quyền và tồn tại tenant |
| `order_id` | Orders `id` | Định danh nguồn ổn định | Tại xác nhận | Unique theo phạm vi đã nêu |
| `line_no` | `order_items.line_no` | Thứ tự/ID dòng tại xác nhận | Tại xác nhận | Không NULL, duy nhất trong đơn |
| `confirmed_at` | Event `OrderConfirmed.confirmedAt` | Parse ISO 8601 → `TIMESTAMPTZ` | **Event time** | Không đổi thành thời gian tải |
| `ingested_at` | Metadata pipeline | Timestamp khi hệ đích nhận | **Processing time** | Không dùng tính ngày bán |
| `customer_id` | Orders `customer_id` | Ánh xạ đúng tenant | Tại xác nhận | Không trộn ID giữa nguồn |
| `customer_segment_key` | Dimension lịch sử | As-of lookup tại `confirmed_at` | **Valid time** | Đúng 1 phiên bản hoặc xử lý ngoại lệ |
| `quantity` | Dòng hàng nguồn | Đơn vị số lượng đã chốt | Tại xác nhận | Phạm vi và đơn vị hợp lệ |
| `unit_price` | Giá trên dòng lúc xác nhận | Decimal, không đọc giá sản phẩm hiện tại | Tại xác nhận | Không sai đơn vị tiền |
| `line_discount_amount` | Giảm giá dòng đã chốt | Decimal, theo chính sách | Tại xác nhận | Không vượt chính sách |
| `booked_amount` | Dẫn xuất từ dòng hàng | `quantity * unit_price - discount` | Theo sự kiện | Đối chiếu từng dòng |
| `currency_code` | Orders `currency_code` | Mã tiền tệ được xác nhận | Tại xác nhận | Không cộng lẫn tiền tệ |

**Tại sao phải ghi cả thời gian ở bảng mapping?** Bởi việc lấy `product.category` từ **bảng hiện tại** và việc lấy **phiên bản tại lúc mua** có thể dùng cùng tên nguồn nhưng cho KPI lịch sử hoàn toàn khác nhau.

### 9.1. Khi có nhiều nguồn cho cùng một trường

Ví dụ `customer_segment` có thể xuất hiện trong CRM, Billing và Orders. Không chọn tùy tiện nguồn có timestamp mới nhất. Tài liệu phải quy định:

- Hệ nào **sở hữu định nghĩa** của “phân khúc” cho KPI này.
- Thứ tự ưu tiên nguồn nếu có fallback hợp lệ.
- Khi nào nguồn được coi là **cũ hoặc lỗi**.
- Cách xử lý xung đột, điều chỉnh hồi tố, mapping khách giữa các hệ.
- Cách đối soát và escalations tới owner.

**Một timestamp mới không chứng minh giá trị đúng nghiệp vụ hơn.** Hai hệ có thể đo những khái niệm khác nhau (phân khúc marketing vs phân khúc tín dụng).

### 9.2. Bản sao không tự tạo một nguồn chân lý mới

Nếu `orders` là owner của sự kiện xác nhận, `fact_confirmed_order_lines` là dữ liệu dẫn xuất. Đổi chiến lược lưu trữ thành document, graph hay columnar warehouse **không thay đổi quyền sở hữu sự thật**. Consumer không nên sửa fact rồi kỳ vọng Orders tự đổi trạng thái.

## 10. Mẫu tài liệu mô hình có thể tái sử dụng

Dưới đây là **mẫu YAML dùng bên trong tài liệu bài học để minh họa data contract**, **không** phải cấu trúc ba trường của file metadata bài học.

~~~yaml
model: mart.fact_confirmed_order_lines
document_version: 1
owner:
  business: Orders Domain
  technical: Data Platform
purpose: Gia tri hang dat sau giam gia theo ngay va san pham

grain:
  statement: >
    Mot dong hang cua mot don trong mot tenant va source_system,
    tai lan xac nhan hop le theo quy tac nguon.
  business_key:
    - source_system
    - tenant_id
    - order_id
    - line_no
  duplicate_policy: Reject_or_quarantine_conflicting_duplicates

source:
  authority: Orders Service
  interface: order.confirmed event and line snapshot
  capture: transactional_outbox_or_approved_CDC
  raw_retention: According_to_data_policy
  reprocessability: From_approved_replay_or_snapshot

time:
  event_time: confirmed_at
  ingest_time: ingested_at
  report_timezone: Asia/Ho_Chi_Minh
  effective_dimension_lookup: customer_segment.valid_from_valid_to
  interval_convention: "start_inclusive_end_exclusive"
  late_event_policy: Reconcile_and_restate_within_approved_window
  finalization: Business_owner_approves_period_close

measure:
  booked_amount:
    formula: quantity * unit_price - line_discount_amount
    meaning: booked_merchandise_after_line_discount
    aggregation: sum_when_no_fanout_and_same_currency
    exclusions: [shipping_fee, tax, refunds]
  currency_code:
    meaning: source_transaction_currency

tests:
  - unique_business_key
  - valid_source_namespace
  - exactly_one_effective_customer_version_or_exception
  - amount_formula
  - no_unexplained_source_target_reconciliation_gap

change_control:
  contract_review: Orders_and_Data_Platform
  consumers: [Finance_Reporting, Commercial_Dashboard]
~~~

Các giá trị như `Orders Domain`, tên consumer, chính sách late event và trường loại trừ là **giả định để học**, không phải dữ liệu của một doanh nghiệp cụ thể. Nội dung tài liệu sản xuất phải được **owner xác nhận**, đặc biệt công thức tiền và lúc chốt kỳ.

### 10.1. Những thông tin nên có trong model card

| Nhóm | Tài liệu cần ghi |
|---|---|
| Danh tính | Model ID, tên, mô tả, version, owner, môi trường |
| Mục đích | Câu hỏi hỗ trợ, KPI và **những câu hỏi không hỗ trợ** |
| Grain | Một dòng là gì, khóa nghiệp vụ, phạm vi tenant/source, quy tắc trùng |
| Schema | Cột, kiểu, nullable, default, đơn vị, enum, PK/FK |
| Nguồn | Source of truth, topic/API/table, cơ chế ingest, SLA |
| Mapping | Field-level lineage, công thức, filter, JOIN, quality checks |
| Thời gian | Event, valid, system, ingest, snapshot, timezone, chốt kỳ |
| Lịch sử | Type 1/Type 2/bitemporal, xử lý correction và event đến muộn |
| Quyền | Phân loại dữ liệu, người được truy cập, retention và xóa dẫn xuất |
| Tính đúng | Uniqueness, completeness, referential checks, đối soát nguồn |
| Vận hành | Độ trễ, tải, khôi phục, khả năng replay, owner xử lý sự cố |
| Tiến hóa | Changelog, ảnh hưởng consumer, quy tắc version/deprecation |

**Không nên để các mục quan trọng chỉ trong một comment SQL có thể biến mất khi tái tạo lược đồ.** Tốt hơn là có tài liệu version-controlled/registry liên kết được với migration, contract test và pipeline thực thi.

## 11. Biến tài liệu thành những phép thử thực thi được

Tài liệu chỉ đáng tin khi có bằng chứng rằng dữ liệu tuân theo **grain, nguồn và thời gian** đã công bố.

### 11.1. Kiểm thử duy nhất tại grain

~~~sql
SELECT
    source_system, tenant_id, order_id, line_no,
    COUNT(*) AS occurrences
FROM staging_confirmed_order_lines
GROUP BY source_system, tenant_id, order_id, line_no
HAVING COUNT(*) > 1;
~~~

Với grain ví dụ, truy vấn phải không trả dòng nào **sau khi staging đã áp dụng quy tắc deduplicate được phê duyệt**. Khi trả dòng, không dùng bừa `SELECT DISTINCT *` để che dữ liệu khác nhau: có thể hai sự kiện cùng business key nhưng **số tiền hoặc thời điểm mâu thuẫn**, phải đối chiếu nguồn và version.

Nếu nguồn có quy tắc một đơn được xác nhận nhiều lần, thì grain khác và phép kiểm thử phải bao gồm **định danh lần xác nhận**. Tài liệu có trách nhiệm khiến phép thử và mô hình **khớp nhau**.

### 11.2. Kiểm thử chênh lệch event time và ingestion time

~~~sql
SELECT
    source_system,
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE ingested_at < confirmed_at
    ) AS apparent_negative_lag,
    COUNT(*) FILTER (
        WHERE ingested_at - confirmed_at > INTERVAL '1 hour'
    ) AS rows_later_than_one_hour
FROM fact_confirmed_order_lines
GROUP BY source_system;
~~~

Chênh lệch âm **không tự động chứng minh lỗi**: có thể đồng hồ nguồn sai, event bị backdated theo quy tắc, hoặc timestamp nạp được ghi khác định nghĩa. Cần điều tra cách định nghĩa/capture và đồng bộ đồng hồ. Ngưỡng một giờ **chỉ là ví dụ**, không phải SLO chung.

### 11.3. Kiểm thử đối soát nguồn–đích theo khóa và kỳ

Giả sử nguồn đã chuẩn hóa theo đúng grain, tiền tệ và công thức tương ứng; đối soát:

~~~sql
WITH source_daily AS (
    SELECT
        (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS business_date,
        currency_code,
        COUNT(*) AS source_lines,
        SUM(quantity * unit_price - line_discount_amount)
            AS source_booked
    FROM staging_confirmed_order_lines
    GROUP BY 1, 2
),
mart_daily AS (
    SELECT
        (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS business_date,
        currency_code,
        COUNT(*) AS mart_lines,
        SUM(booked_amount) AS mart_booked
    FROM fact_confirmed_order_lines
    GROUP BY 1, 2
)
SELECT
    COALESCE(s.business_date, m.business_date) AS business_date,
    COALESCE(s.currency_code, m.currency_code) AS currency_code,
    s.source_lines, m.mart_lines,
    s.source_booked, m.mart_booked
FROM source_daily AS s
FULL OUTER JOIN mart_daily AS m
  ON s.business_date = m.business_date
 AND s.currency_code = m.currency_code
WHERE s.source_lines IS DISTINCT FROM m.mart_lines
   OR s.source_booked IS DISTINCT FROM m.mart_booked;
~~~

**Điều kiện để kết quả có nghĩa:**

1. Hai bên cùng phạm vi tenant/source và cùng danh sách sự kiện hợp lệ.
2. Hai bên đã xử lý trùng, cập nhật, hủy và hoàn **theo cùng quy tắc**.
3. Cùng timezone, tiền tệ và độ chính xác/thực hiện làm tròn.
4. Cùng **watermark/chốt dữ liệu**, hoặc có chính sách cho phép trễ và restatement.

Nếu chưa đồng nhất những điều kiện này, truy vấn có thể phát hiện **chênh lệch có lý do**, chưa chắc lỗi nguồn hay đích. Tổng đúng cũng chưa chứng minh từng dòng đúng; hai sai số trái dấu có thể bù nhau. Nên đối soát bổ sung **theo business key** và kiểm tra các mẫu ngoại lệ.

### 11.4. Kiểm tra dữ liệu không khớp dimension

Các kiểm thử tối thiểu:

- Sự kiện có **đúng một phiên bản chiều hiệu lực** hoặc được đưa vào luồng ngoại lệ đã công bố.
- Khoảng hiệu lực lịch sử không chồng lấn; mở/đóng đúng quy ước.
- Không có `customer_segment_key` tham chiếu nhầm khách/tenant.
- Không lấy phân khúc hiện tại khi KPI đòi “tại thời điểm mua”.
- Khi dimension đến muộn, fact được **bổ sung lại khóa chiều** có kiểm soát; báo cáo bị ảnh hưởng được xác định.

Nếu dimension có một hàng “Unknown” để tránh bỏ mất fact, cần tài liệu hóa **vì sao chưa biết, bao lâu được phép chưa biết và lúc nào phải backfill**. Không lặng lẽ coi Unknown là một phân khúc kinh doanh thật.

### 11.5. Kiểm thử null, tính đầy đủ và số đo

~~~sql
SELECT
    source_system, tenant_id, order_id, line_no,
    quantity, unit_price, line_discount_amount, booked_amount
FROM fact_confirmed_order_lines
WHERE confirmed_at IS NULL
   OR currency_code IS NULL
   OR quantity <= 0
   OR booked_amount IS DISTINCT FROM
      quantity * unit_price - line_discount_amount;
~~~

Trong DDL minh họa, một số điều kiện đã được PK/NOT NULL/CHECK cưỡng chế. Trong hệ phân tích không thực thi constraint hoặc trên **staging trước khi nạp**, các phép thử này vẫn cần.

**Không coi `NULL=0`.** Giá trị chưa biết, không áp dụng, lỗi nạp và số 0 là bốn tình huống có thể khác nhau. Tài liệu định nghĩa cụ thể để các phép thử không “sửa dữ liệu” theo một giả định không được phê duyệt.

## 12. Tài liệu hóa dữ liệu đến muộn và thay đổi hồi tố

Hai tình huống cần tách:

### 12.1. Event đến muộn (*late-arriving fact*)

~~~text
OrderConfirmed.occurredAt = 31/10
Warehouse receives event = 02/11
~~~

Nếu KPI tính đơn theo **ngày xác nhận**, giao dịch phải thuộc ngày 31/10 theo timezone đã quy định. Tài liệu cần có:

- Thời hạn dữ liệu được coi là trễ thông thường.
- Cơ chế giữ offset/watermark và phát lại event mà không nạp trùng.
- Khi nào số kỳ cũ còn được cập nhật; ai chốt báo cáo.
- Cách thông báo dashboard/consumer rằng dữ liệu kỳ trước được restate.
- Đối soát dữ liệu nhận trễ với event log nguồn, không tự đổi `confirmed_at`.

### 12.2. Dimension đến muộn (*late-arriving dimension*)

Một đơn xác nhận lúc 09:15, nhưng thông tin phân khúc khách tại lúc mua được đồng bộ từ CRM lúc 10:30.

Các cách xử lý **có điều kiện**:

1. Giữ fact trong vùng chờ trước khi công bố nếu báo cáo yêu cầu dimension đầy đủ.
2. Dùng surrogate key cho “Unknown/Not yet resolved” với hàng đợi backfill và chỉ số chất lượng rõ.
3. Lưu business key và event time để **resolve lại phiên bản** khi dimension đến; cập nhật fact/read model hoặc tái xử lý dữ liệu tùy kiến trúc.

Không dùng phân khúc hiện tại tùy tiện nếu `segment_at_confirmation` chưa có, vì có thể làm sai lịch sử một cách khó phát hiện.

### 12.3. Hiệu chỉnh hồi tố (*retroactive correction*)

Ví dụ ngày 03/07 CRM xác nhận phân khúc đã đổi từ 15/05. Nếu báo cáo tháng 6 từng sử dụng STANDARD, phải quyết định:

- **Restatement:** tính lại lịch sử theo sự thật hiệu lực mới.
- **As-published:** giữ số đã công bố và ghi đính chính riêng.
- **Bitemporal:** hỗ trợ cả góc nhìn theo hiệu lực thật và góc nhìn “đã biết tại ngày công bố”.

Không có một lựa chọn đúng trong mọi lĩnh vực; đặc biệt báo cáo tài chính, đối soát pháp lý và KPI marketing có thể có chính sách chốt khác nhau.

### 12.4. Delete/tombstone cũng cần hiệu lực thời gian

Một event “xóa khách” có thể nghĩa:

- Khách không còn hoạt động **từ một thời điểm nghiệp vụ**.
- Thông tin được xóa khỏi hệ nguồn **vào lúc xử lý**.
- Dữ liệu cá nhân phải được xóa/ẩn danh ở các bản sao theo chính sách.

Các nghĩa trên không tương đương. Tài liệu phải nói rõ loại event, phạm vi bản sao, thời hạn và cách sửa số liệu lịch sử, đồng thời tránh lưu vĩnh viễn dữ liệu nhạy cảm trong event replay chỉ để “giữ lịch sử”.

## 13. Khi tài liệu thay đổi: quản trị version, consumer và migration

Một tài liệu mô hình không nên được viết một lần rồi bỏ quên.

### 13.1. Những thay đổi đòi cập nhật tài liệu

| Thay đổi | Những mục tài liệu phải xem lại |
|---|---|
| Đổi khóa từ `order_id` sang `(tenant_id,order_id)` | Grain, namespace, unique/FK, JOIN, quality tests |
| Chuyển fact cấp đơn thành fact cấp dòng | Grain, aggregation, COUNT DISTINCT, fanout, source mapping |
| Đổi `created_at` sang `confirmed_at` làm thời gian báo cáo | KPI, event time, timezone, restatement, dashboard |
| Bổ sung SCD Type 2 | As-of lookup, interval convention, overlap tests, late dimension |
| Đổi nguồn CRM sang customer master | Authority, lineage, mapping, kiểm thử khác biệt |
| Thêm tiền tệ mới | Currency, conversion policy, aggregation semantics, giá trị biên |
| Thêm CDC thay batch | Watermark/offset, order, duplicate, lag, replay, retention |
| Bỏ một cột hoặc field API/event | Consumer impact, compatibility, deprecation và migration |
| Thay kỳ chốt báo cáo | Business date, update policy, số liệu đã công bố |

### 13.2. Quy trình review gắn với thay đổi code/schema

~~~text
Yêu cầu thay đổi
    ↓
Xác định field/grain/nguồn/thời gian bị ảnh hưởng
    ↓
Đánh giá consumer và dữ liệu lịch sử
    ↓
Cập nhật model card + mapping + tests
    ↓
Review nghiệp vụ + kỹ thuật + bảo mật nếu liên quan
    ↓
Triển khai expand/migrate/contract khi cần
    ↓
Đối soát và đo tác động
    ↓
Ghi changelog và thời điểm áp dụng
~~~

Nên lưu tài liệu **cùng phiên bản có thể truy vết** với schema migration, model SQL và hợp đồng API/event, hoặc trong catalog có liên kết tới commit/release.

Ví dụ changelog:

~~~text
Version 1:
    amount theo dòng; business_date lấy từ confirmed_at (UTC)

Version 2:
    Cùng grain và công thức,
    báo cáo dùng timezone tenant từ ngày được phê duyệt
    Quy tắc backfill/restatement ghi trong migration record
~~~

Đổi timezone có thể **làm đổi số liệu theo ngày** dù không thay cột. Đó là thay đổi ngữ nghĩa KPI, cần thông báo cho consumer, không chỉ sửa query.

### 13.3. Expand–migrate–contract cho thay đổi tài liệu và schema

Khi thay đổi mô hình:

- **Expand:** thêm cấu trúc/field hoặc version mới, tài liệu mô tả cả cũ lẫn mới.
- **Migrate:** chuyển dữ liệu và consumer, có mapping, backfill và đối soát.
- **Contract:** chỉ bỏ field/bảng/hợp đồng cũ khi không còn phụ thuộc và đã xử lý lịch sử.

Tài liệu giúp xác định **điểm không còn rollback đơn giản**: ví dụ sau khi bỏ raw address, lịch sử phân loại hoặc source event không thể replay, có thể không tái dựng được dữ liệu cũ.

## 14. Kết nối tài liệu mô hình với API, event và hệ phân tích

### API: trả trạng thái hiện tại hay trạng thái tại thời điểm?

`GET /customers/{id}` có thể trả phân khúc **hiện tại**. `GET /orders/{id}` có thể trả đơn **hiện hành**. Nếu consumer cần “đơn như đã biết tại ngày 30/06”, API phải **công bố khả năng as-of** và nguồn lịch sử đủ để trả lời; không tự gắn query `asOf` lên một DB chỉ lưu giá trị hiện tại.

Một response JSON thường cần tài liệu về thời điểm đọc, độ mới và mức nhất quán (cache, replica).

### Event: thời điểm xảy ra khác thời điểm nhận

`OrderConfirmed` có:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "O7",
  "tenantId": "T01",
  "occurredAt": "2026-10-31T23:58:00Z",
  "schemaVersion": 1
}
~~~

`occurredAt` là mốc nghiệp vụ được chủ sở hữu event công bố; consumer không được thay bằng `receivedAt`. `eventId` giúp xử lý **trùng logic**, còn `orderId` định danh đơn. Nếu một đơn có nhiều sự kiện khác nhau, **không dùng `orderId` như ID duy nhất của event**.

### Analytics: lựa chọn grain và effective time của dimension

Trong star schema:

~~~mermaid
flowchart LR
    D["dim_date"] --> F["fact_confirmed_order_lines"]
    P["dim_product (phiên bản)"] --> F
    C["dim_customer_segment_history"] --> F
    F --> R["booked_amount + event time"]
~~~

Nếu fact dùng `customer_segment_key` được resolve theo `confirmed_at`, báo cáo phân khúc **tại lúc mua**. Nếu dashboard JOIN trực tiếp với bảng khách **hiện tại**, sẽ trả báo cáo theo phân khúc **hiện nay**. Cả hai có thể có mục đích, nhưng **không thể gọi cùng một KPI mà không ghi rõ**.

## 15. So sánh cách tài liệu hóa giữa các mô hình dữ liệu

| Kiểu mô hình | Grain cần mô tả | Nguồn và thời gian cần mô tả | Rủi ro đặc thù |
|---|---|---|---|
| **Quan hệ OLTP** | Một hàng là entity/trạng thái hay lịch sử? PK/FK trong namespace nào? | Ai ghi, transaction, các cột hiệu lực, audit | `updated_at` bị hiểu nhầm thành ngày có hiệu lực |
| **Document** | Một document là một đơn hay một lần cập nhật? Mảng `items[]` có grain gì? | Version document, snapshot, event nguồn | Mảng bị flatten làm nhân measure cấp đơn |
| **Đồ thị** | Node/edge hay đường đi là đơn vị đang đếm? Quan hệ có thời hạn không? | Owner của cạnh, `valid_from/to`, nguồn cập nhật | Một quan hệ được tìm qua nhiều đường đi dẫn tới đếm trùng |
| **Time series** | Một series là metric + labelset; một mẫu là series + thời điểm | Thời điểm đo, thời điểm ingest, tần suất, missing samples | Label cardinality và churn; timestamp bị dùng làm nhãn |
| **Data warehouse/star** | Transaction, periodic snapshot hay accumulating snapshot | Event/snapshot time, SCD, dữ liệu đến muộn | JOIN fanout và sum semi-additive qua thời gian |
| **Event stream** | Một event logic hoặc một lần delivery? | `eventId`, `occurredAt`, `publishedAt`, offset | Duplicate, out-of-order, replay/version |

**Điểm chung:** bất kỳ engine nào cũng cần giải thích **đơn vị dữ liệu**, **quyền sở hữu sự thật** và **ngữ nghĩa thời gian**. Chuyển từ PostgreSQL sang document store, graph DB hoặc kho cột không làm các câu hỏi này biến mất.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách phòng tránh |
|---|---|---|
| “Grain = primary key kỹ thuật” | Surrogate key không chứng minh một sự kiện không bị nạp lặp | Viết business grain và unique test |
| “`COUNT(*)` luôn là số đơn” | Fact dòng hàng có nhiều dòng/đơn | Phân biệt line, order, event |
| “Source = tên bảng cuối cùng đọc được” | Không chỉ ra owner và quy tắc tạo sự thật | Ghi business owner, source of truth, capture và lineage |
| “Dữ liệu mới nhất từ hệ nào cũng đúng” | Hai hệ có định nghĩa khác nhau | Quy tắc authority và mapping được phê duyệt |
| “`created_at` là thời điểm sự kiện” | Record có thể tạo trước khi xác nhận | Ghi rõ `event_time` cho từng KPI |
| “`ingested_at` có thể dùng làm ngày bán” | Event đến muộn làm sai kỳ | Tách event time/processing time |
| “`updated_at` đã là bitemporal” | Không có lịch sử những gì hệ đã biết | Phân biệt valid-time và system-time, giữ phiên bản |
| “Chỉ cần `valid_from`” | Không biết khi nào bản cũ ngừng hiệu lực | Dùng `valid_to` và biên khoảng rõ |
| “Khoảng hiệu lực chồng lấn không sao” | Một fact JOIN ra nhiều phiên bản, nhân tiền | Unique match và overlap test |
| “Không khớp chiều thì bỏ fact” | Doanh số thiếu nhưng không có cảnh báo | Quarantine/unknown và backfill có giám sát |
| “Lấy phân khúc hiện tại cũng là lúc mua” | Thay đổi lịch sử bị che | SCD Type 2/snapshot và as-of lookup |
| “Số tiền có kiểu NUMERIC nên cộng được” | Khác currency/định nghĩa hoặc fanout | Ghi đơn vị, KPI và grain |
| “Đối soát tổng khớp là dữ liệu đúng” | Sai số từng dòng có thể bù nhau | Đối soát cả khóa, hàng và tổng |
| “Schema SQL tự nói hết ý nghĩa” | Không có nguồn, thời điểm, ngoại lệ | Model card/data dictionary/source mapping |
| “Thay đổi báo cáo không cần sửa tài liệu” | Consumer không biết KPI đã đổi | Review/changelog và contract tests |
| “Xóa ở nguồn đã xóa mọi bản sao” | Raw event, mart, cache, backup có thể còn dữ liệu | Lineage, retention và xử lý dẫn xuất |

## 17. Bài luyện tập có lời giải

### Bài 1 — Viết grain statement

Bảng chứa `order_id`, `line_no`, `product_id`, `amount`. Một đơn có thể có nhiều dòng, và `order_id` được tái sử dụng giữa tenant. Hãy viết grain.

**Lời giải:** Ví dụ: “Một dòng fact đại diện cho **một dòng hàng `(tenant_id,order_id,line_no)` của một đơn đã xác nhận tại lần xác nhận hợp lệ**”. Nếu nguồn có nhiều lần xác nhận, phải bổ sung `confirmation_id`/phiên bản. `order_id` riêng lẻ không đủ.

### Bài 2 — PK không bảo đảm grain

Fact có `fact_row_id` tự tăng, chứa hai dòng khác `fact_row_id` nhưng cùng `(tenant_id,order_id,line_no)`. Có chắc hai dòng hợp lệ?

**Lời giải:** Không. `fact_row_id` chỉ là khóa kỹ thuật. Nếu grain là một dòng tại lần xác nhận, hai dòng có thể là **duplicate** hoặc xung đột dữ liệu. Phải kiểm tra khóa nghiệp vụ và quy tắc phiên bản/event.

### Bài 3 — Đếm đơn và dòng hàng

D01 có ba dòng, D02 có hai dòng. `COUNT(*)` trên fact dòng hàng cho bao nhiêu? Muốn đếm đơn làm thế nào?

**Lời giải:** Có **5 dòng hàng**, nhưng **2 đơn**. Dùng distinct trên **khóa đơn đầy đủ** (tenant/source nếu cần) hoặc fact cấp đơn; không cộng số đơn distinct của các nhóm chồng nhau.

### Bài 4 — Event time và ingestion time

Một đơn xác nhận `2026-10-31T23:58:00Z`, pipeline nhận `2026-11-01T00:07:00Z`. Báo cáo theo tháng xác nhận UTC thuộc tháng nào?

**Lời giải:** **Tháng 10**, vì dùng `confirmed_at`. `ingested_at` dùng đo độ trễ và vận hành, không thay thế thời điểm nghiệp vụ.

### Bài 5 — Phân loại theo timezone

`confirmed_at=2026-11-21T18:30:00Z`. Báo cáo theo ngày kinh doanh Việt Nam thì là ngày nào?

**Lời giải:** **22/11/2026** theo `Asia/Ho_Chi_Minh` (UTC+7 vào thời điểm đó). Nếu báo cáo theo UTC thì là 21/11. **Timezone là một phần định nghĩa KPI**.

### Bài 6 — Biên thời gian SCD2

Khách C17 thuộc STANDARD đến `2026-06-01T00:00Z` (không gồm mốc cuối), rồi VIP từ đúng mốc đó. Đơn xác nhận đúng `2026-06-01T00:00Z` nên thuộc phân khúc nào?

**Lời giải:** **VIP**. Với khoảng nửa mở `[valid_from,valid_to)`, mốc bắt đầu VIP được bao gồm còn mốc kết thúc STANDARD không được bao gồm.

### Bài 7 — Lịch sử chiều bị chồng lấn

Khách C17 có hai bản ghi hiệu lực `[01/01,01/09)` và `[01/06,01/12)`. Một đơn xác nhận tháng 7 JOIN được mấy phiên bản?

**Lời giải:** **2 phiên bản**, vi phạm bất biến một phân khúc tại một thời điểm nếu nghiệp vụ chỉ cho một. JOIN có thể **nhân dòng fact**, nên phải kiểm tra/giải quyết lịch sử trước khi tổng hợp.

### Bài 8 — Recorded_at có phải bitemporal?

Bảng lịch sử chỉ có `valid_from`, `valid_to` và `recorded_at`. Sau correction, các dòng cũ bị UPDATE và mất trạng thái cũ. Có thể trả lời chắc chắn “hệ đã biết gì tại 30/06” không?

**Lời giải:** **Không** nếu không lưu các phiên bản tri thức trước đó. Một `recorded_at` không đủ; phải lưu lịch sử system-time hoặc audit có khả năng tái dựng phù hợp.

### Bài 9 — Nguồn chân lý

BI đọc doanh thu từ data mart; data mart đọc event do Orders phát. Khi có tranh chấp về định nghĩa “đơn đã xác nhận”, hệ nào là owner?

**Lời giải:** **Orders domain** nếu Orders sở hữu chuyển trạng thái xác nhận. Data mart là bản chiếu phục vụ phân tích. Chủ sở hữu KPI có thể xác định thêm công thức báo cáo, nhưng mart không tự đổi định nghĩa event nguồn.

### Bài 10 — Dimension đến muộn

Đơn xác nhận lúc 09:00 nhưng CRM gửi phiên bản phân khúc đúng thời điểm lúc 11:00. Có thể dùng luôn phân khúc hiện tại và gọi đó là “tại lúc mua” không?

**Lời giải:** Không mặc nhiên. Có thể chờ dimension, dùng unknown có giám sát hoặc backfill as-of khi phiên bản lịch sử đến; phải tài liệu hóa chính sách và ảnh hưởng tới báo cáo đã công bố.

### Bài 11 — Đối soát tổng tiền

Nguồn có hai dòng tiền `100` và `200`; mart có `150` và `150`, cùng tiền tệ, phạm vi. Tổng hai bên đều 300. Đã chứng minh đúng chưa?

**Lời giải:** **Chưa**. Tổng khớp nhưng từng dòng sai. Cần so theo khóa nghiệp vụ và số đo cấp dòng, không chỉ tổng kỳ.

### Bài 12 — Thay thời gian báo cáo

Dashboard đang nhóm theo `created_at`, nhóm nghiệp vụ đổi sang `confirmed_at` nhưng giữ tên metric. Chỉ cần sửa SQL?

**Lời giải:** Không. Đây là **thay đổi ý nghĩa** KPI, có thể chuyển giao dịch giữa ngày/tháng. Cần cập nhật model card, lineage, tests, changelog, chính sách restatement và thông báo consumer.

### Bài 13 — Biến một đơn thành document

Nguồn document có `orderTotal=300` và ba phần tử `items[]`. Pipeline flatten `items[]` thành ba dòng nhưng chép `orderTotal=300` vào mỗi dòng rồi `SUM`. Kết quả và lỗi?

**Lời giải:** Tổng thành **900** thay vì 300. Grain document là **một đơn**, còn grain sau flatten là **một item**. Cần measure cấp dòng hoặc giữ `orderTotal` ở fact cấp đơn, không nhân nguyên giá trị cấp đơn.

## 18. Checklist kiểm tra tài liệu mô hình

- [ ] Có **mục đích nghiệp vụ, câu hỏi hỗ trợ và người sở hữu** rõ ràng.
- [ ] Có **grain statement** chính xác cho mỗi bảng/fact/event/document.
- [ ] Có **business key** đầy đủ namespace, quy tắc phiên bản và kiểm thử unique.
- [ ] Không đánh đồng **surrogate key** với danh tính nghiệp vụ.
- [ ] Mỗi measure có **đơn vị, tiền tệ, công thức, quy tắc tổng hợp và loại trừ**.
- [ ] Đã xác định **nguồn chân lý**, vị trí nguồn, cơ chế capture và owner kỹ thuật.
- [ ] Có **source-to-target mapping** từng field và lineage tới nguồn ban đầu.
- [ ] JOIN được ghi rõ **cardinality**, không làm nhân measure.
- [ ] Đã phân biệt **event time, valid time, system/recorded time, ingestion time, snapshot time**.
- [ ] Có timezone, lịch kinh doanh và quy tắc chốt ngày/kỳ nếu dùng thời gian báo cáo.
- [ ] Với khoảng hiệu lực, đã ghi `[from,to)`, nghĩa của `NULL`, độ chính xác thời gian.
- [ ] Với dimension lịch sử, đã chọn Type 1/Type 2/bitemporal theo nhu cầu thực.
- [ ] Có kiểm tra **không chồng lấn khoảng** và đúng một phiên bản cho as-of join.
- [ ] Có chính sách **late fact, late dimension, correction, restatement và replay**.
- [ ] Có cách xử lý dữ liệu **thiếu, NULL, mâu thuẫn, trùng, nguồn không khả dụng**.
- [ ] Có kiểm thử tham chiếu, tính đầy đủ, công thức số đo và đối soát nguồn–đích.
- [ ] Có mô tả quyền truy cập, phân loại dữ liệu, retention và các bản sao dẫn xuất.
- [ ] Tài liệu gắn với **schema/API/event version**, có changelog, review và consumer impact.
- [ ] Đã kiểm thử trên các tình huống biên: đổi tenant, sự kiện đến muộn, phiên bản chồng lấn, ngày giao thời, job nạp lại.

**Ghi nhớ:** Tài liệu mô hình dữ liệu có giá trị khi người đọc có thể trả lời chính xác **“một dòng là gì, sự thật này đến từ ai, và nó đúng vào thời điểm nào?”**. Grain quyết định khóa và phép tổng hợp; nguồn quyết định trách nhiệm và khả năng đối soát; thời gian hiệu lực quyết định cách hiểu lịch sử. Ghi ba điều ấy thành **hợp đồng có phép thử và được quản lý phiên bản** giúp mô hình quan hệ, document, đồ thị và phân tích cùng tiến hóa mà không đánh đổi độ đúng của dữ liệu.


