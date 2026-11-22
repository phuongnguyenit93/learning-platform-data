# Chọn lọc phương thức bằng RepositoryDefinition và interface cơ sở

## Mục tiêu

Spring Data JPA cho phép một Repository chỉ công khai những thao tác dữ liệu mà một phần của ứng dụng thực sự cần. Thay vì luôn kế thừa `JpaRepository` và tự động nhận toàn bộ API CRUD, ta có thể chọn một tập phương thức nhỏ hơn bằng hai cách:

- Dùng `@RepositoryDefinition(domainClass = ..., idClass = ...)` trên interface Repository cụ thể.
- Tạo một interface cơ sở tối giản kế thừa `Repository<T, ID>`, khai báo những phương thức muốn dùng, rồi cho các Repository cụ thể kế thừa interface đó.

Cả hai cách đều giúp kiểm soát API ở mức Java type. Interface cơ sở còn cho phép dùng lại cùng một tập phương thức cho nhiều entity. Bài viết giải thích cách Spring Data nhận diện các interface này, cách `@NoRepositoryBean` hoạt động, cách kết hợp query method và cách chọn thiết kế phù hợp.

## 1. Repository là một abstraction, không nhất thiết phải có toàn bộ CRUD

Spring Data Repository là interface mô tả cách ứng dụng truy cập dữ liệu. Spring Data quét interface, tạo proxy và điều phối các phương thức tới implementation JPA tương ứng. Với Spring Data JPA, implementation mặc định thường là `SimpleJpaRepository`.

Các interface nền tảng thường gặp:

| Interface | Vai trò |
| --- | --- |
| `Repository<T, ID>` | Marker interface tối thiểu để Spring Data nhận diện repository và kiểu entity/ID. |
| `CrudRepository<T, ID>` | Nhóm thao tác CRUD cơ bản như lưu, tìm, đếm và xóa. |
| `ListCrudRepository<T, ID>` | Biến thể CRUD trả `List` ở các phương thức danh sách. |
| `PagingAndSortingRepository<T, ID>` | Cung cấp thao tác phân trang và sắp xếp. |
| `JpaRepository<T, ID>` | API mở rộng dành cho JPA, gồm các thao tác batch, flush và các khả năng JPA khác. |

`JpaRepository` rất tiện khi một thành phần cần đầy đủ khả năng quản lý dữ liệu. Nhưng nếu một module chỉ cần đọc, việc kế thừa `JpaRepository` làm API của module rộng hơn yêu cầu. Người gọi có thể thấy các phương thức `save`, `delete`, `flush` dù nghiệp vụ chỉ cần truy vấn.

Spring Data cho phép định nghĩa interface chỉ kế thừa marker `Repository` và khai báo chính xác những chữ ký phương thức cần công khai. Các chữ ký phù hợp với thao tác nền tảng được định tuyến tới repository base implementation; query method mới được phân tích theo tên hoặc annotation.

## 2. Chọn lọc phương thức trực tiếp bằng Repository<T, ID>

`Repository<T, ID>` chỉ mang thông tin về kiểu domain và kiểu khóa chính. Nó không tự công khai toàn bộ CRUD. Ta có thể sao chép chữ ký những phương thức cần dùng từ các interface CRUD vào interface riêng.

Ví dụ chỉ muốn cung cấp khả năng đọc:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface CustomerReadRepository
        extends Repository<Customer, Long> {

    Optional<Customer> findById(Long id);

    List<Customer> findAll();

    Optional<Customer> findByEmailIgnoreCase(String email);
}
```

Interface này công khai ba phương thức: tìm theo ID, lấy danh sách và tìm theo email không phân biệt hoa thường. Nó không khai báo `save`, `deleteById` hay `flush`, vì vậy code sử dụng bean thông qua kiểu `CustomerReadRepository` không thể gọi trực tiếp các phương thức đó.

`findById` là phương thức nền tảng được Spring Data nhận diện theo chữ ký và chuyển tới implementation của repository. `findAll` cũng là phương thức nền tảng. `findByEmailIgnoreCase` là derived query: Spring Data phân tích tên phương thức, tìm thuộc tính `email` và tạo query JPA tương ứng.

### Nếu cần thêm một thao tác ghi

Chỉ thêm chữ ký thật sự cần thiết. Ví dụ một interface có quyền đọc và lưu nhưng không có xóa:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface CustomerWriteRepository
        extends Repository<Customer, Long> {

    <S extends Customer> S save(S entity);

    Optional<Customer> findById(Long id);

    List<Customer> findAll();
}
```

Chữ ký generic `<S extends Customer> S save(S entity)` giữ được kiểu cụ thể của entity khi gọi `save`, tương tự chữ ký trong CRUD repository. Không cần khai báo `delete` nếu module không được phép thực hiện thao tác đó qua interface này.

Việc thu hẹp interface là cách thiết kế API và giảm khả năng gọi nhầm ở thời điểm biên dịch. Nó không phải ranh giới bảo mật database: code vẫn có thể ghi dữ liệu thông qua một bean khác, `EntityManager`, JDBC hoặc một Repository khác nếu được cấp quyền truy cập.

## 3. Dùng interface cơ sở để tái sử dụng tập phương thức

Khi nhiều entity cần cùng một tập thao tác, không nên lặp lại các chữ ký trong từng Repository. Tạo interface generic làm cơ sở:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface ReadOnlyRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();
}
```

`T` là kiểu entity và `ID` là kiểu khóa chính. Mỗi Repository cụ thể cung cấp hai kiểu này khi kế thừa:

```java
import java.util.Optional;

public interface CustomerRepository
        extends ReadOnlyRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);
}
```

Repository khác có thể dùng lại cùng interface:

```java
public interface ProductRepository
        extends ReadOnlyRepository<Product, Long> {

    List<Product> findByActiveTrue();
}
```

Nhờ vậy, `CustomerRepository` và `ProductRepository` cùng công khai `findById` và `findAll`, nhưng mỗi interface có query method riêng theo domain của nó.

### Vì sao phải có @NoRepositoryBean?

`ReadOnlyRepository<T, ID>` là interface trung gian. Nó chưa xác định entity cụ thể vì `T` và `ID` vẫn là tham số kiểu tổng quát. Ta không muốn Spring Data tạo một bean Repository trực tiếp từ interface này.

`@NoRepositoryBean` báo cho cơ chế quét Repository rằng interface đó chỉ là nền tảng để các interface cụ thể kế thừa, không phải repository instance độc lập. Các interface con như `CustomerRepository` vẫn được quét và tạo bean bình thường.

Nếu thiếu annotation, Spring Data có thể cố tạo repository cho interface trung gian và không xác định được domain type hoặc ID type phù hợp. Đặt `@NoRepositoryBean` trên các base repository interface chưa phải loại cụ thể là quy ước quan trọng.

### Mở rộng interface cơ sở có kiểm soát

Muốn thêm phương thức dùng chung, hãy bổ sung chữ ký vào base interface. Ví dụ:

```java
@NoRepositoryBean
public interface ReadWriteRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();

    <S extends T> S save(S entity);
}
```

Tất cả Repository kế thừa `ReadWriteRepository` sẽ công khai `save`. Nếu chỉ một nhóm entity được ghi, hãy tạo một nhánh interface riêng cho nhóm đó thay vì đưa `save` vào base interface dùng chung cho mọi entity.

Không nên đặt hàng loạt phương thức CRUD vào base interface chỉ để tránh lặp vài dòng. Mục tiêu là thể hiện đúng khả năng mà các Repository con cần chia sẻ.

## 4. Dùng @RepositoryDefinition trên Repository cụ thể

`@RepositoryDefinition` là lựa chọn thay thế cho việc kế thừa `Repository<T, ID>`. Annotation khai báo rõ entity và kiểu ID của repository:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.RepositoryDefinition;

@RepositoryDefinition(domainClass = Customer.class, idClass = Long.class)
public interface CustomerQueryRepository {

    Optional<Customer> findById(Long id);

    List<Customer> findAll();

    Optional<Customer> findByEmailIgnoreCase(String email);
}
```

Spring Data nhận diện interface có `@RepositoryDefinition`, tạo proxy cho nó và xử lý các phương thức theo cơ chế Repository. Những phương thức nền tảng như `findById` và `findAll` được chuyển tới base implementation; `findByEmailIgnoreCase` được xử lý như derived query.

Điểm khác biệt chính:

| Cách định nghĩa | Cách xác định domain và ID | Phù hợp khi |
| --- | --- | --- |
| `extends Repository<Customer, Long>` | Khai báo trong tham số generic. | Muốn interface thể hiện trực tiếp quan hệ kế thừa của Repository. |
| `@RepositoryDefinition(domainClass = Customer.class, idClass = Long.class)` | Khai báo bằng thuộc tính annotation. | Muốn một interface không cần extends marker `Repository`. |
| Interface cơ sở generic có `@NoRepositoryBean` | Base interface giữ `T`, `ID`; interface con cung cấp kiểu cụ thể. | Nhiều Repository cần chia sẻ một tập phương thức đã chọn. |

Thông thường chỉ cần chọn một cách cho mỗi Repository. Không cần vừa gắn `@RepositoryDefinition` vừa kế thừa `Repository` trên cùng interface. Khi có nhiều Repository cùng cấu trúc, interface cơ sở generic thường giảm lặp tốt hơn.

## 5. Spring Data phân biệt phương thức nền tảng và query method

Repository proxy phải quyết định mỗi phương thức sẽ được thực thi theo cách nào.

### Phương thức nền tảng

Những chữ ký như `findById(ID id)`, `findAll()` hoặc `save(S entity)` tương ứng với các thao tác có sẵn trong repository base implementation. Khi ta chọn lọc bằng cách sao chép chữ ký vào interface con của `Repository`, Spring Data vẫn có thể chuyển lời gọi tới implementation mặc định của store module.

`findById` là một phương thức dành riêng của Repository để tìm theo identifier của entity. Nếu entity có một thuộc tính khác cũng tên `id` nhưng không phải khóa chính, hãy đặt tên query method rõ hơn, ví dụ `findCustomerById(...)`, để tránh nhầm với phương thức nền tảng.

### Derived query method

Phương thức như `findByEmailIgnoreCase`, `findByStatusAndCreatedAtAfter` hoặc `existsByEmail` được phân tích từ tên:

- `findBy`: bắt đầu truy vấn đọc.
- `Email`: thuộc tính `email` của entity.
- `IgnoreCase`: so sánh chuỗi không phân biệt hoa thường.
- `And`, `Or`, `After`, `Before`, `Containing`, `In`, `Between`: các toán tử và phép kết hợp được Spring Data hỗ trợ.

Ví dụ:

```java
public interface CustomerRepository
        extends ReadOnlyRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);

    List<Customer> findByNameContainingIgnoreCase(String keyword);
}
```

Spring Data kiểm tra property trên entity, không phân tích tên cột SQL. Nếu Java property là `email` nhưng cột được map bằng `@Column(name = "email_address")`, phương thức vẫn dùng `findByEmail...`.

### Query khai báo bằng @Query

Với truy vấn phức tạp hoặc tên phương thức quá dài, có thể khai báo JPQL:

```java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> lookupByEmail(@Param("email") String email);
```

JPQL dùng entity name và property Java. Nếu cần SQL theo tên bảng và cột, dùng `nativeQuery = true`. Cả hai dạng query vẫn có thể được khai báo trong Repository chọn lọc hoặc interface con của base interface.

## 6. Cấu hình quét Repository

Trong Spring Boot, Repository thường được quét tự động theo package của lớp `@SpringBootApplication`. Đặt lớp main ở package gốc để các interface con và entity nằm trong những package con dễ được phát hiện.

Nếu cần chỉ rõ package, có thể dùng `@EnableJpaRepositories`:

```java
@SpringBootApplication
@EnableJpaRepositories(basePackages = "com.example.repository")
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Với cấu hình nhiều persistence unit hoặc nhiều database, cần trỏ đúng `entityManagerFactoryRef` và `transactionManagerRef`. `@NoRepositoryBean` chỉ loại interface trung gian khỏi việc tạo bean; nó không thay thế cấu hình package scan.

## 7. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ tạo một interface cơ sở chỉ cho phép đọc. Dữ liệu được tạo bằng `EntityManager` trong một Service riêng; Repository chỉ công khai `findById`, `findAll` và query tìm email.

### Cấu trúc dự án

```text
selective-repository/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/selective/
        │   ├── SelectiveRepositoryApplication.java
        │   ├── Customer.java
        │   ├── ReadOnlyRepository.java
        │   ├── CustomerRepository.java
        │   ├── CustomerWriter.java
        │   └── CustomerReader.java
        └── resources/
            └── application.properties
```

### pom.xml

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
    <artifactId>selective-repository</artifactId>
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

### src/main/resources/application.properties

```properties
spring.datasource.url=jdbc:h2:mem:selective;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`create-drop` phù hợp cho database H2 tạm trong ví dụ. Dự án thật nên quản lý schema bằng Flyway hoặc Liquibase và chọn `ddl-auto` phù hợp với môi trường.

### Customer.java

```java
package com.example.selective;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, unique = true, length = 180)
    private String email;

    protected Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    @Override
    public String toString() {
        return "Customer{id=" + id + ", name=" + name + ", email=" + email + "}";
    }
}
```

### ReadOnlyRepository.java

```java
package com.example.selective;

import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface ReadOnlyRepository<T, ID> extends Repository<T, ID> {
    Optional<T> findById(ID id);

    List<T> findAll();
}
```

### CustomerRepository.java

```java
package com.example.selective;

import java.util.Optional;

public interface CustomerRepository
        extends ReadOnlyRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);
}
```

### CustomerWriter.java

```java
package com.example.selective;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerWriter {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void create(String name, String email) {
        entityManager.persist(new Customer(name, email));
    }
}
```

### CustomerReader.java

```java
package com.example.selective;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerReader {
    private final CustomerRepository repository;

    public CustomerReader(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Customer findByEmail(String email) {
        return repository.findByEmailIgnoreCase(email).orElseThrow();
    }

    @Transactional(readOnly = true)
    public int countAll() {
        List<Customer> customers = repository.findAll();
        return customers.size();
    }
}
```

Query method do ứng dụng tự khai báo không mặc định nhận transaction configuration trong mọi trường hợp. Đặt `@Transactional(readOnly = true)` ở Service giúp ranh giới transaction của thao tác đọc được thể hiện rõ. Các thao tác trong cùng Service method có thể tham gia cùng transaction.

### SelectiveRepositoryApplication.java

```java
package com.example.selective;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SelectiveRepositoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(SelectiveRepositoryApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CustomerWriter writer, CustomerReader reader) {
        return args -> {
            writer.create("An", "an@example.com");

            Customer found = reader.findByEmail("AN@example.com");
            System.out.println("Found: " + found);
            System.out.println("Total customers: " + reader.countAll());
        };
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Với H2 database mới, phần output do ứng dụng in ra có dạng:

```text
Found: Customer{id=1, name=An, email=an@example.com}
Total customers: 1
```

Điểm cần quan sát: `CustomerRepository` không kế thừa `CrudRepository` hoặc `JpaRepository`, nhưng Spring Data vẫn tạo proxy. `findById` và `findAll` được xử lý bằng repository base implementation; `findByEmailIgnoreCase` được phân tích thành query. Ứng dụng gọi được ba phương thức đã công khai, còn `save` và `delete` không có trong kiểu `CustomerRepository`.

## 8. Khi nào dùng RepositoryDefinition, khi nào dùng interface cơ sở?

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Một Repository riêng lẻ cần công khai một vài phương thức | `@RepositoryDefinition` hoặc kế thừa trực tiếp `Repository<T, ID>` và khai báo chữ ký. |
| Nhiều Repository cần cùng tập thao tác tối thiểu | Interface cơ sở generic có `@NoRepositoryBean`. |
| Nhiều Repository có nhóm quyền khác nhau, ví dụ chỉ đọc và đọc/ghi | Tạo các nhánh base interface riêng như `ReadOnlyRepository` và `ReadWriteRepository`. |
| Cần bổ sung hành vi custom cho một số Repository | Dùng repository fragments với interface và implementation tương ứng. |
| Cần thay đổi implementation nền tảng dùng chung cho nhiều Repository | Cấu hình custom repository base class, ví dụ lớp kế thừa `SimpleJpaRepository`. |

`@RepositoryDefinition` và interface cơ sở quyết định API nào được công khai. Repository fragment và custom base class giải quyết việc triển khai hành vi tùy chỉnh; chúng là bài toán khác.

### Phân biệt custom base interface với custom base class

- **Custom base interface:** khai báo chữ ký và khả năng mà code gọi được. `@NoRepositoryBean` ngăn interface generic trung gian được tạo thành bean riêng.
- **Repository fragment:** thêm một nhóm hành vi riêng bằng cách ghép interface custom và implementation vào Repository cần dùng.
- **Custom base class:** thay hoặc mở rộng lớp implementation nền tảng, thường kế thừa `SimpleJpaRepository` và được đăng ký qua cấu hình `repositoryBaseClass`.

Không cần tạo custom base class chỉ để ẩn `save` hoặc `delete`; interface chọn lọc đã giải quyết phần API công khai.

## 9. Lưu ý về phiên bản và thiết kế

1. **Phân trang và CRUD:** từ Spring Data 3.x, `PagingAndSortingRepository` không còn tự kế thừa `CrudRepository`. Nếu cần cả hai nhóm phương thức, hãy kế thừa rõ cả hai interface tương ứng với phiên bản đang dùng.
2. **Kiểu trả về danh sách:** `List<T> findAll()` phù hợp với JPA và implementation `SimpleJpaRepository`. Nếu xây dựng abstraction dùng chung cho nhiều Spring Data store, cân nhắc `Iterable<T>` để tương thích chữ ký CRUD cơ bản.
3. **Generic ID phải đúng:** nếu entity dùng `Long` làm khóa chính, khai báo `Repository<Customer, Long>`; không dùng nhầm kiểu như `String`.
4. **Tên property là tên Java:** derived query dựa trên property của entity, không dựa trực tiếp vào tên cột database.
5. **Phương thức nền tảng có tên dành riêng:** `findById` luôn có ngữ nghĩa tìm theo identifier. Nếu muốn truy vấn một property khác cùng tên, dùng tên phương thức phân biệt rõ.
6. **Đừng quên @NoRepositoryBean:** áp dụng cho base interface tổng quát chưa phải repository cụ thể.
7. **Không lạm dụng base interface:** chỉ đặt các thao tác thực sự dùng chung vào đó. Base interface quá lớn sẽ làm mọi Repository con nhận API không cần thiết.
8. **API hẹp không thay thế phân quyền:** kiểm soát quyền truy cập dữ liệu ở service, authorization và database permissions khi cần; việc không khai báo `delete` chỉ ngăn lời gọi qua kiểu interface đó.
9. **Transaction ở đúng tầng:** đặt transaction theo đơn vị nghiệp vụ ở Service; không giả định mọi query method khai báo đều tự có transaction.

## 10. Checklist khi tạo Repository chọn lọc

- Xác định entity type và ID type.
- Liệt kê chính xác phương thức cần công khai: đọc, lưu, xóa, phân trang hay query tùy chỉnh.
- Nếu chỉ có một Repository, cân nhắc `@RepositoryDefinition` hoặc `Repository<T, ID>` trực tiếp.
- Nếu nhiều Repository chia sẻ API, tạo base interface generic và gắn `@NoRepositoryBean`.
- Đưa derived query hoặc `@Query` vào interface cụ thể theo nhu cầu domain.
- Đặt transaction ở Service cho các nghiệp vụ đọc/ghi cần ranh giới rõ ràng.
- Kiểm tra package scan và đảm bảo Spring tạo bean cho interface cụ thể.
- Biên dịch và chạy ứng dụng để xác nhận mọi chữ ký phương thức được Spring Data triển khai đúng.

Điểm cốt lõi: **`Repository<T, ID>` là marker tối thiểu; `@RepositoryDefinition` là cách khai báo domain/ID bằng annotation; interface cơ sở generic với `@NoRepositoryBean` giúp tái sử dụng một tập phương thức đã chọn.** Hãy công khai đúng khả năng mà module cần, rồi bổ sung hành vi custom bằng fragment hoặc base class khi thực sự cần.