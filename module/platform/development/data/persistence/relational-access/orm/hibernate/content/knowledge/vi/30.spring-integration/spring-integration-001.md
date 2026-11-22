# Spring Boot, Jakarta Persistence và Hibernate phối hợp khởi tạo như thế nào

## 1. Bức tranh tổng thể: ba vai trò khác nhau

Khi phát triển ứng dụng Java có lưu trữ dữ liệu quan hệ, ta thường khai báo một vài dependency Spring Boot, viết entity có annotation `@Entity`, tạo repository và sau đó sử dụng `@Transactional`. Nhiều đối tượng hạ tầng xuất hiện mà lập trình viên không khởi tạo bằng `new`: `DataSource`, `EntityManagerFactory`, `EntityManager`, transaction manager, Hibernate `SessionFactory` và các Spring Data repository proxies.

Để hiểu quá trình đó, cần phân biệt ba thành phần:

| Thành phần | Bản chất | Trách nhiệm chính |
|---|---|---|
| **Spring Boot** | Công cụ cấu hình, khởi động và tích hợp ứng dụng Spring | Đọc cấu hình, nhận diện dependency, tạo các Spring beans thích hợp, quản lý vòng đời |
| **Jakarta Persistence (JPA)** | Đặc tả/API chuẩn về persistence cho Java | Định nghĩa `@Entity`, `EntityManager`, `EntityManagerFactory`, lifecycle, query, persistence context |
| **Hibernate ORM** | Một implementation/provider của Jakarta Persistence; đồng thời có API riêng | Đọc metadata mapping, tạo `SessionFactory`, quản lý entities, dirty checking, SQL generation, JDBC và cache |

Spring Data JPA thường đóng vai trò bổ sung:

| Thành phần | Trách nhiệm |
|---|---|
| **Spring Data JPA** | Tạo repository implementation/proxy, hỗ trợ derived queries, `@Query`, pagination và các thao tác truy cập dữ liệu |

**Điểm quan trọng:** Spring Boot không thay thế Hibernate và Jakarta Persistence không tự thực thi SQL. Spring Boot cấu hình các bean; Hibernate thực thi đặc tả JPA; Spring Data JPA xây lớp repository trên JPA.

Ví dụ:

```java
@Entity
public class Product {
    @Id
    @GeneratedValue
    private Long id;

    private String name;
}
```

`@Entity` là annotation của **Jakarta Persistence**, không phải của Spring Boot. Hibernate đọc annotation này để ánh xạ entity. Spring Boot giúp khởi tạo và kết nối Hibernate với database, còn Spring Data có thể sinh repository để thao tác Product.

## 2. Sơ đồ quá trình khởi tạo

Một ứng dụng Boot dùng JPA phổ biến có luồng khởi tạo khái niệm:

```text
Main / SpringApplication.run(...)
                 |
                 v
        Spring ApplicationContext
                 |
           Auto-configuration
                 |
         +-------+--------+
         |                |
         v                v
  Configuration         Classpath:
  application.yml       JDBC driver, Hibernate,
  profiles, env         Spring Data JPA...
         |                |
         +-------+--------+
                 |
                 v
            DataSource
       (connection pool, JDBC)
                 |
                 v
      Entity scanning + mapping
                 |
                 v
   LocalContainerEntityManagerFactoryBean
                 |
                 v
          Hibernate provider
                 |
                 v
     EntityManagerFactory / SessionFactory
                 |
         +-------+------------+
         |                    |
         v                    v
  JpaTransactionManager   Spring Data repositories
         |                    |
         +--------+-----------+
                  |
                  v
          Application services
          @Transactional
                  |
                  v
       EntityManager / Hibernate Session
                  |
                  v
               JDBC / DB
```

Đây là thứ tự **logic** để hiểu các phụ thuộc, không phải cam kết mỗi startup đều tạo bean theo một dãy tuyến tính chính xác. Spring có thể khởi tạo singleton theo dependency graph, và các auto-configuration/dependency thay đổi theo phiên bản.

## 3. Cần những dependency nào?

Trong ứng dụng Spring Boot dùng Hibernate thông qua Spring Data JPA, dependency chính thường là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
```

Starter thường kéo vào các thành phần cần thiết của:

- Spring Data JPA.
- Spring ORM và transaction infrastructure.
- Jakarta Persistence API.
- Hibernate ORM với vai trò provider mặc định khi tương thích với dependency management của Spring Boot.
- Spring JDBC và các thành phần cần thiết để cấu hình persistence.

Đồng thời ứng dụng cần JDBC driver cho database đã chọn, ví dụ PostgreSQL:

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

Không cần tự thêm một bản Hibernate khác phiên bản do Spring Boot quản lý nếu không có lý do chính đáng. Việc ghi đè version Hibernate hoặc Jakarta Persistence API tùy tiện có thể tạo xung đột classpath và lỗi khởi tạo.

Nếu dùng Flyway/Liquibase, thêm dependency tương ứng và module hỗ trợ database khi phiên bản thư viện yêu cầu.

### 3.1. Phân biệt starter JPA và starter JDBC

| Dependency | Kỳ vọng chủ đạo |
|---|---|
| `spring-boot-starter-jdbc` | `DataSource`, JDBC, `JdbcTemplate` và transaction JDBC |
| `spring-boot-starter-data-jpa` | Tích hợp ORM/JPA, Hibernate, repository JPA và transaction JPA |

Starter JDBC một mình không biến class `@Entity` thành managed entity. Muốn dùng JPA, cần provider cùng cấu hình EntityManagerFactory.

## 4. Từ SpringApplication đến ApplicationContext

Điểm bắt đầu thường là:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

`SpringApplication.run()` xây dựng và refresh Spring `ApplicationContext`, tạo môi trường cấu hình và kích hoạt auto-configuration theo điều kiện.

`@SpringBootApplication` bao gồm các khả năng thiết yếu của Spring Boot như configuration, component scanning và auto-configuration. Nhưng annotation này không có nghĩa “cứ có một entity bất kỳ ở đâu thì tự tìm thấy”: vùng package scanning vẫn quan trọng.

Trong startup, Spring đọc nhiều nguồn cấu hình:

- `application.properties` hoặc `application.yml`.
- Profile-specific configuration.
- Environment variables và system properties.
- Command-line arguments và các property sources khác được cấu hình.

Các property được ràng buộc vào đối tượng cấu hình/bean nếu auto-configuration tương ứng được kích hoạt. Không phải mọi property xuất hiện trong file đều chắc chắn được một bean sử dụng: điều kiện classpath và bean overrides vẫn quyết định.

## 5. Auto-configuration: tạo bean có điều kiện, không phải phép màu

Spring Boot dùng cơ chế auto-configuration để tạo bean dựa trên:

1. Class/dependency có trên classpath.
2. Các property đang được cấu hình.
3. Bean do lập trình viên đã tự cung cấp hay chưa.
4. Các điều kiện về môi trường, web/non-web và công nghệ đang sử dụng.

Ví dụ, nếu có JDBC driver và URL phù hợp, Boot có thể tạo `DataSource`. Khi Hibernate/JPA có mặt và điều kiện thích hợp, Boot cấu hình `EntityManagerFactory`, transaction manager và repository infrastructure.

Các nhóm auto-configuration quan trọng trong nhiều phiên bản Boot:

- `DataSourceAutoConfiguration`.
- Auto-configuration cho Hibernate JPA (thường được biết qua `HibernateJpaAutoConfiguration`).
- `TransactionAutoConfiguration` và transaction-manager-related configuration.
- `JpaRepositoriesAutoConfiguration`.

Tên class và chi tiết nội bộ có thể thay đổi giữa các phiên bản Spring Boot. Điều cần hiểu là **conditional configuration**: một bean tự định nghĩa có thể khiến cấu hình mặc định “back off”, hoặc nhiều `DataSource` khiến Boot không biết nên chọn bean nào.

### 5.1. Khi nào auto-configuration không kích hoạt?

Ví dụ:

- Thiếu dependency JPA/Hibernate.
- Có custom `EntityManagerFactory` hoặc `DataSource` phù hợp khiến một phần cấu hình mặc định được bỏ qua.
- Có nhiều candidate bean mà không có quy tắc chọn rõ.
- Auto-configuration bị exclude có chủ đích.
- Property hoặc profile không cung cấp JDBC URL/driver.

Nếu bean không xuất hiện, không nên mặc định kết luận “Spring Boot bị lỗi”; cần xem điều kiện auto-configuration và các bean hiện có.

## 6. DataSource được tạo như thế nào?

`DataSource` là API JDBC để lấy connection đến database. Một cấu hình phổ biến:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/store
spring.datasource.username=store_app
spring.datasource.password=dev_password_only
spring.datasource.driver-class-name=org.postgresql.Driver
```

Đây là ví dụ local development. Production nên dùng secret management hoặc environment/config injection phù hợp, không commit mật khẩu thật vào repository.

Khi classpath và property phù hợp, Spring Boot có thể tạo connection pool, thường là HikariCP trong những cấu hình starter phổ biến.

```text
Application services
         |
         v
   EntityManager / Session
         |
         v
     DataSource
         |
         v
    Connection pool
      /   |    \
     C1   C2   C3  ...
         |
         v
      Database
```

Phân biệt:

- `DataSource` có thể là singleton bean, dùng chung toàn ứng dụng.
- Pool quản lý các JDBC connections.
- Hibernate Session/Persistence Context **không phải** JDBC connection pool.
- Mỗi transaction có thể mượn connection từ pool theo thời điểm cần thiết; thời điểm acquire/release phụ thuộc Hibernate và transaction configuration.

### 6.1. Pool size không phải số Session tối đa

Một ứng dụng có 200 HTTP requests đồng thời nhưng connection pool 20 không nhất thiết có 200 active database connections. Pool sẽ giới hạn số connections đang cho mượn; những request khác có thể chờ.

Nếu pool quá nhỏ, latency tăng vì chờ connection. Nếu quá lớn, DB có thể bị quá tải bởi quá nhiều connections cùng thực thi. Khi startup thành công nhưng runtime chậm, cần đo cả pool metrics, SQL duration và transaction duration.

## 7. Entity scanning: Hibernate biết những class nào là entity?

Giả sử cấu trúc package:

```text
com.example.store
  ├── StoreApplication.java
  ├── domain
  │     ├── Product.java
  │     └── Order.java
  ├── persistence
  │     └── ProductRepository.java
  └── service
        └── ProductService.java
```

Đặt main class ở package cha thường giúp Boot tìm được các component, entities và repositories ở package con theo convention.

Entity:

```java
package com.example.store.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    @GeneratedValue
    private Long id;

    private String sku;
    private String name;

    protected Product() {}
}
```

Nếu entity nằm ngoài vùng được scan, Hibernate có thể không biết class ấy. Khi repository khai báo entity không được managed, startup hoặc lần sử dụng có thể báo lỗi kiểu:

```text
Not a managed type: class com.other.module.Product
```

Có thể định nghĩa vùng entity scanning tường minh:

```java
@SpringBootApplication
@EntityScan(basePackages = "com.example.shared.domain")
public class StoreApplication {}
```

Đây là cách minh họa khi entity nằm ở package khác. Khi dùng nhiều packages, hãy liệt kê đầy đủ các vùng cần thiết. `@EntityScan` điều khiển entity scanning; nó không thay thế component scan hay repository scan.

## 8. Repository scanning khác entity scanning

Spring Data JPA tìm interfaces dạng:

```java
package com.example.store.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
```

Thông qua repository infrastructure, Spring Data tạo proxy/implementation phù hợp cho interface đó. Nhưng nó không biến class Product thành entity; Hibernate phải nhận diện Product từ metadata riêng.

Ba phạm vi quét dễ nhầm:

| Loại quét | Tìm kiếm | Điều chỉnh thường dùng |
|---|---|---|
| Component scanning | `@Service`, `@Repository` class, `@Component`... | `@ComponentScan`, root package |
| Entity scanning | `@Entity`, `@Embeddable`, `@MappedSuperclass` liên quan | `@EntityScan` hoặc cấu hình persistence unit |
| Repository scanning | Spring Data repository interfaces | `@EnableJpaRepositories` |

Ví dụ có thể chỉ định repository package:

```java
@SpringBootApplication
@EntityScan("com.example.store.domain")
@EnableJpaRepositories("com.example.store.persistence")
public class StoreApplication {}
```

Với cấu trúc package chuẩn, thường không cần thêm các annotation này. Chỉ cấu hình tường minh khi convention không đáp ứng hoặc khi có nhiều persistence units.

## 9. Jakarta Persistence cung cấp metadata chuẩn

Jakarta Persistence quy định các annotation và API:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @Column(nullable = false)
    private String orderNumber;

    protected PurchaseOrder() {}
}
```

Các annotation JPA mô tả:

- Identity và primary key.
- Tên bảng, cột, constraint metadata.
- Association giữa entities.
- Fetch semantics.
- Versioning, converters, entity callbacks.
- Persistence lifecycle contract.

Jakarta Persistence là **đặc tả**. Nó không tự quyết định một database cụ thể sẽ dùng SQL gì. Hibernate đóng vai provider diễn giải mapping và phát SQL tương ứng.

### 9.1. Jakarta và javax: vì sao quan trọng?

Các thế hệ Spring Boot/JPA cũ dùng package `javax.persistence.*`. Các thế hệ dựa trên Jakarta Persistence dùng `jakarta.persistence.*`.

Ví dụ code hiện đại:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
```

Không trộn `javax.persistence.Entity` cũ vào ứng dụng mà phiên bản Hibernate/Jakarta yêu cầu `jakarta.persistence.Entity`. Một class có annotation sai namespace có thể không được nhận diện như entity, hoặc gây xung đột dependency.

Khi nâng từ một thế hệ Spring Boot cũ sang thế hệ mới dùng Jakarta, phải xem cả imports, validation namespace, dependencies, libraries và runtime compatibility; không chỉ đổi một dòng cấu hình.

## 10. EntityManagerFactory được xây dựng bởi ai?

Trong môi trường Spring Boot/Spring ORM dùng JPA, một thành phần tích hợp quan trọng là `LocalContainerEntityManagerFactoryBean`.

Nó là Spring FactoryBean xây dựng và quản lý một JPA `EntityManagerFactory` phù hợp với container:

```text
DataSource
     |
Entity packages / mapping metadata
     |
JPA and Hibernate properties
     |
     v
LocalContainerEntityManagerFactoryBean
     |
     v
Hibernate PersistenceProvider
     |
     v
EntityManagerFactory
     |
     v
SessionFactory implementation
```

Ứng dụng không cần gọi:

```java
Persistence.createEntityManagerFactory("myPersistenceUnit");
```

trong cấu hình Boot thông thường. Spring tạo và quản lý `EntityManagerFactory` theo context lifecycle. Một số dự án nhiều persistence units tự khai báo FactoryBean và transaction manager, nhưng đó là cấu hình nâng cao.

### 10.1. Mục đích của EntityManagerFactory

`EntityManagerFactory`:

- Được tạo tương đối tốn kém so với một EntityManager.
- Chứa mapping metadata và hạ tầng provider.
- Là đối tượng được thiết kế để dùng chung giữa nhiều threads.
- Cung cấp EntityManager mới theo nhu cầu.
- Được đóng khi application context kết thúc.

Không tạo EntityManagerFactory cho mỗi HTTP request; điều đó rất tốn kém và phá vỡ lợi ích của metadata/cache chung.

## 11. Hibernate khởi tạo SessionFactory và mapping

Khi JPA provider Hibernate được bootstrap, nó cần:

1. Phát hiện các managed entity classes và mapping metadata.
2. Phân tích `@Id`, generation strategy, association, embeddables, converters...
3. Xây dựng metamodel, entity persisters và collection persisters.
4. Kiểm tra tính hợp lệ của mapping (ví dụ association trỏ tới entity chưa được quản lý).
5. Khởi tạo các service liên quan JDBC, Dialect, type system, cache và event infrastructure.
6. Tạo cơ sở để mở Hibernate Sessions/EntityManagers và dịch query khi runtime.

Ví dụ một lỗi:

```text
Association targets an unknown entity
```

có thể xuất hiện khi class liên quan không được scan, annotation sai namespace hoặc mapping khai báo sai.

### 11.1. EntityManagerFactory và SessionFactory liên hệ thế nào?

Với Hibernate là JPA provider, `SessionFactory` là API native của Hibernate và là cơ sở triển khai `EntityManagerFactory`. Có thể truy cập Hibernate API bằng cách unwrap:

```java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;

SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);
```

Khi dùng JPA portable, ưu tiên interface `EntityManagerFactory` và `EntityManager`. Khi cần Hibernate-specific feature như `StatelessSession`, native statistics hoặc proprietary query API, có thể unwrap một cách có chủ đích.

Không tạo thêm SessionFactory thủ công bên cạnh JPA EntityManagerFactory do Boot đã quản lý trừ khi kiến trúc thực sự cần. Hai factories có thể tạo hai hệ cache, transaction boundary và connection usage khác nhau.

## 12. Hibernate Dialect được xác định ở đâu?

Hibernate cần biết DBMS để sinh SQL, mapping kiểu và chọn khả năng driver/database.

Trong các cấu hình mới, Hibernate có thể xác định Dialect từ JDBC metadata khi kết nối thành công. Một số dự án vẫn cấu hình tường minh khi đặc thù môi trường yêu cầu.

Ví dụ:

```properties
spring.jpa.database-platform=org.hibernate.dialect.PostgreSQLDialect
```

Không sao chép class Dialect của bản Hibernate khác mà không kiểm tra classpath/version. Một Dialect có thể đổi tên, bị loại bỏ hoặc không còn cần cấu hình thủ công.

Nếu Hibernate không lấy được JDBC metadata khi startup, lỗi “Unable to determine Dialect” có thể là **hệ quả của việc không kết nối DB hoặc thiếu JDBC URL**, không nhất thiết là phải thêm một class Dialect.

Quy trình tìm nguyên nhân:

- Xác minh JDBC URL, username/password.
- Xác minh driver có trên classpath.
- Xác minh network và database readiness.
- Xem nguyên nhân gốc trong stack trace.
- Chỉ cấu hình Dialect rõ ràng nếu cần, không dùng để che lỗi connection.

## 13. Database schema xuất hiện lúc nào?

Một vấn đề startup quan trọng là trách nhiệm tạo schema:

| Cách quản lý | Ai tạo hoặc thay schema? | Định hướng |
|---|---|---|
| Hibernate schema generation | Hibernate dựa trên entity mappings | Phù hợp demo/test, cần cẩn thận |
| Flyway | Versioned migration scripts | Thường phù hợp production |
| Liquibase | Changesets và changelog | Thường phù hợp production |
| DBA/automation bên ngoài | Quy trình hạ tầng riêng | Có thể phù hợp doanh nghiệp |

Ví dụ Hibernate DDL setting trong Boot:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

Một số giá trị thường gặp:

| Giá trị | Ý nghĩa khái quát |
|---|---|
| `none` | Không chủ động tạo/cập nhật schema bằng Hibernate |
| `validate` | Đối chiếu schema với mapping và báo lỗi khi không phù hợp |
| `update` | Cố gắng điều chỉnh schema tự động; không phải migration quản lý đầy đủ |
| `create` | Tạo schema mới theo mapping, có thể mất dữ liệu cũ |
| `create-drop` | Tạo schema và xóa khi đóng factory theo cơ chế provider |

Không dùng `create` hoặc `create-drop` trên database chứa dữ liệu cần giữ. `update` cũng không thay thế hệ thống migration có version, review và rollback policy.

### 13.1. Giá trị mặc định không cố định cho mọi môi trường

Spring Boot có thể chọn default DDL action khác nhau tùy loại database (embedded hay external), có schema manager như Flyway/Liquibase hay không, và version. Vì vậy **không dựa vào một default nhớ từ tutorial**. Hãy cấu hình rõ:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

trong môi trường cần đảm bảo database schema đã được migration tạo sẵn.

## 14. Boot phối hợp Flyway/Liquibase với JPA startup

Khi ứng dụng dùng migration tool được Boot tích hợp, ý định thường là:

```text
Create DataSource
        |
        v
Run Flyway/Liquibase migrations
        |
        v
Bootstrap / validate EntityManagerFactory
        |
        v
Initialize JPA repositories
        |
        v
Application ready to serve
```

Spring Boot có cơ chế điều phối database initialization với những beans phụ thuộc database. Chi tiết bean ordering và auto-configuration phụ thuộc phiên bản, nhưng trong cấu hình chuẩn với Flyway/Liquibase, nên để migrations hoàn thành trước khi JPA validation phụ thuộc schema.

### 14.1. Vì sao không nên trộn nhiều cách tạo schema?

Ví dụ cùng lúc:

- Flyway thay cột `order_status`.
- Hibernate `ddl-auto=update` cố sửa schema theo mapping.
- Một file `schema.sql` khác cũng tự chạy.

Sự pha trộn này có thể làm schema drift và khó xác định ai tạo bảng. Chọn **một nguồn quản lý DDL chính**, ví dụ Flyway, rồi dùng Hibernate `validate` để phát hiện mapping không khớp.

### 14.2. schema.sql và data.sql

Spring Boot còn có các cơ chế thực thi SQL initialization scripts tùy cấu hình. Thứ tự chạy `schema.sql`/`data.sql` so với JPA/Flyway không nên được suy đoán. Các property như `spring.jpa.defer-datasource-initialization` có thể ảnh hưởng trình tự trong một số phiên bản.

Trong hệ thống có migrations, nên quản lý seed/reference data có version rõ ràng thay vì để nhiều script initializer cùng chỉnh schema không có thứ tự minh bạch.

## 15. Transaction manager được tạo như thế nào?

Spring transaction abstraction định nghĩa `PlatformTransactionManager`. Với một JPA persistence unit phổ biến, Boot/Spring ORM có thể cấu hình `JpaTransactionManager`.

```text
@Transactional service call
          |
          v
Spring transaction interceptor
          |
          v
JpaTransactionManager
          |
          +--> Bind EntityManager to transaction
          |
          +--> Participate in JDBC transaction
          |
          +--> Flush / commit or rollback
          |
          v
Database commit / rollback
```

`JpaTransactionManager` phối hợp JPA EntityManager và transaction thông qua Spring transaction infrastructure. Nếu ứng dụng dùng JTA hoặc nhiều datasources, transaction manager có thể khác; không assume mọi transaction đều dùng JpaTransactionManager.

### 15.1. Vì sao cần đúng transaction manager?

Nếu có nhiều persistence units hoặc nhiều transaction managers, `@Transactional` phải chọn đúng manager. Nếu không, code có thể dùng EntityManager thuộc factory khác với transaction đang được mở.

Ví dụ chỉ định rõ:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void createOrder(...) {
    // Thao tác với orders EntityManager.
}
```

Tên bean ở ví dụ là minh họa; dự án phải tự cấu hình đúng các managers. Trường hợp một datasource/một EMF thông thường không cần tự cấu hình phức tạp như vậy.

## 16. @PersistenceContext không giống new EntityManager()

Trong Spring, code thường viết:

```java
@Repository
public class ProductDao {
    @PersistenceContext
    private EntityManager entityManager;
}
```

Spring không nhất thiết inject một concrete EntityManager cố định tồn tại suốt đời singleton repository. Với transaction-scoped persistence context mặc định, Spring sử dụng cơ chế **shared EntityManager proxy** để định tuyến các lời gọi tới EntityManager đang gắn với transaction hiện tại hoặc tạo EntityManager phục vụ thao tác theo quy tắc của framework.

```text
Singleton ProductDao
       |
       v
Injected EntityManager proxy
       |
       +--- Transaction A ---> EntityManager A
       |
       +--- Transaction B ---> EntityManager B
       |
       +--- Outside transaction ---> framework-managed behavior
```

Đây là lý do một singleton repository vẫn có thể được nhiều threads dùng đồng thời mà không chia sẻ cùng một EntityManager concrete.

**EntityManager concrete không thread-safe.** Không tự lưu một EntityManager tạo thủ công vào static field rồi dùng chung cho nhiều requests. Spring proxy có thể dùng chung, nhưng persistence context thực phía sau phải tuân theo transaction/thread boundaries.

## 17. Một request @Transactional diễn ra thế nào?

Ví dụ:

```java
@Service
public class ProductService {
    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void renameProduct(Long id, String newName) {
        Product p = products.findById(id)
            .orElseThrow();
        p.rename(newName);
    }
}
```

Trình tự khái niệm:

```text
HTTP request / job
      |
      v
Spring proxy intercepts @Transactional method
      |
      v
Transaction manager begins/joins transaction
      |
      v
EntityManager associated with transaction
      |
      v
Repository uses EntityManager
      |
      v
Hibernate SELECT -> managed Product
      |
      v
Business method changes managed state
      |
      v
Transaction commit triggers flush
      |
      v
Hibernate dirty checking -> UPDATE SQL
      |
      v
JDBC commit, cleanup thread-bound resources
```

Đoạn code không cần gọi `products.save(p)` sau khi sửa một entity đang managed trong transaction, vì dirty checking có thể tự ghi thay đổi khi flush/commit. Tuy nhiên, nếu entity detached hoặc transaction không được áp dụng như kỳ vọng, hành vi sẽ khác.

### 17.1. @Transactional hoạt động qua Spring proxy

Trong chế độ proxy phổ biến:

- Lời gọi vào method thông qua Spring-managed proxy mới được interceptor xử lý.
- Tự gọi một method `@Transactional` khác trong cùng object (*self-invocation*) có thể không đi qua proxy.
- Method không được Spring quản lý không tự có transaction chỉ vì có annotation.
- Visibility, final class/method và proxy mode có thể ảnh hưởng interception theo phiên bản và cấu hình.

Do đó, khi transaction không được mở, cần kiểm tra cách method được gọi và bean proxy, không chỉ nhìn annotation.

## 18. Dirty checking là việc của Hibernate

Hibernate giữ snapshot/tracking của state managed entity. Khi flush, Hibernate xác định thuộc tính thay đổi và tạo SQL phù hợp.

```java
@Transactional
public void changePrice(Long productId, BigDecimal newPrice) {
    Product p = entityManager.find(Product.class, productId);
    p.changePrice(newPrice);
}
```

Nếu Product đang managed và thay đổi được phép:

```sql
UPDATE product
SET price = ?
WHERE id = ?;
```

SQL minh họa; thực tế có thể thêm version column, các cột khác hoặc câu SQL khác tùy mapping và Hibernate configuration.

Spring không phải thành phần so sánh từng field của entity; Hibernate/provider quản lý dirty checking. Spring quản lý transaction boundary và lifecycle của EntityManager.

### 18.1. Flush không đồng nghĩa commit

`entityManager.flush()` đồng bộ các thao tác pending sang database trong transaction, nhưng không commit. Một exception sau flush vẫn có thể khiến transaction rollback.

```text
persist()/change entity
        |
        v
flush() -> SQL đã gửi
        |
        v
rollback -> thay đổi chưa commit bị hoàn tác
```

Điểm này quan trọng khi hiểu các log SQL: thấy INSERT/UPDATE không chứng minh dữ liệu đã commit.

## 19. Spring Data JPA repository được khởi tạo khi nào?

Repository interface:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
```

Spring Data infrastructure quét interface, phân tích domain type/ID và tạo repository proxy với implementation phù hợp. Thực thi các method CRUD hoặc derived queries dựa trên EntityManager và mapping của provider.

```text
ProductRepository interface
          |
          v
Spring Data repository factory
          |
          v
Repository proxy
          |
          +-- findById() --> EntityManager.find()
          |
          +-- save() --> persist() hoặc merge()
          |
          +-- findBySku() --> generated query
          |
          v
Hibernate/JPA provider -> JDBC/DB
```

Đây là mô hình khái niệm. Các method có thể áp dụng repository-level transaction defaults, query strategies và behavior khác theo Spring Data version.

### 19.1. Save không có nghĩa “luôn INSERT”

`JpaRepository.save(entity)` thường dựa vào nhận diện entity mới để chọn `persist()` hoặc `merge()`. Nếu entity có ID tự gán, version hoặc custom `Persistable.isNew()`, cách nhận diện newness cần được thiết kế chính xác.

Không dùng `save()` như “commit ngay một row”; commit do transaction boundary quyết định. `saveAndFlush()` yêu cầu flush sớm hơn nhưng cũng không đồng nghĩa commit.

## 20. Open EntityManager in View (OSIV)

Trong một số ứng dụng Spring Boot web, có thể bật hoặc mặc định cấu hình cơ chế Open EntityManager in View.

OSIV giữ EntityManager mở trong phạm vi xử lý request/view để lazy association có thể được truy cập sau khi service transaction đã kết thúc. Điều này đôi khi giúp tránh `LazyInitializationException`, nhưng dễ che thiết kế fetch plan kém và gây SQL ở tầng controller/serialization.

```text
OSIV disabled:
HTTP request
  -> @Transactional service (EntityManager managed)
  -> commit/close transaction persistence context
  -> serialize DTO

OSIV enabled:
HTTP request
  -> EntityManager còn mở ở web scope
  -> @Transactional service
  -> kết thúc transaction
  -> view/serialization vẫn có thể trigger lazy SQL
  -> request kết thúc mới đóng EntityManager
```

Không nhầm **EntityManager đang mở** với **database transaction đang hoạt động**; OSIV có thể cho phép lazy reads ngoài service transaction boundary.

Trong nhiều REST APIs, một thiết kế chủ động thường là:

```properties
spring.jpa.open-in-view=false
```

Sau đó load đủ dữ liệu trong service transaction bằng fetch join, entity graph hoặc DTO projection. Tuy nhiên, quyết định bật/tắt OSIV phải dựa trên kiến trúc ứng dụng, không có một default áp dụng cho mọi version/kiểu ứng dụng.

## 21. Lazy loading, Session và thời điểm transaction kết thúc

Một association:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

có thể là proxy hoặc được hỗ trợ bằng cơ chế lazy loading tương ứng. Khi code gọi:

```java
order.getCustomer().getName();
```

Hibernate có thể cần truy vấn thêm. Nếu entity đã detached và không còn persistence context hợp lệ để load, có thể xuất hiện `LazyInitializationException`.

Giải pháp thường không phải bật EAGER cho mọi association:

- Xác định dữ liệu API cần trả.
- Dùng query projection để lấy đúng field.
- Dùng `JOIN FETCH` / EntityGraph có kiểm soát.
- Tránh serialize entity graph trực tiếp.
- Đặt database work trong transaction/service boundary rõ.

Hiểu Spring Boot startup giúp biết Session từ đâu ra; hiểu transaction lifecycle giúp biết Session còn dùng được đến khi nào.

## 22. Read-only transaction là gợi ý, không phải tường lửa ghi

Ví dụ:

```java
@Transactional(readOnly = true)
public ProductView getProduct(long id) {
    return repository.findViewById(id);
}
```

`readOnly=true` có thể ảnh hưởng flush mode, hint hoặc cách transaction infrastructure tương tác với provider. Nhưng nó **không phải một bảo đảm an ninh rằng mọi SQL write sẽ bị DBMS cấm** trong mọi cấu hình.

Khi cần đảm bảo một connection không thể ghi, sử dụng database permissions/read-only database roles hoặc cấu hình transaction/database phù hợp và kiểm thử. Đừng dùng `@Transactional(readOnly = true)` làm cơ chế authorization.

## 23. Tích hợp Validation và entity callbacks

Hibernate xử lý JPA lifecycle và có thể tích hợp Bean Validation khi provider/dependency được cấu hình phù hợp:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    @NotBlank
    private String email;

    @PrePersist
    void beforeInsert() {
        // Lifecycle callback.
    }
}
```

Trong hệ Jakarta, annotation validation tương ứng ở package `jakarta.validation.*` nếu sử dụng Jakarta Validation. Tùy dependency/configuration, validation có thể được gọi tại lifecycle events theo provider.

Phân biệt:

- Spring MVC validation cho request DTO không đồng nghĩa JPA entity validation.
- Hibernate ORM persistence provider không giống Hibernate Validator library.
- Database constraints vẫn là lớp bảo vệ cuối cùng đối với nhiều invariant dữ liệu.
- Bulk HQL/native DML không thực hiện đầy đủ entity callbacks/validation per entity như thao tác managed object.

Đừng dựa vào một `@PreUpdate` callback để đảm bảo audit của mọi bulk update do JDBC/native SQL thực hiện.

## 24. Cấu hình JPA/Hibernate properties đi qua Spring Boot như thế nào?

Spring Boot có các nhóm property:

| Nhóm | Ví dụ | Tác động |
|---|---|---|
| `spring.datasource.*` | URL, username, Hikari pool | JDBC DataSource |
| `spring.jpa.*` | show-sql, open-in-view, database-platform | JPA integration |
| `spring.jpa.hibernate.*` | ddl-auto | Hibernate schema management tích hợp |
| `spring.jpa.properties.*` | hibernate.jdbc.batch_size | Provider-specific Hibernate properties |

Ví dụ:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/store
spring.datasource.username=store_app
spring.datasource.password=dev_password_only

spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

Cấu hình này giả định đã tạo database và schema bằng migration/DDL thích hợp. Không dùng password giả của ví dụ ngoài môi trường local.

### 24.1. Cẩn trọng với property name

Một số property Hibernate khác nhau theo major version. Chỉ dùng property có trong documentation/runtime version của dự án. Đừng nhét mọi setting từ nhiều tutorial vào cấu hình rồi tin rằng tất cả đều được áp dụng.

### 24.2. Profile theo môi trường

Ví dụ:

```text
application.yml
application-dev.yml
application-test.yml
application-prod.yml
```

Ở development có thể bật SQL logging. Ở production nên giới hạn SQL/bind logs, dùng secrets và cấu hình connection pool, migrations, timeouts, observability thích hợp.

## 25. Lưu ý về logging SQL và tham số

Khi điều tra startup hoặc truy vấn:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
```

Cấu hình này phù hợp để minh họa trong local environment, nhưng output `show-sql` không phải một hệ thống tracing/metrics đầy đủ và có thể gây overhead.

Muốn debug thực tế nên cân nhắc logger Hibernate SQL và bind categories **đúng với version**:

- Log SQL template để hiểu query shape.
- Log bind parameters khi thật sự cần và với dữ liệu test.
- Sử dụng connection pool/DB metrics để theo dõi thời gian chờ.
- Không log password, token, PII hoặc raw payload nhạy cảm trong production.

Một request chậm có thể do chờ connection, query plan, N+1, lock hoặc serialization; thấy một SQL trong log không đủ để xác định bottleneck.

## 26. Ví dụ hoàn chỉnh: ứng dụng Spring Boot + Hibernate

### 26.1. Entity

```java
package com.example.store.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Version
    private long version;

    protected Product() {}

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Name required");
        }
        this.name = newName;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
}
```

### 26.2. Repository

```java
package com.example.store.persistence;

import com.example.store.domain.Product;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
```

### 26.3. Service

```java
package com.example.store.service;

import com.example.store.domain.Product;
import com.example.store.persistence.ProductRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long createProduct(String sku, String name) {
        Product product = new Product(sku, name);
        repository.save(product);
        return product.getId();
    }

    @Transactional
    public void renameProduct(Long id, String name) {
        Product product = repository.findById(id)
            .orElseThrow();
        product.rename(name);
    }

    @Transactional(readOnly = true)
    public String findName(Long id) {
        Product product = repository.findById(id)
            .orElseThrow();
        return product.getName();
    }
}
```

`createProduct()` có thể cần flush sớm để ID khả dụng tùy generator; nhiều generator cấp ID trước INSERT, nhưng không giả định toàn bộ generator/DBMS đều giống nhau. `renameProduct()` dựa trên dirty checking khi Product đang managed.

### 26.4. Cấu hình schema

Ví dụ migration SQL:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(128) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    version BIGINT NOT NULL
);
```

Đây chỉ là DDL mô tả cấu trúc. Nếu dùng sequence/identity ID generator, schema phải có cơ chế sinh ID phù hợp với `@GeneratedValue` và DBMS. Không dùng DDL này như migration production hoàn chỉnh nếu chưa xác định ID generator.

### 26.5. Luồng khởi tạo ứng dụng ví dụ

```text
Spring Boot starts
  -> DataSource from datasource configuration
  -> Migration creates products table
  -> Hibernate scans Product
  -> Hibernate validates mapping against schema
  -> EntityManagerFactory ready
  -> Spring Data creates ProductRepository proxy
  -> Spring wires ProductService
  -> @Transactional service methods use Hibernate
```

Ví dụ minh họa kiến trúc; startup thực tế còn nhiều bean và conditional logic khác.

## 27. Tại sao cùng một entity có thể “không tồn tại” trong Hibernate?

Một class Java có `@Entity` vẫn có thể không được quản lý nếu:

- Nằm ngoài entity scanning packages.
- Dùng nhầm `javax.persistence.Entity` trong runtime Jakarta.
- Thiếu dependency JPA/Hibernate.
- Có nhiều persistence units nhưng class được đăng ký ở factory khác.
- Bị loại bởi custom mapping configuration.
- Class không đáp ứng quy tắc entity/mapping của provider.

Các lỗi thường thấy:

```text
Not a managed type
Unknown entity
Unable to locate persister
Association targets an unknown entity
```

Phương pháp tìm nguyên nhân:

1. Kiểm tra import annotation.
2. Kiểm tra package entity và root package Boot application.
3. Kiểm tra `@EntityScan`/persistence unit configuration.
4. Kiểm tra EntityManagerFactory nào được repository dùng.
5. Kiểm tra mapping diagnostics.

Không xử lý bằng cách tạo SessionFactory thứ hai trong service: làm vậy thường làm kiến trúc phức tạp hơn và không sửa đúng nguyên nhân.

## 28. Lỗi kết nối database khi startup

Ví dụ lỗi:

```text
Connection refused
Authentication failed
Could not obtain JDBC Connection
Unable to determine Dialect
```

Nguyên nhân có thể:

- Database chưa chạy hoặc chưa ready.
- JDBC URL/port/hostname sai.
- Username/password sai.
- Network/firewall/DNS chặn.
- JDBC driver không có trên classpath.
- Container application dùng `localhost` để chỉ chính container thay vì DB container.
- Pool timeout trong lúc khởi tạo.

Nếu chạy Docker Compose, JDBC hostname thường là service name trên network nội bộ, không phải `localhost` của máy host; cần xem network architecture thực tế.

Khi Hibernate báo không xác định Dialect, hãy đọc **root cause** của JDBC metadata acquisition trước khi ép một Dialect class vào cấu hình.

## 29. Lỗi schema validation và SQL

Nếu bật:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

mà schema thiếu bảng/cột hoặc kiểu khác mapping, startup có thể thất bại với thông báo về schema validation.

Ví dụ:

```text
Schema-validation: missing table [products]
```

Đây là tín hiệu tốt ở môi trường có migration kiểm soát: ứng dụng không nên phục vụ traffic khi mapping và schema quan trọng không khớp.

Các bước:

1. Kiểm tra migration đã chạy trên đúng database/schema chưa.
2. Kiểm tra `DataSource` dùng URL/user/schema mong đợi.
3. Kiểm tra tên bảng/cột và schema qualifier.
4. Kiểm tra naming strategy, quoted identifiers, JDBC type.
5. Không đổi `validate` thành `update` trên production chỉ để qua startup.

## 30. Khi có nhiều DataSource hoặc nhiều persistence units

Một ứng dụng có thể đọc từ DB reporting và ghi vào DB chính. Lúc đó:

```text
Primary DB                          Reporting DB
    |                                    |
DataSource A                         DataSource B
    |                                    |
EntityManagerFactory A               EntityManagerFactory B
    |                                    |
TransactionManager A                 TransactionManager B
    |                                    |
Repositories A                       Repositories B
```

Thông thường cần cấu hình rõ:

- Bean names/qualifiers cho DataSources.
- `LocalContainerEntityManagerFactoryBean` cho từng persistence unit.
- Package entities thuộc từng EMF.
- Repository scan gắn với đúng `entityManagerFactoryRef` và `transactionManagerRef`.
- Transaction boundaries và distributed consistency strategy.

Ví dụ ý tưởng:

```java
@EnableJpaRepositories(
    basePackages = "com.example.orders.repo",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
class OrdersJpaConfiguration {
    // Các @Bean cần thiết cho orders DataSource/EMF/TM.
}
```

Đây là đoạn khai báo minh họa, chưa phải cấu hình đa datasource hoàn chỉnh. Không kỳ vọng một `@Transactional` thường tự tạo một transaction phân tán trên hai DB độc lập; cần JTA/distributed transaction hoặc thiết kế eventual consistency/outbox khi nghiệp vụ yêu cầu.

## 31. Spring transaction proxy và ngoại lệ rollback

Một method:

```java
@Transactional
public void placeOrder(...) {
    // Persist Order và cập nhật tồn kho.
}
```

trong cấu hình Spring mặc định thường rollback khi có unchecked exception (`RuntimeException` và `Error`), còn checked exception có quy tắc khác nếu không cấu hình thêm. Có thể sử dụng:

```java
@Transactional(rollbackFor = Exception.class)
public void importData() throws Exception {
    // Thực thi các thao tác persistence.
}
```

Không dùng `rollbackFor=Exception.class` theo phản xạ cho mọi method; cần xác định exception nào thực sự yêu cầu rollback.

Một lỗi tinh vi là catch exception bên trong transaction rồi không rethrow hoặc không đánh dấu rollback:

```java
@Transactional
public void doWork() {
    try {
        repository.save(...);
    } catch (RuntimeException ex) {
        // Nếu nuốt lỗi, transaction interceptor có thể
        // không biết phải rollback theo kỳ vọng.
    }
}
```

Transaction có thể vẫn bị đánh dấu rollback-only bởi tầng hạ tầng trong một số tình huống, dẫn tới `UnexpectedRollbackException`. Cần hiểu transaction state và error propagation thay vì chỉ nhìn annotation.

## 32. Khi nào Hibernate thực sự mở JDBC Connection?

Mở EntityManager/Hibernate Session không luôn đồng nghĩa ngay lập tức mượn một JDBC connection.

Tùy connection handling mode và transaction:

- Session có thể được tạo trước khi truy cập DB.
- Khi cần SQL, Hibernate lấy connection từ DataSource.
- Connection được sử dụng cho transaction và có thể được trả pool theo mode tương ứng.
- Flush/commit có thể cần connection nếu có SQL pending.

Vì thế:

```text
@Transactional method starts
        |
        v
Session/persistence context available
        |
        +--> no SQL yet? JDBC connection acquisition may be deferred
        |
        v
First DB access / flush
        |
        v
Borrow connection from pool
```

Đây là mô hình phụ thuộc configuration/provider. Khi đo pool wait hoặc connection leaks, xem JDBC instrumentation và Hibernate connection handling strategy của version đang chạy.

## 33. Sự khác nhau giữa EntityManager, Session và JDBC Connection

| Đối tượng | Ai cung cấp | Ý nghĩa |
|---|---|---|
| `EntityManager` | Jakarta Persistence API, Hibernate implementation | Quản lý persistence context và JPA operations |
| `Session` | Hibernate API | Native ORM session, hỗ trợ thêm chức năng Hibernate |
| `Connection` | JDBC DataSource/driver | Kết nối vật lý/logical tới database để thực thi SQL |

Trong code:

```java
@PersistenceContext
private EntityManager em;

public void inspectHibernateSession() {
    Session session = em.unwrap(Session.class);
    // Sử dụng API Hibernate-specific khi cần.
}
```

Không nhầm `EntityManager.close()` với `Connection.close()` hoặc `SessionFactory.close()`:

- EntityManager/Session là unit-of-work scope.
- Connection có thể được trả về pool khi đóng/hoàn tất sử dụng.
- EntityManagerFactory/SessionFactory tồn tại lâu dài theo application context.

Đừng đóng EntityManager được Spring inject bằng shared proxy theo cách tùy tiện; để framework quản lý lifecycle trong transaction/request phù hợp.

## 34. Tích hợp cache qua Hibernate, không phải Spring Cache mặc định

Spring có abstraction `@Cacheable` cho method caching:

```java
@Cacheable("productView")
public ProductView loadProductView(long id) {
    // ...
}
```

Hibernate cũng có second-level cache và query cache cho entity/query state.

| Loại cache | Điều được cache | Ai quản lý |
|---|---|---|
| Spring Cache | Kết quả method theo key | Spring Cache abstraction/provider |
| Hibernate L2 | Entity/collection state giữa các sessions | Hibernate và cache provider |
| Hibernate query cache | Kết quả query cacheable | Hibernate và cache provider |
| First-level cache | Managed entities trong persistence context | EntityManager/Session |

Không đồng nhất hai cơ chế chỉ vì cùng dùng một cache backend. Bật `@Cacheable` Spring không mặc nhiên bật Hibernate L2, và bật Hibernate L2 không làm mọi service method được Spring cache.

Nếu kết hợp nhiều lớp, cần thiết kế invalidation rõ ràng; nếu không, Spring method cache có thể trả DTO cũ dù Hibernate L2 đã được invalidated chính xác.

## 35. @DataJpaTest: kiểm tra bootstrap với cấu hình test

Spring Boot hỗ trợ slice test như `@DataJpaTest` cho JPA/repository:

```java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository products;

    @Test
    void findsProductBySku() {
        Product p = products.save(new Product("SKU-1", "Book"));

        Optional<Product> found = products.findBySku("SKU-1");

        assertThat(found).isPresent();
    }
}
```

Đây là ví dụ test minh họa, giả định dự án có JUnit/assertion dependencies phù hợp. `@DataJpaTest` tập trung vào JPA components, thường chạy trong transaction có rollback ở cuối test và có thể thay DataSource bằng embedded database khi phù hợp.

Nếu production là PostgreSQL nhưng test dùng H2, test có thể bỏ sót khác biệt về DDL, type, sequence, JSON, khóa và transaction.

### 35.1. Dùng Testcontainers với database đích

Ví dụ:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class ProductRepositoryPostgresIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("store_test");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url", postgres::getJdbcUrl);
        registry.add(
            "spring.datasource.username", postgres::getUsername);
        registry.add(
            "spring.datasource.password", postgres::getPassword);
    }
}
```

Code là khung minh họa; cần imports/dependencies Testcontainers, JUnit và Spring Boot test phù hợp. Với các phiên bản Boot hỗ trợ service connection có thể dùng annotation tích hợp thay cho DynamicPropertySource. Điều cốt lõi là test repository và migrations trên **đúng loại database** cần triển khai.

## 36. Các kiểm tra startup thực tế

Khi một ứng dụng không khởi tạo được JPA, nên kiểm tra theo dependency chain:

```text
1. Spring Boot application context có load?
             |
             v
2. DataSource bean có được tạo?
             |
             v
3. JDBC connection có mở được?
             |
             v
4. Migration/schema có sẵn?
             |
             v
5. EntityManagerFactory có build được?
             |
             v
6. Entities/associations map hợp lệ?
             |
             v
7. TransactionManager chọn đúng?
             |
             v
8. Repository proxies có khởi tạo?
             |
             v
9. Service @Transactional hoạt động?
```

Một lỗi “không inject được ProductRepository” có thể bắt nguồn từ lỗi build EntityManagerFactory, và lỗi build EMF có thể bắt nguồn từ database không kết nối được. Đọc **root cause** và chain của startup exception trước khi sửa bean injection ở lớp trên.

### 36.1. Conditions evaluation report

Spring Boot có cơ chế debug báo auto-configuration conditions, thường có thể bật trong phiên chạy development:

```text
java -jar app.jar --debug
```

Report cho biết auto-configuration nào matched/unmatched và lý do. Kết hợp với startup logs để xác định vì sao DataSource, Hibernate JPA hoặc Spring Data repository configuration không hoạt động.

Không bật debug logging rộng rãi liên tục ở production khi không cần; log có overhead và có thể chứa thông tin cấu hình nhạy cảm.

## 37. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Hướng xử lý |
|---|---|---|
| Nghĩ Spring Boot tự chạy SQL của ORM | Nhầm tầng trách nhiệm | Spring cấu hình; Hibernate triển khai JPA |
| Nghĩ JPA là một ORM implementation | Không biết provider nào đang chạy | Phân biệt Jakarta Persistence API và Hibernate provider |
| Trộn `javax.persistence` với `jakarta.persistence` | Entity không nhận diện hoặc dependency lỗi | Dùng đúng namespace theo stack |
| Đặt entity ngoài vùng scan | `Not a managed type` | Sửa packages hoặc `@EntityScan` |
| Repository nằm ngoài scan | Không có bean repository | `@EnableJpaRepositories` phù hợp |
| Tự tạo SessionFactory nữa | Hai factory/caches/transaction boundaries | Dùng EMF do Spring quản lý |
| Không có JDBC driver/URL | DataSource/metadata lỗi | Kiểm tra driver và datasource |
| Ép Dialect để che lỗi kết nối | Root cause vẫn còn | Xử lý JDBC connection trước |
| Dùng `ddl-auto=create` trên production | Rủi ro mất dữ liệu | Migration + validate |
| Trộn Flyway và Hibernate update | Schema drift | Một nguồn quản lý DDL chính |
| Dùng EntityManager concrete singleton | Không thread-safe | Dùng Spring shared proxy/transaction scope |
| `@Transactional` tự gọi nội bộ | Interceptor không chạy như kỳ vọng | Gọi qua Spring bean proxy hoặc đổi thiết kế |
| Catch exception rồi nuốt lỗi | Rollback semantics bất ngờ | Quản lý propagation/rollback rõ |
| Gọi `save()` là tưởng commit | Data chưa được commit | Xác định transaction boundary |
| Bật EAGER cho mọi association | SQL lớn/N+1 ở nơi khác | Thiết kế fetch plan |
| Bật OSIV để che mọi lazy issue | SQL ngoài service transaction | DTO/projection và boundary rõ |
| Nhầm Spring Cache với Hibernate L2 | Invalidation sai | Thiết kế từng cache layer |
| Test H2 rồi suy ra Postgres đúng | SQL/DDL khác | Testcontainers DB đích |
| Có hai DataSource nhưng không chọn EMF/TM | Ambiguous bean hoặc transaction sai | Explicit qualifiers/config |

## 38. Quy trình dựng ứng dụng từ đầu

**Bước 1 — Chọn stack/version tương thích.** Spring Boot, Spring Data, Jakarta Persistence, Hibernate và JDBC driver phải thuộc một dependency set phù hợp. Ưu tiên dependency management của Boot.

**Bước 2 — Thêm starter JPA và JDBC driver.** Không thêm nhiều provider JPA không cần thiết.

**Bước 3 — Cấu hình DataSource.** Đảm bảo database/connection pool hoạt động, credentials được quản lý an toàn.

**Bước 4 — Tạo entities đúng Jakarta namespace.** Đặt dưới package được scan; xác định identifier và associations.

**Bước 5 — Quản lý migrations.** Dùng Flyway/Liquibase hoặc cơ chế DDL được chọn; ở production nên validate mapping thay vì tự thay schema.

**Bước 6 — Tạo repositories.** Spring Data scan interface và dùng đúng EntityManagerFactory.

**Bước 7 — Đặt transaction tại service.** Viết domain methods, định nghĩa rollback/propagation hợp lý.

**Bước 8 — Thiết kế fetch plan.** Không để view/API tự ý traverse lazy graph ngoài transaction.

**Bước 9 — Kiểm thử với DBMS đích.** Repository integration test, migration, concurrency và schema alignment.

**Bước 10 — Quan sát khi chạy.** SQL counts, JDBC pool, transaction duration, database locks, p95 latency và startup failures.

## 39. Cách tự diễn giải một ứng dụng Spring Boot/JPA

Khi đọc code:

```java
@SpringBootApplication
class Application {}

@Entity
class Customer { ... }

interface CustomerRepository
    extends JpaRepository<Customer, Long> {}

@Service
class CustomerService {
    @Transactional
    public void register(...) { ... }
}
```

hãy đặt những câu hỏi:

- **Boot:** Dependency/property nào kích hoạt DataSource, JPA và repository auto-configuration?
- **Jakarta Persistence:** Customer được map bằng annotations nào? ID, association, lifecycle contract gì?
- **Hibernate:** EntityManagerFactory được provider build ra sao? SQL được sinh lúc nào? Mapping/dirty checking/versioning thế nào?
- **Spring Data:** Repository proxy thực thi method bằng EntityManager nào?
- **Spring transaction:** Method register được gọi qua proxy không? Transaction manager và persistence context scope là gì?
- **Database:** Schema do ai quản lý? Connection, transaction isolation, index và constraints có đúng không?

Trả lời được các câu hỏi này thường giúp xác định đúng tầng khi có lỗi thay vì sửa nhầm annotation hoặc property.

## 40. Sơ đồ quyết định khi có lỗi khởi tạo

```text
                Application startup failed
                           |
                           v
                Root cause thuộc lớp nào?
                  /        |         \
                 /         |          \
                v          v           v
          DataSource    Entity mapping  Repository
             |             |              |
             v             v              v
         URL, driver,   Entity scan,    Repo scan,
         credentials,   annotation,     EMF reference,
         network        ID/relation     query methods
             |             |              |
             +-------------+--------------+
                           |
                           v
                 Schema/migrations match?
                        /       \
                      NO        YES
                      |          |
                      v          v
               Run migrations   Check tx manager,
               or fix mapping   proxy, lifecycle
                      \          /
                       \        /
                        v      v
                    Re-run startup
                    with DB integration test
```

## 41. Tổng kết

Spring Boot, Jakarta Persistence và Hibernate phối hợp theo ba tầng trách nhiệm rõ ràng:

- **Spring Boot** đọc cấu hình, áp dụng auto-configuration có điều kiện, tạo và quản lý các beans như DataSource, EntityManagerFactory, transaction manager và repository infrastructure.
- **Jakarta Persistence** định nghĩa mô hình entity, persistence context và API `EntityManager`/`EntityManagerFactory` mà ứng dụng dùng.
- **Hibernate** đóng vai JPA provider, phân tích mapping, tạo Hibernate SessionFactory, quản lý entity lifecycle, lazy loading, dirty checking, cache và SQL/JDBC.
- **Spring Data JPA** tạo repository proxies trên nền tảng EntityManager; **Spring transaction** bảo đảm những thao tác đó dùng persistence context và transaction phù hợp.

Trình tự quan trọng về mặt ý nghĩa là: **configuration → DataSource → database initialization/migration → EntityManagerFactory/Hibernate → transaction/repository infrastructure → service methods**. Startup thực tế tuân theo dependency graph của ApplicationContext và có thể thay đổi theo phiên bản hoặc cấu hình custom.

Nắm rõ ai tạo bean, ai quản lý transaction, ai quyết định SQL và ai quản lý schema giúp giải quyết các lỗi phổ biến như `Not a managed type`, thiếu repository bean, lỗi Dialect do không kết nối DB, transaction không kích hoạt, `LazyInitializationException` và schema validation failure. Trong production, nên kết hợp migrations có version, transaction boundary rõ ràng, fetch plan chủ động và integration tests trên DBMS đích.
