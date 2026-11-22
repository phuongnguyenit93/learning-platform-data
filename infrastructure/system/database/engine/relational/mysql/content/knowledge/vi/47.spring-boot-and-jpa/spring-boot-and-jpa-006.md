# MySQL dialect theo phiên bản Hibernate và server

Bài học này thuộc module **DATABASE_MYSQL**. Trong ứng dụng Spring Boot dùng Spring Data JPA và Hibernate, dialect là lớp mô tả cách Hibernate tạo và thực thi SQL phù hợp với hệ quản trị cơ sở dữ liệu. Khi kết nối tới MySQL, Hibernate cần biết những cú pháp, kiểu dữ liệu, cơ chế sinh khóa, phân trang, khóa hàng và tính năng SQL mà máy chủ hỗ trợ.

Dialect phải tương thích với cả phiên bản Hibernate lẫn phiên bản MySQL Server. Chọn sai dialect có thể khiến Hibernate sinh cú pháp không được server chấp nhận, bỏ qua khả năng mới, ánh xạ kiểu dữ liệu không phù hợp hoặc tạo DDL sai kỳ vọng. Ngược lại, đặt một dialect quá mới không làm máy chủ cũ tự có thêm tính năng. Bài học này giải thích cách Hibernate nhận diện database, khi nào nên cấu hình tường minh và cách kiểm chứng trên đúng phiên bản triển khai.

## 1. Dialect trong Hibernate làm nhiệm vụ gì?

Dialect là bộ quy tắc để Hibernate chuyển mô hình ORM và truy vấn HQL/JPQL thành SQL cụ thể cho một database. Cùng một truy vấn JPQL có thể được chuyển thành SQL khác nhau tùy dialect.

Ví dụ, ứng dụng có truy vấn phân trang:

~~~java
Page<Order> page = orderRepository.findByCustomerId(
    customerId,
    PageRequest.of(0, 20, Sort.by("createdAt").descending())
);
~~~

Hibernate cần tạo SQL có giới hạn số hàng và cách bỏ qua hàng phù hợp với database. Với MySQL, cú pháp thường dùng là LIMIT và OFFSET. Database khác có thể dùng cú pháp khác.

Dialect còn ảnh hưởng tới:

- Kiểu SQL được chọn khi ánh xạ Java type sang cột database.
- Cách tạo primary key tự tăng và biểu diễn identity column.
- Cú pháp phân trang, khóa hàng và các biểu thức SQL.
- Cách Hibernate tạo DDL cho table, index, constraint và column.
- Việc nhận diện hỗ trợ của các tính năng như window function, CTE, JSON, sequence hoặc returning clause.
- Một số hàm SQL và cách biểu diễn giá trị ngày giờ.

Dialect không phải là cấu hình kết nối. JDBC URL, hostname, port, username, password và driver vẫn do datasource quản lý. Dialect cũng không thay thế schema migration, quyền truy cập hay cấu hình transaction.

## 2. Phân biệt Hibernate version và MySQL Server version

Khi chọn dialect, cần biết hai phiên bản độc lập:

1. **Hibernate version:** quyết định những lớp dialect nào tồn tại, API nào được hỗ trợ và cách Hibernate diễn giải metadata.
2. **MySQL Server version:** quyết định server thực sự chấp nhận cú pháp SQL và tính năng nào.

Spring Boot quản lý phiên bản Hibernate thông qua dependency management của từng release. Không nên chỉ nhìn phiên bản Spring Boot rồi đoán tên dialect. Với Hibernate 6/7, group ID của Hibernate Core thường là org.hibernate.orm; Hibernate 5 dùng org.hibernate. Hãy xem dependency thực tế của ứng dụng:

~~~bash
mvn dependency:tree -Dincludes=org.hibernate.orm:hibernate-core
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
~~~

Với dự án Hibernate 5 dùng group ID cũ, có thể lọc dependency Maven bằng:

~~~bash
mvn dependency:tree -Dincludes=org.hibernate:hibernate-core
~~~

Tên artifact có thể khác giữa các thế hệ Hibernate. Mục tiêu là xác nhận chính xác Hibernate Core đang có trên runtime classpath.

Kiểm tra MySQL Server bằng SQL:

~~~sql
SELECT VERSION() AS server_version,
       @@version_comment AS distribution,
       @@version_compile_os AS server_os,
       @@version_compile_machine AS server_architecture;
~~~

Hoặc đọc từ JDBC:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductName());
    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDatabaseMajorVersion());
    System.out.println(metadata.getDatabaseMinorVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());
}
~~~

Database product version là thông tin về máy chủ mà JDBC driver báo cáo; driver version là phiên bản Connector/J. Hai giá trị này không giống nhau.

Cần kiểm tra phiên bản server từ đúng endpoint mà ứng dụng sẽ sử dụng. Nếu kết nối qua proxy, managed database, compatibility layer hoặc dịch vụ tương thích MySQL, metadata có thể phản ánh phiên bản tương thích hoặc chuỗi phiên bản riêng của nhà cung cấp. Khi đó cần đối chiếu tài liệu của nền tảng.

## 3. Hibernate tự nhận diện dialect như thế nào?

Trong phần lớn cấu hình Hibernate hiện đại, ứng dụng không cần chỉ định dialect thủ công. Khi khởi tạo SessionFactory/EntityManagerFactory, Hibernate đọc JDBC metadata từ connection để nhận diện database product và version, sau đó chọn dialect phù hợp thông qua cơ chế resolver.

Luồng khái quát:

~~~text
Spring Boot
    |
    v
DataSource / HikariCP
    |
    v
MySQL Connector/J
    |
    v
JDBC DatabaseMetaData
    |
    v
Hibernate DialectResolver
    |
    v
MySQLDialect phù hợp
    |
    v
Hibernate sinh SQL và DDL
~~~

Tự nhận diện thường là lựa chọn đơn giản và ít lỗi nhất khi:

- MySQL Server báo metadata chính xác.
- JDBC driver tương thích với server.
- Ứng dụng không dùng một compatibility layer làm sai lệch thông tin product/version.
- Phiên bản Hibernate hỗ trợ release series MySQL đang chạy.

Khi khởi động, Hibernate có thể ghi dialect được chọn trong log. Hãy bật log phù hợp ở môi trường kiểm thử nếu cần xác minh. Không nên phụ thuộc vào việc dò chuỗi log bằng mã ứng dụng production.

### 3.1. Khi nào cần cấu hình tường minh?

Cân nhắc cấu hình dialect tường minh khi:

- JDBC metadata không nhận diện đúng database hoặc phiên bản.
- Kết nối đi qua proxy/driver đặc biệt làm thông tin metadata không chính xác.
- Hệ thống cần cố định một baseline SQL để chạy trên nhiều máy chủ có phiên bản khác nhau.
- Đã xác minh dialect tự nhận diện chọn không đúng lớp cho môi trường cụ thể.
- Nhà cung cấp database yêu cầu một cấu hình dialect tương thích riêng.

Không đặt dialect chỉ vì muốn Hibernate sinh SQL “mới hơn”. Nếu server không hỗ trợ tính năng đó, câu SQL vẫn sẽ thất bại khi thực thi.

## 4. Tên dialect theo thế hệ Hibernate

Tên lớp dialect đã thay đổi giữa các thế hệ Hibernate. Đây là một điểm thường gây lỗi khi nâng cấp Spring Boot.

| Thế hệ Hibernate | Cách cấu hình MySQL thường gặp | Lưu ý |
|---|---|---|
| Hibernate 5.x | Có các lớp theo phiên bản như MySQL57Dialect, MySQL8Dialect tùy release | Chọn lớp tồn tại trong đúng phiên bản Hibernate và phù hợp server |
| Hibernate 6.x | Dùng org.hibernate.dialect.MySQLDialect nếu cần chỉ định | Các lớp version-specific cũ như MySQL8Dialect đã bị loại bỏ khỏi API dialect tiêu chuẩn |
| Hibernate 7.x | Dùng hệ dialect hiện hành, thường là MySQLDialect | Kiểm tra tài liệu đúng minor release và khả năng hỗ trợ server |

Bảng trên mô tả định hướng theo thế hệ, không thay thế kiểm tra dependency và tài liệu chính thức. Một ứng dụng có thể dùng Spring Boot phiên bản khác với ví dụ, hoặc override dependency khiến Hibernate Core không còn là phiên bản Boot quản lý.

### 4.1. Ví dụ với Hibernate 5.x

Một số release Hibernate 5 cung cấp dialect riêng cho các thế hệ MySQL. Ví dụ cấu hình có thể là:

~~~properties
spring.jpa.database-platform=org.hibernate.dialect.MySQL8Dialect
~~~

Chỉ dùng tên lớp này nếu artifact Hibernate đang chạy thực sự có lớp đó và server là phiên bản tương thích. Không sao chép cấu hình Hibernate 5 sang ứng dụng đã chuyển sang Hibernate 6.

### 4.2. Ví dụ với Hibernate 6.x hoặc mới hơn

Nếu cần cấu hình tường minh trong Hibernate 6, tên lớp thông dụng là:

~~~properties
spring.jpa.database-platform=org.hibernate.dialect.MySQLDialect
~~~

Hoặc dùng property Hibernate được truyền qua Spring Boot:

~~~properties
spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.MySQLDialect
~~~

Chọn một cách cấu hình duy nhất. Không cần khai báo đồng thời cả hai property cho cùng một dialect nếu không có lý do đặc biệt.

Trong Hibernate 6, không dùng tên lớp MySQL8Dialect theo thói quen từ Hibernate 5. Hãy để Hibernate đọc phiên bản server qua JDBC metadata khi có thể; MySQLDialect hiện hành có thể điều chỉnh khả năng theo thông tin version.

## 5. Cấu hình Spring Boot với MySQL

Một cấu hình datasource cơ bản:

~~~properties
spring.datasource.url=jdbc:mysql://localhost:3306/shop
spring.datasource.username=shop_app
spring.datasource.password=${SHOP_DB_PASSWORD}
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver
~~~

Trong hầu hết trường hợp, Connector/J được phát hiện tự động khi có trên classpath nên không nhất thiết phải khai báo driver class. Tên driver hiện đại là com.mysql.cj.jdbc.Driver.

Nếu Hibernate tự nhận diện được MySQL, có thể không cấu hình dialect:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
~~~

Khi có yêu cầu cố định dialect và đã xác minh Hibernate version:

~~~properties
spring.jpa.database-platform=org.hibernate.dialect.MySQLDialect
~~~

Đừng sao chép property này một cách máy móc vào mọi dự án. Với Hibernate 5, tên lớp có thể khác. Với Hibernate 6/7, ưu tiên lớp dialect hiện hành và kiểm tra đúng dependency.

### 5.1. Không nhầm property Spring Boot và property Hibernate

Hai cách cấu hình thường thấy:

- spring.jpa.database-platform: property do Spring Boot cung cấp để chỉ định database platform/dialect.
- spring.jpa.properties.hibernate.dialect: property được Spring Boot chuyển tiếp tới Hibernate.

Cả hai đều có thể khiến Hibernate dùng dialect được chỉ định. Nếu đặt cả hai với giá trị khác nhau, cấu hình trở nên khó hiểu và có thể phụ thuộc thứ tự áp dụng. Hãy chọn một nơi làm nguồn cấu hình duy nhất.

### 5.2. Cấu hình theo profile

Nếu môi trường development và production dùng cùng loại MySQL nhưng khác phiên bản, không nên tùy tiện cấu hình dialect mới nhất cho profile production. Hãy xác định server version thấp nhất được hỗ trợ trong toàn bộ môi trường và kiểm thử trên phiên bản đó.

Ví dụ:

~~~text
application.properties
    cấu hình datasource chung

application-dev.properties
    URL tới MySQL development

application-test.properties
    URL tới MySQL container test

application-prod.properties
    URL tới MySQL production
~~~

Nếu các môi trường có khác biệt lớn về phiên bản hoặc nhà cung cấp, hãy kiểm tra tính năng SQL thực tế trên từng profile. Cùng một tên dialect không đảm bảo mọi server hỗ trợ cùng một tập tính năng.

## 6. MySQLDialect và khả năng SQL theo phiên bản server

Dialect mô tả các khả năng SQL mà Hibernate có thể sử dụng. MySQL Server version vẫn là giới hạn thực tế.

Một số khác biệt quan trọng giữa các thế hệ MySQL:

| Khả năng | MySQL 5.7 | MySQL 8.0 |
|---|---|---|
| JSON data type | Có | Có, được mở rộng thêm tính năng |
| Common Table Expression (CTE) | Không | Có |
| Window functions | Không | Có |
| Enforced CHECK constraints | CHECK được phân tích nhưng chưa được thực thi như constraint | Được thực thi từ MySQL 8.0.16 |
| Functional index | Không hỗ trợ trực tiếp theo cú pháp MySQL 8.0 | Có từ MySQL 8.0.13 |
| Descending index key parts | Hạn chế hơn | Hỗ trợ trong các bản 8.0 |
| Native sequence object | Không | Không |

Bảng này chỉ nêu các khác biệt tiêu biểu. Mỗi tính năng có thể phụ thuộc minor release, cú pháp và engine. Ví dụ, MySQL 8.0 là một dòng phát hành dài với nhiều tính năng được bổ sung theo từng bản 8.0.x.

### 6.1. CTE và window function

Hibernate có thể sinh hoặc cho phép thực thi truy vấn dùng CTE/window function khi dialect và phiên bản hỗ trợ. MySQL 5.7 không hiểu cú pháp CTE hoặc window function của MySQL 8.0.

Ví dụ CTE:

~~~sql
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS total
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, total
FROM customer_totals
WHERE total > 100000;
~~~

Ví dụ window function:

~~~sql
SELECT order_id,
       customer_id,
       total_amount,
       ROW_NUMBER() OVER (
           PARTITION BY customer_id
           ORDER BY created_at DESC
       ) AS row_num
FROM orders;
~~~

Nếu ứng dụng triển khai trên nhiều server version, chỉ dùng các tính năng ở baseline thấp nhất hoặc phân nhánh truy vấn có kiểm soát.

### 6.2. JSON

MySQL 5.7 đã có kiểu JSON. Tuy nhiên, các hàm JSON và khả năng index JSON được mở rộng qua các phiên bản 8.0. Không nên chỉ kiểm tra việc server nhận kiểu JSON mà kết luận toàn bộ biểu thức JSON của ứng dụng đều tương thích.

Khi dùng @Column(columnDefinition = "json") hoặc native query cho JSON, hãy kiểm tra DDL và truy vấn trên server thực tế. columnDefinition là đoạn SQL phụ thuộc database, không phải một ánh xạ portable giữa các database.

### 6.3. CHECK constraint

Nếu entity có Bean Validation hoặc schema DDL có CHECK constraint, cần phân biệt validation ở Java với enforcement trong database. MySQL trước 8.0.16 không thực thi CHECK constraint như các bản mới. Vì vậy, một constraint xuất hiện trong DDL cũ không chứng minh server đang bảo vệ dữ liệu theo điều kiện đó.

Đối với dữ liệu quan trọng, cần kiểm thử constraint trên phiên bản production và có validation ở tầng ứng dụng phù hợp.

## 7. Dialect ảnh hưởng thế nào đến kiểu dữ liệu và khóa chính?

Hibernate dùng dialect cùng metadata mapping để quyết định SQL type và cú pháp DDL.

Ví dụ entity:

~~~java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal totalAmount;

    @Column(length = 40, nullable = false)
    private String status;
}
~~~

Với MySQL, IDENTITY thường được ánh xạ tới cột AUTO_INCREMENT. Các kiểu Java khác cũng được ánh xạ sang kiểu SQL phù hợp, nhưng kết quả DDL có thể phụ thuộc dialect, Hibernate version, annotation và cấu hình naming strategy.

Những điểm cần kiểm tra:

- Long thường được ánh xạ tới kiểu số nguyên đủ lớn như BIGINT.
- BigDecimal cần precision và scale phù hợp nghiệp vụ.
- String có thể thành VARCHAR hoặc kiểu text tùy length và mapping.
- Boolean có thể được biểu diễn bằng kiểu số hoặc kiểu tương thích tùy dialect và phiên bản.
- LocalDate, LocalDateTime, Instant và Timestamp có ngữ nghĩa thời gian khác nhau; phải kiểm tra timezone và SQL type.
- Enum có thể lưu theo ordinal hoặc string; STRING thường dễ bảo toàn ý nghĩa hơn khi thứ tự enum thay đổi.

### 7.1. IDENTITY và batching

Ví dụ:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Với MySQL, Hibernate thường dùng AUTO_INCREMENT cho identity generation. Vì ID được sinh khi insert, Hibernate có thể phải thực thi insert ngay để lấy khóa mới; điều này ảnh hưởng khả năng gom batch insert so với các chiến lược cấp ID trước khi insert.

Nếu hệ thống ghi số lượng lớn, hãy đo hiệu năng insert và kiểm tra chiến lược sinh khóa trước khi chọn. Không thay GenerationType chỉ dựa trên mong muốn bật batching mà không xem xét tính duy nhất, thứ tự, khả năng phân tán và tương thích database.

### 7.2. MySQL không có native sequence object

MySQL không cung cấp native sequence object như một số hệ quản trị khác. Nếu entity dùng GenerationType.SEQUENCE, không được giả định rằng MySQL sẽ tạo một sequence object tương đương. Hibernate có thể không hỗ trợ chiến lược đó trực tiếp hoặc phải dùng cơ chế khác tùy phiên bản và cấu hình.

Với MySQL, IDENTITY/AUTO_INCREMENT là lựa chọn phổ biến. Nếu cần ID được cấp trước khi insert hoặc cần sequence theo nghiệp vụ, hãy thiết kế cơ chế riêng và kiểm tra SQL thực tế mà Hibernate sinh ra.

## 8. Phân biệt MySQL và MariaDB

MariaDB có nguồn gốc từ MySQL và tương thích giao thức ở mức lớn, nhưng không phải cùng một database engine/version. Hai sản phẩm có lộ trình tính năng, kiểu dữ liệu, optimizer, system variables và SQL behavior khác nhau.

Nếu ứng dụng kết nối tới MariaDB, không nên mặc định dùng MySQLDialect chỉ vì JDBC URL có dạng mysql hoặc driver cho phép kết nối. Hãy xác minh JDBC DatabaseMetaData trả về product name/version và chọn dialect được Hibernate hỗ trợ cho MariaDB.

Với Hibernate 6, lớp dialect riêng thường dùng cho MariaDB là:

~~~properties
spring.jpa.database-platform=org.hibernate.dialect.MariaDBDialect
~~~

Tên lớp và mức hỗ trợ phải kiểm tra theo Hibernate version thực tế. Các dịch vụ MySQL-compatible như Aurora MySQL, TiDB hoặc nền tảng khác cũng cần kiểm tra ma trận tương thích của nhà cung cấp; không phải mọi tính năng MySQL đều được hỗ trợ đầy đủ.

## 9. Dialect không thay thế schema migration

Dialect có thể giúp Hibernate tạo DDL ban đầu hoặc SQL phù hợp khi chạy ứng dụng. Trong hệ thống production, không nên phụ thuộc vào việc Hibernate tự thay đổi schema mỗi lần khởi động.

Các giá trị thường gặp của spring.jpa.hibernate.ddl-auto:

| Giá trị | Hành vi |
|---|---|
| none | Không tự quản lý schema |
| validate | Kiểm tra mapping với schema hiện tại |
| update | Cố gắng điều chỉnh schema theo entity |
| create | Tạo schema mới khi khởi động |
| create-drop | Tạo schema khi khởi động và xóa khi đóng SessionFactory |

Tên và hành vi cụ thể phụ thuộc Hibernate/Spring Boot version. Đối với production, thường chọn validate hoặc none, còn thay đổi schema được quản lý bằng Flyway hoặc Liquibase.

Ví dụ:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
~~~

Dialect không tự chuyển đổi schema cũ sang schema mới. Nếu đổi từ MySQL 5.7 sang 8.0, vẫn cần kiểm tra migration script, reserved words, collation, index, constraint, SQL mode và dữ liệu.

### 9.1. DDL sinh bởi Hibernate và DDL của migration tool

Hai nguồn DDL cần được phân biệt:

- Hibernate có thể sinh DDL từ entity khi cấu hình schema generation.
- Flyway/Liquibase chạy migration script được nhóm phát triển quản lý.

Migration SQL viết tay có thể dùng cú pháp MySQL cụ thể và không phụ thuộc hoàn toàn vào dialect Hibernate. Nhưng ứng dụng vẫn cần dialect phù hợp để tạo truy vấn runtime, ánh xạ kiểu và xử lý pagination/locking.

Không dùng ddl-auto=update như công cụ thay thế migration versioned trong hệ thống có dữ liệu quan trọng.

## 10. Kiểm tra SQL Hibernate sinh ra

Sau khi xác định dialect, kiểm tra SQL runtime và DDL thực tế.

Bật log SQL trong môi trường development:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Tên logger bind parameter thay đổi theo Hibernate version. Log bind có thể chứa dữ liệu nhạy cảm; không bật TRACE rộng rãi trong production hoặc không có chính sách che dữ liệu.

Đối chiếu SQL được sinh với phiên bản MySQL:

- Cú pháp phân trang.
- Cách quoting identifier và tên bảng/cột.
- Kiểu dữ liệu và default value.
- Cú pháp identity/auto increment.
- Locking clause như FOR UPDATE hoặc SKIP LOCKED.
- Cú pháp JSON, CTE và window function nếu được sử dụng.
- Cách tạo index, unique constraint và foreign key.

Nếu dùng native query, Hibernate không chuyển đổi cú pháp SQL của người viết sang database khác. Người phát triển chịu trách nhiệm đảm bảo câu SQL tương thích với MySQL Server thực tế.

## 11. Kiểm tra dialect bằng integration test

Unit test với mock repository không đủ để chứng minh SQL tương thích với MySQL. Nên có integration test chạy trên MySQL thật hoặc container dùng đúng phiên bản cần hỗ trợ.

Một cấu hình Testcontainers minh họa:

~~~java
@Testcontainers
@SpringBootTest
class OrderRepositoryMySqlTest {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.0.36")
            .withDatabaseName("shop")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void configureDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
    }

    @Autowired
    OrderRepository orderRepository;

    @Test
    void shouldFindOrdersForCustomer() {
        // Chuẩn bị dữ liệu và kiểm tra truy vấn repository
    }
}
~~~

Đây là ví dụ cho test environment; cần khai báo dependency Testcontainers tương thích với Java, JUnit, Spring Boot và MySQL image đã chọn.

Một bộ integration test hữu ích nên kiểm tra:

1. ApplicationContext khởi động và Hibernate nhận diện database.
2. Entity mapping khớp schema thực tế.
3. Repository query và JPQL hoạt động.
4. Pagination và sorting sinh SQL đúng.
5. Transaction, pessimistic lock và optimistic lock hoạt động theo mong đợi.
6. Kiểu dữ liệu ngày giờ, decimal, JSON và enum được đọc/ghi đúng.
7. Migration script chạy thành công trên phiên bản đích.
8. Native query không dùng cú pháp chỉ có ở một phiên bản khác.

Nếu production hỗ trợ nhiều phiên bản MySQL, chạy test matrix trên phiên bản thấp nhất và các phiên bản được triển khai. Chỉ test với MySQL mới nhất có thể bỏ sót lỗi tương thích với máy chủ cũ.

## 12. Các lỗi thường gặp khi chọn dialect

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| ClassNotFoundException cho MySQL8Dialect | Dùng tên dialect Hibernate 5 trong Hibernate 6/7 | Dùng MySQLDialect của thế hệ hiện tại hoặc để Hibernate tự nhận diện |
| Server báo syntax error | Dialect hoặc native SQL dùng tính năng server không hỗ trợ | Kiểm tra VERSION(), SQL sinh ra và compatibility matrix |
| Hibernate chọn sai database | JDBC metadata bị proxy/driver báo sai hoặc endpoint khác dự kiến | Kiểm tra DatabaseMetaData và product version từ chính connection |
| DDL tạo kiểu cột không mong muốn | Mapping Java, annotation hoặc dialect không phù hợp | Kiểm tra SHOW CREATE TABLE và mapping của entity |
| CHECK constraint không bảo vệ dữ liệu | MySQL version cũ không enforce CHECK hoặc constraint không được tạo | Kiểm tra server version và thử insert dữ liệu vi phạm |
| Pagination/locking lỗi | Cú pháp hoặc mức hỗ trợ khác nhau theo server version | Xem SQL runtime và chạy integration test trên đúng server |
| Native query chỉ chạy ở development | Development và production dùng phiên bản/nhà cung cấp khác | Đồng bộ phiên bản hoặc giới hạn SQL ở baseline chung |
| Schema validation thất bại | Entity mapping không khớp kiểu/cột/constraint thực tế | Đối chiếu metadata và migration, không sửa bằng ddl-auto update tùy tiện |
| MariaDB lỗi với MySQL-specific SQL | Dùng nhầm dialect hoặc giả định hai sản phẩm giống nhau | Dùng dialect và test matrix đúng sản phẩm |

### 12.1. Lỗi MySQL8Dialect sau nâng cấp Spring Boot

Một lỗi thường gặp là nâng cấp Spring Boot từ thế hệ dùng Hibernate 5 lên thế hệ dùng Hibernate 6 nhưng giữ nguyên:

~~~properties
spring.jpa.database-platform=org.hibernate.dialect.MySQL8Dialect
~~~

Nếu lớp này không còn trong Hibernate version mới, ứng dụng có thể thất bại khi khởi động do không nạp được dialect.

Cách xử lý:

1. Xác định Hibernate Core version thực tế.
2. Kiểm tra tên dialect có trong artifact hay không.
3. Với Hibernate 6/7, dùng MySQLDialect nếu cần chỉ định tường minh.
4. Nếu metadata JDBC chính xác, thử bỏ cấu hình dialect để Hibernate tự nhận diện.
5. Chạy lại integration test và kiểm tra SQL sinh ra.

Không sửa lỗi bằng cách hạ Hibernate hoặc thêm một lớp dialect cũ từ dependency không tương thích.

## 13. Quy trình chọn và xác minh dialect

Thực hiện theo thứ tự:

1. **Xác định server:** chạy VERSION(), version_comment và kiểm tra sản phẩm thực tế là MySQL, MariaDB hay dịch vụ tương thích.
2. **Xác định driver:** kiểm tra Connector/J version và JDBC DatabaseMetaData.
3. **Xác định Hibernate:** xem dependency tree hoặc dependencyInsight để biết chính xác Hibernate Core.
4. **Kiểm tra dialect:** ưu tiên tự nhận diện; nếu cần explicit, chọn lớp tồn tại trong Hibernate version đó.
5. **Kiểm tra baseline:** liệt kê tính năng SQL thấp nhất mà mọi server trong môi trường triển khai hỗ trợ.
6. **Kiểm tra mapping:** xác minh identity, decimal, string, date/time, JSON, enum và các constraint.
7. **Kiểm tra SQL:** bật log ở môi trường test, xem pagination, locking, DDL và native query.
8. **Chạy integration test:** dùng MySQL image hoặc môi trường tương đương production.
9. **Kiểm tra migration:** chạy Flyway/Liquibase trên database sạch và bản nâng cấp từ schema hiện có.
10. **Triển khai có giám sát:** theo dõi lỗi SQL, migration, transaction và hiệu năng sau khi phát hành.

## 14. Checklist trước khi triển khai

- [ ] Đã biết phiên bản Spring Boot và Hibernate Core thực tế.
- [ ] Đã xác định đúng sản phẩm và phiên bản database từ JDBC connection.
- [ ] Đã kiểm tra Connector/J version.
- [ ] Đã xác nhận lớp dialect tồn tại và tương thích với Hibernate version.
- [ ] Đã ưu tiên auto-detection nếu JDBC metadata chính xác.
- [ ] Nếu cấu hình tường minh, chỉ dùng một property làm nguồn cấu hình.
- [ ] Đã kiểm tra MySQL version thấp nhất trong các môi trường triển khai.
- [ ] Đã xác minh các tính năng CTE, window, JSON, CHECK, index và locking được dùng.
- [ ] Đã kiểm tra kiểu dữ liệu và cơ chế sinh primary key.
- [ ] Đã tách schema migration khỏi runtime dialect.
- [ ] Đã dùng validate hoặc none phù hợp trong production thay cho ddl-auto update tùy tiện.
- [ ] Đã chạy integration test trên đúng MySQL version.
- [ ] Đã kiểm tra native query và log SQL trước khi phát hành.
- [ ] Đã có kế hoạch xử lý khi server version khác với môi trường test.

## 15. Tự kiểm tra

1. Dialect của Hibernate quyết định những phần nào trong SQL mà Hibernate sinh ra?
2. Vì sao phải kiểm tra riêng Hibernate version và MySQL Server version?
3. Hibernate lấy thông tin nào từ JDBC metadata để tự nhận diện dialect?
4. Khi nào nên để Hibernate tự nhận diện, và khi nào cần cấu hình tường minh?
5. Vì sao MySQL8Dialect thường gây lỗi khi chuyển từ Hibernate 5 sang Hibernate 6?
6. MySQL 5.7 và MySQL 8.0 khác nhau thế nào về CTE, window function và CHECK constraint?
7. Vì sao GenerationType.IDENTITY ảnh hưởng đến khả năng batch insert?
8. Vì sao không nên dùng MySQLDialect cho MariaDB mà chưa kiểm tra compatibility?
9. Dialect khác gì với Flyway/Liquibase và spring.jpa.hibernate.ddl-auto?
10. Hãy đề xuất test matrix cho ứng dụng Spring Boot cần chạy trên MySQL 8.0 và 8.4, bao gồm mapping, pagination, locking và migration.

Khi cấu hình Spring Boot và JPA, hãy xem dialect là cầu nối giữa mapping Hibernate và SQL mà database thực sự hỗ trợ. Xác định phiên bản server, driver và Hibernate trước; ưu tiên auto-detection khi metadata chính xác; nếu phải cấu hình tường minh, dùng đúng lớp của thế hệ Hibernate đang chạy. Cuối cùng, kiểm chứng bằng integration test trên phiên bản MySQL production để tránh phụ thuộc vào giả định về cú pháp hoặc tính năng.
