# Chiều thay đổi chậm kiểu 2: tạo phiên bản và khoảng hiệu lực

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **Slowly Changing Dimension Type 2 (SCD Type 2)** như một cách **giữ lịch sử thuộc tính chiều bằng nhiều phiên bản hàng**, thay vì ghi đè giá trị cũ.
- Phân biệt **khóa nghiệp vụ (natural/business key)**, **khóa thay thế (surrogate key)**, **số phiên bản** và **khoảng thời gian hiệu lực**.
- Thiết kế khoảng **[effective_from, effective_to)** không giao nhau, chỉ một phiên bản hiện hành và quy tắc xử lý mốc thời gian biên.
- Ghi một thay đổi chiều trong PostgreSQL có kiểm soát cạnh tranh; nối fact với **phiên bản chiều đúng tại thời điểm sự kiện**.
- Nhận diện các vấn đề **sự kiện đến muộn, hiệu lực hồi tố, xóa thực thể, đối soát, thay đổi schema** và sự khác nhau giữa *valid time* với *recorded time*.
- Chọn SCD Type 1, Type 2, Type 3 hoặc phối hợp theo câu hỏi phân tích; không tự động tạo phiên bản cho mọi thuộc tính.

Bài thuộc chương **Bảng chiều** của **DATABASE_DATA_MODELING**. Khi chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, cần xác định không chỉ thực thể, quan hệ, khóa và chỉ mục mà còn cả **giá trị của một thuộc tính đúng vào thời điểm nào**. Điều này đặc biệt quan trọng khi nối bảng fact với dimension trong kho phân tích, dù nguồn nghiệp vụ ban đầu là quan hệ, document hay một hệ thống khác.

## 1. Bài toán: khách hàng đổi phân khúc, báo cáo quá khứ phải giữ nguyên nghĩa

Một hệ thống bán hàng có khách hàng **C-42**. Trong năm 2026:

| Khoảng thời gian nghiệp vụ | Phân khúc khách hàng |
| --- | --- |
| Từ 01/01 đến trước 15/06 | **BRONZE** |
| Từ 15/06 đến trước 01/09 | **SILVER** |
| Từ 01/09 trở đi | **GOLD** |

Có ba đơn hàng:

| Đơn hàng | Thời điểm xác nhận | Phân khúc cần dùng cho báo cáo “tại lúc mua” |
| --- | --- | --- |
| **O-101** | 31/05/2026 | BRONZE |
| **O-102** | 01/07/2026 | SILVER |
| **O-103** | 05/10/2026 | GOLD |

Nếu bảng **dim_customer** chỉ có một hàng cho mỗi **customer_id** và luôn UPDATE **segment_code = 'GOLD'**, mọi đơn trước đó có thể bị phân loại lại thành GOLD khi báo cáo JOIN theo customer_id. Kết quả ấy có thể đúng cho câu hỏi **“Doanh thu lịch sử theo phân khúc hiện hành của khách?”**, nhưng **sai** cho câu hỏi **“Khách thuộc phân khúc nào khi mua?”**.

SCD Type 2 giải quyết bằng cách **giữ các phiên bản dimension khác nhau theo thời gian**. Khi phân khúc đổi, hệ thống **đóng hiệu lực phiên bản cũ** rồi **thêm phiên bản mới**, thay vì UPDATE đè lên thuộc tính lịch sử.

> **SCD Type 2 không làm đông cứng thực thể khách hàng: nó giữ lịch sử những phiên bản thuộc tính mà báo cáo cần nhìn lại.**

## 2. Tuyên bố grain của dimension trước khi tạo bảng

Với SCD Type 2, tuyên bố grain phù hợp là:

> **Một hàng của dim_customer_version biểu diễn một phiên bản thuộc tính phân tích của một khách hàng trong một khoảng thời gian hiệu lực nghiệp vụ.**

Điều đó có nghĩa:

- Một **customer_id** có thể tương ứng **nhiều hàng** dimension.
- Một **customer_sk** (surrogate key) định danh **một phiên bản hàng cụ thể**, không phải toàn bộ khách hàng.
- Hai phiên bản khác nhau của cùng khách hàng có thể mang **cùng một tên** nhưng khác phân khúc, vùng hoặc thuộc tính được theo dõi.
- Khoảng hiệu lực của các phiên bản cùng khách **không được chồng lấn** nếu hợp đồng yêu cầu đúng một phiên bản tại mỗi thời điểm.
- Bảng fact cần chọn **phiên bản** phù hợp với thời điểm của sự kiện, không nối đại theo bản ghi hiện tại.

Minh họa:

~~~text
Customer C-42 (natural key ổn định)
           |
           +-- customer_sk=1001 | BRONZE | [01/01, 15/06)
           |
           +-- customer_sk=1002 | SILVER | [15/06, 01/09)
           |
           +-- customer_sk=1003 | GOLD   | [01/09, +infinity)

Fact O-101 (31/05) --> 1001
Fact O-102 (01/07) --> 1002
Fact O-103 (05/10) --> 1003
~~~

Ở đây **+infinity** chỉ khoảng còn hiệu lực chưa có ngày kết thúc. Trong SQL bên dưới, ta dùng **effective_to = NULL** để biểu diễn cận trên chưa xác định, không dùng NULL để nói “không có dữ liệu”.

### 2.1. Khóa nghiệp vụ, khóa thay thế, phiên bản: đừng trộn vai trò

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **tenant_id + customer_id** | (7, C-42) | Định danh **một khách hàng** trong phạm vi nghiệp vụ |
| **customer_sk** | 1001, 1002, 1003 | Định danh **mỗi hàng phiên bản** dimension |
| **version_no** | 1, 2, 3 | Số thứ tự phiên bản ở dimension, hỗ trợ kiểm tra/lần vết |
| **source_revision** | 15, 21, 37 | Phiên bản ở hệ thống nguồn; không nhất thiết bằng version_no |
| **effective_from** | 2026-06-15 00:00+07 | Thời điểm bản phiên này bắt đầu có hiệu lực nghiệp vụ |
| **effective_to** | 2026-09-01 00:00+07 | Thời điểm **không còn** hiệu lực, cận trên loại trừ |
| **recorded_at** | Thời điểm ETL nhận/lưu | Metadata kỹ thuật: khi warehouse biết đến bản phiên |

**Natural key** cần ổn định, có phạm vi định danh rõ và không tái sử dụng tùy ý. Trong hệ đa tenant, chỉ **customer_id** có thể không duy nhất toàn cục. **Surrogate key** là khóa kỹ thuật của version: nếu dùng **customer_id** làm khóa chính một hàng, không thể có nhiều version cùng khách.

**version_no** không phải là cột thời gian: hai bản phiên phải xác định hiệu lực bằng khoảng thời gian và quy tắc nghiệp vụ. Không dùng **MAX(version_no)** để thay thế phép tra **as-of** cho một đơn cũ.

## 3. Chọn SCD Type 2 vì câu hỏi phân tích, không chỉ vì thuộc tính thay đổi

Có những cách xử lý phổ biến:

| Chiến lược | Khi thuộc tính đổi | Câu hỏi phù hợp | Đánh đổi |
| --- | --- | --- | --- |
| **Type 0** | Giữ giá trị ban đầu | Thuộc tính thực sự bất biến theo hợp đồng | Không phản ánh thay đổi sau này |
| **Type 1** | UPDATE đè lên hàng hiện có | Phân loại lại toàn bộ lịch sử theo giá trị hiện hành, sửa lỗi không cần lịch sử | Không tái hiện được giá trị cũ từ dimension |
| **Type 2** | Đóng bản cũ, INSERT bản mới | Phân tích **theo trạng thái tại thời điểm sự kiện** | Nhiều hàng/version, logic nạp và JOIN phức tạp |
| **Type 3** | Giữ giá trị trước và hiện tại trong vài cột | So hai mốc xác định như previous/current | Không giữ trọn chuỗi thay đổi bất kỳ |
| **Kết hợp** | Chọn chính sách cho từng thuộc tính | Vừa sửa lỗi, vừa truy lịch sử thuộc tính quan trọng | Phải có hợp đồng rõ cho từng field |

Ví dụ:

- **customer_segment**: có thể dùng Type 2 nếu muốn biết khách thuộc nhóm nào tại ngày mua.
- **Sửa lỗi chính tả tên tỉnh**: có thể Type 1 nếu đây chỉ là chỉnh lỗi nhập liệu, không phải thay đổi phân vùng nghiệp vụ.
- **Tên hiển thị hiện hành**: có thể Type 1 nếu báo cáo không cần lịch sử tên.
- **Vùng quản lý bán hàng**: có thể Type 2 khi việc chuyển vùng ảnh hưởng trách nhiệm và chỉ tiêu doanh thu quá khứ.
- **Người dùng yêu cầu xóa dữ liệu cá nhân**: phải tuân chính sách lưu giữ/xóa; không mặc định tạo vô hạn phiên bản thông tin nhạy cảm.

Một **dimension dạng Type 2** không nhất thiết tạo version mới khi **bất kỳ** cột nào thay đổi. Hãy chỉ rõ **tracked attributes** tạo phiên bản và **Type 1 attributes** có thể được sửa tại chỗ theo chính sách. Nếu cập nhật một field Type 1 trên mọi version lịch sử, đó là lựa chọn chủ đích để chuẩn hóa/sửa dữ liệu, không phải cơ chế làm mới Type 2 cho cùng một sự kiện nghiệp vụ.

## 4. Khoảng hiệu lực: quy ước nửa mở [from, to)

Một hợp đồng đơn giản và dễ kiểm chứng:

~~~text
[effective_from, effective_to)
  - Có hiệu lực tại effective_from.
  - Không còn hiệu lực tại effective_to.
  - effective_to = NULL: chưa biết thời điểm kết thúc, mở về tương lai.
~~~

Với khách C-42:

| Phiên bản | effective_from | effective_to | Phân khúc |
| --- | --- | --- | --- |
| v1 | 2026-01-01 00:00+07 | 2026-06-15 00:00+07 | BRONZE |
| v2 | 2026-06-15 00:00+07 | 2026-09-01 00:00+07 | SILVER |
| v3 | 2026-09-01 00:00+07 | NULL | GOLD |

Một đơn phát sinh **đúng 00:00 ngày 15/06** thuộc **v2**, không thuộc v1. Nếu dùng điều kiện **BETWEEN start AND end** (bao gồm cả hai cận), cả v1 và v2 có thể khớp cùng một thời điểm biên. Vì thế, điều kiện tra as-of là:

~~~sql
WHERE effective_from <= :event_time
  AND (
      effective_to > :event_time
      OR effective_to IS NULL
  )
~~~

Trong PostgreSQL có thể dùng kiểu range **tstzrange(effective_from, effective_to, '[)')**, với NULL ở cận trên mang nghĩa không bị chặn. Chọn **TIMESTAMPTZ** khi lưu thời điểm tuyệt đối và ghi rõ múi giờ kinh doanh khi xác định “có hiệu lực từ ngày nào”. Nếu đổi ngày theo múi giờ địa phương, chuyển đúng ranh giới ngày địa phương sang timestamp có timezone; không giả định mọi ngày ở mọi timezone luôn 24 giờ.

### 4.1. Đừng dùng các trường thời gian với ý nghĩa tráo đổi

- **valid/effective time:** thời điểm phân khúc được nghiệp vụ xem là có hiệu lực.
- **source updated/commit time:** lúc hệ thống nguồn ghi thay đổi.
- **warehouse loaded/recorded time:** lúc pipeline đưa dữ liệu vào kho.
- **fact event time:** lúc đơn đã được xác nhận, thanh toán hoặc giao theo grain của fact.

Ví dụ quản trị viên nhập ngày 20/06 rằng phân khúc đã đổi **có hiệu lực từ 15/06**. Nếu ETL dùng ngày 20/06 làm effective_from, doanh thu các ngày 15–19/06 bị phân loại sai. Nhưng cũng không thể tin mọi timestamp người dùng đưa vào; cần quy tắc duyệt ngày hiệu lực và quản lý sửa hồi tố.

**Type 2 tiêu chuẩn thường giữ lịch sử theo một trục thời gian hiệu lực**. Nếu cần trả lời cả “ngày 18/06 hệ thống từng biết điều gì?” và “về sau ta xác nhận điều gì có hiệu lực ngày 18/06?”, đó là **hai chiều thời gian (bitemporal)** và cần thiết kế riêng, không tự có chỉ nhờ effective_from/effective_to.

## 5. Thiết kế PostgreSQL: bảo vệ phiên bản và chống khoảng chồng lấn

Đây là mô hình minh họa cho dimension khách hàng theo **(tenant_id, customer_id)**. Bảng định danh giúp khóa một khách hàng khi ghi phiên bản, kể cả lúc khách chưa có bản phiên đầu tiên.

### 5.1. Bảng định danh khách và các phiên bản chiều

~~~sql
CREATE TABLE dim_customer_identity (
    tenant_id BIGINT NOT NULL,
    customer_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE dim_customer_version (
    customer_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id TEXT NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    segment_code TEXT NOT NULL,
    region_code TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dim_customer_identity
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES dim_customer_identity (tenant_id, customer_id),
    CONSTRAINT ck_customer_valid_period
        CHECK (
            effective_to IS NULL
            OR effective_to > effective_from
        ),
    CONSTRAINT uq_customer_version_number
        UNIQUE (tenant_id, customer_id, version_no),
    CONSTRAINT uq_customer_valid_start
        UNIQUE (tenant_id, customer_id, effective_from)
);

-- Mỗi khách chỉ có tối đa một version mở về tương lai.
CREATE UNIQUE INDEX ux_dim_customer_current
    ON dim_customer_version (tenant_id, customer_id)
    WHERE effective_to IS NULL;

CREATE INDEX ix_dim_customer_asof
    ON dim_customer_version
       (tenant_id, customer_id, effective_from DESC);
~~~

**Giải thích khóa:**

- **customer_sk** duy nhất cho mỗi hàng version, thuận tiện để fact tham chiếu một phiên bản cụ thể.
- **(tenant_id, customer_id)** ở bảng **identity** định danh khách hàng theo nghiệp vụ.
- **(tenant_id, customer_id, version_no)** không trùng các số phiên bản.
- **(tenant_id, customer_id, effective_from)** không trùng mốc bắt đầu.
- **unique partial index** ngăn hai phiên bản đồng thời cùng có **effective_to IS NULL**.
- **CHECK** ngăn khoảng rỗng hoặc ngược chiều khi đã có điểm kết thúc.

Nhưng có một lỗ hổng quan trọng: những ràng buộc trên **không tự ngăn hai khoảng hữu hạn chồng nhau**. Ví dụ v1 [01/01, 01/08) và v2 [01/06, 01/09) đều có effective_to khác NULL, các UNIQUE ở trên không cấm chúng.

### 5.2. Exclusion constraint bảo vệ khoảng thời gian

PostgreSQL có thể dùng **GiST exclusion constraint** để cấm hai khoảng hiệu lực của cùng khách giao nhau. Trong môi trường được phép cài extension **btree_gist**:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE dim_customer_version
ADD CONSTRAINT ex_customer_no_overlap
EXCLUDE USING gist (
    tenant_id WITH =,
    customer_id WITH =,
    (tstzrange(effective_from, effective_to, '[)')) WITH &&
);
~~~

Ý nghĩa: với **cùng tenant_id và customer_id**, hai khoảng **tstzrange** không được **&&** (giao nhau). Hai khoảng kề nhau **[A,B)** và **[B,C)** vẫn hợp lệ. Cột **effective_to = NULL** là cận trên không giới hạn nên hai phiên bản hiện hành không thể cùng tồn tại.

**Lưu ý vận hành:** extension cần quyền và sự chấp thuận của hệ thống; GiST/exclusion constraint có chi phí chỉ mục và ghi. Trong kho dữ liệu không hỗ trợ ràng buộc này, pipeline phải kiểm tra khoảng chồng lấn và serialize ghi theo khóa nghiệp vụ, đồng thời có job đối soát. **CHECK constraint riêng từng hàng không thể chứng minh các khoảng giữa nhiều hàng không giao nhau**.

Exclusion constraint ngăn **overlap**, nhưng **không buộc các khoảng phải liền mạch**. Nếu cần mỗi thời điểm từ lần xuất hiện đầu tới hiện tại đều có version, phải kiểm tra **gap**. Hệ thống cũng có thể chủ đích cho phép gap khi khách chưa tồn tại hoặc ngừng hoạt động; điều đó phải ghi trong hợp đồng.

## 6. Ghi phiên bản đầu và thay đổi về sau

### 6.1. Thêm phiên bản ban đầu

Ví dụ tạo khách C-42 thuộc tenant 7 từ đầu năm:

~~~sql
BEGIN;

INSERT INTO dim_customer_identity (tenant_id, customer_id)
VALUES (7, 'C-42');

INSERT INTO dim_customer_version (
    tenant_id, customer_id, version_no,
    segment_code, region_code,
    effective_from, effective_to
)
VALUES (
    7, 'C-42', 1,
    'BRONZE', 'SOUTH',
    TIMESTAMPTZ '2026-01-01 00:00:00+07',
    NULL
);

COMMIT;
~~~

Một phiên bản **current** không có nghĩa mọi lịch sử đã tồn tại. Nếu hệ thống chỉ bắt đầu thu thập từ 01/01, báo cáo trước ngày đó có thể **không biết phân khúc** của khách; không được dùng BRONZE để lấp khoảng lịch sử chưa có chứng cứ.

### 6.2. Chuyển BRONZE sang SILVER trong cùng giao dịch

Giả sử ngày hiệu lực tiếp theo **15/06**, thay đổi đã được kiểm tra và nguồn đã xác nhận. Để tránh hai worker cùng tạo version cho một khách, các đường ghi có thể **khóa hàng identity của khách** trước khi đóng/mở version.

~~~sql
BEGIN;

-- Mọi đường ghi phiên bản của khách cần tuân thủ khóa này.
SELECT tenant_id, customer_id
FROM dim_customer_identity
WHERE tenant_id = 7 AND customer_id = 'C-42'
FOR UPDATE;

-- Trước khi thực hiện: xác thực source revision, ngày hiệu lực,
-- version hiện hành và thay đổi thuộc tính theo hợp đồng.
WITH closed AS (
    UPDATE dim_customer_version
    SET effective_to = TIMESTAMPTZ '2026-06-15 00:00:00+07'
    WHERE tenant_id = 7
      AND customer_id = 'C-42'
      AND effective_to IS NULL
      AND effective_from <
          TIMESTAMPTZ '2026-06-15 00:00:00+07'
      AND segment_code = 'BRONZE'
    RETURNING tenant_id, customer_id, version_no
)
INSERT INTO dim_customer_version (
    tenant_id, customer_id, version_no,
    segment_code, region_code,
    effective_from, effective_to
)
SELECT
    tenant_id, customer_id, version_no + 1,
    'SILVER', 'SOUTH',
    TIMESTAMPTZ '2026-06-15 00:00:00+07',
    NULL
FROM closed
RETURNING customer_sk, version_no;

-- Chỉ COMMIT nếu INSERT trả đúng một version như mong đợi.
COMMIT;
~~~

**Quan trọng:** đây là ví dụ của một **chuyển tiếp tiến về phía trước**, không phải thuật toán tổng quát xử lý mọi sự kiện. Ứng dụng hoặc stored procedure phải:

1. Kiểm tra **identity lock** trả đúng khách và dùng cùng giao thức cho mọi writer; nếu chưa tồn tại, phải tạo identity và xử lý tranh chấp khởi tạo.
2. Xác minh nguồn mới hơn hoặc sự kiện được phép, thuộc tính cần đổi thực sự thay đổi và **effective_from mới > effective_from hiện tại**.
3. Kiểm tra **INSERT ... RETURNING trả đúng một hàng** trước khi commit; nếu trả 0, **ROLLBACK/đối chiếu** thay vì báo cập nhật thành công.
4. Xử lý deadlock, constraint violation, retry và sự kiện phát trùng một cách idempotent.
5. Không dùng quy trình này cho **thay đổi hiệu lực hồi tố nằm giữa các phiên bản đã đóng** mà không áp dụng thuật toán tách khoảng riêng.

Việc **UPDATE + INSERT trong cùng transaction** bảo đảm không công bố trạng thái có khoảng trống tạm thời giữa lúc đóng phiên bản cũ và tạo bản mới cho các transaction đọc khác theo quy tắc của PostgreSQL. Khóa identity bảo đảm các writer **tuân thủ cùng giao thức** được serialize theo khách; constraint vẫn là hàng rào bảo vệ khi lập trình sai.

Với thay đổi từ SILVER sang GOLD, áp dụng quy tắc tương tự tại mốc **01/09/2026**, tạo version tiếp theo. Sau đó C-42 có ba hàng như ví dụ ở phần 1.

### 6.3. Khi thuộc tính không đổi, có cần tạo version?

Giả sử nguồn phát **CustomerUpdated** nhưng chỉ thay số điện thoại — trường không nằm trong dimension phân tích. Tạo một version mới với cùng segment/region có thể gây phình dữ liệu và làm số version khó hiểu.

Cần định nghĩa **tracked columns** cho Type 2: ví dụ **segment_code** và **region_code**. Pipeline có thể so các giá trị đã chuẩn hóa hoặc dùng hash của đúng các trường được theo dõi. Chú ý:

- Chuẩn hóa **NULL, chữ hoa/chữ thường, khoảng trắng, mã vùng** theo quy tắc nghiệp vụ.
- Hash chỉ là công cụ phát hiện thay đổi; nếu có rủi ro va chạm hoặc cần độ đúng tuyệt đối, đối chiếu giá trị gốc phù hợp.
- Các field Type 1 phải có đường xử lý riêng; không tạo version vì metadata như **loaded_at** đổi.
- Nếu event có cùng **source revision** nhưng payload khác, coi là xung đột dữ liệu cần điều tra.

## 7. Nối fact với phiên bản dimension tại thời điểm sự kiện

Một fact bán hàng có grain **một đơn đã xác nhận** (đây là ví dụ đơn giản; fact dòng hàng có grain riêng). Bảng có thể tham chiếu version đã xác định:

~~~sql
CREATE TABLE fact_order (
    order_id TEXT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id TEXT NOT NULL,
    customer_sk BIGINT NOT NULL
        REFERENCES dim_customer_version(customer_sk),
    confirmed_at TIMESTAMPTZ NOT NULL,
    order_amount NUMERIC(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_fact_order_customer_sk
    ON fact_order(customer_sk);
~~~

**customer_id** giữ natural ID để truy vết; **customer_sk** gắn fact với **một phiên bản dimension**. Tại lúc nạp fact, pipeline phải tìm phiên bản phù hợp với **confirmed_at**:

~~~sql
SELECT
    d.customer_sk,
    d.version_no,
    d.segment_code,
    d.region_code
FROM dim_customer_version AS d
WHERE d.tenant_id = $1
  AND d.customer_id = $2
  AND d.effective_from <= $3::TIMESTAMPTZ
  AND (
      d.effective_to > $3::TIMESTAMPTZ
      OR d.effective_to IS NULL
  );
~~~

**Hợp đồng truy vấn: trả đúng một hàng** nếu lịch sử có đủ và không chồng lấn. Nếu trả 0: fact đến trước dimension, thiếu lịch sử, sai natural key/tenant hoặc thời điểm ngoài phạm vi. Nếu trả hơn 1: lịch sử dimension đang bị chồng lấn. Không dùng **LIMIT 1** như cách sửa ngầm.

Khi truy vấn doanh thu theo phân khúc tại thời điểm mua:

~~~sql
SELECT
    d.segment_code,
    f.currency,
    COUNT(*) AS order_count,
    SUM(f.order_amount) AS booked_order_amount
FROM fact_order AS f
JOIN dim_customer_version AS d
    ON d.customer_sk = f.customer_sk
GROUP BY d.segment_code, f.currency
ORDER BY d.segment_code, f.currency;
~~~

Đây là **giá trị đơn đã xác nhận**, không mặc định là **tiền đã thu**. Muốn phân tích capture hoặc hoàn tiền, cần nguồn và fact thanh toán có grain riêng. Nhóm theo **currency** để tránh cộng trực tiếp VND với USD.

### 7.1. Vì sao không JOIN theo customer_id và is_current?

~~~sql
-- Sai cho câu hỏi “phân khúc khi mua”:
SELECT
    f.order_id,
    d.segment_code
FROM fact_order AS f
JOIN dim_customer_version AS d
    ON d.tenant_id = f.tenant_id
   AND d.customer_id = f.customer_id
WHERE d.effective_to IS NULL;
~~~

Truy vấn này phân loại **mọi đơn của C-42 thành GOLD** sau 01/09. Nó chỉ có thể đúng cho câu hỏi khác: “Các đơn lịch sử của khách **đang thuộc GOLD** hiện nay là gì?”.

Cần đặt tên rõ cho hai metric:

- **sales_by_segment_at_purchase**: fact nối tới version có hiệu lực lúc sự kiện.
- **historical_sales_by_current_segment**: fact được phân nhóm theo dimension hiện hành; giá trị lịch sử được **tái phân loại theo hiện tại** có chủ đích.

Nếu báo cáo không phân biệt hai ý nghĩa, số liệu có thể thay đổi sau mỗi lần phân khúc cập nhật mà người dùng không hiểu lý do.

### 7.2. Tra theo range có khác việc lưu surrogate key trong fact?

Có hai cách phổ biến:

1. **Xác định customer_sk khi nạp fact** rồi fact JOIN trực tiếp theo surrogate FK. Truy vấn thường rõ ràng và thuận tiện; nhưng khi một thay đổi chiều được nhập **hồi tố**, có thể cần điều chỉnh customer_sk của những fact bị ảnh hưởng.
2. **JOIN động theo natural key + event time** mỗi lần truy vấn. Đỡ phải cập nhật FK trong một số trường hợp, nhưng truy vấn tốn hơn, có nguy cơ nhân hàng nếu lịch sử chồng lấn và cần kiểm soát as-of logic thống nhất.

Nhiều kho phân tích dùng cách 1. Dù cách nào, cần quy định cách xử lý **late-arriving dimension**, **thời gian biên** và **sửa dữ liệu lịch sử**.

## 8. Sự kiện chiều đến muộn và thay đổi hồi tố

Trong thực tế, nguồn không luôn phát thay đổi đúng thứ tự. Một worker có thể nhận sự kiện GOLD trước SILVER; hệ thống vận hành có thể thông báo muộn rằng SILVER đã có hiệu lực từ ngày 15/06.

### 8.1. Phân biệt “đến muộn” với “hiệu lực hồi tố”

- **Late-arriving event:** sự kiện nghiệp vụ xảy ra sớm nhưng hệ thống kho nhận muộn. Mốc hiệu lực của event vẫn là mốc nghiệp vụ đã được xác thực.
- **Retroactive correction:** doanh nghiệp sau đó **sửa lại kiến thức về lịch sử**, ví dụ phát hiện phân khúc đúng từ 10/06 chứ không phải 15/06.
- **Out-of-order arrival:** các event từ cùng thực thể tới consumer sai thứ tự. Cần **source revision/sequence** và chính sách reorder/replay, không tự xếp theo thời điểm nhận.

Không được xử lý cả ba tình huống chỉ bằng “đóng current row, tạo current row mới từ NOW()”. Việc đó có thể làm toàn bộ báo cáo quá khứ sai.

### 8.2. Ví dụ tách khoảng khi phát hiện thay đổi trong quá khứ

Giả sử hiện warehouse ghi:

~~~text
BRONZE: [01/01, 15/06)
SILVER: [15/06, 01/09)
GOLD:   [01/09, +infinity)
~~~

Sau khi được xác minh, nguồn cho biết khách đã lên SILVER từ **10/06**, không phải 15/06. Kết quả đúng theo trục thời gian hiệu lực cần là:

~~~text
BRONZE: [01/01, 10/06)
SILVER: [10/06, 01/09)
GOLD:   [01/09, +infinity)
~~~

Đây là **sửa ranh giới giữa hai phiên bản**, không đơn giản là thêm phiên bản current. Cần khóa natural key, kiểm tra các khoảng liên quan, điều chỉnh theo giao dịch và **xem lại fact có confirmed_at từ 10/06 đến trước 15/06**. Những fact ấy nếu đang tham chiếu BRONZE phải được chuyển sang SILVER (hoặc report dùng as-of join động phản ánh lịch sử mới).

Trong trường hợp nguồn bổ sung một trạng thái **PLATINUM** chỉ có hiệu lực **[10/06, 12/06)**, cần **tách khoảng BRONZE** thành các đoạn trước và sau nếu hợp đồng xác nhận trở về BRONZE; mỗi đoạn có phiên bản/khóa phù hợp. Đơn giản cập nhật **effective_from** trên hàng hiện có mà không xét phần trước/sau có thể làm mất lịch sử.

**Nguyên tắc:** sửa lịch sử phải có mốc, quy tắc, ghi nhận nguồn điều chỉnh và chiến lược cập nhật fact/aggregate đã phát sinh; đừng sửa riêng dimension rồi mặc định mọi fact vẫn được phân loại đúng.

### 8.3. Fact đến trước dimension

Một đơn hàng ngày 18/06 tới pipeline, nhưng bản cập nhật SILVER chưa xuất hiện. Có các lựa chọn:

- **Giữ fact tại staging** và retry trong ngưỡng thời gian xác định.
- Gắn với **unknown/inferred dimension member** có định danh rõ và sau đó **restatement** về đúng customer_sk.
- Nếu nhu cầu cho phép, truy vấn as-of từ nguồn có lịch sử đã xác minh trước khi quyết định phân loại.

Không tự chọn **current GOLD** cho fact ngày 18/06 khi không có bằng chứng. Việc dùng unknown key có thể làm báo cáo tạm thiếu chi tiết nhưng **trung thực hơn** việc điền sai lịch sử. Cần đo số fact chưa giải quyết, tuổi oldest unresolved và độ trễ nạp.

## 9. “Hôm nay ta biết gì” khác “ngày ấy có hiệu lực gì”: giới hạn SCD Type 2

SCD Type 2 phổ biến mô tả **valid time**: một phiên bản có hiệu lực nghiệp vụ trong khoảng nào. **recorded_at** chỉ cho biết một hàng được ghi vào kho lúc nào; một mình nó chưa đủ để tái tạo toàn bộ trạng thái dữ liệu đã được kho tin vào mọi ngày trong quá khứ, đặc biệt khi hàng cũ bị sửa.

Nếu yêu cầu kiểm toán là:

> “Vào ngày 20/06, báo cáo đã trình bày phân khúc của khách tại ngày 10/06 như thế nào, và đến ngày 25/06 doanh nghiệp đã sửa lại hiểu biết đó ra sao?”

...thì cần phân biệt hai trục:

| Trục | Câu hỏi |
| --- | --- |
| **Valid time** | Thuộc tính được xem là có hiệu lực trong nghiệp vụ khi nào? |
| **Recorded/system time** | Phiên bản diễn giải lịch sử này được hệ thống biết/ghi nhận từ lúc nào đến lúc nào? |

Một **mô hình bitemporal** có thể lưu cả **valid_from/valid_to** và **recorded_from/recorded_to**, hoặc lưu sự kiện/sửa đổi dạng append-only đủ để tái dựng các trạng thái đã biết. Đây là bước thiết kế tăng độ phức tạp, không phải yêu cầu bắt buộc cho mọi dimension Type 2.

**Không đồng nhất lịch sử SCD Type 2 với lịch sử chứng từ giao dịch**. Chẳng hạn **order_items.unit_price_at_confirmation** là giá đã chốt của đơn, không được tự đổi khi bảng giá niêm yết/phiên bản danh mục đổi. SCD2 của danh mục giúp phân tích bối cảnh tại thời điểm bán; nó không tự quyết định lại giá giao dịch.

## 10. CDC, ETL và idempotency: tạo version đúng một lần

Một pipeline đưa thay đổi từ nguồn vào **dim_customer_version** thường có các bước:

~~~text
Nguồn có thẩm quyền
   |
   | CDC / outbox / batch có checkpoint
   v
Staging + kiểm tra schema, tenant, natural key
   |
   | Chuẩn hóa tracked attributes, valid time, source revision
   v
Phát hiện thay đổi có ý nghĩa
   |
   | Khóa theo (tenant_id, customer_id)
   v
Đóng/tách khoảng cũ + tạo/sửa version mới
   |
   | Trong cùng ranh giới transaction thích hợp
   v
Đối soát dimension -> ánh xạ/restatement fact nếu cần
   |
   v
Công bố dữ liệu cho báo cáo
~~~

**Idempotency** gồm nhiều lớp:

1. **Nguồn phát lại cùng event ID:** không tạo hai phiên bản giống nhau.
2. **Event cùng natural key nhưng khác source revision:** xử lý theo thứ tự và chính sách hiệu lực; không chọn ngẫu nhiên event đến sau.
3. **Thay đổi trường không theo dõi:** không tạo version Type 2 vô ích.
4. **Sửa hồi tố:** không chỉ overwrite current; phải tái tính các khoảng bị tác động.
5. **Pipeline restart/backfill:** không làm mất hoặc nhân bản version, không khiến fact tham chiếu nhầm customer_sk.

Nên lưu metadata ở staging/control table như **source_event_id**, **source_revision**, checkpoint, trạng thái xử lý và payload fingerprint. Nếu event source được áp dụng ở hai database khác nhau, phải có hợp đồng chống trùng và tái xử lý riêng; **UNIQUE (tenant,customer,version_no)** chưa đủ để chứng minh xử lý mỗi event một lần.

### 10.1. Version của nguồn và version của dimension không phải luôn bằng nhau

Ví dụ nguồn khách có revision 100, 101, 102:

- r100: segment BRONZE, region SOUTH.
- r101: chỉ đổi số điện thoại không theo dõi trong SCD2.
- r102: đổi segment thành SILVER.

Dimension có thể có **v1 = BRONZE**, **v2 = SILVER**. Như vậy **source_revision = 102** có thể tương ứng **version_no = 2**, không phải 102. Nếu pipeline dùng revision để sắp thứ tự, đừng mặc định số thứ tự dimension phải bằng hoặc liên tục với source revision.

### 10.2. Xử lý khách hàng không còn hoạt động

Có hai chính sách hợp lệ nhưng mang nghĩa khác nhau:

- **Đóng phiên bản cuối và không có current row:** sau ngày đóng, phép as-of không tìm thấy phiên bản; phù hợp khi thực thể không còn trong phạm vi cần theo dõi.
- **Tạo phiên bản mới với status = INACTIVE/DELETED:** giữ một phiên bản đại diện trạng thái ngừng hoạt động; báo cáo theo trạng thái và khoảng thời gian có thể dễ hơn.

Không chỉ xóa vật lý các phiên bản lịch sử nếu fact cũ đang tham chiếu chúng. Nhưng cũng không coi SCD2 là lý do giữ vô thời hạn dữ liệu cá nhân: thời hạn lưu, xóa/ẩn và quyền truy cập phải tuân chính sách áp dụng.

## 11. Đối soát SCD Type 2: nhiều hơn kiểm tra current row

Một dimension có thể có đúng một hàng current nhưng vẫn có **gap**, **overlap**, sai mốc hoặc fact trỏ nhầm phiên bản. Vì vậy cần kiểm tra theo từng mức.

### 11.1. Trùng current row

~~~sql
SELECT
    tenant_id, customer_id,
    COUNT(*) AS current_rows
FROM dim_customer_version
WHERE effective_to IS NULL
GROUP BY tenant_id, customer_id
HAVING COUNT(*) > 1;
~~~

Nếu có unique partial index như phần 5, truy vấn phải không có kết quả. Tuy nhiên, **không có current row** cũng có thể là tình trạng bất thường nếu khách vẫn hoạt động và hợp đồng yêu cầu có một current; cần đối chiếu với nguồn/identity để biết đó là lỗi hay khách đã ngừng.

### 11.2. Overlap và khoảng rỗng

Với exclusion constraint, các khoảng trùng/đè lấn sẽ bị từ chối khi ghi. Để đối soát staging hoặc một kho không hỗ trợ exclusion, có thể dùng điều kiện giao nhau của hai khoảng nửa mở:

~~~sql
SELECT
    a.tenant_id,
    a.customer_id,
    a.customer_sk AS version_a,
    b.customer_sk AS version_b
FROM dim_customer_version AS a
JOIN dim_customer_version AS b
  ON b.tenant_id = a.tenant_id
 AND b.customer_id = a.customer_id
 AND b.customer_sk > a.customer_sk
WHERE tstzrange(a.effective_from, a.effective_to, '[)')
      &&
      tstzrange(b.effective_from, b.effective_to, '[)');
~~~

**Khóa chính surrogate** giúp không so một hàng với chính nó, nhưng việc so cặp có thể tốn kém trên lịch sử lớn. Trong vận hành nên chọn phạm vi đối soát, chỉ mục và cơ chế kiểm tra phù hợp.

Kiểm tra khoảng thiếu giữa hai phiên bản liền nhau:

~~~sql
WITH sequenced AS (
    SELECT
        tenant_id,
        customer_id,
        customer_sk,
        effective_from,
        effective_to,
        LEAD(effective_from) OVER (
            PARTITION BY tenant_id, customer_id
            ORDER BY effective_from, customer_sk
        ) AS next_from
    FROM dim_customer_version
)
SELECT *
FROM sequenced
WHERE effective_to IS NOT NULL
  AND next_from IS NOT NULL
  AND effective_to <> next_from;
~~~

Nếu **effective_to < next_from** có **gap**. Nếu **effective_to > next_from** có overlap (dù constraint đã cấm). Khoảng gap **không mặc nhiên là lỗi** nếu khách có thời kỳ không thuộc phạm vi; ngược lại, nếu hợp đồng yêu cầu phủ liên tục thì cần cảnh báo.

### 11.3. Fact có tham chiếu đúng thời điểm không?

Khi fact lưu **customer_sk**, khóa ngoại chỉ chứng minh dimension row **tồn tại**, chưa chứng minh nó **có hiệu lực lúc fact xảy ra**.

~~~sql
SELECT
    f.order_id,
    f.confirmed_at,
    f.customer_sk,
    d.effective_from,
    d.effective_to
FROM fact_order AS f
JOIN dim_customer_version AS d
    ON d.customer_sk = f.customer_sk
WHERE d.tenant_id <> f.tenant_id
   OR d.customer_id <> f.customer_id
   OR f.confirmed_at < d.effective_from
   OR (
       d.effective_to IS NOT NULL
       AND f.confirmed_at >= d.effective_to
   );
~~~

Nếu truy vấn trả hàng, fact đang trỏ tới **sai khách hoặc sai khoảng hiệu lực**. Khi dùng surrogate key, đây là kiểm tra rất quan trọng sau backfill, hồi tố hoặc cập nhật dimension.

Một kiểm tra khác cần tìm fact thiếu dimension, nhưng nếu fact có FK cứng và **NOT NULL** được thực thi thì trường hợp ấy đã được database chặn. Kho phân tích không áp FK vật lý cần tự kiểm tra thêm.

### 11.4. Không đối chiếu lịch sử với thuộc tính hiện hành

Một job phát hiện đơn O-101 có **segment BRONZE**, trong khi hồ sơ khách hàng hiện hành ghi **GOLD**, rồi sửa các fact cũ thành GOLD là dùng sai bất biến. Đúng phải so với **phiên bản dimension có hiệu lực lúc confirmed_at**, theo quy tắc thời gian đã xác định.

Ngoài dữ liệu từng hàng, cần đo **số phiên bản trên mỗi customer**, tỷ lệ gap/overlap, số fact chưa tìm được version, sự kiện bị retry, lag checkpoint, số lần restatement và thời gian xây lại. Một pipeline có thể chạy không lỗi nhưng lịch sử vẫn sai do mốc effective time bị hiểu nhầm.

## 12. SCD Type 2 trong mô hình document, graph và phân tích

Nguyên tắc lưu nhiều phiên bản theo thời điểm không phụ thuộc hoàn toàn vào SQL.

| Mô hình | Cách thể hiện lịch sử chiều | Lợi ích và rủi ro |
| --- | --- | --- |
| **Relational OLTP** | Bảng customer history có version/valid period, FK phù hợp | Ràng buộc và transaction rõ; khi nhiều nguồn ghi cần quản trị quyền |
| **Dimensional warehouse** | **dim_customer_version** có surrogate key, fact trỏ version | Báo cáo “as sold” dễ chạy; cần ETL, SCD matching và restatement |
| **Document** | Collection **customerVersions** với từng document version, hoặc mảng version có giới hạn | Dễ truy xuất một lịch sử khách; mảng dài/phức tạp, unique as-of thường cần logic riêng |
| **Graph** | Đỉnh/cạnh mang valid_from/valid_to hoặc các node trạng thái lịch sử | Truy vấn quan hệ tại thời điểm t; phải tránh đếm cả cạnh cũ và mới |
| **Event log** | Event CustomerSegmentChanged theo ID/time/revision | Có thể dựng dimension; replay cần idempotency, thứ tự và xử lý sửa hồi tố |

Trong **document model**, một khách có thể có nhiều version document, mỗi document mang **customerId**, **effectiveFrom**, **effectiveTo** và thuộc tính. Một truy vấn as-of vẫn phải chọn đúng một document; thiếu ràng buộc giao khoảng có thể tạo hai kết quả. Nhúng toàn bộ lịch sử vào một document không phải mặc nhiên tốt hơn: nó có thể tăng mãi, gây tranh chấp cập nhật và khó index theo thời gian.

Trong **graph**, nếu lưu cả quan hệ **Customer–BELONGS_TO–Segment** cũ và mới, một traversal không lọc valid time có thể trả nhiều segment. SCD2 yêu cầu truy vấn/đường cạnh có mốc hiệu lực rõ, không chỉ tồn tại lịch sử.

Trong **analytics**, SCD2 thường dùng khi tổ chức cần trả lời “doanh số theo phân khúc/vùng tại thời điểm sự kiện”. Nếu chỉ cần phân loại theo trạng thái hiện tại, Type 1 có thể đơn giản và rẻ hơn. Một kiến trúc cũng có thể giữ **bản current** cho thao tác hằng ngày và **versioned dimension** cho báo cáo; hai bản có hợp đồng khác nhau.

## 13. Quy trình triển khai và di trú an toàn

### 13.1. Từ Type 1 sang Type 2

Giả sử kho dữ liệu trước đây chỉ có **dim_customer(customer_id, segment_code)** và muốn bắt đầu lưu lịch sử:

1. **Chốt câu hỏi báo cáo:** phân tích theo segment hiện hành, tại thời điểm mua hay cả hai.
2. **Xác định natural key** có tenant và chính sách tái sử dụng ID.
3. **Liệt kê tracked attributes Type 2**, Type 1 attributes và chính sách privacy.
4. **Đặt quy ước thời gian:** valid time, timezone, mốc cắt chuyển và cách xử lý NULL.
5. **Tạo bảng version** với surrogate key, period constraints, unique current, ghi dấu nguồn.
6. **Nạp version đầu tiên** từ nguồn được xác minh, lưu rõ thời điểm bắt đầu biết lịch sử; không tự bịa segment quá khứ.
7. **Tạo pipeline thay đổi**: idempotent, có checkpoint/replay, lock theo natural key và xử lý hồi tố.
8. **Ánh xạ fact đến customer_sk** theo event time ở phạm vi có đủ lịch sử; đánh dấu unknown/inferred nơi còn thiếu.
9. **Shadow report**: so doanh thu, số fact, phân khúc theo thời điểm, và giải thích sai khác hợp lệ do đổi logic báo cáo.
10. **Chuyển truy vấn có kiểm soát** và giám sát gap, overlap, unmatched facts, lag cùng số liệu tổng.

**Không thể khôi phục chính xác segment ở mọi ngày quá khứ từ một hàng Type 1 hiện hành** nếu không còn dữ liệu lịch sử đáng tin. Backfill bằng giá trị hôm nay và ghi effective_from giả tạo có thể khiến báo cáo trông đủ dữ liệu nhưng sai bản chất.

### 13.2. Đổi quy tắc một tracked attribute

Nếu trước đây **region_code** không tạo version, nay nghiệp vụ cần phân tích doanh thu theo vùng tại ngày bán, có thể phải:

- Xác minh có lịch sử region đầy đủ ở nguồn hay không.
- Thêm region vào danh sách tracked Type 2.
- Quyết định cách đánh dấu những kỳ không xác minh được.
- Tái tạo dimension theo lịch sử có căn cứ, cập nhật customer_sk của fact bị ảnh hưởng và đối soát report.
- Quản lý version của phép biến đổi và tác động đến báo cáo hiện có.

Không nên cập nhật hồi tố mọi version từ region hiện tại rồi gọi đó là lịch sử.

## 14. Chọn thiết kế bằng bằng chứng vận hành

Một dimension Type 2 thường **nhỏ hơn fact** nhưng có thể tăng rất nhanh nếu theo dõi quá nhiều thuộc tính thay đổi thường xuyên. Giả sử một khách có hàng chục thay đổi profile mỗi ngày; nếu cứ tạo version mới cho mọi thay đổi, số hàng và chi phí JOIN có thể tăng mạnh mà không phục vụ báo cáo nào.

### 14.1. Những chỉ số đáng đo

| Chỉ số | Cần biết |
| --- | --- |
| **Version per natural key** | Phân bố số phiên bản/khách, p95/p99 và cực đại |
| **Change events per day** | Lưu lượng, thời điểm cao điểm, tỷ lệ chỉ thay Type 1 fields |
| **SCD load latency** | Từ source commit/valid event tới khi dimension cập nhật |
| **Fact dimension match rate** | Tỷ lệ fact tìm đúng version; số fact pending |
| **Overlap/gap count** | Có interval lỗi/thiếu lịch sử không |
| **Retroactive correction rate** | Bao nhiêu lần tách/sửa khoảng, số fact phải restate |
| **Query p95/p99** | Hiệu năng JOIN theo surrogate key và as-of |
| **Rebuild/restate duration** | Có thể phục hồi và tính lại trong giới hạn yêu cầu không |

### 14.2. Tối ưu vật lý không thay thế mô hình thời gian đúng

- **Index theo (tenant_id, customer_id, effective_from)** giúp tra một khách theo mốc thời gian; cần đo trên phân bố version thực.
- **GiST exclusion constraint** bảo vệ không giao nhau nhưng tăng chi phí ghi/index; cần kiểm tra môi trường triển khai.
- **Partition** có thể giúp dimension rất lớn, nhưng ràng buộc duy nhất/loại trừ xuyên partition phụ thuộc hệ quản trị; không được giả định constraint được bảo vệ toàn cục nếu schema vật lý không hỗ trợ.
- **Fact FK bằng surrogate key** thường giúp báo cáo nhanh hơn JOIN range liên tục; đổi lại phải có quy trình restatement khi lịch sử sửa.
- **Materialized view theo segment** cần rebuild hoặc cập nhật khi sửa lịch sử; chỉ sửa dimension có thể chưa đủ để sửa báo cáo đã tổng hợp.

Một lựa chọn chỉ được xem là phù hợp khi **đúng ngữ nghĩa “as-of”**, có khả năng đối soát và đạt SLO đọc/ghi dưới dữ liệu, thời điểm và tần suất thay đổi đại diện.

## 15. Bài tập tình huống

### Bài 1 — Mốc hiệu lực trùng biên

Khách C-42 có hai version: BRONZE **[01/01, 15/06)** và SILVER **[15/06, 01/09)**. Một đơn được xác nhận đúng **15/06 00:00+07**.

**Câu hỏi:** Đơn thuộc version nào? Vì sao không nên dùng BETWEEN với hai cận đều bao gồm?

### Bài 2 — Surrogate key và natural key

Bảng dimension có **customer_sk** 1001, 1002, 1003 đều ứng với **customer_id = C-42**. Một nhóm muốn UNIQUE(customer_id) vì “khách chỉ có một ID”.

**Câu hỏi:** Ràng buộc ấy có đúng grain không? Cần unique cái gì?

### Bài 3 — Báo cáo thay đổi khi khách nâng hạng

Trong tháng 5 khách ở BRONZE và đã mua 2.000.000 VND. Tháng 9 khách lên GOLD. Báo cáo “doanh số theo phân khúc lúc mua” đột nhiên chuyển toàn bộ 2.000.000 VND của tháng 5 sang GOLD.

**Câu hỏi:** JOIN nào có thể gây lỗi? Viết lại nguyên tắc tra version.

### Bài 4 — Sự kiện đến muộn có hiệu lực hồi tố

Ngày 20/06 hệ thống nhận thông báo: khách thuộc SILVER từ 10/06, nhưng kho đang lưu BRONZE đến 15/06, SILVER từ 15/06. Có các đơn từ 11 đến 14/06.

**Câu hỏi:** Cần sửa những khoảng nào? Điều gì xảy ra với các fact đã gắn customer_sk cũ?

### Bài 5 — Type 1 hay Type 2?

Một quản trị viên sửa lỗi chính tả trong **region_name** từ “Miên Bac” thành “Miền Bắc”, không có thay đổi vùng thực tế. Một khách khác được chuyển quản lý từ miền Bắc sang miền Nam có hiệu lực đầu tháng.

**Câu hỏi:** Hai thay đổi nên theo cùng chính sách lịch sử không? Vì sao?

### Bài 6 — Hai khoảng chồng lấn

Một khách có version A **[01/01, 01/08)** và version B **[01/06, 01/09)**. Cả hai có effective_to khác NULL nên unique current không báo lỗi.

**Câu hỏi:** Lỗi nằm ở đâu và constraint PostgreSQL nào có thể bảo vệ?

### Bài 7 — Ghi lại event không đổi giá trị

Nguồn phát revision 11 với segment SILVER, revision 12 chỉ đổi số điện thoại, revision 13 tiếp tục gửi segment SILVER. Pipeline cứ tạo version mới cho cả ba event.

**Câu hỏi:** Cần phân biệt những trường/metadata nào để không phình dimension?

### Bài 8 — Lịch sử quá khứ không tồn tại

Doanh nghiệp mới bắt đầu thu thập segment từ 01/10; trước đó chỉ có ID khách, không có lịch sử nhóm. Nhóm định gán segment hiện hành của tháng 11 cho mọi đơn trong hai năm trước để báo cáo đầy đủ.

**Câu hỏi:** Phương án có đáng tin không? Nên trình bày dữ liệu thiếu lịch sử thế nào?

### Bài 9 — Hai trục thời gian

Ngày 20/06 kho báo cáo đơn 12/06 thuộc BRONZE. Ngày 25/06 doanh nghiệp phê duyệt sửa hồi tố rằng từ 10/06 khách đã thuộc SILVER. Kiểm toán viên hỏi **báo cáo đã biết gì vào ngày 20/06**.

**Câu hỏi:** Chỉ có effective_from/effective_to của SCD2 đã bị sửa có đủ trả lời không? Cần lưu gì thêm?

### Gợi ý lời giải

1. **SILVER** vì khoảng **[15/06, 01/09)** bao gồm mốc bắt đầu; BRONZE kết thúc tại 15/06 nên không còn hiệu lực. BETWEEN hai cận đóng có thể chọn hai version tại biên.
2. **Không**. Natural key định danh một khách, có thể xuất hiện ở nhiều version. PK là **customer_sk**; có thể dùng UNIQUE(tenant_id, customer_id, version_no), UNIQUE theo effective_from, unique current và constraint chống overlap.
3. JOIN theo **current version** (effective_to IS NULL) đã phân loại lại quá khứ. Cần dùng **customer_sk của fact** đã gắn đúng hoặc JOIN theo customer_id và **confirmed_at nằm trong khoảng hiệu lực**.
4. Đổi BRONZE kết thúc ngày **10/06** và SILVER bắt đầu **10/06**, theo nguồn được xác minh; kiểm tra các khoảng xung quanh. Các fact từ **10/06 đến trước 15/06** nếu đang trỏ BRONZE cần **restatement** tới version đúng hoặc tra as-of động. Cần đối soát aggregate đã tính trước.
5. Sửa lỗi chính tả có thể **Type 1** vì không thay đổi trạng thái nghiệp vụ. Chuyển vùng thực sự nên **Type 2** nếu cần báo cáo theo vùng tại thời điểm bán; hợp đồng theo tracked attributes quyết định.
6. Khoảng chồng nhau **01/06–01/08** tạo hai phiên bản hợp lệ cùng lúc. Dùng **GiST EXCLUDE ... tstzrange(...) WITH &&** theo cùng natural key (có thể cần **btree_gist**) hoặc cơ chế kiểm soát tương đương.
7. Chỉ tạo version mới khi **tracked attributes Type 2** thực sự đổi; tách source_revision/event ID khỏi dimension version, normalize giá trị và xử lý event trùng. Số điện thoại nếu không là tracked field không cần tạo phiên bản.
8. **Không đáng tin**. Không thể suy segment hai năm trước từ giá trị tháng 11 nếu không có chứng cứ. Dùng **unknown/unverified history** theo chính sách, tìm log nguồn/hóa đơn/sự kiện nếu có, công bố giới hạn báo cáo.
9. **Không đủ** nếu sửa lại hàng SCD2 đã làm mất trạng thái hiểu biết cũ. Cần lịch sử **recorded/system time** hoặc event/audit log đủ tái dựng, kết hợp valid time; đây là yêu cầu bitemporal.

## 16. Ghi nhớ

**SCD Type 2 lưu nhiều hàng phiên bản cho cùng một thực thể để bảo toàn thuộc tính chiều theo thời gian hiệu lực.** Grain không còn là “một hàng cho một khách”, mà là **một hàng cho một phiên bản của khách trong một khoảng thời gian**. Natural key liên kết các phiên bản, surrogate key định danh từng version để fact tham chiếu.

Ba bất biến quan trọng là **không chồng lấn khoảng**, **tối đa một phiên bản hiện hành**, và **fact trỏ đúng version có hiệu lực tại thời điểm sự kiện**. Thêm CHECK/UNIQUE thôi chưa đủ cho mọi bất biến; cần ràng buộc khoảng hoặc quy trình kiểm chứng tương ứng.

Khi có dữ liệu đến muộn hoặc sửa hồi tố, **đừng chỉ đóng current và chèn hàng mới bằng thời điểm xử lý**. Hãy xác minh thời điểm nghiệp vụ, điều chỉnh các khoảng bị ảnh hưởng, kiểm tra fact và báo cáo đã phân loại trước đó. Chỉ với hợp đồng thời gian, nguồn gốc và cách phục hồi rõ ràng, SCD Type 2 mới giúp mô hình dữ liệu lịch sử giải thích được và tiến hóa an toàn.
