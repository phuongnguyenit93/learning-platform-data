# Khóa nghiệp vụ, khóa thay thế và thuộc tính mô tả của chiều

## 1. Bài toán: một sản phẩm có nhiều tên, mã và phiên bản phân loại

Trong module **DATABASE_DATA_MODELING**, một thiết kế tốt phải chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, khóa, ràng buộc và lược đồ vật lý có thể giải thích, kiểm chứng và tiến hóa. Đối với chương **Bảng chiều**, câu hỏi quan trọng không chỉ là “bảng sản phẩm có những cột nào?”, mà là:

> Khi một sản phẩm thay đổi tên, thương hiệu hoặc danh mục, các giao dịch quá khứ phải liên kết đến **sản phẩm logic** hay **phiên bản mô tả sản phẩm tại lúc giao dịch**?

Giả sử một sản phẩm có mã **P01** trong hệ thống ERP:

- Từ 01/01/2026 đến trước 01/08/2026, sản phẩm thuộc danh mục **FOOD**.
- Từ 01/08/2026, doanh nghiệp chuyển nó sang danh mục **GIFT**.
- Đơn bán **L-501** ngày 15/07/2026 và đơn **L-502** ngày 15/08/2026 đều bán cùng sản phẩm logic P01.
- Báo cáo **theo danh mục tại lúc bán** cần đưa L-501 vào FOOD và L-502 vào GIFT.

Nếu bảng chiều sản phẩm chỉ có một hàng P01 với danh mục hiện tại GIFT, báo cáo tháng 7 sẽ bị viết lại theo danh mục mới. Nếu tạo một mã sản phẩm nghiệp vụ mới mỗi khi đổi danh mục, lại làm mất tính liên tục của cùng một sản phẩm.

Để tránh hai lỗi đó, phải phân biệt:

1. **Khóa nghiệp vụ (business/natural key)**: định danh đối tượng trong phạm vi hệ thống nguồn.
2. **Khóa thay thế (surrogate key)**: định danh một hàng trong mô hình chiều; với SCD Type 2 thường là **một phiên bản** của đối tượng.
3. **Thuộc tính mô tả (descriptive attributes)**: các thông tin dùng để lọc, nhóm, hiển thị và diễn giải sự kiện theo chiều, ví dụ tên, thương hiệu, danh mục, vùng.

Một hệ thống phức tạp còn có **khóa ổn định của thực thể (durable key)** để nối nhiều phiên bản của cùng đối tượng mà không nhầm với khóa phiên bản. Bài học giải thích khi nào lớp khóa này hữu ích, thay vì mặc định mọi hệ thống phải dùng ba loại khóa.

**Mục tiêu:** thiết kế được bảng chiều có grain đúng; chọn khóa và phạm vi duy nhất; hiểu sự khác biệt giữa ID nguồn với surrogate key; xây lịch sử thuộc tính bằng SCD; gắn fact vào đúng phiên bản; xử lý nguồn trùng mã, dữ liệu đến muộn, dữ liệu không xác định và kiểm tra chất lượng.

## 2. Bảng chiều chứa gì và phục vụ câu hỏi nào?

**Dimension table (bảng chiều)** mô tả các đối tượng hoặc ngữ cảnh mà một phép đo cần phân tích. Nó bổ sung ý nghĩa cho **fact table**, nơi lưu số đo tại một grain đã định.

Ví dụ:

~~~text
fact_sales_line
  source_line_id = L-501
  sale_date = 2026-07-15
  product_version_key = 101
  quantity = 2
  net_amount = 180000 VND

dim_product
  product_version_key = 101
  product_business_key = P01
  product_name = Bánh dinh dưỡng
  category_code = FOOD
  category_name = Thực phẩm
~~~

Từ một số đo **180.000 VND**, dimension cho phép hỏi doanh thu theo danh mục, thương hiệu, nhóm sản phẩm hoặc thuộc tính khác.

| Khái niệm | Ví dụ | Mục đích |
|---|---|---|
| **Fact** | Một dòng bán hàng đã ghi nhận | Lưu phép đo và khóa tới các chiều |
| **Measure** | Số lượng, doanh thu thuần, giá vốn | SUM, COUNT hoặc tính chỉ số |
| **Dimension** | Sản phẩm, khách hàng, cửa hàng, ngày | Lọc, nhóm, drill-down |
| **Thuộc tính chiều** | Danh mục, thương hiệu, vùng, phân khúc | Giải thích số đo |
| **Khóa nghiệp vụ** | ERP/P01 | Nhận diện sản phẩm theo nguồn |
| **Khóa thay thế phiên bản** | product_sk = 101 | Nhận diện một hàng mô tả có hiệu lực cụ thể |

Bảng chiều thường có **nhiều thuộc tính mô tả, ít số đo**, và thường có số dòng ít hơn fact. Nhưng đây là đặc điểm phổ biến, không phải định luật. Một dimension khách hàng hoặc thiết bị có thể rất lớn và biến động nhiều.

### 2.1. Grain của dimension cũng phải được tuyên bố

Với dimension không lưu lịch sử (Type 1), một hàng có thể là:

> Một sản phẩm logic đang được mô tả theo thông tin mới nhất.

Với SCD Type 2, một hàng là:

> Một **phiên bản mô tả** của một sản phẩm logic, có hiệu lực trong một khoảng ngày được xác định.

Hai grain khác nhau dẫn đến hai loại khóa duy nhất khác nhau. Nếu chưa định nghĩa grain, các tranh luận về PRIMARY KEY, UNIQUE và JOIN sẽ không có cơ sở.

## 3. Khóa nghiệp vụ: ID mà hệ thống nguồn hiểu

**Business key (BK)** là mã hoặc tập thuộc tính được nguồn nghiệp vụ dùng để nhận diện một đối tượng.

Ví dụ:

- Mã sản phẩm **P01** trong hệ thống ERP.
- Mã khách hàng **C-482** của CRM.
- Mã cửa hàng **HCM-07** của hệ thống bán lẻ.
- Mã chi nhánh + số tài khoản trong một hệ thống ngân hàng.
- Mã pháp nhân + số hợp đồng trong một nền tảng đa doanh nghiệp.

Khóa nghiệp vụ có thể là **khóa tự nhiên** đã tồn tại trong nghiệp vụ, hoặc mã định danh do hệ thống nguồn phát hành. Điều quan trọng là nó **có ngữ nghĩa nhận diện đối tượng trong phạm vi đã xác định**, không nhất thiết do con người tự đặt.

### 3.1. Phạm vi duy nhất: P01 có thật sự là toàn cục?

Nếu ERP Việt Nam và ERP Thái Lan đều có sản phẩm mã P01, hai mã này không mặc nhiên là một sản phẩm.

Một khóa nghiệp vụ đầy đủ có thể là:

~~~text
(tenant_id, source_system, product_bk)

(1, "ERP-VN", "P01") ≠ (1, "ERP-TH", "P01")
(1, "ERP-VN", "P01") ≠ (2, "ERP-VN", "P01")
~~~

Khi mô hình hóa, phải đặt câu hỏi:

1. Ai cấp mã và trong phạm vi nào nó là duy nhất?
2. Mã có thể bị tái sử dụng sau khi sản phẩm ngừng bán không?
3. Một sản phẩm có thể đổi mã nghiệp vụ không?
4. Hai nguồn có thể dùng hai mã cho cùng một đối tượng không?
5. Mã có bị biến đổi định dạng do khoảng trắng, chữ hoa/thường hoặc số 0 ở đầu không?
6. Có nhiều tenant, pháp nhân, quốc gia hay namespace cần tách riêng không?

Một ràng buộc **UNIQUE(product_bk)** đơn lẻ có thể là sai nếu mã chỉ duy nhất trong **(tenant, source)**. Ngược lại, đặt quá nhiều chiều vào khóa có thể tạo hai bản ghi khác nhau cho cùng một sản phẩm khi nguồn thay đổi trường không thuộc danh tính.

### 3.2. Business key phải được chuẩn hóa thận trọng

Chuỗi **"0012"** không nhất thiết bằng **"12"**. Nếu mã sản phẩm có số 0 ở đầu mang ý nghĩa, không chuyển mã thành integer.

Hai chuỗi **"p01"** và **"P01"** có thể được coi là cùng hoặc khác đối tượng tùy quy định nguồn. Cần thống nhất chuẩn hóa, collation và quy tắc tìm kiếm trước khi đặt unique constraint. Không tự biến mọi BK thành uppercase nếu nguồn phân biệt chữ hoa/thường.

Khi nguồn sử dụng mã có dấu gạch, khoảng trắng hoặc tiền tố, ETL phải tách **mã gốc** với **mã đã chuẩn hóa** nếu cần đối soát. Chuẩn hóa làm mất thông tin không được coi là vô hại chỉ vì JOIN chạy được.

### 3.3. Khóa nghiệp vụ không luôn ổn định mãi mãi

Một cửa hàng được đổi mã từ **HCM-07** thành **HCM-107**; một khách được hợp nhất hồ sơ; sản phẩm chuyển sang ERP mới và nhận mã mới. Điều đó đặt ra hai nhu cầu riêng:

- Giữ **các giá trị mã đã từng dùng** để tra cứu chứng từ nguồn.
- Vẫn biết đây là **một đối tượng logic** sau khi đổi mã, nếu nghiệp vụ xác nhận.

Nếu thay đổi BK làm mất khả năng liên kết lịch sử, cần một bảng ánh xạ alias/crosswalk hoặc một durable key được quản trị. Không tự gộp hai mã vì tên sản phẩm giống nhau; hợp nhất danh tính phải có quy trình kiểm chứng.

## 4. Khóa thay thế: ID nội bộ của hàng dimension

**Surrogate key (SK)** là khóa do mô hình dữ liệu cấp để định danh một hàng, không phụ thuộc trực tiếp vào cách viết mã nghiệp vụ.

Ví dụ:

| product_sk | product_bk | category_code | Hiệu lực |
|---:|---|---|---|
| 101 | P01 | FOOD | [01/01, 01/08) |
| 102 | P01 | GIFT | [01/08, chưa kết thúc) |

Cả hai hàng cùng BK là P01 nhưng có **product_sk khác nhau**, vì chúng là hai phiên bản mô tả ở hai giai đoạn.

**product_sk = 101** không có nghĩa sản phẩm đứng thứ 101, thuộc danh mục 101 hoặc được bán trước các sản phẩm có số lớn hơn. Đây là ID kỹ thuật của **một phiên bản chiều**.

### 4.1. Vì sao fact nên tham chiếu surrogate key phiên bản?

Nếu fact dòng bán chỉ lưu product_bk = P01 rồi JOIN tới mọi hàng dimension theo P01, một giao dịch có thể khớp cả hai phiên bản FOOD và GIFT. Kết quả JOIN bị **nhân hàng**, doanh thu bị cộng trùng.

Nếu fact lưu **product_sk = 101** đã được gắn đúng theo ngày bán, mỗi dòng tham chiếu một phiên bản mô tả xác định.

~~~text
L-501, ngày 15/07, product_sk=101 → FOOD
L-502, ngày 15/08, product_sk=102 → GIFT
~~~

Khóa ngoại từ fact tới product_sk giúp bảo đảm hàng dimension được tham chiếu tồn tại. Nhưng **FK một mình không chứng minh** rằng phiên bản đó có hiệu lực đúng ngày bán; ETL và kiểm tra chất lượng phải xác nhận điều kiện thời gian.

### 4.2. Ưu và nhược điểm của surrogate key

| Ưu điểm | Đánh đổi |
|---|---|
| Không phụ thuộc việc mã nguồn đổi tên hoặc định dạng | Phải có bước ánh xạ BK → SK |
| Cho phép nhiều phiên bản SCD2 của một đối tượng | Tránh dùng MAX(SK) để suy luận hiện tại |
| Fact FK đơn giản, cố định và thường gọn | Cần quản trị Unknown/unresolved member |
| Hỗ trợ tích hợp nhiều nguồn qua mapping | Cần chính sách chống hợp nhất nhầm danh tính |
| Cách ly hệ thống phân tích khỏi mã nguồn | Tăng độ phức tạp ETL và tái xử lý dữ liệu |

Không phải dimension nào cũng **bắt buộc** có surrogate key. Với chiều ngày bất biến có khóa số YYYYMMDD và quan hệ đơn giản, date_key theo quy ước có thể đủ. Nhưng với SCD2 hoặc tích hợp nhiều nguồn, khóa thay thế thường làm thiết kế rõ ràng và an toàn hơn.

### 4.3. Không dùng số tự tăng làm thước đo thời gian

SK 102 lớn hơn 101 **không chứng minh** phiên bản 102 có ngày hiệu lực muộn hơn trong mọi trường hợp. Một quyết định hồi tố có thể được nạp sau và nhận SK lớn hơn dù nó thuộc khoảng hiệu lực cũ hơn.

Tuyệt đối không dùng **MAX(product_sk)** như quy tắc tổng quát để lấy phiên bản đang có hiệu lực. Hãy dùng **khoảng thời gian hiệu lực** hoặc một điều kiện phiên bản được định nghĩa rõ.

## 5. Durable key: ổn định ở mức đối tượng, khác với version key

Trong các kho dữ liệu có SCD2, đôi khi cần phân biệt:

1. **Business key**: mã nguồn trong namespace nguồn, ví dụ (tenant 1, ERP, P01).
2. **Durable key**: ID nội bộ của **một sản phẩm logic**, không đổi qua các phiên bản.
3. **Version surrogate key**: ID nội bộ của **một phiên bản mô tả**.

Ví dụ:

| tenant | source | product_bk | product_dk | product_sk | Danh mục |
|---|---|---|---:|---:|---|
| 1 | ERP | P01 | 7 | 101 | FOOD |
| 1 | ERP | P01 | 7 | 102 | GIFT |

**product_dk = 7** liên kết hai hàng như cùng một sản phẩm logic. **product_sk** là cái fact dùng để gắn phiên bản lịch sử.

Durable key không được nhầm với khóa “vĩnh viễn không thay đổi trong mọi tình huống”. Nếu hai hồ sơ bị hợp nhất hoặc một hồ sơ bị tách sau điều tra, còn cần chính sách **identity resolution** và lịch sử ánh xạ để không xóa dấu vết nguồn.

Có thể triển khai durable key bằng bảng **product_identity** riêng, hoặc cột durable_key lặp trên các hàng version với quy trình cấp/đối soát. Bài này dùng bảng riêng để có một hàng ổn định cho cơ chế khóa khi cập nhật SCD2.

## 6. Thuộc tính mô tả của chiều: thứ được nhóm, lọc và hiển thị

Một bảng sản phẩm có thể có:

- **Nhận diện và hiển thị**: mã sản phẩm, tên, tên viết tắt.
- **Phân loại**: category_code, category_name, ngành hàng, nhóm sản phẩm.
- **Thương hiệu**: brand_code, brand_name.
- **Đặc tính**: kích cỡ, màu sắc, chất liệu, loại đóng gói.
- **Thuộc tính vận hành**: trạng thái ngừng bán, ngày ra mắt, loại hàng.
- **Thuộc tính được suy ra**: nhóm giá hoặc nhóm tuổi khách hàng tại kỳ đã xác định.
- **Thuộc tính hỗ trợ quản trị**: nguồn, thời điểm nạp, decision_ref, trạng thái xác minh.

Các trường này có thể dùng cho **drill-down**, lọc và phân nhóm. Chúng **không nhất thiết là số đo** dù có kiểu số.

| Thuộc tính | Vai trò | Cần suy nghĩ thêm |
|---|---|---|
| product_name | Nhãn hiển thị | Sửa lỗi chính tả có tạo SCD2 không? |
| category_code | Mã nhóm | Có thay đổi theo thời gian không? |
| category_name | Nhãn nhóm | Có đa ngôn ngữ hoặc đổi tên không? |
| brand_code | Nhóm thương hiệu | Thương hiệu có thể chuyển quyền sở hữu? |
| package_size | Thông số | Là thuộc tính SKU hay cần đơn vị đo? |
| color_code | Biến thể sản phẩm | Có thể khiến SKU là đối tượng logic khác? |
| launch_date | Mốc nghiệp vụ | Ngày lịch theo thị trường hay timestamp? |
| price_band | Phân nhóm dẫn xuất | Dựa vào bảng giá nào, ở thời điểm nào? |
| loaded_at | Metadata ETL | Không phải ngày sản phẩm có hiệu lực |

### 6.1. Chọn grain trước khi đưa thuộc tính vào

Nếu một sản phẩm P01 có ba biến thể màu/kích cỡ, **color** có thể là thuộc tính của một biến thể SKU, không phải thuộc tính đơn trị của product master. Nhồi tất cả màu vào một hàng P01 tạo giá trị đa trị hoặc danh sách khó lọc, dễ làm sai grain.

Có thể chọn:

~~~text
Product (mẫu sản phẩm) 1 -- N ProductVariant/SKU
~~~

Sau đó fact bán hàng thường tham chiếu **SKU cụ thể**, không chỉ product master, nếu mỗi biến thể có giá và tồn kho riêng.

**Không có một bảng chiều “sản phẩm” đúng cho mọi nhu cầu.** Phải quyết định fact bán, tồn kho và hoàn hàng đang đo ở grain SKU, product family hay sản phẩm thương mại.

### 6.2. Thuộc tính mô tả có thể thay đổi theo nhịp khác nhau

Tên sản phẩm sửa chính tả, danh mục đổi theo chiến lược bán hàng và loại thuế đổi theo quy định có những vòng đời khác nhau. Nếu mỗi thay đổi nhỏ đều tạo snapshot toàn bộ dimension, bảng sẽ phình to và fact cần quản lý phiên bản dày đặc.

Phân loại mức cần giữ lịch sử:

- **Bất biến hoặc gần như bất biến**: mã quốc gia theo chuẩn được quản trị.
- **Thay đổi nhưng muốn hiển thị giá trị mới ở mọi kỳ**: sửa lỗi tên sản phẩm.
- **Thay đổi và phải giữ trạng thái tại lúc giao dịch**: danh mục, phân khúc khách, vùng bán.
- **Nhiều giá trị đồng thời**: nhiều tag/danh mục — cần bảng liên kết hoặc bridge.
- **Thuộc tính cần lịch sử riêng**: giá bán theo thị trường, chương trình ưu đãi, trạng thái pháp lý.

Không ép mọi loại thay đổi vào một SCD Type 2 duy nhất nếu chúng cần quan hệ, quyền sở hữu hoặc quy tắc hiệu lực khác nhau.

### 6.3. Code và label không phải cùng một thuộc tính

**category_code = FOOD** thường phù hợp làm giá trị phân loại ổn định; **category_name = Thực phẩm** là nhãn hiển thị, có thể dịch sang ngôn ngữ khác.

Nếu báo cáo đa ngôn ngữ, cân nhắc bảng nhãn theo locale hoặc một semantic layer chuyên dụng thay vì lặp nhiều tên ngôn ngữ trên từng version. Nếu đổi tên category nhưng ý nghĩa không đổi, phải quyết định cập nhật nhãn Type 1 hay coi đó là một phân loại mới.

## 7. Sơ đồ quan hệ: đối tượng logic, phiên bản dimension và fact

~~~mermaid
erDiagram
    PRODUCT_IDENTITY ||--o{ DIM_PRODUCT : "có phiên bản mô tả"
    DIM_PRODUCT ||--o{ FACT_SALES_LINE : "được fact tham chiếu"
    DIM_DATE ||--o{ FACT_SALES_LINE : "ngày bán"
    PRODUCT_IDENTITY {
        bigint product_dk PK
        bigint tenant_id
        text source_system
        text product_bk
    }
    DIM_PRODUCT {
        bigint product_sk PK
        bigint product_dk FK
        text product_name
        text category_code
        daterange valid_period
    }
    DIM_DATE {
        int date_key PK
        date calendar_date
    }
    FACT_SALES_LINE {
        bigint sales_line_sk PK
        text source_line_bk
        bigint product_sk FK
        int date_key FK
        int quantity
        decimal net_amount
    }
~~~

Sơ đồ thể hiện rõ ba quan hệ:

- **ProductIdentity → DimProduct**: một sản phẩm logic có nhiều phiên bản mô tả.
- **DimProduct → FactSalesLine**: một phiên bản mô tả có thể được tham chiếu bởi nhiều dòng bán.
- **DimDate → FactSalesLine**: một ngày chứa nhiều dòng bán.

Khi fact lưu product_sk, nó trỏ tới đúng phiên bản, không trỏ trực tiếp tới product_dk. Tuy nhiên báo cáo muốn gộp tất cả phiên bản của P01 vẫn có thể JOIN **dim_product → product_identity**, rồi nhóm theo product_dk hoặc BK khi phù hợp.

Không phải hệ thống nào cũng cần bảng identity riêng; thiết kế tách bảng này chỉ làm minh họa rõ nhu cầu **khóa bền vững mức thực thể**, đồng thời cung cấp hàng ổn định để khóa khi cập nhật phiên bản.

## 8. Thiết kế PostgreSQL: khóa nghiệp vụ và bảng danh tính

Ví dụ PostgreSQL này dùng **date/daterange** vì phân loại sản phẩm được quy định có hiệu lực theo ngày kinh doanh. Nếu thay đổi cần chính xác theo giờ, hãy chọn **timestamptz/tstzrange**, thống nhất timezone và quy tắc thời điểm giao dịch.

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE product_identity (
    product_dk     bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL,
    source_system  text NOT NULL,
    product_bk     text NOT NULL,

    CONSTRAINT uq_product_business_identity
        UNIQUE (tenant_id, source_system, product_bk),

    CONSTRAINT ck_product_bk_not_blank
        CHECK (length(btrim(product_bk)) > 0),

    CONSTRAINT ck_source_system_not_blank
        CHECK (length(btrim(source_system)) > 0)
);
~~~

Giải thích:

- **product_dk** được warehouse cấp, ổn định qua các phiên bản mô tả.
- **tenant_id + source_system + product_bk** là định danh nguồn đầy đủ theo giả định nghiệp vụ.
- **UNIQUE** bảo đảm không tạo hai identity cho cùng một mã trong cùng nguồn/tenant.
- **CHECK** cấm mã chỉ chứa khoảng trắng, nhưng không tự chuẩn hóa chữ hoa/thường hoặc loại bỏ mọi ký tự không hợp lệ.
- DDL không tự chứng minh mã nguồn không bị tái sử dụng. Nếu mã được tái sử dụng cho đối tượng khác, cần một chính sách mapping có thêm chiều định danh hoặc thời gian.

Số **product_dk** là khóa kỹ thuật cho **đối tượng logic trong kho phân tích**, không phải khóa phiên bản. Một nguồn khác có P01 sẽ tạo product_dk khác trừ khi có quy trình xác nhận hai mã cùng chỉ một đối tượng và ánh xạ vào danh tính chuẩn.

## 9. Thiết kế PostgreSQL: phiên bản chiều và thuộc tính mô tả

Mỗi hàng **dim_product** tương ứng một phiên bản của một product_dk.

~~~sql
CREATE TABLE dim_product (
    product_sk       bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_dk       bigint NOT NULL
                     REFERENCES product_identity(product_dk),
    product_name     text NOT NULL,
    brand_code       text,
    category_code    text NOT NULL,
    category_name    text NOT NULL,
    valid_period     daterange NOT NULL,
    decision_ref     text NOT NULL,
    loaded_at        timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT ck_product_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_product_version_no_overlap
        EXCLUDE USING gist (
            product_dk WITH =,
            valid_period WITH &&
        )
);

CREATE INDEX ix_product_dim_by_entity_start
    ON dim_product (product_dk, lower(valid_period));
~~~

**product_sk** là surrogate key phiên bản; **product_dk** là FK đến identity; **valid_period** mô tả khoảng mà các thuộc tính đi kèm được chấp nhận là có hiệu lực theo nghiệp vụ.

Khoảng dùng quy ước **[valid_from, valid_to)**:

~~~text
[2026-01-01, 2026-08-01)  FOOD
[2026-08-01, không giới hạn) GIFT
~~~

Ngày 01/08 chỉ thuộc phiên bản GIFT. Hai khoảng trên **tiếp giáp nhưng không chồng lấn**.

### 9.1. Ràng buộc database bảo vệ điều gì?

| Ràng buộc | Điều được bảo vệ |
|---|---|
| PRIMARY KEY(product_sk) | Mỗi hàng phiên bản có ID riêng |
| FOREIGN KEY(product_dk) | Mỗi phiên bản thuộc một đối tượng logic có identity |
| NOT NULL | Không bỏ trống các thuộc tính/cột cốt lõi |
| CHECK NOT isempty(valid_period) | Không tạo phiên bản có khoảng rỗng |
| CHECK lower_inc AND NOT upper_inc | Diễn giải biên nửa mở nhất quán |
| EXCLUDE(product_dk WITH =, valid_period WITH &&) | Tối đa một phiên bản mô tả cho cùng sản phẩm tại một ngày |
| INDEX(product_dk, lower(valid_period)) | Hỗ trợ đọc timeline theo sản phẩm khi phù hợp |

**EXCLUDE** ngăn overlap, **không tự ngăn khoảng trống**. Một sản phẩm có thể không có phiên bản ở ngày 05/07 nếu dữ liệu thiếu. Khi ánh xạ fact theo ngày bán, trường hợp ấy phải được nhận diện và xử lý.

Việc dùng **btree_gist** giúp kết hợp so sánh bằng cho bigint với toán tử giao khoảng trong GiST. Một extension cần được triển khai theo chính sách quyền database; migration không nên tự ý thay đổi extension trên môi trường sản xuất.

### 9.2. Metadata ETL không phải thời gian hiệu lực

**loaded_at** nói hệ thống đổ dữ liệu vào kho lúc nào, không nói sản phẩm thuộc danh mục đó từ ngày nào. **decision_ref** giúp truy vết quyết định phân loại.

Một phiên bản có thể được nạp ngày 10/08 nhưng có hiệu lực hồi tố từ 01/08. Nếu dùng loaded_at làm valid_from, báo cáo các giao dịch từ 01/08 tới trước 10/08 sẽ sai.

Nếu yêu cầu còn phải trả lời **“ngày 05/08 kho phân tích từng tin sản phẩm thuộc nhóm nào?”**, hãy bổ sung known/system time hoặc snapshot/revision lịch sử; một loaded_at trên hàng đã UPDATE chưa đủ làm bitemporal.

## 10. Dữ liệu minh họa: hai phiên bản của một sản phẩm

~~~sql
INSERT INTO product_identity (
    product_dk, tenant_id, source_system, product_bk
)
VALUES (7, 1, 'ERP', 'P01');

INSERT INTO dim_product (
    product_sk, product_dk, product_name,
    brand_code, category_code, category_name,
    valid_period, decision_ref
)
VALUES
(
    101, 7, 'Bánh dinh dưỡng',
    'BR-N', 'FOOD', 'Thực phẩm',
    daterange(DATE '2026-01-01', DATE '2026-08-01', '[)'),
    'CATEGORY-2026-H1'
),
(
    102, 7, 'Bánh dinh dưỡng',
    'BR-N', 'GIFT', 'Quà tặng',
    daterange(DATE '2026-08-01', NULL, '[)'),
    'CATEGORY-2026-AUG'
);
~~~

Trong dữ liệu mẫu, SK được chỉ định cụ thể để dễ theo dõi. **Trong ETL thực tế**, nên để hệ thống cấp ID và sử dụng kết quả INSERT/RETURNING hoặc bảng mapping; không hardcode 101/102 rồi coi chúng có nghĩa nghiệp vụ.

Truy vấn dòng thời gian:

~~~sql
SELECT
    i.tenant_id,
    i.source_system,
    i.product_bk,
    p.product_dk,
    p.product_sk,
    p.category_code,
    lower(p.valid_period) AS valid_from,
    upper(p.valid_period) AS valid_to,
    p.decision_ref
FROM product_identity i
JOIN dim_product p
  ON p.product_dk = i.product_dk
WHERE i.tenant_id = 1
  AND i.source_system = 'ERP'
  AND i.product_bk = 'P01'
ORDER BY lower(p.valid_period);
~~~

Kết quả có hai hàng, cùng BK nhưng khác SK và khác khoảng hiệu lực.

### 10.1. Tìm phiên bản đúng tại một ngày

~~~sql
SELECT p.product_sk, p.product_name, p.category_code
FROM product_identity i
JOIN dim_product p
  ON p.product_dk = i.product_dk
WHERE i.tenant_id = 1
  AND i.source_system = 'ERP'
  AND i.product_bk = 'P01'
  AND p.valid_period @> DATE '2026-07-15';
-- product_sk = 101, category_code = FOOD
~~~

Đổi ngày hỏi thành **2026-08-15** sẽ chọn SK 102 và danh mục GIFT.

Toán tử **@>** trong PostgreSQL kiểm tra khoảng bên trái chứa ngày bên phải. Đây là phép tra theo **business time**, không phải tra theo thời điểm bản ghi được nạp.

## 11. Fact table: tham chiếu khóa phiên bản, không tham chiếu nhầm mã nguồn

Ví dụ một dòng fact là **một dòng bán đã được ghi nhận**. Mỗi dòng chỉ thuộc một sản phẩm (phiên bản), một ngày bán và có số đo.

~~~sql
CREATE TABLE dim_date (
    date_key      integer PRIMARY KEY, -- YYYYMMDD trong ví dụ
    calendar_date date NOT NULL UNIQUE
);

CREATE TABLE fact_sales_line (
    sales_line_sk  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL,
    sales_source   text NOT NULL,
    source_line_bk text NOT NULL,
    order_bk       text NOT NULL,
    date_key       integer NOT NULL REFERENCES dim_date(date_key),
    product_sk     bigint NOT NULL REFERENCES dim_product(product_sk),
    quantity       integer NOT NULL CHECK (quantity > 0),
    currency_code  char(3) NOT NULL,
    net_amount     numeric(18, 2) NOT NULL,

    CONSTRAINT uq_sales_line_from_source
        UNIQUE (tenant_id, sales_source, source_line_bk)
);

CREATE INDEX ix_fact_sales_date_product
    ON fact_sales_line (date_key, product_sk);
~~~

Ở đây:

- **source_line_bk** định danh dòng bán từ hệ thống nguồn trong phạm vi **tenant_id + sales_source**.
- **sales_line_sk** định danh hàng fact trong kho phân tích.
- **order_bk** là một *degenerate dimension*: định danh đơn dùng COUNT DISTINCT và truy vết, không nhất thiết có bảng chiều riêng.
- **product_sk** là FK tới **phiên bản mô tả sản phẩm**; fact không dùng product_dk thay cho nó.
- **date_key** là FK tới chiều ngày.

Sự khác biệt giữa **sales_source** và **source_system** của sản phẩm là có chủ ý: đơn bán có thể từ hệ thống POS, còn mã sản phẩm có thẩm quyền từ ERP. ETL phải tìm ra mapping đúng giữa các nguồn; không mặc định hai trường source bằng nhau.

### 11.1. Gắn hai giao dịch vào hai phiên bản

~~~sql
INSERT INTO dim_date (date_key, calendar_date)
VALUES
    (20260715, DATE '2026-07-15'),
    (20260815, DATE '2026-08-15');

INSERT INTO fact_sales_line (
    tenant_id, sales_source, source_line_bk,
    order_bk, date_key, product_sk,
    quantity, currency_code, net_amount
)
VALUES
    (1, 'POS', 'L-501', 'O-100', 20260715, 101, 2, 'VND', 180000),
    (1, 'POS', 'L-502', 'O-101', 20260815, 102, 1, 'VND', 120000);
~~~

Kết quả mong đợi:

| Dòng bán | Ngày | BK sản phẩm | SK phiên bản | Danh mục đã chốt | Net |
|---|---|---|---:|---|---:|
| L-501 | 15/07 | P01 | 101 | FOOD | 180.000 VND |
| L-502 | 15/08 | P01 | 102 | GIFT | 120.000 VND |

Đây là ví dụ **grain dòng bán**; số lượng và tiền được cộng theo dòng khi cùng đơn vị, loại tiền và quy tắc ghi nhận. Nếu fact chứa dữ liệu nhiều loại tiền tệ, phải lọc hoặc quy đổi trước khi SUM.

### 11.2. Vì sao FK chưa đủ để kiểm chứng mapping?

FK chỉ bảo đảm product_sk 101 tồn tại trong dim_product. Nó **không** ngăn việc ETL gắn L-502 ngày 15/08 vào product_sk 101, dù khoảng hiệu lực của 101 kết thúc trước 01/08.

Vì vậy cần kiểm tra:

~~~sql
SELECT
    f.source_line_bk,
    d.calendar_date,
    p.product_sk,
    p.valid_period
FROM fact_sales_line f
JOIN dim_date d ON d.date_key = f.date_key
JOIN dim_product p ON p.product_sk = f.product_sk
WHERE NOT (p.valid_period @> d.calendar_date);
-- Với dữ liệu mẫu đúng, không có hàng.
~~~

Khi có multi-tenant, phải đối soát thêm **tenant của fact** với **identity của sản phẩm**; FK trên product_sk đơn lẻ cũng không chứng minh chúng cùng tenant. Có thể tăng bảo đảm bằng mô hình composite key/FK tương ứng, hoặc validation ETL bắt buộc ở ranh giới nạp dữ liệu.

## 12. Hai cách nhóm lịch sử: as-was và as-is

Khi P01 đổi FOOD → GIFT, có hai báo cáo khác nhau nhưng đều có thể hợp lệ.

**As-was** (*theo phân loại tại lúc bán*): các fact tháng 7 nằm ở FOOD vì fact trỏ SK 101; tháng 8 nằm ở GIFT vì fact trỏ SK 102.

~~~sql
SELECT
    p.category_code,
    SUM(f.net_amount) AS net_sales
FROM fact_sales_line f
JOIN dim_product p ON p.product_sk = f.product_sk
WHERE f.currency_code = 'VND'
GROUP BY p.category_code
ORDER BY p.category_code;
-- FOOD = 180000, GIFT = 120000
~~~

**As-is** (*theo phân loại tại ngày tham chiếu hiện được chọn*): nhóm doanh thu lịch sử theo danh mục của sản phẩm ở **ngày đánh giá hiện tại**. Trong ví dụ chọn 15/11/2026:

~~~sql
SELECT
    current_p.category_code,
    SUM(f.net_amount) AS net_sales
FROM fact_sales_line f
JOIN dim_product sold_p
  ON sold_p.product_sk = f.product_sk
JOIN dim_product current_p
  ON current_p.product_dk = sold_p.product_dk
 AND current_p.valid_period @> DATE '2026-11-15'
WHERE f.currency_code = 'VND'
GROUP BY current_p.category_code;
-- GIFT = 300000, theo định nghĩa as-is ngày 15/11
~~~

Truy vấn as-is này **chỉ đúng trong phạm vi có đúng một phiên bản cho mỗi sản phẩm ở ngày tham chiếu**. Nếu dimension có gap tại ngày ấy, INNER JOIN sẽ loại fact; cần kiểm soát thiếu mapping. Nếu sản phẩm đổi danh mục lần nữa sau 15/11, as-is ở một ngày khác có thể khác.

**Không được đổi nhãn báo cáo** từ as-was sang as-is mà không thông báo. Sự khác biệt thuộc **định nghĩa phân tích**, không phải lỗi số học.

## 13. Cập nhật SCD Type 2: đóng phiên bản cũ, tạo phiên bản mới

Khi category thay đổi, cần giữ cả dữ liệu lịch sử để fact cũ tiếp tục trỏ tới đúng phiên bản. Sơ đồ chuyển đổi:

~~~text
Trước thay đổi:
SK 101: P01, FOOD, [01/01, +∞)

Sau quyết định hiệu lực từ 01/08:
SK 101: P01, FOOD, [01/01, 01/08)
SK 102: P01, GIFT, [01/08, +∞)
~~~

Ví dụ transaction **minh họa cho tình trạng ban đầu chỉ có SK 101 mở vô hạn**. Không chạy lại nguyên xi sau khi dữ liệu mẫu phần 10 đã tạo sẵn SK 102.

~~~sql
BEGIN;

-- Khóa identity ổn định của P01 để các lệnh đổi phiên bản
-- cùng sản phẩm xử lý có thứ tự.
SELECT product_dk
FROM product_identity
WHERE tenant_id = 1
  AND source_system = 'ERP'
  AND product_bk = 'P01'
FOR UPDATE;

UPDATE dim_product
SET valid_period = daterange(
    lower(valid_period),
    DATE '2026-08-01',
    '[)'
)
WHERE product_dk = 7
  AND lower(valid_period) < DATE '2026-08-01'
  AND upper_inf(valid_period)
RETURNING product_sk;

-- Ứng dụng phải kiểm tra UPDATE đúng 1 hàng,
-- nếu không thì ROLLBACK để tính lại timeline.

INSERT INTO dim_product (
    product_dk, product_name, brand_code,
    category_code, category_name, valid_period, decision_ref
)
VALUES (
    7, 'Bánh dinh dưỡng', 'BR-N',
    'GIFT', 'Quà tặng',
    daterange(DATE '2026-08-01', NULL, '[)'),
    'CATEGORY-2026-AUG'
)
RETURNING product_sk;

COMMIT;
~~~

**Chỉ nên COMMIT** nếu đã xác minh phạm vi quyết định, số hàng UPDATE, các đoạn hiệu lực và khả năng tuân thủ quy tắc. Nếu INSERT lỗi, transaction phải rollback để không chỉ còn phiên bản cũ đã bị đóng.

Nếu đã có phiên bản được lên lịch từ 15/09, một UPDATE cắt khoảng mở vô hạn và INSERT từ 01/08 đến vô hạn sẽ không đúng. Cần **đọc timeline thực**, xác định đoạn bị ảnh hưởng, chia khoảng tại các mốc phù hợp và giữ các quyết định tương lai không bị thay thế.

### 13.1. Đồng thời và khóa định danh ổn định

Khóa hàng **product_identity** là một điểm đồng bộ hữu ích vì hàng ấy tồn tại ổn định qua nhiều phiên bản. Nếu chỉ khóa hàng dimension hiện hành, có thể không khóa được trường hợp chưa tồn tại phiên bản hoặc có hai thao tác chèn cạnh tranh.

Ràng buộc **EXCLUDE** vẫn cần thiết, vì nó bảo vệ database ngay cả khi một đường ghi bỏ qua giao thức cập nhật. Transaction, kiểm tra version/revision và retry phải phối hợp để không làm mất quyết định đúng.

### 13.2. Chỉ đổi tên chính tả có cần SCD2?

Nếu product_name ban đầu là **“Bánh dĩnh dưỡng”** do nhập sai và nghiệp vụ muốn mọi báo cáo lịch sử hiển thị **“Bánh dinh dưỡng”**, cập nhật Type 1 có thể phù hợp:

~~~sql
UPDATE dim_product
SET product_name = 'Bánh dinh dưỡng'
WHERE product_dk = 7;
~~~

Lệnh này chủ động thay nhãn ở mọi phiên bản của cùng sản phẩm. Nó **không** giữ tên sai đã hiển thị trước đây; nếu phải giải trình, nên lưu audit/decision riêng. Với đổi tên thương mại có hiệu lực từ một ngày cụ thể, SCD2 có thể đúng hơn.

Nguyên tắc: **thuộc tính nào được giữ lịch sử phải dựa vào câu hỏi báo cáo và nghiệp vụ**, không phải cứ một UPDATE là tạo phiên bản mới.

## 14. Unknown member, dữ liệu đến muộn và ánh xạ chưa xác định

Thực tế, fact có thể đến trước dimension. Ví dụ POS gửi L-503 có product_bk = P09, nhưng ERP chưa đồng bộ sản phẩm P09.

Các phương án:

| Phương án | Khi phù hợp | Điều cần kiểm soát |
|---|---|---|
| **Quarantine/staging** | Yêu cầu dữ liệu chính xác trước xuất bản | Ghi nguồn và lý do chưa ánh xạ; có retry |
| **Unknown dimension member** | Cần nạp fact đúng hạn nhưng có nhãn chưa biết | Không lẫn Unknown với sản phẩm thật |
| **Inferred member** | Có BK đã biết nhưng thiếu thuộc tính mô tả | Bổ sung thuộc tính khi dimension tới, giữ danh tính theo quy tắc |
| **Late-arriving restatement** | Phải sửa khóa phiên bản fact khi dữ liệu đầy đủ | Có audit/revision và đối soát ảnh hưởng |

### 14.1. Unknown không giống Not applicable

Có nhiều tình huống:

- **Unknown**: có thể xác định sau.
- **Not applicable**: chiều này không liên quan tới giao dịch.
- **Anonymous**: nghiệp vụ không thu thập danh tính khách.
- **Data error**: mã nguồn không hợp lệ hoặc mâu thuẫn.
- **Deleted/restricted**: dữ liệu không được phép hiển thị.

Gộp tất cả vào một SK Unknown khiến báo cáo khó hiểu và có thể che lỗi nguồn. Nếu dùng các thành viên đặc biệt, chúng cần được khai báo rõ trong dimension và được kiểm tra riêng.

### 14.2. Có nên sửa lại product_sk trong fact?

Nếu fact ban đầu gắn SK Unknown rồi sau đó tìm được phiên bản P09 đúng ngày bán, có thể cập nhật mapping fact theo một quy trình **restatement** được kiểm soát. Nhưng nếu fact đã phát hành ra báo cáo hoặc dùng cho chứng từ chốt, phải biết việc sửa có làm thay đổi kết quả đã công bố không.

Trong event-sourced hoặc immutable fact, có thể ghi bản điều chỉnh hoặc xây lại projection thay vì UPDATE âm thầm. Sự lựa chọn phụ thuộc nghĩa vụ kiểm toán.

### 14.3. Inferred member và SCD2

Nếu chỉ biết BK P09 tại ngày 05/08, hệ thống có thể tạo một identity và một phiên bản mô tả tạm, nhưng **không được tự gán danh mục hiện tại cho toàn bộ quá khứ** khi chưa có bằng chứng. Khi dữ liệu đủ đến, xác định valid period thực sự, tạo hoặc sửa phiên bản và kiểm tra những fact bị ảnh hưởng.

Sự khác biệt quan trọng là một **placeholder có chủ đích** phải được nhận diện rõ với trạng thái chưa xác minh, không được giả làm dữ liệu được nguồn nghiệp vụ xác nhận.

## 15. Nhiều nguồn và quản lý bảng ánh xạ danh tính

Giả sử ERP có mã P01 còn hệ thống PIM có mã PRD-0001; cả hai mô tả cùng một sản phẩm logic theo quyết định của doanh nghiệp. Không thể xác định điều đó chỉ từ cách viết mã.

Một mô hình tích hợp có thể có:

~~~text
canonical_product_id = 7

source mapping:
  ERP / P01      → canonical 7
  PIM / PRD-0001 → canonical 7
~~~

Trong thiết kế phần 8, product_identity dùng một BK theo namespace để cấp product_dk. **Nếu cần gộp hai nguồn vào cùng một đối tượng chuẩn**, có thể bổ sung bảng **source_product_mapping** trỏ nhiều BK nguồn tới một canonical durable key. Không tự sửa lại UNIQUE của identity để đánh đồng P01 ở hai nguồn.

### 15.1. Quy tắc đồng nhất danh tính

Quá trình **identity resolution** có thể dựa vào GTIN/ISBN nếu thích hợp, số chứng nhận, khóa được tổ chức cấp hoặc quyết định quản trị. Cần lưu:

- Nguồn từng mã.
- Căn cứ xác nhận hai mã cùng chỉ một đối tượng.
- Mốc hiệu lực của mapping nếu nó thay đổi.
- Ai phê duyệt việc hợp nhất/tách.
- Cách xử lý fact đã gắn theo mapping cũ.

**Cùng tên sản phẩm không đủ làm bằng chứng cùng danh tính**. Ngược lại, hai sản phẩm cùng mẫu nhưng khác biến thể SKU có thể phải tách vì giá, tồn kho hoặc quyền sở hữu khác nhau.

### 15.2. Tránh FK của fact phụ thuộc trực tiếp vào mã nguồn

Nếu fact dùng mã P01, các hệ thống nguồn khác có thể cung cấp mã P01 với nghĩa khác. JOIN theo mã đơn lẻ rất dễ sai. Khi ETL đã ánh xạ sang product_sk thuộc phiên bản chuẩn, truy vấn phân tích không cần áp lại toàn bộ quy tắc nhận diện nguồn mỗi lần đọc.

Dù vậy, nên giữ **source_system, source_line_bk, source_product_bk** trong staging hoặc lineage để điều tra mapping sai; surrogate key không nên làm mất dấu vết nguồn.

## 16. Thuộc tính mô tả có quan hệ nhiều-nhiều và lịch sử riêng

Một sản phẩm có thể có nhiều **tag**, nằm trong nhiều **bộ sưu tập**, liên kết nhiều **nhà cung cấp** hoặc được bán qua nhiều **kênh**. Không phải mọi giá trị đều phù hợp lưu thành một cột đơn trị trong dim_product.

Ví dụ:

~~~text
P01 → Category FOOD
P01 → Category HEALTHY
~~~

Nếu một fact bán P01 net = 180.000 được JOIN vào hai category, doanh thu sẽ xuất hiện hai lần. Khi đó cần phân biệt:

- **Doanh thu có mặt trong mỗi category**: mỗi category có thể thấy 180.000, nhưng tổng các category không bằng tổng toàn hệ thống.
- **Doanh thu phân bổ theo trọng số**: quy tắc 60/40 cho tổng category bằng 180.000.
- **Danh mục chính duy nhất**: chọn một primary_category có hiệu lực vào ngày bán; các category phụ phục vụ lọc/tag.

Một bridge minh họa:

~~~sql
CREATE TABLE dim_category (
    category_sk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_code text NOT NULL UNIQUE,
    category_name text NOT NULL
);

CREATE TABLE bridge_product_category (
    product_sk bigint NOT NULL REFERENCES dim_product(product_sk),
    category_sk bigint NOT NULL REFERENCES dim_category(category_sk),
    allocation_weight numeric(8, 6) NOT NULL
        CHECK (allocation_weight >= 0 AND allocation_weight <= 1),
    PRIMARY KEY (product_sk, category_sk)
);
~~~

Ở đây quan hệ gắn với **product_sk phiên bản**. Nếu thực thể có nhiều category được version hóa độc lập với những thuộc tính sản phẩm khác, có thể cần bridge theo **product_dk + khoảng hiệu lực quan hệ** để tránh nhân bản toàn bộ product dimension mỗi khi chỉ quan hệ category thay đổi.

Một CHECK trên từng bridge row không chứng minh tổng trọng số bằng 1. Nếu yêu cầu phân bổ đủ doanh thu, cần kiểm tra tổng trọng số theo product_sk hoặc theo từng khoảng thời gian có hiệu lực, kể cả khi cập nhật đồng thời.

## 17. Thuộc tính dẫn xuất và các chiều phân cấp

Một bảng chiều có thể chứa **price_band**, **customer_age_band**, **store_region** hoặc **customer_value_segment** được suy ra từ dữ liệu khác. Đây vẫn có thể là thuộc tính mô tả để lọc/nhóm, nhưng cần kiểm soát:

- **Công thức và nguồn tính**: price_band dựa trên giá gốc hay giá khuyến mại?
- **Thời điểm tính**: segment cuối tháng hay segment khi giao dịch xảy ra?
- **Grain**: tuổi là tuổi tại ngày giao dịch hay tuổi hiện nay?
- **Lịch sử**: nhóm đã từng thay đổi; có cần SCD2 hoặc fact snapshot không?
- **Độ tin cậy**: có tính lại khi dữ liệu nguồn điều chỉnh hồi tố không?

Ví dụ **tuổi khách hiện tại** không phải thuộc tính bất biến để phân tích doanh thu cách đây 5 năm. Nếu nhóm theo tuổi tại lúc mua, phải tính tuổi từ ngày sinh và ngày giao dịch (nếu được phép dùng dữ liệu đó), hoặc lưu nhóm tuổi tại lúc bán theo quy tắc bảo mật. Không JOIN vào age_band hiện tại rồi gọi đó là “tuổi khi mua”.

### 17.1. Hierarchy có thể làm nảy sinh fanout

~~~text
Ngành hàng → Danh mục → Nhóm → SKU
~~~

Đây là một cây chỉ khi một SKU có một nhóm cha tại mốc phân tích. Nếu SKU thuộc đồng thời nhiều nhóm hoặc nhóm đổi theo thời gian, JOIN hierarchy thiếu điều kiện sẽ nhân doanh thu.

Khi thiết kế snowflake dimension, xác định khóa của từng cấp, cardinality và lịch sử các quan hệ; không cho rằng bảng nào có chữ **category** cũng là một-nhiều vĩnh viễn.

## 18. Data quality: kiểm tra tính duy nhất và tính đúng phiên bản

Những kiểm tra quan trọng trước khi đưa mô hình chiều vào báo cáo:

| Kiểm tra | Ý nghĩa |
|---|---|
| BK duy nhất trong namespace (tenant, source) | Không tạo hai identity cho một mã nguồn |
| SK duy nhất và không NULL | Mỗi version row được định danh ổn định |
| FK product_dk hợp lệ | Mọi version có identity |
| Không overlap valid_period của cùng product_dk | Một ngày không có hai phiên bản cạnh tranh |
| Không có khoảng rỗng/sai thứ tự | Dữ liệu temporal có nghĩa |
| Không có gap ở kỳ bắt buộc | Mapping fact không bị thiếu |
| Fact product_sk tồn tại | Không có orphan foreign key |
| Fact ngày bán nằm trong valid_period của product_sk | FK đúng phiên bản thời gian |
| Fact và dimension cùng tenant khi cần | Không rò hoặc gắn chéo dữ liệu |
| Code/label đáp ứng dữ liệu chuẩn | Không tạo nhiều nhóm do lỗi chính tả |
| Unknown/inferred có trạng thái rõ | Dữ liệu thiếu không bị coi là đã xác minh |
| Mapping nguồn đa hệ thống được phê duyệt | Không gộp nhầm danh tính |
| Query sau JOIN giữ số dòng/tiền khi mong đợi | Phát hiện fanout |

### 18.1. Tìm overlap trong bảng staging chưa có constraint

Ví dụ sau hữu ích trên dữ liệu nạp tạm có cấu trúc tương tự dim_product:

~~~sql
SELECT
    a.product_dk,
    a.product_sk AS first_sk,
    b.product_sk AS second_sk,
    a.valid_period AS first_period,
    b.valid_period AS second_period
FROM dim_product a
JOIN dim_product b
  ON a.product_dk = b.product_dk
 AND a.product_sk < b.product_sk
 AND a.valid_period && b.valid_period;
~~~

Với bảng dim_product đã có exclusion constraint hoạt động, kết quả phải rỗng. Khi migration từ nguồn cũ, hãy chạy dạng truy vấn này **trên staging trước khi áp constraint** để phát hiện dữ liệu cần sửa.

### 18.2. Tìm khoảng trống giữa các phiên bản

~~~sql
WITH timeline AS (
    SELECT
        product_dk,
        upper(valid_period) AS valid_to,
        LEAD(lower(valid_period)) OVER (
            PARTITION BY product_dk
            ORDER BY lower(valid_period)
        ) AS next_valid_from
    FROM dim_product
)
SELECT
    product_dk,
    valid_to AS gap_start,
    next_valid_from AS gap_end
FROM timeline
WHERE valid_to IS NOT NULL
  AND next_valid_from IS NOT NULL
  AND valid_to < next_valid_from;
~~~

Đây là kiểm tra **gap nội bộ**. Nó không phát hiện thiếu dữ liệu trước phiên bản đầu tiên hoặc sau phiên bản cuối cùng; phải đối chiếu với vòng đời thực sự của sản phẩm và phạm vi fact.

### 18.3. Kiểm tra fact gắn sai thời điểm

~~~sql
SELECT
    f.sales_line_sk,
    f.source_line_bk,
    d.calendar_date,
    p.product_sk,
    p.valid_period
FROM fact_sales_line f
JOIN dim_date d ON d.date_key = f.date_key
JOIN dim_product p ON p.product_sk = f.product_sk
WHERE NOT (p.valid_period @> d.calendar_date);
~~~

Truy vấn này phải rỗng nếu mọi fact được gắn đúng phiên bản tại ngày bán. Nhưng cũng cần kiểm tra nguồn và tenant của sản phẩm đã ánh xạ, cũng như các dimension khác nếu có lịch sử.

### 18.4. Không để lỗi chiều biến thành lỗi số đo

Nếu một dòng bán 180.000 VND bị JOIN thành hai hàng dimension, SUM sẽ thành 360.000 VND. Nên có một kiểm thử đối soát:

~~~sql
WITH source_total AS (
    SELECT SUM(net_amount) AS amount
    FROM fact_sales_line
    WHERE currency_code = 'VND'
),
joined_total AS (
    SELECT SUM(f.net_amount) AS amount
    FROM fact_sales_line f
    JOIN dim_product p ON p.product_sk = f.product_sk
    WHERE f.currency_code = 'VND'
)
SELECT
    s.amount AS source_amount,
    j.amount AS joined_amount
FROM source_total s
CROSS JOIN joined_total j;
~~~

Khi FK hợp lệ và JOIN theo product_sk PK, hai tổng phải bằng nhau. Tuy nhiên tổng bằng nhau **không đủ** để chứng minh mọi fact được gắn vào đúng phiên bản; vẫn phải kiểm tra mapping theo ngày.

## 19. Trường hợp đặc biệt: chiều ngày, chiều vai trò và chiều suy biến

### 19.1. Date dimension

Chiều ngày có thể dùng **date_key = 20260815** và **calendar_date = 2026-08-15**. Đây là một trường hợp mà khóa theo quy ước có ý nghĩa và ổn định, không cần thiết phải dùng sequence ngẫu nhiên cho từng ngày.

Nhưng thời gian có nhiều nghĩa: ngày đặt, ngày thanh toán, ngày giao, ngày ghi doanh thu. Một fact có thể có nhiều FK tới cùng dim_date, mỗi FK là một **vai trò** (*role-playing dimension*).

### 19.2. Degenerate dimension

**order_bk** có thể được lưu trực tiếp trong fact_sales_line để drill-through và COUNT(DISTINCT order_bk), nếu nó không có tập thuộc tính riêng cần dimension. Đó là **degenerate dimension**, khác với product_sk là FK tới dimension có mô tả.

Cần chú ý scope của order_bk: mã O100 có thể trùng giữa hai POS, nên đếm đơn toàn hệ thống có thể cần tổ hợp (tenant, sales_source, order_bk), không chỉ một chuỗi mã.

### 19.3. Conformed dimension

Nếu fact_sales_line và fact_inventory_daily dùng cùng một định nghĩa sản phẩm và danh mục, chúng có thể so sánh doanh thu với tồn theo product. Nhưng nếu một fact dùng product family còn fact khác dùng SKU, cần ánh xạ grain rõ ràng trước khi drill-across.

**Conformed dimension** là sự thống nhất về **ý nghĩa, khóa và phân loại** giữa các mô hình phân tích, không đơn thuần là có hai bảng cùng tên dim_product.

### 19.4. Mini-dimension cho thuộc tính đổi rất nhanh

Nếu một số thuộc tính khách hàng thay đổi rất thường xuyên (ví dụ nhóm hoạt động, score band), tạo SCD2 toàn bộ dim_customer cho mỗi thay đổi có thể làm tăng phiên bản quá nhanh. Có thể tách nhóm thuộc tính biến động nhanh sang **mini-dimension**, fact tham chiếu tới mini-dim phù hợp.

Nhưng phải làm rõ grain và ý nghĩa thời gian của liên kết. Không nên tách mini-dim chỉ để tối ưu dung lượng nếu làm mất khả năng giải thích phân khúc tại lúc giao dịch.

## 20. Vận hành ETL: nạp, idempotency và sửa hồi tố

Một pipeline điển hình:

~~~mermaid
flowchart LR
    A["ERP/PIM/POS nguồn"] --> B["Staging + chuẩn hóa BK"]
    B --> C["Identity mapping / durable key"]
    C --> D["SCD dimension versions"]
    D --> E["Ánh xạ fact tới version SK"]
    E --> F["Data quality + đối soát"]
    F --> G["Kho phân tích / semantic layer"]
~~~

Quy trình cần phân biệt các bước:

1. **Nhận dữ liệu có khóa nguồn**: tenant, source, BK, version nguồn hoặc thời điểm cập nhật.
2. **Chuẩn hóa mã trong giới hạn hợp đồng nguồn**: không làm mất số 0 đầu hay namespace.
3. **Tìm hoặc tạo identity**: tránh tạo bản trùng trong tình huống hai worker chạy đồng thời.
4. **So sánh thuộc tính cần Type 1/Type 2**: tách thay đổi lỗi nhãn với thay đổi phân loại có hiệu lực.
5. **Tính timeline hợp lệ**: xử lý mốc tương lai/hồi tố, chia khoảng khi cần, giữ ràng buộc chống overlap.
6. **Ghi transaction**: bảo đảm identity/version thay đổi nguyên tử trong database nếu cùng hệ thống.
7. **Ánh xạ fact**: dùng BK nguồn cùng ngày nghiệp vụ để chọn product_sk phù hợp.
8. **Kiểm thử và đối soát**: kiểm tra missing dimensions, duplicated facts, đúng số tiền/nhóm.
9. **Xuất bản phiên bản dữ liệu**: không thay đổi âm thầm dashboard đã chốt khi nghiệp vụ yêu cầu lưu revision.
10. **Theo dõi chất lượng và retry**: thao tác nạp lại không tạo identity/phiên bản trùng.

### 20.1. Idempotency không có nghĩa bỏ qua mọi lần gửi lại

Nếu nguồn gửi lại cùng quyết định, ETL phải nhận ra và không tạo bản SCD2 giống hệt. Nhưng nếu bản gửi lại mang thông tin đã được **sửa có thẩm quyền**, cần xử lý thành một correction chứ không xóa bỏ chỉ vì BK trùng.

Có thể lưu decision_id/source_event_id và revision để phân biệt **retry**, **cập nhật mới** và **đính chính**. Unique BK chỉ bảo vệ identity, không thay thế việc deduplicate bản cập nhật.

### 20.2. Hồi tố ảnh hưởng fact đã chốt

Giả sử ngày 10/08 phát hiện P01 thực ra phải chuyển sang GIFT từ 20/07, không phải 01/08.

- Theo timeline mới, giao dịch L-501 ngày 15/07 vẫn FOOD.
- Một giao dịch L-501B ngày 25/07, nếu từng được gắn FOOD, nay cần được xem xét gắn lại phiên bản GIFT cho báo cáo **as-was theo thông tin hiện được công nhận**.
- Báo cáo tháng 7 đã công bố trước correction có thể khác báo cáo được tái tính sau correction.

Cần chính sách restatement, version của snapshot/report hoặc bitemporal nếu phải chứng minh warehouse **đã biết điều gì tại K**. Không UPDATE fact hay dimension lịch sử một cách tùy tiện rồi không lưu bằng chứng ảnh hưởng.

### 20.3. Khác nhau giữa lỗi mô hình và lỗi dữ liệu nguồn

Nếu BK không duy nhất trong phạm vi đã xác định, có thể là **sai giả định thiết kế** hoặc **dữ liệu nguồn vi phạm hợp đồng**. Hai trường hợp cần hành động khác nhau.

Không “chữa” bằng cách thêm một số ngẫu nhiên vào BK để mỗi hàng trở nên duy nhất; điều đó che giấu xung đột danh tính thay vì giải quyết nó.

## 21. Tối ưu vật lý, bảo mật và tiến hóa dimension

### 21.1. Chỉ mục cho các truy vấn chính

Với mô hình này, các hướng truy vấn điển hình:

| Truy vấn | Khóa hoặc chỉ mục hữu ích |
|---|---|
| BK → durable key | UNIQUE(tenant_id, source_system, product_bk) |
| durable key + ngày → version SK | GiST exclusion và tìm valid_period |
| SK → mô tả | PRIMARY KEY(product_sk) |
| Timeline một sản phẩm | INDEX(product_dk, lower(valid_period)) |
| Fact theo ngày/sản phẩm | INDEX(date_key, product_sk) |
| Báo cáo theo danh mục | Nhóm/scan fact qua dimension; đo trên workload thực |

Không tạo chỉ mục chỉ vì một cột xuất hiện trong SELECT. Cần đo bằng **EXPLAIN (ANALYZE, BUFFERS)** và xem chi phí ghi cập nhật SCD2, độ chọn lọc, bộ nhớ và khối lượng fact.

### 21.2. Thuộc tính lớn, đa ngôn ngữ và riêng tư

Dimension có thể chứa tên dài, mô tả HTML, danh sách ảnh hoặc thông tin nhạy cảm. Các trường lớn không thường dùng để group nên cân nhắc tách sang bảng bổ sung hoặc hệ thống mô tả chuyên dụng để giảm I/O khi BI scan.

Với dimension khách hàng, không nhân bản email, địa chỉ và thông tin cá nhân vào mọi phiên bản nếu yêu cầu phân tích chỉ cần phân khúc. Cần chính sách quyền đọc, retention, mã hóa, tối thiểu hóa và xóa/ẩn danh theo quy định áp dụng.

### 21.3. Tạo dữ liệu chuẩn và tránh drift nhãn

Nếu category_code FOOD được hiển thị lúc thì **“Thực phẩm”**, lúc thì **“Food”**, lúc thì **“Đồ ăn”**, BI có thể tạo ba nhóm hiển thị khác nhau dù cùng một category. Nên quản trị mapping code → nhãn (theo locale, nếu cần), kiểm thử giá trị chuẩn và có chiến lược version nếu phân loại đổi nghĩa.

Lược đồ có thể chuyển từ relational sang document hoặc lakehouse mà vẫn giữ ba khái niệm chính: **danh tính nghiệp vụ**, **định danh phiên bản** và **thuộc tính có nghĩa tại thời điểm phân tích**.

## 22. Bài thực hành: xây chiều khách hàng có lịch sử phân khúc

Một nền tảng thương mại điện tử có yêu cầu:

> “Theo từng tháng, tính doanh thu theo phân khúc khách hàng tại ngày mua. Khách có thể chuyển từ REGULAR sang VIP. Dữ liệu khách đến từ CRM và POS; một số khách mua trước khi hồ sơ CRM được đồng bộ.”

Dữ liệu mẫu:

~~~text
CRM / C-501 (tenant 1)
  REGULAR: [2026-01-01, 2026-07-01)
  VIP:     [2026-07-01, +∞)

Đơn O100 ngày 2026-06-20: net = 100.000 VND
Đơn O101 ngày 2026-07-10: net = 200.000 VND
~~~

Thực hiện:

1. **Định nghĩa BK:** chỉ rõ phạm vi (tenant_id, source_system, customer_bk). Nếu POS có mã khách khác CRM, cần mapping nào để nhận diện cùng khách?
2. **Chọn durable key:** một customer_dk ổn định cho khách logic; mô tả trường hợp khách đổi mã CRM.
3. **Chọn version SK:** tạo hai hàng dim_customer SCD2, mỗi hàng có customer_sk riêng và valid_period riêng.
4. **Chọn thuộc tính mô tả:** segment_code, region_code, loyalty_level; xác định trường nào Type 1, Type 2 và vì sao.
5. **Fact mapping:** O100 phải trỏ customer_sk REGULAR, O101 trỏ customer_sk VIP.
6. **As-was vs as-is:** theo phân khúc lúc bán, REGULAR = 100.000 và VIP = 200.000. Theo phân khúc ngày 15/11/2026, tổng 300.000 có thể được phân loại VIP.
7. **Late-arriving dimension:** nếu O101 tới trước profile CRM, xử lý quarantine hoặc Unknown/inferred member như thế nào?
8. **Tình huống đa tenant:** hai tenant đều có C-501, điều gì ngăn gộp nhầm?
9. **Concurrency:** hai worker đồng thời cập nhật phân khúc ngày 01/07, cần cơ chế khóa và constraint nào?
10. **Correction hồi tố:** ngày 15/08 xác nhận VIP có hiệu lực từ 15/06. Đơn O100 ngày 20/06 có thay đổi phân khúc trong báo cáo tính lại không? Cần chính sách sửa fact, revision và báo cáo đã chốt ra sao?
11. **Kiểm thử:** duplicate BK, overlap SCD2, gap, orphan FK, fact gắn sai ngày, sai tenant và fanout khi JOIN qua cả BK lẫn version.

**Tiêu chí đạt:** BK có namespace, SK đúng grain phiên bản, thuộc tính mô tả có chiến lược thay đổi, fact gắn đúng phiên bản, quy tắc dữ liệu đến muộn và hồi tố không mơ hồ.

## 23. Checklist phê duyệt thiết kế

Trước khi triển khai bảng chiều, hãy kiểm tra:

- **Grain:** mỗi hàng dimension đại diện một đối tượng logic hay một phiên bản mô tả?
- **Khóa nghiệp vụ:** mã nguồn do ai cấp; namespace tenant/source đã đủ; có thể tái sử dụng hoặc đổi mã không?
- **Khóa thay thế:** SK là ID hàng hay ID thực thể; có cần durable key riêng không?
- **FK fact:** fact tham chiếu version SK phù hợp hay chỉ JOIN BK khiến nhân hàng?
- **Thuộc tính mô tả:** có đúng grain, đơn trị hay đa trị; code và label có được quản trị nhất quán?
- **Lịch sử:** trường nào dùng Type 1, Type 2 hoặc relation history; các biên thời gian có được xác định rõ?
- **Ràng buộc:** PK, FK, UNIQUE, CHECK và chống overlap theo đúng khóa nghiệp vụ có đủ không?
- **Dữ liệu đến muộn:** Unknown, Not applicable, inferred member và quarantine được phân biệt chưa?
- **Đa nguồn:** identity resolution có nguồn phê duyệt, không gộp BK trùng ngẫu nhiên chưa?
- **As-was/as-is:** người dùng báo cáo biết mình đang xem phân loại ở thời điểm nào chưa?
- **Kiểm chứng:** duplicate, missing dimension, temporal mismatch, cross-tenant mapping và fanout được kiểm tra tự động chưa?
- **Hồi tố:** correction có quy trình giao dịch, restatement và giữ bằng chứng khi báo cáo đã chốt không?
- **Hiệu năng:** index, phân vùng và nhu cầu scan các thuộc tính chiều đã được đo chưa?
- **Bảo mật:** dữ liệu cá nhân và thông tin bí mật không bị lặp/để lộ qua phiên bản quá khứ chứ?

**Kết luận:** khóa nghiệp vụ trả lời **“đây là đối tượng nào trong nguồn?”**, khóa thay thế phiên bản trả lời **“fact đang tham chiếu đúng hàng mô tả nào?”**, còn thuộc tính chiều trả lời **“đối tượng được phân loại, gọi tên và giải thích ra sao tại thời điểm phân tích?”**. Khi cần, durable key kết nối những phiên bản thuộc cùng đối tượng logic. Phân biệt rõ các vai trò này là nền tảng để xây dimension dễ tiến hóa, truy vấn chính xác, không nhân số đo và có thể kiểm chứng bằng dữ liệu thực tế.
