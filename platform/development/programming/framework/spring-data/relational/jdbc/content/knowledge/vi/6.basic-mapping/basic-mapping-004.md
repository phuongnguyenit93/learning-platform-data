# Định nghĩa cột và khóa chính bằng @Column, @Id trong Spring Data JDBC

## 1. Mục tiêu của việc ánh xạ cột và khóa chính

Trong cơ sở dữ liệu quan hệ, một bảng có **các cột** lưu thuộc tính của bản ghi và thường có **khóa chính (primary key)** dùng để định danh duy nhất từng hàng. Trong Java, ta lại làm việc với class, object và các trường (*field*) như `id`, `title`, `unitPrice`. **Spring Data JDBC** nối hai mô hình này thông qua cơ chế ánh xạ (*relational object mapping*).

Hai annotation nền tảng là:

- **`@Column`:** chỉ rõ tên cột SQL tương ứng với một thuộc tính Java, nhất là khi hai bên dùng tên khác nhau.
- **`@Id`:** chỉ rõ thuộc tính nào đóng vai trò định danh (*identifier*) của entity, từ đó Spring Data JDBC nhận diện object mới hay đã tồn tại và thực hiện thao tác lưu/tải phù hợp.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public class Book {

    @Id
    private Long id;

    private String title;

    @Column("unit_price")
    private BigDecimal price;
}
~~~

Ở đây:

| Thành phần Java | Vai trò | Thành phần trong database |
|---|---|---|
| `@Table("books")` | Xác định bảng ánh xạ | Bảng `books` |
| `@Id private Long id` | Xác định identifier của entity | Cột khóa chính `id` |
| `private String title` | Ánh xạ theo quy ước đặt tên | Cột `title` |
| `@Column("unit_price") private BigDecimal price` | Ánh xạ tên cột tường minh | Cột `unit_price` |

**Phân biệt quan trọng:** các annotation này cung cấp **metadata mapping cho Spring Data JDBC**. Chúng không tự chạy câu lệnh `CREATE TABLE` hay biến thuộc tính Java thành ràng buộc SQL thực tế. Khóa chính ở database vẫn phải được định nghĩa bằng DDL hoặc migration.

## 2. Hai annotation thuộc những package nào?

Spring Data JDBC sử dụng annotation trong hệ sinh thái **Spring Data**, không phải annotation của Jakarta Persistence/JPA:

~~~java
// Spring Data Commons:
import org.springframework.data.annotation.Id;

// Spring Data Relational:
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;
~~~

Không nhầm với:

~~~java
// Các annotation JPA, không dùng thay cho mapping Spring Data JDBC:
import jakarta.persistence.Id;
import jakarta.persistence.Column;
import jakarta.persistence.Table;
~~~

Dù tên giống nhau, chúng phục vụ các tầng mapping khác nhau. `@Column` của Spring Data Relational thường viết `@Column("column_name")`, còn trong JPA thường dùng `@Column(name = "column_name")`. Sao chép nhầm import có thể làm repository ánh xạ sai hoặc không nhận metadata như mong muốn.

Một số annotation liên quan thường gặp:

| Annotation | Chức năng |
|---|---|
| `@Table("books")` | Đặt tên bảng của entity |
| `@Column("unit_price")` | Đặt tên cột của thuộc tính |
| `@Id` | Đánh dấu identifier |
| `@Transient` | Bỏ qua thuộc tính khỏi persistence mapping |
| `@Version` | Quản lý version để hỗ trợ optimistic locking |
| `@MappedCollection` | Điều khiển cột khóa ngoại/key cho collection thuộc aggregate |
| `@Embedded` | Ánh xạ các thuộc tính của value object vào các cột của bảng chứa |

Bài này tập trung vào **`@Column` và `@Id`**, dùng các annotation còn lại để chỉ rõ ranh giới trách nhiệm khi cần.

## 3. @Column: ánh xạ thuộc tính Java tới tên cột SQL

Mục đích của `@Column` là làm rõ **thuộc tính Java phải đọc/ghi cột nào**. Ví dụ trong Java ta thích tên `price` ngắn gọn nhưng schema hiện có dùng `unit_price`:

~~~java
@Column("unit_price")
private BigDecimal price;
~~~

Khi Spring Data JDBC đọc cột `unit_price`, nó ánh xạ giá trị vào thuộc tính `price`. Khi lưu entity, metadata này cũng được dùng để xác định cột nhận giá trị `price`.

### 3.1. Khi nào cần viết @Column?

**Trường hợp 1 — Tên Java và tên cột khác nhau về ý nghĩa**

~~~java
@Column("isbn_code")
private String isbn;

@Column("unit_price")
private BigDecimal price;
~~~

Mặc dù trường tên `isbn` và `price`, Spring Data JDBC sử dụng cột `isbn_code` và `unit_price`.

**Trường hợp 2 — Phải tương thích schema đã có**

Ví dụ một hệ thống cũ có tên cột `legacy_customer_code`. Java vẫn có thể dùng tên property dễ hiểu:

~~~java
@Column("legacy_customer_code")
private String customerCode;
~~~

**Trường hợp 3 — Muốn mapping rõ ràng, giảm phụ thuộc vào quy ước**

Ở nơi schema có lịch sử đặt tên không đồng nhất, `@Column` giúp người đọc thấy trực tiếp tên cột thực tế.

### 3.2. Khi nào không cần @Column?

Spring Data JDBC có **quy ước đặt tên** (*naming strategy*). Trong thiết lập thông dụng, tên thuộc tính camelCase được chuyển thành dạng có dấu gạch dưới tương ứng trong tên cột, chẳng hạn:

| Thuộc tính Java | Tên cột dự kiến theo quy ước thường gặp |
|---|---|
| `title` | `title` |
| `publishedOn` | `published_on` |
| `createdAt` | `created_at` |
| `bookCode` | `book_code` |

Vì vậy có thể viết:

~~~java
private LocalDate publishedOn;
~~~

và để framework ánh xạ tới cột `published_on` theo naming strategy thích hợp.

**Không nên hiểu bảng quy ước là cam kết tuyệt đối:** cách đặt tên còn phụ thuộc phiên bản, `NamingStrategy`, dialect và cách database xử lý chữ hoa/chữ thường hay identifier có dấu nháy. Nếu schema dùng tên đặc biệt, nên khai báo `@Column` rõ ràng và xác nhận SQL trên database thực tế.

### 3.3. @Column có tạo kiểu dữ liệu, NOT NULL hoặc index không?

**Không.** Đây là khác biệt cần nắm khi chuyển từ các công nghệ ORM có hỗ trợ sinh schema sang Spring Data JDBC.

Ví dụ:

~~~java
@Column("email_address")
private String email;
~~~

Dòng này không tự tạo:

- Cột `email_address` trong database.
- Ràng buộc `NOT NULL`, `UNIQUE` hoặc `CHECK`.
- `VARCHAR(320)` hay bất kỳ độ dài chính xác nào.
- Index để tăng tốc truy vấn theo email.
- Giá trị mặc định hoặc cơ chế tự động cập nhật timestamp.

Các quyết định trên thuộc **DDL/migration**:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(320) NOT NULL UNIQUE
);
~~~

Validation ở lớp Java, ví dụ `@NotNull`, có thể giúp phát hiện dữ liệu không hợp lệ sớm khi được kích hoạt ở tầng thích hợp, nhưng **không thay thế constraint của database**.

## 4. @Id: định danh entity trong Spring Data JDBC

`@Id` đánh dấu property mang **identity của entity**:

~~~java
@Id
private Long id;
~~~

Với Spring Data JDBC repository, identifier quan trọng cho cả hai hướng:

1. **Đọc entity:** xác định và ánh xạ giá trị khóa chính từ database về đối tượng.
2. **Lưu entity:** hỗ trợ nhận biết entity mới hay đã tồn tại để chọn hoạt động insert hoặc update.

Ví dụ, `CrudRepository<Book, Long>` khai báo:

~~~java
public interface BookRepository extends CrudRepository<Book, Long> {
}
~~~

Tham số kiểu `Book` là entity được quản lý; `Long` là kiểu identifier, tương ứng với property gắn `@Id`.

Khi gọi:

~~~java
Optional<Book> book = repository.findById(42L);
~~~

repository dùng identifier để tìm bản ghi tương ứng. Khi xóa:

~~~java
repository.deleteById(42L);
~~~

identifier xác định bản ghi bị tác động. Spring Data JDBC có thể phát sinh SQL riêng theo dialect và metadata mapping; không nên coi ví dụ SQL minh họa là chuỗi lệnh cố định của mọi phiên bản.

### 4.1. @Id không phải là định nghĩa PRIMARY KEY trong database

Java:

~~~java
@Id
private Long id;
~~~

SQL schema:

~~~sql
id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
~~~

Hai phần làm các việc khác nhau:

- `@Id` nói với **Spring Data JDBC** rằng property `id` là identifier.
- `PRIMARY KEY` nói với **database** rằng giá trị khóa chính phải duy nhất và không được null.
- `GENERATED BY DEFAULT AS IDENTITY` hướng dẫn **database** tạo giá trị ID trong trường hợp insert không cung cấp ID (cú pháp/hành vi phụ thuộc hệ quản trị).

Nếu Java có `@Id` nhưng bảng không có primary key hoặc giá trị trùng nhau, database vẫn có thể cho phép dữ liệu bất thường tùy schema. Mapping Java không tự bổ sung constraint còn thiếu.

## 5. Ví dụ hoàn chỉnh: Book ánh xạ cột và khóa chính

Giả sử ta xây dựng ứng dụng quản lý sách. Database có schema:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    isbn_code VARCHAR(20) NOT NULL UNIQUE,
    unit_price DECIMAL(12, 2) NOT NULL,
    published_on DATE
);
~~~

Các tên `isbn_code` và `unit_price` khác tên property Java, nên ta sử dụng `@Column`.

### 5.1. Class entity

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import java.time.LocalDate;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public class Book {

    @Id
    private Long id;

    private String title;

    @Column("isbn_code")
    private String isbn;

    @Column("unit_price")
    private BigDecimal price;

    private LocalDate publishedOn;

    public Book() {
    }

    public Book(
            String title,
            String isbn,
            BigDecimal price,
            LocalDate publishedOn
    ) {
        this.title = title;
        this.isbn = isbn;
        this.price = price;
        this.publishedOn = publishedOn;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getIsbn() {
        return isbn;
    }

    public void setIsbn(String isbn) {
        this.isbn = isbn;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    public LocalDate getPublishedOn() {
        return publishedOn;
    }

    public void setPublishedOn(LocalDate publishedOn) {
        this.publishedOn = publishedOn;
    }
}
~~~

Đây là entity mutable đơn giản để quan sát việc ID được gán sau khi lưu. Spring Data JDBC cũng hỗ trợ nhiều cách tạo đối tượng bất biến/constructor-based mapping, nhưng nguyên tắc về `@Id` và `@Column` vẫn là xác định identifier và tên cột.

### 5.2. Repository

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface BookRepository extends CrudRepository<Book, Long> {

    List<Book> findByIsbn(String isbn);
}
~~~

`findByIsbn` được khai báo theo **tên property Java** `isbn`, không phải tên cột `isbn_code`. Khi framework tạo truy vấn từ tên method trong phạm vi Spring Data JDBC hỗ trợ, metadata `@Column("isbn_code")` giúp xác định cột trong SQL.

### 5.3. Lưu đối tượng mới

~~~java
Book newBook = new Book(
        "Spring Data JDBC",
        "978-0000000001",
        new BigDecimal("199000.00"),
        LocalDate.of(2025, 1, 15)
);

Book saved = bookRepository.save(newBook);
Long generatedId = saved.getId();
~~~

Ở ví dụ này `id` ban đầu là `null`, vì vậy entity thường được xem là mới và Spring Data JDBC thực hiện INSERT. Database tạo giá trị khóa identity; framework lấy lại giá trị được sinh ra nếu driver/database hỗ trợ cơ chế khóa được sinh phù hợp.

SQL về mặt ý tưởng tương tự:

~~~sql
INSERT INTO books (title, isbn_code, unit_price, published_on)
VALUES (?, ?, ?, ?);
~~~

Giá trị của `?` được bind qua JDBC. Câu SQL thực tế và cách lấy generated key do Spring Data JDBC, dialect và driver quyết định.

Sau khi gọi `save`, **hãy sử dụng entity được trả về**, đặc biệt khi chọn mô hình bất biến hoặc có callback có thể trả đối tượng mới. Trong ví dụ mutable này, ID cũng có thể được cập nhật trên chính instance ban đầu.

### 5.4. Đọc rồi sửa một hàng đã tồn tại

~~~java
Book book = bookRepository.findById(generatedId)
        .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy sách: " + generatedId
        ));

book.setPrice(new BigDecimal("179000.00"));

Book updated = bookRepository.save(book);
~~~

`book` đã có identifier, nên repository nhận diện đây là đối tượng đã tồn tại theo chiến lược phát hiện entity mới thông thường và thực hiện đường cập nhật. SQL minh họa:

~~~sql
UPDATE books
SET title = ?, isbn_code = ?, unit_price = ?, published_on = ?
WHERE id = ?;
~~~

Cách phát sinh SQL cụ thể tùy mapping, lifecycle và phiên bản. `save` không hoạt động giống việc JPA tự theo dõi dirty fields: **đổi property trên object không tự gửi UPDATE cho tới khi có thao tác lưu phù hợp**.

## 6. Cách Spring Data JDBC biết entity là mới hay đã tồn tại

Đây là điểm dễ gây nhầm lẫn khi làm việc với `@Id`.

Ở cấu hình phổ biến, Spring Data xác định entity mới dựa trên metadata và trạng thái của đối tượng:

| Trạng thái entity | Cách hiểu thường gặp |
|---|---|
| `@Id Long id = null`, không có cơ chế phát hiện khác | Entity mới, chuẩn bị INSERT |
| `@Id Long id = 42L`, không có cơ chế phát hiện khác | Entity có ID, thường đi theo đường UPDATE |
| `@Id long id = 0` với primitive và chiến lược mặc định | Giá trị zero thường được coi là chưa có ID |
| Có property `@Version` | Version có thể được dùng **trước ID** để xác định entity mới |
| Entity triển khai `Persistable` | `isNew()` có thể quyết định trạng thái mới |

Bảng trên mô tả **chiến lược mặc định phổ biến**, không phải quy tắc duy nhất. Spring Data cho phép tùy biến detection và lifecycle; hành vi cụ thể phụ thuộc model/version/callback.

### 6.1. Vì sao nên dùng Long thay vì long khi ID sinh tự động?

~~~java
@Id
private Long id;
~~~

Dùng wrapper `Long` cho phép phân biệt:

- `null`: chưa có ID do database tạo.
- Một giá trị số: ID đã được gán.

Với primitive `long`, giá trị mặc định là `0`; dù Spring Data có quy tắc xử lý ID số bằng zero trong các trường hợp thông dụng, việc dùng `Long` thường rõ nghĩa hơn cho khóa sinh tự động và tránh nhầm lẫn với giá trị hợp lệ của nghiệp vụ.

### 6.2. Gán sẵn ID không có nghĩa là framework luôn INSERT

Giả sử ứng dụng sử dụng chuỗi mã do nghiệp vụ tạo:

~~~java
@Id
private String code;
~~~

Nếu tạo một entity mới với `code = "BK-001"` ngay trước lời gọi `save`, cơ chế mặc định có thể xem nó là entity đã tồn tại vì identifier không còn `null`. Kết quả là đường UPDATE được chọn, trong khi hàng chưa có trong database.

Đây không phải lỗi `@Id`; đó là vấn đề **phân biệt ID đã gán với trạng thái entity mới**.

Các hướng thường dùng:

1. Nếu database sinh ID, để giá trị ban đầu là `null` và nhận ID sau khi lưu.
2. Nếu ứng dụng tự sinh ID, cân nhắc tạo ID trong `BeforeConvertCallback` ở thời điểm thích hợp sau khi trạng thái mới đã được xác định.
3. Với mô hình cần tự quyết định, cân nhắc `Persistable` và triển khai `isNew()` đúng vòng đời.
4. Nếu dùng `@Version`, hiểu rằng chiến lược phát hiện entity mới có thể dựa vào version trước ID.

Không nên dựa vào giả định “`save` có ID thì framework sẽ thử UPDATE, không có hàng thì tự INSERT”: hành vi đó không được bảo đảm theo mô hình Spring Data JDBC.

## 7. Khóa chính được tạo ở đâu?

Có hai nhóm thiết kế phổ biến.

### 7.1. Database sinh khóa chính

DDL ví dụ:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);
~~~

Java:

~~~java
@Table("books")
public class Book {
    @Id
    private Long id;

    private String title;

    // constructor, getters, setters...
}
~~~

Tạo object mới với `id == null`, sau đó gọi `repository.save(book)`. Framework dựa vào cơ chế JDBC generated keys, dialect và khả năng database để nhận ID khi lưu.

Tùy database, cú pháp tạo identity có thể là `GENERATED ... AS IDENTITY`, `AUTO_INCREMENT` hoặc cơ chế khác. **`@Id` không quyết định chiến lược sinh khóa ở tầng database.**

### 7.2. Ứng dụng tự sinh khóa chính

Có thể dùng một mã nghiệp vụ hoặc UUID do ứng dụng tạo, nhưng phải đảm bảo chiến lược xác định entity mới phù hợp.

Ví dụ minh họa callback tạo UUID cho `BookDocument` trước khi chuyển entity sang dạng SQL:

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("book_documents")
public class BookDocument {

    @Id
    private UUID id;

    private String fileName;

    public UUID getId() {
        return id;
    }

    public void setId(UUID id) {
        this.id = id;
    }

    public String getFileName() {
        return fileName;
    }

    public void setFileName(String fileName) {
        this.fileName = fileName;
    }
}
~~~

Đăng ký callback:

~~~java
import java.util.UUID;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;

@Configuration
public class DocumentIdConfiguration {

    @Bean
    BeforeConvertCallback<BookDocument> assignDocumentId() {
        return document -> {
            if (document.getId() == null) {
                document.setId(UUID.randomUUID());
            }
            return document;
        };
    }
}
~~~

Khi sử dụng callback này, entity đi vào thao tác `save` với ID ban đầu `null`; ID được gán trong lifecycle trước khi ghi xuống database. **Bảng phải có cột ID tương thích**, và việc tạo UUID chỉ là một lựa chọn thiết kế. Với entity bất biến, callback có thể cần trả về instance mới thay vì mutate instance cũ.

Không được giả định “database tự sinh UUID” chỉ vì trong Java có `@Id UUID id`. Nơi sinh ID cần được xác định rõ: application, database default, trigger hay cơ chế khác.

## 8. Thêm @Version để kiểm soát cập nhật đồng thời

Mặc dù `@Version` không phải chủ đề chính, nó gắn chặt với lifecycle của `@Id`.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public class VersionedBook {

    @Id
    private Long id;

    @Version
    private Long version;

    private String title;

    // constructor, getters, setters...
}
~~~

DDL phải có cột version:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT,
    title VARCHAR(200) NOT NULL
);
~~~

Spring Data JDBC có thể dùng version để phát hiện entity mới và thực hiện **optimistic locking**. Khi cập nhật, framework kiểm tra version kỳ vọng; nếu bản ghi đã bị một giao dịch khác sửa, update có thể thất bại bằng một ngoại lệ optimistic locking thay vì ghi đè âm thầm.

Lưu ý:

- Kiểu wrapper `Long` cho phép version mới là `null`.
- Cần schema có cột version với kiểu tương thích.
- Nếu SQL thủ công cập nhật bảng mà không duy trì version, có thể phá vỡ giả định optimistic locking của repository.
- Cơ chế phát hiện entity mới khi có `@Version` có ưu tiên khác so với chỉ kiểm tra `@Id`.

## 9. @Column có dùng để ánh xạ khóa chính không?

Có thể khai báo cả `@Id` và `@Column` trên cùng property nếu tên cột khóa chính khác tên property Java:

~~~java
@Table("books")
public class Book {

    @Id
    @Column("book_id")
    private Long id;

    // ...
}
~~~

DDL:

~~~sql
CREATE TABLE books (
    book_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);
~~~

Hai annotation bổ sung cho nhau:

- `@Id`: thuộc tính này là **identifier**.
- `@Column("book_id")`: identifier được lưu ở **cột `book_id`**.

Nếu chỉ dùng `@Column("book_id")` mà bỏ `@Id`, framework không có metadata identifier đúng như yêu cầu repository. Nếu chỉ dùng `@Id` mà schema thật sự đặt tên cột `book_id`, quy ước mặc định có thể tìm cột `id` và gây lỗi.

### Có được gắn nhiều @Id để tạo khóa ghép?

Không nên coi việc gắn nhiều `@Id` trên nhiều property là cách tự động tạo **composite key**. Hỗ trợ và cách biểu diễn định danh ghép có thể phụ thuộc phiên bản Spring Data JDBC. Cần kiểm tra cơ chế được phiên bản đang dùng hỗ trợ và thiết kế mapping nhất quán với khóa ghép trong schema. Với bài học cơ bản, một property identifier đơn là mô hình rõ ràng nhất.

## 10. Cách nhận biết annotation nào ảnh hưởng tới SQL

Hãy tưởng tượng entity:

~~~java
@Table("customers")
public class Customer {

    @Id
    @Column("customer_id")
    private Long id;

    @Column("display_name")
    private String name;

    private String phoneNumber;

    // constructors / accessors...
}
~~~

DDL dự kiến:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    phone_number VARCHAR(30)
);
~~~

Khi repository lưu hoặc truy vấn một `Customer`, metadata về tên bảng, tên cột và identifier được dùng để tạo các thao tác SQL tương ứng. Ví dụ một câu tìm theo ID về mặt ý tưởng có thể là:

~~~sql
SELECT customer_id, display_name, phone_number
FROM customers
WHERE customer_id = ?;
~~~

Nhưng Spring Data JDBC có thể lựa chọn thứ tự cột, alias, cách quote identifier hoặc cú pháp riêng theo dialect khác ví dụ minh họa. Mục tiêu của `@Column` là **chỉ định đúng định danh cột**, không ép framework phải sinh SQL theo đúng mẫu chuỗi ở trên.

## 11. Tương tác với JdbcTemplate và NamedParameterJdbcTemplate

`@Id` và `@Column` được Spring Data JDBC sử dụng trong **mapping của repository/aggregate**. Nếu viết SQL trực tiếp với `JdbcTemplate`, bạn vẫn chịu trách nhiệm đọc cột và tạo object trong `RowMapper`.

Ví dụ:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class BookReportDao {

    private final JdbcTemplate jdbc;

    public BookReportDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<String> findAllIsbns() {
        String sql = "SELECT isbn_code FROM books ORDER BY id";
        return jdbc.query(
                sql,
                (rs, rowNum) -> rs.getString("isbn_code")
        );
    }
}
~~~

Ở đây `JdbcTemplate` thực thi câu SQL do ứng dụng viết. Một `RowMapper` tự định nghĩa không tự đọc `@Column("isbn_code")` trên entity để thay thế mọi tên cột trong câu SQL.

Tương tự, khi dùng `NamedParameterJdbcTemplate`:

~~~java
var params = new MapSqlParameterSource("id", bookId);
String sql = """
        SELECT id, title, isbn_code, unit_price, published_on
        FROM books
        WHERE id = :id
        """;
~~~

`:id` là **tên tham số SQL**, không phải annotation `@Id`. Tên tham số do người viết SQL lựa chọn và giá trị bind qua template; còn `@Id` là metadata về identity của entity trong Spring Data.

Do đó, có thể dùng repository cho CRUD của aggregate và JDBC template cho truy vấn báo cáo đặc biệt, nhưng phải giữ nhất quán tên cột, schema và quy tắc transaction.

## 12. Quy ước tên cột, identifier có dấu nháy và database khác nhau

Một số database không phân biệt chữ hoa/chữ thường với identifier thông thường; một số khác phân biệt rõ identifier **được quote** và **không được quote**. Ví dụ PostgreSQL thường gập identifier không quote về chữ thường, trong khi tên đã quote giữ nguyên chính tả.

Giả sử schema PostgreSQL khai báo:

~~~sql
CREATE TABLE "BookInventory" (
    "BookId" BIGINT PRIMARY KEY,
    "DisplayName" VARCHAR(200)
);
~~~

Schema như vậy khác đáng kể với bảng và cột snake_case không quote. Chỉ thay tên property Java đôi khi không đủ để đạt cách quote đúng.

Khi phải làm việc với identifier có chữ hoa, dấu cách hoặc từ khóa SQL, cần:

1. Xác nhận chính xác tên identifier ở database, bao gồm cách quote.
2. Khai báo mapping `@Table`, `@Column` tương ứng và nếu cần, cấu hình quy ước/quoting phù hợp với phiên bản và dialect.
3. Kiểm tra SQL thực tế cùng database đang sử dụng.

Với dự án mới, **tên bảng/cột đơn giản, không phụ thuộc quoting và có quy ước nhất quán** thường dễ duy trì nhất. Ví dụ `books`, `isbn_code`, `unit_price`.

## 13. NULL, giá trị mặc định và kiểu dữ liệu

`@Column` xác định tên cột, còn việc đọc/ghi dữ liệu phải tương thích với kiểu của cột.

| Kiểu Java | Kiểu SQL thường gặp | Lưu ý |
|---|---|---|
| `Long` | `BIGINT` | Thích hợp cho ID identity; cho phép `null` ở Java trước insert |
| `String` | `VARCHAR` / `TEXT` | Độ dài, charset và constraint do schema quyết định |
| `BigDecimal` | `DECIMAL` / `NUMERIC` | Nên dùng cho tiền hoặc dữ liệu cần độ chính xác thập phân |
| `LocalDate` | `DATE` | Không chứa giờ hay múi giờ |
| `LocalDateTime` | `TIMESTAMP` | Không tự mô tả múi giờ |
| `Boolean` | `BOOLEAN` hoặc kiểu tương đương | Tùy database và converter |

Ví dụ cột `published_on` cho phép `NULL` thì property `LocalDate publishedOn` có thể là `null`. Nếu schema đặt `NOT NULL` mà ứng dụng cố lưu `null`, database sẽ từ chối; `@Column` không tự chuyển thành giá trị mặc định.

Khi database có `DEFAULT CURRENT_TIMESTAMP` hoặc default khác, đừng giả định Spring Data JDBC sẽ **tự bỏ cột khỏi INSERT** mỗi khi Java property null. Tùy cách framework tạo INSERT, null có thể được bind tường minh, làm default phía database không được áp dụng. Cần thiết kế lifecycle/mapping/SQL phù hợp khi muốn database tự phát sinh giá trị.

## 14. @Column và các kiểu cấu trúc aggregate khác

### 14.1. Giá trị nhúng (embedded value object)

Một object giá trị như `Address` có thể được lưu trong các cột của bảng cha, thay vì bảng riêng. Spring Data JDBC cung cấp `@Embedded` để xử lý mô hình này, có thể dùng prefix giúp tránh trùng tên cột. `@Column` vẫn định nghĩa tên của một property, nhưng cơ chế flatten/prefix của embedded object có quy tắc riêng.

### 14.2. Collection và foreign key

Ví dụ aggregate `Order` chứa các dòng hàng `OrderLine`. Với mô hình one-to-many trong Spring Data JDBC, cột liên kết trong bảng con thường do cơ chế mapping aggregate quản lý; `@MappedCollection(idColumn = "...", keyColumn = "...")` có thể được dùng để tùy biến cột khóa tham chiếu và key cho collection.

Không nên gắn `@Column("order_id")` ngẫu nhiên vào một collection rồi kỳ vọng nó tương đương đầy đủ với `@MappedCollection`. Đây là hai trách nhiệm mapping khác nhau.

### 14.3. Thuộc tính không lưu database

Nếu property chỉ là giá trị tạm dùng trong ứng dụng, có thể dùng `@Transient` của Spring Data để loại nó khỏi mapping persistence. Việc không có `@Column` không có nghĩa nó tự động bị bỏ qua: **property persistent thông thường vẫn được ánh xạ theo naming strategy**.

## 15. Các lỗi thường gặp khi định nghĩa @Column và @Id

| Biểu hiện | Nguyên nhân điển hình | Hướng xử lý |
|---|---|---|
| Query báo không tồn tại cột `price` | Java property tên `price` nhưng cột thật là `unit_price` | Gắn `@Column("unit_price")` |
| Insert/update báo không tồn tại bảng/cột | DDL chưa chạy, sai schema hoặc tên identifier | Kiểm tra migration, `@Table`, `@Column` và naming strategy |
| Repository không phát hiện khóa chính phù hợp | Nhầm import `jakarta.persistence.Id` hoặc thiếu `@Id` | Dùng `org.springframework.data.annotation.Id` |
| Tạo object mới có ID tự đặt nhưng `save` chạy update | Cơ chế mặc định coi identifier không null là existing | Thiết kế `isNew`, `BeforeConvertCallback` hoặc version hợp lý |
| `save` không trả ID như mong muốn | Schema không cấu hình sinh ID, driver/dialect không lấy được key | Kiểm tra identity/sequence, generated keys và chiến lược ID |
| `@Column` được khai báo nhưng database vẫn thiếu constraint | `@Column` không tạo DDL | Đặt `PRIMARY KEY`, `NOT NULL`, `UNIQUE` trong migration |
| Object có giá trị `null` gây lỗi ràng buộc | Cột SQL `NOT NULL` hoặc giá trị chưa được gán | Xử lý đầu vào, default và constraint rõ ràng |
| Dùng tên `isbn_code` trong tên derived query | Derived query thường tham chiếu **property Java** `isbn` | Viết `findByIsbn(...)` |
| Update bị ghi đè do hai request đồng thời | Không có cơ chế optimistic locking phù hợp | Xem xét `@Version` và transaction/isolation |
| Truy vấn thủ công không hiểu mapping annotation | `JdbcTemplate` với `RowMapper` riêng không tự áp dụng mapping repository | Đọc đúng tên cột trong SQL/`ResultSet` |

### Nguyên tắc gỡ lỗi

Khi gặp lỗi, hãy lần lượt kiểm tra **DDL thật của bảng → tên cột và kiểu SQL → import annotation → tên property Java → trạng thái ID trước khi `save` → SQL đã thực thi**. Nếu lỗi liên quan object mới hay cũ, tập trung vào `@Id`, `@Version`, `Persistable.isNew()` và callbacks; nếu lỗi tên cột, tập trung vào `@Column`, `@Table` và naming strategy.

## 16. Bài tập thực hành

### Bài 1 — Đổi tên thuộc tính mà không đổi schema

Cho bảng:

~~~sql
CREATE TABLE students (
    student_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    enrollment_date DATE
);
~~~

Hãy tạo class `Student` có property `id`, `name` và `enrolledOn`. Dùng `@Table`, `@Id`, `@Column` để mapping đúng ba cột. Viết `CrudRepository<Student, Long>` và thử insert một sinh viên.

**Gợi ý:** tên cột `student_id` khác `id`; `full_name` khác `name`; `enrollment_date` khác `enrolledOn`.

### Bài 2 — Quan sát ID sinh tự động

Dùng cột identity kiểu `BIGINT`. Tạo object có `id == null`, gọi `save`, in ID trả về. Sau đó lấy cùng object theo ID và đổi một property rồi gọi `save` lần nữa. Quan sát database để xác nhận lần đầu INSERT, lần sau UPDATE.

### Bài 3 — Nhận diện nhầm annotation

Thử dùng `jakarta.persistence.Column` trong entity Spring Data JDBC thay cho `org.springframework.data.relational.core.mapping.Column`. Quan sát hành vi và giải thích vì sao **import annotation** quan trọng hơn việc hai annotation có tên giống nhau.

### Bài 4 — ID do ứng dụng tạo

Thiết kế entity có `@Id UUID id`. Thử gán UUID trước khi gọi `save` và tìm hiểu cách Spring Data JDBC phân biệt object mới. Sau đó dùng callback sinh UUID hoặc chiến lược `Persistable` để xử lý đúng vòng đời.

### Bài 5 — Kiểm tra vai trò constraint

Tạo `@Column("email_address")` rồi thử lưu hai bản ghi có cùng email. Thêm `UNIQUE(email_address)` vào schema, chạy lại và quan sát sự khác biệt. Giải thích sự phân chia trách nhiệm giữa metadata mapping và constraint trong database.

## 17. Ghi nhớ

- **`@Column` trả lời “property Java ánh xạ tới cột SQL nào?”**. Nó chủ yếu điều chỉnh tên cột; không tự khai báo kiểu SQL, độ dài, index hay ràng buộc.
- **`@Id` trả lời “property nào định danh entity?”**. Nó đóng vai trò chính trong tìm kiếm theo ID và trong cơ chế nhận biết entity mới hay đã tồn tại.
- Có thể đặt **`@Id` và `@Column` trên cùng property** khi tên cột khóa chính khác tên property.
- Dùng **annotation Spring Data đúng package**; không nhầm với `jakarta.persistence` của JPA.
- **Database chịu trách nhiệm thực thi `PRIMARY KEY` và chiến lược sinh ID**. Với khóa tự sinh, `Long id = null` là cách biểu diễn rõ ràng trước khi insert.
- `save` không tự bảo đảm INSERT khi entity đã có ID; cần thiết kế cơ chế `isNew`/callbacks/version khi dùng identifier gán thủ công.
- Với Spring Data JDBC, mapping entity và schema phải nhất quán; khai báo annotation Java không thay thế DDL hoặc migration.
