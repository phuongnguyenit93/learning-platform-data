# Định nghĩa JPQL bằng @NamedQuery và @NamedQueries

## Mục tiêu

`@NamedQuery` và `@NamedQueries` cho phép khai báo JPQL có tên cố định trong metadata của entity. Thay vì viết chuỗi JPQL tại từng nơi gọi, ứng dụng định nghĩa query một lần rồi gọi lại bằng tên. Spring Data JPA cũng có thể tự tìm named query tương ứng với tên phương thức trong Repository.

- `@NamedQuery`: khai báo một JPQL query có tên.
- `@NamedQueries`: gom nhiều khai báo `@NamedQuery` trên cùng một entity.
- `EntityManager.createNamedQuery(...)`: thực thi named query trực tiếp bằng JPA.
- Spring Data JPA: tự liên kết named query với repository method theo quy ước tên.

Cách này hữu ích khi query ổn định, được dùng ở nhiều nơi hoặc cần tách phần định nghĩa truy vấn khỏi code gọi. Named query là JPQL tĩnh: tham số có thể thay đổi theo lần gọi, còn cấu trúc query được định nghĩa trước.

## 1. Named query là gì?

Named query là một truy vấn được đặt tên duy nhất trong persistence unit. Tên được dùng để tham chiếu query khi thực thi. Với `@NamedQuery`, chuỗi `query` là JPQL, nên dùng entity name và thuộc tính Java thay vì tên bảng/cột SQL.

Ví dụ entity `Book` có thuộc tính `title` và `category`:

```java
@Entity
@NamedQuery(
    name = "Book.findByTitle",
    query = "select b from Book b where b.title = :title"
)
public class Book {
    // entity fields
}
```

Trong khai báo trên:

- `name` là tên định danh của named query.
- `query` là JPQL được provider phân tích theo mapping của entity.
- `Book` là entity name.
- `b` là alias.
- `b.title` là Java property.
- `:title` là named parameter sẽ được gán giá trị lúc chạy.

`@NamedQuery` được đặt ở cấp class, thường trên entity mà query truy vấn. Đây là metadata của persistence unit, không phải annotation đặt trên method Repository.

## 2. @NamedQuery và @NamedQueries

### Khai báo một query với @NamedQuery

Nếu entity chỉ cần một named query, dùng trực tiếp `@NamedQuery`:

```java
@Entity
@Table(name = "books")
@NamedQuery(
    name = "Book.findByTitle",
    query = "select b from Book b where b.title = :title"
)
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;
}
```

### Gom nhiều query với @NamedQueries

Khi entity có nhiều truy vấn được đặt tên, dùng `@NamedQueries` làm container:

```java
@Entity
@Table(name = "books")
@NamedQueries({
    @NamedQuery(
        name = "Book.findByTitle",
        query = "select b from Book b where b.title = :title"
    ),
    @NamedQuery(
        name = "Book.findByCategory",
        query = "select b from Book b "
              + "where b.category = :category order by b.title asc"
    ),
    @NamedQuery(
        name = "Book.countByCategory",
        query = "select count(b) from Book b where b.category = :category"
    )
})
public class Book {
    // entity fields
}
```

`@NamedQueries` không tạo một loại query khác; nó chỉ cho phép khai báo nhiều `@NamedQuery` tại cùng vị trí. Mỗi query vẫn có tên riêng và nội dung JPQL riêng.

### Đặt tên query

Nên đặt tên theo quy ước dễ nhận diện:

- Bắt đầu bằng entity name, ví dụ `Book`.
- Dùng dấu chấm để tách entity và mục đích, ví dụ `Book.findByTitle`.
- Dùng tên mô tả điều kiện hoặc kết quả, ví dụ `Book.findPublishedByCategory`.
- Bảo đảm tên không trùng với named query khác trong cùng persistence unit.

Tên query phân biệt với tên method Java. Nếu muốn Spring Data tự tìm named query cho một method, phải tuân thủ quy ước liên kết được trình bày ở phần sau.

## 3. JPQL bên trong NamedQuery

JPQL truy vấn trên entity và persistent attributes:

```jpql
select b
from Book b
where b.category = :category
order by b.title asc
```

Không viết tên bảng `books` hoặc tên cột `category` theo schema nếu chúng khác với entity/property. Ví dụ cột database có thể là `book_category`, nhưng JPQL vẫn dùng `b.category` nếu thuộc tính Java tên `category`.

Named query có thể trả entity, scalar value hoặc DTO projection:

```jpql
select b from Book b where b.title = :title
```

```jpql
select count(b) from Book b where b.category = :category
```

```jpql
select new com.example.BookSummary(b.id, b.title)
from Book b
where b.category = :category
```

Với DTO constructor expression, lớp DTO phải có constructor tương ứng với thứ tự và kiểu dữ liệu của các biểu thức được chọn.

### Tham số trong JPQL

Named parameter dùng dấu hai chấm:

```jpql
select b from Book b where b.title = :title
```

Positional parameter dùng số thứ tự:

```jpql
select b from Book b where b.title = ?1
```

Chọn một kiểu tham số nhất quán trong query. Không nối chuỗi đầu vào để tạo JPQL:

```java
// Không an toàn và dễ lỗi cú pháp
String jpql = "select b from Book b where b.title = '" + title + "'";
```

Hãy bind parameter để provider xử lý giá trị và kiểu dữ liệu:

```java
query.setParameter("title", title);
```

Parameter dùng cho giá trị, không dùng để thay tên entity, tên thuộc tính, toán tử hay hướng sort. Nếu cần thay đổi cấu trúc query, dùng query khác, Criteria API, Specification hoặc cơ chế xây query có whitelist.

## 4. Thực thi named query bằng EntityManager

JPA cung cấp `createNamedQuery` để lấy query theo tên:

```java
List<Book> books = entityManager
        .createNamedQuery("Book.findByTitle", Book.class)
        .setParameter("title", "Spring Data JPA")
        .getResultList();
```

Tham số `Book.class` tạo typed query, giúp kết quả được kiểm tra kiểu ở compile time. `getResultList()` trả danh sách rỗng nếu không có hàng phù hợp.

Đối với query đếm:

```java
Long total = entityManager
        .createNamedQuery("Book.countByCategory", Long.class)
        .setParameter("category", "BOOK")
        .getSingleResult();
```

`count` luôn trả một giá trị số, kể cả khi không có hàng phù hợp; kết quả khi đó là `0`. Với query trả một entity đơn lẻ, `getSingleResult()` có thể ném `NoResultException` nếu không có kết quả hoặc `NonUniqueResultException` nếu có nhiều hơn một kết quả. Chọn API và kiểu trả về phù hợp với cardinality của query.

### Dùng query không typed

Có thể dùng overload không truyền result class:

```java
Query query = entityManager.createNamedQuery("Book.findByTitle");
query.setParameter("title", "Spring Data JPA");
List<?> results = query.getResultList();
```

Typed query thường dễ đọc và an toàn kiểu hơn khi kiểu kết quả đã biết.

## 5. Spring Data JPA tự tìm NamedQuery theo tên Repository method

Spring Data JPA có thể liên kết repository method với named query mà không cần gọi `EntityManager` trực tiếp. Quy ước tên là:

```text
<EntitySimpleName>.<repositoryMethodName>
```

Ví dụ:

```java
@NamedQuery(
    name = "Book.findByTitle",
    query = "select b from Book b where b.title = :title"
)
```

Repository:

```java
public interface BookRepository extends JpaRepository<Book, Long> {
    List<Book> findByTitle(@Param("title") String title);
}
```

Khi Spring Data xử lý `findByTitle`, nó tìm named query `Book.findByTitle`. Nếu tìm thấy, query được khai báo sẽ được sử dụng. Nếu không có named query tương ứng, Spring Data có thể chuyển sang tạo query từ tên method theo query lookup strategy đang cấu hình.

Vì vậy, nếu method là `findByCategory`, named query cần tên `Book.findByCategory`. Tên query khác dù nội dung tương tự sẽ không tự động được ghép với method.

### Dùng @Param để bind rõ tên parameter

Trong repository method, nên ghi rõ `@Param` để khớp tên parameter JPQL:

```java
List<Book> findByCategory(@Param("category") String category);
```

JPQL dùng `:category`, nên `@Param("category")` chỉ rõ đối số Java nào được bind vào tham số đó. Điều này giúp code không phụ thuộc vào việc metadata tên tham số có được giữ khi biên dịch hay không.

### Named query và @Query

Nếu repository method có `@Query`, khai báo đó được ưu tiên hơn named query cùng tên. Ví dụ:

```java
@Query("select b from Book b where b.title = :title")
List<Book> findByTitle(@Param("title") String title);
```

Method trên dùng nội dung của `@Query`. Nếu muốn dùng `@NamedQuery`, không đặt `@Query` trên cùng method.

## 6. Named query có thể dùng cho SELECT, UPDATE và DELETE

`@NamedQuery` nhận JPQL query string, không chỉ riêng SELECT. JPQL cũng có bulk UPDATE và DELETE:

```java
@NamedQuery(
    name = "Book.renameCategory",
    query = "update Book b set b.category = :target "
          + "where b.category = :source"
)
```

Thực thi bulk update bằng `executeUpdate()` trong transaction:

```java
int updated = entityManager
        .createNamedQuery("Book.renameCategory")
        .setParameter("source", "OLD")
        .setParameter("target", "BOOK")
        .executeUpdate();
```

Bulk UPDATE/DELETE chạy trực tiếp trên database và không đồng bộ từng entity đang được quản lý trong persistence context. Những entity đã load trước đó có thể giữ trạng thái cũ. Sau bulk operation, cân nhắc `entityManager.clear()` hoặc refresh các entity cần dùng tiếp; chỉ clear khi đã hiểu tác động với thay đổi chưa flush.

Thao tác bulk cần transaction phù hợp. Trong Spring, đặt ở service method `@Transactional`; không thực hiện thay đổi dữ liệu chỉ trong một luồng đọc `readOnly = true`.

## 7. Named query, native query và query động

Ba cách này phục vụ mục đích khác nhau:

| Cách | Ngôn ngữ | Khi phù hợp |
| --- | --- | --- |
| `@NamedQuery` / `@NamedQueries` | JPQL | Query ổn định, đặt tên và tái sử dụng. |
| `@NamedNativeQuery` | SQL của database | Cần tính năng SQL đặc thù, CTE, window function hoặc schema-specific syntax. |
| `@Query` / Criteria / Specification | JPQL hoặc API xây query | Query gắn với repository method hoặc có cấu trúc linh hoạt theo điều kiện. |

`@NamedQuery` không phải native SQL. Nếu query cần tên bảng/cột SQL và cú pháp riêng của database, xem xét `@NamedNativeQuery` hoặc native query phù hợp.

Named query có nội dung cố định; giá trị parameter thay đổi được nhưng không thể bind tên cột hay `ORDER BY` direction như một parameter. Với sort động hoặc bộ lọc tùy chọn phức tạp, cân nhắc `Sort`, Specification hoặc Criteria API thay vì cố ghép chuỗi JPQL.

## 8. Vòng đời và kiểm tra lỗi NamedQuery

Named query là metadata của persistence unit. JPA provider thường phân tích và kiểm tra JPQL khi khởi tạo `EntityManagerFactory`; query sai entity name, property, parameter hoặc cú pháp có thể khiến ứng dụng lỗi ngay khi khởi động.

Ưu điểm của việc phát hiện sớm là lỗi query ít có khả năng chỉ xuất hiện khi một nhánh nghiệp vụ hiếm được gọi. Tuy nhiên, việc kiểm tra đầy đủ và thời điểm phát hiện còn phụ thuộc provider.

Các quy tắc cần giữ:

- Mỗi named query có tên duy nhất trong persistence unit.
- Tên entity và property trong JPQL phải khớp mapping.
- Tên parameter trong JPQL phải khớp với `setParameter` hoặc `@Param`.
- Kiểu kết quả phải phù hợp với repository return type hoặc result class.
- Query có `ORDER BY` nếu nghiệp vụ cần thứ tự xác định.
- Tránh query quá rộng hoặc fetch nhiều quan hệ không cần thiết.

## 9. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ khai báo nhiều named query trên entity `Book`, sau đó gọi qua Spring Data repository. Dự án dùng Spring Boot 3.4.5, Java 17 và H2 in-memory database.

### Cấu trúc dự án

```text
named-query-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/namedquery/
        │   ├── NamedQueryApplication.java
        │   ├── Book.java
        │   └── BookRepository.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>named-query-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:namedqueries;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Book.java`

```java
package com.example.namedquery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.NamedQueries;
import jakarta.persistence.NamedQuery;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
@NamedQueries({
    @NamedQuery(
        name = "Book.findByTitle",
        query = "select b from Book b where b.title = :title"
    ),
    @NamedQuery(
        name = "Book.findByCategory",
        query = "select b from Book b "
              + "where b.category = :category order by b.title asc"
    ),
    @NamedQuery(
        name = "Book.countByCategory",
        query = "select count(b) from Book b where b.category = :category"
    ),
    @NamedQuery(
        name = "Book.findPublished",
        query = "select b from Book b where b.published = true order by b.title asc"
    )
})
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String title;

    @Column(nullable = false, length = 40)
    private String category;

    @Column(nullable = false)
    private boolean published;

    protected Book() {
    }

    public Book(String title, String category, boolean published) {
        this.title = title;
        this.category = category;
        this.published = published;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getCategory() {
        return category;
    }
}
```

### `BookRepository.java`

```java
package com.example.namedquery;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;

public interface BookRepository extends JpaRepository<Book, Long> {
    List<Book> findByTitle(@Param("title") String title);

    List<Book> findByCategory(@Param("category") String category);

    long countByCategory(@Param("category") String category);

    List<Book> findPublished();
}
```

Spring Data tìm các query có tên `Book.findByTitle`, `Book.findByCategory`, `Book.countByCategory` và `Book.findPublished`. Vì chúng đã được khai báo trong `@NamedQueries`, repository sử dụng JPQL tương ứng thay cho việc tạo query từ tên method.

### `NamedQueryApplication.java`

```java
package com.example.namedquery;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NamedQueryApplication {
    public static void main(String[] args) {
        SpringApplication.run(NamedQueryApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(BookRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Book("JPA Basics", "BOOK", true),
                    new Book("Spring Data JPA", "BOOK", true),
                    new Book("Hibernate Guide", "BOOK", false),
                    new Book("Java Fundamentals", "COURSE", true)
            ));
            repository.flush();

            System.out.println("Find by title: "
                    + titles(repository.findByTitle("Spring Data JPA")));
            System.out.println("Find BOOK category: "
                    + titles(repository.findByCategory("BOOK")));
            System.out.println("Count BOOK: " + repository.countByCategory("BOOK"));
            System.out.println("Published: " + titles(repository.findPublished()));
        };
    }

    private static String titles(List<Book> books) {
        return books.stream()
                .map(Book::getTitle)
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Phần output do ứng dụng in ra:

```text
Find by title: Spring Data JPA
Find BOOK category: Hibernate Guide, JPA Basics, Spring Data JPA
Count BOOK: 3
Published: JPA Basics, Java Fundamentals, Spring Data JPA
```

Kết quả được sắp xếp theo JPQL `ORDER BY` đã khai báo trong named query. Query `Book.findPublished` cho thấy repository method `findPublished()` có thể dùng named query ngay cả khi phần tên method không mô tả đầy đủ predicate JPQL.

### Gọi cùng named query trực tiếp qua EntityManager

Nếu cần dùng JPA API thay vì repository method, có thể gọi đúng named query:

```java
List<Book> books = entityManager
        .createNamedQuery("Book.findByCategory", Book.class)
        .setParameter("category", "BOOK")
        .getResultList();
```

Đây là cùng một định nghĩa JPQL trong entity; không cần chép lại chuỗi query ở Service.

## 10. Khi nào nên dùng NamedQuery?

Named query phù hợp khi:

- Một query ổn định được gọi từ nhiều vị trí.
- Muốn định nghĩa JPQL tập trung cạnh entity metadata.
- Muốn Spring Data repository tự tìm query theo quy ước tên method.
- Muốn phát hiện sớm lỗi JPQL khi persistence unit khởi tạo.
- Muốn tái sử dụng query mà không lặp chuỗi JPQL trong nhiều service.

Không nhất thiết chuyển mọi query thành named query. Với query chỉ dùng một lần, query rất động hoặc logic phụ thuộc nhiều điều kiện runtime, `@Query`, Specification hoặc Criteria API có thể dễ bảo trì hơn.

## 11. Lỗi thường gặp

1. **Sai tên named query:** repository method `findByTitle` cần tên theo quy ước `Book.findByTitle`; query tên khác sẽ không tự liên kết.
2. **Nhầm entity name với table name:** JPQL dùng entity name, không dùng tên bảng SQL.
3. **Nhầm property với column:** dùng `b.category` nếu Java property tên `category`, kể cả cột database có tên khác.
4. **Sai parameter name:** `:title` phải khớp `setParameter("title", ...)` hoặc `@Param("title")`.
5. **Đặt @Query và mong named query chạy:** `@Query` trên repository method được ưu tiên.
6. **Trùng tên query trong persistence unit:** đặt tên có namespace theo entity và mục đích.
7. **Dùng getSingleResult cho query có nhiều hàng:** chọn `getResultList`, `Optional` hoặc giới hạn kết quả phù hợp.
8. **Dùng native SQL trong @NamedQuery:** `@NamedQuery` là JPQL; native SQL cần `@NamedNativeQuery`.
9. **Thay đổi JPQL mà không kiểm tra kết quả:** chạy integration test để xác nhận parameter, kiểu trả về, thứ tự và semantics join.
10. **Bulk update làm entity trong persistence context cũ:** clear hoặc refresh có chủ đích sau `executeUpdate()`.

## 12. Kiểm thử NamedQuery

Nên có integration test khởi tạo persistence context và database thử nghiệm để xác nhận:

- Tên query được đăng ký và provider chấp nhận JPQL.
- Named parameter được bind đúng.
- Kết quả có đúng kiểu và số lượng mong đợi.
- `ORDER BY` tạo thứ tự ổn định.
- Query count trả `Long` đúng.
- Repository method thực sự tìm thấy named query theo quy ước.
- Trường hợp không có kết quả và dữ liệu biên được xử lý đúng.

Kiểm thử ở database cùng loại với production khi query phụ thuộc dialect, function, collation hoặc native feature. H2 hữu ích cho ví dụ và test nhanh nhưng không thay thế hoàn toàn integration test với database mục tiêu.

## 13. Nguyên tắc thực hành

- Dùng `@NamedQuery` cho một JPQL query và `@NamedQueries` khi cần nhiều query trên entity.
- Đặt tên theo mẫu `EntityName.methodName` khi muốn Spring Data tự liên kết repository method.
- Dùng named parameter và `@Param` để binding rõ ràng.
- Dùng `EntityManager.createNamedQuery` khi cần gọi trực tiếp từ JPA.
- Giữ query JPQL dùng entity/property Java; dùng `@NamedNativeQuery` cho SQL thuần.
- Không khai báo `@Query` trên method nếu mục tiêu là để named query được chọn.
- Chọn typed query và kiểu trả về đúng với kết quả.
- Kiểm thử query khi khởi động và qua integration test với dữ liệu đại diện.

Điểm cốt lõi: **`@NamedQuery` đặt tên cho một JPQL query; `@NamedQueries` gom nhiều query trên entity. EntityManager gọi query bằng tên, còn Spring Data JPA có thể tự tìm query theo mẫu `EntityName.repositoryMethodName`. Tham số được bind lúc chạy, nhưng cấu trúc JPQL vẫn được định nghĩa trước.**