# Phân biệt ràng buộc ánh xạ, Bean Validation và ràng buộc cơ sở dữ liệu

Khi xây dựng một entity JPA, bạn thường gặp các annotation như **@Column(nullable = false)**, **@NotNull**, **@Size** và các ràng buộc **NOT NULL**, **UNIQUE**, **CHECK** trong database. Chúng có thể mô tả những điều kiện gần giống nhau, nhưng hoạt động ở các lớp khác nhau và được kiểm tra vào những thời điểm khác nhau.

Để thiết kế dữ liệu an toàn, cần phân biệt ba lớp:

1. **Ràng buộc ánh xạ JPA** mô tả cách thuộc tính Java được ánh xạ thành cột hoặc quan hệ trong database.
2. **Bean Validation** kiểm tra dữ liệu có thỏa điều kiện hợp lệ ở tầng ứng dụng hay không.
3. **Ràng buộc database** bảo vệ tính toàn vẹn của dữ liệu ngay tại nơi lưu trữ.

Ba lớp có thể cùng diễn tả một quy tắc, ví dụ tiêu đề sách không được null. Tuy nhiên, mỗi lớp có mục đích riêng. Annotation mapping không thay thế validation; validation ở ứng dụng cũng không thể thay thế constraint của database, đặc biệt khi có nhiều request ghi đồng thời hoặc dữ liệu được ghi từ hệ thống khác.

**Điều kiện của ví dụ:** các đoạn mã bên dưới dùng Spring Boot 3.x, Java 17 trở lên, Jakarta Persistence và Jakarta Bean Validation. Ứng dụng cần **spring-boot-starter-data-jpa**, **spring-boot-starter-validation**, JDBC driver, DataSource và schema tương ứng. Đây là các tệp trong ứng dụng Spring Boot, không phải chương trình độc lập có thể biên dịch chỉ bằng **javac**.

## 1. Nhìn nhanh ba lớp ràng buộc

| Lớp | Công cụ tiêu biểu | Câu hỏi được trả lời | Nơi thực thi |
|---|---|---|---|
| Mapping JPA | **@Column**, **@Table**, **@JoinColumn**, **@Id** | Thuộc tính này được lưu thành cột nào, kiểu và quan hệ ra sao? | JPA provider dùng metadata khi xây dựng mapping và làm việc với database |
| Bean Validation | **@NotNull**, **@NotBlank**, **@Size**, **@Digits**, custom constraint | Dữ liệu ứng dụng nhận hoặc chuẩn bị lưu có hợp lệ không? | Validator, Spring MVC, method validation hoặc JPA lifecycle integration |
| Database constraint | **PRIMARY KEY**, **NOT NULL**, **UNIQUE**, **FOREIGN KEY**, **CHECK** | Database có được phép lưu trạng thái dữ liệu này không? | Database khi thực thi INSERT/UPDATE/DELETE |

Ví dụ một thuộc tính tiêu đề:

~~~java
@NotBlank
@Size(max = 150)
@Column(nullable = false, length = 150)
private String title;
~~~

Ba annotation không phải ba cách viết khác nhau cho cùng một hành động:

- **@NotBlank** kiểm tra chuỗi có giá trị và chứa ít nhất một ký tự không phải khoảng trắng khi Bean Validation được gọi.
- **@Size(max = 150)** kiểm tra độ dài chuỗi ở tầng ứng dụng.
- **@Column(nullable = false, length = 150)** mô tả mapping và metadata cột cho JPA provider, đặc biệt khi provider sinh schema.

Database vẫn cần constraint tương ứng để bảo vệ dữ liệu ở tầng lưu trữ.

## 2. Ràng buộc ánh xạ JPA mô tả cấu trúc lưu trữ

JPA mapping mô tả quan hệ giữa lớp Java và cấu trúc quan hệ. Các annotation mapping thường gặp:

| Annotation | Ý nghĩa mapping |
|---|---|
| **@Id** | Thuộc tính định danh entity |
| **@GeneratedValue** | Chiến lược sinh khóa chính |
| **@Column** | Tên cột, nullability, độ dài, precision, scale và metadata khác |
| **@Table** | Tên bảng, schema và một số constraint ở mức bảng |
| **@JoinColumn** | Cột dùng để ánh xạ quan hệ |
| **@ManyToOne**, **@OneToMany**, **@OneToOne**, **@ManyToMany** | Cách ánh xạ quan hệ giữa entity |
| **@Enumerated** | Cách lưu enum |
| **@Embedded**, **@Embeddable** | Ánh xạ một nhóm giá trị vào cùng entity/table |

Ví dụ:

~~~java
@Entity
@Table(
    name = "books",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_books_isbn",
            columnNames = "isbn"
        )
    }
)
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "title",
        nullable = false,
        length = 150
    )
    private String title;

    @Column(
        name = "isbn",
        nullable = false,
        length = 20
    )
    private String isbn;

    @Column(
        name = "price",
        nullable = false,
        precision = 12,
        scale = 2
    )
    private BigDecimal price;

    protected Book() {
    }
}
~~~

Các thuộc tính của **@Column** có ý nghĩa mapping:

- **name**: tên cột trong database.
- **nullable**: metadata cho biết cột có cho phép null hay không.
- **length**: độ dài cột kiểu chuỗi khi provider tạo schema.
- **precision** và **scale**: độ chính xác và số chữ số sau dấu thập phân của kiểu số phù hợp.
- **unique**: metadata về tính duy nhất của cột khi tạo schema; với constraint có tên hoặc gồm nhiều cột, dùng **@Table(uniqueConstraints = ...)**.

### Mapping có tự kiểm tra object ngay khi gán giá trị không?

Không. Ví dụ:

~~~java
Book book = new Book();
book.setTitle(null);
~~~

Nếu entity cho phép gọi setter như trên, **@Column(nullable = false)** không phải một lời gọi validator tự động tại thời điểm gán. Annotation mô tả mapping cho JPA provider. Provider có thể thực hiện kiểm tra nullability nội bộ khi flush tùy cấu hình, nhưng điều đó không biến **@Column** thành một hệ thống kiểm tra dữ liệu đầu vào tổng quát.

Tương tự:

- **length = 150** không tự cắt chuỗi dài thành 150 ký tự.
- **precision = 12, scale = 2** không tự làm tròn giá tiền về hai chữ số thập phân theo quy tắc nghiệp vụ.
- **unique = true** không tự truy vấn xem giá trị có bị trùng trước khi lưu.
- **@JoinColumn(nullable = false)** không tự đảm bảo một object association khác null ngay lúc tạo object.

Khi provider sinh DDL từ mapping, các thuộc tính này có thể được chuyển thành kiểu cột hoặc constraint tương ứng. Nếu schema được quản lý bằng Flyway/Liquibase hoặc công cụ migration khác, migration phải tạo cấu trúc tương thích. Chỉ sửa annotation trong source không có nghĩa database production đã được cập nhật.

## 3. Bean Validation kiểm tra tính hợp lệ của dữ liệu ứng dụng

Bean Validation là chuẩn validation của Jakarta. Trong Spring Boot 3, các annotation thường dùng thuộc package **jakarta.validation.constraints**.

Các constraint phổ biến:

| Annotation | Quy tắc |
|---|---|
| **@NotNull** | Giá trị không được null |
| **@NotBlank** | Chuỗi không được null, rỗng hoặc chỉ chứa khoảng trắng |
| **@NotEmpty** | Chuỗi/collection/map/array không được null hoặc rỗng |
| **@Size(min, max)** | Giới hạn kích thước chuỗi, collection, map hoặc array |
| **@Min**, **@Max** | Giới hạn giá trị số nguyên theo ngưỡng |
| **@DecimalMin**, **@DecimalMax** | Giới hạn giá trị số theo ngưỡng thập phân |
| **@Digits** | Giới hạn số chữ số phần nguyên và phần thập phân |
| **@Positive**, **@PositiveOrZero** | Giá trị phải dương hoặc không âm |
| **@Email** | Kiểm tra chuỗi theo định dạng email được provider hỗ trợ |
| **@Pattern** | Kiểm tra chuỗi theo regular expression |

Một số khác biệt cần nhớ:

- **@NotNull** chỉ cấm null. Nó vẫn cho phép chuỗi rỗng hoặc chỉ có dấu cách.
- **@NotEmpty** cấm null và giá trị rỗng, nhưng chuỗi gồm ba dấu cách vẫn không rỗng.
- **@NotBlank** phù hợp khi chuỗi bắt buộc phải chứa ít nhất một ký tự không phải khoảng trắng.
- **@Size** giới hạn độ dài/kích thước; nó không thay thế **@NotNull** nếu giá trị cũng bắt buộc.
- **@Digits(integer = 10, fraction = 2)** kiểm tra số chữ số; nó không tự định dạng hay làm tròn số.

Muốn dùng Bean Validation trong Spring Boot, thêm dependency:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

Với Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Starter validation đưa implementation Bean Validation phù hợp vào classpath. Chỉ import annotation mà không có provider tương ứng thì việc validation thực tế có thể không hoạt động như mong đợi.

## 4. Kết hợp mapping và Bean Validation trong một entity

Một entity có thể dùng cả hai lớp annotation. Ví dụ:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

@Entity
@Table(
    name = "books",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_books_isbn",
        columnNames = "isbn"
    )
)
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Size(max = 150)
    @Column(nullable = false, length = 150)
    private String title;

    @NotBlank
    @Size(max = 20)
    @Column(nullable = false, length = 20)
    private String isbn;

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 10, fraction = 2)
    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Book() {
    }

    public Book(String title, String isbn, BigDecimal price) {
        this.title = title;
        this.isbn = isbn;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getIsbn() {
        return isbn;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Ở đây:

- **@NotBlank** và **@Size** kiểm tra nội dung title/isbn.
- **@NotNull**, **@DecimalMin** và **@Digits** kiểm tra giá.
- **@Column** mô tả cột mà JPA provider ánh xạ.
- **@UniqueConstraint** mô tả unique constraint ở mức bảng cho ISBN khi provider sinh DDL.

Ví dụ cố ý đặt **@Size(max = 150)** cùng **length = 150** và **@Digits(integer = 10, fraction = 2)** cùng **precision = 12, scale = 2**. Các cặp này cần nhất quán để ứng dụng không chấp nhận dữ liệu mà schema không thể lưu.

Tuy nhiên, hai lớp annotation vẫn có ngữ nghĩa riêng. Có thể có mapping mà không có Bean Validation, hoặc Bean Validation mà không có một thay đổi DDL tương ứng. Không nên dựa vào việc provider có thể suy ra một số thuộc tính schema từ validation annotation để bỏ qua migration.

## 5. Bean Validation chạy ở thời điểm nào?

Khai báo constraint chưa có nghĩa mọi object được tạo ra sẽ tự động được kiểm tra ngay lập tức. Validation chỉ xảy ra khi một cơ chế gọi validator hoặc framework tích hợp kích hoạt nó.

Có ba nơi thường gặp.

### 5.1. Kiểm tra request trong Spring MVC

Khi nhận request HTTP, đặt constraint trên DTO và dùng **@Valid** tại tham số controller:

~~~java
package com.example.catalog.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

public record CreateBookRequest(
    @NotBlank
    @Size(max = 150)
    String title,

    @NotBlank
    @Size(max = 20)
    String isbn,

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 10, fraction = 2)
    BigDecimal price
) {
}
~~~

Controller:

~~~java
package com.example.catalog.api;

import com.example.catalog.service.BookService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/books")
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Long create(@Valid @RequestBody CreateBookRequest request) {
        return bookService.create(
            request.title(),
            request.isbn(),
            request.price()
        );
    }
}
~~~

Nếu request vi phạm constraint, Spring MVC thực hiện validation trước khi gọi phần thân phương thức controller. Với request body không hợp lệ, Spring thường trả HTTP 400 theo cơ chế xử lý lỗi mặc định hoặc handler tùy chỉnh của ứng dụng.

DTO cho phép định nghĩa quy tắc đầu vào API mà không buộc mọi quy tắc đó phải là quy tắc lưu trữ của entity. Ví dụ một request có thể yêu cầu trường xác nhận mật khẩu, nhưng entity tài khoản không cần lưu trường xác nhận này.

### 5.2. Kiểm tra trong service bằng method validation

Có thể đặt constraint trên tham số hoặc giá trị trả về của phương thức service:

~~~java
@Service
@Validated
public class BookService {

    public void changePrice(
            @NotBlank String isbn,
            @NotNull @DecimalMin("0.00") BigDecimal price) {
        // Thực hiện nghiệp vụ.
    }
}
~~~

**@Validated** trên bean cho phép Spring method validation áp dụng các constraint ở ranh giới lời gọi method khi cấu hình/provider phù hợp. Đây là cơ chế khác với JPA entity lifecycle validation. Cần kiểm tra dependency validation và cách bean được gọi qua Spring proxy.

Không nên mặc định rằng gọi trực tiếp một method bằng **new BookService(...)** sẽ tự kích hoạt Spring method validation.

### 5.3. Validation khi JPA persist/update entity

Jakarta Persistence có tích hợp với Jakarta Bean Validation. Khi có Bean Validation provider và validation integration được bật theo cấu hình persistence, JPA provider có thể kích hoạt validation ở các lifecycle event như trước persist và trước update.

Các nhóm mặc định thường là:

- Trước persist: nhóm **Default**.
- Trước update: nhóm **Default**.
- Trước remove: mặc định không chạy validation group nào.

Có thể cấu hình nhóm validation cho các lifecycle event bằng persistence properties, ví dụ **jakarta.persistence.validation.group.pre-persist** và **jakarta.persistence.validation.group.pre-update**. Trong Spring Boot, các thuộc tính JPA provider có thể được truyền qua cấu hình **spring.jpa.properties**. Cần kiểm tra đúng provider và cấu hình thực tế của ứng dụng.

Điểm quan trọng: Bean Validation không chạy chỉ vì bạn viết:

~~~java
Book book = new Book(null, "9780000000000", BigDecimal.TEN);
~~~

Object Java đã được tạo. Nếu chưa có validator nào được gọi, constructor không tự chạy các annotation constraint. Khi ứng dụng gọi **Validator.validate(book)**, dùng Spring MVC **@Valid**, method validation hoặc JPA lifecycle integration thì các constraint mới được đánh giá.

## 6. Database constraint bảo vệ dữ liệu tại nơi lưu trữ

Database constraint là quy tắc do chính database thực thi. Nó bảo vệ dữ liệu bất kể thao tác ghi đến từ:

- Spring Data JPA.
- JDBC hoặc native SQL.
- Một service khác.
- Batch job hoặc công cụ quản trị.
- Một ứng dụng khác dùng chung database.

Các constraint quan trọng:

| Constraint | Vai trò | Ví dụ |
|---|---|---|
| **PRIMARY KEY** | Định danh hàng duy nhất, không null | **id BIGINT PRIMARY KEY** |
| **NOT NULL** | Cấm giá trị null | **title VARCHAR(150) NOT NULL** |
| **UNIQUE** | Cấm giá trị hoặc tổ hợp giá trị bị trùng | **UNIQUE (isbn)** |
| **FOREIGN KEY** | Bảo đảm tham chiếu tới hàng tồn tại | **FOREIGN KEY (category_id) REFERENCES categories(id)** |
| **CHECK** | Kiểm tra biểu thức trên từng hàng | **CHECK (price >= 0)** |

Ví dụ DDL PostgreSQL:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    isbn VARCHAR(20) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT uk_books_isbn UNIQUE (isbn),
    CONSTRAINT ck_books_title_not_blank
        CHECK (length(trim(title)) > 0),
    CONSTRAINT ck_books_price_non_negative
        CHECK (price >= 0)
);
~~~

DDL này bảo vệ các quy tắc quan trọng ngay cả khi một chương trình bỏ qua Bean Validation. Ví dụ một câu SQL trực tiếp cố insert giá âm sẽ bị database từ chối bởi CHECK constraint.

Một số chi tiết phụ thuộc hệ quản trị:

- So sánh chuỗi trong UNIQUE có thể phân biệt hoa thường hoặc không, tùy collation và kiểu dữ liệu.
- Cách tính độ dài chuỗi có thể khác nhau với Unicode và kiểu cột.
- Hành vi CHECK khi biểu thức nhận NULL phụ thuộc logic SQL ba giá trị; nếu cột bắt buộc, kết hợp NOT NULL.
- Khả năng hỗ trợ và cú pháp DDL có thể khác giữa PostgreSQL, MySQL, SQL Server, Oracle và các hệ khác.

Vì vậy, hãy dùng migration theo đúng database đang triển khai và kiểm thử constraint trên database đó.

## 7. So sánh một quy tắc qua ba lớp

Lấy quy tắc “giá sách không được null và không âm”:

| Lớp | Cách khai báo | Điều gì được bảo vệ |
|---|---|---|
| JPA mapping | **@Column(nullable = false, precision = 12, scale = 2)** | Metadata ánh xạ và cấu trúc cột khi sinh schema |
| Bean Validation | **@NotNull**, **@DecimalMin("0.00")**, **@Digits(...)** | Object được validate không chứa giá trị vi phạm |
| Database | **NOT NULL**, **CHECK (price >= 0)**, **NUMERIC(12,2)** | Không cho lưu hàng vi phạm các constraint |

Ba lớp bổ trợ nhau:

1. Mapping giúp JPA hiểu cấu trúc dữ liệu.
2. Bean Validation giúp phát hiện dữ liệu không hợp lệ sớm và trả lỗi thân thiện.
3. Database constraint là hàng rào cuối cùng bảo vệ tính toàn vẹn của dữ liệu.

Nếu chỉ dùng mapping, dữ liệu từ request vẫn có thể không hợp lệ về nghiệp vụ. Nếu chỉ dùng Bean Validation, một câu SQL trực tiếp vẫn có thể bỏ qua validator. Nếu chỉ dùng database constraint, lỗi có thể chỉ xuất hiện lúc ghi dữ liệu và khó chuyển thành thông báo phù hợp cho người dùng.

## 8. Vì sao existsBy... không thay thế UNIQUE constraint?

Giả sử service kiểm tra ISBN trước khi lưu:

~~~java
if (bookRepository.existsByIsbn(isbn)) {
    throw new IllegalStateException("ISBN already exists");
}

bookRepository.save(book);
~~~

Kiểm tra này cải thiện trải nghiệm khi ISBN đã tồn tại ở thời điểm kiểm tra. Nhưng nó không đảm bảo tính duy nhất dưới tải đồng thời:

1. Request A gọi **existsByIsbn** và nhận **false**.
2. Request B gọi cùng truy vấn và cũng nhận **false**.
3. Cả hai cùng insert một ISBN.
4. Nếu database không có UNIQUE constraint, cả hai hàng có thể được lưu.

Đây là race condition giữa thao tác kiểm tra và thao tác ghi. Chỉ kiểm tra ở Java không khóa được mọi đường ghi vào database.

Giải pháp:

- Giữ kiểm tra ở service nếu cần phản hồi sớm.
- Tạo UNIQUE constraint trên cột hoặc tổ hợp cột trong database.
- Bắt và chuyển lỗi vi phạm constraint thành lỗi nghiệp vụ/API phù hợp.
- Nếu cần xử lý cập nhật đồng thời phức tạp hơn, xem xét optimistic locking với **@Version** hoặc chiến lược khóa phù hợp.

Bean Validation cũng không thay thế UNIQUE constraint. Constraint **@Unique** không phải constraint chuẩn có sẵn của Jakarta Bean Validation cho một giá trị duy nhất trong toàn bộ database; kiểm tra uniqueness thường cần truy vấn và vẫn có race condition. Có thể tạo custom validator để kiểm tra sớm, nhưng database vẫn phải giữ UNIQUE constraint.

## 9. Constraint trên quan hệ entity

Với quan hệ JPA, cần phân biệt mapping quan hệ, Bean Validation và foreign key.

Ví dụ một sách bắt buộc thuộc về một category:

~~~java
@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "category_id", nullable = false)
    @NotNull
    private Category category;

    protected Book() {
    }
}
~~~

Ý nghĩa:

- **@ManyToOne** mô tả quan hệ nhiều sách thuộc một category.
- **optional = false** mô tả quan hệ bắt buộc ở mức JPA mapping.
- **@JoinColumn(nullable = false)** mô tả cột khóa ngoại không nullable trong mapping.
- **@NotNull** kiểm tra association khi Bean Validation được kích hoạt.
- Database cần cột **category_id NOT NULL** và FOREIGN KEY tham chiếu **categories(id)** để bảo vệ tính toàn vẹn thực tế.

Một association khác null vẫn có thể tham chiếu tới một entity không tồn tại hoặc chưa được lưu đúng cách. Foreign key constraint của database mới đảm bảo giá trị khóa ngoại tham chiếu tới hàng hợp lệ.

## 10. Custom constraint cho quy tắc nghiệp vụ phức tạp

Các constraint dựng sẵn xử lý tốt quy tắc trên từng thuộc tính. Với quy tắc liên quan nhiều field, có thể tạo class-level constraint.

Ví dụ ngày kết thúc phải sau ngày bắt đầu:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidDateRangeValidator.class)
public @interface ValidDateRange {

    String message() default "endDate must be after startDate";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
public class ValidDateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingRequest> {

    @Override
    public boolean isValid(
            BookingRequest value,
            ConstraintValidatorContext context) {

        if (value == null
                || value.getStartDate() == null
                || value.getEndDate() == null) {
            return true;
        }

        return value.getEndDate().isAfter(value.getStartDate());
    }
}
~~~

DTO:

~~~java
@ValidDateRange
public class BookingRequest {

    @NotNull
    private LocalDate startDate;

    @NotNull
    private LocalDate endDate;

    public LocalDate getStartDate() {
        return startDate;
    }

    public LocalDate getEndDate() {
        return endDate;
    }
}
~~~

Validator trả về **true** khi các field cần so sánh còn thiếu vì trách nhiệm kiểm tra null đã được giao cho **@NotNull**. Cách này tránh một lỗi validation kép khó đọc. Nếu quy tắc yêu cầu thông báo khác khi một field null, có thể thiết kế validator theo yêu cầu cụ thể.

Custom Bean Validation constraint kiểm tra dữ liệu ứng dụng. Nếu quy tắc cũng phải được bảo vệ trước mọi đường ghi, hãy xem có thể biểu diễn bằng database CHECK/FK/UNIQUE hay cần một thiết kế dữ liệu khác.

## 11. Validation groups và khác biệt giữa tạo mới/cập nhật

Có những quy tắc áp dụng khi tạo mới nhưng không áp dụng khi cập nhật, hoặc ngược lại. Bean Validation hỗ trợ validation groups.

Ví dụ khai báo marker interface:

~~~java
public interface OnCreate {
}

public interface OnUpdate {
}
~~~

DTO:

~~~java
public class BookRequest {

    @NotBlank(groups = {OnCreate.class, OnUpdate.class})
    @Size(max = 150, groups = {OnCreate.class, OnUpdate.class})
    private String title;

    @NotBlank(groups = OnCreate.class)
    private String isbn;

    @NotNull(groups = {OnCreate.class, OnUpdate.class})
    @DecimalMin(value = "0.00", groups = {OnCreate.class, OnUpdate.class})
    private BigDecimal price;

    // getters/setters
}
~~~

Controller có thể chọn group:

~~~java
@PostMapping
public void create(
        @Validated(OnCreate.class) @RequestBody BookRequest request) {
    // ...
}

@PutMapping("/{id}")
public void update(
        @Validated(OnUpdate.class) @RequestBody BookRequest request) {
    // ...
}
~~~

Lưu ý: khi chỉ chỉ định một group như **OnCreate.class**, Bean Validation không tự động chạy group **Default** trừ khi group sequence hoặc kế thừa group được cấu hình để bao gồm nó. Vì vậy, nếu DTO có constraint không gắn group cụ thể, hãy quyết định rõ cách các group kết hợp.

Với JPA lifecycle validation, nhóm được dùng cho pre-persist/pre-update có cấu hình mặc định và có thể được thay đổi bằng persistence properties. Không giả định group được chọn ở controller sẽ tự động trở thành group dùng khi Hibernate validate entity lúc persist. Đây là hai điểm kích hoạt validation khác nhau.

## 12. DDL generation và migration

JPA mapping có thể được Hibernate dùng để sinh DDL. Bean Validation provider cũng có thể tích hợp với Hibernate ORM và một số constraint có thể ảnh hưởng metadata DDL, ví dụ **@NotNull** hoặc **@Size**. Tuy nhiên, kết quả phụ thuộc provider, phiên bản, cấu hình và chế độ schema generation.

Các chế độ Hibernate thường gặp qua cấu hình Spring Boot:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Một số giá trị thường dùng:

- **none**: không tự tạo hoặc kiểm tra schema.
- **validate**: kiểm tra mapping so với schema hiện có.
- **update**: cố gắng điều chỉnh schema theo mapping.
- **create**: tạo lại schema khi khởi động theo hành vi của provider.
- **create-drop**: tạo schema khi khởi động và xóa khi đóng context theo hành vi của provider.

Trong môi trường production, nên quản lý schema bằng migration có phiên bản như Flyway hoặc Liquibase. Migration thể hiện rõ việc thêm cột, thay đổi kiểu, tạo unique constraint, foreign key và CHECK constraint. Annotation trong code không tự cập nhật mọi database đã triển khai.

Quy trình an toàn thường là:

1. Thêm hoặc điều chỉnh Bean Validation để kiểm tra dữ liệu ở tầng ứng dụng.
2. Cập nhật JPA mapping cho đúng cấu trúc mong muốn.
3. Viết migration tạo hoặc sửa constraint trong database.
4. Chạy migration trên môi trường kiểm thử.
5. Chạy integration test để xác nhận cả validation và database constraint.
6. Dùng **ddl-auto: validate** nếu phù hợp để phát hiện mapping không khớp schema.

## 13. Xử lý lỗi theo đúng lớp phát sinh

Một hệ thống tốt phân biệt lỗi validation ứng dụng và lỗi constraint database.

| Lỗi | Thời điểm thường gặp | Cách phản hồi |
|---|---|---|
| DTO vi phạm **@NotBlank** | Khi Spring MVC validate request | HTTP 400 với field error |
| Service method vi phạm constraint | Khi Spring method validation chạy | Chuyển thành lỗi đầu vào theo quy ước API |
| Entity vi phạm JPA lifecycle validation | Trước persist/update theo cấu hình validation integration | Chuyển thành lỗi dữ liệu không hợp lệ |
| UNIQUE/FOREIGN KEY/CHECK vi phạm | Khi database thực thi SQL | Bắt lỗi persistence/data integrity và ánh xạ sang phản hồi phù hợp |
| Schema không tương thích mapping | Khi validate schema hoặc khởi động | Sửa migration/schema hoặc mapping trước khi triển khai |

Không nên trả nguyên SQL, tên bảng nội bộ hoặc stack trace database cho client. Hãy ghi log ở server với correlation id phù hợp và trả lỗi API có ý nghĩa.

Với constraint UNIQUE, cần lưu ý lỗi có thể chỉ phát sinh khi flush hoặc commit. Gọi **save()** không đảm bảo SQL đã được thực thi ngay trong mọi chiến lược ID và cấu hình flush. Nếu cần bắt lỗi ở một vị trí cụ thể, có thể chủ động gọi **saveAndFlush()** hoặc **flush()**, nhưng vẫn phải xử lý transaction rollback đúng cách.

## 14. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chuỗi rỗng vẫn được lưu | Chỉ dùng **@NotNull** | Dùng **@NotBlank** nếu chuỗi bắt buộc có nội dung |
| Chuỗi quá dài gây lỗi database | Có **@Column(length = ...)** nhưng không validate đầu vào hoặc schema không đồng bộ | Kết hợp **@Size** và cột VARCHAR phù hợp |
| Giá âm được gửi vào service | Thiếu Bean Validation hoặc domain invariant | Dùng **@DecimalMin** và kiểm tra quy tắc ở domain/service |
| Hai request tạo cùng ISBN | Chỉ dùng **existsByIsbn** | Tạo UNIQUE constraint trong database và xử lý lỗi trùng |
| Gán association khác null nhưng khóa ngoại không hợp lệ | Chỉ dùng **@NotNull** trên quan hệ | Bảo đảm entity được lưu và tạo FOREIGN KEY constraint |
| Validation không chạy | Thiếu provider, không có trigger hoặc cấu hình validation bị tắt | Kiểm tra dependency và điểm gọi validation |
| DDL không thay đổi sau khi sửa annotation | Schema do migration quản lý hoặc ddl-auto không tạo schema | Cập nhật migration tương ứng |
| Database từ chối giá trị mà Bean Validation cho qua | Constraint ứng dụng yếu hơn schema hoặc khác semantics | Đồng bộ quy tắc và kiểm thử trên database thật |
| Dựa vào lỗi database để báo lỗi đầu vào | Thiếu validation sớm | Validate request/DTO trước khi vào tầng persistence |

## 15. Checklist thiết kế ràng buộc

- [ ] Xác định quy tắc thuộc mapping, validation hay tính toàn vẹn dữ liệu.
- [ ] Dùng **@Column** và các annotation mapping để mô tả cấu trúc lưu trữ.
- [ ] Dùng **@NotNull**, **@NotBlank**, **@Size**, **@Digits** và constraint phù hợp để kiểm tra dữ liệu ứng dụng.
- [ ] Dùng DTO và **@Valid** cho dữ liệu đầu vào API.
- [ ] Kiểm tra JPA lifecycle validation nếu muốn validate entity trước persist/update.
- [ ] Dùng NOT NULL, UNIQUE, FOREIGN KEY và CHECK ở database cho invariant cần được bảo vệ ở mọi đường ghi.
- [ ] Không dựa vào truy vấn kiểm tra trước khi insert để thay thế UNIQUE constraint.
- [ ] Đồng bộ mapping, Bean Validation và migration.
- [ ] Kiểm thử lỗi validation ở ứng dụng và lỗi constraint ở database.
- [ ] Chuyển lỗi thành phản hồi API phù hợp, không làm lộ chi tiết SQL nội bộ.

## 16. Kết luận

Ràng buộc ánh xạ JPA mô tả cách dữ liệu Java được lưu trữ; Bean Validation kiểm tra dữ liệu ở các điểm ứng dụng kích hoạt validator; database constraint bảo vệ tính toàn vẹn ngay tại nơi lưu trữ. Một quy tắc quan trọng có thể xuất hiện ở cả ba lớp, nhưng mỗi lớp phải được cấu hình và kiểm thử theo vai trò riêng.

Hãy dùng validation để phát hiện dữ liệu sai sớm, mapping để giữ mô hình Java nhất quán với schema, và database constraint để bảo vệ dữ liệu trước truy cập đồng thời hoặc những đường ghi bỏ qua ứng dụng.