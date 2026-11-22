# DataIntegrityViolationException và ràng buộc cơ sở dữ liệu

Trong Spring Data JPA, **DataIntegrityViolationException** thường xuất hiện khi thao tác ghi dữ liệu vi phạm một ràng buộc toàn vẹn của database, chẳng hạn khóa chính, khóa ngoại, UNIQUE, NOT NULL hoặc CHECK.

Lỗi có thể không xuất hiện ngay tại dòng gọi **save()**. JPA/Hibernate có thể trì hoãn SQL tới lúc flush hoặc commit transaction. Vì vậy, cần hiểu thời điểm database thực sự kiểm tra constraint, cách Spring dịch exception, cách transaction rollback và cách trả lỗi an toàn cho API.

Bài này cũng phân biệt ba exception có tên gần giống nhau: **org.springframework.dao.DataIntegrityViolationException**, **org.hibernate.exception.ConstraintViolationException** và **jakarta.validation.ConstraintViolationException**. Chúng thuộc các tầng khác nhau và không nên xử lý như một loại lỗi duy nhất.

**Điều kiện của ví dụ:** Java 17 trở lên, Spring Boot 3.x, Spring Data JPA, Hibernate và Jakarta Bean Validation. Ứng dụng cần **spring-boot-starter-data-jpa**, **spring-boot-starter-validation**, JDBC driver, DataSource và schema đã được tạo. SQL migration minh họa cần điều chỉnh cú pháp identity/sequence theo database thực tế. Đây là các phần của ứng dụng Spring Boot, không phải chương trình độc lập chạy chỉ bằng javac.

## 1. Data integrity là gì?

Data integrity (tính toàn vẹn dữ liệu) là tập hợp các quy tắc bảo đảm dữ liệu được lưu trong database luôn hợp lệ và nhất quán.

Ví dụ một hệ thống bán hàng có các quy tắc:

- Mỗi customer phải có ID duy nhất.
- Email customer không được trùng.
- Email và tên hiển thị không được null.
- Mỗi order phải tham chiếu tới một customer tồn tại.
- Tổng tiền đơn hàng không được âm.

Database có thể thực thi các quy tắc này bằng constraint. Khi một câu INSERT hoặc UPDATE vi phạm constraint, database từ chối thao tác và JDBC báo lỗi. Spring/Hibernate có thể bọc lỗi đó thành exception ở tầng Java.

Các constraint là lớp bảo vệ cuối cùng vì chúng được kiểm tra ngay tại database, kể cả khi dữ liệu được ghi bởi một ứng dụng khác, batch job hoặc SQL trực tiếp.

## 2. Các loại constraint phổ biến

| Constraint | Mục đích | Ví dụ lỗi |
|---|---|---|
| PRIMARY KEY | Định danh duy nhất cho mỗi hàng | INSERT ID đã tồn tại |
| UNIQUE | Không cho phép trùng giá trị hoặc tổ hợp giá trị | Hai customer có cùng email |
| NOT NULL | Bắt buộc cột có giá trị | Lưu email null |
| FOREIGN KEY | Bảo đảm quan hệ tham chiếu hợp lệ | Order tham chiếu customer không tồn tại |
| CHECK | Bảo đảm biểu thức điều kiện đúng | Lưu quantity âm |
| UNIQUE composite | Không cho phép trùng tổ hợp cột | Cùng tenant và username |

Ví dụ DDL minh họa:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    CONSTRAINT uk_customers_email UNIQUE (email)
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id),
    CONSTRAINT ck_orders_total_nonnegative
        CHECK (total_amount >= 0)
);
~~~

Tên constraint được đặt tường minh như **uk_customers_email** hoặc **fk_orders_customer** giúp vận hành và chẩn đoán dễ hơn. Cú pháp tạo khóa tự tăng, schema và một số loại constraint phụ thuộc database; hãy đưa DDL phù hợp engine vào Flyway hoặc Liquibase migration.

## 3. Constraint ở database và validation ở ứng dụng

Có hai lớp kiểm tra thường được dùng cùng nhau:

- **Bean Validation** kiểm tra dữ liệu ở tầng ứng dụng trước hoặc trong quá trình persist/update entity.
- **Database constraint** bảo vệ dữ liệu ở nơi lưu trữ, kể cả khi có nhiều ứng dụng cùng ghi.

Ví dụ entity:

~~~java
@Entity
@Table(
    name = "customers",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_customers_email",
            columnNames = "email"
        )
    }
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Email
    @Column(nullable = false, length = 255)
    private String email;

    @NotBlank
    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Trong ví dụ:

- **@NotBlank** yêu cầu chuỗi không null và có ký tự không phải whitespace.
- **@Email** kiểm tra hình dạng địa chỉ email theo validator.
- **@Column(nullable = false)** khai báo metadata mapping/schema.
- **@UniqueConstraint** khai báo unique constraint cho schema được sinh từ mapping.

Các annotation mapping không tự bảo đảm production database đã có constraint. Nếu schema được quản lý bằng migration, phải tạo constraint trong migration. **@Column(nullable = false)** hoặc **@UniqueConstraint** có thể ảnh hưởng DDL khi Hibernate tạo schema, nhưng không thay thế việc quản lý schema đã triển khai.

Bean Validation cũng không thay thế UNIQUE/FK/CHECK ở database. Chẳng hạn @Email không bảo đảm email duy nhất; @NotNull ở ứng dụng không ngăn một SQL client khác ghi null nếu database không có NOT NULL.

## 4. DataIntegrityViolationException thuộc tầng Spring

**org.springframework.dao.DataIntegrityViolationException** là exception trong hệ thống exception của Spring DAO. Nó biểu thị thao tác dữ liệu vi phạm tính toàn vẹn, ví dụ constraint ở database hoặc một số lỗi mapping dữ liệu liên quan.

Đặc điểm:

- Là unchecked exception, kế thừa **DataAccessException**.
- Có thể xuất hiện khi gọi repository hoặc khi flush/commit transaction.
- Spring exception translation giúp giảm phụ thuộc trực tiếp vào exception của JDBC/provider.
- Không chỉ đại diện cho lỗi UNIQUE; NOT NULL, FK và các lỗi integrity khác cũng có thể được bọc trong loại exception này.

Ví dụ import:

~~~java
import org.springframework.dao.DataIntegrityViolationException;
~~~

Không nên chỉ dựa vào tên exception để kết luận constraint cụ thể nào bị vi phạm. Muốn phân loại chính xác cần xem cause chain, SQLState/vendor code và constraint name nếu provider cung cấp.

## 5. Phân biệt ba ConstraintViolationException

Có ba tên exception rất dễ nhầm:

| Exception | Package | Tầng | Ý nghĩa |
|---|---|---|---|
| DataIntegrityViolationException | org.springframework.dao | Spring DAO | Lỗi toàn vẹn dữ liệu được Spring dịch |
| ConstraintViolationException | org.hibernate.exception | Hibernate | Lỗi SQL do database constraint, có thể chứa SQL và tên constraint |
| ConstraintViolationException | jakarta.validation | Bean Validation | Một hoặc nhiều constraint validation của object không đạt |

### Hibernate exception

**org.hibernate.exception.ConstraintViolationException** thường bao bọc lỗi SQL do constraint database. Nó có thể cung cấp:

- **getConstraintName()**: tên constraint nếu driver/provider xác định được.
- **getSQLException()**: SQLException gốc.
- **getSQL()**: câu SQL liên quan trong một số ngữ cảnh.

Tên constraint có thể null tùy database và driver. Không dựa vào thông báo lỗi dạng text để phân loại một cách portable.

### Jakarta Bean Validation exception

**jakarta.validation.ConstraintViolationException** chứa tập hợp các validation violation, ví dụ field email không hợp lệ hoặc tên bị bỏ trống. Lỗi này có thể xảy ra trước khi database thực hiện INSERT/UPDATE.

Ví dụ:

~~~java
import jakarta.validation.ConstraintViolationException;
~~~

Không nhầm exception này với **org.hibernate.exception.ConstraintViolationException**. Khi đọc log hoặc viết catch block, hãy dùng tên package đầy đủ nếu cần phân biệt.

## 6. DataIntegrityViolationException xuất hiện khi nào?

Một thao tác repository có thể trông như đã hoàn tất nhưng SQL chưa được gửi ngay tới database.

~~~java
@Transactional
public Customer create(Customer customer) {
    return customerRepository.save(customer);
}
~~~

JPA có thể giữ thay đổi trong persistence context. Hibernate thực hiện SQL tại thời điểm flush, chẳng hạn:

- Khi ứng dụng gọi **EntityManager.flush()**.
- Khi gọi **JpaRepository.saveAndFlush()**.
- Trước một query cần đồng bộ thay đổi pending.
- Khi transaction commit.

Vì vậy, exception có thể xuất hiện tại commit sau khi method service đã chạy xong phần thân. Spring transaction interceptor thực hiện commit trước khi lời gọi qua proxy trả kết quả cho caller.

Có những trường hợp database/provider thực thi SQL sớm hơn, ví dụ chiến lược sinh IDENTITY có thể yêu cầu INSERT sớm. Không nên dựa vào một thời điểm cố định cho mọi entity và database.

## 7. Dùng flush để phát hiện lỗi sớm hơn

Nếu muốn buộc Hibernate gửi SQL và nhận phản hồi constraint ngay trong phạm vi method, có thể dùng **saveAndFlush()**:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer create(Customer customer) {
        return repository.saveAndFlush(customer);
    }
}
~~~

Hoặc:

~~~java
@Transactional
public Customer create(Customer customer) {
    Customer saved = repository.save(customer);
    entityManager.flush();
    return saved;
}
~~~

**flush() không phải commit.** Nó đồng bộ thay đổi đang chờ trong persistence context xuống database, nhưng transaction vẫn có thể rollback sau đó.

Một số constraint được cấu hình deferred có thể chỉ được kiểm tra tại commit. Do đó, flush không bảo đảm mọi lỗi integrity đều xuất hiện ngay tại vị trí gọi flush.

Dùng flush có chủ đích cho các use case cần phát hiện lỗi ghi sớm. Không gọi flush sau mọi thao tác một cách máy móc vì điều đó có thể làm mất lợi ích batching và tăng round-trip database.

## 8. UNIQUE constraint và race condition

Một cách kiểm tra trước khi insert là:

~~~java
if (repository.existsByEmail(email)) {
    throw new EmailAlreadyUsedException();
}
~~~

Kiểm tra này giúp trả lỗi dễ hiểu trong trường hợp dữ liệu đã tồn tại. Nhưng nó không bảo đảm tính duy nhất khi có nhiều request đồng thời:

~~~text
Request A: existsByEmail -> false
Request B: existsByEmail -> false
Request A: INSERT email
Request B: INSERT email
Database: chỉ một INSERT thành công
Database: INSERT còn lại vi phạm UNIQUE
~~~

Đây là race condition giữa bước kiểm tra và bước ghi. **UNIQUE constraint trong database mới là cơ chế bảo đảm duy nhất có tính đồng thời.**

Có thể kết hợp cả hai:

1. Kiểm tra trước để cải thiện trải nghiệm thông thường.
2. Tạo UNIQUE constraint thật trong database.
3. Bắt và phân loại lỗi integrity khi hai request cạnh tranh cùng giá trị.
4. Trả lỗi nghiệp vụ ổn định cho request thua cuộc.

Không loại bỏ database constraint chỉ vì đã có existsByEmail.

## 9. Đặt tên constraint để dễ chẩn đoán

Migration có tên constraint rõ ràng:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uk_customers_email UNIQUE (email);
~~~

Khi Hibernate nhận được lỗi, cause chain có thể chứa **org.hibernate.exception.ConstraintViolationException**. Nếu driver cung cấp tên constraint, Hibernate có thể trả qua getConstraintName().

Ví dụ kiểm tra cause theo hướng Hibernate-specific:

~~~java
Throwable cause = ex.getMostSpecificCause();

if (cause instanceof
        org.hibernate.exception.ConstraintViolationException hibernateEx) {

    String constraintName = hibernateEx.getConstraintName();
}
~~~

Đây là kỹ thuật phụ thuộc Hibernate. **getMostSpecificCause()** đến từ Spring. Trong một số trường hợp cause trực tiếp hoặc most-specific cause có thể là SQLException thay vì Hibernate exception; cần duyệt cause chain nếu triển khai classifier đầy đủ.

Không giả định constraint name luôn có mặt hoặc giống nhau trên mọi database. Có thể dùng SQLState/vendor code và loại exception làm tín hiệu bổ sung, nhưng classifier phải được kiểm thử trên database thực tế.

Không phân tích chuỗi thông báo lỗi bằng các đoạn text như "Duplicate entry" để làm logic nghiệp vụ portable. Thông báo có thể đổi theo database, phiên bản, ngôn ngữ và driver.

## 10. Transaction rollback khi có lỗi integrity

**DataIntegrityViolationException** là unchecked exception. Theo mặc định, Spring transaction rollback khi một RuntimeException hoặc Error thoát khỏi transactional method.

Ví dụ:

~~~java
@Transactional
public Customer register(Customer customer) {
    return repository.saveAndFlush(customer);
}
~~~

Nếu INSERT vi phạm UNIQUE và exception thoát khỏi method, transaction sẽ rollback.

Cần lưu ý:

- Nếu exception xuất hiện tại flush, Hibernate có thể đánh dấu transaction hoặc Session không còn dùng được cho các thao tác tiếp theo.
- Nếu bắt exception bên trong cùng transaction rồi tiếp tục query/ghi, database có thể đã đánh dấu transaction rollback-only hoặc ở trạng thái lỗi.
- Khi transaction đã rollback-only, caller có thể nhận **UnexpectedRollbackException** lúc commit dù exception ban đầu đã bị catch.
- Không nên bắt rồi bỏ qua DataIntegrityViolationException để tiếp tục dùng cùng persistence context.

Nếu cần chuyển đổi exception, thường để nó thoát khỏi service transactional và xử lý tại tầng bên ngoài transaction, chẳng hạn ControllerAdvice. Nếu cần bắt trong service, hãy thiết kế transaction boundary riêng và không tiếp tục dùng persistence context đã gặp lỗi.

## 11. Xử lý lỗi tại REST API bằng ProblemDetail

Spring Framework 6 hỗ trợ **ProblemDetail** để trả lỗi theo cấu trúc HTTP API rõ ràng.

Ví dụ handler tổng quát:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ProblemDetail> handleIntegrityViolation(
            DataIntegrityViolationException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "Dữ liệu không thể lưu do vi phạm ràng buộc."
        );

        problem.setTitle("Xung đột dữ liệu");

        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(problem);
    }
}
~~~

Response minh họa:

~~~json
{
  "type": "about:blank",
  "title": "Xung đột dữ liệu",
  "status": 409,
  "detail": "Dữ liệu không thể lưu do vi phạm ràng buộc."
}
~~~

Đây là cách xử lý fallback đơn giản. Trong ứng dụng thực tế, không phải mọi DataIntegrityViolationException đều nhất thiết phải trả 409:

- UNIQUE conflict thường phù hợp với 409 Conflict.
- Dữ liệu đầu vào sai có thể được phát hiện sớm và trả 400 hoặc 422 theo hợp đồng API.
- Tham chiếu tới resource không tồn tại có thể cần quy tắc 404/409/422 tùy ngữ nghĩa endpoint.
- Lỗi constraint do bug hoặc dữ liệu nội bộ bất thường có thể cần được ghi nhận như lỗi server.

Nên phân loại các trường hợp đã biết bằng classifier phụ thuộc provider/database, sau đó trả mã lỗi nghiệp vụ ổn định. Không trả SQL, tên bảng/cột nội bộ, constraint details, giá trị dữ liệu hoặc stack trace cho client.

## 12. Không nhầm với lỗi validation request

Có thể dùng **@Valid** để kiểm tra request DTO trước khi gọi service:

~~~java
public record CreateCustomerRequest(
    @NotBlank @Email String email,
    @NotBlank @Size(max = 120) String displayName
) {
}
~~~

Controller:

~~~java
@PostMapping("/customers")
public CustomerResponse create(
        @Valid @RequestBody CreateCustomerRequest request) {

    return customerService.create(request);
}
~~~

Nếu email trống hoặc sai định dạng, Bean Validation có thể từ chối request trước khi repository chạy. Đây là lỗi validation input, không phải database UNIQUE violation.

Tuy nhiên, request validation không thể thay thế database constraint:

- @Email không kiểm tra email đã được người khác đăng ký hay chưa.
- Kiểm tra existsByEmail có race condition.
- Một tiến trình khác vẫn có thể ghi trực tiếp vào database.
- Ràng buộc quan hệ và tính nhất quán cần được bảo vệ tại nơi lưu trữ.

Hãy dùng cả validation và constraint để tạo phản hồi sớm đồng thời bảo vệ dữ liệu cuối cùng.

## 13. Foreign key violation

Foreign key bảo đảm hàng con tham chiếu tới hàng cha tồn tại.

Ví dụ Order có customer_id:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id) REFERENCES customers(id);
~~~

Nếu ứng dụng lưu Order với customer_id không tồn tại, database từ chối INSERT/UPDATE.

Trong JPA, nên biểu diễn quan hệ bằng association:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "customer_id",
    nullable = false,
    foreignKey = @ForeignKey(name = "fk_orders_customer")
)
private Customer customer;
~~~

Ví dụ service tải customer trước:

~~~java
@Transactional
public Order createOrder(Long customerId) {
    Customer customer = customerRepository.findById(customerId)
        .orElseThrow(CustomerNotFoundException::new);

    Order order = new Order(customer);
    return orderRepository.save(order);
}
~~~

Việc tải customer giúp trả lỗi nghiệp vụ rõ ràng khi ID không tồn tại. Foreign key vẫn cần ở database để bảo vệ trước các request đồng thời và mọi đường ghi khác.

Cũng cần phân biệt hai tình huống:

- Customer không tồn tại khi ứng dụng kiểm tra.
- Customer bị xóa giữa lúc kiểm tra và lúc ghi Order.

Foreign key xử lý tình huống cạnh tranh thứ hai. Cách xử lý xóa customer đang được tham chiếu phải được thiết kế rõ: RESTRICT/NO ACTION, CASCADE hoặc quy trình nghiệp vụ riêng.

## 14. CHECK và NOT NULL violation

CHECK constraint bảo đảm một biểu thức đúng cho mỗi hàng:

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT ck_order_items_quantity_positive
CHECK (quantity > 0);
~~~

Nếu quantity bằng 0 hoặc âm, database từ chối thao tác.

NOT NULL:

~~~sql
ALTER TABLE customers
ALTER COLUMN email SET NOT NULL;
~~~

Cú pháp ALTER COLUMN khác nhau theo database; ví dụ trên phù hợp với một số hệ quản trị nhưng cần chuyển đổi cho engine đích.

Có thể kiểm tra sớm bằng Bean Validation:

~~~java
@NotNull
@Positive
private Integer quantity;
~~~

Tuy nhiên, CHECK/NOT NULL trong database vẫn cần thiết vì validation của ứng dụng không chạy với mọi nguồn ghi. Với CHECK có biểu thức phức tạp hoặc phụ thuộc nhiều cột, database constraint giúp bảo vệ quy tắc ở cấp dữ liệu.

## 15. Bulk update và native SQL

JPQL bulk update/delete và native SQL tác động trực tiếp lên database, bỏ qua vòng đời entity thông thường. Chúng không tự gọi Bean Validation trên từng entity và không chạy entity listener như một lần cập nhật entity managed.

Ví dụ:

~~~java
@Modifying
@Transactional
@Query("""
    update Customer c
    set c.email = :email
    where c.id = :id
    """)
int updateEmail(
    @Param("id") Long id,
    @Param("email") String email
);
~~~

Nếu email trùng UNIQUE, database vẫn từ chối UPDATE và lỗi có thể được Spring dịch thành DataIntegrityViolationException. Constraint database vẫn hoạt động, dù Bean Validation lifecycle không được chạy cho từng entity.

Sau bulk update, persistence context có thể giữ entity cũ. Cân nhắc flush trước và clear sau hoặc dùng các tùy chọn @Modifying phù hợp. Không tiếp tục dùng entity managed stale như thể database chưa thay đổi.

Nếu bulk operation có thể vi phạm nhiều loại constraint, hãy kiểm thử trên database thực tế và thiết kế cách phân loại lỗi phù hợp.

## 16. Migration và dữ liệu hiện có

Khi bổ sung UNIQUE, NOT NULL hoặc FK vào một bảng đang có dữ liệu, migration có thể thất bại nếu dữ liệu cũ đã vi phạm quy tắc mới.

Ví dụ trước khi thêm UNIQUE email, cần tìm dữ liệu trùng:

~~~sql
SELECT email, COUNT(*)
FROM customers
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Trước khi thêm NOT NULL:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE email IS NULL;
~~~

Trước khi thêm foreign key, tìm các hàng mồ côi bằng LEFT JOIN hoặc NOT EXISTS.

Quy trình triển khai an toàn thường gồm:

1. Kiểm tra và làm sạch dữ liệu hiện có.
2. Quyết định cách xử lý bản ghi trùng/null/orphan theo nghiệp vụ.
3. Triển khai code tương thích với dữ liệu hiện tại nếu cần nhiều bước.
4. Tạo constraint bằng migration.
5. Xác nhận migration trên dữ liệu gần production.
6. Theo dõi lỗi integrity sau triển khai.

Không dựa vào **spring.jpa.hibernate.ddl-auto=update** như công cụ quản lý schema production. Dùng Flyway hoặc Liquibase để migration có lịch sử, có thể review và tái lập.

## 17. Kiểm thử DataIntegrityViolationException

Integration test nên flush để constraint được kiểm tra ngay trong test:

~~~java
@DataJpaTest
class CustomerConstraintTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void rejectsDuplicateEmail() {
        repository.saveAndFlush(
            new Customer("an@example.test", "An")
        );

        assertThatThrownBy(() ->
            repository.saveAndFlush(
                new Customer("an@example.test", "Another An")
            )
        ).isInstanceOf(DataIntegrityViolationException.class);
    }
}
~~~

Test giả định schema test đã có UNIQUE constraint trên email và Spring exception translation hoạt động. Tùy database/provider, loại exception cụ thể và cause chain có thể khác; assertion ở tầng Spring thường ổn định hơn assertion trực tiếp vào message của database.

Nên kiểm thử thêm:

- NOT NULL và CHECK.
- Foreign key tới customer không tồn tại.
- Delete customer đang được order tham chiếu.
- Bean Validation trước khi SQL chạy.
- Bulk update vi phạm UNIQUE.
- Transaction rollback sau lỗi.
- Constraint được kiểm tra tại commit nếu database dùng deferred constraint.

### Kiểm thử transaction rollback

Khi kiểm tra rollback, hãy dùng transaction boundary rõ ràng. Một test method mặc định có thể chạy trong transaction của @DataJpaTest và rollback khi kết thúc; điều này không tự chứng minh transaction service đã rollback đúng khi exception thoát qua proxy.

Với test service transaction, có thể gọi service từ test không mang @Transactional, xác nhận exception và truy vấn lại bằng transaction mới để kiểm tra dữ liệu không được commit.

Không cố tiếp tục thao tác với cùng persistence context sau khi flush đã thất bại. Dùng transaction/test context mới cho các assertion tiếp theo.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| save() không ném lỗi ngay | SQL được trì hoãn tới flush/commit | Dùng saveAndFlush hoặc flush khi cần phát hiện sớm |
| Catch exception nhưng commit vẫn lỗi | Transaction đã bị đánh dấu rollback-only | Để lỗi thoát khỏi transaction và xử lý bên ngoài |
| Exists trước insert nhưng vẫn trùng | Race condition giữa check và insert | Giữ UNIQUE constraint ở database |
| Nhầm hai ConstraintViolationException | Khác package và khác tầng | Phân biệt Hibernate exception với Jakarta Validation exception |
| @Column(nullable=false) không bảo vệ production | Schema thực tế chưa có NOT NULL | Thêm migration constraint |
| @Valid không ngăn email trùng | Validation format không kiểm tra uniqueness đồng thời | Dùng UNIQUE constraint và xử lý conflict |
| Không lấy được tên constraint | Driver/provider không cung cấp | Dùng cause chain, SQLState/vendor code; không phụ thuộc tên luôn có |
| FK lỗi dù đã kiểm tra ID | Hàng cha bị xóa đồng thời hoặc mapping sai | Giữ FK và xử lý lỗi ở transaction boundary |
| Bulk update không chạy Bean Validation | Bulk DML bỏ qua entity lifecycle | Validate input riêng và giữ database constraint |
| Migration thêm constraint thất bại | Dữ liệu cũ đã vi phạm | Audit và làm sạch dữ liệu trước migration |
| API trả SQL chi tiết | Expose exception message/cause trực tiếp | Trả ProblemDetail ổn định, log chi tiết nội bộ |

## 19. Checklist xử lý lỗi toàn vẹn dữ liệu

- [ ] Xác định constraint cần bảo vệ: PK, UNIQUE, NOT NULL, FK hay CHECK.
- [ ] Tạo constraint thực tế trong database bằng migration.
- [ ] Dùng Bean Validation để phản hồi input sai sớm.
- [ ] Phân biệt DataIntegrityViolationException của Spring với hai ConstraintViolationException ở Hibernate và Jakarta Validation.
- [ ] Hiểu save() có thể trì hoãn SQL tới flush/commit.
- [ ] Dùng saveAndFlush/flush khi cần phát hiện lỗi sớm, không nhầm flush với commit.
- [ ] Dùng UNIQUE constraint để xử lý race condition, không chỉ dựa vào exists query.
- [ ] Đặt tên constraint rõ ràng trong migration.
- [ ] Không tiếp tục dùng persistence context sau lỗi flush.
- [ ] Chuyển exception thành lỗi API ổn định ở ngoài transaction boundary.
- [ ] Không trả SQL, stack trace hoặc dữ liệu nhạy cảm cho client.
- [ ] Kiểm thử constraint trên đúng database/driver của môi trường triển khai.
- [ ] Làm sạch dữ liệu hiện có trước khi thêm constraint mới.
- [ ] Kiểm tra bulk update/delete vì chúng bỏ qua entity lifecycle validation.

## 20. Kết luận

**DataIntegrityViolationException** là exception tầng Spring báo rằng thao tác dữ liệu vi phạm tính toàn vẹn. Nguyên nhân có thể là UNIQUE, NOT NULL, FK, CHECK hoặc constraint khác; chi tiết provider thường nằm trong cause chain. Hãy phân biệt nó với **org.hibernate.exception.ConstraintViolationException** (lỗi constraint SQL của Hibernate) và **jakarta.validation.ConstraintViolationException** (lỗi Bean Validation).

JPA có thể trì hoãn SQL tới flush hoặc commit, vì vậy lỗi không nhất thiết xuất hiện ngay tại save(). Database constraint mới là cơ chế bảo vệ dữ liệu trước ghi đồng thời và nhiều nguồn ghi; Bean Validation giúp phản hồi sớm. Khi lỗi xảy ra, để transaction rollback đúng, xử lý ở boundary phù hợp, trả thông báo API ổn định và giữ chi tiết kỹ thuật trong log nội bộ.