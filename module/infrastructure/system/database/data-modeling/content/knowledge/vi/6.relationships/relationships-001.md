# Quan hệ một với một, một với nhiều và nhiều với nhiều

Trong một hệ thống bán hàng, khách hàng có thể có một tài khoản đăng nhập, một khách hàng có thể đặt nhiều đơn hàng, và một sản phẩm có thể được xếp vào nhiều danh mục. Ba ví dụ này đại diện cho ba kiểu quan hệ phổ biến trong mô hình dữ liệu: một với một (1:1), một với nhiều (1:N) và nhiều với nhiều (N:N).

Phân loại đúng quan hệ giúp mô hình phản ánh chính xác quy tắc nghiệp vụ, tránh tạo liên kết sai, mất dữ liệu hoặc phát sinh bản ghi trùng. Khi chuyển sang cơ sở dữ liệu quan hệ, mỗi kiểu quan hệ còn có cách triển khai bằng khóa ngoại, ràng buộc duy nhất và bảng liên kết.

Bài học sử dụng ví dụ cửa hàng trực tuyến để giải thích cách nhận diện, đọc cardinality, xác định tính bắt buộc, chuyển quan hệ thành lược đồ và kiểm chứng bằng dữ liệu. Trọng tâm là hiểu quan hệ theo góc nhìn nghiệp vụ trước khi chọn cấu trúc lưu trữ.

## 1. Quan hệ biểu diễn điều gì?

Quan hệ (relationship) mô tả cách các thực thể liên kết với nhau theo một quy tắc nghiệp vụ. Ví dụ:

- Một khách hàng **sở hữu** một hồ sơ tài khoản.
- Một khách hàng **đặt** nhiều đơn hàng.
- Một đơn hàng **chứa** nhiều dòng hàng.
- Một sản phẩm **được phân loại vào** nhiều danh mục.
- Một danh mục **chứa** nhiều sản phẩm.

Tên quan hệ nên diễn đạt được hành động hoặc ý nghĩa liên kết. Hãy đọc được từ cả hai phía:

- Khách hàng đặt đơn hàng.
- Đơn hàng được đặt bởi khách hàng.

Hai câu diễn tả cùng một quan hệ nhưng làm rõ vai trò của từng thực thể.

Một quan hệ cần trả lời hai câu hỏi độc lập:

1. Một cá thể ở phía A có thể hoặc phải liên kết với bao nhiêu cá thể ở phía B?
2. Một cá thể ở phía B có thể hoặc phải liên kết với bao nhiêu cá thể ở phía A?

Số lượng tối đa xác định quan hệ một-một, một-nhiều hay nhiều-nhiều. Số lượng tối thiểu cho biết quan hệ có bắt buộc hay không. Không nên chỉ nói “một-nhiều” mà bỏ qua việc một khách hàng có thể chưa có đơn hàng hoặc một đơn nháp có thể chưa có dòng hàng.

## 2. Cardinality và participation

### 2.1. Cardinality: số lượng tối đa

Cardinality mô tả số lượng cá thể tối đa có thể tham gia quan hệ ở mỗi phía.

| Kiểu | Ý nghĩa | Ví dụ |
|---|---|---|
| 1:1 | Mỗi cá thể phía A liên kết tối đa một cá thể phía B và ngược lại | Hồ sơ khách hàng và tài khoản đăng nhập, nếu nghiệp vụ quy định một-một |
| 1:N | Một cá thể phía A có thể liên kết nhiều cá thể phía B; mỗi cá thể B liên kết tối đa một A | Khách hàng và đơn hàng |
| N:N | Mỗi cá thể ở cả hai phía có thể liên kết với nhiều cá thể phía kia | Sản phẩm và danh mục |

Ký hiệu 1 và N biểu diễn giới hạn tối đa, không tự nói rằng quan hệ có bắt buộc hay không.

### 2.2. Participation: số lượng tối thiểu

Participation (mức tham gia) cho biết một cá thể có bắt buộc phải tham gia quan hệ không.

- **Optional participation:** số lượng tối thiểu là 0. Cá thể có thể tồn tại mà chưa có liên kết.
- **Mandatory participation:** số lượng tối thiểu là 1. Cá thể hợp lệ phải có ít nhất một liên kết.

Có thể kết hợp min/max để ghi rõ quy tắc:

| Min..Max | Diễn giải |
|---|---|
| 0..1 | Không có hoặc có tối đa một |
| 1..1 | Bắt buộc đúng một |
| 0..N | Không có hoặc có nhiều |
| 1..N | Phải có ít nhất một, có thể nhiều |

Ví dụ:

- Một khách hàng có thể đặt 0..N đơn hàng.
- Mỗi đơn hàng phải thuộc đúng 1 khách hàng.
- Một đơn hàng ở trạng thái nháp có thể có 0..N dòng hàng.
- Một đơn hàng đã xác nhận phải có 1..N dòng hàng.

Quy tắc cuối phụ thuộc trạng thái đơn hàng. Sơ đồ ER thông thường không thể hiện hết điều kiện này; cần ghi thành business rule và kiểm tra trong quy trình xác nhận đơn.

### 2.3. Đọc min/max từ cả hai phía

Với quan hệ Customer–SalesOrder:

| Phía | Min..Max | Câu nghiệp vụ |
|---|---:|---|
| Customer → SalesOrder | 0..N | Một khách hàng có thể chưa đặt đơn hoặc đặt nhiều đơn |
| SalesOrder → Customer | 1..1 | Mỗi đơn hàng phải thuộc đúng một khách hàng |

Với quan hệ Product–Category:

| Phía | Min..Max | Câu nghiệp vụ |
|---|---:|---|
| Product → Category | 0..N hoặc 1..N | Một sản phẩm có thể chưa được phân loại hoặc phải có ít nhất một danh mục |
| Category → Product | 0..N hoặc 1..N | Một danh mục có thể đang rỗng hoặc phải có sản phẩm |

Hai cột min/max ở hai phía phải xuất phát từ quy tắc thực tế. Không mặc định sản phẩm luôn phải có danh mục hoặc danh mục luôn phải có sản phẩm; catalog có thể cho phép tạo trước rồi phân loại sau.

## 3. Quan hệ một với một (1:1)

Quan hệ 1:1 có nghĩa mỗi cá thể của thực thể A liên kết với tối đa một cá thể của thực thể B, và mỗi cá thể B liên kết với tối đa một A.

Ví dụ, hệ thống cửa hàng có thể quy định mỗi hồ sơ khách hàng có đúng một tài khoản đăng nhập và mỗi tài khoản đăng nhập thuộc đúng một hồ sơ khách hàng.

~~~mermaid
erDiagram
    CUSTOMER ||--|| CUSTOMER_ACCOUNT : has
~~~

Sơ đồ này biểu diễn quan hệ bắt buộc một-một ở cả hai phía. Nếu tài khoản chỉ được tạo khi khách kích hoạt đăng nhập, quan hệ có thể là tùy chọn ở phía Customer:

~~~mermaid
erDiagram
    CUSTOMER ||--o| CUSTOMER_ACCOUNT : may_have
~~~

Cách đọc: mỗi tài khoản thuộc đúng một khách hàng; một khách hàng có thể chưa có tài khoản hoặc có tối đa một tài khoản.

### 3.1. Khi nào nên dùng 1:1?

Quan hệ 1:1 có thể hữu ích khi:

- Hai nhóm dữ liệu có vòng đời khác nhau.
- Có ranh giới bảo mật hoặc quyền truy cập khác nhau.
- Một nhóm thuộc tính chỉ được tạo sau một bước nghiệp vụ.
- Một phần dữ liệu lớn hoặc ít được truy cập, cần tách khỏi bản ghi chính.
- Hai hệ thống hoặc nhóm nghiệp vụ quản lý hai phần riêng biệt.

Ví dụ Customer và CustomerAccount có thể tách vì hồ sơ khách hàng thuộc nghiệp vụ bán hàng, còn thông tin xác thực thuộc miền bảo mật. Tài khoản có thể được khóa hoặc vô hiệu hóa theo quy trình riêng, trong khi hồ sơ khách hàng vẫn được giữ để phục vụ đơn hàng và hỗ trợ.

Tuy nhiên, nếu hai nhóm dữ liệu luôn được tạo, đọc, cập nhật và xóa cùng nhau, không có ranh giới bảo mật hay vòng đời riêng, việc tách thành hai thực thể 1:1 có thể làm mô hình phức tạp không cần thiết. Có thể gộp chúng thành một thực thể.

### 3.2. Triển khai 1:1 bằng khóa ngoại

Một cách triển khai là đặt khóa ngoại ở bảng phụ thuộc và thêm UNIQUE để bảo đảm mỗi bản ghi cha có tối đa một bản ghi con.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);

CREATE TABLE customer_account (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL UNIQUE
        REFERENCES customer(customer_id)
        ON DELETE RESTRICT,
    login_name VARCHAR(120) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Ý nghĩa:

- FOREIGN KEY bảo đảm tài khoản tham chiếu khách hàng tồn tại.
- NOT NULL bảo đảm mỗi tài khoản phải thuộc một khách hàng.
- UNIQUE(customer_id) bảo đảm một khách hàng không có hai tài khoản.
- Mỗi khách hàng có thể chưa có tài khoản vì khóa ngoại nằm ở bảng CustomerAccount, không bắt buộc Customer phải có dòng con.

Đây là quan hệ 0..1 ở phía CustomerAccount khi nhìn từ Customer, và 1..1 từ tài khoản về khách hàng.

Nếu nghiệp vụ bắt buộc mọi khách hàng đều phải có tài khoản ngay khi tạo, khóa ngoại ở bảng con không đủ để bảo đảm chiều ngược lại. Cần cân nhắc gộp bảng, tạo hai bản ghi trong cùng transaction qua quy trình ứng dụng, hoặc dùng cơ chế ràng buộc trì hoãn/trigger phù hợp với hệ quản trị. Không nên nghĩ rằng UNIQUE và NOT NULL tự động bảo đảm mỗi Customer có một CustomerAccount.

### 3.3. Chọn phía đặt khóa ngoại

Thông thường đặt khóa ngoại ở phía:

- Có tính bắt buộc tham chiếu phía kia.
- Được tạo sau hoặc phụ thuộc vòng đời.
- Có thể tồn tại tùy chọn đối với phía còn lại.
- Có dữ liệu tách biệt về bảo mật hoặc quyền sở hữu.

Nếu cả hai phía bắt buộc và được tạo cùng nhau, việc chọn phía đặt khóa ngoại cần xét luồng tạo dữ liệu và khả năng xử lý transaction. Đôi khi hai bảng có thể gộp lại là lựa chọn đơn giản hơn.

### 3.4. Những lỗi thường gặp với 1:1

- **Thiếu UNIQUE:** khóa ngoại chỉ bảo đảm tham chiếu hợp lệ, không ngăn nhiều dòng con cùng tham chiếu một dòng cha. Khi đó quan hệ thực tế là 1:N.
- **Đặt NOT NULL sai phía:** có thể ép một liên kết bắt buộc trong khi nghiệp vụ cho phép chưa có đối tượng liên quan.
- **Cho rằng khóa ngoại bảo đảm cả hai chiều:** FK ở bảng con không bảo đảm mỗi bảng cha có ít nhất một bản ghi con.
- **Tách bảng chỉ để tạo thêm bảng:** nếu không có vòng đời, quyền truy cập hoặc lý do vận hành riêng, việc tách có thể làm tăng join và transaction.

## 4. Quan hệ một với nhiều (1:N)

Quan hệ 1:N có nghĩa một cá thể phía A có thể liên kết với nhiều cá thể phía B, nhưng mỗi cá thể phía B liên kết với tối đa một cá thể A.

Ví dụ:

- Một khách hàng có thể đặt nhiều đơn hàng.
- Mỗi đơn hàng thuộc về một khách hàng.
- Một đơn hàng có nhiều dòng hàng.
- Mỗi dòng hàng thuộc một đơn hàng.

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--o{ ORDER_ITEM : contains
~~~

Ở quan hệ Customer–SalesOrder, phía khách hàng là 1 và phía đơn hàng là N. Mỗi đơn hàng phải tham chiếu một khách hàng; khách hàng có thể chưa có đơn nào.

Ở quan hệ SalesOrder–OrderItem, đơn đã xác nhận có ít nhất một dòng. Trong thực tế, đơn nháp có thể chưa có dòng, nên tính bắt buộc phải được gắn với trạng thái.

### 4.1. Triển khai 1:N bằng khóa ngoại ở phía N

Trong mô hình quan hệ, khóa ngoại thường nằm ở bảng phía nhiều.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);

CREATE TABLE sales_order (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL
        REFERENCES customer(customer_id)
        ON DELETE RESTRICT,
    status VARCHAR(24) NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_sales_order_customer
    ON sales_order(customer_id);
~~~

Mỗi dòng SalesOrder lưu customer_id. Nhiều dòng đơn hàng có thể dùng cùng customer_id. Vì cột không có UNIQUE, một khách hàng có thể được tham chiếu bởi nhiều đơn hàng.

NOT NULL thể hiện mỗi đơn hàng phải thuộc một khách hàng. Nếu đơn nháp có thể chưa gắn khách, có thể cho phép NULL hoặc dùng một mô hình khách vãng lai riêng; quyết định này phải phù hợp với nghiệp vụ và yêu cầu kiểm toán.

### 4.2. Vì sao khóa ngoại nằm ở phía nhiều?

Giả sử đặt một cột danh sách order_id trong Customer để lưu mọi đơn hàng của khách. Cách này làm khó việc:

- Kiểm tra từng đơn hàng có tồn tại.
- Tìm khách hàng của một đơn hàng.
- Thêm hoặc xóa một liên kết mà không ghi đè danh sách.
- Truy vấn, phân trang và đánh chỉ mục các đơn.
- Bảo đảm mỗi đơn thuộc đúng một khách.

Đặt customer_id trong SalesOrder cho phép mỗi dòng đơn tham chiếu đúng một khách hàng bằng FK, còn nhiều đơn có thể cùng tham chiếu một khách. Đây là cách ánh xạ tự nhiên của 1:N.

### 4.3. Một-nhiều có thể có phía tùy chọn

Ví dụ khách hàng và địa chỉ lưu sẵn:

- Một khách hàng có thể lưu 0..N địa chỉ.
- Mỗi địa chỉ phải thuộc đúng một khách hàng.

~~~mermaid
erDiagram
    CUSTOMER ||--o{ CUSTOMER_ADDRESS : owns
~~~

Bảng địa chỉ có customer_id NOT NULL. Nếu địa chỉ có thể được chia sẻ giữa nhiều hồ sơ, đây không còn là quan hệ 1:N đơn giản; cần mô hình hóa theo quy tắc chia sẻ, có thể thành N:N.

### 4.4. Quan hệ một-nhiều có thuộc tính lịch sử

Giả sử một nhân viên phụ trách một phòng ban tại một thời điểm. Nếu nhân viên có thể chuyển phòng ban và cần lưu lịch sử, việc chỉ lưu department_id hiện tại trên Employee không đủ để biết nhân viên từng làm ở đâu.

Có thể tạo thực thể EmployeeDepartmentAssignment:

- Employee 1:N EmployeeDepartmentAssignment.
- Department 1:N EmployeeDepartmentAssignment.
- Mỗi assignment có valid_from, valid_to, chức vụ hoặc tỷ lệ phân bổ.

Lúc này hai quan hệ 1:N tạo thành mô hình liên kết có lịch sử. Nếu nhân viên có thể đồng thời làm ở nhiều phòng ban, cần xem xét quan hệ N:N thay vì giả định một phòng ban hiện tại duy nhất.

### 4.5. Các lỗi thường gặp với 1:N

- Đặt FK ở phía một rồi lưu danh sách ID trong một cột.
- Quên NOT NULL khi phía nhiều bắt buộc có cha.
- Đặt UNIQUE trên FK làm quan hệ vô tình thành 1:1.
- Không đánh chỉ mục FK dù truy vấn thường xuyên lọc theo khóa đó.
- Dùng ON DELETE CASCADE mà không xem xét vòng đời và yêu cầu lưu lịch sử.
- Nhầm số lượng tối đa với tối thiểu: 1:N không có nghĩa mỗi cha bắt buộc phải có con.

## 5. Quan hệ nhiều với nhiều (N:N)

Quan hệ N:N có nghĩa mỗi cá thể ở phía A có thể liên kết với nhiều cá thể ở phía B, và ngược lại.

Ví dụ sản phẩm và danh mục:

- Một sản phẩm có thể thuộc nhiều danh mục.
- Một danh mục có thể chứa nhiều sản phẩm.

~~~mermaid
erDiagram
    PRODUCT ||--o{ PRODUCT_CATEGORY : classified_by
    CATEGORY ||--o{ PRODUCT_CATEGORY : includes
~~~

Trong sơ đồ quan hệ, N:N thường được triển khai qua một thực thể liên kết, ở đây là ProductCategory. Mỗi dòng ProductCategory đại diện cho một liên kết giữa một sản phẩm và một danh mục.

### 5.1. Vì sao cần bảng liên kết?

Không nên lưu một danh sách category_id trong một cột Product hoặc danh sách product_id trong Category. Cách đó khiến khóa ngoại, truy vấn và cập nhật khó bảo đảm tính toàn vẹn.

Bảng liên kết giải quyết bằng cách lưu mỗi cặp khóa trong một dòng:

~~~sql
CREATE TABLE product (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(250) NOT NULL
);

CREATE TABLE category (
    category_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug VARCHAR(160) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE product_category (
    product_id BIGINT NOT NULL
        REFERENCES product(product_id)
        ON DELETE RESTRICT,
    category_id BIGINT NOT NULL
        REFERENCES category(category_id)
        ON DELETE RESTRICT,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (product_id, category_id)
);

CREATE INDEX ix_product_category_category
    ON product_category(category_id, product_id);
~~~

Khóa chính ghép (product_id, category_id) ngăn cùng một sản phẩm được gán vào cùng một danh mục nhiều lần. Hai khóa ngoại bảo đảm cả sản phẩm và danh mục đều tồn tại.

Khóa chính ghép bắt đầu bằng product_id nên hỗ trợ tìm danh mục của một sản phẩm. Chỉ mục đảo chiều (category_id, product_id) hỗ trợ tìm sản phẩm trong một danh mục.

Nếu nghiệp vụ cho phép sản phẩm có nhiều danh mục nhưng chỉ một danh mục chính, có thể thêm partial unique index:

~~~sql
CREATE UNIQUE INDEX uq_product_one_primary_category
    ON product_category(product_id)
    WHERE is_primary;
~~~

Ràng buộc này bảo đảm mỗi sản phẩm có tối đa một danh mục chính. Nó không bảo đảm mọi sản phẩm phải có danh mục chính; điều kiện tối thiểu đó cần được kiểm tra khi phát hành sản phẩm hoặc bằng cơ chế bổ sung.

### 5.2. Quan hệ liên kết có thuộc tính riêng

Một quan hệ N:N có thể mang thông tin riêng:

- Ngày sản phẩm được thêm vào danh mục.
- Người thực hiện việc phân loại.
- Vai trò của sản phẩm trong danh mục.
- Thứ tự hiển thị sản phẩm.
- Trạng thái hoặc khoảng hiệu lực của liên kết.

Những dữ liệu này mô tả lần gán Product–Category, không thuộc riêng Product hay Category. Vì vậy, chúng nằm ở ProductCategory.

Tương tự, quan hệ đơn hàng–sản phẩm thực tế thường được mô hình hóa thành OrderItem vì một lần mua có số lượng, giá, chiết khấu, thuế và số thứ tự riêng.

~~~mermaid
erDiagram
    SALES_ORDER ||--o{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
~~~

OrderItem là thực thể liên kết/chi tiết giữa SalesOrder và Product. Mỗi OrderItem tham chiếu đúng một đơn và một sản phẩm; một đơn có thể có nhiều dòng, một sản phẩm có thể xuất hiện ở nhiều dòng thuộc nhiều đơn.

### 5.3. Chọn khóa cho bảng liên kết

Có hai cách phổ biến:

**Khóa chính ghép:** dùng cặp FK làm khóa chính. Phù hợp khi mỗi cặp chỉ được phép xuất hiện một lần, như ProductCategory hiện tại.

**Khóa thay thế:** thêm relationship_id riêng khi mỗi lần liên kết cần định danh độc lập, có thể lặp lại cùng cặp thực thể theo thời gian hoặc được tham chiếu từ nơi khác.

Ví dụ một sản phẩm có thể được gán vào cùng một danh mục, sau đó gỡ ra và gán lại. Nếu cần giữ từng đợt gán, khóa ghép đơn giản (product_id, category_id) không đủ vì cặp này có thể lặp qua các giai đoạn. Có thể dùng:

~~~sql
CREATE TABLE product_category_assignment (
    assignment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES product(product_id),
    category_id BIGINT NOT NULL REFERENCES category(category_id),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX ix_assignment_product_period
    ON product_category_assignment(product_id, valid_from DESC);

CREATE INDEX ix_assignment_category_period
    ON product_category_assignment(category_id, valid_from DESC);
~~~

Lược đồ này cho phép nhiều đợt gán theo thời gian. Nếu các khoảng hiệu lực không được chồng lấn, cần thêm exclusion constraint hoặc cơ chế transaction tương đương. Chỉ có CHECK trên từng dòng không thể ngăn hai dòng khác nhau chồng lấn thời gian.

### 5.4. Khi nào không nên giữ quan hệ N:N trực tiếp?

Trong mô hình khái niệm có thể vẽ N:N trực tiếp để dễ diễn đạt. Khi chuyển sang mô hình quan hệ, cần thực thể liên kết. Nếu quan hệ có vòng đời, thuộc tính, định danh hoặc được các thực thể khác tham chiếu, bảng liên kết càng cần được xem như một thực thể nghiệp vụ thực thụ.

Ví dụ, quan hệ giữa nhân viên và dự án có thể có vai trò, ngày bắt đầu, ngày kết thúc và số giờ phân bổ. Khi đó Assignment là thực thể rõ ràng hơn một bảng nối không tên.

## 6. So sánh ba kiểu quan hệ qua một ví dụ

| Tiêu chí | 1:1 | 1:N | N:N |
|---|---|---|---|
| Quy tắc tối đa | Mỗi bên liên kết tối đa một | Một bên nhiều, bên kia tối đa một | Cả hai bên đều có thể nhiều |
| Ví dụ | Customer–CustomerAccount | Customer–SalesOrder | Product–Category |
| Ánh xạ quan hệ | FK + UNIQUE | FK ở phía N | Bảng liên kết với hai FK |
| Ràng buộc chính | FK, UNIQUE, NOT NULL tùy participation | FK, NOT NULL/NULL tùy participation | Hai FK, PK ghép hoặc UNIQUE |
| Câu hỏi cần làm rõ | Có cần tách hai thực thể không? | Con có bắt buộc có cha không? | Cặp liên kết có được lặp không? |
| Rủi ro hay gặp | Thiếu UNIQUE khiến thành 1:N | Lưu danh sách con ở phía cha | Thiếu bảng liên kết hoặc khóa chống trùng |

Một mô hình cửa hàng tổng hợp:

~~~mermaid
erDiagram
    CUSTOMER ||--o| CUSTOMER_ACCOUNT : may_have
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : appears_in
    PRODUCT ||--o{ PRODUCT_CATEGORY : classified_by
    CATEGORY ||--o{ PRODUCT_CATEGORY : includes
~~~

Các ký hiệu phản ánh giả định của ví dụ:

- Một khách hàng có thể chưa có tài khoản đăng nhập hoặc có tối đa một tài khoản.
- Mỗi tài khoản đăng nhập thuộc đúng một khách hàng.
- Khách hàng có thể chưa đặt đơn hoặc đặt nhiều đơn.
- Mỗi đơn đã xác nhận có ít nhất một dòng hàng; nếu có đơn nháp, quan hệ dòng hàng cần quy tắc theo trạng thái.
- Sản phẩm và danh mục liên kết nhiều-nhiều thông qua ProductCategory.

## 7. Ánh xạ quan hệ sang cơ sở dữ liệu quan hệ

### 7.1. Quy tắc tổng quát

| Kiểu quan hệ | Cách ánh xạ phổ biến |
|---|---|
| 1:1 | Đặt FK ở một bảng và thêm UNIQUE trên FK |
| 1:N | Đặt FK ở bảng phía nhiều |
| N:N | Tạo bảng liên kết có FK đến cả hai phía |

Các ràng buộc bổ sung:

- **NOT NULL:** thể hiện FK bắt buộc ở phía tham chiếu.
- **UNIQUE:** giới hạn tối đa một liên kết cho một giá trị FK.
- **PRIMARY KEY:** bảo đảm định danh duy nhất cho dòng hoặc cặp liên kết.
- **FOREIGN KEY:** bảo đảm phía được tham chiếu tồn tại.
- **CHECK:** kiểm tra điều kiện trên dữ liệu của một dòng, ví dụ valid_to > valid_from.

Không phải mọi cardinality đều có thể bảo đảm bằng một FK. Ví dụ “mỗi khách hàng phải có ít nhất một đơn hàng” là ràng buộc qua nhiều dòng và thường không nên áp đặt nếu nghiệp vụ cho phép khách hàng mới chưa mua. Nếu thực sự bắt buộc, cần transaction, trigger trì hoãn hoặc quy trình phát hành phù hợp.

### 7.2. Tính bắt buộc và NULL

Nếu khóa ngoại ở phía nhiều là NOT NULL, mỗi dòng phía nhiều phải tham chiếu một dòng phía một. Nếu FK cho phép NULL, một dòng phía nhiều có thể chưa gắn với dòng cha.

Ví dụ đơn hàng có thể được tạo ở trạng thái nháp trước khi khách hàng đăng nhập. Có thể cho phép customer_id NULL ở trạng thái nháp, nhưng khi xác nhận phải có khách hàng hợp lệ. Một CHECK đơn giản có thể kiểm tra quan hệ giữa status và customer_id trên cùng dòng:

~~~sql
CHECK (
    status = 'DRAFT'
    OR customer_id IS NOT NULL
)
~~~

Điều này chỉ minh họa điều kiện trên một dòng. Các quy tắc liên quan nhiều bảng, như đơn đã xác nhận phải có ít nhất một OrderItem, cần kiểm tra trong transaction hoặc trigger thích hợp.

### 7.3. Chọn ON DELETE

Khi xóa một dòng được tham chiếu, cơ sở dữ liệu cần quy tắc:

- **RESTRICT / NO ACTION:** từ chối xóa nếu còn tham chiếu. Phù hợp với dữ liệu giao dịch cần giữ lịch sử.
- **CASCADE:** xóa các dòng phụ thuộc. Phù hợp với dữ liệu con có vòng đời hoàn toàn phụ thuộc và không cần giữ riêng.
- **SET NULL:** xóa liên kết nhưng giữ dòng con. Chỉ dùng khi FK cho phép NULL và nghiệp vụ chấp nhận mất liên kết.
- **SET DEFAULT:** thay bằng giá trị mặc định nếu có ý nghĩa và giá trị mặc định hợp lệ.

Không chọn CASCADE chỉ để việc xóa dễ dàng. Xóa một khách hàng có thể kéo theo đơn hàng và thanh toán là rủi ro lớn. Với dữ liệu thương mại, thường dùng trạng thái vô hiệu hóa hoặc ẩn thay cho xóa vật lý.

## 8. Cardinality trong mô hình khái niệm và ràng buộc thực thi

Một sơ đồ ER giúp trao đổi với nghiệp vụ, nhưng chưa đủ để bảo đảm mọi quy tắc khi nhiều transaction chạy đồng thời.

Ví dụ, một sản phẩm chỉ được có tối đa một danh mục chính. Partial unique index có thể bảo đảm giới hạn tối đa đó. Nhưng quy tắc “mỗi sản phẩm đang bán phải có ít nhất một danh mục chính” cần kiểm tra khi phát hành sản phẩm hoặc bằng transaction/trigger.

Một đơn hàng đã xác nhận phải có ít nhất một dòng hàng. FK từ OrderItem đến SalesOrder chỉ bảo đảm mỗi dòng hàng có đơn cha. Nó không bảo đảm mỗi đơn hàng có con. Đây là khác biệt giữa kiểm tra tham chiếu từ con lên cha và kiểm tra tồn tại ít nhất một con từ cha xuống.

Tương tự, với quan hệ 1:1 bắt buộc cả hai phía, FK + UNIQUE ở bảng phụ thuộc không bảo đảm bảng cha luôn có bảng con. Cần thiết kế luồng tạo đồng bộ hoặc cơ chế ràng buộc bổ sung.

Hãy phân loại các quy tắc:

| Quy tắc | Có thể bảo vệ bằng |
|---|---|
| FK tham chiếu dòng tồn tại | FOREIGN KEY |
| Mỗi khách hàng có tối đa một tài khoản | UNIQUE trên customer_id ở CustomerAccount |
| Mỗi tài khoản phải thuộc khách hàng | NOT NULL + FOREIGN KEY |
| Một đơn phải thuộc khách hàng khi xác nhận | CHECK trạng thái trên dòng hoặc quy trình transaction |
| Một đơn đã xác nhận phải có ít nhất một dòng | Transaction/trigger/quy trình xác nhận |
| Một sản phẩm có tối đa một danh mục chính | Partial UNIQUE index |
| Một sản phẩm phải có ít nhất một danh mục chính khi phát hành | Quy trình phát hành/transaction/trigger |
| Không có hai khoảng gán danh mục chồng lấn | Exclusion constraint hoặc kiểm soát đồng thời tương đương |

## 9. Các lỗi mô hình hóa thường gặp

### Lỗi 1: Nhầm 1:N thành 1:1

Bảng phía nhiều có FK nhưng vô tình thêm UNIQUE trên FK. Kết quả mỗi khách hàng chỉ có thể có một đơn hàng.

Cách sửa: bỏ UNIQUE nếu nghiệp vụ cho phép nhiều đơn; chỉ giữ FK và chỉ mục phù hợp.

### Lỗi 2: Nhầm N:N thành 1:N

Đặt category_id trực tiếp trên Product trong khi một sản phẩm có thể thuộc nhiều danh mục. Cách này buộc mỗi sản phẩm chỉ có một danh mục.

Cách sửa: tạo ProductCategory với hai FK và ràng buộc duy nhất cho cặp nếu cặp chỉ được phép một lần.

### Lỗi 3: Lưu danh sách ID trong một cột

Lưu product_ids = "12,13,14" trong Category làm mất khả năng bảo đảm FK và khiến truy vấn theo sản phẩm khó tối ưu.

Cách sửa: một liên kết là một dòng trong bảng liên kết.

### Lỗi 4: Chỉ ghi “nhiều” mà không ghi min/max

Không rõ khách hàng mới có thể chưa có đơn hay đơn nháp có thể chưa có dòng hàng.

Cách sửa: ghi 0..N hoặc 1..N và ghi điều kiện theo trạng thái nếu có.

### Lỗi 5: Bỏ qua thuộc tính của quan hệ

Bảng nối ProductCategory không lưu được ngày gán, người gán hoặc danh mục chính nếu không có cột riêng.

Cách sửa: mô hình hóa quan hệ có thuộc tính thành thực thể liên kết.

### Lỗi 6: Dùng khóa ghép không phù hợp với lịch sử

Cặp product_id và category_id chỉ xuất hiện một lần trong bảng hiện tại, nhưng nghiệp vụ muốn giữ nhiều đợt gán theo thời gian.

Cách sửa: thêm assignment_id hoặc dùng khóa bao gồm mốc thời gian; xác định quy tắc khoảng hiệu lực và chống chồng lấn.

### Lỗi 7: Dùng CASCADE trên dữ liệu cần kiểm toán

Xóa cha kéo theo các dòng giao dịch quan trọng.

Cách sửa: dùng RESTRICT, vô hiệu hóa chủ thể hoặc lưu trữ theo chính sách dữ liệu.

## 10. Quy trình xác định kiểu quan hệ

Khi đọc một yêu cầu, hãy thực hiện các bước:

1. Xác định hai thực thể tham gia quan hệ.
2. Đặt tên quan hệ bằng một động từ hoặc cụm từ rõ nghĩa.
3. Hỏi với một cá thể A, có thể liên kết tối đa bao nhiêu cá thể B?
4. Hỏi với một cá thể B, có thể liên kết tối đa bao nhiêu cá thể A?
5. Xác định số lượng tối thiểu ở cả hai phía: 0 hay 1?
6. Kiểm tra tính bắt buộc có thay đổi theo trạng thái hoặc thời điểm không.
7. Nếu là 1:1, xem hai thực thể có vòng đời hoặc ranh giới quản lý riêng không.
8. Nếu là 1:N, đặt FK ở phía nhiều và quyết định NULL/NOT NULL.
9. Nếu là N:N, tạo thực thể liên kết; tìm thuộc tính và vòng đời của quan hệ.
10. Chọn khóa, UNIQUE, chỉ mục và hành vi xóa phù hợp.
11. Thử dữ liệu hợp lệ, dữ liệu vi phạm và thao tác đồng thời để kiểm chứng.

## 11. Bài tập thực hành

### Bài tập 1: Khách hàng và tài khoản đăng nhập

Mỗi khách hàng có thể chưa đăng ký tài khoản đăng nhập. Mỗi tài khoản phải thuộc đúng một khách hàng. Một khách hàng không được có hai tài khoản đang hoạt động.

Hãy xác định:

- Kiểu quan hệ và min/max ở hai phía.
- Bảng nào nên chứa FK?
- Có cần UNIQUE không?
- Có cần partial unique index nếu tài khoản đã khóa vẫn được giữ lịch sử không?

Gợi ý: Customer–CustomerAccount là 1:1 tùy chọn từ phía Customer. Đặt FK ở CustomerAccount, NOT NULL và UNIQUE(customer_id). Nếu lịch sử tài khoản có thể có nhiều dòng theo thời gian nhưng chỉ một dòng đang hoạt động, dùng định danh tài khoản riêng và partial unique index cho dòng hoạt động.

### Bài tập 2: Khách hàng và đơn hàng

Một khách hàng có thể đặt nhiều đơn hàng. Mỗi đơn hàng phải thuộc đúng một khách hàng.

Hãy xác định:

- Cardinality và participation.
- Vị trí FK.
- Trường hợp đơn nháp chưa gắn khách hàng có được phép không?

Gợi ý: Customer 0..N SalesOrder; SalesOrder 1..1 Customer. Đặt customer_id ở SalesOrder. Nếu đơn nháp được phép chưa gắn khách, cho phép NULL ở trạng thái nháp và kiểm tra trước khi xác nhận.

### Bài tập 3: Sản phẩm và danh mục

Một sản phẩm có thể thuộc nhiều danh mục. Một danh mục có thể có nhiều sản phẩm. Mỗi sản phẩm đang bán phải có một danh mục chính, ngoài ra có thể có các danh mục phụ.

Hãy xác định:

- Vì sao cần bảng liên kết?
- Khóa chính của bảng liên kết là gì?
- Làm sao bảo đảm tối đa một danh mục chính?
- Làm sao bảo đảm tối thiểu một danh mục chính khi sản phẩm được phát hành?

Gợi ý: ProductCategory có khóa ghép product_id, category_id. Dùng partial unique index để giới hạn một dòng is_primary = true trên mỗi product. Quy tắc phải có ít nhất một dòng chính cần kiểm tra trong transaction phát hành hoặc cơ chế tương đương.

### Bài tập 4: Nhân viên và dự án

Một nhân viên có thể tham gia nhiều dự án. Một dự án có nhiều nhân viên. Mỗi lần tham gia có ngày bắt đầu, ngày kết thúc, vai trò và tỷ lệ phân bổ.

Hãy xác định:

- Quan hệ N:N được triển khai qua thực thể nào?
- Có cần assignment_id không?
- Có thể cho một nhân viên tham gia cùng một dự án nhiều đợt không?
- Cần ràng buộc gì cho thời gian?

Gợi ý: dùng ProjectAssignment với hai FK, ngày bắt đầu/kết thúc, vai trò và tỷ lệ phân bổ. Nếu có nhiều đợt tham gia, dùng khóa thay thế hoặc khóa ghép có valid_from; kiểm tra ngày kết thúc lớn hơn ngày bắt đầu và chống khoảng thời gian chồng lấn nếu nghiệp vụ không cho phép.

### Bộ câu hỏi rà soát

- Quan hệ đã được đọc đúng từ cả hai phía chưa?
- Cardinality tối đa có đúng với nghiệp vụ không?
- Participation tối thiểu có được ghi rõ không?
- Có điều kiện theo trạng thái hoặc thời gian không?
- FK đã đặt ở phía phù hợp chưa?
- UNIQUE có đang vô tình giới hạn một quan hệ 1:N thành 1:1 không?
- N:N đã có bảng liên kết với hai FK chưa?
- Quan hệ có thuộc tính riêng hoặc vòng đời riêng không?
- Khóa của bảng liên kết có cho phép lịch sử và các lần lặp hợp lệ không?
- Hành vi xóa có bảo vệ dữ liệu giao dịch và lịch sử không?
- Các quy tắc min/max nào chưa thể bảo đảm bằng ràng buộc trên một dòng?
- Truy vấn thường gặp có chỉ mục phù hợp không?

Quan hệ 1:1, 1:N và N:N mô tả số lượng liên kết tối đa giữa các thực thể. Để mô hình đúng nghiệp vụ, cần ghi thêm số lượng tối thiểu và tính bắt buộc ở mỗi phía. Khi ánh xạ sang cơ sở dữ liệu quan hệ, 1:1 thường dùng FK kèm UNIQUE, 1:N đặt FK ở phía nhiều, còn N:N dùng bảng liên kết. Việc kiểm tra các ràng buộc, vòng đời và thuộc tính của quan hệ giúp lược đồ vừa phản ánh đúng dữ liệu hiện tại, vừa hỗ trợ lịch sử và thay đổi nghiệp vụ.
