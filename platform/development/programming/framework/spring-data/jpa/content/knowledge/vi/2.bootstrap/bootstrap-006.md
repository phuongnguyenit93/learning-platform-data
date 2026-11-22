# Phân biệt cơ sở dữ liệu nhúng và cơ sở dữ liệu dùng trong triển khai

Trong Spring Data JPA, cơ sở dữ liệu nhúng (embedded database) và cơ sở dữ liệu dùng trong triển khai (thường là cơ sở dữ liệu máy chủ hoặc external database) khác nhau chủ yếu ở **cách chạy, nơi lưu trữ dữ liệu và cách ứng dụng kết nối**. Spring Data JPA vẫn làm việc qua Repository, JPA và Hibernate; khi đổi loại cơ sở dữ liệu, phần thường phải thay đổi là JDBC driver, cấu hình DataSource, cách quản lý schema và vận hành.

## 1. Vị trí của cơ sở dữ liệu trong Spring Data JPA

Luồng xử lý điển hình:

~~~text
Ứng dụng
   |
   v
Spring Data Repository
   |
   v
JPA / EntityManager
   |
   v
Hibernate (JPA provider)
   |
   v
JDBC / DataSource
   |
   +----> H2 chạy embedded trong tiến trình ứng dụng
   |
   +----> PostgreSQL / MySQL chạy như dịch vụ cơ sở dữ liệu riêng
~~~

- **Spring Data JPA** cung cấp các Repository như JpaRepository để thao tác với entity.
- **JPA** định nghĩa API và quy tắc ánh xạ đối tượng Java sang bảng dữ liệu.
- **Hibernate** thường là JPA provider thực thi các thao tác ORM.
- **DataSource** cung cấp kết nối JDBC.
- **Cơ sở dữ liệu** thực sự lưu và truy vấn dữ liệu. Nó có thể chạy cùng tiến trình ứng dụng hoặc chạy như một dịch vụ độc lập.

Vì vậy, Repository thường không cần viết lại khi chuyển từ H2 sang PostgreSQL. Tuy nhiên, không nên giả định hai hệ quản trị có cú pháp SQL, kiểu dữ liệu, hành vi khóa hoặc khả năng tương thích hoàn toàn giống nhau.

## 2. Cơ sở dữ liệu nhúng là gì?

Cơ sở dữ liệu nhúng là hệ quản trị cơ sở dữ liệu được tích hợp và chạy bên trong tiến trình của ứng dụng hoặc được ứng dụng khởi tạo trực tiếp. Ứng dụng thường không cần kết nối đến một máy chủ cơ sở dữ liệu độc lập.

Các ví dụ thường gặp:

- **H2** ở chế độ embedded hoặc in-memory.
- **HSQLDB**.
- **Apache Derby**.

Với H2 in-memory, dữ liệu thường nằm trong bộ nhớ của tiến trình Java. Khi ứng dụng kết thúc, dữ liệu trong bộ nhớ mất đi. H2 cũng hỗ trợ chế độ lưu vào tệp; do đó, không phải mọi cơ sở dữ liệu nhúng đều mất dữ liệu khi ứng dụng tắt.

Ví dụ URL H2:

~~~properties
spring.datasource.url=jdbc:h2:mem:catalog
~~~

Ứng dụng có thể tự khởi tạo cơ sở dữ liệu khi chạy. Cách này thuận tiện cho học tập, demo, kiểm thử hoặc các ứng dụng nhỏ cần thiết lập đơn giản.

## 3. Cơ sở dữ liệu dùng trong triển khai là gì?

Trong ứng dụng web hoặc dịch vụ nhiều người dùng, cơ sở dữ liệu thường được triển khai như một dịch vụ riêng. Ứng dụng Java kết nối đến dịch vụ đó qua mạng bằng JDBC.

Các ví dụ phổ biến:

- **PostgreSQL**.
- **MySQL** hoặc **MariaDB**.
- **Microsoft SQL Server**.
- **Oracle Database**.

Máy chủ cơ sở dữ liệu có vòng đời độc lập với ứng dụng. Ứng dụng có thể khởi động lại hoặc mở rộng thành nhiều instance mà vẫn kết nối đến cùng một cơ sở dữ liệu. Dữ liệu thường được lưu trên ổ đĩa hoặc dịch vụ lưu trữ bền vững và được quản trị bằng các công cụ backup, restore, monitoring, replication và bảo mật.

Ví dụ URL PostgreSQL:

~~~properties
spring.datasource.url=jdbc:postgresql://db-host:5432/catalog
spring.datasource.username=catalog_app
spring.datasource.password=change-me
~~~

Trong môi trường triển khai thật, thông tin đăng nhập nên được cấp qua biến môi trường hoặc hệ thống quản lý secret, không ghi mật khẩu thật vào mã nguồn hay file cấu hình được commit.

## 4. So sánh hai cách triển khai

| Tiêu chí | Cơ sở dữ liệu nhúng | Cơ sở dữ liệu máy chủ |
|---|---|---|
| Nơi chạy | Thường chạy trong tiến trình ứng dụng | Chạy như một dịch vụ riêng |
| Kết nối | Thường truy cập trực tiếp trong cùng tiến trình | Ứng dụng kết nối qua mạng bằng JDBC |
| Cài đặt ban đầu | Đơn giản, thường chỉ cần dependency và cấu hình URL | Cần tạo hoặc cấp phát dịch vụ, database, user và quyền truy cập |
| Vòng đời | Thường gắn với vòng đời ứng dụng | Độc lập với vòng đời ứng dụng |
| Lưu trữ | Có thể ở bộ nhớ hoặc tệp cục bộ | Thường dùng ổ đĩa hoặc dịch vụ lưu trữ bền vững |
| Dữ liệu sau khi khởi động lại | Mất nếu dùng in-memory; còn nếu dùng chế độ tệp thì có thể được giữ lại | Thường được giữ lại nếu lưu trữ và cấu hình backup đúng |
| Nhiều instance ứng dụng | Mỗi tiến trình có thể có một database riêng, tùy chế độ | Nhiều instance có thể cùng kết nối một database |
| Vận hành | Ít thành phần phải quản trị | Cần quản trị kết nối, quyền, backup, phục hồi, giám sát và bảo mật |
| Mục đích thường gặp | Học tập, demo, kiểm thử, ứng dụng đơn tiến trình | Ứng dụng staging/production, nhiều người dùng hoặc nhiều instance |
| Khả năng mở rộng | Phụ thuộc engine và mô hình lưu trữ; thường phù hợp phạm vi nhỏ | Thường có nhiều lựa chọn về kết nối đồng thời, replication và mở rộng |

Đây là cách dùng phổ biến, không phải quy tắc tuyệt đối. Một ứng dụng desktop hoặc thiết bị đơn người dùng có thể dùng database nhúng trong môi trường triển khai. Ngược lại, PostgreSQL chạy trong Docker trên máy phát triển vẫn là cơ sở dữ liệu máy chủ, dù nó chỉ chạy trên máy cá nhân.

## 5. Phân biệt loại hệ quản trị và chế độ chạy

Không nên đồng nhất tên sản phẩm với cách triển khai:

- H2 có thể chạy ở chế độ embedded, in-memory, lưu tệp hoặc server mode.
- PostgreSQL thường chạy như một server độc lập.
- Một cơ sở dữ liệu lưu vào tệp vẫn có thể là database nhúng.
- Một cơ sở dữ liệu chạy trên cùng máy với ứng dụng vẫn có thể là dịch vụ độc lập.

Từ “embedded” mô tả cách database được tích hợp và vận hành trong ứng dụng. Từ “production” mô tả môi trường sử dụng. Hai khái niệm này không phải hai nhóm sản phẩm loại trừ nhau.

## 6. Cùng một Repository có thể dùng với nhiều cơ sở dữ liệu

Ví dụ entity và Repository sau không phụ thuộc riêng vào H2 hay PostgreSQL:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
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
}
~~~

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Đây là các đoạn mã cần đặt trong một dự án Spring Boot có dependency Spring Data JPA; chúng không phải chương trình Java độc lập có thể chạy chỉ bằng javac.

Repository gọi các phương thức như save, findById hoặc findAll. Hibernate chuyển thao tác JPA thành SQL phù hợp với database và dialect tương ứng. Dù vậy, nếu ứng dụng dùng SQL native query, kiểu dữ liệu đặc thù hoặc tính năng riêng của một hệ quản trị, việc chuyển database có thể cần sửa câu SQL hoặc mapping.

## 7. Cấu hình cơ sở dữ liệu nhúng với H2

Trong dự án Spring Boot, cần có starter Spring Data JPA và JDBC driver của database đang dùng. Ví dụ các dependency Maven liên quan:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <!-- Driver dùng khi chạy profile phát triển với H2 -->
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Driver dùng khi kết nối PostgreSQL -->
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Ví dụ file src/main/resources/application-dev.properties:

~~~properties
spring.datasource.url=jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true

spring.h2.console.enabled=true
spring.h2.console.path=/h2-console
~~~

Giải thích:

- jdbc:h2:mem:catalog tạo database tên catalog trong bộ nhớ.
- DB_CLOSE_DELAY=-1 giữ database in-memory tồn tại cho đến khi JVM kết thúc, kể cả khi không còn kết nối đang mở.
- ddl-auto=create-drop yêu cầu Hibernate tạo schema khi khởi tạo và xóa schema khi EntityManagerFactory đóng. Đây là lựa chọn tiện lợi cho môi trường phát triển hoặc kiểm thử vì dữ liệu có thể bị tạo lại.
- show-sql và format_sql hỗ trợ quan sát SQL trong lúc học và gỡ lỗi.
- H2 Console cho phép kiểm tra database qua trình duyệt. Chỉ bật khi cần trong môi trường phát triển và không công khai console trong môi trường production.

Nếu muốn dữ liệu H2 tồn tại qua lần khởi động lại, có thể dùng URL lưu vào tệp, ví dụ:

~~~properties
spring.datasource.url=jdbc:h2:file:./data/catalog
~~~

Đường dẫn tương đối được tính từ thư mục làm việc của tiến trình. Cần quản lý quyền truy cập, backup và vị trí tệp nếu dùng cách này lâu dài.

## 8. Cấu hình cơ sở dữ liệu máy chủ cho môi trường triển khai

Ví dụ ứng dụng kết nối PostgreSQL bằng file src/main/resources/application-prod.properties:

~~~properties
spring.datasource.url=${DB_URL}
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${DB_PASSWORD}
spring.datasource.driver-class-name=org.postgresql.Driver

spring.jpa.hibernate.ddl-auto=validate
spring.jpa.show-sql=false
spring.jpa.open-in-view=false
~~~

Các biến môi trường có thể được cấp khi chạy ứng dụng:

~~~text
SPRING_PROFILES_ACTIVE=prod
DB_URL=jdbc:postgresql://db-host:5432/catalog
DB_USERNAME=catalog_app
DB_PASSWORD=<secret>
~~~

Trong ví dụ trên:

- DB_URL trỏ đến máy chủ, cổng và database cần kết nối. Cổng mặc định của PostgreSQL là 5432.
- Database và tài khoản ứng dụng phải được tạo, cấp quyền trước hoặc bằng quy trình triển khai riêng.
- ddl-auto=validate yêu cầu Hibernate kiểm tra mapping entity có phù hợp với schema hiện có hay không. Nó không tự tạo hoặc cập nhật schema.
- open-in-view=false tắt việc giữ persistence context mở xuyên suốt quá trình xử lý và render response của web request. Khi dùng cấu hình này, hãy tải dữ liệu cần thiết trong service hoặc trong transaction để tránh lỗi truy cập quan hệ lazy sau khi session đã đóng.

Không nên ghi mật khẩu production trực tiếp vào application-prod.properties. Có thể dùng biến môi trường, Docker/Kubernetes Secret hoặc secret manager của nền tảng triển khai. Tài khoản ứng dụng nên có quyền tối thiểu cần thiết.

## 9. Chọn cấu hình theo Spring Profile

Có thể duy trì nhiều file cấu hình trong cùng dự án:

~~~text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
~~~

Ví dụ application.properties:

~~~properties
spring.application.name=catalog-service
~~~

Chạy môi trường phát triển:

~~~text
SPRING_PROFILES_ACTIVE=dev
~~~

Chạy môi trường triển khai:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Spring Boot nạp cấu hình chung và cấu hình của profile đang kích hoạt. Khi triển khai, cần kiểm tra profile thực sự được kích hoạt và bảo đảm DB_URL trỏ đúng database. Nếu không đặt URL hoặc kích hoạt nhầm profile, ứng dụng có thể dùng cấu hình khác với dự định.

Khi đóng gói ứng dụng cho nhiều môi trường, có thể dùng cùng một artifact nhưng cấp cấu hình và secret khác nhau cho từng môi trường. Điều này giúp tránh phải sửa mã nguồn chỉ để đổi địa chỉ database.

## 10. Quản lý schema và dữ liệu khởi tạo

Spring Data JPA không đồng nghĩa với việc Hibernate luôn tự tạo bảng. Việc tạo, cập nhật và quản lý schema cần được cấu hình rõ ràng.

Các giá trị thường dùng của spring.jpa.hibernate.ddl-auto:

| Giá trị | Hành vi |
|---|---|
| none | Hibernate không tự thay đổi schema |
| validate | Kiểm tra mapping entity với schema hiện có |
| update | Cố gắng điều chỉnh schema theo entity |
| create | Tạo lại schema khi khởi tạo |
| create-drop | Tạo schema khi khởi tạo và xóa khi đóng |

Gợi ý sử dụng:

- Với H2 dùng tạm trong lúc học hoặc test, create-drop thường tiện lợi.
- Với database triển khai, nên quản lý thay đổi schema bằng migration có phiên bản, ví dụ Flyway hoặc Liquibase.
- Khi migration đã tạo schema, có thể dùng validate để phát hiện mapping không khớp.
- Không nên dựa vào update như quy trình migration production. Việc tự động cập nhật không thay thế được migration có lịch sử, review, kiểm soát thứ tự và kế hoạch rollback.

Ví dụ migration Flyway src/main/resources/db/migration/V1__create_products.sql:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
~~~

Flyway chạy migration theo phiên bản đã ghi nhận trong database. Khi schema cần thay đổi, thêm migration mới thay vì sửa tùy tiện migration đã áp dụng ở môi trường dùng chung. Cú pháp migration phải tương thích với database mục tiêu; nếu migration sử dụng tính năng riêng của PostgreSQL thì không thể mặc định chạy được trên H2.

Spring Boot cũng hỗ trợ script schema.sql và data.sql để khởi tạo schema hoặc dữ liệu mẫu. Cần chú ý thứ tự chạy script so với Hibernate. Nếu script cần chạy sau khi Hibernate tạo schema, có thể cấu hình spring.jpa.defer-datasource-initialization=true. Với môi trường triển khai, migration có phiên bản thường dễ kiểm soát hơn script khởi tạo đơn giản.

## 11. Những điểm cần kiểm tra khi chuyển từ H2 sang PostgreSQL hoặc MySQL

Dùng cùng entity và Repository không bảo đảm mọi truy vấn sẽ chạy giống nhau. Trước khi chuyển môi trường, cần kiểm tra:

1. **Dialect và cú pháp SQL:** hàm ngày giờ, phép nối chuỗi, phân trang, câu lệnh native query và cú pháp giới hạn kết quả có thể khác nhau.
2. **Kiểu dữ liệu:** kiểu số, boolean, JSON, UUID, ngày giờ và độ chính xác timestamp có thể được ánh xạ khác nhau.
3. **Sinh khóa:** identity, sequence và cách Hibernate lấy giá trị khóa tự sinh có thể khác nhau.
4. **Ràng buộc và chỉ mục:** kiểm tra unique constraint, foreign key, index và quy tắc xử lý giá trị null.
5. **Chữ hoa, chữ thường và collation:** cách so sánh chuỗi hoặc xử lý tên bảng/cột có thể khác.
6. **Transaction và khóa:** mức cô lập, khóa hàng, deadlock và hành vi khi có nhiều giao dịch đồng thời cần được kiểm thử trên database đích.
7. **Migration:** chạy toàn bộ migration trên một database mới và kiểm tra cả trường hợp nâng cấp từ phiên bản schema đang được sử dụng.
8. **Dữ liệu:** nếu chuyển dữ liệu đã có, cần có kế hoạch export/import, chuyển đổi kiểu dữ liệu, đối soát số bản ghi và kiểm tra tính toàn vẹn.

H2 rất hữu ích cho kiểm thử nhanh, nhưng một bài test chạy qua H2 không chứng minh rằng câu SQL hoặc migration chắc chắn chạy được trên PostgreSQL. Với ứng dụng production dùng PostgreSQL, nên có integration test chạy trên PostgreSQL thật hoặc PostgreSQL container, chẳng hạn thông qua Testcontainers. Khi đó, test kiểm tra đúng engine, dialect và hành vi gần với môi trường triển khai.

## 12. Lỗi thường gặp và cách xử lý

**Ứng dụng bất ngờ tạo database H2 khi chạy production**

- Kiểm tra SPRING_PROFILES_ACTIVE.
- Kiểm tra spring.datasource.url có được nạp từ đúng file hoặc biến môi trường hay không.
- Bảo đảm JDBC driver của database đích có trong classpath.
- Cấu hình URL production rõ ràng và kiểm tra cấu hình ngay khi khởi động.

**Lỗi không kết nối được database máy chủ**

- Kiểm tra hostname, port và tên database trong JDBC URL.
- Kiểm tra dịch vụ database đang chạy và có thể truy cập từ môi trường chạy ứng dụng.
- Kiểm tra firewall, network policy, username, password và quyền của tài khoản.
- Nếu chạy bằng Docker Compose, hostname thường là tên service trong network của Compose, không nhất thiết là localhost.

**Bảng không tồn tại hoặc schema không khớp**

- Kiểm tra migration đã chạy thành công chưa.
- Kiểm tra database/schema mà ứng dụng đang kết nối.
- Kiểm tra tên bảng, tên cột và mapping entity.
- Không khắc phục bằng cách tùy tiện đổi sang create trên database đang có dữ liệu.

**Dữ liệu biến mất sau khi khởi động lại**

- Kiểm tra URL có dùng jdbc:h2:mem: hay không.
- Database in-memory mất dữ liệu khi tiến trình kết thúc; nếu cần lưu bền vững, dùng chế độ tệp hoặc database máy chủ với storage phù hợp.
- Không nhầm DB_CLOSE_DELAY=-1 với lưu trữ bền vững: tùy chọn này chỉ giữ database in-memory trong thời gian JVM còn chạy.

**Test chạy với H2 nhưng lỗi trên PostgreSQL**

- Kiểm tra native query, kiểu dữ liệu, sequence/identity và migration.
- Chạy integration test trên cùng hệ quản trị và phiên bản gần với production.
- Tránh dựa vào hành vi riêng của H2 nếu ứng dụng sẽ triển khai trên database khác.

## 13. Quy trình lựa chọn thực tế

- **Học Spring Data JPA hoặc làm demo:** dùng H2 in-memory để bắt đầu nhanh, quan sát entity, Repository và SQL.
- **Unit test hoặc test repository đơn giản:** có thể dùng H2 nếu truy vấn và tính năng sử dụng tương thích.
- **Integration test cần phản ánh production:** ưu tiên chạy cùng engine với production, ví dụ PostgreSQL qua Testcontainers.
- **Ứng dụng web nhiều người dùng:** thường dùng PostgreSQL, MySQL hoặc một dịch vụ database được quản lý; cấu hình connection pool, backup, giám sát và bảo mật.
- **Ứng dụng desktop, offline hoặc chỉ có một tiến trình:** database nhúng lưu tệp có thể phù hợp nếu đã xác định rõ nhu cầu backup, phục hồi, đồng bộ và truy cập đồng thời.

Trước khi triển khai, hãy xác nhận profile, JDBC URL, driver, tài khoản và quyền truy cập; schema đã được tạo bằng migration; Hibernate dùng validate hoặc none theo chiến lược schema; integration test đã chạy trên database đích; và dữ liệu có kế hoạch backup/restore.

## 14. Kết luận

Cơ sở dữ liệu nhúng giúp khởi tạo nhanh và giảm công việc vận hành, nên phù hợp với học tập, demo, kiểm thử hoặc ứng dụng đơn tiến trình. Cơ sở dữ liệu máy chủ tách biệt khỏi vòng đời ứng dụng, hỗ trợ mô hình nhiều instance và thường phù hợp với hệ thống triển khai nhiều người dùng. Trong Spring Data JPA, Repository và entity có thể giữ nguyên khi đổi database, nhưng phải cấu hình đúng driver và DataSource, quản lý schema bằng migration, đồng thời kiểm thử các khác biệt của hệ quản trị đích.
