# Giới hạn phạm vi: mô hình dữ liệu phân tích khác với triển khai toàn bộ luồng ETL

## Mục tiêu học tập và phạm vi

Một báo cáo doanh thu có thể hiển thị đúng tên cột, truy vấn chạy nhanh và vẫn **cho ra số sai** nếu mỗi hàng dữ liệu không có ý nghĩa rõ ràng, cùng một đơn bị đếm nhiều lần, hoặc doanh thu được hiểu khác nhau giữa các nhóm. Vì thế, trước khi xây dựng đường ống dữ liệu, đội ngũ phải xác định **mô hình dữ liệu phân tích** (*analytical data model*): dữ liệu đại diện cho sự kiện nào, được tổng hợp theo chiều nào, chỉ số tính ra sao và ràng buộc gì cần được bảo vệ.

Ngược lại, ngay cả khi sơ đồ fact–dimension rất tốt, dữ liệu vẫn không tự xuất hiện trong kho phân tích. Việc đọc nguồn, đồng bộ thay đổi, xử lý lỗi, lịch chạy, nạp lại lịch sử và theo dõi vận hành thuộc phạm vi **ETL/ELT data pipeline**.

Bài thuộc chương **Mô hình phân tích** trong module **DATABASE_DATA_MODELING**. Mục tiêu của module là rèn kỹ năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ và ràng buộc tới chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời so sánh cách mô hình hóa dữ liệu quan hệ, document, đồ thị và phân tích để lựa chọn cấu trúc dễ tiến hóa và kiểm chứng. Bài này làm rõ **đầu ra của công việc thiết kế mô hình phân tích**, không mở rộng thành hướng dẫn xây dựng toàn bộ hệ thống ETL.

Sau bài học, người học có thể:

1. Phân biệt câu hỏi **“Dữ liệu đích có ý nghĩa và cấu trúc gì?”** với câu hỏi **“Dữ liệu đi từ nguồn tới đích bằng những bước vận hành nào?”**.
2. Xác định **grain** (hạt dữ liệu), **fact**, **dimension**, **measure**, khóa nghiệp vụ/khóa thay thế và các quy tắc thời gian của một mô hình phân tích.
3. Viết **hợp đồng dữ liệu** và các quy tắc chuyển đổi ở mức nghiệp vụ để bàn giao cho nhóm triển khai ETL/ELT mà không nhầm chúng với mã pipeline.
4. Phân định rõ các quyết định về **SCD, dữ liệu đến muộn, hoàn tiền, cập nhật lịch sử, tính mới và chất lượng** giữa mô hình với triển khai.
5. Đọc và đánh giá lược đồ hình sao cùng SQL báo cáo minh họa mà không cần cài đặt ingestion, scheduler hay hệ thống giám sát.
6. Xác định tiêu chí nghiệm thu cho phần **mô hình** và bàn giao phần **vận hành pipeline** cho bước triển khai riêng.

> **Giới hạn có chủ đích:** Bài sử dụng PostgreSQL và SQL minh họa để làm rõ lược đồ đích, phép JOIN và các giả định về chỉ số. Bài **không** viết connector lấy dữ liệu, job streaming/batch, DAG điều phối, logic retry/backfill hay cấu hình triển khai. Những việc đó quan trọng, nhưng là một phạm vi thực hiện khác.

## 1. Hai câu hỏi khác nhau nhưng liên quan chặt chẽ

### 1.1. Mô hình dữ liệu phân tích trả lời “lưu gì và hiểu như thế nào?”

**Mô hình dữ liệu phân tích** là tập các quyết định về cấu trúc và ngữ nghĩa của dữ liệu dùng để phân tích, ví dụ:

- Một hàng trong **fact_sales_line** là **một dòng đơn hàng đã ghi nhận bán** hay một lần thay đổi trạng thái đơn?
- **Doanh thu thuần** có bằng doanh thu gộp trừ chiết khấu không? Đã trừ hoàn trả hay chưa?
- Có thể cộng số lượng, số tiền theo ngày, sản phẩm và nhóm khách hàng không?
- Khách hàng được phân theo **nhóm tại thời điểm mua** hay nhóm **hiện tại**?
- Một khách hàng có thể có nhiều phiên bản trong dimension không? Phiên bản nào gắn với giao dịch lịch sử?
- Dùng khóa nào để một dòng giao dịch chỉ xuất hiện một lần trong tập fact?
- Những giả định nào được hệ thống dữ liệu bảo vệ bằng PK, FK, UNIQUE, CHECK hay phép kiểm tra chất lượng?

Các quyết định này tạo ra **hợp đồng ngữ nghĩa** cho người viết báo cáo, nhà phân tích, ứng dụng và nhóm ETL.

### 1.2. Triển khai ETL/ELT trả lời “dữ liệu tới đó bằng cách nào?”

**ETL** là *Extract–Transform–Load*: trích xuất, biến đổi rồi nạp dữ liệu. **ELT** là *Extract–Load–Transform*: tải dữ liệu gốc vào môi trường đích rồi thực hiện biến đổi tại đó. Cả hai đều là cách tổ chức **luồng xử lý dữ liệu**, không phải định nghĩa hạt fact hay chỉ số nghiệp vụ.

Triển khai ETL/ELT thường phải giải quyết:

- Kết nối database nghiệp vụ, API, file hoặc sự kiện.
- Chọn cơ chế full load, incremental load, CDC hoặc streaming.
- Chuẩn hóa định dạng, xử lý lỗi dữ liệu nguồn và chuyển đổi.
- Tra cứu khóa dimension, xử lý dữ liệu đến trễ, trùng lặp, xóa/sửa.
- Lập lịch, phụ thuộc job, retry, idempotency, backfill.
- Quản lý bí mật kết nối, hạ tầng, quyền, tài nguyên và chi phí.
- Theo dõi độ trễ, số bản ghi, lỗi pipeline, cảnh báo và phục hồi.

Những bước này phải **tuân theo mô hình đích**, nhưng không phải bản thân mô hình đích.

### 1.3. Ranh giới ngắn gọn

| Câu hỏi | Mô hình phân tích | Triển khai ETL/ELT |
| --- | --- | --- |
| Một hàng fact là gì? | **Định nghĩa grain** | Nạp dữ liệu đúng grain đã chốt |
| Doanh thu thuần nghĩa là gì? | **Công thức và phạm vi nghiệp vụ** | Tính hoặc nhận giá trị, kiểm chứng công thức |
| Khách hàng thay đổi nhóm ra sao? | **Chọn SCD1, SCD2 hoặc cách nhìn khác** | Tìm thay đổi, đóng/mở phiên bản và gán khóa |
| Một giao dịch bị gửi lại hai lần thì sao? | **Quy tắc duy nhất theo khóa sự kiện** | Cơ chế dedup, upsert và replay an toàn |
| Báo cáo cần mới trong 30 phút? | **Đặt freshness SLA/SLO mong muốn** | Chọn lịch, streaming, cảnh báo và xử lý quá hạn |
| Một sản phẩm không có dimension tương ứng? | **Quy định trạng thái thiếu tham chiếu** | Hàng đợi, bản ghi unknown, tải lại và đối soát |
| Cần đọc dữ liệu từ hệ thống nào? | **Xác định nguồn có thẩm quyền và mapping khái niệm** | Cấu hình connector, xác thực, retry, incremental |
| Bảng đích có cột nào? | **Lược đồ logic/đích, khóa, ràng buộc** | Tạo, di trú và nạp bảng trong môi trường thực tế |
| Job thất bại lúc 02:00? | **Không phải quyết định cấu trúc mô hình** | Điều tra log, retry, phục hồi và cảnh báo |

**Không phải hai công việc hoàn toàn tách biệt.** Chẳng hạn grain và cách xử lý phiên bản quyết định cách nạp; ngược lại, giới hạn của nguồn và yêu cầu cập nhật có thể buộc thiết kế mô hình điều chỉnh. Điều quan trọng là **nêu đúng ai quyết định gì, sản phẩm bàn giao nào được kiểm chứng và phạm vi nào chưa được triển khai**.

## 2. Các khái niệm cơ sở để thiết kế dữ liệu phân tích

### 2.1. Nguồn OLTP khác mô hình phục vụ phân tích

Hệ thống vận hành (**OLTP**) thường ưu tiên ghi giao dịch đúng và tránh bất thường cập nhật. Ví dụ các bảng **orders**, **order_lines**, **customers**, **products** có quan hệ khóa ngoại, trạng thái và nghiệp vụ thay đổi từng thời điểm.

Hệ thống phân tích (**OLAP** hoặc kho phân tích) thường ưu tiên câu hỏi:

- Tổng doanh thu thuần theo **ngày bán** và **nhóm khách** là bao nhiêu?
- Sản phẩm nào có doanh số cao nhất trong quý?
- Tỷ lệ hoàn trả theo danh mục và tháng phát sinh ra sao?
- Kết quả phân tích có thể tái lập theo cùng **định nghĩa chỉ số** hay không?

Không nên sao chép nguyên lược đồ OLTP rồi gọi đó là mô hình phân tích. Bảng nguồn trả lời “hệ thống vận hành đang lưu gì”, còn mô hình phân tích trả lời “người dùng cần đánh giá sự kiện/chỉ số nào ở độ hạt nào”.

### 2.2. Grain: định nghĩa trước khi chọn cột

**Grain** là ý nghĩa của **chính xác một hàng** trong một fact. Ví dụ:

> Mỗi hàng trong fact_sales_line biểu diễn **một dòng đơn hàng được ghi nhận là giao dịch bán hợp lệ, sau khi đơn đạt trạng thái hoàn tất theo quy tắc kinh doanh**; khóa nghiệp vụ của hàng là order_line_id.

Grain này **khác**:

- Một hàng trên mỗi **đơn hàng**.
- Một hàng trên mỗi **lần thay đổi trạng thái dòng đơn**.
- Một hàng trên mỗi **lô giao hàng**.
- Một hàng trên mỗi **ngày–sản phẩm** sau tổng hợp.

Nếu trộn các grain khác nhau vào cùng một fact mà không có quy tắc rõ ràng, truy vấn SUM hay COUNT rất dễ đếm trùng.

### 2.3. Fact, dimension và measure

- **Fact table** lưu sự kiện, khóa liên kết dimension và **measure** có thể đo/tổng hợp. Ví dụ quantity, gross_amount, discount_amount.
- **Dimension table** cung cấp ngữ cảnh để nhóm và lọc. Ví dụ ngày, sản phẩm, khách hàng, khu vực.
- **Measure** là lượng đo hoặc chỉ số có định nghĩa rõ: số lượng, doanh thu gộp, chiết khấu, doanh thu thuần.
- **Dimension attribute** như customer_segment hoặc product_name là thuộc tính phân tích, không nên cộng SUM.

Một mô hình **hình sao (star schema)** thường đặt fact ở trung tâm, liên kết đến các dimension. Đây là một phương án rất phổ biến, nhưng không phải mọi mô hình phân tích đều bắt buộc hình sao: bảng rộng, mô hình dữ liệu ngữ nghĩa/semantic layer, data vault, cube hoặc các dạng tổng hợp có thể phù hợp ở bối cảnh khác.

### 2.4. Độ cộng được của measure

| Loại measure | Ví dụ | Cách tổng hợp |
| --- | --- | --- |
| **Additive** | Số tiền bán của từng dòng, số lượng bán | Có thể SUM qua các chiều không làm nhân bản fact |
| **Semi-additive** | Số dư cuối ngày, tồn kho cuối ngày | Có thể cộng theo một số chiều, **không cộng số dư qua nhiều thời điểm** như doanh thu |
| **Non-additive** | Tỷ lệ chuyển đổi, biên lợi nhuận %, giá bán trung bình | Phải tính lại từ tử số/mẫu số hoặc quy tắc phù hợp, không SUM trực tiếp |

Ví dụ tỷ lệ hoàn trả:

\[
\text{Tỷ lệ hoàn trả}
=\frac{\text{Số lượng hoàn trả}}{\text{Số lượng bán hợp lệ}}
\]

Phải quy định cùng cửa sổ thời gian, loại sản phẩm, đơn vị đo và cách xử lý mẫu số bằng 0. **Không** cộng hoặc lấy trung bình đơn giản các tỷ lệ của từng dòng để có tỷ lệ toàn hệ thống.

## 3. Ví dụ xuyên suốt: mô hình phân tích doanh số bán hàng

Ta giả định một doanh nghiệp có hệ thống đơn hàng giao dịch. Nhu cầu báo cáo:

1. Doanh thu thuần theo ngày, sản phẩm và phân khúc khách.
2. Đếm số dòng bán, tổng số lượng và tổng tiền của những đơn đã hoàn tất.
3. Khi khách đổi phân khúc, báo cáo lịch sử vẫn dùng **phân khúc tại thời điểm bán**.
4. Đơn hoàn trả và phần hoàn trả sẽ được theo dõi **riêng**; không tự cộng số tiền hoàn trả vào fact bán hàng trong ví dụ.
5. Đơn vị tiền là **VND**; mọi measure tiền trong fact này cùng đơn vị.

Đây là **giả định minh họa**. Nếu doanh nghiệp dùng nhiều tiền tệ, nhiều đợt giao, giá trị thuế, đơn hủy sau hoàn tất hoặc quy tắc ghi nhận doanh thu khác, phải làm rõ trước khi dùng mô hình vào sản xuất.

### 3.1. Bắt đầu bằng câu hỏi và định nghĩa, không bằng tool

| Quyết định mô hình | Giả định đã chốt trong ví dụ |
| --- | --- |
| Sự kiện | Một dòng đơn **được ghi nhận bán** khi đơn đạt trạng thái hoàn tất hợp lệ |
| Grain | Một hàng trên một **order_line_id** nghiệp vụ |
| Thời điểm phân tích | sold_at của sự kiện bán hợp lệ, quy đổi sang **ngày tại Asia/Ho_Chi_Minh** |
| Số lượng | quantity > 0, đo theo **đơn vị bán** của từng sản phẩm |
| Doanh thu gộp | gross_amount, đơn vị VND |
| Chiết khấu | discount_amount, đơn vị VND, từ 0 đến gross_amount |
| Doanh thu thuần bán hàng | net_amount = gross_amount - discount_amount; **chưa trừ hoàn trả**, chưa tự suy ra thuế/phí |
| Khách hàng | Dimension có phiên bản theo thời gian để giữ **phân khúc tại thời điểm bán** |
| Sản phẩm | Dimension chứa thuộc tính sản phẩm phục vụ phân nhóm; chính sách thay đổi danh mục cần quyết định riêng |
| Khóa chống trùng | order_line_id phải duy nhất trong fact tại grain đã nêu |
| Đích báo cáo | Một fact chi tiết và các dimension phục vụ GROUP BY/WHERE |

**Lưu ý về “doanh thu”:** Trong ví dụ này net_amount là **doanh thu thuần ở mức dòng bán sau chiết khấu**, không mặc nhiên bằng doanh thu kế toán đã công nhận theo chuẩn mực, cũng không phải doanh thu sau hoàn tiền. Tên measure phải đủ rõ để không đồng nhất những khái niệm khác nhau.

### 3.2. Sơ đồ hình sao mức khái niệm

~~~~mermaid
erDiagram
    DIM_DATE ||--o{ FACT_SALES_LINE : ngay_ban
    DIM_CUSTOMER ||--o{ FACT_SALES_LINE : khach_tai_thoi_diem_ban
    DIM_PRODUCT ||--o{ FACT_SALES_LINE : san_pham

    DIM_DATE {
        integer date_key PK
        date full_date
        smallint calendar_year
        smallint calendar_month
    }
    DIM_CUSTOMER {
        bigint customer_key PK
        varchar customer_id
        varchar customer_segment
        timestamptz effective_from
        timestamptz effective_to
        boolean is_current
    }
    DIM_PRODUCT {
        bigint product_key PK
        varchar product_id
        varchar product_name
    }
    FACT_SALES_LINE {
        bigint sales_line_key PK
        varchar order_line_id UK
        varchar order_id
        integer date_key FK
        bigint customer_key FK
        bigint product_key FK
        timestamptz sold_at
        integer quantity
        decimal gross_amount
        decimal discount_amount
        decimal net_amount
    }
~~~~

**Giải thích khóa:**

- **sales_line_key** là khóa thay thế (*surrogate key*) của hàng fact; **order_line_id** là khóa nghiệp vụ duy nhất của sự kiện.
- **customer_key** trỏ tới **một phiên bản cụ thể** của khách hàng ở dimension, không chỉ trỏ customer_id hiện tại.
- **product_key** và **date_key** tham chiếu dimension tương ứng.
- **order_id** nằm ngay trong fact để tra cứu hoặc đếm đơn, có thể được xem là **degenerate dimension** khi không cần một bảng dimension đơn hàng riêng cho báo cáo này.
- Ràng buộc FK bảo đảm tham chiếu tồn tại nhưng **không tự bảo đảm customer_key là phiên bản hiệu lực tại sold_at**; đây là một quy tắc dữ liệu thời gian cần kiểm chứng thêm.

### 3.3. Tại sao không làm một fact trên mỗi đơn?

Giả sử đơn O100 có hai sản phẩm. Nếu lưu một hàng trên mỗi đơn với total_amount và đồng thời nối với danh sách sản phẩm, truy vấn tổng doanh thu theo sản phẩm có thể **lặp lại toàn bộ tổng đơn** cho từng sản phẩm.

Thay vì thế:

| order_id | order_line_id | product_id | quantity | net_amount |
| --- | --- | --- | ---: | ---: |
| O100 | O100-L1 | P01 | 2 | 90000 |
| O100 | O100-L2 | P02 | 1 | 20000 |

Doanh thu đơn O100 là **110000**, được tính bằng SUM net_amount của hai dòng. Nếu một fact khác có grain **một hàng mỗi đơn** để phục vụ KPI cấp đơn, hai fact phải được dùng đúng ngữ cảnh; không JOIN trực tiếp hai fact chi tiết rồi SUM bừa bãi.

### 3.4. Một bản ghi dimension có thể đại diện cho một phiên bản

Khách C001 đổi từ **Retail** sang **Enterprise** vào đầu ngày 02/10/2026 theo giờ Việt Nam. Nếu yêu cầu là phân khúc tại thời điểm bán, việc cập nhật trực tiếp customer_segment trên một hàng duy nhất sẽ khiến các giao dịch ngày 01/10 bị gán ngược thành Enterprise.

Một mô hình **SCD Type 2** (*Slowly Changing Dimension*) có thể lưu:

| customer_key | customer_id | customer_segment | effective_from (giờ +07) | effective_to (giờ +07) |
| ---: | --- | --- | --- | --- |
| 101 | C001 | Retail | 2026-01-01 00:00 | 2026-10-02 00:00 |
| 102 | C001 | Enterprise | 2026-10-02 00:00 | Không có (hiện hành) |
| 103 | C002 | Retail | 2026-01-01 00:00 | Không có (hiện hành) |

Giao dịch ngày 01/10 của C001 tham chiếu **customer_key = 101**, còn giao dịch ngày 02/10 tham chiếu **customer_key = 102**. Chính sách chọn SCD2 là **quyết định mô hình**; cách phát hiện thay đổi, tạo phiên bản, xử lý backfill và nạp đúng khóa là **công việc của luồng dữ liệu**.

## 4. Lược đồ đích và SQL minh họa: thiết kế, chưa phải ETL

Đoạn DDL sau thể hiện **một khả năng triển khai cấu trúc đích trên PostgreSQL**. Nó minh họa rõ grain, khóa và một số bất biến; nó **không lấy dữ liệu từ nguồn**, không xây dựng job tự động và không bảo đảm toàn bộ chất lượng dữ liệu chỉ bằng DDL.

### 4.1. Tạo các dimension

~~~~sql
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    calendar_year SMALLINT NOT NULL,
    calendar_month SMALLINT NOT NULL,
    CONSTRAINT ck_date_month CHECK (calendar_month BETWEEN 1 AND 12)
);

CREATE TABLE dim_customer (
    customer_key BIGINT PRIMARY KEY,
    customer_id VARCHAR(40) NOT NULL,
    customer_segment VARCHAR(40) NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL,
    CONSTRAINT uq_customer_version
        UNIQUE (customer_id, effective_from),
    CONSTRAINT ck_customer_interval
        CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ck_customer_current
        CHECK (
            (is_current = TRUE AND effective_to IS NULL)
            OR
            (is_current = FALSE AND effective_to IS NOT NULL)
        )
);

-- Chỉ được có một phiên bản hiện hành cho mỗi customer_id.
CREATE UNIQUE INDEX uq_customer_one_current
    ON dim_customer (customer_id)
    WHERE is_current = TRUE;

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,
    product_id VARCHAR(40) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL,
    product_category VARCHAR(80) NOT NULL
);
~~~~

**Quyết định mô hình quan trọng:**

- **dim_customer** dùng khóa thay thế customer_key để phân biệt các **phiên bản của cùng customer_id**. Cặp (customer_id, effective_from) phải duy nhất.
- Khoảng hiệu lực SCD2 được hiểu là **[effective_from, effective_to)**: bao gồm thời điểm bắt đầu, **không** bao gồm thời điểm kết thúc; effective_to NULL nghĩa là chưa biết thời điểm hết hiệu lực.
- Chỉ mục UNIQUE có điều kiện chặn **hai phiên bản cùng is_current = TRUE** của một customer_id.
- Các CHECK trên chưa ngăn **hai phiên bản đã đóng có khoảng hiệu lực chồng lấn**. Quy tắc không chồng lấn cần cơ chế kiểm tra dữ liệu/constraint bổ sung thích hợp.
- **dim_product** ở ví dụ dùng một hàng trên mỗi product_id, tương tự chính sách cập nhật thuộc tính hiện tại (*Type 1*) cho product_name/category. Nếu cần danh mục sản phẩm **tại thời điểm bán**, phải thay đổi chính sách dimension tương ứng, không tự coi thông tin hiện tại là lịch sử.

Trong thực tế, nhiều kho phân tích dùng khóa dimension được sinh tự động và các cột bổ sung như nguồn dữ liệu, timestamp nạp, phiên bản hệ thống. Ở đây customer_key/product_key được cung cấp tường minh để ví dụ dễ kiểm tra; **cơ chế sinh khóa và ánh xạ ID nguồn** nằm ngoài phạm vi triển khai của bài.

### 4.2. Tạo fact ở mức dòng bán

~~~~sql
CREATE TABLE fact_sales_line (
    sales_line_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_line_id VARCHAR(40) NOT NULL UNIQUE,
    order_id VARCHAR(40) NOT NULL,
    date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    customer_key BIGINT NOT NULL
        REFERENCES dim_customer(customer_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    sold_at TIMESTAMPTZ NOT NULL,
    quantity INTEGER NOT NULL,
    gross_amount NUMERIC(18, 2) NOT NULL,
    discount_amount NUMERIC(18, 2) NOT NULL,
    net_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (gross_amount - discount_amount) STORED,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND',
    CONSTRAINT ck_sales_qty CHECK (quantity > 0),
    CONSTRAINT ck_sales_gross CHECK (gross_amount >= 0),
    CONSTRAINT ck_sales_discount
        CHECK (discount_amount >= 0 AND discount_amount <= gross_amount),
    CONSTRAINT ck_sales_currency CHECK (currency_code = 'VND')
);
~~~~

**Các điều được DDL bảo đảm:**

- order_line_id chỉ xuất hiện **tối đa một lần** trong fact, tương ứng grain đã định nghĩa.
- Các khóa dimension phải tham chiếu bản ghi dimension đang tồn tại.
- Quantity và các measure cơ bản có miền giá trị hợp lệ.
- net_amount được tính nhất quán từ gross_amount và discount_amount **trong chính một hàng**.
- Tiền ở fact này chỉ có mã VND, không cộng nhầm hai loại tiền.

**Những điều DDL chưa bảo đảm:**

- Dòng nguồn đã thực sự đạt điều kiện “bán hợp lệ/hoàn tất”.
- sold_at được chuyển sang đúng date_key theo múi giờ đã chốt.
- customer_key là phiên bản SCD2 có khoảng hiệu lực chứa sold_at.
- order_line_id từ nguồn thật sự đại diện cho một sự kiện bán duy nhất, kể cả khi hệ thống nguồn gửi lại bản tin hoặc đổi trạng thái.
- Nguồn dữ liệu đã đủ, không thiếu giao dịch, không dư dòng và được làm mới trong thời hạn mong muốn.

Các mục này cần **hợp đồng ngữ nghĩa và phép kiểm tra/triển khai của luồng dữ liệu**, không phải lời hứa rằng một câu CREATE TABLE sẽ tự giải quyết mọi vấn đề.

### 4.3. Nạp dữ liệu thử nghiệm đã biết trước

Những INSERT dưới đây chỉ **tạo một bộ dữ liệu minh họa** để kiểm tra mô hình và truy vấn. Chúng **không phải chương trình ETL** trích xuất từ hệ thống đặt hàng.

~~~~sql
INSERT INTO dim_date
    (date_key, full_date, calendar_year, calendar_month)
VALUES
    (20261001, DATE '2026-10-01', 2026, 10),
    (20261002, DATE '2026-10-02', 2026, 10);

INSERT INTO dim_customer
    (customer_key, customer_id, customer_segment,
     effective_from, effective_to, is_current)
VALUES
    (101, 'C001', 'Retail',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     TIMESTAMPTZ '2026-10-02 00:00:00+07', FALSE),
    (102, 'C001', 'Enterprise',
     TIMESTAMPTZ '2026-10-02 00:00:00+07',
     NULL, TRUE),
    (103, 'C002', 'Retail',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     NULL, TRUE);

INSERT INTO dim_product
    (product_key, product_id, product_name, product_category)
VALUES
    (201, 'P01', 'Sổ tay', 'Văn phòng phẩm'),
    (202, 'P02', 'Bút viết', 'Văn phòng phẩm');

INSERT INTO fact_sales_line
    (order_line_id, order_id, date_key, customer_key, product_key,
     sold_at, quantity, gross_amount, discount_amount)
VALUES
    ('O100-L1', 'O100', 20261001, 101, 201,
     TIMESTAMPTZ '2026-10-01 09:00:00+07', 2, 100000, 10000),
    ('O100-L2', 'O100', 20261001, 101, 202,
     TIMESTAMPTZ '2026-10-01 09:00:00+07', 1, 20000, 0),
    ('O101-L1', 'O101', 20261002, 102, 201,
     TIMESTAMPTZ '2026-10-02 10:00:00+07', 1, 50000, 5000),
    ('O102-L1', 'O102', 20261002, 103, 202,
     TIMESTAMPTZ '2026-10-02 12:00:00+07', 3, 60000, 0);
~~~~

Dữ liệu mô tả ba đơn O100, O101, O102 và bốn dòng bán. Trong đó O100 có hai dòng; O101 thuộc C001 sau khi khách chuyển phân khúc sang Enterprise; O102 thuộc C002.

### 4.4. Truy vấn báo cáo từ mô hình

**Báo cáo doanh thu thuần và số lượng theo ngày–phân khúc:**

~~~~sql
SELECT
    d.full_date,
    c.customer_segment,
    SUM(f.quantity) AS units_sold,
    SUM(f.net_amount) AS net_sales_vnd
FROM fact_sales_line AS f
JOIN dim_date AS d ON d.date_key = f.date_key
JOIN dim_customer AS c ON c.customer_key = f.customer_key
GROUP BY d.full_date, c.customer_segment
ORDER BY d.full_date, c.customer_segment;
~~~~

Kết quả tính theo dữ liệu mẫu:

| full_date | customer_segment | units_sold | net_sales_vnd |
| --- | --- | ---: | ---: |
| 2026-10-01 | Retail | 3 | 110000 |
| 2026-10-02 | Enterprise | 1 | 45000 |
| 2026-10-02 | Retail | 3 | 60000 |

**Tổng doanh thu thuần bán hàng:** 110000 + 45000 + 60000 = **215000 VND**. Tổng số lượng bán = **7 đơn vị** theo giả định đơn vị bán có thể cộng ở phạm vi ví dụ; nếu các sản phẩm dùng đơn vị đo không tương thích, cần chỉ số hoặc cách quy đổi khác trước khi tổng hợp.

**Đếm số đơn và số dòng bán:**

~~~~sql
SELECT
    COUNT(*) AS sale_lines,
    COUNT(DISTINCT order_id) AS orders,
    SUM(net_amount) AS net_sales_vnd
FROM fact_sales_line;
-- sale_lines = 4, orders = 3, net_sales_vnd = 215000
~~~~

**Tính tỷ trọng phân khúc theo công thức đúng:**

~~~~sql
WITH revenue_by_segment AS (
    SELECT c.customer_segment, SUM(f.net_amount) AS sales_vnd
    FROM fact_sales_line AS f
    JOIN dim_customer AS c ON c.customer_key = f.customer_key
    GROUP BY c.customer_segment
)
SELECT customer_segment,
       sales_vnd,
       ROUND(
           100 * sales_vnd / NULLIF(SUM(sales_vnd) OVER (), 0),
           2
       ) AS share_percent
FROM revenue_by_segment
ORDER BY customer_segment;
~~~~

Phân khúc Retail có **170000 VND** (khoảng **79,07%**) và Enterprise có **45000 VND** (khoảng **20,93%**). Không cộng hoặc lấy trung bình đơn giản tỷ lệ của từng dòng để có tỷ trọng chung; phải tính dựa trên **tổng doanh thu theo phân khúc chia cho tổng doanh thu của cùng tập dữ liệu**.

### 4.5. Vì sao truy vấn chứng minh được hợp đồng mô hình nhưng chưa chứng minh pipeline?

Những câu SELECT trên giúp kiểm tra:

- Chúng ta đã xác định đúng **ngữ nghĩa của grain và measure** trong dữ liệu thử hay chưa.
- Một cặp fact–dimension có được JOIN bằng khóa đã định không.
- Quy tắc phân khúc lịch sử có xuất hiện trong kết quả theo thời điểm bán không.

Nhưng chúng **không** chứng minh rằng hệ thống nguồn đã được kết nối, dữ liệu ngày mai sẽ tự đến, job chạy đúng hạn, bản tin trùng được loại, hoặc khi CDC thất bại thì job sẽ hồi phục. Muốn khẳng định các điều đó phải có **triển khai và kiểm thử pipeline** ở một hạng mục riêng.

## 5. SCD, dữ liệu đến muộn và thay đổi lịch sử: quyết định mô hình trước, thuật toán nạp sau

Một trong những chỗ dễ lẫn nhất giữa thiết kế phân tích và ETL là xử lý **dữ liệu thay đổi theo thời gian**. Mô hình phải nói rõ **lịch sử được diễn giải thế nào**; pipeline phải thực hiện việc cập nhật dữ liệu đúng theo chính sách ấy.

### 5.1. SCD Type 1 và Type 2 giải quyết hai câu hỏi khác nhau

| Vấn đề | SCD Type 1 | SCD Type 2 |
| --- | --- | --- |
| Cách nhìn | Giá trị **hiện tại** hoặc giá trị được sửa cuối cùng | Giá trị **đã có hiệu lực trong từng thời kỳ** |
| Thay đổi thuộc tính | Cập nhật tại chỗ trong một hàng | Tạo phiên bản mới, đóng phiên bản cũ |
| Biến đổi báo cáo lịch sử | Có thể đổi khi thuộc tính hiện tại đổi | Có thể giữ cách phân nhóm lịch sử theo thời điểm sự kiện |
| Khóa dimension | Thường một hàng cho mỗi business key | Nhiều surrogate key cho một business key |
| Phù hợp | Sửa lỗi chính tả, thuộc tính không cần lịch sử | Phân khúc, khu vực, cấp hạng cần phân tích theo thời điểm |
| Đánh đổi | Đơn giản hơn, ít phiên bản | Nhiều hàng hơn, cần gán phiên bản đúng và kiểm tra hiệu lực |

**Quyết định mô hình:** customer_segment cần đúng **tại thời điểm giao dịch**, nên dùng SCD2 trong ví dụ. Đây là lời cam kết về ý nghĩa dữ liệu.

**Quyết định triển khai ETL:** làm thế nào phát hiện thay đổi từ hệ thống nguồn, đóng phiên bản cũ, tạo customer_key mới, cập nhật dòng đến muộn và tránh hai job tạo cùng phiên bản. Đó là thiết kế luồng dữ liệu, không được suy ra tự động chỉ từ tên SCD2.

### 5.2. Thời gian xảy ra sự kiện khác thời gian xử lý

Phải phân biệt ít nhất:

- **Event time:** thời điểm sự kiện kinh doanh thực sự xảy ra, ví dụ sold_at.
- **Processing/ingestion time:** thời điểm hệ thống phân tích nhận hoặc xử lý bản tin.
- **Dimension effective time:** thời gian một phiên bản dimension có hiệu lực theo chính sách nghiệp vụ.

Ví dụ giao dịch bán xảy ra lúc **21:00 ngày 01/10**, nhưng hệ thống nguồn gửi dữ liệu tới kho vào **03:00 ngày 02/10**. Nếu báo cáo theo ngày bán, dòng này vẫn thuộc **01/10**, không tự chuyển sang 02/10 chỉ vì được nạp muộn.

Nếu customer_segment đổi lúc **00:00 ngày 02/10**, giao dịch ngày 01/10 phải gắn với phiên bản Retail, kể cả khi ETL chạy sau khi segment đã đổi. Vì vậy mô hình phải có **sold_at** và khoảng hiệu lực của customer dimension; pipeline sẽ thực hiện phép **as-of lookup** dựa trên thời điểm.

Điều kiện logic để gán phiên bản là:

\[
customer\_id_{\mathrm{fact}}=customer\_id_{\mathrm{dim}}
\]

và

\[
effective\_from\le sold\_at < effective\_to
\]

hoặc **effective_to chưa có giá trị** cho phiên bản hiện hành.

Một truy vấn phân tích minh họa điều kiện tra cứu phiên bản (không phải toàn bộ thuật toán nạp):

~~~~sql
-- Giả sử có một nguồn sự kiện đã được xác thực và có customer_id/sold_at.
-- Truy vấn này chỉ minh họa quy tắc nối theo thời gian.
SELECT d.customer_key
FROM dim_customer AS d
WHERE d.customer_id = 'C001'
  AND d.effective_from <= TIMESTAMPTZ '2026-10-01 09:00:00+07'
  AND (
      d.effective_to > TIMESTAMPTZ '2026-10-01 09:00:00+07'
      OR d.effective_to IS NULL
  );
-- Kết quả mong đợi: 101.
~~~~

Nếu dữ liệu nguồn chỉ có ngày mà không có thời điểm đủ chính xác, phải quyết định quy tắc gán phiên bản theo độ phân giải hiện có; không thể suy ra lịch sử chính xác hơn chất lượng timestamp của nguồn.

### 5.3. Dữ liệu đến muộn (*late-arriving data*)

Có hai tình huống cần tách:

**Fact đến muộn:** Đơn được bán hôm qua nhưng sự kiện hôm nay mới được nhận. Mô hình phải giữ **ngày bán**, khóa nghiệp vụ và phiên bản khách đúng thời điểm bán; ETL phải quyết định cách nạp bù và làm mới các báo cáo liên quan.

**Dimension đến muộn:** Fact đã tới nhưng thuộc tính/sự tồn tại của khách hoặc sản phẩm chưa được đồng bộ. Mô hình phải xác định cách thể hiện sự thiếu hụt:

- **Quarantine/chưa công bố fact** cho đến khi giải quyết được tham chiếu.
- **Unknown member** có khóa được dành riêng, kèm cờ/thuộc tính thể hiện chưa xác định.
- Một cơ chế bổ sung dữ liệu suy luận tạm thời (*inferred member*), sau đó hoàn thiện khi có nguồn đáng tin.

Đây là **các phương án cần quyết định trước**. Dùng unknown member có thể giúp báo cáo vẫn đủ tổng nhưng làm xuất hiện nhóm “Chưa xác định”; nó không tự tốt hơn việc tạm giữ fact. Việc chọn phương án phụ thuộc yêu cầu **đúng tuyệt đối, tính mới, khả năng chỉnh sửa lịch sử và mức độ chấp nhận thiếu thuộc tính**.

Phần **mô hình** cần ghi điều kiện hợp lệ và ý nghĩa của nhóm unknown. Phần **triển khai** quyết định job xử lý retry, hàng đợi lỗi, lookup, cập nhật lại dimension key và công cụ điều phối.

### 5.4. Sửa, hủy và hoàn trả không phải cùng một thao tác

Trong báo cáo doanh thu, có thể có:

- Dòng bán được **sửa** do sai giá trước khi chốt.
- Đơn bị **hủy** trước khi được coi là bán hợp lệ.
- Đơn đã bán, sau đó khách **trả lại một phần** sản phẩm.
- Một giao dịch được **hoàn tiền** ở thời điểm khác thời điểm trả hàng.

Không thể chỉ thấy “có giá trị âm” rồi quyết định bỏ vào fact_sales_line mà không xác định ý nghĩa nghiệp vụ. Một thiết kế có thể dùng:

~~~~text
FACT_SALES_LINE
  grain = một dòng bán hợp lệ
  measure = số lượng và tiền bán sau chiết khấu

FACT_RETURN_LINE
  grain = một dòng hoàn trả được ghi nhận
  measure = số lượng trả, số tiền trả
  liên kết = order_line_id hoặc sales_line_key, nếu đủ thông tin
~~~~

Khi đó chỉ số:

\[
\text{Doanh thu sau hoàn trả}
=\text{Doanh thu thuần bán hàng}-\text{Giá trị hoàn trả theo chính sách}
\]

phải chỉ rõ **thời điểm ghi nhận hoàn trả**, loại phí/thuế và kỳ báo cáo. Một số báo cáo phân loại hoàn trả theo **ngày trả**; báo cáo khác phân tích chất lượng đơn theo **ngày bán ban đầu**. Hai cách nhìn không tương đương và cần được mô hình hóa minh bạch.

**Ngoài phạm vi bài:** viết job xử lý event hủy, đối soát thanh toán, phát lại sự kiện hoàn tiền, hay hợp nhất các nguồn payment và order theo trạng thái. Chúng cần yêu cầu mô hình làm đầu vào, nhưng là một hệ thống xử lý riêng.

### 5.5. Idempotency: yêu cầu thuộc grain, cách làm thuộc pipeline

Nếu nguồn gửi hai lần một sự kiện bán có cùng **order_line_id**, fact chỉ được có **một hàng** cho sự kiện theo grain đã chốt. Ràng buộc UNIQUE(order_line_id) nêu lên yêu cầu này ở lược đồ đích.

Nhưng chỉ có UNIQUE không định nghĩa đầy đủ:

- Bản tin thứ hai giống hệt có được bỏ qua không?
- Bản tin thứ hai mang giá trị sửa đổi thì **update** hay chuyển thành một sự kiện điều chỉnh khác?
- Khi chạy lại một ngày dữ liệu, job ghi đè phân vùng, merge theo khóa hay đối soát rồi cập nhật?
- Nếu một source order_line_id được **tái sử dụng** qua tenant hoặc phiên bản hệ thống, khóa nghiệp vụ thật có cần thêm tenant_id/source_system không?

Đó là các câu hỏi **thiết kế giao thức nạp và idempotency**. Mô hình phải định nghĩa **định danh duy nhất và cách hiểu sửa đổi**, còn pipeline phải thực thi cách xử lý replay/upsert một cách an toàn.

## 6. Luồng dữ liệu xuất hiện ở đâu trong kiến trúc?

Ta có thể mô tả **các công đoạn** ETL/ELT để thấy ranh giới bàn giao mà **không triển khai chúng**.

~~~~mermaid
flowchart LR
    S["Nguồn OLTP / API / sự kiện"] --> I["Extract / CDC / ingestion"]
    I --> R["Raw / landing"]
    R --> T["Transform / validate / lookup"]
    T --> W["Load / merge / publish"]
    W --> M["Fact / dimension / semantic model"]
    M --> B["BI / báo cáo / truy vấn"]

    D["Thiết kế: grain, measure, dim, khóa, SCD, DQ"] -. "Quy định hợp đồng dữ liệu" .-> T
    D -. "Xác định lược đồ đích" .-> M
    O["Vận hành: scheduler, retry, backfill, alerts"] -. "Điều phối và giám sát" .-> I
    O -. "Điều phối và giám sát" .-> W
~~~~

Sơ đồ không đòi hỏi mọi tổ chức phải có đúng các tầng Raw, Staging, Warehouse như trên. Có hệ thống ELT biến đổi trực tiếp trong data warehouse, có hệ thống streaming nạp liên tục, có hệ thống dùng lakehouse. **Ranh giới khái niệm** vẫn rõ: thiết kế mô hình là bộ quy tắc/đích dữ liệu, còn pipeline là tiến trình đưa dữ liệu từ nguồn đến đích theo bộ quy tắc ấy.

### 6.1. Các bước ETL/ELT và loại đầu vào từ mô hình

| Bước ETL/ELT | Nhóm triển khai cần quyết định | Mô hình phải cung cấp trước |
| --- | --- | --- |
| Extract / ingest | Connector, quyền, CDC log, lịch lấy dữ liệu, phân vùng | Nguồn có thẩm quyền, danh sách sự kiện/thuộc tính cần có |
| Landing / raw | Định dạng, lưu giữ, schema evolution, mã hóa | Hợp đồng trường nguồn và yêu cầu truy vết |
| Clean / standardize | Parse, quy đổi múi giờ, xử lý null/bẩn | Miền giá trị, quy tắc thời gian, chính sách xử lý sai |
| Transform | SQL/job biến đổi, chọn batch/stream | Grain, công thức measure, bản đồ nguồn–đích ở mức nghiệp vụ |
| Dimension processing | Phát hiện thay đổi, cấp surrogate key, SCD2 update | Chính sách SCD, business key, khoảng hiệu lực |
| Fact loading | Merge/upsert, dedup, backfill, quản lý partition | Khóa sự kiện, grain, cách xử lý sửa/hủy/hoàn |
| Quality checks | Framework test, threshold, kết quả pass/fail | Bất biến cần kiểm tra, chuẩn đối soát, mức chịu lỗi |
| Publish | Điều kiện công bố, snapshot, làm mới dashboard | Kỳ báo cáo, tính nhất quán và độ mới yêu cầu |
| Orchestration | DAG, scheduler, dependency, retry | Phụ thuộc dữ liệu ở mức hợp đồng, deadline mong muốn |
| Monitoring | Log, metric, alert, runbook, on-call | Tiêu chí đúng/đủ/mới, mức độ quan trọng của dataset |

**Không nên nhập nhằng:** Viết rằng “dữ liệu phải được làm mới trong vòng 30 phút” là một **yêu cầu chất lượng sản phẩm dữ liệu**; chọn Airflow, Kafka, cron hay cơ chế nào để đạt điều đó là **quyết định triển khai**. Không có công cụ nào tự là một phần bắt buộc của việc định nghĩa fact/dimension.

### 6.2. Thiết kế nguồn–đích ở mức nghiệp vụ khác với code chuyển đổi

Một tài liệu mô hình nên có **source-to-target mapping ở mức ngữ nghĩa**:

| Trường đích | Ý nghĩa | Nguồn logic dự kiến | Quy tắc nghiệp vụ |
| --- | --- | --- | --- |
| order_line_id | Định danh dòng bán | ID dòng đơn từ hệ thống order | Duy nhất theo grain, xét cả nguồn/tenant nếu cần |
| order_id | Đơn chứa dòng | ID đơn nghiệp vụ | Hỗ trợ drill-down và COUNT DISTINCT |
| sold_at | Thời điểm ghi nhận bán | Thời điểm hoàn tất hợp lệ | Giữ timestamp có thông tin múi giờ |
| date_key | Ngày báo cáo | Suy ra từ sold_at | Ngày tại Asia/Ho_Chi_Minh |
| customer_key | Phiên bản khách hàng | customer_id + sold_at | Tra dimension theo khoảng hiệu lực |
| product_key | Sản phẩm phân tích | product_id nguồn | Tra đúng dimension sản phẩm |
| quantity | Số lượng bán | Dòng đơn hợp lệ | Dương; cùng một đơn vị đo đã quy định |
| gross_amount | Giá trị trước chiết khấu | Giá trị dòng bán có thẩm quyền | VND; không âm |
| discount_amount | Chiết khấu dòng | Hợp đồng khuyến mại/dòng bán | VND; từ 0 đến gross_amount |
| net_amount | Doanh thu thuần sau chiết khấu | Tính từ gross và discount | Không tự trừ hoàn tiền/thuế nếu chưa quy định |

Tên nguồn như **orders**, **order_lines** chỉ là ví dụ logic; trong dự án thật phải xác minh bảng, API hoặc event cụ thể và quyền sử dụng dữ liệu. Tài liệu mapping trên **không có** vòng lặp đọc nguồn, logic watermark, mã làm sạch bản tin hay cấu hình lịch chạy—và **không cần có** để được xem là tài liệu mô hình có ích.

### 6.3. Điểm giao giữa hai nhóm: câu hỏi phải được trả lời trước khi coding

Một vài quyết định thường cần được thảo luận chung:

1. **Khóa sự kiện có thật sự ổn định không?** Nếu order_line_id đổi sau khi đơn được tách, mô hình cần business key đáng tin hơn.
2. **Có phân biệt thời gian bán và thời gian nạp không?** Nếu nguồn thiếu sold_at, nhóm thiết kế phải chọn quy tắc thời gian thay thế có ghi rõ độ tin cậy.
3. **Nguồn có lưu lịch sử phân khúc khách không?** Nếu không có, mong muốn báo cáo “phân khúc tại thời điểm bán” có thể không thể phục dựng đầy đủ cho quá khứ.
4. **Mọi sản phẩm có thể cùng quy đổi quantity không?** Nếu không, phải điều chỉnh measure/đơn vị trước khi tổng hợp.
5. **Có bảo đảm tính nhất quán giữa order và payment không?** Nếu doanh thu phụ thuộc thanh toán, mô hình sự kiện phải nói rõ khi nào giao dịch đủ điều kiện.

Đây không phải lý do để viết pipeline ngay. Đây là **điểm xác minh tính khả thi**: mô hình không nên cam kết dữ liệu lịch sử mà nguồn không có hoặc measure mà nghiệp vụ chưa định nghĩa.

## 7. Chất lượng dữ liệu: định nghĩa phép kiểm tra khác với xây dựng bộ máy chạy kiểm tra

**Thiết kế mô hình** nên nêu những điều **luôn phải đúng** đối với dataset và những **sai lệch được chấp nhận**. Từ đó nhóm triển khai mới chọn được nơi chạy kiểm tra, tần suất, mức độ ngăn công bố, cảnh báo và cách khôi phục.

### 7.1. Bốn nhóm phép kiểm tra chính

| Nhóm kiểm tra | Câu hỏi của mô hình | Ví dụ trên fact bán hàng |
| --- | --- | --- |
| **Validity / tính hợp lệ** | Một hàng có giá trị đúng miền và công thức không? | quantity > 0, gross ≥ discount ≥ 0 |
| **Uniqueness / tính duy nhất** | Có hai hàng đại diện cùng một sự kiện không? | order_line_id duy nhất |
| **Referential / temporal integrity** | Tham chiếu dimension có đúng loại và đúng phiên bản không? | customer_key tồn tại và hiệu lực tại sold_at |
| **Completeness / reconciliation** | Dữ liệu đã đủ so với nguồn có thẩm quyền chưa? | Số dòng/tổng tiền sau lọc điều kiện bán hợp lệ khớp đối soát nguồn |

**Freshness** là một tiêu chí bổ sung: bản dữ liệu mới nhất đã đáp ứng deadline theo nghiệp vụ chưa? Một dataset có thể **đúng nhưng quá cũ**, hoặc **rất mới nhưng sai**. Không đánh đồng freshness với correctness.

### 7.2. Ví dụ SQL kiểm tra sau khi dữ liệu đã được nạp

**Kiểm tra có dòng không khớp ngày nghiệp vụ:**

~~~~sql
SELECT
    f.order_line_id,
    f.sold_at,
    d.full_date
FROM fact_sales_line AS f
JOIN dim_date AS d ON d.date_key = f.date_key
WHERE d.full_date IS DISTINCT FROM
      (f.sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE;
~~~~

Kỳ vọng với dữ liệu mẫu là **0 dòng vi phạm**. Nếu tổ chức định nghĩa ngày bán theo múi giờ khác, phải sửa cả hợp đồng và truy vấn kiểm tra.

**Kiểm tra fact tham chiếu đúng phiên bản khách tại thời điểm bán:**

~~~~sql
SELECT
    f.order_line_id,
    f.sold_at,
    c.customer_id,
    c.customer_key,
    c.effective_from,
    c.effective_to
FROM fact_sales_line AS f
JOIN dim_customer AS c ON c.customer_key = f.customer_key
WHERE NOT (
    c.effective_from <= f.sold_at
    AND (
        c.effective_to > f.sold_at
        OR c.effective_to IS NULL
    )
);
~~~~

Kỳ vọng **0 dòng vi phạm**. Lệnh JOIN kiểm tra tính đúng khoảng hiệu lực của phiên bản mà fact đã trỏ đến; nó không chứng minh nguồn đã gửi **đúng customer_id** cho sự kiện, vì fact trong ví dụ chỉ lưu customer_key.

**Kiểm tra khoảng hiệu lực SCD2 bị chồng lấn cho cùng mã khách:**

~~~~sql
SELECT
    a.customer_id,
    a.customer_key AS version_a,
    b.customer_key AS version_b
FROM dim_customer AS a
JOIN dim_customer AS b
    ON a.customer_id = b.customer_id
   AND a.customer_key < b.customer_key
   AND a.effective_from <
       COALESCE(b.effective_to, 'infinity'::TIMESTAMPTZ)
   AND b.effective_from <
       COALESCE(a.effective_to, 'infinity'::TIMESTAMPTZ);
~~~~

Kỳ vọng **0 cặp chồng lấn**. Truy vấn dùng khoảng **[from,to)** nên hai phiên bản có điểm kết thúc/bắt đầu bằng nhau **không** bị xem là chồng lấn. Cơ sở dữ liệu có thể hỗ trợ cơ chế ràng buộc khoảng hiệu lực chặt hơn, nhưng việc chọn và triển khai cụ thể cần được đánh giá theo DBMS.

**Kiểm tra tổng chi tiết có khớp số kỳ vọng của bộ dữ liệu mẫu:**

~~~~sql
SELECT
    COUNT(*) AS line_count,
    COUNT(DISTINCT order_id) AS order_count,
    SUM(quantity) AS total_quantity,
    SUM(net_amount) AS total_net_amount
FROM fact_sales_line;
-- Kỳ vọng với dữ liệu thử: 4, 3, 7, 215000.
~~~~

Khi có nguồn thật, kiểm tra **độ đầy đủ** đòi hỏi đối chiếu với dữ liệu nguồn được chọn theo **cùng mốc thời gian, điều kiện trạng thái, tiền tệ và grain**. Chạy COUNT(*) ở bảng đích một mình không chứng minh dữ liệu đã đầy đủ so với nguồn.

### 7.3. Định nghĩa kiểm tra không đồng nghĩa vận hành kiểm tra

Trong tài liệu mô hình, có thể ghi:

> Với mọi dòng fact đã công bố, ngày trong dim_date phải bằng ngày của sold_at theo múi giờ Asia/Ho_Chi_Minh; mọi customer_key phải trỏ tới một phiên bản khách đang có hiệu lực tại sold_at.

Đó là **quy tắc có thể kiểm chứng**. Công việc triển khai tiếp theo là:

- Chạy kiểm tra ở bước nào: trước nạp, sau merge, trước publish hay liên tục?
- Trường hợp lỗi thì chặn toàn bộ lô, tách dòng lỗi hay công bố có cảnh báo?
- Ai nhận cảnh báo, cách đo độ nghiêm trọng và quy trình khôi phục?
- Kết quả kiểm tra được lưu thế nào để truy vết và đối soát?

Một bài thiết kế mô hình không cần tự cài đặt tất cả bước này. Tuy nhiên, **không được bỏ việc ghi quy tắc kiểm tra** chỉ vì bộ máy kiểm tra thuộc phạm vi ETL.

### 7.4. DDL có thể bảo vệ một phần, không thay thế đối soát nguồn

Ràng buộc UNIQUE(order_line_id) chặn **hai dòng cùng mã** ở bảng fact. Nó không phát hiện **một dòng nguồn bị bỏ sót**, và cũng không biết doanh thu của dòng được ghi đúng hay chưa nếu số tiền sai nhưng vẫn lớn hơn 0.

Ràng buộc FK(customer_key) bảo đảm **phiên bản dimension tồn tại**, nhưng không tự chứng minh đó là **phiên bản đúng theo thời điểm bán**. Một quy tắc kiểm tra thời gian có thể tìm vấn đề này; nếu muốn chặn tại DB khi ghi, cần thiết kế cơ chế ràng buộc bổ sung và xem xét chi phí.

Đó là lý do **định nghĩa mô hình + ràng buộc SQL + phép đối soát + vận hành pipeline** là những lớp bảo vệ khác nhau.

## 8. Tài liệu bàn giao mô hình phân tích nên chứa những gì?

Một bản thiết kế không nhất thiết phải có hàng trăm trang. Quan trọng là đủ **quyết định có thể kiểm tra** và đủ rõ để nhóm ETL, BI và dữ liệu không hiểu khác nhau.

### 8.1. Cấu trúc tài liệu đề xuất

| Phần tài liệu | Nội dung phải trả lời |
| --- | --- |
| **Business questions** | Báo cáo/KPI nào cần trả lời, ai sở hữu định nghĩa? |
| **Scope và non-scope** | Dataset nào sẽ thiết kế, phần nguồn/pipeline nào chưa triển khai? |
| **Grain và population** | Một hàng fact là gì; sự kiện nào được đưa vào hoặc loại ra? |
| **Fact và measure** | Chỉ số, đơn vị đo, phép cộng, công thức và quy tắc hoàn/hủy |
| **Dimension** | Thuộc tính phân tích, khóa và phạm vi giá trị |
| **History policy** | SCD1/SCD2, thời điểm hiệu lực, cách nhìn hiện tại hoặc lịch sử |
| **Time semantics** | Event time, ngày nghiệp vụ, múi giờ, ngày nạp dữ liệu |
| **Keys và relationships** | Business key, surrogate key, FK, khả năng NULL, cardinality |
| **Data contracts** | Trường đầu vào tối thiểu, mapping ngữ nghĩa, xử lý dữ liệu thiếu |
| **Quality rules** | Các bất biến, ví dụ phản chứng và tiêu chí đối soát |
| **Freshness requirement** | Độ trễ được phép, mốc đo, không nhầm với cam kết đã triển khai |
| **Example queries** | Các truy vấn mẫu chứng minh chỉ số/chiều phân tích |
| **Open decisions** | Những yêu cầu chưa chốt hoặc nguồn chưa đủ năng lực |
| **Handoff** | Những quyết định nhóm ETL, BI, Security và vận hành còn phải thực hiện |

### 8.2. Một trang quyết định mẫu cho fact_sales_line

~~~~text
DATA PRODUCT: Daily Sales Analysis

Dataset:
  fact_sales_line

Grain:
  1 hàng cho 1 order_line_id đã được ghi nhận bán hợp lệ.

Included:
  Giao dịch đạt trạng thái hoàn tất theo chính sách bán hàng.

Excluded:
  Đơn nháp, đơn hủy trước khi ghi nhận bán.
  Hoàn trả: được mô hình trong dataset riêng.

Time:
  Event timestamp: sold_at.
  Reporting date: ngày Asia/Ho_Chi_Minh của sold_at.

Measures:
  quantity > 0, đơn vị bán của sản phẩm.
  gross_amount >= 0 VND.
  0 <= discount_amount <= gross_amount.
  net_amount = gross_amount - discount_amount.

Keys:
  UNIQUE(order_line_id) theo phạm vi nguồn đã xác nhận.
  customer_key gắn với SCD2 tại sold_at.

Required dimensions:
  dim_date, dim_customer, dim_product.

Freshness target:
  Dữ liệu hợp lệ cần có trong báo cáo trong 30 phút từ khi nguồn
  xác nhận bán thành công (giả định nghiệp vụ, chưa triển khai).

Non-scope of this model specification:
  Connector, CDC, batch/streaming, scheduler, retries,
  backfill, deployment, monitoring implementation.

Unresolved:
  Chính sách sửa đơn sau hoàn tất; hoàn tiền nhiều đợt;
  ID dòng bán có ổn định xuyên hệ thống hay không.
~~~~

**Một tài liệu tốt có thể chứa câu hỏi chưa giải quyết.** Những điều chưa xác minh phải được ghi thành **open decision**, thay vì âm thầm chọn mặc định rồi để pipeline triển khai một nghĩa vụ không được phê duyệt.

### 8.3. Tiêu chí nghiệm thu riêng cho phần thiết kế

Một bản mô hình có thể được coi là đủ để **bàn giao thiết kế** khi:

1. Người dùng nghiệp vụ xác nhận **câu hỏi và định nghĩa KPI**.
2. Mỗi fact có **grain cụ thể**, tập sự kiện đưa vào/loại ra và khóa chống trùng.
3. Mỗi dimension có nguồn danh tính, khóa, ngữ nghĩa lịch sử và thuộc tính cần dùng.
4. Measure có **đơn vị, công thức, phạm vi thời gian và tính cộng được**.
5. Có sơ đồ liên kết và bảng mô tả khóa/quan hệ.
6. Quy tắc thay đổi, đến muộn, thiếu dimension, hoàn/hủy được chốt hoặc ghi chưa chốt.
7. Có data contract, quy tắc kiểm chứng và một bộ dữ liệu mẫu với **đáp án truy vấn mong đợi**.
8. Nhóm triển khai có thể giải thích rõ những thông tin nguồn còn thiếu hoặc rủi ro khả thi.
9. Tài liệu nói rõ **ETL/ELT chưa được triển khai**; không coi truy vấn ví dụ là bằng chứng hệ thống tự động chạy.

Không nên ghi **“đã hoàn thành pipeline”** chỉ vì có các bảng, dữ liệu minh họa và một vài câu SELECT. Đó là một **đầu ra thiết kế đã có thể kiểm chứng**, không phải một hệ thống vận hành đã được nghiệm thu.

## 9. Phân chia trách nhiệm trong dự án thực tế

Công việc có thể do cùng một người hoặc nhiều nhóm thực hiện; ranh giới dưới đây là **trách nhiệm chức năng**, không phải bắt buộc tổ chức phải chia đội ngũ theo đúng tên gọi.

| Vai trò/chức năng | Trách nhiệm chính | Bàn giao/điểm phối hợp |
| --- | --- | --- |
| **Business/Product Owner** | Định nghĩa KPI, tiêu chí đưa sự kiện vào, thời gian hiệu lực | Chấp thuận “doanh thu” thực sự là chỉ số gì |
| **Data Modeler / Analytics Engineer** | Grain, fact, dimension, semantic definitions, history policy, data contracts | Lược đồ/định nghĩa có thể kiểm chứng, SQL truy vấn mẫu |
| **Data Engineer** | Ingestion, transformation, lookup, job execution, backfill, idempotency, recovery | Pipeline nạp dữ liệu theo hợp đồng; bằng chứng chạy đúng |
| **BI/Analytics** | Dashboard, metric presentation, drill-down và kiểm chứng góc nhìn người dùng | Truy vấn/biểu đồ sử dụng đúng grain và measure |
| **Data Quality/Governance** | Chủ sở hữu dữ liệu, phân loại nhạy cảm, tiêu chí chất lượng, lineage | Chính sách kiểm soát và kết quả kiểm tra |
| **Platform/SRE/Security** | Quyền, bí mật, hạ tầng, chi phí, theo dõi, cảnh báo | Năng lực vận hành, bảo mật và phục hồi |

Ví dụ một analytics engineer vừa có thể định nghĩa bảng fact vừa viết SQL chuyển đổi trong ELT. Điều đó **không làm hai loại đầu ra trở thành một**. Tài liệu mô hình vẫn nên được xem xét theo tính đúng của ngữ nghĩa, còn mã pipeline được nghiệm thu theo **khả năng chạy, đúng dữ liệu nguồn, an toàn và có thể phục hồi**.

### 9.1. Trường hợp phải trao đổi ngược từ ETL về mô hình

Nhóm ETL phát hiện nguồn không cung cấp lịch sử customer_segment, chỉ có phân khúc **hiện tại**. Yêu cầu ban đầu của mô hình là báo cáo “phân khúc tại thời điểm bán” cho ba năm đã qua.

Không thể giải quyết bằng cách **điền phân khúc hiện tại cho cả ba năm rồi gọi đó là lịch sử**. Các lựa chọn cần trao đổi gồm:

- Thu thập nguồn lịch sử đáng tin khác nếu có.
- Giới hạn phạm vi báo cáo lịch sử từ thời điểm bắt đầu ghi nhận thay đổi.
- Gắn **cờ độ tin cậy** hoặc nhãn “không thể xác định lịch sử” cho giai đoạn cũ.
- Đổi yêu cầu phân tích thành “phân khúc hiện tại” nếu người dùng chấp thuận.

Đây là một thay đổi **hợp đồng ngữ nghĩa** cần bên sở hữu mô hình/nghiệp vụ quyết định. Không nên để pipeline âm thầm đổi ý nghĩa của KPI.

### 9.2. Thay đổi schema có tác động tới pipeline, nhưng không phải là pipeline

Khi thêm product_category_history hoặc thay grain của fact, mô hình cần phiên bản thiết kế mới, quy tắc tương thích và kế hoạch dữ liệu lịch sử. Nhóm triển khai sẽ thực hiện **migration, reprocessing/backfill, cập nhật job** và kiểm tra tác động dashboard.

Nói cách khác: mô hình là **hợp đồng mục tiêu cần thay đổi có kiểm soát**; ETL/ELT là **cơ chế hiện thực và đồng bộ hóa hợp đồng đó**. Cùng một thay đổi có thể tác động cả hai bên mà vẫn giữ ranh giới trách nhiệm rõ ràng.

## 10. Những tình huống dễ vượt phạm vi khi học mô hình phân tích

Khi làm bài tập thiết kế, có nhiều yêu cầu nghe giống “mô hình” nhưng thực chất đã chuyển sang **triển khai luồng dữ liệu**. Để xác định ranh giới, hãy hỏi: **đầu ra là quy tắc và cấu trúc dữ liệu, hay là một tiến trình tự chạy trong môi trường?**

### 10.1. “Thiết kế mô hình doanh thu theo tháng”

**Trong phạm vi mô hình:**

- Định nghĩa “tháng” theo lịch và múi giờ nào.
- Chốt grain sự kiện nguồn, cách SUM thành chỉ số tháng và những measure không được cộng trực tiếp.
- Xác định dimension thời gian, khách hàng, sản phẩm và các thuộc tính phân nhóm.
- Quyết định hoàn trả được tính vào tháng bán hay tháng hoàn.
- Thiết kế cấu trúc fact chi tiết và có thể một **aggregate table** tháng nếu truy vấn yêu cầu.
- Viết truy vấn kiểm chứng doanh thu một tháng có khớp tập dòng đã chốt hay không.

**Ngoài phạm vi mô hình đơn thuần:**

- Lên lịch job cuối mỗi tháng.
- Cấu hình incremental refresh hoặc materialized view refresh job.
- Viết cơ chế reprocess những tháng có đơn hoàn trả đến muộn.
- Tích hợp dashboard, quyền xem báo cáo, alert job lỗi.

Một mô hình có thể **đề nghị cần làm mới bảng tháng sau khi có giao dịch muộn**, nhưng không cần tự xây DAG thực hiện việc đó.

### 10.2. “Thiết kế SCD Type 2 cho khách hàng”

**Trong phạm vi mô hình:**

- Chỉ rõ thuộc tính nào cần giữ lịch sử.
- Business key của khách, surrogate key từng phiên bản.
- Khoảng hiệu lực [from,to), quy tắc ngày mở/đóng.
- Cách fact gắn với phiên bản theo event time.
- Quy tắc không chồng lấn, một phiên bản hiện hành.

**Ngoài phạm vi mô hình đơn thuần:**

- Code CDC phát hiện bản ghi đổi phân khúc.
- Chiến lược phân vùng, transaction MERGE, lock và retry.
- Đóng phiên bản cũ hoặc chèn phiên bản mới trong môi trường có ghi đồng thời.
- Backfill lịch sử quá khứ, kiểm tra late-arriving dimension trong pipeline thật.

Một câu SQL minh họa truy vấn phiên bản không đồng nghĩa đã hoàn thành triển khai SCD2 có khả năng phục hồi.

### 10.3. “Bảo đảm báo cáo luôn đủ và đúng”

**Trong phạm vi mô hình:**

- Định nghĩa **đủ** so với những sự kiện nào ở nguồn, trong thời kỳ nào.
- Định nghĩa **đúng** theo khóa, measure, điều kiện trạng thái và quan hệ thời gian.
- Đặt phép đối soát mong muốn và ngưỡng sai lệch cho phép.
- Phân biệt dữ liệu “chưa có”, “không áp dụng”, “không thể xác định lịch sử”.

**Ngoài phạm vi mô hình đơn thuần:**

- Xây hệ thống chạy kiểm tra theo lịch.
- Cấu hình cảnh báo độ trễ và chênh lệch.
- Điều tra log, chạy lại job, xử lý dữ liệu lỗi.
- Thiết kế dashboard vận hành SLA và runbook khôi phục.

### 10.4. “Tích hợp ba nguồn dữ liệu để phân tích khách”

**Trong phạm vi mô hình:**

- Định nghĩa thế nào là **một khách hàng** xuyên các nguồn.
- Khóa nhận dạng hợp nhất và độ tin cậy của từng nguồn.
- Quy tắc xung đột cho các thuộc tính như địa chỉ, nhóm khách, trạng thái.
- Dimension khách hàng hợp nhất (*conformed customer dimension*) và nguồn sự thật (*source of truth*).
- Phạm vi chấp nhận tính trễ hoặc thiếu thông tin.

**Ngoài phạm vi mô hình đơn thuần:**

- Tạo API ingestion, đồng bộ lịch, CDC hoặc file import.
- Thực thi fuzzy matching hay entity resolution bằng chương trình.
- Xây pipeline hợp nhất ID và duy trì bảng mapping theo thời gian.
- Quản trị quota API, bí mật kết nối và retry.

Quy tắc hợp nhất có thể **được đặc tả trong mô hình/hợp đồng dữ liệu**, nhưng việc xây engine thực thi quy tắc đó là một sản phẩm kỹ thuật riêng cần nghiệm thu.

## 11. Các đánh đổi của mô hình phân tích cần nêu, không cần giải bằng hạ tầng ngay

### 11.1. Star schema và cấu trúc chuẩn hóa

Mô hình giao dịch quan hệ thường chuẩn hóa để duy trì toàn vẹn và giảm dư thừa. Mô hình phân tích có thể dùng dimension giàu thuộc tính và fact khóa ngoại để thuận tiện tổng hợp.

| Khía cạnh | Mô hình giao dịch chuẩn hóa | Mô hình phân tích hình sao |
| --- | --- | --- |
| Tối ưu nghiệp vụ chính | Ghi/sửa dữ liệu giao dịch | Lọc, nhóm và tổng hợp chỉ số |
| Grain | Theo từng thực thể hoặc quan hệ nghiệp vụ | Fact theo sự kiện/snapshot xác định |
| Thuộc tính mô tả | Có thể trải trên nhiều bảng chuẩn hóa | Thường tập trung trong dimension |
| Dữ liệu thời gian | Trạng thái hiện tại hoặc lịch sử theo OLTP | Chính sách lịch sử phục vụ câu hỏi phân tích |
| Rủi ro nếu thiết kế kém | Bất thường cập nhật, mồ côi, thiếu khóa | Đếm trùng, sai metric, JOIN sai grain, gán nhầm phiên bản |

Chọn star schema không có nghĩa được phép bỏ ràng buộc duy nhất và tham chiếu. Ngược lại, giữ nguyên tất cả bảng OLTP cũng không bảo đảm báo cáo đúng grain.

### 11.2. Chi tiết hay tổng hợp sẵn?

Một bảng fact ở mức dòng bán cho phép nhiều phân tích linh hoạt nhưng có thể lớn. Bảng aggregate theo ngày–sản phẩm–phân khúc có thể giảm khối lượng dữ liệu đọc cho một số báo cáo:

~~~~text
AGG_DAILY_PRODUCT_SEGMENT:
  grain = một hàng / ngày / sản phẩm / phân khúc khách
  measures = tổng quantity, gross, discount, net
~~~~

Nếu tạo aggregate, phải:

- Định nghĩa chiều nhóm và kỳ thời gian.
- Xác định measure nào có thể SUM và measure nào phải tính lại.
- Làm rõ aggregate là **dữ liệu suy ra từ fact** hay một nguồn tính toán độc lập.
- Có phép đối soát để aggregate khớp fact chi tiết.
- Xác định cơ chế xử lý dữ liệu muộn khiến một nhóm ngày cũ thay đổi.

**Mô hình** chịu trách nhiệm về grain và ngữ nghĩa của aggregate. **Pipeline** chịu trách nhiệm tính, nạp, làm mới, sửa lại hoặc thay thế dữ liệu tổng hợp khi cần. Thiết kế aggregate không đồng nghĩa lập trình công việc refresh.

### 11.3. Snapshot và transaction fact

Không phải mọi fact đều là “một sự kiện bán”. Có các mẫu phổ biến:

- **Transaction fact:** một hàng mỗi sự kiện hoặc dòng giao dịch.
- **Periodic snapshot fact:** một hàng theo kỳ, ví dụ tồn kho **cuối ngày** theo kho–sản phẩm.
- **Accumulating snapshot fact:** một hàng theo thực thể quy trình và các mốc tiến triển, ví dụ vòng đời xử lý một đơn.

Grain quyết định loại measure nào có thể cộng qua các chiều. Với tồn kho cuối ngày, cộng tồn kho của ngày 01/10 với tồn kho của ngày 02/10 thường **không tạo ra một chỉ số tồn kho có ý nghĩa**. Có thể tính trung bình, chênh lệch, cuối kỳ... nhưng phải định nghĩa rõ.

Việc job chụp snapshot mỗi đêm chạy như thế nào, lưu watermark ra sao và xử lý ngày bị thiếu thế nào vẫn là **triển khai pipeline**.

### 11.4. Conformed dimensions và nhiều fact

Nếu có cả FACT_SALES_LINE và FACT_RETURN_LINE, hai fact có thể dùng chung DIM_DATE, DIM_PRODUCT và DIM_CUSTOMER khi định nghĩa chiều tương thích.

Tuy nhiên, phải xác định rõ:

- **Ngày nào**: sale_date hay return_date? Hai chiều có thể dùng cùng bảng DIM_DATE nhưng giữ vai trò khác nhau (*role-playing dimension*).
- **Khách nào**: khách mua tại thời điểm bán hay khách thực hiện hoàn trả?
- **Sản phẩm nào**: sản phẩm theo định danh hiện tại hay phiên bản tại thời điểm giao dịch?
- **Measure**: số tiền bán và tiền hoàn có thể trừ nhau theo kỳ nào?

Một dimension dùng chung làm báo cáo nhất quán hơn khi các định nghĩa phù hợp. Nhưng **không nên JOIN hai bảng fact chi tiết trực tiếp trên date_key/product_key rồi SUM**, vì nhiều dòng bán và nhiều dòng hoàn cùng ngày/sản phẩm sẽ nhân bản tổ hợp. Cần tổng hợp từng fact về **cùng grain so sánh** trước khi nối kết quả, hoặc dùng một semantic layer được thiết kế đúng.

### 11.5. Yêu cầu về tốc độ không quyết định toàn bộ cấu trúc mô hình

Một mục tiêu “dashboard trả trong 2 giây” không đủ để kết luận phải tạo một bảng phẳng hay dùng một loại database cụ thể. Trước hết phải kiểm chứng:

- Báo cáo trả lời câu hỏi gì và đọc mức grain nào?
- Dữ liệu có bao nhiêu hàng, thay đổi thường xuyên thế nào?
- Những chiều lọc nào phổ biến?
- Mức tính mới được phép là bao lâu?
- Có cần truy xuất chi tiết hay chỉ các nhóm tổng hợp?

Sau khi mô hình đúng, kỹ thuật triển khai mới đánh giá **partitioning, clustering, index, materialized view, caching, engine truy vấn, incremental processing** và chi phí thực tế. Tối ưu vật lý quan trọng nhưng không thay thế định nghĩa nghiệp vụ.

## 12. Checklist trước khi bàn giao mô hình cho đội ETL

Đây là danh sách kiểm tra cho **một sản phẩm thiết kế**, không phải bảng tiến độ lập trình pipeline:

- [ ] Có danh sách câu hỏi nghiệp vụ và người chấp thuận KPI.
- [ ] Mỗi fact có một câu định nghĩa grain, tập sự kiện đưa vào/loại ra.
- [ ] Measure có đơn vị, công thức, quy tắc cộng và thời gian hiệu lực.
- [ ] Dimension có khóa nghiệp vụ, khóa thay thế và chính sách thay đổi thuộc tính.
- [ ] Các quan hệ fact–dimension và null/unknown member được mô tả.
- [ ] Có quyết định về giờ sự kiện, múi giờ báo cáo và ngày dùng cho KPI.
- [ ] Hủy, sửa, hoàn trả, dữ liệu đến muộn và sự kiện gửi lặp có quy tắc rõ hoặc được ghi là vấn đề chưa chốt.
- [ ] Hợp đồng nguồn–đích xác định trường tối thiểu và nguồn đáng tin cậy.
- [ ] Có quy tắc kiểm tra tính hợp lệ, duy nhất, tham chiếu và đối soát.
- [ ] Freshness target/latency được nêu như yêu cầu, chưa tự nhận là pipeline đã đạt.
- [ ] Có một bộ dữ liệu nhỏ và truy vấn với kết quả dự kiến để xác nhận logic.
- [ ] Tài liệu phân biệt phần **đã thiết kế** và phần **cần triển khai**.

Nếu một mục chưa đạt, hãy ghi rõ **giả định, hệ quả và người cần quyết định**. Không nên lấp chỗ trống bằng công cụ hoặc pipeline phức tạp khi định nghĩa nghiệp vụ còn chưa rõ.

## 13. Bài tập thực hành có đáp án

### Bài 1 — Phân loại đúng phạm vi công việc

Một dự án yêu cầu:

1. Định nghĩa một hàng fact biểu diễn một dòng bán hoàn tất.
2. Tạo connector CDC đọc thay đổi từ PostgreSQL nguồn.
3. Chọn SCD Type 2 để lưu lịch sử phân khúc khách.
4. Cấu hình cảnh báo khi job nạp bị trễ quá 30 phút.
5. Viết quy tắc so sánh tổng doanh thu nguồn–đích theo ngày.
6. Cài đặt retry với exponential backoff.

**Câu hỏi:** Những phần nào là quyết định mô hình hoặc hợp đồng dữ liệu, những phần nào là triển khai ETL?

**Đáp án:** Mục **1, 3, 5** thuộc **thiết kế mô hình và hợp đồng kiểm chứng**; mục **2, 4, 6** thuộc **triển khai/vận hành pipeline**. Riêng việc **chạy** đối soát nguồn–đích và xử lý kết quả ở mục 5 sẽ do hệ thống ETL/data quality thực hiện. Mục tiêu 30 phút là yêu cầu freshness, còn **cấu hình cảnh báo** để đạt/giám sát yêu cầu đó là công việc vận hành.

### Bài 2 — Chọn grain phù hợp để báo cáo theo sản phẩm

Một đơn O100 chứa 2 dòng: dòng 1 bán sổ tay 90000 VND sau chiết khấu; dòng 2 bán bút 20000 VND. Người thiết kế đề xuất fact có một hàng trên mỗi đơn với doanh thu 110000 VND và nối bảng chi tiết sản phẩm khi báo cáo.

**Câu hỏi:** Vì sao cách làm này dễ sai? Grain nào phù hợp hơn cho doanh thu theo sản phẩm?

**Đáp án:** Nếu nối một hàng đơn với hai sản phẩm rồi SUM doanh thu đơn, **110000 có thể bị tính hai lần**. Để phân tích doanh thu theo sản phẩm, dùng fact **một hàng mỗi dòng bán** với order_line_id duy nhất và net_amount riêng từng dòng (90000 và 20000). Một fact cấp đơn vẫn có thể phục vụ chỉ số khác, nhưng không được JOIN hai grain rồi SUM không kiểm soát.

### Bài 3 — Nhận diện hai định nghĩa “doanh thu thuần”

Đội bán hàng gọi net sales là gross_amount - discount_amount. Đội tài chính gọi net revenue là tiền sau khi trừ hoàn trả, thuế và một số khoản điều chỉnh.

**Câu hỏi:** Có nên dùng một cột net_amount mà không ghi công thức không?

**Đáp án:** Không. Phải **định nghĩa và đặt tên chỉ số rõ phạm vi**: net_sales_after_discount hoặc một tên phù hợp với hợp đồng nghiệp vụ, cùng công thức và những khoản **chưa** tính. Nếu báo cáo tài chính yêu cầu doanh thu đã điều chỉnh, cần quy tắc dữ liệu và sự kiện hoàn/thuế bổ sung, không tự đổi ý nghĩa của cột đang dùng.

### Bài 4 — SCD Type 2 khác Type 1

Khách C001 thuộc Retail ngày 01/10, chuyển sang Enterprise lúc 00:00 ngày 02/10. Báo cáo cần phân khúc **tại thời điểm mua**.

**Câu hỏi:** Chọn SCD1 hay SCD2? Hai giao dịch lúc 09:00 ngày 01/10 và 10:00 ngày 02/10 phải thuộc nhóm nào?

**Đáp án:** Chọn **SCD2** hoặc một mô hình lịch sử tương đương; giao dịch ngày 01/10 thuộc **Retail**, ngày 02/10 thuộc **Enterprise**. Fact phải trỏ đúng phiên bản dimension theo sold_at. Chỉ cập nhật segment hiện tại kiểu SCD1 sẽ có nguy cơ gán ngược Enterprise cho cả hai sự kiện lịch sử.

### Bài 5 — Event time và thời gian nạp

Một đơn bán lúc 23:50 ngày 01/10 theo múi giờ Việt Nam, dữ liệu tới warehouse lúc 02:00 ngày 02/10.

**Câu hỏi:** Nếu dashboard theo “ngày bán tại Việt Nam”, đơn này thuộc ngày nào? Ai chịu trách nhiệm gì?

**Đáp án:** Thuộc **01/10** vì date_key phải dựa vào **event time sold_at** và múi giờ Asia/Ho_Chi_Minh. **Mô hình** định nghĩa quy tắc đó. **Pipeline** nhận dữ liệu đến muộn, tính date_key, nạp đúng kỳ và cập nhật báo cáo bị ảnh hưởng. Không được tự dùng ingestion date nếu mục tiêu là ngày bán.

### Bài 6 — UNIQUE có đủ chống dữ liệu thiếu không?

Bảng fact có UNIQUE(order_line_id). Hệ thống nguồn phát sinh 100 dòng bán, nhưng pipeline chỉ nạp 98 dòng, không có khóa trùng.

**Câu hỏi:** Có vi phạm UNIQUE không? Cần phép kiểm tra nào?

**Đáp án:** Không vi phạm UNIQUE. UNIQUE chỉ chặn **lặp khóa**, không phát hiện **dòng bị thiếu**. Cần đối soát số sự kiện nguồn hợp lệ và dữ liệu đích theo **cùng cửa sổ thời gian, điều kiện trạng thái, phạm vi nguồn**; có thể so sánh thêm tổng quantity/net_amount và danh sách ID thiếu. Định nghĩa đối soát thuộc hợp đồng mô hình; việc chạy tự động thuộc pipeline.

### Bài 7 — Thiết kế unknown dimension member

Một dòng bán đã được xác thực, nhưng hệ thống warehouse chưa có dimension của sản phẩm nguồn P999.

**Câu hỏi:** Mô hình có thể quy định những phương án xử lý nào? Có bắt buộc nạp fact ngay không?

**Đáp án:** Có thể **tạm giữ dòng** đến khi dimension có đủ dữ liệu, hoặc dùng **unknown member có ý nghĩa được quy định**, hoặc bản ghi suy luận tạm thời sẽ hoàn thiện sau. Không có lựa chọn duy nhất cho mọi hệ thống. Cần làm rõ ảnh hưởng đến **tính mới, tính đầy đủ và khả năng sửa lịch sử** trước khi thiết kế job nạp thực tế.

### Bài 8 — Chồng lấn hai phiên bản khách hàng

DIM_CUSTOMER lưu hai phiên bản của C001:

~~~~text
customer_key=101, [2026-01-01, 2026-10-05)
customer_key=102, [2026-10-02, 2026-11-01)
~~~~

**Câu hỏi:** Điều gì sai? Chỉ có PK(customer_key) và UNIQUE(customer_id,effective_from) đã đủ để chặn không?

**Đáp án:** Hai khoảng **chồng lấn từ 02/10 đến trước 05/10** nên không biết fact trong kỳ này phải trỏ phiên bản nào. PK và UNIQUE nói trên **không ngăn chồng lấn khoảng hiệu lực**. Phải thêm quy tắc no-overlap ở mô hình và triển khai phép kiểm tra/ràng buộc thời gian phù hợp.

### Bài 9 — Đếm đơn từ fact dòng bán

Bộ dữ liệu mẫu có bốn hàng fact:

~~~~text
O100-L1 → O100
O100-L2 → O100
O101-L1 → O101
O102-L1 → O102
~~~~

**Câu hỏi:** COUNT(*) và COUNT(DISTINCT order_id) lần lượt là bao nhiêu? Chỉ số nào là số đơn?

**Đáp án:** **COUNT(*) = 4** là số **dòng bán**; **COUNT(DISTINCT order_id) = 3** là số **đơn khác nhau** trong tập fact. Không được gọi COUNT(*) là số đơn khi grain là dòng bán.

### Bài 10 — Tính đúng doanh thu và tỷ trọng phân khúc

Theo dữ liệu minh họa, ba dòng nhóm Retail có doanh thu thuần lần lượt 90000, 20000 và 60000 VND; nhóm Enterprise có một dòng 45000 VND.

**Câu hỏi:** Tổng doanh thu và tỷ trọng Retail?

**Đáp án:** Retail = **170000 VND**, Enterprise = **45000 VND**, tổng = **215000 VND**. Tỷ trọng Retail = \(170000/215000\times100\%\approx79{,}07\%\). Phải dùng **tổng ở tử số và mẫu số**, không lấy trung bình đơn giản tỷ lệ trên từng dòng.

### Bài 11 — Tồn kho cuối ngày có phải additive theo thời gian?

Kho A có 100 sản phẩm cuối ngày 01/10 và 120 sản phẩm cuối ngày 02/10.

**Câu hỏi:** SUM hai số để báo cáo “tồn kho hai ngày” thành 220 có ý nghĩa là số tồn không?

**Đáp án:** Không, vì **tồn kho cuối ngày là measure semi-additive theo thời gian**. Báo cáo tồn cuối kỳ có thể lấy **120**, trung bình tồn kho của hai ngày có thể là **110** nếu đó là định nghĩa đã chốt; cộng thành 220 không biểu diễn tồn kho tại một thời điểm. Mô hình phải ghi cách tổng hợp, còn job snapshot là phạm vi pipeline.

### Bài 12 — Có phải triển khai xong ETL khi đã có SQL?

Một kỹ sư đã tạo dim_date, dim_customer, dim_product, fact_sales_line; nhập bốn hàng mẫu và có truy vấn trả về 215000 VND.

**Câu hỏi:** Có thể thông báo “pipeline ETL hoàn tất” không? Còn thiếu loại bằng chứng nào?

**Đáp án:** Không. Đây là bằng chứng **lược đồ và phép tính với dữ liệu mẫu có thể hoạt động**. Chưa chứng minh kết nối nguồn, incremental/CDC, nạp tự động, dedup, cập nhật SCD2, xử lý lỗi, đối soát, backfill, bảo mật, lịch chạy hay monitoring. Những phần đó phải được triển khai và nghiệm thu riêng.

### Bài 13 — Phân biệt aggregate với triển khai refresh

Một dashboard cần doanh thu theo ngày–sản phẩm–phân khúc với lượng dữ liệu rất lớn.

**Câu hỏi:** Nếu đề xuất bảng aggregate, phần nào cần có trong tài liệu mô hình và phần nào cần bàn giao cho nhóm ETL?

**Đáp án:** **Mô hình** định nghĩa grain aggregate, khóa nhóm, công thức measure, đơn vị, cách xử lý dữ liệu muộn và quy tắc đối soát aggregate với fact chi tiết. **Triển khai** quyết định incremental refresh, job schedule, partition, quy trình nạp lại ngày cũ và cảnh báo chênh lệch.

### Bài 14 — Nguồn không có lịch sử

Nghiệp vụ yêu cầu báo cáo phân khúc khách hàng tại thời điểm bán trong năm 2023–2026. Nguồn chỉ lưu phân khúc hiện tại và bắt đầu có nhật ký thay đổi từ 2026.

**Câu hỏi:** Có thể cam kết báo cáo lịch sử chính xác cho giai đoạn 2023–2025 chỉ bằng cách xây SCD2 hôm nay không?

**Đáp án:** Không. SCD2 chỉ bảo toàn những phiên bản **có dữ liệu để xác định**. Nếu nguồn không giữ thay đổi lịch sử, cần tìm nguồn khác, giới hạn phạm vi lịch sử, gắn mức độ không chắc chắn hoặc điều chỉnh KPI với chấp thuận của nghiệp vụ. **Không được bịa lịch sử** bằng cách áp phân khúc hiện tại cho mọi giao dịch cũ rồi gọi đó là “tại thời điểm bán”.

### Bài 15 — Join hai fact chi tiết

FACT_SALES_LINE có ba dòng của P01 trong tháng, còn FACT_RETURN_LINE có hai dòng hoàn trả P01 trong tháng đó. Một báo cáo JOIN hai fact trực tiếp bằng product_key và month, sau đó SUM giá trị bán lẫn hoàn.

**Câu hỏi:** Vì sao có nguy cơ nhân đôi số liệu? Cách làm an toàn hơn?

**Đáp án:** JOIN nhiều–nhiều giữa ba dòng bán và hai dòng hoàn có thể tạo **6 cặp**; giá trị của mỗi fact bị lặp theo số dòng của fact kia. Phải **tổng hợp từng fact về cùng grain báo cáo** (ví dụ month + product_key) trước khi JOIN hai kết quả, hoặc dùng semantic layer được thiết kế tránh fanout. Đây là quyết định **ngữ nghĩa truy vấn và grain**, không phải lỗi mạng của ETL.

### Bài 16 — Chuyển yêu cầu mơ hồ thành bàn giao cụ thể

Yêu cầu duy nhất của người đặt hàng: “Làm kho dữ liệu doanh số và chạy tự động mỗi 15 phút”.

**Câu hỏi:** Hãy chia thành hai nhóm công việc và nêu các câu hỏi còn thiếu trước khi nhận nghiệm thu.

**Đáp án:**

- **Thiết kế mô hình:** làm rõ định nghĩa doanh thu, grain, tập sự kiện bán, hủy/hoàn, tiền tệ, thời gian, dimension, lịch sử khách, khóa nghiệp vụ, data contract và truy vấn mẫu.
- **Triển khai pipeline:** khảo sát nguồn, chọn ingestion, code chuyển đổi/nạp, cập nhật incrementally, lịch 15 phút, xử lý lỗi/retry, bảo mật, giám sát, kiểm thử đối soát và cơ chế backfill.
- **Câu hỏi bắt buộc:** “15 phút” đo từ lúc nào đến lúc nào; dữ liệu trễ được phép bao lâu; nguồn có lịch sử và định danh ổn định không; ai sở hữu KPI; mức sai lệch được phép; ai trực vận hành khi job lỗi?

Đầu ra thiết kế chỉ nên được nghiệm thu khi các quy tắc dữ liệu đã rõ. Đầu ra pipeline chỉ nên được nghiệm thu khi có **bằng chứng hoạt động thực tế** theo tiêu chí đúng, đủ, mới và có thể phục hồi.

## 14. Tổng kết: mô hình là hợp đồng dữ liệu, ETL/ELT là cơ chế hiện thực

| Chủ đề | Thuộc thiết kế mô hình phân tích | Thuộc triển khai ETL/ELT |
| --- | --- | --- |
| **Grain** | Một hàng fact đại diện sự kiện/snapshot nào | Xử lý nguồn để tạo đúng một hàng theo grain |
| **Measure** | Ý nghĩa, đơn vị, công thức, khả năng cộng | Tính toán/kiểm tra khi nạp và làm mới |
| **Dimension** | Thuộc tính, business key, surrogate key, lịch sử | Cấp khóa, xử lý thay đổi, tra phiên bản |
| **SCD2** | Quy tắc khoảng hiệu lực và báo cáo lịch sử | CDC/change detection, version merge, backfill |
| **Time** | Event time, reporting date, timezone | Parse timestamp, xử lý event đến muộn |
| **Duplicate** | Định nghĩa business key và tính duy nhất | Dedup, idempotent load, replay |
| **Returns/corrections** | Ý nghĩa sự kiện và cách tính KPI | Nạp/điều chỉnh sự kiện theo quy tắc |
| **Quality** | Bất biến, phép kiểm tra, tiêu chí đối soát | Chạy test, chặn publish, alert và khôi phục |
| **Freshness** | Mức yêu cầu và điểm đo | Scheduler/streaming, monitoring và xử lý vi phạm |
| **Schema** | Cấu trúc fact/dimension và ràng buộc | Migration, deployment, hiệu chỉnh vật lý |
| **Vận hành** | Nêu đầu vào/phụ thuộc/giới hạn cần thiết | Connector, secrets, retry, backfill, logs, runbook |

**Nguyên tắc cuối cùng:** Để thiết kế dữ liệu phân tích đúng, hãy bắt đầu từ **câu hỏi nghiệp vụ, grain, fact/dimension, measure, khóa, lịch sử, thời gian và hợp đồng kiểm chứng**. Có thể dùng lược đồ SQL, dữ liệu mẫu và các truy vấn kiểm tra để xác nhận thiết kế, nhưng **không nhầm các minh họa đó với một hệ thống ETL đã hoạt động**. Phần ETL/ELT phải được triển khai và nghiệm thu bằng các tiêu chí riêng về kết nối, xử lý, tính đúng/đủ, tính mới, hồi phục và vận hành. Khi ranh giới này rõ ràng, cả mô hình lẫn pipeline đều dễ đánh giá, thay đổi và bảo vệ chất lượng dữ liệu.
