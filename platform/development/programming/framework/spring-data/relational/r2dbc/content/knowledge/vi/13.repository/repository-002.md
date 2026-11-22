# Quét Repository và liên kết với hạ tầng R2DBC

## 1. Repository được phát hiện và kết nối với R2DBC như thế nào?

Trong Spring Data R2DBC, một repository thường chỉ là một interface khai báo các thao tác dữ liệu. Ví dụ:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Interface này không tự mở kết nối và cũng không chứa phần triển khai SQL. Khi ứng dụng khởi động, Spring Data tìm các repository interface trong những package được cấu hình, tạo implementation dạng proxy và liên kết proxy đó với hạ tầng truy cập dữ liệu R2DBC.

Chuỗi thành phần có thể hình dung như sau:

~~~text
Spring Boot application / @EnableR2dbcRepositories
                    |
                    v
       Quét các repository interface
                    |
                    v
        Repository factory tạo proxy
                    |
                    v
          R2dbcEntityOperations
          (thường là R2dbcEntityTemplate)
                    |
             +------+------+
             |             |
             v             v
      MappingR2dbcConverter  DatabaseClient
             |             |
             +------+------+
                    |
                    v
             ConnectionFactory
                    |
                    v
               R2DBC Driver
                    |
                    v
             Relational Database
~~~

Mỗi thành phần có một trách nhiệm:

- **Repository scanning** tìm interface và đăng ký bean repository.
- **Repository proxy/factory** tạo implementation cho các phương thức CRUD, derived query và query được khai báo.
- **R2dbcEntityOperations** cung cấp các thao tác đọc/ghi entity; implementation phổ biến là **R2dbcEntityTemplate**.
- **MappingR2dbcConverter** chuyển đổi giữa hàng dữ liệu và object Java theo mapping metadata.
- **DatabaseClient** thực thi SQL, bind tham số và đọc kết quả từ R2DBC.
- **ConnectionFactory** cung cấp kết nối theo SPI của R2DBC; driver cụ thể giao tiếp với database.

Hiểu chuỗi này giúp xử lý những lỗi thường gặp: repository không được tìm thấy, proxy không có bean hạ tầng phù hợp, nhiều ConnectionFactory gây mơ hồ, hoặc repository đang trỏ đến nhầm database.

## 2. Repository scanning tìm những gì?

Repository scanning tìm các **interface repository** đáp ứng quy tắc của Spring Data trong package được chỉ định. Ví dụ:

~~~text
com.example.shop
├── ShopApplication.java
├── customer
│   ├── Customer.java
│   └── CustomerRepository.java
├── order
│   ├── Order.java
│   └── OrderRepository.java
└── config
    └── R2dbcConfiguration.java
~~~

Với ứng dụng Spring Boot có class **@SpringBootApplication** tại package gốc **com.example.shop**, cấu hình auto-configuration mặc định có thể phát hiện các repository nằm trong package gốc và các package con.

Điều cần phân biệt:

- Repository scanning tìm interface như **CustomerRepository**.
- Entity mapping sử dụng metadata của kiểu như **Customer**, thường được đánh dấu bằng **@Table**.
- Database schema chứa bảng thật như **customers**.

**Quét repository không phải là quét database để tìm bảng**, cũng không tự tạo bảng. Spring Data không đọc toàn bộ schema rồi tự sinh repository cho từng bảng. Bảng được xác định thông qua mapping metadata hoặc SQL mà ứng dụng khai báo; việc tạo và thay đổi schema thường do migration hoặc quy trình khởi tạo database đảm nhiệm.

## 3. Cấu trúc repository và entity tối thiểu

Ví dụ entity:

~~~java
package com.example.shop.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        String email,
        String status
) {}
~~~

Repository:

~~~java
package com.example.shop.customer;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);
}
~~~

Spring Data có thể tạo implementation cho các thao tác CRUD kế thừa từ **ReactiveCrudRepository** và suy ra truy vấn từ tên phương thức như **findByEmail**, nếu kiểu và thuộc tính được mapping hợp lệ.

Repository không cần annotation **@Repository** trong trường hợp thông thường. Việc phát hiện interface và tạo proxy được thực hiện bởi repository infrastructure. Thêm **@Repository** lên interface không thay thế cho cấu hình repository scanning.

## 4. Spring Boot auto-configuration cho một R2DBC database

Với một database chính, Spring Boot thường là cách thiết lập ngắn gọn nhất.

### 4.1. Khai báo dependency

Ví dụ Gradle Groovy DSL cho PostgreSQL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

Starter cung cấp tích hợp Spring Data R2DBC. Driver PostgreSQL cung cấp kết nối theo R2DBC SPI. Nên dùng Spring Boot dependency management để chọn các phiên bản tương thích.

### 4.2. Cấu hình kết nối

Trong application.yml:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: app
    password: ${DB_PASSWORD}
~~~

Spring Boot có thể dùng URL và credential để cấu hình **ConnectionFactory**, sau đó tạo các thành phần R2DBC cần thiết nếu ứng dụng không tự khai báo bean thay thế.

Không nên commit password thật vào source code. Hãy truyền giá trị qua biến môi trường hoặc secret store của môi trường triển khai.

### 4.3. Đặt class ứng dụng ở package gốc

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Nếu **CustomerRepository** nằm trong **com.example.shop.customer**, package này là package con của **com.example.shop**, nên repository có thể được phát hiện theo cấu hình mặc định của Spring Boot.

Với cấu trúc đơn database thông thường, không cần thêm **@EnableR2dbcRepositories** chỉ để quét package con mặc định. Chỉ cấu hình tường minh khi cần đổi phạm vi quét, kiểm soát package hoặc liên kết repository với một bộ hạ tầng R2DBC cụ thể.

## 5. Cấu hình repository scanning tường minh bằng @EnableR2dbcRepositories

Spring Data R2DBC cung cấp annotation **@EnableR2dbcRepositories** trong package:

~~~java
import org.springframework.data.r2dbc.repository.config.EnableR2dbcRepositories;
~~~

Annotation này bật repository infrastructure và cho phép xác định package chứa repository interface.

### 5.1. Dùng basePackages

~~~java
@Configuration
@EnableR2dbcRepositories(
        basePackages = {
                "com.example.shop.customer",
                "com.example.shop.order"
        }
)
class RepositoryConfiguration {
}
~~~

**basePackages** nhận tên package dưới dạng chuỗi. Cách này dễ cấu hình nhiều package, nhưng tên package là string nên việc đổi tên package có thể không được IDE cập nhật ở mọi nơi.

### 5.2. Dùng basePackageClasses

Một lựa chọn an toàn hơn là dùng class marker:

~~~java
@Configuration
@EnableR2dbcRepositories(
        basePackageClasses = {
                CustomerRepository.class,
                OrderRepository.class
        }
)
class RepositoryConfiguration {
}
~~~

Spring Data dùng package chứa các class được chỉ định làm điểm bắt đầu quét. Cách này có kiểm tra kiểu ở compile time và thuận tiện khi refactor package.

Có thể tạo một class marker riêng nếu muốn tránh phụ thuộc cấu hình vào repository cụ thể:

~~~java
package com.example.shop.customer;

public interface CustomerRepositoryPackage {
}
~~~

Sau đó dùng:

~~~java
@EnableR2dbcRepositories(
        basePackageClasses = CustomerRepositoryPackage.class
)
~~~

Marker chỉ cần nằm trong package muốn quét; nó không phải repository và không cần kế thừa interface Spring Data.

### 5.3. Khi nào cần dùng annotation tường minh?

Có thể dùng **@EnableR2dbcRepositories** khi:

- Repository nằm ngoài package gốc của class **@SpringBootApplication**.
- Ứng dụng có nhiều nhóm repository và cần phân chia package.
- Ứng dụng có nhiều database hoặc nhiều **R2dbcEntityOperations**.
- Muốn chỉ định bean entity operations mà một nhóm repository sử dụng.
- Ứng dụng không dựa vào auto-configuration mặc định của Spring Boot.

Không nên đặt annotation ở nhiều cấu hình cùng quét một package một cách vô tình. Việc đăng ký repository trùng lặp có thể gây lỗi bean hoặc khiến ứng dụng khó xác định repository thuộc cấu hình nào.

## 6. Repository proxy liên kết với hạ tầng nào?

Khi một repository interface được phát hiện, Spring Data tạo một proxy triển khai interface đó. Proxy xử lý các phương thức repository bằng repository factory và các thành phần persistence tương ứng.

Ví dụ, lời gọi:

~~~java
customerRepository.findById(10L);
~~~

được xử lý theo hướng khái quát:

1. Proxy nhận lời gọi phương thức repository.
2. Repository infrastructure xác định thao tác cần thực hiện.
3. Repository sử dụng entity operations đã được cấu hình.
4. Mapping metadata của **Customer** xác định bảng và cột.
5. DatabaseClient tạo và thực thi SQL thông qua ConnectionFactory.
6. MappingR2dbcConverter chuyển hàng kết quả thành Customer.
7. Repository phát kết quả qua **Mono<Customer>**.

Đối với derived query, Spring Data phân tích tên phương thức và metadata property để xây dựng truy vấn. Với **@Query**, câu SQL được khai báo rõ ràng. Cả hai vẫn sử dụng hạ tầng R2DBC đã được liên kết với repository.

Repository proxy không giữ một JDBC-style EntityManager hay persistence context như JPA. Mô hình của Spring Data R2DBC dựa trên thao tác reactive với database và mapping entity theo từng hoạt động.

## 7. Liên kết repository với R2dbcEntityTemplate

### 7.1. R2dbcEntityOperations là abstraction của thao tác entity

**R2dbcEntityTemplate** triển khai abstraction **R2dbcEntityOperations**. Repository infrastructure sử dụng entity operations để thực hiện CRUD và các truy vấn mapping entity.

Trong cấu hình thông thường, bean template mặc định có tên:

~~~text
r2dbcEntityTemplate
~~~

Thuộc tính **entityOperationsRef** của **@EnableR2dbcRepositories** cho phép chỉ định bean entity operations mà nhóm repository cần sử dụng. Mặc định, repository scanning thường liên kết với bean tên **r2dbcEntityTemplate**.

Ví dụ:

~~~java
@Configuration
@EnableR2dbcRepositories(
        basePackageClasses = CustomerRepository.class,
        entityOperationsRef = "r2dbcEntityTemplate"
)
class CustomerRepositoryConfiguration {
}
~~~

Với một database duy nhất, tên mặc định thường đủ và không cần khai báo lại **entityOperationsRef**. Thuộc tính này trở nên quan trọng khi ứng dụng có nhiều template.

### 7.2. Phân biệt DatabaseClient và R2dbcEntityTemplate

| Thành phần | Vai trò |
|---|---|
| **ConnectionFactory** | Cung cấp kết nối R2DBC từ driver |
| **DatabaseClient** | Thực thi SQL, bind giá trị và đọc row |
| **R2dbcMappingContext** | Lưu metadata mapping entity và property |
| **MappingR2dbcConverter** | Chuyển đổi giữa row/value và object Java |
| **R2dbcEntityTemplate** | Kết hợp client và mapping để cung cấp thao tác entity |
| **ReactiveCrudRepository proxy** | Cung cấp repository API dựa trên entity operations |

Nếu cần viết SQL trực tiếp, có thể sử dụng DatabaseClient. Nếu muốn thao tác theo entity, Criteria và mapping metadata, dùng R2dbcEntityTemplate. Repository là abstraction cao hơn cho các thao tác gắn với aggregate/entity.

## 8. Cấu hình thủ công với AbstractR2dbcConfiguration

Không phải ứng dụng nào cũng dùng Spring Boot auto-configuration. Với ứng dụng Spring Framework hoặc khi cần kiểm soát cấu hình R2DBC, có thể mở rộng **AbstractR2dbcConfiguration**.

Ví dụ khung cấu hình:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactories;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.AbstractR2dbcConfiguration;
import org.springframework.data.r2dbc.repository.config.EnableR2dbcRepositories;

@Configuration
@EnableR2dbcRepositories(
        basePackageClasses = CustomerRepository.class
)
class R2dbcConfiguration extends AbstractR2dbcConfiguration {

    @Override
    public ConnectionFactory connectionFactory() {
        return ConnectionFactories.get(
                "r2dbc:postgresql://app:local-password@localhost:5432/shop"
        );
    }
}
~~~

Ví dụ dùng URL minh họa cho local. Trong ứng dụng thực tế, credential nên được lấy từ cấu hình bên ngoài, không viết trực tiếp trong source code.

**AbstractR2dbcConfiguration** cung cấp các thành phần cấu hình cơ bản của Spring Data R2DBC dựa trên ConnectionFactory. Có thể mở rộng các hook của cấu hình khi cần đăng ký custom conversions hoặc điều chỉnh mapping.

Nếu ứng dụng đã dùng Spring Boot auto-configuration, không nên đồng thời tạo một cấu hình thủ công đầy đủ mà không hiểu bean nào đang được tạo. Hai nguồn cấu hình có thể cạnh tranh hoặc làm auto-configuration back off. Hãy chọn một cách cấu hình nhất quán cho mỗi bộ hạ tầng R2DBC.

## 9. Liên kết nhiều nhóm repository với nhiều database

Một ứng dụng có thể sử dụng nhiều relational database, ví dụ:

- Customer database chứa hồ sơ khách hàng.
- Order database chứa đơn hàng.
- Reporting database phục vụ truy vấn báo cáo.

Trong trường hợp này, không nên để tất cả repository dùng một template mặc định nếu chúng cần kết nối đến các database khác nhau. Cần tạo bộ hạ tầng riêng và liên kết từng nhóm repository với đúng **R2dbcEntityOperations**.

### 9.1. Tách package theo database

~~~text
com.example.app
├── customer
│   └── CustomerRepository.java
├── order
│   └── OrderRepository.java
└── config
    ├── CustomerDatabaseConfiguration.java
    └── OrderDatabaseConfiguration.java
~~~

Cấu hình quét repository của customer:

~~~java
@Configuration
@EnableR2dbcRepositories(
        basePackageClasses = CustomerRepository.class,
        entityOperationsRef = "customerR2dbcEntityTemplate"
)
class CustomerDatabaseConfiguration {
}
~~~

Cấu hình quét repository của order:

~~~java
@Configuration
@EnableR2dbcRepositories(
        basePackageClasses = OrderRepository.class,
        entityOperationsRef = "orderR2dbcEntityTemplate"
)
class OrderDatabaseConfiguration {
}
~~~

Ở đây, mỗi nhóm repository được liên kết với một bean template có tên riêng. Ứng dụng cần cung cấp các bean đó cùng ConnectionFactory, DatabaseClient và mapping converter phù hợp với database tương ứng.

### 9.2. Tạo DatabaseClient riêng cho từng ConnectionFactory

Ví dụ phần khai báo client:

~~~java
@Bean("customerDatabaseClient")
DatabaseClient customerDatabaseClient(
        @Qualifier("customerConnectionFactory")
        ConnectionFactory connectionFactory) {

    return DatabaseClient.create(connectionFactory);
}
~~~

Tương tự, order database có client riêng:

~~~java
@Bean("orderDatabaseClient")
DatabaseClient orderDatabaseClient(
        @Qualifier("orderConnectionFactory")
        ConnectionFactory connectionFactory) {

    return DatabaseClient.create(connectionFactory);
}
~~~

Mỗi DatabaseClient phải sử dụng ConnectionFactory tương ứng. Không nên dùng một client cho database này rồi gán nhầm vào template của database khác.

### 9.3. Tạo template riêng và liên kết bằng entityOperationsRef

Có thể tạo template từ DatabaseClient và converter phù hợp:

~~~java
@Bean("customerR2dbcEntityTemplate")
R2dbcEntityTemplate customerR2dbcEntityTemplate(
        @Qualifier("customerDatabaseClient")
        DatabaseClient databaseClient,
        @Qualifier("customerR2dbcConverter")
        R2dbcConverter converter) {

    return new R2dbcEntityTemplate(databaseClient, converter);
}
~~~

Tương tự cho order database:

~~~java
@Bean("orderR2dbcEntityTemplate")
R2dbcEntityTemplate orderR2dbcEntityTemplate(
        @Qualifier("orderDatabaseClient")
        DatabaseClient databaseClient,
        @Qualifier("orderR2dbcConverter")
        R2dbcConverter converter) {

    return new R2dbcEntityTemplate(databaseClient, converter);
}
~~~

Đoạn mã trên tập trung thể hiện mối liên kết giữa client, converter và template. Trong cấu hình thực tế, cần cung cấp các bean converter/mapping context tương ứng và bảo đảm chúng dùng dialect, custom conversions và metadata đúng với database. Có thể dùng cấu hình chuyên biệt kế thừa Spring Data R2DBC configuration để quản lý những thành phần này.

Khi có nhiều bean cùng kiểu, dùng **@Qualifier** hoặc **@Primary** một cách có chủ đích. Không dựa vào thứ tự khởi tạo bean để quyết định repository kết nối database nào.

### 9.4. Tại sao entityOperationsRef quan trọng?

Giả sử cả hai template đều có kiểu **R2dbcEntityTemplate**. Nếu repository không được liên kết tường minh, Spring có thể không xác định được template phù hợp hoặc repository có thể dùng bean mặc định ngoài ý muốn.

**entityOperationsRef** nói rõ:

- CustomerRepository sử dụng **customerR2dbcEntityTemplate**.
- OrderRepository sử dụng **orderR2dbcEntityTemplate**.

Tên trong annotation phải trùng chính xác với tên bean. Nếu bean không tồn tại hoặc sai tên, ứng dụng sẽ lỗi khi tạo repository infrastructure.

### 9.5. Transaction manager cũng cần tách theo database

Nếu mỗi database có ConnectionFactory riêng và cần transaction độc lập, cần transaction manager R2DBC phù hợp cho từng ConnectionFactory. Khi có nhiều transaction manager, cấu hình transaction boundary phải chỉ rõ manager thích hợp, ví dụ qua qualifier hoặc tên transaction manager trong **@Transactional** theo cấu hình ứng dụng.

Một transaction manager gắn với customer database không tự quản lý thao tác trên order database. Một annotation **@Transactional** đơn lẻ cũng không tự tạo transaction phân tán xuyên nhiều database. Nếu nghiệp vụ cần nhất quán xuyên nhiều database, phải thiết kế cơ chế phù hợp như outbox hoặc saga thay vì giả định có một transaction local bao trùm tất cả.

## 10. Custom repository fragment và hạ tầng R2DBC

Khi phương thức derived query hoặc **@Query** chưa đủ linh hoạt, có thể bổ sung custom repository fragment. Fragment là interface riêng khai báo hành vi tùy chỉnh và implementation sử dụng template hoặc DatabaseClient.

Ví dụ interface fragment:

~~~java
public interface CustomerSearchRepository {
    Flux<Customer> searchByName(String keyword);
}
~~~

Repository chính kết hợp fragment:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long>,
                CustomerSearchRepository {
}
~~~

Implementation theo quy ước hậu tố mặc định **Impl**:

~~~java
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import reactor.core.publisher.Flux;

public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final R2dbcEntityTemplate template;

    public CustomerSearchRepositoryImpl(R2dbcEntityTemplate template) {
        this.template = template;
    }

    @Override
    public Flux<Customer> searchByName(String keyword) {
        return template.select(
                Query.query(Criteria.where("name").like("%" + keyword + "%")),
                Customer.class
        );
    }
}
~~~

Ví dụ này minh họa cách fragment dùng cùng template đã được inject. Với input có ký tự wildcard hoặc yêu cầu tìm kiếm phức tạp, cần xác định rõ semantics của LIKE và escaping. Không ghép giá trị người dùng vào SQL string; ở API Criteria, giá trị được truyền như điều kiện dữ liệu.

Repository scanning phát hiện repository chính; Spring Data kết hợp các fragment implementation theo quy ước cấu hình. Fragment không tạo một ConnectionFactory mới. Nó sử dụng hạ tầng được inject, vì vậy nếu repository thuộc nhóm database nào thì template fragment nhận được cũng phải thuộc nhóm đó.

## 11. Query method và @Query sử dụng cùng repository infrastructure

### 11.1. Derived query

~~~java
Flux<Customer> findByStatus(String status);
Mono<Customer> findByEmail(String email);
Mono<Boolean> existsByEmail(String email);
Mono<Long> countByStatus(String status);
~~~

Spring Data phân tích tên method và property của entity để xây dựng query. Repository proxy thực thi thông qua entity operations đã liên kết.

Tên property trong method thường là property Java, không phải tên cột SQL nếu hai tên khác nhau. Ví dụ entity có property **email** ánh xạ sang **email_address**; method derived query nên dựa trên property **email**.

### 11.2. Query tường minh

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :status
    ORDER BY id
    """)
Flux<Customer> findActiveCustomers(String status);
~~~

Với **@Query**, SQL được khai báo trực tiếp. Repository vẫn được tạo bởi scanning infrastructure và vẫn sử dụng cấu hình R2DBC được liên kết. Nhưng tên bảng/cột trong raw SQL cần khớp schema và dialect; entity mapping không tự viết lại toàn bộ SQL tùy chỉnh.

Khi cần kiểm soát tên tham số, có thể dùng **@Param**:

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :customerStatus
    """)
Flux<Customer> findByStatus(
        @Param("customerStatus") String status
);
~~~

Không đưa trực tiếp input vào chuỗi SQL. Dùng bind parameter cho giá trị dữ liệu.

## 12. Repository scanning không tự tạo bảng

Một hiểu nhầm phổ biến là thêm repository interface và **@Table** sẽ khiến Spring tự tạo bảng khi khởi động. Repository scanning chỉ tạo bean repository; mapping metadata chỉ mô tả cách entity liên hệ với bảng/cột.

Việc tạo schema cần một cơ chế riêng:

- Migration bằng Flyway hoặc Liquibase.
- Script khởi tạo database trong môi trường phát triển.
- Quy trình DDL được quản lý riêng.
- Cơ chế tạo schema được dự án chủ động cấu hình.

Ví dụ entity:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name
) {}
~~~

không đồng nghĩa với việc bảng customers chắc chắn đã tồn tại. Nếu repository thực thi query trên bảng chưa được tạo, database sẽ trả lỗi relation/table not found.

Trong ứng dụng R2DBC, migration có thể sử dụng JDBC tùy công cụ và cấu hình. Điều đó không có nghĩa đường truy cập dữ liệu runtime của ứng dụng phải đổi sang JDBC. Migration và runtime persistence là hai trách nhiệm khác nhau.

## 13. Lỗi thường gặp khi quét Repository và liên kết hạ tầng

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Repository không được inject | Package nằm ngoài phạm vi scanning | Đặt package dưới package gốc hoặc cấu hình **@EnableR2dbcRepositories** |
| Không có bean repository khi khởi động | Repository auto-configuration bị tắt hoặc thiếu điều kiện hạ tầng | Kiểm tra dependency, cấu hình repositories và ConnectionFactory |
| Không tạo được repository proxy | Thiếu entity operations/template hoặc cấu hình repository sai | Kiểm tra **R2dbcEntityTemplate**, **entityOperationsRef** và factory configuration |
| Không có ConnectionFactory | Thiếu R2DBC driver hoặc URL không hợp lệ | Kiểm tra runtime dependency và **spring.r2dbc.url** |
| Có nhiều ConnectionFactory và bị ambiguous | Spring không biết chọn bean nào | Dùng **@Primary**, **@Qualifier** và cấu hình repository riêng |
| Repository chạy nhưng truy cập nhầm database | **entityOperationsRef** trỏ sai template hoặc template dùng sai client | Kiểm tra chuỗi template → DatabaseClient → ConnectionFactory |
| Bean template không được tìm thấy | Tên bean không khớp **entityOperationsRef** | Đồng bộ tên bean và giá trị annotation |
| Table/column not found | Mapping metadata không khớp schema hoặc migration chưa chạy | Kiểm tra **@Table**, **@Column**, naming strategy và schema |
| Query method không được tạo | Tên property trong method không tồn tại hoặc query derivation không hỗ trợ | Đối chiếu property Java và dùng **@Query** khi cần |
| Repository bị đăng ký trùng | Nhiều cấu hình quét cùng package | Chia package rõ ràng và loại bỏ cấu hình scan chồng lấn |
| Custom fragment không được gắn vào repository | Sai tên implementation hoặc package không được phát hiện | Kiểm tra tên fragment, hậu tố Impl và package |
| Transaction dùng nhầm database | Transaction manager gắn với ConnectionFactory khác | Chỉ định transaction manager đúng cho nhóm thao tác |

### 13.1. Repository nằm ngoài package gốc

Ví dụ class ứng dụng ở **com.example.shop**, nhưng repository nằm ở **org.company.shared.customer**. Package repository không phải package con nên auto-scan mặc định có thể không phát hiện.

Có thể chỉ định:

~~~java
@EnableR2dbcRepositories(
        basePackages = "org.company.shared.customer"
)
~~~

Hoặc dùng **basePackageClasses** với marker trong package đó.

### 13.2. Thiếu R2DBC driver

Một ứng dụng có thể có repository interface và starter nhưng không có driver cho database. Khi đó Spring không thể tạo ConnectionFactory phù hợp. Kiểm tra runtime classpath, không chỉ compile classpath.

### 13.3. Có nhiều template nhưng không chỉ định bean

Khi ứng dụng có nhiều database, mỗi repository package phải được liên kết với template tương ứng. Kiểm tra **entityOperationsRef** và tên bean trước khi điều tra SQL. Repository tạo thành công nhưng gắn nhầm template có thể gây lỗi dữ liệu rất khó phát hiện.

### 13.4. Nhầm annotation của JPA với R2DBC

Spring Data R2DBC dùng mapping relational như **@Table**, **@Id**, **@Column** và **ReactiveCrudRepository**. Không dùng **@EnableJpaRepositories**, **EntityManager** hoặc giả định **@Entity** của JPA là cơ chế cấu hình repository R2DBC.

Nếu một ứng dụng dùng đồng thời JPA và R2DBC, cần tách rõ package repository, entity mapping và transaction manager của từng công nghệ.

## 14. Kiểm thử repository scanning và wiring

Một integration test nên xác nhận không chỉ application context khởi động mà cả repository được tạo và có thể truy cập database.

Ví dụ kiểm tra repository bean:

~~~java
@SpringBootTest
class CustomerRepositoryWiringTest {

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void repositoryShouldBeInjected() {
        assertThat(customerRepository).isNotNull();
    }
}
~~~

Test này chỉ xác nhận bean được đăng ký. Nó chưa chứng minh ConnectionFactory hoặc SQL hoạt động.

Có thể thêm test truy cập dữ liệu với database thật hoặc Testcontainers:

~~~java
@Test
void shouldReadCustomerFromDatabase() {
    StepVerifier.create(customerRepository.findById(1L))
            .expectNextMatches(customer -> customer.id().equals(1L))
            .verifyComplete();
}
~~~

Để kiểm tra wiring sâu hơn, nên xác nhận:

- Repository được inject đúng package.
- Entity mapping trỏ đến đúng bảng và cột.
- Repository đang dùng template/database dự kiến.
- ConnectionFactory có thể kết nối database.
- Query thực tế chạy được và trả kiểu dữ liệu mong đợi.
- Transaction manager phù hợp nếu test có transaction.
- Với nhiều database, repository của mỗi package truy cập đúng database tương ứng.

Test dùng mock có thể kiểm tra service logic, nhưng không phát hiện lỗi package scan, bean qualifier, dialect, SQL hoặc driver như integration test.

## 15. Checklist cấu hình từ repository đến database

Khi thiết lập một repository mới, có thể đi theo thứ tự:

1. Xác định package chứa repository interface.
2. Xác nhận package đó nằm trong phạm vi scan mặc định của Spring Boot hoặc cấu hình **@EnableR2dbcRepositories**.
3. Khai báo repository kế thừa **ReactiveCrudRepository** hoặc interface Spring Data phù hợp.
4. Đảm bảo entity có mapping metadata như **@Table** và **@Id**.
5. Cung cấp R2DBC driver và cấu hình URL/credential đúng database.
6. Xác nhận **ConnectionFactory** được tạo.
7. Xác nhận **DatabaseClient**, mapping converter và **R2dbcEntityTemplate** được cấu hình.
8. Nếu có nhiều template, đặt **entityOperationsRef** chính xác cho từng package repository.
9. Nếu có nhiều ConnectionFactory, dùng qualifier/primary và transaction manager riêng có chủ đích.
10. Chạy migration để bảo đảm bảng và cột tồn tại.
11. Kiểm thử repository bean và truy vấn thực tế bằng database tương thích.

Có thể kiểm tra theo sơ đồ:

~~~text
Repository interface có được scan?
              |
         +----+----+
         |         |
        Không      Có
         |         |
         v         v
  Sửa package /   Repository proxy
  Enable annotation   được tạo?
                         |
                    +----+----+
                    |         |
                   Không      Có
                    |         |
                    v         v
             Kiểm tra factory,  Entity operations
             template, bean ref    được liên kết?
                                       |
                                  +----+----+
                                  |         |
                                 Không      Có
                                  |         |
                                  v         v
                          Kiểm tra bean name, ConnectionFactory
                          qualifier             và driver
                                                   |
                                                   v
                                             Query thực tế
                                                   |
                                                   v
                                           Mapping đúng entity?
~~~

## 16. Kết luận

Repository scanning là bước Spring Data phát hiện repository interface và tạo proxy để ứng dụng sử dụng. Với Spring Boot, package dưới class **@SpringBootApplication** thường được quét theo cấu hình mặc định. Khi cần kiểm soát package hoặc phân chia nhiều database, dùng **@EnableR2dbcRepositories** với **basePackages**, **basePackageClasses** và **entityOperationsRef**.

Repository proxy được liên kết với **R2dbcEntityOperations**, thường là **R2dbcEntityTemplate**. Template sử dụng mapping converter và DatabaseClient; DatabaseClient dựa trên ConnectionFactory và R2DBC driver để thực thi SQL. Chuỗi liên kết này quyết định repository đang thao tác với bảng và database nào.

Cần nhớ rằng quét repository không tạo bảng và cũng không tự tìm toàn bộ schema. Entity mapping, hạ tầng kết nối và migration schema là các phần riêng cần được cấu hình đồng bộ. Khi ứng dụng có nhiều database, việc tách package repository và liên kết từng nhóm với đúng template, ConnectionFactory và transaction manager giúp tránh truy cập nhầm dữ liệu và làm cấu hình dễ kiểm soát hơn.

