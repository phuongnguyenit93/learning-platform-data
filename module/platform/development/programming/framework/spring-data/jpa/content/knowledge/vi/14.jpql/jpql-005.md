# Đường dẫn thuộc tính và các phép join phát sinh ngầm

## Mục tiêu

JPQL truy vấn trên entity và thuộc tính Java. Khi một thuộc tính là quan hệ tới entity khác, việc đi tiếp qua đường dẫn thuộc tính có thể khiến JPA provider tạo JOIN trong SQL. Đây là **implicit join** (join phát sinh ngầm). Hiểu quy tắc này giúp dự đoán bản ghi nào bị loại, vì sao một truy vấn bất ngờ trở thành inner join, và khi nào cần viết `JOIN` hoặc `LEFT JOIN` tường minh.

Ví dụ `b.publisher.name` đi từ entity `Book` qua quan hệ `publisher` rồi đọc thuộc tính `name`. Vì `publisher` là association tới entity khác, JPQL cần kết nối bảng tương ứng. Path navigation qua single-valued association có semantics của inner join. Nếu publisher có thể null, các book không có publisher sẽ không xuất hiện trong kết quả.

Bài này giải thích cú pháp path expression, implicit join, explicit join, collection join, `ON` và `WHERE`, fetch join, chi phí truy vấn và ví dụ Spring Data JPA chạy được.

## 1. JPQL làm việc với entity và thuộc tính Java

JPQL là ngôn ngữ truy vấn của Jakarta Persistence. Câu lệnh dùng entity name, association và persistent attributes được khai báo trong Java:

```java
@Entity
@Table(name = "books")
public class Book {
    @Id
    private Long id;

    private String title;

    @ManyToOne
    @JoinColumn(name = "publisher_id")
    private Publisher publisher;
}
```

JPQL tham chiếu `Book`, `title` và `publisher`, không tham chiếu trực tiếp tên bảng `books`, cột `title` hay cột `publisher_id`.

```jpql
select b
from Book b
where b.publisher.name = :publisherName
```

Ở đây `Book` là entity name, `b` là identification variable, `b.title` là state-field path, `b.publisher` là association path và `b.publisher.name` là path đi tiếp qua association.

Tên entity và thuộc tính phải đúng với mapping Java và phân biệt chữ hoa/chữ thường theo quy tắc JPQL. Nếu cột database tên `publisher_name` nhưng Java property là `name`, JPQL vẫn viết `p.name`.

## 2. Path expression là gì?

Path expression là đường dẫn bắt đầu từ identification variable hoặc một giá trị path hợp lệ, sau đó đi qua các thuộc tính của entity/embeddable.

| JPQL path | Ý nghĩa |
| --- | --- |
| `b.title` | Thuộc tính cơ bản `title` của Book. |
| `b.publisher` | Association từ Book tới Publisher. |
| `b.publisher.name` | Thuộc tính `name` của Publisher liên kết với Book. |
| `b.publisher.country` | Thuộc tính `country` của Publisher. |
| `b.publisher.address.city` | Đi qua Publisher rồi tới thuộc tính city trong embeddable Address. |

Đi qua một **single-valued association** như `@ManyToOne` hoặc `@OneToOne` có thể tạo implicit join. Đi qua thuộc tính của một embeddable chỉ đi trong cùng mapping object; bản thân embeddable không phải entity/table riêng nên không tạo thêm join.

Ví dụ nếu `Publisher.address` là `@Embedded Address`, path `b.publisher.address.city` cần kết nối từ Book sang Publisher, nhưng `address.city` được ánh xạ vào cột của bảng Publisher.

### Collection-valued path

Không thể tiếp tục điều hướng trực tiếp từ collection như thể nó chỉ có một entity:

```jpql
select b
from Book b
where b.reviews.comment = :comment
```

`reviews` là collection-valued association. Muốn truy cập từng review, khai báo một range variable bằng `JOIN`:

```jpql
select distinct b
from Book b
join b.reviews r
where r.comment = :comment
```

`r` đại diện cho từng Review thuộc collection `b.reviews`, nên có thể truy cập `r.comment`.

## 3. Implicit join phát sinh khi đi qua association

Giả sử entity `Book` có quan hệ `ManyToOne` tới `Publisher`. Truy vấn:

```jpql
select b
from Book b
where b.publisher.country = :country
```

điều hướng từ `b` qua association `publisher` rồi đọc `country`. Provider cần kết nối Book với Publisher. Câu SQL khái niệm có thể tương tự:

```sql
select b.id, b.title, b.publisher_id
from books b
inner join publishers p on p.id = b.publisher_id
where p.country = ?
```

JPQL không viết từ khóa `JOIN`, nhưng association path làm phát sinh join cần thiết. Với path navigation qua single-valued association, implicit join có semantics của inner join.

### Hệ quả khi association có thể null

Nếu `Book.publisher` được phép null, truy vấn `b.publisher.country = :country` không trả về book không có publisher. Không có publisher để thỏa path predicate, nên hàng đó bị loại như khi dùng inner join.

| Book | Publisher | `b.publisher.country = 'VN'` |
| --- | --- | --- |
| Spring JPA | Northwind Press, VN | Có thể khớp |
| Hibernate Deep Dive | Old House, US | Không khớp |
| Independent JPQL | Không có publisher | Bị loại bởi implicit inner join |

### Điều hướng qua nhiều association

Ví dụ `b.publisher.organization.country` đi qua hai association nếu `publisher` và `organization` đều là quan hệ entity. Provider cần kết nối các bảng tương ứng để đánh giá path. Mỗi bước association cần xem xét nullability và join semantics.

Không nên giả định path navigation luôn rẻ chỉ vì câu JPQL ngắn. Một path dài có thể tạo nhiều join và ảnh hưởng execution plan.

## 4. Khi nào nên viết JOIN tường minh?

Viết explicit join khi cần đặt alias cho entity liên quan, join tới collection, chọn `INNER JOIN` hay `LEFT JOIN` rõ ràng, thêm điều kiện `ON`, hoặc tải association bằng `JOIN FETCH`.

```jpql
select b
from Book b
join b.publisher p
where p.country = :country
```

Truy vấn này diễn đạt rõ inner join từ Book tới Publisher. Nó tương đương về ý nghĩa lọc cơ bản với path navigation `b.publisher.country`, nhưng alias `p` giúp câu truy vấn dễ mở rộng.

### INNER JOIN

`JOIN` mặc định là inner join. Chỉ những Book có Publisher phù hợp mới được giữ lại.

```jpql
select b
from Book b
join b.publisher p
where p.name like :pattern
```

### LEFT JOIN

`LEFT JOIN` giữ lại entity ở phía trái ngay cả khi không có entity liên quan. Thuộc tính của alias phía phải sẽ là null khi không có bản ghi phù hợp.

```jpql
select b
from Book b
left join b.publisher p
order by b.title
```

Truy vấn này có thể trả cả book không có publisher. Nếu thêm `where p.name = :name`, các hàng không có publisher sẽ bị loại bởi điều kiện WHERE và kết quả thực tế trở nên giống inner join cho điều kiện đó.

## 5. ON và WHERE trong LEFT JOIN

`ON` bổ sung điều kiện ngay trong phép nối. `WHERE` lọc kết quả sau khi join đã được thực hiện. Khác biệt này đặc biệt quan trọng với LEFT JOIN.

### Điều kiện trong ON

```jpql
select b
from Book b
left join b.publisher p on p.active = true
```

Book vẫn được giữ lại dù publisher không active hoặc không tồn tại; trong trường hợp không có publisher active phù hợp, phía `p` là null.

### Điều kiện trong WHERE

```jpql
select b
from Book b
left join b.publisher p
where p.active = true
```

Điều kiện WHERE loại các hàng có `p` là null. Vì vậy Book không có publisher hoặc có publisher inactive bị loại.

| Book | Publisher active? | LEFT JOIN ... ON active=true | LEFT JOIN ... WHERE active=true |
| --- | --- | --- | --- |
| Spring JPA | Có | Giữ Book và Publisher | Giữ Book |
| Hibernate Deep Dive | Không | Giữ Book, phía Publisher null | Bị loại |
| Independent JPQL | Không có Publisher | Giữ Book, phía Publisher null | Bị loại |

JPQL hỗ trợ điều kiện `ON` cho explicit association join từ Jakarta Persistence 2.1. Khi chuyển predicate giữa ON và WHERE, hãy kiểm tra lại semantics mong muốn, vì số hàng kết quả có thể thay đổi.

## 6. JOIN với collection và DISTINCT

Khi join collection, một entity root có thể xuất hiện nhiều lần trong tập kết quả quan hệ vì mỗi phần tử collection tạo một hàng join.

```jpql
select b
from Book b
join b.reviews r
where r.rating >= :minimumRating
```

Nếu một book có ba review đạt điều kiện, join tạo ba hàng cho cùng book. Nếu mục tiêu là danh sách Book duy nhất, dùng `DISTINCT`:

```jpql
select distinct b
from Book b
join b.reviews r
where r.rating >= :minimumRating
order by b.title
```

`DISTINCT` yêu cầu kết quả entity không trùng theo semantics của query. Provider/database có thể cần xử lý distinct ở SQL hoặc tầng ORM tùy mapping và truy vấn. Kiểm tra SQL và số lượng kết quả thực tế khi query join nhiều collection.

Nếu chỉ muốn kiểm tra một entity có ít nhất một phần tử collection thỏa điều kiện, có thể dùng `EXISTS` subquery để tránh nhân bản root rows:

```jpql
select b
from Book b
where exists (
    select r.id
    from Review r
    where r.book = b
      and r.rating >= :minimumRating
)
```

## 7. JOIN FETCH và implicit join không giống nhau

Implicit join phục vụ việc điều hướng path và lọc/chọn dữ liệu. Nó không có nghĩa association sẽ được khởi tạo trong entity trả về.

`JOIN FETCH` yêu cầu provider tải association cùng query:

```jpql
select b
from Book b
left join fetch b.publisher
order by b.title
```

Với association `ManyToOne` lazy, fetch join có thể giúp tránh việc phát sinh thêm một SELECT cho mỗi book khi code đọc `book.getPublisher().getName()`.

### Khi nào dùng fetch join?

- Khi biết chắc màn hình hoặc nghiệp vụ cần association và muốn tải trong một lần query.
- Khi tránh N+1 query cho quan hệ cần truy cập.
- Khi cần bảo đảm association đã được tải trước khi transaction kết thúc.

### Cẩn thận với collection fetch join

Fetch join một collection có thể nhân bản hàng root ở SQL. `select distinct b` thường cần thiết để kết quả entity không trùng.

Không nên kết hợp phân trang database với collection fetch join một cách tùy tiện. Vì một root có thể chiếm nhiều hàng join, provider có thể phải xử lý pagination trong bộ nhớ hoặc tạo cảnh báo và chi phí lớn. Với phân trang, cân nhắc query trang ID trước rồi fetch association ở query thứ hai, dùng `@EntityGraph` phù hợp hoặc projection.

Fetch join nhiều collection cùng lúc còn có thể tạo tích Descartes làm số hàng tăng rất nhanh. Chỉ tải các association thực sự cần.

## 8. Path expression, NULL và toán tử collection

Path navigation qua association có thể loại entity gốc khi association null. Nếu cần giữ entity gốc, dùng LEFT JOIN và kiểm tra alias:

```jpql
select b
from Book b
left join b.publisher p
where p is null or p.country = :country
```

JPQL có các biểu thức dành cho collection:

```jpql
select b from Book b where b.reviews is empty
```

`IS EMPTY` kiểm tra collection không có phần tử. Có thể dùng `SIZE(b.reviews)` khi cần số phần tử, hoặc `:review member of b.reviews` khi kiểm tra một entity có nằm trong collection.

```jpql
select b from Book b where size(b.reviews) >= :minimumReviews
```

`SIZE` thường cần database tính số phần tử qua subquery hoặc biểu thức tương đương. Nếu chỉ cần biết collection có phần tử thỏa predicate, `EXISTS` có thể thể hiện ý định rõ hơn.

## 9. JPQL path và Spring Data derived property path

Hai cơ chế thường dùng cùng tên thuộc tính nhưng được phân tích ở hai nơi khác nhau:

| Cơ chế | Ví dụ | Cách hoạt động |
| --- | --- | --- |
| JPQL trong `@Query` | `where b.publisher.country = :country` | JPA provider diễn giải path và tạo SQL join cần thiết. |
| Derived query method | `findByPublisherCountry(String country)` | Spring Data phân tích tên method thành query theo property path. |
| Sort runtime | `Sort.by("publisher.name")` | Spring Data kiểm tra property path và áp dụng thứ tự; path có thể cần join. |

Trong derived query, `_` có thể dùng để làm rõ ranh giới property khi tên thuộc tính gây mơ hồ, ví dụ `findByPublisher_Name`. Đây là quy tắc phân tích tên method của Spring Data, không phải cú pháp JPQL.

Khi dùng `@Query`, hãy viết JPQL đúng ngữ pháp và dùng alias/path rõ ràng. Không đưa tên cột SQL vào JPQL trừ khi query được khai báo là native SQL.

## 10. Hiệu năng và cách kiểm tra SQL

Path navigation có thể ngắn gọn nhưng không loại bỏ chi phí JOIN. Để đánh giá query:

1. Bật `logging.level.org.hibernate.SQL=DEBUG` trong môi trường phát triển để quan sát SQL.
2. Dùng `EXPLAIN` hoặc execution plan của database để xem join order, index, estimated rows và scan.
3. Kiểm tra index ở khóa ngoại và các cột lọc/sắp xếp của bảng liên quan.
4. Dùng dữ liệu có phân bố gần production, đặc biệt khi association nullable hoặc collection có nhiều phần tử.
5. Đo số query khi truy cập lazy association để phát hiện N+1.
6. So sánh implicit path, explicit join, fetch join và EXISTS theo đúng kết quả nghiệp vụ cần.

Ví dụ, query `b.publisher.country = :country` thường cần index trên `books.publisher_id` và có thể cần index trên `publishers.country`, tùy execution plan. Index phù hợp không bảo đảm query luôn nhanh nếu predicate ít chọn lọc hoặc dữ liệu lớn.

## 11. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ tạo ba book: một book có publisher Việt Nam, một book có publisher không active ở Mỹ và một book không có publisher. Truy vấn minh họa implicit join, left join, collection join, ON condition và fetch join.

### Cấu trúc dự án

```text
jpql-paths/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/jpql/
        │   ├── JpqlPathsApplication.java
        │   ├── Publisher.java
        │   ├── Book.java
        │   ├── Review.java
        │   ├── BookPublisherInfo.java
        │   ├── PublisherRepository.java
        │   ├── BookRepository.java
        │   └── DemoService.java
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
    <artifactId>jpql-paths</artifactId>
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
spring.datasource.url=jdbc:h2:mem:jpqlpaths;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Publisher.java`

```java
package com.example.jpql;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "publishers")
public class Publisher {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, length = 2)
    private String country;

    @Column(nullable = false)
    private boolean active;

    protected Publisher() {
    }

    public Publisher(String name, String country, boolean active) {
        this.name = name;
        this.country = country;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCountry() {
        return country;
    }

    public boolean isActive() {
        return active;
    }
}
```

### `Book.java`

```java
package com.example.jpql;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "publisher_id")
    private Publisher publisher;

    @OneToMany(mappedBy = "book", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<Review> reviews = new ArrayList<>();

    protected Book() {
    }

    public Book(String title, Publisher publisher) {
        this.title = title;
        this.publisher = publisher;
    }

    public void addReview(Review review) {
        reviews.add(review);
        review.setBook(this);
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Publisher getPublisher() {
        return publisher;
    }
}
```

### `Review.java`

```java
package com.example.jpql;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "book_reviews")
public class Review {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "review_text", nullable = false)
    private String comment;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "book_id", nullable = false)
    private Book book;

    protected Review() {
    }

    public Review(String comment) {
        this.comment = comment;
    }

    void setBook(Book book) {
        this.book = book;
    }
}
```

### `BookPublisherInfo.java`

```java
package com.example.jpql;

public class BookPublisherInfo {
    private final String title;
    private final String publisherName;

    public BookPublisherInfo(String title, String publisherName) {
        this.title = title;
        this.publisherName = publisherName;
    }

    public String getTitle() {
        return title;
    }

    public String getPublisherName() {
        return publisherName;
    }
}
```

### `PublisherRepository.java`

```java
package com.example.jpql;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PublisherRepository extends JpaRepository<Publisher, Long> {
}
```

### `BookRepository.java`

```java
package com.example.jpql;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookRepository extends JpaRepository<Book, Long> {
    @Query("select b from Book b "
         + "where b.publisher.country = :country order by b.title")
    List<Book> findByPublisherCountry(@Param("country") String country);

    @Query("select b from Book b "
         + "left join b.publisher p "
         + "where p.name = :name or p is null order by b.title")
    List<Book> findByPublisherNameOrNoPublisher(@Param("name") String name);

    @Query("select distinct b from Book b "
         + "join b.reviews r "
         + "where lower(r.comment) like lower(concat('%', :keyword, '%')) "
         + "order by b.title")
    List<Book> findBooksWithReviewContaining(@Param("keyword") String keyword);

    @Query("select new com.example.jpql.BookPublisherInfo(b.title, p.name) "
         + "from Book b left join b.publisher p on p.active = true "
         + "order by b.title")
    List<BookPublisherInfo> findPublisherInfoWithActivePublisher();

    @Query("select b from Book b left join fetch b.publisher order by b.title")
    List<Book> findAllWithPublisher();
}
```

Trong `findByPublisherCountry`, `b.publisher.country` là implicit join. Trong `findByPublisherNameOrNoPublisher`, join được viết tường minh để giữ book không có publisher. Query collection join dùng `distinct` để không trả lặp Book. Query DTO đặt điều kiện `p.active = true` trong ON nên vẫn trả mọi book, nhưng tên publisher là null nếu publisher không active hoặc không tồn tại.

### `DemoService.java`

```java
package com.example.jpql;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DemoService {
    private final PublisherRepository publisherRepository;
    private final BookRepository bookRepository;

    @PersistenceContext
    private EntityManager entityManager;

    public DemoService(PublisherRepository publisherRepository,
                       BookRepository bookRepository) {
        this.publisherRepository = publisherRepository;
        this.bookRepository = bookRepository;
    }

    @Transactional
    public void runDemo() {
        Publisher northwind = publisherRepository.save(
                new Publisher("Northwind Press", "VN", true));
        Publisher oldHouse = publisherRepository.save(
                new Publisher("Old House", "US", false));

        Book spring = new Book("Spring JPA", northwind);
        spring.addReview(new Review("JPQL implicit joins explained"));

        Book hibernate = new Book("Hibernate Deep Dive", oldHouse);
        hibernate.addReview(new Review("Query tuning and indexes"));

        Book independent = new Book("Independent JPQL", null);

        bookRepository.saveAll(List.of(spring, hibernate, independent));
        entityManager.flush();
        entityManager.clear();

        System.out.println("Implicit join, country VN: "
                + titles(bookRepository.findByPublisherCountry("VN")));
        System.out.println("Left join, publisher or none: "
                + titles(bookRepository.findByPublisherNameOrNoPublisher("Northwind Press")));
        System.out.println("Collection join, review contains join: "
                + titles(bookRepository.findBooksWithReviewContaining("join")));

        System.out.println("LEFT JOIN ON active publisher:");
        for (BookPublisherInfo row : bookRepository.findPublisherInfoWithActivePublisher()) {
            String publisher = row.getPublisherName() == null
                    ? "(none)" : row.getPublisherName();
            System.out.println("  " + row.getTitle() + " -> " + publisher);
        }

        System.out.println("Fetch join:");
        for (Book book : bookRepository.findAllWithPublisher()) {
            String publisher = book.getPublisher() == null
                    ? "(none)" : book.getPublisher().getName();
            System.out.println("  " + book.getTitle() + " -> " + publisher);
        }
    }

    private static String titles(List<Book> books) {
        return books.stream()
                .map(Book::getTitle)
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
    }
}
```

`flush()` đồng bộ các bản ghi xuống database; `clear()` detach các entity hiện tại để các truy vấn sau đọc lại từ database. Nhờ vậy, phần fetch join minh họa việc tải publisher cùng Book thay vì chỉ đọc lại các object đã có trong persistence context.

### `JpqlPathsApplication.java`

```java
package com.example.jpql;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JpqlPathsApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpqlPathsApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DemoService service) {
        return args -> service.runDemo();
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Phần output do ứng dụng in ra:

```text
Implicit join, country VN: Spring JPA
Left join, publisher or none: Independent JPQL, Spring JPA
Collection join, review contains join: Spring JPA
LEFT JOIN ON active publisher:
  Hibernate Deep Dive -> (none)
  Independent JPQL -> (none)
  Spring JPA -> Northwind Press
Fetch join:
  Hibernate Deep Dive -> Old House
  Independent JPQL -> (none)
  Spring JPA -> Northwind Press
```

Output trên phản ánh dữ liệu được tạo mới trong H2. Alias và SQL cụ thể có thể khác theo Hibernate version và dialect. Điều cần quan sát là implicit path `b.publisher.country` không trả `Independent JPQL` vì publisher null; explicit LEFT JOIN giữ lại hàng đó.

## 12. Lỗi thường gặp

1. **Nghĩ rằng path navigation chỉ đọc field Java:** `b.publisher.name` đi qua association và có thể tạo implicit inner join.
2. **Không hiểu vì sao entity có association null biến mất:** implicit join có semantics inner join; dùng LEFT JOIN nếu cần giữ entity gốc.
3. **Điều hướng trực tiếp qua collection:** dùng `JOIN b.reviews r` rồi truy cập `r.comment`.
4. **Đặt predicate phía phải vào WHERE sau LEFT JOIN:** các hàng null bị loại. Đặt predicate trong ON nếu muốn giữ entity bên trái.
5. **Quên DISTINCT khi join collection:** một root có thể xuất hiện nhiều lần do có nhiều phần tử liên quan.
6. **Nhầm implicit join với fetch join:** join để lọc không tự bảo đảm association được khởi tạo trong entity trả về.
7. **Fetch join collection cùng pagination:** có thể gây duplicate, pagination sai hoặc xử lý trong bộ nhớ; dùng chiến lược phân trang riêng.
8. **Dùng tên cột SQL trong JPQL:** JPQL dùng entity name và Java property; native SQL mới dùng schema table/column.
9. **Bỏ qua N+1:** query một tập Book rồi truy cập lazy Publisher có thể phát sinh thêm query nếu không fetch theo nhu cầu.

## 13. Nguyên tắc thực hành

- Dùng path navigation cho truy vấn ngắn và quan hệ single-valued khi semantics inner join là đúng.
- Viết JOIN tường minh khi cần alias, collection join, LEFT JOIN hoặc ON condition.
- Dùng LEFT JOIN để giữ entity gốc khi association có thể null.
- Đặt điều kiện đúng vị trí: ON để giới hạn hàng được ghép; WHERE để lọc kết quả cuối.
- Dùng DISTINCT hoặc EXISTS khi join collection có thể nhân bản root.
- Dùng JOIN FETCH hoặc `@EntityGraph` khi cần tải association để tránh N+1.
- Tránh phân trang trực tiếp trên collection fetch join; kiểm tra SQL và execution plan.
- Dùng đúng tên entity/property Java và kiểm thử trên database mục tiêu.

Điểm cốt lõi: **Điều hướng qua single-valued association trong JPQL có thể tạo implicit inner join; collection cần explicit join để có alias cho từng phần tử. Dùng LEFT JOIN khi cần giữ entity không có quan hệ, đặt predicate vào ON hay WHERE theo semantics mong muốn, và dùng fetch join riêng khi mục tiêu là tải association.**