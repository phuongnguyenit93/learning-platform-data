# Tạo aggregate root và repository đầu tiên với Spring Data JDBC

Khi bắt đầu một dự án **Spring Data Relational JDBC**, bước quan trọng nhất không chỉ là khai báo một interface kế thừa `CrudRepository`. Ta cần xác định **aggregate root** — đối tượng đại diện cho một ranh giới nhất quán của nghiệp vụ — rồi để repository làm việc qua đối tượng gốc đó.

Bài thực hành này xây dựng một ứng dụng Java nhỏ lưu **sách trong danh mục** bằng **Spring Boot + Spring Data JDBC + H2**. Mỗi `Book` là một aggregate root độc lập; ứng dụng tạo bảng, lưu sách, tìm theo ID, tìm theo tên, cập nhật giá và xóa sách. Phần cuối mở rộng sang aggregate gồm nhiều bảng để làm rõ vì sao Spring Data JDBC nhấn mạnh khái niệm aggregate.

## 1. Kết quả cần đạt

Sau khi thực hiện, bạn có thể:

1. Giải thích aggregate, aggregate root và vai trò của repository trong Spring Data JDBC.
2. Khởi tạo dự án Spring Boot dùng `spring-boot-starter-data-jdbc` và một cơ sở dữ liệu quan hệ.
3. Ánh xạ một Java record thành bảng bằng `@Table` và `@Id`.
4. Tạo repository với `CrudRepository<Book, Long>`, không cần tự viết CRUD SQL cơ bản.
5. Quan sát sự khác nhau giữa tạo mới, tải, cập nhật và xóa aggregate.
6. Biết khi nào thêm entity con với `@MappedCollection` và khi nào chỉ giữ tham chiếu bằng ID.

### Cần chuẩn bị

- **JDK 17 trở lên**; trong bài sử dụng Java record.
- Một IDE cho Java và Spring Boot (IntelliJ IDEA, VS Code hoặc Eclipse).
- Maven hoặc Maven Wrapper đi kèm dự án.
- Kiến thức cơ bản về Java, SQL, khóa chính và dependency injection.

Ví dụ sử dụng các API Spring Data JDBC phổ biến trong các dự án Spring Boot 3.x. Khi tạo dự án bằng Spring Initializr, hãy chọn một phiên bản Spring Boot ổn định tương thích với JDK của bạn; để Initializr quản lý phiên bản các starter. Các đoạn mã tập trung vào cấu hình và cách dùng Spring Data JDBC, không phụ thuộc vào một bản vá cụ thể.

## 2. Aggregate root là gì?

**Aggregate** là một nhóm dữ liệu và đối tượng nghiệp vụ được xem như một đơn vị nhất quán khi thay đổi. **Aggregate root** là đối tượng duy nhất mà mã bên ngoài sử dụng để thực hiện các thay đổi lên aggregate đó.

Xét hai trường hợp:

~~~text
Trường hợp đơn giản: danh mục sách

Book (aggregate root)
├── id
├── title
└── price

Trường hợp phức tạp hơn: đơn hàng

PurchaseOrder (aggregate root)
├── id, customerId, status
├── OrderLine #1 (sku, quantity)
└── OrderLine #2 (sku, quantity)

Customer (aggregate root riêng)
└── id, name
~~~

Trong ví dụ sách, aggregate chỉ gồm **một đối tượng**; đây là điểm khởi đầu tốt nhất để học repository. Với đơn hàng, các dòng hàng có thể thuộc vòng đời của đơn hàng: muốn thêm hoặc xóa dòng hàng, ứng dụng thao tác qua `PurchaseOrder`. Ngược lại, khách hàng có vòng đời riêng; đơn hàng thường chỉ giữ `customerId`, thay vì coi khách hàng là entity con của đơn hàng.

Trong Spring Data JDBC, nguyên tắc thiết kế quan trọng là:

- **Mỗi aggregate có một root**, là điểm truy cập để lưu và tải toàn bộ aggregate.
- Repository thường được định nghĩa cho **aggregate root**. Entity con không nhất thiết cần repository riêng.
- Các đối tượng *thuộc sở hữu* aggregate có vòng đời gắn với root. Khi lưu root, Spring Data JDBC thực hiện các thao tác database tương ứng với mapping của aggregate.
- Các aggregate khác nhau thường tham chiếu lẫn nhau bằng ID hoặc `AggregateReference`, để giữ ranh giới sở hữu rõ ràng.
- **Không có persistence context và dirty checking kiểu JPA**. Thay đổi một đối tượng đang ở trong bộ nhớ không tự tạo lệnh `UPDATE`; cần gọi `save` để lưu trạng thái.

**Không nên hiểu “aggregate root” đơn thuần là một class có `@Id`.** Root là quyết định về nghiệp vụ, phạm vi thay đổi và tính nhất quán. `@Id` chỉ giúp Spring Data JDBC nhận biết định danh trong cơ sở dữ liệu.

## 3. Khởi tạo dự án

Mở [Spring Initializr](https://start.spring.io/) và tạo dự án với lựa chọn:

| Mục | Giá trị minh họa |
|---|---|
| Project | Maven |
| Language | Java |
| Group | `com.example` |
| Artifact | `book-catalog` |
| Package name | `com.example.catalog` |
| Packaging | Jar |
| Java | 17 hoặc cao hơn |
| Dependencies | **Spring Data JDBC**, **H2 Database** |

Ví dụ chạy từ `CommandLineRunner`, nên **không cần Spring Web**. H2 là database trong bộ nhớ để bạn thực hành nhanh; khi triển khai thực tế có thể thay bằng PostgreSQL, MySQL hoặc database được Spring Data JDBC hỗ trợ, cùng driver và cấu hình thích hợp.

Tệp `pom.xml` do Initializr sinh ra phải có các dependency tương đương:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jdbc</artifactId>
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

Đây là **phần dependencies** để đối chiếu; giữ nguyên parent, plugin và phần cấu hình còn lại do Initializr tạo. Spring Boot quản lý phiên bản tương thích của các thư viện. Starter Spring Data JDBC mang theo Spring JDBC và hạ tầng repository cần thiết.

Cấu trúc các tệp chính của ví dụ:

~~~text
book-catalog/
├── pom.xml
├── mvnw
├── mvnw.cmd
└── src/
    └── main/
        ├── java/com/example/catalog/
        │   ├── CatalogApplication.java
        │   ├── domain/Book.java
        │   └── repository/BookRepository.java
        └── resources/
            ├── application.yml
            └── schema.sql
~~~

Các package `domain` và `repository` nằm dưới `com.example.catalog`. Đây là chi tiết quan trọng: `@SpringBootApplication` trong `com.example.catalog` cho phép Spring Boot tìm các component và repository ở những package con theo cấu hình mặc định.

## 4. Tạo bảng và kết nối H2

### 4.1. Tạo `schema.sql`

Thêm tệp `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

Ý nghĩa:

- `id` là khóa chính kiểu `BIGINT`, được database tự sinh khi thêm hàng.
- `title` là tên sách, không cho phép `NULL`.
- `price` lưu số thập phân chính xác, thích hợp hơn `DOUBLE` cho giá tiền.

Đối với ví dụ này, **tên bảng và tên cột được chủ động khai báo**. Khi mapping trở nên phức tạp, hãy giữ cách đặt tên cột rõ ràng để tránh phụ thuộc vào quy tắc chuyển tên mặc định.

### 4.2. Tạo `application.yml`

Thêm tệp `src/main/resources/application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:catalogdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always

logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

`spring.datasource.url` chỉ định database H2 trong bộ nhớ. `DB_CLOSE_DELAY=-1` giữ database còn tồn tại khi kết nối cuối cùng đóng, cho đến khi tiến trình Java kết thúc. `spring.sql.init.mode=always` yêu cầu Spring Boot chạy script khởi tạo SQL khi ứng dụng bắt đầu. Cấu hình log `DEBUG` giúp quan sát hoạt động của Spring JDBC; nếu log quá nhiều có thể bỏ phần `logging`.

**Spring Data JDBC không tự tạo bảng theo `@Table` giống một số cách cấu hình Hibernate/JPA.** Ta phải cung cấp schema. `schema.sql` tiện cho bài học; dự án production thường quản lý thay đổi schema bằng Flyway hoặc Liquibase.

## 5. Viết aggregate root `Book`

Tạo `src/main/java/com/example/catalog/domain/Book.java`:

~~~java
package com.example.catalog.domain;

import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public record Book(
        @Id Long id,
        String title,
        BigDecimal price
) {

    public Book {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tên sách không được để trống");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Giá sách phải >= 0");
        }
        title = title.strip();
    }

    public static Book newBook(String title, BigDecimal price) {
        return new Book(null, title, price);
    }

    public Book changePrice(BigDecimal newPrice) {
        return new Book(id, title, newPrice);
    }
}
~~~

### Hiểu từng thành phần

**`@Table("books")`** chỉ định bảng lưu aggregate root. Annotation đến từ `org.springframework.data.relational.core.mapping.Table`, không phải `jakarta.persistence.Table`.

**`@Id`** đánh dấu thuộc tính định danh. Với `Long id`, giá trị `null` trong mô hình hiện tại biểu thị một aggregate mới chưa được insert; ID được database sinh sau khi lưu. Annotation dùng là `org.springframework.data.annotation.Id`.

**Record `Book`** cung cấp sẵn các accessor `id()`, `title()`, `price()` và biểu diễn dữ liệu bất biến. Spring Data JDBC có khả năng ánh xạ object bất biến, bao gồm Java record. Bởi vậy, việc cập nhật giá tạo ra một đối tượng `Book` mới thay vì gọi setter.

**Compact constructor** áp dụng quy tắc nghiệp vụ cho mọi `Book` được tạo: tên phải có nội dung và giá không âm. Quy tắc này nằm trong aggregate, nên cả `newBook` và `changePrice` đều phải tuân thủ.

**`newBook`** tạo đối tượng chưa có ID. **`changePrice`** giữ ID cũ nhưng tạo trạng thái mới để repository có thể lưu.

Lưu ý: kiểm tra Java trong constructor **không thay thế** ràng buộc database. Ở đây, cả class và bảng đều bảo vệ điều kiện quan trọng theo cách phù hợp với phạm vi của mỗi bên.

### Vì sao chọn `BigDecimal`?

`BigDecimal` biểu diễn giá trị thập phân chính xác:

~~~java
BigDecimal price = new BigDecimal("149000.00");
~~~

Tránh dùng `new BigDecimal(0.1)` vì giá trị `double` có thể mang sai số nhị phân. Khi xử lý tiền thật, còn cần thống nhất đơn vị tiền, quy tắc làm tròn, thuế và độ chính xác lưu trữ.

## 6. Tạo repository đầu tiên

Tạo `src/main/java/com/example/catalog/repository/BookRepository.java`:

~~~java
package com.example.catalog.repository;

import java.util.Optional;
import com.example.catalog.domain.Book;
import org.springframework.data.repository.CrudRepository;

public interface BookRepository extends CrudRepository<Book, Long> {

    Optional<Book> findByTitle(String title);
}
~~~

Chỉ vài dòng đã có repository cho aggregate `Book`. Hai kiểu generic có ý nghĩa:

- `Book`: kiểu **aggregate root** mà repository quản lý.
- `Long`: kiểu khóa chính tương ứng với `@Id Long id`.

`CrudRepository` cung cấp các phương thức thường dùng:

| Phương thức | Mục đích | Dạng kết quả |
|---|---|---|
| `save(Book entity)` | Tạo mới hoặc lưu lại aggregate | `Book` |
| `findById(Long id)` | Tìm theo khóa chính | `Optional<Book>` |
| `findAll()` | Đọc tất cả aggregate | `Iterable<Book>` |
| `existsById(Long id)` | Kiểm tra ID có tồn tại không | `boolean` |
| `count()` | Đếm aggregate | `long` |
| `deleteById(Long id)` | Xóa theo ID | `void` |
| `delete(Book entity)` | Xóa aggregate được chỉ định | `void` |

Phương thức `findByTitle(String title)` là **derived query**. Spring Data đọc tên method, nhận thuộc tính `title` của `Book` rồi tạo truy vấn phù hợp. Không cần viết class triển khai interface, cũng không cần gắn `@Repository` trên interface vì Spring Data tạo proxy repository.

Để phương thức `findByTitle` hoạt động, tên thuộc tính phải khớp với mô hình Java. Nếu đổi `title` thành `bookName`, tên method cũng phải được chỉnh tương ứng, chẳng hạn `findByBookName`.

Trong Spring Data JDBC, repository được tạo từ hạ tầng mapping và SQL. Đây **không phải** Spring Data JPA; không sử dụng `EntityManager`, persistence context hoặc JPQL cho repository này.

## 7. Chạy ví dụ CRUD đầu tiên

Mở tệp ứng dụng chính và sử dụng nội dung sau trong `src/main/java/com/example/catalog/CatalogApplication.java`:

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import com.example.catalog.domain.Book;
import com.example.catalog.repository.BookRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrateRepository(BookRepository repository) {
        return args -> {
            // 1. CREATE: đối tượng mới có id == null.
            Book newBook = Book.newBook(
                "Spring Data JDBC căn bản",
                new BigDecimal("149000.00")
            );
            Book saved = repository.save(newBook);
            System.out.println("CREATED: " + saved);

            // 2. READ: tìm theo khóa chính.
            Book found = repository.findById(saved.id())
                .orElseThrow();
            System.out.println("FOUND: " + found);

            // 3. UPDATE: tạo trạng thái mới, gọi save để lưu.
            Book repriced = found.changePrice(
                new BigDecimal("129000.00")
            );
            Book updated = repository.save(repriced);
            System.out.println("UPDATED: " + updated);

            // 4. Derived query: tìm theo tên sách.
            System.out.println(
                "BY TITLE: " +
                repository.findByTitle("Spring Data JDBC căn bản")
            );

            // 5. READ ALL: phương thức kế thừa CrudRepository.
            repository.findAll().forEach(
                book -> System.out.println("IN CATALOG: " + book)
            );

            // 6. DELETE và xác nhận bằng Optional.empty().
            repository.deleteById(updated.id());
            System.out.println(
                "AFTER DELETE: " + repository.findById(updated.id())
            );
        };
    }
}
~~~

Ở thư mục gốc dự án, chạy với Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Trên macOS/Linux:

~~~bash
./mvnw spring-boot:run
~~~

Ứng dụng tạo bảng từ `schema.sql`, Spring Data tạo bean `BookRepository`, rồi Spring Boot gọi `CommandLineRunner`. Phần log của ví dụ sẽ có dạng:

~~~text
CREATED: Book[id=1, title=Spring Data JDBC căn bản, price=149000.00]
FOUND: Book[id=1, title=Spring Data JDBC căn bản, price=149000.00]
UPDATED: Book[id=1, title=Spring Data JDBC căn bản, price=129000.00]
BY TITLE: Optional[Book[id=1, title=Spring Data JDBC căn bản, price=129000.00]]
IN CATALOG: Book[id=1, title=Spring Data JDBC căn bản, price=129000.00]
AFTER DELETE: Optional.empty
~~~

ID thực tế phụ thuộc trạng thái database; ví dụ hiển thị `1` khi bảng mới được tạo. Nếu đang dùng H2 trong bộ nhớ như cấu hình trên, dữ liệu mất khi ứng dụng kết thúc. Vì dự án không thêm web server, ứng dụng minh họa có thể **chạy xong rồi thoát** — đó là hành vi bình thường.

### Dòng chảy của một lệnh `save`

~~~mermaid
flowchart LR
    A["Book.newBook(...)\nid = null"] --> B["BookRepository.save(book)"]
    B --> C["Spring Data JDBC mapping"]
    C --> D["SQL INSERT"]
    D --> E[("books")]
    E --> F["Book trả về\ncó ID được sinh"]
~~~

Đối với lần cập nhật:

~~~mermaid
flowchart LR
    A["Book đã có ID"] --> B["changePrice(...)"]
    B --> C["repository.save(...)"]
    C --> D["SQL UPDATE theo ID"]
    D --> E[("books")]
~~~

Hai sơ đồ mô tả luồng căn bản. SQL thực tế do framework sinh dựa trên metadata mapping, trạng thái aggregate và các cơ chế như versioning nếu được bổ sung.

## 8. Hiểu đúng vòng đời aggregate khi lưu

### 8.1. Phân biệt đối tượng mới và đã tồn tại

Trong mô hình `Book` đang dùng:

~~~java
Book draft = Book.newBook("Java thực hành", new BigDecimal("99000"));
System.out.println(draft.id()); // null

Book persisted = repository.save(draft);
System.out.println(persisted.id()); // ID được database sinh
~~~

Vì `Book` là record bất biến, **hãy sử dụng đối tượng trả về từ `save`**. Đừng tiếp tục giả định biến `draft` đã được gán ID.

Mặc định, Spring Data JDBC có cơ chế xác định entity mới hay đã tồn tại dựa trên ID; nếu mô hình có `@Version` thì việc xác định trạng thái mới còn liên quan đến giá trị version. Với mô hình đơn giản có `Long id`, `null` thể hiện đối tượng mới.

### 8.2. Không có dirty checking như JPA

Mệnh đề quan trọng:

~~~java
Book current = repository.findById(id).orElseThrow();
Book changed = current.changePrice(new BigDecimal("79000"));

// Trong DB vẫn là giá cũ nếu chỉ tạo 'changed'.
repository.save(changed); // Bây giờ mới yêu cầu ghi trạng thái mới.
~~~

Spring Data JDBC không “theo dõi” `current` hoặc `changed` như một managed JPA entity. Thao tác `save` là hành động lưu rõ ràng. Ngay cả khi gọi trong một phương thức `@Transactional`, việc tạo object mới trong bộ nhớ cũng không tự ghi xuống database.

### 8.3. `save` không nên được hiểu là “upsert” chung

Khi đối tượng được nhận diện là mới, framework sẽ thực hiện quy trình chèn dữ liệu; khi được nhận diện là đã tồn tại, framework thực hiện quy trình cập nhật. **Đừng kỳ vọng rằng truyền một ID bất kỳ vào `save` sẽ tự thêm hàng nếu hàng đó chưa có.** Việc hàng có tồn tại, ràng buộc database và cơ chế optimistic locking có thể khiến thao tác cập nhật thất bại.

### 8.4. Transaction ở tầng service

Repository là đơn vị truy cập dữ liệu. Khi một nghiệp vụ cần nhiều thao tác database phải thành công cùng nhau, nên đặt ranh giới transaction ở **service**:

~~~java
package com.example.catalog.service;

import java.math.BigDecimal;
import java.util.NoSuchElementException;
import com.example.catalog.domain.Book;
import com.example.catalog.repository.BookRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookCatalogService {
    private final BookRepository repository;

    public BookCatalogService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Book changePrice(long id, BigDecimal newPrice) {
        Book book = repository.findById(id)
            .orElseThrow(() ->
                new NoSuchElementException("Không tìm thấy sách: " + id));

        return repository.save(book.changePrice(newPrice));
    }
}
~~~

Đoạn service là phần mở rộng tùy chọn; nếu thêm vào dự án, tạo đúng file trong package `service`. Spring Boot tự phát hiện `@Service` dưới package gốc.

`@Transactional` bảo đảm các thao tác tương thích tham gia cùng transaction khi phương thức được gọi qua Spring bean/proxy. Trong môi trường JDBC thông thường, Spring quản lý transaction qua JDBC connection. Một phương thức gọi trực tiếp method `@Transactional` khác **trong cùng đối tượng** có thể không đi qua proxy và vì thế không kích hoạt transaction như mong đợi.

Với cập nhật đồng thời, hai tác vụ có thể cùng đọc giá cũ rồi ghi đè nhau. Khi nghiệp vụ cần phát hiện xung đột, hãy nghiên cứu thêm **`@Version` / optimistic locking** và đảm bảo bảng có cột version tương ứng. Giao dịch đơn thuần không thay thế chiến lược kiểm soát cập nhật đồng thời.

## 9. Từ một bảng đến aggregate gồm nhiều entity

Book là aggregate một bảng. Để hiểu đầy đủ tư duy Spring Data JDBC, hãy mở rộng bằng ví dụ **đơn hàng có nhiều dòng hàng**. Phần này minh họa cách thiết kế; không cần thêm vào dự án danh mục sách vừa chạy.

### 9.1. Mô hình sở hữu

~~~text
PurchaseOrder [root, bảng purchase_orders]
  └── Set<OrderLine> [children, bảng order_lines]

Quan hệ dữ liệu:

purchase_orders.id
         │
         └── order_lines.order_id
~~~

Giả sử đơn hàng chứa nhiều dòng hàng. `PurchaseOrder` là root. `OrderLine` là thành phần nằm trong aggregate: nó không được tự ý lưu bằng một repository độc lập mà bỏ qua quy tắc nghiệp vụ của đơn hàng.

### 9.2. Mapping bằng `@MappedCollection`

~~~java
import java.util.Set;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        Long customerId,
        @MappedCollection(idColumn = "order_id")
        Set<OrderLine> lines
) {
}

@Table("order_lines")
public record OrderLine(
        @Id Long id,
        String sku,
        int quantity
) {
}
~~~

Đây là **hai kiểu Java**, nên trong dự án thật hãy đặt chúng ở hai tệp `PurchaseOrder.java` và `OrderLine.java` (hoặc khai báo phù hợp với quy tắc một public top-level type trên mỗi file). Cần thêm package và import thích hợp. `OrderLine` được Spring Data JDBC ánh xạ như entity con, không cần property `orderId` trong class; `idColumn = "order_id"` chỉ định cột khóa ngoại ở bảng con.

Schema tương ứng có thể là:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INT NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
~~~

Với aggregate này, repository là:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

**Không cần tạo `OrderLineRepository`** nếu mọi thay đổi của dòng hàng đều đi qua đơn hàng. Root cần có các phương thức như `addLine`, `changeQuantity`, `removeLine` nhằm bảo vệ điều kiện nghiệp vụ; ví dụ record phía trên mới trình bày mapping, chưa xây các quy tắc đó.

Một lưu ý vận hành đáng chú ý: khi cập nhật aggregate có collection con, Spring Data JDBC có thể **xóa và chèn lại các hàng con** theo chiến lược lưu aggregate, thay vì dirty checking từng trường như JPA. Vì vậy, đừng tạo aggregate khổng lồ chỉ để ánh xạ toàn bộ bảng liên quan. Việc thiết kế ranh giới nhỏ, hợp lý giúp hành vi lưu rõ ràng và tránh thao tác SQL không cần thiết.

Nếu thứ tự dòng hàng có ý nghĩa, hãy cân nhắc kiểu `List` cùng mapping `keyColumn` và cột lưu vị trí. `Set` không hứa hẹn giữ thứ tự hiển thị.

### 9.3. Tham chiếu aggregate khác bằng ID

Trong `PurchaseOrder`, trường `customerId` là tham chiếu đến một aggregate khác. Đây thường là lựa chọn đơn giản, dễ hiểu:

~~~java
Long customerId; // Chỉ giữ định danh, không sở hữu Customer
~~~

Spring Data Relational cũng có kiểu `AggregateReference<Customer, Long>` giúp biểu diễn tham chiếu aggregate trong domain model mà không biến `Customer` thành entity con được cascade theo đơn hàng.

Không nên đặt một object `Customer` được Spring Data JDBC diễn giải như quan hệ sở hữu bên trong `PurchaseOrder` chỉ vì database có foreign key. **Foreign key là cấu trúc dữ liệu; ownership của aggregate là quyết định nghiệp vụ.** Một aggregate root khác có repository và vòng đời riêng.

## 10. Mở rộng repository khi CRUD chưa đủ

`CrudRepository` đã giải quyết các thao tác cơ bản. Khi cần câu truy vấn riêng, Spring Data JDBC hỗ trợ **derived query** hoặc SQL tường minh.

Ví dụ thêm một method vào `BookRepository`:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
       SELECT id, title, price
       FROM books
       WHERE price >= :minPrice
       ORDER BY price
       """)
List<Book> findBooksFromPrice(@Param("minPrice") BigDecimal minPrice);
~~~

Đây là **method bổ sung bên trong interface `BookRepository`**, không phải method đứng độc lập ngoài interface. SQL trong `@Query` dành cho Spring Data JDBC, trả trực tiếp các cột khớp với mapping `Book`. Tham số đặt tên `:minPrice` được gắn với `@Param("minPrice")`.

Với bài toán báo cáo có nhiều JOIN hoặc đọc thành DTO, dùng `JdbcTemplate`/`NamedParameterJdbcTemplate` cùng với Spring Data JDBC cũng là lựa chọn hợp lý. Repository quản lý aggregate, còn SQL tùy chỉnh có thể phục vụ các màn hình đọc mà không làm to một aggregate.

**Đừng thêm method query chỉ để thay cho một thao tác CRUD sẵn có:** `findById`, `findAll`, `count` và `deleteById` đã được kế thừa. Hãy để repository đầu tiên đơn giản và mở rộng theo nhu cầu thật.

## 11. Các lỗi thường gặp khi làm bài đầu tiên

| Hiện tượng | Nguyên nhân hay gặp | Cách khắc phục |
|---|---|---|
| Báo không tìm thấy bảng `BOOKS`/`books` | Chưa tạo hoặc chưa chạy `schema.sql`; sai tên bảng | Kiểm tra `src/main/resources/schema.sql`, `spring.sql.init.mode` và `@Table("books")` |
| `No qualifying bean of type BookRepository` | Chưa có starter JDBC hoặc repository ngoài vùng scan | Kiểm tra dependency và package dưới `com.example.catalog` |
| Không tạo được kết nối H2 | Thiếu dependency H2 hoặc URL/driver sai | Kiểm tra runtime dependency và `spring.datasource.url` |
| Dùng nhầm `jakarta.persistence.Id` hay `@Entity` | Trộn annotation JPA với Spring Data JDBC | Dùng `org.springframework.data.annotation.Id` và `org.springframework.data.relational.core.mapping.Table` |
| Gọi `save` nhưng biến record cũ vẫn có `id == null` | Record bất biến, giá trị được trả về là instance đã lưu | Gán `Book saved = repository.save(book)` |
| Thay đổi object nhưng database không đổi | Spring Data JDBC không có dirty checking | Gọi `repository.save(changedBook)` |
| Không cập nhật được entity có ID gán tùy ý | ID không tồn tại hoặc framework đã chọn nhánh update | Tách rõ tạo mới và cập nhật; dùng ID thực tế hoặc cấu hình chiến lược nhận diện entity mới phù hợp |
| Cập nhật aggregate lớn gây nhiều thao tác SQL | Collection con thuộc vòng đời root, có thể bị xóa/chèn lại | Thu gọn ranh giới aggregate, quan sát SQL và thiết kế thao tác ghi phù hợp |
| Dữ liệu mất khi tắt ứng dụng | Database `jdbc:h2:mem:...` chỉ tồn tại trong JVM | Dùng H2 file hoặc database bền vững nếu cần giữ dữ liệu |

### Ba câu hỏi giúp tự hiểu bài

**1. Vì sao `BookRepository` khai báo `Long`?** Vì trường `Book.id` có kiểu `Long`. Kiểu ID là một phần hợp đồng của `CrudRepository<Book, Long>`.

**2. Vì sao gọi `save` trả về đối tượng mới?** Spring Data JDBC có thể cần cung cấp ID do database sinh, version hoặc dữ liệu được chuyển đổi từ quá trình lưu. Với record bất biến, các giá trị đó được biểu diễn bằng instance trả về.

**3. Nếu `OrderLine` là entity con, có cần repository riêng?** Thông thường không. Khi dòng hàng thuộc aggregate `PurchaseOrder`, các thay đổi đi qua root và `PurchaseOrderRepository` để bảo vệ bất biến của đơn hàng.

## 12. Bước phát triển tiếp theo

Sau ví dụ đầu tiên, có thể phát triển ứng dụng theo trình tự:

1. Thêm **service** cho các nghiệp vụ đọc/ghi và `@Transactional` ở ranh giới hợp lý.
2. Thêm **HTTP controller** nếu cần cung cấp REST API; khi đó thêm `spring-boot-starter-web`.
3. Thêm **`@Version`** vào aggregate root và cột version trong bảng để tìm hiểu optimistic locking.
4. Tạo aggregate nhiều entity có `@MappedCollection`, lưu ý vòng đời và chi phí cập nhật collection con.
5. Thay H2 bằng PostgreSQL hoặc MySQL và quản lý schema bằng migration; tiếp tục dùng cùng nguyên tắc repository.
6. Viết truy vấn đọc chuyên biệt khi dữ liệu cho màn hình không trùng với ranh giới aggregate.

Điểm cần giữ lại sau bài học: **repository là cổng truy cập aggregate root**, `@Id` cung cấp danh tính ở database, `@Table` định nghĩa mapping và `save` thể hiện chủ ý lưu trạng thái. Từ một `Book` đơn giản, bạn đã có nền tảng để xây các aggregate phức tạp hơn mà vẫn giữ ranh giới nghiệp vụ và thao tác dữ liệu rõ ràng.
