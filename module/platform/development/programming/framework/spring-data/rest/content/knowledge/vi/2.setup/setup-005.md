# Tạo ứng dụng mẫu với Spring Data JPA, H2 và dữ liệu khởi tạo

Bài thực hành này tạo một ứng dụng Spring Boot nhỏ để quản lý sản phẩm. Spring Data JPA ánh xạ đối tượng Java thành bảng dữ liệu và cung cấp repository; H2 là cơ sở dữ liệu quan hệ nhẹ chạy trong bộ nhớ; dữ liệu mẫu được nạp tự động khi ứng dụng khởi động. Vì module đang học là Spring Data REST, repository còn được công khai thành REST API mà không cần tự viết controller CRUD.

Sau bài này, bạn có thể tạo entity, khai báo repository, cấu hình H2, nạp dữ liệu ban đầu, kiểm tra dữ liệu bằng test và gọi các endpoint REST do Spring Data REST sinh ra.

## 1. Chuẩn bị

- JDK 17 trở lên.
- Maven 3.6.3 trở lên, hoặc Maven Wrapper do Spring Initializr tạo.
- IDE hỗ trợ Java như IntelliJ IDEA, Eclipse hoặc VS Code.
- Kiến thức cơ bản về Java, annotation và HTTP.

Ví dụ dùng Spring Boot 3.5.0 và Java 17. Khi tạo dự án mới, có thể chọn bản vá mới nhất thuộc nhánh Spring Boot 3.5.x tương thích với môi trường của bạn. Spring Boot 3 dùng namespace Jakarta, vì vậy các import JPA trong ví dụ bắt đầu bằng jakarta.persistence.

## 2. Tạo dự án và thêm dependency

Tạo dự án Maven bằng Spring Initializr với:

- Project: Maven
- Language: Java
- Spring Boot: 3.5.x
- Group: com.example
- Artifact: spring-data-jpa-h2-demo
- Packaging: Jar
- Java: 17
- Dependencies: Spring Data JPA, Spring Data REST, H2 Database, Spring Boot Starter Test

Nếu muốn tự kiểm soát cấu hình, nội dung pom.xml tối thiểu có thể như sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-data-jpa-h2-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>spring-data-jpa-h2-demo</name>
    <description>Demo Spring Data JPA, H2 and Spring Data REST</description>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-rest</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
~~~

Vai trò của từng dependency:

- spring-boot-starter-data-jpa cung cấp Spring Data JPA, Hibernate và tích hợp transaction.
- spring-boot-starter-data-rest cung cấp khả năng xuất repository thành REST API theo HAL.
- h2 là driver và cơ sở dữ liệu H2; scope runtime nghĩa là cần khi chạy ứng dụng.
- spring-boot-starter-test cung cấp JUnit Jupiter, AssertJ và các công cụ kiểm thử Spring.

Spring Boot quản lý phiên bản tương thích cho các thư viện thông qua parent POM. Không cần tự chỉ định version cho từng dependency nói trên.

## 3. Tổ chức mã nguồn

Tạo cấu trúc thư mục sau. Các lớp Java nằm cùng package để Spring Boot tự quét component, entity và repository:

~~~text
src
├── main
│   ├── java
│   │   └── com/example/demo
│   │       ├── DemoApplication.java
│   │       ├── Product.java
│   │       ├── ProductRepository.java
│   │       └── ProductDataInitializer.java
│   └── resources
│       └── application.properties
└── test
    └── java
        └── com/example/demo
            └── ProductDataInitializerTest.java
~~~

### 3.1. Lớp khởi động ứng dụng

Tạo DemoApplication.java:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

@SpringBootApplication kết hợp cấu hình, auto-configuration và component scanning. Vì các lớp còn lại nằm trong package com.example.demo hoặc package con, Spring Boot có thể tự phát hiện chúng.

### 3.2. Tạo entity Product

Entity là lớp Java đại diện cho một thực thể được lưu trong cơ sở dữ liệu. Tạo Product.java:

~~~java
package com.example.demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
        // JPA cần constructor không tham số.
    }

    public Product(String name, BigDecimal price, boolean active) {
        this.name = name;
        this.price = price;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
~~~

Giải thích các annotation:

- @Entity đánh dấu Product là entity được JPA quản lý.
- @Table(name = "products") chỉ định tên bảng. Nếu bỏ qua, Hibernate sẽ suy ra tên bảng từ entity theo naming strategy.
- @Id xác định khóa chính.
- @GeneratedValue(strategy = GenerationType.IDENTITY) giao việc tạo giá trị khóa chính cho cơ chế identity của cơ sở dữ liệu.
- @Column khai báo ràng buộc cột. Với price, precision là tổng số chữ số và scale là số chữ số sau dấu thập phân.

Dùng BigDecimal cho tiền tệ thay vì float hoặc double để tránh sai số biểu diễn số thực. Constructor không tham số cần có cho JPA; để protected là đủ trong trường hợp này.

### 3.3. Tạo repository

Repository là tầng truy cập dữ liệu. Tạo ProductRepository.java:

~~~java
package com.example.demo;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

import java.util.List;
import java.util.Optional;

@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(path = "active", rel = "active")
    List<Product> findByActiveTrue();

    @RestResource(path = "by-name", rel = "by-name")
    Optional<Product> findByNameIgnoreCase(@Param("name") String name);
}
~~~

JpaRepository<Product, Long> cung cấp sẵn các thao tác như save, saveAll, findById, findAll, count và deleteById. Tham số thứ nhất là kiểu entity; tham số thứ hai là kiểu của khóa chính.

Spring Data JPA tạo phần triển khai repository lúc chạy. Các phương thức truy vấn có thể được suy ra từ tên phương thức: findByActiveTrue tìm sản phẩm có active bằng true; findByNameIgnoreCase tìm theo tên mà không phân biệt chữ hoa và chữ thường.

@RepositoryRestResource đặt đường dẫn collection là products. @RestResource đặt đường dẫn và tên liên kết cho hai truy vấn tùy chỉnh. @Param đặt tên tham số xuất hiện trên URL. Do có Spring Data REST trên classpath, repository công khai được tự động xuất thành endpoint; không cần viết controller chỉ để thực hiện CRUD cơ bản.

### 3.4. Cấu hình H2 và JPA

Tạo src/main/resources/application.properties:

~~~properties
spring.application.name=spring-data-jpa-h2-demo

spring.datasource.url=jdbc:h2:mem:catalogdb
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.open-in-view=false

spring.h2.console.enabled=true
spring.h2.console.path=/h2-console

spring.data.rest.base-path=/api
~~~

Ý nghĩa cấu hình:

- jdbc:h2:mem:catalogdb tạo database có tên catalogdb trong bộ nhớ. Database tồn tại trong vòng đời của ứng dụng.
- username sa và mật khẩu rỗng là thông tin đăng nhập mặc định cho ví dụ H2 này.
- ddl-auto=create-drop yêu cầu Hibernate tạo schema khi khởi động và xóa schema khi context đóng. Cấu hình phù hợp cho demo, không phù hợp để giữ dữ liệu lâu dài.
- show-sql và format_sql giúp quan sát câu SQL Hibernate thực thi.
- open-in-view=false tắt Open Session in View để tránh vô tình truy vấn dữ liệu lazy loading trong lúc render response.
- spring.h2.console.enabled bật giao diện quản trị H2; path đặt URL của giao diện.
- spring.data.rest.base-path=/api đặt tiền tố cho các endpoint Spring Data REST.

Vì dùng H2 trong bộ nhớ, dữ liệu sẽ mất khi ứng dụng dừng và được tạo lại ở lần chạy tiếp theo. Nếu cần lưu dữ liệu qua nhiều lần chạy, hãy chuyển sang database có lưu trữ bền vững và cấu hình migration phù hợp.

### 3.5. Nạp dữ liệu ban đầu

Có nhiều cách nạp dữ liệu mẫu. Bài này dùng CommandLineRunner để gọi repository sau khi Spring đã khởi tạo context và Hibernate đã tạo schema. Cách này tránh vấn đề thứ tự chạy giữa schema do Hibernate tạo và file data.sql.

Tạo ProductDataInitializer.java:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.math.BigDecimal;
import java.util.List;

@Configuration
public class ProductDataInitializer {

    @Bean
    CommandLineRunner seedProducts(ProductRepository repository) {
        return args -> {
            if (repository.count() == 0) {
                repository.saveAll(List.of(
                    new Product("Bàn phím cơ", new BigDecimal("1290000.00"), true),
                    new Product("Chuột không dây", new BigDecimal("450000.00"), true),
                    new Product("Màn hình 24 inch", new BigDecimal("3290000.00"), true)
                ));
            }
        };
    }
}
~~~

Spring Boot gọi các bean CommandLineRunner sau khi ApplicationContext được khởi tạo và trước khi ứng dụng hoàn tất quá trình khởi động. Khi runner chạy, repository đã sẵn sàng để lưu dữ liệu.

Điều kiện repository.count() == 0 giúp tránh thêm lại toàn bộ dữ liệu mẫu nếu database đã có bản ghi. Với H2 trong bộ nhớ và cấu hình create-drop, database thường rỗng sau mỗi lần khởi động mới, vì vậy ba sản phẩm mẫu sẽ được tạo lại. Với database bền vững, điều kiện này chỉ là cơ chế đơn giản cho dữ liệu demo; dữ liệu khởi tạo phức tạp nên dùng migration hoặc cơ chế seed có kiểm soát.

Không cần tự tạo bảng bằng SQL trong ví dụ này. Hibernate đọc mapping từ Product và tạo bảng products theo cấu hình ddl-auto.

## 4. Kiểm thử dữ liệu khởi tạo

Tạo ProductDataInitializerTest.java trong src/test/java/com/example/demo:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ProductDataInitializerTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void seededProductsAreAvailableAfterStartup() {
        assertThat(repository.findAll()).hasSizeGreaterThanOrEqualTo(3);
        assertThat(repository.findByNameIgnoreCase("Chuột không dây")).isPresent();
    }
}
~~~

@SpringBootTest khởi tạo Spring ApplicationContext cho test. Vì CommandLineRunner được thực thi trong quá trình khởi động context, test có thể kiểm tra dữ liệu đã được nạp. AssertJ cung cấp các assertion dễ đọc: kiểm tra có ít nhất ba bản ghi và có sản phẩm tên Chuột không dây.

Chạy test bằng Maven Wrapper:

~~~bash
./mvnw test
~~~

Trên Windows PowerShell, dùng:

~~~powershell
.\mvnw.cmd test
~~~

Test thành công khi Maven kết thúc với BUILD SUCCESS và không có test failure. Nếu chạy test nhiều lần, H2 trong bộ nhớ của context được tạo mới theo vòng đời test; runner sẽ nạp dữ liệu cho context đó.

## 5. Chạy ứng dụng và gọi REST API

Khởi động ứng dụng:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Sau khi ứng dụng khởi động, Spring Data REST cung cấp các endpoint sau:

| HTTP method | Endpoint | Ý nghĩa |
|---|---|---|
| GET | /api/products | Lấy danh sách sản phẩm |
| GET | /api/products/{id} | Lấy một sản phẩm theo ID |
| POST | /api/products | Tạo sản phẩm |
| PUT | /api/products/{id} | Thay thế thông tin sản phẩm |
| PATCH | /api/products/{id} | Cập nhật một phần sản phẩm |
| DELETE | /api/products/{id} | Xóa sản phẩm |
| GET | /api/products/search/active | Tìm sản phẩm đang hoạt động |
| GET | /api/products/search/by-name?name=Chuột%20không%20dây | Tìm theo tên, không phân biệt hoa thường |

Thử lấy danh sách:

~~~bash
curl -i http://localhost:8080/api/products
~~~

Spring Data REST mặc định trả về HAL JSON. Response thường có các phần như _embedded chứa danh sách tài nguyên, _links chứa liên kết điều hướng và page chứa thông tin phân trang. Tên collection trong _embedded dựa trên tên resource mà Spring Data REST suy ra.

Thử endpoint tìm sản phẩm đang hoạt động:

~~~bash
curl -i http://localhost:8080/api/products/search/active
~~~

Thử tìm theo tên:

~~~bash
curl -i "http://localhost:8080/api/products/search/by-name?name=Chu%E1%BB%99t%20kh%C3%B4ng%20d%C3%A2y"
~~~

Tạo một sản phẩm mới:

~~~bash
curl -i -X POST http://localhost:8080/api/products   -H "Content-Type: application/json"   -d '{"name":"Tai nghe","price":850000,"active":true}'
~~~

Nếu chạy trên Windows PowerShell, gọi curl.exe để tránh alias Invoke-WebRequest của PowerShell. Có thể dùng Postman hoặc REST Client trong IDE với cùng URL, method và JSON body.

Spring Data REST chuyển JSON thành entity rồi gọi repository tương ứng. Khi POST thành công, server thường trả về HTTP 201 Created và header Location trỏ tới tài nguyên vừa tạo. ID thực tế do H2 sinh ra nên không nên giả định một giá trị cố định.

## 6. Mở H2 Console

Trong lúc ứng dụng đang chạy, mở:

~~~text
http://localhost:8080/h2-console
~~~

Nhập thông tin:

- JDBC URL: jdbc:h2:mem:catalogdb
- User Name: sa
- Password: để trống

Chọn Connect. Có thể chạy câu lệnh sau để xem dữ liệu:

~~~sql
SELECT ID, NAME, PRICE, ACTIVE
FROM PRODUCTS
ORDER BY ID;
~~~

Tên bảng và cột được tạo từ mapping JPA. Trong ví dụ này, bảng là PRODUCTS; cách hiển thị chữ hoa/chữ thường phụ thuộc cách H2 chuẩn hóa identifier.

H2 Console chỉ nên bật trong môi trường học tập hoặc phát triển. Không mở console công khai trên môi trường production.

## 7. Luồng hoạt động của ứng dụng

Khi chạy ứng dụng, các thành phần phối hợp theo thứ tự khái quát:

1. Spring Boot đọc application.properties và cấu hình datasource H2.
2. Hibernate quét entity Product và tạo bảng products theo ddl-auto.
3. Spring Data JPA tạo implementation cho ProductRepository.
4. Spring Data REST phát hiện repository được xuất bản và đăng ký các endpoint dưới /api.
5. Spring khởi tạo ApplicationContext rồi chạy ProductDataInitializer.
6. CommandLineRunner kiểm tra số bản ghi; nếu database rỗng, saveAll lưu ba sản phẩm mẫu.
7. Ứng dụng sẵn sàng nhận request HTTP. Spring Data REST chuyển request tới repository và trả kết quả dưới dạng HAL JSON.

Điểm quan trọng là repository đóng vai trò trung tâm: lớp khởi tạo dữ liệu dùng repository để lưu bản ghi, còn Spring Data REST dùng cùng repository để phục vụ HTTP. Không cần tạo một lớp DAO hoặc viết các câu SQL CRUD thủ công.

## 8. Lỗi thường gặp và cách xử lý

**Không tìm thấy ProductRepository hoặc không tạo được bean repository**

Kiểm tra repository có extends JpaRepository<Product, Long>, có dependency spring-boot-starter-data-jpa và nằm trong package được Spring Boot component scanning. Package của DemoApplication nên là package gốc chứa các lớp còn lại.

**Lỗi Not a managed type: Product**

Kiểm tra Product có annotation @Entity, import đúng jakarta.persistence.Entity và nằm trong vùng package được quét. Không dùng javax.persistence với Spring Boot 3.

**Không kết nối được H2 hoặc báo không tìm thấy driver**

Kiểm tra dependency com.h2database:h2, URL jdbc:h2:mem:catalogdb và cấu hình username. Đảm bảo đang chạy đúng cấu hình application.properties.

**Bảng products không tồn tại khi nạp dữ liệu**

Ví dụ này dùng CommandLineRunner nên dữ liệu được lưu sau khi Hibernate tạo schema. Nếu chuyển sang dùng data.sql, cần quan tâm thứ tự khởi tạo; với Spring Boot có thể đặt spring.jpa.defer-datasource-initialization=true để trì hoãn việc chạy script SQL cho đến sau khi Hibernate tạo schema.

**Endpoint trả về 404**

Kiểm tra spring-boot-starter-data-rest đã được thêm, repository được export, đường dẫn cơ sở là /api và đường dẫn collection là /products. URL đầy đủ của collection trong ví dụ là /api/products.

**Dữ liệu biến mất sau khi khởi động lại**

Đây là hành vi dự kiến của jdbc:h2:mem và ddl-auto=create-drop. Dùng database lưu trữ bền vững nếu cần giữ dữ liệu qua các lần chạy.

**Cổng 8080 đã được sử dụng**

Dừng ứng dụng đang chiếm cổng hoặc đặt server.port sang cổng khác trong application.properties, ví dụ server.port=8081. Khi đổi cổng, cập nhật URL gọi API và H2 Console tương ứng.

## 9. Lưu ý khi áp dụng vào dự án thật

Cấu hình trong bài ưu tiên sự đơn giản để học và thử nghiệm. Khi triển khai thực tế:

- Không dùng create-drop nếu dữ liệu cần được giữ lại. Dùng Flyway hoặc Liquibase để quản lý thay đổi schema có phiên bản.
- Không dùng H2 in-memory làm nơi lưu dữ liệu production. Chọn database phù hợp như PostgreSQL hoặc MySQL và cấu hình thông tin kết nối qua biến môi trường hoặc secret manager.
- Không bật H2 Console trên môi trường production.
- Bổ sung Spring Security, phân quyền và xác thực trước khi công khai endpoint ghi dữ liệu.
- Thêm validation cho dữ liệu đầu vào, chẳng hạn tên không rỗng và giá không âm.
- Cân nhắc DTO, projection hoặc cấu hình xuất bản repository để kiểm soát dữ liệu nào được đưa ra API. Việc kế thừa JpaRepository không có nghĩa là mọi phương thức hay mọi trường đều nên được công khai cho người dùng cuối.
- Với dữ liệu mẫu có nhiều quan hệ hoặc cần bảo đảm thứ tự, quản lý bằng migration thay vì chỉ kiểm tra count rồi saveAll.

## 10. Tổng kết

Ứng dụng mẫu đã kết hợp ba phần chính: Spring Data JPA quản lý entity và repository, H2 cung cấp database nhẹ cho quá trình phát triển, còn CommandLineRunner nạp dữ liệu ban đầu sau khi schema sẵn sàng. Spring Data REST xuất repository thành REST API, giúp kiểm tra CRUD và truy vấn mà không cần viết controller thủ công.

Sau khi chạy thành công, bạn có thể mở /api/products để xem dữ liệu, dùng các endpoint search để thử truy vấn, POST một sản phẩm mới và mở H2 Console để quan sát bảng PRODUCTS. Đây là nền tảng để tiếp tục học quan hệ entity, phân trang, sắp xếp, validation, bảo mật và quản lý schema bằng migration.
