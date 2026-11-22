# Phối hợp validator với ràng buộc duy nhất và khóa ngoại trong cơ sở dữ liệu

## Mục tiêu

Một request ghi dữ liệu có thể hợp lệ về cấu trúc nhưng vẫn vi phạm quy tắc nghiệp vụ hoặc tính toàn vẹn của database. Ví dụ:

- Email của một Customer phải đúng định dạng và không được trùng với email đã tồn tại.
- Order phải tham chiếu đến một Customer có thật.
- Một Customer đang được Order sử dụng có thể không được phép xóa.
- Một mã nghiệp vụ phải duy nhất trong phạm vi tenant.

Spring Data REST có thể kiểm tra dữ liệu đầu vào bằng Bean Validation hoặc Spring Validator trước khi gọi repository. Database tiếp tục bảo vệ tính toàn vẹn bằng các constraint như UNIQUE và FOREIGN KEY. Hai lớp này bổ sung cho nhau:

- Validator đưa ra lỗi sớm, dễ hiểu và gắn với field hoặc quy tắc nghiệp vụ.
- Database constraint là hàng rào cuối cùng bảo vệ dữ liệu trước các request đồng thời, các đường ghi khác và lỗi trong ứng dụng.

Không nên dùng một lần kiểm tra bằng repository để thay thế constraint database. Giữa lúc kiểm tra và lúc ghi, một transaction khác có thể thay đổi dữ liệu. Ngược lại, cũng không nên dựa hoàn toàn vào lỗi database nếu có thể phát hiện dữ liệu sai sớm và trả thông báo hữu ích cho client.

## 1. Ba lớp kiểm tra dữ liệu

Một luồng ghi dữ liệu thường cần ba lớp kiểm tra khác nhau:

| Lớp | Ví dụ | Vai trò |
|---|---|---|
| Bean Validation / Spring Validator | @NotBlank, @Email, kiểm tra quy tắc nghiệp vụ | Phát hiện input không hợp lệ trước khi ghi |
| Kiểm tra bằng repository/service | existsByEmail(...), existsById(...) | Phát hiện xung đột hoặc tham chiếu không tồn tại để trả lỗi sớm |
| Database constraint | UNIQUE, FOREIGN KEY, NOT NULL, CHECK | Bảo vệ tính toàn vẹn khi mọi đường ghi cùng truy cập dữ liệu |

Ví dụ với Customer:

    @Entity
    @Table(
        name = "customer",
        uniqueConstraints = {
            @UniqueConstraint(
                name = "uk_customer_email",
                columnNames = "email"
            )
        }
    )
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        @NotBlank
        @Email
        @Column(nullable = false)
        private String email;

        @NotBlank
        private String name;
    }

Các annotation có ý nghĩa riêng:

- @NotBlank và @Email là quy tắc Bean Validation.
- @Column(nullable = false) mô tả mapping và có thể tham gia tạo schema.
- @UniqueConstraint mô tả unique constraint trong metadata JPA để schema generation có thể tạo constraint tương ứng.
- Database chỉ thực sự bảo vệ uniqueness khi constraint đã tồn tại trong schema đang chạy.

Nếu schema được quản lý bằng Flyway, Liquibase hoặc DBA, cần tạo constraint trong migration/schema thực tế. Không giả định annotation JPA tự cập nhật database production.

## 2. Bean Validation cho dữ liệu request

Bean Validation định nghĩa các constraint trên object hoặc property. Spring Boot thường tích hợp Jakarta Bean Validation qua provider như Hibernate Validator khi dependency validation được thêm vào ứng dụng.

Ví dụ:

    public class CustomerRequest {

        @NotBlank
        @Email
        private String email;

        @NotBlank
        @Size(max = 120)
        private String name;
    }

Các constraint phổ biến:

| Annotation | Mục đích |
|---|---|
| @NotNull | Giá trị không được null |
| @NotBlank | Chuỗi không null và có ít nhất một ký tự không phải khoảng trắng |
| @NotEmpty | Chuỗi/collection/map/array không được rỗng |
| @Size | Giới hạn độ dài hoặc số phần tử |
| @Email | Kiểm tra hình dạng địa chỉ email theo validator |
| @Min / @Max | Giới hạn số |
| @Positive / @PositiveOrZero | Kiểm tra dấu của số |
| @Pattern | Kiểm tra chuỗi theo regular expression |
| @Past / @Future | Ràng buộc thời gian |

Validator giúp kiểm tra dữ liệu ở cấp ứng dụng. Nó không tự tạo unique index hoặc foreign key trong database.

### 2.1. Phân biệt null, rỗng và blank

Ba trường hợp sau khác nhau:

- null: không có giá trị.
- chuỗi rỗng: "".
- chuỗi chỉ có khoảng trắng: "   ".

@NotNull chỉ từ chối null. @NotEmpty từ chối null và giá trị rỗng. @NotBlank phù hợp khi field bắt buộc phải có nội dung văn bản thực sự.

Với request PATCH, cần phân biệt property bị bỏ qua với property được gửi rõ ràng là null. Không áp dụng cùng một validation group hoặc DTO một cách máy móc cho POST, PUT và PATCH.

### 2.2. Kích hoạt validation

Trong custom Spring MVC controller, đặt @Valid hoặc @Validated trên request body:

    @PostMapping("/customers")
    public ResponseEntity<Customer> create(
            @Valid @RequestBody CustomerRequest request) {
        // Map request, save entity, return response.
    }

Spring MVC chạy Bean Validation trước khi method xử lý request tiếp tục. Nếu object vi phạm constraint, request thường được xử lý thành lỗi 400 Bad Request theo cơ chế exception handling của Spring MVC.

Với Spring Data REST, request đi qua repository exporter. Có thể đăng ký Spring Validator theo cơ chế validator của Spring Data REST hoặc dùng repository event handler để kiểm tra trước khi lưu. Không nên giả định annotation @Valid trên một custom controller tự động áp dụng cho mọi endpoint repository exporter.

### 2.3. Đăng ký validator cho Spring Data REST

Spring Data REST hỗ trợ các Spring Validator được đặt tên theo thao tác và domain type. Ví dụ validator chạy trước khi tạo Customer có thể được đăng ký bằng bean name:

    @Component("beforeCreateCustomerValidator")
    public class CustomerCreateValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Customer.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Customer customer = (Customer) target;

            if (customer.getEmail() == null
                    || customer.getEmail().isBlank()) {
                errors.rejectValue(
                    "email",
                    "customer.email.required",
                    "Email is required"
                );
            }
        }
    }

Tên bean theo quy ước `beforeCreate<CustomerType>Validator` gắn validator với thao tác tạo. Spring Data REST cũng hỗ trợ validator cho các thao tác lưu/cập nhật theo naming convention tương ứng, ví dụ `beforeSaveCustomerValidator`.

Tên domain type trong bean name cần khớp với tên simple class theo quy ước Spring Data REST. Hãy kiểm tra cấu hình và phiên bản dự án nếu validator không được gọi.

### 2.4. Dùng repository event handler

Một lựa chọn khác là xử lý quy tắc trước khi repository lưu:

    @Component
    @RepositoryEventHandler(Customer.class)
    public class CustomerEventHandler {

        private final CustomerRepository customers;

        public CustomerEventHandler(CustomerRepository customers) {
            this.customers = customers;
        }

        @HandleBeforeCreate
        public void beforeCreate(Customer customer) {
            if (customers.existsByEmail(customer.getEmail())) {
                throw new IllegalArgumentException(
                    "Email is already registered"
                );
            }
        }
    }

Event handler hữu ích khi quy tắc gắn với luồng repository exporter. Tuy nhiên, kiểm tra existsByEmail chỉ là kiểm tra sớm. Database vẫn phải có unique constraint để xử lý request đồng thời.

Không nên đặt logic nghiệp vụ phức tạp, gọi dịch vụ bên ngoài hoặc phát side effect không thể rollback trong validator. Validator nên tập trung xác định dữ liệu có hợp lệ hay không.

## 3. Ràng buộc UNIQUE trong database

UNIQUE bảo đảm một giá trị hoặc tổ hợp giá trị không bị lặp theo quy tắc của database.

Ví dụ email phải duy nhất:

    CREATE TABLE customer (
        id BIGINT PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        name VARCHAR(120) NOT NULL,
        CONSTRAINT uk_customer_email UNIQUE (email)
    );

Hoặc với JPA:

    @Entity
    @Table(
        name = "customer",
        uniqueConstraints = @UniqueConstraint(
            name = "uk_customer_email",
            columnNames = "email"
        )
    )
    public class Customer {
        // fields
    }

### 3.1. Unique trên một cột

Unique constraint trên email ngăn hai row có cùng email theo quy tắc so sánh của database.

Cần xác định email có phân biệt chữ hoa/chữ thường hay không. Một số database/collation so sánh chuỗi không phân biệt hoa thường; database khác có thể phân biệt. Nếu nghiệp vụ xem An@example.test và an@example.test là cùng một địa chỉ, cần chuẩn hóa giá trị hoặc tạo unique index theo biểu thức phù hợp với database.

Không chỉ kiểm tra bằng cách gọi toLowerCase() tùy tiện. Hãy xác định chuẩn normalization, locale và cách lưu dữ liệu nhất quán.

### 3.2. Unique trên nhiều cột

Một tổ hợp nhiều cột có thể phải duy nhất dù từng cột riêng lẻ được phép lặp.

Ví dụ mã phòng ban duy nhất trong từng tenant:

    @Table(
        uniqueConstraints = @UniqueConstraint(
            name = "uk_department_tenant_code",
            columnNames = {"tenant_id", "code"}
        )
    )

Constraint này cho phép hai tenant khác nhau dùng cùng code, nhưng không cho phép hai department trong cùng tenant có cùng code.

Khi kiểm tra sớm bằng repository, method phải kiểm tra đúng tổ hợp:

    boolean existsByTenantIdAndCode(Long tenantId, String code);

Nếu chỉ kiểm tra code mà không xét tenant, validator có thể từ chối nhầm dữ liệu hợp lệ.

### 3.3. Unique và giá trị null

Cách UNIQUE xử lý null phụ thuộc database. Nhiều database cho phép nhiều hàng có NULL trong unique column vì NULL không được xem là bằng một giá trị NULL khác; một số hệ quản trị có cú pháp hoặc semantics riêng.

Nếu field bắt buộc phải có giá trị, kết hợp UNIQUE với NOT NULL. Nếu nghiệp vụ cho phép null, hãy kiểm tra hành vi cụ thể của database và schema.

### 3.4. @Column(unique = true) và @UniqueConstraint

Có thể khai báo:

    @Column(unique = true)
    private String email;

Cách này tiện cho unique constraint đơn cột. Dùng @Table(uniqueConstraints = ...) khi cần:

- Đặt tên constraint.
- Tạo unique constraint trên nhiều cột.
- Khai báo rõ cấu trúc bảng.

Các annotation JPA chủ yếu mô tả schema. Nếu database đã được tạo và migration quản lý schema, phải kiểm tra migration có thực sự tạo constraint tương ứng hay chưa.

## 4. Kiểm tra uniqueness trước khi ghi

Repository có thể cung cấp query method để kiểm tra trùng:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        boolean existsByEmail(String email);

        boolean existsByEmailAndIdNot(String email, Long id);
    }

Khi tạo mới:

    if (customers.existsByEmail(request.getEmail())) {
        errors.rejectValue(
            "email",
            "customer.email.duplicate",
            "Email is already registered"
        );
    }

Khi cập nhật, cần loại trừ chính entity đang được cập nhật:

    if (customers.existsByEmailAndIdNot(
            request.getEmail(), customerId)) {
        errors.rejectValue(
            "email",
            "customer.email.duplicate",
            "Email is already used by another customer"
        );
    }

Nếu quên điều kiện ID khác, một Customer cập nhật mà giữ nguyên email hiện tại sẽ bị báo trùng với chính nó.

### 4.1. Vì sao existsBy... không đủ?

Giả sử hai request đồng thời cùng tạo email `an@example.test`:

1. Transaction A kiểm tra existsByEmail và nhận false.
2. Transaction B kiểm tra existsByEmail và cũng nhận false.
3. A insert row.
4. B insert row.
5. Nếu không có unique constraint, cả hai có thể được lưu.
6. Nếu có unique constraint, chỉ một transaction thành công; transaction còn lại bị database từ chối.

Đây là race condition giữa kiểm tra và ghi (time-of-check to time-of-use). Transaction isolation mặc định không tự động biến một truy vấn exists thành khóa duy nhất cho giá trị đó trong mọi database.

Vì vậy:

- Dùng validator/exists query để trả lỗi sớm, dễ hiểu.
- Dùng UNIQUE để bảo vệ dữ liệu trong mọi trường hợp đồng thời.
- Bắt và chuyển lỗi constraint thành response API phù hợp.

## 5. Ràng buộc FOREIGN KEY

Foreign key bảo đảm giá trị tham chiếu trong bảng con phải trỏ đến một row hợp lệ ở bảng cha.

Ví dụ Order phải tham chiếu Customer:

    CREATE TABLE customer (
        id BIGINT PRIMARY KEY
    );

    CREATE TABLE orders (
        id BIGINT PRIMARY KEY,
        customer_id BIGINT NOT NULL,
        CONSTRAINT fk_order_customer
            FOREIGN KEY (customer_id)
            REFERENCES customer(id)
    );

Với JPA:

    @Entity
    public class Order {

        @Id
        @GeneratedValue
        private Long id;

        @ManyToOne(optional = false)
        @JoinColumn(
            name = "customer_id",
            nullable = false,
            foreignKey = @ForeignKey(name = "fk_order_customer")
        )
        private Customer customer;
    }

Các thành phần có ý nghĩa khác nhau:

- @ManyToOne mô tả quan hệ object giữa Order và Customer.
- optional = false mô tả association không được thiếu ở mức mapping.
- @JoinColumn(name = ...) xác định cột foreign key.
- nullable = false mô tả cột không nhận null.
- @ForeignKey(name = ...) cung cấp metadata tên constraint cho schema generation.

Database chỉ bảo vệ tham chiếu khi foreign key thực sự tồn tại trong schema.

### 5.1. Kiểm tra tham chiếu trước khi ghi

Có thể kiểm tra Customer tồn tại trước khi tạo Order:

    if (!customers.existsById(request.getCustomerId())) {
        errors.rejectValue(
            "customerId",
            "order.customer.notFound",
            "Customer does not exist"
        );
    }

Sau đó service lấy entity và gán association:

    Customer customer = customers.findById(request.getCustomerId())
        .orElseThrow(CustomerNotFoundException::new);

    Order order = new Order();
    order.setCustomer(customer);

    orders.save(order);

Cách này tạo lỗi rõ ràng cho client nếu Customer không tồn tại. Tuy nhiên, Customer vẫn có thể bị xóa giữa lúc kiểm tra và lúc insert Order. Foreign key database là lớp cuối cùng ngăn Order trỏ đến row không còn tồn tại.

### 5.2. Không nhận toàn bộ entity lồng nhau từ client một cách mù quáng

Một request body có thể gửi:

    {
      "customer": {
        "id": 1001
      }
    }

Việc deserialize object lồng nhau không chứng minh Customer 1001 tồn tại hoặc client có quyền sử dụng Customer đó.

Trong API có quy tắc rõ ràng, nên nhận customerId hoặc association URI, xác thực ID và quyền truy cập, rồi tải entity từ repository. Spring Data REST cũng hỗ trợ tham chiếu association bằng URI theo representation của nó. Dù dùng cách nào, server phải kiểm tra tham chiếu và authorization.

## 6. Kiểm tra và ràng buộc khi cập nhật

Khi PUT/PATCH thay đổi field có unique constraint hoặc association có foreign key, cần kiểm tra trạng thái mới.

Ví dụ đổi email:

    @Transactional
    public Customer updateEmail(Long id, String newEmail) {
        Customer customer = customers.findById(id)
            .orElseThrow(CustomerNotFoundException::new);

        if (customers.existsByEmailAndIdNot(newEmail, id)) {
            throw new DuplicateEmailException(newEmail);
        }

        customer.setEmail(newEmail);
        return customers.save(customer);
    }

Kiểm tra sớm giúp đưa ra lỗi nghiệp vụ rõ ràng. Nhưng unique constraint vẫn phải tồn tại để xử lý hai update đồng thời.

Với foreign key, cập nhật association cần kiểm tra entity đích tồn tại và được phép liên kết. Database ngăn ID không hợp lệ, nhưng không tự hiểu mọi quy tắc nghiệp vụ như cùng tenant, cùng trạng thái hoặc có quyền sử dụng.

Ví dụ một Order chỉ được gán cho Customer cùng tenant. Foreign key đơn giản tới customer.id có thể không đủ để thể hiện quy tắc này. Cần kiểm tra tenant trong service/validator và cân nhắc composite foreign key nếu schema/domain yêu cầu bảo đảm ở database.

## 7. Xử lý lỗi database constraint

Khi insert hoặc update vi phạm UNIQUE hoặc FOREIGN KEY, database từ chối statement. Persistence provider có thể ném exception; Spring thường dịch exception truy cập dữ liệu thành nhóm DataAccessException, chẳng hạn DataIntegrityViolationException.

Ví dụ xử lý trong service:

    @Transactional
    public Customer create(Customer customer) {
        try {
            return customers.saveAndFlush(customer);
        } catch (DataIntegrityViolationException ex) {
            throw new CustomerConstraintException(
                "Customer data conflicts with an existing record",
                ex
            );
        }
    }

Ví dụ này giả định repository là JpaRepository. Với CrudRepository, có thể dùng EntityManager.flush hoặc một cách flush phù hợp. Mục đích của flush là buộc provider gửi SQL sớm để constraint violation xuất hiện trong phạm vi xử lý hiện tại.

Không phải lúc nào flush cũng là thời điểm cuối cùng lỗi xuất hiện. Constraint deferred có thể chỉ được kiểm tra lúc commit. Exception handling cần đặt ở transaction boundary có thể quan sát được lỗi commit.

### 7.1. Phân biệt lỗi validation và lỗi constraint

| Lỗi | Ví dụ | Cách xử lý phù hợp |
|---|---|---|
| Input validation | Email sai định dạng | 400 Bad Request với field error |
| Business validation | Customer đã bị khóa nên không được tạo Order | Lỗi nghiệp vụ có status được API quy định |
| UNIQUE violation | Hai request cùng tạo email | Thường ánh xạ thành 409 Conflict |
| FOREIGN KEY violation | customer_id không tồn tại | 400 hoặc 409 theo contract; thường trả lỗi tham chiếu rõ ràng |
| Missing resource | Item ID không tồn tại | 404 Not Found theo contract |
| Method không được export | DELETE bị tắt | 405 Method Not Allowed |

Không nên khẳng định Spring Data REST luôn ánh xạ mọi DataIntegrityViolationException thành một status duy nhất. Kết quả phụ thuộc exception handler, Spring Data REST version và cấu hình ứng dụng. Nếu API cần status ổn định, hãy định nghĩa exception mapping tường minh.

### 7.2. Không trả thông tin database nội bộ

Response lỗi nên cung cấp:

- Mã lỗi ổn định, ví dụ CUSTOMER_EMAIL_DUPLICATE.
- Field hoặc resource liên quan nếu phù hợp.
- Thông điệp có thể hiểu và hành động được.
- Correlation ID nếu cần điều tra.

Không trả nguyên văn SQL, tên schema/table nội bộ, dữ liệu nhạy cảm, stack trace hoặc thông tin kết nối database.

### 7.3. Không bắt rồi tiếp tục transaction đã hỏng

Một số lỗi persistence đánh dấu transaction rollback-only. Sau khi database constraint thất bại, không nên bắt exception rồi tiếp tục thực hiện thêm thao tác trong cùng transaction như thể mọi thứ bình thường.

Hãy để transaction rollback, chuyển exception ở ranh giới thích hợp và tạo response lỗi sau khi trạng thái transaction đã rõ.

## 8. Kết hợp validator với Spring Data REST

Có thể tổ chức validation cho repository exporter theo các tầng:

### Tầng 1 — Constraint trên domain/request model

Dùng annotation như @NotBlank, @Email, @Size cho quy tắc độc lập với database.

### Tầng 2 — Validator trước create/save

Dùng Spring Validator bean hoặc repository event handler để kiểm tra quy tắc cần truy cập repository, ví dụ email đã tồn tại hay customer tham chiếu có hợp lệ.

### Tầng 3 — Database constraint

Đảm bảo UNIQUE, FOREIGN KEY, NOT NULL và CHECK được tạo trong schema thật. Đây là lớp bảo vệ cuối cùng khi có concurrent request hoặc một đường ghi khác bỏ qua validator.

### Tầng 4 — Exception mapping

Chuyển lỗi constraint còn sót lại thành API response ổn định. Cần giữ nguyên transaction rollback và không làm lộ chi tiết database.

Ví dụ handler trước khi tạo:

    @Component
    @RepositoryEventHandler(Order.class)
    public class OrderValidator {

        private final CustomerRepository customers;

        public OrderValidator(CustomerRepository customers) {
            this.customers = customers;
        }

        @HandleBeforeCreate
        public void validateBeforeCreate(Order order) {
            if (order.getCustomer() == null
                    || order.getCustomer().getId() == null
                    || !customers.existsById(
                        order.getCustomer().getId())) {
                throw new IllegalArgumentException(
                    "A valid customer reference is required"
                );
            }
        }
    }

Đây là ví dụ minh họa cho một quy tắc trước create. Trong dự án thực tế, nên dùng exception domain riêng và ánh xạ nó thành status/body phù hợp. Foreign key vẫn phải tồn tại để bảo vệ tính toàn vẹn nếu trạng thái thay đổi giữa validation và insert.

## 9. Thiết kế constraint trong migration

Nếu dùng Flyway, migration có thể tạo constraint rõ ràng:

    ALTER TABLE customer
        ALTER COLUMN email SET NOT NULL;

    ALTER TABLE customer
        ADD CONSTRAINT uk_customer_email UNIQUE (email);

    ALTER TABLE orders
        ADD CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(id);

Cú pháp cụ thể phụ thuộc database. Ví dụ trên dùng cú pháp kiểu PostgreSQL; SQL Server, MySQL, Oracle và các hệ quản trị khác có khác biệt.

Trước khi thêm unique constraint vào bảng đang có dữ liệu:

1. Tìm các giá trị bị trùng.
2. Xác định quy tắc chuẩn hóa và cách xử lý hoa/thường.
3. Làm sạch dữ liệu hiện có.
4. Tạo constraint hoặc unique index trong migration.
5. Xác minh constraint đã được tạo trong database mục tiêu.

Trước khi thêm foreign key:

1. Tìm các foreign key value không có row cha tương ứng.
2. Xử lý dữ liệu mồ côi.
3. Kiểm tra nullability và dữ liệu lịch sử.
4. Tạo foreign key.
5. Xác minh constraint được bật và có hiệu lực.

Không dựa vào annotation JPA nếu schema production được quản lý độc lập.

## 10. Kiểm thử

Nên kiểm tra cả validator lẫn database constraint. Chỉ unit test validator không chứng minh database đã có constraint; chỉ integration test database không chứng minh client nhận được thông báo lỗi tốt.

### 10.1. Test Bean Validation

- Email sai định dạng bị từ chối.
- Field bắt buộc bị null hoặc blank bị từ chối.
- Chuỗi vượt giới hạn bị từ chối.
- Error path và error code xác định đúng field.

### 10.2. Test unique constraint

- Tạo Customer với email chưa tồn tại thành công.
- Tạo Customer với email trùng bị từ chối.
- Cập nhật Customer mà giữ nguyên email của chính nó thành công.
- Cập nhật sang email của Customer khác bị từ chối.
- Hai transaction đồng thời tạo cùng email: chỉ một transaction được commit.

### 10.3. Test foreign key

- Tạo Order với Customer tồn tại thành công.
- Tạo Order với Customer ID không tồn tại bị từ chối.
- Xóa Customer đang được Order tham chiếu bị từ chối nếu constraint dùng RESTRICT/NO ACTION.
- Thử xóa Customer theo chính sách cascade nếu nghiệp vụ cho phép và xác nhận đúng child rows bị ảnh hưởng.

### 10.4. Test API response

Với MockMvc hoặc test HTTP tương đương, xác nhận:

- Validation error trả status và body theo API contract.
- Duplicate email được ánh xạ thành lỗi conflict có mã ổn định.
- Missing reference được mô tả rõ ràng.
- Raw SQL và stack trace không xuất hiện trong response.
- Transaction rollback khi constraint thất bại.
- Request hợp lệ vẫn được lưu và representation JSON/HAL đúng.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Validator báo trùng nhưng database vẫn có dữ liệu trùng | Schema chưa có UNIQUE hoặc validator kiểm tra sai phạm vi |
| Hai request đồng thời cùng tạo được một giá trị | Chỉ có exists query, thiếu unique constraint database |
| Cập nhật entity bị báo trùng chính nó | Query kiểm tra thiếu điều kiện loại trừ ID hiện tại |
| Order tham chiếu Customer không tồn tại vẫn được lưu | Foreign key chưa được tạo hoặc mapping/schema không đồng bộ |
| @Column(unique = true) không tạo constraint production | Schema được quản lý bằng migration và migration chưa thêm constraint |
| Lỗi xuất hiện khi commit, không phải ở save | SQL/constraint được kiểm tra lúc flush hoặc commit |
| API trả 500 cho duplicate | Exception mapping chưa xử lý DataIntegrityViolationException cụ thể |
| Validation không chạy trên repository REST endpoint | Chưa đăng ký đúng validator bean name/event handler hoặc cấu hình sai |
| Request PATCH bị từ chối khi bỏ field | Dùng validation rule cho create/update không phân biệt trạng thái field |
| Constraint báo lỗi khó hiểu | Chưa đặt tên constraint hoặc chưa ánh xạ database exception sang mã lỗi nghiệp vụ |

## 12. Checklist triển khai

1. Xác định quy tắc nào là input validation, quy tắc nào là database integrity.
2. Đặt Bean Validation constraint cho format, nullability và giới hạn field.
3. Đăng ký Spring Validator hoặc repository event handler cho quy tắc cần truy vấn.
4. Dùng exists query để phát hiện duplicate/reference lỗi sớm.
5. Khi update, loại trừ chính entity hiện tại khỏi kiểm tra uniqueness.
6. Tạo UNIQUE và FOREIGN KEY thật trong schema qua migration hoặc schema management.
7. Kiểm tra race condition: validator không thay thế database constraint.
8. Xác định transaction boundary và thời điểm flush/commit.
9. Ánh xạ constraint violation thành status, error code và thông điệp ổn định.
10. Kiểm thử request hợp lệ, dữ liệu trùng, reference thiếu và request đồng thời.
11. Xác minh schema production có constraint thực sự.
12. Không trả raw SQL hoặc thông tin nội bộ cho client.

## Tài liệu tham khảo

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
- [Jakarta Persistence — Table and Column mapping](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Framework — DataIntegrityViolationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html)
