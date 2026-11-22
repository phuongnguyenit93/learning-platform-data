# Lược đồ hình sao, bông tuyết và nhiều bảng dữ kiện dùng chung chiều

Một hệ thống bán lẻ có thể trả lời nhanh câu hỏi **“Đơn hàng này gồm những sản phẩm nào?”** bằng mô hình quan hệ phục vụ giao dịch. Nhưng các câu hỏi phân tích khác hẳn:

- Doanh thu theo **ngày, sản phẩm và cửa hàng** là bao nhiêu?
- Số lượng hàng bị trả lại theo từng danh mục thay đổi ra sao?
- Tồn kho cuối ngày ở mỗi cửa hàng có đủ so với tốc độ bán không?
- Khi kết hợp dữ kiện bán hàng, trả hàng và tồn kho, làm sao không **nhân đôi doanh thu** hoặc **cộng tồn kho sai theo thời gian**?

Để giải quyết những câu hỏi đó, mô hình dữ liệu phân tích thường dùng **bảng dữ kiện (fact table)**, **bảng chiều (dimension table)** và ba kiểu tổ chức đáng chú ý:

1. **Lược đồ hình sao (star schema):** bảng dữ kiện ở trung tâm, các chiều mô tả nối trực tiếp vào fact, thường được làm phẳng để giảm số bước JOIN.
2. **Lược đồ bông tuyết (snowflake schema):** một hoặc nhiều chiều được chuẩn hóa thành các bảng cấp nhỏ hơn, ví dụ Product → Category → CategoryGroup.
3. **Nhiều bảng dữ kiện dùng chung chiều (fact constellation / galaxy schema):** nhiều quy trình nghiệp vụ có các fact riêng, nhưng dùng những chiều thống nhất như Date, Product, Store.

Bài này thuộc chương **Mô hình phân tích** của module **DATABASE_DATA_MODELING**. Mục tiêu là chuyển yêu cầu báo cáo thành mô hình có **mức hạt (grain)**, khóa, ràng buộc, lịch sử và quy tắc tổng hợp rõ ràng; đồng thời biết cách đánh đổi giữa mô hình quan hệ giao dịch, document, đồ thị và kho dữ liệu phân tích. Các ví dụ SQL minh họa trên PostgreSQL, không đại diện cho mọi tính năng tối ưu của các kho phân tích chuyên dụng.

> **Điểm xuất phát:** Trước khi vẽ hình sao, hãy viết thành lời “một hàng của fact đại diện cho điều gì”. Nếu không xác định được grain, mọi phép JOIN, đếm và cộng phía sau đều có nguy cơ sai, dù truy vấn chạy rất nhanh.

## 1. Nền tảng: fact, dimension và mức hạt

### 1.1. Bảng dữ kiện (fact)

Một **fact** ghi lại một **sự kiện**, **trạng thái đo được** hoặc **tiến trình** tại một mức chi tiết được xác định. Nó thường chứa:

- Các khóa tham chiếu tới chiều: ngày, sản phẩm, cửa hàng, khách hàng.
- Các **đại lượng (measures)**: số lượng bán, tiền hàng, tiền hoàn, lượng tồn.
- Định danh giao dịch để truy vết; ví dụ order_id có thể là **degenerate dimension** khi chỉ cần một định danh nghiệp vụ mà không cần bảng chiều Order đầy đủ.

Ví dụ, một hàng **fact_sales_line** có thể nghĩa là:

> “Một dòng hàng được ghi nhận bán thành công trong một đơn hàng, tại một thời điểm, với một sản phẩm, cửa hàng và khách hàng nhất định.”

Một hàng của fact này **không** đại diện cho “một đơn hàng” vì một đơn có nhiều dòng, và cũng không đại diện cho “doanh thu của cả một ngày” vì nhiều dòng cùng ngày có thể tồn tại.

### 1.2. Bảng chiều (dimension)

Một **dimension** cung cấp ngữ cảnh để **lọc, nhóm, phân cấp và đặt nhãn** cho các fact:

- **DimDate:** ngày, tháng, quý, năm, ngày trong tuần.
- **DimProduct:** mã sản phẩm, tên, thương hiệu, danh mục, nhóm danh mục.
- **DimStore:** mã cửa hàng, thành phố, khu vực kinh doanh.
- **DimCustomer:** phân khúc, nhóm khách, thị trường; có thể có yêu cầu bảo vệ dữ liệu cá nhân.

Dimension thường có **khóa thay thế (surrogate key)** độc lập với mã nghiệp vụ. Ví dụ, một sản phẩm mã P-001 có thể mang nhiều product_key khác nhau qua các phiên bản lịch sử nếu dùng **Slowly Changing Dimension Type 2 (SCD2)**.

### 1.3. Grain là hợp đồng của fact

| Fact | Một hàng đại diện | Ví dụ khóa chiều | Đại lượng điển hình |
| --- | --- | --- | --- |
| Bán hàng | **Một dòng hàng bán thành công** | sales_date, product, store, customer | quantity, net_sales_amount |
| Trả hàng | **Một dòng/sự kiện trả hàng** | return_date, product, store | returned_quantity, refund_amount |
| Tồn kho ngày | **Một sản phẩm tại một cửa hàng vào cuối một ngày** | snapshot_date, product, store | units_on_hand |
| Mục tiêu doanh thu | **Một cửa hàng trong một tháng** | target_month, store | target_amount |
| Tiến trình giao đơn | **Một đơn hàng qua các cột mốc giao vận** | order_date, ship_date, delivery_date | số ngày xử lý, trạng thái cuối |

Không thể ghép các đại lượng ở các mức hạt khác nhau như thể chúng có cùng ý nghĩa. Một fact tồn kho cuối ngày không phải sự kiện bán hàng. Một fact mục tiêu tháng không được nhân lên theo số dòng đơn hàng của tháng.

### 1.4. Phân biệt ba kiểu fact thông dụng

- **Transaction fact:** mỗi lần xảy ra một giao dịch/sự kiện tạo hàng mới, ví dụ một dòng bán hoặc một lần hoàn tiền. Phù hợp cộng qua nhiều ngày nếu các measure là additive và không có vấn đề tiền tệ/trùng sự kiện.
- **Periodic snapshot fact:** chụp trạng thái theo chu kỳ, ví dụ tồn kho cuối ngày. Các số đo có thể **cộng theo sản phẩm/cửa hàng ở cùng thời điểm** nhưng thường **không cộng qua nhiều ngày**.
- **Accumulating snapshot fact:** một hàng cho một quá trình có điểm bắt đầu và hoàn thành, cập nhật các mốc như ordered_at, packed_at, shipped_at, delivered_at. Không nhầm nó với fact sự kiện: mỗi lần cập nhật một mốc không nên bị đếm thành một đơn hàng mới.

Trong mô hình phân tích, **số lượng hàng** không phải KPI. KPI phụ thuộc grain, định nghĩa chỉ tiêu, cách lọc sự kiện và cách tổng hợp.

## 2. Lược đồ hình sao (star schema)

### 2.1. Hình dạng và ngữ nghĩa

Ví dụ một quy trình bán hàng:

~~~mermaid
flowchart LR
    D["DimDate"] --> F["FactSalesLine"]
    P["DimProduct"] --> F
    S["DimStore"] --> F
    C["DimCustomer"] --> F
~~~

Các dimension nằm xung quanh bảng fact như các cánh của ngôi sao. Fact lưu khóa để truy đến từng chiều, thay vì lặp toàn bộ tên sản phẩm, tên cửa hàng và phân khúc khách trên mỗi dòng giao dịch.

Ví dụ ở mức khái niệm:

~~~text
FactSalesLine(
    sales_line_key,
    order_id,
    line_no,
    sales_date_key,
    product_key,
    store_key,
    customer_key,
    quantity,
    gross_amount,
    discount_amount,
    net_sales_amount
)

DimProduct(
    product_key,
    product_code,
    product_name,
    brand_name,
    category_name,
    category_group_name,
    ...
)
~~~

Điểm **“hình sao”** không nằm ở việc SQL có bốn JOIN hay năm JOIN, mà ở việc **fact mang khóa chiều** và **chiều diễn đạt ngữ cảnh phân tích**. Dimension có thể chứa nhiều thuộc tính mô tả, các nhóm phân cấp và lịch sử.

### 2.2. Vì sao thường làm phẳng dimension?

Nếu mỗi Product có Brand, Category và CategoryGroup, ta có thể lưu những tên mô tả trong cùng DimProduct để một truy vấn doanh thu theo category chỉ cần:

~~~sql
SELECT p.category_name,
       SUM(f.net_sales_amount) AS net_sales
FROM fact_sales_line AS f
JOIN dim_product AS p ON p.product_key = f.product_key
GROUP BY p.category_name;
~~~

Đây là ví dụ mô tả hình dạng truy vấn; DDL đầy đủ ở phần sau.

**Ưu điểm thường gặp:**

- Dễ hiểu với người dùng BI: fact bán hàng nối trực tiếp tới chiều sản phẩm.
- Truy vấn chọn thuộc tính phân loại không phải JOIN tiếp qua nhiều bảng cấp.
- Có thể lưu **ảnh chụp thuộc tính lịch sử** của Product trong một phiên bản dimension.
- Tối ưu đọc cột/scan/join trong nhiều hệ kho dữ liệu khi kích thước fact rất lớn.

**Đánh đổi:**

- Tên Category/Brand có thể lặp lại trong nhiều hàng DimProduct.
- Việc đổi cách phân loại cần quy tắc lịch sử hoặc cập nhật đúng phạm vi.
- Dimension rộng có thể tăng dung lượng và chi phí bảo trì.
- Không phải mọi thuộc tính lặp trong chiều đều là vấn đề đáng chuẩn hóa: mục tiêu ở đây là **tối ưu truy vấn phân tích có kiểm soát**, không đơn thuần đạt mức chuẩn hóa cao nhất.

### 2.3. Hình sao không có nghĩa bỏ toàn vẹn dữ liệu

Một fact phải tham chiếu chiều hợp lệ. Nếu kho dữ liệu sử dụng khóa ngoại để kiểm soát, mỗi product_key phải tồn tại trong DimProduct. Một số nền tảng phân tích chỉ dùng FK như **metadata** hoặc không cưỡng chế đầy đủ; khi đó pipeline và kiểm thử dữ liệu phải đảm nhận trách nhiệm đối chiếu.

Trường hợp nguồn chưa xác định được Product tại lúc nạp fact cần chính sách rõ:

- Tạm ngừng nhận fact và xử lý dữ liệu nguồn.
- Tạo một bản ghi chiều **Unknown/Not yet identified** có khóa thay thế riêng.
- Nạp lại khi chiều đến muộn (*late-arriving dimension*).

**Không nên âm thầm bỏ fact** chỉ vì chưa tìm thấy chiều, đặc biệt khi đó là giao dịch tài chính cần đối soát.

## 3. Lược đồ bông tuyết (snowflake schema)

### 3.1. Chuẩn hóa một phần hoặc toàn bộ chiều

Thay vì đặt mọi cấp phân loại trong DimProduct, ta tách:

~~~mermaid
flowchart LR
    F["FactSalesLine"] --> P["DimProduct"]
    P --> B["DimBrand"]
    P --> C["DimCategory"]
    C --> G["DimCategoryGroup"]
    F --> D["DimDate"]
    F --> S["DimStore"]
    F --> U["DimCustomer"]
~~~

Theo cách này, một Brand/Category có thể có một hàng riêng được nhiều Product tham chiếu.

**Khác biệt với hình sao:** Fact vẫn giữ **cùng grain** và các measure. Việc snowflake chủ yếu thay đổi **cách tổ chức mô tả trong các dimension**, chứ không tự làm fact “chuẩn hóa” về một mức hạt khác.

### 3.2. Ví dụ lược đồ chiều dạng bông tuyết

Đây là **phương án thay thế** cho DimProduct được làm phẳng, không phải yêu cầu triển khai song song cả hai phương án:

~~~sql
CREATE TABLE dim_category_groups_sf (
    category_group_key BIGINT PRIMARY KEY,
    category_group_code TEXT NOT NULL UNIQUE,
    category_group_name TEXT NOT NULL
);

CREATE TABLE dim_categories_sf (
    category_key BIGINT PRIMARY KEY,
    category_code TEXT NOT NULL UNIQUE,
    category_name TEXT NOT NULL,
    category_group_key BIGINT NOT NULL
        REFERENCES dim_category_groups_sf(category_group_key)
);

CREATE TABLE dim_brands_sf (
    brand_key BIGINT PRIMARY KEY,
    brand_code TEXT NOT NULL UNIQUE,
    brand_name TEXT NOT NULL
);

CREATE TABLE dim_products_sf (
    product_key BIGINT PRIMARY KEY,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category_key BIGINT NOT NULL
        REFERENCES dim_categories_sf(category_key),
    brand_key BIGINT NOT NULL
        REFERENCES dim_brands_sf(brand_key)
);
~~~

Nếu fact dùng DimProducts phiên bản bông tuyết, truy vấn doanh thu theo nhóm category có dạng:

~~~sql
-- Giả định fact_sales_line.product_key tham chiếu dim_products_sf.
SELECT cg.category_group_name,
       SUM(f.net_sales_amount) AS net_sales
FROM fact_sales_line AS f
JOIN dim_products_sf AS p ON p.product_key = f.product_key
JOIN dim_categories_sf AS c ON c.category_key = p.category_key
JOIN dim_category_groups_sf AS cg
  ON cg.category_group_key = c.category_group_key
GROUP BY cg.category_group_name;
~~~

Bộ ví dụ này **minh họa chiến lược thay thế**. Không chạy đồng thời câu query trên với FK trỏ vào DimProduct hình sao nếu chưa đổi mô hình và khóa đúng tương ứng.

### 3.3. Vì sao chọn snowflake?

Một số trường hợp hợp lý:

- Hệ thống có **taxonomy danh mục/nhãn hiệu dùng chung và quản trị tập trung**.
- Các cấp phân loại cần **thông tin riêng** hoặc được dùng bởi nhiều dimension khác.
- Cần hạn chế lặp một tập mô tả rất lớn hoặc thay đổi cấu trúc phân loại thường xuyên.
- Một dimension có số hàng lớn và các trường cấp trên cần quản lý thành dữ liệu riêng.

Những chi phí cần chấp nhận:

- Truy vấn và mô hình BI phải đi qua nhiều JOIN hơn.
- Kế hoạch truy vấn có thể phức tạp, tùy engine, index/cluster và dữ liệu.
- Cập nhật phân cấp Category có thể **diễn giải lại lịch sử** nếu Category dùng Type 1 trong khi báo cáo cần phân loại như thời điểm bán.
- Có thêm FK/đường nạp, kiểm soát khóa và lịch sử giữa các bảng cấp.

Không nên kết luận “hình sao luôn nhanh hơn” hoặc “bông tuyết luôn tiết kiệm hơn” mà chưa đo trên engine và dữ liệu đại diện. Kho cột, cơ chế join, cache, số hàng dimension và mẫu truy vấn quyết định kết quả thực tế.

## 4. Khi có nhiều quy trình: fact constellation (galaxy)

Một doanh nghiệp thường có nhiều quá trình đo khác nhau. Bán hàng, trả hàng, tồn kho, thanh toán, giao vận và mục tiêu doanh số **không nên bị ép vào một bảng fact khổng lồ** chỉ vì cùng liên quan đến Product.

~~~mermaid
flowchart TB
    D["DimDate chung"]
    P["DimProduct chung"]
    S["DimStore chung"]
    C["DimCustomer"]
    F1["FactSalesLine"]
    F2["FactReturnLine"]
    F3["FactInventoryDaily"]
    D --> F1
    D --> F2
    D --> F3
    P --> F1
    P --> F2
    P --> F3
    S --> F1
    S --> F2
    S --> F3
    C --> F1
~~~

Ba fact dùng chung Date, Product và Store theo **định nghĩa nhất quán**, nhưng có grain khác nhau:

| Quy trình | Fact | Grain | Date đóng vai trò | Các chiều chính |
| --- | --- | --- | --- | --- |
| Bán hàng | FactSalesLine | Một dòng bán thành công | Ngày bán | Date, Product, Store, Customer |
| Trả hàng | FactReturnLine | Một dòng/sự kiện trả hàng | Ngày ghi nhận trả hàng | Date, Product, Store |
| Tồn kho | FactInventoryDaily | Một Product tại một Store cuối ngày | Ngày snapshot | Date, Product, Store |

**Dimension dùng chung (conformed dimension)** không có nghĩa mọi fact phải chứa đủ mọi khóa chiều. Tồn kho theo cửa hàng không có Customer là bình thường; tạo Customer giả để ghép cho đủ sao thường là một sai lầm về grain.

### 4.1. Điều kiện để một chiều thực sự “conformed”

DimProduct chỉ thực sự được dùng chung khi các nhóm báo cáo nhất trí về:

1. **Định danh:** Product P-001 trong sales và returns là cùng mã sản phẩm nghiệp vụ.
2. **Phạm vi:** mã có duy nhất toàn doanh nghiệp hay chỉ trong tenant/hệ thống?
3. **Ngữ nghĩa:** một sản phẩm là SKU, biến thể, bộ sản phẩm hay mã dòng sản phẩm?
4. **Thuộc tính:** Category, Brand, hệ phân cấp và các quy tắc NULL được định nghĩa nhất quán.
5. **Lịch sử:** khi Product đổi Category, fact quá khứ được xem theo phân loại **cũ** hay **hiện tại**?
6. **Khóa:** nếu dùng surrogate key theo phiên bản, ETL phải ánh xạ đúng phiên bản tại thời điểm phù hợp.
7. **Chất lượng dữ liệu:** mapping mã nguồn, bản ghi unknown, bản ghi trùng, chuẩn tên và xử lý đổi mã.

Hai bảng đều đặt tên cột **product_id** không đủ để kết luận đó là conformed dimension. Nếu hệ thống A coi một “product” là SKU còn B coi là nhóm SKU, JOIN trực tiếp trên tên mã hoặc chiều tạo ra kết quả sai.

### 4.2. Chiều theo vai trò (role-playing dimension)

Date là ví dụ phổ biến:

- FactSalesLine có **sales_date_key**.
- FactReturnLine có **return_date_key**.
- FactInventoryDaily có **snapshot_date_key**.

Cả ba khóa có thể tham chiếu cùng DimDate, nhưng **vai trò của ngày khác nhau**. Khi báo cáo doanh thu và hoàn tiền theo **ngày ghi nhận**, người dùng phải biết sales_date là ngày bán, return_date là ngày hoàn. Khi tính tỷ lệ đơn bán trong tháng bị trả về sau đó, cần **cohort theo ngày bán gốc**, không thể chỉ lấy returns cùng tháng chia sales cùng tháng rồi gọi đó là tỷ lệ trả hàng theo lô bán.

Một fact giao vận có thể dùng nhiều vai trò của Date trong **cùng một hàng**: order_date_key, ship_date_key, delivered_date_key. Mô hình BI có thể trình bày chúng như những chiều ngày theo vai trò riêng, dù các khóa cùng trỏ đến một bảng vật lý.

## 5. DDL PostgreSQL cho một mô hình galaxy tối giản

Để minh họa có thể kiểm thử, giả định:

- Mọi đại lượng tiền đều tính bằng **VND**; trong hệ thống đa tiền tệ cần thêm currency và quy tắc tỷ giá/qui đổi.
- Dòng bán được ghi nhận khi phát sinh giao dịch bán hợp lệ, không bao gồm giỏ hàng nháp.
- Trả hàng là **sự kiện riêng** có refund_amount dương; không xóa dòng bán gốc.
- Cửa hàng của FactReturnLine là **cửa hàng bán gốc được quy trách nhiệm**, không nhất thiết là nơi khách đến trả hàng. Nếu cần phân tích điểm tiếp nhận trả hàng, thêm **return_processing_store_key** với ngữ nghĩa riêng.
- Snapshot tồn kho chụp số lượng cuối ngày theo cùng quy tắc múi giờ nghiệp vụ.

### 5.1. Các bảng chiều hình sao

~~~sql
-- PostgreSQL: ví dụ đào tạo, không phải một bộ DDL production đầy đủ.
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,               -- ví dụ 20261010
    calendar_date DATE NOT NULL UNIQUE,
    calendar_year SMALLINT NOT NULL,
    calendar_month SMALLINT NOT NULL
        CHECK (calendar_month BETWEEN 1 AND 12),
    day_of_month SMALLINT NOT NULL
        CHECK (day_of_month BETWEEN 1 AND 31)
);

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,             -- phiên bản surrogate
    product_code TEXT NOT NULL,                 -- định danh nghiệp vụ ổn định
    product_name TEXT NOT NULL,
    brand_name TEXT NOT NULL,
    category_name TEXT NOT NULL,
    category_group_name TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK ((valid_to IS NULL) = is_current)
);

-- Mỗi mã sản phẩm có tối đa một phiên bản hiện hành.
CREATE UNIQUE INDEX uq_dim_product_current
ON dim_product (product_code)
WHERE is_current;

CREATE TABLE dim_store (
    store_key BIGINT PRIMARY KEY,
    store_code TEXT NOT NULL UNIQUE,
    store_name TEXT NOT NULL,
    city_name TEXT NOT NULL,
    region_name TEXT NOT NULL
);

CREATE TABLE dim_customer (
    customer_key BIGINT PRIMARY KEY,
    customer_code TEXT NOT NULL UNIQUE,
    customer_segment TEXT NOT NULL
);
~~~

**DimProduct** ở ví dụ chứa nhiều phiên bản theo Type 2. Khóa product_key phân biệt **phiên bản**, còn product_code xác định sản phẩm **qua các phiên bản**. Partial unique index chỉ ngăn hai phiên bản **cùng hiện hành**; nó **chưa cấm khoảng hiệu lực của các phiên bản cũ chồng lấp**. Hệ thống cần thêm cơ chế kiểm tra khoảng thời gian và quá trình ETL/merge nhất quán.

**DimStore** và **DimCustomer** được rút gọn theo mô hình Type 1 trong bài. Nếu các thuộc tính vùng/nhóm khách cần lịch sử, bản thân chúng có thể phải phiên bản hóa giống Product; khi đó khóa và quá trình tra cứu fact cần thay đổi theo.

### 5.2. Fact giao dịch bán hàng

~~~sql
CREATE TABLE fact_sales_line (
    sales_line_key BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,                   -- degenerate dimension
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sales_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL
        REFERENCES dim_store(store_key),
    customer_key BIGINT NOT NULL
        REFERENCES dim_customer(customer_key),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    gross_amount NUMERIC(16, 2) NOT NULL CHECK (gross_amount >= 0),
    discount_amount NUMERIC(16, 2) NOT NULL CHECK (discount_amount >= 0),
    net_sales_amount NUMERIC(16, 2) NOT NULL
        CHECK (net_sales_amount >= 0),
    UNIQUE (order_id, line_no),
    CHECK (net_sales_amount = gross_amount - discount_amount)
);
~~~

Giả định một dòng bán có quantity dương, số tiền gộp và chiết khấu không âm, **net_sales_amount = gross_amount − discount_amount**. Nếu doanh nghiệp có thuế, phí, coupon phân bổ, hủy/điều chỉnh giá hoặc dòng số tiền âm, phải định nghĩa lại các measure; không thể giữ CHECK này một cách máy móc.

**order_id** ở đây là mã đơn được giả định duy nhất toàn hệ thống. Nếu mã đơn chỉ duy nhất trong một tenant/cửa hàng, khóa UNIQUE và các truy vấn COUNT(DISTINCT order_id) phải đưa **tenant_id hoặc định danh giao dịch toàn cục** vào phạm vi.

### 5.3. Fact trả hàng và fact snapshot tồn kho

~~~sql
CREATE TABLE fact_return_line (
    return_line_key BIGINT PRIMARY KEY,
    return_reference TEXT NOT NULL,
    original_sales_line_key BIGINT NOT NULL
        REFERENCES fact_sales_line(sales_line_key),
    return_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL
        REFERENCES dim_store(store_key),
    returned_quantity INTEGER NOT NULL
        CHECK (returned_quantity > 0),
    refund_amount NUMERIC(16, 2) NOT NULL
        CHECK (refund_amount >= 0)
);

CREATE TABLE fact_inventory_daily (
    snapshot_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL
        REFERENCES dim_store(store_key),
    units_on_hand INTEGER NOT NULL,
    inventory_cost_amount NUMERIC(16, 2),
    PRIMARY KEY (snapshot_date_key, product_key, store_key)
);
~~~

Ở đây **units_on_hand** có thể bằng 0 hoặc âm nếu hệ thống cho phép ghi nhận chênh lệch tồn âm; nếu chính sách cấm tồn âm thì bổ sung **CHECK(units_on_hand >= 0)**. Không nên thêm CHECK chỉ vì “tồn kho thường không âm” nếu nghiệp vụ vẫn phải ghi nhận tồn âm/điều chỉnh.

Quan hệ tới original_sales_line_key giúp truy vết nguồn gốc trả hàng. Nhưng các FK **không tự chứng minh**:

- returned_quantity không vượt lượng hàng đã bán trừ các lần trả trước;
- product_key và store_key của lần trả khớp chính sách quy thuộc với lần bán gốc;
- có duy nhất một sự kiện nạp cho mỗi return line từ nguồn;
- refund_amount có đúng chính sách giá/tax không.

Các quy tắc đó cần **khóa định danh nguồn, quy trình ETL, kiểm soát nghiệp vụ và đối soát**; một số cần kiểm tra xuyên fact.

### 5.4. Chỉ mục theo truy vấn, không theo hình minh họa

~~~sql
CREATE INDEX idx_sales_date_product_store
ON fact_sales_line (sales_date_key, product_key, store_key);

CREATE INDEX idx_sales_product_date
ON fact_sales_line (product_key, sales_date_key);

CREATE INDEX idx_return_date_product_store
ON fact_return_line (return_date_key, product_key, store_key);

CREATE INDEX idx_return_original_sale
ON fact_return_line (original_sales_line_key);
~~~

Các chỉ mục B-tree này là ví dụ cho PostgreSQL và các truy vấn lọc ngày/sản phẩm. Trên kho cột/MMP, cách tối ưu có thể là **partition pruning, clustering, sorting, compression hoặc partition/cluster keys**, không phải sao chép nguyên mọi index của OLTP.

Nên đo **EXPLAIN (ANALYZE, BUFFERS)** với dữ liệu và tải đại diện, kiểm tra scan bytes, cardinality, JOIN, sort/hash, độ trễ và chi phí nạp dữ liệu. Dòng cuối cùng của quyết định tối ưu phải dựa trên kế hoạch truy vấn thực, không chỉ sơ đồ sao hay bông tuyết trông có ít JOIN hơn.

## 6. Bộ dữ liệu nhỏ để kiểm tra grain và chỉ tiêu

Ví dụ một sản phẩm P-001 tại cửa hàng HCM-01; mọi measure tiền là VND.

~~~sql
INSERT INTO dim_date
(date_key, calendar_date, calendar_year, calendar_month, day_of_month)
VALUES
    (20261010, DATE '2026-10-10', 2026, 10, 10),
    (20261011, DATE '2026-10-11', 2026, 10, 11);

INSERT INTO dim_product
(product_key, product_code, product_name, brand_name,
 category_name, category_group_name,
 valid_from, valid_to, is_current)
VALUES
    (101, 'P-001', 'Tai nghe không dây', 'Brand A',
     'Tai nghe', 'Thiết bị âm thanh',
     TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL, TRUE);

INSERT INTO dim_store
(store_key, store_code, store_name, city_name, region_name)
VALUES
    (11, 'HCM-01', 'Cửa hàng trung tâm', 'TP. Hồ Chí Minh', 'Miền Nam');

INSERT INTO dim_customer
(customer_key, customer_code, customer_segment)
VALUES
    (51, 'C-001', 'RETAIL');

INSERT INTO fact_sales_line
(sales_line_key, order_id, line_no, sales_date_key,
 product_key, store_key, customer_key,
 quantity, gross_amount, discount_amount, net_sales_amount)
VALUES
    (1001, 501, 1, 20261010, 101, 11, 51, 2, 200000, 0, 200000),
    (1002, 502, 1, 20261010, 101, 11, 51, 1, 100000, 0, 100000),
    (1003, 503, 1, 20261011, 101, 11, 51, 3, 300000, 0, 300000);

-- Trả 1 chiếc từ dòng bán 1001, ghi nhận vào 11/10.
INSERT INTO fact_return_line
(return_line_key, return_reference, original_sales_line_key,
 return_date_key, product_key, store_key, returned_quantity, refund_amount)
VALUES
    (2001, 'RET-001', 1001, 20261011, 101, 11, 1, 100000);

INSERT INTO fact_inventory_daily
(snapshot_date_key, product_key, store_key, units_on_hand,
 inventory_cost_amount)
VALUES
    (20261010, 101, 11, 20, 1200000),
    (20261011, 101, 11, 17, 1020000);
~~~

**Ý nghĩa dự kiến từ dữ liệu mẫu:**

| Ngày | Đã bán (đơn vị) | Tiền bán | Trả hàng (đơn vị) | Tiền hoàn | Tồn cuối ngày |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10/10/2026 | 3 | 300.000 | 0 | 0 | 20 |
| 11/10/2026 | 3 | 300.000 | 1 | 100.000 | 17 |

Đây là những **kết quả suy ra từ dữ liệu mẫu đã nêu**, không phải benchmark hay số liệu kinh doanh thật. Tồn kho cuối ngày là một phép đo trạng thái độc lập: không thể tự suy ra tồn 11/10 chỉ từ doanh số và trả hàng, vì còn nhập kho, xuất điều chuyển, kiểm đếm, hàng trả không đủ điều kiện nhập lại hoặc các điều chỉnh khác.

Một kiểm tra grain đơn giản:

~~~sql
-- Transaction fact: có 3 dòng bán.
SELECT COUNT(*) AS sales_lines,
       SUM(quantity) AS sold_units,
       SUM(net_sales_amount) AS net_sales
FROM fact_sales_line;
-- 3 / 6 / 600000

-- Snapshot fact: một hàng/ngày/sản phẩm/cửa hàng.
SELECT snapshot_date_key, COUNT(*) AS snapshot_rows
FROM fact_inventory_daily
GROUP BY snapshot_date_key
ORDER BY snapshot_date_key;
-- Mỗi ngày có 1 hàng trong ví dụ.
~~~

## 7. “Drill-across”: tổng hợp từng fact trước khi ghép

Khi hai fact có nhiều hàng cho cùng Product–Store–Date, **JOIN trực tiếp hai bảng fact** thường tạo **fan-out**.

Giả sử 10/10 có ba dòng bán và hai sự kiện trả hàng liên quan cùng một sản phẩm/cửa hàng/ngày. Một JOIN trực tiếp theo ba khóa này có thể tạo **3 × 2 = 6 hàng**. Nếu sau đó SUM doanh thu hoặc hoàn tiền, số đo sẽ bị nhân bản.

Ngay cả khi hai fact có khóa chiều giống nhau, chúng có **định danh sự kiện khác nhau**. Không có ý nghĩa “mỗi dòng sale tương ứng với từng dòng return theo cùng Date, Product, Store” chỉ vì ba khóa bằng nhau.

### 7.1. Câu SQL dễ làm sai

~~~sql
-- MINH HỌA THIẾT KẾ SAI cho báo cáo tổng hợp:
SELECT s.sales_date_key, s.product_key, s.store_key,
       SUM(s.net_sales_amount) AS sales_amount,
       SUM(r.refund_amount) AS refund_amount
FROM fact_sales_line AS s
JOIN fact_return_line AS r
  ON r.return_date_key = s.sales_date_key
 AND r.product_key = s.product_key
 AND r.store_key = s.store_key
GROUP BY s.sales_date_key, s.product_key, s.store_key;
~~~

Đoạn trên vừa **nhân số dòng** khi có nhiều giao dịch hai phía, vừa **bỏ mất** ngày chỉ có bán mà chưa có trả hàng hoặc ngày chỉ có trả hàng mà không có bán mới. Không nên vá lỗi bằng **SUM(DISTINCT amount)**, vì hai sự kiện độc lập có thể có cùng giá trị tiền và vẫn phải được đếm hai lần.

### 7.2. Câu SQL đúng hướng: aggregate first, join later

Chọn grain báo cáo:

> **Một hàng theo ngày ghi nhận × mã sản phẩm ổn định × cửa hàng**.

Sau đó tổng hợp mỗi fact **riêng** về đúng grain này, mới FULL OUTER JOIN các kết quả:

~~~sql
WITH sales AS (
    SELECT s.sales_date_key AS date_key,
           p.product_code,
           st.store_code,
           SUM(s.quantity) AS sold_units,
           SUM(s.net_sales_amount) AS sales_amount
    FROM fact_sales_line AS s
    JOIN dim_product AS p ON p.product_key = s.product_key
    JOIN dim_store AS st ON st.store_key = s.store_key
    WHERE s.sales_date_key BETWEEN 20261010 AND 20261011
    GROUP BY s.sales_date_key, p.product_code, st.store_code
),
returns AS (
    SELECT r.return_date_key AS date_key,
           p.product_code,
           st.store_code,
           SUM(r.returned_quantity) AS returned_units,
           SUM(r.refund_amount) AS returned_amount
    FROM fact_return_line AS r
    JOIN dim_product AS p ON p.product_key = r.product_key
    JOIN dim_store AS st ON st.store_key = r.store_key
    WHERE r.return_date_key BETWEEN 20261010 AND 20261011
    GROUP BY r.return_date_key, p.product_code, st.store_code
)
SELECT d.calendar_date,
       COALESCE(s.product_code, r.product_code) AS product_code,
       COALESCE(s.store_code, r.store_code) AS store_code,
       COALESCE(s.sold_units, 0) AS sold_units,
       COALESCE(s.sales_amount, 0) AS sales_amount,
       COALESCE(r.returned_units, 0) AS returned_units,
       COALESCE(r.returned_amount, 0) AS returned_amount
FROM sales AS s
FULL OUTER JOIN returns AS r
  ON r.date_key = s.date_key
 AND r.product_code = s.product_code
 AND r.store_code = s.store_code
JOIN dim_date AS d
  ON d.date_key = COALESCE(s.date_key, r.date_key)
ORDER BY d.calendar_date, product_code, store_code;
~~~

Phân biệt rõ:

- **Ngày của sales** là ngày bán; **ngày của returns** là ngày trả. Báo cáo này so sánh **dòng tiền/số lượng được ghi nhận trong cùng ngày**, không phải tỷ lệ sản phẩm bán ngày đó sẽ bị trả sau này.
- **product_code** được chọn làm khóa nhóm để gom các phiên bản SCD2 của cùng sản phẩm. Nếu mã sản phẩm không ổn định hoặc chỉ duy nhất trong một tenant, phải dùng một **business key ổn định và đúng phạm vi**.
- **store_code** phải có cùng định nghĩa ở hai fact. Ví dụ đã quy ước Returns quy thuộc cửa hàng bán gốc. Nếu Returns ghi cửa hàng xử lý trả, cần định nghĩa lại báo cáo hoặc dùng chiều vai trò khác.
- Sau bước tổng hợp, mỗi nhánh có **tối đa một hàng cho một bộ khóa nhóm**; JOIN sẽ không tạo phép nhân giữa các giao dịch chi tiết.

Cách tổng hợp rồi ghép trên các chiều phù hợp thường được gọi là **drill-across** hoặc **multipass SQL**. Với nhiều fact, hãy chọn trước tập **conformed dimensions** và mức hạt chung ở báo cáo.

### 7.3. Nếu muốn “doanh thu sau hoàn” thì sao?

Một định nghĩa ví dụ là:

~~~text
net_cash_flow_for_period = sales_amount_for_period
                         - refund_amount_for_period
~~~

Đây là số tiền bán ghi nhận trong kỳ trừ tiền trả ghi nhận **trong cùng kỳ**. Nó **không** nhất thiết bằng doanh thu kế toán đã ghi nhận theo chuẩn mực, vì còn thuế, chiết khấu, phí, quyền hoàn, hủy, điều chỉnh và chính sách ghi nhận.

Tương tự:

~~~text
refund_amount_in_period / sales_amount_in_period
~~~

là một **tỷ lệ tiền hoàn trong kỳ trên tiền bán trong kỳ**, không phải “tỷ lệ trả hàng của các đơn đã bán trong kỳ”. Muốn biết tỷ lệ theo **cohort bán hàng**, cần nối sự kiện trả với **original_sales_line_key**, xác định khoảng theo ngày bán và quy tắc mẫu số.

## 8. Measure cộng được, cộng có điều kiện và không cộng được

Phân loại khả năng cộng của measure là thiết yếu khi làm nhiều fact.

| Measure | Tính chất | Tổng hợp phù hợp | Sai lầm thường gặp |
| --- | --- | --- | --- |
| Sold quantity | Thường **additive** theo ngày, sản phẩm, cửa hàng | SUM sau lọc đúng giao dịch | Đếm lại dòng bị hủy hoặc nhân khi JOIN |
| Net sales amount | Additive nếu **cùng tiền tệ, cùng định nghĩa** | SUM | Cộng số tiền VND với USD không chuyển đổi |
| Refund amount | Additive theo sự kiện trả đúng và một tiền tệ | SUM | Trừ cùng một sự kiện hai lần |
| Units on hand | **Semi-additive** | SUM theo SKU/cửa hàng tại **một thời điểm** | SUM ngày 10 và 11 để báo “tồn kho hai ngày” |
| Gross margin % | **Non-additive** | Tính từ tổng lãi và tổng doanh thu | AVG không trọng số các tỷ lệ từng dòng |
| Distinct order count | Thường non-additive | COUNT DISTINCT trên phạm vi báo cáo | Cộng số đơn theo sản phẩm, vì một đơn có nhiều sản phẩm |
| Conversion rate | Non-additive | Tổng conversions / tổng eligible sessions | AVG các tỷ lệ của nhóm không cùng trọng số |

### 8.1. Snapshot tồn kho không được SUM qua thời gian

Sai về nghiệp vụ nếu muốn “tồn cuối kỳ”:

~~~sql
-- Sai nếu diễn giải là tồn kho cuối kỳ hai ngày:
SELECT product_key, store_key, SUM(units_on_hand) AS inventory
FROM fact_inventory_daily
WHERE snapshot_date_key IN (20261010, 20261011)
GROUP BY product_key, store_key;
-- Kết quả 37 từ 20 + 17, không phải số tồn cuối kỳ.
~~~

Để lấy snapshot **mới nhất không muộn hơn ngày báo cáo**:

~~~sql
SELECT product_key, store_key, units_on_hand, snapshot_date_key
FROM (
    SELECT i.*,
           ROW_NUMBER() OVER (
               PARTITION BY i.product_key, i.store_key
               ORDER BY i.snapshot_date_key DESC
           ) AS rn
    FROM fact_inventory_daily AS i
    WHERE i.snapshot_date_key <= 20261011
) AS latest
WHERE rn = 1;
-- Trong ví dụ: 17 chiếc ở 11/10/2026.
~~~

Đây là bản đơn giản khi một Product/Store giữ nguyên surrogate key qua hai snapshot. Nếu DimProduct là SCD2 và **product_key đổi giữa các ngày**, muốn tồn cuối kỳ cho một sản phẩm nghiệp vụ phải nhóm hoặc phân vùng theo **product_code ổn định** sau khi JOIN dimension, đồng thời kiểm tra quy tắc ánh xạ phiên bản. Không dùng MAX(product_key) để giả định đó là phiên bản mới nhất.

Nếu muốn tính **tồn kho trung bình hàng ngày**, phải định nghĩa tập ngày, xử lý ngày thiếu snapshot và cách tính trọng số; lấy AVG trên các snapshot có mặt có thể sai nếu ngày bị thiếu không ngẫu nhiên.

### 8.2. Cộng khác đếm khác lấy số cuối

Một **đơn hàng** có thể gồm nhiều sản phẩm. COUNT(*) trên FactSalesLine đếm dòng bán, còn COUNT(DISTINCT order_id) đếm **đơn duy nhất trong phạm vi truy vấn**, nếu order_id là định danh toàn cục.

Khi chia theo danh mục, một đơn chứa sản phẩm thuộc hai danh mục sẽ xuất hiện ở **cả hai nhóm**. Cộng số đơn của hai nhóm không nhất thiết bằng số đơn toàn doanh nghiệp. Trước khi công bố dashboard, phải ghi rõ measure **có cộng được qua dimension đang nhóm không**.

## 9. Conformed dimensions và lịch sử SCD Type 2

### 9.1. Mã nghiệp vụ và surrogate key có vai trò khác nhau

Giả sử P-001 ban đầu thuộc Category “Tai nghe”, sau đó doanh nghiệp chuyển sang “Thiết bị cá nhân”. Nếu cần xem đúng phân loại **tại thời điểm bán**, dùng nhiều phiên bản:

| product_key | product_code | category_name | valid_from | valid_to | is_current |
| ---: | --- | --- | --- | --- | --- |
| 101 | P-001 | Tai nghe | 2026-01-01 | 2026-10-31 | false |
| 102 | P-001 | Thiết bị cá nhân | 2026-10-31 | NULL | true |

Sự kiện bán ngày 10/10 trỏ product_key **101**. Sự kiện bán ngày 05/11 trỏ product_key **102**, khi pipeline dùng **thời điểm nghiệp vụ** để tra phiên bản phù hợp.

Ở ví dụ này, khoảng hiệu lực được hiểu theo **[valid_from, valid_to)**: bắt đầu bao gồm, kết thúc loại trừ. Hai bản ghi chạm ranh giới mà không chồng lấp.

**SCD2 không tự giải quyết:**

- Hai phiên bản cùng có hiệu lực ở một thời điểm.
- Mã P-001 bị tái sử dụng cho sản phẩm khác.
- Dữ liệu nguồn gửi một thay đổi **muộn** có hiệu lực từ quá khứ.
- Cần xem **theo danh mục hiện tại** thay vì danh mục tại ngày bán.
- Cùng một Product nhưng fact return quy về ngày trả, fact sales quy về ngày bán.

Những tình huống đó phải có quy tắc phiên bản và cách truy vấn tương ứng.

### 9.2. Khi nào nên dùng chiều “hiện tại”, khi nào dùng “as-of”?

Có ít nhất hai câu hỏi hợp lệ:

1. “Doanh thu năm trước **theo danh mục tại thời điểm bán** là bao nhiêu?” → phân loại theo dimension version được fact giữ tại ngày bán.
2. “Nếu áp **danh mục hiện tại** cho mọi sản phẩm, doanh thu năm trước được phân bố lại thế nào?” → đi từ business key sang phiên bản dimension hiện hành hoặc bảng ánh xạ phân loại hiện tại.

Không thể trộn hai cách trong một dashboard rồi so sánh số liệu mà không ghi nhãn. Khi drill-across Sales và Returns, cũng phải xác định Returns được gán phiên bản Product **tại ngày bán gốc** hay **tại ngày trả**. Trong ví dụ phần 5, Returns dùng **product_key của lần bán gốc** để khớp phân loại theo giao dịch bán. Đó là một lựa chọn nghiệp vụ, không phải quy tắc duy nhất.

### 9.3. Kiểm soát tính nhất quán của SCD2

Một số kiểm thử quan trọng:

- Mỗi product_code có **tối đa một** hàng is_current = TRUE.
- Mỗi hàng có valid_to > valid_from hoặc valid_to NULL.
- Các khoảng hiệu lực của cùng product_code **không chồng lấp**.
- Với mỗi fact, sự kiện được ánh xạ tới **đúng một** phiên bản dimension hợp lệ theo thời điểm quy định.
- Khi fact đến muộn, nó không tự động dùng phiên bản hiện hành nếu nghiệp vụ muốn “as-of event”.
- Nếu thay đổi phân loại retroactive, phải xác định có **restatement/backfill fact** hay giữ cách phân loại đã báo cáo.

Trong PostgreSQL, có thể dùng cơ chế kiểm tra khoảng thời gian như exclusion constraint hoặc logic ghi có giao dịch phù hợp. Unique partial index trên bản ghi hiện hành **không đủ** để cấm chồng lấp mọi khoảng thời gian.

## 10. Snowflake và vấn đề lịch sử chiều

Với hình sao, hàng DimProduct SCD2 có thể giữ bản chụp **category_name** và **brand_name** theo phiên bản. Với snowflake, Product trỏ tới Category riêng; nếu Category đổi tên theo Type 1, mọi Product cũ có thể hiển thị **tên Category mới** trong báo cáo quá khứ.

Đây là lựa chọn có thể hợp lệ nếu doanh nghiệp muốn **định nghĩa nhóm hiện hành cho toàn bộ lịch sử**, nhưng không hợp lệ nếu báo cáo cần bảo tồn phân loại tại thời điểm giao dịch.

Để giữ lịch sử trong snowflake, có thể:

- Version hóa **Category** riêng, rồi Product trỏ tới **đúng phiên bản Category**.
- Dùng các quan hệ thành viên Product–Category có khoảng hiệu lực.
- Giữ bản chụp phân loại ở DimProduct phục vụ báo cáo cần “as-of”.
- Xây các view/mart riêng cho báo cáo “theo phân loại hiện tại” và “theo phân loại lịch sử”.

Việc snowflake hóa không tự loại bỏ yêu cầu lịch sử; thường nó làm **quy tắc lịch sử liên chiều phức tạp hơn**. Vì vậy, chọn hình sao hay bông tuyết cần xét cả cách thay đổi Category, Brand và vùng cửa hàng chứ không chỉ số byte lưu tên.

## 11. Many-to-many dimensions và bridge

Một Product có thể được gắn **nhiều chiến dịch (Campaign)** hoặc nhiều nhãn. Nếu JOIN FactSalesLine tới tất cả Campaign của Product, một dòng bán có thể xuất hiện nhiều lần. Đây là tình huống **bridge table**.

Ví dụ grain của bridge:

> Một dòng bán được phân bổ cho một chiến dịch với một tỷ trọng được nghiệp vụ phê duyệt.

~~~sql
CREATE TABLE dim_campaign (
    campaign_key BIGINT PRIMARY KEY,
    campaign_code TEXT NOT NULL UNIQUE,
    campaign_name TEXT NOT NULL
);

CREATE TABLE bridge_sales_campaign (
    sales_line_key BIGINT NOT NULL
        REFERENCES fact_sales_line(sales_line_key),
    campaign_key BIGINT NOT NULL
        REFERENCES dim_campaign(campaign_key),
    allocation_weight NUMERIC(8, 6) NOT NULL
        CHECK (allocation_weight >= 0 AND allocation_weight <= 1),
    PRIMARY KEY (sales_line_key, campaign_key)
);
~~~

Nếu một dòng bán thuộc hai Campaign và doanh nghiệp muốn phân bổ 60%/40%, hai hàng bridge có weight 0.6 và 0.4. Báo cáo phân bổ:

~~~sql
SELECT c.campaign_name,
       SUM(f.net_sales_amount * b.allocation_weight)
           AS allocated_sales
FROM fact_sales_line AS f
JOIN bridge_sales_campaign AS b
  ON b.sales_line_key = f.sales_line_key
JOIN dim_campaign AS c ON c.campaign_key = b.campaign_key
GROUP BY c.campaign_name;
~~~

**Giới hạn:** CHECK trên từng hàng chỉ bảo đảm mỗi weight trong khoảng [0,1], **không buộc tổng weight của một sales_line_key bằng 1**. Quy tắc tổng 100% là ràng buộc xuyên hàng, cần kiểm tra trong pipeline/giao dịch. Đồng thời phải quyết định cách xử lý dòng bán **không có chiến dịch**: phân bổ vào Unknown/Unassigned, hay cố ý để ngoài báo cáo Campaign.

Nếu yêu cầu là “mỗi Campaign có quyền nhận **toàn bộ** doanh số có liên quan”, không được dùng tỷ trọng 60/40 một cách giả tạo. Khi đó báo cáo theo từng Campaign có thể đếm cùng một giao dịch nhiều lần **có chủ đích**, nhưng tổng các Campaign **không thể cộng lại** thành tổng doanh thu doanh nghiệp. Phải ghi rõ ngữ nghĩa chỉ tiêu.

## 12. Khi nhiều fact không có cùng tập chiều

Không phải mọi fact có thể drill-across ở mọi mức hạt.

Ví dụ:

~~~text
FactSalesLine       : Date, Product, Store, Customer
FactInventoryDaily  : Date, Product, Store
FactStoreTargetMonth: Month, Store
~~~

Báo cáo “sales thực tế so với mục tiêu theo **tháng, cửa hàng**” có thể:

1. Tổng hợp FactSalesLine từ **ngày và dòng bán** lên **tháng–cửa hàng**.
2. Giữ FactStoreTargetMonth ở grain **tháng–cửa hàng**.
3. Nối hai kết quả theo month_key, store_code.
4. Tính actual/target sau khi ghép, với chính sách khi target = 0.

**Không** JOIN target tháng trực tiếp vào mọi dòng bán trong tháng rồi SUM(target_amount), vì mục tiêu sẽ bị nhân theo số dòng bán.

Báo cáo “tồn kho theo Customer” không có định nghĩa tự nhiên, vì snapshot tồn kho không có chiều Customer. Nếu cần phân bổ tồn kho cho khách hàng hoặc phân khúc, phải có **quy tắc phân bổ hoặc đặt chỗ tồn kho** riêng; không tự phát sinh customer_key cho fact tồn kho để ghép với sales.

### 12.1. Một bảng fact chung có nhiều cột NULL?

Một thiết kế kiểu:

~~~text
FactEverything(
  event_type,
  sales_date_key,
  return_date_key,
  snapshot_date_key,
  product_key,
  store_key,
  customer_key,
  sales_amount,
  refund_amount,
  units_on_hand,
  ...
)
~~~

có thể dẫn đến các hàng với **nhiều trường NULL**, grain khác nhau và các phép SUM vô nghĩa. Một KPI tồn kho cần “chỉ lấy snapshot mới nhất”, còn doanh thu cần “cộng giao dịch”; việc đặt chung làm người dùng dễ cộng nhầm.

Nếu doanh nghiệp thực sự có **một loại sự kiện thống nhất** với grain và measure tương thích, một fact duy nhất có thể hợp lý. Nhưng không nên trộn những quy trình khác grain chỉ để giảm số bảng.

## 13. Các lỗi phổ biến khi JOIN fact và dimension

### 13.1. Fan-out do dimension không duy nhất ở khóa JOIN

Một fact có product_code P-001. Nếu JOIN trực tiếp với DimProduct SCD2 theo product_code mà không chọn phiên bản, P-001 có hai bản ghi dimension sẽ tạo **hai hàng** từ một dòng fact.

Đúng hướng là:

- Fact lưu **product_key** của phiên bản đã xác định; JOIN theo khóa này.
- Hoặc khi tra phiên bản từ dữ liệu nguồn, JOIN theo **product_code + khoảng hiệu lực** và kiểm tra mỗi sự kiện chỉ nhận đúng một version.

Không JOIN fact SCD2 theo business key rồi SUM tiền mà không kiểm tra số phiên bản khớp.

### 13.2. Fan-out do nhiều fact được JOIN ở mức chi tiết

Đã trình bày ở phần 7: Sales và Returns là hai tập sự kiện độc lập. Tổng hợp riêng về grain chung rồi ghép; không sửa bằng SUM(DISTINCT amount).

### 13.3. Fact đếm đơn theo sản phẩm

Một Order có ba dòng, thuộc ba danh mục. Nếu tính COUNT(DISTINCT order_id) theo category, một đơn có thể xuất hiện ở nhiều category. Tổng số đơn category **không được cộng** để ra tổng đơn nếu các tập không rời nhau.

### 13.4. Inner JOIN làm rơi fact

Khi fact có customer_key chưa xác định nhưng dimension chưa được nạp, INNER JOIN có thể khiến doanh thu “biến mất” khỏi báo cáo. Nên dùng quy tắc unknown member, xử lý late-arriving dimension hoặc quan hệ LEFT JOIN có kiểm soát; quan trọng là đối soát **số fact ban đầu và số fact được báo cáo**.

### 13.5. Trộn đơn vị đo, tiền tệ và thời điểm

- Số lượng chiếc không thể cộng với kilogram.
- Doanh thu VND không cộng trực tiếp USD.
- Sales theo ngày bán không đồng nghĩa Payment theo ngày thu tiền.
- Inventory cuối ngày không cộng theo tháng.
- Một tên Category giống nhau ở hai taxonomy chưa chắc cùng nhóm.

Những điều này là **ràng buộc ngữ nghĩa**, không thể được sửa chỉ bằng PK/FK.

## 14. ETL/ELT, dữ liệu đến muộn và khả năng đối soát

Một schema tốt trên giấy vẫn có thể sai nếu đường nạp không giữ đúng grain hoặc phiên bản chiều.

### 14.1. Một quy trình nạp thường gặp

~~~mermaid
flowchart LR
    O["Nguồn giao dịch"] --> S["Staging / Kiểm tra"]
    S --> D["Chuẩn hóa DimDate / DimProduct / DimStore"]
    D --> M["Ánh xạ surrogate key theo thời điểm"]
    S --> M
    M --> F["Nạp FactSales / FactReturns / Inventory"]
    F --> Q["Đối soát grain, số tiền, khóa, độ trễ"]
    Q --> B["Mart / Dashboard"]
~~~

Các bất biến nên được ghi thành kiểm thử:

| Kiểm thử | Điều phải đúng |
| --- | --- |
| Duy nhất theo nguồn | Một source_sale_line_id chỉ sinh đúng một fact tại grain đã định |
| Tham chiếu chiều | Mọi surrogate FK có chiều tồn tại hoặc unknown member theo chính sách |
| Ánh xạ SCD2 | Một sự kiện nhận đúng một version phù hợp thời điểm |
| Bội số fact | Một return event không được nạp lại thành nhiều hàng khi job retry |
| Tổng tiền | Tổng fact theo cửa sổ đối soát khớp tổng nguồn sau điều chỉnh quy định |
| Tổng số dòng | Số event hợp lệ nguồn khớp số fact mới, xét các loại bị loại có lý do |
| Snapshot | Có đúng một hàng cho date–product–store dự kiến; ngày thiếu được đánh dấu |
| Conformed dimension | Mã Product/Store và phân cấp dùng thống nhất ở mọi pipeline |
| Freshness | Dữ liệu cập nhật trong độ trễ đã công bố |
| Lịch sử | Fact cũ vẫn nối đúng version dimension theo chính sách as-of |

### 14.2. Nạp lặp và late-arriving facts

Nếu một bản tin bán hàng bị gửi lại, pipeline không được ghi thêm một sales_line_key mới rồi **nhân doanh thu**. Cần khóa nghiệp vụ từ nguồn, cơ chế **idempotent upsert/merge**, hoặc bảng dedup có tính duy nhất theo (source_system, source_event_id).

Nếu FactReturns đến sau nhiều ngày, **return_date_key** phải phản ánh đúng ngày nghiệp vụ của sự kiện trả, không tự chuyển thành ngày batch ETL chạy. Đồng thời giữ **load_timestamp** riêng nếu cần đo độ trễ.

Nếu Product SCD2 được cập nhật muộn có hiệu lực trong quá khứ, phải quyết định cách xử lý các fact đã nạp:

- **Restatement:** ánh xạ lại fact tới version đúng nếu chính sách đòi báo cáo lịch sử theo thông tin đã sửa.
- **As-was:** giữ cách diễn giải trước để bảo toàn báo cáo đã phát hành.
- **Hai chế độ báo cáo:** cung cấp cả lịch sử đã hiệu chỉnh và lịch sử như đã công bố, nếu yêu cầu kiểm toán.

Không tự động chuyển mọi fact về product_key hiện hành vì cách đó có thể xóa ý nghĩa lịch sử.

### 14.3. Thay đổi schema và dimension liên phòng ban

Một nhóm bán hàng có thể gọi Category “Phụ kiện”, nhóm kho gọi “Thiết bị lắp thêm”. Nếu chỉ đồng nhất tên cột category_name mà không có **danh mục mã chuẩn và quy tắc ánh xạ**, conformed dimension sẽ phân chia sai.

Cần một **hợp đồng dữ liệu** quy định: mã, nguồn sở hữu, định nghĩa, miền giá trị, chính sách lịch sử, thời gian cập nhật và cách xử lý ngoại lệ. Khi nguồn thay đổi, làm rõ tác động lên fact, dashboard và các mart dùng chung.

## 15. Chọn hình sao hay bông tuyết theo nhu cầu

| Tiêu chí | Star | Snowflake | Fact constellation |
| --- | --- | --- | --- |
| Đối tượng chính | Một fact với chiều nối trực tiếp | Một fact với chiều được chuẩn hóa thêm | **Nhiều fact** cho các quy trình khác nhau |
| Grain | Do fact xác định | Do fact xác định | **Mỗi fact có grain riêng** |
| Mức JOIN lấy mô tả chiều | Thường ít | Thường nhiều | Phụ thuộc star/snowflake của từng fact |
| Lặp dữ liệu mô tả | Nhiều hơn trong dimension | Thường giảm ở bảng cấp | Dùng chiều conformed giảm việc tạo hệ mô tả rời rạc |
| Lịch sử phân cấp | Có thể giữ bản chụp Type 2 cùng product | Có thể cần lịch sử liên nhiều dimension | Phải thống nhất chính sách lịch sử qua các fact |
| Truy vấn BI | Dễ tiếp cận với một nghiệp vụ | Cần hiểu phân cấp và JOIN | Cần **drill-across** đúng mức hạt |
| Rủi ro chính | Dimension rộng, bảo trì phân loại | Phức tạp lịch sử/đường JOIN | Nhân bản khi JOIN fact, so sánh chỉ tiêu sai ngữ nghĩa |
| Khi cân nhắc | Mart đọc nhiều, dễ dùng | Danh mục phức tạp dùng chung | Phân tích liên quy trình bán–trả–kho–mục tiêu |

**Star và snowflake là hai cách thiết kế chiều**, còn **constellation là cách tổ chức nhiều fact cùng chiều**. Chúng không loại trừ nhau. Một galaxy có thể dùng dimension hình sao ở phần bán hàng và dimension phân cấp snowflake ở phần phân tích danh mục; điều kiện then chốt vẫn là **conformed dimensions và grain**.

### 15.1. Dựa vào benchmark, không dựa vào hình dáng sơ đồ

Trên một kho phân tích dạng cột, số JOIN không luôn phản ánh toàn bộ chi phí. Một Snowflake có các bảng dimension rất nhỏ có thể chạy nhanh nhờ broadcast/hash JOIN, trong khi Star với dimension quá rộng và lọc kém có thể không tối ưu.

Khi quyết định hãy đo:

- Dung lượng fact và dimension; kích thước scan và số hàng qua JOIN.
- Estimated/actual cardinality; có phát sinh fan-out không.
- Độ trễ p50/p95 cho truy vấn dashboard quan trọng.
- Chi phí nạp và cập nhật SCD2, duy trì bảng Category/Brand.
- Độ phức tạp semantic model và rủi ro người dùng tự JOIN sai.
- Kiểm soát phân quyền, dữ liệu nhạy cảm và quy tắc lưu trữ.

Không nên phi chuẩn hóa dimension để làm nhanh một dashboard mà vô tình thay đổi quy tắc tính KPI ở toàn doanh nghiệp.

## 16. So sánh với mô hình giao dịch, document và graph

Mô hình phân tích không thay thế mục tiêu của OLTP:

- **OLTP quan hệ:** tối ưu tính nhất quán giao dịch và thao tác theo đối tượng. Một Order có OrderLine, Payment, ShippingAddress với PK/FK, trạng thái và ràng buộc cập nhật.
- **OLAP/star:** tái tổ chức sự kiện thành fact và chiều phục vụ tổng hợp theo nhiều lát cắt. Snapshot, SCD và bảng tổng hợp được chọn theo mục tiêu phân tích.
- **Document:** thông tin Order và các dòng có thể nhúng thành một document để đọc một giao dịch; khi phân tích liên đơn ở quy mô lớn vẫn cần xác định grain, tách mảng và tạo các sự kiện chuẩn.
- **Graph:** quan hệ Product–Category có nhiều cha, User–Campaign hoặc mạng lưới liên kết có thể được biểu diễn bằng node/cạnh; khi tổng hợp số tiền qua nhiều đường, phải khử trùng hoặc phân bổ, không cộng số lần duyệt như doanh thu.

Một nguồn document có thể chứa:

~~~json
{
  "orderId": 501,
  "soldAt": "2026-10-10T10:00:00+07:00",
  "storeCode": "HCM-01",
  "customerCode": "C-001",
  "lines": [
    {"lineNo": 1, "productCode": "P-001", "quantity": 2,
     "grossAmount": 200000, "discount": 0}
  ]
}
~~~

Khi chuyển sang star, **mỗi phần tử của lines** trở thành một sự kiện FactSalesLine theo grain đã định; các trường Product/Store/Customer được ánh xạ tới conformed dimensions. Nếu chỉ đếm một document là một dòng bán, một Order nhiều dòng có thể làm sai số lượng/sản phẩm; nếu sao chép toàn bộ tổng đơn vào mỗi dòng thì có thể nhân doanh thu đơn.

Với graph taxonomy nhiều cha, một Product có thể đi đến cùng nhóm tổ tiên qua hai đường. Khi dùng graph để nạp/nhóm dimension, phải xác định **thuộc một nhóm theo tồn tại đường đi hay theo từng đường**. Nếu báo cáo một lần cho mỗi Product–nhóm, dùng một tập tổ tiên duy nhất; nếu phân bổ theo nhiều nhánh, cần trọng số có kiểm soát.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Vẽ fact trước khi viết grain | Cột và khóa không nhất quán, KPI mơ hồ | Viết một câu định nghĩa một hàng fact |
| Cho rằng mọi fact cùng Date/Product/Store có thể JOIN chi tiết | Fan-out và mất các nhóm chỉ có dữ kiện một phía | Tổng hợp từng fact về grain chung, sau đó JOIN |
| Dùng SUM(DISTINCT amount) để chống trùng | Bỏ mất các sự kiện có cùng số tiền | Chỉnh grain và đường JOIN |
| Cộng tồn kho qua nhiều ngày | Tạo “tồn” không có nghĩa nghiệp vụ | Lấy snapshot cuối kỳ hoặc average đã định nghĩa |
| Cộng số đơn theo Category | Một đơn nhiều Category bị đếm nhiều lần | COUNT DISTINCT theo đúng phạm vi và kiểm tra tính cộng được |
| JOIN SCD2 bằng product_code mà không chọn version | Nhân fact theo số phiên bản dimension | FK tới product_key hoặc lookup as-of đúng |
| Chỉ dùng tên cột giống nhau làm bằng chứng conformed | Sai SKU, tenant, phân cấp, hiệu lực | Chuẩn hóa mã và semantic contract |
| Chuyển Returns theo ngày trả thành “tỷ lệ trả của sales ngày đó” | Sai cohort và mẫu số | Nối về lần bán gốc và định nghĩa cohort |
| Đặt tất cả loại sự kiện vào FactEverything | Trộn grain, measure NULL, SUM vô nghĩa | Tách fact theo quy trình và grain |
| Chọn Snowflake chỉ để đạt chuẩn hóa cao hơn | Tăng JOIN, khó lịch sử mà chưa có lợi ích | Đo tải và độ phức tạp quản trị |
| Bỏ fact vì dimension chưa tới | Thiếu doanh thu trong báo cáo | Unknown member/late dimension có đối soát |
| Không chặn nạp lặp khi pipeline retry | Doanh thu bị nhân theo số lần nạp | Unique event ID, idempotency và kiểm thử |
| Dùng giá Product hiện hành để tính doanh thu quá khứ | Thay đổi lịch sử doanh thu | Lưu giá tại giao dịch trong fact |
| Không xác định tiền tệ/múi giờ | Cộng và so sánh sai | Quy ước currency, thời gian, tỷ giá rõ |
| Lưu dimension Category Type 1 nhưng đòi lịch sử as-of | Báo cáo cũ bị phân loại lại | SCD2/phiên bản quan hệ hoặc snapshot |
| Đếm doanh thu theo campaign nhiều–nhiều mà không phân bổ | Nhân doanh thu | Bridge, trọng số hoặc nhãn chỉ tiêu không cộng được |

## 18. Bài tập tình huống có hướng dẫn giải

### Bài 1. Tìm grain của fact

**Đề bài:** Một đơn 501 gồm ba dòng hàng. Hệ thống có bảng fact với khóa order_id và product_key, lưu quantity, unit_price và discount_amount. Có chắc grain là một dòng bán không?

**Gợi ý:** **Chưa chắc.** Một Product có thể xuất hiện nhiều lần trong cùng một Order theo khuyến mãi/kho/lô hàng, nên (order_id, product_key) không nhất thiết là khóa duy nhất của dòng. Cần định danh nguồn như **(order_id, line_no)** hoặc source_sales_line_id và xác định cách xử lý hủy/điều chỉnh. Chỉ khi grain rõ mới chọn khóa và measure.

### Bài 2. Chọn star hay snowflake

**Đề bài:** 99% báo cáo cần doanh thu theo Category, Brand. Dimension Product có vài triệu phiên bản SCD2, cấu trúc Category thay đổi theo lịch sử. Có nên tự động chuyển thành Snowflake vì Category lặp nhiều?

**Gợi ý:** Không tự động. Cần đánh giá dung lượng, JOIN, mức thay đổi taxonomy, chính sách phân loại lịch sử và khả năng dùng chung Category. Star với thuộc tính phân loại lưu theo phiên bản có thể dễ phục vụ as-of; Snowflake có thể giảm lặp nhưng thêm quy tắc lịch sử. So sánh thực nghiệm trên truy vấn, engine và dữ liệu đại diện.

### Bài 3. Tại sao không JOIN fact trực tiếp?

**Đề bài:** Một ngày có 5 dòng bán và 3 dòng trả cùng Product/Store. JOIN trực tiếp theo ngày–Product–Store tạo tối đa bao nhiêu cặp, nếu mọi hàng đều khớp?

**Gợi ý:** **5 × 3 = 15 hàng**. SUM tiền bán hoặc hoàn trên kết quả sẽ lặp dữ liệu. Tổng hợp Sales và Returns riêng về một hàng/ngày–Product–Store, rồi JOIN kết quả tổng hợp.

### Bài 4. Tồn kho cuối kỳ

**Đề bài:** Một cửa hàng có tồn cuối ngày 20, 17 và 24 chiếc trong ba ngày. Tồn cuối kỳ là bao nhiêu?

**Gợi ý:** Nếu ba snapshot thuộc cùng Product/Store và ngày thứ ba là cuối kỳ, tồn cuối kỳ là **24**, không phải 61. Nếu muốn tồn trung bình ba ngày có đủ snapshot, là (20 + 17 + 24)/3; phải nói rõ cách tính và ngày thiếu.

### Bài 5. Dùng conformed dimension

**Đề bài:** Hệ Sales dùng product_id = 10 cho một SKU; hệ Warehouse dùng product_id = 10 cho một dòng sản phẩm có nhiều SKU. Hai nhóm đều đặt tên cột product_id. Có thể drill-across ngay không?

**Gợi ý:** Không. Hai trường có **ngữ nghĩa khác grain**. Cần bảng ánh xạ SKU–ProductGroup, định nghĩa mức hạt chung và cách tổng hợp/cấp lại Product dimension trước khi so sánh.

### Bài 6. Type 2 và JOIN sai

**Đề bài:** Product P-001 có hai dòng DimProduct SCD2, một từ tháng 1–10, một từ tháng 11. Fact tháng 9 trỏ product_key của phiên bản tháng 9. Vì sao JOIN theo product_code có thể làm doanh thu tăng gấp đôi?

**Gợi ý:** Vì product_code khớp **cả hai phiên bản**, tạo hai hàng từ một fact. JOIN theo surrogate product_key đã lưu trong fact hoặc áp điều kiện ngày hiệu lực đúng tại bước tra cứu phiên bản.

### Bài 7. Tỷ lệ trả hàng

**Đề bài:** Trong tháng 10 có tiền bán 100 triệu, tiền hoàn 8 triệu. Có thể báo “8% đơn bán tháng 10 bị trả hàng” không?

**Gợi ý:** Không. 8/100 là **tỷ lệ tiền hoàn trong tháng so với tiền bán trong tháng**, chưa chắc cùng những đơn. Muốn tỷ lệ trả theo lô bán tháng 10, phải truy original_sales_line/order, xác định đơn vị đếm (dòng/chiếc/đơn), cửa sổ cho phép trả và mẫu số phù hợp.

### Bài 8. Mục tiêu tháng và thực tế dòng bán

**Đề bài:** Cửa hàng có mục tiêu tháng 100 triệu, tháng đó có 1.000 dòng bán. JOIN mục tiêu vào từng dòng rồi SUM(target_amount) sẽ trả bao nhiêu?

**Gợi ý:** Nếu lặp 100 triệu trên mỗi dòng, phép SUM thành **100 tỷ**, sai. Tổng hợp bán hàng lên tháng–cửa hàng trước, sau đó JOIN fact mục tiêu đúng grain.

### Bài 9. Campaign và Bridge

**Đề bài:** Một dòng bán 100.000 đồng thuộc Campaign A và B. Nếu báo cáo cần tổng phân bổ đúng 100.000, bridge nên biểu diễn thế nào?

**Gợi ý:** Ví dụ A weight = 0,6 và B weight = 0,4; báo cáo SUM(amount × weight) cho 60.000 và 40.000. Phải kiểm tra tổng weight bằng 1 ở **tập hàng cùng sales_line_key**; CHECK từng hàng chỉ kiểm soát [0,1].

### Bài 10. Giao dịch đến muộn

**Đề bài:** Ngày 15/11 pipeline nhận một dòng bán có event_time 30/10, Product đã đổi Category từ 01/11. Fact nên trỏ dimension version nào?

**Gợi ý:** Nếu báo cáo **theo phân loại tại thời điểm bán**, tra version có hiệu lực ngày 30/10, không dùng version hiện hành ngày nạp. Nếu chính sách báo cáo theo Category hiện hành, cung cấp ánh xạ/current view rõ ràng; đừng trộn hai chế độ.

### Bài 11. Một Order nhiều Product

**Đề bài:** Báo cáo COUNT(DISTINCT order_id) theo ba Category lần lượt là 30, 40, 50. Có thể nói tổng 120 đơn không?

**Gợi ý:** Không nếu một Order chứa Product thuộc nhiều Category. Cùng Order có thể được tính ở nhiều nhóm, nên tổng các nhóm có thể lớn hơn tổng distinct Order toàn phạm vi. Hãy định nghĩa quy tắc gán đơn cho category nếu chỉ cần mỗi đơn thuộc một nhóm.

### Bài 12. Đảm bảo bảng fact snapshot không bị trùng

**Đề bài:** FactInventoryDaily grain là ngày–sản phẩm–cửa hàng. Một job retry nạp hai bản ghi cùng bộ khóa nhưng số tồn khác nhau. Hệ thống nên làm gì?

**Gợi ý:** PK/UNIQUE trên (snapshot_date_key, product_key, store_key) giúp phát hiện trùng. Pipeline cần quyết định bản nào đúng (theo source version, timestamp, quy trình đối soát), thực hiện upsert có kiểm soát và ghi log lỗi; không cộng hai snapshot.

## 19. Checklist nghiệm thu mô hình phân tích

Trước khi chốt schema hoặc dashboard, kiểm tra:

1. **Grain:** mỗi fact có một câu định nghĩa không nhập nhằng; có khóa nguồn chống nạp trùng.
2. **Conformed dimensions:** dùng cùng miền định danh, phân loại, quy tắc lịch sử, đơn vị đo và tenant khi drill-across.
3. **Measure:** đã phân loại additive, semi-additive, non-additive; biết phép tổng hợp nào có ý nghĩa.
4. **Fact constellation:** không JOIN chi tiết các fact độc lập; mỗi fact được tổng hợp về cùng reporting grain trước khi ghép.
5. **Date roles:** ngày bán, ngày trả, ngày snapshot và ngày lập báo cáo được phân biệt.
6. **SCD:** version dimension được tra đúng theo thời điểm; xử lý khoảng hiệu lực chồng lấp và thay đổi muộn.
7. **Đối soát:** số fact, số lượng, tiền và các nhóm unknown khớp dữ liệu nguồn theo chính sách.
8. **Đa trị:** nhiều Campaign/Category có bridge và quy tắc khử trùng/phân bổ để không nhân chỉ tiêu.
9. **Thực thi:** test trên dữ liệu có quy mô và độ lệch phù hợp, kiểm tra plan, index/partition/cluster, chi phí nạp và lịch sử.
10. **Diễn giải:** dashboard nêu rõ grain, tiền tệ, cách xử lý hoàn/hủy, độ trễ và lịch sử Category.

## 20. Ghi nhớ

- **Star schema:** một fact ở trung tâm, các dimension nối trực tiếp; thường dễ dùng và giảm JOIN mô tả.
- **Snowflake schema:** một hoặc nhiều dimension được tách thành cấp chuẩn hóa; giảm trùng dữ liệu mô tả nhưng tăng yêu cầu JOIN và quản trị lịch sử.
- **Fact constellation:** nhiều bảng fact độc lập theo các **grain khác nhau**, dùng chung những **conformed dimensions** để phân tích liên quy trình.
- **Grain quyết định phép tính.** Không cộng inventory qua ngày, không cộng ratio/COUNT DISTINCT sai phạm vi, không nhân doanh thu qua join nhiều–nhiều.
- **Drill-across cần multipass:** tổng hợp từng fact về cùng chiều và grain báo cáo, **sau đó** JOIN các kết quả.
- **Conformed không chỉ là trùng tên cột:** phải thống nhất định danh, quy tắc lịch sử, phạm vi tenant, phân cấp và ý nghĩa vai trò chiều.
- **SCD2 và late-arriving data** là vấn đề của toàn chuỗi nguồn–ETL–fact–dimension, không phải chỉ thêm hai cột valid_from/valid_to.

Một mô hình phân tích tốt không chỉ vẽ được ba sơ đồ khác nhau. Nó cho phép người đọc định nghĩa chính xác **mỗi hàng đại diện cho điều gì, các bảng có thể kết hợp ở mức nào và khi nào một chỉ tiêu được phép cộng**, đồng thời kiểm chứng được kết quả bằng dữ liệu và quy tắc nghiệp vụ.
