# Chiều thay đổi chậm kiểu 1: ghi đè giá trị

## 1. SCD Type 1 là gì và giải quyết vấn đề nào?

Trong mô hình phân tích, **dimension (bảng chiều)** mô tả ngữ cảnh để diễn giải một sự việc ở bảng fact: khách hàng thuộc phân khúc nào, sản phẩm có tên gì, cửa hàng thuộc vùng nào. Những thuộc tính này đôi khi thay đổi chậm hơn giao dịch, nhưng vẫn có thể được điều chỉnh sau khi đã nạp vào kho dữ liệu.

**Slowly Changing Dimension Type 1 (SCD Type 1)** là cách quản lý thay đổi bằng **ghi đè giá trị thuộc tính hiện hành trên chính hàng chiều đang tồn tại**, thay vì tạo thêm phiên bản hàng lịch sử cho mỗi lần thay đổi.

Ví dụ, khách hàng `CUS-42` có tên hiển thị bị nhập sai:

| Thời điểm nạp | customer_bk | display_name trong dimension | segment |
| --- | --- | --- | --- |
| Trước khi sửa | CUS-42 | Nguyên Vân | STANDARD |
| Sau khi sửa | CUS-42 | Nguyễn Vân | STANDARD |

Với SCD Type 1, hàng chiều chứa tên đúng `Nguyễn Vân` và **không lưu lại giá trị `Nguyên Vân` như một phiên bản chiều trước đó**. Các fact cũ đang trỏ đến cùng khóa chiều sẽ hiển thị tên mới khi JOIN.

Tính chất này rất hữu ích cho sửa lỗi chính tả, chuẩn hóa nhãn, sửa mã vùng bị nhập sai hoặc các thuộc tính mà tổ chức **cố ý muốn mọi báo cáo, kể cả báo cáo quá khứ, sử dụng giá trị hiện hành đã hiệu chỉnh**.

Nhưng đây cũng là đánh đổi cốt lõi: **SCD Type 1 không giữ được lịch sử biến động của các thuộc tính đã bị ghi đè trong chính bảng chiều**. Nếu báo cáo cần biết “khách thuộc phân khúc gì khi mua hàng”, chỉ có hàng Type 1 hiện tại thường không đủ.

### Điều SCD Type 1 có và không có

- Có: một biểu diễn hiện hành theo business key, khóa tham chiếu ổn định, cập nhật thuộc tính tương đối đơn giản.
- Có: khả năng **đổi cách nhóm các fact lịch sử** theo giá trị chiều mới, khi đó là chủ ý nghiệp vụ.
- Không: chuỗi các giá trị cũ của thuộc tính đã ghi đè, trừ khi tổ chức giữ lịch sử **ở một nguồn khác** như audit, snapshot, CDC hoặc bảng SCD2.
- Không: bảo đảm dữ liệu nguồn tự đúng; chuẩn hóa, quyền cập nhật và kiểm chứng vẫn cần thiết.
- Không: lý do để ghi đè sự kiện nghiệp vụ, giao dịch tài chính, định danh hay khóa của fact.

Chữ “slowly” là cách gọi một họ kỹ thuật thiết kế chiều, **không** quy định phải đợi một khoảng thời gian mới cập nhật và cũng không hàm ý mọi thuộc tính đều thay đổi chậm.

## 2. Xác định grain: một hàng chiều đại diện cho ai hoặc cái gì?

Đề bài trước khi viết SQL là:

> Trong dimension này, **một hàng đại diện cho một thực thể nghiệp vụ nào**, và điều gì khiến hai hàng được coi là cùng thực thể?

Với `dim_customer` dùng Type 1 toàn bộ, giả sử mỗi tenant có một mã khách hàng chuẩn đã được hệ thống quản lý danh tính xác nhận:

**Grain:** một hàng cho mỗi cặp `(tenant_id, customer_bk)`.

Với `dim_product`, grain có thể là một sản phẩm theo `(tenant_id, product_bk)`. Nếu SKU bị tái sử dụng cho sản phẩm khác, SKU **không đủ ổn định làm business key**; cần định danh bền vững hơn hoặc một namespace/quy tắc thời gian đã được xác minh.

### Ba loại khóa phải tách biệt

| Khóa | Vai trò | Ví dụ |
| --- | --- | --- |
| **Business key (BK)** | Định danh thực thể theo hợp đồng nghiệp vụ/nguồn có thẩm quyền. | `customer_bk = CUS-42`. |
| **Surrogate key (SK)** | Khóa thay thế do kho phân tích quản lý, được fact tham chiếu. | `customer_sk = 1087`. |
| **Source record key** | Định danh record trong hệ nguồn, có thể khác giữa các hệ. | `crm_customer_id = 42`, `app_user_id = U-918`. |

**Type 1 phải giữ nguyên SK khi chỉ sửa thuộc tính**: mọi fact trước và sau thay đổi đều trỏ đến cùng `customer_sk`. Nếu cứ xóa hàng chiều cũ rồi INSERT hàng mới với SK khác, fact có thể bị mồ côi hoặc đòi cập nhật lại hàng triệu dòng, làm mất ý nghĩa của một phép ghi đè đơn giản.

Ngoài ra, **không được coi hai source ID giống chuỗi là cùng khách hàng** khi chúng thuộc hai nguồn hoặc tenant khác nhau. Nếu chưa có business key chung, cần định nghĩa namespace, bảng mapping được xác minh hoặc một canonical ID ổn định trước khi tạo dimension hợp nhất.

### Một dimension Type 1 không đồng nghĩa “chỉ có một trường”

Bảng `dim_customer` có thể gồm tên, phân khúc, vùng bán, nhóm tuổi dạng phân loại và các nhãn khác. Type 1 mô tả **cách cập nhật thuộc tính**, không phải số lượng trường hay cách đặt khóa. Các thuộc tính cùng hàng cũng có thể theo **chính sách SCD khác nhau**, nhưng khi trộn Type 1 và Type 2 cần có quy tắc cụ thể, không viết đè bất kỳ trường nào không phân biệt.

## 3. Ảnh hưởng quan trọng nhất: fact lịch sử được phân nhóm lại

Xét dữ liệu đặt hàng:

- Ngày 2026-01-15, khách `CUS-42` thuộc phân khúc `STANDARD` và đặt một đơn có giá trị 2.000.000 VND.
- Ngày 2026-03-01, CRM chuyển khách sang `VIP`.
- Dimension được cập nhật **SCD Type 1**, thay `segment = 'STANDARD'` bằng `segment = 'VIP'`, giữ `customer_sk = 1087`.
- Dòng fact tháng 1 vẫn là đơn 2.000.000 VND, không thay đổi tiền hay khóa.

Dữ liệu theo hai thời điểm:

| Bảng/hàng | Trước cập nhật | Sau cập nhật Type 1 |
| --- | --- | --- |
| `dim_customer(1087)` | `segment = STANDARD` | `segment = VIP` |
| `fact_order_line` của tháng 1 | `customer_sk = 1087`, `net_minor = 2.000.000` | Không đổi |
| Báo cáo tháng 1 **JOIN dimension hiện tại** | 2.000.000 trong nhóm STANDARD | 2.000.000 trong nhóm VIP |

Kết quả quan trọng:

**Số tiền giao dịch lịch sử không tự đổi, nhưng cách phân loại giao dịch lịch sử có thể đổi.**

Đây không nhất thiết là lỗi. Nếu nghiệp vụ hỏi “**Toàn bộ doanh số lịch sử của những khách hiện thuộc nhóm VIP là bao nhiêu?**”, Type 1 có thể đúng. Nếu hỏi “**Tháng 1, nhóm VIP tại thời điểm bán tạo bao nhiêu doanh số?**”, Type 1 đơn lẻ **không thể khôi phục** phân khúc STANDARD đã bị ghi đè.

### Hai câu hỏi SQL có ngữ nghĩa khác nhau

**Câu hỏi A: phân khúc hiện tại của khách khi xem doanh số cũ**

~~~sql
SELECT date_trunc('month', f.ordered_at) AS order_month,
       c.segment AS current_segment,
       f.currency,
       SUM(f.net_minor) AS booked_net_minor
FROM fact_order_line f
JOIN dim_customer c
  ON c.tenant_id = f.tenant_id
 AND c.customer_sk = f.customer_sk
GROUP BY date_trunc('month', f.ordered_at),
         c.segment, f.currency;
~~~

Đây là cách phân tích Type 1 phù hợp nếu tiêu đề báo cáo nhấn mạnh **current segment**, không phải “segment at sale”.

**Câu hỏi B: phân khúc đúng vào thời điểm giao dịch**

Không thể trả lời tin cậy bằng hàng Type 1 duy nhất nếu giá trị lịch sử không còn ở đâu khác. Cần **SCD Type 2**, thuộc tính phân khúc đã được cố định theo chính sách trên fact, hoặc một nguồn lịch sử có đủ thời gian hiệu lực để tái tạo. Không nên tự gán phân khúc hiện tại cho lịch sử rồi đặt tên là “tại thời điểm bán”.

## 4. Khi nào nên và không nên dùng Type 1?

### Các trường hợp thường phù hợp

| Thuộc tính/sự việc | Vì sao Type 1 có thể hợp lý? | Điều kiện cần xác nhận |
| --- | --- | --- |
| Sửa lỗi chính tả tên hiển thị | Muốn mọi báo cáo nhìn thấy tên đúng. | Tên cũ không cần như một thuộc tính phân tích lịch sử. |
| Chuẩn hóa cách viết tên vùng | `TP.HCM` và `Hồ Chí Minh` cùng một vùng theo định nghĩa đã duyệt. | Không đánh đồng hai vùng khác nhau; có bảng mapping chuẩn. |
| Sửa mô tả phân loại sản phẩm bị nhập sai | Mọi kỳ báo cáo cần dùng nhãn chuẩn. | Đây là **sửa lỗi**, không phải thay đổi danh mục theo thời gian. |
| Điền thuộc tính còn thiếu từ nguồn đáng tin | Hàng chiều từ `UNKNOWN` chuyển thành giá trị đã xác nhận. | Giá trị trước là thiếu, không phải một trạng thái lịch sử cần giữ. |
| Cập nhật nhãn giao diện không ảnh hưởng tính toán lịch sử | Truy vấn cần thông tin hiện hành. | Việc ghi đè không phá lời giải thích các giao dịch cũ. |

### Những trường hợp Type 1 thường không đủ

| Nhu cầu | Vì sao Type 1 đơn lẻ không đủ? | Lựa chọn thường phù hợp hơn |
| --- | --- | --- |
| Phân khúc khách **tại lúc đặt hàng** | Giá trị cũ bị ghi đè khi phân khúc đổi. | SCD2 hoặc giữ snapshot phân khúc theo grain hợp lệ của fact. |
| Giá hợp đồng có hiệu lực theo ngày | Ghi đè giá sẽ làm lịch sử hóa đơn khó giải thích. | Bảng phiên bản giá/valid time, hoặc giá được chốt trên fact hợp đồng. |
| Theo dõi ai thay đổi thuộc tính và khi nào | Type 1 không lưu before/after. | Audit log, CDC được lưu, event hoặc bảng history. |
| Đối soát khoản thu và hoàn tiền | Đây là **fact nghiệp vụ**, không phải nhãn dimension. | Ledger/fact movement với ID giao dịch và mốc xác nhận. |
| Điều chỉnh hồi tố có hai thời gian | Cần biết hệ thống từng biết gì và dữ kiện có hiệu lực khi nào. | Bitemporal/version history hoặc mô hình phù hợp. |
| Phân tích luồng trạng thái chuyển đổi | Cần lịch sử trạng thái, không chỉ state cuối. | Transaction fact/event timeline hoặc SCD thích hợp. |

**Quy tắc chọn:** dùng Type 1 khi **giá trị mới nên thay thế giá trị cũ cho mọi lượt đọc**. Dùng SCD2 hoặc lịch sử khác khi “giá trị cũ đúng tại một thời điểm” vẫn có giá trị phân tích.

Không phải mọi thay đổi thuộc tính đều có một lựa chọn cố định. Ví dụ `customer_segment` có thể được xử lý Type 1 trong dashboard “phân nhóm hiện tại”, nhưng cần Type 2 trong báo cáo chính sách ưu đãi theo thời điểm bán. Hai yêu cầu phải được ghi thành hai định nghĩa riêng, không giấu đằng sau một cột tên chung.

## 5. Thiết kế bảng quan hệ Type 1 với khóa và ràng buộc rõ

Ví dụ sau dùng PostgreSQL và giả định **CRM chuẩn là nguồn có thẩm quyền duy nhất** đối với `display_name`, `segment` và `region_code`. `customer_bk` ổn định, duy nhất trong mỗi tenant. Hệ nguồn có `source_revision` nguyên, tăng nghiêm ngặt khi phát bản ghi phiên bản mới cho cùng khách.

~~~sql
CREATE TABLE dim_customer (
    customer_sk       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         UUID NOT NULL,
    customer_bk       VARCHAR(100) NOT NULL,
    display_name      TEXT NOT NULL,
    segment           VARCHAR(30) NOT NULL,
    region_code       VARCHAR(20),
    is_inferred       BOOLEAN NOT NULL DEFAULT FALSE,
    source_revision   BIGINT NOT NULL CHECK (source_revision >= 0),
    source_updated_at TIMESTAMPTZ,
    first_loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_applied_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    attributes_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, customer_bk),
    UNIQUE (tenant_id, customer_sk),
    CHECK (btrim(display_name) <> '')
);

CREATE INDEX ix_dim_customer_segment_region
    ON dim_customer (tenant_id, segment, region_code);

CREATE TABLE fact_order_line (
    tenant_id       UUID NOT NULL,
    order_id        VARCHAR(100) NOT NULL,
    line_id         VARCHAR(100) NOT NULL,
    customer_sk     BIGINT NOT NULL,
    ordered_at      TIMESTAMPTZ NOT NULL,
    net_minor       BIGINT NOT NULL CHECK (net_minor >= 0),
    currency        CHAR(3) NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_id),
    FOREIGN KEY (tenant_id, customer_sk)
        REFERENCES dim_customer (tenant_id, customer_sk)
);

CREATE INDEX ix_fact_order_line_customer_time
    ON fact_order_line (tenant_id, customer_sk, ordered_at);
~~~

**Giải thích quyết định vật lý:**

1. `customer_sk` là SK toàn bảng; `UNIQUE(tenant_id, customer_bk)` giữ **một hàng cho một business key** theo grain. Nếu nhiều nguồn chưa có cùng canonical BK, phải mở rộng không gian khóa.
2. Ràng buộc bổ sung `UNIQUE(tenant_id, customer_sk)` cho phép foreign key tổ hợp từ fact xác nhận cả **tenant và SK**, thay vì chỉ xác nhận SK tồn tại ở một tenant bất kỳ.
3. `display_name` và `segment` là thuộc tính Type 1, không có `valid_from/valid_to` để lưu nhiều phiên bản. Cột `attributes_changed_at` chỉ cho biết **lần gần nhất nội dung chiều được thay**, không giữ giá trị cũ.
4. `source_revision` giúp chống cập nhật bởi bản nguồn đã cũ, **chỉ khi hệ nguồn bảo đảm revision có thứ tự tin cậy theo từng business key**. Nó không phải SCD2 version, không phải SK.
5. `is_inferred` cho biết một hàng được tạo tạm để giữ FK khi fact đến trước thông tin khách; khi dữ liệu đầy đủ đến, ta **bổ sung trên chính SK đó**.
6. `fact_order_line` có grain một dòng hàng trong một đơn. Khoản `net_minor` ở đây là giá trị của dòng hàng theo chính sách đặt hàng đã thống nhất, không tự đồng nghĩa doanh thu được ghi nhận hay dòng tiền thực tế.
7. Chỉ mục chiều theo `tenant_id, segment, region_code` là gợi ý cho các query lọc; không tự coi mọi chỉ mục là tốt. Kho dữ liệu columnar có chiến lược clustering/partition và scan khác PostgreSQL OLTP.

**Lưu ý định danh:** nếu nguồn có khả năng tái sử dụng `customer_bk` cho người khác, thiết kế một hàng/BK không an toàn. Cần sửa hợp đồng định danh (ví dụ thêm namespace hoặc key bền vững), không dùng Type 1 để ghi đè hai người khác nhau thành một người.

## 6. Phân biệt các loại thời điểm trong bảng Type 1

Một hàng chiều thường có nhiều metadata thời gian, không nên coi chúng đồng nghĩa:

| Trường | Ý nghĩa | Có tạo lịch sử thuộc tính không? |
| --- | --- | --- |
| `source_updated_at` | Mốc cập nhật do nguồn cung cấp; có thể lệch đồng hồ hoặc đến muộn. | Không. |
| `first_loaded_at` | Lúc dimension lần đầu biết đến business key. | Không. |
| `last_applied_at` | Lần gần nhất áp dụng một phiên bản nguồn mới hơn theo hợp đồng. | Không. |
| `attributes_changed_at` | Lần gần nhất giá trị thuộc tính Type 1 thực sự đổi trong dimension. | Không. |
| `ordered_at` ở fact | Thời điểm nghiệp vụ của đơn hàng. | Thuộc fact, không thay bằng giờ cập nhật chiều. |

Dù có đủ các timestamp này, bảng Type 1 vẫn **không trả lời được** “trước lần sửa cuối, thuộc tính có giá trị nào”. Để có câu trả lời đó, phải có một bảng lịch sử, event, audit hoặc SCD2.

Một hệ nguồn không có revision đáng tin cậy có thể dùng **vị trí CDC/transaction log đã được cam kết** hoặc cơ chế phân thứ tự nhất quán khác. Không tự so `source_updated_at` giữa hai nguồn độc lập rồi mặc định bản có timestamp lớn hơn là sự thật được ưu tiên.

## 7. Quy trình nạp ETL/ELT: chuẩn hóa, xác định khóa, ghi đè

Một pipeline Type 1 có thể chia thành các bước:

~~~mermaid
flowchart TD
    A["CRM snapshot / CDC đã commit"] --> B["Staging: schema, namespace, revision"]
    B --> C["Kiểm tra chất lượng và dedup"]
    C --> D["Xác định một phiên bản mới nhất hợp lệ trên mỗi BK"]
    D --> E{"BK đã tồn tại trong dim_customer?"}
    E -->|"Chưa"| F["INSERT hàng chiều mới + SK"]
    E -->|"Có, revision mới hơn"| G["UPDATE thuộc tính trên cùng SK"]
    E -->|"Có, revision cũ / retry"| H["Bỏ qua hoặc đối chiếu xung đột"]
    F --> I["Kiểm chứng grain, version, đối soát"]
    G --> I
    H --> I
~~~

### Bước 1: nguồn phải có hợp đồng

Cần biết bản ghi nhận là:

- **Full-state record/snapshot:** đủ mọi thuộc tính cần cập nhật, bao gồm giá trị NULL có nghĩa “giá trị hiện hành không được biết”.
- **Partial change/patch:** chỉ có một số trường thay đổi; các trường **vắng mặt** không có nghĩa cần đặt thành NULL.
- **CDC/event stream:** dữ liệu có thứ tự và định danh giao dịch/record, có thể nhận nhiều lần hoặc sai thứ tự ở consumer.

Đoạn SQL ví dụ sau **chỉ dành cho full-state record đã được làm sạch và chọn một dòng hợp lệ cho mỗi business key**. Nếu đầu vào là patch, phải hợp nhất với state nguồn theo policy trước khi chạy; không nhầm missing với NULL.

### Bước 2: tạo staging sạch, một hàng mỗi BK

~~~sql
-- Bảng tạm được nạp bằng pipeline trước bước upsert.
-- Ví dụ chỉ áp dụng cho một nguồn CRM chuẩn, revision >= 1.
CREATE TEMP TABLE stg_customer_clean (
    tenant_id         UUID NOT NULL,
    customer_bk       VARCHAR(100) NOT NULL,
    display_name      TEXT NOT NULL,
    segment           VARCHAR(30) NOT NULL,
    region_code       VARCHAR(20),
    source_revision   BIGINT NOT NULL CHECK (source_revision >= 1),
    source_updated_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, customer_bk)
) ON COMMIT DROP;
~~~

**Lưu ý khi chạy ví dụ:** Bảng tạm có `ON COMMIT DROP` phải được tạo, nạp dữ liệu, kiểm tra xung đột và sử dụng để upsert **trong cùng một transaction và cùng kết nối**. Nếu chạy riêng lệnh `CREATE TEMP TABLE` ở chế độ tự động commit sau mỗi câu, bảng có thể bị xóa ngay khi lệnh tạo hoàn tất. Với pipeline nạp nhiều bước hoặc nhiều kết nối, có thể dùng staging bền vững theo `batch_id` và chính sách dọn dẹp riêng.

Điều kiện **một hàng/BK** được xây từ bước chọn phiên bản mới nhất có căn cứ, ví dụ cursor CDC hoặc `source_revision` có hợp đồng. Không chọn tùy tiện theo `MAX(ingested_at)` nếu message đến muộn. Nếu cùng BK và cùng revision có payload khác nhau, đó là **mâu thuẫn dữ liệu** cần cách ly/điều tra, không chọn ngẫu nhiên một hàng.

### Bước 3: phát hiện xung đột cùng revision

Trước khi ghi, so sánh dữ liệu staging với hàng đã nạp:

~~~sql
SELECT s.tenant_id, s.customer_bk, s.source_revision
FROM stg_customer_clean s
JOIN dim_customer d
  ON d.tenant_id = s.tenant_id
 AND d.customer_bk = s.customer_bk
WHERE s.source_revision = d.source_revision
  AND (
       ROW(s.display_name, s.segment, s.region_code)
       IS DISTINCT FROM
       ROW(d.display_name, d.segment, d.region_code)
  );
~~~

Nếu truy vấn trả hàng, cần **dừng/đưa vào luồng lỗi** theo chính sách. Nếu hai worker chạy song song, việc kiểm tra riêng lẻ bên ngoài transaction **không thay thế** phối hợp concurrency; nên giới hạn một writer trên cùng khóa/batch, hoặc giữ kiểm tra và upsert trong transaction/luồng nhận dữ liệu được điều phối.

### Bước 4: INSERT hoặc UPDATE mà giữ nguyên SK

~~~sql
INSERT INTO dim_customer (
    tenant_id, customer_bk, display_name,
    segment, region_code, source_revision,
    source_updated_at, is_inferred
)
SELECT
    tenant_id, customer_bk, display_name,
    segment, region_code, source_revision,
    source_updated_at, FALSE
FROM stg_customer_clean
ON CONFLICT (tenant_id, customer_bk)
DO UPDATE SET
    attributes_changed_at =
        CASE
            WHEN dim_customer.is_inferred
              OR ROW(
                    dim_customer.display_name,
                    dim_customer.segment,
                    dim_customer.region_code
                 ) IS DISTINCT FROM ROW(
                    EXCLUDED.display_name,
                    EXCLUDED.segment,
                    EXCLUDED.region_code
                 )
            THEN now()
            ELSE dim_customer.attributes_changed_at
        END,
    display_name = EXCLUDED.display_name,
    segment = EXCLUDED.segment,
    region_code = EXCLUDED.region_code,
    source_revision = EXCLUDED.source_revision,
    source_updated_at = EXCLUDED.source_updated_at,
    is_inferred = FALSE,
    last_applied_at = now()
WHERE dim_customer.source_revision < EXCLUDED.source_revision;
~~~

**Tại sao câu upsert này có ý nghĩa Type 1?**

- Cặp `(tenant_id, customer_bk)` là unique, dùng tìm đúng hàng hiện có.
- `UPDATE` sửa thuộc tính trên **cùng hàng**, không chèn một hàng SCD2 mới và **không cấp lại `customer_sk`**.
- Điều kiện `source_revision < EXCLUDED.source_revision` ngăn **retry cùng revision** và **bản cũ đến muộn** ghi đè phiên bản mới hơn.
- `ROW(...) IS DISTINCT FROM ROW(...)` so sánh cả trường có NULL, tránh bất ngờ từ biểu thức `<>` với NULL.
- `attributes_changed_at` chỉ đổi khi thuộc tính thực sự khác (hoặc hàng tạm được hoàn thiện); `last_applied_at` đổi khi một revision cao hơn được chấp nhận, kể cả khi giá trị hiển thị không khác.
- Ví dụ không sử dụng `COALESCE(EXCLUDED.region_code, dim_customer.region_code)`: với **full-state record**, NULL có thể là chủ ý xóa/không còn biết vùng. Nếu dùng COALESCE, NULL mới sẽ không ghi đè được giá trị cũ, tạo dữ liệu sai.

**Giới hạn:** `source_revision` chỉ so sánh được trong cùng một chuỗi phiên bản nguồn đã định nghĩa. Nếu CRM reset revision, hợp nhất hồ sơ hoặc hai hệ cập nhật cùng trường, cần một chính sách mới về identity, ưu tiên nguồn và thứ tự; SQL trên không tự giải quyết xung đột đó.

### Bước 5: commit và ghi nhận kết quả nạp

Nên ghi metadata lần nạp, số hàng insert/update/skip/conflict và checkpoint nguồn. Nếu checkpoint và dữ liệu đích ở cùng một DB, cập nhật **trong cùng transaction** khi phù hợp. Nếu nguồn ở hệ khác, cần cách ghi checkpoint/retry sao cho không bỏ qua dữ liệu đã commit nhưng chưa xử lý xong.

Upsert idempotent theo revision có thể được thử lại sau lỗi mà không làm tăng số hàng dimension hoặc thay SK. Không vì thấy một batch “đã chạy” mà mặc định tất cả hàng trong batch đã được cập nhật nếu trước đó có lỗi từng phần.

## 8. Bản ghi đến muộn, sai thứ tự và dữ liệu sửa hồi tố

### Khi một bản cập nhật cũ đến sau

Giả sử ba bản full-state của `CUS-42`:

| Lần nhận ở kho | source_revision | segment | Xử lý Type 1 |
| ---: | ---: | --- | --- |
| Thứ nhất | 7 | STANDARD | Ghi nhận. |
| Thứ hai | 9 | VIP | Cập nhật cùng SK. |
| Thứ ba | 8 | PREMIUM | **Bỏ qua** vì revision thấp hơn 9. |
| Thứ tư | 9 | VIP | Retry trùng, không thay đổi. |

Nếu chỉ dùng thời gian nhận dữ liệu, dòng revision 8 có thể ghi đè `VIP` thành `PREMIUM`, khiến dimension lùi về state cũ. Vì vậy cần so thứ tự **nguồn đã cam kết**, không phải giờ ingest.

### Khi dữ liệu cũ bị sửa sai hồi tố

Ví dụ quản lý xác nhận phân khúc `STANDARD` của tháng 1 là nhập nhầm, thực tế phải là `VIP` từ đầu. Type 1 có thể ghi đè thành `VIP` và báo cáo lịch sử dùng giá trị sửa đúng theo **policy restatement**.

Khác với tình huống khách **thực sự nâng hạng vào tháng 3**, khi đó muốn báo cáo “khách là STANDARD trong tháng 1, VIP từ tháng 3” thì SCD2 hoặc lịch sử valid-time phù hợp hơn.

Sự khác nhau không nằm ở mã SQL: cả hai có thể mang payload `segment=VIP`. Nó nằm ở **ý nghĩa nghiệp vụ**:

- **Correction:** giá trị cũ được công nhận là sai.
- **Change over time:** giá trị cũ từng đúng, giá trị mới chỉ đúng từ một mốc.

Không thể chọn Type 1 hay Type 2 đúng nếu chưa phân biệt hai trường hợp.

## 9. Fact đến trước dimension: inferred member và unknown member

Trong hệ nhiều nguồn, đơn hàng có thể đến trước thông tin khách. Foreign key ở fact vẫn cần một dimension row.

Có hai cách xử lý phổ biến:

**Inferred member:** tạo tạm một hàng chiều **cho chính business key đó**, có `is_inferred = TRUE`, SK bền vững. Khi CRM gửi dữ liệu đầy đủ, upsert Type 1 cập nhật hàng đó và đặt `is_inferred = FALSE`, **giữ nguyên SK**. Cách này hữu ích khi BK đã được xác minh đủ tin cậy.

**Unknown member:** gắn fact với một khóa đặc biệt “không xác định” khi chưa biết business key hoặc chưa thể lập hàng suy đoán. Về sau có thể phải **backfill fact** sang SK thực khi nguồn cung cấp bằng chứng. Unknown member không nên bị coi là một khách hàng thật; cần chính sách tách unknown theo tenant/loại nguyên nhân nếu cần.

Ví dụ trạng thái inferred:

| customer_sk | customer_bk | display_name | segment | is_inferred |
| ---: | --- | --- | --- | --- |
| 1087 | CUS-42 | UNKNOWN | UNKNOWN | true |
| 1087 (sau enrich) | CUS-42 | Nguyễn Vân | VIP | false |

Hai dòng trong bảng chỉ là **hai thời điểm quan sát cùng một hàng**, không phải hai hàng đồng thời.

### Lưu ý về cách tạo inferred member

Schema mẫu cho phép `source_revision = 0` dành cho hàng suy đoán; nguồn CRM hợp lệ sử dụng revision từ 1 trở lên. Khi có event đến trước, việc tạo inferred member phải dùng **cùng unique business key** và transaction/concurrency phù hợp để tránh tạo hai hàng cho cùng `CUS-42`.

Chỉ nên suy đoán **sự tồn tại của BK đã được xác nhận**. Không tự đoán tên, vùng hay phân khúc thật từ một nguồn thiếu thông tin. Nhãn `UNKNOWN` là giá trị kỹ thuật theo hợp đồng, không phải một sự thật nghiệp vụ.

## 10. Type 1, Type 2, Type 0 và mô hình kết hợp

Bảng so sánh:

| Kiểu | Khi thuộc tính thay đổi | Khả năng trả lời lịch sử | Trường hợp |
| --- | --- | --- | --- |
| **Type 0** | Giữ nguyên giá trị ban đầu của thuộc tính. | Biết giá trị được cố định ban đầu; không nắm mọi thay đổi. | Thuộc tính được chốt, không cho ghi đè theo policy. |
| **Type 1** | Ghi đè trên hàng hiện tại. | Chỉ có giá trị mới trong dimension đó. | Sửa nhãn, sửa lỗi, phân nhóm lại lịch sử có chủ ý. |
| **Type 2** | Chèn phiên bản dimension mới với SK mới hoặc phiên bản hợp lệ được định danh rõ. | Truy vấn thuộc tính từng có hiệu lực ở mốc nghiệp vụ nếu historization đúng. | Phân khúc lúc bán, khu vực bán tại thời điểm phát sinh. |
| **Hybrid Type 1 + Type 2** | Một số thuộc tính ghi đè, số khác tạo phiên bản. | Khác nhau theo chính sách từng thuộc tính. | Tên bị sửa chính tả kiểu 1, phân khúc thay theo thời gian kiểu 2. |

Trong SCD2 điển hình, nhiều hàng của một BK có `valid_from`, `valid_to` hoặc số phiên bản. Fact tham chiếu **SK của phiên bản chiều tại thời điểm giao dịch**. Với Type 1 thuần, **một BK có một SK**, và tất cả fact liên quan tới cùng hàng đang bị ghi đè.

### Kết hợp Type 1 và Type 2 trong một dimension

Giả sử `dim_customer` historize `segment` theo Type 2 nhưng `display_name` là Type 1. Khi sửa lỗi tên từ `Nguyên Vân` thành `Nguyễn Vân`, cần xác định:

- Nếu **tên đúng phải thay thế mọi bản lịch sử**, cập nhật trường tên trên **tất cả các hàng SCD2 của cùng BK**, không chỉ hàng hiện hành. Các SK của phiên bản segment vẫn giữ nguyên.
- Nếu tên cũ từng có ý nghĩa tại thời điểm cũ và phải tra cứu được, tên **không nên** là thuộc tính Type 1 trong thiết kế này.
- Quy tắc xử lý correction hồi tố của segment có thể yêu cầu tách/chỉnh lại các khoảng Type 2 và đối chiếu fact keys; không biến nó thành ghi đè Type 1 vì dễ làm biến mất lịch sử có giá trị.

Đây là lý do nên có **chính sách SCD ở cấp thuộc tính**, với owner và định nghĩa, chứ không chỉ gắn nhãn “bảng khách hàng dùng SCD2” rồi cập nhật bất kỳ trường nào tùy tiện.

## 11. Điều gì không nên ghi đè bằng Type 1?

Một số dữ liệu tuy nhìn giống “thuộc tính” nhưng thực chất là dữ kiện đã chốt của một giao dịch:

- **Đơn giá khi bán:** giá hiện hành của sản phẩm có thể là Type 1 để hiển thị catalog, nhưng giá đã chốt của dòng đơn phải được giữ ở fact/hợp đồng theo quy tắc.
- **Địa chỉ giao của đơn đã hoàn tất:** khách đổi địa chỉ liên lạc không làm thay đổi địa chỉ thực tế đã giao. Nếu báo cáo cần vị trí giao lịch sử, phải giữ dữ kiện giao thực tế.
- **Phân khúc quyết định mức ưu đãi tại ngày mua:** nếu ưu đãi phụ thuộc segment thời điểm đó, ghi đè segment hiện tại có thể khiến không giải thích được chính sách đã áp dụng.
- **Số tiền capture/refund:** phải lấy từ giao dịch được nguồn xác nhận; yêu cầu hoàn tiền chưa đồng nghĩa đã hoàn.
- **Mốc sự kiện đã xảy ra:** sửa `last_status` trên dimension không thay thế bảng fact/event cho vòng đời sự kiện.

Có thể hiển thị “thông tin khách hiện tại” bên cạnh chứng từ cũ, nhưng tên cột/báo cáo phải nói rõ đó là thông tin hiện tại, không được biến thành bằng chứng rằng chứng từ xưa vốn mang giá trị ấy.

### Thay business key không phải sửa thuộc tính Type 1 thông thường

Nếu CRM đổi mã khách hoặc phát hiện hai mã phải hợp nhất, cần quy trình identity reconciliation, mapping và lineage. Cập nhật trực tiếp `customer_bk` có thể gây đứt liên kết staging/dedup, và việc gộp hai SK có thể đòi quyết định lại fact references. Không dùng `ON CONFLICT DO UPDATE SET customer_bk = ...` tùy tiện để giải quyết master-data merge.

## 12. Kiểm thử và đối soát bảng chiều Type 1

Một pipeline hoạt động không lỗi không đồng nghĩa dữ liệu đúng. Nên kiểm thử các bất biến sau:

| Nhóm | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| **Grain** | Mỗi `(tenant_id, customer_bk)` có một hàng chiều. | Không có BK trùng. |
| **Khóa ổn định** | Sửa `display_name` hoặc `segment` không đổi `customer_sk`. | Fact references tiếp tục hợp lệ. |
| **Nguồn mới hơn** | Revision 9 đến trước revision 8. | Revision 8 không ghi đè 9. |
| **Idempotency** | Chạy lại cùng batch/revision. | Không thêm hàng, không thay thuộc tính bất ngờ. |
| **Conflict** | Hai payload khác nhau cùng BK và revision. | Dừng/đưa vào hàng lỗi, không chọn ngẫu nhiên. |
| **NULL** | Full-state record gửi `region_code = NULL`. | Giá trị cũ bị xóa nếu đó là nghĩa hợp lệ. |
| **Partial payload** | Patch không có `region_code`. | Không tự đặt region thành NULL. |
| **Inferred member** | Fact đến trước dim rồi CRM cập nhật. | SK ban đầu vẫn tồn tại và được hoàn thiện. |
| **Ảnh hưởng báo cáo** | Segment thay đổi Type 1. | Báo cáo lịch sử dùng current segment theo hợp đồng; không gọi nhầm là as-of. |
| **Tenant** | Fact thuộc tenant A không tham chiếu dim tenant B. | FK tổ hợp/kiểm tra cách ly chặn lỗi. |

### Một số SQL kiểm tra

~~~sql
-- Trùng business key: phải trả 0 hàng.
SELECT tenant_id, customer_bk, COUNT(*) AS n
FROM dim_customer
GROUP BY tenant_id, customer_bk
HAVING COUNT(*) > 1;

-- Số inferred members còn tồn: dùng để theo dõi độ đầy đủ.
SELECT tenant_id, COUNT(*) AS inferred_count
FROM dim_customer
WHERE is_inferred = TRUE
GROUP BY tenant_id;

-- Kiểm tra fact không tìm thấy chiều (FK thường đã chặn với bảng local).
SELECT f.tenant_id, f.order_id, f.line_id
FROM fact_order_line f
LEFT JOIN dim_customer d
  ON d.tenant_id = f.tenant_id
 AND d.customer_sk = f.customer_sk
WHERE d.customer_sk IS NULL;

-- Phân bố khách theo phân khúc hiện tại.
SELECT tenant_id, segment, COUNT(*) AS customer_count
FROM dim_customer
WHERE is_inferred = FALSE
GROUP BY tenant_id, segment;
~~~

`UNIQUE` và FK trong DDL mẫu sẽ ngăn nhiều lỗi ngay ở ghi; các truy vấn kiểm tra vẫn hữu ích khi dữ liệu được import qua đường đặc biệt, dùng read store tách biệt hoặc cần giám sát chất lượng theo tỷ lệ.

### Đối soát với nguồn

Với tập business key đầy đủ đã xác nhận:

1. Đếm số BK hợp lệ tại CRM và số BK tương ứng ở dimension theo tenant.
2. So giá trị hiển thị, phân khúc, vùng và `source_revision` của các bản mới nhất.
3. Phân loại sai lệch: chưa nhận được bản nguồn, record bị cách ly, revision cũ, lỗi mapping, hoặc rule khác nhau.
4. Theo dõi thời gian từ khi nguồn commit đến khi dimension áp dụng.
5. Thử với dữ liệu có NULL, ký tự Unicode, định danh đổi dạng, message lặp và đúng ca phục hồi sau lỗi.

Đối soát chỉ đúng khi **cùng phạm vi nguồn và cùng mốc nhất quán**. Không so một snapshot nguồn lúc 10:00 với kho đã nhận cập nhật 10:30 rồi kết luận sai vì số hàng khác.

## 13. Tối ưu truy vấn và cập nhật: đừng biến một bài toán đơn giản thành quá tải

Một ưu điểm của Type 1 là số hàng dimension thường tương đối gọn: một BK chỉ có một hàng thay vì có thể có hàng chục phiên bản SCD2. Với yêu cầu “customer hiện tại theo phân khúc”, JOIN và lọc có thể đơn giản.

Nhưng không phải Type 1 luôn rẻ:

- **Upsert quy mô lớn** vẫn gây ghi nhiều trang dữ liệu, WAL, lock và index maintenance.
- **Chỉ mục trên thuộc tính thường đổi** như `segment` hoặc `region_code` phải được cập nhật khi ghi đè, có thể tốn chi phí.
- **Nguồn gửi lại toàn bộ snapshot** mỗi giờ có thể gây viết lại hàng triệu hàng nếu không phân biệt bản không đổi.
- **Dữ liệu phân nhóm lại quá khứ** có thể làm cache, materialized aggregate hoặc dashboard đã lưu số liệu trở nên lỗi thời.
- **Đổi BK/merge identity** không được giải quyết bằng cách chạy upsert đơn giản.

Cần phân biệt **transaction mới ở nguồn** và **rebuild bảng dẫn xuất**. Với Type 1, cập nhật tên/segment trong dim có thể đổi ngay kết quả JOIN trực tiếp; nhưng một bảng tổng hợp `monthly_sales_by_segment` đã materialize từ segment cũ không tự cập nhật. Phải thiết kế invalidation/rebuild hoặc tổng hợp lại các partition/mốc bị ảnh hưởng, rồi đối soát.

### Index nào là cần thiết?

- `UNIQUE(tenant_id, customer_bk)` là bắt buộc theo grain khi muốn chống trùng.
- `PRIMARY KEY(customer_sk)` và khóa tổ hợp tham chiếu bảo vệ liên kết với fact.
- Chỉ mục `(tenant_id, segment, region_code)` có thể hữu ích nếu thường lọc nhóm khách theo tenant.
- Chỉ mục ở fact theo `(tenant_id, customer_sk, ordered_at)` phù hợp nếu phân tích khách cụ thể hoặc JOIN có điều kiện; không thể thay thế thử nghiệm workload.
- Với hệ columnar/MPP, chiến lược partition/clustering/encoding khác PostgreSQL; không bê nguyên mọi index row-store sang.

Đo P95/P99 truy vấn theo nhu cầu, số bản cập nhật thực sự khác thuộc tính, bloat, lock contention, thời gian backfill và chi phí làm mới aggregate. Type 1 làm ít việc về lịch sử **không có nghĩa** vận hành không cần giám sát.

## 14. Schema evolution, lineage và quyền riêng tư

### Khi thêm trường vào dimension

Ví dụ cần thêm `loyalty_tier`. Trước tiên xác định: đây là **phân loại hiện hành** hay **mức hạng tại thời điểm phát sinh ưu đãi**? Nếu chỉ cần current, có thể bổ sung thuộc tính Type 1. Nếu cần giải thích một ưu đãi năm ngoái, phải lưu lịch sử tại nơi phù hợp thay vì chỉ thêm cột hiện tại.

Thực hiện migration có kiểm soát: thêm cột và giá trị thiếu có nghĩa, backfill từ nguồn có căn cứ, cập nhật kiểm thử ETL, điều chỉnh semantic layer, xác nhận các báo cáo bị ảnh hưởng. Đừng tự gán `UNKNOWN` = `STANDARD` chỉ để loại bỏ NULL hoặc điền cho đủ mẫu.

### Lineage: đã ghi đè không có nghĩa mất mọi nguồn gốc

Bảng Type 1 có thể giữ `source_revision`, metadata lần nạp và **tham chiếu nguồn** để biết dữ liệu hiện tại đến từ đâu. Nếu yêu cầu audit các giá trị trước/sau, phải lưu ở **kho lịch sử có quyền và retention riêng**; Type 1 bản thân nó không phải nơi bảo tồn đầy đủ lịch sử.

Đối với doanh nghiệp tích hợp nhiều nguồn, cần thêm quy tắc về **nguồn có thẩm quyền theo từng thuộc tính**, ưu tiên nguồn, thời điểm đồng bộ, kiểm tra chéo, và định danh không xung đột. Cùng một khách có thể có tên ở CRM và tên trên hóa đơn với mục đích khác nhau; không nên áp một quy tắc “bản mới nhất thắng” chung cho mọi trường.

### Quyền riêng tư

- Dimension có thể chứa tên, địa chỉ, phân khúc nhạy cảm hoặc dữ liệu có thể nhận dạng cá nhân. Chỉ nạp dữ liệu thật sự cần cho phân tích.
- Ghi đè tên trong dimension **không xóa tên cũ** khỏi staging, backups, export, audit, cache, bảng hợp nhất hay kho downstream.
- Cần chính sách quyền đọc theo tenant/nhóm, thời hạn lưu và quy trình xóa/ẩn danh khi có yêu cầu phù hợp.
- Không coi surrogate key hoặc business key được băm là **ẩn danh tuyệt đối**: chúng có thể liên kết trở lại một người qua bảng mapping và fact.
- Nếu dữ liệu phải bị xóa/ẩn danh, không chỉ sửa `display_name = 'REDACTED'` trong một bảng rồi tuyên bố đã hoàn tất. Phải đánh giá mọi bản sao và giới hạn của quá trình phục hồi.

**Điểm kiến trúc:** Type 1 phục vụ **cách diễn giải hiện hành** của fact, nhưng không tự quy định retention, bảo mật hay xóa lịch sử ở toàn hệ thống.

## 15. Những sai lầm phổ biến khi triển khai Type 1

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Mỗi lần thay tên lại INSERT một hàng chiều | Đó là phiên bản hóa khác Type 1; fact có thể trỏ sai SK. | UPDATE trên cùng business key/SK. |
| Đổi `customer_sk` cùng lúc đổi `segment` | Fact cũ bị mồ côi hoặc phải cập nhật hàng loạt. | Giữ SK bất biến cho cập nhật Type 1. |
| Ghi đè mọi thuộc tính vì “bảng là Type 1” | Mất phân khúc/địa chỉ/giá vốn cần lịch sử. | Gán chính sách SCD cho từng thuộc tính. |
| Dùng `MAX(ingested_at)` chọn bản thắng | Message đến muộn ghi đè dữ liệu mới. | Version/cursor nguồn có hợp đồng thứ tự. |
| Đầu vào patch thiếu trường bị gán NULL | Xóa nhầm thuộc tính đúng. | Phân biệt missing và explicit NULL. |
| `COALESCE` giữ mọi giá trị cũ khi nguồn gửi NULL | Không thể chủ động xóa giá trị đã hết hiệu lực. | Quy tắc NULL dựa trên full-state/patch contract. |
| Không xử lý payload cùng revision khác nhau | Dữ liệu mâu thuẫn bị bỏ qua im lặng. | Phát hiện và cách ly conflict. |
| Đổi business key như sửa nhãn | Nối sai hai người/đứt liên kết fact. | Master-data mapping và kiểm chứng identity. |
| Gọi báo cáo current segment là “tại thời điểm mua” | Hiểu sai lịch sử. | Type 2/historical fact hoặc đặt tên metric rõ. |
| Ghi đè giá bán trên fact theo giá catalog mới | Làm thay đổi chứng từ giao dịch. | Fact giao dịch lưu giá tại thời điểm chốt. |
| Quên inferred member khi fact đến sớm | Orphan fact hoặc unknown kéo dài. | Inferred/unknown member có quy trình hoàn thiện. |
| Dùng Type 1 rồi tuyên bố có full audit | Không còn giá trị before/after trong dimension. | Audit/history riêng nếu có yêu cầu. |
| Chỉ cập nhật dimension, không làm mới aggregate | Dashboard materialized vẫn phân nhóm cũ. | Invalidation/recompute và đối soát KPI. |

## 16. Bài tập thực hành: nạp Type 1 và giải thích thay đổi báo cáo

**Bối cảnh:** nền tảng bán khóa học có `fact_enrollment` (một hàng cho mỗi lượt ghi danh) và `dim_student` (một hàng mỗi học viên). Hệ CRM cung cấp thông tin học viên theo `student_bk` và `source_revision` tăng dần. Người phân tích muốn xem số lượt ghi danh theo **khu vực hiện tại** của học viên. Ban vận hành cũng cần biết học viên thuộc khu vực nào **khi ghi danh**.

Tập dữ liệu:

| Bản ghi | student_bk | source_revision | region | Ghi chú |
| --- | --- | ---: | --- | --- |
| A | ST-07 | 12 | NORTH | Có trong dimension đầu kỳ. |
| B | ST-07 | 14 | SOUTH | CRM cập nhật sau đó. |
| C | ST-07 | 13 | CENTRAL | Message đến muộn sau B. |
| D | ST-07 | 14 | SOUTH | Callback/nạp lặp. |
| E | ST-09 | 5 | NULL | CRM xác nhận không biết vùng. |

Trước B, học viên `ST-07` có `student_sk = 305` và 20 lượt ghi danh trong tháng trước.

### Yêu cầu

1. **Chọn grain và khóa:** định nghĩa `(tenant_id, student_bk)` và `student_sk`, cách fact tham chiếu dimension; giải thích không cấp SK mới khi B được nạp.
2. **Định nghĩa Type 1:** sau B, C và D, region của ST-07 phải là gì? Vì sao?
3. **Tính kết quả dashboard:** 20 lượt ghi danh tháng trước chuyển sang nhóm nào khi truy vấn theo current region? Giá trị fact có đổi không?
4. **Phân biệt câu hỏi lịch sử:** nếu muốn trả lời vùng lúc ghi danh, đề xuất SCD2 hoặc attribute-at-event có định nghĩa hợp lệ; giải thích vì sao Type 1 không đủ.
5. **DDL:** viết bảng `dim_student` với unique tenant/BK, surrogate key, `source_revision` và metadata; tạo fact với FK bảo vệ tenant.
6. **Upsert:** viết `INSERT ... ON CONFLICT DO UPDATE` có điều kiện revision mới hơn; dùng `IS DISTINCT FROM` để xác định khi nào thuộc tính thật sự đổi.
7. **Xử lý NULL:** nguồn gửi record đầy đủ cho ST-09 với region NULL. Vì sao không nên tự giữ vùng cũ bằng `COALESCE`? Nếu đây chỉ là patch thiếu trường thì làm gì khác?
8. **Dữ liệu lỗi:** hai payload có cùng `student_bk + source_revision` nhưng region khác nhau; đề xuất xử lý thay vì tự chọn theo thời gian nhận.
9. **Fact đến trước:** lượt ghi danh đến trước thông tin ST-11; mô hình inferred member hay unknown member phù hợp, và chính sách backfill nào cần có?
10. **Báo cáo đã materialize:** `monthly_enrollments_by_region` chứa tổng cũ. Chọn cách làm mới/đối soát sau khi dimension thay vùng.
11. **Kiểm thử:** liệt kê kiểm tra retry, concurrency, uniqueness, SK ổn định, region NULL, phân quyền tenant và số liệu KPI.
12. **ADR:** chọn những thuộc tính của học viên dùng Type 1 và những thuộc tính cần Type 2, kèm lý do từ các câu hỏi nghiệp vụ thực tế.

### Bảng kiểm tự đánh giá

| Tiêu chí | Kết quả đúng |
| --- | --- |
| **Một hàng/BK** | Một `(tenant_id, student_bk)` có một dimension row Type 1. |
| **SK ổn định** | Fact cũ và mới vẫn tham chiếu cùng `student_sk` sau cập nhật. |
| **Chống cập nhật lùi** | Revision 13 đến sau 14 không được ghi đè 14. |
| **Chống xử lý lặp** | Revision 14 lặp không thay đổi và không tạo hàng mới. |
| **Ngữ nghĩa NULL** | Phân biệt full-state NULL với patch thiếu trường. |
| **Báo cáo lịch sử** | Biết Type 1 phân loại lại fact cũ theo thuộc tính hiện hành. |
| **Lịch sử cần giữ** | Có nguồn lịch sử/Type 2 nếu cần truy vấn as-of. |
| **Đối soát** | Không nhân bản fact khi JOIN; đối chiếu lại aggregate đã materialize. |
| **Quản trị** | Có lineage, chính sách xóa, xử lý conflict và quyền theo tenant. |

**Kết luận:** SCD Type 1 là lựa chọn **ghi đè thuộc tính mô tả của một thực thể trên cùng hàng dimension**, giữ khóa thay thế ổn định và cập nhật các phép JOIN lịch sử theo cách phân nhóm hiện tại. Nó phù hợp khi dữ liệu cũ cần được **thay thế**, không phù hợp khi giá trị cũ vẫn **đúng và có ý nghĩa tại thời điểm trước đó**. Muốn mô hình bền vững, hãy quyết định từ câu hỏi báo cáo, xác định grain/khóa, quy tắc nguồn và cập nhật đồng thời; sau đó thiết kế ETL, chỉ mục, kiểm thử và lịch sử bổ sung đúng mức cần thiết.
