# Chọn cơ sở dữ liệu nhúng hay cùng loại với môi trường thật

Khi kiểm thử tầng dữ liệu, lựa chọn database ảnh hưởng trực tiếp đến độ tin cậy của kết quả. Một database nhúng như H2 có thể khởi động nhanh, chạy ngay trong tiến trình test và giúp kiểm tra nhiều thao tác CRUD với chi phí thấp. Tuy nhiên, nếu ứng dụng triển khai trên PostgreSQL, MySQL hoặc một engine cụ thể khác, database nhúng không nhất thiết tái hiện đúng SQL dialect, kiểu dữ liệu, transaction, locking hay constraint của môi trường thật.

Vì vậy, câu hỏi không chỉ là database nào dễ cấu hình hơn. Cần xác định test đang muốn chứng minh điều gì: logic repository cơ bản, khả năng tương thích với database engine, migration, transaction, truy vấn đặc thù hay hành vi đồng thời. Chọn database theo mục tiêu giúp cân bằng tốc độ phản hồi và mức độ tin cậy.

## Hai lựa chọn có đặc điểm gì?

### Database nhúng

Database nhúng chạy bên trong ứng dụng test hoặc được tích hợp trực tiếp vào tiến trình. Một số lựa chọn thường gặp trong hệ sinh thái Java là H2, HSQLDB và Apache Derby. Spring JDBC cung cấp API hỗ trợ tạo embedded database bằng `EmbeddedDatabaseBuilder`.

Một database nhúng có thể chạy trong bộ nhớ hoặc dùng file tùy engine và cấu hình. Trong test, cấu hình in-memory thường được chọn vì tạo môi trường mới nhanh và dễ dọn dẹp.

Đặc điểm thường thấy:

- Khởi động nhanh, không cần quản lý một server database riêng.
- Dễ tạo mới cho từng test suite hoặc ApplicationContext.
- Phù hợp với test cần nhiều vòng lặp nhanh.
- Có thể thực thi SQL thật, kiểm tra mapping và repository cơ bản.
- Hành vi SQL và transaction phụ thuộc engine nhúng, có thể khác database production.

Database nhúng vẫn là database engine thật, có parser SQL, transaction và constraint. Nó không phải mock. Tuy nhiên, nó chỉ chứng minh hành vi trên chính engine đó.

### Database cùng loại với môi trường triển khai

Lựa chọn này nghĩa là test sử dụng cùng engine với môi trường ứng dụng chạy, ví dụ PostgreSQL cho PostgreSQL, MySQL cho MySQL hoặc SQL Server cho SQL Server. Database có thể chạy bằng Testcontainers, service riêng trong CI, database cục bộ hoặc một instance test chuyên dụng.

Đặc điểm thường thấy:

- SQL dialect và nhiều hành vi engine gần với môi trường triển khai.
- Có thể kiểm tra native query, kiểu dữ liệu, constraint, sequence, locking và migration thực tế.
- Phát hiện sớm khác biệt do engine mà database nhúng không thể mô phỏng.
- Khởi động và chuẩn bị môi trường thường tốn thời gian hơn.
- Cần quản lý version, tài nguyên, dữ liệu và khả năng chạy trong CI.

Dùng cùng engine không có nghĩa test phải kết nối vào database production. Nên tạo database hoặc container dùng riêng cho test, với dữ liệu giả lập và quyền truy cập giới hạn.

## So sánh nhanh

| Tiêu chí | Database nhúng | Cùng engine với môi trường thật |
|---|---|---|
| Thời gian khởi động | Thường nhanh | Thường chậm hơn do khởi động server/container |
| Hạ tầng cần có | Thường chỉ cần dependency Java | Cần Docker, service database hoặc môi trường tương đương |
| SQL dialect | Theo engine nhúng | Gần với engine triển khai |
| Kiểu dữ liệu đặc thù | Có thể thiếu hoặc mô phỏng khác | Có thể kiểm tra trực tiếp |
| Native query | Chỉ đáng tin nếu tương thích với engine nhúng | Phù hợp để xác nhận query của engine mục tiêu |
| Transaction và locking | Có thể khác về isolation, lock và concurrency | Gần hơn với hành vi engine thực tế |
| Migration | Kiểm tra được một số migration nếu hỗ trợ dialect | Kiểm tra migration trên đúng engine và version |
| Chạy nhiều test | Dễ tạo database mới, chi phí thấp | Cần tối ưu container, schema và dữ liệu |
| Độ phù hợp cho test nhanh | Cao | Có thể tốn chi phí hơn |
| Độ phù hợp cho kiểm tra tương thích | Có giới hạn | Cao hơn |

Không có lựa chọn nào tự động phù hợp với mọi test. Database nhúng tối ưu vòng phản hồi nhanh; database cùng engine tối ưu độ tin cậy cho những hành vi phụ thuộc engine.

## Những khác biệt giữa database có thể làm test sai lệch

Một repository test chạy xanh trên H2 không chứng minh chắc chắn rằng cùng câu truy vấn sẽ chạy đúng trên PostgreSQL hoặc MySQL. Khác biệt có thể xuất hiện ở nhiều tầng.

### 1. SQL dialect và cú pháp

Các engine có thể khác nhau về:

- Hàm xử lý chuỗi, ngày giờ, JSON và kiểu dữ liệu.
- Cú pháp phân trang như `LIMIT/OFFSET`, `FETCH FIRST` hoặc các biến thể.
- Cú pháp upsert, ví dụ `ON CONFLICT`, `ON DUPLICATE KEY` hoặc `MERGE`.
- Cú pháp lấy generated key và sequence.
- Cú pháp khóa bản ghi như `SELECT ... FOR UPDATE`.
- Cách viết DDL, index có điều kiện và constraint.

Ví dụ, câu truy vấn dùng tính năng riêng của PostgreSQL có thể chạy bình thường trên PostgreSQL nhưng không được H2 hỗ trợ hoặc có ngữ nghĩa khác. Nếu test dùng H2, lỗi tương thích có thể chỉ xuất hiện sau khi triển khai.

### 2. Kiểu dữ liệu và chuyển đổi

Một số kiểu dữ liệu không có ánh xạ giống nhau giữa các engine:

- UUID có thể được lưu dưới dạng kiểu native hoặc chuỗi.
- JSON/JSONB có khả năng truy vấn và index khác nhau.
- Boolean có thể được biểu diễn khác.
- Timestamp có hoặc không có timezone có quy tắc chuyển đổi khác nhau.
- Decimal có thể khác về scale, rounding và overflow.
- Array, enum, binary và large object có thể có hỗ trợ riêng.

Nếu ứng dụng dùng kiểu dữ liệu đặc thù, test trên cùng engine sẽ cho bằng chứng đáng tin hơn về mapping và conversion.

### 3. Collation, chữ hoa/thường và so sánh chuỗi

Tìm kiếm email hoặc username có thể khác nhau tùy collation và cấu hình case sensitivity. Một truy vấn so sánh `'Lan'` với `'lan'` có thể cho kết quả khác giữa hai engine hoặc giữa hai collation.

Các khác biệt khác gồm:

- Sắp xếp dấu tiếng Việt và ký tự Unicode.
- So sánh chuỗi có khoảng trắng cuối.
- So sánh accent-sensitive hay accent-insensitive.
- Unique constraint với chuỗi không phân biệt hoa thường.

Nếu nghiệp vụ dựa vào quy tắc so sánh cụ thể, hãy kiểm tra trên engine và collation mà ứng dụng sẽ dùng.

### 4. Transaction, isolation và locking

Các database có thể khác nhau về isolation mặc định, MVCC, lock granularity, deadlock detection và cách xử lý concurrent update.

Ví dụ, một test kiểm tra hai transaction cùng cập nhật số dư có thể chạy qua trên embedded database nhưng cho kết quả khác trên database production. Một test dùng `SELECT FOR UPDATE` cũng cần engine hỗ trợ đúng ngữ nghĩa khóa.

Khi cần kiểm tra:

- Lost update hoặc optimistic/pessimistic locking.
- Transaction isolation.
- Deadlock và lock timeout.
- Concurrent insert vào unique key.
- Transaction rollback với nhiều thao tác.
- Hành vi commit và visibility giữa các connection.

nên dùng cùng engine và cấu hình gần với môi trường triển khai. Test concurrency cần quản lý nhiều connection/transaction thực sự; chỉ chạy một test method trong một transaction không chứng minh được hành vi cạnh tranh.

### 5. Constraint, generated key và sequence

Các engine có quy tắc riêng về identity, auto increment, sequence, default value và constraint. Ví dụ, sequence có thể tăng dù transaction rollback; cách lấy generated key có thể khác; một số constraint được kiểm tra ngay khi statement chạy, một số có thể được trì hoãn tới cuối transaction nếu engine hỗ trợ.

Nếu ứng dụng phụ thuộc vào những hành vi đó, test trên database cùng engine là cần thiết.

### 6. DDL và migration

Một migration có thể chạy được trên H2 nhưng thất bại trên PostgreSQL do khác cú pháp, thứ tự khóa hoặc khả năng hỗ trợ DDL. Một số database có implicit commit đối với DDL; hành vi rollback schema change không giống nhau.

Test migration cần tạo database sạch, chạy chính chuỗi migration ứng dụng sử dụng và xác nhận trạng thái schema sau migration. Nếu ứng dụng triển khai trên một engine cụ thể, hãy chạy migration trên engine đó.

## Khi nào database nhúng là lựa chọn hợp lý?

Database nhúng phù hợp khi test cần kiểm tra logic tầng dữ liệu có tính portable và không phụ thuộc vào tính năng đặc thù của production engine.

Các trường hợp thường gặp:

- Repository thực hiện CRUD cơ bản qua Spring JDBC.
- Truy vấn SQL chuẩn, không dùng native feature của một engine cụ thể.
- Mapping entity đơn giản mà không phụ thuộc dialect đặc thù.
- Kiểm tra service phối hợp với repository trong một context nhỏ.
- Nhiều test cần khởi tạo database nhanh để có phản hồi thường xuyên.
- Kiểm tra dữ liệu fixture, constraint cơ bản và truy vấn đơn giản.

Ví dụ, một repository tìm customer theo email bằng truy vấn SQL đơn giản có thể được kiểm tra trên H2 nếu schema và câu SQL tương thích:

~~~java
@Repository
class CustomerJdbcRepository {

    private final JdbcTemplate jdbcTemplate;

    CustomerJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    Optional<String> findNameByEmail(String email) {
        return jdbcTemplate.query(
            "select name from customer where email = ?",
            rs -> rs.next()
                ? Optional.of(rs.getString("name"))
                : Optional.empty(),
            email
        );
    }
}
~~~

Nếu test chỉ cần chứng minh repository ánh xạ đúng kết quả của truy vấn portable, H2 có thể là lựa chọn nhanh. Tuy nhiên, nếu ứng dụng chạy trên PostgreSQL và truy vấn dùng JSONB, array, operator hoặc collation riêng, H2 không đủ để chứng minh tương thích.

## Tạo database nhúng với Spring JDBC

Spring JDBC cung cấp `EmbeddedDatabaseBuilder` để tạo embedded database từ cấu hình Java và chạy script schema/fixture.

Dependency H2 cần được khai báo trong test runtime, ví dụ với Gradle:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-jdbc")
    testRuntimeOnly("com.h2database:h2")
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
~~~

Ví dụ cấu hình:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;

@Configuration
class EmbeddedDatabaseTestConfig {

    @Bean(destroyMethod = "shutdown")
    EmbeddedDatabase dataSource() {
        return new EmbeddedDatabaseBuilder()
            .setType(EmbeddedDatabaseType.H2)
            .addScript("classpath:db/schema.sql")
            .addScript("classpath:db/reference-data.sql")
            .build();
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
~~~

`EmbeddedDatabaseBuilder` tạo database H2 và chạy các script theo thứ tự khai báo. Bean có destroy method `shutdown` để đóng database khi context bị đóng.

Test dùng cấu hình này qua Spring TestContext Framework:

~~~java
@SpringJUnitConfig(EmbeddedDatabaseTestConfig.class)
class CustomerJdbcRepositoryTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    CustomerJdbcRepository repository;

    @Test
    void findsCustomerByEmail() {
        jdbcTemplate.update(
            "insert into customer(id, email, name) values (?, ?, ?)",
            1001L,
            "lan@example.test",
            "Lan"
        );

        assertThat(repository.findNameByEmail("lan@example.test"))
            .contains("Lan");
    }
}
~~~

Ví dụ giả định cấu hình test cũng đăng ký bean `CustomerJdbcRepository`, schema có các cột tương ứng và class test có import assertion phù hợp. Mục đích là minh họa cách Spring tạo database nhúng, inject DataSource/JdbcTemplate và cho repository chạy trên database thật trong tiến trình test.

Có thể dùng `EmbeddedDatabaseType.HSQL` hoặc `EmbeddedDatabaseType.DERBY` nếu dependency tương ứng có mặt. Cấu hình cụ thể phụ thuộc engine và phiên bản thư viện.

### Ưu điểm và giới hạn của embedded database trong Spring

Ưu điểm:

- Không cần quản lý server database ngoài tiến trình.
- Dễ tạo database mới cho từng ApplicationContext.
- Script schema và dữ liệu có thể đặt trong test resources.
- Phù hợp cho test chạy thường xuyên trong IDE và build local.
- Có thể kết hợp transaction test-managed của Spring.

Giới hạn:

- SQL chạy trên H2 không nhất thiết tương thích với engine triển khai.
- Cấu hình embedded không chứng minh network, authentication hoặc connection pool production.
- Một số kiểu dữ liệu, index, function và locking có ngữ nghĩa khác.
- Test có thể vô tình dựa vào hành vi dễ dãi hơn của embedded engine.
- Test migration chỉ đáng tin khi migration thực sự tương thích với engine nhúng; điều đó không chứng minh migration production hoạt động.

Không nên dùng chế độ tương thích của H2 như bằng chứng rằng H2 đã trở thành PostgreSQL hoặc MySQL. Compatibility mode có thể hỗ trợ một số cú pháp, nhưng không thay thế toàn bộ hành vi của engine đích.

## Khi nào cần cùng engine với môi trường triển khai?

Dùng cùng engine khi kết quả test phụ thuộc vào tính năng hoặc ngữ nghĩa riêng của database production.

Ví dụ:

- Repository sử dụng native SQL hoặc function riêng.
- Ứng dụng dùng JSONB, array, enum, full-text search hoặc extension của database.
- Migration tạo index, trigger, sequence, stored procedure hoặc constraint đặc thù.
- Hành vi locking, transaction isolation hoặc concurrent update là một phần yêu cầu.
- Ứng dụng phụ thuộc collation, timezone, generated column hoặc kiểu dữ liệu riêng.
- Cần xác nhận truy vấn phức tạp và kế hoạch thực thi trên engine thực tế.
- Cần kiểm tra tương thích phiên bản database đang triển khai.

Cùng engine cũng hữu ích khi nhóm phát triển đã từng gặp lỗi chỉ xuất hiện trên production do khác biệt database. Khi đó, test trên đúng engine giúp tái hiện hành vi gần hơn và giảm khoảng cách giữa local, CI và deployment.

## Dùng Testcontainers để chạy database cùng loại

Testcontainers khởi chạy dịch vụ database trong container dành cho test. Với PostgreSQL, có thể dùng module PostgreSQL và tích hợp JUnit Jupiter.

Ví dụ dependency Gradle:

~~~groovy
dependencies {
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testRuntimeOnly("org.postgresql:postgresql")
}
~~~

Ví dụ test dùng PostgreSQL container:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringJUnitConfig(PostgresTestConfig.class)
class CustomerRepositoryPostgresIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void registerDatabaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add("test.datasource.url", postgres::getJdbcUrl);
        registry.add("test.datasource.username", postgres::getUsername);
        registry.add("test.datasource.password", postgres::getPassword);
    }

    @Test
    void runsAgainstPostgres() {
        // Thực hiện truy vấn trên PostgreSQL đang chạy trong container.
    }
}
~~~

`@Container` và `@Testcontainers` thuộc tích hợp JUnit của Testcontainers. `@DynamicPropertySource` thuộc Spring Test và đăng ký JDBC URL, username, password được container cấp phát vào Environment.

Cấu hình Spring có thể tạo DataSource từ các property này:

~~~java
@Configuration
class PostgresTestConfig {

    @Bean
    DataSource dataSource(Environment environment) {
        DriverManagerDataSource dataSource =
            new DriverManagerDataSource();

        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl(
            environment.getRequiredProperty("test.datasource.url")
        );
        dataSource.setUsername(
            environment.getRequiredProperty("test.datasource.username")
        );
        dataSource.setPassword(
            environment.getRequiredProperty("test.datasource.password")
        );

        return dataSource;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
~~~

Trong dự án thực tế, cấu hình có thể dùng connection pool và migration tool giống ứng dụng. Ví dụ dùng `DriverManagerDataSource` ở đây để làm rõ cách lấy property và kết nối tới container; nó không phải connection pool dành cho production.

### Chọn version container phù hợp

Không nên luôn dùng tag `latest`. Hãy ghim major/minor version tương ứng với môi trường cần kiểm tra, ví dụ cùng major version PostgreSQL hoặc MySQL đang triển khai. Nếu production dùng extension hoặc cấu hình riêng, test container cần cài và bật những thành phần đó.

Cùng tên engine nhưng khác version vẫn có thể có khác biệt về:

- SQL syntax và feature được hỗ trợ.
- Query planner và execution plan.
- Default collation hoặc timezone.
- Driver behavior và protocol.
- Migration compatibility.
- Locking, optimizer và hiệu năng.

Nếu hệ thống chạy trên managed database có extension hoặc cấu hình riêng, container chuẩn có thể chưa tái hiện đầy đủ. Khi đó cần bổ sung extension/configuration tương ứng hoặc có một nhóm test môi trường chuyên biệt.

## Chú ý vòng đời container và Spring context cache

Spring TestContext Framework có thể cache ApplicationContext giữa các test class có cấu hình tương đương. Testcontainers JUnit extension thường quản lý static container theo vòng đời test class. Nếu context giữ DataSource trỏ tới container đã dừng, một test class sau có thể vô tình dùng context cũ.

Có hai hướng tổ chức phổ biến:

1. **Chia sẻ container có vòng đời dài:** dùng singleton container cho nhóm test và giữ endpoint ổn định trong suốt thời gian ApplicationContext được tái sử dụng.
2. **Context riêng theo vòng đời resource:** khi mỗi class có container riêng, bảo đảm context tương ứng được đóng/loại khỏi cache trước khi container dừng, chẳng hạn dùng `@DirtiesContext(classMode = AFTER_CLASS)` khi phù hợp.

Không nên kết hợp tùy tiện container dừng sau mỗi class với context được cache lâu hơn container. Endpoint động có thể được đăng ký bằng supplier, nhưng bean như DataSource thường giữ URL đã đọc khi khởi tạo; supplier đổi giá trị không tự động tái tạo connection pool.

Nếu test chạy song song, cần bảo đảm class này không đóng container hoặc context mà class khác đang sử dụng. Có thể dùng tài nguyên singleton chung với dữ liệu/schema riêng, hoặc cấp container và context độc lập cho từng nhóm test.

## Migration phải chạy trên database mà ứng dụng dùng

Một trong những lý do mạnh nhất để chọn cùng engine là kiểm tra migration. Nếu ứng dụng sử dụng Flyway hoặc Liquibase, hãy chạy đúng migration scripts trên database test sạch.

Quy trình tổng quát:

1. Khởi động database đúng engine và version mục tiêu.
2. Tạo database/schema rỗng dành riêng cho test.
3. Chạy toàn bộ migration theo thứ tự mà ứng dụng sử dụng.
4. Xác nhận migration hoàn tất.
5. Chạy repository và integration test trên schema đã được migration tạo ra.
6. Đóng database/container hoặc xóa schema khi suite kết thúc.

Không nên tạo một schema H2 thủ công rồi dùng kết quả đó để kết luận migration PostgreSQL đã đúng. Test nhanh có thể dùng schema rút gọn; test migration cần chạy migration thật trên engine mục tiêu.

Nếu migration cần nâng cấp từ phiên bản cũ, hãy tạo database ở trạng thái cũ, nạp dữ liệu đại diện, chạy migration và xác nhận dữ liệu được chuyển đổi đúng. Điều này kiểm tra cả DDL lẫn khả năng bảo toàn dữ liệu.

## Kết hợp hai loại database trong chiến lược kiểm thử

Không nhất thiết mọi test đều phải chạy trên cùng engine production. Một chiến lược thực tế có thể chia theo phạm vi:

| Nhóm test | Database phù hợp | Điều được kiểm chứng |
|---|---|---|
| Unit test logic không cần database | Không cần database hoặc dùng mock | Quy tắc nghiệp vụ và cách gọi dependency |
| Test repository với SQL portable | Embedded database | Mapping, CRUD và truy vấn cơ bản |
| Test service cần persistence context đơn giản | Embedded hoặc engine thật tùy hành vi | Phối hợp service/repository và transaction cơ bản |
| Native query và kiểu dữ liệu đặc thù | Cùng engine production | Tương thích SQL và mapping theo engine |
| Migration và constraint quan trọng | Cùng engine production | DDL, schema version, constraint và dữ liệu |
| Locking, isolation, concurrency | Cùng engine production | Hành vi transaction và đồng thời |
| Hiệu năng truy vấn | Engine/version và dữ liệu gần thực tế | Query plan, index và thời gian thực thi |

Cách kết hợp này giúp phần lớn test đơn giản chạy nhanh, trong khi các hành vi nhạy cảm với engine vẫn được kiểm chứng trên database phù hợp.

Tuy nhiên, nếu ứng dụng phụ thuộc sâu vào một engine cụ thể, có thể chọn cùng engine cho phần lớn repository integration test để giảm rủi ro khác biệt. Chiến lược nên dựa trên những feature database mà code thực sự sử dụng, không phải một quy tắc cố định cho mọi dự án.

## Những điều cần giữ giống môi trường thật

Khi mục tiêu là kiểm tra database compatibility, chỉ chọn cùng engine vẫn chưa đủ. Hãy xem xét cả các yếu tố sau:

- **Version:** dùng version tương ứng với môi trường triển khai.
- **Driver:** dùng JDBC driver phù hợp và version tương thích.
- **Extension/plugin:** bật extension mà ứng dụng sử dụng.
- **Collation và encoding:** cấu hình gần với production nếu truy vấn phụ thuộc so sánh chuỗi.
- **Timezone:** thống nhất timezone database và ứng dụng.
- **Schema:** chạy migration thực tế thay vì tạo schema giản lược.
- **Isolation:** cấu hình transaction isolation phù hợp với yêu cầu.
- **User và permission:** kiểm tra quyền cần thiết nếu ứng dụng phụ thuộc role hoặc grant.
- **Connection settings:** xem xét pool, autocommit và timeout khi chúng ảnh hưởng hành vi.
- **Dữ liệu:** dùng kích thước và phân bố dữ liệu đủ đại diện cho test đang thực hiện.

Không cần sao chép mọi cấu hình production vào mọi test. Chỉ mô phỏng những điều kiện liên quan trực tiếp đến hành vi cần kiểm chứng. Không sử dụng dữ liệu khách hàng hoặc credential production trong môi trường test.

## Hiệu năng và độ ổn định của test suite

Database cùng engine có chi phí khởi động, pull image, chạy migration và cleanup. Có thể giảm chi phí bằng cách:

- Chia sẻ một container cho một test suite khi endpoint và context có vòng đời ổn định.
- Chạy migration một lần cho schema dùng chung nếu test không sửa schema.
- Dùng schema hoặc namespace riêng cho từng test class/worker khi chạy song song.
- Tạo fixture tối thiểu theo từng test method.
- Tránh khởi động container mới cho mọi test method nếu không cần.
- Đóng connection, executor và tài nguyên phụ trợ đúng vòng đời.

Database nhúng cũng có thể tạo test không ổn định nếu test dùng chung một database in-memory, phụ thuộc thứ tự chạy hoặc không dọn dữ liệu. Tốc độ nhanh không tự động tạo ra tính cô lập.

Với cả hai lựa chọn, test cần:

- Có thể chạy riêng mà không phụ thuộc dữ liệu của test trước.
- Dùng business key hoặc namespace để tránh va chạm.
- Quản lý transaction và cleanup đúng phạm vi.
- Không dựa vào ID tự tăng hoặc thời gian hiện tại nếu không cần.
- Không chạy destructive cleanup trên database được chia sẻ với test khác.

## Những nhầm lẫn thường gặp

**Cho rằng H2 là mock database.** H2 là một database engine thật. Nó thực thi SQL và transaction, nhưng hành vi của nó không đồng nhất với PostgreSQL, MySQL hoặc engine khác.

**Cho rằng H2 compatibility mode tương đương engine production.** Chế độ tương thích chỉ hỗ trợ một phần cú pháp hoặc hành vi. Nó không tái hiện toàn bộ dialect, locking, optimizer và extension.

**Cho rằng test xanh trên embedded database chứng minh production database chạy đúng.** Test chỉ chứng minh hành vi trên engine được dùng trong test. Những tính năng đặc thù cần được kiểm tra trên engine mục tiêu.

**Cho rằng mọi test đều cần database production-like.** Unit test không cần database nếu logic có thể kiểm tra độc lập. Nhiều repository test portable có thể chạy nhanh trên embedded database.

**Kết nối thẳng vào database production để kiểm thử.** Test cần database riêng, dữ liệu giả lập và quyền truy cập được giới hạn. Không chạy fixture hoặc cleanup lên dữ liệu production.

**Dùng database cùng engine nhưng version khác xa production.** Feature, optimizer, collation hoặc migration có thể khác. Ghim version test phù hợp với version mục tiêu.

**Dùng Testcontainers nhưng bỏ qua vòng đời Spring context.** Container dừng trong khi context vẫn cache có thể khiến DataSource giữ endpoint cũ. Phải thiết kế vòng đời tài nguyên và context đồng bộ.

**Tự viết schema khác migration production rồi coi là integration test đầy đủ.** Schema thủ công có thể bỏ sót constraint hoặc kiểu dữ liệu. Test migration cần chạy chuỗi migration thật.

**Dùng một database dùng chung cho nhiều test song song mà không namespace dữ liệu.** Test có thể đọc, ghi hoặc xóa dữ liệu của nhau. Hãy cô lập database/schema hoặc business key.

## Quy trình chọn database cho một test

Trước khi chọn embedded database hay cùng engine với môi trường thật, hãy xác định:

1. Test đang kiểm tra logic nghiệp vụ, repository CRUD, native SQL, migration, transaction hay concurrency?
2. Truy vấn có dùng cú pháp hoặc kiểu dữ liệu riêng của database production không?
3. Test có phụ thuộc collation, timezone, sequence, locking hoặc constraint cụ thể không?
4. Mục tiêu là phản hồi nhanh hay xác nhận tính tương thích với engine?
5. Có thể dùng database nhúng mà vẫn giữ được các đặc tính cần kiểm tra không?
6. Nếu dùng Testcontainers, container có đúng engine/version và extension cần thiết không?
7. Schema có được tạo từ migration thực tế không?
8. Database, ApplicationContext và fixture có vòng đời tương thích không?
9. Test có thể chạy độc lập, lặp lại và song song mà không chia sẻ dữ liệu ngoài ý muốn không?

Nếu test chỉ cần SQL portable và mapping cơ bản, embedded database thường đủ và giúp suite chạy nhanh. Nếu test phụ thuộc native feature, migration, locking, isolation hoặc kiểu dữ liệu đặc thù, hãy dùng cùng engine với môi trường triển khai. Kết hợp hai lựa chọn theo mục tiêu giúp test tầng dữ liệu vừa có phản hồi nhanh vừa phát hiện được những khác biệt database có thể gây lỗi khi ứng dụng chạy thật.
