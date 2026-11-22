# Metamodel tĩnh và kiểm tra tên thuộc tính trong quá trình biên dịch

Khi viết truy vấn động bằng Criteria API của Jakarta Persistence, chúng ta thường gặp cú pháp như `root.get("title")` hoặc `root.join("author")`. Cách viết này hợp lệ nhưng chứa một điểm yếu: **tên thuộc tính được truyền dưới dạng chuỗi**. Nếu entity đổi tên `title` thành `name` mà chuỗi trong Criteria không được sửa, trình biên dịch Java vẫn có thể biên dịch thành công. Lỗi chỉ xuất hiện khi Hibernate phân tích truy vấn ở runtime.

**Static metamodel (mô hình siêu dữ liệu tĩnh)** giải quyết phần lớn vấn đề đó bằng cách sinh ra các class Java đại diện cho các entity và thuộc tính đã được ánh xạ. Thay vì viết `root.get("title")`, code có thể dùng `root.get(Book_.title)`. Nếu xóa hoặc đổi tên thuộc tính trong entity và chạy lại annotation processor, biểu thức tham chiếu thành viên cũ sẽ **không còn biên dịch được**. Đồng thời, kiểu Java của đường dẫn cũng được giữ lại để compiler kiểm tra nhiều lỗi kiểu dữ liệu ngay khi build.

Bài này nằm trong chương **Criteria và truy vấn động** của Hibernate ORM, tập trung vào:

- Static metamodel khác gì so với metamodel runtime.
- Cách annotation processor tạo các class `Book_`, `Author_` và metadata có kiểu.
- Cách dùng `SingularAttribute`, `SetAttribute`, `ListAttribute` trong Criteria.
- Cách viết filter, sort, join và projection động mà không nối tên thuộc tính tùy tiện.
- Giới hạn thật sự của compile-time safety: điều gì được compiler bảo vệ và điều gì vẫn phải kiểm chứng ở runtime.
- Cấu hình build và những lỗi thường gặp khi sinh metamodel trong Hibernate 6.x.

Các ví dụ dùng `jakarta.persistence.*` và Hibernate ORM 6.x; tên artifact, processor và vị trí generated source phải tương ứng đúng phiên bản Hibernate đang dùng. Không tự chuyển code từ `javax.persistence` của dự án cũ sang `jakarta.persistence` mà chưa nâng cấp toàn bộ stack tương ứng.

## 1. Vấn đề của đường dẫn thuộc tính viết bằng chuỗi

Giả sử entity có thuộc tính `title`:

~~~java
@Entity
public class Book {
    @Id
    private Long id;

    private String title;

    private BigDecimal price;

    protected Book() {}
}
~~~

Criteria thông thường:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Book> query = cb.createQuery(Book.class);
Root<Book> book = query.from(Book.class);

query.select(book);
query.where(cb.equal(book.get("title"), "Hibernate in Action"));

List<Book> result =
        entityManager.createQuery(query).getResultList();
~~~

Đoạn code hợp lệ, nhưng compiler không thể biết chuỗi `"title"` phải khớp một thuộc tính persistent của `Book`. Nếu developer đổi tên field thành `name`:

~~~java
private String name;
~~~

mà bỏ quên query:

~~~java
book.get("title");
~~~

chương trình vẫn có thể biên dịch; tới khi chạy query, provider mới phát hiện path không tồn tại và báo lỗi tương ứng.

Vấn đề tương tự xảy ra khi:

- Đổi tên association `author` thành `writer` nhưng quên sửa `root.join("author")`.
- Viết nhầm `"createdAt"` thành `"createAt"`.
- Chuyển một field từ `String` sang `BigDecimal` nhưng code Criteria dùng kiểu `String`.
- Dùng tên cột database `"book_title"` thay vì tên thuộc tính entity `"title"`.
- Refactor bằng công cụ IDE nhưng các chuỗi tự do không được cập nhật.

Một cách viết an toàn hơn:

~~~java
book.get(Book_.title);
~~~

`Book_` được sinh từ mapping của `Book`. Tham chiếu `Book_.title` là một **thành viên Java**, nên công cụ refactor và compiler có thể tìm thấy lỗi khi class metamodel đã được tái sinh từ mapping mới.

## 2. Static metamodel là gì?

Jakarta Persistence định nghĩa một **canonical static metamodel**: mỗi managed class có thể được biểu diễn bởi một class Java mang hậu tố dấu gạch dưới `_`, thường cùng package.

Ví dụ:

~~~text
Entity source                  Static metamodel do processor sinh
com.example.catalog.Book  --> com.example.catalog.Book_
com.example.catalog.Author --> com.example.catalog.Author_
com.example.catalog.Address -> com.example.catalog.Address_
~~~

Các thuộc tính persistent được biểu diễn bởi metadata có kiểu, ví dụ:

| Entity attribute | Loại trong static metamodel | Ý nghĩa |
| --- | --- | --- |
| `Book.id: Long` | `SingularAttribute<Book, Long>` | Thuộc tính đơn, kiểu `Long` |
| `Book.title: String` | `SingularAttribute<Book, String>` | Thuộc tính đơn, kiểu `String` |
| `Book.price: BigDecimal` | `SingularAttribute<Book, BigDecimal>` | Thuộc tính đơn, kiểu `BigDecimal` |
| `Book.author: Author` | `SingularAttribute<Book, Author>` | Association to-one |
| `Book.tags: Set<String>` | `SetAttribute<Book, String>` | Collection-valued attribute |
| `Author.books: List<Book>` | `ListAttribute<Author, Book>` | Association to-many dạng list |

Các type này thuộc package `jakarta.persistence.metamodel`. Chúng **mô tả thuộc tính**, không chứa giá trị dữ liệu của một cuốn sách cụ thể.

### 2.1. Sơ đồ mối quan hệ

~~~mermaid
flowchart LR
    A["Book.java với @Entity"] --> B["javac + annotation processor"]
    B --> C["Book_.java được sinh"]
    C --> D["Criteria: root.get(Book_.title)"]
    D --> E["Java compiler kiểm tra thành viên và kiểu"]
    E --> F["Hibernate xây query từ Criteria tree"]
    F --> G["SQL theo mapping và Dialect"]
~~~

Hai tầng hoạt động độc lập về thời điểm:

1. **Build time:** processor đọc annotations/mapping và tạo Java source cho static metamodel.
2. **Runtime:** Hibernate xây persistence metamodel và dùng Criteria tree để sinh/thực thi truy vấn.

`Book_` không chạy SQL và không thay thế metadata runtime; nó cung cấp cách **tham chiếu metadata bằng type system của Java**.

## 3. Mô hình entity đầy đủ cho ví dụ

Giả sử một ứng dụng quản lý sách, tác giả và các nhãn.

### 3.1. Entity Book

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private BookStatus status;

    private Instant publishedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private Author author;

    @ElementCollection
    @CollectionTable(
        name = "book_tags",
        joinColumns = @JoinColumn(name = "book_id")
    )
    @Column(name = "tag")
    private Set<String> tags = new HashSet<>();

    protected Book() {}
}
~~~

### 3.2. Entity Author và enum

~~~java
package com.example.catalog;

import jakarta.persistence.*;

@Entity
@Table(name = "authors")
public class Author {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Author() {}
}
~~~

~~~java
package com.example.catalog;

public enum BookStatus {
    DRAFT, PUBLISHED, ARCHIVED
}
~~~

Mỗi đoạn `public` class/enum là **một file Java riêng** trong package `com.example.catalog`. Các field là private vì static metamodel được tạo từ JPA mapping, không yêu cầu public fields. Hibernate có thể dùng field access dựa vào vị trí `@Id` và các annotation.

## 4. Class Book_ được sinh có hình dạng thế nào?

Sau khi annotation processor chạy, source được sinh ra có thể trông như sau:

~~~java
// MINH HỌA; không tự sửa file được sinh.
package com.example.catalog;

import jakarta.persistence.metamodel.*;
import jakarta.persistence.*;

@StaticMetamodel(Book.class)
public abstract class Book_ {
    public static volatile SingularAttribute<Book, Long> id;
    public static volatile SingularAttribute<Book, String> title;
    public static volatile SingularAttribute<Book, BigDecimal> price;
    public static volatile SingularAttribute<Book, BookStatus> status;
    public static volatile SingularAttribute<Book, Instant> publishedAt;
    public static volatile SingularAttribute<Book, Author> author;
    public static volatile SetAttribute<Book, String> tags;
}
~~~

Đoạn trên là **hình dạng khái niệm**. Generated source thực tế có thể thêm import, annotation đánh dấu generated, string constants hoặc cấu trúc bổ sung tùy phiên bản processor; không giả định mọi field/annotation có thứ tự đúng như ví dụ.

### 4.1. Vì sao dùng hai tham số generic?

Với:

~~~java
SingularAttribute<Book, BigDecimal> price;
~~~

- `Book` là kiểu entity **sở hữu** thuộc tính.
- `BigDecimal` là kiểu Java của **giá trị** thuộc tính.

Khi gọi:

~~~java
Path<BigDecimal> pricePath = book.get(Book_.price);
~~~

compiler biết biểu thức là `Path<BigDecimal>`. Nhờ đó, API Criteria có thể kiểm tra rằng phương thức so sánh nhận giá trị tương thích.

Với collection:

~~~java
SetAttribute<Book, String> tags;
~~~

compiler biết đây là collection thuộc `Book`, có phần tử kiểu `String`. Khi join:

~~~java
SetJoin<Book, String> tagJoin =
        book.join(Book_.tags, JoinType.INNER);
~~~

kiểu của phần tử join cũng được xác định.

### 4.2. Ý nghĩa của các static fields

Field `Book_.title` không chứa tên sách của một entity. Nó là một đối tượng metadata thể hiện mapping của thuộc tính title. Provider khởi tạo metadata tĩnh trong quá trình bootstrap phù hợp.

Không viết:

~~~java
// SAI: Book_ không phải entity chứa dữ liệu.
Book_ bookMetadata = new Book_();
~~~

Không nên chỉnh sửa generated source để thêm thuộc tính. Khi mapping thay đổi, lần build tiếp theo có thể ghi đè file và làm mất sửa đổi.

### 4.3. Static metamodel có thể có name constants

Một số generator còn sinh constant chuỗi, ví dụ:

~~~java
public static final String TITLE = "title";
~~~

Có thể dùng constants đó khi một API chỉ chấp nhận String. Tuy nhiên, để tận dụng type checking tốt nhất trong Criteria, dùng **attribute metadata**:

~~~java
root.get(Book_.title);
~~~

thay vì:

~~~java
root.get(Book_.TITLE);
~~~

Cách thứ hai vẫn chuyển thành overload nhận String và có thể đánh mất một phần type safety của `SingularAttribute<Book, String>`. String constant được sinh có lợi về tránh sai chính tả, nhưng không giữ đầy đủ kiểu Java của path.

## 5. Cấu hình annotation processor trong Hibernate 6.x

Static metamodel thường được tạo ở **compile time** bởi annotation processor. Với Hibernate ORM 6.x, artifact phổ biến là `org.hibernate.orm:hibernate-jpamodelgen`; tên artifact và cơ chế xử lý có thể thay đổi ở các dòng Hibernate mới hơn. Hãy chọn version tương thích với `hibernate-core` của dự án.

### 5.1. Maven

Ví dụ dùng Java 21 và Hibernate ORM 6.6.0.Final; trong dự án thật, giữ version đồng nhất bằng dependency management/BOM hoặc properties của build:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>21</release>
        <annotationProcessorPaths>
          <path>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-jpamodelgen</artifactId>
            <version>6.6.0.Final</version>
          </path>
        </annotationProcessorPaths>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Dự án cũng cần dependency Hibernate ORM/Jakarta Persistence phù hợp để biên dịch các entity và Criteria code. `annotationProcessorPaths` xác định processor chạy lúc compilation; nó không thay thế runtime ORM dependency.

Generated source thường xuất hiện ở:

~~~text
target/generated-sources/annotations/com/example/catalog/Book_.java
~~~

Đường dẫn có thể khác theo Maven Compiler Plugin và cấu hình dự án. Không copy file đó vào thư mục source chính rồi sửa bằng tay.

### 5.2. Gradle, Java plugin

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.hibernate.orm:hibernate-core:6.6.0.Final'
    annotationProcessor 'org.hibernate.orm:hibernate-jpamodelgen:6.6.0.Final'
}
~~~

Với Gradle, generated source của Java annotation processing thường được đưa vào quá trình biên dịch và nằm ở đường dẫn dạng:

~~~text
build/generated/sources/annotationProcessor/java/main/
~~~

Nếu dùng Kotlin DSL:

~~~kotlin
plugins {
    java
}

dependencies {
    implementation("org.hibernate.orm:hibernate-core:6.6.0.Final")
    annotationProcessor("org.hibernate.orm:hibernate-jpamodelgen:6.6.0.Final")
}
~~~

Ví dụ version chỉ nhằm minh họa cấu hình cho Hibernate 6.6; không ghép processor 6.6 với runtime Hibernate 7 mà chưa kiểm tra tương thích. Nếu dự án sử dụng Gradle version catalog/BOM, hãy thay version literal bằng cơ chế quản lý dependency hiện có.

### 5.3. Maven/Gradle và JDK mới

Từ các dòng JDK mới, đặc biệt Java 23 trở đi, cách annotation processing được bật tự động đã thay đổi theo compiler và build tool. Vì vậy, nên **khai báo processor tường minh** ở build, thay vì dựa vào processor tình cờ xuất hiện trên classpath.

Ở một số cấu hình Maven có thể cần chọn chế độ annotation processing thích hợp, ví dụ `proc=full`, tùy phiên bản plugin và JDK; xem tài liệu plugin/processor đúng stack thực tế trước khi thêm tùy chọn. Với Gradle, khai báo `annotationProcessor` riêng là cách thông thường để build Java source.

### 5.4. Kotlin entities, kapt và các công cụ khác

`annotationProcessor` của Java không tự bảo đảm sinh metamodel cho entity được định nghĩa bằng Kotlin. Dự án Kotlin có thể cần **kapt** hoặc giải pháp annotation processing khác tương thích với processor và phiên bản framework; cần kiểm tra cấu hình Kotlin build. Không giả định KSP và kapt thay thế được nhau cho mọi Java annotation processor.

Khi project dùng Lombok, cần để compilation/annotation processing nhìn thấy mapping đúng; với các quy tắc JPA access, processor dựa trên metadata trong source/annotation. Thứ tự processor hoặc generated code có thể ảnh hưởng một số thiết kế; ưu tiên mapping annotations rõ ràng trong entity.

## 6. Sử dụng static metamodel trong CriteriaQuery

### 6.1. Một truy vấn tìm sách đơn giản

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.*;
import java.math.BigDecimal;
import java.util.List;

public List<Book> publishedAffordableBooks(
        EntityManager em,
        BigDecimal maximumPrice
) {
    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Book> cq = cb.createQuery(Book.class);
    Root<Book> book = cq.from(Book.class);

    Predicate published = cb.equal(
            book.get(Book_.status),
            BookStatus.PUBLISHED
    );

    Predicate affordable = cb.lessThanOrEqualTo(
            book.get(Book_.price),
            maximumPrice
    );

    cq.select(book)
      .where(cb.and(published, affordable))
      .orderBy(
          cb.asc(book.get(Book_.title)),
          cb.asc(book.get(Book_.id))
      );

    return em.createQuery(cq).getResultList();
}
~~~

Chú ý:

- `book.get(Book_.status)` là path kiểu `BookStatus`.
- `book.get(Book_.price)` là path kiểu `BigDecimal`.
- `book.get(Book_.title)` là path kiểu `String`.
- Không có chuỗi `"status"`, `"price"` hay `"title"` nằm trong các thao tác truy cập property.
- `setParameter`/Criteria parameters và việc bind giá trị vẫn hữu ích cho truy vấn động; static metamodel không thay cơ chế parameter binding.

### 6.2. Nếu đổi tên thuộc tính thì lỗi sẽ xuất hiện ở đâu?

Giả sử đổi `Book.title` thành `Book.name` và sinh lại metamodel. Class `Book_` mới có `name` thay vì `title`. Code sau:

~~~java
book.get(Book_.title);
~~~

không còn một thành viên `Book_.title` để tham chiếu, và compiler sẽ báo lỗi **cannot find symbol** (hoặc lỗi thành viên tương ứng). Đây là lợi ích quan trọng nhất so với `book.get("title")`.

**Điều kiện tiên quyết:** annotation processor phải thực sự chạy, generated source phải được cập nhật và build không dựa vào stale generated files. Nếu mã nguồn sinh cũ bị giữ lại hoặc IDE chưa refresh, bạn có thể thấy lỗi trễ hoặc biểu hiện khó hiểu.

## 7. Compiler còn giúp kiểm tra kiểu giá trị

Một static metamodel cho `Book.price` cung cấp:

~~~java
Path<BigDecimal> price = book.get(Book_.price);
~~~

Phương thức của CriteriaBuilder có generic bounds để nhận loại biểu thức tương ứng, ví dụ:

~~~java
Predicate inRange = cb.between(
        book.get(Book_.price),
        new BigDecimal("10.00"),
        new BigDecimal("50.00")
);
~~~

Compiler sẽ phát hiện nhiều kiểu mismatch khi API yêu cầu kiểu được xác định rõ ràng.

Ví dụ cố truyền `String` vào phép so sánh số:

~~~java
// LỖI KIỂU: giá trị cần tương thích BigDecimal.
Predicate invalid = cb.greaterThan(
        book.get(Book_.price),
        "100"
);
~~~

Với overload typed của CriteriaBuilder, compiler thường không tìm được phương thức phù hợp vì biểu thức `BigDecimal` và `String` không có kiểu Comparable chung phù hợp với generic contract.

### 7.1. So với dùng String path

~~~java
Path<BigDecimal> price =
        book.<BigDecimal>get("price");
~~~

Khi dùng overload nhận String, developer có thể **tự khai báo generic type** hoặc cast một cách sai mà compiler không thể kiểm tra metadata thực:

~~~java
// Có thể biên dịch, nhưng "price" thực sự là BigDecimal chứ không phải String.
Path<String> fake = book.get("price");
~~~

Lúc runtime, Hibernate/provider mới có đủ mapping để phát hiện hoặc xử lý sự không khớp. Static metamodel giảm khả năng này bằng cách để type được lấy trực tiếp từ metadata đã sinh, không phải lời hứa do caller gán.

### 7.2. Không phải mọi lỗi kiểu đều được compiler ngăn

Một số phương thức Criteria nhận `Object`, `Expression<?>` hoặc generic tương đối rộng; Java còn có raw types và unchecked casts. Vì vậy static metamodel **tăng mức độ an toàn**, không thể cam kết compiler từ chối mọi query semantically sai.

Ví dụ:

~~~java
@SuppressWarnings({"rawtypes", "unchecked"})
Path unsafePath = book.get(Book_.price);
~~~

Nếu code cố tình bỏ generic và cast không kiểm soát, lợi ích compile-time checking có thể mất. Giữ generic types xuyên suốt các helper, tránh raw `Path`/`Join` và ép kiểu không cần thiết.

## 8. Join typed: từ association sang thuộc tính của entity liên quan

Giả sử cần tìm sách theo tên tác giả:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

Join<Book, Author> author = book.join(
        Book_.author,
        JoinType.INNER
);

cq.select(book)
  .where(cb.like(
      cb.lower(author.get(Author_.name)),
      "%nguyen%"
  ));

List<Book> books = em.createQuery(cq).getResultList();
~~~

Ở đây:

- `Book_.author` là `SingularAttribute<Book, Author>`.
- `book.join(Book_.author)` trả về join có thông tin kiểu owner/target.
- `Author_.name` là `SingularAttribute<Author, String>`.
- `author.get(Author_.name)` là path kiểu `String`.

Nếu đổi `Author.name` thành `fullName`, code chứa `Author_.name` bị lỗi biên dịch sau khi metamodel được sinh lại.

### 8.1. So sánh với join dùng chuỗi

~~~java
Join<Book, Author> author = book.join("author");
Path<String> authorName = author.get("name");
~~~

Với chuỗi, cả `"author"` và `"name"` đều không được compiler đối chiếu với mapping. Bằng static metamodel, hai đường dẫn được kết nối qua các typed attributes.

### 8.2. Inner join và left join vẫn là quyết định nghiệp vụ

Static metamodel không tự quyết định có cần giữ Book chưa có Author:

~~~java
Join<Book, Author> author = book.join(
        Book_.author,
        JoinType.LEFT
);
~~~

`LEFT` giữ root rows theo semantics outer join; `INNER` chỉ giữ rows có association phù hợp. Việc chọn join type vẫn cần hiểu yêu cầu business, nullability và điều kiện WHERE. Một predicate trên entity được left-join nếu đặt sai có thể vô tình biến kết quả thành tương đương inner join.

## 9. Collection-valued attributes và typed joins

Ví dụ `Book.tags` được ánh xạ bằng `@ElementCollection Set<String>`. Static metamodel dùng `SetAttribute<Book, String>`.

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

SetJoin<Book, String> tag =
        book.join(Book_.tags, JoinType.INNER);

cq.select(book)
  .distinct(true)
  .where(cb.equal(tag, "java"));

List<Book> result = em.createQuery(cq).getResultList();
~~~

Mỗi book có thể có nhiều tag. JOIN làm một Book xuất hiện ở nhiều hàng kết quả SQL, vì vậy `distinct(true)` có thể cần thiết nếu use case đòi mỗi entity chỉ một lần.

### 9.1. Các dạng collection metadata

| Mapping Java | Metadata tĩnh thường dùng | Typed Criteria join |
| --- | --- | --- |
| `Set<Tag>` | `SetAttribute<Book, Tag>` | `SetJoin<Book, Tag>` |
| `List<OrderItem>` | `ListAttribute<Order, OrderItem>` | `ListJoin<Order, OrderItem>` |
| `Map<String, Value>` | `MapAttribute<Entity, String, Value>` | `MapJoin<Entity, String, Value>` |
| `Collection<String>` | `CollectionAttribute<Entity, String>` | `CollectionJoin<Entity, String>` |
| `ManyToOne Author` | `SingularAttribute<Book, Author>` | `Join<Book, Author>` |

Kiểu chính xác phụ thuộc declared collection type và mapping. Static metamodel cho collection biết cả loại phần tử và owner, nhưng vẫn phải hiểu SQL join multiplicity, distinct, pagination và lazy fetching.

### 9.2. Metamodel không làm collection fetch join luôn an toàn

Nếu Criteria query dùng:

~~~java
book.fetch(Book_.tags, JoinType.LEFT);
~~~

cần cân nhắc số dòng SQL, pagination và fetch nhiều collection. Static metamodel đảm bảo path tồn tại và được định kiểu, **không tự ngăn Cartesian product hay MultipleBagFetchException**.

## 10. @Embeddable và đường dẫn lồng nhau

Static metamodel cũng áp dụng cho `@Embeddable`. Giả sử một tác giả có địa chỉ:

~~~java
@Embeddable
public class Address {
    private String city;
    private String countryCode;

    protected Address() {}
}
~~~

~~~java
@Embedded
private Address address;
~~~

Nếu `Author` chứa `address`, processor có thể sinh:

~~~java
// MINH HỌA:
public static volatile SingularAttribute<Author, Address> address;
// Trong Address_:
public static volatile SingularAttribute<Address, String> city;
~~~

Truy vấn:

~~~java
Join<Book, Author> author = book.join(Book_.author);

Path<String> city =
        author.get(Author_.address).get(Address_.city);

cq.where(cb.equal(city, "Ha Noi"));
~~~

Compiler kiểm tra các thành viên `Author_.address` và `Address_.city`. Mọi member trong path phản ánh mapping Java, không phải tên cột trong `@AttributeOverride`.

**Lưu ý:** ví dụ trên chỉ minh họa các field cần thiết của Address/Author; ứng dụng thật phải có mapping và annotation import đầy đủ trong từng class.

## 11. @MappedSuperclass và thuộc tính kế thừa

Một base class dùng `@MappedSuperclass`:

~~~java
@MappedSuperclass
public abstract class AuditedEntity {
    @Column(nullable = false)
    private Instant createdAt;
}
~~~

Nếu `Book extends AuditedEntity`, processor có thể sinh `AuditedEntity_` và thiết lập quan hệ metamodel kế thừa tương ứng.

~~~java
// Truy vấn path thuộc superclass thông qua metadata.
Path<Instant> created =
        book.get(AuditedEntity_.createdAt);
~~~

Tùy cách generator biểu diễn inheritance, các field của superclass cũng có thể được truy cập thông qua type metamodel con. Điểm quan trọng là **persistent attributes kế thừa vẫn có metadata**, miễn processor thấy lớp/mapping tương ứng.

Nếu base class nằm ở module dependency khác, việc sinh/tái sử dụng static metamodel cần được thiết kế theo module compilation; module chứa entity con không tự bảo đảm processor sẽ sinh source cho một dependency đã biên dịch nếu module đó chưa có generated metadata.

## 12. Truy vấn động: kết hợp filter tùy chọn bằng metamodel

Một search endpoint có thể hỗ trợ nhiều điều kiện tùy chọn:

~~~java
public record BookFilter(
        BookStatus status,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        String titleContains,
        Set<String> requiredTags
) {}
~~~

Có thể xây predicates động nhưng vẫn giữ typed paths:

~~~java
public List<Book> searchBooks(EntityManager em, BookFilter filter) {
    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Book> cq = cb.createQuery(Book.class);
    Root<Book> book = cq.from(Book.class);

    List<Predicate> conditions = new ArrayList<>();

    if (filter.status() != null) {
        conditions.add(
                cb.equal(book.get(Book_.status), filter.status())
        );
    }

    if (filter.minPrice() != null) {
        conditions.add(
                cb.greaterThanOrEqualTo(
                        book.get(Book_.price),
                        filter.minPrice()
                )
        );
    }

    if (filter.maxPrice() != null) {
        conditions.add(
                cb.lessThanOrEqualTo(
                        book.get(Book_.price),
                        filter.maxPrice()
                )
        );
    }

    if (filter.titleContains() != null
            && !filter.titleContains().isBlank()) {
        String pattern = "%"
                + escapeLike(filter.titleContains().toLowerCase(Locale.ROOT))
                + "%";
        conditions.add(cb.like(
                cb.lower(book.get(Book_.title)),
                pattern,
                '!'
        ));
    }

    if (filter.requiredTags() != null
            && !filter.requiredTags().isEmpty()) {
        SetJoin<Book, String> tag = book.join(
                Book_.tags, JoinType.INNER
        );
        conditions.add(tag.in(filter.requiredTags()));
        cq.distinct(true);
    }

    cq.select(book);
    cq.where(conditions.toArray(Predicate[]::new));
    cq.orderBy(cb.asc(book.get(Book_.id)));

    return em.createQuery(cq).getResultList();
}
~~~

Ví dụ cần các imports `java.util.*`, `java.math.BigDecimal` và `jakarta.persistence.criteria.*`, và helper `escapeLike` nếu dùng tìm kiếm literal. Giá trị `requiredTags` minh họa semantics **ít nhất một tag thuộc tập yêu cầu**, không phải “phải có tất cả các tag”; nếu yêu cầu tất cả tags, cần query/aggregate logic khác.

### 12.1. Helper escape cho LIKE

Dấu `%` và `_` là wildcard trong LIKE. Parameter binding ngăn injection nhưng không biến wildcard thành ký tự thường. Nếu muốn tìm literal substring:

~~~java
static String escapeLike(String value) {
    return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}
~~~

Trong ví dụ ở trên, overload `cb.like(Expression<String>, String, char)` quy định escape character `'!'`. Hãy xác nhận behavior/collation và yêu cầu case-insensitive của database thực tế.

### 12.2. Dữ liệu vẫn phải được bind hoặc xử lý bằng Criteria parameters

Criteria API thường biến literal values thành JDBC parameters trong những đường thực thi Hibernate phù hợp, nhưng **không nên coi static metamodel là cơ chế chống injection cho mọi tình huống**. Khi cần kiểm soát parameter rõ ràng, dùng `ParameterExpression`:

~~~java
ParameterExpression<BigDecimal> priceParam =
        cb.parameter(BigDecimal.class, "maximumPrice");

cq.where(cb.lessThanOrEqualTo(
        book.get(Book_.price),
        priceParam
));

TypedQuery<Book> query = em.createQuery(cq);
query.setParameter("maximumPrice", maximumPrice);
~~~

Value binding và typed metadata giải quyết **hai vấn đề riêng**:

- Static metamodel: tên/path và Java type của thuộc tính.
- Parameter binding: tách giá trị dữ liệu khỏi cấu trúc truy vấn.

## 13. Sắp xếp động có kiểm soát

Không bao giờ chuyển thẳng chuỗi `request.sortBy()` vào `root.get(request.sortBy())` chỉ vì Criteria API trông có vẻ type-safe:

~~~java
// KHÔNG khuyến khích: tên field từ client không được allowlist.
cq.orderBy(cb.asc(book.get(request.sortBy())));
~~~

Đoạn trên vẫn dựa vào overload nhận String. Nếu request sai tên thuộc tính, query lỗi runtime; nếu trỏ vào thuộc tính không nên phơi bày, ứng dụng có thể cho phép sắp xếp theo dữ liệu nhạy cảm hoặc gây truy vấn tốn kém.

### 13.1. Ánh xạ API field sang static metamodel

~~~java
public enum BookSort {
    TITLE,
    PRICE,
    PUBLISHED_AT
}

public enum Direction {
    ASC,
    DESC
}
~~~

Ánh xạ vào các path được compiler kiểm tra:

~~~java
Path<?> sortPath = switch (sort) {
    case TITLE -> book.get(Book_.title);
    case PRICE -> book.get(Book_.price);
    case PUBLISHED_AT -> book.get(Book_.publishedAt);
};

Order order = direction == Direction.DESC
        ? cb.desc(sortPath)
        : cb.asc(sortPath);

cq.orderBy(order, cb.asc(book.get(Book_.id)));
~~~

Lưu ý `Order` ở đây là `jakarta.persistence.criteria.Order`, không phải entity mang tên Order. Khi dùng code trong project, chọn import/type rõ ràng để tránh trùng tên.

Mỗi nhánh `switch` chọn một metadata field có sẵn trong generated source. Nếu Book đổi tên `price`, code tham chiếu `Book_.price` không còn biên dịch sau khi processor cập nhật.

### 13.2. Vì sao vẫn cần allowlist khi đã có metamodel?

Static metamodel giúp **developer** tránh sai tên thuộc tính khi build; nó không chứng minh rằng **client** được phép dùng mọi attribute. Allowlist vẫn cần để:

- Giới hạn field mà API được phép filter/sort.
- Không cho query theo field nhạy cảm hoặc nội bộ.
- Tránh các sort path khiến DB phải join nhiều bảng ngoài ý muốn.
- Áp dụng index và giới hạn hiệu năng phù hợp.
- Giữ API contract ổn định khi entity model thay đổi.

Compile-time safety và authorization là hai lớp bảo vệ độc lập.

## 14. Projection với CriteriaQuery và metamodel

Static metamodel cũng có lợi khi chỉ lấy vài giá trị thay vì hydrate entity.

### 14.1. Scalar projection

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<String> cq = cb.createQuery(String.class);
Root<Book> book = cq.from(Book.class);

cq.select(book.get(Book_.title))
  .orderBy(cb.asc(book.get(Book_.title)));

List<String> titles = em.createQuery(cq).getResultList();
~~~

`Book_.title` cho compiler biết selection là `String`. Một `CriteriaQuery<String>` phù hợp với biểu thức được chọn.

### 14.2. DTO constructor projection

~~~java
public record BookRow(
        Long id,
        String title,
        BigDecimal price
) {}
~~~

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<BookRow> cq = cb.createQuery(BookRow.class);
Root<Book> book = cq.from(Book.class);

cq.select(cb.construct(
        BookRow.class,
        book.get(Book_.id),
        book.get(Book_.title),
        book.get(Book_.price)
));

List<BookRow> rows = em.createQuery(cq).getResultList();
~~~

Metamodel kiểm tra paths và types, nhưng việc constructor tương thích có thể được kiểm tra bởi provider khi xây/thi hành Criteria query, chứ không phải mọi trường hợp đều được Java compiler xác nhận: `cb.construct(...)` nhận các selection qua varargs. Nếu DTO constructor bị đổi tham số hoặc thứ tự, hãy có tests kiểm chứng query.

### 14.3. Count và GROUP BY

~~~java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Book> book = cq.from(Book.class);

cq.select(cb.count(book));
Long count = em.createQuery(cq).getSingleResult();
~~~

Với group:

~~~java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<Book> book = cq.from(Book.class);

cq.multiselect(
        book.get(Book_.status).alias("status"),
        cb.count(book).alias("total")
);
cq.groupBy(book.get(Book_.status));

List<Tuple> rows = em.createQuery(cq).getResultList();
~~~

Tuple giúp lấy kết quả theo alias; metamodel giữ type của các path, nhưng tên alias `"status"` và `"total"` trong Tuple vẫn là chuỗi do developer đặt, không tự được compiler đối chiếu. Static metamodel không loại bỏ mọi chuỗi trong query API.

## 15. Static metamodel và runtime metamodel khác nhau

Hibernate/Jakarta Persistence còn cung cấp **runtime metamodel**, truy cập qua:

~~~java
Metamodel runtimeMetamodel = entityManager.getMetamodel();

EntityType<Book> entityType =
        runtimeMetamodel.entity(Book.class);

SingularAttribute<? super Book, String> title =
        entityType.getSingularAttribute("title", String.class);
~~~

Đây là lookup metadata **lúc ứng dụng chạy**. Nó hữu ích cho:

- Công cụ introspection entity mappings.
- Framework tạo filter dựa trên metadata.
- Việc xử lý entity types không biết trước tại compile time.
- Kiểm tra cấu trúc mapping ở runtime.

Nhưng việc lookup theo `"title"` vẫn là string-based; nếu tên sai, lỗi chỉ lộ ra lúc runtime.

| Tiêu chí | Static metamodel | Runtime metamodel |
| --- | --- | --- |
| Nguồn | Generated Java source bởi processor | Metadata của provider lúc boot |
| Truy cập | `Book_.title` | `metamodel.entity(Book.class).getAttribute("title")` |
| Kiểm tra tên property | Java compiler sau khi sinh lại source | Runtime |
| Thông tin type | Generic metadata Java | Runtime metadata, có generic API |
| Phù hợp | Criteria viết sẵn trong source, refactoring | Framework introspection, dynamic tooling |
| Phụ thuộc build processor | Có | Không cần generator tĩnh |
| Có thay thế metadata runtime không? | Không | Là metadata runtime của provider |

Trong Criteria, static metamodel là **đầu vào typed để xây expression**. Hibernate vẫn dùng runtime metamodel, query parser/semantic model và Dialect để tạo SQL.

## 16. Giới hạn thực tế của compile-time safety

Static metamodel rất hữu ích nhưng cần hiểu chính xác nó bảo vệ đến đâu.

### 16.1. Những lỗi thường bị phát hiện lúc biên dịch

- Không còn `Book_.title` sau khi đổi tên field và sinh lại metamodel.
- Dùng một `SingularAttribute` thuộc sai owner type ở phương thức có generic constraints.
- Dùng sai collection attribute type khi gọi overload typed của `join`.
- Gán `Path<BigDecimal>` vào `Path<String>`.
- Dùng generic overload không nhận được sự kết hợp kiểu đường dẫn/giá trị.
- Tham chiếu class metamodel bị xóa hoặc đổi package.

### 16.2. Những lỗi không nhất thiết bị compiler phát hiện

- Tên cột hoặc bảng database đã thay đổi nhưng migration chưa chạy.
- Thiếu index, SQL chậm hoặc Cartesian product.
- Transaction isolation hoặc locking không đúng.
- Nullability, dữ liệu bẩn hoặc constraint vi phạm.
- Phương thức Criteria nhận `Object`/raw type nên cho phép kiểu sai.
- Constructor DTO có thứ tự/kiểu không khớp trong `cb.construct`.
- Alias/parameter name dùng chuỗi nhưng sai ở runtime.
- Filter logic dùng AND thay OR hoặc thiếu tenant/authorization predicate.
- Mối quan hệ `LEFT JOIN` bị filter ở WHERE theo cách làm mất null rows.
- Dialect không hỗ trợ function/cast/operator được chọn.
- Mapping lỗi do processor không thấy đầy đủ cấu hình XML hoặc convention runtime.

**Kết luận:** static metamodel làm giảm lỗi truy cập property và type mismatch, nhưng không thể thay thế integration tests, schema migrations, SQL profiling hay security review.

## 17. Mối liên hệ với JPQL/HQL thuần chuỗi

Static metamodel chủ yếu phục vụ **Criteria API**. Một HQL string:

~~~java
em.createQuery(
    "select b from Book b where b.title = :title",
    Book.class
);
~~~

vẫn chứa `b.title` dưới dạng văn bản, và Java compiler không kiểm tra nó như `Book_.title`. Processor không tự sửa mọi HQL literal hay phát lỗi compile-time cho các path nằm trong string này.

Nếu một phần code dùng HQL thuần chuỗi và một phần dùng Criteria, static metamodel chỉ bảo vệ các call sites thực sự sử dụng generated metadata. Hibernate có thêm các giải pháp processor/validation riêng tùy phiên bản, nhưng đừng coi đó là một phần được bảo đảm bởi JPA static metamodel contract.

### 17.1. Khi nào nên giữ HQL string?

HQL string thường dễ đọc với query cố định, join/aggregate phức tạp hoặc các extension của Hibernate. Criteria + static metamodel thường hấp dẫn khi:

- Bộ filter tùy chọn thay đổi nhiều tổ hợp.
- Có nhiều path trong truy vấn động.
- Refactor entity thường xuyên.
- Cần helper tạo predicates có type tương đối rõ.
- Muốn tránh tự nối tên thuộc tính bằng String.

Không cần ép mọi query trong dự án sang Criteria chỉ để sử dụng metamodel. Chọn theo độ rõ ràng, độ ổn định và nhu cầu truy vấn.

## 18. Kết hợp static metamodel với parameter binding và bảo mật

Static metamodel **không phải cơ chế chống SQL injection tự thân**. Nó bảo vệ phần **tên/path trong code**; giá trị request vẫn cần được bind và validate.

Không làm:

~~~java
// Không an toàn: ghép input thành HQL source.
String hql = "from Book b where b.title = '" + userInput + "'";
~~~

Đúng với HQL:

~~~java
em.createQuery(
        "from Book b where b.title = :title",
        Book.class
    )
    .setParameter("title", userInput)
    .getResultList();
~~~

Đúng với Criteria:

~~~java
ParameterExpression<String> titleParameter =
        cb.parameter(String.class, "title");

cq.where(cb.equal(
        book.get(Book_.title),
        titleParameter
));

TypedQuery<Book> query = em.createQuery(cq);
query.setParameter("title", userInput);
~~~

Với dynamic sorting, dùng enum/allowlist kết hợp generated attributes; không nhận raw field name. Với multi-tenant, luôn thêm predicate tenant từ security context đáng tin cậy:

~~~java
conditions.add(
        cb.equal(book.get(Book_.tenantId), currentTenantId)
);
~~~

Đoạn trên giả định `Book` thực sự có mapping `tenantId`; nếu không, processor sẽ không sinh `Book_.tenantId` và compiler sẽ báo lỗi. Điều này minh họa type safety của path, **không tự chứng minh tenant ID được lấy đúng quyền**. Không lấy tenant ID đáng tin cậy chỉ từ request body mà không xác thực.

## 19. Kiểu truy cập field/property và generated metadata

Static metamodel mô tả **persistent attributes** mà JPA mapping nhận biết, không đơn giản là mọi field Java.

Nếu `@Id` nằm trên field:

~~~java
@Id
private Long id;
~~~

JPA thường dùng **field access** mặc định cho entity. Nếu `@Id` nằm trên getter, JPA có thể dùng **property access**. `@Access(AccessType.FIELD)` và `@Access(AccessType.PROPERTY)` có thể thay đổi chiến lược theo class/attribute.

Vì vậy:

- Một field Java không persistent có thể không xuất hiện trong generated metamodel.
- Một getter được mapping với property access có thể xuất hiện dù backing field có tên khác.
- `@Transient` và các quy tắc mapping ảnh hưởng attribute set.
- Các mapping do XML override có thể ảnh hưởng metadata; processor cần được cấu hình để nhìn thấy nguồn mapping liên quan nếu dự án dùng XML phức tạp.

Đừng chỉ nhìn vào tên field Java rồi kết luận `Book_` chắc chắn có một member tương ứng. Nguồn sự thật là **JPA persistent mapping**.

## 20. Những lỗi build thường gặp

### 20.1. Compiler báo không tìm thấy Book_

Ví dụ:

~~~text
cannot find symbol
  symbol: class Book_
~~~

Nguyên nhân thường gặp:

- Chưa thêm `hibernate-jpamodelgen` vào annotation processor path.
- Annotation processing bị vô hiệu hóa trong IDE/build.
- Entity nằm ở module khác nhưng module đó chưa sinh/đóng gói metamodel.
- Mismatch `javax.persistence` và `jakarta.persistence` khi nâng cấp.
- Processor version không phù hợp runtime/JDK.
- IDE chưa nhận generated source folder trong project model.

Hướng xử lý là sửa **cấu hình compilation** và chạy lại build tạo metamodel, không tự viết tạm class `Book_` bằng tay.

### 20.2. Book_ tồn tại nhưng thiếu thuộc tính mới

Có thể processor chưa chạy lại, generated sources bị stale hoặc thuộc tính không được JPA coi là persistent. Kiểm tra annotation access, `@Transient`, module dependencies và việc generated output có thực sự được cập nhật sau thay đổi entity.

Nếu build đang dựa vào stale generated files, một thao tác refactor có thể không được phản ánh chính xác. Làm sạch generated output khi cần và bảo đảm build pipeline luôn chạy annotation processing trong môi trường CI.

### 20.3. Import nhầm javax và jakarta

Hibernate 6.x dùng Jakarta Persistence namespaces tương ứng:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.metamodel.SingularAttribute;
~~~

Một generated metamodel dùng `javax.persistence.metamodel` trong khi entity/runtime đang dùng `jakarta.persistence` có thể gây lỗi biên dịch hoặc incompatibility. Cần dùng phiên bản processor và API nhất quán thay vì sửa generated source bằng tay.

### 20.4. Source generated không đồng bộ giữa IDE và CI

IDE có thể hiển thị code compile được nhờ generated files cũ, còn CI clean build thất bại. Hoặc CI thành công nhưng IDE chưa nhận folder được sinh. Hãy để **build tool là nguồn điều phối annotation processing**, đồng bộ project model của IDE với Maven/Gradle và chạy clean compilation khi cần điều tra.

### 20.5. Generated source có nên commit vào repository không?

Thông thường source metamodel được **generate trong build**, không cần chỉnh tay hay commit nếu pipeline có processor ổn định. Một số tổ chức chọn commit generated sources vì quy trình build đặc thù; nếu làm vậy, phải có cơ chế kiểm tra generated code luôn đồng bộ với entity source. Không trộn hai nguồn source tĩnh và generated output một cách không kiểm soát.

## 21. Static metamodel trong dự án đa module

Giả sử kiến trúc:

~~~text
catalog-domain/
  src/main/java/.../Book.java
  src/main/java/.../Author.java

catalog-query/
  src/main/java/.../BookQueryService.java
~~~

Module `catalog-query` dùng `Book_.title`, vì vậy module `catalog-domain` cần sinh và xuất bản class `Book_` tương ứng trong compiled artifact hoặc có chiến lược generation nhất quán.

Không nhất thiết để query module tự sinh static metamodel cho entity class đã biên dịch trong dependency; Java annotation processing thường làm việc trên source được biên dịch trong module hiện tại. Thiết kế ownership rõ:

- Module chứa entity chịu trách nhiệm cấu hình processor.
- Generated metamodel được biên dịch vào artifact của module đó.
- Module query phụ thuộc artifact chứa cả entity và metamodel.
- CI luôn build đúng thứ tự module/dependency.
- Khi đổi entity property, build lại module domain rồi module query để compiler phát hiện references cũ.

Nếu dùng JPMS `module-info.java`, còn phải kiểm tra module path, annotation processor path và visibility/exports phù hợp.

## 22. Lựa chọn giữa String path, static metamodel và DSL khác

| Tiêu chí | `root.get("title")` | `root.get(Book_.title)` | DSL/codegen khác |
| --- | --- | --- | --- |
| Cấu hình ban đầu | Ít | Cần annotation processor | Tùy công cụ |
| Compiler phát hiện đổi tên field | Không với string literal | Có, sau khi regenerate | Thường có nếu codegen/type-safe |
| Java type của path | Có thể do caller gán sai | Theo generated metadata | Tùy DSL |
| Dynamic filters | Có | Có | Tùy DSL |
| Cần biết JPA mapping | Có ở runtime | Có cả lúc generate/build | Tùy |
| Hỗ trợ refactoring | Hạn chế với chuỗi | Tốt hơn | Thường tốt |
| Đảm bảo SQL/index/authorization đúng | Không | Không | Không tự động |
| Phù hợp | Query nhỏ, code tạm, introspection runtime | Criteria source ổn định, nhiều refactor | Khi hệ sinh thái dự án cần DSL chuyên biệt |

Static metamodel là một công cụ mạnh trong **JPA Criteria API**, nhưng không phải cách duy nhất để viết truy vấn type-safe. Quan trọng hơn lựa chọn công cụ là có hợp đồng query rõ, sử dụng đúng path metadata, bind giá trị an toàn và kiểm chứng semantics.

## 23. Một ví dụ end-to-end: service tìm kiếm có filter, join và sort

Giả sử một API cần tìm sách xuất bản theo ngưỡng giá, tên tác giả và thứ tự sort.

~~~java
public record BookSearch(
        BookStatus status,
        BigDecimal minimumPrice,
        String authorName
) {}

public enum SortBy {
    TITLE, PRICE, PUBLISHED_AT
}
~~~

Một phương thức service:

~~~java
public List<Book> search(
        EntityManager em,
        BookSearch filter,
        SortBy sortBy,
        boolean descending,
        int page,
        int pageSize
) {
    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Book> cq = cb.createQuery(Book.class);
    Root<Book> book = cq.from(Book.class);

    List<Predicate> predicates = new ArrayList<>();

    if (filter.status() != null) {
        predicates.add(
                cb.equal(book.get(Book_.status), filter.status())
        );
    }

    if (filter.minimumPrice() != null) {
        predicates.add(
                cb.greaterThanOrEqualTo(
                        book.get(Book_.price),
                        filter.minimumPrice()
                )
        );
    }

    if (filter.authorName() != null
            && !filter.authorName().isBlank()) {
        Join<Book, Author> author =
                book.join(Book_.author, JoinType.INNER);
        predicates.add(
                cb.equal(author.get(Author_.name), filter.authorName())
        );
    }

    Path<?> sortPath = switch (sortBy) {
        case TITLE -> book.get(Book_.title);
        case PRICE -> book.get(Book_.price);
        case PUBLISHED_AT -> book.get(Book_.publishedAt);
    };

    cq.select(book)
      .where(predicates.toArray(Predicate[]::new))
      .orderBy(
          descending ? cb.desc(sortPath) : cb.asc(sortPath),
          cb.asc(book.get(Book_.id))
      );

    int size = Math.min(Math.max(pageSize, 1), 100);
    int safePage = Math.max(page, 0);
    long offset = (long) safePage * size;

    if (offset > Integer.MAX_VALUE) {
        throw new IllegalArgumentException("Page offset too large");
    }

    return em.createQuery(cq)
            .setFirstResult((int) offset)
            .setMaxResults(size)
            .getResultList();
}
~~~

Đây là ví dụ thiết kế:

- Các filter có thể bật/tắt nhưng property paths đều là typed metadata.
- Tên tác giả được truy cập thông qua typed join.
- Sort field chỉ lấy từ enum allowlist.
- Thứ tự có ID làm tie-breaker.
- Pagination được giới hạn và kiểm tra overflow.
- Code không nhận HQL fragments trực tiếp từ client.

Các import cần thiết gồm `java.util.*`, `java.math.BigDecimal`, `jakarta.persistence.*`, `jakarta.persistence.criteria.*` và các class domain. Đối với ứng dụng multi-tenant, vẫn phải thêm tenant predicate server-side hoặc cơ chế tenant isolation đúng theo cấu hình; ví dụ này không tự bao hàm authorization.

## 24. Câu hỏi tự kiểm tra

1. Khi đổi tên `Book.title` thành `Book.name`, vì sao `root.get(Book_.title)` có thể gây lỗi biên dịch trong khi `root.get("title")` không?
2. `SingularAttribute<Book, BigDecimal>` biểu diễn hai kiểu generic nào?
3. Có thể dùng `Book_.price` để lấy giá trị price của một object Book cụ thể bằng cách đọc static field không? Vì sao?
4. Khi nào dùng `SetAttribute` thay vì `SingularAttribute`?
5. Static metamodel được sinh ở build time hay lúc thực thi truy vấn?
6. Với Hibernate 6.x, vai trò của `hibernate-jpamodelgen` là gì và vì sao cần khai báo annotation processor path?
7. Tại sao `root.get(Book_.TITLE)` (constant String) không đem lại cùng mức type safety như `root.get(Book_.title)`?
8. `Book_.author` và `Author_.name` phối hợp thế nào trong typed join?
9. Static metamodel có tự ngăn một query thiếu tenant filter hoặc dùng sai transaction isolation không?
10. Vì sao `cb.construct(BookRow.class, ...)` chưa chắc phát hiện mọi lỗi constructor ngay tại compile time?
11. Một field trong entity được đánh dấu `@Transient` có xuất hiện như persistent attribute trong generated metamodel không?
12. Nếu một module chứa entity và một module khác chứa Criteria queries, module nào nên chịu trách nhiệm sinh `Book_`?
13. Một ứng dụng nhận sort field từ HTTP request. Vì sao vẫn cần enum/allowlist dù đã có static metamodel?
14. Khi generated metamodel bị stale, những dấu hiệu nào có thể xuất hiện trong IDE/CI?
15. So sánh static metamodel với `EntityManager.getMetamodel()` về thời điểm và kiểu kiểm tra.

**Gợi ý:** (1) Java member reference được kiểm tra sau khi codegen; chuỗi không được compiler hiểu là property; (2) owner entity và Java attribute value; (3) không, field là metadata; (4) collection-valued Set; (5) build time; (6) processor tạo source metamodel; (7) overload String mất generic type của attribute; (8) join từ Book sang Author rồi get typed name; (9) không, đó là semantics/authorization; (10) varargs selection và provider resolution; (11) không; (12) module sở hữu entity; (13) để giới hạn quyền và độ phức tạp; (14) class/field thiếu, import cũ, IDE/CI khác nhau; (15) static compile-time so với introspection runtime.

## 25. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): Criteria, entity mapping và persistence metamodel.
- [Hibernate ORM 6.6 Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/): API Criteria/Hibernate và tooling tương ứng phiên bản.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): tài liệu metamodel generator/tooling theo phiên bản ORM sử dụng.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): canonical static metamodel, Criteria API, Metamodel API và portable persistence contract.
- [Jakarta Persistence API Javadocs](https://jakarta.ee/specifications/persistence/): `SingularAttribute`, `SetAttribute`, `CriteriaBuilder`, `Root` và `Join`.

**Điểm cần ghi nhớ:** metamodel tĩnh biến các đường dẫn thuộc tính của Criteria từ **chuỗi chỉ được kiểm tra khi chạy** thành **tham chiếu Java có kiểu được kiểm tra khi biên dịch**. Cần sinh và cập nhật `Book_` đúng cách bằng annotation processing, dùng các metadata fields thay vì tên chuỗi, và giữ generic types xuyên suốt query. Nhưng compile-time safety chỉ bảo vệ một phần: vẫn phải bind values, allowlist dynamic sort/filter, xác thực quyền, quản lý schema, và đo SQL/hiệu năng trên database thực tế.
