# Biểu diễn quan hệ một-một bằng khóa ngoại

Quan hệ một-một (one-to-one) mô tả hai bảng có liên hệ sao cho mỗi bản ghi ở một phía gắn với tối đa một bản ghi ở phía còn lại. Trong mô hình quan hệ, cách phổ biến để biểu diễn quan hệ này là đặt khóa ngoại (foreign key) ở một bảng và thêm ràng buộc duy nhất (UNIQUE) cho cột khóa ngoại.

Một khóa ngoại đơn lẻ chưa đủ để tạo quan hệ một-một. Nếu nhiều hàng có thể chứa cùng một giá trị khóa ngoại, quan hệ đó là nhiều-một (many-to-one). Ràng buộc UNIQUE mới giới hạn mỗi bản ghi được tham chiếu bởi tối đa một hàng ở bảng chứa khóa ngoại.

Trong Spring Data Relational R2DBC, cần phân biệt cấu trúc quan hệ ở database với mô hình object Java. R2DBC không dùng annotation JPA `@OneToOne` để tự động tạo và quản lý object graph. Ứng dụng cần thiết kế khóa ngoại và constraint trong schema, ánh xạ các bảng thành entity phù hợp, rồi đọc hoặc ghi dữ liệu liên quan bằng repository, SQL hoặc `DatabaseClient` theo ranh giới aggregate.

Bài học này trình bày cách chọn vị trí khóa ngoại, cách bảo đảm tính một-một bằng constraint, cách mô hình hóa entity trong Spring Data R2DBC, cách truy vấn hai bảng và cách duy trì tính nhất quán khi ghi hoặc xóa dữ liệu.

## 1. Ý nghĩa của quan hệ một-một

Giả sử một hệ thống quản lý khách hàng và hồ sơ cá nhân. Mỗi hồ sơ thuộc về một khách hàng, và một khách hàng có tối đa một hồ sơ.

Hai bảng:

- `customer`: lưu dữ liệu chính của khách hàng.
- `customer_profile`: lưu thông tin hồ sơ mở rộng.

Ví dụ:

~~~text
customer
+----+-------------+
| id | full_name   |
+----+-------------+
| 10 | Nguyen An   |
| 11 | Tran Binh   |
+----+-------------+

customer_profile
+----+------------+----------------+
| id | customer_id| date_of_birth  |
+----+------------+----------------+
| 50 | 10         | 1995-04-12     |
| 51 | 11         | 1990-09-23     |
+----+------------+----------------+
~~~

Cột `customer_profile.customer_id` tham chiếu `customer.id`. Nếu mỗi khách hàng chỉ được có tối đa một hồ sơ, cột này phải có ràng buộc `UNIQUE`.

Quan hệ một-một thường có hai cách hiểu về tính bắt buộc:

- **Một-một tùy chọn:** một khách hàng có thể chưa có hồ sơ; nếu có thì chỉ có một.
- **Một-một bắt buộc theo một chiều:** mỗi hồ sơ phải thuộc về đúng một khách hàng, và một khách hàng có tối đa một hồ sơ. Khách hàng vẫn có thể chưa có hồ sơ.

Đây là điểm cần phân biệt: khóa ngoại `NOT NULL` trên bảng con bảo đảm mỗi hàng con có hàng cha. Nó không bảo đảm mọi hàng cha đều có hàng con. Muốn mọi khách hàng luôn có hồ sơ, cần thêm quy tắc ở tầng nghiệp vụ hoặc chọn thiết kế dữ liệu phù hợp hơn.

## 2. Khóa ngoại đơn lẻ chưa tạo quan hệ một-một

Giả sử bảng hồ sơ có khóa ngoại:

~~~sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    date_of_birth DATE,
    CONSTRAINT fk_profile_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Ràng buộc foreign key bảo đảm `customer_id` phải tham chiếu tới một khách hàng hợp lệ. Tuy nhiên, schema này vẫn cho phép nhiều hàng hồ sơ cùng tham chiếu một khách hàng:

~~~text
customer_profile
+----+------------+
| id | customer_id|
+----+------------+
| 50 | 10         |
| 52 | 10         |
+----+------------+
~~~

Đây là quan hệ nhiều-một từ `customer_profile` tới `customer`, vì hai hồ sơ có thể cùng thuộc khách hàng 10.

Để giới hạn một hồ sơ cho mỗi khách hàng, thêm UNIQUE:

~~~sql
ALTER TABLE customer_profile
ADD CONSTRAINT uk_profile_customer UNIQUE (customer_id);
~~~

Hoặc khai báo ngay khi tạo bảng:

~~~sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL UNIQUE,
    date_of_birth DATE,
    CONSTRAINT fk_profile_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Lúc này:

- Foreign key bảo đảm hồ sơ không trỏ tới khách hàng không tồn tại.
- UNIQUE bảo đảm một khách hàng không bị nhiều hồ sơ tham chiếu.
- NOT NULL bảo đảm mỗi hàng hồ sơ phải có khách hàng.

Ba điều kiện có ý nghĩa khác nhau và thường được dùng cùng nhau.

## 3. Chọn bảng đặt khóa ngoại

Khóa ngoại thường được đặt ở bảng phụ thuộc hoặc bảng có vòng đời phụ thuộc vào bảng còn lại. Với ví dụ khách hàng và hồ sơ, `customer_profile` thường là bảng phụ thuộc vì hồ sơ không có ý nghĩa nếu không gắn với khách hàng.

### 3.1. Đặt khóa ngoại ở bảng phụ thuộc

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL UNIQUE,
    date_of_birth DATE,
    address VARCHAR(300),
    CONSTRAINT fk_profile_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Ưu điểm:

- Bảng chính không phải chứa cột nullable chỉ để trỏ tới dữ liệu mở rộng.
- Bảng phụ thuộc thể hiện rõ nó cần một hàng cha.
- Có thể xóa hồ sơ mà không xóa khách hàng, tùy quy tắc nghiệp vụ.
- Có thể thêm dữ liệu mở rộng theo module mà không làm bảng chính quá rộng.

Với thiết kế này, mỗi hồ sơ bắt buộc thuộc một khách hàng; khách hàng có thể có hoặc chưa có hồ sơ.

### 3.2. Đặt khóa ngoại ở bảng chính

Cũng có thể đặt `profile_id` ở bảng `customer`:

~~~sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    date_of_birth DATE,
    address VARCHAR(300)
);

CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    profile_id BIGINT UNIQUE,
    CONSTRAINT fk_customer_profile
        FOREIGN KEY (profile_id) REFERENCES customer_profile(id)
);
~~~

`UNIQUE(profile_id)` bảo đảm một hồ sơ không được nhiều khách hàng sử dụng. Nếu `profile_id` nullable, khách hàng có thể chưa có hồ sơ.

Đặt khóa ngoại ở bảng chính có thể phù hợp khi khách hàng là phía luôn sở hữu tham chiếu đến hồ sơ. Tuy nhiên, cần xem xét thứ tự insert: phải tạo hồ sơ trước để lấy `profile_id`, rồi mới tạo khách hàng, trừ khi database hỗ trợ constraint trì hoãn và ứng dụng chủ động dùng tính năng đó.

### 3.3. Tiêu chí chọn vị trí

| Tiêu chí | Khóa ngoại ở bảng phụ thuộc | Khóa ngoại ở bảng chính |
|---|---|---|
| Ví dụ | `profile.customer_id` | `customer.profile_id` |
| Phù hợp khi | Bản ghi phụ thuộc cần biết chủ sở hữu | Bản ghi chính luôn tham chiếu dữ liệu phụ |
| Tạo dữ liệu | Tạo hàng chính trước, hàng phụ sau | Thường tạo hàng được tham chiếu trước |
| Xóa dữ liệu phụ | Có thể xóa riêng hàng phụ | Phải xử lý tham chiếu từ hàng chính |
| Khả năng biểu diễn tùy chọn | Parent có thể không có child | FK nullable cho phép parent không có reference |
| Constraint một-một | UNIQUE trên FK | UNIQUE trên FK |

Chọn vị trí dựa trên quyền sở hữu, vòng đời, thứ tự tạo và cách truy vấn thường xuyên. Cả hai thiết kế đều có thể biểu diễn một-một nếu có ràng buộc phù hợp.

## 4. Dùng khóa chính đồng thời làm khóa ngoại

Một cách thiết kế khác là dùng chung giá trị khóa chính giữa bảng chính và bảng mở rộng. Khóa chính của bảng con đồng thời là khóa ngoại tham chiếu bảng cha.

Ví dụ:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY,
    date_of_birth DATE,
    address VARCHAR(300),
    CONSTRAINT fk_profile_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Ở đây `customer_profile.customer_id` vừa là primary key vừa là foreign key. Do khóa chính vốn đã unique, mỗi khách hàng có tối đa một hàng hồ sơ.

Ưu điểm:

- Không cần thêm một ID riêng cho bảng hồ sơ.
- Quan hệ một-một được thể hiện trực tiếp bằng shared primary key.
- Không thể có hai hàng hồ sơ cùng tham chiếu một khách hàng.

Hạn chế:

- Khóa của hồ sơ phụ thuộc vào khóa khách hàng.
- Tạo hồ sơ cần biết ID khách hàng.
- Hồ sơ không có định danh độc lập với khách hàng.
- Nếu hồ sơ cần được tham chiếu độc lập hoặc có vòng đời riêng, khóa riêng có thể linh hoạt hơn.

Shared primary key chỉ bảo đảm mỗi khách hàng có tối đa một hồ sơ; nó vẫn không bắt buộc mọi khách hàng phải có hồ sơ.

## 5. Tùy chọn, bắt buộc và tính duy nhất

Ba thuộc tính schema thường được phối hợp:

| Ràng buộc | Ý nghĩa |
|---|---|
| `FOREIGN KEY` | Giá trị phải tham chiếu hàng hợp lệ |
| `UNIQUE` | Không có hai hàng cùng giá trị khóa ngoại |
| `NOT NULL` | Mỗi hàng phải có giá trị khóa ngoại |

Ví dụ một-một tùy chọn từ khách hàng tới hồ sơ:

~~~sql
customer_id BIGINT UNIQUE
    REFERENCES customer(id)
~~~

Cột có thể null. Khi có giá trị, nó phải duy nhất và tham chiếu khách hàng hợp lệ.

Ví dụ một-một bắt buộc đối với mỗi hàng hồ sơ:

~~~sql
customer_id BIGINT NOT NULL UNIQUE
    REFERENCES customer(id)
~~~

Mỗi hồ sơ phải có một khách hàng, và mỗi khách hàng có tối đa một hồ sơ.

Lưu ý rằng cách xử lý nhiều giá trị `NULL` trong unique constraint có khác biệt giữa hệ quản trị và cấu hình cụ thể. PostgreSQL thông thường cho phép nhiều `NULL` trong unique constraint vì các giá trị null được xem là không bằng nhau; các hệ quản trị khác có thể có quy tắc khác hoặc hỗ trợ tùy chọn riêng. Hãy xác nhận hành vi trên database mục tiêu.

## 6. Referential actions khi xóa hoặc cập nhật

Khi một hàng được tham chiếu bị xóa hoặc thay đổi khóa, database cần biết xử lý các hàng phụ thuộc như thế nào.

Một số lựa chọn phổ biến:

| Hành động | Ý nghĩa |
|---|---|
| `RESTRICT` / `NO ACTION` | Ngăn thao tác nếu vẫn còn hàng tham chiếu, tùy semantics của database |
| `CASCADE` | Xóa hoặc cập nhật hàng phụ thuộc theo hàng được tham chiếu |
| `SET NULL` | Đặt khóa ngoại thành null khi hàng được tham chiếu bị xóa |
| `SET DEFAULT` | Gán giá trị mặc định nếu database hỗ trợ và giá trị đó hợp lệ |

Ví dụ dùng cascade khi hồ sơ không thể tồn tại độc lập với khách hàng:

~~~sql
CONSTRAINT fk_profile_customer
    FOREIGN KEY (customer_id)
    REFERENCES customer(id)
    ON DELETE CASCADE
~~~

Nếu nghiệp vụ yêu cầu lưu hồ sơ để kiểm toán, `CASCADE` có thể không phù hợp. Có thể dùng `RESTRICT` để buộc ứng dụng xử lý hồ sơ trước khi xóa khách hàng.

Nếu khóa ngoại nullable và muốn giữ hàng hồ sơ nhưng bỏ liên kết:

~~~sql
FOREIGN KEY (customer_id)
    REFERENCES customer(id)
    ON DELETE SET NULL
~~~

Tuy nhiên, `SET NULL` không phù hợp nếu `customer_id` có `NOT NULL`.

Không nên chọn cascade chỉ vì nó tiện cho code. Referential action phải phản ánh quy tắc lưu trữ và vòng đời dữ liệu. Database là lớp bảo vệ cuối cùng ngay cả khi một thao tác xóa không đi qua Spring Data.

## 7. Ánh xạ hai bảng thành entity trong Spring Data R2DBC

Spring Data Relational sử dụng metadata như `@Table`, `@Id` và `@Column` để ánh xạ entity với bảng. Khóa ngoại vẫn là cột trong schema; ứng dụng có thể biểu diễn giá trị khóa ngoại thành một property ID trong entity phụ thuộc.

Ví dụ entity khách hàng:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String fullName;

    // Constructor, getters và setters
}
~~~

Entity hồ sơ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer_profile")
public class CustomerProfile {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @Column("date_of_birth")
    private LocalDate dateOfBirth;

    private String address;

    // Constructor, getters và setters
}
~~~

`customerId` là giá trị foreign key. Nó cho biết hồ sơ thuộc khách hàng nào. Property này không tự động tải một object `Customer` liên quan.

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}

public interface CustomerProfileRepository
        extends ReactiveCrudRepository<CustomerProfile, Long> {

    Mono<CustomerProfile> findByCustomerId(Long customerId);
}
~~~

Vì `customer_id` có unique constraint, phương thức `findByCustomerId` có thể dùng `Mono<CustomerProfile>` để thể hiện tối đa một hồ sơ. Nếu schema không bảo vệ tính duy nhất, nên dùng `Flux<CustomerProfile>` hoặc sửa schema theo quy tắc một-một thực tế.

### 7.1. Vì sao dùng ID thay vì tự khai báo object reference?

Trong Spring Data Relational, không nên mặc định rằng khai báo:

~~~java
private Customer customer;
~~~

sẽ tạo hành vi giống JPA `@OneToOne`, tự join khi đọc và tự lưu cả hai bảng. Spring Data R2DBC không cung cấp mô hình ORM JPA với `@OneToOne`, lazy proxy và cascade persistence tương ứng.

Dùng `Long customerId` làm rõ cột khóa ngoại và cho phép ứng dụng quyết định khi nào cần tải khách hàng. Nếu cần một object kết hợp, truy vấn rõ ràng và ánh xạ sang DTO hoặc domain model ở tầng service.

### 7.2. Phân biệt aggregate root và hàng phụ thuộc

Spring Data Relational khuyến khích thiết kế theo aggregate. Nếu hồ sơ là dữ liệu thuộc sở hữu của khách hàng và luôn có cùng vòng đời với khách hàng, hãy cân nhắc biểu diễn chúng trong cùng ranh giới aggregate bằng cơ chế mapping quan hệ mà phiên bản Spring Data hỗ trợ.

Nếu khách hàng và hồ sơ có vòng đời, quyền sở hữu hoặc quy trình cập nhật độc lập, có thể coi chúng là các aggregate riêng và giữ tham chiếu bằng ID. Khi đó, ứng dụng điều phối việc đọc và ghi hai aggregate.

Không nên tạo một object graph lớn chỉ vì hai bảng có foreign key. Ranh giới aggregate nên dựa trên bất biến nghiệp vụ và quyền sở hữu dữ liệu.

## 8. Truy vấn một-một bằng derived query

Khi chỉ cần đọc hồ sơ theo khóa ngoại, derived query là cách ngắn gọn:

~~~java
public interface CustomerProfileRepository
        extends ReactiveCrudRepository<CustomerProfile, Long> {

    Mono<CustomerProfile> findByCustomerId(Long customerId);

    Mono<Boolean> existsByCustomerId(Long customerId);
}
~~~

`findByCustomerId` trả tối đa một hồ sơ nếu `customer_id` có unique constraint. `existsByCustomerId` chỉ trả lời có hay không mà không cần tải toàn bộ entity.

Có thể lấy khách hàng trước, rồi lấy hồ sơ:

~~~java
Mono<CustomerWithProfile> findCustomerDetails(Long customerId) {
    return customerRepository.findById(customerId)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(customerId)))
            .flatMap(customer ->
                    customerProfileRepository.findByCustomerId(customerId)
                            .map(profile ->
                                    CustomerWithProfile.from(customer, profile))
                            .defaultIfEmpty(
                                    CustomerWithProfile.withoutProfile(customer)));
}
~~~

Ví dụ này thể hiện hồ sơ là tùy chọn: khách hàng vẫn được trả về khi không có hồ sơ. Nếu hồ sơ bắt buộc theo nghiệp vụ, thay `defaultIfEmpty` bằng `switchIfEmpty(Mono.error(...))`.

Không gọi `subscribe()` trong service để chạy hai truy vấn riêng. Hãy kết hợp các publisher và trả về một chuỗi reactive để caller, transaction và lỗi được quản lý nhất quán.

## 9. Dùng JOIN và projection khi cần dữ liệu kết hợp

Nếu màn hình cần khách hàng cùng thông tin hồ sơ, một câu join có thể hiệu quả hơn hai lần đọc riêng.

Ví dụ DTO:

~~~java
public record CustomerProfileView(
        Long customerId,
        String fullName,
        LocalDate dateOfBirth,
        String address) {
}
~~~

Truy vấn dùng LEFT JOIN để vẫn trả khách hàng chưa có hồ sơ:

~~~sql
SELECT
    c.id AS customer_id,
    c.full_name AS full_name,
    p.date_of_birth AS date_of_birth,
    p.address AS address
FROM customer c
LEFT JOIN customer_profile p
    ON p.customer_id = c.id
WHERE c.id = :customerId;
~~~

Khi khai báo truy vấn trong repository, có thể dùng:

~~~java
@Query("""
    SELECT
        c.id AS customer_id,
        c.full_name AS full_name,
        p.date_of_birth AS date_of_birth,
        p.address AS address
    FROM customer c
    LEFT JOIN customer_profile p
        ON p.customer_id = c.id
    WHERE c.id = :customerId
    """)
Mono<CustomerProfileView> findProfileView(Long customerId);
~~~

`LEFT JOIN` giữ lại hàng `customer` ngay cả khi không có `customer_profile`. Các cột của hồ sơ khi đó là SQL `NULL`.

Nếu chỉ dùng `INNER JOIN`, khách hàng không có hồ sơ sẽ không xuất hiện trong kết quả. Chọn loại join theo hợp đồng nghiệp vụ:

| Loại JOIN | Kết quả |
|---|---|
| `INNER JOIN` | Chỉ khách hàng có hồ sơ phù hợp |
| `LEFT JOIN` | Tất cả khách hàng; phần hồ sơ có thể null |
| `RIGHT JOIN` | Tất cả hồ sơ, kể cả khi không có khách hàng tương ứng; thường không cần nếu FK được bảo vệ |
| `FULL OUTER JOIN` | Giữ hàng từ cả hai phía; mức hỗ trợ tùy database |

Vì foreign key bảo đảm hồ sơ luôn có khách hàng, `RIGHT JOIN` hoặc `FULL OUTER JOIN` thường không cần cho mô hình này. `LEFT JOIN` thường phù hợp khi hồ sơ là tùy chọn.

Đặt alias rõ ràng để tránh trùng tên cột `id`, `created_at` hoặc `status` khi join nhiều bảng.

## 10. Truy vấn kết hợp bằng DatabaseClient

`DatabaseClient` cho phép viết SQL tường minh và map kết quả sang DTO:

~~~java
Mono<CustomerProfileView> findCustomerProfile(Long customerId) {
    return databaseClient.sql("""
            SELECT
                c.id AS customer_id,
                c.full_name AS full_name,
                p.date_of_birth AS date_of_birth,
                p.address AS address
            FROM customer c
            LEFT JOIN customer_profile p
                ON p.customer_id = c.id
            WHERE c.id = :customerId
            """)
            .bind("customerId", customerId)
            .map((row, metadata) -> new CustomerProfileView(
                    row.get("customer_id", Long.class),
                    row.get("full_name", String.class),
                    row.get("date_of_birth", LocalDate.class),
                    row.get("address", String.class)))
            .one();
}
~~~

`one()` phù hợp vì `customer.id` là khóa chính nên truy vấn có tối đa một hàng. Nếu khách hàng không tồn tại, publisher hoàn tất rỗng. Nếu có hàng nhưng chưa có hồ sơ, `date_of_birth` và `address` có thể null do `LEFT JOIN`.

Đây là hai trạng thái khác nhau:

- Không có khách hàng: không có hàng kết quả.
- Có khách hàng nhưng không có hồ sơ: có một hàng kết quả với các cột hồ sơ null.

Nếu cần phân biệt rõ hồ sơ vắng mặt với hồ sơ có các trường nullable, hãy chọn thêm `p.id AS profile_id` vào SELECT. Nếu `profile_id` null, không có hàng hồ sơ được join. Nếu có ID nhưng một thuộc tính hồ sơ null, hồ sơ tồn tại nhưng trường đó chưa có giá trị.

## 11. Ghi dữ liệu theo thứ tự và trong transaction

Khi khóa ngoại nằm ở bảng `customer_profile`, phải có khách hàng trước khi insert hồ sơ:

~~~text
1. INSERT customer
        |
        v
2. Nhận customer.id
        |
        v
3. INSERT customer_profile(customer_id, ...)
        |
        v
4. COMMIT
~~~

Nếu hai thao tác phải cùng thành công hoặc cùng rollback, hãy đặt chúng trong một reactive transaction.

Ví dụ khái quát với `TransactionalOperator`:

~~~java
Mono<CustomerProfile> createCustomerWithProfile(
        Customer customer,
        CustomerProfile profile) {

    return customerRepository.save(customer)
            .flatMap(savedCustomer -> {
                profile.setCustomerId(savedCustomer.getId());
                return customerProfileRepository.save(profile);
            })
            .as(transactionalOperator::transactional);
}
~~~

`transactionalOperator` phải được cấu hình với đúng `ConnectionFactory` mà các repository sử dụng. Nếu hai repository dùng connection factory khác nhau hoặc publisher bị subscribe tách rời, chúng có thể không tham gia cùng một transaction.

Nếu hồ sơ là tùy chọn và khách hàng có thể được tạo trước rồi bổ sung hồ sơ sau, hai thao tác có thể thuộc hai use case khác nhau. Khi đó, không nhất thiết phải gộp chúng trong một transaction dài.

### 11.1. Khi khóa ngoại nằm ở bảng chính

Nếu `customer.profile_id` tham chiếu `customer_profile.id`, thứ tự tạo thường đảo lại:

1. Tạo hồ sơ và lấy ID.
2. Gán ID đó vào khách hàng.
3. Lưu khách hàng.

Với khóa ngoại vòng hoặc hai phía đều bắt buộc tham chiếu lẫn nhau, việc insert có thể phức tạp. Nên tránh thiết kế vòng nếu không có lý do nghiệp vụ mạnh; một khóa ngoại duy nhất thường đủ để biểu diễn quan hệ.

## 12. Bảo vệ tính một-một trước request đồng thời

Một lỗi phổ biến là kiểm tra chưa có hồ sơ rồi mới insert:

~~~java
return profileRepository.existsByCustomerId(customerId)
        .flatMap(exists -> {
            if (exists) {
                return Mono.error(
                        new ProfileAlreadyExistsException(customerId));
            }

            return profileRepository.save(profile);
        });
~~~

Logic này hữu ích để tạo thông báo nghiệp vụ thân thiện, nhưng không bảo đảm tính duy nhất khi có request đồng thời:

~~~text
Request A: existsByCustomerId -> false
Request B: existsByCustomerId -> false
Request A: INSERT profile
Request B: INSERT profile
~~~

Nếu không có unique constraint, cả hai có thể thành công và tạo hai hồ sơ cho một khách hàng.

`UNIQUE(customer_id)` ở database là lớp bảo vệ cuối cùng. Khi hai request cạnh tranh, một insert thành công; insert còn lại nhận lỗi vi phạm unique constraint. Ứng dụng cần chuyển lỗi đó thành phản hồi nghiệp vụ thích hợp.

Không dựa vào kiểm tra trước insert như cơ chế duy nhất. Constraint database bảo vệ quy tắc ngay cả khi dữ liệu được ghi từ batch, script, dịch vụ khác hoặc nhiều instance ứng dụng.

## 13. Xóa và cập nhật quan hệ

Hãy xác định điều gì xảy ra khi xóa khách hàng hoặc hồ sơ:

- Nếu xóa khách hàng phải xóa hồ sơ, cân nhắc `ON DELETE CASCADE`.
- Nếu không cho xóa khách hàng khi còn hồ sơ, dùng `RESTRICT`/`NO ACTION` và xử lý hồ sơ trước.
- Nếu xóa hồ sơ nhưng giữ khách hàng, có thể xóa hàng hồ sơ độc lập khi FK nằm ở bảng hồ sơ.
- Nếu FK nằm ở bảng chính và hồ sơ bị xóa, phải cập nhật `profile_id` về null hoặc chọn hành vi tham chiếu phù hợp.

Ví dụ xóa hồ sơ theo customer ID:

~~~java
Mono<Void> deleteProfile(Long customerId) {
    return profileRepository.deleteByCustomerId(customerId);
}
~~~

Nếu database có `ON DELETE CASCADE`, thao tác xóa khách hàng có thể tự xóa hồ sơ phụ thuộc. Dù vậy, ứng dụng vẫn cần hiểu rõ tác động của lệnh xóa và kiểm thử trên database mục tiêu.

Đối với dữ liệu cần audit, lưu trữ lịch sử hoặc tuân thủ quy định, có thể cần soft delete hoặc trạng thái archive thay vì xóa vật lý/cascade.

## 14. Migration schema và dữ liệu hiện có

Thêm UNIQUE constraint vào một bảng đã có dữ liệu có thể thất bại nếu đã tồn tại nhiều hàng cùng `customer_id`.

Trước khi migration, cần phát hiện dữ liệu trùng:

~~~sql
SELECT customer_id, COUNT(*) AS profile_count
FROM customer_profile
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Cần xử lý các nhóm trùng theo quy tắc nghiệp vụ: chọn bản ghi giữ lại, hợp nhất dữ liệu, chuyển dữ liệu lịch sử sang bảng riêng hoặc yêu cầu người quản trị giải quyết. Không xóa ngẫu nhiên một hàng chỉ để migration chạy qua.

Sau khi dữ liệu sạch, tạo constraint:

~~~sql
ALTER TABLE customer_profile
ADD CONSTRAINT uk_profile_customer UNIQUE (customer_id);
~~~

Nếu cột bắt buộc, xác nhận không có null trước khi đặt `NOT NULL`:

~~~sql
SELECT COUNT(*)
FROM customer_profile
WHERE customer_id IS NULL;
~~~

Quản lý thay đổi bằng Flyway, Liquibase hoặc công cụ migration của dự án. Annotation entity không tự tạo foreign key hoặc unique constraint trong schema production.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ tạo foreign key mà không có UNIQUE | Một khách hàng có thể có nhiều hồ sơ | Thêm `UNIQUE` trên cột FK |
| Nghĩ `NOT NULL` bảo đảm mỗi khách hàng có hồ sơ | Nó chỉ bảo đảm mỗi hàng hồ sơ có khách hàng | Bổ sung quy tắc nghiệp vụ hoặc đổi mô hình |
| Đặt FK ở phía khó tạo trước | Phát sinh phụ thuộc thứ tự insert hoặc vòng FK | Đặt FK theo quyền sở hữu và vòng đời |
| Dùng `@OneToOne` của JPA cho entity R2DBC | Annotation không cung cấp mapping JPA trong Spring Data Relational | Ánh xạ cột FK tường minh và truy vấn liên quan rõ ràng |
| Khai báo object reference rồi mong tự join | Có thể không được materialize như mong muốn | Dùng ID FK, projection và JOIN tường minh |
| Trả `Mono<Profile>` nhưng FK không unique | Dữ liệu nhiều hàng có thể làm truy vấn đơn lỗi | Thêm constraint hoặc dùng `Flux` nếu thực sự là nhiều-một |
| Kiểm tra exists rồi insert mà không có constraint | Hai request đồng thời có thể tạo hàng trùng | Dùng unique constraint và xử lý lỗi vi phạm |
| Dùng `INNER JOIN` cho quan hệ tùy chọn | Khách hàng chưa có hồ sơ bị loại khỏi kết quả | Dùng `LEFT JOIN` |
| Không phân biệt hàng thiếu với cột null | Response có thể diễn giải sai trạng thái | Chọn thêm ID của hàng phụ để xác định nó có tồn tại |
| Xóa parent mà không xác định hành vi FK | Lệnh xóa thất bại hoặc xóa dây chuyền ngoài dự kiến | Chọn `RESTRICT`, `CASCADE` hoặc `SET NULL` theo nghiệp vụ |
| Ghi hai bảng nhưng không có transaction | Một bảng có thể được ghi khi bảng kia thất bại | Dùng reactive transaction khi cần tính nguyên tử |
| Thêm UNIQUE vào dữ liệu cũ đang trùng | Migration thất bại | Kiểm tra và xử lý duplicate trước migration |

## 16. Quy trình thiết kế quan hệ một-một

Khi mô hình hóa hai bảng có quan hệ một-một, hãy thực hiện theo trình tự:

1. Xác định bản ghi nào là chủ thể và bản ghi nào phụ thuộc về vòng đời hoặc nghiệp vụ.
2. Chọn bảng đặt khóa ngoại; ưu tiên vị trí giúp tạo, cập nhật và xóa dữ liệu rõ ràng.
3. Thêm foreign key để ngăn tham chiếu tới bản ghi không tồn tại.
4. Thêm UNIQUE hoặc dùng shared primary key để bảo đảm tối đa một hàng ở phía phụ thuộc.
5. Quyết định khóa ngoại có `NOT NULL` hay cho phép null.
6. Xác định hành vi `ON DELETE` và `ON UPDATE` theo chính sách dữ liệu.
7. Ánh xạ từng bảng thành entity riêng bằng `@Table`, `@Id`, `@Column`.
8. Giữ khóa ngoại thành property ID tường minh khi cần tham chiếu giữa các aggregate.
9. Dùng derived query để đọc riêng hoặc JOIN/projection khi cần dữ liệu kết hợp.
10. Dùng reactive transaction cho các thao tác nhiều bảng cần tính nguyên tử.
11. Xử lý lỗi unique constraint để bảo vệ trước request đồng thời.
12. Viết migration và integration test trên đúng database/driver.

## 17. Ghi nhớ

- Quan hệ một-một cần foreign key và ràng buộc UNIQUE trên cột FK, hoặc shared primary key.
- Foreign key bảo đảm tham chiếu hợp lệ; UNIQUE giới hạn mỗi hàng được tham chiếu tối đa một lần; NOT NULL yêu cầu mỗi hàng có giá trị FK.
- NOT NULL trên bảng con không bảo đảm mọi hàng cha đều có hàng con.
- Có thể đặt FK ở bảng phụ thuộc hoặc bảng chính; lựa chọn dựa trên quyền sở hữu, vòng đời và thứ tự tạo dữ liệu.
- Spring Data R2DBC không dùng `@OneToOne` của JPA để tự động tạo quan hệ, join, lazy loading hoặc cascade.
- Ánh xạ FK thành property ID tường minh là cách rõ ràng để tham chiếu một aggregate khác.
- Dùng `LEFT JOIN` nếu bản ghi chính vẫn cần xuất hiện khi dữ liệu phụ chưa tồn tại.
- Dùng transaction reactive khi tạo hoặc cập nhật hai bảng cần cùng thành công hoặc cùng rollback.
- Kiểm tra unique constraint ở database; kiểm tra tồn tại trước insert không ngăn được race condition.
- Migration phải xử lý dữ liệu trùng và null hiện có trước khi thêm constraint.
- Kiểm thử cả trường hợp có bản ghi phụ, không có bản ghi phụ, FK sai, duplicate và xóa theo chính sách đã chọn.

