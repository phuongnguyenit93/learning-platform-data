# Nhận diện Repository khi nhiều mô-đun Spring Data cùng tồn tại

Một ứng dụng Spring Boot có thể dùng nhiều mô-đun Spring Data cùng lúc, chẳng hạn Spring Data JPA để làm việc với PostgreSQL và Spring Data MongoDB để làm việc với MongoDB. Khi chỉ có một mô-đun Spring Data, việc tìm repository thường khá đơn giản. Khi nhiều mô-đun cùng xuất hiện trên classpath, Spring Data cần xác định mỗi repository thuộc về store nào để tạo đúng loại proxy và kết nối với đúng hạ tầng lưu trữ.

Spring Data giải quyết tình huống này bằng **strict repository configuration mode** (chế độ cấu hình repository nghiêm ngặt). Ở chế độ này, một repository cần có dấu hiệu đủ rõ để xác định store mà nó thuộc về. Hai dấu hiệu quan trọng là:

1. Repository kế thừa interface đặc thù của store, ví dụ **JpaRepository** hoặc **MongoRepository**.
2. Kiểu domain của repository mang annotation đặc thù của store, ví dụ **@Entity** của JPA hoặc **@Document** của MongoDB.

Nếu repository chỉ kế thừa abstraction chung như **CrudRepository**, đồng thời domain type không có annotation đặc thù, Spring Data có thể không xác định được repository thuộc mô-đun nào. Hiểu các quy tắc này giúp tránh lỗi repository không được đăng ký, repository bị gắn sai store hoặc cấu hình khởi động mơ hồ.

**Điều kiện của ví dụ:** các đoạn mã minh họa dùng Spring Boot 3.x, Java 17 trở lên và Spring Data tương ứng. Ví dụ JPA dùng **spring-boot-starter-data-jpa**; ví dụ MongoDB dùng **spring-boot-starter-data-mongodb**. Mỗi đoạn mã là một tệp nguồn riêng trong ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Vì sao nhiều mô-đun Spring Data cần nhận diện repository?

Mỗi mô-đun Spring Data cung cấp cách làm việc với một loại persistence store. Ví dụ:

| Mô-đun | Store | Repository đặc thù | Annotation domain thường gặp |
|---|---|---|---|
| Spring Data JPA | Cơ sở dữ liệu quan hệ thông qua JPA | **JpaRepository** | **jakarta.persistence.Entity** |
| Spring Data MongoDB | MongoDB | **MongoRepository** | **org.springframework.data.mongodb.core.mapping.Document** |
| Spring Data Redis | Redis | **CrudRepository** hoặc repository API phù hợp của mô-đun | **org.springframework.data.redis.core.RedisHash** |
| Spring Data Elasticsearch | Elasticsearch | **ElasticsearchRepository** | **org.springframework.data.elasticsearch.annotations.Document** |

Khi ứng dụng chỉ có JPA, Spring Data JPA có thể xử lý các repository phù hợp trong phạm vi quét của nó. Khi JPA và MongoDB cùng có mặt, cả hai mô-đun đều cung cấp repository infrastructure và cùng quan tâm đến các abstraction chung trong Spring Data Commons.

Ví dụ một interface:

~~~java
public interface BookRepository extends CrudRepository<Book, String> {
}
~~~

Chỉ nhìn vào **CrudRepository<Book, String>**, hệ thống biết đây là một repository Spring Data, nhưng chưa đủ thông tin để kết luận repository này phải được tạo bởi JPA hay MongoDB. Kiểu khóa **String** cũng không xác định store; cả MongoDB lẫn nhiều mô hình dữ liệu khác đều có thể dùng String làm ID.

Spring Data cần thêm bằng chứng từ kiểu repository, annotation domain hoặc phạm vi cấu hình cụ thể.

## 2. Strict repository configuration mode là gì?

Khi Spring Data phát hiện nhiều mô-đun repository trên classpath, quá trình bootstrap chuyển sang **strict repository configuration mode**. Thay vì giả định một mô-đun duy nhất sở hữu mọi repository, từng mô-đun áp dụng quy tắc nhận diện để quyết định repository nào thuộc về nó.

Trong log khởi động có thể thấy thông báo tương tự:

~~~text
Multiple Spring Data modules found, entering strict repository configuration mode
~~~

Thông báo này tự nó không phải lỗi. Nó cho biết có nhiều mô-đun Spring Data và việc nhận diện repository cần chặt chẽ hơn. Sau đó, log bootstrap của từng mô-đun giúp xem mô-đun nào đã tìm thấy repository nào.

Trong strict mode, hai tín hiệu nhận diện thường dùng là:

- **Repository type:** interface kế thừa repository đặc thù của một store.
- **Domain annotation:** kiểu domain mang annotation được mô-đun đó nhận diện.

Nếu một repository có cả hai tín hiệu và chúng cùng chỉ tới một store, ý định rất rõ ràng. Nếu chỉ dùng abstraction chung, annotation domain trở nên quan trọng. Nếu cả hai tín hiệu mâu thuẫn hoặc một domain type được đánh dấu cho nhiều store, cấu hình có thể trở nên mơ hồ.

Strict mode là cơ chế nhận diện lúc bootstrap. Nó không phải bộ định tuyến truy vấn ở runtime và không tự biến một repository thành repository đa store.

## 3. Cách 1: Kế thừa repository interface đặc thù của store

Đây thường là cách rõ ràng nhất. Mỗi repository kế thừa interface thuộc mô-đun mà nó cần sử dụng.

Ví dụ repository cho JPA:

~~~java
package com.example.catalog.jpa.repository;

import com.example.catalog.jpa.domain.JpaBook;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface JpaBookRepository extends JpaRepository<JpaBook, Long> {

    Optional<JpaBook> findByIsbn(String isbn);
}
~~~

Repository cho MongoDB:

~~~java
package com.example.catalog.mongo.repository;

import com.example.catalog.mongo.domain.MongoBook;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.Optional;

public interface MongoBookRepository
        extends MongoRepository<MongoBook, String> {

    Optional<MongoBook> findByIsbn(String isbn);
}
~~~

Spring Data có thể nhận diện:

- **JpaBookRepository** là repository JPA vì nó kế thừa **JpaRepository**.
- **MongoBookRepository** là repository MongoDB vì nó kế thừa **MongoRepository**.

Tên interface như **JpaBookRepository** hay **MongoBookRepository** chỉ giúp con người đọc code. Tín hiệu kỹ thuật là kiểu interface mà repository kế thừa, không phải tiền tố tên lớp.

Không nên tạo một interface nghiệp vụ chung rồi cố làm cho nó đồng thời kế thừa nhiều repository store-specific. Các mô-đun có thể có hợp đồng phương thức, semantics của ID, query derivation và cơ chế thực thi khác nhau. Nếu một use case cần đọc hoặc ghi nhiều store, hãy phối hợp các repository riêng ở tầng service.

## 4. Cách 2: Dùng annotation đặc thù trên domain type

Khi repository chỉ kế thừa abstraction chung như **CrudRepository**, annotation trên kiểu domain có thể giúp Spring Data nhận diện store.

Entity JPA:

~~~java
package com.example.catalog.jpa.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class JpaBook {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String isbn;

    protected JpaBook() {
    }

    public JpaBook(String isbn) {
        this.isbn = isbn;
    }

    public Long getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }
}
~~~

Document MongoDB:

~~~java
package com.example.catalog.mongo.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "books")
public class MongoBook {

    @Id
    private String id;

    private String isbn;

    public MongoBook() {
    }

    public MongoBook(String isbn) {
        this.isbn = isbn;
    }

    public String getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }
}
~~~

Các repository dùng abstraction chung:

~~~java
package com.example.catalog.jpa.repository;

import com.example.catalog.jpa.domain.JpaBook;
import org.springframework.data.repository.CrudRepository;

public interface JpaBookCrudRepository
        extends CrudRepository<JpaBook, Long> {
}
~~~

~~~java
package com.example.catalog.mongo.repository;

import com.example.catalog.mongo.domain.MongoBook;
import org.springframework.data.repository.CrudRepository;

public interface MongoBookCrudRepository
        extends CrudRepository<MongoBook, String> {
}
~~~

Trong trường hợp này:

- **JpaBook** có **@Entity**, nên cung cấp tín hiệu domain cho mô-đun JPA.
- **MongoBook** có **@Document** của Spring Data MongoDB, nên cung cấp tín hiệu domain cho mô-đun MongoDB.

Lưu ý import chính xác. JPA dùng **jakarta.persistence.Entity**. MongoDB dùng **org.springframework.data.mongodb.core.mapping.Document**. Elasticsearch cũng có annotation tên đơn giản là **Document**, nhưng thuộc package khác. Không chỉ nhìn tên ngắn của annotation; hãy kiểm tra import thực tế.

Annotation domain phải đúng với mô-đun và mapping mà ứng dụng dùng. Một lớp Java chỉ có **@Id** chung của Spring Data chưa chắc đủ để phân biệt JPA với MongoDB, vì nhiều mô-đun cùng hiểu annotation định danh của Spring Data Commons.

## 5. Khi repository chỉ dùng CrudRepository và domain không có annotation đặc thù

Đây là trường hợp dễ gây nhầm lẫn nhất.

Giả sử:

~~~java
public class BookRecord {
    private String id;
    private String isbn;
}
~~~

và repository:

~~~java
public interface BookRecordRepository
        extends CrudRepository<BookRecord, String> {
}
~~~

Nếu ứng dụng chỉ có một mô-đun Spring Data, repository có thể được nhận diện theo cấu hình một store. Nhưng khi nhiều mô-đun cùng tồn tại, interface chỉ kế thừa **CrudRepository** và domain type không có annotation store-specific thì không có tín hiệu đủ rõ để gắn repository vào JPA hay MongoDB.

Hậu quả có thể là repository không được mô-đun nào nhận diện, kèm cảnh báo về repository candidate không thể xác định store. Tùy cấu hình và phiên bản, repository có thể bị bỏ qua trong quá trình bootstrap hoặc dẫn đến lỗi khi ứng dụng cần inject bean đó.

Cách xử lý:

1. Nếu repository thực sự thuộc JPA, kế thừa **JpaRepository** hoặc đánh dấu domain bằng **@Entity**.
2. Nếu repository thực sự thuộc MongoDB, kế thừa **MongoRepository** hoặc đánh dấu domain bằng **@Document**.
3. Nếu cần abstraction chung cho tầng nghiệp vụ, tạo interface/service phía trên và inject các repository store-specific bên dưới.
4. Nếu repository được bật bằng cấu hình store-specific, giới hạn package của từng cấu hình để tránh quét lẫn nhau.

Không nên giải quyết bằng cách đổi tên interface thành **JpaBookRepository** rồi giữ nguyên mọi thứ khác. Tên lớp không thay thế được tín hiệu kỹ thuật mà Spring Data sử dụng.

## 6. Tránh một domain type mang annotation của nhiều store

Một lỗi thiết kế khác là dùng cùng một lớp domain cho nhiều database và gắn nhiều annotation:

~~~java
@Entity
@Document(collection = "books")
public class Book {
    // ...
}
~~~

Khi một lớp mang đồng thời annotation của nhiều store, Spring Data có thể không xác định được một repository generic đang thuộc mô-đun nào. Các mô-đun có quy tắc mapping và vòng đời entity khác nhau; JPA entity và MongoDB document cũng không có cùng semantics.

Thiết kế rõ ràng hơn là tách kiểu domain:

~~~text
catalog
├── jpa
│   ├── domain
│   │   └── JpaBook
│   └── repository
│       └── JpaBookRepository
└── mongo
    ├── domain
    │   └── MongoBook
    └── repository
        └── MongoBookRepository
~~~

Nếu cả hai store cùng biểu diễn một khái niệm nghiệp vụ, có thể dùng DTO hoặc model nghiệp vụ trung lập ở tầng service để trao đổi dữ liệu. Mỗi store giữ kiểu persistence riêng và chuyển đổi tại ranh giới thích hợp.

Ví dụ một service đọc dữ liệu từ cả hai store:

~~~java
@Service
public class BookLookupService {

    private final JpaBookRepository jpaRepository;
    private final MongoBookRepository mongoRepository;

    public BookLookupService(
            JpaBookRepository jpaRepository,
            MongoBookRepository mongoRepository) {
        this.jpaRepository = jpaRepository;
        this.mongoRepository = mongoRepository;
    }

    public long relationalBookCount() {
        return jpaRepository.count();
    }

    public long documentBookCount() {
        return mongoRepository.count();
    }
}
~~~

Đây là một bean điều phối hai repository riêng. Nó không làm cho hai repository dùng chung một persistence context hoặc một transaction manager.

## 7. Giới hạn package bằng @EnableJpaRepositories và @EnableMongoRepositories

Khi cần kiểm soát chính xác repository nào thuộc mô-đun nào, khai báo cấu hình riêng và dùng package marker.

Cấu hình JPA:

~~~java
package com.example.catalog.jpa.config;

import com.example.catalog.jpa.repository.JpaBookRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
    basePackageClasses = JpaBookRepository.class
)
public class JpaRepositoryConfiguration {
}
~~~

Cấu hình MongoDB:

~~~java
package com.example.catalog.mongo.config;

import com.example.catalog.mongo.repository.MongoBookRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
    basePackageClasses = MongoBookRepository.class
)
public class MongoRepositoryConfiguration {
}
~~~

**basePackageClasses** dùng package của class marker làm điểm bắt đầu quét. Các package con cũng thuộc phạm vi quét. Đây thường là lựa chọn an toàn hơn **basePackages = "..."** vì refactor package có thể được IDE cập nhật và trình biên dịch kiểm tra class reference.

Có thể dùng **basePackages** nếu cần cấu hình theo chuỗi:

~~~java
@EnableJpaRepositories(
    basePackages = {
        "com.example.catalog.jpa.repository",
        "com.example.inventory.jpa.repository"
    }
)
~~~

Không để cấu hình JPA và MongoDB quét cùng một vùng repository rộng nếu không cần thiết. Tách package theo store giúp việc kiểm tra, bảo trì và đọc log bootstrap dễ hơn.

### Lưu ý về cấu hình mặc định của Spring Boot

Spring Boot có auto-configuration cho từng store. Khi tự thêm **@EnableJpaRepositories** hoặc **@EnableMongoRepositories**, hãy kiểm tra cấu hình auto-configuration và log bootstrap để chắc chắn mỗi repository chỉ được đăng ký bởi cấu hình dự kiến. Tránh vừa quét mặc định toàn bộ package gốc, vừa tạo các cấu hình explicit có phạm vi chồng lấn mà không có chủ đích.

Nếu dùng nhiều cấu hình repository, mỗi cấu hình nên có một phạm vi package rõ ràng và chỉ rõ factory/transaction manager khi có nhiều persistence unit.

## 8. Phân biệt @EntityScan với package quét trong EntityManagerFactory

Với Spring Boot auto-configuration cho JPA, **@EntityScan** là cách chỉ định package domain để auto-configured entity manager nhận diện.

Ví dụ:

~~~java
@EntityScan(basePackageClasses = JpaBook.class)
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Trong cấu hình nhiều EntityManagerFactory tự tạo, từng factory cần biết package entity của nó. Khi đó cấu hình factory thường dùng **packages(...)**:

~~~java
@Bean
LocalContainerEntityManagerFactoryBean catalogEntityManagerFactory(
        EntityManagerFactoryBuilder builder,
        @Qualifier("catalogDataSource") DataSource dataSource) {

    return builder
        .dataSource(dataSource)
        .packages(JpaBook.class)
        .persistenceUnit("catalog")
        .build();
}
~~~

Hai cách này nằm ở các cấp cấu hình khác nhau:

- **@EntityScan** phục vụ entity scanning trong cấu hình auto-configured của Spring Boot.
- **EntityManagerFactoryBuilder.packages(...)** chỉ định package entity cho EntityManagerFactory cụ thể.

Không nên kỳ vọng một **@EntityScan** chung tự phân chia entity cho nhiều EntityManagerFactory. Với nhiều persistence unit, hãy cấu hình package entity tường minh trên từng factory.

## 9. Chọn đúng repository và domain trong nhiều store: ví dụ tổng hợp

Một ứng dụng dùng JPA và MongoDB có thể tổ chức như sau:

~~~text
com.example
├── Application.java
└── catalog
    ├── jpa
    │   ├── domain
    │   │   └── JpaBook.java
    │   └── repository
    │       └── JpaBookRepository.java
    ├── mongo
    │   ├── domain
    │   │   └── MongoBook.java
    │   └── repository
    │       └── MongoBookRepository.java
    └── service
        └── BookLookupService.java
~~~

Cấu hình tổng thể:

~~~java
package com.example;

import com.example.catalog.jpa.domain.JpaBook;
import com.example.catalog.jpa.repository.JpaBookRepository;
import com.example.catalog.mongo.repository.MongoBookRepository;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@SpringBootApplication
@EntityScan(basePackageClasses = JpaBook.class)
@EnableJpaRepositories(basePackageClasses = JpaBookRepository.class)
@EnableMongoRepositories(basePackageClasses = MongoBookRepository.class)
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Cấu hình này minh họa việc tách phạm vi entity JPA và hai nhóm repository. Ứng dụng còn phải cấu hình DataSource/JPA và MongoDB connection theo môi trường. Nếu package **com.example** là package gốc của ứng dụng, component scan mặc định cũng có thể tìm **BookLookupService**.

Với ứng dụng chỉ có một store, không cần copy cấu hình này một cách máy móc. Chỉ khai báo annotation bổ sung khi package layout hoặc yêu cầu multi-store khiến auto-configuration mặc định không đủ rõ.

## 10. Đọc log để chẩn đoán repository được nhận diện thế nào

Khi có nhiều mô-đun Spring Data, hãy quan sát log ở giai đoạn repository bootstrap. Một số thông tin hữu ích:

- Spring phát hiện nhiều Spring Data modules và chuyển sang strict mode.
- Mỗi mô-đun bắt đầu bootstrap repository trong phạm vi cấu hình của nó.
- Số repository được tìm thấy bởi JPA và MongoDB.
- Repository candidate nào bị bỏ qua hoặc không thể gắn vào store.
- Repository có được tạo bean thành công hay không.

Tên log và mức chi tiết có thể khác theo phiên bản. Có thể tăng log level trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.data.repository.config: DEBUG
    org.springframework.data.jpa.repository.config: DEBUG
    org.springframework.data.mongodb.repository.config: DEBUG
~~~

Không nên bật DEBUG quá rộng trong production nếu chưa đánh giá lượng log và thông tin được ghi. Dùng log để xác định repository scan trước, sau đó kiểm tra package, kiểu interface và annotation domain của candidate cụ thể.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Repository generic không được nhận diện | Chỉ kế thừa **CrudRepository**, domain không có annotation store-specific | Kế thừa interface đặc thù hoặc thêm annotation domain phù hợp |
| **Not a managed type** | Entity không được persistence unit nhận diện | Kiểm tra **@Entity**, **@EntityScan** hoặc **packages(...)** của factory |
| Không inject được repository | Package repository nằm ngoài phạm vi scan | Kiểm tra **@EnableJpaRepositories** hoặc **@EnableMongoRepositories** |
| Repository bị gắn nhầm store | Domain/interface thiếu dấu hiệu rõ hoặc package scan chồng lấn | Dùng repository type đặc thù, domain riêng và package riêng |
| Service không được tìm thấy | Component nằm ngoài component scan | Chỉnh **@SpringBootApplication(scanBasePackages = ...)** hoặc **@ComponentScan** |
| Một repository được cấu hình hai lần | Auto-configuration và cấu hình explicit có phạm vi chồng lấn | Thu hẹp package và xem log bootstrap của từng store |
| Repository trỏ sai EntityManagerFactory | Nhiều persistence unit nhưng thiếu hoặc sai factory reference | Chỉ định **entityManagerFactoryRef** và transaction manager phù hợp |
| Domain dùng annotation sai package | Import nhầm **@Document** hoặc **@Id** giữa các mô-đun | Kiểm tra import đầy đủ và annotation thuộc đúng store |

## 12. Checklist khi dùng nhiều mô-đun Spring Data

- [ ] Xác định ứng dụng đang dùng những store nào: JPA, MongoDB, Redis, Elasticsearch hoặc mô-đun khác.
- [ ] Kiểm tra dependency để biết mô-đun Spring Data nào có mặt trên classpath.
- [ ] Đảm bảo repository có interface đặc thù của store hoặc domain có annotation nhận diện tương ứng.
- [ ] Không dựa vào tên repository để xác định store.
- [ ] Tránh dùng một domain type với annotation của nhiều store nếu không có thiết kế mapping chuyên biệt.
- [ ] Tách package repository theo store.
- [ ] Dùng **basePackageClasses** để giới hạn package scan rõ ràng.
- [ ] Phân biệt component scan, entity scan và repository scan.
- [ ] Với nhiều EntityManagerFactory, chỉ định repository group và package entity cho từng factory.
- [ ] Kiểm tra log bootstrap và viết integration test cho từng store.
- [ ] Không giả định hai repository thuộc hai database sẽ tham gia cùng một transaction nguyên tử.

## 13. Kết luận

Khi nhiều mô-đun Spring Data cùng tồn tại, Spring cần xác định repository nào thuộc store nào. Cách rõ ràng nhất là dùng repository interface đặc thù như **JpaRepository** và **MongoRepository**. Nếu repository dùng abstraction chung như **CrudRepository**, annotation domain như **@Entity** hoặc **@Document** cung cấp tín hiệu nhận diện quan trọng.

Hãy giữ ba phạm vi quét riêng biệt: **@ComponentScan** cho bean ứng dụng, **@EntityScan** cho entity trong cấu hình Spring Boot và **@EnableJpaRepositories**/**@EnableMongoRepositories** cho repository của từng store. Package được tách rõ, domain type phản ánh đúng store và repository được cấu hình tường minh sẽ giúp ứng dụng khởi động ổn định, dễ kiểm tra và dễ mở rộng.