# Kết hợp Bean Validation, quy tắc nghiệp vụ và ràng buộc cơ sở dữ liệu

Một ứng dụng Spring Data JPA cần kiểm tra dữ liệu ở nhiều thời điểm và nhiều lớp. Bean Validation kiểm tra hình dạng và tính hợp lệ cơ bản của dữ liệu đầu vào; quy tắc nghiệp vụ quyết định thao tác có được phép trong trạng thái hiện tại hay không; ràng buộc database bảo vệ tính toàn vẹn của dữ liệu ngay tại nơi lưu trữ.

Ba lớp này giải quyết các vấn đề khác nhau và bổ trợ cho nhau. Chỉ kiểm tra ở API là chưa đủ vì dữ liệu có thể đến từ batch, message consumer hoặc service khác. Chỉ dựa vào database cũng chưa đủ vì thông báo lỗi thường khó hiểu với người dùng và không diễn đạt được mọi quy tắc nghiệp vụ.

## 1. Ba lớp kiểm tra có trách nhiệm gì?

| Lớp | Mục đích | Ví dụ |
|---|---|---|
| Bean Validation | Kiểm tra cấu trúc và điều kiện cục bộ của dữ liệu | email đúng định dạng, tên không rỗng, số lượng lớn hơn 0 |
| Business validation | Kiểm tra quy tắc theo nghiệp vụ, trạng thái và ngữ cảnh | không hủy đơn đã giao, không vượt hạn mức được cấp |
| Database constraints | Bảo vệ tính toàn vẹn tại nơi lưu dữ liệu, kể cả khi có nhiều writer | UNIQUE, NOT NULL, FOREIGN KEY, CHECK |

Ví dụ khi đăng ký khách hàng:

- Bean Validation từ chối email rỗng hoặc không đúng định dạng.
- Quy tắc nghiệp vụ kiểm tra khách hàng có đủ điều kiện đăng ký hoặc email đã được sử dụng theo chính sách ứng dụng hay chưa.
- Database áp đặt unique constraint trên email để ngăn hai request đồng thời tạo cùng một email.

Một điều kiện có thể được kiểm tra ở nhiều lớp nếu mỗi lớp có mục đích riêng. Ví dụ số lượng không được âm có thể được kiểm tra trong DTO để trả lỗi sớm, trong domain model để bảo vệ nghiệp vụ và bằng CHECK constraint để bảo vệ dữ liệu trước mọi đường ghi.

## 2. Bean Validation trên request DTO

Với API, nên xác thực dữ liệu nhận vào trên DTO. Điều này tách hợp đồng HTTP khỏi entity JPA và giúp ứng dụng kiểm tra dữ liệu trước khi bắt đầu thao tác database.

Ví dụ dùng Java 17 record và Jakarta Bean Validation:

```java
package com.example.customer.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
        @NotBlank(message = "Email is required")
        @Email(message = "Email format is invalid")
        @Size(max = 254, message = "Email is too long")
        String email,

        @NotBlank(message = "Name is required")
        @Size(max = 120, message = "Name is too long")
        String name
) {
}
```

Controller kích hoạt validation bằng `@Valid`:

```java
package com.example.customer.api;

import com.example.customer.Customer;
import com.example.customer.CustomerService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Customer create(
            @Valid @RequestBody CreateCustomerRequest request) {
        return service.create(request);
    }
}
```

Khi dữ liệu không đạt constraint trên request body, Spring MVC thực hiện validation trước khi gọi service. Với cấu hình Spring MVC thông thường, lỗi này được báo dưới dạng `MethodArgumentNotValidException`; ứng dụng có thể chuyển các field error thành response HTTP 400 có cấu trúc.

Một số lưu ý:

- `@NotBlank` từ chối null, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng.
- `@Email` kiểm tra định dạng theo validator; nó không chứng minh địa chỉ email thực sự tồn tại hoặc người dùng sở hữu địa chỉ đó.
- `@Size` giới hạn độ dài dữ liệu. Database vẫn cần độ dài cột phù hợp.
- `@Valid` trên field lồng nhau giúp cascade validation sang object con; với collection, đặt `@Valid` trên phần tử cần kiểm tra.
- Nếu không có Bean Validation provider trên classpath, annotation có thể không được thực thi. Trong Spring Boot, thường thêm starter validation phù hợp với phiên bản dự án.

Không nên nhận trực tiếp entity từ request rồi bind mọi field. DTO giúp tránh việc client tự gửi các trường như ID, trạng thái, role hoặc audit metadata mà chỉ server mới được quyền thay đổi.

## 3. Validation cho quy tắc liên quan nhiều field

Một số điều kiện chỉ có ý nghĩa khi xem nhiều trường cùng lúc, ví dụ ngày bắt đầu phải trước ngày kết thúc hoặc loại thanh toán quyết định trường thông tin nào bắt buộc.

Có thể dùng class-level constraint với custom validator, hoặc kiểm tra trong service/domain nếu điều kiện phụ thuộc nghiệp vụ. Class-level constraint phù hợp với quy tắc cấu trúc của một request; quy tắc phụ thuộc database hoặc trạng thái hiện tại thường thuộc business layer.

Ví dụ, một request có khoảng thời gian:

```java
public record BookingRequest(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate
) {
}
```

Quy tắc `startDate <= endDate` có thể được cài đặt bằng custom class-level annotation như `@ValidDateRange`. Validator nhận toàn bộ object, kiểm tra hai giá trị và trả lỗi gắn với object hoặc field phù hợp. Khi viết custom validator, cần xử lý null theo cách nhất quán: các constraint `@NotNull` kiểm tra null riêng, còn validator khoảng thời gian có thể bỏ qua khi một đầu mốc null để tránh lặp thông báo.

Không nên nhồi mọi điều kiện nghiệp vụ vào custom validator. Validator thường nên thuần, nhanh và không phụ thuộc trạng thái transaction hoặc truy vấn database.

## 4. Đặt quy tắc nghiệp vụ trong domain/service

Quy tắc nghiệp vụ quyết định một hành động có hợp lệ trong trạng thái hiện tại hay không. Ví dụ đơn hàng đã giao thì không được hủy.

```java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
```

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public void cancel() {
        if (status == OrderStatus.SHIPPED) {
            throw new OrderRuleViolationException(
                    "A shipped order cannot be cancelled");
        }

        if (status == OrderStatus.CANCELLED) {
            throw new OrderRuleViolationException(
                    "The order is already cancelled");
        }

        status = OrderStatus.CANCELLED;
    }
}
```

Service tải aggregate, gọi hành vi nghiệp vụ và lưu thay đổi:

```java
@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void cancel(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.cancel();
    }
}
```

Khi entity đang được quản lý trong persistence context, JPA dirty checking sẽ ghi nhận thay đổi; không nhất thiết phải gọi `save` lại cho entity managed. Repository `save` vẫn hữu ích khi thao tác với entity mới hoặc entity detached theo cách phù hợp.

Đặt quy tắc gắn với trạng thái bên trong aggregate giúp mọi caller dùng cùng một hành vi. Những quy tắc cần đọc dữ liệu từ nhiều aggregate hoặc repository, ví dụ hạn mức tín dụng tổng hay điều kiện phụ thuộc subscription, thường cần service/domain service điều phối và transaction rõ ràng.

Không nên chỉ dựa vào controller để kiểm tra quy tắc nghiệp vụ. Batch job, message consumer hoặc một API nội bộ khác có thể gọi service mà không đi qua controller.

## 5. Bean Validation trên entity và vòng đời JPA

Có thể đặt một số constraint lên entity để kiểm tra trạng thái entity khi JPA persist hoặc update. Ví dụ:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Email
    @Column(nullable = false, length = 254)
    private String email;

    @NotBlank
    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
    }

    public Customer(String email, String name) {
        this.email = email;
        this.name = name;
    }
}
```

Khi JPA được tích hợp với Bean Validation provider, các constraint trên entity có thể được thực thi trong các sự kiện persist/update theo cấu hình validation mode. Với cấu hình mặc định, provider thường kiểm tra trước khi ghi dữ liệu tương ứng; vì vậy lỗi có thể xuất hiện tại `persist`, `flush` hoặc commit cuối transaction.

Tuy nhiên, không nên coi entity annotation là lớp bảo vệ duy nhất:

- Các đường ghi ngoài JPA như JDBC, native SQL hoặc công cụ quản trị không chạy Bean Validation listener của JPA.
- Bulk JPQL update/delete bỏ qua lifecycle callback của từng entity.
- Entity có thể được thay đổi trong bộ nhớ trước khi validation thực sự chạy.
- Validation của entity không thay thế việc xác thực request DTO hoặc quy tắc nghiệp vụ.

Nếu cùng một constraint xuất hiện trên DTO và entity, hãy xác định rõ mục tiêu của từng nơi. DTO bảo vệ hợp đồng đầu vào; entity bảo vệ trạng thái object khi đi qua lifecycle JPA.

## 6. Database constraints là lớp bảo vệ cuối cùng

Database constraint đảm bảo dữ liệu hợp lệ dù thao tác ghi đến từ ứng dụng nào hoặc xảy ra đồng thời ra sao.

Các constraint thường dùng:

- **NOT NULL:** cột bắt buộc phải có giá trị.
- **UNIQUE:** không cho phép giá trị hoặc tổ hợp giá trị trùng.
- **PRIMARY KEY:** định danh duy nhất cho từng hàng.
- **FOREIGN KEY:** bảo đảm quan hệ tham chiếu tới hàng tồn tại.
- **CHECK:** giới hạn giá trị theo biểu thức, ví dụ số lượng không âm.

Ví dụ migration SQL:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    name VARCHAR(120) NOT NULL,
    CONSTRAINT uk_customer_email UNIQUE (email)
);

CREATE TABLE inventory (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    available INTEGER NOT NULL,
    CONSTRAINT ck_inventory_available_nonnegative
        CHECK (available >= 0)
);
```

Dùng Flyway hoặc Liquibase để quản lý schema migration một cách có kiểm soát. Các annotation như `@Column(nullable = false)`, `@Column(unique = true)` và `@Table(uniqueConstraints = ...)` mô tả mapping và có thể hỗ trợ tạo schema khi bật DDL generation. Trong môi trường production, migration rõ ràng giúp xác định constraint thực sự đang tồn tại trong database.

Đối với quan hệ, hãy khai báo foreign key ở database. `@ManyToOne` hoặc `@OneToMany` mô tả quan hệ trong object model, nhưng không nên giả định mapping annotation tự bảo đảm mọi database schema đã có foreign key tương ứng nếu schema được quản lý bên ngoài.

## 7. Vì sao kiểm tra trước khi ghi không thay thế được UNIQUE constraint?

Giả sử service kiểm tra email trước khi tạo khách hàng:

```java
if (repository.existsByEmail(normalizedEmail)) {
    throw new EmailAlreadyRegisteredException();
}

repository.save(new Customer(normalizedEmail, name));
```

Kiểm tra này giúp trả thông báo sớm trong trường hợp email đã tồn tại tại thời điểm truy vấn. Nhưng nó không loại bỏ race condition:

1. Request A kiểm tra và thấy email chưa tồn tại.
2. Request B cũng kiểm tra và thấy email chưa tồn tại.
3. Cả hai cùng thực hiện INSERT.
4. Database chỉ cho phép một transaction commit vì unique constraint.

Do đó, unique constraint là điều kiện bắt buộc nếu dữ liệu phải duy nhất. Kiểm tra `existsByEmail` chỉ là cải thiện trải nghiệm; ứng dụng vẫn phải xử lý lỗi database khi có cạnh tranh.

Nếu quy tắc không phân biệt chữ hoa/thường, hãy chuẩn hóa email trước khi lưu và truy vấn, hoặc tạo unique index phù hợp với collation/biểu thức của database. Cần bảo đảm mọi writer tuân thủ cùng một quy tắc chuẩn hóa. Đừng giả định `UNIQUE(email)` tự động coi `A@example.com` và `a@example.com` là cùng giá trị trên mọi database.

## 8. Xử lý lỗi validation và constraint thành response phù hợp

Các lỗi có thể phát sinh ở những thời điểm khác nhau:

| Loại lỗi | Ví dụ | Nơi thường phát hiện |
|---|---|---|
| Request Bean Validation | email rỗng, tên quá dài | Trước khi gọi service |
| Business rule | không hủy đơn đã giao | Trong domain/service |
| JPA Bean Validation | entity vi phạm `@NotNull` hoặc `@Size` | Persist, flush hoặc commit |
| Database constraint | unique, foreign key, check | Khi database thực thi SQL hoặc commit |

Spring MVC thường ném `MethodArgumentNotValidException` khi `@Valid @RequestBody` không hợp lệ. Method validation có thể ném `jakarta.validation.ConstraintViolationException`. JPA Bean Validation cũng dùng exception thuộc Jakarta Validation.

Lỗi database constraint được Spring dịch thường thành `DataIntegrityViolationException`; Hibernate có `org.hibernate.exception.ConstraintViolationException` cho lỗi SQL constraint. Cần phân biệt exception của Hibernate với `jakarta.validation.ConstraintViolationException`: tên gần giống nhau nhưng nguồn gốc khác nhau.

Có thể dùng `@RestControllerAdvice` để chuẩn hóa response:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<?> handleInvalidRequest(
            MethodArgumentNotValidException ex) {
        // Trả HTTP 400 cùng danh sách field errors.
        return ResponseEntity.badRequest().body(
                Map.of("error", "INVALID_REQUEST"));
    }

    @ExceptionHandler(OrderRuleViolationException.class)
    ResponseEntity<?> handleBusinessRule(
            OrderRuleViolationException ex) {
        // Trả lỗi nghiệp vụ phù hợp, ví dụ HTTP 409.
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                Map.of("error", ex.getMessage()));
    }
}
```

Đoạn code minh họa hai loại lỗi có thể ánh xạ trực tiếp. Với `DataIntegrityViolationException`, không nên mặc định mọi trường hợp đều là email trùng. Nó có thể xuất phát từ unique, foreign key, NOT NULL hoặc CHECK. Hãy phân loại theo constraint/schema và nghiệp vụ đã biết; tránh phân tích chuỗi thông báo vendor-specific như cơ chế chính. Không trả SQL, tên bảng nội bộ hoặc dữ liệu nhạy cảm ra response công khai.

Khi lỗi database chỉ xuất hiện lúc flush hoặc commit, hãy bắt ở ngoài transaction boundary, chẳng hạn tại caller của service `@Transactional` hoặc trong exception handler của request. Bắt rồi bỏ qua persistence exception bên trong transaction có thể để transaction ở trạng thái rollback-only.

## 9. Validation groups và method validation

Với cùng một object, một số ứng dụng cần các nhóm kiểm tra khác nhau theo thao tác. Ví dụ khi tạo mới thì ID phải vắng mặt, còn khi cập nhật thì ID phải có. Bean Validation hỗ trợ validation groups để chọn tập constraint cần chạy. Tuy nhiên, không nên lạm dụng groups khiến DTO khó hiểu; nhiều trường hợp hai DTO riêng cho create và update rõ ràng hơn.

Service cũng có thể bật method validation bằng `@Validated` và đặt constraint trên tham số/phương thức:

```java
@Service
@Validated
public class InventoryService {

    public void reserve(@Positive int quantity) {
        // Thực hiện nghiệp vụ sau khi tham số hợp lệ.
    }
}
```

Method validation phụ thuộc cấu hình Spring validation và việc lời gọi đi qua proxy tương ứng. Gọi method nội bộ trong cùng object có thể bỏ qua proxy validation. Dù dùng method validation, quy tắc phụ thuộc trạng thái database vẫn cần được kiểm tra ở business layer và database constraint.

## 10. Quy trình thiết kế và kiểm thử

Khi thêm một trường hoặc thao tác nghiệp vụ, hãy xác định rõ điều kiện thuộc lớp nào:

1. **Đầu vào:** dữ liệu có đúng kiểu, không rỗng, đúng định dạng và nằm trong giới hạn kích thước không? Dùng Bean Validation trên DTO.
2. **Nghiệp vụ:** hành động có được phép theo trạng thái hiện tại, quyền người dùng và dữ liệu liên quan không? Dùng domain method hoặc service/domain service.
3. **Toàn vẹn dữ liệu:** dữ liệu có phải duy nhất, bắt buộc, tham chiếu hợp lệ hoặc nằm trong miền giá trị không? Tạo database constraint bằng migration.
4. **Lỗi đồng thời:** nếu hai transaction cùng vượt qua bước kiểm tra trước, database có ngăn được trạng thái sai không? Dùng UNIQUE, CHECK, optimistic locking hoặc conditional update phù hợp.
5. **Phản hồi:** ánh xạ lỗi đầu vào, lỗi nghiệp vụ và lỗi constraint thành response có ý nghĩa, không để lộ chi tiết nội bộ.

Bộ test nên bao gồm:

- Request thiếu email hoặc email sai định dạng bị từ chối trước khi service chạy.
- Quy tắc domain từ chối chuyển trạng thái không hợp lệ.
- Entity vi phạm constraint được phát hiện khi persist/flush theo cấu hình JPA.
- Database từ chối giá trị vi phạm NOT NULL, UNIQUE, FOREIGN KEY hoặc CHECK.
- Hai request đồng thời đăng ký cùng email: chỉ một transaction thành công nhờ unique constraint.
- Bulk update hoặc native SQL được kiểm tra riêng vì chúng có thể bỏ qua Bean Validation lifecycle và domain method.
- Các integration test quan trọng chạy trên database engine tương thích với production; Testcontainers là lựa chọn hữu ích để kiểm tra hành vi constraint và cạnh tranh thay vì chỉ dựa vào database giả lập.

## 11. Lỗi thiết kế thường gặp

- **Chỉ validate ở controller:** batch, message consumer và các caller khác có thể bỏ qua controller. Đặt quy tắc dùng chung trong domain/service và database.
- **Chỉ kiểm tra bằng `existsBy...`:** hai transaction có thể cùng thấy dữ liệu chưa tồn tại. Dùng unique constraint để bảo vệ cuối cùng.
- **Đưa mọi quy tắc vào entity annotation:** annotation không diễn đạt tốt quy tắc phụ thuộc trạng thái, quyền hoặc nhiều aggregate.
- **Dùng database constraint để thay mọi validation:** database có thể từ chối dữ liệu nhưng thông báo thường không đủ thân thiện; lỗi nghiệp vụ nên được phát hiện sớm hơn khi có thể.
- **Nhầm `@Column(nullable = false)` với constraint đã tồn tại:** kiểm tra schema migration thực tế và xác nhận database có NOT NULL.
- **Bắt mọi `DataIntegrityViolationException` thành lỗi email trùng:** lỗi có thể do foreign key, check hoặc constraint khác. Phân loại theo nguyên nhân và ngữ cảnh.
- **Cho rằng bulk update chạy đầy đủ entity validation:** bulk JPQL/native SQL bỏ qua lifecycle của từng entity. Tự kiểm tra điều kiện trong câu lệnh và bảo vệ bằng database constraint.
- **Chỉ kiểm thử H2 trong khi production dùng database khác:** khác biệt về collation, kiểu dữ liệu, constraint, isolation và locking có thể che giấu lỗi. Dùng Testcontainers hoặc môi trường tích hợp tương đương cho các hành vi quan trọng.

## 12. Ghi nhớ

Bean Validation giúp từ chối dữ liệu đầu vào không đúng hình dạng; business validation bảo vệ quy tắc và trạng thái nghiệp vụ; database constraints bảo vệ tính toàn vẹn trước mọi đường ghi và cạnh tranh đồng thời. Hãy phân công đúng trách nhiệm cho từng lớp, giữ các ràng buộc quan trọng trong database, xử lý lỗi ở đúng transaction boundary và kiểm thử bằng database gần với production.