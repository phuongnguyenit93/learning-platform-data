# Chiều thay đổi chậm kiểu 3: giữ một phần giá trị trước

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **Slowly Changing Dimension Type 3 (SCD Type 3)**: giữ giá trị **hiện tại** và một số giá trị **trước đó** trong các cột của **cùng một hàng chiều**.
- Phát biểu **grain**, khóa nghiệp vụ, khóa thay thế và quy tắc thay đổi đối với một bảng chiều kiểu 3.
- Phân biệt **"giá trị liền trước lần đổi gần nhất"** với **"giá trị thực sự có hiệu lực tại thời điểm giao dịch"**; hiểu vì sao SCD3 không thay thế lịch sử đầy đủ của SCD2.
- Chọn SCD Type 1, 2, 3 hoặc thiết kế kết hợp theo đúng câu hỏi phân tích, không chọn chỉ vì truy vấn đơn giản hơn.
- Thiết kế quy trình nạp SCD3 với kiểm tra giá trị đổi thực sự, version nguồn, idempotency và cập nhật nguyên tử trong PostgreSQL.
- Viết truy vấn so sánh **hai cách phân nhóm** của cùng một tập dữ kiện: theo vùng hiện tại và vùng liền trước, đồng thời xử lý trường hợp chưa từng đổi vùng.
- Xử lý giới hạn lịch sử, sự kiện đến trễ, thay đổi liên tiếp, nhiều thuộc tính, phát hành lại báo cáo và kiểm thử tính đúng.

Trong **DATABASE_DATA_MODELING**, chuyển yêu cầu nghiệp vụ thành bảng chiều không chỉ là tạo một cột mã và một cột tên. Doanh nghiệp thường thay đổi cơ cấu bán hàng, phân khúc khách hàng hoặc người phụ trách; báo cáo cần trả lời **dữ liệu được phân loại theo tổ chức hiện nay hay theo một cách phân loại trước đây?** SCD Type 3 là một kỹ thuật giữ **một phần** thông tin trước đó để so sánh những cách nhìn này mà không nhân nhiều hàng cho cùng đối tượng. Đổi lại, nó **không lưu được toàn bộ lịch sử**. Hiểu rõ đánh đổi đó là trọng tâm của bài thuộc chương **Bảng chiều**.

## 1. Tình huống: cửa hàng đổi vùng quản lý

Một chuỗi bán lẻ có 200 cửa hàng. Mỗi cửa hàng có mã ổn định, nhưng được gán vào một **vùng quản lý doanh số** có thể thay đổi khi tổ chức tái cơ cấu. Ví dụ:

- Trước ngày 15/10/2026, cửa hàng **S-101** thuộc vùng **Bắc**.
- Từ ngày 15/10/2026, cửa hàng S-101 được chuyển sang vùng **Trung**.
- Ban điều hành muốn xem doanh số cùng một kỳ theo **vùng quản lý hiện tại**, đồng thời xem **nếu vẫn dùng cách phân vùng trước lần tái cơ cấu gần nhất** thì số liệu được phân bổ ra sao.

Hai câu hỏi rất khác nhau:

1. **So sánh cách phân bổ:** Lấy cùng tập giao dịch, nhóm một lần theo vùng *hiện tại*, một lần theo vùng *liền trước*. Đây là bài toán SCD3 phù hợp.
2. **Tái hiện đúng lịch sử tại ngày bán:** Với mỗi giao dịch ngày 01/05, 20/10 hoặc 01/12, xác định vùng **đã thực sự có hiệu lực vào ngày đó**. Đây là bài toán lịch sử theo thời gian; nếu cửa hàng đổi vùng nhiều lần, SCD3 thông thường **không đủ**.

Vì thế, phát biểu yêu cầu "cần xem vùng cũ" vẫn chưa đủ để quyết định. Cần hỏi rõ **cũ là giá trị liền trước hiện tại hay là bất kỳ giá trị nào tại một thời điểm quá khứ?**

## 2. Cấu trúc SCD Type 3: một hàng, nhiều cột giá trị

**SCD3** lưu những phiên bản được chọn của một thuộc tính **theo chiều ngang** trong một bản ghi, ví dụ:

| store_key | store_id | store_name | current_region | previous_region | region_changed_at |
| ---: | --- | --- | --- | --- | --- |
| 501 | S-101 | Cửa hàng A | Trung | Bắc | 2026-10-15 00:00+07 |
| 502 | S-102 | Cửa hàng B | Nam | NULL | NULL |

**Grain:** một hàng biểu diễn **một cửa hàng thuộc một tenant**. Thay đổi vùng không tạo thêm hàng dimension mới.

**Khóa:**

- **store_id** là định danh ổn định của cửa hàng trong nguồn vận hành, có thể cần kết hợp **tenant_id**.
- **store_key** là khóa thay thế (*surrogate key*) dùng để liên kết với bảng fact.
- **current_region** mô tả phân loại hiện hành theo thời điểm bản chiều được nạp.
- **previous_region** lưu giá trị ngay trước **lần thay đổi vùng gần nhất đã được xử lý đúng**.
- **region_changed_at** ghi mốc đổi vùng gần nhất mà nguồn có thẩm quyền cung cấp; không phải mốc tạo fact.

Lần đổi từ **Bắc → Trung** thực hiện **trên cùng hàng**:

~~~text
Trước đổi:
store_key = 501
current_region = Bắc
previous_region = NULL

Sau khi tiếp nhận chuyển vùng:
store_key = 501                (không đổi)
current_region = Trung        (giá trị mới)
previous_region = Bắc         (giá trị ngay trước)
region_changed_at = 15/10/2026
~~~

Nếu cửa hàng chưa từng đổi vùng trong phạm vi lịch sử được theo dõi, **previous_region = NULL** mang nghĩa "chưa có giá trị trước được ghi nhận", không tự động có nghĩa cửa hàng từng thuộc vùng UNKNOWN.

### Vì sao gọi là "kiểu 3"?

Trong phân loại SCD phổ biến:

- **Type 1:** ghi đè giá trị cũ, không lưu lịch sử của thuộc tính đó trong chiều.
- **Type 2:** thêm một **hàng phiên bản** mới cho cùng đối tượng; các hàng có khoảng hiệu lực.
- **Type 3:** giữ **một số cột lịch sử hữu hạn** trên **cùng hàng**: current/previous, hoặc original/current, tùy chính sách đã công bố.

Type 3 không giới hạn bắt buộc chỉ **một** previous column; có thể giữ original_region, previous_region, current_region nếu yêu cầu chỉ cần các giá trị đó. Nhưng nó vẫn giữ **một số mốc cố định**, không phải lịch sử vô hạn.

## 3. Diễn tiến nhiều lần thay đổi và dữ liệu bị mất

Giả sử cùng cửa hàng S-101 lần lượt trải qua:

~~~mermaid
flowchart LR
    A["01/01<br/>current = Bắc<br/>previous = NULL"]
    B["15/10<br/>current = Trung<br/>previous = Bắc"]
    C["20/11<br/>current = Nam<br/>previous = Trung"]
    A -->|"Đổi vùng lần 1"| B
    B -->|"Đổi vùng lần 2"| C
~~~

| Thời điểm quan sát | current_region | previous_region | Đọc được điều gì? |
| --- | --- | --- | --- |
| Sau khi nạp ban đầu | Bắc | NULL | Chỉ biết Bắc là vùng hiện hành |
| Sau thay đổi 15/10 | Trung | Bắc | Biết ngay trước Trung là Bắc |
| Sau thay đổi 20/11 | Nam | Trung | Biết ngay trước Nam là Trung; **Bắc đã mất khỏi hàng này** |

Nếu tiếp tục đổi **Nam → Bắc**, SCD3 trở thành current=Bắc, previous=Nam. Hai cột không đủ để cho biết cửa hàng cũng từng thuộc Bắc **trước khi chuyển Trung**.

**Giới hạn quyết định:** SCD3 tiêu chuẩn không trả lời được câu hỏi "S-101 thuộc vùng nào vào tháng 5, tháng 10, tháng 11?" sau nhiều đợt thay đổi, trừ khi có **nguồn lịch sử độc lập** để đối chiếu. Một cột region_changed_at của **lần đổi gần nhất** không khôi phục các lần đổi trước đã bị ghi đè.

Ngay cả khi doanh nghiệp chỉ có một thay đổi trong một kỳ, cách diễn giải "vùng trước/hiện tại" cần được ghi lại trong hợp đồng dữ liệu, bởi một thay đổi bổ sung bất ngờ có thể xóa ý nghĩa kỳ đối chiếu trước.

### Hai biến thể chính sách hay gặp

| Cách lưu | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| current + **previous** | Giá trị liền trước **lần đổi mới nhất** | So sánh trạng thái mới với bước liền trước, chấp nhận lịch sử trượt |
| current + **original** | Giá trị lúc khởi tạo hoặc tại một baseline đã chốt | So sánh mọi lần đổi với phân loại gốc/cơ cấu tại một kỳ mốc |

Đừng gọi original_region là previous_region nếu nó không quay vòng mỗi lần đổi. Hai kiểu cột này nhìn giống nhau về SQL nhưng mang **ngữ nghĩa kinh doanh khác**. Có thể dùng cả hai khi hợp đồng nêu rõ cách duy trì từng cột.

## 4. SCD3 không tự biến dữ liệu quá khứ thành dữ liệu "as-of"

Điểm thường gây sai báo cáo là nhầm hai phép toán:

**Phân nhóm lại theo cách phân loại hiện tại hoặc trước đó:**

> "Lấy tất cả doanh số tháng 9, tính một lần theo vùng **hiện tại** của từng cửa hàng và một lần theo vùng **liền trước lần chuyển gần nhất**."

**Phân nhóm theo trạng thái thực sự tại thời điểm giao dịch:**

> "Lấy doanh số tháng 9 và nhóm theo vùng mà cửa hàng **đã thuộc về trong tháng 9**, kể cả nếu kể từ đó đã chuyển hai hoặc ba vùng."

SCD3 phục vụ tốt phép đầu. Phép thứ hai thường cần:

- **SCD2** với nhiều hàng phiên bản và khoảng hiệu lực;
- snapshot vùng ngay trong fact tại thời điểm giao dịch, khi định nghĩa ghi nhận đã được xác nhận;
- một bảng lịch sử phân công vùng đủ chi tiết để thực hiện phép nối theo thời gian;
- hoặc một kết hợp/hybrid được thiết kế tường minh.

**Không dùng previous_region để thay cho "region_at_sale" một cách mặc định.** Nếu cửa hàng đổi vùng hai lần, previous_region là vùng trước lần đổi **cuối cùng**, không phải vùng đã có hiệu lực lúc tất cả giao dịch quá khứ xảy ra.

### Bảng so sánh các kiểu thay đổi chậm

| Câu hỏi/đặc tính | Type 1 | Type 2 | Type 3 |
| --- | --- | --- | --- |
| Giá trị hiện tại ở chiều? | Có | Ở hàng phiên bản hiện hành | Có |
| Giữ giá trị ngay trước? | Không trong chính chiều | Có qua hàng lịch sử | Có nếu thiết kế cột previous |
| Lưu toàn bộ chuỗi thay đổi? | Không | Có trong phạm vi lịch sử được nạp/giữ | Không, chỉ số mốc đã chọn |
| Thay đổi tạo hàng mới? | Không | Có | Không |
| Khóa thay thế fact cho một đối tượng có đổi qua phiên bản? | Thường ổn định | Có thể khác nhau theo phiên bản | Thường ổn định |
| Báo cáo đúng thuộc tính tại thời điểm fact? | Không tự đủ | Có nếu fact gắn đúng phiên bản hiệu lực | Không tự đủ sau nhiều lần đổi |
| So sánh **cùng tập fact** theo hai phân loại hiện tại và trước đó? | Không có vùng trước | Cần logic chọn phiên bản rồi phân nhóm | Trực tiếp qua hai cột |
| Chi phí/chú ý | Mất lịch sử | Nhiều hàng, ánh xạ thời gian và late events | Ghi đè lịch sử cũ, định nghĩa previous/baseline |

Không có kiểu nào "đúng tuyệt đối" cho mọi trường hợp. Việc chọn kiểu phụ thuộc câu hỏi cần giữ được **về quá khứ**, khối lượng dữ liệu và hợp đồng nghiệp vụ.

## 5. Từ yêu cầu đến dimension grain và quyền sở hữu

Trước khi tạo bảng, xác định:

1. **Đối tượng nào đang đổi?** Trong ví dụ là *cửa hàng*, không phải một giao dịch bán.
2. **Thuộc tính nào cần phiên bản?** Vùng quản lý bán hàng; không nhất thiết mọi trường của Store đều cần Type 3.
3. **Giá trị "previous" nghĩa gì?** Giá trị trước mỗi lần đổi, giá trị của lần đổi lớn gần nhất, hay vùng tại mốc tái cơ cấu?
4. **Nguồn có thẩm quyền là đâu?** Hệ thống quản lý cửa hàng/tổ chức vùng, không phải bảng mart được cập nhật tay.
5. **Phạm vi duy nhất là gì?** Thường là (tenant_id, store_id).
6. **Mức độ đầy đủ của chuỗi thay đổi?** Pipeline thấy mọi lần đổi vùng hay chỉ một snapshot mới nhất mỗi đêm?
7. **Fact đã tham chiếu chiều thế nào?** Có khóa thay thế ổn định để không phải cập nhật hàng triệu fact khi vùng đổi không?
8. **Báo cáo có cần tái hiện một lần chạy cũ?** Nếu có, SCD3 đơn thuần bị ghi đè có thể không đủ để cố định kết quả báo cáo.

Đầu ra có thể là một **hợp đồng dữ liệu**:

| Thuộc tính | Quy ước minh họa |
| --- | --- |
| Dimension | Store |
| Grain | Một hàng cho một (tenantId, storeId) |
| Khóa fact | (tenantId, storeKey) |
| Thuộc tính Type 3 | currentRegion, previousRegion |
| Ý nghĩa previous | Giá trị ngay trước lần thay đổi vùng **mới nhất đã được xử lý theo đúng thứ tự nguồn** |
| Trường Type 1 | storeName có thể được sửa trong cùng hàng, không xoay previousRegion |
| Thời gian thay đổi | regionChangedAt từ nguồn có thẩm quyền, theo UTC |
| Phiên bản nguồn | sourceVersion tăng đơn điệu trong phạm vi Store |
| Dữ liệu chưa có quá khứ | previousRegion = NULL |
| Lỗi cần xử lý | Sự kiện ngoài thứ tự, bỏ sót phiên bản, trùng ID, sửa đổi hồi tố (backdated) |
| Loại báo cáo | So sánh phân loại vùng hiện tại với lần trước, **không** tuyên bố truy vấn as-of đầy đủ |

## 6. Lược đồ PostgreSQL: một hàng cho mỗi cửa hàng

PostgreSQL sau chỉ là ví dụ để làm rõ ngữ nghĩa và ràng buộc; một warehouse dạng cột có thể dùng lệnh MERGE hoặc pipeline khác thay cho UPDATE từng hàng.

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.dim_store_scd3 (
    tenant_id UUID NOT NULL,
    store_key BIGINT GENERATED ALWAYS AS IDENTITY,
    store_id UUID NOT NULL,
    store_name TEXT NOT NULL,
    current_region TEXT NOT NULL,
    previous_region TEXT,
    region_changed_at TIMESTAMPTZ,
    source_version BIGINT NOT NULL CHECK (source_version >= 0),
    last_source_event_id UUID,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, store_key),
    UNIQUE (tenant_id, store_id),
    CHECK (length(trim(store_name)) > 0),
    CHECK (length(trim(current_region)) > 0),
    CHECK (
        previous_region IS NULL
        OR length(trim(previous_region)) > 0
    )
);

CREATE INDEX dim_store_current_region
    ON mart.dim_store_scd3 (tenant_id, current_region);

CREATE INDEX dim_store_previous_region
    ON mart.dim_store_scd3 (tenant_id, previous_region)
    WHERE previous_region IS NOT NULL;
~~~

**Đọc DDL theo ý nghĩa:**

- **UNIQUE (tenant_id, store_id)** giữ đúng grain một hàng/store/tenant. Không cho tạo một hàng mỗi lần vùng đổi như Type 2.
- **store_key** không thay đổi khi current_region đổi; các fact có thể tiếp tục giữ khóa đó.
- **previous_region NULL** lúc khởi tạo biểu thị chưa biết giá trị trước. Không bắt buộc current_region phải khác previous_region bằng CHECK, bởi chính sách/nguồn có thể có ngoại lệ và ràng buộc cứng có thể gây lỗi khi migration; điều cần bảo vệ là **quy tắc cập nhật**.
- **source_version** giúp tránh bản cũ ghi đè bản mới khi phiên bản được nguồn cấp nhất quán; bản thân một con số không chứng minh đã nhận đủ mọi phiên bản trung gian.
- **region_changed_at** là một mốc nghiệp vụ, không phải loaded_at. Nếu nguồn chỉ gửi thời gian nhận chứ không có ngày hiệu lực, phải nêu giới hạn đó.
- Hai chỉ mục vùng minh họa cho truy vấn nhóm và lọc thường gặp. Trên warehouse chuyên dụng, cách sắp xếp, thống kê và lưu trữ cột có thể làm chỉ mục khác đi; không nhất thiết tạo cả hai.

Nếu vùng có **mã chính thức** và tên hiển thị có thể đổi, nên lưu region_id/region_code ổn định và JOIN dimension vùng phù hợp thay vì dùng tên tự do làm danh tính. Ví dụ dùng TEXT để dễ đọc, không có nghĩa tên hiển thị là một business key đáng tin cậy.

### Bảng fact liên kết với dimension Type 3

~~~sql
CREATE TABLE mart.fact_paid_order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    store_key BIGINT NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    gross_sales_vnd BIGINT NOT NULL CHECK (gross_sales_vnd >= 0),
    load_batch_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, store_key)
        REFERENCES mart.dim_store_scd3 (tenant_id, store_key)
);

CREATE INDEX paid_line_by_store_date
    ON mart.fact_paid_order_line (tenant_id, store_key, paid_at);
~~~

**Grain fact:** một hàng là một dòng OrderLine được ghi nhận bán sau khi đơn đã thanh toán toàn bộ theo giả định bài học. Một Order có nhiều dòng, nên COUNT(*) là số dòng bán, không phải số đơn. Nếu nghiệp vụ cho phép thanh toán theo nhiều đợt, phải chọn grain khác hoặc mở rộng khóa đúng thực tế, không dựa vào giả định này.

Khi vùng đổi, fact không cần sửa store_key; cùng một fact có thể được tổng hợp theo current_region hoặc previous_region bằng JOIN đến hàng dimension đó. **Điểm mạnh của SCD3 cũng chính là giới hạn của nó:** khi dimension bị cập nhật, phép nhóm lại của **các fact cũ** có thể thay đổi.

## 7. Nạp ban đầu, đổi vùng và quy tắc xoay giá trị

### 7.1. Nạp ban đầu: không tự bịa vùng trước

Nguồn cho biết S-101 đang thuộc vùng Bắc và sourceVersion=1. Nếu không có lịch sử đáng tin cậy, hàng mới có:

~~~sql
-- :tenant_id, :store_id, ... là tham số từ pipeline đã xác thực.
INSERT INTO mart.dim_store_scd3 (
    tenant_id, store_id, store_name,
    current_region, previous_region,
    region_changed_at, source_version, last_source_event_id
) VALUES (
    :tenant_id, :store_id, :store_name,
    :initial_region, NULL,
    NULL, :initial_source_version, :source_event_id
)
ON CONFLICT (tenant_id, store_id) DO NOTHING
RETURNING store_key;
~~~

Nếu xung đột, pipeline phải kiểm tra hàng hiện có và phiên bản, không coi ON CONFLICT DO NOTHING là bằng chứng dữ liệu nguồn bằng nhau. Trường hợp có hai worker nạp cùng cửa hàng cần cơ chế khóa/UPSERT và kiểm tra version nhất quán.

Khi bắt đầu theo dõi từ giữa vòng đời mà nguồn chỉ trả giá trị hiện tại, previous_region NULL nghĩa là **không biết**, chứ không có nghĩa cửa hàng chưa từng đổi vùng.

### 7.2. Một lần đổi hợp lệ: xoay current sang previous

Giả sử sự kiện từ nguồn: version 2, newRegion=Trung, effectiveAt=2026-10-15T00:00:00+07. Dùng **một UPDATE nguyên tử**:

~~~sql
UPDATE mart.dim_store_scd3 AS d
SET previous_region = CASE
        WHEN d.current_region IS DISTINCT FROM :new_region
        THEN d.current_region
        ELSE d.previous_region
    END,
    region_changed_at = CASE
        WHEN d.current_region IS DISTINCT FROM :new_region
        THEN :effective_at
        ELSE d.region_changed_at
    END,
    current_region = :new_region,
    source_version = :source_version,
    last_source_event_id = :source_event_id,
    updated_at = CURRENT_TIMESTAMP
WHERE d.tenant_id = :tenant_id
  AND d.store_id = :store_id
  AND d.source_version < :source_version
RETURNING
    d.store_key,
    d.current_region,
    d.previous_region,
    d.region_changed_at,
    d.source_version;
~~~

**Vì sao dùng IS DISTINCT FROM?** Câu so sánh trả về TRUE/FALSE rõ ràng cả khi giá trị có thể NULL. Ở bảng này current_region NOT NULL; toán tử vẫn giúp diễn đạt "chỉ xoay khi giá trị thực sự đổi".

Trong PostgreSQL, biểu thức ở SET đọc **giá trị hàng trước UPDATE**. Do đó previous_region nhận current_region cũ, còn current_region nhận :new_region. Không nên thực hiện bằng hai UPDATE rời rạc rồi để một phiên xử lý khác chen vào giữa.

**Trường hợp giá trị không đổi:** Một event sửa tên cửa hàng nhưng vẫn giữ vùng Trung không được xoay previous_region thành Trung. CASE ở trên chỉ xoay khi vùng khác thật. Dù vậy pipeline phải chắc rằng event có chứa **giá trị vùng mới hợp lệ**, không truyền NULL chỉ vì payload cập nhật tên không mang trường vùng.

**Trường hợp event cũ hoặc lặp:** WHERE source_version < :source_version làm một version đã áp dụng không ghi đè current_region mới. Nhưng nếu event cùng version lại có payload khác, đó là **xung đột chất lượng dữ liệu** cần phát hiện từ event log/inbox, không được im lặng coi giống nhau.

### 7.3. Không làm mất lần đổi trung gian

Nếu nguồn có:

~~~text
Version 5: Bắc
Version 6: Trung
Version 7: Nam
~~~

nhưng pipeline nhận version 7 **trước** version 6 và lập tức cập nhật hàng version 5, kết quả có thể thành **current=Nam, previous=Bắc**. Sau đó version 6 bị bỏ qua. Kết quả **không phải "previous thực sự"**, vì ngay trước Nam là Trung.

Muốn giữ **giá trị liền trước thật sự** phải có một trong các cách:

- bảo đảm tất cả sự kiện đổi vùng được xử lý theo đúng thứ tự **của từng store**;
- phát hiện lỗ hổng sequence rồi **buffer/replay** trước khi cập nhật;
- lấy từ nguồn một **snapshot đầy đủ gồm previous chính xác** hoặc một change history có thẩm quyền;
- hoặc xây lại chiều từ một log thay đổi đầy đủ và được sắp theo thứ tự kinh doanh.

Nếu pipeline chỉ nhận **snapshot mới nhất mỗi đêm** và không bảo đảm thấy mọi lần đổi, phải đặt tên/ghi chú chính xác rằng previous_region là **giá trị trước lần quan sát thay đổi gần nhất**, không được tuyên bố nó luôn là vùng trước theo nghiệp vụ.

Một sourceVersion tăng theo **mọi cập nhật Store**, không chỉ vùng, có thể có các version trung gian chỉ sửa tên. Khi phát hiện gap, cần biết loại sự kiện nào còn thiếu; không thể mặc định mỗi version bị bỏ là một lần đổi vùng.

## 8. Truy vấn so sánh vùng trước và vùng hiện tại

Giả sử trong tháng 10, hai cửa hàng có doanh số:

| store_id | Doanh số tháng 10 | current_region | previous_region |
| --- | ---: | --- | --- |
| S-101 | 120.000.000 VND | Trung | Bắc |
| S-102 | 80.000.000 VND | Nam | NULL |

Tập fact không đổi. Nhưng cách nhóm cho ra:

| Cách nhóm | Bắc | Trung | Nam | Tổng |
| --- | ---: | ---: | ---: | ---: |
| Theo **vùng hiện tại** | 0 | 120 triệu | 80 triệu | 200 triệu |
| Theo **cách phân loại liền trước** (giữ nguyên cửa hàng chưa đổi) | 120 triệu | 0 | 80 triệu | 200 triệu |

Đó là **phân bổ lại một tập doanh số** theo hai cách tổ chức, không phải tăng/giảm doanh thu thực tế hay so sánh tháng trước–tháng này.

### 8.1. Tổng hợp theo vùng hiện tại

~~~sql
SELECT d.current_region AS region,
       SUM(f.gross_sales_vnd) AS sales_vnd
FROM mart.fact_paid_order_line AS f
JOIN mart.dim_store_scd3 AS d
  ON d.tenant_id = f.tenant_id
 AND d.store_key = f.store_key
WHERE f.tenant_id = :tenant_id
  AND f.paid_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND f.paid_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY d.current_region
ORDER BY region;
~~~

### 8.2. Tổng hợp theo vùng ngay trước lần đổi mới nhất

Nếu yêu cầu nghiệp vụ quy định **cửa hàng chưa có previous_region được giữ nguyên trong nhóm hiện tại**, có thể dùng COALESCE:

~~~sql
SELECT COALESCE(d.previous_region, d.current_region)
           AS baseline_region,
       SUM(f.gross_sales_vnd) AS sales_vnd
FROM mart.fact_paid_order_line AS f
JOIN mart.dim_store_scd3 AS d
  ON d.tenant_id = f.tenant_id
 AND d.store_key = f.store_key
WHERE f.tenant_id = :tenant_id
  AND f.paid_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND f.paid_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
GROUP BY COALESCE(d.previous_region, d.current_region)
ORDER BY baseline_region;
~~~

**COALESCE là một quyết định báo cáo, không phải sự thật lịch sử.** previous_region NULL có thể nghĩa là chưa đổi, chưa được quan sát hoặc thiếu dữ liệu. Nếu "chưa biết" phải là nhóm riêng, không được dùng COALESCE như trên; có thể hiển thị "Chưa có vùng trước" và thêm cột chất lượng dữ liệu.

### 8.3. So sánh hai phương án trên cùng một bản tổng hợp

Tránh JOIN fact với chính nó rồi nhân số dòng. Trước hết tổng hợp doanh số **một lần theo cửa hàng**, sau đó tạo hai góc nhìn:

~~~sql
WITH sales_by_store AS (
    SELECT tenant_id, store_key,
           SUM(gross_sales_vnd) AS sales_vnd
    FROM mart.fact_paid_order_line
    WHERE tenant_id = :tenant_id
      AND paid_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND paid_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07'
    GROUP BY tenant_id, store_key
),
regional_views AS (
    SELECT 'CURRENT' AS classification,
           d.current_region AS region,
           s.sales_vnd
    FROM sales_by_store AS s
    JOIN mart.dim_store_scd3 AS d
      ON d.tenant_id = s.tenant_id
     AND d.store_key = s.store_key

    UNION ALL

    SELECT 'PREVIOUS_OR_CURRENT' AS classification,
           COALESCE(d.previous_region, d.current_region) AS region,
           s.sales_vnd
    FROM sales_by_store AS s
    JOIN mart.dim_store_scd3 AS d
      ON d.tenant_id = s.tenant_id
     AND d.store_key = s.store_key
)
SELECT classification, region, SUM(sales_vnd) AS sales_vnd
FROM regional_views
GROUP BY classification, region
ORDER BY classification, region;
~~~

Hai tổng theo classification **nên bằng nhau** nếu cùng tập fact và mỗi hàng dimension chỉ khớp đúng một hàng; đó là một kiểm tra tính nhất quán hữu ích. Tuy nhiên tổng bằng nhau **không chứng minh các vùng được gán đúng**.

### Vấn đề thời điểm chạy báo cáo

Nếu S-101 lại chuyển **Trung → Nam** vào tháng 11 rồi người dùng chạy lại truy vấn tháng 10, current_region=Nam, previous_region=Trung. Báo cáo tháng 10 theo **"vùng trước hiện tại"** nay cho kết quả khác báo cáo đã chạy hồi tháng 10. Đó là hành vi dự kiến của SCD3 nhưng có thể không phù hợp với yêu cầu **tái lập báo cáo lịch sử đã phát hành**.

Nếu cần lưu số liệu "như đã công bố ngày 31/10", phải đóng băng snapshot dimension hoặc kết quả phân nhóm theo phiên bản báo cáo, hoặc sử dụng lịch sử đầy đủ. Không thể chỉ ghi ngày truy vấn vào báo cáo rồi khôi phục một previous_region đã bị ghi đè.

## 9. Tránh ba nhầm lẫn quan trọng trong KPI

### 9.1. "Vùng trước" không đồng nghĩa "vùng tại ngày giao dịch"

SCD3 current/previous không xác định được mọi khoảng thời gian hiệu lực. Đừng lấy previous_region của tháng 11 áp cho các giao dịch tháng 2 rồi đặt tên là "vùng của giao dịch tháng 2".

### 9.2. Phân loại lại không phải tăng trưởng

Giả sử tổng tháng 10 là 200 triệu và tổng tháng 9 là 180 triệu. Việc nhóm 120 triệu từ Trung về Bắc theo cột previous chỉ **đổi cách phân loại** của cùng một doanh số, không làm tổng thành 320 triệu và không tự cho biết tăng trưởng theo vùng. Nếu so sánh tăng trưởng cùng kỳ, cần bảo đảm **cùng định nghĩa phân vùng** cho cả hai kỳ và cùng chính sách thay đổi thuộc tính.

### 9.3. Không nhầm grain của fact với grain của dimension

fact_paid_order_line là **một dòng bán**; dim_store_scd3 là **một cửa hàng**. JOIN theo store_key là quan hệ nhiều fact → một dimension. Nếu ai đó vô tình tạo nhiều hàng dimension cho cùng store_key/business key, doanh số sẽ bị nhân lên. Ngược lại, COUNT(*) sau JOIN vẫn là **số dòng bán**, không phải số cửa hàng hay số đơn.

Khi so sánh doanh số có nhiều tiền tệ, cần chính sách quy đổi trước khi SUM; bài dùng VND cho nhất quán.

## 10. Type 3 với nhiều thuộc tính thay đổi độc lập

Một Store có thể đổi cả **vùng quản lý** và **người phụ trách**. Hai thuộc tính này không nhất thiết thay cùng lúc. Có thể dùng:

| Cột | Ý nghĩa |
| --- | --- |
| current_region / previous_region | Vùng mới nhất / ngay trước lần đổi vùng |
| region_changed_at | Mốc đổi vùng gần nhất |
| current_manager_id / previous_manager_id | Quản lý mới nhất / ngay trước lần đổi quản lý |
| manager_changed_at | Mốc đổi quản lý gần nhất |

Quy tắc xử lý:

- Event **StoreRegionChanged** chỉ xoay current_region → previous_region; không thay previous_manager_id.
- Event **StoreManagerChanged** chỉ xoay manager tương ứng.
- Event đổi **tên hiển thị cửa hàng** có thể xử lý như Type 1 trên store_name, không xoay hai nhóm cột Type 3.
- Nếu hai trường đổi trong cùng một sự kiện theo chính sách nghiệp vụ, cập nhật cả hai một cách nguyên tử nhưng vẫn giữ mốc thời gian/nguồn của từng thuộc tính theo hợp đồng.

Một trường sourceVersion dùng chung cho Store có thể hỗ trợ thứ tự cập nhật toàn entity. Nếu các hệ thống khác nhau có authority và sequence độc lập cho region/manager, một version toàn cục tự sinh tại pipeline **không tự bảo đảm** trật tự của cả hai nguồn. Cần mô hình quyền sở hữu và version/sequence theo trường hoặc theo nguồn có thẩm quyền.

### Có thể giữ nhiều hơn một giá trị cũ không?

Có thể thiết kế:

~~~text
current_region
previous_region
previous_2_region
~~~

nhưng đây là **lịch sử hữu hạn theo số cột**. Mỗi lần đổi tiếp phải xoay đúng thứ tự và tính toán chi phí mở rộng schema khi cần thêm mốc. Một yêu cầu **"truy vấn mọi lần đổi trong 5 năm"** là tín hiệu mạnh để dùng bảng lịch sử hoặc Type 2 thay vì tiếp tục tạo previous_3, previous_4...

Nếu yêu cầu là so sánh cố định "cơ cấu trước tái cấu trúc 2025" với "cơ cấu hiện hành", một cột baseline_2025_region có thể rõ nghĩa hơn previous_region trượt.

## 11. Sự kiện đến trễ, correction và thời gian hiệu lực

Một sự kiện **đến muộn** không nhất thiết là thay đổi **cũ hơn về nghiệp vụ**. Ví dụ nguồn gửi correction: tại ngày 15/10 vùng đúng phải là **Nam** thay vì **Trung**, nhưng correction chỉ được gửi ngày 20/11.

Hai loại thứ tự cần phân biệt:

- **Thứ tự version/commit tại nguồn:** giá trị nào là bản ghi mới nhất được nguồn chấp nhận.
- **Thời gian hiệu lực nghiệp vụ:** thay đổi có tác dụng từ lúc nào, có thể được sửa hồi tố.

SCD3 với current/previous và một timestamp gần nhất **không đủ để tái dựng mọi thay đổi theo thời gian hiệu lực**. Nếu có nhu cầu cập nhật *as-of* sau correction, hãy định nghĩa bảng lịch sử hiệu lực, quy tắc restatement fact hoặc Type 2 phù hợp. Không sửa previous_region để "đoán" chuỗi lịch sử còn thiếu.

### Thiết kế pipeline an toàn hơn

~~~mermaid
flowchart LR
    S["Nguồn quản lý Store"] --> C["CDC / domain events"]
    C --> R["Raw change log<br/>eventId, sourceVersion, eventTime"]
    R --> V["Validate + deduplicate<br/>kiểm tra gap và thứ tự"]
    V --> P["SCD3 projection<br/>current + previous"]
    P --> BI["Báo cáo phân nhóm hiện tại / trước"]
    R -.->|"Khi cần replay/correction"| V
~~~

Một chuỗi xử lý nên:

1. Nhận ID đối tượng có **namespace tenant** và kiểm tra quyền/source.
2. Xác thực eventType, schema, version, effectiveAt và giá trị vùng.
3. Deduplicate theo eventId cùng **nguồn**; xử lý xung đột nếu cùng ID/version nhưng nội dung khác.
4. Kiểm tra mọi thay đổi vùng có được quan sát theo thứ tự không. Nếu có gap hoặc đảo thứ tự, chờ, tải lịch sử hoặc đánh dấu previous không đầy đủ.
5. So sánh giá trị **vùng thực sự** trước khi xoay, không xoay vì một event sửa tên.
6. Cập nhật current/previous/timestamp/version **nguyên tử** và ghi metadata nạp.
7. Kiểm tra số lượng cửa hàng, vùng hợp lệ, các chỉ số phân nhóm và mức đầy đủ sau nạp.
8. Phát hành báo cáo kèm **data-as-of / dimension-as-of** hoặc version của lần chốt.

Raw change log có thể được lưu tách biệt trong pipeline để replay, nhưng việc tồn tại log **không có nghĩa** bảng chiều Type 3 đã có lịch sử truy vấn theo thời gian. Khi cần phép JOIN lịch sử trên warehouse, phải xây mô hình lịch sử tương ứng từ log.

## 12. Tính nguyên tử và tranh chấp khi nhiều worker cập nhật cùng cửa hàng

Trong PostgreSQL, hai UPDATE cùng một hàng phải cạnh tranh khóa hàng. Ở mức READ COMMITTED, khi một lệnh chờ transaction khác và tiếp tục, điều kiện được đánh giá lại trên phiên bản hàng phù hợp. WHERE source_version < :source_version giúp sự kiện có version thấp hơn không ghi đè giá trị mới hơn.

Nhưng cần phân biệt:

- **Không ghi đè current bằng bản cũ:** có thể bảo vệ bằng version condition.
- **previous luôn đúng là giá trị liền trước của nguồn:** đòi chuỗi thay đổi đầy đủ/đúng thứ tự hoặc payload từ nguồn có bảo đảm.

Hai tính chất không tương đương. UPDATE đơn dòng an toàn về mặt atomicity vẫn có thể cho **previous sai về ngữ nghĩa** nếu bỏ qua một thay đổi trung gian.

Với warehouse hỗ trợ MERGE theo batch, có thể dồn tất cả thay đổi của một cửa hàng trong một batch, sắp xếp bằng **source order có thẩm quyền**, lần lượt áp quy tắc xoay rồi ghi hàng cuối. Không lấy giá trị "cuối cùng theo receivedAt" nếu receivedAt chỉ là thời điểm nhận trên pipeline.

**Idempotency khi chạy lại batch:** Nếu replay cùng sourceVersion, không được xoay previous thêm lần nữa. Nếu retry một batch sau khi giao dịch commit nhưng phản hồi bị mất, kiểm tra version và state đã ghi. Nếu phát hiện bản trùng khác payload, đưa vào quy trình kiểm tra thay vì bỏ qua im lặng.

## 13. Khi nào nên chọn Type 2, Type 3 hoặc thiết kế kết hợp?

Hãy dùng câu hỏi báo cáo để quyết định:

| Yêu cầu | Ứng viên phù hợp | Vì sao |
| --- | --- | --- |
| Chỉ cần tên cửa hàng mới nhất; không quan tâm tên cũ | Type 1 cho store_name | Ghi đè đơn giản, không có nhu cầu lịch sử |
| Cùng tập doanh số cần xem theo **vùng hiện tại** và **vùng ngay trước** | Type 3 cho region | Hai góc nhìn trực tiếp, cùng một store_key |
| Cần xác định vùng cửa hàng tại **mọi ngày bán** trong ba năm | Type 2 hoặc bảng lịch sử hiệu lực | Nhiều phiên bản và khoảng hiệu lực |
| Cần giữ "vùng gốc ngày mở cửa" và "vùng hôm nay" | Type 3 với original_region + current_region | Baseline cố định thay vì previous trượt |
| Cần truy vấn vừa "as-of sale" vừa "phân loại theo vùng hiện tại" | Type 2 kết hợp cách gắn vùng hiện tại, hoặc hybrid | Hai phép nhìn khác bản chất |
| Chỉ có hai thời điểm tổ chức được chốt, muốn báo cáo so sánh cố định | Type 3 baseline có version kỳ chốt, hoặc snapshot riêng | Giảm rủi ro previous bị xoay ngoài dự kiến |
| Hàng trăm lần thay đổi mỗi ngày, cần replay/audit từng lần | Event history/Type 2, có thể thêm Type 3 làm projection | Type 3 đơn thuần mất chi tiết |

### Ví dụ Type 2 khác Type 3

Với Type 2, một Store thay vùng Bắc → Trung → Nam có thể được mô hình hóa:

| store_key | store_id | region | valid_from | valid_to |
| ---: | --- | --- | --- | --- |
| 501 | S-101 | Bắc | 2026-01-01 | 2026-10-15 |
| 803 | S-101 | Trung | 2026-10-15 | 2026-11-20 |
| 950 | S-101 | Nam | 2026-11-20 | NULL |

Khoảng hiệu lực dùng quy ước **[valid_from, valid_to)** — gồm đầu, không gồm cuối. Nếu fact lúc 01/10 cần vùng **tại thời điểm bán**, nó liên kết với phiên bản 501; fact lúc 01/11 với 803; fact lúc 01/12 với 950. Đó là điều Type 3 một hàng không tự biểu diễn sau nhiều lần đổi.

Với Type 3, một hàng S-101 vẫn có **store_key=501, current=Nam, previous=Trung**. Tất cả các fact cùng store_key đều có thể được gộp theo hai cột này khi báo cáo chạy, bất kể ngày bán.

Không nên kết luận Type 2 luôn tốt hơn chỉ vì lưu được nhiều lịch sử. Nó làm tăng số hàng, yêu cầu ánh xạ đúng hiệu lực, xử lý late-arriving data và truy vấn có thể phức tạp hơn. Type 3 là lựa chọn có chủ đích khi **chỉ cần số mốc hữu hạn**.

### Hybrid không tự giải quyết mọi vấn đề

Một thiết kế kết hợp Type 1/2/3 đôi khi được gọi là **Type 6** tùy tài liệu, có thể giữ giá trị hiện tại trong các bản ghi Type 2 bên cạnh lịch sử. Nhưng tên gọi không thay cho hợp đồng: phải ghi rõ trường nào bị ghi đè, trường nào tạo hàng mới, fact liên kết phiên bản nào và cách correction cập nhật lịch sử.

Nếu phần lớn báo cáo chỉ so sánh hai cách phân nhóm, có thể tạo một **Type 3 projection** từ nguồn lịch sử Type 2. Khi đó Type 3 phục vụ truy vấn tiện lợi, còn nguồn lịch sử vẫn bảo vệ khả năng tái dựng khi có thay đổi mới.

## 14. Chuyển từ Type 1 sang Type 3

Một tổ chức ban đầu chỉ lưu current_region trong dim_store. Sau đó có yêu cầu so sánh với vùng trước. Quy trình đổi mô hình:

1. Xác minh **ý nghĩa previous** với người sở hữu báo cáo: gần nhất, baseline hay một kỳ xác định?
2. Thêm previous_region nullable, region_changed_at và metadata version/nguồn nếu thiếu.
3. **Không tự chép current_region sang previous_region** rồi gọi là lịch sử. Nếu không có nguồn quá khứ, để NULL và công bố mức đầy đủ.
4. Nếu có audit log, CDC lịch sử hoặc một bảng phân công vùng đủ tin cậy, backfill previous chính xác theo quy tắc.
5. Đổi pipeline để xoay trường khi **vùng thay đổi thực**, xử lý thứ tự và idempotency.
6. Điều chỉnh semantic layer để có tên rõ ràng: Current Sales Region, Previous Observed Sales Region hoặc Baseline 2025 Region.
7. Kiểm thử các báo cáo đã có để đảm bảo current_region và store_key không đổi ngoài dự định.
8. Gắn version/cutoff báo cáo nếu các kết quả so sánh cần được tái lập sau các lần thay đổi tiếp theo.

Trong quá trình backfill, previous_region NULL có thể tồn tại trên một phần dữ liệu và có nghĩa **không biết**. Tránh dashboard coi tất cả NULL là "chưa từng chuyển vùng" nếu nguồn lịch sử chưa đầy đủ.

### Phân quyền và quy tắc truy cập

Bảng chiều phân tích có thể tổng hợp dữ liệu nhiều tenant. Tất cả đường JOIN, UPDATE và truy vấn phải giữ tenant_id và cơ chế phân quyền tương ứng. ID cửa hàng không tự cấp quyền đọc doanh số. Nếu previous attribute là người quản lý hoặc phân khúc khách hàng, cần lưu ý thông tin nhân sự/cá nhân, nguyên tắc dữ liệu tối thiểu và retention.

Việc một chiều chỉ giữ một giá trị cũ không miễn yêu cầu đối soát và phân quyền. Một phép nhóm phân tích vẫn có thể tiết lộ thông tin nhạy cảm nếu các nhóm quá nhỏ hoặc người dùng được xem dữ liệu ngoài phạm vi.

## 15. Kiểm thử theo trường hợp biên

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Nạp S-101 lần đầu với vùng Bắc | current=Bắc, previous=NULL, một hàng cho store |
| Vùng Bắc → Trung, sourceVersion lớn hơn | current=Trung, previous=Bắc, store_key giữ nguyên |
| Nhận lại chính event vừa áp dụng | Không xoay previous lần nữa |
| Event chỉ đổi storeName, vùng vẫn Trung | previous=Bắc, region_changed_at giữ nguyên |
| Trung → Nam sau đó | current=Nam, previous=Trung; phải biết Bắc không còn trong hàng |
| Nhận version Nam trước version Trung | Không được tuyên bố previous chính xác nếu đã bỏ qua Trung |
| Cùng sourceVersion nhưng payload khác | Cảnh báo xung đột, điều tra nguồn |
| Đổi vùng rồi chuyển lại vùng ban đầu | Theo thứ tự thay đổi thực, current/previous phản ánh hai bước gần nhất |
| Hai tenant có store_id trùng | Không gộp dữ liệu xuyên tenant |
| Vùng được đổi tên nhưng bản chất phân công không đổi | Không xoay region nếu chỉ sửa nhãn theo chính sách |
| Báo cáo tháng 10 chạy lại sau đổi vùng tháng 11 | Nhận diện rằng kết quả có thể tái phân loại; kiểm yêu cầu freeze/as-of |
| JOIN fact theo store_key | Mỗi fact khớp tối đa một hàng dimension cùng tenant |
| Nguồn lịch sử không đầy đủ khi migration | previous NULL/flag chất lượng, không tạo giá trị giả |

### Gợi ý unit/integration test cho phép xoay

Với dữ liệu khởi tạo:

~~~text
store = S-101
version = 10
current = Bắc
previous = NULL

Apply version 11, newRegion=Trung:
  current=Trung, previous=Bắc, version=11

Apply version 11 lần nữa:
  không đổi

Apply version 12, newRegion=Trung:
  current=Trung, previous=Bắc, version=12

Apply version 13, newRegion=Nam:
  current=Nam, previous=Trung, version=13
~~~

Test không chỉ kiểm tra rằng một câu UPDATE chạy thành công; hãy kiểm tra **ngữ nghĩa previous**, thứ tự nguồn, tính duy nhất business key, việc fact không bị nhân và sự thay đổi kết quả báo cáo theo thời điểm chạy.

## 16. Bài tập: phân khúc khách hàng trước và sau chiến dịch

**Bối cảnh:** Doanh nghiệp có chương trình thành viên Bronze, Silver, Gold. Mỗi Customer có customerId ổn định, trạng thái phân khúc hiện tại và ngày đổi hạng. Nhóm marketing muốn xem **giá trị mua hàng của cùng một tập khách** theo **hạng hiện nay** và theo **hạng liền trước**. Trong một quý, một khách có thể nâng hai hạng; một số khách chưa từng đổi.

**Câu hỏi:**

1. Đề xuất grain, khóa nghiệp vụ/khóa thay thế và các cột cho dim_customer SCD3. Đặt tên rõ nghĩa current_tier và previous_tier.
2. Với khách C-01 đi từ Bronze → Silver → Gold, hãy điền current_tier và previous_tier sau mỗi lần đổi. Sau lần cuối, có thể truy vấn toàn bộ lịch sử hạng của C-01 từ bảng chiều này không?
3. Đề xuất cách nhóm fact_purchase theo current_tier và previous_tier. Xử lý previous_tier=NULL cho khách chưa từng đổi theo hai chính sách khác nhau: **giữ nguyên hạng hiện tại** và **nhóm chưa biết**.
4. Marketing yêu cầu "doanh thu **tại từng thời điểm** khi khách còn Bronze/Silver/Gold trong 3 năm". Type 3 có còn phù hợp không? Giải thích cần Type 2, history hoặc snapshot gì.
5. Nếu nhận sự kiện nâng Gold trước sự kiện nâng Silver, UPDATE theo sourceVersion lớn nhất có thể tạo previous_tier nào sai? Hãy đề xuất cách xử lý.
6. Giả sử khách bị hạ Gold → Silver sau khi báo cáo cuối quý phát hành. Báo cáo dùng Type 3 sẽ đổi thế nào khi chạy lại? Làm sao đóng băng số liệu đã công bố?
7. Thiết kế ít nhất bốn test kiểm chứng khi đổi hạng, retry, thay thuộc tính không liên quan và sự kiện đến sai thứ tự.

### Hướng giải

- **Grain dim_customer:** một hàng cho mỗi (tenantId, customerId). Giữ customer_key ổn định để fact_purchase tham chiếu.
- Sau C-01 bắt đầu Bronze: current=Bronze, previous=NULL; sau nâng Silver: current=Silver, previous=Bronze; sau nâng Gold: current=Gold, previous=Silver. Bronze không còn trong các cột Type 3 mặc định.
- Truy vấn theo previous_tier cần chính sách cho NULL. Nếu dùng COALESCE(previous_tier, current_tier), hãy đặt tên "phân loại trước hoặc giữ nguyên" thay vì "hạng lịch sử tại ngày mua".
- Yêu cầu "tại từng thời điểm trong 3 năm" cần **lịch sử theo hiệu lực**, thường Type 2 hoặc fact snapshot tại giao dịch. Type 3 một hàng không đủ khi có nhiều lần nâng/hạ.
- Khi event Gold đến trước Silver, previous được ghi từ trạng thái đã biết có thể là Bronze thay vì Silver. Chỉ xử lý theo version lớn hơn không đảm bảo previous thật; cần replay/đảm bảo thứ tự hoặc snapshot nguồn chứa previous chính xác.
- Báo cáo theo current/previous là **so sánh phân loại lại**, không tự là số liệu giá trị giao dịch theo hạng tại thời điểm bán. Nếu cần tái lập báo cáo quý đã chốt, lưu phiên bản chiều/baseline riêng hoặc kết quả đã phát hành.

## 17. Checklist và kết luận

- **Một hàng** của dimension là đối tượng nào, unique key có bao gồm tenant/namespace không?
- previous có nghĩa **liền trước**, **giá trị gốc** hay **mốc cố định**? Tên cột có nói đúng không?
- Chỉ xoay previous khi **thuộc tính theo dõi thực sự đổi**, không xoay do retry hay trường khác đổi?
- Pipeline có xử lý eventId, sourceVersion, gap/out-of-order và correction theo nguồn có thẩm quyền không?
- Một lần đổi có được cập nhật current, previous, thời điểm và version **nguyên tử** không?
- Giá trị previous NULL có thể là chưa đổi hay lịch sử không biết; chính sách báo cáo có phân biệt chưa?
- Fact giữ khóa thay thế ổn định, JOIN mỗi fact với đúng **một** hàng chiều, không nhân doanh số không?
- Có phân biệt **so sánh phân nhóm của cùng tập fact** với **thuộc tính tại thời điểm fact** không?
- Khi current/previous thay đổi, báo cáo kỳ cũ có thể đổi; có cần bản chốt/snapshot để tái lập không?
- Nếu cần **mọi lần đổi**, đã chọn Type 2 hoặc bảng lịch sử thay vì cố nhét vào một cột previous chưa?
- Thuộc tính khác như tên hiển thị, manager, vùng có chính sách Type 1/2/3 riêng và quyền sở hữu rõ không?
- Thiết kế đã được kiểm chứng với đổi hai lần, chuyển ngược, event trùng, event trễ, thiếu lịch sử và nhiều tenant chưa?

**Kết luận:** **SCD Type 3** là cách mô hình hóa **một phần lịch sử được chọn** ngay trên **một hàng chiều**. Các cột current/previous giúp so sánh cùng một tập giao dịch theo hai cách phân loại và giữ khóa tham chiếu của fact ổn định. Đổi lại, mỗi lần xoay có thể làm mất giá trị cũ hơn và tái phân loại những báo cáo đã chạy. Vì vậy, hãy chỉ dùng Type 3 khi nghiệp vụ thực sự cần **một số góc nhìn hữu hạn**, mô tả rõ ý nghĩa previous/baseline, bảo vệ thứ tự cập nhật và áp dụng Type 2 hoặc lịch sử riêng khi yêu cầu truy vấn **đúng theo mọi thời điểm quá khứ**. Đó là cách biến nhu cầu báo cáo thành một mô hình dữ liệu minh bạch, kiểm chứng được và có thể tiến hóa.
