# Flyway, Liquibase và kiểm chứng nâng cấp schema trong Spring Boot Testing

## Mục tiêu học tập

Một hệ thống Spring Boot có thể chạy đúng với database **mới tinh** nhưng thất bại khi triển khai lên database **đang chứa dữ liệu thật**. Lý do là việc tạo các bảng ở trạng thái cuối không tương đương với quá trình **nâng cấp schema từ phiên bản cũ sang phiên bản mới**. Migration phải bảo vệ cả **cấu trúc**, **dữ liệu hiện hữu**, **ràng buộc**, **lịch sử phiên bản** và **khả năng triển khai lặp lại**.

Hai công cụ thường dùng trong Spring Boot là:

- **Flyway:** quản lý các migration theo phiên bản, thường qua file SQL `V1__...sql`, `V2__...sql`, có bảng lịch sử `flyway_schema_history`.
- **Liquibase:** quản lý **changeset** bằng XML/YAML/JSON/formatted SQL, theo dõi trong `DATABASECHANGELOG` và cơ chế khóa `DATABASECHANGELOGLOCK`.

Bài thuộc module **Spring Boot – testing**, nhánh **Dữ liệu kiểm thử**, với đề bài **Flyway, Liquibase và kiểm chứng nâng cấp schema**. Trọng tâm không chỉ là cấu hình để migration chạy mà còn là viết phép kiểm có thể phát hiện những sai sót khi chuyển từ schema cũ sang schema mới.

Sau bài, bạn sẽ biết cách:

1. Phân biệt schema migration, schema generation của Hibernate và fixture SQL của test.
2. Cấu hình Flyway/Liquibase đúng lifecycle trong Spring Boot; tránh chạy hai công cụ cùng quản lý một schema.
3. Viết migration có thứ tự: **tạo bảng V1 → thêm cột V2 → backfill dữ liệu → ràng buộc NOT NULL/default**.
4. Viết test thực sự dựng **V1**, insert dữ liệu theo V1, rồi chạy **V2 trên chính database đó**.
5. Kiểm dữ liệu trước đây vẫn đọc được, cột mới có giá trị đúng, constraint có hiệu lực và history ghi đủ migrations.
6. Xác nhận migration **idempotent ở mức công cụ**: chạy `migrate/update` lần nữa không áp dụng lại một migration đã thành công.
7. Kiểm migration tự chạy trước khi ứng dụng sử dụng JDBC beans khi Spring Boot khởi động.
8. Dùng database/schema tách riêng và Testcontainers khi migration chứa PostgreSQL/MySQL-specific syntax.
9. Đánh giá checksum drift, migration fail giữa chừng, transaction DDL, rollback, expand–contract và chiến lược CI/CD an toàn.
10. Chạy một project minh họa bằng **Java 17, Spring Boot 3.3.5, Gradle, JUnit Jupiter, H2, Flyway và Liquibase**.

**Nguyên tắc:** Migration test **không chỉ hỏi “schema mới có cột chưa?”**. Nó phải hỏi “database được nâng từ phiên bản cũ có giữ dữ liệu, biến đổi đúng và đáp ứng hợp đồng của version mới không?”.

## 1. Schema mới tinh và schema được nâng cấp là hai bài toán khác nhau

Giả sử bản phát hành V1 có bảng:

~~~sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(120) NOT NULL
);
~~~

Bản V2 yêu cầu thêm `status` và bảo đảm tài khoản cũ có trạng thái `ACTIVE`.

Nếu chỉ tạo schema cuối cùng:

~~~sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(120) NOT NULL,
    status VARCHAR(16) DEFAULT 'ACTIVE' NOT NULL
);
~~~

thì bạn **chưa kiểm** những điều quan trọng:

- Database V1 có nhiều row, nâng cấp có giữ nguyên ID/email?
- Dữ liệu cũ được backfill thành `ACTIVE` trước khi thêm `NOT NULL`?
- Nếu tạo constraint trước khi backfill, migration có fail khi bảng đã có row?
- Migration đã được đánh dấu hoàn tất trong schema history chưa?
- Nếu ứng dụng khởi động lại, công cụ có tránh chạy lại ALTER/INSERT gây lỗi không?
- Có đang dùng đúng DB engine và đúng migration locations?
- Có migration cũ bị sửa nội dung làm checksum thay đổi?
- Tác động của DDL transaction trên PostgreSQL, MySQL, H2 có giống nhau không?

Một test nâng cấp **đúng nghĩa** phải bắt đầu từ **V1** có dữ liệu, sau đó triển khai các bước V2, rồi xác minh **state sau chuyển đổi**.

### Từ baseline đến phiên bản mới

~~~text
Database trống (test-only, độc lập)
           |
           v
Áp dụng V1 -> customer_accounts(id, email)
           |
           v
Insert account cũ: (101, "old@example.test")
           |
           v
Áp dụng V2 -> thêm status
           |    backfill status = ACTIVE
           |    đặt NOT NULL và DEFAULT
           v
Đọc account ID=101
  - email không đổi
  - status = ACTIVE
  - constraint NOT NULL đang hoạt động
  - migration history chỉ có V1, V2
           |
           v
Chạy migrate/update lần nữa
  - không áp dụng lại V1/V2
  - dữ liệu không bị nhân đôi/xóa
~~~

**Lưu ý từ vựng:** “Migration chạy lặp lại an toàn” ở đây nghĩa công cụ kiểm history và **không chạy lại changeset/version đã thành công**, không có nghĩa mọi câu SQL migration riêng lẻ đều idempotent nếu bạn thủ công thực thi lặp lại nó.

## 2. Flyway và Liquibase khác nhau thế nào?

| Tiêu chí | Flyway | Liquibase |
| --- | --- | --- |
| Đơn vị phổ biến | Versioned/repeatable migration | Changeset trong changelog |
| File thông dụng | `V1__create.sql`, `V2__alter.sql`, `R__refresh.sql` | XML, YAML, JSON, formatted SQL |
| Thứ tự | Theo version; repeatable theo checksum và dependency | Theo thứ tự changelog/include, kèm điều kiện |
| Lịch sử | `flyway_schema_history` | `DATABASECHANGELOG` |
| Khóa tránh chạy đồng thời | Migration locking tùy engine/cơ chế | `DATABASECHANGELOGLOCK` |
| Kiểm drift | `validate()`/checksum, info trạng thái | Changeset checksum/validation |
| Nâng V1 → V2 trong test | `Flyway.configure().target("1")`, sau đó latest | Chạy changelog chỉ gồm V1 rồi master V1+V2 |
| Chọn môi trường | Locations, placeholders, cấu hình | Contexts, labels, preconditions |
| Rollback | Thường **forward-fix**; chức năng undo tùy edition/version | Có thể khai báo rollback cho changesets, nhưng không tự bảo đảm đảo ngược mọi thay đổi dữ liệu |
| Rủi ro | Sửa versioned migration đã chạy, SQL sai dialect | Đổi identity/checksum changeset, context/label áp sai, changelog path di chuyển |
| Chọn tool | Team thích SQL trực tiếp, version file rõ | Team thích changeset model, multi-format, context/label/rollback definitions |

**Không nên bật cả Flyway và Liquibase cùng migrate một schema một cách vô ý.** Chọn một công cụ làm nguồn chân lý cho database chính. Nếu tổ chức thực sự có lý do vận hành cả hai, phải phân chia phạm vi schema/data source, thứ tự và ownership cụ thể, kiểm rõ trong CI. Project ở dưới cài cả hai **để học và so sánh**, nhưng tách database và **tắt Liquibase auto migration** trong test kiểm Spring Boot startup của Flyway.

## 3. Spring Boot chạy migrations khi nào?

Khi dependency/config phù hợp, Spring Boot thường kích hoạt migration **trong quá trình ApplicationContext khởi động**, trước những bean khai báo phụ thuộc database initialization được sử dụng. Có thể có `Flyway` hoặc `SpringLiquibase` bean. Nhưng bạn vẫn phải kiểm thực tế vì custom wiring, profiles hoặc bean ordering có thể thay đổi kết quả.

### Flyway

Với Spring Boot 3.3, dependency chủ yếu:

~~~groovy
implementation 'org.flywaydb:flyway-core'
~~~

Mặc định Flyway tìm versioned SQL ở `classpath:db/migration`. Tên file ví dụ:

~~~text
V1__create_customer_accounts.sql
V2__add_status_and_backfill.sql
R__refresh_reporting_view.sql
~~~

- `V1`, `V2` xác định version.
- Hai dấu gạch dưới `__` phân tách version và mô tả.
- File `R__...` là **repeatable migration**; chỉ dùng khi hiểu khi nào checksum thay đổi và thứ tự xử lý.
- `spring.flyway.locations` điều khiển nơi tìm migrations.
- `spring.flyway.enabled=false` tắt việc tích hợp tự động trong context khi bạn muốn tự điều phối migration trong một phép thử đặc biệt.
- Một số database engines trong Flyway 10 cần module riêng, ví dụ `org.flywaydb:flyway-database-postgresql` với PostgreSQL.
- Không nhầm Flyway Java API với **Flyway Gradle plugin**: gọi Flyway từ test Java không yêu cầu plugin `org.flywaydb.flyway` trong `build.gradle`.

### Liquibase

Trong Spring Boot 3.3 có thể dùng:

~~~groovy
implementation 'org.liquibase:liquibase-core'
~~~

Mặc định Boot tìm master changelog tại `db/changelog/db.changelog-master.yaml`, hoặc dùng:

~~~properties
spring.liquibase.change-log=classpath:db/changelog/db.changelog-master.xml
spring.liquibase.enabled=true
~~~

Liquibase quản lý những changesets chưa áp dụng theo identity gồm **id, author và filename/logical file path**, kèm checksums. Các cấu hình quan trọng:

- `spring.liquibase.enabled=false`: tắt Liquibase auto-update trong Spring Boot context.
- `spring.liquibase.contexts`: chọn changeSets cho môi trường cụ thể.
- `spring.liquibase.labels`: filter changesets theo labels.
- `spring.liquibase.change-log`: đường dẫn master file.
- Với multi-DataSource, Boot có thể dùng `@LiquibaseDataSource` hoặc `spring.liquibase.url/user/password` theo cấu hình thích hợp.

**Cảnh báo version:** Ngữ nghĩa API/config trong bài chốt **Spring Boot 3.3.5**. Dòng Boot 4 hoặc Liquibase/Flyway major version mới có thể thay đổi module names, default behaviors và runtime requirements; không copy dependency từ blog mới sang dự án cũ mà không đối chiếu BOM/Javadoc.

## 4. Một test migration tốt phải kiểm những gì?

Bản tối thiểu nên kiểm cả sáu lớp:

1. **Khởi tạo V1:** schema cũ có đúng bảng/cột; V2 chưa có cột mới.
2. **Đặt dữ liệu lịch sử:** insert một hoặc nhiều bản ghi theo đúng hợp đồng V1.
3. **Nâng cấp:** chạy V2 bằng tool thật, không tự gọi SQL V2 ở test thay engine.
4. **Bảo toàn dữ liệu:** ID, email/field cũ không bị mất/đổi ngoài đặc tả.
5. **Schema mới:** status được backfill; constraint `NOT NULL`/default/index có hiệu lực.
6. **History/idempotency:** tool ghi nhận đủ migrations và không chạy lại chúng khi khởi động lần nữa.

Đối với production schema, nên thêm:

- Foreign keys/check constraints/indexes có thực sự áp dụng?
- Timestamp/time zone/decimal precision hoạt động đúng?
- Backfill có xử lý cả row null/blank/legacy đặc biệt?
- Query của phiên bản ứng dụng **cũ** còn hoạt động trong giai đoạn rolling deploy?
- Zero-downtime rollout có tránh table locks dài hoặc rewrite table lớn?
- Data migration có xử lý được batches, retry và restart?
- Người dùng/tenant khác nhau có dữ liệu đặc thù không?
- Đường rollback/restore và backup đã được diễn tập chưa?

**Đừng đánh đồng “schema có cột” với “data upgrade đúng”.** Một `ALTER TABLE ADD COLUMN` đơn thuần có thể tạo column `status` toàn null; test chỉ check metadata sẽ pass trong khi code V2 cần status non-null.

## 5. Vì sao không dùng Hibernate `ddl-auto=create-drop` để kiểm migration?

Spring Data JPA/Hibernate có khả năng sinh schema từ entity mapping. Ví dụ:

~~~properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

Cấu hình này thích hợp cho một số demo JPA cô lập, **nhưng không kiểm Flyway/Liquibase SQL**. Nó dựng bảng ở **trạng thái entity hiện tại**, không đi qua lịch sử version V1→V2. Nếu V2 migration bị viết sai hoặc quên backfill, test vẫn có thể xanh vì Hibernate đã tạo đúng schema cuối.

Khi migration là nguồn chân lý:

- Dùng **Flyway/Liquibase** để quản lý DDL.
- Với JPA, dùng `spring.jpa.hibernate.ddl-auto=validate` hoặc `none` theo mục tiêu.
- Không để `schema.sql`/`data.sql` tự tạo lại tables song song một cách vô ý.
- Đối chiếu entity mapping với schema đã migrate, không để entity tự âm thầm update schema thay migration.
- Chạy migrations thật trên database có dữ liệu V1 để kiểm quá trình nâng cấp.

**`ddl-auto=validate` chỉ kiểm mapping tương thích với schema nhìn thấy**, không kiểm backfill, history, dữ liệu cũ còn nguyên hoặc chiến lược rollback.

## 6. Project Java 17/Spring Boot 3.3.5 chạy được

Project dưới đây chủ động dùng **H2 in-memory và JDBC** để tập trung vào migrations. Không cần Docker hoặc database ngoài. Các bài nâng cấp sử dụng H2 được tạo riêng cho từng test, tránh trùng state. Một test dùng Spring Boot auto-configuration để xác nhận Flyway tự migrate khi context khởi động.

### 6.1. Danh sách tệp

~~~text
schema-upgrade-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/com/example/migration/
    │   │   └── SchemaUpgradeApplication.java
    │   └── resources/db/migration/flyway/
    │       ├── V1__create_customer_accounts.sql
    │       └── V2__add_status_and_backfill.sql
    └── test/
        ├── java/com/example/migration/
        │   ├── FlywayUpgradeTest.java
        │   ├── LiquibaseUpgradeTest.java
        │   └── BootFlywayStartupTest.java
        └── resources/db/changelog/accounts/
            ├── 001-create.xml
            ├── 002-upgrade.xml
            ├── only-v1.xml
            └── master.xml
~~~

**Các file Liquibase XML được đặt dưới `src/test/resources`**, chỉ phục vụ ví dụ kiểm tool; không trở thành một migration chain chạy tự động trong ứng dụng production của lab này. Flyway SQL ở `src/main/resources` là migration chain mặc định mà bài Spring Boot startup test sẽ sử dụng qua `spring.flyway.locations`.

File Gradle Wrapper là tài nguyên tạo bởi Gradle; source text phía dưới không tự bao gồm JAR nhị phân.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'schema-upgrade-lab'
~~~

### 6.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.flywaydb:flyway-core'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.liquibase:liquibase-core'

    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Tại sao cấu hình như vậy?**

- `spring-boot-starter-jdbc`: có `JdbcTemplate`, `DataSource`, `DriverManagerDataSource`, Hikari và transaction infrastructure.
- `flyway-core`: dùng Flyway Java API và Boot Flyway auto-configuration.
- `liquibase-core`: dùng Liquibase Java API trong **test code**.
- `spring-boot-starter-test`: JUnit Jupiter, Spring TestContext/assertions.
- H2 ở `testRuntimeOnly`: engine embedded chỉ dùng trong test.
- Không dùng cả Flyway và Liquibase để migrate cùng một DataSource. Boot smoke test có `spring.liquibase.enabled=false` để Liquibase dependency trên test classpath không gây migration tự động.
- `useJUnitPlatform()` giúp Gradle chạy JUnit 5.

Khi áp dụng thực tế, đa số production services chỉ đưa **một công cụ migration** vào runtime classpath. Project này cài Liquibase test-only để so sánh cách kiểm chứng hai công cụ.

### 6.4. `SchemaUpgradeApplication.java`

**`src/main/java/com/example/migration/SchemaUpgradeApplication.java`**

~~~java
package com.example.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SchemaUpgradeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SchemaUpgradeApplication.class, args);
    }
}
~~~

Project không có JDBC URL production/default; mục tiêu runnable là chạy **Gradle test**, nơi mỗi test cấp test database riêng. Không chạy `bootRun` trên môi trường không có DataSource chỉ vì bài có `main` class.

## 7. Flyway SQL migrations: V1 và V2

**`src/main/resources/db/migration/flyway/V1__create_customer_accounts.sql`**

~~~sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(120) NOT NULL
);
~~~

V1 chưa có `status`. Điều này giúp bài kiểm chứng thật sự thấy “schema trước nâng cấp”.

**`src/main/resources/db/migration/flyway/V2__add_status_and_backfill.sql`**

~~~sql
ALTER TABLE customer_accounts
    ADD COLUMN status VARCHAR(16);

UPDATE customer_accounts
SET status = 'ACTIVE'
WHERE status IS NULL;

ALTER TABLE customer_accounts
    ALTER COLUMN status SET NOT NULL;

ALTER TABLE customer_accounts
    ALTER COLUMN status SET DEFAULT 'ACTIVE';

CREATE INDEX idx_customer_accounts_status
    ON customer_accounts(status);
~~~

Giải thích thứ tự:

1. **Thêm cột nullable** để database V1 đang có dữ liệu không fail ngay.
2. **Backfill** row hiện hữu: mọi `status` null được đặt `ACTIVE`.
3. **Siết NOT NULL** sau khi dữ liệu đáp ứng constraint.
4. **Đặt DEFAULT** để các INSERT trong demo không ghi status vẫn nhận `ACTIVE`.
5. **Tạo index** phục vụ truy vấn thường gặp theo status.

Với H2 demo, các câu SQL này tương thích. Trên production PostgreSQL/MySQL, syntax/locking/transaction của ALTER/DEFAULT/INDEX có thể khác; **phải thử trên đúng engine/phiên bản production**.

### Tại sao không đặt NOT NULL ngay từ đầu?

Nếu bảng có row cũ, thêm cột non-null không default có thể fail vì row cũ chưa có giá trị hợp lệ. Tách thành **expand → backfill → contract** là một mẫu giảm rủi ro. Trong demo, các bước đó nằm trong V2 để dễ học; khi rolling deployment có nhiều phiên bản app chạy đồng thời, nên phân chia thành **nhiều lần deploy/migrations** để code V1 và V2 đều tương thích trong giai đoạn chuyển tiếp.

### Thế nào là “không sửa migration đã phát hành”?

Khi V1 đã chạy trên DB thật, **không chỉnh sửa nội dung V1** để sửa schema. Thay vào đó, tạo migration V3/V4 mới để thay đổi tiếp. Flyway lưu checksum của versioned migration; sửa file đã áp dụng có thể làm `validate` báo drift, là tín hiệu cần điều tra chứ không phải lỗi nên che bằng `repair` tùy tiện.

## 8. JUnit: kiểm Flyway nâng cấp từ V1 sang V2

**`src/test/java/com/example/migration/FlywayUpgradeTest.java`**

~~~java
package com.example.migration;

import java.util.UUID;

import javax.sql.DataSource;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.dao.DataIntegrityViolationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FlywayUpgradeTest {

    private static final String LOCATION =
            "classpath:db/migration/flyway";

    private DataSource newDatabase() {
        String name = "flyway_" +
                UUID.randomUUID().toString().replace("-", "");

        return new DriverManagerDataSource(
                "jdbc:h2:mem:" + name + ";DB_CLOSE_DELAY=-1",
                "sa",
                "");
    }

    private Flyway flyway(DataSource source) {
        return Flyway.configure()
                .dataSource(source)
                .locations(LOCATION)
                .load();
    }

    @Test
    void upgradesOldDataFromV1ToV2() {
        DataSource source = newDatabase();
        JdbcTemplate jdbc = new JdbcTemplate(source);

        // Bước 1: Chỉ chạy migrations tới V1.
        Flyway first = Flyway.configure()
                .dataSource(source)
                .locations(LOCATION)
                .target("1")
                .load();

        first.migrate();

        assertEquals("1",
                first.info().current().getVersion().getVersion());

        // V1 chưa có STATUS.
        Integer statusColumns = jdbc.queryForObject(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS " +
                "WHERE TABLE_NAME = ? AND COLUMN_NAME = ?",
                Integer.class, "CUSTOMER_ACCOUNTS", "STATUS");

        assertEquals(0, statusColumns);

        // Bước 2: Insert dữ liệu theo schema V1.
        jdbc.update(
                "INSERT INTO customer_accounts(id, email) " +
                "VALUES (?, ?)",
                101L, "old@example.test");

        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer_accounts",
                Integer.class));

        // Bước 3: Nâng DB hiện có tới latest (V2).
        Flyway latest = flyway(source);
        latest.migrate();
        latest.validate();

        assertEquals("2",
                latest.info().current().getVersion().getVersion());

        // Bước 4: Account cũ được giữ, status đã backfill.
        String email = jdbc.queryForObject(
                "SELECT email FROM customer_accounts WHERE id = ?",
                String.class, 101L);
        String status = jdbc.queryForObject(
                "SELECT status FROM customer_accounts WHERE id = ?",
                String.class, 101L);

        assertEquals("old@example.test", email);
        assertEquals("ACTIVE", status);

        // Bước 5: Constraint NOT NULL hoạt động.
        assertThrows(DataIntegrityViolationException.class, () ->
                jdbc.update(
                    "INSERT INTO customer_accounts(id, email, status) " +
                    "VALUES (?, ?, NULL)",
                    102L, "null@example.test"));

        // Bước 6: Database history có V1, V2 thành công.
        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM flyway_schema_history " +
                "WHERE success = TRUE",
                Integer.class));

        // Bước 7: Chạy lại không áp dụng thêm migration.
        assertEquals(0, latest.migrate().migrationsExecuted);
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer_accounts",
                Integer.class));
    }

    @Test
    void freshDatabaseGetsLatestSchemaOnce() {
        DataSource source = newDatabase();
        JdbcTemplate jdbc = new JdbcTemplate(source);
        Flyway tool = flyway(source);

        assertEquals(2, tool.migrate().migrationsExecuted);
        assertEquals(0, tool.migrate().migrationsExecuted);

        // DEFAULT áp dụng cho row insert sau migration.
        jdbc.update(
                "INSERT INTO customer_accounts(id, email) " +
                "VALUES (?, ?)",
                201L, "new@example.test");

        assertEquals("ACTIVE", jdbc.queryForObject(
                "SELECT status FROM customer_accounts WHERE id = ?",
                String.class, 201L));

        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM flyway_schema_history " +
                "WHERE success = TRUE",
                Integer.class));

        assertTrue(tool.info().current().getVersion()
                .getVersion().equals("2"));
    }
}
~~~

### Đọc các assertions quan trọng

| Phép kiểm | Bằng chứng |
| --- | --- |
| `first.info().current() == 1` | Chỉ migrations đến V1 đã áp dụng |
| Query `INFORMATION_SCHEMA.COLUMNS` trả 0 | V1 chưa có STATUS, nên phép thử có thể phân biệt “trước/sau” |
| Insert ID 101 trước V2 | Migration nâng trên **dữ liệu cũ**, không chỉ DB rỗng |
| `latest.info().current() == 2` | Database đã lên V2 |
| Email không đổi | Bảo toàn dữ liệu business quan trọng |
| Status = ACTIVE | Backfill chính xác |
| INSERT status NULL bị từ chối | Constraint NOT NULL có hiệu lực |
| History có hai successful rows | Lịch sử Flyway theo dự kiến |
| `migrationsExecuted == 0` lần hai | Không reapply V1/V2 |
| Database mới có default ACTIVE | V2 cũng làm việc khi DB ban đầu trống |

**Vì sao dùng `DriverManagerDataSource`?** Nó tạo các connection trực tiếp từ JDBC URL và đủ cho test nhỏ, không có pool. Mỗi JUnit method tạo một database H2 tên ngẫu nhiên `flyway_<UUID>` nên không phụ thuộc trạng thái method khác. H2 `DB_CLOSE_DELAY=-1` giữ in-memory database trong JVM dù connection cuối đóng, hữu ích cho nhiều câu lệnh mở connection riêng. Đây là **database tạm, chỉ dùng trong test**, không phải config production.

**Vì sao không dùng `@Transactional` quanh migration test?** Flyway tự quản lý thao tác migration/history. Nếu test mở một transaction JUnit bao quanh DDL hoặc mong rollback V2 vào cuối method, behavior có thể khác giữa database engines. Tách một database mới cho từng test sẽ dễ quan sát hơn.

**Giới hạn:** Tests trên H2 chưa bảo đảm SQL V2 của bạn chạy được trên PostgreSQL/MySQL; phần Testcontainers ở mục 17 dành cho yêu cầu đó.

## 9. Liquibase: định nghĩa schema bằng changesets

Để so sánh công bằng, Liquibase sử dụng **cùng hợp đồng business**: V1 có `id/email`; V2 thêm `status`, backfill `ACTIVE`, thêm NOT NULL/default.

Thay vì chỉ tạo một master file với hai changesets rồi chạy toàn bộ ngay từ đầu, lab có **hai entrypoint**:

- `only-v1.xml` chỉ include changeset V1 để tạo điểm xuất phát.
- `master.xml` include V1 và V2 để thực hiện nâng cấp thật.

Cả hai entrypoint đều include **cùng một file V1 vật lý** với path nhất quán. Điều này quan trọng: Liquibase định danh changeset bằng **id + author + filename/logicalFilePath**; nếu đổi filename khi chuyển từ bản V1 sang master, công cụ có thể xem đó là changeset khác và thử chạy lại lệnh tạo bảng.

### 9.1. `001-create.xml`

**`src/test/resources/db/changelog/accounts/001-create.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.20.xsd">

    <changeSet id="001-create-accounts" author="training">
        <createTable tableName="customer_accounts">
            <column name="id" type="BIGINT">
                <constraints primaryKey="true" nullable="false"/>
            </column>
            <column name="email" type="VARCHAR(120)">
                <constraints nullable="false"/>
            </column>
        </createTable>
    </changeSet>
</databaseChangeLog>
~~~

### 9.2. `002-upgrade.xml`

**`src/test/resources/db/changelog/accounts/002-upgrade.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.20.xsd">

    <changeSet id="002-add-status-and-backfill"
               author="training">
        <addColumn tableName="customer_accounts">
            <column name="status" type="VARCHAR(16)"/>
        </addColumn>

        <update tableName="customer_accounts">
            <column name="status" value="ACTIVE"/>
            <where>status IS NULL</where>
        </update>

        <addNotNullConstraint
            tableName="customer_accounts"
            columnName="status"
            columnDataType="VARCHAR(16)"/>

        <addDefaultValue
            tableName="customer_accounts"
            columnName="status"
            columnDataType="VARCHAR(16)"
            defaultValue="ACTIVE"/>

        <createIndex
            indexName="idx_customer_accounts_status"
            tableName="customer_accounts">
            <column name="status"/>
        </createIndex>
    </changeSet>
</databaseChangeLog>
~~~

Liquibase có thể hỗ trợ phần lớn DDL dưới dạng change types độc lập, giúp bớt phụ thuộc cú pháp SQL trực tiếp. Nhưng **mức độ hỗ trợ một change type vẫn phụ thuộc database engine**; một changeset chạy trên H2 không chứng minh nó đạt cùng semantics/locking trên PostgreSQL/MySQL.

### 9.3. Entry-point chỉ V1

**`src/test/resources/db/changelog/accounts/only-v1.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.20.xsd">

    <include file="001-create.xml"
             relativeToChangelogFile="true"/>
</databaseChangeLog>
~~~

### 9.4. Entry-point toàn bộ V1 và V2

**`src/test/resources/db/changelog/accounts/master.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.20.xsd">

    <include file="001-create.xml"
             relativeToChangelogFile="true"/>
    <include file="002-upgrade.xml"
             relativeToChangelogFile="true"/>
</databaseChangeLog>
~~~

**Vì sao hai entrypoint không gây chạy lại V1?** Cả hai `include` cùng file `001-create.xml` theo cùng đường dẫn tương đối; Liquibase lưu changeset identity, checksum và xem V1 đã áp dụng. Nếu bạn **move/rename changeset** sau khi deploy, identity có thể thay đổi; dự án thực có thể dùng `logicalFilePath`/migration policy thích hợp, nhưng không tự thay đổi tên đường dẫn cũ một cách ngẫu nhiên.

## 10. JUnit: kiểm Liquibase nâng cấp từ V1 sang V2

**`src/test/java/com/example/migration/LiquibaseUpgradeTest.java`**

~~~java
package com.example.migration;

import java.sql.Connection;
import java.util.UUID;

import javax.sql.DataSource;

import liquibase.Contexts;
import liquibase.LabelExpression;
import liquibase.Liquibase;
import liquibase.database.Database;
import liquibase.database.DatabaseFactory;
import liquibase.database.jvm.JdbcConnection;
import liquibase.resource.ClassLoaderResourceAccessor;

import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class LiquibaseUpgradeTest {

    private static final String V1 =
            "db/changelog/accounts/only-v1.xml";

    private static final String LATEST =
            "db/changelog/accounts/master.xml";

    private DataSource newDatabase() {
        String name = "liquibase_" +
                UUID.randomUUID().toString().replace("-", "");

        return new DriverManagerDataSource(
                "jdbc:h2:mem:" + name + ";DB_CLOSE_DELAY=-1",
                "sa",
                "");
    }

    private void update(DataSource source, String changelog)
            throws Exception {

        try (Connection connection = source.getConnection()) {
            Database database = DatabaseFactory.getInstance()
                    .findCorrectDatabaseImplementation(
                            new JdbcConnection(connection));

            try (Liquibase tool = new Liquibase(
                    changelog,
                    new ClassLoaderResourceAccessor(),
                    database)) {

                tool.update(new Contexts(), new LabelExpression());
            }
        }
    }

    @Test
    void upgradesV1ToV2AndPreservesHistoricalRows()
            throws Exception {

        DataSource source = newDatabase();
        JdbcTemplate jdbc = new JdbcTemplate(source);

        // Bước 1: Liquibase chỉ thực thi V1.
        update(source, V1);

        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM DATABASECHANGELOG",
                Integer.class));

        // Trước upgrade, STATUS chưa tồn tại.
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS " +
                "WHERE TABLE_NAME = ? AND COLUMN_NAME = ?",
                Integer.class, "CUSTOMER_ACCOUNTS", "STATUS"));

        // Bước 2: Dữ liệu có từ schema V1.
        jdbc.update(
                "INSERT INTO customer_accounts(id, email) " +
                "VALUES (?, ?)",
                301L, "legacy@example.test");

        // Bước 3: Cùng DB, thay entrypoint master V1 + V2.
        update(source, LATEST);

        // Bước 4: Không mất dữ liệu và backfill đúng.
        assertEquals("legacy@example.test",
                jdbc.queryForObject(
                    "SELECT email FROM customer_accounts WHERE id = ?",
                    String.class, 301L));

        assertEquals("ACTIVE",
                jdbc.queryForObject(
                    "SELECT status FROM customer_accounts WHERE id = ?",
                    String.class, 301L));

        // Bước 5: Không cho phép status NULL sau V2.
        assertThrows(DataIntegrityViolationException.class, () ->
                jdbc.update(
                    "INSERT INTO customer_accounts(id,email,status) " +
                    "VALUES (?,?,NULL)",
                    302L, "bad@example.test"));

        // Bước 6: Hai changesets được ghi nhận một lần.
        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM DATABASECHANGELOG",
                Integer.class));

        // Bước 7: Update lần nữa không làm thay đổi state.
        update(source, LATEST);

        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM DATABASECHANGELOG",
                Integer.class));
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer_accounts",
                Integer.class));
    }

    @Test
    void freshLiquibaseUpdateAppliesAllChangeSetsOnce()
            throws Exception {

        DataSource source = newDatabase();
        JdbcTemplate jdbc = new JdbcTemplate(source);

        update(source, LATEST);

        jdbc.update(
                "INSERT INTO customer_accounts(id,email) " +
                "VALUES (?,?)",
                401L, "fresh@example.test");

        assertEquals("ACTIVE",
                jdbc.queryForObject(
                    "SELECT status FROM customer_accounts WHERE id = ?",
                    String.class, 401L));

        update(source, LATEST);

        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM DATABASECHANGELOG",
                Integer.class));
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer_accounts",
                Integer.class));
    }
}
~~~

### Vì sao kiểm Liquibase bằng hai root changelogs?

Một API `update(...)` theo mặc định tiến tới latest của changelog hiện tại. Ta muốn quan sát **V1 thật** trước khi nâng sang V2 nên cung cấp entrypoint `only-v1.xml`, sau đó dùng `master.xml`. Điều quan trọng là **file V1 được include không đổi identity**.

Trong test:

- `DATABASECHANGELOG` có một row sau V1.
- Sau V2, có hai rows tương ứng hai changesets.
- `DATABASECHANGELOGLOCK` cũng được Liquibase quản lý để tránh một số cuộc chạy update đồng thời.
- Khi `update` chạy lại, không có changeset mới để áp dụng; history vẫn có hai rows.
- Việc dữ liệu ID 301 còn nguyên chứng minh backfill **không làm mất account**.
- Constraint và DEFAULT được kiểm bằng INSERT tiêu cực và tích cực.

### Chú ý đóng connection

`Liquibase` 4.x triển khai `AutoCloseable` trong API của ví dụ. Test dùng `try-with-resources` cho connection và tool để giảm rò kết nối/handle. Việc gọi API trên một H2 DataSource không pool phù hợp với lab nhỏ; trong ứng dụng thật, Boot tạo và quản lý `SpringLiquibase`/connection lifecycle cho startup.

### Contexts và labels của Liquibase

`new Contexts()` và `new LabelExpression()` trong test biểu diễn không có filter. **Không được giả định một changeset gắn `context="test"` sẽ chỉ chạy khi context test được bật**: tùy syntax/version, changesets có context có thể vẫn được chạy nếu client không cung cấp filter. Đối với changeset **chỉ được phép chạy trong test**, Liquibase hỗ trợ cú pháp bắt buộc context (ví dụ `@test`) hoặc chiến lược changelog/test profile riêng; phải kiểm rõ theo version.

Không dùng test-only changesets để chèn dữ liệu khách hàng thật vào production. Khi test cần fixture, tách source/config và kiểm tính an toàn của migration location/context.

## 11. Spring Boot startup test: tự áp dụng Flyway trước khi truy vấn

Hai class trên kiểm **API của migration tool**. Để xác minh Spring Boot thật sự tích hợp Flyway khi ApplicationContext khởi động, thêm một full context smoke test.

**`src/test/java/com/example/migration/BootFlywayStartupTest.java`**

~~~java
package com.example.migration;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = SchemaUpgradeApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.datasource.url="
            + "jdbc:h2:mem:boot_upgrade_smoke;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.flyway.locations=classpath:db/migration/flyway",
        "spring.liquibase.enabled=false",
        "spring.sql.init.mode=never"
    })
class BootFlywayStartupTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private Flyway flyway;

    @Test
    void bootAppliedMigrationsBeforeTestStarted() {
        assertEquals("2",
                flyway.info().current().getVersion().getVersion());

        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM flyway_schema_history " +
                "WHERE success = TRUE",
                Integer.class));

        // Test không tự gọi migrate(): app startup đã migrate.
        jdbc.update(
                "INSERT INTO customer_accounts(id,email) " +
                "VALUES (?,?)",
                501L, "boot@example.test");

        assertEquals("ACTIVE", jdbc.queryForObject(
                "SELECT status FROM customer_accounts WHERE id = ?",
                String.class, 501L));
    }

    @Test
    void bootKeepsFlywayHistoryOnTheActualDatabase() {
        assertTrue(flyway.info().current().getVersion()
                .getVersion().equals("2"));

        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM flyway_schema_history " +
                "WHERE success = TRUE",
                Integer.class));
    }
}
~~~

**Điểm cần nắm:** `@SpringBootTest` không có test-managed transaction mặc định, nên INSERT trong test đầu tiên được commit trên H2. Test thứ hai không dựa vào số row của business table, chỉ kiểm history để không phụ thuộc thứ tự method. Với ứng dụng thực, dùng database/schema test riêng và teardown resource để tránh dữ liệu rác.

### Có cần viết một Boot Liquibase startup test nữa?

Khi dự án chọn **Liquibase làm migration tool chính**, cần có một smoke test tương tự:

- Bật `spring.liquibase.enabled=true`.
- Tắt Flyway `spring.flyway.enabled=false`.
- Chỉ định `spring.liquibase.change-log=classpath:db/changelog/accounts/master.xml`.
- Dùng database test riêng.
- Assert `DATABASECHANGELOG` có đủ changesets và một table/column thực sự sử dụng được.

**Đây là hướng mở rộng**, không thêm làm test thứ bảy trong project mẫu để tránh hai công cụ cạnh tranh cho một schema. Cấu hình thay thế dựa trên cùng các XML files của bài và dependency `liquibase-core` phải nằm trên runtime classpath của test.

## 12. Chạy Gradle và kết quả dự kiến

Tổng bộ ví dụ:

| Test class | Số `@Test` | Mục tiêu |
| --- | ---: | --- |
| `FlywayUpgradeTest` | 2 | Nâng V1→V2, backfill, constraint, history, rerun |
| `LiquibaseUpgradeTest` | 2 | Chạy changesets V1→V2, kiểm data/history/idempotency |
| `BootFlywayStartupTest` | 2 | Flyway tự chạy trong Spring Boot startup |
| **Tổng** | **6** | Hai công cụ + integration vào Boot |

Từ project root có Wrapper, JDK 17 và các dependencies đã tải:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng:

~~~bash
./gradlew test --tests 'com.example.migration.FlywayUpgradeTest'
./gradlew test --tests 'com.example.migration.LiquibaseUpgradeTest'
./gradlew test --tests 'com.example.migration.BootFlywayStartupTest'
~~~

Kỳ vọng: **6 method pass** trong môi trường tương thích. Đây là kết quả **dự kiến từ source**, không phải tuyên bố đã thực thi Gradle/JUnit trên máy người học.

Báo cáo thường nằm ở:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.migration.FlywayUpgradeTest.xml
    ├── TEST-com.example.migration.LiquibaseUpgradeTest.xml
    └── TEST-com.example.migration.BootFlywayStartupTest.xml
~~~

Không có `System.out.println` trong project nên **không có stdout nghiệp vụ cố định**. Nếu Gradle báo `UP-TO-DATE` hoặc `FROM-CACHE`, task có thể tái sử dụng kết quả; để chẩn đoán cần thực thi mới:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu project mới chưa có Wrapper nhưng đã cài Gradle tương thích, có thể khởi tạo:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó lưu Wrapper script/JAR theo quy định của repository. Project công ty nên giữ Gradle Wrapper/JDK được CI chuẩn hóa.

### Cách đọc expected output

Khi chạy Flyway/Liquibase, log có thể ghi migrations applied, lock acquired/released và schema history. **Không hardcode nguyên văn log**: version Flyway/Liquibase, logger và dialect có thể đổi thông điệp. Những assertions đáng tin trong bài là **trạng thái database** và **migration history** được đọc sau update.

## 13. Kiểm checksum và migration drift

### Flyway

Flyway lưu lịch sử version, checksum và trạng thái áp dụng. Khi bạn thay đổi nội dung của một file `V1__...` đã chạy trên DB, `validate()` có thể báo checksum mismatch. Đây là cảnh báo quan trọng về **schema drift**.

Một test regression hữu ích:

1. Trên một database test, áp dụng V1 với file version đã phát hành.
2. Thử chạy cùng tập migration files ở branch mới.
3. Gọi `validate()`.
4. Nếu có mismatch, đánh dấu lỗi; kiểm code review/triển khai, **không tự động repair**.

`repair` có thể chỉnh metadata/history, không phải phép biến đổi làm database schema **tự tương thích** với file đã bị sửa. Nếu có migration thất bại và trạng thái không nhất quán, cần đánh giá **schema thực tế + lịch sử** trước khi quyết định có sửa history hay không.

### Liquibase

Liquibase lưu checksum cho mỗi changeset, được định danh bởi id, author và file path/logicalFilePath. Thay đổi nội dung changeset đã deploy có thể dẫn tới checksum validation failure, trừ một số cơ chế như `runOnChange`/`validCheckSum` được dùng có mục đích. Những cơ chế đó **không nên dùng để che mọi khác biệt**.

Thói quen tốt:

- Một changeset/version đã áp dụng thì **bất biến**.
- Thay đổi schema tiếp theo được tạo trong changeset/version mới.
- Tránh rename/move changelog file gây đổi identity.
- Code review migration SQL/DDL như một thay đổi production.
- CI có phép thử nâng từ version cũ đã được phát hành, không chỉ schema mới tinh.

### Vì sao checksum đúng vẫn chưa đủ?

Checksum chỉ bảo vệ sự nhất quán **định nghĩa migration đã áp dụng**. Nó không chứng minh:

- Query code mới tương thích với dữ liệu cũ.
- Constraint mới phù hợp dữ liệu production.
- Index không làm khóa bảng quá lâu.
- Migrations trước đó có data corrupt do backfill logic sai.
- Cấu hình DB production giống H2.
- Rolling deployment không làm phiên bản app cũ lỗi.

Cần kết hợp checksum validation với các assertions **data/schema/compatibility**.

## 14. Rollback, repair và DDL transactions

Không phải database nào cũng rollback DDL giống nhau.

| Vấn đề | Điều cần kiểm |
| --- | --- |
| PostgreSQL | Nhiều DDL có thể transactional; một số lệnh/kiểu CREATE INDEX có giới hạn riêng |
| MySQL | Nhiều DDL dẫn tới implicit commit, dù gọi trong transaction |
| H2 | Chỉ dùng làm demo; semantics không đại diện hoàn toàn production |
| Flyway failed migration | Có thể để lại lịch sử thất bại hoặc schema đã thay đổi một phần tùy database |
| Liquibase failed changeset | Có thể rollback transaction khi engine hỗ trợ, nhưng không phải mọi DDL/side effect đều đảo ngược được |
| Rollback application version | Không đồng nghĩa database tự rollback schema |
| `clean`/`dropAll` | Destructive; không chạy với DB production/dùng chung |
| Restore backup | Cần quy trình backup/restore và kiểm thử trước khi sự cố xảy ra |

**Đừng xem “undo” là mặc định an toàn.** Đối với thao tác mất dữ liệu như `DROP COLUMN` hoặc `TRUNCATE`, rollback SQL không thể khôi phục dữ liệu nếu không có backup/snapshot hoặc chiến lược copy trước.

Trong deployment thật, thường ưu tiên:

- **Forward-fix:** tạo migration sửa tiếp trạng thái đã triển khai.
- **Backward-compatible schema:** giữ code cũ/new hoạt động trong giai đoạn chuyển đổi.
- **Backup + tested restore:** cho tình huống cần phục hồi state trước migration.
- **Runbook:** mô tả điều kiện stop, người duyệt, metrics, các bước rollback application và restore database.

Một test chỉ green trên H2 không thay một buổi diễn tập restore.

## 15. Expand–migrate–contract trong rolling deployment

Bài demo thêm NOT NULL/default trong một V2 vì các tests không triển khai nhiều phiên bản application đồng thời. Production có nhiều instances có thể cần chia thành các releases:

**Release A — Expand**

~~~sql
ALTER TABLE customer_accounts
    ADD COLUMN status VARCHAR(16);
~~~

- Thêm cột nullable, giữ code cũ vẫn có thể INSERT.
- Code mới đọc status với fallback an toàn.
- Bắt đầu ghi status ở code mới.

**Release B — Backfill và dual-write/compatibility**

~~~sql
UPDATE customer_accounts
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Với bảng lớn, có thể cần **backfill theo batch**, checkpoint, throttling, resume sau failure và đo row counts. Câu UPDATE toàn bảng trong ví dụ không phải khuyến nghị chạy thẳng trên hàng trăm triệu rows.

**Release C — Contract sau khi các phiên bản cũ không còn cần**

~~~sql
ALTER TABLE customer_accounts
    ALTER COLUMN status SET NOT NULL;
~~~

Nếu đổi tên cột, thường cần giai đoạn đọc/ghi song song và chỉ drop cột cũ sau khi tất cả app instances đã chuyển. Tránh deploy schema “contract” trước khi code cũ dừng dùng old column.

### Test nào có thể bảo vệ từng giai đoạn?

- Test code V1 với schema đã **expand** để xác nhận backward compatibility.
- Test code V2 với schema V1 đã migrate + data backfill.
- Test old readers/new writers trong giai đoạn dual-write nếu cần.
- Test constraint sau migration trên data cũ nhiều dạng.
- Test repeat/retry của backfill.
- Integration test với database engine thật và các index có kích thước đại diện.

**Quan trọng:** Test migration và test tương thích ứng dụng là hai loại khác nhau; nên có cả hai khi downtime hoặc mixed-version deployments là rủi ro quan trọng.

## 16. Dữ liệu kiểm thử: tránh “fresh database bias”

Một fixture hữu ích không chỉ có một row sạch. Với các migration thực, hãy thử:

- **Database trống:** migrations V1→latest từ đầu.
- **Database có data lịch sử:** email/ID cũ, foreign keys, nullable legacy fields.
- **Ranh giới:** text dài nhất, số min/max, timestamp/time zone, Unicode tiếng Việt.
- **Dữ liệu đặc thù:** row cũ có giá trị null hoặc enum đã deprecated.
- **Số lượng lớn:** batch backfill, index build, connection pool, lock contention.
- **Concurrent writes:** nếu app vẫn ghi trong lúc migrate, đo tương thích/locking.
- **Nhiều tenants/schema:** migration áp dụng đủ từng schema theo runbook.
- **Failure injection:** một bước lỗi giữa migration; kiểm trạng thái, retry/restore theo engine.

Tuy nhiên không đưa dữ liệu khách hàng production không được ẩn danh vào test. Dùng dữ liệu tổng hợp hoặc bản sao được xử lý theo chính sách bảo mật. Migration test không được cấp quyền xóa hoặc viết production DB.

### Assertion mạnh và assertion yếu

**Yếu:**

~~~java
assertTrue(jdbc.queryForObject(
        "SELECT COUNT(*) FROM customer_accounts",
        Integer.class) >= 0);
~~~

Query này pass ngay cả khi bảng rỗng và account cũ bị xóa.

**Mạnh:**

~~~java
assertEquals("legacy@example.test",
        jdbc.queryForObject(
            "SELECT email FROM customer_accounts WHERE id = ?",
            String.class, 301L));

assertEquals("ACTIVE",
        jdbc.queryForObject(
            "SELECT status FROM customer_accounts WHERE id = ?",
            String.class, 301L));
~~~

Hai assertions độc lập xác nhận **data cũ được giữ** và **data mới được biến đổi đúng**. Không lấy expected từ chính migration code rồi so với kết quả của nó; fixture/test expected phải xuất phát từ business contract.

## 17. PostgreSQL Testcontainers cho migration production-like

H2 phù hợp để dạy cơ chế và kiểm migration đơn giản. Nếu production dùng PostgreSQL, hãy chạy cùng SQL/changelog trong **PostgreSQL Testcontainers**, nhất là khi migration có:

- `jsonb`, arrays, enums, UUID types, `ILIKE` hoặc SQL functions.
- Transactional DDL/locking khác H2.
- `CREATE INDEX CONCURRENTLY`, extension hoặc schemas riêng.
- Foreign key validations và row-level locks.
- Backfill chạy trên dữ liệu lớn, indexes hoặc constraints phức tạp.
- PostgreSQL-specific default expressions hoặc type conversions.

### Dependencies mở rộng với Boot 3.3

Trong project dùng Flyway:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    // Flyway 10 sử dụng module hỗ trợ PostgreSQL.
    implementation 'org.flywaydb:flyway-database-postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
~~~

Đây là snippet bổ sung vào project đã có starter/JUnit, không phải `build.gradle` hoàn chỉnh. Cần container runtime và Postgres image được phép tải/chạy.

### Một test context phù hợp

~~~java
@Testcontainers
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.flyway.locations=classpath:db/migration/flyway",
        "spring.liquibase.enabled=false"
    })
class PostgresMigrationIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired DataSource, JdbcTemplate, Flyway...
    // Assert DatabaseProductName = PostgreSQL
    // Assert actual schema, history, migrated data.
}
~~~

Đây là snippet kiến trúc, cần imports/dependencies/DDL/fixture và code assertions để compile. `@ServiceConnection` cung cấp connection details cho auto-configured DataSource khi được cấu hình đúng, nhưng **việc container start không tự chứng minh app đã dùng nó**. Luôn đọc JDBC metadata từ DataSource thực tế để xác nhận engine.

### Slice test với PostgreSQL container

Nếu dùng `@DataJpaTest` hoặc `@JdbcTest` trên **Spring Boot 3.3**, test database auto-configuration thường có thể thay DataSource bằng embedded H2. Khi muốn giữ PostgreSQL Testcontainers phải dùng:

~~~java
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
~~~

`Replace.NON_TEST` chỉ có ở Boot 3.4+, không áp dụng cho code Boot 3.3. Nếu bạn quên `Replace.NONE`, test có thể vô tình kiểm H2 và báo xanh dù native SQL Postgres không chạy được. Kiểm `getDatabaseProductName() == "PostgreSQL"` giúp phát hiện nhầm lẫn này.

### Kiểm nâng cấp V1→V2 trên container

Với database PostgreSQL mới tinh chỉ dành cho từng test:

1. Chạy **migration V1** đúng engine, dừng tại V1.
2. Insert fixture dữ liệu lịch sử.
3. Chạy V2 hoặc latest.
4. Assert data/status/constraints/history bằng JDBC trên PostgreSQL.
5. Chạy lại công cụ để kiểm idempotency/checksum.
6. Hủy container/schema test sau test suite.

Dù dùng `@SpringBootTest` hay Java API trực tiếp, **không dùng cùng một container/schema đang chia sẻ với test khác** nếu cleanup toàn bảng có thể ảnh hưởng lẫn nhau.

## 18. Những sai sót thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test migration xanh trên DB mới, deploy V1 thất bại | Không kiểm upgrade có dữ liệu cũ | Dựng V1 + seed data rồi nâng lên V2 |
| Column STATUS có nhưng toàn null | Quên backfill | Assert legacy row status và constraint |
| Migration tạo NOT NULL fail | Đặt constraint trước backfill | Expand → backfill → contract |
| Flyway không tìm thấy file | Sai `locations`/tên `V...__...sql` | Kiểm classpath và naming |
| Flyway validation checksum mismatch | Sửa versioned migration đã chạy | Tạo migration mới; không auto repair |
| Flyway chạy sai schema | DataSource/schema config sai | Kiểm JDBC metadata + schema history |
| Flyway và Liquibase tranh nhau tables | Cả hai auto enabled trên cùng DB | Chọn một tool/scope; tắt tool còn lại |
| Liquibase chạy lại changeset V1 | Thay id/author/file path | Giữ identity hoặc dùng logical path có chủ đích |
| Liquibase lock không được giải phóng | Job migration bị kill/fail | Chẩn đoán DATABASECHANGELOGLOCK; không xóa bừa |
| Test chỉ assert history count | Migration ghi metadata nhưng data sai | Assert business records + constraints |
| `migrate` lần hai gây duplicate | Migration chạy không qua history/định danh sai | Kiểm version/changeset identity |
| H2 pass, PostgreSQL fail | SQL dialect/DDL/locking khác | Testcontainers engine thật |
| Hibernate `create-drop` che lỗi | Schema do ORM dựng, không qua migrations | Dùng migration làm nguồn schema; JPA validate |
| `@Sql` seed chạy trước migration | Listener ordering hoặc schema chưa có | Sắp xếp lifecycle/fixture sau migrations |
| Test bị phụ thuộc thứ tự | Chia sẻ DB không reset | Mỗi test DB/schema riêng |
| DB production bị ALTER ngoài ý muốn | Test profile/credentials sai | CI network isolation, test-only DB allowlist |
| Repeatable Flyway chạy lại ngoài ý muốn | Checksum của R__ file thay đổi | Hiểu repeatables và dependency order |
| Liquibase context test chạy ở prod | Filter/`context` không bắt buộc đúng cách | Dùng required context/test-only changelog và CI checks |
| Backfill mất hàng giờ | Full table UPDATE/lock lớn | Batch, checkpoint, benchmark, staging |
| Rollback không khôi phục dữ liệu | DDL implicit commit/drop column | Restore/forward-fix strategy |
| Native SQL migration không portable | DB-specific syntax | Kiểm trên engine/version thật |
| Schema migration có data leak | Test fixture chứa production PII | Dữ liệu tổng hợp/ẩn danh và quyền hạn đúng |

### Quy trình chẩn đoán

1. Xác nhận **tool**, Spring Boot version và migration path.
2. Kiểm database **thực tế** mà app/tool kết nối, không chỉ properties.
3. Kiểm history table và current version/changeset identities.
4. Kiểm file versions và checksums có bị sửa sau khi deploy.
5. Chạy lại trên DB cô lập **tại V1 có data**, không chỉ DB fresh.
6. Đọc root cause SQL/DDL, bao gồm constraint/index/type error.
7. Kiểm transaction semantics và trạng thái DB sau migration fail.
8. Đối chiếu business data, schema constraints và indexes.
9. Nếu DB engine khác H2, chuyển sang Testcontainers đúng engine.
10. Không dùng `clean`/`dropAll` hoặc `repair` tự động để che lỗi không hiểu nguyên nhân.

## 19. Tiêu chí đánh giá một migration test trong CI

Một pipeline tốt thường có các lớp:

**Lớp A — Static/code review:**

- Không sửa V1/V2 đã phát hành; migration mới có version/changeset ID riêng.
- SQL/changelog parse được; không có password/URL production.
- Có ghi chú về backward compatibility và cách khắc phục khi fail.
- Thay đổi phá hủy dữ liệu phải có phương án backup/restore.

**Lớp B — Empty schema test:**

- Chạy toàn bộ migrations từ database trống.
- Bảo đảm schema cuối đủ bảng/cột/index.
- Migrations được apply một lần và validate thành công.

**Lớp C — Upgrade test:**

- Khởi động từ schema version trước thực tế.
- Seed fixture đại diện dữ liệu legacy.
- Chạy migrations mới.
- Kiểm data preservation + backfill + constraints.
- Chạy lại tool để kiểm idempotency.

**Lớp D — Production-engine test:**

- PostgreSQL/MySQL/Testcontainers đúng version lớn.
- Flyway/Liquibase dùng datasource tương ứng, không bị H2 replacement.
- Kiểm DB-specific SQL, transaction/DDL/locks.
- Khi cần, có dữ liệu đủ lớn để profiling.

**Lớp E — App compatibility:**

- Start ứng dụng mới với schema đã migrate.
- Kiểm repository/API query chính.
- Kiểm app cũ với schema expand nếu rolling deploy yêu cầu.
- Kiểm startup log, migration history, alert và ownership.

**Lớp F — Operational readiness:**

- Backup/snapshot/restore được diễn tập.
- Migration có execution-time budget và lock monitoring.
- Có người phê duyệt thay đổi destructive.
- Không cho CI truy cập production DB ngoài chính sách.

Không bắt buộc chạy các phép thử đắt nhất cho mỗi commit nếu dự án lớn, nhưng cần có **coverage upgrade thực sự** trước khi release — không chỉ test DB fresh.

## 20. Bài tập thực hành

**Bài A — thiếu backfill:** Trong bản sao test, bỏ câu `UPDATE customer_accounts SET status='ACTIVE'`. Chạy upgrade test với row V1. Phân tích vì sao migration fail tại NOT NULL hoặc row cũ không thỏa contract.

**Bài B — test quá yếu:** Tạm bỏ assertion email/ID được bảo toàn, chỉ kiểm bảng tồn tại. Thử một V2 sai có `DELETE FROM customer_accounts`. Nhận xét vì sao test yếu không bắt được mất dữ liệu.

**Bài C — idempotency:** Chạy `migrate`/`update` hai lần. Assert history vẫn có hai version/changesets, row count không đổi. Phân biệt behavior tool và SQL statement idempotency.

**Bài D — Flyway drift:** Trên database test V1 đã migrate, thay nội dung file V1 trong nhánh thử nghiệm rồi gọi `validate()`. Quan sát checksum mismatch và hoàn nguyên. Không dùng database dùng chung.

**Bài E — Liquibase identity:** Thử đổi `id` hoặc đường dẫn file changeset V1 trong một copy của lab. Phân tích vì sao tool có thể cố chạy lại `createTable` và cách quản lý `logicalFilePath` một cách có kiểm soát.

**Bài F — fixture trước và sau:** Thêm hai customers lịch sử với email Unicode và length boundary trong V1, nâng V2 rồi xác nhận tất cả vẫn tồn tại/ACTIVE.

**Bài G — NOT NULL/default:** Sau V2, thử INSERT status null và INSERT bỏ trường status. Lần thứ nhất phải bị từ chối, lần thứ hai phải lấy DEFAULT.

**Bài H — Spring Boot wiring:** Trong `BootFlywayStartupTest`, đổi `spring.flyway.locations` sang thư mục rỗng. Test phải phát hiện schema/history chưa đúng, không chỉ chờ context boot thành công.

**Bài I — tránh hai tool chạy cùng lúc:** Tạm bật Liquibase auto trong một test context khác dùng DB riêng. Kiểm và giải thích vì sao cùng schema có thể bị cả hai công cụ thay đổi; hoàn nguyên cấu hình tách biệt.

**Bài J — Testcontainers:** Chuyển Flyway V1/V2 sang PostgreSQL 16 test container. Xác minh engine, data, index, history và transaction/DDL behavior.

**Bài K — expand–contract:** Chia V2 thành ba migrations (add nullable, backfill, enforce NOT NULL). Viết test code cũ tương thích giai đoạn expand và code mới tương thích sau contract.

**Bài L — bad legacy data:** Thêm dữ liệu V1 có email/field không đáp ứng rule mới. Thiết kế migration xử lý bằng backfill/repair có kiểm soát; không xóa dữ liệu tùy tiện.

**Bài M — schema drift không do tool:** Thực hiện một ALTER thủ công trên DB test ngoài migration, sau đó chạy tests. Phân biệt history checksum consistency và actual schema consistency; thêm metadata/constraint assertions.

**Bài N — rollback/restore runbook:** Giả lập migration thất bại giữa chừng trên database sandbox, kiểm trạng thái và lập hướng forward-fix hoặc restore phù hợp DB engine. Không thí nghiệm destructive trên production.

## 21. Checklist trước khi merge migration

- [ ] Schema migration là nguồn chân lý; không để `ddl-auto=create-drop` che lỗi?
- [ ] Flyway/Liquibase được bật đúng một công cụ cho một schema?
- [ ] Migration paths/versions/changeset identities theo quy ước và không bị đổi sau deploy?
- [ ] Có test **từ DB V1 có dữ liệu** lên V2, không chỉ test DB trống?
- [ ] Có assertion bảo toàn ID/field business quan trọng?
- [ ] Backfill null/legacy data được kiểm rõ?
- [ ] NOT NULL/default/index/foreign key được kiểm khi là contract?
- [ ] Công cụ history cho biết các migrations được apply một lần?
- [ ] Chạy migration lần hai không reapply các bản đã thành công?
- [ ] Checksum drift được báo fail thay vì repair tùy tiện?
- [ ] Test dùng DB/schema riêng, tránh fixture collision và xóa dữ liệu của test khác?
- [ ] H2 chỉ được dùng khi behavior cần kiểm không phụ thuộc production dialect?
- [ ] Khi production là PostgreSQL/MySQL, có test trên đúng engine?
- [ ] `@DataJpaTest/@JdbcTest` có `Replace.NONE` nếu cần giữ Testcontainers trên Boot 3.3?
- [ ] JPA `ddl-auto=validate`/`none` phù hợp khi migration quản lý schema?
- [ ] Test-only Liquibase contexts/Flyway locations không bị chạy trong production?
- [ ] Test chứng minh Boot startup thực sự áp dụng migration trước khi query?
- [ ] Migrations tương thích rolling deploy, có expand–contract khi cần?
- [ ] Đã xác định behavior khi DDL fail/implicit commit/lock timeout?
- [ ] Có backup/restore hoặc forward-fix runbook cho thay đổi rủi ro?
- [ ] CI không có credentials/quyền destructive tới production DB?
- [ ] Log migration không in secrets/PII và có người nhận cảnh báo khi fail?
- [ ] Gradle/JUnit report cho thấy test thật sự được chạy, không chỉ task cached?

## 22. Tài liệu tham khảo

Các liên kết nên được đọc theo đúng version đang dùng. Project mẫu cố định Spring Boot 3.3.5/Java 17 và dùng Flyway/Liquibase versions do Boot BOM quản lý; API ở những major releases mới có thể thay đổi.

- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): Flyway/Liquibase auto-configuration, startup migrations và test-specific migrations.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, JDBC/JPA slices và test database replacement.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection` và connection details.
- [Flyway — Java API](https://documentation.red-gate.com/flyway/reference/usage/api-java): `Flyway.configure`, `migrate`, `validate`, `info`, `target`.
- [Flyway — Validate](https://documentation.red-gate.com/flyway/reference/commands/validate): checksum drift và migration validation.
- [Liquibase — Using XML Changelogs](https://www.liquibase.com/blog/using-xml-changelogs-liquibase): changesets, master include structure.
- [Liquibase — Include Changelogs](https://docs.liquibase.com/reference-guide/changelog-attributes/include): `include`, relative paths và changeset filename identity.
- [Liquibase — Contexts](https://docs.liquibase.com/reference-guide/changelog-attributes/what-are-contexts): context filtering, required contexts.
- [Liquibase — Core API](https://javadocs.liquibase.com/liquibase-core/liquibase/Liquibase.html): `update(Contexts, LabelExpression)` và Java API.
- [Testcontainers for Java](https://java.testcontainers.org/): database containers để kiểm migrations trên engine production.

**Ghi nhớ:** Kiểm schema migration đúng phải có **hai nhánh**: tạo database mới từ đầu **và** nâng cấp database cũ đang có dữ liệu. Với Flyway, kiểm version/history/checksum; với Liquibase, kiểm changeset identity/history/checksum. Cả hai đều cần assertions dữ liệu và constraints độc lập, chạy trên đúng engine khi SQL đặc thù, và phải có phương án rollback/restore an toàn. Một test chỉ “ứng dụng khởi động thành công trên H2” chưa đủ chứng minh nâng cấp schema production sẽ an toàn.
