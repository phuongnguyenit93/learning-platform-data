# Thực hiện một thay đổi mô hình có chuyển đổi dữ liệu và đối soát

## Mục tiêu và cách sử dụng bài thực hành

Trong chương **Thực hành tổng hợp** của module **DATABASE_DATA_MODELING**, chúng ta luyện chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng: thực thể, quan hệ, bất biến, chuẩn hóa, khóa, chỉ mục và lược đồ vật lý. Sau đó, cần biết cách tiến hóa mô hình quan hệ, document, đồ thị hoặc phân tích mà **không đánh mất ý nghĩa dữ liệu đã tồn tại**. Bài này biến mục tiêu ấy thành một bài thực hành từ yêu cầu đến thiết kế, chuyển đổi dữ liệu, phát hiện lỗi, đối soát, kiểm thử và bàn giao.

Kết thúc bài, bạn cần có khả năng:

1. Phát biểu mục tiêu thay đổi và **grain, identity, invariants, owner** của dữ liệu trước và sau.
2. Thiết kế **schema đích** từ nguồn document JSONB chứa dòng hàng sang bảng OrderHeader và OrderLine đã chuẩn hóa; chọn PK, FK, CHECK, index, transaction và chính sách số tiền.
3. Tạo **bộ dữ liệu thử** có bản ghi sạch lẫn lỗi, phát hiện dữ liệu không đủ điều kiện bằng quy tắc có thể giải thích; không âm thầm sửa tiền để migration chạy hết.
4. Chuyển dữ liệu theo các bước **expand → assess/quarantine → backfill → catch-up → verify → switch → contract** và kiểm tra việc chạy lại.
5. Đối soát số Order, số line, tổng tiền, trạng thái, phiên bản và **một-một theo business key**, thay vì chỉ so COUNT(*).
6. Xử lý writer đồng thời, retry, dữ liệu mới trong thời gian backfill, thay đổi contract API/event và báo cáo phân tích.
7. Thiết kế rollback/roll-forward, giám sát vận hành, bảo mật tenant và kịch bản test mà người khác có thể kiểm chứng.

Đây là một **bài thực hành có hướng giải**, không phải script áp dụng nguyên xi lên production. SQL minh họa sử dụng PostgreSQL, Java dùng cú pháp Java 17. Các đoạn có tham số bắt đầu bằng dấu hai chấm là SQL dùng trong prepared statement hoặc migration runner có bind biến; không phải cứ dán vào psql là chạy được. Chỉ thực thi trên môi trường thử có dữ liệu giả, sao lưu thích hợp và quyền hạn được giới hạn.

## 1. Yêu cầu thay đổi: từ Order chứa JSON sang Order và các dòng có khóa riêng

Hệ thống bán hàng đang dùng một bảng nguồn **sales.order_legacy**. Mỗi hàng đại diện cho một Order. Danh sách mặt hàng được lưu trong cột **items_jsonb**:

~~~json
{
  "tenantId": "T1",
  "orderId": "O100",
  "customerId": "C1",
  "status": "CONFIRMED",
  "currency": "VND",
  "totalVnd": 310000,
  "version": 2,
  "items": [
    {
      "lineNo": 1, "skuId": "A",
      "quantity": 2, "unitPriceVnd": 120000,
      "discountPerUnitVnd": 10000
    },
    {
      "lineNo": 2, "skuId": "B",
      "quantity": 1, "unitPriceVnd": 90000,
      "discountPerUnitVnd": 0
    }
  ]
}
~~~

Đối tượng JSON minh họa các trường nằm trong một hàng: metadata Order ở cột riêng, mảng items thực sự nằm trong items_jsonb. Do đó nó là **mô hình lưu vật lý dạng lai**: một row cho Order và một document JSONB cho lines, không phải khẳng định PostgreSQL đã lưu nguyên JSON kể trên làm một cột duy nhất.

**Động lực thay đổi:**

- Cần kiểm tra lineNo duy nhất trong phạm vi Order và quantity/giá đúng kiểu, ngăn dữ liệu lỗi ngay khi ghi.
- Cần truy vấn theo SKU, theo ngày và theo tenant trên hàng triệu dòng, giảm việc giải mảng JSONB trong nhiều query giao dịch.
- Cần liên kết các nghiệp vụ trả hàng/điều chỉnh vào **danh tính từng dòng hàng** được kiểm soát.
- Cần giữ lại lịch sử Order, snapshot đơn giá và ngữ nghĩa tổng tiền trong khi ứng dụng cũ vẫn có thể chạy một phần giai đoạn triển khai.

**Mục tiêu:** tạo **sales.order_header** và **sales.order_line**; mỗi Order có một header và nhiều line. Khóa (tenant_id, order_id, line_no) xác định line. Tổng tiền được phân thành gross, discount, payable. Có đối soát trước khi chuyển quyền ghi/đọc sang schema mới.

Điều **không** đổi: ý nghĩa nghiệp vụ của Order, các trạng thái đã xác nhận, ID công khai, tiền VND, quyền sở hữu của Sales và hợp đồng hiện hành mà consumer được cam kết. Không tự quyết rằng vì đã tách bảng nên API phải trả mảng lines dưới tên khác hoặc event OrderConfirmed phải đổi định dạng ngay.

## 2. Chốt ngữ nghĩa: grain, phép tính và nguồn có thẩm quyền

| Khái niệm | Trước | Sau | Bất biến giữ nguyên |
| --- | --- | --- | --- |
| Order | Một hàng legacy / một Order | Một hàng order_header | Một Order trong tenant |
| OrderLine | Một phần tử items_jsonb | Một hàng order_line | lineNo duy nhất trong Order |
| Customer | customer_id | customer_id | Chỉ tham chiếu ID, không nhúng Customer aggregate |
| Product | skuId trong phần tử JSON | sku_id của dòng | Đơn giá là snapshot lúc mua |
| Total | total_vnd của source | gross_total_vnd, discount_total_vnd, payable_total_vnd | Payable sau giảm giá không đổi nghĩa |
| Status | DRAFT, CONFIRMED, CANCELLED | Cùng trạng thái | Chỉ command của Sales được chuyển trạng thái |
| Version | version của Order | version của Order root | Không dùng như schemaVersion của event |

Trong phạm vi bài, tiền là **số nguyên đồng VND**, không có thuế/phí vận chuyển, chưa có hoàn tiền và mỗi dòng có giảm giá **trên mỗi đơn vị**. Nếu \(q_i\) là quantity, \(p_i\) là đơn giá, \(d_i\) là giảm giá/đơn vị:

\[
g_i=q_ip_i,\qquad r_i=q_id_i,\qquad n_i=g_i-r_i.
\]

\[
q_i>0,\quad p_i\ge0,\quad 0\le d_i\le p_i,\quad
\mathrm{gross}=\sum_i g_i,\quad
\mathrm{discount}=\sum_i r_i,\quad
\mathrm{payable}=\mathrm{gross}-\mathrm{discount}.
\]

**Quy tắc bắt buộc:**

- Order CONFIRMED phải có ít nhất một dòng hợp lệ và thời điểm confirmedAt.
- Order DRAFT có thể tạm rỗng; không cho sửa giá/dòng đơn CONFIRMED qua lệnh thông thường.
- Cùng tenantId+orderId không được có hai Order; cùng Order không có hai dòng lineNo.
- customerId, status, total, currency, version và mọi snapshot giá phải được giữ đúng ý nghĩa sau khi chuyển.
- Một bản ghi nguồn lỗi **không được lặng lẽ bỏ qua rồi báo 100% thành công**; phải có bản phân loại, nguyên nhân và người sở hữu xử lý.
- Tổng của header phải bằng tính lại từ các line cùng version/transaction, không chỉ khớp một con số tổng trên báo cáo.

**Sales sở hữu** trạng thái, snapshot giá, các dòng và việc confirm. **Payment** sở hữu sự thật đã thu tiền, **Inventory** sở hữu giữ tồn, **Analytics** sở hữu định nghĩa fact/metric phát sinh. Chuyển bảng lưu trữ không cấp cho hệ thống khác quyền đổi Order.

### Sơ đồ trước và sau

~~~mermaid
flowchart LR
    subgraph Source["Legacy: JSONB trong Order"]
      A["order_legacy<br/>PK tenant_id + order_id"]
      J["items_jsonb<br/>mảng {lineNo, sku, qty, price, discount}"]
      A --> J
    end
    subgraph Target["Đích: quan hệ đã chuẩn hóa"]
      H["order_header<br/>PK tenant_id + order_id"]
      L["order_line<br/>PK tenant_id + order_id + line_no"]
      H -->|"FK, 1 : N"| L
    end
    A -. "migration có đối soát" .-> H
    J -. "mỗi phần tử hợp lệ" .-> L
~~~

Sơ đồ đích là **1:N về quan hệ logic**, nhưng một Order DRAFT có thể có 0 dòng. Vì vậy cardinality thực thi là **Order 0..N OrderLine**, và mọi OrderLine thuộc **đúng một** Order.

## 3. Bộ dữ liệu mẫu và đáp án tài chính được chốt trước

Để có kết quả khách quan, dùng sáu Order trong tenant T1, trong đó **ba Order hợp lệ**, ba Order cần điều tra:

| Order | Status | Nội dung chính | total_vnd nguồn | Kết quả đánh giá |
| --- | --- | --- | ---: | --- |
| O100 | CONFIRMED | A: 2×120.000 giảm 10.000/đv; B: 1×90.000 không giảm | 310.000 | OK |
| O101 | DRAFT | A: 1×120.000 không giảm | 120.000 | OK |
| O102 | CONFIRMED | B: 3×90.000 giảm 5.000/đv | 255.000 | OK |
| O103 | CONFIRMED | A: 1×100.000; B: 2×50.000, đều không giảm | **200.001** | AMOUNT_MISMATCH: dòng = 200.000 |
| O104 | DRAFT | Hai dòng cùng lineNo=1, giá 10.000 và 15.000 | 25.000 | DUPLICATE_LINE_NO |
| O105 | CONFIRMED | Không có dòng, total=0 | 0 | EMPTY_CONFIRMED |

**Đáp án trước khi chuyển:**

- O100: gross 330.000, discount 20.000, payable **310.000**.
- O101: gross 120.000, discount 0, payable **120.000**.
- O102: gross 270.000, discount 15.000, payable **255.000**.
- **Ba Order được chấp nhận:** 3 header, 4 line, tổng gross **720.000**, discount **35.000**, payable **685.000**; riêng hai Order CONFIRMED có payable **565.000**.
- **Ba Order bị cách ly:** O103, O104, O105; không được hòa vào số "đã di chuyển thành công".

Lưu ý tổng gross ba Order hợp lệ = 330.000 + 120.000 + 270.000 = **720.000**, payable = 310.000 + 120.000 + 255.000 = **685.000**. Mục tiêu đối soát là giữ được cả tổng **theo tập bản ghi** và từng Order/line; chỉ so số tổng có thể che trường hợp một Order tăng 1 VND và Order khác giảm 1 VND.

Không sửa total O103 từ 200.001 về 200.000 theo phép tính ngay trong migration. Sai lệch 1 VND có thể là dấu hiệu giá lịch sử bị thiếu, làm tròn hay lỗi hệ thống cũ; phải xác minh nguồn có thẩm quyền trước khi quyết định sửa.

## 4. Dựng schema nguồn trên PostgreSQL

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.order_legacy (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    total_vnd BIGINT NOT NULL CHECK (total_vnd >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    items_jsonb JSONB NOT NULL
        CHECK (jsonb_typeof(items_jsonb) = 'array'),
    created_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);
~~~

Cột JSONB được kiểm tra ở **mức mảng**, chưa bảo vệ từng lineNo, số lượng, giá hoặc tổng tiền. Vì vậy đây là ví dụ hợp lý về một legacy storage có **bất biến nghiệp vụ yếu hơn** những gì nghiệp vụ muốn cam kết. Migration bổ sung khả năng phát hiện/ràng buộc; không được suy từ việc có JSONB mà kết luận PostgreSQL không thể kiểm tra sâu hơn.

### Dữ liệu mẫu: ba hàng sạch

~~~sql
INSERT INTO sales.order_legacy (
    tenant_id, order_id, customer_id, status, total_vnd,
    version, items_jsonb, created_at, confirmed_at
) VALUES
(
    'T1','O100','C1','CONFIRMED',310000,2,
    '[{"lineNo":1,"skuId":"A","quantity":2,
       "unitPriceVnd":120000,"discountPerUnitVnd":10000},
      {"lineNo":2,"skuId":"B","quantity":1,
       "unitPriceVnd":90000,"discountPerUnitVnd":0}]'::jsonb,
    TIMESTAMPTZ '2026-11-20 08:00:00+00',
    TIMESTAMPTZ '2026-11-20 09:00:00+00'
),
(
    'T1','O101','C1','DRAFT',120000,1,
    '[{"lineNo":1,"skuId":"A","quantity":1,
       "unitPriceVnd":120000,"discountPerUnitVnd":0}]'::jsonb,
    TIMESTAMPTZ '2026-11-21 08:00:00+00',NULL
),
(
    'T1','O102','C2','CONFIRMED',255000,3,
    '[{"lineNo":1,"skuId":"B","quantity":3,
       "unitPriceVnd":90000,"discountPerUnitVnd":5000}]'::jsonb,
    TIMESTAMPTZ '2026-11-21 10:00:00+00',
    TIMESTAMPTZ '2026-11-21 11:00:00+00'
);
~~~

### Dữ liệu mẫu: ba hàng có vấn đề cần quarantine

~~~sql
INSERT INTO sales.order_legacy (
    tenant_id, order_id, customer_id, status, total_vnd,
    version, items_jsonb, created_at, confirmed_at
) VALUES
(
    'T1','O103','C3','CONFIRMED',200001,2,
    '[{"lineNo":1,"skuId":"A","quantity":1,
       "unitPriceVnd":100000,"discountPerUnitVnd":0},
      {"lineNo":2,"skuId":"B","quantity":2,
       "unitPriceVnd":50000,"discountPerUnitVnd":0}]'::jsonb,
    TIMESTAMPTZ '2026-11-21 12:00:00+00',
    TIMESTAMPTZ '2026-11-21 13:00:00+00'
),
(
    'T1','O104','C4','DRAFT',25000,1,
    '[{"lineNo":1,"skuId":"A","quantity":1,
       "unitPriceVnd":10000,"discountPerUnitVnd":0},
      {"lineNo":1,"skuId":"B","quantity":1,
       "unitPriceVnd":15000,"discountPerUnitVnd":0}]'::jsonb,
    TIMESTAMPTZ '2026-11-21 14:00:00+00',NULL
),
(
    'T1','O105','C5','CONFIRMED',0,2,
    '[]'::jsonb,
    TIMESTAMPTZ '2026-11-21 15:00:00+00',
    TIMESTAMPTZ '2026-11-21 15:30:00+00'
);
~~~

**Quan trọng:** những hàng lỗi này được tạo **có chủ ý** cho bài tập kiểm chứng; chúng không được đưa vào production. Các INSERT là setup một lần, không idempotent nếu chạy lặp trên cùng bảng. Các trường thời gian là UTC và hoàn toàn giả lập; khi nạp dữ liệu thực, cần giữ nguyên instant hoặc policy timezone được công bố.

## 5. Thiết kế schema đích: quan hệ và ràng buộc vật lý

~~~sql
CREATE TABLE sales.order_header (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    currency_code CHAR(3) NOT NULL CHECK (currency_code = 'VND'),
    gross_total_vnd BIGINT NOT NULL CHECK (gross_total_vnd >= 0),
    discount_total_vnd BIGINT NOT NULL CHECK (discount_total_vnd >= 0),
    payable_total_vnd BIGINT NOT NULL CHECK (payable_total_vnd >= 0),
    version BIGINT NOT NULL CHECK (version >= 0),
    migrated_from_version BIGINT NOT NULL CHECK (migrated_from_version >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (discount_total_vnd <= gross_total_vnd),
    CHECK (gross_total_vnd - discount_total_vnd = payable_total_vnd),
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);

CREATE TABLE sales.order_line (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku_id TEXT NOT NULL CHECK (length(trim(sku_id)) > 0),
    quantity BIGINT NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    discount_per_unit_vnd BIGINT NOT NULL
        CHECK (discount_per_unit_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header (tenant_id, order_id),
    CHECK (discount_per_unit_vnd <= unit_price_vnd)
);

CREATE INDEX order_header_by_customer
    ON sales.order_header
        (tenant_id, customer_id, created_at DESC, order_id DESC);

CREATE INDEX order_line_by_sku
    ON sales.order_line (tenant_id, sku_id, order_id);
~~~

Ở đích, **OrderHeader** có grain một Order, **OrderLine** có grain một dòng của Order. PK ghép tenant vào quan hệ tránh một line T2 trỏ nhầm header T1. FK bảo vệ tồn tại header trong cùng DB. Index thứ nhất phục vụ danh sách đơn gần đây theo khách, index thứ hai hỗ trợ các truy vấn theo SKU nhưng cần đo plan thực tế. Index có chi phí ghi và không phải cứ thêm field là cần index.

**Những bất biến chưa được CHECK giải quyết hoàn toàn:**

- Order CONFIRMED phải có ít nhất một dòng. CHECK trên một header row không tự thấy các row con.
- Tổng header phải bằng **SUM(line.quantity × line.price)** và tổng giảm giá của toàn bộ các dòng.
- Không được sửa line của Order CONFIRMED.
- Mọi request cập nhật Order phải áp **quyền tenant, version hoặc lock**, kể cả batch/import/admin.

Những điều này cần domain behavior, transaction/giao thức khóa nhất quán và kiểm tra dữ liệu. Nếu muốn enforce hoàn toàn trong DB, có thể cân nhắc trigger/procedure hoặc quyền DB chặt hơn, nhưng phải review transaction semantics và hiệu năng, không khẳng định các CHECK đơn giản đã đủ.

### Vì sao giữ version và migrated_from_version riêng?

**version** là phiên bản hiện tại của aggregate để phát hiện ghi cạnh tranh. **migrated_from_version** là lineage: bản nguồn được chụp khi lần đầu backfill. Sau cutover, version của Order có thể tăng; không được tiếp tục đồng bộ vô điều kiện từ legacy version cũ và ghi đè state mới.

**Mục tiêu không phải hai database cùng writable.** Trong giai đoạn dual-read hoặc catch-up, phải chỉ định **một nguồn có thẩm quyền**. Version giúp bảo vệ nhưng không thay được quyết định ai được quyền ghi ở từng giai đoạn.

## 6. Preflight: tìm lỗi cấu trúc trước khi ép JSON thành kiểu SQL

Việc JSON có dạng mảng không bảo đảm mọi phần tử đều là object có đủ field. Một document có quantity là chuỗi, giá âm hoặc lineNo vượt giới hạn INTEGER có thể khiến một lệnh CAST hàng loạt thất bại giữa chừng. Vì thế, đánh giá dữ liệu nên gồm **hai lượt**:

1. **Kiểm tra hình dạng và kiểu dữ liệu JSON**, số tiền là số nguyên trong phạm vi hỗ trợ, khóa định danh không thiếu.
2. **Sau khi an toàn để parse**, kiểm tra logic giữa các dòng, trạng thái, tổng tiền và trùng danh tính.

Ví dụ phát hiện field thiếu hoặc sai loại trước khi parse:

~~~sql
SELECT o.tenant_id, o.order_id,
       e.ordinality AS item_position,
       e.value AS suspicious_item
FROM sales.order_legacy AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.items_jsonb)
    WITH ORDINALITY AS e(value, ordinality)
WHERE jsonb_typeof(e.value) IS DISTINCT FROM 'object'
   OR jsonb_typeof(e.value -> 'lineNo')
        IS DISTINCT FROM 'number'
   OR jsonb_typeof(e.value -> 'skuId')
        IS DISTINCT FROM 'string'
   OR jsonb_typeof(e.value -> 'quantity')
        IS DISTINCT FROM 'number'
   OR jsonb_typeof(e.value -> 'unitPriceVnd')
        IS DISTINCT FROM 'number'
   OR jsonb_typeof(e.value -> 'discountPerUnitVnd')
        IS DISTINCT FROM 'number';
~~~

Trên sáu Order mẫu, truy vấn **không có kết quả** vì các lỗi được cài đặt là lỗi **logic**, không phải sai kiểu JSON. Đây chỉ là **kiểm tra cấp kiểu sơ bộ**; production còn phải kiểm tra số nguyên, phạm vi INTEGER/BIGINT, mã SKU rỗng, số lượng âm, độ dài mảng, tiền vượt phạm vi và schemaVersion nguồn. Ví dụ price JSON = 1.5 là number nhưng không phải đồng VND nguyên; không được cast rồi làm tròn ngầm.

**Không chạy bước parse khi còn item sai kiểu**, vì việc CAST trong truy vấn đánh giá có thể dừng toàn bộ lô. Trong pipeline thật, dữ liệu không đạt lượt 1 phải được đưa vào quarantine với lý do; chỉ dữ liệu an toàn mới sang lượt 2. Phần SQL tiếp theo **giả định đã đạt điều kiện parse** như đúng sáu record mẫu.

## 7. Đánh giá nghiệp vụ và phân loại hàng chuyển đổi

Thực hành tạo **một bảng tạm trong phiên làm việc** để snapshot kết quả phân loại. Khi làm với hệ thống đang nhận ghi, việc chỉ chạy một câu query bất kỳ trong lúc nguồn thay đổi **không tạo ra snapshot nhất quán cho toàn migration**; ở phần triển khai thực tế sẽ cần snapshot/cutoff và CDC.

~~~sql
-- Chạy trong phiên thử mới sau khi đã qua kiểm tra kiểu.
CREATE TEMP TABLE migration_assessment AS
WITH line_stats AS (
    SELECT o.tenant_id, o.order_id,
           COUNT(*) AS line_count,
           COUNT(DISTINCT i."lineNo") AS distinct_line_count,
           BOOL_AND(
               COALESCE(
                   i."lineNo" > 0
                   AND length(trim(i."skuId")) > 0
                   AND i."quantity" > 0
                   AND i."unitPriceVnd" >= 0
                   AND i."discountPerUnitVnd" >= 0
                   AND i."discountPerUnitVnd" <= i."unitPriceVnd"
                   AND trunc(i."unitPriceVnd") = i."unitPriceVnd"
                   AND trunc(i."discountPerUnitVnd")
                       = i."discountPerUnitVnd",
                   FALSE
               )
           ) AS valid_lines,
           SUM(i."quantity"::NUMERIC * i."unitPriceVnd")
               AS gross_numeric,
           SUM(i."quantity"::NUMERIC * i."discountPerUnitVnd")
               AS discount_numeric
    FROM sales.order_legacy AS o
    CROSS JOIN LATERAL jsonb_to_recordset(o.items_jsonb) AS i(
        "lineNo" INTEGER,
        "skuId" TEXT,
        "quantity" BIGINT,
        "unitPriceVnd" NUMERIC,
        "discountPerUnitVnd" NUMERIC
    )
    GROUP BY o.tenant_id, o.order_id
),
assessed AS (
    SELECT o.*,
           COALESCE(s.line_count, 0)::BIGINT AS line_count,
           COALESCE(s.distinct_line_count, 0)::BIGINT
               AS distinct_line_count,
           COALESCE(s.valid_lines, FALSE) AS valid_lines,
           COALESCE(s.gross_numeric, 0)::NUMERIC AS gross_numeric,
           COALESCE(s.discount_numeric, 0)::NUMERIC
               AS discount_numeric
    FROM sales.order_legacy AS o
    LEFT JOIN line_stats AS s
      ON s.tenant_id = o.tenant_id
     AND s.order_id = o.order_id
)
SELECT a.*,
       a.gross_numeric - a.discount_numeric AS payable_numeric,
       CASE
           WHEN a.status = 'CONFIRMED' AND a.line_count = 0
               THEN 'EMPTY_CONFIRMED'
           WHEN a.line_count > 0 AND NOT a.valid_lines
               THEN 'INVALID_LINE'
           WHEN a.line_count <> a.distinct_line_count
               THEN 'DUPLICATE_LINE_NO'
           WHEN a.gross_numeric > 9223372036854775807::NUMERIC
             OR a.discount_numeric > 9223372036854775807::NUMERIC
             OR a.gross_numeric - a.discount_numeric
                   > 9223372036854775807::NUMERIC
               THEN 'AMOUNT_OVERFLOW'
           WHEN a.gross_numeric - a.discount_numeric
                    IS DISTINCT FROM a.total_vnd
               THEN 'AMOUNT_MISMATCH'
           ELSE 'OK'
       END AS verdict
FROM assessed AS a;

SELECT order_id, status, line_count, distinct_line_count,
       gross_numeric, discount_numeric, payable_numeric,
       total_vnd, verdict
FROM migration_assessment
ORDER BY order_id;
~~~

**Giải thích cơ chế:**

- LEFT JOIN giữ **Order rỗng** trong kết quả. Nếu dùng INNER JOIN vào phần tử JSON, O105 sẽ biến mất và migration có thể báo thiếu ít hơn thực tế.
- COUNT(DISTINCT lineNo) phát hiện O104 có 2 dòng nhưng chỉ 1 lineNo khác nhau.
- Dùng NUMERIC ở bước tổng tiền để quan sát dữ liệu vượt BIGINT trước khi ghi vào đích. Kiểu đích là BIGINT; trường hợp tổng vượt phạm vi phải được quarantine thay vì để CAST thất bại giữa batch.
- Với DRAFT rỗng và totalVnd=0, rule hiện tại cho phép; nếu DRAFT rỗng mà totalVnd khác 0 sẽ bị AMOUNT_MISMATCH.
- BOOL_AND trên ít nhất một dòng kiểm tra điều kiện từng dòng; COALESCE(FALSE) không cho null biến thành bản ghi hợp lệ.

**Kết quả kỳ vọng:**

| Order | line_count | distinct_line_count | payable tính lại | verdict |
| --- | ---: | ---: | ---: | --- |
| O100 | 2 | 2 | 310.000 | OK |
| O101 | 1 | 1 | 120.000 | OK |
| O102 | 1 | 1 | 255.000 | OK |
| O103 | 2 | 2 | 200.000 | AMOUNT_MISMATCH |
| O104 | 2 | 1 | 25.000 | DUPLICATE_LINE_NO |
| O105 | 0 | 0 | 0 | EMPTY_CONFIRMED |

Nếu kết quả khác, không tiếp tục backfill. Trước hết kiểm tra fixture, logic tính và quy tắc nghiệp vụ. **Điều kiện kiểm tra** cần được giữ trong mã kiểm thử/version control, không chỉ đọc bằng mắt một lần rồi bỏ.

### Phạm vi của ví dụ assessment

Bảng tạm phía trên **không phải một công cụ làm sạch JSON tổng quát**: jsonb_to_recordset đòi dữ liệu parse được và lineNo trong miền INTEGER, quantity trong BIGINT. Vì vậy preflight kiểu và phạm vi phải chạy trước, hoặc pipeline production cần cơ chế parse từng record có bắt lỗi và quarantine riêng. Một Order có nhiều lý do lỗi có thể được báo **một verdict ưu tiên** theo thứ tự CASE; nên lưu thêm danh sách nguyên nhân đầy đủ khi điều tra thực tế.

## 8. Quarantine: giữ bản ghi lỗi có danh tính và lý do

Không nên có hai lựa chọn cực đoan là **sửa bừa để qua CHECK** hoặc **bỏ qua và không ai biết**. Hệ thống cần danh sách ngoại lệ, số lượng, mức độ ảnh hưởng, người quyết định và trạng thái xử lý.

~~~sql
CREATE TABLE sales.order_migration_reject (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    evaluated_source_version BIGINT NOT NULL,
    reason_code TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_total_vnd BIGINT,
    computed_payable_numeric NUMERIC,
    source_line_count BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, order_id, evaluated_source_version)
);

INSERT INTO sales.order_migration_reject (
    tenant_id, order_id, evaluated_source_version,
    reason_code, source_total_vnd, computed_payable_numeric,
    source_line_count
)
SELECT tenant_id, order_id, version, verdict,
       total_vnd, payable_numeric, line_count
FROM migration_assessment
WHERE verdict <> 'OK'
ON CONFLICT (tenant_id, order_id, evaluated_source_version)
DO UPDATE
SET reason_code = EXCLUDED.reason_code,
    source_total_vnd = EXCLUDED.source_total_vnd,
    computed_payable_numeric = EXCLUDED.computed_payable_numeric,
    source_line_count = EXCLUDED.source_line_count;

SELECT order_id, reason_code
FROM sales.order_migration_reject
WHERE tenant_id = 'T1'
ORDER BY order_id;
~~~

Trên fixture, bảng reject có ba dòng: O103, O104, O105. Khóa (tenant, order, sourceVersion) giúp chạy lại cùng đánh giá không nhân bản một lỗi. **Không tự cập nhật dữ liệu nguồn** trong câu INSERT này.

Trong sản phẩm thật, một nguồn có thể được đánh giá nhiều lần **ở cùng version** bởi rule mới; nếu cần lịch sử phân loại không mất, dùng thêm **assessmentRunId hoặc bản ghi audit bất biến**. Bảng ví dụ chỉ giữ trạng thái mới nhất cho cùng source version vì mục tiêu là thực hành một batch.

### Quy trình xử lý ba lỗi

| Order | Hành động **không được** làm | Điều cần điều tra |
| --- | --- | --- |
| O103 — lệch 1 VND | Tự đổi source total sang 200.000 hoặc tự tăng đơn giá một dòng thêm 1 | Có rounding/thuế/khuyến mại legacy? Hợp đồng tổng tiền cũ thật sự là gì? |
| O104 — trùng lineNo | Tự đổi lineNo thứ hai thành 2 mà không có chứng cứ | lineNo có thật là ID nghiệp vụ hay chỉ là vị trí mảng? Có hoạt động trả hàng tham chiếu lineNo cũ không? |
| O105 — CONFIRMED rỗng | Tự gắn một dòng giá 0 để qua CHECK, hoặc bỏ đơn khỏi lịch sử | Đây là đơn dịch vụ đặc biệt, đơn bị xóa dòng do lỗi, hay dữ liệu hỏng? |

**Chủ nghiệp vụ** và owner của Sales phải xác nhận cách xử lý. Có thể phục hồi dữ liệu từ audit, sự kiện, hóa đơn, đối soát Payment hoặc dữ liệu khách hàng; mỗi correction cần evidence, người phê duyệt và mốc hiệu lực. Nếu chưa đủ dữ kiện, giữ quarantine và báo cáo **coverage chưa đầy đủ**, không coi toàn bộ 6/6 đã chuyển.

Quarantine phải hạn chế quyền và retention như nguồn. Không đưa PII hoặc toàn bộ JSON chứa thông tin khách vào log rộng rãi chỉ để tiện debug; có thể lưu mã lỗi, hash/ID và truy vết tới bản nguồn có quyền kiểm soát.

## 9. Backfill: chuyển các bản ghi OK trong một transaction

Điều kiện của phần lab: mọi ghi vào nguồn được **tạm dừng** trong lúc chụp assessment và backfill, nên bảng tạm tương ứng với một snapshot đủ nhất quán. Phần rollout ở các mục sau xử lý yêu cầu không thể dừng ghi.

Mục tiêu: chép chính xác **ba Order OK**, cùng các dòng, totals, status, version và timestamps. Không làm thay đổi ba Order lỗi. Để minh họa tính **chạy lại không nhân bản**, dùng khóa đích và ON CONFLICT DO NOTHING, rồi **bắt buộc đối soát** vì bỏ qua conflict không chứng minh bản hiện có khớp nguồn.

~~~sql
BEGIN;

-- 1. Header: lấy tiền đã tính trong assessment,
-- bằng số tiền source khi verdict=OK.
INSERT INTO sales.order_header (
    tenant_id, order_id, customer_id, status, currency_code,
    gross_total_vnd, discount_total_vnd, payable_total_vnd,
    version, migrated_from_version, created_at, confirmed_at
)
SELECT tenant_id, order_id, customer_id, status, currency_code,
       gross_numeric::BIGINT, discount_numeric::BIGINT,
       payable_numeric::BIGINT,
       version, version, created_at, confirmed_at
FROM migration_assessment
WHERE verdict = 'OK'
ON CONFLICT (tenant_id, order_id) DO NOTHING;

-- 2. Từng line: chỉ từ snapshot đã được đánh giá OK.
INSERT INTO sales.order_line (
    tenant_id, order_id, line_no, sku_id,
    quantity, unit_price_vnd, discount_per_unit_vnd
)
SELECT a.tenant_id, a.order_id,
       i."lineNo", i."skuId",
       i."quantity", i."unitPriceVnd"::BIGINT,
       i."discountPerUnitVnd"::BIGINT
FROM migration_assessment AS a
JOIN sales.order_header AS h
  ON h.tenant_id = a.tenant_id
 AND h.order_id = a.order_id
 AND h.version = a.version
 AND h.migrated_from_version = a.version
CROSS JOIN LATERAL jsonb_to_recordset(a.items_jsonb) AS i(
    "lineNo" INTEGER,
    "skuId" TEXT,
    "quantity" BIGINT,
    "unitPriceVnd" NUMERIC,
    "discountPerUnitVnd" NUMERIC
)
WHERE a.verdict = 'OK'
ON CONFLICT (tenant_id, order_id, line_no) DO NOTHING;

COMMIT;
~~~

Đặt cùng transaction giúp tránh trạng thái **header đã vào đích nhưng line chưa vào** do lỗi trong chính lô. Với dataset nhỏ, một transaction là đủ; trong môi trường có hàng triệu đơn, chia lô theo **Order root**, bảo đảm mỗi Order và toàn bộ lines của nó thuộc **một transaction**, checkpoint theo business key và đối soát từng lô.

### Tại sao ON CONFLICT DO NOTHING không đủ?

Nếu đã có một target line cùng (tenant,order,lineNo) nhưng giá bị sai, câu INSERT có thể **không báo lỗi**. Không thể từ "script chạy xong" suy ra kết quả đúng. Vì thế:

- Sau mỗi batch, đối chiếu **số Order, số line, chi tiết từng dòng, tổng tiền và version**.
- Bất kỳ conflict không cùng payload phải được báo là **data drift**, chặn cutover và điều tra.
- Không dùng ON CONFLICT DO UPDATE vô điều kiện từ legacy sau khi target đã nhận command mới. Nếu sourceVersion cũ ghi đè targetVersion mới, đó là **lost update do migration**.

Trong triển khai không có thời gian dừng ghi, assessment snapshot và transaction ghi đích phải kết hợp **CDC/replay theo version hoặc high-watermark**. Những câu SQL trên chỉ giải quyết **backfill trạng thái tại một mốc**, không phải tự động đồng bộ nguồn liên tục.

## 10. Đối soát lớp 1: coverage, số hàng và tổng tiền

**Không chỉ kiểm tra source count = target count**, vì nguồn có ba bản được quarantine. Trước hết phải định nghĩa **tập nguồn đủ điều kiện** và **tập ngoại lệ**:

~~~sql
-- Một Order thuộc đúng một nhóm đánh giá trong snapshot.
SELECT verdict,
       COUNT(*) AS order_count,
       SUM(line_count) AS source_line_count,
       SUM(payable_numeric) AS source_payable_numeric
FROM migration_assessment
GROUP BY verdict
ORDER BY verdict;

-- Coverage ở mức Order và số dòng đích, theo tenant lab T1.
SELECT
  (SELECT COUNT(*) FROM migration_assessment
   WHERE verdict = 'OK') AS expected_orders,
  (SELECT COUNT(*) FROM sales.order_header
   WHERE tenant_id = 'T1') AS actual_orders,
  (SELECT COALESCE(SUM(line_count),0)
   FROM migration_assessment
   WHERE verdict = 'OK') AS expected_lines,
  (SELECT COUNT(*) FROM sales.order_line
   WHERE tenant_id = 'T1') AS actual_lines;

-- Tổng tiền chuyển được (không cộng các Order đã quarantine).
SELECT COUNT(*) AS target_orders,
       SUM(gross_total_vnd) AS gross_vnd,
       SUM(discount_total_vnd) AS discount_vnd,
       SUM(payable_total_vnd) AS payable_vnd,
       SUM(payable_total_vnd)
           FILTER (WHERE status = 'CONFIRMED')
           AS confirmed_payable_vnd
FROM sales.order_header
WHERE tenant_id = 'T1';
~~~

Kỳ vọng cho môi trường thử chưa có dữ liệu khác:

| Chỉ số | Kết quả mong đợi |
| --- | ---: |
| Source Orders | 6 |
| Source OK | 3 |
| Source Quarantine | 3 |
| Target Orders | **3** |
| Target OrderLines | **4** |
| Target gross | **720.000 VND** |
| Target discount | **35.000 VND** |
| Target payable | **685.000 VND** |
| Target CONFIRMED payable | **565.000 VND** |

Lưu ý query GROUP BY verdict có thể hiển thị tổng payable cho nhóm lỗi, nhưng **số đó không được coi là số tiền hợp lệ của đích**. O103 sai 1 VND; chính vì thế phải giữ số nguồn và số tính lại **ở hai cột khác nhau**, không trộn vào một metric chỉ để dashboard trông khớp.

### Tỷ lệ coverage

Trong fixture, **coverage Order** là \(3/6=50\%\). Đây là con số cố ý thấp do ba bản ghi lỗi được cài đặt phục vụ bài tập, **không** phải một ngưỡng chấp nhận trong hệ thống thương mại. Trong thực tế, mốc cutover phải có chính sách rõ về dữ liệu bị cách ly, bao gồm có thể cần **100% với Order đang hoạt động**, ngay cả khi dữ liệu archive có xử lý ngoại lệ riêng.

**Một tổng số tiền khớp không chứng minh từng Order khớp**: hai sai lệch đối dấu có thể triệt tiêu nhau. Vì vậy cần đối soát tiếp ở hai lớp chi tiết.

## 11. Đối soát lớp 2 và 3: từng Order, từng dòng

### 11.1. Đối chiếu header với snapshot nguồn

~~~sql
SELECT a.order_id,
       a.status AS source_status,
       h.status AS target_status,
       a.total_vnd AS source_payable,
       h.payable_total_vnd AS target_payable,
       a.version AS source_version,
       h.version AS target_version
FROM migration_assessment AS a
LEFT JOIN sales.order_header AS h
  ON h.tenant_id = a.tenant_id AND h.order_id = a.order_id
WHERE a.verdict = 'OK'
  AND (
       h.order_id IS NULL
       OR h.customer_id IS DISTINCT FROM a.customer_id
       OR h.status IS DISTINCT FROM a.status
       OR h.currency_code IS DISTINCT FROM a.currency_code
       OR h.gross_total_vnd IS DISTINCT FROM a.gross_numeric
       OR h.discount_total_vnd IS DISTINCT FROM a.discount_numeric
       OR h.payable_total_vnd IS DISTINCT FROM a.total_vnd
       OR h.version IS DISTINCT FROM a.version
       OR h.created_at IS DISTINCT FROM a.created_at
       OR h.confirmed_at IS DISTINCT FROM a.confirmed_at
  );
~~~

Truy vấn phải **không trả dòng nào** khi target đúng snapshot. Vì dùng LEFT JOIN và IS DISTINCT FROM, nó vẫn phát hiện một Order đích thiếu hoặc NULL khác mong đợi. Cần kiểm tra thêm **target ngoài tập expected** (nếu đó không phải dữ liệu được ghi hợp lệ sau snapshot); chỉ so từ expected sang target sẽ bỏ sót bản ghi dư.

### 11.2. Đối chiếu line bằng business key

~~~sql
WITH expected_lines AS (
    SELECT a.tenant_id, a.order_id,
           i."lineNo" AS line_no,
           i."skuId" AS sku_id,
           i."quantity" AS quantity,
           i."unitPriceVnd"::BIGINT AS unit_price_vnd,
           i."discountPerUnitVnd"::BIGINT AS discount_per_unit_vnd
    FROM migration_assessment AS a
    CROSS JOIN LATERAL jsonb_to_recordset(a.items_jsonb) AS i(
        "lineNo" INTEGER, "skuId" TEXT, "quantity" BIGINT,
        "unitPriceVnd" NUMERIC, "discountPerUnitVnd" NUMERIC
    )
    WHERE a.verdict = 'OK'
),
target_lines AS (
    SELECT *
    FROM sales.order_line
    WHERE tenant_id = 'T1'
)
SELECT COALESCE(e.tenant_id, t.tenant_id) AS tenant_id,
       COALESCE(e.order_id, t.order_id) AS order_id,
       COALESCE(e.line_no, t.line_no) AS line_no,
       e.sku_id AS source_sku, t.sku_id AS target_sku,
       e.quantity AS source_qty, t.quantity AS target_qty
FROM expected_lines AS e
FULL OUTER JOIN target_lines AS t
  ON t.tenant_id = e.tenant_id
 AND t.order_id = e.order_id
 AND t.line_no = e.line_no
WHERE e.line_no IS NULL
   OR t.line_no IS NULL
   OR e.sku_id IS DISTINCT FROM t.sku_id
   OR e.quantity IS DISTINCT FROM t.quantity
   OR e.unit_price_vnd IS DISTINCT FROM t.unit_price_vnd
   OR e.discount_per_unit_vnd
        IS DISTINCT FROM t.discount_per_unit_vnd
ORDER BY 1,2,3;
~~~

Phải **không có dòng nào** trong phạm vi snapshot lab. FULL OUTER JOIN giúp tìm cả **dòng thiếu** và **dòng dư**. Ở production, nếu target đã có Order mới sau snapshot hoặc bao gồm nhiều tenant, cần giới hạn cả hai phía theo **cùng cohort và cutoff** để không gắn nhãn nhầm những dữ liệu mới hợp lệ là thừa.

### 11.3. Đối soát lại tổng từ chính bảng đích

~~~sql
WITH line_totals AS (
    SELECT tenant_id, order_id,
           COUNT(*) AS lines,
           SUM(quantity::NUMERIC * unit_price_vnd) AS gross,
           SUM(quantity::NUMERIC * discount_per_unit_vnd)
               AS discount
    FROM sales.order_line
    WHERE tenant_id = 'T1'
    GROUP BY tenant_id, order_id
)
SELECT h.order_id, h.status, h.payable_total_vnd,
       t.lines, t.gross, t.discount,
       t.gross - t.discount AS computed_payable
FROM sales.order_header AS h
LEFT JOIN line_totals AS t
  ON t.tenant_id = h.tenant_id AND t.order_id = h.order_id
WHERE h.tenant_id = 'T1'
  AND (
      (h.status = 'CONFIRMED' AND t.lines IS NULL)
      OR h.gross_total_vnd IS DISTINCT FROM COALESCE(t.gross,0)
      OR h.discount_total_vnd
           IS DISTINCT FROM COALESCE(t.discount,0)
      OR h.payable_total_vnd
           IS DISTINCT FROM COALESCE(t.gross - t.discount,0)
  );
~~~

Query cũng phải không trả dòng nào. Nó chứng minh **bản đích tự nhất quán** tại thời điểm quan sát, nhưng **chưa chứng minh bản đích có cùng ý nghĩa nguồn**: một migration sai nhưng cùng lúc sửa cả header và line có thể qua kiểm tra này. Vì vậy ba lớp cần phối hợp:

1. **Coverage và totals** trên tập dữ liệu được phép chuyển.
2. **So sánh theo từng Order và line** với snapshot có thẩm quyền.
3. **Bất biến nội bộ đích** và các ràng buộc vật lý.

Với dữ liệu quan trọng, lưu bằng chứng đối soát (runId, batchKey, sourceVersion/cutoff, số chênh lệch, số được cách ly, checksum có định nghĩa, người xác nhận) trong hệ thống quản trị migration. Không đưa những bằng chứng đó vào nhật ký chứa PII rộng quyền.

## 12. Nhánh thực hành tùy chọn: sửa dữ liệu lỗi **sau phê duyệt**

Mục 8 cố ý giữ ba Order trong quarantine. Để luyện quy trình sửa đúng, giả sử **chỉ trong môi trường lab**, nhóm nghiệp vụ đã kiểm tra audit và xác nhận:

1. O103 thực sự có tổng phải trả 200.000 VND; giá trị total_vnd=200.001 là lỗi nhập ở hệ thống cũ, không phải thuế/phí.
2. O104 chưa được dùng trong bất kỳ tham chiếu bên ngoài; lineNo chỉ là vị trí trong đơn DRAFT và dòng thứ hai phải có lineNo=2.
3. O105 là đơn từng bị hệ thống cũ đánh dấu CONFIRMED nhầm, không có giao dịch thật; trạng thái đúng là CANCELLED với số tiền 0. Các tác động đã phát ra bên ngoài (nếu có) phải được xử lý bằng quy trình correction/bù riêng.

**Không suy diễn ba quyết định trên từ hình dạng dữ liệu.** Trong production chúng là giả định **chỉ hợp lệ khi có bằng chứng và phê duyệt**. Một đơn CONFIRMED rỗng có thể là đơn dịch vụ không dùng line vật lý; khi đó **mô hình đích** phải được điều chỉnh hoặc có ngoại lệ được thiết kế rõ, không cưỡng ép chuyển thành CANCELLED.

### Sửa theo originalVersion và ghi audit

~~~sql
BEGIN;

-- CHỈ LAB, sau khi evidence xác nhận amount thật của O103.
UPDATE sales.order_legacy
SET total_vnd = 200000,
    version = version + 1
WHERE tenant_id = 'T1'
  AND order_id = 'O103'
  AND version = 2
  AND total_vnd = 200001;

-- O104: sau khi xác nhận lineNo không phải external reference.
UPDATE sales.order_legacy
SET items_jsonb = jsonb_set(
        items_jsonb, '{1,lineNo}', '2'::jsonb, FALSE
    ),
    version = version + 1
WHERE tenant_id = 'T1'
  AND order_id = 'O104'
  AND status = 'DRAFT'
  AND version = 1;

-- O105: chỉ khi nghiệp vụ xác nhận chưa từng có xác nhận thật.
UPDATE sales.order_legacy
SET status = 'CANCELLED',
    confirmed_at = NULL,
    version = version + 1
WHERE tenant_id = 'T1'
  AND order_id = 'O105'
  AND status = 'CONFIRMED'
  AND version = 2;

-- Trước COMMIT, xác minh mỗi UPDATE trả đúng một hàng.
-- Nếu bất kỳ lệnh nào trả 0: ROLLBACK và điều tra version/source.
COMMIT;
~~~

Đây là SQL minh họa thao tác sửa dữ liệu **được phê duyệt** trong lab; SQL riêng lẻ không tự ghi audit ai đã quyết định. Ở hệ thống thật, audit cần tham chiếu ticket/evidence/actor, trạng thái trước–sau và lý do; nếu correction làm thay đổi sự thật đã công bố, phải có hợp đồng thông báo/correction thích hợp. Không phát lại OrderConfirmed như thể đơn được xác nhận mới chỉ vì migration sửa một row.

Sau sửa, **đánh giá lại từ nguồn đã đổi**, không dùng bảng tạm migration_assessment được chụp **trước sửa**. Để giữ lịch sử lần đánh giá đầu, có thể giữ assessmentRunId và tạo snapshot đánh giá mới bằng đúng bộ quy tắc. Trong lab, tạo phiên mới hoặc dọn bảng tạm rồi chạy lại câu tạo assessment ở mục 7.

Kết quả mới **nếu cả ba giả định và ba UPDATE đều đúng**:

| Chỉ số | Trước correction | Sau correction |
| --- | ---: | ---: |
| OK source Order | 3 | **6** |
| Quarantine hiện tại | 3 | **0** |
| OrderLine có thể chuyển | 4 | **8** |
| Gross hợp lệ | 720.000 | **945.000** |
| Discount hợp lệ | 35.000 | **35.000** |
| Payable hợp lệ | 685.000 | **910.000** |
| Payable của Order CONFIRMED | 565.000 | **765.000** |

O103 đóng góp thêm 200.000 VND vào cohort CONFIRMED; O104 đóng góp 25.000 VND vào tổng toàn bộ nhưng vẫn DRAFT; O105 là CANCELLED không có dòng và không thêm tiền. **Đừng nhầm số 910.000 toàn bộ Order với 765.000 thuộc CONFIRMED.**

### Quarantine là lịch sử phát hiện, không phải cờ có thể xóa sạch

Bảng reject đã ghi lỗi của sourceVersion cũ. Khi nguồn được sửa và tăng version, các dòng lịch sử **vẫn có thể tồn tại** để truy vết. Báo cáo "quarantine hiện tại = 0" phải dựa trên **assessment mới**, không phải COUNT(*) trên toàn bảng reject lịch sử. Nếu muốn quản lý xử lý ngoại lệ, dùng trạng thái OPEN/RESOLVED với audit theo run/version, không xóa bằng chứng phát hiện lỗi rồi coi như dữ liệu luôn sạch.

## 13. Khi không thể dừng ghi: snapshot, CDC và catch-up

Trong production, hệ thống có thể tiếp nhận Order DRAFT trong thời gian backfill kéo dài nhiều giờ. Giải pháp "đọc toàn bảng, rồi chuyển quyền ghi" sẽ mất những thay đổi xảy ra sau thời điểm đọc trừ khi có cơ chế bắt lại.

### Sơ đồ chuyển đổi giữ một writer có thẩm quyền

~~~mermaid
sequenceDiagram
    participant W as Old Writer
    participant S as Legacy Source
    participant C as Change Log / CDC
    participant M as Migration Worker
    participant T as Normalized Target
    participant R as Reconciler

    W->>S: Ghi Order v5
    S->>C: Committed change với offset/LSN
    M->>S: Snapshot nhất quán tại watermark W0
    M->>T: Backfill các Order đủ điều kiện
    C->>M: Replay thay đổi sau W0
    M->>T: Apply theo Order + sourceVersion
    R->>S: Đọc nguồn cùng cutoff W1
    R->>T: Đọc target đã catch-up tới W1
    R-->>M: Coverage, detail, totals, lag, quarantine
~~~

**Điều kiện kỹ thuật phải đúng:** mốc snapshot và vị trí log/CDC phải **liên kết được với nhau** để không có khoảng trống giữa snapshot và luồng thay đổi. Chỉ ghi giờ đồng hồ lúc bắt đầu SELECT và nói "sau đó lấy event mới hơn" là không đủ, vì transaction có thể bắt đầu trước nhưng commit sau. Cách triển khai phụ thuộc PostgreSQL logical decoding, replication slot, snapshot protocol và công cụ CDC thực tế; phải kiểm chứng cấu hình, retention WAL và quyền truy cập.

### Các bước rollout phù hợp với nhiều phiên bản

1. **Expand:** thêm schema đích, constraint/index phù hợp; vẫn giữ nguồn cũ có thẩm quyền.
2. **Capture:** thiết lập kênh committed change có checkpoint và bảo vệ khoảng trống giữa snapshot/stream.
3. **Backfill:** chuyển từng Order nguyên vẹn theo sourceVersion; trường hợp lỗi chuyển vào quarantine, không ngăn luồng chung vô thời hạn nếu có chính sách riêng.
4. **Catch-up:** áp dụng thay đổi sau watermark; dedup, đúng thứ tự **trong phạm vi một Order**, và phân biệt correction với business event.
5. **Shadow read:** cùng một request đọc từ nguồn cũ và đích qua canonical mapper, so giá trị có ý nghĩa; chỉ một đường trả cho người dùng.
6. **Read switch:** chuyển dần read use cases nếu đối soát, quyền tenant, độ trễ và hiệu năng đạt điều kiện.
7. **Write cutover:** dùng một giao thức điều phối duy nhất xác định **đổi quyền ghi từ nguồn cũ sang đích**. Chặn/tắt old writer còn ghi nguồn, xử lý command đang bay và xác nhận không có lỗ hổng dữ liệu.
8. **Contract:** chỉ bỏ items_jsonb/source cũ khi mọi reader, writer, export, consumer và khả năng khôi phục đã được giải quyết.

### Áp dụng một Order update an toàn

Giả sử snapshot thấy O101 version=1; trong lúc backfill, old writer hợp lệ thêm một dòng và commit version=2. Target có thể đã nhận version=1. Một catch-up handler cần:

~~~text
Nhận committed change cho (tenant=T1, order=O101, version=2).

Nếu target sourceVersion=1:
    kiểm tra source v2 đủ dữ liệu, quyền và bất biến;
    trong một transaction, thay tập lines và totals của O101
    theo đúng v2, giữ ID của các dòng, tăng version sang 2;
    commit target state + checkpoint xử lý change.

Nếu target đã là sourceVersion=2:
    so payload/hash có nghĩa; nếu giống, dedup;
    nếu khác, báo drift, không tự chọn một bên.

Nếu target đang ở sourceVersion>2:
    không ghi đè bằng version 2;
    xử lý thứ tự/gap, đối chiếu theo nguồn có thẩm quyền.

Nếu source v2 không đạt validation:
    quarantine phiên bản v2 và dừng chuyển quyền ghi
    đối với Order liên quan theo chính sách.
~~~

Mô tả trên là **protocol**, không phải SQL UPSERT đơn giản. Việc thay toàn bộ lines phải giữ tính nguyên tử của Order và không xóa những changes **đã hợp lệ do target writer mới tạo sau cutover**. Trong giai đoạn source còn là writer, target nên là replica/projector; sau cutover, việc replay source cũ phải **bị chặn hoặc phân xử**.

### CDC không đồng nghĩa integration event

Một row UPDATE do backfill, sửa schema, hay tính lại cache không tự là **OrderConfirmed**. Nếu phát OrderConfirmed mỗi lần CDC thấy order_legacy thay đổi, Inventory có thể giữ hàng lần nữa. Cần tách **luồng sao chép trạng thái** khỏi **sự kiện miền**, và chỉ phát integration event khi business transition thực sự xảy ra tại nguồn có thẩm quyền.

## 14. Tách Java domain, persistence mapping và hợp đồng API

Một lỗi kiến trúc là để cùng một class Java được serialize sang JSONB, làm entity ORM, làm HTTP request và làm event. Sau migration, việc đổi storage có thể vô tình làm client mất trường hoặc được quyền ghi total/status.

Mô hình miền cần giữ **hành vi và bất biến** độc lập với cách lưu:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Line(int lineNo, String skuId, long quantity,
            long unitPriceVnd, long discountPerUnitVnd) {
    Line {
        Objects.requireNonNull(skuId);
        if (lineNo <= 0 || skuId.isBlank() || quantity <= 0
                || unitPriceVnd < 0 || discountPerUnitVnd < 0
                || discountPerUnitVnd > unitPriceVnd) {
            throw new IllegalArgumentException("Invalid line");
        }
    }
    long gross() {
        return Math.multiplyExact(quantity, unitPriceVnd);
    }
    long discount() {
        return Math.multiplyExact(quantity, discountPerUnitVnd);
    }
}

record Totals(long gross, long discount, long payable) {}
enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }

final class Order {
    private final String orderId;
    private final List<Line> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;
    private long version;

    Order(String orderId) {
        this.orderId = Objects.requireNonNull(orderId);
    }

    void addLine(Line line) {
        if (status != OrderStatus.DRAFT)
            throw new IllegalStateException("Order not editable");
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(l -> l.lineNo() == line.lineNo()))
            throw new IllegalArgumentException("Duplicate lineNo");
        var current = totals();
        Math.addExact(current.gross(), line.gross());
        Math.addExact(current.discount(), line.discount());
        lines.add(line);
        version++;
    }

    Totals totals() {
        long gross = 0, discount = 0;
        for (Line line : lines) {
            gross = Math.addExact(gross, line.gross());
            discount = Math.addExact(discount, line.discount());
        }
        return new Totals(
            gross, discount, Math.subtractExact(gross, discount));
    }

    void confirm() {
        if (status != OrderStatus.DRAFT || lines.isEmpty())
            throw new IllegalStateException("Cannot confirm");
        totals();
        status = OrderStatus.CONFIRMED;
        version++;
    }

    List<Line> lines() { return List.copyOf(lines); }
    long version() { return version; }
    OrderStatus status() { return status; }
}
~~~

Đây là Java 17 **rút gọn** để minh họa rule; nó chưa có factory phục hồi dữ liệu, tenant scope, các command idempotency hay tích hợp Payment/Inventory. **Repository thực tế** cần một đường restore có kiểm soát để đặt status/version và lines theo dữ liệu đã commit, **không gọi lại addLine/confirm để nạp lịch sử**, vì sẽ tăng version và tạo tác động giả.

Trong giai đoạn chuyển đổi:

- **LegacyOrderRepository:** đọc items_jsonb và ánh xạ thành các Line miền đã kiểm tra.
- **NormalizedOrderRepository:** đọc header/line, dựng cùng Order miền và kiểm tra totals.
- **OrderCommandService:** giữ quyền auth/tenant, expectedVersion, state transition; chỉ writer có thẩm quyền được lưu.
- **OrderViewMapper:** tạo HTTP response theo contract, không đưa table/row_version hoặc JSONB thô ra ngoài chỉ vì storage có chúng.
- **EventMapper:** phát đúng integration event có schemaVersion khi business transition đã commit.

Với một request đọc, cả hai repository cần trả cùng **canonical OrderView** theo contract. Ví dụ Order O100 luôn trả payable=310.000 VND và hai lines, bất kể dữ liệu nằm trong JSONB hay bảng normalized. Các field mới như gross/discount có thể thêm theo chính sách API riêng; **migration storage không bắt buộc client thay đổi cùng lúc**.

### Event và backfill là hai loại thay đổi

Một Order CONFIRMED từ tuần trước được copy từ legacy sang đích **không vừa được confirm lần nữa**. Vì vậy migration **không phát OrderConfirmed mới** cho mỗi bản ghi được chép. Nếu Analytics cần rebuild, dùng luồng snapshot/CDC hoặc một event backfill có semantic riêng và ID/lineage ổn định để nạp, không làm Notification/Inventory tưởng có đơn mới.

Nếu sau cutover một command thật sự confirm Order, hãy ghi **state + outbox trong cùng transaction** với cùng eventId khi relay retry. Sự kiện có occurredAt từ nghiệp vụ, không phải thời điểm migration hoặc CDC nhận dữ liệu.

## 15. Đối soát báo cáo và downstream projection

Nhóm phân tích đang có báo cáo **số đơn đã xác nhận và số tiền theo SKU**. Sau khi chuyển từ JSONB sang bảng quan hệ, phải chứng minh **cùng cohort, cùng định nghĩa và cùng thời điểm**, không chỉ chứng minh bảng mới có dữ liệu.

Giả sử mỗi Order CONFIRMED có snapshot lines hợp lệ và chưa có nghiệp vụ xác nhận từng phần. Có thể dùng fact với grain:

> **Một fact row = một OrderLine đã xác nhận thuộc một Order, trong tenant cụ thể**, với snapshot giá, giảm giá và thời điểm xác nhận.

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.fact_confirmed_order_line (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    sku_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    business_date DATE NOT NULL,
    quantity BIGINT NOT NULL CHECK (quantity > 0),
    gross_vnd BIGINT NOT NULL CHECK (gross_vnd >= 0),
    discount_vnd BIGINT NOT NULL CHECK (discount_vnd >= 0),
    net_vnd BIGINT NOT NULL CHECK (net_vnd >= 0),
    source_order_version BIGINT NOT NULL,
    transform_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    CHECK (discount_vnd <= gross_vnd),
    CHECK (gross_vnd - discount_vnd = net_vnd)
);
~~~

Trên fixture **chưa correction**, tập Order OK chỉ gồm O100, O101, O102; O101 vẫn DRAFT. Do đó fact confirmed có **ba dòng**: hai dòng O100 và một dòng O102. Query trên đích normalized:

~~~sql
SELECT l.sku_id,
       SUM(l.quantity) AS units,
       SUM(l.quantity::NUMERIC * l.unit_price_vnd) AS gross,
       SUM(l.quantity::NUMERIC * l.discount_per_unit_vnd)
           AS discount,
       SUM(l.quantity::NUMERIC *
           (l.unit_price_vnd - l.discount_per_unit_vnd))
           AS net
FROM sales.order_header AS h
JOIN sales.order_line AS l
  ON l.tenant_id = h.tenant_id AND l.order_id = h.order_id
WHERE h.tenant_id = 'T1'
  AND h.status = 'CONFIRMED'
GROUP BY l.sku_id
ORDER BY l.sku_id;
~~~

Kỳ vọng:

| SKU | Số đơn vị | Gross | Discount | Net |
| --- | ---: | ---: | ---: | ---: |
| A | 2 | 240.000 | 20.000 | **220.000** |
| B | 4 | 360.000 | 15.000 | **345.000** |
| **Tổng** | **6** | **600.000** | **35.000** | **565.000** |

**Quy tắc đối soát BI:** với cùng tenant, business date/cutoff, trạng thái và schema/transform version, tổng net của fact confirmed phải khớp tổng payable của các Order CONFIRMED **thuộc tập đã chuyển thành công**. Không so 565.000 với tổng nguồn bao gồm O103 lỗi rồi gọi chênh lệch là do database mới. Cần nhãn hoặc metadata **coverage/quarantine** để người xem không hiểu nhầm số tạm là đầy đủ.

**OrderConfirmed không đồng nghĩa PaymentCaptured.** Nếu câu hỏi là **doanh thu đã thu**, cần nguồn Payment có thẩm quyền, xử lý failed attempt, partial capture, refund, currency và policy ghi nhận. Không dùng status CONFIRMED để thay thế định nghĩa tiền đã thu hoặc doanh thu kế toán.

### Bẫy thay grain khi chuyển schema

Nếu một Order có hai lines và hai PaymentAttempt, JOIN cả ba nguồn rồi SUM line net sẽ có thể nhân tiền theo số attempt. Muốn số Order thì COUNT(DISTINCT order_id) theo grain và cohort phù hợp; muốn số lượng hàng thì SUM(quantity); muốn số tiền thu thì cần fact capture/allocation có grain riêng.

Nếu Analytics từng lấy trực tiếp JSONB, có thể thay adapter để đọc bảng normalized nhưng **giữ semantic model và metric version** nếu ý nghĩa không đổi. Nếu đồng thời thay policy tính ngày hoặc trạng thái, đó là **một thay đổi KPI khác** phải được duyệt và thông báo độc lập.

## 16. Hiệu năng và kích thước: backfill không được phá OLTP

Giả sử môi trường thật có **5 triệu Order, trung bình 8 lines/Order**. Số line logic là khoảng **40 triệu**, chưa kể audit, outbox và bản ghi lỗi. Không nên một transaction bao toàn bộ 5 triệu Order rồi chạy trong giờ cao điểm.

| Nguy cơ | Điều có thể xảy ra | Kiểm soát |
| --- | --- | --- |
| Transaction quá lớn | Lock, WAL, timeout, rollback lâu | Chia batch theo (tenant,order), commit từng Order/lô có kích thước giới hạn |
| Backfill quét JSONB liên tục | CPU/I/O tăng, ảnh hưởng latency checkout | Giới hạn throughput và đo p95/p99 cùng tải |
| Tạo index khối lượng lớn | Tốn disk/temp, có thể ảnh hưởng ghi | Kiểm tra phương án build index phù hợp engine và thời gian triển khai |
| CDC lag | WAL/log bị giữ, target ngày càng tụt hậu | Theo dõi offset/lag, giới hạn backfill, cơ chế catch-up |
| Dữ liệu lỗi nhiều | Quarantine phình to, coverage chậm đạt | Phân loại theo reason, owner và quy trình xử lý |
| UPSERT không có version guard | Record cũ ghi đè record mới | Conditional update theo version, một writer có thẩm quyền |
| Reconciliation full scan | Tốn I/O lớn, làm nóng dữ liệu không cần | Đối soát theo batch/key, sampling chỉ bổ trợ không thay kiểm tra quan trọng |
| Dữ liệu nhạy cảm trong log | Lộ thông tin khi debug | Ghi ID/mã lỗi/summary với quyền hạn phù hợp |

### Một thuật toán batch an toàn ở mức Order

~~~text
checkpoint = (lastTenantId, lastOrderId, sourceWatermark)

while còn Order đủ điều kiện trong snapshot:
    lấy N Order tiếp theo theo keyset ổn định;
    phân loại theo rule versioned;
    với từng Order OK:
        BEGIN target transaction
        ghi header + toàn bộ lines theo version nguồn
        verify số line, giá trị, state tại mốc đó
        COMMIT
    với Order lỗi:
        ghi quarantine có version, lý do, owner
    đối soát tổng batch và lưu kết quả
    chỉ sau khi batch đã durable mới lưu checkpoint

sau snapshot:
    apply committed changes từ CDC bắt đầu ở watermark an toàn;
    chờ lag < ngưỡng được duyệt;
    đối soát lại tại cùng cutoff;
    mới xem xét read/write cutover
~~~

Độ lớn N không nên đoán từ một hằng số đẹp. Hãy thử với p95 latency nguồn, lock wait, WAL, kích thước Order và tốc độ CDC thực tế. Một Order cực lớn có thể cần xử lý riêng; nhưng phải giữ tính nhất quán **toàn aggregate** thay vì chia nó làm hai transaction rồi cho user đọc nửa đơn đã chuyển.

### Những gì cần quan sát

- Source read latency, transaction lock wait, deadlock và tỷ lệ timeouts.
- Batch throughput (Orders/s, Lines/s), source/target disk usage, WAL/CDC retention.
- Số Order đã đánh giá, OK, quarantined, migrated, verified; không trộn các trạng thái.
- Số dòng mismatch, số tiền mismatch và số Order lệch phiên bản theo batch.
- CDC lag theo offset và độ trễ thời gian, retry count và lỗi ghi target.
- Tỷ lệ read discrepancy khi shadow read và p95/p99 trước–sau switch.
- Tỷ lệ event duplicate/outbox pending và số lần chuyển trạng thái bị conflict.

Một benchmark có số liệu thật cần ghi phiên bản PostgreSQL, tài nguyên, index, độ lớn dữ liệu và workload. Bài viết **không khẳng định đã chạy các truy vấn hay benchmark**; SQL là mẫu để thực hiện trên môi trường kiểm thử.

## 17. Kế hoạch rollback và roll-forward theo giai đoạn

Rollback một migration **trước khi có dữ liệu mới** khác rollback **sau khi đã đổi writer**. Cần lập kế hoạch trước khi bật tính năng.

| Giai đoạn | Nguồn ghi có thẩm quyền | Có thể quay lại thế nào? | Điều phải tránh |
| --- | --- | --- | --- |
| Expand, mới tạo bảng đích | Legacy | Dừng backfill, giữ source | DROP schema khi job còn chạy |
| Backfill, target chỉ là bản sao | Legacy | Tắt projector, đọc nguồn cũ | Dùng target chưa verified làm source thật |
| Read switch, write còn legacy | Legacy | Chuyển read về legacy, sửa projector | Giả vờ shadow mismatch là không quan trọng |
| Đang cutover write | Cần cơ chế phân xử rõ | Tạm dừng ghi, đối chiếu in-flight, roll-forward/hotfix nếu cần | Cho hai writer cùng nhận command không đồng bộ |
| Target đã nhận write mới | Target | Ưu tiên roll-forward hoặc chuyển ngược có quy trình migration đối soát riêng | Khởi động old writer và ghi đè dữ liệu mới bằng legacy |
| Contract bỏ schema cũ | Target | Restore qua backup/transform được chuẩn bị trước | Tin DROP TABLE có rollback bằng Git |

**Rủi ro khó đảo ngược:** target có thể có các cột, trạng thái hoặc line được tạo sau cutover mà legacy items_jsonb không biểu diễn được hoặc old binary không biết. Khi ấy "deploy lại phiên bản cũ" có thể làm **mất dữ liệu/ngữ nghĩa**. Tạm chặn write hoặc roll-forward là lựa chọn an toàn hơn rollback tự động.

### Điều kiện trước khi xóa legacy

1. Mọi read/write, batch, export, script quản trị đã chuyển và được kiểm chứng.
2. Consumer API/event và Analytics không còn phụ thuộc trực tiếp items_jsonb.
3. Quarantine hiện tại đã được xử lý hoặc có chính sách hợp lệ về những bản không thể chuyển.
4. Backup/restore và replay đã được thử, không chỉ có file backup tồn tại.
5. Bằng chứng đối soát cuối cùng có cutoff, version, owner phê duyệt.
6. Không còn CDC/catch-up job cần đọc legacy và retention/audit được giải quyết.

**Git commit chứa DROP COLUMN không phải bằng chứng điều kiện trên đã đạt.** Trạng thái triển khai cần được xác nhận từ migration history, schema thực tế, app release và các pipeline phụ thuộc.

## 18. Bộ kiểm thử bắt buộc của thay đổi mô hình

| Nhóm | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| Schema nguồn | JSONB mảng có field thiếu, sai kiểu, số quá lớn | Phân loại/quarantine trước CAST |
| Dữ liệu mẫu | O100–O102 | Verdict OK, tiền đúng |
| Sai tổng | O103 | AMOUNT_MISMATCH, không bị sửa ngầm |
| Trùng khóa line | O104 | DUPLICATE_LINE_NO |
| Empty confirmed | O105 | EMPTY_CONFIRMED |
| PK/FK/CHECK | Thêm line trùng PK, quantity=0, discount > unitPrice | Đích từ chối ở constraint phù hợp |
| Backfill chạy lại | Chạy hai lần cùng snapshot | Không nhân Order/Line, mọi trường vẫn khớp |
| Backfill lỗi giữa transaction | INSERT line thất bại sau header | Rollback cả Order thuộc transaction |
| Phục hồi domain | Restore Order CONFIRMED từ bảng đích | Không gọi lại confirm hoặc phát event mới |
| Version | Legacy update v2 sau snapshot v1 | Apply hợp lệ theo thứ tự, không ghi đè bản mới |
| Concurrent commands | Hai worker sửa cùng Order version | Một update thắng, request khác conflict |
| Tenant isolation | T2 cố đọc/ghi O100 của T1 | Bị từ chối, không rò giá/đơn |
| Reconciliation | Thay giá một line đích 1 VND trong môi trường test | Query theo line và totals phát hiện |
| Event replay | Relay phát lại OrderConfirmed cùng eventId | Consumer không xử lý hai business effects |
| Event vs backfill | Chép Order đã CONFIRMED từ legacy | Không phát lại OrderConfirmed như sự kiện mới |
| Analytics | Order có hai line, Payment có hai attempt | Không nhân doanh thu do JOIN sai |
| Cutover | Old/new binary cùng tồn tại lúc switch | Không có hai writer không điều phối |
| Rollback | Target đã ghi dữ liệu mới không có trong legacy | Có phương án bảo toàn trước khi đổi binary |
| Dữ liệu lớn | Order có rất nhiều line | Không vượt giới hạn batch/transaction đã công bố |

### Đối soát có điều kiện PASS/FAIL, không chỉ biểu đồ đẹp

Nên tự động hóa các cổng:

~~~text
assert evaluated_orders = ok_orders + quarantined_orders
assert target_orders_for_snapshot = ok_orders
assert target_lines_for_snapshot = SUM(ok_source.line_count)
assert header_differences_for_snapshot = 0
assert line_differences_for_snapshot = 0
assert target_internal_amount_mismatch = 0
assert target_conflict_unresolved = 0
assert consumer_schema_contract_tests = PASS
assert historical_migration_replayed_as_new_event = 0
~~~

Ở production, các biến và phạm vi phải gắn **tenant, snapshot watermark, sourceVersion, batch/runId**. Nếu source phát sinh Order mới sau cutoff, không đưa chúng vào target_orders_for_snapshot khi đối soát snapshot. **So với tập dữ liệu không cùng mốc rồi thấy lệch không nhất thiết là lỗi**, nhưng hệ thống phải có cách chứng minh phần lệch thuộc dữ liệu đến muộn hay thuộc lỗi thật.

## 19. Bộ bài tập giao nộp

Hãy làm **trên database thử**, dùng fixture của mục 4. Ghi các quyết định nghiệp vụ còn thiếu như **giả định**, không tự bịa kết quả quan sát hoặc bỏ qua hàng lỗi. Đầu ra nên là một tài liệu thiết kế ngắn cùng truy vấn/bảng kết quả và mô tả kiểm thử.

### Phần A — mô hình và chuyển đổi

**Bài 1. Grain và danh tính.** Mô tả grain của order_legacy, order_header, order_line. Vì sao lineNo không thể là PK duy nhất toàn database? Một FK từ line đến header phải chứa tenantId không? Vì sao?

**Bài 2. Bảo vệ bất biến.** Tạo ma trận cho các điều kiện quantity>0, discount<=price, tổng tiền header khớp lines, Order CONFIRMED không rỗng, không sửa line của Order CONFIRMED. Chỉ rõ điều kiện được PK/FK/CHECK bảo vệ và điều kiện phải cần transaction/domain.

**Bài 3. Tính tay dữ liệu mẫu.** Không nhìn vào bảng đáp án, tính gross, discount, payable từng Order, tổng ba Order hợp lệ, tổng hai Order CONFIRMED hợp lệ, số lines được chấp nhận. Chỉ ra hàng nào phải quarantine và lý do.

**Bài 4. Kiểm tra cấu trúc.** Một phần tử JSONB có unitPriceVnd là chuỗi "120000", hoặc một số lớn hơn BIGINT. Preflight ở mục 6 có phát hiện đủ cả hai trường hợp không? Cần bổ sung quy tắc nào trước parse?

**Bài 5. Backfill và chạy lại.** Hãy thực hiện SQL ở các mục 5–9 trên bản thử sạch. Chạy lại phần backfill từ cùng assessment. Điều gì phải giữ nguyên? Nếu một row đích đã có cùng key nhưng unitPriceVnd sai 1 VND, ON CONFLICT DO NOTHING có báo lỗi không?

### Phần B — đối soát và sửa dữ liệu

**Bài 6. Ba lớp đối soát.** Viết/giải thích query kiểm đếm, đối chiếu header và FULL OUTER JOIN dòng. Vì sao tổng tiền toàn bộ bằng nhau vẫn không chứng minh dữ liệu đúng?

**Bài 7. Quarantine.** O103 lệch 1 VND, O104 trùng lineNo, O105 CONFIRMED rỗng. Hãy đề xuất bằng chứng cần có trước khi sửa; dữ liệu sau correction sẽ được đánh giá lại thế nào?

**Bài 8. Sai khác cố ý.** Trong database thử, sửa một unit_price_vnd của một OrderLine đích khác nguồn sau khi đã tắt đường ghi ứng dụng. Kiểm tra nào phát hiện, kiểm tra nào có thể không phát hiện? Phải khôi phục như thế nào?

**Bài 9. Báo cáo phân tích.** Từ tập ba Order OK, lập bảng net theo SKU và số Order CONFIRMED. Có được lấy tổng 685.000 VND làm doanh thu đã thu không? Nếu có hai PaymentAttempt cho O100, việc JOIN sai sẽ ảnh hưởng thế nào?

### Phần C — triển khai, kiến trúc và vận hành

**Bài 10. Thay đổi trong lúc backfill.** Snapshot O101 version=1, nguồn nhận thêm một line và commit version=2, sau đó event v2 đến trước một retry v1. Vẽ diễn tiến apply/replay vào target và giải thích cách tránh version lùi.

**Bài 11. Cutover và rollback.** Thiết kế thứ tự deploy khi có web, batch và admin writer cũ; khi nào được tắt chúng? Nếu target đã nhận một Order có field mới mà legacy không biết, vì sao rollback binary cũ có thể nguy hiểm?

**Bài 12. Event và downstream.** Một relay đã gửi OrderConfirmed rồi crash; migration sau đó chuyển Order ấy sang bảng mới. Có được phát một OrderConfirmed khác vì quá trình backfill không? Phân biệt commandId, eventId, sourceVersion và schemaVersion.

**Bài 13. Chọn công nghệ.** Nếu thay vì bảng normalized muốn chuyển sang **document mỗi Order**, điểm nào của quy trình giữ nguyên, điểm nào phải đổi về transaction, validator và khả năng cập nhật đồng thời? Nếu dùng **đồ thị** để đọc quan hệ khách–đơn–SKU, graph có được quyền confirm Order không?

**Bài 14. Kế hoạch kiểm chứng.** Đề xuất ít nhất 10 test, một bảng monitoring và ba cổng điều kiện trước write cutover. Nêu một trường hợp **rollback không an toàn** và phương án thay thế.

### Mẫu báo cáo cần nộp

| Hạng mục | Nội dung cần có |
| --- | --- |
| Model decision | Business rule, grain, PK/FK, mapping JSONB → rows |
| Source quality | Kết quả preflight kiểu, assessment verdict, quarantine |
| Backfill | Bản ghi OK, checkpoint/batch key, kết quả INSERT/commit |
| Reconciliation | Số Order/line, tổng tiền, header diffs, line diffs |
| Compatibility | Old/new reader, old/new writer, API/event và KPI |
| Deployment | Expand, snapshot, catch-up, shadow, switch, contract |
| Failure handling | Retry/version, quarantine, rollback/roll-forward |
| Verification | Test cases, kết quả, môi trường, phiên bản, giới hạn |

Nếu chưa có database thử để thực thi, ghi **chưa chạy** cho phần kết quả SQL và nêu rõ kết quả **kỳ vọng** theo fixture. Không được ghi PASS cho một truy vấn hoặc benchmark chưa chạy.

## 20. Hướng giải và lời giải kiểm chứng

### 20.1. Bài 1–3: mô hình và số học

**Bài 1:** order_legacy và order_header đều là **một Order**. Mỗi phần tử items_jsonb và mỗi order_line là **một OrderLine**, danh tính cần (tenantId, orderId, lineNo). Mọi Order đều có thể có lineNo=1; chỉ dùng lineNo làm PK toàn hệ thống sẽ trùng. FK ghép tenant ngăn một OrderLine của T2 tham chiếu nhầm header T1. Khóa còn phải đi cùng kiểm tra authorization, vì PK không chứng minh caller được quyền xem dữ liệu.

**Bài 2:** CHECK trên line bảo vệ quantity>0, unitPrice>=0 và discount nằm trong phạm vi giá. PK bảo vệ lineNo không trùng **sau khi đã parse vào đích**; FK bảo vệ liên kết header. Tổng các dòng với header là bất biến nhiều row, Order CONFIRMED không rỗng và không cho sửa dòng đã confirm cần hành vi domain/transaction hoặc thiết kế trigger/procedure phù hợp. Bất biến phải được bảo vệ **ở tất cả đường ghi**, kể cả batch và script.

**Bài 3:** ba Order sạch:

| Order | Gross | Discount | Payable | Lines |
| --- | ---: | ---: | ---: | ---: |
| O100 | 330.000 | 20.000 | 310.000 | 2 |
| O101 | 120.000 | 0 | 120.000 | 1 |
| O102 | 270.000 | 15.000 | 255.000 | 1 |
| **Tổng OK** | **720.000** | **35.000** | **685.000** | **4** |

Hai Order CONFIRMED hợp lệ O100+O102 có payable **565.000 VND**. O103 sai tổng nguồn 200.001 so với dòng 200.000; O104 trùng lineNo; O105 CONFIRMED nhưng rỗng. **Không tính ba đơn bị quarantine vào target coverage hoặc cohort hợp lệ**.

### 20.2. Bài 4–5: an toàn parse và idempotency

**Bài 4:** preflight jsonb_typeof phát hiện giá là string; nhưng giá là JSON number cực lớn vẫn có type number, nên **chưa đủ**. Cần kiểm tra integer/scale và phạm vi của lineNo INTEGER, quantity BIGINT, money BIGINT, số phần tử/độ sâu và giá trị thiếu trước CAST. Có thể parse một item bằng tầng ứng dụng/decoder có lỗi được bắt theo bản ghi và quarantine; không để một lỗi làm dừng toàn bộ stream mà không biết Order nào gây lỗi.

**Bài 5:** chạy backfill lần hai trên **cùng snapshot** không được tăng header/line count hoặc tổng tiền. ON CONFLICT DO NOTHING sẽ **bỏ qua cả một row đích sai nội dung** có key trùng, nên đối soát theo Order và line phải phát hiện và chặn cutover. Không dùng UPSERT ghi đè vô điều kiện khi target đã có writer mới.

### 20.3. Bài 6–8: ba cách chứng minh dữ liệu đúng

**Bài 6:** kiểm đếm coverage giúp biết có đủ Order/line nhưng không biết chúng có đúng giá không. Tổng tiền có thể khớp khi hai lỗi đối dấu triệt tiêu. Header comparison giữ ID, status, customer, money, version và thời gian. Line comparison dùng FULL OUTER JOIN để thấy **thiếu, thừa, sai field**. Target-internal recomputation phát hiện header lệch lines dù nguồn không có sẵn, nhưng chưa đủ nếu cả header và lines cùng bị biến đổi sai. Cần cả ba.

**Bài 7:** O103 cần hóa đơn/ledger/công thức tiền lịch sử, O104 cần bằng chứng ý nghĩa lineNo và các tham chiếu bên ngoài, O105 cần xác minh sự thật nghiệp vụ ở Payment/Inventory/audit. Nếu correction được duyệt, tạo một version nguồn mới, ghi audit, chụp assessment mới, rồi di chuyển **tập vừa chuyển trạng thái từ quarantine sang OK** theo protocol. Không xóa bản ghi reject lịch sử một cách không truy vết.

**Bài 8:** sửa unitPriceVnd một line trong môi trường test có thể bị CHECK chặn nếu giá âm hoặc nhỏ hơn discount; nếu vẫn hợp lệ nhưng lệch 1 VND, **line-level FULL OUTER JOIN** sẽ phát hiện. **Target-internal recomputation** thường cũng phát hiện vì header chưa đổi, nhưng nếu ai đó đổi cả header theo giá sai thì nó có thể không phát hiện; lúc ấy so với source theo từng line vẫn phát hiện. Khôi phục bằng **nguồn có thẩm quyền và audit/correction có kiểm soát**, không tùy ý bù 1 VND vào một dòng khác.

### 20.4. Bài 9: analytic grain và metric

| SKU | Quantity của CONFIRMED | Gross | Discount | Net |
| --- | ---: | ---: | ---: | ---: |
| A | 2 | 240.000 | 20.000 | **220.000** |
| B | 4 | 360.000 | 15.000 | **345.000** |
| **Tổng** | **6** | **600.000** | **35.000** | **565.000** |

Nguồn OK có **ba Order** nhưng **chỉ hai CONFIRMED**; O101 DRAFT góp vào tổng 685.000 của tất cả Order, không vào cohort CONFIRMED 565.000. Số Order CONFIRMED là COUNT(DISTINCT order_id) theo tenant/cutoff, không phải COUNT(*) số dòng fact. Do chưa có bằng chứng PaymentCaptured, **685.000 lẫn 565.000 không mặc nhiên là doanh thu đã thu**. Hai PaymentAttempt join trực tiếp với hai lines O100 có thể nhân số tiền; cần chọn fact capture/attempt đúng grain, xử lý trùng và refund.

### 20.5. Bài 10–12: CDC, cutover và event

**Bài 10:** snapshot O101 v1 vào đích; khi CDC v2 tới, apply trong một transaction toàn Order nếu target đang v1 và nguồn v2 đạt validation. Retry v1 sau đó bị bỏ qua hoặc đối chiếu vì không thể ghi version thấp hơn. Nếu v2 đến khi target chưa có v1, cần tái dựng trạng thái đầy đủ hoặc chờ gap/đọc snapshot có thẩm quyền; **không tạo dòng đoán mò**. Checkpoint được cập nhật sau khi target commit, không trước.

**Bài 11:** nâng các reader và writer theo **ma trận phiên bản**, chỉ cutover khi web, batch, admin và luồng khác không còn quyền ghi nguồn cũ, in-flight commands đã được phân xử, target caught up và đối soát PASS. Nếu target có field/trạng thái mới không tồn tại ở legacy, old writer có thể ghi đè làm mất thông tin. Ưu tiên tạm chặn write, hotfix hoặc roll-forward; chuyển ngược chỉ theo migration có đối soát riêng.

**Bài 12:** không phát OrderConfirmed mới vì backfill. **commandId/idempotency key** định danh một ý định command có thể retry; **eventId** định danh một business occurrence đã commit và giữ nguyên khi broker redeliver; **sourceVersion** là phiên bản Order được sao chép; **schemaVersion** mô tả định dạng hợp đồng event. Bốn định danh này có vai trò khác nhau, không dùng thay thế lẫn nhau.

### 20.6. Bài 13–14: công nghệ và cổng triển khai

**Bài 13:** khi đích là một document/Order, vẫn phải chốt grain, tiền, identity, sourceVersion, quarantine, CDC, đối soát, bảo mật và cutover. Nhưng constraint/FK không còn giống quan hệ: validator có thể kiểm tra cấu trúc, atomicity thuộc **một document**, outbox ở collection khác cần protocol/transaction riêng; quá nhiều lines khiến document quá lớn hoặc là điểm nóng cập nhật. Nếu dùng graph đọc đường Customer→Order→SKU, graph có thể là **read projection**, không được tự confirm Order chỉ vì có node/edge quan hệ.

**Bài 14:** bộ test tối thiểu gồm parse lỗi, trùng lineNo, mismatch tiền, empty confirmed, FK/CHECK, backfill retry, header/line rollback, full outer join, version cạnh tranh, CDC out-of-order, dedup event, tenant isolation, read shadow, BI cohort và rollback mixed-version. Theo dõi coverage, quarantine, mismatch theo khóa/tiền, CDC lag, conflict, p95 latency, outbox backlog và transformVersion. Ba cổng trước write cutover có thể là:

1. **Tính đúng:** mọi Order đang hoạt động được xử lý theo chính sách; header/line diffs = 0; totals và version theo cùng cutoff PASS; quarantine được duyệt.
2. **Nhất quán vận hành:** CDC catch-up đạt lag cho phép, không có in-flight command chưa phân xử, transaction/version/idempotency test PASS.
3. **Tương thích và khôi phục:** mọi writer/reader/consumer đã sẵn sàng, shadow read và security test PASS, có backup/restore và roll-forward/rollback được chứng minh.

Ba cổng này phải có **người chịu trách nhiệm và bằng chứng**. "CI xanh" mà còn Order đang hoạt động trong quarantine chưa được quyết định hoặc old writer còn chạy không đủ để chuyển quyền ghi.

## 21. Rubric chấm bài, checklist và kết luận

### Rubric tham khảo — 100 điểm

| Tiêu chí | Điểm | Điều kiện đạt |
| --- | ---: | --- |
| Phân tích yêu cầu, grain, ID, ranh giới và bất biến | 15 | Order/Line chính xác; quyền Sales/Payment/Inventory tách biệt |
| Schema đích và mapping JSONB → row | 15 | PK, FK, CHECK, chỉ mục, totals, trạng thái và version rõ |
| Preflight, phân loại và quarantine | 15 | Phát hiện O103/O104/O105, không sửa tiền/ID tự động |
| Backfill an toàn, retry và version guard | 15 | Cùng transaction theo Order, không ghi đè state mới |
| Đối soát đầy đủ | 20 | Coverage, totals, header, line, sai khác và cutoff đúng |
| Rollout/CDC, event và rollback | 10 | Một writer có quyền; outbox/idempotency; có kế hoạch khôi phục |
| Analytics, security và kiểm thử | 5 | Đúng grain, tenant, late data và test đồng thời |
| Lập luận và bằng chứng | 5 | Phân biệt kết quả chạy thật với kết quả kỳ vọng; nêu giả định |
| **Tổng** | **100** | |

### Checklist bàn giao thay đổi

- **Nguồn:** Có biết Order/Line trước migration được hiểu thế nào, total_vnd bao gồm những gì, ai là owner của dữ liệu không?
- **Đích:** Mô hình quan hệ mới có grain, identity, FK, CHECK, index và bất biến đúng, hay chỉ tách JSON thành nhiều hàng?
- **Khóa:** Mọi join và kiểm tra quyền đều mang namespace tenant; lineNo chỉ duy nhất trong một Order?
- **Snapshot:** Giá và giảm giá đã chốt được giữ; không tính lại bằng Catalog hiện tại?
- **Tiền:** Gross, discount, payable chính xác, không dùng floating point và không làm tròn ngầm?
- **Preflight:** Đã kiểm tra JSON shape, kiểu số, phạm vi giá trị trước CAST trên dữ liệu thật?
- **Quarantine:** Mỗi lỗi có business key, sourceVersion, reason, owner và evidence; không bị tính là chuyển thành công?
- **Migration:** Có checkpoint, transaction theo Order, chạy lại idempotent và không overwrite version mới?
- **Đối soát:** Đếm đúng cohort, so header, line, totals, status, version, timestamps và bản ghi dư/thiếu theo cutoff?
- **CDC:** Snapshot và committed change stream không có gap, offset được commit sau khi target durable?
- **Writer:** Trước và sau cutover có đúng một nguồn có thẩm quyền và không có batch/admin ghi vượt giao thức?
- **API:** Chỉ đổi storage, các client cũ có tiếp tục nhận đúng hợp đồng hay có thay đổi có phiên bản được thông báo?
- **Event:** Copy lịch sử không phát lại OrderConfirmed mới; event thật được lưu cùng transaction/outbox và retry giữ eventId?
- **Analytics:** Fact có grain rõ và không đánh đồng confirmed với paid; metric chỉ công bố khi coverage/data quality đáp ứng chính sách?
- **Bảo mật:** Quyền theo tenant, dữ liệu nhạy cảm trong logs, snapshots, backup/quarantine có kiểm soát?
- **Vận hành:** Đã đo p95/p99, WAL/CDC lag, dung lượng index, thời gian rollback/restore và chi phí lô lớn?
- **Khôi phục:** Nếu đã có dữ liệu mới, có thể roll-forward an toàn thay vì dùng old writer làm mất field/trạng thái?
- **Bằng chứng:** Kết quả SQL thực tế, mã migration, test, source watermark, transform version và chữ ký phê duyệt được lưu ở nơi phù hợp?

### Bài học rút ra khi chọn mô hình

Mô hình nguồn một hàng chứa JSONB có thể hợp lý khi Order thường được nạp trọn, dòng hàng ít, không cần FK/INDEX theo từng line và các command giữ đúng giới hạn aggregate. Mô hình đích quan hệ giúp thể hiện **khóa của từng OrderLine**, ràng buộc hàng con và các truy vấn theo SKU rõ hơn, nhưng **không tự thay thế domain transaction**. Nếu quyết định dùng document database thay vì hai bảng, vẫn cần cùng phép thử **danh tính, bất biến, dữ liệu lịch sử, idempotency, quyền truy cập và đối soát**; chỉ thay kỹ thuật lưu và phạm vi transaction vật lý. Mô hình đồ thị hoặc analytical fact nên được xem là **biểu diễn theo nhu cầu truy vấn** khi thích hợp, không là lý do để bỏ ranh giới sở hữu nghiệp vụ.

**Kết luận:** Một thay đổi mô hình dữ liệu chỉ thành công khi **ngữ nghĩa trước và sau được giữ đúng hoặc được thay đổi có chủ đích**, dữ liệu cũ đã được **phân loại và chuyển đổi theo quy tắc có thể giải thích**, còn kết quả đã được **đối soát trên cùng tập khóa và mốc thời gian**. Với ví dụ này, ba Order sạch được chuyển thành **3 header, 4 line, tổng payable 685.000 VND**, trong khi **3 Order lỗi được cách ly có chứng cứ**; riêng cohort CONFIRMED hợp lệ có payable **565.000 VND**. Không được coi 50% coverage là đủ để cutover trong production chỉ vì script không báo lỗi. Khi thêm snapshot/CDC, kiểm soát writer, contract, analytics, rollback và kiểm thử đồng thời, quá trình **expand → assess/quarantine → backfill → catch-up → reconcile → switch → contract** trở thành một phương pháp tiến hóa mô hình **rõ trách nhiệm, có bằng chứng và có thể kiểm chứng** thay vì một lần ALTER TABLE may rủi.
