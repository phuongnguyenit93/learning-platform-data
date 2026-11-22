# Số đo, chiều phân tích và quan hệ giữa chúng

## 1. Vì sao mô hình phân tích bắt đầu từ câu hỏi, không phải từ bảng?

Module **DATABASE_DATA_MODELING** rèn kỹ năng chuyển yêu cầu thành mô hình dữ liệu có thực thể, quan hệ, ràng buộc, khóa và lược đồ vật lý phù hợp. Trong chương **Mô hình phân tích**, mục tiêu không đơn thuần là lưu đơn hàng hay sản phẩm cho giao dịch hằng ngày, mà là trả lời nhất quán các câu hỏi tổng hợp:

- Doanh thu thuần tháng 7 của từng danh mục sản phẩm là bao nhiêu?
- Số lượng bán theo khu vực tăng hay giảm?
- Khách hàng thuộc phân khúc nào đang tạo nhiều lợi nhuận nhất?
- Giá trị đơn hàng bình quân (AOV) được tính từ bao nhiêu đơn?
- Tồn kho cuối tháng là bao nhiêu, và vì sao không được cộng tồn của từng ngày?
- Nếu sản phẩm đổi danh mục, báo cáo lịch sử dùng danh mục tại lúc bán hay danh mục hiện nay?

Ba khái niệm quyết định chất lượng câu trả lời là **số đo (measure)**, **chiều phân tích (dimension)** và **quan hệ giữa chúng**. Nhưng trước khi đặt các bảng fact/dimension, bắt buộc phải định nghĩa thêm **hạt dữ liệu (grain)**: mỗi dòng đại diện chính xác cho điều gì.

Trong bài này, các ví dụ dùng hệ thống thương mại điện tử với đơn hàng, sản phẩm, khách, cửa hàng, doanh thu, tồn kho và chiến dịch marketing. Người học sẽ đi từ định nghĩa nghiệp vụ đến star schema, SQL PostgreSQL, Slowly Changing Dimensions (SCD), phép tổng hợp, tránh đếm trùng và bộ kiểm thử dữ liệu.

**Sau bài học, bạn cần làm được**: xác định grain và khóa của fact; phân loại số đo cộng được hoặc không cộng được; tách dimension khỏi measure; xây quan hệ fact–dimension đúng cardinality; tính chỉ số dẫn xuất có mẫu số rõ; xử lý quan hệ nhiều-nhiều và thay đổi thuộc tính theo thời gian; kiểm chứng các con số qua đối soát.

## 2. Số đo là gì? Chiều phân tích là gì?

**Số đo** là đại lượng định lượng được ghi hoặc tính tại một grain. Ví dụ trên một dòng bán hàng: số lượng 2, đơn giá 100.000 VND, chiết khấu 20.000 VND, doanh thu thuần 180.000 VND và giá vốn 120.000 VND.

**Chiều phân tích** mô tả ngữ cảnh của số đo và cho phép lọc, nhóm, phân tầng. Ví dụ: ngày bán, tên sản phẩm, danh mục, thành phố, vùng, kênh bán, phân khúc khách.

| Trường | Vai trò | Tại sao? |
|---|---|---|
| quantity = 2 | Số đo | Có thể cộng số lượng bán theo kỳ nếu cùng đơn vị |
| net_amount = 180000 | Số đo | Đại lượng tiền tại một dòng bán |
| cogs_amount = 120000 | Số đo | Giá vốn đã được ghi nhận cho dòng |
| unit_price = 100000 | Thuộc tính định lượng cơ sở | Có thể tham gia tính tiền nhưng không tự do cộng qua các dòng |
| product_id = P01 | Khóa nhận diện chiều | Dùng liên kết sản phẩm, không cộng các mã |
| category_name = Đồ ăn | Thuộc tính chiều | Dùng nhóm doanh thu |
| year = 2026 | Thuộc tính chiều thời gian | Dùng group/filter, không là số đo kinh doanh |
| order_number = O100 | Định danh giao dịch | Có thể COUNT DISTINCT, không SUM |
| gross_margin_pct = 34,29% | Chỉ số dẫn xuất | Phải tính từ tổng lợi nhuận và tổng doanh thu |

**Không phân loại số đo chỉ dựa trên kiểu số.** Mã bưu điện, khóa sản phẩm, số điện thoại có thể là dữ liệu số nhưng không mang ý nghĩa cộng. Ngược lại, một trạng thái theo danh mục có thể cần đếm số bản ghi để trở thành measure.

### 2.1. Tách câu hỏi BI thành các thành phần

Câu hỏi: **“Doanh thu thuần tháng 07/2026 theo danh mục sản phẩm tại miền Nam”**.

- Measure: tổng net sales.
- Dimension thời gian: tháng và năm của ngày ghi nhận bán.
- Dimension sản phẩm: danh mục **tại thời điểm giao dịch** nếu báo cáo as-was.
- Dimension cửa hàng: khu vực SOUTH.
- Bộ lọc: chỉ dòng bán đủ điều kiện ghi nhận; đơn hủy không được tính.
- Đơn vị tiền: VND, hoặc tiền đã quy đổi theo một quy tắc rõ.
- Grain: một **dòng hàng đã bán**, không phải một đơn hay một ngày.

Từng lựa chọn cần được chốt trước khi viết SQL. Cùng nhãn “doanh thu thuần” có thể bị hiểu khác nhau nếu nhóm bán hàng tính trước hoàn hàng còn nhóm tài chính tính sau hoàn hàng và thuế.

## 3. Grain là hợp đồng của một hàng fact

**Fact table** lưu sự kiện hoặc trạng thái có thể phân tích. Grain trả lời: **một hàng fact đại diện cho đối tượng, thời điểm và mức chi tiết nào?**

| Grain | Một hàng có nghĩa là | Ví dụ số đo |
|---|---|---|
| Dòng bán hàng | Một dòng sản phẩm của một đơn bán đã ghi nhận | quantity, net_amount, cogs_amount |
| Đơn hàng | Một đơn đã ghi nhận | order_total, shipping_fee, item_count |
| SKU–kho–ngày | Tồn của một SKU tại một kho cuối một ngày | closing_qty |
| Khách–tháng | Trạng thái một khách tại kỳ tháng | MRR, trạng thái thuê bao |
| Phiên truy cập | Một session hợp lệ | page_views, duration |
| Lần thanh toán | Một payment transaction | paid_amount, fee_amount |
| Một lần giao hàng | Một shipment | delivered_qty, shipping_cost |

**Grain phải được viết bằng ngôn ngữ nghiệp vụ trước khi đặt khóa kỹ thuật.** Ví dụ với fact dòng bán, order O100 có thể có hai dòng L1 và L2. Khi đó COUNT(*) = 2 là số dòng, không phải số đơn. Muốn đếm đơn phải dùng COUNT(DISTINCT order_number) trong phạm vi phù hợp hoặc dùng fact ở grain đơn.

### 3.1. Sai grain làm nhân số đo

Phí giao hàng 30.000 VND thuộc **đơn O100**. Nếu sao chép cùng 30.000 vào mỗi dòng của đơn và SUM ở fact dòng sản phẩm, một đơn có ba dòng sẽ tạo 90.000 VND phí giao hàng giả.

Có ba lựa chọn:

1. Để shipping_fee trong **fact_order** ở grain đơn.
2. **Phân bổ** shipping_fee xuống từng dòng bằng một quy tắc có căn cứ; khi đó SUM ở grain dòng được phép nếu tổng phân bổ khớp phí đơn.
3. Giữ cả fact_order và fact_sales_line, nhưng chỉ tổng hợp và JOIN ở grain tương thích.

Không ép số đo cấp đơn vào cấp dòng rồi mong phép SUM tự hiểu cardinality.

### 3.2. Grain giao dịch khác grain ảnh chụp

- Sales line đo **biến động đã xảy ra**.
- Inventory daily đo **mức tồn tại điểm cuối ngày**.
- Subscription monthly đo **trạng thái định kỳ**.

Việc hai bảng cùng có date_key và product_key không có nghĩa chúng có thể JOIN trực tiếp từng hàng mà không nhân dữ liệu.

## 4. Tính cộng được của số đo

Số đo cần được phân loại theo **chiều mà phép cộng có ý nghĩa**.

| Loại | Định nghĩa | Ví dụ |
|---|---|---|
| **Additive** | Có thể cộng qua các chiều phù hợp mà không trùng lặp đơn vị quan sát | Quantity sold, net sales, discounts, COGS |
| **Semi-additive** | Cộng qua một số chiều, không cộng qua những chiều khác | Tồn kho, số dư tài khoản, MRR cuối kỳ |
| **Non-additive** | Không được cộng trực tiếp | Tỷ lệ chuyển đổi, phần trăm lợi nhuận, giá đơn vị, AOV |
| **Distinct count** | Đếm tập khóa duy nhất; không cộng được qua các nhóm chồng nhau | Số khách khác nhau, số đơn phân biệt |

### 4.1. Additive vẫn có điều kiện

Doanh thu có thể SUM theo ngày, cửa hàng và sản phẩm nếu hàng fact **không bị nhân**, giao dịch cùng quy tắc ghi nhận và tiền tệ được xác định. Không có phép SUM hợp nghĩa giữa 100 USD và 100 VND nếu chưa quy đổi.

Quantity bán cũng cần đơn vị đo tương đương. Cộng 10 chiếc với 5 kg thành “15 sản phẩm” không phải một chỉ số có thể diễn giải mà không có chính sách quy đổi.

### 4.2. Semi-additive: tồn kho cuối ngày

| Ngày | Tồn cuối ngày |
|---|---:|
| 01/07 | 30 |
| 02/07 | 27 |
| 03/07 | 40 |

Tồn cuối kỳ là **40**, không phải 30 + 27 + 40 = 97. Có thể cộng tồn của nhiều kho **tại cùng ngày** nếu sản phẩm, đơn vị và phạm vi sở hữu thống nhất; không cộng các ảnh chụp qua ngày.

Một số đo “tồn bình quân” cần quy tắc lấy mẫu và trọng số thời gian. AVG(30, 27, 40) ≈ 32,33 chỉ có nghĩa trung bình ba mốc quan sát được, không chắc bằng tồn trung bình theo từng phút nếu dữ liệu thay đổi giữa các lần chụp.

### 4.3. Non-additive: tỷ lệ phải tính lại từ tử và mẫu

Giả sử khu vực A có 10 đơn, doanh thu 1 triệu; khu vực B có 90 đơn, doanh thu 4,5 triệu:

~~~text
AOV_A = 1.000.000 / 10 = 100.000
AOV_B = 4.500.000 / 90 = 50.000

AOV_toàn_bộ = 5.500.000 / 100 = 55.000
Không phải (100.000 + 50.000) / 2 = 75.000
~~~

Với tỷ suất lợi nhuận, tỷ lệ hủy, conversion, churn: **tổng tử số chia tổng mẫu số** sau khi cùng bộ lọc và cấp phân tích. Nếu chỉ lưu phần trăm đã làm tròn, sẽ mất thông tin cần để roll-up chính xác.

### 4.4. Đếm phân biệt không cộng qua các nhóm chồng nhau

Một khách mua ở hai cửa hàng sẽ xuất hiện trong customer count của cả hai. Tổng customer count từng cửa hàng có thể cao hơn customer count toàn công ty. Tương tự, một đơn gồm sản phẩm của hai danh mục sẽ bị đếm trong cả hai danh mục.

Nếu cần số khách/đơn duy nhất toàn bộ, phải **đếm lại ở cấp toàn bộ**, không cộng các distinct count đã nhóm. Các cấu trúc đếm xấp xỉ như sketch cũng cần nêu sai số và quy tắc hợp nhất.

## 5. Dimension và các thuộc tính mô tả

Dimension trả lời các câu hỏi **“theo gì?”**, **“ở đâu?”**, **“khi nào?”**, **“đối tượng thuộc nhóm nào?”**.

- **Date**: ngày, thứ, tháng, quý, năm, kỳ tài chính.
- **Product**: mã, tên, danh mục, ngành hàng, thương hiệu.
- **Customer**: mã khách, phân khúc, khu vực, loại tài khoản.
- **Store**: mã cửa hàng, thành phố, vùng, kênh bán.
- **Campaign**: chiến dịch, nhóm mục tiêu, kênh marketing.
- **Currency**: mã tiền và quy tắc biểu diễn/đơn vị.
- **Channel**: web, app, đối tác, cửa hàng.

### 5.1. Hierarchy và drill-down

~~~text
Ngành hàng → Danh mục → Nhóm → Sản phẩm
Năm → Quý → Tháng → Ngày
Quốc gia → Vùng → Thành phố → Cửa hàng
~~~

Thứ bậc hỗ trợ roll-up (SKU → nhóm) và drill-down (năm → tháng). Nhưng một phân cấp không nhất thiết là cây cố định: sản phẩm có thể thuộc nhiều danh mục, vùng bán có thể tổ chức lại, lịch tài chính không trùng lịch dương. Phải nêu rõ nếu cấp cha có thể thay đổi hoặc có nhiều cha.

### 5.2. Khóa tự nhiên và khóa thay thế

**Business key** nhận diện đối tượng trong nghiệp vụ, chẳng hạn product_id = P01.

**Surrogate key** nhận diện **một hàng dimension**, ví dụ product_key = 1001, đặc biệt quan trọng nếu dimension lưu nhiều phiên bản SCD Type 2:

~~~text
product_key | product_id | category   | valid period
1001        | P01        | Đồ ăn      | [01/01, 01/08)
1002        | P01        | Quà tặng   | [01/08, +∞)
~~~

Fact bán ngày 01/07 phải liên kết product_key 1001 nếu báo cáo dùng **phân loại tại ngày bán**. Không lấy product_key lớn nhất theo product_id để gắn cho mọi giao dịch lịch sử.

### 5.3. Conformed, role-playing và degenerate dimensions

**Conformed dimension** có ý nghĩa chung giữa nhiều fact: cùng Product/Date/Store giúp so sánh doanh thu, hàng trả và tồn kho theo cùng định nghĩa.

**Role-playing dimension** dùng cùng dim_date với các vai trò khác nhau: order_date_key, paid_date_key, shipped_date_key. Query cần alias riêng và chỉ rõ đang dùng mốc nào.

**Degenerate dimension** là định danh nghiệp vụ đặt ngay trong fact, như order_number, khi nó không cần bảng dimension mô tả riêng. Nó dùng đếm đơn, drill-through và đối soát, không phải số đo để SUM.

## 6. Quan hệ fact–dimension trong star schema

Mô hình hình sao (**star schema**) đặt fact ở trung tâm, các dimension mô tả ngữ cảnh của mỗi bản ghi.

~~~mermaid
erDiagram
    DIM_DATE ||--o{ FACT_SALES_LINE : "ngày bán"
    DIM_PRODUCT ||--o{ FACT_SALES_LINE : "phiên bản sản phẩm"
    DIM_STORE ||--o{ FACT_SALES_LINE : "cửa hàng"
    DIM_CUSTOMER ||--o{ FACT_SALES_LINE : "khách hàng"
    DIM_DATE {
        int date_key PK
        date calendar_date
        int calendar_year
        int calendar_month
    }
    DIM_PRODUCT {
        bigint product_key PK
        text product_id
        text category_name
        date valid_from
        date valid_to
    }
    DIM_STORE {
        bigint store_key PK
        text store_id
        text region_code
    }
    DIM_CUSTOMER {
        bigint customer_key PK
        text customer_id
        text segment_code
    }
    FACT_SALES_LINE {
        bigint sales_line_key PK
        text source_line_id UK
        text order_number
        int sale_date_key FK
        bigint product_key FK
        bigint store_key FK
        bigint customer_key FK
        int quantity
        decimal net_amount
        decimal cogs_amount
    }
~~~

Mỗi fact dòng bán gắn với một ngày, một phiên bản sản phẩm, một cửa hàng và nếu có thể một khách hàng. Một dimension có nhiều dòng fact tham chiếu nhưng mỗi fact phải chọn đúng phiên bản tương ứng.

### 6.1. Tại sao star schema thường được dùng?

Star schema ưu tiên truy vấn tổng hợp đọc nhiều hàng: fact giữ số đo và khóa; dimension giữ mô tả. Nó thường đơn giản hơn việc JOIN một mô hình OLTP được chuẩn hóa sâu với nhiều bảng quan hệ trung gian.

**Snowflake schema** chuẩn hóa tiếp dimension, ví dụ dim_product → dim_category → dim_department. Nó giảm trùng mô tả và có thể hữu ích khi hierarchy quản lý tập trung, nhưng tăng JOIN và yêu cầu thiết kế lịch sử giữa các cấp. Chọn star hoặc snowflake theo workload và cách quản trị chứ không theo một quy tắc tuyệt đối.

### 6.2. Quan hệ một-nhiều phải bảo toàn grain

Một dòng fact JOIN một dimension theo **primary/surrogate key duy nhất** thường không tăng số dòng. Ngược lại, JOIN với lịch sử dimension chỉ qua product_id mà không lọc khoảng hiệu lực sẽ nhân một giao dịch theo số phiên bản lịch sử.

Nếu một sản phẩm có ba phiên bản category, JOIN fact vào cả ba khiến SUM doanh thu tăng ba lần. Dùng product_key đã gắn đúng lúc ETL, hoặc temporal join có điều kiện ngày trong [from, to) và ràng buộc không chồng lấn.

## 7. Quy trình thiết kế mô hình phân tích

Một trình tự dễ kiểm chứng:

1. **Chọn quá trình nghiệp vụ**: bán hàng, hoàn hàng, tồn kho, truy cập, thanh toán.
2. **Nêu grain**: một dòng bán, một đơn, một SKU–kho–ngày, một session.
3. **Liệt kê các chiều** dùng lọc/nhóm ở grain đó.
4. **Liệt kê số đo** và tính chất tổng hợp: additive, semi-additive, non-additive.
5. **Xác định ràng buộc**: khóa nguồn duy nhất, FK, phiên bản dimension, hợp lệ tiền tệ/đơn vị, trạng thái giao dịch.
6. **Thiết kế quy trình ETL/ELT**: cách lấy phiên bản dimension, khử trùng, đến muộn, sửa hồi tố.
7. **Kiểm chứng** bằng tập dữ liệu nhỏ với kết quả biết trước rồi đối soát nguồn thật.
8. **Tối ưu vật lý** khi đã đo truy vấn và tần suất cập nhật.

Không bắt đầu bằng “bảng fact cần những cột nào?” mà bỏ qua grain. Những cột được chọn phải phù hợp với một đơn vị quan sát thống nhất.

## 8. Ví dụ tính số đo: ba dòng của hai đơn hàng

Giả sử ngày 01/07/2026 tại một cửa hàng, có ba dòng bán đã hoàn tất, tất cả bằng **VND**, số tiền không gồm thuế và chưa xét hoàn hàng:

| Dòng | Đơn | Sản phẩm | Danh mục | SL | Đơn giá | Gross | Giảm giá | Net | Giá vốn |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| L1 | O100 | P01 | Đồ ăn | 2 | 100.000 | 200.000 | 20.000 | 180.000 | 120.000 |
| L2 | O100 | P02 | Gia dụng | 1 | 80.000 | 80.000 | 0 | 80.000 | 50.000 |
| L3 | O101 | P01 | Đồ ăn | 1 | 100.000 | 100.000 | 10.000 | 90.000 | 60.000 |
| **Tổng** | **2 đơn** | | | **4** | | **380.000** | **30.000** | **350.000** | **230.000** |

~~~text
gross_amount = quantity × unit_price
net_amount = gross_amount - discount_amount
gross_profit = net_amount - cogs_amount

Tổng lượng bán     = 4
Tổng gross         = 380.000
Tổng giảm giá      = 30.000
Tổng net           = 350.000
Tổng giá vốn       = 230.000
Lợi nhuận gộp      = 120.000
Số đơn phân biệt   = 2
AOV                = 350.000 / 2 = 175.000
Net/đơn vị hàng    = 350.000 / 4 = 87.500
Tỷ suất LN gộp     = 120.000 / 350.000 ≈ 34,29%
~~~

### 8.1. Phân tích theo danh mục

| Danh mục | Lượng bán | Net sales | Giá vốn | Lợi nhuận gộp |
|---|---:|---:|---:|---:|
| Đồ ăn | 3 | 270.000 | 180.000 | 90.000 |
| Gia dụng | 1 | 80.000 | 50.000 | 30.000 |
| **Tổng** | **4** | **350.000** | **230.000** | **120.000** |

Danh mục Đồ ăn có 2 đơn, Gia dụng có 1 đơn. **Cộng số đơn theo danh mục thành 3 là sai** khi muốn tổng số đơn hệ thống; thực tế chỉ 2 đơn vì O100 chứa cả hai danh mục.

### 8.2. “Trung bình” phụ thuộc mẫu số

- Trung bình net theo dòng: 350.000 / 3 ≈ 116.666,67 VND/dòng.
- AOV: 350.000 / 2 = 175.000 VND/đơn.
- Giá bán thuần trung bình theo số đơn vị: 350.000 / 4 = 87.500 VND/đơn vị.

Ba chỉ số đều đúng với mẫu số tương ứng nhưng trả lời những câu hỏi khác nhau. Không dùng AVG(net_amount) trên fact dòng để báo AOV.

## 9. Lược đồ PostgreSQL: xây các dimension

Ví dụ này xây mô hình tối giản, với **dim_product có SCD Type 2**; store/customer là dimension chưa phiên bản hóa để giữ ví dụ tập trung. Nếu cần lịch sử khu vực cửa hàng hoặc phân khúc khách tại ngày bán, phải bổ sung SCD cho những dimension ấy.

### 9.1. Date dimension

~~~sql
CREATE TABLE dim_date (
    date_key         integer PRIMARY KEY, -- ví dụ 20260701
    calendar_date    date NOT NULL UNIQUE,
    calendar_year    integer NOT NULL,
    calendar_month   integer NOT NULL CHECK (calendar_month BETWEEN 1 AND 12),
    calendar_quarter integer NOT NULL CHECK (calendar_quarter BETWEEN 1 AND 4)
);
~~~

Cần một quy trình sinh chiều ngày và kiểm tra tính nhất quán giữa date_key, calendar_date, calendar_month. Kỳ tài chính hoặc ngày nghỉ có thể được thêm làm thuộc tính của dimension theo quy tắc tổ chức.

### 9.2. Product dimension với khoảng hiệu lực

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE dim_product (
    product_key   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id    text NOT NULL,
    product_name  text NOT NULL,
    category_name text NOT NULL,
    valid_from    date NOT NULL,
    valid_to      date,

    CONSTRAINT ck_product_period
        CHECK (valid_to IS NULL OR valid_from < valid_to),

    CONSTRAINT ex_product_version_no_overlap
        EXCLUDE USING gist (
            product_id WITH =,
            daterange(valid_from, valid_to, '[)') WITH &&
        )
);
~~~

Một product_id có thể có nhiều product_key khi category hoặc thuộc tính cần theo dõi thay đổi. Exclusion constraint cấm hai phiên bản cùng product_id có ngày hiệu lực giao nhau. Nó **không bảo đảm không có khoảng trống**; nếu cần độ bao phủ liên tục, phải kiểm tra thêm.

Mô hình này giả định mỗi sản phẩm chỉ có **một category chính** tại một ngày. Nếu nhiều category đồng thời là nghiệp vụ hợp lệ, cần bảng quan hệ nhiều-nhiều hoặc bridge, không đặt UNIQUE sai.

### 9.3. Store và customer dimensions

~~~sql
CREATE TABLE dim_store (
    store_key   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    store_id    text NOT NULL UNIQUE,
    store_name  text NOT NULL,
    region_code text NOT NULL
);

CREATE TABLE dim_customer (
    customer_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  text NOT NULL UNIQUE,
    segment_code text NOT NULL
);
~~~

Ở ví dụ, segment và region có giá trị hiện tại. Nếu tổ chức cần phân tích doanh thu theo **segment tại thời điểm bán**, nên SCD2 hóa dim_customer hoặc có một trường thuộc tính đã chốt trong fact. Không âm thầm dùng segment hiện tại để đặt nhãn là phân khúc lịch sử.

## 10. Fact dòng bán và ràng buộc ở grain

~~~sql
CREATE TABLE fact_sales_line (
    sales_line_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_line_id text NOT NULL UNIQUE,
    order_number   text NOT NULL, -- degenerate dimension
    sale_date_key  integer NOT NULL REFERENCES dim_date(date_key),
    product_key    bigint NOT NULL REFERENCES dim_product(product_key),
    store_key      bigint NOT NULL REFERENCES dim_store(store_key),
    customer_key   bigint REFERENCES dim_customer(customer_key),
    currency_code  char(3) NOT NULL,

    quantity       integer NOT NULL CHECK (quantity > 0),
    unit_price     numeric(18, 2) NOT NULL CHECK (unit_price >= 0),
    discount_amount numeric(18, 2) NOT NULL
                    CHECK (
                        discount_amount >= 0
                        AND discount_amount <= quantity * unit_price
                    ),
    cogs_amount    numeric(18, 2) NOT NULL CHECK (cogs_amount >= 0),

    gross_amount   numeric(18, 2)
                   GENERATED ALWAYS AS (quantity * unit_price) STORED,
    net_amount     numeric(18, 2)
                   GENERATED ALWAYS AS
                       (quantity * unit_price - discount_amount) STORED
);

CREATE INDEX ix_sales_date_product
    ON fact_sales_line (sale_date_key, product_key);
~~~

Giải thích:

- **source_line_id UNIQUE** chống nạp trùng một dòng bán; phải xác nhận ID nguồn thực sự duy nhất trong phạm vi hệ thống/tenant.
- **order_number** giúp COUNT DISTINCT đơn và drill-through, không phải measure.
- **product_key** gắn **phiên bản SCD2 đã được chọn** tại ngày bán.
- **customer_key nullable** biểu diễn trường hợp không xác định khách; báo cáo phải có quy tắc nhóm Unknown/Anonymous thay vì loại bỏ thầm lặng.
- **currency_code** là điều kiện bắt buộc khi cộng tiền của nhiều thị trường.
- Gross/net trong DDL này là công thức dòng giản lược. Thực tế có thể cần làm tròn theo tiền tệ, thuế, giảm giá nhiều cấp và số tiền đã chốt không được tính lại bằng công thức đã đổi.

**Fact này chỉ chứa dòng bán được ghi nhận.** Các đơn nháp hoặc hủy không được tự động xem là doanh thu; hoàn hàng cần quy tắc ghi nhận riêng, ví dụ fact returns theo ngày hoàn hoặc bút toán điều chỉnh.

### 10.1. Chọn product_key đúng ngày nghiệp vụ

~~~sql
SELECT product_key, category_name
FROM dim_product
WHERE product_id = 'P01'
  AND valid_from <= DATE '2026-07-01'
  AND (
      valid_to IS NULL
      OR DATE '2026-07-01' < valid_to
  );
~~~

Với dữ liệu SCD2 không overlap, truy vấn có tối đa một hàng. Nếu không có hàng, ETL phải có chính sách **quarantine**, dùng dimension Unknown được quản trị, hoặc xử lý dữ liệu đến muộn. Không mặc định lấy product_key lớn nhất hoặc phiên bản hiện tại.

## 11. SQL tổng hợp đúng và các phép tính dẫn xuất

### 11.1. Doanh thu, lượng bán, lợi nhuận theo tháng và category

~~~sql
SELECT
    d.calendar_year,
    d.calendar_month,
    p.category_name,
    SUM(f.quantity) AS units_sold,
    SUM(f.gross_amount) AS gross_sales,
    SUM(f.discount_amount) AS discounts,
    SUM(f.net_amount) AS net_sales,
    SUM(f.cogs_amount) AS cogs,
    SUM(f.net_amount - f.cogs_amount) AS gross_profit,
    ROUND(
        100 * SUM(f.net_amount - f.cogs_amount)
        / NULLIF(SUM(f.net_amount), 0), 2
    ) AS gross_margin_pct
FROM fact_sales_line f
JOIN dim_date d ON d.date_key = f.sale_date_key
JOIN dim_product p ON p.product_key = f.product_key
WHERE d.calendar_year = 2026
  AND d.calendar_month = 7
  AND f.currency_code = 'VND'
GROUP BY d.calendar_year, d.calendar_month, p.category_name
ORDER BY p.category_name;
~~~

\`gross_margin_pct\` phải được tính bằng **tổng lợi nhuận chia tổng doanh thu**, không AVG phần trăm của từng dòng. Phải xác định rõ profit ở đây chỉ là **gross profit = net sales - COGS**, chưa gồm chi phí marketing, vận hành hoặc thuế.

### 11.2. AOV từ số đơn phân biệt

~~~sql
SELECT
    d.calendar_year,
    d.calendar_month,
    SUM(f.net_amount) AS net_sales,
    COUNT(DISTINCT f.order_number) AS order_count,
    SUM(f.net_amount)
        / NULLIF(COUNT(DISTINCT f.order_number), 0) AS aov
FROM fact_sales_line f
JOIN dim_date d ON d.date_key = f.sale_date_key
WHERE d.calendar_year = 2026
  AND d.calendar_month = 7
  AND f.currency_code = 'VND'
GROUP BY d.calendar_year, d.calendar_month;
~~~

Công thức này giả định các dòng của một đơn thuộc cùng kỳ ngày ghi nhận và cùng loại tiền theo quy tắc báo cáo. Nếu đơn có nhiều lần ghi nhận vào các ngày khác nhau, phải định nghĩa lại mẫu số order count hoặc dùng bảng fact_order có grain đơn.

### 11.3. Trung bình theo số lượng hàng

~~~sql
SELECT
    SUM(net_amount)
        / NULLIF(SUM(quantity), 0) AS avg_net_unit_price
FROM fact_sales_line
WHERE currency_code = 'VND';
~~~

Đây là trung bình có trọng số theo đơn vị bán. AVG(unit_price) chỉ có thể trả cùng giá trị trong những trường hợp đặc biệt, không phải quy tắc chung.

## 12. SCD và ý nghĩa của phân tích “as-was” so với “as-is”

Giả sử P01 thuộc danh mục **Đồ ăn** đến trước 01/08/2026 rồi chuyển sang **Quà tặng** từ 01/08:

~~~text
P01, product_key 1001: [01/01, 01/08)  → Đồ ăn
P01, product_key 1002: [01/08, +∞)     → Quà tặng
~~~

**As-was:** xem doanh thu tháng 7 theo danh mục khi giao dịch xảy ra. L1 và L3 vẫn thuộc Đồ ăn.

**As-is:** xem toàn bộ doanh thu lịch sử theo danh mục hiện tại. Cũng các dòng L1, L3 có thể được quy lại Quà tặng.

Hai cách đều có thể hữu ích, nhưng phải **đặt tên báo cáo và chính sách rõ ràng**. Một fact gắn product_key lịch sử không có nghĩa mọi truy vấn buộc phải as-was; cũng không được đổi sang as-is mà không thông báo.

### 12.1. Các kiểu Slowly Changing Dimension

| Kiểu | Cơ chế | Khi nên dùng |
|---|---|---|
| **Type 0** | Giữ nguyên giá trị ban đầu | Thuộc tính cần bất biến |
| **Type 1** | Ghi đè giá trị | Sửa chính tả, không cần lịch sử giá trị cũ |
| **Type 2** | Tạo hàng mới với khoảng hiệu lực | Cần phân tích theo trạng thái đã có hiệu lực tại ngày giao dịch |
| **Type 3** | Lưu giá trị hiện tại và một số giá trị trước | Nhu cầu so sánh lịch sử giới hạn |
| **Bridge/temporal relation** | Quan hệ nhiều-nhiều, có thể có hiệu lực thời gian | Sản phẩm đa danh mục, khách nhiều phân khúc hợp lệ |

SCD Type 2 theo valid time **chưa tự động là bitemporal**. Nếu warehouse sửa lại ngày hiệu lực trong quá khứ và mất phiên bản kiến thức cũ, không thể trả lời “tại thời điểm K warehouse từng coi sản phẩm thuộc nhóm nào?”. Khi yêu cầu đó quan trọng, cần known/system time hoặc snapshot báo cáo/revision.

### 12.2. Late-arriving dimension và fact

Giao dịch phát sinh 28/07 nhưng tới kho phân tích ngày 02/08 phải được đặt vào **business date** theo metric contract, không tùy tiện vào tháng 8 vì timestamp nạp. Tương tự, một thay đổi category có hiệu lực từ 01/08 nhưng được nhập ngày 03/08 đòi hỏi cơ chế gắn lại phiên bản dimension của fact ngày 01/08 nếu cần.

Các lựa chọn: giữ fact chờ dimension, dùng hàng Unknown sau đó backfill có kiểm soát, hoặc phát lại partition/kỳ bị ảnh hưởng. Phải có đối soát để không mất hoặc đếm đôi giao dịch.

## 13. Quan hệ nhiều-nhiều và bẫy fanout

Một dòng bán có thể chịu ảnh hưởng của nhiều chiến dịch. Giả sử dòng L1 có doanh thu thuần **100.000 VND** và được liên kết tới Campaign A, Campaign B.

~~~text
fact_sales_line:
L1 → net_amount = 100.000

bridge:
L1 → Campaign A
L1 → Campaign B
~~~

JOIN trực tiếp rồi SUM(net_amount) sẽ thành **200.000**. Đây là **fanout**.

### 13.1. Hai định nghĩa cần phân biệt

**Influenced/touched revenue**: mỗi campaign được ghi nhận “chạm” doanh thu 100.000. Khi đó A = 100.000 và B = 100.000, nhưng **không được cộng** hai nhóm để gọi đó là tổng doanh thu.

**Attributed revenue**: phân bổ doanh thu theo trọng số, ví dụ A 60%, B 40%:

~~~text
A: 100.000 × 0,60 = 60.000
B: 100.000 × 0,40 = 40.000
Tổng phân bổ = 100.000
~~~

Trọng số phải xuất phát từ chính sách attribution được phê duyệt, không phải số ngẫu nhiên do kỹ thuật chọn.

### 13.2. Bridge table và phép tính phân bổ

~~~sql
CREATE TABLE dim_campaign (
    campaign_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_code text NOT NULL UNIQUE,
    campaign_name text NOT NULL
);

CREATE TABLE bridge_sales_line_campaign (
    sales_line_key bigint NOT NULL
                   REFERENCES fact_sales_line(sales_line_key),
    campaign_key   bigint NOT NULL
                   REFERENCES dim_campaign(campaign_key),
    attribution_weight numeric(8, 6) NOT NULL
                        CHECK (
                            attribution_weight >= 0
                            AND attribution_weight <= 1
                        ),
    PRIMARY KEY (sales_line_key, campaign_key)
);

SELECT
    c.campaign_name,
    SUM(f.net_amount * b.attribution_weight) AS attributed_net_sales
FROM fact_sales_line f
JOIN bridge_sales_line_campaign b
  ON b.sales_line_key = f.sales_line_key
JOIN dim_campaign c
  ON c.campaign_key = b.campaign_key
WHERE f.currency_code = 'VND'
GROUP BY c.campaign_name;
~~~

Nếu yêu cầu **toàn bộ doanh thu phải được phân bổ**, tổng trọng số của từng dòng phải bằng 1 (có thể gồm Campaign Unattributed). Một CHECK trên từng hàng **không kiểm soát tổng trọng số của nhiều hàng**; cần transaction validation hoặc kiểm tra ETL theo nhóm sales_line_key.

Nếu chiến dịch có hiệu lực theo thời gian, cần kiểm tra cầu nối có đúng khoảng ngày đối với dòng bán hay không. Không JOIN số đo tháng 7 vào mapping campaign của tháng 9 ngoài chủ đích.

## 14. Nhiều fact khác grain: aggregate rồi mới kết hợp

Giả sử cần báo cáo theo ngày/SKU:

- Số lượng bán từ **fact_sales_line** (nhiều dòng/ngày/SKU).
- Tồn cuối ngày từ **fact_inventory_daily** (một dòng/ngày/SKU/kho).

Nếu JOIN trực tiếp fact bán vào fact tồn theo ngày và SKU, một hàng tồn có thể bị lặp theo số dòng bán. Tồn cuối kỳ bị nhân.

Nên **tổng hợp từng fact về cùng cấp phân tích trước**, rồi JOIN hai tập tổng:

~~~sql
WITH sales_by_day_product AS (
    SELECT
        sale_date_key AS date_key,
        product_key,
        SUM(quantity) AS units_sold
    FROM fact_sales_line
    GROUP BY sale_date_key, product_key
),
inventory_by_day_product AS (
    SELECT
        snapshot_date_key AS date_key,
        product_key,
        SUM(closing_qty) AS closing_qty
    FROM fact_inventory_daily
    GROUP BY snapshot_date_key, product_key
)
SELECT
    COALESCE(s.date_key, i.date_key) AS date_key,
    COALESCE(s.product_key, i.product_key) AS product_key,
    s.units_sold,
    i.closing_qty
FROM sales_by_day_product s
FULL JOIN inventory_by_day_product i
  ON i.date_key = s.date_key
 AND i.product_key = s.product_key;
~~~

**Lưu ý:** fact_inventory_daily ở đây là bảng minh họa cần tạo riêng, không thuộc DDL đã tạo ở phần 9–10. Giả định mỗi kho có một closing_qty hợp lệ theo ngày/SKU và các giá trị cùng đơn vị; cần chọn revision được chấp nhận nếu ảnh chụp được công bố lại.

Khi cần báo cáo theo category, cả hai fact phải dùng phân loại thống nhất hoặc giải thích vì sao sales được tính **as-was** còn inventory dùng category hiện tại. Đây là vai trò của **conformed dimension**.

### 14.1. Không tạo tỷ lệ từ dữ liệu khác mẫu số

Conversion rate có thể cần số phiên mua thành công / số phiên truy cập hợp lệ. Hai nguồn này có grain và khóa khác nhau; phải định nghĩa session, attribution, thời gian chờ và việc một session phát sinh nhiều đơn. Không lấy số dòng order làm mẫu số cho conversion vì mỗi đơn có thể có nhiều dòng.

## 15. Các loại fact và số đo tương ứng

### 15.1. Transaction fact

Mỗi hàng là một giao dịch hoặc dòng sự kiện được ghi nhận: dòng bán, hoàn hàng, thanh toán. Số lượng và tiền thường additive qua nhiều chiều. Cần xác định trạng thái nào đủ điều kiện ghi nhận, xử lý retry/dedup và thời điểm ghi doanh thu.

### 15.2. Periodic snapshot fact

Mỗi hàng là trạng thái tại một kỳ, ví dụ SKU–kho–ngày:

~~~text
(date_key, warehouse_key, product_key) → closing_qty
~~~

Nếu có nhiều revision của cùng ngày, phải chọn **phiên bản được chấp nhận**; không cộng các revision như các trạng thái độc lập.

Tồn kho là semi-additive: cộng theo SKU và kho tại một ngày khi thích hợp, **không SUM qua ngày** để ra tồn cuối tháng.

### 15.3. Accumulating snapshot fact

Mỗi hàng là một quy trình với các mốc thay đổi:

~~~text
order_id
created_date_key
paid_date_key
shipped_date_key
delivered_date_key
fulfillment_days
~~~

Hàng có thể được cập nhật khi quy trình tiến triển. Nếu cần tái dựng trạng thái quy trình trong quá khứ, phải có lịch sử phiên bản/event riêng; một accumulating snapshot chỉ giữ trạng thái cuối không đủ.

### 15.4. Factless fact

Bảng chỉ lưu một sự kiện/quan hệ, không có số tiền:

~~~text
fact_attendance:
(date_key, student_key, class_key) → một lần điểm danh
~~~

COUNT(*) hoặc COUNT DISTINCT tạo số đo từ sự tồn tại của hàng. Nhưng cần phân biệt ghi nhận tham gia lớp với trạng thái đăng ký có hiệu lực trong nhiều ngày; grain và ngữ nghĩa khác nhau.

## 16. Metric contract và semantic layer

Để hai dashboard không tính cùng tên chỉ số ra hai số khác nhau, nên chuẩn hóa định nghĩa trong **metric catalog/semantic layer**.

| Thuộc tính | Ví dụ net sales |
|---|---|
| Tên metric | net_sales_amount |
| Định nghĩa | Tổng doanh thu bán sau giảm giá tại dòng |
| Grain | Dòng bán đã hoàn tất |
| Công thức | SUM(quantity × unit_price − discount_amount) |
| Ngày nghiệp vụ | sale_date_key |
| Đơn vị | VND trong view này |
| Thuế | Không bao gồm |
| Returns | Không trừ trực tiếp trong metric; có metric net-after-returns riêng |
| Dimension | Date, Product SCD2, Store, Customer |
| Unknown | Quy tắc khách không nhận diện, product mapping thiếu |
| SLA dữ liệu | Độ trễ nạp và cách xử lý late facts |
| Đối soát | Tổng với sổ bán cùng kỳ và phạm vi |

Đối với margin percentage, metric contract nên ghi rõ:

~~~text
gross_margin_pct =
   100 × SUM(net_amount - cogs_amount)
         / NULLIF(SUM(net_amount), 0)
~~~

Không định nghĩa AVG(line_margin_pct) nếu mục tiêu là tỷ suất lợi nhuận toàn nhóm.

### 16.1. Khác phiên bản định nghĩa là khác metric

Nếu trước đây net sales không trừ returns nhưng nay tổ chức muốn metric sau returns, không nên đổi công thức âm thầm rồi ghi đè mọi báo cáo đã công bố. Cần phiên bản định nghĩa, mốc áp dụng, người duyệt, cách backfill/revision và tên hiển thị không gây nhầm.

Semantic layer là **hợp đồng giữa kỹ thuật và nghiệp vụ**, không chỉ là nơi cất công thức SQL.

## 17. Kiểm thử tính đúng và phát hiện nhân hàng

| Kiểm tra | Kỳ vọng |
|---|---|
| Một source_line_id chỉ có một dòng fact | Khóa UNIQUE và đối soát nguồn |
| Fact có product_key phù hợp ngày bán | Mapping SCD2 theo khoảng hiệu lực |
| Một product_id không có hai phiên bản SCD2 chồng nhau | Ràng buộc exclusion hoặc DQ test |
| JOIN fact với dimension không nhân bản fact | Phía dimension duy nhất theo key |
| Tổng discount không vượt tổng gross ở cấp dòng theo hợp đồng | CHECK hoặc kiểm thử |
| Net, gross, COGS cùng tiền tệ và đơn vị | Data contract và kiểm tra mã tiền |
| COUNT DISTINCT order không cộng qua nhóm category | Tính lại ở cấp toàn bộ |
| Bridge campaign có tổng trọng số đúng | Transaction validation/đối soát |
| Fact snapshot chỉ chọn một revision ở kỳ | Unique business grain + revision policy |
| Dữ liệu đến muộn được tính theo ngày nghiệp vụ | Kiểm tra event time với load time |
| Tỷ lệ được tổng hợp từ tử/mẫu đúng | So sánh roll-up với tính lại từ fact |

### 17.1. SQL kiểm tra duplicate

~~~sql
SELECT source_line_id, COUNT(*) AS number_of_rows
FROM fact_sales_line
GROUP BY source_line_id
HAVING COUNT(*) > 1;
~~~

Với DDL có UNIQUE, kết quả luôn rỗng; truy vấn hữu ích hơn ở bảng staging chưa bật ràng buộc.

### 17.2. Minh họa fanout từ bridge

~~~sql
WITH source_total AS (
    SELECT SUM(net_amount) AS net
    FROM fact_sales_line
),
naive_join_total AS (
    SELECT SUM(f.net_amount) AS net
    FROM fact_sales_line f
    JOIN bridge_sales_line_campaign b
      ON b.sales_line_key = f.sales_line_key
)
SELECT
    s.net AS original_net,
    j.net AS incorrectly_joined_net
FROM source_total s CROSS JOIN naive_join_total j;
~~~

Đây **không phải truy vấn doanh thu dùng cho dashboard**. Nó cho thấy JOIN có thể làm tăng tổng khi một dòng có nhiều campaign, hoặc làm giảm tổng nếu INNER JOIN loại các dòng chưa có campaign.

### 17.3. Ma trận kiểm thử số mẫu

| Chỉ số | Giá trị kỳ vọng |
|---|---:|
| Số dòng fact | 3 |
| Số đơn phân biệt | 2 |
| Tổng quantity | 4 |
| Gross | 380.000 VND |
| Discount | 30.000 VND |
| Net | 350.000 VND |
| COGS | 230.000 VND |
| Gross profit | 120.000 VND |
| AOV | 175.000 VND/đơn |
| Net/đơn vị hàng | 87.500 VND |
| Margin rate | Khoảng 34,29% |
| Net của Đồ ăn | 270.000 VND |
| Net của Gia dụng | 80.000 VND |

## 18. Hiệu năng, quản trị vật lý và lựa chọn công nghệ

Trong OLTP, bảng được chuẩn hóa phục vụ thao tác đúng và cập nhật thường xuyên. Trong OLAP, fact/dimension phục vụ truy vấn đọc lớn, lọc theo chiều và tổng hợp. Có thể duy trì mô hình OLTP làm **nguồn giao dịch**, rồi ETL/ELT sang star schema để BI.

### 18.1. Index, partition và aggregate table

Các fact lớn thường lọc theo ngày và dimension key. Cần đo bằng EXPLAIN (ANALYZE, BUFFERS), xem tốc độ scan, độ chọn lọc, chi phí ghi và tình trạng thống kê trước khi tạo nhiều index. Partition theo thời gian có thể hỗ trợ pruning và retention nếu truy vấn thường lọc ngày; không áp dụng máy móc khi workload chủ yếu theo khách hàng hoặc khi làm mất khả năng ràng buộc uniqueness toàn cục.

**Aggregate table** theo tháng–danh mục–cửa hàng có thể tăng tốc dashboard. Nhưng nếu lưu order_count riêng cho từng danh mục, **không SUM các distinct count này** để ra số đơn toàn hệ thống khi đơn có nhiều category. Cần tạo các mức tổng có ngữ nghĩa riêng hoặc tính lại từ grain đủ chi tiết.

### 18.2. Columnar warehouse

Kho dữ liệu dạng cột giúp scan một số cột metric và dimension trên lượng fact lớn. Tuy nhiên, engine nhanh không sửa được sai lầm grain, JOIN many-to-many, sai tiền tệ hay sai ngày hiệu lực.

### 18.3. Document, graph và phân tích

- **Document** có thể lưu một đơn kèm mảng items; để tính doanh thu theo category, phải tách items về grain dòng và tránh nhân chi phí cấp đơn.
- **Graph** phù hợp phân tích đường đi, nhóm và quan hệ đa cấp; khi một nút thuộc nhiều nhóm, cần định nghĩa đếm lặp hay phân bổ.
- **Relational/star** phù hợp nhiều chỉ số cộng theo chiều với khóa và quan hệ rõ.
- **Analytical/lakehouse** kết hợp nguồn event, CDC, transaction và snapshot; càng nhiều nguồn càng cần conformed dimensions, metric catalog và đối soát.

Tiêu chí chọn mô hình là **khả năng duy trì ngữ nghĩa, ràng buộc và truy vấn được yêu cầu**, không chỉ tên công nghệ.

## 19. Bài thực hành: dashboard bán, tồn và chiến dịch

Một chuỗi cửa hàng yêu cầu dashboard:

> Theo ngày, vùng, danh mục và chiến dịch, hiển thị doanh thu thuần, lượng bán, tồn cuối ngày, số đơn phân biệt, AOV, tỷ suất lợi nhuận gộp và doanh thu phân bổ cho chiến dịch. Một sản phẩm có thể đổi danh mục; một đơn có thể được nhiều chiến dịch tác động.

Hãy thực hiện:

1. **Nêu grain** của fact bán và fact tồn, giải thích vì sao không gộp các số đo khác grain vào một hàng tùy ý.
2. **Chọn dimension** Date, Product, Store, Customer và Campaign; xác định dimension nào là conformed giữa các fact.
3. **Phân loại số đo** quantity/net/cogs, closing_qty, AOV, gross margin, distinct orders.
4. **Chọn khóa** source_line_id, product_key SCD2, store_key và surrogate key cho từng phiên bản dimension.
5. **Xử lý campaign nhiều-nhiều**: so sánh influenced revenue và attributed revenue; đề xuất bridge với weight tổng bằng 1 nếu cần phân bổ.
6. **Viết temporal mapping** để giao dịch ngày 01/07 gắn category tại ngày đó.
7. **Viết query** doanh thu theo category; tính margin bằng tổng tử/mẫu.
8. **Tính AOV** từ 2 đơn O100/O101 với net 350.000, kết quả 175.000 VND; giải thích vì sao COUNT(*) = 3 sai.
9. **Chọn tồn cuối kỳ** từ fact SKU–kho–ngày, không cộng tồn qua ngày.
10. **Drill-across** hai fact tại grain ngày–sản phẩm sau khi aggregate riêng từng fact.
11. **Thử sửa hồi tố** khi Product P01 đổi category từ 01/08 nhưng quyết định tới warehouse ngày 03/08. Phân biệt as-was, as-is và revision đã xuất bản.
12. **Kiểm thử** trùng source line, orphan dimension, overlap SCD2, bridge fanout và đơn có sản phẩm nhiều danh mục.

**Tiêu chí đạt:** mỗi metric có công thức, đơn vị và bộ lọc; mỗi fact có grain rõ; mỗi quan hệ JOIN không làm thay đổi số đo ngoài chủ đích; các chỉ số dẫn xuất có mẫu số đúng; kiểm thử tổng tiền khớp dữ liệu nguồn.

## 20. Checklist thiết kế số đo, chiều phân tích và quan hệ

- **Câu hỏi nghiệp vụ:** báo cáo cần trả lời gì, ở kỳ và cấp chi tiết nào?
- **Grain:** một hàng fact biểu diễn chính xác cái gì?
- **Số đo:** công thức, đơn vị, trạng thái hợp lệ, returns/thuế/tiền tệ đã rõ chưa?
- **Tính cộng:** additive, semi-additive, non-additive và distinct count có quy tắc roll-up đúng không?
- **Chiều:** khóa nghiệp vụ, surrogate key, mô tả và hierarchy được xác định chưa?
- **Quan hệ:** fact JOIN dimension có giữ nguyên grain không; many-to-many có bridge, trọng số hoặc metric riêng không?
- **Thời gian:** date_key dùng ngày nghiệp vụ nào; role-playing dimensions và SCD đã đúng chưa?
- **Lịch sử:** as-was/as-is, late-arriving facts, Type 1/2 và correction hồi tố đã thống nhất chưa?
- **Nhiều fact:** sales, returns, inventory và sessions được aggregate độc lập trước khi kết hợp chưa?
- **Đối soát:** kiểm tra duplicate, orphan, overlap, tổng tiền, số đơn và quyền truy vấn dữ liệu chưa?
- **Semantic layer:** các nhóm có dùng cùng định nghĩa metric và version thay đổi không?
- **Hiệu năng:** index, partition, aggregate và warehouse được đo bằng workload thực tế chưa?

**Kết luận:** số đo trả lời **“bao nhiêu?”**, chiều phân tích trả lời **“theo góc nhìn nào?”**, grain trả lời **“mỗi hàng đại diện cho điều gì?”**, còn quan hệ xác định **“những số đo đó gắn với phiên bản chiều nào, với bao nhiêu liên kết?”**. Chỉ khi bốn phần nhất quán, phép SUM, COUNT DISTINCT hay GROUP BY mới tạo ra con số vừa nhanh vừa có thể giải thích và kiểm chứng.
