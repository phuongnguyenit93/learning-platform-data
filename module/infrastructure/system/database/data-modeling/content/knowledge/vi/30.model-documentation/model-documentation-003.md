# Định nghĩa khóa, quan hệ, bội số và hành vi vòng đời

Một sơ đồ thực thể–quan hệ có thể cho thấy **Customer nối với Order**, **Order nối với OrderLine** và **OrderLine nối với Product**. Nhưng chỉ nhìn đường nối chưa đủ để đội phát triển triển khai đúng:

- Một khách có thể đặt bao nhiêu đơn? Một đơn có thể **không có khách** khi mua tại quầy hay không?
- Một đơn nháp có được phép chưa có dòng hàng? Một đơn đã xác nhận có thể bị xóa dòng cuối cùng không?
- Product có thể xuất hiện trong nhiều OrderLine không? Nếu Product đổi tên hoặc ngừng kinh doanh, những dòng bán cũ phải xử lý thế nào?
- Mã Order chỉ duy nhất **trong tenant** hay toàn bộ hệ thống? Mã khách có được tái sử dụng?
- Khi xóa Customer, Order bị xóa theo, bị chặn, hay còn lại với thông tin ẩn danh? Có phải mọi “xóa” đều là DELETE vật lý?

Nếu tài liệu chỉ ghi “Customer 1–N Order” mà không giải thích **khóa, phạm vi định danh, bội số tối thiểu/tối đa, tính bắt buộc, thời điểm hiệu lực và hành vi vòng đời**, mỗi nhóm triển khai sẽ tự suy diễn. Kết quả có thể là một CSDL hợp lệ về cú pháp nhưng vi phạm quy tắc bán hàng, quyền sở hữu hoặc lịch sử kế toán.

Bài này thuộc chương **Tài liệu mô hình** trong module **DATABASE_DATA_MODELING**. Mục tiêu là học cách viết **hợp đồng mô hình dữ liệu** đủ rõ để chuyển yêu cầu nghiệp vụ thành PK/FK/UNIQUE/CHECK, thiết kế quan hệ, quy tắc cập nhật–xóa–lưu lịch sử và phép kiểm chứng. Các ví dụ sử dụng PostgreSQL, đồng thời chỉ ra cách ý nghĩa đó được diễn đạt trong mô hình document, graph và phân tích.

> **Nguyên tắc:** Mỗi đường quan hệ phải đọc được thành **một câu nghiệp vụ có chủ ngữ và vị ngữ**, kèm **bội số ở cả hai phía**, phạm vi khóa, quy tắc ghi và hành vi khi đối tượng thay đổi hoặc kết thúc vòng đời. ERD chỉ là một hình chiếu của hợp đồng, không phải toàn bộ hợp đồng.

## 1. Tài liệu hóa mô hình là tài liệu hóa điều gì?

Một mô hình dữ liệu có ba tầng thường cần phân biệt:

| Tầng | Câu hỏi | Ví dụ cần ghi |
| --- | --- | --- |
| **Khái niệm (conceptual)** | Nghiệp vụ có những thực thể và mối quan hệ nào? | Customer đặt Order; Order gồm các Line |
| **Logic (logical)** | Điều gì định danh thực thể, bội số và quy tắc nào phải đúng? | Một Line thuộc đúng một Order; Order CONFIRMED phải có ít nhất một Line |
| **Vật lý (physical)** | DBMS lưu và cưỡng chế bằng khóa, chỉ mục, cột và giao dịch ra sao? | PK(tenant_id,order_id,line_no), FK ghép, CHECK, procedure xác nhận |

**Cùng một quy tắc** có thể xuất hiện ở cả ba tầng nhưng với độ chi tiết khác nhau. Ví dụ:

- Khái niệm: “Một Order gồm các dòng hàng.”
- Logic: “Một Order DRAFT có 0..N Line; một Order CONFIRMED có 1..N Line; một Line có đúng một Order, không thể di chuyển sang Order khác sau khi được tạo.”
- Vật lý: bảng order_lines có FK (tenant_id,order_id), khóa (tenant_id,order_id,line_no), quy trình chuyển trạng thái kiểm tra tồn tại Line trong transaction; mọi đường xóa/sửa Line phải phối hợp với cùng owner.

Nếu chỉ có FK, **chưa thể** kết luận Order luôn có Line. FK bảo vệ hướng **Line → Order**, không tự buộc chiều ngược lại phải có phần tử.

### 1.1. Một hợp đồng quan hệ hoàn chỉnh cần những trường gì?

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| **Tên và ý nghĩa** | Quan hệ “Customer đặt Order” hay “Customer nhận Order”? |
| **Vai trò hai đầu** | Ai là bên sở hữu, tham chiếu, tham gia, được tham chiếu? |
| **Định danh** | Khóa chính, khóa nghiệp vụ, khóa tham chiếu; duy nhất ở phạm vi nào? |
| **Bội số tối thiểu/tối đa** | Mỗi phía có 0, 1 hay nhiều đối tượng liên quan? |
| **Tính bắt buộc** | Bắt buộc ngay khi tạo hay chỉ sau trạng thái/mốc thời gian? |
| **Vòng đời** | Được tạo, gắn, tháo, cập nhật, lưu trữ, ẩn, xóa khi nào? |
| **Ràng buộc** | Cái gì DBMS cưỡng chế được, cái gì do owner/transaction kiểm soát? |
| **Thời gian** | Quan hệ hiện hành hay có lịch sử valid_from/valid_to? |
| **Phạm vi và quyền** | Tenant, service owner, shard, quy tắc bảo mật và truy cập? |
| **Ngoại lệ** | Guest checkout, late data, soft delete, missing reference xử lý thế nào? |
| **Kiểm chứng** | Câu SQL/test nào chứng minh quy tắc trong phạm vi đã chọn? |

Tài liệu chỉ liệt kê tên cột và kiểu SQL là **data dictionary sơ lược**; nó chưa mô tả đầy đủ quan hệ và vòng đời.

## 2. Từ yêu cầu đến khóa: phân biệt các loại khóa

### 2.1. Khóa ứng viên, khóa chính và khóa thay thế

**Khóa ứng viên (candidate key)** là tập thuộc tính tối thiểu phân biệt được một hàng theo quy tắc nghiệp vụ trong **phạm vi định danh xác định**.

Ví dụ, một Order trong hệ SaaS có thể có:

- **Khóa nghiệp vụ:** (tenant_id, order_code), trong đó order_code hiển thị với khách.
- **Khóa kỹ thuật:** (tenant_id, order_id), trong đó order_id do hệ thống cấp.
- **Khóa chính (primary key):** một khóa được chọn làm định danh hàng trong CSDL.
- **Khóa duy nhất khác (alternate key):** một candidate key còn lại được bảo vệ bằng UNIQUE khi phù hợp.

Không nên suy ra order_code là khóa duy nhất toàn hệ chỉ vì ví dụ hiện tại chưa thấy trùng. Nếu hai tenant được phép phát mã O-001 thì uniqueness phải **đặt trong tenant**.

Một ví dụ khác, Product có SKU P-101 có thể đổi mã do tái phân loại nhưng product_id vẫn giữ nguyên. Khi đó SKU là **mã nghiệp vụ có chính sách đổi mã**, còn product_id có thể được chọn làm định danh ổn định của thực thể. Việc tái sử dụng SKU cần chính sách riêng.

### 2.2. Khóa ghép phản ánh phạm vi

~~~text
Order identity:
  (tenant_id, order_id)

Order business code:
  UNIQUE (tenant_id, order_code)

Line identity:
  (tenant_id, order_id, line_no)

Product identity:
  (tenant_id, product_id)
~~~

**line_no = 1** không có ý nghĩa duy nhất ngoài một Order. **order_id = 1001** không được giả định duy nhất ngoài một tenant trừ khi hệ thống cam kết điều đó. Khóa ghép giúp tài liệu thể hiện đúng phạm vi và cho phép FK bảo vệ tenant.

Khi nhiều bảng dùng composite key, cần tài liệu rõ **thứ tự cột**, ý nghĩa từng phần và lý do. Không dùng FK chỉ theo customer_id nếu Customer được định danh bằng (tenant_id, customer_id).

### 2.3. Khóa định danh khác khóa hiển thị

Một số trường phù hợp hiển thị hoặc tìm kiếm nhưng không nên dùng làm PK:

- Tên khách, tên sản phẩm hoặc địa chỉ: có thể trùng và thay đổi.
- Email: chính sách case normalization, dùng chung, đổi hoặc xóa cần được quyết định.
- Số điện thoại: có thể đổi chủ và tái sử dụng.
- Giá trị thời gian created_at: nhiều bản ghi có thể cùng timestamp.
- Hash của nội dung: cùng nội dung không nhất thiết cùng thực thể; sửa nội dung sẽ đổi hash.

Nếu chọn surrogate key, vẫn cần bảo vệ **những business-key invariants thực sự tồn tại** bằng UNIQUE, registry hoặc kiểm tra phù hợp; surrogate PK không tự chống việc tạo hai Customer cho cùng một identity nghiệp vụ.

### 2.4. NULL và UNIQUE không nên bị mô tả mơ hồ

Trong PostgreSQL, một UNIQUE thông thường có thể cho phép nhiều hàng có giá trị NULL tại một cột tham gia khóa, theo quy tắc NULL mặc định. Vì vậy:

~~~text
UNIQUE(tenant_id, external_reference)
~~~

không đồng nghĩa “mọi Order bắt buộc có reference”, và cũng không tự giải quyết việc reference rỗng, có dấu cách hay được chuẩn hóa chữ hoa/chữ thường.

Tài liệu phải nói rõ:

1. Thuộc tính có được NULL không? NULL nghĩa là **chưa biết**, **không áp dụng**, hay **chưa cấp mã**?
2. Định danh có cần duy nhất khi thuộc tính NULL?
3. Khi chuẩn hóa văn bản, thế nào là hai mã tương đương?
4. Mã có được đổi, chuyển tenant hoặc tái sử dụng sau xóa mềm không?
5. Hai hệ nguồn có thể cấp mã trùng nhau không? Có cần source_system trong khóa?

**Không dùng NULL như một giải pháp mặc định cho mọi trường hợp chưa được phân tích.**

## 3. Định nghĩa quan hệ bằng câu nghiệp vụ và vai trò

Một đường nối không chỉ có tên “FK_Customer”. Hãy viết câu từ **hai phía**.

Ví dụ:

- “Mỗi Order được đặt bởi **đúng một Customer đã đăng ký**.”
- “Một Customer có thể đặt **không hoặc nhiều Order**.”
- “Mỗi OrderLine thuộc **đúng một Order**.”
- “Một Order DRAFT có thể có **0 hoặc nhiều OrderLine**.”
- “Một Order CONFIRMED bắt buộc có **ít nhất một OrderLine**.”
- “Mỗi OrderLine tham chiếu **đúng một Product trong cùng tenant**.”
- “Một Product có thể xuất hiện ở **không hoặc nhiều OrderLine**.”

Những câu trên đã chứa **bội số**, **tính tùy chọn** và **phạm vi** để thiết kế khóa. Tuy nhiên, còn thiếu hành vi khi xóa Customer, Product, Order hoặc khi chuyển trạng thái Order.

### 3.1. Đọc bội số theo ký pháp min..max

Viết ở mỗi đầu quan hệ:

| Ký hiệu | Nghĩa |
| --- | --- |
| **0..1** | Có thể không có, nhiều nhất một |
| **1..1** | Bắt buộc đúng một |
| **0..N** | Có thể không có hoặc có nhiều |
| **1..N** | Có ít nhất một, không giới hạn trên bởi mô hình logic |
| **m..n** | Ít nhất m, nhiều nhất n; cần ràng buộc nghiệp vụ riêng |

Ví dụ **Customer — Order**:

~~~text
Từ góc nhìn một Order:
  số Customer được tham chiếu = 1..1

Từ góc nhìn một Customer:
  số Order do Customer đặt = 0..N
~~~

Với **Order — OrderLine**, bội số phụ thuộc trạng thái:

~~~text
Line -> Order:                1..1 ở mọi trạng thái hợp lệ
Order DRAFT -> Line:          0..N
Order CONFIRMED -> Line:      1..N
~~~

Việc thay đổi bội số **theo trạng thái** không thể được diễn tả trọn vẹn bằng một đường ERD tĩnh. Cần chú thích văn bản và quy tắc chuyển trạng thái.

### 3.2. Mối quan hệ và cột FK không phải cùng khái niệm

Quan hệ “Order thuộc Customer” có thể được hiện thực bằng customer_id trong Orders. Tuy nhiên:

- Một FK có thể trỏ tới **surrogate key**, không phải business code.
- Quan hệ có thể có **thuộc tính riêng** như effective_from, role, allocation_weight.
- Một quan hệ có thể được lưu bằng **bảng liên kết**, document nesting hoặc cạnh graph.
- Một FK chỉ kiểm tra sự tồn tại tham chiếu theo khả năng DBMS; nó không diễn giải tất cả ý nghĩa vòng đời.

Hãy tài liệu hóa **predicate nghiệp vụ** trước, sau đó mới ghi cơ chế lưu.

## 4. Tài liệu bội số ở cả hai phía và điều kiện tham gia

Một bảng quan hệ minh họa cho nghiệp vụ Order:

| Quan hệ | Từ A nhìn B | Từ B nhìn A | Điều kiện đặc biệt |
| --- | --- | --- | --- |
| Customer đặt Order | Customer → Order: 0..N | Order → Customer: 1..1 | Order được tạo cho Customer đã đăng ký |
| Order chứa Line | Order → Line: 0..N khi DRAFT | Line → Order: 1..1 | Order CONFIRMED: 1..N |
| Product xuất hiện ở Line | Product → Line: 0..N | Line → Product: 1..1 | Product có thể inactive nhưng Line lịch sử vẫn hợp lệ |
| Order có PaymentAttempt | Order → PaymentAttempt: 0..N | Attempt → Order: 1..1 | Nhiều lần thử; trạng thái thanh toán riêng |
| Order gắn Label | Order → Label: 0..N | Label → Order: 0..N | Cần bảng quan hệ trung gian |

**Tính bắt buộc của quan hệ** có thể mang hai nghĩa:

- **Tồn tại ngay tại thời điểm tạo:** Order được tạo phải có Customer.
- **Tồn tại khi đạt trạng thái:** Order DRAFT có thể chưa có Line, nhưng không được xác nhận nếu thiếu Line.

Không được gộp hai nghĩa rồi áp NOT NULL/FK không phù hợp. Một constraint tĩnh có thể bảo vệ Line thuộc Order, nhưng “Order CONFIRMED phải có Line” cần kiểm soát xuyên hàng và đường ghi.

### 4.1. ERD minh họa và giới hạn diễn đạt

~~~mermaid
erDiagram
    TENANT ||--o{ CUSTOMER : owns
    TENANT ||--o{ PRODUCT : owns
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--o{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : appears_in
    SALES_ORDER ||--o{ PAYMENT_ATTEMPT : has
    SALES_ORDER ||--o{ ORDER_LABEL_LINK : tags
    ORDER_LABEL ||--o{ ORDER_LABEL_LINK : assigned
~~~

Sơ đồ thể hiện bội số **cấu trúc**. Nó không đủ diễn tả:

- Điều kiện “CONFIRMED phải có Line”.
- Mã/order_id chỉ duy nhất trong tenant.
- Quy tắc không xóa Customer đã có Order.
- Product inactive nhưng các OrderLine quá khứ vẫn giữ FK.
- Trạng thái PaymentAttempt và việc cho phép retry.
- Trường hợp một tenant không được đọc dữ liệu tenant khác.

Những điều đó phải hiện diện ở **tài liệu từ điển và danh mục bất biến** đi kèm.

## 5. Quan hệ 1–1, 1–N, N–M và quan hệ định danh

### 5.1. Quan hệ 1–1

Một User có thể có tối đa một Profile riêng biệt, và mỗi Profile chỉ thuộc một User. Nếu Profile có thể chưa được tạo, từ User nhìn Profile là **0..1**, còn Profile nhìn User là **1..1**.

Có thể triển khai bằng một FK UNIQUE NOT NULL ở Profile:

~~~sql
CREATE TABLE app_users (
    user_id BIGINT PRIMARY KEY
);

CREATE TABLE user_profiles (
    profile_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE
        REFERENCES app_users(user_id)
);
~~~

UNIQUE(user_id) bảo vệ **một User không có hai Profile**, nhưng không bắt mọi User phải có Profile. Nếu thực sự bắt buộc Profile luôn tồn tại đồng thời với User, phải quy định tạo atomically trong cùng transaction hoặc cân nhắc gộp hai đối tượng; FK một hướng không tự bảo vệ total participation ở cả hai phía.

### 5.2. Quan hệ 1–N

Order có nhiều Line, nhưng Line thuộc đúng một Order. FK nằm ở phía **N** (OrderLine). Nếu Line có khóa (order_id,line_no), nó là một thực thể **phụ thuộc định danh**: line_no chỉ có nghĩa trong Order.

Lưu ý **nhận diện yếu (weak entity/identifying relationship)** khác “xóa con theo cha”. Dù khóa của Line phụ thuộc Order, chính sách xóa Order có thể là RESTRICT để bảo vệ lịch sử; không tự áp CASCADE chỉ vì Line là thực thể yếu.

### 5.3. Quan hệ N–M

Order có nhiều Label; một Label được gắn với nhiều Order. Không lưu chuỗi “vip,urgent,fragile” trong một cột rồi kỳ vọng FK, uniqueness và thời gian gắn nhãn được bảo vệ.

Thông thường tạo **association table**:

~~~text
OrderLabelLink(
  tenant_id,
  order_id,
  label_id,
  applied_at,
  applied_by
)
~~~

Grain của mỗi hàng có thể là **một nhãn hiện được gắn với một Order**. Nếu cần lịch sử nhiều lượt gắn/tháo cùng nhãn, grain phải chuyển thành **một event hoặc một khoảng hiệu lực**, với khóa bổ sung.

### 5.4. Quan hệ tự tham chiếu

Một Employee có Manager là Employee khác, hoặc Category có ParentCategory. Ví dụ:

~~~sql
CREATE TABLE categories (
    tenant_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    parent_category_id BIGINT,
    category_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, category_id),
    FOREIGN KEY (tenant_id, parent_category_id)
        REFERENCES categories(tenant_id, category_id),
    CHECK (
        parent_category_id IS NULL
        OR parent_category_id <> category_id
    )
);
~~~

Ý nghĩa:

- Một Category có **0..1 parent trực tiếp**.
- Một Category có **0..N child trực tiếp**.
- Không được làm parent của chính nó trong một bước.

**CHECK parent_id <> category_id không cấm chu trình dài** A → B → C → A. Nếu nghiệp vụ yêu cầu cây không chu trình, cần kiểm tra toàn đường tổ tiên trong một cơ chế ghi có concurrency control phù hợp. Nếu cho phép nhiều parent, mô hình phải đổi thành bảng liên kết CategoryEdge và có thêm quy tắc graph.

### 5.5. Mối quan hệ có vai trò riêng

Một Order có thể có **người mua**, **người nhận hàng** và **người phê duyệt**. Cả ba có thể trỏ tới cùng kiểu thực thể Person/Customer nhưng quan hệ **khác vai trò**:

~~~text
Order --placed_by--> Customer
Order --ship_to_contact--> Contact
Order --approved_by--> Employee
~~~

Không dùng một cột person_id chung để diễn giải ba quan hệ khác nhau. Tài liệu phải nêu vai trò, bội số và thời điểm được phép NULL cho từng quan hệ.

## 6. DDL PostgreSQL: mô hình bán hàng có khóa và quan hệ rõ ràng

Ví dụ sau là **một mô hình logic cụ thể** để kiểm chứng các phát biểu trên; không phải đơn thuốc dùng nguyên văn cho mọi hệ thống. Giả định:

1. **Mọi Order trong bài do Customer đã đăng ký đặt**; nếu nghiệp vụ có guest checkout, phải mô hình hóa riêng thay vì tùy tiện bỏ NOT NULL.
2. **tenant_id** là phạm vi định danh. Các khóa số con có thể trùng giữa tenant khác nhau.
3. **Product** có thể được ngừng bán (is_active = FALSE) nhưng không bị xóa cứng nếu đã xuất hiện trong Line lịch sử.
4. Dòng hàng lưu **unit_price_vnd tại lúc lập Order**; không tính doanh thu lịch sử bằng giá hiện hành của Product.
5. PaymentAttempt là **một lần thử thanh toán** có định danh và vòng đời riêng, không đồng nghĩa Order đã được thanh toán.
6. Cột trạng thái hỗ trợ DRAFT, CONFIRMED, CANCELLED; quy tắc chuyển trạng thái được mô tả riêng ở phần vòng đời.

### 6.1. Tenant, Customer và Product

~~~sql
-- PostgreSQL, chạy trên database thử nghiệm riêng.
CREATE TABLE tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_code TEXT NOT NULL UNIQUE
);

CREATE TABLE customers (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    customer_id BIGINT NOT NULL,
    customer_code TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    archived_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, customer_code)
);

CREATE TABLE products (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    product_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (tenant_id, product_id),
    UNIQUE (tenant_id, sku)
);
~~~

**Giải thích tài liệu:**

- Một Customer thuộc **đúng một Tenant** và được định danh bởi (tenant_id,customer_id).
- Một Product thuộc **đúng một Tenant** theo quy ước minh họa; Product không tự dùng chung giữa tenant.
- archived_at là trạng thái ngừng sử dụng Customer, **không phải xóa hàng**; FK vẫn hợp lệ.
- Product.is_active = FALSE không làm các OrderLine cũ mất tham chiếu.

Nếu business cho phép SKU được tái sử dụng sau khi Product bị archive, UNIQUE(tenant_id,sku) cần thay đổi theo chính sách; không xóa constraint mà chưa đánh giá tác động tới các OrderLine lịch sử và đối soát.

### 6.2. Order và OrderLine

~~~sql
CREATE TABLE sales_orders (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    order_id BIGINT NOT NULL,
    order_code TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    UNIQUE (tenant_id, order_code),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id)
        ON DELETE RESTRICT,
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL),
    CHECK (status <> 'CANCELLED' OR cancelled_at IS NOT NULL)
);

CREATE TABLE order_lines (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL
        CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_orders(tenant_id, order_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products(tenant_id, product_id)
        ON DELETE RESTRICT
);
~~~

**Những điều DDL bảo vệ được:**

- Order thuộc một Customer tồn tại **trong cùng tenant**.
- Một Line chỉ thuộc một Order tồn tại **trong cùng tenant**.
- Line trỏ Product tồn tại trong cùng tenant.
- Một Order không có hai Line cùng line_no; line_no có thể lặp ở Order khác.
- quantity > 0, unit_price_vnd >= 0, status nằm trong miền hợp lệ.
- Không xóa cứng Customer hoặc Product khi FK RESTRICT còn được tham chiếu.
- Bản ghi Order CONFIRMED phải có confirmed_at; CANCELLED phải có cancelled_at.

**Những điều DDL chưa bảo vệ được:**

- Order CONFIRMED phải có ít nhất một Line.
- Chỉ cho phép DRAFT → CONFIRMED/CANCELLED và CONFIRMED → CANCELLED theo chính sách.
- Không cho sửa giá/dòng sau khi xác nhận.
- Không cho Customer đã archive đặt Order mới.
- Product.is_active = TRUE tại thời điểm thêm Line mới.
- Không cho trường cancelled_at xuất hiện vô nghĩa ở các trạng thái khác, nếu domain yêu cầu.
- Giá/quantity/currency có đúng chương trình bán hàng, thuế và tổng tiền hay không.

Đây là các quy tắc cần **write owner, procedure/transaction, trigger hoặc domain service** phối hợp với ràng buộc cục bộ. Tài liệu phải phân biệt cái gì **đã được DBMS cưỡng chế** và cái gì mới là **quy tắc mong muốn**.

### 6.3. PaymentAttempt và các Label

~~~sql
CREATE TABLE payment_attempts (
    tenant_id BIGINT NOT NULL,
    payment_attempt_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    provider_code TEXT NOT NULL,
    provider_attempt_ref TEXT NOT NULL,
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd > 0),
    status TEXT NOT NULL CHECK (
        status IN ('INITIATED','AUTHORIZED','CAPTURED','FAILED')
    ),
    captured_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, payment_attempt_id),
    UNIQUE (tenant_id, provider_code, provider_attempt_ref),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_orders(tenant_id, order_id)
        ON DELETE RESTRICT,
    CHECK (status <> 'CAPTURED' OR captured_at IS NOT NULL)
);

CREATE TABLE order_labels (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    label_id BIGINT NOT NULL,
    label_code TEXT NOT NULL,
    label_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, label_id),
    UNIQUE (tenant_id, label_code)
);

CREATE TABLE order_label_links (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    label_id BIGINT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, order_id, label_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_orders(tenant_id, order_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, label_id)
        REFERENCES order_labels(tenant_id, label_id)
        ON DELETE RESTRICT
);
~~~

PaymentAttempt là **thực thể nghiệp vụ cần lịch sử và đối soát**, nên không CASCADE khi xóa Order. Quan hệ OrderLabelLink ở ví dụ là **nhãn phụ trợ hiện hành, có thể tái tạo**, nên có thể dùng CASCADE **nếu** Order thực sự được phép xóa cứng. Trong mô hình này, Order thường không được xóa khi đã có Line/PaymentAttempt vì các FK RESTRICT; câu ON DELETE CASCADE ở nhãn không cấp quyền vượt các ràng buộc đó.

**Nếu nhãn là dấu vết kiểm toán, không dùng CASCADE:** phải đổi lifecycle của OrderLabelLink, lưu lịch sử gắn/tháo và chính sách xóa tương ứng. Hành vi ON DELETE không được chọn chỉ vì thao tác đó dễ viết SQL.

### 6.4. Dữ liệu mẫu kiểm chứng

~~~sql
INSERT INTO tenants(tenant_id, tenant_code)
VALUES (1, 'SHOP-A'), (2, 'SHOP-B');

INSERT INTO customers
    (tenant_id, customer_id, customer_code, customer_name)
VALUES
    (1, 11, 'C-11', 'Khách hàng A'),
    (2, 11, 'C-11', 'Khách hàng B');

INSERT INTO products
    (tenant_id, product_id, sku, product_name)
VALUES
    (1, 101, 'SKU-101', 'Tai nghe'),
    (2, 101, 'SKU-101', 'Bàn phím');

INSERT INTO sales_orders
    (tenant_id, order_id, order_code, customer_id, status)
VALUES
    (1, 1001, 'O-1001', 11, 'DRAFT');

INSERT INTO order_lines
    (tenant_id, order_id, line_no, product_id, quantity, unit_price_vnd)
VALUES (1, 1001, 1, 101, 2, 150000);

INSERT INTO order_labels
    (tenant_id, label_id, label_code, label_name)
VALUES (1, 5, 'PRIORITY', 'Ưu tiên');

INSERT INTO order_label_links(tenant_id, order_id, label_id)
VALUES (1, 1001, 5);
~~~

Hai tenant có thể có cùng customer_id, product_id và SKU vì **được định danh trong tenant**. Bản ghi Order của tenant 1 không thể tham chiếu Customer chỉ tồn tại ở tenant 2 bằng FK ghép.

**Chú ý:** chỉ nhập một Customer thuộc tenant 2 chưa đủ để thử lỗi cross-tenant khi Customer ID trùng ở cả hai tenant; phải chọn ID mà tenant đích không có, hoặc so sánh trước quan hệ nghiệp vụ. Ví dụ kiểm thử FK được trình bày ở phần sau.

## 7. Cách đọc ON DELETE và ON UPDATE như quy tắc vòng đời

Cú pháp FOREIGN KEY có thể chứa hành vi khi bản ghi cha thay đổi. Nó phải phản ánh **nghĩa nghiệp vụ**, không được chọn mặc định vì ít phát sinh lỗi.

| Hành vi | Ý nghĩa tổng quát | Khi nào phù hợp | Cảnh báo |
| --- | --- | --- | --- |
| **RESTRICT** | Chặn xóa/sửa khóa cha khi còn con tham chiếu | Customer/Product có Order lịch sử | Phải có quy trình archive thay DELETE |
| **NO ACTION** | Nếu ràng buộc còn vi phạm ở thời điểm kiểm tra thì từ chối | Giữ toàn vẹn tham chiếu, có thể xét deferrable | Không đồng nhất hoàn toàn với RESTRICT trong mọi tình huống deferral |
| **CASCADE** | Xóa/sửa khóa con theo hành động trên cha | Dữ liệu phụ có vòng đời hoàn toàn phụ thuộc | Có thể xóa hàng loạt dữ liệu cần audit |
| **SET NULL** | Gỡ liên kết bằng NULL khi cha bị xóa | Quan hệ tùy chọn và NULL mang nghĩa hợp lệ | Cột FK phải cho phép NULL; không làm mất nghĩa nguồn |
| **SET DEFAULT** | Thay giá trị FK bằng default | Chỉ khi default trỏ tới thực thể hợp lệ và được phê duyệt | “Unknown” giả có thể che sai nghiệp vụ |

Trong PostgreSQL, NO ACTION là hành vi mặc định của FK; ở một số tình huống có thể kiểm tra deferred nếu constraint DEFERRABLE và cơ chế phù hợp, còn RESTRICT không được hiểu là một lựa chọn giống hệt cho mọi thời điểm kiểm tra.

### 7.1. Vì sao không CASCADE Customer → Order?

Nếu Customer bị xóa và toàn bộ Orders/PaymentAttempts bị xóa theo, doanh thu đã phát sinh có thể mất dấu vết đối soát. Tài liệu nên nói:

> “Customer đã từng đặt Order phải được chuyển ARCHIVED/ANONYMIZED theo chính sách; không xóa cứng nếu còn Order/PaymentAttempt cần lưu trữ. Các Order lịch sử vẫn giữ customer_id hoặc chuyển sang định danh pseudonym/retention model đã được duyệt.”

Cần phân biệt **ẩn dữ liệu cá nhân** với **xóa toàn bộ giao dịch**. Việc lưu hoặc xóa phụ thuộc luật và chính sách thực tế; tài liệu mô hình phải nêu owner/quy trình nhưng không tự suy ra quyền giữ dữ liệu vô thời hạn.

### 7.2. Khi nào CASCADE hợp lệ?

Một bản ghi **giỏ hàng nháp** và các CartLine chỉ có ý nghĩa trong vòng đời của Cart. Nếu đã thống nhất “xóa Cart nháp thì xóa cả CartLine” và CartLine không chứa dữ liệu cần lưu trữ riêng, ON DELETE CASCADE có thể phù hợp. Nhưng sau khi giỏ chuyển thành Order và có giao dịch, các Line đã trở thành lịch sử bán hàng, **không tự thừa hưởng** chính sách xóa Cart.

### 7.3. Khóa cha có được sửa hay không?

Nếu surrogate customer_id hoặc order_id được thiết kế **bất biến**, nên hạn chế UPDATE PK; không tự dựa vào ON UPDATE CASCADE để cho phép tùy ý đổi danh tính.

Đổi **mã hiển thị** customer_code có thể là một thao tác được cho phép, trong khi id không đổi. Nếu mã nghiệp vụ bị dùng làm FK, mọi đổi mã có thể kéo theo nhiều cập nhật và ảnh hưởng history; cân nhắc surrogate key với UNIQUE business code.

### 7.4. Soft delete không kích hoạt ON DELETE

~~~sql
UPDATE customers
SET archived_at = CURRENT_TIMESTAMP
WHERE tenant_id = 1 AND customer_id = 11;
~~~

Đây là **UPDATE trạng thái**, không phải DELETE nên FK ON DELETE không tự xử lý các Order liên quan. Nếu nghiệp vụ nói “không đặt Order mới cho Customer archived”, write owner phải kiểm tra archived_at trong cùng ranh giới nhất quán.

Tương tự, UNIQUE vẫn tính Customer archived theo constraint hiện tại. Nếu muốn tái sử dụng customer_code sau khi archive, cần định nghĩa uniqueness mới có xét trạng thái; nhưng phải đánh giá liệu các tham chiếu và báo cáo lịch sử có còn phân biệt được danh tính hay không.

## 8. Vòng đời không chỉ là xóa: tạo, chuyển trạng thái, lưu lịch sử

Tài liệu mô hình nên mô tả tối thiểu các giai đoạn:

~~~text
Tạo -> Gắn liên kết -> Cập nhật -> Khóa thay đổi
    -> Xác nhận/đóng -> Lưu trữ/ẩn -> Xóa theo chính sách
~~~

**Mỗi thực thể có thể có vòng đời riêng.** Product không còn bán vẫn tồn tại với OrderLine; PaymentAttempt có lịch sử độc lập; Label có thể được gỡ khỏi Order mà không xóa Order.

### 8.1. Máy trạng thái của Order

Ví dụ một quy trình:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> CONFIRMED : confirm
    DRAFT --> CANCELLED : cancel
    CONFIRMED --> CANCELLED : approved_cancel
    CONFIRMED --> [*] : archived_view
    CANCELLED --> [*] : archived_view
~~~

Trong sơ đồ, archived_view là cách trình bày “ngừng sử dụng tích cực”; **không nhất thiết là xóa vật lý**. Một Order có thể được xem là kết thúc nghiệp vụ và vẫn được lưu theo chính sách kế toán.

Cần ghi rõ:

- **Điều kiện DRAFT → CONFIRMED:** ít nhất một Line hợp lệ; Customer không bị archive; chính sách stock/payment được thỏa.
- **Điều kiện CONFIRMED → CANCELLED:** có quyền hủy, quy tắc hoàn/đảo giữ hàng, chứng từ và lưu lịch sử.
- **Điều gì không được sửa sau CONFIRMED:** quantity/price/danh tính Line hay chỉ một số trường? Quy định bởi domain.
- **Ai được phép chuyển:** API, batch, tác vụ thủ công; mọi writer phải qua cùng owner/transaction.
- **Idempotency:** confirm/cancel bị gửi lại phải không tạo side-effect trùng.

**CHECK(status IN (...)) chỉ kiểm tra tập giá trị**, không kiểm soát đường chuyển DRAFT → CONFIRMED hay chống hủy hai lần. Việc chống transition sai là ràng buộc theo **trạng thái trước/sau**, cần cơ chế ghi tương ứng.

### 8.2. Cùng thực thể, nhiều vòng đời con

PaymentAttempt có thể có chuỗi trạng thái riêng:

~~~text
INITIATED -> AUTHORIZED -> CAPTURED
          -> FAILED
~~~

Ví dụ trên là một mô hình giản lược; một provider có thể có VOIDED, EXPIRED, REFUNDED hoặc capture nhiều phần. Không tự suy ra PaymentAttempt CAPTURED đồng nghĩa Order đã được giao hoặc hoàn tiền sẽ sửa cùng một hàng. Refund có thể là **sự kiện tài chính mới** cần ledger/refund fact riêng.

Tài liệu phải phân biệt **quan hệ tồn tại** (Attempt thuộc Order) với **điều kiện chuyển trạng thái** (Order được phép CONFIRMED dựa trên điều gì).

## 9. Bất biến xuyên hàng không thể viết bằng CHECK đơn giản

Trong lược đồ minh họa, một Order CONFIRMED bắt buộc có ít nhất một Line. SQL phát hiện trạng thái vi phạm:

~~~sql
SELECT o.tenant_id, o.order_id
FROM sales_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
~~~

**Đây là truy vấn đối soát, không tự ngăn lỗi.** CHECK cục bộ trên sales_orders không thể đơn giản SELECT từ order_lines rồi đảm bảo tính đúng khi writer khác xóa Line đồng thời.

### 9.1. Giao thức xác nhận Order trong một database

Một lệnh ConfirmOrder có thể làm theo các bước trong **cùng transaction**:

~~~sql
BEGIN;

-- 1. Khóa Order để đồng bộ mọi lệnh sửa Line và chuyển trạng thái.
SELECT status, customer_id
FROM sales_orders
WHERE tenant_id = 1 AND order_id = 1001
FOR UPDATE;

-- 2. Kiểm tra business preconditions:
SELECT EXISTS (
    SELECT 1
    FROM order_lines
    WHERE tenant_id = 1 AND order_id = 1001
) AS has_line;

-- 3. CHỈ KHI status = DRAFT và has_line = true
--    cùng điều kiện nghiệp vụ khác được xác nhận:
UPDATE sales_orders
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE tenant_id = 1
  AND order_id = 1001
  AND status = 'DRAFT'
RETURNING order_id, status;

-- 4. Nếu số hàng/điều kiện không đúng: ROLLBACK.
--    Nếu mọi điều kiện đạt: COMMIT.
COMMIT;
~~~

**Không chạy từ đầu đến COMMIT mà bỏ qua nhánh điều kiện trong chú thích.** Ứng dụng/procedure phải kiểm tra kết quả trước khi commit.

Quan trọng hơn, mọi API **xóa hoặc sửa Line** cũng phải khóa **Order cha trước** và kiểm tra trạng thái. Nếu ConfirmOrder khóa cha nhưng DeleteLine không dùng cùng quy ước, DeleteLine vẫn có thể phá bất biến sau khi Order đã CONFIRMED.

Tài liệu triển khai nên ghi:

> “Mọi thay đổi order_lines và mọi transition sales_orders phải đi qua Order Owner. Owner lấy khóa Order theo tenant_id + order_id, kiểm tra trạng thái và cùng transaction ghi thay đổi. Không có writer được bypass.”

### 9.2. Nếu Order và Line nằm trên hai shard độc lập?

Một transaction PostgreSQL cục bộ không tự trở thành transaction xuyên hai database. Việc gọi GET /order-lines từ service khác rồi UPDATE status ở Order DB không bảo đảm tập Line không đổi giữa lúc kiểm tra và COMMIT.

Phương án:

- Colocate Order và Line theo cùng shard key/owner.
- Dùng cơ chế transaction phân tán thực sự nếu nền tảng hỗ trợ và phù hợp.
- Thiết kế workflow có trạng thái/ownership mà chỉ công bố CONFIRMED sau khi đã có bằng chứng đủ mạnh.
- Thay bất biến nếu nghiệp vụ cho phép, sau khi được phê duyệt.

Không được chỉ viết “eventual consistency” trong tài liệu rồi coi invariant cứng đã được bảo vệ.

## 10. Thuộc tính và quy tắc của quan hệ cũng có vòng đời

Quan hệ N–M có thể chứa metadata:

~~~text
OrderLabelLink:
  label_id, applied_at, applied_by, source_system
~~~

Nếu chỉ lưu **liên kết hiện tại**, khóa chính (tenant_id,order_id,label_id) bảo vệ tối đa một liên kết hiện hành cho mỗi cặp.

Nếu nghiệp vụ cần biết **bao giờ nhãn được gắn/tháo**, một bảng lịch sử có grain khác:

~~~text
OrderLabelHistory:
  tenant_id
  order_id
  label_id
  valid_from
  valid_to
  reason
  event_id
~~~

Bội số giờ thay đổi theo thời điểm: một Order có thể từng gắn cùng Label nhiều lần ở **những khoảng không chồng lấp**, nhưng tại một instant chỉ có tối đa một liên kết active nếu đó là quy tắc.

### 10.1. Mô hình quan hệ có hiệu lực theo thời gian

~~~sql
CREATE TABLE order_label_history (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    label_id BIGINT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    reason TEXT,
    PRIMARY KEY (tenant_id, order_id, label_id, valid_from),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_orders(tenant_id, order_id),
    FOREIGN KEY (tenant_id, label_id)
        REFERENCES order_labels(tenant_id, label_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

Một CHECK chỉ cấm khoảng ngược; nó **không tự cấm hai khoảng chồng lấp** đối với cùng (tenant_id,order_id,label_id). Nếu quy tắc “tối đa một LabelLink active tại một instant” là invariant, cần exclusion constraint, procedure/transaction hoặc giải pháp theo DBMS.

Sử dụng khoảng **[valid_from,valid_to)**: bắt đầu bao gồm, kết thúc loại trừ. Hai khoảng chạm nhau ở ranh giới có thể hợp lệ mà không chồng lấp.

### 10.2. Khi thay đổi Product không được viết lại lịch sử OrderLine

Nếu Product đổi tên hoặc giá niêm yết, OrderLine đã xác nhận cần giữ **giá giao dịch** và thường cả các thuộc tính quan trọng để lập chứng từ tại thời điểm bán. Một FK sang Product chỉ bảo vệ danh tính sản phẩm, không đảm bảo product_name hiện hành đúng tên tại thời điểm bán.

Tùy bài toán:

- Lưu **unit_price_vnd**, discount/tax và định danh Product tại từng Line.
- Lưu thêm snapshot tên sản phẩm, SKU, đơn vị tính khi chứng từ cần bất biến.
- Dùng SCD Type 2 và khóa phiên bản Product để truy xuất phân loại lịch sử.
- Tách cách xem **as-sold** và **as-current**; không trộn hai chế độ rồi ghi chung vào một KPI.

Tài liệu hóa quan hệ phải nói **Product nào** được tham chiếu: thực thể logic qua thời gian hay một **version cụ thể** tại giao dịch.

## 11. Ranh giới tenant, service và quyền sở hữu quan hệ

Cùng một mô hình có thể triển khai:

- Trong một database: FK ghép được DBMS cưỡng chế.
- Trong nhiều schema của cùng DBMS: có thể có FK/transaction tùy cách triển khai.
- Trong hai database/shard độc lập: không tự có FK/transaction toàn cục.
- Trong hai microservice chỉ giao tiếp API/event: mỗi service có thể sở hữu dữ liệu khác nhau; cần hợp đồng và xử lý thất bại.

**Phạm vi định danh** phải được tài liệu hóa độc lập với topology. Nếu Customer chỉ duy nhất theo tenant nhưng Order được route theo customer_id không có tenant, có thể đặt sai owner hoặc kiểm tra sai tham chiếu.

### 11.1. Mẫu hợp đồng owner cho quan hệ

~~~text
Relationship:
  SalesOrder PLACED_BY Customer

Identity:
  Order: (tenant_id, order_id)
  Customer: (tenant_id, customer_id)

Cardinality:
  Order -> Customer: 1..1
  Customer -> Order: 0..N

Write owner:
  Order Service / Order aggregate

Reference scope:
  Same tenant only

Creation:
  Order requires existing active Customer

Update:
  Customer reference immutable after CONFIRMED

Delete/archive:
  Customer archive does not delete Order
  Hard delete blocked while retention requires Order

Enforcement:
  Composite FK in one relational database
  Owner check for Customer active status
  Cross-service consistency: explicitly unresolved if split databases

Verification:
  FK orphan test, tenant mismatch test,
  concurrent archive/create scenario
~~~

Một hợp đồng như vậy cho phép reviewer nhận ra ngay **những quy tắc không thể suy từ FK** và những giới hạn khi sau này tách service.

### 11.2. Quan hệ xuyên service cần chỉ rõ mức bảo đảm

Nếu Order Service lưu customer_id nhưng Customer Service sở hữu Customers ở DB khác, tài liệu phải nêu:

- Tham chiếu được xác nhận **đồng bộ tại lệnh tạo** hay đối soát bất đồng bộ?
- Khi Customer bị khóa/xóa, Order lịch sử còn được giữ?
- Có yêu cầu snapshot thông tin Customer tại Order không?
- Nếu gọi Customer API timeout, Order được tạo PENDING, bị từ chối, hay vẫn ghi provisional?
- Mã Customer có được tái sử dụng hoặc đổi tenant không?
- Ai sửa orphan references khi sự kiện đến muộn?

Không ghi đơn giản “FK to Customers” nếu DBMS không thực sự cưỡng chế được. Hãy gọi đúng là **logical reference** và mô tả giao thức bảo vệ.

## 12. Data dictionary: tài liệu thực thể và từng thuộc tính

ERD trả lời thực thể nối nhau thế nào; **data dictionary** ghi một thuộc tính có ý nghĩa gì, nguồn nào cung cấp và được phép đổi khi nào.

Ví dụ từ điển cho SalesOrder:

| Trường | Kiểu logic / vật lý | Ý nghĩa | NULL | Nguồn/quy tắc |
| --- | --- | --- | --- | --- |
| tenant_id | ID / BIGINT | Tổ chức sở hữu đơn | Không | Một phần PK và mọi FK cùng tenant |
| order_id | ID / BIGINT | Định danh kỹ thuật Order trong tenant | Không | PK(tenant_id,order_id), không đổi |
| order_code | Code / TEXT | Mã hiển thị với khách | Không | UNIQUE(tenant_id,order_code), được cấp theo chính sách |
| customer_id | ID / BIGINT | Customer đặt đơn | Không trong case này | FK(tenant_id,customer_id); guest checkout cần mô hình khác |
| status | Enum / TEXT | Trạng thái vòng đời Order | Không | DRAFT, CONFIRMED, CANCELLED |
| created_at | Instant / TIMESTAMPTZ | Thời điểm tạo bản ghi nghiệp vụ | Không | Không dùng thay order_id |
| confirmed_at | Instant / TIMESTAMPTZ | Mốc xác nhận khi hợp lệ | Có | Bắt buộc khi status CONFIRMED |
| cancelled_at | Instant / TIMESTAMPTZ | Mốc hủy theo nghiệp vụ | Có | Bắt buộc khi status CANCELLED |

Từ điển trên nên được bổ sung **owner, sensitivity, retention, source version, ví dụ, giới hạn** khi áp dụng thật. Ví dụ thông tin liên hệ và địa chỉ giao hàng có thể là dữ liệu cá nhân cần chính sách truy cập, thời hạn lưu và phương thức ẩn danh.

### 12.1. Phân biệt kiểu dữ liệu và miền giá trị

Kiểu BIGINT chỉ nói về biểu diễn số nguyên trong phạm vi nhất định. Nó **không** nói:

- Đây là tiền, ID hay số lượng?
- Giá trị được phép âm không?
- Đơn vị là VND nguyên đồng, cent hay một số chỉ số quy đổi?
- Có thể tái sử dụng ID không?
- Được cấp bởi service nào?
- Có thể NULL ở trạng thái DRAFT nhưng bắt buộc ở CONFIRMED không?

Ví dụ unit_price_vnd BIGINT trong OrderLine:

~~~text
Attribute:
  unit_price_vnd

Meaning:
  Giá bán đơn vị đã chốt cho dòng hàng, tính bằng VND nguyên đồng.

Grain:
  Một OrderLine tại thời điểm lập đơn.

Constraints:
  NOT NULL, >= 0 trong phiên bản mô hình này.

Source:
  Pricing decision tại bước tạo/cập nhật Line trước CONFIRMED.

Lifecycle:
  Không thay đổi tại Line đã CONFIRMED;
  nếu nghiệp vụ có correction, cần event/chứng từ điều chỉnh.

Anti-rule:
  Không đọc giá hiện hành từ Products rồi thay đổi lịch sử Line.
~~~

Cách tài liệu hóa này giúp người đọc hiểu được **ngữ nghĩa** thay vì chỉ biết một cột là số.

### 12.2. Đặt tên quan hệ có vai trò diễn đạt

Nên chọn tên như:

- PLACED_BY: Order được đặt bởi Customer.
- CONTAINS: Order chứa OrderLine.
- REFERENCES_PRODUCT: Line chỉ tới Product.
- BELONGS_TO_TENANT: dữ liệu thuộc phạm vi tenant.
- ATTEMPTED_PAYMENT_FOR: một lần thử thanh toán cho Order.
- TAGGED_WITH: Order có một Label hiện hành.

Những tên như HAS, FK_ID hoặc LINK nếu không có chú giải thường không đủ khi cùng hai thực thể có nhiều quan hệ. Nếu Order có cả Customer mua hàng và Customer nhận quà, phải có **hai vai trò riêng**, mỗi vai trò có khóa/bội số và hành vi lịch sử riêng.

## 13. Relationship catalog: bảng hợp đồng cho từng đường nối

Một **relationship catalog** giúp review tất cả FK hoặc logical references mà không phải lần lượt đọc DDL.

| Quan hệ | Child → Parent | Parent → Child | Phạm vi | Thực thi hiện có | Vòng đời |
| --- | --- | --- | --- | --- | --- |
| Customer–Order | 1..1 | 0..N | cùng tenant | FK ghép, Customer NOT NULL | Không hard delete Customer còn Order |
| Order–Line | 1..1 | 0..N | cùng Order/tenant | FK ghép, PK line | CONFIRMED cần 1..N; Line bị khóa sửa |
| Product–Line | 1..1 | 0..N | cùng tenant | FK ghép | Inactive Product vẫn tồn tại vì lịch sử |
| Order–PaymentAttempt | 1..1 | 0..N | cùng tenant | FK ghép, unique provider attempt | Không xóa theo Order |
| Order–Label | 0..N | 0..N | cùng tenant | Bảng liên kết và PK ghép | Gỡ liên kết không xóa Label |
| Tenant–Customer | 1..1 | 0..N | tenant | FK + PK ghép | Chính sách xóa tenant cần quy trình toàn hệ |

**Điểm quan trọng:** Bảng mô tả bội số cấu trúc; trường hợp Order CONFIRMED có Line tối thiểu phải ghi **điều kiện thêm**, không sửa cột “0..N” thành “1..N” ở mọi thời điểm.

### 13.1. Mẫu tài liệu một quan hệ đầy đủ

~~~yaml
# Ví dụ biểu mẫu thiết kế minh họa; KHÔNG phải metadata bài học.
name: SALES_ORDER_CONTAINS_ORDER_LINE
predicate: "Một Order chứa các dòng hàng của chính đơn đó"
left_entity: SalesOrder
right_entity: OrderLine

identity:
  order: [tenant_id, order_id]
  line: [tenant_id, order_id, line_no]

cardinality:
  order_to_lines:
    draft: "0..N"
    confirmed: "1..N"
  line_to_order: "1..1"

scope:
  tenant: "phải cùng tenant_id"
  shard_owner: "Order aggregate owner"

creation:
  line_requires_existing_order: true
  line_no_unique_within_order: true

lifecycle:
  line_edit_after_confirm: "forbidden_by_domain"
  line_delete_after_confirm: "forbidden_by_domain"
  order_hard_delete: "restricted_while_business_history_retained"

enforcement:
  database: "PK, composite FK, quantity CHECK"
  application_transaction: "Order lock + confirm preconditions"
  not_enforced_by_fk: "confirmed order must contain >=1 line"

verification:
  - "query confirmed orders lacking lines"
  - "concurrent confirm/delete-last-line test"
  - "cross-tenant FK test"
~~~

Tập thông tin này nên được quản lý như **hợp đồng thiết kế có phiên bản**, không phải chỉ là YAML đẹp để xuất báo cáo. Nếu nội dung ghi “forbidden_by_domain” nhưng SQL cho writer bypass để xóa Line, tài liệu không khớp thực tế.

### 13.2. Quy tắc tài liệu hóa ngoại lệ

Nếu nghiệp vụ có trường hợp đặc biệt, ghi ngay trong hợp đồng:

~~~text
Trường hợp:
  Order IMPORTED_HISTORICAL có thể thiếu Customer.

Quyết định:
  Không gán customer_id giả vào Customer hiện hành.
  Dùng loại Order riêng và historical_customer_reference,
  hoặc mô hình Unknown Member đã được duyệt nếu báo cáo cần.

Tác động:
  Cardinality Order -> Customer của nhóm IMPORTED khác nhóm REGISTERED.
  Hợp đồng phải mô tả discriminator và phạm vi riêng.
~~~

Không cần thiết chọn chính xác phương án ở ví dụ nếu business chưa quyết định. Quan trọng là **đừng để một ngoại lệ thực biến thành một NULL không có ngữ nghĩa** hoặc khiến nhóm khác suy ra “mọi Order đều có Customer”.

## 14. Kiểm tra SQL: biến hợp đồng thành bằng chứng

Tài liệu mô hình có giá trị cao khi mỗi quy tắc quan trọng có **phép kiểm chứng**.

### 14.1. Tìm Order CONFIRMED nhưng thiếu Line

~~~sql
SELECT o.tenant_id, o.order_id
FROM sales_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
-- Kỳ vọng 0 hàng nếu bất biến được bảo vệ đúng.
~~~

Nếu kết quả không rỗng, truy vết owner nào đã cho chuyển trạng thái hoặc xóa Line cuối. Việc thêm index có thể tăng tốc kiểm tra nhưng **không sửa được đường ghi sai**.

### 14.2. Tìm Customer archived còn đang được sử dụng làm điểm tạo Order mới

~~~sql
SELECT o.tenant_id, o.order_id, o.created_at,
       c.archived_at
FROM sales_orders AS o
JOIN customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE c.archived_at IS NOT NULL
  AND o.created_at > c.archived_at;
~~~

**Cẩn trọng khi diễn giải:** một Order có created_at sau archived_at có thể là import lịch sử/backfill hoặc một lỗi thời gian hệ thống. Nếu quy tắc là “không được tạo Order sau khi Customer archive”, cần phân biệt **business event time** và thời điểm ingest. Truy vấn chẩn đoán không thay thế audit lệnh tạo và nguồn sự kiện.

### 14.3. Kiểm tra uniqueness theo business key

~~~sql
SELECT tenant_id, order_code, COUNT(*) AS duplicates
FROM sales_orders
GROUP BY tenant_id, order_code
HAVING COUNT(*) > 1;
-- Không nên có hàng vì UNIQUE(tenant_id, order_code).
~~~

Nếu áp UNIQUE bằng migration trên dữ liệu cũ, phải kiểm tra duplicate **trước khi thêm constraint** và tiếp tục giám sát writer cũ trong giai đoạn rollout.

### 14.4. Kiểm tra orphan nếu FK chỉ là logical reference

Trong một database có FK đã cưỡng chế, orphan theo khóa sẽ không xuất hiện khi toàn vẹn được duy trì. Nhưng nếu dữ liệu nhập từ hệ nguồn khác hoặc FK chỉ là **logic xuyên service**, có thể dùng:

~~~sql
SELECT o.tenant_id, o.order_id, o.customer_id
FROM sales_orders AS o
LEFT JOIN customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

Nếu dữ liệu nằm ở hai database độc lập, truy vấn trên chỉ là **minh họa logic đối soát** sau khi đã có hai tập dữ liệu cùng môi trường phân tích; nó không tự chạy xuyên mọi service.

### 14.5. Kiểm tra bội số 0..1 khi không có UNIQUE

Một quan hệ Profile → User mà nghiệp vụ yêu cầu một User tối đa một Profile, nếu thiếu UNIQUE(user_id) thì có thể tìm:

~~~sql
SELECT user_id, COUNT(*) AS profile_count
FROM user_profiles
GROUP BY user_id
HAVING COUNT(*) > 1;
~~~

Nếu database đã có UNIQUE(user_id), truy vấn sẽ rỗng khi constraint hoạt động đúng; giá trị của kiểm tra nằm ở chỗ **đối chiếu dữ liệu lịch sử và phát hiện mô hình chưa cưỡng chế invariant**.

### 14.6. Không dùng COUNT DISTINCT để che fan-out

Giả sử Order có 3 Line và 2 PaymentAttempt. JOIN trực tiếp theo Order tạo **3 × 2 = 6 hàng**; SUM(amount) hoặc COUNT(*) có thể bị nhân.

~~~sql
-- Sai nếu muốn tổng amount theo Order:
SELECT o.order_id, SUM(p.amount_vnd) AS paid_amount
FROM sales_orders AS o
JOIN order_lines AS l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
JOIN payment_attempts AS p
  ON p.tenant_id = o.tenant_id
 AND p.order_id = o.order_id
GROUP BY o.order_id;
~~~

Trong hệ nhiều tenant, GROUP BY chỉ theo order_id còn có thể **trộn các Order khác tenant có cùng order_id**. Đây là lỗi phạm vi khóa **ngoài** lỗi fan-out. Ngay cả khi bổ sung tenant_id vào GROUP BY, việc JOIN hai quan hệ con ở mức chi tiết vẫn có thể nhân số tiền.

Sửa bằng cách xác định **grain báo cáo** và tổng hợp từng tập con về một hàng/Order trước khi ghép:

~~~sql
WITH line_totals AS (
    SELECT tenant_id, order_id,
           SUM(quantity * unit_price_vnd) AS line_amount_vnd
    FROM order_lines
    GROUP BY tenant_id, order_id
),
captured_payments AS (
    SELECT tenant_id, order_id,
           SUM(amount_vnd) AS captured_amount_vnd
    FROM payment_attempts
    WHERE status = 'CAPTURED'
    GROUP BY tenant_id, order_id
)
SELECT o.tenant_id, o.order_id,
       COALESCE(l.line_amount_vnd, 0) AS line_amount_vnd,
       COALESCE(p.captured_amount_vnd, 0) AS captured_amount_vnd
FROM sales_orders AS o
LEFT JOIN line_totals AS l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
LEFT JOIN captured_payments AS p
  ON p.tenant_id = o.tenant_id
 AND p.order_id = o.order_id;
~~~

Đây là **báo cáo minh họa**: chưa xét thuế, giảm giá, hoàn tiền, capture trùng do provider, tiền tệ hoặc tính đúng của PaymentAttempt status. Nhưng nó cho thấy vì sao tài liệu bội số quan hệ còn phục vụ **thiết kế truy vấn đúng**, không chỉ DDL.

## 15. Kiểm thử âm: các thao tác đáng lẽ phải bị từ chối

Một kế hoạch kiểm thử quan hệ không chỉ chèn dữ liệu hợp lệ. Nó cần chứng minh **những điều không được phép**.

### 15.1. Vi phạm FK tenant–Order

Giả sử Order 1001 chỉ tồn tại trong tenant 1. Thử tạo Line cho tenant 2 với order_id 1001:

~~~sql
-- Kỳ vọng lỗi FK: tenant 2 chưa có Order 1001.
INSERT INTO order_lines
    (tenant_id, order_id, line_no, product_id, quantity, unit_price_vnd)
VALUES (2, 1001, 1, 101, 1, 150000);
~~~

Product 101 tồn tại ở tenant 2 trong dữ liệu mẫu, nhưng Order 1001 **không tồn tại ở tenant 2**. Chính FK ghép từ Line tới Order phải từ chối.

### 15.2. Vi phạm khóa định danh Line

~~~sql
-- Dòng line_no=1 trong Order 1001 đã tồn tại.
INSERT INTO order_lines
    (tenant_id, order_id, line_no, product_id, quantity, unit_price_vnd)
VALUES (1, 1001, 1, 101, 1, 150000);
-- Kỳ vọng lỗi PK.
~~~

Hai Order khác nhau có thể cùng line_no=1, nên chỉ UNIQUE(line_no) là sai phạm vi.

### 15.3. Vi phạm miền giá trị

~~~sql
-- Kỳ vọng lỗi CHECK:
INSERT INTO sales_orders
    (tenant_id, order_id, order_code, customer_id, status)
VALUES (1, 1002, 'O-1002', 11, 'DELIVERED');
~~~

Lỗi xuất hiện vì status DELIVERED không thuộc miền trạng thái của **mô hình mẫu**, không có nghĩa mọi nghiệp vụ bán hàng trên thế giới đều không cần trạng thái DELIVERED. Nếu domain cần nó, phải thay máy trạng thái và cả tài liệu, không chỉ nới CHECK tùy tiện.

### 15.4. Hành vi xóa Customer được tham chiếu

~~~sql
-- Kỳ vọng lỗi FK RESTRICT do Order 1001 còn tham chiếu.
DELETE FROM customers
WHERE tenant_id = 1 AND customer_id = 11;
~~~

Nếu muốn archive Customer, dùng UPDATE archived_at theo policy, và xác nhận không còn writer tạo Order mới cho Customer đã archive. Không dùng ON DELETE CASCADE để “cho DELETE chạy được” mà không xem xét lịch sử Order.

### 15.5. Kiểm thử concurrency cho bất biến liên bảng

Một kịch bản cần chạy bằng **hai session độc lập** trong môi trường thử:

~~~text
Session A:
  Khóa Order 1001, kiểm tra có Line, chờ trước confirm.

Session B:
  Muốn xóa Line cuối hoặc sửa Line khi Order còn DRAFT.

Kỳ vọng:
  Cả hai đi qua cùng Order Owner và cùng quy ước khóa;
  không có lịch commit nào tạo Order CONFIRMED mà không có Line.
~~~

Không chỉ chạy hai transaction tuần tự rồi gọi là test concurrency. Cần thử giao cắt theo thời điểm, isolation level, deadlock/retry và mọi lệnh sửa Line có thể phá invariant. Khi khóa theo cùng quy ước, một bên phải chờ hoặc bị từ chối theo trạng thái sau khi bên kia commit.

## 16. Vòng đời của lịch sử, xóa mềm và dữ liệu cá nhân

Trong mô hình quan hệ, **DELETE vật lý** và **kết thúc vòng đời nghiệp vụ** là hai việc khác nhau.

Ví dụ Customer có thể:

~~~text
ACTIVE -> ARCHIVED -> ANONYMIZED
~~~

trong khi Order vẫn tồn tại vì cần truy vết giao dịch. Tài liệu phải nêu:

1. Khi archive, Customer có còn được dùng để đặt Order mới không?
2. Các Order cũ còn hiển thị tên Customer không?
3. Có cần thay thế PII bằng pseudonym/token hay xóa thuộc tính cụ thể không?
4. Những thông tin nào còn lưu theo nghĩa vụ pháp lý hoặc vận hành?
5. Khi Customer được xóa cứng, những FK nào còn tham chiếu và điều kiện nào cho phép chuyển/giải phóng?
6. Dữ liệu dẫn xuất trong analytics/search/cache có lịch cập nhật hoặc xóa theo policy như thế nào?
7. Ai phê duyệt và ghi nhận thao tác xóa/ẩn danh?

Không nên tự khẳng định phải giữ dữ liệu mãi mãi hoặc phải xóa toàn bộ ngay lập tức. Đó là **quyết định policy, pháp lý và nghiệp vụ** cần sự tham gia của người phụ trách.

### 16.1. Khi phải giữ lịch sử giao dịch nhưng xóa PII

Một thiết kế có thể tách **CustomerIdentity** chứa thông tin cá nhân khỏi **CustomerReference/OrderSnapshot** cần thiết cho giao dịch. Sau khi thực hiện policy ẩn danh, Order có thể giữ một **định danh không trực tiếp tiết lộ danh tính** và những trường hợp lý còn cần cho đối soát.

Nhưng cần đánh giá nguy cơ tái nhận diện qua các thuộc tính còn lại, quyền truy cập, khóa mã hóa, retention của backup và bản sao analytics. **Soft delete không đồng nghĩa đã xóa dữ liệu cá nhân.**

### 16.2. Quan hệ giữ lại có thể cần “tombstone”

Khi một đối tượng nguồn bị gỡ khỏi hệ thống nhưng sự kiện lịch sử vẫn phải biết nó từng tồn tại, có thể lưu **tombstone** hoặc mã nguồn lịch sử đã được kiểm soát. Không tạo Customer giả mà không có thuộc tính xác định rồi coi mọi Order đều có Customer hợp lệ.

Nếu dùng Unknown Member, tài liệu phải nói rõ đâu là **tham chiếu chưa biết**, đâu là **đối tượng bị xóa theo policy**, đâu là **đối tượng thực sự tồn tại**. Ba trường hợp có ý nghĩa và quyền truy cập khác nhau.

## 17. Quan hệ đa hình, dữ liệu nguồn và miền đối tượng

Một tình huống dễ mô tả mơ hồ:

~~~text
Comment(
  target_type,
  target_id,
  content
)
~~~

target_type có thể là ORDER, PRODUCT hoặc CUSTOMER. Một FK chỉ theo target_id không bảo vệ được target thuộc **đúng bảng theo target_type**. Nếu hệ thống thật sự dùng polymorphic association, tài liệu phải mô tả:

- Tập loại target hợp lệ.
- Định danh và tenant scope của từng loại.
- Ai kiểm tra sự tồn tại/ownership của target.
- Điều gì xảy ra khi target bị xóa/archived.
- Bội số theo từng loại target.
- Cách truy vấn tránh nhầm ID bằng nhau ở hai bảng khác nhau.

Một số hướng mô hình hóa:

| Phương án | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Các cột nullable order_id/product_id riêng + CHECK đúng một | Có thể dùng FK tới từng bảng | Nhiều cột, cần kiểm soát XOR, khó thêm loại |
| Bảng liên kết riêng CommentOrder, CommentProduct | FK rõ ràng, quan hệ có vòng đời riêng | Nhiều bảng, đường đọc UNION |
| Bảng supertype Target chung | Có một PK/FK thống nhất | Cần thiết kế lifecycle/đồng bộ subtype đúng |
| target_type + target_id không FK vật lý | Linh hoạt ở ingest | Phải có validation/owner/orphan reconciliation mạnh |

Không coi một polymorphic ID là “khóa ngoại” nếu DBMS không cưỡng chế được. Trong model documentation, hãy ghi **logical reference** và chính sách kiểm chứng tương ứng.

### 17.1. Nhiều nguồn dùng mã khác nhau

Nếu một Product có mã P-101 ở ERP và SKU-001 ở storefront, bảng ánh xạ có thể là một thực thể riêng:

~~~text
ProductExternalIdentity(
  source_system,
  source_product_code,
  tenant_id,
  product_id,
  valid_from,
  valid_to
)
~~~

Không JOIN đơn giản hai bảng theo tên sản phẩm; cũng không assume một mã nguồn có ý nghĩa toàn bộ vòng đời. Nếu mapping thay đổi theo thời gian, quan hệ tới Product cần **thời gian hiệu lực, phạm vi source và kiểm tra không chồng lấp**.

## 18. So sánh tài liệu quan hệ ở relational, document, graph và warehouse

Cùng một ý nghĩa nghiệp vụ có thể được hiện thực bằng những cấu trúc khác nhau. Tài liệu phải giữ **ngữ nghĩa bất biến**, không ép mọi công nghệ trông như ERD quan hệ.

### 18.1. Quan hệ (RDBMS)

- **PK/UNIQUE:** định danh và khóa ứng viên.
- **FK:** tham chiếu, có thể cưỡng chế trong cùng DBMS và phạm vi transaction.
- **CHECK/NOT NULL:** tính hợp lệ cục bộ của một hàng.
- **Procedure/transaction:** các invariant xuyên hàng và chuyển trạng thái.
- **Index/partition:** đường truy cập vật lý; không tự thay invariant.

Tài liệu cần phân biệt constraint **đang được DB cưỡng chế** với quy tắc **mới được định nghĩa ở ứng dụng**.

### 18.2. Document: nhúng quan hệ thành thành phần sở hữu

Một Order document có thể chứa Lines:

~~~json
{
  "tenantId": 1,
  "orderId": 1001,
  "status": "DRAFT",
  "customerId": 11,
  "lines": [
    {"lineNo": 1, "productId": 101, "quantity": 2, "unitPriceVnd": 150000}
  ]
}
~~~

Ở đây Order–Line được mô hình hóa như **quan hệ thành phần được nhúng**. Điều này phù hợp nếu Line chỉ có ý nghĩa trong Order và thường được đọc/ghi cùng Order. Nhưng cần hỏi:

- Document DB có hỗ trợ cập nhật nguyên tử một document không?
- Có giới hạn kích thước/mức contention khi Lines tăng rất nhiều không?
- Customer/Product vẫn ở document khác: ai kiểm tra tham chiếu và tenant?
- Product đổi tên, giá hiện hành có làm thay lịch sử Line không?
- Khi xóa Order document, toàn bộ Lines bị xóa theo: có phù hợp retention không?

Nhúng dữ liệu không tự giải quyết mọi quan hệ 1–N hoặc mọi constraint xuyên document. Tài liệu lifecycle quan trọng không kém DDL.

### 18.3. Graph: quan hệ có thể là cạnh có thuộc tính

Trong graph:

~~~text
(Customer {tenant:1,id:11})
   -[:PLACED]-> (Order {tenant:1,id:1001})

(Order {tenant:1,id:1001})
   -[:CONTAINS {lineNo:1,quantity:2}]->
 (Product {tenant:1,id:101})
~~~

Nếu mô hình dùng cạnh CONTAINS đại diện OrderLine, phải hỏi **OrderLine có danh tính và vòng đời độc lập** không. Một Line có thể cần giá tại thời điểm bán, chiết khấu, trả hàng, điều chỉnh, chứng từ và source_line_id; lúc đó **Line node/relationship entity riêng** có thể phù hợp hơn một cạnh đơn giản.

Graph còn có các invariant đặc biệt:

- Mỗi Category có tối đa một parent trực tiếp hay nhiều parent?
- Có cấm chu trình không?
- Có cho phép nhiều cạnh cùng loại giữa cùng hai node?
- Cạnh có effective_from/effective_to và lịch sử không?
- Một truy vấn đi theo nhiều đường có thể đếm cùng Product nhiều lần không?

**Bội số cạnh** và tính không chu trình không tự được giải quyết chỉ vì mô hình được lưu trong graph DB.

### 18.4. Kho phân tích: fact và chiều có grain riêng

Một Order có nhiều Line nên FactSalesLine thường có grain **một dòng bán**, không phải một Order. DimCustomer/DimProduct phục vụ ngữ cảnh. Tài liệu phải nói:

- Khóa Product ở fact là **business key** hay **surrogate key của phiên bản SCD2**?
- Có bắt buộc mọi fact tham chiếu dimension? Unknown member là gì?
- Một OrderLine có thể xuất hiện ở nhiều fact/event khác nhau không?
- Kết hợp FactSales với FactReturns có gây fan-out không?
- Khi Product archive/đổi Category, báo cáo lịch sử theo Category cũ hay hiện tại?

Trong OLAP, tài liệu khóa và bội số quyết định cách JOIN/aggregate an toàn. Không dùng sơ đồ một đường FK để suy ra mọi measure có thể SUM trên mọi dimension.

## 19. Review mô hình: biến sơ đồ thành tài liệu có phiên bản

Một nhóm nên kiểm tra **mô hình, DDL và dữ liệu thật** theo cùng một phiên bản. Quy trình đề xuất:

1. **Tập hợp câu hỏi nghiệp vụ** cần mô hình trả lời.
2. **Liệt kê thực thể và định nghĩa một hàng** cho mỗi thực thể/bảng.
3. **Xác định candidate keys**, phạm vi tenant/source/time và chính sách đổi mã.
4. **Viết predicate cho mỗi quan hệ** theo hai chiều.
5. **Gán bội số min..max** và điều kiện theo trạng thái.
6. **Xác định hành vi vòng đời:** tạo, sửa, tách/gộp, archive, hard delete, ẩn danh.
7. **Chọn owner/transaction boundary** cho các invariant không thể bảo vệ bằng một hàng.
8. **Ánh xạ sang PK/FK/UNIQUE/CHECK/index** và nêu rõ các quy tắc chưa được DB cưỡng chế.
9. **Viết test âm và truy vấn đối soát** cho các lỗi dự kiến.
10. **Kiểm tra với dữ liệu hiện có**: NULL, orphan, duplicate, sai tenant, late events, history.
11. **Review với chủ nghiệp vụ và đội kỹ thuật**: chốt quyền, ngoại lệ, SLO và thời hạn lưu trữ.
12. **Phiên bản hóa tài liệu và migration**: nêu thay đổi tác động tới API, CDC, BI và các service.
13. **Theo dõi drift sau triển khai**: so ràng buộc đã công bố với schema thực, test và dữ liệu phát sinh.

### 19.1. Khi đổi bội số hoặc vòng đời

Ví dụ ban đầu Order → Customer = 1..1, sau đó thêm guest checkout. Không thể chỉ đổi customer_id sang nullable mà không trả lời:

- Guest Order được phân biệt bằng trường nào?
- Có cần guest_contact_snapshot, consent và retention khác không?
- Một guest có thể sau đó được gắn với Customer mới hay không?
- Nếu được gắn sau, lịch sử hóa quyết định này thế nào?
- Các API cũ có giả định customer_id luôn tồn tại?
- Dashboard đếm khách duy nhất có tính guest thế nào?

Thay đổi bội số **1..1 thành 0..1** kéo theo thay đổi ngữ nghĩa, nullable, quyền truy cập, ETL và test. Một migration DDL thành công chưa đồng nghĩa đã cập nhật hợp đồng toàn hệ.

### 19.2. Mẫu quyết định thiết kế ngắn

~~~text
Decision:
  Product không bị xóa cứng nếu đã có OrderLine lịch sử.

Rationale:
  Cần truy vết giao dịch, chứng từ và hoàn/trả.

Model:
  OrderLine -> Product: 1..1
  Product -> OrderLine: 0..N
  FK cùng tenant, ON DELETE RESTRICT.

Allowed lifecycle:
  Product is_active TRUE -> FALSE.
  Không cho Line mới chọn Product inactive.
  Line lịch sử vẫn tham chiếu Product.

Enforcement:
  FK bảo vệ tham chiếu.
  Write owner bảo vệ điều kiện active khi tạo Line.
  Audit/reconciliation kiểm tra đường ghi bỏ qua owner.

Alternatives:
  Snapshot đầy đủ SKU/tên sản phẩm tại Line
  hoặc dimension version nếu cần lịch sử phân loại.

Review trigger:
  Khi thay đổi retention, chính sách xóa dữ liệu
  hoặc cấu trúc Product/SKU.
~~~

Decision record giúp người bảo trì sau này biết **vì sao** một FK được cấu hình RESTRICT và cần tham khảo ai trước khi đổi sang CASCADE.

## 20. Lỗi tài liệu hóa thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ vẽ đường nối, không có predicate | Hai nhóm hiểu quan hệ khác nhau | Viết câu nghiệp vụ hai chiều |
| Chỉ ghi “1–N”, bỏ min cardinality | Không biết có được 0 Line hay không | Ghi 0..N / 1..N theo trạng thái |
| Gọi mọi ID là PK toàn cục | Nhầm tenant, mã nguồn, phiên bản | Ghi phạm vi candidate/business/surrogate key |
| FK chỉ theo customer_id trong hệ multi-tenant | Có thể tham chiếu nhầm tenant | FK ghép tenant_id + customer_id |
| Cho rằng FK bắt Order phải có Line | Order CONFIRMED thiếu Line | Owner transaction + kiểm tra mọi writer |
| Cho rằng NOT NULL chứng minh quan hệ hợp lệ | Cột có ID nhưng cha có thể không tồn tại | FK hoặc logical reference được kiểm soát |
| Dùng CASCADE cho mọi phụ thuộc | Xóa mất lịch sử tài chính | Lifecycle và retention trước ON DELETE |
| Cho rằng soft delete giống DELETE | Writer vẫn tham chiếu archived object | Quy tắc archive trong owner |
| Dùng Unique cho mã có thể tái sử dụng nhưng không ghi scope/time | Phá chính sách hoặc trùng lịch sử | Định nghĩa uniqueness theo trạng thái/hiệu lực |
| Chỉ dùng CHECK(status IN (...)) cho workflow | Chuyển trạng thái trái phép | State machine và transition guard |
| Không tài liệu hóa các mối quan hệ nhiều vai trò | Nhầm người mua/người nhận/người duyệt | Role names và FK riêng |
| Giữ nhiều version SCD2 nhưng JOIN bằng business key không lọc thời gian | Nhân fact và báo cáo sai | FK version key/lookup as-of |
| JOIN nhiều bảng con rồi SUM | Fan-out | Aggregate theo grain trước JOIN |
| Document nhúng nhưng không ghi lifecycle | Xóa parent làm mất dữ liệu cần giữ | Nêu rõ atomicity và retention |
| Graph chỉ kiểm tra parent != self | Chu trình dài vẫn có | Kiểm tra toàn đường và concurrency |
| Mô tả logical FK như FK được DB cưỡng chế | Hiểu nhầm bảo đảm xuyên service | Ghi owner, protocol, reconciliation |
| Không kiểm thử thao tác bị cấm | Constraint sai tồn tại lâu | Negative tests/concurrent tests |
| Tài liệu không cập nhật khi schema thay đổi | Mất đồng bộ với production | Versioning, ADR, drift checks |

## 21. Bài tập tình huống và hướng dẫn giải

### Bài 1. Khóa Order theo tenant

**Đề bài:** Hai tenant đều có order_id = 1001 và order_code = O-1001. Khóa duy nhất nào phù hợp nếu business cho phép mã trùng giữa tenant?

**Gợi ý giải:** PK(tenant_id,order_id) và UNIQUE(tenant_id,order_code). Không đặt UNIQUE(order_code) toàn bảng khi phạm vi định danh là tenant. Nếu order_id toàn cục là quy ước thật, cần ghi rõ khác biệt này.

### Bài 2. Diễn giải bội số hai phía

**Đề bài:** Một Customer có thể chưa đặt đơn; một Order bắt buộc thuộc Customer. Viết bội số cho hai chiều.

**Gợi ý giải:** Customer → Order là 0..N; Order → Customer là 1..1. FK customer_id NOT NULL trong Orders và tham chiếu Customer bảo vệ phía Order, không buộc Customer phải có Order.

### Bài 3. Điều kiện theo trạng thái

**Đề bài:** DRAFT có thể chưa có Line, CONFIRMED phải có ít nhất một Line. FK OrderLine → Order có đủ không?

**Gợi ý giải:** Không. FK chỉ bảo vệ Line có Order. Cần quy tắc ConfirmOrder kiểm tra EXISTS Line trong cùng transaction/owner và ngăn writer khác xóa Line cuối sau khi xác nhận.

### Bài 4. 1–1 nhưng optional

**Đề bài:** Mỗi User có thể có tối đa một Profile, nhưng tạo tài khoản chưa bắt buộc có Profile. Nên đặt FK/UNIQUE thế nào?

**Gợi ý giải:** Profile.user_id NOT NULL + FK + UNIQUE. User không cần Profile ngay, nên không kết luận toàn bộ User có Profile chỉ từ FK ở phía Profile.

### Bài 5. Quan hệ N–M và định danh

**Đề bài:** Một Order có nhiều Label; một Label dùng cho nhiều Order. Làm sao ngăn gắn cùng Label hai lần ở trạng thái hiện hành?

**Gợi ý giải:** Bảng OrderLabelLink với PK(tenant_id,order_id,label_id) và hai FK cùng tenant. Nếu cần lịch sử gắn/tháo, đổi grain sang event/khoảng hiệu lực và bảo vệ không chồng lấp các khoảng active.

### Bài 6. Product inactive

**Đề bài:** Product ngừng bán, nhưng nhiều OrderLine lịch sử vẫn tham chiếu Product. Có nên ON DELETE CASCADE từ Product xuống Line?

**Gợi ý giải:** Không khi lịch sử Order cần được giữ. Dùng is_active/archived và FK ON DELETE RESTRICT; write owner ngăn chọn Product inactive cho Line mới, trong khi Line lịch sử vẫn hợp lệ.

### Bài 7. Xóa Customer có đơn hàng

**Đề bài:** Customer được yêu cầu ẩn danh nhưng các chứng từ Order cần lưu theo chính sách. Có nên xóa Customer làm mất Orders?

**Gợi ý giải:** Không mặc định. Phải thiết kế policy tách PII/định danh giao dịch, archive/ẩn danh có kiểm soát và retention. Soft delete không đồng nghĩa đã xóa PII; hard delete cần xem FK và nghĩa vụ lưu trữ cụ thể.

### Bài 8. CHECK và chuyển trạng thái

**Đề bài:** Status chỉ thuộc DRAFT, CONFIRMED, CANCELLED. Một writer chuyển CANCELLED → CONFIRMED. CHECK(status IN (...)) có chặn không?

**Gợi ý giải:** Không, CONFIRMED vẫn là giá trị trong miền. Cần state machine và quy tắc transition so trạng thái cũ/mới trong transaction, đồng thời kiểm soát mọi writer.

### Bài 9. Trùng line_no

**Đề bài:** Order 1001 và Order 1002 đều có Line số 1. Đây có phải duplicate?

**Gợi ý giải:** Không. Grain và khóa của Line là (tenant_id,order_id,line_no). UNIQUE(line_no) toàn bảng là sai.

### Bài 10. FK ghép và NULL

**Đề bài:** FK(tenant_id, customer_id) hợp lệ nhưng customer_id NULL vẫn được chấp nhận theo cấu hình mặc định. Vì sao?

**Gợi ý giải:** Với FK theo MATCH SIMPLE, khi một thành phần tham chiếu NULL, việc kiểm tra tham chiếu có thể được bỏ qua. Nếu Customer bắt buộc, cần customer_id NOT NULL cùng FK; guest order cần một mô hình có ngoại lệ rõ.

### Bài 11. Mã không phải ID

**Đề bài:** Product đổi SKU từ A-101 sang A-102; OrderLine lịch sử phải còn trỏ đúng Product. Có nên lưu SKU làm FK duy nhất không?

**Gợi ý giải:** Cân nhắc product_id ổn định làm FK và UNIQUE SKU theo policy. Nếu chứng từ cần SKU tại thời điểm bán, lưu snapshot hoặc version tương ứng; không sửa ngầm chứng từ lịch sử khi Product đổi mã.

### Bài 12. Một Order có nhiều Attempt

**Đề bài:** Một Order có 2 PaymentAttempt và 3 Line. JOIN trực tiếp rồi SUM tiền Attempt tạo mấy dòng ghép nếu mọi hàng khớp?

**Gợi ý giải:** 2 × 3 = 6. Tổng tiền có thể bị nhân ba lần. Tổng hợp Attempt và Line về grain Order trước rồi JOIN; xác định rõ Attempt nào CAPTURED mới được tính.

### Bài 13. Category có chu trình dài

**Đề bài:** A có parent B, B có parent C, C có parent A. CHECK(parent_category_id <> category_id) có phát hiện không?

**Gợi ý giải:** Không, không node nào làm cha trực tiếp của chính nó. Muốn đảm bảo đồ thị phân cấp không có chu trình cần kiểm tra đường đi có concurrency control hoặc cấu trúc owner phù hợp.

### Bài 14. Quan hệ có hiệu lực thời gian

**Đề bài:** Một Order có Label L trong [01/10,10/10), sau đó [10/10,20/10). Hai hàng có chồng lấp không? Nếu có [05/10,12/10) thì sao?

**Gợi ý giải:** Hai khoảng đầu chỉ chạm ranh giới nên không chồng lấp khi dùng khoảng nửa mở. Khoảng thứ ba chồng lấp cả hai. CHECK(valid_to > valid_from) không tự cấm overlap; cần constraint/procedure kiểm tra theo cùng khóa quan hệ.

### Bài 15. Tách service nhưng vẫn ghi FK trên sơ đồ

**Đề bài:** Customer ở database A, Orders ở database B; tài liệu ghi “FK Orders.customer_id → Customer.id” dù không có distributed FK. Có vấn đề gì?

**Gợi ý giải:** Tài liệu đang mô tả sai bảo đảm thực tế. Phải gọi logical reference, nêu scope, owner, kiểm tra sự tồn tại, xử lý xóa/chuyển tenant, timeout, replay, orphan reconciliation và thời điểm chấp nhận.

### Bài 16. Đổi từ Order có Customer bắt buộc sang guest checkout

**Đề bài:** Product muốn cho đặt hàng không có tài khoản. Có phải chỉ cần bỏ NOT NULL khỏi customer_id?

**Gợi ý giải:** Không. Cần quyết định cách phân biệt guest/registered, thông tin giao hàng và retention, khả năng gắn guest vào Customer về sau, các API/báo cáo giả định Customer và quy tắc kiểm tra. Đây là thay đổi bội số và vòng đời, không chỉ schema.

## 22. Checklist nghiệm thu tài liệu khóa, quan hệ và vòng đời

- [ ] Mỗi thực thể có **định nghĩa một hàng** và phạm vi nghiệp vụ rõ ràng.
- [ ] Candidate key, primary key, alternate/business key và chính sách đổi/tái sử dụng mã được ghi rõ.
- [ ] Khóa theo tenant/source/region có **phạm vi duy nhất** được kiểm chứng, không suy từ dữ liệu mẫu.
- [ ] Mỗi quan hệ có **predicate**, tên vai trò ở hai đầu, bội số tối thiểu/tối đa từ cả hai góc nhìn.
- [ ] Điều kiện bội số thay đổi theo **trạng thái hoặc thời gian** được ghi ngoài ERD tĩnh.
- [ ] FK được ánh xạ đúng hướng, gồm các cột tenant khi cần; tham chiếu xuyên DB được đánh dấu logical.
- [ ] Các quan hệ 1–1, 1–N, N–M và tự tham chiếu có **khóa và bảng liên kết** phù hợp.
- [ ] ON DELETE/ON UPDATE được quyết định theo **vòng đời nghiệp vụ và retention**, không theo thói quen.
- [ ] Quy tắc tạo, cập nhật, khóa, archive, ẩn danh, xóa và chuyển trạng thái của từng thực thể được nêu cụ thể.
- [ ] Các invariant không thể bảo vệ bằng FK/CHECK được gán **write owner, transaction/procedure và test concurrency**.
- [ ] Có chính sách cho NULL, Unknown, guest, late data, orphan, duplicate và sự kiện lịch sử.
- [ ] Các chiều có hiệu lực thời gian/SCD được JOIN đúng version, không tạo fan-out do chồng lấp.
- [ ] Chính sách dữ liệu cá nhân và lưu giữ lịch sử có owner/quy trình, không nhầm soft delete với xóa PII.
- [ ] Data dictionary, ERD, relationship catalog, DDL và API/event schema diễn đạt cùng một phiên bản hợp đồng.
- [ ] Các phép kiểm chứng âm/dương và query đối soát đã được gắn với từng invariant quan trọng.
- [ ] Khi mô hình thay đổi, có review tác động tới reader/writer, CDC, document, graph, warehouse và dashboard.

## 23. Ghi nhớ

- **Khóa** không chỉ là kiểu dữ liệu của cột ID: phải có phạm vi, tính ổn định, chính sách đổi/tái sử dụng và ràng buộc PK/UNIQUE phù hợp.
- **Quan hệ** phải được đọc như một câu nghiệp vụ có vai trò, không chỉ là đường nối và tên FK.
- **Bội số** gồm **tối thiểu và tối đa ở cả hai phía**. Bội số có thể phụ thuộc trạng thái như Order CONFIRMED cần Line, điều một ERD tĩnh khó thể hiện đầy đủ.
- **FK bảo vệ một chiều tham chiếu**, nhưng không tự bảo vệ toàn bộ invariant xuyên hàng hay máy trạng thái.
- **ON DELETE/UPDATE** là quyết định vòng đời: CASCADE có thể hợp lệ cho dữ liệu phụ, nhưng nguy hiểm với chứng từ, Payment và lịch sử nghiệp vụ.
- **Soft delete, archive, anonymize và hard delete khác nhau** về ngữ nghĩa, tham chiếu và nghĩa vụ dữ liệu.
- **Quan hệ có thời gian hiệu lực** cần mô tả khoảng, version, thời điểm tra cứu và bảo vệ chồng lấp.
- **Tenant/shard/service** là một phần của hợp đồng định danh và thực thi; logical reference xuyên service không phải FK được DBMS cưỡng chế.
- **Tài liệu có thể kiểm chứng** khi nối mỗi bất biến với một constraint, owner/protocol và phép thử hoặc truy vấn đối soát.

Một bản tài liệu mô hình dữ liệu hữu ích không chỉ giúp người xem hiểu các bảng được nối với nhau như thế nào. Nó phải cho phép kỹ sư, người phụ trách nghiệp vụ và người kiểm thử **cùng kết luận chính xác một hàng được định danh ra sao, ai được liên kết với ai, có thể liên kết bao nhiêu lần, khi nào quan hệ hợp lệ và điều gì phải xảy ra khi vòng đời của các đối tượng thay đổi**.


