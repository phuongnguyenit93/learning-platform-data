# Dữ kiện đến trễ, điều chỉnh và bản ghi bù trừ

Trong kho dữ liệu phân tích, một đơn hàng có thể được tạo vào thứ Hai nhưng đến thứ Tư hệ thống nguồn mới gửi sự kiện bán hàng. Một tuần sau, bộ phận chăm sóc khách hàng sửa số tiền chiết khấu. Đến cuối tháng, khách hủy một phần hoặc trả hàng. Nếu pipeline chỉ **nạp một lần rồi không bao giờ xem lại dữ liệu**, báo cáo thiếu giao dịch. Nếu pipeline **ghi đè tùy tiện**, không ai biết số liệu đã thay đổi vì lý do gì. Nếu pipeline **thêm mọi bản tin thành một giao dịch mới**, doanh thu có thể bị nhân đôi.

Những vấn đề này thường được gọi là **dữ kiện đến trễ (late-arriving facts)**, **điều chỉnh (adjustments/corrections)** và **bản ghi bù trừ (compensating records)**. Chúng liên quan đến cùng một câu hỏi lớn:

> Khi sự thật nghiệp vụ được biết muộn, được sửa hoặc bị đảo ngược, làm thế nào để fact table vẫn có grain đúng, tổng hợp đúng và truy vết được những gì hệ thống đã biết ở từng thời điểm?

Bài này thuộc chương **Bảng dữ kiện** của module **DATABASE_DATA_MODELING**. Trọng tâm là chuyển những quy tắc nghiệp vụ về thời gian và thay đổi dữ liệu thành **mô hình fact, khóa, ràng buộc, luồng ETL/ELT, phép đối soát và SQL có thể kiểm chứng**. Nội dung so sánh cách tổ chức dữ liệu quan hệ, document, đồ thị và phân tích khi cần; ví dụ triển khai dùng PostgreSQL để minh họa, không phải một hệ thống kế toán hoặc xử lý thanh toán hoàn chỉnh.

## 1. Ba tình huống phải phân biệt

### 1.1. Dữ kiện đến trễ: sự kiện đúng, nhưng biết muộn

Một dòng bán hàng thực sự xảy ra ngày **10/10/2026**, nhưng hệ thống phân tích chỉ nhận được lúc **13/10/2026** do mạng gián đoạn. Dữ kiện không sai; chỉ có **thời điểm đến** khác **thời điểm xảy ra**.

Nếu nhóm báo cáo phân tích doanh số **theo ngày bán**, bản ghi thuộc ngày 10/10. Nếu nhóm vận hành phân tích **số giao dịch được tiếp nhận ngày nào**, nó thuộc ngày 13/10. Hai câu hỏi đều hợp lệ nhưng phải dùng hai trục thời gian khác nhau.

### 1.2. Điều chỉnh: giá trị đã ghi nhận cần sửa

Một dòng bán ban đầu ghi **200.000 VND** cho hai sản phẩm. Ngày 16/10, dữ liệu nguồn xác nhận đã bỏ sót khoản giảm giá **20.000 VND**.

Tùy quy tắc báo cáo, hệ thống có thể:

- Cập nhật số tiền của bản ghi bán từ 200.000 xuống 180.000.
- Giữ bản ghi gốc, thêm **bản ghi điều chỉnh -20.000** có tham chiếu tới dòng bán.
- Đảo ngược bản ghi ban đầu rồi ghi lại bản ghi đúng.
- Giữ kỳ báo cáo đã khóa, ghi điều chỉnh vào **kỳ hiện tại** thay vì thay số kỳ trước.

Đây là những chiến lược khác nhau về **mô hình lịch sử và cách ghi nhận**, không phải bốn cú pháp SQL có thể thay thế tùy ý.

### 1.3. Bù trừ/đảo ngược: một hiệu ứng cần được triệt tiêu có truy vết

Ngày 20/10, giao dịch ở ví dụ bị hủy theo nghiệp vụ. Thay vì xóa dòng bán cũ, có thể ghi một **movement âm** để bù hiệu ứng còn hiệu lực.

Nếu dòng bán có giá trị 200.000 và đã điều chỉnh -20.000, thì hiệu ứng hiện tại là **+180.000**. Một bản ghi đảo ngược toàn bộ **trạng thái còn lại** cần -180.000, không phải -200.000 nếu vẫn giữ khoản điều chỉnh -20.000: khi đó tổng sẽ thành **-20.000**, sai nếu mục tiêu là bằng 0.

Bản ghi đảo ngược phải có **đích tham chiếu, lý do, định danh sự kiện duy nhất và chính sách về thời điểm ghi nhận**. Một số nghiệp vụ dùng cặp “đảo toàn bộ bản ghi trước + ghi lại bản ghi thay thế” thay vì điều chỉnh số chênh lệch; không được trộn hai cách mà không xác định rõ các bản ghi nào cần bị vô hiệu.

### Bảng phân biệt nhanh

| Tình huống | Sự thật nghiệp vụ | Dữ liệu thêm/sửa | Nguy cơ chính |
| --- | --- | --- | --- |
| Đến trễ | Sự kiện đã xảy ra từ trước | Nạp muộn theo ngày nghiệp vụ gốc | Thiếu kỳ cũ, gán nhầm sang ngày nạp |
| Điều chỉnh | Giá trị hoặc thuộc tính ban đầu chưa đúng | Sửa bản gốc hoặc thêm phần chênh lệch | Đếm trùng, mất lịch sử, sai số kỳ |
| Bù trừ/đảo ngược | Hiệu ứng trước cần triệt tiêu | Ghi movement đối ứng có liên kết | Đảo hai lần, đảo sai số dư |
| Trả hàng | Có **sự kiện mới** sau bán | FactReturn hoặc movement theo nghiệp vụ | Coi trả hàng là lỗi dữ liệu, lẫn với hủy |
| Bản tin gửi lại | **Không có sự kiện mới** | Không được cộng thêm fact | Nạp trùng do retry/CDC |
| Dimension đến muộn | Sự kiện có thật nhưng thiếu ngữ cảnh tra chiều | Bổ sung/phiên bản hóa dimension | Gán nhầm phiên bản hiện hành |

**Điểm cốt lõi:** “Đến trễ”, “điều chỉnh”, “đảo ngược” và “bản tin gửi lặp” có thể xuất hiện cùng lúc nhưng cần quy tắc xử lý khác nhau.

## 2. Viết grain trước khi viết bảng

Một fact table muốn được điều chỉnh đúng phải có **định nghĩa một hàng rõ ràng**.

Ví dụ có ba cách tổ chức:

| Mô hình fact | Một hàng đại diện | Định danh tự nhiên cần có | Hành vi thay đổi |
| --- | --- | --- | --- |
| **FactSalesLine hiện trạng** | Một dòng bán đã biết ở trạng thái mới nhất | source_system + sale_line_id | Có thể UPDATE cùng hàng, giữ lịch sử ở nơi khác |
| **FactSalesMovement** | Một **sự kiện/delta bất biến** tác động đến một dòng bán | source_system + source_event_id | INSERT sự kiện mới; tổng SUM(delta) cho hiệu ứng cộng dồn |
| **FactInventorySnapshot** | Một sản phẩm–cửa hàng ở một thời điểm chụp | date + product + store | Sửa/phiên bản hóa **giá trị trạng thái**, không cộng các snapshot |
| **FactOrderLifecycle** | Một đơn hàng qua các cột mốc tiến trình | source_system + order_id | Cập nhật mốc theo sự kiện đến, có xử lý bản tin sai thứ tự |

Chỉ chọn **FactSalesMovement** khi đại lượng có thể được biểu diễn bằng các **chênh lệch cộng được** cùng định nghĩa: số lượng delta, số tiền delta. Một sự kiện “giá hiện tại là 85.000” là **giá trị tuyệt đối**, không tự động là “cộng thêm 85.000”. Phải chuyển thành chênh lệch so với trạng thái trước nếu muốn đưa vào cùng mô hình delta.

Ngược lại, một snapshot tồn kho **20 chiếc cuối ngày** và một snapshot sửa lại **18 chiếc cuối ngày** là hai **phiên bản của một phép đo**, không phải hai lượng tồn để cộng thành 38 chiếc.

### 2.1. Grain của sự kiện so với grain của báo cáo

Fact movement có grain “một source event được chấp nhận”, nhưng báo cáo có thể muốn:

- Một hàng theo **ngày bán × sản phẩm × cửa hàng**.
- Một hàng theo **đơn hàng × dòng bán** ở trạng thái hiện tại.
- Một hàng theo **ngày ghi sổ × loại nghiệp vụ**.
- Một snapshot “**những gì báo cáo biết ở ngày 15/10**”.

Vì vậy, grain của fact không nhất thiết giống grain của một bảng tổng hợp/dashboard. Phải quy định cách chuyển grain trước khi SUM.

### 2.2. Khóa chống nạp trùng không phải khóa nghiệp vụ của dòng bán

Một dòng bán có thể có:

~~~text
sale_line_id = ORDER-901:1
~~~

và nhiều sự kiện:

~~~text
source_event_id = SALE-1
source_event_id = SALE-1-PRICE-ADJ
source_event_id = SALE-1-CANCEL
~~~

Khóa của fact movement phải phân biệt **cả ba sự kiện**. Nếu đặt UNIQUE(sale_line_id) trên fact movement, không thể ghi điều chỉnh; nếu bỏ UNIQUE(source_event_id), một bản tin bị retry có thể sinh hai dòng giống nhau.

**Quy tắc:** phân biệt **định danh đối tượng nghiệp vụ**, **định danh dòng giao dịch**, **định danh sự kiện/phiên bản nguồn** và **surrogate key** trong kho dữ liệu.

## 3. Các trục thời gian: sự kiện, hiệu lực, ghi sổ và tiếp nhận

Một hệ thống có thể cần tối thiểu bốn thời điểm.

| Thời điểm | Ý nghĩa | Trả lời câu hỏi |
| --- | --- | --- |
| **occurred_at / event_time** | Lúc sự kiện thực tế xảy ra tại nguồn | Khách mua/hủy/điều chỉnh vào lúc nào? |
| **business_effective_date** | Ngày nghiệp vụ được quy cho hiệu ứng khi phân tích | Điều chỉnh này ảnh hưởng doanh số kỳ nào? |
| **posting_date** | Ngày hệ thống ghi nhận vào sổ/kỳ công bố | Điều chỉnh được hạch toán ở kỳ nào? |
| **loaded_at / ingested_at** | Lúc kho dữ liệu thực sự nhận và chấp nhận bản tin | Báo cáo đã biết sự kiện này từ khi nào? |

Ví dụ:

| Movement | Occurred | Effective | Posting | Loaded | Số tiền delta |
| --- | --- | --- | --- | --- | ---: |
| Bán hai chiếc | 10/10 | 10/10 | 13/10 | 13/10 | +200.000 |
| Sửa chiết khấu | 16/10 | 10/10 | 16/10 | 16/10 | -20.000 |
| Hủy toàn bộ | 20/10 | 20/10 | 20/10 | 20/10 | -180.000 |

**Đây là một lựa chọn chính sách minh họa.** Điều chỉnh chiết khấu được quy hiệu lực về ngày bán 10/10 nhưng được ghi sổ ngày 16/10. Hủy giao dịch là một sự kiện mới có hiệu lực ngày 20/10. Một doanh nghiệp có thể áp chính sách khác, nhất là khi kỳ kế toán đã khóa.

### 3.1. “Dữ liệu đúng tại thời điểm nào?” có hai nghĩa

Có ít nhất hai kiểu câu hỏi:

1. **As-of business time:** tính các sự kiện có hiệu lực nghiệp vụ không muộn hơn ngày **t**.
2. **As-known-at / system time:** chỉ dùng các sự kiện hệ phân tích **đã tiếp nhận trước mốc k**.

Phối hợp hai trục giúp hỏi:

> “Tại cuối ngày 15/10, hệ thống **đã biết** doanh số có hiệu lực ngày 10/10 là bao nhiêu?”

Đây là nhu cầu kiểm toán và giải thích vì sao báo cáo lịch sử thay đổi sau khi nhận thêm dữ liệu.

Một bảng movement **append-only** với loaded_at bất biến hỗ trợ các truy vấn kiểu này, miễn là dữ liệu không bị xóa/sửa âm thầm và các phiên bản dimension cần thiết cũng được lưu lịch sử. Nếu được phép UPDATE trực tiếp event cũ mà không giữ phiên bản, loaded_at đơn lẻ **không còn đủ** để tái hiện đúng báo cáo cũ.

### 3.2. Ngày nghiệp vụ phải có múi giờ và quy ước rõ ràng

Một sự kiện lúc 23:30 UTC có thể rơi vào ngày hôm sau ở Việt Nam. Nếu doanh nghiệp báo cáo theo giờ Asia/Ho_Chi_Minh, khóa DimDate phải được suy từ **instant + timezone nghiệp vụ**, không ngầm dùng ngày UTC hoặc timezone máy chạy ETL.

Đối với tổ chức đa thị trường, Store có thể có timezone riêng; phải quyết định “ngày doanh thu theo timezone cửa hàng” hay “ngày tập đoàn theo UTC”. Hai cách có thể tạo kết quả theo ngày khác nhau nhưng đều hợp lệ nếu được ghi nhãn.

## 4. Chọn chiến lược: UPDATE, delta append-only hay đảo–ghi lại

Không phải mọi fact đều bắt buộc append-only. Quyết định phụ thuộc tính bất biến, yêu cầu lịch sử và chi phí đọc/ghi.

### 4.1. Cập nhật tại chỗ (in-place correction)

Ví dụ:

~~~sql
UPDATE fact_sales_line
SET net_amount_vnd = 180000
WHERE source_system = 'checkout'
  AND source_sale_line_id = 'ORDER-901:1';
~~~

*Đây là ví dụ khái niệm; giả định bảng fact_sales_line với các cột đã nêu tồn tại.*

Ưu điểm: truy vấn trạng thái hiện tại đơn giản; không phải cộng các delta. Nhược điểm: mất khả năng biết đã từng ghi nhận 200.000 nếu không có **audit/version table hoặc CDC history**. UPDATE cũng có thể làm thay đổi kết quả các báo cáo đã phát hành.

Phù hợp khi fact đại diện **trạng thái đã biết mới nhất**, còn lịch sử thay đổi được lưu ở hệ thống có trách nhiệm khác hoặc không bắt buộc lưu.

### 4.2. Thêm chênh lệch (delta adjustment)

Thay vì sửa 200.000 thành 180.000:

~~~text
SALE:       +200.000
ADJUSTMENT:  -20.000
--------------------
Hiện trạng: +180.000
~~~

Ưu điểm: có dấu vết điều chỉnh và có thể tái hiện số đã biết theo thời điểm nhận dữ liệu. Nhược điểm: truy vấn hiện trạng phải tổng hợp; số lượng movement tăng; khó hơn khi xử lý khóa, bản tin đảo và điều chỉnh sai thứ tự.

Phù hợp với measure **additive**, có định danh sự kiện đáng tin cậy, cần audit và xử lý ghi lặp.

### 4.3. Đảo toàn bộ rồi ghi phiên bản đúng (reverse and rebook)

Một cách khác là:

~~~text
Bản gốc:             +200.000
REVERSAL bản gốc:    -200.000
REBOOK bản đúng:     +180.000
----------------------------
Hiện trạng:          +180.000
~~~

Cách này không giống thêm delta -20.000. Nếu đã dùng **ADJUSTMENT -20.000** và sau đó vẫn ghi **REVERSAL -200.000, REBOOK +180.000** mà không xử lý adjustment cũ, tổng cuối sẽ là 160.000, sai.

Bắt buộc chọn rõ **họ logic**:

- **Delta changes:** ghi mỗi thay đổi chênh lệch đối với trạng thái đang có.
- **Full replacement:** đảo các hiệu ứng của phiên bản cũ rồi ghi phiên bản mới, với cơ chế khống chế những adjustment gắn phiên bản cũ.

Một bản tin “sửa giá thành 180.000” **không thể** đưa thẳng vào cột delta +180.000 nếu chưa biết 180.000 là **giá trị mới** hay **phần chênh**.

### 4.4. Bản ghi bù trừ không luôn là sự kiện trả hàng

**Bù trừ kỹ thuật** thường đảo ảnh hưởng của một bản ghi sai hoặc một quyết định hủy. **Trả hàng nghiệp vụ** là sự kiện mới có nguyên nhân, ngày trả, kho nhập lại, hoàn tiền và có thể phí. Không nên gộp tất cả thành một delta âm rồi gọi chung “return” nếu doanh nghiệp cần phân tích riêng số lần hủy, số hàng trả, chất lượng sản phẩm hoặc nguyên nhân hoàn tiền.

Một hệ có thể có cả **FactSalesMovement** và **FactReturnLine**. Chúng là những sự kiện khác loại nhưng phải có quy tắc tính KPI thống nhất để **không trừ doanh thu hai lần**.

## 5. Lược đồ PostgreSQL cho fact movement bất biến

Giả định ví dụ học tập:

- Mọi giá trị tiền trong fact được lưu theo **VND nguyên đồng**, không trộn tiền tệ.
- Một source_sale_line_id có đúng một **SALE gốc** trong nguồn đã chọn; mọi adjustment/reversal tham chiếu SALE gốc cùng source_system.
- Movement ghi **chênh lệch** số lượng và **chênh lệch** số tiền sau chiết khấu.
- Fact không bị UPDATE/DELETE sau khi chấp nhận. Đây là **quy tắc ghi của pipeline**, không phải điều chỉ riêng DDL dưới đây bảo đảm.
- Ngày hiệu lực có thể khác ngày ghi sổ và ngày tiếp nhận.
- Mỗi movement tham chiếu dimension Product/Store có phiên bản đã được lựa chọn theo chính sách nghiệp vụ.

### 5.1. Bảng chiều tối giản

~~~sql
-- PostgreSQL; chạy trong database thử nghiệm riêng.
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,           -- ví dụ 20261010
    calendar_date DATE NOT NULL UNIQUE
);

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE dim_store (
    store_key BIGINT PRIMARY KEY,
    store_code TEXT NOT NULL UNIQUE,
    store_name TEXT NOT NULL
);
~~~

Một Product có thể có nhiều phiên bản Type 2 dùng cùng product_code, nên không đặt UNIQUE(product_code) cho toàn bộ dim_product. Việc **cấm phiên bản chồng lấp** phải được thiết kế thêm; PRIMARY KEY(product_key) chỉ bảo vệ định danh của **một phiên bản**.

### 5.2. Bảng fact movement

~~~sql
CREATE TABLE fact_sales_movement (
    movement_key BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    -- Dedupe theo định danh sự kiện từ nguồn:
    source_system TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    source_sale_line_id TEXT NOT NULL,
    related_source_event_id TEXT,

    movement_kind TEXT NOT NULL
        CHECK (movement_kind IN ('SALE', 'ADJUSTMENT', 'REVERSAL')),

    -- Xác định các trục thời gian:
    occurred_at TIMESTAMPTZ NOT NULL,
    effective_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    posting_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Ngữ cảnh để phân tích:
    product_key BIGINT NOT NULL REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL REFERENCES dim_store(store_key),

    -- Delta được phép âm cho adjustment/reversal:
    quantity_delta INTEGER NOT NULL,
    net_amount_delta_vnd BIGINT NOT NULL,

    CONSTRAINT uq_source_sales_event
        UNIQUE (source_system, source_event_id),

    CONSTRAINT fk_movement_related_event
        FOREIGN KEY (source_system, related_source_event_id)
        REFERENCES fact_sales_movement(source_system, source_event_id),

    CONSTRAINT movement_shape CHECK (
        (
            movement_kind = 'SALE'
            AND related_source_event_id IS NULL
            AND quantity_delta > 0
            AND net_amount_delta_vnd >= 0
        )
        OR
        (
            movement_kind = 'ADJUSTMENT'
            AND related_source_event_id IS NOT NULL
            AND (
                quantity_delta <> 0
                OR net_amount_delta_vnd <> 0
            )
        )
        OR
        (
            movement_kind = 'REVERSAL'
            AND related_source_event_id IS NOT NULL
            AND quantity_delta < 0
            AND net_amount_delta_vnd <= 0
        )
    )
);

-- Áp dụng đúng giả định: mỗi dòng nghiệp vụ chỉ có một SALE gốc.
CREATE UNIQUE INDEX uq_one_original_sale_per_line
ON fact_sales_movement (source_system, source_sale_line_id)
WHERE movement_kind = 'SALE';

CREATE INDEX idx_sales_movement_effective
ON fact_sales_movement
    (effective_date_key, product_key, store_key);

CREATE INDEX idx_sales_movement_posting
ON fact_sales_movement
    (posting_date_key, product_key, store_key);

CREATE INDEX idx_sales_movement_line
ON fact_sales_movement
    (source_system, source_sale_line_id, loaded_at);
~~~

**Những điều lược đồ trên bảo vệ được:**

- Không có hai event cùng source_system + source_event_id.
- Movement có loại và hình dạng delta theo giả định.
- Adjustment/reversal phải trỏ tới **một event có định danh tồn tại** trong cùng source_system.
- Các FK dimension dùng khóa surrogate hợp lệ.
- Trong giả định một SALE gốc/một dòng, không nhập SALE gốc lần thứ hai bằng event_id khác.

**Những điều lược đồ trên chưa thể tự bảo vệ:**

1. related_source_event_id có thực sự trỏ tới **SALE gốc của chính source_sale_line_id** hay không. FK chỉ kiểm tra tồn tại, không kiểm tra loại/same line.
2. Một reversal có phải **chính xác số dư còn lại**, có bị đảo hai lần hoặc làm âm số lượng ròng không.
3. effective_date_key có đúng với chính sách ngày nghiệp vụ của occurred_at và timezone không.
4. product_key/store_key của adjustment có khớp đúng version/scope của dòng gốc không.
5. Một event có được **ghi bất biến** hay không; DDL không ngăn writer có quyền thực hiện UPDATE/DELETE.
6. Dữ liệu đến muộn nhưng nguồn chưa gửi đầy đủ có làm dashboard tạm thiếu không.
7. Kết quả tiền có tuân thủ quy tắc thuế, phí, hoàn tiền, tỷ giá và kỳ đã khóa không.

Những bất biến này cần thêm **quyền DB, trigger/procedure, giao dịch, quy tắc ingest và kiểm tra đối soát**. Không được diễn giải ví dụ DDL là hệ thống ledger hoàn chỉnh.

### 5.3. Chú ý khóa tự tham chiếu và nạp sai thứ tự

Ví dụ FK tham chiếu event gốc sẽ từ chối ADJUSTMENT nếu SALE gốc chưa có trong fact. Nhưng trong thực tế, **bản tin điều chỉnh có thể đến trước bản tin bán** vì hệ thống truyền dẫn không bảo đảm thứ tự.

Các chính sách có thể chọn:

- **Staging/pending:** giữ adjustment trong hàng chờ, nạp khi bản gốc đến.
- **Inferred original:** tạo bản ghi neo có định danh, sau đó điền dữ liệu khi có nguồn; cần thiết kế bảng/loại hàng riêng chứ không dùng SALE giả không có measure chính xác.
- **Tạm nhận sự kiện độc lập có kiểm soát:** không tạo FK tới event gốc ở fact append-only, nhưng giữ hàng lỗi và đánh dấu chưa được cộng vào mart cho đến khi quan hệ khớp.
- **Tách ledger và trạng thái materialized:** ingest nguồn theo thứ tự bất kỳ nhưng chỉ phát hành các delta đủ điều kiện khi mọi phụ thuộc đã giải quyết.

Không xóa FK rồi coi như đã giải quyết xong bài toán thứ tự đến. Phải quyết định **phạm vi dữ liệu “chưa hoàn chỉnh” được phép xuất hiện** trong dashboard và cách phát lại hàng đợi.

## 6. Ví dụ ba movement: bán muộn, sửa tiền, hủy

Dữ liệu minh họa:

- **10/10/2026:** bán 2 chiếc, giá trị 200.000 VND.
- **13/10:** fact SALE đến muộn, được ghi sổ và nạp.
- **16/10:** xác định chiết khấu 20.000 bị thiếu; adjustment có hiệu lực về ngày bán 10/10 nhưng ghi sổ ngày 16/10.
- **20/10:** hủy toàn bộ phần bán còn hiệu lực; reversal số lượng -2 và tiền -180.000, có hiệu lực và ghi sổ ngày 20/10.

### 6.1. Dữ liệu dimension

~~~sql
INSERT INTO dim_date (date_key, calendar_date) VALUES
    (20261010, DATE '2026-10-10'),
    (20261013, DATE '2026-10-13'),
    (20261016, DATE '2026-10-16'),
    (20261020, DATE '2026-10-20');

INSERT INTO dim_product
    (product_key, product_code, product_name, valid_from, valid_to)
VALUES
    (101, 'P-001', 'Tai nghe Bluetooth',
     TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL);

INSERT INTO dim_store (store_key, store_code, store_name)
VALUES (11, 'HCM-01', 'Cửa hàng trung tâm');
~~~

### 6.2. Các event bất biến

~~~sql
-- 1. SALE: xảy ra 10/10 nhưng nhận, ghi sổ ngày 13/10.
INSERT INTO fact_sales_movement
    (movement_key, source_system, source_event_id,
     source_sale_line_id, related_source_event_id,
     movement_kind, occurred_at, effective_date_key,
     posting_date_key, loaded_at, product_key, store_key,
     quantity_delta, net_amount_delta_vnd)
VALUES
    (1001, 'checkout', 'SALE-1', 'ORDER-901:1', NULL,
     'SALE', TIMESTAMPTZ '2026-10-10 11:00:00+07',
     20261010, 20261013,
     TIMESTAMPTZ '2026-10-13 08:00:00+07',
     101, 11, 2, 200000);

-- 2. ADJUSTMENT: biết 16/10, nhưng hiệu lực về 10/10.
INSERT INTO fact_sales_movement
    (movement_key, source_system, source_event_id,
     source_sale_line_id, related_source_event_id,
     movement_kind, occurred_at, effective_date_key,
     posting_date_key, loaded_at, product_key, store_key,
     quantity_delta, net_amount_delta_vnd)
VALUES
    (1002, 'checkout', 'SALE-1-PRICE-ADJ', 'ORDER-901:1',
     'SALE-1', 'ADJUSTMENT',
     TIMESTAMPTZ '2026-10-16 09:00:00+07',
     20261010, 20261016,
     TIMESTAMPTZ '2026-10-16 09:05:00+07',
     101, 11, 0, -20000);

-- 3. REVERSAL: hủy hiệu ứng còn lại vào 20/10.
INSERT INTO fact_sales_movement
    (movement_key, source_system, source_event_id,
     source_sale_line_id, related_source_event_id,
     movement_kind, occurred_at, effective_date_key,
     posting_date_key, loaded_at, product_key, store_key,
     quantity_delta, net_amount_delta_vnd)
VALUES
    (1003, 'checkout', 'SALE-1-CANCEL', 'ORDER-901:1',
     'SALE-1', 'REVERSAL',
     TIMESTAMPTZ '2026-10-20 14:00:00+07',
     20261020, 20261020,
     TIMESTAMPTZ '2026-10-20 14:01:00+07',
     101, 11, -2, -180000);
~~~

Ở ví dụ học tập, loaded_at được điền bằng mốc giả định để tái hiện báo cáo theo thời điểm. Trong production, nó thường là **timestamp do pipeline/warehouse ghi tại thời điểm chấp nhận**, phải bất biến sau đó; không cho phía gửi tùy ý tự khai một thời điểm “đã nhận” để che độ trễ.

### 6.3. Trạng thái cuối của dòng bán

~~~sql
SELECT source_system, source_sale_line_id,
       SUM(quantity_delta) AS net_quantity,
       SUM(net_amount_delta_vnd) AS net_amount_vnd
FROM fact_sales_movement
GROUP BY source_system, source_sale_line_id;
-- checkout | ORDER-901:1 | 0 | 0
~~~

Kết quả **0 đơn vị, 0 VND** vì:

~~~text
Số lượng: +2  +0  -2 = 0
Tiền:    +200000 -20000 -180000 = 0
~~~

Chỉ từ tổng bằng 0 **không suy ra** rằng giao dịch chưa bao giờ tồn tại. Lịch sử vẫn cho biết từng có bán, sửa chiết khấu và hủy. Dashboard cần phân biệt **gross sales events**, **current net impact**, **cancellations** và các chỉ tiêu công bố khác; không dùng duy nhất SUM(delta) cho mọi câu hỏi.

## 7. Báo cáo theo ngày hiệu lực, ngày ghi sổ và mốc đã biết

### 7.1. Theo ngày hiệu lực nghiệp vụ

~~~sql
SELECT d.calendar_date AS business_date,
       SUM(f.quantity_delta) AS quantity_delta,
       SUM(f.net_amount_delta_vnd) AS net_amount_delta_vnd
FROM fact_sales_movement AS f
JOIN dim_date AS d ON d.date_key = f.effective_date_key
GROUP BY d.calendar_date
ORDER BY business_date;
~~~

Kết quả từ ví dụ:

| Ngày hiệu lực | Quantity delta | Amount delta (VND) |
| --- | ---: | ---: |
| 10/10/2026 | +2 | +180.000 |
| 20/10/2026 | -2 | -180.000 |

Khoản điều chỉnh -20.000 được **quy về ngày bán 10/10**, nên tổng ngày 10/10 được sửa từ 200.000 còn 180.000 sau khi sự kiện adjustment đến. Sự kiện hủy ngày 20/10 có hiệu lực vào ngày hủy nên tạo movement âm ngày 20/10.

**Đây là báo cáo movement theo ngày hiệu lực**, không nhất thiết là định nghĩa doanh thu kế toán. Nếu doanh nghiệp yêu cầu doanh thu ngày bán sau cùng phải bằng 0 khi hủy ngày 20, cần định nghĩa một **phép restatement theo cohort dòng bán** khác hoặc phân bổ hủy về ngày gốc.

### 7.2. Theo ngày ghi sổ

~~~sql
SELECT d.calendar_date AS posting_date,
       SUM(f.quantity_delta) AS quantity_delta,
       SUM(f.net_amount_delta_vnd) AS posted_amount_delta_vnd
FROM fact_sales_movement AS f
JOIN dim_date AS d ON d.date_key = f.posting_date_key
GROUP BY d.calendar_date
ORDER BY posting_date;
~~~

Kết quả:

| Ngày ghi sổ | Quantity delta | Amount delta (VND) |
| --- | ---: | ---: |
| 13/10/2026 | +2 | +200.000 |
| 16/10/2026 | 0 | -20.000 |
| 20/10/2026 | -2 | -180.000 |

Ngày 10/10 không có movement **được ghi sổ** theo ví dụ, dù ngày đó có giao dịch thực tế. Vì vậy cần đặt tên rõ như **posted_sales_delta** hoặc **business_effective_sales_delta**, tránh một chỉ tiêu chung “sales” không biết đang nhóm theo ngày nào.

### 7.3. “Báo cáo đã biết gì vào lúc đó?”

Nếu chỉ xét doanh số có hiệu lực ngày 10/10, vào cuối ngày 15/10 hệ thống đã biết +200.000; đến cuối 17/10 đã biết điều chỉnh thành +180.000.

~~~sql
-- Snapshot kiến thức cuối 15/10 theo giờ +07:00.
SELECT COALESCE(SUM(net_amount_delta_vnd), 0) AS known_amount_vnd
FROM fact_sales_movement
WHERE effective_date_key = 20261010
  AND loaded_at < TIMESTAMPTZ '2026-10-16 00:00:00+07';
-- 200000

-- Snapshot kiến thức cuối 17/10.
SELECT COALESCE(SUM(net_amount_delta_vnd), 0) AS known_amount_vnd
FROM fact_sales_movement
WHERE effective_date_key = 20261010
  AND loaded_at < TIMESTAMPTZ '2026-10-18 00:00:00+07';
-- 180000
~~~

Dùng khoảng **nửa mở** để xác định ranh giới ngày rõ ràng. Truy vấn theo loaded_at là cơ chế **as-known-at** đơn giản cho event append-only; nếu dòng nguồn có phiên bản đến muộn, bị xóa cứng hoặc dimension đã đổi mà không giữ lịch sử, phải mở rộng thiết kế để tái hiện trạng thái đầy đủ.

### 7.4. Kỳ báo cáo đã khóa không được sửa ngầm

Một số tổ chức không cho phép sửa số đã công bố của kỳ kế toán đóng. Khi adjustment đến sau ngày khóa kỳ:

- **Chính sách A — restatement:** tính lại kỳ cũ và **phát hành phiên bản báo cáo đã điều chỉnh**.
- **Chính sách B — current-period adjustment:** ghi khoản điều chỉnh vào kỳ đang mở; báo cáo cũ không đổi.
- **Chính sách C — dual views:** giữ cả số **as originally reported** và số **restated**, có bảng đối chiếu nguyên nhân.

Không có một lựa chọn đúng chung cho mọi doanh nghiệp. Điều quan trọng là **business_effective_date** và **posting_date** phải thể hiện rõ chính sách, với lịch sử phiên bản/đóng kỳ. Không nên sửa thẳng một cột date_key trong fact cũ chỉ để dashboard khớp số hôm nay.

## 8. Phân biệt điều chỉnh lỗi, hủy, trả hàng và hoàn tiền

Các sự kiện âm có thể cùng làm giảm một chỉ tiêu nhưng **không cùng ý nghĩa nghiệp vụ**.

| Nghiệp vụ | Sự kiện phát sinh | Measure chính | Yêu cầu lịch sử |
| --- | --- | --- | --- |
| Sửa chiết khấu nhập thiếu | Điều chỉnh số tiền giao dịch | amount_delta âm hoặc dương | Giữ số cũ, số mới/lý do nếu yêu cầu |
| Hủy trước giao/hoàn tất | Đảo cam kết/bán tùy chính sách | quantity/amount reversal | Ai hủy, khi nào, trạng thái đơn |
| Khách trả hàng đã nhận | Một **return event** mới | returned_quantity, refund_amount | Liên kết lần bán, lý do, kho nhận |
| Hoàn tiền riêng phần | Refund event | refund_amount, có thể quantity = 0 | Trạng thái thanh toán, đơn vị tiền |
| Bản tin phát lại do retry | Không có sự kiện nghiệp vụ mới | **Không thay đổi tổng** | Dedup theo ID nguồn |
| Điều chỉnh tồn kho kiểm đếm | Delta tồn kho hoặc snapshot revision | stock_delta hoặc units_on_hand mới | Lý do, kho, kỳ kiểm kê |

Một đơn bị hủy và một kiện hàng được trả có thể dẫn đến cùng con số giảm 100.000, nhưng dashboard vận hành phải phân biệt **cancellation_rate**, **return_rate** và **refund_amount**.

Nếu FactSalesMovement đã có reversal -100.000 và FactReturnLine cũng lưu refund +100.000, công thức “net sales = SUM(sales movements) - SUM(refund)” **có thể trừ hai lần**. Cần định nghĩa rõ movement nào đã bao gồm hoàn tiền, fact nào phục vụ báo cáo riêng và khi drill-across phải thống nhất phạm vi.

### 8.1. Điều chỉnh cùng dòng nhưng khác đơn vị đo

Một điều chỉnh có thể chỉ sửa:

- Số lượng: +1 hoặc -1 đơn vị.
- Tiền: -20.000 VND do chiết khấu.
- Thuế: +5.000 VND nếu chính sách tax được theo dõi riêng.
- Mã sản phẩm/cửa hàng: **thay đổi chiều** chứ không phải phép cộng số đơn giản.

Nếu sửa **product_key từ P-A thành P-B**, một movement delta duy nhất với product_key=P-B và số tiền bằng 0 **không chuyển** số lượng/doanh thu đã thuộc P-A sang P-B. Một cách phù hợp là ghi delta âm tại **P-A** và delta dương tại **P-B**, hoặc cập nhật/phiên bản hóa phép ánh xạ dimension của dòng bán theo chính sách restatement.

Các measure **không cộng được** như conversion rate, average unit price hay distinct order count không được “điều chỉnh” bằng cách cộng một tỷ lệ phần trăm âm vào fact. Cần tính lại từ các tử số/mẫu số hoặc sự kiện nền.

## 9. Bảo vệ khả năng nạp lặp an toàn (idempotency)

Các hệ truyền tin, CDC và job ETL thường có cơ chế **at-least-once delivery**: cùng một thông điệp có thể được gửi lại. Nếu cứ INSERT, tổng fact bị nhân.

### 9.1. Định danh và quy tắc xung đột

Khóa như **(source_system, source_event_id)** phải:

- Không thay đổi giữa các lần gửi lại của **cùng một sự kiện**.
- Khác nhau giữa **hai sự kiện nghiệp vụ khác nhau**.
- Đúng phạm vi tenant, topic hoặc hệ nguồn; nếu event_id chỉ duy nhất trong một tenant, phải đưa tenant_id vào khóa.
- Không suy ra bằng timestamp nhận hoặc sequence trong kho dữ liệu vì mỗi retry có thể có giá trị mới.

Ví dụ cách chặn INSERT trùng theo khóa:

~~~sql
INSERT INTO fact_sales_movement
    (source_system, source_event_id, source_sale_line_id,
     movement_kind, related_source_event_id,
     occurred_at, effective_date_key, posting_date_key,
     product_key, store_key, quantity_delta, net_amount_delta_vnd)
VALUES
    ('checkout', 'SALE-1', 'ORDER-901:1', 'SALE', NULL,
     TIMESTAMPTZ '2026-10-10 11:00:00+07',
     20261010, 20261013,
     101, 11, 2, 200000)
ON CONFLICT (source_system, source_event_id)
DO NOTHING;
~~~

**DO NOTHING không đủ để xác minh tính đúng đắn.** Nếu nguồn dùng lại event_id nhưng gửi **payload khác**, âm thầm bỏ qua nghĩa là có xung đột dữ liệu chưa được giải quyết.

Pipeline thực tế cần kiểm tra payload chuẩn hóa hoặc hash của các trường nghiệp vụ:

- Cùng ID, cùng nội dung → **retry hợp lệ**, không cộng thêm.
- Cùng ID, nội dung khác → **quarantine/escalate**, hoặc cơ chế version chính thức của nguồn.
- ID khác nhưng là **một giao dịch lặp theo nghĩa nghiệp vụ** → cần business dedup theo quy tắc riêng, không phụ thuộc hoàn toàn event_id.

Không được gộp hai sự kiện thực sự khác nhau chỉ vì **cùng amount, timestamp hoặc product_id**.

### 9.2. Không dùng arrival order làm thứ tự nghiệp vụ

Một bản tin ADJUSTMENT có thể đến trước SALE; một bản tin trạng thái có sequence 13 đến trước sequence 12. Cần dùng **source version/sequence**, định danh và phụ thuộc để xác định thứ tự hợp lệ; không sắp theo loaded_at rồi cho rằng tất cả sự kiện sau luôn mới hơn về nghiệp vụ.

Khi hệ nguồn có monotonic sequence **theo một aggregate/order**, hãy kiểm tra missing sequence và quá trình phát lại. Nếu nguồn chỉ đảm bảo thứ tự **trong từng partition của message broker**, thứ tự toàn hệ thống không được suy ra từ đó.

### 9.3. Exactly-once effect khác exactly-once delivery

Kho dữ liệu có thể nhận cùng message nhiều lần nhưng vẫn tạo **hiệu ứng đúng một lần** nhờ unique event key, transaction và cơ chế retry an toàn. Đây là điều quan trọng với tổng doanh thu.

Khi một transaction vừa INSERT fact vừa ghi trạng thái đã xử lý offset, cần bảo đảm hai phần **được commit nhất quán** hoặc có cơ chế idempotent để phát lại không làm nhân dữ liệu. Không mặc định message broker hay database riêng lẻ tự bảo đảm hiệu ứng exactly-once xuyên mọi hệ thống.

## 10. Giao dịch đồng thời, đảo ngược hai lần và trạng thái cuối

Bảng movement có thể chỉ nhận INSERT nhưng vẫn có **bất biến xuyên nhiều hàng**.

### 10.1. Một reversal có thể đúng ở từng hàng nhưng sai khi cộng

Trong dữ liệu mẫu, nếu thêm hai reversal cùng -180.000 với hai source_event_id khác nhau, cả hai đều qua CHECK cục bộ nhưng tổng trở thành âm. Unique(source_event_id) không chặn **hai nghiệp vụ đảo cùng một dòng** khi nguồn cung cấp ID khác nhau.

Tùy chính sách cần thêm:

- Unique business operation key như **cancellation_id**.
- Ràng buộc một lần hủy toàn bộ trên mỗi sale_line_id.
- Kiểm tra trạng thái **đã hủy hay chưa** trước khi ghi bù trừ.
- Kiểm tra tổng quantity/amount theo đúng phạm vi, bao gồm adjustment đã chấp nhận.
- Giao dịch/khóa bảo đảm hai writer không cùng thấy dòng “chưa hủy” rồi ghi hai reversal.

### 10.2. Quy trình ghi bù trừ an toàn hơn

Một thủ tục nghiệp vụ có thể hoạt động như sau:

1. Nhận command có **operation_id** ổn định.
2. Trong một transaction, khóa đối tượng dòng bán/aggregate **theo một quy ước mọi writer đều dùng**.
3. Kiểm tra command đã xử lý chưa; nếu rồi, trả trạng thái cũ mà không sinh movement mới.
4. Tính **số dư còn hiệu lực** từ các movement hợp lệ, đúng phiên bản chính sách.
5. Kiểm tra điều kiện cho phép hủy: đã giao/đã hoàn, có refund, đã khóa kỳ hay chưa.
6. Tạo reversal với quantity_delta và amount_delta đối ứng theo quy tắc.
7. Ghi sự kiện, trạng thái xử lý command và audit trong cùng giao dịch; commit.
8. Khi lỗi serialization/deadlock, retry **toàn bộ transaction** với cùng operation_id.

Chỉ một câu SELECT SUM rồi một INSERT trong hai transaction độc lập **không bảo vệ** được trường hợp nhiều writer cạnh tranh. Có thể dùng khóa trên hàng nguồn đại diện (order line), transaction advisory lock theo business key hoặc cơ chế isolation SERIALIZABLE kèm retry, tùy DBMS và kiến trúc.

Nếu fact warehouse được nạp từ một **ledger nguồn đã giải quyết các quy tắc bù trừ**, không nhất thiết tái áp mọi luật giao dịch tại kho phân tích. Nhưng pipeline vẫn phải kiểm tra **bản tin lặp, bản tin thiếu và sai quan hệ với sự kiện gốc**.

## 11. Late-arriving dimension và ánh xạ SCD Type 2

Một fact đến trễ thường còn phải đối mặt với vấn đề **chiều đến trễ**.

Ví dụ Product P-001 có lịch sử:

| product_key | product_code | category | valid_from | valid_to |
| ---: | --- | --- | --- | --- |
| 101 | P-001 | Tai nghe | 01/01/2026 | 01/11/2026 |
| 102 | P-001 | Thiết bị cá nhân | 01/11/2026 | NULL |

Một sale ngày **10/10** đến kho ngày **05/11**. Nếu pipeline luôn tra bản ghi DimProduct **hiện hành** ở ngày nạp, nó sẽ gán product_key **102**, khiến báo cáo “theo danh mục tại thời điểm bán” bị chuyển sang “Thiết bị cá nhân” sai lịch sử.

Cần ánh xạ theo **business event time** và khoảng hiệu lực:

~~~sql
-- Giả định dim_product có khoảng hiệu lực SCD2 đã được làm sạch.
-- :product_code và :event_at là tham số nguồn.
SELECT product_key
FROM dim_product
WHERE product_code = 'P-001'
  AND valid_from <= TIMESTAMPTZ '2026-10-10 11:00:00+07'
  AND (
      valid_to > TIMESTAMPTZ '2026-10-10 11:00:00+07'
      OR valid_to IS NULL
  );
-- Kỳ vọng: 101 nếu không có khoảng chồng lấp.
~~~

Phải bảo đảm một sự kiện khớp **đúng một version**. Nếu có 0 version, cần chính sách missing dimension. Nếu có 2 version, khoảng hiệu lực bị chồng lấp; không nên chọn một bản tùy tiện bằng LIMIT 1 rồi giấu vấn đề.

### 11.1. Xử lý khi chiều chưa đến

Có ba hướng thường gặp:

1. **Tạm giữ fact** ở staging và retry khi chiều đến, có SLA và cảnh báo freshness.
2. **Unknown member:** nạp fact với một product_key “Unknown” có định danh và lý do, sau đó cập nhật ánh xạ hoặc phát hành bản restatement có lịch sử.
3. **Inferred member:** tạo một bản ghi chiều tạm theo business key, hoàn thiện thuộc tính khi nguồn dimension đến.

Mỗi hướng có đánh đổi giữa **độ đầy đủ fact**, **độ đúng phân loại** và **độ trễ xuất bản**. Nếu sửa product_key của fact đã nạp, đó là thay đổi lịch sử ngữ cảnh; nên lưu audit hoặc version của phép ánh xạ, nhất là khi dashboard yêu cầu tái hiện báo cáo as-known-at.

### 11.2. Điều chỉnh hồi tố dimension

Đôi khi nguồn báo “P-001 thực ra đổi Category từ 01/10 chứ không phải 01/11”. Đây là **thay đổi lịch sử dimension**, khác việc nhận muộn một sale.

Có thể phải:

- Sửa các khoảng hiệu lực SCD2 và kiểm tra không chồng lấp.
- Xác định fact trong khoảng bị ảnh hưởng cần **rekey/restatement** hay giữ as-was.
- Đối soát các báo cáo đã phát hành theo phiên bản cũ.
- Tách chỉ tiêu **phân loại hiện hành** khỏi **phân loại tại thời điểm sự kiện**.

Không thể chỉ sửa DimProduct rồi cho rằng mọi query còn đúng nếu fact tham chiếu product_key của phiên bản đã bị điều chỉnh.

## 12. Watermark, completeness và xử lý cửa sổ dữ liệu

Trong batch hoặc stream, pipeline thường dùng **watermark** hoặc mốc tiến độ để xử lý các sự kiện đến trễ.

### 12.1. Watermark không phải bằng chứng “không còn dữ kiện muộn”

Giả sử hệ thống thông báo cho phép trễ tối đa 48 giờ để tổng hợp theo ngày. Nếu sự kiện ngày 10/10 đến ngày 13/10, nó vượt ngưỡng này.

Một hệ stream có thể:

- Đưa vào luồng **late-event handling**.
- Cập nhật lại cửa sổ đã đóng nếu công nghệ và chính sách hỗ trợ.
- Ghi điều chỉnh của kỳ hiện tại.
- Quarantine và yêu cầu backfill có kiểm soát.

Việc “đóng cửa sổ sau 48 giờ” là một **chính sách xử lý**, không phải một định luật rằng không bao giờ có event đến trễ hơn. Nguồn thực tế có thể bị lỗi nhiều ngày, nhập tay dữ liệu cũ hoặc gửi bản sửa sau nhiều tháng.

### 12.2. Theo dõi độ trễ có phân phối

Một phép đo đơn giản:

~~~sql
SELECT movement_kind,
       COUNT(*) AS event_count,
       MIN(loaded_at - occurred_at) AS min_lag,
       MAX(loaded_at - occurred_at) AS max_lag,
       AVG(EXTRACT(EPOCH FROM (loaded_at - occurred_at))) / 3600
           AS avg_lag_hours
FROM fact_sales_movement
GROUP BY movement_kind;
~~~

**Diễn giải thận trọng:** với ADJUSTMENT, occurred_at là lúc sự kiện sửa phát sinh, không phải ngày bán bị sửa. Vì vậy độ trễ đo ở đây là **thời gian phát tán sự kiện adjustment**, không phải số ngày từ lúc bán đến lúc điều chỉnh.

Độ trễ âm có thể xuất hiện vì clock skew, đồng bộ thời gian sai hoặc nguồn khai occurred_at tương lai; cần phân loại. AVG che khuất đuôi dài, nên trong vận hành cần đo **p95/p99**, số event quá SLA và tỷ lệ late events theo từng source.

### 12.3. Các dấu hiệu completeness

- Số source events theo ngày/partition/sequence so với số accepted events.
- Khoảng **source sequence** bị thiếu; đặc biệt với các event liên quan bản gốc.
- Số movement đang pending do thiếu dimension hoặc thiếu original event.
- Số bản tin trùng ID cùng payload, trùng ID khác payload.
- Tổng lượng/tiền theo source control totals so với fact sau điều chỉnh.
- Số ngày/kỳ đã đóng báo cáo và số event đến sau khi đóng.
- Độ trễ tăng theo hệ nguồn, tenant, loại giao dịch hoặc khu vực.

**Lưu ý:** COUNT ở kho bằng COUNT nguồn chưa chắc đã đúng vì một bản tin nguồn có thể bị hủy, cập nhật phiên bản hoặc không đủ điều kiện tạo fact. Phải đối soát theo **phép biến đổi và phạm vi đã được định nghĩa**, không chỉ so hai số tổng tùy ý.

## 13. Bảng tổng hợp và kỳ báo cáo đã công bố

Một dashboard có thể dùng bảng aggregate hằng ngày:

~~~text
daily_sales_mart(
    business_date,
    product_code,
    store_code,
    net_amount_vnd,
    net_units,
    refreshed_at,
    calculation_version
)
~~~

Khi một adjustment có hiệu lực về ngày 10/10 nhưng đến ngày 16/10, mart ngày 10/10 cần được xử lý theo chính sách:

- **Recompute affected partition:** tính lại ngày 10/10 từ nguồn movement.
- **Apply exactly-once delta:** cộng -20.000 vào tổng đã có, chỉ một lần với operation_id duy nhất.
- **Frozen snapshot + correction layer:** giữ bản đã công bố, báo cáo bản điều chỉnh ở lớp riêng.
- **Versioned mart:** lưu phiên bản kết quả trước/sau để so sánh.

### 13.1. Vì sao “chạy lại job” đôi khi nhân số?

Nếu job mỗi lần quét event và thực hiện:

~~~text
mart.total = mart.total + SUM(source_events)
~~~

thì chạy lại cùng một khoảng sẽ cộng những event đã xử lý thêm lần nữa. Cần dùng một trong các cách:

- **Thay thế kết quả** của toàn bộ nhóm khóa bị ảnh hưởng (recompute + atomic swap/upsert).
- Duy trì **checkpoint/cursor + dedup event_id**, chỉ cộng event mới đã chấp nhận.
- Dùng phép upsert theo **version nguồn** và ghi nhận lần chạy, có kiểm tra idempotency.

Khi cập nhật nhiều mart liên quan cùng sự kiện, cần đảm bảo độ nhất quán của phiên bản báo cáo; không để doanh thu ở mart A đã điều chỉnh nhưng mart B vẫn ở version cũ mà dashboard lại coi là cùng một lần công bố.

### 13.2. Backfill các kỳ đã qua

Quy trình backfill an toàn nên:

1. Xác định khoảng **ngày hiệu lực** thực sự bị ảnh hưởng, không chỉ ngày nạp.
2. Xác định các dimension/SCD2 version có thể thay đổi kết quả phân nhóm.
3. Đánh dấu các aggregate/partition cần tính lại.
4. Nạp dữ liệu bằng khóa sự kiện ổn định, kiểm tra trùng và bản tin thiếu.
5. Tính lại trên dữ liệu staging/phiên bản mới, đối soát tổng và số hàng.
6. Xuất bản **một phiên bản nhất quán** sau khi đạt kiểm tra.
7. Lưu log lần backfill, phạm vi, input snapshot và phiên bản tính toán.
8. Có phương án rollback hoặc phát hành correction nếu báo cáo đã được sử dụng.

Không xóa mù toàn bộ partition rồi để dashboard đọc dữ liệu rỗng trong lúc nạp lại nếu hệ thống yêu cầu tính sẵn sàng và nhất quán.

## 14. Snapshot đến trễ hoặc được sửa không phải delta transaction

**Periodic snapshot fact** có grain khác **transaction movement fact**.

Ví dụ tồn kho cuối ngày 10/10 tại P-001, Store HCM-01:

~~~text
Snapshot revision 1: 20 chiếc
Snapshot revision 2: 18 chiếc (kiểm đếm bổ sung)
~~~

Đây không có nghĩa tồn kho cuối ngày là **20 + 18 = 38 chiếc**. Nếu báo cáo muốn giá trị cuối cùng đã xác nhận thì dùng revision 2; nếu cần “số đã biết trước lúc điều chỉnh”, lấy revision có loaded_at không muộn hơn mốc truy vấn.

### 14.1. Mô hình revision cho snapshot

~~~sql
CREATE TABLE fact_inventory_snapshot_revision (
    snapshot_date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL REFERENCES dim_store(store_key),
    revision_no INTEGER NOT NULL CHECK (revision_no > 0),
    source_revision_id TEXT NOT NULL,
    units_on_hand INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        snapshot_date_key, product_key, store_key, revision_no
    ),
    UNIQUE (source_revision_id)
);
~~~

**Giả định:** revision_no tăng theo phiên bản được nguồn xác nhận cho cùng bộ (date, product, store). Nếu có nhiều source độc lập, UNIQUE(source_revision_id) phải thêm source_system hoặc tenant_id tương ứng.

Lấy revision mới nhất đã biết tại thời điểm cutoff bằng PostgreSQL:

~~~sql
SELECT DISTINCT ON
    (snapshot_date_key, product_key, store_key)
    snapshot_date_key,
    product_key,
    store_key,
    revision_no,
    units_on_hand
FROM fact_inventory_snapshot_revision
WHERE loaded_at < TIMESTAMPTZ '2026-10-18 00:00:00+07'
ORDER BY snapshot_date_key, product_key, store_key,
         revision_no DESC;
~~~

Điều kiện loaded_at chọn các version đã được nhận trước cutoff; ORDER BY revision_no chọn phiên bản nguồn cao nhất trong các version đã biết. Nếu nguồn có revision đến không theo thứ tự, **không** chọn chỉ theo loaded_at rồi coi bản đến cuối là bản đúng nhất: bản nguồn version cũ có thể đến sau version mới.

### 14.2. Tồn kho là measure semi-additive

Units_on_hand có thể cộng **theo sản phẩm/cửa hàng tại cùng một thời điểm**, nhưng không thể cộng qua nhiều ngày để diễn giải thành “tồn cuối kỳ”.

Nếu muốn tồn cuối tháng, phải chọn **snapshot mới nhất không muộn hơn cuối tháng** theo sản phẩm–cửa hàng, đồng thời xử lý các ngày thiếu snapshot và lịch sử version. Nếu muốn average inventory, định nghĩa độ phủ ngày và cách xử lý missing snapshots.

### 14.3. Accumulating snapshot và sự kiện sai thứ tự

Một hàng accumulating snapshot của Order có ordered_at, shipped_at, delivered_at. Nếu sự kiện DELIVERED đến trước SHIPPED, không nên “giữ thời gian đến sau làm trạng thái trước” chỉ vì ETL xử lý theo arrival order.

Nên giữ các mốc theo **event type + event time + source version** và tính trạng thái hiện hành theo quy tắc chuyển trạng thái; có thể lưu mọi sự kiện nguồn ở bảng event lịch sử rồi cập nhật bảng accumulating snapshot được dẫn xuất.

## 15. Cấu trúc vật lý: partition, index và chi phí truy vấn

Một fact movement có thể tích lũy nhiều hàng do mọi adjustment/reversal đều được giữ. Thiết kế vật lý cần phục vụ cả **lọc theo ngày hiệu lực**, **lọc theo ngày ghi sổ** và **truy vết dòng gốc**.

### 15.1. Chọn chỉ mục theo mẫu truy vấn

| Truy vấn | Cấu trúc có thể hỗ trợ | Đánh đổi |
| --- | --- | --- |
| Tổng hợp theo ngày hiệu lực, Product, Store | Index hoặc sort/partition theo effective_date_key | Sự kiện điều chỉnh đến muộn có thể ghi vào kỳ cũ |
| Ghi sổ theo ngày posting | Index/partition theo posting_date_key | Không thay thế lọc theo ngày hiệu lực |
| Tái hiện một dòng bán | Index theo source_system + source_sale_line_id | Tăng chi phí INSERT |
| Báo cáo as-known-at | Index theo loaded_at hoặc kết hợp khóa phân tích | Có thể kém chọn lọc khi quét một kỳ dài |
| Phát hiện duplicate | UNIQUE(source_system, source_event_id) | Bắt buộc duy trì index khi ghi |
| Kiểm tra reference | Index cho related_source_event_id theo scope | Phục vụ truy vết và xử lý event thiếu |

Không nên tự động tạo một index cho mọi cột. Với hàng trăm triệu movement, mỗi index có chi phí lưu trữ, ghi, vacuum, rebuild và replication. Trên kho phân tích dạng cột, clustering, partition pruning hoặc scan cột có thể quan trọng hơn B-tree.

### 15.2. Partition theo ngày nào?

- **Theo loaded_at:** dữ liệu thường ghi vào partition hiện hành, dễ ingest và retention theo ngày tiếp nhận; truy vấn theo ngày nghiệp vụ có thể phải quét nhiều partition nếu late arrivals không dự đoán được.
- **Theo effective_date:** truy vấn báo cáo theo ngày nghiệp vụ dễ prune; nhưng late events phải viết ngược vào partition cũ, có thể đã archive/frozen.
- **Theo posting_date:** hỗ trợ báo cáo kỳ ghi sổ đã khóa; không tự phục vụ restatement về kỳ hiệu lực cũ.

Không có đáp án cố định. Chọn partition key theo **mẫu truy vấn, lateness distribution, chính sách backfill, quản trị dữ liệu cũ và yêu cầu pháp lý**. Khi chọn một trục làm partition key, các trục khác có thể cần index/cluster/bảng mart riêng.

### 15.3. Kiểm chứng bằng kế hoạch truy vấn

Trong PostgreSQL, một truy vấn mẫu:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_key, store_key,
       SUM(quantity_delta) AS net_units,
       SUM(net_amount_delta_vnd) AS net_vnd
FROM fact_sales_movement
WHERE effective_date_key BETWEEN 20261010 AND 20261020
GROUP BY product_key, store_key;
~~~

Cần quan sát số hàng ước lượng/thực, Seq Scan hay Index Scan, hash/sort, buffers và thời gian. Nếu aggregate phải đọc phần lớn fact, một Seq Scan có thể hợp lý; không tự gắn nhãn “scan là sai”.

**Cẩn trọng:** EXPLAIN ANALYZE thực thi câu SQL. Ví dụ SELECT ở trên là truy vấn đọc, nhưng EXPLAIN ANALYZE đi cùng INSERT/UPDATE/DELETE sẽ thực thi thao tác ghi. Chỉ chạy benchmark trong môi trường được phép và có dữ liệu đại diện.

## 16. Đối soát theo từng cấp: sự kiện, dòng, kỳ và kho

Một hệ thống xử lý late facts phải được kiểm tra ở nhiều cấp. Một báo cáo tổng đúng **có thể che giấu** hai lỗi bù trừ nhau (thừa một giao dịch + thiếu một giao dịch).

### 16.1. Kiểm tra dữ liệu movement theo dòng bán

~~~sql
SELECT source_system, source_sale_line_id,
       COUNT(*) AS movement_count,
       SUM(quantity_delta) AS net_quantity,
       SUM(net_amount_delta_vnd) AS net_amount_vnd
FROM fact_sales_movement
GROUP BY source_system, source_sale_line_id
ORDER BY source_system, source_sale_line_id;
~~~

Trong mô hình giả định số lượng bán ròng không âm, truy vấn tìm nhóm bất thường:

~~~sql
SELECT source_system, source_sale_line_id,
       SUM(quantity_delta) AS net_quantity
FROM fact_sales_movement
GROUP BY source_system, source_sale_line_id
HAVING SUM(quantity_delta) < 0;
~~~

Tuy nhiên, **không tự áp net_quantity >= 0 cho mọi mô hình**: nếu dòng fact là dòng điều chỉnh tồn hoặc khoản phí không có số lượng, quy tắc có thể khác. Hãy gắn kiểm tra theo đúng fact type và chính sách đơn vị đo.

### 16.2. Kiểm tra event tham chiếu sai SALE gốc

FK trong ví dụ chỉ bảo vệ related_source_event_id tồn tại. Truy vấn phát hiện adjustment/reversal tham chiếu **không đúng dòng hoặc không đúng loại SALE**:

~~~sql
SELECT m.source_system, m.source_event_id,
       m.source_sale_line_id, m.related_source_event_id
FROM fact_sales_movement AS m
JOIN fact_sales_movement AS origin
  ON origin.source_system = m.source_system
 AND origin.source_event_id = m.related_source_event_id
WHERE m.movement_kind IN ('ADJUSTMENT', 'REVERSAL')
  AND (
      origin.movement_kind <> 'SALE'
      OR origin.source_sale_line_id <> m.source_sale_line_id
  );
~~~

Nếu quy tắc đòi related event phải là SALE gốc, kết quả phải rỗng. Truy vấn này không tự phát hiện được mọi trường hợp sai amount, đảo hai lần hoặc thiếu event; cần thêm kiểm tra theo operation_id và trạng thái nghiệp vụ.

### 16.3. Kiểm tra tăng trưởng sau backfill

Sau một đợt nạp lại, tối thiểu phải đo:

1. Số source event IDs khác nhau được chấp nhận.
2. Số duplicate cùng payload không tạo thêm movement.
3. Số duplicate khác payload đã được xử lý.
4. Số adjustment chưa ghép được original event.
5. Phân bố lag và số event vượt cửa sổ xử lý.
6. Tổng quantity/amount theo business date, posting date và source.
7. Tổng hợp trước/sau theo tập group bị ảnh hưởng.
8. Số phát hành báo cáo đã bị restate, với version và nguyên nhân.

Không chỉ so một **SUM toàn kho** vì +100.000 và -100.000 sai chỗ có thể triệt tiêu trong tổng mà vẫn khiến báo cáo theo cửa hàng/sản phẩm sai nghiêm trọng.

## 17. Mô hình quan hệ, document, graph và warehouse

Late arrival và compensation là những **vấn đề ngữ nghĩa dữ liệu**, không biến mất khi đổi công nghệ.

| Kiến trúc | Biểu diễn có thể phù hợp | Cần kiểm soát |
| --- | --- | --- |
| **RDBMS giao dịch** | Bảng event/ledger bất biến, FK/UNIQUE, transaction | Idempotency, concurrency, state transition, reference |
| **Document** | Document Order hiện trạng + mảng revisions/events, hoặc collection sự kiện riêng | Mảng tăng quá lớn, update cạnh tranh, dedup xuyên document |
| **Graph** | Node Event nối tới Order/SaleLine bằng cạnh ADJUSTS/REVERSES | Chuỗi tham chiếu, đảo lặp, vòng/sai loại cạnh, tổng hợp theo event duy nhất |
| **Warehouse/OLAP** | Append-only fact, fact snapshot phiên bản, DimDate theo vai trò, SCD2 | Grain, date role, backfill, partition, mart và reconciliation |

### 17.1. Document: trạng thái hiện tại và event log

Một document Order có thể lưu:

~~~json
{
  "orderId": "ORDER-901",
  "version": 3,
  "currentNetAmountVnd": 0,
  "lastEventId": "SALE-1-CANCEL"
}
~~~

Nó thuận tiện cho API đọc **trạng thái mới nhất**, nhưng không cho biết diễn tiến đầy đủ nếu không có **event history**. Có thể lưu event log ở collection riêng, mỗi event có eventId, occurredAt, effectiveDate, delta, reference. Khi document trạng thái được cập nhật từ event, cần cơ chế **version compare-and-set**, transaction hoặc idempotent projection để không áp cùng event hai lần.

Không tự mặc định “nhúng tất cả sự kiện vào mảng” sẽ tốt hơn: document có thể tăng vô hạn, khó truy vấn cross-order theo ngày hiệu lực và chịu cạnh tranh ghi vào cùng object.

### 17.2. Graph: truy vết quan hệ điều chỉnh

Một graph có thể có:

~~~text
(:SaleLine {id:"ORDER-901:1"})
  <-[:APPLIES_TO]- (:SaleEvent {id:"SALE-1"})
  <-[:CORRECTS]- (:Adjustment {id:"SALE-1-PRICE-ADJ"})

(:Reversal {id:"SALE-1-CANCEL"})
  -[:REVERSES]-> (:SaleEvent {id:"SALE-1"})
~~~

Đồ thị giúp truy vết **một sự kiện sửa sự kiện nào**, nhưng không tự bảo đảm số tiền reversal bằng hiệu ứng cần đảo. Nếu có nhiều đường trong graph cùng dẫn tới một event, một phép duyệt đường đi có thể trả event ấy nhiều lần; tổng hợp tài chính phải khử trùng bằng **định danh sự kiện** hoặc áp trọng số theo nghiệp vụ, không SUM theo số đường duyệt.

### 17.3. Warehouse: fact nào đóng vai trò gì?

Một kiến trúc có thể giữ đồng thời:

- **Raw source events:** lưu payload gốc, source ID, thời điểm nguồn và thời điểm tiếp nhận để truy vết.
- **Validated movement fact:** một hàng cho mỗi event đủ điều kiện, có delta và khóa chiều.
- **Current-state mart:** SUM delta hoặc projection để phục vụ câu hỏi trạng thái hiện tại.
- **As-reported snapshots:** lưu số báo cáo đã phát hành theo run/version và cutoff.
- **Reconciliation/audit tables:** kết quả so sánh nguồn–kho và điều chỉnh kỳ.

Các lớp này **không phải nhiều nguồn sự thật độc lập**. Cần xác định lớp nào là nguồn để tính lại lớp nào, quy tắc sửa dữ liệu là gì, cách quản lý phiên bản và khả năng backfill.

## 18. Quy trình thiết kế và vận hành từ yêu cầu nghiệp vụ

Một quy trình thực dụng cho fact có thể đến muộn hoặc bị sửa:

1. **Định nghĩa grain:** một dòng source, một event, một revision hay một snapshot trạng thái?
2. **Phân loại event:** original, adjustment, reversal, return, refund, duplicate, retraction và correction dimension.
3. **Chọn thời gian:** event time, effective date, posting date, load time, timezone và cutoff công bố.
4. **Xác định bất biến:** một lần bán được ghi bao nhiêu lần, đảo mấy lần, số dư hợp lệ, kỳ nào khóa.
5. **Chọn chiến lược thay đổi:** UPDATE có history, append delta, reverse-and-rebook, versioned snapshot hoặc kết hợp theo fact type.
6. **Thiết kế khóa:** source system, tenant, business key, event id, operation id và surrogate key; chống nạp lặp ở đúng phạm vi.
7. **Thiết kế phụ thuộc:** adjustment/reversal phải liên hệ bản gốc; xử lý bản tin đến sai thứ tự và dimension đến muộn.
8. **Thiết kế lịch sử:** yêu cầu as-known-at, as-reported, restated report và thời hạn giữ dữ liệu.
9. **Thiết kế pipeline:** staging, validation, quarantine, dedup, SCD2 lookup, atomic publication, retry/backfill.
10. **Thiết kế đối soát:** tổng nguồn, số event, số movement, số kỳ bị ảnh hưởng, exception và SLA độ trễ.
11. **Thiết kế vật lý:** partition theo đúng trục thời gian, chỉ mục, tổng hợp/materialized view, chi phí nạp/ghi.
12. **Thử trường hợp biên:** duplicate, correction trước original, hai reversal cạnh tranh, kỳ đã khóa, dimension hồi tố, snapshot revision muộn.
13. **Đo kết quả:** query plan, độ trễ, throughput, lag p95/p99, số exception và mức sai khác trước/sau.
14. **Công bố ngữ nghĩa:** chỉ tiêu là gross, net, posted hay restated; ngày của báo cáo đang là ngày nào.

### 18.1. Hợp đồng dữ liệu tối thiểu cho một movement

~~~text
Tên event:
  SOURCE_SALE_ADJUSTMENT

Khóa định danh:
  (source_system, tenant_id, source_event_id)

Tham chiếu nghiệp vụ:
  source_sale_line_id, original_sale_event_id

Thời gian:
  occurred_at, effective_date, posting_date, loaded_at

Đại lượng:
  quantity_delta, net_amount_delta, currency

Quy tắc:
  Delta đã tính theo đơn vị nào?
  Adjustment có thể âm/dương?
  Có được gửi sau kỳ khóa không?
  Gốc chưa đến thì đưa vào staging nào?
  Retry cùng id có phải cùng payload?
  Khi có hai reversal, ngăn bằng operation key nào?
  Những báo cáo nào được restate?

Đối soát:
  Bản tin nguồn, số movement accepted, số lượng/tiền theo kỳ,
  độ trễ nạp, các nhóm lỗi và mốc công bố.
~~~

Đây là **hợp đồng ngữ nghĩa**; không nên chỉ gửi một schema JSON có trường amount mà bỏ qua ý nghĩa “amount là giá trị mới hay delta”.

## 19. Bài tập tự kiểm tra có hướng dẫn giải

### Bài 1. Phân biệt ngày xảy ra và ngày nạp

**Đề bài:** Khách mua ngày 10/10, hệ thống nguồn gửi sự kiện ngày 13/10. Báo cáo bán theo ngày mua và báo cáo sự kiện tiếp nhận sẽ đặt giao dịch vào ngày nào?

**Gợi ý:** Theo ngày mua là **10/10**; theo ngày tiếp nhận là **13/10**. Phải giữ riêng event/business date và loaded_at; không tự thay ngày mua bằng ngày batch chạy.

### Bài 2. Điều chỉnh chênh lệch

**Đề bài:** Ghi nhận ban đầu +500.000, sau đó xác nhận số tiền đúng là 460.000. Dùng fact delta thì thêm movement nào?

**Gợi ý:** Một **ADJUSTMENT -40.000** nếu chính sách là **chỉ ghi chênh lệch**. Không cộng thêm +460.000 vào fact đang có +500.000. Nếu chọn reverse-and-rebook, cần -500.000 và +460.000, không ghi đồng thời delta -40.000 ngoài quy trình đó.

### Bài 3. Đảo một giao dịch đã chỉnh sửa

**Đề bài:** SALE +200.000, ADJUSTMENT -20.000. Muốn số dư cuối bằng 0 khi hủy toàn bộ, reversal cần bao nhiêu?

**Gợi ý:** **-180.000** theo chính sách đảo **số dư còn hiệu lực**. Nếu muốn đảo bản gốc rồi rebook, phải xử lý/đảo các adjustment theo cơ chế nhất quán, không chỉ thêm -200.000 một cách độc lập.

### Bài 4. Tại sao source_event_id quan trọng?

**Đề bài:** Event bán +100.000 được broker gửi lại ba lần do retry. Nếu warehouse dùng surrogate movement_key tự tăng mà không có khóa nguồn thì hậu quả gì?

**Gợi ý:** Có thể tạo ba hàng và báo **300.000**, sai. Cần unique theo phạm vi ID nguồn ổn định và kiểm tra payload khi event id bị dùng lại với nội dung khác.

### Bài 5. Adjustment đến trước original

**Đề bài:** Sự kiện sửa giá tới warehouse trước bản SALE gốc; bảng movement có FK từ adjustment đến source_event_id của SALE. Nên làm gì?

**Gợi ý:** Giữ ở **staging/pending**, retry sau khi gốc đến; hoặc có mô hình inferred event được thiết kế rõ. Không xóa FK rồi cho adjustment không rõ gốc đi thẳng vào báo cáo cuối.

### Bài 6. Trả hàng và reversal

**Đề bài:** Pipeline đã trừ 80.000 từ sales movements khi có return, đồng thời FactReturns ghi refund +80.000. Dashboard tính SUM(sales movements) - SUM(refund). Có vấn đề gì?

**Gợi ý:** Có thể **trừ hai lần**. Phải xác định movement đã bao gồm return/refund chưa và chọn công thức KPI chỉ tính mỗi hiệu ứng một lần.

### Bài 7. Dữ liệu Type 2 đến muộn

**Đề bài:** Product chuyển Category từ 01/11. SALE ngày 10/10 đến vào 05/11. Báo cáo muốn phân loại theo ngày bán nên gán phiên bản dimension nào?

**Gợi ý:** Gán phiên bản **có hiệu lực 10/10**, không mặc định phiên bản hiện hành ngày nạp. Nếu không tìm thấy đúng một phiên bản thì xử lý exception/unknown theo chính sách.

### Bài 8. Kỳ khóa và restatement

**Đề bài:** Kỳ tháng 10 đã công bố; ngày 05/11 phát hiện doanh thu tháng 10 thiếu 1 triệu. Có bắt buộc sửa trực tiếp bảng tổng tháng 10 không?

**Gợi ý:** Không. Cần chính sách: **restate tháng 10 có version mới**, **ghi điều chỉnh kỳ hiện tại**, hoặc cung cấp cả hai chế độ. Mọi lựa chọn phải có dấu vết và định nghĩa ngày hiệu lực/ngày ghi sổ.

### Bài 9. Sửa snapshot tồn kho

**Đề bài:** Snapshot ngày 10/10 là 20 chiếc; kiểm kê muộn sửa thành 18 chiếc. Có được cộng hai hàng revision thành 38 để tính tồn cuối ngày không?

**Gợi ý:** Không. Chọn **phiên bản hợp lệ mới nhất** theo revision nguồn hoặc chính sách cutoff, không SUM các giá trị snapshot tuyệt đối.

### Bài 10. As-known-at

**Đề bài:** SALE +200.000 được nạp 13/10, ADJUSTMENT -20.000 được nạp 16/10 nhưng hiệu lực 10/10. Nếu truy vấn doanh thu 10/10 với cutoff cuối ngày 15/10 và cuối ngày 17/10, kết quả là gì?

**Gợi ý:** **200.000** và **180.000**, nếu dùng fact bất biến và lọc loaded_at theo cutoff. Đây là hai ảnh chụp kiến thức khác nhau về cùng kỳ nghiệp vụ.

### Bài 11. Cập nhật đồng thời

**Đề bài:** Hai worker cùng tính được số dư +180.000 rồi mỗi worker thêm reversal -180.000 với event id khác nhau. UNIQUE(source_event_id) có đủ không?

**Gợi ý:** Không. Đây là **hai operation nghiệp vụ** với hai ID khác nhau. Cần operation_id/business uniqueness và cơ chế giao dịch/khóa/serialization đảm bảo chỉ một lần hủy hợp lệ.

### Bài 12. Chọn partition key

**Đề bài:** Pipeline nhận hàng trăm triệu event, rất nhiều late arrivals từ nhiều tháng trước. Báo cáo chủ yếu theo ngày nghiệp vụ nhưng dữ liệu được nạp theo ngày hiện tại. Nên partition theo ngày nào?

**Gợi ý:** Cần đo **lateness, query pattern và chi phí backfill**. Partition theo business date hỗ trợ pruning báo cáo nhưng late inserts vào partition cũ; theo loaded_at giúp ingest nhưng khó prune theo ngày nghiệp vụ; theo posting date phù hợp kỳ ghi sổ. Không có đáp án mặc định.

### Bài 13. KPI nào được phép cộng?

**Đề bài:** Fact có quantity_delta và average_unit_price. Khi nhận adjustment -20.000, có thể lấy SUM(average_unit_price) của mọi movement để tính giá trung bình mới không?

**Gợi ý:** Không. Giá trung bình là measure **không cộng được**; phải tính từ **tổng tiền / tổng lượng** với phạm vi nghiệp vụ, điều kiện số lượng khác 0 và chính sách hàng hủy/trả phù hợp.

### Bài 14. Vì sao tổng bằng 0 chưa đủ?

**Đề bài:** Hai lỗi dữ liệu: thiếu một sale +100.000 tại Store A và nạp dư một sale +100.000 tại Store B. Tổng doanh thu toàn hệ có thể vẫn bằng số nguồn. Đối soát còn cần gì?

**Gợi ý:** Cần đối chiếu **theo source event ID, business key, ngày, store, product, số lượng và trạng thái**. Một tổng toàn hệ có thể che hai sai lệch bù trừ nhau.

## 20. Checklist nghiệm thu

Trước khi đưa một fact có late arrival/adjustment vào báo cáo, xác nhận:

- **Grain:** một hàng fact có ý nghĩa chính xác; không trộn event delta với snapshot tuyệt đối.
- **Khóa:** mọi event có source ID ổn định, đúng tenant/system; các retry không tạo thêm hiệu ứng.
- **Thời gian:** occurred, effective, posting, loaded và timezone được tách rõ.
- **Đảo ngược:** có tham chiếu đúng gốc, lý do, phạm vi, operation id và kiểm soát đảo lặp.
- **Kỳ đóng:** chính sách late correction, restatement và phát hành phiên bản báo cáo rõ.
- **SCD2:** fact đến muộn được ánh xạ tới dimension theo thời điểm phù hợp, không theo ngày nạp mặc định.
- **Thứ tự đến:** adjustment trước original được xử lý ở staging hoặc cơ chế tương đương.
- **Idempotency:** retry cùng ID/payload không tăng số hàng; ID trùng payload khác bị phân loại lỗi.
- **Aggregate:** chỉ tính delta một lần; mart khi backfill được recompute/upsert nhất quán.
- **Snapshot:** revision sửa một trạng thái không được cộng như transaction.
- **Reconciliation:** kiểm tra cả số event, số hàng, tổng lượng/tiền, các nhóm và exception.
- **Lịch sử:** có thể giải thích vì sao một kỳ được báo cáo khác nhau ở hai thời điểm.
- **Hiệu năng:** index/partition/query plan được đo trên phân bố late events phù hợp.
- **Định nghĩa KPI:** phân biệt doanh số, doanh thu ghi sổ, điều chỉnh, hủy, trả hàng và hoàn tiền.

## 21. Ghi nhớ

- **Dữ kiện đến trễ** là sự kiện hợp lệ được nhận sau lúc nó xảy ra; phải lưu đúng thời gian nghiệp vụ, thời gian tiếp nhận và quy tắc kỳ.
- **Điều chỉnh** là thay đổi một giá trị trước đó; phải chọn rõ **ghi chênh lệch**, **sửa có lịch sử** hay **đảo rồi ghi lại**.
- **Bản ghi bù trừ** là một sự kiện có dấu vết nhằm đảo hiệu ứng; nó phải được ngăn ghi hai lần và khớp phần giá trị cần đảo.
- **Không trộn delta với snapshot tuyệt đối.** SUM movement có nghĩa; SUM hai revision tồn kho của cùng một thời điểm thường không có nghĩa.
- **Idempotency và out-of-order handling** quyết định tính đúng khi event bị phát lại hoặc đến sai thứ tự.
- **Late-arriving fact và late-arriving dimension** có quan hệ mật thiết: fact được ghi muộn phải tra đúng SCD version theo chính sách nghiệp vụ.
- **As-known-at, as-effective và as-posted** là ba góc nhìn khác nhau; một báo cáo thay đổi sau backfill không nhất thiết là lỗi nếu có phiên bản và giải thích rõ.
- **Đối soát và phép đo thực tế** phải đi cùng thiết kế khóa, FK, CHECK, index và partition; một tổng số đúng chưa chứng minh mọi dòng đều đúng.

Một mô hình fact đáng tin cậy không chỉ lưu được số liệu mới nhất. Nó còn trả lời được **số liệu đến từ sự kiện nào, được biết khi nào, ảnh hưởng kỳ nào, đã điều chỉnh hoặc bù trừ ra sao, và có thể kiểm chứng lại bằng dữ liệu nguồn hay không**.
