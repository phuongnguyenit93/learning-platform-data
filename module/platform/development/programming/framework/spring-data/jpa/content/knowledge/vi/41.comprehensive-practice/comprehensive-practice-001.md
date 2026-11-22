# Xây dựng quản lý khách hàng với CRUD, validation và DTO bằng Spring Data JPA

## 1. Mục tiêu và kiến trúc

Bài thực hành xây dựng một REST API quản lý khách hàng với các chức năng:

- Tạo khách hàng mới.
- Xem chi tiết theo ID.
- Liệt kê, tìm kiếm và phân trang khách hàng.
- Cập nhật thông tin khách hàng.
- Xóa khách hàng.
- Kiểm tra dữ liệu đầu vào bằng Jakarta Bean Validation.
- Dùng DTO để tách hợp đồng HTTP khỏi entity JPA.
- Trả lỗi có cấu trúc cho dữ liệu không hợp lệ, email trùng và khách hàng không tồn tại.

Ứng dụng dùng Java 17+, Spring Boot 3.x, Spring Web MVC, Spring Data JPA, Jakarta Validation và H2 cho môi trường thực hành. Các ví dụ dùng constructor injection, Java record cho DTO và mapping thủ công để người học nhìn thấy rõ luồng dữ liệu.

Luồng xử lý:

~~~text
HTTP request
    |
    v
CustomerController
    |  @Valid + request DTO
    v
CustomerService
    |  transaction + business rules
    v
CustomerRepository
    |  Spring Data JPA
    v
Hibernate / EntityManager
    |
    v
Database

Entity -> mapper -> response DTO -> HTTP response
Exceptions -> GlobalExceptionHandler -> structured HTTP error
~~~

Controller nhận và trả DTO. Service thực hiện nghiệp vụ và quản lý transaction. Repository truy cập database. Entity biểu diễn trạng thái được lưu trữ. Mapper chuyển entity thành response DTO.

Không trả trực tiếp entity từ REST controller. Cách đó có thể làm lộ trường nội bộ, tạo phụ thuộc vào mapping persistence, gây lazy-loading ngoài transaction và khiến thay đổi entity vô tình thay đổi API.

## 2. Khởi tạo project và dependency

Tạo project Spring Boot bằng Spring Initializr với Java 17 trở lên. Chọn Spring Web, Spring Data JPA, Validation, H2 Database và Spring Boot Test.

Các dependency Maven chính:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Để các dependency không có version riêng, project cần kế thừa Spring Boot parent hoặc import Spring Boot dependency BOM. Chọn phiên bản Spring Boot còn được hỗ trợ trong môi trường của dự án; không trộn version Spring Framework, Hibernate và Spring Data JPA thủ công nếu không có lý do tương thích rõ ràng.

Cấu trúc package đề xuất:

~~~text
src/main/java/com/example/customers/
    CustomerApplication.java
    controller/
        CustomerController.java
    dto/
        CreateCustomerRequest.java
        UpdateCustomerRequest.java
        CustomerResponse.java
        PageResponse.java
        ApiError.java
    entity/
        Customer.java
    exception/
        CustomerNotFoundException.java
        DuplicateCustomerEmailException.java
        GlobalExceptionHandler.java
    mapper/
        CustomerMapper.java
    repository/
        CustomerRepository.java
    service/
        CustomerService.java

src/main/resources/
    application.properties

src/test/java/com/example/customers/
    CustomerApiIntegrationTest.java
~~~

Lớp khởi động:

~~~java
package com.example.customers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomerApplication.class, args);
    }
}
~~~

## 3. Thiết kế bảng và Customer entity

Một khách hàng có các trường:

| Trường | Kiểu Java | Quy tắc |
|---|---|---|
| id | Long | Primary key, database sinh |
| fullName | String | Bắt buộc, tối đa 120 ký tự |
| email | String | Bắt buộc, tối đa 320 ký tự, duy nhất |
| phone | String | Không bắt buộc, tối đa 20 ký tự |
| createdAt | Instant | Thời điểm tạo |
| updatedAt | Instant | Thời điểm cập nhật gần nhất |
| version | long | Optimistic locking |

Entity:

~~~java
package com.example.customers.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customers_email",
        columnNames = "email"
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @Column(nullable = false, length = 320)
    private String email;

    @Column(length = 20)
    private String phone;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    private long version;

    protected Customer() {
        // Required by JPA.
    }

    public Customer(String fullName, String email, String phone) {
        this.fullName = fullName;
        this.email = email;
        this.phone = phone;
    }

    public void updateProfile(
            String fullName,
            String email,
            String phone) {
        this.fullName = fullName;
        this.email = email;
        this.phone = phone;
    }

    @PrePersist
    void onCreate() {
        Instant now = Instant.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    @PreUpdate
    void onUpdate() {
        this.updatedAt = Instant.now();
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public String getPhone() {
        return phone;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public long getVersion() {
        return version;
    }
}
~~~

Một số điểm cần hiểu:

- Constructor không tham số có visibility protected để JPA có thể tạo entity.
- Constructor nghiệp vụ nhận các trường được phép thiết lập khi tạo.
- Không cung cấp setter công khai cho ID, timestamp hoặc version.
- Phương thức updateProfile thể hiện thay đổi nghiệp vụ được phép.
- @PrePersist và @PreUpdate là lifecycle callbacks để cập nhật timestamp.
- @Version giúp Hibernate phát hiện cập nhật đồng thời khi entity được ghi.
- Unique constraint ở database là hàng rào cuối cùng để ngăn hai transaction cùng tạo email trùng.

Chuẩn hóa email về chữ thường trước khi lưu để tránh các giá trị như An@Example.com và an@example.com trở thành hai khách hàng khác nhau theo quy tắc của ứng dụng. Nếu hệ thống cần giữ nguyên cách viết email để hiển thị, có thể lưu thêm giá trị hiển thị và một cột normalized_email có unique index.

Không dựa riêng vào kiểm tra email trùng trong Java. Hai request đồng thời có thể cùng kiểm tra thấy email chưa tồn tại rồi cùng insert. Database unique constraint mới bảo đảm tính duy nhất khi có cạnh tranh.

## 4. Tạo request DTO và validation

DTO là đối tượng đại diện cho dữ liệu trao đổi qua API. Request DTO chỉ chứa các trường client được phép gửi. Nó không chứa ID do database sinh, timestamp, version hoặc thuộc tính nội bộ.

### CreateCustomerRequest

~~~java
package com.example.customers.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(

    @NotBlank(message = "Full name is required")
    @Size(max = 120, message = "Full name must not exceed 120 characters")
    String fullName,

    @NotBlank(message = "Email is required")
    @Email(message = "Email format is invalid")
    @Size(max = 320, message = "Email must not exceed 320 characters")
    String email,

    @Size(max = 20, message = "Phone must not exceed 20 characters")
    @Pattern(
        regexp = "^$|^[0-9+(). -]{7,20}$",
        message = "Phone must contain 7 to 20 valid characters"
    )
    String phone
) {
}
~~~

### UpdateCustomerRequest

Với PUT, request được hiểu là nội dung thay thế đầy đủ của phần thông tin có thể chỉnh sửa. Vì vậy, fullName và email vẫn bắt buộc. Phone có thể là chuỗi rỗng hoặc null nếu người dùng muốn bỏ số điện thoại.

~~~java
package com.example.customers.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record UpdateCustomerRequest(

    @NotBlank(message = "Full name is required")
    @Size(max = 120, message = "Full name must not exceed 120 characters")
    String fullName,

    @NotBlank(message = "Email is required")
    @Email(message = "Email format is invalid")
    @Size(max = 320, message = "Email must not exceed 320 characters")
    String email,

    @Size(max = 20, message = "Phone must not exceed 20 characters")
    @Pattern(
        regexp = "^$|^[0-9+(). -]{7,20}$",
        message = "Phone must contain 7 to 20 valid characters"
    )
    String phone
) {
}
~~~

Các annotation quan trọng:

| Annotation | Ý nghĩa |
|---|---|
| @NotNull | Giá trị không được null |
| @NotBlank | Chuỗi phải khác null, rỗng và chỉ chứa whitespace |
| @NotEmpty | Không null và không rỗng; không loại whitespace-only |
| @Size | Giới hạn độ dài chuỗi hoặc kích thước collection |
| @Email | Kiểm tra định dạng email ở mức Bean Validation |
| @Pattern | Kiểm tra chuỗi theo regular expression |
| @Min, @Max | Giới hạn giá trị số |
| @Positive | Giá trị số phải lớn hơn 0 |

@Email không chứng minh email tồn tại hoặc người gửi sở hữu địa chỉ đó. Nếu nghiệp vụ cần xác minh, phải gửi email xác nhận hoặc thực hiện quy trình xác minh riêng.

@Valid tại controller yêu cầu Spring MVC chạy Bean Validation trên request object. Nếu thiếu dependency validation, các annotation có thể không được thực thi như mong muốn.

## 5. Response DTO và DTO phân trang

Response DTO xác định chính xác dữ liệu API công khai:

~~~java
package com.example.customers.dto;

import java.time.Instant;

public record CustomerResponse(
    Long id,
    String fullName,
    String email,
    String phone,
    Instant createdAt,
    Instant updatedAt,
    long version
) {
}
~~~

DTO phân trang:

~~~java
package com.example.customers.dto;

import java.util.List;
import org.springframework.data.domain.Page;

public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last
) {

    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.isFirst(),
            source.isLast()
        );
    }
}
~~~

Trả một DTO phân trang riêng giúp API ổn định hơn việc serialize trực tiếp implementation Page của Spring Data. Client có thể dựa vào các trường content, page, size, totalElements và totalPages mà không phụ thuộc cấu trúc nội bộ của PageImpl.

Không đưa entity vào response DTO. Việc chuyển đổi entity sang DTO cần diễn ra trong service hoặc mapper, trong transaction phù hợp để tránh vô tình truy cập lazy association sau khi persistence context đóng.

## 6. Viết mapper thủ công

Với một entity đơn giản, mapper thủ công dễ đọc và không cần thêm thư viện:

~~~java
package com.example.customers.mapper;

import com.example.customers.dto.CustomerResponse;
import com.example.customers.entity.Customer;

public final class CustomerMapper {

    private CustomerMapper() {
    }

    public static CustomerResponse toResponse(Customer customer) {
        return new CustomerResponse(
            customer.getId(),
            customer.getFullName(),
            customer.getEmail(),
            customer.getPhone(),
            customer.getCreatedAt(),
            customer.getUpdatedAt(),
            customer.getVersion()
        );
    }
}
~~~

Mapper không nhận trực tiếp request rồi sao chép mọi thuộc tính vào entity. Service kiểm soát trường nào được thay đổi và thực hiện quy tắc nghiệp vụ trước khi gọi phương thức domain.

Với dự án lớn có nhiều entity và mapping phức tạp, có thể cân nhắc MapStruct. Dù dùng mapper nào, cần kiểm soát rõ mapping từ request sang entity để tránh mass assignment, ví dụ client tự gửi role, status, ownerId hoặc version mà API không cho phép chỉnh sửa.

## 7. Khai báo CustomerRepository

Spring Data JPA cung cấp CRUD qua JpaRepository:

~~~java
package com.example.customers.repository;

import com.example.customers.entity.Customer;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    boolean existsByEmailIgnoreCase(String email);

    Page<Customer>
    findByFullNameContainingIgnoreCaseOrEmailContainingIgnoreCase(
        String fullName,
        String email,
        Pageable pageable
    );
}
~~~

JpaRepository đã cung cấp các method thường dùng:

- save(entity): lưu mới hoặc cập nhật entity theo quy tắc JPA.
- findById(id): tìm theo primary key, trả Optional.
- findAll(): lấy tất cả entity.
- findAll(pageable): lấy một trang.
- existsById(id): kiểm tra sự tồn tại.
- delete(entity), deleteById(id): xóa entity.
- count(): đếm số entity.

Tên method findByFullNameContainingIgnoreCaseOrEmailContainingIgnoreCase là derived query. Spring Data phân tích tên method, tạo truy vấn phù hợp và bind các tham số. Containing tạo điều kiện tìm chuỗi con; IgnoreCase thực hiện so sánh không phân biệt chữ hoa/chữ thường theo khả năng của provider/database.

Không ghép chuỗi SQL hoặc JPQL từ input người dùng. Derived query và parameter binding giúp tránh lỗi cú pháp và giảm nguy cơ injection.

## 8. Tạo exception nghiệp vụ

Exception riêng giúp service biểu đạt rõ tình huống nghiệp vụ:

~~~java
package com.example.customers.exception;

public class CustomerNotFoundException extends RuntimeException {

    public CustomerNotFoundException(Long id) {
        super("Customer with id " + id + " was not found");
    }
}
~~~

~~~java
package com.example.customers.exception;

public class DuplicateCustomerEmailException extends RuntimeException {

    public DuplicateCustomerEmailException(String email) {
        super("Email is already registered: " + email);
    }
}
~~~

Service không nên tự tạo ResponseEntity hoặc biết HTTP status. Nó chỉ ném exception nghiệp vụ; controller advice sẽ chuyển exception thành HTTP response phù hợp.

## 9. Xây dựng CustomerService

Service là nơi tập trung transaction và quy tắc nghiệp vụ.

~~~java
package com.example.customers.service;

import com.example.customers.dto.*;
import com.example.customers.entity.Customer;
import com.example.customers.exception.*;
import com.example.customers.mapper.CustomerMapper;
import com.example.customers.repository.CustomerRepository;
import java.util.Locale;
import org.springframework.data.domain.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private static final int MAX_PAGE_SIZE = 100;

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public CustomerResponse create(CreateCustomerRequest request) {
        String email = normalizeEmail(request.email());

        if (repository.existsByEmailIgnoreCase(email)) {
            throw new DuplicateCustomerEmailException(email);
        }

        Customer customer = new Customer(
            request.fullName().trim(),
            email,
            normalizePhone(request.phone())
        );

        Customer saved = repository.saveAndFlush(customer);
        return CustomerMapper.toResponse(saved);
    }

    @Transactional(readOnly = true)
    public CustomerResponse getById(Long id) {
        Customer customer = repository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

        return CustomerMapper.toResponse(customer);
    }

    @Transactional(readOnly = true)
    public PageResponse<CustomerResponse> search(
            String query,
            int page,
            int size) {

        validatePage(page, size);

        Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.asc("fullName"),
                Sort.Order.asc("id")
            )
        );

        String term = query == null ? "" : query.trim();

        Page<Customer> customers;
        if (term.isEmpty()) {
            customers = repository.findAll(pageable);
        } else {
            customers =
                repository
                    .findByFullNameContainingIgnoreCaseOrEmailContainingIgnoreCase(
                        term,
                        term,
                        pageable
                    );
        }

        Page<CustomerResponse> responsePage =
            customers.map(CustomerMapper::toResponse);

        return PageResponse.from(responsePage);
    }

    @Transactional
    public CustomerResponse update(
            Long id,
            UpdateCustomerRequest request) {

        Customer customer = repository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

        String email = normalizeEmail(request.email());

        if (!customer.getEmail().equals(email)
                && repository.existsByEmailIgnoreCase(email)) {
            throw new DuplicateCustomerEmailException(email);
        }

        customer.updateProfile(
            request.fullName().trim(),
            email,
            normalizePhone(request.phone())
        );

        // Flush so @PreUpdate and @Version are reflected in the response.
        repository.flush();
        return CustomerMapper.toResponse(customer);
    }

    @Transactional
    public void delete(Long id) {
        Customer customer = repository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

        repository.delete(customer);
    }

    private static String normalizeEmail(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }

    private static String normalizePhone(String phone) {
        if (phone == null || phone.isBlank()) {
            return null;
        }
        return phone.trim();
    }

    private static void validatePage(int page, int size) {
        if (page < 0) {
            throw new IllegalArgumentException(
                "Page index must be zero or greater"
            );
        }

        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "Page size must be between 1 and " + MAX_PAGE_SIZE
            );
        }
    }
}
~~~

### Phân tích transaction

- create, update và delete dùng transaction ghi.
- getById và search dùng read-only transaction.
- Repository được inject qua constructor để dễ test và tránh field injection.
- Entity được tải trong transaction rồi thay đổi qua phương thức updateProfile.
- Không cần gọi save lại cho entity đã managed sau khi sửa thuộc tính; JPA dirty checking sẽ phát hiện thay đổi khi flush.
- saveAndFlush trong create buộc insert được gửi xuống database ngay trong method, giúp lấy ID và phát hiện constraint violation sớm hơn. Commit vẫn do transaction manager thực hiện.

### Kiểm tra email trùng và race condition

existsByEmailIgnoreCase giúp trả lỗi sớm, thân thiện với client. Nhưng hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra. Unique constraint của database bảo đảm dữ liệu cuối cùng không có email trùng.

Vì vậy, ứng dụng cần xử lý cả DuplicateCustomerEmailException và DataIntegrityViolationException. Không dựa vào existsByEmailIgnoreCase như một cơ chế khóa đồng thời.

### Phân trang ổn định

Service giới hạn size tối đa là 100 để tránh client yêu cầu tải hàng trăm nghìn bản ghi. Sort theo fullName rồi id để thứ tự có khóa phụ ổn định khi nhiều khách hàng có cùng tên.

Page thường yêu cầu thêm count query để tính totalElements và totalPages. Nếu màn hình không cần tổng số trang, có thể dùng Slice để tránh count query. Với dữ liệu rất lớn, cân nhắc keyset pagination thay vì offset sâu.

## 10. Tạo CustomerController

Controller định nghĩa HTTP contract và chuyển request cho service:

~~~java
package com.example.customers.controller;

import com.example.customers.dto.*;
import com.example.customers.service.CustomerService;
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {

        CustomerResponse created = service.create(request);

        URI location = ServletUriComponentsBuilder
            .fromCurrentRequest()
            .path("/{id}")
            .buildAndExpand(created.id())
            .toUri();

        return ResponseEntity.created(location).body(created);
    }

    @GetMapping("/{id}")
    public CustomerResponse getById(@PathVariable Long id) {
        return service.getById(id);
    }

    @GetMapping
    public PageResponse<CustomerResponse> search(
            @RequestParam(required = false) String q,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {

        return service.search(q, page, size);
    }

    @PutMapping("/{id}")
    public CustomerResponse update(
            @PathVariable Long id,
            @Valid @RequestBody UpdateCustomerRequest request) {

        return service.update(id, request);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Các endpoint:

| HTTP | URL | Chức năng | Thành công |
|---|---|---|---|
| POST | /api/customers | Tạo khách hàng | 201 Created |
| GET | /api/customers/{id} | Xem chi tiết | 200 OK |
| GET | /api/customers | Tìm kiếm/phân trang | 200 OK |
| PUT | /api/customers/{id} | Cập nhật đầy đủ trường cho phép | 200 OK |
| DELETE | /api/customers/{id} | Xóa khách hàng | 204 No Content |

POST trả Location header trỏ tới resource vừa tạo. DELETE trả 204 vì không có response body. Nếu ID không tồn tại, service ném CustomerNotFoundException và advice trả 404.

PUT trong ví dụ là thay thế đầy đủ các trường có thể chỉnh sửa. Nếu muốn cập nhật một phần, hãy thiết kế PATCH DTO và quy tắc rõ ràng cho ba trạng thái: field bị bỏ qua, field được gửi null và field có giá trị. Không dùng cùng một DTO PUT rồi âm thầm coi null là giữ nguyên vì client khó dự đoán hành vi.

## 11. Chuẩn hóa lỗi bằng @RestControllerAdvice

Định nghĩa cấu trúc lỗi:

~~~java
package com.example.customers.dto;

import java.time.Instant;
import java.util.Map;

public record ApiError(
    String code,
    String message,
    Map<String, String> fieldErrors,
    Instant timestamp
) {
}
~~~

Global exception handler:

~~~java
package com.example.customers.exception;

import com.example.customers.dto.ApiError;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.*;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(CustomerNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(
            CustomerNotFoundException exception) {

        return response(
            HttpStatus.NOT_FOUND,
            "CUSTOMER_NOT_FOUND",
            exception.getMessage(),
            Map.of()
        );
    }

    @ExceptionHandler(DuplicateCustomerEmailException.class)
    public ResponseEntity<ApiError> handleDuplicateEmail(
            DuplicateCustomerEmailException exception) {

        return response(
            HttpStatus.CONFLICT,
            "DUPLICATE_EMAIL",
            exception.getMessage(),
            Map.of()
        );
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException exception) {

        Map<String, String> errors =
            exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .collect(Collectors.toMap(
                    error -> error.getField(),
                    error -> error.getDefaultMessage() == null
                        ? "Invalid value"
                        : error.getDefaultMessage(),
                    (first, ignored) -> first,
                    LinkedHashMap::new
                ));

        return response(
            HttpStatus.BAD_REQUEST,
            "VALIDATION_FAILED",
            "Request validation failed",
            errors
        );
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ApiError> handleDataIntegrity(
            DataIntegrityViolationException exception) {

        return response(
            HttpStatus.CONFLICT,
            "DATA_CONSTRAINT_VIOLATION",
            "The request conflicts with an existing database constraint",
            Map.of()
        );
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> handleBadRequest(
            IllegalArgumentException exception) {

        return response(
            HttpStatus.BAD_REQUEST,
            "INVALID_ARGUMENT",
            exception.getMessage(),
            Map.of()
        );
    }

    private static ResponseEntity<ApiError> response(
            HttpStatus status,
            String code,
            String message,
            Map<String, String> fieldErrors) {

        ApiError body = new ApiError(
            code,
            message,
            fieldErrors,
            Instant.now()
        );

        return ResponseEntity.status(status).body(body);
    }
}
~~~

Trong ứng dụng production, nên ghi log exception database ở server với correlation ID, đồng thời không trả SQL, tên constraint nội bộ, stack trace hoặc dữ liệu nhạy cảm cho client.

Nếu dùng Spring MVC method validation trực tiếp trên parameter, tùy method signature và phiên bản Spring, có thể cần xử lý thêm HandlerMethodValidationException. Bài này kiểm tra các trường bên trong request DTO bằng @Valid nên tập trung vào MethodArgumentNotValidException.

## 12. Cấu hình database cho môi trường thực hành

Với H2 in-memory:

~~~properties
spring.application.name=customer-management

spring.datasource.url=jdbc:h2:mem:customers;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.driver-class-name=org.h2.Driver

# Chỉ dùng create-drop cho database demo/test tạm thời.
spring.jpa.hibernate.ddl-auto=create-drop

spring.jpa.open-in-view=false
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
~~~

create-drop giúp dựng schema khi ứng dụng khởi động và xóa khi SessionFactory đóng. Cấu hình này phù hợp cho demo hoặc test tạm, không dùng cho database cần giữ dữ liệu.

open-in-view=false đóng Open EntityManager in View. Controller phải làm việc với DTO đã được tạo trong transaction, tránh để việc serialize response kích hoạt lazy loading ngoài service.

### Cấu hình production

Với database dùng chung hoặc production, nên quản lý schema bằng Flyway hoặc Liquibase. Chạy migration có version rồi dùng:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
~~~

Validate kiểm tra mapping với schema có sẵn. Migration mới chịu trách nhiệm tạo bảng, cột, constraint và index. Không để Hibernate update và migration tool cùng thay đổi một schema.

## 13. Chạy ứng dụng và gọi API

Chạy ứng dụng bằng Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Tạo khách hàng:

~~~bash
curl -i -X POST http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  -d '{
    "fullName": "An Nguyen",
    "email": "an@example.com",
    "phone": "+84 900 123 456"
  }'
~~~

Response thành công có dạng:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/customers/1
Content-Type: application/json
~~~

~~~json
{
  "id": 1,
  "fullName": "An Nguyen",
  "email": "an@example.com",
  "phone": "+84 900 123 456",
  "createdAt": "2026-11-09T10:00:00Z",
  "updatedAt": "2026-11-09T10:00:00Z",
  "version": 0
}
~~~

Timestamp và ID trong response thực tế do database/ứng dụng tạo nên sẽ khác ví dụ minh họa.

Lấy khách hàng:

~~~bash
curl http://localhost:8080/api/customers/1
~~~

Tìm kiếm và phân trang:

~~~bash
curl "http://localhost:8080/api/customers?q=an&page=0&size=10"
~~~

Response phân trang có cấu trúc:

~~~json
{
  "content": [
    {
      "id": 1,
      "fullName": "An Nguyen",
      "email": "an@example.com",
      "phone": "+84 900 123 456",
      "createdAt": "2026-11-09T10:00:00Z",
      "updatedAt": "2026-11-09T10:00:00Z",
      "version": 0
    }
  ],
  "page": 0,
  "size": 10,
  "totalElements": 1,
  "totalPages": 1,
  "first": true,
  "last": true
}
~~~

Cập nhật khách hàng:

~~~bash
curl -i -X PUT http://localhost:8080/api/customers/1 \
  -H "Content-Type: application/json" \
  -d '{
    "fullName": "An Nguyen Updated",
    "email": "an@example.com",
    "phone": "+84 912 000 111"
  }'
~~~

Xóa khách hàng:

~~~bash
curl -i -X DELETE http://localhost:8080/api/customers/1
~~~

Kết quả xóa thành công là HTTP 204 No Content.

## 14. Ví dụ response khi validation thất bại

Gửi request thiếu tên và email sai định dạng:

~~~bash
curl -i -X POST http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  -d '{
    "fullName": " ",
    "email": "not-an-email",
    "phone": "123"
  }'
~~~

Response minh họa:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
~~~

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request validation failed",
  "fieldErrors": {
    "fullName": "Full name is required",
    "email": "Email format is invalid",
    "phone": "Phone must contain 7 to 20 valid characters"
  },
  "timestamp": "2026-11-09T10:00:00Z"
}
~~~

Danh sách fieldErrors chứa các trường vi phạm và thông báo tương ứng. Thời điểm timestamp là thời điểm server xử lý lỗi.

## 15. Kiểm thử API bằng MockMvc

Integration test kiểm tra nhiều thành phần cùng hoạt động: controller, validation, service, repository, Hibernate và database.

~~~java
package com.example.customers;

import com.example.customers.repository.CustomerRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerApiIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private CustomerRepository repository;

    @BeforeEach
    void cleanDatabase() {
        repository.deleteAllInBatch();
    }

    @Test
    void createReadUpdateAndDeleteCustomer() throws Exception {
        String createBody = """
            {
              "fullName": "An Nguyen",
              "email": "an@example.com",
              "phone": "+84 900 123 456"
            }
            """;

        MvcResult result = mockMvc.perform(
                post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(createBody)
            )
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andExpect(jsonPath("$.email").value("an@example.com"))
            .andReturn();

        JsonNode created = objectMapper.readTree(
            result.getResponse().getContentAsString()
        );
        long id = created.get("id").asLong();
        Instant createdAt = Instant.parse(created.get("createdAt").asText());
        long createdVersion = created.get("version").asLong();

        mockMvc.perform(get("/api/customers/{id}", id))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.fullName").value("An Nguyen"));

        // Ensure the lifecycle timestamp advances at the database precision.
        Thread.sleep(20L);

        String updateBody = """
            {
              "fullName": "An Nguyen Updated",
              "email": "an@example.com",
              "phone": "+84 912 000 111"
            }
            """;

        MvcResult updateResult = mockMvc.perform(
                put("/api/customers/{id}", id)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(updateBody)
            )
            .andExpect(status().isOk())
            .andExpect(
                jsonPath("$.fullName").value("An Nguyen Updated")
            )
            .andReturn();

        JsonNode updated = objectMapper.readTree(
            updateResult.getResponse().getContentAsString()
        );
        Instant updatedAt = Instant.parse(updated.get("updatedAt").asText());
        long updatedVersion = updated.get("version").asLong();

        assertTrue(
            updatedAt.isAfter(createdAt),
            "updatedAt should advance after the update"
        );
        assertTrue(
            updatedVersion > createdVersion,
            "version should increment after the update"
        );

        MvcResult persistedResult = mockMvc.perform(
                get("/api/customers/{id}", id)
            )
            .andExpect(status().isOk())
            .andReturn();

        JsonNode persisted = objectMapper.readTree(
            persistedResult.getResponse().getContentAsString()
        );
        Instant persistedUpdatedAt =
            Instant.parse(persisted.get("updatedAt").asText());

        assertTrue(
            persistedUpdatedAt.isAfter(createdAt),
            "updatedAt should be persisted after the update"
        );
        assertEquals(
            updatedVersion,
            persisted.get("version").asLong(),
            "the response version should match the persisted version"
        );

        mockMvc.perform(delete("/api/customers/{id}", id))
            .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/customers/{id}", id))
            .andExpect(status().isNotFound());
    }

    @Test
    void rejectsInvalidRequest() throws Exception {
        String invalidBody = """
            {
              "fullName": "",
              "email": "invalid-email",
              "phone": "123"
            }
            """;

        mockMvc.perform(
                post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(invalidBody)
            )
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.fieldErrors.fullName").exists())
            .andExpect(jsonPath("$.fieldErrors.email").exists());
    }

    @Test
    void rejectsDuplicateEmailIgnoringCase() throws Exception {
        String first = """
            {
              "fullName": "An Nguyen",
              "email": "an@example.com",
              "phone": null
            }
            """;

        String duplicate = """
            {
              "fullName": "Another Customer",
              "email": "AN@EXAMPLE.COM",
              "phone": null
            }
            """;

        mockMvc.perform(
                post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(first)
            )
            .andExpect(status().isCreated());

        mockMvc.perform(
                post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(duplicate)
            )
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("DUPLICATE_EMAIL"));
    }

    @Test
    void searchesAndReturnsPageMetadata() throws Exception {
        repository.saveAll(java.util.List.of(
            new com.example.customers.entity.Customer(
                "An Nguyen", "an@example.com", null
            ),
            new com.example.customers.entity.Customer(
                "Binh Tran", "binh@example.com", null
            ),
            new com.example.customers.entity.Customer(
                "An Le", "an.le@example.com", null
            )
        ));

        mockMvc.perform(
                get("/api/customers")
                    .param("q", "an")
                    .param("page", "0")
                    .param("size", "1")
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content.length()").value(1))
            .andExpect(jsonPath("$.page").value(0))
            .andExpect(jsonPath("$.size").value(1))
            .andExpect(jsonPath("$.totalElements").value(2))
            .andExpect(jsonPath("$.totalPages").value(2));
    }
}
~~~

Test search có thể khớp tên hoặc email chứa chuỗi tìm kiếm. Với dữ liệu mẫu, hai khách hàng có tên bắt đầu bằng An và email chứa an; truy vấn tìm kiếm không phân biệt hoa thường trả về hai kết quả.

Các test dùng database test riêng và xóa dữ liệu trước mỗi test. Không chạy test này trên database dùng chung hoặc production.

## 16. Kiểm thử repository và constraint

Ngoài MockMvc integration test, có thể dùng @DataJpaTest để kiểm tra repository độc lập:

- Derived query tìm đúng khách hàng theo tên/email.
- existsByEmailIgnoreCase hoạt động với chữ hoa/thường.
- Unique constraint từ chối email trùng.
- Pageable trả đúng content, totalElements và totalPages.
- Sort ổn định khi nhiều khách hàng có cùng fullName.
- @Version tăng khi entity được cập nhật.

@DataJpaTest thường cấu hình database nhúng và transaction rollback sau mỗi test. Nếu cần xác nhận DDL, collation, kiểu dữ liệu hoặc hành vi constraint theo production engine, dùng Testcontainers với cùng loại database.

Không chỉ dựa vào H2 để kết luận migration hoặc SQL sẽ chạy giống PostgreSQL/MySQL/SQL Server. Các database khác nhau về collation, kiểu dữ liệu, unique index, identity, locking và transaction behavior.

## 17. DTO validation khác business validation

Bean Validation kiểm tra hình dạng dữ liệu đầu vào:

- fullName không rỗng.
- email đúng định dạng và giới hạn độ dài.
- phone tuân theo quy tắc chuỗi.

Business validation kiểm tra quy tắc phụ thuộc trạng thái hệ thống:

- Email chưa được khách hàng khác sử dụng.
- Khách hàng đang tồn tại trước khi cập nhật/xóa.
- Khách hàng có thể bị xóa theo chính sách nghiệp vụ.
- Người dùng hiện tại có quyền sửa khách hàng đó.
- Trạng thái khách hàng cho phép thực hiện thao tác.

Không cố nhồi mọi business rule vào annotation trên DTO. Những quy tắc cần truy cập database, security context hoặc nhiều entity nên được thực hiện trong service/domain layer.

Nếu một quy tắc phải luôn đúng bất kể API nào ghi dữ liệu, hãy bảo vệ nó ở database bằng unique, foreign key, check constraint hoặc cơ chế phù hợp, đồng thời kiểm tra lại trong service để trả lỗi thân thiện.

## 18. Xử lý đồng thời và optimistic locking

Entity có @Version. Khi Hibernate cập nhật entity, câu SQL thường kiểm tra version hiện tại và tăng version. Nếu transaction khác đã cập nhật cùng bản ghi trước đó, update có thể ảnh hưởng 0 dòng và JPA báo optimistic locking failure.

Điều này tránh việc hai người cùng sửa một khách hàng rồi âm thầm ghi đè dữ liệu của nhau.

Có thể bổ sung handler cho lỗi này:

~~~java
@ExceptionHandler(
    org.springframework.orm.ObjectOptimisticLockingFailureException.class
)
public ResponseEntity<ApiError> handleOptimisticLock(
        org.springframework.orm.ObjectOptimisticLockingFailureException exception) {

    return response(
        HttpStatus.CONFLICT,
        "CONCURRENT_MODIFICATION",
        "Customer was changed by another request. Reload and retry.",
        Map.of()
    );
}
~~~

Đặt method này trong GlobalExceptionHandler cùng các handler đã khai báo. HTTP 409 cho biết client cần tải dữ liệu mới và quyết định có áp dụng lại thay đổi hay không.

Nếu muốn API hỗ trợ optimistic concurrency rõ ràng ở HTTP layer, có thể trả version trong response và nhận If-Match/ETag ở request. Khi đó cần định nghĩa semantics version, xử lý 412 Precondition Failed và bảo đảm version được kiểm tra trong transaction. Bài thực hành hiện trả version trong DTO để người học có thể mở rộng.

## 19. Bảo mật và giới hạn API

CRUD customer thường chứa thông tin cá nhân. Trước khi đưa API vào môi trường thật, cần bổ sung:

- Spring Security và authentication/authorization.
- Quyền truy cập theo tenant/owner, không chỉ theo ID.
- HTTPS và quản lý secret ngoài source code.
- Rate limit hoặc quota cho API public.
- Giới hạn page size và kiểm soát query tìm kiếm.
- Audit log cho thao tác tạo, sửa, xóa.
- Không log email, số điện thoại hoặc request body nhạy cảm nếu không cần.
- Chính sách lưu giữ, xóa và xuất dữ liệu theo yêu cầu nghiệp vụ.
- Backup, migration và giám sát database.

Không dùng ID ngẫu nhiên hoặc khó đoán như một cơ chế phân quyền. Mọi thao tác get/update/delete vẫn cần kiểm tra user hiện tại có quyền truy cập resource hay không.

Với tìm kiếm, nên có giới hạn độ dài q, index phù hợp và kế hoạch query khi dữ liệu lớn. Tìm chuỗi con với wildcard ở đầu có thể không tận dụng được B-tree index thông thường. Cần xem execution plan và cân nhắc full-text search nếu nghiệp vụ cần.

## 20. Các lỗi thường gặp

### 20.1. Trả entity trực tiếp từ controller

Có thể lộ trường nội bộ, kéo theo lazy-loading, vòng lặp JSON ở quan hệ hai chiều hoặc làm API phụ thuộc cấu trúc database. Dùng response DTO.

### 20.2. Quên @Valid trên request body

Annotation validation trong DTO sẽ không tự chạy ở controller nếu không kích hoạt validation cho request. Dùng @Valid cùng dependency starter validation.

### 20.3. Chỉ kiểm tra email trùng ở service

Hai request đồng thời có thể cùng vượt qua existsByEmailIgnoreCase. Thêm unique constraint ở database và xử lý DataIntegrityViolationException.

### 20.4. Dùng DTO create cho cả update mà không định nghĩa semantics

PUT thường thay thế đầy đủ các trường cho phép cập nhật; PATCH cập nhật một phần. Hãy phân biệt request DTO và cách xử lý null/field bị bỏ qua.

### 20.5. Cho phép client gửi ID, version hoặc timestamp

Client có thể cố sửa trường nội bộ hoặc trường quản lý bởi database. Request DTO chỉ chứa trường được phép chỉnh sửa.

### 20.6. Trả Page entity trực tiếp

API có thể phụ thuộc implementation serialization của Spring Data và vô tình trả entity. Map sang PageResponse chứa DTO.

### 20.7. Phân trang không có sort ổn định

Nếu sort không duy nhất, bản ghi có thể đổi vị trí giữa các trang. Thêm khóa phụ như id vào thứ tự sắp xếp.

### 20.8. Không giới hạn page size

Client có thể yêu cầu tải quá nhiều dữ liệu, làm tăng bộ nhớ, thời gian SQL và response size. Đặt page size mặc định và giới hạn tối đa.

### 20.9. Gọi save cho mọi thay đổi entity managed

JPA dirty checking đã phát hiện thay đổi của entity managed trong transaction. Gọi save lại không cần thiết trong trường hợp này, dù không nhất thiết gây lỗi.

### 20.10. Bật Open EntityManager in View để che lỗi lazy loading

Việc serialize entity sau service transaction có thể phát sinh query ngoài ý muốn. Dùng DTO được tạo trong transaction và cân nhắc open-in-view=false.

### 20.11. Dùng create-drop trên production

Schema có thể bị xóa khi ứng dụng kết thúc. Dùng migration có version và ddl-auto=validate hoặc none.

### 20.12. Trả lỗi database thô cho client

SQL, stack trace và tên constraint có thể tiết lộ cấu trúc nội bộ. Trả error code và thông báo phù hợp; ghi chi tiết ở log server đã bảo vệ.

## 21. Quy trình triển khai bài thực hành

Thực hiện theo thứ tự:

1. Tạo Spring Boot project với Web, Data JPA, Validation và H2.
2. Tạo Customer entity với unique email constraint và @Version.
3. Tạo CreateCustomerRequest và UpdateCustomerRequest với Bean Validation.
4. Tạo CustomerResponse và PageResponse.
5. Viết CustomerMapper.
6. Tạo CustomerRepository với existsByEmailIgnoreCase và derived search query.
7. Viết exception nghiệp vụ cho not found và duplicate email.
8. Viết CustomerService với transaction boundary, normalize email và pagination.
9. Viết CustomerController với POST, GET, PUT và DELETE.
10. Viết GlobalExceptionHandler cho validation và business errors.
11. Cấu hình H2 và open-in-view=false.
12. Chạy ứng dụng, gọi API bằng curl hoặc Postman.
13. Viết MockMvc integration tests cho CRUD, validation, duplicate email và pagination.
14. Chạy test trên database gần production trước khi triển khai.

## 22. Ghi nhớ

- Entity mô tả trạng thái persistence; DTO mô tả dữ liệu API nhận và trả.
- Request DTO giúp giới hạn trường client được phép gửi và giảm nguy cơ mass assignment.
- @Valid kích hoạt Jakarta Bean Validation trên request object.
- @NotBlank phù hợp với chuỗi bắt buộc; @Email kiểm tra hình dạng email chứ không xác minh quyền sở hữu.
- Service chứa business rules và transaction boundary.
- JpaRepository cung cấp CRUD, derived query và Pageable.
- Mapper chuyển entity sang response DTO, tránh serialize entity trực tiếp.
- Unique constraint database là điều kiện bắt buộc để bảo đảm email không trùng khi có request đồng thời.
- @Version hỗ trợ optimistic locking và phát hiện cập nhật cạnh tranh.
- PageResponse giúp API kiểm soát cấu trúc phân trang.
- @RestControllerAdvice chuẩn hóa lỗi 400, 404 và 409.
- Phân trang cần giới hạn size và sort ổn định.
- open-in-view=false khuyến khích hoàn tất mapping DTO trong transaction.
- Dùng integration test để xác minh controller, validation, service, repository và database phối hợp đúng.
- Với production, dùng Flyway/Liquibase, security, audit, backup và database engine phù hợp.

Bài thực hành hoàn chỉnh cho thấy cách các lớp trong Spring Data JPA phối hợp để tạo một CRUD API có kiểm tra dữ liệu, DTO rõ ràng, transaction và xử lý lỗi nhất quán. Khi mở rộng sang dự án thật, hãy bổ sung authorization, migration có version, concurrency contract và observability theo yêu cầu nghiệp vụ.

## Tài liệu tham khảo

- [Spring Data JPA — JPA Repositories](https://docs.spring.io/spring-data/jpa/reference/jpa.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)