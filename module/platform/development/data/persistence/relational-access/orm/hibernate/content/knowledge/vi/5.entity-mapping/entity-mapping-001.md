# Điều kiện để một lớp Java trở thành thực thể được Hibernate quản lý

Trong Java, một lớp có thể biểu diễn bất kỳ khái niệm nào: đơn hàng, khách hàng, giá trị tiền, DTO trả về API hoặc lớp dịch vụ. Nhưng **không phải lớp nào cũng là thực thể (entity)** để Hibernate lưu, đọc và theo dõi trong cơ sở dữ liệu quan hệ.

Muốn một lớp trở thành thực thể JPA/Hibernate, cần đáp ứng **điều kiện về cấu trúc lớp**, có **định danh và metadata ánh xạ**, đồng thời được **đăng ký vào mô hình persistence**. Ngay cả khi lớp đã là entity hợp lệ, **mỗi đối tượng cụ thể chỉ được Hibernate theo dõi khi nó đang ở trạng thái managed trong một persistence context**.

Bài học này dùng Jakarta Persistence (JPA) với Hibernate ORM. Ví dụ dùng namespace `jakarta.persistence.*` thường gặp trong Hibernate 6+ và các ứng dụng Spring Boot hiện đại. Ứng dụng cũ có thể dùng `javax.persistence.*`; cần chọn namespace phù hợp với phiên bản thực tế.

## 1. Phân biệt lớp Java, entity class và managed entity instance

Xét một lớp bình thường:

~~~java
public class Book {
    private Long id;
    private String title;

    public Book(String title) {
        this.title = title;
    }
}
~~~

Lớp trên mới mô tả một kiểu dữ liệu Java. Hibernate chưa có đủ thông tin để biết đây là entity, đâu là khóa chính, có cần ánh xạ sang bảng nào và phải khởi tạo đối tượng bằng cách nào.

Khi bổ sung metadata:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Book {
    @Id
    private Long id;

    private String title;

    protected Book() {
    }

    public Book(Long id, String title) {
        this.id = id;
        this.title = title;
    }
}
~~~

`Book` trở thành một **ứng viên entity** hợp lệ về những đặc điểm cơ bản. Tuy nhiên, còn phải đưa lớp này vào **persistence unit** hoặc cơ chế bootstrap Hibernate tương ứng. Cuối cùng, một lệnh như `find()` hay `persist()` sẽ đưa **một instance** vào phạm vi quản lý của `EntityManager`/`Session`.

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Lớp Java thông thường | `class Book` | Chỉ có định nghĩa kiểu Java |
| Entity class | `@Entity class Book` có `@Id`, constructor phù hợp | Mô tả kiểu đối tượng có định danh, có thể ánh xạ quan hệ |
| Registered/mapped entity | `Book` xuất hiện trong metadata của factory | Hibernate biết cách quản lý và truy vấn lớp này |
| Transient/new instance | `new Book(...)` | Đối tượng mới, chưa được persistence context quản lý |
| Managed instance | Instance trả về từ `em.find()`, hoặc được `em.persist()` | Hibernate theo dõi thay đổi của đối tượng trong context hiện tại |
| Detached instance | Entity từng managed nhưng context đã đóng hoặc bị tách | Vẫn là đối tượng thuộc entity class, nhưng không còn được theo dõi bởi context cũ |

**“Là entity” nói về lớp và ánh xạ; “đang managed” nói về một đối tượng tại một thời điểm.** Hai ý này cần được tách rõ khi đọc lỗi Hibernate.

## 2. Điều kiện cốt lõi của một entity theo Jakarta Persistence

Với lối sử dụng JPA chuẩn, các yêu cầu thường gặp là:

1. Lớp được khai báo là entity qua `@Entity` hoặc metadata XML tương đương.
2. Có định danh: một khóa chính được ánh xạ bằng `@Id`, `@EmbeddedId` hoặc cơ chế khóa ghép phù hợp; định danh có thể được kế thừa từ lớp cha được ánh xạ.
3. Có constructor **không tham số** với mức truy cập `public` hoặc `protected`.
4. Là **top-level class** hoặc **static nested class**. Nó không phải non-static inner class.
5. Lớp entity không được là `final`; các phương thức và trường instance bền vững (persistent) theo ràng buộc JPA cũng không được `final`.
6. Entity phải phù hợp cơ chế truy cập thuộc tính (*field access* hoặc *property access*) mà metadata đang dùng.
7. Lớp phải được provider nhận diện trong phạm vi persistence unit đang khởi tạo.

Đó là các điều kiện **để mô hình ánh xạ có thể được quản lý**. Để chạy thực tế, ứng dụng còn cần dependency JPA/Hibernate, cấu hình nguồn dữ liệu, bảng/cột tương ứng hoặc cơ chế tạo schema, và transaction đúng cho thao tác ghi.

Cần phân biệt chuẩn JPA với khả năng riêng của Hibernate: Hibernate có thể chấp nhận một số trường hợp không hoàn toàn di động, chẳng hạn constructor package-private hoặc một số lớp `final` ở các cấu hình nhất định. Nhưng những ngoại lệ ấy có thể hạn chế proxy/lazy loading và không nên là mẫu mặc định khi viết ứng dụng JPA.

## 3. `@Entity`: khai báo lớp sẽ được ánh xạ

Cách rõ nhất để khai báo một entity qua annotation:

~~~java
package com.example.library.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {
    // Phần @Id, constructor và thuộc tính sẽ bổ sung bên dưới.
}
~~~

- `@Entity` cho provider biết lớp này đại diện cho kiểu thực thể có định danh.
- `@Table(name = "books")` chọn bảng SQL. **`@Table` không bắt buộc**: nếu bỏ qua, provider dùng tên bảng mặc định, có thể chịu ảnh hưởng của chiến lược đặt tên.
- Có thể đặt tên entity riêng qua `@Entity(name = "LibraryBook")`. Tên này dùng trong JPQL/HQL; tên bảng do `@Table` quyết định.

Ví dụ:

~~~java
@Entity(name = "LibraryBook")
@Table(name = "books")
public class Book {
    // ...
}
~~~

Truy vấn JPQL sử dụng **tên entity**:

~~~java
List<Book> books = em.createQuery(
    "select b from LibraryBook b",
    Book.class
).getResultList();
~~~

Trong khi đó SQL trực tiếp truy cập **tên bảng**:

~~~sql
SELECT * FROM books;
~~~

### Entity từ XML không nhất thiết phải ghi `@Entity`

Chuẩn Jakarta Persistence cũng hỗ trợ metadata XML. Một lớp không gắn `@Entity` vẫn có thể trở thành entity nếu được khai báo chính xác trong mapping XML và mapping đó được provider nạp vào persistence unit.

Vì vậy, câu “mọi entity đều bắt buộc phải có dòng `@Entity` trong Java” không hoàn toàn đúng. **Điều bắt buộc là Hibernate phải nhận được metadata ánh xạ entity hợp lệ** từ một nguồn được hỗ trợ.

## 4. Mỗi entity cần định danh ổn định

Hibernate phải phân biệt từng hàng dữ liệu và nhận ra khi nào hai lần truy vấn nhắc tới cùng một thực thể. Vì thế entity cần **identifier** tương ứng với khóa chính.

Ví dụ dùng khóa thay thế kiểu `Long`:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

- `@Id`: thuộc tính tham gia định danh chính.
- `@GeneratedValue`: chỉ định cơ chế sinh khóa; đây là lựa chọn phổ biến, **không phải yêu cầu bắt buộc**. Ứng dụng cũng có thể tự cấp mã định danh.
- `GenerationType.IDENTITY`: thường sử dụng cột có khả năng sinh giá trị identity tại database; có thể ảnh hưởng thời điểm Hibernate chạy `INSERT` để lấy ID.

SQL minh họa tương ứng:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);
~~~

Một đối tượng `Book` có `id = 15` có thể được ánh xạ tới hàng `books.id = 15`. Nếu có hai `Book` mang cùng giá trị khóa, Hibernate phải tôn trọng quy tắc định danh khi chúng cùng xuất hiện trong một persistence context.

### Các cách khai báo khóa

| Tình huống | Annotation | Khi sử dụng |
| --- | --- | --- |
| Khóa đơn | `@Id` | Một thuộc tính duy nhất định danh entity |
| Khóa sinh tự động | `@Id` + `@GeneratedValue` | Cơ sở dữ liệu hoặc provider tạo khóa |
| Khóa ghép trong lớp ID | `@EmbeddedId` | Nhiều trường tạo một giá trị ID nhúng |
| Khóa ghép với ID class | `@IdClass` và nhiều `@Id` | Ánh xạ khóa ghép theo lớp định danh riêng |
| Khóa trong mapped superclass | `@Id` ở lớp cha `@MappedSuperclass` | Entity con kế thừa ánh xạ ID |

Không cần tự thêm `@Id` mới vào từng lớp con nếu khóa đã được kế thừa đúng từ mô hình cha.

Ví dụ kế thừa ID:

~~~java
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
public abstract class IdentifiedEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    protected Long id;

    public Long getId() {
        return id;
    }
}
~~~

~~~java
import jakarta.persistence.Entity;

@Entity
public class Category extends IdentifiedEntity {
    private String name;

    protected Category() {
    }

    public Category(String name) {
        this.name = name;
    }
}
~~~

`Category` là entity; `IdentifiedEntity` là **mapped superclass**, bản thân nó không trở thành entity độc lập để truy vấn như `Category`. Định danh của `Category` được cung cấp qua lớp cha.

**Không nên nhầm `@Id` với `@Column(unique = true)`.** Một thuộc tính unique không tự thay thế vai trò định danh entity. ID của Hibernate và ràng buộc PK/FK thật ở database cần thống nhất với nhau.

## 5. Constructor không tham số để ORM khởi tạo đối tượng

Hibernate cần khả năng tạo đối tượng khi đọc dữ liệu từ bảng hoặc thực hiện những thao tác nội bộ. Với entity JPA chuẩn, lớp phải có constructor **không tham số**, mức truy cập `public` hoặc `protected`.

~~~java
@Entity
public class Author {
    @Id
    private Long id;

    private String name;

    protected Author() {
        // Constructor dành cho JPA/Hibernate.
    }

    public Author(Long id, String name) {
        this.id = id;
        this.name = name;
    }
}
~~~

Constructor không tham số **không bắt buộc phải public**: `protected` thường được ưu tiên để hạn chế mã nghiệp vụ tự khởi tạo entity không hợp lệ.

Java chỉ tự thêm constructor không tham số mặc định nếu lớp **không khai báo bất kỳ constructor nào**. Nếu bạn đã viết:

~~~java
public Author(String name) {
    this.name = name;
}
~~~

thì Java không tự tạo `Author()`. Cần khai báo tường minh constructor không tham số.

### Trường hợp kế thừa

Nếu entity kế thừa từ một lớp cha, chuỗi gọi constructor cũng phải hợp lệ theo quy tắc Java. Constructor không tham số của entity có thể gọi `super()`; lớp cha phải có constructor phù hợp để mã biên dịch.

Trong Hibernate, một số cơ chế có thể tạo instance bằng kỹ thuật riêng, nhưng dựa vào đó làm entity không còn đáp ứng JPA chuẩn sẽ giảm tính di động và có thể gây lỗi khi thay provider hoặc cách tạo proxy.

## 6. Tránh `final` đối với entity và thuộc tính persistent

JPA yêu cầu entity class không phải `final` và không dùng các persistent instance field hoặc method dạng `final`. Lý do kỹ thuật quan trọng là Hibernate thường có thể sử dụng **proxy subclass** và kỹ thuật bytecode để hỗ trợ nạp dữ liệu và quản lý trạng thái.

Ví dụ nên tránh cho entity JPA:

~~~java
@Entity
public final class Book {
    // final class: không đáp ứng yêu cầu entity chuẩn JPA.
}
~~~

Với entity thông dụng, ưu tiên:

~~~java
@Entity
public class Book {
    @Id
    private Long id;

    private String title;

    protected Book() {
    }
}
~~~

Các lưu ý liên quan:

- Một số chiến lược proxy của Hibernate cần khả năng kế thừa entity và ghi đè phương thức phù hợp. `final` có thể khiến proxy không hoạt động và làm thay đổi cách lazy loading.
- Bản thân một lớp `record` của Java là `final` và thiết kế theo cấu trúc bất biến; nó không phải lựa chọn thông thường cho JPA entity. `record` phù hợp hơn với DTO hoặc, trong một số phiên bản Hibernate, các kiểu value mapping được hỗ trợ riêng.
- Lớp entity có thể là `abstract` nếu mô hình kế thừa yêu cầu. **Abstract** không đồng nghĩa với **final**.
- Entity không nên là enum hoặc interface: JPA entity là lớp có thể được quản lý theo quy tắc của persistence provider.

Trong các dự án dùng Kotlin, data class mặc định thường là `final`; việc áp dụng entity cần quan tâm plugin mở lớp và constructor theo quy ước của Kotlin/JPA. Với Java, cách đơn giản nhất là viết entity dạng class thông thường.

## 7. Hibernate phải biết đọc và ghi các thuộc tính ra sao

Entity có thể dùng hai chiến lược truy cập chính.

### 7.1. Field access: annotation trên field

~~~java
@Entity
@Access(AccessType.FIELD)
public class Book {
    @Id
    private Long id;

    @Column(nullable = false)
    private String title;

    protected Book() {
    }

    public String getTitle() {
        return title;
    }
}
~~~

Trong field access, Hibernate đọc/ghi **trực tiếp vào field** theo metadata. Các field persistent có thể để `private`; getter và setter **không phải điều kiện bắt buộc** để Hibernate ánh xạ những field đó. Getter/setter vẫn hữu ích cho API nghiệp vụ của ứng dụng.

Nếu không khai báo `@Access`, vị trí của `@Id` hoặc `@EmbeddedId` trên field thường xác định cách truy cập mặc định tương ứng trong phạm vi ánh xạ.

### 7.2. Property access: annotation trên getter

~~~java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
@Access(AccessType.PROPERTY)
public class Magazine {
    private Long id;
    private String name;

    protected Magazine() {
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    protected void setName(String name) {
        this.name = name;
    }
}
~~~

Ở property access, Hibernate tương tác thông qua **getter/setter** của thuộc tính persistent. Các phương thức truy cập phải phù hợp quy ước JavaBeans và yêu cầu JPA. Không đặt annotation trên field trong khi đang thiết kế property access nếu chưa chủ động dùng `@Access` ở phạm vi thích hợp.

| Tiêu chí | Field access | Property access |
| --- | --- | --- |
| Vị trí annotation ánh xạ | Field | Getter |
| Cách provider đọc/ghi | Trực tiếp qua field | Qua getter/setter |
| Có cần setter cho mọi field persistent? | Không | Cần phương thức cập nhật property phù hợp |
| Có thể giữ domain API ít setter public? | Thuận tiện | Cũng có thể, nhưng phải bảo đảm property access hợp lệ |
| Rủi ro thường gặp | Quên `@Transient` trên field phụ | Getter tính toán bị hiểu như persistent property |

Đừng dùng đồng thời annotation ở field và getter một cách ngẫu nhiên. Nếu muốn pha trộn, cần khai báo rõ `@Access` để loại bỏ tính mơ hồ.

### Những field không được lưu

~~~java
@Entity
public class Download {
    @Id
    private Long id;

    private String fileName; // Persistent field theo field access.

    @Transient
    private String temporaryDownloadUrl; // Không lưu vào DB.

    private transient int progressPercent; // Java transient; không persistent.

    private static int activeCounter; // Static field; không persistent.

    protected Download() {
    }
}
~~~

Annotation `@Transient` đến từ `jakarta.persistence.Transient`, khác từ khóa `transient` của Java. Trong trường hợp field access thông dụng, cả hai có thể dùng để loại trừ thuộc tính khỏi persistent state; `static` cũng không phải dữ liệu của từng entity.

## 8. Ví dụ entity hoàn chỉnh, phù hợp dùng trong thực tế

Một entity `Book` đơn giản có thông tin sách, giá bán và mã khóa:

~~~java
package com.example.library.domain;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "books")
@Access(AccessType.FIELD)
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    @Column(name = "price", nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Book() {
        // JPA/Hibernate sử dụng khi tái tạo đối tượng.
    }

    public Book(String title, BigDecimal price) {
        changeTitle(title);
        changePrice(price);
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void changeTitle(String newTitle) {
        String value = Objects.requireNonNull(newTitle).trim();
        if (value.isEmpty() || value.length() > 200) {
            throw new IllegalArgumentException("Tiêu đề không hợp lệ");
        }
        this.title = value;
    }

    public void changePrice(BigDecimal newPrice) {
        BigDecimal value = Objects.requireNonNull(newPrice);
        if (value.signum() < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
        this.price = value;
    }
}
~~~

Lớp này thể hiện các đặc điểm chính:

- Có `@Entity` và `@Table` xác định kiểu entity và bảng.
- Có `@Id` và một cách sinh khóa.
- Có constructor `protected Book()`.
- Không là `final`; field persistent không khai báo `final`.
- Dùng `@Access(AccessType.FIELD)` để Hibernate thao tác trên field riêng tư.
- Có phương thức nghiệp vụ `changeTitle()` và `changePrice()` bảo vệ quy tắc ứng dụng.
- Không yêu cầu setter public cho `id` hay mọi thuộc tính chỉ để thỏa mãn Hibernate.

Để minh họa schema PostgreSQL tương thích với ánh xạ:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0)
);
~~~

Ràng buộc database quan trọng vì nhiều đường ghi dữ liệu có thể bỏ qua kiểm tra Java. `@Column(nullable = false)` mô tả mapping và có thể ảnh hưởng DDL khi provider tạo schema, nhưng ràng buộc thực tế phải được triển khai trong database hoặc migration.

## 9. Entity hợp lệ vẫn cần được đăng ký vào persistence unit

Một class có đầy đủ `@Entity`, `@Id` và constructor chưa chắc đã được factory đang chạy quản lý.

### 9.1. Với JPA thuần: khai báo trong `persistence.xml`

Ví dụ file `src/main/resources/META-INF/persistence.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">

    <persistence-unit name="libraryPU"
                      transaction-type="RESOURCE_LOCAL">
        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>com.example.library.domain.Book</class>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/library"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="library_user"/>
            <property name="hibernate.hbm2ddl.auto"
                      value="validate"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Đây là cấu hình minh họa: database `library`, tài khoản kết nối, driver và bảng `books` cần tồn tại; mật khẩu nên được truyền qua cơ chế cấu hình runtime thích hợp, không hardcode trong tài liệu hay repository.

Phần `<class>` đăng ký tường minh `Book`. `<exclude-unlisted-classes>true</exclude-unlisted-classes>` ngăn các lớp chưa được liệt kê tham gia chỉ bởi cơ chế khám phá tự động trong phạm vi tương ứng.

Khởi tạo factory:

~~~java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("libraryPU");
~~~

Với Java SE, đường dẫn `META-INF/persistence.xml` phải nằm trên **runtime classpath**. Nếu không, provider không thể tìm persistence unit theo tên.

### 9.2. Với Spring Boot: cơ chế quét entity

Khi sử dụng Spring Boot với JPA auto-configuration, các entity nằm trong package của lớp ứng dụng chính và các package con thường được tìm thấy theo quy ước:

~~~text
com.example.library
  LibraryApplication.java
  domain/
    Book.java
~~~

Nếu entity ở package nằm ngoài phạm vi mặc định, có thể chỉ rõ:

~~~java
@SpringBootApplication
@EntityScan(basePackageClasses = Book.class)
public class LibraryApplication {
    public static void main(String[] args) {
        SpringApplication.run(LibraryApplication.class, args);
    }
}
~~~

Đây là đoạn minh họa, cần thêm import Spring Boot và `Book` tương ứng. `@EntityScan` xác định vùng tìm **entity**; nó không cùng nhiệm vụ với `@ComponentScan` (Spring bean) hoặc `@EnableJpaRepositories` (Spring Data repository).

### 9.3. Với Hibernate native: `addAnnotatedClass`

Nếu bootstrap bằng API riêng của Hibernate, cần đưa lớp vào `MetadataSources`:

~~~java
MetadataSources sources = new MetadataSources(registry)
    .addAnnotatedClass(Book.class);

Metadata metadata = sources.buildMetadata();
SessionFactory sessionFactory = metadata.buildSessionFactory();
~~~

Ở đây `registry` là `StandardServiceRegistry` đã tạo và cấu hình trước. Phần dựng/đóng registry, factory và datasource phải được quản lý ở phạm vi ứng dụng.

Không nên nhầm:

~~~java
sources.addPackage("com.example.library.domain");
~~~

với việc tự động đăng ký tất cả entity trong package. `MetadataSources.addPackage(...)` phục vụ metadata cấp package, chẳng hạn các annotation được khai báo trong `package-info.java`; nó **không thay thế** `addAnnotatedClass(Book.class)`.

### 9.4. Kiểm tra lớp đã được factory nhận diện chưa

Dùng JPA Metamodel để xem những entity thực sự được đăng ký:

~~~java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("libraryPU");

try {
    for (var entityType : emf.getMetamodel().getEntities()) {
        System.out.println(entityType.getJavaType().getName());
    }
} finally {
    emf.close();
}
~~~

Nếu `Book` có trong metadata, danh sách sẽ chứa:

~~~text
com.example.library.domain.Book
~~~

Đây là kiểm tra **entity class đã nằm trong factory**, không nói rằng đang có bao nhiêu hàng sách trong database hay instance nào đang managed.

## 10. Khi nào một đối tượng cụ thể được Hibernate quản lý?

Sự khác biệt giữa **mapped entity class** và **managed instance** thể hiện rõ qua vòng đời JPA.

~~~mermaid
stateDiagram-v2
    [*] --> New: new Book(...)
    New --> Managed: persist(...)
    Managed --> Detached: detach / clear / close context
    Detached --> Managed: merge(...) trả về bản managed
    Managed --> Removed: remove(...)
    Removed --> [*]: flush/commit xóa thành công
~~~

Sơ đồ diễn tả luồng thông dụng; `merge()` trả về **instance managed** tương ứng, không biến đối tượng detached ban đầu thành managed theo kiểu thay đổi trực tiếp trạng thái của cùng một Java object.

| Trạng thái | Mô tả | Hibernate theo dõi thay đổi? |
| --- | --- | --- |
| New/transient | Mới tạo bằng `new` | Không |
| Managed/persistent | Đang thuộc `EntityManager` hoặc `Session` hiện hành | Có, trong phạm vi persistence context |
| Detached | Từng managed nhưng đã bị tách | Không, cho tới khi hợp nhất/được xử lý trong context mới |
| Removed | Đang managed và được đánh dấu xóa | Được xử lý theo thao tác xóa khi đồng bộ |

### Từ `new` đến `persist` và `commit`

Giả sử ứng dụng đã khởi tạo `EntityManagerFactory emf` với unit `libraryPU`. Ví dụ đơn giản:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;
import java.math.BigDecimal;

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Book book = new Book(
        "Hibernate cơ bản",
        new BigDecimal("250000.00")
    );

    // Mới new: Hibernate chưa quản lý instance này.
    System.out.println(em.contains(book)); // false

    em.persist(book);

    // Sau persist: instance thuộc persistence context.
    System.out.println(em.contains(book)); // true

    tx.commit();
} catch (RuntimeException e) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw e;
} finally {
    em.close();
}
~~~

Các thời điểm cần nhớ:

1. `new Book(...)` chỉ tạo object trong JVM, không chèn hàng SQL.
2. `em.persist(book)` làm đối tượng mới trở thành managed. Hibernate sẽ đưa thao tác chèn vào quy trình đồng bộ; với chiến lược IDENTITY có thể cần `INSERT` sớm để lấy ID.
3. `flush` đồng bộ các thay đổi đang chờ tới database, nhưng chưa đồng nghĩa với commit.
4. `tx.commit()` cam kết giao dịch thành công; nếu transaction rollback thì `INSERT` chưa commit cũng bị hủy.
5. `em.close()` kết thúc persistence context; đối tượng Java còn được giữ ở biến bên ngoài sẽ không còn managed trong context vừa đóng.

Trong ví dụ resource-local ở trên, Hibernate quản lý thao tác ghi trong transaction. Với Spring, thường đặt ranh giới transaction ở service bằng `@Transactional`, thay vì tự `begin()`/`commit()`.

### Nạp dữ liệu bằng `find`

~~~java
EntityManager em = emf.createEntityManager();
try {
    Book book = em.find(Book.class, 15L);

    if (book != null) {
        System.out.println(em.contains(book)); // true
        System.out.println(book.getTitle());
    }
} finally {
    em.close();
}
~~~

`find()` trả về entity managed nếu tồn tại và context đang mở; kết quả có thể lấy từ persistence context trước khi cần query SQL. Nếu không tồn tại, `find()` trả về `null`. Một lần đọc không tự động cam kết thao tác ghi.

Trong cùng một persistence context, Hibernate/JPA bảo toàn quy tắc định danh: cùng một hàng và kiểu entity thường tương ứng cùng một instance Java managed. Hai context khác nhau có thể tạo **hai object Java khác nhau** đại diện cùng hàng SQL.

### Managed không đồng nghĩa dữ liệu đã commit

Hibernate có thể theo dõi thay đổi trên managed entity theo cơ chế *dirty checking*:

~~~java
Book book = em.find(Book.class, 15L);
book.changePrice(new BigDecimal("275000.00"));
~~~

Nếu thao tác nằm trong transaction phù hợp, Hibernate có thể phát hiện `price` đổi và phát sinh `UPDATE` khi flush. Không cần bắt buộc gọi `save()` sau từng setter của một entity đang managed. Nhưng nếu transaction rollback, dữ liệu database chưa được cam kết theo giá trị mới.

### Trường hợp detached và `merge`

Sau khi `em.close()`, instance vừa đọc vẫn là một object Java hợp lệ; tuy nhiên thay đổi nó không tự đồng bộ với database.

~~~java
Book managedCopy = em.merge(detachedBook);
// managedCopy là instance được quản lý bởi em hiện tại.
// detachedBook không đương nhiên trở thành instance managed.
~~~

Để `merge` có ý nghĩa ghi dữ liệu, cần context và transaction phù hợp. Không nên mặc định instance trả về từ `merge` là cùng tham chiếu Java với object ban đầu.

## 11. Entity, value object, DTO và class thường khác nhau

Chọn loại lớp phù hợp rất quan trọng vì **không phải mọi dữ liệu cần một entity có định danh riêng**.

| Loại lớp | Có định danh riêng trong JPA? | Cách dùng phổ biến |
| --- | --- | --- |
| `@Entity` | Có | Bản ghi có vòng đời độc lập, được EntityManager quản lý |
| `@Embeddable` | Không có định danh entity độc lập | Giá trị nhúng vào entity, ví dụ địa chỉ |
| `@MappedSuperclass` | Không phải entity độc lập | Chia sẻ field/ID ánh xạ cho các lớp entity con |
| DTO/record | Không | Truyền dữ liệu qua API, trả kết quả truy vấn, hiển thị |
| Service/repository | Không | Xử lý nghiệp vụ hoặc truy cập dữ liệu, không tự lưu thành hàng |

Ví dụ `Address` là kiểu giá trị nhúng:

~~~java
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    private String city;
    private String street;

    protected Address() {
    }

    public Address(String city, String street) {
        this.city = city;
        this.street = street;
    }
}
~~~

Entity chứa địa chỉ:

~~~java
@Entity
public class Customer {
    @Id
    private Long id;

    @Embedded
    private Address address;

    protected Customer() {
    }
}
~~~

`Address` không có khóa chính riêng; các trường của nó thường được lưu cùng hàng `Customer`. `@Embedded` lấy từ `jakarta.persistence.Embedded`.

Ví dụ DTO:

~~~java
public record BookResponse(Long id, String title) {
}
~~~

`BookResponse` thích hợp để trả kết quả qua API; không nên thêm `@Entity` chỉ vì nó chứa các trường giống bảng SQL. DTO có thể bất biến và không có constructor không tham số vì nó không tham gia vòng đời entity.

## 12. Các điểm cần chú ý với proxy và lazy loading

Hibernate có thể sử dụng proxy cho association nạp trễ. Ví dụ một hóa đơn có quan hệ:

~~~java
@Entity
public class Invoice {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    protected Invoice() {
    }
}
~~~

Khi truy cập `invoice.getCustomer()`, Hibernate có thể trả về một proxy thay vì nạp ngay toàn bộ dữ liệu của khách hàng. Việc proxy có thể hoạt động còn tùy kiểu class, phương thức, bytecode enhancement và cấu hình.

Hệ quả đối với thiết kế entity:

- Tránh `final class` và `final` trên những phương thức Hibernate cần proxy.
- Đảm bảo constructor không tham số phù hợp để provider tạo đối tượng.
- Đừng đặt tác vụ phụ thuộc dịch vụ ngoài hoặc logic nặng trong constructor không tham số.
- Tránh gọi phương thức truy cập lazy association tùy ý sau khi đóng session; khi dữ liệu cần nạp mà không còn context phù hợp, có thể gặp `LazyInitializationException`.
- Đừng nhầm “object là proxy” với “object không phải entity”. Proxy là một kỹ thuật triển khai để đại diện entity trong lúc nạp dữ liệu.

Không phải mọi association và mọi phương thức đều dùng proxy; bản thân `FetchType.LAZY` là chỉ dẫn cơ chế nạp, còn hành vi cụ thể cần xét theo cấu hình thực tế.

## 13. Lỗi hay gặp khi định nghĩa entity

### 13.1. Thiếu `@Id`

~~~java
@Entity
public class Product {
    private String sku;
    private String name;

    protected Product() {
    }
}
~~~

Hibernate không biết thuộc tính nào là định danh chính. Cần khai báo khóa:

~~~java
@Id
private String sku;
~~~

Nếu `sku` là mã do nghiệp vụ cấp thì không cần `@GeneratedValue`; ứng dụng phải bảo đảm cấp ID hợp lệ, duy nhất và ổn định. Nếu SKU có thể thay đổi, cân nhắc dùng ID thay thế và đặt unique constraint cho SKU.

### 13.2. Chỉ có constructor có tham số

~~~java
@Entity
public class Publisher {
    @Id
    private Long id;

    public Publisher(Long id) {
        this.id = id;
    }
}
~~~

Thiếu constructor không tham số hợp lệ. Thêm:

~~~java
protected Publisher() {
}
~~~

Nếu dùng Lombok `@AllArgsConstructor` hoặc `@Builder`, cần bảo đảm vẫn có constructor không tham số mức truy cập đúng với JPA (chẳng hạn cấu hình `@NoArgsConstructor(access = AccessLevel.PROTECTED)` khi phù hợp). Không nên dùng mọi annotation sinh mã tự động mà chưa hiểu cấu trúc class cuối cùng.

### 13.3. Dùng `final` hoặc `record` làm entity

~~~java
public record UserRecord(Long id, String email) {
}
~~~

`record` là kiểu dữ liệu hữu ích cho DTO, nhưng không đáp ứng trực tiếp yêu cầu entity class chuẩn JPA (tính `final` và constructor/writability). Hãy dùng class entity thông thường, còn record để mang dữ liệu đọc ra hoặc trả về API.

### 13.4. Import nhầm `javax.persistence` và `jakarta.persistence`

Một dự án dùng API/provider hiện đại có thể không nhận diện annotation của namespace cũ nếu dependency trộn phiên bản. Đối với ứng dụng Hibernate 6+ theo Jakarta Persistence, hãy dùng:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
~~~

Đồng bộ phiên bản Hibernate, framework, JPA API và mapping XML; tránh sửa ngẫu nhiên một import trong khi cả project đang dùng bộ dependency khác.

### 13.5. Quên đăng ký entity với persistence unit

Nếu class có `@Entity` nhưng `persistence.xml` đặt `<exclude-unlisted-classes>true</exclude-unlisted-classes>` mà không liệt kê class, hoặc entity nằm ngoài phạm vi quét của Spring Boot, Hibernate có thể báo `Unknown entity` hoặc `Not a managed type`.

Hướng xử lý: xác định ứng dụng đang bootstrap theo cách nào, rồi thêm class vào `<class>`, chỉnh `@EntityScan` hoặc gọi `addAnnotatedClass(...)` phù hợp.

### 13.6. Trộn field access và property access

~~~java
@Entity
public class Example {
    @Id
    private Long id; // Field access.

    private String title;

    @Column(name = "book_title")
    public String getTitle() {
        return title;
    }

    protected Example() {
    }
}
~~~

Đặt annotation cho getter giữa ánh xạ field access có thể dẫn tới metadata không như dự kiến. Nên thống nhất vị trí annotation hoặc dùng `@Access` tường minh khi cần trộn ở những thuộc tính đặc biệt.

### 13.7. Hiểu sai `equals()`, `hashCode()` và định danh

Entity thường được so sánh bằng thông tin định danh, nhưng một ID được sinh có thể chỉ xuất hiện sau `persist`/`INSERT`. Nếu `hashCode()` thay đổi khi object đang nằm trong `HashSet` hoặc `HashMap`, cấu trúc tập hợp có thể hoạt động sai.

Ngoài ra, Hibernate proxy và các trạng thái detached khiến việc so sánh entity tinh tế hơn so sánh DTO. Không nên mặc định `@Data` của Lombok là lựa chọn phù hợp cho mọi entity: nó có thể sinh `equals`/`hashCode` dựa trên nhiều thuộc tính và quan hệ, gây truy cập lazy association ngoài ý muốn hoặc vòng lặp trong quan hệ hai chiều.

### 13.8. Có annotation nhưng schema thực tế chưa phù hợp

`@Entity` và `@Column` không bảo đảm bảng/cột đã tồn tại. Nếu dùng `hibernate.hbm2ddl.auto=validate`, Hibernate kiểm tra schema và có thể báo lỗi khi khác mapping. Nếu tắt validate, lỗi có thể chỉ lộ ra khi chạy SQL.

Trong hệ thống có dữ liệu cần giữ, nên kiểm soát schema bằng migration. Tránh dùng `create` hoặc `create-drop` trên database có dữ liệu quan trọng vì các chế độ ấy có thể tạo lại hoặc xóa cấu trúc bảng.

## 14. Phân biệt ràng buộc kỹ thuật với khuyến nghị thiết kế

Một số quy tắc giúp entity dễ bảo trì nhưng **không phải điều kiện bắt buộc để Hibernate nhận diện entity**:

| Thực hành | Bắt buộc? | Giải thích |
| --- | --- | --- |
| Có `@Entity` hoặc mapping XML tương đương | Có, để định nghĩa entity mapping | Cần nguồn metadata xác định kiểu entity |
| Có khóa định danh `@Id`/`@EmbeddedId` hoặc kế thừa phù hợp | Có | Entity cần identifier |
| Constructor không tham số `public`/`protected` theo JPA | Có | JPA provider cần khởi tạo entity |
| Class không `final` theo JPA | Có | Liên quan khả năng quản lý/proxy theo chuẩn |
| Có `@Table` | Không | Có thể dùng bảng theo tên mặc định |
| Có `@Column` cho mọi field | Không | Các thuộc tính persistent thường được ánh xạ mặc định |
| Có `@GeneratedValue` | Không | Có thể tự cấp identifier |
| Có getter và setter public cho mọi field | Không, nếu field access | Hibernate có thể đọc/ghi qua field |
| Mỗi entity nằm trong package `entity` | Không | Tên package là lựa chọn tổ chức mã |
| Entity có constructor nghiệp vụ và phương thức đổi trạng thái có kiểm soát | Khuyến nghị | Giúp bảo vệ bất biến của domain |
| Không gọi cơ sở dữ liệu từ constructor | Khuyến nghị | Constructor cần đơn giản, an toàn khi ORM khởi tạo |
| Tách DTO khỏi entity dùng cho API | Khuyến nghị | Giảm phụ thuộc persistence, tránh lộ quan hệ/lazy loading |

Một điểm cần nhớ: **không có yêu cầu entity phải kế thừa một class Hibernate đặc biệt hoặc triển khai interface Hibernate nào**. Đây là ưu điểm quan trọng của mô hình POJO (*Plain Old Java Object*) với JPA.

## 15. Quan sát thực thể được quản lý bằng API chuẩn

Giả sử `Book` đã được đăng ký và `EntityManagerFactory` đã khởi tạo. Có thể quan sát cả **metadata cấp lớp** lẫn **trạng thái cấp đối tượng**:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;
import java.math.BigDecimal;

public class EntityLifecycleDemo {
    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("libraryPU");

        try {
            // Kiểm tra Book thuộc mô hình entity của factory.
            boolean registered = emf.getMetamodel()
                .getEntities()
                .stream()
                .anyMatch(type -> type.getJavaType().equals(Book.class));

            System.out.println("Registered: " + registered);

            EntityManager em = emf.createEntityManager();
            EntityTransaction tx = em.getTransaction();

            Book book = new Book(
                "Tìm hiểu JPA",
                new BigDecimal("199000.00")
            );

            try {
                System.out.println("Before persist: " + em.contains(book));

                tx.begin();
                em.persist(book);

                System.out.println("After persist: " + em.contains(book));

                tx.commit();
            } catch (RuntimeException e) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw e;
            } finally {
                em.close();
            }
        } finally {
            emf.close();
        }
    }
}
~~~

Trong đoạn trên, `Book` được hiểu là lớp đã khai báo ở mục trước và nằm trên classpath; cần import `com.example.library.domain.Book` nếu khác package. Ví dụ cần driver JDBC, cấu hình unit và schema tương ứng để chạy. Với một entity được đăng ký hợp lệ, ý nghĩa kết quả là:

~~~text
Registered: true
Before persist: false
After persist: true
~~~

Hai dòng `contains` phụ thuộc **chính instance đó và chính EntityManager đó**. `contains` không dùng để hỏi “bảng có dữ liệu hay không” hay “class đã đăng ký chưa”; vì thế mới cần thêm `getMetamodel()` khi quan sát cấu hình cấp lớp.

## 16. Câu hỏi tự luyện

**Câu 1.** Lớp Java có `@Entity` và `@Id` nhưng không được đưa vào persistence unit. Có thể gọi `em.persist(new MyEntity())` và chắc chắn Hibernate nhận diện nó không?

**Trả lời:** Không. Annotation mô tả mapping, nhưng factory hiện tại phải nạp mapping của lớp đó. Cần đăng ký hoặc quét entity đúng phạm vi.

**Câu 2.** Một entity dùng field access, tất cả các field đều `private` và không có setter public. Nó có thể hợp lệ không?

**Trả lời:** Có. Hibernate có thể truy cập field theo cơ chế field access, miễn là lớp và metadata đáp ứng các yêu cầu khác. Setter public không bắt buộc cho mọi field.

**Câu 3.** `@GeneratedValue` có phải điều kiện bắt buộc cho mọi entity không?

**Trả lời:** Không. Entity phải có identifier, nhưng khóa có thể được ứng dụng tự cấp; `@GeneratedValue` là một chiến lược sinh khóa.

**Câu 4.** Sau `new Book(...)`, nếu object thuộc lớp `@Entity`, nó đã được theo dõi thay đổi chưa?

**Trả lời:** Chưa. Object mới ở trạng thái transient. Nó trở thành managed khi được đưa vào persistence context theo thao tác hợp lệ, chẳng hạn `persist()`.

**Câu 5.** Đóng `EntityManager` xong, instance `Book` trước đó còn là object Java và có dữ liệu không?

**Trả lời:** Có. Nhưng nó không còn được persistence context đã đóng theo dõi, nên thay đổi sau đó không tự được ghi xuống database.

**Câu 6.** Một lớp `@Embeddable` có thể dùng bên trong entity. Nó có trở thành entity độc lập chỉ vì có các cột được lưu không?

**Trả lời:** Không. Nó là value type được nhúng; không có entity identity riêng chỉ bởi `@Embeddable`.

**Câu 7.** Vì sao `@EntityScan` và `@ComponentScan` trong Spring Boot không thể thay thế nhau?

**Trả lời:** Entity scan tìm lớp được JPA quản lý; component scan tìm Spring beans như service/controller/configuration. Hai cơ chế phục vụ hai mô hình quản lý khác nhau.

## 17. Sơ đồ tổng hợp: từ class đến managed object

~~~mermaid
flowchart TD
    A["Lớp Java"] --> B{"Có entity mapping hợp lệ?"}
    B -- "Không" --> X["Vẫn là lớp Java thông thường"]
    B -- "Có" --> C{"Cấu trúc/ID/constructor đáp ứng JPA?"}
    C -- "Không" --> Y["Sửa ánh xạ hoặc thiết kế lớp"]
    C -- "Có" --> D{"Được factory đăng ký hoặc khám phá?"}
    D -- "Không" --> Z["Lớp chưa thuộc mô hình persistence hiện tại"]
    D -- "Có" --> E["Mapped entity class"]
    E --> F["new Book(...)"]
    F --> G["Transient instance"]
    E --> H["find(...)"]
    H --> I["Managed instance"]
    G --> J["persist(...)"]
    J --> I
    I --> K["flush và commit trong transaction"]
    I --> L["detach / close persistence context"]
    L --> M["Detached instance"]
~~~

**Ba tầng nhận diện cần nhớ:** (1) class có mapping entity hợp lệ; (2) mapping của class nằm trong `EntityManagerFactory`/`SessionFactory` đang dùng; (3) instance cụ thể đang thuộc `EntityManager`/`Session` nào. Khi debug Hibernate, xác định chính xác đang gặp vấn đề ở tầng nào sẽ giúp tìm nguyên nhân nhanh hơn.

Với nền tảng đó, bạn có thể chuyển một POJO thành entity đúng chuẩn, biết khi nào Hibernate có thể tạo và quản lý object, và tránh những lỗi thường thấy về khóa chính, constructor, proxy, package scanning và trạng thái persistence context.
