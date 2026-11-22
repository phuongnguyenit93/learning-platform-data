# Khóa chính, khóa nghiệp vụ và quan hệ giữa dữ liệu cùng tổ chức trong Hibernate ORM

## 1. Khi ID đúng nhưng lại thuộc tổ chức khác

Hãy hình dung một ứng dụng quản lý bán hàng SaaS phục vụ nhiều tổ chức (organizations). Mỗi tổ chức có khách hàng, đơn hàng, sản phẩm và nhân viên riêng. Người dùng có thể là thành viên của một hoặc nhiều tổ chức, nhưng tại một thời điểm họ chỉ được thao tác trên dữ liệu của những tổ chức đã được cấp quyền.

Một ứng dụng đơn tổ chức có thể tạo đơn hàng như sau:

~~~java
Customer customer = customerRepository.findById(customerId)
    .orElseThrow();

PurchaseOrder order = new PurchaseOrder(customer);
orderRepository.save(order);
~~~

Trong môi trường nhiều tổ chức, đoạn code này có thể sai nghiêm trọng. Khóa customerId có thể trỏ đến một Customer của tổ chức B trong khi Order đang được tạo cho tổ chức A. Nếu database chỉ dùng foreign key:

~~~sql
FOREIGN KEY (customer_id) REFERENCES customers(id)
~~~

thì foreign key chỉ xác minh rằng Customer ID có tồn tại, **không xác minh Customer và Order thuộc cùng organization**.

Ví dụ:

| Bản ghi | ID | organization_id | Ý nghĩa |
|---|---:|---:|---|
| Customer A | 21 | 7 | Khách hàng của tổ chức 7 |
| Customer B | 82 | 8 | Khách hàng của tổ chức 8 |
| Order mới | 901 | 7 | Đơn hàng của tổ chức 7 |

Nếu Order 901 tham chiếu customer_id = 82, foreign key chỉ theo customer_id vẫn hợp lệ, dù đây là **liên kết chéo tổ chức ngoài ý muốn**.

Bài học đặt ra ba câu hỏi tách biệt:

1. **Khóa chính (primary key)** xác định một row bằng những cột nào?
2. **Khóa nghiệp vụ (business key)** xác định đối tượng theo quy tắc nghiệp vụ trong phạm vi nào?
3. **Khóa ngoại (foreign key)** có bảo đảm hai row có quan hệ thuộc cùng tổ chức không?

Chọn khóa chính tốt chưa đủ. Một hệ thống nhiều tổ chức còn phải thiết kế khóa nghiệp vụ, khóa ngoại, truy vấn Hibernate và authorization để các tầng thống nhất về **phạm vi sở hữu dữ liệu**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt khóa thay thế (surrogate key), khóa tự nhiên/nghiệp vụ, khóa ghép và tenant/organization scope.
2. Chọn giữa ID toàn cục và primary key ghép organization_id + local_id.
3. Thiết kế UNIQUE theo tổ chức cho mã khách hàng, số đơn hàng và định danh nghiệp vụ.
4. Dùng composite foreign key để ngăn liên kết cross-organization.
5. Ánh xạ khóa, UNIQUE và quan hệ đó bằng Jakarta Persistence/Hibernate.
6. Hiểu @EmbeddedId, @IdClass, @MapsId và các điểm dễ nhầm khi mapping cột được chia sẻ.
7. Viết repository/service luôn mang organization context được xác minh.
8. Không nhầm ID khó đoán, Hibernate Filter hay composite key với authorization.
9. Xử lý soft delete, chuyển dữ liệu giữa tổ chức và tài nguyên dùng chung.
10. Kiểm thử constraint, giao dịch, cache, migration và các tình huống tấn công truy cập chéo.

Ví dụ dùng Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA và PostgreSQL. Các đoạn code minh họa cần được đưa vào các file/class tương ứng và căn đúng phiên bản của dự án.

## 2. “Tổ chức” là một ranh giới dữ liệu, không chỉ là cột để lọc

Trong hệ thống nhiều tổ chức, các khái niệm thường gặp:

- **Organization**: một công ty/đơn vị khách hàng sử dụng phần mềm.
- **User**: danh tính đăng nhập, có thể thuộc nhiều organizations.
- **Membership**: việc một user được cấp vai trò trong một organization.
- **Organization-owned record**: bản ghi như Customer, Order, Invoice, Product thuộc một organization cụ thể.
- **Shared reference data**: dữ liệu chung như mã quốc gia, tiền tệ hoặc loại đơn vị đo, có thể không thuộc riêng organization nào.

Trong bài này, organization_id là ranh giới sở hữu dữ liệu. Nếu dự án dùng từ **tenant**, hãy xác nhận tenant và organization có cùng nghĩa không. Một tenant có thể chứa nhiều organizations, hoặc một organization có nhiều sub-accounts; không được tự động hoán đổi tenant_id và organization_id khi mô hình thực tế có nhiều tầng.

### 2.1. Sơ đồ sở hữu

~~~mermaid
flowchart TD
    O[Organization] --> C[Customer]
    O --> P[Product]
    O --> R[PurchaseOrder]
    R --> I[OrderItem]
    C --> R
    U[Global User] --> M[OrganizationMembership]
    O --> M
    G[Shared Currency Catalog] -. lookup chung .-> R
~~~

Các mũi tên thể hiện sở hữu/tham chiếu ở mức khái niệm. Trong database, quan hệ Customer → Order và Order → OrderItem cần ràng buộc cả organization scope.

### 2.2. Hai yêu cầu độc lập

**Dữ liệu đúng:** một Order của organization 7 không được tham chiếu Customer của organization 8.

**Truy cập đúng:** một user không có quyền organization 8 không được đọc/sửa Orders của organization 8.

Composite FK có thể giải quyết phần lớn bài toán **dữ liệu đúng**, nhưng không tự kiểm tra người đang đăng nhập. Repository predicate, application authorization hoặc RLS giải quyết **truy cập đúng**. Cần cả hai.

### 2.3. Không đồng nhất organization ID với user ID

~~~text
user_id = 19
membership = {(19, 7), (19, 8)}
active_organization_id = 7
~~~

Đăng nhập bằng user 19 không có nghĩa dữ liệu của user đó tự thuộc organization 19. Organization context phải được chọn từ những tổ chức mà user được cấp quyền, không được suy ra bằng một phép gán nhầm userId = organizationId.

## 3. Khóa chính, khóa ứng viên và khóa nghiệp vụ

### 3.1. Khóa chính (primary key)

Khóa chính định danh một row trong bảng và có tính duy nhất, không NULL. Ví dụ:

~~~sql
CREATE TABLE organizations (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL
);
~~~

id là primary key; code có UNIQUE nên là một alternate/candidate key phù hợp nếu có thêm điều kiện NOT NULL.

### 3.2. Surrogate key

Một ID không mang ý nghĩa nghiệp vụ:

~~~sql
id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
~~~

hoặc:

~~~sql
id UUID PRIMARY KEY
~~~

Đây là **surrogate key**. Ưu điểm thường gặp: ổn định khi tên/mã nghiệp vụ đổi, reference bằng một cột, giảm phụ thuộc business rules. Tuy nhiên ID có tính duy nhất toàn bảng **không bảo đảm** row được phép truy cập hoặc quan hệ cùng tổ chức.

### 3.3. Business/natural key

Một tổ chức có thể dùng customer_code = C-001, order_number = SO-2026-00001. Các giá trị này có ý nghĩa nghiệp vụ, được tìm kiếm, hiển thị hoặc truyền qua API.

Nhưng trong SaaS nhiều tổ chức:

~~~text
Organization 7: Customer code C-001
Organization 8: Customer code C-001
~~~

Hai khách hàng là hai thực thể khác nhau. Vì vậy khóa nghiệp vụ thường là **cặp (organization_id, customer_code)**, không chỉ customer_code.

### 3.4. Candidate key, alternate key và index không đồng nghĩa

- PRIMARY KEY: lựa chọn một khóa chính cho row.
- UNIQUE + NOT NULL (hoặc cấu trúc tương đương): thực thi tính duy nhất của một candidate key.
- Business key: khái niệm nghiệp vụ có thể được ràng buộc UNIQUE.
- INDEX thông thường: giúp tra cứu, **không cấm trùng**.
- FOREIGN KEY: đảm bảo các giá trị tham chiếu hợp lệ theo key/constraint ở bảng đích.

Một khóa nghiệp vụ không nhất thiết phải trở thành primary key; có thể giữ ID thay thế làm PK và đặt UNIQUE cho khóa nghiệp vụ.

## 4. Thiết kế 1 — ID toàn cục cho từng bảng, UNIQUE theo tổ chức

Đây là một lựa chọn phổ biến khi tất cả organizations dùng chung database và schema.

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(id),
    customer_code VARCHAR(50) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT uq_customers_org_code
        UNIQUE (organization_id, customer_code),
    CONSTRAINT uq_customers_org_id
        UNIQUE (organization_id, id)
);
~~~

Ý nghĩa:

- id định danh một Customer trên toàn bảng.
- organization_id xác định bên sở hữu Customer.
- (organization_id, customer_code) bảo đảm cùng một tổ chức không có hai mã khách hàng trùng nhau.
- Tổ chức khác được phép dùng cùng customer_code.
- UNIQUE(organization_id, id) phục vụ foreign key ghép từ bảng con trong PostgreSQL.

### 4.1. Tại sao có UNIQUE(organization_id, id) dù id đã PRIMARY KEY?

Về mặt logic, id đã duy nhất nên cặp (organization_id, id) cũng duy nhất. Nhưng nếu một bảng khác muốn khai báo:

~~~sql
FOREIGN KEY (organization_id, customer_id)
    REFERENCES customers(organization_id, id)
~~~

PostgreSQL yêu cầu bộ cột được tham chiếu có UNIQUE/PRIMARY KEY hoặc unique index phù hợp theo luật FK của PostgreSQL. PRIMARY KEY chỉ trên id **không tự cung cấp một khóa được khai báo trên cặp (organization_id,id)** cho composite FK đó.

Vì vậy UNIQUE ghép trông dư về logic nhưng có vai trò làm **referenced key** cho ràng buộc same-organization. Nó có chi phí index/ghi/storage; thiết kế phải cân đối với yêu cầu toàn vẹn.

### 4.2. Global ID không phải mã khách hàng

Một Customer đổi customer_code từ C-001 thành C-778 nhưng id vẫn là 21. Những Order tham chiếu customer_id 21 không phải cập nhật FK chỉ vì mã khách hàng đổi.

Ngược lại, nếu customer_code là PK, đổi mã có thể dẫn đến ON UPDATE handling hoặc phải cập nhật nhiều FKs. Chỉ chọn business key làm PK khi nó thật sự ổn định và có lý do thiết kế.

## 5. Thiết kế 2 — Composite primary key gồm organization_id và local_id

Một lựa chọn khác là định danh mỗi row bằng cặp:

~~~sql
CREATE TABLE purchase_orders_composite (
    organization_id BIGINT NOT NULL
        REFERENCES organizations(id),
    local_id UUID NOT NULL,
    order_number VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    PRIMARY KEY (organization_id, local_id),
    UNIQUE (organization_id, order_number)
);
~~~

Ở đây local_id chỉ được yêu cầu duy nhất **trong organization**. Thực tế UUID có thể được sinh toàn cục để giảm khả năng trùng, nhưng PK vẫn là (organization_id, local_id) theo hợp đồng dữ liệu.

### 5.1. Lợi ích

- Định danh persistent object thể hiện rõ phạm vi organization.
- FK từ child tự nhiên bao gồm organization_id.
- Hai tổ chức có thể dùng cùng local ID mà vẫn không đụng PK.
- Có thể phù hợp với dữ liệu phân vùng/shard theo organization.

### 5.2. Chi phí

- Mọi FK phải mang organization_id và local_id.
- JPA ID mapping, repository ID type và serialization phức tạp hơn.
- PK lớn hơn làm index/FK lớn hơn, ảnh hưởng storage và join.
- ID generator theo từng organization cần được thiết kế, không tự xuất hiện khi dùng @EmbeddedId.
- Thao tác đổi organization_id đồng nghĩa đổi một phần PK, thường không nên được phép.

### 5.3. So sánh hai kiểu PK

| Tiêu chí | PK toàn cục: id | PK ghép: (organization_id, local_id) |
|---|---|---|
| Repository ID | Long/UUID đơn giản | @EmbeddedId hoặc @IdClass |
| FK same-org | Cần composite FK + UNIQUE(organization_id,id), hoặc ràng buộc tương đương | FK ghép theo PK tự nhiên |
| Độ rộng khóa | Thường nhỏ hơn | Rộng hơn |
| ID local trùng giữa organizations | Không nếu ID là global PK | Có thể |
| Di chuyển row sang org khác | Vẫn rất khó vì quan hệ/bảo mật | Thường là đổi PK, cần tránh |
| Tích hợp API/public ID | Cần luôn mang organization scope khi tra cứu | Thường phải truyền cặp scope + local ID |
| Hibernate mapping | Đơn giản hơn ở entity root | Phức tạp hơn nhưng thể hiện scope rõ |

Không có một lựa chọn bắt buộc cho mọi SaaS. Quan trọng nhất là **mọi quan hệ và query đều bảo toàn organization boundary**, chứ không chỉ đẹp ở bảng root.

## 6. Thiết kế database hoàn chỉnh với PK toàn cục và FK cùng tổ chức

Ta chọn thiết kế 1 để minh họa sự kết hợp giữa PK, business key và FK.

### 6.1. Organizations

~~~sql
CREATE TABLE organizations (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    organization_code VARCHAR(80) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL
);
~~~

organization_code là mã cấp toàn hệ thống nếu business yêu cầu global uniqueness; nó không phải customer_code/order_number được phép trùng theo tổ chức.

### 6.2. Customers

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(id),
    customer_code VARCHAR(50) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT uq_customers_org_code
        UNIQUE (organization_id, customer_code),
    CONSTRAINT uq_customers_org_id
        UNIQUE (organization_id, id)
);
~~~

### 6.3. Purchase orders

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(id),
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(19, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    deleted_at TIMESTAMPTZ,

    CONSTRAINT uq_orders_org_number
        UNIQUE (organization_id, order_number),
    CONSTRAINT uq_orders_org_id
        UNIQUE (organization_id, id),
    CONSTRAINT fk_order_customer_same_org
        FOREIGN KEY (organization_id, customer_id)
        REFERENCES customers(organization_id, id),
    CONSTRAINT ck_order_total
        CHECK (total_amount >= 0)
);
~~~

Composite FK là trọng tâm:

~~~sql
FOREIGN KEY (organization_id, customer_id)
REFERENCES customers(organization_id, id)
~~~

Đơn hàng organization 7 chỉ được tham chiếu khách hàng có cặp (7, customer_id). Nếu customer_id tồn tại nhưng ở organization 8, **DB từ chối INSERT/UPDATE**.

### 6.4. Order items

~~~sql
CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(19, 2) NOT NULL,

    CONSTRAINT fk_item_order_same_org
        FOREIGN KEY (organization_id, order_id)
        REFERENCES purchase_orders(organization_id, id),
    CONSTRAINT uq_item_line_per_order
        UNIQUE (organization_id, order_id, line_number),
    CONSTRAINT ck_item_quantity
        CHECK (quantity > 0)
);
~~~

Nhờ FK ghép, một Item thuộc organization 7 không thể trỏ đến Order của organization 8. Đây là **ràng buộc ở tầng database**, áp dụng cả khi thao tác bằng JDBC, native SQL hoặc dữ liệu nhập từ hệ thống khác.

### 6.5. Cây khóa

~~~mermaid
flowchart TD
    O[organizations PK id] --> C[customers PK id, org_id]
    O --> R[purchase_orders PK id, org_id]
    C -->|FK org_id + customer_id| R
    R -->|FK org_id + order_id| I[order_items PK id, org_id]
    C -. UNIQUE org_id + customer_code .-> K1[Customer business key]
    R -. UNIQUE org_id + order_number .-> K2[Order business key]
~~~

Những FKs ghép cũng làm các thay đổi organization_id của parent rất khó hoặc bị chặn khi có children. Đây thường là điều mong muốn: ownership của một row không nên bị chuyển bằng một UPDATE tùy tiện.

## 7. Điều gì xảy ra khi FK chỉ theo id?

Để thấy khác biệt, thử một ví dụ database test.

Giả sử:

~~~sql
INSERT INTO organizations(id, organization_code, display_name, status)
VALUES (7, 'ORG-A', 'Tổ chức A', 'ACTIVE'),
       (8, 'ORG-B', 'Tổ chức B', 'ACTIVE');

INSERT INTO customers(
    id, organization_id, customer_code, display_name
) VALUES
    (21, 7, 'C-001', 'Khách A'),
    (82, 8, 'C-001', 'Khách B');
~~~

Hai row có cùng customer_code nhưng thuộc hai organizations nên hợp lệ vì UNIQUE ghép.

Bây giờ thử:

~~~sql
INSERT INTO purchase_orders (
    organization_id, customer_id, order_number,
    status, created_at, total_amount, version
) VALUES (
    7, 82, 'SO-001',
    'DRAFT', CURRENT_TIMESTAMP, 100.00, 0
);
~~~

Với composite FK đúng, database từ chối: (organization_id=7, customer_id=82) không tồn tại trong cặp khóa của customers. Nếu chỉ có FK(customer_id) REFERENCES customers(id), thao tác này có thể thành công — và dữ liệu đã bị liên kết chéo.

### 7.1. Mã lỗi không phải lỗi ứng dụng ngẫu nhiên

Trên PostgreSQL, vi phạm FK thường có SQLSTATE 23503. Spring/Hibernate có thể chuyển exception thành nhóm data-integrity exception. Khi gặp lỗi đó, cần:

- Rollback transaction bị lỗi.
- Ghi log kỹ thuật không chứa dữ liệu nhạy cảm không cần thiết.
- Trả lỗi nghiệp vụ thích hợp, thường không tiết lộ customer ID thuộc organization nào.
- Kiểm tra application đã truyền organization context đáng tin cậy chưa.

Không giải quyết bằng cách bỏ FK chỉ để request thành công.

### 7.2. FK ghép không kiểm tra deleted_at

Một Order có thể tham chiếu Customer đã xóa mềm nếu Customer row vẫn tồn tại và khóa ghép còn hợp lệ. FK kiểm tra **tồn tại và scope**, không tự kiểm tra customer.deleted_at IS NULL.

Nếu nghiệp vụ cấm tạo Order mới cho Customer deleted, service cần kiểm tra trạng thái active dưới transaction thích hợp và cân nhắc concurrency; DB có thể dùng mô hình trạng thái/constraint bổ sung nếu cần bảo đảm mạnh hơn.

## 8. Vì sao chỉ thêm organization_id vào mỗi bảng vẫn chưa đủ?

Một schema:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    organization_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customers(id)
);
~~~

có organization_id nhưng **không bắt buộc** organization_id của Customer bằng organization_id của Order.

Nếu chỉ dựa vào application code kiểm tra:

~~~java
if (!order.organizationId().equals(customer.organizationId())) {
    throw new IllegalArgumentException("Khác tổ chức");
}
~~~

thì vẫn có các đường ghi khác: native SQL, batch import, ETL, admin script hoặc bug từ một service khác. Composite FK là tuyến phòng vệ ở DB mà các writer đó khó bypass một cách vô ý.

### 8.1. Defense in depth

Ba lớp nên cùng tồn tại:

1. **Service/domain**: kiểm tra organization ownership và quyền nghiệp vụ, trả thông báo hợp lý.
2. **Repository/query**: tìm entity trong organization scope, không dùng ID trần từ client.
3. **Database constraints**: chặn FK chéo và duplicate business keys ngay cả khi code có bug.

Mỗi lớp có nhiệm vụ khác nhau; chỉ thêm organization_id nhưng thiếu foreign key ghép là chưa giải quyết trọn bài toán quan hệ cùng tổ chức.

## 9. Bảo đảm parent và child cùng organization theo nhiều cấp

Ví dụ:

~~~text
Organization
  -> Customer
      -> PurchaseOrder
          -> OrderItem
              -> ShipmentItem
~~~

Nếu mọi quan hệ parent-child đều có FK ghép theo organization_id, một row ở tầng sâu không thể trỏ trực tiếp đến parent của organization khác qua key hợp lệ.

Nhưng đừng nhầm **quan hệ dọc** với **quan hệ ngang**. Ví dụ Shipment có cả order_id và warehouse_id, cả hai phải thuộc organization:

~~~sql
CREATE TABLE shipments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    UNIQUE (organization_id, id),
    FOREIGN KEY (organization_id, order_id)
        REFERENCES purchase_orders(organization_id, id),
    FOREIGN KEY (organization_id, warehouse_id)
        REFERENCES warehouses(organization_id, id)
);
~~~

Nếu chỉ bảo vệ order_id mà không bảo vệ warehouse_id, một Shipment của organization 7 vẫn có thể liên kết warehouse thuộc organization 8.

### 9.1. Quy tắc kiểm kê quan hệ

Với mỗi foreign key:

- Bảng child thuộc tổ chức nào?
- Bảng parent thuộc một tổ chức hay là dữ liệu global?
- Quan hệ này **bắt buộc cùng tổ chức** hay là một chia sẻ có chủ đích?
- Nếu cùng tổ chức, FK/constraint nào tại DB đang enforce?
- Nếu khác tổ chức có chủ đích, quyền chia sẻ được ghi nhận ở đâu?

Không sao chép một kiểu FK chung cho cả global reference data và organization-owned records.

## 10. Khóa nghiệp vụ luôn phải hỏi “duy nhất trong phạm vi nào?”

Những business keys thường gặp:

| Đối tượng | Khóa nghiệp vụ ví dụ | Phạm vi UNIQUE thường gặp |
|---|---|---|
| Organization | organization_code | Toàn hệ thống |
| Customer | customer_code | Trong một organization |
| Product | sku | Trong một organization hoặc catalog được sở hữu |
| PurchaseOrder | order_number | Trong một organization |
| Invoice | invoice_number | Theo organization và kỳ/quy tắc pháp lý |
| Warehouse | warehouse_code | Trong một organization |
| OrderItem | line_number | Trong một Order thuộc organization |
| Membership | (organization_id, user_id) | Một membership cho cặp org/user |
| Currency | ISO code | Toàn hệ thống nếu là bảng global |

Đừng dùng UNIQUE(customer_code) trên bảng customers chung nếu organization khác được quyền đặt cùng mã.

### 10.1. Unique constraint chống race

Một service kiểm tra:

~~~java
if (!customerRepository.existsByOrganizationIdAndCustomerCode(
        organizationId, code)) {
    customerRepository.save(newCustomer);
}
~~~

không bảo đảm uniqueness khi hai transactions chạy đồng thời. Cả hai có thể thấy chưa tồn tại, rồi cùng INSERT.

Database phải có:

~~~sql
UNIQUE (organization_id, customer_code)
~~~

để một thao tác bị từ chối khi conflict. Service có thể kiểm tra sớm cho UX, nhưng UNIQUE là tuyến bảo vệ cuối.

### 10.2. Normalization của business key

Nếu business coi “c-001”, “C-001” và “ C-001 ” là cùng mã, việc chỉ dùng VARCHAR UNIQUE mặc định có thể chưa đáp ứng tùy collation/database.

Một hướng PostgreSQL:

~~~sql
CREATE UNIQUE INDEX uq_customer_normalized_code
ON customers (
    organization_id,
    lower(btrim(customer_code))
);
~~~

Hoặc chuẩn hóa code trước khi INSERT/UPDATE, có CHECK constraint/quy tắc nhất quán. Không viết hai unique constraints không cần thiết trong production; chọn chính sách rõ, dọn dữ liệu cũ rồi migration cho phù hợp.

### 10.3. Business key thay đổi theo vòng đời

Một Customer có thể đổi customer_code sau khi sáp nhập hệ thống, còn primary key id giữ nguyên. Các FKs tốt nhất tham chiếu ID ổn định thay vì business code mutable, trừ khi yêu cầu nghiệp vụ khác và có kế hoạch ON UPDATE/transaction rõ ràng.

## 11. Business key có namespace hoặc thời gian hiệu lực

Không phải business key nào cũng chỉ là (organization_id, code).

Ví dụ số hóa đơn có quy tắc theo năm:

~~~sql
UNIQUE (organization_id, fiscal_year, invoice_number)
~~~

Hoặc một tổ chức có nhiều cửa hàng, SKU chỉ duy nhất theo cửa hàng:

~~~sql
UNIQUE (organization_id, store_id, sku)
~~~

Trong trường hợp store_id là một row thuộc organization, cần FK ghép:

~~~sql
FOREIGN KEY (organization_id, store_id)
REFERENCES stores(organization_id, id)
~~~

Không chỉ thêm store_id vào UNIQUE rồi bỏ qua việc store có cùng organization hay không.

### 11.1. Tìm hiểu business rule trước khi chọn index

Một câu hỏi thường quan trọng hơn annotation:

> “Có được phép hai tổ chức cùng có số đơn SO-001 không? Có được phép hai cửa hàng của cùng tổ chức dùng chung SKU không? Khi xóa mềm, mã có được tái sử dụng không?”

Câu trả lời xác định UNIQUE scope. Java @Column(unique=true) trên customer_code thường sai nếu tính duy nhất chỉ theo organization.

### 11.2. Khóa nghiệp vụ trong API

Endpoint có thể là:

~~~text
GET /organizations/7/orders/SO-001
~~~

Ở đây SO-001 là business key **trong organization 7**. Không query chỉ:

~~~sql
SELECT * FROM purchase_orders WHERE order_number = 'SO-001';
~~~

mà phải dùng:

~~~sql
SELECT *
FROM purchase_orders
WHERE organization_id = 7
  AND order_number = 'SO-001';
~~~

Server vẫn phải xác minh người dùng được phép truy cập organization 7; organization ID trong URL không tự cấp quyền.

## 12. Primary key và public identifier không nhất thiết giống nhau

Có thể giữ primary key BIGINT internal và thêm public_id UUID:

~~~sql
ALTER TABLE purchase_orders
ADD COLUMN public_id UUID;
~~~

Sau khi backfill, đặt NOT NULL/UNIQUE theo quy trình migration. Khi đó:

- id: ID tối ưu cho FK/nội bộ.
- public_id: ID xuất hiện trong public API, khó đoán hơn auto-increment.
- organization_id: scope được authorization kiểm tra.
- order_number: business key hiển thị, có thể theo quy tắc số đơn.

### 12.1. UUID khó đoán không phải authorization

~~~text
GET /orders/550e8400-e29b-41d4-a716-446655440000
~~~

Nếu user tổ chức A có public UUID của Order thuộc tổ chức B, endpoint vẫn phải từ chối. ID khó đoán chỉ giảm khả năng enumeration trong một số ngữ cảnh, không thay thế kiểm soát truy cập.

### 12.2. UNIQUE(public_id) hay UNIQUE(org_id,public_id)?

Nếu public_id được thiết kế **duy nhất toàn hệ thống**, UNIQUE(public_id) là hợp lý. Nếu public_id chỉ duy nhất trong organization, cần UNIQUE(organization_id,public_id) và API phải mang organization scope.

Không tự suy luận một UUID có 128 bit chắc chắn “không bao giờ trùng”; ràng buộc UNIQUE vẫn hữu ích cho tính toàn vẹn.

## 13. Entity mapping với global surrogate primary key

JPA Customer:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uq_customers_org_code",
            columnNames = {"organization_id", "customer_code"}
        ),
        @UniqueConstraint(
            name = "uq_customers_org_id",
            columnNames = {"organization_id", "id"}
        )
    }
)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "organization_id",
        nullable = false,
        updatable = false
    )
    private Long organizationId;

    @Column(
        name = "customer_code",
        nullable = false,
        length = 50
    )
    private String customerCode;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    protected Customer() {}

    public Customer(Long organizationId, String code, String name) {
        this.organizationId = organizationId;
        this.customerCode = code;
        this.displayName = name;
    }

    public Long getId() { return id; }
    public Long getOrganizationId() { return organizationId; }
    public String getCustomerCode() { return customerCode; }
}
~~~

Ở đây tổ chức được gán khi entity được tạo, không có public setter đổi organizationId. updatable=false là chỉ dẫn cho SQL UPDATE của Hibernate, **không phải** ràng buộc bất biến tuyệt đối cho mọi native SQL/DB writer; bảo vệ bằng domain/service, FK và database policy.

### 13.1. Không dựa vào @UniqueConstraint để tự tạo DDL ở production

Khi migration tool sở hữu schema và Hibernate chạy validate, annotation @UniqueConstraint **không tự thêm constraint** vào database. Cần migration SQL tương ứng. Entity metadata và DDL phải nhất quán, nhưng có thể cần DB-specific index không biểu diễn hết bằng annotation.

### 13.2. Equality của entity global ID

Không sử dụng cả object graph, collections hoặc mutable business fields trong equals/hashCode do Lombok @Data tạo tự động. ID được generate sau persist cũng có thể làm hashCode thay đổi nếu dùng naïve. Chọn chiến lược equals/hashCode nhất quán với Hibernate proxy và lifecycle của entity, hoặc không cần override nếu use case không đòi entity equality dựa trên ID.

Việc hai Customer của hai organizations cùng customer_code không làm chúng bằng nhau theo entity identity.

## 14. Mapping Order–Customer bằng composite FK trong Hibernate

Ta muốn hai cột:

~~~text
purchase_orders.organization_id
purchase_orders.customer_id
~~~

cùng tham gia FK tới:

~~~text
customers.organization_id
customers.id
~~~

Một cách mapping rõ ràng với global surrogate IDs là để **scalar fields sở hữu việc ghi FK** và association chỉ dùng để đọc/điều hướng:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "organization_id",
        nullable = false,
        updatable = false
    )
    private Long organizationId;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumns({
        @JoinColumn(
            name = "organization_id",
            referencedColumnName = "organization_id",
            insertable = false,
            updatable = false
        ),
        @JoinColumn(
            name = "customer_id",
            referencedColumnName = "id",
            insertable = false,
            updatable = false
        )
    })
    private Customer customer;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(
            Long organizationId,
            Customer customer,
            String orderNumber,
            BigDecimal totalAmount) {

        if (!Objects.equals(
                organizationId, customer.getOrganizationId())) {
            throw new IllegalArgumentException(
                "Khách hàng không thuộc cùng tổ chức");
        }
        if (customer.getId() == null) {
            throw new IllegalArgumentException(
                "Customer cần có ID trước khi tạo Order");
        }

        this.organizationId = organizationId;
        this.customerId = customer.getId();
        this.customer = customer;
        this.orderNumber = orderNumber;
        this.totalAmount = totalAmount;
        this.status = "DRAFT";
        this.createdAt = Instant.now();
    }

    public Long getId() { return id; }
    public Long getOrganizationId() { return organizationId; }
    public Long getCustomerId() { return customerId; }
    public Customer getCustomer() { return customer; }
}
~~~

Đây là **một hướng mapping Hibernate** cho association tới tổ hợp cột được UNIQUE ở parent. Phải kiểm chứng trên Hibernate version/dialect mục tiêu, vì referenced non-primary unique keys và composite association có các chi tiết metadata quan trọng. Nhớ rằng SQL migration phải thực sự tạo UNIQUE(organization_id,id).

### 14.1. Vì sao insertable=false, updatable=false?

Hai cột FK đã được scalar fields organizationId và customerId ánh xạ. Nếu association cũng cố ghi cùng column, Hibernate có thể báo duplicate column mapping hoặc khó quyết định nguồn giá trị.

Ở đây:

- organizationId, customerId là nguồn ghi.
- customer là quan hệ đọc bằng đúng cặp cột.
- Constructor/domain method gán scalar và association nhất quán.
- Composite FK ở DB là tuyến bảo vệ cuối.

Không hiểu lầm insertable=false/updatable=false là association “không có quan hệ”; Hibernate vẫn có thể load Customer theo join metadata.

### 14.2. Nguồn ghi duy nhất cho mỗi cột

Một cách mapping khác có thể để association sở hữu việc ghi một hoặc nhiều cột FK và scalar organizationId ở read-only mode. Không trộn hai phong cách trong cùng entity mà không xác định nguồn ghi, lifecycle và khả năng sửa customer.

### 14.3. Thay Customer trong cùng organization

Một business method có thể:

~~~java
public void changeCustomer(Customer newCustomer) {
    if (!Objects.equals(
            organizationId, newCustomer.getOrganizationId())) {
        throw new IllegalArgumentException(
            "Không thể gán khách khác tổ chức");
    }
    if (newCustomer.getId() == null) {
        throw new IllegalArgumentException("Customer chưa có ID");
    }
    this.customerId = newCustomer.getId();
    this.customer = newCustomer;
}
~~~

Điều này chỉ hợp lệ nếu nghiệp vụ cho phép chuyển Customer trên đơn hàng; với hóa đơn đã phát hành hoặc đơn hàng đã giao, có thể phải cấm thay đổi để bảo toàn chứng từ.

### 14.4. Nếu dùng @ManyToOne chỉ theo customer_id

~~~java
@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

Mapping này **không tự thực thi** điều kiện cùng organization. Dù DB có composite FK độc lập, Hibernate vẫn có thể load association theo ID và không thể hiện scope trong metadata. Hãy giữ mapping và DDL thống nhất để tránh hành vi load ngoài ý muốn; đặc biệt phải kiểm thử lazy loading.

## 15. Mapping OrderItem cùng tổ chức

Theo cùng nguyên tắc:

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "organization_id",
        nullable = false,
        updatable = false
    )
    private Long organizationId;

    @Column(name = "order_id", nullable = false)
    private Long orderId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumns({
        @JoinColumn(
            name = "organization_id",
            referencedColumnName = "organization_id",
            insertable = false,
            updatable = false
        ),
        @JoinColumn(
            name = "order_id",
            referencedColumnName = "id",
            insertable = false,
            updatable = false
        )
    })
    private PurchaseOrder order;

    @Column(name = "line_number", nullable = false)
    private int lineNumber;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderItem() {}
}
~~~

Một helper khi tạo Item phải sao chép organizationId từ **Order đã được xác minh**:

~~~java
public static OrderItem forOrder(
        PurchaseOrder order,
        int lineNumber,
        String sku,
        int quantity) {
    if (order.getId() == null) {
        throw new IllegalArgumentException(
            "Cần ID của Order trước khi tạo Item");
    }
    OrderItem item = new OrderItem();
    item.organizationId = order.getOrganizationId();
    item.orderId = order.getId();
    item.order = order;
    item.lineNumber = lineNumber;
    item.sku = sku;
    item.quantity = quantity;
    return item;
}
~~~

Ví dụ này giả định Order đã có ID. Nếu dùng cascade persist với Order còn new và ID chưa cấp, chọn một mapping có association sở hữu FK hoặc dùng composite ID/@MapsId thích hợp; không copy null orderId rồi kỳ vọng JPA tự đồng bộ scalar.

### 15.1. OrderItem không được đổi organization tùy tiện

Nếu Item chuyển sang Order khác trong cùng tổ chức, kiểm tra scope và invariant. Nếu Order đích thuộc organization khác, đây là một **di chuyển cross-organization** cần workflow riêng hoặc phải bị từ chối. Database composite FK đảm bảo không thể chuyển nhầm chỉ bằng cách sửa orderId và giữ organizationId cũ.

### 15.2. Cascade không thay foreign key

CascadeType.PERSIST/REMOVE/MERGE điều khiển lifecycle ORM, **không thay thế composite FK** ở database. Một cascade INSERT vẫn phải tuân thủ organization constraint. CascadeType.ALL trên mọi association có thể gây xóa hoặc merge dữ liệu ngoài aggregate intended ownership.

## 16. JPA @EmbeddedId cho composite primary key

Nếu chọn PK (organization_id, local_id), JPA cung cấp @EmbeddedId.

### 16.1. Lớp khóa

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

@Embeddable
public class OrderKey implements Serializable {
    @Column(name = "organization_id", nullable = false)
    private Long organizationId;

    @Column(name = "local_id", nullable = false)
    private UUID localId;

    protected OrderKey() {}

    public OrderKey(Long organizationId, UUID localId) {
        this.organizationId = Objects.requireNonNull(organizationId);
        this.localId = Objects.requireNonNull(localId);
    }

    public Long getOrganizationId() { return organizationId; }
    public UUID getLocalId() { return localId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderKey that)) return false;
        return Objects.equals(organizationId, that.organizationId)
            && Objects.equals(localId, that.localId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(organizationId, localId);
    }
}
~~~

Lớp @Embeddable key cần quy tắc equality/hashCode dựa trên **tất cả thành phần khóa**, và các thành phần phải ổn định trong lifecycle của entity.

### 16.2. Entity dùng @EmbeddedId

~~~java
@Entity
@Table(name = "purchase_orders_composite")
public class CompositeOrder {
    @EmbeddedId
    private OrderKey id;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    protected CompositeOrder() {}

    public CompositeOrder(
            Long organizationId,
            String orderNumber) {
        this.id = new OrderKey(
            organizationId, UUID.randomUUID());
        this.orderNumber = orderNumber;
        this.status = "DRAFT";
    }

    public OrderKey getId() { return id; }
}
~~~

Repository:

~~~java
public interface CompositeOrderRepository
        extends JpaRepository<CompositeOrder, OrderKey> {
}
~~~

Tìm theo ID:

~~~java
OrderKey key = new OrderKey(
    authenticatedOrganizationId, localOrderId);

CompositeOrder order = repository.findById(key)
    .orElseThrow();
~~~

Điểm quan trọng: composite key chứa organization ID về mặt định danh, nhưng application **vẫn phải xác minh authenticatedOrganizationId** thuộc phạm vi user có quyền. Nếu client tự gửi một organizationId khác rồi code tin ngay, composite ID không cứu được lỗi authorization.

### 16.3. Không thay đổi @EmbeddedId sau persist

Nếu id đã là (7, UUID-A), đừng sửa organizationId thành 8 để “chuyển Order sang tổ chức khác”. Hibernate identity map, FK và database PK đều được xây trên khóa ban đầu. Một chuyển đổi ownership phải là nghiệp vụ được kiểm soát, thường cần tạo record mới, migration có kiểm soát hoặc workflow liên hệ lịch sử.

## 17. @IdClass và @MapsId — khi nào cân nhắc?

JPA có nhiều cách biểu diễn composite key:

| Kỹ thuật | Ý nghĩa | Điểm cần chú ý |
|---|---|---|
| @EmbeddedId | Một value object đại diện toàn bộ primary key | Repository ID type rõ; equality trong embeddable |
| @IdClass | Nhiều @Id fields trên entity + class key song song | Tên và kiểu fields phải khớp key class |
| @MapsId | Association đóng góp một phần hoặc toàn bộ ID | Shared PK/derived ID; quản lý insert/order/cascade cẩn thận |
| Scalar FK + @JoinColumns read-only | Composite association nhưng root PK vẫn đơn cột | Cần xác định nguồn ghi cột và đồng bộ scalar/reference |

### 17.1. @IdClass

Với composite PK (organizationId, localId), một entity có thể khai báo:

~~~java
@Entity
@IdClass(OrderId.class)
class Order {
    @Id
    private Long organizationId;

    @Id
    private UUID localId;
}
~~~

OrderId phải đáp ứng quy tắc JPA ID class, có constructor phù hợp, Serializable và equals/hashCode; tên/kiểu thuộc tính khớp mapping. Đây là **mẫu rút gọn** nhằm so sánh, không phải class hoàn chỉnh.

### 17.2. @MapsId

@MapsId phù hợp cho derived identifiers, ví dụ một child PK chứa organization ID và order ID của parent. Khi dùng composite join và @MapsId, phải thống nhất thứ tự @JoinColumns, referencedColumnName, field trong embeddable key và cascade state.

Không tự kết hợp @EmbeddedId + @MapsId + nhiều writable mappings trên cùng cột nếu chưa có integration test. Một mapping chạy được ở bootstrap chưa bảo đảm INSERT/UPDATE/association traversal đúng trên mọi use case.

### 17.3. Khi nào không nên cố dùng composite PK?

Nếu hệ thống có nhiều entities và tooling/ORM dễ vận hành hơn với global surrogate id, giữ PK đơn cột rồi thêm UNIQUE(organization_id,id) và composite FKs có thể đạt same-org DB integrity với mapping root đơn giản hơn.

Đừng thay PK toàn bộ hệ thống chỉ vì muốn mọi ID nhìn thấy tenant ID; hãy cân nhắc chi phí migration, indexes, API, cache và quan hệ.

## 18. Thiết kế Membership: quan hệ intentionally giữa user global và organization

Một user có thể tham gia nhiều organizations. Quan hệ này **không phải lỗi cross-organization**; nó là cấu trúc phân quyền có chủ đích.

~~~sql
CREATE TABLE app_users (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE
);

CREATE TABLE organization_memberships (
    organization_id BIGINT NOT NULL
        REFERENCES organizations(id),
    user_id BIGINT NOT NULL
        REFERENCES app_users(id),
    role VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (organization_id, user_id)
);
~~~

Primary key ghép của Membership có ý nghĩa nghiệp vụ: mỗi cặp organization/user có tối đa một membership (nếu domain không quản lý nhiều nhiệm kỳ/historical records trong cùng bảng).

### 18.1. Không xem Membership như @ManyToMany “thuần”

Membership có role, status, joinedAt, invitedBy, approval policy. Vì có thuộc tính và lifecycle riêng, thường nên tạo **association entity OrganizationMembership** thay vì @ManyToMany đơn giản.

### 18.2. Kiểm tra membership ở service

~~~java
boolean allowed = membershipRepository
    .existsByOrganizationIdAndUserIdAndStatus(
        selectedOrganizationId,
        authenticatedUserId,
        "ACTIVE"
    );

if (!allowed) {
    throw new AccessDeniedException(
        "Không có quyền với tổ chức đã chọn");
}
~~~

Trong production cần role-based permissions, trạng thái revoked/invited, cache invalidation, session revocation và transaction timing. Kiểm tra membership phải dựa trên authenticatedUserId từ auth system, không từ userId do client tùy chọn.

### 18.3. Composite PK Membership thể hiện điều gì?

(organization_id,user_id) là khóa nghiệp vụ hợp lý nếu membership không có identity độc lập cần giữ qua lịch sử. Nếu mỗi lần join/leave tạo một membership event riêng, có thể dùng id surrogate và unique partial cho membership active; key design phải theo domain.

## 19. Tài nguyên global và tài nguyên organization-owned

Không phải mọi bảng đều cần organization_id.

### 19.1. Global catalog

~~~sql
CREATE TABLE currencies (
    code CHAR(3) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL
);
~~~

PurchaseOrder có currency_code tham chiếu currencies(code). Đây là FK global được thiết kế để nhiều organizations dùng cùng một currency.

### 19.2. Organization-owned product

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(id),
    sku VARCHAR(80) NOT NULL,
    UNIQUE (organization_id, sku),
    UNIQUE (organization_id, id)
);
~~~

OrderItem liên kết tới Product cần composite FK (organization_id,product_id) nếu sản phẩm phải thuộc cùng tổ chức.

### 19.3. Shared data theo hợp đồng

Nếu một Product có thể được dùng chung giữa nhiều organizations, không cho phép một bảng con tùy ý trỏ sang Product.organization_id khác chỉ vì “đôi khi cần chia sẻ”. Hãy biểu diễn quan hệ chia sẻ rõ:

~~~text
GlobalProduct
  -> OrganizationProductAccess(organization_id, product_id, role/validity)
  -> OrganizationOrderItem references authorized product
~~~

Có thể dùng global catalog gốc + organization-specific mapping/price/visibility. Foreign key đến global Product bảo đảm tồn tại, còn quyền mua/bán theo organization phải có policy bổ sung được thực thi ở service/database.

### 19.4. Cross-organization transfers

Một chuyển hàng từ organization 7 tới 8 là nghiệp vụ **giữa hai bên**, không phải vô tình gán StockMovement của bên 7 vào Warehouse bên 8. Nên dùng TransferRequest/TransferLine có sourceOrganizationId và destinationOrganizationId tường minh, với permission và transaction/saga phù hợp.

## 20. Repository API: luôn mang phạm vi organization

Một repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByIdAndOrganizationId(
        Long id,
        Long organizationId
    );

    Optional<PurchaseOrder>
        findByOrganizationIdAndOrderNumber(
            Long organizationId,
            String orderNumber
        );

    Page<PurchaseOrder>
        findByOrganizationIdAndStatus(
            Long organizationId,
            String status,
            Pageable pageable
        );
}
~~~

### 20.1. Vì sao findById(id) chưa đủ?

Nếu ID là global PK, findById(id) có thể tìm được entity của bất kỳ organization nào. Dù ID không bị trùng, repository vẫn không xác minh caller có quyền đọc.

Nên có service:

~~~java
@Transactional(readOnly = true)
public OrderRow getOrder(
        Long orderId,
        Long selectedOrgId,
        AuthenticatedUser actor) {

    authorization.requireMembership(actor, selectedOrgId);

    PurchaseOrder order = orders
        .findByIdAndOrganizationId(orderId, selectedOrgId)
        .orElseThrow(OrderNotFoundException::new);

    return OrderRow.from(order);
}
~~~

Các class/permissions/DTO helper phải được project định nghĩa. Ý chính là **tổ chức đã được xác minh được truyền từ application boundary tới query**.

### 20.2. Không tin organization ID của request body

Sai:

~~~java
PurchaseOrder order = orders.findById(request.orderId())
    .orElseThrow();
order.setCustomerId(request.customerId());
~~~

Đúng hơn:

1. Xác định user từ authentication.
2. Xác minh user thuộc organization được chọn và có quyền thực hiện thao tác.
3. Tải Order bằng (id, organization_id).
4. Tải Customer bằng (id, organization_id).
5. Kiểm tra business rules rồi sửa managed Order.
6. DB composite FK chặn mọi tham chiếu khác tổ chức còn sót.

### 20.3. findByIdAndOrganizationId vẫn không thay thế mọi authorization

Một nhân viên organization 7 có thể chỉ được đọc Orders trong department mà họ quản lý. Predicate organization là tầng đầu, cần bổ sung role/owner/department policy theo business.

## 21. Application service tạo Order an toàn

Một ví dụ:

~~~java
@Service
public class PlaceOrderService {
    private final CustomerRepository customers;
    private final PurchaseOrderRepository orders;
    private final OrganizationAuthorization authorization;

    public PlaceOrderService(
            CustomerRepository customers,
            PurchaseOrderRepository orders,
            OrganizationAuthorization authorization) {
        this.customers = customers;
        this.orders = orders;
        this.authorization = authorization;
    }

    @Transactional
    public Long create(
            AuthenticatedUser actor,
            Long requestedOrgId,
            CreateOrderCommand command) {

        authorization.requirePermission(
            actor, requestedOrgId, "ORDER_CREATE");

        Customer customer = customers
            .findByIdAndOrganizationId(
                command.customerId(), requestedOrgId)
            .orElseThrow(CustomerNotFoundException::new);

        PurchaseOrder order = new PurchaseOrder(
            requestedOrgId,
            customer,
            command.orderNumber(),
            command.totalAmount()
        );

        return orders.save(order).getId();
    }
}
~~~

Những DTO, exception, authorization service và constructors là ví dụ khung, không phải API có sẵn của Spring. Transaction bao cả thao tác kiểm tra/tạo; database UNIQUE/FK vẫn kiểm tra cuối cùng lúc flush/commit.

### 21.1. Không tạo Customer stub từ client ID rồi gán thẳng

Tránh:

~~~java
Customer stub = new Customer();
stub.setId(command.customerId());
order.setCustomer(stub);
~~~

Bạn chưa xác minh Customer thuộc organization yêu cầu. Gắn entity detached/proxy cũng có thể dẫn tới behavior merge/cascade khó đoán. Tải Customer trong organization scope và kiểm tra quyền trước.

### 21.2. Không dựa vào một lần SELECT để chống thay đổi đồng thời

Nếu Customer chuyển trạng thái DELETED/SUSPENDED giữa lúc service kiểm tra và lúc commit, cần xác định business consistency:

- Chỉ cần snapshot tại thời điểm chọn?
- Phải chặn tạo Order nếu Customer bị khóa đồng thời?
- Cần optimistic locking, pessimistic row lock hoặc conditional SQL?

Composite FK chỉ bảo đảm ownership/existence, không khóa business status. Quy tắc nghiệp vụ cần transaction/locking thích hợp.

### 21.3. Response sau save không có nghĩa commit sớm

Khi service đang trong @Transactional, repository.save không commit độc lập. Unique/FK exception có thể nổ tại flush/commit. Không gửi HTTP/payment side effect dựa vào việc save đã trả ID; dùng after-commit hoặc transactional outbox khi cần tích hợp ngoài DB.

## 22. Đọc theo business key đúng scope

Một mã đơn hàng SO-001 có thể tồn tại ở organization 7 và 8. Repository:

~~~java
Optional<PurchaseOrder>
    findByOrganizationIdAndOrderNumber(
        Long organizationId,
        String orderNumber
    );
~~~

Đây là query đúng về **tính duy nhất theo tổ chức**. Không dùng:

~~~java
Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
~~~

nếu database cho phép cùng orderNumber trên nhiều organizations; Spring Data có thể ném IncorrectResultSizeDataAccessException hoặc trả kết quả không đáp ứng hợp đồng kỳ vọng nếu method/query được viết thiếu.

### 22.1. Natural ID của Hibernate

Hibernate có @NaturalId để đánh dấu business key ổn định:

~~~java
@NaturalId
@Column(name = "organization_id", updatable = false)
private Long organizationId;

@NaturalId
@Column(name = "customer_code", updatable = false)
private String customerCode;
~~~

Khi cả hai field cùng là natural-id attributes, natural key gồm organizationId và customerCode. Có thể dùng API Session.byNaturalId(...) theo cách được Hibernate version hỗ trợ, nhưng vẫn cần xác minh organization authorization và database UNIQUE thực tế. Natural ID cache không phải cơ chế quyền truy cập.

### 22.2. Mutable natural key

Nếu customerCode được phép đổi, khai báo immutable natural ID là sai domain. Hibernate có tùy chọn @NaturalId(mutable=true) và synchronization/cache semantics riêng, nhưng thường một repository query theo (organizationId, code) với surrogate PK ổn định dễ vận hành hơn.

### 22.3. Business key có thể là dữ liệu nhạy cảm

Không nên mặc định dùng email/số điện thoại làm global primary key. Dữ liệu cá nhân có thể thay đổi, bị ẩn, bị xóa, hoặc trùng trong các organizations theo business model. Dùng ID ổn định và UNIQUE theo phạm vi thật sự nếu cần.

## 23. JOIN trong HQL: association mapping đúng vẫn cần scope rõ

Một query:

~~~hql
select o
from PurchaseOrder o
join fetch o.customer
where o.organizationId = :organizationId
  and o.id = :orderId
~~~

Nếu association được map bằng cặp (organization_id,customer_id), SQL JOIN sẽ dựa trên metadata đó. Query vẫn cần điều kiện organizationId để giới hạn root results.

### 23.1. Query join thủ công theo ID mà quên org

Ví dụ HQL:

~~~hql
select o.id, c.displayName
from PurchaseOrder o, Customer c
where o.customerId = c.id
~~~

Nếu Customer ID là global unique và DB composite FK đúng, c.id trùng về lý thuyết sẽ cùng org khi dữ liệu hợp lệ. Nhưng cách query này **không thể hiện** business boundary; nếu schema/mapping khác hoặc dữ liệu legacy chưa ràng buộc FK, nó có thể gây cross-scope result. Ưu tiên join qua association đúng metadata và filter root theo org.

### 23.2. Join trên business code cần đầy đủ namespace

Sai:

~~~sql
SELECT o.id, c.id
FROM purchase_orders o
JOIN customers c
  ON c.customer_code = o.external_customer_code;
~~~

Nếu nhiều organizations đều có C-001, câu JOIN có thể nhân bản hoặc ghép Order của organization 7 với Customer của 8.

Đúng:

~~~sql
SELECT o.id, c.id
FROM purchase_orders o
JOIN customers c
  ON c.organization_id = o.organization_id
 AND c.customer_code = o.external_customer_code
WHERE o.organization_id = :organizationId;
~~~

Đây là lỗi phổ biến khi import dữ liệu từ hệ thống cũ dùng mã nghiệp vụ nhưng quên namespace.

### 23.3. EntityGraph/fetch join không cấp quyền

Fetch join hoặc @EntityGraph chỉ thay đổi fetch plan, không biến một query thiếu tenant predicate thành an toàn. Đồng thời fetch collection to-many với pagination vẫn có rủi ro row multiplication; tách page root IDs và fetch associations theo kế hoạch có scope.

## 24. Bảo mật IDOR: object ID không chứng minh quyền

IDOR (Insecure Direct Object Reference) xảy ra khi ứng dụng cho phép user truy cập tài nguyên bằng ID mà không kiểm tra quyền tương ứng.

Ví dụ:

~~~text
GET /api/orders/901
PATCH /api/orders/901
DELETE /api/orders/901
~~~

Nếu các endpoint chỉ gọi findById(901) rồi xử lý, user thuộc organization khác có thể đọc/sửa tài nguyên ngoài scope khi biết ID.

### 24.1. Xác minh ở boundary

Hướng an toàn:

~~~text
Auth principal
  -> Verify membership + permission in selected organization
  -> Scoped repository query (organization_id + id)
  -> Business invariants
  -> Database constraints
  -> DTO response
~~~

### 24.2. Status 404 hay 403?

Một API có thể trả 404 cho resource ngoài organization để hạn chế tiết lộ sự tồn tại; nơi khác có thể dùng 403 khi phạm vi đã được xác minh và yêu cầu rõ quyền. Điều quan trọng là **không tiết lộ dữ liệu/metadata từ organization khác** trong thông báo lỗi, log hiển thị công khai hoặc timing side channel dễ khai thác.

### 24.3. ID toàn cục không làm query scoped trở nên dư

Dù id = 901 chỉ xuất hiện đúng một lần trên toàn database, vẫn phải xác minh organization_id = trustedOrgId. Uniqueness và authorization là hai thuộc tính khác nhau.

## 25. Hibernate Filter và tenant discriminator không thay composite FK

Hibernate có khả năng filter:

~~~java
session.enableFilter("organizationScope")
    .setParameter("organizationId", trustedOrgId);
~~~

hoặc multi-tenancy mechanism được hỗ trợ theo phiên bản. Những cơ chế này hữu ích ở **đường tải dữ liệu**, nhưng không thay toàn vẹn quan hệ:

- Filter có thể chưa bật ở một Session.
- Entity đã managed trong first-level cache có thể được trả mà không có SQL.
- Direct find/getReference hoặc association load có semantics khác query list theo version.
- Native SQL/ETL có thể bypass Hibernate filter.
- Bulk DML không mặc định áp dụng mọi filter.
- Chỉ lọc Order ở query không bảo đảm Order.customerId trỏ đến Customer cùng organization trong DB.

### 25.1. Hai tầng bổ sung nhau

**Composite FK** bảo đảm integrity ở database cho mọi writer.

**Tenant-scoped query/authorization** bảo đảm caller chỉ thấy và thay đổi dữ liệu được phép.

Không nên chọn một trong hai rồi xem như đủ toàn bộ bài toán.

### 25.2. Chuyển organization trong cùng Session

Nếu một Session đã load Customer organization 7, rồi application đổi filter sang organization 8, managed Customer trước đó không tự biến mất. Đừng tái sử dụng một persistence context giữa các organization scopes có quyền khác nhau.

Tốt hơn là chọn organization một lần ở transaction boundary, dùng Session/EntityManager riêng khi đổi organization, và trả DTO thay vì truyền managed entities giữa scopes.

### 25.3. Native SQL không tự nhận filter

~~~sql
SELECT *
FROM purchase_orders
WHERE id = :id;
~~~

Câu SQL này phải có organization predicate hoặc chịu DB RLS phù hợp nếu được dùng để truy cập scoped data. Session filter không làm một native SQL tự đổi thành WHERE id=:id AND organization_id=:trustedOrgId.

## 26. Database row-level security là lớp bổ sung

PostgreSQL RLS có thể áp dụng giới hạn hàng ở database theo role/session context.

Ví dụ minh họa:

~~~sql
ALTER TABLE purchase_orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_organization_policy
ON purchase_orders
USING (
    organization_id =
      current_setting('app.organization_id', true)::BIGINT
)
WITH CHECK (
    organization_id =
      current_setting('app.organization_id', true)::BIGINT
);
~~~

USING điều khiển hàng có thể được nhìn thấy hoặc tác động theo policy; WITH CHECK ràng buộc hàng mới/updated theo semantics PostgreSQL. Khi app không thiết lập setting, current_setting(...,true) trả NULL và so sánh thường không đúng, giúp fail closed với policy đơn giản này. Phải xem kỹ cách policy kết hợp, table owner, privileges và DB version.

### 26.1. Thiết lập organization ID ở transaction scope

Có thể dùng:

~~~sql
SELECT set_config(
    'app.organization_id',
    :trustedOrganizationIdText,
    true
);
~~~

Tham số thứ ba true biểu thị local transaction setting trong PostgreSQL. Thực tế phải gọi trong transaction được quản lý rõ, trên **đúng connection** dùng cho queries, và từ organization ID đã xác minh. Không lưu tenant setting toàn connection rồi trả connection về pool mà không dọn; đó là nguy cơ rò rỉ scope.

### 26.2. RLS không tự giải quyết managed entities

Nếu Hibernate đã có entity trong L1, một lần find tiếp theo có thể không phát SQL; RLS không được đánh giá lại. Vì vậy tách persistence context theo security scope vẫn quan trọng khi dùng RLS.

### 26.3. Vai trò và bypass

PostgreSQL superuser, role có BYPASSRLS và table owner trong một số cấu hình có thể bypass RLS. FORCE ROW LEVEL SECURITY có thể thay đổi hành vi với owner; phải test với database role giống application runtime, không chỉ dùng superuser trong development.

RLS là defense-in-depth hữu ích, nhưng không thay database FK/UNIQUE, application authorization hoặc việc quản lý transaction connection context.

## 27. Soft delete và khóa nghiệp vụ có thể tái sử dụng

Giả sử Customer C-001 bị soft-delete và organization 7 được phép tạo Customer mới cùng mã C-001.

Một UNIQUE toàn phần:

~~~sql
UNIQUE (organization_id, customer_code)
~~~

sẽ chặn việc tái sử dụng vì row deleted vẫn tồn tại. Cần xác định business semantics:

- Mã là định danh vĩnh viễn, không bao giờ được tái sử dụng?
- Hay mã chỉ cần unique trong tập active?

### 27.1. Partial unique index theo active rows

PostgreSQL hỗ trợ:

~~~sql
CREATE UNIQUE INDEX uq_active_customer_code_per_org
ON customers(organization_id, customer_code)
WHERE deleted_at IS NULL;
~~~

Nếu chọn policy này, phải **loại bỏ hoặc điều chỉnh UNIQUE toàn phần trước đó** qua migration được kiểm soát; nếu vẫn giữ cả hai thì partial index không giúp tái sử dụng code.

### 27.2. Partial UNIQUE không thể thay referenced key cho FK ghép

Một foreign key cần tham chiếu một key hợp lệ theo database rules. Với PostgreSQL, **partial unique index** chỉ đảm bảo uniqueness trên một tập con rows và không thể dùng làm target thay thế thông thường cho foreign key (organization_id,id).

Giữ UNIQUE(organization_id,id) đầy đủ để composite FK tham chiếu, độc lập với partial unique index cho business key active.

### 27.3. Restore conflict

Giả sử:

~~~text
Customer 21: org 7, C-001, deleted
Customer 45: org 7, C-001, active
~~~

Nếu restore Customer 21 bằng cách đặt deleted_at=NULL, partial unique index sẽ từ chối vì Customer 45 đã dùng mã đó. Workflow restore cần:

- Phát hiện conflict.
- Quyết định đổi customer_code, hợp nhất hoặc từ chối restore.
- Dùng transaction/constraint để ngăn race.

Không chỉ tắt soft-delete filter rồi set deletedAt=null mà bỏ qua uniqueness semantics.

### 27.4. Soft delete không xóa foreign keys

Order có thể vẫn tham chiếu Customer đã deleted; database FK vẫn hợp lệ. Nếu không cho phép tạo Order mới với deleted Customer, cần app query/status checks hoặc mô hình DB bổ sung. Soft delete không đồng nghĩa referential deletion.

## 28. Khi organization_id có thể thay đổi?

Nhiều dự án vô tình cho phép:

~~~java
customer.setOrganizationId(otherOrganizationId);
~~~

Đây không phải thay đổi field thông thường. Organization ownership ảnh hưởng:

- FK của Orders/Items/Shipments.
- Business key uniqueness namespace.
- Access control và cache keys.
- Audit/financial records.
- Reports và dữ liệu phát hành trước đó.

### 28.1. Nên coi ownership là immutable

Thông thường một record được tạo thuộc organization nào thì owner không thay đổi, trừ khi có nghiệp vụ transfer rõ. Không public setter cho organizationId; giữ @Column(updatable=false) theo mapping hoặc dùng composite PK có organizationId.

### 28.2. Chuyển dữ liệu giữa tổ chức

Nếu cần chuyển một Customer từ organization 7 sang 8, các lựa chọn:

1. Tạo Customer mới ở org 8 rồi migrate/liên kết dữ liệu được phép.
2. Tạo transfer record có source/destination, audit và approval.
3. Nếu cần move vật lý, thiết kế migration/transaction quản lý mọi FKs và uniqueness, có kiểm soát lock, cache và downstream integrations.

Không chỉ UPDATE organization_id rồi hy vọng các children tự chuyển theo; composite FKs có thể chặn chính vì nó bảo vệ integrity.

### 28.3. Không tự bật ON UPDATE CASCADE để cho phép mọi transfer

ON UPDATE CASCADE trên composite FK có thể lan truyền organization_id xuống nhiều bảng nếu parent key đổi. Về kỹ thuật có tình huống dùng được, nhưng nó không tự kiểm tra quyền, invoices, reports hoặc side effects ở hệ thống khác. Ownership transfer là quyết định domain, không chỉ là thao tác cascade.

## 29. Concurrency: khóa nghiệp vụ, foreign key và transaction

Các constraints không thay thế transaction management.

### 29.1. Hai request tạo cùng order_number

~~~text
T1: check SO-001 không tồn tại trong org 7
T2: check SO-001 không tồn tại trong org 7
T1: INSERT -> thành công
T2: INSERT -> UNIQUE violation tại flush/commit
~~~

Đây là behavior mong muốn nếu business key phải unique. Service có thể map lỗi database thành conflict rõ ràng, retry **chỉ khi an toàn** và không tạo side effect trùng.

### 29.2. Sinh số đơn theo tổ chức

Không làm:

~~~sql
SELECT MAX(order_sequence_no) + 1
FROM purchase_orders
WHERE organization_id = :orgId;
~~~

rồi INSERT mà không có serialization/locking; hai transaction có thể cùng lấy số.

Giải pháp tùy yêu cầu:

- Global DB sequence/identity nếu số không cần tăng liên tục theo org.
- Một bảng organization_counters có khóa (organization_id, counter_name), update atomic/row lock để cấp số.
- UUID/ULID làm internal/public ID, business number cấp sau.
- External numbering service có idempotency và phân tán rõ.

Không giả định generated identity luôn liên tục, không có khoảng trống; rollback và cache sequence có thể tạo gaps.

### 29.3. Optimistic locking

~~~java
@Version
private long version;
~~~

giúp phát hiện một số lost updates khi hai transaction sửa cùng entity qua Hibernate. Nó không thay FK cùng tổ chức hoặc UNIQUE(organization_id,order_number). Các cơ chế giải quyết những loại invariant khác nhau.

### 29.4. Ghi dựa trên điều kiện organization

Khi cần bulk update:

~~~hql
update PurchaseOrder o
set o.status = :status
where o.id = :id
  and o.organizationId = :orgId
~~~

Truyền orgId từ verified context, kiểm tra số rows affected. Bulk HQL có thể bypass @Version handling và entity callbacks theo cách thông thường; nếu cần optimistic check, bổ sung version predicate/increment được thiết kế rõ và đồng bộ persistence context.

## 30. Index cho truy vấn theo organization

Khi mọi query bắt đầu với organization_id, index nên phản ánh access patterns.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_org_created
ON purchase_orders(
    organization_id,
    created_at DESC,
    id DESC
);

CREATE INDEX idx_orders_org_customer
ON purchase_orders(
    organization_id,
    customer_id
);

CREATE INDEX idx_items_org_order
ON order_items(
    organization_id,
    order_id
);
~~~

Các index ở trên là ứng viên minh họa. Một UNIQUE index hiện có trên (organization_id,id) hoặc (organization_id,order_number) phục vụ những access paths tương ứng; tránh tạo duplicate indexes vô ích.

### 30.1. Tại sao organization_id thường đứng trước?

Một query thường gặp:

~~~sql
SELECT id, order_number
FROM purchase_orders
WHERE organization_id = :orgId
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Index bắt đầu bằng organization_id có thể giúp hạn chế rows trước khi sắp xếp/paginate. Hiệu quả cụ thể phụ thuộc cardinality, phân bố org lớn/nhỏ và PostgreSQL planner; cần EXPLAIN (ANALYZE, BUFFERS) trên dữ liệu đại diện.

### 30.2. Không bỏ index FK ở child

Trong PostgreSQL, FK không tự động tạo index trên **referencing columns** ở child. Nếu thường load Items theo (organization_id,order_id), index tương ứng có thể giúp JOIN và một số thao tác cập nhật/xóa parent.

### 30.3. Organization lớn và organization nhỏ

Một vài org có hàng triệu Orders trong khi đa số chỉ vài trăm. Plan/index hiệu quả cho org nhỏ chưa chắc tốt với org lớn. Cần benchmark theo phân bố thật, cập nhật database statistics và cân nhắc partition/sharding nếu có lý do rõ.

## 31. Phân vùng, sharding và nhiều database

Trong một database/shared schema, composite FK là cách trực tiếp để DB bảo đảm same-org.

### 31.1. Schema per organization

Ví dụ:

~~~text
org7.customers
org7.purchase_orders
org8.customers
org8.purchase_orders
~~~

Mỗi schema có thể dùng ID local trùng nhau, vì namespace được tách vật lý. Khi code kết nối/chọn schema, organization scope nằm trong schema context, không chỉ trong key. Vẫn phải xác minh đúng schema cho mỗi transaction/connection và không rò rỉ search_path qua connection pool.

### 31.2. Database per organization

Mỗi organization có database riêng. FK có thể enforce bên trong DB đó, nhưng không thể trực tiếp dùng một FK bình thường nối sang database khác. Khi cần liên kết cross-database có chủ đích, phải dùng reference contract/event/workflow kiểm tra consistency.

### 31.3. Sharding theo organization

Sharding có thể route mọi records một organization tới cùng shard. Cặp (organization_id, local_id) thuận lợi cho routing, nhưng routing key và primary key không phải cùng một khái niệm. Một global UUID cũng có thể dùng với organization_id làm shard key.

Cross-shard foreign keys thường không có enforcement như một database đơn. Khi đó cần thêm safeguards ở service/event/saga, audit và reconciliation; đây là trade-off kiến trúc.

### 31.4. Partitioned tables

PostgreSQL partitioning theo organization hoặc hash organization có constraint/index rules cần đối chiếu phiên bản. Một UNIQUE trên partitioned table có thể cần chứa partition key. Thiết kế PK/UNIQUE/FK phải được kiểm tra trên schema partitioning thật, không bê nguyên SQL của bảng thường mà không test.

## 32. Cache và identity trong hệ thống nhiều tổ chức

### 32.1. First-level cache

Một Hibernate Session có identity map. Nếu code load Customer 21 từ organization 7 rồi đổi một filter sang organization 8 trong **cùng Session**, Customer 21 không tự bị detach. Không dùng filter mutable để chuyển security scope của một persistence context đã chứa entities.

### 32.2. Second-level cache

Với Hibernate multi-tenancy được cấu hình đúng, cache keys/provider có thể tích hợp tenant identifier theo cơ chế của Hibernate. Nhưng nếu chỉ thêm trường organizationId và lọc bằng application/Hibernate @Filter, **không suy ra cache tự tách quyền theo organization**.

Một entity cache hit có thể tránh DB query; authorization không được phép phụ thuộc việc SQL luôn được chạy. Các rows nhạy cảm hoặc quyền thay đổi nhanh có thể không phù hợp với L2 cache.

### 32.3. Spring Cache key phải chứa scope

Sai:

~~~java
@Cacheable("orderRows")
public OrderRow getOrder(Long orderId) { ... }
~~~

nếu method có business behavior phụ thuộc active organization nhưng cache key chỉ có orderId theo cách không xác minh authorization trước khi trả cache hit.

Hướng cần thiết kế:

~~~java
@Cacheable(
    cacheNames = "orderRows",
    key = "#organizationId + ':' + #orderId"
)
public OrderRow getOrder(
        Long organizationId, Long orderId) {
    // Authorization phải được thực thi ở boundary.
}
~~~

Key chứa organization ID **vẫn không thay thế** kiểm tra membership/permission. Ngoài ra, nếu authorization logic nằm *bên trong* method được @Cacheable intercept, một cache hit có thể bỏ qua body và kiểm tra đó. Đặt auth ở lớp luôn chạy trước cache read, hoặc dùng cấu trúc access control phù hợp với cache contract.

### 32.4. Cache business key

Nếu cache Customer theo customer_code, key phải chứa organizationId và các namespace bổ sung như store/fiscal year nếu business key cần. Cache key chỉ "C-001" có thể cho dữ liệu organization 8 bị dùng khi organization 7 cùng có mã đó.

## 33. Migration từ schema đơn tổ chức sang schema nhiều tổ chức

Đây là bài toán phổ biến khi một ứng dụng ban đầu chỉ phục vụ một công ty, sau đó trở thành SaaS.

Schema cũ:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    customer_code VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id)
);
~~~

Để chuyển sang nhiều organizations, **không nên** chỉ thêm organization_id NOT NULL trong một bước rồi deploy app mới mà không backfill.

### 33.1. Giai đoạn expand

~~~sql
ALTER TABLE customers
ADD COLUMN organization_id BIGINT;

ALTER TABLE purchase_orders
ADD COLUMN organization_id BIGINT;
~~~

Lúc này dữ liệu cũ chưa có organization. Không bật NOT NULL ngay khi còn rows cần gán.

### 33.2. Backfill dữ liệu cũ

Xác định organization mặc định hoặc mapping từ hệ thống legacy:

~~~sql
UPDATE customers
SET organization_id = :legacyOrganizationId
WHERE organization_id IS NULL;

UPDATE purchase_orders o
SET organization_id = c.organization_id
FROM customers c
WHERE o.customer_id = c.id
  AND o.organization_id IS NULL;
~~~

Các tham số :legacyOrganizationId là biểu tượng cho migration/backfill job có parameter binding; SQL file migration thuần cần giá trị hoặc cách truyền phù hợp. Với bảng lớn, chia batch và theo dõi progress/locks/WAL.

### 33.3. Kiểm tra tính đúng trước khi đặt constraint

~~~sql
SELECT o.id, o.organization_id, c.organization_id
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.organization_id IS DISTINCT FROM c.organization_id;
~~~

Kết quả phải rỗng theo business invariant. Kiểm tra NULLs, orphan references và duplicate business keys theo organization.

### 33.4. Giai đoạn thêm keys/constraints

Sau khi dữ liệu đúng:

~~~sql
ALTER TABLE customers
ALTER COLUMN organization_id SET NOT NULL;

ALTER TABLE purchase_orders
ALTER COLUMN organization_id SET NOT NULL;

ALTER TABLE customers
ADD CONSTRAINT uq_customers_org_id
UNIQUE (organization_id, id);

ALTER TABLE purchase_orders
ADD CONSTRAINT fk_order_customer_same_org
FOREIGN KEY (organization_id, customer_id)
REFERENCES customers(organization_id, id);
~~~

Phải xem constraints/unique keys cũ cần giữ hay bỏ. Nếu customer_code đã UNIQUE toàn bảng, muốn cho hai org dùng cùng mã cần migration thay đổi constraint, sau khi mọi writer/reader đã có organization scope đúng.

### 33.5. Online migration và NOT VALID

Trên PostgreSQL, có thể dùng FOREIGN KEY ... NOT VALID rồi VALIDATE CONSTRAINT ở giai đoạn riêng để giảm ảnh hưởng của việc kiểm tra toàn bộ dữ liệu cũ trong một statement:

~~~sql
ALTER TABLE purchase_orders
ADD CONSTRAINT fk_order_customer_same_org
FOREIGN KEY (organization_id, customer_id)
REFERENCES customers(organization_id, id)
NOT VALID;

ALTER TABLE purchase_orders
VALIDATE CONSTRAINT fk_order_customer_same_org;
~~~

NOT VALID không có nghĩa bỏ qua mọi ghi mới: PostgreSQL vẫn enforce FK cho những writes mới phù hợp, còn dữ liệu lịch sử được xác minh khi VALIDATE. Cần có referenced UNIQUE trước; các bước này phải được phối hợp với application rollout, locks và version PostgreSQL.

Với unique index lớn, CREATE UNIQUE INDEX CONCURRENTLY có thể giảm thời gian blocking nhưng không chạy trong transaction block thông thường; migration tool phải hỗ trợ non-transactional step phù hợp. Không tự chạy online DDL trên production mà chưa xem lock/rollback plan.

### 33.6. Expand–contract qua nhiều phiên bản app

~~~mermaid
flowchart TD
    A[Schema legacy không org_id] --> B[Expand: thêm org_id nullable]
    B --> C[Backfill và app dual-compatible]
    C --> D[Chuyển queries và writes sang org scope]
    D --> E[Validate dữ liệu cùng org]
    E --> F[Thêm NOT NULL UNIQUE composite FK]
    F --> G[Contract: bỏ legacy key/policy]
~~~

Nếu app cũ vẫn ghi row mà không có organization_id, thêm NOT NULL quá sớm sẽ làm request lỗi. Lập compatibility matrix giữa app versions và schema versions; không chỉ dựa vào Hibernate ddl-auto=update để thực hiện các bước chuyển đổi.

## 34. Migration từ global ID sang composite primary key khó hơn nhiều

Thay PK(id) thành PK(organization_id,local_id) kéo theo:

- Mọi FKs đang tham chiếu id cần chuyển sang composite.
- ORM @Id/repository IDs/API/cache keys thay đổi.
- Dữ liệu legacy phải có organization_id chính xác ở mọi cấp.
- Sequences/ID generators cần thiết kế lại.
- Hệ thống khác có thể lưu old IDs.
- Các transactions đang chạy và rolling deployments cần tương thích.

Thường nên cân nhắc **giữ global PK và thêm composite UNIQUE/FKs** nếu đã có hệ sinh thái lớn phụ thuộc ID. Đổi PK chỉ khi lợi ích kiến trúc đủ lớn và có migration multi-phase được thử thật.

### 34.1. Không thay PK bằng một câu ALTER rồi dừng

~~~sql
ALTER TABLE purchase_orders
DROP CONSTRAINT purchase_orders_pkey;
~~~

Đây là thao tác phá vỡ referenced FKs và assumptions. Một migration phải giải quyết dependency graph, dữ liệu lịch sử, application code, replication, backup và rollback. Đừng lấy ví dụ SQL đơn giản này làm kế hoạch deploy.

### 34.2. Cơ chế legacy ID mapping

Khi chuyển identity scheme, có thể cần bảng ánh xạ:

~~~text
legacy_order_id -> organization_id, new_local_id
~~~

Nó giúp imports, integrations và event consumers tra cứu trong giai đoạn chuyển đổi. Cần unique constraints và retention policy; không để mapping table trở thành đường bypass authorization.

## 35. Audit, event và tích hợp ngoài cần mang organization context

Một event:

~~~json
{
  "eventId": "6feac3ce-0bbf-4bf4-bd15-897bc6f2bc90",
  "eventType": "OrderPlaced",
  "organizationId": 7,
  "orderId": 901,
  "orderNumber": "SO-001"
}
~~~

Event nên có organizationId đáng tin cậy, correlation/idempotency key và schema version theo contract thực tế. Không chỉ publish orderNumber = SO-001: consumer không biết đó là tổ chức nào.

### 35.1. Outbox cũng là organization-owned data

~~~sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    organization_id BIGINT NOT NULL,
    aggregate_type VARCHAR(60) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(20) NOT NULL
);
~~~

Nếu outbox_event tham chiếu một Order cụ thể và cần DB same-org integrity, có thể thêm FK ghép (organization_id, aggregate_id) cho một loại outbox chuyên biệt. Với polymorphic aggregate_type nhiều bảng, FK chung không thể trực tiếp tham chiếu nhiều parent tables bằng một constraint; chọn event schema/service invariants hoặc outbox tables khác theo thiết kế.

### 35.2. Consumer phải xác minh organization scope

Message broker thường không mang ORM Session/tenant filter từ producer. Consumer phải dùng organizationId trong event để thiết lập authorization/routing context đã được tin cậy theo contract, kiểm tra schema và không cho một tenant phát event giả của tenant khác qua public endpoint.

### 35.3. Idempotency theo tổ chức

Một request idempotency key như REQUEST-001 có thể được hai organizations sử dụng. Nếu uniqueness chỉ theo key sẽ gây xung đột giả:

~~~sql
UNIQUE (organization_id, idempotency_key)
~~~

nếu business cho phép trùng giữa tổ chức. Nếu một payment provider yêu cầu key global, có thể xây key từ organization ID và request key theo cách không rò rỉ thông tin.

## 36. Kiểm thử same-organization integrity bằng PostgreSQL thật

Test bằng PostgreSQL Testcontainers tốt hơn chỉ dựa vào H2 khi cần xác minh composite FKs, partial indexes và RLS.

### 36.1. Ma trận kiểm thử cốt lõi

| Tình huống | Kỳ vọng |
|---|---|
| Hai org dùng cùng customer_code | Hợp lệ nếu UNIQUE theo org |
| Cùng org dùng trùng customer_code | DB từ chối (UNIQUE) |
| Order org 7 tham chiếu Customer org 7 | Hợp lệ |
| Order org 7 tham chiếu Customer org 8 | DB từ chối (composite FK) |
| Item org 7 tham chiếu Order org 8 | DB từ chối (composite FK) |
| User org 7 gọi API Order org 8 theo ID | Service từ chối, không lộ dữ liệu |
| findById được gọi nhầm trong code | Code review/test nhận ra thiếu scope |
| Native SQL nhập row cross-org | DB từ chối |
| Bulk UPDATE thiếu org | Test phát hiện, sửa query predicate |
| Soft delete mã C-001 rồi tái sử dụng | Theo unique policy đã chọn |
| Restore deleted C-001 khi có active C-001 | Conflict được xử lý đúng |
| Cache key chỉ dùng business code | Test phát hiện lẫn dữ liệu giữa org |
| Đổi org trong cùng Session | Không được dùng managed state cũ như scope mới |
| External event OrderPlaced cùng orderNumber hai org | Consumer phân biệt rõ organization |

### 36.2. Test SQL constraint trực tiếp

~~~java
@Test
void rejectsCrossOrganizationOrderCustomer() {
    assertThrows(DataIntegrityViolationException.class, () -> {
        transactionTemplate.executeWithoutResult(status -> {
            PurchaseOrder order = new PurchaseOrder(
                organization7,
                customerOfOrganization8,
                "SO-CROSS",
                new BigDecimal("10.00")
            );
            orderRepository.saveAndFlush(order);
        });
    });
}
~~~

Lưu ý: constructor PurchaseOrder minh họa ở trên tự kiểm tra organization, nên test này **có thể fail tại domain validation trước khi DB được gọi**. Để kiểm tra composite FK thực sự, phải cố ý dùng JDBC/native INSERT cross-org trên database test hoặc một fixture mapping được kiểm soát để không bị validation ứng dụng chặn trước.

Đây là khác biệt rất quan trọng giữa:

- Test kiểm tra service từ chối đúng.
- Test kiểm tra **database** thực thi FK ngay cả khi service bị bypass.

### 36.3. Test database trực tiếp với JDBC

~~~java
@Test
void compositeForeignKeyRejectsCrossOrgReference() {
    assertThrows(DataIntegrityViolationException.class, () ->
        jdbcTemplate.update("""
            INSERT INTO purchase_orders(
                organization_id, customer_id, order_number,
                status, created_at, total_amount, version
            ) VALUES (?, ?, ?, 'DRAFT', CURRENT_TIMESTAMP, 10.00, 0)
            """,
            org7Id, customerOfOrg8Id, "SO-BAD"
        )
    );
}
~~~

Fixture customers/organizations phải đã commit và migration đầy đủ. Nếu dùng @Transactional trên test, exception SQL ở PostgreSQL có thể khiến transaction aborted; chạy từng case trong transaction độc lập hoặc cleanup đúng.

### 36.4. Test PK ghép

~~~java
OrderKey a = new OrderKey(7L, localId);
OrderKey b = new OrderKey(8L, localId);

assertNotEquals(a, b);
assertEquals(a, new OrderKey(7L, localId));
~~~

Sau đó persist hai CompositeOrders với cùng localId nhưng khác organizationId, xác nhận DB cho phép theo PK(organization_id,local_id). Với class demo tự tạo UUID, cần fixture có constructor/setter giúp kiểm soát localId trong test.

### 36.5. Test hai tenant với API

1. Tạo user U7 chỉ thuộc organization 7.
2. Tạo Order 901 thuộc organization 8.
3. Gọi GET/PATCH/DELETE bằng U7 với ID 901.
4. Xác nhận response policy (404/403) và không sửa dữ liệu.
5. Kiểm tra cả orderNumber trùng giữa organizations.
6. Test role admin organization 7 vẫn không mặc nhiên có quyền org 8.

### 36.6. Test concurrency

Chạy hai transactions tạo Customer C-001 ở cùng organization. Database UNIQUE phải chặn một giao dịch. Kiểm tra exception được map ở boundary đúng và transaction thất bại rollback, không catch rồi tiếp tục sử dụng EntityManager đã bị lỗi.

### 36.7. Test RLS và cache

Nếu dùng RLS, test với runtime DB role (không phải superuser), SET LOCAL organization context trên connection đúng, thử SELECT/INSERT/UPDATE cross-org. Nếu dùng L2/Spring cache, test không lộ dữ liệu cross-org khi cache warm và khi đổi organization trong request khác.

## 37. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Order thuộc org A có Customer org B | FK chỉ theo customer_id | Composite FK (organization_id,customer_id) |
| Code khách hàng C-001 không tạo được ở org B | UNIQUE(customer_code) global sai scope | UNIQUE(organization_id,customer_code) |
| Query JOIN mã C-001 trả nhiều Customer | JOIN chỉ theo business code | JOIN thêm organization_id/namespace |
| findById trả Order ngoài org | Không kiểm tra quyền/scope | Scoped repository + authorization |
| UUID khó đoán vẫn truy cập chéo | Nhầm UUID với security | Enforce org membership và object permissions |
| Entity filter đã bật nhưng vẫn đọc được row cũ | L1 managed instance hoặc direct load path | Context mới, auth độc lập |
| Mapping @JoinColumns báo duplicate column | Hai properties cùng ghi một column | Xác định writable vs read-only mapping |
| Mapping composite join không tìm được parent | Referenced columns không UNIQUE/PK hoặc metadata sai | Tạo UNIQUE đúng, map referencedColumnName |
| Child được gán tenantId khác parentId | Helper không đồng bộ scalar/association | Constructor invariant và DB composite FK |
| Hibernate validate pass nhưng FK sai | Validator không kiểm tra đầy đủ mọi constraint | Test PostgreSQL catalogs/constraint violation |
| Duplicate customer code khi concurrent create | Chỉ kiểm tra exists | DB UNIQUE và conflict handling |
| @EmbeddedId query không tìm đúng | equals/hashCode thiếu field hoặc ID mutable | Composite ID immutable với equals/hashCode đúng |
| Change organization gây FK errors | Owner bị đổi tùy tiện | Cấm setter, transfer workflow riêng |
| Soft delete rồi vẫn không tái sử dụng code | UNIQUE toàn phần vẫn tồn tại | Partial UNIQUE nếu business cho phép |
| Restore deleted bị UNIQUE violation | Active row đã dùng business key | Resolve conflict trong restore workflow |
| Native SQL/bulk DML sửa org khác | Query thiếu organization predicate | Scoped DML + kiểm tra affected rows |
| Cache key C-001 lẫn hai org | Không chứa organization namespace | Scoped cache key + authorization trước cache |
| RLS test pass ở dev nhưng prod lộ row | Test dùng role bypass hoặc session setting sai | Test runtime role, transaction-local context |
| Migration gặp lỗi NOT NULL org_id | Rows cũ chưa backfill | Expand–backfill–validate–contract |
| FK mới thất bại trên dữ liệu cũ | Có cross-org legacy links | Reconcile dữ liệu trước constraint |
| Import external cross-org bị từ chối | Composite FK hoạt động đúng | Sửa pipeline mapping, không bỏ FK |
| API chỉ truyền local_id nhưng tìm nhầm org | Không truyền organization context | ID scoped object và authorized org resolution |

## 38. Bài tập thực hành theo cấp độ

### Bài A — Khóa chính và business key

1. Tạo bảng organizations, customers với id global PK.
2. Đặt UNIQUE(organization_id,customer_code).
3. Thêm Customer C-001 vào org 7 và 8; xác nhận thành công.
4. Thêm C-001 lần hai vào org 7; xác nhận UNIQUE violation.
5. Đổi customer_code trên Customer đầu tiên; kiểm tra id không đổi.
6. Giải thích vì sao không nên dùng customer_code làm PK khi có thể đổi.

### Bài B — Composite FK ngăn cross-org

1. Tạo customers với UNIQUE(organization_id,id).
2. Tạo purchase_orders với FK ghép.
3. Insert Order org 7 cho Customer org 7.
4. Insert Order org 7 cho Customer org 8 và quan sát 23503.
5. So sánh nếu chỉ dùng FK(customer_id), trên database test riêng.
6. Thêm FK ghép cho order_items → purchase_orders.

### Bài C — JPA mapping

1. Map Customer và PurchaseOrder bằng scalar organizationId/customerId.
2. Thêm @JoinColumns read-only cho association.
3. Test load lazy Customer từ Order thuộc cùng org.
4. Tạo domain method changeCustomer chỉ cho phép cùng org.
5. Test direct JDBC insert cross-org bị DB chặn.
6. So sánh với mapping @ManyToOne chỉ theo customer_id.

### Bài D — Composite primary key

1. Tạo OrderKey implements Serializable với organizationId và UUID localId.
2. Implement equals/hashCode.
3. Tạo CompositeOrder @EmbeddedId và repository ID OrderKey.
4. Persist cùng localId ở hai organizations.
5. Kiểm tra findById(new OrderKey(orgId,localId)).
6. Đánh giá trade-off với global surrogate id + composite FK.

### Bài E — Repository bảo mật

1. Viết findByIdAndOrganizationId.
2. Tạo user thuộc org 7 và Order thuộc org 8.
3. Kiểm tra service getOrder từ chối.
4. Đổi API từ findById sang scoped query.
5. Test cả update/delete và bulk DML.
6. Giải thích vì sao UUID và @Filter chưa đủ authorization.

### Bài F — Membership và global references

1. Tạo organization_memberships PK(organization_id,user_id).
2. Thêm một user tham gia hai organizations với role khác nhau.
3. Chọn active organization bằng dữ liệu đã xác minh.
4. Tạo bảng currencies dùng chung, không có organization_id.
5. Tạo bảng products thuộc tổ chức và OrderItem FK ghép tới Product.
6. Thiết kế OrganizationProductAccess nếu cần chia sẻ một global product.

### Bài G — Soft delete và business uniqueness

1. Tạo Customer C-001 org 7, sau đó soft-delete.
2. Thử tạo C-001 mới khi còn UNIQUE toàn phần; quan sát conflict.
3. Thay bằng partial unique index theo active rows trên DB test.
4. Tạo C-001 mới; thử restore C-001 cũ.
5. Thiết kế cách giải quyết restore conflict.
6. Giữ UNIQUE(organization_id,id) đầy đủ phục vụ FK.

### Bài H — Migration dữ liệu cũ

1. Dựng schema đơn tổ chức với Customers/Orders/Items có dữ liệu.
2. Expand thêm organization_id nullable.
3. Backfill theo parent–child.
4. Query tìm cross-org mismatches và NULLs.
5. Thêm UNIQUE ghép và composite FKs.
6. Chạy Hibernate schema validate sau migrations.
7. Chạy Testcontainers upgrade từ DB legacy thay vì chỉ DB trống.

### Bài I — RLS/cache/concurrency

1. Bật PostgreSQL RLS với runtime role.
2. Thiết lập app.organization_id bằng transaction-local setting.
3. Test không đọc/ghi chéo bằng native SQL.
4. Thử cùng business key ở hai organizations trong Spring Cache.
5. Thiết kế cache key có organizationId và auth trước cache hit.
6. Chạy concurrent INSERT cùng customer_code và quan sát UNIQUE.

## 39. Checklist thiết kế dữ liệu nhiều tổ chức

1. **Organization hay tenant là ranh giới sở hữu chính?** Có phân tầng hay không?
2. Mỗi entity là global reference, organization-owned hay shared-with-permission?
3. Khóa chính chọn global surrogate hay composite (organization_id,local_id)? Vì sao?
4. Khóa nghiệp vụ có phạm vi UNIQUE đúng organization/store/fiscal year không?
5. Business key có thể thay đổi, bị xóa mềm hoặc tái sử dụng không?
6. Mọi FK giữa các organization-owned rows có bảo đảm cùng organization không?
7. Parent table có UNIQUE/PK phù hợp cho composite FK chưa?
8. Mọi bảng cấp sâu có nhiều parent references đã kiểm tra same-org cho **từng** reference chưa?
9. Các reference global/cross-org có được mô hình hóa chủ đích không?
10. Entity mapping có @JoinColumns đúng cột, đúng referencedColumnName không?
11. Có cột được map writable hai lần gây conflict không?
12. Nếu dùng @EmbeddedId, ID class có immutable fields và equals/hashCode đúng không?
13. Có public setter cho organizationId gây ownership changes vô tình không?
14. Repository có method scoped theo organization không, hay còn dùng findById trần?
15. Organization ID từ request có được xác minh với principal và membership không?
16. Có object-level permission ngoài organization membership không?
17. Các query HQL/Criteria/native/DTO/join theo business key có điều kiện organization đầy đủ không?
18. Bulk UPDATE/DELETE và import pipelines có bảo vệ scope không?
19. Có DB UNIQUE/FK/CHECK để bảo vệ mọi writer không?
20. Constraint violation và optimistic conflict có rollback và map error đúng không?
21. Soft-delete UNIQUE/restore behavior đã rõ chưa?
22. Có mô hình riêng cho transfer ownership/cross-org sharing không?
23. Hibernate Session/L1 và L2/application cache có bị dùng qua nhiều security scopes không?
24. Nếu dùng RLS, role/setting/connection pool và cache bypass đã được test chưa?
25. Index đã phục vụ WHERE organization_id và FK join chưa?
26. Nếu dùng sharding/partitioning, PK/UNIQUE/FK rules có được xác minh trên DB thực không?
27. Migration từ legacy schema có backfill và validation trước NOT NULL/FK không?
28. Có integration test cố tình ghi cross-org qua JDBC/native SQL để chứng minh FK không?
29. Có test user org A đọc/sửa dữ liệu org B qua mọi API path không?
30. Có test concurrent creation, restore, membership revocation và cache-hit authorization không?

## 40. Tổng kết: ba loại khóa, ba trách nhiệm

~~~mermaid
flowchart TD
    A[Organization scope] --> B[Primary key: row identity]
    A --> C[Business key: uniqueness theo phạm vi]
    A --> D[Composite FK: cùng organization]
    B --> E[Hibernate entity identity]
    C --> F[UNIQUE/index + tra cứu nghiệp vụ]
    D --> G[DB từ chối cross-org relationships]
    H[Authentication + Membership + Permission] --> I[Scoped repository/service]
    I --> B
    I --> C
    I --> D
~~~

Các nguyên tắc cần nhớ:

1. **Primary key trả lời “đây là row nào?”** Một id toàn cục có thể định danh duy nhất mà vẫn không cho biết user được phép truy cập.
2. **Business key trả lời “đối tượng được nhận diện thế nào trong domain?”** Với nhiều organizations, mã Customer/Order thường unique theo (organization_id, code), không unique toàn hệ thống.
3. **Foreign key trả lời “quan hệ này có hợp lệ ở database không?”** FK chỉ trên customer_id có thể chấp nhận Customer thuộc tổ chức khác. FK ghép (organization_id,customer_id) → customers(organization_id,id) mới enforce same-organization.
4. **Nếu PK chỉ trên id, có thể cần UNIQUE(organization_id,id)** ở parent để PostgreSQL cho phép FK ghép tham chiếu.
5. **Composite PK là một lựa chọn khác, không phải bắt buộc.** @EmbeddedId giúp biểu diễn scope trong ID nhưng có chi phí mapping/index/API.
6. **Organization ownership nên ổn định.** Chuyển dữ liệu giữa các tổ chức cần một workflow tường minh, không chỉ sửa organization_id.
7. **Global catalog, Membership và shared resources có phạm vi riêng.** Không áp dụng same-org FK một cách máy móc lên quan hệ cố ý chia sẻ.
8. **Application authorization không thể thay bằng PK/FK.** Kiểm tra membership, permission và query scoped cho mọi read/write.
9. **Hibernate Filter và cache không tự bảo vệ mọi đường đọc.** Entity đã managed, native SQL, bulk DML và application cache cần được thiết kế riêng.
10. **UNIQUE/FOREIGN KEY ở database bảo vệ cả khi ORM bị bypass.** Các điều kiện đó cần nằm trong migrations được kiểm soát.
11. **Soft delete thay đổi uniqueness theo nghiệp vụ**, nhưng partial UNIQUE cho business key không thay referenced UNIQUE dùng bởi FK.
12. **Kiểm thử phải cố tình tìm cách phá ranh giới tổ chức**, từ SQL trực tiếp tới API, cache, concurrency, migration và các transactions khác nhau.

Một thiết kế nhiều tổ chức bền vững không chỉ thêm organization_id vào tất cả bảng. Nó xác định rõ **định danh row**, **định danh nghiệp vụ trong namespace nào** và **mỗi quan hệ có được phép băng qua ranh giới sở hữu hay không**. Khi khóa chính, khóa nghiệp vụ, composite foreign keys, Hibernate mappings và authorization cùng thể hiện một hợp đồng, database sẽ ngăn được nhiều lỗi cross-organization ngay cả trước khi chúng trở thành sự cố bảo mật hoặc dữ liệu.
