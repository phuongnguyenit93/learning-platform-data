# Lựa chọn kho dữ liệu và kiểm tra mức hỗ trợ xuất REST theo phiên bản

## Mục tiêu

Khi khởi tạo Spring Data REST, cần chọn đúng kho dữ liệu, Spring Data module và bộ phiên bản tương thích. Spring Data REST đảm nhiệm việc xuất repository thành tài nguyên HTTP; nó không cung cấp driver database, không thay thế module truy cập dữ liệu và không có cùng mức kiểm thử tích hợp với mọi store.

Sau bài này, bạn có thể:

- Chọn store theo mô hình dữ liệu, kiểu truy vấn, giao dịch và yêu cầu vận hành.
- Phân biệt store được Spring Data REST kiểm thử tích hợp chính thức với store chỉ có khả năng tương thích qua Repository programming model.
- Xác định phiên bản Spring Boot, Spring Data REST, Spring Data Commons và store module đang được quản lý.
- Khởi tạo một repository mẫu, kiểm tra endpoint HAL và kiểm thử thao tác HTTP.

## 1. Hiểu đúng ba lớp

Khi nói ứng dụng dùng PostgreSQL, MongoDB hay Neo4j, ta đang nói tới kho dữ liệu. Để ứng dụng làm việc với store, cần Spring Data module tương ứng. Spring Data REST nằm ở lớp web và xuất repository thành tài nguyên HTTP.

1. **Kho dữ liệu (data store):** hệ quản trị hoặc dịch vụ lưu trữ thật, ví dụ PostgreSQL, MongoDB, Neo4j, Cassandra.
2. **Spring Data module:** cung cấp mapping, repository, query và tích hợp riêng với store, ví dụ Spring Data JPA hoặc Spring Data MongoDB.
3. **Spring Data REST:** phát hiện repository đủ điều kiện và xuất collection/item resource qua Spring MVC. Các response mặc định dùng HAL để client khám phá liên kết.

Luồng xử lý:

~~~text
HTTP client
    |
    v
Spring Data REST (Spring MVC, HAL)
    |
    v
Spring Data Repository
    |
    v
Store-specific Spring Data module
    |
    v
Database / data service
~~~

Ví dụ với PostgreSQL:

- PostgreSQL lưu dữ liệu.
- PostgreSQL JDBC driver cung cấp kết nối.
- Spring Data JPA ánh xạ entity và triển khai repository.
- Spring Data REST xuất repository thành endpoint HTTP.

Chỉ thêm Spring Data REST không thể tự tạo khả năng lưu dữ liệu nếu ứng dụng chưa có store module, driver và cấu hình kết nối phù hợp.

Spring Data REST được xây dựng trên Spring MVC. Nếu ứng dụng được thiết kế hoàn toàn theo WebFlux, không nên mặc định REST exporter sẽ cung cấp một API reactive tương đương. Hãy xác minh kiến trúc web và các repository thực tế; với API reactive end-to-end, WebFlux controller/service có thể là lựa chọn rõ ràng hơn.

## 2. Chọn store theo đặc tính dữ liệu và truy vấn

Không nên chọn database chỉ vì đã quen với repository interface. Hãy liệt kê dữ liệu cần lưu, truy vấn quan trọng, yêu cầu giao dịch và cách hệ thống tăng trưởng trước.

| Nhóm store | Spring Data module thường gặp | Phù hợp khi | Điều cần thiết kế |
|---|---|---|---|
| Cơ sở dữ liệu quan hệ | JPA, JDBC | Dữ liệu có quan hệ, ràng buộc, join, transaction và báo cáo SQL | Entity/aggregate, khóa ngoại, index, transaction boundary và migration |
| Quan hệ reactive | R2DBC | Cần truy cập SQL non-blocking trong ứng dụng reactive | Repository reactive, Mono/Flux, ConnectionFactory và khả năng tương thích của API layer |
| Cơ sở dữ liệu tài liệu | MongoDB, Couchbase | Dữ liệu được đọc/ghi theo document hoặc aggregate, cấu trúc có thể thay đổi | Embedding hay reference, index, kích thước document và query pattern |
| Cơ sở dữ liệu đồ thị | Neo4j | Quan hệ giữa các đối tượng là trọng tâm, cần traversal hoặc tìm đường đi | Node, relationship, hướng traversal và mô hình truy vấn |
| Wide-column | Cassandra | Ghi lớn, phân tán, tính sẵn sàng cao và truy vấn có thể dự đoán trước | Partition key, clustering key và thiết kế bảng theo query |
| In-memory data grid | GemFire | Cần phân phối dữ liệu trong bộ nhớ, cache hoặc truy cập độ trễ thấp | Partitioning, replication, persistence và đồng bộ dữ liệu |
| Key-value, search, directory | Redis, Elasticsearch, LDAP và module liên quan | Cache, tìm kiếm toàn văn hoặc dữ liệu danh bạ chuyên biệt | Vai trò của store trong kiến trúc, query semantics và module repository có sẵn |

Các tiêu chí nên được xem xét cùng nhau:

- **Mô hình dữ liệu:** quan hệ chuẩn hóa, document lồng nhau hay graph relationship dẫn tới cách mapping khác nhau.
- **Truy vấn:** liệt kê các truy vấn thực tế. Cassandra cần query-first modeling; Neo4j mạnh ở traversal; Elasticsearch phục vụ search hơn là thay thế nguồn dữ liệu giao dịch.
- **Giao dịch và nhất quán:** xác định có cần transaction nhiều bản ghi, ràng buộc khóa ngoại, optimistic locking hay cập nhật từng aggregate.
- **Quy mô và vận hành:** cân nhắc replication, partitioning, backup/restore, độ trễ, chi phí và năng lực vận hành của nhóm.
- **Tích hợp ứng dụng:** kiểm tra driver, transaction manager, migration tool, test container và module Spring Data.
- **API cần công bố:** repository có phù hợp làm hợp đồng REST công khai hay nghiệp vụ cần controller/service và DTO riêng.

Một store có Spring Data module không đồng nghĩa store đó đã được Spring Data REST kiểm thử tích hợp. Đây là bước xác minh riêng sau khi chọn database.

## 3. Phạm vi hỗ trợ store của Spring Data REST

Tài liệu Getting Started của Spring Data REST hiện liệt kê năm tích hợp store mà dự án đã viết integration test để xác minh:

- **Spring Data JPA**
- **Spring Data MongoDB**
- **Spring Data Neo4j**
- **Spring Data GemFire**
- **Spring Data Cassandra**

Cần đọc đúng ý nghĩa của danh sách. Spring Data REST không tự bổ sung chức năng lưu trữ cho database. Về nguyên tắc, exporter có thể làm việc với Spring Data project khác nếu project đó hỗ trợ Repository programming model. Năm store trên là những tích hợp được dự án xác nhận bằng integration test.

Hãy phân loại store ứng viên theo mức bằng chứng:

| Mức | Ý nghĩa | Việc cần làm |
|---|---|---|
| Có trong danh sách integration-tested | Tài liệu Spring Data REST nêu rõ store đã được kiểm thử tích hợp | Bắt đầu từ module tương ứng, sau đó vẫn kiểm thử đúng phiên bản và tính năng ứng dụng cần |
| Có Repository abstraction nhưng ngoài danh sách | Có thể tương thích về mô hình repository, nhưng không có cùng mức xác nhận trong tài liệu | Tạo proof of concept và integration test với đúng store module, exporter và version |
| Không có repository phù hợp | Exporter không thể tự biến API tùy ý thành repository resource | Dùng controller/service hoặc adapter riêng, hoặc chọn module khác |

Không nên kết luận Redis, Elasticsearch, Couchbase, LDAP, Spring Data JDBC hay R2DBC chắc chắn không thể tích hợp chỉ vì chúng không có trong danh sách năm store. Kết luận chính xác là tài liệu hiện hành không liệt kê chúng trong nhóm tích hợp đã được kiểm thử chính thức; cần kiểm tra repository contract và xác minh bằng thử nghiệm.

### Trường hợp riêng: R2DBC

Spring Data R2DBC hỗ trợ repository reactive, thường kế thừa ReactiveCrudRepository và trả về các kiểu Reactor như Mono hoặc Flux. Đây là repository model khác về hành vi so với ví dụ JPA đồng bộ.

R2DBC không nằm trong danh sách năm store được Spring Data REST công bố là đã kiểm thử tích hợp. Vì vậy:

- Không suy ra rằng mọi ReactiveCrudRepository sẽ được xuất thành endpoint REST phù hợp chỉ vì nó kế thừa Repository.
- Kiểm tra tài liệu và integration test của chính cặp Spring Data REST/store module đang dùng.
- Nếu ứng dụng cần xử lý reactive xuyên suốt, hãy đánh giá WebFlux controller/service và cách chuyển đổi dữ liệu thay vì giả định exporter MVC đáp ứng mọi yêu cầu.

## 4. Kiểm tra phiên bản Spring Data theo Spring Boot

### 4.1. Để Spring Boot quản lý dependency

Spring Data có nhiều module và chu kỳ phát hành riêng. Spring Data REST, Commons, JPA, MongoDB, Neo4j hay Cassandra không nhất thiết có cùng số major/minor version.

Khi dùng Spring Boot, nên để dependency management của Boot quản lý phiên bản các module. Bảng sau lấy từ Managed Dependency Coordinates của các bản Spring Boot stable được công bố tại ngày 11-11-2026:

| Spring Boot | spring-data-rest-webmvc | spring-data-commons | Release train |
|---|---:|---:|---|
| 4.1.2 | 5.1.2 | 4.1.2 | 2026.0 |
| 4.0.9 | 5.0.8 | 4.0.8 | 2025.1 |
| 3.5.16 | 4.5.13 | 3.5.13 | 2025.0 |

Đây là ví dụ về bộ version được Boot quản lý, không phải khuyến nghị nâng cấp một dự án cũ mà chưa đánh giá Java, Spring Framework và thư viện khác.

Một số quy tắc:

- Không tự đặt cùng một version cho tất cả Spring Data module.
- Không override riêng spring-data-rest-webmvc hoặc spring-data-commons nếu chưa kiểm tra compatibility matrix.
- Dùng starter của Spring Boot và bỏ trường version khi Boot BOM đã quản lý artifact.
- Nếu không dùng Spring Boot, sử dụng Spring Data Release Train BOM để đồng bộ module Spring Data.
- Khi nâng cấp, đọc release notes và migration guide của release train tương ứng; không chỉ thay số version trong build file.

### 4.2. Phân biệt các artifact

| Artifact | Vai trò |
|---|---|
| spring-boot-starter-data-rest | Starter Boot để bật Spring Data REST |
| spring-data-rest-webmvc | REST exporter dựa trên Spring MVC |
| spring-data-rest-core | Thành phần lõi của Spring Data REST |
| spring-data-rest-hal-explorer | HAL browser để khám phá API, nếu ứng dụng cần |
| spring-data-jpa | Repository và mapping cho JPA |
| spring-data-mongodb | Repository và mapping cho MongoDB |
| spring-data-neo4j | Repository và mapping cho Neo4j |
| spring-data-cassandra | Repository và mapping cho Cassandra |
| Driver database | Kết nối thật tới PostgreSQL, MongoDB, Cassandra và các store khác |

Thêm starter REST mà thiếu store module hoặc driver thì không tạo được repository hoạt động. Thêm store starter mà chưa bật REST exporter cũng không có nghĩa repository sẽ được xuất thành endpoint.

### 4.3. Xem dependency thực tế

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.data
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-rest-webmvc --configuration runtimeClasspath
~~~

Đọc kết quả theo thứ tự:

1. Xác định version của spring-data-rest-webmvc.
2. Xác định version của spring-data-commons.
3. Xác định store module thực tế, ví dụ spring-data-jpa hoặc spring-data-mongodb.
4. Kiểm tra có dependency bị override hoặc kéo vào một version khác qua dependency bắc cầu hay không.
5. Đối chiếu toàn bộ version với Managed Dependency Coordinates của đúng Spring Boot line hoặc Spring Data Release Train BOM.
6. Đọc tài liệu Spring Data REST và release notes đúng major/minor version trước khi sử dụng một tính năng cụ thể.

Dependency tree chỉ chứng minh build đã giải quyết dependency. Nó không chứng minh repository của store đã được xuất đúng hoặc thao tác database hoạt động đúng. Cần kiểm thử endpoint với store thật hoặc môi trường integration test tương ứng.

## 5. Ví dụ khởi tạo với JPA và PostgreSQL

JPA là một trong năm store có integration test chính thức với Spring Data REST. Ví dụ dưới đây dùng Spring Boot 4.1.2; version của starter và Spring Data module được Boot quản lý.

### 5.1. Maven dependencies

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Đây là phần dependency của POM. Để ứng dụng chạy, cần cấu hình datasource PostgreSQL và tạo database phù hợp. Không khai báo version riêng cho starter REST, starter JPA hay driver khi đã dùng Boot dependency management.

### 5.2. Entity và repository

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
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
}
~~~

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Đặt entity và repository trong package được ứng dụng Spring Boot scan. JpaRepository cung cấp CRUD, paging và sorting. Repository annotation đặt tên collection rõ ràng để endpoint ổn định.

### 5.3. Cấu hình kết nối

Ví dụ cấu hình tối thiểu cho PostgreSQL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=app
spring.datasource.password=change-me
spring.jpa.hibernate.ddl-auto=update
~~~

Giá trị mật khẩu ở trên chỉ là ví dụ cấu hình cục bộ. Môi trường thực tế nên lấy secret từ biến môi trường hoặc secret manager. Với hệ thống production, quản lý schema bằng Flyway hoặc Liquibase thường dễ kiểm soát hơn việc tự động cập nhật schema.

### 5.4. Endpoint được xuất

Với repository public và cấu hình mặc định, Spring Data REST phát hiện repository và xuất collection resource:

| HTTP | URL | Mục đích |
|---|---|---|
| GET | /products | Lấy collection |
| GET | /products/{id} | Lấy một item |
| POST | /products | Tạo item khi save được export |
| PUT/PATCH | /products/{id} | Cập nhật item theo cấu hình export |
| DELETE | /products/{id} | Xóa item khi delete được export |

Khám phá API từ root URL và yêu cầu media type HAL:

~~~bash
curl -i http://localhost:8080/
curl -i -H "Accept: application/hal+json" http://localhost:8080/products
~~~

Root resource trả về các liên kết tới resource được xuất. Collection response có thể chứa danh sách embedded rỗng nếu chưa có dữ liệu; điều đó không có nghĩa endpoint không tồn tại.

Tạo thử một product:

~~~bash
curl -i -X POST http://localhost:8080/products \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"name":"Keyboard"}'
~~~

Khi repository và database hoạt động đúng, thao tác tạo trả về HTTP 201 Created và Location header trỏ tới item mới. ID cụ thể do database sinh nên không thể khẳng định trước.

Khi đổi từ JPA sang MongoDB, Neo4j hoặc Cassandra, phải thay store starter, driver, mapping, cấu hình và repository theo module đó. Không chỉ đổi tên dependency trong POM.

## 6. Kiểm soát repository nào được xuất

Spring Data REST có thể tự động phát hiện repository. Repository public thường được xét để xuất theo detection strategy đang cấu hình. Cần kiểm tra repository, annotation và từng method được công bố.

Các strategy thường gặp:

| Strategy | Hành vi |
|---|---|
| DEFAULT | Dùng quy tắc mặc định, xét repository public và cờ exported |
| ANNOTATED | Chỉ xét repository được đánh dấu bằng RepositoryRestResource |
| VISIBILITY | Dựa trên visibility của repository |
| ALL | Xét mọi repository, kể cả repository không public |

Ví dụ đổi path collection:

~~~java
@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Ẩn một repository nội bộ:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

Ẩn một finder method:

~~~java
import java.util.List;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(exported = false)
    List<Product> findByInternalCode(String internalCode);
}
~~~

Repository có thể tồn tại và được service sử dụng nhưng không xuất hiện trong REST API do visibility, detection strategy hoặc exported=false.

Tự động xuất repository cũng là quyết định về hợp đồng API và bảo mật. Chỉ công bố thao tác phù hợp với API công khai; dùng Spring Security để bảo vệ endpoint. Với nghiệp vụ nhiều bước, DTO riêng, phân quyền phức tạp hoặc workflow, controller/service thường giúp kiểm soát hợp đồng rõ hơn.

## 7. Kiểm thử mức hỗ trợ theo đúng phiên bản

Đừng dừng ở việc ứng dụng khởi động thành công. Hãy tạo integration test hoặc smoke test cho đúng cặp Spring Data REST và store module đang triển khai.

Checklist tối thiểu:

1. **Context:** ứng dụng khởi động, repository bean được tạo và database kết nối được.
2. **Discovery:** GET root trả HTTP 200 và có link tới collection mong đợi.
3. **Collection:** GET collection trả HTTP 200, media type HAL JSON và metadata paging phù hợp.
4. **Create:** POST trả HTTP 201 và Location header hợp lệ.
5. **Read:** GET theo Location trả lại dữ liệu vừa tạo.
6. **Update:** PUT/PATCH hoạt động theo repository method và exposure configuration.
7. **Delete:** DELETE chỉ thành công khi thao tác delete được export.
8. **Finder/search:** kiểm tra search resource và query method nếu ứng dụng sử dụng.
9. **Store mapping:** kiểm tra ID, association, kiểu dữ liệu, transaction và optimistic locking theo module.
10. **Paging/sorting:** kiểm tra các tính năng ứng dụng cần; không giả định mọi store có cùng semantics.
11. **Security:** người dùng không có quyền không thể gọi thao tác nhạy cảm.
12. **Version:** chạy lại các test trên đúng version đang deploy, không chỉ trên version mới nhất trong tài liệu.

Với store ngoài danh sách integration-tested, cần kiểm tra tối thiểu CRUD, ID mapping, query method, paging/sorting và association nếu ứng dụng cần các tính năng đó. Với R2DBC, xác minh rõ repository reactive có được exporter phiên bản đang dùng hỗ trợ hay không; không suy luận điều đó từ Repository abstraction.

### Một số lỗi thường gặp

- **404 Not Found:** sai path/base path, repository không được phát hiện hoặc resource không được xuất.
- **405 Method Not Allowed:** resource tồn tại nhưng method tương ứng không có hoặc đã bị tắt qua exported/exposure configuration.
- **NoSuchMethodError/ClassNotFoundException:** có thể do lệch version, override BOM hoặc module trùng phiên bản.
- **Root có link nhưng thao tác store lỗi:** exporter đã phát hiện repository, nhưng driver, mapping, transaction hoặc query của store cần kiểm tra.
- **Build thành công nhưng REST endpoint không xuất:** dependency có mặt không đồng nghĩa repository được scan và export.
- **API lộ thao tác nội bộ:** cần kiểm tra detection strategy, exported flag, Spring Security và thiết kế hợp đồng công khai.

## 8. Quy trình lựa chọn và xác minh

1. Liệt kê mô hình dữ liệu, query pattern, transaction và yêu cầu vận hành.
2. Chọn database và Spring Data module tương ứng.
3. Kiểm tra store có trong danh sách integration-tested của Spring Data REST hay chỉ có Repository abstraction.
4. Nếu dùng R2DBC, xác minh riêng repository reactive và kiến trúc WebMVC/WebFlux.
5. Chọn Spring Boot line hoặc Spring Data release train tương thích với Java và Spring Framework.
6. Để BOM quản lý version; kiểm tra dependency tree sau khi build.
7. Thêm REST exporter, store module, driver và cấu hình kết nối.
8. Tạo repository mẫu, kiểm tra root HAL, collection và item endpoint.
9. Chạy integration test cho CRUD, mapping, query, paging, security và các tính năng cần thiết.
10. Chỉ công bố API sau khi xác nhận cả compatibility lẫn exposure policy.

## Tài liệu tham khảo chính thức

- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): cách khởi tạo, store được hỗ trợ và phạm vi integration test.
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection/item resources, HAL và HTTP methods.
- [Spring Data REST — Customizing](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): repository detection, exported flag và tùy chỉnh endpoint.
- [Spring Data REST — Dependencies](https://docs.spring.io/spring-data/rest/reference/data-commons/dependencies.html): quản lý dependency và Spring Data release train.
- [Spring Data R2DBC — Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html): ReactiveCrudRepository và hành vi repository reactive.
- [Spring Boot 4.1 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html): version do Boot 4.1 quản lý.
- [Spring Boot 4.0 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html): version do Boot 4.0 quản lý.
- [Spring Boot 3.5 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): version do Boot 3.5 quản lý.
- [Spring Data 2026.0 Release Notes](https://github.com/spring-projects/spring-data-commons/wiki/Spring-Data-2026.0-Release-Notes): thay đổi và lưu ý nâng cấp của release train.

Phiên bản Spring thay đổi theo patch và release train. Khi bắt đầu dự án hoặc nâng cấp, hãy đối chiếu tài liệu chính thức và dependency tree của chính dự án tại thời điểm triển khai.
