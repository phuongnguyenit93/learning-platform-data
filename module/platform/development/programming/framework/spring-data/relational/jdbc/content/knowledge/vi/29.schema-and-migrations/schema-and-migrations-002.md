# Đặt khóa ngoại, chỉ mục, unique và check constraint

Trong **Spring Data Relational JDBC**, entity mapping mô tả cách aggregate được chuyển thành các hàng và cột, còn schema database quyết định dữ liệu nào được phép tồn tại. Một model Java có thể kiểm tra dữ liệu ở service, nhưng batch job, ứng dụng khác hoặc câu SQL trực tiếp vẫn có thể ghi vào cùng database. Vì vậy, các quy tắc toàn vẹn quan trọng cần được bảo vệ ở tầng database.

Bốn thành phần thường dùng là:

- **Foreign key (khóa ngoại):** bảo đảm giá trị tham chiếu đến hàng được tham chiếu đang tồn tại.
- **Index (chỉ mục):** giúp database tìm và sắp xếp dữ liệu hiệu quả hơn cho những truy vấn phù hợp.
- **Unique constraint:** bảo đảm một cột hoặc tổ hợp cột không có giá trị trùng theo quy tắc database.
- **Check constraint:** bảo đảm giá trị của một hàng thỏa mãn biểu thức điều kiện.

Trong ứng dụng Spring Data JDBC, các thành phần này thường được tạo và thay đổi bằng schema migration như Flyway hoặc Liquibase. Mapping annotation giúp Spring Data biết tên bảng/cột và quan hệ aggregate; chúng không thay thế việc thiết kế, triển khai và kiểm soát constraint trong schema thực tế.

## 1. Vì sao cần constraint ở database?

Giả sử ứng dụng có bảng đơn hàng và bảng dòng sản phẩm:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 2) NOT NULL
);
```

Code Java có thể kiểm tra rằng đơn hàng phải có mã, item phải thuộc một đơn, số lượng lớn hơn 0 và mã đơn hàng không trùng. Nhưng những kiểm tra trong Java chỉ chạy khi dữ liệu đi qua đúng đoạn code đó. Một câu SQL thủ công hoặc một ứng dụng khác có thể bỏ qua validation.

Constraint trong database bảo vệ dữ liệu tại nơi lưu trữ, bất kể câu lệnh ghi đến từ repository, **JdbcAggregateTemplate**, **JdbcTemplate** hay công cụ khác.

### 1.1. Phân biệt validation và constraint

| Cơ chế | Nhiệm vụ |
|---|---|
| Bean Validation như **@NotNull**, **@Size** | Kiểm tra dữ liệu ở tầng ứng dụng khi validation được gọi |
| Domain validation | Bảo vệ quy tắc nghiệp vụ trong hành vi aggregate |
| Database constraint | Ngăn dữ liệu vi phạm quy tắc toàn vẹn được lưu |
| Index | Tổ chức đường truy cập cho query; không phải mọi index đều là constraint |

Các lớp này bổ sung cho nhau. Domain model có thể báo lỗi thân thiện khi số lượng âm, còn CHECK constraint là lớp bảo vệ cuối cùng nếu có đường ghi bỏ qua domain model.

Không nên đẩy mọi quy tắc nghiệp vụ vào constraint. Constraint phù hợp với các điều kiện toàn vẹn dữ liệu có thể biểu diễn và thực thi đáng tin cậy ở database.

## 2. Foreign key: bảo vệ quan hệ giữa các bảng

Foreign key (FK) ràng buộc một hoặc nhiều cột của bảng tham chiếu với khóa chính hoặc một khóa unique của bảng được tham chiếu.

Ví dụ, mỗi dòng sản phẩm phải thuộc một đơn hàng tồn tại:

```sql
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_purchase_order
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id);
```

Sau khi tạo FK:

- Không thể thêm order_items.order_id trỏ đến đơn hàng không tồn tại.
- Không thể xóa một đơn hàng đang được tham chiếu nếu thao tác xóa vi phạm chính sách FK.
- Database kiểm tra quan hệ này khi thực hiện thao tác ghi liên quan.

### 2.1. Khai báo FK khi tạo bảng

```sql
CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_items_purchase_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
);
```

Tên constraint được đặt rõ ràng để dễ đọc lỗi, kiểm tra schema và viết migration tiếp theo.

### 2.2. Khóa tham chiếu phải là khóa phù hợp

Cột được tham chiếu thường là primary key hoặc một candidate key có unique constraint/index được database chấp nhận.

Ví dụ tham chiếu đến mã đơn hàng:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT uq_purchase_orders_order_number
UNIQUE (order_number);

ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order_number
FOREIGN KEY (order_number)
REFERENCES purchase_orders(order_number);
```

Trong thiết kế thông thường, tham chiếu bằng ID ổn định thường dễ quản lý hơn tham chiếu bằng mã nghiệp vụ có thể thay đổi. Nếu dùng khóa nghiệp vụ, cần xác định chính sách khi mã đó được cập nhật.

### 2.3. NOT NULL và foreign key là hai quy tắc khác nhau

FK không mặc định bắt buộc cột tham chiếu phải có giá trị.

```sql
CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT,
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
);
```

Trong ví dụ, order_id có thể là NULL. Khi NULL, không có giá trị cụ thể để kiểm tra tham chiếu, nên FK thường không từ chối hàng đó.

Nếu mỗi item bắt buộc phải thuộc một đơn, hãy khai báo cả hai:

```sql
order_id BIGINT NOT NULL,
CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id)
    REFERENCES purchase_orders(id)
```

NOT NULL quy định sự hiện diện của giá trị; FK quy định giá trị đó phải tham chiếu đến hàng hợp lệ.

## 3. Chính sách khi hàng được tham chiếu bị xóa hoặc cập nhật

Khi một hàng cha đang được tham chiếu bị xóa hoặc khóa tham chiếu bị thay đổi, database cần áp dụng một hành vi.

| Hành động | Ý nghĩa |
|---|---|
| **NO ACTION** | Không cho phép thao tác nếu cuối thời điểm kiểm tra vẫn còn tham chiếu không hợp lệ |
| **RESTRICT** | Từ chối thao tác khi còn hàng tham chiếu; thời điểm kiểm tra tùy database |
| **CASCADE** | Xóa hoặc cập nhật các hàng con bị ảnh hưởng |
| **SET NULL** | Đặt cột FK ở hàng tham chiếu thành NULL |
| **SET DEFAULT** | Đặt cột FK về default value nếu database hỗ trợ và giá trị đó thỏa FK |

Ví dụ:

```sql
CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id)
    REFERENCES purchase_orders(id)
    ON DELETE CASCADE
```

Nếu một đơn hàng bị xóa, database tự xóa các dòng sản phẩm tham chiếu đến đơn đó.

### 3.1. ON DELETE CASCADE

CASCADE phù hợp khi hàng con không có ý nghĩa độc lập nếu thiếu hàng cha, chẳng hạn các dòng chi tiết thuộc một đơn hàng.

Tuy nhiên, cần cân nhắc:

- Xóa một root có thể xóa số lượng lớn hàng con.
- Audit hoặc lịch sử cần giữ lại có thể bị xóa ngoài dự kiến.
- Ứng dụng có thể đã chủ động xóa child theo quy trình persistence riêng.
- Cascade từ nhiều quan hệ có thể tạo chuỗi xóa khó theo dõi.

Với Spring Data JDBC, framework hiểu aggregate mapping và có chiến lược ghi/xóa các member của aggregate. Hãy xác định rõ database cascade và hành vi xóa do Spring Data thực hiện có tương thích không; không bật cascade chỉ vì có quan hệ một-nhiều.

### 3.2. ON DELETE RESTRICT hoặc NO ACTION

Nếu dữ liệu con cần được xử lý rõ ràng trước khi xóa cha, có thể dùng RESTRICT hoặc NO ACTION:

```sql
CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id)
    REFERENCES purchase_orders(id)
    ON DELETE RESTRICT
```

Database từ chối xóa đơn hàng khi vẫn còn item tham chiếu. Service có thể yêu cầu hủy, lưu trữ hoặc xử lý các item trước khi cho phép xóa.

NO ACTION và RESTRICT có khác biệt về thời điểm kiểm tra ở một số database, nhất là khi có deferred constraint. Hãy xác nhận semantics theo dialect.

### 3.3. ON DELETE SET NULL

Chỉ dùng khi quan hệ thực sự là tùy chọn:

```sql
FOREIGN KEY (sales_rep_id)
REFERENCES employees(id)
ON DELETE SET NULL
```

Cột FK phải cho phép NULL. Nếu cột được khai báo NOT NULL, hành động SET NULL không thể hoàn tất.

Ví dụ phù hợp có thể là một khách hàng vẫn tồn tại khi nhân viên phụ trách đã bị xóa, và hệ thống chấp nhận khách hàng không còn người phụ trách.

### 3.4. ON UPDATE

Có thể quy định hành vi khi khóa được tham chiếu thay đổi:

```sql
FOREIGN KEY (country_code)
REFERENCES countries(code)
ON UPDATE CASCADE
```

Với primary key dạng ID bất biến, việc đổi khóa thường không phải thao tác nghiệp vụ thông thường. Nếu dùng khóa nghiệp vụ có thể thay đổi, hãy xác định rõ có nên cascade hay cấm thay đổi.

Không nên dựa vào ON UPDATE CASCADE để thay thế thiết kế khóa ổn định.

## 4. Foreign key và aggregate boundary trong Spring Data JDBC

Spring Data JDBC tổ chức dữ liệu theo aggregate. Aggregate root là điểm truy cập và lưu aggregate; các entity thuộc aggregate được quản lý cùng root theo mapping.

Ví dụ:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderItem> items = new LinkedHashSet<>();
}
```

```java
@Table("order_items")
public class OrderItem {

    @Id
    private Long id;

    private String productCode;
    private int quantity;
}
```

idColumn = "order_id" mô tả cột ở bảng member dùng để tham chiếu ID của root. Schema database cần có cột đó và có thể bảo vệ quan hệ bằng FK:

```sql
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id);
```

Annotation mapping giúp Spring Data JDBC tạo và thực thi câu SQL đúng với cấu trúc đã khai báo. Migration tạo FK trong database. Hai phần cần nhất quán về tên bảng, tên cột, kiểu dữ liệu và nullability.

### 4.1. Tham chiếu sang aggregate khác

Ví dụ một đơn hàng tham chiếu đến khách hàng:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private AggregateReference<Customer, Long> customer;
}
```

AggregateReference biểu diễn tham chiếu đến một aggregate khác bằng ID. Nó giúp model thể hiện ranh giới aggregate mà không nhúng toàn bộ customer vào order.

Ở schema, có thể tạo FK:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT fk_purchase_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(id);
```

FK là quyết định ở tầng database. AggregateReference không tự bảo đảm mọi schema migration đều đã tạo constraint. Nếu ứng dụng cần bảo đảm customer phải tồn tại, hãy tạo FK trong migration và xử lý lỗi tham chiếu khi ghi.

### 4.2. Không biến mọi quan hệ object thành một aggregate

FK có thể kết nối các bảng thuộc nhiều aggregate. Điều đó không có nghĩa Spring Data JDBC sẽ tự động tải toàn bộ object graph hoặc cho phép thay đổi chúng như một aggregate duy nhất.

Thiết kế aggregate boundary cần dựa trên quy tắc nhất quán nghiệp vụ và vòng đời dữ liệu. FK bảo vệ tính toàn vẹn tham chiếu ở database; nó không thay thế thiết kế domain.

## 5. Index: tăng tốc truy vấn phù hợp

Index là cấu trúc phụ trợ giúp database tìm hàng mà không phải quét toàn bộ bảng trong nhiều trường hợp.

Ví dụ query thường tìm đơn theo khách hàng và sắp xếp mới nhất:

```sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC;
```

Có thể cân nhắc index:

```sql
CREATE INDEX idx_purchase_orders_customer_created_id
ON purchase_orders(customer_id, created_at DESC, id DESC);
```

Index đặt các cột theo thứ tự được thiết kế cho điều kiện lọc và thứ tự truy vấn. Query planner vẫn quyết định có dùng index hay không dựa trên thống kê, cardinality, chi phí và execution plan.

### 5.1. Index không tự động làm mọi query nhanh hơn

Index có chi phí:

- Tốn dung lượng lưu trữ.
- Làm INSERT/UPDATE/DELETE tốn thêm công cập nhật index.
- Có thể làm tăng chi phí bảo trì tùy database.
- Nhiều index trùng lặp làm schema khó quản lý.

Tạo index dựa trên query thực tế, không tạo index cho mọi cột một cách máy móc.

### 5.2. Index cho foreign key

Một FK bảo đảm tính toàn vẹn, nhưng không đồng nghĩa cột FK luôn được index tự động ở mọi database.

```sql
CREATE INDEX idx_order_items_order_id
ON order_items(order_id);
```

Index này có thể giúp tải các item của một order, JOIN order với item, kiểm tra các hàng tham chiếu khi xóa/cập nhật root và chạy truy vấn lọc theo order_id.

Một số database như PostgreSQL không tự tạo index trên cột tham chiếu ở bảng con khi khai báo FK. MySQL InnoDB thường yêu cầu và có thể tự tạo index phù hợp nếu chưa có. Vì vậy, kiểm tra hành vi của dialect và index đã tồn tại trước khi tạo thêm.

### 5.3. Index đơn và index composite

Index đơn:

```sql
CREATE INDEX idx_orders_status
ON purchase_orders(status);
```

Có thể hỗ trợ query chỉ lọc theo status.

Index composite:

```sql
CREATE INDEX idx_orders_customer_status_created
ON purchase_orders(customer_id, status, created_at DESC);
```

Có thể hỗ trợ query lọc theo customer và status, sau đó sắp xếp theo thời gian.

Thứ tự cột trong composite index rất quan trọng. Với B-tree index, database thường tận dụng tốt các điều kiện trên các cột đứng đầu (leftmost prefix). Index (customer_id, status, created_at) có thể hữu ích cho truy vấn theo customer, hoặc customer + status; nó thường không thay thế tốt một index chỉ trên status nếu query không có điều kiện customer.

Hãy thiết kế index theo những truy vấn thực sự xuất hiện trong ứng dụng.

### 5.4. Index hỗ trợ ORDER BY

Một index có thể hỗ trợ sắp xếp nếu thứ tự cột và hướng phù hợp với query:

```sql
CREATE INDEX idx_orders_created_id
ON purchase_orders(created_at DESC, id DESC);
```

Query:

```sql
SELECT id, order_number
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Database có thể đọc index theo thứ tự cần thiết thay vì sort toàn bộ tập kết quả. Khả năng tận dụng phụ thuộc database, filter, direction và query plan.

### 5.5. Covering index và included columns

Một số database hỗ trợ thêm cột không thuộc key để query có thể lấy dữ liệu trực tiếp từ index.

Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_orders_customer_created
ON purchase_orders(customer_id, created_at DESC)
INCLUDE (id, order_number, status);
```

Các cột trong INCLUDE không tham gia thứ tự key nhưng có thể giúp index-only scan trong điều kiện phù hợp. Đây là tối ưu phụ thuộc dialect; không dùng cú pháp này như SQL portable.

## 6. Unique constraint: bảo đảm không có dữ liệu trùng

Unique constraint yêu cầu giá trị của một cột hoặc tổ hợp cột là duy nhất.

Ví dụ mã đơn hàng không được trùng:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT uq_purchase_orders_order_number
UNIQUE (order_number);
```

Hoặc khai báo khi tạo bảng:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT uq_purchase_orders_order_number
        UNIQUE (order_number)
);
```

### 6.1. Unique trên nhiều cột

Một khách hàng có thể có nhiều địa chỉ, nhưng không được trùng nhãn địa chỉ trong cùng khách hàng:

```sql
ALTER TABLE customer_addresses
ADD CONSTRAINT uq_customer_addresses_customer_label
UNIQUE (customer_id, label);
```

Điều này cho phép hai khách hàng khác nhau cùng có label HOME, nhưng một khách hàng không thể có hai địa chỉ cùng label.

Unique composite kiểm tra tổ hợp giá trị, không kiểm tra riêng từng cột.

### 6.2. UNIQUE và NULL

Cách xử lý NULL trong unique constraint có khác biệt giữa database.

Nhiều hệ quản trị mặc định cho phép nhiều hàng có NULL trong cột unique vì NULL không được xem là bằng nhau theo semantics unique thông thường. Một số database cung cấp cú pháp hoặc tùy chọn khác, ví dụ PostgreSQL có NULLS NOT DISTINCT ở các phiên bản hỗ trợ.

Nếu nghiệp vụ yêu cầu mỗi hàng phải có giá trị duy nhất và bắt buộc có giá trị, dùng cả:

```sql
email_address VARCHAR(320) NOT NULL,
CONSTRAINT uq_customers_email UNIQUE (email_address)
```

Nếu NULL mang ý nghĩa “chưa có email”, cần xác định rõ có cho phép nhiều khách hàng chưa có email hay không và dùng cú pháp phù hợp với database.

### 6.3. Unique constraint và unique index

Nhiều database triển khai unique constraint bằng unique index. Về ý nghĩa thiết kế:

- UNIQUE diễn đạt quy tắc toàn vẹn dữ liệu.
- Unique index là cấu trúc index thực thi quy tắc và có thể phục vụ truy vấn.

Khi muốn thể hiện quy tắc duy nhất thông thường, dùng UNIQUE constraint để schema thể hiện rõ ý định. Dùng unique index trực tiếp khi cần tính năng đặc thù như partial unique index hoặc expression index.

### 6.4. Partial unique index

Có trường hợp chỉ muốn bảo đảm duy nhất trong một tập con hàng.

Ví dụ, mỗi khách hàng chỉ có một địa chỉ mặc định đang hoạt động:

```sql
CREATE UNIQUE INDEX uq_customer_one_active_default_address
ON customer_addresses(customer_id)
WHERE is_default = TRUE AND archived_at IS NULL;
```

Đây là partial unique index trong PostgreSQL. Nó chỉ áp dụng với các hàng thỏa điều kiện WHERE. Không phải mọi database đều hỗ trợ cú pháp tương tự; cần dùng giải pháp phù hợp với dialect.

### 6.5. Unique không thay thế xử lý xung đột trong ứng dụng

Không nên chỉ kiểm tra trước:

```java
if (!repository.existsByOrderNumber(orderNumber)) {
    repository.save(order);
}
```

Hai request đồng thời có thể cùng kiểm tra thấy mã chưa tồn tại rồi cùng insert. Đây là race condition.

Unique constraint ở database là lớp bảo vệ cuối cùng. Ứng dụng nên bắt và chuyển lỗi duplicate thành phản hồi nghiệp vụ phù hợp, chẳng hạn mã đơn đã được sử dụng.

Trong Spring, lỗi có thể được dịch thành DuplicateKeyException hoặc DataIntegrityViolationException tùy driver, câu SQL và cách Spring dịch exception. Không nên phụ thuộc vào một exception subclass duy nhất nếu nhiều database/driver được hỗ trợ.

## 7. Check constraint: kiểm tra giá trị trong từng hàng

Check constraint yêu cầu biểu thức điều kiện không được đánh giá là FALSE khi ghi hoặc cập nhật hàng.

Ví dụ số lượng phải lớn hơn 0:

```sql
ALTER TABLE order_items
ADD CONSTRAINT chk_order_items_quantity_positive
CHECK (quantity > 0);
```

Giá không được âm:

```sql
ALTER TABLE order_items
ADD CONSTRAINT chk_order_items_unit_price_nonnegative
CHECK (unit_price >= 0);
```

Trạng thái chỉ được thuộc một tập giá trị:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT chk_purchase_orders_status
CHECK (status IN ('NEW', 'PAID', 'CANCELLED', 'SHIPPED'));
```

### 7.1. CHECK không thay thế NOT NULL

Một chi tiết quan trọng: SQL CHECK thường chấp nhận biểu thức cho kết quả UNKNOWN (chẳng hạn khi giá trị là NULL), miễn là kết quả không phải FALSE.

Do đó:

```sql
quantity INTEGER CHECK (quantity > 0)
```

không nhất thiết ngăn quantity = NULL.

Nếu quantity bắt buộc phải có và lớn hơn 0:

```sql
quantity INTEGER NOT NULL,
CONSTRAINT chk_order_items_quantity_positive
    CHECK (quantity > 0)
```

NOT NULL và CHECK giải quyết hai điều kiện khác nhau.

### 7.2. Check cho khoảng giá trị

Ví dụ phần trăm giảm giá phải nằm trong khoảng 0 đến 100:

```sql
discount_percent DECIMAL(5, 2) NOT NULL,
CONSTRAINT chk_discount_percent_range
    CHECK (discount_percent >= 0 AND discount_percent <= 100)
```

Có thể dùng BETWEEN:

```sql
CHECK (discount_percent BETWEEN 0 AND 100)
```

Hai biểu thức có cùng ý nghĩa với giá trị số không NULL.

### 7.3. Check cho quan hệ giữa các cột

Ví dụ ngày kết thúc phải bằng hoặc sau ngày bắt đầu:

```sql
CREATE TABLE promotions (
    id BIGINT PRIMARY KEY,
    starts_at TIMESTAMP NOT NULL,
    ends_at TIMESTAMP NOT NULL,
    CONSTRAINT chk_promotion_date_range
        CHECK (ends_at >= starts_at)
);
```

Điều kiện này liên quan các cột trong cùng một hàng và phù hợp với CHECK constraint.

### 7.4. Không dùng CHECK cho quy tắc cần nhìn nhiều hàng

CHECK thường được thiết kế để kiểm tra biểu thức trên hàng hiện tại. Không nên dùng nó để kiểm tra tổng số hàng liên quan hoặc trạng thái của hàng ở bảng khác.

Ví dụ “một khách hàng chỉ được có tối đa 5 đơn đang mở” là quy tắc liên quan nhiều hàng. Có thể cần transaction locking, trigger, một bảng counter được quản lý đồng bộ hoặc thiết kế nghiệp vụ khác. Một CHECK đơn giản không thể bảo đảm quy tắc này một cách portable.

Nếu quy tắc là duy nhất, hãy dùng unique constraint/index. Nếu quy tắc tham chiếu bảng khác, dùng FK. Nếu quy tắc phức tạp liên quan nhiều hàng, chọn cơ chế database và transaction thích hợp thay vì ép vào CHECK.

### 7.5. CHECK và phiên bản database

Mức hỗ trợ CHECK khác nhau theo hệ quản trị và phiên bản. Ví dụ MySQL chỉ thực thi CHECK constraint trong các bản phát hành mới hơn (MySQL 8.0.16 trở đi); những bản cũ hơn có thể parse nhưng bỏ qua constraint. Hãy xác nhận phiên bản production thực sự enforce điều kiện.

## 8. Kết hợp các constraint trong một schema

Ví dụ một schema đơn hàng có thể định nghĩa các quy tắc:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email_address VARCHAR(320) NOT NULL,
    CONSTRAINT uq_customers_email UNIQUE (email_address)
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,

    CONSTRAINT uq_purchase_orders_order_number
        UNIQUE (order_number),

    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id),

    CONSTRAINT chk_purchase_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED', 'SHIPPED'))
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 2) NOT NULL,

    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
        ON DELETE CASCADE,

    CONSTRAINT chk_order_items_quantity_positive
        CHECK (quantity > 0),

    CONSTRAINT chk_order_items_unit_price_nonnegative
        CHECK (unit_price >= 0)
);

CREATE INDEX idx_purchase_orders_customer_created
    ON purchase_orders(customer_id, created_at DESC, id DESC);

CREATE INDEX idx_order_items_order_id
    ON order_items(order_id);
```

Schema trên minh họa nhiều loại quy tắc:

| Quy tắc | Constraint/index |
|---|---|
| Email khách hàng không được trùng | uq_customers_email |
| Mã đơn hàng không được trùng | uq_purchase_orders_order_number |
| Đơn hàng phải thuộc khách hàng tồn tại | fk_purchase_orders_customer |
| Trạng thái đơn hàng thuộc tập cho phép | chk_purchase_orders_status |
| Item phải thuộc đơn hàng tồn tại | fk_order_items_order |
| Số lượng phải dương | chk_order_items_quantity_positive |
| Giá đơn vị không âm | chk_order_items_unit_price_nonnegative |
| Tải đơn theo khách hàng và thời gian | idx_purchase_orders_customer_created |
| Tải item theo order | idx_order_items_order_id |

ON DELETE CASCADE trong ví dụ là lựa chọn minh họa. Chỉ dùng nếu vòng đời dữ liệu cho phép xóa item cùng đơn hàng. Nếu cần giữ lịch sử, có thể dùng soft delete hoặc chính sách khác.

## 9. Quản lý constraint và index bằng schema migration

Spring Data JDBC tập trung vào mapping và persistence aggregate. Trong nhiều dự án, schema được quản lý bằng công cụ migration để các môi trường phát triển, kiểm thử và production có cùng cấu trúc.

Một migration versioned có thể tạo bảng và constraint ban đầu. Ví dụ tên file Flyway:

```text
src/main/resources/db/migration/
  V001__create_customer_tables.sql
  V002__add_order_indexes.sql
  V003__add_order_status_constraint.sql
```

Ví dụ nội dung migration:

```sql
-- V001__create_customer_tables.sql

CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email_address VARCHAR(320) NOT NULL,
    CONSTRAINT uq_customers_email UNIQUE (email_address)
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_purchase_orders_order_number
        UNIQUE (order_number),
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

Migration tiếp theo thêm index:

```sql
-- V002__add_order_indexes.sql

CREATE INDEX idx_purchase_orders_customer_created
ON purchase_orders(customer_id, created_at DESC, id DESC);
```

Migration sau bổ sung CHECK:

```sql
-- V003__add_order_status_constraint.sql

ALTER TABLE purchase_orders
ADD CONSTRAINT chk_purchase_orders_status
CHECK (status IN ('NEW', 'PAID', 'CANCELLED', 'SHIPPED'));
```

Các migration được áp dụng theo version. Khi một migration đã chạy ở môi trường dùng chung, không sửa nội dung lịch sử của nó để thay đổi schema; tạo migration mới mô tả thay đổi tiếp theo.

### 9.1. Tên constraint nên rõ ràng và ổn định

Một quy ước phổ biến:

| Loại | Prefix gợi ý | Ví dụ |
|---|---|---|
| Primary key | pk_ | pk_purchase_orders |
| Foreign key | fk_ | fk_order_items_order |
| Unique | uq_ | uq_customers_email |
| Check | chk_ | chk_order_items_quantity_positive |
| Index | idx_ | idx_orders_customer_created |

Tên rõ ràng giúp đọc lỗi database và viết migration drop/alter. Một số database có giới hạn độ dài identifier; hãy giữ tên ngắn nhưng có nghĩa và theo naming convention của dự án.

### 9.2. Migration phải an toàn với dữ liệu hiện có

Thêm constraint vào bảng đã có dữ liệu có thể thất bại nếu dữ liệu hiện tại vi phạm quy tắc mới.

Trước khi thêm FK:

```sql
SELECT oi.order_id
FROM order_items oi
LEFT JOIN purchase_orders o ON o.id = oi.order_id
WHERE oi.order_id IS NOT NULL
  AND o.id IS NULL;
```

Trước khi thêm unique:

```sql
SELECT order_number, COUNT(*)
FROM purchase_orders
GROUP BY order_number
HAVING COUNT(*) > 1;
```

Trước khi thêm CHECK:

```sql
SELECT id, quantity
FROM order_items
WHERE quantity <= 0;
```

Các truy vấn này giúp tìm dữ liệu cần xử lý trước khi migration được áp dụng. Với cột nullable, hãy kiểm tra NULL riêng nếu quy tắc mới yêu cầu NOT NULL.

Không xóa hoặc sửa dữ liệu production tự động mà chưa xác định quy tắc chuyển đổi. Migration có thể cần một bước backfill hoặc cleanup có kiểm soát trước khi constraint được bật.

### 9.3. Expand-contract cho thay đổi lớn

Khi thay đổi schema mà ứng dụng cũ và mới có thể chạy đồng thời trong lúc deploy, dùng chiến lược expand-contract:

1. **Expand:** thêm cột/index/constraint tương thích với phiên bản ứng dụng cũ.
2. Deploy code mới có thể đọc/ghi cấu trúc mới.
3. Backfill dữ liệu cũ.
4. Chuyển ứng dụng sang cấu trúc mới.
5. **Contract:** loại bỏ cột hoặc cấu trúc cũ trong migration sau khi không còn code dùng nó.

Ví dụ, muốn biến email_address thành unique nhưng dữ liệu hiện tại còn trùng: trước tiên xử lý dữ liệu và deploy code ngăn tạo duplicate; sau đó mới thêm unique constraint.

### 9.4. Rollback migration

Không phải mọi thay đổi schema đều có thể rollback an toàn nếu đã có dữ liệu mới được ghi.

- Drop index thường không làm mất dữ liệu nhưng có thể ảnh hưởng hiệu năng.
- Drop FK làm mất lớp bảo vệ tham chiếu.
- Drop CHECK làm mất lớp bảo vệ miền giá trị.
- Drop unique constraint cho phép duplicate mới xuất hiện.
- Thay đổi kiểu cột có thể mất dữ liệu nếu chuyển đổi không bảo toàn.

Hãy đánh giá hậu quả dữ liệu và compatibility trước khi viết rollback script. Với Flyway, migration versioned thông thường là lịch sử tiến về phía trước; rollback thường được triển khai bằng migration mới hoặc quy trình undo có kiểm soát tùy cách dự án tổ chức.

## 10. Tạo index trên bảng lớn

Tạo index trên bảng lớn có thể tiêu tốn thời gian, CPU, I/O và ảnh hưởng khả năng ghi.

PostgreSQL hỗ trợ:

```sql
CREATE INDEX CONCURRENTLY idx_orders_created_id
ON purchase_orders(created_at DESC, id DESC);
```

CONCURRENTLY giảm mức chặn ghi so với tạo index thông thường, nhưng có giới hạn: không chạy bên trong transaction block thông thường và có thể để lại index invalid nếu thao tác thất bại. Cần cấu hình migration tool để migration này không bị bọc trong transaction nếu dùng cú pháp đó.

SQL Server và các database khác có lựa chọn online index operation riêng theo edition/version. Không giả định CONCURRENTLY là cú pháp portable.

Trước khi tạo index trên production:

- Xác định query cần tối ưu.
- Đọc execution plan.
- Đánh giá kích thước bảng và write workload.
- Chọn cách tạo index ít ảnh hưởng phù hợp database.
- Theo dõi thời gian, lock và trạng thái index.
- Xác nhận migration tool xử lý transaction theo yêu cầu của câu lệnh.

## 11. Deferrable constraint và kiểm tra trì hoãn

Một số database, như PostgreSQL, hỗ trợ constraint có thể trì hoãn việc kiểm tra đến cuối transaction:

```sql
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
DEFERRABLE INITIALLY DEFERRED;
```

Với constraint deferred, một transaction có thể tạm thời tạo trạng thái tham chiếu chưa hợp lệ giữa các câu lệnh, miễn là trạng thái cuối khi kiểm tra vẫn hợp lệ.

Điều này hữu ích trong một số thao tác đổi khóa hoặc ghi nhiều hàng có phụ thuộc vòng. Nhưng không phải mọi loại constraint hoặc database đều hỗ trợ deferrable theo cùng cách.

Không dùng deferred constraint để che giấu thứ tự ghi không rõ ràng. Chỉ bật khi use case thật sự cần và integration test xác nhận semantics trên database đích.

## 12. Constraint và exception trong Spring Data JDBC

Khi câu lệnh vi phạm FK, unique hoặc CHECK, database trả lỗi. Spring JDBC thường dịch lỗi JDBC thành hệ exception trong package org.springframework.dao.

| Vi phạm | Exception Spring thường gặp |
|---|---|
| Unique/duplicate key | DuplicateKeyException hoặc DataIntegrityViolationException |
| FK | DataIntegrityViolationException |
| CHECK | DataIntegrityViolationException |
| NOT NULL | DataIntegrityViolationException |

Exception subclass chính xác có thể phụ thuộc database, driver và cách dịch lỗi. Nếu ứng dụng hỗ trợ nhiều dialect, xử lý theo loại lỗi nghiệp vụ và không dựa hoàn toàn vào một vendor error code.

Ví dụ:

```java
@Transactional
public Customer register(Customer customer) {
    try {
        return customerRepository.save(customer);
    } catch (DuplicateKeyException exception) {
        throw new EmailAlreadyRegisteredException(
            customer.emailAddress(),
            exception
        );
    }
}
```

Ví dụ giả định unique constraint trên email được tạo trong database. Service chuyển lỗi persistence thành exception có ý nghĩa với use case.

Không nên chỉ bắt DataIntegrityViolationException rồi trả về thông báo “dữ liệu không hợp lệ” cho mọi trường hợp. FK, CHECK, NOT NULL và unique có ý nghĩa khác nhau; hãy chuyển thành lỗi domain/API thích hợp khi có đủ thông tin.

### 12.1. Không thay constraint bằng kiểm tra exists

Đoạn code sau có thể hữu ích để đưa ra phản hồi sớm:

```java
if (!repository.existsByOrderNumber(orderNumber)) {
    repository.save(order);
}
```

Nhưng vẫn phải giữ unique constraint trong database để xử lý cạnh tranh đồng thời. Kiểm tra trước giúp trải nghiệm người dùng; constraint mới là bảo đảm cuối cùng.

### 12.2. Sau lỗi constraint, transaction có thể rollback-only

Một số database đánh dấu transaction ở trạng thái lỗi sau câu SQL vi phạm constraint. Nếu bắt exception rồi tiếp tục chạy query trong cùng transaction, thao tác tiếp theo có thể thất bại hoặc transaction vẫn không thể commit.

Cách an toàn thường là để exception thoát khỏi transaction boundary và chuyển đổi ở tầng cao hơn. Nếu cần tiếp tục sau một thao tác có thể vi phạm constraint, hãy thiết kế transaction/savepoint riêng và kiểm tra khả năng hỗ trợ của database/transaction manager.

## 13. Mapping Spring Data JDBC và schema phải đồng nhất

Spring Data JDBC dùng mapping metadata để biết:

- Tên bảng từ **@Table**.
- Tên cột từ **@Column** hoặc naming strategy.
- ID từ **@Id**.
- Quan hệ collection qua **@MappedCollection**.
- Tham chiếu aggregate qua **AggregateReference**.
- Kiểu dữ liệu qua converter.

Ví dụ:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    @Column("customer_id")
    private AggregateReference<Customer, Long> customer;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderItem> items = new LinkedHashSet<>();
}
```

Schema cần tương ứng:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT uq_purchase_orders_order_number UNIQUE (order_number),
    CONSTRAINT fk_purchase_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT chk_order_items_quantity
        CHECK (quantity > 0)
);

CREATE INDEX idx_order_items_order_id
ON order_items(order_id);
```

Nếu mapping dùng customer_id nhưng schema chỉ có customer, câu SQL được tạo có thể lỗi. Nếu MappedCollection dùng order_id nhưng bảng child dùng purchase_order_id, cần sửa mapping hoặc migration để thống nhất.

### 13.1. Annotation mapping không tự tạo mọi constraint

@Table, @Column, @Id và @MappedCollection mô tả mapping object-relational. Không nên kỳ vọng chúng tự tạo đầy đủ FK, index, unique và CHECK constraint trong production.

Một số công cụ schema initialization có thể tạo DDL cho môi trường phát triển, nhưng migration versioned vẫn là cách rõ ràng để quản lý schema có kiểm soát.

### 13.2. Unique trong Java và unique trong database

Nếu model có field emailAddress, việc kiểm tra email không trùng trong service không tự tạo unique constraint. Hãy tạo constraint bằng migration:

```sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email_address
UNIQUE (email_address);
```

Sau đó viết integration test xác nhận database từ chối duplicate.

## 14. Kiểm thử constraint và index

Constraint là hành vi database, nên unit test thuần Java không đủ để chứng minh chúng được triển khai đúng.

### 14.1. Test foreign key

Tạo một order item tham chiếu ID không tồn tại và xác nhận database từ chối:

```java
@Test
void rejectsItemWithUnknownOrder() {
    assertThatThrownBy(() ->
        jdbcTemplate.update(
            """
            INSERT INTO order_items(
                id, order_id, product_code, quantity, unit_price
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            1L,
            999999L,
            "KB-01",
            1,
            new BigDecimal("10.00")
        )
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

### 14.2. Test unique constraint

```java
@Test
void rejectsDuplicateOrderNumber() {
    insertOrder(1L, "ORD-1001");

    assertThatThrownBy(() ->
        insertOrder(2L, "ORD-1001")
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

Test nên xác nhận database từ chối duplicate, không chỉ xác nhận service validation.

### 14.3. Test CHECK constraint

```java
@Test
void rejectsNonPositiveItemQuantity() {
    assertThatThrownBy(() ->
        insertOrderItem(1L, 10L, "KB-01", 0)
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

### 14.4. Test migration với đúng database

H2 có thể khác PostgreSQL, MySQL, SQL Server hoặc Oracle về cú pháp và semantics constraint/index. Nếu production dùng một database cụ thể, integration test nên dùng cùng hệ quản trị và version tương thích, thường qua Testcontainers.

Kiểm thử:

- Migration chạy trên schema rỗng.
- Migration chạy trên dữ liệu hiện có đại diện.
- FK từ chối tham chiếu không tồn tại.
- Unique từ chối duplicate.
- CHECK từ chối giá trị sai.
- Index được tạo với đúng cột và thứ tự.
- Query thực tế có execution plan phù hợp sau khi có index.

### 14.5. Index không thể kiểm thử bằng cách chỉ kiểm tra query trả đúng dữ liệu

Index thường không thay đổi kết quả logic của query. Để xác nhận hiệu quả, cần xem execution plan và đo trên dữ liệu đủ đại diện. Không khẳng định query dùng index chỉ vì index đã được tạo.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không thể thêm item với order hợp lệ | FK trỏ sai cột hoặc mapping/schema lệch nhau | Kiểm tra mapping và DDL |
| Item trỏ đến order không tồn tại | Chưa tạo FK | Thêm foreign key constraint |
| FK vẫn cho phép NULL | Chỉ có FK, thiếu NOT NULL | Thêm NOT NULL nếu quan hệ bắt buộc |
| Xóa order bị từ chối | Còn child tham chiếu với RESTRICT/NO ACTION | Xử lý child hoặc chọn cascade có chủ đích |
| Xóa order làm mất dữ liệu lịch sử | Dùng ON DELETE CASCADE không phù hợp | Dùng RESTRICT/soft delete hoặc retention policy |
| Query lọc theo FK vẫn chậm | Cột FK chưa có index phù hợp | Kiểm tra index và execution plan |
| Unique constraint không chặn nhiều NULL | Semantics NULL của database | Kết hợp NOT NULL hoặc thiết kế unique phù hợp |
| Hai request tạo duplicate | Chỉ dùng exists-check trong Java | Dùng unique constraint và xử lý duplicate exception |
| CHECK không chặn NULL | CHECK trả UNKNOWN khi biểu thức chứa NULL | Thêm NOT NULL nếu bắt buộc |
| CHECK không được enforce | Database version không hỗ trợ/enforce | Kiểm tra phiên bản production |
| Thêm constraint thất bại khi deploy | Dữ liệu cũ vi phạm điều kiện mới | Audit, backfill và cleanup trước migration |
| Index làm ghi chậm | Có quá nhiều index hoặc index ít hữu ích | Đo workload, loại index trùng/không dùng |
| Migration lỗi khi tạo index lớn | Lock hoặc giới hạn transaction của dialect | Dùng chiến lược online/concurrent phù hợp |
| Test H2 pass nhưng production lỗi | Khác biệt dialect | Integration test với database production-compatible |

## 16. Bài thực hành

Giả sử có các bảng customers, purchase_orders và order_items.

**Bài 1.** Mỗi item phải thuộc một order tồn tại. Cần constraint nào?

*Đáp án:* Foreign key từ order_items.order_id đến purchase_orders.id. Nếu item bắt buộc có order, cột order_id còn cần NOT NULL.

**Bài 2.** Mã đơn hàng phải duy nhất. Dùng gì?

*Đáp án:* Unique constraint trên purchase_orders.order_number.

**Bài 3.** Quantity phải lớn hơn 0. Dùng gì?

*Đáp án:* CHECK (quantity > 0) và NOT NULL nếu quantity bắt buộc có giá trị.

**Bài 4.** Query thường tải item theo order_id nhưng chạy chậm. Có thể cần gì?

*Đáp án:* Index trên order_items(order_id), sau đó xác nhận bằng execution plan. Một số database tự tạo index cho FK, một số không.

**Bài 5.** Có nên chỉ dùng existsByOrderNumber để ngăn mã đơn trùng không?

*Đáp án:* Không. Hai transaction đồng thời có thể cùng vượt qua kiểm tra. Database vẫn cần unique constraint.

**Bài 6.** ON DELETE CASCADE có luôn phù hợp với item của order không?

*Đáp án:* Không. Chỉ dùng khi item có vòng đời phụ thuộc root và việc xóa root được phép xóa toàn bộ item. Nếu cần audit hoặc lịch sử, chọn chính sách khác.

**Bài 7.** Vì sao CHECK quantity > 0 không đủ để cấm NULL?

*Đáp án:* Trong SQL, biểu thức với NULL có thể trả UNKNOWN; CHECK thường chỉ từ chối FALSE. Thêm NOT NULL nếu giá trị bắt buộc.

**Bài 8.** Có thể thêm unique constraint vào bảng production đang có duplicate không?

*Đáp án:* Không thể thêm thành công khi dữ liệu vi phạm. Cần tìm và xử lý duplicate trước, rồi triển khai migration thêm constraint.

**Bài 9.** Spring Data JDBC có tự tạo toàn bộ index và FK từ aggregate mapping không?

*Đáp án:* Không nên giả định như vậy. Mapping mô tả quan hệ object và tên cột; schema constraint/index cần được quản lý qua migration hoặc cơ chế DDL có kiểm soát.

## 17. Điều cần ghi nhớ

- **Foreign key** bảo vệ tham chiếu giữa các bảng; dùng **NOT NULL** riêng nếu quan hệ bắt buộc có giá trị.
- Chọn **CASCADE**, **RESTRICT**, **NO ACTION** hoặc **SET NULL** theo vòng đời và yêu cầu lưu trữ dữ liệu.
- Spring Data JDBC aggregate mapping và database FK có vai trò bổ sung nhau; mapping không tự bảo đảm schema đã có constraint.
- **Index** giúp query phù hợp tìm/sắp xếp dữ liệu hiệu quả hơn nhưng làm tăng dung lượng và chi phí ghi.
- Thiết kế index từ query thực tế; chú ý thứ tự cột trong composite index và index cho cột FK.
- **Unique constraint** là lớp bảo vệ cuối cùng cho dữ liệu duy nhất, kể cả khi nhiều request chạy đồng thời.
- **CHECK constraint** kiểm tra biểu thức trên hàng; kết hợp **NOT NULL** nếu giá trị không được phép thiếu.
- Không dùng CHECK đơn giản để kiểm tra quy tắc phức tạp giữa nhiều hàng hoặc nhiều bảng.
- Đặt tên constraint/index rõ ràng và quản lý bằng migration versioned.
- Trước khi thêm constraint vào bảng có dữ liệu, tìm và xử lý các hàng vi phạm.
- Kiểm thử migration và constraint trên đúng database/dialect production.
- Xử lý exception toàn vẹn dữ liệu ở service để chuyển thành lỗi nghiệp vụ/API phù hợp.

### Tài liệu tham khảo chính thức

- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): mapping aggregate, bảng, cột và quan hệ member.
- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repository và persistence trong Spring Data JDBC.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): primary key, foreign key, unique, check và hành vi constraint.
- [PostgreSQL — Indexes](https://www.postgresql.org/docs/current/indexes.html): các loại index và cách database sử dụng index.
- [MySQL — InnoDB Foreign Key Constraints](https://dev.mysql.com/doc/refman/8.4/en/innodb-foreign-key-constraints.html): quy tắc FK và hành động tham chiếu.
- [MySQL — CHECK Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html): cú pháp và điều kiện enforce CHECK.
- [Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations): cách tổ chức migration theo version.

Khi triển khai, hãy xác nhận cú pháp, semantics NULL, hành vi cascade và khả năng tạo index theo database/version thực tế. Mục tiêu là để mapping Spring Data JDBC, schema migration và quy tắc toàn vẹn trong database mô tả cùng một cấu trúc dữ liệu.
