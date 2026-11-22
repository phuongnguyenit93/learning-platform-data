# QuerydslPredicateExecutor cho tìm kiếm, đếm và tồn tại

## Mục tiêu

Querydsl cho phép mô tả điều kiện truy vấn bằng Java expression có kiểu (type-safe), thay vì ghép chuỗi JPQL hoặc SQL. Spring Data JPA tích hợp Querydsl thông qua `QuerydslPredicateExecutor<T>`, giúp repository nhận một Predicate rồi thực hiện tìm kiếm, phân trang, đếm hoặc kiểm tra sự tồn tại của dữ liệu.

Cách tiếp cận này phù hợp khi ứng dụng có nhiều bộ lọc tùy chọn và muốn kết hợp chúng theo điều kiện AND/OR. Các lớp Q được tạo tự động từ entity giúp IDE hỗ trợ autocomplete và phát hiện lỗi tên thuộc tính ngay khi biên dịch.

Sau bài này, bạn có thể:

- Hiểu vai trò của Querydsl và các lớp Q được sinh từ entity.
- Cấu hình Querydsl tương thích Jakarta Persistence.
- Cho repository kế thừa `QuerydslPredicateExecutor`.
- Tạo predicate bằng Q-type, `BooleanExpression` và `BooleanBuilder`.
- Dùng `findAll`, `findOne`, `count` và `exists`.
- Kết hợp predicate với `Sort` và `Pageable`.
- Giới hạn các field được phép bind từ HTTP request.
- Nhận biết giới hạn của executor và khi nào cần custom repository với `JPAQueryFactory`.
- Kiểm thử kết quả truy vấn trên JPA provider thực tế.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA. Ví dụ cấu hình Querydsl cần được căn chỉnh theo phiên bản Spring Data/Querydsl của dự án.

## 1. Querydsl và Predicate

Querydsl là thư viện xây dựng query bằng Java API có kiểu. Thay vì viết một chuỗi query:

```java
String jpql =
        "select c from Customer c where c.active = true";
```

ta có thể biểu diễn điều kiện bằng Java expression:

```java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.active.isTrue();
```

`Predicate` mô tả điều kiện logic có thể được chuyển thành WHERE clause. Các phép so sánh, nối chuỗi, kiểm tra null, tập hợp và điều kiện ngày tháng được biểu diễn bằng các method có kiểu phù hợp.

Ví dụ:

```java
customer.firstName.eq("An");
customer.email.containsIgnoreCase("@example.com");
customer.age.goe(18);
customer.createdAt.before(Instant.now());
customer.department.name.eq("Engineering");
```

Các biểu thức này không thực thi query ngay. Chúng mô tả điều kiện; repository hoặc Querydsl query factory sẽ thực thi chúng trên database.

### 1.1. Q-type được sinh tự động

Với entity `Customer`, Querydsl annotation processor tạo class `QCustomer`. Class này có các path tương ứng với thuộc tính entity:

- `customer.id`: path cho ID.
- `customer.firstName`: StringPath.
- `customer.email`: StringPath.
- `customer.active`: BooleanPath.
- `customer.createdAt`: DateTimePath hoặc path thời gian tương ứng.
- Association cũng có path phù hợp với kiểu entity liên quan.

Q-type thường nằm trong cùng package với entity. Không tự viết hoặc chỉnh sửa các class Q được sinh; chúng là output của annotation processing và sẽ được tạo lại khi build.

## 2. Cấu hình Querydsl cho Jakarta Persistence

Spring Boot 3.x dùng Jakarta Persistence, vì vậy dependency Querydsl phải tương thích Jakarta. Một cấu hình Maven thường dùng với Querydsl 5.1.x:

```xml
<properties>
    <querydsl.version>5.1.0</querydsl.version>
</properties>

<dependencies>
    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>5.1.0</version>
        <classifier>jakarta</classifier>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>5.1.0</version>
                        <classifier>jakarta</classifier>
                    </path>
                    <path>
                        <groupId>jakarta.persistence</groupId>
                        <artifactId>jakarta.persistence-api</artifactId>
                        <version>3.1.0</version>
                    </path>
                    <path>
                        <groupId>jakarta.annotation</groupId>
                        <artifactId>jakarta.annotation-api</artifactId>
                        <version>2.1.1</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Các version trên là ví dụ cho stack Jakarta; hãy dùng version tương thích với Spring Boot/Spring Data đang quản lý trong dự án. Nếu dự án dùng Spring Boot 2.x với `javax.persistence`, cần dependency và annotation processor thuộc dòng tương thích javax, không dùng classifier Jakarta.

Với Gradle, cấu hình tương ứng thường đặt thư viện runtime trong `implementation` và annotation processor trong `annotationProcessor`:

```groovy
dependencies {
    implementation "com.querydsl:querydsl-jpa:5.1.0:jakarta"

    annotationProcessor "com.querydsl:querydsl-apt:5.1.0:jakarta"
    annotationProcessor "jakarta.persistence:jakarta.persistence-api:3.1.0"
    annotationProcessor "jakarta.annotation:jakarta.annotation-api:2.1.1"
}
```

### 2.1. Sinh Q-class

Sau khi cấu hình annotation processor, chạy build:

```bash
./mvnw clean compile
```

Trên Windows:

```powershell
.mvnw.cmd clean compile
```

Q-class được tạo trong thư mục generated sources của build, thường là:

```text
target/generated-sources/annotations/
```

Ví dụ entity trong package `com.example.demo.customer` sẽ tạo `QCustomer` trong package tương ứng. IDE có thể cần reload Maven/Gradle hoặc đánh dấu generated sources để nhận diện class vừa sinh.

Nếu Q-class không được tạo, kiểm tra annotation processor, classifier Jakarta/Javax, import `jakarta.persistence.Entity`, compiler configuration và output của clean compile. Không tạo một class Q thủ công để che lỗi cấu hình.

## 3. Entity và repository mẫu

Entity Customer:

```java
package com.example.demo.customer;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String firstName;

    @Column(nullable = false, length = 100)
    private String lastName;

    @Column(nullable = false, unique = true, length = 320)
    private String email;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false)
    private Instant createdAt;

    protected Customer() {
    }

    public Customer(
            String firstName,
            String lastName,
            String email,
            boolean active,
            Instant createdAt
    ) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.email = email;
        this.active = active;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Sau khi build, Querydsl tạo class tương đương về mặt khái niệm:

```java
// Generated source - không tự viết hoặc chỉnh sửa.
public class QCustomer extends EntityPathBase<Customer> {
    public static final QCustomer customer =
            new QCustomer("customer");

    public final StringPath firstName = createString("firstName");
    public final StringPath lastName = createString("lastName");
    public final StringPath email = createString("email");
    public final BooleanPath active = createBoolean("active");
}
```

Đoạn Q-class trên chỉ minh họa cấu trúc, không phải file cần thêm vào source code. Annotation processor sẽ sinh class đầy đủ dựa trên mapping thật của entity.

Repository:

```java
package com.example.demo.customer;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
```

Chỉ cần kế thừa `QuerydslPredicateExecutor<Customer>`, repository có thể nhận Querydsl Predicate mà không phải viết một method riêng cho từng tổ hợp filter.

## 4. Các method của QuerydslPredicateExecutor

Các thao tác chính:

| Method | Kết quả | Mục đích |
|---|---|---|
| `findAll(predicate)` | `Iterable<T>` | Lấy mọi entity khớp predicate |
| `findAll(predicate, sort)` | `Iterable<T>` | Lấy kết quả theo thứ tự |
| `findAll(predicate, pageable)` | `Page<T>` | Lấy một trang và metadata phân trang |
| `findOne(predicate)` | `Optional<T>` | Lấy một kết quả nếu predicate khớp |
| `count(predicate)` | `long` | Đếm số entity khớp |
| `exists(predicate)` | `boolean` | Kiểm tra có entity khớp hay không |

Các method nhận `Predicate` từ `com.querydsl.core.types.Predicate`.

Ví dụ kiểm tra email:

```java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.email.eq("an@example.com");

Optional<Customer> result = repository.findOne(predicate);
```

`findOne` không có nghĩa là tự chọn ngẫu nhiên một hàng đầu tiên. Predicate nên xác định tối đa một kết quả. Nếu có nhiều hàng khớp, Spring Data có thể ném `IncorrectResultSizeDataAccessException`. Với truy vấn có nhiều kết quả, dùng `findAll` hoặc Page.

## 5. Tạo Predicate trực tiếp từ Q-type

Q-type có các method phù hợp với kiểu thuộc tính.

### 5.1. So sánh chính xác

```java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.active.isTrue()
        .and(customer.lastName.eq("Nguyen"));
```

Các method thường dùng:

- `eq(value)`: bằng.
- `ne(value)`: khác.
- `isNull()` và `isNotNull()`: kiểm tra null.
- `isTrue()` và `isFalse()`: boolean.
- `in(collection)`: thuộc một tập giá trị.
- `notIn(collection)`: không thuộc tập giá trị.

### 5.2. Tìm chuỗi

```java
Predicate predicate = customer.firstName.containsIgnoreCase("an")
        .and(customer.email.endsWithIgnoreCase("@example.com"));
```

Một số method String thường gặp:

| Method | Ý nghĩa |
|---|---|
| `eq` | So khớp chính xác |
| `contains` | Chứa chuỗi |
| `containsIgnoreCase` | Chứa chuỗi, bỏ qua hoa/thường |
| `startsWith` | Bắt đầu bằng |
| `endsWith` | Kết thúc bằng |
| `like` | So khớp LIKE |
| `matches` | Biểu thức regex tùy khả năng backend/provider |

Hành vi regex hoặc các hàm đặc thù không phải lúc nào cũng portable giữa database. Ưu tiên các biểu thức được Querydsl JPA và provider hỗ trợ; kiểm thử trên database thực tế.

### 5.3. So sánh ngày và số

Với thuộc tính có thứ tự:

```java
Instant from = Instant.parse("2026-01-01T00:00:00Z");
Instant to = Instant.parse("2026-02-01T00:00:00Z");

Predicate predicate = customer.createdAt.goe(from)
        .and(customer.createdAt.lt(to));
```

Các method phổ biến gồm `gt`, `goe`, `lt` và `loe`. Có thể dùng khoảng nửa mở `[from, to)`: bao gồm đầu khoảng, loại trừ cuối khoảng để tránh trùng ranh giới giữa hai kỳ liên tiếp.

## 6. Kết hợp filter tùy chọn bằng BooleanBuilder

Form tìm kiếm thường có nhiều trường không bắt buộc. `BooleanBuilder` cho phép thêm predicate khi có input tương ứng.

DTO tìm kiếm:

```java
public record CustomerSearchForm(
        String name,
        String email,
        Boolean active,
        Instant createdFrom,
        Instant createdTo
) {
}
```

Tạo predicate:

```java
import com.querydsl.core.BooleanBuilder;

public Predicate buildPredicate(CustomerSearchForm form) {
    QCustomer customer = QCustomer.customer;
    BooleanBuilder builder = new BooleanBuilder();

    if (form.name() != null && !form.name().isBlank()) {
        builder.and(
                customer.firstName.containsIgnoreCase(
                        form.name().trim()
                ).or(
                        customer.lastName.containsIgnoreCase(
                                form.name().trim()
                        )
                )
        );
    }

    if (form.email() != null && !form.email().isBlank()) {
        builder.and(
                customer.email.eq(form.email().trim())
        );
    }

    if (form.active() != null) {
        builder.and(customer.active.eq(form.active()));
    }

    if (form.createdFrom() != null) {
        builder.and(customer.createdAt.goe(form.createdFrom()));
    }

    if (form.createdTo() != null) {
        builder.and(customer.createdAt.lt(form.createdTo()));
    }

    if (!builder.hasValue()) {
        throw new IllegalArgumentException(
                "At least one search criterion is required"
        );
    }

    return builder;
}
```

`BooleanBuilder` là mutable: mỗi lần gọi method `and` hoặc `or` sẽ cập nhật builder. Tạo builder mới cho từng request hoặc lần tìm kiếm; không giữ một builder dùng chung ở field static hay singleton service vì các request có thể làm lẫn điều kiện của nhau.

Nếu form cho phép tìm kiếm không điều kiện, hãy xử lý trường hợp builder rỗng một cách rõ ràng, ví dụ gọi một query giới hạn riêng hoặc trả lỗi/validation theo yêu cầu sản phẩm. Không vô tình chạy toàn bộ bảng chỉ vì người dùng gửi form rỗng.

### 6.1. AND và OR

`and` thu hẹp tập kết quả; `or` mở rộng tập kết quả. Nhóm logic phải được đặt đúng:

```java
BooleanBuilder builder = new BooleanBuilder();

builder.and(customer.active.isTrue());

BooleanExpression nameMatches =
        customer.firstName.containsIgnoreCase("an")
                .or(customer.lastName.containsIgnoreCase("an"));

builder.and(nameMatches);
```

Logic tương đương:

```sql
WHERE active = true
  AND (
      lower(first_name) LIKE '%an%'
      OR lower(last_name) LIKE '%an%'
  )
```

Tách nhóm OR thành một expression trước khi AND vào builder giúp giữ đúng ngoặc nghiệp vụ.

## 7. Tạo các Predicate có thể tái sử dụng

Với điều kiện được dùng ở nhiều nơi, có thể tách thành các hàm trả về `BooleanExpression`:

```java
public final class CustomerPredicates {

    private static final QCustomer CUSTOMER = QCustomer.customer;

    private CustomerPredicates() {
    }

    public static BooleanExpression isActive(Boolean active) {
        return active == null
                ? null
                : CUSTOMER.active.eq(active);
    }

    public static BooleanExpression nameContains(String name) {
        if (name == null || name.isBlank()) {
            return null;
        }

        return CUSTOMER.firstName.containsIgnoreCase(name.trim())
                .or(CUSTOMER.lastName.containsIgnoreCase(name.trim()));
    }

    public static BooleanExpression emailEquals(String email) {
        if (email == null || email.isBlank()) {
            return null;
        }

        return CUSTOMER.email.eq(email.trim());
    }
}
```

Ghép các expression có thể null:

```java
BooleanBuilder builder = new BooleanBuilder();

BooleanExpression active = CustomerPredicates.isActive(form.active());
BooleanExpression name = CustomerPredicates.nameContains(form.name());
BooleanExpression email = CustomerPredicates.emailEquals(form.email());

if (active != null) {
    builder.and(active);
}
if (name != null) {
    builder.and(name);
}
if (email != null) {
    builder.and(email);
}
```

Không gọi `builder.and(null)` một cách tùy tiện. Kiểm tra null trước khi thêm expression để thể hiện rõ filter nào đang được áp dụng.

Một predicate factory nên không giữ state và chỉ mô tả điều kiện. Validation của form, quyền truy cập, tenant và giới hạn số lượng kết quả nên được kiểm soát ở tầng service.

## 8. Tìm kiếm, đếm và kiểm tra tồn tại

Sau khi có Predicate, có thể dùng cùng điều kiện cho nhiều thao tác.

```java
Predicate predicate = buildPredicate(form);

Iterable<Customer> customers = repository.findAll(predicate);

long total = repository.count(predicate);

boolean hasMatch = repository.exists(predicate);
```

Các thao tác có thể phục vụ các use case khác nhau:

- Danh sách kết quả: `findAll(predicate)` hoặc overload có Pageable.
- Hiển thị số kết quả: `count(predicate)`.
- Kiểm tra email hoặc mã đã tồn tại: `exists(predicate)`.
- Lấy một entity theo điều kiện duy nhất: `findOne(predicate)`.

Ví dụ kiểm tra email:

```java
public boolean emailExists(String email) {
    if (email == null || email.isBlank()) {
        throw new IllegalArgumentException("Email is required");
    }

    QCustomer customer = QCustomer.customer;
    return repository.exists(customer.email.equalsIgnoreCase(email.trim()));
}
```

Nếu email cần so sánh chính xác theo quy tắc của hệ thống, hãy dùng cùng semantics với unique constraint và collation của database. Query exists hỗ trợ kiểm tra trước, nhưng không thay thế unique constraint vì hai transaction đồng thời vẫn có thể cùng kiểm tra “chưa tồn tại” rồi cùng INSERT.

## 9. Kết hợp Predicate với Sort và Pageable

Repository hỗ trợ truyền Sort:

```java
Iterable<Customer> result = repository.findAll(
        predicate,
        Sort.by(
                Sort.Order.asc("lastName"),
                Sort.Order.asc("firstName"),
                Sort.Order.asc("id")
        )
);
```

Sort dùng property Java của entity. Khi có nhiều hàng cùng tên, thêm ID làm tie-breaker để thứ tự xác định hơn.

Với phân trang:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("lastName"),
                Sort.Order.asc("id")
        )
);

Page<Customer> page = repository.findAll(predicate, pageable);

List<Customer> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

`Page` thường cần count query để xác định tổng số phần tử. Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, cân nhắc `Slice` trong một query custom phù hợp hoặc dùng cơ chế scrolling. `QuerydslPredicateExecutor.findAll(predicate, pageable)` trả về Page.

Kiểm soát page size ở service/controller; không cho client yêu cầu một page khổng lồ. Với dữ liệu lớn, OFFSET sâu có thể tốn chi phí; cân nhắc keyset/scrolling hoặc custom query phù hợp với version Spring Data.

## 10. Dùng QuerydslPredicateExecutor trong service

Service có thể chịu trách nhiệm tạo predicate, validate input và áp dụng phân trang:

```java
@Service
@Transactional(readOnly = true)
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Page<Customer> search(
            CustomerSearchForm form,
            Pageable pageable
    ) {
        if (pageable.getPageSize() > 100) {
            throw new IllegalArgumentException("Page size must not exceed 100");
        }

        if (form.createdFrom() != null
                && form.createdTo() != null
                && !form.createdFrom().isBefore(form.createdTo())) {
            throw new IllegalArgumentException(
                    "createdFrom must be earlier than createdTo"
            );
        }

        Predicate predicate = buildPredicate(form);
        return repository.findAll(predicate, pageable);
    }

    private Predicate buildPredicate(CustomerSearchForm form) {
        QCustomer customer = QCustomer.customer;
        BooleanBuilder builder = new BooleanBuilder();

        if (form.name() != null && !form.name().isBlank()) {
            String name = form.name().trim();
            builder.and(
                    customer.firstName.containsIgnoreCase(name)
                            .or(customer.lastName.containsIgnoreCase(name))
            );
        }

        if (form.email() != null && !form.email().isBlank()) {
            builder.and(customer.email.equalsIgnoreCase(form.email().trim()));
        }

        if (form.active() != null) {
            builder.and(customer.active.eq(form.active()));
        }

        if (form.createdFrom() != null) {
            builder.and(customer.createdAt.goe(form.createdFrom()));
        }

        if (form.createdTo() != null) {
            builder.and(customer.createdAt.lt(form.createdTo()));
        }

        if (!builder.hasValue()) {
            throw new IllegalArgumentException(
                    "At least one search criterion is required"
            );
        }

        return builder;
    }
}
```

Ví dụ này dùng `Boolean` trong form để phân biệt “không chọn trạng thái” với `false`. Nếu dùng primitive boolean, giá trị mặc định false có thể vô tình trở thành filter.

Service còn xác thực khoảng ngày và giới hạn page size. Trong ứng dụng thực tế, có thể chuyển validation sang Bean Validation hoặc một lớp validator riêng.

## 11. Bind Predicate từ HTTP request

Spring Data Web có thể tạo Querydsl Predicate từ query parameters. Ví dụ controller:

```java
@GetMapping("/customers")
public Page<Customer> search(
        @QuerydslPredicate(root = Customer.class) Predicate predicate,
        @PageableDefault(size = 20) Pageable pageable
) {
    return repository.findAll(predicate, pageable);
}
```

`@QuerydslPredicate` yêu cầu Spring Data tạo predicate từ các request parameters theo binding rules. Tùy cấu hình ứng dụng, cần bật Spring Data web support bằng `@EnableSpringDataWebSupport` hoặc bảo đảm cấu hình auto-configuration tương ứng đang hoạt động.

Ví dụ request:

```http
GET /customers?firstName=An&active=true&page=0&size=20
```

Cách bind mặc định có thể làm lộ nhiều thuộc tính entity hơn mong muốn. Không nên để mọi property có thể được filter chỉ vì Q-type có path tương ứng.

### 11.1. Giới hạn field được phép bằng QuerydslBinderCustomizer

Repository có thể tùy chỉnh binding:

```java
import com.querydsl.core.types.dsl.StringExpression;
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer>,
                QuerydslBinderCustomizer<QCustomer> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QCustomer customer
    ) {
        bindings.excludeUnlistedProperties(true);

        bindings.including(
                customer.firstName,
                customer.lastName,
                customer.active
        );

        bindings.bind(customer.firstName)
                .first((path, value) -> path.containsIgnoreCase(value));

        bindings.bind(customer.lastName)
                .first((path, value) -> path.containsIgnoreCase(value));
    }
}
```

Cấu hình này chỉ cho phép bind các thuộc tính được liệt kê. Hai trường tên dùng containsIgnoreCase; active giữ cách bind boolean mặc định.

Không đưa các thuộc tính như tenantId, role, internalStatus, salary hoặc dữ liệu nhạy cảm vào binding chỉ vì chúng có trong entity. Nếu query bắt buộc phải giới hạn theo tenant/người dùng, hãy thêm điều kiện đó từ security context ở server; không nhận tenant scope từ client.

Nếu repository đã kế thừa QuerydslBinderCustomizer, không cần khai báo lại phần extends của repository ở hai nơi; ghép các interface vào cùng một khai báo như ví dụ.

### 11.2. Không trả entity trực tiếp nếu API chỉ cần một phần dữ liệu

Ví dụ controller thực tế thường nên map kết quả sang DTO để kiểm soát response:

```java
public record CustomerSummary(
        Long id,
        String firstName,
        String lastName,
        String email
) {
    static CustomerSummary from(Customer customer) {
        return new CustomerSummary(
                customer.getId(),
                customer.getFirstName(),
                customer.getLastName(),
                customer.getEmail()
        );
    }
}
```

```java
@GetMapping("/customers")
public Page<CustomerSummary> search(
        @QuerydslPredicate(root = Customer.class) Predicate predicate,
        @PageableDefault(size = 20) Pageable pageable
) {
    return repository.findAll(predicate, pageable)
            .map(CustomerSummary::from);
}
```

DTO kiểm soát dữ liệu công khai; authorization vẫn phải được kiểm tra riêng.

## 12. Kiểm thử QuerydslPredicateExecutor

Dùng `@DataJpaTest` để xác nhận predicate được thực thi bởi repository và JPA provider.

```java
package com.example.demo.customer;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import com.querydsl.core.BooleanBuilder;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @BeforeEach
    void setUp() {
        repository.saveAllAndFlush(List.of(
                new Customer(
                        "An", "Nguyen", "an@example.com", true,
                        Instant.parse("2026-01-10T00:00:00Z")
                ),
                new Customer(
                        "Binh", "Tran", "binh@example.com", true,
                        Instant.parse("2026-01-11T00:00:00Z")
                ),
                new Customer(
                        "Chi", "Le", "chi@example.com", false,
                        Instant.parse("2026-01-12T00:00:00Z")
                )
        ));
    }

    @Test
    void findsCustomersByComposedPredicate() {
        QCustomer customer = QCustomer.customer;

        BooleanBuilder predicate = new BooleanBuilder();
        predicate.and(customer.active.isTrue());
        predicate.and(customer.firstName.containsIgnoreCase("an"));

        Iterable<Customer> result = repository.findAll(predicate);

        assertThat(result)
                .extracting(Customer::getEmail)
                .containsExactly("an@example.com");
    }

    @Test
    void countsAndChecksExistence() {
        QCustomer customer = QCustomer.customer;
        var predicate = customer.active.isTrue();

        assertThat(repository.count(predicate)).isEqualTo(2);
        assertThat(repository.exists(
                customer.email.eq("an@example.com")
        )).isTrue();
    }

    @Test
    void findsOneWhenPredicateIsUnique() {
        QCustomer customer = QCustomer.customer;

        var result = repository.findOne(
                customer.email.eq("binh@example.com")
        );

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getLastName()).isEqualTo("Tran");
    }

    @Test
    void appliesPageAndSort() {
        QCustomer customer = QCustomer.customer;

        Page<Customer> page = repository.findAll(
                customer.active.isTrue(),
                PageRequest.of(
                        0,
                        1,
                        Sort.by(Sort.Direction.ASC, "lastName")
                                .and(Sort.by("id"))
                )
        );

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }
}
```

Ví dụ giả định QCustomer đã được sinh bởi annotation processor, repository và entity nằm đúng package, cùng các dependency JUnit 5, AssertJ và Spring Boot JPA test support. `@DataJpaTest` thường chạy trong transaction và rollback sau mỗi test.

Test này kiểm tra bốn hành vi khác nhau: kết hợp predicate, count/exists, findOne với điều kiện duy nhất và Page có count/sort. Đây là kiểm tra hành vi repository; nó không chứng minh query có index tối ưu hoặc chạy nhanh trên dữ liệu production.

## 13. QuerydslPredicateExecutor có giới hạn gì?

`QuerydslPredicateExecutor` là abstraction tiện cho các thao tác CRUD đọc phổ biến dựa trên Predicate. Nó không phải API đầy đủ để điều khiển mọi phần của một query.

Những trường hợp nên cân nhắc custom repository với `JPAQueryFactory`:

- Cần DTO projection phức tạp hoặc chọn nhiều biểu thức.
- Cần JOIN FETCH để kiểm soát tải association.
- Cần GROUP BY, HAVING hoặc aggregate đặc thù.
- Cần subquery hoặc query nhiều root phức tạp.
- Cần kiểm soát DISTINCT, selection hoặc query metadata.
- Cần bulk UPDATE/DELETE.
- Cần tối ưu SQL cụ thể và kiểm soát query plan.

Ví dụ custom repository có thể nhận cùng một Predicate nhưng tự quyết định projection:

```java
@Repository
public class CustomerQueryRepository {

    private final JPAQueryFactory queryFactory;

    public CustomerQueryRepository(JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    public List<CustomerSummary> findSummaries(Predicate predicate) {
        QCustomer customer = QCustomer.customer;

        return queryFactory
                .select(Projections.constructor(
                        CustomerSummary.class,
                        customer.id,
                        customer.firstName,
                        customer.lastName,
                        customer.email
                ))
                .from(customer)
                .where(predicate)
                .orderBy(customer.lastName.asc(), customer.id.asc())
                .fetch();
    }
}
```

Ví dụ này minh họa cách dùng `JPAQueryFactory`; để biên dịch cần khai báo bean factory với `EntityManager` và cấu hình Querydsl JPA tương thích. DTO constructor phải khớp thứ tự và kiểu biểu thức được chọn.

Có thể dùng QuerydslPredicateExecutor cho tìm kiếm đơn giản và custom repository cho báo cáo hoặc query đặc thù. Không cần ép mọi truy vấn vào một abstraction duy nhất.

## 14. Hiệu năng và bảo mật

Querydsl tạo query có bind parameter qua provider, nhưng điều đó không thay thế validation hoặc authorization.

**Giới hạn filter.** Chỉ expose các field mà người dùng được phép tìm. Dùng `QuerydslBinderCustomizer` để giới hạn web binding.

**Giới hạn page size.** Không cho client yêu cầu hàng trăm nghìn bản ghi qua một request.

**Bắt buộc tenant/user scope ở server.** Kết hợp điều kiện tenant lấy từ security context với predicate do người dùng cung cấp. Không tin tenantId hoặc ownerId do client gửi.

**Kiểm tra chuỗi rỗng và null.** Không thêm điều kiện khi filter không được chọn; phân biệt false/0 với trạng thái chưa nhập.

**Cẩn thận với contains.** `containsIgnoreCase` thường tạo LIKE với wildcard đầu; B-tree index thông thường có thể không hỗ trợ hiệu quả. Xem execution plan và cân nhắc full-text/trigram index theo database.

**Phân trang có thứ tự ổn định.** Thêm khóa duy nhất vào cuối sort để giảm khả năng bản ghi đổi thứ tự giữa các trang.

**Đo count query.** Page có thể phát sinh query đếm riêng. Với filter có JOIN hoặc predicate phức tạp, count có thể tốn kém.

**Không log dữ liệu nhạy cảm.** Query parameter có thể chứa email hoặc thông tin cá nhân; mask dữ liệu khi logging.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy QCustomer | Annotation processor chưa chạy hoặc sai classifier | Kiểm tra apt, Jakarta/Javax và clean compile |
| Q-type không nhận thay đổi entity | Generated source cũ hoặc IDE chưa reload | Chạy clean compile và refresh project |
| Repository không nhận Predicate | Thiếu QuerydslPredicateExecutor hoặc dependency không tương thích | Kiểm tra repository extends và Querydsl version |
| findOne ném lỗi nhiều kết quả | Predicate không duy nhất | Dùng findAll hoặc bảo đảm unique constraint |
| Form rỗng trả toàn bộ dữ liệu | BooleanBuilder không có điều kiện | Quy định rõ hành vi và kiểm tra hasValue |
| Filter false bị bỏ qua | Dùng điều kiện kiểu truthy thay vì null check | Dùng Boolean wrapper và kiểm tra != null |
| OR mở rộng kết quả ngoài ý muốn | Nhóm predicate sai | Tạo BooleanExpression OR trước khi AND vào builder |
| Client lọc được field nội bộ | Web binding mặc định quá rộng | Dùng excludeUnlistedProperties và including |
| Page total chậm | Count query phức tạp | Đo count riêng, cân nhắc Slice/custom query |
| Kết quả trùng sau JOIN | Association tạo nhiều hàng | Dùng distinct hoặc custom query đúng semantics |
| Querydsl method không đủ biểu đạt | Executor chỉ cung cấp thao tác predicate cơ bản | Dùng custom repository/JPAQueryFactory |
| Query chạy chậm với containsIgnoreCase | LIKE wildcard đầu hoặc thiếu index phù hợp | Kiểm tra execution plan và chiến lược tìm kiếm |

## 16. Checklist triển khai

- [ ] Querydsl dependency và annotation processor khớp Jakarta Persistence của dự án.
- [ ] Q-type được sinh từ entity, không được tự chỉnh sửa.
- [ ] Repository kế thừa `QuerydslPredicateExecutor<T>`.
- [ ] Predicate dùng Q-type thay vì ghép chuỗi query.
- [ ] BooleanBuilder được tạo mới cho từng request.
- [ ] Filter tùy chọn phân biệt null với false/0.
- [ ] Trường hợp predicate rỗng có hành vi được quyết định rõ.
- [ ] findOne chỉ dùng khi điều kiện đảm bảo tối đa một kết quả.
- [ ] count/exists được dùng đúng mục đích.
- [ ] Pageable có giới hạn page size và sort ổn định.
- [ ] Web binding chỉ cho phép các field được duyệt.
- [ ] Tenant/authorization condition được thêm từ server.
- [ ] Query phức tạp dùng custom repository phù hợp.
- [ ] Integration test xác nhận findAll/findOne/count/exists và phân trang.
- [ ] Query quan trọng được đo bằng SQL và execution plan trên database đích.

## Kết luận

`QuerydslPredicateExecutor` giúp Spring Data JPA thực thi các Predicate có kiểu thông qua những method repository quen thuộc: `findAll`, `findOne`, `count` và `exists`. Q-type được sinh từ entity giúp IDE hỗ trợ thuộc tính và phát hiện lỗi sớm; `BooleanBuilder` cho phép kết hợp các filter tùy chọn mà không phải nối chuỗi JPQL.

Hãy tạo predicate mới cho mỗi lần tìm kiếm, xác định rõ hành vi khi form rỗng, giới hạn field được bind từ HTTP và thêm điều kiện tenant/authorization ở server. Dùng Pageable khi cần Page và count; chuyển sang custom repository với `JPAQueryFactory` khi cần projection, fetch join, aggregate hoặc kiểm soát query nâng cao. Kiểm thử qua repository và JPA provider thật để xác nhận cả kết quả lẫn hành vi phân trang.
