# Thiết kế khóa ngoại, ràng buộc duy nhất và các bất biến dữ liệu

Trong Spring Data Relational R2DBC, repository và `R2dbcEntityTemplate` giúp ứng dụng đọc, thêm, cập nhật và xóa entity theo mô hình reactive. Tuy nhiên, tính đúng đắn của dữ liệu không thể chỉ dựa vào các câu lệnh trong service. Khi nhiều request chạy đồng thời, nhiều instance cùng ghi dữ liệu hoặc một chương trình khác truy cập cùng database, chỉ kiểm tra ở tầng ứng dụng là chưa đủ. Cơ sở dữ liệu cần có các ràng buộc để bảo vệ quan hệ và bất biến quan trọng ngay tại nơi dữ liệu được lưu.

Khóa ngoại (foreign key) bảo đảm một giá trị tham chiếu tới bản ghi hợp lệ. Ràng buộc duy nhất (unique constraint) ngăn các giá trị hoặc tổ hợp giá trị bị trùng. Các ràng buộc như `NOT NULL`, `CHECK` và khóa chính bổ sung những quy tắc khác. Kết hợp chúng với transaction và validation ở tầng nghiệp vụ giúp dữ liệu luôn nhất quán kể cả khi nhiều thao tác xảy ra cùng lúc.

## 1. Bất biến dữ liệu là gì?

Bất biến dữ liệu (data invariant) là điều kiện phải luôn đúng đối với trạng thái được lưu. Ví dụ:

- Mỗi đơn hàng phải tham chiếu tới một khách hàng đã tồn tại.
- Mỗi tài khoản có một mã định danh duy nhất trong phạm vi tenant.
- Email đăng ký của một khách hàng phải duy nhất theo quy tắc chuẩn hóa của sản phẩm.
- Số lượng hàng tồn kho không được âm.
- Tổng tiền hoặc trạng thái của một bản ghi phải tuân theo các quy tắc miền đã xác định.

Một số bất biến có thể được biểu diễn trực tiếp bằng cấu trúc relational: `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL` và `CHECK`. Một số quy tắc phức tạp cần được kiểm tra trong domain/service hoặc transaction, ví dụ tổng hạn mức trên nhiều dòng, chuyển trạng thái theo quy trình hay điều kiện phụ thuộc vào nhiều aggregate.

Nên đặt quy tắc ở tầng có thể bảo vệ nó trước mọi đường ghi dữ liệu. Nếu một điều kiện có thể biểu diễn bằng constraint của database, constraint thường là hàng rào cuối cùng đáng tin cậy. Validation ở tầng ứng dụng vẫn cần thiết để trả lỗi thân thiện và phát hiện sớm đầu vào sai, nhưng không thay thế constraint.

## 2. Các loại constraint thường dùng

| Constraint | Quy tắc được bảo vệ | Ví dụ |
| --- | --- | --- |
| `PRIMARY KEY` | Mỗi hàng có định danh duy nhất và không null | `customer.id` |
| `FOREIGN KEY` | Giá trị tham chiếu phải tồn tại ở bảng được tham chiếu | `orders.customer_id` tham chiếu `customer.id` |
| `UNIQUE` | Một cột hoặc tổ hợp cột không được trùng theo quy tắc của database | `(tenant_id, email_normalized)` |
| `NOT NULL` | Cột bắt buộc phải có giá trị | `orders.created_at` |
| `CHECK` | Giá trị phải thỏa một biểu thức điều kiện | `quantity >= 0` |

Các constraint có thể kết hợp với nhau. Ví dụ một bảng tài khoản có khóa chính `id`, email bắt buộc, email duy nhất trong tenant và `tenant_id` phải tham chiếu tới một tenant hợp lệ.

```sql
CREATE TABLE tenant (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    CONSTRAINT fk_customer_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant(id),
    CONSTRAINT uq_customer_tenant_email
        UNIQUE (tenant_id, email_normalized)
);
```

Đây là SQL theo cú pháp PostgreSQL phổ biến. Kiểu dữ liệu, cách đặt tên constraint và một số chi tiết có thể khác giữa các hệ quản trị. Constraint được tạo trong schema database; annotation của entity không tự thay thế toàn bộ định nghĩa schema này.

## 3. Khóa ngoại bảo vệ quan hệ giữa các bảng

Khóa ngoại xác định một cột hoặc nhóm cột ở bảng con phải khớp với khóa chính hoặc một khóa duy nhất được tham chiếu ở bảng cha. Ví dụ, một đơn hàng phải thuộc về một khách hàng tồn tại:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
```

`orders.customer_id` là khóa ngoại. Database từ chối insert hoặc update một đơn hàng nếu `customer_id` không trỏ tới customer hợp lệ. `NOT NULL` bảo đảm đơn hàng bắt buộc phải có khách hàng. Nếu cột nullable và không có `NOT NULL`, giá trị `NULL` thường được chấp nhận vì không có giá trị tham chiếu để kiểm tra; chi tiết còn tùy hệ quản trị.

Khóa ngoại bảo vệ tính toàn vẹn tham chiếu (referential integrity). Nó không tự tạo object graph trong Java, không tự tải customer khi đọc order và cũng không đồng nghĩa với cascade thao tác entity trong ORM. Spring Data Relational R2DBC ánh xạ các cột theo metadata; quan hệ ở database vẫn được thực thi bởi database.

### Khóa ngoại trong entity Spring Data R2DBC

Một cách biểu diễn đơn giản là lưu ID của đối tượng được tham chiếu:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @Column("created_at")
    private LocalDateTime createdAt;

    // Constructor, getters và các phương thức miền cần thiết.
}
```

`customerId` ánh xạ tới cột `customer_id`. Constraint `fk_orders_customer` được khai báo trong schema và database kiểm tra khi ghi. Việc Java field có tên `customerId` không tự tạo khóa ngoại; schema phải được tạo bằng migration hoặc công cụ quản lý schema.

Khi cần thông tin khách hàng, service có thể ghép hai truy vấn reactive, dùng truy vấn join phù hợp hoặc thiết kế projection. Không nên giả định R2DBC có lazy loading và navigation proxy giống JPA/Hibernate.

## 4. Chọn hành vi khi bản ghi được tham chiếu bị xóa

Khi một hàng cha đang được hàng con tham chiếu, database cần biết xử lý thế nào nếu ứng dụng xóa hoặc thay đổi khóa của hàng cha. Các hành vi phổ biến gồm:

| Hành vi | Ý nghĩa | Trường hợp sử dụng |
| --- | --- | --- |
| `RESTRICT` | Từ chối xóa/thay đổi hàng cha khi còn hàng con tham chiếu; thời điểm kiểm tra cụ thể tùy hệ quản trị | Dữ liệu con cần được xử lý rõ ràng trước khi xóa cha |
| `NO ACTION` | Không thực hiện hành động tự động; database kiểm tra constraint theo quy tắc và thời điểm của hệ quản trị | Muốn database từ chối thao tác vi phạm quan hệ |
| `CASCADE` | Xóa hoặc cập nhật khóa tương ứng ở hàng con khi hàng cha bị xóa hoặc khóa được cập nhật | Hàng con thực sự thuộc vòng đời của hàng cha và được phép xóa cùng |
| `SET NULL` | Đặt cột khóa ngoại ở hàng con thành `NULL` khi hàng cha bị xóa hoặc khóa được cập nhật | Quan hệ là tùy chọn và hàng con vẫn có ý nghĩa độc lập |
| `SET DEFAULT` | Đặt cột khóa ngoại về giá trị mặc định | Chỉ phù hợp khi giá trị mặc định hợp lệ và có ý nghĩa miền |

Ví dụ cấm xóa khách hàng nếu vẫn còn đơn hàng:

```sql
CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES customer(id)
    ON DELETE RESTRICT
```

Ví dụ cho phép xóa các dòng địa chỉ phụ thuộc hoàn toàn vào khách hàng:

```sql
CONSTRAINT fk_customer_address
    FOREIGN KEY (customer_id)
    REFERENCES customer(id)
    ON DELETE CASCADE
```

Chỉ dùng `CASCADE` khi việc xóa hàng con là đúng với vòng đời nghiệp vụ. Xóa một customer không nhất thiết có nghĩa phải xóa hóa đơn, lịch sử giao dịch hoặc đơn hàng đã phát sinh. Với dữ liệu cần lưu dấu vết kiểm toán, thường phải dùng quy trình lưu trữ, ẩn danh hoặc soft delete thay vì cascade xóa vật lý.

`SET NULL` yêu cầu cột khóa ngoại cho phép null. Nếu cột có `NOT NULL`, thao tác sẽ không thể hoàn tất theo hành vi đó. Cũng cần xem xét chuỗi cascade qua nhiều bảng, trigger và quy tắc lưu trữ trước khi chọn hành vi.

## 5. Khóa ngoại nhiều cột và ràng buộc tenant

Trong hệ thống multi-tenant, chỉ kiểm tra `customer_id` tồn tại có thể chưa đủ. Một order của tenant A không được tham chiếu tới customer của tenant B. Có thể bảo vệ quan hệ này bằng khóa ngoại ghép gồm cả `tenant_id` và `customer_id`.

```sql
CREATE TABLE customer (
    id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(200) NOT NULL,
    CONSTRAINT pk_customer PRIMARY KEY (id),
    CONSTRAINT uq_customer_tenant_id UNIQUE (tenant_id, id)
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer_tenant
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customer(tenant_id, id)
);
```

Khóa duy nhất `(tenant_id, id)` ở bảng customer tạo khóa mục tiêu hợp lệ cho foreign key ghép. Khi insert order, database kiểm tra cả hai giá trị cùng thuộc một customer. Nhờ vậy, một `customer_id` có thể tồn tại nhưng không thể được tham chiếu từ tenant sai.

Ở tầng ứng dụng, vẫn phải xác thực người dùng có quyền thao tác trên tenant đó. Constraint bảo vệ dữ liệu trước sai sót hoặc đường ghi không tuân thủ, nhưng không thay thế kiểm soát truy cập và authorization.

## 6. Ràng buộc duy nhất trên một cột

`UNIQUE` bảo đảm không có hai hàng cùng giá trị ở cột hoặc tổ hợp cột được chỉ định theo ngữ nghĩa của hệ quản trị. Ví dụ mã tài khoản phải duy nhất:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    account_code VARCHAR(50) NOT NULL,
    CONSTRAINT uq_account_code UNIQUE (account_code)
);
```

Khi một request tạo account với `account_code` đã được sử dụng, database từ chối insert. Điều này bảo vệ dữ liệu kể cả khi hai request đồng thời cùng thử đăng ký một mã.

Có thể tạo unique constraint bằng DDL trong migration. Một số database cũng hỗ trợ unique index trực tiếp. Về mặt thiết kế, hãy dùng tên constraint có ý nghĩa để dễ nhận diện khi xử lý lỗi và kiểm tra schema.

## 7. Ràng buộc duy nhất ghép nhiều cột

Nhiều quy tắc chỉ yêu cầu duy nhất trong một phạm vi, không phải trên toàn bảng. Ví dụ email chỉ cần duy nhất trong từng tenant:

```sql
ALTER TABLE customer
    ADD CONSTRAINT uq_customer_tenant_email
    UNIQUE (tenant_id, email_normalized);
```

Constraint ghép bảo đảm không có hai hàng cùng `tenant_id` và `email_normalized`. Hai tenant khác nhau có thể có cùng email nếu nghiệp vụ cho phép.

Các ví dụ khác về unique ghép:

- `(tenant_id, external_reference)` để mã tham chiếu bên ngoài duy nhất trong từng tenant.
- `(warehouse_id, product_id)` để mỗi sản phẩm chỉ có một dòng tồn kho trong mỗi kho.
- `(room_id, booking_date, time_slot)` để giới hạn một tổ hợp phòng, ngày và khung giờ.
- `(country_code, tax_identifier)` nếu mã số thuế chỉ cần duy nhất trong từng quốc gia.

Hãy xác định đúng phạm vi nghiệp vụ trước khi tạo constraint. Nếu tạo unique trên `email` toàn cục trong khi yêu cầu thực tế chỉ là unique theo tenant, ứng dụng sẽ từ chối các trường hợp hợp lệ. Nếu bỏ `tenant_id` trong một quy tắc cần unique theo tenant, dữ liệu có thể bị trùng trong cùng phạm vi.

## 8. NULL và unique constraint

Ý nghĩa của `NULL` trong unique constraint dễ gây nhầm lẫn. Nhiều hệ quản trị, bao gồm PostgreSQL theo mặc định, cho phép nhiều hàng có `NULL` trong cột unique vì `NULL` không được xem là một giá trị bằng nhau theo phép so sánh thông thường. Một số database có tùy chọn hoặc quy tắc khác; cần kiểm tra tài liệu hệ quản trị cụ thể.

Nếu nghiệp vụ yêu cầu mọi hàng đều phải có giá trị và giá trị đó duy nhất, hãy kết hợp `NOT NULL` với `UNIQUE`:

```sql
CREATE TABLE user_account (
    id BIGINT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    CONSTRAINT uq_user_account_username UNIQUE (username)
);
```

Với unique ghép, nếu một trong các cột có thể null, hành vi có thể khác điều mong đợi. Không nên dùng null như một cách biểu diễn “chưa biết” rồi giả định constraint sẽ giới hạn số hàng chưa biết. Nếu quy tắc miền cần tối đa một giá trị vắng mặt, hãy chọn thiết kế và constraint phù hợp với hệ quản trị.

## 9. Chuẩn hóa giá trị trước khi áp dụng unique

Ràng buộc duy nhất so sánh giá trị theo collation và quy tắc của database. Ví dụ `User@example.com` và `user@example.com` có thể được xem là khác nhau trong một cấu hình, nhưng được xem là tương đương trong cấu hình khác. Khoảng trắng đầu/cuối hoặc cách chuẩn hóa Unicode cũng có thể ảnh hưởng.

Nếu nghiệp vụ yêu cầu so sánh không phân biệt hoa thường hoặc theo dạng chuẩn hóa, hãy xác định một quy tắc canonicalization rõ ràng và áp dụng nhất quán. Một lựa chọn là lưu thêm cột chuẩn hóa:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    CONSTRAINT uq_customer_email_normalized UNIQUE (email_normalized)
);
```

Ứng dụng tính `email_normalized` theo quy tắc đã thống nhất trước khi lưu. Nếu database hỗ trợ generated column hoặc functional index phù hợp, có thể cân nhắc chuẩn hóa ngay trong database. Cú pháp và semantics phụ thuộc hệ quản trị.

Không nên tự ý lowercase mọi phần của mọi định danh nếu quy tắc nghiệp vụ không cho phép. Cần xác định rõ cách xử lý Unicode, khoảng trắng, dấu, locale và những trường hợp đặc biệt. Database constraint chỉ bảo vệ giá trị được lưu; nó không tự biết quy tắc chuẩn hóa mà sản phẩm mong muốn.

## 10. Soft delete và tính duy nhất

Soft delete thường giữ hàng trong database và đánh dấu `deleted_at` hoặc `is_deleted`. Nếu unique constraint vẫn áp dụng trên toàn bộ hàng, một tài khoản đã bị soft delete vẫn chiếm giá trị username/email, nên không thể tạo bản ghi mới dùng lại giá trị đó.

Nếu nghiệp vụ cho phép tái sử dụng giá trị sau khi xóa mềm, cần thiết kế uniqueness theo trạng thái hoạt động. PostgreSQL hỗ trợ partial unique index:

```sql
CREATE UNIQUE INDEX uq_active_customer_email
    ON customer (tenant_id, email_normalized)
    WHERE deleted_at IS NULL;
```

Đây là cú pháp riêng của PostgreSQL, không phải cú pháp portable cho mọi database. Với hệ quản trị khác, có thể cần generated column, cột trạng thái hoặc một mô hình dữ liệu khác. Phải bảo đảm cách kiểm tra ở ứng dụng trùng khớp chính xác với predicate của index.

Soft delete cũng ảnh hưởng tới khóa ngoại. Hàng bị đánh dấu xóa vẫn tồn tại vật lý nên foreign key vẫn xem nó là bản ghi được tham chiếu hợp lệ. Nếu nghiệp vụ không cho phép tạo order mới với customer đã xóa mềm, cần kiểm tra trạng thái trong service/domain và bảo vệ thao tác phù hợp bằng transaction hoặc mô hình dữ liệu. Foreign key thông thường không kiểm tra cột `deleted_at` của hàng cha.

## 11. CHECK constraint cho quy tắc trên một hàng

`CHECK` bảo đảm một biểu thức đúng cho mỗi hàng được insert hoặc update. Ví dụ số lượng và giá không âm:

```sql
CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_order_line_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_line_unit_price CHECK (unit_price >= 0)
);
```

`NOT NULL` vẫn cần thiết. Trong SQL, biểu thức `CHECK` thường được xem là hợp lệ nếu kết quả là `TRUE` hoặc `UNKNOWN` (do `NULL`); vì vậy `CHECK (quantity > 0)` không tự ngăn `quantity = NULL` ở những hệ quản trị áp dụng semantics này. Kết hợp `NOT NULL` để bảo vệ trường bắt buộc.

Một số bất biến khác có thể biểu diễn bằng `CHECK`:

```sql
ALTER TABLE account
    ADD CONSTRAINT ck_account_balance_nonnegative
    CHECK (balance >= 0);

ALTER TABLE booking
    ADD CONSTRAINT ck_booking_time_range
    CHECK (ends_at > starts_at);
```

Các biểu thức `CHECK` thường được đánh giá trên một hàng. Không dùng chúng như cơ chế tổng quát để kiểm tra tổng hợp nhiều hàng hoặc truy vấn bảng khác; hỗ trợ và hành vi có thể khác giữa các hệ quản trị. Những bất biến liên hàng cần constraint chuyên biệt, transaction, khóa hoặc thiết kế dữ liệu phù hợp.

## 12. Phân biệt constraint và validation ở tầng ứng dụng

Validation và constraint giải quyết các mục tiêu bổ sung nhau:

| Vị trí | Mục tiêu | Ví dụ |
| --- | --- | --- |
| API/request validation | Từ chối đầu vào sai định dạng sớm và trả lỗi dễ hiểu | Email thiếu định dạng, số lượng không hợp lệ |
| Domain/service | Kiểm tra quy tắc nghiệp vụ và quyền thực hiện hành động | Không cho đặt hàng nếu customer không thuộc tenant hiện tại |
| Database constraint | Bảo vệ trạng thái lưu trước mọi đường ghi và cạnh tranh đồng thời | Unique email, FK customer, check số lượng dương |
| Transaction | Bảo đảm một nhóm thao tác liên quan cùng thành công hoặc rollback theo chính sách | Tạo order và các order line trong một transaction |

Ví dụ, service có thể kiểm tra email đã tồn tại trước khi tạo tài khoản để trả phản hồi nhanh. Nhưng unique constraint vẫn cần thiết vì hai request có thể cùng kiểm tra thấy email chưa tồn tại rồi cùng insert. Chỉ database có thể phân xử một cách nguyên tử giữa hai thao tác ghi cạnh tranh đó.

Không nên loại bỏ validation chỉ vì database có constraint. Nếu đợi tới lúc insert mới biết email không hợp lệ, người dùng có thể nhận lỗi kỹ thuật khó hiểu. Ngược lại, không nên chỉ dựa vào validation và bỏ constraint đối với bất biến cần được bảo vệ ở cấp dữ liệu.

## 13. Race condition khi kiểm tra trước khi ghi

Một lỗi phổ biến là thực hiện quy trình “check rồi insert” như thể hai bước đó là nguyên tử:

```java
public Mono<Customer> register(String email) {
    return customerRepository.existsByEmail(email)
            .flatMap(exists -> {
                if (exists) {
                    return Mono.error(new EmailAlreadyRegisteredException());
                }

                return customerRepository.save(Customer.newCustomer(email));
            });
}
```

Đoạn mã giúp báo sớm khi email đã có, nhưng không đủ để bảo đảm duy nhất. Hai request có thể chạy như sau:

```text
Request A                 Database                 Request B
    |                         |                         |
    |---- check email ------->|<------ check email -----|
    |<--- not found ----------|---------- not found ----|
    |                         |                         |
    |---- insert email ------>|<------ insert email ----|
    |                         |                         |
    |<--- insert succeeds ----|---- unique violation -->|
```

Unique constraint khiến tối đa một insert thành công. Request còn lại nhận lỗi vi phạm constraint. Nếu không có constraint, cả hai có thể thành công và tạo dữ liệu trùng.

Do đó, có thể giữ bước kiểm tra trước để cải thiện trải nghiệm, nhưng kết quả insert và unique constraint mới là quyết định cuối cùng. Luôn xử lý lỗi duplicate ở đường ghi.

## 14. Xử lý lỗi constraint trong Spring Data R2DBC

Khi database từ chối thao tác vì vi phạm unique, foreign key, check hoặc not-null, driver phát lỗi và lỗi được truyền qua publisher. Spring có thể chuyển một số lỗi của driver thành các exception trong hệ thống `DataAccessException`, ví dụ `DuplicateKeyException` hoặc `DataIntegrityViolationException`, tùy driver và ngữ cảnh thực thi.

Có thể xử lý lỗi trùng khóa đã được nhận diện ở service:

```java
public Mono<Customer> register(String email) {
    Customer customer = Customer.newCustomer(email);

    return customerRepository.save(customer)
            .onErrorMap(DuplicateKeyException.class,
                    error -> new EmailAlreadyRegisteredException());
}
```

Ví dụ giả định exception translation của đường truy cập dữ liệu ánh xạ lỗi unique thành `DuplicateKeyException`. Cần kiểm tra driver và phiên bản thực tế. Một số lỗi constraint có thể chỉ được ánh xạ thành `DataIntegrityViolationException` hoặc exception riêng của driver. Không nên chuyển mọi lỗi integrity thành “email đã tồn tại” vì nguyên nhân có thể là FK, CHECK hoặc NOT NULL.

Nếu cần phân biệt nhiều constraint, hãy dựa trên loại lỗi, tên constraint hoặc mã lỗi database mà driver cung cấp. Nên gom việc chuyển lỗi hạ tầng thành lỗi miền tại một ranh giới rõ ràng, rồi để controller/API ánh xạ thành status code thích hợp. Ví dụ duplicate thường có thể trở thành HTTP 409 Conflict; dữ liệu đầu vào sai định dạng có thể là 400 Bad Request. Quyết định cụ thể phụ thuộc hợp đồng API.

Không log password, URL có credentials hoặc toàn bộ dữ liệu nhạy cảm trong exception. Log mã lỗi và tên constraint khi an toàn, kèm correlation ID để truy vết request.

## 15. Khóa ngoại và thứ tự thao tác trong transaction

Khi tạo dữ liệu cha và con, cần bảo đảm bản ghi cha tồn tại trước khi bản ghi con tham chiếu tới nó, trừ khi database và constraint được cấu hình hỗ trợ kiểm tra trì hoãn theo một cách phù hợp. Cách đơn giản và phổ biến là lưu parent, nhận ID, rồi lưu child trong cùng transaction:

```java
public Mono<Order> createOrder(Order order, List<OrderLine> lines) {
    return transactionalOperator.transactional(
            orderRepository.save(order)
                    .flatMap(savedOrder ->
                            Flux.fromIterable(lines)
                                    .map(line -> line.withOrderId(savedOrder.getId()))
                                    .concatMap(orderLineRepository::save)
                                    .then(Mono.just(savedOrder))
                    )
    );
}
```

Đoạn mã minh họa cách nối các thao tác trong một publisher transaction. `withOrderId` đại diện cho phương thức tạo bản sao line có gắn ID order theo mô hình entity của ứng dụng. Nếu một dòng con lưu thất bại, lỗi đi qua pipeline để transaction manager có thể rollback các thao tác đã tham gia transaction.

Với `Flux`, cần chọn concurrency có chủ đích. Nếu các thao tác ghi con độc lập và database cho phép, có thể cân nhắc xử lý song song trong phạm vi transaction. Nếu cần thứ tự hoặc muốn giảm áp lực lên pool, `concatMap` thực hiện tuần tự. Không gọi `subscribe()` riêng cho từng dòng vì như vậy có thể tách chúng khỏi transaction và luồng lỗi của thao tác tạo order.

## 16. Bất biến liên quan nhiều hàng và cập nhật đồng thời

Không phải bất biến nào cũng là một unique hoặc check constraint đơn giản. Ví dụ, tổng số lượng đặt trước không được vượt quá sức chứa của một sự kiện. Nếu service chỉ đọc tổng hiện tại, kiểm tra còn chỗ rồi insert, hai request đồng thời có thể cùng thấy còn một chỗ và cùng đặt chỗ cuối cùng.

Một số cách thiết kế có thể bảo vệ loại bất biến này:

- Thực hiện cập nhật có điều kiện nguyên tử, ví dụ chỉ tăng `reserved_count` khi `reserved_count + requested <= capacity`, rồi kiểm tra số hàng bị ảnh hưởng.
- Dùng transaction với mức isolation hoặc cơ chế khóa phù hợp để tuần tự hóa những thao tác cạnh tranh.
- Biểu diễn tài nguyên có thể đặt trước thành các hàng riêng và dùng unique constraint để bảo đảm mỗi tài nguyên chỉ được đặt một lần trong cùng phạm vi thời gian.
- Dùng optimistic locking/version nếu mô hình và phiên bản Spring Data hỗ trợ, sau đó xử lý xung đột cập nhật bằng cách đọc lại hoặc báo lỗi phù hợp.

Ví dụ cập nhật có điều kiện theo SQL PostgreSQL:

```sql
UPDATE event_capacity
SET reserved_count = reserved_count + :requested
WHERE event_id = :eventId
  AND reserved_count + :requested <= capacity;
```

Nếu số hàng cập nhật bằng 1, thao tác đã giữ được chỗ theo điều kiện. Nếu bằng 0, sự kiện không tồn tại hoặc không còn đủ sức chứa; service có thể phân biệt hai trường hợp bằng truy vấn hoặc quy tắc nghiệp vụ bổ sung. Câu lệnh là một thao tác nguyên tử ở database đối với hàng được cập nhật, tránh khoảng trống giữa bước đọc và bước ghi riêng biệt.

## 17. Thiết kế aggregate và quan hệ trong Spring Data Relational

Spring Data Relational không phải JPA. Không nên thiết kế entity với kỳ vọng có lazy-loading proxy, cascade persistence hoặc object graph tự động như Hibernate. Mô hình aggregate giúp xác định ranh giới dữ liệu được lưu cùng nhau và trách nhiệm cập nhật của từng phần.

Với một order có nhiều order line, có thể coi `Order` là aggregate root và `OrderLine` là dữ liệu thuộc vòng đời của order. Spring Data Relational có các annotation như `@MappedCollection` để ánh xạ collection được quản lý bởi aggregate root trong các mô hình phù hợp. DDL vẫn cần có primary key và foreign key tương ứng; annotation mapping không thay thế constraint.

Với quan hệ giữa hai aggregate độc lập, ví dụ `Order` và `Customer`, thường lưu ID tham chiếu (`customerId`) và truy vấn aggregate cần thiết một cách tường minh. Điều này giúp tránh vô tình tải hoặc cập nhật một mạng lưới object lớn chỉ vì một thuộc tính quan hệ.

Chọn ranh giới aggregate theo quy tắc nhất quán của domain. Nếu hai phần dữ liệu phải thay đổi nguyên tử, cần thiết kế transaction và quan hệ sở hữu rõ ràng. Nếu chúng có vòng đời độc lập, giữ tham chiếu bằng ID thường làm trách nhiệm ghi dữ liệu dễ hiểu hơn.

## 18. Index và hiệu năng của khóa ngoại, unique

Unique constraint thường được database triển khai bằng một unique index hoặc cấu trúc tương đương. Index này vừa giúp kiểm tra trùng lặp vừa có thể tăng tốc truy vấn theo các cột unique. Không cần tạo thêm một index trùng hoàn toàn nếu database đã tạo index cho constraint đó.

Đối với cột ở phía bảng con của foreign key, không phải hệ quản trị nào cũng tự tạo index. PostgreSQL chẳng hạn không tự động tạo index trên cột tham chiếu ở bảng con. Index trên `orders.customer_id` có thể giúp truy vấn order theo customer và giúp một số thao tác xóa/cập nhật ở bảng cha kiểm tra hàng tham chiếu nhanh hơn.

Ví dụ:

```sql
CREATE INDEX ix_orders_customer_id ON orders(customer_id);
```

Với foreign key ghép `(tenant_id, customer_id)`, hãy xem các truy vấn thực tế và cân nhắc index ghép có thứ tự cột phù hợp:

```sql
CREATE INDEX ix_orders_tenant_customer
    ON orders(tenant_id, customer_id);
```

Index cũng có chi phí ghi và lưu trữ. Không tạo index theo cảm tính; dùng query plan, tần suất truy vấn, số hàng và chi phí cập nhật để quyết định. Unique constraint và foreign key có vai trò toàn vẹn; index bổ sung chủ yếu phục vụ hiệu năng và không thay thế quy tắc dữ liệu.

## 19. Quản lý constraint bằng database migration

Schema và constraint nên được quản lý bằng migration có version thay vì chỉ dựa vào entity annotation hoặc thay đổi thủ công trên database production. Migration giúp các môi trường phát triển, kiểm thử và production có cùng cấu trúc dữ liệu có thể tái lập.

Ví dụ một migration SQL:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    CONSTRAINT uq_customer_tenant_email
        UNIQUE (tenant_id, email_normalized)
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer_tenant
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customer(tenant_id, id)
        ON DELETE RESTRICT
);

CREATE INDEX ix_orders_tenant_customer
    ON orders(tenant_id, customer_id);
```

Đây là ví dụ PostgreSQL; `GENERATED BY DEFAULT AS IDENTITY` và cú pháp index có thể cần điều chỉnh theo database khác. Với Spring Boot, Flyway hoặc Liquibase thường được dùng để quản lý migration. Các công cụ migration thường chạy qua cơ chế JDBC hoặc cơ chế riêng của chúng; việc ứng dụng runtime dùng R2DBC không có nghĩa mọi công cụ migration tự động chạy qua R2DBC. Cần cấu hình migration riêng và bảo đảm nó hoàn tất trước khi ứng dụng phụ thuộc schema mới.

Khi thêm constraint vào bảng đã có dữ liệu, migration có thể thất bại nếu dữ liệu hiện tại vi phạm quy tắc. Quy trình an toàn thường gồm:

1. Thống kê và tìm dữ liệu trùng, null hoặc tham chiếu mồ côi.
2. Xác định cách sửa, gộp hoặc loại bỏ dữ liệu vi phạm theo quyết định nghiệp vụ.
3. Triển khai thay đổi ứng dụng theo thứ tự tương thích nếu cần, ví dụ ghi dữ liệu theo định dạng mới trước khi bắt buộc constraint.
4. Thêm constraint/index bằng migration có kiểm soát thời gian khóa và ảnh hưởng tới workload.
5. Kiểm tra schema và dữ liệu sau migration ở môi trường tương ứng.

Không xóa constraint chỉ để migration chạy qua mà chưa hiểu ảnh hưởng đến bất biến. Nếu bảng lớn, cần xem chiến lược tạo index/constraint online hoặc concurrent theo khả năng của database.

## 20. Kiểm thử tính toàn vẹn dữ liệu

Unit test cho service có thể xác minh validation và cách xử lý lỗi, nhưng không chứng minh database thực sự thực thi foreign key hoặc unique constraint. Nên có integration test với hệ quản trị tương thích để xác nhận hành vi thật.

Các tình huống nên được kiểm thử gồm:

- Insert order với `customer_id` tồn tại thành công.
- Insert order với `customer_id` không tồn tại bị từ chối.
- Xóa customer còn order tham chiếu bị từ chối nếu dùng `RESTRICT`.
- Hai request đồng thời tạo cùng giá trị unique: tối đa một request thành công.
- Unique ghép cho phép cùng email ở tenant khác nhau nhưng từ chối trùng trong cùng tenant.
- Giá trị null hoặc số âm bị chặn đúng theo `NOT NULL` và `CHECK`.
- Lỗi ở một thao tác con làm transaction rollback các thay đổi liên quan.
- Soft delete có hành vi uniqueness đúng theo quy tắc tái sử dụng giá trị.

Với kiểm thử reactive, có thể dùng Reactor Test `StepVerifier` để xác minh publisher hoàn tất thành công hoặc phát lỗi. Đối với tình huống cạnh tranh, nên tạo nhiều subscription đồng thời trong integration test và xác minh trạng thái cuối ở database, không chỉ xác minh loại exception ở một request.

## 21. Nguyên tắc thực hành

- Định nghĩa bất biến dữ liệu rõ ràng trước khi thiết kế bảng và quan hệ.
- Dùng primary key cho định danh, foreign key cho tính toàn vẹn tham chiếu và unique constraint cho giá trị/tổ hợp cần duy nhất.
- Kết hợp `NOT NULL` với `UNIQUE` khi trường bắt buộc phải có giá trị.
- Dùng `CHECK` cho điều kiện trên một hàng và xác định riêng các quy tắc liên hàng cần transaction hoặc cơ chế đồng thời.
- Chọn `ON DELETE` theo vòng đời nghiệp vụ; không dùng cascade chỉ vì muốn xóa dữ liệu dễ dàng.
- Với multi-tenant, cân nhắc unique và foreign key ghép để ngăn tham chiếu chéo tenant.
- Xác định quy tắc chuẩn hóa trước khi tạo unique cho email, username hoặc mã định danh.
- Giữ validation ở tầng ứng dụng để trả lỗi rõ ràng, nhưng để database constraint phân xử các lần ghi cạnh tranh.
- Bắt và phân loại lỗi constraint trong reactive pipeline; không chuyển mọi lỗi integrity thành cùng một lỗi nghiệp vụ.
- Quản lý schema bằng migration và kiểm thử constraint trên database tương thích.
- Thiết kế aggregate phù hợp với Spring Data Relational; không giả định có cơ chế quan hệ và cascade giống JPA.
- Tạo index bổ sung dựa trên truy vấn và query plan, không tạo trùng index do unique constraint đã sinh.

## 22. Kết luận

Khóa ngoại bảo vệ quan hệ giữa các bảng, unique constraint bảo vệ tính duy nhất của một giá trị hoặc tổ hợp giá trị, còn `NOT NULL` và `CHECK` bảo vệ các điều kiện cơ bản của từng hàng. Những ràng buộc này là nền tảng để dữ liệu vẫn đúng khi có nhiều request, nhiều instance và nhiều đường ghi khác nhau cùng truy cập database.

Trong Spring Data Relational R2DBC, entity mapping và reactive repository giúp tổ chức thao tác dữ liệu, còn database constraint bảo vệ tính toàn vẹn ở cấp lưu trữ. Kết hợp validation, transaction reactive, xử lý lỗi constraint và migration có kiểm soát sẽ giúp ứng dụng duy trì bất biến nghiệp vụ mà không phụ thuộc vào một đoạn kiểm tra đơn lẻ ở service.
