# SQL dialect, schema và ranh giới của bước sinh mã jOOQ

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức tích hợp hệ thống qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration. Trọng tâm không chỉ là kết nối, mà còn là cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, idempotency, kiểm thử và quan sát những luồng tích hợp thực tế.

Ở chương **JDBC và jOOQ**, bài **SQL dialect, schema và ranh giới của bước sinh mã jOOQ** giải quyết ba câu hỏi rất hay bị trộn lẫn:

1. **SQL dialect:** jOOQ sẽ tạo SQL theo cú pháp PostgreSQL, MySQL, SQL Server hay một hệ quản trị khác?
2. **Database schema:** tables, columns, constraints, sequences, types thực tế trong cơ sở dữ liệu đến từ đâu?
3. **Code generation:** ở thời điểm nào jOOQ introspect metadata, tạo Java classes, và điều gì **không** thuộc trách nhiệm generator?

Ví dụ, một Order Service dùng PostgreSQL lưu `app.orders` cùng `app.order_outbox`. Đội phát triển thêm cột `currency`, viết Flyway migration V12 rồi chạy jOOQ generator từ một database staging còn V11. Generated `ORDERS` không có `CURRENCY` nên compile lỗi. Một người khác sinh classes từ V12 nhưng deploy vào database production chưa migrate nên SQL lỗi `column ... does not exist`. Người thứ ba dùng H2 dialect trong test dù production dùng PostgreSQL; câu SQL `ON CONFLICT` hoặc locking behavior không được xác minh đúng.

Bài này định nghĩa rõ ranh giới giữa **build-time metadata**, **runtime SQL**, **DB migration và deployment**, để tránh cả lỗi compile lẫn lỗi dữ liệu âm thầm.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt `DSLContext`, `SQLDialect`, JDBC `DataSource`, driver và database server.
2. Đọc đúng catalog, schema, `search_path`, input/output schema và runtime mapping.
3. Cấu hình Spring Boot + PostgreSQL + jOOQ và giải thích SQL được render như thế nào.
4. Phân tích dialect differences: paging, upsert, `RETURNING`, JSONB, UUID, enum, sequence, time, locking.
5. Thiết kế bước jOOQ code generation cho Maven hoặc Gradle trước `compileJava`.
6. Sử dụng Flyway/Liquibase và database metadata nhất quán để regenerate models.
7. Kiểm soát generated POJOs/records/DAOs, naming strategy, forced types và converters.
8. Xác định dependency scopes, generator classpath và quyền truy cập metadata.
9. Chẩn đoán schema drift giữa migrations, generated code và runtime database.
10. Kiểm thử bằng PostgreSQL Testcontainers, CI codegen verification, rollback và observability.

> **Nguyên tắc:** jOOQ generator đọc metadata và tạo **Java source**; nó không tự tạo schema production, không thực thi Flyway migration và không thay thế transaction manager. Generated Java compile thành công không chứng minh database runtime tương thích.

---

## 1. Sơ đồ các ranh giới trong vòng đời ứng dụng

~~~mermaid
flowchart TD
    M["Versioned migrations in Git"] --> E["Migrate isolated PostgreSQL"]
    E --> S["Database schema metadata"]
    S --> G["jOOQ Code Generation at BUILD TIME"]
    G --> J["Generated Tables / Records / Keys / POJOs"]
    J --> C["Java compilation and Boot JAR"]
    C --> R["Runtime DSLContext + SQLDialect"]
    R --> Q["Rendered SQL + JDBC bind variables"]
    Q --> D["Hikari DataSource / JDBC driver"]
    D --> P["Real PostgreSQL database"]
~~~

| Thành phần | Vai trò | Không tự làm |
| --- | --- | --- |
| SQL migrations | Tạo/đổi schema có version | Sinh Java classes |
| PostgreSQL catalog/schema | Nguồn physical metadata | Đảm bảo Java đã rebuild |
| jOOQ `org.jooq.meta` | Introspect metadata | Chạy database transaction nghiệp vụ |
| jOOQ `org.jooq.codegen` | Sinh Java source | Chạy production DDL |
| Generated `Tables`, `Keys`, `Records` | Java DSL metadata typed | Tạo bảng/column trong DB |
| jOOQ `DSLContext` | Dựng/render/execute SQL | Tự chọn đúng target DB nếu cấu hình sai |
| `SQLDialect` | Cách render SQL theo vendor | Chuyển đổi DB engine |
| Spring JDBC/Hikari | Connection pool, JDBC session | Đảm bảo SQL portable |
| Flyway/Liquibase | Nâng schema theo migration versions | Thực thi Java ORM queries |
| Spring transaction manager | Điều phối local transaction | Tự tạo distributed ACID với broker/HTTP |

### 1.1. Những từ “schema” khác nhau

- **Physical database schema**: namespace `app`, `audit`, `public` trong PostgreSQL, chứa tables/views/sequences.
- **Data contract schema**: JSON Schema, Avro, Protobuf, XSD của HTTP/broker.
- **Generated schema class**: Java representation của database metadata tại thời điểm codegen.
- **Default schema/search path**: cách tên table không fully-qualified được resolve ở runtime.
- **Schema migration version**: thứ tự DDL/data change có kiểm soát qua Flyway/Liquibase.

Không map DB generated record trực tiếp thành Kafka event chỉ vì cả hai được gọi là schema. Wire contract có version/privacy riêng.

### 1.2. jOOQ có thay JDBC không?

Không. Trong mô hình JDBC thông thường:

~~~mermaid
sequenceDiagram
    participant S as OrderService
    participant J as jOOQ DSLContext
    participant H as HikariCP
    participant D as PostgreSQL
    S->>J: select/update using generated fields
    J->>J: Render SQLDialect.POSTGRES + bind values
    J->>H: Borrow JDBC connection
    H->>D: PreparedStatement execute
    D-->>H: ResultSet / SQLSTATE
    H-->>J: JDBC results
    J-->>S: Record / DTO
~~~

Codegen chạy **trước** Java compilation; runtime dùng các generated classes đã compile. `DataSource` vẫn quyết định DB endpoint, credentials, TLS, pool và transaction. jOOQ không phải phương án tránh SQL hoặc tránh hiểu indexes/constraints.

## 2. Dependencies và version alignment

Với Spring Boot 3.x/Java 17+ và PostgreSQL, Gradle ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jooq'

    // jOOQ starter thường đã kéo JDBC infrastructure;
    // chỉ thêm starter-jdbc tường minh nếu dự án cần.
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    implementation 'org.flywaydb:flyway-core'
    // Với Flyway releases tách PostgreSQL support module:
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

Không coi mọi dependency trong ví dụ là cần thiết trong mọi project. Gradle/Spring Boot BOM có thể quản lý phiên bản jOOQ, PostgreSQL JDBC và Flyway; module database-specific của Flyway phụ thuộc release. Với Boot 4/JOOQ editions khác, kiểm tra compatibility matrix trước khi copy.

### 2.1. Generator và runtime là hai classpaths

| Artifact | Môi trường | Lý do |
| --- | --- | --- |
| `spring-boot-starter-jooq` | Runtime application | DSL/JDBC/Spring integration |
| PostgreSQL JDBC driver | Runtime application | Kết nối và execute SQL |
| `org.jooq:jooq-codegen` | Build tool | Sinh Java source |
| `org.jooq:jooq-meta` | Build tool, thường transitive | Đọc DB metadata |
| PostgreSQL JDBC driver cho generator | Build tool classpath | Mở metadata connection |
| Generated Java files | Main source set | Compile thành application |
| Flyway/Liquibase | Build/test/runtime theo pipeline | Schema migration |
| PostgreSQL Testcontainers | CI/test/build | Isolated, schema thật |
| jOOQ commercial edition | Theo license/dialect | Một số dialect/features không ở OSS |

Nếu application code không import generator types, đừng đưa `jooq-codegen` vào production runtime classpath chỉ để IDE nhận generated classes.

### 2.2. SQLDialect hỗ trợ theo edition/version

`SQLDialect.POSTGRES` là dialect phổ biến khi target PostgreSQL. Các dialect khác nhau có thể được hỗ trợ ở OSS hoặc commercial distribution và mức hỗ trợ thay đổi qua jOOQ releases. Không giả định mọi database nằm trong enum của bản OSS hoặc mọi vendor feature được dịch tự động.

Generator version, runtime jOOQ version và metadata modules nên đồng bộ, tránh generated source gọi method/class không tồn tại ở runtime. Khi nâng jOOQ major/minor, kiểm tra generated diff và compile/integration tests.

## 3. Spring Boot runtime cấu hình DataSource và SQL dialect

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://orders-db.internal.example:5432/orders?sslmode=verify-full
    username: ${ORDERS_DB_USER}
    password: ${ORDERS_DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      connection-timeout: 3000
  jooq:
    sql-dialect: POSTGRES
~~~

- `spring.datasource.*`: endpoint, authentication, TLS, driver và pool.
- `spring.jooq.sql-dialect`: chỉ định SQL rendering dialect trong các Boot versions hỗ trợ property này.
- Spring Boot thường auto-configure `DSLContext` từ `DataSource` khi dependency/bean conditions phù hợp.
- `SQLDialect.POSTGRES` **không** tự đổi MySQL database thành PostgreSQL.
- Nếu không cấu hình, Boot có thể detect dialect dựa JDBC metadata ở những database được hỗ trợ; dự án nhiều datasources/proxy cần đặt tường minh và verify.

### 3.1. DSLContext ở runtime

~~~java
import org.jooq.DSLContext;
import org.springframework.stereotype.Repository;
import static com.example.db.jooq.tables.Orders.ORDERS;

@Repository
public class OrderQueryRepository {

    private final DSLContext dsl;

    public OrderQueryRepository(DSLContext dsl) {
        this.dsl = dsl;
    }

    public OrderSummary findById(long id) {
        return dsl.select(
                        ORDERS.ID,
                        ORDERS.ORDER_ID,
                        ORDERS.ORDER_STATUS,
                        ORDERS.AMOUNT_MINOR)
                .from(ORDERS)
                .where(ORDERS.ID.eq(id))
                .fetchOne(r -> new OrderSummary(
                        r.get(ORDERS.ID),
                        r.get(ORDERS.ORDER_ID),
                        r.get(ORDERS.ORDER_STATUS),
                        r.get(ORDERS.AMOUNT_MINOR)));
    }
}
~~~

`OrderSummary` là DTO ứng dụng, generated `Orders` và field names phụ thuộc codegen target/config. `fetchOne` có thể trả `null` nếu không có hàng; API adapter nên quy định not-found rõ. Đừng dựa vào Java import path trong ví dụ khi project tự dùng custom naming strategy.

### 3.2. Render SQL không cần execute

~~~java
String rendered = dsl
        .select(ORDERS.ID)
        .from(ORDERS)
        .where(ORDERS.ORDER_STATUS.eq("CONFIRMED"))
        .getSQL();
~~~

`getSQL()` dựng SQL theo dialect/settings, có thể chứa bind markers theo cấu hình. Nó không xác minh cột có tồn tại trong production DB, không check GRANT và không chạy query planner.

Nếu chỉ cần render offline:

~~~java
import org.jooq.DSLContext;
import org.jooq.SQLDialect;
import org.jooq.impl.DSL;

DSLContext renderer = DSL.using(SQLDialect.POSTGRES);
~~~

Đây là renderer không có JDBC connection. Đừng đăng ký nó đè lên Spring Boot runtime bean rồi mong code thực thi queries được.

### 3.3. Multiple datasources

Một integration service có thể ghi `orders` database và đọc `reporting` database:

~~~text
orderDataSource     -> orderDslContext     -> OrderTransactionManager
reportDataSource    -> reportDslContext    -> ReportTransactionManager
~~~

Nếu hai sources dùng dialect/schema khác nhau, phải tạo `DSLContext`/`ConnectionProvider`/transaction manager tương ứng, inject bằng `@Qualifier`, và test routing. Boot tự cấu hình thường tối ưu cho **một primary datasource**; nhiều nguồn cần cấu hình rõ. Transaction của DataSource A không tự bao phủ DataSource B.

## 4. Dialect khác nhau ở đâu?

| Feature | PostgreSQL | DB khác có thể dùng | Rủi ro nếu hardcode |
| --- | --- | --- | --- |
| Pagination | `LIMIT ... OFFSET` | `FETCH FIRST`, `OFFSET ... FETCH`, `ROWNUM` | Syntax/cost/ordering |
| Upsert | `ON CONFLICT` | `ON DUPLICATE KEY`, `MERGE` | Concurrency/conflict semantics |
| Generated values | `RETURNING` | `OUTPUT`, JDBC generated keys | Thêm round trip/result behavior |
| JSON | `JSONB`, `@>` | JSON functions/operators khác | Type/index semantics |
| UUID | Native UUID | CHAR/BINARY/vendor type | Java converter mismatch |
| Arrays | PostgreSQL ARRAY | JSON/string/separate tables | Type semantics |
| Temporal | `TIMESTAMPTZ`, interval | Vendor date/time types | Timezone/precision |
| Locks | `FOR UPDATE SKIP LOCKED` | Hints/other clauses | Outbox claim semantics |
| Identity | `GENERATED ... AS IDENTITY` | AUTO_INCREMENT/sequence | Generated keys |
| Name quoting | Double quote, folding | Backtick/brackets | Case/reserved keywords |
| Schema/catalog | PostgreSQL schemas | Vendor-specific namespaces | Wrong physical object |
| Boolean | Native boolean | Number/bit/custom | Converter issues |

jOOQ DSL có thể chuyển nhiều constructs sang vendor SQL, nhưng **không bảo đảm portable semantics**. Phải chạy integration tests trên DB thực tế.

### 4.1. Pagination cần ORDER BY ổn định

~~~java
var page = dsl.select(ORDERS.ID, ORDERS.CREATED_AT)
        .from(ORDERS)
        .where(ORDERS.ORDER_STATUS.eq("CONFIRMED"))
        .orderBy(ORDERS.CREATED_AT.desc(), ORDERS.ID.desc())
        .limit(50)
        .offset(100)
        .fetch();
~~~

Không có deterministic `ORDER BY`, các trang có thể thiếu/trùng. `OFFSET` lớn cũng tốn chi phí. Với outbox/projection throughput cao, cân nhắc keyset paging theo `(created_at, id)` cùng consistency rules.

### 4.2. Upsert và idempotent inbox

PostgreSQL SQL:

~~~sql
INSERT INTO app.processed_events(consumer_name, event_id, processed_at)
VALUES ('inventory', 'E-100', CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Đây là PostgreSQL-specific syntax. MySQL và SQL Server có variants khác; không suy logic race/transaction identical chỉ vì jOOQ có API cho upsert.

jOOQ shape minh họa:

~~~java
dsl.insertInto(PROCESSED_EVENTS)
        .set(PROCESSED_EVENTS.CONSUMER_NAME, "inventory")
        .set(PROCESSED_EVENTS.EVENT_ID, eventId)
        .set(PROCESSED_EVENTS.PROCESSED_AT,
                java.time.OffsetDateTime.now())
        .onConflict(
                PROCESSED_EVENTS.CONSUMER_NAME,
                PROCESSED_EVENTS.EVENT_ID)
        .doNothing()
        .execute();
~~~

Đoạn này giả định generated field types tương ứng; nếu `EVENT_ID` trong DB là UUID, Java `eventId` phải `UUID`, không phải String. Check generated signature/driver trước khi copy.

### 4.3. RETURNING và generated keys

~~~sql
INSERT INTO app.orders(order_id, order_status, amount_minor, currency)
VALUES ('ORD-100', 'NEW', 150000, 'VND')
RETURNING id, created_at;
~~~

~~~java
var inserted = dsl.insertInto(ORDERS)
        .set(ORDERS.ORDER_ID, "ORD-100")
        .set(ORDERS.ORDER_STATUS, "NEW")
        .set(ORDERS.AMOUNT_MINOR, 150000L)
        .set(ORDERS.CURRENCY, "VND")
        .returning(ORDERS.ID, ORDERS.CREATED_AT)
        .fetchOne();
~~~

`returning()` support và emulation khác theo database/dialect/version. Nếu caller cần `id` hoặc timestamp làm receipt, test PostgreSQL round trip thực thay vì chỉ assert SQL string.

### 4.4. JSONB, UUID và vendor types

~~~sql
SELECT order_id
FROM app.orders
WHERE metadata @> '{"source":"mobile"}'::jsonb;
~~~

`@>` là PostgreSQL JSONB containment. Index GIN và JSONB semantics thuộc PostgreSQL, không tự chuyển portable thành MySQL JSON path. jOOQ JSON/JSONB wrappers, converters và binding support còn tùy version. **Không nối raw JSON request vào SQL string**; bind tham số bằng DSL/PreparedStatement.

### 4.5. Locking của outbox

~~~sql
SELECT id, event_id, payload
FROM app.order_outbox
WHERE status = 'NEW'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

Nếu relay dùng nhiều workers, lock/query phải nằm trong transaction phù hợp. `SKIP LOCKED` giúp tránh contention chứ không bảo đảm exactly-once publish: worker có thể publish thành công rồi crash trước khi đánh dấu outbox sent, gây replay. Consumer cần dedupe stable `eventId`.

### 4.6. SQLDialect.DEFAULT không là “portable mode”

`SQLDialect.DEFAULT` có những use cases rendering generic, nhưng không làm mọi SQL chạy như nhau trên mọi DB. Khi production là PostgreSQL, nên chọn PostgreSQL dialect và test PostgreSQL-specific behavior; H2 compatibility mode không xác nhận JSONB, locking, sequences, optimizer và transaction isolation.

## 5. Catalog, schema, search_path và generated names

Trong PostgreSQL:

~~~text
database orders
  schema app
    orders
    order_outbox
    processed_events
  schema audit
    integration_events
  schema public
    extensions ...
~~~

### 5.1. SQL name resolution

~~~sql
SELECT current_database(), current_schema(), current_user;
SHOW search_path;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('app', 'audit')
ORDER BY table_schema, table_name;
~~~

Unqualified `SELECT * FROM orders` có thể resolve theo `search_path`; `SELECT * FROM app.orders` định danh schema rõ. jOOQ có schema qualification và mapping settings, nhưng database runtime connection/search_path vẫn quan trọng.

### 5.2. Generator inputSchema và outputSchema

- `inputSchema`: schema nguồn generator introspect.
- `outputSchema`: schema được đại diện trong generated model khi cấu hình mapping, **không phải filesystem output directory**.
- `inputCatalog`/`outputCatalog`: catalog mapping trên những DB hỗ trợ.
- `schemata`: nhiều source schema mappings.
- `target.directory`: thư mục code được sinh ra trên disk.
- `target.packageName`: Java package root.

Không lấy `target.directory=build/generated-src/jooq` làm bằng chứng runtime DB có schema `jooq`.

### 5.3. Những cấu hình sai phổ biến

| Config lỗi | Kết quả |
| --- | --- |
| Flyway migrate `app`, generator đọc `public` | Thiếu tables/columns |
| Generator đọc `orders_test`, runtime tới `orders_prod` version cũ | Runtime SQL error |
| Runtime user thiếu `USAGE` schema | Login OK, query denied |
| `renderSchema(false)` khi search_path sai | Query resolve wrong table |
| Một table `orders` ở nhiều schemas | Import/generated class nhầm |
| DB tenant isolation dựa hoàn toàn `search_path` | Có thể đọc sai tenant nếu role privileges quá rộng |

### 5.4. Multi-tenant schema mapping

Có thể generate Java từ reference schema rồi map runtime schema theo tenant. Nhưng runtime mapping phải đi cùng domain authorization và DB grants/RLS; không tin một `tenantId` từ HTTP header làm principal. Schema mapping là cách render tên, không phải cơ chế security isolation.

## 6. jOOQ code generation: sinh gì và không sinh gì?

Generator có thể tạo:

- Java classes cho schemas/tables/fields.
- `Keys` metadata cho primary/foreign/unique keys.
- `Record`/`UpdatableRecord` classes.
- POJOs/interfaces/DAOs theo cấu hình.
- Enum/sequence/routine/UDT mappings theo database/version/edition.
- Custom forced types và converters.

Generator **không**:

- Chạy Flyway/Liquibase ở production.
- Tạo bảng/cột/index/role lúc Spring Boot startup.
- Backfill dữ liệu khi đổi column type.
- Tự deploy schema migrations.
- Bảo đảm compiled Java model khớp schema runtime.
- Đảm bảo CRUD hay `@Transactional` atomic với Kafka/HTTP.
- Thay thế constraints/unique keys trong database.

### 6.1. Quy trình chuẩn

~~~mermaid
flowchart LR
    M["Migration files in Git"] --> P["Create isolated PostgreSQL"]
    P --> F["Apply Flyway/Liquibase"]
    F --> G["jOOQ generator introspects metadata"]
    G --> J["Generated Java sources"]
    J --> C["compileJava"]
    C --> T["Integration tests"]
    T --> B["Boot JAR"]
~~~

Chỉ Java source được đưa vào compilation/application. Generator không cần chạy khi production pod được tạo nếu build artifact đã chứa compiled classes.

### 6.2. Các metadata sources

| Nguồn | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| PostgreSQL Testcontainers đã migrate | CI, developer, high fidelity | Container startup |
| PostgreSQL ephemeral database | Build pipelines có DB isolated | Provisioning/version drift |
| Local PostgreSQL từ migrations | Dev nhanh | Dữ liệu cũ/migrations chưa chạy |
| Shared staging DB | Tạm thời nếu có kiểm soát | Drift/race/change control |
| Production DB | Không khuyến nghị | Secrets và nondeterministic metadata |
| DDL parser (`DDLDatabase` khi version hỗ trợ) | Build không cần live DB | Không full vendor metadata parity |

Nếu migration có PostgreSQL-specific features, Testcontainers PostgreSQL thường đáng tin hơn H2. Nếu dùng DDLDatabase, cần chứng minh generator hiểu DDL dialect/constraints/extension objects.

### 6.3. Một schema ví dụ

~~~sql
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE app.orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id VARCHAR(120) NOT NULL UNIQUE,
    order_status VARCHAR(24) NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE app.order_outbox (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    order_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES app.orders(order_id)
);

CREATE INDEX idx_outbox_pending
    ON app.order_outbox(status, created_at, id)
    WHERE status = 'NEW';
~~~

Đây là **DDL minh họa cho migration nguồn**, không phải lời khuyên thực thi tự động trong application startup. PostgreSQL cần `pg_hba`/roles/grants phù hợp; generator read-only introspection khác user runtime DB.

### 6.4. Output Java chỉ là một snapshot

~~~text
com.example.db.jooq
    Tables.java
    Keys.java
    tables/Orders.java
    tables/OrderOutbox.java
    tables/records/OrdersRecord.java
~~~

Cây trên minh họa, package/subdirectories phụ thuộc generator config/version. Không sửa generated classes bằng tay; migration schema trước, regenerate rồi review diff.

 
## 7. Maven code generation: build plugin và schema metadata

jOOQ có Maven plugin `org.jooq:jooq-codegen-maven`. Cấu hình minh họa dưới đây giả định PostgreSQL **đã được provision và migrate trước** khi Maven đi qua phase `generate-sources`.

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.jooq</groupId>
      <artifactId>jooq-codegen-maven</artifactId>
      <version>${jooq.version}</version>
      <executions>
        <execution>
          <id>generate-jooq</id>
          <phase>generate-sources</phase>
          <goals><goal>generate</goal></goals>
        </execution>
      </executions>
      <dependencies>
        <dependency>
          <groupId>org.postgresql</groupId>
          <artifactId>postgresql</artifactId>
          <version>${postgresql.version}</version>
        </dependency>
      </dependencies>
      <configuration>
        <jdbc>
          <driver>org.postgresql.Driver</driver>
          <url>${jooq.codegen.jdbc.url}</url>
          <user>${jooq.codegen.jdbc.user}</user>
          <password>${jooq.codegen.jdbc.password}</password>
        </jdbc>
        <generator>
          <name>org.jooq.codegen.JavaGenerator</name>
          <database>
            <name>org.jooq.meta.postgres.PostgresDatabase</name>
            <inputSchema>app</inputSchema>
            <includes>orders|order_outbox</includes>
            <excludes>flyway_schema_history</excludes>
          </database>
          <generate>
            <records>true</records>
            <pojos>true</pojos>
            <daos>false</daos>
          </generate>
          <target>
            <packageName>com.example.db.jooq</packageName>
            <directory>${project.build.directory}/generated-sources/jooq</directory>
          </target>
        </generator>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Đây là **một fragment minh họa**, không phải `pom.xml` hoàn chỉnh:

- `${jooq.version}`, `${postgresql.version}` và `${jooq.codegen.jdbc.*}` phải được cung cấp bởi BOM/build settings/CI secret. Không commit mật khẩu.
- Generator phiên bản X phải tương thích với runtime jOOQ phiên bản Y. Khóa version theo matrix của project.
- Plugin có **classloader/dependencies riêng**; JDBC driver ở application `runtime` không mặc nhiên có trong plugin realm.
- `inputSchema=app` là schema nguồn trong PostgreSQL, không phải Java package hay runtime `search_path`.
- `includes/excludes` lọc metadata theo generator regex matching; không phải SQL `LIKE`.
- Credentials nên là codegen-only identity trong ephemeral database.
- Nếu custom converters/forced types, generator output phải compile được khi các converter classes có mặt.
- `phase=generate-sources` không tự chạy Flyway trước plugin, trừ khi build pipeline đã orchestration rõ.

### 7.1. Phase ordering

~~~text
CI:
  provision PostgreSQL isolated
  apply Flyway/Liquibase migrations
  mvn generate-sources
    jOOQ codegen introspects migrated PostgreSQL
  mvn compile
  mvn test / integration tests
  package and deploy
~~~

Một application có `spring.flyway.enabled=true` chạy migration khi context khởi tạo **không có nghĩa** Maven generator biết đợi cho application startup. Phải có bước migration trước codegen ở build.

### 7.2. Metadata privilege không đồng nghĩa DML privilege

Generator cần xem metadata đúng schema, không phải cập nhật bảng nghiệp vụ production. Một DB role dùng để introspect PostgreSQL có thể cần `USAGE` schema và quyền đọc metadata/objects liên quan theo version; không dùng `SUPERUSER` hoặc runtime DML credentials vô điều kiện.

### 7.3. Khi không thể mở DB trong build

Có thể dùng jOOQ DDL-based metadata (`DDLDatabase` hoặc jOOQ-meta extensions theo version), metadata snapshot hoặc commit generated output đã được CI verify. Nhưng SQL parser có thể không hiểu đầy đủ PostgreSQL extensions, routines, partial indexes hoặc types; phải kiểm lại bằng PostgreSQL integration tests.

## 8. Gradle generator: classpath khác runtime

Một cách minh họa không phụ thuộc community plugin cụ thể là tạo `JavaExec` task:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<supported-boot-version>'
}

configurations {
    jooqGenerator
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jooq'
    runtimeOnly 'org.postgresql:postgresql'

    jooqGenerator "org.jooq:jooq-codegen:${jooqVersion}"
    jooqGenerator "org.postgresql:postgresql:${postgresqlVersion}"
}

def generatedDir = layout.buildDirectory.dir('generated-src/jooq')

tasks.register('generateJooq', JavaExec) {
    group = 'code generation'
    description = 'Generate jOOQ sources from migrated schema'
    classpath = configurations.jooqGenerator
    mainClass = 'org.jooq.codegen.GenerationTool'

    args 'src/main/jooq/jooq-config.xml'

    inputs.file('src/main/jooq/jooq-config.xml')
    outputs.dir(generatedDir)
}

sourceSets {
    main {
        java {
            srcDir generatedDir
        }
    }
}

tasks.named('compileJava') {
    dependsOn 'generateJooq'
}
~~~

Ví dụ có các assumptions cần hoàn thiện trước khi áp dụng:

1. `jooqVersion`/`postgresqlVersion` là project properties được pin và tương thích.
2. XML config có target directory `build/generated-src/jooq` và connect metadata source đúng.
3. Build phải provision + migrate DB trước task `generateJooq`.
4. Nếu source import types của Postgres codegen extensions, thêm generator dependencies thích hợp.
5. Không chạy task trên production pod; source được compile trước deploy.
6. Đường dẫn source, task output/inputs và multi-module dependencies phải được kiểm tra.

### 8.1. Caching/incremental build rủi ro

Nếu Gradle chỉ quan sát file XML mà không biết **migrations/DB metadata** đã đổi, nó có thể đánh dấu task `UP-TO-DATE` và giữ generated files cũ. Cần model input gồm migration scripts/schema artifact hoặc buộc regenerate ở CI verification. Đừng lấy một green Gradle incremental build làm bằng chứng codegen đã đồng bộ DB.

### 8.2. Official/community Gradle jOOQ plugins

Có official jOOQ Gradle codegen support ở các version phù hợp và những community plugins được dùng trong các dự án. Các DSL/task names/edition settings **không giống nhau**. Chọn một plugin, đọc docs đúng release và đồng bộ dependency BOM; không copy trộn cấu hình `nu.studer.jooq` với `org.jooq.jooq-codegen` mà không kiểm chứng.

### 8.3. Runtime không mở generator connection

~~~text
generateJooq (build-time):
   generator JDBC metadata source -> .java files

compileJava:
   .java -> classes inside application artifact

bootRun (runtime):
   Hikari DataSource -> JDBC query via DSLContext
~~~

Một application runtime vẫn cần credentials để query PostgreSQL, nhưng đó là **runtime DB role**, không phải tài khoản generate source. Tách secrets giúp giảm blast radius.

## 9. Cấu hình target package, inputSchema, naming và generate flags

Generator fragment:

~~~xml
<generator>
  <name>org.jooq.codegen.JavaGenerator</name>
  <database>
    <name>org.jooq.meta.postgres.PostgresDatabase</name>
    <inputSchema>app</inputSchema>
    <includes>orders|order_outbox</includes>
  </database>
  <generate>
    <records>true</records>
    <pojos>true</pojos>
    <daos>false</daos>
    <javaTimeTypes>true</javaTimeTypes>
  </generate>
  <target>
    <packageName>com.example.db.jooq</packageName>
    <directory>build/generated-src/jooq</directory>
  </target>
</generator>
~~~

Các flags/XML options có thể khác theo jOOQ major/minor; kiểm tra XML schema/documentation của version đang dùng.

### 9.1. `target.directory` không phải database schema

- `target.directory`: filesystem path sinh `.java` files.
- `target.packageName`: package Java root.
- `inputSchema`: namespace database nguồn generator đọc.
- `outputSchema`: nếu mapping, schema được đại diện trong generated metadata.
- `outputSchemaToDefault`: nếu supported, điều khiển schema qualification.
- `inputCatalog`/`outputCatalog`: catalog mapping khi dialect/database hỗ trợ.

Đặt `target.directory=build/generated-src/jooq` **không tạo** PostgreSQL schema `jooq`.

### 9.2. Generated names và naming strategy

Table SQL `order_outbox` thường có class `OrderOutbox`; column `event_id` trở thành constant `EVENT_ID`. Exact generated layout tùy naming strategy và jOOQ version. Khi đổi Java naming strategy, compile imports có thể đổi hàng loạt dù DB physical names không đổi.

Không sửa `Orders.java` để đổi `order_status` thành `status`; nếu muốn rename SQL column, phải thiết kế migration/compatibility. Nếu chỉ đổi Java-facing API, dùng custom naming strategy/mapping có review và test.

### 9.3. Records, POJOs và DAOs

| Generated artifact | Khi hữu ích | Cần lưu ý |
| --- | --- | --- |
| Table/Field objects | Type-safe SQL DSL | Reflect build-time snapshot |
| Records | Read/write row values | Không phải JPA entity session |
| `Keys` | PK/FK/unique metadata | Không tạo constraint mới |
| POJOs | Repository mapping | Không expose nguyên wire contract |
| DAOs | CRUD tiện lợi | Không thay custom SQL/transaction |
| Enum types | Domain/DB enum mapping | New enum value có thể phá reader cũ |
| Routines/sequences | Vendor-specific objects | Privilege/version/edition |

Chỉ sinh những artifacts thực sự dùng. Một service tập trung SQL DSL/outbox có thể không cần DAOs, vì atomic idempotency và claim cần custom SQL.

### 9.4. Codegen không nên in secrets ra logs

Generator có thể log JDBC URL, metadata, config nếu debug sai. Inject user/password qua secret management trong build, tránh in plugin config hoặc `--debug` logs không được redaction. Generator không nên kết nối production DB.

## 10. Forced types, converters và semantic types

jOOQ có thể map SQL column types thành Java types mặc định hoặc tùy biến thông qua `forcedTypes`, converters/bindings và naming rules.

### 10.1. Type mapping cần xác nhận trên generated source

| PostgreSQL | Java/jOOQ thường gặp | Test cần có |
| --- | --- | --- |
| `BIGINT` | `Long` | Overflow/nullable |
| `INTEGER` | `Integer` | Absent/null vs zero |
| `UUID` | `java.util.UUID` | Stable identity, serializing |
| `TIMESTAMPTZ` | `OffsetDateTime` theo version/config | Offset/instant semantics |
| `TIMESTAMP` | `LocalDateTime` | Timezone assumptions |
| `JSONB` | `org.jooq.JSONB` hoặc converter | Schema version/parsing |
| `NUMERIC(p,s)` | `BigDecimal` | Scale/precision |
| `CHAR(3)` | `String` | Padding and currency ISO semantics |
| PostgreSQL ENUM | Generated enum/user type | Compatibility on new values |
| ARRAY | Arrays/list binding tùy driver | Element type and portability |

Đừng đoán generated `ORDERS.AMOUNT_MINOR` là `Long` nếu generator có custom forced type hoặc source DB khác. Đọc actual class signature và kiểm test round-trip với PostgreSQL.

### 10.2. Converter classes là runtime dependency

Giả sử SQL `CHAR(3)` cần map thành `CurrencyCode` value object. Nếu generated field dùng converter riêng, class `CurrencyCodeConverter` phải có mặt khi code compile/runtime. Generator có thể chỉ sinh **tham chiếu** tới converter, không tự viết business converter cho bạn.

### 10.3. Nullability trong Java và SQL

`NOT NULL`, default, generated values và `CHECK` constraints thuộc database. Java record/POJO nullability annotations chỉ giúp static analysis hoặc validation theo policy, không thay DB constraint. Với rolling deployments, thêm một column `NOT NULL` ngay có thể phá writer cũ, dù new generated Java compile xanh.

### 10.4. DATE/TIMESTAMP và money

Đổi `TIMESTAMP` sang `TIMESTAMPTZ` có thể thay ý nghĩa timezone của dữ liệu lịch sử. Đổi `amount_minor INTEGER` sang `BIGINT` có thể làm generated Java signature từ `Integer` sang `Long`. Đây là compile-time warning hữu ích nhưng **không thay backfill, data migration hoặc API contract review**.

### 10.5. Database extension types

PostgreSQL `citext`, arrays, custom domains, user enums hoặc PostGIS có metadata/codec requirements khác. Có thể cần extensions, jOOQ commercial edition hoặc forced converters; kiểm tra exact jOOQ/driver support trước khi dùng, không giả định `SQLDialect.POSTGRES` xử lý mọi extension.

 
## 11. Schema drift giữa migrations, generated source và runtime database

Một quy trình tích hợp có ít nhất **bốn trạng thái** cần đồng bộ:

~~~text
Migration scripts in Git (V12)
  -> Metadata DB used by generator (V12?)
  -> Generated Java source (V12?)
  -> Deployed runtime DB (V12?)
~~~

Chỉ một dấu hỏi sai có thể tạo lỗi compile, query hoặc xử lý dữ liệu. Chạy generator thành công trên staging DB chưa phải bằng chứng production có cùng schema.

### 11.1. Các dạng drift

| Drift | Dấu hiệu | Hành động |
| --- | --- | --- |
| Migration mới nhưng generated code cũ | Java thiếu `ORDERS.CURRENCY` | Regenerate từ DB đã migrate |
| Generated code v12 nhưng production DB v11 | SQLSTATE `42703` undefined column | Apply migration đúng thứ tự |
| DB drop column, Java cũ vẫn tham chiếu | SQL error sau deploy | Expand–migrate–contract |
| Generator trỏ `public`, migration nằm `app` | Generated tables thiếu/sai | Chỉnh `inputSchema` |
| Generator trỏ DB có manual schema drift | Codegen diff nondeterministic | Fresh PostgreSQL + migrations |
| `SQLDialect` không đúng runtime DB | Syntax/type/SQL emulation khác | Fix dialect/driver |
| Codegen và jOOQ runtime versions lệch | Compiler/linkage errors | Pin compatible versions |
| Converter không theo kịp SQL type | Decode/mapper exception | Rebuild forced types/converters |
| Application dùng sai `DSLContext` | Query qua datasource khác | Qualifier/transaction tests |
| Runtime user thiếu privilege | SQLSTATE `42501` | GRANT theo least privilege |

### 11.2. Flyway/Liquibase source of truth

Chọn nhất quán:

- Versioned SQL migrations trong Git điều khiển tiến hóa physical schema.
- Codegen chạy **sau** khi áp migrations lên isolated PostgreSQL.
- Generated classes được tái tạo, không sửa tay.
- Runtime database có migration history/check trước khi traffic chuyển sang code dùng schema mới.
- Database migrations và application rollout có compatibility window cho old pods, batch jobs và downstream readers.

Nếu dự án chọn một schema-first workflow khác, phải document rõ nguồn canonical, build artifact và migration discipline tương ứng. Không để cả hand-edited generated Java lẫn manual SQL patches tranh quyền “source of truth”.

### 11.3. Commit generated source hay regenerate khi build?

| Phương án | Lợi ích | Rủi ro | Gate cần |
| --- | --- | --- | --- |
| Không commit | Ít Git noise, luôn generated | Developer/CI cần generator metadata | Reproducible build |
| Commit generated code | IDE/offline thuận tiện, review diff | Quên regenerate, conflicts | Clean regenerate + diff check |
| Shared generated JAR | Dùng chung across modules | Coupling schema/versions | SemVer/internal artifact compatibility |
| Generate từ staging DB | Nhanh cho team nhỏ | Drift/race/credentials | Hạn chế, thay bằng ephemeral DB |

Không có lựa chọn đúng với mọi tổ chức. Điều bắt buộc là **khả năng tái lập từ migration source**, và khi CI thấy drift phải fail chứ không lặng lẽ giữ stale classes.

### 11.4. Generate không tự chạy migration

Một Maven generator ở `generate-sources` không đợi Spring Boot application startup để Flyway chạy. Một Gradle codegen task phụ thuộc `compileJava` không tự biết database đang ở version nào. **Sắp xếp build steps tường minh**, ví dụ Testcontainers lifecycle hoặc CI job provisioning.

### 11.5. Database schema là một hợp đồng giữa các phiên bản code

Khi deployment có hai pods:

~~~text
Pod A: generated classes V11
Pod B: generated classes V12
DB: schema V12
~~~

Với thay đổi additive, hai pods có thể cùng hoạt động. Với rename/drop hoặc tightening constraints, pod A có thể fail khi INSERT/SELECT. Trong các luồng Spring Integration, còn phải tính consumer batch/outbox relay dùng version cũ và replay historical rows.

## 12. Expand–migrate–contract và ranh giới deployment

Giả sử schema v11:

~~~sql
CREATE TABLE app.orders (
    id BIGINT PRIMARY KEY,
    order_id VARCHAR(120) UNIQUE NOT NULL,
    amount_minor INTEGER NOT NULL,
    legacy_total VARCHAR(40)
);
~~~

Muốn:

- Widen `amount_minor` thành BIGINT.
- Thêm `currency`.
- Xóa `legacy_total` vì đã dùng amount_minor.

### 12.1. EXPAND: thêm field an toàn cho old writers

~~~sql
ALTER TABLE app.orders
    ADD COLUMN currency CHAR(3);
~~~

Thêm nullable ở giai đoạn đầu cho phép pod cũ vẫn INSERT. Reader mới cần xử lý null/absent với semantics đúng (không tự mặc định USD/VND khi dữ liệu lịch sử không bảo đảm).

### 12.2. MIGRATE: backfill và deploy reader/writer

~~~text
1. Deploy new reader supports missing currency.
2. New writer starts setting currency.
3. Backfill old rows using authoritative historical records.
4. Verify no invalid or unknown currencies remain.
5. Track all old pods, scheduled jobs, ETL consumers.
6. Observe rollback window and aggregate data counts.
~~~

Nếu vừa thêm required column vừa deploy app mới nhưng old pods vẫn insert thiếu `currency`, traffic có thể lỗi `NOT NULL violation`. Codegen v12 type có thể đẹp nhưng database migration/rollout vẫn sai.

### 12.3. CONTRACT: tighten và bỏ legacy

~~~sql
ALTER TABLE app.orders
    ALTER COLUMN currency SET NOT NULL;
~~~

Chỉ sau khi mọi writers đều ghi currency và historical rows đã backfill. Bỏ `legacy_total` ở một migration/lần phát hành riêng khi không còn consumer nào cần.

### 12.4. Widening integer

`INTEGER`→`BIGINT` có thể là thay đổi có ý nghĩa cho SQL type, generated Java `Integer`→`Long` và REST/broker contracts. Không coi Java compile errors là “làm khó”: đó là cảnh báo cần cập nhật mapping/range/budget. Với tables rất lớn, DDL có thể lock/rewrite hoặc gây tải tùy PostgreSQL version/operation; lập kế hoạch online migration trên DB thật, không chạy trong giờ cao điểm không đánh giá.

### 12.5. Rollback code không phải rollback data

Nếu code v12 đã ghi JSONB shape hoặc enum value mới, rollback về code v11 có thể fail đọc dữ liệu mới. Phải có forward reader compatibility, feature flag, two-phase release hoặc versioned mapping theo policy.

## 13. Transaction boundary: jOOQ, Spring JDBC và outbox

### 13.1. Spring @Transactional

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public OrderReceipt confirm(ConfirmOrder command) {
        OrderReceipt result = orders.confirm(command);
        outbox.persistOrderConfirmed(
                command.operationId(), result.orderId());
        return result;
    }
}
~~~

`OrderRepository`, `OutboxRepository`, `ConfirmOrder`, `OrderReceipt` là types ứng dụng. **Cả hai repositories phải dùng cùng transactional datasource/connection** nếu mục tiêu là atomic SQL update + outbox insert. Nếu một repo dùng DSLContext của DB A và repo khác dùng DataSource B, local `@Transactional` không tự đảm bảo atomicity across databases.

### 13.2. jOOQ transaction API

Khi dùng jOOQ-managed transactions thay vì Spring annotation, có thể dùng:

~~~java
import org.jooq.DSLContext;
import org.jooq.impl.DSL;

public class OrderTransactionalRepository {

    private final DSLContext dsl;

    public OrderTransactionalRepository(DSLContext dsl) {
        this.dsl = dsl;
    }

    public void markConfirmed(long orderId) {
        dsl.transaction(configuration -> {
            DSLContext tx = DSL.using(configuration);

            tx.update(ORDERS)
                    .set(ORDERS.ORDER_STATUS, "CONFIRMED")
                    .where(ORDERS.ID.eq(orderId))
                    .execute();

            tx.insertInto(ORDER_OUTBOX)
                    .set(ORDER_OUTBOX.EVENT_ID,
                            java.util.UUID.randomUUID())
                    .set(ORDER_OUTBOX.ORDER_ID, "ORD-" + orderId)
                    .set(ORDER_OUTBOX.EVENT_TYPE, "OrderConfirmed")
                    .set(ORDER_OUTBOX.SCHEMA_VERSION, 1)
                    .set(ORDER_OUTBOX.PAYLOAD,
                            org.jooq.JSONB.valueOf("{}"))
                    .set(ORDER_OUTBOX.STATUS, "NEW")
                    .execute();
        });
    }
}
~~~

Đây là **logic minh họa**, chưa có idempotency, outbox payload thực, domain validation hoặc auth. Các generated fields/types và imports phải khớp schema/generator. Nếu dùng Spring-managed `@Transactional`, ưu tiên một transaction ownership rõ; không vô ý lồng jOOQ transaction manager không tương thích.

### 13.3. Spring TransactionProvider và connection

Spring Boot jOOQ auto-configuration thường tích hợp transaction với Spring DataSource/transaction manager khi phù hợp. Tự tạo `DSLContext` bằng `DSL.using(SQLDialect.POSTGRES)` hoặc supply một connection pool độc lập có thể phá transaction propagation của `@Transactional`.

Một integration test cần chứng minh:

~~~text
BEGIN transaction
  update app.orders
  insert app.order_outbox
force exception before commit
ASSERT both changes rolled back
~~~

Không chỉ mock `DSLContext` rồi kiểm method calls.

### 13.4. Transaction không bao gồm Kafka/HTTP

Một SQL transaction không ACID với Kafka producer publish hoặc HTTP partner API. **Outbox pattern**: cập nhật order và insert outbox trong cùng SQL COMMIT, relay publish sau commit với retry/deduplication.

~~~mermaid
sequenceDiagram
    participant S as OrderService
    participant D as PostgreSQL
    participant R as OutboxRelay
    participant K as Kafka
    S->>D: BEGIN + update order + insert outbox E-100
    D-->>S: COMMIT
    R->>D: Claim pending outbox
    R->>K: Publish event E-100
    K-->>R: Broker ACK
    R->>D: Mark sent
    Note over R,K: ACK may be lost; publish can repeat
~~~

### 13.5. Codegen và business idempotency

Generated primary keys metadata không thay **unique business key**. Nếu cần exactly-once business effect của duplicate HTTP/broker request, tạo unique `operation_id` hoặc `(consumer, event_id)` tại DB, xử lý duplicate trong transaction, trả persisted receipt và giữ stable eventId khi relay retry.

## 14. SQL errors: schema mismatch, permission và concurrency

jOOQ có `DataAccessException` và các exception types/classification tương ứng. Root cause từ JDBC có thể chứa SQLSTATE/vendor error code. Cần phân loại thay vì retry mọi query lỗi.

| PostgreSQL SQLSTATE | Ý nghĩa | Phản ứng |
| --- | --- | --- |
| `42P01` | Undefined table | Schema/migration mismatch, fail fast |
| `42703` | Undefined column | Generated/runtime drift |
| `42501` | Insufficient privilege | GRANT/role issue, không retry nóng |
| `23505` | Unique violation | Deduplication/business conflict |
| `23503` | Foreign key violation | Data invariant/order |
| `23502` | NOT NULL violation | Validation/rolling deploy |
| `23514` | CHECK violation | Business data invalid |
| `40001` | Serialization failure | Retry whole transaction có kiểm soát |
| `40P01` | Deadlock detected | Bounded transaction retry |
| `08xxx` | Connection exception | Network/availability, outcome UNKNOWN nếu commit không rõ |

### 14.1. COMMIT outcome UNKNOWN

Nếu client gọi SQL COMMIT và network reset trước khi nhận response, local application có thể không biết DB có commit hay không. Không tự retry “create order” với một random operationId mới; dùng unique business key/status lookup.

### 14.2. Lỗi do dialect khác với lỗi SQLSTATE schema

Nếu câu SQL được render theo dialect không phù hợp DB, có thể nhận syntax error (`42601`) hoặc unsupported operator/function. Chẩn đoán:

1. Runtime `DSLContext.configuration().dialect()` đang là gì?
2. JDBC URL/DB product/version thực tế là gì?
3. SQL render và bind placeholders ra sao?
4. PostgreSQL error position/SQLSTATE?
5. Query được generator build với table/field metadata nào?

Nếu DB user không có quyền, dialect đúng cũng không sửa được SQLSTATE 42501.

### 14.3. Không in bind values có PII

Trong production, tránh `ParamType.INLINED` hoặc logger in raw SQL chứa customer email, payment metadata, secret token. Cho phép log SQL shape/statement type/duration và `SQLSTATE` có redaction. JDBC/jOOQ diagnostics cần kiểm soát access/retention.

## 15. SQL injection và dynamic schema/identifier

Typed DSL giúp bind **data values**:

~~~java
dsl.selectFrom(ORDERS)
        .where(ORDERS.ORDER_ID.eq(requestOrderId))
        .fetchOne();
~~~

Thông thường jOOQ bind parameter thay vì nối request string trực tiếp vào SQL. Tuy nhiên, dynamic **identifiers**, raw SQL fragments và DSL templates vẫn có thể gây injection nếu xử lý sai.

### 15.1. Không nối tên bảng/column từ HTTP input

~~~java
// ANTI-PATTERN conceptual:
String query = "SELECT * FROM " + userProvidedTableName;
~~~

Table name thường không thể bind như một data value. Nếu client được chọn sorting/filtering, whitelist allowed generated Fields và use `DSL.name(...)`/typed DSL theo validated identifiers. Tránh dùng `DSL.field(String)` với chuỗi từ untrusted input.

### 15.2. Multi-tenant dynamic schema

Một user gửi `tenantId` không tự có quyền chọn schema theo tên. Nếu map tenant→schema, lấy tenant identity từ authenticated principal/domain authorization, giới hạn allowed schemas và dùng DB privileges/RLS. Test cross-tenant access với real datasource.

### 15.3. SQL logging và params

`renderInlined()`/inlined diagnostics có thể làm lộ data trong logs. Để debug có thể dùng sanitized query shape, SQLSTATE và traces; không lưu raw credit card numbers, PII hoặc access tokens ở event logs.

## 16. Reproducible CI/CD codegen pipeline

Một pipeline tham khảo:

~~~mermaid
flowchart TD
    A["Checkout migrations, generator config"] --> B["Start PostgreSQL Testcontainers/ephemeral DB"]
    B --> C["Apply all migration versions"]
    C --> D["Run jOOQ code generation"]
    D --> E["Compile generated + handwritten source"]
    E --> F["Compare generated diff if committed"]
    F --> G["Run PostgreSQL integration tests"]
    G --> H["Publish immutable build artifact"]
    H --> I["Deploy migration then compatible application"]
~~~

### 16.1. CI invariants

- Fresh schema DB from pinned PostgreSQL image version.
- Flyway/Liquibase migrates to expected version.
- jOOQ codegen input points to **that DB**, not local/staging by accident.
- Generated output is deterministic enough for review.
- Runtime jOOQ + generator versions compatible.
- Application compiles and tests on same target dialect.
- No credentials in generated Java, CI logs hoặc artifact.
- Migration order compatible với old pods/runtime.
- No untracked schema modifications hidden in CI setup.

### 16.2. Determinism

Generated source diff có thể thay đổi do:

- JOOQ/driver versions nâng.
- Metadata row ordering/config flags.
- Migrations không cố định thứ tự.
- Generator naming strategy đổi.
- `inputSchema` sai.
- Manual changes trong shared DB.
- Timestamp/banner/generation comments tùy version/config.
- Filesystem paths khác nhau.

Không viết golden diff test dựa vào timestamp nếu generator có option để loại nondeterminism. Tập trung vào schema metadata semantics và reproducibility.

### 16.3. Codegen kiểm tra drift

Nếu team commit generated Java, CI có thể:

~~~text
clean build
generate sources from fresh migrated DB
compare generated output to committed tree
if difference unexpected: fail and request regeneration
~~~

Không cho CI tự commit lại source trong mọi PR nếu chưa được yêu cầu; review schema-generated changes như các code changes khác.

## 17. Kiểm thử đúng dialect và schema bằng PostgreSQL

### 17.1. Vì sao H2 tests không đủ?

H2 in PostgreSQL compatibility mode vẫn khác PostgreSQL về:

- JSONB type/operators.
- Partial indexes.
- `INSERT ... ON CONFLICT`.
- Row locking, `SKIP LOCKED`.
- Transaction isolation/deadlock behavior.
- `TIMESTAMPTZ`/UUID/arrays/enums.
- SQL planner, constraints, sequences.
- Metadata introspection và generator output.

Với các tính năng này, dùng PostgreSQL thật trong Testcontainers hoặc ephemeral DB là lựa chọn kiểm chứng chính xác hơn.

### 17.2. Spring Boot integration skeleton

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.jooq.DSLContext;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest
class OrderJooqIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.jooq.sql-dialect", () -> "POSTGRES");
    }

    @Autowired
    DSLContext dsl;

    @Test
    void usesPostgresDialect() {
        assertEquals(
                org.jooq.SQLDialect.POSTGRES,
                dsl.dialect());
    }
}
~~~

Test skeleton cần migrations trên classpath, generated models và test resource setup. Khi Testcontainers tạo database mới, Spring Boot/Flyway phải apply migrations trước test queries. `postgres:16-alpine` chỉ minh họa pinned image; chọn version tương thích production và security policy. Không hardcode production secrets vào tests.

### 17.3. Test generated columns round-trip

~~~text
Given app.orders migrated to V12
When jOOQ insert with generated ORDERS.CURRENCY and returning ID
Then PostgreSQL accepts SQL
And returned Java types match generated mappings
And SELECT fetch maps currency/amount correctly
~~~

Đây là test **cả generated code lẫn runtime schema**, mạnh hơn unit test so sánh `.getSQL()`.

### 17.4. Test transaction rollback

~~~text
Given app.orders and app.order_outbox are empty
When @Transactional service updates order, inserts outbox
And throws before COMMIT
Then no business state or outbox intent is committed
~~~

Test database thực, đúng transaction manager/DSLContext. Nếu application có nhiều datasources, phải test mỗi transaction boundary.

### 17.5. Test concurrency và unique keys

~~~text
Given same operationId K-100 sent twice concurrently
When both workers attempt to insert reservation/receipt
Then one logical business effect exists
And duplicate attempt receives previous receipt/conflict
And eventId/outbox dedupe is preserved
~~~

Đừng chỉ mock repository method returns: SQL unique constraint and transaction race behavior mới là bằng chứng.

### 17.6. Test schema migration compatibility

~~~text
Old generated client V11 + DB schema V12:
  must continue to read/write supported fields

New generated client V12 + DB schema V11:
  must not be deployed for code paths requiring V12 fields

After Flyway V12 and regeneration:
  new client V12 passes CRUD/upsert/lock/JSONB tests
~~~

Khi cần graceful rolling deploy, test old/new applications against expanded schema; sau contract phase mới remove old fields.

## 18. Observability: query shape, execution và migration state

Không chỉ đo `dsl.select(...).fetch()` thành công. Cần biết **dialect, database version, schema, pool và SQLSTATE**.

| Signal | Vì sao cần |
| --- | --- |
| `DSLContext` configured dialect | Phát hiện render sai vendor |
| JDBC database product/version | Phát hiện target mismatch |
| Database migration version | So sánh generated/runtime schema |
| `current_database`, `current_schema` | Phát hiện wrong endpoint/schema |
| Query latency p50/p95/p99 | SQL performance/locks |
| Query errors by SQLSTATE | Tách schema drift/auth/connection |
| Hikari active/pending | Pool saturation |
| Connection acquisition latency | Pool bottleneck |
| Row counts | N+1 hoặc full table scan |
| Outbox backlog oldest age | Relay consistency |
| DB lock waits/deadlocks | Concurrency |
| Codegen duration/version | Build reliability |
| Generated source drift count | CI schema mismatch |
| Migration failures | Deployment gate |

Micrometer/Actuator và jOOQ ExecuteListener/diagnostics có thể cung cấp hoặc giúp instrument một phần, tùy phiên bản và cấu hình. Các tên metric là gợi ý, **không khẳng định framework tự động sinh toàn bộ**.

### 18.1. SQL listener và tracing

jOOQ cung cấp listener APIs cho execution lifecycle. Một custom `ExecuteListener` có thể đo time, statement type, SQLSTATE và kết nối trace context với transaction. Không log bind variables nhạy cảm và không làm blocking network export trong listener callback.

### 18.2. Cardinality

Tags hợp lý:

~~~text
database=orders
dialect=POSTGRES
operation=select|insert|update
error_sqlstate=42703|42501|23505
schema_version=12
~~~

Không dùng `orderId`, raw SQL with literal data, customer email, JWT token, entire JDBC URL với password làm Prometheus tags. Query IDs/hashes nên normalize SQL shape theo tooling, có redaction và giới hạn cardinality.

### 18.3. Error budget

Nếu codegen drift làm mọi query vào `ORDERS.CURRENCY` fail, đây là release/config bug chứ không phải transient database outage. Circuit breaker/retries không sửa được SQLSTATE `42703`; nên fail fast/deployment rollback hoặc migrate schema theo approved plan.

## 19. Runbook khi jOOQ query hoặc generator lỗi

| Triệu chứng | Khả năng | Bước kiểm tra |
| --- | --- | --- |
| `ORDERS.CURRENCY` không compile | Generated Java cũ | DB codegen schema version, regenerate |
| Generated files rỗng | `inputSchema`/regex sai | `current_schema`, generator logs |
| Codegen JDBC auth fails | Wrong build secret/URL/TLS | Metadata role, endpoint, CA |
| Codegen báo driver missing | Plugin classpath thiếu driver | Maven plugin deps/Gradle generator config |
| Codegen chạy nhưng output không được compile | Source set/target dir sai | Generated directory, task dependencies |
| Gradle task UP-TO-DATE dù migration đổi | Inputs không track migrations | Model inputs, clean CI regenerate |
| SQLSTATE 42P01 | Table/schema không tồn tại | Migration, `inputSchema`, runtime DB |
| SQLSTATE 42703 | Missing column | Generated/runtime drift |
| SQLSTATE 42501 | Runtime DB role thiếu GRANT | Schema USAGE, table/sequence privilege |
| SQL syntax fails on PostgreSQL | Wrong dialect or raw vendor SQL | `DSLContext.dialect()`, SQL render |
| JSONB operator fails | Test DB/dialect mismatch | Real PostgreSQL test |
| `RETURNING` result sai | DB dialect/version semantics | Real JDBC round-trip |
| `FOR UPDATE` behaves differently | Lock/isolation/dialect | Transaction, DB version |
| Converter ClassNotFound | Missing compile/runtime class | ForcedType/converter dependency |
| Type mismatch after migration | Java signatures stale | Regenerate, mapping update |
| Outbox duplicate events | ACK-loss/retry | Stable eventId/inbox dedupe |
| Database pool exhaustion | Long transactions/N+1 | Hikari pending, execution traces |
| Postgres TLS verification fails | CA/hostname mismatch | `sslmode=verify-full`, SAN |
| Rollback code cannot read new values | Data forward incompatibility | Versioned mapping/migration plan |

### 19.1. Thứ tự điều tra

1. Xác định query chạy qua `DSLContext` nào và runtime JDBC URL/DB product.
2. Kiểm tra dialect, generated package/version và migration version.
3. Đọc SQLSTATE/root cause, không chỉ text `DataAccessException`.
4. Kiểm tra `current_schema`, `search_path`, privileges và actual table definitions.
5. Xác định SQL có bind values, raw fragments hay vendor-only feature.
6. So generated SQL với PostgreSQL dialect đúng và thử trên isolated DB cùng version.
7. Xem Hikari pool/lock/transaction durations nếu có timeouts.
8. Xác nhận codegen CI đã regenerate từ fresh migrated schema.
9. Sửa migration/generator config hoặc repository code, không sửa generated Java tay.
10. Đảm bảo event/retry không tạo duplicate business effects sau lỗi DB.

## 20. Anti-pattern thường gặp

| Anti-pattern | Vì sao sai? | Thay thế |
| --- | --- | --- |
| Chỉ sửa generated `Orders.java` | Sẽ bị ghi đè/không có DB column | Migrate schema rồi regenerate |
| Chạy codegen trong production startup | Build/runtime coupling, secrets/race | Build-time generate |
| Dùng DB production làm metadata source CI | Rủi ro quyền/drift | Ephemeral DB from migrations |
| Dùng H2 dialect khi production PostgreSQL | Syntax/locking/type mismatch | PostgreSQL Testcontainers |
| Đổi `SQLDialect` để “nâng cấp DB” | Không thay database server | DB migration/driver/config |
| Bỏ qua `inputSchema` | Sinh sai objects hoặc không có objects | Explicit schema |
| Trộn `target.directory` với `outputSchema` | Filesystem vs DB namespace | Separate configs |
| Generate từ staging DB sửa tay | Nondeterministic output | Fresh migrations |
| Không pin generator/runtime version | Java API/linkage mismatch | Align with BOM |
| Gradle caching không track migration files | Stale generated classes | Declare inputs/verification |
| Bật all generated DAOs cho mọi domain | Coupling và build bloat | Chỉ bật cần thiết |
| Publish `OrdersRecord` thẳng Kafka | Leaks DB schema/PII | Separate event DTO |
| `SELECT *` trong public contract | Thay cột phá payload | Explicit fields |
| Nối HTTP input thành SQL identifier | Injection/cross-tenant | Whitelist fields/schema |
| Dùng search_path làm tenant authorization | Không phải security isolation | DB grants/RLS/domain auth |
| Giữ JDBC transaction khi gọi HTTP partner | Locks/pool saturation | Outbox/saga |
| Coi SQL unique violation là network error | Retry sai | Business idempotency |
| Catch hết SQL exception rồi retry vô hạn | DDL/auth bugs không tự hết | SQLSTATE taxonomy |
| Ignore migration version at deploy | Production schema drift | Migration readiness gates |
| Rollback JAR và nghĩ data rollback | New values may remain | Compatibility plan |
| Log bind params chứa PII | Rò dữ liệu | Redaction/normalized SQL |

## 21. Checklist production cho jOOQ + JDBC

### A. Dialect và runtime

- [ ] Biết chính xác DB engine/version/driver và chọn dialect được hỗ trợ.
- [ ] `DSLContext` dùng đúng DataSource, credentials, SSL và transaction manager.
- [ ] Multiple datasources có qualifiers/boundaries rõ.
- [ ] Không dùng H2-only tests thay PostgreSQL integration tests khi có vendor features.
- [ ] Raw SQL fragments dùng bind values và không nhận identifier tùy ý từ client.
- [ ] SQL errors phân loại theo SQLSTATE, không retry tất cả.
- [ ] Locking, upsert, JSONB, timezones, generated keys được test trên DB đích.

### B. Schema và codegen

- [ ] Một nguồn canonical cho versioned schema migrations.
- [ ] Codegen metadata source là DB cô lập đã migrate tới version kỳ vọng.
- [ ] `inputSchema`, includes/excludes, Java package và target dir chính xác.
- [ ] Generator/runtime jOOQ, driver và plugins version compatible.
- [ ] Generated code không sửa tay; có policy commit/regenerate.
- [ ] Gradle/Maven task graph bảo đảm migrate → generate → compile → test.
- [ ] CI detect codegen drift sau migration.
- [ ] No production codegen credentials in build/artifacts/logs.
- [ ] Generated records không expose trực tiếp HTTP/broker wire contracts.
- [ ] Forced types/converters và nullability được test round-trip.

### C. Migration và reliability

- [ ] Migrations được triển khai trước khi code truy cập column/table mới.
- [ ] Old/new pods tương thích trong rolling deployment.
- [ ] Expand–migrate–contract cho rename/drop/required columns.
- [ ] Backfill historical values có authoritative source và metrics.
- [ ] Database roles runtime/migration/codegen được tách theo least privilege.
- [ ] Outbox + business update ở cùng local SQL transaction.
- [ ] Idempotency dùng stable operationId/eventId và DB uniqueness.
- [ ] JDBC COMMIT network loss được xử lý là UNKNOWN khi chưa biết kết quả.
- [ ] Không giữ transaction khi chờ HTTP/broker dài.
- [ ] Rollback JAR có xét data/schema forward compatibility.

### D. Testing và operations

- [ ] Integration tests dùng PostgreSQL cùng dialect/version class phù hợp.
- [ ] Test mismatch generated code/runtime schema và SQLSTATE.
- [ ] Test JSONB, upsert, RETURNING, locks và transactions.
- [ ] Test concurrency/duplicate operationId/unique constraints.
- [ ] Verify Flyway/Liquibase version trong deployment.
- [ ] Metrics cho query latency, SQLSTATE, Hikari, outbox lag, build codegen drift.
- [ ] No raw SQL binds/secrets in logs or metrics labels.
- [ ] Runbook phân biệt schema mismatch, privilege, dialect và connection failure.

**Ghi nhớ:** Trong Spring Boot Integration, **SQL dialect quyết định SQL jOOQ render**, **database schema quyết định những đối tượng và ràng buộc tồn tại thật**, còn **jOOQ code generation chạy ở build time để tạo Java metadata**. Flyway/Liquibase hoặc quy trình migration được chỉ định mới sở hữu tiến hóa schema production. Quy trình ổn định là **migrate isolated PostgreSQL → generate jOOQ → compile → test đúng dialect → deploy migration tương thích trước code**; cùng với transaction/outbox/idempotency, nó giúp tránh cả lỗi build lẫn các sự cố dữ liệu khi luồng tích hợp thay đổi.

## Tài liệu tham khảo

- [jOOQ — Manual](https://www.jooq.org/doc/latest/manual/): DSL, SQL rendering, execution, records, transactions.
- [jOOQ — SQL Dialect](https://www.jooq.org/doc/latest/manual/sql-building/dsl-context/sql-dialects/): rendering theo RDBMS.
- [jOOQ — Code Generation](https://www.jooq.org/doc/latest/manual/code-generation/): metadata generators và Java output.
- [jOOQ — Code Generation Configuration](https://www.jooq.org/doc/latest/manual/code-generation/codegen-configuration/): inputSchema, target package, generated artifacts.
- [jOOQ — Maven Plugin](https://www.jooq.org/doc/latest/manual/code-generation/codegen-maven/): Maven generator lifecycle.
- [jOOQ — Gradle Code Generation](https://www.jooq.org/doc/latest/manual/code-generation/codegen-gradle/): official Gradle support/version-specific configuration.
- [jOOQ — Forced Types](https://www.jooq.org/doc/latest/manual/code-generation/codegen-advanced/codegen-config-database/codegen-database-forced-types/): custom type mappings.
- [jOOQ — Transactions](https://www.jooq.org/doc/latest/manual/sql-execution/transaction-management/): transaction APIs/providers.
- [Spring Boot — jOOQ](https://docs.spring.io/spring-boot/reference/data/sql.html#data.sql.jooq): Spring Boot integration và SQL dialect settings.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transactional DataSource boundaries.
- [Spring JDBC Reference](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): DataSource, JdbcTemplate, exception translations.
- [PostgreSQL — Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html): namespaces, search_path và privileges.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): ON CONFLICT, RETURNING.
- [PostgreSQL — SELECT](https://www.postgresql.org/docs/current/sql-select.html): locking, order and pagination.
- [PostgreSQL — JSON](https://www.postgresql.org/docs/current/datatype-json.html): JSONB operators/indexes.
- [Flyway — Documentation](https://documentation.red-gate.com/fd): versioned migrations.
- [Liquibase — Documentation](https://docs.liquibase.com/): changesets, schema changes.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): DB-backed integration tests.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): duplicate-safe processing.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): local transaction + durable message intent.
