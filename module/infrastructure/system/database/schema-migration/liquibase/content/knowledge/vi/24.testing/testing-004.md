# Kiểm thử bằng Testcontainers với hệ quản trị thực tế

Migration Liquibase có thể chạy đúng trên H2 hoặc database giả lập nhưng thất bại trên hệ quản trị production. Sự khác biệt về kiểu dữ liệu, cú pháp DDL, transaction, index, constraint, sequence, locking và catalog metadata có thể chỉ xuất hiện khi chạy trên đúng DBMS. Vì vậy, kiểm thử migration cần có một lớp tích hợp sử dụng **database thật trong container**, được tạo và hủy tự động theo vòng đời test.

**Testcontainers** cho phép test Java khởi chạy PostgreSQL, MySQL, MariaDB và nhiều dịch vụ khác bằng container, kết nối ứng dụng hoặc Liquibase vào endpoint do container cung cấp, rồi kiểm tra schema, dữ liệu và lịch sử migration. Cách này giúp kiểm chứng những hành vi mà mock hoặc H2 không thể đại diện đầy đủ.

Bài thuộc chương **Kiểm thử** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào kiểm thử Liquibase bằng Testcontainers với DBMS thực tế, từ cấu hình container, tích hợp Spring Boot, xác minh fresh install và upgrade đến kiểm tra lỗi, rollback, khóa và cô lập dữ liệu giữa các test.

## 1. Vì sao cần DBMS thực tế trong kiểm thử migration?

H2 hữu ích cho kiểm thử nhanh hoặc logic ứng dụng đơn giản, nhưng không thể đảm bảo hành vi giống PostgreSQL, MySQL, Oracle hay SQL Server. Ví dụ:

- Kiểu dữ liệu, độ chính xác số, timestamp và Boolean có khác biệt.
- Cú pháp ALTER TABLE, identity/sequence, index và constraint không giống nhau.
- Một số DBMS hỗ trợ transactional DDL, một số thao tác DDL có thể commit riêng.
- CREATE INDEX CONCURRENTLY của PostgreSQL có hạn chế transaction riêng.
- Quy tắc đặt tên identifier, schema, catalog và chữ hoa/thường khác nhau.
- Cách xử lý lock, deadlock, timeout và isolation level khác nhau.
- JDBC driver trả metadata và kiểu dữ liệu có thể khác.
- SQL function, trigger, procedure và delimiter phụ thuộc DBMS.

Một migration dùng được trên H2 chưa chắc chạy được trên PostgreSQL. Ngược lại, một câu SQL hợp lệ trên PostgreSQL có thể không có cú pháp tương đương trên MySQL.

| Cách kiểm thử | Điều có thể xác minh tốt | Giới hạn |
|---|---|---|
| Unit test với mock | Logic chọn cấu hình, xử lý kết quả, mapping | Không thực thi DDL/DML thật |
| H2 in-memory | Một số thao tác schema và repository nhanh | Không đại diện đầy đủ DBMS production |
| Testcontainers với DBMS thực tế | SQL, kiểu dữ liệu, constraint, index, JDBC, Liquibase runtime | Cần Docker/container runtime và thời gian khởi động |
| Kiểm thử trên staging | Tích hợp gần môi trường triển khai | Tốn tài nguyên, dữ liệu và thời gian; phản hồi chậm hơn |

Không nhất thiết bỏ H2 khỏi mọi test. Hãy dùng từng lớp đúng mục tiêu, nhưng các changeset quan trọng phải được kiểm chứng trên DBMS thực tế mà hệ thống sẽ triển khai.

## 2. Testcontainers hoạt động như thế nào?

Testcontainers cung cấp API Java để tạo và điều khiển container phục vụ test. Với một test PostgreSQL:

1. JUnit khởi chạy container PostgreSQL từ image đã chọn.
2. Container tạo database và user dùng riêng cho test.
3. Testcontainers cung cấp JDBC URL, username và password.
4. Spring Boot cấu hình DataSource từ thông tin đó.
5. Liquibase chạy changelog trong quá trình khởi tạo Spring context.
6. Test truy vấn database để xác minh schema, dữ liệu và DATABASECHANGELOG.
7. Sau test suite, container được dừng và loại bỏ theo lifecycle đã cấu hình.

~~~mermaid
flowchart TD
    A["JUnit bắt đầu integration test"] --> B["Testcontainers khởi chạy DBMS"]
    B --> C["Cấp JDBC URL và credentials"]
    C --> D["Spring Boot tạo DataSource"]
    D --> E["Liquibase chạy changelog"]
    E --> F["Test kiểm tra schema, data, history"]
    F --> G["JUnit kết thúc"]
    G --> H["Container được dọn theo lifecycle"]
~~~

Điểm quan trọng là ứng dụng và Liquibase kết nối tới **database trong container**, không phải database local hoặc H2 được cấu hình mặc định ở profile khác.

## 3. Chuẩn bị dependency cho test

Với dự án Maven dùng JUnit 5, các dependency thường gồm:

- Spring Boot test starter.
- Testcontainers JUnit Jupiter integration.
- Module Testcontainers tương ứng DBMS, ví dụ PostgreSQL.
- JDBC driver tương ứng DBMS trong runtime/test classpath.
- Liquibase core đã được ứng dụng sử dụng.

Ví dụ dependency Testcontainers:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>TESTCONTAINERS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Giá trị TESTCONTAINERS_VERSION là placeholder; thay bằng một phiên bản Testcontainers cụ thể đã được pin, tương thích với Java, JUnit và Spring Boot của dự án. Nên quản lý các module bằng Testcontainers BOM để tránh lệch phiên bản giữa junit-jupiter và postgres.

Nếu dự án đã có Spring Boot dependency management, không tự thêm version riêng cho từng module khi BOM đã quản lý. JDBC driver phải có mặt ở runtime classpath của ứng dụng hoặc test theo cách DataSource được cấu hình.

## 4. Chọn image DBMS tương ứng production

Ví dụ dùng PostgreSQL:

~~~java
@Testcontainers
class LiquibasePostgresIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("liquibase_test")
            .withUsername("test_user")
            .withPassword("test_password");
}
~~~

Image trong ví dụ chỉ là một phiên bản mẫu. Dự án nên chọn đúng major/minor hoặc image digest đã được phê duyệt, tương ứng với môi trường production và chính sách cập nhật bảo mật.

Không nên dùng tag latest cho test migration quan trọng, vì image có thể thay đổi theo thời gian và khiến cùng một commit cho kết quả khác nhau. Ghi nhận phiên bản DBMS và Testcontainers trong cấu hình test để có thể tái tạo lỗi.

### 4.1. Dùng đúng DBMS, không chỉ cùng họ SQL

Nếu production chạy PostgreSQL, ưu tiên PostgreSQL container. Nếu production chạy MySQL, dùng MySQL container; nếu dùng MariaDB, kiểm tra MariaDB thay vì giả định MySQL tương đương hoàn toàn.

Khi hỗ trợ nhiều DBMS, mỗi DBMS cần bộ test riêng hoặc một test matrix. Một test PostgreSQL thành công không chứng minh changeset SQL dành cho Oracle hoặc SQL Server cũng đúng.

### 4.2. Khởi động container cần Docker hoặc runtime tương thích

Máy phát triển và CI phải có Docker Engine hoặc một container runtime được Testcontainers hỗ trợ và cấu hình đúng. Nếu không thể truy cập daemon, test sẽ lỗi trước khi Liquibase chạy.

Không nên cấu hình bỏ qua test một cách âm thầm trên CI bắt buộc kiểm thử migration. Nếu local không có Docker, có thể cho phép developer chạy nhóm test khác, nhưng pipeline kiểm soát phát hành phải có job chạy integration test DBMS thực tế.

## 5. Kết nối Spring Boot tới PostgreSQL container

Một cách phổ biến là dùng JUnit 5 extension của Testcontainers và Spring DynamicPropertySource để truyền JDBC URL vào Spring Boot:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class LiquibasePostgresIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void configureDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.liquibase.enabled", () -> true);
        registry.add(
            "spring.liquibase.change-log",
            () -> "classpath:/db/changelog/db.changelog-master.yaml"
        );
    }

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void migrationCreatesCustomerTable() {
        Boolean exists = jdbcTemplate.queryForObject(
            "SELECT to_regclass('public.customer') IS NOT NULL",
            Boolean.class
        );

        assertThat(exists).isTrue();
    }
}
~~~

Trong ví dụ:

- Container được khai báo static nên tồn tại trong phạm vi class test.
- @DynamicPropertySource đăng ký thuộc tính datasource sau khi Testcontainers cung cấp endpoint.
- Liquibase dùng cùng DataSource với ứng dụng nếu không cấu hình datasource riêng cho Liquibase.
- Spring Boot khởi tạo Liquibase trước khi test method chạy, theo lifecycle auto-configuration.
- JdbcTemplate truy vấn chính database mà migration vừa cập nhật.

Cần bảo đảm test class nằm trong phạm vi component scan của ứng dụng hoặc chỉ định cấu hình Spring Boot phù hợp. Changelog phải thực sự có trong classpath test.

### 5.1. Spring Boot 3.1+ và @ServiceConnection

Spring Boot 3.1 trở lên có thể tích hợp Testcontainers bằng @ServiceConnection nếu dự án thêm dependency spring-boot-testcontainers phù hợp. Ví dụ:

~~~java
@Container
@ServiceConnection
static final PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16.4-alpine");
~~~

Cách này cho Spring Boot tự tạo connection details từ container. Khi dùng @ServiceConnection, không cần lặp lại các thuộc tính datasource tương ứng bằng DynamicPropertySource trong cùng một cấu hình nếu service connection đã cung cấp đầy đủ.

Chọn một cách kết nối rõ ràng và nhất quán. Không để dynamic properties và service connection cùng cấu hình một thuộc tính theo cách khó xác định giá trị cuối cùng.

## 6. Kiểm thử fresh install: database hoàn toàn mới

Fresh install kiểm tra đường đi từ database trống tới schema/data mà release yêu cầu.

Một bài test nên xác minh nhiều hơn việc Spring context khởi động thành công:

- Bảng bắt buộc đã tồn tại.
- Cột có đúng kiểu, nullability và default.
- Primary key, foreign key, unique/check constraint đúng.
- Index có định nghĩa và trạng thái hợp lệ.
- View/sequence/function cần thiết tồn tại.
- Dữ liệu tham chiếu được nạp đúng.
- DATABASECHANGELOG ghi nhận changeset dự kiến.
- DATABASECHANGELOGLOCK được giải phóng sau migration.

Ví dụ assertion:

~~~java
@Test
void migrationCreatesExpectedSchemaAndHistory() {
    Boolean tableExists = jdbcTemplate.queryForObject(
        "SELECT to_regclass('public.customer') IS NOT NULL",
        Boolean.class
    );
    assertThat(tableExists).isTrue();

    Integer columnCount = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM information_schema.columns " +
        "WHERE table_schema = 'public' " +
        "AND table_name = 'customer' " +
        "AND column_name = 'email'",
        Integer.class
    );
    assertThat(columnCount).isEqualTo(1);

    Integer changesetCount = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM databasechangelog " +
        "WHERE id = ? AND author = ?",
        Integer.class,
        "001-create-customer",
        "database-team"
    );
    assertThat(changesetCount).isEqualTo(1);
}
~~~

Các tên bảng, cột, changeset và schema trong ví dụ phải được thay bằng tên thực tế của dự án. Trên PostgreSQL, tên không quote thường được chuẩn hóa chữ thường; nếu dự án dùng quoted identifiers hoặc schema khác, điều chỉnh truy vấn cho phù hợp.

## 7. Kiểm tra kiểu dữ liệu, constraint và index

Testcontainers hữu ích vì test có thể truy vấn catalog thật của DBMS thay vì chỉ kiểm tra entity mapping.

Ví dụ PostgreSQL kiểm tra cột:

~~~sql
SELECT column_name, data_type, is_nullable,
       column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customer'
ORDER BY ordinal_position;
~~~

Kiểm tra constraint:

~~~sql
SELECT conname, contype
FROM pg_constraint
WHERE conrelid = 'public.customer'::regclass
ORDER BY conname;
~~~

Kiểm tra index:

~~~sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'customer'
ORDER BY indexname;
~~~

Với unique index, không chỉ kiểm tra tên index; cần xác minh cột, thứ tự, predicate và unique flag. Với foreign key, kiểm tra cả bảng/cột tham chiếu và hành vi ON DELETE/ON UPDATE nếu nghiệp vụ phụ thuộc.

Không nên so sánh toàn bộ catalog một cách mù quáng nếu DBMS tự sinh tên constraint hoặc metadata khác nhau giữa phiên bản. Hãy assertion những thuộc tính có ý nghĩa đối với ứng dụng.

## 8. Kiểm thử data migration và dữ liệu seed

Migration không chỉ tạo schema. Changeset có thể loadData, loadUpdateData hoặc thực thi SQL để backfill dữ liệu.

Ví dụ kiểm tra dữ liệu tham chiếu sau khi Liquibase chạy:

~~~java
@Test
void seedDataIsLoaded() {
    Integer count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM country WHERE code IN ('VN', 'JP', 'US')",
        Integer.class
    );

    assertThat(count).isEqualTo(3);

    String name = jdbcTemplate.queryForObject(
        "SELECT name FROM country WHERE code = 'VN'",
        String.class
    );

    assertThat(name).isEqualTo("Viet Nam");
}
~~~

Đối với data migration, nên kiểm tra:

- Số dòng trước và sau theo điều kiện nghiệp vụ.
- Khóa chính/unique không bị trùng.
- Foreign key không có bản ghi mồ côi.
- Giá trị chuyển đổi đúng, bao gồm NULL, chuỗi rỗng và timezone.
- Dữ liệu cũ không bị mất ngoài chủ đích.
- Chạy lại update thông thường không tạo dữ liệu trùng.
- Dữ liệu mới đáp ứng invariant mà ứng dụng phụ thuộc.

Một test chỉ xác nhận count bằng 3 chưa đủ nếu ba dòng đó có thể là ba mã sai. Assertion cần kiểm tra cả khóa và giá trị quan trọng.

## 9. Kiểm thử upgrade từ phiên bản trước

Fresh install và upgrade là hai đường đi khác nhau. Một database production thường đã có lịch sử changeset và dữ liệu lâu năm; test chỉ từ database trống có thể bỏ sót lỗi với dữ liệu cũ.

Một upgrade test đáng tin cậy nên:

1. Khởi chạy DBMS container sạch.
2. Áp dụng changelog của release trước hoặc khôi phục fixture được tạo từ database release trước.
3. Nạp dữ liệu đại diện, gồm cả trường hợp biên và dữ liệu legacy.
4. Chạy changelog của release hiện tại trên cùng database.
5. Xác minh các changeset mới được áp dụng đúng.
6. Xác minh dữ liệu cũ được giữ hoặc chuyển đổi theo yêu cầu.
7. Kiểm tra constraint/index mới không thất bại vì dữ liệu cũ.
8. Đối chiếu DATABASECHANGELOG để chắc chắn lịch sử không bị chạy lại hoặc mất dấu.

Điểm quan trọng: khi chạy release trước rồi release mới, **identity của các changeset cũ phải được giữ ổn định**. Đừng tạo hai master changelog có đường dẫn khác nhau rồi vô tình khiến Liquibase xem cùng một changeset là một định danh khác. Dùng đúng artifact/đường dẫn lịch sử hoặc fixture được chuẩn bị theo cách dự án quản lý.

### 9.1. Dữ liệu legacy cần có trong fixture

Ví dụ bảng customer trước migration có thể chứa:

- email NULL nếu schema cũ cho phép.
- email trùng nhau nếu chưa có unique constraint.
- chuỗi rỗng hoặc khoảng trắng.
- giá trị Unicode.
- timestamp ở timezone khác nhau.
- dữ liệu tham chiếu bị thiếu do hệ thống cũ chưa áp FK.

Nếu release mới thêm NOT NULL hoặc unique constraint, test phải chứng minh bước làm sạch/backfill diễn ra trước khi thêm constraint. Một database sạch không phát hiện được những lỗi này.

## 10. Kiểm thử precondition

Precondition bảo vệ changeset khỏi chạy trong trạng thái database không phù hợp. Testcontainers giúp kiểm tra điều kiện trên đúng catalog và dữ liệu của DBMS thật.

Ví dụ precondition yêu cầu bảng tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-add-customer-status
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
~~~

Test nên có ít nhất hai tình huống:

- Bảng tồn tại: changeset được chạy và cột status xuất hiện.
- Bảng không tồn tại: migration dừng theo chính sách HALT, không đánh dấu nhầm thành công.

Với onFail=MARK_RAN, cần kiểm tra cả hai nhánh: precondition đạt thì change được thực thi; precondition không đạt thì changeset được ghi nhận theo chính sách nhưng phần change bị bỏ qua. Đừng chỉ kiểm tra DATABASECHANGELOG có bản ghi; phải xác minh trạng thái schema tương ứng.

## 11. Kiểm thử rollback trên DBMS thực tế

Rollback có thể phụ thuộc transaction và khả năng DDL của DBMS. Testcontainers giúp kiểm chứng SQL đảo ngược trên đúng engine.

Một quy trình test:

1. Khởi tạo container và chạy update tới tag/changeset cần kiểm tra.
2. Xác minh schema/data sau migration.
3. Chạy rollback SQL preview hoặc phạm vi rollback dự kiến.
4. Thực thi rollback trên database test dùng riêng.
5. Xác minh đối tượng đã được đảo ngược.
6. Xác minh dữ liệu không bị mất ngoài dự kiến.
7. Nếu có ý nghĩa, chạy update lại để kiểm tra khả năng reapply.

Ví dụ các lệnh Liquibase thường dùng:

~~~bash
liquibase validate
liquibase update
liquibase rollback-count-sql --count=1
liquibase rollback-count --count=1
~~~

Các lệnh cần được cấu hình cùng JDBC URL của container và changelog tương ứng. Tên lệnh/options phụ thuộc Liquibase version. Chỉ chạy rollback-count trên database test đã xác nhận đúng đích; không lấy command này làm lệnh mặc định cho production.

### 11.1. Không giả định mọi DBMS rollback DDL như nhau

PostgreSQL hỗ trợ transactional DDL cho nhiều thao tác, nhưng CREATE INDEX CONCURRENTLY có hạn chế transaction. Một số DBMS có DDL auto-commit hoặc hành vi rollback khác. Vì vậy, test rollback phải bao gồm cả tình huống lỗi ở giữa changeset nếu migration có nhiều thao tác.

Với thay đổi dữ liệu không thể đảo ngược chính xác, kiểm tra backup/forward-fix thay vì viết một câu SQL ngược có vẻ đối xứng nhưng sai nghiệp vụ.

## 12. Kiểm thử checksum và lịch sử changeset

Liquibase sử dụng DATABASECHANGELOG để nhận diện changeset đã được áp dụng và theo dõi checksum/kiểu thực thi.

Test có thể kiểm tra:

- Changeset mới được ghi đúng ID, author, filename.
- Changeset cũ không bị thực thi lại trong update thông thường.
- Checksum không thay đổi ngoài chủ đích giữa artifact đã phát hành.
- runAlways/runOnChange hoạt động theo ý định.
- mark-next-changeset-ran hoặc onFail=MARK_RAN tạo lịch sử đúng nhưng không thực thi change.
- Lịch sử và trạng thái schema thực tế không bị lệch.

Ví dụ:

~~~sql
SELECT id, author, filename, md5sum,
       exectype, dateexecuted, orderexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Không kiểm tra checksum bằng cách hard-code một giá trị MD5SUM vào test trừ khi có lý do rất cụ thể và kiểm soát version. Thường nên xác minh changeset identity, EXECTYPE và hành vi update; checksum được quản lý bởi Liquibase theo phiên bản.

Một bản ghi lịch sử không chứng minh SQL đã tạo ra schema mong đợi. Luôn kết hợp assertion DATABASECHANGELOG với assertion schema/data.

## 13. Kiểm thử lock và nhiều tiến trình migration

DATABASECHANGELOGLOCK điều phối các tiến trình Liquibase cùng phạm vi khóa. Testcontainers có thể chạy hai tiến trình trên cùng database container để kiểm tra việc chờ khóa và xử lý lỗi.

Một test concurrency có kiểm soát nên:

- Dùng cùng database, cùng changelog identity và cùng bảng lock.
- Khởi chạy hai Liquibase runner gần đồng thời.
- Quan sát tiến trình lấy lock và tiến trình chờ.
- Xác minh changeset chỉ được áp dụng một lần trong luồng update bình thường.
- Kiểm tra lock được giải phóng sau khi kết thúc thành công.
- Mô phỏng process thất bại trong một test riêng và kiểm tra trạng thái trước khi retry.

Không nên dùng sleep cố định để khẳng định timing. Dùng latch/barrier, log hoặc tín hiệu trạng thái để đồng bộ test. Không kiểm tra rằng tiến trình B phải chờ đúng một số mili giây; điều đó phụ thuộc tải và môi trường CI.

Test concurrency dễ flaky nếu cùng một schema được nhiều test method dùng đồng thời. Hãy chạy test riêng, cô lập database/schema và giới hạn song song khi kiểm tra hành vi lock.

## 14. Cô lập database và dữ liệu giữa các test

Container riêng cho mỗi test method giúp cô lập mạnh nhưng có thể chậm vì phải khởi động DBMS nhiều lần. Container static cho một test class nhanh hơn, nhưng các test dùng chung schema và dữ liệu.

Một số chiến lược:

| Chiến lược | Ưu điểm | Rủi ro/cách dùng |
|---|---|---|
| Một container cho mỗi class | Startup một lần, phù hợp test migration cùng bộ | Phải dọn dữ liệu giữa test |
| Một container cho mỗi method | Cô lập cao | Chậm, tốn CPU/RAM |
| Một container, database riêng cho từng test | Cô lập lịch sử và schema tốt | Cần quản lý tạo/xóa database |
| Một container, schema riêng cho từng test | Nhẹ hơn database riêng | Phải cấu hình default schema và history/lock riêng |
| Container dùng chung toàn suite | Nhanh | Cần quản lý lifecycle, Spring context cache và concurrency cẩn thận |

Với migration test, dùng một database sạch cho từng kịch bản thường dễ hiểu hơn việc chạy nhiều test trên một DATABASECHANGELOG đã tích lũy lịch sử.

### 14.1. Dọn dữ liệu không được xóa lịch sử migration tùy tiện

Nếu chỉ cần reset dữ liệu nghiệp vụ giữa test, có thể dùng transaction rollback cho test data hoặc TRUNCATE các bảng phù hợp. Nhưng không xóa DATABASECHANGELOG để làm database “trông như mới” trong khi schema vẫn tồn tại.

Để test fresh install, tạo database mới hoặc container mới. Để test upgrade, tạo lại trạng thái phiên bản trước. Đừng tái sử dụng một schema đã chạy migration với lịch sử không tương ứng.

## 15. Vòng đời container và Spring TestContext cache

Testcontainers JUnit Jupiter hỗ trợ container static (một container cho class) và instance (một container cho test instance). Spring TestContext có thể cache ApplicationContext để tăng tốc giữa các test class.

Điều này tạo ra một bẫy: một Spring context đã giữ DataSource trỏ tới container của class trước, nhưng container đó đã bị dừng khi class kết thúc. Test class sau tái sử dụng context cache có thể kết nối vào endpoint không còn tồn tại.

Cách xử lý tùy kiến trúc:

- Dùng base test class chia sẻ container và context với lifecycle tương thích.
- Quản lý container bằng Spring bean/Testcontainers integration phù hợp Spring Boot.
- Cấu hình context cache/lifecycle rõ ràng.
- Chỉ dùng @DirtiesContext khi thật sự cần làm mới context; không lạm dụng vì làm test chậm.
- Không tắt container trong khi context còn giữ connection tới nó.

Nếu test chạy song song, cần xác định container/database nào được chia sẻ và dữ liệu nào có thể tranh chấp. Lifecycle không rõ ràng thường tạo lỗi ngẫu nhiên chỉ xuất hiện trên CI.

## 16. Kiểm thử nhiều DBMS bằng test matrix

Nếu module hỗ trợ nhiều hệ quản trị, nên có test matrix theo DBMS/version:

| DBMS | Container/module | Nhóm kiểm tra |
|---|---|---|
| PostgreSQL | PostgreSQLContainer | DDL, JSON/UUID, sequence, index, concurrent DDL |
| MySQL | MySQLContainer | kiểu dữ liệu, auto increment, constraint, DDL behavior |
| MariaDB | MariaDBContainer | tương thích riêng với MariaDB và driver |
| Oracle | Oracle container/image phù hợp | sequence, identity, PL/SQL, schema/identifier |
| SQL Server | MSSQLServerContainer | T-SQL, schema, identity và transaction |

Việc sử dụng image có thể chịu điều kiện license, registry access, architecture hoặc cấu hình riêng. Hãy dùng image được tổ chức phê duyệt và version gần production.

Không chạy mọi DBMS ở mọi test method. Chia test theo nhóm changeset và DBMS support; những thay đổi chỉ dành cho PostgreSQL có thể dùng filter dbms=postgresql, còn các invariant chung cần được kiểm tra trên từng engine được hỗ trợ.

## 17. Kiểm thử SQL đặc thù DBMS và extension

Một số migration phụ thuộc extension hoặc chức năng riêng của database. Ví dụ PostgreSQL có thể dùng extension, function, partial index hoặc expression index.

Testcontainers giúp xác minh SQL thật, nhưng image chuẩn có thể chưa cài extension cần thiết. Có thể dùng custom image đã được phê duyệt hoặc bước cài extension trong fixture, miễn là test tái tạo được môi trường production.

Các câu hỏi cần kiểm tra:

- Extension có sẵn và đúng version?
- User migration có quyền CREATE EXTENSION không?
- Extension được bật trước changeset phụ thuộc chưa?
- Index expression/partial index có định nghĩa đúng?
- Function/trigger có được tạo và gọi đúng?
- Rollback có xử lý dependency?
- Image test có cùng major version với production?

Không cài extension tùy tiện trong test rồi giả định production cũng có quyền/cấu hình tương tự.

## 18. Kiểm thử migration lỗi và trạng thái nửa hoàn tất

Test cần xác minh cách DBMS và Liquibase xử lý khi changeset thất bại.

Các tình huống đáng kiểm tra:

- SQL sai cú pháp.
- Thiếu quyền DDL.
- Vi phạm unique, FK hoặc NOT NULL.
- Lock timeout/deadlock.
- Tệp sqlFile hoặc CSV không tồn tại.
- Changeset chứa nhiều thao tác và lỗi xảy ra ở giữa.
- runInTransaction=false hoặc DDL không hỗ trợ transaction.
- Container bị mất kết nối trong lúc migration.

Sau lỗi, không chỉ assert rằng Spring context ném exception. Cần kiểm tra:

1. DATABASECHANGELOG có ghi changeset lỗi hay không.
2. DATABASECHANGELOGLOCK có được giải phóng hay còn trạng thái giữ khóa.
3. Schema có thay đổi một phần không.
4. Dữ liệu có được ghi một phần không.
5. Retry có an toàn hay sẽ gặp object already exists/duplicate key.
6. Cần rollback, restore hay forward-fix.

Hành vi rollback transaction khác nhau theo DBMS và loại câu lệnh. Test nên xác minh kết quả thực tế thay vì giả định mọi changeset thất bại đều không để lại thay đổi.

## 19. Test precondition, context và label trong nhiều profile

Spring Boot có thể chọn datasource hoặc changelog theo profile. Liquibase cũng có context và label để lọc changeset. Testcontainers cho phép chạy cùng artifact dưới nhiều cấu hình:

- Context test chỉ nạp dữ liệu phục vụ test.
- Context prod bỏ qua seed data chỉ dành cho dev.
- Changeset dbms=postgresql chỉ chạy trên PostgreSQL.
- Label chọn nhóm migration theo đợt triển khai.

Mỗi test phải ghi rõ filter đang dùng. Nếu test profile vô tình chạy cả context dev và prod, kết quả có thể không giống pipeline production.

Nên có test riêng cho cấu hình production-like, không chứa seed hoặc changeset chỉ dành cho môi trường phát triển. Kiểm tra DATABASECHANGELOG và dữ liệu sau khi chạy từng profile để chứng minh filter có hiệu lực.

## 20. Test migration đóng gói trong executable JAR

Một test dùng classpath trong IDE xác minh nội dung resource ở test runtime, nhưng không chứng minh JAR phát hành có đủ changelog, sqlFile, CSV và rollback file.

Có thể bổ sung bước kiểm thử artifact:

1. Build executable JAR trong CI.
2. Liệt kê tài nguyên trong JAR và xác nhận mọi file migration có mặt.
3. Khởi chạy chính JAR với datasource trỏ tới Testcontainers hoặc database test.
4. Xác minh Liquibase tìm được changelog và các file con.
5. Kiểm tra schema/data/history sau khi ứng dụng khởi động.
6. Chạy trên đúng Java/Spring Boot/Liquibase dependency đã đóng gói.

Ví dụ kiểm tra archive:

~~~bash
jar tf target/application.jar
~~~

Với Spring Boot executable JAR, tài nguyên ứng dụng thường ở BOOT-INF/classes và dependency ở BOOT-INF/lib. Không chỉ kiểm tra master changelog; cần kiểm tra mọi tài nguyên được tham chiếu gián tiếp.

Bước này đặc biệt hữu ích khi IDE test thành công nhưng môi trường container production báo không tìm thấy sqlFile hoặc CSV.

## 21. Tối ưu tốc độ và độ ổn định của integration test

Testcontainers khởi chạy DBMS thật nên chậm hơn unit test. Có thể giữ tốc độ hợp lý bằng cách:

- Chia test theo nhóm: unit, integration DBMS, migration upgrade và concurrency.
- Dùng container static theo class hoặc suite khi lifecycle rõ ràng.
- Chỉ chạy DBMS matrix đầy đủ trong CI thích hợp, không lặp lại ở mọi unit test.
- Dùng image được cache trong CI nhưng pin version/digest.
- Giới hạn concurrency để không làm host hoặc database container quá tải.
- Tạo fixture dữ liệu nhỏ nhưng đại diện cho trường hợp biên.
- Tránh sleep cố định và assertion phụ thuộc thời gian chạy.
- Thu thập log container khi test thất bại.
- Dùng timeout hợp lý cho startup và migration.
- Không bật reuse container toàn cục nếu test cần database sạch và lịch sử xác định.

Reuse container có thể tăng tốc local nhưng làm trạng thái database tồn tại giữa các lần chạy. Nếu dùng, phải reset database/schema có kiểm soát; không để DATABASECHANGELOG cũ làm test mới bỏ qua migration.

## 22. Chạy Testcontainers trong CI/CD

Pipeline cần có runtime cho container và quyền truy cập daemon phù hợp. Trình tự điển hình:

1. Compile/test nhanh.
2. Khởi chạy nhóm integration test Testcontainers với DBMS đúng production.
3. Chạy fresh install.
4. Chạy upgrade từ fixture release trước.
5. Kiểm tra schema, dữ liệu và DATABASECHANGELOG.
6. Chạy rollback test ở database disposable khi phù hợp.
7. Lưu log/test report và phiên bản image.
8. Chỉ promote artifact khi các kiểm tra bắt buộc đạt.

Nếu CI dùng Docker-in-Docker hoặc remote Docker host, cấu hình Testcontainers phải trỏ đúng daemon và network. Lỗi không kết nối được Docker thường xảy ra trước khi Liquibase được gọi; cần phân biệt với lỗi migration.

Không cho test tự động kết nối tới production do biến môi trường bị cấu hình sai. Dùng endpoint container được tạo cho test và xác minh database identity trước khi chạy các thao tác destructive.

## 23. Troubleshooting: lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Docker daemon không truy cập được | CI runner chưa bật hoặc chưa cấp quyền | Kiểm tra Docker socket/runtime và cấu hình Testcontainers |
| Container không khởi động | Image không tải được, sai architecture, thiếu tài nguyên | Kiểm tra image, registry, RAM/CPU và log container |
| Spring Boot kết nối nhầm DB | Datasource profile ghi đè dynamic properties | Kiểm tra effective properties và JDBC URL |
| Liquibase không chạy | spring.liquibase.enabled=false hoặc thiếu dependency | Kiểm tra profile, dependency và startup log |
| Không tìm thấy changelog | Sai classpath path hoặc resource không có trong test runtime | Kiểm tra src/main/resources và include |
| Migration chạy trên H2 thay vì container | Test config vẫn nạp datasource H2 | Kiểm tra driver, URL và dependency |
| Unique/FK violation chỉ trên PostgreSQL | DBMS thực thi constraint khác H2 hoặc dữ liệu fixture không hợp lệ | Kiểm tra dữ liệu trước migration |
| Test flaky khi chạy song song | Nhiều test chia sẻ schema/history/data | Cô lập database/schema và điều phối concurrency |
| Spring context dùng container đã dừng | TestContext cache và lifecycle container không khớp | Chia sẻ container đúng lifecycle hoặc làm mới context |
| Rollback để lại object | DDL/transaction hoặc rollback SQL không tương thích | Kiểm tra catalog và transaction behavior |
| Test qua nhưng production lỗi | Image/version/extension/permission khác | Đồng bộ DBMS version và cấu hình production-like |
| Không thấy thay đổi sau update | Changeset đã có trong DATABASECHANGELOG hoặc bị filter | Kiểm tra history, context, label và DBMS |
| Lock vẫn giữ sau lỗi | Process/connection chưa kết thúc hoặc trạng thái lock tồn đọng | Kiểm tra holder và DATABASECHANGELOGLOCK trước retry |

Khi điều tra, đi theo thứ tự: **container sống và sẵn sàng → JDBC URL đúng → Spring profile → Liquibase startup → changelog/resource → SQL/DBMS → transaction/history → assertion**. Không sửa DATABASECHANGELOG thủ công chỉ để làm test xanh.

## 24. Checklist cho bộ test Liquibase bằng Testcontainers

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Container dùng đúng DBMS production? | Image và version được pin |
| JDBC driver tương ứng có trong test/runtime? | Dependency đã xác minh |
| Test kết nối đúng endpoint container? | JDBC URL do container cung cấp |
| Spring Boot có bật Liquibase trong test? | Effective property và log startup |
| Changelog root và file con có trên classpath? | Kiểm tra resource/test artifact |
| Fresh install đạt? | Schema, constraint, index và seed data được assert |
| Upgrade từ release trước đạt? | Fixture lịch sử và dữ liệu legacy |
| Precondition/context/label được kiểm tra? | Test cả nhánh đạt và không đạt |
| DATABASECHANGELOG đúng? | ID/author/filename/EXECTYPE được đối chiếu |
| DATABASECHANGELOGLOCK được giải phóng? | Trạng thái lock sau khi chạy |
| Rollback được thử trên DBMS thật? | SQL preview và trạng thái sau rollback |
| Lỗi giữa migration được kiểm tra? | Schema/data/history sau failure |
| Test concurrency có cô lập? | Không dùng chung state ngoài ý muốn |
| Container và Spring context có lifecycle tương thích? | Không tái sử dụng context trỏ container đã dừng |
| Có test từ executable JAR? | Artifact thật chạy với database test |
| CI có container runtime? | Pipeline log và test report |
| Secrets và dữ liệu test an toàn? | Không dùng credentials/PII production |

**Nguyên tắc cuối cùng:** Testcontainers giúp kiểm thử migration trên chính hệ quản trị mà ứng dụng sẽ sử dụng. Hãy pin image/version, nối Spring Boot và Liquibase vào endpoint container, kiểm tra cả fresh install lẫn upgrade, xác minh schema/data/history, thử rollback và tình huống lỗi, đồng thời cô lập database giữa các test. Một bộ test chỉ xanh trên H2 hoặc chỉ xác nhận Spring context khởi động chưa đủ để chứng minh migration an toàn trên DBMS production.

