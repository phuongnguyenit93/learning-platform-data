# Vai trò của JpaVendorAdapter và các thuộc tính nhà cung cấp

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích JpaVendorAdapter đứng ở đâu trong kiến trúc Spring Data JPA và Spring ORM.
- Phân biệt JpaVendorAdapter, JpaDialect, PersistenceProvider và EntityManagerFactory.
- Cấu hình HibernateJpaVendorAdapter trong ứng dụng Spring Framework tự cấu hình JPA.
- Sử dụng thuộc tính chuẩn của Jakarta Persistence và thuộc tính riêng của Hibernate hoặc provider khác.
- Cấu hình các thuộc tính JPA trong Spring Boot bằng application.yml hoặc application.properties.
- Chẩn đoán trường hợp cấu hình bị bỏ qua, sai provider, sai dialect hoặc sinh schema ngoài ý muốn.

## 1. JpaVendorAdapter giải quyết vấn đề gì?

JPA là một đặc tả. Ứng dụng sử dụng API như EntityManager, EntityManagerFactory, EntityTransaction và các annotation mapping để làm việc với persistence context. Một JPA provider hiện thực đặc tả đó. Hibernate ORM và EclipseLink là hai ví dụ về provider.

Spring ORM cung cấp lớp tích hợp để đưa JPA provider vào vòng đời và cơ chế quản lý transaction của Spring. Trong cấu hình dùng LocalContainerEntityManagerFactoryBean, JpaVendorAdapter là điểm kết nối giữa Spring và provider cụ thể.

Một JpaVendorAdapter cung cấp thông tin và hành vi phụ thuộc nhà cung cấp, thường gồm:

- PersistenceProvider mà Spring sẽ sử dụng để tạo EntityManagerFactory.
- JpaDialect tương ứng để Spring xử lý một số hành vi transaction và exception theo provider.
- Bản đồ các thuộc tính JPA/provider mặc định.
- Thông tin database platform và các cờ cấu hình như hiển thị SQL hoặc tạo DDL, tùy implementation.

Trong Spring ORM, các implementation thường gặp gồm HibernateJpaVendorAdapter, EclipseLinkJpaVendorAdapter và OpenJpaVendorAdapter. Chọn adapter phù hợp với provider thật sự có trên classpath và được cấu hình cho persistence unit.

### Vị trí trong kiến trúc

Luồng cấu hình có thể hình dung như sau:

~~~text
Spring Data JPA repositories
          |
          v
EntityManager / EntityManagerFactory
          ^
          |
LocalContainerEntityManagerFactoryBean
          |
          +---- JpaVendorAdapter
          |        +---- PersistenceProvider
          |        +---- JpaDialect
          |        +---- vendor defaults
          |
          +---- JPA properties
          |
          +---- DataSource
          |
          v
JPA provider (ví dụ Hibernate)
          |
          v
JDBC driver
          |
          v
Database
~~~

Spring Data JPA repository sử dụng EntityManager để thực hiện thao tác persistence. EntityManagerFactory được tạo bởi cấu hình JPA của ứng dụng. JpaVendorAdapter tham gia lúc Spring khởi tạo EntityManagerFactory; nó không phải repository, không phải EntityManager và cũng không phải connection pool.

## 2. Phân biệt các thành phần liên quan

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| JpaVendorAdapter | Cung cấp thông tin tích hợp Spring ORM cho một JPA provider | HibernateJpaVendorAdapter |
| PersistenceProvider | Provider thực hiện việc tạo EntityManagerFactory theo chuẩn JPA | Hibernate, EclipseLink |
| JpaDialect | Cầu nối các hành vi đặc thù provider với transaction và exception của Spring | HibernateJpaDialect |
| LocalContainerEntityManagerFactoryBean | Factory bean của Spring để cấu hình và khởi tạo EntityManagerFactory | Đặt DataSource, packagesToScan, adapter và properties |
| EntityManagerFactory | Factory tạo EntityManager cho persistence unit | Được inject vào tầng persistence |
| DataSource | Cung cấp JDBC connections | HikariCP kết nối PostgreSQL |
| JpaProperties của Spring Boot | Tập hợp cấu hình JPA mà Spring Boot bind từ application configuration | spring.jpa.show-sql |

JpaVendorAdapter không thay thế JpaDialect. Adapter trả về dialect phù hợp với provider để Spring ORM có thể phối hợp transaction và một số thao tác JDBC. HibernateJpaVendorAdapter thường đi cùng HibernateJpaDialect.

Adapter cũng không tự quản lý connection pool. DataSource và pool như HikariCP là một phần cấu hình riêng. Việc chọn adapter không tự động làm cho một database trở nên tương thích với provider; driver, dialect, schema và phiên bản thư viện vẫn phải phù hợp.

## 3. HibernateJpaVendorAdapter

Với ứng dụng Spring Data JPA sử dụng Hibernate, implementation thường dùng là:

~~~java
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;

HibernateJpaVendorAdapter adapter = new HibernateJpaVendorAdapter();
~~~

Các tùy chọn thường gặp:

- setShowSql(boolean): yêu cầu provider hiển thị câu SQL theo cơ chế show SQL của Hibernate.
- setGenerateDdl(boolean): chỉ định adapter có yêu cầu tạo DDL hay không.
- setDatabasePlatform(String): chỉ định tên platform/dialect của database khi thật sự cần.
- setDatabase(Database): chọn loại database từ enum của Spring ORM trong những trường hợp cần adapter suy ra platform.

Không phải ứng dụng nào cũng cần đặt tất cả các tùy chọn. Với Hibernate hiện đại, provider thường có thể nhận diện database phổ biến từ JDBC metadata. Vì vậy, không nên đặt dialect cứng theo thói quen nếu không có yêu cầu cụ thể. Khi dùng database không phổ biến hoặc custom dialect, hãy xác nhận dialect phù hợp với đúng major version Hibernate.

setShowSql(true) hữu ích khi thử nghiệm nhanh nhưng thường không phải cách tốt nhất để quản lý log trong môi trường triển khai. Có thể bật log category để kiểm soát SQL và bind values theo môi trường. Giá trị bind có thể chứa dữ liệu nhạy cảm, vì vậy không bật log bind ở production nếu chưa có quy trình bảo vệ phù hợp.

setGenerateDdl là cờ tích hợp của adapter; nó không phải một công cụ migration database. Với ứng dụng thực tế, nên quản lý thay đổi schema bằng Flyway hoặc Liquibase và cấu hình Hibernate ở chế độ validate hoặc none tùy quy trình triển khai.

## 4. Cấu hình adapter trong Spring Framework

Khi không dùng Spring Boot auto-configuration, ứng dụng có thể khai báo LocalContainerEntityManagerFactoryBean trực tiếp.

Ví dụ dưới đây dùng Java 17+, Spring ORM, Spring Data JPA, Hibernate và một DataSource đã được cấu hình ở nơi khác:

~~~java
package com.example.config;

import java.util.Properties;

import javax.sql.DataSource;
import jakarta.persistence.EntityManagerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
@EnableJpaRepositories(basePackages = "com.example.persistence")
public class JpaConfiguration {

    @Bean
    LocalContainerEntityManagerFactoryBean entityManagerFactory(
            DataSource dataSource) {

        HibernateJpaVendorAdapter adapter =
                new HibernateJpaVendorAdapter();

        adapter.setShowSql(false);
        adapter.setGenerateDdl(false);

        Properties properties = new Properties();
        properties.setProperty("hibernate.hbm2ddl.auto", "validate");
        properties.setProperty("hibernate.jdbc.time_zone", "UTC");
        properties.setProperty("hibernate.format_sql", "true");
        properties.setProperty("hibernate.jdbc.batch_size", "50");
        properties.setProperty("hibernate.order_inserts", "true");
        properties.setProperty("hibernate.order_updates", "true");

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();

        factory.setDataSource(dataSource);
        factory.setPackagesToScan("com.example.domain");
        factory.setPersistenceUnitName("application");
        factory.setJpaVendorAdapter(adapter);
        factory.setJpaProperties(properties);

        return factory;
    }

    @Bean
    PlatformTransactionManager transactionManager(
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
~~~

Các điểm cần hiểu:

1. DataSource được inject vào factory bean; ví dụ này không tự tạo pool hay JDBC URL.
2. packagesToScan chỉ ra các package chứa entity cần quản lý.
3. setJpaVendorAdapter chọn Hibernate làm provider adapter.
4. setJpaProperties bổ sung các thuộc tính mà Hibernate hiểu.
5. JpaTransactionManager phối hợp transaction JPA với cơ chế transaction của Spring.
6. @EnableJpaRepositories chỉ rõ package chứa repository interface.

Các import Jakarta ở ví dụ này phù hợp với stack Spring Boot 3/Spring Framework 6 và JPA 3.1 trở lên. Nếu dự án dùng stack cũ dựa trên JPA 2.x, namespace API có thể là javax.persistence; không trộn hai namespace trong cùng một persistence stack.

Trong ứng dụng có nhiều persistence unit, mỗi EntityManagerFactory cần cấu hình riêng và adapter phải khớp provider của persistence unit đó. Cần chỉ rõ entity package, repository package, transaction manager và tên persistence unit để tránh repository dùng nhầm factory.

## 5. Thuộc tính chuẩn JPA và thuộc tính riêng của provider

Không phải mọi thuộc tính cấu hình đều có cùng mức độ di động.

### Thuộc tính chuẩn Jakarta Persistence

Các thuộc tính thuộc namespace jakarta.persistence được định nghĩa bởi đặc tả Jakarta Persistence. Chúng có ý nghĩa chuẩn hóa giữa các provider ở phạm vi đặc tả hỗ trợ.

Ví dụ có thể gặp:

- jakarta.persistence.jdbc.driver
- jakarta.persistence.jdbc.url
- jakarta.persistence.jdbc.user
- jakarta.persistence.jdbc.password
- jakarta.persistence.schema-generation.database.action
- jakarta.persistence.validation.mode

Trong ứng dụng Spring, thông tin kết nối thường được đặt ở DataSource thay vì cấu hình JDBC trực tiếp trong JPA provider. Khi dùng Spring Boot, hãy ưu tiên spring.datasource.* cho URL, user và password.

### Thuộc tính riêng của Hibernate

Các thuộc tính bắt đầu bằng hibernate. là cấu hình riêng của Hibernate. Chúng có thể bật các tính năng không được JPA chuẩn hóa.

| Thuộc tính | Tác dụng | Lưu ý |
|---|---|---|
| hibernate.hbm2ddl.auto | Điều khiển hành vi tạo/kiểm tra schema của Hibernate | Không thay thế migration có version |
| hibernate.show_sql | In SQL do Hibernate phát ra | Có thể làm log khó kiểm soát |
| hibernate.format_sql | Định dạng SQL để dễ đọc | Hữu ích trong môi trường phát triển |
| hibernate.jdbc.time_zone | Múi giờ dùng khi Hibernate trao đổi giá trị thời gian qua JDBC | Thường chọn UTC và thống nhất với ứng dụng/database |
| hibernate.jdbc.batch_size | Số lệnh DML có thể gom vào JDBC batch | Cần kiểm tra driver và chiến lược sinh ID |
| hibernate.order_inserts | Sắp xếp insert để tăng khả năng gom batch | Có thể ảnh hưởng thứ tự SQL quan sát được |
| hibernate.order_updates | Sắp xếp update để tăng khả năng gom batch | Kiểm thử hành vi và hiệu năng |
| hibernate.default_batch_fetch_size | Kích thước batch mặc định cho việc tải association | Đây là batching khi đọc, khác JDBC DML batch |
| hibernate.generate_statistics | Bật thống kê nội bộ của Hibernate | Dùng để chẩn đoán, đánh giá chi phí khi bật |

Tên và giá trị hợp lệ của thuộc tính phụ thuộc phiên bản Hibernate. Trước khi cấu hình, kiểm tra tài liệu của đúng major version đang dùng.

### Thuộc tính riêng của provider khác

EclipseLink dùng namespace riêng, ví dụ eclipselink.logging.level, eclipselink.target-database và eclipselink.ddl-generation. OpenJPA có nhóm thuộc tính riêng như openjpa.Log và các tùy chọn JDBC của nó.

Không gửi thuộc tính hibernate.* cho EclipseLink và kỳ vọng nó có tác dụng. Một provider có thể bỏ qua thuộc tính không nhận biết hoặc phát cảnh báo tùy phiên bản. Khi đổi provider, phải rà soát lại toàn bộ property map, dialect, dependency và các hành vi persistence liên quan.

## 6. Cấu hình thuộc tính trong Spring Boot

Trong ứng dụng Spring Boot, thông thường không cần tự tạo HibernateJpaVendorAdapter. Auto-configuration chọn adapter dựa trên JPA provider có trên classpath và cấu hình của ứng dụng.

Dùng các thuộc tính cấp cao của Spring Boot cho những lựa chọn phổ biến:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/app
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

  jpa:
    show-sql: false
    hibernate:
      ddl-auto: validate
~~~

Các thuộc tính riêng của Hibernate có thể truyền qua spring.jpa.properties.*:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        jdbc:
          time_zone: UTC
          batch_size: 50
        order_inserts: true
        order_updates: true
        default_batch_fetch_size: 50
~~~

Spring Boot bỏ phần tiền tố spring.jpa.properties. trước khi truyền property vào JPA provider. Phần tên phía sau cần đúng chính tả và đúng tên mà provider yêu cầu; cơ chế relaxed binding không sửa tên thuộc tính provider cho bạn.

Có thể dùng application.properties tương đương:

~~~properties
spring.jpa.show-sql=false
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.jdbc.time_zone=UTC
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
spring.jpa.properties.hibernate.default_batch_fetch_size=50
~~~

Phân biệt hai nhóm cấu hình:

- spring.jpa.hibernate.ddl-auto là thuộc tính tiện ích do Spring Boot cung cấp để điều khiển hành vi schema của Hibernate.
- spring.jpa.properties.hibernate.* là cách chuyển tiếp thuộc tính riêng của provider.

Với cấu hình DataSource, ưu tiên spring.datasource.*. Không đặt cùng một thông tin kết nối ở cả DataSource lẫn property map JPA nếu không có lý do rõ ràng, vì điều đó dễ tạo hai nguồn cấu hình khác nhau.

### Khi nào cần tự khai báo JpaVendorAdapter trong Boot?

Chỉ cân nhắc tạo bean adapter khi cần tùy biến tích hợp provider ở mức thấp hoặc có cấu hình nhiều persistence unit. Trước khi thêm bean, cần hiểu điều kiện auto-configuration của đúng phiên bản Spring Boot vì một bean tùy chỉnh có thể làm thay đổi bean mặc định và cách Boot xây dựng EntityManagerFactory.

Với ứng dụng đơn giản, hãy ưu tiên spring.jpa.* và spring.jpa.properties.*. Chỉ dùng cấu hình adapter thủ công khi các thuộc tính chuẩn của Boot không đáp ứng được nhu cầu. Sau khi tùy chỉnh, kiểm tra log khởi động và xác nhận đúng EntityManagerFactory, provider và repository được tạo.

## 7. Quản lý DDL và migration an toàn

Hibernate hỗ trợ các chế độ schema thường gặp thông qua hibernate.hbm2ddl.auto; Spring Boot cung cấp spring.jpa.hibernate.ddl-auto để cấu hình tương ứng.

| Giá trị | Ý nghĩa khái quát | Trường hợp thường dùng |
|---|---|---|
| none | Không yêu cầu Hibernate quản lý schema | Schema được quản lý bên ngoài |
| validate | Kiểm tra mapping có tương thích schema hiện tại hay không | Kiểm tra lúc khởi động |
| update | Cố gắng điều chỉnh schema theo mapping | Chủ yếu dùng thử nghiệm; không thay migration có version |
| create | Tạo schema khi khởi động | Môi trường tạm thời |
| create-drop | Tạo schema lúc khởi động và xóa khi EntityManagerFactory đóng | Test hoặc môi trường dùng một lần |

Hành vi chi tiết có thể phụ thuộc provider và phiên bản. Không dùng update hoặc create trên production như một chiến lược migration. Thay đổi schema cần được review, version hóa và triển khai theo thứ tự có thể kiểm soát bằng Flyway hoặc Liquibase. Ở production, validate hoặc none thường phù hợp hơn tùy việc ứng dụng có cần kiểm tra schema lúc khởi động hay không.

## 8. Logging SQL và tham số truy vấn

Có hai cách thường gặp để quan sát SQL của Hibernate:

1. Bật show SQL bằng adapter hoặc spring.jpa.show-sql.
2. Dùng logging framework để bật các logger của Hibernate.

Ví dụ cấu hình log cho Hibernate 6 trong application-dev.yml:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

org.hibernate.SQL ghi câu SQL. org.hibernate.orm.jdbc.bind ghi giá trị bind của tham số JDBC trong Hibernate 6. Tên logger có thể khác giữa các major version, vì vậy hãy kiểm tra tài liệu của phiên bản đang dùng.

Dùng profile dev hoặc test cho cấu hình chi tiết. Bind value có thể chứa mật khẩu, email, thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm. Không bật TRACE cho bind parameters trên production nếu chưa đánh giá rủi ro, quyền truy cập log và thời hạn lưu trữ.

## 9. Cách kiểm tra cấu hình có hiệu lực

Khi một property không hoạt động, cần kiểm tra cả cấu hình ứng dụng lẫn dependency/provider thực tế.

### Bước 1: Kiểm tra provider trên dependency graph

Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.hibernate.orm:hibernate-core
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
~~~

Xác nhận provider đúng phiên bản và không có nhiều provider ngoài dự kiến trên classpath.

### Bước 2: Kiểm tra cấu hình Spring

Với Spring Boot, kiểm tra profile được kích hoạt và nguồn cấu hình có độ ưu tiên cao hơn như biến môi trường, tham số dòng lệnh hoặc external config. Một application-prod.yml có thể ghi đè giá trị trong application.yml.

Với cấu hình thủ công, kiểm tra đúng LocalContainerEntityManagerFactoryBean đang được repository sử dụng, adapter được gắn vào factory và property map được chuyển tới factory.

### Bước 3: Kiểm tra log khởi động

Tìm thông tin provider, dialect, persistence unit và EntityManagerFactory. Nếu có nhiều factory, gắn tên persistence unit dễ nhận diện và kiểm tra repository trỏ tới đúng factory.

### Bước 4: Chạy integration test

Một test tích hợp nên xác nhận:

- Spring context khởi tạo được EntityManagerFactory.
- Repository có thể lưu và đọc entity.
- Transaction commit và rollback hoạt động như mong đợi.
- Schema ở trạng thái phù hợp với ddl-auto đã chọn.
- Các thuộc tính hiệu năng như JDBC batching có tác dụng trong kịch bản thực tế.

Không kết luận property có hiệu lực chỉ vì ứng dụng khởi động thành công. Một property sai tên có thể bị bỏ qua mà không gây lỗi ngay lập tức.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tạo được EntityManagerFactory | Thiếu provider dependency hoặc adapter không khớp provider | Kiểm tra dependency tree, classpath và cấu hình persistence unit |
| Hibernate property không có tác dụng | Sai tên property, sai prefix hoặc ứng dụng đang dùng provider khác | Kiểm tra map cuối cùng và tài liệu đúng phiên bản |
| Hibernate không nhận diện dialect | DataSource không cung cấp JDBC metadata hoặc driver sai | Kiểm tra JDBC URL, driver, quyền kết nối; chỉ định dialect nếu thật sự cần |
| SQL không xuất hiện | show-sql tắt hoặc logger chưa bật đúng category | Kiểm tra profile và logger của đúng phiên bản Hibernate |
| Giá trị bind không xuất hiện | Chưa bật logger bind hoặc tên category không khớp phiên bản | Kiểm tra logger Hibernate 6 hoặc phiên bản đang chạy |
| Schema tự thay đổi ngoài dự kiến | ddl-auto đang là update, create hoặc create-drop | Đổi sang chế độ phù hợp và dùng migration có version |
| Ứng dụng dùng sai provider | Có nhiều provider trên classpath hoặc cấu hình nhiều persistence unit chưa rõ ràng | Chỉ định dependency và adapter theo từng factory |
| JpaTransactionManager không phối hợp đúng | Transaction manager trỏ nhầm EntityManagerFactory hoặc thiếu cấu hình transaction | Kiểm tra bean name, persistence unit và @EnableTransactionManagement |

## 11. Quy trình chọn và cấu hình thuộc tính nhà cung cấp

Khi cần thêm một thuộc tính:

1. Xác định provider và phiên bản thực tế từ dependency graph.
2. Kiểm tra thuộc tính đó thuộc Jakarta Persistence hay thuộc riêng provider.
3. Tra cứu tên, kiểu dữ liệu, giá trị hợp lệ và phiên bản hỗ trợ trong tài liệu tương ứng.
4. Chọn đúng điểm cấu hình: spring.jpa.* cho tùy chọn Boot, spring.jpa.properties.* cho property provider, hoặc setJpaProperties trong cấu hình factory thủ công.
5. Chỉ khai báo một nguồn có thẩm quyền cho mỗi giá trị; tránh lặp lại ở nhiều profile hoặc nhiều lớp cấu hình.
6. Khởi động ứng dụng, kiểm tra log và chạy integration test.
7. Ghi lại lý do nếu dùng custom dialect, property ít phổ biến hoặc override mặc định của provider.

Không sao chép một cấu hình Hibernate sang EclipseLink hay OpenJPA. Tên property, ý nghĩa, giá trị hợp lệ và thời điểm áp dụng có thể khác nhau.

## Checklist trước khi merge

- [ ] JpaVendorAdapter khớp với JPA provider thực tế.
- [ ] Đã phân biệt JpaVendorAdapter, JpaDialect, PersistenceProvider và EntityManagerFactory.
- [ ] DataSource và provider được cấu hình ở đúng lớp trách nhiệm.
- [ ] Thuộc tính chuẩn JPA và thuộc tính riêng provider được phân loại đúng.
- [ ] Tên property và giá trị được kiểm tra theo đúng phiên bản provider.
- [ ] Không hardcode dialect khi provider có thể tự nhận diện và không có yêu cầu custom.
- [ ] Không dùng ddl-auto update/create như migration production.
- [ ] SQL và bind logging chỉ bật ở môi trường phù hợp.
- [ ] EntityManagerFactory, repository và transaction đã được kiểm tra bằng integration test.

## Kết luận

JpaVendorAdapter là cầu nối tích hợp giữa Spring ORM và JPA provider. Nó cung cấp PersistenceProvider, JpaDialect và các mặc định theo nhà cung cấp cho quá trình tạo EntityManagerFactory. Các thuộc tính như hibernate.jdbc.batch_size hoặc eclipselink.logging.level thuộc về provider cụ thể, vì vậy phải dùng đúng tên và đúng phiên bản. Trong Spring Boot, ưu tiên spring.jpa.* và spring.jpa.properties.*; trong cấu hình Spring ORM thủ công, gắn adapter vào LocalContainerEntityManagerFactoryBean và quản lý property map rõ ràng. Luôn xác nhận provider, cấu hình hiệu lực và hành vi thực tế bằng log cùng integration test.
