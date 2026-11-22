# Thứ tự khởi tạo dữ liệu và tương tác với Hibernate

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, ứng dụng Spring Boot phối hợp HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter của Spring Integration. Các luồng ấy thường phụ thuộc vào **schema và dữ liệu nền**: bảng lưu đơn hàng, inbox chống xử lý trùng, outbox phát sự kiện, bảng checkpoint của job và các cấu hình tích hợp.

Một ứng dụng có thể chạy đúng trên H2 nhưng không khởi động được ở PostgreSQL vì **Hibernate kiểm tra bảng trước khi migration tạo bảng**, hoặc vì **data.sql chạy trước khi Hibernate tạo schema**. Nghiêm trọng hơn, bật đồng thời nhiều cơ chế sửa schema có thể làm mất dữ liệu hoặc tạo sự khác biệt khó giải thích giữa các môi trường.

Bài thuộc chương **Khởi tạo và migration** và tập trung vào **thứ tự khởi tạo dữ liệu và tương tác với Hibernate**. Mục tiêu là hiểu đúng cơ chế, chọn ai sở hữu schema, cấu hình thứ tự, xử lý lỗi, kiểm thử và quan sát trong các luồng tích hợp thực tế.

Sau bài học, bạn có thể:

- Phân biệt Boot SQL scripts, Hibernate DDL, Hibernate import.sql, Flyway và Liquibase.
- Giải thích thứ tự khởi tạo mặc định giữa schema.sql/data.sql và EntityManagerFactory.
- Dùng spring.jpa.defer-datasource-initialization đúng mục đích.
- Thiết kế chuỗi migration → Hibernate validate → ứng dụng bắt đầu nghiệp vụ.
- Nhận biết vấn đề seed trùng, schema mismatch, thứ tự bean phụ thuộc, multi-datasource.
- Kiểm thử trên database thực và tổ chức migration an toàn cho nhiều replica.

> **Nguyên tắc:** Chỉ nên có một cơ chế sở hữu việc **thay đổi schema** cho mỗi database ở một môi trường. Khởi tạo database không tự đảm bảo transaction phân tán, idempotency hay delivery từ broker.

## 1. Các cơ chế khởi tạo và quan hệ với Hibernate

| Cơ chế | Nguồn dữ liệu/định nghĩa | Vai trò | Phạm vi phù hợp |
| --- | --- | --- | --- |
| **Spring Boot SQL initialization** | schema.sql, data.sql, script theo platform | Chạy SQL lúc startup | Demo/test, seed đơn giản có chủ đích |
| **Hibernate schema generation** | Entity JPA + ddl-auto | Create, update hoặc validate schema | Tạo bảng ở dev/test; validate production |
| **Hibernate import.sql** | import.sql tại root classpath | Nạp DML khi Hibernate tạo schema | Seed demo cùng create/create-drop |
| **Flyway** | Migration V1__..., V2__... | Quản lý schema có version và history | Production |
| **Liquibase** | Changelog và changesets | Quản lý schema có version/lock | Production |

Điều quan trọng là **schema initialization** khác **data initialization**. Một công cụ tạo bảng không đồng nghĩa đã có dữ liệu nền, và một seed script không tự tạo bảng nếu nó chưa tồn tại.

~~~mermaid
flowchart TD
    A["Spring Boot startup"] --> B{"Chiến lược sở hữu schema"}
    B -->|"SQL scripts"| C["schema.sql → data.sql"]
    B -->|"Hibernate dev/test"| D["Hibernate DDL → import.sql / data.sql"]
    B -->|"Production migration"| E["Flyway hoặc Liquibase"]
    C --> F["EntityManagerFactory / JDBC"]
    D --> F
    E --> G["Hibernate ddl-auto=validate"]
    G --> F
    F --> H["Repositories / services"]
    H --> I["HTTP / cache / broker / Integration"]
~~~

Ba nhánh trên là **các chiến lược thay thế nhau**. Không hiểu sơ đồ theo nghĩa luôn chạy đồng thời cả script, Hibernate create và migration.

## 2. Những bean tham gia quá trình khởi tạo

Các thành phần liên quan gồm:

- `DataSource`: cấp JDBC connection, nhưng **không tự bảo đảm bảng đã tồn tại**.
- SQL script database initializer của Boot: xử lý vị trí và thứ tự schema/data scripts.
- `Flyway` hoặc `SpringLiquibase`: áp dụng phiên bản schema mới.
- `EntityManagerFactory`: Hibernate dựng metadata entity và thực hiện create/update/validate theo cấu hình.
- `JdbcTemplate`, JPA repository: truy vấn sau khi được tạo và bắt đầu sử dụng.
- Application services, message consumers, HTTP handlers, jobs: có thể cần dữ liệu nền trước khi xử lý.

Cách khởi động kỳ vọng trong một hệ thống production:

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant D as DataSource
    participant M as Flyway/Liquibase
    participant H as Hibernate
    participant C as Consumer / Job
    B->>D: Cấu hình connection
    B->>M: Áp dụng migration chưa chạy
    M-->>B: Schema sẵn sàng
    B->>H: Dựng EntityManagerFactory
    H->>D: Validate mapping
    H-->>B: JPA sẵn sàng
    B->>C: Khởi động xử lý nghiệp vụ
~~~

Spring Boot tự thiết lập dependency giữa nhiều initializer và JPA trong cấu hình thông thường. Với bean tùy chỉnh tự mở thread/query ở constructor hoặc nhiều DataSource, cần bảo đảm thứ tự bổ sung.

## 3. schema.sql và data.sql của Spring Boot

### 3.1. Tệp và mục đích

Các tên tài nguyên thường gặp:

~~~text
src/main/resources/
    application.yml
    schema.sql
    data.sql
~~~

`schema.sql` có thể tạo bảng:

~~~sql
CREATE TABLE integration_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value VARCHAR(500) NOT NULL
);

CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

`data.sql` nạp dữ liệu:

~~~sql
INSERT INTO integration_settings(setting_key, setting_value)
VALUES ('catalog.sync.enabled', 'true');
~~~

Đây là SQL minh họa. Kiểu dữ liệu/tên schema, từ khóa DDL và cú pháp insert có thể khác theo database. Các bảng inbox/outbox của hệ thống thật nên có migrations và ràng buộc chính xác, không chỉ dựa vào snippet.

Spring Boot nhận diện tên `schema.sql`, `data.sql` hoặc script biến thể cho platform như `schema-postgresql.sql` và `data-postgresql.sql` khi cấu hình tương ứng. Có thể đặt script tại đường dẫn riêng qua `spring.sql.init.schema-locations` và `spring.sql.init.data-locations`.

### 3.2. Các thuộc tính quan trọng

~~~yaml
spring:
  sql:
    init:
      mode: always
      encoding: UTF-8
      continue-on-error: false
~~~

| Property | Ý nghĩa |
| --- | --- |
| `spring.sql.init.mode` | Chế độ embedded, always hoặc never |
| `spring.sql.init.platform` | Chọn biến thể script theo database |
| `spring.sql.init.schema-locations` | Nơi đọc các script schema |
| `spring.sql.init.data-locations` | Nơi đọc các script seed |
| `spring.sql.init.encoding` | Encoding của script |
| `spring.sql.init.continue-on-error` | Có tiếp tục sau lỗi script hay không |

Mặc định, Boot thường chỉ tự khởi tạo script trên **embedded database** được hỗ trợ như H2, HSQLDB hoặc Derby. Muốn chạy scripts trên PostgreSQL hay MySQL bên ngoài phải bật `spring.sql.init.mode=always` có chủ đích.

**Cảnh báo:** `always` có thể chạy lại script **mỗi lần ứng dụng khởi động**. Nếu `data.sql` chèn cùng primary key, lần khởi động tiếp theo có thể gặp duplicate key. Đừng nhầm seed bằng script startup với migration có lịch sử áp dụng.

Chế độ `never` hữu ích khi schema đã được Flyway/Liquibase hoặc quy trình triển khai quản lý.

## 4. Hibernate ddl-auto và schema generation

Spring Boot truyền `spring.jpa.hibernate.ddl-auto` vào cấu hình schema management của Hibernate.

| ddl-auto | Cách Hibernate xử lý | Gợi ý |
| --- | --- | --- |
| none | Không tự tạo, sửa hay validate schema | Dùng khi có cách kiểm tra schema riêng |
| validate | Kiểm tra mapping so với schema hiện có | Production với Flyway/Liquibase |
| update | Cố gắng thay đổi schema theo entity | Chỉ phù hợp một số tình huống dev, không phải migration production |
| create | Tạo lại schema khi khởi tạo | Test/dev với DB có thể xóa |
| create-drop | Tạo khi khởi tạo và drop lúc đóng SessionFactory | Test/dev với DB tạm |

Nếu không đặt tường minh, Boot có thể chọn `create-drop` đối với embedded database được nhận diện khi không có schema manager, hoặc `none` đối với DB ngoài/đã có schema manager. Không dựa vào mặc định khi môi trường production có dữ liệu cần bảo toàn.

Ví dụ entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "integration_settings")
public class IntegrationSetting {

    @Id
    @Column(name = "setting_key", length = 100)
    private String key;

    @Column(
            name = "setting_value",
            length = 500,
            nullable = false)
    private String value;

    protected IntegrationSetting() {}

    public IntegrationSetting(String key, String value) {
        this.key = key;
        this.value = value;
    }

    public String getKey() { return key; }
    public String getValue() { return value; }
}
~~~

`@Entity` xác định kỳ vọng mapping. Nó không tự quyết định bảng do `schema.sql`, Hibernate hay Flyway tạo. Nếu ở `ddl-auto=validate` mà bảng thiếu, việc startup thất bại là dấu hiệu phù hợp: schema chưa đạt contract.

`ddl-auto=update` không cung cấp version history, kiểm soát rename/drop cột, backfill dữ liệu hay rollback theo chuẩn migration. Không thay Flyway/Liquibase bằng Hibernate update trong production.

## 5. Thứ tự mặc định: SQL scripts trước Hibernate

Trong cấu hình Spring Boot thông thường, SQL initializer chạy **trước khi** Hibernate hoàn tất khởi tạo `EntityManagerFactory`.

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant S as SQL initializer
    participant H as Hibernate
    participant A as Application
    B->>S: schema.sql
    S->>S: data.sql
    S-->>B: Scripts hoàn tất
    B->>H: EntityManagerFactory
    H->>H: none/validate/update/create
    H-->>B: JPA sẵn sàng
    B->>A: Services có thể truy cập DB
~~~

Nếu `data.sql` cần chèn vào bảng **chỉ được Hibernate tạo bởi `ddl-auto=create`**, script có thể báo `table not found`. Nếu `schema.sql` đã tạo bảng rồi Hibernate `create` tạo lại, kết quả có thể là lỗi bảng tồn tại hoặc dữ liệu seed bị xóa theo cách Hibernate xử lý.

### 5.1. Chiến lược A: script tạo schema, Hibernate chỉ validate

Với H2 và Spring Data JPA:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
}
~~~

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:integration_test;DB_CLOSE_DELAY=-1

  sql:
    init:
      mode: always

  jpa:
    hibernate:
      ddl-auto: validate
~~~

`schema.sql` tạo bảng, `data.sql` nạp dữ liệu, Hibernate xác minh mapping sau đó. **Không bật defer** trong chiến lược này; nếu Hibernate validate trước khi schema scripts chạy, nó có thể thất bại vì bảng chưa có.

### 5.2. Hai cấu hình dễ gây lỗi

**Cấu hình data.sql trước Hibernate create:**

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
  sql:
    init:
      mode: always
~~~

Khi chỉ có `data.sql`, SQL initializer có thể chạy trước khi Hibernate tạo bảng.

**Cấu hình schema.sql cùng Hibernate create:**

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create
  sql:
    init:
      mode: always
~~~

Nếu `schema.sql` cũng tạo các bảng từ entity, hai cơ chế đang cạnh tranh sở hữu DDL. Không khắc phục bằng cách bật `continue-on-error=true` và hy vọng nó tự ổn định.

## 6. spring.jpa.defer-datasource-initialization=true

Thuộc tính này điều chỉnh thứ tự của **Boot SQL script initialization so với JPA EntityManagerFactory**.

~~~yaml
spring:
  jpa:
    defer-datasource-initialization: true
~~~

Khi bật, Boot trì hoãn script initialization đến **sau khi các EntityManagerFactory liên quan được khởi tạo**. Nhờ vậy Hibernate có thể tạo bảng trước khi Boot chạy `data.sql`.

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant H as Hibernate
    participant S as SQL initializer
    B->>H: Khởi tạo EntityManagerFactory
    H->>H: ddl-auto=create-drop tạo bảng
    H-->>B: Schema tồn tại
    B->>S: Chạy schema.sql nếu có
    S->>S: Chạy data.sql
    S-->>B: Seed hoàn tất
~~~

### 6.1. Chiến lược B: Hibernate tạo schema, data.sql seed

~~~yaml
# application-dev.yml
spring:
  datasource:
    url: jdbc:h2:mem:catalog_dev;DB_CLOSE_DELAY=-1

  jpa:
    hibernate:
      ddl-auto: create-drop
    defer-datasource-initialization: true

  sql:
    init:
      mode: always
~~~

`data.sql`:

~~~sql
INSERT INTO integration_settings(setting_key, setting_value)
VALUES ('catalog.sync.enabled', 'true');

INSERT INTO integration_settings(setting_key, setting_value)
VALUES ('catalog.sync.batch-size', '100');
~~~

Ở đây **không cần schema.sql** tạo lại cùng bảng, vì Hibernate sở hữu DDL.

### 6.2. Khi defer=true không phù hợp

- `schema.sql` phải tạo bảng **trước khi Hibernate validate**.
- Flyway/Liquibase là nguồn quản lý schema production.
- Bạn muốn trì hoãn một job nghiệp vụ hay broker consumer: property này chỉ điều chỉnh **Boot SQL scripts**, không đặt lịch hay điều phối toàn ứng dụng.
- Bạn cần seed dữ liệu một lần duy nhất qua nhiều restart: defer không cung cấp versioning hoặc deduplication.

**Quy tắc nhớ:** Hibernate tạo bảng → Boot data.sql seed thì cân nhắc `defer=true`. Scripts/migrations tạo bảng → Hibernate validate thì giữ thứ tự mặc định.

## 7. import.sql của Hibernate khác data.sql

Hibernate có cơ chế đọc `import.sql` tại classpath root **khi nó tạo schema mới**, thường với `create` hoặc `create-drop`.

~~~text
src/main/resources/
    application-dev.yml
    import.sql
~~~

~~~sql
-- import.sql
INSERT INTO integration_settings(setting_key, setting_value)
VALUES ('catalog.sync.enabled', 'true');
~~~

| Đặc điểm | Hibernate import.sql | Boot data.sql |
| --- | --- | --- |
| Cơ chế thực thi | Hibernate | SQL initializer của Boot |
| Thời điểm | Sau khi Hibernate tạo schema trong chế độ phù hợp | Theo Boot SQL initialization và thứ tự dependency |
| Có chạy với ddl-auto=validate? | Không theo cơ chế import tạo schema | Có thể, nếu SQL initializer bật |
| Điều khiển bởi defer? | Không | Có |
| Có lịch sử migration? | Không | Không |

Nếu có cả `import.sql` và `data.sql` chèn cùng primary key, kết quả thường là lỗi duplicate hoặc dữ liệu seed không như mong muốn. Chọn **một cơ chế seed demo/test**.

Không để `import.sql` nạp dữ liệu thử nghiệm vô tình xuất hiện ở runtime classpath của production nơi có `ddl-auto=create`; đây là tổ hợp có nguy cơ mất dữ liệu.


## 8. Flyway quản lý schema trước Hibernate validate

Với production, một chiến lược rõ ràng là dùng **Flyway sở hữu thay đổi schema**, Hibernate chỉ kiểm tra tương thích mapping.

~~~groovy
// build.gradle (Gradle Groovy DSL), ví dụ PostgreSQL
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.flywaydb:flyway-core'

    // Các phiên bản Flyway hiện đại có module database riêng:
    implementation 'org.flywaydb:flyway-database-postgresql'

    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Để Spring Boot quản lý version của các dependencies tương thích; khi nâng major version của Flyway, kiểm tra module vendor cần thiết cho database.

~~~yaml
# application-prod.yml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

  flyway:
    enabled: true
    locations:
      - classpath:db/migration

  jpa:
    hibernate:
      ddl-auto: validate

  sql:
    init:
      mode: never
~~~

Ý nghĩa:

1. `DataSource` được tạo từ cấu hình môi trường.
2. Flyway kiểm tra history và chạy các migrations mới.
3. Hibernate tạo `EntityManagerFactory` và `validate` schema.
4. Repository/application code hoạt động trên schema đã được quản lý.

Ví dụ cấu trúc migration:

~~~text
src/main/resources/
  db/
    migration/
      V1__create_integration_tables.sql
      V2__add_source_version.sql
      V3__add_outbox_index.sql
~~~

Nội dung `V1__create_integration_tables.sql` dành cho PostgreSQL:

~~~sql
CREATE TABLE integration_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value VARCHAR(500) NOT NULL
);

CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ NULL
);
~~~

Migration tiếp theo:

~~~sql
-- V2__add_source_version.sql
ALTER TABLE outbox_events
ADD COLUMN source_version BIGINT NOT NULL DEFAULT 1;
~~~

**Không sửa tùy tiện một migration versioned đã được triển khai**, vì history/checksum có thể không còn khớp. Cần tạo migration mới và thực hiện quy trình thay đổi dữ liệu an toàn.

Các scripts ở trên dùng cú pháp PostgreSQL, không áp dụng nguyên xi cho H2 hay MySQL. Test SQL quan trọng cần chạy với cùng loại database production.

## 9. Liquibase là chiến lược thay thế

Liquibase cung cấp changelog và changeset được theo dõi qua bảng lịch sử riêng. Nếu chọn Liquibase thì không nên đồng thời để Flyway thay đổi cùng nhóm bảng.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.liquibase:liquibase-core'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml

  jpa:
    hibernate:
      ddl-auto: validate

  sql:
    init:
      mode: never
~~~

Changelog YAML minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-integration-settings
      author: integration-team
      changes:
        - createTable:
            tableName: integration_settings
            columns:
              - column:
                  name: setting_key
                  type: varchar(100)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: setting_value
                  type: varchar(500)
                  constraints:
                    nullable: false
~~~

Boot có thể sắp xếp để Liquibase hoàn thành cập nhật schema trước khi JPA dùng database trong cấu hình mặc định. Tuy nhiên nếu bạn định nghĩa custom `SpringLiquibase`, nhiều DataSource hoặc custom bean tự query DB quá sớm, vẫn cần kiểm tra dependency ordering.

### 9.1. Seed quan trọng nên có lịch sử

Nếu `integration_settings` là reference data bắt buộc ở production, có thể đưa nó vào Flyway migration/Liquibase changeSet. Ví dụ UPSERT minh họa với PostgreSQL:

~~~sql
INSERT INTO integration_settings(setting_key, setting_value)
VALUES ('catalog.sync.enabled', 'true')
ON CONFLICT (setting_key) DO NOTHING;
~~~

Nếu cấu hình do operator tự điều chỉnh sau khi triển khai, migration không nên ghi đè giá trị đó trong mỗi lần startup. Cần xác định rõ dữ liệu do code sở hữu hay do vận hành sở hữu.

## 10. Hibernate validate và thay đổi mapping

Nếu entity có field mới, ví dụ `sourceVersion` không null, và bảng hiện tại chưa có cột, Hibernate `validate` có thể báo schema mismatch:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    @Column(name = "order_id")
    private String id;

    @Column(
            name = "source_version",
            nullable = false)
    private Long sourceVersion;

    protected OrderEntity() {}
}
~~~

Migration nên thực hiện trước khi phiên bản code yêu cầu cột:

~~~sql
ALTER TABLE orders
ADD COLUMN source_version BIGINT;

UPDATE orders
SET source_version = 1
WHERE source_version IS NULL;

ALTER TABLE orders
ALTER COLUMN source_version SET NOT NULL;
~~~

Với bảng rất lớn, một lần UPDATE toàn bảng hay thêm NOT NULL có thể khóa lâu. Nên cân nhắc **expand–migrate–contract**:

1. **Expand:** thêm cột/bảng tương thích với phiên bản cũ.
2. **Deploy:** code mới có thể đọc/ghi cả cấu trúc chuyển tiếp.
3. **Backfill:** cập nhật dữ liệu cũ theo batch, có checkpoint và đo tiến độ.
4. **Contract:** xóa cấu trúc cũ sau khi mọi instance đã nâng phiên bản.
5. **Validate:** kiểm tra JPA mapping, integration queries và các consumer theo schema mới.

`ddl-auto=validate` giúp phát hiện một phần sai khác entity/schema; nó **không** xác minh đầy đủ index, business unique constraints, hiệu năng query, dữ liệu lịch sử và hợp đồng HTTP/broker. Vì vậy vẫn cần tests bổ sung.

## 11. Thứ tự khởi tạo bean phụ thuộc database

Boot nhận diện một số bean là database initializers (script initializer, Flyway, Liquibase và thành phần JPA phù hợp) để thiết lập quan hệ dependency. Nhưng một bean tùy biến có thể tự query DB trong constructor hoặc `@PostConstruct` trước khi lịch khởi tạo hoàn tất nếu không có dependency phù hợp.

Ví dụ bean đọc cấu hình sau khi schema/data được nạp:

~~~java
// IntegrationConfigWarmup.java
import org.springframework.jdbc.core.JdbcTemplate;

public class IntegrationConfigWarmup {

    public IntegrationConfigWarmup(
            JdbcTemplate jdbcTemplate) {
        jdbcTemplate.queryForList(
                "SELECT setting_key, setting_value "
                        + "FROM integration_settings");
    }
}
~~~

Khai báo dependency database initialization cho bean:

~~~java
import org.springframework.boot.sql.init.dependency.DependsOnDatabaseInitialization;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration(proxyBeanMethods = false)
public class WarmupConfiguration {

    @Bean
    @DependsOnDatabaseInitialization
    IntegrationConfigWarmup integrationConfigWarmup(
            JdbcTemplate jdbcTemplate) {
        return new IntegrationConfigWarmup(jdbcTemplate);
    }
}
~~~

`@DependsOnDatabaseInitialization` diễn đạt rằng bean này cần được tạo sau các initializers mà Boot phát hiện. Nó không buộc service ngoài (HTTP/broker) sẵn sàng, và không bảo đảm một background task ngoài Spring lifecycle sẽ tự chờ.

### @PostConstruct, ApplicationRunner và background consumers

- `@PostConstruct`: có thể truy cập DB nếu bean có dependency đúng, nhưng không phù hợp để chạy migration lớn hoặc tạo side effect có thể bị lặp.
- `ApplicationRunner`/`CommandLineRunner`: chạy sau khi context được tạo; hữu ích cho kiểm tra/warmup ngắn, **không** thay migration có history.
- Quartz jobs, Spring Integration pollers và broker listener: cần phối hợp startup/readiness để không query schema đang thay đổi.
- Bean tự tạo thread trong constructor: khó quản lý thứ tự, shutdown và retry; nên dùng cơ chế lifecycle của Spring.

Nếu cache warm-up hoặc đồng bộ HTTP là công việc có side effect, cần idempotency và checkpoint; chỉ chạy “sau migrations” chưa đủ để an toàn trên nhiều replicas.

## 12. Multi-DataSource: nhiều database cần nhiều initializer

Một ứng dụng có thể kết nối **orders DB** và **reporting DB**. `spring.datasource.*` cùng một initializer mặc định không tự đảm bảo cả hai được migration.

~~~mermaid
flowchart TD
    A["Spring Boot"] --> B["Orders DataSource"]
    A --> C["Reporting DataSource"]
    B --> D["Orders migrations"]
    C --> E["Reporting migrations"]
    D --> F["Orders EntityManagerFactory"]
    E --> G["Reporting JdbcTemplate / JPA"]
    F --> H["Use case / Integration flow"]
    G --> H
~~~

Cần:

1. Định nghĩa `DataSourceProperties`/`DataSource` riêng theo prefix.
2. Đặt bean `@Primary`/`@Qualifier` tường minh khi cần.
3. Gắn một Flyway/Liquibase/SQL initializer rõ ràng vào **mỗi datasource phù hợp**.
4. Tạo `EntityManagerFactory`/repository/transaction manager đúng nguồn.
5. Đảm bảo custom bean phụ thuộc initializer của **database nó sử dụng**.
6. Kiểm tra runtime không vô tình migrate nhầm database production sang một test database hoặc ngược lại.

Spring Boot có các cơ chế chọn datasource migration như `@FlywayDataSource` và cấu hình connection riêng; với nhiều database có thể phải tạo nhiều instances Flyway/Liquibase. Đừng đoán chỉ cần hai URL trong YAML là Boot tự tạo hai pipeline initialization.

**Giao dịch giữa DB khác nhau:** `@Transactional` với một transaction manager không tự commit atomically trên orders DB, reporting DB, Redis và broker. Có thể cần outbox, saga, event-driven synchronization hoặc reconciliation.

### R2DBC khác JDBC/Hibernate

R2DBC dùng `ConnectionFactory` và `spring.r2dbc.*`, trong khi Hibernate ORM thông thường dùng JDBC `DataSource`. Không dùng `spring.jpa.defer-datasource-initialization` làm công tắc điều khiển mọi nguồn dữ liệu reactive. Nếu dùng cả hai stack, xác định chính xác initializer và bean thuộc nguồn nào.

## 13. Seed data, idempotency và hợp đồng tích hợp

Nên phân loại dữ liệu trước khi quyết định seed:

| Dữ liệu | Ví dụ | Cách quản lý gợi ý |
| --- | --- | --- |
| Demo/test fixture | Một vài sản phẩm giả | data.sql/import.sql chỉ trong dev/test |
| Reference data có version | Loại sự kiện, mã trạng thái | Migration với ownership rõ |
| Config do operator chỉnh | Enable flag, rate limit | Config service hoặc DB quản trị |
| Business records | Orders/payments | Transaction nghiệp vụ |
| Inbox/outbox/checkpoint | Event ID, message chưa phát, cursor | SQL transaction/idempotency |
| Search/cache projection | Elasticsearch/Redis | Rebuild từ nguồn chuẩn |

**Không xóa hay reset bảng inbox/outbox lúc startup** chỉ vì muốn môi trường “sạch”, vì event có thể bị xử lý lại hoặc message chưa phát có thể mất. Migrations phải bảo tồn dữ liệu theo hợp đồng.

Một seed `INSERT ... ON CONFLICT DO NOTHING` giúp tránh insert trùng tại database, nhưng **không thay** cơ chế idempotent consumer. Để xử lý broker redelivery, cần event ID ổn định, unique constraint/claim atomically và transaction chung giữa đánh dấu event và business change.

Tương tự, việc Flyway hoàn tất migrations **không** khiến HTTP POST ra đối tác tham gia transaction SQL. Nếu ghi DB rồi gửi broker, cần cân nhắc transactional outbox và consumer idempotency.

## 14. Deploy an toàn khi có nhiều replicas

Trong rolling deployment, phiên bản cũ và mới có thể cùng dùng database. Thay schema phải xét:

- **Compatibility window:** API/repository cũ còn truy vấn field/table cũ không?
- **Lock contention:** DDL và backfill có giữ khóa lâu hay không?
- **Migration ownership:** app startup hay một migration job riêng chạy DDL?
- **Quyền:** runtime DB user có nhất thiết cần DDL quyền hay không?
- **Readiness:** application có nhận HTTP/message trước khi schema tương thích chưa?
- **Recovery:** nếu migration dở dang thì DB và lịch sử migration nằm ở trạng thái nào?
- **Observability:** thời gian migration, version áp dụng, job/consumer lag và lỗi startup.

Flyway/Liquibase có cơ chế history/locking hỗ trợ tránh nhiều tiến trình cùng áp dụng thay đổi, nhưng không tự biến một migration DDL nặng thành zero-downtime.

Cần ưu tiên migration tương thích ngược; chỉ xóa cột sau khi phiên bản cũ ngừng sử dụng. Khi cần backfill nhiều dữ liệu, dùng batch/checkpoint đo được, thay vì đặt toàn bộ logic trong `ApplicationRunner` mỗi lần deploy.

## 15. Kiểm thử thứ tự khởi tạo

### 15.1. Test SQL scripts trước Hibernate validate

Trong test với H2, đặt:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:validation_test;DB_CLOSE_DELAY=-1
  sql:
    init:
      mode: always
  jpa:
    hibernate:
      ddl-auto: validate
    defer-datasource-initialization: false
~~~

Với `schema.sql`/`data.sql` và entity tương ứng, có thể assert dữ liệu sau khi context khởi tạo:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class InitializationOrderTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void seedIsAvailableAfterStartup() {
        String value = jdbcTemplate.queryForObject(
                """
                SELECT setting_value
                FROM integration_settings
                WHERE setting_key = ?
                """,
                String.class,
                "catalog.sync.enabled");

        assertEquals("true", value);
    }
}
~~~

### 15.2. Test Hibernate create rồi data.sql

Cấu hình test riêng:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
    defer-datasource-initialization: true
  sql:
    init:
      mode: always
~~~

Với embedded database và JPA entity có bảng phù hợp, Hibernate tạo schema rồi `data.sql` nạp dữ liệu. Test cần chứng minh dữ liệu có sau startup. **Không thêm schema.sql cũng tạo lại bảng**.

### 15.3. Test migration với database production-like

Với PostgreSQL production, dùng PostgreSQL Testcontainers/test instance để kiểm tra:

- Từ database rỗng, migrations tạo đúng bảng/cột/index.
- Hibernate `ddl-auto=validate` khởi động thành công.
- Migration chạy lại không seed trùng dữ liệu.
- Unique constraint ngăn xử lý trùng `event_id`.
- Schema phiên bản cũ có thể nâng lên phiên bản mới.
- Failure của migration làm startup fail-fast, không cho consumer xử lý dữ liệu dở dang.

Skeleton:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class MigrationAgainstPostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("integration_test");

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add(
                "spring.datasource.username",
                postgres::getUsername);
        registry.add(
                "spring.datasource.password",
                postgres::getPassword);
    }

    @Test
    void migrationsFinishedBeforeApplicationUsesDatabase() {
        // Assertion thật phải query bảng, migration history và constraints.
    }
}
~~~

Đây là test skeleton, cần dependencies Testcontainers/JUnit, migration fixtures, container runtime và assertions thực. Test chỉ kiểm tra context startup mà không kiểm tra constraint/schema history thì chưa đủ.

### 15.4. @Sql của Spring Test khác Boot data.sql

`@Sql` của Spring Test nạp scripts ở thời điểm test lifecycle theo cấu hình; `data.sql` do Boot SQL initializer xử lý khi application context startup. Không dùng `@Sql` để che đi việc thứ tự initializer của production đang sai. Với test transaction rollback, phải hiểu riêng transaction mode và thời điểm `@Sql` chạy.

## 16. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| data.sql báo table not found | SQL scripts chạy trước Hibernate create | Dùng defer=true khi Hibernate tạo schema hoặc chuyển schema sang script/migration |
| Hibernate validate báo missing table | Migration/script chưa chạy hoặc sai schema/search path | Kiểm tra thứ tự và database/schema thực |
| Bảng đã tồn tại trong khi Hibernate create | schema.sql và Hibernate cùng làm DDL | Chọn một schema owner |
| Seed bị duplicate sau restart | data.sql được chạy lại | Dùng migration/UPSERT hoặc chỉ seed trong test |
| Seed biến mất | Hibernate create làm lại bảng sau khi scripts seed | Ngừng phối hợp hai nguồn DDL trái thứ tự |
| import.sql không chạy | Hibernate không ở chế độ tạo schema | Xem ddl-auto và classpath root |
| import.sql trùng data.sql | Hai nguồn seed cùng ID | Chỉ giữ một nguồn |
| Flyway checksum mismatch | Migration đã áp dụng bị sửa | Tạo migration mới, sửa history theo quy trình |
| Liquibase lock bị giữ | Chạy dở hoặc migration chưa hoàn thành | Kiểm tra trạng thái/owner và xử lý an toàn |
| Prod khác test H2 | SQL dialect, constraint, transaction khác nhau | Testcontainers cùng vendor |
| Custom bean query trước seed | Thiếu dependency vào database initialization | Dùng annotation hoặc lifecycle phù hợp |
| DB thứ hai thiếu schema | Chưa có migrator/initializer riêng | Cấu hình multi-datasource rõ |
| Consumer xử lý trước migrations | Startup asynchronous hoặc readiness sai | Chặn lifecycle và fail-fast |

Thứ tự chẩn đoán:

1. Kiểm tra URL, database schema và profile đang chạy (không in password).
2. Xác định ai sở hữu DDL và giá trị `ddl-auto`.
3. Kiểm tra `spring.sql.init.mode`, scripts và `defer-datasource-initialization`.
4. Xem stacktrace **lỗi đầu tiên** từ SQL initializer/Flyway/Liquibase/Hibernate.
5. Kiểm tra migration history, lock và quyền DDL nếu có.
6. Reproduce từ database rỗng hoặc schema version cũ bằng test cùng vendor.
7. Xác minh consumer/job không truy cập DB sớm.

**Không chữa tạm** bằng `ddl-auto=update` ở production, `create-drop`, `continue-on-error=true` hay xóa migration history. Những thao tác này có thể giấu lỗi và gây mất dữ liệu.

## 17. Checklist trước khi triển khai

- [ ] Có **một schema owner** rõ cho mỗi database: script, Hibernate dev/test hoặc migration tool.
- [ ] Đặt `ddl-auto` tường minh; production ưu tiên `validate` với schema đã migration.
- [ ] Hiểu thứ tự mặc định **schema.sql → data.sql → Hibernate**.
- [ ] Chỉ dùng `defer-datasource-initialization=true` khi muốn scripts chạy sau Hibernate tạo schema.
- [ ] Không để `import.sql` và `data.sql` seed trùng.
- [ ] Flyway/Liquibase có history, migrations được review và kiểm tra compatibility.
- [ ] Dữ liệu production không bị reset; các bảng inbox/outbox/checkpoint được bảo tồn.
- [ ] Multi-datasource có initializer và transaction manager đúng nguồn.
- [ ] Consumer, Quartz job và cache warm-up chờ schema/dữ liệu cần thiết.
- [ ] Kiểm thử từ schema rỗng và schema cũ trên database gần production.
- [ ] Có quy trình expand–migrate–contract, backfill có checkpoint và quan sát migration.
- [ ] HTTP, broker và database side effects vẫn có idempotency, transaction và retry riêng.

**Kết luận:** `spring.jpa.defer-datasource-initialization` chỉ điều chỉnh **thứ tự SQL scripts của Boot so với Hibernate**; nó không thay thế migration versioned. Với demo/test có thể để Hibernate tạo bảng rồi nạp `data.sql`. Với production, kiến trúc đáng tin cậy là **Flyway/Liquibase thay đổi schema → Hibernate validate → ứng dụng nhận công việc tích hợp**, kết hợp kiểm thử dữ liệu cũ, transaction, idempotency và observability.

## Tài liệu tham khảo

- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): scripts, Hibernate, defer initialization và schema managers.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, JPA và SQL integration.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): profile, env và property precedence.
- [Spring Framework — Executing SQL Scripts in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): @Sql và test lifecycle.
- [Hibernate ORM — Schema Generation](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#schema-generation): schema actions và import.sql.
- [Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations): versioned migrations và history.
- [Liquibase — Changelogs](https://docs.liquibase.com/concepts/changelogs/home.html): changesets và schema changes.
