# Định danh chủ thể hiện tại và định danh một phiên bản lịch sử

Một sản phẩm có thể đổi tên, giá, mô tả hoặc danh mục mà cửa hàng vẫn xem đó là cùng một sản phẩm. Một khách hàng có thể đổi email và số điện thoại nhưng lịch sử đơn hàng vẫn thuộc về cùng người đó. Ngược lại, nếu một sản phẩm được thay bằng một phiên bản kinh doanh khác hoặc hai hồ sơ khách hàng thực ra là hai người khác nhau, hệ thống phải nhận diện đó là những chủ thể khác nhau.

Để mô hình hóa chính xác, cần phân biệt hai loại định danh:

- **Định danh chủ thể (subject identity):** nhận diện một đối tượng nghiệp vụ xuyên suốt vòng đời của nó, dù các thuộc tính thay đổi.
- **Định danh phiên bản (version identity):** nhận diện một trạng thái cụ thể của chủ thể trong một khoảng thời gian hoặc tại một lần ghi nhận.

Ví dụ, mã **product_id** nhận diện sản phẩm xuyên suốt vòng đời; **product_version_id** nhận diện một phiên bản cụ thể của thông tin sản phẩm. Khi tên hoặc giá thay đổi, product_id có thể giữ nguyên nhưng product_version_id mới được tạo.

Sự phân biệt này là nền tảng khi chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu. Nó giúp hệ thống vừa trả lời được “đối tượng hiện tại là ai/cái gì?”, vừa trả lời được “ở thời điểm đó, đối tượng có những thuộc tính nào và hệ thống đã biết điều gì?”.

## 1. Hai câu hỏi nhận diện khác nhau

Hãy dùng ví dụ một cửa hàng trực tuyến.

Sản phẩm có mã SKU, tên, mô tả, giá và danh mục. Trong quá trình kinh doanh, tên sản phẩm có thể được sửa, giá có thể thay đổi, sản phẩm có thể chuyển danh mục. Đơn hàng cũ vẫn phải giữ đúng tên và giá tại thời điểm mua.

Có hai câu hỏi:

1. **Chủ thể nào đang được nói đến?** Đây là sản phẩm có định danh ổn định, chẳng hạn Product 501.
2. **Phiên bản nào của chủ thể đang được nói đến?** Đây là trạng thái của Product 501 có hiệu lực từ ngày 1/10 đến trước ngày 15/11, với tên, giá và danh mục cụ thể.

Một chủ thể có thể có nhiều phiên bản theo thời gian:

~~~mermaid
flowchart LR
    P["Product 501<br/>Định danh chủ thể ổn định"] --> V1["Version 1<br/>Tên A · 400.000đ<br/>01/10–14/11"]
    P --> V2["Version 2<br/>Tên A Plus · 450.000đ<br/>15/11–30/11"]
    P --> V3["Version 3<br/>Tên A Plus · 470.000đ<br/>Từ 01/12"]
~~~

Sơ đồ chỉ minh họa thời gian hiệu lực. Trong dữ liệu thật, các mốc thời gian và giá trị phải lấy từ nghiệp vụ đã xác nhận.

Nếu chỉ lưu một dòng Product và ghi đè tên, giá mỗi lần thay đổi, ta giữ được thông tin hiện tại nhưng làm mất trạng thái cũ. Nếu tạo một Product mới mỗi lần giá đổi, ta lại làm đứt định danh chủ thể: đơn hàng cũ, liên kết danh mục và báo cáo có thể tưởng rằng đó là những sản phẩm khác nhau.

Mô hình phiên bản giải quyết hai nhu cầu bằng cách tách định danh ổn định khỏi các trạng thái có thời hạn.

## 2. Định danh chủ thể là gì?

Định danh chủ thể là mã dùng để nhận diện một đối tượng nghiệp vụ qua các thay đổi thuộc tính mà nghiệp vụ vẫn xem là cùng một đối tượng.

Ví dụ:

| Chủ thể | Thay đổi thuộc tính | Định danh chủ thể |
|---|---|---|
| Khách hàng | Đổi email hoặc số điện thoại | customer_id giữ nguyên nếu vẫn là cùng người |
| Sản phẩm | Sửa tên hiển thị hoặc mô tả | product_id giữ nguyên nếu vẫn là cùng sản phẩm |
| Kho | Đổi tên gọi hoặc số điện thoại liên hệ | warehouse_id giữ nguyên nếu vẫn là cùng địa điểm/kho |
| Nhân viên | Đổi địa chỉ liên hệ | employee_id giữ nguyên nếu vẫn là cùng nhân viên |
| Đơn hàng | Chuyển từ PENDING sang PAID | order_id giữ nguyên vì vẫn là cùng đơn |

Định danh chủ thể không phải là ảnh chụp thuộc tính. Nó đại diện cho sự liên tục của đối tượng theo cách nghiệp vụ định nghĩa.

### 2.1. Định danh kỹ thuật và định danh nghiệp vụ

Một chủ thể thường có nhiều loại mã:

- **Định danh kỹ thuật:** do hệ thống tạo, ví dụ customer_id dạng số hoặc UUID.
- **Định danh nghiệp vụ:** mã có ý nghĩa với người dùng hoặc hệ thống bên ngoài, ví dụ SKU, mã khách hàng, mã đơn hàng.
- **Định danh từ hệ thống ngoài:** mã khách hàng ở CRM, mã sản phẩm từ nhà cung cấp hoặc mã giao dịch của cổng thanh toán.

Định danh kỹ thuật thường phù hợp làm khóa tham chiếu nội bộ vì có thể giữ ổn định ngay cả khi mã nghiệp vụ thay đổi. Mã nghiệp vụ cần được quản lý bằng quy tắc duy nhất và thời gian hiệu lực nếu có thể đổi hoặc tái sử dụng.

Ví dụ, khách hàng đổi email không nên khiến toàn bộ đơn hàng phải đổi khóa ngoại. Các đơn hàng tiếp tục tham chiếu customer_id. Email cũ và email mới có thể được lưu trong lịch sử định danh liên hệ nếu cần tra cứu.

### 2.2. Một mã có thể duy nhất nhưng không phải định danh ổn định

Email có thể duy nhất tại một thời điểm, nhưng vẫn có thể đổi hoặc được cấp lại cho người khác. SKU có thể duy nhất trong catalog hiện tại nhưng doanh nghiệp có thể ngừng dùng rồi tái sử dụng theo chính sách. Tên sản phẩm thường không duy nhất và có thể thay đổi.

Vì vậy, cần phân biệt:

- **Duy nhất:** không có hai đối tượng cùng dùng mã trong phạm vi và thời điểm được quy định.
- **Ổn định:** mã tiếp tục chỉ đúng cùng một chủ thể qua các thay đổi được phép.
- **Bền vững theo lịch sử:** dữ liệu cũ vẫn có thể xác định đúng đối tượng hoặc mã đã có hiệu lực tại thời điểm đó.

Một mã có thể thỏa tính duy nhất nhưng không thỏa tính ổn định. Đừng dùng một thuộc tính làm khóa tham chiếu lâu dài chỉ vì nó đang là duy nhất.

### 2.3. Phạm vi duy nhất của định danh

Định danh phải có phạm vi rõ ràng:

- SKU có thể duy nhất trong một cửa hàng hoặc toàn bộ hệ thống.
- Mã khách hàng có thể duy nhất trong một tenant, chi nhánh hoặc quốc gia.
- Mã giao dịch có thể chỉ duy nhất trong phạm vi một nhà cung cấp thanh toán.
- Số hóa đơn có thể duy nhất theo năm tài chính hoặc pháp nhân phát hành.

Ví dụ, cặp (tenant_id, customer_number) có thể là định danh nghiệp vụ duy nhất trong một tenant. Nếu hệ thống đa tenant, chỉ ràng buộc customer_number duy nhất toàn cục có thể sai với nghiệp vụ.

Hãy viết rõ phạm vi vào quy tắc định danh trước khi thiết kế khóa.

## 3. Định danh phiên bản là gì?

Định danh phiên bản nhận diện một bản ghi trạng thái cụ thể của chủ thể. Một chủ thể có thể có nhiều phiên bản; mỗi phiên bản mang một nhóm thuộc tính tại một khoảng thời gian hoặc một thời điểm ghi nhận.

Ví dụ Product 501 có ba phiên bản:

| product_id | product_version_id | Tên | Giá | Hiệu lực |
|---|---|---|---:|---|
| 501 | 9001 | Tai nghe A | 400.000 | 01/10–14/11 |
| 501 | 9002 | Tai nghe A Plus | 450.000 | 15/11–30/11 |
| 501 | 9003 | Tai nghe A Plus | 470.000 | Từ 01/12 |

Trong bảng:

- **product_id** nhận diện chủ thể.
- **product_version_id** nhận diện một phiên bản.
- Nhiều dòng có cùng product_id vì chúng thuộc cùng một chủ thể.
- Mỗi product_version_id phải duy nhất.
- Khoảng hiệu lực của các phiên bản cùng chủ thể cần tuân theo quy tắc thời gian, thường không chồng lấn.

Định danh phiên bản cho phép một đơn hàng tham chiếu đúng thông tin sản phẩm đã áp dụng tại thời điểm mua, thay vì đọc nhầm phiên bản hiện tại.

### 3.1. Khi nào cần định danh phiên bản?

Nên xem xét version identity khi có các yêu cầu:

- Phải xem lại tên, giá, địa chỉ, phân loại hoặc điều khoản tại một thời điểm trong quá khứ.
- Cần biết một thuộc tính có hiệu lực từ khi nào đến khi nào.
- Báo cáo phải dùng thuộc tính lịch sử thay vì thuộc tính hiện tại.
- Thay đổi dữ liệu cần được kiểm toán.
- Một quy trình phải tham chiếu chính xác phiên bản đã được phê duyệt hoặc sử dụng.
- Có thể sửa dữ liệu hồi tố nhưng vẫn cần biết trước đó hệ thống đã ghi nhận điều gì.

Không cần tạo phiên bản cho mọi cột. Hãy xác định thuộc tính nào cần lịch sử và lý do nghiệp vụ. Ví dụ, có thể cần lịch sử giá và tên sản phẩm nhưng không cần version riêng cho trường ghi chú nội bộ ít quan trọng.

### 3.2. Phiên bản không đồng nghĩa với chủ thể mới

Giả sử một sản phẩm đổi giá từ 400.000 lên 450.000 đồng. Nếu đó vẫn là cùng sản phẩm, product_id giữ nguyên và tạo phiên bản mới.

Nhưng nếu doanh nghiệp thay đổi bản chất của mặt hàng, chẳng hạn sản phẩm A được thay bằng một mẫu mới không tương thích, có SKU và bảo hành riêng, nghiệp vụ có thể xem đó là chủ thể mới. Khi ấy nên tạo product_id mới, có thể liên kết bằng quan hệ **replaces** hoặc **successor_of**.

Ranh giới “cùng chủ thể” là quyết định nghiệp vụ. Đừng tự động tạo version chỉ vì có thay đổi, cũng đừng tự động giữ identity nếu bản chất đối tượng đã đổi.

## 4. Mô hình dữ liệu tách chủ thể và phiên bản

Một mô hình quan hệ phổ biến tách bảng chủ thể ổn định khỏi bảng phiên bản.

~~~mermaid
erDiagram
    PRODUCT ||--|{ PRODUCT_VERSION : has
    PRODUCT ||--o{ ORDER_ITEM : ordered_as_subject
    PRODUCT_VERSION ||--o{ ORDER_ITEM : purchased_as_version
~~~

Bảng Product giữ định danh ổn định và các thuộc tính thực sự không đổi hoặc ít khi thay đổi. Bảng ProductVersion giữ những thuộc tính có thể thay đổi theo thời gian.

Ví dụ lược đồ PostgreSQL:

~~~sql
CREATE TABLE product (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lifecycle_status VARCHAR(20) NOT NULL
        CHECK (lifecycle_status IN ('ACTIVE', 'DISCONTINUED'))
);

CREATE TABLE product_version (
    product_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES product(product_id)
        ON DELETE RESTRICT,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(250) NOT NULL,
    description TEXT,
    current_price NUMERIC(18, 2) NOT NULL
        CHECK (current_price >= 0),
    currency CHAR(3) NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    UNIQUE (product_id, valid_from)
);

CREATE UNIQUE INDEX uq_product_version_current
    ON product_version(product_id)
    WHERE valid_to IS NULL;

CREATE UNIQUE INDEX uq_product_version_sku_current
    ON product_version(sku)
    WHERE valid_to IS NULL;

CREATE INDEX ix_product_version_lookup
    ON product_version(product_id, valid_from DESC);
~~~

Đây là ví dụ cơ bản. Nếu SKU được tái sử dụng hoặc chỉ duy nhất trong tenant, cần đưa phạm vi đó vào khóa và quy tắc kiểm tra. Nếu phiên bản được lên lịch trong tương lai, khái niệm “current” phải được định nghĩa theo thời điểm hiện tại, không chỉ theo giá trị valid_to rỗng. Trong hệ thống có nhiều phiên bản được lên lịch, nên truy vấn phiên bản có hiệu lực tại thời điểm cần tìm.

### 4.1. Cách đọc chủ thể hiện tại

Một truy vấn tìm thông tin hiện tại có thể lấy phiên bản đang hiệu lực:

~~~sql
SELECT
    p.product_id,
    v.product_version_id,
    v.sku,
    v.name,
    v.current_price,
    v.currency
FROM product AS p
JOIN product_version AS v
    ON v.product_id = p.product_id
WHERE p.product_id = :product_id
  AND v.valid_from <= now()
  AND (v.valid_to IS NULL OR now() < v.valid_to);
~~~

Nếu hệ thống chỉ cho phép một phiên bản hiện tại và không có phiên bản tương lai được lên lịch, partial unique index với valid_to IS NULL có thể giúp bảo đảm tối đa một phiên bản mở cho mỗi product_id. Tuy nhiên, index này không tự ngăn các khoảng thời gian lịch sử chồng lấn.

### 4.2. Cách tìm phiên bản có hiệu lực tại thời điểm mua

~~~sql
SELECT
    product_id,
    product_version_id,
    sku,
    name,
    current_price,
    currency
FROM product_version
WHERE product_id = :product_id
  AND valid_from <= :purchased_at
  AND (valid_to IS NULL OR :purchased_at < valid_to);
~~~

Dùng khoảng thời gian nửa mở [valid_from, valid_to) giúp hai phiên bản kế tiếp có thể nối nhau tại cùng một mốc mà không bị tính trùng:

- Phiên bản cũ có hiệu lực đến trước 15/11.
- Phiên bản mới có hiệu lực từ đúng 15/11.

Một thời điểm chỉ thuộc một khoảng nếu các khoảng không chồng lấn.

### 4.3. Bảo đảm khoảng hiệu lực không chồng lấn

Ràng buộc UNIQUE(product_id, valid_from) chỉ ngăn hai phiên bản bắt đầu cùng thời điểm. Nó không ngăn hai khoảng có thời gian chồng lấn.

Trong PostgreSQL, có thể dùng exclusion constraint với range:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE product_version
ADD CONSTRAINT ex_product_version_no_overlap
EXCLUDE USING gist (
    product_id WITH =,
    tstzrange(valid_from, valid_to, '[)') WITH &&
);
~~~

Ràng buộc này ngăn hai khoảng hiệu lực của cùng product_id giao nhau. Nếu dùng hệ quản trị khác, cần cơ chế tương đương như transaction có khóa, trigger hoặc quy trình kiểm tra có tính nguyên tử.

Không nên chỉ kiểm tra “trước khi insert không thấy bản ghi trùng” ở tầng ứng dụng mà không có khóa hoặc ràng buộc cơ sở dữ liệu. Hai transaction đồng thời có thể cùng kiểm tra thấy không có xung đột rồi cùng ghi hai khoảng chồng lấn.

## 5. Phân biệt thời gian hiệu lực và thời gian ghi nhận

Một điểm quan trọng trong dữ liệu lịch sử là “khi nào sự việc có hiệu lực?” và “khi nào hệ thống biết hoặc ghi nhận điều đó?” có thể khác nhau.

- **Valid time (thời gian hiệu lực):** khoảng thời gian sự thật đó đúng trong thế giới nghiệp vụ.
- **Transaction time / system time (thời gian ghi nhận):** khoảng thời gian dữ liệu đó được lưu và được hệ thống xem là thông tin đã biết.

Ví dụ: ngày 20/11, nhân viên phát hiện giá sản phẩm đã được áp dụng từ ngày 15/11 nhưng hồ sơ nhập nhầm giá. Giá đúng có hiệu lực từ 15/11; hệ thống chỉ ghi nhận sửa sai vào ngày 20/11.

Nếu chỉ lưu valid_from và valid_to rồi sửa đè bản ghi, ta biết giá đúng trong quá khứ nhưng không biết hệ thống đã từng tin vào giá sai từ ngày 15 đến ngày 20. Nếu cần kiểm toán cả hai góc nhìn, hãy lưu hai trục thời gian.

### 5.1. Mô hình hai trục thời gian (bitemporal)

Một bảng bitemporal có thể gồm:

- **valid_from, valid_to:** khoảng thời gian dữ liệu có hiệu lực trong nghiệp vụ.
- **recorded_from, recorded_to:** khoảng thời gian hệ thống lưu phiên bản nhận thức đó.

Ví dụ dữ liệu:

| product_id | Giá | Valid time | Recorded time |
|---|---:|---|---|
| 501 | 450.000 | Từ 15/11 | 15/11–20/11 |
| 501 | 430.000 | Từ 15/11 | Từ 20/11 |

Bản ghi thứ nhất thể hiện điều hệ thống đã ghi nhận trước khi sửa. Bản ghi thứ hai thể hiện điều hệ thống biết sau khi sửa hồi tố. Cả hai đều nói về cùng khoảng hiệu lực nghiệp vụ, nhưng thuộc hai giai đoạn ghi nhận khác nhau.

Lược đồ khái niệm:

~~~sql
CREATE TABLE product_version_history (
    version_record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES product(product_id),
    name VARCHAR(250) NOT NULL,
    current_price NUMERIC(18, 2) NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    recorded_from TIMESTAMPTZ NOT NULL,
    recorded_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (recorded_to IS NULL OR recorded_to > recorded_from)
);
~~~

Đây là cấu trúc minh họa; muốn bảo đảm không chồng lấn trong cả hai chiều cần thêm ràng buộc và quy tắc transaction phù hợp. Bitemporal hữu ích cho kiểm toán, giá/điều khoản có hiệu lực hồi tố, dữ liệu tuân thủ và báo cáo cần tái hiện điều hệ thống đã biết tại một thời điểm.

### 5.2. Hai câu hỏi mà bitemporal trả lời

- “Giá nào có hiệu lực vào ngày 16/11 theo dữ liệu đã sửa đúng hiện nay?” → lọc theo valid time, dùng nhận thức hiện tại.
- “Ngày 18/11 hệ thống đang ghi nhận giá nào cho ngày 16/11?” → lọc theo valid time và recorded time tại ngày 18/11.

Nếu nghiệp vụ không cần câu hỏi thứ hai, lưu một trục thời gian thường đơn giản hơn. Không nên dùng bitemporal chỉ vì nó có vẻ đầy đủ; hãy dùng khi cần phân biệt lịch sử sự thật với lịch sử nhận thức của hệ thống.

## 6. Liên kết dữ liệu hiện tại và lịch sử đúng cách

Khi thiết kế quan hệ giữa các bảng, cần xác định bên tham chiếu muốn chỉ đến chủ thể hay một phiên bản cụ thể.

### 6.1. Tham chiếu chủ thể

Đơn hàng có thể tham chiếu product_id để trả lời “đơn hàng này mua sản phẩm nào?”. Quan hệ này phù hợp khi cần nhóm doanh thu theo chủ thể sản phẩm xuyên suốt các phiên bản.

Nhưng nếu chỉ tham chiếu product_id rồi lấy tên và giá từ phiên bản hiện tại, hóa đơn cũ có thể thay đổi theo catalog. Đó là lỗi lịch sử.

### 6.2. Tham chiếu phiên bản

Nếu đơn hàng cần biết chính xác phiên bản catalog đã được áp dụng khi mua, OrderItem có thể lưu cả product_id và product_version_id:

~~~sql
CREATE TABLE order_item (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL REFERENCES product(product_id),
    product_version_id BIGINT NOT NULL
        REFERENCES product_version(product_version_id),
    sku_snapshot VARCHAR(80) NOT NULL,
    name_snapshot VARCHAR(250) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Ở đây:

- product_id hỗ trợ tổng hợp theo chủ thể sản phẩm.
- product_version_id chỉ ra phiên bản được sử dụng.
- sku_snapshot, name_snapshot và unit_price lưu dữ kiện thương mại đã chốt trên đơn.

Có thể giảm số cột snapshot nếu version record là bất biến và được giữ vĩnh viễn. Tuy vậy, với chứng từ thương mại, lưu các giá trị đã chốt trên chính dòng hàng thường giúp bảo vệ nội dung giao dịch khỏi thay đổi do sửa dữ liệu catalog hoặc migration.

### 6.3. Khi nào chỉ cần snapshot?

Nếu mục tiêu là tái hiện hóa đơn, tên, SKU, đơn giá, thuế và địa chỉ giao hàng tại thời điểm đặt có thể được chụp trực tiếp vào Order và OrderItem. Không nhất thiết phải tạo một mô hình version đầy đủ cho mọi thực thể.

Snapshot phù hợp khi:

- Chỉ cần giữ dữ kiện đã dùng trong một giao dịch.
- Không cần truy vấn toàn bộ lịch sử phiên bản của chủ thể.
- Dữ liệu snapshot có vòng đời gắn với chứng từ.
- Không cần biết các giá trị trung gian từng có hiệu lực giữa hai giao dịch.

Version table phù hợp khi cần tra cứu phiên bản, thời gian hiệu lực, báo cáo theo thuộc tính lịch sử hoặc tái sử dụng phiên bản trong nhiều quy trình.

Hai cách có thể cùng tồn tại: version table là lịch sử catalog, còn snapshot trên OrderItem là dữ kiện thương mại đã chốt.

## 7. Thay đổi thuộc tính hay thay đổi định danh?

Đây là quyết định quan trọng nhất khi mô hình hóa version.

| Tình huống | Giữ subject_id? | Tạo version mới? | Giải thích |
|---|---|---|---|
| Khách đổi email | Có | Có nếu cần lịch sử email | Vẫn là cùng khách hàng |
| Khách đổi số điện thoại | Có | Có nếu cần lịch sử liên hệ | Định danh người không đổi |
| Sản phẩm sửa mô tả | Có | Có nếu mô tả cũ cần truy vấn | Cùng sản phẩm |
| Sản phẩm đổi giá | Có | Có nếu cần lịch sử giá | Cùng sản phẩm, giá có thời hạn |
| Sản phẩm chuyển danh mục | Có | Có hoặc version quan hệ ProductCategory | Chủ thể giữ nguyên, phân loại thay đổi |
| Sản phẩm mới thay thế với đặc tính khác | Thường không | Chủ thể mới | Cần định danh mới và có thể liên kết thay thế |
| Hai hồ sơ khách hàng trùng của cùng một người | Giữ một identity chuẩn, lưu ánh xạ | Có thể cập nhật lịch sử hồ sơ | Cần quy trình hợp nhất có kiểm toán |
| Một hồ sơ khách hàng thực ra đại diện hai người | Tách thành hai identity | Không chỉ tạo hai version | Đây là sửa nhận diện chủ thể, không phải sửa thuộc tính |

### 7.1. Hợp nhất hai định danh trùng

Giả sử hệ thống tạo Customer 101 và Customer 205 nhưng sau đó xác minh chúng là cùng một người. Không nên xóa một mã rồi đổi toàn bộ dữ liệu lịch sử mà không để lại dấu vết.

Một quy trình hợp nhất có thể:

1. Chọn identity chuẩn (canonical customer).
2. Ghi nhận identity cũ là alias/merged identity của identity chuẩn.
3. Lưu thời điểm, lý do và người phê duyệt việc hợp nhất.
4. Chuyển các tham chiếu hiện tại theo quy trình kiểm soát.
5. Giữ ánh xạ để tra cứu dữ liệu hoặc mã cũ từ hệ thống tích hợp.
6. Kiểm tra đơn hàng, thanh toán và quyền truy cập sau khi hợp nhất.

Có thể mô hình hóa bằng bảng CustomerIdentityLink với source_customer_id, canonical_customer_id, relation_type, effective_at và reason. Cần ngăn chu trình hợp nhất và xác định rõ có cho phép hợp nhất nhiều cấp hay không.

### 7.2. Tách một định danh bị gộp nhầm

Nếu một hồ sơ thực ra đại diện cho hai người khác nhau, chỉ tạo hai phiên bản lịch sử sẽ sai: hai người không phải hai trạng thái của cùng một người. Phải tạo hai subject identity riêng và phân bổ lại các dữ kiện theo bằng chứng nghiệp vụ.

Việc phân bổ lịch sử cần được kiểm toán. Không phải mọi đơn hàng đều có thể tự động xác định thuộc người nào. Những bản ghi chưa rõ phải được đánh dấu cần đối soát thay vì gán theo phỏng đoán.

### 7.3. Định danh ngoài và alias

Khi tích hợp CRM, ERP, nhà cung cấp hoặc cổng thanh toán, một chủ thể có thể có nhiều mã từ các hệ thống khác nhau. Hãy tách mã bên ngoài thành bản ghi định danh có nguồn:

| subject_id | source_system | external_id | valid_from | valid_to |
|---|---|---|---|---|
| 501 | ERP | ERP-P-778 | 01/01 | null |
| 501 | Marketplace | MP-991 | 01/03 | null |
| 501 | LegacyCatalog | OLD-77 | 01/01 | 30/06 |

Khóa duy nhất thường là (source_system, external_id) trong phạm vi thời gian hợp lệ theo quy tắc của hệ thống nguồn. Không nên giả định mã bên ngoài là duy nhất toàn cục hoặc không bao giờ được tái sử dụng.

## 8. Các chiến lược quản lý phiên bản thường gặp

### 8.1. Ghi đè (Type 1)

Khi thay đổi thuộc tính, cập nhật trực tiếp bản ghi hiện tại. Không lưu lịch sử của giá trị cũ.

Phù hợp khi:

- Giá trị cũ không còn ý nghĩa nghiệp vụ.
- Sai chính tả hoặc lỗi dữ liệu cần sửa.
- Báo cáo chỉ cần trạng thái hiện tại.

Không phù hợp khi cần tái hiện thông tin tại thời điểm giao dịch hoặc kiểm toán.

### 8.2. Lưu phiên bản mới (Type 2)

Khi thuộc tính cần theo dõi thay đổi, đóng khoảng hiệu lực của phiên bản cũ và thêm phiên bản mới. Subject identity giữ nguyên.

Ví dụ:

1. Phiên bản cũ có valid_to bằng thời điểm thay đổi.
2. Phiên bản mới có valid_from bằng thời điểm đó và valid_to rỗng.
3. Truy vấn theo thời điểm chọn đúng phiên bản.

Đây là cách phổ biến cho lịch sử thuộc tính trong mô hình dữ liệu phân tích (Slowly Changing Dimension Type 2) và có thể áp dụng trong hệ thống giao dịch nếu nghiệp vụ cần lịch sử phiên bản.

### 8.3. Lưu giá trị trước và sau (Type 3)

Giữ một hoặc một số giá trị cũ trong các cột riêng, chẳng hạn previous_region và current_region. Cách này chỉ phù hợp khi số lượng phiên bản cần giữ rất ít và quy tắc truy vấn rõ ràng. Nó không thay thế được lịch sử không giới hạn.

### 8.4. Lưu toàn bộ sự kiện thay đổi

Thay vì chỉ lưu trạng thái phiên bản, hệ thống ghi các sự kiện như ProductRenamed, PriceChanged, CategoryAssigned. Có thể dựng trạng thái từ các sự kiện nếu áp dụng event sourcing.

Cách này giữ được nguyên nhân và diễn biến thay đổi, nhưng cần xử lý thứ tự, sự kiện trùng, version schema và khả năng replay. Không nên chọn event sourcing chỉ để lưu lịch sử tên hoặc giá nếu bảng version đơn giản đã đáp ứng yêu cầu.

| Chiến lược | Giữ định danh chủ thể | Giữ lịch sử | Độ phức tạp | Phù hợp |
|---|---|---|---|---|
| Type 1 | Có | Không | Thấp | Thuộc tính không cần lịch sử |
| Type 2 | Có | Có, theo phiên bản | Trung bình | Truy vấn trạng thái theo thời gian |
| Type 3 | Có | Giới hạn | Thấp đến trung bình | Chỉ cần một số giá trị trước/sau |
| Event log/event sourcing | Có, nếu thiết kế đúng | Theo chuỗi sự kiện | Cao hơn | Cần lịch sử hành động và replay |

## 9. Định danh phiên bản trong mô hình phân tích

Trong kho dữ liệu, dimension thường cần giữ lịch sử thuộc tính. Slowly Changing Dimension Type 2 là cách phổ biến:

- Mỗi hàng dimension có một surrogate key riêng gọi là version key.
- Nhiều hàng dimension có cùng business key/subject key.
- Mỗi hàng có effective start/end và cờ hiện hành hoặc cách xác định phiên bản hiện hành.
- Fact lưu version key có hiệu lực tại thời điểm sự kiện phát sinh.

Ví dụ:

| product_sk | product_id (business key) | Tên | Nhóm hàng | Hiệu lực |
|---|---|---|---|---|
| 1001 | 501 | Tai nghe A | Audio | 01/10–14/11 |
| 1002 | 501 | Tai nghe A Plus | Premium Audio | Từ 15/11 |

FactSales của đơn đặt ngày 10/11 tham chiếu product_sk 1001. FactSales của đơn đặt ngày 18/11 tham chiếu product_sk 1002. Khi tổng hợp theo tên/nhóm hàng lịch sử, doanh thu không bị gán nhầm vào thuộc tính hiện tại.

Cần phân biệt:

- **product_id** trong nguồn giao dịch nhận diện chủ thể.
- **product_sk** trong dimension nhận diện phiên bản dimension.
- **order_item_id** hoặc khóa fact nhận diện sự kiện/dòng giao dịch.

Nếu fact chỉ lưu product_id rồi join vào phiên bản dimension hiện tại, báo cáo lịch sử có thể thay đổi khi dimension cập nhật.

## 10. Những quy tắc cần bảo vệ

Mô hình version cần nhiều quy tắc hơn việc thêm cột version_id.

| Quy tắc | Cách kiểm chứng hoặc bảo vệ |
|---|---|
| Mỗi chủ thể có định danh ổn định | Primary key trên bảng chủ thể |
| Mỗi phiên bản có định danh riêng | Primary key trên bảng phiên bản |
| Phiên bản thuộc đúng chủ thể | Foreign key từ version đến subject |
| Khoảng thời gian hợp lệ | CHECK valid_to > valid_from |
| Các phiên bản không chồng lấn | Exclusion constraint hoặc transaction/trigger tương đương |
| Chỉ có một phiên bản hiện tại theo quy tắc | Partial unique index hoặc ràng buộc tương đương |
| Mã nghiệp vụ duy nhất đúng phạm vi | UNIQUE theo tenant/source và khoảng hiệu lực phù hợp |
| Dữ liệu giao dịch lịch sử không bị đổi | Tham chiếu version và/hoặc lưu snapshot |
| Sửa hồi tố có thể kiểm toán | Bitemporal hoặc audit history |
| Hợp nhất/tách chủ thể có dấu vết | Identity mapping và quy trình phê duyệt |

Không phải tất cả quy tắc đều có thể diễn tả bằng một CHECK. Ràng buộc nhiều dòng, nhiều khoảng thời gian hoặc nhiều bảng cần cơ chế transaction, exclusion constraint, trigger hoặc logic ứng dụng có kiểm soát đồng thời.

## 11. Các lỗi thiết kế thường gặp

### Lỗi 1: Dùng email làm khóa chính khách hàng

Khách hàng đổi email sẽ buộc mọi bảng tham chiếu phải cập nhật. Nếu email được tái sử dụng, dữ liệu lịch sử có thể gắn nhầm người.

Cách sửa: dùng customer_id ổn định làm định danh chủ thể; email là định danh liên hệ có thể thay đổi, có thể có lịch sử và trạng thái xác minh.

### Lỗi 2: Tạo chủ thể mới mỗi lần thuộc tính thay đổi

Mỗi lần sản phẩm đổi giá lại tạo một product_id mới khiến doanh thu theo sản phẩm bị chia nhỏ và các quan hệ khác phải chuyển theo.

Cách sửa: giữ product_id cho cùng chủ thể, tạo product_version_id cho trạng thái mới nếu cần lịch sử.

### Lỗi 3: Ghi đè phiên bản cũ

Bản ghi hiện tại được cập nhật trực tiếp nên không thể trả lời tên, giá hoặc phân loại tại ngày giao dịch.

Cách sửa: đóng hiệu lực phiên bản cũ và thêm phiên bản mới; hoặc lưu snapshot tại giao dịch nếu chỉ cần dữ kiện đã chốt.

### Lỗi 4: Lưu version_id nhưng không lưu subject_id

Khi đó, việc nhóm các phiên bản của cùng một chủ thể khó rõ ràng và các bảng nghiệp vụ không có một định danh ổn định để tham chiếu. Có thể suy ra subject từ version table nhưng việc lưu subject identity riêng thường làm mô hình rõ ràng hơn.

### Lỗi 5: Hai phiên bản hiện hành cùng tồn tại

Nếu không có ràng buộc, một chủ thể có thể có hai phiên bản cùng được xem là hiện tại. Truy vấn có thể trả về hai dòng và chọn ngẫu nhiên.

Cách sửa: xác định rõ ý nghĩa “hiện tại”, đặt unique constraint phù hợp và kiểm soát khoảng hiệu lực không chồng lấn.

### Lỗi 6: Chỉ lưu thời gian ghi nhận, không lưu thời gian hiệu lực

Dữ liệu nhập muộn hoặc sửa hồi tố làm cho lịch sử nghiệp vụ sai lệch.

Cách sửa: phân biệt valid time và recorded time khi nghiệp vụ cần cả hai góc nhìn.

### Lỗi 7: Nhầm sự kiện với phiên bản

Một sự kiện như PaymentCaptured ghi nhận một lần xảy ra. Phiên bản Payment ghi trạng thái giao dịch trong một giai đoạn. Một sự kiện có thể làm tạo phiên bản mới, nhưng hai khái niệm không thay thế nhau.

Cách sửa: dùng event log để lưu điều đã xảy ra; dùng version table để lưu trạng thái có hiệu lực theo thời gian; chỉ kết hợp khi có yêu cầu rõ.

## 12. Quy trình chọn định danh và chiến lược lịch sử

Khi thiết kế một thực thể có thuộc tính thay đổi, hãy làm theo trình tự:

1. **Định nghĩa chủ thể:** viết rõ thế nào được xem là cùng một đối tượng qua thời gian.
2. **Chọn định danh ổn định:** ưu tiên mã kỹ thuật không mang ý nghĩa dễ thay đổi; ghi rõ phạm vi duy nhất.
3. **Liệt kê thuộc tính biến động:** phân loại thuộc tính cần lịch sử, không cần lịch sử hoặc chỉ cần snapshot.
4. **Xác định nhu cầu thời gian:** cần biết giá trị có hiệu lực khi nào, hay còn cần biết hệ thống ghi nhận nó khi nào.
5. **Chọn chiến lược:** Type 1, Type 2, Type 3, event history hoặc snapshot theo yêu cầu truy vấn.
6. **Thiết kế định danh phiên bản:** version_id hoặc khóa ghép subject_id với mốc bắt đầu; bảo đảm quy tắc duy nhất.
7. **Xác định liên kết:** bảng nghiệp vụ tham chiếu chủ thể, phiên bản hay cả hai.
8. **Bảo vệ khoảng thời gian:** không để phiên bản chồng lấn hoặc thiếu khoảng hiệu lực ngoài ý muốn.
9. **Xử lý hợp nhất/tách identity:** có alias, mapping, phê duyệt và khả năng truy vết.
10. **Kiểm tra bằng truy vấn lịch sử:** thử xem trạng thái hiện tại, trạng thái tại ngày X và điều hệ thống đã biết tại ngày Y.

## 13. Bài tập tự kiểm tra

### Bài tập 1: Khách hàng đổi email

Một khách hàng đổi email vào ngày 10/05. Đơn hàng từ tháng 3 vẫn phải thuộc cùng khách hàng và báo cáo phải tìm được email đã dùng lúc đặt.

Hãy xác định:

- Định danh chủ thể nào cần giữ nguyên?
- Email là thuộc tính hiện tại hay một định danh liên hệ có lịch sử?
- Đơn hàng có cần snapshot email không?
- Có cần lưu valid time hoặc recorded time?

Gợi ý: customer_id giữ nguyên. Email có thể được lưu trong bảng contact history nếu cần biết email nào có hiệu lực vào thời điểm đặt. Snapshot email trên đơn chỉ cần khi chứng từ hoặc yêu cầu kiểm toán đòi hỏi đúng giá trị đã dùng lúc đó.

### Bài tập 2: Sản phẩm thay đổi giá và tên

Sản phẩm P có tên “Bàn phím K” và giá 700.000 đồng. Ngày 01/06 đổi tên thành “Bàn phím K Pro”, ngày 10/06 tăng giá lên 750.000 đồng. Đơn ngày 05/06 phải hiển thị tên cũ và giá 700.000 đồng.

Hãy xác định:

- P có giữ product_id không?
- Có bao nhiêu version cần tạo?
- Đơn ngày 05/06 tham chiếu subject hay version?
- Có cần snapshot tên và giá trên OrderItem?

Gợi ý: nếu vẫn là cùng sản phẩm, product_id giữ nguyên. Có thể tạo version mới ngày 01/06 và ngày 10/06. Đơn tham chiếu phiên bản có hiệu lực ngày 05/06 và lưu giá trị đã chốt trên dòng hàng.

### Bài tập 3: Hai hồ sơ khách hàng bị trùng

CRM có Customer 100 và Customer 200. Sau xác minh, cả hai là cùng một người. Một số đơn hàng đã tham chiếu từng mã.

Hãy xác định:

- Chọn identity chuẩn như thế nào?
- Mã còn lại có bị xóa không?
- Làm sao giữ lịch sử tham chiếu và mã ngoài?
- Nếu sau này phát hiện hai hồ sơ là hai người khác nhau thì xử lý ra sao?

Gợi ý: tạo ánh xạ identity, lưu lý do và thời điểm hợp nhất, giữ alias. Nếu xác định nhầm và thực chất là hai người, phải tách thành hai subject identity và đối soát từng quan hệ lịch sử.

### Bài tập 4: Sửa dữ liệu hồi tố

Ngày 20/08, nhân viên phát hiện mức thuế đúng đã có hiệu lực từ 01/08 nhưng hệ thống ghi sai đến ngày 20/08. Bộ phận kiểm toán cần biết cả mức thuế có hiệu lực trong tháng 8 và mức thuế hệ thống đã ghi nhận ngày 10/08.

Hãy xác định có cần bitemporal không và vì sao.

Gợi ý: có. Valid time biểu diễn hiệu lực từ 01/08; recorded time cho biết hệ thống chỉ ghi nhận sửa đúng vào 20/08. Hai trục thời gian trả lời hai câu hỏi khác nhau.

### Bộ câu hỏi rà soát cuối bài

- Chủ thể có định danh ổn định qua các thay đổi hợp lệ không?
- Mã nghiệp vụ có thể đổi, tái sử dụng hoặc chỉ duy nhất trong một phạm vi không?
- Thay đổi thuộc tính có thực sự tạo ra một chủ thể mới không?
- Mỗi phiên bản có định danh riêng và liên kết về đúng chủ thể không?
- Khoảng hiệu lực của các phiên bản có chồng lấn không?
- Có cần phân biệt thời gian hiệu lực và thời gian ghi nhận không?
- Giao dịch lịch sử tham chiếu phiên bản hay lưu snapshot nào?
- Hợp nhất/tách chủ thể có thể truy vết và đối soát không?
- Truy vấn báo cáo có thể tái hiện đúng thuộc tính tại thời điểm phát sinh không?

Một mô hình dữ liệu tốt duy trì được định danh của chủ thể khi đối tượng thay đổi, đồng thời nhận diện được từng phiên bản khi nghiệp vụ cần lịch sử. Subject identity trả lời “đây là cùng đối tượng nào?”, còn version identity trả lời “đây là trạng thái cụ thể nào của đối tượng?”. Khi phân biệt rõ hai câu hỏi, hệ thống có thể phục vụ cả thao tác hiện tại, chứng từ lịch sử, báo cáo theo thời gian và kiểm toán mà không làm đứt các liên kết nghiệp vụ.
