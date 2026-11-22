# Cấu hình @EnableJpaRepositories và @EntityScan

Trong một ứng dụng Spring Boot dùng Spring Data JPA, hai annotation **@EnableJpaRepositories** và **@EntityScan** giúp Spring tìm đúng các thành phần persistence khi chúng nằm ngoài package mặc định của ứng dụng hoặc khi cần kiểm soát rõ phạm vi quét.

- **@EnableJpaRepositories** tìm các interface repository và đăng ký proxy để ứng dụng có thể inject, gọi chúng.
- **@EntityScan** khai báo các package chứa lớp entity để JPA nhận diện và ánh xạ chúng.
- **@ComponentScan** tìm các bean thông thường như service, controller và component. Nó là một cơ chế riêng.

Ba cơ chế này liên quan đến các package nhưng có mục đích khác nhau. Hiểu đúng ranh giới giúp tránh lỗi không tìm thấy repository, entity không được quản lý hoặc bean được gắn nhầm persistence unit.

**Điều kiện của ví dụ:** các đoạn mã minh họa dùng Spring Boot 3.x, Java 17 trở lên, Spring Data JPA và Jakarta Persistence. Ứng dụng cần dependency **spring-boot-starter-data-jpa**, JDBC driver phù hợp, DataSource được cấu hình và schema tương ứng. Các đoạn mã là những tệp riêng trong ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Ba phạm vi quét cần phân biệt

Giả sử dự án có cấu trúc package:

~~~text
com.example
├── bootstrap
│   └── Application.java
└── catalog
    ├── domain
    │   └── Book.java
    ├── repository
    │   └── BookRepository.java
    └── service
        └── BookService.java
~~~

Mỗi cơ chế chịu trách nhiệm cho một nhóm thành phần:

| Cơ chế | Annotation | Thành phần được tìm | Kết quả |
|---|---|---|---|
| Component scanning | **@ComponentScan** hoặc **@SpringBootApplication** | **@Component**, **@Service**, **@Controller**, **@Configuration** và các stereotype liên quan | Bean được đăng ký trong Spring ApplicationContext |
| Entity scanning | **@EntityScan** | Các lớp entity trong package đã khai báo | Package entity được cung cấp cho cấu hình JPA tự động của Spring Boot |
| Repository scanning | **@EnableJpaRepositories** | Interface repository của Spring Data JPA | Spring đăng ký các repository proxy để có thể inject |

Có thể hình dung:

~~~text
ApplicationContext
       |
       +-- Component scan
       |      +-- BookService
       |      +-- Controller
       |      +-- Configuration
       |
       +-- Repository scan
       |      +-- BookRepository interface
       |              |
       |              +-- Spring Data tạo repository proxy
       |
       +-- Entity scan
              +-- Book entity
                      |
                      +-- JPA EntityManager quản lý mapping
~~~

**@EntityScan** không tìm service hoặc repository. **@EnableJpaRepositories** không đăng ký entity và cũng không thay thế component scan. **@ComponentScan** không tự biến một interface bất kỳ thành Spring Data repository.

## 2. Spring Boot mặc định đã quét những package nào?

Trong ứng dụng Spring Boot thông thường, **@SpringBootApplication** kết hợp cấu hình ứng dụng, auto-configuration và component scanning. Package chứa lớp main thường là package gốc để quét các package con.

Ví dụ, nếu lớp main nằm tại **com.example.Application**, cấu trúc sau thường được phát hiện theo cấu hình mặc định:

~~~text
com.example
├── Application.java
└── catalog
    ├── domain
    │   └── Book.java
    ├── repository
    │   └── BookRepository.java
    └── service
        └── BookService.java
~~~

Với một DataSource và một persistence unit, Spring Boot thường tự cấu hình entity scanning và Spring Data JPA repository scanning từ package gốc của ứng dụng. Khi toàn bộ entity, repository và component nằm dưới package đó, bạn thường không cần tự thêm **@EntityScan** hay **@EnableJpaRepositories**.

Vấn đề xuất hiện khi lớp main đặt ở package hẹp, ví dụ **com.example.bootstrap**, còn entity và repository nằm trong package anh em **com.example.catalog**. Package **com.example.catalog** không phải package con của **com.example.bootstrap**. Khi đó cấu hình mặc định có thể không tìm thấy các lớp cần thiết.

Đặt lớp main tại package gốc chung là lựa chọn đơn giản nếu cấu trúc dự án cho phép. Nếu không thể thay đổi cấu trúc, hãy chỉ rõ phạm vi quét bằng các annotation phù hợp.

Không nên đặt lớp main trong default package (không khai báo package). Việc quét từ default package có thể khiến Spring cố quét quá rộng và làm ứng dụng khởi động chậm hoặc phát sinh xung đột.

## 3. Dùng @EntityScan để chỉ định package entity

**@EntityScan** thuộc Spring Boot:

~~~java
import org.springframework.boot.autoconfigure.domain.EntityScan;
~~~

Annotation này khai báo package chứa các lớp domain cần được dùng cho entity scanning của các data store được Spring Boot tự cấu hình. Với JPA, mục đích là giúp persistence configuration nhận diện các lớp được đánh dấu **@Entity**, cùng các kiểu domain liên quan mà provider cần.

Có hai cách chỉ định package chính:

- **basePackages**: khai báo tên package bằng chuỗi.
- **basePackageClasses**: truyền một hoặc nhiều class làm mốc; Spring lấy package của các class đó.

Ví dụ:

~~~java
@EntityScan(basePackages = {
    "com.example.catalog.domain",
    "com.example.customer.domain"
})
@Configuration
public class DomainScanConfiguration {
}
~~~

Cách dùng class marker:

~~~java
@EntityScan(basePackageClasses = {
    Book.class,
    Customer.class
})
@Configuration
public class DomainScanConfiguration {
}
~~~

Trong đó **Book.class** và **Customer.class** là các lớp nằm trong package cần quét. Chúng được dùng làm mốc package; không cần tạo một annotation đặc biệt trên các lớp này chỉ để làm marker.

Nên ưu tiên **basePackageClasses** khi có thể vì trình biên dịch sẽ kiểm tra tên class. Khi đổi package hoặc refactor, IDE cũng có thể cập nhật tham chiếu. Với **basePackages**, tên package chỉ là chuỗi nên lỗi chính tả thường chỉ xuất hiện lúc khởi động.

### @EntityScan không làm gì?

- Không tự đánh dấu một lớp Java thành entity. Lớp vẫn cần **@Entity** hoặc annotation JPA thích hợp như **@Embeddable** hay **@MappedSuperclass** theo vai trò của nó.
- Không tạo bảng hoặc cập nhật schema. Việc tạo schema phụ thuộc cấu hình Hibernate DDL hoặc công cụ migration.
- Không tìm interface repository.
- Không quét service/controller.
- Không cấu hình DataSource hoặc thông tin kết nối database.

Ví dụ entity tối giản:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Khi package của **Book** được cấu hình đúng, JPA mới có thể xem **Book** là một entity trong persistence unit tương ứng. Schema vẫn cần có bảng **books** với các cột tương thích hoặc được tạo bằng chiến lược schema đã chọn.

## 4. Dùng @EnableJpaRepositories để tìm repository

**@EnableJpaRepositories** thuộc Spring Data JPA:

~~~java
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
~~~

Annotation này bật repository infrastructure và chỉ định package chứa các interface repository cần đăng ký. Spring Data tạo proxy triển khai các thao tác khai báo trong interface, chẳng hạn **findById**, **save** hoặc các query method do ứng dụng định nghĩa.

Ví dụ repository:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByTitleContainingIgnoreCase(String keyword);
}
~~~

Khai báo cấu hình bằng chuỗi package:

~~~java
@EnableJpaRepositories(
    basePackages = "com.example.catalog.repository"
)
@Configuration
public class RepositoryScanConfiguration {
}
~~~

Hoặc dùng class marker:

~~~java
@EnableJpaRepositories(
    basePackageClasses = BookRepository.class
)
@Configuration
public class RepositoryScanConfiguration {
}
~~~

Khi có nhiều package, truyền nhiều class marker:

~~~java
@EnableJpaRepositories(
    basePackageClasses = {
        BookRepository.class,
        CustomerRepository.class
    }
)
@Configuration
public class RepositoryScanConfiguration {
}
~~~

Spring sẽ quét package của từng class marker và các package con tương ứng. Các interface được tìm thấy cần là repository hợp lệ, thường mở rộng **Repository**, **CrudRepository**, **ListCrudRepository** hoặc **JpaRepository**.

### Các thuộc tính thường cần biết

| Thuộc tính | Mục đích |
|---|---|
| **basePackages** / **value** | Chỉ định package bằng tên chuỗi |
| **basePackageClasses** | Chỉ định package qua class marker, an toàn hơn khi refactor |
| **entityManagerFactoryRef** | Tên bean EntityManagerFactory mà các repository được quét sẽ dùng |
| **transactionManagerRef** | Tên bean transaction manager mà repository dùng |
| **repositoryImplementationPostfix** | Hậu tố tên lớp triển khai repository tùy chỉnh; mặc định là **Impl** |
| **considerNestedRepositories** | Cho phép phát hiện repository interface lồng bên trong kiểu khác; mặc định là **false** |
| **bootstrapMode** | Điều khiển thời điểm khởi tạo repository proxy; mặc định thường là **DEFAULT** |

Với ứng dụng chỉ có một EntityManagerFactory và một transaction manager theo tên mặc định của Spring Boot, thường có thể bỏ qua **entityManagerFactoryRef** và **transactionManagerRef**. Khi có nhiều persistence unit, cần khai báo rõ hai tham chiếu này để tránh repository gắn vào database không mong muốn.

## 5. Cấu hình cả entity và repository trong ứng dụng

Quay lại cấu trúc package có lớp main ở **com.example.bootstrap**, còn domain, repository và service nằm trong **com.example.catalog**. Ta có thể khai báo cấu hình tập trung ở lớp main:

~~~java
package com.example.bootstrap;

import com.example.catalog.domain.Book;
import com.example.catalog.repository.BookRepository;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(scanBasePackages = "com.example")
@EntityScan(basePackageClasses = Book.class)
@EnableJpaRepositories(basePackageClasses = BookRepository.class)
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Ba phần trong cấu hình giải quyết ba phạm vi khác nhau:

1. **scanBasePackages = "com.example"** cho component scanning, để Spring tìm **BookService** và các bean khác nằm dưới **com.example**.
2. **@EntityScan(basePackageClasses = Book.class)** khai báo package chứa entity **Book** cho JPA auto-configuration của Spring Boot.
3. **@EnableJpaRepositories(basePackageClasses = BookRepository.class)** bật repository scanning tại package của **BookRepository**.

Nếu không mở rộng component scan, việc thêm **@EntityScan** và **@EnableJpaRepositories** vẫn không khiến **BookService** ở package bên ngoài được đăng ký thành bean.

Một service có thể inject repository đã được đăng ký:

~~~java
package com.example.catalog.service;

import com.example.catalog.repository.BookRepository;
import org.springframework.stereotype.Service;

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public long countBooks() {
        return bookRepository.count();
    }
}
~~~

Cấu hình kết nối database là một phần riêng. Ví dụ với PostgreSQL, các thuộc tính kết nối có thể được khai báo trong **application.yml**:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/catalog
    username: app_user
    password: change-me
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Ứng dụng còn cần PostgreSQL JDBC driver trong dependency. Giá trị tài khoản trong ví dụ chỉ là cấu hình minh họa; môi trường thực tế cần lấy thông tin kết nối từ cấu hình bảo mật phù hợp. **ddl-auto: validate** yêu cầu schema đã tồn tại và kiểm tra mapping; nó không tạo bảng.

## 6. Khi nào nên dùng cấu hình mặc định, khi nào nên khai báo rõ?

| Tình huống | Cách phù hợp |
|---|---|
| Main class ở package gốc, entity và repository nằm trong các package con | Dùng Spring Boot scanning mặc định |
| Entity nằm ngoài package gốc được auto-configuration nhận diện | Thêm **@EntityScan** với package phù hợp |
| Repository nằm ngoài package gốc được repository auto-configuration nhận diện | Thêm **@EnableJpaRepositories** với package phù hợp |
| Service/controller nằm ngoài component scan | Điều chỉnh **@SpringBootApplication(scanBasePackages = ...)** hoặc **@ComponentScan** |
| Có nhiều nhóm repository dùng các EntityManagerFactory khác nhau | Tạo cấu hình **@EnableJpaRepositories** riêng và chỉ rõ các bean tham chiếu |
| Entity thuộc nhiều persistence unit | Cấu hình package entity riêng cho từng EntityManagerFactory |

Không cần thêm cả hai annotation chỉ vì dự án dùng Spring Data JPA. Nếu cấu trúc package đã phù hợp với mặc định, việc khai báo lại phạm vi quét làm tăng cấu hình mà không đem lại lợi ích.

Khi chỉ có một database, nên ưu tiên cấu trúc package có một root chung và để Spring Boot auto-configuration xử lý phần lớn công việc. Chỉ mở rộng phạm vi quét khi cấu trúc thực tế đòi hỏi.

## 7. Nhiều database hoặc nhiều persistence unit

Một ứng dụng có thể kết nối nhiều database. Ví dụ, database catalog lưu sách, còn database identity lưu tài khoản. Khi đó, mỗi nhóm repository phải dùng đúng EntityManagerFactory và transaction manager.

Mô hình:

~~~text
CatalogRepository package
        |
        +-- @EnableJpaRepositories
        |      entityManagerFactoryRef = catalogEntityManagerFactory
        |      transactionManagerRef = catalogTransactionManager
        |
        +-- Catalog EntityManagerFactory
        |      packagesToScan: catalog.domain
        |
        +-- Catalog Transaction Manager
               |
               +-- catalog database

IdentityRepository package
        |
        +-- @EnableJpaRepositories
        |      entityManagerFactoryRef = identityEntityManagerFactory
        |      transactionManagerRef = identityTransactionManager
        |
        +-- Identity EntityManagerFactory
        |      packagesToScan: identity.domain
        |
        +-- Identity Transaction Manager
               |
               +-- identity database
~~~

Ví dụ cấu hình repository cho catalog:

~~~java
package com.example.catalog.config;

import com.example.catalog.repository.BookRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
    basePackageClasses = BookRepository.class,
    entityManagerFactoryRef = "catalogEntityManagerFactory",
    transactionManagerRef = "catalogTransactionManager"
)
public class CatalogRepositoryConfiguration {
}
~~~

Cấu hình trên giả định ứng dụng đã khai báo hai bean có tên chính xác là **catalogEntityManagerFactory** và **catalogTransactionManager**. Nếu tên bean thực tế khác, Spring không thể giải quyết tham chiếu.

EntityManagerFactory của catalog phải quét đúng entity package. Với cấu hình dùng **EntityManagerFactoryBuilder** của Spring Boot, phần quan trọng có dạng:

~~~java
@Bean
LocalContainerEntityManagerFactoryBean catalogEntityManagerFactory(
        EntityManagerFactoryBuilder builder,
        @Qualifier("catalogDataSource") DataSource dataSource) {

    return builder
        .dataSource(dataSource)
        .packages(Book.class)
        .persistenceUnit("catalog")
        .build();
}
~~~

Lời gọi **packages(Book.class)** xác định các package entity cho persistence unit catalog. Transaction manager tương ứng có thể được tạo từ EntityManagerFactory đó:

~~~java
@Bean
PlatformTransactionManager catalogTransactionManager(
        @Qualifier("catalogEntityManagerFactory") EntityManagerFactory entityManagerFactory) {

    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Các đoạn trên là phần cấu hình của một persistence unit, chưa phải toàn bộ cấu hình hai database. Ứng dụng còn phải khai báo **catalogDataSource**, các bean tương ứng cho identity, cấu hình connection properties và các dependency/import cần thiết.

### Vai trò của @EntityScan trong cấu hình nhiều database

**@EntityScan** hữu ích khi Spring Boot auto-configure entity scanning cho một persistence setup chung. Tuy nhiên, annotation này không tự chia entity thành các nhóm thuộc các database khác nhau.

Khi tự tạo nhiều EntityManagerFactory, hãy chỉ định package entity riêng trên từng factory, chẳng hạn **packages(Book.class)** cho catalog và **packages(UserAccount.class)** cho identity. Đây là ranh giới rõ ràng để tránh một persistence unit cố quản lý entity của database khác.

Đồng thời, giữ package repository tách biệt để từng **@EnableJpaRepositories** chỉ quét đúng nhóm interface. Không để hai cấu hình repository cùng quét một package nếu chúng phải dùng các EntityManagerFactory khác nhau.

Một transaction manager JPA quản lý transaction cho persistence unit tương ứng. Một transaction thông thường không tự trở thành distributed transaction chỉ vì phương thức service gọi hai repository thuộc hai database. Nếu nghiệp vụ cần tính nguyên tử xuyên nhiều database, phải thiết kế cơ chế điều phối phù hợp như XA/JTA hoặc mô hình nhất quán cuối cùng (saga/outbox) tùy yêu cầu; không giả định hai transaction manager độc lập sẽ commit hoặc rollback cùng nhau.

## 8. Kiểm tra cấu hình sau khi ứng dụng khởi động

Có thể kiểm tra theo từng lớp:

1. **Component scan:** service/controller mong đợi có được đăng ký thành bean không?
2. **Entity scan:** Hibernate có nhận diện entity không? Kiểm tra mapping, tên bảng và thông tin entity khi khởi động.
3. **Repository scan:** repository có thể inject vào service không? Query method có được Spring Data phân tích thành công không?
4. **Persistence unit:** repository có dùng đúng EntityManagerFactory và transaction manager không?
5. **Database:** kết nối có thành công và schema có tương thích mapping không?

Một bài kiểm tra repository nhỏ có thể dùng **@DataJpaTest** trong Spring Boot:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private BookRepository bookRepository;

    @Test
    void savesAndFindsBook() {
        Book saved = bookRepository.save(new Book("Spring Data JPA"));

        assertThat(saved.getId()).isNotNull();
        assertThat(bookRepository.findById(saved.getId())).isPresent();
    }
}
~~~

**@DataJpaTest** tạo test slice tập trung vào JPA repositories và cấu hình liên quan. Nếu ứng dụng đặt repository/entity ngoài package mà test slice tự phát hiện, hãy import cấu hình persistence tương ứng hoặc chỉ rõ cách cấu hình test. Bài test cần database phù hợp; có thể dùng database nhúng trong test hoặc Testcontainers tùy dự án.

Đừng chỉ kết luận cấu hình đúng vì ứng dụng đã khởi động. Một bài test lưu và đọc lại entity giúp xác nhận repository thực sự hoạt động với mapping và database mà test đang dùng.

## 9. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
|---|---|---|
| **Not a managed type: Book** | Entity không nằm trong package được persistence unit quét hoặc thiếu **@Entity** | Kiểm tra **@EntityScan** hoặc package scanning của EntityManagerFactory |
| Không inject được **BookRepository** | Repository package chưa được quét hoặc interface không phải repository hợp lệ | Kiểm tra **@EnableJpaRepositories**, package marker và dependency Spring Data JPA |
| Không tìm thấy bean **entityManagerFactory** | Repository tham chiếu tên mặc định nhưng ứng dụng chỉ khai báo factory với tên khác | Đặt đúng **entityManagerFactoryRef** |
| Không tìm thấy transaction manager | **transactionManagerRef** không khớp tên bean hoặc bean chưa được khai báo | Kiểm tra bean name và kiểu **PlatformTransactionManager** |
| Service không được inject | Service nằm ngoài component scan | Điều chỉnh **scanBasePackages** hoặc **@ComponentScan** |
| Repository truy cập nhầm database | Nhiều cấu hình quét trùng package hoặc tham chiếu nhầm factory | Tách repository package và chỉ định hai bean ref rõ ràng |
| Mapping entity sai schema | Entity đã được quét nhưng bảng/cột không tương thích | Kiểm tra migration, dialect và cấu hình schema |
| Test không thấy repository | Test slice không import cấu hình scanning riêng | Import cấu hình persistence vào test hoặc chỉnh cấu hình test phù hợp |

Khi gặp lỗi, xác định lỗi thuộc phạm vi nào trước: component, repository, entity, EntityManagerFactory hay database. Sau đó kiểm tra package và bean reference của đúng phạm vi đó. Tránh thêm hàng loạt package scan rộng khi chưa biết thành phần nào đang bị thiếu.

## 10. Checklist cấu hình

- [ ] Lớp main nằm ở package gốc hợp lý, không ở default package.
- [ ] Hiểu rõ package mặc định được Spring Boot dùng để auto-configure scanning.
- [ ] Service/controller nằm trong phạm vi component scan.
- [ ] Entity có annotation JPA phù hợp và được đúng persistence unit quét.
- [ ] Repository interface được Spring Data JPA quét.
- [ ] Dùng **basePackageClasses** khi có class marker phù hợp để tránh chuỗi package dễ sai.
- [ ] Không dùng **@EntityScan** thay cho repository scan hoặc component scan.
- [ ] Không dùng **@EnableJpaRepositories** thay cho entity scan.
- [ ] Với nhiều database, mỗi repository group tham chiếu đúng EntityManagerFactory và transaction manager.
- [ ] Mỗi EntityManagerFactory có package entity riêng phù hợp.
- [ ] DataSource, JDBC driver, schema và migration đã được cấu hình.
- [ ] Có test lưu và đọc entity qua repository.

## 11. Kết luận

**@EntityScan** giúp Spring Boot biết package chứa các entity cho cấu hình persistence tự động. **@EnableJpaRepositories** giúp Spring Data JPA tìm interface repository và tạo proxy. **@ComponentScan** chịu trách nhiệm tìm service, controller và các bean thông thường.

Nếu tất cả thành phần nằm dưới package gốc của lớp main và ứng dụng chỉ có một persistence unit, Spring Boot thường tự xử lý được. Khi package tách rời hoặc có nhiều database, khai báo phạm vi quét và các tham chiếu EntityManagerFactory/transaction manager một cách rõ ràng sẽ giúp ứng dụng khởi động đúng và repository truy cập đúng dữ liệu.